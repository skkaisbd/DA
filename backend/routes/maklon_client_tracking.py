"""Klien Maklon Tracking (read-only) — Fase 2 tambahan yang disetujui user.

Role `klien_maklon` (main ERP token, linked via users.buyer_id →
dewi_maklon_clients.id) dapat memantau PO maklon miliknya: progress produksi
per item + status dispatch (surat jalan bertahap). Admin/admin_maklon dapat
melihat semua (opsional filter ?buyer_id=).
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, check_role, serialize_doc
from routes.production_rbac import PROD_ADMIN_ROLES
from services.maklon_progress import compute_po_progress, compute_pos_batch

router = APIRouter(prefix="/api/maklon-client", tags=["maklon-client-tracking"])


def _resolve_scope(user: dict, request: Request):
    """Returns buyer_id scope (None = all, admin only)."""
    role = (user.get('role') or '')
    if role == 'klien_maklon':
        buyer_id = user.get('buyer_id')
        if not buyer_id:
            raise HTTPException(403, 'Akun klien belum terhubung ke master klien. Hubungi admin.')
        return buyer_id
    if check_role(user, PROD_ADMIN_ROLES):
        return request.query_params.get('buyer_id') or None
    raise HTTPException(403, 'Forbidden')


async def _po_aggregates(db, po_ids):
    """Batch: po_items + produced + shipped/received per po_id."""
    items_all = await db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None) if po_ids else []
    item_ids = [i['id'] for i in items_all]
    prod_agg = await db.production_job_items.aggregate([
        {'$match': {'po_item_id': {'$in': item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$produced_qty'}}},
    ]).to_list(None) if item_ids else []
    ship_agg = await db.buyer_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': item_ids}}},
        {'$group': {'_id': '$po_item_id', 'shipped': {'$sum': '$qty_shipped'},
                    'recv': {'$sum': {'$ifNull': ['$qty_received', '$qty_shipped']}}}},
    ]).to_list(None) if item_ids else []
    produced = {a['_id']: a['qty'] for a in prod_agg}
    shipped = {a['_id']: a['shipped'] for a in ship_agg}
    received = {a['_id']: a['recv'] for a in ship_agg}
    items_by_po = {}
    for it in items_all:
        items_by_po.setdefault(it['po_id'], []).append(it)
    return items_by_po, produced, shipped, received


@router.get("/pos")
async def list_client_pos(request: Request):
    user = await require_auth(request)
    db = get_db()
    scope = _resolve_scope(user, request)
    query = {'business_type': 'maklon'}
    if scope:
        query['buyer_id'] = scope
    pos = await db.production_pos.find(query, {'_id': 0}).sort('created_at', -1).to_list(200)
    po_ids = [p['id'] for p in pos]
    items_by_po, produced, shipped, received = await _po_aggregates(db, po_ids)
    # Canonical multi-state breakdown per PO (additive; progress_pct lama tetap dijaga)
    breakdowns = await compute_pos_batch(db, po_ids)
    result = []
    for po in pos:
        items = items_by_po.get(po['id'], [])
        t_ord = sum(int(i.get('qty', 0) or 0) for i in items)
        t_prod = sum(produced.get(i['id'], 0) for i in items)
        t_ship = sum(shipped.get(i['id'], 0) for i in items)
        t_recv = sum(received.get(i['id'], 0) for i in items)
        bd = breakdowns.get(po['id'], {})
        result.append({
            'po_id': po['id'], 'po_number': po.get('po_number', ''),
            'status': po.get('status', ''), 'po_date': serialize_doc(po.get('po_date')),
            'deadline': serialize_doc(po.get('deadline')),
            'item_count': len(items),
            'total_ordered': t_ord, 'total_produced': t_prod,
            'total_shipped': t_ship, 'total_received': t_recv,
            'progress_pct': round(t_prod / t_ord * 100) if t_ord > 0 else 0,
            'delivery_pct': round(t_recv / t_ord * 100) if t_ord > 0 else 0,
            # Canonical breakdown (baru) — konsumen boleh abaikan utk backward-compat
            'breakdown': bd.get('breakdown', {}),
            'good_pct': bd.get('good_pct', 0),
            'dispatch_pct': bd.get('dispatch_pct', 0),
        })
    return result


@router.get("/pos/{po_id}/tracking")
async def client_po_tracking(po_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    scope = _resolve_scope(user, request)
    po = await db.production_pos.find_one({'id': po_id, 'business_type': 'maklon'}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO maklon tidak ditemukan')
    if scope and po.get('buyer_id') != scope:
        raise HTTPException(403, 'PO ini bukan milik klien Anda')

    items_by_po, produced, shipped, received = await _po_aggregates(db, [po_id])
    items = []
    for it in items_by_po.get(po_id, []):
        ordered = int(it.get('qty', 0) or 0)
        prod = produced.get(it['id'], 0)
        recv = received.get(it['id'], 0)
        items.append({
            'po_item_id': it['id'], 'product_name': it.get('product_name', ''),
            'sku': it.get('sku', ''), 'size': it.get('size', ''), 'color': it.get('color', ''),
            'serial_number': it.get('serial_number', ''),
            'ordered_qty': ordered, 'produced_qty': prod,
            'shipped_qty': shipped.get(it['id'], 0), 'received_qty': recv,
            'progress_pct': round(prod / ordered * 100) if ordered > 0 else 0,
        })

    # Dispatches (surat jalan bertahap) — grouped per buyer_shipment + dispatch_seq
    bs_docs = await db.buyer_shipments.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    bs_map = {b['id']: b for b in bs_docs}
    bs_items = await db.buyer_shipment_items.find(
        {'shipment_id': {'$in': list(bs_map.keys())}}, {'_id': 0}
    ).sort([('dispatch_seq', 1), ('created_at', 1)]).to_list(None) if bs_map else []
    dispatch_map = {}
    for bi in bs_items:
        key = (bi.get('shipment_id'), bi.get('dispatch_seq', 1))
        if key not in dispatch_map:
            bs = bs_map.get(bi.get('shipment_id'), {})
            dispatch_map[key] = {
                'shipment_number': bs.get('shipment_number', ''),
                'dispatch_seq': bi.get('dispatch_seq', 1),
                'dispatch_date': serialize_doc(bi.get('dispatch_date') or bi.get('created_at')),
                'status': bs.get('ship_status', ''),
                'total_qty': 0, 'items': [],
            }
        d = dispatch_map[key]
        d['total_qty'] += int(bi.get('qty_shipped', 0) or 0)
        d['items'].append({
            'product_name': bi.get('product_name', ''), 'sku': bi.get('sku', ''),
            'size': bi.get('size', ''), 'color': bi.get('color', ''),
            'qty_shipped': bi.get('qty_shipped', 0),
            'qty_received': bi.get('qty_received'),
        })
    dispatches = sorted(dispatch_map.values(), key=lambda d: (d['dispatch_date'] or '', d['dispatch_seq']))

    total_ordered = sum(i['ordered_qty'] for i in items)
    total_produced = sum(i['produced_qty'] for i in items)
    total_received = sum(i['received_qty'] for i in items)
    # Canonical multi-state breakdown (additive) — progress_pct lama tetap dijaga
    prog = await compute_po_progress(db, po_id)
    return {
        'po_id': po_id, 'po_number': po.get('po_number', ''),
        'status': po.get('status', ''), 'po_date': serialize_doc(po.get('po_date')),
        'deadline': serialize_doc(po.get('deadline')),
        'client_name': po.get('customer_name', ''),
        'items': items, 'dispatches': dispatches,
        'total_ordered': total_ordered, 'total_produced': total_produced,
        'total_received': total_received,
        'progress_pct': round(total_produced / total_ordered * 100) if total_ordered > 0 else 0,
        'breakdown': prog.get('breakdown', {}) if prog else {},
        'good_pct': prog.get('good_pct', 0) if prog else 0,
        'dispatch_pct': prog.get('dispatch_pct', 0) if prog else 0,
        'items_breakdown': prog.get('items', []) if prog else [],
    }


@router.get("/pos/{po_id}/progress")
async def client_po_progress(po_id: str, request: Request):
    """Canonical multi-state progress lengkap (per item breakdown).

    Dipakai UI tracking/PO-360 baru & modul Permak. Scope sama dgn endpoint lain:
    klien_maklon hanya PO miliknya; admin semua.
    """
    user = await require_auth(request)
    db = get_db()
    scope = _resolve_scope(user, request)
    po = await db.production_pos.find_one({'id': po_id, 'business_type': 'maklon'}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO maklon tidak ditemukan')
    if scope and po.get('buyer_id') != scope:
        raise HTTPException(403, 'PO ini bukan milik klien Anda')
    prog = await compute_po_progress(db, po_id)
    if prog is None:
        raise HTTPException(404, 'Progress tidak tersedia untuk PO ini')
    return prog
