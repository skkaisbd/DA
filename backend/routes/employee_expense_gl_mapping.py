"""
Employee Expense GL Mapping Configuration
CV. Dewi Aditya — Employee Expense Management (EEM) Phase 4/5C

Konfigurasi mapping kategori expense → GL account code.
Digunakan untuk split posting saat settlement.

Collection: employee_expense_gl_mappings
Schema: {
    id, category, gl_account_code, gl_account_name, 
    is_active, created_at, updated_at, updated_by
}

Prefix: /api/hr/expenses/gl-mappings

Endpoints:
  GET    /gl-mappings                    — list all mappings
  POST   /gl-mappings                    — create mapping
  PUT    /gl-mappings/{id}               — update mapping
  DELETE /gl-mappings/{id}               — delete mapping
  GET    /gl-mappings/resolve/{category} — resolve GL account for category
  POST   /gl-mappings/bulk-resolve       — resolve multiple categories
  POST   /gl-mappings/seed-default       — seed default GL mapping untuk semua kategori master (Phase 5C)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/hr/expenses', tags=['GL-Mapping'])

# ── Default GL Account ─────────────────────────────────────────────────────────
DEFAULT_TRAVEL_EXPENSE_GL = '6-3400'  # Biaya Perjalanan Dinas (fallback)

ADMIN_ROLES = ('superadmin', 'admin', 'owner', 'finance')


# ── Helpers ────────────────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc)


def _serialize(doc: dict) -> dict:
    if not doc:
        return {}
    d = serialize_doc(doc)
    for key in ('created_at', 'updated_at'):
        if key in d and isinstance(d[key], datetime):
            d[key] = d[key].isoformat()
    return d


# ── Models ─────────────────────────────────────────────────────────────────────
class GLMappingCreate(BaseModel):
    category: str = Field(..., description='Kategori expense (e.g., Transportasi, Konsumsi)')
    gl_account_code: str = Field(..., description='GL account code (e.g., 6-3410)')
    gl_account_name: str = Field(..., description='Nama akun GL')
    is_active: bool = True


class GLMappingUpdate(BaseModel):
    category: Optional[str] = None
    gl_account_code: Optional[str] = None
    gl_account_name: Optional[str] = None
    is_active: Optional[bool] = None


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get('/gl-mappings')
async def list_gl_mappings(
    is_active: Optional[bool] = Query(None),
    user: dict = Depends(require_auth),
):
    """List semua GL mappings (Admin/Finance only)."""
    role = (user.get('role') or '').lower()
    if role not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya Admin/Finance yang bisa akses GL mapping')

    db = get_db()
    q = {}
    if is_active is not None:
        q['is_active'] = is_active

    docs = await db.employee_expense_gl_mappings.find(q, {'_id': 0}).sort('category', 1).to_list(100)
    return {'total': len(docs), 'items': [_serialize(d) for d in docs]}


@router.post('/gl-mappings', status_code=201)
async def create_gl_mapping(body: GLMappingCreate, user: dict = Depends(require_auth)):
    """Buat mapping baru (Admin/Finance only)."""
    role = (user.get('role') or '').lower()
    if role not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya Admin/Finance yang bisa buat mapping')

    db = get_db()

    # Check duplicate category
    existing = await db.employee_expense_gl_mappings.find_one({'category': body.category}, {'_id': 0})
    if existing:
        raise HTTPException(400, f'Mapping untuk kategori "{body.category}" sudah ada')

    # Verify GL account exists in COA
    coa = await db.rahaza_coa_accounts.find_one({'code': body.gl_account_code}, {'_id': 0})
    if not coa:
        raise HTTPException(400, f'GL account code {body.gl_account_code} tidak ditemukan di COA')

    now = _now()
    doc = {
        'id': str(uuid.uuid4()),
        'category': body.category,
        'gl_account_code': body.gl_account_code,
        'gl_account_name': body.gl_account_name,
        'is_active': body.is_active,
        'created_at': now,
        'updated_at': now,
        'updated_by': user.get('id'),
        'updated_by_name': user.get('name'),
    }

    await db.employee_expense_gl_mappings.insert_one(doc)
    await log_activity(user.get('id'), user.get('name'), 'create', 'gl_mapping',
                       f'Buat GL mapping: {body.category} → {body.gl_account_code}')

    return _serialize(doc)


@router.put('/gl-mappings/{mapping_id}')
async def update_gl_mapping(mapping_id: str, body: GLMappingUpdate, user: dict = Depends(require_auth)):
    """Update mapping (Admin/Finance only)."""
    role = (user.get('role') or '').lower()
    if role not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya Admin/Finance yang bisa update mapping')

    db = get_db()
    doc = await db.employee_expense_gl_mappings.find_one({'id': mapping_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Mapping tidak ditemukan')

    updates = {}
    if body.category is not None:
        updates['category'] = body.category
    if body.gl_account_code is not None:
        # Verify GL account exists
        coa = await db.rahaza_coa_accounts.find_one({'code': body.gl_account_code}, {'_id': 0})
        if not coa:
            raise HTTPException(400, f'GL account code {body.gl_account_code} tidak ditemukan di COA')
        updates['gl_account_code'] = body.gl_account_code
    if body.gl_account_name is not None:
        updates['gl_account_name'] = body.gl_account_name
    if body.is_active is not None:
        updates['is_active'] = body.is_active

    if not updates:
        raise HTTPException(400, 'Tidak ada perubahan')

    updates['updated_at'] = _now()
    updates['updated_by'] = user.get('id')
    updates['updated_by_name'] = user.get('name')

    await db.employee_expense_gl_mappings.update_one({'id': mapping_id}, {'$set': updates})
    await log_activity(user.get('id'), user.get('name'), 'update', 'gl_mapping',
                       f'Update GL mapping: {doc.get("category")}')

    updated_doc = await db.employee_expense_gl_mappings.find_one({'id': mapping_id}, {'_id': 0})
    return _serialize(updated_doc)


@router.delete('/gl-mappings/{mapping_id}')
async def delete_gl_mapping(mapping_id: str, user: dict = Depends(require_auth)):
    """Hapus mapping (Admin/Finance only)."""
    role = (user.get('role') or '').lower()
    if role not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya Admin/Finance yang bisa hapus mapping')

    db = get_db()
    doc = await db.employee_expense_gl_mappings.find_one({'id': mapping_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Mapping tidak ditemukan')

    await db.employee_expense_gl_mappings.delete_one({'id': mapping_id})
    await log_activity(user.get('id'), user.get('name'), 'delete', 'gl_mapping',
                       f'Hapus GL mapping: {doc.get("category")}')

    return {'ok': True, 'deleted': mapping_id}


@router.get('/gl-mappings/resolve/{category}')
async def resolve_gl_account(category: str, user: dict = Depends(require_auth)):
    """Resolve GL account code untuk kategori tertentu. Return default jika tidak ada mapping."""
    db = get_db()
    mapping = await db.employee_expense_gl_mappings.find_one(
        {'category': category, 'is_active': True}, {'_id': 0}
    )

    if mapping:
        return {
            'category': category,
            'gl_account_code': mapping.get('gl_account_code'),
            'gl_account_name': mapping.get('gl_account_name'),
            'source': 'mapping',
        }
    else:
        return {
            'category': category,
            'gl_account_code': DEFAULT_TRAVEL_EXPENSE_GL,
            'gl_account_name': 'Biaya Perjalanan Dinas (Default)',
            'source': 'default',
        }


@router.post('/gl-mappings/bulk-resolve')
async def bulk_resolve_gl_accounts(
    categories: List[str],
    user: dict = Depends(require_auth),
):
    """Resolve multiple categories sekaligus. Used untuk settlement posting."""
    db = get_db()
    mappings = await db.employee_expense_gl_mappings.find(
        {'category': {'$in': categories}, 'is_active': True}, {'_id': 0}
    ).to_list(100)

    mapping_dict = {m['category']: m for m in mappings}
    results = []

    for cat in categories:
        if cat in mapping_dict:
            m = mapping_dict[cat]
            results.append({
                'category': cat,
                'gl_account_code': m.get('gl_account_code'),
                'gl_account_name': m.get('gl_account_name'),
                'source': 'mapping',
            })
        else:
            results.append({
                'category': cat,
                'gl_account_code': DEFAULT_TRAVEL_EXPENSE_GL,
                'gl_account_name': 'Biaya Perjalanan Dinas (Default)',
                'source': 'default',
            })

    return {'items': results}


# ── Phase 5C: Seed Default GL Mapping ────────────────────────────────────────
# Default mapping: kategori → GL account code
DEFAULT_GL_SEED = {
    'Transportasi':                  ('6-3300', 'Biaya Transportasi'),
    'Akomodasi':                     ('6-3400', 'Biaya Perjalanan Dinas'),
    'Konsumsi / Makan':              ('6-3500', 'Biaya Representasi / Konsumsi'),
    'Representasi / Entertainment':  ('6-3500', 'Biaya Representasi / Konsumsi'),
    'Komunikasi':                    ('6-3600', 'Biaya Komunikasi'),
    'ATK / Perlengkapan':            ('6-3700', 'Biaya ATK & Perlengkapan'),
    'Parkir / Tol':                  ('6-3300', 'Biaya Transportasi'),
    'Biaya Training / Seminar':      ('6-3800', 'Biaya Pendidikan & Pelatihan'),
    'Biaya Kesehatan':               ('6-3900', 'Biaya Kesehatan Karyawan'),
    'Sewa Kendaraan':                ('6-3400', 'Biaya Perjalanan Dinas'),
    'Perbaikan / Maintenance':       ('6-3100', 'Biaya Pemeliharaan'),
    'Biaya Pengiriman / Kurir':      ('6-3200', 'Biaya Pengiriman'),
    'Lain-lain':                     ('6-3999', 'Biaya Lain-lain'),
}


@router.post('/gl-mappings/seed-default')
async def seed_default_gl_mappings(
    user: dict = Depends(require_auth),
):
    """
    Seed default GL mapping untuk semua kategori dari master.
    Hanya buat mapping untuk kategori yang BELUM punya mapping.
    Idempotent — aman dipanggil berkali-kali (Phase 5C).
    """
    if user.get('role') not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya admin/finance yang dapat menjalankan seed.')
    db = get_db()

    # Ambil semua kategori master yang aktif
    master_cats = await db.employee_expense_categories.find(
        {'is_active': True}, {'_id': 0, 'name': 1}
    ).to_list(200)

    # Fallback: gunakan DEFAULT_GL_SEED keys jika master kosong
    if master_cats:
        cat_names = [c['name'] for c in master_cats]
    else:
        cat_names = list(DEFAULT_GL_SEED.keys())

    seeded = 0
    skipped = 0
    warnings = []

    for cat_name in cat_names:
        # Cek apakah mapping sudah ada
        existing_mapping = await db.employee_expense_gl_mappings.find_one(
            {'category': cat_name, 'is_active': True},
        )
        if existing_mapping:
            skipped += 1
            continue

        # Cari default GL code
        if cat_name in DEFAULT_GL_SEED:
            gl_code, gl_name = DEFAULT_GL_SEED[cat_name]
        else:
            # Gunakan fallback default
            gl_code, gl_name = DEFAULT_TRAVEL_EXPENSE_GL, 'Biaya Perjalanan Dinas (Default)'
            warnings.append(f'Kategori "{cat_name}" tidak ada di DEFAULT_GL_SEED, pakai fallback.')

        # Validasi COA code ada di DB (opsional, soft validation)
        coa_acc = await db.rahaza_coa_accounts.find_one({'code': gl_code}, {'_id': 0, 'name': 1})
        if coa_acc:
            gl_name = coa_acc.get('name', gl_name)

        now_str = datetime.now(timezone.utc).isoformat()
        doc = {
            'id': str(uuid.uuid4()),
            'category': cat_name,
            'gl_account_code': gl_code,
            'gl_account_name': gl_name,
            'is_active': True,
            'created_at': now_str,
            'updated_at': now_str,
            'updated_by': user['id'],
        }
        await db.employee_expense_gl_mappings.insert_one(doc)
        seeded += 1

    logger.info(f"[GL-MAPPING-SEED] Seeded {seeded}, skipped {skipped} by {user.get('email')}")
    return {
        'ok': True,
        'seeded': seeded,
        'skipped': skipped,
        'warnings': warnings,
        'message': f'{seeded} mapping baru dibuat, {skipped} sudah ada.',
    }
