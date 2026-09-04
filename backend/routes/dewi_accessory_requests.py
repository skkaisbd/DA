"""Session 27 — GAP-R3 Accessory Request Workflow

★ SSOT (P3 TD-009 — Session #11.10): canonical store for ALL accessory
  request flows across CV. Dewi Aditya. Absorbs:
  - `acc_internal_requests` (deprecated, see `dewi_accessories_full.py`
    `/api/dewi/accessories/internal-requests/*`) — `request_type='internal_issuance'`
  - `accessory_requests` (deprecated, see `operations.py`
    `/api/operations/accessory-requests/*`) — `request_type='vendor_additional'|
    'vendor_replacement'`
  - Native RnD sample requests — `request_type='rnd_sample'` (legacy docs
    without `request_type` are treated as rnd_sample).

Status workflow (normalized across all request_types):
  draft → submitted → allocated → delivered (or rejected/cancelled)

Migration script: /app/backend/migrations/migrate_acc_requests_consolidation.py
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
from typing import Optional
import uuid
import re

router = APIRouter(prefix="/api/dewi/accessory-requests", tags=["RnD-Accessory-Requests"])


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


VALID_STATUSES = {'draft', 'submitted', 'allocated', 'delivered', 'rejected', 'cancelled'}

# P3 TD-009: known request_type discriminators
VALID_REQUEST_TYPES = {
    'rnd_sample',          # Native — RnD requesting accessories for sample/style production
    'internal_issuance',   # Migrated from acc_internal_requests — internal divisions requesting stock
    'vendor_additional',   # Migrated from accessory_requests — vendor ADDITIONAL shipment request
    'vendor_replacement',  # Migrated from accessory_requests — vendor REPLACEMENT shipment request
}


def _normalize_request_type(rt: Optional[str]) -> str:
    """Map legacy 'sample' or empty values to 'rnd_sample'; pass-through known types."""
    if not rt or rt in ('sample', 'rnd', 'rnd_sample'):
        return 'rnd_sample'
    return rt if rt in VALID_REQUEST_TYPES else 'rnd_sample'


# ─── LIST ────────────────────────────────────────────────────────────────────
@router.get('')
async def list_requests(
    status:            Optional[str] = None,
    request_type:      Optional[str] = Query(None, description="Filter by SSOT discriminator: rnd_sample|internal_issuance|vendor_additional|vendor_replacement"),
    sample_request_id: Optional[str] = None,
    style_id:          Optional[str] = None,
    divisi:            Optional[str] = None,
    vendor_id:         Optional[str] = None,
    urgent_only:       Optional[bool] = False,
    search:            Optional[str] = None,
    limit:             int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: dict = {}
    if status:
        q['status'] = status
    if request_type:
        q['request_type'] = request_type
    if sample_request_id:
        q['sample_request_id'] = sample_request_id
    if style_id:
        q['style_id'] = style_id
    if divisi:
        q['divisi'] = divisi
    if vendor_id:
        q['vendor_id'] = vendor_id
    if urgent_only:
        q['urgent'] = True
    if search:
        rx = re.escape(search)
        q['$or'] = [
            {'request_code':   {'$regex': rx, '$options': 'i'}},
            {'style_code':     {'$regex': rx, '$options': 'i'}},
            {'style_name':     {'$regex': rx, '$options': 'i'}},
            {'requester_name': {'$regex': rx, '$options': 'i'}},
            {'divisi':         {'$regex': rx, '$options': 'i'}},
        ]
    items = await db.dewi_accessory_requests.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(it) for it in items]


# ─── DETAIL ──────────────────────────────────────────────────────────────────
@router.get('/{request_id}')
async def get_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    return serialize(doc)


# ─── CREATE ──────────────────────────────────────────────────────────────────
@router.post('')
async def create_request(body: dict, user: dict = Depends(require_auth)):
    """Create accessory request. Supports all SSOT request_types:
       rnd_sample | internal_issuance | vendor_additional | vendor_replacement.

       Defaults to 'rnd_sample' when `request_type` is omitted (backward compat).
    """
    db = get_db()

    items = body.get('items') or []
    if not items:
        raise HTTPException(400, 'Minimal 1 item aksesoris harus diisi')

    rt = _normalize_request_type(body.get('request_type'))
    sample_id = body.get('sample_request_id') or ''
    style_id  = body.get('style_id') or ''

    style_code = body.get('style_code') or ''
    style_name = body.get('style_name') or ''

    # Auto-resolve style info if not provided (rnd_sample type only)
    if rt == 'rnd_sample' and style_id and not (style_code and style_name):
        st = await db.dewi_rnd_styles.find_one({'id': style_id})
        if st:
            style_code = style_code or st.get('style_code', '')
            style_name = style_name or st.get('style_name', '')

    # Generate code with type-specific prefix when none supplied
    today = now_utc().strftime('%y%m%d')
    prefix_map = {
        'rnd_sample':         'REQ-AKS',
        'internal_issuance':  'INT-REQ',
        'vendor_additional':  'ACC-ADD',
        'vendor_replacement': 'ACC-RPL',
    }
    prefix = prefix_map.get(rt, 'REQ-AKS')
    # SESI #27 — SATU PINTU kebijakan penomoran (dulu: nomor ketikan diterima apa pun
    # bentuknya, tanpa pemeriksaan pola maupun nomor kembar). `{TIPE}` menjaga empat
    # seri (sampel R&D · pengeluaran internal · tambahan vendor · pengganti vendor)
    # tetap terpisah seperti sekarang.
    from core.doc_number_policy import issue_number
    code = await issue_number(db, "dewi_accessory_requests.request_code",
                              ctx={"TIPE": prefix},
                              requested=(body.get('request_code') or '').strip())

    doc = {
        'id': sid(),
        'request_code': code,
        'request_type': rt,
        # rnd_sample fields
        'sample_request_id': sample_id,
        'style_id': style_id,
        'style_code': style_code,
        'style_name': style_name,
        # internal_issuance fields
        'divisi':       body.get('divisi', ''),
        'purpose':      body.get('purpose', ''),
        'admin_notes':  body.get('admin_notes', ''),
        # vendor_*  fields
        'vendor_id':              body.get('vendor_id', ''),
        'original_shipment_id':   body.get('original_shipment_id'),
        'po_id':                  body.get('po_id'),
        'po_number':              body.get('po_number', ''),
        'total_requested_qty':    body.get('total_requested_qty'),
        # common
        'items': [
            {
                # ACC-1/ACC-2: `material_id` dibawa agar permintaan bisa dipenuhi dari
                # stok kanonik (rahaza_material_stock) tanpa cocok-cocokan nama/kode.
                'material_id': it.get('material_id') or it.get('acc_id') or it.get('accessory_id') or '',
                'material_code': it.get('material_code', '') or it.get('acc_code', '') or it.get('accessory_code', ''),
                'material_name': it.get('material_name', '') or it.get('acc_name', '') or it.get('accessory_name', ''),
                'qty': float(it.get('qty', 0) or it.get('qty_requested', 0) or it.get('requested_qty', 0) or 0),
                'unit': it.get('unit', 'pcs'),
                'notes': it.get('notes', ''),
            } for it in items
        ],
        'urgent': bool(body.get('urgent', False)),
        'needed_by_date': body.get('needed_by_date', '') or body.get('needed_by', ''),
        'notes': body.get('notes', '') or body.get('reason', ''),
        'status': body.get('status', 'draft'),
        'requester_id': user['id'],
        'requester_name': user.get('name', ''),
        'allocated_by': None,
        'allocated_at': None,
        'delivered_by': None,
        'delivered_at': None,
        'rejection_reason': None,
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_accessory_requests.insert_one(doc)
    return serialize(doc)


# ─── UPDATE (edit details — only if still draft/submitted) ───────────────────
@router.put('/{request_id}')
async def update_request(request_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] in ('delivered', 'rejected', 'cancelled'):
        raise HTTPException(400, f"Tidak bisa edit request dengan status {doc['status']}")

    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by', 'requester_id', 'request_code')}
    if 'items' in upd:
        upd['items'] = [
            {
                'material_code': it.get('material_code', ''),
                'material_name': it.get('material_name', ''),
                'qty': float(it.get('qty', 0) or 0),
                'unit': it.get('unit', 'pcs'),
                'notes': it.get('notes', ''),
            } for it in (upd['items'] or [])
        ]
    upd['updated_at'] = now_utc()
    await db.dewi_accessory_requests.update_one({'id': request_id}, {'$set': upd})
    return {'ok': True}


# ─── SUBMIT (draft → submitted) ──────────────────────────────────────────────
@router.post('/{request_id}/submit')
async def submit_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'draft':
        raise HTTPException(400, 'Hanya request berstatus draft yang bisa disubmit')
    await db.dewi_accessory_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'submitted',
            'submitted_at': now_utc(),
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── ALLOCATE (submitted → allocated, by Admin Aksesoris) ────────────────────
@router.post('/{request_id}/allocate')
async def allocate_request(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    db = get_db()
    body = body or {}
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'submitted':
        raise HTTPException(400, 'Hanya request berstatus submitted yang bisa di-allocate')
    await db.dewi_accessory_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'allocated',
            'allocated_by': user.get('name', ''),
            'allocated_at': now_utc(),
            'allocation_notes': body.get('notes', ''),
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── DELIVER (allocated → delivered) ─────────────────────────────────────────
@router.post('/{request_id}/deliver')
async def deliver_request(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    """Serahkan barang ke pemohon.

    FASE 10 — untuk `request_type='internal_issuance'` endpoint ini SEKARANG
    MEMOTONG STOK (kartu stok bernilai + jurnal pemakaian), persis seperti jalur
    legacy `PUT /api/acc/internal-requests/{id}` status `Issued`. Tanpa ini, migrasi
    UI ke SSOT akan membuat stok tidak pernah berkurang — dan koleksi legacy
    `acc_internal_requests` tidak akan pernah bisa di-drop.

    Prinsip aman:
      * SEMUA baris divalidasi dulu (`check_availability`) — kalau satu baris kurang
        stok, tidak ada satu pun yang dipotong (tidak ada penyerahan separuh).
      * IDEMPOTEN: dokumen ditandai `stock_issued` sehingga klik ganda tidak memotong
        stok dua kali.
    """
    db = get_db()
    body = body or {}
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] != 'allocated':
        raise HTTPException(400, 'Hanya request berstatus allocated yang bisa di-deliver')

    issue_results: list[dict] = []
    if doc.get('request_type') == 'internal_issuance' and not doc.get('stock_issued'):
        from core import accessory_issue

        try:
            rows = await accessory_issue.check_availability(db, doc.get('items') or [])
        except accessory_issue.IssueError as e:
            raise HTTPException(getattr(e, 'status', 400), str(e))
        note = (f"Permintaan internal {doc.get('request_code', '')}"
                f"{' · ' + doc['divisi'] if doc.get('divisi') else ''}")
        for row in rows:
            try:
                res = await accessory_issue.issue_accessory(
                    db, user, acc_id=row['material']['id'], qty=row['qty'],
                    notes=note, ref_type='accessory_request', ref_id=request_id,
                )
            except accessory_issue.IssueError as e:
                # Sudah lolos pra-validasi; kalau tetap gagal (mis. balapan), laporkan
                # apa yang SUDAH terpotong supaya operator bisa menelusuri.
                raise HTTPException(
                    400, f"{str(e)} — {len(issue_results)} baris sudah terlanjur dikeluarkan; "
                         f"periksa kartu stok aksesoris.")
            issue_results.append({
                'material_id': res['material_id'], 'material_code': res['material_code'],
                'material_name': res['material_name'], 'qty': res['qty_issued'],
                'unit': res['unit'], 'unit_cost': res['unit_cost'], 'value': res['value'],
                'je_number': (res.get('je') or {}).get('je_number', ''),
                'je_posted': bool((res.get('je') or {}).get('posted')),
            })

    update = {
        'status': 'delivered',
        'delivered_by': user.get('name', ''),
        'delivered_at': now_utc(),
        'delivery_notes': body.get('notes', ''),
        'updated_at': now_utc(),
    }
    if issue_results:
        update['stock_issued'] = True
        update['stock_issue_results'] = issue_results
        update['stock_issued_at'] = now_utc()
    await db.dewi_accessory_requests.update_one({'id': request_id}, {'$set': update})
    return {
        'ok': True,
        'stock_issued': bool(issue_results),
        'issued_items': issue_results,
        'total_value': round(sum(x['value'] for x in issue_results), 2),
    }


# ─── REJECT ──────────────────────────────────────────────────────────────────
@router.post('/{request_id}/reject')
async def reject_request(request_id: str, body: dict = None, user: dict = Depends(require_auth)):
    from routes.shared import assert_can_act
    assert_can_act(user, 'accessories.approve', 'accessories.manage', portal='accessories',
                   legacy_roles=('admin_aksesoris', 'spv_aksesoris', 'admin_gudang',
                                 'manager', 'owner', 'admin', 'superadmin'),
                   what='menolak permintaan aksesoris')
    db = get_db()
    body = body or {}
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] in ('delivered', 'cancelled'):
        raise HTTPException(400, f"Tidak bisa reject request dengan status {doc['status']}")
    await db.dewi_accessory_requests.update_one(
        {'id': request_id},
        {'$set': {
            'status': 'rejected',
            'rejection_reason': body.get('reason', ''),
            'rejected_by': user.get('name', ''),
            'rejected_at': now_utc(),
            'updated_at': now_utc(),
        }}
    )
    return {'ok': True}


# ─── DELETE ──────────────────────────────────────────────────────────────────
@router.delete('/{request_id}')
async def delete_request(request_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_accessory_requests.find_one({'id': request_id})
    if not doc:
        raise HTTPException(404, 'Request tidak ditemukan')
    if doc['status'] not in ('draft', 'rejected', 'cancelled'):
        raise HTTPException(400, 'Hanya request berstatus draft/rejected/cancelled yang bisa dihapus')
    await db.dewi_accessory_requests.delete_one({'id': request_id})
    return {'ok': True}


# ─── STATS / DASHBOARD ───────────────────────────────────────────────────────
@router.get('/stats/summary')
async def stats_summary(user: dict = Depends(require_auth)):
    db = get_db()

    by_status_pipeline = [
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]
    by_status = {row['_id']: row['count'] async for row in db.dewi_accessory_requests.aggregate(by_status_pipeline)}

    by_type_pipeline = [
        {'$group': {'_id': '$request_type', 'count': {'$sum': 1}}}
    ]
    raw_by_type = {row['_id'] or 'rnd_sample': row['count']
                   async for row in db.dewi_accessory_requests.aggregate(by_type_pipeline)}
    # Normalize None / missing → rnd_sample bucket
    by_request_type = {
        'rnd_sample':         raw_by_type.get('rnd_sample', 0) + raw_by_type.get(None, 0),
        'internal_issuance':  raw_by_type.get('internal_issuance', 0),
        'vendor_additional':  raw_by_type.get('vendor_additional', 0),
        'vendor_replacement': raw_by_type.get('vendor_replacement', 0),
    }

    total = sum(by_status.values())
    urgent_pending = await db.dewi_accessory_requests.count_documents({
        'urgent': True,
        'status': {'$in': ['submitted', 'allocated']}
    })
    return {
        'total': total,
        'draft':     by_status.get('draft', 0),
        'submitted': by_status.get('submitted', 0),
        'allocated': by_status.get('allocated', 0),
        'delivered': by_status.get('delivered', 0),
        'rejected':  by_status.get('rejected', 0),
        'cancelled': by_status.get('cancelled', 0),
        'urgent_pending': urgent_pending,
        'by_request_type': by_request_type,
    }
