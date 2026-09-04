"""
Employee Expense Category Master — Routes
CV. Dewi Aditya — Employee Expense Management (EEM) Phase 5A

Master data kategori expense yang bisa dikelola Admin/Finance dari UI.
Menambah fleksibilitas di atas mekanisme COA-driven existing.

Collection: employee_expense_categories
Schema: {
    id, code(optional), name, description, is_active,
    created_at, updated_at, created_by, updated_by
}

Prefix: /api/hr/expenses

Endpoints:
  GET    /master-categories              — list semua (aktif default)
  POST   /master-categories              — create kategori baru (admin/finance)
  PUT    /master-categories/{id}         — update (admin/finance)
  DELETE /master-categories/{id}         — soft-delete is_active=false (admin/finance)
  POST   /master-categories/seed-default — seed kategori default jika kosong (admin)
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import logging
import uuid

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/hr/expenses', tags=['EEM-Category-Master'])

ADMIN_ROLES = ('superadmin', 'admin', 'owner', 'finance')

# Default categories yang di-seed saat collection kosong
DEFAULT_CATEGORIES = [
    {'code': 'CAT-001', 'name': 'Transportasi',             'description': 'Biaya transportasi (angkutan umum, taxi, ojol)'},
    {'code': 'CAT-002', 'name': 'Akomodasi',                'description': 'Biaya hotel dan penginapan'},
    {'code': 'CAT-003', 'name': 'Konsumsi / Makan',         'description': 'Biaya makan dan konsumsi'},
    {'code': 'CAT-004', 'name': 'Representasi / Entertainment', 'description': 'Biaya representasi dan entertainment klien'},
    {'code': 'CAT-005', 'name': 'Komunikasi',               'description': 'Biaya telepon, internet, pulsa'},
    {'code': 'CAT-006', 'name': 'ATK / Perlengkapan',       'description': 'Alat tulis kantor dan perlengkapan kerja'},
    {'code': 'CAT-007', 'name': 'Parkir / Tol',             'description': 'Biaya parkir dan tol'},
    {'code': 'CAT-008', 'name': 'Biaya Training / Seminar', 'description': 'Biaya pelatihan, seminar, kursus'},
    {'code': 'CAT-009', 'name': 'Biaya Kesehatan',          'description': 'Biaya medis dan kesehatan karyawan'},
    {'code': 'CAT-010', 'name': 'Sewa Kendaraan',           'description': 'Biaya sewa kendaraan operasional'},
    {'code': 'CAT-011', 'name': 'Perbaikan / Maintenance',  'description': 'Biaya perbaikan dan maintenance kecil'},
    {'code': 'CAT-012', 'name': 'Biaya Pengiriman / Kurir', 'description': 'Biaya pengiriman paket dan dokumen'},
    {'code': 'CAT-013', 'name': 'Lain-lain',                'description': 'Pengeluaran lainnya yang tidak termasuk kategori di atas'},
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ser(doc: dict) -> dict:
    if not doc:
        return {}
    d = serialize_doc(doc)
    return d


# ── Pydantic Models ────────────────────────────────────────────────────────────

class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    code: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=500)
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    code: Optional[str] = Field(None, max_length=20)
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get('/master-categories')
async def list_master_categories(
    include_inactive: bool = Query(False, description='Sertakan kategori nonaktif'),
    user: dict = Depends(require_auth),
):
    """List kategori expense dari master data."""
    db = get_db()
    q = {} if include_inactive else {'is_active': True}
    cats = await db.employee_expense_categories.find(q, {'_id': 0}).sort('name', 1).to_list(200)
    return {
        'items': [_ser(c) for c in cats],
        'total': len(cats),
    }


@router.post('/master-categories')
async def create_master_category(
    body: CategoryCreate,
    user: dict = Depends(require_auth),
):
    """Buat kategori expense baru. Hanya admin/finance."""
    if user.get('role') not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya admin/finance yang dapat membuat kategori.')
    db = get_db()

    # Cek duplikat nama (case-insensitive)
    existing = await db.employee_expense_categories.find_one(
        {'name': {'$regex': f'^{body.name}$', '$options': 'i'}},
        {'_id': 0, 'id': 1},
    )
    if existing:
        raise HTTPException(400, f'Kategori dengan nama "{body.name}" sudah ada.')

    doc = {
        'id': str(uuid.uuid4()),
        'code': (body.code or '').strip() or None,
        'name': body.name.strip(),
        'description': (body.description or '').strip() or None,
        'is_active': body.is_active,
        'created_at': _now(),
        'updated_at': _now(),
        'created_by': user['id'],
        'updated_by': user['id'],
    }
    await db.employee_expense_categories.insert_one(doc)

    await log_activity(user['id'], user.get('name', user.get('email')), 
                       'CREATE_EEM_CATEGORY', 'employee_expense_categories', 
                       f"Created category: {doc['name']}")
    logger.info(f"[EEM-CATEGORY] Created: {doc['name']} by {user.get('email')}")
    return _ser(doc)


@router.put('/master-categories/{cat_id}')
async def update_master_category(
    cat_id: str,
    body: CategoryUpdate,
    user: dict = Depends(require_auth),
):
    """Update kategori expense. Hanya admin/finance."""
    if user.get('role') not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya admin/finance yang dapat mengubah kategori.')
    db = get_db()

    existing = await db.employee_expense_categories.find_one({'id': cat_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Kategori tidak ditemukan.')

    updates: dict = {'updated_at': _now(), 'updated_by': user['id']}
    if body.name is not None:
        # Cek duplikat nama (exclude current)
        dup = await db.employee_expense_categories.find_one(
            {'name': {'$regex': f'^{body.name}$', '$options': 'i'}, 'id': {'$ne': cat_id}},
            {'_id': 0, 'id': 1},
        )
        if dup:
            raise HTTPException(400, f'Kategori dengan nama "{body.name}" sudah ada.')
        updates['name'] = body.name.strip()
    if body.code is not None:
        updates['code'] = (body.code or '').strip() or None
    if body.description is not None:
        updates['description'] = (body.description or '').strip() or None
    if body.is_active is not None:
        updates['is_active'] = body.is_active

    await db.employee_expense_categories.update_one({'id': cat_id}, {'$set': updates})
    updated = await db.employee_expense_categories.find_one({'id': cat_id}, {'_id': 0})
    await log_activity(user['id'], user.get('name', user.get('email')), 
                       'UPDATE_EEM_CATEGORY', 'employee_expense_categories', 
                       f"Updated category: {existing['name']}")
    return _ser(updated)


@router.delete('/master-categories/{cat_id}')
async def delete_master_category(
    cat_id: str,
    user: dict = Depends(require_auth),
):
    """Soft-delete kategori (set is_active=false). Hanya admin/finance."""
    if user.get('role') not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya admin/finance yang dapat menonaktifkan kategori.')
    db = get_db()

    existing = await db.employee_expense_categories.find_one({'id': cat_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Kategori tidak ditemukan.')

    await db.employee_expense_categories.update_one(
        {'id': cat_id},
        {'$set': {'is_active': False, 'updated_at': _now(), 'updated_by': user['id']}},
    )
    await log_activity(user['id'], user.get('name', user.get('email')), 
                       'DEACTIVATE_EEM_CATEGORY', 'employee_expense_categories', 
                       f"Deactivated category: {existing['name']}")
    return {'ok': True, 'message': f'Kategori "{existing["name"]}" dinonaktifkan.'}


@router.post('/master-categories/seed-default')
async def seed_default_categories(
    user: dict = Depends(require_auth),
):
    """
    Seed kategori default jika collection masih kosong atau belum memiliki semua default.
    Idempotent — aman dipanggil berkali-kali.
    """
    if user.get('role') not in ADMIN_ROLES:
        raise HTTPException(403, 'Hanya admin yang dapat menjalankan seed.')
    db = get_db()

    seeded = 0
    skipped = 0
    for cat in DEFAULT_CATEGORIES:
        existing = await db.employee_expense_categories.find_one(
            {'name': {'$regex': f'^{cat["name"]}$', '$options': 'i'}},
        )
        if existing:
            skipped += 1
            continue
        doc = {
            'id': str(uuid.uuid4()),
            'code': cat.get('code'),
            'name': cat['name'],
            'description': cat.get('description', ''),
            'is_active': True,
            'created_at': _now(),
            'updated_at': _now(),
            'created_by': user['id'],
            'updated_by': user['id'],
        }
        await db.employee_expense_categories.insert_one(doc)
        seeded += 1

    logger.info(f"[EEM-CATEGORY-SEED] Seeded {seeded}, skipped {skipped} by {user.get('email')}")
    return {
        'ok': True,
        'seeded': seeded,
        'skipped': skipped,
        'message': f'{seeded} kategori baru di-seed, {skipped} sudah ada.',
    }
