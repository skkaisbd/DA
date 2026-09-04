"""PO Stage Tracking — ekstensi DA (dipertahankan saat adopsi SOMMERVILLE Fase 2).

Dipakai oleh panel aktif `POStageTrackingPanel.jsx` di RahazaOrdersModule.
Sumber asli: routes/_archive/pre_sommerville/production_po.py (GAP #3 + BUG-003).
Mendukung dua koleksi: production_pos DAN rahaza_orders.
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc
from core.helpers import now
from routes.production_rbac import deny_klien

STAGE_KEYWORDS = (
    ('rework', ('rework', 'revisi', 'permak', 'repair')),
    ('cutting', ('cut', 'potong')),
    ('sewing', ('jahit', 'sew', 'cmt', 'sewing')),
    ('qc', ('qc', 'quality', 'inspeksi')),
    ('packing', ('pack', 'kemas')),
    ('finishing', ('finish', 'setrika', 'steam')),
)

router = APIRouter(prefix="/api", tags=["production-stage-tracking"])


@router.put("/production-pos/{po_id}/stage-qty")
async def update_po_stage_qty(po_id: str, request: Request):
    """
    Input / update qty per tahap produksi untuk internal PO.
    stage: cutting | sewing | qc | packing
    Jika PO punya WO, data aktual diambil dari WIP events (real-time).
    Input manual di sini berlaku sebagai override/suplemen.
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    # BUG-003 fix: panel Stage Tracking juga dipakai oleh Order Produksi Rahaza
    # (koleksi rahaza_orders), bukan hanya production_pos. Cari di kedua koleksi.
    po = await db.production_pos.find_one({'id': po_id})
    po_collection = 'production_pos'
    if not po:
        po = await db.rahaza_orders.find_one({'id': po_id})
        po_collection = 'rahaza_orders'
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')

    body = await request.json()
    stage = body.get('stage')
    valid_stages = ['cutting', 'sewing', 'qc', 'packing']
    if stage not in valid_stages:
        raise HTTPException(400, f"stage harus salah satu dari: {valid_stages}")

    stage_qty = po.get('stage_qty') or {}

    if stage == 'cutting':
        if body.get('qty_in') is not None:
            stage_qty['cutting_input'] = max(0, int(body['qty_in']))
        if body.get('qty_out') is not None:
            stage_qty['cutting_output'] = max(0, int(body['qty_out']))
    elif stage == 'sewing':
        if body.get('qty_out') is not None:
            stage_qty['sewing_output'] = max(0, int(body['qty_out']))
    elif stage == 'qc':
        if body.get('qty_pass') is not None:
            stage_qty['qc_pass'] = max(0, int(body['qty_pass']))
        if body.get('qty_fail') is not None:
            stage_qty['qc_fail'] = max(0, int(body['qty_fail']))
    elif stage == 'packing':
        if body.get('qty_out') is not None:
            stage_qty['packing_output'] = max(0, int(body['qty_out']))

    await db[po_collection].update_one(
        {'id': po_id},
        {'$set': {'stage_qty': stage_qty, 'updated_at': now()}}
    )
    return {'message': f'Stage qty {stage} diperbarui', 'stage_qty': stage_qty}


@router.get("/production-pos/{po_id}/stage-summary")
async def get_po_stage_summary(po_id: str, request: Request):
    """
    Aggregated stage summary untuk PO:
    - Real data dari rahaza_wip_events (linked WOs)
    - Suplemen manual dari po.stage_qty
    Returns cutting/sewing/qc/packing summary.
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    # BUG-003 fix: dukung juga Order Produksi Rahaza (koleksi rahaza_orders)
    po = await db.production_pos.find_one({'id': po_id})
    po_source = 'production_pos'
    if not po:
        po = await db.rahaza_orders.find_one({'id': po_id})
        po_source = 'rahaza_orders'
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')

    # Sumber WIP ada DUA: WO engine lama (work_order_id) dan job produksi internal
    # (job_id, event_type='complete' — mirror HR-1). AUDIT 2026-09-03: dulu hanya WO
    # yang dibaca, padahal koleksi rahaza_work_orders tidak punya penulis lagi ⇒
    # ringkasan tahap selalu 0 dan jatuh ke angka manual.
    wo_ids_raw = await db.rahaza_work_orders.find(
        {'order_id': po_id, 'source': {'$ne': 'maklon'}},
        {'_id': 0, 'id': 1, 'qty': 1, 'status': 1}
    ).to_list(500)
    wo_ids = [w['id'] for w in wo_ids_raw]
    jobs = await db.production_jobs.find({'po_id': po_id}, {'_id': 0, 'id': 1}).to_list(500)
    job_ids = [j['id'] for j in jobs]
    job_qty = 0
    if job_ids:
        agg_q = await db.production_job_items.aggregate([
            {'$match': {'job_id': {'$in': job_ids}}},
            {'$group': {'_id': None, 'q': {'$sum': {'$ifNull': ['$available_qty', {'$ifNull': ['$shipment_qty', {'$ifNull': ['$ordered_qty', 0]}]}]}}}},
        ]).to_list(1)
        job_qty = int((agg_q[0]['q'] if agg_q else 0) or 0)
    total_wo_qty = sum(int(w.get('qty', 0)) for w in wo_ids_raw) + job_qty
    anchor = {'$or': [{'work_order_id': {'$in': wo_ids}}, {'job_id': {'$in': job_ids}},
                      {'production_po_id': po_id}]}

    # Aggregate from WIP events
    wip_summary = {'cutting_output': 0, 'sewing_output': 0, 'qc_pass': 0, 'qc_fail': 0, 'packing_output': 0}
    if wo_ids or job_ids:
        processes = await db.rahaza_processes.find(
            {'active': True}, {'_id': 0, 'id': 1, 'name': 1, 'order_seq': 1, 'process_type': 1}
        ).sort('order_seq', 1).to_list(500)
        proc_ids = [p['id'] for p in processes]

        if proc_ids:
            # Tahap dikenali dari process_type / nama proses — BUKAN posisi urutan
            # (dulu processes[0]=cutting & processes[-1]=sewing, padahal proses
            # terakhir bisa 'Rework/Revisi' atau 'Packing' — audit iteration_102).
            def _stage_of(p):
                for key in ((p.get('process_type') or '').lower(), (p.get('name') or '').lower()):
                    if not key:
                        continue
                    for stage, words in STAGE_KEYWORDS:
                        if any(w in key for w in words):
                            return stage
                return None

            pipe_base = [
                {'$match': {**anchor, 'event_type': {'$in': ['output', 'complete']}}},
                {'$group': {'_id': '$process_id', 'total': {'$sum': '$qty'}}}
            ]
            agg = await db.rahaza_wip_events.aggregate(pipe_base).to_list(500)
            by_proc = {r['_id']: r['total'] for r in agg}

            process_breakdown = []
            for p in processes:
                stage = _stage_of(p)
                qty_p = int(by_proc.get(p['id'], 0) or 0)
                process_breakdown.append({'process_id': p['id'], 'name': p.get('name'),
                                          'order_seq': p.get('order_seq'), 'stage': stage, 'qty': qty_p})
                if stage == 'cutting':
                    wip_summary['cutting_output'] += qty_p
                elif stage == 'sewing':
                    wip_summary['sewing_output'] += qty_p
                elif stage == 'packing':
                    wip_summary['packing_output'] += qty_p
            wip_summary['by_process'] = process_breakdown

            qc_pipe = [
                {'$match': {**anchor, 'event_type': {'$in': ['qc_pass', 'qc_fail']}}},
                {'$group': {'_id': '$event_type', 'total': {'$sum': '$qty'}}}
            ]
            qc_agg = await db.rahaza_wip_events.aggregate(qc_pipe).to_list(500)
            for r in qc_agg:
                if r['_id'] == 'qc_pass':
                    wip_summary['qc_pass'] = r['total']
                elif r['_id'] == 'qc_fail':
                    wip_summary['qc_fail'] = r['total']

    # Manual stage_qty from PO (used as override when WIP data unavailable)
    manual_sq = po.get('stage_qty') or {}

    def _pick(wip_key, manual_key):
        wip_val = wip_summary.get(wip_key, 0)
        manual_val = int(manual_sq.get(manual_key, 0))
        return wip_val if wip_val > 0 else manual_val

    # Items summary for each stage
    if po_source == 'rahaza_orders':
        qty_ordered = sum(int(it.get('qty', 0)) for it in (po.get('items') or []))
    else:
        items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(500)
        # po_items lama hanya menyimpan `qty` (adapter from-order), yang baru `qty_ordered` — baca keduanya.
        qty_ordered = sum(int(it.get('qty_ordered') or it.get('qty') or 0) for it in items)

    summary = {
        'po_id': po_id,
        'po_number': po.get('po_number') or po.get('order_number', ''),
        'status': po.get('status', ''),
        'qty_ordered': qty_ordered,
        'total_wo_qty': total_wo_qty,
        'wo_count': len(wo_ids_raw) + len(job_ids),
        'stage_qty': {
            'cutting_input':   int(manual_sq.get('cutting_input', 0)),
            'cutting_output':  _pick('cutting_output', 'cutting_output'),
            'sewing_output':   _pick('sewing_output', 'sewing_output'),
            'qc_pass':         _pick('qc_pass', 'qc_pass'),
            'qc_fail':         _pick('qc_fail', 'qc_fail'),
            'packing_output':  _pick('packing_output', 'packing_output'),
        },
        'by_process': wip_summary.get('by_process', []),
        'wip_data_available': bool(wo_ids or job_ids),
        'manual_stage_qty': manual_sq,
    }

    # Calculate progress %
    sq = summary['stage_qty']
    if qty_ordered > 0:
        if sq['packing_output'] >= qty_ordered:
            summary['progress_pct'] = 100
        elif sq['qc_pass'] > 0:
            summary['progress_pct'] = min(84, 70 + int((sq['qc_pass'] / qty_ordered) * 14))
        elif sq['sewing_output'] > 0:
            summary['progress_pct'] = min(69, 50 + int((sq['sewing_output'] / qty_ordered) * 19))
        elif sq['cutting_output'] > 0:
            summary['progress_pct'] = min(49, 30 + int((sq['cutting_output'] / qty_ordered) * 19))
        else:
            completed_wos = sum(1 for w in wo_ids_raw if w.get('status') == 'completed')
            summary['progress_pct'] = int((completed_wos / len(wo_ids_raw) * 100)) if wo_ids_raw else 0
    else:
        summary['progress_pct'] = 0

    return serialize_doc(summary)
