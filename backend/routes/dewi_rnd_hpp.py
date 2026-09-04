"""dewi_rnd — HPP Calculator + Tech Pack."""
from fastapi import Depends, HTTPException
from database import get_db
from auth import require_auth
from routes.dewi_rnd_shared import (
    router, now_utc, sid, serialize,
    line_code, line_name, resolve_master_material, resolve_rnd_material,
)
from utils.fabric_costing import compute_fabric_cost
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar/harga

# ──────────────────────────────────────────────────────────────────────────────
# HPP CALCULATOR (Full Cost per Pcs → Harga Jual Proposal)
# ──────────────────────────────────────────────────────────────────────────────

def _num(value, default):
    """Coerce to float, respecting an explicit 0 (only None/'' fall back to default)."""
    if value is None or value == '':
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _calculate_hpp(body: dict, bom_material_cost=None, cost_lines_total=None) -> dict:
    """Core HPP calculation logic.

    Tiga cara memasok biaya material, dari yang paling baru:

    1. `cost_lines_total` (F4 — HYBRID, sumber PER BARIS). Total = Σ semua baris
       `cost_lines`, apa pun sumbernya (`master` / `techpack` / `manual`).
       Inilah yang diminta owner: master + custom field bisa BERCAMPUR.
    2. `bom_material_cost` (mode lama `use_bom=True`): 100% dari BOM Tech Pack.
    3. Tidak keduanya: 100% manual (`fabric_usage × fabric_price` + accessories).

    (1) dan (2) dipisah supaya dokumen HPP LAMA tetap menghasilkan angka yang
    SAMA — tidak ada uang yang berubah karena refactor ini.

    Biaya CMT (`cmt_cost_per_pcs`) tetap INPUT MANUAL per model (decision 3.a),
    tapi F4 menyediakan saran dari master katalog buyer.
    """
    fabric_usage   = _num(body.get('fabric_usage_per_pcs'), 0)
    fabric_price   = _num(body.get('fabric_price_per_meter'), 0)
    accessories    = body.get('accessories_cost', [])
    cmt_cost       = _num(body.get('cmt_cost_per_pcs'), 0)
    cutting_cost   = _num(body.get('cutting_cost_per_pcs'), 0)
    packaging_cost = _num(body.get('packaging_cost_per_pcs'), 0)
    overhead_pct   = _num(body.get('overhead_pct'), 10)
    margin_pct     = _num(body.get('margin_pct'), 30)

    if cost_lines_total is not None:
        # F4 HYBRID: sumber per baris, total = jumlah SEMUA baris.
        material_cost = _num(cost_lines_total, 0)
        fabric_cost   = material_cost
        acc_total     = 0.0
        material_source = 'cost_lines'
    elif bom_material_cost is not None:
        # Mode BOM otomatis (legacy): material_cost = biaya BOM.
        material_cost = _num(bom_material_cost, 0)
        fabric_cost   = material_cost
        acc_total     = 0.0
        material_source = 'bom'
    else:
        # Mode manual (legacy).
        fabric_cost   = fabric_usage * fabric_price
        acc_total     = sum(
            _num(a.get('unit_cost'), 0) * _num(a.get('qty'), 1)
            for a in accessories
        )
        material_cost = fabric_cost + acc_total
        material_source = 'manual'

    direct_cost   = material_cost + cmt_cost + cutting_cost + packaging_cost
    overhead_val  = direct_cost * overhead_pct / 100
    hpp_total     = direct_cost + overhead_val
    selling_price = hpp_total / (1 - margin_pct / 100) if margin_pct < 100 else hpp_total

    return {
        'fabric_cost':            round(fabric_cost, 2),
        'accessories_total':      round(acc_total, 2),
        'material_cost':          round(material_cost, 2),
        'material_source':        material_source,
        'cmt_cost':               round(cmt_cost, 2),
        'cutting_cost':           round(cutting_cost, 2),
        'packaging_cost':         round(packaging_cost, 2),
        'direct_cost':            round(direct_cost, 2),
        'overhead_value':         round(overhead_val, 2),
        'hpp_total':              round(hpp_total, 2),
        'selling_price_proposal': round(selling_price, 2),
        'margin_pct':             margin_pct,
        'overhead_pct':           overhead_pct,
    }


async def _material_cost_from_bom(db, bom_items: list) -> tuple:
    """Hitung biaya material dari BOM Tech Pack × harga master (KEPUTUSAN #2 / 4.a).

    DIPERBAIKI 2026-08-02 (laporan owner: "satuan & konversi material belum ada di
    RnD untuk BOM-nya, termasuk costing"). Sebelumnya `line_cost = qty × unit_cost`
    TANPA melihat satuan, padahal:
      · `rahaza_materials.unit_cost` = harga per **satuan dasar** (INV-UOM-1),
        mis. per kg untuk kain rajut — sementara baris BOM RnD sering ditulis
        dalam meter/yard/gram/lusin → biaya bisa ratusan kali salah.
      · `dewi_rnd_materials.price_per_meter` = harga per **meter**, dipakai apa
        adanya walau baris BOM bersatuan kg/pcs.

    Sekarang setiap baris dikonversi lewat `core.bom_uom` (kemasan material →
    tabel dimensi global → gramasi×lebar kain), lalu:
      · harga dari master material  → biaya = qty(satuan dasar) × unit_cost
      · harga per meter (RnD)       → biaya = qty(meter) × price_per_meter
    Breakdown mengembalikan qty asli + qty terkonversi + status konversi supaya
    ketidakcocokan satuan kelihatan, bukan diam-diam salah.
    """
    breakdown = []
    total = 0.0
    for line in (bom_items or []):
        row = await _cost_one_line(db, line)
        total += row['line_cost']
        breakdown.append(row)
    return round(total, 2), breakdown


# ── Memoisasi pencarian master material (HANYA lookup, bukan aritmetika) ──────
# Daftar HPP harus memeriksa "harga master sudah berubah?" untuk SEMUA dokumen.
# Tanpa memo, satu kali buka daftar bisa menembak ribuan query (setiap baris
# menembak rahaza_materials 3× + dewi_rnd_materials 2×). Kunci memo sengaja
# hanya identitas material — qty/satuan TIDAK ikut, jadi tidak ada peluang
# angka uang tertukar antar baris.

def _mat_key(line: dict) -> tuple:
    ln = line or {}
    return (
        str(ln.get('material_id') or ln.get('linked_material_id') or ''),
        line_code(ln),
        line_name(ln).lower(),
    )


async def _resolve_master_cached(db, line: dict, cache: dict = None):
    if cache is None:
        return await resolve_master_material(db, line)
    store = cache.setdefault('master', {})
    key = _mat_key(line)
    if key not in store:
        store[key] = await resolve_master_material(db, line)
    return store[key]


async def _resolve_rnd_cached(db, line: dict, cache: dict = None):
    if cache is None:
        return await resolve_rnd_material(db, line)
    store = cache.setdefault('rnd', {})
    key = _mat_key(line)
    if key not in store:
        store[key] = await resolve_rnd_material(db, line)
    return store[key]


async def _cost_one_line(db, line: dict, cache: dict = None) -> dict:
    """Hitung SATU baris material (dipakai BOM legacy DAN cost_lines F4).

    Diekstrak dari `_material_cost_from_bom` tanpa mengubah satu pun aturannya,
    supaya angka dokumen HPP lama TIDAK bergeser sedikit pun.

    `cache` (opsional) HANYA memoisasi hasil pencarian master material —
    aritmetikanya tidak disentuh. Dipakai daftar HPP yang harus memeriksa harga
    basi untuk ratusan baris sekaligus tanpa meledakkan jumlah query.
    """
    qty = _num(line.get('qty') or line.get('quantity') or line.get('usage'), 0)
    code = line_code(line)
    name = line_name(line) or code
    unit = bom_uom.norm_unit(line.get('unit') or '')

    # Baris Tech Pack memakai kunci `material` (nama) — bukan `material_code`.
    # Master dicari lewat id → kode → NAMA supaya baris techpack lama pun
    # tetap dapat harga & faktor konversinya.
    master = await _resolve_master_cached(db, line, cache)
    if master and not code:
        code = str(master.get('code') or '')

    # Konversi baris → satuan dasar material
    factor, base_unit, uom_status, uom_note = bom_uom.line_factor(master, unit or None)
    qty_base = round(qty * factor, 6)

    unit_cost = _num(line.get('unit_cost') or line.get('unit_price'), 0)
    source = 'bom_line' if unit_cost > 0 else None
    cost_unit = unit or base_unit          # satuan yang dipakai harga baris
    qty_for_cost = qty if unit_cost > 0 else qty_base

    if unit_cost <= 0 and master and _num(master.get('unit_cost'), 0) > 0:
        unit_cost = _num(master.get('unit_cost'), 0)
        source = 'rahaza_materials.unit_cost'
        cost_unit = base_unit
        qty_for_cost = qty_base
        name = name or master.get('name') or code
    if unit_cost <= 0:
        rm = await _resolve_rnd_cached(db, line, cache)
        if rm:
            # RnD boleh menyatakan satuan harganya sendiri (`unit`/`price_unit`);
            # default lama = per meter.
            rnd_unit = bom_uom.norm_unit(rm.get('price_unit') or rm.get('unit') or 'm')
            rnd_price = _num(rm.get('price_per_unit') or rm.get('price_per_meter'), 0)
            if rnd_price > 0:
                qty_in_rnd_unit = None
                if rnd_unit == (unit or rnd_unit):
                    qty_in_rnd_unit = qty
                else:
                    gf = bom_uom.global_factor(unit or rnd_unit, rnd_unit)
                    if gf:
                        qty_in_rnd_unit = qty * gf
                    elif master is not None:
                        f2, _b, st2, _n2 = bom_uom.line_factor(master, rnd_unit)
                        if st2 in ('base', 'uom', 'global', 'fabric') and f2:
                            qty_in_rnd_unit = qty_base / f2
                if qty_in_rnd_unit is not None:
                    unit_cost = rnd_price
                    source = f'dewi_rnd_materials.price_per_{rnd_unit}'
                    cost_unit = rnd_unit
                    qty_for_cost = round(qty_in_rnd_unit, 6)
                    name = name or rm.get('material_name') or code
                else:
                    uom_status = 'mismatch'
                    uom_note = (uom_note or '') + (
                        f" Harga RnD per {rnd_unit} tidak bisa dipakai untuk satuan "
                        f"BOM '{unit or '-'}' (lengkapi satuan/kemasan material).")

    line_cost = _num(qty_for_cost, 0) * unit_cost
    return {
        'material_id': (master or {}).get('id') or line.get('material_id') or '',
        'material_code': code,
        'material_name': name,
        'master_linked': master is not None,
        'qty': qty,
        'unit': unit,
        'qty_base': qty_base,
        'unit_base': base_unit,
        'uom_factor': round(factor, 8),
        'uom_status': uom_status,
        'uom_note': uom_note,
        'qty_costed': round(_num(qty_for_cost, 0), 6),
        'cost_unit': cost_unit,
        'unit_cost': round(unit_cost, 2),
        'line_cost': round(line_cost, 2),
        'cost_source': source or 'unresolved',
    }


# ══════════════════════════════════════════════════════════════════════════════
# F4 — HPP HYBRID: sumber biaya PER BARIS (Master / Techpack / Manual)
# ══════════════════════════════════════════════════════════════════════════════

COST_SOURCES = ('master', 'techpack', 'manual')


async def compute_cost_lines(db, raw_lines: list) -> tuple:
    """Hitung `cost_lines` hybrid → (total, lines).

    Kenapa ini ada: dulu `use_bom` adalah saklar GLOBAL (semua-atau-tidak), jadi
    MUSTAHIL sebagian baris dari master dan sebagian custom. Sekarang setiap baris
    membawa `source`-nya sendiri dan totalnya adalah jumlah SEMUA baris.

    Kebijakan **D1** (dipilih owner): harga master BOLEH ditimpa, TAPI
    `override_reason` WAJIB — nego harga itu nyata, tapi harus berjejak.
    `unit_cost_master` disimpan sebagai snapshot supaya sistem bisa memberi tahu
    "harga master sudah berubah, perbarui?" (lihat `/stale-check`).
    """
    out, total = [], 0.0
    for idx, raw in enumerate(raw_lines or []):
        raw = dict(raw or {})
        source = str(raw.get('source') or 'manual').strip().lower()
        if source not in COST_SOURCES:
            raise HTTPException(
                400,
                f"Baris biaya #{idx + 1}: sumber '{source}' tidak dikenal. "
                f"Pilih salah satu: Master / Techpack / Manual.",
            )

        label = str(raw.get('label') or raw.get('material_name') or raw.get('material') or '').strip()
        qty = _num(raw.get('qty'), 1)
        override = bool(raw.get('override'))
        reason = str(raw.get('override_reason') or '').strip()

        # D1 — override wajib beralasan (berlaku untuk sumber yang punya harga master)
        if override and source in ('master', 'techpack') and not reason:
            raise HTTPException(
                400,
                f"Baris biaya #{idx + 1} ({label or 'tanpa nama'}): harga master ditimpa "
                f"tapi ALASAN belum diisi. Isi alasannya (mis. \"nego supplier\") supaya "
                f"perubahan harga ada jejaknya.",
            )

        if source == 'manual':
            unit_cost_used = _num(raw.get('unit_cost_used'), _num(raw.get('unit_cost'), 0))
            row = {
                'line_id': raw.get('line_id') or sid(),
                'label': label or f'Baris manual #{idx + 1}',
                'source': 'manual',
                'material_id': '', 'material_code': '', 'material_name': '',
                'master_linked': False,
                'qty': qty,
                'unit': str(raw.get('unit') or 'pcs'),
                'qty_costed': qty,
                'cost_unit': str(raw.get('unit') or 'pcs'),
                'unit_cost_master': 0.0,
                'unit_cost_used': round(unit_cost_used, 2),
                'override': False,
                'override_reason': '',
                'line_cost': round(qty * unit_cost_used, 2),
                'cost_source': 'manual',
                'uom_status': 'manual',
                'uom_note': '',
            }
        else:
            probe = {
                'material_id': raw.get('material_id'),
                'material_code': raw.get('material_code'),
                'material_name': raw.get('material_name') or label,
                'material': raw.get('material') or label,
                'qty': qty,
                'unit': raw.get('unit'),
            }
            # Harga master murni: JANGAN pakai unit_cost baris sebagai harga master.
            costed = await _cost_one_line(db, probe)
            unit_cost_master = _num(costed.get('unit_cost'), 0)
            unit_cost_used = (_num(raw.get('unit_cost_used'), unit_cost_master)
                              if override else unit_cost_master)
            qty_costed = _num(costed.get('qty_costed'), qty)
            row = {
                'line_id': raw.get('line_id') or sid(),
                'label': label or costed.get('material_name') or f'Baris #{idx + 1}',
                'source': source,
                'material_id': costed.get('material_id') or '',
                'material_code': costed.get('material_code') or '',
                'material_name': costed.get('material_name') or '',
                'master_linked': bool(costed.get('master_linked')),
                'qty': qty,
                'unit': costed.get('unit') or '',
                'qty_costed': qty_costed,
                'cost_unit': costed.get('cost_unit') or '',
                'unit_cost_master': round(unit_cost_master, 2),
                'unit_cost_used': round(unit_cost_used, 2),
                'override': override,
                'override_reason': reason if override else '',
                'line_cost': round(qty_costed * unit_cost_used, 2),
                'cost_source': costed.get('cost_source') or 'unresolved',
                'uom_status': costed.get('uom_status'),
                'uom_note': costed.get('uom_note'),
            }
            if not row['master_linked']:
                row['warn'] = ('Baris ini tidak tertaut master material — harga & konversi '
                               'satuan tidak bisa dihitung. Pilih materialnya atau ubah '
                               'sumbernya menjadi Manual.')
        total += row['line_cost']
        out.append(row)
    return round(total, 2), out


def legacy_cost_lines(doc: dict) -> list:
    """Baca dokumen HPP LAMA sebagai `cost_lines` — TANPA mengubah angkanya.

    Sesuai proposal §D: `use_bom=True` ⇒ semua baris bersumber `techpack`
    (dari `bom_breakdown` yang sudah tersimpan); `use_bom=False` ⇒ semua `manual`
    (kain + aksesoris). Hanya untuk DIBACA/ditampilkan; `hpp_total` tersimpan
    tidak pernah dihitung ulang dari sini.
    """
    if doc.get('cost_lines'):
        return doc['cost_lines']
    lines = []
    if doc.get('use_bom'):
        for b in (doc.get('bom_breakdown') or []):
            lines.append({
                'line_id': f"legacy-{b.get('material_code') or b.get('material_name') or len(lines)}",
                'label': b.get('material_name') or b.get('material_code') or 'Baris BOM',
                'source': 'techpack',
                'material_id': '', 'material_code': b.get('material_code') or '',
                'material_name': b.get('material_name') or '',
                'master_linked': b.get('cost_source') not in (None, '', 'unresolved'),
                'qty': b.get('qty'), 'unit': b.get('unit'),
                'qty_costed': b.get('qty_costed'), 'cost_unit': b.get('cost_unit'),
                'unit_cost_master': b.get('unit_cost'), 'unit_cost_used': b.get('unit_cost'),
                'override': False, 'override_reason': '',
                'line_cost': b.get('line_cost'), 'cost_source': b.get('cost_source'),
                'uom_status': b.get('uom_status'), 'uom_note': b.get('uom_note'),
                'legacy': True,
            })
    else:
        fu = _num(doc.get('fabric_usage_per_pcs'), 0)
        fp = _num(doc.get('fabric_price_per_meter'), 0)
        if fu or fp:
            lines.append({
                'line_id': 'legacy-fabric', 'label': 'Kain (input manual lama)',
                'source': 'manual', 'material_id': '', 'material_code': '', 'material_name': '',
                'master_linked': False, 'qty': fu, 'unit': 'm', 'qty_costed': fu, 'cost_unit': 'm',
                'unit_cost_master': 0.0, 'unit_cost_used': round(fp, 2),
                'override': False, 'override_reason': '',
                'line_cost': round(fu * fp, 2), 'cost_source': 'manual',
                'uom_status': 'manual', 'uom_note': '', 'legacy': True,
            })
        for a in (doc.get('accessories_cost') or []):
            q = _num(a.get('qty'), 1)
            uc = _num(a.get('unit_cost'), 0)
            lines.append({
                'line_id': f"legacy-acc-{a.get('name') or len(lines)}",
                'label': a.get('name') or 'Aksesoris', 'source': 'manual',
                'material_id': '', 'material_code': '', 'material_name': '',
                'master_linked': False, 'qty': q, 'unit': 'pcs', 'qty_costed': q, 'cost_unit': 'pcs',
                'unit_cost_master': 0.0, 'unit_cost_used': round(uc, 2),
                'override': False, 'override_reason': '',
                'line_cost': round(q * uc, 2), 'cost_source': 'manual',
                'uom_status': 'manual', 'uom_note': '', 'legacy': True,
            })
    return lines


async def annotate_techpack_bom(db, bom_items: list) -> list:
    """Tautkan baris BOM Tech Pack ke master material + simpan hasil konversi satuannya.

    Ditulis saat tech pack disimpan supaya `qty_base`/`unit_base`/`uom_status`
    tersedia untuk konsumen hilir (HPP dari BOM, tampilan Tech Pack) tanpa
    menghitung ulang, dan supaya satuan yang tidak bisa dikonversi kelihatan.

    F3/C1 (2026-08-07): baris yang TIDAK tertaut master sekarang diberi
    `master_linked=False` + `master_link_note`. Alasannya: baris tanpa master
    tidak punya harga & faktor konversi satuan, jadi HPP-nya salah **diam-diam**.
    Dengan penanda ini layar bisa memasang badge peringatan, dan pemakai tahu
    angka mana yang belum bisa dipercaya. C5: kolom warna baris ikut dilengkapi.
    """
    from utils.rnd_techpack import attach_row_color
    out = []
    for line in (bom_items or []):
        row = dict(line)
        master = await resolve_master_material(db, row)
        unit = bom_uom.norm_unit(row.get('unit') or '')
        factor, base_unit, status, note = bom_uom.line_factor(master, unit or None)
        qty = _num(row.get('qty'), 0)
        row['unit'] = unit or base_unit
        if master:
            row['material_id'] = master.get('id')
            row['material_code'] = master.get('code') or row.get('material_code') or ''
            row['master_linked'] = True
            row['master_name'] = master.get('name') or ''
            row['master_unit_cost'] = _num(master.get('unit_cost'), 0)
            row.pop('master_link_note', None)
        else:
            row['master_linked'] = False
            row['master_unit_cost'] = 0.0
            row['master_link_note'] = (
                'Tanpa tautan master: harga & konversi satuan TIDAK dihitung — '
                'HPP dari BOM untuk baris ini akan meleset. Pilih materialnya di '
                'kolom "Tautkan master".'
            )
        row = await attach_row_color(db, row)
        row.update({
            'unit_base': base_unit,
            'uom_factor': round(factor, 8),
            'qty_base': round(qty * factor, 6),
            'uom_status': status,
            'uom_note': note,
        })
        out.append(row)
    return out


async def _normalize_techpack_payload(db, body: dict, existing: dict = None) -> dict:
    """F3 — satukan semua pengencang Tech Pack di SATU tempat (dipakai POST & PUT).

    Yang dilakukan:
      · `size_columns` → `[{col_id,label}]` stabil (col_id lama dipertahankan)
      · `measurements` → `values` berkunci `col_id` (+ `values_legacy`, `orphan_values`)
      · `base_size`/`size_range` diambil dari `size_list` style (satu sumber ukuran)
      · `fabric_consumption.size` ditandai bila di luar `size_list`
      · `colorways` + warna baris `fabrics`/`bom_items` dipadankan ke master warna
      · `bom_unlinked_count` dihitung untuk badge peringatan di layar
    """
    from utils.rnd_techpack import (
        normalize_size_columns, normalize_measurements, normalize_colorways,
        attach_row_color, normalize_fabric_consumption,
    )
    from routes.dewi_rnd_sizes import resolve_style_sizes, compute_size_range, pick_base_size

    existing = existing or {}
    out = {}
    style_id = body.get('style_id', existing.get('style_id', ''))

    sizes_info = await resolve_style_sizes(db, style_id) if style_id else {'size_list': []}
    size_list = sizes_info.get('size_list') or []

    # ── C3 kolom ukuran + measurements ──
    if 'size_columns' in body or 'measurements' in body:
        raw_cols = body.get('size_columns', existing.get('size_columns'))
        cols = normalize_size_columns(raw_cols)
        if not cols and size_list:
            cols = normalize_size_columns(size_list)
        out['size_columns'] = cols
        raw_meas = body.get('measurements', existing.get('measurements'))
        rows, stats = normalize_measurements(raw_meas, cols)
        out['measurements'] = rows
        out['measurements_stats'] = stats

    # ── C2 konsumsi kain terikat daftar ukuran ──
    if 'fabric_consumption' in body:
        cons, off = normalize_fabric_consumption(body.get('fabric_consumption'), size_list)
        out['fabric_consumption'] = cons
        out['fabric_consumption_off_list'] = off

    # ── C5 warna baris kain ──
    if 'fabrics' in body:
        out['fabrics'] = [await attach_row_color(db, dict(r or {})) for r in (body.get('fabrics') or [])]

    # ── C4 colorways tech pack ──
    if 'colorways' in body:
        out['colorways'] = await normalize_colorways(db, body.get('colorways'))

    # ── C1 badge "tanpa master" ──
    if 'bom_items' in body:
        items = await annotate_techpack_bom(db, body.get('bom_items') or [])
        out['bom_items'] = items
        out['bom_unlinked_count'] = len([b for b in items if not b.get('master_linked')])

    # ── B/F2 base_size & size_range: satu sumber = size_list style ──
    if size_list:
        out['base_size'] = pick_base_size(size_list, body.get('base_size') or existing.get('base_size'))
        out['size_range'] = compute_size_range(size_list)
        out['style_size_list'] = size_list
    return out



async def _latest_bom_for_style(db, style_id: str) -> list:
    """Ambil bom_items dari tech-pack terbaru (is_latest) untuk sebuah style."""
    tp = await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id, 'is_latest': True}, {'_id': 0}
    )
    if not tp:
        tp = await db.dewi_rnd_tech_packs.find_one(
            {'style_id': style_id}, {'_id': 0}, sort=[('created_at', -1)]
        )
    return (tp or {}).get('bom_items', []) or []


async def _propagate_hpp(db, style_id: str, hpp_total: float, selling_price=None) -> dict:
    """Propagasi HPP RnD → Production Model → FG → Katalog Marketing (auto-refresh).

    KEPUTUSAN #2 (4.a): saat HPP RnD dihitung/di-update, HPP pada item katalog yang
    tertaut (via model_id / fg_material_id) ikut ter-refresh otomatis. `hpp` katalog =
    HPP dari RnD (bukan input marketing).
    """
    if not style_id:
        return {'models': 0, 'fg': 0, 'catalog_items': 0}
    now = now_utc()
    hpp_total = round(_num(hpp_total, 0), 2)

    # 1) Production models turunan style ini
    model_ids = [m['id'] async for m in db.rahaza_models.find({'rnd_style_id': style_id}, {'id': 1})]
    if model_ids:
        await db.rahaza_models.update_many(
            {'id': {'$in': model_ids}},
            # `hpp_rnd` = nilai ASAL R&D (SSOT sumber), `hpp` = nilai EFEKTIF yang
            # dibaca 34 pintu lama. Tanpa `hpp_rnd`, produk manual dengan
            # `hpp == base_hpp` akan salah dilaporkan bersumber 'rnd' (F5).
            {'$set': {'hpp': hpp_total, 'hpp_rnd': hpp_total,
                      'hpp_source': 'rnd', 'hpp_updated_at': now}},
        )

    # 2) FG (rahaza_materials type='fg') tertaut ke style / model → set hpp
    fg_filter = {'$or': [{'rnd_style_id': style_id}]}
    if model_ids:
        fg_filter['$or'].append({'model_id': {'$in': model_ids}})
    fg_ids = [f['id'] async for f in db.rahaza_materials.find(fg_filter, {'id': 1})]
    if fg_ids:
        await db.rahaza_materials.update_many(
            {'id': {'$in': fg_ids}},
            {'$set': {'hpp': hpp_total, 'hpp_source': 'rnd', 'hpp_updated_at': now}},
        )

    # 3) Katalog marketing tertaut (model_id ATAU fg_material_id)
    cat_or = []
    if model_ids:
        cat_or.append({'model_id': {'$in': model_ids}})
    if fg_ids:
        cat_or.append({'fg_material_id': {'$in': fg_ids}})
    cat_modified = 0
    if cat_or:
        res = await db.marketing_catalog_items.update_many(
            {'$or': cat_or},
            {'$set': {
                'hpp': hpp_total,
                'hpp_source': 'rnd',
                'hpp_updated_at': now,
                'updated_at': now,
            }},
        )
        cat_modified = res.modified_count
    return {'models': len(model_ids), 'fg': len(fg_ids), 'catalog_items': cat_modified}


@router.get('/hpp-calculator')
async def list_hpp(
    style_id: str = None,
    with_stale: bool = True,
    user: dict = Depends(require_auth),
):
    """Daftar HPP + TANDA "harga master sudah berubah" per dokumen.

    Kenapa tandanya di DAFTAR (permintaan owner 2026-08-08): `stale-check` dulu
    hanya dipanggil saat modal Edit dibuka, jadi HPP yang harganya sudah basi
    tidak kelihatan sampai seseorang kebetulan membukanya satu per satu. Padahal
    inilah angka yang dipakai menetapkan harga jual.

    Yang DIJAMIN tidak terjadi: tidak ada satu pun angka tersimpan yang berubah.
    `hpp_total`, `direct_cost`, dan `cost_lines[].line_cost` dikembalikan APA
    ADANYA; perbandingan harga master hanya ditambahkan sebagai field BARU
    (`stale_count`, `stale_delta_total`, `stale_lines`).

    `with_stale=false` mematikan perbandingan (daftar tercepat, mis. untuk
    pemanggil lain yang hanya butuh angkanya).
    """
    db = get_db()
    q = {}
    if style_id:
        q['style_id'] = style_id
    docs = await db.dewi_rnd_hpp.find(q, {'_id': 0}).sort('created_at', -1).to_list(200)
    cache: dict = {}          # memo lookup master, dibagi SEMUA dokumen di daftar ini
    out = []
    for d in docs:
        row = serialize(d)
        # F4 kompatibilitas mundur: dokumen lama DIBACA sebagai cost_lines
        # (techpack bila use_bom, selain itu manual) — total tersimpan tidak diubah.
        row['cost_lines'] = legacy_cost_lines(d)
        row['cost_lines_legacy'] = not bool(d.get('cost_lines'))
        if with_stale:
            stale, checked = await _stale_lines_for_doc(db, {**d, 'cost_lines': row['cost_lines']},
                                                        cache)
            row['stale_checked_lines'] = checked
            row['stale_count'] = len(stale)
            row['stale_delta_total'] = round(sum(s['delta'] for s in stale), 2)
            row['stale_lines'] = stale
        out.append(row)
    return out


@router.get('/hpp/fabric-estimate')
async def hpp_fabric_estimate(
    style_id: str,
    size: str = None,
    user: dict = Depends(require_auth),
):
    """#1 HPP otomatis: estimasi biaya kain/pcs per-size dari fabric_consumption techpack.

    Dipakai HPP Calculator (auto-fill pemakaian kain + harga tertimbang) & Pola/Marking.
    """
    db = get_db()
    tp = await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id, 'is_latest': True}, {'_id': 0}
    ) or await db.dewi_rnd_tech_packs.find_one(
        {'style_id': style_id}, {'_id': 0}, sort=[('created_at', -1)]
    )
    if not tp:
        raise HTTPException(404, 'Tech pack untuk style ini belum ada. Buat/import techpack dulu.')
    res = await compute_fabric_cost(db, tp, size)
    res['style_id'] = style_id
    res['style_code'] = tp.get('style_code', '')
    res['style_name'] = tp.get('style_name', '')
    res['fabric_consumption_rows'] = len(tp.get('fabric_consumption') or [])
    return serialize(res)


@router.post('/hpp-calculator')
async def create_hpp(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    style_id = body.get('style_id', '')

    # F4 HYBRID (baru): sumber biaya per baris. Menang atas `use_bom` bila dikirim.
    raw_lines = body.get('cost_lines')
    cost_lines, lines_total = [], None
    if isinstance(raw_lines, list) and len(raw_lines) > 0:
        lines_total, cost_lines = await compute_cost_lines(db, raw_lines)

    # Mode BOM otomatis (KEPUTUSAN #2 / 4.a): material dari BOM × unit_cost master.
    use_bom = bool(body.get('use_bom')) or ('bom_items' in body)
    bom_breakdown = []
    if lines_total is not None:
        calc = _calculate_hpp(body, cost_lines_total=lines_total)
    elif use_bom:
        bom_items = body.get('bom_items')
        if not bom_items and style_id:
            bom_items = await _latest_bom_for_style(db, style_id)
        material_cost, bom_breakdown = await _material_cost_from_bom(db, bom_items or [])
        calc = _calculate_hpp(body, bom_material_cost=material_cost)
    else:
        calc = _calculate_hpp(body)

    doc = {
        'id':         sid(),
        'hpp_code':   body.get('hpp_code', f"HPP-{sid()[:6].upper()}"),
        'style_id':   style_id,
        'style_code': body.get('style_code', ''),
        'style_name': body.get('style_name', ''),
        'fabric_usage_per_pcs':   body.get('fabric_usage_per_pcs', 0),
        'fabric_price_per_meter': body.get('fabric_price_per_meter', 0),
        'fabric_source':          body.get('fabric_source', 'manual'),   # 'techpack' bila di-tarik dari fabric_consumption
        'fabric_size':            body.get('fabric_size', ''),           # size acuan saat tarik dari techpack
        'accessories_cost':       body.get('accessories_cost', []),
        'cmt_cost_per_pcs':       body.get('cmt_cost_per_pcs', 0),
        'cmt_cost_source':        body.get('cmt_cost_source', 'manual'), # F4: 'catalog' bila dari master katalog buyer
        'cmt_cost_ref':           body.get('cmt_cost_ref', ''),
        'cutting_cost_per_pcs':   body.get('cutting_cost_per_pcs', 0),
        'packaging_cost_per_pcs': body.get('packaging_cost_per_pcs', 0),
        'overhead_pct':           body.get('overhead_pct', 10),
        'margin_pct':             body.get('margin_pct', 30),
        # `use_bom` TETAP DISIMPAN (kompatibilitas mundur — proposal §D)
        'use_bom':                use_bom,
        'bom_breakdown':          bom_breakdown,
        'cost_lines':             cost_lines,
        'notes':                  body.get('notes', ''),
        'status':                 body.get('status', 'draft'),
        **calc,
        'created_by':      user['id'],
        'created_by_name': user.get('name', ''),
        'created_at': now_utc(),
        'updated_at': now_utc(),
    }
    await db.dewi_rnd_hpp.insert_one(doc)
    # Auto-refresh HPP ke model/FG/katalog tertaut.
    propagation = await _propagate_hpp(db, style_id, doc['hpp_total'], doc.get('selling_price_proposal'))
    out = serialize(doc)
    out['_propagation'] = propagation
    return out


@router.put('/hpp-calculator/{calc_id}')
async def update_hpp(calc_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')

    style_id = body.get('style_id', existing.get('style_id', ''))
    merged = {**existing, **body}

    raw_lines = body.get('cost_lines', existing.get('cost_lines'))
    cost_lines, lines_total = existing.get('cost_lines') or [], None
    if isinstance(raw_lines, list) and len(raw_lines) > 0:
        lines_total, cost_lines = await compute_cost_lines(db, raw_lines)

    use_bom = body.get('use_bom', existing.get('use_bom'))
    use_bom = bool(use_bom) or ('bom_items' in body)
    bom_breakdown = existing.get('bom_breakdown', [])
    if lines_total is not None:
        calc = _calculate_hpp(merged, cost_lines_total=lines_total)
    elif use_bom:
        bom_items = body.get('bom_items')
        if not bom_items and style_id:
            bom_items = await _latest_bom_for_style(db, style_id)
        material_cost, bom_breakdown = await _material_cost_from_bom(db, bom_items or [])
        # gabungkan input manual lain (cmt/cutting/packaging/overhead/margin) dari body+existing
        calc = _calculate_hpp(merged, bom_material_cost=material_cost)
    else:
        calc = _calculate_hpp(merged)

    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by', 'bom_items')}
    upd.update(calc)
    upd['use_bom'] = use_bom
    upd['bom_breakdown'] = bom_breakdown
    upd['cost_lines'] = cost_lines
    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_hpp.update_one({'id': calc_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')
    doc = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    propagation = await _propagate_hpp(db, style_id, doc.get('hpp_total'), doc.get('selling_price_proposal'))
    out = serialize(doc)
    out['_propagation'] = propagation
    return out


@router.delete('/hpp-calculator/{calc_id}')
async def delete_hpp(calc_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_hpp.delete_one({'id': calc_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')
    return {'ok': True}


@router.post('/hpp-calculator/preview')
async def preview_hpp(body: dict, user: dict = Depends(require_auth)):
    """Hitung HPP tanpa menyimpan (live preview).

    F4: bila `cost_lines` dikirim, dipakai mode HYBRID (sumber per baris) dan
    tiap baris dikembalikan lengkap dengan `unit_cost_master`, `unit_cost_used`,
    `override_reason`, dan `line_cost` supaya layar bisa menampilkan tabelnya.
    """
    raw_lines = body.get('cost_lines')
    if isinstance(raw_lines, list) and len(raw_lines) > 0:
        db = get_db()
        total, lines = await compute_cost_lines(db, raw_lines)
        calc = _calculate_hpp(body, cost_lines_total=total)
        return {
            **calc,
            'cost_lines': lines,
            'cost_lines_total': total,
            'cost_lines_count': len(lines),
            'cost_lines_unlinked': len([l for l in lines
                                        if l['source'] != 'manual' and not l.get('master_linked')]),
        }
    return _calculate_hpp(body)


@router.post('/hpp-calculator/cost-lines/from-techpack')
async def cost_lines_from_techpack(body: dict, user: dict = Depends(require_auth)):
    """Ubah BOM Tech Pack terbaru sebuah style menjadi `cost_lines` bersumber `techpack`.

    Tombol "Tarik dari Techpack BOM" di layar HPP memakai ini. Perilaku harga per
    baris SAMA dengan mode `use_bom` lama (§D: "perilaku yang sudah benar hari ini,
    dipertahankan") — yang berubah hanya: hasilnya bisa DICAMPUR dengan baris lain.
    """
    db = get_db()
    style_id = str(body.get('style_id') or '').strip()
    bom_items = body.get('bom_items')
    if not bom_items and style_id:
        bom_items = await _latest_bom_for_style(db, style_id)
    if not bom_items:
        raise HTTPException(
            404,
            'BOM Tech Pack untuk style ini belum ada. Buat/impor Tech Pack yang berisi BOM dulu.',
        )
    raw = [{
        'source': 'techpack',
        'label': line_name(b) or line_code(b) or 'Baris BOM',
        'material_id': b.get('material_id') or '',
        'material_code': b.get('material_code') or '',
        'material_name': line_name(b),
        'material': b.get('material') or '',
        'qty': b.get('qty') or 0,
        'unit': b.get('unit') or '',
    } for b in bom_items]
    total, lines = await compute_cost_lines(db, raw)
    return {
        'cost_lines': lines,
        'cost_lines_total': total,
        'bom_items_count': len(bom_items),
        'unlinked_count': len([l for l in lines if not l.get('master_linked')]),
        'style_id': style_id,
    }


@router.get('/hpp-calculator/cmt-suggestions')
async def cmt_suggestions(
    search: str = None,
    user: dict = Depends(require_auth),
):
    """Saran ongkos CMT dari MASTER katalog buyer (`dewi_maklon_buyer_catalog`).

    Proposal §2.4: `cmt_cost_per_pcs` selama ini angka manual tanpa sumber master,
    padahal `default_cmt_price` sudah ada. Ini membuat masternya bisa dipakai
    tanpa memaksa — pengguna tetap boleh mengetik angka sendiri.
    """
    db = get_db()
    q = {'default_cmt_price': {'$gt': 0}}
    if search:
        import re as _re
        rx = {'$regex': _re.escape(search), '$options': 'i'}
        q['$or'] = [{'artikel_code': rx}, {'product_name': rx}, {'buyer_ref_code': rx}]
    rows = await db.dewi_maklon_buyer_catalog.find(
        q, {'_id': 0, 'id': 1, 'artikel_code': 1, 'product_name': 1,
            'buyer_ref_code': 1, 'default_cmt_price': 1, 'client_name': 1},
    ).sort('artikel_code', 1).to_list(200)
    return [{
        'catalog_id': r.get('id'),
        'code': r.get('artikel_code') or r.get('buyer_ref_code') or '',
        'name': r.get('product_name') or '',
        'client_name': r.get('client_name') or '',
        'cmt_price': float(r.get('default_cmt_price') or 0),
    } for r in rows]


async def _stale_lines_for_doc(db, doc: dict, cache: dict = None) -> tuple:
    """(stale_lines, checked_lines) untuk SATU dokumen HPP — SATU definisi "basi".

    Dipakai bersama oleh `/stale-check` (detail, di dalam form) dan
    `GET /hpp-calculator` (badge di DAFTAR). Sengaja satu fungsi supaya daftar
    dan form tidak mungkin memberi jawaban berbeda untuk dokumen yang sama.

    Baris `manual` dilewati: harganya memang milik pengguna, tidak punya master
    untuk dibandingkan. Dokumen HPP LAMA dibaca sebagai `manual` oleh
    `legacy_cost_lines()`, jadi dokumen lama tidak akan pernah ditandai basi —
    dan angkanya tidak pernah disentuh.
    """
    lines = doc.get('cost_lines') or []
    stale, checked = [], 0
    for l in lines:
        if l.get('source') == 'manual':
            continue
        checked += 1
        # Sengaja TIDAK mengirim `unit_cost`: kita mau HARGA MASTER MURNI sekarang,
        # bukan harga yang tersimpan di baris.
        current = await _cost_one_line(db, {
            'material_id': l.get('material_id'), 'material_code': l.get('material_code'),
            'material_name': l.get('material_name'), 'qty': l.get('qty'), 'unit': l.get('unit'),
        }, cache)
        now_cost = _num(current.get('unit_cost'), 0)
        snap = _num(l.get('unit_cost_master'), 0)
        if abs(now_cost - snap) > 0.005:
            stale.append({
                'line_id': l.get('line_id'), 'label': l.get('label'),
                'material_code': l.get('material_code'),
                'unit_cost_snapshot': snap, 'unit_cost_now': round(now_cost, 2),
                'delta': round(now_cost - snap, 2),
                'direction': 'naik' if now_cost > snap else 'turun',
                'override': bool(l.get('override')),
                'override_reason': l.get('override_reason') or '',
                'line_cost_saved': round(_num(l.get('line_cost'), 0), 2),
                'line_cost_now': round(_num(current.get('qty_costed'), 0) * now_cost, 2),
            })
    return stale, checked


@router.get('/hpp-calculator/{calc_id}/stale-check')
async def hpp_stale_check(calc_id: str, user: dict = Depends(require_auth)):
    """"Harga master sudah berubah, perbarui?" — bandingkan snapshot vs harga master kini.

    Sumber `master`/`techpack` menyimpan `unit_cost_master` sebagai SNAPSHOT saat
    HPP dihitung. Endpoint ini membandingkannya dengan harga master sekarang,
    sehingga layar bisa memberi tanda baris mana yang perlu diperbarui — tanpa
    pernah mengubah angka tersimpan diam-diam.
    """
    db = get_db()
    doc = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')

    stale, checked = await _stale_lines_for_doc(db, doc, {})
    return {
        'hpp_id': calc_id, 'hpp_code': doc.get('hpp_code'),
        'checked_lines': checked,
        'stale_count': len(stale),
        'stale_lines': stale,
        'hint': ('Harga master berubah sejak HPP ini dihitung. Buka HPP-nya lalu '
                 'Simpan ulang untuk memakai harga baru — angka lama tidak diubah otomatis.'),
    }


@router.post('/hpp-calculator/compute-from-bom')
async def compute_hpp_from_bom(body: dict, user: dict = Depends(require_auth)):
    """Preview HPP dengan biaya material OTOMATIS dari BOM (KEPUTUSAN #2 / decision 4.a).

    Body:
      - style_id (opsional): jika diberikan & bom_items kosong → ambil BOM dari tech-pack terbaru.
      - bom_items (opsional): override daftar BOM [{material_code|material_id, qty, unit, unit_cost?}].
      - cmt_cost_per_pcs, cutting_cost_per_pcs, packaging_cost_per_pcs (manual), overhead_pct, margin_pct.
    Return: hasil kalkulasi + material_breakdown + bom_material_cost.
    """
    db = get_db()
    style_id = body.get('style_id', '')
    bom_items = body.get('bom_items')
    if not bom_items and style_id:
        bom_items = await _latest_bom_for_style(db, style_id)
    material_cost, breakdown = await _material_cost_from_bom(db, bom_items or [])
    calc = _calculate_hpp(body, bom_material_cost=material_cost)
    return {
        **calc,
        'bom_material_cost': material_cost,
        'material_breakdown': breakdown,
        'bom_items_count': len(bom_items or []),
        'style_id': style_id,
    }


@router.post('/hpp-calculator/{calc_id}/propagate')
async def propagate_hpp_endpoint(calc_id: str, user: dict = Depends(require_auth)):
    """Paksa propagasi ulang HPP ini ke Production Model → FG → Katalog Marketing."""
    db = get_db()
    doc = await db.dewi_rnd_hpp.find_one({'id': calc_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'HPP calculation tidak ditemukan')
    result = await _propagate_hpp(db, doc.get('style_id', ''), doc.get('hpp_total'), doc.get('selling_price_proposal'))
    return {'ok': True, 'hpp_total': doc.get('hpp_total'), 'propagation': result}


# ──────────────────────────────────────────────────────────────────────────────
# TECH PACK (Dokumen teknis per style: BOM, konstruksi, grading)
# ──────────────────────────────────────────────────────────────────────────────

@router.get('/tech-packs')
async def list_tech_packs(
    style_id: str = None,
    search: str = None,
    user: dict = Depends(require_auth),
):
    db = get_db()
    q: dict = {}
    if style_id:
        q['style_id'] = style_id
    if search:
        q['$or'] = [
            {'style_code':  {'$regex': search, '$options': 'i'}},
            {'style_name':  {'$regex': search, '$options': 'i'}},
            {'version':     {'$regex': search, '$options': 'i'}},
        ]
    docs = await db.dewi_rnd_tech_packs.find(q, {'_id': 0}).sort('created_at', -1).to_list(200)
    return [serialize(d) for d in docs]


@router.post('/tech-packs')
async def create_tech_pack(body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    norm = await _normalize_techpack_payload(db, body)
    doc = {
        'id':           sid(),
        'style_id':     body.get('style_id', ''),
        'style_code':   body.get('style_code', ''),
        'style_name':   body.get('style_name', ''),
        'version':      body.get('version', 'v1'),
        'doc_url':      body.get('doc_url', None),
        'doc_type':     body.get('doc_type', 'pdf'),
        'title':        body.get('title', ''),
        'description':  body.get('description', ''),
        'bom_items':    norm.get('bom_items', []),
        'bom_unlinked_count': norm.get('bom_unlinked_count', 0),
        'fabrics':            norm.get('fabrics', body.get('fabrics', [])),
        'fabric_consumption': norm.get('fabric_consumption', body.get('fabric_consumption', [])),
        'fabric_consumption_off_list': norm.get('fabric_consumption_off_list', 0),
        'colorways':          norm.get('colorways', []),          # F3/C4: colorway resmi per gaya
        'construction_points': body.get('construction_points', []), # (b) per-poin terstruktur
        'construction_notes': body.get('construction_notes', ''),
        'stitch_type':        body.get('stitch_type', ''),
        'seam_allowance_mm':  body.get('seam_allowance_mm', 10),
        'size_grading_notes': body.get('size_grading_notes', ''),
        # F2: base_size & size_range mengikuti size_list style (bukan teks bebas)
        'base_size':          norm.get('base_size', body.get('base_size', 'M')),
        'size_range':         norm.get('size_range', body.get('size_range', 'S-XL')),
        'style_size_list':    norm.get('style_size_list', []),
        # F3/C3: [{col_id,label}] — col_id stabil supaya ganti nama tidak menghilangkan nilai
        'size_columns':       norm.get('size_columns', []),
        'fit_categories':     body.get('fit_categories', []),       # #2b: info fit (Standar/Jumbo), tidak ubah SKU
        'measurements':       norm.get('measurements', []),
        'measurements_stats': norm.get('measurements_stats', {}),
        'status':       body.get('status', 'draft'),
        'approved_by':  None,
        'approved_at':  None,
        'is_latest':    True,
        'created_by':      user['id'],
        'created_by_name': user.get('name', ''),
        'created_at':   now_utc(),
        'updated_at':   now_utc(),
    }
    if body.get('style_id'):
        await db.dewi_rnd_tech_packs.update_many(
            {'style_id': body['style_id'], 'is_latest': True},
            {'$set': {'is_latest': False}},
        )
    await db.dewi_rnd_tech_packs.insert_one(doc)
    return serialize(doc)


@router.get('/tech-packs/{tp_id}')
async def get_tech_pack(tp_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    doc = await db.dewi_rnd_tech_packs.find_one({'id': tp_id}, {'_id': 0})
    if not doc:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    return serialize(doc)


@router.put('/tech-packs/{tp_id}')
async def update_tech_pack(tp_id: str, body: dict, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_rnd_tech_packs.find_one({'id': tp_id}, {'_id': 0})
    if not existing:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    upd = {k: v for k, v in body.items() if k not in ('id', '_id', 'created_at', 'created_by')}
    # F3: semua pengencang (col_id stabil, warna, badge tanpa-master) lewat satu pintu.
    upd.update(await _normalize_techpack_payload(db, body, existing))
    upd['updated_at'] = now_utc()
    res = await db.dewi_rnd_tech_packs.update_one({'id': tp_id}, {'$set': upd})
    if res.matched_count == 0:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    doc = await db.dewi_rnd_tech_packs.find_one({'id': tp_id}, {'_id': 0})
    return serialize(doc)


@router.post('/tech-packs/{tp_id}/approve')
async def approve_tech_pack(tp_id: str, user: dict = Depends(require_auth)):
    from routes.shared import assert_can_act
    assert_can_act(user, 'rnd.approve', portal='rnd',
                   legacy_roles=('rnd_staff', 'manager_produksi', 'supervisor_produksi',
                                 'manager', 'owner', 'admin', 'superadmin'),
                   what='menyetujui tech pack')
    db = get_db()
    res = await db.dewi_rnd_tech_packs.update_one(
        {'id': tp_id},
        {'$set': {
            'status':      'approved',
            'approved_by':  user.get('name', ''),
            'approved_at':  now_utc(),
            'updated_at':   now_utc(),
        }},
    )
    if res.matched_count == 0:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    return {'ok': True}


@router.delete('/tech-packs/{tp_id}')
async def delete_tech_pack(tp_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    res = await db.dewi_rnd_tech_packs.delete_one({'id': tp_id})
    if res.deleted_count == 0:
        raise HTTPException(404, 'Tech pack tidak ditemukan')
    return {'ok': True}
