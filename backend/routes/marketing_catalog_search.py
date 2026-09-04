"""routes.marketing_catalog_search — F9b · PENCARIAN ITEM KATALOG LINTAS-KATALOG.

MENGAPA BERKAS INI ADA
----------------------
Sejak **K-8a** (F9) order WAJIB membawa tautan ke master
(`catalog_item_id`/`variant_id`, atau `sku_id` yang benar-benar dikenal). Server
menolak SKU asal-ketik dengan **400**. Tetapi layar "Buat Order" masih meminta
staf **mengetik SKU dengan tangan** — jadi alur pembuatan order manual praktis
MENTOK: apa pun yang diketik hampir selalu ditolak, dan staf tidak punya cara
melihat SKU yang sah.

Semua endpoint item katalog yang sudah ada terikat pada satu katalog
(`/api/marketing/catalogs/{catalog_id}/items`), sehingga pemilih produk di layar
order tidak punya sumber data: staf tidak tahu item itu ada di katalog mana.

Endpoint ini menutup lubang itu: **satu** pencarian untuk SEMUA katalog, dengan
angka **stok jual LIVE** (K-6a/K-7a — bukan angka simpanan) plus alasan eksplisit
kalau sebuah item tidak boleh dijual. Keputusan pemilik (2026-08-10): item yang
tidak bisa dijual **tetap ditampilkan** tetapi dinonaktifkan + diberi alasan,
supaya staf paham *kenapa* dan bisa memperbaikinya — bukan menghilang tanpa jejak.

Catatan: endpoint ini HANYA MEMBACA. Tidak ada tulisan ke stok/uang.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Request
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri (middleware
# hanya menolak permintaan yang MENYEBUT toko, ia tidak tahu isi jawaban).
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth
from core import catalog_stock as _cstock
from core import catalog_margin as _cmargin  # sesi #37: SSOT margin

router = APIRouter(prefix='/api/marketing/catalog-items', tags=['Marketing-Catalog-search'])

# Batas aman: pencarian pemilih produk tidak perlu memindai seluruh koleksi.
CANDIDATE_CAP = 300


def _s(doc: dict) -> dict:
    out = {k: v for k, v in (doc or {}).items() if k != '_id'}
    for k, v in out.items():
        if isinstance(v, datetime):
            out[k] = v.isoformat()
    return out


def _f(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _block_reason(row: dict) -> Optional[str]:
    """Alasan sebuah item TIDAK boleh dijual — bahasa staf, bukan bahasa mesin.

    Urutan sengaja: status produk dulu (paling menentukan), lalu tautan master,
    baru angka stok. Menyebut penyebab paling hulu lebih dulu membuat staf
    memperbaiki akar masalahnya, bukan gejalanya.
    """
    if row.get('is_active') is False:
        return ('Produk sudah DIHENTIKAN (item katalog non-aktif) — tidak bisa dijual. '
                'Aktifkan kembali produknya di Master Produk bila memang masih dijual.')
    if not row.get('fg_material_id'):
        return ('Belum tertaut ke Master Produk / Barang Jadi — stoknya tidak bisa dihitung, '
                'jadi tidak boleh dijual. Tautkan varian/FG-nya dulu di Katalog.')
    if _f(row.get('available')) <= 0:
        return (f"Stok jual habis (0). On-hand {_f(row.get('fg_onhand')):g} sudah dikurangi "
                f"pesanan lain {_f(row.get('fg_reserved')):g}.")
    return None


@router.get('/search')
async def search_catalog_items(
    request: Request,
    q: Optional[str] = None,
    catalog_id: Optional[str] = None,
    account_id: Optional[str] = None,
    platform: Optional[str] = None,
    category_id: Optional[str] = None,
    only_sellable: bool = False,
    limit: int = 25,
):
    """Cari item katalog di SEMUA katalog + stok jual LIVE + alasan tak bisa dijual.

    Dipakai oleh pemilih produk di layar **Buat Order** (F9b) supaya staf tidak
    perlu mengetik SKU (yang sejak K-8a hampir selalu ditolak 400).

    Setiap baris menyertakan:
      · `available` — stok jual **LIVE** (Σ on-hand − Σ reserved, KECUALI lokasi
        karantina/blokir sesuai K-6a). `null` bila item belum tertaut master.
      · `sellable` + `block_reason` — boleh dijual atau tidak, dan kenapa.
      · `harga_jual` (nilai awal harga di order) & `retail_price_master` (harga resmi).
    """
    user = await require_auth(request)
    db = get_db()

    limit = max(1, min(int(limit or 25), 100))

    # F6 (sesi #10) — item katalog menempel pada toko; pemilih produk pun ikut
    # lingkup: staf toko A tidak boleh menjual dari katalog toko B.
    flt: dict = await _scope.scope_filter(db, user, {})
    if catalog_id:
        flt['catalog_id'] = catalog_id
    if account_id:
        flt['account_id'] = account_id
    if platform:
        flt['platform'] = {'$regex': f'^{re.escape(platform)}$', '$options': 'i'}
    if category_id:
        flt['category_id'] = category_id
    term = (q or '').strip()
    if term:
        pat = re.escape(term)
        flt['$or'] = [
            {'name': {'$regex': pat, '$options': 'i'}},
            {'sku': {'$regex': pat, '$options': 'i'}},
            {'variant_sku': {'$regex': pat, '$options': 'i'}},
            {'variant_info': {'$regex': pat, '$options': 'i'}},
            {'tags': {'$regex': pat, '$options': 'i'}},
        ]

    total_match = await db.marketing_catalog_items.count_documents(flt)
    docs: List[dict] = await db.marketing_catalog_items.find(flt, {'_id': 0}) \
        .sort('name', 1).limit(CANDIDATE_CAP).to_list(CANDIDATE_CAP)

    # ── nama katalog & akun (1 query, bukan N) ────────────────────────────────
    cat_ids = {d.get('catalog_id') for d in docs if d.get('catalog_id')}
    cmap = {}
    if cat_ids:
        async for c in db.marketing_catalogs.find({'id': {'$in': list(cat_ids)}}, {'_id': 0}):
            cmap[c['id']] = c
    # Katalog lama kadang tidak menyimpan `account_name` (di-denormalisasi belakangan).
    # Ambil dari master akun supaya staf tahu produk ini dijual di toko yang mana —
    # tanpa itu, SKU yang sama di 2 akun tidak bisa dibedakan di pemilih produk.
    acc_ids = {c.get('account_id') for c in cmap.values()
               if c.get('account_id') and not (c.get('account_name') or '').strip()}
    if acc_ids:
        amap = {}
        async for a in db.marketing_platform_accounts.find(
                {'id': {'$in': list(acc_ids)}}, {'_id': 0, 'id': 1, 'account_name': 1, 'name': 1}):
            amap[a['id']] = a.get('account_name') or a.get('name') or ''
        for c in cmap.values():
            if not (c.get('account_name') or '').strip():
                c['account_name'] = amap.get(c.get('account_id'), '')

    # ── stok jual LIVE untuk semua baris sekaligus (SSOT core.catalog_stock) ──
    blocked = await _cstock.blocked_location_ids(db)
    links = {}
    for d in docs:
        links[d['id']] = await _cstock.resolve_link(db, d)
    mids = [v['fg_material_id'] for v in links.values() if v.get('fg_material_id')]
    smap = await _cstock.sellable_map(db, mids, blocked_locs=blocked)
    fgcost = await _cmargin.fg_cost_map(db, mids)

    rows: List[dict] = []
    for d in docs:
        row = _s(d)
        lk = links[d['id']]
        linked = bool(lk.get('fg_material_id'))
        res = smap.get(lk.get('fg_material_id')) or dict(_cstock.EMPTY)
        cache = _f(row.get('stock_quantity'))
        cinfo = cmap.get(row.get('catalog_id')) or {}

        hj = _f(row.get('harga_jual')) or _f(row.get('price'))
        hpp = _f(row.get('hpp'))
        official = _f(row.get('retail_price_master'))

        out = {
            'id': row.get('id'),
            'catalog_item_id': row.get('id'),      # nama eksplisit untuk payload order
            'catalog_id': row.get('catalog_id'),
            'catalog_name': cinfo.get('name') or '',
            'account_id': row.get('account_id') or cinfo.get('account_id') or '',
            'account_name': cinfo.get('account_name') or '',
            'platform': row.get('platform') or cinfo.get('platform') or '',
            'sku': row.get('sku') or '',
            'name': row.get('name') or '',
            'variant_info': row.get('variant_info') or '',
            'category_id': row.get('category_id') or None,
            'category_code': row.get('category_code') or '',
            'category_name': row.get('category_name') or row.get('category') or '',
            'images': row.get('images') or [],
            # harga & margin (K-3a)
            'harga_jual': hj,
            'harga_coret': _f(row.get('harga_coret')) or _f(row.get('original_price')),
            'hpp': hpp,
            'hpp_source': row.get('hpp_source') or 'none',
            'retail_price_master': official,
            'margin': round(hj - hpp, 2),
            'margin_pct': None,   # diisi core.catalog_margin di bawah
            'price_delta_vs_master': round(hj - official, 2) if official else 0.0,
            # stok LIVE (K-6a/K-7a)
            'available': res['available'] if linked else None,
            'fg_onhand': res['onhand'],
            'fg_reserved': res['reserved'],
            'fg_excluded_onhand': res['excluded_onhand'],
            'cached_stock_quantity': cache,
            'in_sync': (abs(cache - res['available']) < 0.001) if linked else False,
            'stock_alert_threshold': _f(row.get('stock_alert_threshold')) or 10.0,
            'stock_live_status': (
                _cstock.stock_status(res['available'],
                                    _f(row.get('stock_alert_threshold')) or 10.0)
                if linked else 'unlinked'),
            # tautan master
            'is_active': row.get('is_active') is not False,
            'link_type': lk.get('link_type') or 'none',
            'variant_id': row.get('variant_id') or lk.get('variant_id'),
            'variant_sku': lk.get('variant_sku') or row.get('variant_sku') or '',
            'fg_material_id': lk.get('fg_material_id'),
            'fg_code': lk.get('fg_code') or '',
            'model_id': row.get('model_id') or lk.get('model_id'),
        }
        # Sesi #37 — margin memakai SATU rumus (`core.catalog_margin`): HPP
        # efektif dari lapisan FIFO FG → HPP FG → HPP katalog, dan bila tidak
        # diketahui hasilnya "belum bisa diukur", bukan 100%/0%.
        _cmargin.decorate(out, fgcost.get(lk.get('fg_material_id')))
        out['block_reason'] = _block_reason(out)
        out['sellable'] = out['block_reason'] is None
        out['max_qty'] = int(res['available']) if (linked and res['available'] > 0) else 0
        rows.append(out)

    if only_sellable:
        rows = [r for r in rows if r['sellable']]

    # Bisa-dijual dulu, lalu nama — staf melihat yang bisa dipakai di baris atas,
    # tetapi yang bermasalah tetap terlihat (keputusan pemilik: jangan disembunyikan).
    rows.sort(key=lambda r: (0 if r['sellable'] else 1, (r.get('name') or '').lower()))
    shown = rows[:limit]

    return {
        'ok': True,
        'items': shown,
        'total': total_match,
        'returned': len(shown),
        'counts': {
            'sellable': sum(1 for r in rows if r['sellable']),
            'blocked': sum(1 for r in rows if not r['sellable']),
            'scanned': len(rows),
        },
        'live_source': 'core.catalog_stock (K-6a/K-7a)',
    }
