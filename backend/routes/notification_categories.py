"""
NOTIFIKASI BERKATEGORI — CV. Dewi Aditya (2026-07-27)

MASALAH YANG DIPERBAIKI (laporan owner)
---------------------------------------
Bel notifikasi lama menumpahkan SEMUA notifikasi apa adanya: tidak ada kategori,
tidak jelas datang dari portal mana, dan admin tidak bisa mengatur siapa menerima
apa. Akibatnya notifikasi jadi kebisingan, bukan alat bantu kerja.

YANG DITAMBAHKAN
----------------
1. KATEGORI = PORTAL SUMBER. Notifikasi lama TIDAK perlu dimigrasi: kategori
   diturunkan saat baca dari `link_module` (prefix modul = portal) lalu `type`.
   Jadi seluruh notifikasi historis langsung ikut terkategori.
2. KONFIGURASI ADMIN: matriks kategori × role (`notif_category_config`) — role
   apa boleh menerima kategori apa. Default: semua kategori aktif untuk role yang
   memang punya akses portal tersebut (diturunkan dari PORTAL_ACCESS, jadi
   konsisten dengan RBAC dan tidak jadi sumber kebenaran kedua).
3. PREFERENSI PER-USER (`notif_user_prefs`): user boleh membisukan kategori
   tertentu untuk dirinya sendiri, tapi TIDAK bisa membuka kategori yang sudah
   ditutup admin.
4. KATEGORI "UNTUK SAYA" (2026-08-07, perbaikan POC RBAC 3 FAIL). Notifikasi yang
   dialamatkan LANGSUNG ke seseorang (user_id / target_user_ids / target_roles
   berisi role-nya) dulu bisa HILANG dari bel bila kategori turunannya bukan
   kategori portal yang biasa ia lihat — contohnya subtype tak dikenal yang jatuh
   ke 'sysadmin', padahal 'sysadmin' hanya untuk admin. Sekarang notifikasi
   semacam itu ditampung di kategori bawaan `personal` ("Untuk Saya") yang selalu
   aktif untuk semua orang dan tidak bisa ditutup admin maupun dibisukan user.
   Kategori ini TIDAK melonggarkan RBAC: aturan audiens (`notif_audience_query`)
   tetap satu-satunya penentu siapa boleh menerima apa.

Endpoint (prefix /api/notifications):
  GET  /categories                daftar kategori + hitungan (untuk bel ringkas)
  GET  /categorized               daftar notifikasi + kategori (untuk popup)
  GET  /category-config           matriks admin
  PUT  /category-config           simpan matriks (admin)
  GET  /my-category-prefs         kategori yang dibisukan user
  PUT  /my-category-prefs         simpan pembisuan user
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request

from auth import require_auth, serialize_doc
from database import get_db
from routes.shared import PORTAL_ACCESS, SUPER_ROLES
from utils.notif_unified import notif_is_unread_for, notif_user_id


def _explicitly_addressed(notif: dict, user: dict) -> bool:
    """Ditujukan LANGSUNG ke user ini (personal / daftar user / role-nya).

    Notifikasi yang jelas-jelas dialamatkan ke seseorang WAJIB sampai, walaupun
    kategorinya bukan kategori portal yang biasa ia lihat. Filter kategori hanya
    untuk menyaring notifikasi siaran antar-portal (2026-08-07).
    """
    uid = notif_user_id(user)
    role = (user.get("role") or "").lower()
    meta = notif.get("meta") or {}
    if notif.get("user_id") and notif.get("user_id") == uid:
        return True
    if uid in (list(notif.get("target_user_ids") or []) + list(meta.get("target_user_ids") or [])):
        return True
    roles = [str(r).lower() for r in (list(notif.get("target_roles") or [])
                                      + list(meta.get("target_roles") or []))]
    return bool(role) and role in roles

router = APIRouter(prefix="/api/notifications", tags=["notifications-category"])

CFG = "notif_category_config"
PREF = "notif_user_prefs"

# Kategori = portal sumber. `key` sengaja sama dengan portal id supaya tombol
# "buka modul" bisa langsung memakai router portal yang sudah ada.
CATEGORIES = [
    {"key": "personal",    "label": "Untuk Saya",         "icon": "user-check"},
    {"key": "warehouse",   "label": "Gudang",             "icon": "warehouse"},
    {"key": "procurement", "label": "Pengadaan",          "icon": "shopping-cart"},
    {"key": "production",  "label": "Produksi",           "icon": "factory"},
    {"key": "cutting",     "label": "Cutting",            "icon": "scissors"},
    {"key": "maklon",      "label": "Maklon",             "icon": "package"},
    {"key": "finance",     "label": "Keuangan",           "icon": "landmark"},
    {"key": "hr",          "label": "SDM",                "icon": "users"},
    {"key": "toko",        "label": "Marketing",          "icon": "shopping-bag"},
    {"key": "accessories", "label": "Aksesoris",          "icon": "sparkles"},
    {"key": "assets",      "label": "Aset",               "icon": "boxes"},
    {"key": "rnd",         "label": "RnD",                "icon": "flask"},
    {"key": "sysadmin",    "label": "Sistem",             "icon": "shield"},
]
CATEGORY_KEYS = [c["key"] for c in CATEGORIES]
CATEGORY_LABEL = {c["key"]: c["label"] for c in CATEGORIES}
# Kategori bawaan yang SELALU aktif untuk semua orang: penampung notifikasi yang
# dialamatkan langsung ke user tetapi kategori portalnya di luar jangkauannya.
PERSONAL_CATEGORY = "personal"

# Prefix moduleId → kategori (urutan penting: yang paling spesifik dulu).
_PREFIX = [
    # 2026-08-06 — `proc-` HARUS dicek sebelum prefix lain: Portal Pengadaan kini
    # pemilik notifikasi PR/PO/faktur supplier (sebelumnya nyasar ke Gudang &
    # Keuangan sehingga staf pengadaan tidak melihat pekerjaannya sendiri).
    ("proc-", "procurement"),
    ("cutting-", "cutting"), ("acc-", "accessories"), ("accessories-", "accessories"),
    ("asset-", "assets"), ("wh-", "warehouse"), ("wms-", "warehouse"),
    ("warehouse-", "warehouse"), ("prod-", "production"), ("production-", "production"),
    ("cmt-", "maklon"), ("maklon-", "maklon"), ("fin-", "finance"), ("finance-", "finance"),
    ("hr-", "hr"), ("payroll-", "hr"), ("portal-", "hr"), ("self-", "hr"),
    ("marketing-", "toko"), ("toko-", "toko"), ("rnd-", "rnd"),
    ("mgmt-", "sysadmin"), ("management-", "sysadmin"), ("admin-", "sysadmin"),
]
# Fallback berdasarkan `type` notifikasi bila link_module kosong.
_TYPE = {
    # 2026-08-06 — token pengadaan didahulukan: "purchase_invoice" harus jatuh ke
    # Pengadaan, bukan Keuangan (token "invoice" ada di kelompok finance di bawah).
    "purchase_request": "procurement", "purchase_order": "procurement",
    "procurement": "procurement", "purchase": "procurement",
    "supplier": "procurement", "vendor": "procurement", "3way": "procurement",
    "low_stock": "warehouse", "stock": "warehouse", "reorder": "warehouse",
    "opname": "warehouse", "receiving": "warehouse",
    "production": "production", "job": "production", "qc": "production",
    "cmt": "maklon", "maklon": "maklon",
    "invoice": "finance", "payment": "finance", "journal": "finance",
    "budget": "finance", "expense": "finance", "kasbon": "finance",
    "leave": "hr", "attendance": "hr", "payroll": "hr", "kpi": "hr",
    "recruitment": "hr", "birthday": "hr",
    "marketing": "toko", "kol": "toko", "order": "toko",
    "accessory": "accessories", "asset": "assets", "rnd": "rnd",
    "backup": "sysadmin", "system": "sysadmin", "collab": "sysadmin",
}


def categorize(notif: dict) -> str:
    # `link_module` bisa di akar (penulis lama) atau di `meta` (notif_insert SSOT).
    mod = (notif.get("link_module")
           or (notif.get("meta") or {}).get("link_module") or "").lower()
    for pref, cat in _PREFIX:
        if mod.startswith(pref):
            return cat
    # `subtype` lebih spesifik daripada `type` domain ('rahaza'/'dewi'), cek dulu.
    t = f"{notif.get('subtype') or ''} {notif.get('type') or ''}".lower()
    for token, cat in _TYPE.items():
        if token in t:
            return cat
    return "sysadmin"


def _default_matrix() -> dict:
    """Default: sebuah role menerima kategori X bila role itu memang punya akses
    portal X (diturunkan dari PORTAL_ACCESS agar tidak menciptakan sumber
    kebenaran RBAC kedua)."""
    roles = sorted({r for lst in PORTAL_ACCESS.values() for r in lst})
    matrix = {}
    for role in roles:
        allowed = [c for c in CATEGORY_KEYS if role in PORTAL_ACCESS.get(c, [])]
        # Semua orang berhak tahu urusan SDM yang menyangkut dirinya.
        if "hr" not in allowed:
            allowed.append("hr")
        # "Untuk Saya" tidak pernah bisa ditutup — isinya memang milik user itu.
        if PERSONAL_CATEGORY not in allowed:
            allowed.append(PERSONAL_CATEGORY)
        matrix[role] = sorted(allowed)
    for sr in SUPER_ROLES:
        matrix[sr] = list(CATEGORY_KEYS)
    return matrix


async def get_matrix(db) -> dict:
    doc = await db[CFG].find_one({"id": "default"}, {"_id": 0})
    if not doc:
        doc = {"id": "default", "matrix": _default_matrix(),
               "updated_at": datetime.now(timezone.utc), "updated_by": "system"}
        await db[CFG].insert_one(dict(doc))
    return doc


async def category_scope(db, user: dict) -> dict:
    """Cakupan kategori untuk satu user — DUA lapis yang sengaja dipisah:

    · `base`  = kategori yang DIBUKA ADMIN untuk peran ini (matriks × role).
    · `muted` = kategori yang DIBISUKAN SENDIRI oleh user (pilihannya).

    Bedanya penting untuk perilaku bel:
      - Kategori di luar `base` (celah RBAC) tapi notifikasinya dialamatkan
        langsung ke user → dialihkan ke "Untuk Saya" supaya tidak hilang.
      - Kategori yang user BISUKAN SENDIRI → benar-benar disembunyikan (tidak
        dialihkan ke "Untuk Saya"), karena itu keputusan sadar si user.
      - "Untuk Saya" tidak bisa ditutup admin maupun dibisukan user.
    """
    role = (user.get("role") or "").lower()
    if role in SUPER_ROLES:
        base = list(CATEGORY_KEYS)
    else:
        cfg = await get_matrix(db)
        base = list(cfg["matrix"].get(role) or ["hr"])
    if PERSONAL_CATEGORY not in base:
        base.insert(0, PERSONAL_CATEGORY)
    base = [c for c in CATEGORY_KEYS if c in base]
    pref = await db[PREF].find_one({"user_id": user.get("id")}, {"_id": 0}) or {}
    muted = {c for c in (pref.get("muted_categories") or []) if c != PERSONAL_CATEGORY}
    return {"base": base, "muted": sorted(muted),
            "allowed": [c for c in base if c not in muted]}


async def allowed_categories(db, user: dict) -> list[str]:
    """Kategori yang aktif untuk user (setelah pembisuan). Dipakai UI & guard."""
    return (await category_scope(db, user))["allowed"]


def effective_category(notif: dict, user: dict, scope: dict) -> Optional[str]:
    """Kategori yang dipakai untuk MENAMPILKAN notifikasi ini kepada `user`.

    · Kategori dibisukan user → None (dihormati, tidak dialihkan).
    · Kategori aktif → pakai kategori itu.
    · Kategori di luar jangkauan peran TAPI notifikasi dialamatkan langsung ke
      user (personal / daftar user / role-nya) → "Untuk Saya" (jaring penyelamat
      bug 2026-08-07: dulu notifikasi seperti ini hilang dari bel).
    · Selain itu → None (siaran antar-portal yang bukan urusannya).

    Dipakai bersama `/categories` (hitungan) dan `/categorized` (daftar) supaya
    angka di bel selalu cocok dengan isi popupnya.
    """
    cat = categorize(notif)
    if cat in scope["muted"]:
        return None
    if cat in scope["allowed"]:
        return cat
    if (PERSONAL_CATEGORY in scope["allowed"]
            and _explicitly_addressed(notif, user)):
        return PERSONAL_CATEGORY
    return None


def _present(notif: dict, cat: str, unread: bool) -> dict:
    """Bentuk baris siap-tampil untuk bel.

    Menormalkan dua beda konvensi penulis notifikasi supaya UI tidak perlu tahu:
    `body` (SSOT `notif_insert`) vs `message` (penulis lama), dan `link_module`
    yang bisa berada di akar dokumen ATAU di dalam `meta`.
    """
    meta = notif.get("meta") or {}
    return {
        **notif,
        "category": cat,
        "category_label": CATEGORY_LABEL.get(cat, cat),
        "read": not unread,
        "message": notif.get("message") or notif.get("body") or "",
        "body": notif.get("body") or notif.get("message") or "",
        "link_module": notif.get("link_module") or meta.get("link_module") or "",
        "link_params": notif.get("link_params") or meta.get("link_params") or None,
    }


async def _fetch(db, user, limit=200):
    """Ambil notifikasi yang DITUJUKAN kepada user (aturan audiens tunggal).

    Sejak 2026-08-07 memakai `notif_audience_query` di `utils/notif_unified`:
    `user_id` == saya, ATAU `target_user_ids` memuat saya, ATAU `target_roles`
    memuat role saya. Notifikasi tanpa target hanya untuk admin/owner.
    Sebelumnya bel hanya membaca konvensi lama (target_user_ids/target_roles di
    akar dokumen) sehingga peringatan PO/piutang, cuti, payroll, absensi dan
    rapor RnD tersimpan tetapi tidak pernah tampil.
    """
    from utils.notif_unified import notif_audience_query
    rows = await db.notifications.find(
        notif_audience_query(user), {"_id": 0}).sort("created_at", -1).to_list(limit)
    return rows


@router.get("/categories")
async def list_categories(request: Request):
    """Untuk bel ringkas: kategori + jumlah belum dibaca."""
    user = await require_auth(request)
    db = get_db()
    scope = await category_scope(db, user)
    allowed = scope["allowed"]
    rows = await _fetch(db, user)
    counts = {k: {"total": 0, "unread": 0} for k in allowed}
    latest = []
    for r in rows:
        cat = effective_category(r, user, scope)
        if cat is None:
            continue
        unread = notif_is_unread_for(r, user)
        counts[cat]["total"] += 1
        if unread:
            counts[cat]["unread"] += 1
        if len(latest) < 3:
            latest.append(_present(r, cat, unread))
    return serialize_doc({
        "categories": [
            {**c, **counts[c["key"]]} for c in CATEGORIES if c["key"] in counts
        ],
        "total_unread": sum(v["unread"] for v in counts.values()),
        "total": sum(v["total"] for v in counts.values()),
        "latest": latest,
    })


@router.get("/categorized")
async def list_categorized(request: Request, category: Optional[str] = None,
                           unread_only: bool = Query(False), limit: int = Query(100, ge=1, le=300)):
    user = await require_auth(request)
    db = get_db()
    scope = await category_scope(db, user)
    allowed = scope["allowed"]
    if category and category not in allowed:
        raise HTTPException(403, "Kategori ini tidak diaktifkan untuk peran Anda.")
    rows = await _fetch(db, user, limit=300)
    out = []
    for r in rows:
        cat = effective_category(r, user, scope)
        if cat is None:
            continue
        if category and cat != category:
            continue
        unread = notif_is_unread_for(r, user)
        if unread_only and not unread:
            continue
        out.append(_present(r, cat, unread))
        if len(out) >= limit:
            break
    return serialize_doc({"items": out, "count": len(out), "allowed_categories": allowed,
                          "categories": [c for c in CATEGORIES if c["key"] in allowed]})


@router.get("/category-config")
async def read_config(request: Request):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in SUPER_ROLES:
        raise HTTPException(403, "Hanya admin yang boleh melihat konfigurasi notifikasi.")
    db = get_db()
    cfg = await get_matrix(db)
    roles = sorted(set(list(cfg["matrix"].keys()) +
                       [r for lst in PORTAL_ACCESS.values() for r in lst]))
    return serialize_doc({"categories": CATEGORIES, "roles": roles,
                          "matrix": cfg["matrix"], "updated_at": cfg.get("updated_at"),
                          "locked_categories": [PERSONAL_CATEGORY]})


@router.put("/category-config")
async def save_config(request: Request):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in SUPER_ROLES:
        raise HTTPException(403, "Hanya admin yang boleh mengubah konfigurasi notifikasi.")
    db = get_db()
    body = await request.json()
    matrix = body.get("matrix")
    if not isinstance(matrix, dict):
        raise HTTPException(400, "matrix wajib berupa objek {role: [kategori]}")
    clean = {}
    for role, cats in matrix.items():
        if not isinstance(cats, list):
            raise HTTPException(400, f"nilai untuk role '{role}' harus berupa daftar kategori")
        bad = [c for c in cats if c not in CATEGORY_KEYS]
        if bad:
            raise HTTPException(400, f"kategori tidak dikenal: {bad}")
        clean[str(role).lower()] = sorted(set(cats) | {PERSONAL_CATEGORY})
    for sr in SUPER_ROLES:
        clean[sr] = list(CATEGORY_KEYS)  # admin selalu menerima semuanya
    await db[CFG].update_one({"id": "default"}, {"$set": {
        "matrix": clean, "updated_at": datetime.now(timezone.utc),
        "updated_by": user.get("name") or user.get("id"),
    }}, upsert=True)
    return {"ok": True, "matrix": clean, "locked_categories": [PERSONAL_CATEGORY]}


@router.get("/my-category-prefs")
async def read_prefs(request: Request):
    user = await require_auth(request)
    db = get_db()
    scope = await category_scope(db, user)
    return serialize_doc({
        "muted_categories": scope["muted"],
        # kategori yang boleh diatur user (yang dibuka admin untuk perannya)
        "available": scope["base"],
        # yang benar-benar aktif sekarang (setelah pembisuan)
        "active": scope["allowed"],
        "locked_categories": [PERSONAL_CATEGORY],
        "categories": [c for c in CATEGORIES if c["key"] in scope["base"]],
    })


@router.put("/my-category-prefs")
async def save_prefs(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    muted = body.get("muted_categories") or []
    bad = [c for c in muted if c not in CATEGORY_KEYS]
    if bad:
        raise HTTPException(400, f"kategori tidak dikenal: {bad}")
    # "Untuk Saya" selalu aktif — permintaan membisukannya diabaikan (bukan error)
    clean = sorted({c for c in muted if c != PERSONAL_CATEGORY})
    await db[PREF].update_one({"user_id": user.get("id")}, {"$set": {
        "user_id": user.get("id"), "muted_categories": clean,
        "updated_at": datetime.now(timezone.utc),
    }}, upsert=True)
    return {"ok": True, "muted_categories": clean,
            "active": await allowed_categories(db, user),
            "locked_categories": [PERSONAL_CATEGORY]}
