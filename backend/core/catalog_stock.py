"""core.catalog_stock — F7 · SSOT **SATU** rumus "stok yang boleh dijual".

Latar belakang (dibuktikan `scripts/_prove_catalog_master_gaps.py`, 10/10):
"stok katalog" punya **TIGA** rumus berbeda di tiga pintu masuk yang sama-sama
menulis `marketing_catalog_items.stock_quantity`:

| Pintu                            | Rumus lama       | Lokasi        | reserved? |
|----------------------------------|------------------|---------------|-----------|
| `POST /{cid}/items/from-fg`      | `qty` mentah     | **1** lokasi  | tidak     |
| `PUT  /{cid}/items/{id}/sync-fg-stock` | on-hand − reserved | semua   | ya        |
| `POST /{cid}/sync-from-wms`      | `qty` mentah     | semua         | tidak     |

Akibat nyata: item baru **selalu lahir stok 0** (M2) dan `sync-from-wms`
menaikkan stok katalog di atas yang benar-benar tersedia ⇒ **OVERSELLING** (M3).

KEPUTUSAN OWNER (2026-08-10):
  * **K-6a** — stok yang boleh dijual = **SEMUA lokasi KECUALI** yang bertanda
    `blocked` / `quarantine` (baik pada BARIS stok maupun pada MASTER lokasi).
  * **K-7a** — stok katalog **dihitung LIVE** saat katalog dibaca.
    `stock_quantity` hanya **cache tampilan** + penanda `in_sync`. Mustahil basi.

ATURAN MODUL INI:
  * Ia adalah **satu-satunya** tempat rumus stok jual ditulis. Ketiga pintu di
    atas WAJIB memanggilnya — kalau tidak, gate `INV-KATALOG` KT-1 merah.
  * Semua pembacaan jumlah fisik lewat `read_qty()` / `read_reserved()`
    (`core/stock_schema`), sebab koleksi `rahaza_material_stock` punya **3 skema
    historis** (`qty` / `total_qty` / `quantity`). Membaca `qty` mentah = KT-4 merah.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone

from core.stock_schema import read_qty, read_reserved

logger = logging.getLogger(__name__)

STOCK = 'rahaza_material_stock'
QUARANTINE_ROLE = 'karantina'


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


# ══════════════════════════════════════════════════════════════════════════════
# K-6a — lokasi yang TIDAK boleh dijual
# ══════════════════════════════════════════════════════════════════════════════
async def blocked_location_ids(db) -> set:
    """Kumpulan id lokasi yang stoknya TIDAK boleh dijual (K-6a).

    Sumber (digabung, bukan dipilih salah satu — supaya satu penamaan yang
    terlewat tidak membocorkan stok karantina ke katalog):
      * `rahaza_locations` dengan `blocked: True` / `quarantine: True`
      * `rahaza_locations` dengan `role == 'karantina'` atau kode ber-KARANTINA
      * `wh_zones` dengan `blocked: True` / `role == 'karantina'`
    """
    out: set = set()
    try:
        cur = db.rahaza_locations.find(
            {'$or': [
                {'blocked': True},
                {'quarantine': True},
                {'role': QUARANTINE_ROLE},
                {'code': {'$regex': 'KARANTINA', '$options': 'i'}},
            ]},
            {'_id': 0, 'id': 1},
        )
        async for d in cur:
            if d.get('id'):
                out.add(d['id'])
    except Exception as e:  # noqa: BLE001 — daftar blokir tidak boleh mematikan fitur
        logger.error('[katalog-stok] gagal membaca lokasi terblokir: %s', e)
    try:
        cur = db.wh_zones.find(
            {'$or': [{'blocked': True}, {'quarantine': True}, {'role': QUARANTINE_ROLE}]},
            {'_id': 0, 'id': 1},
        )
        async for d in cur:
            if d.get('id'):
                out.add(d['id'])
    except Exception as e:  # noqa: BLE001
        logger.debug('[katalog-stok] wh_zones tidak terbaca: %s', e)
    return out


def row_is_sellable(row: dict, blocked_locs: set) -> bool:
    """Baris stok boleh dijual? (K-6a)"""
    if not row:
        return False
    if row.get('blocked') is True or row.get('quarantine') is True:
        return False
    loc = row.get('location_id') or ((row.get('location') or {}).get('id')
                                    if isinstance(row.get('location'), dict) else None)
    if loc and loc in blocked_locs:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# Rumus stok jual
# ══════════════════════════════════════════════════════════════════════════════
EMPTY = {
    'found': False, 'onhand': 0.0, 'reserved': 0.0, 'available': 0.0,
    'excluded_onhand': 0.0, 'rows': 0, 'rows_excluded': 0,
}


def _compute(rows: list, blocked_locs: set) -> dict:
    onhand = reserved = excluded = 0.0
    n_ok = n_bad = 0
    for s in rows:
        if row_is_sellable(s, blocked_locs):
            onhand += read_qty(s)
            reserved += read_reserved(s)
            n_ok += 1
        else:
            excluded += read_qty(s)
            n_bad += 1
    return {
        'found': bool(rows),
        'onhand': round(onhand, 2),
        'reserved': round(reserved, 2),
        'available': round(max(0.0, onhand - reserved), 2),
        'excluded_onhand': round(excluded, 2),
        'rows': n_ok, 'rows_excluded': n_bad,
    }


async def sellable_map(db, material_ids: list, *, blocked_locs: set = None) -> dict:
    """Stok jual untuk BANYAK material sekaligus (1 query — dipakai `GET items`)."""
    ids = [m for m in dict.fromkeys(material_ids or []) if m]
    if not ids:
        return {}
    if blocked_locs is None:
        blocked_locs = await blocked_location_ids(db)
    buckets: dict = {mid: [] for mid in ids}
    cur = db[STOCK].find({'material_id': {'$in': ids}}, {'_id': 0})
    async for s in cur:
        buckets.setdefault(s.get('material_id'), []).append(s)
    return {mid: _compute(rows, blocked_locs) for mid, rows in buckets.items()}


async def sellable_stock(db, material_id: str, *, blocked_locs: set = None) -> dict:
    """Stok jual SATU material FG (SSOT — dipakai semua pintu)."""
    if not material_id:
        return dict(EMPTY)
    if blocked_locs is None:
        blocked_locs = await blocked_location_ids(db)
    rows = await db[STOCK].find({'material_id': material_id}, {'_id': 0}).to_list(2000)
    return _compute(rows, blocked_locs)


# ══════════════════════════════════════════════════════════════════════════════
# Resolusi tautan item katalog → FG
# ══════════════════════════════════════════════════════════════════════════════
async def find_fg_by_sku(db, sku: str) -> dict:
    sku = (sku or '').strip()
    if not sku:
        return {}
    pat = f'^{re.escape(sku)}$'
    return await db.rahaza_materials.find_one(
        {'type': 'fg', '$or': [{'code': {'$regex': pat, '$options': 'i'}},
                               {'sku': {'$regex': pat, '$options': 'i'}}]},
        {'_id': 0},
    ) or {}


async def resolve_link(db, item: dict) -> dict:
    """Tautan item katalog → FG. Prioritas: variant_sku → variant_id → fg/material_id.

    Return: {link_type, fg_material_id, fg_code, fg, variant_sku, variant_id, model_id}
    `link_type` = 'variant_sku' | 'variant_id' | 'fg_material' | 'none'
    """
    out = {'link_type': 'none', 'fg_material_id': None, 'fg_code': '', 'fg': {},
           'variant_sku': (item.get('variant_sku') or '').strip(),
           'variant_id': item.get('variant_id'), 'model_id': item.get('model_id')}

    vsku = out['variant_sku']
    if not vsku and out['variant_id']:
        v = await db.rahaza_model_variants.find_one(
            {'id': out['variant_id']}, {'_id': 0, 'sku': 1, 'model_id': 1})
        if v:
            vsku = (v.get('sku') or '').strip()
            out['variant_sku'] = vsku
            out['model_id'] = out['model_id'] or v.get('model_id')
    if vsku:
        fg = await find_fg_by_sku(db, vsku)
        if fg:
            out.update({'link_type': 'variant_sku', 'fg': fg, 'fg_material_id': fg.get('id'),
                        'fg_code': fg.get('code') or fg.get('sku') or '',
                        'model_id': out['model_id'] or fg.get('model_id')})
            return out
        out['link_type'] = 'variant_sku'  # tertaut, tetapi master FG belum ada
        return out

    mid = item.get('fg_material_id') or item.get('material_id')
    if mid:
        fg = await db.rahaza_materials.find_one({'id': mid}, {'_id': 0}) or {}
        out.update({'link_type': 'fg_material', 'fg': fg, 'fg_material_id': mid,
                    'fg_code': fg.get('code') or fg.get('sku') or '',
                    'model_id': out['model_id'] or fg.get('model_id'),
                    'variant_sku': out['variant_sku'] or (fg.get('sku') or '')})
        return out
    return out


async def resolve_links_bulk(db, items: list) -> dict:
    """:func:`resolve_link` untuk BANYAK item — jumlah query KONSTAN, bukan N+1.

    Kenapa perlu: `GET /{cid}/items` memanggil :func:`resolve_link` di dalam loop,
    jadi katalog 300 item = ~600 query. Selama daftar hanya memuat satu halaman
    (100 baris) itu tidak terasa, tetapi F11 harus menghitung "item bermasalah"
    untuk **seluruh** katalog (kalau tidak, banner kesehatan data hanya jujur
    untuk halaman yang sedang tampil — persis jenis kebohongan yang membuat
    orang berhenti mempercayai peringatan).

    Return ``{item_id: link_dict}`` dengan bentuk yang sama seperti
    :func:`resolve_link` supaya pemanggil tidak perlu tahu bedanya.
    """
    items = [i for i in (items or []) if i and i.get('id')]
    if not items:
        return {}

    # 1) variant_id → sku (hanya untuk item yang `variant_sku`-nya kosong)
    need_v = [i for i in items
              if not (i.get('variant_sku') or '').strip() and i.get('variant_id')]
    vmap: dict = {}
    if need_v:
        vids = list({i['variant_id'] for i in need_v})
        cur = db.rahaza_model_variants.find({'id': {'$in': vids}},
                                            {'_id': 0, 'id': 1, 'sku': 1, 'model_id': 1})
        async for v in cur:
            vmap[v['id']] = v

    eff: dict = {}
    for i in items:
        vsku = (i.get('variant_sku') or '').strip()
        model_id = i.get('model_id')
        if not vsku and i.get('variant_id'):
            v = vmap.get(i['variant_id']) or {}
            vsku = (v.get('sku') or '').strip()
            model_id = model_id or v.get('model_id')
        eff[i['id']] = {'vsku': vsku, 'model_id': model_id}

    # 2) FG berdasarkan kode/sku — satu query untuk semua SKU sekaligus
    skus = {e['vsku'] for e in eff.values() if e['vsku']}
    fg_by_key: dict = {}
    if skus:
        cur = db.rahaza_materials.find(
            {'type': 'fg', '$or': [{'code': {'$in': list(skus)}},
                                   {'sku': {'$in': list(skus)}}]}, {'_id': 0})
        async for fg in cur:
            for key in (fg.get('code'), fg.get('sku')):
                if key:
                    fg_by_key[str(key).upper()] = fg

    # 3) FG berdasarkan id (item yang tertaut lewat fg_material_id/material_id)
    mids = {i.get('fg_material_id') or i.get('material_id') for i in items}
    mids = {m for m in mids if m}
    fg_by_id: dict = {}
    if mids:
        cur = db.rahaza_materials.find({'id': {'$in': list(mids)}}, {'_id': 0})
        async for fg in cur:
            fg_by_id[fg['id']] = fg

    out: dict = {}
    for i in items:
        e = eff[i['id']]
        link = {'link_type': 'none', 'fg_material_id': None, 'fg_code': '', 'fg': {},
                'variant_sku': e['vsku'], 'variant_id': i.get('variant_id'),
                'model_id': e['model_id']}
        if e['vsku']:
            fg = fg_by_key.get(e['vsku'].upper())
            if fg is None:
                # cadangan: pencocokan tak-peka-huruf satu per satu (jarang terpakai,
                # tetapi menjaga hasil IDENTIK dengan resolve_link)
                fg = await find_fg_by_sku(db, e['vsku']) or None
            if fg:
                link.update({'link_type': 'variant_sku', 'fg': fg,
                             'fg_material_id': fg.get('id'),
                             'fg_code': fg.get('code') or fg.get('sku') or '',
                             'model_id': link['model_id'] or fg.get('model_id')})
            else:
                link['link_type'] = 'variant_sku'   # tertaut, tetapi master FG belum ada
            out[i['id']] = link
            continue
        mid = i.get('fg_material_id') or i.get('material_id')
        if mid:
            fg = fg_by_id.get(mid) or {}
            link.update({'link_type': 'fg_material', 'fg': fg, 'fg_material_id': mid,
                         'fg_code': fg.get('code') or fg.get('sku') or '',
                         'model_id': link['model_id'] or fg.get('model_id'),
                         'variant_sku': link['variant_sku'] or (fg.get('sku') or '')})
        out[i['id']] = link
    return out


async def item_sellable(db, item: dict, *, blocked_locs: set = None) -> dict:
    """Stok jual LIVE untuk sebuah item katalog + info tautannya (K-7a)."""
    link = await resolve_link(db, item)
    res = dict(EMPTY)
    if link['fg_material_id']:
        res = await sellable_stock(db, link['fg_material_id'], blocked_locs=blocked_locs)
    cache = _f(item.get('stock_quantity'))
    return {
        **res,
        'link_type': link['link_type'],
        'fg_material_id': link['fg_material_id'],
        'fg_code': link['fg_code'],
        'variant_sku': link['variant_sku'],
        'model_id': link['model_id'],
        'cached_stock_quantity': cache,
        'in_sync': bool(link['fg_material_id']) and abs(cache - res['available']) < 0.001,
    }


def stock_status(qty: float, threshold: float) -> str:
    if qty <= 0:
        return 'out_of_stock'
    if qty <= threshold:
        return 'low_stock'
    return 'in_stock'


def cache_patch(res: dict, threshold: float) -> dict:
    """Fragment `$set` untuk menyegarkan CACHE stok item katalog (K-7a)."""
    avail = float(res.get('available') or 0)
    return {
        'stock_quantity': avail,
        'stock_status': stock_status(avail, float(threshold or 10)),
        'fg_onhand': res.get('onhand', 0.0),
        'fg_reserved': res.get('reserved', 0.0),
        'fg_available': avail,
        'fg_excluded_onhand': res.get('excluded_onhand', 0.0),
        'fg_material_id': res.get('fg_material_id'),
        'stock_source': res.get('link_type') or 'none',
        'stock_in_sync': True,
        'last_stock_sync': _now(),
        'updated_at': _now(),
    }


async def sync_item_cache(db, item: dict, *, blocked_locs: set = None) -> dict:
    """Hitung LIVE lalu simpan ke cache item katalog. Return hasil hitungnya."""
    res = await item_sellable(db, item, blocked_locs=blocked_locs)
    if not res['fg_material_id']:
        return res
    await db.marketing_catalog_items.update_one(
        {'id': item['id']},
        {'$set': cache_patch(res, item.get('stock_alert_threshold', 10))})
    res['in_sync'] = True
    return res


# ══════════════════════════════════════════════════════════════════════════════
# Reservasi HANYA dari baris yang boleh dijual (K-6a) — dipakai F9
# ══════════════════════════════════════════════════════════════════════════════
async def reserve_sellable(db, material_id: str, qty: float, *, ref=None, actor=None) -> dict:
    """Reservasi `qty` dari baris stok yang BOLEH DIJUAL saja (greedy available desc).

    Beda dengan `stock_service.reserve_material()` yang memakai SEMUA baris:
    di sini baris karantina/blokir tidak pernah ikut, sesuai K-6a. Rollback bila
    gagal di tengah supaya tidak ada reservasi menggantung.
    """
    from core import stock_service

    qty = round(float(qty or 0), 4)
    if qty <= 0:
        raise ValueError('qty harus > 0')
    blocked = await blocked_location_ids(db)
    rows = await db[STOCK].find({'material_id': material_id}, {'_id': 0}).to_list(2000)
    rows = [r for r in rows if row_is_sellable(r, blocked)]
    rows.sort(key=lambda r: read_qty(r) - read_reserved(r), reverse=True)
    total = round(sum(read_qty(r) - read_reserved(r) for r in rows), 4)
    if total < qty:
        raise stock_service.InsufficientStock(material_id, None, qty, max(0.0, total))

    remaining, done = qty, []
    try:
        for r in rows:
            if remaining <= 0:
                break
            avail = round(read_qty(r) - read_reserved(r), 4)
            if avail <= 0:
                continue
            take = round(min(avail, remaining), 4)
            await stock_service.reserve_row(r['id'], take, ref=ref, actor=actor, db=db)
            done.append({'stock_id': r['id'], 'qty_reserved': take,
                         'location_id': r.get('location_id')})
            remaining = round(remaining - take, 4)
        if remaining > 0:
            raise stock_service.InsufficientStock(material_id, None, qty, qty - remaining)
    except Exception:
        for d in done:
            try:
                await stock_service._release_row(d['stock_id'], d['qty_reserved'], db=db)
            except Exception as e:  # noqa: BLE001
                logger.error('[katalog-stok] ROLLBACK reservasi GAGAL baris=%s qty=%s: %s',
                             d['stock_id'], d['qty_reserved'], e)
        raise
    return {'material_id': material_id, 'reserved': qty, 'rows': done}


async def release_rows(db, rows: list) -> float:
    """Lepas reservasi pada baris-baris yang tercatat (idempoten, floor 0)."""
    from core import stock_service

    freed = 0.0
    for d in rows or []:
        sid = (d or {}).get('stock_id')
        q = round(float((d or {}).get('qty_reserved') or 0), 4)
        if not sid or q <= 0:
            continue
        try:
            await stock_service._release_row(sid, q, db=db)
            freed = round(freed + q, 4)
        except Exception as e:  # noqa: BLE001
            logger.error('[katalog-stok] gagal melepas reservasi baris=%s qty=%s: %s', sid, q, e)
    return freed
