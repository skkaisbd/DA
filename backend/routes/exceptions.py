"""Exception & Variance domain: Material Requests, Material Defect Reports,
Production Returns, Production Variances (over/under-production).

Moved out of server.py during Backend Refactor Phase 7
(see /app/BACKEND_REFACTOR_PLAN.md). Pure move — behavior is byte-for-byte
identical to the original definitions in server.py. Medium risk phase per
the plan (recently revised heavily in PRD Phase 16-19, still "hangat") —
every line below is an exact cut-paste from server.py, no logic was altered.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from routes.production_rbac import (PROD_ADMIN_ROLES, PROD_VENDOR_ROLES,
    is_vendor, vendor_identity, deny_klien, require_write_actor,
    resolve_vendor_doc, resolve_buyer_name)
from core.helpers import new_id, now, parse_date, to_end_of_day
from core.pagination import LEGACY_DEFAULT_CAP, _paginate_params, _paginated_envelope, _sort_params
from core.cmt_override import (apply_scope, effective_vendor_id, resolve_override,
                               stamp as ov_stamp)

logger = __import__('logging').getLogger(__name__)
router = APIRouter(prefix="/api", tags=["exceptions"])

# ── DA BUG-FIX: state machine exceptions di-enforce (referensi SOMMERVILLE
# menerima nilai/lompatan status bebas). Forward-only.
VARIANCE_STATUS_TRANSITIONS = {
    'Reported': ['Acknowledged', 'Resolved'],
    'Acknowledged': ['Resolved'],
    'Resolved': [],
}
# Urutan status retur (STATUS_OPTIONS referensi ProductionReturnModule).
RETURN_STATUS_FLOW = ['Repair Needed', 'In Repair', 'Completed', 'Shipped Back']


def _return_allowed_next(status):
    if status not in RETURN_STATUS_FLOW:
        return []
    return RETURN_STATUS_FLOW[RETURN_STATUS_FLOW.index(status) + 1:]

# ─── MATERIAL REQUESTS ──────────────────────────────────────────────────────
@router.get("/material-requests")
async def get_material_requests(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    query = {}
    sp = request.query_params
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    if sp.get('request_type'): query['request_type'] = sp['request_type']
    if sp.get('status'): query['status'] = sp['status']
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'request_type', 'status', 'po_number'})
    total = await db.material_requests.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.material_requests.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    for d in docs:
        d['allowed_next'] = ['Approved', 'Rejected'] if d.get('status') == 'Pending' else []
    # ── PELACAKAN RANTAI PENGGANTI (keluhan pemilik 2026-06, INV-F28) ──────────
    # Persetujuan sudah menerbitkan surat jalan anak sejak lama, tetapi layar
    # hanya melihat nomornya — tidak ada kabar apakah surat jalan itu sudah
    # diterima vendor atau sudah diinspeksi, sehingga permintaan pengganti
    # "hilang" setelah disetujui. Status anak + jejak inspeksinya diambil batch
    # (2 query) supaya layar bisa menggambar pelacaknya.
    child_ids = [d.get('child_shipment_id') for d in docs if d.get('child_shipment_id')]
    if child_ids:
        ships = {s['id']: s for s in await db.vendor_shipments.find(
            {'id': {'$in': child_ids}},
            {'_id': 0, 'id': 1, 'status': 1, 'received_at': 1, 'shipment_number': 1}
        ).to_list(None)}
        insp_by_ship = {i['shipment_id']: i for i in await db.vendor_material_inspections.find(
            {'shipment_id': {'$in': child_ids}},
            {'_id': 0, 'id': 1, 'shipment_id': 1, 'created_at': 1}
        ).to_list(None)}
        for d in docs:
            cid = d.get('child_shipment_id')
            if not cid:
                continue
            cs = ships.get(cid) or {}
            insp = insp_by_ship.get(cid) or {}
            d['child_shipment_status'] = cs.get('status') or 'Missing'
            d['child_received_at'] = cs.get('received_at')
            d['child_inspection_id'] = insp.get('id') or ''
            d['child_inspected'] = bool(insp.get('id'))
            d['child_inspected_at'] = insp.get('created_at')
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@router.post("/material-requests")
async def create_material_request(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    _ov = await resolve_override(request, user, db)
    vendor_id = await effective_vendor_id(request, user, db, body.get('vendor_id'))
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    if body.get('request_type') not in ['ADDITIONAL', 'REPLACEMENT']: raise HTTPException(400, 'request_type harus ADDITIONAL atau REPLACEMENT')
    orig = await db.vendor_shipments.find_one({'id': body.get('original_shipment_id')}) if body.get('original_shipment_id') else None
    if not orig: raise HTTPException(404, 'Shipment asal tidak ditemukan')
    if _ov and orig.get('vendor_id') != _ov['vendor_id']:
        raise HTTPException(403, f"Pengiriman asal bukan milik {_ov['vendor_name']}")
    # Get PO number for request numbering
    po_number = body.get('po_number', '')
    po_id = body.get('po_id', '')
    if not po_number and po_id:
        po_doc = await db.production_pos.find_one({'id': po_id})
        if po_doc: po_number = po_doc.get('po_number', '')
    if not po_number:
        # Try to get from shipment items
        first_si = await db.vendor_shipment_items.find_one({'shipment_id': orig['id']})
        if first_si:
            po_number = first_si.get('po_number', '')
            if not po_id: po_id = first_si.get('po_id', '')
    # Count existing requests for THIS PO (not global)
    po_req_count = await db.material_requests.count_documents({'po_number': po_number, 'request_type': body['request_type']}) if po_number else await db.material_requests.count_documents({'request_type': body['request_type']})
    prefix = 'REQ-ADD' if body['request_type'] == 'ADDITIONAL' else 'REQ-RPL'
    req_number = f"{prefix}-{po_req_count + 1}-{po_number}" if po_number else f"{prefix}-{str(po_req_count + 1).zfill(4)}"
    items = body.get('items', [])
    # Phase 16: Defensive serial_number lookup
    # Jika item tidak punya serial_number (mis. resubmit dari request lama / data legacy),
    # auto-lookup dari vendor_shipment_items berdasarkan shipment_item_id atau matching sku+size+color
    if items and orig.get('id'):
        # Build lookup maps dari shipment items (sekali fetch, hindari N+1)
        ship_items_list = await db.vendor_shipment_items.find({'shipment_id': orig['id']}).to_list(None)
        si_by_id = {si['id']: si for si in ship_items_list if si.get('id')}
        si_by_sku_size_color = {}
        for si in ship_items_list:
            key = (si.get('sku', ''), si.get('size', ''), si.get('color', ''))
            # Simpan yang punya serial_number (prioritas), kalau tidak ada simpan apa adanya
            if key not in si_by_sku_size_color or (si.get('serial_number') and not si_by_sku_size_color[key].get('serial_number')):
                si_by_sku_size_color[key] = si
        for it in items:
            if it.get('serial_number'):
                continue  # sudah ada, skip
            matched_si = None
            sid = it.get('shipment_item_id')
            if sid and sid in si_by_id:
                matched_si = si_by_id[sid]
            else:
                key = (it.get('sku', ''), it.get('size', ''), it.get('color', ''))
                matched_si = si_by_sku_size_color.get(key)
            if matched_si:
                if not it.get('serial_number'):
                    it['serial_number'] = matched_si.get('serial_number', '')
                if not it.get('po_item_id'):
                    it['po_item_id'] = matched_si.get('po_item_id', '')
                if not it.get('shipment_item_id'):
                    it['shipment_item_id'] = matched_si.get('id', '')
    # Use vendor notes as reason (adopt notes from form)
    reason = body.get('reason', '') or body.get('notes', '') or body.get('vendor_notes', '')
    # Phase 16: support resubmit from a rejected request
    previous_request_id = body.get('previous_request_id', '')
    previous_request_number = ''
    if previous_request_id:
        prev = await db.material_requests.find_one({'id': previous_request_id}, {'_id': 0})
        if prev:
            previous_request_number = prev.get('request_number', '')
    req_doc = {
        'id': new_id(), 'request_number': req_number, 'request_type': body['request_type'],
        'vendor_id': vendor_id, 'vendor_name': orig.get('vendor_name', ''),
        'original_shipment_id': body['original_shipment_id'],
        'original_shipment_number': orig.get('shipment_number', ''),
        'po_id': po_id, 'po_number': po_number,
        'items': items,
        'total_requested_qty': sum(int(i.get('requested_qty', 0) or 0) for i in items),
        'reason': reason, 'vendor_notes': body.get('notes', ''), 'status': 'Pending',
        'inspection_id': body.get('inspection_id', ''),
        'defect_report_id': body.get('defect_report_id', ''),
        'previous_request_id': previous_request_id,
        'previous_request_number': previous_request_number,
        'business_type': orig.get('business_type', 'internal'),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now(),
        **ov_stamp(_ov),
    }
    await db.material_requests.insert_one(req_doc)
    # Mark previous request as resubmitted (defensive: avoid endless resubmit chain spamming)
    if previous_request_id:
        await db.material_requests.update_one(
            {'id': previous_request_id},
            {'$set': {'resubmitted_as_id': req_doc['id'], 'resubmitted_as_number': req_number, 'updated_at': now()}}
        )
    return JSONResponse(serialize_doc(req_doc), status_code=201)

@router.put("/material-requests/{req_id}")
async def update_material_request(req_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    req = await db.material_requests.find_one({'id': req_id})
    if not req: raise HTTPException(404, 'Request tidak ditemukan')
    new_status = body.get('status')
    if new_status is not None and new_status != req.get('status'):
        if new_status not in ('Approved', 'Rejected'):
            raise HTTPException(400, "Status permintaan hanya 'Approved' atau 'Rejected'")
        if req.get('status') != 'Pending':
            raise HTTPException(400,
                f"Permintaan sudah '{req.get('status')}' — keputusan hanya bisa diambil saat 'Pending'")
    if new_status == 'Approved' and req.get('status') == 'Pending':
        orig = await db.vendor_shipments.find_one({'id': req.get('original_shipment_id')})
        if not orig: raise HTTPException(404, 'Shipment asal tidak ditemukan')
        existing_children = await db.vendor_shipments.count_documents({
            'parent_shipment_id': req['original_shipment_id'], 'shipment_type': req['request_type']})
        suffix = f"A{existing_children + 1}" if req['request_type'] == 'ADDITIONAL' else f"R{existing_children + 1}"
        child_number = f"{orig.get('shipment_number')}-{suffix}"
        child_id = new_id()
        admin_notes = body.get('admin_notes', '')
        child_ship = {
            'id': child_id, 'shipment_number': child_number,
            'delivery_note_number': f"DN-{child_number}",
            'vendor_id': orig['vendor_id'], 'vendor_name': orig.get('vendor_name', ''),
            'shipment_date': now(), 'shipment_type': req['request_type'],
            'parent_shipment_id': req['original_shipment_id'],
            'business_type': orig.get('business_type', 'internal'),
            'material_request_id': req_id, 'status': 'Sent',
            'notes': admin_notes or f"Child shipment dari {orig.get('shipment_number')}",
            'notes_for_vendor': admin_notes,
            'created_by': user['name'], 'created_at': now(), 'updated_at': now()
        }
        await db.vendor_shipments.insert_one(child_ship)
        # Check if this is an accessories-only request
        is_accessories_request = req.get('category') == 'accessories'
        
        if is_accessories_request:
            # For accessories request, create accessory shipment items only
            for ri in req.get('items', []):
                await db.accessory_shipment_items.insert_one({
                    'id': new_id(), 'shipment_id': child_id, 'shipment_number': child_number,
                    'po_id': req.get('po_id'), 'po_number': req.get('po_number', ''),
                    'accessory_id': ri.get('accessory_id', ''),
                    'accessory_name': ri.get('accessory_name', ''),
                    'accessory_code': ri.get('accessory_code', ''),
                    'qty_sent': int(ri.get('requested_qty', 0) or 0),
                    'unit': ri.get('unit', 'pcs'),
                    'shipment_type': req['request_type'],
                    'parent_shipment_id': req['original_shipment_id'],
                    'created_at': now()
                })
        else:
            # For material request, create vendor shipment items
            # Get original shipment items to inherit serial numbers
            orig_items_map = {}
            orig_si_list = await db.vendor_shipment_items.find({'shipment_id': orig['id']}).to_list(None)
            for osi in orig_si_list:
                if osi.get('po_item_id'):
                    orig_items_map[osi['po_item_id']] = osi
            for ri in req.get('items', []):
                # Inherit serial_number from original shipment item or PO item
                serial = ri.get('serial_number', '')
                po_item_id = ri.get('po_item_id', '')
                if not serial and po_item_id:
                    # Try original shipment item
                    orig_si = orig_items_map.get(po_item_id, {})
                    serial = orig_si.get('serial_number', '')
                if not serial and po_item_id:
                    # Try PO item
                    poi = await db.po_items.find_one({'id': po_item_id})
                    if poi: serial = poi.get('serial_number', '')
                await db.vendor_shipment_items.insert_one({
                    'id': new_id(), 'shipment_id': child_id, 'shipment_number': child_number,
                    'po_id': req.get('po_id'), 'po_number': req.get('po_number', ''),
                    'po_item_id': po_item_id,
                    'product_name': ri.get('product_name', ''), 'sku': ri.get('sku', ''),
                    'size': ri.get('size', ''), 'color': ri.get('color', ''),
                    'serial_number': serial,
                    'qty_sent': int(ri.get('requested_qty', 0) or 0),
                    'shipment_type': req['request_type'],
                    'parent_shipment_id': req['original_shipment_id'],
                    'created_at': now()
                })
        await db.material_requests.update_one({'id': req_id}, {'$set': {
            'status': 'Approved', 'admin_notes': body.get('admin_notes', ''),
            'approved_by': user['name'], 'approved_at': now(),
            'child_shipment_id': child_id, 'child_shipment_number': child_number,
            'updated_at': now()
        }})
        result = serialize_doc(await db.material_requests.find_one({'id': req_id}, {'_id': 0}))
        result['child_shipment'] = serialize_doc(child_ship)
        return result
    elif new_status == 'Rejected':
        # Phase 16: admin_notes WAJIB diisi saat reject (agar vendor tahu alasan penolakan)
        admin_notes = (body.get('admin_notes', '') or '').strip()
        if not admin_notes:
            raise HTTPException(400, 'Catatan admin wajib diisi saat menolak permintaan.')
        await db.material_requests.update_one({'id': req_id}, {'$set': {
            'status': 'Rejected', 'admin_notes': admin_notes,
            'rejected_by': user['name'], 'rejected_at': now(),
            'updated_at': now()
        }})
        return serialize_doc(await db.material_requests.find_one({'id': req_id}, {'_id': 0}))
    body.pop('_id', None); body.pop('id', None); body.pop('status', None)
    await db.material_requests.update_one({'id': req_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.material_requests.find_one({'id': req_id}, {'_id': 0}))

# ─── MATERIAL DEFECT REPORTS ─────────────────────────────────────────────────
@router.get("/material-defect-reports")
async def get_defect_reports(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    query = {}
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('defect_type'): query['defect_type'] = sp['defect_type']
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'report_date', 'status', 'defect_type'})
    total = await db.material_defect_reports.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.material_defect_reports.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@router.post("/material-defect-reports")
async def create_defect_report(request: Request):
    # ─── K5 (Phase C) DEPRECATION ─────────────────────────────────────────
    # material_defect_reports is no longer a production gate. FG defects are now
    # captured at DA CMT-receipt inspection (Phase B: qty_actual + reject_qty in
    # the "Terima FG dari CMT" module). Writing new defect reports is disabled;
    # GET stays for legacy read-only reporting.
    raise HTTPException(410,
        'Endpoint di-deprekasi per K5 (Phase C). Laporan defect material tidak lagi '
        'menjadi gate produksi — catat reject FG saat DA menerima kiriman CMT '
        '(modul "Terima FG dari CMT").')
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    # ─── M-3 FIX: Derive vendor_id from job/job_item when admin calls without it ───
    # Vendor role: always uses user.vendor_id.
    # Admin role: accepts explicit vendor_id in body, OR derives from referenced job/job_item.
    vendor_id = vendor_identity(user) if is_vendor(user) else body.get('vendor_id')
    job_item = None
    if body.get('job_item_id'):
        job_item = await db.production_job_items.find_one({'id': body['job_item_id']})
    job_doc = None
    if body.get('job_id'):
        job_doc = await db.production_jobs.find_one({'id': body['job_id']})
    elif job_item and job_item.get('job_id'):
        job_doc = await db.production_jobs.find_one({'id': job_item['job_id']})
    if not vendor_id and job_doc:
        vendor_id = job_doc.get('vendor_id')
    if not vendor_id:
        raise HTTPException(400, 'vendor_id diperlukan (atau kirim job_id / job_item_id yang valid)')
    defect = {
        'id': new_id(), 'vendor_id': vendor_id,
        'job_id': body.get('job_id') or (job_item or {}).get('job_id'),
        'job_item_id': body.get('job_item_id'),
        'po_id': body.get('po_id'), 'po_item_id': body.get('po_item_id'),
        'sku': body.get('sku', (job_item or {}).get('sku', '')),
        'product_name': body.get('product_name', (job_item or {}).get('product_name', '')),
        'size': body.get('size', (job_item or {}).get('size', '')),
        'color': body.get('color', (job_item or {}).get('color', '')),
        'defect_qty': int(body.get('defect_qty', 0) or 0),
        'defect_type': body.get('defect_type', 'Material Cacat'),
        'description': body.get('description', ''),
        'shipment_id': body.get('shipment_id'),
        'report_date': parse_date(body.get('report_date')) or now(),
        'business_type': (job_doc or {}).get('business_type', 'internal'),
        'status': 'Reported', 'reported_by': user['name'],
        'created_at': now(), 'updated_at': now()
    }
    await db.material_defect_reports.insert_one(defect)
    return JSONResponse(serialize_doc(defect), status_code=201)

# ─── PRODUCTION RETURNS ──────────────────────────────────────────────────────
@router.get("/production-returns")
async def get_returns(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('status'): query['status'] = sp['status']
    if sp.get('po_id'): query['reference_po_id'] = sp['po_id']
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'return_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'return_number', 'status'})
    total = await db.production_returns.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    returns = await db.production_returns.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)

    # ── Phase 10B: batch-fetch items ──
    ret_ids = [r['id'] for r in returns]
    if ret_ids:
        items_all = await db.production_return_items.find({'return_id': {'$in': ret_ids}}, {'_id': 0}).to_list(None)
    else:
        items_all = []
    items_by_ret = {}
    for it in items_all:
        items_by_ret.setdefault(it['return_id'], []).append(it)

    result = [{**serialize_doc(r), 'items': serialize_doc(items_by_ret.get(r['id'], []))} for r in returns]
    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@router.get("/production-returns/{ret_id}")
async def get_return(ret_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    ret = await db.production_returns.find_one({'id': ret_id}, {'_id': 0})
    if not ret: raise HTTPException(404, 'Not found')
    items = await db.production_return_items.find({'return_id': ret_id}, {'_id': 0}).to_list(None)
    result = serialize_doc(ret)
    result['items'] = serialize_doc(items)
    result['allowed_next'] = _return_allowed_next(ret.get('status', 'Repair Needed'))
    return result

@router.post("/production-returns")
async def create_return(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    return_id = new_id()
    # SESI #27 — SATU PINTU kebijakan penomoran (Otomatis/Manual). Retur produksi
    # dari buyer sering disalin dari nomor surat retur pihak buyer, jadi mode MANUAL
    # bukan kemewahan. Sebelum ini jenis dokumen ini bahkan TIDAK ADA di katalog
    # Penomoran Dokumen — owner tak bisa melihat, apalagi mengatur, formatnya.
    from core.doc_number_policy import issue_number
    return_number = await issue_number(
        db, "production_returns.return_number",
        requested=(body.get("return_number") or "").strip())
    ref_po = await db.production_pos.find_one({'id': body.get('reference_po_id')}) if body.get('reference_po_id') else None
    items_data = body.get('items', [])

    # ─── VALIDATION GUARDRAILS (Phase A — C-2 & H-4) ──────────────────────
    # Reject empty/negative returns and returns that exceed max_returnable
    if not items_data:
        raise HTTPException(400, 'Retur harus memiliki minimal 1 item')
    for item in items_data:
        try:
            qty = int(item.get('return_qty', 0) or 0)
        except (TypeError, ValueError):
            raise HTTPException(400, 'return_qty harus bilangan bulat')
        if qty < 1:
            raise HTTPException(400, f'return_qty harus minimal 1 (diterima: {qty})')
        po_item_id = item.get('po_item_id')
        if po_item_id:
            # max_returnable = total_shipped - total_already_returned
            buyer_items = await db.buyer_shipment_items.find({'po_item_id': po_item_id}).to_list(None)
            total_shipped = sum(int(bi.get('qty_shipped', 0) or 0) for bi in buyer_items)
            prev_return_items = await db.production_return_items.find({'po_item_id': po_item_id}).to_list(None)
            total_already_returned = sum(int(ri.get('return_qty', 0) or 0) for ri in prev_return_items)
            max_returnable = max(0, total_shipped - total_already_returned)
            if qty > max_returnable:
                sku = item.get('sku') or (await db.po_items.find_one({'id': po_item_id}) or {}).get('sku', '')
                raise HTTPException(400,
                    f'Retur {sku}: qty {qty} melebihi maks yang bisa diretur ({max_returnable} pcs). '
                    f'Total dikirim ke buyer: {total_shipped}, sudah diretur: {total_already_returned}.')

    total_qty = sum(int(i.get('return_qty', 0) or 0) for i in items_data)
    return_doc = {
        'id': return_id, 'return_number': return_number,
        'reference_po_id': body.get('reference_po_id'),
        'reference_po_number': (ref_po or {}).get('po_number', body.get('reference_po_number', '')),
        'customer_name': body.get('customer_name', (ref_po or {}).get('customer_name', '')),
        'buyer_name': body.get('buyer_name', body.get('customer_name', '')),
        'return_date': parse_date(body.get('return_date')) or now(),
        'return_reason': body.get('return_reason', ''), 'notes': body.get('notes', ''),
        'business_type': (ref_po or {}).get('business_type', 'internal'),
        'status': 'Repair Needed', 'total_return_qty': total_qty,
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.production_returns.insert_one(return_doc)
    inserted_items = []
    for item in items_data:
        ri = {
            'id': new_id(), 'return_id': return_id,
            'po_item_id': item.get('po_item_id'),
            'sku': item.get('sku', ''), 'product_name': item.get('product_name', ''),
            'serial_number': item.get('serial_number', ''),
            'size': item.get('size', ''), 'color': item.get('color', ''),
            'return_qty': int(item.get('return_qty', 0) or 0),
            'defect_type': item.get('defect_type', ''),
            'repair_notes': item.get('repair_notes', ''), 'repaired_qty': 0,
            'created_at': now()
        }
        await db.production_return_items.insert_one(ri)
        inserted_items.append(ri)
    result = serialize_doc(return_doc)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@router.put("/production-returns/{ret_id}")
async def update_return(ret_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    if body.get('return_date'): body['return_date'] = parse_date(body['return_date'])
    if 'status' in body:
        ret_doc = await db.production_returns.find_one({'id': ret_id})
        if not ret_doc: raise HTTPException(404, 'Return not found')
        new_ret_status = body['status']
        if new_ret_status not in RETURN_STATUS_FLOW:
            raise HTTPException(400, f"Status retur tidak dikenal. Valid: {RETURN_STATUS_FLOW}")
        cur = ret_doc.get('status', 'Repair Needed')
        cur_idx = RETURN_STATUS_FLOW.index(cur) if cur in RETURN_STATUS_FLOW else 0
        if new_ret_status != cur and RETURN_STATUS_FLOW.index(new_ret_status) < cur_idx:
            raise HTTPException(400,
                f"Transisi status retur ilegal: '{cur}' → '{new_ret_status}' (hanya boleh maju: {RETURN_STATUS_FLOW})")
    await db.production_returns.update_one({'id': ret_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.production_returns.find_one({'id': ret_id}, {'_id': 0}))

@router.delete("/production-returns/{ret_id}")
async def delete_return(ret_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.production_returns.find_one({'id': ret_id})
    if not doc: raise HTTPException(404, 'Not found')
    await db.production_return_items.delete_many({'return_id': ret_id})
    await db.production_returns.delete_one({'id': ret_id})
    return {'success': True}

# ─── PRODUCTION VARIANCES (OVERPRODUCTION/UNDERPRODUCTION) ──────────────────
@router.post("/production-variances")
async def create_variance(request: Request):
    """Vendor reports overproduction or underproduction for a job/item"""
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    
    # Get vendor_id from user context if vendor role
    _ov = await resolve_override(request, user, db)
    vendor_id = await effective_vendor_id(request, user, db, body.get('vendor_id'))
    if not vendor_id: raise HTTPException(400, 'vendor_id required')
    
    # Validate job exists
    job_id = body.get('job_id')
    if not job_id: raise HTTPException(400, 'job_id required')
    job = await db.production_jobs.find_one({'id': job_id})
    if not job: raise HTTPException(404, 'Job not found')
    if job.get('vendor_id') != vendor_id: raise HTTPException(403, 'Job does not belong to this vendor')
    
    # Get PO info
    po_id = job.get('po_id') or body.get('po_id')
    po = await db.production_pos.find_one({'id': po_id}) if po_id else None
    po_number = po.get('po_number', '') if po else ''
    
    variance_type = body.get('variance_type')  # 'OVERPRODUCTION' or 'UNDERPRODUCTION'
    if variance_type not in ['OVERPRODUCTION', 'UNDERPRODUCTION']:
        raise HTTPException(400, 'variance_type must be OVERPRODUCTION or UNDERPRODUCTION')
    
    # Create variance record
    variance = {
        'id': new_id(),
        'vendor_id': vendor_id,
        'vendor_name': job.get('vendor_name', ''),
        'job_id': job_id,
        'job_number': job.get('job_number', ''),
        'po_id': po_id,
        'po_number': po_number,
        'variance_type': variance_type,
        'business_type': job.get('business_type', 'internal'),
        'reason': body.get('reason', ''),
        'notes': body.get('notes', ''),
        'items': body.get('items', []),  # Array of {job_item_id, product_name, sku, ordered_qty, produced_qty, variance_qty}
        'total_variance_qty': sum(int(item.get('variance_qty', 0) or 0) for item in body.get('items', [])),
        'reported_by': user['name'],
        'status': 'Reported',  # Reported, Acknowledged, Resolved
        'created_at': now(),
        'updated_at': now(),
        **ov_stamp(_ov),
    }
    
    await db.production_variances.insert_one(variance)
    await log_activity(user['id'], user['name'], 'Create', 'Production Variance',
                      f"Reported {variance_type} for job {job.get('job_number')}: {variance['total_variance_qty']} pcs")
    
    return JSONResponse(serialize_doc(variance), status_code=201)

@router.get("/production-variances")
async def get_variances(request: Request):
    """List production variances with filters"""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    
    query = {}
    
    # Vendor filter (auto for vendor role, override untuk staf DA, opsional utk admin)
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    
    # Type filter
    if sp.get('variance_type'):
        query['variance_type'] = sp['variance_type']
    
    # Status filter
    if sp.get('status'):
        query['status'] = sp['status']

    # FASE IA-1 (2026-07-26) — pemisahan data per domain (Portal Produksi = internal,
    # Portal Maklon = maklon). Field `business_type` SUDAH ditulis saat create
    # (lihat create_variance), jadi ini murni filter baca.
    bt = sp.get('business_type')
    if bt == 'internal':
        query['business_type'] = 'internal'
    elif bt == 'maklon':
        query['business_type'] = {'$ne': 'internal'}
    
    # Date range filter
    date_from = parse_date(sp.get('from'))
    date_to = to_end_of_day(sp.get('to'))
    if date_from or date_to:
        date_filter = {}
        if date_from: date_filter['$gte'] = date_from
        if date_to: date_filter['$lte'] = date_to
        if date_filter: query['created_at'] = date_filter
    
    # Search
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'job_number': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
            {'reason': {'$regex': search, '$options': 'i'}}
        ]
    
    variances = await db.production_variances.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    for v in variances:
        v['allowed_next'] = VARIANCE_STATUS_TRANSITIONS.get(v.get('status', 'Reported'), [])
    return serialize_doc(variances)

@router.get("/production-variances/stats")
async def get_variance_stats(request: Request):
    """Get summary statistics for production variances"""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    
    query = {}
    
    # Vendor filter
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    
    # Date range filter
    date_from = parse_date(sp.get('from'))
    date_to = to_end_of_day(sp.get('to'))
    if date_from or date_to:
        date_filter = {}
        if date_from: date_filter['$gte'] = date_from
        if date_to: date_filter['$lte'] = date_to
        if date_filter: query['created_at'] = date_filter
    
    # FASE IA-1 — pemisahan data per domain (samakan dgn list endpoint di atas)
    bt = sp.get('business_type')
    if bt == 'internal':
        query['business_type'] = 'internal'
    elif bt == 'maklon':
        query['business_type'] = {'$ne': 'internal'}

    # Aggregate stats
    all_variances = await db.production_variances.find(query, {'_id': 0}).to_list(None)
    
    overproduction = [v for v in all_variances if v.get('variance_type') == 'OVERPRODUCTION']
    underproduction = [v for v in all_variances if v.get('variance_type') == 'UNDERPRODUCTION']
    
    stats = {
        'total_records': len(all_variances),
        'overproduction': {
            'count': len(overproduction),
            'total_qty': sum(v.get('total_variance_qty', 0) for v in overproduction)
        },
        'underproduction': {
            'count': len(underproduction),
            'total_qty': sum(v.get('total_variance_qty', 0) for v in underproduction)
        },
        'by_status': {},
        'by_vendor': {}
    }
    
    # Group by status
    for v in all_variances:
        status = v.get('status', 'Unknown')
        if status not in stats['by_status']:
            stats['by_status'][status] = 0
        stats['by_status'][status] += 1
    
    # Group by vendor
    for v in all_variances:
        vname = v.get('vendor_name', 'Unknown')
        if vname not in stats['by_vendor']:
            stats['by_vendor'][vname] = {'overproduction': 0, 'underproduction': 0, 'total_qty': 0}
        stats['by_vendor'][vname][v.get('variance_type', '').lower()] += 1
        stats['by_vendor'][vname]['total_qty'] += v.get('total_variance_qty', 0)
    
    return stats

@router.put("/production-variances/{vid}")
async def update_variance_status(vid: str, request: Request):
    """Admin updates variance status (Acknowledged/Resolved)"""
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    
    variance = await db.production_variances.find_one({'id': vid})
    if not variance: raise HTTPException(404, 'Variance not found')
    new_var_status = body.get('status')
    if new_var_status is not None and new_var_status != variance.get('status'):
        allowed = VARIANCE_STATUS_TRANSITIONS.get(variance.get('status', 'Reported'), [])
        if new_var_status not in allowed:
            raise HTTPException(400,
                f"Transisi status variance ilegal: '{variance.get('status')}' → '{new_var_status}'. "
                f"Valid: {allowed if allowed else 'tidak ada (status final)'}")
    await db.production_variances.update_one({'id': vid}, {'$set': {
        'status': body.get('status', variance.get('status')),
        'admin_notes': body.get('admin_notes', ''),
        'updated_by': user['name'],
        'updated_at': now()
    }})
    
    await log_activity(user['id'], user['name'], 'Update', 'Production Variance',
                      f"Updated variance status to {body.get('status')} for {variance.get('job_number')}")
    
    return {'success': True}

# ══════════════════════════════════════════════════════════════════════════════
# PHASE 7C (DA): PRODUCTION VARIANCE → GL AUTO-POSTING — dipertahankan saat
# adopsi SOMMERVILLE (jembatan finance DA, lihat PRODUKSI_E3_BRIDGE_FINANCE.md)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/production-variances/{vid}/post-gl")
async def post_variance_to_gl(vid: str, request: Request):
    """
    Post production variance ke GL.
    OVERPRODUCTION: Dr Inventory FG (1-1404) / Cr Variance Income (4-920)
    UNDERPRODUCTION: Dr Variance Loss (6-4100) / Cr WIP (1-330)
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    try:
        body = await request.json()
    except Exception:
        body = {}

    variance = await db.production_variances.find_one({'id': vid})
    if not variance:
        raise HTTPException(404, 'Variance not found')

    variance_value = float(variance.get('variance_value', 0))
    if variance_value == 0:
        items = variance.get('items', [])
        total_value = 0
        for item in items:
            var_qty = int(item.get('variance_qty', 0) or 0)
            product_sku = item.get('sku')
            unit_cost = 0
            if product_sku:
                product = await db.rahaza_models.find_one({'code': product_sku}, {'_id': 0})
                if product:
                    unit_cost = float(product.get('cost_per_unit', 0) or product.get('price', 0) or 0)
            unit_cost = float(body.get('unit_cost', unit_cost))
            total_value += abs(var_qty) * unit_cost

        variance_value = round(total_value)
        await db.production_variances.update_one(
            {'id': vid},
            {'$set': {'variance_value': variance_value, 'updated_at': now()}}
        )
        variance['variance_value'] = variance_value

    if variance_value <= 0:
        raise HTTPException(400, 'Variance value harus > 0. Set unit_cost jika belum ada.')

    posting_result = None
    try:
        from routes.rahaza_posting import post_production_variance
        variance_refresh = await db.production_variances.find_one({'id': vid}, {'_id': 0})
        posting_result = await post_production_variance(db, variance_refresh, user)
    except Exception as e:
        logger.exception("Production variance auto-post failed")
        posting_result = {"ok": False, "error": str(e)}

    final_variance = await db.production_variances.find_one({'id': vid}, {'_id': 0})
    final_variance['_posting_result'] = posting_result

    await log_activity(user['id'], user['name'], 'Post GL', 'Production Variance',
                      f"Posted variance {variance['variance_type']} to GL: {variance_value}")

    return serialize_doc(final_variance)


@router.post("/production-variances/{vid}/retry-posting")
async def retry_variance_posting(vid: str, request: Request):
    """Retry posting production variance to GL (idempotent)"""
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()

    variance = await db.production_variances.find_one({'id': vid}, {'_id': 0})
    if not variance:
        raise HTTPException(404, 'Variance not found')

    try:
        from routes.rahaza_posting import post_production_variance
        result = await post_production_variance(db, variance, user)
    except Exception as e:
        logger.exception("Production variance retry post failed")
        result = {"ok": False, "error": str(e)}

    final_variance = await db.production_variances.find_one({'id': vid}, {'_id': 0})
    final_variance['_posting_result'] = result
    return serialize_doc(final_variance)
