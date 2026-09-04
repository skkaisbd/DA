"""
Marketing Catalog - Management
Catalog CRUD + dashboard + utilities
"""
import uuid
import html
import re
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri (middleware
# hanya menolak permintaan yang MENYEBUT toko, ia tidak tahu isi jawaban).
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth, log_activity
from core import catalog_stock as _cstock   # F7: SSOT satu rumus stok jual
from core import product_master as _pm      # F3–F6: SSOT kategori/HPP/harga resmi

router = APIRouter(prefix='/api/marketing/catalogs', tags=['Marketing-Catalog-mgmt'])

# Photo upload settings
PRODUCT_UPLOAD_ROOT = Path('/app/uploads/products')
PRODUCT_UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
MAX_PHOTO_BYTES = 5 * 1024 * 1024
ALLOWED_MIMES = {'image/jpeg', 'image/png', 'image/webp'}
ALLOWED_EXT = {'jpg', 'jpeg', 'png', 'webp'}

# Helper functions
def _uid():
    return str(uuid.uuid4())

def _now():
    return datetime.now(timezone.utc)

def _san(value: str, max_len: int = 500) -> str:
    if not isinstance(value, str):
        return value
    return html.escape(value.strip())[:max_len]

def _s(doc: dict) -> dict:
    if doc is None:
        return {}
    out = dict(doc)
    out.pop('_id', None)
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out

def _stock_status(qty: float, threshold: float) -> str:
    if qty <= 0:
        return 'out_of_stock'
    elif qty <= threshold:
        return 'low_stock'
    else:
        return 'in_stock'

async def _refresh_catalog_stats(db, catalog_id: str):
    items = await db.marketing_catalog_items.find(
        {'catalog_id': catalog_id, 'is_active': True},
        {'_id': 0, 'stock_quantity': 1, 'stock_status': 1}
    ).to_list(500)
    total_stock = sum(float(i.get('stock_quantity', 0)) for i in items)
    low = sum(1 for i in items if i.get('stock_status') == 'low_stock')
    out = sum(1 for i in items if i.get('stock_status') == 'out_of_stock')
    await db.marketing_catalogs.update_one(
        {'id': catalog_id},
        {'$set': {
            'item_count': len(items),
            'total_stock': total_stock,
            'low_stock_count': low,
            'out_of_stock_count': out,
            'updated_at': _now(),
        }}
    )


# Pydantic models
# ─── Pydantic Models ──────────────────────────────────────────────────────────

class CatalogCreate(BaseModel):
    account_id: str
    name: str
    description: Optional[str] = ''
    platform: Optional[str] = ''     # inherited from account, stored for quick filter
    is_active: Optional[bool] = True


class CatalogUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CatalogItemCreate(BaseModel):
    sku: str
    name: str
    description: Optional[str] = ''
    price: Optional[float] = Field(default=0, ge=0)          # selling price
    original_price: Optional[float] = Field(default=0, ge=0) # HPP / base price
    platform_price: Optional[float] = 0 # actual listed price on platform (can differ)
    stock_quantity: Optional[float] = Field(default=0, ge=0)
    stock_alert_threshold: Optional[float] = Field(default=10, ge=0)
    material_id: Optional[str] = None   # optional link to WMS material (rahaza_materials)
    platform_url: Optional[str] = ''
    images: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    weight_gram: Optional[float] = Field(default=0, ge=0)
    category: Optional[str] = ''
    variant_info: Optional[str] = ''    # e.g. "Warna: Merah, Size: L"
    is_active: Optional[bool] = True


class CatalogItemUpdate(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = Field(default=None, ge=0)
    original_price: Optional[float] = Field(default=None, ge=0)
    platform_price: Optional[float] = None
    stock_quantity: Optional[float] = Field(default=None, ge=0)
    stock_alert_threshold: Optional[float] = Field(default=None, ge=0)
    material_id: Optional[str] = None
    platform_url: Optional[str] = None
    images: Optional[List[str]] = None
    tags: Optional[List[str]] = None
    weight_gram: Optional[float] = Field(default=None, ge=0)
    category: Optional[str] = None
    variant_info: Optional[str] = None
    is_active: Optional[bool] = None


class StockUpdateBody(BaseModel):
    stock_quantity: float = Field(ge=0)
    notes: Optional[str] = ''


class CatalogItemFromFG(BaseModel):
    """Create catalog item by picking from FG master (rahaza_materials, type='fg').
    Backend auto-fills SKU/name/color/category from FG; user only sets selling price + URL.
    """
    fg_material_id: str  # UUID dari rahaza_materials
    price: float = Field(ge=0)                              # selling price (required)
    original_price: Optional[float] = Field(default=0, ge=0)       # HPP/coret price (optional)
    platform_price: Optional[float] = 0       # actual listed price
    platform_url: Optional[str] = ''
    images: Optional[List[str]] = []
    tags: Optional[List[str]] = []
    stock_alert_threshold: Optional[float] = Field(default=10, ge=0)
    description_override: Optional[str] = ''  # custom description (optional)


class BulkStockUpdate(BaseModel):
    updates: List[dict]   # [{ item_id, stock_quantity, notes }]


# ═══════════════════════════════════════════════════════════════════════════════

@router.post('')
async def create_catalog(data: CatalogCreate, request: Request):
    """Buat catalog baru untuk satu akun platform."""
    user = await require_auth(request)
    db = get_db()

    account = await db.marketing_platform_accounts.find_one({'id': data.account_id}, {'_id': 0})
    if not account:
        raise HTTPException(404, 'Akun platform tidak ditemukan.')

    # Use platform from account if not provided
    platform = data.platform or account.get('platform', '')

    doc = {
        'id': _uid(),
        'account_id': data.account_id,
        # BUG DITUTUP 2026-08-12 — dulu `account.get('name')`, padahal master toko
        # memakai field `account_name`. Akibatnya SETIAP katalog lahir dengan
        # `account_name: ''` dan layar katalog menampilkan kolom toko kosong.
        'account_name': account.get('account_name') or account.get('name') or '',
        'platform': platform,
        'name': _san(data.name, 200),
        'description': _san(data.description or '', 1000),
        'is_active': data.is_active,
        'item_count': 0,
        'total_stock': 0.0,
        'low_stock_count': 0,
        'out_of_stock_count': 0,
        'created_at': _now(),
        'updated_at': _now(),
        'created_by': user.get('id', ''),
    }
    await db.marketing_catalogs.insert_one(doc)
    return {'ok': True, 'catalog': _s(doc)}


@router.get('')
async def list_catalogs(
    request: Request,
    account_id: Optional[str] = None,
    platform: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
):
    """List semua katalog dengan filter opsional."""
    user = await require_auth(request)
    db = get_db()
    # F14 — katalog toko tidak boleh kosong sementara order/sample sudah ada:
    # tanpa katalog, SKU order yatim dan HPP sample tidak punya sumber.
    from core.marketing_master_seed import ensure_demo_catalogs
    await ensure_demo_catalogs(db)

    q = await _scope.scope_filter(db, user, {})
    if account_id:
        q['account_id'] = account_id
    if platform:
        q['platform'] = platform
    if is_active is not None:
        q['is_active'] = is_active
    if search:
        q['name'] = {'$regex': search, '$options': 'i'}

    docs = await db.marketing_catalogs.find(q, {'_id': 0}).sort('created_at', -1).to_list(500)
    return {'ok': True, 'catalogs': [_s(d) for d in docs], 'total': len(docs)}


@router.get('/stock-dashboard')
async def stock_dashboard(
    request: Request,
    account_id: Optional[str] = None,
    platform: Optional[str] = None,
):
    """
    Ringkasan stok lintas semua katalog (atau filter per account/platform).
    Returns: total_items, in_stock, low_stock, out_of_stock, catalogs summary.
    """
    user = await require_auth(request)
    db = get_db()

    q: dict = await _scope.scope_filter(db, user, {})
    if account_id:
        q['account_id'] = account_id
    if platform:
        q['platform'] = platform

    items = await db.marketing_catalog_items.find(q, {'_id': 0,
        'catalog_id': 1, 'stock_quantity': 1, 'stock_alert_threshold': 1,
        'stock_status': 1, 'name': 1, 'sku': 1, 'price': 1, 'platform': 1,
        'account_id': 1, 'is_active': 1,
    }).to_list(500)

    active_items = [i for i in items if i.get('is_active', True)]
    total = len(active_items)
    in_stock = sum(1 for i in active_items if i.get('stock_status') == 'in_stock')
    low_stock = sum(1 for i in active_items if i.get('stock_status') == 'low_stock')
    out_stock = sum(1 for i in active_items if i.get('stock_status') == 'out_of_stock')

    # Low stock items list (top 20 by stock_quantity asc)
    low_items = sorted(
        [i for i in active_items if i.get('stock_status') in ('low_stock', 'out_of_stock')],
        key=lambda x: x.get('stock_quantity', 0)
    )[:20]

    # Per-platform breakdown
    platform_summary: dict = {}
    for i in active_items:
        p = i.get('platform', 'Other')
        if p not in platform_summary:
            platform_summary[p] = {'platform': p, 'total': 0, 'in_stock': 0, 'low_stock': 0, 'out_of_stock': 0}
        platform_summary[p]['total'] += 1
        st = i.get('stock_status', 'in_stock')
        platform_summary[p][st] = platform_summary[p].get(st, 0) + 1

    # Get last sync info
    last_sync = await db.marketing_stock_syncs.find_one(
        q, {'_id': 0}, sort=[('synced_at', -1)]
    )

    return {
        'ok': True,
        'summary': {
            'total_items': total,
            'in_stock': in_stock,
            'low_stock': low_stock,
            'out_of_stock': out_stock,
            'health_pct': round(in_stock / total * 100, 1) if total else 0,
        },
        'low_stock_items': [_s(i) for i in low_items],
        'platform_breakdown': list(platform_summary.values()),
        'last_sync': _s(last_sync) if last_sync else None,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# FG MASTER INTEGRATION — REGISTERED HERE (BEFORE /{catalog_id}) for route precedence
# ═══════════════════════════════════════════════════════════════════════════════

@router.get('/fg-products')
async def search_fg_products(
    request: Request,
    q: Optional[str] = Query(None, description="Search by FG code or name"),
    limit: int = Query(50, ge=1, le=200),
):
    """Search FG (Finished Goods) products dari master inventory (rahaza_materials, type='fg').
    
    Used by Catalog Item creation flow untuk pick produk dari master, bukan input manual.
    Returns: List of FG with current stock from rahaza_material_stock.
    """
    await require_auth(request)
    db = get_db()
    
    query = {'type': 'fg', '$or': [{'active': True}, {'active': {'$exists': False}}]}
    if q and q.strip():
        search = q.strip()
        # Combine with the active filter
        query = {
            'type': 'fg',
            '$or': [{'active': True}, {'active': {'$exists': False}}],
            '$and': [
                {
                    '$or': [
                        {'name': {'$regex': search, '$options': 'i'}},
                        {'code': {'$regex': search, '$options': 'i'}},
                    ]
                }
            ],
        }
    
    materials = await db.rahaza_materials.find(query, {'_id': 0}).sort('name', 1).limit(limit).to_list(length=limit)
    
    # Get default active location
    default_loc = await db.rahaza_locations.find_one({'active': True}, {'_id': 0})
    loc_id = default_loc['id'] if default_loc else None
    
    # Attach stock info
    for mat in materials:
        if loc_id:
            stock_doc = await db.rahaza_material_stock.find_one(
                {'material_id': mat.get('id'), 'location_id': loc_id}, {'_id': 0}
            )
            mat['stock_qty'] = float(stock_doc.get('qty', 0)) if stock_doc else 0.0
        else:
            mat['stock_qty'] = 0.0
        mat['location_id'] = loc_id
    
    return {'ok': True, 'data': [_s(m) for m in materials], 'total': len(materials)}


@router.get('/master-products')
async def list_master_products_for_catalog(
    request: Request,
    q: Optional[str] = Query(None, description="Cari kode/nama produk atau varian"),
    account_id: Optional[str] = Query(None, description="Tandai varian yang SUDAH ada di katalog toko ini"),
    only_sellable: bool = Query(False, description="Hanya varian yang stok jualnya > 0"),
    limit: int = Query(60, ge=1, le=300),
):
    """Master produk internal (model R&D) + varian FG-nya, siap dipilih untuk katalog toko.

    KENAPA endpoint ini ada (bukan memakai `/fg-products` yang sudah ada)
    ---------------------------------------------------------------------
    `/fg-products` mengembalikan daftar FG **datar** tanpa induk produknya, tanpa
    HPP/harga resmi master, dan stoknya dibaca dari "lokasi aktif pertama" dengan
    `qty` mentah — angka yang bukan stok jual (karantina/blokir/reservasi ikut).
    Untuk mengisi katalog **9 toko**, staf butuh melihat: produk apa, varian mana,
    HPP-nya berapa, harga resminya berapa, stok jual berapa, dan **varian mana yang
    sudah ada di katalog toko itu** — supaya tidak memilih ulang yang sudah ada.
    Semua dibaca dari SSOT (`core.product_master`, `core.catalog_stock`).
    """
    await require_auth(request)
    db = get_db()

    mq: dict = {'$or': [{'active': True}, {'active': {'$exists': False}}]}
    if q and q.strip():
        rx = {'$regex': re.escape(q.strip()), '$options': 'i'}
        mq['$and'] = [{'$or': [{'name': rx}, {'code': rx}, {'category_name': rx}]}]
    models = await db.rahaza_models.find(mq, {'_id': 0}).sort('name', 1).limit(limit).to_list(limit)

    # varian FG per model
    model_ids = [m['id'] for m in models]
    fgs = await db.rahaza_materials.find(
        {'type': 'fg', 'model_id': {'$in': model_ids},
         '$or': [{'active': True}, {'active': {'$exists': False}}]},
        {'_id': 0}).sort('code', 1).to_list(2000)

    in_catalog: set = set()
    catalog_id = None
    if account_id:
        cat = await db.marketing_catalogs.find_one(
            {'account_id': account_id}, {'_id': 0, 'id': 1})
        if cat:
            catalog_id = cat['id']
            async for it in db.marketing_catalog_items.find(
                    {'catalog_id': catalog_id}, {'_id': 0, 'fg_material_id': 1}):
                if it.get('fg_material_id'):
                    in_catalog.add(it['fg_material_id'])

    by_model: dict = {}
    for fg in fgs:
        stock = await _cstock.sellable_stock(db, fg['id'])
        sellable = float(stock['available'])
        if only_sellable and sellable <= 0:
            continue
        by_model.setdefault(fg['model_id'], []).append({
            'fg_material_id': fg['id'],
            'code': fg.get('code') or '',
            'name': fg.get('name') or '',
            'color': fg.get('color') or '',
            'size_code': fg.get('size_code') or '',
            'unit': fg.get('unit') or 'pcs',
            'hpp': float(fg.get('hpp') or 0),
            # F14b — bahan dibawa ikut supaya layar yang memilih produk (mis.
            # Launching, Caption AI) tidak perlu menghitungnya sendiri. Kalau
            # tiap layar menghitung sendiri, suatu hari salah satunya memakai
            # aturan berbeda dan dua layar menyebut bahan berbeda untuk produk
            # yang sama.
            'composition': (fg.get('composition') or '').strip(),
            'sellable_stock': sellable,
            'onhand': float(stock['onhand']),
            'reserved': float(stock['reserved']),
            'in_catalog': fg['id'] in in_catalog,
        })

    out = []
    for m in models:
        variants = by_model.get(m['id'], [])
        if only_sellable and not variants:
            continue
        master = _pm.master_display_fields(m)
        # Bahan tingkat produk = gabungan komposisi varian (unik, urut muncul).
        # Kosong kalau master memang belum mencatatnya — dikatakan apa adanya,
        # bukan ditebak (layar menampilkan "belum dicatat di master").
        _comps: list = []
        for v in variants:
            c = v.get('composition') or ''
            if c and c not in _comps:
                _comps.append(c)
        out.append({
            'model_id': m['id'],
            'code': m.get('code') or '',
            'name': m.get('name') or '',
            'category_name': master.get('category_name') or m.get('category_name') or '',
            'material': ' / '.join(_comps),
            'hpp': float(master.get('hpp') or m.get('hpp') or 0),
            'hpp_source': master.get('hpp_source') or 'none',
            'retail_price_master': float(master.get('retail_price_master')
                                         or m.get('retail_price') or 0),
            'variant_count': len(variants),
            'in_catalog_count': sum(1 for v in variants if v['in_catalog']),
            'variants': variants,
        })

    return {'ok': True, 'catalog_id': catalog_id,
            'products': out,
            'total_products': len(out),
            'total_variants': sum(p['variant_count'] for p in out)}


class AssignFromMasterBody(BaseModel):
    """Isi katalog BANYAK toko sekaligus dari master produk internal."""
    account_ids: List[str] = Field(min_length=1)
    fg_material_ids: List[str] = Field(min_length=1)
    # 'master'  → harga jual awal = harga resmi master (K-3a)
    # 'kosong'  → harga jual 0, staf isi per toko nanti
    price_mode: str = 'master'
    stock_alert_threshold: Optional[float] = Field(default=10, ge=0)
    catalog_name: Optional[str] = None


@router.post('/assign-from-master')
async def assign_from_master(data: AssignFromMasterBody, request: Request):
    """Tambahkan produk master terpilih ke katalog BEBERAPA toko dalam satu aksi.

    KENAPA ini perlu ada
    --------------------
    Jalur yang sudah ada hanya bisa menambah **satu varian ke satu katalog** per
    permintaan. Untuk 9 toko × puluhan varian, itu ratusan klik — dan yang terjadi
    di lapangan bukan "staf sabar", melainkan **katalog dibiarkan kosong**. Katalog
    kosong berarti: item pesanan hasil impor tidak bisa ditautkan ke master ⇒ HPP
    dan **marjin per pesanan tidak bisa dihitung sama sekali**. Jadi tombol ini
    bukan kenyamanan, ia prasyarat angka marjin.

    Sifatnya:
      * **Idempoten** — varian yang sudah ada di katalog toko dilaporkan
        "sudah ada", bukan digandakan (kunci `catalog_id` + `fg_material_id`).
      * **Tidak gagal total** — satu varian bermasalah (non-aktif/produk
        dihentikan) hanya menolak varian itu, dengan alasan per baris.
      * Katalog toko **dibuatkan otomatis** kalau belum ada, memakai nama toko —
        supaya staf tidak harus tahu bahwa "katalog" adalah lapisan tersendiri.
      * HPP & harga resmi **selalu** dari master (bukan diketik), lewat
        `create_item_from_fg` yang sama dengan jalur satuan.
    """
    user = await require_auth(request)
    db = get_db()

    if data.price_mode not in ('master', 'kosong'):
        raise HTTPException(400, "price_mode harus 'master' atau 'kosong'")

    accounts = await db.marketing_platform_accounts.find(
        {'id': {'$in': data.account_ids}}, {'_id': 0}).to_list(200)
    found_ids = {a['id'] for a in accounts}
    missing = [a for a in data.account_ids if a not in found_ids]
    if missing:
        raise HTTPException(404, f"{len(missing)} toko tujuan tidak ditemukan — "
                                 'muat ulang daftar toko lalu coba lagi.')

    from routes.marketing_catalog_items import (          # lazy: hindari impor siklik
        create_item_from_fg as _create_item, _refresh_catalog_stats as _refresh_stats,
    )

    results = []
    tot_created = tot_skipped = tot_rejected = 0
    for acc in accounts:
        catalog = await db.marketing_catalogs.find_one(
            {'account_id': acc['id']}, {'_id': 0})
        catalog_created = False
        if not catalog:
            catalog = {
                'id': _uid(),
                'account_id': acc['id'],
                'account_name': acc.get('account_name') or acc.get('name') or '',
                'platform': acc.get('platform', ''),
                'name': _san(data.catalog_name
                             or f"Katalog {acc.get('account_name') or acc.get('account_code')}", 200),
                'description': 'Dibuat otomatis saat mengisi katalog dari master produk.',
                'is_active': True,
                'item_count': 0,
                'total_stock': 0.0,
                'low_stock_count': 0,
                'out_of_stock_count': 0,
                'created_at': _now(),
                'updated_at': _now(),
                'created_by': user.get('id', ''),
            }
            await db.marketing_catalogs.insert_one(dict(catalog))
            catalog.pop('_id', None)
            catalog_created = True

        created = skipped = rejected = 0
        notes = []
        for fg_id in data.fg_material_ids:
            opts = {'stock_alert_threshold': data.stock_alert_threshold}
            if data.price_mode == 'kosong':
                opts['harga_jual'] = 0
            doc, err = await _create_item(db, catalog, fg_id, opts, user)
            if err:
                status, msg = err
                if status == 409:
                    skipped += 1
                    notes.append({'fg_material_id': fg_id, 'action': 'sudah ada', 'why': msg})
                else:
                    rejected += 1
                    notes.append({'fg_material_id': fg_id, 'action': 'ditolak', 'why': msg})
                continue
            created += 1
            notes.append({'fg_material_id': fg_id, 'action': 'ditambahkan',
                          'sku': doc.get('sku'), 'name': doc.get('name'),
                          'hpp': doc.get('hpp'), 'harga_jual': doc.get('harga_jual'),
                          'stok_jual': doc.get('stock_quantity')})
        if created:
            await _refresh_stats(db, catalog['id'])

        tot_created += created
        tot_skipped += skipped
        tot_rejected += rejected
        results.append({
            'account_id': acc['id'],
            'account_code': acc.get('account_code'),
            'account_name': acc.get('account_name') or acc.get('name'),
            'catalog_id': catalog['id'],
            'catalog_name': catalog.get('name'),
            'catalog_created': catalog_created,
            'created': created, 'skipped': skipped, 'rejected': rejected,
            'notes': notes[:200],
        })

    await log_activity(
        user.get('id', ''), user.get('name') or user.get('email', 'system'),
        'assign_from_master', 'marketing_catalog_items',
        f"Isi katalog dari master produk: {len(accounts)} toko × "
        f"{len(data.fg_material_ids)} varian ⇒ {tot_created} item baru, "
        f"{tot_skipped} sudah ada, {tot_rejected} ditolak")

    return {
        'ok': True,
        'summary': {'accounts': len(accounts), 'products': len(data.fg_material_ids),
                    'created': tot_created, 'skipped': tot_skipped,
                    'rejected': tot_rejected},
        'results': results,
        'message': (f"{tot_created} item katalog dibuat di {len(accounts)} toko"
                    + (f", {tot_skipped} sudah ada" if tot_skipped else '')
                    + (f", {tot_rejected} ditolak" if tot_rejected else '')
                    + '. HPP & harga resmi diambil dari master produk.'),
    }


@router.post('/archive-legacy-items')
async def archive_legacy_items(request: Request):
    """Archive catalog items yang dibuat manual (tanpa fg_material_id link).
    
    Marks items as is_active=False dan tambah 'legacy_archived' tag untuk hidden filter.
    Admin only.
    """
    user = await require_auth(request)
    role = user.get('role', '')
    if role not in ['admin', 'owner', 'superadmin']:
        raise HTTPException(403, 'Hanya admin/owner yang bisa archive legacy data.')
    
    db = get_db()
    
    # Find items without fg_material_id (legacy manual entries)
    result = await db.marketing_catalog_items.update_many(
        {
            '$or': [
                {'fg_material_id': None},
                {'fg_material_id': {'$exists': False}},
            ],
            'source': {'$ne': 'from_fg'},
        },
        {
            '$set': {
                'is_active': False,
                'legacy_archived': True,
                'archived_at': _now(),
                'archived_by': user.get('id', ''),
            }
        }
    )
    
    # Refresh catalog stats for affected catalogs
    affected_catalogs = await db.marketing_catalog_items.distinct('catalog_id', {'legacy_archived': True})
    for cid in affected_catalogs:
        await _refresh_catalog_stats(db, cid)
    
    return {
        'ok': True,
        'archived_count': result.modified_count,
        'message': f'{result.modified_count} item legacy berhasil di-archive. Item baru harus pakai FG picker.',
    }


@router.get('/{catalog_id}')
async def get_catalog(catalog_id: str, request: Request):
    """Get catalog detail."""
    await require_auth(request)
    db = get_db()

    doc = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Katalog tidak ditemukan.')
    return {'ok': True, 'catalog': _s(doc)}


@router.put('/{catalog_id}')
async def update_catalog(catalog_id: str, data: CatalogUpdate, request: Request):
    """Update catalog info."""
    user = await require_auth(request)
    db = get_db()

    patch = {k: v for k, v in data.dict().items() if v is not None}
    if not patch:
        raise HTTPException(400, 'Tidak ada perubahan.')
    patch['updated_at'] = _now()
    patch['updated_by'] = user.get('id', '')

    res = await db.marketing_catalogs.update_one({'id': catalog_id}, {'$set': patch})
    if res.matched_count == 0:
        raise HTTPException(404, 'Katalog tidak ditemukan.')

    doc = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0})
    return {'ok': True, 'catalog': _s(doc)}


@router.delete('/{catalog_id}')
async def delete_catalog(catalog_id: str, request: Request):
    """Hapus catalog dan semua item-nya."""
    await require_auth(request)
    db = get_db()

    cat = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0, 'name': 1})
    if not cat:
        raise HTTPException(404, 'Katalog tidak ditemukan.')

    item_count = await db.marketing_catalog_items.count_documents({'catalog_id': catalog_id})
    await db.marketing_catalog_items.delete_many({'catalog_id': catalog_id})
    await db.marketing_catalogs.delete_one({'id': catalog_id})

    return {'ok': True, 'message': f"Katalog '{cat['name']}' dan {item_count} item dihapus."}
