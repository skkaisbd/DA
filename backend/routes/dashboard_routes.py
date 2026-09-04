"""
Dashboard, Global Search, Vendor Dashboard
Extracted from server.py monolith.
"""
# ruff: noqa: E741
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import (require_auth, serialize_doc)
from routes.shared import now, parse_date, to_end_of_day, get_pagination_params, paginated_response
from core import product_master as pm  # T1: SATU definisi "model masih hidup"
import logging
from datetime import datetime, timezone, timedelta, date
import re

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["dashboard"])


# ─── HELPERS ─────────────────────────────────────────────────────────────────
async def _sum_field(db, collection, query: dict, field: str) -> float:
    agg = await db[collection].aggregate([
        {'$match': query},
        {'$group': {'_id': None, 'total': {'$sum': f'${field}'}}}
    ]).to_list(2)
    return agg[0]['total'] if agg else 0.0


async def _ar_aging(db) -> dict:
    """Compute AR aging buckets from rahaza_ar_invoices."""
    today = date.today()
    unpaid = await db.rahaza_ar_invoices.find(
        {'status': {'$in': ['sent', 'partial']}}, {'_id': 0, 'balance': 1, 'due_date': 1}
    ).to_list(500)
    buckets = {'current': 0, 'd30': 0, 'd60': 0, 'd90': 0, 'd90plus': 0}
    for inv in unpaid:
        bal = float(inv.get('balance', 0))
        dd = inv.get('due_date')
        if not dd:
            buckets['current'] += bal
            continue
        try:
            dd_d = date.fromisoformat(str(dd)[:10])
            diff = (today - dd_d).days
        except Exception:
            buckets['current'] += bal
            continue
        if diff <= 0:
            buckets['current'] += bal
        elif diff <= 30:
            buckets['d30'] += bal
        elif diff <= 60:
            buckets['d60'] += bal
        elif diff <= 90:
            buckets['d90'] += bal
        else:
            buckets['d90plus'] += bal
    return buckets

@router.get("/dashboard")
async def get_dashboard(request: Request):
    """Dashboard Eksekutif — KPI ringkasan dengan data today/MTD/YTD."""
    await require_auth(request)
    db = get_db()
    n = now()
    today = date.today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)
    mtd_start = datetime(today.year, today.month, 1, tzinfo=timezone.utc)
    ytd_start = datetime(today.year, 1, 1, tzinfo=timezone.utc)

    # ── Rahaza orders (primary) ──
    total_orders = await db.rahaza_orders.count_documents({})
    active_orders = await db.rahaza_orders.count_documents({'status': {'$in': ['confirmed', 'in_production']}})
    completed_orders = await db.rahaza_orders.count_documents({'status': {'$in': ['completed', 'closed']}})

    # Work Orders (rahaza)
    active_wos = await db.rahaza_work_orders.count_documents({'status': {'$in': ['released', 'in_progress']}})
    wo_status_agg = await db.rahaza_work_orders.aggregate([
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]).to_list(500)

    # ── AR / AP (Rahaza finance) ──
    ar_invoices = await db.rahaza_ar_invoices.find({}, {'_id': 0}).to_list(500)
    ap_invoices = await db.rahaza_ap_invoices.find({}, {'_id': 0}).to_list(500)
    total_revenue = sum(i.get('total', 0) for i in ar_invoices)
    total_paid_ar = sum(i.get('paid_amount', 0) for i in ar_invoices)
    outstanding_ar = sum(i.get('balance', 0) for i in ar_invoices if i.get('status') != 'paid')
    total_vendor_cost = sum(i.get('total', 0) for i in ap_invoices)
    total_paid_ap = sum(i.get('paid_amount', 0) for i in ap_invoices)
    outstanding_ap = sum(i.get('balance', 0) for i in ap_invoices if i.get('status') != 'paid')
    gross_margin = total_revenue - total_vendor_cost

    # ── Shipments — RC-03/RC-DASH-DECISION: pengiriman pelanggan = wh_delivery_notes
    # (rahaza_shipments = koleksi dorman/kosong, self-consistent tapi tak dipakai flow)
    pending_shipments = await db.wh_delivery_notes.count_documents({'status': {'$in': ['draft', 'issued']}})

    # ── Delayed orders (past due_date, not completed) ──
    today_iso = today.isoformat()
    delayed_orders = await db.rahaza_orders.count_documents({
        'status': {'$in': ['confirmed', 'in_production']},
        'due_date': {'$lt': today_iso},
    })

    # ── Revenue Today / MTD / YTD (from rahaza AR invoices — SSOT) ──
    # NOTE: legacy `invoices` collection was DROPPED in Session #11.16 Phase B.
    # Revenue now reads exclusively from rahaza_ar_invoices (SSOT).
    # See FORENSIC_04 Cluster 5 + FORENSIC_12 GAP-01.
    revenue_today = sum(i.get('total', 0) for i in ar_invoices
                        if i.get('created_at') and _in_range(i['created_at'], today_start, today_end))
    revenue_mtd   = sum(i.get('total', 0) for i in ar_invoices
                        if i.get('created_at') and _in_range(i['created_at'], mtd_start, today_end))
    revenue_ytd   = sum(i.get('total', 0) for i in ar_invoices
                        if i.get('created_at') and _in_range(i['created_at'], ytd_start, today_end))

    # ── Employee count (active) ──
    active_employees = await db.rahaza_employees.count_documents({'status': {'$in': ['active', 'Active']}})
    if active_employees == 0:
        active_employees = await db.users.count_documents({'status': 'active'})

    # ── Attendance today — RC-01/RC-03: SSOT live rahaza_attendance_events
    # (fallback dewi_attendance dihapus: phantom tanpa writer)
    att_today_ids = await db.rahaza_attendance_events.distinct(
        'employee_id', {'date': today_iso, 'status': {'$in': ['hadir', 'present']}})
    att_today = len(att_today_ids)
    attendance_today_pct = min(100, round((att_today / active_employees * 100) if active_employees else 0))

    # ── AR aging ──
    ar_aging = await _ar_aging(db)

    # ── OEE — FASE 4 (E10 DELETE): engine rahaza_oee/line diarsip → metrik OEE null
    avg_oee = None

    # ── On-time rate ──
    closed_orders = await db.rahaza_orders.find(
        {'status': {'$in': ['completed', 'closed']}}, {'_id': 0, 'due_date': 1, 'updated_at': 1}
    ).to_list(500)
    on_time = 0
    for o in closed_orders:
        dd = o.get('due_date')
        upd = o.get('updated_at')
        if not dd or not upd:
            continue
        # upd is datetime, dd is ISO string
        try:
            upd_d = upd.date() if hasattr(upd, 'date') else date.fromisoformat(str(upd)[:10])
            dd_d = date.fromisoformat(dd[:10])
            if upd_d <= dd_d:
                on_time += 1
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    on_time_rate = round((on_time / len(closed_orders) * 100) if closed_orders else 0)

    # ── Monthly data (6 months — orders + output) ──
    monthly_data = []
    for i in range(5, -1, -1):
        start = datetime(n.year, n.month, 1, tzinfo=timezone.utc) - timedelta(days=i * 30)
        start = start.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        m_orders = await db.rahaza_orders.count_documents({'created_at': {'$gte': start, '$lt': end}})
        # RC-03/RC-DASH-DECISION: output produksi nyata = rahaza_wip_events event_type='output'
        # (event_date string "YYYY-MM-DD"; rahaza_shipments = dorman/kosong)
        m_out_agg = await db.rahaza_wip_events.aggregate([
            {'$match': {'event_type': 'output',
                        'event_date': {'$gte': start.date().isoformat(), '$lt': end.date().isoformat()}}},
            {'$group': {'_id': None, 'total': {'$sum': {'$ifNull': ['$qty', 0]}}}}
        ]).to_list(1)
        monthly_data.append({
            'month': start.strftime('%b %y'),
            'pos': m_orders,
            'production': m_out_agg[0]['total'] if m_out_agg else 0,
        })

    # ── User count ──
    total_users = await db.users.count_documents({'status': 'active'})

    # ── Alerts: overdue orders, near deadline, unpaid invoices ──
    overdue_orders = await db.rahaza_orders.find(
        {'status': {'$in': ['confirmed', 'in_production']}, 'due_date': {'$lt': today_iso}},
        {'_id': 0},
    ).sort('due_date', 1).limit(5).to_list(500)
    near_deadline_orders = await db.rahaza_orders.find(
        {'status': {'$in': ['confirmed', 'in_production']},
         'due_date': {'$gte': today_iso, '$lt': (date.today() + timedelta(days=3)).isoformat()}},
        {'_id': 0},
    ).sort('due_date', 1).limit(5).to_list(500)
    unpaid_ars = await db.rahaza_ar_invoices.find(
        {'status': {'$in': ['sent', 'partial']}}, {'_id': 0}
    ).sort('due_date', 1).limit(5).to_list(500)

    return {
        'totalPOs': total_orders, 'activePOs': active_orders,
        'garments': await db.rahaza_models.count_documents(pm.LIVE_MODEL_FILTER),
        # T1 — hitungan produk BERHENTI bergantung `active: True` semata. Dokumen
        # hasil promosi R&D lama hanya punya `status: 'active'`; dulu tidak ikut
        # terhitung ⇒ dashboard bilang 1, daftar model bilang 2.
        'products': await db.rahaza_models.count_documents(pm.LIVE_MODEL_FILTER),
        'totalInvoiced': total_revenue + total_vendor_cost,
        'totalPaid': total_paid_ar + total_paid_ap,
        'outstanding': outstanding_ar + outstanding_ap,
        'totalVendorCost': total_vendor_cost,
        'totalRevenue': total_revenue,
        'grossMargin': gross_margin,
        'totalInvoicedAR': total_revenue, 'totalInvoicedAP': total_vendor_cost,
        'outstandingAR': outstanding_ar, 'outstandingAP': outstanding_ap,
        'totalPaidAR': total_paid_ar, 'totalPaidAP': total_paid_ap,
        'activeJobs': active_wos,
        'pendingShipments': pending_shipments,
        'pendingAdditionalRequests': 0,
        'pendingReplacementRequests': 0,
        'pendingReturns': 0,
        'totalBuyerShipments': await db.wh_delivery_notes.count_documents({'status': {'$in': ['issued', 'received']}}),
        'totalVendorShipments': 0,
        'totalProducedGlobal': 0,
        'totalAvailableGlobal': 0,
        'globalProgressPct': round((completed_orders / total_orders * 100) if total_orders else 0),
        'totalAccessories': await db.rahaza_materials.count_documents({'type': 'accessory', 'active': True}),
        'totalAccShipments': 0,
        'pendingAccInspections': 0,
        'pendingAccRequests': 0,
        'unpaidInvoices': sum(1 for i in ar_invoices if i.get('status') == 'sent'),
        'partialInvoices': sum(1 for i in ar_invoices if i.get('status') == 'partial'),
        'delayedPOs': delayed_orders,
        'monthlyData': monthly_data,
        'woStatus': wo_status_agg,
        'topGarments': [],
        'pendingReminders': 0,
        'onTimeRate': on_time_rate,
        'totalUsers': total_users,
        # ── NEW: Real-time Executive KPIs ──
        'revenueToday': revenue_today,
        'revenueMTD': revenue_mtd,
        'revenueYTD': revenue_ytd,
        'activeEmployees': active_employees,
        'attendanceTodayCount': att_today,
        'attendanceTodayPct': attendance_today_pct,
        'avgOEE': avg_oee,
        'arAging': ar_aging,
        'alerts': {
            'overduePos': serialize_doc(overdue_orders),
            'nearDeadlinePos': serialize_doc(near_deadline_orders),
            'unpaidInvoices': serialize_doc(unpaid_ars),
        },
    }


def _in_range(val, start: datetime, end: datetime) -> bool:
    """Check if a datetime value (or ISO string) is in [start, end)."""
    if isinstance(val, datetime):
        dt = val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    else:
        try:
            s = str(val).replace('Z', '+00:00')
            dt = datetime.fromisoformat(s)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
        except Exception:
            return False
    return start <= dt < end


@router.get("/dashboard/analytics")
async def get_dashboard_analytics(request: Request):
    """Enhanced analytics with date range filter"""
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    date_from = parse_date(sp.get('from'))
    date_to = to_end_of_day(sp.get('to'))
    date_filter = {}
    if date_from:
        date_filter['$gte'] = date_from
    if date_to:
        date_filter['$lte'] = date_to
    date_q = {'created_at': date_filter} if date_filter else {}
    # Vendor lead times — RC-04: SSOT warehouse_receiving (join rahaza_purchase_orders
    # by po_number; lead = tanggal terima - po_date). vendor_shipments = subsistem legacy kosong.
    vendor_lead_times = []
    recvs = await db.warehouse_receiving.find(
        {**date_q, 'status': {'$in': ['received', 'accepted', 'partial_received']}},
        {'_id': 0, 'supplier_name': 1, 'po_number': 1, 'created_at': 1}).to_list(500)
    po_numbers = [r['po_number'] for r in recvs if r.get('po_number')]
    pos_map = {}
    if po_numbers:
        async for p in db.rahaza_purchase_orders.find(
                {'po_number': {'$in': po_numbers}}, {'_id': 0, 'po_number': 1, 'po_date': 1}):
            pos_map[p['po_number']] = p.get('po_date')
    vendor_lt_map = {}
    for r in recvs:
        vn = r.get('supplier_name', 'Unknown')
        po_date = pos_map.get(r.get('po_number'))
        recv_at = r.get('created_at')
        if not po_date or not recv_at:
            continue
        try:
            recv_d = recv_at.date() if isinstance(recv_at, datetime) else date.fromisoformat(str(recv_at)[:10])
            delta = (recv_d - date.fromisoformat(str(po_date)[:10])).days
        except Exception:
            continue
        if delta >= 0:
            vendor_lt_map.setdefault(vn, []).append(delta)
    for vn, days_list in sorted(vendor_lt_map.items()):
        avg_lt = round(sum(days_list) / len(days_list), 1) if days_list else 0
        vendor_lead_times.append({'vendor': vn, 'avg_days': avg_lt, 'shipment_count': len(days_list)})
    # Missing/defect rates by vendor — RC-04: SSOT rahaza_grn_inspections
    # (field: supplier_name/total_received_qty/total_rejected_qty)
    all_inspections = await db.rahaza_grn_inspections.find(date_q, {'_id': 0}).to_list(500)
    vendor_defect_map = {}
    for insp in all_inspections:
        vn = insp.get('supplier_name', 'Unknown')
        if vn not in vendor_defect_map:
            vendor_defect_map[vn] = {'received': 0, 'missing': 0}
        vendor_defect_map[vn]['received'] += insp.get('total_received_qty', 0) or 0
        vendor_defect_map[vn]['missing'] += insp.get('total_rejected_qty', 0) or 0
    defect_rates = []
    for vn, vals in sorted(vendor_defect_map.items()):
        total = vals['received'] + vals['missing']
        rate = round((vals['missing'] / total * 100) if total > 0 else 0, 1)
        defect_rates.append({'vendor': vn, 'missing_rate': rate, 'total_received': vals['received'], 'total_missing': vals['missing']})
    # Production throughput by week — RC-04: SSOT rahaza_wip_events (event_type='output',
    # event_date string). rahaza_shipments & production_progress = kosong/legacy.
    weekly_throughput = []
    n = now()
    for w in range(7, -1, -1):
        start = n - timedelta(days=(w + 1) * 7)
        end = n - timedelta(days=w * 7)
        wip_agg = await db.rahaza_wip_events.aggregate([
            {'$match': {'event_type': 'output',
                        'event_date': {'$gte': start.date().isoformat(), '$lt': end.date().isoformat()}}},
            {'$group': {'_id': None, 'total': {'$sum': {'$ifNull': ['$qty', 0]}}}}
        ]).to_list(1)
        qty = wip_agg[0]['total'] if wip_agg else 0
        weekly_throughput.append({
            'week': f"W{8-w}", 'label': start.strftime('%d/%m'),
            'qty': qty
        })
    # Production completion rate by product — RC-04: SSOT rahaza_work_orders group model_name
    product_completion = await db.rahaza_work_orders.aggregate([
        {'$group': {'_id': '$model_name', 'total_available': {'$sum': {'$ifNull': ['$qty', 0]}},
                    'total_produced': {'$sum': {'$ifNull': ['$completed_qty', 0]}}}},
        {'$sort': {'total_available': -1}}, {'$limit': 10}
    ]).to_list(10)
    product_comp = [{'product': p['_id'] or 'Unknown',
                     'available': p.get('total_available', 0),
                     'produced': p.get('total_produced', 0),
                     'rate': round((p['total_produced'] / p['total_available'] * 100) if p.get('total_available', 0) > 0 else 0, 1)
                     } for p in product_completion]
    # Shipment/receiving status breakdown — RC-04: SSOT warehouse_receiving
    ship_status_agg = await db.warehouse_receiving.aggregate([
        {'$group': {'_id': '$status', 'count': {'$sum': 1}}}
    ]).to_list(20)
    # WO deadline distribution — RC-04: SSOT rahaza_work_orders.due_date (string)
    all_pos = await db.rahaza_work_orders.find(
        {'status': {'$nin': ['completed', 'draft', 'cancelled']}},
        {'_id': 0, 'due_date': 1, 'wo_number': 1}).to_list(500)
    overdue_count = 0
    this_week_count = 0
    next_week_count = 0
    later_count = 0
    for p in all_pos:
        dl = p.get('due_date')
        if not dl:
            continue
        if isinstance(dl, str):
            dl = parse_date(dl)
        if not isinstance(dl, datetime):
            continue
        # Ensure timezone-aware comparison
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        if dl < n:
            overdue_count += 1
        elif dl < n + timedelta(days=7):
            this_week_count += 1
        elif dl < n + timedelta(days=14):
            next_week_count += 1
        else:
            later_count += 1
    return {
        'vendorLeadTimes': vendor_lead_times,
        'defectRates': defect_rates,
        'weeklyThroughput': weekly_throughput,
        'productCompletion': product_comp,
        'shipmentStatus': [{'status': s['_id'] or 'Unknown', 'count': s['count']} for s in ship_status_agg],
        'deadlineDistribution': {
            'overdue': overdue_count, 'thisWeek': this_week_count,
            'nextWeek': next_week_count, 'later': later_count
        }
    }


# ─── VENDOR DASHBOARD ────────────────────────────────────────────────────────
@router.get("/vendor/dashboard")
async def get_vendor_dashboard(request: Request):
    """Dashboard vendor CMT (modul 1 dari 11).

    ── Portal CMT Override (2026-08-08) ─────────────────────────────────────
    Dulu endpoint ini melempar 403 KERAS untuk semua non-vendor, sehingga staf
    DA yang mengisi atas nama vendor "tidak pakai sistem" mentok di pintu
    pertama. Sekarang staf berhak (lihat core/cmt_override.OVERRIDE_ROLES) boleh
    membacanya dengan header `X-CMT-Override-Vendor`, dan HANYA untuk vendor itu.

    `recentProgress` & `alerts` dulu dikembalikan KOSONG PERMANEN (list hard-code)
    padahal frontend VendorDashboard.jsx merendernya — jadi dua panel di layar
    vendor selalu kosong tanpa alasan. Sekarang diisi dari data sungguhan.
    """
    user = await require_auth(request)
    from routes.production_rbac import is_vendor, vendor_identity
    from core.cmt_override import resolve_override
    db = get_db()
    ctx = await resolve_override(request, user, db)
    if is_vendor(user):
        vendor_id = vendor_identity(user)
    else:
        if not ctx:
            raise HTTPException(
                403,
                'Dashboard vendor hanya untuk akun vendor CMT, atau staf DA yang '
                'membuka Portal CMT Override (pilih vendor dulu).')
        vendor_id = ctx['vendor_id']
    jobs = await db.production_jobs.find({'vendor_id': vendor_id}, {'_id': 0}).sort('created_at', -1).to_list(500)
    active_jobs = len([j for j in jobs if j.get('status') == 'In Progress' and not j.get('parent_job_id')])
    completed_jobs = len([j for j in jobs if j.get('status') == 'Completed'])
    incoming = await db.vendor_shipments.count_documents({'vendor_id': vendor_id, 'status': 'Sent'})
    all_job_ids = [j['id'] for j in jobs]
    all_job_items = await db.production_job_items.find({'job_id': {'$in': all_job_ids}}).to_list(500) if all_job_ids else []
    total_produced = sum(i.get('produced_qty', 0) for i in all_job_items)
    total_available = sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in all_job_items)

    # ── recentProgress: 10 setoran progress terakhir milik vendor ini ────────
    recent_progress = []
    if all_job_ids:
        job_num_map = {j['id']: j.get('job_number', '') for j in jobs}
        rows = await db.production_progress.find(
            {'job_id': {'$in': all_job_ids}}, {'_id': 0}
        ).sort('progress_date', -1).to_list(10)
        for r in rows:
            recent_progress.append({
                'id': r.get('id'),
                'job_number': job_num_map.get(r.get('job_id'), ''),
                'sku': r.get('sku', ''),
                'product_name': r.get('product_name', ''),
                'completed_quantity': r.get('completed_quantity', 0),
                'progress_date': serialize_doc(r.get('progress_date')),
                'recorded_by': r.get('recorded_by', ''),
                # keputusan 3a — badge "diinput staf DA" juga di dashboard vendor
                'entered_by_staff': r.get('entered_by_staff') is True,
                'entered_by': r.get('entered_by', ''),
            })

    # ── alerts: job telat & job mendekati tenggat (7 hari) ───────────────────
    _now = datetime.now(timezone.utc)
    overdue_jobs, near_jobs = [], []
    for j in jobs:
        if j.get('status') == 'Completed':
            continue
        dl = j.get('deadline') or j.get('delivery_deadline')
        if isinstance(dl, str):
            try:
                dl = datetime.fromisoformat(dl.replace('Z', '+00:00'))
            except Exception:
                dl = None
        if not isinstance(dl, datetime):
            continue
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=timezone.utc)
        days = (dl - _now).days
        row = {'id': j.get('id'), 'job_number': j.get('job_number', ''),
               'po_number': j.get('po_number', ''),
               'deadline': serialize_doc(dl), 'days_left': days}
        if days < 0:
            overdue_jobs.append(row)
        elif days <= 7:
            near_jobs.append(row)

    return {
        'activeJobs': active_jobs, 'completedJobs': completed_jobs,
        'incomingShipments': incoming,
        'totalProduced': total_produced, 'totalAvailable': total_available,
        'progressPct': round((total_produced / total_available * 100) if total_available > 0 else 0),
        'recentProgress': recent_progress,
        'alerts': {'overdueJobs': overdue_jobs, 'nearDeadlineJobs': near_jobs},
        'vendorId': vendor_id,
    }


# ─── GLOBAL SEARCH ───────────────────────────────────────────────────────────
@router.get("/global-search")
async def global_search(request: Request):
    """
    Global Search v2 — Rahaza-native.
    Mencari lintas entitas bisnis utama: Order, Work Order, Customer, Material,
    Employee, AR Invoice, AP Invoice, Line.

    Response: {results: [{type, id, label, sub, module}]}
    - `module` = moduleId yang dikenali moduleRegistry.js (untuk navigasi saat klik).
    """
    await require_auth(request)
    db = get_db()
    q = request.query_params.get('q', '').strip()
    if not q or len(q) < 2:
        return {'results': []}

    regex = {'$regex': re.escape(q), '$options': 'i'}
    limit_per_type = 5
    results = []

    # ── Orders ─────────────────────────────────────────────────────────────
    orders = await db.rahaza_orders.find(
        {'$or': [
            {'order_number': regex},
            {'customer_name_snapshot': regex},
            {'notes': regex},
        ]},
        {'_id': 0, 'id': 1, 'order_number': 1, 'customer_name_snapshot': 1, 'status': 1, 'order_date': 1}
    ).limit(limit_per_type).to_list(500)
    for o in orders:
        results.append({
            'type': 'Order',
            'id': o.get('id'),
            'label': o.get('order_number', ''),
            'sub': f"{o.get('customer_name_snapshot', '')} · {o.get('status', '')}",
            'module': 'prod-orders',
        })

    # ── Work Orders ────────────────────────────────────────────────────────
    wos = await db.rahaza_work_orders.find(
        {'$or': [
            {'wo_number': regex},
            {'order_number_snapshot': regex},
            {'model_code_snapshot': regex},
            {'model_name_snapshot': regex},
        ]},
        {'_id': 0, 'id': 1, 'wo_number': 1, 'order_number_snapshot': 1, 'model_code_snapshot': 1,
         'model_name_snapshot': 1, 'status': 1, 'qty': 1}
    ).limit(limit_per_type).to_list(500)
    for w in wos:
        results.append({
            'type': 'Work Order',
            'id': w.get('id'),
            'label': w.get('wo_number', ''),
            'sub': f"{w.get('model_code_snapshot', '')} · {w.get('qty', 0)} pcs · {w.get('status', '')}",
            'module': 'prod-work-orders',
        })

    # ── Customers ──────────────────────────────────────────────────────────
    customers = await db.rahaza_customers.find(
        {'$or': [{'code': regex}, {'name': regex}, {'phone': regex}, {'email': regex}]},
        {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'active': 1}
    ).limit(limit_per_type).to_list(500)
    for c in customers:
        results.append({
            'type': 'Pelanggan',
            'id': c.get('id'),
            'label': c.get('name', ''),
            'sub': c.get('code', ''),
            'module': 'mgmt-rahaza-customers',
        })

    # ── Materials ──────────────────────────────────────────────────────────
    materials = await db.rahaza_materials.find(
        {'$or': [{'code': regex}, {'name': regex}]},
        {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'type': 1, 'unit': 1}
    ).limit(limit_per_type).to_list(500)
    for m in materials:
        results.append({
            'type': 'Material',
            'id': m.get('id'),
            'label': m.get('name', ''),
            'sub': f"{m.get('code', '')} · {m.get('type', '')} ({m.get('unit', '')})",
            'module': 'wh-materials',
        })

    # ── Employees ──────────────────────────────────────────────────────────
    employees = await db.rahaza_employees.find(
        {'$or': [{'employee_code': regex}, {'name': regex}, {'phone': regex}]},
        {'_id': 0, 'id': 1, 'employee_code': 1, 'name': 1, 'role': 1, 'active': 1}
    ).limit(limit_per_type).to_list(500)
    for e in employees:
        results.append({
            'type': 'Karyawan',
            'id': e.get('id'),
            'label': e.get('name', ''),
            'sub': f"{e.get('employee_code', '')} · {e.get('role', '')}",
            'module': 'prod-employees',
        })

    # ── AR Invoices ────────────────────────────────────────────────────────
    ar = await db.rahaza_ar_invoices.find(
        {'$or': [{'invoice_number': regex}, {'customer_name': regex}]},
        {'_id': 0, 'id': 1, 'invoice_number': 1, 'customer_name': 1, 'total': 1, 'status': 1}
    ).limit(limit_per_type).to_list(500)
    for i in ar:
        results.append({
            'type': 'AR Invoice',
            'id': i.get('id'),
            'label': i.get('invoice_number', ''),
            'sub': f"{i.get('customer_name', '')} · {i.get('status', '')}",
            'module': 'fin-ar-invoices',
        })

    # ── AP Invoices ────────────────────────────────────────────────────────
    ap = await db.rahaza_ap_invoices.find(
        {'$or': [{'invoice_number': regex}, {'vendor_name': regex}]},
        {'_id': 0, 'id': 1, 'invoice_number': 1, 'vendor_name': 1, 'total': 1, 'status': 1}
    ).limit(limit_per_type).to_list(500)
    for i in ap:
        results.append({
            'type': 'AP Invoice',
            'id': i.get('id'),
            'label': i.get('invoice_number', ''),
            'sub': f"{i.get('vendor_name', '')} · {i.get('status', '')}",
            'module': 'fin-ap',  # routes to legacy AP module (Rahaza AP belum punya module dedicated)
        })

    # ── Lines ──────────────────────────────────────────────────────────────
    lines = await db.rahaza_lines.find(
        {'$or': [{'code': regex}, {'name': regex}]},
        {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'process_code': 1, 'active': 1}
    ).limit(limit_per_type).to_list(500)
    for l in lines:
        results.append({
            'type': 'Line Produksi',
            'id': l.get('id'),
            'label': l.get('code', ''),
            'sub': f"{l.get('name', '')} · {l.get('process_code', '')}",
            'module': 'prod-lines',
        })

    return {'results': results}


# ─── ATTACHMENTS ─────────────────────────────────────────────────────────────
@router.get("/attachments")
async def get_attachments(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    entity_type = sp.get('entity_type')
    entity_id = sp.get('entity_id')
    if not entity_type or not entity_id:
        raise HTTPException(400, 'entity_type and entity_id required')
    q = {'entity_type': entity_type, 'entity_id': entity_id}
    # Dual-mode: paginated or full list
    if sp.get('page') or sp.get('limit'):
        page, limit, skip = get_pagination_params(request, default_limit=20)
        total = await db.attachments.count_documents(q)
        items = await db.attachments.find(q, {'_id': 0}).sort('uploaded_at', -1).skip(skip).limit(limit).to_list(limit)
        return paginated_response(serialize_doc(items), total, page, limit)
    return serialize_doc(await db.attachments.find(q, {'_id': 0}).sort('uploaded_at', -1).to_list(500))

