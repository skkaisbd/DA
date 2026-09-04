#!/usr/bin/env python3
"""test_core_master_katalog.py — POC ISOLASI (F0) untuk sesi 2026-08-10.

Menguji SATU rantai lima lapis lewat **HTTP sungguhan** (bukan unit test palsu):

    rahaza_product_categories → rahaza_models → rahaza_model_variants
      → rahaza_materials(type='fg') → rahaza_material_stock
        → marketing_catalog_items → marketing_orders → reservasi

Kenapa POC dulu: rantainya lima lapis dan menyentuh **stok & uang**. Kalau tidak
dibuktikan di sini, kegagalan baru terlihat di layar marketing (stok 0 /
overselling) — dan saat itu uang sudah hilang.

Keputusan owner yang diuji (FINAL, 2026-08-10):
  K-1A kode model otomatis dari `sku_prefix`; format SKU {MODEL}-{WARNA}-{SIZE} TIDAK diubah
  K-2  14 kategori awal
  K-3a `retail_price` di master = harga jual resmi; katalog memakainya sebagai nilai awal
  K-5a kategori lama dipetakan; yang tak dikenal dibuat entri master (`created_from='migrasi'`)
  K-6a stok "boleh dijual" = SEMUA lokasi KECUALI bertanda `blocked`/`quarantine`
  K-7a stok katalog dihitung LIVE; `stock_quantity` hanya cache + penanda `in_sync`
  K-8a order WAJIB bawa `catalog_item_id`/`variant_id`; SKU tak dikenal → 400
  K-9a nonaktifkan produk/varian ⇒ item katalog nonaktif + daftar terdampak

Pakai::
    python3 test_core_master_katalog.py            # semua bagian
    python3 test_core_master_katalog.py F1 F7      # hanya bagian tertentu
    python3 test_core_master_katalog.py --no-cleanup

SEMUA artefak uji memakai penanda `POCMK` dan DIHAPUS di akhir (jejak = 0).
"""
from __future__ import annotations

import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend'))

import requests  # noqa: E402
from pymongo import MongoClient  # noqa: E402

BASE = os.environ.get('POC_BASE', 'http://localhost:8001')
MARK = 'POCMK'
G, R, Y, B, X, BOLD, DIM = ('\033[92m', '\033[91m', '\033[93m', '\033[94m',
                            '\033[0m', '\033[1m', '\033[2m')

db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                 )[os.environ.get('DB_NAME', 'test_database')]

PASS: list[str] = []
FAIL: list[str] = []
_section = ''


def section(title: str) -> None:
    global _section
    _section = title
    print(f'\n{B}{BOLD}{"─" * 96}{X}')
    print(f'{B}{BOLD}  {title}{X}')
    print(f'{B}{BOLD}{"─" * 96}{X}')


def check(cond: bool, name: str, detail: str = '') -> bool:
    tag = f'{_section} · {name}'
    if cond:
        PASS.append(tag)
        print(f'  {G}✓{X} {name}' + (f'  {DIM}{detail}{X}' if detail else ''))
    else:
        FAIL.append(tag)
        print(f'  {R}✗ {name}{X}' + (f'  {Y}→ {detail}{X}' if detail else ''))
    return cond


# ══════════════════════════════════════════════════════════════════════════════
# HTTP helper
# ══════════════════════════════════════════════════════════════════════════════
class Api:
    def __init__(self) -> None:
        self.s = requests.Session()
        self.token = ''

    def login(self, email='admin@garment.com', password='Admin@123') -> bool:
        r = self.s.post(f'{BASE}/api/auth/login',
                        json={'email': email, 'password': password}, timeout=30)
        if r.status_code != 200:
            print(f'{R}LOGIN GAGAL {r.status_code}: {r.text[:200]}{X}')
            return False
        self.token = r.json().get('access_token') or r.json().get('token') or ''
        self.s.headers.update({'Authorization': f'Bearer {self.token}'})
        return True

    def _req(self, method, path, **kw):
        kw.setdefault('timeout', 60)
        return self.s.request(method, f'{BASE}{path}', **kw)

    def get(self, path, **kw):
        return self._req('GET', path, **kw)

    def post(self, path, **kw):
        return self._req('POST', path, **kw)

    def put(self, path, **kw):
        return self._req('PUT', path, **kw)

    def patch(self, path, **kw):
        return self._req('PATCH', path, **kw)

    def delete(self, path, **kw):
        return self._req('DELETE', path, **kw)


api = Api()


def jbody(r):
    try:
        return r.json()
    except Exception:  # noqa: BLE001
        return {}


# ══════════════════════════════════════════════════════════════════════════════
# Prasyarat: warna + ukuran master, akun + katalog marketing untuk uji
# ══════════════════════════════════════════════════════════════════════════════
CTX: dict = {}


def prasyarat() -> bool:
    section('§0 PRASYARAT — warna, ukuran, akun & katalog marketing uji')

    colors = jbody(api.get('/api/rahaza/colors'))
    colors = colors if isinstance(colors, list) else colors.get('colors', [])
    if not check(len(colors) >= 2, 'master warna tersedia', f'{len(colors)} warna'):
        return False
    sizes = jbody(api.get('/api/rahaza/sizes'))
    sizes = sizes if isinstance(sizes, list) else sizes.get('sizes', [])
    if not check(len(sizes) >= 1, 'master ukuran tersedia', f'{len(sizes)} ukuran'):
        return False
    CTX['color'] = colors[0]
    CTX['color2'] = colors[1]
    CTX['size'] = sizes[0]

    # akun platform uji
    acc = db.marketing_platform_accounts.find_one({'account_code': f'{MARK}-ACC'}, {'_id': 0})
    if not acc:
        r = api.post('/api/marketing/accounts', json={
            'account_code': f'{MARK}-ACC', 'account_name': f'{MARK} Akun Uji',
            'platform': 'shopee', 'username': f'{MARK}', 'group': 'other',
        })
        if not check(r.status_code in (200, 201), 'buat akun platform uji', f'HTTP {r.status_code} {r.text[:150]}'):
            return False
        acc = jbody(r).get('account') or {}
    CTX['account_id'] = acc.get('id')

    cat = db.marketing_catalogs.find_one({'name': f'{MARK} Katalog Uji'}, {'_id': 0})
    if not cat:
        r = api.post('/api/marketing/catalogs', json={
            'account_id': CTX['account_id'], 'name': f'{MARK} Katalog Uji',
            'description': 'katalog untuk POC master↔katalog', 'platform': 'shopee',
        })
        if not check(r.status_code in (200, 201), 'buat katalog uji', f'HTTP {r.status_code} {r.text[:150]}'):
            return False
        cat = jbody(r).get('catalog') or {}
    CTX['catalog_id'] = cat.get('id')
    return check(bool(CTX.get('catalog_id')), 'katalog uji siap', CTX.get('catalog_id', ''))


# ══════════════════════════════════════════════════════════════════════════════
# Alat bantu domain
# ══════════════════════════════════════════════════════════════════════════════
def _loc(code_suffix: str, *, blocked=False, quarantine=False) -> str:
    """Lokasi uji (dipakai untuk membuktikan K-6a)."""
    code = f'{MARK}-LOC-{code_suffix}'
    doc = db.rahaza_locations.find_one({'code': code}, {'_id': 0, 'id': 1})
    if doc:
        return doc['id']
    lid = str(uuid.uuid4())
    d = {'id': lid, 'code': code, 'name': f'{MARK} Lokasi {code_suffix}',
         'type': 'warehouse', 'active': True}
    if blocked:
        d['blocked'] = True
    if quarantine:
        d['quarantine'] = True
    db.rahaza_locations.insert_one(d)
    return lid


def set_stock(material_id: str, location_id: str, qty: float, reserved: float = 0.0,
              *, blocked=False, quarantine=False) -> None:
    """Tulis satu baris stok (menjaga SEMUA alias jumlah fisik — core/stock_schema)."""
    doc = {
        'qty': float(qty), 'total_qty': float(qty), 'quantity': float(qty),
        'reserved_quantity': float(reserved),
        'available_quantity': float(qty) - float(reserved),
        'ownership': 'cv_da', 'inventory_category': 'fg_internal',
        'poc_marker': MARK,
    }
    if blocked:
        doc['blocked'] = True
    if quarantine:
        doc['quarantine'] = True
    db.rahaza_material_stock.update_one(
        {'material_id': material_id, 'location_id': location_id},
        {'$set': doc, '$setOnInsert': {'id': str(uuid.uuid4())}}, upsert=True)


def create_model(code: str = None, **extra) -> tuple[int, dict]:
    body = {'name': f'{MARK} Produk Uji', 'description': 'POC master produk'}
    if code:
        body['code'] = code
    body.update(extra)
    r = api.post('/api/rahaza/models', json=body)
    return r.status_code, jbody(r)


def gen_variant(model_id: str, color_id: str, size_id: str) -> dict:
    r = api.post(f'/api/rahaza/models/{model_id}/variants/generate',
                 json={'color_ids': [color_id], 'size_ids': [size_id]})
    return jbody(r)


def fg_of_variant(sku: str) -> dict:
    return db.rahaza_materials.find_one({'type': 'fg', 'code': sku}, {'_id': 0}) or {}


def add_item_from_fg(fg_id: str, price: float = 0, **extra) -> tuple[int, dict]:
    body = {'fg_material_id': fg_id, 'price': price}
    body.update(extra)
    r = api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/items/from-fg", json=body)
    return r.status_code, jbody(r)


def list_items(**params) -> dict:
    r = api.get(f"/api/marketing/catalogs/{CTX['catalog_id']}/items", params=params)
    return jbody(r)


# ══════════════════════════════════════════════════════════════════════════════
# F1 — KODE PRODUK KEMBAR (T1) + normalisasi `active`
# ══════════════════════════════════════════════════════════════════════════════
def test_F1() -> None:
    section('§F1 KODE PRODUK KEMBAR (T1) — PR-1 · PR-2 · PR-3 · PR-9')

    # PR-1a — dua kali POST kode sama (keduanya active) ⇒ 409
    code_a = f'{MARK}-DUP1'
    st1, _ = create_model(code_a)
    check(st1 in (200, 201), 'model pertama dibuat', f'HTTP {st1}')
    st2, b2 = create_model(code_a)
    check(st2 == 409, 'kode sama (dokumen aktif) ⇒ 409',
          f'HTTP {st2} {str(b2)[:120]}')

    # PR-1b — dokumen LAMA gaya promosi R&D: hanya punya `status`, TANPA `active`
    code_b = f'{MARK}-DUP2'
    legacy_id = str(uuid.uuid4())
    db.rahaza_models.insert_one({
        'id': legacy_id, 'code': code_b, 'name': f'{MARK} Warisan Promosi R&D',
        'status': 'active', 'poc_marker': MARK,
    })
    st3, b3 = create_model(code_b)
    check(st3 == 409, 'kode sama dengan dokumen warisan (hanya `status`) ⇒ 409',
          f'HTTP {st3} {str(b3)[:140]}')
    if st3 in (200, 201):
        # bersihkan duplikat yang lolos supaya tidak mencemari pemeriksaan berikutnya
        db.rahaza_models.delete_many({'code': code_b, 'id': {'$ne': legacy_id}})

    # PR-1c — promosi R&D lewat HTTP harus menulis `active`
    style_code = f'{MARK}-STY'
    rs = api.post('/api/dewi/rnd/styles', json={
        'style_code': style_code, 'style_name': f'{MARK} Style POC',
        'category': 'Vest', 'description': 'POC promosi',
    })
    style = jbody(rs)
    style_id = style.get('id') or (style.get('style') or {}).get('id')
    if style_id:
        db.dewi_rnd_styles.update_one({'id': style_id}, {'$set': {'poc_marker': MARK}})
        # siklus hidup wajib: draft → pending_owner_review → approved_for_launch
        api.post(f'/api/dewi/rnd/styles/{style_id}/submit-for-review', json={})
        api.post(f'/api/dewi/rnd/styles/{style_id}/owner-approve',
                 json={'note': 'POC'})
        rp = api.post(f'/api/dewi/rnd/styles/{style_id}/promote-to-production',
                      json={'model_code': f'{MARK}-PROMO'})
        pb = jbody(rp)
        mid = pb.get('model_id')
        if mid:
            db.rahaza_models.update_one({'id': mid}, {'$set': {'poc_marker': MARK}})
        mdoc = db.rahaza_models.find_one({'id': mid}, {'_id': 0}) if mid else None
        check(bool(mdoc) and mdoc.get('active') is True,
              'promosi R&D menulis `active: True`',
              f"HTTP {rp.status_code} active={(mdoc or {}).get('active')} "
              f"status={(mdoc or {}).get('status')} {str(pb)[:120]}")
        check(bool(mdoc) and mdoc.get('category_id'),
              'promosi R&D memetakan kategori style ke MASTER kategori',
              f"category_id={(mdoc or {}).get('category_id')} "
              f"category={(mdoc or {}).get('category')}")
        # PR-9 — dashboard menghitung produk hasil promosi
        dash = jbody(api.get('/api/dashboard'))
        stats = dash.get('stats') or dash
        n_dash = int(stats.get('products') or stats.get('garments') or 0)
        rows = jbody(api.get('/api/rahaza/models'))
        rows = rows if isinstance(rows, list) else rows.get('models', [])
        n_list = sum(1 for m in rows if m.get('active') is not False)
        check(n_dash == n_list,
              'PR-9 GET /api/dashboard == jumlah model hidup di daftar',
              f'dashboard={n_dash} daftar={n_list}')
    else:
        check(False, 'style R&D uji dibuat', f'HTTP {rs.status_code} {rs.text[:160]}')

    # PR-2 — nol dokumen rahaza_models tanpa `active`
    # (artefak POC sengaja dibuat tanpa `active` untuk menguji 409 — dikecualikan)
    n_no_active = db.rahaza_models.count_documents(
        {'active': {'$exists': False}, 'poc_marker': {'$ne': MARK}})
    check(n_no_active == 0, 'PR-2 nol dokumen `rahaza_models` tanpa field `active`',
          f'{n_no_active} dokumen')

    # PR-3 — nol `code` kembar di seluruh koleksi
    dups = list(db.rahaza_models.aggregate([
        {'$group': {'_id': {'$toUpper': '$code'}, 'n': {'$sum': 1}}},
        {'$match': {'n': {'$gt': 1}}},
    ]))
    check(not dups, 'PR-3 nol `code` kembar di seluruh koleksi',
          f'kembar: {[d["_id"] for d in dups]}')


# ══════════════════════════════════════════════════════════════════════════════
# F7 — SATU RUMUS STOK JUAL (K-6a/K-7a) — KT-1..KT-5
# ══════════════════════════════════════════════════════════════════════════════
def _build_stock_fixture() -> dict:
    """Model → varian → FG → stok 3 lokasi (normal / karantina / blokir)."""
    code = f'{MARK}-STK'
    st, m = create_model(code)
    if st not in (200, 201):
        m = db.rahaza_models.find_one({'code': code}, {'_id': 0}) or {}
    model_id = m.get('id')
    if not model_id:
        return {}
    db.rahaza_models.update_one({'id': model_id}, {'$set': {'poc_marker': MARK}})
    gen_variant(model_id, CTX['color']['id'], CTX['size']['id'])
    v = db.rahaza_model_variants.find_one({'model_id': model_id}, {'_id': 0}) or {}
    sku = v.get('sku', '')
    fg = fg_of_variant(sku)
    if not fg:
        return {}
    db.rahaza_model_variants.update_one({'id': v['id']}, {'$set': {'poc_marker': MARK}})
    db.rahaza_materials.update_one({'id': fg['id']}, {'$set': {'poc_marker': MARK}})

    # stok: 100 on-hand −30 reserved di lokasi normal ⇒ sellable 70
    #       50 di lokasi KARANTINA + 40 di baris BLOKIR ⇒ TIDAK boleh dihitung
    set_stock(fg['id'], _loc('OK'), 100, 30)
    set_stock(fg['id'], _loc('QRT', quarantine=True), 50, 0, quarantine=True)
    set_stock(fg['id'], _loc('BLK', blocked=True), 40, 0, blocked=True)
    return {'model_id': model_id, 'variant': v, 'sku': sku, 'fg': fg, 'sellable': 70.0}


def test_F7() -> None:
    section('§F7 SATU RUMUS STOK JUAL (K-6a · K-7a) — KT-1..KT-5')
    fx = _build_stock_fixture()
    if not check(bool(fx), 'fixture model→varian→FG→stok siap'):
        return
    fg_id, sellable = fx['fg']['id'], fx['sellable']
    print(f'  {DIM}FG {fx["sku"]} · on-hand 100 (−30 reserved) di lokasi normal, '
          f'50 karantina, 40 blokir ⇒ sellable seharusnya {sellable:g}{X}')

    # KT-2 — item baru dari FG lahir dengan stok jual SEBENARNYA (bukan 0)
    st, body = add_item_from_fg(fg_id, price=150000)
    item = (body or {}).get('item') or {}
    if not check(st in (200, 201), 'buat item katalog dari FG', f'HTTP {st} {str(body)[:150]}'):
        return
    item_id = item.get('id')
    db.marketing_catalog_items.update_one({'id': item_id}, {'$set': {'poc_marker': MARK}})
    v_create = float(item.get('stock_quantity') or 0)
    check(abs(v_create - sellable) < 0.001,
          'KT-2 item baru dari FG lahir dengan stok jual sebenarnya',
          f'stock_quantity={v_create:g} (seharusnya {sellable:g})')

    # KT-1a — sync-fg-stock memberi angka IDENTIK
    r = api.put(f"/api/marketing/catalogs/{CTX['catalog_id']}/items/{item_id}/sync-fg-stock")
    v_sync_item = float(jbody(r).get('stock_quantity') or -1)
    check(abs(v_sync_item - sellable) < 0.001, 'KT-1a `sync-fg-stock` = stok jual',
          f'{v_sync_item:g} vs {sellable:g}')

    # KT-1b/KT-3 — sync-from-wms memberi angka IDENTIK (bukan on-hand mentah)
    api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/sync-from-wms")
    it = db.marketing_catalog_items.find_one({'id': item_id}, {'_id': 0}) or {}
    v_wms = float(it.get('stock_quantity') or 0)
    check(abs(v_wms - sellable) < 0.001,
          'KT-1b `sync-from-wms` = stok jual (bukan qty mentah)',
          f'{v_wms:g} vs {sellable:g}')
    check(v_wms <= sellable + 0.001,
          'KT-3 stok katalog TIDAK melebihi (on-hand − reserved) ⇒ overselling mustahil',
          f'{v_wms:g} <= {sellable:g}')
    check(abs(v_create - v_sync_item) < 0.001 and abs(v_sync_item - v_wms) < 0.001,
          'KT-1 KETIGA pintu menghasilkan angka IDENTIK',
          f'create={v_create:g} sync-item={v_sync_item:g} sync-wms={v_wms:g}')

    # K-6a — lokasi karantina/blokir tidak ikut dihitung
    check(v_wms < 100.0, 'K-6a stok karantina & blokir DIKECUALIKAN',
          f'{v_wms:g} < 100 (90 unit karantina/blokir tidak ikut)')

    # KT-5 — item yang tertaut lewat VARIAN (tanpa material_id) tidak dilewati
    r = api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/items", json={
        'sku': f'{MARK}-VAR-ITEM', 'name': f'{MARK} Item Bertaut Varian',
        'variant_id': fx['variant']['id'], 'price': 100000,
    })
    vitem = jbody(r).get('item') or {}
    if vitem.get('id'):
        db.marketing_catalog_items.update_one({'id': vitem['id']}, {'$set': {'poc_marker': MARK}})
        db.marketing_catalog_items.update_one(
            {'id': vitem['id']}, {'$set': {'stock_quantity': 0.0}})
        api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/sync-from-wms")
        got = db.marketing_catalog_items.find_one({'id': vitem['id']}, {'_id': 0}) or {}
        check(abs(float(got.get('stock_quantity') or 0) - sellable) < 0.001,
              'KT-5 item bertaut varian IKUT tersinkron (tidak dilewati diam-diam)',
              f"stock_quantity={got.get('stock_quantity')}")
    else:
        check(False, 'buat item bertaut varian', f'HTTP {r.status_code} {r.text[:150]}')

    # K-7a — GET items menyertakan `available` LIVE + penanda `in_sync`
    db.marketing_catalog_items.update_one({'id': item_id}, {'$set': {'stock_quantity': 999.0}})
    lst = list_items(limit=200)
    row = next((i for i in lst.get('items', []) if i.get('id') == item_id), {})
    check('available' in row,
          'K-7a `GET items` menyertakan `available` LIVE', f"available={row.get('available')}")
    check(abs(float(row.get('available') or -1) - sellable) < 0.001,
          'K-7a `available` LIVE = stok jual walau cache basi',
          f"available={row.get('available')} cache={row.get('stock_quantity')}")
    check(row.get('in_sync') is False,
          'K-7a penanda `in_sync` mendeteksi cache basi', f"in_sync={row.get('in_sync')}")

    # KT-4 — nol pembaca `qty` mentah di jalur stok katalog (diperiksa via AST,
    # bukan pencocokan teks — supaya komentar/docstring tidak jadi merah palsu)
    import ast as _ast
    bad = []
    for rel in ('backend/routes/marketing_catalog_stock.py',
                'backend/routes/marketing_catalog_items.py',
                'backend/core/catalog_stock.py'):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), rel)
        if not os.path.exists(p):
            continue
        with open(p, encoding='utf-8') as fh:
            tree = _ast.parse(fh.read())
        for node in _ast.walk(tree):
            if (isinstance(node, _ast.Call) and isinstance(node.func, _ast.Attribute)
                    and node.func.attr == 'get' and node.args
                    and isinstance(node.args[0], _ast.Constant)
                    and node.args[0].value in ('qty', 'total_qty')):
                bad.append(f'{rel}:{node.lineno}')
    check(not bad, 'KT-4 nol pembaca `qty` mentah (wajib read_qty/read_reserved)',
          f'pelanggar: {bad}')

    CTX['f7'] = {**fx, 'item_id': item_id, 'variant_item_id': vitem.get('id')}


# ══════════════════════════════════════════════════════════════════════════════
# F2 — MASTER KATEGORI PRODUK
# ══════════════════════════════════════════════════════════════════════════════
EXPECTED_PREFIX = {'Sweater': 'SWT', 'Cardigan': 'CRD', 'Vest': 'VST', 'Jacket': 'JKT',
                   'Polo': 'PLO', 'Hoodie': 'HDI', 'Rok': 'RSK', 'Celana': 'CLN',
                   'Dress': 'DRS', 'Blouse': 'BLS', 'Kemeja': 'KMJ',
                   'Set/Setelan': 'SET', 'Lainnya': 'OTH'}


def test_F2() -> None:
    section('§F2 MASTER KATEGORI PRODUK (K-2) — 4 endpoint + PR-8')

    r = api.get('/api/rahaza/product-categories')
    body = jbody(r)
    cats = body if isinstance(body, list) else body.get('categories', [])
    if not check(r.status_code == 200, 'GET /api/rahaza/product-categories', f'HTTP {r.status_code}'):
        return
    check(len(cats) >= 14, 'K-2 14 kategori awal ter-seed', f'{len(cats)} kategori')
    names = {c.get('name'): (c.get('sku_prefix') or '') for c in cats}
    missing = [n for n in EXPECTED_PREFIX if n not in names]
    check(not missing, 'K-2 semua nama kategori keputusan owner ada', f'hilang: {missing}')
    wrong = [f"{n}:{names.get(n)}≠{p}" for n, p in EXPECTED_PREFIX.items()
             if n in names and names[n] != p]
    check(not wrong, 'K-2 prefix SKU sesuai keputusan owner', f'{wrong}')
    CTX['cat_vest'] = next((c for c in cats if c.get('sku_prefix') == 'VST'), None)
    check(bool(CTX['cat_vest']), 'kategori Vest (VST) ditemukan')

    # POST — tambah kategori
    r = api.post('/api/rahaza/product-categories', json={
        'code': f'{MARK}CAT', 'name': f'{MARK} Kategori Uji',
        'sku_prefix': 'ZPC', 'order_seq': 99,
    })
    nb = jbody(r)
    newc = nb.get('category') or nb
    check(r.status_code in (200, 201), 'POST kategori baru', f'HTTP {r.status_code} {str(nb)[:140]}')
    cid = newc.get('id')
    if cid:
        db.rahaza_product_categories.update_one({'id': cid}, {'$set': {'poc_marker': MARK}})
        CTX['cat_poc'] = newc

    # POST — kode kembar ⇒ 409
    r = api.post('/api/rahaza/product-categories', json={
        'code': f'{MARK}CAT', 'name': 'kembar', 'sku_prefix': 'ZPD'})
    check(r.status_code == 409, 'kode kategori kembar ⇒ 409', f'HTTP {r.status_code}')

    # PUT — ubah nama/urutan
    if cid:
        r = api.put(f'/api/rahaza/product-categories/{cid}',
                    json={'name': f'{MARK} Kategori Uji (diubah)', 'order_seq': 98})
        check(r.status_code == 200, 'PUT kategori (nama/urutan)', f'HTTP {r.status_code}')
        after = db.rahaza_product_categories.find_one({'id': cid}, {'_id': 0}) or {}
        check(after.get('name', '').endswith('(diubah)'), 'perubahan nama tersimpan',
              after.get('name', ''))

    # DELETE — belum dipakai ⇒ boleh dinonaktifkan
    if cid:
        r = api.delete(f'/api/rahaza/product-categories/{cid}')
        check(r.status_code == 200, 'DELETE kategori yang belum dipakai ⇒ nonaktif',
              f'HTTP {r.status_code}')
        after = db.rahaza_product_categories.find_one({'id': cid}, {'_id': 0}) or {}
        check(after.get('active') is False, 'kategori jadi non-aktif (soft delete)',
              f"active={after.get('active')}")
        # hidupkan lagi untuk dipakai uji PR-8
        api.put(f'/api/rahaza/product-categories/{cid}', json={'active': True})


# ══════════════════════════════════════════════════════════════════════════════
# F3/F4/F5 — category_id + kode otomatis + HPP/harga/berat + propagasi
# ══════════════════════════════════════════════════════════════════════════════
def test_F345() -> None:
    section('§F3–F5 category_id · kode otomatis (K-1A) · HPP/harga/berat · propagasi')

    cat = CTX.get('cat_vest') or {}
    if not cat:
        r = api.get('/api/rahaza/product-categories')
        b = jbody(r)
        cats = b if isinstance(b, list) else b.get('categories', [])
        cat = next((c for c in cats if c.get('sku_prefix') == 'VST'), {})
    if not check(bool(cat.get('id')), 'kategori Vest tersedia untuk uji'):
        return

    # PR-4 — category_id tak dikenal ⇒ 400
    st, b = create_model(f'{MARK}-BADCAT', category_id='tidak-ada-0000')
    check(st == 400, 'PR-4 `category_id` tak dikenal ⇒ 400', f'HTTP {st} {str(b)[:120]}')
    if st in (200, 201):
        db.rahaza_models.delete_many({'code': f'{MARK}-BADCAT'})

    # PR-4b — kategori NON-AKTIF ⇒ 400
    poc_cat = CTX.get('cat_poc') or {}
    if poc_cat.get('id'):
        api.delete(f"/api/rahaza/product-categories/{poc_cat['id']}")
        st, b = create_model(f'{MARK}-INACTCAT', category_id=poc_cat['id'])
        check(st == 400, 'PR-4b kategori non-aktif ⇒ 400', f'HTTP {st}')
        if st in (200, 201):
            db.rahaza_models.delete_many({'code': f'{MARK}-INACTCAT'})
        api.put(f"/api/rahaza/product-categories/{poc_cat['id']}", json={'active': True})

    # K-1A — kode model DIBUAT OTOMATIS dari sku_prefix (tanpa `code` di body)
    st, m = create_model(None, category_id=cat['id'], base_hpp=42000,
                         retail_price=175000, weight_gram=320,
                         name=f'{MARK} Vest Otomatis')
    if not check(st in (200, 201), 'POST model tanpa `code` (kode otomatis)',
                 f'HTTP {st} {str(m)[:200]}'):
        return
    model = m.get('model') or m
    model_id = model.get('id')
    db.rahaza_models.update_one({'id': model_id}, {'$set': {'poc_marker': MARK}})
    code = (model.get('code') or '')
    check(code.startswith('VST-') and code.split('-')[-1].isdigit(),
          'K-1A kode otomatis berpola {PREFIX}-{URUT}', f'code={code}')

    # F3 — denormalisasi kategori + `category` legacy tetap disinkronkan
    check(model.get('category_id') == cat['id'], 'category_id tersimpan')
    check(model.get('category_code') == cat.get('code'), 'category_code terdenormalisasi',
          f"{model.get('category_code')}")
    check(model.get('category') == cat.get('name'),
          '`category` legacy = nama kategori (34 endpoint lama tetap jalan)',
          f"category={model.get('category')}")

    # F5 — base_hpp / retail_price / weight_gram benar-benar tersimpan
    check(float(model.get('base_hpp') or 0) == 42000, 'base_hpp tersimpan',
          str(model.get('base_hpp')))
    check(float(model.get('retail_price') or 0) == 175000, 'retail_price tersimpan (K-3a)',
          str(model.get('retail_price')))
    check(float(model.get('weight_gram') or 0) == 320, 'weight_gram tersimpan',
          str(model.get('weight_gram')))
    check(model.get('hpp_source') in ('manual', 'rnd'),
          'HPP punya sumber yang dilaporkan (`hpp_source`)', str(model.get('hpp_source')))

    # varian → FG: kategori/berat/HPP MENGALIR
    gen_variant(model_id, CTX['color']['id'], CTX['size']['id'])
    v = db.rahaza_model_variants.find_one({'model_id': model_id}, {'_id': 0}) or {}
    if not check(bool(v), 'varian dibuat'):
        return
    db.rahaza_model_variants.update_one({'id': v['id']}, {'$set': {'poc_marker': MARK}})
    sku = v.get('sku', '')
    # PR-10 — format SKU TIDAK berubah
    expect_sku = f"{code}-{CTX['color']['code']}-{CTX['size']['code']}".upper()
    check(sku == expect_sku, 'PR-10 format SKU tetap {MODEL}-{WARNA}-{SIZE}',
          f'{sku} vs {expect_sku}')

    fg = fg_of_variant(sku)
    if not check(bool(fg), 'FG otomatis dibuat untuk varian', sku):
        return
    db.rahaza_materials.update_one({'id': fg['id']}, {'$set': {'poc_marker': MARK}})
    check(fg.get('category_id') == cat['id'], 'kategori mengalir ke FG (category_id)',
          str(fg.get('category_id')))
    check(float(fg.get('weight_gram') or 0) == 320, 'PR-7 weight_gram master sampai ke FG',
          str(fg.get('weight_gram')))
    check(float(fg.get('hpp') or 0) == 42000,
          'PR-6 HPP manual (base_hpp) mengalir ke FG', str(fg.get('hpp')))

    # item katalog dari FG → dipakai untuk uji propagasi & F6
    set_stock(fg['id'], _loc('OK'), 25, 5)
    st, body = add_item_from_fg(fg['id'])
    item = (body or {}).get('item') or {}
    if not check(st in (200, 201), 'item katalog dibuat dari FG', f'HTTP {st} {str(body)[:150]}'):
        return
    item_id = item.get('id')
    db.marketing_catalog_items.update_one({'id': item_id}, {'$set': {'poc_marker': MARK}})

    # K-3a — harga jual awal dari retail_price master
    check(abs(float(item.get('harga_jual') or 0) - 175000) < 0.001,
          'K-3a harga jual item katalog terisi awal dari `retail_price` master',
          f"harga_jual={item.get('harga_jual')}")
    check(abs(float(item.get('hpp') or 0) - 42000) < 0.001,
          'PR-6 HPP item katalog dari base_hpp', f"hpp={item.get('hpp')}")
    check(item.get('hpp_source') == 'manual', "sumber HPP dilaporkan 'manual'",
          str(item.get('hpp_source')))
    check(item.get('category_id') == cat['id'], 'item katalog membawa category_id',
          str(item.get('category_id')))

    # PR-5 — ubah kategori & berat di master ⇒ FG DAN item katalog ikut berubah
    r = api.get('/api/rahaza/product-categories')
    b = jbody(r)
    cats = b if isinstance(b, list) else b.get('categories', [])
    cat2 = next((c for c in cats if c.get('sku_prefix') == 'JKT'), None) or \
        next((c for c in cats if c.get('id') != cat['id']), None)
    r = api.put(f'/api/rahaza/models/{model_id}',
                json={'category_id': cat2['id'], 'weight_gram': 555, 'retail_price': 199000})
    check(r.status_code == 200, 'PUT model ubah kategori/berat/harga', f'HTTP {r.status_code}')
    fg2 = db.rahaza_materials.find_one({'id': fg['id']}, {'_id': 0}) or {}
    it2 = db.marketing_catalog_items.find_one({'id': item_id}, {'_id': 0}) or {}
    check(fg2.get('category_id') == cat2['id'], 'PR-5a kategori baru sampai ke FG',
          f"{fg2.get('category_code')}")
    check(float(fg2.get('weight_gram') or 0) == 555, 'PR-5b berat baru sampai ke FG',
          str(fg2.get('weight_gram')))
    check(it2.get('category_id') == cat2['id'], 'PR-5c kategori baru sampai ke ITEM KATALOG',
          f"{it2.get('category_code')} / {it2.get('category')}")
    check(float(it2.get('weight_gram') or 0) == 555,
          'PR-5d berat baru sampai ke ITEM KATALOG', str(it2.get('weight_gram')))

    # PR-8 — kategori yang masih dipakai TIDAK bisa dinonaktifkan
    r = api.delete(f"/api/rahaza/product-categories/{cat2['id']}")
    check(r.status_code == 409, 'PR-8 kategori yang masih dipakai ⇒ DELETE 409',
          f'HTTP {r.status_code} {r.text[:140]}')

    CTX['f345'] = {'model_id': model_id, 'code': code, 'variant': v, 'fg': fg,
                   'item_id': item_id, 'cat': cat, 'cat2': cat2}


# ══════════════════════════════════════════════════════════════════════════════
# F6 — KATALOG MEMAKAI MASTER (kategori dropdown, filter, margin)
# ══════════════════════════════════════════════════════════════════════════════
def test_F6() -> None:
    section('§F6 KATALOG MEMAKAI MASTER — filter category_id · margin · selisih harga')
    fx = CTX.get('f345')
    if not check(bool(fx), 'fixture F3–F5 tersedia'):
        return
    cat2, item_id = fx['cat2'], fx['item_id']

    # filter category_id (bukan regex teks)
    lst = list_items(category_id=cat2['id'], limit=200)
    ids = [i.get('id') for i in lst.get('items', [])]
    check(item_id in ids, 'filter `category_id` menemukan item', f'{len(ids)} item')
    other = next((c for c in [fx['cat']] if c['id'] != cat2['id']), None)
    if other:
        lst2 = list_items(category_id=other['id'], limit=200)
        ids2 = [i.get('id') for i in lst2.get('items', [])]
        check(item_id not in ids2, 'filter `category_id` TIDAK mencampur kategori lain',
              f'{len(ids2)} item')

    # margin + selisih harga platform vs harga resmi master
    lst = list_items(limit=200)
    row = next((i for i in lst.get('items', []) if i.get('id') == item_id), {})
    check('margin' in row and 'margin_pct' in row,
          'item katalog melaporkan `margin` & `margin_pct`',
          f"margin={row.get('margin')} pct={row.get('margin_pct')}")
    hj, hpp = float(row.get('harga_jual') or 0), float(row.get('hpp') or 0)
    check(abs(float(row.get('margin') or 0) - (hj - hpp)) < 0.01,
          'margin = harga jual − HPP', f'{hj} − {hpp}')
    check('retail_price_master' in row and 'price_delta_vs_master' in row,
          'K-3a selisih harga platform vs harga resmi master ditampilkan',
          f"master={row.get('retail_price_master')} delta={row.get('price_delta_vs_master')}")

    # kategori tidak lagi bisa ditimpa teks bebas (T3)
    r = api.put(f"/api/marketing/catalogs/{CTX['catalog_id']}/items/{item_id}",
                json={'category': 'Kategori Ngawur Bebas'})
    after = db.marketing_catalog_items.find_one({'id': item_id}, {'_id': 0}) or {}
    check(after.get('category') != 'Kategori Ngawur Bebas',
          'T3 kategori item katalog TIDAK bisa ditimpa teks bebas',
          f"HTTP {r.status_code} category={after.get('category')}")

    # ── F6b (2026-08-10) — item MANUAL memilih kategori dari MASTER ────────────
    # Layar katalog sekarang mengirim `category_id`, bukan teks. Dua hal harus
    # benar: id ngawur DITOLAK (bukan diterima lalu kategorinya kosong), dan id
    # sah tersimpan lengkap dengan kode kategorinya.
    r = api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/items", json={
        'sku': f'{MARK}-MAN-BADCAT', 'name': f'{MARK} Item Manual Kategori Ngawur',
        'category_id': 'kategori-tidak-ada-xyz', 'harga_jual': 50000})
    check(r.status_code == 400,
          'F6b `category_id` ngawur saat BUAT item ⇒ 400 (tidak diterima diam-diam)',
          f'HTTP {r.status_code} {r.text[:120]}')

    r = api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/items", json={
        'sku': f'{MARK}-MAN-CAT', 'name': f'{MARK} Item Manual Kategori Master',
        'category_id': cat2['id'], 'harga_jual': 50000, 'stock_quantity': 5})
    mb = jbody(r).get('item') or {}
    check(r.status_code in (200, 201) and mb.get('category_id') == cat2['id']
          and (mb.get('category_code') or '') == cat2.get('code'),
          'F6b item manual menyimpan kategori MASTER (kode + nama ikut)',
          f"HTTP {r.status_code} {mb.get('category_code')} / {mb.get('category_name')}")


# ══════════════════════════════════════════════════════════════════════════════
# F8 — refresh-from-master + K-9a (produk dihentikan)
# ══════════════════════════════════════════════════════════════════════════════
def test_F8() -> None:
    section('§F8 refresh-from-master · K-9a produk dihentikan — KT-6..KT-8')
    fx = CTX.get('f345')
    if not check(bool(fx), 'fixture F3–F5 tersedia'):
        return
    model_id, item_id, fg = fx['model_id'], fx['item_id'], fx['fg']

    # KT-6 — ubah NAMA master ⇒ item katalog ikut disegarkan
    api.put(f'/api/rahaza/models/{model_id}', json={'name': f'{MARK} Vest Nama Baru'})
    db.marketing_catalog_items.update_one(
        {'id': item_id}, {'$set': {'name': 'NAMA BASI', 'category': 'BASI'}})
    r = api.post(f"/api/marketing/catalogs/{CTX['catalog_id']}/refresh-from-master")
    rb = jbody(r)
    check(r.status_code == 200, 'POST refresh-from-master', f'HTTP {r.status_code} {str(rb)[:140]}')
    it = db.marketing_catalog_items.find_one({'id': item_id}, {'_id': 0}) or {}
    check(it.get('name') != 'NAMA BASI', 'KT-6 nama item disegarkan dari master',
          f"name={it.get('name')}")
    check(it.get('category') == fx['cat2'].get('name'),
          'KT-6 kategori item disegarkan dari master', f"category={it.get('category')}")

    # KT-8 / K-9a — nonaktifkan model ⇒ item katalog nonaktif + DAFTAR TERDAMPAK
    r = api.delete(f'/api/rahaza/models/{model_id}')
    rb = jbody(r)
    check(r.status_code == 200, 'DELETE model (nonaktifkan)', f'HTTP {r.status_code}')
    affected = rb.get('affected_catalog_items') or rb.get('affected') or []
    check(isinstance(affected, list) and len(affected) >= 1,
          'K-9a daftar item katalog terdampak dikembalikan ke staf',
          f'{len(affected) if isinstance(affected, list) else affected} item')
    it = db.marketing_catalog_items.find_one({'id': item_id}, {'_id': 0}) or {}
    check(it.get('is_active') is False,
          'K-9a item katalog otomatis DINONAKTIFKAN', f"is_active={it.get('is_active')}")

    # KT-7 — FG milik model non-aktif tidak bisa ditambahkan ke katalog
    db.marketing_catalog_items.delete_many({'catalog_id': CTX['catalog_id'],
                                            'fg_material_id': fg['id']})
    st, b = add_item_from_fg(fg['id'])
    check(st == 400, 'KT-7 FG milik model NON-AKTIF ⇒ tidak bisa masuk katalog (400)',
          f'HTTP {st} {str(b)[:140]}')

    # hidupkan kembali untuk uji F9
    api.put(f'/api/rahaza/models/{model_id}', json={'active': True})


# ══════════════════════════════════════════════════════════════════════════════
# F9 — ORDER WAJIB BAWA TAUTAN MASTER (K-8a) + reservasi
# ══════════════════════════════════════════════════════════════════════════════
def _total_reserved(material_id: str) -> float:
    from core.stock_schema import read_reserved
    rows = list(db.rahaza_material_stock.find({'material_id': material_id}, {'_id': 0}))
    return round(sum(read_reserved(s) for s in rows), 4)


def test_F9() -> None:
    section('§F9 ORDER ↔ MASTER (K-8a) · reservasi saat konfirmasi — KT-9 · KT-10')
    fx = CTX.get('f7')
    if not check(bool(fx), 'fixture F7 tersedia'):
        return
    fg, item_id = fx['fg'], fx['item_id']

    base = {'platform': 'shopee', 'customer_name': f'{MARK} Pembeli',
            'quantity': 2, 'price_final': 150000}

    # KT-9a — tanpa tautan master ⇒ 400
    r = api.post('/api/marketing/orders', json={**base, 'sku_id': ''})
    check(r.status_code == 400, 'KT-9a order tanpa tautan master ⇒ 400',
          f'HTTP {r.status_code} {r.text[:140]}')

    # KT-9b — SKU tak dikenal ⇒ 400
    r = api.post('/api/marketing/orders', json={**base, 'sku_id': 'SKU-TIDAK-ADA-XYZ'})
    check(r.status_code == 400, 'KT-9b SKU tak dikenal ⇒ 400',
          f'HTTP {r.status_code} {r.text[:140]}')

    reserved_before = _total_reserved(fg['id'])

    # KT-9c — order sah dengan catalog_item_id ⇒ server mengisi fg_material_id
    r = api.post('/api/marketing/orders', json={**base, 'catalog_item_id': item_id})
    ob = jbody(r)
    order = ob.get('order') or ob
    order_id = order.get('id')
    if not check(r.status_code in (200, 201) and bool(order_id),
                 'KT-9c order dengan `catalog_item_id` diterima',
                 f'HTTP {r.status_code} {str(ob)[:180]}'):
        return
    db.marketing_orders.update_one({'id': order_id}, {'$set': {'poc_marker': MARK}})
    check(order.get('fg_material_id') == fg['id'],
          'KT-9c server MENGISI `fg_material_id` otomatis',
          f"fg_material_id={order.get('fg_material_id')}")
    check(bool(order.get('variant_id')), 'KT-9c `variant_id` ikut tersimpan',
          str(order.get('variant_id')))

    # M10 — stok DIRESERVASI saat order dikonfirmasi (tidak menunggu allocate)
    reserved_after = _total_reserved(fg['id'])
    check(abs(reserved_after - (reserved_before + 2)) < 0.001,
          'M10 stok direservasi saat order dibuat/dikonfirmasi',
          f'{reserved_before:g} → {reserved_after:g} (+2 pcs)')

    # stok jual katalog turun setelah reservasi (mustahil oversell)
    lst = list_items(limit=200)
    row = next((i for i in lst.get('items', []) if i.get('id') == item_id), {})
    check(float(row.get('available') or 0) <= 68.001,
          'stok jual katalog turun setelah reservasi (anti-oversell)',
          f"available={row.get('available')}")

    # allocate: TIDAK boleh menghitung reservasi dua kali
    api.patch(f'/api/marketing/orders/{order_id}/status', json={'status': 'new'})
    r = api.get(f'/api/fulfillment/orders/{order_id}/suggest-allocation')
    sb = jbody(r)
    check(r.status_code == 200, 'GET suggest-allocation (usulan otomatis)',
          f'HTTP {r.status_code} {str(sb)[:140]}')
    sug = (sb.get('items') or sb.get('suggestions') or [])
    check(any((s or {}).get('material_id') == fg['id'] for s in sug),
          'M9 usulan alokasi menunjuk FG yang benar dari tautan order',
          f'{len(sug)} usulan')
    if sug:
        r = api.post(f'/api/fulfillment/orders/{order_id}/allocate', json={
            'items': [{'material_id': fg['id'], 'qty_allocated': 2,
                       'sku_code': fg.get('code', '')}]})
        after_alloc = _total_reserved(fg['id'])
        check(r.status_code in (200, 201), 'allocate berhasil',
              f'HTTP {r.status_code} {r.text[:140]}')
        check(abs(after_alloc - reserved_after) < 0.001,
              'reservasi TIDAK dihitung dua kali setelah allocate',
              f'{reserved_after:g} → {after_alloc:g}')

    # batal ⇒ reservasi dilepas
    api.patch(f'/api/marketing/orders/{order_id}/status', json={'status': 'cancelled'})
    after_cancel = _total_reserved(fg['id'])
    check(abs(after_cancel - reserved_before) < 0.001,
          'order dibatalkan ⇒ reservasi DILEPAS (stok kembali bisa dijual)',
          f'{after_cancel:g} vs awal {reserved_before:g}')

    # order LAMA (tanpa tautan) tetap terbaca
    legacy_id = str(uuid.uuid4())
    db.marketing_orders.insert_one({
        'id': legacy_id, 'order_id': f'{MARK}-LEGACY', 'platform': 'shopee',
        'customer_name': f'{MARK} Lama', 'sku_id': 'SKU-LAMA-BEBAS',
        'quantity': 1, 'status': 'delivered', 'poc_marker': MARK,
    })
    r = api.get('/api/marketing/orders', params={'search': f'{MARK}-LEGACY'})
    lb = jbody(r)
    rows = lb.get('orders') or lb.get('items') or []
    check(r.status_code == 200 and any(o.get('id') == legacy_id for o in rows),
          'K-8a order LAMA tanpa tautan tetap TERBACA', f'HTTP {r.status_code} {len(rows)} baris')

    # KT-10 — nol item katalog yatim
    items = list(db.marketing_catalog_items.find({}, {'_id': 0}))
    fg_ids = {m['id'] for m in db.rahaza_materials.find({'type': 'fg'}, {'_id': 0, 'id': 1})}
    orphan = [i.get('sku') for i in items
              if i.get('fg_material_id') and i['fg_material_id'] not in fg_ids]
    check(not orphan, 'KT-10 nol item katalog yatim (menunjuk FG yang tak ada)', f'{orphan}')


# ══════════════════════════════════════════════════════════════════════════════
# F9b — ORDER MULTI-PRODUK (K-8b) + pemilih produk katalog
# ══════════════════════════════════════════════════════════════════════════════
def test_F9B() -> None:
    """Kenapa bagian ini ada (temuan 2026-08-10).

    K-8a mewajibkan tautan master, tetapi implementasi pertama hanya menautkan &
    mereservasi **baris pertama** order. Order 3 produk ⇒ 2 produk TIDAK dipesan,
    jadi stok yang sama masih bisa terjual dua kali — bug uang/stok yang tidak
    terlihat dari layar mana pun. Selain itu layar order masih meminta staf
    MENGETIK SKU, padahal SKU asal-ketik selalu ditolak 400: alur buat-order
    manual praktis mentok sampai ada pemilih produk.
    """
    section('§F9b ORDER MULTI-PRODUK (K-8b) · pemilih produk katalog — KT-11..KT-17')
    fx = CTX.get('f7')
    if not check(bool(fx), 'fixture F7 tersedia'):
        return
    fg1, item1 = fx['fg'], fx['item_id']

    # ── produk KEDUA (supaya multi-baris benar-benar diuji, bukan disimulasikan)
    code2 = f'{MARK}-STK2'
    st, m2 = create_model(code2)
    if st not in (200, 201):
        m2 = db.rahaza_models.find_one({'code': code2}, {'_id': 0}) or {}
    mid2 = m2.get('id')
    if not check(bool(mid2), 'produk kedua dibuat', f'HTTP {st}'):
        return
    db.rahaza_models.update_one({'id': mid2}, {'$set': {'poc_marker': MARK}})
    gen_variant(mid2, CTX['color2']['id'], CTX['size']['id'])
    v2 = db.rahaza_model_variants.find_one({'model_id': mid2}, {'_id': 0}) or {}
    fg2 = fg_of_variant(v2.get('sku', ''))
    if not check(bool(fg2), 'FG produk kedua lahir dari varian', v2.get('sku', '')):
        return
    db.rahaza_model_variants.update_one({'id': v2['id']}, {'$set': {'poc_marker': MARK}})
    db.rahaza_materials.update_one({'id': fg2['id']}, {'$set': {'poc_marker': MARK}})
    set_stock(fg2['id'], _loc('OK2'), 20, 0)
    st2, ib = add_item_from_fg(fg2['id'], 90000)
    item2 = (ib.get('item') or {}).get('id')
    if not check(st2 in (200, 201) and bool(item2), 'item katalog kedua dibuat', f'HTTP {st2}'):
        return

    # ── KT-11 — pencarian item katalog (sumber data pemilih produk di layar order)
    r = api.get('/api/marketing/catalog-items/search', params={'q': MARK, 'limit': 50})
    sb = jbody(r)
    rows = {x.get('sku'): x for x in (sb.get('items') or [])}
    check(r.status_code == 200 and len(rows) >= 2,
          'KT-11 pencarian item katalog lintas-katalog hidup',
          f'HTTP {r.status_code} {len(rows)} item')
    row1 = rows.get(fx['sku']) or {}
    check(abs(float(row1.get('available') or -1) - fx['sellable']) < 0.001,
          'KT-11 stok di pemilih produk = stok jual LIVE (bukan angka simpanan)',
          f"available={row1.get('available')} vs {fx['sellable']}")
    check(row1.get('sellable') is True and not row1.get('block_reason'),
          'KT-11 item sehat ditandai boleh dijual',
          f"sellable={row1.get('sellable')}")
    check(float(row1.get('fg_excluded_onhand') or 0) > 0,
          'KT-11 stok karantina/blokir dilaporkan TERPISAH (bukti K-6a di layar)',
          f"excluded={row1.get('fg_excluded_onhand')}")

    # ── KT-12 — order MULTI-PRODUK: SEMUA baris tertaut & dipesan ──────────────
    res1_before, res2_before = _total_reserved(fg1['id']), _total_reserved(fg2['id'])
    r = api.post('/api/marketing/orders', json={
        'platform': 'shopee', 'customer_name': f'{MARK} Pembeli Multi',
        'items': [
            {'catalog_item_id': item1, 'sku_code': fx['sku'], 'qty': 2, 'price': 150000},
            {'catalog_item_id': item2, 'sku_code': v2.get('sku'), 'qty': 3, 'price': 90000},
        ]})
    ob = jbody(r)
    order = ob.get('order') or ob
    oid = order.get('id')
    if not check(r.status_code in (200, 201) and bool(oid),
                 'KT-12 order 2 produk diterima', f'HTTP {r.status_code} {str(ob)[:160]}'):
        return
    db.marketing_orders.update_one({'id': oid}, {'$set': {'poc_marker': MARK}})
    lines = order.get('items') or []
    check(len(lines) == 2 and all(ln.get('fg_material_id') for ln in lines),
          'KT-12 SETIAP baris order tertaut ke FG master (bukan hanya baris pertama)',
          f"{[ (ln.get('sku_code'), bool(ln.get('fg_material_id'))) for ln in lines ]}")
    d1 = _total_reserved(fg1['id']) - res1_before
    d2 = _total_reserved(fg2['id']) - res2_before
    check(abs(d1 - 2) < 0.001 and abs(d2 - 3) < 0.001,
          'KT-12 stok DIPESAN untuk semua baris (anti-oversell produk ke-2)',
          f'produk1 +{d1:g} (minta 2) · produk2 +{d2:g} (minta 3)')
    check(abs(float(order.get('total_payment') or 0) - (2 * 150000 + 3 * 90000)) < 0.01,
          'KT-12 total pembayaran = jumlah semua baris',
          f"total={order.get('total_payment')}")

    # ── KT-13 — usulan alokasi menyebut SEMUA baris (bukan cuma yang pertama) ──
    api.patch(f'/api/marketing/orders/{oid}/status', json={'status': 'new'})
    r = api.get(f'/api/fulfillment/orders/{oid}/suggest-allocation')
    sug = (jbody(r).get('items') or [])
    mids = {s.get('material_id') for s in sug}
    check(r.status_code == 200 and fg1['id'] in mids and fg2['id'] in mids,
          'KT-13 usulan alokasi mencakup SEMUA produk pesanan',
          f'{len(sug)} usulan')

    # ── KT-14 — dibatalkan ⇒ reservasi SEMUA baris dilepas ─────────────────────
    api.patch(f'/api/marketing/orders/{oid}/status', json={'status': 'cancelled'})
    a1 = _total_reserved(fg1['id']) - res1_before
    a2 = _total_reserved(fg2['id']) - res2_before
    check(abs(a1) < 0.001 and abs(a2) < 0.001,
          'KT-14 pembatalan melepas reservasi SEMUA baris (stok bisa dijual lagi)',
          f'sisa produk1 {a1:g} · produk2 {a2:g}')

    # ── KT-15 — ATOMIK: satu baris gagal ⇒ TIDAK ada reservasi menggantung ─────
    r = api.post('/api/marketing/orders', json={
        'platform': 'shopee', 'customer_name': f'{MARK} Pembeli Gagal',
        'items': [
            {'catalog_item_id': item1, 'sku_code': fx['sku'], 'qty': 1, 'price': 1000},
            {'catalog_item_id': item2, 'sku_code': v2.get('sku'), 'qty': 999999, 'price': 1000},
        ]})
    check(r.status_code == 409, 'KT-15 baris melebihi stok ⇒ 409 (order tidak dibuat)',
          f'HTTP {r.status_code} {r.text[:130]}')
    b1 = _total_reserved(fg1['id']) - res1_before
    b2 = _total_reserved(fg2['id']) - res2_before
    check(abs(b1) < 0.001 and abs(b2) < 0.001,
          'KT-15 reservasi baris yang sudah lolos DILEPAS (tak ada stok terpesan hantu)',
          f'sisa produk1 {b1:g} · produk2 {b2:g}')

    # ── KT-16 — SKU asal-ketik di dalam `items[]` tetap DITOLAK (K-8a utuh) ────
    r = api.post('/api/marketing/orders', json={
        'platform': 'shopee', 'customer_name': f'{MARK} Pembeli Ketik',
        'items': [{'sku_code': 'SKU-KETIK-NGAWUR-XYZ', 'product_name': 'x',
                   'qty': 1, 'price': 1000}]})
    check(r.status_code == 400, 'KT-16 SKU asal-ketik per baris ⇒ 400',
          f'HTTP {r.status_code}')

    # ── KT-17 — item yang TIDAK boleh dijual tetap TAMPIL + ada alasannya ─────
    # (keputusan pemilik: jangan disembunyikan — staf harus tahu apa yang rusak)
    api.put(f"/api/marketing/catalogs/{CTX['catalog_id']}/items/{item2}",
            json={'is_active': False})
    r = api.get('/api/marketing/catalog-items/search',
                params={'q': v2.get('sku'), 'limit': 20})
    hit = next((x for x in (jbody(r).get('items') or [])
                if x.get('catalog_item_id') == item2), None)
    check(bool(hit) and hit.get('sellable') is False and bool(hit.get('block_reason')),
          'KT-17 item non-aktif tetap terlihat, ditandai tak bisa dijual + alasan',
          f"sellable={(hit or {}).get('sellable')} · {str((hit or {}).get('block_reason'))[:70]}")
    r = api.post('/api/marketing/orders', json={
        'platform': 'shopee', 'customer_name': f'{MARK} Pembeli NonAktif',
        'items': [{'catalog_item_id': item2, 'qty': 1, 'price': 1000}]})
    check(r.status_code == 400, 'KT-17 order memakai item non-aktif ⇒ 400',
          f'HTTP {r.status_code} {r.text[:120]}')


# ══════════════════════════════════════════════════════════════════════════════
# CLEANUP — jejak data uji WAJIB 0
# ══════════════════════════════════════════════════════════════════════════════
def cleanup() -> None:
    section('§CLEANUP — hapus SEMUA artefak uji (jejak wajib 0)')
    removed = {}

    fg_ids = [m['id'] for m in db.rahaza_materials.find(
        {'$or': [{'poc_marker': MARK}, {'code': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]
    model_ids = [m['id'] for m in db.rahaza_models.find(
        {'$or': [{'poc_marker': MARK}, {'code': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]
    var_ids = [v['id'] for v in db.rahaza_model_variants.find(
        {'$or': [{'poc_marker': MARK}, {'model_id': {'$in': model_ids}},
                 {'sku': {'$regex': f'^{MARK}'}}]}, {'_id': 0, 'id': 1})]

    plans = [
        ('marketing_orders', {'$or': [{'poc_marker': MARK},
                                      {'customer_name': {'$regex': MARK}},
                                      {'order_id': {'$regex': f'^{MARK}'}}]}),
        ('marketing_catalog_items', {'$or': [{'poc_marker': MARK},
                                             {'sku': {'$regex': f'^{MARK}'}},
                                             {'fg_material_id': {'$in': fg_ids}},
                                             {'catalog_id': CTX.get('catalog_id', '__none__')}]}),
        ('marketing_stock_syncs', {'catalog_id': CTX.get('catalog_id', '__none__')}),
        ('marketing_catalogs', {'name': {'$regex': f'^{MARK}'}}),
        ('marketing_platform_accounts', {'account_code': {'$regex': f'^{MARK}'}}),
        ('rahaza_material_stock', {'$or': [{'poc_marker': MARK},
                                           {'material_id': {'$in': fg_ids}}]}),
        ('rahaza_stock_ledger', {'material_id': {'$in': fg_ids}}),
        ('rahaza_materials', {'id': {'$in': fg_ids}}),
        ('rahaza_model_variants', {'id': {'$in': var_ids}}),
        ('rahaza_models', {'id': {'$in': model_ids}}),
        ('rahaza_product_categories', {'poc_marker': MARK}),
        ('rahaza_locations', {'code': {'$regex': f'^{MARK}-LOC-'}}),
        ('dewi_rnd_styles', {'$or': [{'poc_marker': MARK},
                                     {'style_code': {'$regex': f'^{MARK}'}}]}),
        ('dewi_rnd_variants', {'style_id': {'$in': []}}),
        ('wh_pending_inbound', {'material_id': {'$in': fg_ids}}),
        ('activity_logs', {'entity_id': {'$regex': f'^{MARK}'}}),
    ]
    for coll, q in plans:
        try:
            n = db[coll].delete_many(q).deleted_count
            if n:
                removed[coll] = n
        except Exception as e:  # noqa: BLE001
            print(f'  {Y}! gagal bersihkan {coll}: {e}{X}')

    for k, v in removed.items():
        print(f'  {DIM}· {k}: {v} dihapus{X}')

    leftovers = {}
    for coll, q in (('rahaza_models', {'code': {'$regex': f'^{MARK}'}}),
                    ('rahaza_materials', {'code': {'$regex': f'^{MARK}'}}),
                    ('marketing_catalog_items', {'sku': {'$regex': f'^{MARK}'}}),
                    ('marketing_catalogs', {'name': {'$regex': f'^{MARK}'}}),
                    ('marketing_orders', {'customer_name': {'$regex': MARK}}),
                    ('rahaza_product_categories', {'poc_marker': MARK}),
                    ('rahaza_locations', {'code': {'$regex': f'^{MARK}-LOC-'}})):
        n = db[coll].count_documents(q)
        if n:
            leftovers[coll] = n
    check(not leftovers, 'jejak data uji = 0', f'{leftovers}')


SECTIONS = {
    'F1': test_F1, 'F7': test_F7, 'F2': test_F2,
    'F345': test_F345, 'F6': test_F6, 'F8': test_F8, 'F9': test_F9,
    'F9B': test_F9B,
}
ORDER = ['F1', 'F7', 'F2', 'F345', 'F6', 'F8', 'F9', 'F9B']


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    do_cleanup = '--no-cleanup' not in sys.argv
    wanted = [a.upper() for a in args] or ORDER

    print(f'{B}{BOLD}{"=" * 96}{X}')
    print(f'  {BOLD}POC ISOLASI — MASTER PRODUK ↔ KATALOG MARKETING ↔ ORDER{X}')
    print(f'  {DIM}target: {BASE} · penanda artefak: {MARK} · bagian: {", ".join(wanted)}{X}')
    print(f'{B}{BOLD}{"=" * 96}{X}')

    if not api.login():
        return 2
    if not prasyarat():
        if do_cleanup:
            cleanup()
        return 2

    try:
        for key in ORDER:
            if key in wanted:
                SECTIONS[key]()
    finally:
        if do_cleanup:
            cleanup()

    total = len(PASS) + len(FAIL)
    print(f'\n{B}{BOLD}{"=" * 96}{X}')
    color = G if not FAIL else R
    print(f'  HASIL: {color}{BOLD}{len(PASS)}/{total} LULUS{X}'
          + (f'   {R}{len(FAIL)} GAGAL{X}' if FAIL else f'   {G}— POC HIJAU{X}'))
    if FAIL:
        print(f'\n  {R}{BOLD}Yang masih gagal:{X}')
        for f in FAIL:
            print(f'    {R}✗{X} {f}')
    print(f'{B}{BOLD}{"=" * 96}{X}\n')
    return 0 if not FAIL else 1


if __name__ == '__main__':
    sys.exit(main())
