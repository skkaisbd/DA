"""dewi_rnd — Material Research + Sample Costing."""
import re
from fastapi import Depends, HTTPException, Query
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import (
    router, now_utc, sid, serialize,
    line_code, line_name, resolve_master_material, resolve_rnd_material,
)
from core import bom_uom  # 2026-08-02: satuan & konversi material di RnD


def _num(v, d=0.0):
    try:
        if v in (None, ''):
            return float(d)
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _normalize_price_fields(body: dict) -> dict:
    """Satukan penulisan harga & satuan Riset Material (laporan owner 2026-08-02).

    Dulu koleksi ini HANYA punya `price_per_meter`, sehingga material yang dibeli
    per kg/pcs/lusin tetap dianggap per meter oleh kalkulator HPP & sample costing.
    Sekarang: `price_unit` (satuan harga, default 'm') + `price_per_unit`, dengan
    `price_per_meter` tetap ditulis sebagai cermin agar data & UI lama tidak pecah.
    """
    unit = bom_uom.norm_unit(body.get('price_unit') or body.get('unit') or 'm') or 'm'
    price = _num(body.get('price_per_unit'), _num(body.get('price_per_meter'), 0))
    body['price_unit'] = unit
    body['price_per_unit'] = price
    # cermin kompatibilitas: hanya sah bila satuan harganya memang meter
    body['price_per_meter'] = price if unit in ('m', 'meter', 'mtr') else _num(body.get('price_per_meter'), 0)
    if body.get('unit') in (None, ''):
        body['unit'] = unit
    return body


async def _enrich_costing_line(db, line: dict) -> dict:
    """Hitung ulang biaya SATU baris BOM sample dengan konversi satuan.

    Dulu `total_cost` sepenuhnya dikirim frontend (qty × harga, tanpa peduli
    satuan) lalu dijumlahkan mentah oleh server. Sekarang server yang menghitung:
    qty baris dikonversi ke satuan harga material (kemasan material → tabel
    dimensi global → gramasi×lebar kain), sehingga "500 gram" tidak lagi dihitung
    sebagai 500 kg. Bila satuan tidak bisa dikonversi, biaya TETAP dihitung 1:1
    tapi baris ditandai `uom_status='mismatch'` + catatan agar terlihat di UI.

    Urutan harga (keputusan owner): harga yang DIKETIK user menang → Riset
    Material → `unit_cost` master material.
    """
    out = dict(line)
    qty = _num(line.get('qty') or line.get('quantity'), 0)
    unit = bom_uom.norm_unit(line.get('unit') or '')

    rnd = await resolve_rnd_material(db, line)
    master = await resolve_master_material(db, line)
    if master is None and (rnd or {}).get('linked_material_id'):
        master = await db.rahaza_materials.find_one({'id': rnd['linked_material_id']}, {'_id': 0})

    price = _num(line.get('price_per_unit') or line.get('unit_cost')
                 or line.get('unit_price') or line.get('price'), 0)
    price_unit = bom_uom.norm_unit(line.get('price_unit') or '')
    source = 'line' if price > 0 else None
    if price <= 0 and rnd:
        price = _num(rnd.get('price_per_unit'), _num(rnd.get('price_per_meter'), 0))
        price_unit = bom_uom.norm_unit(rnd.get('price_unit') or rnd.get('unit') or 'm')
        source = 'rnd_material' if price > 0 else None
    if price <= 0 and master:
        price = _num(master.get('unit_cost'), 0)
        price_unit = bom_uom.norm_unit(master.get('base_uom') or master.get('unit') or 'pcs')
        source = 'master_material' if price > 0 else None

    price_unit = price_unit or unit or 'pcs'
    qty_priced, status, note = qty, 'base', ''
    if unit and price_unit and unit != price_unit:
        gf = bom_uom.global_factor(unit, price_unit)
        if gf:
            qty_priced, status = qty * gf, 'global'
            note = f"1 {unit} = {gf:g} {price_unit}"
        elif master is not None:
            f_line, base, st, nt = bom_uom.line_factor(master, unit)
            f_price, _b2, st2, _n2 = bom_uom.line_factor(master, price_unit)
            if st in ('base', 'uom', 'global', 'fabric') and st2 in ('base', 'uom', 'global', 'fabric') and f_price:
                qty_priced = (qty * f_line) / f_price
                status = 'fabric' if 'fabric' in (st, st2) else 'uom'
                note = f"via satuan dasar {base}"
            else:
                status, note = 'mismatch', (nt or f"satuan '{unit}' tidak bisa dikonversi ke '{price_unit}'")
        else:
            status, note = 'mismatch', (f"satuan '{unit}' vs harga per '{price_unit}' tidak bisa "
                                        f"dikonversi (material belum tertaut master)")

    total = round(_num(qty_priced) * price, 2)
    out.update({
        'qty': qty, 'unit': unit or price_unit,
        'price_per_unit': round(price, 2), 'price_unit': price_unit,
        'unit_cost': round(price, 2),           # cermin untuk UI/data lama
        'qty_priced': round(_num(qty_priced), 6),
        'uom_status': status, 'uom_note': note,
        'price_source': source or 'unresolved',
        'total_cost': total,
    })
    if master:
        out['material_id'] = master.get('id')
        out['material_code'] = master.get('code') or out.get('material_code') or ''
        out['unit_base'] = bom_uom.norm_unit(master.get('base_uom') or master.get('unit') or 'pcs')
    else:
        out['material_id'] = out.get('material_id') or ''
    return out


async def _recompute_costing_lines(db, lines: list) -> tuple:
    enriched = [await _enrich_costing_line(db, ln) for ln in (lines or [])]
    total = round(sum(_num(x.get('total_cost')) for x in enriched), 2)
    notes = [f"{line_name(x) or x.get('material_code') or '(baris)'}: {x['uom_note']}"
             for x in enriched if x.get('uom_status') in ('mismatch', 'unlinked') and x.get('uom_note')]
    return enriched, total, notes


async def _recompute_costing_doc(db, body: dict, base: dict = None) -> dict:
    """Hitung ulang SELURUH angka Sample Costing di server (sadar satuan)."""
    src = {**(base or {}), **body}
    fabric, fab_total, w1 = await _recompute_costing_lines(db, src.get('fabric_items') or [])
    trim, trim_total, w2 = await _recompute_costing_lines(db, src.get('trim_items') or [])
    bom, bom_total, w3 = await _recompute_costing_lines(db, src.get('bom_lines') or [])
    material = round(fab_total + trim_total + bom_total, 2)
    labor = _num(src.get('labor_cost'), 0)
    overhead = _num(src.get('overhead_cost'), 0)
    return {
        'fabric_items': fabric,
        'trim_items': trim,
        'bom_lines': bom,
        'total_material_cost': material,
        'labor_cost': labor,
        'overhead_cost': overhead,
        'total_cost': round(material + labor + overhead, 2),
        'uom_warnings': w1 + w2 + w3,
    }


# ──────────────────────────────────────────────────────────────────────────────
# MATERIAL RESEARCH (Fabric/Material Research)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/materials')
async def list_materials(
    search: str = None,
    category: str = None,
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if search:
        q['$or'] = [
            {'material_code': {'$regex': re.escape(search), '$options': 'i'}},
            {'material_name': {'$regex': re.escape(search), '$options': 'i'}},
        ]
    if category:
        q['category'] = category

    items = await db.dewi_rnd_materials.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(it) for it in items]


@router.get('/material-options')
async def material_options(
    search: str = None,
    limit: int = Query(500, ge=1, le=2000),
    user: dict = Depends(require_auth),
):
    """Master material (kain/aksesoris) untuk MENAUTKAN baris BOM & costing RnD.

    Tautan inilah yang membuat konversi satuan mungkin: faktor kemasan (`uoms`),
    gramasi & lebar kain, serta harga per satuan dasar (`unit_cost`) semuanya
    tinggal di master `rahaza_materials`.
    """
    db = get_db()
    q = {'active': True, 'type': {'$ne': 'fg'}}
    if search:
        rx = {'$regex': re.escape(search), '$options': 'i'}
        q['$or'] = [{'code': rx}, {'name': rx}]
    proj = {'_id': 0, 'id': 1, 'code': 1, 'name': 1, 'type': 1, 'unit': 1,
            'base_uom': 1, 'unit_cost': 1, 'gsm': 1, 'width_cm': 1}
    rows = await db.rahaza_materials.find(q, proj).sort([('type', 1), ('code', 1)]).to_list(limit)
    return [{
        'material_id': m.get('id'),
        'code': m.get('code') or '',
        'name': m.get('name') or '',
        'type': m.get('type') or '',
        'base_unit': bom_uom.norm_unit(m.get('base_uom') or m.get('unit') or 'pcs'),
        'unit_cost': float(m.get('unit_cost') or 0),
        'has_fabric_dims': bool(bom_uom.fabric_kg_per_meter(m)),
    } for m in rows]


@router.get('/uom-options')
async def uom_options(
    material_id: str = None,
    code: str = None,
    name: str = None,
    user: dict = Depends(require_auth),
):
    """Satuan yang SAH untuk sebuah material + faktornya ke satuan dasar."""
    db = get_db()
    mat = None
    if material_id or code or name:
        mat = await resolve_master_material(db, {'material_id': material_id, 'code': code, 'name': name})
    return {
        'linked': mat is not None,
        'material_id': (mat or {}).get('id'),
        'code': (mat or {}).get('code'),
        'name': (mat or {}).get('name'),
        'base_unit': bom_uom.norm_unit((mat or {}).get('base_uom') or (mat or {}).get('unit') or '') or None,
        'unit_cost': float((mat or {}).get('unit_cost') or 0),
        'units': bom_uom.allowed_units(mat) if mat else [],
        'hint': ('Satuan di luar daftar ini tidak bisa dikonversi otomatis — tambahkan kemasannya '
                 'di master material (Satuan & Kemasan), atau untuk kain lengkapi gramasi & lebar.'),
    }


async def _normalize_material_colors(db, body: dict) -> list:
    """F1 (§A akhir): `dewi_rnd_materials.colors` = daftar warna yang TERSEDIA untuk bahan.

    Dipadankan ke master `rahaza_colors` supaya baris kain/BOM Tech Pack nanti hanya
    bisa memilih warna yang memang ada — bukan teks bebas. Aditif: default `[]`,
    jadi dokumen lama tetap sah.
    """
    from routes.dewi_rnd_colors import _resolve_color
    out, seen = [], set()
    for item in (body.get('colors') or []):
        if isinstance(item, str):
            item = {'name': item}
        doc, _created = await _resolve_color(db, item or {}, allow_create=True)
        if not doc or doc['id'] in seen:
            continue
        seen.add(doc['id'])
        out.append({
            'color_id': doc['id'],
            'code': doc.get('code') or '',
            'name': doc.get('name') or '',
            'hex': doc.get('hex') or '#CCCCCC',
        })
    return out


@router.post('/materials')
async def create_material(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    code = (body.get('material_code') or '').strip().upper()
    name = (body.get('material_name') or '').strip()
    if not code or not name:
        raise HTTPException(400, 'material_code dan material_name wajib diisi')

    existing = await db.dewi_rnd_materials.find_one({'material_code': code})
    if existing:
        raise HTTPException(409, f'Material code {code} sudah ada')

    body = _normalize_price_fields(body)
    colors = await _normalize_material_colors(db, body)
    doc = {
        'id': sid(),
        'material_code': code,
        'material_name': name,
        'category': body.get('category', ''),
        'vendor': body.get('vendor', ''),
        'composition': body.get('composition', ''),
        'weight': body.get('weight', 0),
        # F1: warna yang tersedia untuk bahan ini (rujuk master rahaza_colors)
        'colors': colors,
        # 2026-08-02: harga sadar satuan (price_unit) + cermin price_per_meter
        'price_unit': body['price_unit'],
        'price_per_unit': body['price_per_unit'],
        'price_per_meter': body['price_per_meter'],
        'unit': body.get('unit') or body['price_unit'],
        'linked_material_id': body.get('linked_material_id') or '',
        'min_order_qty': body.get('min_order_qty', 0),
        'test_results': body.get('test_results', ''),
        'notes': body.get('notes', ''),
        'status': body.get('status', 'active'),
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_materials.insert_one(doc)
    return serialize(doc)


@router.get('/materials/{material_id}')
async def get_material(material_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    mat = await db.dewi_rnd_materials.find_one({'id': material_id})
    if not mat:
        raise HTTPException(404, 'Material tidak ditemukan')
    return serialize(mat)


@router.put('/materials/{material_id}')
async def update_material(material_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    body.pop('_id', None)
    body.pop('id', None)
    body.pop('created_at', None)
    if any(k in body for k in ('price_per_unit', 'price_unit', 'price_per_meter', 'unit')):
        existing = await db.dewi_rnd_materials.find_one({'id': material_id}, {'_id': 0}) or {}
        merged = {**existing, **body}
        merged = _normalize_price_fields(merged)
        body.update({k: merged[k] for k in ('price_unit', 'price_per_unit', 'price_per_meter', 'unit')})
    if 'colors' in body:
        body['colors'] = await _normalize_material_colors(db, body)
    body['updated_at'] = now_utc()

    res = await db.dewi_rnd_materials.update_one({'id': material_id}, {'$set': body})
    if res.matched_count == 0:
        raise HTTPException(404, 'Material tidak ditemukan')

    updated = await db.dewi_rnd_materials.find_one({'id': material_id})
    return serialize(updated)


@router.delete('/materials/{material_id}')
async def delete_material(material_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_materials.delete_one({'id': material_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Material tidak ditemukan')
    return {'success': True}


# ──────────────────────────────────────────────────────────────────────────────
# SAMPLE COSTING (Costing & BOM untuk Sample)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/sample-costing')
async def list_sample_costing(
    sample_request_id: str = None,
    limit: int = Query(200, ge=1, le=1000),
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if sample_request_id:
        q['sample_request_id'] = sample_request_id

    items = await db.dewi_rnd_sample_costing.find(q).sort('created_at', -1).limit(limit).to_list(length=limit)
    return [serialize(it) for it in items]


@router.post('/sample-costing/preview')
async def preview_sample_costing(body: dict, user: dict = Depends(require_auth)):
    """Pratinjau biaya sample TANPA menyimpan — dipakai UI untuk tampilkan konversi."""
    db = get_db()
    return await _recompute_costing_doc(db, body)


@router.post('/sample-costing')
async def create_sample_costing(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    sample_request_id = body.get('sample_request_id')
    sample_code = (body.get('sample_code') or '').strip()
    req = None
    if sample_request_id:
        req = await db.dewi_rnd_sample_requests.find_one({'id': sample_request_id})
        if not req:
            raise HTTPException(404, 'Sample request tidak ditemukan')
    elif sample_code:
        req = await db.dewi_rnd_sample_requests.find_one({'sample_code': sample_code})
        sample_request_id = (req or {}).get('id', '')
    if not sample_request_id and not sample_code:
        raise HTTPException(400, 'sample_request_id atau sample_code wajib diisi')

    computed = await _recompute_costing_doc(db, body)
    doc = {
        'id': sid(),
        'sample_request_id': sample_request_id or '',
        'sample_code': sample_code or (req or {}).get('sample_code', ''),
        'style_id': body.get('style_id') or (req or {}).get('style_id', ''),
        'style_name': body.get('style_name') or (req or {}).get('style_name', ''),
        'notes': body.get('notes', ''),
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
        **computed,
    }
    await db.dewi_rnd_sample_costing.insert_one(doc)
    return serialize(doc)


@router.get('/sample-costing/{costing_id}')
async def get_sample_costing(costing_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    costing = await db.dewi_rnd_sample_costing.find_one({'id': costing_id})
    if not costing:
        raise HTTPException(404, 'Sample costing tidak ditemukan')
    return serialize(costing)


@router.put('/sample-costing/{costing_id}')
async def update_sample_costing(costing_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_rnd_sample_costing.find_one({'id': costing_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Sample costing tidak ditemukan')

    for k in ('_id', 'id', 'created_at', 'created_by'):
        body.pop(k, None)
    computed = await _recompute_costing_doc(db, body, existing)
    upd = dict(body)
    upd.update(computed)
    upd['updated_at'] = now_utc()

    await db.dewi_rnd_sample_costing.update_one({'id': costing_id}, {'$set': upd})
    updated = await db.dewi_rnd_sample_costing.find_one({'id': costing_id})
    return serialize(updated)


@router.delete('/sample-costing/{costing_id}')
async def delete_sample_costing(costing_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_sample_costing.delete_one({'id': costing_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Sample costing tidak ditemukan')
    return {'success': True}
