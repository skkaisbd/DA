"""
CV. Dewi Aditya — Production Control Tower (Aggregator)
Phase 28 — P2 Workflow Consolidation #3

Single dashboard untuk daily operations production manager:
- Work Orders status overview (draft, released, in_progress, completed, blocked, etc.)
- Maklon POs production progress
- CMT Receipts pending QC
- Critical alerts (deadline at risk, blocked WOs, overdue ones)
- Today's output vs target
- Capacity utilization snapshot

Endpoints:
- GET /api/prod/control-tower             — full aggregator
- GET /api/prod/control-tower/wo-list     — filtered WO list (by risk/status)
- GET /api/prod/control-tower/alerts      — critical alerts only
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta, date
from database import get_db
from auth import require_auth, serialize_doc
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/prod', tags=['Production-Control-Tower'])

# WO terminal states (no longer active)
WO_TERMINAL = ('completed', 'cancelled', 'closed')
WO_ACTIVE = ('draft', 'released', 'in_progress', 'paused', 'on_hold', 'qc_pending', 'finishing')


async def _load_active_wos(db, extra_filter: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """SUMBER DATA Pusat Kendali = `production_jobs` (alur Produksi Internal yang nyata).

    AUDIT 2026-09-03: layar ini dulu membaca `rahaza_work_orders` — koleksi engine
    multi-stage yang sudah DIHAPUS (FASE 4) dan tidak punya satu pun penulis lagi.
    Akibatnya Pusat Kendali selalu 0 walau PO/job berjalan. Kini job diperkaya lewat
    `_enrich_jobs` yang sama dengan Tracking Produksi, lalu dipetakan ke bentuk "WO"
    yang sudah dipakai layar (wo_number/client_name/qty/qty_produced/deadline/status).
    """
    from routes.production_execution import _enrich_jobs
    from core.production_job_lifecycle import JOB_CLOSED_STATUSES
    q: Dict[str, Any] = {'parent_job_id': {'$in': [None, '']}, **(extra_filter or {})}
    jobs = await db.production_jobs.find(q, {'_id': 0}).sort('created_at', -1).to_list(2000)
    jobs = [j for j in jobs if not j.get('parent_job_id')]
    enriched = await _enrich_jobs(db, jobs)
    po_ids = list({j.get('po_id') for j in enriched if j.get('po_id')})
    pos = await db.production_pos.find({'id': {'$in': po_ids}}, {'_id': 0, 'id': 1, 'deadline': 1,
                                                                'delivery_deadline': 1, 'status': 1}).to_list(None) if po_ids else []
    po_map = {p['id']: p for p in pos}
    out = []
    for j in enriched:
        raw_status = str(j.get('status') or 'Open')
        closed = raw_status in JOB_CLOSED_STATUSES or raw_status.lower() in WO_TERMINAL
        po = po_map.get(j.get('po_id') or '', {})
        out.append({
            'id': j.get('id'),
            'wo_number': j.get('job_number') or j.get('id'),
            'po_id': j.get('po_id'),
            'po_number': j.get('po_number'),
            'client_name': j.get('vendor_name') or 'Produksi Internal',
            'source': 'internal' if (j.get('business_type') or 'internal') == 'internal' else 'maklon',
            'status': 'completed' if closed else ('in_progress' if (j.get('total_produced') or 0) > 0 else 'released'),
            'raw_status': raw_status,
            'qty': j.get('total_available') or j.get('total_ordered') or 0,
            'qty_produced': j.get('total_produced') or 0,
            'qty_shipped': j.get('total_shipped_to_buyer') or 0,
            'deadline': j.get('deadline') or j.get('delivery_deadline') or po.get('deadline') or po.get('delivery_deadline'),
            'completed_at': j.get('completed_at') or j.get('updated_at'),
            'created_at': j.get('created_at'),
        })
    return out


def _today_iso() -> str:
    return date.today().isoformat()


def _parse_date(s: Optional[str]) -> Optional[date]:
    """Normalisasi APA PUN menjadi `datetime.date` murni (atau None).

    BUG-4 (FASE 11) — `datetime` adalah SUBCLASS `date`; cek `datetime` HARUS
    didahulukan, kalau tidak objek BSON datetime lolos apa adanya dan
    perbandingan `datetime` vs `date` melempar TypeError → HTTP 500.
    """
    if not s:
        return None
    try:
        if isinstance(s, datetime):      # WAJIB dicek sebelum `date`
            return s.date()
        if isinstance(s, date):
            return s
        return date.fromisoformat(str(s)[:10])
    except Exception:
        return None


def _wo_progress_pct(wo: Dict[str, Any]) -> float:
    qty = float(wo.get('qty', 0) or 0)
    produced = float(wo.get('qty_produced', 0) or 0)
    if qty <= 0:
        return 0.0
    return round((produced / qty) * 100, 1)


def _wo_days_until_deadline(wo: Dict[str, Any]) -> Optional[int]:
    dl = _parse_date(wo.get('deadline'))
    if not dl:
        return None
    return (dl - date.today()).days


def _wo_risk_status(wo: Dict[str, Any]) -> str:
    """
    Compute risk status for an active WO:
      'overdue'    → deadline already passed
      'at_risk'    → < 5 days to deadline AND progress < 70%
      'on_track'   → all good
      'unknown'    → no deadline
    Terminal WOs always return 'completed' or 'cancelled'.
    """
    status = (wo.get('status') or '').lower()
    if status in WO_TERMINAL:
        return status
    days = _wo_days_until_deadline(wo)
    progress = _wo_progress_pct(wo)
    if days is None:
        return 'unknown'
    if days < 0:
        return 'overdue'
    if days <= 5 and progress < 70:
        return 'at_risk'
    if days <= 2:
        return 'at_risk'
    return 'on_track'


# ─────────────────────────────────────────────────────────────────────────────
# Main Aggregator
# ─────────────────────────────────────────────────────────────────────────────
@router.get('/control-tower')
async def control_tower(
    days_window: int = Query(7, ge=1, le=60, description='Today output window in days'),
    user: dict = Depends(require_auth),
):
    """
    Single-call aggregator for Production Control Tower dashboard.

    Returns all KPIs + critical lists in one response.
    """
    db = get_db()
    today = date.today()
    today_iso = today.isoformat()
    win_start = (today - timedelta(days=days_window)).isoformat()

    # ── Active Work Orders (= production_jobs induk yang belum selesai) ─────
    all_wos = await _load_active_wos(db)
    active_wos = [w for w in all_wos if w['status'] not in WO_TERMINAL]
    total_active = len(active_wos)

    status_count: Dict[str, int] = {}
    risk_count: Dict[str, int] = {'on_track': 0, 'at_risk': 0, 'overdue': 0, 'unknown': 0}
    total_target_qty = 0
    total_produced_qty = 0
    enriched_active: List[Dict[str, Any]] = []

    for wo in active_wos:
        s = (wo.get('status') or '').lower() or 'draft'
        status_count[s] = status_count.get(s, 0) + 1

        risk = _wo_risk_status(wo)
        if risk in risk_count:
            risk_count[risk] += 1

        target = int(wo.get('qty', 0) or 0)
        produced = int(wo.get('qty_produced', 0) or 0)
        total_target_qty += target
        total_produced_qty += produced

        enriched_active.append({
            **wo,
            'progress_pct': _wo_progress_pct(wo),
            'days_to_deadline': _wo_days_until_deadline(wo),
            'risk_status': risk,
        })

    # ── Today output (job selesai hari ini / dalam jendela) ─────────────────
    def _done_since(w, since_iso):
        d = _parse_date(w.get('completed_at'))
        return w['status'] in WO_TERMINAL and d is not None and d.isoformat() >= since_iso
    today_completed_count = sum(1 for w in all_wos if _done_since(w, today_iso))
    last_week_completed = sum(1 for w in all_wos if _done_since(w, win_start))

    # ── Maklon PO progress aggregation ──────────────────────────────────────
    maklon_pos = await db.dewi_maklon_pos.find(
        {'status': {'$in': ['confirmed', 'in_production', 'partial_delivered']}},
        {'_id': 0}
    ).to_list(length=500)
    maklon_progress = []
    total_maklon_target = 0
    total_maklon_produced = 0
    for po in maklon_pos:
        total_qty = int(po.get('total_qty', 0) or 0)
        items = po.get('items') or []
        produced = sum(int(it.get('qty_produced', 0) or 0) for it in items)
        total_maklon_target += total_qty
        total_maklon_produced += produced
        progress = round((produced / total_qty) * 100, 1) if total_qty > 0 else 0
        maklon_progress.append({
            'id': po['id'],
            'po_number': po.get('po_number'),
            'client_name': po.get('client_name'),
            'status': po.get('status'),
            'deadline': po.get('deadline'),
            'days_to_deadline': _wo_days_until_deadline(po),
            'total_qty': total_qty,
            'qty_produced': produced,
            'progress_pct': progress,
            'risk_status': _wo_risk_status({**po, 'qty': total_qty, 'qty_produced': produced}),
        })

    # ── CMT Receipts pending review ─────────────────────────────────────────
    cmt_pending = await db.cmt_receipts.count_documents(
        {'status': {'$in': ['submitted', 'pending_approval', 'in_review']}}
    )
    cmt_today = await db.cmt_receipts.count_documents({
        'created_at': {'$gte': datetime.fromisoformat(f'{today_iso}T00:00:00')}
    })

    # ── Bundles: engine bundel sudah dihapus (FASE 4) — tidak ada yang perlu dicetak.
    bundle_pending_print = 0

    # ── Critical alerts ─────────────────────────────────────────────────────
    overdue_list = sorted(
        [w for w in enriched_active if w['risk_status'] == 'overdue'],
        key=lambda x: (x.get('deadline') or '')
    )[:10]
    at_risk_list = sorted(
        [w for w in enriched_active if w['risk_status'] == 'at_risk'],
        key=lambda x: (x.get('days_to_deadline') if x.get('days_to_deadline') is not None else 999)
    )[:10]

    alerts_count = len(overdue_list) + len(at_risk_list) + cmt_pending

    # ── Maklon PO timeline / 'starting soon' ────────────────────────────────
    upcoming_deadline_pos = sorted(
        [m for m in maklon_progress if m.get('days_to_deadline') is not None and m['days_to_deadline'] <= 14],
        key=lambda x: x['days_to_deadline'] or 999
    )[:10]

    # ── Overall progress ────────────────────────────────────────────────────
    overall_progress_pct = round((total_produced_qty / total_target_qty) * 100, 1) if total_target_qty > 0 else 0

    response = {
        'as_of': datetime.now(timezone.utc).isoformat(),
        'kpis': {
            'active_wos': total_active,
            'today_completed_wos': today_completed_count,
            'window_completed_wos': last_week_completed,
            'window_days': days_window,
            'total_target_qty': total_target_qty,
            'total_produced_qty': total_produced_qty,
            'overall_progress_pct': overall_progress_pct,
            'on_track': risk_count['on_track'],
            'at_risk': risk_count['at_risk'],
            'overdue': risk_count['overdue'],
            'unknown_deadline': risk_count['unknown'],
            'maklon_active_pos': len(maklon_progress),
            'maklon_target_qty': total_maklon_target,
            'maklon_produced_qty': total_maklon_produced,
            'maklon_progress_pct': round((total_maklon_produced / total_maklon_target) * 100, 1) if total_maklon_target > 0 else 0,
            'cmt_pending_review': cmt_pending,
            'cmt_received_today': cmt_today,
            'bundles_pending_print': bundle_pending_print,
            'total_alerts': alerts_count,
        },
        'wo_status_breakdown': status_count,
        'overdue_wos': serialize_doc(overdue_list),
        'at_risk_wos': serialize_doc(at_risk_list),
        # Semua WO aktif (termasuk on_track / tanpa deadline) supaya angka Active WOs
        # bisa direkonsiliasi di layar (audit iteration_102).
        'all_active_wos': serialize_doc(sorted(
            enriched_active,
            key=lambda x: ({'overdue': 0, 'at_risk': 1, 'unknown': 2, 'on_track': 3}.get(x['risk_status'], 9),
                           x.get('deadline') or '9999'))),
        'maklon_progress': serialize_doc(maklon_progress[:20]),
        'upcoming_deadlines': serialize_doc(upcoming_deadline_pos),
    }
    return response


@router.get('/control-tower/wo-list')
async def control_tower_wo_list(
    risk: Optional[str] = Query(None, description='Filter: on_track|at_risk|overdue|unknown'),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description='maklon|toko|generic'),
    limit: int = Query(100, ge=1, le=500),
    user: dict = Depends(require_auth),
):
    """
    Filtered active WO list for the Control Tower table.
    """
    db = get_db()
    extra: Dict[str, Any] = {}
    if source in ('internal',):
        extra['business_type'] = 'internal'
    elif source in ('maklon', 'toko', 'generic'):
        extra['business_type'] = {'$ne': 'internal'}
    wos = [w for w in await _load_active_wos(db, extra) if w['status'] not in WO_TERMINAL]
    if status:
        wos = [w for w in wos if w['status'] == status]
    wos.sort(key=lambda w: (w.get('deadline') is None, str(w.get('deadline') or '')))
    enriched = []
    for wo in wos[:limit]:
        item = {
            **wo,
            'progress_pct': _wo_progress_pct(wo),
            'days_to_deadline': _wo_days_until_deadline(wo),
            'risk_status': _wo_risk_status(wo),
        }
        if risk and item['risk_status'] != risk:
            continue
        enriched.append(item)
    return {'total': len(enriched), 'items': serialize_doc(enriched)}


@router.get('/control-tower/alerts')
async def control_tower_alerts(user: dict = Depends(require_auth)):
    """Just the critical alerts (overdue + at_risk + cmt_pending) — for header notification bell."""
    db = get_db()
    wos = [w for w in await _load_active_wos(db) if w['status'] not in WO_TERMINAL]
    overdue = []
    at_risk = []
    for wo in wos:
        risk = _wo_risk_status(wo)
        if risk == 'overdue':
            overdue.append({
                'wo_id': wo['id'],
                'wo_number': wo.get('wo_number'),
                'days_overdue': abs(_wo_days_until_deadline(wo) or 0),
                'client_name': wo.get('client_name'),
                'progress_pct': _wo_progress_pct(wo),
            })
        elif risk == 'at_risk':
            at_risk.append({
                'wo_id': wo['id'],
                'wo_number': wo.get('wo_number'),
                'days_to_deadline': _wo_days_until_deadline(wo),
                'client_name': wo.get('client_name'),
                'progress_pct': _wo_progress_pct(wo),
            })
    cmt_pending = await db.cmt_receipts.count_documents(
        {'status': {'$in': ['submitted', 'pending_approval', 'in_review']}}
    )
    return {
        'total': len(overdue) + len(at_risk) + cmt_pending,
        'overdue': overdue,
        'at_risk': at_risk,
        'cmt_pending_review': cmt_pending,
    }
