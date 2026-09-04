"""
Discount Campaign Manager — Backend Routes
Phase 3 Week 9: Kelola kampanye diskon multi-platform dengan expiration tracking
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri: jaring
# pengaman middleware hanya menolak permintaan yang MENYEBUT toko, ia tidak
# tahu isi jawaban. Tanpa ini staf pemegang satu toko membaca angka 9 toko.
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth
from routes.shared import require_portal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/discounts", tags=["marketing-discounts"])

DISCOUNT_TYPES = [
    "flash_sale", "voucher", "bundling", "buy_x_get_y",
    "free_shipping", "diskon_persen", "cashback", "giveaway"
]
DISCOUNT_TYPE_LABELS = {
    "flash_sale":    "Flash Sale",
    "voucher":       "Voucher / Kupon",
    "bundling":      "Bundling Produk",
    "buy_x_get_y":   "Buy X Get Y",
    "free_shipping": "Gratis Ongkir",
    "diskon_persen": "Diskon %",
    "cashback":      "Cashback",
    "giveaway":      "Giveaway",
}
PLATFORMS = ["shopee", "tiktok", "tokopedia", "instagram", "semua_platform"]


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

def _get_user(request: Request) -> dict:
    return getattr(request.state, "user", {}) or {}

def _compute_status(start_date: str, end_date: str) -> str:
    """Compute live status based on current date."""
    try:
        today = _now().date()
        start = datetime.fromisoformat(start_date).date() if 'T' not in start_date else datetime.fromisoformat(start_date).date()
        end   = datetime.fromisoformat(end_date).date()   if 'T' not in end_date   else datetime.fromisoformat(end_date).date()
        if today < start:
            return "upcoming"
        if today > end:
            return "expired"
        return "active"
    except Exception:
        return "draft"


# ── Seed ─────────────────────────────────────────────────────────────────────
async def seed_discounts_if_empty():
    db = get_db()
    if await db.marketing_discounts.count_documents({}) > 0:
        return

    import random
    now = _now()
    # F14 — sama seperti kalender konten: modelnya sudah benar, seed-nya belum.
    from core import marketing_account_scope as _scope
    accounts = await _scope.seed_account_pool(db)
    sample_discounts = [
        {"name": "Flash Sale Harbolnas 12.12",         "type": "flash_sale",    "value": 50, "unit": "persen"},
        {"name": "Voucher Gratis Ongkir Shopee",        "type": "free_shipping", "value": 0,  "unit": "nominal"},
        {"name": "Bundling Gamis + Kerudung",            "type": "bundling",      "value": 15, "unit": "persen"},
        {"name": "Cashback 10% Tokopedia",               "type": "cashback",      "value": 10, "unit": "persen"},
        {"name": "Buy 2 Get 1 Free Kerudung",            "type": "buy_x_get_y",   "value": 0,  "unit": "unit"},
        {"name": "Diskon 30% Koleksi Gamis Baru",        "type": "diskon_persen", "value": 30, "unit": "persen"},
        {"name": "Flash Sale TikTok Live",               "type": "flash_sale",    "value": 40, "unit": "persen"},
        {"name": "Giveaway Anniversary DA 2026",         "type": "giveaway",      "value": 0,  "unit": "nominal"},
        {"name": "Voucher Ramadhan Spesial",             "type": "voucher",        "value": 25000, "unit": "nominal"},
        {"name": "Flash Sale Akhir Bulan",               "type": "flash_sale",    "value": 35, "unit": "persen"},
    ]

    entries = []
    for i, disc in enumerate(sample_discounts):
        acc = accounts[i % len(accounts)]
        offset_start = random.randint(-10, 15)
        duration     = random.randint(1, 14)
        start_dt = now + timedelta(days=offset_start)
        end_dt   = start_dt + timedelta(days=duration)
        start_str = start_dt.strftime("%Y-%m-%d")
        end_str   = end_dt.strftime("%Y-%m-%d")

        entries.append({
            "id":           str(uuid.uuid4()),
            "account_id":   acc["id"],
            "account_name": acc.get("account_name", ""),
            "platform":     acc.get("platform", "shopee"),
            "name":         disc["name"],
            "discount_type": disc["type"],
            "discount_type_label": DISCOUNT_TYPE_LABELS.get(disc["type"], disc["type"]),
            "discount_value": disc["value"],
            "discount_unit":  disc["unit"],
            "min_purchase":   random.choice([0, 50000, 100000, 150000]),
            "max_discount":   random.choice([0, 50000, 100000]),
            "start_date":     start_str,
            "end_date":       end_str,
            "status":         _compute_status(start_str, end_str),
            "description":    f"Kampanye {disc['name']} untuk meningkatkan penjualan.",
            "product_scope":  "semua_produk",
            "_seed_origin": True,
            "created_by":     "system",
            "created_at":     _now(),
            "updated_at":     _now(),
        })

    if entries:
        await db.marketing_discounts.insert_many(entries)
    logger.info(f"[discounts] seeded {len(entries)} campaigns")


# ── Models ───────────────────────────────────────────────────────────────────
class DiscountIn(BaseModel):
    account_id: Optional[str] = None  # UUID dari marketing_platform_accounts
    account_name: str
    platform: str
    name: str
    discount_type: str
    discount_value: float = Field(default=0, ge=0)
    discount_unit: Optional[str] = "persen"    # persen | nominal | unit
    min_purchase: Optional[float] = 0
    max_discount: Optional[float] = Field(default=0, ge=0)
    start_date: str    # YYYY-MM-DD
    end_date: str      # YYYY-MM-DD
    description: Optional[str] = ""
    product_scope: Optional[str] = "semua_produk"

class DiscountUpdate(BaseModel):
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    platform: Optional[str] = None
    name: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = Field(default=None, ge=0)
    discount_unit: Optional[str] = None
    min_purchase: Optional[float] = None
    max_discount: Optional[float] = Field(default=None, ge=0)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    product_scope: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/types")
async def get_types(request: Request):
    await require_portal(request, "toko")  # RBAC read-guard (BUG-AUTH-1)
    return {"success": True, "types": [{"value": k, "label": v} for k, v in DISCOUNT_TYPE_LABELS.items()]}


@router.get("/summary")
async def get_summary(request: Request,
                      account_id: str = Query(default="")):
    user = await require_auth(request)
    await seed_discounts_if_empty()
    db = get_db()
    _sq = await _scope.scope_filter(
        db, user, {"account_id": account_id} if account_id else {})

    all_docs = await db.marketing_discounts.find(dict(_sq), {"_id": 0, "start_date": 1, "end_date": 1, "platform": 1}).to_list(1000)

    # Recompute live statuses
    active = upcoming = expired = 0
    by_platform = {}
    for d in all_docs:
        st = _compute_status(d.get("start_date", ""), d.get("end_date", ""))
        if st == "active":
            active   += 1
        elif st == "upcoming":
            upcoming += 1
        elif st == "expired":
            expired  += 1
        p = d.get("platform", "")
        by_platform[p] = by_platform.get(p, 0) + 1

    # Expiring in 3 days
    today = _now().date()
    in_3  = today + timedelta(days=3)
    expiring_soon = 0
    for d in all_docs:
        try:
            end = datetime.fromisoformat(d["end_date"]).date() if 'T' not in d["end_date"] else datetime.fromisoformat(d["end_date"]).date()
            if today <= end <= in_3:
                expiring_soon += 1
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return {
        "success": True,
        "data": {
            "total":         len(all_docs),
            "active":        active,
            "upcoming":      upcoming,
            "expired":       expired,
            "expiring_soon": expiring_soon,
            "by_platform":   by_platform,
        }
    }


@router.get("")
async def list_discounts(
    request: Request,
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    account_id: str = Query(default="", description="F14 — filter per toko (SSOT)"),
    status:    str = Query(default=""),
    platform:  str = Query(default=""),
    discount_type: str = Query(default=""),
    account:   str = Query(default="", description="kompatibilitas: cocok nama"),
    search:    str = Query(default=""),
):
    user = await require_auth(request)
    await seed_discounts_if_empty()
    db = get_db()

    q = await _scope.scope_filter(
        db, user, {"account_id": account_id} if account_id else {})
    if platform:
        q["platform"]      = platform
    if discount_type:
        q["discount_type"] = discount_type
    if account:
        q["account_name"]  = {"$regex": account, "$options": "i"}
    if search:
        q["name"]          = {"$regex": search, "$options": "i"}

    # If status filter → filter by live computed status
    all_items = await db.marketing_discounts.find(q, {"_id": 0}).sort("start_date", -1).to_list(2000)

    # Recompute status live
    for item in all_items:
        item["status"] = _compute_status(item.get("start_date", ""), item.get("end_date", ""))
        # Days left / ago
        try:
            end = datetime.fromisoformat(item["end_date"]).date()
            diff = (end - _now().date()).days
            item["days_remaining"] = diff if diff >= 0 else None
        except Exception:
            item["days_remaining"] = None

    if status:
        all_items = [i for i in all_items if i["status"] == status]

    total = len(all_items)
    skip  = (page - 1) * page_size
    items = all_items[skip: skip + page_size]

    return {
        "success": True,
        "data": serialize(items),
        "pagination": {"total": total, "page": page, "page_size": page_size,
                       "total_pages": max(1, (total + page_size - 1) // page_size)}
    }


@router.post("")
async def create_discount(body: DiscountIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db   = get_db()

    disc = {
        "id":           str(uuid.uuid4()),
        "account_id":   body.account_id,  # FK to marketing_platform_accounts (UUID)
        "account_name": body.account_name,
        "platform":     body.platform,
        "name":         body.name,
        "discount_type": body.discount_type,
        "discount_type_label": DISCOUNT_TYPE_LABELS.get(body.discount_type, body.discount_type),
        "discount_value": body.discount_value,
        "discount_unit":  body.discount_unit or "persen",
        "min_purchase":   body.min_purchase or 0,
        "max_discount":   body.max_discount or 0,
        "start_date":     body.start_date,
        "end_date":       body.end_date,
        "status":         _compute_status(body.start_date, body.end_date),
        "description":    body.description or "",
        "product_scope":  body.product_scope or "semua_produk",
        "created_by":     user.get("email", "unknown"),
        "created_at":     _now(),
        "updated_at":     _now(),
    }
    await db.marketing_discounts.insert_one(disc)
    return {"success": True, "data": serialize(disc)}


@router.put("/{disc_id}")
async def update_discount(disc_id: str, body: DiscountUpdate, request: Request):
    await require_auth(request)
    db = get_db()
    existing = await db.marketing_discounts.find_one({"id": disc_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Discount not found")

    upd = {k: v for k, v in body.dict().items() if v is not None}
    if "discount_type" in upd:
        upd["discount_type_label"] = DISCOUNT_TYPE_LABELS.get(upd["discount_type"], upd["discount_type"])
    # Recompute status based on new/existing dates
    sd = upd.get("start_date", existing.get("start_date", ""))
    ed = upd.get("end_date",   existing.get("end_date", ""))
    upd["status"] = _compute_status(sd, ed)
    upd["updated_at"] = _now()
    await db.marketing_discounts.update_one({"id": disc_id}, {"$set": upd})
    updated = {**existing, **upd}
    return {"success": True, "data": serialize(updated)}


@router.delete("/{disc_id}")
async def delete_discount(disc_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_discounts.delete_one({"id": disc_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Discount not found")
    return {"success": True, "message": "Deleted"}
