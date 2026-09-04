"""Shared RBAC + master-data resolution helpers for the ported SOMMERVILLE
production engine (Fase 2 adopsi — lihat /app/memory/SOMMERVILLE_ADOPTION_PLAN.md).

RBAC-1 = B (locked): SOMMERVILLE role strings are remapped to DA roles:
  admin  → admin, admin_maklon            (superadmin always bypasses via check_role)
  vendor → vendor, cmt_vendor             (identity via vendor_id ATAU cmt_vendor_id)
  buyer  → klien_maklon (read-only, HANYA lewat /api/maklon-client/*)

Master data resolution (F-2 = Option A, satu engine):
  vendor_id → `garments` (SOMMERVILLE master) ATAU `vendor_partners` (CMT vendor DA)
  buyer_id  → `buyers` (SOMMERVILLE master) ATAU `dewi_maklon_clients` (klien maklon DA)
"""
from fastapi import HTTPException, Request

PROD_ADMIN_ROLES = [
    'admin', 'admin_maklon', 'admin_produksi',
    'supervisor_produksi', 'owner', 'manager', 'ppic',
]
# Catatan: `superadmin` selalu bypass via check_role().
# Perluasan ini memperbaiki inkonsistensi: GET /production-pos terbuka utk semua user
# login, tetapi CREATE/UPDATE dulu hanya admin/admin_maklon → role manajemen produksi
# (owner/admin_produksi/supervisor_produksi) kena 403 "Forbidden" saat simpan PO.
PROD_VENDOR_ROLES = ['vendor', 'cmt_vendor']


def is_vendor(user: dict) -> bool:
    return (user.get('role') or '') in PROD_VENDOR_ROLES


def vendor_identity(user: dict):
    """Vendor entity id for the logged-in vendor user (SOMMERVILLE vendor_id
    or DA cmt_vendor_id → vendor_partners.id)."""
    return user.get('vendor_id') or user.get('cmt_vendor_id')


EXTERNAL_ROLES = ('klien_maklon',) + tuple(PROD_VENDOR_ROLES)
# Vendor CMT masih boleh membaca daftar selisih kirim miliknya (endpoint sudah ter-scope vendor).
_VENDOR_ALLOWED_PATHS = ('/api/prod/short-shipments',)


async def deny_external_dep(request: Request):
    """Dependency router: klien maklon & vendor CMT TIDAK boleh menyentuh endpoint admin
    maklon (`/api/dewi/maklon/*`, `/api/prod/cmt-receipts*`, tagihan CMT). Klien memakai
    `/api/maklon-client/*`, vendor memakai engine yang ter-scope `vendor_id` (audit M-01/M-02)."""
    from auth import require_auth
    user = await require_auth(request)
    role = user.get('role') or ''
    if role in EXTERNAL_ROLES:
        if role in PROD_VENDOR_ROLES and request.method == 'GET' \
                and request.url.path.rstrip('/') in _VENDOR_ALLOWED_PATHS:
            return user
        raise HTTPException(403, 'Akses ditolak: endpoint ini khusus staf DA. Klien memakai '
                                 '/api/maklon-client/*, vendor CMT memakai portal vendor.')
    return user


def deny_klien(user: dict):
    """klien_maklon is read-only and may ONLY use /api/maklon-client/* endpoints."""
    if (user.get('role') or '') == 'klien_maklon':
        raise HTTPException(403, 'Akses klien maklon hanya melalui endpoint tracking (/api/maklon-client/*)')


def require_write_actor(user, check_role_fn):
    """Guard for endpoints that were open to any authenticated user in
    SOMMERVILLE (vendor OR admin submit paths)."""
    if is_vendor(user):
        return
    if check_role_fn(user, PROD_ADMIN_ROLES):
        return
    raise HTTPException(403, 'Forbidden')


async def resolve_vendor_doc(db, vendor_id):
    """Vendor master lookup: garments (SOMMERVILLE) → vendor_partners (DA CMT).
    Returns a doc that always carries `garment_name`/`garment_code` keys so the
    ported code keeps working unchanged."""
    if not vendor_id:
        return None
    doc = await db.garments.find_one({'id': vendor_id})
    if doc:
        return doc
    vp = await db.vendor_partners.find_one({'id': vendor_id})
    if vp:
        vp.setdefault('garment_name', vp.get('name', ''))
        vp.setdefault('garment_code', vp.get('code', ''))
        return vp
    return None


async def resolve_buyer_name(db, buyer_id, default=''):
    """Buyer/customer master lookup: buyers (SOMMERVILLE) → dewi_maklon_clients (DA)."""
    if not buyer_id:
        return default
    b = await db.buyers.find_one({'id': buyer_id})
    if b:
        return b.get('buyer_name', default)
    c = await db.dewi_maklon_clients.find_one({'id': buyer_id})
    if c:
        return c.get('name', default)
    return default
