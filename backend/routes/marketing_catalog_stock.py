"""
Marketing Catalog - Stock
Stock updates + WMS sync + history
"""
import uuid
import html
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from core import catalog_stock as _cstock  # F7: SSOT SATU rumus stok jual

router = APIRouter(prefix='/api/marketing/catalogs', tags=['Marketing-Catalog-stock'])

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

@router.put('/{catalog_id}/items/{item_id}/stock')
async def update_item_stock(catalog_id: str, item_id: str, body: StockUpdateBody, request: Request):
    """Update stok item secara manual."""
    user = await require_auth(request)
    db = get_db()

    item = await db.marketing_catalog_items.find_one(
        {'id': item_id, 'catalog_id': catalog_id}, {'_id': 0}
    )
    if not item:
        raise HTTPException(404, 'Item tidak ditemukan.')

    old_qty = float(item.get('stock_quantity', 0))
    new_qty = float(body.stock_quantity)
    threshold = float(item.get('stock_alert_threshold', 10))

    patch = {
        'stock_quantity': new_qty,
        'stock_status': _stock_status(new_qty, threshold),
        'updated_at': _now(),
        'updated_by': user.get('id', ''),
        'last_stock_sync': _now(),
    }
    await db.marketing_catalog_items.update_one({'id': item_id}, {'$set': patch})
    await _refresh_catalog_stats(db, catalog_id)

    # Log sync
    await db.marketing_stock_syncs.insert_one({
        'id': _uid(),
        'catalog_id': catalog_id,
        'item_id': item_id,
        'sku': item.get('sku', ''),
        'name': item.get('name', ''),
        'old_stock': old_qty,
        'new_stock': new_qty,
        'delta': new_qty - old_qty,
        'sync_type': 'manual',
        'notes': body.notes or '',
        'synced_at': _now(),
        'synced_by': user.get('id', ''),
    })

    return {
        'ok': True,
        'item_id': item_id,
        'old_stock': old_qty,
        'new_stock': new_qty,
        'delta': new_qty - old_qty,
        'stock_status': _stock_status(new_qty, threshold),
    }


@router.post('/{catalog_id}/bulk-stock-update')
async def bulk_stock_update(catalog_id: str, body: BulkStockUpdate, request: Request):
    """
    Bulk update stok banyak item sekaligus.
    Body: { "updates": [{ "item_id": "...", "stock_quantity": 50, "notes": "..." }] }
    """
    user = await require_auth(request)
    db = get_db()

    catalog = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0, 'id': 1})
    if not catalog:
        raise HTTPException(404, 'Katalog tidak ditemukan.')

    saved = 0
    skipped = 0
    sync_logs = []

    for upd in body.updates:
        item_id = upd.get('item_id')
        new_qty_raw = upd.get('stock_quantity')
        if not item_id or new_qty_raw is None:
            skipped += 1
            continue

        item = await db.marketing_catalog_items.find_one(
            {'id': item_id, 'catalog_id': catalog_id}, {'_id': 0}
        )
        if not item:
            skipped += 1
            continue

        old_qty = float(item.get('stock_quantity', 0))
        new_qty = float(new_qty_raw)
        threshold = float(item.get('stock_alert_threshold', 10))

        await db.marketing_catalog_items.update_one(
            {'id': item_id},
            {'$set': {
                'stock_quantity': new_qty,
                'stock_status': _stock_status(new_qty, threshold),
                'updated_at': _now(),
                'last_stock_sync': _now(),
            }}
        )
        sync_logs.append({
            'id': _uid(),
            'catalog_id': catalog_id,
            'item_id': item_id,
            'sku': item.get('sku', ''),
            'name': item.get('name', ''),
            'old_stock': old_qty,
            'new_stock': new_qty,
            'delta': new_qty - old_qty,
            'sync_type': 'bulk_manual',
            'notes': upd.get('notes', ''),
            'synced_at': _now(),
            'synced_by': user.get('id', ''),
        })
        saved += 1

    if sync_logs:
        await db.marketing_stock_syncs.insert_many(sync_logs)
    await _refresh_catalog_stats(db, catalog_id)

    return {'ok': True, 'saved': saved, 'skipped': skipped}


@router.post('/{catalog_id}/sync-from-wms')
async def sync_stock_from_wms(catalog_id: str, request: Request):
    """Sinkronkan stok SELURUH item katalog dari WMS — **SATU rumus** (F7).

    Yang diperbaiki 2026-08-10 (semua TERBUKTI sebelum diperbaiki):
      * **M1** dulu endpoint ini memakai rumus SENDIRI (`qty` mentah, semua lokasi)
        sehingga tiga pintu memberi tiga angka berbeda untuk item yang sama.
      * **M3** `reserved_quantity` diabaikan ⇒ stok katalog di-set LEBIH BESAR
        daripada yang tersedia ⇒ **OVERSELLING** (barang yang sudah dipesan orang
        lain ikut ditawarkan lagi).
      * **M4** membaca `s.get('qty', 0)` MENTAH, padahal `core/stock_schema`
        mewajibkan `read_qty()` (koleksi punya 3 skema historis).
      * **M5** filternya `material_id $exists` ⇒ item yang tertaut lewat
        `variant_sku` **dilewati diam-diam**; laporannya tetap "sukses".

    Sekarang: SEMUA item yang punya tautan apa pun (material_id / fg_material_id /
    variant_id / variant_sku) diproses lewat SSOT `core.catalog_stock`, dan item
    yang **tidak** tertaut dilaporkan eksplisit sebagai `not_linked` — bukan hilang.
    """
    user = await require_auth(request)
    db = get_db()

    catalog = await db.marketing_catalogs.find_one({'id': catalog_id}, {'_id': 0})
    if not catalog:
        raise HTTPException(404, 'Katalog tidak ditemukan.')

    items = await db.marketing_catalog_items.find(
        {'catalog_id': catalog_id}, {'_id': 0}).to_list(5000)

    blocked = await _cstock.blocked_location_ids(db)
    synced = not_found = not_linked = 0
    sync_logs, unlinked_items, no_master_items = [], [], []

    for item in items:
        res = await _cstock.item_sellable(db, item, blocked_locs=blocked)
        if res['link_type'] == 'none':
            not_linked += 1
            unlinked_items.append({'id': item.get('id'), 'sku': item.get('sku', ''),
                                   'name': item.get('name', '')})
            continue
        if not res['fg_material_id']:
            not_found += 1
            no_master_items.append({'id': item.get('id'), 'sku': item.get('sku', ''),
                                    'name': item.get('name', ''),
                                    'variant_sku': res.get('variant_sku', '')})
            continue

        old_qty = float(item.get('stock_quantity', 0) or 0)
        new_qty = float(res['available'])
        await db.marketing_catalog_items.update_one(
            {'id': item['id']},
            {'$set': _cstock.cache_patch(res, item.get('stock_alert_threshold', 10))})
        sync_logs.append({
            'id': _uid(), 'catalog_id': catalog_id, 'item_id': item['id'],
            'sku': item.get('sku', ''), 'name': item.get('name', ''),
            'old_stock': old_qty, 'new_stock': new_qty, 'delta': new_qty - old_qty,
            'sync_type': 'wms_sync',
            'notes': (f"Stok jual SSOT ({res['link_type']}): on-hand {res['onhand']:g} − "
                      f"reserved {res['reserved']:g}"
                      + (f", dikecualikan karantina/blokir {res['excluded_onhand']:g}"
                         if res['excluded_onhand'] else '')),
            'synced_at': _now(), 'synced_by': user.get('id', ''),
        })
        synced += 1

    if sync_logs:
        await db.marketing_stock_syncs.insert_many(sync_logs)
    await _refresh_catalog_stats(db, catalog_id)

    return {
        'ok': True,
        'synced': synced,
        'not_found_in_wms': not_found,
        'not_linked': not_linked,
        'total_items': len(items),
        'unlinked_items': unlinked_items,
        'no_master_items': no_master_items,
        'formula': 'on-hand − reserved, semua lokasi kecuali karantina/blokir (K-6a)',
        'message': (
            f'Sinkron stok selesai: {synced} item diperbarui, '
            f'{not_found} tertaut tapi master FG belum ada, '
            f'{not_linked} belum tertaut ke master.'
        ),
        'synced_at': _now().isoformat(),
    }


@router.get('/{catalog_id}/stock-history')
async def get_stock_history(
    catalog_id: str,
    request: Request,
    item_id: Optional[str] = None,
    limit: int = 50,
):
    """Riwayat perubahan stok untuk satu katalog (atau satu item)."""
    await require_auth(request)
    db = get_db()

    q: dict = {'catalog_id': catalog_id}
    if item_id:
        q['item_id'] = item_id

    logs = await db.marketing_stock_syncs.find(q, {'_id': 0}).sort('synced_at', -1).limit(limit).to_list(500)
    return {'ok': True, 'history': [_s(log) for log in logs]}


@router.get('/{catalog_id}/low-stock')
async def get_low_stock_items(catalog_id: str, request: Request):
    """Item dengan stok rendah atau habis di katalog ini."""
    await require_auth(request)
    db = get_db()

    items = await db.marketing_catalog_items.find(
        {
            'catalog_id': catalog_id,
            'is_active': True,
            'stock_status': {'$in': ['low_stock', 'out_of_stock']},
        },
        {'_id': 0}
    ).sort('stock_quantity', 1).to_list(500)

    return {
        'ok': True,
        'items': [_s(i) for i in items],
        'count': len(items),
        'out_of_stock': sum(1 for i in items if i.get('stock_status') == 'out_of_stock'),
        'low_stock': sum(1 for i in items if i.get('stock_status') == 'low_stock'),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# SEED DEMO DATA
# ═══════════════════════════════════════════════════════════════════════════════

@router.post('/seed-demo')
async def seed_demo_catalog(request: Request):
    """Seed demo catalogs + items untuk testing."""
    user = await require_auth(request)
    db = get_db()

    # Only seed if no catalogs exist yet
    existing = await db.marketing_catalogs.count_documents({})
    if existing > 0:
        return {'ok': True, 'message': f'{existing} katalog sudah ada, skip seed.'}

    # Get first active account
    account = await db.marketing_platform_accounts.find_one({'status': 'active'}, {'_id': 0})
    if not account:
        # Create a demo account first
        account = {
            'id': _uid(),
            'name': 'Toko Demo Shopee',
            'platform': 'Shopee',
            'status': 'active',
            'username': 'toko_demo_shopee',
            'created_at': _now(),
        }
        await db.marketing_platform_accounts.insert_one(account)

    catalog_id = _uid()
    cat_doc = {
        'id': catalog_id,
        'account_id': account['id'],
        'account_name': account.get('name', ''),
        'platform': account.get('platform', 'Shopee'),
        'name': 'Katalog Produk Utama',
        'description': 'Katalog utama produk fashion CV. Dewi Aditya',
        'is_active': True,
        'item_count': 0,
        'total_stock': 0.0,
        'low_stock_count': 0,
        'out_of_stock_count': 0,
        'created_at': _now(),
        'updated_at': _now(),
        'created_by': user.get('id', ''),
    }
    await db.marketing_catalogs.insert_one(cat_doc)

    # Demo items
    demo_items = [
        {'sku': 'SKU-001', 'name': 'Kaos Polos Premium Pria', 'category': 'Kaos', 'price': 85000, 'stock_quantity': 150, 'stock_alert_threshold': 20, 'variant_info': 'Warna: Hitam, Putih, Abu | Size: S, M, L, XL'},
        {'sku': 'SKU-002', 'name': 'Celana Chino Slim Fit', 'category': 'Celana', 'price': 175000, 'stock_quantity': 8, 'stock_alert_threshold': 15, 'variant_info': 'Warna: Khaki, Navy | Size: 28-34'},
        {'sku': 'SKU-003', 'name': 'Kemeja Oxford Formal', 'category': 'Kemeja', 'price': 225000, 'stock_quantity': 0, 'stock_alert_threshold': 10, 'variant_info': 'Warna: Putih, Biru Muda | Size: S–XXL'},
        {'sku': 'SKU-004', 'name': 'Jaket Bomber Pria', 'category': 'Jaket', 'price': 350000, 'stock_quantity': 45, 'stock_alert_threshold': 10, 'variant_info': 'Warna: Hitam, Olive | Size: M–XXL'},
        {'sku': 'SKU-005', 'name': 'Dress Casual Wanita', 'category': 'Dress', 'price': 195000, 'stock_quantity': 5, 'stock_alert_threshold': 10, 'variant_info': 'Warna: Floral, Polos | Size: S–XL'},
        {'sku': 'SKU-006', 'name': 'Rok Midi Motif Batik', 'category': 'Rok', 'price': 155000, 'stock_quantity': 32, 'stock_alert_threshold': 8},
        {'sku': 'SKU-007', 'name': 'Blouse Sifon Wanita', 'category': 'Blouse', 'price': 135000, 'stock_quantity': 0, 'stock_alert_threshold': 10, 'variant_info': 'Warna: Pink, Cream, Hitam | Size: S–XL'},
        {'sku': 'SKU-008', 'name': 'Jogger Pants Unisex', 'category': 'Celana', 'price': 145000, 'stock_quantity': 78, 'stock_alert_threshold': 15},
    ]

    for item_data in demo_items:
        qty = float(item_data.get('stock_quantity', 0))
        thresh = float(item_data.get('stock_alert_threshold', 10))
        doc = {
            'id': _uid(),
            'catalog_id': catalog_id,
            'account_id': account['id'],
            'platform': account.get('platform', 'Shopee'),
            'sku': item_data['sku'],
            'name': item_data['name'],
            'description': '',
            'price': float(item_data.get('price', 0)),
            'original_price': float(item_data.get('price', 0)) * 0.65,
            'platform_price': float(item_data.get('price', 0)),
            'stock_quantity': qty,
            'stock_alert_threshold': thresh,
            'stock_status': _stock_status(qty, thresh),
            'material_id': None,
            'platform_url': '',
            'images': [],
            'tags': [item_data.get('category', '')],
            'weight_gram': 250.0,
            'category': item_data.get('category', ''),
            'variant_info': item_data.get('variant_info', ''),
            'is_active': True,
            'last_stock_sync': None,
            'created_at': _now(),
            'updated_at': _now(),
            'created_by': user.get('id', ''),
        }
        await db.marketing_catalog_items.insert_one(doc)

    await _refresh_catalog_stats(db, catalog_id)

    return {
        'ok': True,
        'message': f'Seed berhasil: 1 katalog + {len(demo_items)} items.',
        'catalog_id': catalog_id,
    }
