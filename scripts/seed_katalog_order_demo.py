#!/usr/bin/env python3
"""Seed IDEMPOTEN — data demo rantai MASTER PRODUK → FG → KATALOG → ORDER (F6/F9b).

MENGAPA BERKAS INI ADA
----------------------
`scripts/bootstrap.sh` menyeed produksi, HR, maklon, dan aksesoris, tetapi
rantai **marketing** berhenti di akun platform: `marketing_catalogs` = 0 dan
`marketing_catalog_items` = 0 pada environment yang lahir dari bootstrap segar.
Akibat nyatanya:

  · layar **Katalog Produk** kosong — fitur F6/F7 (kategori master, stok LIVE,
    margin, "simpanan basi") tidak bisa dilihat maupun diuji lewat layar;
  · layar **Buat Order** tidak punya satu pun produk yang sah untuk dipilih,
    padahal sejak K-8a order WAJIB menunjuk item katalog yang tertaut master
    (SKU asal-ketik ⇒ 400). Jadi alur order manual tidak bisa dibuktikan.

Skrip ini membangun rantai LENGKAP memakai **API sungguhan** (bukan tulis-paksa
ke koleksi), sehingga semua invarian yang dijaga backend tetap berlaku:

    kategori master → model (kode OTOMATIS dari prefix) → varian → FG
      → stok per lokasi → item katalog (`from-fg`) → siap dijual

Sifatnya:
  · **IDEMPOTEN** — dijalankan berkali-kali tidak menggandakan apa pun
    (dikenali lewat penanda `demo_source`).
  · **TIDAK menyentuh uang** — hanya master + stok fisik demo. Tidak membuat
    jurnal GL, invoice, atau pembayaran, jadi baseline gate tidak berubah.
  · **Sengaja menyisakan kasus BURUK** supaya layar bisa dinilai jujur:
      - 1 produk dengan stok jual **0** (habis) ⇒ pemilih produk order harus
        menolaknya dengan alasan yang jelas;
      - stok di **ZNA-KARANTINA** (lokasi blokir) ⇒ harus TIDAK terhitung sebagai
        stok jual (bukti K-6a);
      - 1 item katalog **manual tanpa tautan master** ⇒ harus muncul sebagai
        "belum tertaut master" dan tidak bisa dijual.

Pakai:
    python3 /app/scripts/seed_katalog_order_demo.py
    python3 /app/scripts/seed_katalog_order_demo.py --cleanup    # buang data demo ini
"""
from __future__ import annotations

import os
import sys
import uuid

import requests
from pymongo import MongoClient

BASE = os.environ.get('POC_BASE', 'http://localhost:8001')
CLEANUP = '--cleanup' in sys.argv
TAG = 'seed_katalog_order_demo'      # penanda supaya bisa dibersihkan
G, R, Y, X, BOLD = '\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m'

db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                 )[os.environ.get('DB_NAME', 'test_database')]

# Produk demo: sengaja beda kategori supaya filter kategori di katalog ada isinya.
# `stok` = jumlah per varian di lokasi jual; `karantina` = jumlah di ZNA-KARANTINA.
PRODUK = [
    {'name': 'Kaos Polos Premium Cotton Combed 30s', 'cat': 'KAOS',
     'base_hpp': 42_000, 'retail_price': 89_000, 'weight_gram': 220,
     'colors': ['PTH', 'HTM'], 'sizes': ['M', 'L'], 'stok': 60, 'karantina': 12},
    {'name': 'Hoodie Fleece Basic Unisex', 'cat': 'HOODIE',
     'base_hpp': 98_000, 'retail_price': 229_000, 'weight_gram': 620,
     'colors': ['HTM', 'ABU'], 'sizes': ['L', 'XL'], 'stok': 25, 'karantina': 0},
    {'name': 'Celana Jogger Tapered Fit', 'cat': 'CELANA',
     'base_hpp': 76_000, 'retail_price': 175_000, 'weight_gram': 410,
     'colors': ['HTM'], 'sizes': ['M', 'L'], 'stok': 0, 'karantina': 8},
]

ok_n = warn_n = err_n = 0


def ok(msg: str, detail: str = '') -> None:
    global ok_n
    ok_n += 1
    print(f'  {G}✓{X} {msg}' + (f'  \033[2m{detail}{X}' if detail else ''))


def warn(msg: str) -> None:
    global warn_n
    warn_n += 1
    print(f'  {Y}!{X} {msg}')


def err(msg: str) -> None:
    global err_n
    err_n += 1
    print(f'  {R}✗{X} {msg}')


class Api:
    def __init__(self) -> None:
        self.s = requests.Session()
        r = self.s.post(f'{BASE}/api/auth/login', json={
            'email': 'admin@garment.com', 'password': 'Admin@123'}, timeout=30)
        tok = (r.json() or {}).get('token', '') if r.status_code == 200 else ''
        if not tok:
            print(f'{R}FATAL: login admin gagal (HTTP {r.status_code}){X}')
            sys.exit(1)
        self.s.headers.update({'Authorization': f'Bearer {tok}',
                               'Content-Type': 'application/json'})

    def get(self, p, **kw):
        return self.s.get(f'{BASE}{p}', timeout=60, **kw)

    def post(self, p, **kw):
        return self.s.post(f'{BASE}{p}', timeout=120, **kw)


def jbody(r):
    try:
        return r.json()
    except Exception:
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# CLEANUP
# ══════════════════════════════════════════════════════════════════════════════
def cleanup() -> int:
    print(f'\n{BOLD}CLEANUP data demo katalog/order ({TAG}){X}')
    models = list(db.rahaza_models.find({'demo_source': TAG}, {'_id': 0, 'id': 1}))
    mids = [m['id'] for m in models]
    variants = list(db.rahaza_model_variants.find({'model_id': {'$in': mids}}, {'_id': 0, 'id': 1}))
    vids = [v['id'] for v in variants]
    fgs = list(db.rahaza_materials.find(
        {'$or': [{'model_id': {'$in': mids}}, {'variant_id': {'$in': vids}}], 'type': 'fg'},
        {'_id': 0, 'id': 1}))
    fids = [f['id'] for f in fgs]
    cats = list(db.marketing_catalogs.find({'demo_source': TAG}, {'_id': 0, 'id': 1}))
    cids = [c['id'] for c in cats]

    plan = [
        ('marketing_orders', {'demo_source': TAG}),
        ('marketing_catalog_items', {'$or': [{'catalog_id': {'$in': cids}},
                                             {'demo_source': TAG}]}),
        ('marketing_stock_syncs', {'catalog_id': {'$in': cids}}),
        ('marketing_catalogs', {'demo_source': TAG}),
        ('rahaza_material_stock', {'material_id': {'$in': fids}}),
        ('rahaza_stock_ledger', {'material_id': {'$in': fids}}),
        ('rahaza_materials', {'id': {'$in': fids}}),
        ('rahaza_model_variants', {'id': {'$in': vids}}),
        ('rahaza_models', {'demo_source': TAG}),
    ]
    for coll, flt in plan:
        if any(isinstance(v, dict) and '$in' in v and not v['$in'] for v in flt.values()):
            continue
        n = db[coll].delete_many(flt).deleted_count
        if n:
            print(f'  · {coll}: {n} dihapus')
    print(f'{G}CLEANUP selesai{X}')
    return 0


# ══════════════════════════════════════════════════════════════════════════════
# SEED
# ══════════════════════════════════════════════════════════════════════════════
def _loc_id(code: str) -> str:
    d = db.rahaza_locations.find_one({'code': code}, {'_id': 0, 'id': 1}) or {}
    return d.get('id', '')


def set_stock(material_id: str, location_id: str, qty: float) -> None:
    """Tulis satu baris stok fisik demo (SEMUA alias jumlah dijaga — core/stock_schema).

    Sengaja TIDAK lewat `rahaza/material-adjust`: endpoint itu memposting jurnal
    GL, dan data demo tidak boleh menggeser angka uang / baseline gate.
    """
    db.rahaza_material_stock.update_one(
        {'material_id': material_id, 'location_id': location_id},
        {'$set': {
            'qty': float(qty), 'total_qty': float(qty), 'quantity': float(qty),
            'reserved_quantity': 0.0, 'available_quantity': float(qty),
            'ownership': 'cv_da', 'inventory_category': 'fg_internal',
            'demo_source': TAG,
        }, '$setOnInsert': {'id': str(uuid.uuid4())}},
        upsert=True)


def main() -> int:
    if CLEANUP:
        return cleanup()

    api = Api()
    print(f'\n{BOLD}SEED demo rantai master → FG → katalog → order{X}  ({BASE})')

    # ── prasyarat master ──────────────────────────────────────────────────────
    kategori = {c['code']: c for c in db.rahaza_product_categories.find({}, {'_id': 0})}
    if len(kategori) < 5:
        err('master kategori produk belum ter-seed — jalankan '
            'backend/migrations/seed_product_categories.py dulu')
        return 1
    warna = {c['code']: c for c in db.rahaza_colors.find({}, {'_id': 0})}
    ukuran = {s['code']: s for s in db.rahaza_sizes.find({}, {'_id': 0})}
    if not warna or not ukuran:
        err('master warna/ukuran kosong — seed master produksi dulu')
        return 1
    loc_jual = _loc_id('ZNA-FG') or _loc_id('GDG-UTAMA-DEMO')
    loc_karantina = _loc_id('ZNA-KARANTINA')
    if not loc_jual:
        err('lokasi gudang produk jadi (ZNA-FG) tidak ada')
        return 1
    ok('prasyarat master siap',
       f'{len(kategori)} kategori · {len(warna)} warna · {len(ukuran)} ukuran')

    # ── akun platform + katalog ───────────────────────────────────────────────
    acc = db.marketing_platform_accounts.find_one({'status': 'active'}, {'_id': 0}) \
        or db.marketing_platform_accounts.find_one({}, {'_id': 0})
    if not acc:
        r = api.post('/api/marketing/accounts', json={
            'account_code': 'DEMO-SHOPEE', 'account_name': 'Toko Demo Shopee',
            'platform': 'shopee', 'username': 'toko_demo_shopee', 'group': 'other'})
        if r.status_code not in (200, 201):
            err(f'buat akun platform gagal: HTTP {r.status_code} {r.text[:160]}')
            return 1
        acc = jbody(r).get('account') or {}
    ok('akun platform siap', acc.get('account_name') or acc.get('name') or acc.get('id', ''))

    katalog = db.marketing_catalogs.find_one({'demo_source': TAG}, {'_id': 0})
    if not katalog:
        r = api.post('/api/marketing/catalogs', json={
            'account_id': acc['id'], 'name': 'Katalog Utama Shopee',
            'description': 'Katalog produk siap jual — data demo rantai master↔katalog.',
            'platform': acc.get('platform') or 'shopee'})
        if r.status_code not in (200, 201):
            err(f'buat katalog gagal: HTTP {r.status_code} {r.text[:160]}')
            return 1
        katalog = jbody(r).get('catalog') or {}
        db.marketing_catalogs.update_one({'id': katalog['id']},
                                        {'$set': {'demo_source': TAG}})
    catalog_id = katalog['id']
    ok('katalog siap', f"{katalog.get('name')} ({catalog_id[:8]})")

    # ── produk → varian → FG → stok → item katalog ────────────────────────────
    total_items = 0
    for p in PRODUK:
        cat = kategori.get(p['cat'])
        if not cat:
            warn(f"kategori {p['cat']} tidak ada — produk '{p['name']}' dilewati")
            continue

        model = db.rahaza_models.find_one({'name': p['name']}, {'_id': 0})
        if not model:
            r = api.post('/api/rahaza/models', json={
                'name': p['name'], 'category_id': cat['id'],
                'description': 'Produk demo siap jual (rantai master↔katalog).',
                'base_hpp': p['base_hpp'], 'retail_price': p['retail_price'],
                'weight_gram': p['weight_gram'], 'material_kg_per_pcs': 0.25,
                'bundle_size': 30})
            if r.status_code not in (200, 201):
                err(f"buat model '{p['name']}' gagal: HTTP {r.status_code} {r.text[:160]}")
                continue
            model = jbody(r)
            model = model.get('model') or model
        db.rahaza_models.update_one({'id': model['id']}, {'$set': {'demo_source': TAG}})
        ok(f"produk: {model.get('code')} · {p['name']}",
           f"HPP {p['base_hpp']:,} · harga resmi {p['retail_price']:,} · {p['weight_gram']} g")

        # varian (SKU {MODEL}-{WARNA}-{SIZE}) — FG dibuat otomatis oleh variant SSOT
        color_ids = [warna[c]['id'] for c in p['colors'] if c in warna]
        size_ids = [ukuran[s]['id'] for s in p['sizes'] if s in ukuran]
        if not color_ids or not size_ids:
            warn(f"warna/ukuran demo tidak lengkap untuk {model.get('code')}")
            continue
        r = api.post(f"/api/rahaza/models/{model['id']}/variants/generate",
                     json={'color_ids': color_ids, 'size_ids': size_ids})
        if r.status_code not in (200, 201):
            warn(f"generate varian {model.get('code')}: HTTP {r.status_code} {r.text[:120]}")

        variants = list(db.rahaza_model_variants.find({'model_id': model['id']}, {'_id': 0}))
        if not variants:
            err(f"varian {model.get('code')} tidak terbentuk")
            continue

        for v in variants:
            fg = db.rahaza_materials.find_one(
                {'type': 'fg', 'code': v.get('sku')}, {'_id': 0}) or {}
            if not fg:
                warn(f"FG untuk varian {v.get('sku')} belum ada — dilewati")
                continue
            set_stock(fg['id'], loc_jual, float(p['stok']))
            if p['karantina'] and loc_karantina:
                set_stock(fg['id'], loc_karantina, float(p['karantina']))

            # item katalog dari FG — harga & HPP & kategori diisi SERVER dari master
            existing = db.marketing_catalog_items.find_one(
                {'catalog_id': catalog_id,
                 '$or': [{'variant_sku': v.get('sku')}, {'sku': v.get('sku')}]},
                {'_id': 0, 'id': 1})
            if existing:
                continue
            r = api.post(f'/api/marketing/catalogs/{catalog_id}/items/from-fg',
                         json={'fg_material_id': fg['id'], 'price': 0,
                               'stock_alert_threshold': 10})
            if r.status_code not in (200, 201):
                warn(f"item katalog {v.get('sku')}: HTTP {r.status_code} {r.text[:140]}")
                continue
            total_items += 1
        ok(f"  varian & item katalog: {len(variants)} varian",
           f"stok jual {p['stok']}/varian" + (f" · karantina {p['karantina']}"
                                              if p['karantina'] else ''))

    # ── 1 item MANUAL tanpa tautan master (kasus buruk yang harus terlihat) ───
    legacy = db.marketing_catalog_items.find_one(
        {'catalog_id': catalog_id, 'sku': 'LEGACY-NOLINK-001'}, {'_id': 0, 'id': 1})
    if not legacy:
        cat_oth = kategori.get('LAINNYA') or next(iter(kategori.values()))
        r = api.post(f'/api/marketing/catalogs/{catalog_id}/items', json={
            'sku': 'LEGACY-NOLINK-001',
            'name': 'Tas Kanvas Tote (item lama, belum tertaut master)',
            'category_id': cat_oth['id'],
            'harga_jual': 65_000, 'stock_quantity': 7, 'stock_alert_threshold': 5,
            'variant_info': 'Warna: Cream'})
        if r.status_code in (200, 201):
            _iid = (jbody(r).get('item') or {}).get('id')
            if _iid:
                db.marketing_catalog_items.update_one({'id': _iid},
                                                     {'$set': {'demo_source': TAG}})
            ok('item manual tanpa tautan master dibuat (bukti "belum tertaut master")',
               'LEGACY-NOLINK-001')
        else:
            warn(f'item manual legacy: HTTP {r.status_code} {r.text[:140]}')
    else:
        ok('item manual tanpa tautan master sudah ada', 'LEGACY-NOLINK-001')

    # ── ringkasan hasil lewat API yang dipakai LAYAR (bukan tebakan) ──────────
    r = api.get('/api/marketing/catalog-items/search', params={'limit': 100})
    body = jbody(r)
    rows = body.get('items') or []
    counts = body.get('counts') or {}
    if r.status_code == 200:
        ok('pencarian item katalog (dipakai pemilih produk order) hidup',
           f"{counts.get('sellable', 0)} bisa dijual · {counts.get('blocked', 0)} bermasalah")
        for row in rows[:3]:
            print(f"      · {row['sku']:<22} {row['name'][:34]:<34} "
                  f"stok {row['available'] if row['available'] is not None else '—'} "
                  f"· Rp{row['harga_jual']:,.0f}")
        bad = [x for x in rows if not x['sellable']]
        if bad:
            print(f"      · contoh TIDAK bisa dijual: {bad[0]['sku']} — "
                  f"{(bad[0]['block_reason'] or '')[:70]}")
    else:
        err(f'pencarian item katalog gagal: HTTP {r.status_code} {r.text[:160]}')

    print(f'\n{BOLD}SELESAI{X} — {ok_n} ok · {warn_n} peringatan · {err_n} gagal '
          f'· {total_items} item katalog baru')
    return 1 if err_n else 0


if __name__ == '__main__':
    sys.exit(main())
