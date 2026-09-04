"""marketing_platform_kpi_routes — **baca KPI harian platform** (F7.2).

KENAPA ENDPOINT INI ADA
-----------------------
Impor `shopee_shop_kpi` / `shopee_content_kpi` menulis ke
`marketing_platform_kpi_daily`. Tanpa endpoint pembaca, koleksi itu akan menjadi
contoh baru dari keluhan owner: *"data masuk tapi tidak muncul di mana pun"* —
dan gate `gate_marketing_ssot` memang menandai koleksi yang ditulis-tapi-tak-dibaca.

ATURAN ANGKA (dipegang di satu tempat, bukan di layar)
-----------------------------------------------------
1. **GMV KPI bukan omzet.** Semua angka di sini memakai definisi platform
   (pesanan dibuat / siap dikirim / dibayar) dan **tidak pernah** dijumlah dengan
   `marketing_sales_data` / `marketing_orders`. Endpoint selalu mengirim
   `data_notes` yang menyatakan itu, supaya layar tidak bisa "lupa".
2. **Visibilitas per toko** memakai SSOT `core/marketing_account_scope` (F6):
   staf hanya melihat toko yang di-assign; membuka toko lain ⇒ 403.
3. **Tidak ada penjumlahan lintas-kanal untuk uang.** `shop` sudah memuat seluruh
   toko; `live` + `video` adalah bagian DI DALAM-nya. Menjumlah ketiganya berarti
   menghitung penjualan yang sama sampai tiga kali — jadi ringkasan dipisah per kanal.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth, serialize_doc
from core import marketing_account_scope as scope
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/platform-kpi", tags=["Marketing-PlatformKPI"])

COL = "marketing_platform_kpi_daily"
CHANNELS = ("shop", "live", "video")
CHANNEL_LABEL = {"shop": "Toko (keseluruhan)", "live": "Live Streaming", "video": "Video"}

# Angka yang dijumlah per kanal. Rasio (%) TIDAK dijumlah — dihitung ulang dari
# pembilang/penyebutnya, karena menjumlah persen adalah kesalahan yang paling
# sering membuat laporan terlihat "masuk akal" padahal salah.
SUM_FIELDS = (
    "gmv_created", "gmv_ready", "gmv_paid",
    "orders_created", "orders_ready", "orders_paid",
    "products_sold", "buyers", "visitors", "product_clicks", "product_views",
    "add_to_cart", "viewers", "active_viewers", "effective_viewers", "views",
    "likes", "shares", "comments", "new_followers", "live_sessions", "live_minutes",
    "videos_with_product", "voucher_shop_claimed", "voucher_live_claimed",
    "coin_claimed", "gmv_product_page", "gmv_live", "gmv_video", "gmv_affiliate",
    "gmv_ads",
)
DATA_NOTES = [
    "Angka di layar ini KPI PLATFORM (definisi Shopee: pesanan dibuat / siap "
    "dikirim / dibayar). Omzet resmi toko tetap dari pesanan (Order Terpadu) — "
    "kedua angka TIDAK boleh dijumlah.",
    "Kanal 'Toko' sudah mencakup Live dan Video. Menjumlah ketiganya menghitung "
    "penjualan yang sama berkali-kali.",
    "Rasio (konversi, CTR, engagement) dihitung ulang dari totalnya — bukan "
    "rata-rata dari rata-rata.",
]


def _num(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


async def _base_query(request: Request, account_id: Optional[str],
                      date_from: Optional[str], date_to: Optional[str],
                      channel: Optional[str]) -> Dict[str, Any]:
    user = await require_auth(request)
    db = get_db()
    q: Dict[str, Any] = {}
    if account_id:
        await scope.assert_account_visible(db, user, account_id)
        q["account_id"] = account_id
    else:
        visible = await scope.visible_account_ids(db, user)
        if visible is not None:
            q["account_id"] = {"$in": visible}
    if channel:
        if channel not in CHANNELS:
            raise HTTPException(400, f"Kanal harus salah satu dari: {', '.join(CHANNELS)}")
        q["channel"] = channel
    if date_from or date_to:
        q["date"] = {}
        if date_from:
            q["date"]["$gte"] = date_from
        if date_to:
            q["date"]["$lte"] = date_to
    return q


@router.get("/summary")
async def kpi_summary(request: Request,
                      account_id: Optional[str] = Query(None),
                      date_from: Optional[str] = Query(None),
                      date_to: Optional[str] = Query(None)):
    """Ringkasan per kanal + seri harian kanal `shop` (untuk grafik)."""
    q = await _base_query(request, account_id, date_from, date_to, None)
    db = get_db()
    rows = await db[COL].find(q, {"_id": 0}).sort("date", 1).to_list(5000)

    by_channel: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        ch = r.get("channel") or "shop"
        b = by_channel.setdefault(ch, {"channel": ch, "label": CHANNEL_LABEL.get(ch, ch),
                                       "days": 0, "dates": []})
        b["days"] += 1
        b["dates"].append(r.get("date"))
        for f in SUM_FIELDS:
            b[f] = round(_num(b.get(f)) + _num(r.get(f)), 2)

    out: List[dict] = []
    for ch in CHANNELS:
        b = by_channel.get(ch)
        if not b:
            continue
        gmv, orders = _num(b.get("gmv_created")), _num(b.get("orders_created"))
        visitors, views = _num(b.get("visitors")), _num(b.get("views"))
        eng = _num(b.get("likes")) + _num(b.get("comments")) + _num(b.get("shares"))
        b["aov"] = round(gmv / orders, 2) if orders else 0.0
        b["conversion_rate"] = round(orders / visitors * 100, 4) if visitors else 0.0
        b["engagement"] = round(eng, 2)
        b["engagement_rate"] = round(eng / views * 100, 2) if views else 0.0
        b["gmv_per_view"] = round(gmv / views, 2) if views else 0.0
        b["date_from"] = min(b["dates"]) if b["dates"] else None
        b["date_to"] = max(b["dates"]) if b["dates"] else None
        b.pop("dates", None)
        out.append(b)

    shop_series = [{"date": r.get("date"),
                    "gmv_created": _num(r.get("gmv_created")),
                    "orders_created": _num(r.get("orders_created")),
                    "visitors": _num(r.get("visitors")),
                    "gmv_live": _num(r.get("gmv_live")),
                    "gmv_video": _num(r.get("gmv_video")),
                    "gmv_ads": _num(r.get("gmv_ads"))}
                   for r in rows if (r.get("channel") or "") == "shop"]

    return serialize_doc({
        "success": True,
        "channels": out,
        "shop_series": shop_series,
        "total_rows": len(rows),
        "sources": sorted({r.get("source") for r in rows if r.get("source")}),
        "data_notes": DATA_NOTES,
    })


@router.get("")
async def kpi_rows(request: Request,
                   account_id: Optional[str] = Query(None),
                   channel: Optional[str] = Query(None),
                   date_from: Optional[str] = Query(None),
                   date_to: Optional[str] = Query(None),
                   limit: int = Query(400, ge=1, le=2000)):
    """Baris KPI harian (tabel). Terurut tanggal terbaru lebih dulu."""
    q = await _base_query(request, account_id, date_from, date_to, channel)
    db = get_db()
    rows = await db[COL].find(q, {"_id": 0}).sort([("date", -1), ("channel", 1)]).to_list(limit)
    total = await db[COL].count_documents(q)
    return serialize_doc({"success": True, "rows": rows, "total": total,
                          "data_notes": DATA_NOTES})
