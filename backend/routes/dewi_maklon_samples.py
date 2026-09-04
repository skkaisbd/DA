"""
CV. Dewi Aditya — Portal Maklon API Routes
Phase 3B: Sample Management (production samples, revisions, client approval)

Collections:
- dewi_maklon_samples: Sample product records per maklon order
- dewi_maklon_sample_revisions: Revision history per sample (audit trail)
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from auth import require_auth
from routes._maklon_adapter import find_maklon_record, po_to_legacy_order
import uuid

router = APIRouter(prefix='/api/dewi/maklon/samples', tags=['Dewi-Maklon-Samples'], dependencies=[Depends(deny_external_dep)])
# ══════════════════════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════════════════════

SAMPLE_STATUSES = ['draft', 'in_progress', 'submitted', 'approved', 'rejected', 'revision_requested']

class SampleIn(BaseModel):
    order_id: str = Field(..., description="Referensi ke dewi_maklon_orders.id")
    sample_code: Optional[str] = None
    product_name: str
    description: Optional[str] = None
    target_size: Optional[str] = Field(default='M', description="Size sampel produksi")
    fabric_used: Optional[str] = None
    color_used: Optional[str] = None
    sample_qty: int = Field(default=1, ge=1)
    photos: List[str] = Field(default_factory=list, description="URL atau file reference")
    notes: Optional[str] = None
    # Phase M2.1: optional link ke Buyer Catalog (master artikel buyer).
    # Jika dipilih, otomatis prefill product_name/description dari catalog.
    buyer_catalog_id: Optional[str] = Field(None, description="ID Buyer Catalog (opsional)")

class RevisionIn(BaseModel):
    reason: str = Field(..., description="Alasan revisi / feedback dari klien")
    changes_required: Optional[str] = None
    photos: List[str] = Field(default_factory=list)

class ApprovalIn(BaseModel):
    approved_by_name: Optional[str] = None
    feedback: Optional[str] = None

class RejectionIn(BaseModel):
    rejected_by_name: Optional[str] = None
    reason: str
    changes_required: Optional[str] = None

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _generate_sample_code(db, order_code: str, requested: str = "") -> str:
    """Kode sampel maklon — SATU PINTU kebijakan penomoran (SESI #27).

    `{ORDER}` = kode order/PO klien, supaya satu seri per order tetap terjaga
    seperti sebelumnya (`SMP-<ORDER>-01`, `-02`, …) dan formatnya kini bisa
    diatur owner di layar Penomoran Dokumen.
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, "dewi_maklon_samples.sample_code",
                              ctx={"ORDER": order_code}, requested=requested)

def _clean(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop('_id', None)
    return doc

# ══════════════════════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get('')
async def list_samples(
    order_id: Optional[str] = None,
    status: Optional[str] = None,
    buyer_catalog_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """List all samples, optionally filtered by order_id, status, or buyer_catalog_id."""
    db = get_db()
    query = {}
    if order_id:
        query['order_id'] = order_id
    if status:
        query['status'] = status
    if buyer_catalog_id:
        query['buyer_catalog_id'] = buyer_catalog_id
    samples = await db.dewi_maklon_samples.find(query).sort('created_at', -1).to_list(length=500)
    return [_clean(s) for s in samples]

@router.get('/{sample_id}')
async def get_sample(sample_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    sample = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')
    # Include revision history
    revisions = await db.dewi_maklon_sample_revisions.find(
        {'sample_id': sample_id}
    ).sort('created_at', -1).to_list(length=100)
    sample = _clean(sample)
    sample['revisions'] = [_clean(r) for r in revisions]
    return sample

@router.post('')
async def create_sample(payload: SampleIn, user: dict = Depends(require_auth)):
    """Create a new sample for a maklon order/PO."""
    db = get_db()

    # P1.B: lookup in BOTH dewi_maklon_pos (SSOT) and dewi_maklon_orders (legacy)
    rec = await find_maklon_record(db, payload.order_id)
    if not rec:
        raise HTTPException(400, 'Order maklon tidak ditemukan')
    is_po = rec.get('_collection') == 'dewi_maklon_pos'
    order = po_to_legacy_order(rec) if is_po else rec

    # Phase M2.1: Auto-fill dari Buyer Catalog jika ada
    catalog_snapshot = None
    if payload.buyer_catalog_id:
        cat = await db.dewi_maklon_buyer_catalog.find_one(
            {'id': payload.buyer_catalog_id}, {'_id': 0}
        )
        if cat:
            # Validate catalog client matches order client (consistency)
            if order.get('client_id') and cat.get('client_id') and order['client_id'] != cat['client_id']:
                raise HTTPException(
                    400,
                    'Buyer Catalog tidak cocok dengan klien order ini. '
                    'Pilih artikel dari klien yang sama.',
                )
            # Override jika field kosong
            if not payload.product_name or payload.product_name.strip() == '':
                payload.product_name = cat.get('product_name') or cat.get('artikel_code') or 'Sample'
            if not payload.description:
                payload.description = cat.get('description') or ''
            if not payload.color_used and cat.get('color_options'):
                payload.color_used = cat['color_options'][0]
            catalog_snapshot = {
                'artikel_code': cat.get('artikel_code', ''),
                'buyer_ref_code': cat.get('buyer_ref_code', ''),
                'product_name': cat.get('product_name', ''),
            }

    now = datetime.now(timezone.utc)
    # SESI #27 — nomor lewat SATU PINTU kebijakan. Dulu `payload.sample_code or …`
    # menerima kode ketikan apa pun bentuknya (hanya dicek kembar), jadi mode
    # OTOMATIS milik owner bisa dilangkahi hanya dengan mengisi kolom.
    sample_code = await _generate_sample_code(
        db, order.get('order_code', 'UNK'), (payload.sample_code or '').strip())

    # Check duplicate code
    if await db.dewi_maklon_samples.find_one({'sample_code': sample_code}):
        raise HTTPException(400, f'Sample code {sample_code} sudah digunakan')

    doc = payload.dict()
    doc['id'] = str(uuid.uuid4())
    doc['sample_code'] = sample_code
    doc['order_code'] = order.get('order_code')
    # P1.B: store BOTH order_id and po_id (for unified lookups)
    if is_po:
        doc['po_id'] = order.get('id')  # SSOT PO reference
    doc['client_id'] = order.get('client_id')
    doc['client_name'] = order.get('client_name')
    doc['status'] = 'draft'
    doc['revision_number'] = 0
    doc['approved_by_name'] = None
    doc['approved_at'] = None
    doc['rejected_by_name'] = None
    doc['rejected_at'] = None
    doc['submitted_at'] = None
    doc['created_at'] = now
    doc['updated_at'] = now
    doc['created_by'] = user.get('name', 'System')
    # Phase M2.1: simpan snapshot catalog untuk audit
    if catalog_snapshot:
        doc['buyer_catalog_snapshot'] = catalog_snapshot

    await db.dewi_maklon_samples.insert_one(doc)
    return {'message': 'Sample berhasil dibuat', 'id': doc['id'], 'sample_code': sample_code}

@router.put('/{sample_id}')
async def update_sample(sample_id: str, payload: SampleIn, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not existing:
        raise HTTPException(404, 'Sample tidak ditemukan')
    if existing.get('status') == 'approved':
        raise HTTPException(400, 'Sample sudah disetujui, tidak dapat diubah')

    update_data = payload.dict(exclude_unset=True)
    # Don't allow changing order_id or sample_code here
    update_data.pop('order_id', None)
    update_data.pop('sample_code', None)
    update_data['updated_at'] = datetime.now(timezone.utc)

    await db.dewi_maklon_samples.update_one({'id': sample_id}, {'$set': update_data})
    return {'message': 'Sample diperbarui'}

@router.delete('/{sample_id}')
async def delete_sample(sample_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not existing:
        raise HTTPException(404, 'Sample tidak ditemukan')
    if existing.get('status') == 'approved':
        raise HTTPException(400, 'Sample yang sudah disetujui tidak dapat dihapus')
    await db.dewi_maklon_samples.delete_one({'id': sample_id})
    await db.dewi_maklon_sample_revisions.delete_many({'sample_id': sample_id})
    return {'message': 'Sample dihapus'}

# ══════════════════════════════════════════════════════════════════════════════
# WORKFLOW
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/{sample_id}/submit')
async def submit_sample(sample_id: str, user: dict = Depends(require_auth)):
    """Submit sample for client approval (status → submitted)."""
    db = get_db()
    sample = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')
    if sample.get('status') not in ['draft', 'in_progress', 'revision_requested']:
        raise HTTPException(400, f'Sample dengan status {sample.get("status")} tidak bisa disubmit')

    now = datetime.now(timezone.utc)
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'submitted',
            'submitted_at': now,
            'updated_at': now,
        }}
    )
    # Phase 4 P1: notify klien
    try:
        from routes.dewi_notifications import queue_for_client
        body = (
            f"Sample {sample.get('sample_code')} untuk produk "
            f"\"{sample.get('product_name')}\" sudah siap untuk Anda review. "
            f"Silakan login ke Portal Klien untuk approve / minta revisi."
        )
        await queue_for_client(
            db,
            client_id=sample.get('client_id'),
            subject=f"Sample siap approval — {sample.get('sample_code')}",
            body=body,
            event_type='sample_submitted',
            source_ref=sample_id,
            meta={'sample_code': sample.get('sample_code'), 'product_name': sample.get('product_name')},
        )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    return {'message': 'Sample disubmit untuk approval klien'}

@router.post('/{sample_id}/approve')
async def approve_sample(sample_id: str, payload: ApprovalIn, user: dict = Depends(require_auth)):
    """Client approves the sample (final decision)."""
    from routes.shared import assert_can_act
    assert_can_act(user, 'maklon.approve', 'maklon.manage', portal='maklon',
                   legacy_roles=('admin_maklon', 'manager', 'manager_produksi',
                                 'owner', 'admin', 'superadmin'),
                   what='menyetujui sample maklon')
    db = get_db()
    sample = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')
    if sample.get('status') not in ['submitted', 'revision_requested']:
        raise HTTPException(400, 'Hanya sample submitted yang bisa disetujui')

    now = datetime.now(timezone.utc)
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'approved',
            'approved_by_name': payload.approved_by_name or user.get('name'),
            'approved_at': now,
            'approval_feedback': payload.feedback,
            'updated_at': now,
        }}
    )
    return {'message': 'Sample disetujui'}

@router.post('/{sample_id}/reject')
async def reject_sample(sample_id: str, payload: RejectionIn, user: dict = Depends(require_auth)):
    """Client rejects sample with required changes."""
    from routes.shared import assert_can_act
    assert_can_act(user, 'maklon.approve', 'maklon.manage', portal='maklon',
                   legacy_roles=('admin_maklon', 'manager', 'manager_produksi',
                                 'owner', 'admin', 'superadmin'),
                   what='menolak sample maklon')
    db = get_db()
    sample = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')
    if sample.get('status') not in ['submitted', 'revision_requested']:
        raise HTTPException(400, 'Hanya sample submitted yang bisa ditolak')

    now = datetime.now(timezone.utc)
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'rejected',
            'rejected_by_name': payload.rejected_by_name or user.get('name'),
            'rejected_at': now,
            'rejection_reason': payload.reason,
            'updated_at': now,
        }}
    )
    return {'message': 'Sample ditolak'}

@router.post('/{sample_id}/revision')
async def request_revision(sample_id: str, payload: RevisionIn, user: dict = Depends(require_auth)):
    """Request a revision of the sample (new iteration)."""
    db = get_db()
    sample = await db.dewi_maklon_samples.find_one({'id': sample_id})
    if not sample:
        raise HTTPException(404, 'Sample tidak ditemukan')

    now = datetime.now(timezone.utc)
    new_rev = int(sample.get('revision_number', 0)) + 1

    # Insert revision history record
    rev_doc = {
        'id': str(uuid.uuid4()),
        'sample_id': sample_id,
        'revision_number': new_rev,
        'reason': payload.reason,
        'changes_required': payload.changes_required,
        'photos': payload.photos,
        'requested_by': user.get('name', 'System'),
        'created_at': now,
    }
    await db.dewi_maklon_sample_revisions.insert_one(rev_doc)

    # Update sample status
    await db.dewi_maklon_samples.update_one(
        {'id': sample_id},
        {'$set': {
            'status': 'revision_requested',
            'revision_number': new_rev,
            'updated_at': now,
        }}
    )
    return {'message': f'Revisi #{new_rev} dicatat', 'revision_number': new_rev}

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/summary/overview')
async def samples_summary(user: dict = Depends(require_auth)):
    """Dashboard summary for samples."""
    db = get_db()
    total = await db.dewi_maklon_samples.count_documents({})
    by_status = {}
    for st in SAMPLE_STATUSES:
        by_status[st] = await db.dewi_maklon_samples.count_documents({'status': st})
    pending_approval = by_status.get('submitted', 0) + by_status.get('revision_requested', 0)

    return {
        'total_samples': total,
        'by_status': by_status,
        'pending_approval': pending_approval,
        'approved': by_status.get('approved', 0),
        'rejected': by_status.get('rejected', 0),
    }

@router.get('/by-order/{order_id}')
async def samples_by_order(order_id: str, user: dict = Depends(require_auth)):
    """All samples for a given order."""
    db = get_db()
    samples = await db.dewi_maklon_samples.find({'order_id': order_id}).sort('created_at', -1).to_list(length=200)
    return [_clean(s) for s in samples]
