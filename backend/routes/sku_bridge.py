"""routes/sku_bridge.py — **Jembatan SKU** Marketing ⇄ Gudang (Sesi #20).

Semua aturannya ada di :mod:`core.sku_bridge`. Berkas ini hanya pintu HTTP-nya,
supaya satu pemetaan identitas barang tidak pernah punya dua kamus.

Endpoint (prefix ``/api/sku-bridge``):
  GET    /health                 — KPI kesehatan tautan marketing↔gudang
  GET    /unmapped               — SKU platform yang belum dikenal master
  GET    /suggest                — usulan sasaran + keyakinan (tidak menebak)
  GET    /targets                — cari sasaran (item katalog / varian) manual
  GET    /mappings               — daftar pemetaan yang sudah ada
  POST   /map                    — petakan 1 SKU → master (+ backfill pesanan)
  POST   /auto-map               — pemetaan massal (pratinjau dulu; `apply=true` utk menulis)
  POST   /relink                 — terapkan ulang seluruh pemetaan ke pesanan
  DELETE /mappings/{psid}        — lepas pemetaan
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import log_activity, require_auth, serialize_doc
from core import sku_bridge as bridge
from database import get_db

router = APIRouter(prefix='/api/sku-bridge', tags=['sku-bridge'])


class MapIn(BaseModel):
    platform_sku_id: str = Field(..., description='SKU milik platform (angka, apa adanya)')
    catalog_item_id: Optional[str] = Field(None, description='Sasaran: item katalog jual')
    variant_id: Optional[str] = Field(None, description='Sasaran: varian model internal')
    fg_material_id: Optional[str] = Field(None, description='Sasaran: master FG langsung')
    account_id: Optional[str] = Field(None, description='Toko (wajib bila sasaran varian)')
    product_name: str = ''
    variation: str = ''
    confidence: Optional[float] = None


class AutoMapIn(BaseModel):
    min_confidence: float = Field(default=bridge.AUTO_MIN_CONFIDENCE, ge=0.5, le=1.0)
    limit: int = Field(default=100, ge=1, le=500)
    account_id: Optional[str] = None
    apply: bool = Field(default=False, description='False = pratinjau (tidak menulis apa pun)')


@router.get('/health')
async def bridge_health(account_id: Optional[str] = None, user: dict = Depends(require_auth)):
    """KPI kesehatan tautan — angka yang menjawab "apakah gudang bisa bekerja?"."""
    db = get_db()
    return await bridge.health(db, account_id=account_id)


@router.get('/unmapped')
async def unmapped(account_id: Optional[str] = None, q: Optional[str] = None,
                   limit: int = Query(default=300, ge=1, le=1000),
                   with_suggestion: bool = Query(default=False),
                   user: dict = Depends(require_auth)):
    """SKU platform yang dipesan pembeli tetapi belum dikenal master gudang.

    `with_suggestion=true` menyertakan usulan terbaik per SKU (1 kali hitung pool,
    jadi tetap murah untuk ratusan baris).
    """
    db = get_db()
    res = await bridge.list_unmapped(db, account_id=account_id, q=q, limit=limit)
    if with_suggestion and res['rows']:
        pool = await bridge._candidate_pool(db, account_id=None)
        models = await bridge._model_pool(db)
        for r in res['rows']:
            sg = await bridge.suggest(db, product_name=r['product_name'],
                                     variation=r['variation'],
                                     account_id=r.get('account_id'), limit=1,
                                     pool=pool, models=models)
            best = sg.get('best')
            mm = sg.get('model_match') or {}
            r['parsed'] = sg.get('parsed')
            r['recommended_action'] = sg.get('recommended_action')
            r['action_reason'] = sg.get('reason')
            r['model_match'] = mm or None
            r['suggestion'] = ({'target_id': best['target_id'], 'kind': best['kind'],
                                'label': best['label'], 'sku': best.get('sku') or '',
                                'confidence': best['confidence'], 'reasons': best['reasons'],
                                'auto_ok': (sg.get('recommended_action') == 'map'
                                            and bridge._f(mm.get('match_confidence'))
                                            >= bridge.AUTO_MIN_CONFIDENCE)}
                               if best else None)
    return res


@router.get('/suggest')
async def suggest_targets(platform_sku_id: Optional[str] = None,
                          product_name: str = '', variation: str = '',
                          account_id: Optional[str] = None,
                          limit: int = Query(default=8, ge=1, le=50),
                          user: dict = Depends(require_auth)):
    """Usulan sasaran untuk satu SKU. Daftar kosong = masternya belum ada."""
    db = get_db()
    if platform_sku_id and not (product_name or variation):
        o = await db[bridge.ORDERS].find_one(
            {'items.platform_sku_id': str(platform_sku_id).strip()},
            {'_id': 0, 'items': 1, 'account_id': 1})
        if o:
            account_id = account_id or o.get('account_id')
            for ln in (o.get('items') or []):
                if str(ln.get('platform_sku_id') or '') == str(platform_sku_id).strip():
                    product_name = ln.get('product_name_raw') or ln.get('product_name') or ''
                    variation = ln.get('variation_raw') or ''
                    break
    if not (product_name or variation):
        raise HTTPException(400, 'Butuh product_name/variation, atau platform_sku_id yang ada di pesanan.')
    res = await bridge.suggest(db, product_name=product_name, variation=variation,
                              account_id=account_id, limit=limit)
    res['product_name'] = product_name
    res['variation'] = variation
    return res


@router.get('/targets')
async def search_targets(q: str = '', account_id: Optional[str] = None,
                         limit: int = Query(default=40, ge=1, le=200),
                         user: dict = Depends(require_auth)):
    """Cari sasaran pemetaan secara manual (item katalog + varian model)."""
    db = get_db()
    return await bridge.search_targets(db, q=q, account_id=account_id, limit=limit)


class BulkResolveIn(BaseModel):
    actions: list = Field(default=['map', 'create_variant'],
                          description="Pilihan: 'map' (tautkan varian yang sudah ada), "
                                      "'create_variant' (buat varian di model yang cocok), "
                                      "'create_master' (buat model BARU)")
    limit: int = Field(default=200, ge=1, le=1000)
    account_id: Optional[str] = None
    apply: bool = Field(default=False, description='False = pratinjau, tidak menulis apa pun')


@router.post('/bulk-resolve')
async def bulk_resolve(body: BulkResolveIn, user: dict = Depends(require_auth)):
    """Selesaikan banyak SKU sekaligus mengikuti aksi yang disarankan mesin.

    Bawaan **pratinjau** dan hanya aksi yang aman (`map` + `create_variant`).
    `create_master` harus dipilih sadar karena ia menambah master produk baru.
    """
    db = get_db()
    res = await bridge.bulk_resolve(db, actions=tuple(body.actions or ()), limit=body.limit,
                                   account_id=body.account_id, user=user,
                                   dry_run=not body.apply)
    if body.apply:
        await log_activity(user.get('id', ''), user.get('name', ''),
                          f"Jembatan SKU massal: {res['applied_count']} SKU diselesaikan "
                          f"({res['created_models']} model + {res['created_variants']} varian baru, "
                          f"{res['orders_updated']} pesanan tertaut)", 'sku-bridge', '')
    return res


@router.get('/mappings')
async def list_mappings(q: Optional[str] = None,
                        limit: int = Query(default=300, ge=1, le=1000),
                        user: dict = Depends(require_auth)):
    db = get_db()
    res = await bridge.list_mappings(db, q=q, limit=limit)
    res['rows'] = [serialize_doc(r) for r in res['rows']]
    return res


@router.post('/map')
async def map_sku(body: MapIn, user: dict = Depends(require_auth)):
    """Petakan satu SKU platform ke master, lalu tautkan SEMUA pesanannya."""
    db = get_db()
    if not (body.catalog_item_id or body.variant_id or body.fg_material_id):
        raise HTTPException(400, 'Pilih sasaran: catalog_item_id, variant_id, atau fg_material_id.')
    res = await bridge.apply_mapping(
        db, body.platform_sku_id, catalog_item_id=body.catalog_item_id,
        variant_id=body.variant_id, fg_material_id=body.fg_material_id,
        account_id=body.account_id, user=user, method='manual',
        confidence=body.confidence, product_name=body.product_name,
        variation=body.variation)
    if not res.get('ok'):
        raise HTTPException(res.get('status', 400), res.get('message', 'Pemetaan gagal.'))
    await log_activity(user.get('id', ''), user.get('name', ''),
                       f"Jembatan SKU: {body.platform_sku_id} → {res['target'].get('name')} "
                       f"({res['orders_updated']} pesanan tertaut)",
                       'sku-bridge', body.platform_sku_id)
    res['bridge'] = serialize_doc(res.get('bridge') or {})
    return res


@router.post('/auto-map')
async def auto_map(body: AutoMapIn, user: dict = Depends(require_auth)):
    """Pemetaan massal untuk yang keyakinannya tinggi. Bawaan = PRATINJAU."""
    db = get_db()
    res = await bridge.auto_map(db, min_confidence=body.min_confidence, limit=body.limit,
                               account_id=body.account_id, user=user,
                               dry_run=not body.apply)
    if body.apply:
        await log_activity(user.get('id', ''), user.get('name', ''),
                          f"Jembatan SKU otomatis: {res['applied_count']} SKU dipetakan "
                          f"(ambang {res['min_confidence']})", 'sku-bridge', '')
    return res


@router.post('/relink')
async def relink(platform_sku_id: Optional[str] = None, user: dict = Depends(require_auth)):
    """Terapkan ulang pemetaan ke pesanan (pemulihan; idempoten)."""
    db = get_db()
    return await bridge.relink_orders(db, platform_sku_id=platform_sku_id)


class CreateMasterIn(BaseModel):
    platform_sku_id: str
    product_name: str = ''
    variation: str = ''
    account_id: Optional[str] = None
    model_id: Optional[str] = Field(None, description='Pakai model yang SUDAH ada (opsional)')
    model_name: Optional[str] = Field(None, description='Timpa nama model yang diusulkan')
    category_text: Optional[str] = None
    color_name: Optional[str] = None
    size_code: Optional[str] = None
    retail_price: float = 0
    hpp: float = 0
    apply: bool = Field(default=False, description='False = pratinjau rencana, tidak menulis')


@router.post('/create-master')
async def create_master(body: CreateMasterIn, user: dict = Depends(require_auth)):
    """Buat master dari SKU platform yang belum dikenal, lalu tautkan.

    Ini jalan keluar untuk barang yang memang **belum pernah ada** di master
    (mesin usulan jujur mengembalikan daftar kosong untuk kasus itu). Rantainya:
    model → varian (warna×ukuran) → master FG → item katalog toko → pemetaan SKU
    → seluruh pesanan lama ikut tertaut.

    Bawaan **pratinjau**: kirim `apply: true` untuk benar-benar membuat.
    """
    db = get_db()
    res = await bridge.create_master_and_map(
        db, body.platform_sku_id, product_name=body.product_name, variation=body.variation,
        account_id=body.account_id, model_id=body.model_id, model_name=body.model_name,
        category_text=body.category_text, color_name=body.color_name,
        size_code=body.size_code, retail_price=body.retail_price, hpp=body.hpp,
        user=user, dry_run=not body.apply)
    if not res.get('ok'):
        raise HTTPException(res.get('status', 400), res.get('message', 'Gagal membuat master.'))
    if body.apply:
        await log_activity(user.get('id', ''), user.get('name', ''),
                          f"Jembatan SKU: master dibuat dari {body.platform_sku_id} "
                          f"→ {res.get('variant', {}).get('sku', '')}",
                          'sku-bridge', body.platform_sku_id)
        res['bridge'] = serialize_doc(res.get('bridge') or {})
    return res


@router.delete('/mappings/{platform_sku_id}')
async def unmap(platform_sku_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await bridge.remove_mapping(db, platform_sku_id, user=user)
    if not res.get('ok'):
        raise HTTPException(res.get('status', 400), res.get('message', 'Gagal melepas pemetaan.'))
    await log_activity(user.get('id', ''), user.get('name', ''),
                       f'Jembatan SKU dilepas: {platform_sku_id}', 'sku-bridge', platform_sku_id)
    return res
