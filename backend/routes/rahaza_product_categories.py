"""routes.rahaza_product_categories — F2 · MASTER KATEGORI PRODUK (K-2).

Kenapa koleksi baru, bukan menambah dropdown lagi: kategori dipakai untuk
**filter & grouping** di katalog marketing, tetapi selama ini (a) nilainya teks
bebas tanpa validasi (P3), (b) ada **4 kosakata** yang tidak pernah bertemu (T2),
dan (c) `rahaza_materials.category` bermakna ganda (T4). Satu master + `category_id`
membuat grouping bisa dipercaya.

Keputusan owner K-1A: setiap kategori punya **`sku_prefix`**; kode produk dibuat
otomatis `VST-0001` dari prefix itu (format SKU varian TIDAK diubah).

Endpoint (semua di bawah `/api/rahaza/product-categories`):
  GET    /                 daftar kategori (dipakai SEMUA dropdown)
  GET    /{cid}            detail + jumlah produk yang memakainya
  POST   /                 tambah kategori
  PUT    /{cid}            ubah nama / prefix / urutan / aktif
  DELETE /{cid}            nonaktifkan — **409 bila masih dipakai produk** (PR-8)
"""
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from auth import log_activity, require_auth, serialize_doc
from core import product_master as pm
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/rahaza/product-categories', tags=['rahaza-product-categories'])

COLL = 'rahaza_product_categories'


def _now():
    return datetime.now(timezone.utc)


async def _require_internal(request: Request):
    """RBAC master produk (sama dengan master model): staff internal saja."""
    user = await require_auth(request)
    role = (user.get('role') or '').lower()
    if role in ('cmt_vendor', 'vendor', 'klien_maklon'):
        raise HTTPException(403, 'Akses master hanya untuk staff internal.')
    return user


class CategoryIn(BaseModel):
    code: Optional[str] = None
    name: str
    sku_prefix: Optional[str] = None
    order_seq: Optional[int] = Field(default=500)
    description: Optional[str] = ''


class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    sku_prefix: Optional[str] = None
    order_seq: Optional[int] = None
    description: Optional[str] = None
    active: Optional[bool] = None


async def _usage_count(db, cid: str) -> dict:
    """Berapa dokumen yang memakai kategori ini (dipakai PR-8 & layar)."""
    models = await db.rahaza_models.count_documents(
        pm.live_model_filter({'category_id': cid}))
    fg = await db.rahaza_materials.count_documents({'type': 'fg', 'category_id': cid})
    items = await db.marketing_catalog_items.count_documents(
        {'category_id': cid, 'is_active': {'$ne': False}})
    return {'models': models, 'fg': fg, 'catalog_items': items,
            'total': models + fg + items}


@router.get('')
async def list_categories(request: Request, include_inactive: bool = False,
                          with_usage: bool = False):
    """Daftar kategori produk (urut `order_seq`, lalu nama)."""
    await require_auth(request)
    db = get_db()
    # seed idempoten: dropdown tidak boleh pernah kosong di container segar
    if await db[COLL].count_documents({}) == 0:
        await pm.seed_default_categories(db)
    q = {} if include_inactive else {'active': {'$ne': False}}
    rows = await db[COLL].find(q, {'_id': 0}).sort(
        [('order_seq', 1), ('name', 1)]).to_list(500)
    if with_usage:
        for r in rows:
            r['usage'] = await _usage_count(db, r['id'])
    return {'ok': True, 'categories': serialize_doc(rows), 'total': len(rows)}


@router.get('/{cid}')
async def get_category(cid: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db[COLL].find_one({'id': cid}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Kategori tidak ditemukan.')
    doc['usage'] = await _usage_count(db, cid)
    return {'ok': True, 'category': serialize_doc(doc)}


@router.post('', status_code=201)
async def create_category(data: CategoryIn, request: Request):
    user = await _require_internal(request)
    db = get_db()
    name = (data.name or '').strip()
    if not name:
        raise HTTPException(400, 'Nama kategori wajib diisi.')
    code = (data.code or pm._slug(name) or 'KAT').strip().upper()
    prefix = (data.sku_prefix or pm._slug(name)[:3] or 'OTH').strip().upper()
    if not prefix.isalnum():
        raise HTTPException(400, 'Prefix SKU hanya boleh huruf/angka.')
    if await db[COLL].find_one({'code': code}, {'_id': 0, 'id': 1}):
        raise HTTPException(409, f"Kode kategori '{code}' sudah ada.")
    dupe_prefix = await db[COLL].find_one(
        {'sku_prefix': prefix, 'active': {'$ne': False}}, {'_id': 0, 'name': 1})
    if dupe_prefix:
        raise HTTPException(
            409, f"Prefix SKU '{prefix}' sudah dipakai kategori '{dupe_prefix.get('name')}'. "
                 'Prefix harus unik supaya kode produk otomatis tidak tertukar.')
    doc = {
        'id': pm._uid(), 'code': code, 'name': name, 'sku_prefix': prefix,
        'order_seq': int(data.order_seq if data.order_seq is not None else 500),
        'description': (data.description or '').strip(),
        'active': True, 'created_from': 'manual',
        'created_at': _now(), 'updated_at': _now(),
    }
    await db[COLL].insert_one(doc)
    await log_activity(user['id'], user.get('name', ''), 'create',
                       'rahaza.product_category', code)
    return {'ok': True, 'category': serialize_doc(doc)}


@router.put('/{cid}')
async def update_category(cid: str, data: CategoryUpdate, request: Request):
    user = await _require_internal(request)
    db = get_db()
    cur = await db[COLL].find_one({'id': cid}, {'_id': 0})
    if not cur:
        raise HTTPException(404, 'Kategori tidak ditemukan.')

    patch = {}
    if data.name is not None:
        if not data.name.strip():
            raise HTTPException(400, 'Nama kategori tidak boleh kosong.')
        patch['name'] = data.name.strip()
    if data.sku_prefix is not None:
        prefix = data.sku_prefix.strip().upper()
        if not prefix.isalnum():
            raise HTTPException(400, 'Prefix SKU hanya boleh huruf/angka.')
        clash = await db[COLL].find_one(
            {'sku_prefix': prefix, 'id': {'$ne': cid}, 'active': {'$ne': False}},
            {'_id': 0, 'name': 1})
        if clash:
            raise HTTPException(409, f"Prefix SKU '{prefix}' sudah dipakai '{clash.get('name')}'.")
        patch['sku_prefix'] = prefix
    if data.order_seq is not None:
        patch['order_seq'] = int(data.order_seq)
    if data.description is not None:
        patch['description'] = data.description.strip()
    if data.active is not None:
        if data.active is False:
            usage = await _usage_count(db, cid)
            if usage['total'] > 0:
                raise HTTPException(
                    409, f"Kategori '{cur.get('name')}" + "' masih dipakai "
                         f"{usage['models']} produk / {usage['fg']} barang jadi / "
                         f"{usage['catalog_items']} item katalog — tidak bisa dinonaktifkan.")
        patch['active'] = bool(data.active)
    if not patch:
        return {'ok': True, 'category': serialize_doc(cur), 'message': 'Tidak ada perubahan.'}

    patch['updated_at'] = _now()
    await db[COLL].update_one({'id': cid}, {'$set': patch})
    after = await db[COLL].find_one({'id': cid}, {'_id': 0})

    # nama kategori berubah ⇒ propagasi ke SEMUA produk/FG/item yang memakainya
    # (menutup P2b: salinan tanpa penyegar = laporan yang berbohong dengan sopan)
    if 'name' in patch or 'sku_prefix' in patch:
        cat_patch = pm.category_patch(after)
        cat_patch['updated_at'] = _now()
        await db.rahaza_models.update_many({'category_id': cid}, {'$set': cat_patch})
        await db.rahaza_materials.update_many({'category_id': cid}, {'$set': cat_patch})
        await db.marketing_catalog_items.update_many({'category_id': cid}, {'$set': cat_patch})

    await log_activity(user['id'], user.get('name', ''), 'update',
                       'rahaza.product_category', cid)
    return {'ok': True, 'category': serialize_doc(after)}


@router.delete('/{cid}')
async def deactivate_category(cid: str, request: Request):
    """Nonaktifkan kategori. **PR-8**: ditolak 409 bila masih dipakai."""
    user = await _require_internal(request)
    db = get_db()
    cur = await db[COLL].find_one({'id': cid}, {'_id': 0})
    if not cur:
        raise HTTPException(404, 'Kategori tidak ditemukan.')
    usage = await _usage_count(db, cid)
    if usage['total'] > 0:
        raise HTTPException(
            409, f"Kategori '{cur.get('name')}' masih dipakai "
                 f"{usage['models']} produk / {usage['fg']} barang jadi / "
                 f"{usage['catalog_items']} item katalog — pindahkan dulu, "
                 'baru kategori ini bisa dinonaktifkan.')
    await db[COLL].update_one({'id': cid}, {'$set': {'active': False, 'updated_at': _now()}})
    await log_activity(user['id'], user.get('name', ''), 'deactivate',
                       'rahaza.product_category', cid)
    return {'ok': True, 'status': 'deactivated', 'usage': usage}
