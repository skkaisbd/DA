"""
CV. Dewi Aditya — Flashsales (Toko Online)
===========================================

LEGACY-PRESERVED endpoints. After P1.D Phase C (2026-05-23):
- Product Catalog, Channel Manager, Dashboard endpoints REMOVED → migrated to
  /api/marketing/catalogs, /api/marketing/accounts, /api/marketing/dashboard/toko-overview
- Flashsales endpoints PRESERVED here because dewi_toko_flashsales collection
  has no marketing equivalent (intentionally retained during P1.D drop).

Mounted at: /api/dewi/toko/flashsales/*
Collection: dewi_toko_flashsales (preserved)

IMPORTANT (Phase C, 2026-05-23):
  Approximately 18 endpoints + ~600 LOC of helper classes (_ScopedView,
  _LazyProductsView, _legacy_channels, _legacy_syncs, seed_toko_channels)
  were removed. The `_toko_adapter.py` helpers are no longer used by this
  file (still used by dewi_online_orders.py for pack-batches mark-as-packed).
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from utils.helpers import _uid, _now, _clean, _clean_list
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/dewi/toko', tags=['Dewi-Toko-Flashsales'])

SUPPORTED_CHANNELS = ['shopee', 'tokopedia', 'tiktok_shop', 'website']


# ── Pydantic Models ──────────────────────────────────────────────────────────

class FlashsaleProductItem(BaseModel):
    product_id: Optional[str] = None
    sku_code: str
    name: Optional[str] = None
    original_price: float = Field(default=0.0, ge=0)
    flashsale_price: float = Field(default=0.0, ge=0)
    discount_pct: float = Field(default=0.0, ge=0, le=100)
    quota: int = Field(default=0, ge=0)


class FlashsaleIn(BaseModel):
    name: str = Field(..., min_length=2)
    channel_code: str = 'shopee'
    start_at: str  # ISO datetime string
    end_at: str    # ISO datetime string
    products: List[FlashsaleProductItem] = Field(default_factory=list)
    notes: Optional[str] = None


class FlashsalePatchIn(BaseModel):
    name: Optional[str] = None
    channel_code: Optional[str] = None
    start_at: Optional[str] = None
    end_at: Optional[str] = None
    products: Optional[List[FlashsaleProductItem]] = None
    notes: Optional[str] = None
    status: Optional[str] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get('/flashsales')
async def list_flashsales(
    status: Optional[str] = None,
    channel_code: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(require_auth),
):
    """List flashsales. Preserved at /api/dewi/toko/flashsales (no marketing equivalent)."""
    db = get_db()
    filt: dict = {}
    if status:
        filt['status'] = status
    if channel_code:
        filt['channel_code'] = channel_code
    items = await db.dewi_toko_flashsales.find(filt).sort('start_at', -1).to_list(length=limit)
    return _clean_list(items)


@router.get('/flashsales/{flashsale_id}')
async def get_flashsale(flashsale_id: str, user=Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_toko_flashsales.find_one({'id': flashsale_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Flashsale tidak ditemukan')
    return _clean(doc)


@router.post('/flashsales', status_code=201)
async def create_flashsale(payload: FlashsaleIn, user=Depends(require_auth)):
    db = get_db()
    if payload.channel_code not in SUPPORTED_CHANNELS:
        raise HTTPException(
            status_code=422,
            detail=f'Channel tidak valid. Pilih: {SUPPORTED_CHANNELS}',
        )
    doc = {
        'id': _uid(),
        'name': payload.name,
        'channel_code': payload.channel_code,
        'start_at': payload.start_at,
        'end_at': payload.end_at,
        'products': [p.model_dump() for p in payload.products],
        'notes': payload.notes,
        'status': 'draft',
        'created_by': user.get('id'),
        'created_at': _now(),
        'updated_at': _now(),
    }
    await db.dewi_toko_flashsales.insert_one(doc)
    return {'message': 'Flashsale dibuat', 'id': doc['id']}


@router.put('/flashsales/{flashsale_id}')
async def update_flashsale(flashsale_id: str, payload: FlashsalePatchIn, user=Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_toko_flashsales.find_one({'id': flashsale_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Flashsale tidak ditemukan')
    if doc['status'] == 'active':
        raise HTTPException(status_code=400, detail='Flashsale aktif tidak bisa diedit. Nonaktifkan dulu.')
    patch = payload.model_dump(exclude_none=True)
    if 'products' in patch:
        patch['products'] = [p if isinstance(p, dict) else p.model_dump() for p in patch['products']]
    if not patch:
        raise HTTPException(status_code=422, detail='Tidak ada field yang diupdate')
    patch['updated_at'] = _now()
    await db.dewi_toko_flashsales.update_one({'id': flashsale_id}, {'$set': patch})
    return {'message': 'Flashsale diperbarui'}


@router.post('/flashsales/{flashsale_id}/activate')
async def toggle_flashsale(flashsale_id: str, user=Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_toko_flashsales.find_one({'id': flashsale_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Flashsale tidak ditemukan')
    new_status = 'active' if doc['status'] != 'active' else 'draft'
    await db.dewi_toko_flashsales.update_one(
        {'id': flashsale_id},
        {'$set': {'status': new_status, 'updated_at': _now()}},
    )
    return {'message': f'Status flashsale: {new_status}', 'status': new_status}


@router.delete('/flashsales/{flashsale_id}')
async def delete_flashsale(flashsale_id: str, user=Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_toko_flashsales.find_one({'id': flashsale_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Flashsale tidak ditemukan')
    if doc['status'] == 'active':
        raise HTTPException(status_code=400, detail='Nonaktifkan flashsale sebelum menghapus')
    await db.dewi_toko_flashsales.delete_one({'id': flashsale_id})
    return {'message': 'Flashsale dihapus'}
