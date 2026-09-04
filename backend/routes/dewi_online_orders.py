"""
CV. Dewi Aditya — Pack Batches (Toko Online)
=============================================

LEGACY-PRESERVED endpoints. After P1.D Phase C (2026-05-23):
- Orders endpoints (CRUD + status) REMOVED → migrated to /api/marketing/orders
- Pack-batches PRESERVED here because dewi_toko_pack_batches collection has
  no marketing equivalent (intentionally retained during P1.D drop).

Mounted at: /api/dewi/toko/pack-batches/*
Collections:
  - dewi_toko_pack_batches (preserved)
  - marketing_orders (filtered _legacy_toko=True) — used to mark orders as packed

Approximately 7 endpoints + ~280 LOC of OrdersView wrapper helpers were removed.
"""
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from utils.helpers import _uid, _now, _clean_list, _next_code
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/dewi/toko', tags=['Dewi-Toko-PackBatches'])

SCHEDULE_TIMES = ['08:00', '13:00', '15:00']


# ── Pydantic Models ──────────────────────────────────────────────────────────

class PackBatchIn(BaseModel):
    batch_name: Optional[str] = None
    schedule_time: str = '13:00'
    order_ids: List[str] = Field(default_factory=list)


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get('/pack-batches')
async def list_pack_batches(
    status: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    user=Depends(require_auth),
):
    """List packing batches. Preserved at /api/dewi/toko/pack-batches."""
    db = get_db()
    filt: dict = {}
    if status:
        filt['status'] = status
    items = await db.dewi_toko_pack_batches.find(filt).sort('created_at', -1).to_list(length=limit)
    return _clean_list(items)


@router.post('/pack-batches', status_code=201)
async def create_pack_batch(payload: PackBatchIn, user=Depends(require_auth)):
    """Create a packing batch and mark referenced orders as `packed` in marketing_orders."""
    db = get_db()
    if payload.schedule_time not in SCHEDULE_TIMES:
        raise HTTPException(
            status_code=422,
            detail=f'Waktu jadwal tidak valid. Pilih: {SCHEDULE_TIMES}',
        )

    # Validate orders exist and are packable — read directly from marketing_orders
    valid_order_ids: List[str] = []
    if payload.order_ids:
        cursor = db.marketing_orders.find(
            {'id': {'$in': payload.order_ids}, 'status': 'new'},
            {'_id': 0, 'id': 1, 'status': 1},
        )
        async for d in cursor:
            valid_order_ids.append(d['id'])

    code = await _next_code(db, 'PACK', 'dewi_toko_pack_batches', 'batch_code')
    name = payload.batch_name or f'Batch Packing {payload.schedule_time}'
    batch_doc = {
        'id': _uid(),
        'batch_code': code,
        'batch_name': name,
        'schedule_time': payload.schedule_time,
        'order_ids': valid_order_ids,
        'total_orders': len(valid_order_ids),
        'status': 'open',
        'created_by': user.get('id'),
        'created_at': _now(),
        'closed_at': None,
    }
    await db.dewi_toko_pack_batches.insert_one(batch_doc)

    # Tandai order sebagai 'packed' — F10: WAJIB lewat SSOT `core/order_status`
    # supaya stempel `packed_date`, jejak audit `status_history[]`, dan guard
    # transisi sama dengan jalur lain. Dulu jalur ini memakai `update_many`
    # sendiri, jadi order yang sudah DIBATALKAN pun bisa ikut ditandai "packed"
    # (order mati kembali masuk antrean gudang tanpa reservasi stok).
    packed_ok, packed_skipped = [], []
    if valid_order_ids:
        from core import order_status as _ostat
        for _oid in valid_order_ids:
            try:
                await _ostat.apply_status(
                    db, _oid, 'packed', user=user, source='pack_batch',
                    extra={'pack_batch_id': batch_doc['id']})
                packed_ok.append(_oid)
            except _ostat.InvalidOrderTransition as e:
                packed_skipped.append({'order_id': _oid, 'reason': e.reason})
            except KeyError:
                packed_skipped.append({'order_id': _oid, 'reason': 'Order tidak ditemukan.'})
    return {
        'message': f'Batch packing dibuat dengan {len(valid_order_ids)} order',
        'id': batch_doc['id'],
        'batch_code': code,
        'packed_count': len(packed_ok),
        'skipped_count': len(packed_skipped),
        'skipped': packed_skipped,
    }


@router.post('/pack-batches/{batch_id}/close')
async def close_pack_batch(batch_id: str, user=Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_toko_pack_batches.find_one({'id': batch_id})
    if not doc:
        raise HTTPException(status_code=404, detail='Batch tidak ditemukan')
    if doc['status'] == 'closed':
        raise HTTPException(status_code=400, detail='Batch sudah ditutup')
    await db.dewi_toko_pack_batches.update_one(
        {'id': batch_id},
        {'$set': {'status': 'closed', 'closed_at': _now()}},
    )
    return {'message': 'Batch ditutup'}
