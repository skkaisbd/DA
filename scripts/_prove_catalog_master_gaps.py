#!/usr/bin/env python3
"""_prove_catalog_master_gaps.py — BUKTIKAN cacat logika **master data ↔ katalog marketing**.

Dipakai menyusun `docs/PLAN_MASTER_PRODUK_KATEGORI_HARGA.md` **BAGIAN 8** (permintaan owner
2026-08-10: *"telusuri hubungan master data dengan catalog marketing … apakah ada gap"*).

**SKRIP INI READ-ONLY.** Tidak ada `insert/update/delete` sama sekali — ia hanya (a) menghitung
angka dari data yang sudah ada, dan (b) memeriksa TEKS KODE untuk invarian statik. Jadi aman
dijalankan kapan pun, termasuk di data produksi.

Yang dibuktikan (kode M* = sama dengan penomoran di BAGIAN 8 rencana):

  M1  "stok katalog" punya TIGA rumus berbeda di tiga pintu.
  M2  item katalog baru dari FG selalu lahir stok 0 (lokasi "default" salah pilih).
  M3  `sync-from-wms` mengabaikan `reserved_quantity` ⇒ stok katalog > yang tersedia (overselling).
  M4  `sync-from-wms` membaca `qty` MENTAH, melanggar aturan `core/stock_schema` (wajib `read_qty`).
  M5  `sync-from-wms` melewati item yang tertaut lewat `variant_sku` (hanya `material_id`).
  M6  TIDAK ADA sinkron otomatis: nol jadwal scheduler & nol hook pergerakan stok.
  M7  Snapshot master lain (`name`/`category`/`weight_gram`) tidak punya penyegar.
  M8  `from-fg` tidak memeriksa model/FG masih aktif (produk dihentikan tetap bisa dijual).
  M9  `marketing_orders` tidak menyimpan tautan ke master (hanya `sku_id` teks bebas).
  M11 Sinkron marketplace = MOCK.

Pakai::  python3 scripts/_prove_catalog_master_gaps.py
"""
from __future__ import annotations

import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                'backend'))

from core.stock_schema import read_qty, read_reserved
from pymongo import MongoClient

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
G, R, Y, B, X, BOLD = ('\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[0m', '\033[1m')

_ok = _no = 0


def show(cond: bool, code: str, claim: str, detail: str = '') -> None:
    global _ok, _no
    if cond:
        _ok += 1
        print(f'  {G}[TERBUKTI]{X} {code} — {claim}' + (f'  {Y}→ {detail}{X}' if detail else ''))
    else:
        _no += 1
        print(f'  {R}[TIDAK TERBUKTI]{X} {code} — {claim}'
              + (f'  {Y}→ {detail}{X}' if detail else ''))


def src(rel: str) -> str:
    try:
        with open(os.path.join(APP, rel), encoding='utf-8', errors='replace') as fh:
            return fh.read()
    except OSError:
        return ''


def main() -> int:
    db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                     )[os.environ.get('DB_NAME', 'test_database')]

    print(f'{B}{"=" * 100}{X}')
    print(f'  {BOLD}BUKTI GAP — MASTER DATA ↔ KATALOG MARKETING{X}   (READ-ONLY)')
    print(f'{B}{"=" * 100}{X}')

    # ── M1/M2/M3: hitung TIGA rumus stok pada data nyata ───────────────────────
    default_loc = db.rahaza_locations.find_one({'active': True}, {'_id': 0, 'id': 1, 'name': 1})
    print(f'\n  {BOLD}Tiga rumus "stok katalog" pada data nyata{X}')
    print(f'  lokasi "default" yang dipakai jalur CREATE '
          f'(`find_one({{active: True}})`): {Y}{(default_loc or {}).get("name")}{X}')
    print(f'\n  {"material":24s}{"A create(1 lokasi)":>20s}{"B sync-item":>14s}{"C sync-wms":>13s}   beda')
    print(f'  {"-" * 78}')

    beda = a_zero = oversell = 0
    mats = db.rahaza_material_stock.distinct('material_id')
    for mid in mats:
        rows = list(db.rahaza_material_stock.find({'material_id': mid}, {'_id': 0}))
        m = db.rahaza_materials.find_one({'id': mid}, {'_id': 0, 'code': 1}) or {}
        a_doc = next((r for r in rows if r.get('location_id') == (default_loc or {}).get('id')), None)
        # Nama variabel SENGAJA bukan A/B/C: `B` bertabrakan dengan konstanta warna
        # modul ini dan membuat `print` di atas UnboundLocalError (ditemukan ruff F823).
        qty_create = float(a_doc.get('qty', 0)) if a_doc else 0.0   # POST /items/from-fg
        qty_item = max(0.0, sum(read_qty(r) for r in rows)
                       - sum(read_reserved(r) for r in rows))       # PUT /sync-fg-stock
        qty_wms = sum(float(r.get('qty', 0)) for r in rows)         # POST /sync-from-wms
        sama = abs(qty_create - qty_item) < 1e-3 and abs(qty_item - qty_wms) < 1e-3
        if not sama:
            beda += 1
        if qty_create == 0 and qty_item > 0:
            a_zero += 1
        if qty_wms > qty_item:
            oversell += 1
        print(f'  {(m.get("code") or mid)[:24]:24s}{qty_create:20.2f}{qty_item:14.2f}'
              f'{qty_wms:13.2f}   {"" if sama else R + "BEDA" + X}')
    print(f'  {"-" * 78}')

    show(beda == len(mats) and len(mats) > 0, 'M1',
         'ketiga pintu memberi angka stok BERBEDA untuk material yang sama',
         f'{beda}/{len(mats)} material berbeda')
    show(a_zero == len(mats) and len(mats) > 0, 'M2',
         'jalur CREATE (`from-fg`) menghasilkan stok 0 padahal stok jual > 0 — lokasi '
         '"default" = lokasi aktif PERTAMA, bukan lokasi yang menyimpan stok',
         f'{a_zero}/{len(mats)} material lahir 0')
    show(oversell > 0, 'M3',
         '`sync-from-wms` mengabaikan `reserved_quantity` ⇒ stok katalog LEBIH BESAR '
         'daripada yang tersedia (overselling)',
         f'{oversell} material tampak lebih banyak daripada yang tersedia')

    # ── M4/M5: invarian STATIK pada kode ──────────────────────────────────────
    print(f'\n  {BOLD}Pemeriksaan kode (statik){X}')
    stock_src = src('backend/routes/marketing_catalog_stock.py')
    show(bool(re.search(r"\.get\(\s*'qty'\s*,", stock_src)) and 'read_qty' not in stock_src,
         'M4', '`sync-from-wms` membaca `qty` MENTAH dan TIDAK memakai `read_qty()` — '
               'padahal `core/stock_schema` mewajibkannya (koleksi punya 3 skema historis)',
         "ditemukan .get('qty', …), tanpa import read_qty")
    show("'material_id': {'$exists': True, '$ne': None}" in stock_src
         or '"material_id": {"$exists": True, "$ne": None}' in stock_src,
         'M5', '`sync-from-wms` hanya menyentuh item yang punya `material_id` ⇒ item yang '
               'tertaut lewat `variant_sku` DILEWATI diam-diam',
         'filter material_id $exists')

    # ── M6: nol otomatisasi ───────────────────────────────────────────────────
    sched = src('backend/utils/scheduler.py')
    hooked = []
    for rel_dir in ('backend/routes', 'backend/core'):
        d = os.path.join(APP, rel_dir)
        for fn in sorted(os.listdir(d)) if os.path.isdir(d) else []:
            if not fn.endswith('.py'):
                continue
            if ((fn.startswith(('wms_', 'rahaza_inventory')) or rel_dir.endswith('core'))
                    and 'marketing_catalog_items' in src(os.path.join(rel_dir, fn))):
                hooked.append(fn)
    show('catalog' not in sched.lower() and not hooked, 'M6',
         'TIDAK ADA sinkron otomatis: nol jadwal scheduler DAN nol hook pergerakan stok yang '
         'menyentuh `marketing_catalog_items` ⇒ stok katalog basi sampai ada manusia menekan tombol',
         f'scheduler: {"ada" if "catalog" in sched.lower() else "nol"} · '
         f'hook stok: {hooked or "nol"}')

    # ── M7: penyegar hanya untuk HPP & stok ───────────────────────────────────
    items_src = src('backend/routes/marketing_catalog_items.py')
    show('refresh-hpp' in items_src
         and 'refresh-from-master' not in items_src, 'M7',
         'penyegar hanya ada untuk HPP (dan stok, manual). `name`/`category`/`weight_gram`/'
         '`variant_info` disalin sekali saat item dibuat dan TIDAK PERNAH diperbarui',
         'ada refresh-hpp, tidak ada refresh-from-master')

    # ── M8: from-fg tidak cek model aktif ─────────────────────────────────────
    m = re.search(r"async def add_catalog_item_from_fg.*?await db\.marketing_catalog_items\.insert_one",
                  items_src, re.DOTALL)
    blok = m.group(0) if m else ''
    show(bool(blok) and 'rahaza_models' not in blok, 'M8',
         '`POST /items/from-fg` TIDAK memeriksa model/FG masih aktif ⇒ produk yang sudah '
         'dihentikan tetap bisa dimasukkan ke katalog (jalur manual `POST /items` sudah benar)',
         'blok from-fg tidak menyentuh rahaza_models')

    # ── M9: order tidak tertaut master ────────────────────────────────────────
    ord_src = src('backend/routes/marketing_orders_routes.py')
    m2 = re.search(r'async def create_order.*?insert_one', ord_src, re.DOTALL)
    blok2 = m2.group(0) if m2 else ''
    tautan = [k for k in ('catalog_item_id', 'fg_material_id', 'variant_id') if k in blok2]
    n_ord = db.marketing_orders.count_documents({})
    n_link = db.marketing_orders.count_documents(
        {'$or': [{'catalog_item_id': {'$exists': True}}, {'fg_material_id': {'$exists': True}},
                 {'variant_id': {'$exists': True}}]})
    show(not tautan, 'M9',
         '`POST /api/marketing/orders` TIDAK menyimpan tautan ke master (hanya `sku_id` teks '
         'bebas, tanpa validasi) ⇒ tautan order→barang dibuat ULANG dengan tangan saat '
         'fulfillment `allocate`',
         f'field tautan di create_order: {tautan or "TIDAK ADA"} · '
         f'order di DB: {n_ord}, punya tautan: {n_link}')

    # ── M11: sinkron marketplace mock ─────────────────────────────────────────
    sync_src = src('backend/routes/marketing_toko_sync_routes.py')
    show('_mock_sync_provider' in sync_src and 'random' in sync_src, 'M11',
         'sinkron ke marketplace masih MOCK (angka acak, `mock: True`) ⇒ memperbaiki stok '
         'internal TIDAK otomatis memperbaiki stok di Shopee/Tokopedia/TikTok',
         'ditemukan _mock_sync_provider() + random')

    print(f'\n{B}{"=" * 100}{X}')
    print(f'  HASIL: {G}{_ok} klaim TERBUKTI{X} / {R}{_no} tidak terbukti{X}'
          f'   (skrip READ-ONLY — nol dokumen disentuh)')
    print(f'{B}{"=" * 100}{X}')
    return 0 if _no == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
