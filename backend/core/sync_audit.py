"""core/sync_audit.py — **audit sinkronisasi lintas portal** sebagai layanan hidup.

═══════════════════════════════════════════════════════════════════════════════
KENAPA ADA
═══════════════════════════════════════════════════════════════════════════════
Ketidaksinkronan yang membuat pemilik kehilangan kepercayaan ("id gudang dan
marketing tidak sama") baru ketahuan setelah **seseorang menjalankan skrip
forensik**. Skrip itu hanya hidup di komputer agent. Pemilik tidak punya cara
melihat kesehatan tautan datanya sendiri, jadi kerusakan senyap bisa berumur
berbulan-bulan.

Berkas ini memindahkan pengukuran itu ke dalam aplikasi:
  * :func:`build_report` — laporan A–E yang sama, dihitung dari data hidup.
  * :func:`run_repair` — perbaikan yang **aman & bisa dipratinjau** (dry-run).

ATURAN
------
1. Audit **hanya membaca**. Perbaikan hanya lewat :func:`run_repair`, selalu
   idempoten, dan selalu bisa dijalankan sebagai pratinjau lebih dulu.
2. Tidak ada perbaikan yang MENEBAK identitas barang. Menautkan item katalog ke
   FG hanya dilakukan bila **SKU-nya sama persis** — sisanya urusan Jembatan SKU
   (manusia yang memutuskan).
3. Angka yang dilaporkan wajib bisa ditelusuri ke baris aslinya (`samples`).
"""
from __future__ import annotations

import logging
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

STOCK = 'rahaza_material_stock'
MATERIALS = 'rahaza_materials'
ITEMS = 'marketing_catalog_items'
ORDERS = 'marketing_orders'
VARIANTS = 'rahaza_model_variants'
LOCATIONS = 'rahaza_locations'


def _now():
    return datetime.now(timezone.utc)


def _f(v, d=0.0):
    try:
        return float(v if v is not None else d)
    except (TypeError, ValueError):
        return d


def _pct(a, b):
    return 0.0 if not b else round(100.0 * a / b, 1)


def _read_qty(s: dict) -> float:
    for k in ('qty', 'total_qty', 'quantity', 'on_hand', 'onhand'):
        if s.get(k) is not None:
            return _f(s[k])
    return 0.0


def _read_reserved(s: dict) -> float:
    for k in ('reserved_qty', 'reserved', 'qty_reserved'):
        if s.get(k) is not None:
            return _f(s[k])
    return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Aturan rujukan lintas koleksi (foreign key yang harus utuh)
# ══════════════════════════════════════════════════════════════════════════════
FK_RULES = [
    ('marketing_catalog_items', 'catalog_id', 'marketing_catalogs', 'id', 'item katalog → katalog'),
    ('marketing_catalog_items', 'account_id', 'marketing_platform_accounts', 'id', 'item katalog → toko'),
    ('marketing_catalog_items', 'fg_material_id', 'rahaza_materials', 'id', 'item katalog → master FG'),
    ('marketing_catalog_items', 'variant_id', 'rahaza_model_variants', 'id', 'item katalog → varian'),
    ('marketing_catalog_items', 'model_id', 'rahaza_models', 'id', 'item katalog → model'),
    ('marketing_orders', 'account_id', 'marketing_platform_accounts', 'id', 'pesanan → toko'),
    ('marketing_sku_bridge', 'fg_material_id', 'rahaza_materials', 'id', 'jembatan SKU → master FG'),
    ('marketing_sku_bridge', 'catalog_item_id', 'marketing_catalog_items', 'id', 'jembatan SKU → item katalog'),
    ('rahaza_material_stock', 'material_id', 'rahaza_materials', 'id', 'baris stok → material'),
    ('rahaza_material_stock', 'location_id', 'rahaza_locations', 'id', 'baris stok → lokasi'),
    ('rahaza_model_variants', 'model_id', 'rahaza_models', 'id', 'varian → model'),
    ('rahaza_materials', 'variant_id', 'rahaza_model_variants', 'id', 'master FG → varian'),
    ('rahaza_materials', 'model_id', 'rahaza_models', 'id', 'master FG → model'),
    ('rahaza_stock_ledger', 'material_id', 'rahaza_materials', 'id', 'kartu stok → material'),
    ('rahaza_material_movements', 'material_id', 'rahaza_materials', 'id', 'mutasi stok → material'),
    ('marketing_sales_data', 'account_id', 'marketing_platform_accounts', 'id', 'penjualan → toko'),
    ('marketing_budgets', 'account_id', 'marketing_platform_accounts', 'id', 'anggaran → toko'),
    ('marketing_account_targets', 'account_id', 'marketing_platform_accounts', 'id', 'target → toko'),
    ('vendor_jobs', 'model_id', 'rahaza_models', 'id', 'job vendor → model'),
    ('production_job_items', 'material_id', 'rahaza_materials', 'id', 'baris job produksi → material'),
    ('po_items', 'material_id', 'rahaza_materials', 'id', 'baris PO → material'),
]


# ══════════════════════════════════════════════════════════════════════════════
# A. MARKETING → GUDANG
# ══════════════════════════════════════════════════════════════════════════════
async def _section_a(db) -> dict:
    from core import fulfillment_status as fs

    lines = linked = 0
    pcs = pcs_linked = 0.0
    orders = ready = partial = blocked = 0
    queue = queue_ready = 0
    need_ship_not_in_queue = 0
    unmapped = set()
    sources = Counter()
    fstat = Counter()

    async for o in db[ORDERS].find({}, {'_id': 0, 'items': 1, 'fulfillment_status': 1,
                                       'status': 1, 'fg_material_id': 1,
                                       'quantity': 1, 'sku_id': 1}):
        orders += 1
        fstat[str(o.get('fulfillment_status') or '(kosong)')] += 1
        lk = fs.order_linkage(o)
        lines += lk['lines']
        linked += lk['linked']
        pcs += lk['pcs']
        pcs_linked += lk['pcs_linked']
        unmapped.update(lk['unmapped_skus'])
        if lk['ready']:
            ready += 1
        elif lk['linked']:
            partial += 1
        else:
            blocked += 1
        for ln in (o.get('items') or []):
            sources[str((ln or {}).get('master_link_source') or 'unlinked')] += 1
        inq = fs.in_queue(o.get('fulfillment_status'))
        if inq:
            queue += 1
            if lk['ready']:
                queue_ready += 1
        else:
            want, _ = fs.initial_status(o)
            if want == fs.PENDING and o.get('fulfillment_status') not in fs.CLOSED_STATES:
                need_ship_not_in_queue += 1

    bridges = await db['marketing_sku_bridge'].count_documents({})
    legacy_map = 0
    async for it in db[ITEMS].find({'platform_sku_ids': {'$exists': True, '$ne': []}},
                                   {'_id': 0, 'platform_sku_ids': 1}):
        legacy_map += len(it.get('platform_sku_ids') or [])

    findings = []
    if lines and linked == 0:
        findings.append({'severity': 'CRITICAL', 'code': 'A1',
                         'text': f'NOL dari {lines} baris pesanan marketing menunjuk master gudang. '
                                 'Tim gudang mustahil mencocokkan barang dari id.',
                         'action': 'sku_bridge'})
    elif lines and _pct(linked, lines) < 90:
        findings.append({'severity': 'HIGH', 'code': 'A1',
                         'text': f'{lines - linked} dari {lines} baris pesanan belum menunjuk master gudang '
                                 f'({_pct(linked, lines)}% tertaut).',
                         'action': 'sku_bridge'})
    if unmapped:
        findings.append({'severity': 'HIGH', 'code': 'A3',
                         'text': f'{len(unmapped)} SKU platform dipesan pembeli tetapi belum dikenal master.',
                         'action': 'sku_bridge'})
    if need_ship_not_in_queue:
        findings.append({'severity': 'CRITICAL', 'code': 'A2',
                         'text': f'{need_ship_not_in_queue} pesanan yang menurut platform PERLU DIKIRIM '
                                 'tidak berada di antrean gudang — gudang tidak melihat pekerjaannya.',
                         'action': 'normalize_fulfillment_status'})
    if queue and queue_ready == 0:
        findings.append({'severity': 'HIGH', 'code': 'A5',
                         'text': f'{queue} pesanan ada di antrean gudang tetapi TIDAK SATU PUN siap '
                                 'dialokasikan (semua barisnya belum tertaut master).',
                         'action': 'sku_bridge'})

    return {'title': 'Marketing → Gudang', 'findings': findings, 'metrics': {
        'orders': orders, 'lines': lines, 'lines_linked': linked,
        'lines_linked_pct': _pct(linked, lines),
        'pcs': round(pcs, 2), 'pcs_linked': round(pcs_linked, 2),
        'pcs_linked_pct': _pct(pcs_linked, pcs),
        'orders_ready': ready, 'orders_partial': partial, 'orders_blocked': blocked,
        'queue_orders': queue, 'queue_ready': queue_ready,
        'need_ship_not_in_queue': need_ship_not_in_queue,
        'unmapped_sku_count': len(unmapped),
        'bridge_mappings': bridges, 'legacy_platform_sku_map': legacy_map,
        'link_sources': dict(sources), 'fulfillment_status_spread': dict(fstat),
    }}


# ══════════════════════════════════════════════════════════════════════════════
# B. KATALOG → MASTER FG
# ══════════════════════════════════════════════════════════════════════════════
async def _section_b(db) -> dict:
    items = await db[ITEMS].find({}, {'_id': 0}).to_list(20000)
    mats = {}
    fg_by_code = {}
    async for m in db[MATERIALS].find({}, {'_id': 0, 'id': 1, 'code': 1, 'sku': 1, 'type': 1}):
        mats[m['id']] = m
        if (m.get('type') or '').lower() == 'fg':
            for k in (m.get('code'), m.get('sku')):
                if k:
                    fg_by_code[str(k).upper()] = m

    stock_rows = defaultdict(list)
    async for s in db[STOCK].find({}, {'_id': 0}):
        stock_rows[s.get('material_id')].append(s)

    linked, dangling, fixable, no_link = [], [], [], []
    for i in items:
        mid = i.get('fg_material_id') or i.get('material_id')
        if mid:
            (linked if mid in mats else dangling).append(i)
        else:
            vsku = str(i.get('variant_sku') or i.get('sku') or '').strip().upper()
            (fixable if vsku and vsku in fg_by_code else no_link).append(i)

    drift = []
    nostock = []
    for i in linked:
        mid = i.get('fg_material_id') or i.get('material_id')
        rows = stock_rows.get(mid, [])
        if not rows:
            nostock.append({'sku': i.get('sku', ''), 'name': (i.get('name') or '')[:60]})
        live = max(0.0, sum(_read_qty(r) for r in rows) - sum(_read_reserved(r) for r in rows))
        cache = _f(i.get('stock_quantity'))
        if abs(live - cache) > 0.001:
            drift.append({'sku': i.get('sku', ''), 'name': (i.get('name') or '')[:60],
                          'cache': cache, 'live': round(live, 2)})

    findings = []
    if dangling:
        findings.append({'severity': 'HIGH', 'code': 'B1',
                         'text': f'{len(dangling)} item katalog menunjuk master FG yang TIDAK ADA — '
                                 'stok yang ditampilkan ke marketing pasti salah.',
                         'action': None})
    if fixable:
        findings.append({'severity': 'MED', 'code': 'B2',
                         'text': f'{len(fixable)} item katalog bisa ditautkan otomatis lewat SKU yang sama '
                                 'tetapi tautannya dibiarkan kosong.',
                         'action': 'relink_catalog_by_sku'})
    if no_link:
        # Bedakan cacat NYATA dari fixture demo. `scripts/seed_katalog_order_demo.py`
        # SENGAJA membuat satu item tanpa tautan master (`LEGACY-NOLINK-001`,
        # komentarnya: "kasus buruk yang harus terlihat") supaya audit ini bisa
        # dibuktikan bekerja. Kalau ia dihitung sebagai cacat, skor mustahil hijau
        # dan pemilik dilatih untuk mengabaikan temuan HIGH — itu lebih berbahaya
        # daripada temuannya sendiri.
        demo_only = [d for d in no_link
                     if d.get('demo_source') or d.get('created_via') in ('demo', 'seed')
                     or str(d.get('sku') or '').upper().startswith(('LEGACY-NOLINK', 'DEMO-', 'QA-'))]
        real = [d for d in no_link if d not in demo_only]
        if real:
            findings.append({'severity': 'HIGH', 'code': 'B3',
                             'text': f'{len(real)} item katalog tanpa master FG ⇒ stoknya tidak bisa dihitung.',
                             'action': None})
        if demo_only:
            findings.append({
                'severity': 'INFO', 'code': 'B3d',
                'text': (f'{len(demo_only)} item katalog tanpa master FG adalah FIXTURE DEMO yang '
                         'sengaja dibuat seeder sebagai bukti audit ini bekerja '
                         f"({', '.join(str(d.get('sku') or '?') for d in demo_only[:3])}) — "
                         'bukan cacat, jangan dihapus.'),
                'action': None})
    if drift:
        findings.append({'severity': 'HIGH', 'code': 'B4',
                         'text': f'{len(drift)} item katalog memamerkan stok yang berbeda dari gudang '
                                 '(risiko overselling).',
                         'action': 'refresh_catalog_stock_cache'})
    if nostock:
        findings.append({'severity': 'MED', 'code': 'B5',
                         'text': f'{len(nostock)} item katalog tertaut master FG yang belum punya baris stok '
                                 '(dijual tanpa barang di gudang).',
                         'action': None})

    return {'title': 'Katalog Marketing → Master FG', 'findings': findings, 'metrics': {
        'items': len(items), 'linked': len(linked), 'dangling': len(dangling),
        'fixable_by_sku': len(fixable), 'no_link': len(no_link),
        'stock_cache_drift': len(drift), 'linked_without_stock_rows': len(nostock),
    }, 'samples': {'drift': drift[:15], 'no_stock': nostock[:15],
                   'dangling': [{'sku': d.get('sku'), 'name': d.get('name')} for d in dangling[:10]],
                   'no_link': [{'sku': d.get('sku'), 'name': d.get('name')} for d in no_link[:10]]}}


# ══════════════════════════════════════════════════════════════════════════════
# C. VARIAN → MASTER FG → STOK
# ══════════════════════════════════════════════════════════════════════════════
async def _section_c(db) -> dict:
    variants = await db[VARIANTS].find({}, {'_id': 0, 'id': 1, 'sku': 1, 'model_name': 1,
                                            'color_name': 1, 'size_code': 1,
                                            'active': 1}).to_list(20000)
    fg = await db[MATERIALS].find({'type': 'fg'}, {'_id': 0, 'id': 1, 'code': 1, 'sku': 1,
                                                   'variant_id': 1}).to_list(20000)
    fg_by_variant = {m['variant_id']: m for m in fg if m.get('variant_id')}
    fg_by_code = {str(m.get('code') or m.get('sku') or '').upper(): m for m in fg}

    stock_ids = set()
    async for s in db[STOCK].find({}, {'_id': 0, 'material_id': 1}):
        if s.get('material_id'):
            stock_ids.add(s['material_id'])

    item_variant_ids = set()
    async for i in db[ITEMS].find({'variant_id': {'$ne': None}}, {'_id': 0, 'variant_id': 1}):
        item_variant_ids.add(i['variant_id'])

    orphan = [v for v in variants
              if v['id'] not in fg_by_variant
              and str(v.get('sku') or '').upper() not in fg_by_code]
    with_fg = [v for v in variants if v['id'] in fg_by_variant]
    no_stock = [v for v in with_fg if fg_by_variant[v['id']]['id'] not in stock_ids]
    not_sellable = [v for v in variants if v['id'] not in item_variant_ids]
    fg_no_variant = [m for m in fg if not m.get('variant_id')]

    findings = []
    if orphan:
        findings.append({'severity': 'HIGH', 'code': 'C1',
                         'text': f'{len(orphan)} varian model belum punya master FG ⇒ mustahil dikirim gudang.',
                         'action': None})
    if fg_no_variant:
        findings.append({'severity': 'MED', 'code': 'C2',
                         'text': f'{len(fg_no_variant)} master FG tidak menunjuk varian mana pun — '
                                 'jejak balik ke master produk hilang.',
                         'action': None})
    if no_stock:
        findings.append({'severity': 'MED', 'code': 'C3',
                         'text': f'{len(no_stock)} varian sudah punya master FG tetapi belum punya baris '
                                 'stok di gudang (belum pernah diterima barangnya).',
                         'action': None})
    if not_sellable:
        findings.append({'severity': 'MED', 'code': 'C4',
                         'text': f'{len(not_sellable)} varian belum masuk katalog jual mana pun ⇒ '
                                 'marketing tidak bisa menjualnya.',
                         'action': None})

    # ── C5 (Sesi #28) — palet warna kembar membuat pemetaan warna MENDUA ─────
    # Diukur: 5 pasang kembar (Putih PTH+WHT · Hitam HTM+BLK · Merah MRH+RED ·
    # Krem KRM+CRM · Abu+Abu-abu) sehingga SATU model punya dua varian "Putih"
    # (DA-TS01-PTH-S dan DA-TS01-WHT-S). Pencocokan warna berdasarkan nama jadi
    # bisa memilih kode mana saja — inilah pintu masuk barang salah kirim.
    from core import variant_identity as _vi

    color_groups: dict = {}
    async for c in db.rahaza_colors.find({'active': {'$ne': False}},
                                         {'_id': 0, 'id': 1, 'code': 1, 'name': 1}):
        color_groups.setdefault(_vi.color_group_key(c.get('name')), []).append(c)
    dup_groups = {k: v for k, v in color_groups.items() if len(v) > 1}
    if dup_groups:
        label = ', '.join(
            '{}={}'.format(name, '+'.join(sorted(str(x.get('code') or '') for x in members)))
            for name, members in sorted(dup_groups.items()))
        findings.append({
            'severity': 'HIGH', 'code': 'C5',
            'text': (f'{len(dup_groups)} warna master punya kembaran ({label}) '
                     '⇒ pemetaan warna mendua dan satu model bisa punya dua varian '
                     'berwarna sama.'),
            'action': 'merge_duplicate_colors'})

    # ── C6 (Sesi #28) — dimensi ke-3 (Opsi) wajib punya master & terisi ──────
    no_option = await db[VARIANTS].count_documents({'$or': [
        {'option_code': {'$exists': False}}, {'option_code': {'$in': [None, '']}}]})
    if no_option:
        findings.append({
            'severity': 'MED', 'code': 'C6',
            'text': (f'{no_option} varian belum punya kolom Opsi (dimensi ke-3) — '
                     "'Pakai Karet' dan 'Tanpa Karet' bisa tertimpa menjadi satu barang."),
            'action': 'ensure_variant_option_dimension'})

    return {'title': 'Varian Model → Master FG → Stok', 'findings': findings, 'metrics': {
        'variants': len(variants), 'fg_materials': len(fg),
        'variants_with_fg': len(with_fg), 'orphan_variants': len(orphan),
        'fg_without_variant': len(fg_no_variant),
        'variants_with_fg_no_stock': len(no_stock),
        'variants_not_in_catalog': len(not_sellable),
    }, 'samples': {'orphan': [{'sku': v.get('sku'), 'name': v.get('model_name')} for v in orphan[:10]],
                   'no_stock': [{'sku': v.get('sku'), 'name': v.get('model_name')} for v in no_stock[:10]]}}


# ══════════════════════════════════════════════════════════════════════════════
# D. STOCK OPNAME → MASTER
# ══════════════════════════════════════════════════════════════════════════════
OPNAME_RE = re.compile(r'opname|stock_count|stock_take|cycle_count', re.I)


async def _section_d(db) -> dict:
    names = await db.list_collection_names()
    opname_colls = sorted(c for c in names if OPNAME_RE.search(c))

    mats = set()
    async for m in db[MATERIALS].find({}, {'_id': 0, 'id': 1}):
        mats.add(m['id'])
    locs = set()
    async for l in db[LOCATIONS].find({}, {'_id': 0, 'id': 1}):
        locs.add(l['id'])

    counts = {}
    sessions = lines = bad_mat = bad_loc = 0
    samples = []
    for c in opname_colls:
        n = await db[c].count_documents({})
        counts[c] = n
        if not n:
            continue
        async for d in db[c].find({}, {'_id': 0}):
            sessions += 1
            rows = d.get('items') or d.get('lines') or d.get('counts') or []
            if isinstance(rows, list) and rows:
                for ln in rows:
                    if not isinstance(ln, dict):
                        continue
                    lines += 1
                    mid = ln.get('material_id') or ln.get('item_id')
                    lid = ln.get('location_id') or ln.get('bin_id') or ln.get('position_id')
                    if mid and mid not in mats:
                        bad_mat += 1
                        if len(samples) < 10:
                            samples.append({'collection': c, 'material_id': mid,
                                            'reason': 'material_id tidak ada di master'})
                    if lid and lid not in locs:
                        bad_loc += 1
                        if len(samples) < 10:
                            samples.append({'collection': c, 'location_id': lid,
                                            'reason': 'location_id tidak ada di master lokasi'})
            else:
                mid = d.get('material_id')
                if mid:
                    lines += 1
                    if mid not in mats:
                        bad_mat += 1

    schema = Counter()
    dang_m = dang_l = 0
    async for s in db[STOCK].find({}, {'_id': 0}):
        keys = tuple(sorted(k for k in ('qty', 'total_qty', 'quantity') if s.get(k) is not None))
        schema['+'.join(keys) or '(tanpa field qty)'] += 1
        if s.get('material_id') and s['material_id'] not in mats:
            dang_m += 1
        if s.get('location_id') and s['location_id'] not in locs:
            dang_l += 1

    findings = []
    if bad_mat:
        findings.append({'severity': 'HIGH', 'code': 'D1',
                         'text': f'{bad_mat} baris stock opname memakai material_id yang tidak ada di master.',
                         'action': None})
    if bad_loc:
        findings.append({'severity': 'HIGH', 'code': 'D2',
                         'text': f'{bad_loc} baris stock opname memakai lokasi yang tidak ada di master lokasi.',
                         'action': None})
    if sessions == 0:
        findings.append({'severity': 'INFO', 'code': 'D0',
                         'text': 'Belum ada sesi stock opname — kecocokan opname↔master belum bisa diukur '
                                 'dari data nyata.', 'action': None})
    if len(schema) > 1:
        findings.append({'severity': 'MED', 'code': 'D3',
                         'text': f'Koleksi stok memakai {len(schema)} skema kuantitas berbeda '
                                 f'({", ".join(schema)}) — pembacaan mentah akan salah hitung. '
                                 'Semua pembaca WAJIB lewat core/stock_schema.', 'action': None})
    if dang_m:
        findings.append({'severity': 'HIGH', 'code': 'D4',
                         'text': f'{dang_m} baris stok menunjuk material yang tidak ada di master.',
                         'action': None})
    if dang_l:
        findings.append({'severity': 'HIGH', 'code': 'D5',
                         'text': f'{dang_l} baris stok menunjuk lokasi yang tidak ada di master lokasi.',
                         'action': None})

    return {'title': 'Stock Opname → Master Data', 'findings': findings, 'metrics': {
        'opname_collections': counts, 'sessions': sessions, 'lines': lines,
        'unknown_material_id': bad_mat, 'unknown_location_id': bad_loc,
        'stock_qty_schemas': dict(schema),
        'stock_dangling_material': dang_m, 'stock_dangling_location': dang_l,
    }, 'samples': {'opname': samples}}


# ══════════════════════════════════════════════════════════════════════════════
# E. INTEGRITAS RUJUKAN
# ══════════════════════════════════════════════════════════════════════════════
async def _section_e(db) -> dict:
    names = set(await db.list_collection_names())
    cache = {}
    rows = []
    for coll, field, target, tfield, note in FK_RULES:
        if coll not in names or target not in names:
            continue
        n = await db[coll].count_documents({})
        if not n:
            continue
        if target not in cache:
            ids = set()
            async for d in db[target].find({}, {'_id': 0, tfield: 1}):
                if d.get(tfield):
                    ids.add(d[tfield])
            cache[target] = ids
        ids = cache[target]
        filled = dang = 0
        bad_samples = []
        async for d in db[coll].find({}, {'_id': 0, field: 1}):
            v = d.get(field)
            if not v or not isinstance(v, str):
                continue
            filled += 1
            if v not in ids:
                dang += 1
                if len(bad_samples) < 5:
                    bad_samples.append(v)
        rows.append({'collection': coll, 'field': field, 'target': target,
                     'docs': n, 'filled': filled, 'dangling': dang,
                     'note': note, 'samples': bad_samples})

    findings = []
    for r in sorted(rows, key=lambda x: -x['dangling']):
        if r['dangling']:
            findings.append({'severity': 'HIGH', 'code': 'E1',
                             'text': f"{r['collection']}.{r['field']} → {r['target']}: "
                                     f"{r['dangling']} rujukan rusak ({r['note']}).",
                             'action': None})
    empties = [r for r in rows if r['docs'] and r['filled'] == 0]
    for r in empties:
        findings.append({'severity': 'MED', 'code': 'E2',
                         'text': f"{r['collection']}.{r['field']} kosong di SELURUH {r['docs']} dokumen "
                                 f"({r['note']}) — tautannya tidak pernah diisi.",
                         'action': None})

    return {'title': 'Integritas Rujukan Lintas Koleksi', 'findings': findings,
            'metrics': {'rules_checked': len(rows),
                        'broken_rules': sum(1 for r in rows if r['dangling']),
                        'empty_link_rules': len(empties)},
            'rows': sorted(rows, key=lambda x: (-x['dangling'], x['collection']))}


# ══════════════════════════════════════════════════════════════════════════════
# Laporan gabungan
# ══════════════════════════════════════════════════════════════════════════════
SEV_RANK = {'CRITICAL': 0, 'HIGH': 1, 'MED': 2, 'INFO': 3}


async def build_report(db) -> dict:
    a = await _section_a(db)
    b = await _section_b(db)
    c = await _section_c(db)
    d = await _section_d(db)
    e = await _section_e(db)
    sections = {'A': a, 'B': b, 'C': c, 'D': d, 'E': e}

    all_f = []
    for key, sec in sections.items():
        for f in sec['findings']:
            all_f.append({**f, 'section': key, 'section_title': sec['title']})
    all_f.sort(key=lambda f: SEV_RANK.get(f['severity'], 9))
    sev = Counter(f['severity'] for f in all_f)

    blocking = sev.get('CRITICAL', 0) + sev.get('HIGH', 0)
    verdict = 'HIJAU' if blocking == 0 else ('MERAH' if sev.get('CRITICAL') else 'KUNING')
    score = max(0, 100 - (sev.get('CRITICAL', 0) * 25 + sev.get('HIGH', 0) * 10
                          + sev.get('MED', 0) * 3))

    return {'generated_at': _now().isoformat(), 'verdict': verdict, 'score': score,
            'severity_counts': {'CRITICAL': sev.get('CRITICAL', 0), 'HIGH': sev.get('HIGH', 0),
                                'MED': sev.get('MED', 0), 'INFO': sev.get('INFO', 0)},
            'findings': all_f, 'sections': sections}


# ══════════════════════════════════════════════════════════════════════════════
# Perbaikan — aman, idempoten, bisa dipratinjau
# ══════════════════════════════════════════════════════════════════════════════
REPAIRS = {
    'relink_catalog_by_sku': {
        'label': 'Tautkan item katalog ke master FG lewat SKU yang sama',
        'explain': 'Hanya untuk item yang SKU-nya SAMA PERSIS dengan kode master FG. '
                   'Tidak ada penebakan nama.',
    },
    'refresh_catalog_stock_cache': {
        'label': 'Segarkan cache stok item katalog dari stok gudang',
        'explain': 'Menghitung ulang stok jual (semua lokasi kecuali karantina/blokir) '
                   'lewat SSOT core/catalog_stock.',
    },
    'relink_orders_from_bridge': {
        'label': 'Terapkan ulang Jembatan SKU ke seluruh pesanan',
        'explain': 'Jembatan adalah sumber kebenaran; pesanan hanya cerminannya.',
    },
    'normalize_fulfillment_status': {
        'label': 'Samakan kosakata status fulfillment (unallocated → pending_fulfillment)',
        'explain': 'Pesanan yang menurut platform PERLU DIKIRIM dimasukkan ke antrean gudang; '
                   'yang sudah selesai/dibatalkan TIDAK disentuh.',
    },
    'merge_duplicate_colors': {
        'label': 'Rapikan palet warna kembar (Putih PTH+WHT, Hitam HTM+BLK, …)',
        'explain': 'Kanonik = kode dengan rujukan terbanyak. Varian kembar yang kanoniknya '
                   'sudah ada dihapus; yang belum punya kanonik DIALIHKAN. Apa pun yang '
                   'punya stok/kartu stok/baris pesanan TIDAK disentuh dan dilaporkan.',
    },
    'ensure_variant_option_dimension': {
        'label': 'Aktifkan dimensi ke-3 varian (Opsi) + perluas index unik ke 4 sumbu',
        'explain': "Menyemai master opsi (Tidak Disebut/Pakai Karet/Tanpa Karet/Smook), "
                   "membekali varian lama option_code='NA' (SKU-nya TIDAK berubah), lalu "
                   'memindahkan index unik dari 3 sumbu ke 4 sumbu.',
    },
}


async def run_repair(db, action: str, *, dry_run: bool = True, user: dict = None) -> dict:
    if action not in REPAIRS:
        return {'ok': False, 'status': 400,
                'message': f"Perbaikan '{action}' tidak dikenal. Pilihan: {', '.join(REPAIRS)}"}

    if action == 'relink_catalog_by_sku':
        fg_by_code = {}
        async for m in db[MATERIALS].find({'type': 'fg'}, {'_id': 0, 'id': 1, 'code': 1, 'sku': 1}):
            for k in (m.get('code'), m.get('sku')):
                if k:
                    fg_by_code[str(k).upper()] = m
        changed = []
        async for i in db[ITEMS].find({'$or': [{'fg_material_id': None},
                                               {'fg_material_id': {'$exists': False}}]},
                                      {'_id': 0, 'id': 1, 'sku': 1, 'variant_sku': 1, 'name': 1}):
            key = str(i.get('variant_sku') or i.get('sku') or '').strip().upper()
            fg = fg_by_code.get(key)
            if not fg:
                continue
            changed.append({'item_id': i['id'], 'sku': key, 'name': i.get('name'),
                            'fg_material_id': fg['id']})
            if not dry_run:
                await db[ITEMS].update_one({'id': i['id']},
                                           {'$set': {'fg_material_id': fg['id'],
                                                     'material_id': fg['id'],
                                                     'fg_code': fg.get('code') or key,
                                                     'updated_at': _now()}})
        return {'ok': True, 'action': action, 'dry_run': dry_run, 'affected': len(changed),
                'samples': changed[:20],
                'message': (('PRATINJAU — ' if dry_run else '')
                            + f'{len(changed)} item katalog ditautkan lewat SKU identik.')}

    if action == 'refresh_catalog_stock_cache':
        from core import catalog_stock as cstock
        blocked = await cstock.blocked_location_ids(db)
        changed = []
        async for i in db[ITEMS].find({}, {'_id': 0}):
            res = await cstock.item_sellable(db, i, blocked_locs=blocked)
            if not res.get('fg_material_id'):
                continue
            before = _f(i.get('stock_quantity'))
            after = _f(res.get('available'))
            if abs(before - after) < 0.001:
                continue
            changed.append({'item_id': i['id'], 'sku': i.get('sku'), 'name': i.get('name'),
                            'before': before, 'after': after})
            if not dry_run:
                await db[ITEMS].update_one(
                    {'id': i['id']},
                    {'$set': cstock.cache_patch(res, i.get('stock_alert_threshold', 10))})
        return {'ok': True, 'action': action, 'dry_run': dry_run, 'affected': len(changed),
                'samples': changed[:20],
                'message': (('PRATINJAU — ' if dry_run else '')
                            + f'{len(changed)} cache stok item katalog disegarkan.')}

    if action == 'relink_orders_from_bridge':
        from core import sku_bridge
        if dry_run:
            n = await db['marketing_sku_bridge'].count_documents({'active': {'$ne': False}})
            affected = 0
            async for b in db['marketing_sku_bridge'].find({'active': {'$ne': False}},
                                                          {'_id': 0, 'platform_sku_id': 1}):
                affected += await db[ORDERS].count_documents(
                    {'items.platform_sku_id': b['platform_sku_id']})
            return {'ok': True, 'action': action, 'dry_run': True, 'affected': affected,
                    'message': f'PRATINJAU — {n} pemetaan akan diterapkan ke {affected} pesanan.'}
        res = await sku_bridge.relink_orders(db)
        return {'ok': True, 'action': action, 'dry_run': False,
                'affected': res['orders_updated'], 'message': res['message']}

    if action == 'normalize_fulfillment_status':
        from core import fulfillment_status as fs
        plan = Counter()
        samples = []
        n = 0
        async for o in db[ORDERS].find(
                {'fulfillment_status': {'$in': ['unallocated', 'pending', '', None]}},
                {'_id': 0, 'id': 1, 'order_id': 1, 'status': 1, 'fulfillment_status': 1}):
            want, reason = fs.initial_status(o)
            if want == fs.canon(o.get('fulfillment_status')) and o.get('fulfillment_status') == want:
                continue
            plan[want] += 1
            n += 1
            if len(samples) < 20:
                samples.append({'order_id': o.get('order_id'), 'from': o.get('fulfillment_status'),
                                'to': want, 'reason': reason})
            if not dry_run:
                await db[ORDERS].update_one(
                    {'id': o.get('id')} if o.get('id') else {'order_id': o.get('order_id')},
                    {'$set': {'fulfillment_status': want,
                              'fulfillment_status_normalized_at': _now(),
                              'fulfillment_status_normalized_reason': reason}})
        return {'ok': True, 'action': action, 'dry_run': dry_run, 'affected': n,
                'plan': dict(plan), 'samples': samples,
                'message': (('PRATINJAU — ' if dry_run else '')
                            + f'{n} pesanan disamakan kosakatanya: '
                            + ', '.join(f'{k}={v}' for k, v in plan.items()))}

    if action == 'merge_duplicate_colors':
        from core import variant_identity as vi
        res = await vi.merge_duplicate_colors(db, dry_run=dry_run, user=user)
        affected = (sum(d['to_delete'] + d['to_repoint']
                        for g in res['groups'] for d in g['duplicates'])
                    if dry_run else res['variants_deleted'] + res['variants_repointed'])
        return {'ok': True, 'action': action, 'dry_run': dry_run, 'affected': affected,
                'groups': res['groups'], 'blocked': res['blocked'],
                'samples': [{'group': g['group'], 'canonical': g['canonical']['code'],
                             'duplicates': [d['code'] for d in g['duplicates']]}
                            for g in res['groups'][:20]],
                'message': res['message']}

    if action == 'ensure_variant_option_dimension':
        from core import variant_identity as vi
        if dry_run:
            n = await db[VARIANTS].count_documents({'$or': [
                {'option_code': {'$exists': False}}, {'option_code': {'$in': [None, '']}}]})
            info = await db[VARIANTS].index_information()
            return {'ok': True, 'action': action, 'dry_run': True, 'affected': n,
                    'message': (f'PRATINJAU — {n} varian akan dibekali option_code="NA" '
                                '(SKU tidak berubah); index unik '
                                + ('sudah 4 sumbu.'
                                   if 'model_size_color_option_unique' in info
                                   else 'dipindahkan dari 3 sumbu ke 4 sumbu.'))}
        res = await vi.ensure_all_masters(db, user=user)
        return {'ok': True, 'action': action, 'dry_run': False,
                'affected': res['index']['variants_backfilled'], 'detail': res,
                'message': (f"{res['index']['variants_backfilled']} varian dibekali kolom Opsi; "
                            f"{res['options']['created']} opsi & {res['sizes']['created']} ukuran "
                            f"disemai; index unik 4 sumbu "
                            f"{'dipasang' if res['index']['legacy_index_dropped'] else 'sudah ada'}.")}

    return {'ok': False, 'status': 400, 'message': 'Perbaikan tidak terimplementasi.'}
