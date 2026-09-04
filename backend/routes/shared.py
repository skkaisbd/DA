"""
Shared utilities for all route modules.
Common helpers, constants, and imports.
"""
import uuid
from datetime import datetime, timezone
from fastapi import Request  # untuk anotasi dependency require_portal_dep

# Valid PO statuses (staged lifecycle)
PO_STATUSES = [
    "Draft", "Confirmed", "Distributed", "In Production", 
    "Production Complete", "Variance Review", "Return Review",
    "Ready to Close", "Closed"
]

def new_id():
    return str(uuid.uuid4())

def now():
    return datetime.now(timezone.utc)

def parse_date(d):
    if not d:
        return None
    if isinstance(d, datetime):
        return d
    try:
        return datetime.fromisoformat(str(d).replace('Z', '+00:00'))
    except Exception:
        return None

def to_end_of_day(d):
    if isinstance(d, str):
        d = parse_date(d)
    if d:
        return d.replace(hour=23, minute=59, second=59, microsecond=999999)
    return None

async def enrich_with_product_photos(items, db):
    """Add product photo_url to items that have a product_name. Single batch query."""
    if not items:
        return items
    pnames = list({(it.get('product_name') or '').strip() for it in items if it.get('product_name')})
    photos = {}
    if pnames:
        async for prod in db.products.find(
            {'product_name': {'$in': pnames}}, {'_id': 0, 'product_name': 1, 'photo_url': 1}
        ):
            photos[prod['product_name']] = prod.get('photo_url', '')
    for item in items:
        pname = item.get('product_name', '')
        if pname:
            item['product_photo'] = photos.get(pname, '')
    return items

def _fmt_date(v):
    if not v:
        return '-'
    s = str(v)[:10]
    return s if s != 'None' else '-'

def _fmt_num(v):
    try:
        return f"{int(v):,}".replace(',', '.')
    except (ValueError, TypeError):
        return str(v or 0)

def _fmt_money(v):
    try:
        return f"Rp {int(v):,}".replace(',', '.')
    except (ValueError, TypeError):
        return 'Rp 0'


# ═══════════════════════════════════════════════════════════════════════════════
# PAGINATION HELPER
# ═══════════════════════════════════════════════════════════════════════════════

def get_pagination_params(request, default_limit=50, max_limit=200):
    """Extract pagination parameters from query string."""
    try:
        page = max(1, int(request.query_params.get("page", 1)))
        limit = min(max_limit, max(1, int(request.query_params.get("limit", default_limit))))
    except (ValueError, TypeError):
        page = 1
        limit = default_limit
    skip = (page - 1) * limit
    return page, limit, skip

def paginated_response(items, total, page, limit):
    """Create a standard paginated response."""
    total_pages = max(1, -(-total // limit))  # Ceiling division
    return {
        "items": items,
        "pagination": {
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        }
    }


# ═══════════════════════════════════════════════════════════════════════════════
# PORTAL RBAC HELPER
# ═══════════════════════════════════════════════════════════════════════════════

SUPER_ROLES = ("superadmin", "admin", "owner")
ALL_ROLE_PORTALS = ("self", "collaboration")

# Role → portal access (kept in sync with frontend portalAccess.js).
# Portal ids match portalNav.js keys. SUPER_ROLES get every portal.
PORTAL_ACCESS = {
    "management":     ["hr_manager", "manager_produksi", "manager_keuangan", "manager_hr", "manager_marketing"],
    "sysadmin":       [],   # super_admin + admin saja
    # 2026-08-08 — `ppic` DITAMBAHKAN. Owner memutuskan PPIC termasuk staf yang
    # berhak memakai pintu "Input Vendor CMT" (Portal CMT Override), tetapi PPIC
    # sama sekali TIDAK punya akses Portal Produksi/Maklon sehingga pintunya
    # tidak mungkin dijangkau — izin fitur ada, jalannya tidak. Cermin FE:
    # frontend/src/components/erp/portalAccess.js
    "production":     ["supervisor_produksi", "admin_produksi", "ppic", "operator", "spv_cuting", "operator_cuting", "supervisor"],
    "cutting":        ["spv_cuting", "operator_cuting", "supervisor_produksi", "admin_produksi", "admin_gudang"],
    # 2026-08-06 — Portal Pengadaan (procurement dilepas dari Gudang/Keuangan/
    # Aksesoris). Daftar peran SAMA dengan `_require_procurement` di
    # routes/procurement_suppliers.py + cermin FE portalAccess.js.
    # 2026-08-06 — `admin_aksesoris`/`spv_aksesoris` WAJIB ada: pintu "Request
    # Aksesoris" (pembelian) dipindah ke portal ini dan DIHAPUS dari Portal
    # Aksesoris, jadi tanpa mereka fitur itu hilang total bagi divisi aksesoris.
    # 2026-08-07 — APPROVER PR WAJIB BISA MASUK PORTAL INI. Temuan nyata: peran
    # yang berhak menyetujui PR (`supervisor_produksi`, `manager`, `dept_head`,
    # `manager_hr`, `manager_marketing`, `spv_packing`, `spv_cuting`) dan peran
    # tahap FINAL (`director`, `cfo`, `ceo`) tidak punya akses Portal Pengadaan,
    # sehingga mereka tidak bisa membuka layar "Permintaan Pengadaan" tempat
    # kotak persetujuan berada — rantai persetujuan mati sebelum dimulai.
    "procurement":    ["admin_pengadaan", "manager_pengadaan", "purchasing", "admin_gudang", "accounting", "staff_keuangan", "manager_keuangan", "manager_produksi", "supervisor", "admin_aksesoris", "spv_aksesoris",
                       "supervisor_produksi", "manager", "dept_head", "manager_hr", "manager_marketing", "spv_packing", "spv_cuting", "director", "cfo", "ceo"],
    "warehouse":      ["admin_gudang", "spv_packing", "tim_packing", "admin_aksesoris", "supervisor"],
    "accessories":    ["admin_aksesoris", "admin_gudang", "spv_aksesoris"],
    "finance":        ["accounting", "staff_keuangan", "manager_keuangan"],
    "hr":             ["hr", "hr_manager", "staff_hr"],
    "maklon":         ["admin_maklon", "admin_produksi", "supervisor_produksi", "ppic", "accounting"],
    "toko":           ["pic_toko", "pic_marketing", "staff_marketing", "marketing_kol", "cs_staff", "manager_marketing"],
    "rnd":            ["rnd_staff", "manager_produksi", "supervisor_produksi"],
    "assets":         ["accounting", "manager_keuangan", "staff_keuangan", "admin_gudang"],
    "collaboration":  [],   # all roles
    "self":           [],   # all roles
}
def check_portal_access(user, portal_id):
    """Check if a user role has access to a given portal.

    2026-08-05 — `PORTAL_ACCESS` di atas kini menjadi **bawaan**; bila owner sudah
    mengatur daftar portal pada dokumen role (`roles.portals`) ATAU pada user
    (`users.extra_portals`), konfigurasi itulah yang dipakai. Sinkron dengan
    `frontend/src/components/erp/portalAccess.js` (satu-satunya cermin FE).
    """
    role = (user.get("role", "") or "").lower()
    if role in SUPER_ROLES:
        return True
    if portal_id in ALL_ROLE_PORTALS:
        return True
    custom = user.get("_portals")
    if isinstance(custom, list) and custom:
        return portal_id in custom
    return role in PORTAL_ACCESS.get(portal_id, [])

def get_user_portals(user):
    """Get list of portal IDs the user can access (bawaan atau konfigurasi owner)."""
    role = (user.get("role", "") or "").lower()
    if role in SUPER_ROLES:
        return list(PORTAL_ACCESS.keys())
    custom = user.get("_portals")
    if isinstance(custom, list) and custom:
        return sorted(set(custom) | set(ALL_ROLE_PORTALS))
    return [pid for pid in PORTAL_ACCESS if pid in ALL_ROLE_PORTALS or role in PORTAL_ACCESS[pid]]


async def resolve_role_access(db, user: dict) -> dict:
    """Akses efektif user: portal + menu yang disembunyikan + izin aksi.

    Sumber (berlapis, tanpa duplikasi katalog):
      1. dokumen `roles` (field `portals`, `hidden_modules`) — diatur owner di
         Portal Administrasi Sistem → Manajemen Role.
      2. dokumen `users` (`extra_portals`, `hidden_modules`, `extra_permissions`)
         — kekecualian per orang.
      3. bila keduanya kosong → `PORTAL_ACCESS` bawaan di modul ini.
    """
    role = (user.get("role") or "").lower()
    u = await db.users.find_one({"id": user.get("id")}, {"_id": 0, "extra_portals": 1,
                                                        "hidden_modules": 1,
                                                        "extra_permissions": 1,
                                                        "role_id": 1}) or {}
    role_doc = None
    if u.get("role_id"):
        role_doc = await db.roles.find_one({"id": u["role_id"]}, {"_id": 0})
    if not role_doc:
        role_doc = await db.roles.find_one({"name": role}, {"_id": 0})
    portals = list((role_doc or {}).get("portals") or [])
    portals += [p for p in (u.get("extra_portals") or []) if p not in portals]
    hidden = list((role_doc or {}).get("hidden_modules") or [])
    hidden += [m for m in (u.get("hidden_modules") or []) if m not in hidden]
    user["_portals"] = portals
    return {
        "role": role,
        "is_super": role in SUPER_ROLES,
        "portals": get_user_portals(user),
        "hidden_modules": [] if role in SUPER_ROLES else hidden,
        "extra_permissions": list(u.get("extra_permissions") or []),
    }



# ─────────────────────────────────────────────────────────────────────────────
# RBAC read/write guard (SSOT: check_portal_access) — menutup BUG-RBAC-1.
# require_auth = autentikasi (login). require_portal = OTORISASI (akses portal).
# SUPER_ROLES otomatis lolos (via check_portal_access). Bypass izin eksplisit tetap
# dihormati (mis. "*", "<portal>.manage", "<portal>.view").
# ─────────────────────────────────────────────────────────────────────────────
async def require_portal(request, *portal_ids, allow_perms=()):
    """Tegakkan akses portal. Return user bila boleh, else HTTPException(403).

    portal_ids: satu atau lebih portal (lolos bila user punya akses SALAH SATU).
    """
    from fastapi import HTTPException  # lazy: hindari beban import saat modul dimuat
    from auth import require_auth       # lazy: hindari risiko circular import
    user = await require_auth(request)
    for pid in portal_ids:
        if check_portal_access(user, pid):
            return user
    perms = user.get("_permissions") or []
    if "*" in perms:
        return user
    wanted = set(allow_perms)
    for pid in portal_ids:
        wanted.update({f"{pid}.manage", f"{pid}.view"})
    if wanted & set(perms):
        return user
    raise HTTPException(403, f"Forbidden: butuh akses portal ({', '.join(portal_ids)}).")


def require_portal_dep(*portal_ids, allow_perms=()):
    """Factory dependency FastAPI untuk dipasang di APIRouter(dependencies=[...])
    ATAU per-endpoint (Depends). Menegakkan require_portal untuk SEMUA endpoint router."""
    async def _dep(request: Request):
        await require_portal(request, *portal_ids, allow_perms=allow_perms)
    return _dep


# ─────────────────────────────────────────────────────────────────────────────
# IZIN AKSI / APPROVAL (action-level RBAC) — SATU mesin untuk seluruh route.
#
# MODEL "FALLBACK AMAN" (keputusan owner 2026-08-06):
#   1. SUPER_ROLES atau izin "*"                 -> selalu lolos
#   2. role punya salah satu izin yang diminta   -> lolos
#   3. role BELUM dikonfigurasi izinnya (kosong) -> pakai daftar role legacy
#      (`legacy_roles`) supaya fitur lama TIDAK mati mendadak
#   4. selain itu                                -> 403
#
# Konsekuensi yang disengaja: begitu owner mencentang izin untuk sebuah role,
# daftar izin itulah yang berlaku (aturan legacy berhenti dipakai untuk role
# tersebut). UI Peran & Hak Akses memberi peringatan jelas soal ini.
# ─────────────────────────────────────────────────────────────────────────────
def user_permissions(user) -> set:
    """Izin efektif user: izin role + izin tambahan per orang."""
    perms = set(user.get("_permissions") or [])
    if not perms:
        perms = set(user.get("permissions") or [])
    perms |= set(user.get("_extra_permissions") or [])
    return {p for p in perms if p}


def perms_configured(user) -> bool:
    """True bila owner sudah mengatur izin untuk role user (bukan role kosong)."""
    if user.get("_role_perms") is not None:
        return bool(user.get("_role_perms"))
    # Fallback bila require_auth versi lama belum mengisi `_role_perms`.
    return bool(user.get("_permissions"))


def has_perm(user, *keys) -> bool:
    """Cek izin murni (tanpa fallback role legacy)."""
    role = (user.get("role") or "").lower()
    if role in SUPER_ROLES:
        return True
    perms = user_permissions(user)
    if "*" in perms:
        return True
    return bool(perms & {k for k in keys if k})


def can_act(user, *keys, legacy_roles=(), legacy_any=False) -> bool:
    """Cek izin dengan fallback aman (lihat model di atas). Tidak melempar error.

    legacy_roles : daftar role lama yang tetap boleh SELAMA izin role belum diatur.
    legacy_any   : True bila endpoint ini dulunya terbuka untuk SEMUA user login
                   (mis. put-away gudang). Selama izin role belum diatur, perilaku
                   lama dipertahankan; begitu owner mengatur izin, gerbang aktif.
    """
    if has_perm(user, *keys):
        return True
    if perms_configured(user):
        return False
    if legacy_any:
        return True
    role = (user.get("role") or "").lower()
    return role in {str(r).lower() for r in legacy_roles}


def assert_can_act(user, *keys, portal=None, legacy_roles=(), legacy_any=False,
                   what="melakukan aksi ini"):
    """Gerbang keputusan (approve/reject/confirm) untuk handler ber-`Depends(require_auth)`.

    2026-08-07 — audit RBAC: puluhan endpoint keputusan hanya butuh "sudah login"
    sehingga staf mana pun bisa menyetujui dokumen orang lain. Helper ini memakai
    model aman `can_act`: admin/owner selalu lolos, dan selama izin sebuah role
    belum diatur owner, role lama tetap boleh (fitur tidak mati mendadak).
    """
    from fastapi import HTTPException  # lazy
    roles = tuple(legacy_roles) + (tuple(PORTAL_ACCESS.get(portal, ())) if portal else ())
    if not can_act(user, *keys, legacy_roles=roles, legacy_any=legacy_any):
        raise HTTPException(403, f"Akses ditolak: Anda tidak berhak {what}.")
    return user


async def require_perm(request, *keys, legacy_roles=(), legacy_any=False, message=None):
    """Gerbang aksi/approval. Return user bila boleh, else HTTPException(403)."""
    from fastapi import HTTPException  # lazy
    from auth import require_auth       # lazy: hindari circular import
    user = await require_auth(request)
    if can_act(user, *keys, legacy_roles=legacy_roles, legacy_any=legacy_any):
        return user
    label = ", ".join([k for k in keys if k]) or "izin khusus"
    raise HTTPException(403, message or f"Akses ditolak: butuh izin ({label}).")


def require_perm_dep(*keys, legacy_roles=(), legacy_any=False, message=None):
    """Factory dependency FastAPI untuk memasang require_perm di router/endpoint."""
    async def _dep(request: Request):
        return await require_perm(request, *keys, legacy_roles=legacy_roles,
                                  legacy_any=legacy_any, message=message)
    return _dep
