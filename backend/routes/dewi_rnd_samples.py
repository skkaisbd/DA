"""dewi_rnd — Sample Requests + Revisions."""
from fastapi import Depends, HTTPException, Query
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import router, now_utc, sid, serialize
from routes.shared import assert_can_act

# Yang boleh memutus dokumen RnD (di luar admin/owner yang selalu boleh).
RND_APPROVER_ROLES = ('rnd_staff', 'manager_produksi', 'supervisor_produksi',
                      'manager', 'owner', 'admin', 'superadmin')

# ──────────────────────────────────────────────────────────────────────────────
# SAMPLE REQUESTS
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/sample-requests')
async def list_sample_requests(
    style_id: str = None,
    status: str = None,
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    """List sample requests"""
    db = get_db()
    q = {}
    if style_id:
        q['style_id'] = style_id
    if status:
        q['status'] = status

    items = await db.dewi_rnd_sample_requests.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(it) for it in items]


@router.post('/sample-requests')
async def create_sample_request(body: dict, user: dict = Depends(require_auth)):
    """Create new sample request"""
    db = get_db()
    style_id = body.get('style_id')
    if not style_id:
        raise HTTPException(400, 'style_id wajib diisi')

    from datetime import datetime as _dt
    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    doc = {
        'id': sid(),
        'sample_code': f"SR-{_dt.now().strftime('%Y%m%d')}-{sid()[:6].upper()}",
        'style_id': style_id,
        'style_code': style.get('style_code', ''),
        'style_name': style.get('style_name', ''),
        'quantity': body.get('quantity', 1),
        'priority': body.get('priority', 'normal'),
        'sample_pic': (body.get('sample_pic') or '').strip(),   # PIC / pembuat sample (2026-08-07)
        'due_date': body.get('due_date'),
        'notes': body.get('notes', ''),
        'status': 'draft',
        'approval_status': None,
        'approved_by': None,
        'approved_by_name': None,
        'approved_at': None,
        'approval_notes': None,
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_sample_requests.insert_one(doc)
    return serialize(doc)


@router.get('/sample-requests/{request_id}')
async def get_sample_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    req = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    if not req:
        raise HTTPException(404, 'Sample request tidak ditemukan')
    return serialize(req)


@router.put('/sample-requests/{request_id}')
async def update_sample_request(request_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    body.pop('_id', None)
    body.pop('id', None)
    body.pop('created_at', None)
    body['updated_at'] = now_utc()

    res = await db.dewi_rnd_sample_requests.update_one({'id': request_id}, {'$set': body})
    if res.matched_count == 0:
        raise HTTPException(404, 'Sample request tidak ditemukan')

    updated = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    return serialize(updated)


@router.post('/sample-requests/{request_id}/submit')
async def submit_sample_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    req = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    if not req:
        raise HTTPException(404, 'Sample request tidak ditemukan')
    if req.get('status') != 'draft':
        raise HTTPException(400, 'Hanya draft yang bisa di-submit')

    await db.dewi_rnd_sample_requests.update_one(
        {'id': request_id},
        {'$set': {'status': 'submitted', 'updated_at': now_utc()}},
    )
    updated = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    return serialize(updated)


@router.post('/sample-requests/{request_id}/approve')
async def approve_sample_request(request_id: str, body: dict, user: dict = Depends(require_auth)):
    assert_can_act(user, 'rnd.approve', portal='rnd', legacy_roles=RND_APPROVER_ROLES,
                   what='menyetujui permintaan sample RnD')
    db = get_db()
    req = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    if not req:
        raise HTTPException(404, 'Sample request tidak ditemukan')
    if req.get('status') != 'submitted':
        raise HTTPException(400, 'Hanya submitted yang bisa di-approve')

    await db.dewi_rnd_sample_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'approved',
            'approval_status': 'approved',
            'approved_by': user['id'],
            'approved_by_name': user.get('name', ''),
            'approved_at': now_utc(),
            'approval_notes': body.get('notes', ''),
            'updated_at': now_utc(),
        }},
    )
    updated = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    return serialize(updated)


@router.post('/sample-requests/{request_id}/reject')
async def reject_sample_request(request_id: str, body: dict, user: dict = Depends(require_auth)):
    assert_can_act(user, 'rnd.approve', portal='rnd', legacy_roles=RND_APPROVER_ROLES,
                   what='menolak permintaan sample RnD')
    db = get_db()
    req = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    if not req:
        raise HTTPException(404, 'Sample request tidak ditemukan')
    if req.get('status') != 'submitted':
        raise HTTPException(400, 'Hanya submitted yang bisa di-reject')

    await db.dewi_rnd_sample_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'rejected',
            'approval_status': 'rejected',
            'approved_by': user['id'],
            'approved_by_name': user.get('name', ''),
            'approved_at': now_utc(),
            'approval_notes': body.get('notes', ''),
            'updated_at': now_utc(),
        }},
    )
    updated = await db.dewi_rnd_sample_requests.find_one({'id': request_id})
    return serialize(updated)


@router.delete('/sample-requests/{request_id}')
async def delete_sample_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_sample_requests.delete_one({'id': request_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Sample request tidak ditemukan')
    return {'success': True}


# ──────────────────────────────────────────────────────────────────────────────
# REVISIONS (Design Revision Tracking)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/revisions')
async def list_revisions(
    style_id: str = None,
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if style_id:
        q['style_id'] = style_id

    items = await db.dewi_rnd_revisions.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(it) for it in items]


@router.post('/revisions')
async def create_revision(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    style_id = body.get('style_id')
    if not style_id:
        raise HTTPException(400, 'style_id wajib diisi')

    style = await db.dewi_rnd_styles.find_one({'id': style_id})
    if not style:
        raise HTTPException(404, 'Style tidak ditemukan')

    prev_revisions = await db.dewi_rnd_revisions.find({'style_id': style_id}).sort('revision_number', -1).to_list(length=1)
    revision_number = 1 if not prev_revisions else prev_revisions[0].get('revision_number', 0) + 1

    doc = {
        'id': sid(),
        'style_id': style_id,
        'style_code': style.get('style_code', ''),
        'revision_number': revision_number,
        'revision_name': body.get('revision_name', f'Rev {revision_number}'),
        'changes_summary': body.get('changes_summary', ''),
        'reason': body.get('reason', ''),
        'previous_revision_id': body.get('previous_revision_id'),
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
    }
    await db.dewi_rnd_revisions.insert_one(doc)
    return serialize(doc)


@router.get('/revisions/{revision_id}')
async def get_revision(revision_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    rev = await db.dewi_rnd_revisions.find_one({'id': revision_id})
    if not rev:
        raise HTTPException(404, 'Revision tidak ditemukan')
    return serialize(rev)


@router.put('/revisions/{revision_id}')
async def update_revision(revision_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by')}
    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_revisions.update_one({'id': revision_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'Revision tidak ditemukan')
    return {'ok': True}


@router.delete('/revisions/{revision_id}')
async def delete_revision(revision_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_revisions.delete_one({'id': revision_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Revision tidak ditemukan')
    return {'success': True}
