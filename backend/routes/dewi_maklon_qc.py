"""
CV. Dewi Aditya — Portal Maklon API Routes
Phase 3B: QC Tracking per Stage (cutting / sewing / final) + reject analytics

Collections:
- dewi_maklon_qc_checks: QC inspection records per maklon order stage
"""
from fastapi import APIRouter, HTTPException, Depends
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from auth import require_auth
from routes._maklon_adapter import legacy_orders_view as _lmo
import uuid

router = APIRouter(prefix='/api/dewi/maklon/qc', tags=['Dewi-Maklon-QC'], dependencies=[Depends(deny_external_dep)])
# ══════════════════════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════════════════════

QC_STAGES = ['raw_material', 'cutting', 'sewing', 'final', 'pre_packing']
QC_RESULTS = ['pending', 'pass', 'pass_with_notes', 'fail', 'rework']

class QCDefect(BaseModel):
    defect_code: Optional[str] = None
    description: str
    qty_affected: int = Field(default=1, ge=0)

class QCCheckIn(BaseModel):
    order_id: str = Field(..., description="Referensi ke dewi_maklon_orders.id")
    stage: str = Field(..., description=f"Salah satu: {QC_STAGES}")
    inspector_name: Optional[str] = None
    qty_inspected: int = Field(..., ge=0)
    qty_passed: int = Field(default=0, ge=0)
    qty_rejected: int = Field(default=0, ge=0)
    qty_rework: int = Field(default=0, ge=0)
    defects: List[QCDefect] = Field(default_factory=list)
    photos: List[str] = Field(default_factory=list)
    result: str = Field(default='pending')
    notes: Optional[str] = None


def _clean(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop('_id', None)
    return doc

def _calc_reject_rate(doc: dict) -> float:
    total = int(doc.get('qty_inspected') or 0)
    if total == 0:
        return 0.0
    rejected = int(doc.get('qty_rejected') or 0)
    return round((rejected / total) * 100, 2)


def _assert_qty_consistency(inspected, passed, rejected, rework):
    """R9-BUG-1 guard: qty_passed+qty_rejected+qty_rework tidak boleh melebihi qty_inspected."""
    if (int(passed) + int(rejected) + int(rework)) > int(inspected):
        raise HTTPException(400, "qty_passed + qty_rejected + qty_rework tidak boleh melebihi qty_inspected")

async def _get_reject_threshold(db) -> float:
    """Read reject threshold from system config, default 5%."""
    cfg = await db.dewi_system_config.find_one({'key': 'maklon_qc_reject_threshold_pct'})
    if cfg and cfg.get('value') is not None:
        try:
            return float(cfg['value'])
        except (ValueError, TypeError):
            return 5.0
    return 5.0

# ══════════════════════════════════════════════════════════════════════════════
# CRUD
# ══════════════════════════════════════════════════════════════════════════════

@router.get('')
async def list_qc(
    order_id: Optional[str] = None,
    stage: Optional[str] = None,
    result: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    db = get_db()
    query = {}
    if order_id:
        query['order_id'] = order_id
    if stage:
        query['stage'] = stage
    if result:
        query['result'] = result
    checks = await db.dewi_maklon_qc_checks.find(query).sort('inspected_at', -1).to_list(length=500)
    return [_clean(c) for c in checks]

@router.post('')
async def create_qc(payload: QCCheckIn, user: dict = Depends(require_auth)):
    # ─── K5 (Phase C) DEPRECATION ─────────────────────────────────────────
    # Stage-based maklon QC (dewi_maklon_qc_checks) is removed per K5. FG reject
    # is captured at DA CMT-receipt inspection (Phase B). Writes are disabled.
    raise HTTPException(410,
        'QC stage-based maklon di-deprekasi per K5 (Phase C). Reject FG dicatat '
        'saat DA menerima kiriman CMT (modul "Terima FG dari CMT").')
    db = get_db()
    if payload.stage not in QC_STAGES:
        raise HTTPException(400, f'Stage {payload.stage} tidak valid. Valid: {QC_STAGES}')
    if payload.result not in QC_RESULTS:
        raise HTTPException(400, f'Result {payload.result} tidak valid. Valid: {QC_RESULTS}')
    _assert_qty_consistency(payload.qty_inspected, payload.qty_passed, payload.qty_rejected, payload.qty_rework)

    order = await _lmo(db).find_one({'id': payload.order_id})
    if not order:
        raise HTTPException(400, 'Order maklon tidak ditemukan')

    now = datetime.now(timezone.utc)
    doc = payload.dict()
    doc['id'] = str(uuid.uuid4())
    doc['order_code'] = order.get('order_code')
    doc['client_name'] = order.get('client_name')
    doc['inspector_name'] = payload.inspector_name or user.get('name', 'System')
    doc['reject_rate_pct'] = _calc_reject_rate(doc)
    doc['inspected_at'] = now
    doc['created_at'] = now
    doc['updated_at'] = now
    doc['created_by'] = user.get('name', 'System')

    # Alert flag if reject rate exceeds threshold
    threshold = await _get_reject_threshold(db)
    doc['alert_triggered'] = doc['reject_rate_pct'] > threshold
    doc['alert_threshold_pct'] = threshold

    await db.dewi_maklon_qc_checks.insert_one(doc)
    return {
        'message': 'QC check dicatat',
        'id': doc['id'],
        'reject_rate_pct': doc['reject_rate_pct'],
        'alert_triggered': doc['alert_triggered'],
    }

@router.put('/{qc_id}')
async def update_qc(qc_id: str, payload: QCCheckIn, user: dict = Depends(require_auth)):
    # K5 (Phase C): DEPRECATED — stage-based maklon QC writes disabled. See "Terima FG dari CMT".
    raise HTTPException(410,
        'QC stage-based maklon di-deprekasi per K5 (Phase C). Reject FG dicatat '
        'saat DA menerima kiriman CMT (modul "Terima FG dari CMT").')
    db = get_db()
    existing = await db.dewi_maklon_qc_checks.find_one({'id': qc_id})
    if not existing:
        raise HTTPException(404, 'QC check tidak ditemukan')

    update_data = payload.dict(exclude_unset=True)
    update_data.pop('order_id', None)
    merged = {**existing, **update_data}
    _assert_qty_consistency(
        merged.get('qty_inspected') or 0, merged.get('qty_passed') or 0,
        merged.get('qty_rejected') or 0, merged.get('qty_rework') or 0,
    )
    update_data['reject_rate_pct'] = _calc_reject_rate(merged)
    threshold = await _get_reject_threshold(db)
    update_data['alert_triggered'] = update_data['reject_rate_pct'] > threshold
    update_data['alert_threshold_pct'] = threshold
    update_data['updated_at'] = datetime.now(timezone.utc)

    await db.dewi_maklon_qc_checks.update_one({'id': qc_id}, {'$set': update_data})
    return {'message': 'QC check diperbarui', 'reject_rate_pct': update_data['reject_rate_pct']}

@router.delete('/{qc_id}')
async def delete_qc(qc_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    result = await db.dewi_maklon_qc_checks.delete_one({'id': qc_id})
    if result.deleted_count == 0:
        raise HTTPException(404, 'QC check tidak ditemukan')
    return {'message': 'QC check dihapus'}

# ══════════════════════════════════════════════════════════════════════════════
# SUMMARY / ANALYTICS
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/summary/overview')
async def qc_summary(user: dict = Depends(require_auth)):
    """Overall QC stats across all maklon orders."""
    db = get_db()
    total = await db.dewi_maklon_qc_checks.count_documents({})

    # Aggregate totals
    pipeline = [
        {'$group': {
            '_id': None,
            'total_inspected': {'$sum': '$qty_inspected'},
            'total_passed': {'$sum': '$qty_passed'},
            'total_rejected': {'$sum': '$qty_rejected'},
            'total_rework': {'$sum': '$qty_rework'},
        }},
    ]
    agg = await db.dewi_maklon_qc_checks.aggregate(pipeline).to_list(1)
    totals = agg[0] if agg else {'total_inspected': 0, 'total_passed': 0, 'total_rejected': 0, 'total_rework': 0}
    totals.pop('_id', None)
    insp = totals.get('total_inspected', 0) or 0
    rej = totals.get('total_rejected', 0) or 0
    overall_reject_rate = round((rej / insp) * 100, 2) if insp > 0 else 0.0

    by_stage = {}
    for st in QC_STAGES:
        by_stage[st] = await db.dewi_maklon_qc_checks.count_documents({'stage': st})

    alerts = await db.dewi_maklon_qc_checks.count_documents({'alert_triggered': True})
    threshold = await _get_reject_threshold(db)

    return {
        'total_checks': total,
        **totals,
        'overall_reject_rate_pct': overall_reject_rate,
        'by_stage': by_stage,
        'alerts_count': alerts,
        'reject_threshold_pct': threshold,
    }

@router.get('/by-order/{order_id}')
async def qc_by_order(order_id: str, user: dict = Depends(require_auth)):
    """QC records + summary for a single order."""
    db = get_db()
    checks = await db.dewi_maklon_qc_checks.find({'order_id': order_id}).sort('inspected_at', -1).to_list(length=200)
    checks = [_clean(c) for c in checks]

    # Per-stage summary
    stages_summary = {}
    for c in checks:
        st = c.get('stage')
        if st not in stages_summary:
            stages_summary[st] = {
                'checks_count': 0, 'qty_inspected': 0, 'qty_passed': 0,
                'qty_rejected': 0, 'qty_rework': 0,
            }
        s = stages_summary[st]
        s['checks_count'] += 1
        s['qty_inspected'] += int(c.get('qty_inspected', 0) or 0)
        s['qty_passed'] += int(c.get('qty_passed', 0) or 0)
        s['qty_rejected'] += int(c.get('qty_rejected', 0) or 0)
        s['qty_rework'] += int(c.get('qty_rework', 0) or 0)

    for st, s in stages_summary.items():
        s['reject_rate_pct'] = round((s['qty_rejected'] / s['qty_inspected']) * 100, 2) if s['qty_inspected'] > 0 else 0.0

    return {
        'order_id': order_id,
        'checks': checks,
        'stages_summary': stages_summary,
        'total_checks': len(checks),
    }

@router.get('/defect-pareto')
async def defect_pareto(
    order_id: Optional[str] = None,
    stage: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """Pareto analysis on defects across all QC records."""
    db = get_db()
    query = {}
    if order_id:
        query['order_id'] = order_id
    if stage:
        query['stage'] = stage

    pipeline = [
        {'$match': query},
        {'$unwind': '$defects'},
        {'$group': {
            '_id': {
                'code': {'$ifNull': ['$defects.defect_code', 'UNCODED']},
                'description': '$defects.description',
            },
            'qty_total': {'$sum': '$defects.qty_affected'},
            'occurrences': {'$sum': 1},
        }},
        {'$sort': {'qty_total': -1}},
        {'$limit': 30},
    ]
    items = await db.dewi_maklon_qc_checks.aggregate(pipeline).to_list(length=30)

    total = sum(int(i.get('qty_total', 0) or 0) for i in items)
    cumulative = 0
    out = []
    for i in items:
        qty = int(i.get('qty_total', 0) or 0)
        cumulative += qty
        out.append({
            'defect_code': i['_id']['code'],
            'description': i['_id']['description'],
            'qty_total': qty,
            'occurrences': i['occurrences'],
            'pct_of_total': round((qty / total) * 100, 2) if total > 0 else 0,
            'cumulative_pct': round((cumulative / total) * 100, 2) if total > 0 else 0,
        })
    return {'total_defect_qty': total, 'items': out}

# ──────────────────────────────────────────────────────────────────────────────
# GENERIC ID-BASED ROUTES (must be LAST so static paths take precedence)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/{qc_id}')
async def get_qc(qc_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    check = await db.dewi_maklon_qc_checks.find_one({'id': qc_id})
    if not check:
        raise HTTPException(404, 'QC check tidak ditemukan')
    return _clean(check)