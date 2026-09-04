"""Session 27 — GAP-R1 KREATOR Request Management
Marketing (KOL Specialist / SPV) submit request produk untuk KREATOR (influencer).
RnD approve → produk masuk pipeline sample/style master.

Kategori KREATOR sesuai SOP perusahaan:
  - live_streaming: butuh 1 pcs per warna best-seller
  - tiktok_video:   butuh 1 pcs random color

Status workflow:
  draft → submitted → approved_by_rnd → sample_ready → delivered
                  └─→ rejected
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
from typing import Optional
import uuid
import re

router = APIRouter(prefix="/api/dewi/kreator-requests", tags=["Marketing-Kreator-Requests"])


def now_utc():
    return datetime.now(timezone.utc)


def sid():
    return str(uuid.uuid4())


def serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


VALID_TYPES = {'live_streaming', 'tiktok_video'}
VALID_STATUSES = {'draft', 'submitted', 'approved_by_rnd', 'sample_ready', 'delivered', 'rejected', 'cancelled'}


# ─── LIST ────────────────────────────────────────────────────────────────────
@router.get('')
async def list_requests(
    status:        Optional[str] = None,
    kreator_type:  Optional[str] = None,
    kreator_name:  Optional[str] = None,
    search:        Optional[str] = None,
    limit:         int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: dict = {}
    if status:
        q['status'] = status
    if kreator_type:
        q['kreator_type'] = kreator_type
    if kreator_name:
        q['kreator_name'] = {'$regex': re.escape(kreator_name), '$options': 'i'}
    if search:
        rx = re.escape(search)
        q['$or'] = [
            {'request_code':   {'$regex': rx, '$options': 'i'}},
            {'kreator_name':   {'$regex': rx, '$options': 'i'}},
            {'product_concept':{'$regex': rx, '$options': 'i'}},
            {'style_code':     {'$regex': rx, '$options': 'i'}},
        ]
    items = await db.dewi_kreator_requests.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(it) for it in items]


# ─── DETAIL ──────────────────────────────────────────────────────────────────
@router.get('/{request_id}')
async def get_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    return serialize(doc)


# ─── CREATE ──────────────────────────────────────────────────────────────────
@router.post('')
async def create_request(body: dict, user: dict = Depends(require_auth)):
    db = get_db()

    kreator_name = (body.get('kreator_name') or '').strip()
    kreator_type = (body.get('kreator_type') or '').strip()
    if not kreator_name:
        raise HTTPException(400, 'Nama kreator wajib diisi')
    if kreator_type not in VALID_TYPES:
        raise HTTPException(400, f"kreator_type harus salah satu dari: {', '.join(VALID_TYPES)}")
    if not (body.get('product_concept') or '').strip():
        raise HTTPException(400, 'Konsep produk wajib diisi')

    today = now_utc().strftime('%y%m%d')
    # SESI #27 — SATU PINTU kebijakan penomoran (dulu: `body.get('request_code') or …`
    # menerima nomor ketikan tanpa pemeriksaan pola/kembar).
    from core.doc_number_policy import issue_number
    code = await issue_number(db, "dewi_kreator_requests.request_code",
                              requested=(body.get('request_code') or '').strip())

    # Default qty rule sesuai SOP
    default_qty = 1
    sample_qty = int(body.get('sample_qty') or default_qty)

    doc = {
        'id': sid(),
        'request_code': code,
        'kreator_name': kreator_name,
        'kreator_handle': body.get('kreator_handle', ''),
        'kreator_type': kreator_type,
        'kreator_id': body.get('kreator_id', ''),                 # link to dewi_kol if applicable
        'product_concept': (body.get('product_concept') or '').strip(),
        'reference_links': body.get('reference_links', []),       # array of URLs (marketplace/social)
        'target_segment':  body.get('target_segment', ''),
        'sample_qty': sample_qty,
        'sample_colors': body.get('sample_colors', []),
        'sample_sizes':  body.get('sample_sizes', []),
        'deadline':      body.get('deadline', ''),
        'notes':         body.get('notes', ''),
        # Link to RnD after approval
        'style_id':      body.get('style_id', ''),
        'style_code':    body.get('style_code', ''),
        'style_name':    body.get('style_name', ''),
        'sample_request_id': body.get('sample_request_id', ''),
        # Workflow
        'status': body.get('status', 'draft'),
        'requester_id':   user['id'],
        'requester_name': user.get('name', ''),
        'approved_by':    None,
        'approved_at':    None,
        'rejected_by':    None,
        'rejected_at':    None,
        'rejection_reason': None,
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_kreator_requests.insert_one(doc)
    return serialize(doc)


# ─── UPDATE ──────────────────────────────────────────────────────────────────
@router.put('/{request_id}')
async def update_request(request_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'requester_id', 'request_code')}
    upd['updated_at'] = now_utc()
    if 'kreator_type' in upd and upd['kreator_type'] not in VALID_TYPES:
        raise HTTPException(400, 'kreator_type tidak valid')
    await db.dewi_kreator_requests.update_one({'id': request_id}, {'$set': upd})
    return {'ok': True}


# ─── SUBMIT (draft → submitted) ──────────────────────────────────────────────
@router.post('/{request_id}/submit')
async def submit_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'draft':
        raise HTTPException(400, 'Hanya request berstatus draft yang bisa disubmit')
    await db.dewi_kreator_requests.update_one(
        {'id': request_id},
        {'$set': {'status': 'submitted', 'submitted_at': now_utc(), 'updated_at': now_utc()}}
    )
    return {'ok': True}


# ─── APPROVE BY RND ──────────────────────────────────────────────────────────
@router.post('/{request_id}/approve-by-rnd')
async def approve_by_rnd(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    from routes.shared import assert_can_act
    assert_can_act(user, 'rnd.approve', 'rnd.manage', portal='rnd',
                   legacy_roles=('rnd_staff', 'manager_produksi', 'supervisor_produksi',
                                 'manager', 'owner', 'admin', 'superadmin'),
                   what='menyetujui permintaan kreator (RnD)')
    db = get_db()
    body = body or {}
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'submitted':
        raise HTTPException(400, 'Hanya request berstatus submitted yang bisa di-approve')

    # Optional: link ke style master
    style_id   = body.get('style_id', doc.get('style_id', ''))
    style_code = body.get('style_code', doc.get('style_code', ''))
    style_name = body.get('style_name', doc.get('style_name', ''))

    await db.dewi_kreator_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'approved_by_rnd',
            'approved_by': user.get('name', ''),
            'approved_at': now_utc(),
            'approval_notes': body.get('notes', ''),
            'style_id': style_id,
            'style_code': style_code,
            'style_name': style_name,
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── REJECT ──────────────────────────────────────────────────────────────────
@router.post('/{request_id}/reject')
async def reject_request(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    from routes.shared import assert_can_act
    assert_can_act(user, 'rnd.approve', 'rnd.manage', 'toko.approve', portal='rnd',
                   legacy_roles=('rnd_staff', 'manager_produksi', 'supervisor_produksi',
                                 'manager_marketing', 'manager', 'owner', 'admin', 'superadmin'),
                   what='menolak permintaan kreator')
    db = get_db()
    body = body or {}
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] in ('delivered', 'cancelled'):
        raise HTTPException(400, f"Tidak bisa reject status {doc['status']}")
    await db.dewi_kreator_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'rejected',
            'rejected_by': user.get('name', ''),
            'rejected_at': now_utc(),
            'rejection_reason': body.get('reason', ''),
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── MARK SAMPLE READY ───────────────────────────────────────────────────────
@router.post('/{request_id}/mark-sample-ready')
async def mark_sample_ready(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    db = get_db()
    body = body or {}
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'approved_by_rnd':
        raise HTTPException(400, 'Sample hanya bisa diset ready jika status approved_by_rnd')
    await db.dewi_kreator_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'sample_ready',
            'sample_ready_at': now_utc(),
            'sample_notes': body.get('notes', ''),
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── MARK DELIVERED (sample dikirim ke KREATOR) ──────────────────────────────
@router.post('/{request_id}/mark-delivered')
async def mark_delivered(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    db = get_db()
    body = body or {}
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'sample_ready':
        raise HTTPException(400, 'Hanya request sample_ready yang bisa di-deliver')
    await db.dewi_kreator_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'delivered',
            'delivered_by': user.get('name', ''),
            'delivered_at': now_utc(),
            'delivery_method': body.get('delivery_method', ''),
            'tracking_number': body.get('tracking_number', ''),
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── DELETE ──────────────────────────────────────────────────────────────────
@router.delete('/{request_id}')
async def delete_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_kreator_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] not in ('draft', 'rejected', 'cancelled'):
        raise HTTPException(400, 'Hanya draft/rejected/cancelled yang bisa dihapus')
    await db.dewi_kreator_requests.delete_one({'id': request_id})
    return {'ok': True}


# ─── STATS ───────────────────────────────────────────────────────────────────
@router.get('/stats/summary')
async def stats_summary(user: dict = Depends(require_auth)):
    db = get_db()
    by_status = {}
    async for row in db.dewi_kreator_requests.aggregate([{'$group': {'_id': '$status', 'count': {'$sum': 1}}}]):
        by_status[row['_id']] = row['count']
    by_type = {}
    async for row in db.dewi_kreator_requests.aggregate([{'$group': {'_id': '$kreator_type', 'count': {'$sum': 1}}}]):
        by_type[row['_id']] = row['count']
    total = sum(by_status.values())
    return {
        'total': total,
        'by_status': by_status,
        'by_type': by_type,
        'live_streaming': by_type.get('live_streaming', 0),
        'tiktok_video': by_type.get('tiktok_video', 0),
        'pending_rnd_approval': by_status.get('submitted', 0),
        'ready_to_deliver': by_status.get('sample_ready', 0),
    }
