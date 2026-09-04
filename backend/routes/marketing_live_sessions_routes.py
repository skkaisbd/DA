"""
Live Session Module — Backend Routes
Phase 3 Week 7: Manage live streaming session performance data
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query
from database import get_db
from core import marketing_live_fields as _LF
from core import marketing_live_products as _LP
from auth import require_auth
# F6 (sesi #9) — daftar & ringkasan WAJIB berlingkup toko (core/marketing_account_scope).
from core import marketing_account_scope as _scope
import random

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/live", tags=["marketing-live"])

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

def _get_user(request: Request) -> dict:
    return getattr(request.state, "user", {}) or {}

# ── Seed Demo Data ──
async def seed_live_if_empty():
    """Auto-seed realistic live session data if collection is empty."""
    db = get_db()
    if await db.marketing_live_sessions.count_documents({}) > 0:
        return
    
    # F14 — sesi live demo dulu hanya menyimpan `host_name` sebagai TEKS dan
    # tidak punya `account_id`/`host_id` (18/18 kosong). Akibatnya omzet live tidak
    # bisa dipertanggungjawabkan ke toko mana pun, dan jam kerja host tidak bisa
    # dihubungkan ke sesinya. Sekarang keduanya diambil dari master.
    from core import marketing_account_scope as _scope
    from core.marketing_master_seed import ensure_demo_hosts
    _accounts = await _scope.seed_account_pool(db)
    await ensure_demo_hosts(db)
    _hosts = await db.marketing_livehosts.find(
        {}, {"_id": 0, "id": 1, "name": 1, "assigned_account_ids": 1}).to_list(100)
    
    live_records = []
    for i in range(18):  # 18 live sessions
        account = random.choice(_accounts)
        platform = account.get("platform", "shopee")
        # host yang di-assign ke akun ini; kalau master host masih kosong, sesi
        # tetap dibuat TANPA host (jujur) — bukan diberi nama karangan.
        _cand = [h for h in _hosts
                 if account["id"] in (h.get("assigned_account_ids") or [])] or _hosts
        host_doc = random.choice(_cand) if _cand else None
        host = (host_doc or {}).get("name", "")
        date = _now() - timedelta(days=random.randint(1, 45))
        
        duration_min = random.randint(30, 180)
        peak_viewers = random.randint(100, 3000)
        total_viewers = int(peak_viewers * random.uniform(1.5, 4))
        likes = int(total_viewers * random.uniform(0.3, 0.8))
        comments = int(total_viewers * random.uniform(0.1, 0.4))
        shares = int(total_viewers * random.uniform(0.02, 0.1))
        
        orders = int(peak_viewers * random.uniform(0.05, 0.2))
        revenue = orders * random.uniform(50000, 250000)
        
        engagement_rate = ((likes + comments + shares) / total_viewers * 100) if total_viewers > 0 else 0
        conversion_rate = (orders / total_viewers * 100) if total_viewers > 0 else 0
        
        live_records.append({
            "id": str(uuid.uuid4()),
            "platform": platform,
            "account_id": account["id"],
            "account_name": account.get("account_name", ""),
            "host_id": (host_doc or {}).get("id"),
            "host_name": host,
            "title": f"Live Shopping {random.choice(['Fashion', 'Beauty', 'Accessories'])} - {date.strftime('%b %d')}",
            "session_date": date,
            "duration_minutes": duration_min,
            "peak_viewers": peak_viewers,
            "total_viewers": total_viewers,
            "likes": likes,
            "comments": comments,
            "shares": shares,
            "orders": orders,
            "revenue": round(revenue, 2),
            "engagement_rate": round(engagement_rate, 2),
            "conversion_rate": round(conversion_rate, 2),
            "products_featured": random.randint(5, 20),
            "status": "completed",
            "notes": [],
            "_seed_origin": True,
            "created_by": "system",
            "created_at": date,
            "updated_at": date
        })
    
    if live_records:
        await db.marketing_live_sessions.insert_many(live_records)
        try:
            await db.marketing_live_sessions.create_index("id", unique=True, sparse=True)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        try:
            await db.marketing_live_sessions.create_index("platform")
            await db.marketing_live_sessions.create_index("host_name")
            await db.marketing_live_sessions.create_index("session_date")
            await db.marketing_live_sessions.create_index("status")
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        logger.info(f"[seed] Inserted {len(live_records)} live session records")

# ── Endpoints ──

@router.get("/summary")
async def live_summary(request: Request,
                      account_id: Optional[str] = Query(None)):
    user = await require_auth(request)
    db = get_db()
    await seed_live_if_empty()

    # F14/F16 — SSOT nama field: `core.marketing_live_fields`.
    # Sebelum ini pipeline menjumlahkan `$gmv`/`$total_orders`/`$cr_rate` yang
    # TIDAK PERNAH ADA di koleksi (penulisnya memakai revenue/orders/
    # conversion_rate) ⇒ kartu "Total Revenue" menampilkan Rp 0 tepat di atas
    # tabel yang penuh angka puluhan juta. Layar yang membantah dirinya sendiri.
    _sm = await _scope.scope_filter(db, user,
                                    {"account_id": account_id} if account_id else None)
    _pre = [{"$match": _sm}] if _sm else []
    pipeline = _pre + [
        {"$group": {
            "_id": None,
            "total_sessions": {"$sum": 1},
            "total_revenue": {"$sum": _LF.REVENUE},
            "total_orders": {"$sum": _LF.ORDERS},
            "total_viewers": {"$sum": _LF.VIEWERS},
            "total_peak_viewers": {"$sum": _LF.PEAK_VIEWERS},
            "avg_conversion": {"$avg": _LF.CONVERSION},
            "avg_engagement": {"$avg": _LF.ENGAGEMENT},
        }}
    ]
    
    result = await db.marketing_live_sessions.aggregate(pipeline).to_list(1)
    stats = result[0] if result else {
        "total_sessions": 0, "total_revenue": 0, "total_orders": 0,
        "total_viewers": 0, "avg_conversion": 0
    }
    
    # By platform
    platform_pipeline = _pre + [
        {"$group": {
            "_id": "$platform",
            "sessions": {"$sum": 1},
            "revenue": {"$sum": _LF.REVENUE},
            "viewers": {"$sum": _LF.VIEWERS}
        }}
    ]
    by_platform = {}
    async for doc in db.marketing_live_sessions.aggregate(platform_pipeline):
        by_platform[doc["_id"]] = {
            "sessions": doc["sessions"],
            "revenue": doc["revenue"],
            "viewers": doc["viewers"]
        }
    
    # Top hosts
    host_pipeline = _pre + [
        {"$group": {
            "_id": "$host_name",
            "sessions": {"$sum": 1},
            "revenue": {"$sum": _LF.REVENUE}
        }},
        {"$sort": {"revenue": -1}},
        {"$limit": 5}
    ]
    top_hosts = []
    async for doc in db.marketing_live_sessions.aggregate(host_pipeline):
        top_hosts.append({"host": doc["_id"], "sessions": doc["sessions"], "revenue": doc["revenue"]})
    
    return success_response(data={
        "total_sessions": stats["total_sessions"],
        "total_revenue": stats["total_revenue"],
        "total_orders": stats["total_orders"],
        "total_viewers": stats["total_viewers"],
        "total_peak_viewers": stats.get("total_peak_viewers", 0),
        "avg_engagement_rate": round(stats.get("avg_engagement") or 0, 2),
        "avg_conversion_rate": round(stats.get("avg_conversion") or 0, 2),
        "by_platform": by_platform,
        "top_hosts": top_hosts
    })

@router.get("/sessions")
async def list_sessions(
    request: Request,
    account_id: Optional[str] = Query(None, description="F14 — filter per toko"),
    host_id: Optional[str] = Query(None),
    platform: Optional[str] = Query(None),
    host: Optional[str] = Query(None, description="kompatibilitas: nama host"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=10, le=100)
):
    user = await require_auth(request)
    db = get_db()
    await seed_live_if_empty()

    query = {}
    if account_id:
        query["account_id"] = account_id
    else:
        query = await _scope.scope_filter(db, user, query)
    if host_id:
        query["host_id"] = host_id
    if platform:
        query["platform"] = platform
    if host:
        query["host_name"] = host

    total = await db.marketing_live_sessions.count_documents(query)
    skip = (page - 1) * page_size
    
    sessions = await db.marketing_live_sessions.find(query).sort("session_date", -1).skip(skip).limit(page_size).to_list(page_size)

    # F18#3 — ringkasan rincian produk untuk SELURUH halaman dalam SATU agregasi.
    # (20 baris × 1 kueri = kolom "Rincian" yang pertama kali dihapus orang saat
    # tabelnya melambat; itu sebabnya digabung di sini.)
    await _lp_ready(db)
    _sum = await _LP.summary_for_sessions(db, [s.get("id") for s in sessions])
    for s in sessions:
        agg = _sum.get(s.get("id")) or {}
        s_rev = _LP.num(s.get("revenue") or s.get("gmv"))
        det_rev = _LP.num(agg.get("total_revenue"))
        s["products_detail"] = {
            "lines_count": agg.get("lines_count", 0),
            "total_units": agg.get("total_units", 0),
            "total_revenue": round(det_rev, 2),
            "unallocated_revenue": round(max(s_rev - det_rev, 0.0), 2),
            "coverage_pct": round(det_rev / s_rev * 100, 1) if s_rev else 0.0,
            "over_allocated": bool(s_rev > 0 and det_rev > s_rev * (1 + _LP.OVER_TOLERANCE)),
        }

    return success_response(
        data={"sessions": serialize(sessions)},
        pagination={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    )

@router.get("/performance-trend")
async def performance_trend(
    request: Request,
    days: int = Query(30, ge=7, le=90),
    account_id: Optional[str] = Query(None)
):
    user = await require_auth(request)
    db = get_db()
    await seed_live_if_empty()

    start_dt = _now() - timedelta(days=days)

    _m = _LF.date_match("session_date", start_dt, _now())
    if account_id:
        _m = {"$and": [_m, {"account_id": account_id}]}
    else:
        _vis = await _scope.visible_account_ids(db, user)
        if _vis is not None:
            _m = {"$and": [_m, {"account_id": {"$in": _vis}}]}
    pipeline = [
        {"$match": _m},
        {"$group": {
            "_id": _LF.date_as_string("session_date"),
            "sessions": {"$sum": 1},
            "revenue": {"$sum": _LF.REVENUE},
            "viewers": {"$sum": _LF.VIEWERS}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    trend = []
    async for doc in db.marketing_live_sessions.aggregate(pipeline):
        trend.append({
            "date": doc["_id"],
            "sessions": doc["sessions"],
            "revenue": doc["revenue"],
            "viewers": doc["viewers"]
        })
    
    return success_response(data={"trend": trend}, metadata={"days": days})


# ══════════════════════════════════════════════════════════════════════════════
# F16 — CRUD SESI LIVE (sebelumnya TIDAK ADA SAMA SEKALI)
# ══════════════════════════════════════════════════════════════════════════════
# Audit 2026-08-11: berkas ini hanya punya endpoint GET, sehingga sesi live
# **tidak bisa dicatat lewat aplikasi**. Padahal sesi live adalah tempat
# bertemunya tiga hal yang harus bisa dipertanggungjawabkan: omzet toko, jam
# kerja host, dan performa produk yang dibawakan.
#
# Aturan yang ditegakkan di sini:
#   · `account_id` WAJIB (F14) — omzet live milik satu toko.
#   · `host_id` WAJIB dan host itu harus SUDAH di-assign ke toko tersebut,
#     supaya jam kerja & bayarannya tidak dibebankan ke toko yang tidak
#     memakainya (keputusan owner; dijaga gate INV-MKTSCOPE MKS-23).
#   · engagement/conversion/AOV DIHITUNG server (`core.marketing_live_fields`),
#     bukan diketik — nama fieldnya pun satu, karena dua ejaan untuk satu angka
#     adalah asal cacat "Total Revenue Rp 0" yang baru saja diperbaiki.
from fastapi import HTTPException                     # noqa: E402
from pydantic import BaseModel, Field as _PField      # noqa: E402
from typing import List                               # noqa: E402

LIVE_STATUSES = ("scheduled", "live", "completed", "cancelled")

# Indeks rincian produk dibuat sekali per proses (idempoten, tapi tidak perlu
# dipanggil di setiap request).
_LP_INDEXES_READY = False


async def _lp_ready(db):
    global _LP_INDEXES_READY
    if not _LP_INDEXES_READY:
        await _LP.ensure_indexes(db)
        _LP_INDEXES_READY = True
    # Sesi demo diberi rincian sekali (lihat _LP.seed_demo_products) supaya layar
    # "Produk Terlaris saat Live" tidak tampak rusak di basis data baru.
    await _LP.seed_demo_products(db)


class LiveProductLineIn(BaseModel):
    """Satu produk yang dibawakan/laku pada satu sesi live.

    `catalog_item_id` — produk DIPILIH dari katalog toko, tidak diketik. Nama,
    SKU, kategori, dan HPP diambil dari master supaya "produk terlaris" tidak
    terpecah karena beda ejaan.
    """
    id: Optional[str] = None
    catalog_item_id: str
    units_sold: int = _PField(0, ge=0)
    revenue: float = _PField(0, ge=0)
    orders: int = _PField(0, ge=0)
    notes: Optional[str] = ""


class LiveProductLineUpdate(BaseModel):
    catalog_item_id: Optional[str] = None
    units_sold: Optional[int] = _PField(None, ge=0)
    revenue: Optional[float] = _PField(None, ge=0)
    orders: Optional[int] = _PField(None, ge=0)
    notes: Optional[str] = None


class LiveProductsReplaceIn(BaseModel):
    products: List[LiveProductLineIn] = []


class LiveSessionIn(BaseModel):
    account_id: str
    host_id: str
    session_date: str
    title: str
    start_time: Optional[str] = ""
    duration_minutes: int = _PField(0, ge=0)
    peak_viewers: int = _PField(0, ge=0)
    total_viewers: int = _PField(0, ge=0)
    likes: int = _PField(0, ge=0)
    comments: int = _PField(0, ge=0)
    shares: int = _PField(0, ge=0)
    orders: int = _PField(0, ge=0)
    revenue: float = _PField(0, ge=0)
    units_sold: int = _PField(0, ge=0)
    products_featured: int = _PField(0, ge=0)
    status: Optional[str] = "completed"
    notes_text: Optional[str] = ""
    # F18#3 — rincian produk bisa dikirim bersama sesinya (satu form, satu simpan).
    products: Optional[List[LiveProductLineIn]] = None


class LiveSessionUpdate(BaseModel):
    account_id: Optional[str] = None
    host_id: Optional[str] = None
    session_date: Optional[str] = None
    title: Optional[str] = None
    start_time: Optional[str] = None
    duration_minutes: Optional[int] = _PField(None, ge=0)
    peak_viewers: Optional[int] = _PField(None, ge=0)
    total_viewers: Optional[int] = _PField(None, ge=0)
    likes: Optional[int] = _PField(None, ge=0)
    comments: Optional[int] = _PField(None, ge=0)
    shares: Optional[int] = _PField(None, ge=0)
    orders: Optional[int] = _PField(None, ge=0)
    revenue: Optional[float] = _PField(None, ge=0)
    units_sold: Optional[int] = _PField(None, ge=0)
    products_featured: Optional[int] = _PField(None, ge=0)
    status: Optional[str] = None
    notes_text: Optional[str] = None
    # Dikirim = GANTI seluruh rincian sesi ini. Tidak dikirim = rincian dibiarkan.
    products: Optional[List[LiveProductLineIn]] = None


def _parse_live_date(raw: str) -> datetime:
    from core.marketing_import_engine import parse_date
    d, err = parse_date(raw)
    if err or d is None:
        raise HTTPException(400, f"Tanggal sesi tidak dikenali: {err or raw}")
    return d


@router.get("/sessions/{session_id}")
async def get_live_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.marketing_live_sessions.find_one({"id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Sesi live tidak ditemukan")
    # F18#3 — rincian produk ikut dikirim supaya layar tidak perlu dua panggilan
    # (dan tidak ada dua versi angka rekonsiliasi di JS).
    lines = await _LP.list_lines(db, session_id)
    return success_response(data={**serialize(doc),
                                 "products": serialize(lines),
                                 "products_reconciliation": _LP.reconcile(doc, lines)})


@router.post("/sessions", status_code=201)
async def create_live_session(body: LiveSessionIn, request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    from core import marketing_account_scope as _scope

    account = await _scope.require_account(db, body.account_id)
    host = await _scope.assert_host_assigned(db, body.host_id, account["id"])
    if body.status and body.status not in LIVE_STATUSES:
        raise HTTPException(400, f"status harus salah satu: {', '.join(LIVE_STATUSES)}")

    doc = body.dict()
    doc.pop("account_id", None)
    note = doc.pop("notes_text", "") or ""
    product_lines = doc.pop("products", None)
    doc["id"] = str(uuid.uuid4())
    doc["session_date"] = _parse_live_date(body.session_date)
    doc["host_id"] = host["id"]
    doc["host_name"] = host.get("name", "")
    doc["notes"] = ([{"id": str(uuid.uuid4()), "text": note,
                      "at": _now().isoformat(),
                      "by": user.get("email", "system")}] if note else [])
    _scope.stamp_account(doc, account)
    _LF.compute_derived(doc)
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    doc["created_by"] = user.get("email", "system")
    await db.marketing_live_sessions.insert_one(dict(doc))
    doc.pop("_id", None)
    # F18#3 — rincian produk disimpan setelah sesinya ada (butuh session_id).
    lines = []
    if product_lines:
        await _lp_ready(db)
        try:
            lines = await _LP.replace_lines(db, doc,
                                            [dict(p) for p in product_lines],
                                            user_email=user.get("email", "system"))
        except HTTPException:
            # Sesi tanpa rincian lebih baik daripada sesi hantu: batalkan sesinya
            # supaya pengguna tidak menyimpan dua kali saat memperbaiki rinciannya.
            await db.marketing_live_sessions.delete_one({"id": doc["id"]})
            raise
    return success_response(data={**serialize(doc), "products": serialize(lines),
                                 "products_reconciliation": _LP.reconcile(doc, lines)})


@router.put("/sessions/{session_id}")
async def update_live_session(session_id: str, body: LiveSessionUpdate,
                              request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    from core import marketing_account_scope as _scope

    existing = await db.marketing_live_sessions.find_one({"id": session_id},
                                                        {"_id": 0})
    if not existing:
        raise HTTPException(404, "Sesi live tidak ditemukan")

    upd = {k: v for k, v in body.dict().items() if v is not None}
    note = upd.pop("notes_text", None)
    product_lines = upd.pop("products", None)
    account_id = upd.pop("account_id", None) or existing.get("account_id")
    account = await _scope.require_account(db, account_id)
    if "host_id" in upd or account_id != existing.get("account_id"):
        host = await _scope.assert_host_assigned(
            db, upd.get("host_id") or existing.get("host_id"), account["id"])
        upd["host_id"] = host["id"]
        upd["host_name"] = host.get("name", "")
    if "status" in upd and upd["status"] not in LIVE_STATUSES:
        raise HTTPException(400, f"status harus salah satu: {', '.join(LIVE_STATUSES)}")
    if "session_date" in upd:
        upd["session_date"] = _parse_live_date(upd["session_date"])

    merged = {**existing, **upd}
    _scope.stamp_account(upd, account)
    _LF.compute_derived(merged)
    for k in ("engagement_rate", "conversion_rate", "aov"):
        upd[k] = merged[k]
    if note:
        notes = list(existing.get("notes") or [])
        notes.append({"id": str(uuid.uuid4()), "text": note,
                      "at": _now().isoformat(), "by": user.get("email", "system")})
        upd["notes"] = notes
    upd["updated_at"] = _now()
    upd["updated_by"] = user.get("email", "system")
    await db.marketing_live_sessions.update_one({"id": session_id}, {"$set": upd})
    merged_doc = {**existing, **upd}
    # F18#3 — rincian produk mengikuti sesi yang sudah diperbarui (toko/host bisa
    # berubah, dan baris rincian harus ikut lingkup barunya).
    await _lp_ready(db)
    if product_lines is not None:
        await _LP.replace_lines(db, merged_doc, [dict(p) for p in product_lines],
                                user_email=user.get("email", "system"))
    lines = await _LP.list_lines(db, session_id)
    return success_response(data={**serialize(merged_doc),
                                 "products": serialize(lines),
                                 "products_reconciliation": _LP.reconcile(merged_doc, lines)})


@router.delete("/sessions/{session_id}")
async def delete_live_session(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_live_sessions.delete_one({"id": session_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Sesi live tidak ditemukan")
    # Cascade: rincian produk tanpa sesi = baris yatim yang tetap terhitung di
    # laporan "produk terlaris" padahal sesinya sudah tidak ada.
    removed = await _LP.delete_for_session(db, session_id)
    return {"success": True, "message": "Sesi live dihapus",
            "product_lines_deleted": removed}


# ══════════════════════════════════════════════════════════════════════════════
# F18#3 — RINCIAN PRODUK PER SESI LIVE (sebelumnya TIDAK ADA JALANNYA)
# ══════════════════════════════════════════════════════════════════════════════
# `GET /live/analytics/product-performance` sudah lama membaca `products[]`, tapi
# tidak ada endpoint/impor/seed yang bisa mengisinya ⇒ laporan "produk terlaris
# saat live" selalu kosong. Endpoint di bawah adalah jalan resminya; aturan &
# rekonsiliasinya ada di SSOT `core/marketing_live_products.py` supaya layar,
# impor, dan analitik memakai definisi yang sama.
async def _load_session_or_404(db, session_id: str) -> dict:
    doc = await db.marketing_live_sessions.find_one({"id": session_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Sesi live tidak ditemukan")
    return doc


@router.get("/sessions/{session_id}/products")
async def list_session_products(session_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _lp_ready(db)
    session = await _load_session_or_404(db, session_id)
    lines = await _LP.list_lines(db, session_id)
    return success_response(
        data={"products": serialize(lines),
              "reconciliation": _LP.reconcile(session, lines)},
        metadata={"session_id": session_id, "session_title": session.get("title"),
                  "account_id": session.get("account_id"),
                  "account_name": session.get("account_name")})


@router.put("/sessions/{session_id}/products")
async def replace_session_products(session_id: str, body: LiveProductsReplaceIn,
                                   request: Request):
    """Ganti SELURUH rincian sesi (dipakai tombol simpan pada dialog)."""
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    await _lp_ready(db)
    session = await _load_session_or_404(db, session_id)
    lines = await _LP.replace_lines(db, session, [dict(p) for p in body.products],
                                    user_email=user.get("email", "system"))
    return success_response(data={"products": serialize(lines),
                                  "reconciliation": _LP.reconcile(session, lines)})


@router.post("/sessions/{session_id}/products", status_code=201)
async def add_session_product(session_id: str, body: LiveProductLineIn,
                              request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    await _lp_ready(db)
    session = await _load_session_or_404(db, session_id)
    line = await _LP.add_line(db, session, body.dict(),
                              user_email=user.get("email", "system"))
    lines = await _LP.list_lines(db, session_id)
    return success_response(data={"product": serialize(line),
                                  "reconciliation": _LP.reconcile(session, lines)})


@router.put("/sessions/{session_id}/products/{line_id}")
async def update_session_product(session_id: str, line_id: str,
                                 body: LiveProductLineUpdate, request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    await _lp_ready(db)
    session = await _load_session_or_404(db, session_id)
    line = await _LP.update_line(db, session, line_id, body.dict(),
                                 user_email=user.get("email", "system"))
    lines = await _LP.list_lines(db, session_id)
    return success_response(data={"product": serialize(line),
                                  "reconciliation": _LP.reconcile(session, lines)})


@router.delete("/sessions/{session_id}/products/{line_id}")
async def delete_session_product(session_id: str, line_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    await _lp_ready(db)
    session = await _load_session_or_404(db, session_id)
    await _LP.delete_line(db, session_id, line_id)
    lines = await _LP.list_lines(db, session_id)
    return {"success": True, "message": "Baris rincian dihapus",
            "reconciliation": _LP.reconcile(session, lines)}


@router.post("/sessions/{session_id}/products/sync-session-totals")
async def sync_session_totals(session_id: str, request: Request):
    """Samakan omzet/order/unit sesi dengan rincian produknya.

    Sengaja tombol terpisah: total sesi biasanya berasal dari laporan resmi
    marketplace. Kalau ditimpa otomatis setiap kali rincian berubah, angka acuan
    itu hilang tanpa jejak dan tidak ada yang tahu mana yang benar.
    """
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    await _lp_ready(db)
    session = await _load_session_or_404(db, session_id)
    out = await _LP.sync_session_totals(db, session,
                                        user_email=user.get("email", "system"))
    return success_response(data=out)


@router.get("/statuses")
async def live_reference_lists(request: Request):
    """Daftar acuan status sesi dari SERVER (layar tidak menyalin sendiri)."""
    await require_auth(request)
    return {"ok": True, "statuses": list(LIVE_STATUSES)}
