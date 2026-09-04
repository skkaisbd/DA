"""
Employee Expense Summary & Dashboard Endpoints
CV. Dewi Aditya — Employee Expense Management (EEM)

Prefix: /api/hr/expenses

Endpoints:
  GET /summary            — aggregate stats (counts, amounts by status)
  GET /pending-approval   — aggregated pending items for current approver
  GET /my-summary         — summary for logged-in employee
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone
from database import get_db
from auth import require_auth
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/hr/expenses', tags=['Employee-Expense-Summary'])


def _now():
    return datetime.now(timezone.utc)


@router.get('/summary')
async def expense_summary(user: dict = Depends(require_auth)):
    """Aggregate summary stats — klaim dan travel requests."""
    db = get_db()
    role = (user.get('role') or '').lower()
    is_approver = role in ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance')

    # Filters: manager/HR sees all, employee sees own
    base_q = {} if is_approver else {'employee_id': user.get('id')}

    # Expense Claims stats
    claim_statuses = ['draft', 'submitted', 'approved', 'rejected', 'paid', 'posted']
    claim_stats = {}
    for s in claim_statuses:
        q = {**base_q, 'status': s}
        claim_stats[s] = await db.rahaza_expense_claims.count_documents(q)

    # Totals
    pipeline = [
        {'$match': {**base_q, 'status': {'$in': ['submitted', 'approved', 'paid', 'posted']}}},
        {'$group': {'_id': None, 'total': {'$sum': '$total_amount'}}}
    ]
    total_claims_amount = 0
    async for doc in db.rahaza_expense_claims.aggregate(pipeline):
        total_claims_amount = doc.get('total', 0)

    # Travel stats
    travel_statuses = ['draft', 'submitted', 'approved', 'advance_paid', 'on_trip', 'completed', 'rejected']
    travel_stats = {}
    for s in travel_statuses:
        q = {**base_q, 'status': s}
        travel_stats[s] = await db.employee_travel_requests.count_documents(q)

    travel_budget_pipeline = [
        {'$match': {**base_q, 'status': {'$in': ['submitted', 'approved', 'advance_paid', 'on_trip', 'completed']}}},
        {'$group': {'_id': None, 'total': {'$sum': '$total_budget'}}}
    ]
    total_travel_budget = 0
    async for doc in db.employee_travel_requests.aggregate(travel_budget_pipeline):
        total_travel_budget = doc.get('total', 0)

    # Pending counts for approver badge
    pending_claims = await db.rahaza_expense_claims.count_documents({'status': 'submitted'})
    pending_travel = await db.employee_travel_requests.count_documents({'status': 'submitted'})
    pending_advance = await db.employee_travel_requests.count_documents({'status': 'approved'})  # waiting advance

    return {
        'expense_claims': {
            'counts': claim_stats,
            'total_amount': total_claims_amount,
            'pending_approval': claim_stats.get('submitted', 0),
            'total_pending_approval': pending_claims,
        },
        'travel_requests': {
            'counts': travel_stats,
            'total_budget': total_travel_budget,
            'pending_approval': travel_stats.get('submitted', 0),
            'pending_advance': travel_stats.get('approved', 0),
            'total_pending_approval': pending_travel,
        },
        'total_pending': pending_claims + pending_travel + pending_advance,
        'is_approver': is_approver,
    }


@router.get('/pending-approval')
async def pending_approval_list(
    limit: int = Query(50, ge=1, le=200),
    user: dict = Depends(require_auth),
):
    """Aggregated pending items for current approver — claims + travel."""
    db = get_db()
    role = (user.get('role') or '').lower()
    if role not in ('superadmin', 'admin', 'owner', 'hr', 'manager', 'finance'):
        return {'total': 0, 'items': []}

    # Pending expense claims
    claims = await db.rahaza_expense_claims.find(
        {'status': 'submitted'}, {'_id': 0}
    ).sort('submitted_at', 1).limit(limit).to_list(length=limit)

    # Pending travel requests
    travel = await db.employee_travel_requests.find(
        {'status': {'$in': ['submitted', 'approved']}}, {'_id': 0}
    ).sort('submitted_at', 1).limit(limit).to_list(length=limit)

    items = []
    for c in claims:
        items.append({
            'id': c.get('id'),
            'type': 'expense_claim',
            'type_label': 'Klaim Biaya',
            'ref_number': c.get('claim_number'),
            'employee_name': c.get('employee_name'),
            'employee_dept': c.get('employee_dept'),
            'title': c.get('title'),
            'amount': c.get('total_amount', 0),
            'status': c.get('status'),
            'submitted_at': str(c.get('submitted_at') or c.get('created_at') or ''),
        })
    for t in travel:
        sub_label = 'Menunggu Persetujuan' if t.get('status') == 'submitted' else 'Menunggu Uang Muka'
        items.append({
            'id': t.get('id'),
            'type': 'travel_request',
            'type_label': f'Perjalanan Dinas ({sub_label})',
            'ref_number': t.get('trip_number'),
            'employee_name': t.get('employee_name'),
            'employee_dept': t.get('employee_dept'),
            'title': f"{t.get('destination')} ({t.get('start_date')} - {t.get('end_date')})",
            'amount': t.get('total_budget', 0),
            'status': t.get('status'),
            'submitted_at': str(t.get('submitted_at') or t.get('created_at') or ''),
        })

    items.sort(key=lambda x: x.get('submitted_at') or '', reverse=False)
    return {'total': len(items), 'items': items}


@router.get('/my-summary')
async def my_expense_summary(user: dict = Depends(require_auth)):
    """Summary klaim dan perjalanan dinas milik karyawan yang login."""
    db = get_db()
    emp_id = user.get('id')
    base_q = {'employee_id': emp_id}

    # My claims
    my_claims = await db.rahaza_expense_claims.count_documents(base_q)
    my_claims_pending = await db.rahaza_expense_claims.count_documents({**base_q, 'status': 'submitted'})
    my_claims_approved = await db.rahaza_expense_claims.count_documents({**base_q, 'status': {'$in': ['approved', 'paid', 'posted']}})

    total_claimed = 0
    total_paid = 0
    async for doc in db.rahaza_expense_claims.aggregate([
        {'$match': {**base_q, 'status': {'$in': ['submitted', 'approved', 'paid', 'posted']}}},
        {'$group': {'_id': '$status', 'total': {'$sum': '$total_amount'}}}
    ]):
        if doc['_id'] in ('paid', 'posted'):
            total_paid += doc.get('total', 0)
        total_claimed += doc.get('total', 0)

    # My trips
    my_trips = await db.employee_travel_requests.count_documents(base_q)
    my_trips_pending = await db.employee_travel_requests.count_documents({**base_q, 'status': 'submitted'})
    active_trip = await db.employee_travel_requests.count_documents({**base_q, 'status': {'$in': ['approved', 'advance_paid', 'on_trip']}})

    return {
        'employee_id': emp_id,
        'expense_claims': {
            'total': my_claims,
            'pending': my_claims_pending,
            'approved': my_claims_approved,
            'total_claimed': total_claimed,
            'total_paid': total_paid,
        },
        'travel_requests': {
            'total': my_trips,
            'pending': my_trips_pending,
            'active': active_trip,
        },
    }
