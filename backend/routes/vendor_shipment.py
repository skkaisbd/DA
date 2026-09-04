"""Vendor Shipment & Material Inspection domain: Vendor Shipments (+ items),
Vendor Material Inspections (+ items).

Moved out of server.py during Backend Refactor Phase 5
(see /app/BACKEND_REFACTOR_PLAN.md). Pure move — behavior is byte-for-byte
identical to the original definitions in server.py. Medium risk phase per
the plan (tied directly to capacity invariants M-1/C-1) — every line below
is an exact cut-paste from server.py, no logic was altered.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from routes.production_rbac import (PROD_ADMIN_ROLES, PROD_VENDOR_ROLES,
    is_vendor, vendor_identity, deny_klien, require_write_actor,
    resolve_vendor_doc, resolve_buyer_name)
from core.helpers import new_id, now, parse_date
from core.pagination import LEGACY_DEFAULT_CAP, _paginate_params, _paginated_envelope, _sort_params
from core.enrichment import enrich_with_product_photos
from core.cmt_override import (apply_scope, effective_vendor_id, resolve_override,
                               stamp as ov_stamp)
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["vendor-shipments"])


@router.post("/vendor-shipments/material-preview")
async def vendor_shipment_material_preview(request: Request):
    """FASE H-1 — PRATINJAU material yang akan KELUAR dari gudang.

    Dipanggil form "Kirim Material CMT" SEBELUM Simpan supaya pemakai melihat
    kain & aksesoris apa yang akan berkurang beserta kecukupan stoknya. Tanpa ini,
    satu-satunya cara mengetahui stok kurang adalah menekan Simpan dan ditolak —
    UX yang persis dikeluhkan pemilik pada layar dispatch ke buyer.

    Body: {po_id?, items: [{po_item_id, qty_sent}]}
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    body = await request.json()
    items = body.get('items') or []
    lines = [{'po_item_id': it.get('po_item_id'), 'qty': it.get('qty_sent')}
             for it in items if it.get('po_item_id')]
    if not lines:
        return {'applicable': False, 'reason': 'items[] kosong', 'materials': []}

    # Maklon: material milik KLIEN — gudang DA tidak dipotong, jadi tidak ada
    # yang perlu dipratinjau. Jawaban ini disampaikan JELAS, bukan daftar kosong.
    bt = 'internal'
    poi_ids = [ln['po_item_id'] for ln in lines]
    poi = await db.po_items.find_one({'id': {'$in': poi_ids}}, {'_id': 0, 'po_id': 1})
    if poi and poi.get('po_id'):
        po_doc = await db.production_pos.find_one(
            {'id': poi['po_id']}, {'_id': 0, 'business_type': 1})
        bt = (po_doc or {}).get('business_type', 'internal')
    if bt == 'maklon':
        return {
            'applicable': False,
            'business_type': 'maklon',
            'reason': ('Produksi MAKLON: material milik klien dan dikirim oleh klien, '
                       'jadi stok gudang DA tidak dipotong.'),
            'materials': [], 'has_shortage': False,
        }

    from core import material_issue_engine as mie
    try:
        need, notes, total_pcs = await mie.bom_need_for_lines(db, lines)
    except Exception as e:  # noqa: BLE001
        logger.exception('pratinjau material gagal')
        return {'applicable': False, 'reason': f'gagal membaca BOM: {e}', 'materials': []}

    rows, has_short = [], False
    for code, e in need.items():
        mat = await db.rahaza_materials.find_one(
            {'code': code, 'active': True},
            {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'unit': 1, 'unit_cost': 1})
        if not mat:
            rows.append({'code': code, 'name': e['name'], 'unit': e['unit'],
                         'qty_required': round(e['qty'], 4), 'available': 0,
                         'shortage': True,
                         'problem': 'belum terdaftar di Master Item gudang'})
            has_short = True
            continue
        loc, avail = await mie.best_location_for(db, mat['id'], e['qty'])
        short = (not loc) or (avail + 1e-9 < e['qty'])
        if short:
            has_short = True
        rows.append({
            'material_id': mat['id'], 'code': mat['code'],
            'name': mat.get('name') or code,
            'unit': mat.get('unit') or e['unit'],
            'qty_required': round(e['qty'], 4),
            'available': round(avail, 4),
            'location_id': loc,
            'unit_cost': float(mat.get('unit_cost') or 0),
            'value': round(e['qty'] * float(mat.get('unit_cost') or 0), 2),
            'shortage': short,
            'problem': ('belum punya baris stok di gudang' if not loc
                        else ('stok kurang' if short else '')),
        })
    rows.sort(key=lambda r: (not r['shortage'], r['code']))
    return {
        'applicable': True,
        'business_type': bt,
        'total_pcs': total_pcs,
        'materials': rows,
        'has_shortage': has_short,
        'bom_notes': notes,
        'total_value': round(sum(r.get('value') or 0 for r in rows), 2),
    }


# ─── VENDOR SHIPMENTS ────────────────────────────────────────────────────────
@router.get("/vendor-shipments")
async def get_vendor_shipments(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    query = {}
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    _bt = sp.get('business_type')
    if _bt == 'maklon': query['business_type'] = 'maklon'
    elif _bt == 'internal': query['business_type'] = {'$ne': 'maklon'}  # internal + legacy/null
    elif _bt: query['business_type'] = _bt
    if sp.get('status'): query['status'] = sp['status']
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'shipment_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]

    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'shipment_number', 'shipment_date',
                                 'vendor_name', 'status', 'shipment_type'})
    total = await db.vendor_shipments.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.vendor_shipments.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    shipments = await cursor.to_list(limit)

    # ── Phase 10B: batch-fetch related rows ──
    ship_ids = [s['id'] for s in shipments]
    if ship_ids:
        items_all = await db.vendor_shipment_items.find({'shipment_id': {'$in': ship_ids}}, {'_id': 0}).to_list(None)
        # count child shipments + qty pengganti dalam satu agregasi (INV-F28:
        # daftar harus bisa memberi tahu "punya 2 kiriman pengganti, 10 pcs")
        child_agg = await db.vendor_shipments.aggregate([
            {'$match': {'parent_shipment_id': {'$in': ship_ids}}},
            {'$group': {'_id': '$parent_shipment_id', 'n': {'$sum': 1},
                        'ids': {'$push': '$id'}}},
        ]).to_list(None)
        child_all_ids = [cid for c in child_agg for cid in (c.get('ids') or [])]
        child_qty_agg = await db.vendor_shipment_items.aggregate([
            {'$match': {'shipment_id': {'$in': child_all_ids}}},
            {'$group': {'_id': '$shipment_id', 'q': {'$sum': '$qty_sent'}}},
        ]).to_list(None) if child_all_ids else []
        qty_by_child = {c['_id']: int(c.get('q') or 0) for c in child_qty_agg}
    else:
        items_all, child_agg, qty_by_child = [], [], {}

    items_by_ship = {}
    for it in items_all:
        items_by_ship.setdefault(it['shipment_id'], []).append(it)
    child_count_by_ship = {c['_id']: c['n'] for c in child_agg}
    child_qty_by_ship = {c['_id']: sum(qty_by_child.get(cid, 0) for cid in (c.get('ids') or []))
                         for c in child_agg}

    # Collect all PO ids referenced, fetch accessory counts in one aggregation
    all_po_ids = set()
    for s in shipments:
        if s.get('po_id'): all_po_ids.add(s['po_id'])
    for it in items_all:
        if it.get('po_id'): all_po_ids.add(it['po_id'])
    if all_po_ids:
        acc_agg = await db.po_accessories.aggregate([
            {'$match': {'po_id': {'$in': list(all_po_ids)}}},
            {'$group': {'_id': '$po_id', 'n': {'$sum': 1}}},
        ]).to_list(None)
        acc_count_by_po = {a['_id']: a['n'] for a in acc_agg}
    else:
        acc_count_by_po = {}

    result = []
    for s in shipments:
        items = items_by_ship.get(s['id'], [])
        child_ships = child_count_by_ship.get(s['id'], 0)
        po_ids_s = {s['po_id']} if s.get('po_id') else set()
        for item in items:
            if item.get('po_id'): po_ids_s.add(item['po_id'])
        # Surat jalan ANAK tidak membawa kebutuhan aksesoris PO (lihat catatan di
        # `get_vendor_shipment`) — hitungannya harus 0 supaya panel aksesoris di
        # daftar tidak menjanjikan barang yang tidak ada di kiriman itu.
        po_acc_count = (0 if s.get('parent_shipment_id')
                        else sum(acc_count_by_po.get(pid, 0) for pid in po_ids_s))
        result.append({**serialize_doc(s), 'items': serialize_doc(items),
                       'child_shipment_count': child_ships, 'has_children': child_ships > 0,
                       'child_qty_total': child_qty_by_ship.get(s['id'], 0),
                       'po_accessories_count': po_acc_count})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@router.get("/vendor-shipments/{sid}")
async def get_vendor_shipment(sid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    s = await db.vendor_shipments.find_one({'id': sid}, {'_id': 0})
    if not s: raise HTTPException(404, 'Not found')
    # Scoping vendor & mode override (staf DA atas nama vendor).
    _ov = await resolve_override(request, user, db)
    if is_vendor(user) and s.get('vendor_id') != vendor_identity(user):
        raise HTTPException(403, 'Pengiriman ini bukan milik vendor Anda')
    if _ov and s.get('vendor_id') != _ov['vendor_id']:
        raise HTTPException(403, f"Pengiriman ini bukan milik {_ov['vendor_name']}")
    items = await db.vendor_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(None)
    # Get accessory shipment items if this is an accessory additional shipment
    accessory_items = await db.accessory_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(None)
    child_ships = await db.vendor_shipments.find({'parent_shipment_id': sid}, {'_id': 0}).to_list(None)
    # ── 10E: batch child ship items in 2 queries instead of 2N ──
    child_ids = [cs['id'] for cs in child_ships]
    cs_items_all  = await db.vendor_shipment_items.find({'shipment_id': {'$in': child_ids}}, {'_id': 0}).to_list(None) if child_ids else []
    cs_acc_all    = await db.accessory_shipment_items.find({'shipment_id': {'$in': child_ids}}, {'_id': 0}).to_list(None) if child_ids else []
    cs_items_map: dict = {}
    for it in cs_items_all: cs_items_map.setdefault(it.get('shipment_id'), []).append(it)
    cs_acc_map: dict = {}
    for it in cs_acc_all: cs_acc_map.setdefault(it.get('shipment_id'), []).append(it)
    child_with_items = [
        {**serialize_doc(cs),
         'items': serialize_doc(cs_items_map.get(cs['id'], [])),
         'accessory_items': serialize_doc(cs_acc_map.get(cs['id'], []))}
        for cs in child_ships
    ]
    # ── 10E: batch PO accessories + PO info in 2 queries instead of 2N ──
    # ═══════════════════════════════════════════════════════════════════════
    # SURAT JALAN ANAK TIDAK MEMBAWA AKSESORIS PO (keluhan pemilik 2026-06)
    # ═══════════════════════════════════════════════════════════════════════
    # `po_accessories` adalah KEBUTUHAN aksesoris seluruh PO — bukan isi kiriman.
    # Untuk surat jalan ANAK (ADDITIONAL/REPLACEMENT/REWORK) isinya hanya barang
    # yang benar-benar dikirim ulang, jadi mengirimkan daftar aksesoris PO membuat
    # form inspeksi vendor memuat baris aksesoris yang TIDAK pernah dikirim →
    # vendor mengisinya "kurang" → lahir permintaan aksesoris palsu, dan kiriman
    # pengganti "selalu membawa aksesoris". Dibuktikan
    # `scripts/_repro_5bug_produksi_maklon.py` (BUG 5), dijaga INV-F27.
    # Aksesoris pada surat jalan anak HANYA dari `accessory_shipment_items`-nya.
    is_child = bool(s.get('parent_shipment_id'))
    po_ids: set = set()
    if not is_child:
        if s.get('po_id'):
            po_ids.add(s['po_id'])
        for item in items:
            if item.get('po_id'):
                po_ids.add(item['po_id'])
    po_ids_list = list(po_ids)
    all_po_accs = await db.po_accessories.find({'po_id': {'$in': po_ids_list}}, {'_id': 0}).to_list(None) if po_ids_list else []
    all_po_docs = await db.production_pos.find({'id': {'$in': po_ids_list}}, {'_id': 0, 'id': 1, 'po_number': 1}).to_list(None) if po_ids_list else []
    po_num_map = {doc['id']: doc.get('po_number', '') for doc in all_po_docs}
    po_accessories_all = []
    for acc in all_po_accs:
        acc['po_number'] = po_num_map.get(acc.get('po_id'), '')
        po_accessories_all.append(acc)
    po_info_map = po_num_map
    items = await enrich_with_product_photos(items, db)
    result = serialize_doc(s)
    result['items'] = serialize_doc(items)
    result['accessory_items'] = serialize_doc(accessory_items)
    result['child_shipments'] = child_with_items
    result['po_accessories'] = serialize_doc(po_accessories_all)
    # ── RANTAI PENGGANTI TERLACAK DUA ARAH (INV-F28) ──────────────────────────
    # Anak menunjuk balik ke permintaan yang melahirkannya, induk melaporkan
    # berapa pcs yang sudah dikirim ulang. Tanpa ini surat jalan pengganti
    # muncul di daftar tanpa penjelasan asal-usulnya.
    result['child_qty_total'] = sum(
        int(it.get('qty_sent') or 0) for cs in child_with_items for it in (cs.get('items') or []))
    result['child_qty_by_type'] = {}
    for cs in child_with_items:
        t = (cs.get('shipment_type') or 'REPLACEMENT').upper()
        result['child_qty_by_type'][t] = result['child_qty_by_type'].get(t, 0) + sum(
            int(it.get('qty_sent') or 0) for it in (cs.get('items') or []))
    if is_child and s.get('material_request_id'):
        mr = await db.material_requests.find_one(
            {'id': s['material_request_id']},
            {'_id': 0, 'request_number': 1, 'request_type': 1, 'reason': 1, 'approved_by': 1})
        result['material_request_number'] = (mr or {}).get('request_number', '')
        result['material_request_type'] = (mr or {}).get('request_type', '')
        result['material_request_reason'] = (mr or {}).get('reason', '')
    # Layar perlu tahu ALASANNYA kosong, bukan sekadar kosong.
    result['accessories_scope'] = 'own' if is_child else 'po'
    result['is_child_shipment'] = is_child
    result['allowed_next'] = ['Received'] if s.get('status') == 'Sent' else []
    return result

@router.post("/vendor-shipments")
async def create_vendor_shipment(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    vendor = await resolve_vendor_doc(db, body.get('vendor_id'))
    if not vendor: raise HTTPException(404, 'Vendor not found')
    dup = await db.vendor_shipments.find_one({'shipment_number': body.get('shipment_number')})
    if dup: raise HTTPException(400, f'Nomor shipment "{body.get("shipment_number")}" sudah digunakan')
    items_data = body.get('items', [])
    # Derive po_id and po_number from items if all items reference the same PO
    shipment_po_id = body.get('po_id', '')
    shipment_po_number = body.get('po_number', '')
    if not shipment_po_id and items_data:
        po_ids_in_items = list(set(i.get('po_id') for i in items_data if i.get('po_id')))
        if len(po_ids_in_items) == 1:
            shipment_po_id = po_ids_in_items[0]
            po_doc = await db.production_pos.find_one({'id': shipment_po_id}, {'_id': 0})
            shipment_po_number = po_doc.get('po_number', '') if po_doc else ''
    for item in items_data:
        if item.get('po_id'):
            po = await db.production_pos.find_one({'id': item['po_id']})
            if po and po.get('vendor_id') and po['vendor_id'] != body['vendor_id']:
                raise HTTPException(400, f"PO {po.get('po_number')} ditujukan untuk vendor lain")
    # ── FASE 3 (cacat CRIT SSOT-1b) — VALIDASI FK po_id / po_item_id ──────────
    # Dibuktikan audit 2026-07-31: endpoint ini MENERIMA `po_id` yang tidak ada di
    # `production_pos` dan tetap balas HTTP 201 ⇒ terbentuk surat jalan material
    # YATIM (`po_number` kosong, `business_type` jatuh ke 'internal'). Kesalahan
    # tidak pernah terlihat dan datanya jadi sampah. Sekarang: 400 yang jelas.
    _po_ids_seen = {i.get('po_id') for i in items_data if i.get('po_id')}
    if body.get('po_id'):
        _po_ids_seen.add(body['po_id'])
    for _pid in _po_ids_seen:
        if not await db.production_pos.find_one({'id': _pid}, {'_id': 1}):
            raise HTTPException(
                400, f"PO tidak ditemukan di data produksi (po_id={_pid}). "
                     "PO Maklon lama yang dibuat sebelum penyatuan SSOT perlu dimigrasi "
                     "dulu (scripts/migrate_orphan_maklon_pos.py).")
    for _it in items_data:
        if _it.get('po_item_id') and not await db.po_items.find_one({'id': _it['po_item_id']}, {'_id': 1}):
            raise HTTPException(400, f"Item PO tidak ditemukan (po_item_id={_it['po_item_id']})")
    # Phase 8.5 — NORMAL shipment over-ship guard (reject lines that exceed remaining qty to vendor)
    shipment_type = body.get('shipment_type', 'NORMAL')
    if shipment_type == 'NORMAL':
        # (a) reject duplicate po_item_id within this shipment
        seen_item_ids = []
        for item in items_data:
            pid = item.get('po_item_id')
            if not pid:
                continue
            if pid in seen_item_ids:
                raise HTTPException(400, f"PO Item terduplikasi dalam shipment yang sama (po_item_id={pid})")
            seen_item_ids.append(pid)
        # (b) ensure each line does not exceed remaining qty (ordered - already sent)
        for item in items_data:
            pid = item.get('po_item_id')
            if not pid:
                continue
            po_item_doc = await db.po_items.find_one({'id': pid})
            if not po_item_doc:
                raise HTTPException(400, f"PO Item tidak ditemukan (po_item_id={pid})")
            ordered = int(po_item_doc.get('qty', 0) or 0)
            prev_vsis = await db.vendor_shipment_items.find({'po_item_id': pid}).to_list(None)
            already_sent = sum(int(v.get('qty_sent', 0) or 0) for v in prev_vsis)
            remaining = max(0, ordered - already_sent)
            qty_sent_now = int(item.get('qty_sent', 0) or 0)
            if remaining <= 0:
                raise HTTPException(400, f"Item PO '{po_item_doc.get('product_name','')}' sudah fully shipped ke vendor (ordered={ordered}, dikirim={already_sent}). Tidak bisa membuat NORMAL shipment lagi.")
            if qty_sent_now > remaining:
                raise HTTPException(400, f"Qty dikirim ({qty_sent_now}) melebihi sisa qty ke vendor ({remaining}) untuk item '{po_item_doc.get('product_name','')}'. Kurangi qty atau gunakan permintaan ADDITIONAL.")
    shipment_business_type = 'internal'
    if shipment_po_id:
        _po_bt = await db.production_pos.find_one({'id': shipment_po_id}, {'_id': 0, 'business_type': 1})
        shipment_business_type = (_po_bt or {}).get('business_type', 'internal')
    shipment_id = new_id()
    shipment = {
        'id': shipment_id, 'shipment_number': body.get('shipment_number'),
        'delivery_note_number': body.get('delivery_note_number', ''),
        'vendor_id': body['vendor_id'], 'vendor_name': vendor.get('garment_name', ''),
        'po_id': shipment_po_id, 'po_number': shipment_po_number,
        'shipment_date': parse_date(body.get('shipment_date')) or now(),
        'shipment_type': body.get('shipment_type', 'NORMAL'),
        'parent_shipment_id': body.get('parent_shipment_id'),
        'business_type': shipment_business_type,
        'status': 'Sent', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.vendor_shipments.insert_one(shipment)
    inserted_items = []
    affected_pos = set()
    for item in items_data:
        po_item = await db.po_items.find_one({'id': item.get('po_item_id')}) if item.get('po_item_id') else None
        si = {
            'id': new_id(), 'shipment_id': shipment_id, 'shipment_number': body.get('shipment_number'),
            'po_id': item.get('po_id'), 'po_number': item.get('po_number'),
            'po_item_id': item.get('po_item_id'),
            'source_po_item_id': item.get('po_item_id'),
            'product_name': (po_item or {}).get('product_name', item.get('product_name', '')),
            'serial_number': (po_item or {}).get('serial_number', item.get('serial_number', '')),
            'size': (po_item or {}).get('size', item.get('size', '')),
            'color': (po_item or {}).get('color', item.get('color', '')),
            'sku': (po_item or {}).get('sku', item.get('sku', '')),
            'qty_sent': int(item.get('qty_sent', 0) or 0),
            'ordered_qty': (po_item or {}).get('qty', int(item.get('ordered_qty', 0) or 0)),
            'shipment_type': body.get('shipment_type', 'NORMAL'),
            'parent_shipment_id': body.get('parent_shipment_id'),
            'created_at': now()
        }
        await db.vendor_shipment_items.insert_one(si)
        inserted_items.append(si)
        if item.get('po_id'): affected_pos.add(item['po_id'])
    for pid in affected_pos:
        po = await db.production_pos.find_one({'id': pid})
        if po and po.get('status') == 'Draft':
            await db.production_pos.update_one({'id': pid}, {'$set': {'status': 'Distributed', 'updated_at': now()}})

    # ═════════════════════════════════════════════════════════════════════════
    # FASE H-1 (2026-08-15) — MENGIRIM MATERIAL KE CMT MENGURANGI STOK GUDANG
    # ═════════════════════════════════════════════════════════════════════════
    # CACAT NYATA yang ditutup di sini (keluhan pemilik: "kirim material ke cmt —
    # bahan dikirimkan dan berkurang, tidak perlu ada ketik ketik lagi"):
    # endpoint ini DULU hanya menulis `vendor_shipments` + `vendor_shipment_items`,
    # dan baris itemnya adalah PO ITEM GARMEN (`sku`/`size`/`qty_sent`) — bukan
    # material. Tidak ada mutasi stok, tidak ada dokumen pengeluaran, tidak ada
    # jurnal. Akibatnya kain & aksesoris keluar gudang TANPA JEJAK dan stok gudang
    # tidak pernah turun; nilai persediaan menggelembung tanpa ada yang tahu.
    #
    # Sekarang: kebutuhan material dihitung dari BOM aktif (model × ukuran × qty
    # dikirim, satuan dikonversi lewat SSOT `core.bom_uom`), Material Issue
    # DITERBITKAN OTOMATIS, stok dipotong lewat mesin yang SAMA dengan approve MI
    # (`core.material_issue_engine`), dan jurnal ikut terposting.
    #
    # KEPUTUSAN PEMILIK: stok kurang ⇒ pengiriman DITOLAK dengan angka yang jelas,
    # BUKAN diteruskan menjadi stok minus. Karena itu bila penerbitan MI gagal,
    # surat jalan yang baru dibuat DIBATALKAN kembali (tidak meninggalkan dokumen
    # setengah jadi — pelajaran surat jalan yatim di Fase E).
    material_issue = None
    # HANYA untuk produksi INTERNAL. Pada MAKLON, material adalah milik KLIEN dan
    # datang lewat kiriman klien — bukan stok gudang DA. Aturan ini bukan tebakan:
    # `production_internal_adapter.create_mi_draft_from_job()` sudah menolak job
    # maklon dengan alasan yang sama ("maklon: material dari klien via shipment").
    # Memotong stok DA untuk maklon justru akan MENGHILANGKAN kain milik DA yang
    # tidak pernah dikirim.
    _is_material_out = (
        shipment_business_type != 'maklon'
        and body.get('shipment_type', 'NORMAL') in ('NORMAL', 'ADDITIONAL', 'REPLACEMENT')
        and not is_vendor(user)
    )
    if _is_material_out:
        from core import material_issue_engine as mie

        async def _rollback_shipment():
            await db.vendor_shipment_items.delete_many({'shipment_id': shipment_id})
            await db.vendor_shipments.delete_one({'id': shipment_id})

        try:
            material_issue = await mie.issue_for_vendor_shipment(
                db, shipment, inserted_items, user)
        except mie.MaterialShortage as e:
            await _rollback_shipment()
            lines = '; '.join(
                f"{s['material_code']} butuh {s['required']:g} {s.get('unit', '')}"
                f" tersedia {s['available']:g}" for s in e.shortages)
            raise HTTPException(
                400,
                'Surat jalan TIDAK dibuat: stok material di gudang tidak cukup untuk '
                f'kiriman ini. {lines}. Tambah stok (penerimaan/opname) atau kurangi '
                'qty kirim, lalu coba lagi.')
        except mie.BomMissing as e:
            await _rollback_shipment()
            raise HTTPException(400, f'Surat jalan TIDAK dibuat: {e}')
        except Exception as e:  # noqa: BLE001
            await _rollback_shipment()
            logger.exception('penerbitan Material Issue otomatis gagal (SJ %s)',
                             body.get('shipment_number'))
            raise HTTPException(
                500,
                'Surat jalan TIDAK dibuat: gagal menerbitkan dokumen pengeluaran '
                f'material ({e}). Tidak ada stok yang dipotong.')

    await log_activity(user['id'], user['name'], 'Create', 'Vendor Shipment', f"Created shipment {body.get('shipment_number')}")
    result = serialize_doc(shipment)
    result['items'] = serialize_doc(inserted_items)
    if material_issue:
        result['material_issue'] = {
            'mi_number': (material_issue.get('mi') or {}).get('mi_number')
                         or material_issue.get('mi_number'),
            'material_lines': material_issue.get('material_lines'),
            'bom_notes': material_issue.get('bom_notes') or [],
            'already_existed': material_issue.get('already', False),
        }
    return JSONResponse(result, status_code=201)

@router.put("/vendor-shipments/{sid}")
async def update_vendor_shipment(sid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES + PROD_VENDOR_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    # Portal CMT Override — staf DA menandai "Diterima" ATAS NAMA vendor.
    _ov = await resolve_override(request, user, db)
    _cur_ship = await db.vendor_shipments.find_one({'id': sid}, {'_id': 0, 'vendor_id': 1})
    if not _cur_ship: raise HTTPException(404, 'Shipment not found')
    if is_vendor(user) and _cur_ship.get('vendor_id') != vendor_identity(user):
        raise HTTPException(403, 'Pengiriman ini bukan milik vendor Anda')
    if _ov and _cur_ship.get('vendor_id') != _ov['vendor_id']:
        raise HTTPException(403, f"Pengiriman ini bukan milik {_ov['vendor_name']}")
    _stamp = ov_stamp(_ov)
    if _stamp:
        # Jejak penerimaan diberi prefiks `receipt_` supaya tidak menimpa jejak
        # pembuatan surat jalan (dibuat DA) — dua peristiwa berbeda, dua jejak.
        body.update({f'receipt_{k}': v for k, v in _stamp.items()})
    # DA BUG-FIX: state machine shipment di-enforce (hanya Sent → Received).
    cur_doc = None
    if 'status' in body:
        if body['status'] not in ('Sent', 'Received'):
            raise HTTPException(400, "Status shipment hanya 'Sent' atau 'Received'")
        cur_doc = await db.vendor_shipments.find_one({'id': sid}, {'_id': 0, 'status': 1})
        if not cur_doc: raise HTTPException(404, 'Shipment not found')
        cur = cur_doc.get('status', 'Sent')
        if body['status'] != cur and not (cur == 'Sent' and body['status'] == 'Received'):
            raise HTTPException(400,
                f"Transisi status shipment ilegal: '{cur}' → '{body['status']}' (hanya 'Sent' → 'Received')")
    # ── BUG-FIX 2026-08-08 (Rekap Harian) — `received_at` diisi SERVER ────────
    # SEBELUM: satu-satunya penulis `received_at` adalah browser
    # (`VendorReceiving.jsx` mengirim `received_at: new Date()`), sehingga:
    #   1) nilainya masuk sebagai STRING ISO, sementara semua field waktu lain
    #      bertipe Date ⇒ query rentang `{$gte: Date, $lt: Date}` TIDAK PERNAH
    #      cocok (Mongo mengurutkan antar-tipe, bukan membandingkan nilai) ⇒
    #      kolom "Terima" di Rekap Harian akan selalu ✗ walau barang diterima;
    #   2) jamnya = jam komputer staf; kalau salah setel, TANGGAL PENERIMAAN
    #      material ikut salah — dan tanggal itu dipakai laporan.
    # SEKARANG: server yang menetapkan waktunya (kiriman browser diabaikan),
    # dan hanya sekali (transisi Sent → Received), bukan tiap kali di-PUT.
    body.pop('received_at', None)
    if body.get('status') == 'Received' and (cur_doc or {}).get('status') != 'Received':
        body['received_at'] = now()
    await db.vendor_shipments.update_one({'id': sid}, {'$set': {**body, 'updated_at': now()}})
    # ── Phase A Fix A2 (2026-07-16, GUIDELINE_CMT_FLOW.md §9.3) ──────────────
    # Retro-safety net: kalau shipment ADDITIONAL/REPLACEMENT baru dijadikan
    # 'Received' padahal inspeksinya sudah selesai duluan (bug pre-fix data),
    # create child_job sekarang (self-heal). Idempotent via helper.
    if body.get('status') == 'Received':
        ship = await db.vendor_shipments.find_one({'id': sid})
        if ship and ship.get('parent_shipment_id'):
            already_job = await db.production_jobs.find_one(
                {'vendor_shipment_id': sid}, {'_id': 0, 'id': 1}
            )
            if not already_job:
                insp = await db.vendor_material_inspections.find_one({'shipment_id': sid})
                if insp:
                    insp_items = await db.vendor_material_inspection_items.find(
                        {'inspection_id': insp['id']}
                    ).to_list(None)
                    await _create_child_job_from_inspection(db, ship, insp, insp_items, user['name'])
    await log_activity(user['id'], user['name'], 'Update', 'Vendor Shipment', f"Updated shipment: {sid}")
    return serialize_doc(await db.vendor_shipments.find_one({'id': sid}, {'_id': 0}))

@router.delete("/vendor-shipments/{sid}")
async def delete_vendor_shipment(sid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.vendor_shipments.find_one({'id': sid})
    if not doc: raise HTTPException(404, 'Not found')
    inspections = await db.vendor_material_inspections.find({'shipment_id': sid}).to_list(None)
    for insp in inspections:
        await db.vendor_material_inspection_items.delete_many({'inspection_id': insp['id']})
    await db.vendor_material_inspections.delete_many({'shipment_id': sid})
    jobs = await db.production_jobs.find({'vendor_shipment_id': sid}).to_list(None)
    for job in jobs:
        child_jobs = await db.production_jobs.find({'parent_job_id': job['id']}).to_list(None)
        for cj in child_jobs:
            await db.production_job_items.delete_many({'job_id': cj['id']})
            await db.production_progress.delete_many({'job_id': cj['id']})
            await db.production_jobs.delete_one({'id': cj['id']})
        await db.production_job_items.delete_many({'job_id': job['id']})
        await db.production_progress.delete_many({'job_id': job['id']})
        await db.production_jobs.delete_one({'id': job['id']})
    await db.material_requests.delete_many({'original_shipment_id': sid})
    child_ships = await db.vendor_shipments.find({'parent_shipment_id': sid}).to_list(None)
    for cs in child_ships:
        await db.vendor_shipment_items.delete_many({'shipment_id': cs['id']})
        await db.vendor_shipments.delete_one({'id': cs['id']})
    await db.vendor_shipment_items.delete_many({'shipment_id': sid})
    await db.vendor_shipments.delete_one({'id': sid})
    await log_activity(user['id'], user['name'], 'Delete', 'Vendor Shipment', f"Cascade deleted shipment: {doc.get('shipment_number')}")
    return {'success': True}

# ─── VENDOR MATERIAL INSPECTIONS ─────────────────────────────────────────────

# ── Phase A helper (2026-07-16, GUIDELINE_CMT_FLOW.md §9.3 Fix A3) ──────────
async def _create_child_job_from_inspection(db, shipment: dict, inspection: dict,
                                            inspection_items: list, actor: str) -> str | None:
    """Auto-create production_job (dan production_job_items) untuk shipment
    ADDITIONAL/REPLACEMENT yang inspeksinya baru saja submit.

    Idempotent: bila `production_jobs` sudah ada untuk shipment ini, langsung return None.

    Prekondisi:
      - shipment.parent_shipment_id non-null (harus ADDITIONAL / REPLACEMENT)
      - parent shipment sudah punya `production_jobs` (parent_job)
      - Σreceived_qty pada material items (bukan accessory) > 0

    Return: child_job_id (string) atau None kalau prekondisi belum terpenuhi.
    """
    if not shipment.get('parent_shipment_id'):
        return None
    parent_job = await db.production_jobs.find_one(
        {'vendor_shipment_id': shipment['parent_shipment_id']}, {'_id': 0}
    )
    if not parent_job:
        # Parent job belum di-create — child akan menyusul retroaktif kalau parent muncul.
        return None
    already_exists = await db.production_jobs.find_one(
        {'vendor_shipment_id': shipment['id']}, {'_id': 0, 'id': 1}
    )
    if already_exists:
        return None
    material_items = [i for i in inspection_items if i.get('item_type') != 'accessory']
    total_received = sum(int(i.get('received_qty', 0) or 0) for i in material_items)
    if total_received <= 0:
        # Semua material nol → tidak ada yang bisa diproduksi; skip child job.
        return None

    child_job_id = new_id()
    # RC-5 (2026-08-07) — nomor job ANAK dulu memakai
    # `count_documents({parent_job_id}) + 1`. Dua kiriman tambahan/rework yang
    # diproses bersamaan membaca hitungan yang SAMA lalu menghasilkan nomor job
    # KEMBAR (mis. dua "JOB-0007-A1"), sehingga catatan produksi dua kiriman
    # berbeda saling tertukar. Sekarang urutannya dari counter atomik per JOB
    # INDUK — sama dengan jalur di routes/production_execution.py.
    from utils.counters import next_counter
    suffix = 'A' if shipment.get('shipment_type') == 'ADDITIONAL' else 'R'
    child_seq = await next_counter(
        db, f"autonum:production_jobs:child:{parent_job['id']}:{suffix}",
        namespace='autonum')
    child_job_number = f"{parent_job['job_number']}-{suffix}{child_seq}"
    child_job = {
        'id': child_job_id, 'job_number': child_job_number,
        'parent_job_id': parent_job['id'], 'parent_job_number': parent_job['job_number'],
        'vendor_id': parent_job.get('vendor_id'), 'vendor_name': parent_job.get('vendor_name', ''),
        'po_id': parent_job.get('po_id'), 'po_number': parent_job.get('po_number', ''),
        'customer_name': parent_job.get('customer_name', ''),
        'vendor_shipment_id': shipment['id'],
        'shipment_number': shipment.get('shipment_number'),
        'shipment_type': shipment.get('shipment_type', 'ADDITIONAL'),
        'business_type': parent_job.get('business_type', shipment.get('business_type', 'internal')),
        'deadline': parent_job.get('deadline'),
        'delivery_deadline': parent_job.get('delivery_deadline'),
        'status': 'In Progress',
        'notes': f"Auto-created from {shipment.get('shipment_type')} shipment",
        'created_by': actor, 'created_at': now(), 'updated_at': now(),
    }
    await db.production_jobs.insert_one(child_job)

    ship_items = await db.vendor_shipment_items.find({'shipment_id': shipment['id']}).to_list(None)
    for si in ship_items:
        po_item = (await db.po_items.find_one({'id': si.get('po_item_id')})
                   if si.get('po_item_id') else None)
        matched = next((ii for ii in material_items if ii.get('shipment_item_id') == si['id']), None)
        if not matched:
            matched = next((ii for ii in material_items
                            if ii.get('sku') == si.get('sku')
                            and ii.get('size') == si.get('size', '')), None)
        avail = int(matched.get('received_qty', 0)) if matched else int(si.get('qty_sent', 0) or 0)
        await db.production_job_items.insert_one({
            'id': new_id(), 'job_id': child_job_id, 'job_number': child_job_number,
            'po_item_id': si.get('po_item_id'),
            'vendor_shipment_item_id': si['id'],
            'product_name': si.get('product_name', ''), 'sku': si.get('sku', ''),
            'size': si.get('size', ''), 'color': si.get('color', ''),
            # [RELATION FIX] carry master-data links (buyer catalog / model / variant)
            'catalog_item_id': (po_item or {}).get('catalog_item_id'),
            'maklon_variant_id': (po_item or {}).get('maklon_variant_id'),
            'model_id': (po_item or {}).get('model_id'),
            'rahaza_variant_id': (po_item or {}).get('rahaza_variant_id'),
            'serial_number': (po_item or {}).get('serial_number', si.get('serial_number', '')),
            'ordered_qty': si.get('qty_sent', 0),
            'shipment_qty': si.get('qty_sent', 0),
            'available_qty': avail,
            'produced_qty': 0,
            'created_at': now(),
        })
    return child_job_id


@router.get("/vendor-material-inspections")
async def get_inspections(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    query = {}
    sp = request.query_params
    await apply_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    if sp.get('shipment_id'): query['shipment_id'] = sp['shipment_id']
    inspections = await db.vendor_material_inspections.find(query, {'_id': 0}).sort('created_at', -1).to_list(None)
    # ── 10B-rem: batch-fetch all shipments + inspection items in 2 queries ──
    insp_ids = [insp['id'] for insp in inspections]
    ship_ids_needed = list({insp.get('shipment_id') for insp in inspections if insp.get('shipment_id')})
    all_ship_docs = await db.vendor_shipments.find(
        {'id': {'$in': ship_ids_needed}}, {'_id': 0, 'id': 1, 'shipment_number': 1}
    ).to_list(None) if ship_ids_needed else []
    ship_num_map = {s['id']: s.get('shipment_number', '') for s in all_ship_docs}
    all_insp_items = await db.vendor_material_inspection_items.find(
        {'inspection_id': {'$in': insp_ids}}, {'_id': 0}
    ).to_list(None) if insp_ids else []
    items_by_insp: dict = {}
    for it in all_insp_items:
        items_by_insp.setdefault(it.get('inspection_id'), []).append(it)
    result = []
    for insp in inspections:
        all_items = items_by_insp.get(insp['id'], [])
        mat_items = [i for i in all_items if i.get('item_type') != 'accessory']
        acc_items  = [i for i in all_items if i.get('item_type') == 'accessory']
        result.append({
            **serialize_doc(insp),
            'shipment_number': ship_num_map.get(insp.get('shipment_id'), ''),
            'items': serialize_doc(mat_items),
            'accessory_items': serialize_doc(acc_items),
        })
    return result

@router.post("/vendor-material-inspections")
async def create_inspection(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    _ov = await resolve_override(request, user, db)
    vendor_id = await effective_vendor_id(request, user, db, body.get('vendor_id'))
    # Try to infer vendor_id from shipment if not provided
    if not vendor_id and body.get('shipment_id'):
        ship = await db.vendor_shipments.find_one({'id': body['shipment_id']})
        if ship: vendor_id = ship.get('vendor_id')
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    shipment = await db.vendor_shipments.find_one({'id': body.get('shipment_id')}) if body.get('shipment_id') else None
    if not shipment: raise HTTPException(404, 'Shipment tidak ditemukan')
    if _ov and shipment.get('vendor_id') != _ov['vendor_id']:
        raise HTTPException(403, f"Pengiriman ini bukan milik {_ov['vendor_name']}")
    existing = await db.vendor_material_inspections.find_one({'shipment_id': body['shipment_id']})
    if existing: raise HTTPException(400, 'Inspeksi untuk shipment ini sudah dilakukan')
    inspection_id = new_id()
    items_data = body.get('items', [])
    accessory_items_data = body.get('accessory_items', [])
    total_received = sum(int(i.get('received_qty', 0) or 0) for i in items_data)
    total_missing = sum(int(i.get('missing_qty', 0) or 0) for i in items_data)
    total_acc_received = sum(int(a.get('received_qty', 0) or 0) for a in accessory_items_data)
    total_acc_missing = sum(int(a.get('missing_qty', 0) or 0) for a in accessory_items_data)
    inspection = {
        'id': inspection_id, 'shipment_id': body['shipment_id'],
        'shipment_number': shipment.get('shipment_number', ''),
        'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
        'inspection_date': parse_date(body.get('inspection_date')) or now(),
        'total_received': total_received, 'total_missing': total_missing,
        'total_acc_received': total_acc_received, 'total_acc_missing': total_acc_missing,
        'overall_notes': body.get('overall_notes', ''), 'status': 'Submitted',
        'submitted_by': user['name'], 'created_at': now(), 'updated_at': now(),
        **ov_stamp(_ov),
    }
    await db.vendor_material_inspections.insert_one(inspection)
    for item in items_data:
        await db.vendor_material_inspection_items.insert_one({
            'id': new_id(), 'inspection_id': inspection_id,
            'item_type': 'material',
            'shipment_item_id': item.get('shipment_item_id'),
            'sku': item.get('sku', ''), 'product_name': item.get('product_name', ''),
            'size': item.get('size', ''), 'color': item.get('color', ''),
            'ordered_qty': int(item.get('ordered_qty', 0) or 0),
            'received_qty': int(item.get('received_qty', 0) or 0),
            'missing_qty': int(item.get('missing_qty', 0) or 0),
            'condition_notes': item.get('condition_notes', ''), 'created_at': now()
        })
    for acc in accessory_items_data:
        await db.vendor_material_inspection_items.insert_one({
            'id': new_id(), 'inspection_id': inspection_id,
            'item_type': 'accessory',
            'accessory_id': acc.get('accessory_id', ''),
            'accessory_name': acc.get('accessory_name', ''),
            'accessory_code': acc.get('accessory_code', ''),
            'unit': acc.get('unit', 'pcs'),
            'ordered_qty': int(acc.get('ordered_qty', 0) or 0),
            'received_qty': int(acc.get('received_qty', 0) or 0),
            'missing_qty': int(acc.get('missing_qty', 0) or 0),
            'condition_notes': acc.get('condition_notes', ''), 'created_at': now()
        })
    # Update shipment
    await db.vendor_shipments.update_one({'id': body['shipment_id']}, {'$set': {
        'inspection_status': 'Inspected', 'total_received': total_received,
        'total_missing': total_missing, 'inspected_at': now(), 'updated_at': now()
    }})
    # ── Phase A Fix A1 (2026-07-16, GUIDELINE_CMT_FLOW.md §9.3) ──────────────
    # Auto-create child job for additional/replacement shipment.
    # Inspection = implicit receipt-acknowledgment: promote status to 'Received'
    # if not already, then create child job via helper. Removes race condition
    # where guard `shipment.status == 'Received'` silently skipped child_job creation
    # when frontend inspected before marking Received.
    if shipment.get('parent_shipment_id'):
        if shipment.get('status') != 'Received':
            await db.vendor_shipments.update_one(
                {'id': shipment['id']},
                {'$set': {'status': 'Received', 'received_at': now(), 'updated_at': now()}}
            )
            shipment['status'] = 'Received'
        # refetch just-inserted inspection items for the helper
        _insp_items = await db.vendor_material_inspection_items.find(
            {'inspection_id': inspection_id}
        ).to_list(None)
        await _create_child_job_from_inspection(db, shipment, inspection, _insp_items, user['name'])
    # ═══════════════════════════════════════════════════════════════════════
    # FASE 5 — SATU alur permintaan komponen/material kurang (cacat MAT-1/MAT-3)
    # ═══════════════════════════════════════════════════════════════════════
    # SEBELUM: temuan kurang saat inspeksi ditulis ke `material_requests` —
    # collection yang bahkan TIDAK ADA di DB, tidak punya UI, dan tidak pernah
    # ditautkan ke inspeksi. Sementara "Komponen Kurang"
    # (`dewi_cmt_component_requests`) punya modul UI tapi selalu kosong.
    # SEKARANG: keduanya disatukan → `dewi_cmt_component_requests` = SSOT,
    # WAJIB menunjuk po_id + vendor_id + inspection_id, dan dibuat OTOMATIS dari
    # inspeksi (material maupun aksesoris yang kurang).
    missing_accessories = [a for a in accessory_items_data if int(a.get('missing_qty', 0) or 0) > 0]
    missing_materials = [m for m in items_data if int(m.get('missing_qty', 0) or 0) > 0]
    auto_request = None
    if missing_accessories or missing_materials:
        po_id = shipment.get('po_id', '')
        if not po_id:
            first_si = await db.vendor_shipment_items.find_one({'shipment_id': body['shipment_id']})
            if first_si:
                po_id = first_si.get('po_id', '')
        po_doc = await db.production_pos.find_one({'id': po_id}, {'_id': 0}) if po_id else None
        po_number = (po_doc or {}).get('po_number', '')
        try:
            from utils.counters import gen_prefixed_number as _gen
            code = await _gen(db, 'dewi_cmt_component_requests', 'request_code',
                              f"REQ-KRG-{now().strftime('%y%m%d')}-", 3)
            req_items = [{
                'component_type': m.get('product_name') or m.get('sku', '') or 'material',
                'size': m.get('size', ''), 'color': m.get('color', ''),
                'qty': float(m.get('missing_qty', 0) or 0), 'unit': 'pcs',
                'kind': 'material',
                'notes': m.get('condition_notes', ''),
            } for m in missing_materials] + [{
                'component_type': a.get('accessory_name', '') or a.get('accessory_code', '') or 'aksesoris',
                'size': '', 'color': '',
                'qty': float(a.get('missing_qty', 0) or 0), 'unit': a.get('unit', 'pcs'),
                'kind': 'accessory', 'accessory_id': a.get('accessory_id', ''),
                'accessory_code': a.get('accessory_code', ''),
                'notes': a.get('condition_notes', ''),
            } for a in missing_accessories]
            detail = ', '.join(f"{i['component_type']}({int(i['qty'])} {i['unit']})" for i in req_items)
            auto_request = {
                'id': new_id(), 'request_code': code,
                'request_type': 'accessory' if (missing_accessories and not missing_materials) else 'component',
                'cmt_partner_id': vendor_id, 'cmt_partner_name': shipment.get('vendor_name', ''),
                'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
                'po_id': po_id, 'po_number': po_number,
                'work_order_id': '', 'work_order_code': po_number,
                'product_name': (req_items[0]['component_type'] if req_items else ''),
                'inspection_id': inspection_id,
                'source_shipment_id': body['shipment_id'],
                'source_shipment_number': shipment.get('shipment_number', ''),
                'origin': 'vendor_inspection',
                'items': req_items,
                'urgent': True,
                'needed_by_date': '',
                'notes': f"Otomatis dari inspeksi material {shipment.get('shipment_number', '')}: kurang {detail}",
                'status': 'pending',
                'requester_id': user['id'], 'requester_name': user.get('name', ''),
                'fulfilled_shipment_id': None, 'fulfilled_shipment_number': None,
                'created_at': now(), 'updated_at': now(),
            }
            await db.dewi_cmt_component_requests.insert_one(dict(auto_request))
            # tautkan balik ke inspeksi supaya bisa dilacak dua arah
            await db.vendor_material_inspections.update_one(
                {'id': inspection_id},
                {'$set': {'component_request_id': auto_request['id'],
                          'component_request_code': code}})
        except Exception:
            import logging as _lg
            _lg.getLogger(__name__).exception(
                'FASE 5: gagal auto-buat permintaan komponen dari inspeksi %s', inspection_id)
            auto_request = None

    # ─── Phase 16: Auto REQ-RPL for missing materials REMOVED ───
    # Business rule (Phase 16): Missing during inspection → ADDITIONAL (vendor-driven via modal).
    # Defect/cacat during production → REPLACEMENT (via VendorDefectReports flow).
    # Frontend (VendorMaterialInspection) now opens AdditionalRequestModal so vendor
    # can edit overall + per-item reasons and submit a single REQ-ADD request.

    await log_activity(user['id'], user['name'], 'Create', 'Material Inspection',
                       f"Inspeksi shipment {shipment.get('shipment_number')}: diterima {total_received}, missing {total_missing}, acc diterima {total_acc_received}, acc missing {total_acc_missing}")
    all_item_docs = await db.vendor_material_inspection_items.find({'inspection_id': inspection_id}, {'_id': 0}).to_list(None)
    result = serialize_doc(inspection)
    result['items'] = serialize_doc([i for i in all_item_docs if i.get('item_type') != 'accessory'])
    result['accessory_items'] = serialize_doc([i for i in all_item_docs if i.get('item_type') == 'accessory'])
    if auto_request:
        result['component_request'] = serialize_doc(auto_request)
    return JSONResponse(result, status_code=201)
