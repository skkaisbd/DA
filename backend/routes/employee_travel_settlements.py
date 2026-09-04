"""
Employee Travel Settlements — Rekonsiliasi Biaya Perjalanan Dinas
CV. Dewi Aditya — Employee Expense Management (EEM) Phase B

Alur:
  1. Karyawan pulang dinas, buat settlement draft
  2. Input biaya aktual + struk
  3. Submit → Manager/HR approve → Finance post GL

GL Posting saat post:
  Dr  6-3400  Biaya Perjalanan Dinas        (total_actual)
  Cr  1-1610  Uang Muka Karyawan            (advance_received)

  Jika actual > advance (bayar tambahan ke karyawan):
      Cr  1-1201  Bank                       (|selisih|)
  Jika actual < advance (terima kembalian dari karyawan):
      Dr  1-1201  Bank                       (selisih)

Prefix: /api/hr/expenses

Endpoints:
  POST /travel/{req_id}/settlements         — buat settlement draft
  GET  /travel/{req_id}/settlements         — list settlements untuk 1 trip
  GET  /settlements                         — all settlements (finance queue)
  GET  /settlements/{id}                    — detail
  PUT  /settlements/{id}                    — update draft
  POST /settlements/{id}/submit             — submit
  POST /settlements/{id}/approve            — approve
  POST /settlements/{id}/post               — post GL (Finance)
  GET  /outstanding-advances                — laporan uang muka outstanding
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
router = APIRouter(prefix='/api/hr/expenses', tags=['Travel-Settlement'])

# ── GL Account Codes ─────────────────────────────────────────────────────
GL_TRAVEL_EXPENSE    = '6-3400'   # Biaya Perjalanan Dinas
GL_EMPLOYEE_ADVANCE  = '1-1610'   # Uang Muka Karyawan
GL_BANK_DEFAULT      = '1-1201'   # Bank BCA (default)

APPROVER_ROLES = ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance')


# ── Helpers ────────────────────────────────────────────────────────────────────
def _now():
    return datetime.now(timezone.utc)


def _to_iso(v):
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(tzinfo=timezone.utc).isoformat() if v.tzinfo is None else v.isoformat()
    return str(v)


def _serialize(doc: dict) -> dict:
    if not doc:
        return {}
    d = serialize_doc(doc)
    for key in ('created_at', 'updated_at', 'submitted_at', 'approved_at', 'posted_at'):
        if key in d:
            d[key] = _to_iso(d[key])
    return d


async def _get_or_404(db, stl_id: str) -> dict:
    doc = await db.employee_travel_settlements.find_one({'id': stl_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, f'Settlement {stl_id} tidak ditemukan')
    return doc


async def _get_travel_or_404(db, req_id: str) -> dict:
    doc = await db.employee_travel_requests.find_one({'id': req_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, f'Travel request {req_id} tidak ditemukan')
    return doc


async def _gen_settlement_number(db, requested: str = '') -> str:
    """Nomor penyelesaian dinas — SATU PINTU kebijakan penomoran (Otomatis/Manual).

    SESI #27 (batch-3 Fase G): ditegakkan lewat `issue_number` supaya setelan
    Otomatis/Manual di layar admin benar-benar berlaku (dulu selalu otomatis).
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, 'employee_travel_settlements.settlement_number',
                              requested=requested)


def _calc_total(items: list) -> float:
    return sum(float(it.get('amount', 0) or 0) for it in items)


def _settlement_type(advance: float, actual: float) -> str:
    diff = round(advance - actual, 2)
    if diff > 0:
        return 'return'       # ada kembalian dari karyawan
    elif diff < 0:
        return 'additional'   # karyawan perlu bayar tambahan
    return 'exact'


# ── Pydantic Models ────────────────────────────────────────────────────────────
class SettlementItem(BaseModel):
    date: str
    category: str
    amount: float = Field(ge=0)
    notes: Optional[str] = ''
    receipt_url: Optional[str] = ''


class SettlementCreate(BaseModel):
    actual_items: List[SettlementItem] = Field(default_factory=list)
    notes: Optional[str] = ''
    bank_account_id: Optional[str] = ''   # override bank account for selisih payment
    # SESI #27 — nomor ketikan staf (HANYA dipakai bila kebijakan = MANUAL).
    settlement_number: Optional[str] = ''


class SettlementUpdate(BaseModel):
    actual_items: Optional[List[SettlementItem]] = None
    notes: Optional[str] = None
    bank_account_id: Optional[str] = None


class ApprovePayload(BaseModel):
    note: Optional[str] = ''


class RejectPayload(BaseModel):
    reason: str


class PostPayload(BaseModel):
    bank_account_id: Optional[str] = ''
    note: Optional[str] = ''


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post('/travel/{req_id}/settlements', status_code=201)
async def create_settlement(req_id: str, body: SettlementCreate, user: dict = Depends(require_auth)):
    """Buat settlement draft untuk perjalanan dinas yang sudah selesai."""
    db = get_db()
    tr = await _get_travel_or_404(db, req_id)

    # Hanya karyawan pemilik atau approver yang bisa buat settlement
    role = (user.get('role') or '').lower()
    if tr.get('employee_id') != user.get('id') and role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya pemilik perjalanan yang dapat membuat settlement')

    # Status harus advance_paid atau completed
    if tr.get('status') not in ('advance_paid', 'on_trip', 'completed', 'approved'):
        raise HTTPException(
            400,
            f"Travel request status '{tr.get('status')}' belum bisa di-settle. "
            "Harus minimal 'approved' atau 'advance_paid'."
        )

    # Cek apakah sudah ada settlement yang belum di-reject
    existing = await db.employee_travel_settlements.find_one(
        {'travel_request_id': req_id, 'status': {'$nin': ['rejected']}},
        {'_id': 0, 'id': 1, 'settlement_number': 1, 'status': 1}
    )
    if existing:
        raise HTTPException(
            400,
            f"Settlement {existing.get('settlement_number')} ({existing.get('status')}) sudah ada. "
            "Hapus atau reject dulu sebelum membuat yang baru."
        )

    items = [it.model_dump() for it in (body.actual_items or [])]
    total_actual = _calc_total(items)
    advance = float(tr.get('cash_advance_paid', 0) or tr.get('cash_advance_approved', 0) or 0)
    difference = round(advance - total_actual, 2)
    stl_type = _settlement_type(advance, total_actual)

    settlement_number = await _gen_settlement_number(
        db, (body.settlement_number or '').strip())
    now = _now()
    doc = {
        'id': str(uuid.uuid4()),
        'settlement_number': settlement_number,
        'travel_request_id': req_id,
        'trip_number': tr.get('trip_number'),
        'employee_id': tr.get('employee_id'),
        'employee_name': tr.get('employee_name'),
        'employee_dept': tr.get('employee_dept'),
        'destination': tr.get('destination'),
        'start_date': tr.get('start_date'),
        'end_date': tr.get('end_date'),
        'purpose': tr.get('purpose'),
        # Actual expenses
        'actual_items': items,
        'total_actual': total_actual,
        # Advance reconciliation
        'advance_received': advance,
        'advance_je_id': tr.get('advance_je_id', ''),
        'advance_je_number': tr.get('advance_je_number', ''),
        'difference': difference,              # positif = kembalian, negatif = kurang bayar
        'settlement_type': stl_type,           # return | additional | exact
        # Settlement meta
        'bank_account_id': body.bank_account_id or '',
        'notes': body.notes or '',
        'status': 'draft',
        'approval_note': '',
        'reject_reason': '',
        'submitted_at': None,
        'approved_at': None,
        'approved_by': '',
        'approved_by_name': '',
        'posted_at': None,
        'posted_by': '',
        'posted_by_name': '',
        'gl_je_id': '',
        'gl_je_number': '',
        'gl_je_lines': [],
        'created_by': user.get('id'),
        'created_by_name': user.get('name'),
        'created_at': now,
        'updated_at': now,
    }
    await db.employee_travel_settlements.insert_one(doc)
    await log_activity(user.get('id'), user.get('name'), 'create', 'travel_settlement',
                       f'Buat settlement {settlement_number} untuk {tr.get("trip_number")} — aktual Rp {total_actual:,.0f}')
    return _serialize(doc)


@router.get('/travel/{req_id}/settlements')
async def list_trip_settlements(req_id: str, user: dict = Depends(require_auth)):
    """List settlements untuk 1 travel request."""
    db = get_db()
    tr = await _get_travel_or_404(db, req_id)
    role = (user.get('role') or '').lower()
    if tr.get('employee_id') != user.get('id') and role not in APPROVER_ROLES:
        raise HTTPException(403, 'Tidak punya akses')
    docs = await db.employee_travel_settlements.find(
        {'travel_request_id': req_id}, {'_id': 0}
    ).sort('created_at', -1).to_list(20)
    return {'total': len(docs), 'items': [_serialize(d) for d in docs]}


@router.get('/settlements')
async def list_all_settlements(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0),
    user: dict = Depends(require_auth),
):
    """List semua settlements. Finance/HR lihat semua, karyawan hanya miliknya."""
    db = get_db()
    role = (user.get('role') or '').lower()
    q: dict = {}

    if role not in APPROVER_ROLES:
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
            {'settlement_number': {'$regex': search, '$options': 'i'}},
            {'trip_number': {'$regex': search, '$options': 'i'}},
            {'employee_name': {'$regex': search, '$options': 'i'}},
            {'destination': {'$regex': search, '$options': 'i'}},
        ]

    total_count = await db.employee_travel_settlements.count_documents(q)
    docs = await db.employee_travel_settlements.find(q, {'_id': 0}) \
        .sort('created_at', -1).skip(skip).limit(limit).to_list(length=limit)
    return {'total': total_count, 'items': [_serialize(d) for d in docs]}


# ── EEM Phase 4: Export ────────────────────────────────────────────────────────
# NOTE: Export routes MUST be defined BEFORE parameterized routes to avoid matching conflict
@router.get('/settlements/export')
async def export_settlements(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    to_date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    user: dict = Depends(require_auth),
):
    """Export settlements ke CSV (with RBAC filter)."""
    db = get_db()
    role = (user.get('role') or '').lower()
    q: dict = {}

    # RBAC filter
    if role not in APPROVER_ROLES:
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

    docs = await db.employee_travel_settlements.find(q, {'_id': 0}).sort('created_at', -1).to_list(1000)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Nomor Settlement', 'Nomor Trip', 'Tanggal', 'Karyawan', 'Departemen', 'Destinasi',
        'Uang Muka (Rp)', 'Aktual (Rp)', 'Selisih (Rp)', 'Tipe', 'Status', 'Tgl Approved', 'Tgl Posted', 'JE Number'
    ])

    for doc in docs:
        writer.writerow([
            doc.get('settlement_number', ''),
            doc.get('trip_number', ''),
            _to_iso(doc.get('created_at'))[:10] if doc.get('created_at') else '',
            doc.get('employee_name', ''),
            doc.get('employee_dept', ''),
            doc.get('destination', ''),
            doc.get('advance_received', 0),
            doc.get('total_actual', 0),
            doc.get('difference', 0),
            doc.get('settlement_type', ''),
            doc.get('status', ''),
            _to_iso(doc.get('approved_at'))[:10] if doc.get('approved_at') else '',
            _to_iso(doc.get('posted_at'))[:10] if doc.get('posted_at') else '',
            doc.get('gl_je_number', ''),
        ])

    output.seek(0)
    filename = f"travel_settlements_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get('/outstanding-advances/export')
async def export_outstanding_advances(user: dict = Depends(require_auth)):
    """Export outstanding advances ke CSV (with RBAC filter)."""
    db = get_db()
    role = (user.get('role') or '').lower()
    q = {'status': {'$in': ['advance_paid', 'on_trip']}, 'cash_advance_paid': {'$gt': 0}}

    # RBAC filter
    if role not in APPROVER_ROLES:
        q['employee_id'] = user.get('id')

    docs = await db.employee_travel_requests.find(q, {'_id': 0}).sort('advance_paid_at', -1).to_list(500)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Nomor Trip', 'Tanggal Berangkat', 'Tanggal Kembali', 'Karyawan', 'Departemen',
        'Destinasi', 'Uang Muka (Rp)', 'Status', 'Tgl Disburse', 'Advance JE', 'Hari Outstanding'
    ])

    now = datetime.now(timezone.utc)
    for doc in docs:
        advance_paid_at = doc.get('advance_paid_at')
        days_outstanding = 0
        if advance_paid_at:
            if isinstance(advance_paid_at, str):
                try:
                    advance_paid_at = datetime.fromisoformat(advance_paid_at.replace('Z', '+00:00'))
                except Exception:
                    logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
            if isinstance(advance_paid_at, datetime):
                # RC-23: string date-only ("2026-05-06") menghasilkan datetime NAIVE →
                # aware - naive = TypeError. Normalisasi tz sebelum pengurangan.
                if advance_paid_at.tzinfo is None:
                    advance_paid_at = advance_paid_at.replace(tzinfo=timezone.utc)
                days_outstanding = (now - advance_paid_at).days

        writer.writerow([
            doc.get('trip_number', ''),
            _to_iso(doc.get('departure_date'))[:10] if doc.get('departure_date') else '',
            _to_iso(doc.get('return_date'))[:10] if doc.get('return_date') else '',
            doc.get('employee_name', ''),
            doc.get('employee_dept', ''),
            doc.get('destination', ''),
            doc.get('cash_advance_paid', 0),
            doc.get('status', ''),
            _to_iso(advance_paid_at)[:10] if advance_paid_at else '',
            doc.get('advance_je_number', ''),
            days_outstanding,
        ])

    output.seek(0)
    filename = f"outstanding_advances_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get('/settlements/{stl_id}')
async def get_settlement(stl_id: str, user: dict = Depends(require_auth)):
    """Detail settlement."""
    db = get_db()
    doc = await _get_or_404(db, stl_id)
    role = (user.get('role') or '').lower()
    if doc.get('employee_id') != user.get('id') and role not in APPROVER_ROLES:
        raise HTTPException(403, 'Tidak punya akses')
    return _serialize(doc)


@router.put('/settlements/{stl_id}')
async def update_settlement(stl_id: str, body: SettlementUpdate, user: dict = Depends(require_auth)):
    """Update settlement draft."""
    db = get_db()
    doc = await _get_or_404(db, stl_id)
    role = (user.get('role') or '').lower()
    if doc.get('employee_id') != user.get('id') and role not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik yang bisa edit')
    if doc.get('status') != 'draft':
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa diedit")

    upd: dict = {'updated_at': _now()}
    if body.actual_items is not None:
        items = [it.model_dump() for it in body.actual_items]
        total_actual = _calc_total(items)
        advance = float(doc.get('advance_received', 0))
        difference = round(advance - total_actual, 2)
        upd['actual_items'] = items
        upd['total_actual'] = total_actual
        upd['difference'] = difference
        upd['settlement_type'] = _settlement_type(advance, total_actual)
    if body.notes is not None:
        upd['notes'] = body.notes
    if body.bank_account_id is not None:
        upd['bank_account_id'] = body.bank_account_id

    await db.employee_travel_settlements.update_one({'id': stl_id}, {'$set': upd})
    updated = await _get_or_404(db, stl_id)
    return _serialize(updated)


@router.post('/settlements/{stl_id}/submit')
async def submit_settlement(stl_id: str, user: dict = Depends(require_auth)):
    """Submit settlement untuk diapprove."""
    db = get_db()
    doc = await _get_or_404(db, stl_id)
    role = (user.get('role') or '').lower()
    if doc.get('employee_id') != user.get('id') and role not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik yang bisa submit')
    if doc.get('status') != 'draft':
        raise HTTPException(400, f"Status '{doc.get('status')}' bukan draft")
    if not doc.get('actual_items'):
        raise HTTPException(400, 'Harus ada minimal 1 item biaya aktual')

    now = _now()
    await db.employee_travel_settlements.update_one(
        {'id': stl_id},
        {'$set': {'status': 'submitted', 'submitted_at': now, 'updated_at': now}}
    )

    # Notification — RC-13: koleksi kanonik `notifications` via notif_unified
    # 2026-08-07: type wajib VALID_TYPES (dulu gagal diam-diam).
    try:
        from utils.notif_unified import notif_insert
        await notif_insert(
            db,
            type='rahaza',
            subtype='travel_settlement_submitted',
            severity='warning',
            title='Settlement Perjalanan Dinas Menunggu Approval',
            body=(
                f"{doc.get('employee_name')} mengajukan settlement "
                f"{doc.get('settlement_number')} — {doc.get('destination')} "
                f"(aktual Rp {doc.get('total_actual', 0):,.0f})"
            ),
            source_type='travel_settlement',
            source_id=stl_id,
            source_ref=doc.get('settlement_number'),
            target_roles=list(APPROVER_ROLES),
            status='sent',
            meta={'link_module': 'hr-approval-inbox'},
        )
    except Exception:
        logging.getLogger(__name__).exception("notifikasi settlement gagal dikirim")

    await log_activity(user.get('id'), user.get('name'), 'submit', 'travel_settlement',
                       f"Submit settlement {doc.get('settlement_number')}")
    return {'ok': True, 'id': stl_id, 'new_status': 'submitted'}


@router.post('/settlements/{stl_id}/approve')
async def approve_settlement(stl_id: str, payload: ApprovePayload, user: dict = Depends(require_auth)):
    """Approve settlement (Manager/HR)."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya Manager/HR yang dapat approve')
    doc = await _get_or_404(db, stl_id)
    if doc.get('status') != 'submitted':
        raise HTTPException(400, f"Status '{doc.get('status')}' harus submitted")

    now = _now()
    await db.employee_travel_settlements.update_one(
        {'id': stl_id},
        {'$set': {
            'status': 'approved',
            'approved_by': user.get('id'),
            'approved_by_name': user.get('name'),
            'approved_at': now,
            'approval_note': payload.note or '',
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'approve', 'travel_settlement',
                       f"Approve settlement {doc.get('settlement_number')}")
    return {'ok': True, 'id': stl_id, 'new_status': 'approved'}


@router.post('/settlements/{stl_id}/reject')
async def reject_settlement(stl_id: str, payload: RejectPayload, user: dict = Depends(require_auth)):
    """Reject settlement."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya Manager/HR yang dapat reject')
    doc = await _get_or_404(db, stl_id)
    if doc.get('status') not in ('submitted', 'approved'):
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa di-reject")

    now = _now()
    await db.employee_travel_settlements.update_one(
        {'id': stl_id},
        {'$set': {
            'status': 'rejected',
            'reject_reason': payload.reason,
            'rejected_by': user.get('id'),
            'rejected_by_name': user.get('name'),
            'rejected_at': now,
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'reject', 'travel_settlement',
                       f"Reject settlement {doc.get('settlement_number')}: {payload.reason}")
    return {'ok': True, 'id': stl_id, 'new_status': 'rejected'}


@router.post('/settlements/{stl_id}/post')
async def post_settlement_gl(stl_id: str, payload: PostPayload, user: dict = Depends(require_auth)):
    """
    Finance: Post GL settlement perjalanan dinas.

    JE yang dibuat:
      Dr  6-3400  Biaya Perjalanan Dinas        (total_actual)
      Cr  1-1610  Uang Muka Karyawan            (advance_received)

      PLUS salah satu:
      -- Jika actual > advance (karyawan harus dibayar tambahan):
          Cr  1-1201  Bank                       (|difference|)
      -- Jika actual < advance (karyawan kembalikan sisa):
          Dr  1-1201  Bank                       (difference)
      -- Jika exact: tidak ada baris bank tambahan
    """
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'finance'):
        raise HTTPException(403, 'Hanya Finance yang dapat melakukan posting GL')

    doc = await _get_or_404(db, stl_id)
    if doc.get('status') != 'approved':
        raise HTTPException(400, f"Status '{doc.get('status')}' harus 'approved' sebelum di-post")

    total_actual  = float(doc.get('total_actual', 0))
    advance       = float(doc.get('advance_received', 0))
    difference    = float(doc.get('difference', 0))  # advance - actual
    stl_type      = doc.get('settlement_type', 'exact')

    if total_actual <= 0 and advance <= 0:
        raise HTTPException(400, 'Total biaya aktual dan advance keduanya 0')

    # Determine bank account — RC-05: bank asli = rahaza_cash_accounts (rahaza_bank_accounts phantom)
    bank_acc_id = payload.bank_account_id or doc.get('bank_account_id', '')
    bank_gl_code = GL_BANK_DEFAULT
    if bank_acc_id:
        ba = await db.rahaza_cash_accounts.find_one({'id': bank_acc_id}, {'_id': 0})
        if ba and (ba.get('gl_account_code') or ba.get('code')):
            bank_gl_code = ba.get('gl_account_code') or ba.get('code')

    now = _now()
    je_date = date.today()
    memo = f"Settlement Dinas {doc.get('settlement_number')} — {doc.get('employee_name', '')} — {doc.get('destination', '')}"

    lines = []
    total_debit  = 0.0
    total_credit = 0.0

    # Line 1: Dr Beban Perjalanan Dinas (full actual amount)
    if total_actual > 0:
        lines.append({
            'account_code': GL_TRAVEL_EXPENSE,
            'debit': total_actual, 'credit': 0,
            'description': memo, 'cost_center_id': '',
        })
        total_debit += total_actual

    # Line 2: Cr Uang Muka Karyawan (clear advance receivable)
    if advance > 0:
        lines.append({
            'account_code': GL_EMPLOYEE_ADVANCE,
            'debit': 0, 'credit': advance,
            'description': f'Clear advance {doc.get("trip_number","")}',
            'cost_center_id': '',
        })
        total_credit += advance

    # Line 3: Bank adjustment untuk selisih
    abs_diff = abs(difference)
    if abs_diff > 0.01:  # tolerance
        if stl_type == 'return':      # advance > actual: karyawan kembalikan
            # Dr Bank (terima kembalian)
            lines.append({
                'account_code': bank_gl_code,
                'debit': abs_diff, 'credit': 0,
                'description': f'Kembalian advance dari {doc.get("employee_name","")}',
                'cost_center_id': '',
            })
            total_debit += abs_diff
        elif stl_type == 'additional':  # actual > advance: bayar tambahan ke karyawan
            # Cr Bank (bayar ke karyawan)
            lines.append({
                'account_code': bank_gl_code,
                'debit': 0, 'credit': abs_diff,
                'description': f'Bayar tambahan ke {doc.get("employee_name","")}',
                'cost_center_id': '',
            })
            total_credit += abs_diff

    # Validate balanced
    if abs(total_debit - total_credit) > 0.01:
        # Should never happen, but safety guard
        logger.error(f'JE imbalance: Dr={total_debit} Cr={total_credit} for settlement {stl_id}')

    # RC-05: posting WAJIB lewat engine rahaza_posting
    from routes.rahaza_posting import _create_posted_je
    je_res = await _create_posted_je(
        db, je_date, memo,
        source_module='travel_settlement',
        source_ref=doc.get('settlement_number') or stl_id,
        lines_raw=lines, user=user,
    )
    if not je_res.get('ok'):
        raise HTTPException(400, f"Posting GL gagal: {je_res.get('error')}")
    je_id = je_res['je_id']
    je_number = je_res['je_number']

    # Update settlement
    await db.employee_travel_settlements.update_one(
        {'id': stl_id},
        {'$set': {
            'status': 'posted',
            'posted_by': user.get('id'),
            'posted_by_name': user.get('name'),
            'posted_at': now,
            'gl_je_id': je_id,
            'gl_je_number': je_number,
            'gl_je_lines': lines,
            'updated_at': now,
        }}
    )

    # Mark travel request as completed
    await db.employee_travel_requests.update_one(
        {'id': doc.get('travel_request_id')},
        {'$set': {'status': 'completed', 'completed_at': now, 'updated_at': now}}
    )

    await log_activity(
        user.get('id'), user.get('name'), 'post_gl', 'travel_settlement',
        f"Post GL settlement {doc.get('settlement_number')} — {stl_type} — JE {je_number}"
    )
    return {
        'ok': True, 'id': stl_id, 'new_status': 'posted',
        'gl_je_id': je_id, 'gl_je_number': je_number,
        'settlement_type': stl_type,
        'total_actual': total_actual,
        'advance_received': advance,
        'difference': difference,
        'je_lines': lines,
    }


# ── Outstanding Cash Advance Report ───────────────────────────────────────────────
@router.get('/outstanding-advances')
async def outstanding_advances(user: dict = Depends(require_auth)):
    """
    Laporan Uang Muka Outstanding (1-1610 belum ter-clear).
    
    Menampilkan semua travel request yg advance sudah dibayar tapi settlement belum di-post.
    """
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        return {'total': 0, 'total_outstanding': 0, 'items': []}

    # Travel requests dengan status advance_paid atau on_trip (advance sudah keluar, belum settled)
    paid_requests = await db.employee_travel_requests.find(
        {'status': {'$in': ['advance_paid', 'on_trip']}, 'cash_advance_paid': {'$gt': 0}},
        {'_id': 0}
    ).sort('advance_paid_at', 1).to_list(500)

    # Untuk setiap request, cek apakah sudah ada settlement posted
    results = []
    total_outstanding = 0.0

    for tr in paid_requests:
        settled = await db.employee_travel_settlements.find_one(
            {'travel_request_id': tr['id'], 'status': 'posted'},
            {'_id': 0, 'id': 1}
        )
        if not settled:
            advance = float(tr.get('cash_advance_paid', 0))
            total_outstanding += advance
            # Check if there's a pending settlement
            pending_stl = await db.employee_travel_settlements.find_one(
                {'travel_request_id': tr['id'], 'status': {'$in': ['draft', 'submitted', 'approved']}},
                {'_id': 0, 'settlement_number': 1, 'status': 1}
            )
            results.append({
                'id': tr.get('id'),
                'trip_number': tr.get('trip_number'),
                'employee_id': tr.get('employee_id'),
                'employee_name': tr.get('employee_name'),
                'employee_dept': tr.get('employee_dept'),
                'destination': tr.get('destination'),
                'end_date': tr.get('end_date'),
                'cash_advance_paid': advance,
                'advance_paid_at': _to_iso(tr.get('advance_paid_at')),
                'status': tr.get('status'),
                'pending_settlement': pending_stl,
                # Days since end_date
                'days_since_return': (
                    (date.today() - date.fromisoformat(tr['end_date'])).days
                    if tr.get('end_date') else None
                ),
            })

    # Sort by oldest first (most overdue)
    results.sort(key=lambda x: x.get('advance_paid_at') or '', reverse=False)

    return {
        'total': len(results),
        'total_outstanding': total_outstanding,
        'gl_account': GL_EMPLOYEE_ADVANCE,
        'items': results,
    }


@router.get('/settlement-summary')
async def settlement_summary(user: dict = Depends(require_auth)):
    """Summary stats untuk settlement dashboard."""
    db = get_db()
    role = (user.get('role') or '').lower()
    is_approver = role in APPROVER_ROLES
    base_q = {} if is_approver else {'employee_id': user.get('id')}

    statuses = ['draft', 'submitted', 'approved', 'posted', 'rejected']
    counts = {}
    for s in statuses:
        counts[s] = await db.employee_travel_settlements.count_documents({**base_q, 'status': s})

    # Total amounts
    pipeline_actual = [
        {'$match': {**base_q, 'status': {'$in': ['submitted', 'approved', 'posted']}}},
        {'$group': {'_id': None,
                    'total_actual': {'$sum': '$total_actual'},
                    'total_advance': {'$sum': '$advance_received'},
                    'total_return': {'$sum': {'$cond': [{'$gt': ['$difference', 0]}, '$difference', 0]}},
                    'total_additional': {'$sum': {'$cond': [{'$lt': ['$difference', 0]}, {'$abs': '$difference'}, 0]}}}}
    ]
    totals = {'total_actual': 0, 'total_advance': 0, 'total_return': 0, 'total_additional': 0}
    async for d in db.employee_travel_settlements.aggregate(pipeline_actual):
        totals = d

    # Outstanding advances
    outstanding_count = await db.employee_travel_requests.count_documents(
        {'status': {'$in': ['advance_paid', 'on_trip']}, 'cash_advance_paid': {'$gt': 0}}
    )

    return {
        'settlement_counts': counts,
        'totals': totals,
        'outstanding_advances_count': outstanding_count,
        'pending_post': counts.get('approved', 0),
    }



# ── EEM Phase 4: Bulk Actions ──────────────────────────────────────────────────
class BulkApproveSettlementRequest(BaseModel):
    settlement_ids: List[str] = Field(..., description='List of settlement IDs to approve')
    approval_note: Optional[str] = ''


@router.post('/settlements/bulk-approve')
async def bulk_approve_settlements(body: BulkApproveSettlementRequest, user: dict = Depends(require_auth)):
    """Bulk approve multiple settlements (Finance/HR/Manager only)."""
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Tidak punya hak approve')

    db = get_db()
    results = {'success': [], 'failed': []}

    for stl_id in body.settlement_ids:
        try:
            doc = await db.employee_travel_settlements.find_one({'id': stl_id}, {'_id': 0})
            if not doc:
                results['failed'].append({'id': stl_id, 'reason': 'Tidak ditemukan'})
                continue

            if doc.get('status') != 'submitted':
                results['failed'].append({'id': stl_id, 'reason': f'Status {doc.get("status")} tidak bisa di-approve'})
                continue

            # Approve
            now = _now()
            await db.employee_travel_settlements.update_one(
                {'id': stl_id},
                {'$set': {
                    'status': 'approved',
                    'approved_at': now,
                    'approved_by': user.get('id'),
                    'approved_by_name': user.get('name'),
                    'approval_note': body.approval_note or '',
                    'updated_at': now,
                }}
            )
            await log_activity(user.get('id'), user.get('name'), 'approve', 'travel_settlement',
                             f'Bulk approve settlement {doc.get("settlement_number")}')
            results['success'].append(stl_id)

        except Exception as e:
            logger.error(f'Bulk approve settlement {stl_id} error: {e}')
            results['failed'].append({'id': stl_id, 'reason': str(e)})

    return {
        'ok': True,
        'total': len(body.settlement_ids),
        'success_count': len(results['success']),
        'failed_count': len(results['failed']),
        'results': results,
    }


class BulkPostSettlementRequest(BaseModel):
    settlement_ids: List[str] = Field(..., description='List of settlement IDs to post GL')


@router.post('/settlements/bulk-post')
async def bulk_post_settlements(body: BulkPostSettlementRequest, user: dict = Depends(require_auth)):
    """Bulk post GL for multiple settlements (Finance only)."""
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'finance'):
        raise HTTPException(403, 'Hanya Finance yang bisa post GL')

    db = get_db()
    results = {'success': [], 'failed': []}

    for stl_id in body.settlement_ids:
        try:
            doc = await db.employee_travel_settlements.find_one({'id': stl_id}, {'_id': 0})
            if not doc:
                results['failed'].append({'id': stl_id, 'reason': 'Tidak ditemukan'})
                continue

            if doc.get('status') != 'approved':
                results['failed'].append({'id': stl_id, 'reason': f'Status {doc.get("status")}, harus approved dulu'})
                continue

            if doc.get('gl_je_id'):
                results['failed'].append({'id': stl_id, 'reason': 'Sudah di-post GL'})
                continue

            # Import rahaza_posting here to avoid circular imports
            from routes.rahaza_posting import _generate_je_number, _create_journal_entry

            # Build JE lines
            advance = float(doc.get('advance_received', 0))
            actual = float(doc.get('total_actual', 0))
            difference = float(doc.get('difference', 0))

            je_lines = [
                {'account_code': GL_TRAVEL_EXPENSE, 'description': 'Biaya Perjalanan Dinas', 'debit': actual, 'credit': 0},
                {'account_code': GL_EMPLOYEE_ADVANCE, 'description': 'Clearing Uang Muka', 'debit': 0, 'credit': advance},
            ]

            if difference > 0:
                je_lines.append({
                    'account_code': GL_BANK_DEFAULT,
                    'description': 'Kembalian dari karyawan',
                    'debit': difference,
                    'credit': 0
                })
            elif difference < 0:
                je_lines.append({
                    'account_code': GL_BANK_DEFAULT,
                    'description': 'Bayar tambahan ke karyawan',
                    'debit': 0,
                    'credit': abs(difference)
                })

            # Create JE
            je_number = await _generate_je_number(db, 'STL')
            je_id = str(uuid.uuid4())
            await _create_journal_entry(
                db=db,
                je_id=je_id,
                je_number=je_number,
                ref_id=stl_id,
                ref_type='travel_settlement',
                ref_number=doc.get('settlement_number', ''),
                description=f'Settlement {doc.get("trip_number")} — {doc.get("destination")}',
                lines=je_lines,
                posted_by=user.get('id'),
                posted_by_name=user.get('name'),
            )

            # Update settlement
            now = _now()
            await db.employee_travel_settlements.update_one(
                {'id': stl_id},
                {'$set': {
                    'status': 'posted',
                    'gl_je_id': je_id,
                    'gl_je_number': je_number,
                    'gl_je_lines': je_lines,
                    'posted_at': now,
                    'posted_by': user.get('id'),
                    'posted_by_name': user.get('name'),
                    'updated_at': now,
                }}
            )

            await log_activity(user.get('id'), user.get('name'), 'post_gl', 'travel_settlement',
                             f'Bulk post GL settlement {doc.get("settlement_number")} → JE {je_number}')
            results['success'].append({'id': stl_id, 'je_number': je_number})

        except Exception as e:
            logger.error(f'Bulk post settlement {stl_id} error: {e}')
            results['failed'].append({'id': stl_id, 'reason': str(e)})

    return {
        'ok': True,
        'total': len(body.settlement_ids),
        'success_count': len(results['success']),
        'failed_count': len(results['failed']),
        'results': results,
    }

