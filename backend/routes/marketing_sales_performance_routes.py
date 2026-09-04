"""
Sales Performance Dashboard — Backend Routes
Phase 3 Week 6: Aggregate sales data from marketing_sales_data + marketing_orders
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query
from database import get_db
from auth import require_auth
# F6 (sesi #9) — performa penjualan WAJIB berlingkup toko.
from core import marketing_account_scope as _scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/performance", tags=["marketing-performance"])

# ── Standardized Response Helper ──
def success_response(data=None, pagination=None, metadata=None):
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if pagination is not None:
        response["pagination"] = pagination
    if metadata is not None:
        response["metadata"] = metadata
    return response

def _now() -> datetime:
    return datetime.now(timezone.utc)

def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

# ── Endpoints ──

@router.get("/overview")
async def performance_overview(
    request: Request,
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None, description="alias start_date"),
    date_to: Optional[str] = Query(None, description="alias end_date"),
    platform: Optional[str] = Query(None),
    account: Optional[str] = Query(None),
    account_id: Optional[str] = Query(None),
):
    """Ringkasan performa penjualan dari `marketing_orders`.

    F1.5/D05 (2026-08-12) — TIGA cacat yang ditutup di sini:
      1. Filter toko diterjemahkan ke `account_name` (teks), padahal dokumen punya
         `account_id`. Dua toko yang namanya diubah/mirip ⇒ angka tercampur.
      2. Omzet memakai `total_payment` (= Order Amount, TERMASUK ongkir) sehingga
         angkanya tidak pernah sama dengan omzet produk di rekap harian/Target.
         Sekarang memakai `revenue_product` (dasar kanonik), dengan cadangan
         `revenue`/`total_payment` untuk dokumen lama.
      3. Nama parameter tanggal berbeda dengan pemanggil lain (`date_from/date_to`)
         ⇒ layar mengirim rentang, endpoint diam-diam memakai "30 hari terakhir".
    """
    user = await require_auth(request)
    db = get_db()

    start_date = start_date or date_from
    end_date = end_date or date_to

    # Parse dates
    if start_date:
        start_dt = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
    else:
        start_dt = _now() - timedelta(days=30)
    
    if end_date:
        end_dt = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        if len(end_date) <= 10:           # tanggal saja ⇒ ikutkan seluruh harinya
            end_dt = end_dt + timedelta(days=1) - timedelta(microseconds=1)
    else:
        end_dt = _now()
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=timezone.utc)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=timezone.utc)

    # Aggregate from marketing_orders (committed import data)
    match_stage = {
        "order_date": {"$gte": start_dt, "$lte": end_dt},
        "status": {"$nin": ["cancelled"]}
    }
    if platform:
        match_stage["platform"] = platform
    # F1.5 — lingkup toko memakai `account_id` (SSOT). `account_name` hanya
    # dipertahankan sebagai jalur kompatibilitas dokumen lama.
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
        acc = await db.marketing_platform_accounts.find_one(
            {"id": account_id}, {"_id": 0, "account_name": 1})
        ors = [{"account_id": account_id}]
        if acc and acc.get("account_name"):
            ors.append({"account_id": {"$exists": False}, "account_name": acc["account_name"]})
        match_stage["$or"] = ors
    elif account:
        match_stage["account_name"] = account
    else:
        # F6 (sesi #9): tanpa filter toko, staf berlingkup hanya menjumlah toko
        # yang di-assign kepadanya — sebelumnya angka SEMUA toko yang keluar.
        _vis = await _scope.visible_account_ids(db, user)
        if _vis is not None:
            match_stage["account_id"] = {"$in": _vis}

    # Omzet kanonik: omzet PRODUK (setelah diskon penjual, sebelum potongan platform).
    REV_EXPR = {"$ifNull": ["$revenue_product", {"$ifNull": ["$revenue", "$total_payment"]}]}

    pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": None,
            "total_revenue": {"$sum": REV_EXPR},
            "total_order_amount": {"$sum": {"$ifNull": ["$order_amount", "$total_payment"]}},
            "total_orders": {"$sum": 1},
            "total_items": {"$sum": "$quantity"}
        }}
    ]
    
    result = await db.marketing_orders.aggregate(pipeline).to_list(1)
    stats = result[0] if result else {"total_revenue": 0, "total_order_amount": 0,
                                      "total_orders": 0, "total_items": 0}
    
    # Calculate AOV
    aov = stats["total_revenue"] / max(stats["total_orders"], 1)
    
    # By platform breakdown
    platform_pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": "$platform",
            "revenue": {"$sum": REV_EXPR},
            "orders": {"$sum": 1}
        }}
    ]
    by_platform = {}
    async for doc in db.marketing_orders.aggregate(platform_pipeline):
        by_platform[doc["_id"]] = {"revenue": doc["revenue"], "orders": doc["orders"]}

    # Pecahan per kanal pesanan (live / video / product_card / …) — F1
    channel_pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": {"$ifNull": ["$order_channel", "other"]},
            "revenue": {"$sum": REV_EXPR},
            "orders": {"$sum": 1}
        }},
        {"$sort": {"revenue": -1}},
    ]
    by_channel = {}
    async for doc in db.marketing_orders.aggregate(channel_pipeline):
        by_channel[doc["_id"]] = {"revenue": doc["revenue"], "orders": doc["orders"]}
    
    # Daily trend (rentang yang diminta, bukan selalu 30 hari terakhir)
    daily_pipeline = [
        {"$match": match_stage},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$order_date"}},
            "revenue": {"$sum": REV_EXPR},
            "orders": {"$sum": 1}
        }},
        {"$sort": {"_id": 1}}
    ]
    daily_trend = []
    async for doc in db.marketing_orders.aggregate(daily_pipeline):
        daily_trend.append({"date": doc["_id"], "revenue": doc["revenue"], "orders": doc["orders"]})
    
    return success_response(data={
        "total_revenue": stats["total_revenue"],
        "total_order_amount": stats.get("total_order_amount", 0),
        "total_orders": stats["total_orders"],
        "total_items": stats["total_items"],
        "aov": round(aov, 2),
        "revenue_label": "sebelum potongan platform",
        "by_platform": by_platform,
        "by_channel": by_channel,
        "daily_trend": daily_trend
    }, metadata={
        "start_date": start_dt.isoformat(),
        "end_date": end_dt.isoformat()
    })

@router.get("/top-products")
async def top_products(
    request: Request,
    days: int = Query(30, ge=1, le=365),
    limit: int = Query(10, ge=5, le=50),
    account_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
):
    user = await require_auth(request)
    db = get_db()
    
    start_dt = _now() - timedelta(days=days)
    
    match_stage: dict = {
        "order_date": {"$gte": start_dt},
        "status": {"$nin": ["cancelled"]}
    }
    if platform:
        match_stage["platform"] = platform
    if account_id:
        acc = await db.marketing_platform_accounts.find_one(
            {"id": account_id}, {"_id": 0, "account_name": 1})
        ors = [{"account_id": account_id}]
        if acc and acc.get("account_name"):
            ors.append({"account_id": {"$exists": False}, "account_name": acc["account_name"]})
        match_stage["$or"] = ors
        await _scope.assert_account_visible(db, user, account_id)
    else:
        # F6 (sesi #9) — tanpa filter toko, staf berlingkup hanya melihat produk
        # dari toko yang di-assign kepadanya.
        _vis = await _scope.visible_account_ids(db, user)
        if _vis is not None:
            match_stage["account_id"] = {"$in": _vis}

    # F1.5 — pecahan per PRODUK memakai `items[]` (1 dokumen = 1 pesanan, banyak SKU).
    # Pipeline lama mengelompokkan `product_name` pada AKAR dokumen sehingga seluruh
    # pesanan hasil impor Seller Center jatuh ke satu grup `null`.
    pipeline = [
        {"$match": match_stage},
        {"$unwind": {"path": "$items", "preserveNullAndEmptyArrays": True}},
        {"$group": {
            "_id": {"$ifNull": ["$items.product_name_raw",
                                {"$ifNull": ["$items.product_name", "$product_name"]}]},
            "total_qty": {"$sum": {"$ifNull": ["$items.quantity", "$quantity"]}},
            "total_revenue": {"$sum": {"$ifNull": [
                "$items.sku_subtotal_after_discount",
                {"$ifNull": ["$revenue_product", "$total_payment"]}]}},
            "order_count": {"$addToSet": "$id"},
            "sku": {"$first": {"$ifNull": ["$items.seller_sku", "$sku_id"]}},
        }},
        {"$project": {"total_qty": 1, "total_revenue": 1, "sku": 1,
                      "order_count": {"$size": "$order_count"}}},
        {"$sort": {"total_revenue": -1}},
        {"$limit": limit}
    ]
    
    products = []
    async for doc in db.marketing_orders.aggregate(pipeline):
        products.append({
            "product_name": doc["_id"],
            "sku": doc.get("sku"),
            "total_qty": doc["total_qty"],
            "total_revenue": doc["total_revenue"],
            "order_count": doc["order_count"]
        })
    
    return success_response(data={"products": products}, metadata={"days": days, "limit": limit})
