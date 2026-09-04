"""
CV. Dewi Aditya — HR Approval Inbox (Aggregator)
Phase 26 — P2 Workflow Consolidation #2

Unified inbox for managers/HR to approve multiple types of HR requests in one place:
- Cuti (Leave) — rahaza_leave_requests (status=pending_approval)
- Lembur (Overtime) — rahaza_overtime_requests (status=pending)
- Penyesuaian Gaji (Salary Adjustment) — rahaza_salary_adjustments (status in
  draft/pending_manager/pending_hr)
- Resignasi — rahaza_employees (resignation flow with status=submitted)

Endpoints:
- GET  /api/hr/inbox                        — aggregate all pending approvals
- GET  /api/hr/inbox/summary                — count summary per category
- POST /api/hr/inbox/{type}/{id}/approve    — generic approve
- POST /api/hr/inbox/{type}/{id}/reject     — generic reject

Implementation note: this is an AGGREGATOR. Approve/reject endpoints delegate
to existing per-module endpoints to keep business logic centralized.
"""
# ruff: noqa: E741
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc, log_activity
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/hr/inbox', tags=['HR-Inbox'])


# ─────────────────────────────────────────────────────────────────────────────
# Allowed request types & validation
# ─────────────────────────────────────────────────────────────────────────────
ALLOWED_TYPES = ('leave', 'overtime', 'salary_adjustment', 'resignation', 'attendance', 'expense_claim', 'travel_request')


def _to_iso(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        return dt
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    return str(dt)


async def _enrich_employee(db, emp_id: str) -> Dict[str, Any]:
    """Fetch employee snapshot (name, code, dept)."""
    if not emp_id:
        return {}
    emp = await db.rahaza_employees.find_one({'id': emp_id}, {'_id': 0})
    if not emp:
        return {}
    return {
        'employee_id': emp.get('id'),
        'employee_code': emp.get('employee_code'),
        'employee_name': emp.get('name'),
        'employee_dept': emp.get('department'),
        'employee_position': emp.get('position'),
        'manager_id': emp.get('manager_id'),
    }


def _require_approver_role(user: dict):
    # 2026-08-06 — gerbang izin terpusat (routes.shared.can_act, fallback aman).
    from routes.shared import can_act as _can_act
    if not _can_act(user, 'hr.approve', 'hr.manage',
                    legacy_roles=('hr', 'manager', 'hr_manager')):
        raise HTTPException(403, 'Akses ditolak: butuh izin approval SDM (hr.approve).')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — build inbox items from raw docs
# ─────────────────────────────────────────────────────────────────────────────
async def _fetch_leaves(db, type_filter: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Pending leave requests."""
    if type_filter and type_filter != 'leave':
        return []
    rows = await db.rahaza_leave_requests.find(
        {'status': 'pending_approval'}, {'_id': 0}
    ).sort('created_at', -1).limit(limit).to_list(length=limit)

    if not rows:
        return []

    emp_ids = list({r.get('employee_id') for r in rows if r.get('employee_id')})
    lt_ids  = list({r.get('leave_type_id') for r in rows if r.get('leave_type_id')})
    emps = await db.rahaza_employees.find({'id': {'$in': emp_ids}}, {'_id': 0}).to_list(length=500) if emp_ids else []
    lts  = await db.rahaza_leave_types.find({'id': {'$in': lt_ids}}, {'_id': 0}).to_list(length=500) if lt_ids else []
    emp_map = {e['id']: e for e in emps}
    lt_map  = {l['id']: l for l in lts}

    items = []
    for r in rows:
        e = emp_map.get(r.get('employee_id')) or {}
        lt = lt_map.get(r.get('leave_type_id')) or {}
        # Leave duration field varies — newer docs use duration_days / duration_working_days
        total_days = (
            r.get('duration_working_days')
            or r.get('duration_days')
            or r.get('total_days')
            or 0
        )
        items.append({
            'id': r['id'],
            'type': 'leave',
            'type_label': 'Cuti / Izin',
            'created_at': _to_iso(r.get('created_at')),
            'submitted_at': _to_iso(r.get('submitted_at') or r.get('created_at')),
            'requester_id': r.get('employee_id'),
            'requester_name': e.get('name'),
            'requester_code': e.get('employee_code'),
            'requester_dept': e.get('department'),
            'title': f"{lt.get('name', 'Cuti')} — {total_days} hari",
            'period': f"{r.get('from_date', '')} → {r.get('to_date', '')}",
            'reason': r.get('reason', ''),
            'amount': None,
            'meta': {
                'leave_type': lt.get('name'),
                'leave_type_code': lt.get('code'),
                'total_days': total_days,
                'is_paid': lt.get('paid', False),
                'request_type': lt.get('request_type') or r.get('request_type'),
                'from_date': r.get('from_date'),
                'to_date': r.get('to_date'),
                'half_day': r.get('half_day') or r.get('is_half_day'),
                'attachment_url': r.get('attachment_url'),
            },
            'raw': serialize_doc(r),
        })
    return items


async def _fetch_overtime(db, type_filter: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Pending overtime requests."""
    if type_filter and type_filter != 'overtime':
        return []
    rows = await db.rahaza_overtime_requests.find(
        {'status': 'pending'}, {'_id': 0}
    ).sort('created_at', -1).limit(limit).to_list(length=limit)
    if not rows:
        return []
    emp_ids = list({r.get('employee_id') for r in rows if r.get('employee_id')})
    emps = await db.rahaza_employees.find({'id': {'$in': emp_ids}}, {'_id': 0}).to_list(length=500) if emp_ids else []
    emp_map = {e['id']: e for e in emps}
    items = []
    for r in rows:
        e = emp_map.get(r.get('employee_id')) or {}
        items.append({
            'id': r['id'],
            'type': 'overtime',
            'type_label': 'Lembur',
            'created_at': _to_iso(r.get('created_at')),
            'submitted_at': _to_iso(r.get('created_at')),
            'requester_id': r.get('employee_id'),
            'requester_name': e.get('name'),
            'requester_code': e.get('employee_code'),
            'requester_dept': e.get('department'),
            'title': f"Lembur {r.get('hours', 0)} jam — {r.get('date', '')}",
            'period': f"{r.get('start_time', '')} - {r.get('end_time', '')}",
            'reason': r.get('reason', ''),
            'amount': None,
            'meta': {
                'date': r.get('date'),
                'start_time': r.get('start_time'),
                'end_time': r.get('end_time'),
                'hours': r.get('hours'),
                'rate_multiplier': r.get('rate_multiplier', 1.5),
            },
            'raw': serialize_doc(r),
        })
    return items


async def _fetch_salary_adjustments(db, type_filter: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Salary adjustments pending manager/HR approval."""
    if type_filter and type_filter != 'salary_adjustment':
        return []
    rows = await db.rahaza_salary_adjustments.find(
        {'status': {'$in': ['draft', 'pending_manager', 'pending_hr']}},
        {'_id': 0}
    ).sort('created_at', -1).limit(limit).to_list(length=limit)
    if not rows:
        return []
    emp_ids = list({r.get('employee_id') for r in rows if r.get('employee_id')})
    emps = await db.rahaza_employees.find({'id': {'$in': emp_ids}}, {'_id': 0}).to_list(length=500) if emp_ids else []
    emp_map = {e['id']: e for e in emps}
    items = []
    for r in rows:
        e = emp_map.get(r.get('employee_id')) or {}
        old_v = float(r.get('old_value', 0) or 0)
        new_v = float(r.get('new_value', 0) or 0)
        delta = new_v - old_v
        items.append({
            'id': r['id'],
            'type': 'salary_adjustment',
            'type_label': 'Penyesuaian Gaji',
            'created_at': _to_iso(r.get('created_at')),
            'submitted_at': _to_iso(r.get('submitted_at') or r.get('created_at')),
            'requester_id': r.get('employee_id'),
            'requester_name': e.get('name'),
            'requester_code': e.get('employee_code'),
            'requester_dept': e.get('department'),
            'title': f"{r.get('adjustment_type', 'Penyesuaian')} — Rp {int(delta):+,}",
            'period': r.get('effective_date', ''),
            'reason': r.get('reason', ''),
            'amount': delta,
            'meta': {
                'adjustment_type': r.get('adjustment_type'),
                'old_value': old_v,
                'new_value': new_v,
                'delta': delta,
                'effective_date': r.get('effective_date'),
                'sub_status': r.get('status'),
            },
            'raw': serialize_doc(r),
        })
    return items


async def _fetch_resignations(db, type_filter: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Resignations awaiting acceptance."""
    if type_filter and type_filter != 'resignation':
        return []
    rows = await db.rahaza_employees.find(
        {'resignation_status': 'submitted'}, {'_id': 0}
    ).sort('resignation_submitted_at', -1).limit(limit).to_list(length=limit)
    items = []
    for r in rows:
        items.append({
            'id': r['id'],
            'type': 'resignation',
            'type_label': 'Resignasi',
            'created_at': _to_iso(r.get('resignation_submitted_at') or r.get('updated_at')),
            'submitted_at': _to_iso(r.get('resignation_submitted_at')),
            'requester_id': r.get('id'),
            'requester_name': r.get('name'),
            'requester_code': r.get('employee_code'),
            'requester_dept': r.get('department'),
            'title': f"Resignasi efektif {r.get('resignation_effective_date', '—')}",
            'period': r.get('resignation_effective_date', ''),
            'reason': r.get('resignation_reason', ''),
            'amount': None,
            'meta': {
                'resignation_reason': r.get('resignation_reason'),
                'resignation_effective_date': r.get('resignation_effective_date'),
                'last_working_date': r.get('resignation_effective_date'),
                'position': r.get('position'),
            },
            'raw': serialize_doc(r),
        })
    return items


async def _fetch_attendance(db, type_filter: Optional[str], limit: int) -> List[Dict[str, Any]]:
    """Pending attendance approvals (rahaza_attendance_events with approval_status='pending').

    Source: rahaza_auto_attendance module's queue. Items here typically come from
    auto-attendance flow (face-recognition / geo-check failed / outside-window absen).
    """
    if type_filter and type_filter != 'attendance':
        return []
    rows = await db.rahaza_attendance_events.find(
        {'approval_status': 'pending'}, {'_id': 0}
    ).sort('date', -1).limit(limit).to_list(length=limit)

    if not rows:
        return []

    emp_ids = list({r.get('employee_id') for r in rows if r.get('employee_id')})
    emps = await db.rahaza_employees.find(
        {'id': {'$in': emp_ids}}, {'_id': 0}
    ).to_list(length=500) if emp_ids else []
    emp_map = {e['id']: e for e in emps}

    items = []
    for r in rows:
        e = emp_map.get(r.get('employee_id')) or {}
        date_str = r.get('date', '')
        check_in = r.get('check_in_time') or r.get('clock_in_time') or '—'
        check_out = r.get('check_out_time') or r.get('clock_out_time') or '—'
        items.append({
            'id': r['id'],
            'type': 'attendance',
            'type_label': 'Approval Absensi',
            'created_at': _to_iso(r.get('created_at')),
            'submitted_at': _to_iso(r.get('updated_at') or r.get('created_at')),
            'requester_id': r.get('employee_id'),
            'requester_name': e.get('name'),
            'requester_code': e.get('employee_code'),
            'requester_dept': e.get('department'),
            'title': f"Absen {date_str} — {check_in} → {check_out}",
            'period': date_str,
            'reason': r.get('note', '') or r.get('reason', ''),
            'amount': None,
            'meta': {
                'date': date_str,
                'check_in_time': check_in,
                'check_out_time': check_out,
                'work_hours': r.get('work_hours') or r.get('total_hours'),
                'location': r.get('clock_in_location') or r.get('location'),
                'face_match': r.get('face_match_score'),
                'geo_distance_m': r.get('geo_distance_m'),
                'note': r.get('note') or r.get('reason'),
                'attendance_type': r.get('attendance_type') or r.get('type'),
                'photo_url': r.get('clock_in_photo_url') or r.get('photo_url'),
            },
            'raw': serialize_doc(r),
        })
    return items


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get('')
async def list_inbox(
    type_filter: Optional[str] = Query(None, alias='type', description='Filter: leave|overtime|salary_adjustment|resignation|attendance'),
    limit_per_type: int = Query(50, le=200),
    user: dict = Depends(require_auth),
):
    """
    Aggregated inbox of pending HR approvals.

    Returns items from 5 sources combined and sorted desc by submission/creation time.
    Use `?type=leave` etc. to filter to one category.
    """
    _require_approver_role(user)
    if type_filter and type_filter not in ALLOWED_TYPES:
        raise HTTPException(400, f'Type harus salah satu: {list(ALLOWED_TYPES)}')

    db = get_db()
    leaves      = await _fetch_leaves(db, type_filter, limit_per_type)
    overtime    = await _fetch_overtime(db, type_filter, limit_per_type)
    salary_adj  = await _fetch_salary_adjustments(db, type_filter, limit_per_type)
    resignation = await _fetch_resignations(db, type_filter, limit_per_type)
    attendance  = await _fetch_attendance(db, type_filter, limit_per_type)

    all_items = leaves + overtime + salary_adj + resignation + attendance
    # Sort by submitted_at desc, fallback created_at
    all_items.sort(key=lambda x: (x.get('submitted_at') or x.get('created_at') or ''), reverse=True)

    return {
        'total': len(all_items),
        'counts': {
            'leave': len(leaves),
            'overtime': len(overtime),
            'salary_adjustment': len(salary_adj),
            'resignation': len(resignation),
            'attendance': len(attendance),
        },
        'items': all_items,
    }


@router.get('/summary')
async def inbox_summary(user: dict = Depends(require_auth)):
    """Count of pending approvals per category (for badge/notification)."""
    _require_approver_role(user)
    db = get_db()
    leaves_c = await db.rahaza_leave_requests.count_documents({'status': 'pending_approval'})
    overtime_c = await db.rahaza_overtime_requests.count_documents({'status': 'pending'})
    sal_c = await db.rahaza_salary_adjustments.count_documents(
        {'status': {'$in': ['draft', 'pending_manager', 'pending_hr']}}
    )
    resig_c = await db.rahaza_employees.count_documents({'resignation_status': 'submitted'})
    att_c = await db.rahaza_attendance_events.count_documents({'approval_status': 'pending'})
    total = leaves_c + overtime_c + sal_c + resig_c + att_c
    return {
        'total_pending': total,
        'leave': leaves_c,
        'overtime': overtime_c,
        'salary_adjustment': sal_c,
        'resignation': resig_c,
        'attendance': att_c,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Approve / Reject — delegates to per-domain endpoints internally
# ─────────────────────────────────────────────────────────────────────────────
class ActionPayload(BaseModel):
    note: Optional[str] = None
    reason: Optional[str] = None


@router.post('/{req_type}/{req_id}/approve')
async def approve_request(req_type: str, req_id: str, payload: Optional[ActionPayload] = None,
                          user: dict = Depends(require_auth)):
    """Approve a pending HR request (leave/overtime/salary_adjustment/resignation)."""
    _require_approver_role(user)
    if req_type not in ALLOWED_TYPES:
        raise HTTPException(400, f'Type harus salah satu: {list(ALLOWED_TYPES)}')

    db = get_db()
    now = datetime.now(timezone.utc)
    note = (payload.note if payload else None) or ''
    actor_id = user.get('id', '')
    actor_name = user.get('name', '')

    if req_type == 'leave':
        leave = await db.rahaza_leave_requests.find_one({'id': req_id})
        if not leave:
            raise HTTPException(404, 'Leave request tidak ditemukan')
        if leave.get('status') != 'pending_approval':
            raise HTTPException(400, f"Leave status saat ini: {leave.get('status')}. Harus pending_approval.")
        await db.rahaza_leave_requests.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'approved',
                'approved_by': actor_id,
                'approved_by_name': actor_name,
                'approved_at': now,
                'approval_note': note,
            }}
        )
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Approve cuti {req_id} via HR Inbox')
        return {'ok': True, 'type': 'leave', 'id': req_id, 'new_status': 'approved'}

    if req_type == 'overtime':
        ot = await db.rahaza_overtime_requests.find_one({'id': req_id})
        if not ot:
            raise HTTPException(404, 'Overtime request tidak ditemukan')
        if ot.get('status') != 'pending':
            raise HTTPException(400, f"OT status saat ini: {ot.get('status')}. Harus pending.")
        await db.rahaza_overtime_requests.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'approved',
                'approved_by': actor_id,
                'approved_by_name': actor_name,
                'approved_at': now,
                'approval_note': note,
            }}
        )
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Approve lembur {req_id} via HR Inbox')
        return {'ok': True, 'type': 'overtime', 'id': req_id, 'new_status': 'approved'}

    if req_type == 'salary_adjustment':
        adj = await db.rahaza_salary_adjustments.find_one({'id': req_id})
        if not adj:
            raise HTTPException(404, 'Salary adjustment tidak ditemukan')
        cur_status = adj.get('status')
        role = (user.get('role') or '').lower()
        # Manager → moves to pending_hr; HR/admin → moves to approved
        if cur_status in ('draft', 'pending_manager'):
            new_status = 'pending_hr' if role in ('manager',) else 'approved'
            upd = {'status': new_status, 'manager_approved_by': actor_id, 'manager_approved_at': now}
            if new_status == 'approved':
                upd['hr_approved_by'] = actor_id
                upd['hr_approved_at'] = now
        elif cur_status == 'pending_hr':
            new_status = 'approved'
            upd = {'status': new_status, 'hr_approved_by': actor_id, 'hr_approved_at': now}
        else:
            raise HTTPException(400, f'Status sudah {cur_status}, tidak bisa di-approve.')
        if note:
            upd['approval_note'] = note
        await db.rahaza_salary_adjustments.update_one({'id': req_id}, {'$set': upd})
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Approve penyesuaian gaji {req_id} → {new_status} via HR Inbox')
        return {'ok': True, 'type': 'salary_adjustment', 'id': req_id, 'new_status': new_status}

    if req_type == 'resignation':
        emp = await db.rahaza_employees.find_one({'id': req_id})
        if not emp:
            raise HTTPException(404, 'Employee tidak ditemukan')
        if emp.get('resignation_status') != 'submitted':
            raise HTTPException(400, f"Resignation status saat ini: {emp.get('resignation_status')}")
        await db.rahaza_employees.update_one(
            {'id': req_id},
            {'$set': {
                'resignation_status': 'accepted',
                'resignation_accepted_by': actor_id,
                'resignation_accepted_at': now,
                'resignation_acceptance_note': note,
            }}
        )
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Accept resignasi karyawan {req_id} via HR Inbox')
        return {'ok': True, 'type': 'resignation', 'id': req_id, 'new_status': 'accepted'}

    if req_type == 'attendance':
        ev = await db.rahaza_attendance_events.find_one({'id': req_id})
        if not ev:
            raise HTTPException(404, 'Record absen tidak ditemukan')
        if ev.get('approval_status') != 'pending':
            raise HTTPException(400, f"Status absen saat ini: {ev.get('approval_status')}. Harus pending.")
        await db.rahaza_attendance_events.update_one(
            {'id': req_id},
            {'$set': {
                'approval_status': 'approved',
                'approval_by': actor_id,
                'approval_by_name': actor_name,
                'approval_notes': note,
                'approval_at': now,
                'status': 'hadir',
                'updated_by': actor_id,
                'updated_by_name': actor_name,
                'updated_at': now,
            }}
        )
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Approve absen {req_id} via HR Inbox')
        return {'ok': True, 'type': 'attendance', 'id': req_id, 'new_status': 'approved'}

    if req_type == 'expense_claim':
        claim = await db.rahaza_expense_claims.find_one({'id': req_id})
        if not claim:
            raise HTTPException(404, 'Klaim biaya tidak ditemukan')
        if claim.get('status') != 'submitted':
            raise HTTPException(400, f"Status klaim saat ini: {claim.get('status')}. Harus submitted.")
        await db.rahaza_expense_claims.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'approved',
                'approved_by': actor_id,
                'approved_by_name': actor_name,
                'approved_at': now,
                'approval_note': note,
                'updated_at': now,
            }}
        )
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Approve klaim biaya {req_id} via HR Inbox')
        return {'ok': True, 'type': 'expense_claim', 'id': req_id, 'new_status': 'approved'}

    if req_type == 'travel_request':
        tr = await db.employee_travel_requests.find_one({'id': req_id})
        if not tr:
            raise HTTPException(404, 'Travel request tidak ditemukan')
        if tr.get('status') != 'submitted':
            raise HTTPException(400, f"Status travel request saat ini: {tr.get('status')}. Harus submitted.")
        await db.employee_travel_requests.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'approved',
                'approved_by': actor_id,
                'approved_by_name': actor_name,
                'approved_at': now,
                'approval_note': note,
                'cash_advance_approved': tr.get('cash_advance_requested', 0),
                'updated_at': now,
            }}
        )
        await log_activity(actor_id, actor_name, 'approve', 'hr_inbox',
                           f'Approve travel request {req_id} via HR Inbox')
        return {'ok': True, 'type': 'travel_request', 'id': req_id, 'new_status': 'approved'}

    raise HTTPException(400, 'Unhandled type')


@router.post('/{req_type}/{req_id}/reject')
async def reject_request(req_type: str, req_id: str, payload: ActionPayload,
                         user: dict = Depends(require_auth)):
    """Reject a pending HR request with required reason."""
    _require_approver_role(user)
    if req_type not in ALLOWED_TYPES:
        raise HTTPException(400, f'Type harus salah satu: {list(ALLOWED_TYPES)}')
    if not payload.reason and not payload.note:
        raise HTTPException(400, 'Alasan reject wajib diisi.')

    db = get_db()
    now = datetime.now(timezone.utc)
    reason = payload.reason or payload.note or ''
    actor_id = user.get('id', '')
    actor_name = user.get('name', '')

    if req_type == 'leave':
        leave = await db.rahaza_leave_requests.find_one({'id': req_id})
        if not leave:
            raise HTTPException(404, 'Leave request tidak ditemukan')
        await db.rahaza_leave_requests.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'rejected',
                'rejected_by': actor_id,
                'rejected_by_name': actor_name,
                'rejected_at': now,
                'reject_reason': reason,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject cuti {req_id}: {reason}')
        return {'ok': True, 'type': 'leave', 'id': req_id, 'new_status': 'rejected'}

    if req_type == 'overtime':
        ot = await db.rahaza_overtime_requests.find_one({'id': req_id})
        if not ot:
            raise HTTPException(404, 'Overtime request tidak ditemukan')
        await db.rahaza_overtime_requests.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'rejected',
                'rejected_by': actor_id,
                'rejected_at': now,
                'rejected_reason': reason,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject lembur {req_id}: {reason}')
        return {'ok': True, 'type': 'overtime', 'id': req_id, 'new_status': 'rejected'}

    if req_type == 'salary_adjustment':
        adj = await db.rahaza_salary_adjustments.find_one({'id': req_id})
        if not adj:
            raise HTTPException(404, 'Salary adjustment tidak ditemukan')
        await db.rahaza_salary_adjustments.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'rejected',
                'rejected_by': actor_id,
                'rejected_at': now,
                'reject_reason': reason,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject penyesuaian gaji {req_id}: {reason}')
        return {'ok': True, 'type': 'salary_adjustment', 'id': req_id, 'new_status': 'rejected'}

    if req_type == 'resignation':
        # Soft-reject = withdraw resignation submission
        emp = await db.rahaza_employees.find_one({'id': req_id})
        if not emp:
            raise HTTPException(404, 'Employee tidak ditemukan')
        await db.rahaza_employees.update_one(
            {'id': req_id},
            {'$set': {
                'resignation_status': 'rejected',
                'resignation_rejected_by': actor_id,
                'resignation_rejected_at': now,
                'resignation_reject_reason': reason,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject resignasi karyawan {req_id}: {reason}')
        return {'ok': True, 'type': 'resignation', 'id': req_id, 'new_status': 'rejected'}

    if req_type == 'attendance':
        ev = await db.rahaza_attendance_events.find_one({'id': req_id})
        if not ev:
            raise HTTPException(404, 'Record absen tidak ditemukan')
        await db.rahaza_attendance_events.update_one(
            {'id': req_id},
            {'$set': {
                'approval_status': 'rejected',
                'approval_by': actor_id,
                'approval_by_name': actor_name,
                'approval_notes': reason,
                'approval_at': now,
                'status': 'alfa',
                'updated_by': actor_id,
                'updated_by_name': actor_name,
                'updated_at': now,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject absen {req_id}: {reason}')
        return {'ok': True, 'type': 'attendance', 'id': req_id, 'new_status': 'rejected'}

    if req_type == 'expense_claim':
        claim = await db.rahaza_expense_claims.find_one({'id': req_id})
        if not claim:
            raise HTTPException(404, 'Klaim biaya tidak ditemukan')
        await db.rahaza_expense_claims.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'rejected',
                'reject_reason': reason,
                'rejected_by': actor_id,
                'rejected_by_name': actor_name,
                'rejected_at': now,
                'updated_at': now,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject klaim biaya {req_id}: {reason}')
        return {'ok': True, 'type': 'expense_claim', 'id': req_id, 'new_status': 'rejected'}

    if req_type == 'travel_request':
        tr = await db.employee_travel_requests.find_one({'id': req_id})
        if not tr:
            raise HTTPException(404, 'Travel request tidak ditemukan')
        await db.employee_travel_requests.update_one(
            {'id': req_id},
            {'$set': {
                'status': 'rejected',
                'reject_reason': reason,
                'rejected_by': actor_id,
                'rejected_by_name': actor_name,
                'rejected_at': now,
                'updated_at': now,
            }}
        )
        await log_activity(actor_id, actor_name, 'reject', 'hr_inbox',
                           f'Reject travel request {req_id}: {reason}')
        return {'ok': True, 'type': 'travel_request', 'id': req_id, 'new_status': 'rejected'}

    raise HTTPException(400, 'Unhandled type')
