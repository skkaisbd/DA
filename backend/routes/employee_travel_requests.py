"""
Employee Travel Requests (Perjalanan Dinas) — Routes
CV. Dewi Aditya — Employee Expense Management (EEM)

Perjalanan dinas karyawan: request → approval → cash advance → on_trip → completed

Status flow: draft → submitted → approved/rejected → advance_paid → on_trip → completed

Prefix: /api/hr/expenses/travel

Endpoints:
  POST /travel                          — create travel request (draft)
  GET  /travel                          — list requests
  GET  /travel/{id}                     — detail
  PUT  /travel/{id}                     — update draft
  POST /travel/{id}/submit              — submit for approval
  POST /travel/{id}/approve             — approve
  POST /travel/{id}/reject              — reject
  POST /travel/{id}/advance-paid        — mark cash advance as disbursed
  POST /travel/{id}/complete            — mark trip completed
  GET  /travel/{id}/per-diem-calc       — preview per diem calculation
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
router = APIRouter(prefix='/api/hr/expenses', tags=['Employee-Travel'])

# ── Constants ──────────────────────────────────────────────────────────────────
DESTINATION_TYPES = ['dalam_kota', 'luar_kota', 'luar_negeri']
DESTINATION_LABELS = {
    'dalam_kota': 'Dalam Kota',
    'luar_kota': 'Luar Kota',
    'luar_negeri': 'Luar Negeri',
}

STATUS_FLOW = [
    'draft', 'submitted', 'approved', 'advance_paid', 'on_trip', 'completed', 'rejected'
]

STATUS_LABELS = {
    'draft': 'Draft',
    'submitted': 'Diajukan',
    'approved': 'Disetujui',
    'advance_paid': 'Uang Muka Dibayar',
    'on_trip': 'Sedang Perjalanan',
    'completed': 'Selesai',
    'rejected': 'Ditolak',
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


def _serialize(doc: dict) -> dict:
    if not doc:
        return {}
    d = serialize_doc(doc)
    for key in ('created_at', 'updated_at', 'submitted_at', 'approved_at', 'advance_paid_at', 'completed_at'):
        if key in d:
            d[key] = _to_iso(d[key])
    return d


async def _get_or_404(db, req_id: str) -> dict:
    doc = await db.employee_travel_requests.find_one({'id': req_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, f'Travel request {req_id} tidak ditemukan')
    return doc


async def _generate_trip_number(db, requested: str = '') -> str:
    """Nomor perjalanan dinas — SATU PINTU kebijakan penomoran (Otomatis/Manual).

    SESI #27 (batch-3 Fase G): dulu selalu otomatis, jadi mode MANUAL milik owner
    tidak pernah berlaku pada dokumen yang justru paling sering diketik ulang dari
    arsip kertas (SPPD). Sekarang ditegakkan lewat `issue_number`.
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, 'employee_travel_requests.trip_number',
                              requested=requested)


async def _get_per_diem_rate(db, destination_type: str) -> dict:
    """Ambil per diem rate untuk tipe destinasi."""
    rate = await db.employee_per_diem_rates.find_one(
        {'destination_type': destination_type, 'is_active': True},
        {'_id': 0}
    )
    if not rate:
        # Default rates jika belum dikonfigurasi
        defaults = {
            'dalam_kota': {'daily_rate': 100_000, 'meal_allowance': 50_000, 'transport_allowance': 50_000},
            'luar_kota': {'daily_rate': 300_000, 'meal_allowance': 75_000, 'transport_allowance': 100_000},
            'luar_negeri': {'daily_rate': 500_000, 'meal_allowance': 150_000, 'transport_allowance': 200_000},
        }
        return defaults.get(destination_type, {'daily_rate': 100_000, 'meal_allowance': 50_000, 'transport_allowance': 50_000})
    return rate


def _calc_days(start_date: str, end_date: str) -> int:
    try:
        s = date.fromisoformat(start_date)
        e = date.fromisoformat(end_date)
        return max(1, (e - s).days + 1)
    except Exception:
        return 1


# ── Pydantic Models ────────────────────────────────────────────────────────────
class TravelCreate(BaseModel):
    destination: str
    destination_type: str = 'luar_kota'
    purpose: str
    start_date: str
    end_date: str
    transport_estimate: float = 0
    accommodation_estimate: float = 0
    other_estimate: float = 0
    cash_advance_requested: float = 0
    notes: Optional[str] = ''
    use_per_diem: bool = True
    # SESI #27 — nomor ketikan staf (HANYA dipakai bila kebijakan = MANUAL).
    trip_number: Optional[str] = ''


class TravelUpdate(BaseModel):
    destination: Optional[str] = None
    destination_type: Optional[str] = None
    purpose: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    transport_estimate: Optional[float] = None
    accommodation_estimate: Optional[float] = None
    other_estimate: Optional[float] = None
    cash_advance_requested: Optional[float] = None
    notes: Optional[str] = None
    use_per_diem: Optional[bool] = None


class ApprovePayload(BaseModel):
    cash_advance_approved: Optional[float] = None
    note: Optional[str] = ''


class RejectPayload(BaseModel):
    reason: str


class AdvancePaidPayload(BaseModel):
    amount_paid: float = Field(ge=0)
    payment_method: Optional[str] = 'transfer'
    note: Optional[str] = ''


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.post('/travel', status_code=201)
async def create_travel_request(body: TravelCreate, user: dict = Depends(require_auth)):
    """Buat travel request baru."""
    db = get_db()
    emp = await db.rahaza_employees.find_one(
        {'$or': [{'id': user.get('id')}, {'email': user.get('email')}]}, {'_id': 0}
    )
    if body.destination_type not in DESTINATION_TYPES:
        raise HTTPException(400, f"destination_type harus salah satu dari: {DESTINATION_TYPES}")

    days = _calc_days(body.start_date, body.end_date)
    rate = await _get_per_diem_rate(db, body.destination_type)
    per_diem_daily = float(rate.get('daily_rate', 0))
    per_diem_total = per_diem_daily * days if body.use_per_diem else 0
    total_budget = (
        per_diem_total +
        body.transport_estimate +
        body.accommodation_estimate +
        body.other_estimate
    )

    trip_number = await _generate_trip_number(db, (body.trip_number or '').strip())
    now = _now()
    doc = {
        'id': str(uuid.uuid4()),
        'trip_number': trip_number,
        'employee_id': user.get('id'),
        'employee_name': user.get('name') or (emp.get('name') if emp else ''),
        'employee_dept': emp.get('department') if emp else '',
        'employee_position': emp.get('position') if emp else '',
        'destination': body.destination,
        'destination_type': body.destination_type,
        'destination_label': DESTINATION_LABELS.get(body.destination_type, body.destination_type),
        'purpose': body.purpose,
        'start_date': body.start_date,
        'end_date': body.end_date,
        'days_count': days,
        'use_per_diem': body.use_per_diem,
        'per_diem_daily': per_diem_daily,
        'per_diem_total': per_diem_total,
        'transport_estimate': body.transport_estimate,
        'accommodation_estimate': body.accommodation_estimate,
        'other_estimate': body.other_estimate,
        'total_budget': total_budget,
        'cash_advance_requested': body.cash_advance_requested,
        'cash_advance_approved': 0,
        'cash_advance_paid': 0,
        'advance_paid_at': None,
        'advance_paid_by': '',
        'advance_paid_by_name': '',
        'payment_method': '',
        'notes': body.notes or '',
        'status': 'draft',
        'approval_note': '',
        'reject_reason': '',
        'submitted_at': None,
        'approved_at': None,
        'approved_by': '',
        'approved_by_name': '',
        'completed_at': None,
        'created_by': user.get('id'),
        'created_by_name': user.get('name'),
        'created_at': now,
        'updated_at': now,
    }
    await db.employee_travel_requests.insert_one(doc)
    await log_activity(user.get('id'), user.get('name'), 'create', 'travel_request',
                       f'Buat travel request {trip_number} ke {body.destination}')
    return _serialize(doc)


@router.get('/travel')
async def list_travel_requests(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0),
    user: dict = Depends(require_auth),
):
    """List travel requests."""
    db = get_db()
    role = (user.get('role') or '').lower()
    q: dict = {}

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
            {'trip_number': {'$regex': search, '$options': 'i'}},
            {'destination': {'$regex': search, '$options': 'i'}},
            {'purpose': {'$regex': search, '$options': 'i'}},
            {'employee_name': {'$regex': search, '$options': 'i'}},
        ]

    total_count = await db.employee_travel_requests.count_documents(q)
    docs = await db.employee_travel_requests.find(q, {'_id': 0}) \
        .sort('created_at', -1).skip(skip).limit(limit).to_list(length=limit)

    return {'total': total_count, 'items': [_serialize(d) for d in docs]}


# ── EEM Phase 4: Export ────────────────────────────────────────────────────────
# NOTE: Export route MUST be defined BEFORE parameterized routes to avoid matching conflict
@router.get('/travel/export')
async def export_travel_requests(
    status: Optional[str] = Query(None),
    employee_id: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    to_date: Optional[str] = Query(None, description='YYYY-MM-DD'),
    user: dict = Depends(require_auth),
):
    """Export travel requests ke CSV (with RBAC filter)."""
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

    # Date range filter (by departure_date)
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
            q['departure_date'] = date_q

    docs = await db.employee_travel_requests.find(q, {'_id': 0}).sort('departure_date', -1).to_list(1000)

    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Nomor Trip', 'Tanggal Berangkat', 'Tanggal Kembali', 'Karyawan', 'Departemen', 
        'Destinasi', 'Tipe', 'Tujuan', 'Hari', 'Uang Muka (Rp)', 'Status', 'Tgl Approved', 'Advance JE'
    ])

    for doc in docs:
        writer.writerow([
            doc.get('trip_number', ''),
            _to_iso(doc.get('departure_date'))[:10] if doc.get('departure_date') else '',
            _to_iso(doc.get('return_date'))[:10] if doc.get('return_date') else '',
            doc.get('employee_name', ''),
            doc.get('employee_dept', ''),
            doc.get('destination', ''),
            DESTINATION_LABELS.get(doc.get('destination_type', ''), doc.get('destination_type', '')),
            doc.get('purpose', ''),
            doc.get('days_count', 0),
            doc.get('cash_advance_amount', 0),
            STATUS_LABELS.get(doc.get('status', ''), doc.get('status', '')),
            _to_iso(doc.get('approved_at'))[:10] if doc.get('approved_at') else '',
            doc.get('advance_je_number', ''),
        ])

    output.seek(0)
    filename = f"travel_requests_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get('/travel/{req_id}')
async def get_travel_request(req_id: str, user: dict = Depends(require_auth)):
    """Detail travel request."""
    db = get_db()
    doc = await _get_or_404(db, req_id)
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance'):
        if doc.get('employee_id') != user.get('id'):
            raise HTTPException(403, 'Tidak punya akses ke request ini')
    return _serialize(doc)


@router.put('/travel/{req_id}')
async def update_travel_request(req_id: str, body: TravelUpdate, user: dict = Depends(require_auth)):
    """Update travel request (hanya draft)."""
    db = get_db()
    doc = await _get_or_404(db, req_id)
    if doc.get('employee_id') != user.get('id') and (user.get('role') or '').lower() not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik yang bisa edit')
    if doc.get('status') != 'draft':
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa diedit")

    upd: dict = {'updated_at': _now()}
    dest_type = body.destination_type or doc.get('destination_type', 'luar_kota')
    start = body.start_date or doc.get('start_date', '')
    end = body.end_date or doc.get('end_date', '')
    use_pd = body.use_per_diem if body.use_per_diem is not None else doc.get('use_per_diem', True)

    if body.destination is not None:
        upd['destination'] = body.destination
    if body.destination_type is not None:
        upd['destination_type'] = dest_type
        upd['destination_label'] = DESTINATION_LABELS.get(dest_type, dest_type)
    if body.purpose is not None:
        upd['purpose'] = body.purpose
    if body.start_date is not None:
        upd['start_date'] = start
    if body.end_date is not None:
        upd['end_date'] = end
    if body.notes is not None:
        upd['notes'] = body.notes
    if body.use_per_diem is not None:
        upd['use_per_diem'] = use_pd

    # Recalculate per diem & budget
    days = _calc_days(start, end)
    upd['days_count'] = days

    rate = await _get_per_diem_rate(db, dest_type)
    per_diem_daily = float(rate.get('daily_rate', 0))
    per_diem_total = per_diem_daily * days if use_pd else 0
    upd['per_diem_daily'] = per_diem_daily
    upd['per_diem_total'] = per_diem_total

    transport = body.transport_estimate if body.transport_estimate is not None else doc.get('transport_estimate', 0)
    accom = body.accommodation_estimate if body.accommodation_estimate is not None else doc.get('accommodation_estimate', 0)
    other = body.other_estimate if body.other_estimate is not None else doc.get('other_estimate', 0)
    if body.transport_estimate is not None:
        upd['transport_estimate'] = transport
    if body.accommodation_estimate is not None:
        upd['accommodation_estimate'] = accom
    if body.other_estimate is not None:
        upd['other_estimate'] = other
    if body.cash_advance_requested is not None:
        upd['cash_advance_requested'] = body.cash_advance_requested

    upd['total_budget'] = per_diem_total + float(transport) + float(accom) + float(other)

    await db.employee_travel_requests.update_one({'id': req_id}, {'$set': upd})
    updated = await _get_or_404(db, req_id)
    return _serialize(updated)


@router.post('/travel/{req_id}/submit')
async def submit_travel_request(req_id: str, user: dict = Depends(require_auth)):
    """Submit travel request untuk approval."""
    db = get_db()
    doc = await _get_or_404(db, req_id)
    if doc.get('employee_id') != user.get('id') and (user.get('role') or '').lower() not in ('superadmin', 'admin'):
        raise HTTPException(403, 'Hanya pemilik yang bisa submit')
    if doc.get('status') != 'draft':
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa di-submit. Harus draft.")
    if not doc.get('destination') or not doc.get('purpose'):
        raise HTTPException(400, 'Destinasi dan tujuan wajib diisi')

    now = _now()
    await db.employee_travel_requests.update_one(
        {'id': req_id},
        {'$set': {'status': 'submitted', 'submitted_at': now, 'updated_at': now}}
    )
    await log_activity(user.get('id'), user.get('name'), 'submit', 'travel_request',
                       f"Submit travel request {doc.get('trip_number')} ke {doc.get('destination')}")

    try:
        # RC-13: koleksi kanonik `notifications` via notif_unified
        # 2026-08-07: type wajib VALID_TYPES — dulu 'travel_request_submitted'
        # menyebabkan ValueError yang ditelan except ⇒ approver tak diberi tahu.
        from utils.notif_unified import notif_insert
        await notif_insert(
            db,
            type='rahaza',
            subtype='travel_request_submitted',
            severity='warning',
            title='Travel Request Baru Menunggu Persetujuan',
            body=f"{doc.get('employee_name')} mengajukan perjalanan dinas ke {doc.get('destination')} ({doc.get('start_date')} - {doc.get('end_date')})",
            source_type='travel_request',
            source_id=req_id,
            source_ref=doc.get('trip_number'),
            target_roles=list(APPROVER_ROLES),
            status='sent',
            meta={'link_module': 'hr-approval-inbox'},
        )
    except Exception:
        logging.getLogger(__name__).exception("notifikasi travel request gagal dikirim")

    return {'ok': True, 'id': req_id, 'new_status': 'submitted'}


@router.post('/travel/{req_id}/approve')
async def approve_travel_request(req_id: str, payload: ApprovePayload, user: dict = Depends(require_auth)):
    """Setujui travel request."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya Manager/HR yang dapat approve')

    doc = await _get_or_404(db, req_id)
    if doc.get('status') != 'submitted':
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa di-approve. Harus submitted.")

    now = _now()
    cash_adv_approved = payload.cash_advance_approved \
        if payload.cash_advance_approved is not None \
        else doc.get('cash_advance_requested', 0)

    await db.employee_travel_requests.update_one(
        {'id': req_id},
        {'$set': {
            'status': 'approved',
            'approved_by': user.get('id'),
            'approved_by_name': user.get('name'),
            'approved_at': now,
            'approval_note': payload.note or '',
            'cash_advance_approved': cash_adv_approved,
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'approve', 'travel_request',
                       f"Approve travel request {doc.get('trip_number')}")
    return {'ok': True, 'id': req_id, 'new_status': 'approved', 'cash_advance_approved': cash_adv_approved}


@router.post('/travel/{req_id}/reject')
async def reject_travel_request(req_id: str, payload: RejectPayload, user: dict = Depends(require_auth)):
    """Tolak travel request."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Hanya Manager/HR yang dapat reject')

    doc = await _get_or_404(db, req_id)
    if doc.get('status') not in ('submitted', 'approved'):
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa di-reject")

    now = _now()
    await db.employee_travel_requests.update_one(
        {'id': req_id},
        {'$set': {
            'status': 'rejected',
            'reject_reason': payload.reason,
            'rejected_by': user.get('id'),
            'rejected_by_name': user.get('name'),
            'rejected_at': now,
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'reject', 'travel_request',
                       f"Reject travel request {doc.get('trip_number')}: {payload.reason}")
    return {'ok': True, 'id': req_id, 'new_status': 'rejected'}


@router.post('/travel/{req_id}/advance-paid')
async def mark_advance_paid(req_id: str, payload: AdvancePaidPayload, user: dict = Depends(require_auth)):
    """Finance: tandai cash advance sudah dibayar + buat JE advance.
    
    Journal Entry:
      Dr  1-1610  Uang Muka Karyawan   (amount_paid)
          Cr  1-1201  Bank             (amount_paid)
    """
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'finance'):
        raise HTTPException(403, 'Hanya Finance yang dapat melakukan pembayaran uang muka')

    doc = await _get_or_404(db, req_id)
    if doc.get('status') != 'approved':
        raise HTTPException(400, f"Status '{doc.get('status')}' harus 'approved' untuk bayar uang muka")

    amount = float(payload.amount_paid or 0)
    if amount <= 0:
        raise HTTPException(400, 'Jumlah uang muka harus lebih dari 0')

    now = _now()
    je_date = date.today()

    # RC-05: posting WAJIB lewat engine rahaza_posting (validasi COA/saldo/periode).
    from routes.rahaza_posting import _create_posted_je
    credit_code = '1-1201'  # Bank BCA default

    memo = f"Uang Muka Perjalanan Dinas {doc.get('trip_number')} — {doc.get('employee_name', '')}"
    lines = [
        {
            'account_code': '1-1610',   # Dr: Uang Muka Karyawan (asset naik)
            'debit': amount, 'credit': 0,
            'description': memo, 'cost_center_id': '',
        },
        {
            'account_code': credit_code,  # Cr: Bank (kas turun)
            'debit': 0, 'credit': amount,
            'description': memo, 'cost_center_id': '',
        },
    ]
    je_res = await _create_posted_je(
        db, je_date, memo,
        source_module='travel_advance',
        source_ref=doc.get('trip_number') or req_id,
        lines_raw=lines, user=user,
    )
    if not je_res.get('ok'):
        raise HTTPException(400, f"Posting GL gagal: {je_res.get('error')}")
    je_id = je_res['je_id']
    je_number = je_res['je_number']

    await db.employee_travel_requests.update_one(
        {'id': req_id},
        {'$set': {
            'status': 'advance_paid',
            'cash_advance_paid': amount,
            'advance_paid_at': now,
            'advance_paid_by': user.get('id'),
            'advance_paid_by_name': user.get('name'),
            'payment_method': payload.payment_method or 'transfer',
            'advance_je_id': je_id,
            'advance_je_number': je_number,
            'updated_at': now,
        }}
    )
    await log_activity(user.get('id'), user.get('name'), 'advance_paid', 'travel_request',
                       f"Bayar uang muka {doc.get('trip_number')} Rp {amount:,.0f} → JE {je_number}")
    return {
        'ok': True, 'id': req_id, 'new_status': 'advance_paid',
        'amount_paid': amount, 'je_id': je_id, 'je_number': je_number,
    }


@router.post('/travel/{req_id}/complete')
async def complete_travel_request(req_id: str, user: dict = Depends(require_auth)):
    """Tandai perjalanan dinas selesai."""
    db = get_db()
    doc = await _get_or_404(db, req_id)
    if doc.get('employee_id') != user.get('id') and (user.get('role') or '').lower() not in APPROVER_ROLES:
        raise HTTPException(403, 'Tidak punya akses')
    if doc.get('status') not in ('approved', 'advance_paid', 'on_trip'):
        raise HTTPException(400, f"Status '{doc.get('status')}' tidak bisa diselesaikan")

    now = _now()
    await db.employee_travel_requests.update_one(
        {'id': req_id},
        {'$set': {'status': 'completed', 'completed_at': now, 'updated_at': now}}
    )
    await log_activity(user.get('id'), user.get('name'), 'complete', 'travel_request',
                       f"Selesai travel request {doc.get('trip_number')}")
    return {'ok': True, 'id': req_id, 'new_status': 'completed'}


@router.get('/travel/{req_id}/per-diem-calc')
async def calc_per_diem(req_id: str, user: dict = Depends(require_auth)):
    """Preview kalkulasi per diem untuk travel request."""
    db = get_db()
    doc = await _get_or_404(db, req_id)
    dest_type = doc.get('destination_type', 'luar_kota')
    days = doc.get('days_count', 1)
    rate = await _get_per_diem_rate(db, dest_type)
    per_diem_daily = float(rate.get('daily_rate', 0))
    meal = float(rate.get('meal_allowance', 0))
    transport = float(rate.get('transport_allowance', 0))
    return {
        'destination_type': dest_type,
        'destination_label': DESTINATION_LABELS.get(dest_type, dest_type),
        'days_count': days,
        'per_diem_daily': per_diem_daily,
        'meal_allowance_daily': meal,
        'transport_allowance_daily': transport,
        'per_diem_total': per_diem_daily * days,
        'total_allowance': (per_diem_daily + meal + transport) * days,
        'rate_source': 'configured' if await db.employee_per_diem_rates.find_one({'destination_type': dest_type}) else 'default',
    }



# ── EEM Phase 4: Bulk Actions ──────────────────────────────────────────────────
class BulkApproveTravelRequest(BaseModel):
    travel_ids: List[str] = Field(..., description='List of travel request IDs to approve')
    approval_note: Optional[str] = ''


@router.post('/travel/bulk-approve')
async def bulk_approve_travel(body: BulkApproveTravelRequest, user: dict = Depends(require_auth)):
    """Bulk approve multiple travel requests (Finance/HR/Manager only)."""
    role = (user.get('role') or '').lower()
    if role not in APPROVER_ROLES:
        raise HTTPException(403, 'Tidak punya hak approve')

    db = get_db()
    results = {'success': [], 'failed': []}

    for travel_id in body.travel_ids:
        try:
            doc = await db.employee_travel_requests.find_one({'id': travel_id}, {'_id': 0})
            if not doc:
                results['failed'].append({'id': travel_id, 'reason': 'Tidak ditemukan'})
                continue

            if doc.get('status') != 'submitted':
                results['failed'].append({'id': travel_id, 'reason': f'Status {doc.get("status")} tidak bisa di-approve'})
                continue

            # Approve
            now = _now()
            await db.employee_travel_requests.update_one(
                {'id': travel_id},
                {'$set': {
                    'status': 'approved',
                    'approved_at': now,
                    'approved_by': user.get('id'),
                    'approved_by_name': user.get('name'),
                    'approval_note': body.approval_note or '',
                    'updated_at': now,
                }}
            )
            await log_activity(user.get('id'), user.get('name'), 'approve', 'travel_request',
                             f'Bulk approve travel {doc.get("trip_number")}')
            results['success'].append(travel_id)

        except Exception as e:
            logger.error(f'Bulk approve travel {travel_id} error: {e}')
            results['failed'].append({'id': travel_id, 'reason': str(e)})

    return {
        'ok': True,
        'total': len(body.travel_ids),
        'success_count': len(results['success']),
        'failed_count': len(results['failed']),
        'results': results,
    }

