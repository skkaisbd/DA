"""core.product_master — SSOT master produk internal DA (F2·F3·F4·F5).

Kenapa modul ini ada: `category`, `hpp`, `weight_gram` dan `retail_price`
selama ini ditulis oleh **tiga penulis berbeda** (form manual, promosi R&D,
seeder) dengan aturan masing-masing. Akibat yang sudah TERBUKTI
(`scripts/_prove_master_produk_logic_gaps.py`):

  * **P1a/P1b** produk manual lahir tanpa HPP & harga jual ⇒ FG `hpp = 0` ⇒
    margin katalog marketing mustahil dihitung.
  * **P2a/P2b** `category` DISALIN ke FG saat FG dibuat dan **tidak pernah**
    diperbarui ⇒ ubah kategori di master, FG & katalog tetap kategori LAMA.
  * **P3** `category` teks bebas — server menerima nilai di luar dropdown.
  * **P4a/P4b** `weight_gram` DIBACA `ensure_fg_material()` tetapi tidak pernah
    ditulis ⇒ berat FG selalu 0.
  * **T1** `active` tidak ditulis semua penulis ⇒ index unik `code` bocor ⇒
    **kode produk bisa kembar**.

KEPUTUSAN OWNER (2026-08-10):
  * **K-1A** kategori punya `sku_prefix`; `code` model **dibuat otomatis**
    (`VST-0001`) lewat counter atomik. Format SKU varian tetap
    `{MODEL}-{WARNA}-{SIZE}` ⇒ nol migrasi SKU/barcode.
  * **K-3a** `retail_price` di master = **harga jual RESMI**; katalog memakainya
    sebagai nilai awal dan boleh menimpanya per platform (selisih ditampilkan).
  * **K-5a** kategori lama dipetakan; yang tak dikenal dibuatkan entri master
    (`created_from='migrasi'`) — nol data hilang.

ATURAN:
  1. `apply_category()` adalah **satu-satunya** penulis stempel kategori.
  2. `resolve_hpp()` adalah **satu-satunya** urutan resolusi HPP
     (`model.hpp` R&D → `model.base_hpp` manual → 0) dan selalu melaporkan sumbernya.
  3. `propagate_master_changes()` menurunkan kategori/nama/berat/HPP/harga ke
     FG **dan** item katalog yang tertaut — hanya dokumen ber-`model_id` ini.
  4. `active` WAJIB ditulis semua penulis; `status` berhenti dipakai sebagai
     penanda hidup/mati (tetap dibaca untuk dokumen lama).
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CATEGORIES = 'rahaza_product_categories'

# ── K-2 — 14 kategori awal (keputusan owner 2026-08-10) ──────────────────────
DEFAULT_CATEGORIES = [
    {'code': 'SWEATER', 'name': 'Sweater', 'sku_prefix': 'SWT', 'order_seq': 10},
    {'code': 'CARDIGAN', 'name': 'Cardigan', 'sku_prefix': 'CRD', 'order_seq': 20},
    {'code': 'VEST', 'name': 'Vest', 'sku_prefix': 'VST', 'order_seq': 30},
    {'code': 'JACKET', 'name': 'Jacket', 'sku_prefix': 'JKT', 'order_seq': 40},
    {'code': 'POLO', 'name': 'Polo', 'sku_prefix': 'PLO', 'order_seq': 50},
    {'code': 'KAOS', 'name': 'Kaos / T-Shirt', 'sku_prefix': 'KAO', 'order_seq': 60},
    {'code': 'HOODIE', 'name': 'Hoodie', 'sku_prefix': 'HDI', 'order_seq': 70},
    {'code': 'ROK', 'name': 'Rok', 'sku_prefix': 'RSK', 'order_seq': 80},
    {'code': 'CELANA', 'name': 'Celana', 'sku_prefix': 'CLN', 'order_seq': 90},
    {'code': 'DRESS', 'name': 'Dress', 'sku_prefix': 'DRS', 'order_seq': 100},
    {'code': 'BLOUSE', 'name': 'Blouse', 'sku_prefix': 'BLS', 'order_seq': 110},
    {'code': 'KEMEJA', 'name': 'Kemeja', 'sku_prefix': 'KMJ', 'order_seq': 120},
    {'code': 'SET', 'name': 'Set/Setelan', 'sku_prefix': 'SET', 'order_seq': 130},
    {'code': 'LAINNYA', 'name': 'Lainnya', 'sku_prefix': 'OTH', 'order_seq': 999},
]

# Pemetaan kosakata LAMA (T2 — 4 kamus yang tidak pernah bertemu) → kategori master.
LEGACY_CATEGORY_MAP = {
    'sweater': 'SWEATER', 'sweater rajut': 'SWEATER', 'rajut': 'SWEATER',
    'cardigan': 'CARDIGAN', 'kardigan': 'CARDIGAN',
    'vest': 'VEST', 'rompi': 'VEST',
    'jacket': 'JACKET', 'jaket': 'JACKET', 'outerwear': 'JACKET',
    'polo': 'POLO', 'polo shirt': 'POLO',
    'kaos': 'KAOS', 't-shirt': 'KAOS', 'tshirt': 'KAOS', 'kaos/t-shirt': 'KAOS',
    'hoodie': 'HOODIE',
    'rok': 'ROK', 'skirt': 'ROK',
    'celana': 'CELANA', 'kulot': 'CELANA', 'pants': 'CELANA',
    'dress': 'DRESS', 'gamis': 'DRESS',
    'blouse': 'BLOUSE', 'blus': 'BLOUSE',
    'kemeja': 'KEMEJA', 'shirt': 'KEMEJA',
    'set': 'SET', 'setelan': 'SET', 'set/setelan': 'SET',
    'other': 'LAINNYA', 'lainnya': 'LAINNYA', 'general': 'LAINNYA', '': 'LAINNYA',
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


def _f(v, default=0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return float(default)


# ══════════════════════════════════════════════════════════════════════════════
# T1 — SATU definisi "model masih hidup"
# ══════════════════════════════════════════════════════════════════════════════
# `active: {$ne: False}` juga cocok untuk dokumen LAMA yang **tidak punya** field
# `active` (promosi R&D menulis `status: 'active'` saja). Itulah inti bug T1:
# pengecekan duplikat dulu memakai `{active: True}` sehingga dokumen promosi
# ada di luar jangkauan ⇒ kode kembar diterima HTTP 200.
LIVE_MODEL_FILTER = {'active': {'$ne': False}, 'status': {'$ne': 'inactive'}}


def live_model_filter(extra: dict = None) -> dict:
    q = dict(LIVE_MODEL_FILTER)
    if extra:
        q.update(extra)
    return q


def model_is_live(doc: dict) -> bool:
    if not doc:
        return False
    if doc.get('active') is False:
        return False
    return (doc.get('status') or '') != 'inactive'


# ══════════════════════════════════════════════════════════════════════════════
# F2 — master kategori
# ══════════════════════════════════════════════════════════════════════════════
async def seed_default_categories(db) -> int:
    """Idempoten: isi 14 kategori awal (K-2). Return jumlah yang BARU dibuat."""
    created = 0
    for c in DEFAULT_CATEGORIES:
        exists = await db[CATEGORIES].find_one({'code': c['code']}, {'_id': 0, 'id': 1})
        if exists:
            continue
        await db[CATEGORIES].insert_one({
            'id': _uid(), **c, 'description': '', 'active': True,
            'created_from': 'seed', 'created_at': _now(), 'updated_at': _now(),
        })
        created += 1
    if created:
        logger.info('  · master kategori produk ter-seed (%d baru)', created)
    return created


async def get_category(db, category_id: str) -> dict:
    if not category_id:
        return {}
    return await db[CATEGORIES].find_one({'id': category_id}, {'_id': 0}) or {}


async def get_category_by_code(db, code: str) -> dict:
    if not code:
        return {}
    return await db[CATEGORIES].find_one(
        {'code': str(code).strip().upper()}, {'_id': 0}) or {}


async def resolve_category_by_text(db, text: str, *, allow_create: bool = False) -> dict:
    """K-5a — kategori teks LAMA → entri master. Nol data hilang.

    Urutan: nama sama (case-insensitive) → kode sama → peta kosakata lama →
    (bila `allow_create`) buat entri master baru `created_from='migrasi'`.
    """
    raw = (text or '').strip()
    key = raw.lower()
    if raw:
        doc = await db[CATEGORIES].find_one(
            {'name': {'$regex': f'^{_re_escape(raw)}$', '$options': 'i'}}, {'_id': 0})
        if doc:
            return doc
        doc = await db[CATEGORIES].find_one({'code': raw.upper()}, {'_id': 0})
        if doc:
            return doc
    mapped = LEGACY_CATEGORY_MAP.get(key)
    if mapped:
        doc = await get_category_by_code(db, mapped)
        if doc:
            return doc
    if not allow_create:
        return {}
    code = _slug(raw) or 'LAINNYA'
    base, i = code, 1
    while await db[CATEGORIES].find_one({'code': code}, {'_id': 0, 'id': 1}):
        i += 1
        code = f'{base}{i}'[:32]
    doc = {
        'id': _uid(), 'code': code, 'name': raw or 'Lainnya',
        'sku_prefix': (_slug(raw) or 'OTH')[:3], 'order_seq': 900,
        'description': 'Dibuat otomatis oleh migrasi kategori (K-5a).',
        'active': True, 'created_from': 'migrasi',
        'created_at': _now(), 'updated_at': _now(),
    }
    await db[CATEGORIES].insert_one(doc)
    return doc


def _slug(s: str) -> str:
    import re as _re
    return _re.sub(r'[^A-Z0-9]', '', (s or '').upper())[:32]


def _re_escape(s: str) -> str:
    import re as _re
    return _re.escape(s)


# ══════════════════════════════════════════════════════════════════════════════
# F3 — SATU penulis stempel kategori (aturan #2)
# ══════════════════════════════════════════════════════════════════════════════
def apply_category(doc: dict, cat: dict) -> dict:
    """Stempel kategori ke dokumen (model / FG / item katalog).

    `category` legacy TETAP disinkronkan (= `category_name`) karena 34 endpoint,
    FG, dan katalog sudah membacanya — memutusnya akan mematikan fitur lama.
    """
    cat = cat or {}
    doc['category_id'] = cat.get('id')
    doc['category_code'] = cat.get('code') or ''
    doc['category_name'] = cat.get('name') or ''
    doc['category'] = cat.get('name') or doc.get('category') or ''
    return doc


def category_patch(cat: dict) -> dict:
    """Fragment `$set` kategori (untuk update/propagasi)."""
    cat = cat or {}
    return {
        'category_id': cat.get('id'),
        'category_code': cat.get('code') or '',
        'category_name': cat.get('name') or '',
        'category': cat.get('name') or '',
    }


# ══════════════════════════════════════════════════════════════════════════════
# F4 — K-1A: kode model otomatis dari `sku_prefix`
# ══════════════════════════════════════════════════════════════════════════════
async def next_model_code(db, cat: dict, *, width: int = 4) -> str:
    """`VST-0001` — counter atomik per prefix kategori (aman saat balapan).

    Format SKU varian **tidak** disentuh: SKU tetap `{MODEL}-{WARNA}-{SIZE}`,
    jadi hasil akhirnya `VST-0001-NVY-M` — kategori kelihatan di SKU tanpa
    migrasi apa pun (keputusan K-1A).
    """
    from utils.counters import next_counter

    prefix = ((cat or {}).get('sku_prefix') or 'OTH').strip().upper() or 'OTH'
    for _ in range(50):
        seq = await next_counter(db, f'model_code_{prefix}', namespace='rahaza')
        code = f'{prefix}-{str(seq).zfill(width)}'
        clash = await db.rahaza_models.find_one({'code': code}, {'_id': 0, 'id': 1})
        if not clash:
            return code
    raise RuntimeError(f'gagal membuat kode model unik untuk prefix {prefix}')


# ══════════════════════════════════════════════════════════════════════════════
# F5 — urutan resolusi HPP (aturan #4)
# ══════════════════════════════════════════════════════════════════════════════
def resolve_hpp(model: dict) -> tuple:
    """(hpp, source) — **HPP BOM** → HPP R&D → `base_hpp` manual → 0.

    Sumbernya IKUT dilaporkan supaya layar tidak pernah menampilkan angka tanpa asal.

    2026-08-23 — sumber baru **'bom'** (`hpp_bom`) DIDAHULUKAN. Ia lahir dari
    `core/product_costing`: BOM × harga bahan hasil PEMBELIAN (rata-rata bergerak)
    + upah CMT + upah cutting/internal. Ini melanjutkan keputusan pemilik sesi #30
    ("harga jangan dari ketikan master") ke tingkat produk jadi. Model yang BELUM
    pernah dihitung tidak punya `hpp_bom` ⇒ angkanya TIDAK berubah sama sekali.

    Kenapa `hpp_rnd` ada: `rahaza_models.hpp` dipakai 34 pintu lama sebagai
    "HPP yang berlaku", jadi ia tetap menyimpan **nilai efektif** (kalau tidak,
    setiap pembaca lama akan melihat 0 untuk produk manual — itu P1b lagi).
    Karena itu nilai **asal R&D** disimpan terpisah di `hpp_rnd`. Tanpa pemisahan
    ini, produk manual (`hpp == base_hpp`) akan salah dilaporkan bersumber 'rnd'.

    Dokumen LAMA (sebelum `hpp_rnd` ada) tetap terbaca: `hpp` dianggap dari R&D
    bila nilainya berbeda dari `base_hpp` (atau `base_hpp` kosong).
    """
    model = model or {}
    bom = _f(model.get('hpp_bom'))
    if bom > 0:
        return round(bom, 2), 'bom'
    rnd = _f(model.get('hpp_rnd'))
    if rnd <= 0:
        legacy = _f(model.get('hpp'))
        base_now = _f(model.get('base_hpp'))
        if legacy > 0 and (base_now <= 0 or abs(legacy - base_now) > 0.0001):
            rnd = legacy
    if rnd > 0:
        return round(rnd, 2), 'rnd'
    base = _f(model.get('base_hpp'))
    if base > 0:
        return round(base, 2), 'manual'
    return 0.0, 'none'


def master_images(model: dict) -> list:
    """Foto MASTER produk (F4.3) → ``[{url, caption, from}]``.

    KENAPA INI PERLU (cacat D13)
    ----------------------------
    Foto desain sudah ada sejak R&D: `dewi_rnd_styles.design_images` dibawa ke
    `rahaza_models.image_paths` saat style dipromosikan ke master. Tetapi item
    katalog **tidak pernah menyalinnya**, sehingga marketing memulai dari NOL foto
    untuk setiap toko — dan yang benar-benar terjadi bukan "marketing memotret
    ulang", melainkan **katalog tanpa foto**: produk tidak bisa dikenali di layar,
    dan pemeriksaan "produk ini yang mana?" dilakukan dengan menebak dari nama.

    Foto master **baca-saja** di layar katalog (miliknya R&D). Foto versi
    marketplace tetap diunggah marketing ke `images[]` dan itulah yang dipakai
    sebagai `primary_image` bila ada.

    Menerima dua bentuk yang benar-benar dipakai di DB:
      * `image_paths: ["/uploads/...", ...]`             (dari promote-to-production)
      * `reference_images: [{url, title}, ...]`          (GAP-6, foto referensi produksi)
    """
    model = model or {}
    out: list = []
    seen: set = set()

    def _add(url, caption, src):
        u = str(url or '').strip()
        if not u or u in seen:
            return
        seen.add(u)
        out.append({'url': u, 'caption': str(caption or '').strip(), 'from': src})

    for p in (model.get('image_paths') or []):
        if isinstance(p, dict):
            _add(p.get('url') or p.get('path'), p.get('title') or p.get('caption'), 'rnd_style')
        else:
            _add(p, '', 'rnd_style')
    for p in (model.get('reference_images') or []):
        if isinstance(p, dict):
            _add(p.get('url') or p.get('path'), p.get('title') or p.get('caption'), 'model')
        else:
            _add(p, '', 'model')
    return out


def master_display_fields(model: dict) -> dict:
    """Field master yang DISALIN ke FG & item katalog (harus punya penyegar — M7)."""
    hpp, src = resolve_hpp(model)
    return {
        'category_id': model.get('category_id'),
        'category_code': model.get('category_code') or '',
        'category_name': model.get('category_name') or model.get('category') or '',
        'category': model.get('category_name') or model.get('category') or '',
        'weight_gram': _f(model.get('weight_gram')),
        'hpp': hpp,
        'hpp_source': src,
        'retail_price_master': _f(model.get('retail_price')),
    }


# ══════════════════════════════════════════════════════════════════════════════
# F3/F8 — propagasi master → FG → item katalog (aturan #3)
# ══════════════════════════════════════════════════════════════════════════════
async def propagate_master_changes(db, model: dict, *, refresh_name: bool = False) -> dict:
    """Turunkan kategori/berat/HPP/harga resmi dari master ke FG + item katalog.

    Hanya menyentuh dokumen yang **tertaut `model_id`** — tidak pernah menebak.
    `refresh_name=True` juga menyegarkan nama tampilan (dipakai
    `POST /refresh-from-master`); saat penyuntingan biasa nama katalog dibiarkan
    karena nama jualan per platform memang boleh berbeda.
    """
    if not (model or {}).get('id'):
        return {'fg': 0, 'items': 0}
    fields = master_display_fields(model)
    now = _now()

    fg_patch = {k: v for k, v in fields.items() if k != 'retail_price_master'}
    fg_patch['updated_at'] = now
    res_fg = await db.rahaza_materials.update_many(
        {'type': 'fg', 'model_id': model['id']}, {'$set': fg_patch})

    fg_ids = [m['id'] async for m in db.rahaza_materials.find(
        {'type': 'fg', 'model_id': model['id']}, {'_id': 0, 'id': 1})]

    item_patch = dict(fields)
    item_patch['updated_at'] = now
    item_q = {'$or': [{'model_id': model['id']}]}
    if fg_ids:
        item_q['$or'].extend([{'fg_material_id': {'$in': fg_ids}},
                              {'material_id': {'$in': fg_ids}}])
    res_items = await db.marketing_catalog_items.update_many(item_q, {'$set': item_patch})

    if refresh_name and model.get('name'):
        # nama item = nama tampilan FG (nama model + varian) supaya tidak menghapus
        # perbedaan varian; dikerjakan per-item karena teksnya berbeda tiap varian.
        async for it in db.marketing_catalog_items.find(item_q, {'_id': 0, 'id': 1,
                                                                'fg_material_id': 1,
                                                                'material_id': 1}):
            fid = it.get('fg_material_id') or it.get('material_id')
            fg = await db.rahaza_materials.find_one({'id': fid}, {'_id': 0, 'name': 1}) if fid else None
            new_name = (fg or {}).get('name') or model.get('name')
            await db.marketing_catalog_items.update_one(
                {'id': it['id']}, {'$set': {'name': new_name, 'updated_at': now}})

    return {'fg': res_fg.modified_count, 'items': res_items.modified_count,
            'fg_ids': fg_ids}


# ══════════════════════════════════════════════════════════════════════════════
# K-9a — produk/varian dihentikan ⇒ item katalog ikut dinonaktifkan
# ══════════════════════════════════════════════════════════════════════════════
async def deactivate_catalog_items_for_model(db, model_id: str) -> list:
    """Nonaktifkan item katalog yang menawarkan produk ini + kembalikan DAFTARNYA.

    Daftar terdampak dikembalikan supaya staf tahu apa yang berubah — bukan
    perubahan senyap (keputusan K-9a).
    """
    fg_ids = [m['id'] async for m in db.rahaza_materials.find(
        {'type': 'fg', 'model_id': model_id}, {'_id': 0, 'id': 1})]
    var_ids = [v['id'] async for v in db.rahaza_model_variants.find(
        {'model_id': model_id}, {'_id': 0, 'id': 1})]
    q = {'is_active': {'$ne': False}, '$or': [{'model_id': model_id}]}
    if fg_ids:
        q['$or'].extend([{'fg_material_id': {'$in': fg_ids}}, {'material_id': {'$in': fg_ids}}])
    if var_ids:
        q['$or'].append({'variant_id': {'$in': var_ids}})
    affected = await db.marketing_catalog_items.find(
        q, {'_id': 0, 'id': 1, 'sku': 1, 'name': 1, 'catalog_id': 1, 'platform': 1}
    ).to_list(2000)
    if affected:
        await db.marketing_catalog_items.update_many(
            {'id': {'$in': [a['id'] for a in affected]}},
            {'$set': {'is_active': False, 'deactivated_reason': 'produk dihentikan (K-9a)',
                      'deactivated_at': _now(), 'updated_at': _now()}})
    return affected


async def deactivate_catalog_items_for_variant(db, variant_id: str) -> list:
    """K-9a untuk satu VARIAN (SKU) yang dihentikan."""
    v = await db.rahaza_model_variants.find_one({'id': variant_id}, {'_id': 0}) or {}
    sku = (v.get('sku') or '').strip()
    fg = await db.rahaza_materials.find_one(
        {'type': 'fg', 'code': sku}, {'_id': 0, 'id': 1}) if sku else None
    q = {'is_active': {'$ne': False}, '$or': [{'variant_id': variant_id}]}
    if sku:
        q['$or'].append({'variant_sku': sku})
    if fg:
        q['$or'].extend([{'fg_material_id': fg['id']}, {'material_id': fg['id']}])
    affected = await db.marketing_catalog_items.find(
        q, {'_id': 0, 'id': 1, 'sku': 1, 'name': 1, 'catalog_id': 1, 'platform': 1}
    ).to_list(2000)
    if affected:
        await db.marketing_catalog_items.update_many(
            {'id': {'$in': [a['id'] for a in affected]}},
            {'$set': {'is_active': False, 'deactivated_reason': 'varian dihentikan (K-9a)',
                      'deactivated_at': _now(), 'updated_at': _now()}})
    return affected
