"""
Unified Orders Dashboard — Backend Routes
Phase 2 Week 4: Order management dari hasil commit Universal Smart Import
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from database import get_db
from core import marketing_account_scope as _scope
from auth import require_auth
from utils.query_guards import q_date

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/orders", tags=["marketing-orders"])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── ZONA WAKTU: `order_date` ADALAH JAM DINDING WIB, BUKAN UTC ────────────────
# Kontrak SSOT ada di `core/marketing_daily_rollup` (§Zona waktu): `order_date`
# disimpan sebagai **jam dinding platform (WIB)** supaya rekap harian sama dengan
# yang staf lihat di Seller Center. Pesanan hasil IMPOR memang begitu (nilai
# mentah dari ekspor, mis. `2026-07-16 18:18:10`), tetapi pintu MANUAL dulu
# menulis `datetime.now(timezone.utc)`.
#
# Cacat NYATA yang ditutup (terukur 2026-08-13, gate CYC-8e MERAH): pesanan yang
# dibuat staf pada 01:12 **WIB tanggal 14** tersimpan bertanggal **13** (18:12
# UTC). Akibatnya rekap harian menaikkan omzet HARI YANG SALAH — layar "hari ini"
# tetap Rp 0 sementara omzet kemarin naik sendiri, dan pace target F5 (yang
# memakai `today_wib()`) menghitung hari yang berbeda dari pesanannya. Setiap
# pesanan yang diinput antara 00:00–07:00 WIB kena.
#
# Karena `order_date` dokumen impor NAIVE (tanpa tzinfo), pintu manual memakai
# bentuk yang sama: jam dinding WIB tanpa tzinfo. `created_at`/`updated_at` tetap
# UTC ber-tz (itu jejak audit, bukan tanggal bisnis).
WIB = timezone(timedelta(hours=7))


def _now_wib_wall() -> datetime:
    """Jam dinding WIB **tanpa tzinfo** — bentuk kanonik `order_date`."""
    return datetime.now(WIB).replace(tzinfo=None)


def _wib_day_start() -> datetime:
    """Awal hari menurut jam dinding WIB (dipakai jendela 'hari ini')."""
    return _now_wib_wall().replace(hour=0, minute=0, second=0, microsecond=0)


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


# F10 — daftar status & aturan transisi TIDAK boleh punya salinan di sini.
# Satu sumber: `core/order_status.py` (lihat docstring modul itu — jalur yang
# menyalin daftar ini adalah cara termudah membuatnya berbeda suatu hari).
from core.order_status import (  # noqa: E402
    ORDER_STATUSES as _CORE_ORDER_STATUSES,
    InvalidOrderTransition,
    apply_status as _apply_status,
    release_for_delete as _release_for_delete,
)

ORDER_STATUSES = list(_CORE_ORDER_STATUSES)
STATUS_FLOW = {
    "new": ["packed", "cancelled"],
    "packed": ["shipped", "cancelled"],
    "shipped": ["delivered", "returned"],
    "delivered": ["returned"],
    "cancelled": [],
    "returned": []
}

# ── Seed Demo Data ─────────────────────────────────────────────────────────────

async def ensure_order_indexes():
    """Pastikan indeks `marketing_orders` ada. **TIDAK** membuat data apa pun.

    CACAT BESAR YANG DITUTUP 2026-08-12 — dulu fungsi ini bernama
    `seed_orders_if_empty()` dan, setiap kali koleksi `marketing_orders` kosong,
    ia MENYUNTIK **60 pesanan ACAK** (produk, kota, kurir, status, dan uang dipilih
    dengan `random`) hanya karena seseorang membuka layar Order Terpadu.

    Kenapa itu tidak boleh ada lagi: sejak F2, `marketing_orders` adalah **SUMBER
    TUNGGAL OMZET** — rekap harian, target bulanan, dashboard, dan laporan rapat
    semuanya diturunkan darinya. Artinya pesanan karangan itu berubah menjadi
    **omzet karangan** di laporan yang dipakai rapat, tanpa satu pun penanda bahwa
    angkanya palsu. Ia juga membuat hasil "Batalkan impor" tidak pernah benar-benar
    bersih: 559 pesanan dihapus, lalu 60 pesanan acak muncul sendiri.

    Data demo yang SAH tetap tersedia dan sengaja harus diminta:
    `scripts/seed_katalog_order_demo.py` (rantai master → FG → katalog → order
    lewat API sungguhan, idempoten, bertanda `demo_source`).
    """
    db = get_db()
    for spec in (("id", {"unique": True, "sparse": True}), ("order_id", {}),
                 ("platform", {}), ("status", {}), ("order_date", {}), ("sku_id", {}),
                 ("account_id", {})):
        try:
            await db.marketing_orders.create_index(spec[0], **spec[1])
        except Exception:
            logging.getLogger(__name__).debug("index %s sudah ada", spec[0], exc_info=True)


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/summary")
async def orders_summary(request: Request,
                         account_id: Optional[str] = Query(None)):
    """F14 — ringkasan WAJIB bisa dilingkupi toko yang sama dengan tabelnya.
    Kalau tidak, kartu KPI dan tabel di bawahnya menampilkan dua kenyataan
    berbeda pada satu layar, dan yang dipercaya biasanya yang salah."""
    user = await require_auth(request)
    db = get_db()
    await ensure_order_indexes()
    # F6 (sesi #10) — ringkasan ini adalah UANG: staf yang memegang satu toko tidak
    # boleh membaca omzet sembilan toko dari kartu KPI. `scope_filter` mengembalikan
    # kueri yang sama untuk pemakai yang melihat semua toko.
    _scope_q = await _scope.scope_filter(
        db, user, {"account_id": account_id} if account_id else {})

    now   = _now()
    # Jendela "hari ini"/"pekan ini" memakai batas hari **WIB**, sejajar dengan
    # bentuk `order_date` (jam dinding WIB). Memakai tengah malam UTC membuat
    # jendela bergeser 7 jam: antara 00:00–07:00 WIB, "hari ini" masih memuat
    # pesanan sore KEMARIN — angka yang tak bisa dijelaskan ke staf.
    today_start = _wib_day_start()
    week_start  = today_start - timedelta(days=today_start.weekday())

    # Total counts by status
    _pre = [{"$match": dict(_scope_q)}] if _scope_q else []
    pipeline_status = _pre + [
        {"$group": {"_id": "$status", "count": {"$sum": 1},
                    "revenue": {"$sum": "$revenue"}}}
    ]
    status_counts = {}
    status_revenue = {}
    async for doc in db.marketing_orders.aggregate(pipeline_status):
        status_counts[doc["_id"]] = doc["count"]
        status_revenue[doc["_id"]] = doc.get("revenue", 0)

    # Revenue today
    pipeline_today = [
        {"$match": {**_scope_q, "order_date": {"$gte": today_start}, "status": {"$nin": ["cancelled", "returned"]}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$revenue"}, "orders": {"$sum": 1}}}
    ]
    today_data = {"revenue": 0, "orders": 0}
    async for doc in db.marketing_orders.aggregate(pipeline_today):
        today_data = {"revenue": doc.get("revenue", 0), "orders": doc.get("orders", 0)}

    # Revenue this week
    pipeline_week = [
        {"$match": {**_scope_q, "order_date": {"$gte": week_start}, "status": {"$nin": ["cancelled", "returned"]}}},
        {"$group": {"_id": None, "revenue": {"$sum": "$revenue"}, "orders": {"$sum": 1}}}
    ]
    week_data = {"revenue": 0, "orders": 0}
    async for doc in db.marketing_orders.aggregate(pipeline_week):
        week_data = {"revenue": doc.get("revenue", 0), "orders": doc.get("orders", 0)}

    # By platform
    pipeline_plat = _pre + [
        {"$group": {"_id": "$platform", "count": {"$sum": 1},
                    "revenue": {"$sum": "$revenue"}}}
    ]
    by_platform = {}
    async for doc in db.marketing_orders.aggregate(pipeline_plat):
        by_platform[doc["_id"]] = {"count": doc["count"], "revenue": doc.get("revenue", 0)}

    # Need action (new + packed)
    need_action = (status_counts.get("new", 0) + status_counts.get("packed", 0))
    total = sum(status_counts.values())
    total_revenue = sum(v for k, v in status_revenue.items() if k not in ["cancelled", "returned"])

    return {
        "total_orders":     total,
        "need_action":      need_action,
        "total_revenue":    round(total_revenue),
        "by_status":        status_counts,
        "by_platform":      by_platform,
        "today":            today_data,
        "this_week":        week_data,
    }


@router.get("")
async def list_orders(
    request: Request,
    platform:   Optional[str]  = Query(None),
    status:     Optional[str]  = Query(None),
    account_id: Optional[str]  = Query(None, description="F14 — filter per toko (SSOT)"),
    account_name: Optional[str]= Query(None, description="kompatibilitas: filter nama"),
    date_from:  Optional[str]  = Query(None),
    date_to:    Optional[str]  = Query(None),
    search:     Optional[str]  = Query(None),
    page:       int            = Query(1, ge=1),
    page_size:  int            = Query(25, le=100),
    sort_by:    str            = Query("order_date"),
    sort_dir:   int            = Query(-1)
):
    user = await require_auth(request)
    db = get_db()
    await ensure_order_indexes()

    q: dict = {}
    # F6 (2026-08-13) — daftar pesanan dipotong ke toko yang di-assign. Tanpa ini,
    # staf 1 toko bisa membaca seluruh pesanan (nama pembeli, nilai, kurir) toko lain.
    if account_id:
        await _scope.assert_account_visible(db, user, account_id)
    else:
        _visible = await _scope.visible_account_ids(db, user)
        if _visible is not None:
            q["account_id"] = {"$in": _visible}
    if platform:
        q["platform"]     = platform
    if status:
        q["status"]       = status
    if account_id:
        q["account_id"] = account_id
    if account_name:
        q["account_name"] = account_name
    if date_from or date_to:
        q["order_date"] = {}
        if date_from:
            # BUG-R11-A: validasi dulu — tanggal sampah dulu bikin HTTP 500
            q["order_date"]["$gte"] = datetime.fromisoformat(
                q_date(date_from, name="date_from").isoformat()
            )
        if date_to:
            q["order_date"]["$lte"] = datetime.fromisoformat(
                q_date(date_to, name="date_to").isoformat() + "T23:59:59"
            )
    if search:
        q["$or"] = [
            {"order_id":    {"$regex": search, "$options": "i"}},
            {"product_name":{"$regex": search, "$options": "i"}},
            {"sku_id":      {"$regex": search, "$options": "i"}},
            {"customer_name":{"$regex": search, "$options": "i"}},
        ]

    total = await db.marketing_orders.count_documents(q)
    orders = await db.marketing_orders.find(
        q, {"_id": 0}
    ).sort(sort_by, sort_dir).skip((page - 1) * page_size).limit(page_size).to_list(500)

    return serialize({
        "orders": orders,
        "pagination": {
            "page": page, "page_size": page_size, "total": total,
            "total_pages": max(1, (total + page_size - 1) // page_size)
        }
    })


# ══════════════════════════════════════════════════════════════════════════════
# F3 — MONITORING PENGIRIMAN: "apa yang harus dikejar hari ini"
# ══════════════════════════════════════════════════════════════════════════════
# Ekspor "Untuk Dikirim" memberi tahu pesanan mana yang MENUNGGU dikirim, tetapi
# daftar 559 baris tidak memberi tahu apa pun tentang PRIORITAS. Yang dibutuhkan
# tim setiap pagi cuma tiga angka: berapa yang belum dikirim, berapa yang sudah
# LEWAT BATAS (ini yang berubah jadi denda/penalti platform & pembatalan otomatis),
# dan berapa yang batal.
#
# BATAS KIRIM TIDAK DIKARANG DI KODE. Ia disimpan per toko di master
# (`ship_sla_days` / `ship_sla_days_preorder`) dan bisa diubah pemilik dari layar.
# Angka di bawah hanya nilai AWAL, dan layar selalu menyebut batas yang dipakai —
# aturan bisnis yang tersembunyi di kode adalah cara termudah membuat laporan
# "merah" yang tidak bisa dipertanggungjawabkan.
SLA_DEFAULT_DAYS = 2            # pesanan normal
SLA_DEFAULT_PREORDER_DAYS = 7   # pre-order (514 dari 601 baris berkas contoh = pre-order)

OPEN_STATUSES = ("new", "paid", "packed")
SHIPPED_STATUSES = ("shipped", "delivered", "completed")


def _as_utc(v):
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str) and len(v) >= 10:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00"))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def _order_is_preorder(order: dict) -> bool:
    """Pre-order = ADA item pre-order di dalam pesanan (batas kirimnya lebih panjang)."""
    if order.get("is_preorder") is True:
        return True
    for it in order.get("items") or []:
        if it.get("is_preorder") is True:
            return True
    return False


def _sla_of(account: dict, preorder: bool) -> float:
    if preorder:
        return float((account or {}).get("ship_sla_days_preorder")
                     or SLA_DEFAULT_PREORDER_DAYS)
    return float((account or {}).get("ship_sla_days") or SLA_DEFAULT_DAYS)


@router.get("/fulfillment-monitor")
async def fulfillment_monitor(
    request: Request,
    account_id: Optional[str] = Query(None, description="kosong = semua toko"),
    bucket: str = Query("lewat_batas", description="belum_dikirim | lewat_batas | batal | retur"),
    as_of: Optional[str] = Query(None, description="YYYY-MM-DD (uji/simulasi); kosong = sekarang"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=500),
):
    """Pesanan yang **belum dikirim**, yang **lewat batas kirim**, dan yang **batal**.

    Semua angka diturunkan dari `marketing_orders` (hasil impor Seller Center) —
    tidak ada satu pun yang diketik. Respons SELALU memuat `data_notes`: batas hari
    yang dipakai per toko, dan bagian mana yang datanya memang belum lengkap
    (mis. batal/retur tidak ada di ekspor "Untuk Dikirim") supaya rapat tidak
    menyimpulkan "tidak ada pembatalan" dari data yang tidak memuatnya.
    """
    user = await require_auth(request)
    db = get_db()
    await ensure_order_indexes()

    now = _as_utc(as_of) or _now() if as_of else _now()
    if as_of and not _as_utc(as_of):
        raise HTTPException(400, "as_of harus format YYYY-MM-DD")

    # F6 (sesi #10) — daftar toko & pesanannya wajib berlingkup pemakai. Tanpa ini
    # staf pemegang satu toko melihat antrean kirim + pembatalan sembilan toko.
    accounts = await _scope.visible_accounts(
        db, user, base={} if not account_id else {"id": account_id}, limit=200)
    if account_id and not accounts:
        raise HTTPException(404, "Toko tidak ditemukan")
    acc_by_id = {a["id"]: a for a in accounts}

    q: dict = await _scope.scope_filter(
        db, user, {"account_id": account_id} if account_id else {})
    orders = await db.marketing_orders.find(q, {"_id": 0}).to_list(20000)

    open_rows, late_rows, cancelled_rows, returned_rows = [], [], [], []
    shipped_n = 0
    per_store: dict = {}

    for o in orders:
        aid = o.get("account_id") or ""
        acc = acc_by_id.get(aid, {})
        st = (o.get("status") or "").lower()
        stat = per_store.setdefault(aid, {
            "account_id": aid,
            "account_code": acc.get("account_code") or "",
            "account_name": o.get("account_name") or acc.get("account_name") or "(tanpa toko)",
            "platform": o.get("platform") or acc.get("platform") or "",
            "sla_days": _sla_of(acc, False),
            "sla_days_preorder": _sla_of(acc, True),
            "belum_dikirim": 0, "lewat_batas": 0, "batal": 0, "retur": 0,
            "sudah_dikirim": 0,
            "nilai_belum_dikirim": 0.0, "nilai_lewat_batas": 0.0,
            "umur_tertua_hari": 0.0,
        })

        if st == "cancelled":
            stat["batal"] += 1
            cancelled_rows.append(o)
            continue
        if st == "returned":
            stat["retur"] += 1
            returned_rows.append(o)
            continue
        if st in SHIPPED_STATUSES or _as_utc(o.get("shipped_at")):
            stat["sudah_dikirim"] += 1
            shipped_n += 1
            continue
        if st not in OPEN_STATUSES:
            continue

        basis = _as_utc(o.get("paid_at")) or _as_utc(o.get("order_date"))
        if basis is None:
            age_days = None
        else:
            age_days = round((now - basis).total_seconds() / 86400.0, 2)
        preorder = _order_is_preorder(o)
        sla = _sla_of(acc, preorder)
        value = float(o.get("revenue_product") or o.get("revenue") or 0)
        late = age_days is not None and age_days > sla

        row = {
            "id": o.get("id"),
            "order_id": o.get("order_id"),
            "account_id": aid,
            "account_name": stat["account_name"],
            "platform": stat["platform"],
            "status": st,
            "status_raw": o.get("status_raw") or "",
            "is_preorder": preorder,
            "paid_at": o.get("paid_at") or o.get("order_date"),
            "order_date": o.get("order_date"),
            "age_days": age_days,
            "sla_days": sla,
            "over_by_days": (round(age_days - sla, 2) if late else 0),
            "deadline": (basis + timedelta(days=sla)).isoformat() if basis else None,
            "late": bool(late),
            "courier": o.get("courier") or o.get("shipping_provider") or "",
            "order_channel": o.get("order_channel") or "",
            "quantity": o.get("quantity") or 0,
            "value": value,
            "buyer": o.get("buyer_username") or o.get("customer_name") or "",
            "city": o.get("city") or o.get("regency_city") or "",
        }
        open_rows.append(row)
        stat["belum_dikirim"] += 1
        stat["nilai_belum_dikirim"] += value
        if age_days is not None:
            stat["umur_tertua_hari"] = max(stat["umur_tertua_hari"], age_days)
        if late:
            late_rows.append(row)
            stat["lewat_batas"] += 1
            stat["nilai_lewat_batas"] += value

    def _simple(o: dict) -> dict:
        return {
            "id": o.get("id"), "order_id": o.get("order_id"),
            "account_id": o.get("account_id"),
            "account_name": o.get("account_name"),
            "status": (o.get("status") or "").lower(),
            "status_raw": o.get("status_raw") or "",
            "order_date": o.get("order_date"),
            "cancelled_at": o.get("cancelled_at"),
            "cancel_reason": o.get("cancel_reason") or o.get("cancelation_return_type") or "",
            "value": float(o.get("revenue_product") or o.get("revenue") or 0),
            "quantity": o.get("quantity") or 0,
        }

    buckets = {
        "belum_dikirim": sorted(open_rows, key=lambda r: -(r["age_days"] or 0)),
        "lewat_batas": sorted(late_rows, key=lambda r: -(r["over_by_days"] or 0)),
        "batal": [_simple(o) for o in cancelled_rows],
        "retur": [_simple(o) for o in returned_rows],
    }
    if bucket not in buckets:
        raise HTTPException(400, f"bucket harus salah satu dari: {', '.join(buckets)}")
    rows = buckets[bucket]
    total = len(rows)
    start = (page - 1) * page_size
    page_rows = rows[start:start + page_size]

    totals = {
        "belum_dikirim": len(open_rows),
        "lewat_batas": len(late_rows),
        "batal": len(cancelled_rows),
        "retur": len(returned_rows),
        "sudah_dikirim": shipped_n,
        "nilai_belum_dikirim": round(sum(r["value"] for r in open_rows)),
        "nilai_lewat_batas": round(sum(r["value"] for r in late_rows)),
        "umur_tertua_hari": max([r["age_days"] or 0 for r in open_rows], default=0),
        "pesanan_dibaca": len(orders),
    }

    notes = []
    if not orders:
        notes.append("Belum ada pesanan sama sekali untuk lingkup ini — impor ekspor "
                     "Seller Center dulu di menu Impor Data.")
    if not cancelled_rows and not returned_rows and orders:
        notes.append("Angka BATAL & RETUR masih 0 karena ekspor 'Untuk Dikirim' (Ekspor A) "
                     "tidak memuat pesanan batal/retur. Jangan disimpulkan sebagai "
                     "'tidak ada pembatalan' — perlu ekspor Batal/Retur (Ekspor C).")
    missing_basis = sum(1 for r in open_rows if r["age_days"] is None)
    if missing_basis:
        notes.append(f"{missing_basis} pesanan tidak punya waktu bayar maupun tanggal "
                     f"pesanan, jadi umurnya tidak bisa dihitung dan TIDAK ikut "
                     f"dihitung lewat batas.")
    default_sla = [s for s in per_store.values()
                   if s["sla_days"] == SLA_DEFAULT_DAYS
                   and not (acc_by_id.get(s["account_id"], {}) or {}).get("ship_sla_days")]
    if default_sla:
        notes.append(f"{len(default_sla)} toko masih memakai batas kirim bawaan "
                     f"({SLA_DEFAULT_DAYS} hari normal / {SLA_DEFAULT_PREORDER_DAYS} hari "
                     f"pre-order). Ubah per toko lewat tombol 'Batas kirim' bila "
                     f"platformnya berbeda.")

    return serialize({
        "ok": True,
        "as_of": now.isoformat(),
        "bucket": bucket,
        "totals": totals,
        "per_store": sorted(per_store.values(), key=lambda s: -s["lewat_batas"]),
        "rows": page_rows,
        "page": page, "page_size": page_size, "total": total,
        "total_pages": max(1, (total + page_size - 1) // page_size),
        "sla_default": {"normal": SLA_DEFAULT_DAYS, "preorder": SLA_DEFAULT_PREORDER_DAYS},
        "data_notes": notes,
    })


@router.get("/picking-list")
async def generate_picking_list(
    request: Request,
    statuses: Optional[str] = Query("new,packed"),
    platform: Optional[str] = Query(None)
):
    """Generate a picking list grouped by SKU."""
    user = await require_auth(request)
    db = get_db()

    status_list = [s.strip() for s in statuses.split(",")]
    # F6 (sesi #10) — daftar ambil barang ikut lingkup toko: staf toko A tidak
    # boleh mengambil (atau melihat) pesanan toko B.
    q: dict = await _scope.scope_filter(db, user, {"status": {"$in": status_list}})
    if platform:
        q["platform"] = platform

    orders = await db.marketing_orders.find(q, {"_id": 0}).to_list(500)

    # Group by SKU + Variation
    picking: dict = {}
    for o in orders:
        key = f"{o.get('sku_id','')} | {o.get('variation','')}"
        if key not in picking:
            picking[key] = {
                "sku_id":       o.get("sku_id", ""),
                "variation":    o.get("variation", ""),
                "product_name": o.get("product_name", ""),
                "total_qty":    0,
                "order_ids":    [],
                "platforms":    set()
            }
        picking[key]["total_qty"]  += o.get("quantity", 1)
        picking[key]["order_ids"].append(o.get("order_id", ""))
        picking[key]["platforms"].add(o.get("platform", ""))

    result = []
    for k, v in sorted(picking.items(), key=lambda x: -x[1]["total_qty"]):
        result.append({
            "sku_id":       v["sku_id"],
            "variation":    v["variation"],
            "product_name": v["product_name"],
            "total_qty":    v["total_qty"],
            "order_count":  len(v["order_ids"]),
            "platforms":    list(v["platforms"]),
            "order_ids":    v["order_ids"][:10]
        })

    return {
        "picking_list": result,
        "total_items": len(result),
        "total_orders": len(orders),
        "generated_at": _now().isoformat(),
        "status_filter": status_list
    }


@router.get("/{order_id}")
async def get_order(order_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    order = await db.marketing_orders.find_one(
        {"$or": [{"id": order_id}, {"order_id": order_id}]}, {"_id": 0}
    )
    if not order:
        raise HTTPException(404, "Order not found")
    return serialize(order)


# ── Manual Order Creation (replaces legacy POST /api/dewi/toko/orders) ───────

class OrderItemBody(BaseModel):
    sku_code: Optional[str] = ""
    product_name: Optional[str] = ""
    qty: int = Field(default=1, ge=0)
    price: float = Field(default=0.0, ge=0)
    variant: Optional[str] = ""
    # ── K-8b (2026-08-10) — TAUTAN MASTER PER BARIS ───────────────────────────
    # Dulu hanya baris PERTAMA yang ditautkan & direservasi, jadi order 3 produk
    # hanya memesan stok 1 produk: dua produk lain bisa terjual dua kali
    # (overselling) tanpa jejak. Sekarang setiap baris membawa tautannya sendiri.
    catalog_item_id: Optional[str] = None
    variant_id: Optional[str] = None
    fg_material_id: Optional[str] = None


class OrderCreateBody(BaseModel):
    # ── F14 — LINGKUP TOKO WAJIB ──────────────────────────────────────────────
    # Dulu order hanya menyimpan `account_name` sebagai TEKS. Akibat terukur:
    # 60/60 order tidak punya `account_id`, sehingga pemilih akun di layar Order
    # Terpadu SELALU mengembalikan daftar kosong dan laporan per toko Rp 0.
    # `account_name` sekarang hanya jalan masuk (nama dari berkas marketplace);
    # yang DISIMPAN selalu `account_id` hasil resolusi master.
    account_id: Optional[str] = None
    # Required
    platform: str  # shopee | tiktok | tokopedia | manual | website | etc.
    customer_name: str
    # Identification
    order_id: Optional[str] = None  # marketplace reference (auto-gen if blank)
    account_name: Optional[str] = None
    # ── K-8a — TAUTAN KE MASTER (wajib salah satu) ────────────────────────────
    catalog_item_id: Optional[str] = None   # item katalog yang dijual
    variant_id: Optional[str] = None        # varian master (SKU terkecil)
    fg_material_id: Optional[str] = None    # diisi server; diterima utk impor
    reserve_stock: Optional[bool] = True    # M10 — pesan stok saat order masuk
    # Customer
    customer_phone: Optional[str] = ""
    customer_address: Optional[str] = ""
    city: Optional[str] = ""
    # Items (can be multi or single)
    items: List[OrderItemBody] = []
    # Or single-item flat fields (used when items=[])
    sku_id: Optional[str] = ""
    product_name: Optional[str] = ""
    variation: Optional[str] = ""
    quantity: int = Field(default=1, ge=0)
    price_original: float = Field(default=0.0, ge=0)
    price_final: float = Field(default=0.0, ge=0)
    # Money
    total_payment: float = Field(default=0.0, ge=0)
    fee_amount: float = Field(default=0.0, ge=0)
    shipping_cost: float = Field(default=0.0, ge=0)
    # Logistics
    courier: Optional[str] = ""
    tracking_number: Optional[str] = None
    payment_method: Optional[str] = ""
    note: Optional[str] = ""


async def _resolve_order_link(db, *, catalog_item_id=None, variant_id=None,
                              fg_material_id=None, sku_id='') -> dict:
    """**K-8a** — resolusi tautan order → master, dijalankan SERVER.

    Kenapa wajib: `marketing_orders` dulu hanya menyimpan `sku_id` **teks bebas**
    tanpa validasi (M9). Akibatnya `POST /api/fulfillment/orders/{id}/allocate`
    MEWAJIBKAN manusia memilih `material_id` untuk setiap pesanan — tautan
    order→barang dibuat ULANG dengan tangan, dan salah pilih = stok salah turun.

    Urutan: `catalog_item_id` → `variant_id` → `fg_material_id` → `sku_id` (dicari
    di item katalog, lalu varian, lalu kode FG). Tidak ketemu ⇒ pemanggil balas 400.
    """
    from core import catalog_stock as _cstock

    out = {'catalog_item_id': None, 'variant_id': None, 'fg_material_id': None,
           'variant_sku': '', 'product_name': '', 'variation': '',
           'model_id': None, 'harga_jual': 0.0, 'resolved_by': None}

    item = None
    if catalog_item_id:
        item = await db.marketing_catalog_items.find_one({'id': catalog_item_id}, {'_id': 0})
        if not item:
            return {**out, 'error': f"catalog_item_id '{catalog_item_id}' tidak ditemukan."}
        if item.get('is_active') is False:
            return {**out, 'error': f"Item katalog '{item.get('sku')}' sudah non-aktif "
                                    '(produk dihentikan) — tidak bisa dijual.'}
        out['resolved_by'] = 'catalog_item_id'

    if not item and variant_id:
        v = await db.rahaza_model_variants.find_one({'id': variant_id}, {'_id': 0})
        if not v:
            return {**out, 'error': f"variant_id '{variant_id}' tidak ditemukan."}
        if v.get('active') is False:
            return {**out, 'error': f"Varian {v.get('sku')} sudah non-aktif — tidak bisa dijual."}
        item = await db.marketing_catalog_items.find_one(
            {'$or': [{'variant_id': variant_id}, {'variant_sku': v.get('sku')}],
             'is_active': {'$ne': False}}, {'_id': 0})
        out.update({'variant_id': variant_id, 'variant_sku': v.get('sku') or '',
                    'model_id': v.get('model_id'), 'resolved_by': 'variant_id'})
        if not item:
            fg = await _cstock.find_fg_by_sku(db, v.get('sku') or '')
            out['fg_material_id'] = (fg or {}).get('id')
            out['product_name'] = (fg or {}).get('name') or v.get('model_name') or ''
            out['variation'] = f"{v.get('color_name', '')} / {v.get('size_code', '')}".strip(' /')
            if not out['fg_material_id']:
                return {**out, 'error': f"Master FG untuk SKU {v.get('sku')} belum ada di inventory."}
            return out

    if not item and fg_material_id:
        fg = await db.rahaza_materials.find_one(
            {'id': fg_material_id, 'type': 'fg'}, {'_id': 0})
        if not fg:
            return {**out, 'error': f"fg_material_id '{fg_material_id}' bukan FG yang dikenal."}
        item = await db.marketing_catalog_items.find_one(
            {'$or': [{'fg_material_id': fg['id']}, {'material_id': fg['id']}],
             'is_active': {'$ne': False}}, {'_id': 0})
        if not item:
            out.update({'fg_material_id': fg['id'], 'variant_sku': fg.get('sku') or fg.get('code') or '',
                        'variant_id': fg.get('variant_id'), 'model_id': fg.get('model_id'),
                        'product_name': fg.get('name') or '', 'resolved_by': 'fg_material_id'})
            return out

    if not item and (sku_id or '').strip():
        sku = sku_id.strip()
        item = await db.marketing_catalog_items.find_one(
            {'sku': {'$regex': f'^{__import__("re").escape(sku)}$', '$options': 'i'},
             'is_active': {'$ne': False}}, {'_id': 0})
        if item:
            out['resolved_by'] = 'sku_id→catalog_item'
        else:
            v = await db.rahaza_model_variants.find_one(
                {'sku': {'$regex': f'^{__import__("re").escape(sku)}$', '$options': 'i'}},
                {'_id': 0})
            if v:
                return await _resolve_order_link(db, variant_id=v['id'])
            fg = await _cstock.find_fg_by_sku(db, sku)
            if fg:
                return await _resolve_order_link(db, fg_material_id=fg['id'])
            return {**out, 'error': f"SKU '{sku}' tidak dikenal di katalog maupun master produk. "
                                    'Pilih produk dari katalog.'}

    if not item:
        return {**out, 'error': 'Order wajib membawa tautan ke master: `catalog_item_id` '
                                'atau `variant_id` (atau `sku_id` yang dikenal).'}

    link = await _cstock.resolve_link(db, item)
    if not link.get('fg_material_id'):
        return {**out, 'error': f"Item katalog '{item.get('sku')}' belum tertaut ke master FG — "
                                'tautkan varian/FG-nya dulu di Katalog.'}
    out.update({
        'catalog_item_id': item.get('id'),
        'variant_id': item.get('variant_id') or link.get('variant_id'),
        'fg_material_id': link['fg_material_id'],
        'variant_sku': link.get('variant_sku') or item.get('sku') or '',
        'product_name': item.get('name') or '',
        'variation': item.get('variant_info') or '',
        'model_id': item.get('model_id') or link.get('model_id'),
        'harga_jual': float(item.get('harga_jual') or item.get('price') or 0),
        'resolved_by': out['resolved_by'] or 'catalog_item_id',
    })
    return out


@router.post("", status_code=201)
async def create_order(body: OrderCreateBody, request: Request):
    """Create a manual order in marketing_orders SSOT.

    **K-8a (2026-08-10)** — order WAJIB membawa tautan master
    (`catalog_item_id`/`variant_id`, atau `sku_id` yang dikenal). Server yang
    mengisi `fg_material_id`. SKU tak dikenal ⇒ **400**. Pesanan LAMA tetap
    terbaca (tautan hanya diwajibkan untuk pembuatan BARU).

    **M10** — stok langsung **DIRESERVASI** saat order masuk. Dulu reservasi baru
    terjadi di `allocate`, sehingga ada jendela di mana stok yang sama bisa
    dijual dua kali. Stok tidak cukup ⇒ **409** (bukan diterima lalu oversell).
    """
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    from core import catalog_stock as _cstock
    from core import stock_service as _ss
    from core import marketing_account_scope as _scope

    # F14 — resolusi toko dilakukan SEBELUM apa pun ditulis/direservasi. Order
    # tanpa toko yang sah ditolak keras: baris yatim tidak pernah muncul di layar
    # yang difilter, dan itu jenis kerusakan yang tidak melahirkan pesan error.
    _acc, _why = await _scope.resolve_account(
        db, account_id=body.account_id, account_name=body.account_name,
        platform=body.platform)
    if not _acc:
        raise HTTPException(400, f"Toko/akun tidak sah: {_why}")

    # ── K-8b — SETIAP baris order ditautkan & direservasi, bukan hanya yang pertama
    # Dulu hanya `items[0]` yang ditautkan ke master dan hanya stok baris itu yang
    # dipesan. Order 3 produk = 2 produk TIDAK dipesan ⇒ bisa terjual dua kali
    # (overselling) tanpa jejak. Sekarang server memvalidasi & memesan per baris,
    # dan kalau satu baris gagal SEMUA reservasi baris sebelumnya dilepas (atomik).
    raw_items = [it.dict() for it in body.items] if body.items else []
    flat_mode = not raw_items
    if flat_mode:
        lines = [{
            'sku_code': body.sku_id or '',
            'product_name': body.product_name or '',
            'qty': int(body.quantity or 1),
            'price': float(body.price_final or 0),
            'variant': body.variation or '',
            'catalog_item_id': body.catalog_item_id,
            'variant_id': body.variant_id,
            'fg_material_id': body.fg_material_id,
        }]
    else:
        lines = raw_items
        # Payload lama (importer/layar lama) menaruh tautan di tingkat ORDER —
        # dipakaikan ke baris pertama supaya tetap sah, tanpa perubahan perilaku.
        _first = lines[0]
        if not (_first.get('catalog_item_id') or _first.get('variant_id')
                or _first.get('fg_material_id')):
            _first['catalog_item_id'] = body.catalog_item_id
            _first['variant_id'] = body.variant_id
            _first['fg_material_id'] = body.fg_material_id

    def _line_label(idx: int, ln: dict) -> str:
        """Sebut baris mana yang bermasalah — hanya bila ordernya multi-produk."""
        if len(lines) <= 1:
            return ''
        who = ((ln.get('sku_code') or ln.get('product_name') or '') or '').strip()
        return f"Produk {idx + 1}" + (f" ({who})" if who else '')

    resolved: list = []
    for _i, _ln in enumerate(lines):
        _lk = await _resolve_order_link(
            db,
            catalog_item_id=_ln.get('catalog_item_id'),
            variant_id=_ln.get('variant_id'),
            fg_material_id=_ln.get('fg_material_id'),
            sku_id=(_ln.get('sku_code') or ''),
        )
        if _lk.get('error'):
            _pre = _line_label(_i, _ln)
            raise HTTPException(400, f"{_pre}: {_lk['error']}" if _pre else _lk['error'])
        resolved.append(_lk)

    primary, link = lines[0], resolved[0]

    sku_id = body.sku_id or (primary.get("sku_code") or "") or link['variant_sku']
    product_name = body.product_name or (primary.get("product_name") or "") or link['product_name']
    variation = body.variation or (primary.get("variant") or "") or link['variation']
    quantity = body.quantity or sum(int(ln.get("qty") or 0) for ln in lines) or 1

    price_final = body.price_final or float(primary.get("price") or 0) or link['harga_jual']
    price_original = body.price_original or price_final

    now = _now()
    # tanggal bisnis pesanan = jam dinding WIB (lihat catatan `_now_wib_wall`)
    order_wall = _now_wib_wall()
    new_id = str(uuid.uuid4())
    order_ref = body.order_id or f"MAN-{order_wall.strftime('%Y%m%d')}-{new_id[:6].upper()}"

    # ── M10: reservasi stok saat order dibuat — PER BARIS (K-8b) ──────────────
    items_list: list = []
    reserved_rows, reserved_qty = [], 0.0
    try:
        for _i, (_ln, _lk) in enumerate(zip(lines, resolved)):
            _qty = quantity if flat_mode else int(_ln.get('qty') or 0)
            _price = float(_ln.get('price') or 0) or (price_final if _i == 0 else 0.0) \
                or _lk['harga_jual']
            _row = {
                'sku_code':      (_ln.get('sku_code') or _lk['variant_sku'] or ''),
                'product_name':  (_ln.get('product_name') or _lk['product_name'] or ''),
                'qty':           _qty,
                'price':         _price,
                'variant':       (_ln.get('variant') or _lk['variation'] or ''),
                # tautan master per baris — diisi SERVER, tak bisa dikarang klien
                'catalog_item_id':    _lk['catalog_item_id'],
                'variant_id':         _lk['variant_id'],
                'variant_sku':        _lk['variant_sku'],
                'fg_material_id':     _lk['fg_material_id'],
                'model_id':           _lk['model_id'],
                'master_link_source': _lk['resolved_by'],
                'reserved_qty':       0.0,
                'reserved_rows':      [],
            }
            if body.reserve_stock and _qty > 0:
                try:
                    rsv = await _cstock.reserve_sellable(
                        db, _lk['fg_material_id'], _qty,
                        ref={'source': 'marketing_order_create', 'order_ref': order_ref,
                             'line': _i + 1},
                        actor={'id': user.get('id', ''), 'email': user.get('email', '')})
                except _ss.InsufficientStock as e:
                    _pre = _line_label(_i, _ln)
                    _who = _row['sku_code'] or _row['product_name'] or '—'
                    raise HTTPException(
                        409, (f'{_pre}: ' if _pre else '')
                        + f"Stok jual tidak cukup untuk {_who}: diminta {_qty}, "
                          f"tersedia {getattr(e, 'available', 0)}. "
                          'Order tidak dibuat supaya tidak terjadi overselling.') from None
                _row['reserved_rows'] = rsv['rows']
                _row['reserved_qty'] = rsv['reserved']
                reserved_rows.extend(rsv['rows'])
                reserved_qty += rsv['reserved']
            items_list.append(_row)
    except Exception:
        # ATOMIK — satu baris gagal ⇒ reservasi baris sebelumnya DILEPAS. Tanpa ini
        # order yang gagal meninggalkan "stok terpesan hantu": fisiknya ada, tak
        # pernah bisa dijual, dan tak ada dokumen yang menjelaskan kenapa.
        if reserved_rows:
            await _cstock.release_rows(db, reserved_rows)
        raise

    lines_amount = sum(float(r['price'] or 0) * int(r['qty'] or 0) for r in items_list)
    total_payment = body.total_payment or (lines_amount + (body.shipping_cost or 0)) \
        or (price_final * quantity + (body.shipping_cost or 0))
    revenue = total_payment - (body.fee_amount or 0)
    # ── 2026-08-13 — NAMA UANG KANONIK JUGA UNTUK PESANAN MANUAL ──────────────
    # Sebelum ini, pesanan yang diinput staf lewat layar TIDAK punya
    # `revenue_product` / `order_amount` / `revenue_gross` / `seller_discount_total`
    # — satu-satunya nama yang dibaca rekap harian turunan (F2), siklus (F5), dan
    # marjin. Akibat terukur: setiap pesanan hasil input layar menyumbang **Rp 0**
    # ke omzet, ke anggaran diskon, dan ke marjin, tanpa satu pun galat. Bentuk
    # dokumen yang berbeda per pintu masuk adalah cara paling senyap membuat satu
    # koleksi punya dua kebenaran.
    gross_before_discount = sum(
        float(r.get('price_original') or r.get('price') or 0) * int(r.get('qty') or 0)
        for r in items_list) or (price_original * quantity)
    seller_discount_total = max(0.0, gross_before_discount - lines_amount)
    for _r in items_list:
        # nama kanonik per baris (dibaca marjin & laporan), legacy `qty`/`price`
        # DIPERTAHANKAN supaya layar lama tidak berubah perilaku.
        _r['quantity'] = int(_r.get('qty') or 0)
        _r['sku_subtotal_after_discount'] = round(
            float(_r.get('price') or 0) * int(_r.get('qty') or 0), 2)
        _r['sku_subtotal_before_discount'] = round(
            float(_r.get('price_original') or _r.get('price') or 0) * int(_r.get('qty') or 0), 2)
        _r['sku_seller_discount'] = round(
            max(0.0, _r['sku_subtotal_before_discount'] - _r['sku_subtotal_after_discount']), 2)

    doc = {
        "id":              new_id,
        "order_id":        order_ref,
        "platform":        body.platform,
        "account_name":    body.account_name or body.platform,
        "product_name":    product_name,
        "sku_id":          sku_id,
        "variation":       variation,
        "items":           items_list,
        "quantity":        quantity,
        # K-8a — tautan master, diisi SERVER
        "catalog_item_id": link['catalog_item_id'],
        "variant_id":      link['variant_id'],
        "variant_sku":     link['variant_sku'],
        "fg_material_id":  link['fg_material_id'],
        "model_id":        link['model_id'],
        "master_link_source": link['resolved_by'],
        # K-8b — jumlah baris yang benar-benar tertaut & dipesan (audit)
        "linked_line_count": len(items_list),
        "multi_line_linked": len(items_list) > 1,
        # M10 — reservasi (gabungan SEMUA baris; rinciannya di `items[].reserved_rows`)
        "stock_reserved":   bool(reserved_rows),
        "reserved_qty":     reserved_qty,
        "reserved_rows":    reserved_rows,
        "reserved_at":      now if reserved_rows else None,
        "price_original":  price_original,
        "price_final":     price_final,
        "discount_seller": max(0.0, price_original - price_final) * quantity,
        "shipping_cost":   body.shipping_cost or 0,
        "total_payment":   total_payment,
        "fee_amount":      body.fee_amount or 0,
        "net_amount":      revenue,
        "revenue":         revenue,
        # nama uang KANONIK (dibaca rekap harian F2, siklus F5, marjin, laporan)
        "revenue_product":        round(lines_amount, 2),
        "order_amount":           round(total_payment, 2),
        "revenue_gross":          round(gross_before_discount, 2),
        "seller_discount_total":  round(seller_discount_total, 2),
        "platform_discount_total": 0.0,
        "order_channel":          "other",
        "payment_method":  body.payment_method or "",
        "status":          "new",
        "fulfillment_status": "pending_fulfillment",
        "courier":         body.courier or "",
        "tracking_number": body.tracking_number,
        "customer_name":   body.customer_name,
        "customer_phone":  body.customer_phone or "",
        "customer_address": body.customer_address or "",
        "city":            body.city or "",
        "note":            body.note or "",
        "order_date":      order_wall,
        "packed_date":     None,
        "shipped_date":    None,
        "delivered_date":  None,
        "cancelled_date":  None,
        "_source_type":    "manual_input",
        "created_by":      user.get("email", "system"),
        "created_at":      now,
        "updated_at":      now,
    }
    # F14 — LINGKUP TOKO benar-benar DITULIS. Penjaga di atas sudah menolak order
    # tanpa toko yang sah, tetapi `account_id`-nya dulu tidak pernah ikut disimpan:
    # yang tersimpan hanya `account_name` sebagai teks. Akibatnya setiap pesanan
    # hasil input layar menjadi baris YATIM — tidak muncul di layar yang difilter
    # per toko, tidak ikut rekap harian turunan, dan membuat gate MKS-1 merah.
    _scope.stamp_account(doc, _acc)
    try:
        await db.marketing_orders.insert_one(doc)
    except Exception:
        # jangan tinggalkan reservasi menggantung kalau penyimpanan gagal
        if reserved_rows:
            await _cstock.release_rows(db, reserved_rows)
        raise
    # cache stok item katalog ikut disegarkan supaya layar langsung jujur.
    # K-8b — SEMUA item katalog yang tersentuh, bukan hanya baris pertama.
    for _cid in {r.get('catalog_item_id') for r in items_list if r.get('catalog_item_id')}:
        try:
            it = await db.marketing_catalog_items.find_one({'id': _cid}, {'_id': 0})
            if it:
                await _cstock.sync_item_cache(db, it)
        except Exception:
            logger.exception('sync cache stok katalog setelah order gagal')
    # ── F2 — REKAP HARIAN IKUT DIHITUNG ULANG ────────────────────────────────
    # Rekap harian adalah TURUNAN dari pesanan. Pintu impor sudah memanggil hook
    # ini, pintu manual belum: pesanan yang diinput staf tidak pernah muncul di
    # omzet harian, jadi layar Input Sales & Dashboard menampilkan hari itu seolah
    # tidak ada penjualan. Kegagalan hitung ulang TIDAK membatalkan pesanan (barang
    # & reservasinya sudah sah), tetapi juga tidak boleh senyap.
    try:
        from core import marketing_daily_rollup as _rollup
        await _rollup.recompute_for_orders(db, [new_id],
                                           actor=user.get('email', 'manual_order'))
    except Exception:
        logger.exception('[order] rekap harian gagal dihitung ulang setelah order '
                         'manual dibuat order_id=%s account_id=%s tanggal=%s',
                         order_ref, doc.get('account_id'), now.date().isoformat())
    return serialize(doc)


@router.delete("/{order_id}")
async def delete_order(order_id: str, request: Request):
    """Hapus order — reservasi stoknya WAJIB dilepas lebih dulu.

    F10 — jalur ini yang paling berbahaya (dibuktikan
    `test_core_order_status_reservation.py` PC-3). Begitu dokumen order dihapus,
    `reserved_rows` — satu-satunya catatan *baris stok mana* yang dipesan — ikut
    hilang, jadi `reserved_quantity` yang tertahan di `rahaza_material_stock`
    menjadi **yatim**: tidak bisa dijual, tidak bisa dijelaskan, dan tidak bisa
    dipulihkan dengan aman tanpa membongkar seluruh koleksi. Itulah stok hantu.
    """
    await require_auth(request)
    db = get_db()

    order = await db.marketing_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        # Kompat: sebagian pemanggil mengirim `order_id` tampilan (mis. MAN-...).
        order = await db.marketing_orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")

    rel = await _release_for_delete(db, order, source="delete_order")
    await db.marketing_orders.delete_one({"id": order["id"]})
    # F2 — omzet hari itu WAJIB dihitung ulang sesudah pesanan hilang. Tanpa ini,
    # rekap harian tetap memuat uang dari pesanan yang sudah tidak ada, dan tidak
    # ada satu pun jejak yang menjelaskan selisihnya.
    try:
        from core import marketing_daily_rollup as _rollup
        from core.marketing_daily_rollup import order_date_key
        _d = order_date_key(order.get("order_date"))
        if order.get("account_id") and _d:
            await _rollup.recompute_pairs(db, [(order["account_id"], _d)],
                                          actor="delete_order")
    except Exception:
        logger.warning("[order] rekap harian GAGAL dihitung ulang sesudah pesanan "
                       "dihapus order=%s account=%s", order.get("order_id"),
                       order.get("account_id"), exc_info=True)
    return {"ok": True, "message": "Order deleted",
            "reservation_released": rel["released"]}


class StatusUpdateBody(BaseModel):
    status: str
    note: Optional[str] = None
    tracking_number: Optional[str] = None


@router.patch("/{order_id}/status")
async def update_order_status(
    order_id: str,
    body: StatusUpdateBody,
    request: Request
):
    """Ubah status satu order — **lewat SSOT** `core/order_status.apply_status`.

    F10: seluruh logika (stempel tanggal, pelepasan reservasi, penyelarasan
    `fulfillment_status`, penyegaran cache stok katalog, jejak audit) pindah ke
    `core/order_status.py` supaya jalur LAIN (bulk, webhook, hapus, batch packing)
    tidak bisa lagi berbeda perilaku. Sebelum ini, jalur inilah SATU-SATUNYA yang
    melepas reservasi — dan itu sebabnya bulk-batal membocorkan stok.
    """
    await require_auth(request)
    user = _get_user(request)
    db = get_db()

    order = await db.marketing_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, "Order not found")

    try:
        res = await _apply_status(
            db, order, body.status, user=user, note=body.note,
            tracking_number=body.tracking_number, source="api:patch")
    except InvalidOrderTransition as e:
        raise HTTPException(400, e.reason) from None

    return {"ok": True, "new_status": res["new_status"],
            "previous_status": res["previous_status"],
            "reservation_released": res["released"]}


class BulkStatusBody(BaseModel):
    order_ids: List[str]
    status: str
    note: Optional[str] = None


@router.post("/bulk-status")
async def bulk_update_status(body: BulkStatusBody, request: Request):
    """Ubah status BANYAK order — **lewat SSOT**, satu per satu.

    F10 — BUG UANG YANG DITUTUP DI SINI (dibuktikan
    `test_core_order_status_reservation.py` PC-2): dulu jalur ini memakai
    `update_many` sehingga status berubah **tanpa** melepas reservasi stok.
    Stok jual 25 → order 2 pcs → 23 → bulk-batal → **tetap 23 selamanya**.
    Barangnya ada di gudang, sistem tidak mau menjualnya lagi, dan tidak ada
    dokumen yang menjelaskan kenapa. Tombolnya TERPAKAI di UI ("Order Terpadu"
    → pilihan "Batal"), jadi membatalkan 20 order = 20 reservasi bocor.

    Sekarang: satu panggilan `apply_status` per order (tidak ada jalan pintas
    `update_many`), dan kegagalan per-order **dilaporkan** — bukan ditelan —
    supaya staf tahu order mana yang tidak berubah dan kenapa.
    """
    await require_auth(request)
    user = _get_user(request)
    db = get_db()

    if body.status not in ORDER_STATUSES:
        raise HTTPException(400, f"Invalid status: {body.status}")

    updated, failed, released_total = [], [], 0.0
    for oid in (body.order_ids or []):
        order = await db.marketing_orders.find_one({"id": oid}, {"_id": 0})
        if not order:
            failed.append({"order_id": oid, "reason": "Order tidak ditemukan."})
            continue
        try:
            res = await _apply_status(db, order, body.status, user=user, note=body.note,
                                     source="api:bulk")
        except InvalidOrderTransition as e:
            failed.append({"order_id": oid, "order_ref": order.get("order_id"),
                           "reason": e.reason})
            continue
        except Exception as e:  # noqa: BLE001 — satu order gagal tak boleh menggagalkan sisanya
            logger.exception("bulk-status gagal untuk order %s", oid)
            failed.append({"order_id": oid, "order_ref": order.get("order_id"),
                           "reason": f"Gagal diproses: {e}"})
            continue
        updated.append(oid)
        released_total += res["released"]

    return {"ok": not failed, "updated_count": len(updated), "updated_ids": updated,
            "reservation_released": round(released_total, 4),
            "failed_count": len(failed), "failed": failed}
