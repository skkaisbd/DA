"""
Employee Expense Claims (Reimbursement) — Routes
CV. Dewi Aditya — Employee Expense Management (EEM)

Klaim biaya karyawan (reimbursement) dengan approval 2-level dan GL posting otomatis.

Status flow: draft → submitted → approved/rejected → paid → posted

Prefix: /api/hr/expenses

Endpoints:
  POST /claims                          — create claim (draft)
  GET  /claims                          — list (my claims / all for manager)
  GET  /claims/{id}                     — detail
  PUT  /claims/{id}                     — update draft
  POST /claims/{id}/submit              — submit for approval
  POST /claims/{id}/approve             — approve (manager/hr/finance)
  POST /claims/{id}/reject              — reject with reason
  POST /claims/{id}/disburse            — finance disburse + GL post
  DELETE /claims/{id}                   — delete draft
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date, timezone
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import logging
import uuid
import csv
import io

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/hr/expenses', tags=['Employee-Expenses'])

# ── Constants ──────────────────────────────────────────────────────────────────
EXPENSE_CATEGORIES = [
    'Transportasi', 'Akomodasi', 'Konsumsi / Makan',
    'Representasi / Entertainment', 'Komunikasi', 'ATK / Perlengkapan',
    'Parkir / Tol', 'Lain-lain'
]

STATUS_LABELS = {
    'draft': 'Draft',
    'submitted': 'Menunggu Persetujuan',
    'approved': 'Disetujui',
    'rejected': 'Ditolak',
    'paid': 'Sudah Dibayar',
    'posted': 'Sudah di-Post GL',
}

APPROVER_ROLES = ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance')


# ── Helpers ────────────────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc)


def _to_iso(v):
    if v is None:
        return None
    if isinstance(v, str):
        return v
    if isinstance(v, datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v.isoformat()
    return str(v)


def _serialize_claim(doc: dict) -> dict:
    if not doc:
        return {}
    d = serialize_doc(doc)
    # Convert datetime fields
    for key in ('created_at', 'updated_at', 'submitted_at', 'approved_at', 'paid_at'):
        if key in d:
            d[key] = _to_iso(d[key])
    # Ensure items list
    if 'items' not in d:
        d['items'] = []
    return d


def _calc_total(items: list) -> float:
    return sum(float(it.get('amount', 0) or 0) for it in items)


async def _get_claim_or_404(db, claim_id: str) -> dict:
    doc = await db.rahaza_expense_claims.find_one({'id': claim_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, f'Klaim {claim_id} tidak ditemukan')
    return doc


async def _generate_claim_number(db, requested: str = '') -> str:
    """Nomor klaim biaya — SATU PINTU kebijakan penomoran (Otomatis/Manual).

    SESI #27 (batch-3 Fase G): sebelumnya jalur ini SELALU otomatis
    (`gen_prefixed_number`), sehingga mode MANUAL yang dipilih owner di layar
    "Penomoran Dokumen" tersimpan, tampil, tetapi tidak pernah berlaku —
    setelan yang tidak ditegakkan lebih buruk daripada setelan yang tidak ada.
    Sekarang: mode otomatis MENOLAK nomor ketikan, mode manual mewajibkan nomor
    yang mengikuti pola dan menolak nomor kembar (409).
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, 'rahaza_expense_claims.claim_number',
                              requested=requested)


# ── Pydantic Models ────────────────────────────────────────────────────────────
class ClaimItem(BaseModel):
    date: str
    category: str
    amount: float = Field(ge=0)
    notes: Optional[str] = ''
    receipt_url: Optional[str] = ''


class ClaimCreate(BaseModel):
    title: str
    items: List[ClaimItem] = Field(default_factory=list)
    cost_center_id: Optional[str] = ''
    gl_debit_code: Optional[str] = ''
    bank_account_id: Optional[str] = ''
    notes: Optional[str] = ''
    # SESI #27 — nomor ketikan staf (HANYA dipakai bila kebijakan = MANUAL).
    claim_number: Optional[str] = ''


class ClaimUpdate(BaseModel):
    title: Optional[str] = None
    items: Optional[List[ClaimItem]] = None
    cost_center_id: Optional[str] = None
    gl_debit_code: Optional[str] = None
    bank_account_id: Optional[str] = None
    notes: Optional[str] = None


class ApprovePayload(BaseModel):
    note: Optional[str] = ''


class RejectPayload(BaseModel):
    reason: str


class DisbursePayload(BaseModel):
    bank_account_id: Optional[str] = ''
    payment_method: Optional[str] = 'transfer'
    note: Optional[str] = ''


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post('/claims', status_code=201)
async def create_claim(body: ClaimCreate, user: dict = Depends(require_auth)):
    """Buat klaim biaya baru (status: draft)."""
    db = get_db()
    emp = await db.rahaza_employees.find_one(
        {'$or': [{'id': user.get('id')}, {'email': user.get('email')}]}, {'_id': 0}
    )
    items = [it.model_dump() for it in (body.items or [])]
    total = _calc_total(items)
    claim_number = await _generate_claim_number(db, (body.claim_number or '').strip())
    now = _now()
    doc = {
        'id': str(uuid.uuid4()),
        'claim_number': claim_number,
        'employee_id': user.get('id'),
        'employee_name': user.get('name') or (emp.get('name') if emp else ''),
        'employee_dept': emp.get('department') if emp else '',
        'employee_position': emp.get('position') if emp else '',
        'title': body.title,
        'items': items,
        'total_amount': total,
        'status': 'draft',
        'cost_center_id': body.cost_center_id or '',
        'gl_debit_code': body.gl_debit_code or '',
        'bank_account_id': body.bank_account_id or '',
        'notes': body.notes or '',
        'approval_note': '',
        'reject_reason': '',
        'submitted_at': None,
        'approved_at': None,
        'approved_by': '',
        'approved_by_name': '',
        'paid_at': None,
        'paid_by': '',
        'paid_by_name': '',
        'payment_method': '',
        'gl_je_id': '',
        'created_by': user.get('id'),
        'created_by_name': user.get('name'),
        'created_at': now,
        'updated_at': now,
    }
    await db.rahaza_expense_claims.insert_one(doc)
    await log_activity(user.get('id'), user.get('name'), 'create', 'expense_claim',
                       f'Buat klaim {claim_number} Rp {total:,.0f}')
    return _serialize_claim(doc)


@router.get('/claims')
async def list_claims(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0),
    user: dict = Depends(require_auth),
):
    """List klaim biaya. Karyawan biasa hanya lihat miliknya sendiri."""
    db = get_db()
    role = (user.get('role') or '').lower()
    q: dict = {}

    # Employee hanya bisa lihat klaim miliknya
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance'):
        q['employee_id'] = user.get('id')
    elif employee_id:
        q['employee_id'] = employee_id

    if status:
        if ',' in status:
            q['status'] = {'$in': status.split(',')}
        else:
            q['status'] = status
    if search:
        q['$or'] = [
            {'claim_number': {'$regex': search, '$options': 'i'}},
            {'title': {'$regex': search, '$options': 'i'}},
            {'employee_name': {'$regex': search, '$options': 'i'}},
        ]

    total_count = await db.rahaza_expense_claims.count_documents(q)
    docs = await db.rahaza_expense_claims.find(q, {'_id': 0}) \
        .sort('created_at', -1).skip(skip).limit(limit).to_list(length=limit)

    return {
        'total': total_count,
        'items': [_serialize_claim(d) for d in docs],
    }


# ── EEM Phase 4: Export ────────────────────────────────────────────────────────
# NOTE: Export route MUST be defined BEFORE parameterized routes to avoid matching conflict
@router.get('/claims/export')
async def export_claims(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    to_date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    user: dict = Depends(require_auth),
):
    """Export klaim biaya ke CSV (with RBAC filter)."""
    db = get_db()
    role = (user.get('role') or '').lower()
    q: dict = {}

    # RBAC filter
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance'):
        q['employee_id'] = user.get('id')
    elif employee_id:
        q['employee_id'] = employee_id

    if status:
        if ',' in status:
            q['status'] = {'$in': status.split(',')}
        else:
            q['status'] = status

    # Date range filter
    if from_date or to_date:
        date_q = {}
        if from_date:
            try:
                date_q['$gte'] = datetime.fromisoformat(from_date).replace(tzinfo=timezone.utc)
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        if to_date:
            try:
                date_q['$lte'] = datetime.fromisoformat(to_date).replace(hour=23, minute=59, second=59, tzinfo=timezone.utc)
            except Exception:
                logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        if date_q:
            q['created_at'] = date_q

    docs = await db.rahaza_expense_claims.find(q, {'_id': 0}).sort('created_at', -1).to_list(1000)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Nomor Klaim', 'Tanggal', 'Karyawan', 'Departemen', 'Judul', 
        'Total (Rp)', 'Status', 'Tgl Submit', 'Tgl Approved', 'Tgl Paid', 'JE Number'
    ])

    for doc in docs:
        writer.writerow([
            doc.get('claim_number', ''),
            _to_iso(doc.get('created_at'))[:10] if doc.get('created_at') else '',
            doc.get('employee_name', ''),
            doc.get('employee_dept', ''),
            doc.get('title', ''),
            doc.get('total_amount', 0),
            STATUS_LABELS.get(doc.get('status', ''), doc.get('status', '')),
            _to_iso(doc.get('submitted_at'))[:10] if doc.get('submitted_at') else '',
            _to_iso(doc.get('approved_at'))[:10] if doc.get('approved_at') else '',
            _to_iso(doc.get('paid_at'))[:10] if doc.get('paid_at') else '',
            doc.get('gl_je_number', ''),
        ])

    output.seek(0)
    filename = f"expense_claims_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get('/claims/{claim_id}')
async def get_claim(claim_id: str, user: dict = Depends(require_auth)):
    """Detail klaim biaya."""
    db = get_db()
    doc = await _get_claim_or_404(db, claim_id)
    role = (user.get('role') or '').lower()
    # Employee hanya boleh lihat miliknya
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance'):
        if doc.get('employee_id') != user.get('id'):
            raise HTTPException(403, 'Tidak punya akses ke klaim ini')
    return _serialize_claim(doc)


@router.put('/claims/{claim_id}')
async def update_claim(claim_id: str, body: ClaimUpdate, user: dict = Depends(require_auth)):
    """Update klaim (hanya status draft)."""
    db = get_db()
    doc = await _get_claim_or_404(db, claim_id)
    if doc.get('employee_id') != user.get('id') and (user.get('role') or '').lower() not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik klaim yang bisa edit')
    if doc.get('status') != 'draft':
        raise HTTPException(400, f"Klaim status '{doc.get('status')}' tidak bisa diedit. Hanya draft.")

    upd: dict = {'updated_at': _now()}
    if body.title is not None:
        upd['title'] = body.title
    if body.items is not None:
        items = [it.model_dump() for it in body.items]
        upd['items'] = items
        upd['total_amount'] = _calc_total(items)
    if body.cost_center_id is not None:
        upd['cost_center_id'] = body.cost_center_id
    if body.gl_debit_code is not None:
        upd['gl_debit_code'] = body.gl_debit_code
    if body.bank_account_id is not None:
        upd['bank_account_id'] = body.bank_account_id
    if body.notes is not None:
        upd['notes'] = body.notes

    await db.rahaza_expense_claims.update_one({'id': claim_id}, {'$set': upd})
    updated = await _get_claim_or_404(db, claim_id)
    return _serialize_claim(updated)


@router.post('/claims/{claim_id}/submit')
async def submit_claim(claim_id: str, user: dict = Depends(require_auth)):
    """Submit klaim untuk persetujuan."""
    db = get_db()
    doc = await _get_claim_or_404(db, claim_id)
    if doc.get('employee_id') != user.get('id') and (user.get('role') or '').lower() not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik klaim yang bisa submit')
    if doc.get('status') != 'draft':
        raise HTTPException(400, f"Status klaim saat ini: {doc.get('status')}. Harus draft untuk di-submit.")
    if not doc.get('items'):
        raise HTTPException(400, 'Klaim harus memiliki minimal 1 item sebelum di-submit')
    if doc.get('total_amount', 0) <= 0:
        raise HTTPException(400, 'Total klaim harus lebih dari 0')

    now = _now()
    await db.rahaza_expense_claims.update_one(
        {'id': claim_id},
        {'$set': {'status': 'submitted', 'submitted_at': now, 'updated_at': now}}
    )
    await log_activity(user.get('id'), user.get('name'), 'submit', 'expense_claim',
                       f"Submit klaim {doc.get('claim_number')} Rp {doc.get('total_amount', 0):,.0f}")

    # Notification ke HR/Manager — RC-13: koleksi kanonik `notifications` via notif_unified
    # 2026-08-07: `type` WAJIB salah satu VALID_TYPES ('rahaza' dsb). Sebelumnya
    # dikirim type='expense_claim_submitted' ⇒ ValueError ditelan `except` ⇒
    # approver TIDAK PERNAH diberi tahu. Sekarang subtype + target role.
    try:
        from utils.notif_unified import notif_insert
        await notif_insert(
            db,
            type='rahaza',
            subtype='expense_claim_submitted',
            severity='warning',
            title='Klaim Biaya Baru Menunggu Persetujuan',
            body=f"{doc.get('employee_name')} mengajukan klaim {doc.get('claim_number')} Rp {doc.get('total_amount', 0):,.0f}",
            source_type='expense_claim',
            source_id=claim_id,
            source_ref=doc.get('claim_number'),
            target_roles=list(APPROVER_ROLES),
            status='sent',
            meta={'link_module': 'hr-approval-inbox'},
        )
    except Exception:
        logging.getLogger(__name__).exception("notifikasi klaim biaya gagal dikirim")

    return {'ok': True, 'id': claim_id, 'new_status': 'submitted'}


@router.post('/claims/{claim_id}/approve')
async def approve_claim(claim_id: str, payload: ApprovePayload, user: dict = Depends(require_auth)):
    """Setujui klaim biaya."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya Manager/HR/Finance yang dapat approve')

    doc = await _get_claim_or_404(db, claim_id)
    if doc.get('status') != 'submitted':
        raise HTTPException(400, f"Status klaim saat ini: {doc.get('status')}. Harus submitted untuk di-approve.")

    now = _now()
    await db.rahaza_expense_claims.update_one(
        {'id': claim_id},
        {'$set': {
            'status': 'approved',
            'approved_by': user.get('id'),
            'approved_by_name': user.get('name'),
            'approved_at': now,
            'approval_note': payload.note or '',
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'approve', 'expense_claim',
                       f"Approve klaim {doc.get('claim_number')}")
    return {'ok': True, 'id': claim_id, 'new_status': 'approved'}


@router.post('/claims/{claim_id}/reject')
async def reject_claim(claim_id: str, payload: RejectPayload, user: dict = Depends(require_auth)):
    """Tolak klaim biaya."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya Manager/HR/Finance yang dapat reject')

    doc = await _get_claim_or_404(db, claim_id)
    if doc.get('status') not in ('submitted', 'approved'):
        raise HTTPException(400, f"Status klaim saat ini: {doc.get('status')}. Tidak bisa di-reject.")

    now = _now()
    await db.rahaza_expense_claims.update_one(
        {'id': claim_id},
        {'$set': {
            'status': 'rejected',
            'reject_reason': payload.reason,
            'rejected_by': user.get('id'),
            'rejected_by_name': user.get('name'),
            'rejected_at': now,
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'reject', 'expense_claim',
                       f"Reject klaim {doc.get('claim_number')}: {payload.reason}")
    return {'ok': True, 'id': claim_id, 'new_status': 'rejected'}


@router.post('/claims/{claim_id}/disburse')
async def disburse_claim(claim_id: str, payload: DisbursePayload, user: dict = Depends(require_auth)):
    """Finance disburse klaim — bayar ke karyawan + post GL."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'finance', 'accounting', 'staff_keuangan', 'hr_manager'):
        raise HTTPException(403, 'Hanya Finance yang dapat melakukan disbursement')

    doc = await _get_claim_or_404(db, claim_id)
    if doc.get('status') != 'approved':
        raise HTTPException(400, f"Status klaim saat ini: {doc.get('status')}. Harus approved untuk disbursement.")

    amount = float(doc.get('total_amount', 0))
    if amount <= 0:
        raise HTTPException(400, 'Total klaim 0, tidak bisa disburse')

    now = _now()
    je_date = date.today()

    # RC-05: posting WAJIB lewat engine rahaza_posting (idempoten, validasi COA/saldo/periode).
    # Default akun: Dr 6-3500 (Biaya Reimbursement Karyawan) / Cr bank default profil 'expense'.
    # ('6-1001' lama TIDAK ADA di rahaza_coa_accounts; 'rahaza_bank_accounts' = phantom →
    #  bank asli = rahaza_cash_accounts.)
    from routes.rahaza_posting import _create_posted_je
    from routes.rahaza_posting_profiles import get_mapping
    gl_debit_code = doc.get('gl_debit_code') or '6-3500'
    credit_code = (await get_mapping(db, 'expense')).get('credit_cash_default')  # default bank (profil)

    bank_acc_id = payload.bank_account_id or doc.get('bank_account_id') or ''
    if bank_acc_id:
        ba = await db.rahaza_cash_accounts.find_one({'id': bank_acc_id}, {'_id': 0})
        if ba and (ba.get('gl_account_code') or ba.get('code')):
            credit_code = ba.get('gl_account_code') or ba.get('code')

    memo = f"Reimburse {doc.get('claim_number')} — {doc.get('employee_name', '')}"
    lines = [
        {'account_code': gl_debit_code, 'debit': amount, 'credit': 0, 'description': memo, 'cost_center_id': doc.get('cost_center_id', '')},
        {'account_code': credit_code, 'debit': 0, 'credit': amount, 'description': memo, 'cost_center_id': ''},
    ]
    je_res = await _create_posted_je(
        db, je_date, memo,
        source_module='expense_claim',
        source_ref=doc.get('claim_number') or claim_id,
        lines_raw=lines, user=user,
    )
    if not je_res.get('ok'):
        raise HTTPException(400, f"Posting GL gagal: {je_res.get('error')}")
    je_id = je_res['je_id']
    je_number = je_res['je_number']

    # Update claim status
    await db.rahaza_expense_claims.update_one(
        {'id': claim_id},
        {'$set': {
            'status': 'posted',
            'paid_by': user.get('id'),
            'paid_by_name': user.get('name'),
            'paid_at': now,
            'payment_method': payload.payment_method or 'transfer',
            'gl_je_id': je_id,
            'gl_je_number': je_number,
            'bank_account_id': bank_acc_id or doc.get('bank_account_id', ''),
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'disburse', 'expense_claim',
                       f"Disburse klaim {doc.get('claim_number')} Rp {amount:,.0f} → JE {je_number}")
    return {'ok': True, 'id': claim_id, 'new_status': 'posted', 'gl_je_id': je_id, 'gl_je_number': je_number}


@router.delete('/claims/{claim_id}')
async def delete_claim(claim_id: str, user: dict = Depends(require_auth)):
    """Hapus klaim draft."""
    db = get_db()
    doc = await _get_claim_or_404(db, claim_id)
    if doc.get('employee_id') != user.get('id') and (user.get('role') or '').lower() not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik klaim yang bisa hapus')
    if doc.get('status') != 'draft':
        raise HTTPException(400, 'Hanya klaim draft yang bisa dihapus')
    await db.rahaza_expense_claims.delete_one({'id': claim_id})
    return {'ok': True, 'deleted': claim_id}


# ── EEM Phase 4: Bulk Actions ──────────────────────────────────────────────────
class BulkApproveRequest(BaseModel):
    claim_ids: List[str] = Field(..., description='List of claim IDs to approve')
    approval_note: Optional[str] = ''


@router.post('/claims/bulk-approve')
async def bulk_approve_claims(body: BulkApproveRequest, user: dict = Depends(require_auth)):
    """Bulk approve multiple claims (Finance/HR/Manager only)."""
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Tidak punya hak approve')

    db = get_db()
    results = {'success': [], 'failed': []}

    for claim_id in body.claim_ids:
        try:
            doc = await db.rahaza_expense_claims.find_one({'id': claim_id}, {'_id': 0})
            if not doc:
                results['failed'].append({'id': claim_id, 'reason': 'Tidak ditemukan'})
                continue

            if doc.get('status') != 'submitted':
                results['failed'].append({'id': claim_id, 'reason': f'Status {doc.get("status")} tidak bisa di-approve'})
                continue

            # Approve
            now = _now()
            await db.rahaza_expense_claims.update_one(
                {'id': claim_id},
                {'$set': {
                    'status': 'approved',
                    'approved_at': now,
                    'approved_by': user.get('id'),
                    'approved_by_name': user.get('name'),
                    'approval_note': body.approval_note or '',
                    'updated_at': now,
                }}
            )
            await log_activity(user.get('id'), user.get('name'), 'approve', 'expense_claim',
                             f'Bulk approve klaim {doc.get("claim_number")}')
            results['success'].append(claim_id)

        except Exception as e:
            logger.error(f'Bulk approve claim {claim_id} error: {e}')
            results['failed'].append({'id': claim_id, 'reason': str(e)})

    return {
        'ok': True,
        'total': len(body.claim_ids),
        'success_count': len(results['success']),
        'failed_count': len(results['failed']),
        'results': results,
    }


# ── Supporting data ────────────────────────────────────────────────────────────
@router.get('/categories')
async def get_categories(user: dict = Depends(require_auth)):
    """
    Daftar kategori expense.
    Prioritas sumber: master kategori (employee_expense_categories) → COA 6-3xxx → fallback constants.
    Output kompatibel dengan format {code, name, label, description}.
    """
    db = get_db()

    # Prioritas 1: Master kategori (Phase 5A)
    master_cats = await db.employee_expense_categories.find(
        {'is_active': True}, {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'description': 1}
    ).sort('name', 1).to_list(200)

    if master_cats:
        categories = [
            {
                'code': cat.get('code') or cat['name'],
                'name': cat['name'],
                'label': f"{cat['code']} - {cat['name']}" if cat.get('code') else cat['name'],
                'description': cat.get('description') or '',
            }
            for cat in master_cats
        ]
        return {'categories': categories, 'source': 'master'}

    # Prioritas 2: COA accounts (6-3xxx series)
    coa_categories = await db.rahaza_coa_accounts.find(
        {
            'code': {'$regex': '^6-3'},
            'is_active': {'$ne': False},
        },
        {'_id': 0, 'code': 1, 'name': 1, 'description': 1}
    ).sort('code', 1).to_list(100)

    if coa_categories:
        categories = [
            {
                'code': cat['code'],
                'name': cat['name'],
                'label': f"{cat['code']} - {cat['name']}",
                'description': cat.get('description', '')
            }
            for cat in coa_categories
        ]
        return {'categories': categories, 'source': 'coa'}

    # Prioritas 3: Fallback constants (backward compatibility)
    categories = [
        {'code': cat, 'name': cat, 'label': cat, 'description': ''}
        for cat in EXPENSE_CATEGORIES
    ]
    return {'categories': categories, 'source': 'fallback'}

