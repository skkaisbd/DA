"""
Employee Per Diem Rates — Admin Configuration
CV. Dewi Aditya — Employee Expense Management (EEM)

Konfigurasi uang harian (per diem) per tipe destinasi.

Prefix: /api/hr/expenses

Endpoints:
  GET  /per-diem-rates            — list all rates
  POST /per-diem-rates            — create rate config
  PUT  /per-diem-rates/{id}       — update rate
  DELETE /per-diem-rates/{id}     — delete (soft)
  GET  /per-diem-rates/preview    — preview all destination types
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import logging
import uuid
from utils.waktu import now_wib

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/hr/expenses', tags=['Employee-PerDiem'])

DESTINATION_TYPES = ['dalam_kota', 'luar_kota', 'luar_negeri']
DESTINATION_LABELS = {
    'dalam_kota': 'Dalam Kota',
    'luar_kota': 'Luar Kota',
    'luar_negeri': 'Luar Negeri',
}

# Default rates (IDR)
DEFAULT_RATES = {
    'dalam_kota': {'daily_rate': 100_000, 'meal_allowance': 50_000, 'transport_allowance': 50_000},
    'luar_kota':  {'daily_rate': 300_000, 'meal_allowance': 75_000,  'transport_allowance': 100_000},
    'luar_negeri': {'daily_rate': 600_000, 'meal_allowance': 150_000, 'transport_allowance': 200_000},
}


def _now():
    return datetime.now(timezone.utc)


def _admin_only(user: dict):
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'hr'):
        raise HTTPException(403, 'Hanya admin/HR yang dapat mengubah konfigurasi Per Diem')


class PerDiemCreate(BaseModel):
    destination_type: str
    label: Optional[str] = ''
    daily_rate: float = Field(ge=0)
    meal_allowance: float = Field(default=0, ge=0)
    transport_allowance: float = Field(default=0, ge=0)
    effective_date: Optional[str] = ''
    notes: Optional[str] = ''


class PerDiemUpdate(BaseModel):
    label: Optional[str] = None
    daily_rate: Optional[float] = Field(default=None, ge=0)
    meal_allowance: Optional[float] = Field(default=None, ge=0)
    transport_allowance: Optional[float] = Field(default=None, ge=0)
    effective_date: Optional[str] = None
    is_active: Optional[bool] = None
    notes: Optional[str] = None


@router.get('/per-diem-rates')
async def list_per_diem_rates(user: dict = Depends(require_auth)):
    """List konfigurasi per diem rates."""
    db = get_db()
    docs = await db.employee_per_diem_rates.find({}, {'_id': 0}).sort('destination_type', 1).to_list(100)
    # Pastikan semua 3 tipe ada (isi default jika belum dikonfigurasi)
    configured = {d['destination_type'] for d in docs}
    for dt in DESTINATION_TYPES:
        if dt not in configured:
            defaults = DEFAULT_RATES.get(dt, {})
            docs.append({
                'id': None,
                'destination_type': dt,
                'label': DESTINATION_LABELS.get(dt, dt),
                'daily_rate': defaults.get('daily_rate', 0),
                'meal_allowance': defaults.get('meal_allowance', 0),
                'transport_allowance': defaults.get('transport_allowance', 0),
                'effective_date': '',
                'is_active': True,
                'notes': 'Default rate — belum dikonfigurasi',
                'is_default': True,
                'created_at': None,
            })
    return {'items': [serialize_doc(d) for d in docs]}


@router.post('/per-diem-rates', status_code=201)
async def create_per_diem_rate(body: PerDiemCreate, user: dict = Depends(require_auth)):
    """Buat konfigurasi per diem baru."""
    _admin_only(user)
    db = get_db()
    if body.destination_type not in DESTINATION_TYPES:
        raise HTTPException(400, f"destination_type harus salah satu: {DESTINATION_TYPES}")
    # Nonaktifkan yang lama untuk tipe yang sama
    await db.employee_per_diem_rates.update_many(
        {'destination_type': body.destination_type},
        {'$set': {'is_active': False}}
    )
    now = _now()
    doc = {
        'id': str(uuid.uuid4()),
        'destination_type': body.destination_type,
        'label': body.label or DESTINATION_LABELS.get(body.destination_type, body.destination_type),
        'daily_rate': body.daily_rate,
        'meal_allowance': body.meal_allowance,
        'transport_allowance': body.transport_allowance,
        'effective_date': body.effective_date or now_wib().strftime('%Y-%m-%d'),
        'is_active': True,
        'notes': body.notes or '',
        'created_by': user.get('id'),
        'created_by_name': user.get('name'),
        'created_at': now,
        'updated_at': now,
    }
    await db.employee_per_diem_rates.insert_one(doc)
    await log_activity(user.get('id'), user.get('name'), 'create', 'per_diem_rate',
                       f"Buat per diem {body.destination_type}: Rp {body.daily_rate:,.0f}/hari")
    return serialize_doc(doc)


@router.put('/per-diem-rates/{rate_id}')
async def update_per_diem_rate(rate_id: str, body: PerDiemUpdate, user: dict = Depends(require_auth)):
    """Update konfigurasi per diem."""
    _admin_only(user)
    db = get_db()
    existing = await db.employee_per_diem_rates.find_one({'id': rate_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Rate tidak ditemukan')
    upd: dict = {'updated_at': _now()}
    for field in ('label', 'daily_rate', 'meal_allowance', 'transport_allowance', 'effective_date', 'is_active', 'notes'):
        v = getattr(body, field)
        if v is not None:
            upd[field] = v
    await db.employee_per_diem_rates.update_one({'id': rate_id}, {'$set': upd})
    updated = await db.employee_per_diem_rates.find_one({'id': rate_id}, {'_id': 0})
    return serialize_doc(updated)


@router.delete('/per-diem-rates/{rate_id}')
async def delete_per_diem_rate(rate_id: str, user: dict = Depends(require_auth)):
    """Hapus per diem rate (soft delete — set is_active=False)."""
    _admin_only(user)
    db = get_db()
    existing = await db.employee_per_diem_rates.find_one({'id': rate_id})
    if not existing:
        raise HTTPException(404, 'Rate tidak ditemukan')
    await db.employee_per_diem_rates.update_one({'id': rate_id}, {'$set': {'is_active': False, 'updated_at': _now()}})
    return {'ok': True, 'deleted': rate_id}
