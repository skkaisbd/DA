"""SSOT KAPASITAS KIRIM DA → BUYER (Fase E, 2026-08-15).

MENGAPA MODUL INI ADA
---------------------
Sebelum ini ada **TIGA** rumus berbeda untuk pertanyaan yang sama — "item ini
masih boleh dikirim berapa?" — dan ketiganya menjawab angka berbeda pada layar
yang sama:

  1. Layar (`BuyerShipmentModule.buildConsItems`)
       cap = Σ(qty_actual − reject_qty), TANPA mengurangi yang sudah dikirim.
     Ini SALAH DUA KALI:
       · `qty_actual` pada `cmt_receipt_lines` sudah berarti **qty LOLOS QC**
         (buktinya `dewi_cmt_packing.py`: `arrived = qty_actual + reject_qty`),
         jadi mengurangi `reject_qty` lagi = memotong reject DUA KALI.
         Inilah sebab keluhan pemilik "chip tertulis 90 kok jadi 80".
       · tidak mengurangi qty yang sudah didispatch ⇒ layar mem-prefill angka
         yang PASTI ditolak backend, dan pemakai baru tahu setelah klik Simpan.
  2. Pagar backend (`_validate_source_receipts_cap`)
       max = Σ(qty_actual) − sudah didispatch **dari receipt yang sama**.
     Pembatas "dari receipt yang sama" membuat dispatch lama yang memakai
     receipt LAIN untuk po_item yang sama tidak ikut terhitung.
  3. Pagar stok (`_fg_precheck_for_dispatch`) memakai stok FG gudang.

Ditambah satu lubang: hasil PERMAK yang sudah jadi bagus **tidak pernah**
menambah kapasitas kirim, karena `apply_rework_outcome()` hanya menaikkan stok
FG + buku kuantitas job dan tidak menyentuh `cmt_receipt_lines`. Akibatnya
lingkaran "100 diproduksi → 10 reject → diperbaiki → 100 siap kirim" tidak
pernah tertutup: 10 pcs itu selamanya tidak bisa dikirim ke buyer.

SATU RUMUS (dipakai layar, pagar backend, dan daftar kekurangan kirim)
---------------------------------------------------------------------
    good_from_cmt = Σ cmt_receipt_lines.qty_actual        (sudah NETTO lolos QC)
    reworked_ok   = Σ cmt_receipt_lines.qty_reworked_ok   (hasil permak sendiri)
    dispatched    = Σ buyer_shipment_items qty EFEKTIF
                    (qty_received bila sudah diisi, else qty_shipped)
    ───────────────────────────────────────────────────────────────────────
    shippable     = max(0, good_from_cmt + reworked_ok − dispatched)

Catatan yang membuat rumus ini benar, bukan sekadar rapi:
  · `reject_open` hanya INFORMASI di layar; ia TIDAK dikurangi lagi karena
    `qty_actual` memang belum memuatnya.
  · Permak `retur_ke_cmt` TIDAK menambah `reworked_ok` — barangnya dikerjakan
    ulang vendor dan masuk lagi lewat PENERIMAAN CMT baru, jadi `qty_actual`
    naik sendiri. Menambahkannya di sini akan menghitung dua kali.
  · `dispatched` dihitung per **po_item_id** melintasi SEMUA surat jalan buyer,
    bukan hanya yang memakai receipt terpilih — itu satu-satunya definisi yang
    cocok dengan kolom "Sudah Dikirim" yang dilihat pemakai.
  · Stok FG gudang tetap PAGAR TERAKHIR (`_fg_precheck_for_dispatch`); modul ini
    melaporkannya sebagai `fg_stock` supaya layar bisa memperingatkan lebih awal
    alih-alih menolak saat Simpan.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

RECEIVER_BUYER = 'buyer'


def _i(v) -> int:
    try:
        return int(float(v or 0))
    except (TypeError, ValueError):
        return 0


def line_key(po_item_id, sku) -> str:
    """Kunci penggabungan. `po_item_id` diutamakan karena satu SKU bisa muncul di
    beberapa PO pada surat jalan konsolidasi."""
    poi = (po_item_id or '').strip()
    if poi:
        return f"poi:{poi}"
    return f"sku:{(sku or '').strip()}"


def _blank(key: str) -> dict:
    return {
        'key': key,
        'po_item_id': key[4:] if key.startswith('poi:') else '',
        'sku': key[4:] if key.startswith('sku:') else '',
        'product_name': '', 'size': '', 'color': '', 'serial_number': '',
        'po_id': '', 'po_number': '',
        'ordered': 0,
        'good_from_cmt': 0,
        'reject_open': 0,
        'reworked_ok': 0,
        'internal_produced': 0,
        'source': 'cmt',
        'dispatched': 0,
        'shippable': 0,
        'fg_stock': None,
        'receipt_ids': [],
    }


async def _apply_internal_produced(db, rows: dict, *, seed_all: bool = False,
                                   po_id: str = '') -> None:
    """Hasil PRODUKSI INTERNAL (`production_job_items.produced_qty`) sebagai sumber kirim.

    PO `business_type='internal'` tidak pernah lewat CMT ⇒ tidak ada `cmt_receipt_lines`.
    Tanpa ini kapasitas kirimnya selalu 0 (audit iteration_102). Stok FG gudang tetap
    pagar terakhir (`_fg_precheck_for_dispatch`).
    `seed_all=True` menambahkan baris untuk semua item PO internal yang sudah berproduksi
    (dipakai daftar kekurangan kirim); selain itu hanya melengkapi baris yang sudah ada.
    """
    proj = {'_id': 0, 'id': 1, 'po_id': 1}
    if seed_all:
        q = {'business_type': 'internal'}
        if po_id:
            q['id'] = po_id
        po_ids = await db.production_pos.distinct('id', q)
        poi_docs = await db.po_items.find({'po_id': {'$in': po_ids}}, proj).to_list(None) if po_ids else []
    else:
        poi_ids = [r['po_item_id'] for r in rows.values() if r['po_item_id']]
        if not poi_ids:
            return
        poi_docs = await db.po_items.find({'id': {'$in': poi_ids}}, proj).to_list(None)
        po_ids = list({d.get('po_id') for d in poi_docs if d.get('po_id')})
        internal = set(await db.production_pos.distinct(
            'id', {'id': {'$in': po_ids}, 'business_type': 'internal'})) if po_ids else set()
        poi_docs = [d for d in poi_docs if d.get('po_id') in internal]
    target = [d['id'] for d in poi_docs]
    if not target:
        return
    ji_q = {'po_item_id': {'$in': target}}
    if seed_all:
        ji_q['produced_qty'] = {'$gt': 0}
    async for ji in db.production_job_items.find(ji_q, {'_id': 0}):
        k = line_key(ji.get('po_item_id'), ji.get('sku'))
        r = rows.setdefault(k, _blank(k)) if seed_all else rows.get(k)
        if not r:
            continue
        r['internal_produced'] += _i(ji.get('produced_qty'))
        r['source'] = 'internal'
        for f in ('sku', 'product_name', 'size', 'color'):
            if not r[f] and ji.get(f):
                r[f] = ji[f]


async def _rows_from_receipt_lines(db, query: dict) -> dict:
    """Bangun baris kapasitas dari `cmt_receipt_lines` yang cocok `query`."""
    rows: dict = {}
    async for ln in db.cmt_receipt_lines.find(query, {'_id': 0}):
        k = line_key(ln.get('po_item_id'), ln.get('sku_code'))
        r = rows.setdefault(k, _blank(k))
        r['good_from_cmt'] += _i(ln.get('qty_actual'))
        r['reworked_ok'] += _i(ln.get('qty_reworked_ok'))
        # sisa reject yang BELUM diputuskan (informasi layar saja)
        r['reject_open'] += max(
            0,
            _i(ln.get('reject_qty')) - _i(ln.get('qty_reworked_ok'))
            - _i(ln.get('qty_reject_scrapped')))
        if not r['sku']:
            r['sku'] = ln.get('sku_code') or ''
        for src, dst in (('product_name', 'product_name'), ('size', 'size'),
                         ('color', 'color')):
            if not r[dst] and ln.get(src):
                r[dst] = ln[src]
        if ln.get('po_item_id') and not r['po_item_id']:
            r['po_item_id'] = ln['po_item_id']
        if ln.get('receipt_id') and ln['receipt_id'] not in r['receipt_ids']:
            r['receipt_ids'].append(ln['receipt_id'])
    return rows


async def _apply_dispatched(db, rows: dict) -> None:
    """Kurangi kapasitas dengan qty yang SUDAH dikirim ke buyer (semua surat jalan)."""
    if not rows:
        return
    poi_ids = [r['po_item_id'] for r in rows.values() if r['po_item_id']]
    skus = [r['sku'] for r in rows.values() if not r['po_item_id'] and r['sku']]
    ors = []
    if poi_ids:
        ors.append({'po_item_id': {'$in': poi_ids}})
    if skus:
        ors.append({'sku': {'$in': skus}})
    if not ors:
        return
    items = await db.buyer_shipment_items.find(
        {'$or': ors}, {'_id': 0}).to_list(None)
    if not items:
        return
    ship_ids = list({it.get('shipment_id') for it in items if it.get('shipment_id')})
    buyer_ships = set()
    if ship_ids:
        async for s in db.buyer_shipments.find(
                {'id': {'$in': ship_ids}}, {'_id': 0, 'id': 1, 'receiver_type': 1}):
            # dokumen lama tanpa receiver_type = surat jalan ke BUYER (backward compat)
            if (s.get('receiver_type') or RECEIVER_BUYER) == RECEIVER_BUYER:
                buyer_ships.add(s['id'])
    for it in items:
        if it.get('shipment_id') not in buyer_ships:
            continue
        k = line_key(it.get('po_item_id'), it.get('sku'))
        r = rows.get(k)
        if not r:
            continue
        eff = (_i(it['qty_received']) if it.get('qty_received') is not None
               else _i(it.get('qty_shipped')))
        r['dispatched'] += eff
        if not r['ordered']:
            r['ordered'] = _i(it.get('ordered_qty'))


async def _enrich_po(db, rows: dict) -> None:
    """Isi ordered/po_number/serial dari `po_items` + `production_pos`."""
    poi_ids = [r['po_item_id'] for r in rows.values() if r['po_item_id']]
    if not poi_ids:
        return
    poi_docs = await db.po_items.find({'id': {'$in': poi_ids}}, {'_id': 0}).to_list(None)
    po_ids = list({d.get('po_id') for d in poi_docs if d.get('po_id')})
    po_meta = {}
    if po_ids:
        async for p in db.production_pos.find(
                {'id': {'$in': po_ids}},
                {'_id': 0, 'id': 1, 'po_number': 1, 'customer_name': 1, 'business_type': 1}):
            po_meta[p['id']] = p
    by_id = {d['id']: d for d in poi_docs}
    for r in rows.values():
        d = by_id.get(r['po_item_id'])
        if not d:
            continue
        r['ordered'] = _i(d.get('qty')) or r['ordered']
        r['po_id'] = d.get('po_id') or ''
        r['serial_number'] = d.get('serial_number') or r['serial_number']
        for f in ('product_name', 'sku', 'size', 'color'):
            if not r.get(f) and d.get(f):
                r[f] = d[f]
        meta = po_meta.get(r['po_id']) or {}
        r['po_number'] = meta.get('po_number', '')
        r['buyer'] = meta.get('customer_name', '')
        r['business_type'] = meta.get('business_type') or 'internal'


async def _enrich_fg_stock(db, rows: dict) -> None:
    """Stok FG per SKU (informasi dini; pagar keras tetap di precheck dispatch)."""
    skus = list({r['sku'] for r in rows.values() if r.get('sku')})
    if not skus:
        return
    try:
        from core import production_qty_ledger as qled
        from core import stock_service
        from core import quarantine as qmod
    except Exception:  # noqa: BLE001
        return
    try:
        qloc = await qmod.get_quarantine_location_id(db)
    except Exception:  # noqa: BLE001
        qloc = None
    cache: dict = {}
    for sku in skus:
        try:
            mat = await qled.resolve_fg_material(db, sku=sku)
            if not mat:
                cache[sku] = None
                continue
            have = 0.0
            for row in await stock_service.list_rows(mat['id'], db=db):
                if qloc and row.get('location_id') == qloc:
                    continue
                try:
                    have += float(row.get('qty') or row.get('quantity') or 0)
                except (TypeError, ValueError):
                    continue
            cache[sku] = have
        except Exception:  # noqa: BLE001
            logger.exception('kapasitas kirim: gagal membaca stok FG %s', sku)
            cache[sku] = None
    for r in rows.values():
        if r.get('sku') in cache:
            r['fg_stock'] = cache[r['sku']]


def _shippable(r: dict) -> int:
    return max(0, r['good_from_cmt'] + r['reworked_ok'] + r['internal_produced'] - r['dispatched'])


def _finalize(rows: dict) -> list:
    out = []
    for r in rows.values():
        r['shippable'] = _shippable(r)
        r['remaining_vs_order'] = max(0, r['ordered'] - r['dispatched']) if r['ordered'] else 0
        out.append(r)
    out.sort(key=lambda x: (x.get('po_number') or '', x.get('sku') or ''))
    return out


async def by_receipts(db, receipt_ids: list, *, with_fg_stock: bool = False) -> list:
    """Kapasitas kirim untuk kumpulan `cmt_receipts` yang dipilih di form dispatch."""
    ids = [r for r in (receipt_ids or []) if r]
    if not ids:
        return []
    rows = await _rows_from_receipt_lines(db, {'receipt_id': {'$in': ids}})
    await _apply_dispatched(db, rows)
    await _enrich_po(db, rows)
    if with_fg_stock:
        await _enrich_fg_stock(db, rows)
    return _finalize(rows)


async def by_po_items(db, po_item_ids: list, *, with_fg_stock: bool = False) -> list:
    """Kapasitas kirim untuk daftar po_item (dipakai pagar backend)."""
    ids = [p for p in (po_item_ids or []) if p]
    if not ids:
        return []
    rows = await _rows_from_receipt_lines(db, {'po_item_id': {'$in': ids}})
    for pid in ids:
        rows.setdefault(line_key(pid, ''), _blank(line_key(pid, '')))
    await _apply_internal_produced(db, rows)
    await _apply_dispatched(db, rows)
    await _enrich_po(db, rows)
    if with_fg_stock:
        await _enrich_fg_stock(db, rows)
    return _finalize(rows)


async def map_for_validation(db, *, receipt_ids: list, items_data: list) -> dict:
    """Peta kunci → baris kapasitas untuk pagar `POST /api/buyer-shipments`.

    Menggabungkan DUA sumber supaya tidak ada celah:
      · baris dari receipt yang dipilih (jalur normal), dan
      · baris dari po_item yang diminta (menutup kasus po_item yang penerimaannya
        ada di receipt LAIN, mis. sesudah permak retur ke CMT).
    """
    rows = await _rows_from_receipt_lines(db, {'receipt_id': {'$in': list(receipt_ids or [])}})
    extra_pois = [it.get('po_item_id') for it in (items_data or []) if it.get('po_item_id')]
    missing = [p for p in extra_pois if line_key(p, '') not in rows]
    if missing:
        rows.update(await _rows_from_receipt_lines(db, {'po_item_id': {'$in': missing}}))
        for p in missing:
            rows.setdefault(line_key(p, ''), _blank(line_key(p, '')))
    await _apply_internal_produced(db, rows)
    await _apply_dispatched(db, rows)
    await _enrich_po(db, rows)
    for r in rows.values():
        r['shippable'] = _shippable(r)
    return rows


async def outstanding(db, *, buyer: str = '', po_id: str = '',
                      include_settled: bool = False) -> list:
    """DAFTAR KEKURANGAN KIRIM — semua item yang masih punya sisa kirim ke buyer.

    Dipakai tab "Kekurangan Kirim" supaya pemakai tidak perlu menebak sisa.

    Sumber baris SENGAJA gabungan dua arah:
      · `cmt_receipt_lines` → barang yang sudah diterima dari CMT (calon kiriman), dan
      · `buyer_shipment_items` → item yang SUDAH pernah dikirim sebagian.
    Kalau hanya memakai penerimaan, surat jalan lama yang penerimaannya belum
    tercatat (data warisan) akan HILANG dari daftar padahal justru itu yang
    kekurangan kirimnya paling sering ditanyakan.
    """
    rows = await _rows_from_receipt_lines(db, {})
    # tambahkan po_item dari surat jalan buyer yang sudah ada (termasuk warisan)
    ship_ids = set()
    async for s in db.buyer_shipments.find(
            {}, {'_id': 0, 'id': 1, 'receiver_type': 1}):
        if (s.get('receiver_type') or RECEIVER_BUYER) == RECEIVER_BUYER:
            ship_ids.add(s['id'])
    if ship_ids:
        async for it in db.buyer_shipment_items.find(
                {'shipment_id': {'$in': list(ship_ids)}}, {'_id': 0}):
            k = line_key(it.get('po_item_id'), it.get('sku'))
            r = rows.setdefault(k, _blank(k))
            if not r['sku']:
                r['sku'] = it.get('sku') or ''
            for f in ('product_name', 'size', 'color', 'serial_number'):
                if not r[f] and it.get(f):
                    r[f] = it[f]
    await _apply_internal_produced(db, rows, seed_all=True, po_id=po_id)
    await _apply_dispatched(db, rows)
    await _enrich_po(db, rows)
    await _enrich_fg_stock(db, rows)
    result = _finalize(rows)
    if buyer:
        b = buyer.strip().lower()
        result = [r for r in result if (r.get('buyer') or '').strip().lower() == b]
    if po_id:
        result = [r for r in result if r.get('po_id') == po_id]
    if not include_settled:
        result = [r for r in result
                  if r['shippable'] > 0 or r.get('remaining_vs_order', 0) > 0]
    return result
