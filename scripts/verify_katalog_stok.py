#!/usr/bin/env python3
"""verify_katalog_stok.py — gate **INV-KATALOG** (KT-1 … KT-10).

Kenapa gate ini ada (semua pernah TERBUKTI di repo ini):
  * `sync-from-wms` mengabaikan `reserved_quantity` ⇒ stok katalog di-set LEBIH
    BESAR daripada yang tersedia ⇒ **OVERSELLING** (5000 vs 4999 · 300 vs 277).
  * Item katalog baru dari FG **selalu lahir stok 0** (lokasi "default" salah) ⇒
    produk baru tampak habis ⇒ kehilangan penjualan tanpa pesan error.
  * Tiga pintu punya tiga rumus ⇒ dua tombol menjawab beda, tak ada yang tahu
    mana yang benar.
⇒ ini gate UANG, bukan gate gaya kode.

Invarian:
  KT-1  `from-fg`, `sync-fg-stock`, `sync-from-wms` → angka IDENTIK
  KT-2  Item baru dari FG lahir dengan stok jual SEBENARNYA (bukan 0)
  KT-3  Stok katalog TIDAK boleh > (on-hand − reserved) ⇒ overselling mustahil
  KT-4  Nol pembaca `qty` MENTAH di jalur stok katalog (wajib `read_qty`)
  KT-5  `sync-from-wms` menyentuh SEMUA item tertaut (termasuk lewat `variant_sku`)
  KT-6  Ubah nama/kategori/berat master ⇒ item katalog ikut berubah
  KT-7  FG milik model NON-AKTIF tidak bisa ditambahkan ke katalog (400)
  KT-8  Nonaktifkan model/varian ⇒ item katalog dinonaktifkan + daftar terdampak (K-9a)
  KT-9  POST /api/marketing/orders tanpa tautan / SKU tak dikenal ⇒ 400
  KT-10 Nol item katalog YATIM (menunjuk FG yang sudah tidak ada) — seluruh DB
  KT-11 Nol order batal/retur di SELURUH DB yang masih menggenggam reservasi
        (+ self-test: gate WAJIB merah pada pelanggaran sintetis)
  KT-12 `POST /bulk-status` batal ⇒ reservasi SEMUA order dilepas (F10)
  KT-13 `DELETE /orders/{id}` ⇒ reservasi dilepas (tidak meninggalkan stok hantu)
  KT-14 Order `cancelled` tidak bisa dihidupkan lagi ke `new` (400) — anti-overselling
  KT-15 Nol penulis `marketing_orders.status` di luar SSOT `core/order_status`

Semua artefak uji berpenanda `INVKTL` dan DIHAPUS di akhir (jejak = 0).

Pakai::  python3 scripts/verify_katalog_stok.py
"""
from __future__ import annotations

import ast
import os
import sys
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, 'backend'))

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

from core import order_status as _ostat  # noqa: E402  (SSOT definisi "bocor" — F10)

BASE = os.environ.get('GATE_BASE', 'http://localhost:8001')
MARK = 'INVKTL'
G, R, Y, X, BOLD, DIM = ('\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m', '\033[2m')

db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                 )[os.environ.get('DB_NAME', 'test_database')]
S = requests.Session()
OK: list = []
BAD: list = []


def chk(cond, code, claim, detail=''):
    if cond:
        OK.append(code)
        print(f'  {G}✓ {code}{X} {claim}' + (f'  {DIM}{detail}{X}' if detail else ''))
    else:
        BAD.append(code)
        print(f'  {R}✗ {code} {claim}{X}' + (f'  {Y}→ {detail}{X}' if detail else ''))
    return cond


def api(method, path, **kw):
    kw.setdefault('timeout', 60)
    return S.request(method, f'{BASE}{path}', **kw)


def j(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


def set_stock(material_id, location_id, qty, reserved=0.0, **flags):
    doc = {'qty': float(qty), 'total_qty': float(qty), 'quantity': float(qty),
           'reserved_quantity': float(reserved),
           'available_quantity': float(qty) - float(reserved),
           'ownership': 'cv_da', 'inventory_category': 'fg_internal',
           'gate_marker': MARK, **flags}
    db.rahaza_material_stock.update_one(
        {'material_id': material_id, 'location_id': location_id},
        {'$set': doc, '$setOnInsert': {'id': str(uuid.uuid4())}}, upsert=True)


def loc(suffix, **flags):
    code = f'{MARK}-LOC-{suffix}'
    d = db.rahaza_locations.find_one({'code': code}, {'_id': 0, 'id': 1})
    if d:
        return d['id']
    lid = str(uuid.uuid4())
    db.rahaza_locations.insert_one({'id': lid, 'code': code, 'name': f'{MARK} {suffix}',
                                    'type': 'warehouse', 'active': True, **flags})
    return lid


def cleanup():
    fg_ids = [m['id'] for m in db.rahaza_materials.find(
        {'$or': [{'gate_marker': MARK}, {'code': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]
    model_ids = [m['id'] for m in db.rahaza_models.find(
        {'$or': [{'gate_marker': MARK}, {'code': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]
    cat_ids = [c['id'] for c in db.marketing_catalogs.find(
        {'name': {'$regex': f'^{MARK}'}}, {'_id': 0, 'id': 1})]
    # 2026-08-13 — akun uji gate ini dipakai membuat PESANAN, dan sejak F2/F5 setiap
    # perubahan status pesanan ikut menghitung ulang REKAP HARIAN turunan. Kalau
    # akunnya dibuang tanpa membuang rekap turunannya, yang tertinggal adalah
    # dokumen rekap ber-`account_id` YATIM — dan gate MKS-2 (INV-MKTSCOPE) akan
    # MERAH karena sebab yang dibuat oleh gate lain, bukan oleh produk.
    acc_ids = [a['id'] for a in db.marketing_platform_accounts.find(
        {'account_code': {'$regex': f'^{MARK}'}}, {'_id': 0, 'id': 1})]
    for coll, q in (
        ('marketing_orders', {'$or': [{'gate_marker': MARK},
                                      {'customer_name': {'$regex': MARK}}]}),
        ('marketing_sales_data', {'$or': [{'account_id': {'$in': acc_ids}},
                                          {'account_name': {'$regex': f'^{MARK}'}}]}),
        ('marketing_catalog_items', {'$or': [{'gate_marker': MARK},
                                             {'fg_material_id': {'$in': fg_ids}},
                                             {'catalog_id': {'$in': cat_ids}},
                                             {'sku': {'$regex': f'^{MARK}'}}]}),
        ('marketing_stock_syncs', {'catalog_id': {'$in': cat_ids}}),
        ('marketing_catalogs', {'name': {'$regex': f'^{MARK}'}}),
        ('marketing_platform_accounts', {'account_code': {'$regex': f'^{MARK}'}}),
        ('rahaza_material_stock', {'$or': [{'gate_marker': MARK},
                                           {'material_id': {'$in': fg_ids}}]}),
        ('rahaza_stock_ledger', {'material_id': {'$in': fg_ids}}),
        ('rahaza_materials', {'id': {'$in': fg_ids}}),
        ('rahaza_model_variants', {'model_id': {'$in': model_ids}}),
        ('rahaza_models', {'id': {'$in': model_ids}}),
        ('rahaza_locations', {'code': {'$regex': f'^{MARK}-LOC-'}}),
        ('wh_pending_inbound', {'material_id': {'$in': fg_ids}}),
    ):
        try:
            db[coll].delete_many(q)
        except Exception:  # noqa: BLE001
            pass


def raw_qty_readers() -> list:
    """KT-4 — diperiksa lewat AST (komentar/docstring tidak dihitung)."""
    bad = []
    for rel in ('backend/routes/marketing_catalog_stock.py',
                'backend/routes/marketing_catalog_items.py',
                'backend/core/catalog_stock.py'):
        p = os.path.join(APP, rel)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as fh:
            tree = ast.parse(fh.read())
        for n in ast.walk(tree):
            if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                    and n.func.attr == 'get' and n.args
                    and isinstance(n.args[0], ast.Constant)
                    and n.args[0].value in ('qty', 'total_qty')):
                bad.append(f'{rel}:{n.lineno}')
    return bad


def rogue_status_writers() -> list:
    """KT-15 — siapa pun yang menulis `marketing_orders.status` DI LUAR SSOT.

    F10: status order + siklus reservasi punya SATU penulis
    (`backend/core/order_status.py::apply_status`). Gate ini memindai SELURUH
    `backend/` lewat AST: setiap ``db.marketing_orders.update_one/update_many``
    yang membawa kunci ``'status'`` di dalam ``$set`` dianggap pelanggaran.

    Kenapa AST dan bukan grep: pola ini pernah lolos justru karena tersebar di
    berkas yang tidak dicurigai (`marketing_webhooks.py`, `dewi_online_orders.py`).
    Yang dikecualikan hanya modul SSOT itu sendiri + alat uji/migrasi.
    """
    allow_prefix = ('core/order_status.py', 'migrations/', 'scripts/')
    bad = []
    for root, _dirs, files in os.walk(os.path.join(APP, 'backend')):
        if any(seg in root for seg in ('__pycache__', '_archive', 'node_modules')):
            continue
        for fn in files:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(root, fn)
            rel = os.path.relpath(p, os.path.join(APP, 'backend'))
            if rel.startswith(allow_prefix) or 'test' in rel:
                continue
            try:
                with open(p, encoding='utf-8') as fh:
                    tree = ast.parse(fh.read())
            except (SyntaxError, UnicodeDecodeError):
                continue
            for n in ast.walk(tree):
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr in ('update_one', 'update_many')):
                    continue
                # penerima harus ...marketing_orders
                recv = n.func.value
                name = getattr(recv, 'attr', None) or getattr(recv, 'id', None)
                if name != 'marketing_orders':
                    if not (isinstance(recv, ast.Subscript)
                            and isinstance(getattr(recv, 'slice', None), ast.Constant)
                            and recv.slice.value == 'marketing_orders'):
                        continue
                # cari literal 'status' di dalam $set / $setOnInsert
                for sub in ast.walk(n):
                    if not isinstance(sub, ast.Dict):
                        continue
                    for k, v in zip(sub.keys, sub.values):
                        if (isinstance(k, ast.Constant) and k.value in ('$set', '$setOnInsert')
                                and isinstance(v, ast.Dict)):
                            for kk in v.keys:
                                if isinstance(kk, ast.Constant) and kk.value == 'status':
                                    bad.append(f'backend/{rel}:{n.lineno}')
    return sorted(set(bad))


def main() -> int:  # noqa: C901
    print(f'{BOLD}INV-KATALOG — satu rumus stok jual, anti-overselling, tautan order{X}')

    # KT-4 & KT-10 tidak butuh login / tidak menyentuh data
    chk(not raw_qty_readers(), 'KT-4',
        'nol pembaca `qty` MENTAH di jalur stok katalog (wajib read_qty)',
        f'pelanggar: {raw_qty_readers()}')
    fg_all = {m['id'] for m in db.rahaza_materials.find({'type': 'fg'}, {'_id': 0, 'id': 1})}
    orphan = [i.get('sku') for i in db.marketing_catalog_items.find(
        {'fg_material_id': {'$nin': [None, '']}}, {'_id': 0, 'sku': 1, 'fg_material_id': 1})
        if i['fg_material_id'] not in fg_all]
    chk(not orphan, 'KT-10', 'nol item katalog yatim (menunjuk FG yang tak ada)',
        f'{orphan[:10]}')

    # ── KT-11 — GATE UANG: pemindaian SELURUH DB (bukan hanya data uji) ───────
    # Order yang sudah `cancelled`/`returned` TIDAK boleh masih menggenggam
    # reservasi: barangnya ada di gudang tetapi sistem menolak menjualnya, dan
    # tidak ada dokumen yang menjelaskan kenapa. Perbaiki dengan
    # `python3 backend/migrations/repair_leaked_order_reservations.py --execute`.
    leaked = list(db.marketing_orders.find(
        _ostat.leak_query(), {'_id': 0, 'order_id': 1, 'status': 1, 'reserved_qty': 1}))
    chk(not leaked, 'KT-11',
        'nol order batal/retur di SELURUH DB yang masih menggenggam reservasi stok',
        f'bocor {len(leaked)}: {[x.get("order_id") for x in leaked[:8]]} '
        '→ jalankan backend/migrations/repair_leaked_order_reservations.py --execute')

    # ── KT-15 — nol penulis status order di luar SSOT (AST, seluruh backend) ──
    rogue = rogue_status_writers()
    chk(not rogue, 'KT-15',
        'nol penulis `marketing_orders.status` di luar SSOT core/order_status',
        f'pelanggar: {rogue}')

    r = S.post(f'{BASE}/api/auth/login', timeout=30,
               json={'email': 'admin@garment.com', 'password': 'Admin@123'})
    if r.status_code != 200:
        print(f'  {R}login gagal {r.status_code}{X}')
        return 2
    S.headers.update({'Authorization': f"Bearer {j(r).get('token') or j(r).get('access_token')}"})

    cleanup()
    try:
        cats = (j(api('GET', '/api/rahaza/product-categories')) or {}).get('categories', [])
        colors = j(api('GET', '/api/rahaza/colors'))
        colors = colors if isinstance(colors, list) else colors.get('colors', [])
        sizes = j(api('GET', '/api/rahaza/sizes'))
        sizes = sizes if isinstance(sizes, list) else sizes.get('sizes', [])
        if not (cats and colors and sizes):
            chk(False, 'KT-0', 'prasyarat master (kategori/warna/ukuran) tersedia')
            return 1

        rm = api('POST', '/api/rahaza/models',
                 json={'code': f'{MARK}-M1', 'name': f'{MARK} Produk',
                       'category_id': cats[0]['id'], 'base_hpp': 10000,
                       'retail_price': 90000, 'weight_gram': 200})
        model = j(rm)
        if not chk(bool(model.get('id')), 'KT-0', 'produk uji dibuat',
                   f'HTTP {rm.status_code} {str(model)[:120]}'):
            return 1
        db.rahaza_models.update_one({'id': model['id']}, {'$set': {'gate_marker': MARK}})
        api('POST', f"/api/rahaza/models/{model['id']}/variants/generate",
            json={'color_ids': [colors[0]['id']], 'size_ids': [sizes[0]['id']]})
        v = db.rahaza_model_variants.find_one({'model_id': model['id']}, {'_id': 0}) or {}
        fg = db.rahaza_materials.find_one({'type': 'fg', 'code': v.get('sku')}, {'_id': 0}) or {}
        if not chk(bool(fg.get('id')), 'KT-0', 'FG uji lahir dari varian', v.get('sku', '')):
            return 1
        db.rahaza_materials.update_one({'id': fg['id']}, {'$set': {'gate_marker': MARK}})

        # stok: 200 (−50 reserved) boleh dijual · 80 karantina · 60 blokir
        set_stock(fg['id'], loc('OK'), 200, 50)
        set_stock(fg['id'], loc('QRT', quarantine=True), 80, 0, quarantine=True)
        set_stock(fg['id'], loc('BLK', blocked=True), 60, 0, blocked=True)
        sellable = 150.0

        acc = (j(api('POST', '/api/marketing/accounts',
                     json={'account_code': f'{MARK}-ACC', 'account_name': f'{MARK} akun',
                           'platform': 'shopee'})) or {}).get('account') or {}
        cat_doc = (j(api('POST', '/api/marketing/catalogs',
                         json={'account_id': acc.get('id'), 'name': f'{MARK} Katalog',
                               'platform': 'shopee'})) or {}).get('catalog') or {}
        cid = cat_doc.get('id')

        ri = api('POST', f'/api/marketing/catalogs/{cid}/items/from-fg',
                 json={'fg_material_id': fg['id'], 'price': 0})
        item = (j(ri) or {}).get('item') or {}
        if item.get('id'):
            db.marketing_catalog_items.update_one({'id': item['id']},
                                                  {'$set': {'gate_marker': MARK}})
        v_create = float(item.get('stock_quantity') or -1)
        chk(abs(v_create - sellable) < 0.001, 'KT-2',
            'item baru dari FG lahir dengan stok jual sebenarnya (bukan 0)',
            f'{v_create} vs {sellable}')

        v_item = float(j(api('PUT', f"/api/marketing/catalogs/{cid}/items/{item['id']}/sync-fg-stock")
                         ).get('stock_quantity') or -1)
        api('POST', f'/api/marketing/catalogs/{cid}/sync-from-wms')
        v_wms = float((db.marketing_catalog_items.find_one({'id': item['id']}, {'_id': 0}) or {}
                       ).get('stock_quantity') or -1)
        chk(abs(v_create - v_item) < 0.001 and abs(v_item - v_wms) < 0.001, 'KT-1',
            'ketiga pintu stok menghasilkan angka IDENTIK',
            f'create={v_create} sync-item={v_item} sync-wms={v_wms}')
        chk(v_wms <= sellable + 0.001, 'KT-3',
            'stok katalog TIDAK melebihi (on-hand − reserved) ⇒ overselling mustahil',
            f'{v_wms} <= {sellable} (140 unit karantina/blokir dikecualikan)')

        # KT-5 — item bertaut VARIAN tanpa material_id tetap ikut sinkron
        rv = api('POST', f'/api/marketing/catalogs/{cid}/items',
                 json={'sku': f'{MARK}-VITEM', 'name': f'{MARK} item varian',
                       'variant_id': v['id'], 'price': 50000})
        vitem = (j(rv) or {}).get('item') or {}
        if vitem.get('id'):
            db.marketing_catalog_items.update_one(
                {'id': vitem['id']}, {'$set': {'gate_marker': MARK, 'stock_quantity': 0.0}})
            api('POST', f'/api/marketing/catalogs/{cid}/sync-from-wms')
            got = db.marketing_catalog_items.find_one({'id': vitem['id']}, {'_id': 0}) or {}
            chk(abs(float(got.get('stock_quantity') or -1) - sellable) < 0.001, 'KT-5',
                '`sync-from-wms` ikut menyentuh item bertaut varian',
                f"stock_quantity={got.get('stock_quantity')}")
        else:
            chk(False, 'KT-5', 'item bertaut varian dibuat', f'HTTP {rv.status_code}')

        # KT-9 — order wajib tautan master
        # F14 (2026-08-11): order WAJIB membawa `account_id` yang sah — lihat
        # gate INV-MKTSCOPE. Fixture di sini menyertakannya karena yang diuji
        # adalah siklus reservasi stok, bukan penegakan lingkup toko.
        base_order = {'platform': 'shopee', 'customer_name': f'{MARK} pembeli',
                      'account_id': acc.get('id'),
                      'quantity': 1, 'price_final': 90000}
        r_no = api('POST', '/api/marketing/orders', json={**base_order, 'sku_id': ''})
        r_bad = api('POST', '/api/marketing/orders',
                    json={**base_order, 'sku_id': 'SKU-NGAWUR-XYZ'})
        chk(r_no.status_code == 400 and r_bad.status_code == 400, 'KT-9',
            'order tanpa tautan / SKU tak dikenal ⇒ 400',
            f'tanpa={r_no.status_code} ngawur={r_bad.status_code}')
        for rr in (r_no, r_bad):
            if rr.status_code in (200, 201):
                db.marketing_orders.delete_one({'id': j(rr).get('id')})

        # ══════════════════════════════════════════════════════════════════════
        # F10 — SIKLUS RESERVASI: setiap jalur yang mematikan order WAJIB melepas
        # stoknya. Ketiga kode di bawah pernah MERAH sungguhan (POC
        # `test_core_order_status_reservation.py`): stok jual 25 → order 2 pcs →
        # 23 → bulk-batal → tetap 23 SELAMANYA, tanpa dokumen yang menjelaskan.
        # ══════════════════════════════════════════════════════════════════════
        ok_loc = loc('OK')

        def reserved_now() -> float:
            row = db.rahaza_material_stock.find_one(
                {'material_id': fg['id'], 'location_id': ok_loc}, {'_id': 0}) or {}
            try:
                return float(row.get('reserved_quantity') or 0)
            except (TypeError, ValueError):
                return -1.0

        def mk_order(qty: int, tag: str):
            rr = api('POST', '/api/marketing/orders', json={
                'platform': 'shopee', 'customer_name': f'{MARK} {tag}',
                'account_id': acc.get('id'),
                'items': [{'catalog_item_id': item['id'], 'qty': qty, 'price': 90000}]})
            return rr, (j(rr) or {}).get('id')

        base_res = reserved_now()          # 50 dari set_stock(..., 200, 50)

        # KT-12 — bulk batal melepas reservasi SEMUA order
        r1, o1 = mk_order(2, 'bulk1')
        r2, o2 = mk_order(3, 'bulk2')
        res_after = reserved_now()
        rbulk = api('POST', '/api/marketing/orders/bulk-status',
                    json={'order_ids': [x for x in (o1, o2) if x], 'status': 'cancelled'})
        res_bulk = reserved_now()
        chk(r1.status_code == 201 and r2.status_code == 201
            and abs(res_after - (base_res + 5)) < 0.001
            and abs(res_bulk - base_res) < 0.001, 'KT-12',
            'bulk batal ⇒ reservasi SEMUA order dilepas (stok jual kembali utuh)',
            f'reserved {base_res} → {res_after} → {res_bulk} (harus kembali {base_res}) '
            f'· HTTP {rbulk.status_code}')

        # KT-11 (self-test) — pelanggaran SINTETIS harus terdeteksi pemindaian DB
        _synth_ok = False
        if o1:
            db.marketing_orders.update_one(
                {'id': o1}, {'$set': {'status': 'cancelled', 'stock_reserved': True,
                                      'reserved_qty': 2.0,
                                      'reserved_rows': [{'stock_id': 'INVKTL-FAKE-ROW',
                                                         'qty_reserved': 2.0}]}})
            _synth_ok = db.marketing_orders.count_documents(_ostat.leak_query()) > 0
            db.marketing_orders.update_one(
                {'id': o1}, {'$set': {'stock_reserved': False, 'reserved_qty': 0.0,
                                      'reserved_rows': []}})
        chk(_synth_ok, 'KT-11-SELF',
            'pemindaian kebocoran TERBUKTI mendeteksi pelanggaran sintetis',
            'kalau ini hijau, KT-11 di bawah benar-benar berarti')
        db.marketing_orders.delete_many({'customer_name': {'$regex': f'^{MARK}'}})

        # KT-13 — HAPUS order melepas reservasi (bukan stok hantu)
        r3, o3 = mk_order(2, 'delete')
        res_before_del = reserved_now()
        rdel = api('DELETE', f'/api/marketing/orders/{o3}')
        res_after_del = reserved_now()
        chk(r3.status_code == 201 and rdel.status_code == 200
            and abs(res_before_del - (base_res + 2)) < 0.001
            and abs(res_after_del - base_res) < 0.001, 'KT-13',
            'HAPUS order ⇒ reservasi dilepas (tidak meninggalkan stok hantu)',
            f'reserved {base_res} → {res_before_del} → {res_after_del} · HTTP {rdel.status_code}')

        # KT-14 — order batal TIDAK boleh dihidupkan lagi (anti-overselling)
        r4, o4 = mk_order(2, 'transition')
        api('PATCH', f'/api/marketing/orders/{o4}/status', json={'status': 'cancelled'})
        rrev = api('PATCH', f'/api/marketing/orders/{o4}/status', json={'status': 'new'})
        doc4 = db.marketing_orders.find_one({'id': o4}, {'_id': 0}) or {}
        chk(rrev.status_code == 400 and doc4.get('status') == 'cancelled', 'KT-14',
            "order batal tidak bisa dihidupkan lagi ke 'new' (400) ⇒ stok tak terjual dua kali",
            f"HTTP {rrev.status_code} status={doc4.get('status')}")
        db.marketing_orders.delete_many({'customer_name': {'$regex': f'^{MARK}'}})
        chk(abs(reserved_now() - base_res) < 0.001, 'KT-12b',
            'setelah semua uji siklus order, reservasi kembali ke angka semula',
            f'{reserved_now()} vs {base_res}')

        # KT-6 — ubah master ⇒ item katalog ikut berubah
        api('PUT', f"/api/rahaza/models/{model['id']}",
            json={'category_id': cats[-1]['id'], 'weight_gram': 321})
        it2 = db.marketing_catalog_items.find_one({'id': item['id']}, {'_id': 0}) or {}
        chk(it2.get('category_id') == cats[-1]['id']
            and float(it2.get('weight_gram') or 0) == 321, 'KT-6',
            'ubah kategori/berat master ⇒ item katalog ikut berubah',
            f"cat={it2.get('category_code')} berat={it2.get('weight_gram')}")

        # KT-8 — nonaktifkan model ⇒ item katalog nonaktif + daftar terdampak
        rd = api('DELETE', f"/api/rahaza/models/{model['id']}")
        body = j(rd)
        affected = body.get('affected_catalog_items') or []
        it3 = db.marketing_catalog_items.find_one({'id': item['id']}, {'_id': 0}) or {}
        chk(rd.status_code == 200 and it3.get('is_active') is False and len(affected) >= 1,
            'KT-8', 'nonaktifkan produk ⇒ item katalog nonaktif + daftar terdampak (K-9a)',
            f"HTTP {rd.status_code} is_active={it3.get('is_active')} terdampak={len(affected)}")

        # KT-7 — FG milik model non-aktif tidak bisa masuk katalog
        db.marketing_catalog_items.delete_many({'catalog_id': cid, 'fg_material_id': fg['id']})
        r7 = api('POST', f'/api/marketing/catalogs/{cid}/items/from-fg',
                 json={'fg_material_id': fg['id'], 'price': 1000})
        chk(r7.status_code == 400, 'KT-7',
            'FG milik model NON-AKTIF tidak bisa ditambahkan ke katalog (400)',
            f'HTTP {r7.status_code}')
    finally:
        cleanup()
        left = (db.marketing_catalogs.count_documents({'name': {'$regex': f'^{MARK}'}})
                + db.rahaza_models.count_documents({'code': {'$regex': f'^{MARK}'}})
                + db.rahaza_locations.count_documents({'code': {'$regex': f'^{MARK}-LOC-'}}))
        chk(left == 0, 'KT-CLEAN', 'jejak data uji gate = 0', f'{left} sisa')

    total = len(OK) + len(BAD)
    print(f'\n  INV-KATALOG: {G if not BAD else R}{BOLD}{len(OK)}/{total} OK{X}'
          + (f'  {R}{len(BAD)} FAIL: {BAD}{X}' if BAD else f'  {G}— HIJAU{X}'))
    return 1 if BAD else 0


if __name__ == '__main__':
    sys.exit(main())
