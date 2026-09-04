"""Production PO Core domain: Production POs, PO Items, PO Status Transition,
PO Quantity Summary, PO Accessories (add-on).

Moved out of server.py during Backend Refactor Phase 4
(see /app/BACKEND_REFACTOR_PLAN.md). Pure move — behavior is byte-for-byte
identical to the original definitions in server.py. This is the most central
entity in the ERP (HIGH risk phase per the plan) — every line below is an
exact cut-paste from server.py, no logic was altered.
"""
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from routes.production_rbac import (PROD_ADMIN_ROLES, PROD_VENDOR_ROLES,
    is_vendor, vendor_identity, deny_klien, require_write_actor,
    resolve_vendor_doc, resolve_buyer_name)
from cascade_delete import cascade_delete_po
from core.helpers import new_id, now, parse_date
from core.pagination import LEGACY_DEFAULT_CAP, _paginate_params, _paginated_envelope, _sort_params
from core.enrichment import enrich_with_product_photos
from utils.variant_ssot import build_variant_sku
from utils.waktu import now_wib

router = APIRouter(prefix="/api", tags=["production-pos"])

# Valid PO statuses (staged lifecycle)
PO_STATUSES = [
    "Draft", "Confirmed", "Distributed", "In Production", 
    "Production Complete", "Variance Review", "Return Review",
    "Ready to Close", "Closed",
    # Phase C (2026-07-17) — terminal closure states.
    "Completed",     # auto-close on 100% buyer fulfillment
    "Closed Short",  # manual close < 100% (deadline / shortage / reject / mutual)
]

# ── DA BUG-FIX (kategori C-1..M-3): state machine PO di-enforce.
# Referensi SOMMERVILLE hanya memvalidasi keanggotaan PO_STATUSES tanpa cek
# urutan (Draft bisa langsung Closed). Matrix mengikuti PRODUKSI_TOBE_FLOW_FINAL.
# Review states (Variance/Return) opsional: boleh dilewati atau bertukar urutan.
PO_STATUS_TRANSITIONS = {
    'Draft': ['Confirmed'],
    'Confirmed': ['Distributed'],
    'Distributed': ['In Production'],
    'In Production': ['Production Complete'],
    'Production Complete': ['Variance Review', 'Return Review', 'Ready to Close'],
    'Variance Review': ['Return Review', 'Ready to Close'],
    'Return Review': ['Variance Review', 'Ready to Close'],
    'Ready to Close': ['Closed'],
    'Closed': [],
    # Phase C terminal states. GAP G: 'Completed' TIDAK lagi buntu — selisih terima
    # buyer yang ketahuan belakangan boleh diselesaikan lewat 'Closed Short'.
    'Completed': ['Closed Short'],
    'Closed Short': [],
}
# Manual close (dengan close_reason) hanya sah setelah produksi selesai.
PO_CLOSABLE_STATUSES = ['Production Complete', 'Variance Review', 'Return Review', 'Ready to Close']

# ── Phase C (2026-07-17) — PO Closure Rules ──────────────────────────────────
# Manual close-short reasons (§11.2). Endpoint: POST /production-pos/{id}/close-short.
CLOSE_SHORT_REASONS = {
    'deadline_expired', 'buyer_material_shortage',
    'cmt_quality_reject_final', 'mutual_agreement',
}
# Statuses from which a manual close-short is legal (§11.3).
# GAP G (audit 2026-07-31 + keputusan owner 2026-08-01): selisih terima buyer
# sering baru ketahuan SETELAH PO otomatis ditutup 'Completed'. Dulu close-short
# ditolak dari 'Completed' ("status final") sehingga selisih mentok tanpa tindak
# lanjut. Sekarang penyesuaian pasca-Completed DIIZINKAN (tetap butuh alasan +
# qty_short > 0 + jejak audit) supaya keputusan finance bisa dijalankan.
CLOSE_SHORT_ALLOWED_FROM = [
    'In Production', 'Production Complete', 'Variance Review',
    'Return Review', 'Ready to Close', 'Completed',
]


async def _resolve_rahaza_variant(db, item: dict):
    """Fase 2: bila item PO internal memilih varian ber-SKU (rahaza_model_variants),
    resolve varian → inject model_id/size_id ke `item` (agar validasi model/size lolos)
    dan kembalikan dokumen varian. Return None bila item tidak memakai varian.
    Menerima `rahaza_variant_id` (kanonik) atau alias `variant_sku`."""
    rv_id = item.get('rahaza_variant_id')
    variant = None
    if rv_id:
        variant = await db.rahaza_model_variants.find_one(
            {'id': rv_id, 'active': {'$ne': False}}, {'_id': 0})
        if not variant:
            raise HTTPException(400, f"Varian '{rv_id}' tidak ditemukan atau non-aktif.")
    elif item.get('variant_sku'):
        variant = await db.rahaza_model_variants.find_one(
            {'sku': str(item['variant_sku']).strip().upper(), 'active': {'$ne': False}}, {'_id': 0})
    if variant:
        # Inject master FK agar validate_internal_item lolos & konsisten
        item['model_id'] = variant['model_id']
        item['size_id'] = variant['size_id']
    return variant



# ─── PRODUCTION POs ──────────────────────────────────────────────────────────
@router.get("/production-pos")
async def get_pos(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    query = {}
    search = sp.get('search'); status = sp.get('status'); vendor_id = sp.get('vendor_id')
    if search: query['$or'] = [{'po_number': {'$regex': search, '$options': 'i'}}, {'customer_name': {'$regex': search, '$options': 'i'}}]
    if status: query['status'] = status
    if vendor_id: query['vendor_id'] = vendor_id
    # FASE 5: filter business_type utk UI (maklon | internal)
    business_type = sp.get('business_type')
    if business_type == 'internal':
        query['business_type'] = 'internal'
    elif business_type == 'maklon':
        query['business_type'] = {'$ne': 'internal'}

    # Paginate the parent PO query (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'po_number', 'customer_name', 'vendor_name',
                                 'status', 'deadline', 'delivery_deadline'})
    total = await db.production_pos.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.production_pos.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    pos = await cursor.to_list(limit)

    # ── Phase 10B: eliminate N+1 by batch-fetching all related rows once ──
    po_ids = [po['id'] for po in pos]
    if po_ids:
        items_all = await db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None)
        accs_all = await db.po_accessories.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(None)
        item_ids = [i['id'] for i in items_all]
        # Aggregate shipment totals per po_item_id in a single query each
        buyer_agg = await db.buyer_shipment_items.aggregate([
            {'$match': {'po_item_id': {'$in': item_ids}}},
            {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_shipped'},
                        'recv': {'$sum': {'$ifNull': ['$qty_received', '$qty_shipped']}}}},
        ]).to_list(None) if item_ids else []
        vendor_agg = await db.vendor_shipment_items.aggregate([
            {'$match': {'po_item_id': {'$in': item_ids}}},
            {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_sent'}}},
        ]).to_list(None) if item_ids else []
    else:
        items_all, accs_all, buyer_agg, vendor_agg = [], [], [], []

    # Build maps
    items_by_po = {}
    for it in items_all:
        items_by_po.setdefault(it['po_id'], []).append(it)
    accs_by_po = {}
    for a in accs_all:
        accs_by_po.setdefault(a['po_id'], []).append(a)
    buyer_by_item = {b['_id']: b['qty'] for b in buyer_agg}
    recv_by_item = {b['_id']: b['recv'] for b in buyer_agg}
    vendor_by_item = {v['_id']: v['qty'] for v in vendor_agg}

    result = []
    for po in pos:
        items = items_by_po.get(po['id'], [])
        po_accessories = accs_by_po.get(po['id'], [])
        serial_numbers = list({i.get('serial_number', '') for i in items if i.get('serial_number')})
        created = po.get('created_at')
        date_str = ''
        if created:
            if isinstance(created, datetime):
                date_str = created.strftime('%d/%m/%Y')
            else:
                date_str = str(created)[:10]
        composite_label = f"{po.get('po_number', '')} | {po.get('vendor_name', '')} | {date_str}"

        total_ordered = sum(i.get('qty', 0) for i in items)
        total_shipped = sum(buyer_by_item.get(i['id'], 0) for i in items)
        total_received = sum(recv_by_item.get(i['id'], 0) for i in items)
        total_sent_to_vendor = sum(vendor_by_item.get(i['id'], 0) for i in items)
        # ─── H-1 FIX: clamp remaining at 0 (preserves dashboard semantics),
        # expose over_shipped_qty separately so overproduction shipping is visible.
        remaining_qty_to_ship = max(0, total_ordered - total_received)
        over_shipped_qty = max(0, total_shipped - total_ordered)
        # Phase 8.5: remaining qty the vendor still needs to receive (NORMAL shipment capacity)
        remaining_qty_to_vendor = max(0, total_ordered - total_sent_to_vendor)

        result.append({**serialize_doc(po), 'items': serialize_doc(items), 'item_count': len(items),
                       'total_qty': total_ordered,
                       'total_shipped_to_buyer': total_shipped,
                       'total_received_to_buyer': total_received,
                       'remaining_qty_to_ship': remaining_qty_to_ship,
                       'over_shipped_qty': over_shipped_qty,
                       'total_sent_to_vendor': total_sent_to_vendor,
                       'remaining_qty_to_vendor': remaining_qty_to_vendor,
                       'serial_numbers': serial_numbers, 'composite_label': composite_label,
                       'po_accessories': serialize_doc(po_accessories),
                       'po_accessories_count': len(po_accessories)})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@router.get("/production-pos/{po_id}")
async def get_po(po_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po: raise HTTPException(404, 'Not found')
    items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    wos = await db.work_orders.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    po_accessories = await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)
    items = await enrich_with_product_photos(items, db)
    result = serialize_doc(po)
    result['items'] = serialize_doc(items)
    result['distributions'] = serialize_doc(wos)
    result['po_accessories'] = serialize_doc(po_accessories)
    # FE dapat merender tombol aksi dinamis dari daftar transisi valid
    result['allowed_next'] = PO_STATUS_TRANSITIONS.get(po.get('status', 'Draft'), [])
    result['can_close'] = po.get('status') in PO_CLOSABLE_STATUSES
    return result

@router.post("/production-pos")
async def create_po(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    result = await create_po_internal(db, body, user)
    return JSONResponse(result, status_code=201)


async def create_po_internal(db, body: dict, user: dict, *,
                             number_issued: bool = False) -> dict:
    """FASE 3 — SATU jalur pembuatan PO produksi (internal & maklon).

    Diekstrak dari handler `POST /api/production-pos` supaya Portal MAKLON bisa
    memakai jalur YANG SAMA (`routes/dewi_maklon_pos._create_engine_po_for_maklon`),
    bukan menulis PO asli ke collection mirror `dewi_maklon_pos`.
    Pelajaran audit 2026-07-31: dua penulis PO = dua sumber kebenaran = 10 PO yatim
    dengan status produksi palsu.

    `number_issued=True` (FASE G): nomornya SUDAH diterbitkan oleh jenis dokumen
    ASALNYA — dipakai jalur cermin PO Maklon yang nomornya lahir dari
    `dewi_maklon_pos.po_number`. Menerbitkan ulang di sini berarti satu dokumen
    punya dua penomoran; memvalidasinya dengan pola milik jenis dokumen LAIN akan
    menolak nomor yang justru dibuat sistem sendiri.
    """
    # FASE G (2026-08-16) — nomor PO lewat SATU kebijakan (auto/manual).
    # Dulu barisnya `if not body.get('po_number'): raise ...` lalu nomor apa pun
    # yang dikirim disimpan APA ADANYA. Itu sebabnya arsip PO bercampur
    # `PO-INT-DEMO-1`, `PO-MK-DEMO-1`, `PO-MKL-GAB-A` — tiga pola untuk satu jenis
    # dokumen, tidak bisa diurutkan maupun dicari. Bawaan tetap MANUAL supaya cara
    # kerja hari ini tidak berubah; yang baru: nomor manual wajib mengikuti polanya,
    # dan owner boleh memindahkannya ke OTOMATIS dari layar Penomoran Dokumen.
    business_type = body.get('business_type', 'internal')
    if business_type not in ('internal', 'maklon'):
        raise HTTPException(400, "business_type harus 'internal' atau 'maklon'")
    if number_issued:
        po_number = (body.get('po_number') or '').strip()
        if not po_number:
            raise HTTPException(400, 'Nomor PO wajib diisi')
        if await db.production_pos.find_one({'po_number': po_number}, {'_id': 1}):
            raise HTTPException(409, f"Nomor PO '{po_number}' sudah dipakai dokumen lain.")
        body['po_number'] = po_number
    else:
        from core.doc_number_policy import issue_number
        po_number = await issue_number(
            db,
            'production_pos.po_number_maklon' if business_type == 'maklon'
            else 'production_pos.po_number',
            requested=body.get('po_number') or '')
        body['po_number'] = po_number
    vendor_name = ''
    if body.get('vendor_id'):
        vendor_doc = await resolve_vendor_doc(db, body['vendor_id'])
        vendor_name = vendor_doc.get('garment_name', '') if vendor_doc else ''
    po_id = new_id()
    initial_status = 'Confirmed' if body.get('status') == 'Confirmed' else 'Draft'
    # Resolve buyer name from buyer_id if provided (buyers ATAU dewi_maklon_clients)
    customer_name = body.get('customer_name', '')
    buyer_id = body.get('buyer_id')
    if buyer_id:
        customer_name = await resolve_buyer_name(db, buyer_id, customer_name)
    # ── Fase 3 (D3): PO internal — validasi model_id+size_id SEMUA item dulu ──
    items_data = body.get('items', [])
    internal_masters = {}
    internal_variants = {}  # Fase 2: rahaza_model_variants terpilih per item
    if business_type == 'internal':
        from routes.production_internal_adapter import validate_internal_item
        for idx, item in enumerate(items_data):
            # Fase 2: bila item pilih varian ber-SKU, resolve → inject model_id/size_id
            rv = await _resolve_rahaza_variant(db, item)
            if rv:
                internal_variants[idx] = rv
            internal_masters[idx] = await validate_internal_item(db, item)
    po = {
        'id': po_id, 'po_number': body['po_number'], 'customer_name': customer_name,
        'buyer_id': buyer_id,
        'vendor_id': body.get('vendor_id'), 'vendor_name': vendor_name,
        'po_date': parse_date(body.get('po_date')) or now(),
        'deadline': parse_date(body.get('deadline')),
        'delivery_deadline': parse_date(body.get('delivery_deadline')),
        'status': initial_status, 'notes': body.get('notes', ''),
        'business_type': business_type,
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.production_pos.insert_one(po)
    inserted_items = []
    for idx, item in enumerate(items_data):
        # [FASE 4 — BACKWARD-COMPAT FALLBACK, KEEP] Legacy `products`/`product_variants`
        # lookups. New POs from the active UI no longer send product_id/variant_id
        # (Internal→rahaza_models, Maklon→buyer-catalog), so these resolve to None and
        # are safely skipped. Retained so historical POs carrying product_id/variant_id
        # still enrich name/size/color/sku when those collections still hold data.
        variant = await db.product_variants.find_one({'id': item.get('variant_id')}) if item.get('variant_id') else None
        product = await db.products.find_one({'id': item.get('product_id')}) if item.get('product_id') else None
        model, msize = internal_masters.get(idx, (None, None))
        rv = internal_variants.get(idx)  # Fase 2: rahaza_model_variants
        po_item = {
            'id': new_id(), 'po_id': po_id, 'po_number': body['po_number'],
            'product_id': item.get('product_id'),
            'catalog_item_id': item.get('catalog_item_id'),  # maklon: FK ke dewi_maklon_buyer_catalog (master produk maklon)
            'product_name': (model or {}).get('name') or (product or {}).get('product_name') or item.get('product_name', ''),
            'variant_id': item.get('variant_id'),
            'rahaza_variant_id': (rv or {}).get('id'),  # Fase 2: FK ke rahaza_model_variants
            'maklon_variant_id': item.get('maklon_variant_id'),  # maklon: FK ke variant embedded di buyer_catalog (relasi master data)
            'buyer_ref_code': item.get('buyer_ref_code', ''),    # kode artikel buyer (boleh custom per varian)
            'model_id': (model or {}).get('id'), 'size_id': (msize or {}).get('id'),
            'size': (msize or {}).get('code') or (variant or {}).get('size', item.get('size', '')),
            'color': (rv or {}).get('color_name') or (variant or {}).get('color', item.get('color', '')),
            'color_code': (rv or {}).get('color_code') or item.get('color_code', ''),
            'sku': (rv or {}).get('sku') or (variant or {}).get('sku') or item.get('sku') or (build_variant_sku(model.get('code', ''), item.get('color_code', ''), msize.get('code', '')) if model else ''),
            'qty': int(item.get('qty', 0) or 0),
            # FASE 1 (cacat FLD-1): banyak pembaca (laporan/PDF/UI lama) membaca
            # `qty_ordered`, sementara penulis hanya menyimpan `qty` ⇒ kolom tampil
            # kosong/0. Simpan keduanya agar satu arti, dua nama, satu angka.
            'qty_ordered': int(item.get('qty', 0) or 0),
            'serial_number': item.get('serial_number', ''),
            'selling_price_snapshot': float(item.get('selling_price_snapshot', 0) or (product or {}).get('selling_price', 0) or 0),
            'cmt_price_snapshot': float(item.get('cmt_price_snapshot', 0) or (product or {}).get('cmt_price', 0) or 0),
            'created_at': now()
        }
        await db.po_items.insert_one(po_item)
        inserted_items.append(po_item)
    # ── Fase 3 (ACC-1): auto-explode aksesoris dari BOM utk PO internal ──
    accessories_explode = None
    if business_type == 'internal':
        try:
            from routes.production_internal_adapter import explode_po_accessories_from_bom
            accessories_explode = await explode_po_accessories_from_bom(db, po_id)
        except Exception:
            import logging; logging.getLogger(__name__).exception('BOM explode gagal utk PO %s', po_id)
    # ── 2026-08-01: PADANAN untuk MAKLON — BOM Template artikel → kebutuhan
    #    material PO (`dewi_maklon_bom`) + baris aksesoris (`po_accessories`)
    #    supaya ikut tercetak di Surat Jalan. Sebelum ini PO maklon tidak pernah
    #    meledakkan BOM sama sekali (template hanya jadi katalog mati).
    maklon_bom_explode = None
    if business_type == 'maklon':
        try:
            from routes.dewi_maklon_bom_templates import explode_maklon_bom_for_po
            maklon_bom_explode = await explode_maklon_bom_for_po(db, po_id, user=user)
        except Exception:
            import logging; logging.getLogger(__name__).exception('BOM maklon explode gagal utk PO %s', po_id)
    await log_activity(user['id'], user['name'], 'Create', 'Production PO', f"Created PO: {po['po_number']} with {len(items_data)} items")
    # ── Fase 2 Maklon: sinkronisasi finance saat PO maklon langsung Confirmed ──
    if business_type == 'maklon' and initial_status == 'Confirmed':
        from routes.production_maklon_bridge import try_sync_maklon_finance
        await try_sync_maklon_finance(db, po_id, user)
    result = serialize_doc(po)
    result['items'] = serialize_doc(inserted_items)
    if accessories_explode is not None:
        result['accessories_explode'] = accessories_explode
    if maklon_bom_explode is not None:
        result['maklon_bom_explode'] = maklon_bom_explode
    return result

# ═══════════════════════════════════════════════════════════════════════════
# ACC-1 — KEBUTUHAN AKSESORIS PER PO (BOM explode → cek stok → request internal)
#
# Konteks (memory/PRODUKSI_E9_AKSESORIS.md §ACC-1): explode BOM → `po_accessories`
# sudah ada, TAPI hasilnya berhenti sebagai teks: tidak dibandingkan dengan stok
# nyata dan tidak bisa dilanjutkan menjadi permintaan barang. Akibatnya user tetap
# harus mengetik ulang kebutuhan di modul Aksesoris (kerja dobel + rawan salah).
#
# Dua endpoint di bawah menutup rantai itu:
#   GET  .../accessory-requirements                → kebutuhan + on-hand + kekurangan
#   POST .../accessory-requirements/create-request  → jadikan permintaan internal
#                                                     (SSOT `dewi_accessory_requests`,
#                                                      request_type='internal_issuance')
# ═══════════════════════════════════════════════════════════════════════════
async def _po_accessory_rows(db, po_id: str):
    return await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)


@router.get("/production-pos/{po_id}/accessory-requirements")
async def po_accessory_requirements(po_id: str, request: Request):
    """Kebutuhan aksesoris PO + posisi stok + kekurangan (read-only)."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')

    rows = await _po_accessory_rows(db, po_id)
    ids = [r.get('accessory_id') for r in rows if r.get('accessory_id')]

    from core import stock_service
    onhand = await stock_service.onhand_map(ids, db=db) if ids else {}
    avail = await stock_service.available_map(ids, db=db) if ids else {}

    masters = {}
    if ids:
        async for m in db.rahaza_materials.find(
                {'id': {'$in': ids}},
                {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'unit': 1, 'unit_cost': 1, 'hpp': 1}):
            masters[m['id']] = m

    out = []
    total_shortage_value = 0.0
    shortage_lines = unlinked_lines = 0
    for r in rows:
        mid = r.get('accessory_id')
        master = masters.get(mid) or {}
        need = float(r.get('qty_needed') or 0)
        # Pakai `available` (on-hand − reserved) supaya stok yang sudah dialokasikan
        # ke PO lain / karantina TIDAK dihitung sebagai tersedia.
        have = float(avail.get(mid, 0)) if mid else 0.0
        on_hand = float(onhand.get(mid, 0)) if mid else 0.0
        shortage = round(max(need - have, 0.0), 3)
        unit_cost = float(master.get('unit_cost') or master.get('hpp') or 0)
        if not mid:
            unlinked_lines += 1
        if shortage > 0:
            shortage_lines += 1
            total_shortage_value += shortage * unit_cost
        out.append({
            **r,
            'material_id': mid,
            'material_code': master.get('code') or r.get('accessory_code') or '',
            'material_name': master.get('name') or r.get('accessory_name') or '',
            'linked': bool(mid),
            'on_hand': on_hand,
            'available': have,
            'shortage': shortage,
            'unit_cost': unit_cost,
            'shortage_value': round(shortage * unit_cost, 2),
            'status': 'unlinked' if not mid else ('shortage' if shortage > 0 else 'ok'),
        })

    # request internal yang sudah dibuat untuk PO ini (agar UI tidak dobel bikin)
    existing = await db.dewi_accessory_requests.find(
        {'po_id': po_id, 'request_type': 'internal_issuance'},
        {'_id': 0, 'id': 1, 'request_code': 1, 'status': 1, 'created_at': 1}
    ).sort('created_at', -1).to_list(20)

    return {
        'po_id': po_id,
        'po_number': po.get('po_number', ''),
        'business_type': po.get('business_type', ''),
        'requirements': serialize_doc(out),
        'summary': {
            'total_lines': len(out),
            'shortage_lines': shortage_lines,
            'unlinked_lines': unlinked_lines,
            'total_shortage_value': round(total_shortage_value, 2),
            'ready': shortage_lines == 0 and unlinked_lines == 0,
        },
        'existing_requests': serialize_doc(existing),
    }


@router.post("/production-pos/{po_id}/accessory-requirements/create-request")
async def po_accessory_create_request(po_id: str, request: Request):
    """Buat permintaan aksesoris internal dari kebutuhan PO.

    Body: {only_shortage?: bool=true, divisi?: str, needed_by?: str,
           urgent?: bool, notes?: str, force?: bool=false}
    Default hanya mengambil baris yang KURANG stok (tidak membanjiri gudang dengan
    permintaan barang yang sudah tersedia). `force=false` menolak bila masih ada
    permintaan aktif untuk PO ini (hindari dobel).
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, 'Hanya admin/supervisor produksi yang boleh membuat permintaan aksesoris')
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')
    body = await request.json() if await request.body() else {}
    only_shortage = body.get('only_shortage', True)
    force = bool(body.get('force'))

    if not force:
        dup = await db.dewi_accessory_requests.find_one(
            {'po_id': po_id, 'request_type': 'internal_issuance',
             'status': {'$in': ['draft', 'submitted', 'allocated']}},
            {'_id': 0, 'request_code': 1, 'status': 1})
        if dup:
            raise HTTPException(400, f"Permintaan aksesoris untuk PO ini sudah ada: "
                                     f"{dup.get('request_code')} (status {dup.get('status')}). "
                                     f"Selesaikan/batalkan dulu, atau kirim force=true.")

    rows = await _po_accessory_rows(db, po_id)
    if not rows:
        raise HTTPException(400, 'PO ini belum punya kebutuhan aksesoris. '
                                 'Pastikan BOM aktif berisi aksesoris, lalu simpan ulang PO.')

    ids = [r.get('accessory_id') for r in rows if r.get('accessory_id')]
    from core import stock_service
    avail = await stock_service.available_map(ids, db=db) if ids else {}

    items, skipped_ok, skipped_unlinked = [], 0, 0
    for r in rows:
        mid = r.get('accessory_id')
        need = float(r.get('qty_needed') or 0)
        if need <= 0:
            continue
        if not mid:
            # Tanpa material_id, permintaan tidak bisa dipenuhi dari stok mana pun.
            skipped_unlinked += 1
            continue
        have = float(avail.get(mid, 0))
        qty = round(max(need - have, 0.0), 3) if only_shortage else need
        if qty <= 0:
            skipped_ok += 1
            continue
        items.append({
            'material_id': mid,
            'material_code': r.get('accessory_code', ''),
            'material_name': r.get('accessory_name', ''),
            'qty': qty,
            'unit': r.get('unit', 'pcs'),
            'notes': f"Kebutuhan PO {po.get('po_number', '')}"
                     + (f" · butuh {need}, tersedia {have}" if only_shortage else ''),
        })

    if not items:
        detail = 'Semua kebutuhan aksesoris sudah tercukupi stok — tidak ada yang perlu diminta.'
        if skipped_unlinked:
            detail += (f" Catatan: {skipped_unlinked} baris belum tertaut ke master material "
                       f"sehingga dilewati — perbaiki BOM-nya dulu.")
        raise HTTPException(400, detail)

    from utils.counters import gen_prefixed_number
    today = now_wib().strftime('%y%m%d')
    code = await gen_prefixed_number(db, 'dewi_accessory_requests', 'request_code',
                                     f'INT-REQ-{today}-', 3)
    doc = {
        'id': new_id(),
        'request_code': code,
        'request_type': 'internal_issuance',
        'sample_request_id': '', 'style_id': '', 'style_code': '', 'style_name': '',
        'divisi': body.get('divisi') or 'Produksi',
        'purpose': body.get('notes') or f"Kebutuhan aksesoris PO {po.get('po_number', '')}",
        'admin_notes': '',
        'vendor_id': '', 'original_shipment_id': None,
        'po_id': po_id, 'po_number': po.get('po_number', ''),
        'total_requested_qty': round(sum(i['qty'] for i in items), 3),
        'items': items,
        'urgent': bool(body.get('urgent', False)),
        'needed_by_date': body.get('needed_by', '') or (po.get('deadline').isoformat()[:10]
                                                        if isinstance(po.get('deadline'), datetime) else ''),
        'notes': body.get('notes', ''),
        'status': 'submitted',       # langsung masuk Inbox Approval Aksesoris
        'requester_id': user['id'],
        'requester_name': user.get('name', ''),
        'allocated_by': None, 'allocated_at': None,
        'delivered_by': None, 'delivered_at': None,
        'rejection_reason': None,
        'source': 'po_bom_explode',  # jejak: dibuat otomatis dari kebutuhan PO (ACC-1)
        'created_at': now(), 'updated_at': now(),
    }
    await db.dewi_accessory_requests.insert_one(doc)
    await log_activity(user['id'], user['name'], 'Create', 'Accessory Request',
                       f"{code} dari kebutuhan PO {po.get('po_number', '')} ({len(items)} item)")
    return JSONResponse({
        'ok': True,
        'request': serialize_doc(doc),
        'lines_requested': len(items),
        'lines_skipped_sufficient': skipped_ok,
        'lines_skipped_unlinked': skipped_unlinked,
        'message': f"Permintaan {code} dibuat ({len(items)} item) dan masuk Inbox Approval Aksesoris.",
    }, status_code=201)


@router.post("/production-pos/{po_id}/close")
async def close_po(po_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po = await db.production_pos.find_one({'id': po_id})
    if not po: raise HTTPException(404, 'PO not found')
    if po.get('status') == 'Closed':
        raise HTTPException(400, 'PO sudah Closed')
    if po.get('status') not in PO_CLOSABLE_STATUSES:
        raise HTTPException(400,
            f"PO berstatus '{po.get('status')}' belum bisa ditutup. "
            f"Close manual hanya sah dari: {PO_CLOSABLE_STATUSES}")
    await db.production_pos.update_one({'id': po_id}, {'$set': {
        'status': 'Closed', 'close_reason': body.get('close_reason'),
        'close_notes': body.get('close_notes', ''), 'closed_by': user['name'],
        'closed_at': now(), 'updated_at': now()
    }})
    if po.get('business_type') == 'maklon':
        from routes.production_maklon_bridge import try_sync_maklon_finance
        await try_sync_maklon_finance(db, po_id, user)
    await log_activity(user['id'], user['name'], 'Close PO', 'Production PO', f"Closed PO: {po.get('po_number')}")
    return {'success': True}

@router.post("/production-pos/{po_id}/close-short")
async def close_po_short(po_id: str, request: Request):
    """Phase C §11.2 — Manual short-close (< 100% fulfilled).

    Sets status='Closed Short' + closed_reason (enum) + qty_short/qty_short_pct,
    then triggers finance finalization (credit note draft if AR already issued,
    else shrink the draft AR invoice to qty_received)."""
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    reason = (body.get('closed_reason') or '').strip()
    if reason not in CLOSE_SHORT_REASONS:
        raise HTTPException(400,
            f"closed_reason tidak valid: '{reason}'. Pilihan: {sorted(CLOSE_SHORT_REASONS)}")
    po = await db.production_pos.find_one({'id': po_id})
    if not po:
        raise HTTPException(404, 'PO not found')
    if po.get('status') in ('Closed', 'Closed Short'):
        raise HTTPException(400, f"PO sudah berstatus '{po.get('status')}'.")
    if po.get('status') not in CLOSE_SHORT_ALLOWED_FROM:
        raise HTTPException(400,
            f"Close-short tidak sah dari status '{po.get('status')}'. "
            f"Hanya dari: {CLOSE_SHORT_ALLOWED_FROM}")
    post_completion = po.get('status') == 'Completed'

    from routes.production_maklon_bridge import compute_po_fulfillment, finalize_ar_on_short_close
    f = await compute_po_fulfillment(db, po_id)
    qty_short = int(f['qty_short'])
    if qty_short <= 0:
        raise HTTPException(400,
            'Tidak ada kekurangan qty (qty_short=0) — PO sudah terpenuhi penuh. '
            'Gunakan penutupan normal / auto-complete, bukan close-short.')

    await db.production_pos.update_one({'id': po_id}, {'$set': {
        'status': 'Closed Short',
        'closed_reason': reason,
        'close_notes': body.get('notes', ''),
        'closed_by': user['name'],
        'closed_at': now(),
        'qty_short': qty_short,
        'qty_short_pct': f['qty_short_pct'],
        'qty_received_at_close': f['total_received'],
        'qty_produced_at_close': f.get('total_produced', 0),
        'qty_ordered_at_close': f['total_ordered'],
        'post_completion_adjustment': bool(post_completion),
        'status_before_close_short': po.get('status'),
        'updated_at': now(),
    }})
    # Mirror finance dulu (status/qty), baru penyesuaian AR — supaya total_value mirror
    # tidak menimpa hasil penyesuaian close-short (audit M-03).
    if po.get('business_type') == 'maklon':
        from routes.production_maklon_bridge import try_sync_maklon_finance
        await try_sync_maklon_finance(db, po_id, user)
    finance = await finalize_ar_on_short_close(db, po, user, f)
    # GAP G — selisih yang masih terbuka harus terlihat saat PO ditutup supaya
    # keputusan tanggungan (CMT / DA) tidak terlewat.
    open_shorts = None
    try:
        from core import short_shipment as shortmod
        bs = await shortmod.list_buyer_shorts(db, status='open', po_id=po_id)
        cs = await shortmod.cmt_short_totals(db, po_id=po_id)
        open_shorts = {
            'buyer': {'docs': bs.get('total'), 'qty_open': bs.get('total_qty_open'),
                      'items': bs.get('items')},
            'cmt': cs,
            'action_required': (bs.get('total_qty_open') or 0) > 0 or (cs.get('qty_short_open') or 0) > 0,
        }
    except Exception:
        import logging as _lg
        _lg.getLogger(__name__).exception('ringkasan selisih saat close-short gagal')
    await log_activity(user['id'], user['name'], 'Close Short PO', 'Production PO',
        f"PO {po.get('po_number')} → Closed Short ({reason}). "
        f"qty_short={qty_short}/{f['total_ordered']} ({f['qty_short_pct']}%)."
        + (' [penyesuaian pasca-Completed]' if post_completion else ''))
    return {
        'success': True,
        'status': 'Closed Short',
        'closed_reason': reason,
        'qty_ordered': f['total_ordered'],
        'qty_received': f['total_received'],
        'qty_produced': f.get('total_produced', 0),
        'qty_fulfilled': f.get('total_fulfilled', f['total_received']),
        'basis': f.get('basis'),
        'qty_short': qty_short,
        'qty_short_pct': f['qty_short_pct'],
        'post_completion_adjustment': bool(post_completion),
        'open_shorts': open_shorts,
        'finance': finance,
    }

@router.put("/production-pos/{po_id}")
async def update_po(po_id: str, request: Request):
    """
    Phase 8.6 — Full PO edit (header + items + po_accessories) with strict guardrails.

    Accepts optional `items` and `po_accessories` in body for delta update:
      - Upsert existing by `id` (update in place)
      - Insert new (item without `id`)
      - Delete items/accessories whose `id` is no longer present in payload,
        but ONLY when no downstream references exist.

    Strict guardrails (confirmed with user):
      - If any vendor_shipment_items or buyer_shipment_items reference a po_item:
          * forbid editing sku / size / color
          * forbid reducing qty below max(already-sent-to-vendor, already-shipped-to-buyer)
          * forbid deleting the item
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    existing = await db.production_pos.find_one({'id': po_id})
    if not existing: raise HTTPException(404, 'PO not found')
    if existing.get('status') == 'Closed' and (user.get('role') or '').lower() != 'superadmin':
        raise HTTPException(403, 'PO ini sudah Closed.')
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    if 'business_type' in body and body['business_type'] not in ('internal', 'maklon'):
        raise HTTPException(400, "business_type harus 'internal' atau 'maklon'")

    # Separate items / accessories payloads (optional)
    items_payload = body.pop('items', None)
    acc_payload = body.pop('po_accessories', None)

    # ─── Header update ────────────────────────────────────────────────
    if body.get('deadline'): body['deadline'] = parse_date(body['deadline'])
    if body.get('delivery_deadline'): body['delivery_deadline'] = parse_date(body['delivery_deadline'])
    if body.get('po_date'): body['po_date'] = parse_date(body['po_date'])
    if body.get('vendor_id'):
        vd = await resolve_vendor_doc(db, body['vendor_id'])
        body['vendor_name'] = vd.get('garment_name', '') if vd else ''
    # resolve buyer_name from buyer_id (consistent with create_po)
    if body.get('buyer_id'):
        body['customer_name'] = await resolve_buyer_name(db, body['buyer_id'], body.get('customer_name', ''))

    new_po_number = body.get('po_number')
    if new_po_number and new_po_number != existing.get('po_number'):
        dup = await db.production_pos.find_one({'po_number': new_po_number, 'id': {'$ne': po_id}})
        if dup: raise HTTPException(400, f'Nomor PO "{new_po_number}" sudah digunakan')

    await db.production_pos.update_one({'id': po_id}, {'$set': {**body, 'updated_at': now()}})

    # ─── Items delta update (with guardrails) ─────────────────────────
    if items_payload is not None:
        existing_items = await db.po_items.find({'po_id': po_id}).to_list(None)
        existing_by_id = {i['id']: i for i in existing_items}
        payload_ids = set()

        async def _shipped_qty_for_item(item_id):
            vsis = await db.vendor_shipment_items.find({'po_item_id': item_id}).to_list(None)
            bsis = await db.buyer_shipment_items.find({'po_item_id': item_id}).to_list(None)
            sent_to_vendor = sum(int(v.get('qty_sent', 0) or 0) for v in vsis)
            shipped_to_buyer = sum(int(b.get('qty_shipped', 0) or 0) for b in bsis)
            return sent_to_vendor, shipped_to_buyer, (len(vsis) > 0 or len(bsis) > 0)

        # 1) upsert / insert from payload
        _is_internal_po = (body.get('business_type') or existing.get('business_type', 'internal')) == 'internal'
        for raw in items_payload:
            item_id = raw.get('id')
            # Fase 3 (D3): PO internal — item baru atau item yang mengganti model wajib FK valid
            model = msize = None
            rv = None  # Fase 2: rahaza_model_variants terpilih
            if _is_internal_po:
                _old_it = existing_by_id.get(item_id) if item_id else None
                # Fase 2: resolve varian (inject model_id/size_id ke raw bila varian dipilih)
                rv = await _resolve_rahaza_variant(db, raw)
                if raw.get('model_id') or raw.get('size_id') or not _old_it:
                    from routes.production_internal_adapter import validate_internal_item
                    _probe = {**raw}
                    if _old_it:
                        _probe.setdefault('model_id', _old_it.get('model_id'))
                        _probe.setdefault('size_id', _old_it.get('size_id'))
                    model, msize = await validate_internal_item(db, _probe)
            # [FASE 4 — BACKWARD-COMPAT FALLBACK, KEEP] resolve legacy product/variant
            # metadata (mirror create_po). Null-guarded: no-op for POs without
            # product_id/variant_id and when products/product_variants are empty.
            product = await db.products.find_one({'id': raw.get('product_id')}) if raw.get('product_id') else None
            variant = await db.product_variants.find_one({'id': raw.get('variant_id')}) if raw.get('variant_id') else None
            qty_new = int(raw.get('qty', 0) or 0)
            sku_new = (rv or {}).get('sku') or (variant or {}).get('sku') or raw.get('sku') or ((f"{model.get('code','')}-{msize.get('code','')}") if model else '')
            size_new = (msize or {}).get('code') or (rv or {}).get('size_code') or (variant or {}).get('size', raw.get('size', ''))
            color_new = (rv or {}).get('color_name') or (variant or {}).get('color', raw.get('color', ''))

            if item_id and item_id in existing_by_id:
                old = existing_by_id[item_id]
                payload_ids.add(item_id)
                sent_to_vendor, shipped_to_buyer, has_refs = await _shipped_qty_for_item(item_id)
                if has_refs:
                    # block sku/size/color changes
                    if sku_new != old.get('sku', '') or size_new != old.get('size', '') or color_new != old.get('color', ''):
                        raise HTTPException(400, f"Item '{old.get('product_name','')}' sudah memiliki shipment; SKU/Size/Color tidak dapat diubah.")
                    # block qty reduction below max(sent, shipped)
                    floor = max(sent_to_vendor, shipped_to_buyer)
                    if qty_new < floor:
                        raise HTTPException(400, f"Qty item '{old.get('product_name','')}' tidak dapat < {floor} (sudah dikirim/shipped).")
                await db.po_items.update_one({'id': item_id}, {'$set': {
                    'po_id': po_id,
                    'po_number': new_po_number or existing.get('po_number'),
                    'product_id': raw.get('product_id'),
                    'catalog_item_id': raw.get('catalog_item_id', old.get('catalog_item_id')),
                    'model_id': (model or {}).get('id', old.get('model_id')),
                    'size_id': (msize or {}).get('id', old.get('size_id')),
                    'product_name': (model or {}).get('name') or (product or {}).get('product_name', old.get('product_name', '')),
                    'variant_id': raw.get('variant_id'),
                    'rahaza_variant_id': (rv or {}).get('id', old.get('rahaza_variant_id')),
                    'maklon_variant_id': raw.get('maklon_variant_id', old.get('maklon_variant_id')),
                    'buyer_ref_code': raw.get('buyer_ref_code', old.get('buyer_ref_code', '')),
                    'size': size_new, 'color': color_new, 'color_code': (rv or {}).get('color_code') or raw.get('color_code', old.get('color_code', '')), 'sku': sku_new,
                    'qty': qty_new,
                    'serial_number': raw.get('serial_number', old.get('serial_number', '')),
                    'selling_price_snapshot': float(raw.get('selling_price_snapshot', 0) or (product or {}).get('selling_price', 0) or 0),
                    'cmt_price_snapshot': float(raw.get('cmt_price_snapshot', 0) or (product or {}).get('cmt_price', 0) or 0),
                    'updated_at': now(),
                }})
            else:
                # insert new po_item
                new_item = {
                    'id': new_id(), 'po_id': po_id,
                    'po_number': new_po_number or existing.get('po_number'),
                    'product_id': raw.get('product_id'),
                    'catalog_item_id': raw.get('catalog_item_id'),
                    'model_id': (model or {}).get('id'), 'size_id': (msize or {}).get('id'),
                    'product_name': (model or {}).get('name') or (product or {}).get('product_name', '') or raw.get('product_name', ''),
                    'variant_id': raw.get('variant_id'),
                    'rahaza_variant_id': (rv or {}).get('id'),
                    'maklon_variant_id': raw.get('maklon_variant_id'),
                    'buyer_ref_code': raw.get('buyer_ref_code', ''),
                    'size': size_new, 'color': color_new, 'color_code': (rv or {}).get('color_code') or raw.get('color_code', ''), 'sku': sku_new,
                    'qty': qty_new,
                    'serial_number': raw.get('serial_number', ''),
                    'selling_price_snapshot': float(raw.get('selling_price_snapshot', 0) or (product or {}).get('selling_price', 0) or 0),
                    'cmt_price_snapshot': float(raw.get('cmt_price_snapshot', 0) or (product or {}).get('cmt_price', 0) or 0),
                    'created_at': now(),
                }
                await db.po_items.insert_one(new_item)

        # 2) delete po_items not present in payload (only if no references)
        for existing_id, old in existing_by_id.items():
            if existing_id in payload_ids:
                continue
            _, _, has_refs = await _shipped_qty_for_item(existing_id)
            if has_refs:
                raise HTTPException(400, f"Item '{old.get('product_name','')}' tidak dapat dihapus karena sudah memiliki shipment/returns. Kurangi qty atau biarkan.")
            await db.po_items.delete_one({'id': existing_id})

        # Also propagate new po_number to vendor/buyer shipment items (denormalized)
        if new_po_number and new_po_number != existing.get('po_number'):
            await db.vendor_shipment_items.update_many({'po_id': po_id}, {'$set': {'po_number': new_po_number}})
            await db.buyer_shipment_items.update_many({'po_id': po_id}, {'$set': {'po_number': new_po_number}})
            await db.po_items.update_many({'po_id': po_id}, {'$set': {'po_number': new_po_number}})

    # ─── Accessories delta update ─────────────────────────────────────
    if acc_payload is not None:
        existing_accs = await db.po_accessories.find({'po_id': po_id}).to_list(None)
        existing_acc_by_id = {a['id']: a for a in existing_accs}
        payload_acc_ids = set()
        for raw in acc_payload:
            if not (raw.get('accessory_name') or raw.get('accessory_id')):
                continue
            acc_id = raw.get('id')
            doc_fields = {
                'po_id': po_id,
                'accessory_id': raw.get('accessory_id'),
                'accessory_name': raw.get('accessory_name', ''),
                'accessory_code': raw.get('accessory_code', ''),
                'qty_needed': int(raw.get('qty_needed', 0) or 0),
                'unit': raw.get('unit', 'pcs'),
                'notes': raw.get('notes', ''),
            }
            if acc_id and acc_id in existing_acc_by_id:
                payload_acc_ids.add(acc_id)
                await db.po_accessories.update_one({'id': acc_id}, {'$set': {**doc_fields, 'updated_at': now()}})
            else:
                await db.po_accessories.insert_one({**doc_fields, 'id': new_id(), 'created_at': now()})
        # delete accessories dropped from payload (accessory records are safe to delete)
        for existing_id in existing_acc_by_id.keys():
            if existing_id not in payload_acc_ids:
                await db.po_accessories.delete_one({'id': existing_id})

    # ── Fase 3 (ACC-1): re-explode aksesoris BOM bila items PO internal berubah ──
    if items_payload is not None and (body.get('business_type') or existing.get('business_type', 'internal')) == 'internal':
        try:
            from routes.production_internal_adapter import explode_po_accessories_from_bom
            await explode_po_accessories_from_bom(db, po_id)
        except Exception:
            import logging; logging.getLogger(__name__).exception('BOM re-explode gagal utk PO %s', po_id)
    # ── 2026-08-01: idem untuk MAKLON — kebutuhan material ikut qty/item terbaru.
    #    Dokumen BOM yang di-set manual (user pilih versi template) tidak ditimpa
    #    (proteksi ada di explode_maklon_bom_for_po: force=False).
    if items_payload is not None and (body.get('business_type') or existing.get('business_type')) == 'maklon':
        try:
            from routes.dewi_maklon_bom_templates import explode_maklon_bom_for_po
            await explode_maklon_bom_for_po(db, po_id, user=user)
        except Exception:
            import logging; logging.getLogger(__name__).exception('BOM maklon re-explode gagal utk PO %s', po_id)
    await log_activity(user['id'], user['name'], 'Update', 'Production PO', f"Updated PO: {existing.get('po_number')}")
    return serialize_doc(await db.production_pos.find_one({'id': po_id}, {'_id': 0}))

@router.delete("/production-pos/{po_id}")
async def delete_po(po_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.production_pos.find_one({'id': po_id})
    if not doc: raise HTTPException(404, 'Not found')
    await cascade_delete_po(po_id)
    await log_activity(user['id'], user['name'], 'Delete', 'Production PO', f"Cascade deleted PO: {doc.get('po_number')}")
    return {'success': True}

# ─── PO ITEMS ────────────────────────────────────────────────────────────────
@router.get("/po-items")
async def get_po_items(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    query = {}
    po_id = request.query_params.get('po_id')
    if po_id: query['po_id'] = po_id
    items = await db.po_items.find(query, {'_id': 0}).sort('created_at', 1).to_list(None)
    # ── 10B-rem: batch-fetch all vendor shipment items in 1 query ──
    item_ids = [it['id'] for it in items]
    all_vsis = await db.vendor_shipment_items.find({'po_item_id': {'$in': item_ids}}).to_list(None) if item_ids else []
    vsi_map: dict = {}
    for vsi in all_vsis:
        vsi_map.setdefault(vsi.get('po_item_id'), []).append(vsi)
    # Phase 8.5: enrich each po_item with total_sent_to_vendor & remaining_qty_to_vendor
    # so the Vendor Shipment UI can cap qty and hide fully-sent items.
    enriched = []
    for item in items:
        total_sent = sum(v.get('qty_sent', 0) or 0 for v in vsi_map.get(item['id'], []))
        ordered = int(item.get('qty', 0) or 0)
        remaining = max(0, ordered - total_sent)
        enriched.append({**serialize_doc(item),
                         'total_sent_to_vendor': total_sent,
                         'remaining_qty_to_vendor': remaining})
    return enriched

@router.get("/po-items-produced")
async def get_po_items_produced(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    po_id = request.query_params.get('po_id')
    if not po_id: raise HTTPException(400, 'po_id wajib diisi')
    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None)
    if not po_items: return []
    po_item_ids = [it['id'] for it in po_items]

    # ── 10B-rem: batch everything for this PO in ~6 queries instead of N×M×K ──
    # 1. All parent job_items for these po_items
    all_ji = await db.production_job_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(None)
    ji_by_poitem: dict = {}
    for ji in all_ji:
        ji_by_poitem.setdefault(ji.get('po_item_id'), []).append(ji)
    # 2. Batch-fetch parent jobs
    parent_job_ids = list({ji.get('job_id') for ji in all_ji if ji.get('job_id')})
    # 3. Batch-fetch child jobs for all parent jobs at once
    child_jobs = await db.production_jobs.find({'parent_job_id': {'$in': parent_job_ids}}).to_list(None) if parent_job_ids else []
    child_job_ids = [cj['id'] for cj in child_jobs]
    # 4. Batch-fetch child job items
    child_ji_all = await db.production_job_items.find({'job_id': {'$in': child_job_ids}}).to_list(None) if child_job_ids else []
    # Build map: po_item_id -> sum of child produced_qty
    child_prod_by_poitem: dict = {}
    for cji in child_ji_all:
        poi = cji.get('po_item_id')
        if poi:
            child_prod_by_poitem[poi] = child_prod_by_poitem.get(poi, 0) + cji.get('produced_qty', 0)
    # 5. Batch return items
    all_returns = await db.production_return_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(None)
    ret_by_poitem: dict = {}
    for r in all_returns:
        poi = r.get('po_item_id')
        if poi: ret_by_poitem[poi] = ret_by_poitem.get(poi, 0) + r.get('return_qty', 0)
    # 6. Batch buyer shipment items
    all_buyer = await db.buyer_shipment_items.find({'po_item_id': {'$in': po_item_ids}}).to_list(None)
    shipped_by_poitem: dict = {}
    for b in all_buyer:
        poi = b.get('po_item_id')
        if poi: shipped_by_poitem[poi] = shipped_by_poitem.get(poi, 0) + b.get('qty_shipped', 0)

    enriched = []
    for item in po_items:
        parent_prod = sum(ji.get('produced_qty', 0) for ji in ji_by_poitem.get(item['id'], []))
        total_produced = parent_prod + child_prod_by_poitem.get(item['id'], 0)
        total_returned = ret_by_poitem.get(item['id'], 0)
        total_shipped  = shipped_by_poitem.get(item['id'], 0)
        enriched.append({**serialize_doc(item),
            'total_produced': total_produced, 'total_shipped': total_shipped,
            'total_returned': total_returned,
            'max_returnable': max(0, total_shipped - total_returned)})
    return enriched

@router.put("/po-items/{item_id}")
async def update_po_item(item_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None)
    await db.po_items.update_one({'id': item_id}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.po_items.find_one({'id': item_id}, {'_id': 0}))

@router.delete("/po-items/{item_id}")
async def delete_po_item(item_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.po_items.delete_one({'id': item_id})
    return {'success': True}

# ─── PO STATUS TRANSITION ───────────────────────────────────────────────────
@router.post("/production-pos/{po_id}/quick-complete")
async def quick_complete_po(po_id: str, request: Request):
    """
    Quick Complete: execute the ENTIRE production flow for a PO in one shot.
    Steps:
      1. Create Vendor Shipment  (skip if already exists)
      2. Mark Shipment → Received
      3. Create Material Inspection (all received, 0 missing)
      4. Create Production Job
      5. Record Production Progress  (100 % for every job item)
      6. Create Buyer Shipment       (ship all produced qty)
      7. Mark PO → Completed
    Each step is idempotent: if it already exists, it is reused.
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    skip_buyer_shipment = body.get('skip_buyer_shipment', False)

    po = await db.production_pos.find_one({'id': po_id})
    if not po: raise HTTPException(404, 'PO tidak ditemukan')
    if po.get('status') in ('Completed', 'Closed'):
        raise HTTPException(400, f"PO sudah berstatus '{po['status']}'. Quick Complete tidak dapat dijalankan.")

    po_items = await db.po_items.find({'po_id': po_id}).to_list(None)
    if not po_items:
        raise HTTPException(400, 'PO tidak memiliki item. Tambahkan item terlebih dahulu.')

    vendor = await resolve_vendor_doc(db, po.get('vendor_id')) if po.get('vendor_id') else None
    if not vendor:
        raise HTTPException(400, 'Vendor belum ditetapkan pada PO. Quick Complete memerlukan vendor.')

    total_qty = sum(int(i.get('qty', 0) or 0) for i in po_items)
    if total_qty == 0:
        raise HTTPException(400, 'Semua item PO memiliki qty = 0.')

    steps = []

    # ── STEP 1: Create or reuse Vendor Shipment ──────────────────────────────
    existing_shipment = await db.vendor_shipments.find_one({'po_id': po_id})
    if existing_shipment:
        shipment_id = existing_shipment['id']
        shipment_doc = existing_shipment
        steps.append({'step': 1, 'name': 'Vendor Shipment', 'status': 'reused',
                      'id': shipment_id, 'number': existing_shipment.get('shipment_number')})
    else:
        shipment_count = await db.vendor_shipments.count_documents({})
        shipment_number = f"SJ-QC-{str(shipment_count + 1).zfill(4)}-{po.get('po_number', '')}"
        shipment_id = new_id()
        shipment_doc = {
            'id': shipment_id, 'shipment_number': shipment_number,
            'delivery_note_number': '',
            'vendor_id': vendor['id'], 'vendor_name': vendor.get('garment_name', ''),
            'po_id': po_id, 'po_number': po.get('po_number', ''),
            'shipment_date': now(), 'shipment_type': 'NORMAL',
            'parent_shipment_id': None,
            'business_type': po.get('business_type', 'internal'),
            'status': 'Sent', 'notes': 'Auto-created by Quick Complete',
            'created_by': user['name'], 'created_at': now(), 'updated_at': now()
        }
        await db.vendor_shipments.insert_one(shipment_doc)
        for pi in po_items:
            await db.vendor_shipment_items.insert_one({
                'id': new_id(), 'shipment_id': shipment_id, 'shipment_number': shipment_number,
                'po_id': po_id, 'po_number': po.get('po_number', ''),
                'po_item_id': pi['id'], 'source_po_item_id': pi['id'],
                'product_name': pi.get('product_name', ''), 'sku': pi.get('sku', ''),
                'size': pi.get('size', ''), 'color': pi.get('color', ''),
                'serial_number': pi.get('serial_number', ''),
                'qty_sent': int(pi.get('qty', 0) or 0),
                'ordered_qty': int(pi.get('qty', 0) or 0),
                'shipment_type': 'NORMAL', 'parent_shipment_id': None,
                'created_at': now()
            })
        if po.get('status') == 'Draft':
            await db.production_pos.update_one({'id': po_id}, {'$set': {'status': 'Distributed', 'updated_at': now()}})
        steps.append({'step': 1, 'name': 'Vendor Shipment', 'status': 'created',
                      'id': shipment_id, 'number': shipment_number})

    # ── STEP 2: Mark Shipment → Received ────────────────────────────────────
    if shipment_doc.get('status') != 'Received':
        await db.vendor_shipments.update_one({'id': shipment_id},
                                             {'$set': {'status': 'Received', 'updated_at': now()}})
        steps.append({'step': 2, 'name': 'Terima Shipment', 'status': 'done'})
    else:
        steps.append({'step': 2, 'name': 'Terima Shipment', 'status': 'reused'})
    # Refresh shipment_doc
    shipment_doc = await db.vendor_shipments.find_one({'id': shipment_id})

    # ── STEP 3: Create Material Inspection ───────────────────────────────────
    existing_insp = await db.vendor_material_inspections.find_one({'shipment_id': shipment_id})
    if existing_insp:
        inspection_id = existing_insp['id']
        steps.append({'step': 3, 'name': 'Inspeksi Material', 'status': 'reused', 'id': inspection_id})
    else:
        ship_items = await db.vendor_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
        total_received = sum(int(si.get('qty_sent', 0) or 0) for si in ship_items)
        inspection_id = new_id()
        inspection = {
            'id': inspection_id, 'shipment_id': shipment_id,
            'shipment_number': shipment_doc.get('shipment_number', ''),
            'vendor_id': vendor['id'], 'vendor_name': vendor.get('garment_name', ''),
            'inspection_date': now(),
            'total_received': total_received, 'total_missing': 0,
            'total_acc_received': 0, 'total_acc_missing': 0,
            'overall_notes': 'Auto-completed by Quick Complete', 'status': 'Submitted',
            'submitted_by': user['name'], 'created_at': now(), 'updated_at': now()
        }
        await db.vendor_material_inspections.insert_one(inspection)
        for si in ship_items:
            await db.vendor_material_inspection_items.insert_one({
                'id': new_id(), 'inspection_id': inspection_id, 'item_type': 'material',
                'shipment_item_id': si['id'],
                'sku': si.get('sku', ''), 'product_name': si.get('product_name', ''),
                'size': si.get('size', ''), 'color': si.get('color', ''),
                'ordered_qty': int(si.get('qty_sent', 0) or 0),
                'received_qty': int(si.get('qty_sent', 0) or 0),
                'missing_qty': 0, 'condition_notes': '', 'created_at': now()
            })
        await db.vendor_shipments.update_one({'id': shipment_id}, {'$set': {
            'inspection_status': 'Inspected', 'total_received': total_received,
            'total_missing': 0, 'inspected_at': now(), 'updated_at': now()
        }})
        steps.append({'step': 3, 'name': 'Inspeksi Material', 'status': 'created', 'id': inspection_id})

    # ── STEP 4: Create Production Job ────────────────────────────────────────
    existing_job = await db.production_jobs.find_one({'vendor_shipment_id': shipment_id})
    if existing_job:
        job_id = existing_job['id']
        job_number = existing_job.get('job_number', '')
        steps.append({'step': 4, 'name': 'Production Job', 'status': 'reused',
                      'id': job_id, 'number': job_number})
    else:
        # RC-5 fix: atomic race-safe numbering (was count_documents()+1 → dua
        # "Quick Complete" yang berjalan bersamaan menghasilkan nomor job KEMBAR).
        from utils.counters import gen_prefixed_number as _gen_job_number
        job_id = new_id()
        job_number = await _gen_job_number(db, 'production_jobs', 'job_number', 'JOB-', 4)
        job = {
            'id': job_id, 'job_number': job_number,
            'parent_job_id': None, 'parent_job_number': None,
            'vendor_id': vendor['id'], 'vendor_name': vendor.get('garment_name', ''),
            'po_id': po_id, 'po_number': po.get('po_number', ''),
            'customer_name': po.get('customer_name', ''),
            'vendor_shipment_id': shipment_id,
            'shipment_number': shipment_doc.get('shipment_number'),
            'shipment_type': 'NORMAL',
            'business_type': po.get('business_type', 'internal'),
            'deadline': po.get('deadline'), 'delivery_deadline': po.get('delivery_deadline'),
            'status': 'In Progress', 'notes': 'Auto-created by Quick Complete',
            'created_by': user['name'], 'created_at': now(), 'updated_at': now()
        }
        await db.production_jobs.insert_one(job)
        insp_doc = await db.vendor_material_inspections.find_one({'shipment_id': shipment_id})
        ship_items = await db.vendor_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
        for si in ship_items:
            po_item = await db.po_items.find_one({'id': si.get('po_item_id')}) if si.get('po_item_id') else None
            available_qty = si.get('qty_sent', 0)
            if insp_doc:
                ii = await db.vendor_material_inspection_items.find_one(
                    {'inspection_id': insp_doc['id'], 'shipment_item_id': si['id']})
                if ii:
                    available_qty = ii.get('received_qty', available_qty)
            await db.production_job_items.insert_one({
                'id': new_id(), 'job_id': job_id, 'job_number': job_number,
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
                'ordered_qty': (po_item or {}).get('qty', si.get('qty_sent', 0)),
                'shipment_qty': si.get('qty_sent', 0), 'available_qty': available_qty,
                'produced_qty': 0, 'created_at': now()
            })
        await db.production_pos.update_one({'id': po_id}, {'$set': {'status': 'In Production', 'updated_at': now()}})
        steps.append({'step': 4, 'name': 'Production Job', 'status': 'created',
                      'id': job_id, 'number': job_number})

    # ── STEP 5: Record Production Progress (100%) ────────────────────────────
    job_items_all = await db.production_job_items.find({'job_id': job_id}).to_list(None)
    progress_entries = 0
    for ji in job_items_all:
        available = ji.get('available_qty', ji.get('shipment_qty', 0))
        already = ji.get('produced_qty', 0)
        remaining = max(0, available - already)
        if remaining > 0:
            await db.production_progress.insert_one({
                'id': new_id(), 'job_id': ji.get('job_id'), 'job_item_id': ji['id'],
                'sku': ji.get('sku', ''), 'product_name': ji.get('product_name', ''),
                'size': ji.get('size', ''), 'color': ji.get('color', ''),
                'progress_date': now(), 'completed_quantity': remaining,
                'notes': 'Auto-completed by Quick Complete',
                'recorded_by': user['name'], 'created_at': now()
            })
            await db.production_job_items.update_one(
                {'id': ji['id']}, {'$set': {'produced_qty': available, 'updated_at': now()}}
            )
            progress_entries += 1
    # Jalur tutup KEDUA (Quick Complete). Wajib memakai penulis yang sama dengan
    # auto-complete di `production_execution.py`, kalau tidak salah satunya akan
    # lupa menulis `closed_at` dan rekap tanggal lampau kembali bohong.
    from core.production_job_lifecycle import close_job
    await close_job(db, job_id)
    steps.append({'step': 5, 'name': 'Progress Produksi (100%)',
                  'status': 'done' if progress_entries > 0 else 'reused',
                  'progress_entries': progress_entries})

    # ── STEP 6: Create Buyer Shipment ────────────────────────────────────────
    if not skip_buyer_shipment:
        existing_bs = await db.buyer_shipments.find_one({'job_id': job_id})
        if existing_bs:
            steps.append({'step': 6, 'name': 'Buyer Shipment', 'status': 'reused',
                          'id': existing_bs['id'], 'number': existing_bs.get('shipment_number')})
        else:
            bs_id = new_id()
            bs_number = f"SJ-BYR-QC-{po.get('po_number', '')}"
            bs = {
                'id': bs_id, 'shipment_number': bs_number,
                'vendor_id': vendor['id'], 'vendor_name': vendor.get('garment_name', ''),
                'po_id': po_id, 'po_number': po.get('po_number', ''),
                'customer_name': po.get('customer_name', ''),
                'job_id': job_id, 'ship_status': 'Partially Shipped',
                'notes': 'Auto-created by Quick Complete',
                'created_by': user['name'], 'created_at': now(), 'updated_at': now()
            }
            await db.buyer_shipments.insert_one(bs)
            job_items_final = await db.production_job_items.find({'job_id': job_id}).to_list(None)
            total_shipped = 0
            for ji in job_items_final:
                qty_to_ship = ji.get('produced_qty', 0)
                if qty_to_ship > 0:
                    po_item = await db.po_items.find_one({'id': ji.get('po_item_id')}) if ji.get('po_item_id') else None
                    await db.buyer_shipment_items.insert_one({
                        'id': new_id(), 'shipment_id': bs_id,
                        'dispatch_seq': 1, 'dispatch_date': now(),
                        'po_item_id': ji.get('po_item_id'), 'job_item_id': ji['id'],
                        'job_id': job_id,
                        'product_name': ji.get('product_name', ''),
                        'serial_number': ji.get('serial_number', ''),
                        'size': ji.get('size', ''), 'color': ji.get('color', ''),
                        'sku': ji.get('sku', ''),
                        'ordered_qty': (po_item or {}).get('qty', ji.get('ordered_qty', 0)),
                        'qty_shipped': qty_to_ship, 'created_at': now()
                    })
                    total_shipped += qty_to_ship
            steps.append({'step': 6, 'name': 'Buyer Shipment', 'status': 'created',
                          'id': bs_id, 'number': bs_number, 'total_shipped': total_shipped})
    else:
        steps.append({'step': 6, 'name': 'Buyer Shipment', 'status': 'skipped'})

    # ── STEP 7: Mark PO → Completed ─────────────────────────────────────────
    await db.production_pos.update_one({'id': po_id},
                                       {'$set': {'status': 'Completed', 'updated_at': now()}})
    steps.append({'step': 7, 'name': 'Status PO → Completed', 'status': 'done'})

    total_items = sum(int(i.get('qty', 0) or 0) for i in po_items)
    # ── Fase 2 Maklon: sinkronisasi finance setelah Quick Complete PO maklon ──
    if po.get('business_type') == 'maklon':
        from routes.production_maklon_bridge import try_sync_maklon_finance
        await try_sync_maklon_finance(db, po_id, user)
    await log_activity(user['id'], user['name'], 'Quick Complete', 'Production PO',
                       f"Quick Complete PO {po.get('po_number')}: {len(steps)} langkah, {total_items} pcs")
    return {
        'success': True,
        'po_id': po_id, 'po_number': po.get('po_number'),
        'steps': steps,
        'total_items': total_items,
        'job_number': job_number,
        'message': f"PO {po.get('po_number')} berhasil diselesaikan secara lengkap.",
    }

@router.post("/production-pos/{po_id}/status")
async def transition_po_status(po_id: str, request: Request):
    """Transition PO through staged statuses."""
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    new_status = body.get('status')
    if new_status not in PO_STATUSES:
        raise HTTPException(400, f"Invalid status. Valid: {PO_STATUSES}")
    po = await db.production_pos.find_one({'id': po_id})
    if not po: raise HTTPException(404, 'PO not found')
    current_status = po.get('status', 'Draft')
    allowed_next = PO_STATUS_TRANSITIONS.get(current_status, [])
    if new_status not in allowed_next:
        raise HTTPException(400,
            f"Transisi status ilegal: '{current_status}' → '{new_status}'. "
            f"Transisi valid dari '{current_status}': {allowed_next if allowed_next else 'tidak ada (status final)'}")
    update_data = {'status': new_status, 'updated_at': now()}
    if body.get('notes'): update_data['status_notes'] = body['notes']
    if new_status == 'Closed':
        update_data['closed_by'] = user['name']
        update_data['closed_at'] = now()
        update_data['close_reason'] = body.get('close_reason', '')
    await db.production_pos.update_one({'id': po_id}, {'$set': update_data})
    # ── Fase 2 Maklon: resync mirror finance saat status PO maklon berubah ──
    if po.get('business_type') == 'maklon':
        from routes.production_maklon_bridge import try_sync_maklon_finance
        await try_sync_maklon_finance(db, po_id, user)
    await log_activity(user['id'], user['name'], 'Status Change', 'Production PO',
                       f"PO {po.get('po_number')}: {po.get('status')} → {new_status}")
    return serialize_doc(await db.production_pos.find_one({'id': po_id}, {'_id': 0}))

# ─── PO QUANTITY SUMMARY ────────────────────────────────────────────────────
@router.get("/production-pos/{po_id}/fulfillment")
async def po_fulfillment(po_id: str, request: Request):
    """Phase C: buyer-fulfillment snapshot for closure UI (ordered/shipped/
    received/qty_short/qty_short_pct + whether a manual close-short is allowed)."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO not found')
    from routes.production_maklon_bridge import compute_po_fulfillment
    f = await compute_po_fulfillment(db, po_id)
    f['status'] = po.get('status')
    f['closed_reason'] = po.get('closed_reason')
    f['closed_at'] = po.get('closed_at')
    f['business_type'] = po.get('business_type')
    f['can_close_short'] = (po.get('status') in CLOSE_SHORT_ALLOWED_FROM) and f['qty_short'] > 0
    f['close_short_reasons'] = sorted(CLOSE_SHORT_REASONS)
    # ── GAP A/G: selisih kirim (CMT→DA) & selisih terima (DA→buyer) yang MASIH terbuka ──
    try:
        from core import short_shipment as shortmod
        bs = await shortmod.list_buyer_shorts(db, status='open', po_id=po_id)
        f['shorts'] = {
            'cmt': await shortmod.cmt_short_totals(db, po_id=po_id),
            'buyer': {'docs': bs.get('total'), 'qty_open': bs.get('total_qty_open'),
                      'items': bs.get('items')},
        }
    except Exception:
        import logging as _lg
        _lg.getLogger(__name__).exception('ringkasan selisih (fulfillment PO %s) gagal', po_id)
        f['shorts'] = None
    # ── FASE 1: sertakan angka QC supaya penutupan PO jelas "produced X, reject Y" ──
    try:
        from core import production_qty_ledger as qty_ledger
        led = await qty_ledger.po_ledger_totals(db, po_id)
        f['qc'] = led['totals']
    except Exception:
        import logging as _lg
        _lg.getLogger(__name__).exception('buku kuantitas QC gagal (fulfillment PO %s)', po_id)
        f['qc'] = None
    # strip verbose per-item maps from the response
    for k in ('ordered_by_item', 'received_by_item', 'rate_by_item'):
        f.pop(k, None)
    return f

@router.get("/production-pos/{po_id}/quantity-summary")
async def po_quantity_summary(po_id: str, request: Request):
    """Get comprehensive quantity summary for a PO."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
    if not po: raise HTTPException(404, 'PO not found')
    items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    summary_items = []
    totals = {'ordered': 0, 'received': 0, 'missing': 0, 'defect': 0, 
              'available': 0, 'produced': 0, 'shipped': 0, 'returned': 0}
    # ── 10E: batch all sub-document lookups for PDF summary in 7 queries ──
    pdf_item_ids = [it['id'] for it in items]
    _s_vsi_all  = await db.vendor_shipment_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_vsi_ids  = [vsi['id'] for vsi in _s_vsi_all]
    _s_ship_ids = list({vsi.get('shipment_id') for vsi in _s_vsi_all if vsi.get('shipment_id')})
    _s_ships    = await db.vendor_shipments.find({'id': {'$in': _s_ship_ids}}, {'_id': 0, 'id': 1, 'status': 1, 'inspection_status': 1}).to_list(None) if _s_ship_ids else []
    _s_ship_map = {sh['id']: sh for sh in _s_ships}
    _s_insps    = await db.vendor_material_inspections.find({'shipment_id': {'$in': _s_ship_ids}}).to_list(None) if _s_ship_ids else []
    _s_insp_map = {insp.get('shipment_id'): insp for insp in _s_insps}
    _s_insp_ids = [insp['id'] for insp in _s_insps]
    _s_ii_all   = await db.vendor_material_inspection_items.find({'inspection_id': {'$in': _s_insp_ids}, 'shipment_item_id': {'$in': _s_vsi_ids}}).to_list(None) if (_s_insp_ids and _s_vsi_ids) else []
    _s_ii_map   = {ii.get('shipment_item_id'): ii for ii in _s_ii_all}
    _s_defects  = await db.material_defect_reports.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_ji_all   = await db.production_job_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_bi_all   = await db.buyer_shipment_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_ri_all   = await db.production_return_items.find({'po_item_id': {'$in': pdf_item_ids}}).to_list(None) if pdf_item_ids else []
    _s_vsi_by_poi: dict = {}
    for vsi in _s_vsi_all: _s_vsi_by_poi.setdefault(vsi.get('po_item_id'), []).append(vsi)
    _s_def_by_poi: dict = {}
    for d in _s_defects: _s_def_by_poi.setdefault(d.get('po_item_id'), []).append(d)
    _s_ji_by_poi: dict = {}
    for ji in _s_ji_all: _s_ji_by_poi.setdefault(ji.get('po_item_id'), []).append(ji)
    _s_bi_by_poi: dict = {}
    for bi in _s_bi_all: _s_bi_by_poi.setdefault(bi.get('po_item_id'), []).append(bi)
    _s_ri_by_poi: dict = {}
    for ri in _s_ri_all: _s_ri_by_poi.setdefault(ri.get('po_item_id'), []).append(ri)
    _is_internal_po = po.get('business_type') == 'internal'
    for item in items:
        ship_items_for_item = _s_vsi_by_poi.get(item['id'], [])
        received = 0; missing = 0
        for si in ship_items_for_item:
            ship = _s_ship_map.get(si.get('shipment_id'), {})
            if ship.get('inspection_status') == 'Inspected':
                insp = _s_insp_map.get(si.get('shipment_id'))
                if insp:
                    ii = _s_ii_map.get(si['id'])
                    if ii:
                        received += ii.get('received_qty', 0); missing += ii.get('missing_qty', 0)
                    else: received += si.get('qty_sent', 0)
            elif ship.get('status') == 'Received':
                received += si.get('qty_sent', 0)
        total_defect = sum(d.get('defect_qty', 0) for d in _s_def_by_poi.get(item['id'], []))
        if _is_internal_po and not ship_items_for_item:
            # PO internal: material diserahkan gudang ke job (bukan kiriman vendor)
            received = sum(int(ji.get('available_qty', 0) or 0) for ji in _s_ji_by_poi.get(item['id'], []))
        available = max(0, received - total_defect)
        produced = sum(ji.get('produced_qty', 0) for ji in _s_ji_by_poi.get(item['id'], []))
        shipped  = sum(bi.get('qty_shipped', 0) for bi in _s_bi_by_poi.get(item['id'], []))
        returned = sum(ri.get('return_qty', 0) for ri in _s_ri_by_poi.get(item['id'], []))
        ordered = item.get('qty', 0)
        over = max(0, produced - ordered); under = max(0, ordered - produced)
        summary_items.append({
            **serialize_doc(item),
            'ordered_qty': ordered, 'received_qty': received, 'missing_qty': missing,
            'defect_qty': total_defect, 'available_qty': available, 'produced_qty': produced,
            'shipped_qty': shipped, 'returned_qty': returned,
            'overproduction_qty': over, 'underproduction_qty': under
        })
        totals['ordered'] += ordered; totals['received'] += received
        totals['missing'] += missing; totals['defect'] += total_defect
        totals['available'] += available; totals['produced'] += produced
        totals['shipped'] += shipped; totals['returned'] += returned
    totals['overproduction'] = max(0, totals['produced'] - totals['ordered'])
    totals['underproduction'] = max(0, totals['ordered'] - totals['produced'])

    # ── FASE 1: buku kuantitas QC (accepted / reject / rework / scrap) ─────────
    # CACAT LAMA (INV-3): ringkasan ini tidak pernah memuat angka reject, sehingga
    # saat menutup PO tidak terlihat "produced 100, reject 10". Sekarang angka QC
    # diambil dari SSOT buku kuantitas job item.
    try:
        from core import production_qty_ledger as qty_ledger
        led = await qty_ledger.po_ledger_totals(db, po_id)
        lt = led['totals']
        totals.update({
            'declared': lt['declared'],
            'accepted': lt['accepted'],
            'reject': lt['reject'],
            'reject_open': lt['rework_open'],
            'reject_undecided': lt['reject_undecided'],
            'repaired': lt['repaired'],
            'scrap': lt['scrap'],
            'reject_rate_pct': lt['reject_rate_pct'],
        })
        per = led['per_po_item']
        for si in summary_items:
            p = per.get(si.get('id')) or {}
            si.update({
                'declared_qty': p.get('declared', 0),
                'accepted_qty': p.get('accepted', 0),
                'reject_qty_qc': p.get('reject', 0),
                'rework_open_qty': p.get('rework_open', 0),
                'repaired_qty': p.get('repaired', 0),
                'scrap_qty': p.get('scrap', 0),
            })
    except Exception:
        import logging as _lg
        _lg.getLogger(__name__).exception('buku kuantitas QC gagal dihitung utk PO %s', po_id)
        totals.setdefault('accepted', 0); totals.setdefault('reject', 0)

    return {'po': serialize_doc(po), 'items': summary_items, 'totals': totals}

@router.get("/po-accessories")
async def get_po_accessories(request: Request):
    """Get accessories linked to a PO."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    po_id = request.query_params.get('po_id')
    if not po_id: raise HTTPException(400, 'po_id required')
    return serialize_doc(await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).sort('created_at', 1).to_list(None))

@router.post("/po-accessories")
async def add_po_accessory(request: Request):
    """Add accessory to a PO."""
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po_id = body.get('po_id')
    if not po_id: raise HTTPException(400, 'po_id required')
    items = body.get('items', [])
    inserted = []
    for item in items:
        acc_doc = {
            'id': new_id(), 'po_id': po_id,
            'accessory_id': item.get('accessory_id'),
            'accessory_name': item.get('accessory_name', ''),
            'accessory_code': item.get('accessory_code', ''),
            'qty_needed': int(item.get('qty_needed', 0) or 0),
            'unit': item.get('unit', 'pcs'),
            'notes': item.get('notes', ''),
            'created_at': now()
        }
        await db.po_accessories.insert_one(acc_doc)
        inserted.append(acc_doc)
    await log_activity(user['id'], user['name'], 'Add Accessories', 'Production PO',
                       f"Added {len(inserted)} accessories to PO")
    return JSONResponse(serialize_doc(inserted), status_code=201)

@router.delete("/po-accessories/{acc_id}")
async def remove_po_accessory(acc_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    await db.po_accessories.delete_one({'id': acc_id})
    return {'success': True}
