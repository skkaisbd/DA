"""
operations_serials.py — Serial Number Tracking & Lifecycle Timeline
Endpoints: /api/serial-list, /api/serial-trace

Refactored: Session #12 P2 (split from operations.py 2580 LOC monolith)
"""
import re
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc

router = APIRouter(prefix="/api", tags=["serial-tracking"])


# ─── SERIAL TRACKING TIMELINE ───────────────────────────────────────────────
@router.get("/serial-list")
async def serial_list(request: Request):
    """Get list of all serial numbers with status info."""
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    search = sp.get('search', '').strip()
    status_filter = sp.get('status', '')  # ongoing, completed, all
    # Build query
    query = {}
    if search:
        query['serial_number'] = {'$regex': re.escape(search), '$options': 'i'}
    if user.get('role') == 'vendor':
        # Only show serials for vendor's POs
        vendor_pos = await db.production_pos.find({'vendor_id': user.get('vendor_id')}, {'id': 1}).to_list(500)
        vendor_po_ids = [p['id'] for p in vendor_pos]
        query['po_id'] = {'$in': vendor_po_ids}
    po_items = await db.po_items.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)
    result = []
    if not po_items:
        return []

    # ── Batch prefetch all related docs ──
    po_ids_list = list({it.get('po_id') for it in po_items if it.get('po_id')})
    po_map = {}
    if po_ids_list:
        async for po in db.production_pos.find({'id': {'$in': po_ids_list}}, {'_id': 0}):
            po_map[po['id']] = po
    item_ids = [it['id'] for it in po_items]
    ji_by_poi = {}
    if item_ids:
        async for ji in db.production_job_items.find({'po_item_id': {'$in': item_ids}}):
            ji_by_poi.setdefault(ji['po_item_id'], []).append(ji)
    # Orphan by (sku, size, color) triple
    triples = list({(it.get('sku', ''), it.get('size', ''), it.get('color', '')) for it in po_items})
    orphan_lookup = {}
    if triples:
        skus = list({t[0] for t in triples})
        sizes = list({t[1] for t in triples})
        colors = list({t[2] for t in triples})
        async for oji in db.production_job_items.find({
            '$or': [{'po_item_id': None}, {'po_item_id': ''}, {'po_item_id': {'$exists': False}}],
            'sku': {'$in': skus}, 'size': {'$in': sizes}, 'color': {'$in': colors},
        }):
            key = (oji.get('sku', ''), oji.get('size', ''), oji.get('color', ''))
            orphan_lookup.setdefault(key, []).append(oji)
    bsi_by_poi = {}
    if item_ids:
        async for b in db.buyer_shipment_items.find({'po_item_id': {'$in': item_ids}}):
            bsi_by_poi.setdefault(b['po_item_id'], []).append(b)
    vsi_by_poi = {}
    all_vsi = []
    if item_ids:
        async for v in db.vendor_shipment_items.find({'po_item_id': {'$in': item_ids}}):
            vsi_by_poi.setdefault(v['po_item_id'], []).append(v)
            all_vsi.append(v)
    # Inspection items keyed by shipment_item_id (batch $in)
    insp_item_by_vsi_id = {}
    vsi_ids = [v['id'] for v in all_vsi]
    if vsi_ids:
        async for ii in db.vendor_material_inspection_items.find(
            {'shipment_item_id': {'$in': vsi_ids}}
        ):
            insp_item_by_vsi_id[ii['shipment_item_id']] = ii

    for item in po_items:
        if not item.get('serial_number'):
            continue
        po = po_map.get(item.get('po_id'))
        ji_list = ji_by_poi.get(item['id'], [])
        produced = sum(j.get('produced_qty', 0) for j in ji_list)
        counted_ids = {j['id'] for j in ji_list}
        triple_key = (item.get('sku', ''), item.get('size', ''), item.get('color', ''))
        for oji in orphan_lookup.get(triple_key, []):
            if oji['id'] not in counted_ids:
                produced += oji.get('produced_qty', 0)
        bi_list = bsi_by_poi.get(item['id'], [])
        shipped = sum(b.get('qty_shipped', 0) for b in bi_list)
        ordered = item.get('qty', 0)
        remaining = max(0, ordered - shipped)
        if shipped >= ordered:
            serial_status = 'completed'
        elif produced > 0 or ji_list:
            serial_status = 'ongoing'
        else:
            serial_status = 'pending'
        if status_filter and status_filter != 'all' and serial_status != status_filter:
            continue
        received_qty = 0
        for vsi in vsi_by_poi.get(item['id'], []):
            insp = insp_item_by_vsi_id.get(vsi['id'])
            if insp:
                received_qty += insp.get('received_qty', 0)
            else:
                received_qty += vsi.get('qty_sent', 0)
        result.append({
            'serial_number': item.get('serial_number'),
            'po_number': (po or {}).get('po_number', ''),
            'po_id': item.get('po_id'),
            'customer_name': (po or {}).get('customer_name', ''),
            'vendor_name': (po or {}).get('vendor_name', ''),
            'product_name': item.get('product_name', ''),
            'sku': item.get('sku', ''),
            'size': item.get('size', ''),
            'color': item.get('color', ''),
            'ordered_qty': ordered,
            'received_qty': received_qty,
            'produced_qty': produced,
            'shipped_qty': shipped,
            'remaining_qty': remaining,
            'status': serial_status,
            'po_status': (po or {}).get('status', ''),
            'deadline': serialize_doc((po or {}).get('deadline')),
        })
    return result

@router.get("/serial-trace")
async def serial_trace(request: Request):
    """Get full lifecycle timeline + PO-wide summary for a serial number.

    REFACTORED (Phase 3.6): batch-prefetch pattern eliminates ~10 N+1 queries.
    Behavior-preserved via golden-master byte-match regression test.

    Strategy:
      - Fetch each layer in 1 bulk $in query, keyed by id/foreign_key.
      - Composite-key maps (inspection_id, shipment_item_id) built in Python.
      - Orphan job-item lookup via bulk sku/size/color $in, filtered in-memory.
      - Preserves double-counting behavior for items sharing same
        (sku, size, color) triple (existing logic — change only if bug fix).
    """
    await require_auth(request)
    db = get_db()
    serial = request.query_params.get('serial', '').strip()
    if not serial:
        raise HTTPException(400, 'serial parameter required')

    timeline = []

    # ── 1. Entry point: po_items with the searched serial ──
    po_items = await db.po_items.find({'serial_number': serial}, {'_id': 0}).to_list(500)
    po_ids = list({pi.get('po_id') for pi in po_items if pi.get('po_id')})
    po_item_ids = [pi['id'] for pi in po_items]

    # ── 2. Fetch ALL POs and ALL their items in batched queries ──
    po_details = {}
    if po_ids:
        async for po in db.production_pos.find({'id': {'$in': po_ids}}, {'_id': 0}):
            po_details[po['id']] = po
    all_po_items = []
    if po_ids:
        async for it in db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}):
            all_po_items.append(it)
    all_po_item_ids = [pi['id'] for pi in all_po_items]

    # ── 3. Batch prefetch maps for summary computation ──
    ji_by_poi = {}
    if all_po_item_ids:
        async for ji in db.production_job_items.find({'po_item_id': {'$in': all_po_item_ids}}):
            ji_by_poi.setdefault(ji['po_item_id'], []).append(ji)

    # Orphan job-items: no po_item_id, match by (sku, size, color) triple
    triples = list({(it.get('sku', ''), it.get('size', ''), it.get('color', ''))
                     for it in all_po_items})
    orphan_lookup = {}
    if triples:
        skus = list({t[0] for t in triples})
        sizes = list({t[1] for t in triples})
        colors = list({t[2] for t in triples})
        async for oji in db.production_job_items.find({
            '$or': [{'po_item_id': None}, {'po_item_id': ''}, {'po_item_id': {'$exists': False}}],
            'sku': {'$in': skus}, 'size': {'$in': sizes}, 'color': {'$in': colors},
        }):
            key = (oji.get('sku', ''), oji.get('size', ''), oji.get('color', ''))
            orphan_lookup.setdefault(key, []).append(oji)

    bsi_by_poi = {}
    if all_po_item_ids:
        async for bi in db.buyer_shipment_items.find({'po_item_id': {'$in': all_po_item_ids}}, {'_id': 0}).sort('dispatch_seq', 1):
            bsi_by_poi.setdefault(bi['po_item_id'], []).append(bi)

    # ── 4. Build summary for ALL items in the PO ──
    summary_items = []
    totals = {'ordered': 0, 'produced': 0, 'shipped': 0, 'not_produced': 0, 'not_shipped': 0}
    vendors_set = set()
    buyer_names = set()
    for item in all_po_items:
        po = po_details.get(item.get('po_id'), {})
        vendors_set.add(po.get('vendor_name', ''))
        buyer_names.add(po.get('customer_name', ''))
        ji_list = ji_by_poi.get(item['id'], [])
        produced = sum(j.get('produced_qty', 0) for j in ji_list)
        # Preserve existing behavior: add orphan ji produced for matching triple
        # (note: if multiple items share same triple, orphan contributes to each)
        counted_ids = {j['id'] for j in ji_list}
        triple_key = (item.get('sku', ''), item.get('size', ''), item.get('color', ''))
        for oji in orphan_lookup.get(triple_key, []):
            if oji['id'] not in counted_ids:
                produced += oji.get('produced_qty', 0)
        bi_list = bsi_by_poi.get(item['id'], [])
        shipped = sum(b.get('qty_shipped', 0) for b in bi_list)
        ordered = item.get('qty', 0)
        summary_items.append({
            'po_item_id': item['id'], 'serial_number': item.get('serial_number', ''),
            'product_name': item.get('product_name', ''), 'sku': item.get('sku', ''),
            'size': item.get('size', ''), 'color': item.get('color', ''),
            'ordered_qty': ordered, 'produced_qty': produced, 'shipped_qty': shipped,
            'not_produced': max(0, ordered - produced), 'not_shipped': max(0, ordered - shipped),
            'is_searched_serial': item.get('serial_number') == serial,
            'po_number': item.get('po_number', po.get('po_number', ''))
        })
        totals['ordered'] += ordered
        totals['produced'] += produced
        totals['shipped'] += shipped
    totals['not_produced'] = max(0, totals['ordered'] - totals['produced'])
    totals['not_shipped'] = max(0, totals['ordered'] - totals['shipped'])

    # ── 5. Timeline events ONLY for searched-serial po_items ──
    # Prefetch all layers keyed on searched po_item_ids
    vsi_by_poi_searched = {}
    if po_item_ids:
        async for si in db.vendor_shipment_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}):
            vsi_by_poi_searched.setdefault(si['po_item_id'], []).append(si)
    all_ship_ids = list({si.get('shipment_id') for arr in vsi_by_poi_searched.values()
                          for si in arr if si.get('shipment_id')})
    ship_map = {}
    if all_ship_ids:
        async for sh in db.vendor_shipments.find({'id': {'$in': all_ship_ids}}, {'_id': 0}):
            ship_map[sh['id']] = sh
    insp_by_ship = {}
    if all_ship_ids:
        async for ins in db.vendor_material_inspections.find({'shipment_id': {'$in': all_ship_ids}}):
            insp_by_ship[ins['shipment_id']] = ins
    insp_items_lookup = {}
    insp_ids = [i['id'] for i in insp_by_ship.values()]
    if insp_ids:
        async for ii in db.vendor_material_inspection_items.find({'inspection_id': {'$in': insp_ids}}):
            insp_items_lookup[(ii.get('inspection_id'), ii.get('shipment_item_id'))] = ii
    # job items for searched po_items (already in ji_by_poi, but raw not with _id stripped there)
    ji_searched_by_poi = {}
    if po_item_ids:
        async for ji in db.production_job_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}):
            ji_searched_by_poi.setdefault(ji['po_item_id'], []).append(ji)
    job_map = {}
    all_job_ids_searched = list({j.get('job_id') for arr in ji_searched_by_poi.values() for j in arr if j.get('job_id')})
    if all_job_ids_searched:
        async for jb in db.production_jobs.find({'id': {'$in': all_job_ids_searched}}, {'_id': 0}):
            job_map[jb['id']] = jb
    # progress — keyed by job_item id; we need _id-inclusive docs (original code
    # accessed ji['id'] from the raw loop result, so re-fetch preserves parity)
    progress_by_ji = {}
    ji_full_by_poi = {}
    if po_item_ids:
        async for ji in db.production_job_items.find({'po_item_id': {'$in': po_item_ids}}):
            ji_full_by_poi.setdefault(ji['po_item_id'], []).append(ji)
    all_ji_ids_full = [j['id'] for arr in ji_full_by_poi.values() for j in arr]
    if all_ji_ids_full:
        async for p in db.production_progress.find(
            {'job_item_id': {'$in': all_ji_ids_full}}, {'_id': 0}
        ).sort('progress_date', 1):
            progress_by_ji.setdefault(p['job_item_id'], []).append(p)
    # buyer_shipment_items for searched po_items (already prefetched globally, reuse)
    # buyer_shipments
    bship_ids = list({b.get('shipment_id') for poi in po_item_ids for b in bsi_by_poi.get(poi, []) if b.get('shipment_id')})
    bship_map = {}
    if bship_ids:
        async for bs in db.buyer_shipments.find({'id': {'$in': bship_ids}}, {'_id': 0}):
            bship_map[bs['id']] = bs
    # production_returns
    ret_items_by_poi = {}
    if po_item_ids:
        async for ri in db.production_return_items.find({'po_item_id': {'$in': po_item_ids}}, {'_id': 0}):
            ret_items_by_poi.setdefault(ri['po_item_id'], []).append(ri)
    ret_ids = list({r.get('return_id') for arr in ret_items_by_poi.values() for r in arr if r.get('return_id')})
    ret_map = {}
    if ret_ids:
        async for r in db.production_returns.find({'id': {'$in': ret_ids}}, {'_id': 0}):
            ret_map[r['id']] = r

    # ── Build timeline events (order matches original for output parity) ──
    # 5a. PO Created
    for pi in po_items:
        po = po_details.get(pi.get('po_id'), {})
        timeline.append({
            'step': 'PO Created', 'event': 'PO Dibuat',
            'details': f"PO {po.get('po_number','')} - {pi.get('product_name','')} ({pi.get('sku','')}) x{pi.get('qty',0)}",
            'date': serialize_doc(pi.get('created_at')),
            'module': 'production-po', 'po_number': pi.get('po_number'),
            'po_item_id': pi['id'], 'qty': pi.get('qty', 0),
            'sku': pi.get('sku'), 'size': pi.get('size'), 'color': pi.get('color'),
            'customer_name': po.get('customer_name', ''),
            'vendor_name': po.get('vendor_name', ''), 'status': po.get('status', '')
        })
    # 5b. Vendor Shipments
    for poi_id in po_item_ids:
        for si in vsi_by_poi_searched.get(poi_id, []):
            ship = ship_map.get(si.get('shipment_id'))
            ship_type = (ship or {}).get('shipment_type', 'NORMAL')
            ship_num = (ship or {}).get('shipment_number', '')
            timeline.append({
                'step': f"Vendor Shipment ({ship_type})",
                'event': f"Pengiriman Vendor ({ship_type})",
                'details': f"Shipment {ship_num} - dikirim {si.get('qty_sent', 0)} pcs",
                'date': serialize_doc((ship or {}).get('shipment_date', si.get('created_at'))),
                'module': 'vendor-shipments', 'shipment_number': ship_num,
                'qty_sent': si.get('qty_sent', 0), 'status': (ship or {}).get('status', ''),
                'inspection_status': (ship or {}).get('inspection_status', 'Pending')
            })
    # 5c. Material Inspection
    for poi_id in po_item_ids:
        for si in vsi_by_poi_searched.get(poi_id, []):
            insp = insp_by_ship.get(si.get('shipment_id'))
            if insp:
                ii = insp_items_lookup.get((insp['id'], si['id']))
                if ii:
                    timeline.append({
                        'step': 'Material Inspection',
                        'event': 'Inspeksi Material',
                        'details': f"Diterima: {ii.get('received_qty', 0)}, Missing: {ii.get('missing_qty', 0)}, Defect: {ii.get('defect_qty', 0)}",
                        'date': serialize_doc(insp.get('inspection_date')),
                        'module': 'inspections', 'received_qty': ii.get('received_qty', 0),
                        'missing_qty': ii.get('missing_qty', 0),
                        'condition_notes': ii.get('condition_notes', '')
                    })
    # 5d. Production Jobs
    for poi_id in po_item_ids:
        for ji in ji_searched_by_poi.get(poi_id, []):
            job = job_map.get(ji.get('job_id'))
            timeline.append({
                'step': 'Production Job',
                'event': 'Job Produksi Dibuat',
                'details': f"Job {(job or {}).get('job_number', '')} - tersedia {ji.get('available_qty', 0)} pcs, diproduksi {ji.get('produced_qty', 0)} pcs",
                'date': serialize_doc(ji.get('created_at')),
                'module': 'production-jobs', 'job_number': (job or {}).get('job_number', ''),
                'available_qty': ji.get('available_qty', 0),
                'produced_qty': ji.get('produced_qty', 0),
                'status': (job or {}).get('status', '')
            })
    # 5e. Production Progress
    for poi_id in po_item_ids:
        for ji in ji_full_by_poi.get(poi_id, []):
            for p in progress_by_ji.get(ji['id'], []):
                timeline.append({
                    'step': 'Production Progress',
                    'event': 'Progres Produksi',
                    'details': f"Selesai {p.get('completed_quantity', 0)} pcs - {p.get('notes', '')}",
                    'date': serialize_doc(p.get('progress_date')),
                    'module': 'production-progress',
                    'completed_quantity': p.get('completed_quantity', 0),
                    'notes': p.get('notes', ''), 'recorded_by': p.get('recorded_by', '')
                })
    # 5f. Buyer Dispatch
    for poi_id in po_item_ids:
        for bi in bsi_by_poi.get(poi_id, []):
            bs = bship_map.get(bi.get('shipment_id'))
            timeline.append({
                'step': f"Buyer Dispatch #{bi.get('dispatch_seq', 1)}",
                'event': f"Pengiriman ke Buyer #{bi.get('dispatch_seq', 1)}",
                'details': f"Shipment {(bs or {}).get('shipment_number', '')} - dikirim {bi.get('qty_shipped', 0)} pcs",
                'date': serialize_doc(bi.get('dispatch_date', bi.get('created_at'))),
                'module': 'buyer-shipments', 'shipment_number': (bs or {}).get('shipment_number', ''),
                'qty_shipped': bi.get('qty_shipped', 0), 'ordered_qty': bi.get('ordered_qty', 0)
            })
    # 5g. Production Return
    for poi_id in po_item_ids:
        for ri in ret_items_by_poi.get(poi_id, []):
            ret = ret_map.get(ri.get('return_id'))
            timeline.append({
                'step': 'Production Return',
                'event': 'Retur Produksi',
                'details': f"Return {(ret or {}).get('return_number', '')} - {ri.get('return_qty', 0)} pcs",
                'date': serialize_doc((ret or {}).get('return_date')),
                'module': 'production-returns',
                'return_number': (ret or {}).get('return_number', ''),
                'return_qty': ri.get('return_qty', 0), 'status': (ret or {}).get('status', '')
            })
    timeline.sort(key=lambda x: x.get('date', '') or '')

    # ── Build PO info ──
    po_info = []
    for pid in po_ids:
        po = po_details.get(pid, {})
        po_info.append({
            'po_id': pid, 'po_number': po.get('po_number', ''),
            'customer_name': po.get('customer_name', ''),
            'vendor_name': po.get('vendor_name', ''),
            'status': po.get('status', ''),
            'deadline': serialize_doc(po.get('deadline'))
        })
    return {
        'serial_number': serial, 'po_item_count': len(po_items),
        'po_count': len(po_ids), 'po_info': po_info,
        'summary': {
            'buyer': ', '.join(filter(None, buyer_names)),
            'vendors': ', '.join(filter(None, vendors_set)),
            'total_ordered': totals['ordered'], 'total_produced': totals['produced'],
            'total_not_produced': totals['not_produced'],
            'total_shipped': totals['shipped'],
            'total_not_shipped': totals['not_shipped'],
            'all_serials': list(set(i.get('serial_number', '') for i in all_po_items if i.get('serial_number'))),
        },
        'all_items': summary_items, 'timeline': timeline
    }

