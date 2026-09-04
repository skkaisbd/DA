"""Buyer Shipment & Traceability domain: Buyer Shipments (+ items, dispatches,
force-edit, received qty, receipt variance), Serial Tracking Timeline.

Moved out of server.py during Backend Refactor Phase 8
(see /app/BACKEND_REFACTOR_PLAN.md). Pure move — behavior is byte-for-byte
identical to the original definitions in server.py. HIGH risk phase per the
plan (qty_shipped vs qty_received logic is the newest & most sensitive,
Phase 17-19 of the PRD) — every line below is an exact cut-paste from
server.py, no logic was altered.

Phase B (CMT → DA → Buyer, 2026-07-16):
  * `receiver_type` field ('da' or 'buyer', default 'buyer' for backward compat).
  * Role gate:
      - Vendor CMT → force `receiver_type='da'` (Deklarasi Kirim ke DA).
        On save, auto-create draft `cmt_receipts` yg akan diproses DA admin.
      - DA admin  → default `receiver_type='buyer'`; `receiver_type='da'`
        eksplisit ditolak (403). `receiver_type='buyer'` wajib `source_receipt_ids[]`
        yg mengacu ke `cmt_receipts` status Approved.
  * Qty cap:
      - `receiver_type='da'` → tidak ada cap produced_qty (declaration only).
      - `receiver_type='buyer'` → cap terhadap Σ `cmt_receipts.qty_actual`
        (dari `source_receipt_ids`) minus qty yg sudah dispatch dari receipt yang sama.
  * COGS posting hanya jalan untuk `receiver_type='buyer'` (dispatch riil).
"""
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
import logging

logger = logging.getLogger(__name__)
from routes.production_rbac import (PROD_ADMIN_ROLES, PROD_VENDOR_ROLES,
    is_vendor, vendor_identity, deny_klien, require_write_actor,
    resolve_vendor_doc, resolve_buyer_name)
from core.helpers import new_id, now, parse_date
from core.pagination import LEGACY_DEFAULT_CAP, _paginate_params, _paginated_envelope, _sort_params
from utils.waktu import now_wib

router = APIRouter(prefix="/api", tags=["buyer-shipments"])


# ═══════════════════════════════════════════════════════════════════════════
# PHASE B — CMT → DA → Buyer helpers
# ═══════════════════════════════════════════════════════════════════════════

RECEIVER_DA = 'da'
RECEIVER_BUYER = 'buyer'


def _resolve_receiver_type(body: dict, user: dict, override_ctx: dict | None = None) -> str:
    """Determine receiver_type per role gate. Called INSIDE create endpoint
    so the endpoint stays testable via HTTP.

    - is_vendor(user): force 'da' (silently override client body).
    - staf DA dalam **mode Portal CMT Override** (`override_ctx` terisi): dianggap
      SAMA dengan vendor ⇒ default & boleh 'da'. Tanpa ini, modul "Kirim ke Buyer"
      (deklarasi kirim CMT→DA) MUSTAHIL diisi staf atas nama vendor yang tidak
      memakai sistem — dan itulah modul yang paling menentukan TAGIHAN CMT.
      Aman karena `override_ctx` hanya terbit setelah role + vendor divalidasi
      (core/cmt_override.resolve_override) dan dokumennya selalu distempel
      `entered_by_staff` sehingga jelas bukan deklarasi vendor sendiri.
    - else (DA-admin/superadmin):
        * if body sends receiver_type='da' → 403 (only vendor can declare CMT ship)
        * else default 'buyer' (also for legacy clients not sending the field)
    """
    if is_vendor(user):
        return RECEIVER_DA
    _default = RECEIVER_DA if override_ctx else RECEIVER_BUYER
    requested = (body.get('receiver_type') or _default).lower().strip()
    if requested == RECEIVER_DA:
        if override_ctx:
            return RECEIVER_DA
        raise HTTPException(
            403,
            'Hanya vendor CMT yang boleh membuat pengiriman receiver_type=da. '
            'DA admin memakai receiver_type=buyer dengan source_receipt_ids. '
            'Untuk mengisi atas nama vendor, buka Portal CMT Override.'
        )
    if requested not in (RECEIVER_DA, RECEIVER_BUYER):
        raise HTTPException(400, f"receiver_type tidak valid: '{requested}'")
    return RECEIVER_BUYER


async def _validate_source_receipts_cap(db, source_receipt_ids: list, items_data: list, user: dict):
    """Phase B: for DA + receiver_type='buyer', validate that:
      1. source_receipt_ids[] non-empty
      2. All referenced `cmt_receipts` exist AND status='Approved'
      3. Sum(qty_shipped requested per po_item/sku) does not exceed
         Sum(qty_actual across source receipts) minus already dispatched
         from these same receipts.

    Returns dict {source_receipt_ids, receipts, receipt_lines} for downstream.
    Raises HTTPException on any violation.
    """
    if not source_receipt_ids:
        raise HTTPException(
            400,
            'Buyer shipment dari DA wajib source_receipt_ids[] (mengacu ke '
            'cmt_receipts status Approved). Phase B enforcement.'
        )
    receipts = await db.cmt_receipts.find(
        {'id': {'$in': list(source_receipt_ids)}}, {'_id': 0}
    ).to_list(None)
    if len(receipts) != len(set(source_receipt_ids)):
        found_ids = {r['id'] for r in receipts}
        missing = [rid for rid in source_receipt_ids if rid not in found_ids]
        raise HTTPException(
            400, f"cmt_receipts tidak ditemukan: {missing}"
        )
    # FASE 4: status penerimaan disederhanakan menjadi `completed_qc` (lama:
    # `Approved`). Gerbang ini memakai SSOT `core/cmt_receipt_status` supaya
    # dokumen lama MAUPUN baru sama-sama diterima — bukan literal 'Approved'.
    from core.cmt_receipt_status import is_done as _receipt_done
    non_approved = [r for r in receipts if not _receipt_done(r.get('status'))]
    if non_approved:
        raise HTTPException(
            400,
            'Semua source_receipt_ids harus sudah SELESAI QC. Ditolak: ' +
            ', '.join(f"{r.get('receipt_code','?')}({r.get('status')})" for r in non_approved)
        )
    # ── FASE E (2026-08-15) — SATU SSOT KAPASITAS KIRIM ──────────────────────
    # DULU pagar ini punya rumusnya SENDIRI dan layar punya rumus LAIN, sehingga
    # form mem-prefill angka yang pasti ditolak di sini (keluhan pemilik: "Maks
    # (dari CMT) 100 tapi disimpan katanya maksimal 50"). Sekarang keduanya
    # membaca `core.dispatch_capacity` — kalau rumusnya berubah, dua-duanya ikut.
    # Perubahan nyata dibanding versi lama:
    #   · qty sudah-dikirim dihitung per po_item MELINTASI SEMUA surat jalan
    #     buyer (bukan hanya yang memakai receipt terpilih) — definisi yang sama
    #     dengan kolom "Sudah Dikirim" yang dilihat pemakai.
    #   · hasil PERMAK (`qty_reworked_ok`) ikut menambah kapasitas, supaya barang
    #     reject yang sudah diperbaiki BISA dikirim (dulu mustahil selamanya).
    from core import dispatch_capacity as dcap
    cap_rows = await dcap.map_for_validation(
        db, receipt_ids=list(source_receipt_ids), items_data=items_data)
    receipt_lines = await db.cmt_receipt_lines.find(
        {'receipt_id': {'$in': list(source_receipt_ids)}}, {'_id': 0}
    ).to_list(None)

    requested_by_key = {}
    label_by_key = {}
    for it in items_data:
        q = int(it.get('qty_shipped', 0) or 0)
        if q > 0:
            k = dcap.line_key(it.get('po_item_id'), it.get('sku'))
            requested_by_key[k] = requested_by_key.get(k, 0) + q
            label_by_key.setdefault(k, (it.get('sku') or it.get('po_item_id') or '?'))

    for k, req_qty in requested_by_key.items():
        row = cap_rows.get(k) or {}
        good = int(row.get('good_from_cmt', 0) or 0)
        fixed = int(row.get('reworked_ok', 0) or 0)
        already = int(row.get('dispatched', 0) or 0)
        max_avail = int(row.get('shippable', max(0, good + fixed - already)) or 0)
        if req_qty > max_avail:
            label = row.get('sku') or label_by_key.get(k, k)
            detail = (f'lolos QC {good} pcs'
                      + (f' + hasil permak {fixed} pcs' if fixed else '')
                      + f' − sudah dikirim {already} pcs')
            raise HTTPException(
                400,
                f'Qty kirim untuk {label} ({req_qty} pcs) melebihi sisa yang boleh '
                f'dikirim. Perhitungan: {detail} = sisa {max_avail} pcs. '
                f'Ubah qty menjadi maksimal {max_avail} pcs.'
            )

    return {
        'source_receipt_ids': list(source_receipt_ids),
        'receipts': receipts,
        'receipt_lines': receipt_lines,
        'capacity': cap_rows,
    }


async def _resolve_pos_for_items(db, items_data, body_po_id, receiver_type):
    """Phase D: resolve the PO(s) referenced by shipment items. A DA→buyer surat
    jalan may span MULTIPLE POs of the SAME buyer (consolidation). Returns the
    primary PO (only when a single PO), the distinct po_ids, a po_item->po map,
    a po_by_id map, the buyer name, and the business_type. Enforces single-buyer
    per surat jalan for buyer dispatch."""
    po_item_ids = [it.get('po_item_id') for it in (items_data or []) if it.get('po_item_id')]
    poitem_to_po = {}
    po_ids = []
    if po_item_ids:
        poi_docs = await db.po_items.find(
            {'id': {'$in': po_item_ids}}, {'_id': 0, 'id': 1, 'po_id': 1}).to_list(None)
        for d in poi_docs:
            if d.get('po_id'):
                poitem_to_po[d['id']] = d['po_id']
        po_ids = list(dict.fromkeys(poitem_to_po.values()))  # unique, order-preserving
    if not po_ids and body_po_id:
        po_ids = [body_po_id]

    po_by_id = {}
    if po_ids:
        pos = await db.production_pos.find({'id': {'$in': po_ids}}, {'_id': 0}).to_list(None)
        po_by_id = {p['id']: p for p in pos}

    customer_name = ''
    business_type = 'internal'
    if po_by_id:
        buyers = list({(p.get('customer_name') or '').strip()
                       for p in po_by_id.values() if (p.get('customer_name') or '').strip()})
        if receiver_type == RECEIVER_BUYER and len(buyers) > 1:
            raise HTTPException(
                400,
                'Surat jalan konsolidasi hanya boleh untuk 1 buyer. '
                f'Terdeteksi beberapa buyer berbeda: {buyers}.')
        customer_name = buyers[0] if buyers else ''
        bts = list({(p.get('business_type') or 'internal') for p in po_by_id.values()})
        business_type = bts[0] if bts else 'internal'

    primary_po_id = po_ids[0] if len(po_ids) == 1 else None
    primary_po = po_by_id.get(primary_po_id) if primary_po_id else None
    return {
        'poitem_to_po': poitem_to_po, 'po_ids': po_ids, 'po_by_id': po_by_id,
        'primary_po_id': primary_po_id, 'primary_po': primary_po,
        'customer_name': customer_name, 'business_type': business_type,
    }


async def _auto_create_cmt_receipt_from_shipment(db, shipment: dict, items: list, user: dict,
                                                dispatch_seq: int = 1) -> str:
    """Phase B: when a vendor CMT creates a buyer_shipment with receiver_type='da',
    auto-create a matching `cmt_receipts` document (Draft) with lines pre-populated
    from `buyer_shipment_items`. DA admin then fills `qty_actual` / `reject_qty`
    via `PUT /cmt-receipts/{id}/lines/{lid}` and finally approves it.

    PERBAIKAN 2026-08-01 (kirim ulang selisih): dulu penerimaan DA hanya dibuat
    untuk dispatch PERTAMA (`is_new`). Deklarasi kirim ULANG (dispatch #2, #3 …)
    — jalur utama penyelesaian selisih kirim — tidak menghasilkan penerimaan
    sehingga barangnya TIDAK BISA diterima DA. Sekarang SETIAP dispatch deklarasi
    membuat satu penerimaan (idempoten per `related_shipment_id` + `dispatch_seq`).

    Returns the new receipt_id (empty string on failure — best-effort; never
    breaks the main dispatch flow).
    """
    try:
        import uuid as _uuid
        from utils.counters import gen_prefixed_number
        existing = await db.cmt_receipts.find_one(
            {'related_shipment_id': shipment['id'],
             'related_dispatch_seq': int(dispatch_seq or 1)}, {'_id': 0, 'id': 1})
        if existing:
            return existing['id']
        # Vendor / cmt name resolution — reuse the same fields the buyer_shipment
        # already carries (vendor_name is filled by resolve_vendor_doc).
        cmt_name = shipment.get('vendor_name', '') or (user.get('name') or '')
        vendor_id = shipment.get('vendor_id') or ''
        po_id = shipment.get('po_id') or ''
        po = await db.production_pos.find_one({'id': po_id}) if po_id else None
        wo_number = (po or {}).get('po_number', '')
        receipt_code = await gen_prefixed_number(db, 'cmt_receipts', 'receipt_code', 'CMT-RCV-', 5)
        receipt_id = str(_uuid.uuid4())
        now_ts = now()
        _seq = int(dispatch_seq or 1)
        doc = {
            'id': receipt_id,
            'receipt_code': receipt_code,
            'cmt_name': cmt_name,
            'cmt_vendor_id': vendor_id,
            'wo_number': wo_number,
            'wo_id': shipment.get('job_id', ''),
            'po_id': po_id,
            'po_number': wo_number,
            'business_type': shipment.get('business_type', 'internal'),
            'receipt_date': str(now_ts)[:10],
            'delivery_note': (f"{shipment.get('shipment_number', '')}"
                              + (f" · kirim ke-{_seq}" if _seq > 1 else '')),
            'notes': (f"Auto-generated dari CMT declaration {shipment.get('shipment_number','')}"
                      f" (dispatch #{_seq})."),
            'status': 'Draft',
            'submitted_at': '', 'submitted_by': '',
            'approved_at': '', 'approved_by': '',
            'reject_reason': '',
            # Phase B linkage fields:
            'related_shipment_id': shipment['id'],
            'related_dispatch_seq': _seq,
            'total_shipped_by_cmt': 0,
            'total_actual': 0,
            'total_rejected': 0,
            'variance_reason': '',
            'defect_photos': [],
            'created_by': user['name'],
            'created_at': now_ts, 'updated_at': now_ts,
        }
        await db.cmt_receipts.insert_one(doc)

        # Populate lines — one per buyer_shipment_items row with qty_shipped > 0.
        total_shipped = 0
        for it in items:
            qty = int(it.get('qty_shipped', 0) or 0)
            if qty <= 0:
                continue
            total_shipped += qty
            await db.cmt_receipt_lines.insert_one({
                'id': str(_uuid.uuid4()),
                'receipt_id': receipt_id,
                'sku_code': it.get('sku', ''),
                'product_name': it.get('product_name', ''),
                'color': it.get('color', ''),
                'size': it.get('size', ''),
                'qty_expected': qty,   # equals what CMT declared shipping
                'qty_shipped_by_cmt': qty,
                'qty_claimed_by_cmt': qty,   # klaim vendor (dipisah dari dokumen resmi)
                'qty_short': 0, 'qty_short_resolved': 0, 'short_status': '',
                'qty_actual': None,    # DA fills this on inspection
                'reject_qty': 0,
                'reject_reason': '',
                'photos': [],
                'source_buyer_shipment_item_id': it.get('id'),
                'po_item_id': it.get('po_item_id'),
                'job_item_id': it.get('job_item_id'),
                'notes': '',
                'created_at': now_ts,
            })
        # Cache total_shipped_by_cmt on the header for quick display.
        await db.cmt_receipts.update_one(
            {'id': receipt_id},
            {'$set': {'total_shipped_by_cmt': total_shipped, 'updated_at': now()}}
        )
        return receipt_id
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            'Phase B: gagal auto-create cmt_receipts dari buyer_shipments %s',
            shipment.get('id')
        )
        return ''

async def _fg_precheck_for_dispatch(db, items_data: list) -> list:
    """GAP E (pre-flight) — pastikan stok FG CUKUP sebelum surat jalan dibuat.

    Dijalankan SEBELUM dokumen ditulis supaya kegagalan stok tidak meninggalkan
    surat jalan setengah jadi. SKU tanpa master FG hanya menghasilkan peringatan
    (barangnya memang belum pernah masuk stok — mis. data lama).
    """
    from core import production_qty_ledger as qled
    from core import stock_service
    from core import quarantine as qmod
    try:
        qloc = await qmod.get_quarantine_location_id(db)
    except Exception:  # noqa: BLE001
        qloc = None
    warnings, need = [], {}
    for it in items_data:
        qty = int(it.get('qty_shipped', 0) or 0)
        if qty <= 0:
            continue
        sku = (it.get('sku') or '').strip()
        if not sku:
            continue
        need[sku] = need.get(sku, 0) + qty
    for sku, qty in need.items():
        mat = await qled.resolve_fg_material(db, sku=sku)
        if not mat:
            warnings.append(f"Master FG {sku} tidak ditemukan — stok FG tidak dikurangi.")
            continue
        rows = await stock_service.list_rows(mat['id'], db=db)
        have = 0.0
        for r in rows:
            if r.get('location_id') == qloc:
                continue
            try:
                have += float(r.get('qty') or r.get('quantity') or 0)
            except (TypeError, ValueError) as e:
                # 2026-08-07 — DULU `pass` tanpa jejak. Arahnya "aman" (stok
                # dihitung LEBIH KECIL ⇒ pengiriman diblokir, bukan lolos), tetapi
                # penyebabnya — baris stok dengan qty bukan angka — tidak pernah
                # dilaporkan. Hasilnya keluhan "stok jelas ada tapi katanya kurang"
                # yang tak bisa dijelaskan siapa pun. Sekarang selalu tercatat.
                logger.error(
                    "[kirim-buyer] baris stok %s material %s (%s) punya qty yang BUKAN "
                    "ANGKA (%r) — baris ini dihitung 0 sehingga stok tampak lebih "
                    "sedikit dan pengiriman bisa terblokir. Perbaiki baris stok ini: %s",
                    r.get('id'), mat.get('id'), sku, r.get('qty') or r.get('quantity'), e)
        if have + 0.0001 < qty:
            raise HTTPException(
                400,
                f"Stok FG {sku} tidak cukup untuk dikirim: butuh {qty} pcs, tersedia "
                f"{have:g} pcs. Selesaikan scan-in gudang untuk hasil produksi / QC "
                f"penerimaan dari CMT dulu, atau perbaiki stok lewat Stock Opname.")
    return warnings


async def _issue_fg_for_dispatch(db, shipment: dict, items: list, user: dict) -> dict:
    """GAP E — stok FG BERKURANG saat barang dikirim ke buyer.

    BUG NYATA (audit 2026-07-31): kirim 100 pcs ke buyer → stok FG tetap 100
    (`rahaza_fg_movements` hanya berisi IN, tidak ada `stock_service.issue`
    untuk dispatch buyer di seluruh backend) ⇒ nilai persediaan FG menggelembung
    dan gudang tidak pernah "kosong" walau barang sudah keluar.

    IDEMPOTEN per baris dispatch (`fg_issued_at`).
    """
    from core import production_qty_ledger as qled
    out = {'issued': [], 'warnings': []}
    for it in items:
        if it.get('fg_issued_at'):
            continue
        qty = int(it.get('qty_shipped', 0) or 0)
        if qty <= 0:
            continue
        sku = (it.get('sku') or '').strip()
        mat = await qled.resolve_fg_material(db, sku=sku) if sku else None
        if not mat:
            out['warnings'].append(f"Master FG {sku or it.get('id')} tidak ditemukan — "
                                   "stok FG tidak dikurangi.")
            continue
        ref = {'source': 'buyer_shipment', 'shipment_id': shipment.get('id'),
               'shipment_number': shipment.get('shipment_number'),
               'dispatch_seq': it.get('dispatch_seq'), 'shipment_item_id': it.get('id'),
               'po_id': it.get('po_id') or shipment.get('po_id'),
               'po_number': it.get('po_number') or shipment.get('po_number'),
               'customer_name': shipment.get('customer_name')}
        try:
            res = await qled.issue_fg(db, material_id=mat['id'], qty=qty, sku=sku,
                                     ref=ref, actor=user)
        except qled.FGStockShortfall as e:
            out['warnings'].append(str(e))
            continue
        except Exception as e:  # noqa: BLE001
            import logging as _lg
            _lg.getLogger(__name__).exception('stok FG keluar gagal (item %s)', it.get('id'))
            out['warnings'].append(f"Stok FG {sku} gagal dikurangi: {e}")
            continue
        await db.buyer_shipment_items.update_one({'id': it['id']}, {'$set': {
            'fg_issued_at': now(), 'fg_issued_qty': qty, 'fg_material_id': mat['id'],
            # SESI #34 — biaya batch (FIFO) yang IKUT keluar bersama barangnya.
            # `fg_cogs_uncosted_qty` > 0 berarti sebagian barang keluar tanpa
            # lapisan biaya (batch masuknya belum punya HPP) — angka itu tidak
            # boleh ditutup, karena ia menjelaskan kenapa HPP terlihat murah.
            'fg_cogs': res.get('cogs', 0.0),
            'fg_cogs_layers': res.get('cogs_layers') or [],
            'fg_cogs_uncosted_qty': res.get('uncosted_qty', 0)}})
        it['fg_issued_at'] = now()
        await db.rahaza_fg_movements.insert_one({
            'id': new_id(), 'sku_code': sku, 'movement_type': 'OUT', 'qty': qty,
            'source': 'buyer_shipment', 'ref_id': shipment.get('id'),
            'ref_number': shipment.get('shipment_number'),
            'material_id': mat['id'],
            'location_id': (res.get('issued') or [{}])[0].get('location_id', ''),
            'dispatch_seq': it.get('dispatch_seq'),
            'shipment_item_id': it.get('id'),
            'notes': (f"Kirim ke buyer {shipment.get('customer_name') or ''} — SJ "
                      f"{shipment.get('shipment_number')} dispatch #{it.get('dispatch_seq')}"),
            'cogs_fifo': res.get('cogs', 0.0),
            'cogs_uncosted_qty': res.get('uncosted_qty', 0),
            'created_by': user.get('name', ''), 'created_at': now()})
        out['issued'].append({'sku': sku, 'qty': qty, 'rows': res.get('issued')})
    return out


# ─── BUYER SHIPMENTS ─────────────────────────────────────────────────────────
@router.get("/buyer-dispatch-capacity")
async def buyer_dispatch_capacity(request: Request):
    """FASE E — kapasitas kirim per item, memakai SSOT `core.dispatch_capacity`.

    Dipakai form "Buat Buyer Shipment" supaya angka di layar SAMA PERSIS dengan
    pagar yang menolak saat Simpan. Sebelum ini layar menghitung sendiri dan
    salah dua kali (memotong reject dua kali + tidak mengurangi yang sudah
    dikirim), sehingga pemakai selalu diarahkan ke angka yang pasti ditolak.

    Query (pilih salah satu):
      receipt_ids=<id,id,...>   → sesuai CMT Receipt yang dicentang di form
      po_item_ids=<id,id,...>   → langsung per item PO
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    from core import dispatch_capacity as dcap

    def _split(name):
        raw = sp.get(name) or ''
        return [x.strip() for x in raw.split(',') if x.strip()]

    receipt_ids = _split('receipt_ids')
    po_item_ids = _split('po_item_ids')
    want_stock = (sp.get('with_fg_stock') or '').lower() in ('1', 'true', 'yes')
    if receipt_ids:
        rows = await dcap.by_receipts(db, receipt_ids, with_fg_stock=want_stock)
    elif po_item_ids:
        rows = await dcap.by_po_items(db, po_item_ids, with_fg_stock=want_stock)
    else:
        raise HTTPException(400, 'receipt_ids[] atau po_item_ids[] wajib diisi')
    return {
        'items': rows,
        'totals': {
            'good_from_cmt': sum(r['good_from_cmt'] for r in rows),
            'reworked_ok': sum(r['reworked_ok'] for r in rows),
            'internal_produced': sum(r['internal_produced'] for r in rows),
            'dispatched': sum(r['dispatched'] for r in rows),
            'shippable': sum(r['shippable'] for r in rows),
        },
        'formula': 'sisa bisa kirim = lolos QC + hasil permak + hasil produksi internal − sudah dikirim',
    }


@router.get("/buyer-dispatch-outstanding")
async def buyer_dispatch_outstanding(request: Request):
    """FASE E — DAFTAR KEKURANGAN KIRIM (dispatch list).

    Semua item yang barangnya SUDAH diterima dari CMT tetapi belum habis dikirim
    ke buyer, beserta stok FG yang benar-benar tersedia. Tujuannya menghilangkan
    kerja menebak: pemakai bisa langsung melihat "sisa 20 pcs, stok ada 20" lalu
    membuat dispatch susulan tanpa membuka-buka PO satu per satu.
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    from core import dispatch_capacity as dcap
    rows = await dcap.outstanding(
        db,
        buyer=(sp.get('buyer') or '').strip(),
        po_id=(sp.get('po_id') or '').strip(),
        include_settled=(sp.get('include_settled') or '').lower() in ('1', 'true', 'yes'),
    )
    buyers = sorted({(r.get('buyer') or '').strip() for r in rows if (r.get('buyer') or '').strip()})
    return {
        'items': rows,
        'buyers': buyers,
        'totals': {
            'ordered': sum(r['ordered'] for r in rows),
            'dispatched': sum(r['dispatched'] for r in rows),
            'shippable': sum(r['shippable'] for r in rows),
            'items': len(rows),
        },
    }


@router.get("/buyer-shipments")
async def get_buyer_shipments(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('po_id'):
        # Phase D: a consolidated surat jalan may not carry po_id on the HEADER
        # (it spans multiple POs). Match shipments whose header OR any item points
        # to this PO, via a precomputed id-set (avoids clashing with search $or).
        _pid = sp['po_id']
        _ids = set(await db.buyer_shipments.distinct('id', {'po_id': _pid}))
        _ids |= set(await db.buyer_shipment_items.distinct('shipment_id', {'po_id': _pid}))
        query['id'] = {'$in': list(_ids)}
    _bt = sp.get('business_type')
    if _bt == 'maklon': query['business_type'] = 'maklon'
    elif _bt == 'internal': query['business_type'] = {'$ne': 'maklon'}  # internal + legacy/null
    elif _bt: query['business_type'] = _bt
    from core.cmt_override import apply_scope as _ov_scope
    await _ov_scope(request, user, db, query, param_vendor_id=sp.get('vendor_id'))
    if sp.get('status'): query['ship_status'] = sp['status']
    # Phase B — receiver_type filter (default: all). Legacy docs w/o field are
    # treated as 'buyer' for backward compat.
    rt = (sp.get('receiver_type') or '').strip().lower()
    _receiver_clause = None
    if rt == RECEIVER_DA:
        _receiver_clause = [{'receiver_type': RECEIVER_DA}]
    elif rt == RECEIVER_BUYER:
        _receiver_clause = [
            {'receiver_type': RECEIVER_BUYER},
            {'receiver_type': {'$exists': False}},
            {'receiver_type': None},
        ]
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'shipment_number': {'$regex': search, '$options': 'i'}},
            {'customer_name': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
        ]

    # Combine search $or with receiver_type $or via $and (mongo forbids two $or at root).
    if _receiver_clause is not None:
        if query.get('$or'):
            query['$and'] = [{'$or': query.pop('$or')}, {'$or': _receiver_clause}]
        else:
            query['$or'] = _receiver_clause

    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'shipment_number', 'customer_name',
                                 'vendor_name', 'po_number', 'ship_status'})
    total = await db.buyer_shipments.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    cursor = db.buyer_shipments.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit)
    shipments = await cursor.to_list(limit)

    # ── Phase 10B: batch-fetch items ──
    ship_ids = [s['id'] for s in shipments]
    if ship_ids:
        items_all = await db.buyer_shipment_items.find({'shipment_id': {'$in': ship_ids}}, {'_id': 0}).to_list(None)
    else:
        items_all = []
    items_by_ship = {}
    for it in items_all:
        items_by_ship.setdefault(it['shipment_id'], []).append(it)

    # ── FASE 22 (keluhan #6) — nomor PO untuk surat jalan GABUNGAN ────────────
    # Surat jalan gabungan tidak punya `po_number` di header (memang lintas PO),
    # jadi kolom "NO. PO" di tabel KOSONG dan pengguna tidak tahu isinya PO apa.
    # Kirim `po_numbers[]` + `is_consolidated` supaya tabel bisa menampilkan
    # "2 PO (gabungan): PO-A, PO-B" tanpa harus membuka detail.
    _all_po_ids = set()
    for s in shipments:
        for pid in (s.get('po_ids') or []):
            if pid:
                _all_po_ids.add(pid)
        if s.get('po_id'):
            _all_po_ids.add(s['po_id'])
    for it in items_all:
        if it.get('po_id'):
            _all_po_ids.add(it['po_id'])
    po_no_by_id = {}
    if _all_po_ids:
        for p in await db.production_pos.find(
                {'id': {'$in': list(_all_po_ids)}}, {'_id': 0, 'id': 1, 'po_number': 1}).to_list(None):
            po_no_by_id[p['id']] = p.get('po_number')

    result = []
    for s in shipments:
        items = items_by_ship.get(s['id'], [])
        po_ids = list(s.get('po_ids') or ([s['po_id']] if s.get('po_id') else []))
        if not po_ids:
            po_ids = [p for p in dict.fromkeys(i.get('po_id') for i in items) if p]
        po_numbers = [po_no_by_id.get(p) for p in po_ids if po_no_by_id.get(p)]
        if not po_numbers and s.get('po_number'):
            po_numbers = [s['po_number']]
        is_consolidated = bool(s.get('is_consolidated')) or len(po_ids) > 1
        po_item_map = {}
        for item in items:
            key = item.get('po_item_id') or item['id']
            if key not in po_item_map:
                po_item_map[key] = {'ordered_qty': item.get('ordered_qty', 0), 'shipped': 0, 'received': 0}
            po_item_map[key]['shipped'] += item.get('qty_shipped', 0)
            po_item_map[key]['received'] += (item['qty_received'] if item.get('qty_received') is not None else item.get('qty_shipped', 0))
        total_ordered = sum(v['ordered_qty'] for v in po_item_map.values())
        total_shipped = sum(v['shipped'] for v in po_item_map.values())
        total_received = sum(v['received'] for v in po_item_map.values())
        remaining = max(0, total_ordered - total_received)
        pct = round((total_received / total_ordered * 100)) if total_ordered > 0 else 0
        max_dispatch = max((i.get('dispatch_seq', 1) for i in items), default=0)
        result.append({**serialize_doc(s), 'items': serialize_doc(items),
                       'po_ids': po_ids, 'po_numbers': po_numbers,
                       'is_consolidated': is_consolidated,
                       'receiver_type': s.get('receiver_type') or RECEIVER_BUYER,
                       'total_ordered': total_ordered, 'total_shipped': total_shipped,
                       'total_received': total_received,
                       'remaining': remaining, 'progress_pct': pct, 'dispatch_count': max_dispatch})

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result

@router.get("/buyer-shipments/{bsid}")
async def get_buyer_shipment(bsid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    s = await db.buyer_shipments.find_one({'id': bsid}, {'_id': 0})
    if not s: raise HTTPException(404, 'Not found')
    items = await db.buyer_shipment_items.find({'shipment_id': bsid}, {'_id': 0}).sort([('dispatch_seq', 1), ('created_at', 1)]).to_list(None)
    dispatch_map = {}
    poi_totals = {}
    for item in items:
        seq = item.get('dispatch_seq', 1)
        if seq not in dispatch_map:
            dispatch_map[seq] = {'dispatch_seq': seq, 'dispatch_date': item.get('dispatch_date') or item.get('created_at'), 'items': [], 'total_qty': 0}
        dispatch_map[seq]['items'].append(serialize_doc(item))
        dispatch_map[seq]['total_qty'] += item.get('qty_shipped', 0)
        key = item.get('po_item_id') or item['id']
        if key not in poi_totals:
            poi_totals[key] = {'po_item_id': item.get('po_item_id'), 'sku': item.get('sku', ''),
                               'product_name': item.get('product_name', ''), 'serial_number': item.get('serial_number', ''),
                               'size': item.get('size', ''), 'color': item.get('color', ''),
                               'ordered_qty': item.get('ordered_qty', 0), 'cumulative_shipped': 0, 'cumulative_received': 0}
        poi_totals[key]['cumulative_shipped'] += item.get('qty_shipped', 0)
        poi_totals[key]['cumulative_received'] += (item['qty_received'] if item.get('qty_received') is not None else item.get('qty_shipped', 0))
    dispatches = sorted(dispatch_map.values(), key=lambda d: d['dispatch_seq'])
    summary_items = list(poi_totals.values())
    total_ordered = sum(i['ordered_qty'] for i in summary_items)
    total_shipped = sum(i['cumulative_shipped'] for i in summary_items)
    total_received = sum(i['cumulative_received'] for i in summary_items)
    remaining = max(0, total_ordered - total_received)
    pct = round((total_received / total_ordered * 100)) if total_ordered > 0 else 0
    result = serialize_doc(s)
    result.update({'items': serialize_doc(items), 'dispatches': dispatches,
                   'summary_items': summary_items, 'total_ordered': total_ordered,
                   'total_shipped': total_shipped, 'total_received': total_received,
                   'remaining': remaining, 'progress_pct': pct})

    # ── FASE 6 (cacat CONS-1/CONS-3 + keluhan #6 owner) ───────────────────────
    # "jika saya gabungkan dan ada child shipment maka tidak bisa ambil data child
    #  shipmentnya, sangat berantakan."
    # Detail surat jalan sekarang SELALU mengembalikan:
    #   · `po_breakdown[]`  — rincian per PO di dalam satu surat jalan gabungan
    #   · `child_shipments[]` — surat jalan turunan (beserta itemnya)
    #   · `parent_shipment`   — induk bila dokumen ini adalah child
    #   · `source_receipts[]` — penerimaan CMT yang menjadi sumber barang
    po_ids = list(s.get('po_ids') or ([s.get('po_id')] if s.get('po_id') else []))
    if not po_ids:
        po_ids = [p for p in {i.get('po_id') for i in items} if p]
    pos = await db.production_pos.find({'id': {'$in': po_ids}}, {'_id': 0}).to_list(None) if po_ids else []
    po_map = {p['id']: p for p in pos}
    breakdown: dict = {}
    for it in items:
        pid = it.get('po_id')
        if not pid:
            poi = await db.po_items.find_one({'id': it.get('po_item_id')}, {'_id': 0, 'po_id': 1}) \
                if it.get('po_item_id') else None
            pid = (poi or {}).get('po_id')
        if not pid:
            continue
        b = breakdown.setdefault(pid, {
            'po_id': pid,
            'po_number': (po_map.get(pid) or {}).get('po_number', ''),
            'customer_name': (po_map.get(pid) or {}).get('customer_name', ''),
            'business_type': (po_map.get(pid) or {}).get('business_type', ''),
            'qty_shipped': 0, 'qty_received': 0, 'line_count': 0})
        b['qty_shipped'] += int(it.get('qty_shipped') or 0)
        b['qty_received'] += int(it['qty_received'] if it.get('qty_received') is not None
                                 else it.get('qty_shipped') or 0)
        b['line_count'] += 1
    result['po_breakdown'] = list(breakdown.values())
    result['po_ids'] = po_ids
    result['is_consolidated'] = bool(s.get('consolidated')) or len(breakdown) > 1

    children = await db.buyer_shipments.find(
        {'$or': [{'parent_shipment_id': bsid}, {'id': {'$in': list(s.get('child_shipment_ids') or [])}}]},
        {'_id': 0}).to_list(None)
    child_out = []
    for c in children:
        citems = await db.buyer_shipment_items.find({'shipment_id': c['id']}, {'_id': 0}).to_list(None)
        child_out.append({**serialize_doc(c),
                          'items': serialize_doc(citems),
                          'total_shipped': sum(int(x.get('qty_shipped') or 0) for x in citems),
                          'total_received': sum(int(x['qty_received'] if x.get('qty_received') is not None
                                                   else x.get('qty_shipped') or 0) for x in citems)})
    result['child_shipments'] = child_out
    result['child_shipment_count'] = len(child_out)

    if s.get('parent_shipment_id'):
        parent = await db.buyer_shipments.find_one({'id': s['parent_shipment_id']}, {'_id': 0})
        result['parent_shipment'] = serialize_doc(parent) if parent else None

    src_ids = list(s.get('source_receipt_ids') or [])
    if src_ids:
        srcs = await db.cmt_receipts.find({'id': {'$in': src_ids}}, {'_id': 0}).to_list(None)
        from core.cmt_receipt_status import with_canon_status as _wcs
        result['source_receipts'] = [serialize_doc(_wcs(x)) for x in srcs]
    else:
        result['source_receipts'] = []
    return result

@router.post("/buyer-shipments")
async def create_buyer_shipment(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()

    # ─── PHASE B — Role gate & receiver_type resolution ────────────────────
    from core.cmt_override import resolve_override, stamp as ov_stamp, effective_vendor_id
    _ov = await resolve_override(request, user, db)
    receiver_type = _resolve_receiver_type(body, user, _ov)
    items_data = body.get('items', [])

    # ─── PHASE D — resolve PO(s) from items (consolidated multi-PO buyer SJ) ──
    # A DA→buyer surat jalan may carry items from MULTIPLE POs of the SAME buyer.
    # Resolve per-item PO; assert single buyer. For CMT→DA declarations this stays
    # single-PO (vendors declare against one PO / job).
    po_res = await _resolve_pos_for_items(db, items_data, body.get('po_id'), receiver_type)
    po = po_res['primary_po']                 # single PO (or None when consolidated)
    po_ids = po_res['po_ids']
    # PO INTERNAL tidak lewat CMT ⇒ tidak ada cmt_receipts; sumber kirimnya adalah
    # hasil produksi job internal (pagar C-1 di bawah) + stok FG gudang.
    internal_dispatch = bool(po_ids) and all(
        (po_res['po_by_id'].get(p) or {}).get('business_type') == 'internal' for p in po_ids)
    # ──────────────────────────────────────────────────────────────────────

    source_receipt_ids = []
    if receiver_type == RECEIVER_BUYER and not is_vendor(user):
        # DA + dispatch to buyer wajib source_receipt_ids[]. Validate + cap qty.
        source_receipt_ids = body.get('source_receipt_ids') or []
        if not isinstance(source_receipt_ids, list):
            raise HTTPException(400, 'source_receipt_ids harus array of string')
        # Phase B: enforce presence of source_receipt_ids EARLY (before the
        # generic M-1 "minimal 1 pcs" qty guard) so DA dispatch attempts without
        # source receipts always surface the correct, actionable error message
        # (GUIDELINE §12.2 scenario 4c) regardless of whether items[] is empty.
        if not source_receipt_ids and not internal_dispatch:
            raise HTTPException(
                400,
                'Buyer shipment dari DA wajib source_receipt_ids[] (mengacu ke '
                'cmt_receipts status Approved). Phase B enforcement.'
            )
        # Full existence/status/qty-cap validation runs post items_data extraction.
    # ── END Phase B pre-flight ────────────────────────────────────────────

    vendor_id = await effective_vendor_id(request, user, db, body.get('vendor_id'))
    vendor_doc = await resolve_vendor_doc(db, vendor_id) if vendor_id else None

    # ═══════════════════════════════════════════════════════════════════════
    # FASE E (2026-08-15) — SEMUA PAGAR DIJALANKAN **SEBELUM** DOKUMEN DITULIS
    # ═══════════════════════════════════════════════════════════════════════
    # BUG NYATA yang ditutup di sini (terlihat di layar pemilik): blok validasi
    # ini DULU berjalan SESUDAH `db.buyer_shipments.insert_one(master_shipment)`.
    # Akibatnya setiap percobaan simpan yang DITOLAK (mis. "qty melebihi sisa")
    # tetap meninggalkan SURAT JALAN YATIM: header ada, item 0, progres 0/0 pcs,
    # status Pending. Nomor surat jalan pun ikut terpakai (counter naik).
    # Itulah sebabnya daftar pengiriman berisi baris "0 / 0 pcs" yang tidak bisa
    # dijelaskan siapa pun — dan pemakai menyangka pengirimannya "sudah pernah
    # dilakukan". Sekarang: gagal validasi ⇒ TIDAK ADA dokumen tertulis.
    #
    # Pagar ini hanya butuh `items_data`, `source_receipt_ids`, dan `receiver_type`
    # — tidak satu pun butuh `shipment_id` — jadi memindahkannya ke atas aman.
    # ═══════════════════════════════════════════════════════════════════════
    # LANJUTAN DISPATCH pada surat jalan yang SAMA (keluhan pemilik 2026-06)
    # ═══════════════════════════════════════════════════════════════════════
    # CACAT NYATA: penyambungan dispatch hanya bisa lewat `job_id` (jalur
    # deklarasi vendor). Untuk dispatch DA → buyer, setiap penyimpanan selalu
    # membuat surat jalan BARU dengan nomor baru dan `dispatch_seq` kembali ke 1.
    # Akibatnya pengiriman bertahap (partial) tidak pernah bisa mencapai 100%
    # pada satu surat jalan: yang muncul adalah beberapa surat jalan terpisah
    # untuk PO yang sama. Dibuktikan `scripts/_repro_5bug_produksi_maklon.py`
    # (BUG 2). Sekarang layar boleh mengirim `shipment_id` (tombol "+ Dispatch")
    # dan kiriman itu ditambahkan sebagai `dispatch_seq` berikutnya — nomor surat
    # jalan TIDAK berubah. Pagar kapasitas tidak dilonggarkan sedikit pun: batas
    # "sisa bisa kirim" dihitung per po_item melintasi SEMUA surat jalan.
    #
    # Diperiksa SEBELUM pagar qty/kapasitas di bawah supaya `shipment_id` yang
    # salah menjawab "surat jalan tidak ditemukan" (404) — bukan pesan qty yang
    # menyesatkan pemakai ke arah yang keliru.
    cont_id = (body.get('shipment_id') or '').strip()
    master_shipment = None
    if cont_id:
        master_shipment = await db.buyer_shipments.find_one({'id': cont_id})
        if not master_shipment:
            raise HTTPException(404, f'Surat jalan {cont_id} tidak ditemukan — '
                                     'lanjutan dispatch dibatalkan')
        _cur_rt = master_shipment.get('receiver_type') or RECEIVER_BUYER
        if _cur_rt != receiver_type:
            raise HTTPException(
                400, f"Surat jalan {master_shipment.get('shipment_number')} bertipe "
                     f"penerima '{_cur_rt}', tidak bisa dilanjutkan sebagai "
                     f"'{receiver_type}'.")
        if is_vendor(user) and master_shipment.get('vendor_id') != vendor_id:
            raise HTTPException(403, 'Surat jalan ini bukan milik vendor Anda')

    # ─── VALIDATION GUARDRAILS (Phase A — C-1 & M-1) ──────────────────────
    # Reject 0-qty dispatches (M-1): require at least one item with qty_shipped > 0
    total_qty_in_request = sum(int(i.get('qty_shipped', 0) or 0) for i in items_data)
    if total_qty_in_request <= 0:
        raise HTTPException(400, 'Dispatch harus memiliki minimal 1 pcs barang dikirim')

    # ─── PHASE B — source_receipt_ids cap (DA → buyer) ────────────────────
    if receiver_type == RECEIVER_BUYER and not is_vendor(user) and (source_receipt_ids or not internal_dispatch):
        # Validate source_receipt_ids exist, are Approved, and cap qty per SKU.
        await _validate_source_receipts_cap(db, source_receipt_ids, items_data, user)
    # ──────────────────────────────────────────────────────────────────────

    # ─── GAP E pre-flight — stok FG harus CUKUP sebelum dokumen ditulis ────
    fg_warnings = []
    if receiver_type == RECEIVER_BUYER:
        fg_warnings = await _fg_precheck_for_dispatch(db, items_data)
    # ──────────────────────────────────────────────────────────────────────

    # Cap qty_shipped against total produced (C-1): supports overproduction,
    # blocks phantom/ghost shipments. Cumulative across all dispatches.
    # Phase B: SKIPPED when receiver_type='da' (CMT declaration is upstream of
    # any DA receipt — DA will verify actual qty at cmt_receipts inspection).
    # Phase B fix: when computing "already received", EXCLUDE receiver_type='da'
    # rows (those are CMT→DA declarations, NOT buyer receipts) so DA dispatch
    # capacity is not double-counted.
    if receiver_type == RECEIVER_BUYER:
        for item in items_data:
            po_item_id = item.get('po_item_id')
            qty_req = int(item.get('qty_shipped', 0) or 0)
            if qty_req < 0:
                raise HTTPException(400, f'qty_shipped tidak boleh negatif')
            if po_item_id and qty_req > 0:
                # Sum all produced for this po_item (all jobs + child jobs)
                all_job_items = await db.production_job_items.find({'po_item_id': po_item_id}).to_list(None)
                total_produced = sum(int(ji.get('produced_qty', 0) or 0) for ji in all_job_items)
                # Cap based on ACTUAL RECEIVED (effective: qty_received when set, else qty_shipped)
                # so shortfalls (shipped > received) re-open capacity to re-ship the difference.
                # Phase B: only count shipments to BUYER (receiver_type='buyer' or legacy null).
                bs_ids = await db.buyer_shipments.distinct(
                    'id',
                    {'$or': [
                        {'receiver_type': RECEIVER_BUYER},
                        {'receiver_type': {'$exists': False}},
                        {'receiver_type': None},
                    ]}
                )
                all_bs_items = await db.buyer_shipment_items.find(
                    {'po_item_id': po_item_id, 'shipment_id': {'$in': bs_ids}}
                ).to_list(None)
                total_already_received = sum(
                    (int(bi['qty_received']) if bi.get('qty_received') is not None else int(bi.get('qty_shipped', 0) or 0))
                    for bi in all_bs_items)

                # Phase B relaxation: if source_receipt_ids present, use Σqty_actual
                # (from those receipts) as the "produced capacity" instead of the raw
                # job_items produced_qty — because the FG has been formally handed over
                # from CMT to DA and the receipts are the SSOT of what DA can dispatch.
                if source_receipt_ids:
                    _receipt_lines = await db.cmt_receipt_lines.find(
                        {'receipt_id': {'$in': list(source_receipt_ids)},
                         'po_item_id': po_item_id}
                    ).to_list(None)
                    receipt_cap = sum(int(ln.get('qty_actual', 0) or 0) for ln in _receipt_lines)
                    # Take the LARGER (more permissive) of produced_qty vs receipt_cap;
                    # receipt validation function already enforces the per-SKU tighter cap.
                    total_produced = max(total_produced, receipt_cap)

                if total_already_received + qty_req > total_produced:
                    sku = (await db.po_items.find_one({'id': po_item_id}) or {}).get('sku', '')
                    raise HTTPException(400,
                        f'Qty kirim ke buyer untuk {sku} ({total_already_received + qty_req}) melebihi qty diproduksi/diterima dari CMT ({total_produced}). '
                        f'Maksimal kirim: {max(0, total_produced - total_already_received)} pcs.')
    else:
        # receiver_type='da': only sanity check negative values.
        for item in items_data:
            if int(item.get('qty_shipped', 0) or 0) < 0:
                raise HTTPException(400, 'qty_shipped tidak boleh negatif')


    job_id = body.get('job_id')
    if master_shipment is None and job_id:
        master_shipment = await db.buyer_shipments.find_one({'job_id': job_id, 'vendor_id': vendor_id})
    is_new = not master_shipment
    if is_new:
        shipment_id = new_id()
        # Phase D: auto-generate a CONFIGURABLE document number (unless the client
        # sent an explicit one). Falls back to the legacy prefix on any error.
        _doc_type = 'buyer_shipment_da' if receiver_type == RECEIVER_DA else 'buyer_shipment_buyer'
        shipment_number = (body.get('shipment_number') or '').strip()
        if not shipment_number:
            try:
                from utils.doc_numbering import gen_document_number
                shipment_number = await gen_document_number(
                    db, _doc_type,
                    context={'po_number': (po or {}).get('po_number', ''),
                             'buyer': po_res['customer_name']})
            except Exception:
                import logging as _lg
                _lg.getLogger(__name__).exception('Phase D: gen_document_number gagal; fallback prefix legacy')
                _prefix = 'SJ-CMT-DA' if receiver_type == RECEIVER_DA else 'SJ-BYR'
                shipment_number = f"{_prefix}-{(po or {}).get('po_number', '') or int(now_wib().timestamp())}"
        master_shipment = {
            'id': shipment_id,
            'shipment_number': shipment_number,
            'vendor_id': vendor_id, 'vendor_name': (vendor_doc or {}).get('garment_name', user['name']),
            'po_id': po_res['primary_po_id'], 'po_number': (po or {}).get('po_number', body.get('po_number', '')),
            'po_ids': po_ids,   # Phase D: all POs represented (consolidated SJ)
            'customer_name': po_res['customer_name'] or (po or {}).get('customer_name', body.get('customer_name', '')),
            'job_id': job_id, 'ship_status': 'Pending',
            'business_type': po_res['business_type'],
            # ─── PHASE B fields ────────────────────────────────────────────
            'receiver_type': receiver_type,
            'source_receipt_ids': source_receipt_ids,
            'related_cmt_receipt_id': None,   # filled below if receiver_type='da'
            'created_by_da': (receiver_type == RECEIVER_BUYER),
            'consolidated': len(po_ids) > 1,  # Phase D flag
            # ────────────────────────────────────────────────────────────────
            'notes': body.get('notes', ''),
            'created_by': user['name'], 'created_at': now(), 'updated_at': now(),
            # keputusan 3a — jejak "diinput staf DA" pada deklarasi kirim CMT→DA
            **ov_stamp(_ov),
        }
        await db.buyer_shipments.insert_one(master_shipment)
    else:
        shipment_id = master_shipment['id']
        # Lanjutan dispatch: sumber penerimaan & PO yang baru ikut dicatat di
        # header supaya jejak "surat jalan ini berasal dari penerimaan apa" utuh.
        if source_receipt_ids:
            await db.buyer_shipments.update_one(
                {'id': shipment_id},
                {'$addToSet': {'source_receipt_ids': {'$each': list(source_receipt_ids)}}})
        _new_pos = [p for p in po_ids
                    if p and p not in (master_shipment.get('po_ids') or [])]
        if _new_pos:
            await db.buyer_shipments.update_one(
                {'id': shipment_id},
                {'$addToSet': {'po_ids': {'$each': _new_pos}},
                 '$set': {'consolidated': len((master_shipment.get('po_ids') or [])) + len(_new_pos) > 1}})
    existing_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
    max_dispatch = max((i.get('dispatch_seq', 1) for i in existing_items), default=0)
    dispatch_seq = max_dispatch + 1
    dispatch_date = parse_date(body.get('shipment_date')) or now()

    inserted_items = []
    for item in items_data:
        po_item = await db.po_items.find_one({'id': item.get('po_item_id')}) if item.get('po_item_id') else None
        # Phase D: denormalize the origin PO onto each line so fulfillment/auto-close
        # can be computed per-PO even inside a consolidated multi-PO surat jalan.
        _it_po_id = po_res['poitem_to_po'].get(item.get('po_item_id')) or po_res['primary_po_id'] or body.get('po_id')
        _it_po_number = (po_res['po_by_id'].get(_it_po_id) or {}).get('po_number', '') if _it_po_id else ''
        _job_item_id = item.get('job_item_id')
        _job_id_line = item.get('job_id') or job_id
        if not _job_item_id and item.get('po_item_id'):
            # Layar mengirim baris berbasis po_item; isi job_item_id supaya agregasi
            # "dikirim/diterima" per job (production_execution) tetap terisi (iterasi 103).
            _jis = await db.production_job_items.find(
                {'po_item_id': item['po_item_id']}, {'_id': 0, 'id': 1, 'job_id': 1, 'produced_qty': 1}
            ).sort('created_at', 1).to_list(None)
            if _jis:
                _best = max(_jis, key=lambda j: int(j.get('produced_qty') or 0))
                _job_item_id = _best['id']
                _job_id_line = _job_id_line or _best.get('job_id')
        si = {
            'id': new_id(), 'shipment_id': shipment_id,
            'dispatch_seq': dispatch_seq, 'dispatch_date': dispatch_date,
            'po_id': _it_po_id, 'po_number': _it_po_number,   # Phase D denormalization
            'po_item_id': item.get('po_item_id'), 'job_item_id': _job_item_id,
            'job_id': _job_id_line,
            'product_name': (po_item or {}).get('product_name', item.get('product_name', '')),
            'serial_number': (po_item or {}).get('serial_number', item.get('serial_number', '')),
            'size': (po_item or {}).get('size', item.get('size', '')),
            'color': (po_item or {}).get('color', item.get('color', '')),
            'sku': (po_item or {}).get('sku', item.get('sku', '')),
            # Phase D: consolidated create payloads omit ordered_qty per line, so
            # fall back to the origin po_item's ordered qty. Keeps Total Order /
            # progress % correct for multi-PO surat jalan (single-PO path unchanged
            # because it already sends ordered_qty explicitly).
            'ordered_qty': int(item.get('ordered_qty', 0) or 0) or int((po_item or {}).get('qty', 0) or 0),
            'qty_shipped': int(item.get('qty_shipped', 0) or 0), 'created_at': now()
        }
        await db.buyer_shipment_items.insert_one(si)
        inserted_items.append(si)
    all_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
    any_shipped = any(i.get('qty_shipped', 0) > 0 for i in all_items)
    ship_status = 'Partially Shipped' if any_shipped else 'Pending'
    await db.buyer_shipments.update_one({'id': shipment_id}, {'$set': {
        'ship_status': ship_status, 'last_dispatch': dispatch_date,
        'last_dispatch_seq': dispatch_seq, 'updated_at': now()
    }})

    # ─── GAP E — STOK FG KELUAR (dispatch riil ke buyer) ──────────────────
    # + GAP G — pengiriman ulang MENUTUP catatan selisih buyer yang masih open.
    fg_result = None
    buyer_short_closed = None
    if receiver_type == RECEIVER_BUYER:
        fg_result = await _issue_fg_for_dispatch(db, master_shipment, inserted_items, user)
        if fg_warnings:
            fg_result['warnings'] = list(fg_warnings) + list(fg_result.get('warnings') or [])
        if fg_result.get('warnings'):
            await db.buyer_shipments.update_one(
                {'id': shipment_id}, {'$set': {'fg_stock_warning': fg_result['warnings'][:5]}})
        try:
            from core import short_shipment as shortmod
            closed = {'resolved': 0, 'shorts': []}
            for it in inserted_items:
                if not it.get('po_item_id'):
                    continue
                r = await shortmod.resolve_buyer_shorts_on_dispatch(
                    db, po_item_id=it['po_item_id'], qty=int(it.get('qty_shipped') or 0),
                    shipment=master_shipment, actor=user)
                closed['resolved'] += r.get('resolved', 0)
                closed['shorts'].extend(r.get('shorts') or [])
            buyer_short_closed = closed if closed['resolved'] else None
        except Exception:
            import logging as _lg
            _lg.getLogger(__name__).exception('penutupan selisih buyer gagal (SJ %s)', shipment_id)
    # ──────────────────────────────────────────────────────────────────────

    # ─── PHASE B — Auto-create cmt_receipts Draft for CMT declarations ────
    # When a vendor CMT creates a shipment with receiver_type='da', we create a
    # matching cmt_receipts (Draft) so DA admin can inspect + fill qty_actual.
    # SETIAP dispatch (termasuk kirim ULANG selisih) mendapat penerimaannya sendiri.
    if receiver_type == RECEIVER_DA:
        _receipt_id = await _auto_create_cmt_receipt_from_shipment(
            db, master_shipment, inserted_items, user, dispatch_seq=dispatch_seq)
        if _receipt_id:
            _set = {'related_cmt_receipt_id': _receipt_id}
            await db.buyer_shipments.update_one(
                {'id': shipment_id},
                {'$set': _set, '$addToSet': {'related_cmt_receipt_ids': _receipt_id}})
            master_shipment['related_cmt_receipt_id'] = _receipt_id
    # ──────────────────────────────────────────────────────────────────────

    # ── Fase 3 (FIN-1): COGS saat fulfillment PO internal (per dispatch, idempoten) ──
    # Phase B: COGS hanya untuk receiver_type='buyer' (dispatch riil ke buyer).
    # Phase D: business_type diambil dari resolusi PO (master_shipment). COGS berbasis
    # job/HPP (grouping-agnostic) sehingga satu SJ konsolidasi lintas-PO internal tetap
    # posting 1 JE yang benar (Σ HPP semua job). Maklon di-skip (COGS bukan di dispatch).
    cogs_result = None
    _bt = master_shipment.get('business_type') or (po or {}).get('business_type') or 'internal'
    if _bt == 'internal' and receiver_type == RECEIVER_BUYER:
        try:
            from routes.rahaza_posting import post_cogs_on_buyer_dispatch
            cogs_result = await post_cogs_on_buyer_dispatch(db, master_shipment, inserted_items, dispatch_seq, user)
        except Exception:
            import logging; logging.getLogger(__name__).exception('COGS posting gagal utk dispatch %s seq %s', shipment_id, dispatch_seq)
    _label = 'CMT Declaration to DA' if receiver_type == RECEIVER_DA else 'Buyer Shipment'
    await log_activity(user['id'], user['name'], 'Create' if is_new else 'Add Dispatch', _label, f"{_label} - {ship_status}")
    result = serialize_doc(master_shipment)
    result.update({'ship_status': ship_status, 'dispatch_seq': dispatch_seq, 'is_new': is_new, 'items': serialize_doc(inserted_items)})
    if cogs_result is not None:
        result['cogs_posting'] = serialize_doc(cogs_result)
    if fg_result is not None:
        result['fg_stock'] = serialize_doc(fg_result)
    if buyer_short_closed:
        result['buyer_short_closed'] = serialize_doc(buyer_short_closed)
    return JSONResponse(result, status_code=201 if is_new else 200)

@router.put("/buyer-shipments/{bsid}")
async def update_buyer_shipment(bsid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    body.pop('_id', None); body.pop('id', None); body.pop('items', None)
    # DA BUG-FIX: ship_status dikelola otomatis oleh engine dispatch
    # (Pending/Partially Shipped/Shipped dari agregasi item) — tolak set manual.
    if 'ship_status' in body:
        raise HTTPException(400, 'ship_status dikelola otomatis oleh engine dispatch — tidak bisa diubah manual')
    await db.buyer_shipments.update_one({'id': bsid}, {'$set': {**body, 'updated_at': now()}})
    return serialize_doc(await db.buyer_shipments.find_one({'id': bsid}, {'_id': 0}))

@router.delete("/buyer-shipments/{bsid}")
async def delete_buyer_shipment(bsid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.buyer_shipments.find_one({'id': bsid})
    if not doc: raise HTTPException(404, 'Not found')
    # GAP E — pembatalan surat jalan harus MEMBALIK mutasi stok FG, kalau tidak
    # barang "hilang" dari gudang padahal dokumennya sudah tidak ada.
    items = await db.buyer_shipment_items.find({'shipment_id': bsid}, {'_id': 0}).to_list(None)
    reverted = 0
    from core import production_qty_ledger as qled
    for it in items:
        qty = int(it.get('fg_issued_qty') or 0)
        if qty <= 0 or not it.get('fg_issued_at'):
            continue
        mat = await qled.resolve_fg_material(
            db, material_id=it.get('fg_material_id', ''), sku=it.get('sku', ''))
        if not mat:
            continue
        try:
            posted = await qled.post_fg_accepted(
                db, material_id=mat['id'], qty=qty,
                ref={'source': 'buyer_shipment_cancel', 'shipment_id': bsid,
                     'shipment_number': doc.get('shipment_number'),
                     'shipment_item_id': it.get('id')},
                actor=user, meta={'material_code': mat.get('code', ''), 'unit': 'pcs',
                                  'type': 'finished_goods'})
            await db.rahaza_fg_movements.insert_one({
                'id': new_id(), 'sku_code': it.get('sku', ''), 'movement_type': 'IN',
                'qty': qty, 'source': 'buyer_shipment_cancel', 'ref_id': bsid,
                'ref_number': doc.get('shipment_number'), 'material_id': mat['id'],
                'location_id': posted['location_id'],
                'notes': f"Surat jalan {doc.get('shipment_number')} dihapus — stok FG dikembalikan",
                'created_by': user['name'], 'created_at': now()})
            reverted += qty
        except Exception:
            import logging as _lg
            _lg.getLogger(__name__).exception('pembalikan stok FG gagal (item %s)', it.get('id'))
    await db.buyer_short_records.update_many(
        {'shipment_id': bsid, 'status': 'open'},
        {'$set': {'status': 'cancelled', 'resolution': 'dibatalkan',
                  'resolution_notes': 'surat jalan dihapus', 'updated_at': now()}})
    await db.buyer_shipment_items.delete_many({'shipment_id': bsid})
    await db.buyer_shipments.delete_one({'id': bsid})
    return {'success': True, 'fg_stock_reverted': reverted}

@router.put("/buyer-shipment-items/{item_id}")
async def force_edit_buyer_shipment_item(item_id: str, request: Request):
    """Force edit qty_shipped of a single buyer shipment item (Admin/Superadmin).
    Full override (no produced cap) per user decision; reason is mandatory and an
    audit trail (edit_history + activity log) is recorded. All progress figures
    (vendor portal remaining_to_ship, PO remaining, shipment progress) are computed
    on-the-fly from qty_shipped, so this edit propagates automatically everywhere.
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, 'Hanya Admin/Superadmin yang dapat melakukan force edit')
    db = get_db()
    body = await request.json()
    reason = (body.get('reason') or '').strip()
    if not reason:
        raise HTTPException(400, 'Alasan koreksi wajib diisi')
    if 'qty_shipped' not in body:
        raise HTTPException(400, 'qty_shipped wajib diisi')
    try:
        new_qty = int(body.get('qty_shipped'))
    except (TypeError, ValueError):
        raise HTTPException(400, 'qty_shipped harus berupa angka')
    if new_qty < 0:
        raise HTTPException(400, 'qty_shipped tidak boleh negatif')

    item = await db.buyer_shipment_items.find_one({'id': item_id})
    if not item:
        raise HTTPException(404, 'Item pengiriman tidak ditemukan')
    old_qty = int(item.get('qty_shipped', 0) or 0)

    # Full override: no cap enforced. Compute an informational warning if the new
    # cumulative shipped for this po_item exceeds total produced.
    warning = None
    po_item_id = item.get('po_item_id')
    if po_item_id:
        all_job_items = await db.production_job_items.find({'po_item_id': po_item_id}).to_list(None)
        total_produced = sum(int(ji.get('produced_qty', 0) or 0) for ji in all_job_items)
        all_bs_items = await db.buyer_shipment_items.find({'po_item_id': po_item_id}).to_list(None)
        total_shipped_others = sum(int(bi.get('qty_shipped', 0) or 0) for bi in all_bs_items if bi.get('id') != item_id)
        if total_shipped_others + new_qty > total_produced:
            warning = (f'Total kirim untuk item ini ({total_shipped_others + new_qty} pcs) '
                       f'melebihi qty diproduksi ({total_produced} pcs).')

    edit_entry = {
        'old_qty': old_qty, 'new_qty': new_qty, 'reason': reason,
        'edited_by': user['name'], 'edited_by_id': user['id'], 'edited_at': now()
    }
    await db.buyer_shipment_items.update_one(
        {'id': item_id},
        {'$set': {'qty_shipped': new_qty, 'edited_by': user['name'], 'edited_at': now(), 'updated_at': now()},
         '$push': {'edit_history': edit_entry}}
    )

    # ─── GAP E — mutasi stok FG harus MENGIKUTI koreksi qty dikirim ───────
    # Kalau tidak, force-edit membuat stok FG bercabang dari dokumen (bug yang
    # sama dengan dispatch tanpa mutasi stok).
    shipment = await db.buyer_shipments.find_one({'id': item.get('shipment_id')}, {'_id': 0}) or {}
    stock_adjust = None
    if (shipment.get('receiver_type') or RECEIVER_BUYER) == RECEIVER_BUYER:
        delta = new_qty - old_qty
        issued = int(item.get('fg_issued_qty') or 0)
        if delta != 0 and (issued or item.get('fg_issued_at')):
            from core import production_qty_ledger as qled
            mat = await qled.resolve_fg_material(
                db, material_id=item.get('fg_material_id', ''), sku=item.get('sku', ''))
            if mat:
                ref = {'source': 'buyer_shipment_force_edit', 'shipment_id': shipment.get('id'),
                       'shipment_number': shipment.get('shipment_number'),
                       'shipment_item_id': item_id, 'reason': reason}
                try:
                    if delta > 0:
                        await qled.issue_fg(db, material_id=mat['id'], qty=delta,
                                            sku=item.get('sku', ''), ref=ref, actor=user)
                        mv = 'OUT'
                    else:
                        await qled.post_fg_accepted(
                            db, material_id=mat['id'], qty=-delta, ref=ref, actor=user,
                            meta={'material_code': mat.get('code', ''), 'unit': 'pcs',
                                  'type': 'finished_goods'})
                        mv = 'IN'
                    await db.rahaza_fg_movements.insert_one({
                        'id': new_id(), 'sku_code': item.get('sku', ''), 'movement_type': mv,
                        'qty': abs(delta), 'source': 'buyer_shipment_force_edit',
                        'ref_id': shipment.get('id'), 'ref_number': shipment.get('shipment_number'),
                        'material_id': mat['id'], 'shipment_item_id': item_id,
                        'notes': f"Koreksi qty dikirim {old_qty} → {new_qty} pcs. Alasan: {reason}",
                        'created_by': user['name'], 'created_at': now()})
                    await db.buyer_shipment_items.update_one(
                        {'id': item_id}, {'$set': {'fg_issued_qty': max(0, issued + delta)}})
                    stock_adjust = {'delta': delta, 'movement': mv}
                except qled.FGStockShortfall as e:
                    warning = (warning + ' ' if warning else '') + str(e)
                except Exception as e:  # noqa: BLE001
                    import logging as _lg
                    _lg.getLogger(__name__).exception('koreksi stok FG force-edit gagal')
                    warning = (warning + ' ' if warning else '') + f'Stok FG gagal dikoreksi: {e}'
    # ──────────────────────────────────────────────────────────────────────

    # Recompute ship_status for the parent (master) shipment
    shipment_id = item.get('shipment_id')
    if shipment_id:
        all_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(None)
        any_shipped = any(int(i.get('qty_shipped', 0) or 0) > 0 for i in all_items)
        await db.buyer_shipments.update_one({'id': shipment_id}, {'$set': {
            'ship_status': 'Partially Shipped' if any_shipped else 'Pending', 'updated_at': now()
        }})

    await log_activity(user['id'], user['name'], 'Force Edit', 'Buyer Shipment',
        f"Koreksi qty {item.get('sku', '')} (SN {item.get('serial_number', '-')}) "
        f"{old_qty} → {new_qty} pcs. Alasan: {reason}")

    updated = await db.buyer_shipment_items.find_one({'id': item_id}, {'_id': 0})
    return {'success': True, 'item': serialize_doc(updated),
            'old_qty': old_qty, 'new_qty': new_qty, 'warning': warning,
            'stock_adjust': stock_adjust}

@router.put("/buyer-shipment-items/{item_id}/received")
async def set_buyer_shipment_item_received(item_id: str, request: Request):
    """Record the ACTUAL received quantity by the buyer for a single item
    (Admin/Superadmin). qty_shipped (what the vendor sent) is left untouched.
    When qty_received is never set, downstream logic treats it as == qty_shipped.
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, 'Hanya Admin/Superadmin yang dapat mengisi qty diterima')
    db = get_db()
    body = await request.json()
    if 'qty_received' not in body:
        raise HTTPException(400, 'qty_received wajib diisi')
    try:
        new_recv = int(body.get('qty_received'))
    except (TypeError, ValueError):
        raise HTTPException(400, 'qty_received harus berupa angka')
    if new_recv < 0:
        raise HTTPException(400, 'qty_received tidak boleh negatif')
    reason = (body.get('reason') or '').strip()

    item = await db.buyer_shipment_items.find_one({'id': item_id})
    if not item:
        raise HTTPException(404, 'Item pengiriman tidak ditemukan')
    qty_shipped = int(item.get('qty_shipped', 0) or 0)
    old_recv = item.get('qty_received')
    old_recv = int(old_recv) if old_recv is not None else qty_shipped

    entry = {'old_qty': old_recv, 'new_qty': new_recv, 'reason': reason,
             'edited_by': user['name'], 'edited_by_id': user['id'], 'edited_at': now()}
    await db.buyer_shipment_items.update_one({'id': item_id},
        {'$set': {'qty_received': new_recv, 'received_by': user['name'], 'received_at': now(), 'updated_at': now()},
         '$push': {'received_history': entry}})

    # ─── GAP G — SELISIH TERIMA BUYER PUNYA IDENTITAS + TINDAK LANJUT ─────
    # Aturan owner: perlakuannya SAMA dengan selisih CMT→DA (bisa ketinggalan /
    # salah hitung) ⇒ dokumen SJ dikoreksi ke qty yang benar-benar diterima,
    # selisihnya menjadi dokumen `SEL-BYR-…` status open (bisa dikirim ulang),
    # barangnya dikembalikan ke stok FG, dan Admin/Finance dapat notifikasi.
    # Keputusan tanggungan (CMT / DA) diambil saat PO ditutup — bukan otomatis.
    buyer_short = None
    if new_recv < qty_shipped:
        try:
            from core import short_shipment as shortmod
            ship = await db.buyer_shipments.find_one({'id': item.get('shipment_id')}, {'_id': 0}) or {}
            if (ship.get('receiver_type') or RECEIVER_BUYER) == RECEIVER_BUYER:
                buyer_short = await shortmod.record_buyer_short(
                    db, shipment=ship, item=item, qty_shipped=qty_shipped,
                    qty_received=new_recv, actor=user, reason=reason)
        except Exception:
            import logging as _lg
            _lg.getLogger(__name__).exception('pencatatan selisih buyer gagal (item %s)', item_id)
    # ──────────────────────────────────────────────────────────────────────

    await log_activity(user['id'], user['name'], 'Set Qty Diterima', 'Buyer Shipment',
        f"Qty diterima {item.get('sku', '')} (SN {item.get('serial_number', '-')}) "
        f"{old_recv} → {new_recv} pcs (dikirim {qty_shipped})." + (f" Alasan: {reason}" if reason else ''))

    updated = await db.buyer_shipment_items.find_one({'id': item_id}, {'_id': 0})

    # ─── Phase C §11.2 / Phase D — auto-close PO on full buyer fulfillment ────
    # Resolve the PO from the ITEM (Phase D: a consolidated SJ spans multiple POs,
    # so the shipment header po_id may be null / a different PO). Fallbacks keep
    # legacy single-PO shipments working.
    auto_close = None
    try:
        _po_id = item.get('po_id')
        if not _po_id and item.get('po_item_id'):
            _poi = await db.po_items.find_one({'id': item['po_item_id']}, {'_id': 0, 'po_id': 1})
            _po_id = (_poi or {}).get('po_id')
        if not _po_id:
            ship = await db.buyer_shipments.find_one({'id': item.get('shipment_id')}, {'_id': 0, 'po_id': 1})
            _po_id = (ship or {}).get('po_id')
        if _po_id:
            from routes.production_maklon_bridge import try_auto_close_po_on_full
            auto_close = await try_auto_close_po_on_full(db, _po_id, user)
    except Exception:
        auto_close = None
    # ──────────────────────────────────────────────────────────────────────

    return {'success': True, 'item': serialize_doc(updated), 'qty_shipped': qty_shipped,
            'qty_received': new_recv, 'variance': qty_shipped - new_recv,
            'buyer_short': serialize_doc(buyer_short) if buyer_short else None,
            'po_auto_close': auto_close}

@router.get("/buyer-receipt-variance")
async def buyer_receipt_variance(request: Request):
    """Per-PO report of Shipped vs Received (actual) vs Variance, with per-item drill-down.
    Effective received = qty_received when set, else qty_shipped (assume fully received).
    Optional ?po_id= filter (also used by invoice creation to prefill qty from received).
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    req_po_id = sp.get('po_id')
    # Phase D: a consolidated surat jalan may span multiple POs (header po_id null),
    # so select shipments whose header OR any item references the PO.
    if req_po_id:
        _ids = set(await db.buyer_shipments.distinct('id', {'po_id': req_po_id}))
        _ids |= set(await db.buyer_shipment_items.distinct('shipment_id', {'po_id': req_po_id}))
        bs_q = {'id': {'$in': list(_ids)}}
    else:
        bs_q = {}
    from core.cmt_override import apply_scope as _ov_scope2
    await _ov_scope2(request, user, db, bs_q, param_vendor_id=sp.get('vendor_id'))
    shipments = await db.buyer_shipments.find(bs_q, {'_id': 0}).to_list(None)
    ship_map = {s['id']: s for s in shipments}
    ship_ids = list(ship_map.keys())
    if not ship_ids:
        return []
    items = await db.buyer_shipment_items.find({'shipment_id': {'$in': ship_ids}}, {'_id': 0}).to_list(None)
    # Phase D: resolve per-PO metadata (po_number/customer) since a consolidated SJ
    # groups by the ITEM's PO, not the header.
    _po_ids = [p for p in {(it.get('po_id') or ship_map.get(it.get('shipment_id'), {}).get('po_id')) for it in items} if p]
    _po_meta = {}
    if _po_ids:
        async for p in db.production_pos.find(
                {'id': {'$in': _po_ids}}, {'_id': 0, 'id': 1, 'po_number': 1, 'customer_name': 1}):
            _po_meta[p['id']] = p
    po_rows = {}
    for it in items:
        s = ship_map.get(it.get('shipment_id'))
        if not s:
            continue
        # Phase D: group by the ITEM's PO (consolidated SJ spans multiple POs).
        item_po_id = it.get('po_id') or s.get('po_id')
        if req_po_id and item_po_id != req_po_id:
            continue  # only the requested PO when filtered
        po_key = item_po_id or f"NOPO::{s.get('id')}"
        meta = _po_meta.get(item_po_id, {})
        if po_key not in po_rows:
            po_rows[po_key] = {
                'po_id': item_po_id, 'po_number': meta.get('po_number', s.get('po_number', '')),
                'customer_name': meta.get('customer_name', s.get('customer_name', '')),
                'vendor_name': s.get('vendor_name', ''),
                'total_shipped': 0, 'total_received': 0, 'total_variance': 0, '_items': {},
            }
        row = po_rows[po_key]
        shipped = int(it.get('qty_shipped', 0) or 0)
        recv = it.get('qty_received')
        recv = int(recv) if recv is not None else shipped
        var = shipped - recv
        ikey = it.get('po_item_id') or it.get('id')
        if ikey not in row['_items']:
            row['_items'][ikey] = {
                'po_item_id': it.get('po_item_id'), 'sku': it.get('sku', ''),
                'product_name': it.get('product_name', ''), 'serial_number': it.get('serial_number', ''),
                'size': it.get('size', ''), 'color': it.get('color', ''),
                'shipped': 0, 'received': 0, 'variance': 0,
            }
        d = row['_items'][ikey]
        d['shipped'] += shipped; d['received'] += recv; d['variance'] += var
        row['total_shipped'] += shipped; row['total_received'] += recv; row['total_variance'] += var
    result = []
    # ── GAP G: laporan tetap menampilkan SELISIH walau dokumen SJ sudah
    # dikoreksi ke qty yang benar-benar diterima (identitasnya di `SEL-BYR-…`).
    from core import short_shipment as shortmod
    short_map = await shortmod.buyer_short_totals(
        db, po_ids=[k for k in po_rows.keys() if k and not str(k).startswith('NOPO::')])
    for po_key, row in po_rows.items():
        row['items'] = list(row.pop('_items').values())
        s = short_map.get(row.get('po_id') or '', {})
        row['qty_short_open'] = int(s.get('qty_short_open') or 0)
        row['qty_short_resolved'] = int(s.get('qty_short_resolved') or 0)
        row['short_docs'] = s.get('items') or []
        # variance efektif = selisih dokumen + selisih yang masih terbuka
        row['total_variance_effective'] = row['total_variance'] + row['qty_short_open']
        for it in row['items']:
            it['qty_short_open'] = sum(
                int(x.get('qty_open') or 0) for x in (s.get('items') or [])
                if x.get('po_item_id') == it.get('po_item_id') and x.get('status') == 'open')
        result.append(row)
    result.sort(key=lambda r: r.get('po_number', ''))
    return result


# ═══════════════════════════════════════════════════════════════════════════
# SELISIH KIRIM DA → BUYER (dokumen kelas satu + keputusan finance)
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/buyer-shorts")
async def list_buyer_shorts(request: Request):
    """Catatan selisih kirim DA → buyer. `?status=open|resolved|cancelled|all`,
    `?po_id=`, `?shipment_id=`."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    from core import short_shipment as shortmod
    out = await shortmod.list_buyer_shorts(
        db, status=(sp.get('status') or 'open'), po_id=sp.get('po_id') or '',
        shipment_id=sp.get('shipment_id') or '')
    return serialize_doc(out)


@router.post("/buyer-shorts/{short_id}/resolve")
async def resolve_buyer_short(short_id: str, request: Request):
    """Keputusan atas selisih terima buyer:

      · `dikirim_ulang`  — barang ketinggalan/salah hitung, akan dikirim ulang
      · `tanggungan_cmt` — KEPUTUSAN FINANCE: barang hilang, dibebankan vendor CMT
      · `tanggungan_da`  — KEPUTUSAN FINANCE: barang hilang, dibebankan DA
      · `dibatalkan`     — qty diterima salah dicatat

    Untuk keputusan "hilang", stok FG yang sebelumnya dikembalikan akan
    DIHAPUSBUKUKAN supaya stok fisik tidak menggelembung.
    """
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES + ['finance', 'admin_finance']):
        raise HTTPException(403, 'Hanya Admin/Finance yang boleh memutuskan selisih buyer')
    db = get_db()
    body = await request.json()
    from core import short_shipment as shortmod
    try:
        doc = await shortmod.resolve_buyer_short_manual(
            db, short_id, resolution=(body.get('resolution') or '').strip(),
            notes=(body.get('notes') or '').strip(), actor=user)
    except LookupError as e:
        raise HTTPException(404, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_activity(user['id'], user['name'], 'Keputusan Selisih Buyer', 'Buyer Shipment',
                       f"{(doc or {}).get('short_number')} · {(doc or {}).get('sku')} "
                       f"{(doc or {}).get('qty_short')} pcs → {body.get('resolution')}"
                       + (f". Catatan: {body.get('notes')}" if body.get('notes') else ''))
    return {'success': True, 'short': serialize_doc(doc)}

@router.get("/buyer-shipment-dispatches")
async def get_dispatches(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sid = request.query_params.get('shipment_id')
    if not sid: raise HTTPException(400, 'shipment_id required')
    items = await db.buyer_shipment_items.find({'shipment_id': sid}, {'_id': 0}).sort([('dispatch_seq', 1), ('created_at', 1)]).to_list(None)
    dm = {}
    for item in items:
        seq = item.get('dispatch_seq', 1)
        if seq not in dm:
            dm[seq] = {'dispatch_seq': seq, 'dispatch_date': item.get('dispatch_date') or item.get('created_at'), 'items': [], 'total_qty': 0}
        dm[seq]['items'].append(serialize_doc(item))
        dm[seq]['total_qty'] += item.get('qty_shipped', 0)
    return sorted(dm.values(), key=lambda d: d['dispatch_seq'])
