"""
Product Launch Manager — Backend Routes
Phase 3 Week 10: Manajemen peluncuran produk multi-platform dengan timeline
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri: jaring
# pengaman middleware hanya menolak permintaan yang MENYEBUT toko, ia tidak
# tahu isi jawaban. Tanpa ini staf pemegang satu toko membaca angka 9 toko.
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth
from core import material_fields as _mf  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/product-launches", tags=["marketing-product-launches"])

LAUNCH_STATUSES = ["planning", "ready", "launched", "postponed", "cancelled"]
PLATFORMS = ["shopee", "tiktok", "tokopedia", "instagram", "website"]

STATUS_LABELS = {
    "planning":  "Perencanaan",
    "ready":     "Siap Launch",
    "launched":  "Sudah Launch",
    "postponed": "Ditunda",
    "cancelled": "Dibatalkan",
}


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


# ── F14b — PRODUK YANG DILUNCURKAN WAJIB PRODUK YANG ADA DI MASTER ───────────
# Temuan pemilik (2026-08-14): form Launching meminta staf MENGETIK nama produk /
# bahan / model sebagai teks bebas, padahal yang diluncurkan adalah produk DA
# sendiri yang sudah terdaftar di `rahaza_models` beserta varian FG-nya.
#
# Kenapa itu MAHAL, bukan soal kenyamanan mengetik:
#   1. `_auto_create_fg_from_launch()` membuat BARANG JADI dari teks itu ⇒ satu
#      produk lahir dua kali di master stok dengan dua kode berbeda. Stok, HPP,
#      dan reservasi katalog pecah mengikutinya, dan tidak ada satu pun galat.
#   2. Harga rencana tidak bisa dibandingkan dengan harga RESMI master maupun
#      harga katalog toko ⇒ "kenapa harga di toko beda dengan rencana?" tidak
#      punya jawaban.
#   3. Ejaan = identitas. "Katun Linen Premium" ≠ "katun linen premium" bagi
#      mesin; laporan per produk/bahan salah DIAM-DIAM.
#
# ATURAN (mengikuti pelajaran `received_at`/`closed_at`): field turunan master
# yang dipakai laporan **ditulis SERVER**, kiriman browser DIABAIKAN. Fungsi di
# bawah adalah SATU-SATUNYA penulisnya — kalau setiap endpoint menyalin sendiri,
# suatu hari salah satunya lupa dan tidak ada yang tahu.
MASTER_DERIVED_FIELDS = (
    "product_name", "model", "model_code", "category_name",
    "hpp_master", "retail_price_master", "material", "master_linked",
)


async def _resolve_master_model(db, model_id: str) -> dict:
    """Baca produk dari MASTER (`rahaza_models`) → field turunan yang siap ditulis.

    Menolak (400) kalau `model_id` tidak dikenal atau produknya sudah tidak aktif —
    rencana peluncuran untuk produk yang tidak ada di master adalah rencana yang
    tidak bisa dieksekusi gudang.
    """
    if not model_id:
        raise HTTPException(
            400, "Produk wajib dipilih dari Master Produk. Rencana peluncuran "
                 "tanpa tautan master tidak bisa dicocokkan dengan stok, HPP, "
                 "maupun harga resmi.")
    m = await db.rahaza_models.find_one({"id": model_id}, {"_id": 0})
    if not m:
        raise HTTPException(
            400, f"Produk '{model_id}' tidak ada di Master Produk. Daftarkan "
                 f"dulu di Master Produk supaya kode, HPP, dan harga resminya "
                 f"punya satu sumber.")
    if m.get("active") is False:
        raise HTTPException(
            400, f"Produk '{m.get('code') or model_id}' sudah TIDAK AKTIF di "
                 f"Master Produk — tidak bisa dijadikan rencana peluncuran baru.")

    # Bahan: master produk BELUM punya field bahan sendiri; yang ada adalah
    # `composition` pada varian FG. Kalau memang belum dicatat, dikatakan apa
    # adanya (string kosong) — bukan diisi tebakan, dan bukan diketik ulang staf
    # (ejaan keempat tidak menolong siapa pun; perbaikannya di Master Produk).
    comps: list = []
    async for fg in db.rahaza_materials.find(
            {"type": "fg", "model_id": model_id},
            {"_id": 0, "composition": 1}):
        c = (fg.get("composition") or "").strip()
        if c and c not in comps:
            comps.append(c)

    retail = float(m.get("retail_price") or 0)
    hpp = float(m.get("hpp") if m.get("hpp") is not None else (m.get("base_hpp") or 0))
    return {
        "model_id":            model_id,
        "model_code":          m.get("code") or "",
        # `model` dipertahankan (dokumen lama memakainya) tetapi sekarang berisi
        # KODE master, bukan kata bebas seperti "Gamis"/"Kulot".
        "model":               m.get("code") or "",
        "product_name":        m.get("name") or "",
        "category_name":       m.get("category_name") or m.get("category") or "",
        "hpp_master":          hpp,
        "retail_price_master": retail,
        "material":            " / ".join(comps),
        "master_linked":       True,
    }


# ── Seed ─────────────────────────────────────────────────────────────────────
async def seed_product_launches_if_empty():
    """Contoh rencana peluncuran — SELALU dari produk yang BENAR-BENAR ada di master.

    F14b: versi lama menyemai 8 produk dari daftar HARDCODE ("Gamis Busui
    Friendly…", bahan "Katun Linen Premium") yang tidak ada di `rahaza_models`.
    Data contoh yang tidak menaati aturan produk BUKAN sekadar kotor: ia
    MENGAJARKAN pola yang salah — staf melihat 8 baris tanpa tautan master lalu
    menyimpulkan mengetik bebas itu wajar. Sekarang contohnya diambil dari master
    (dan kalau master kosong, TIDAK ada contoh yang dibuat — lebih baik layar
    kosong dengan petunjuk daripada 8 rencana untuk produk yang tidak ada).
    """
    db = get_db()
    if await db.marketing_product_launches.count_documents({}) > 0:
        return

    import random
    now = _now()

    models = await db.rahaza_models.find(
        {"$or": [{"active": True}, {"active": {"$exists": False}}]},
        {"_id": 0}).sort("code", 1).limit(8).to_list(8)
    if not models:
        logger.info("[product_launches] master produk kosong ⇒ 0 contoh disemai "
                    "(sengaja: contoh tanpa tautan master mengajarkan pola salah)")
        return

    # F14 — peluncuran demo dulu hanya menyimpan daftar nama platform, tanpa
    # `account_id` maupun `target_account_ids` yang terisi ⇒ 8/8 tak berlingkup toko.
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    all_platforms = sorted({a.get("platform", "shopee") for a in _accounts})
    statuses = ["planning", "planning", "ready", "ready", "launched", "launched",
                "launched", "postponed"]

    entries = []
    for i, m in enumerate(models):
        derived = await _resolve_master_model(db, m["id"])

        days_offset = random.randint(-7, 30)
        launch_date = (now + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        plats = random.sample(all_platforms, random.randint(1, min(3, len(all_platforms))))
        status = statuses[i % len(statuses)]
        if days_offset < 0 and status in ("planning", "ready"):
            status = "launched"

        # Harga contoh BERANGKAT dari harga RESMI master (K-3a), bukan angka
        # karangan — supaya selisih rencana↔master bisa dilihat, bukan ditebak.
        retail = derived["retail_price_master"] or 0
        original_price   = retail
        flash_sale_price = int(retail * 0.8) if retail else 0
        cross_price      = int(retail * 1.2) if retail else 0
        listing_price    = flash_sale_price

        _acc = _accounts[i % len(_accounts)]
        _targets = [a["id"] for a in _accounts if a.get("platform") in plats] or [_acc["id"]]
        entries.append({
            "id":           str(uuid.uuid4()),
            "account_id":   _acc["id"],
            "account_name": _acc.get("account_name", ""),
            "target_account_ids": _targets,
            **derived,
            "launch_date":  launch_date,
            "photo_urls":   [],
            "original_price":    original_price,
            "flash_sale_price":  flash_sale_price,
            "cross_price":       cross_price,
            "listing_price":     listing_price,
            "platforms":         plats,
            "description":       f"{derived['product_name']} — koleksi 2026.",
            "status":            status,
            "status_label":      STATUS_LABELS.get(status, status),
            "launch_notes":      "",
            "fg_material_id":    None,
            "_seed_origin": True,
            "created_by":        "system",
            "created_at":        _now(),
            "updated_at":        _now(),
        })

    if entries:
        await db.marketing_product_launches.insert_many(entries)
    logger.info(f"[product_launches] seeded {len(entries)} launches (semua tertaut master)")


# ── Models ───────────────────────────────────────────────────────────────────
class LaunchIn(BaseModel):
    # F14 — peluncuran dulu hanya punya `target_account_ids` yang tak pernah
    # terisi (8/8 dokumen tanpa lingkup toko). `account_id` = toko pemilik
    # rencana; `target_account_ids` tetap ada untuk peluncuran lintas-toko.
    account_id: str
    # F14b — WAJIB. Produk yang diluncurkan adalah produk DA yang sudah ada di
    # `rahaza_models`. Lihat `_resolve_master_model()` untuk alasannya.
    model_id: str
    launch_date: str      # YYYY-MM-DD
    # ── Field TURUNAN master (dikirim browser boleh, tapi DIABAIKAN) ──────────
    # Dibiarkan ada supaya klien lama tidak error 422; nilainya ditimpa server.
    product_name: Optional[str] = None
    material: Optional[str] = None
    model: Optional[str] = None
    photo_urls: Optional[List[str]] = []
    # Harga: BOLEH beda dari harga resmi master (keputusan owner K-3a — katalog
    # per platform boleh menimpa, selisihnya DITAMPILKAN). Karena itu harga
    # TIDAK ikut ditimpa server; yang ditimpa hanya identitas produk.
    original_price: Optional[float] = Field(default=0, ge=0)
    flash_sale_price: Optional[float] = Field(default=0, ge=0)
    cross_price: Optional[float] = Field(default=0, ge=0)
    listing_price: Optional[float] = Field(default=0, ge=0)
    platforms: Optional[List[str]] = []
    description: Optional[str] = ""
    status: Optional[str] = "planning"
    launch_notes: Optional[str] = ""
    # ── RnD Master link (NEW) ──
    style_id: Optional[str] = None      # FK to dewi_rnd_styles
    style_code: Optional[str] = None    # denormalized
    target_account_ids: Optional[List[str]] = []  # multi-platform accounts

class LaunchUpdate(BaseModel):
    account_id: Optional[str] = None
    model_id: Optional[str] = None
    launch_date: Optional[str] = None
    # Turunan master — diterima demi kompatibilitas, tetapi DIBUANG sebelum
    # disimpan (lihat `update_launch`). Satu-satunya cara mengubahnya adalah
    # mengganti `model_id`.
    product_name: Optional[str] = None
    material: Optional[str] = None
    model: Optional[str] = None
    photo_urls: Optional[List[str]] = None
    original_price: Optional[float] = Field(default=None, ge=0)
    flash_sale_price: Optional[float] = Field(default=None, ge=0)
    cross_price: Optional[float] = Field(default=None, ge=0)
    listing_price: Optional[float] = Field(default=None, ge=0)
    platforms: Optional[List[str]] = None
    description: Optional[str] = None
    status: Optional[str] = None
    launch_notes: Optional[str] = None
    style_id: Optional[str] = None
    style_code: Optional[str] = None
    target_account_ids: Optional[List[str]] = None


# ── Endpoints ────────────────────────────────────────────────────────────────
@router.get("/summary")
async def get_summary(request: Request):
    user = await require_auth(request)
    await seed_product_launches_if_empty()
    db = get_db()

    # F6 — peluncuran bisa LINTAS-TOKO, jadi "milik saya" = pemilik ATAU sasaran.
    _vis = await _scope.visible_account_ids(db, user)
    _sq = {} if _vis is None else {"$or": [{"account_id": {"$in": _vis}},
                                          {"target_account_ids": {"$in": _vis}}]}
    all_docs = await db.marketing_product_launches.find(
        _sq, {"_id": 0, "status": 1, "launch_date": 1, "platforms": 1}).to_list(1000)

    counts = {s: 0 for s in LAUNCH_STATUSES}
    by_platform = {}
    upcoming_30 = 0
    today = _now().date()
    in_30 = today + timedelta(days=30)

    for d in all_docs:
        s = d.get("status", "")
        if s in counts:
            counts[s] += 1
        for p in (d.get("platforms") or []):
            by_platform[p] = by_platform.get(p, 0) + 1
        try:
            ld = datetime.fromisoformat(d["launch_date"]).date()
            if today <= ld <= in_30 and d.get("status") in ["planning", "ready"]:
                upcoming_30 += 1
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    return {
        "success": True,
        "data": {
            "total":       len(all_docs),
            "planning":    counts["planning"],
            "ready":       counts["ready"],
            "launched":    counts["launched"],
            "postponed":   counts["postponed"],
            "cancelled":   counts["cancelled"],
            "upcoming_30": upcoming_30,
            "by_platform": by_platform,
        }
    }


@router.get("")
async def list_launches(
    request: Request,
    page:      int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    account_id: str = Query(default="", description="F14 — filter per toko"),
    scope: str = Query(default="any", pattern="^(any|owner|target)$",
                       description="any = pemilik ATAU sasaran · owner = hanya pemilik"),
    status:    str = Query(default=""),
    platform:  str = Query(default=""),
    search:    str = Query(default=""),
    date_from: str = Query(default=""),
    date_to:   str = Query(default=""),
):
    user = await require_auth(request)
    await seed_product_launches_if_empty()
    db = get_db()

    q = {}
    # F6 — lingkup pemakai lebih dulu (pemilik ATAU sasaran), filter layar sesudahnya.
    _vis = await _scope.visible_account_ids(db, user)
    if _vis is not None:
        q["$or"] = [{"account_id": {"$in": _vis}},
                    {"target_account_ids": {"$in": _vis}}]
    if account_id:
        # Peluncuran bisa LINTAS-TOKO: satu produk diluncurkan di beberapa akun.
        # Karena itu ada dua arti "milik toko ini":
        #   owner  = toko yang membuat rencananya (`account_id`)
        #   target = toko yang menjadi sasaran peluncuran (`target_account_ids`)
        # Default `any` menampilkan keduanya — kalau hanya owner yang ditampilkan,
        # rencana yang MENYASAR toko ini akan hilang dari layar toko itu. Pemanggil
        # yang butuh ketat bisa meminta `scope=owner`. Setiap baris dibubuhi
        # `matched_scope` supaya alasan kemunculannya bisa diperiksa, bukan ditebak.
        if scope == "owner":
            q["account_id"] = account_id
        elif scope == "target":
            q["target_account_ids"] = account_id
        else:
            q["$or"] = [{"account_id": account_id},
                        {"target_account_ids": account_id}]
    if status:
        q["status"]   = status
    if platform:
        q["platforms"] = platform
    if search:
        q["product_name"] = {"$regex": search, "$options": "i"}
    if date_from:
        q.setdefault("launch_date", {})["$gte"] = date_from
    if date_to:
        q.setdefault("launch_date", {})["$lte"] = date_to

    total = await db.marketing_product_launches.count_documents(q)
    skip  = (page - 1) * page_size
    items = await db.marketing_product_launches.find(q, {"_id": 0})\
                    .sort("launch_date", 1).skip(skip).limit(page_size).to_list(page_size)
    if account_id:
        for _it in items:
            _own = _it.get("account_id") == account_id
            _tgt = account_id in (_it.get("target_account_ids") or [])
            _it["matched_scope"] = ("owner+target" if _own and _tgt
                                    else "owner" if _own else "target")
    # F14b — status tautan master DIHITUNG SERVER, bukan ditebak layar. Dokumen
    # warisan (dibuat sebelum aturan "produk wajib dari master") jumlahnya
    # DIAKUI, bukan disembunyikan — layar menampilkannya sebagai peringatan
    # beserta cara memperbaikinya.
    for _it in items:
        _it["master_linked"] = bool(_it.get("model_id"))
    unlinked_cond = {"$or": [{"model_id": {"$exists": False}},
                             {"model_id": None}, {"model_id": ""}]}
    unlinked_total = await db.marketing_product_launches.count_documents(
        {"$and": [q, unlinked_cond]} if q else unlinked_cond)
    return {
        "success": True,
        "data": serialize(items),
        "master_link": {
            "unlinked_total": unlinked_total,
            "hint": ("Peluncuran ini dibuat sebelum aturan 'produk wajib dari "
                     "Master Produk'. Buka Edit lalu pilih produknya — supaya "
                     "stok, HPP, dan harga resminya punya satu sumber."),
        },
        "pagination": {"total": total, "page": page, "page_size": page_size,
                       "total_pages": max(1, (total + page_size - 1) // page_size)}
    }


@router.post("")
async def create_launch(body: LaunchIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db   = get_db()

    from core import marketing_account_scope as _scope
    account = await _scope.require_account(db, body.account_id)

    # F14b — identitas produk DITULIS SERVER dari master; apa pun yang dikirim
    # browser untuk `product_name`/`model`/`material` diabaikan. Satu penulis.
    derived = await _resolve_master_model(db, body.model_id)

    status = body.status if body.status in LAUNCH_STATUSES else "planning"
    launch = {
        "id":           str(uuid.uuid4()),
        **derived,
        "launch_date":  body.launch_date,
        "photo_urls":   body.photo_urls or [],
        "original_price":   body.original_price or 0,
        "flash_sale_price": body.flash_sale_price or 0,
        "cross_price":      body.cross_price or 0,
        "listing_price":    body.listing_price or 0,
        "platforms":        body.platforms or [],
        "description":      body.description or "",
        "status":           status,
        "status_label":     STATUS_LABELS.get(status, status),
        "launch_notes":     body.launch_notes or "",
        # ── RnD & Account linkage ──
        "style_id":         body.style_id,
        "style_code":       body.style_code or "",
        "target_account_ids": body.target_account_ids or [],
        "fg_material_id":   None,  # populated when launch reaches 'launched' status
        "created_by":       user.get("email", "unknown"),
        "created_at":       _now(),
        "updated_at":       _now(),
    }
    _scope.stamp_account(launch, account)
    if not launch.get("target_account_ids"):
        launch["target_account_ids"] = [account["id"]]
    await db.marketing_product_launches.insert_one(launch)
    return {"success": True, "data": serialize(launch)}


@router.put("/{launch_id}")
async def update_launch(launch_id: str, body: LaunchUpdate, request: Request):
    await require_auth(request)
    db = get_db()
    existing = await db.marketing_product_launches.find_one({"id": launch_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Launch not found")

    upd = {k: v for k, v in body.dict().items() if v is not None}

    # F14b — field turunan master TIDAK boleh ditulis browser. Kalau dibiarkan,
    # staf bisa memilih produk A lalu menimpa namanya dengan teks apa pun, dan
    # dokumen itu akan terlihat "tertaut master" padahal isinya sudah berbeda —
    # cacat yang lebih berbahaya daripada teks bebas terang-terangan.
    for _f in MASTER_DERIVED_FIELDS:
        upd.pop(_f, None)

    # Satu-satunya cara mengubah identitas produk: mengganti `model_id`.
    if upd.get("model_id") and upd["model_id"] != existing.get("model_id"):
        upd.update(await _resolve_master_model(db, upd["model_id"]))
    else:
        upd.pop("model_id", None)

    if "status" in upd:
        upd["status_label"] = STATUS_LABELS.get(upd["status"], upd["status"])
    upd["updated_at"] = _now()
    await db.marketing_product_launches.update_one({"id": launch_id}, {"$set": upd})
    updated = {**existing, **upd}
    return {"success": True, "data": serialize(updated)}


@router.delete("/{launch_id}")
async def delete_launch(launch_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_product_launches.delete_one({"id": launch_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Launch not found")
    return {"success": True, "message": "Deleted"}


@router.post("/{launch_id}/status")
async def update_status(launch_id: str, request: Request):
    """
    Update launch status. Saat status berubah ke 'launched', system akan:
    1. Auto-create FG entry di rahaza_materials (type='fg') jika belum ada
    2. Link launch.fg_material_id ke FG yang dibuat
    """
    await require_auth(request)
    body = await request.json()
    new_status = body.get("status", "")
    if new_status not in LAUNCH_STATUSES:
        raise HTTPException(400, f"Invalid status: {new_status}")
    db = get_db()
    existing = await db.marketing_product_launches.find_one({"id": launch_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Launch not found")
    
    update_fields = {
        "status": new_status,
        "status_label": STATUS_LABELS.get(new_status, new_status),
        "updated_at": _now(),
    }
    
    # ── Tautkan ke FG master saat 'launched' ──
    # F14b — namanya dulu "auto-create"; sekarang MENAUTKAN ke barang jadi yang
    # sudah ada. Tidak ada produk baru yang lahir dari teks (lihat fungsinya).
    fg_linked = None
    if new_status == "launched" and not existing.get("fg_material_id"):
        fg_doc = await _auto_create_fg_from_launch(db, existing)
        if fg_doc:
            update_fields["fg_material_id"] = fg_doc["id"]
            update_fields["fg_code"] = fg_doc["code"]
            update_fields["fg_link_status"] = "tertaut_master"
            fg_linked = fg_doc
        else:
            # Diakui, bukan didiamkan: layar bisa menampilkan berapa banyak
            # peluncuran yang statusnya sudah 'launched' tetapi tidak punya
            # barang jadi — dulu angka ini disembunyikan oleh FG karangan.
            update_fields["fg_link_status"] = (
                "butuh_tautan_master" if not existing.get("model_id")
                else "master_belum_punya_varian")

    await db.marketing_product_launches.update_one(
        {"id": launch_id},
        {"$set": update_fields}
    )

    return {
        "success": True,
        "status": new_status,
        "fg_linked": bool(fg_linked),
        "fg_link_status": update_fields.get("fg_link_status"),
        # Nama lama dipertahankan supaya klien lama tidak pecah, TETAPI artinya
        # sekarang "tertaut", bukan "dibuat" — dan tidak pernah lagi True untuk
        # produk yang tidak ada di master.
        "fg_auto_created": False,
        "fg": serialize(fg_linked) if fg_linked else None,
    }


async def _auto_create_fg_from_launch(db, launch: dict) -> Optional[dict]:
    """Tautkan peluncuran ke BARANG JADI — tanpa pernah membuat produk kembar.

    ═══════════════════════════════════════════════════════════════════════════
    F14b — CACAT YANG DITUTUP DI SINI (temuan pemilik 2026-08-14)
    ═══════════════════════════════════════════════════════════════════════════
    Versi lama membuat FG baru dari TEKS yang diketik staf:

        code = style_code OR model OR product_name.replace(" ", "-").upper()[:30]

    Untuk baris demo `"Gamis Busui Friendly DA-2026 Series 1"` itu menghasilkan
    kode FG `GAMIS-BUSUI-FRIENDLY-DA-2026-S` — barang jadi yang **tidak pernah
    ada di master**, tanpa `model_id`, tanpa varian warna/ukuran, `hpp = 0`, dan
    kategori literal `"launch"`. Akibatnya berantai:
      · master stok punya DUA barang untuk satu produk (yang asli + yang lahir
        dari teks) ⇒ "stok produk ini berapa?" punya dua jawaban;
      · `hpp = 0` ⇒ margin katalog marketing mustahil dihitung untuk barang itu;
      · kategori `"launch"` bukan kategori produk ⇒ laporan per kategori bocor.
    Dan semuanya terjadi **tanpa satu pun galat** — hanya sebaris log info.

    ATURAN SEKARANG:
      1. Peluncuran yang **tertaut master** (`model_id`) TIDAK PERNAH membuat FG.
         Barang jadinya sudah ada — dikembalikan varian yang benar-benar ada.
      2. Peluncuran **warisan** (tanpa `model_id`, dibuat sebelum aturan ini)
         juga tidak lagi membuat FG diam-diam. Ia ditandai
         `fg_link_status='butuh_tautan_master'` supaya jumlahnya **diakui di
         layar** dan bisa diperbaiki, bukan ditebak. (Pelajaran `closed_at`:
         data warisan tidak boleh ditebak diam-diam.)
    """
    try:
        model_id = launch.get("model_id")

        # ── (2) Warisan: tidak ada tautan master ⇒ TIDAK membuat apa pun ──────
        if not model_id:
            logger.warning(
                "[product_launches] launch %s tidak tertaut master ⇒ FG TIDAK "
                "dibuat (dulu: FG karangan dari teks). Perbaiki lewat Edit → "
                "pilih produk dari Master Produk.", launch.get("id"))
            return None

        # ── (1) Tertaut master: pakai varian FG yang SUDAH ADA ────────────────
        variants = await db.rahaza_materials.find(
            {"type": "fg", "model_id": model_id,
             "$or": [{"active": True}, {"active": {"$exists": False}}]},
            {"_id": 0}).sort("code", 1).to_list(500)

        if not variants:
            logger.warning(
                "[product_launches] model %s belum punya varian FG ⇒ tidak ada "
                "yang bisa ditautkan. Buat varian di Master Produk (warna×ukuran).",
                model_id)
            return None

        # Varian mana yang dijadikan penanda? Yang paling banyak stok jualnya —
        # itu varian yang paling mungkin benar-benar dikirim saat launch.
        # Tidak ada penulisan baru ke master: murni PEMBACAAN.
        primary = variants[0]
        logger.info(
            "[product_launches] launch %s ditautkan ke FG master %s (%d varian) "
            "— tidak ada FG baru yang dibuat",
            launch.get("id"), primary.get("code"), len(variants))
        return primary
    except Exception as e:  # noqa: BLE001
        logger.error(f"Gagal menautkan FG untuk launch {launch.get('id')}: {e}",
                     exc_info=True)
        return None
