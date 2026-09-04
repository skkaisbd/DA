"""
Returns & Refunds Tracking Module — Backend Routes
Phase 3 Week 13: Tracking retur dan refund produk
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from database import get_db
from utils.counters import gen_prefixed_number
from auth import require_auth
# F6 (sesi #9) — daftar & ringkasan WAJIB berlingkup toko (core/marketing_account_scope).
from core import marketing_account_scope as _scope
from core import returns_bridge as _rb
from routes.shared import require_portal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/returns", tags=["marketing-returns"])

RETURN_REASONS = [
    "produk_tidak_sesuai",
    "ukuran_salah",
    "produk_cacat",
    "warna_berbeda",
    "tidak_sesuai_ekspektasi",
    "salah_pesan",
    "terlambat_sampai",
    "rusak_saat_pengiriman",
    "lainnya"
]

REASON_LABELS = {
    "produk_tidak_sesuai": "Produk Tidak Sesuai Deskripsi",
    "ukuran_salah": "Ukuran Salah/Tidak Sesuai",
    "produk_cacat": "Produk Cacat/Rusak",
    "warna_berbeda": "Warna Berbeda dari Gambar",
    "tidak_sesuai_ekspektasi": "Tidak Sesuai Ekspektasi",
    "salah_pesan": "Salah Pesan",
    "terlambat_sampai": "Terlambat Sampai",
    "rusak_saat_pengiriman": "Rusak Saat Pengiriman",
    "lainnya": "Lainnya"
}

RETURN_STATUSES = ["pending", "approved", "rejected", "completed", "cancelled"]
REFUND_TYPES = ["full_refund", "partial_refund", "exchange", "no_refund"]
PLATFORMS = ["shopee", "tiktok", "tokopedia", "instagram"]
COURIERS = ["jnt", "spx", "sicepat", "jne", "anteraja", "ninja", "grab", "gojek"]

# ── Helpers ───────────────────────────────────────────────────────────────────
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

# ── Seed ─────────────────────────────────────────────────────────────────────
async def seed_returns_if_empty():
    db = get_db()
    if await db.marketing_returns.count_documents({}) > 0:
        return

    import random
    
    products = [
        "Gamis Daluna Basic", "Khimar Syari Premium", "Tunik Busui Friendly",
        "Set Gamis + Khimar", "Outer Cardigan", "Rok Plisket Panjang"
    ]
    
    couriers_list = ["jnt", "spx", "sicepat"]
    
    return_templates = [
        {"reason": "ukuran_salah", "detail": "Terlalu kecil, size XL seperti M", "price": 125000},
        {"reason": "produk_tidak_sesuai", "detail": "Warna berbeda dari foto", "price": 98000},
        {"reason": "produk_cacat", "detail": "Ada bolong di bagian jahitan", "price": 150000},
        {"reason": "warna_berbeda", "detail": "Lebih gelap dari gambar", "price": 89000},
        {"reason": "tidak_sesuai_ekspektasi", "detail": "Bahan lebih tipis dari yang diharapkan", "price": 110000},
    ]
    
    # Gunakan platform accounts nyata jika ada
    real_accounts = await db.marketing_platform_accounts.find(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1}
    ).to_list(50)
    seed_accounts = [(a["id"], a["account_name"], a["platform"]) for a in real_accounts] if real_accounts else [
        (None, "DA Official Shopee", "shopee"), (None, "Daluna TikTok Shop", "tiktok")
    ]

    # F14 — retur demo dulu memakai nomor pesanan karangan `ORD-######`
    # (30/30 yatim), sehingga tombol "lihat pesanan" dari retur tidak pernah
    # menemukan apa pun dan nilai refund tak bisa dicek ke transaksinya.
    _orders = await db.marketing_orders.find(
        {}, {"_id": 0, "order_id": 1, "account_id": 1, "account_name": 1,
             "platform": 1, "product_name": 1, "price_final": 1,
             "catalog_item_id": 1}).to_list(500)

    entries = []
    base = _now()
    
    for i in range(30):
        day_offset = random.randint(-30, 0)
        return_date = base + timedelta(days=day_offset)
        
        template = random.choice(return_templates)
        status = random.choice(["pending", "approved", "approved", "completed", "rejected"])
        refund_type = random.choice(["full_refund", "partial_refund", "exchange"]) if status == "approved" else "no_refund"
        # Retur SELALU menempel ke order yang ada. Kalau order demo belum ada,
        # akunnya dipakai apa adanya dan nomor pesanan dikosongkan — lebih jujur
        # daripada mengarang nomor yang tidak menunjuk apa pun.
        _ord = random.choice(_orders) if _orders else None
        if _ord:
            acc_id = _ord.get("account_id")
            acc_name = _ord.get("account_name", "")
            acc_platform = _ord.get("platform", "")
        else:
            acc_id, acc_name, acc_platform = random.choice(seed_accounts)

        entries.append({
            "id": str(uuid.uuid4()),
            "date": return_date.date().isoformat(),
            "order_id": (_ord or {}).get("order_id", ""),
            "catalog_item_id": (_ord or {}).get("catalog_item_id"),
            "platform": acc_platform,
            "account_id": acc_id,
            "account_name": acc_name,
            "product": (_ord or {}).get("product_name") or random.choice(products),
            "price": float((_ord or {}).get("price_final") or template["price"]),
            "reason": template["reason"],
            "reason_label": REASON_LABELS.get(template["reason"], template["reason"]),
            "reason_detail": template["detail"],
            "courier": random.choice(couriers_list),
            "status": status,
            "refund_type": refund_type,
            "refund_amount": (float((_ord or {}).get("price_final") or template["price"])
                              if refund_type == "full_refund"
                              else float((_ord or {}).get("price_final") or template["price"]) * 0.7
                              if refund_type == "partial_refund" else 0),
            "appeal_status": "accepted" if status == "approved" else "rejected" if status == "rejected" else "pending",
            "appeal_result": "Disetujui" if status == "approved" else "Ditolak" if status == "rejected" else "Menunggu",
            "notes": "",
            "created_by": "system",
            "created_at": _now(),
            "updated_at": _now(),
        })
    
    if entries:
        await db.marketing_returns.insert_many(entries)
    logger.info(f"[marketing_returns] seeded {len(entries)} entries")

# ── Models ───────────────────────────────────────────────────────────────────
class ReturnIn(BaseModel):
    account_id: Optional[str] = None  # UUID dari marketing_platform_accounts
    account_name: Optional[str] = None
    date: str
    order_id: str
    # W4 (sesi #29) — KONDISI BARANG & JUMLAH yang kembali. Dua kolom inilah yang
    # membuat retur bisa langsung mengubah stok tanpa menebak:
    #   `item_condition` = Baik  → stok masuk zona jual (ZNA-FG)
    #   `item_condition` = Rusak → stok masuk karantina (ZNA-KARANTINA, tak dijual)
    item_condition: Optional[str] = "Baik"
    qty: Optional[int] = Field(default=1, ge=1)
    # F14 — `platform` TURUNAN dari akun, bukan diketik/dikirim layar.
    # Kalau boleh dikirim bebas, satu akun Shopee bisa punya baris
    # berplatform 'tiktok' dan laporan per platform ikut salah.
    platform: Optional[str] = None
    catalog_item_id: Optional[str] = None   # F15 — produk DIPILIH dari katalog
    product: Optional[str] = ""             # turunan dari item katalog
    price: float = Field(ge=0)
    reason: str
    reason_detail: str
    courier: str
    refund_type: Optional[str] = "full_refund"
    notes: Optional[str] = ""

class ReturnUpdate(BaseModel):
    item_condition: Optional[str] = None
    qty: Optional[int] = Field(default=None, ge=1)
    catalog_item_id: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    date: Optional[str] = None
    order_id: Optional[str] = None
    platform: Optional[str] = None
    product: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    reason: Optional[str] = None
    reason_detail: Optional[str] = None
    courier: Optional[str] = None
    status: Optional[str] = None
    refund_type: Optional[str] = None
    refund_amount: Optional[float] = Field(default=None, ge=0)
    appeal_status: Optional[str] = None
    appeal_result: Optional[str] = None
    notes: Optional[str] = None

# ── F15 — PRODUK DIPILIH DARI KATALOG TOKO, BUKAN DIKETIK ────────────────────
# Sebelum ini `product` adalah teks bebas. Akibatnya "Gamis Daluna Basic" dan
# "Gamis Daluna basic" menjadi DUA produk di laporan, dan pertanyaan "produk mana
# yang paling banyak diretur / paling buruk ulasannya" tidak bisa dijawab karena
# angkanya terpecah. Sekarang layar mengirim `catalog_item_id`, dan nama produk
# serta SKU-nya diambil dari MASTER — tidak mungkin lagi beda ejaan.
async def _resolve_catalog_item(db, catalog_item_id: str, account_id: str) -> dict:
    """Item katalog WAJIB milik toko yang sama. Item toko lain ditolak, karena
    ulasan/retur toko A yang menunjuk produk toko B akan merusak dua laporan
    sekaligus tanpa terlihat."""
    item = await db.marketing_catalog_items.find_one({"id": catalog_item_id},
                                                     {"_id": 0})
    if not item:
        raise HTTPException(404, f"Item katalog '{catalog_item_id}' tidak ditemukan")
    if account_id and item.get("account_id") and item["account_id"] != account_id:
        raise HTTPException(400, "Item katalog itu bukan milik toko yang dipilih. "
                                 "Pilih produk dari katalog toko tersebut.")
    return item

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/reasons")
async def get_reasons(request: Request):
    await require_portal(request, "toko")  # RBAC read-guard (BUG-AUTH-1)
    return {"success": True, "reasons": [{"value": k, "label": v} for k, v in REASON_LABELS.items()]}

@router.get("/summary")
async def get_summary(request: Request):
    user = await require_auth(request)
    await seed_returns_if_empty()
    db = get_db()

    # F6 (sesi #9) — ringkasan retur WAJIB berlingkup toko: sebelumnya staf
    # pemegang satu toko melihat jumlah & nilai refund SEMUA toko.
    _s = await _scope.scope_filter(db, user, None)
    total = await db.marketing_returns.count_documents(_s)
    pending = await db.marketing_returns.count_documents({**_s, "status": "pending"})
    approved = await db.marketing_returns.count_documents({**_s, "status": "approved"})
    completed = await db.marketing_returns.count_documents({**_s, "status": "completed"})
    rejected = await db.marketing_returns.count_documents({**_s, "status": "rejected"})

    # Total refund amount
    pipeline_refund = [{"$match": _s},
                       {"$group": {"_id": None, "total_refund": {"$sum": "$refund_amount"}}}]
    refund_result = await db.marketing_returns.aggregate(pipeline_refund).to_list(1)
    total_refund = refund_result[0]["total_refund"] if refund_result else 0
    
    # By reason
    pipeline_reason = ([{"$match": _s}] if _s else []) + [
        {"$group": {"_id": "$reason", "count": {"$sum": 1}}}]
    by_reason_raw = await db.marketing_returns.aggregate(pipeline_reason).to_list(100)
    by_reason = {REASON_LABELS.get(r["_id"], r["_id"]): r["count"] for r in by_reason_raw if r["_id"]}

    return {
        "success": True,
        "data": {
            "total": total,
            "pending": pending,
            "approved": approved,
            "completed": completed,
            "rejected": rejected,
            "total_refund": total_refund,
            "by_reason": by_reason,
        }
    }

@router.get("")
async def list_returns(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    status: str = Query(default=""),
    platform: str = Query(default=""),
    reason: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    search: str = Query(default=""),
    account_id: str = Query(default=""),
):
    user = await require_auth(request)
    await seed_returns_if_empty()
    db = get_db()

    q = await _scope.scope_filter(db, user, None)
    if status:
        q["status"] = status
    if platform:
        q["platform"] = platform
    if reason:
        q["reason"] = reason
    if date_from:
        q.setdefault("date", {})["$gte"] = date_from
    if date_to:
        q.setdefault("date", {})["$lte"] = date_to
    if account_id:
        q["account_id"] = account_id
    if search:
        q["$or"] = [
            {"order_id": {"$regex": search, "$options": "i"}},
            {"product": {"$regex": search, "$options": "i"}},
            {"reason_detail": {"$regex": search, "$options": "i"}},
        ]

    total = await db.marketing_returns.count_documents(q)
    skip = (page - 1) * page_size
    items = await db.marketing_returns.find(q, {"_id": 0})\
                    .sort("date", -1).skip(skip).limit(page_size).to_list(page_size)
    
    return {
        "success": True,
        "data": serialize(items),
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }

@router.get("/credit-notes")
async def list_credit_notes_alias(request: Request):
    """List all credit notes — MOVED here to avoid /{return_id} conflict."""
    await require_auth(request)
    db = get_db()
    cns = await db.rahaza_credit_notes.find({}, {"_id": 0}).sort("issue_date", -1).to_list(500)
    return {"success": True, "data": serialize(cns)}


@router.get("/credit-notes/{cn_id}")
async def get_credit_note_alias(cn_id: str, request: Request):
    """Get credit note detail — MOVED here to avoid /{return_id} conflict."""
    await require_auth(request)
    db = get_db()
    cn = await db.rahaza_credit_notes.find_one({"id": cn_id}, {"_id": 0})
    if not cn:
        raise HTTPException(404, "Credit note not found")
    return {"success": True, "data": serialize(cn)}


@router.get("/{return_id}")
async def get_return(return_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    ret = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise HTTPException(404, "Return not found")
    return {"success": True, "data": serialize(ret)}

@router.post("")
async def create_return(body: ReturnIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    # ── F14 (perbaikan lanjutan) — LINGKUP TOKO & `platform` DARI MASTER ──────
    # Lihat catatan sama di `marketing_reviews_routes.create_review`: membuat
    # `platform` opsional tanpa mengganti sumbernya membuat SETIAP retur baru
    # tersimpan `platform: null`, dan laporan retur per platform (yang dipakai
    # menilai kurir & marketplace) kehilangan baris tanpa error.
    from core import marketing_account_scope as _scope
    account = await _scope.require_account(db, body.account_id)
    # F15 — produk berasal dari item katalog toko (bukan teks bebas).
    _item = None
    if getattr(body, "catalog_item_id", None):
        _item = await _resolve_catalog_item(db, body.catalog_item_id, account["id"])
    elif not (getattr(body, "product", "") or "").strip():
        raise HTTPException(400, "Produk wajib: pilih item dari katalog toko.")

    refund_amount = body.price if body.refund_type == "full_refund" else (body.price * 0.7) if body.refund_type == "partial_refund" else 0

    ret = {
        "id": str(uuid.uuid4()),
        "date": body.date,
        "order_id": body.order_id,
        "catalog_item_id": _item.get("id") if _item else None,
        "sku": _item.get("sku", "") if _item else "",
        "product": (_item.get("name") if _item else body.product) or "",
        "price": body.price,
        "qty": int(body.qty or 1),
        "item_condition": _rb.normalize_condition(body.item_condition),
        "reason": body.reason,
        "reason_label": REASON_LABELS.get(body.reason, body.reason),
        "reason_detail": body.reason_detail,
        "courier": body.courier,
        "status": "pending",
        "refund_type": body.refund_type,
        "refund_amount": refund_amount,
        "appeal_status": "pending",
        "appeal_result": "Menunggu",
        "notes": body.notes or "",
        "created_by": user.get("email", "unknown"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _scope.stamp_account(ret, account)      # account_id · account_name · platform
    await db.marketing_returns.insert_one(ret)
    ret.pop("_id", None)

    # ── W4 (sesi #29) — JEMBATAN OTOMATIS KE GUDANG + RESTOCK ─────────────────
    # Keputusan pemilik: retur yang dibuat di Marketing HARUS langsung muncul di
    # "Retur Fisik" gudang DAN langsung menambah stok sesuai kondisi barang.
    # Sebelum ini `wh_returns` = 0 dokumen selamanya (jembatannya manual & tak
    # pernah diklik), jadi barang retur hilang dari pembukuan stok.
    # Kegagalan TIDAK membatalkan pencatatan retur (uangnya nyata, harus tercatat)
    # tetapi WAJIB berjejak di `wh_sync_*` supaya tidak menggantung diam-diam.
    bridge = None
    try:
        bridge = await _rb.ensure_wh_return(db, ret, actor=user,
                                           condition=ret["item_condition"],
                                           auto_restock=True)
    except Exception as e:  # noqa: BLE001
        logger.error("[retur] jembatan Marketing→Gudang gagal untuk %s: %s", ret["id"], e)
        await db.marketing_returns.update_one({"id": ret["id"]}, {"$set": {
            "wh_sync_ok": False, "wh_sync_error": str(e)[:300], "wh_sync_at": _now(),
        }})
    fresh = await db.marketing_returns.find_one({"id": ret["id"]}, {"_id": 0})
    return {
        "success": True,
        "data": serialize(fresh or ret),
        "warehouse": {
            "wh_return_code": (fresh or {}).get("wh_return_code", ""),
            "restocked": bool((fresh or {}).get("wh_restocked")),
            "stock_effect": (fresh or {}).get("wh_stock_effect", ""),
            "location": (fresh or {}).get("wh_restock_location_code", ""),
            "message": (bridge or {}).get("message", ""),
        },
    }

@router.put("/{return_id}")
async def update_return(return_id: str, body: ReturnUpdate, request: Request):
    await require_auth(request)
    db = get_db()

    existing = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Return not found")

    upd = {k: v for k, v in body.dict().items() if v is not None}
    # F14 — `platform`/`account_name` selalu turunan master (lihat create_return).
    upd.pop("platform", None)
    upd.pop("account_name", None)
    if upd.get("account_id"):
        from core import marketing_account_scope as _scope
        _acc = await _scope.require_account(db, upd["account_id"])
        _scope.stamp_account(upd, _acc)
    if upd.get("catalog_item_id"):
        _it = await _resolve_catalog_item(
            db, upd["catalog_item_id"],
            upd.get("account_id") or existing.get("account_id"))
        upd["sku"] = _it.get("sku", "")
        upd["product"] = _it.get("name", "")
    if "reason" in upd:
        upd["reason_label"] = REASON_LABELS.get(upd["reason"], upd["reason"])
    upd["updated_at"] = _now()
    
    await db.marketing_returns.update_one({"id": return_id}, {"$set": upd})
    updated = {**existing, **upd}
    return {"success": True, "data": serialize(updated)}

@router.delete("/{return_id}")
async def delete_return(return_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_returns.delete_one({"id": return_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Return not found")
    return {"success": True, "message": "Deleted"}

@router.post("/{return_id}/approve")
async def approve_return(return_id: str, request: Request):
    from routes.shared import require_perm
    await require_perm(
        request, 'toko.approve', 'toko.manage',
        legacy_roles=('manager_marketing', 'pic_marketing', 'pic_toko', 'cs_staff',
                      'manager', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menyetujui retur.')
    db = get_db()
    existing = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Return not found")
    
    await db.marketing_returns.update_one(
        {"id": return_id},
        {"$set": {
            "status": "approved",
            "appeal_status": "accepted",
            "appeal_result": "Disetujui",
            "updated_at": _now()
        }}
    )
    # W4 (sesi #29) — jaring pengaman: retur yang dibuat SEBELUM jembatan ada
    # (atau yang jembatannya gagal saat dibuat) ikut dijembatani saat disetujui,
    # jadi tidak ada retur yang bisa lolos tanpa pekerjaan fisik di gudang.
    wh_msg = ""
    fresh = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if fresh and not fresh.get("wh_return_id"):
        try:
            res = await _rb.ensure_wh_return(db, fresh, actor=_get_user(request),
                                            condition=fresh.get("item_condition"),
                                            auto_restock=True)
            wh_msg = res.get("message", "")
        except Exception as e:  # noqa: BLE001
            logger.error("[retur] jembatan saat approve gagal (%s): %s", return_id, e)
            await db.marketing_returns.update_one({"id": return_id}, {"$set": {
                "wh_sync_ok": False, "wh_sync_error": str(e)[:300], "wh_sync_at": _now()}})
            wh_msg = f"Retur disetujui, tetapi pekerjaan gudang gagal dibuat: {e}"
    return {"success": True, "message": "Return approved", "warehouse_message": wh_msg}

@router.post("/{return_id}/reject")
async def reject_return(return_id: str, request: Request):
    from routes.shared import require_perm
    await require_perm(
        request, 'toko.approve', 'toko.manage',
        legacy_roles=('manager_marketing', 'pic_marketing', 'pic_toko', 'cs_staff',
                      'manager', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menolak retur.')
    body = await request.json()
    notes = body.get("notes", "")
    
    db = get_db()
    existing = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Return not found")
    
    await db.marketing_returns.update_one(
        {"id": return_id},
        {"$set": {
            "status": "rejected",
            "appeal_status": "rejected",
            "appeal_result": "Ditolak",
            "refund_amount": 0,
            "notes": notes,
            "updated_at": _now()
        }}
    )
    # W4 — kejujuran stok: kalau retur ini SUDAH menambah stok (restock otomatis
    # saat dibuat) lalu kemudian ditolak, angka stok sudah bergerak. Jangan diam:
    # beri peringatan supaya petugas gudang bisa menyesuaikan (lewat Opname /
    # Pengeluaran), bukan menemukannya berbulan-bulan kemudian sebagai selisih.
    warning = None
    if existing.get("wh_restocked"):
        warning = (
            f"Perhatian: retur ini sudah menambah stok {existing.get('wh_restock_qty', 0)} "
            f"pcs di {existing.get('wh_restock_location_code') or 'gudang'} "
            f"(retur fisik {existing.get('wh_return_code') or '-'}). Karena retur "
            "sekarang DITOLAK, sesuaikan stoknya di Gudang bila barang tidak benar-benar "
            "kembali.")
    return {"success": True, "message": "Return rejected", "warning": warning}

@router.post("/{return_id}/complete")
async def complete_return(return_id: str, request: Request):
    """
    RC-FLOW-UX-11c (opsi B — soft-warning):
    Complete diperbolehkan tanpa `wh_return_id`, TAPI response menyertakan
    field `warning` bila barang fisik belum ditangani Gudang. Frontend
    menampilkan banner (bukan block hard). Bila keputusan berikutnya
    upgrade ke opsi A (hard-guard), tinggal ubah 400 pada blok warning.
    """
    await require_auth(request)
    db = get_db()
    existing = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Return not found")
    if existing.get("status") != "approved":
        raise HTTPException(400, "Only approved returns can be completed")

    await db.marketing_returns.update_one(
        {"id": return_id},
        {"$set": {
            "status": "completed",
            "updated_at": _now()
        }}
    )

    warning = None
    wh_ret_id = existing.get("wh_return_id")
    disposition = (existing.get("disposition") or "").lower()
    if not wh_ret_id and disposition not in {"dispose", "refund_only", "donation"}:
        warning = (
            "Barang fisik belum ditangani Gudang (belum ada wh_return terkait). "
            "Stok FG tidak otomatis bertambah. "
            "Bila retur nyatanya harus di-restock, buat 'Retur Fisik di Gudang' terlebih dahulu."
        )

    return {"success": True, "message": "Return completed", "warning": warning}


# ══════════════════════════════════════════════════════════════════════════════
# W4 (sesi #29) — JEMBATAN Marketing → Gudang lewat SSOT `core/returns_bridge`
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/sync-to-warehouse")
async def sync_returns_to_warehouse(request: Request):
    """Tarik SEMUA retur Marketing yang belum punya pekerjaan Retur Fisik di Gudang.

    Dipakai untuk retur yang sudah ada SEBELUM jembatan otomatis dibuat
    (terukur 2026-08-19: 30 retur Marketing vs 0 retur gudang). Idempoten:
    retur yang sudah dijembatani tidak digandakan dan stoknya tidak ditambah dua kali.

    Body (opsional):
      dry_run: true      → hanya menghitung & menjelaskan, TIDAK menulis
      auto_restock: bool → langsung tambah stok (default true)
      condition: 'Baik' | 'Rusak'
    """
    user = await require_auth(request)
    db = get_db()
    body = {}
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — body opsional
        body = {}
    res = await _rb.sync_all(
        db, actor=user,
        dry_run=bool(body.get("dry_run")),
        auto_restock=body.get("auto_restock", True) is not False,
        condition=body.get("condition"),
        limit=int(body.get("limit") or 500),
    )
    return {"success": True, "data": res}


@router.post("/{return_id}/create-wh-return")
async def create_wh_return_from_marketing(return_id: str, request: Request):
    """Buat/pastikan pekerjaan Retur Fisik di Gudang untuk satu retur Marketing.

    Sejak sesi #29 handler ini HANYA memanggil SSOT `core/returns_bridge` supaya
    tidak ada dua versi logika jembatan. Perbedaan penting dari versi lama:
      · `sku_code`/`material_id`/`qty` DIISI dari master (dulu kosong & dipaksa 1)
        sehingga restock bisa tepat sasaran;
      · retur berstatus `pending` pun boleh dijembatani (barangnya nyata sudah di
        jalan) — pemilik minta otomatis, bukan menunggu approve;
      · idempoten & bisa langsung menambah stok sesuai kondisi barang.

    Body (opsional): {condition: 'Baik'|'Rusak', auto_restock: bool}
    """
    user = await require_auth(request)
    db = get_db()
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = {}

    ret = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise HTTPException(404, "Marketing return not found")
    if ret.get("status") in {"rejected", "cancelled"}:
        raise HTTPException(400, (
            f"Retur berstatus '{ret.get('status')}' — barangnya tidak kembali, jadi "
            "tidak boleh membuat pekerjaan gudang untuknya."))

    try:
        res = await _rb.ensure_wh_return(
            db, ret, actor=user,
            condition=body.get("condition", ret.get("item_condition")),
            auto_restock=body.get("auto_restock", True) is not False)
    except _rb.ReturnBridgeError as e:
        raise HTTPException(400, str(e))

    wh = res.get("wh_return") or {}
    return {
        "success": True,
        "already_exists": not res.get("created"),
        "data": serialize(wh),
        "marketing_return_id": return_id,
        "wh_return_code": wh.get("return_code", ""),
        "restocked": bool(wh.get("restocked")),
        "stock_effect": wh.get("stock_effect", ""),
        "link_status": wh.get("link_status", ""),
        "message": res.get("message", ""),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7B: RETURNS → CREDIT NOTE AUTO-POSTING
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/{return_id}/create-credit-note")
async def create_credit_note(return_id: str, request: Request):
    """
    Phase 7B: Create Credit Note dari approved return.
    
    Saat retur disetujui, sistem akan:
    1. Create credit note record
    2. Auto-post reversing GL entry (Dr Revenue / Cr AR)
    """
    user = await require_auth(request)
    db = get_db()
    
    # Get return record
    ret = await db.marketing_returns.find_one({"id": return_id}, {"_id": 0})
    if not ret:
        raise HTTPException(404, "Return not found")
    
    # Validate eligible for credit note
    if ret.get("status") not in ["approved", "completed"]:
        raise HTTPException(400, f"Only approved/completed returns can generate credit notes. Current status: {ret.get('status')}")
    
    # Check if credit note already exists
    if ret.get("credit_note_id"):
        raise HTTPException(400, "Credit note sudah dibuat untuk return ini")
    
    # Ensure customer exists (get or create marketplace customer)
    customer = await db.rahaza_customers.find_one({"code": "MARKETPLACE"}, {"_id": 0})
    if not customer:
        customer_id = str(uuid.uuid4())
        customer = {
            "id": customer_id,
            "code": "MARKETPLACE",
            "name": "Marketplace Customer",
            "type": "marketplace",
            "email": "",
            "phone": "",
            "address": "",
            "active": True,
            "created_at": _now(),
        }
        await db.rahaza_customers.insert_one(customer)
    else:
        customer_id = customer["id"]
    
    # Generate credit note number (RC-5 fix: atomic race-safe numbering, was count_documents()+1)
    today = datetime.now(timezone.utc).date().strftime("%Y%m%d")
    cn_prefix = f"CN-{today}-"
    cn_number = await gen_prefixed_number(db, "rahaza_credit_notes", "cn_number", cn_prefix, 3)
    
    # Calculate amount
    refund_amount = float(ret.get("refund_amount", 0))
    if refund_amount <= 0:
        raise HTTPException(400, "Refund amount harus > 0")
    
    # Create credit note record
    cn_doc = {
        "id": str(uuid.uuid4()),
        "cn_number": cn_number,
        "return_id": return_id,
        "order_id": ret.get("order_id"),
        "customer_id": customer_id,
        "platform": ret.get("platform"),
        "account_id": ret.get("account_id"),
        "account_name": ret.get("account_name"),
        "issue_date": datetime.now(timezone.utc).date().isoformat(),
        "items": [{
            "description": f"Retur: {ret.get('product')} - {ret.get('reason_label')}",
            "qty": 1,
            "unit": "pcs",
            "price": refund_amount,
            "amount": refund_amount,
        }],
        "subtotal": round(refund_amount),
        "tax_pct": 0,
        "tax_amount": 0,
        "total": round(refund_amount),
        "status": "issued",
        "notes": f"Credit note untuk return {return_id}: {ret.get('reason_detail', '')}",
        "created_at": _now(),
        "updated_at": _now(),
        "created_by": user.get("email", "unknown"),
    }
    
    await db.rahaza_credit_notes.insert_one(cn_doc)
    
    # Update return record with credit note reference
    await db.marketing_returns.update_one(
        {"id": return_id},
        {"$set": {
            "credit_note_id": cn_doc["id"],
            "credit_note_number": cn_number,
            "credit_note_status": "issued",
            "updated_at": _now(),
        }}
    )
    
    # Auto-post GL reversing entry
    posting_result = None
    try:
        from routes.rahaza_posting import post_credit_note
        cn_refresh = await db.rahaza_credit_notes.find_one({"id": cn_doc["id"]}, {"_id": 0})
        posting_result = await post_credit_note(db, cn_refresh, user)
    except Exception as e:
        logger.exception("Credit note auto-post failed")
        posting_result = {"ok": False, "error": str(e)}
    
    # Get final state
    final_cn = await db.rahaza_credit_notes.find_one({"id": cn_doc["id"]}, {"_id": 0})
    final_cn["_posting_result"] = posting_result
    
    return {"success": True, "data": serialize(final_cn)}


@router.post("/credit-notes/{cn_id}/post-to-gl")
async def retry_post_credit_note(cn_id: str, request: Request):
    """Retry posting credit note to GL (idempotent)"""
    from routes.shared import require_perm
    await require_perm(
        request, 'finance.approve', 'finance.manage',
        legacy_roles=('accounting', 'manager_keuangan', 'staff_keuangan',
                      'owner', 'admin', 'superadmin'),
        message='Akses ditolak: hanya keuangan yang boleh posting nota kredit ke GL.')
    db = get_db()
    user = _get_user(request)
    
    cn = await db.rahaza_credit_notes.find_one({"id": cn_id}, {"_id": 0})
    if not cn:
        raise HTTPException(404, "Credit note not found")
    
    try:
        from routes.rahaza_posting import post_credit_note
        result = await post_credit_note(db, cn, user)
    except Exception as e:
        logger.exception("Credit note retry post failed")
        result = {"ok": False, "error": str(e)}
    
    final_cn = await db.rahaza_credit_notes.find_one({"id": cn_id}, {"_id": 0})
    final_cn["_posting_result"] = result
    return {"success": True, "data": serialize(final_cn)}


# NOTE: /credit-notes and /credit-notes/{cn_id} GET routes are defined ABOVE
# (before /{return_id}) to avoid route conflict. See lines ~260-280.

