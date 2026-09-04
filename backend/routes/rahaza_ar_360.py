"""
CV. Dewi Aditya / Rahaza — AR 360° (Aging + Customer Statement + Top Debtors)
Phase 30 — Order-to-Cash (OTC) Completion

Complement to Phase 27 (AP from GR + 3-way Match). Now completes the OTC side:
- Enhanced AR aging with per-customer breakdown matrix
- Top debtors ranking
- Customer statement with running balance (invoices + payments chronologically)
- Collection KPIs (DSO, % overdue, etc.)
- Multi-source: combines `rahaza_ar_invoices` + (optionally) `dewi_maklon_invoices`

Endpoints:
  GET  /api/rahaza/ar-360/dashboard               — system-wide KPIs + bucket totals + top debtors
  GET  /api/rahaza/ar-360/aging                   — per-customer aging matrix
  GET  /api/rahaza/ar-360/customer/{cid}/statement — single-customer statement
"""

from fastapi import APIRouter, HTTPException, Request, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, date, timedelta
from database import get_db
from auth import require_auth, serialize_doc
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/rahaza/ar-360', tags=['Rahaza-AR-360'])

# Open statuses considered as outstanding AR
OPEN_AR_STATUSES = ('sent', 'partial_paid', 'overdue', 'pending')
TERMINAL_AR_STATUSES = ('paid', 'cancelled', 'void')


def _today() -> date:
    return date.today()


def _parse_date(v) -> Optional[date]:
    """Normalisasi APA PUN menjadi `datetime.date` murni (atau None).

    BUG-4 (FASE 11) — `datetime` adalah SUBCLASS `date`, jadi cek `datetime`
    HARUS didahulukan. Kalau tidak, nilai BSON datetime lolos apa adanya dan
    perbandingan seperti `(today - due).days` / `due < today` melempar
    `TypeError: can't compare datetime.datetime to datetime.date` → HTTP 500.
    Di preview ini belum meledak hanya karena `due_date` masih kosong;
    pada DB berisi data nyata jebakannya aktif.
    """
    if not v:
        return None
    try:
        if isinstance(v, datetime):      # WAJIB dicek sebelum `date`
            return v.date()
        if isinstance(v, date):
            return v
        s = str(v)[:10]
        return date.fromisoformat(s)
    except Exception:
        return None


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


def _bucket_key(days_overdue: int) -> str:
    if days_overdue <= 0:
        return 'current'
    if days_overdue <= 30:
        return '1_30'
    if days_overdue <= 60:
        return '31_60'
    if days_overdue <= 90:
        return '61_90'
    return '90_plus'


async def _require_finance(request: Request) -> dict:
    user = await require_auth(request)
    role = (user.get('role') or '').lower()
    if role in ('superadmin', 'admin', 'owner', 'finance', 'manager', 'accountant'):
        return user
    perms = user.get('_permissions') or []
    if '*' in perms or 'finance.manage' in perms or 'finance.read' in perms:
        return user
    raise HTTPException(403, 'Forbidden: butuh role finance/accountant/manager.')


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
async def _fetch_open_invoices(db) -> List[Dict[str, Any]]:
    """Fetch all open AR invoices (status not terminal)."""
    return await db.rahaza_ar_invoices.find(
        {'status': {'$nin': list(TERMINAL_AR_STATUSES)}},
        {'_id': 0}
    ).to_list(length=10000)


def _classify_invoice(inv: Dict[str, Any]) -> Dict[str, Any]:
    """Add days_overdue + bucket + balance fields to invoice dict."""
    today = _today()
    due = _parse_date(inv.get('due_date'))
    if due:
        days_overdue = (today - due).days
    else:
        days_overdue = 0
    balance = float(inv.get('balance') or 0)
    if balance <= 0:
        # nothing to age
        balance = max(0.0, float(inv.get('total') or 0) - float(inv.get('paid_amount') or 0))
    return {
        **inv,
        'days_overdue': days_overdue,
        'bucket': _bucket_key(days_overdue),
        'computed_balance': round(balance, 2),
        'due_date_parsed': due.isoformat() if due else None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────
@router.get('/dashboard')
async def ar_360_dashboard(request: Request, top_n: int = Query(10, le=50)):
    """
    System-wide AR dashboard:
    - Bucket totals (current / 1-30 / 31-60 / 61-90 / 90+)
    - Top N debtors by outstanding balance
    - Collection KPIs: total outstanding, count_overdue, avg_days_overdue, DSO estimate
    """
    await _require_finance(request)
    db = get_db()
    today = _today()

    invoices = await _fetch_open_invoices(db)
    classified = [_classify_invoice(inv) for inv in invoices]

    buckets = {'current': 0.0, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, '90_plus': 0.0}
    bucket_counts = {'current': 0, '1_30': 0, '31_60': 0, '61_90': 0, '90_plus': 0}
    by_customer: Dict[str, Dict[str, Any]] = {}

    total_outstanding = 0.0
    total_overdue_amount = 0.0
    count_overdue = 0
    sum_days_overdue_weighted = 0.0  # sum(days_overdue * balance) for DSO calc

    for inv in classified:
        bal = inv['computed_balance']
        if bal <= 0:
            continue
        b = inv['bucket']
        buckets[b] += bal
        bucket_counts[b] += 1
        total_outstanding += bal
        if inv['days_overdue'] > 0:
            count_overdue += 1
            total_overdue_amount += bal
            sum_days_overdue_weighted += inv['days_overdue'] * bal

        cid = inv.get('customer_id') or 'unknown'
        cname = inv.get('customer_name') or '—'
        if cid not in by_customer:
            by_customer[cid] = {
                'customer_id': cid,
                'customer_name': cname,
                'invoice_count': 0,
                'outstanding': 0.0,
                'overdue_amount': 0.0,
                'oldest_days_overdue': 0,
            }
        by_customer[cid]['invoice_count'] += 1
        by_customer[cid]['outstanding'] += bal
        if inv['days_overdue'] > 0:
            by_customer[cid]['overdue_amount'] += bal
        if inv['days_overdue'] > by_customer[cid]['oldest_days_overdue']:
            by_customer[cid]['oldest_days_overdue'] = inv['days_overdue']

    # Enrich customer names from `rahaza_customers`
    cids_to_resolve = [cid for cid, info in by_customer.items() if info['customer_name'] == '—' and cid != 'unknown']
    if cids_to_resolve:
        cust_rows = await db.rahaza_customers.find(
            {'id': {'$in': cids_to_resolve}}, {'_id': 0, 'id': 1, 'name': 1, 'code': 1}
        ).to_list(length=500)
        cmap = {c['id']: c for c in cust_rows}
        for cid, info in by_customer.items():
            if info['customer_name'] == '—' and cid in cmap:
                info['customer_name'] = cmap[cid].get('name', '—')
                info['customer_code'] = cmap[cid].get('code', '')

    # Round + sort top debtors
    debtors = sorted(by_customer.values(), key=lambda x: x['outstanding'], reverse=True)
    for d in debtors:
        d['outstanding'] = round(d['outstanding'], 2)
        d['overdue_amount'] = round(d['overdue_amount'], 2)

    # DSO-ish metric: weighted average days overdue (across overdue invoices only)
    avg_days_overdue = round(sum_days_overdue_weighted / total_overdue_amount, 1) if total_overdue_amount > 0 else 0

    # Receipts last 30 days (for DSO estimate)
    last_30 = (today - timedelta(days=30)).isoformat()
    paid_invoices_30 = await db.rahaza_ar_invoices.find(
        {'status': 'paid', 'updated_at': {'$gte': last_30}},
        {'_id': 0, 'total': 1, 'paid_amount': 1}
    ).to_list(length=2000)
    cash_collected_30 = sum(float(inv.get('paid_amount', inv.get('total', 0)) or 0) for inv in paid_invoices_30)
    dso_estimate = round((total_outstanding / cash_collected_30) * 30, 1) if cash_collected_30 > 0 else None

    return {
        'as_of': datetime.now(timezone.utc).isoformat(),
        'kpis': {
            'total_outstanding': round(total_outstanding, 2),
            'total_overdue_amount': round(total_overdue_amount, 2),
            'count_open_invoices': len([inv for inv in classified if inv['computed_balance'] > 0]),
            'count_overdue_invoices': count_overdue,
            'avg_days_overdue': avg_days_overdue,
            'total_unique_debtors': len(by_customer),
            'cash_collected_30d': round(cash_collected_30, 2),
            'dso_estimate_days': dso_estimate,
            'overdue_pct_of_outstanding': round((total_overdue_amount / total_outstanding) * 100, 1) if total_outstanding > 0 else 0,
        },
        'buckets': {k: round(v, 2) for k, v in buckets.items()},
        'bucket_counts': bucket_counts,
        'top_debtors': debtors[:top_n],
    }


@router.get('/aging')
async def ar_360_aging_matrix(request: Request,
                              customer_id: Optional[str] = None,
                              with_zero: bool = Query(False, description='Include customers with zero balance')):
    """
    Per-customer aging matrix.
    Returns rows: [{customer_id, customer_name, current, 1_30, 31_60, 61_90, 90_plus, total, count}, ...]
    Optionally filter to one customer_id.
    """
    await _require_finance(request)
    db = get_db()

    invoices = await _fetch_open_invoices(db)
    if customer_id:
        invoices = [inv for inv in invoices if inv.get('customer_id') == customer_id]
    classified = [_classify_invoice(inv) for inv in invoices]

    matrix: Dict[str, Dict[str, Any]] = {}
    for inv in classified:
        cid = inv.get('customer_id') or 'unknown'
        cname = inv.get('customer_name') or '—'
        if cid not in matrix:
            matrix[cid] = {
                'customer_id': cid,
                'customer_name': cname,
                'current': 0.0,
                '1_30': 0.0,
                '31_60': 0.0,
                '61_90': 0.0,
                '90_plus': 0.0,
                'total': 0.0,
                'count': 0,
                'oldest_days_overdue': 0,
            }
        b = inv['bucket']
        bal = inv['computed_balance']
        matrix[cid][b] += bal
        matrix[cid]['total'] += bal
        matrix[cid]['count'] += 1
        if inv['days_overdue'] > matrix[cid]['oldest_days_overdue']:
            matrix[cid]['oldest_days_overdue'] = inv['days_overdue']

    # Enrich missing customer names
    cids_to_resolve = [cid for cid, info in matrix.items() if info['customer_name'] == '—' and cid != 'unknown']
    if cids_to_resolve:
        cust_rows = await db.rahaza_customers.find(
            {'id': {'$in': cids_to_resolve}}, {'_id': 0, 'id': 1, 'name': 1, 'code': 1, 'contact_phone': 1, 'contact_email': 1}
        ).to_list(length=500)
        cmap = {c['id']: c for c in cust_rows}
        for cid, info in matrix.items():
            if info['customer_name'] == '—' and cid in cmap:
                info['customer_name'] = cmap[cid].get('name', '—')
                info['customer_code'] = cmap[cid].get('code', '')

    rows = list(matrix.values())
    if not with_zero:
        rows = [r for r in rows if r['total'] > 0.01]
    rows.sort(key=lambda r: r['total'], reverse=True)
    # Round
    for r in rows:
        for k in ('current', '1_30', '31_60', '61_90', '90_plus', 'total'):
            r[k] = round(r[k], 2)

    # Totals footer
    totals = {
        'current': sum(r['current'] for r in rows),
        '1_30': sum(r['1_30'] for r in rows),
        '31_60': sum(r['31_60'] for r in rows),
        '61_90': sum(r['61_90'] for r in rows),
        '90_plus': sum(r['90_plus'] for r in rows),
        'total': sum(r['total'] for r in rows),
        'count': sum(r['count'] for r in rows),
    }
    for k in ('current', '1_30', '31_60', '61_90', '90_plus', 'total'):
        totals[k] = round(totals[k], 2)

    return {'rows': rows, 'totals': totals, 'as_of': datetime.now(timezone.utc).isoformat()}


@router.get('/customer/{customer_id}/statement')
async def customer_statement(customer_id: str, request: Request,
                             date_from: Optional[str] = None,
                             date_to: Optional[str] = None):
    """
    Detailed customer statement with running balance.
    
    Combines invoices (debits) + payments (credits) chronologically and computes
    running balance.
    """
    await _require_finance(request)
    db = get_db()

    customer = await db.rahaza_customers.find_one({'id': customer_id}, {'_id': 0})
    if not customer:
        raise HTTPException(404, 'Customer tidak ditemukan')

    # Date filter
    df = _parse_date(date_from) if date_from else None
    dt = _parse_date(date_to) if date_to else None

    # Fetch all invoices for this customer
    inv_query: Dict[str, Any] = {'customer_id': customer_id}
    if df or dt:
        date_q: Dict[str, Any] = {}
        if df:
            date_q['$gte'] = df.isoformat()
        if dt:
            date_q['$lte'] = dt.isoformat()
        inv_query['issue_date'] = date_q

    invoices = await db.rahaza_ar_invoices.find(inv_query, {'_id': 0}).sort('issue_date', 1).to_list(length=2000)

    # Build chronological transaction stream
    transactions: List[Dict[str, Any]] = []
    for inv in invoices:
        # Skip cancelled/void for statement view (but include paid for history)
        if inv.get('status') in ('cancelled', 'void'):
            continue
        transactions.append({
            'date': inv.get('issue_date'),
            'type': 'invoice',
            'reference': inv.get('invoice_number'),
            'description': f"Invoice {inv.get('invoice_number')}",
            'debit': float(inv.get('total') or 0),
            'credit': 0,
            'invoice_id': inv.get('id'),
            'status': inv.get('status'),
            'due_date': inv.get('due_date'),
            'balance_before': None,  # filled below
            'balance_after': None,
        })
        # Look at payments embedded in invoice doc (some flows store payments inline)
        for p in (inv.get('payments') or []):
            transactions.append({
                'date': p.get('date') or p.get('payment_date') or inv.get('issue_date'),
                'type': 'payment',
                'reference': p.get('reference') or f"PAY-{inv.get('invoice_number')}",
                'description': f"Payment for {inv.get('invoice_number')}",
                'debit': 0,
                'credit': float(p.get('amount') or 0),
                'invoice_id': inv.get('id'),
                'payment_method': p.get('payment_method'),
                'note': p.get('note'),
            })

    # RC-09: pembayaran AR LIVE tersimpan di rahaza_cash_movements
    # (record_ar_payment → category 'ar_payment', ref_id=<invoice_id>; seed → 'ar_receipt',
    # ref_id 'ar:<no>'). rahaza_ar_payments = seed-only DUPLIKAT movements → jalur lama dihapus
    # agar tidak double-count.
    try:
        inv_ids = {inv.get('id') for inv in invoices if inv.get('id')}
        inv_nums = {inv.get('invoice_number') for inv in invoices if inv.get('invoice_number')}
        movs = await db.rahaza_cash_movements.find(
            {'direction': 'in', 'category': {'$in': ['ar_payment', 'ar_receipt']}},
            {'_id': 0}
        ).to_list(length=2000)
        for mv in movs:
            ref = str(mv.get('ref_id') or '')
            ref_core = ref[3:] if ref.startswith('ar:') else ref
            ref_label = mv.get('ref_label') or ''
            if ref_core not in inv_ids and ref_core not in inv_nums and ref_label not in inv_nums:
                continue
            pdate = mv.get('date')
            if df and pdate and pdate < df.isoformat():
                continue
            if dt and pdate and pdate > dt.isoformat():
                continue
            transactions.append({
                'date': pdate,
                'type': 'payment',
                'reference': ref_label or f"PAY-{ref_core[:8]}",
                'description': mv.get('notes') or f"Pembayaran ({mv.get('account_name', '')})",
                'debit': 0,
                'credit': float(mv.get('amount') or 0),
                'invoice_id': ref_core if ref_core in inv_ids else None,
                'payment_method': mv.get('account_name'),
            })
    except Exception:
        # Collection may not exist — that's OK
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    # Sort by date, fallback to insertion order
    transactions.sort(key=lambda t: (t.get('date') or ''))

    # Compute running balance
    running = 0.0
    for t in transactions:
        t['balance_before'] = round(running, 2)
        running += float(t.get('debit') or 0) - float(t.get('credit') or 0)
        t['balance_after'] = round(running, 2)
        t['debit'] = round(float(t.get('debit') or 0), 2)
        t['credit'] = round(float(t.get('credit') or 0), 2)

    # Aging snapshot
    open_invoices = [_classify_invoice(inv) for inv in invoices
                     if inv.get('status') not in TERMINAL_AR_STATUSES]
    buckets = {'current': 0.0, '1_30': 0.0, '31_60': 0.0, '61_90': 0.0, '90_plus': 0.0}
    for inv in open_invoices:
        bal = inv['computed_balance']
        if bal > 0:
            buckets[inv['bucket']] += bal

    return {
        'customer': serialize_doc(customer),
        'transactions': transactions,
        'opening_balance': 0,
        'closing_balance': round(running, 2),
        'aging_snapshot': {k: round(v, 2) for k, v in buckets.items()},
        'aging_total': round(sum(buckets.values()), 2),
        'total_invoices': len([t for t in transactions if t['type'] == 'invoice']),
        'total_payments': len([t for t in transactions if t['type'] == 'payment']),
        'total_billed': round(sum(t.get('debit', 0) for t in transactions), 2),
        'total_paid': round(sum(t.get('credit', 0) for t in transactions), 2),
        'as_of': datetime.now(timezone.utc).isoformat(),
        'date_from': df.isoformat() if df else None,
        'date_to': dt.isoformat() if dt else None,
    }


@router.get('/customers')
async def list_customers_with_balance(request: Request):
    """Lightweight customers list for picker — only those with outstanding."""
    await _require_finance(request)
    db = get_db()

    invoices = await _fetch_open_invoices(db)
    classified = [_classify_invoice(inv) for inv in invoices]
    by_customer: Dict[str, Dict[str, Any]] = {}
    for inv in classified:
        cid = inv.get('customer_id') or 'unknown'
        if cid == 'unknown':
            continue
        if cid not in by_customer:
            by_customer[cid] = {
                'customer_id': cid,
                'customer_name': inv.get('customer_name'),
                'outstanding': 0.0,
                'invoice_count': 0,
            }
        by_customer[cid]['outstanding'] += inv['computed_balance']
        by_customer[cid]['invoice_count'] += 1

    # Enrich names
    cids_to_resolve = [cid for cid, info in by_customer.items() if not info['customer_name']]
    if cids_to_resolve:
        cust_rows = await db.rahaza_customers.find(
            {'id': {'$in': cids_to_resolve}}, {'_id': 0, 'id': 1, 'name': 1, 'code': 1}
        ).to_list(length=500)
        cmap = {c['id']: c for c in cust_rows}
        for cid, info in by_customer.items():
            if not info['customer_name'] and cid in cmap:
                info['customer_name'] = cmap[cid].get('name', '—')

    # Always include all customers from master (even with zero outstanding)
    all_customers = await db.rahaza_customers.find({}, {'_id': 0, 'id': 1, 'name': 1, 'code': 1}).to_list(length=1000)
    for c in all_customers:
        if c['id'] not in by_customer:
            by_customer[c['id']] = {
                'customer_id': c['id'],
                'customer_name': c.get('name', '—'),
                'customer_code': c.get('code', ''),
                'outstanding': 0.0,
                'invoice_count': 0,
            }

    rows = sorted(by_customer.values(), key=lambda x: x['outstanding'], reverse=True)
    for r in rows:
        r['outstanding'] = round(r['outstanding'], 2)
    return {'total': len(rows), 'items': rows}
