#!/usr/bin/env python3
"""verify_master_produk.py — gate **INV-PRODUK** (PR-1 … PR-10).

Satu pertanyaan yang harus dijawab gate ini:
  “Kalau pemeriksaan ini hilang, apakah UANG atau DATA bisa rusak tanpa ada yang tahu?”

Jawabannya YA untuk semuanya:
  * **kode produk kembar** (T1) → dua master untuk satu barang ⇒ stok/BOM/laporan pecah
  * **kategori teks bebas** (P3) → grouping katalog marketing tidak bisa dipercaya
  * **kategori basi** (P2b) → laporan per-kategori berbohong dengan sopan
  * **HPP 0 untuk produk manual** (P1) → margin katalog mustahil dihitung
  * **berat FG 0** (P4) → biaya kirim salah
  * **format SKU berubah** → barcode & riwayat stok patah

Invarian:
  PR-1  POST /api/rahaza/models dengan `code` yang sudah ada ⇒ 409 — termasuk bila
        dokumen lama HANYA punya `status` (inilah bug T1 yang terbukti)
  PR-2  NOL dokumen `rahaza_models` tanpa field `active`
  PR-3  NOL `code` kembar di seluruh koleksi
  PR-4  `category_id` tak dikenal / non-aktif ⇒ 400
  PR-5  Ubah kategori/berat master ⇒ FG **dan** item katalog tertaut ikut berubah
  PR-6  Produk tanpa HPP R&D tetapi punya `base_hpp` ⇒ dipakai, `hpp_source='manual'`
  PR-7  `weight_gram` master benar-benar sampai ke FG
  PR-8  Kategori yang masih dipakai TIDAK bisa dinonaktifkan (409)
  PR-9  GET /api/dashboard menghitung produk hasil promosi R&D
  PR-10 Format SKU tetap `{MODEL}-{WARNA}-{SIZE}` (K-1A) ⇒ INV-RND-3 tetap hijau

Semua artefak uji berpenanda `INVPRD` dan DIHAPUS di akhir (jejak = 0).

Pakai::  python3 scripts/verify_master_produk.py
"""
from __future__ import annotations

import os
import sys
import uuid

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(APP, 'backend'))

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

BASE = os.environ.get('GATE_BASE', 'http://localhost:8001')
MARK = 'INVPRD'
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


def cleanup():
    fg_ids = [m['id'] for m in db.rahaza_materials.find(
        {'$or': [{'gate_marker': MARK}, {'code': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]
    model_ids = [m['id'] for m in db.rahaza_models.find(
        {'$or': [{'gate_marker': MARK}, {'code': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]
    for coll, q in (
        ('marketing_catalog_items', {'$or': [{'gate_marker': MARK},
                                             {'fg_material_id': {'$in': fg_ids}},
                                             {'sku': {'$regex': f'^{MARK}'}}]}),
        ('marketing_catalogs', {'name': {'$regex': f'^{MARK}'}}),
        ('marketing_platform_accounts', {'account_code': {'$regex': f'^{MARK}'}}),
        ('rahaza_material_stock', {'material_id': {'$in': fg_ids}}),
        ('rahaza_stock_ledger', {'material_id': {'$in': fg_ids}}),
        ('rahaza_materials', {'id': {'$in': fg_ids}}),
        ('rahaza_model_variants', {'model_id': {'$in': model_ids}}),
        ('rahaza_models', {'id': {'$in': model_ids}}),
        ('rahaza_product_categories', {'gate_marker': MARK}),
        ('dewi_rnd_styles', {'style_code': {'$regex': f'^{MARK}'}}),
        ('wh_pending_inbound', {'material_id': {'$in': fg_ids}}),
    ):
        try:
            db[coll].delete_many(q)
        except Exception:  # noqa: BLE001
            pass


def main() -> int:
    print(f'{BOLD}INV-PRODUK — master produk: kode, kategori, HPP, berat, SKU{X}')
    r = S.post(f'{BASE}/api/auth/login', timeout=30,
               json={'email': 'admin@garment.com', 'password': 'Admin@123'})
    if r.status_code != 200:
        print(f'  {R}login gagal {r.status_code}{X}')
        return 2
    S.headers.update({'Authorization': f"Bearer {j(r).get('token') or j(r).get('access_token')}"})

    cleanup()  # sisa jalannya yang gagal sebelumnya

    try:
        # ── PR-2 / PR-3: invarian SELURUH DB (tanpa membuat data) ─────────────
        n_no_active = db.rahaza_models.count_documents({'active': {'$exists': False}})
        chk(n_no_active == 0, 'PR-2', 'nol `rahaza_models` tanpa field `active`',
            f'{n_no_active} dokumen — jalankan migrations/normalize_model_active.py')
        dups = list(db.rahaza_models.aggregate([
            {'$group': {'_id': {'$toUpper': '$code'}, 'n': {'$sum': 1}}},
            {'$match': {'n': {'$gt': 1}}}]))
        chk(not dups, 'PR-3', 'nol `code` produk kembar di seluruh koleksi',
            f'kembar: {[d["_id"] for d in dups]}')

        # ── prasyarat: kategori + warna + ukuran ────────────────────────────
        cats = (j(api('GET', '/api/rahaza/product-categories')) or {}).get('categories', [])
        if not chk(len(cats) >= 14, 'PR-0', 'master kategori produk ter-seed (K-2)',
                   f'{len(cats)} kategori'):
            return 1
        cat_a = next((c for c in cats if c.get('sku_prefix') == 'VST'), cats[0])
        cat_b = next((c for c in cats if c.get('id') != cat_a['id']), cats[-1])
        colors = j(api('GET', '/api/rahaza/colors'))
        colors = colors if isinstance(colors, list) else colors.get('colors', [])
        sizes = j(api('GET', '/api/rahaza/sizes'))
        sizes = sizes if isinstance(sizes, list) else sizes.get('sizes', [])
        if not (colors and sizes):
            chk(False, 'PR-0', 'master warna & ukuran tersedia')
            return 1

        # ── PR-1: duplikat kode ⇒ 409 (termasuk dokumen warisan tanpa `active`) ──
        code1 = f'{MARK}-A'
        r1 = api('POST', '/api/rahaza/models',
                 json={'code': code1, 'name': f'{MARK} Produk A', 'category_id': cat_a['id']})
        m1 = j(r1)
        db.rahaza_models.update_one({'id': m1.get('id')}, {'$set': {'gate_marker': MARK}})
        r2 = api('POST', '/api/rahaza/models',
                 json={'code': code1, 'name': 'kembar', 'category_id': cat_a['id']})
        chk(r2.status_code == 409, 'PR-1a', 'kode sama (dokumen aktif) ⇒ 409',
            f'HTTP {r2.status_code}')

        legacy_code = f'{MARK}-LEGACY'
        db.rahaza_models.insert_one({'id': str(uuid.uuid4()), 'code': legacy_code,
                                     'name': f'{MARK} warisan', 'status': 'active',
                                     'gate_marker': MARK})
        r3 = api('POST', '/api/rahaza/models',
                 json={'code': legacy_code, 'name': 'kembar', 'category_id': cat_a['id']})
        chk(r3.status_code == 409, 'PR-1b',
            'kode sama dgn dokumen warisan (hanya `status`) ⇒ 409', f'HTTP {r3.status_code}')
        if r3.status_code in (200, 201):
            db.rahaza_models.delete_many({'code': legacy_code,
                                          'gate_marker': {'$ne': MARK}})

        # ── PR-4: kategori tak dikenal / non-aktif ⇒ 400 ────────────────────
        r4 = api('POST', '/api/rahaza/models',
                 json={'code': f'{MARK}-BAD', 'name': 'x', 'category_id': 'tidak-ada'})
        chk(r4.status_code == 400, 'PR-4', '`category_id` tak dikenal ⇒ 400',
            f'HTTP {r4.status_code}')
        if r4.status_code in (200, 201):
            db.rahaza_models.delete_many({'code': f'{MARK}-BAD'})

        # ── K-1A + PR-6/PR-7/PR-10: produk kode otomatis + angka master ────────
        rm = api('POST', '/api/rahaza/models',
                 json={'name': f'{MARK} Produk Otomatis', 'category_id': cat_a['id'],
                       'base_hpp': 33000, 'retail_price': 149000, 'weight_gram': 275})
        model = j(rm)
        if not chk(rm.status_code in (200, 201) and model.get('id'), 'PR-K1A',
                   'kode produk dibuat OTOMATIS dari prefix kategori',
                   f'HTTP {rm.status_code} code={model.get("code")}'):
            return 1
        db.rahaza_models.update_one({'id': model['id']}, {'$set': {'gate_marker': MARK}})
        prefix = (cat_a.get('sku_prefix') or '').upper()
        chk((model.get('code') or '').startswith(f'{prefix}-'), 'PR-K1A2',
            f'kode berpola {{{prefix}}}-{{URUT}}', f"code={model.get('code')}")
        chk(model.get('hpp_source') == 'manual' and float(model.get('hpp') or 0) == 33000,
            'PR-6a', 'HPP manual (`base_hpp`) dipakai + sumbernya dilaporkan',
            f"hpp={model.get('hpp')} source={model.get('hpp_source')}")

        api('POST', f"/api/rahaza/models/{model['id']}/variants/generate",
            json={'color_ids': [colors[0]['id']], 'size_ids': [sizes[0]['id']]})
        v = db.rahaza_model_variants.find_one({'model_id': model['id']}, {'_id': 0}) or {}
        expect = f"{model['code']}-{colors[0]['code']}-{sizes[0]['code']}".upper()
        chk(v.get('sku') == expect, 'PR-10',
            'format SKU tetap {MODEL}-{WARNA}-{SIZE}', f"{v.get('sku')} vs {expect}")
        fg = db.rahaza_materials.find_one({'type': 'fg', 'code': v.get('sku')}, {'_id': 0}) or {}
        if fg:
            db.rahaza_materials.update_one({'id': fg['id']}, {'$set': {'gate_marker': MARK}})
        chk(float(fg.get('weight_gram') or 0) == 275, 'PR-7',
            '`weight_gram` master sampai ke FG', f"FG.weight_gram={fg.get('weight_gram')}")
        chk(float(fg.get('hpp') or 0) == 33000, 'PR-6b',
            'HPP manual mengalir ke FG (margin katalog bisa dihitung)',
            f"FG.hpp={fg.get('hpp')}")

        # ── PR-5: propagasi kategori/berat ke FG + ITEM KATALOG ──────────────
        acc = db.marketing_platform_accounts.find_one({'account_code': f'{MARK}-ACC'}, {'_id': 0})
        if not acc:
            acc = (j(api('POST', '/api/marketing/accounts',
                         json={'account_code': f'{MARK}-ACC', 'account_name': f'{MARK} akun',
                               'platform': 'shopee'})) or {}).get('account') or {}
        cat_doc = db.marketing_catalogs.find_one({'name': f'{MARK} Katalog'}, {'_id': 0})
        if not cat_doc:
            cat_doc = (j(api('POST', '/api/marketing/catalogs',
                             json={'account_id': acc.get('id'), 'name': f'{MARK} Katalog',
                                   'platform': 'shopee'})) or {}).get('catalog') or {}
        cid = cat_doc.get('id')
        item = {}
        if cid and fg:
            ri = api('POST', f'/api/marketing/catalogs/{cid}/items/from-fg',
                     json={'fg_material_id': fg['id'], 'price': 0})
            item = (j(ri) or {}).get('item') or {}
            if item.get('id'):
                db.marketing_catalog_items.update_one({'id': item['id']},
                                                      {'$set': {'gate_marker': MARK}})
        chk(bool(item.get('id')), 'PR-5.0', 'item katalog dibuat dari FG')
        chk(abs(float(item.get('harga_jual') or 0) - 149000) < 0.01, 'PR-K3a',
            'harga jual item terisi awal dari `retail_price` master (K-3a)',
            f"harga_jual={item.get('harga_jual')}")

        api('PUT', f"/api/rahaza/models/{model['id']}",
            json={'category_id': cat_b['id'], 'weight_gram': 480})
        fg2 = db.rahaza_materials.find_one({'id': fg.get('id')}, {'_id': 0}) or {}
        it2 = db.marketing_catalog_items.find_one({'id': item.get('id')}, {'_id': 0}) or {}
        chk(fg2.get('category_id') == cat_b['id'] and float(fg2.get('weight_gram') or 0) == 480,
            'PR-5a', 'perubahan kategori & berat master ⇒ FG ikut berubah',
            f"FG cat={fg2.get('category_code')} berat={fg2.get('weight_gram')}")
        chk(it2.get('category_id') == cat_b['id'] and float(it2.get('weight_gram') or 0) == 480,
            'PR-5b', 'perubahan kategori & berat master ⇒ ITEM KATALOG ikut berubah',
            f"item cat={it2.get('category_code')} berat={it2.get('weight_gram')}")

        # ── PR-8: kategori yang dipakai tidak bisa dinonaktifkan ──────────────
        rdel = api('DELETE', f"/api/rahaza/product-categories/{cat_b['id']}")
        chk(rdel.status_code == 409, 'PR-8',
            'kategori yang masih dipakai ⇒ DELETE 409', f'HTTP {rdel.status_code}')

        # ── PR-9: dashboard == daftar model hidup ──────────────────────────
        dash = j(api('GET', '/api/dashboard'))
        stats = dash.get('stats') or dash
        n_dash = int(stats.get('products') or 0)
        rows = j(api('GET', '/api/rahaza/models'))
        rows = rows if isinstance(rows, list) else rows.get('models', [])
        n_list = sum(1 for m in rows if m.get('active') is not False)
        chk(n_dash == n_list, 'PR-9',
            'GET /api/dashboard menghitung SEMUA produk hidup (termasuk promosi R&D)',
            f'dashboard={n_dash} daftar={n_list}')
    finally:
        cleanup()
        left = (db.rahaza_models.count_documents({'code': {'$regex': f'^{MARK}'}})
                + db.rahaza_materials.count_documents({'code': {'$regex': f'^{MARK}'}})
                + db.marketing_catalogs.count_documents({'name': {'$regex': f'^{MARK}'}}))
        chk(left == 0, 'PR-CLEAN', 'jejak data uji gate = 0', f'{left} sisa')

    total = len(OK) + len(BAD)
    print(f'\n  INV-PRODUK: {G if not BAD else R}{BOLD}{len(OK)}/{total} OK{X}'
          + (f'  {R}{len(BAD)} FAIL: {BAD}{X}' if BAD else f'  {G}— HIJAU{X}'))
    return 1 if BAD else 0


if __name__ == '__main__':
    sys.exit(main())
