"""core.bom_uom — Konversi satuan untuk BOM, MRP, HPP & pengeluaran material.

LATAR BELAKANG (laporan owner 2026-08-02)
-----------------------------------------
`core/uom.py` sudah menjadi SSOT konversi satuan, tetapi menurut peta dampak
`docs/MAP_UOM_IMPACT.md` domain **BOM/MRP, Finance/HPP, RnD, Produksi, Maklon,
Pengadaan** semuanya berstatus "sudah sadar pack: 0" — artinya rantai
BOM → kebutuhan material → pengeluaran gudang → HPP memakai `qty` MENTAH dengan
satuan bebas (default 'pcs'), padahal:

  * INV-UOM-1: `rahaza_materials.unit_cost` SELALU harga per **satuan dasar**
  * INV-UOM-2: seluruh qty stok/ledger SELALU dalam **satuan dasar**

Akibatnya baris BOM "250 gram" diperlakukan sebagai 250 **kg** (500× lipat), dan
"1 lusin" dihitung 1 **pcs**. Modul ini menutup celah itu tanpa mengubah invarian:
ia hanya MEMBACA, tidak pernah menulis daftar `uoms` material.

URUTAN RESOLUSI FAKTOR (dari paling dipercaya)
----------------------------------------------
  1. `core.uom` — satuan ada di daftar `uoms` material (kemasan resmi)   → 'uom'
  2. Tabel dimensi global (massa/panjang/jumlah/volume/luas)             → 'global'
  3. Kain: silang dimensi meter ⇄ kg lewat `gsm` + `width_cm` material   → 'fabric'
  4. Tidak dikenal → faktor 1 + PERINGATAN eksplisit                     → 'mismatch'

Baris tanpa tautan master (`material_id`/`code` kosong) → faktor 1 + 'unlinked'.
Semua hasil dilaporkan sebagai `uom_status` + `uom_note` supaya UI bisa
menampilkan peringatan, bukan diam-diam salah hitung.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from core import uom as uom_core

# ── Tabel dimensi global: faktor ke satuan acuan tiap dimensi ────────────────
# mass → gram, length → mm, count → pcs, volume → ml, area → cm2
_DIMENSIONS: dict[str, dict[str, float]] = {
    'mass': {
        'mg': 0.001, 'gram': 1.0, 'gr': 1.0, 'g': 1.0, 'ons': 100.0,
        'kg': 1000.0, 'kgs': 1000.0, 'kilo': 1000.0, 'kwintal': 100_000.0,
        'ton': 1_000_000.0, 'lb': 453.59237, 'lbs': 453.59237, 'oz': 28.349523,
    },
    'length': {
        'mm': 1.0, 'cm': 10.0, 'dm': 100.0, 'm': 1000.0, 'meter': 1000.0,
        'metre': 1000.0, 'mtr': 1000.0, 'km': 1_000_000.0,
        'inch': 25.4, 'inci': 25.4, '"': 25.4, 'ft': 304.8, 'feet': 304.8,
        'yard': 914.4, 'yd': 914.4, 'yds': 914.4,
    },
    'count': {
        'pcs': 1.0, 'pc': 1.0, 'piece': 1.0, 'buah': 1.0, 'unit': 1.0,
        'lembar': 1.0, 'sheet': 1.0, 'helai': 1.0, 'batang': 1.0,
        'pasang': 2.0, 'pair': 2.0,
        'lusin': 12.0, 'dozen': 12.0, 'dz': 12.0, 'dus_lusin': 12.0,
        'kodi': 20.0, 'rim': 500.0, 'gross': 144.0, 'grosir': 144.0,
    },
    'volume': {'ml': 1.0, 'cc': 1.0, 'liter': 1000.0, 'ltr': 1000.0, 'l': 1000.0,
               'galon': 3785.41, 'gallon': 3785.41},
    'area': {'cm2': 1.0, 'm2': 10_000.0, 'sqm': 10_000.0, 'inch2': 6.4516},
}

# Satuan yang artinya bergantung material (kemasan) — TIDAK boleh dikonversi
# lewat tabel global; harus lewat `uoms` material atau pack_unit/pack_size.
PACKAGING_UNITS = {'rol', 'roll', 'pak', 'pack', 'bks', 'bungkus', 'ktn', 'karton',
                   'box', 'dus', 'bal', 'ball', 'set', 'ikat', 'gulung', 'sak', 'karung',
                   'lot', 'bundel', 'bundle'}

_ALIAS = {
    'meters': 'm', 'metres': 'm', 'mtrs': 'm', 'yards': 'yard', 'inches': 'inch',
    'kilogram': 'kg', 'kilograms': 'kg', 'grams': 'gram', 'gramme': 'gram',
    'pieces': 'pcs', 'pieces(s)': 'pcs', 'pc(s)': 'pcs', 'ea': 'pcs', 'each': 'pcs',
    'liters': 'liter', 'litres': 'liter',
}


def norm_unit(u: Any) -> str:
    """Normalisasi penulisan satuan (huruf kecil, tanpa spasi, alias disamakan)."""
    s = str(u or '').strip().lower().replace('.', '')
    s = s.replace(' ', '')
    return _ALIAS.get(s, s)


def dimension_of(unit: Any) -> Optional[str]:
    u = norm_unit(unit)
    if u in PACKAGING_UNITS:
        return None
    for dim, table in _DIMENSIONS.items():
        if u in table:
            return dim
    return None


def global_factor(from_unit: Any, to_unit: Any) -> Optional[float]:
    """Faktor konversi antar satuan sedimensi (mis. gram→kg = 0.001). None bila
    beda dimensi / satuan kemasan / tidak dikenal."""
    a, b = norm_unit(from_unit), norm_unit(to_unit)
    if not a or not b:
        return None
    if a == b:
        return 1.0
    dim_a, dim_b = dimension_of(a), dimension_of(b)
    if not dim_a or dim_a != dim_b:
        return None
    table = _DIMENSIONS[dim_a]
    return table[a] / table[b]


def fabric_kg_per_meter(material: dict | None) -> Optional[float]:
    """Berat kain per meter lari dari `gsm` × `width_cm` (g/m² × m ÷ 1000)."""
    m = material or {}
    try:
        gsm = float(m.get('gsm') or m.get('gramasi') or m.get('weight_gsm') or 0)
        width = float(m.get('width_cm') or m.get('lebar_cm') or m.get('width') or 0)
    except (TypeError, ValueError):
        return None
    if gsm <= 0 or width <= 0:
        return None
    return (gsm * (width / 100.0)) / 1000.0


def line_factor(material: dict | None, unit: Any) -> tuple:
    """Faktor baris BOM → satuan dasar material.

    Return (factor, base_unit, status, note).
    status ∈ {'base','uom','global','fabric','mismatch','unlinked'}
    """
    base = uom_core.base_uom_of(material) if material else norm_unit(unit) or 'pcs'
    u = norm_unit(unit) or base
    if not material:
        return 1.0, u, 'unlinked', ('Baris belum tertaut master material — satuan & '
                                    'konversi tidak bisa diverifikasi.')
    if u == norm_unit(base):
        return 1.0, base, 'base', ''

    # 1) kemasan resmi material (uoms / pack_unit)
    row = uom_core.find_uom(material, u)
    if row:
        return float(row['factor']), base, 'uom', ''

    # 2) tabel dimensi global
    gf = global_factor(u, base)
    if gf:
        return gf, base, 'global', f"Dikonversi otomatis: 1 {u} = {gf:g} {base}."

    # 3) kain: meter ⇄ kg lewat gsm & lebar
    kg_per_m = fabric_kg_per_meter(material)
    if kg_per_m:
        to_m = global_factor(u, 'm')
        if to_m and norm_unit(base) in ('kg', 'gram', 'gr', 'g'):
            f = to_m * kg_per_m                                # → kg
            if norm_unit(base) != 'kg':
                f = f * (global_factor('kg', base) or 1.0)
            return f, base, 'fabric', (f"Konversi kain via gramasi & lebar: "
                                       f"1 m = {kg_per_m:g} kg.")
        to_kg = global_factor(u, 'kg')
        if to_kg and norm_unit(base) in ('m', 'meter', 'yard', 'cm'):
            meters = to_kg / kg_per_m
            f = meters * (global_factor('m', base) or 1.0)
            return f, base, 'fabric', (f"Konversi kain via gramasi & lebar: "
                                       f"1 kg = {1 / kg_per_m:g} m.")

    return 1.0, base, 'mismatch', (
        f"Satuan '{u}' tidak bisa dikonversi ke satuan dasar '{base}'. "
        f"Tambahkan satuan itu pada master material (Satuan & Kemasan), atau untuk kain "
        f"lengkapi gramasi (gsm) & lebar (cm). Sementara dihitung 1:1.")


# ── Indeks master material (satu query untuk semua baris) ────────────────────
def factor_to_base(material: dict | None, unit: Any) -> tuple:
    """Faktor `unit` → satuan dasar dengan cakupan LEBAR. Return (factor, source).

    Cakupan = kemasan resmi material (`uoms`) + satuan sedimensi global +
    kain m⇄kg via gramasi & lebar — PERSIS sama dengan daftar yang ditawarkan
    `allowed_units()` ke dropdown UI. Melempar `uom_core.UomError` bila satuan
    tetap tidak bisa dikonversi, supaya pemanggil (titik masuk stok) menolak
    dengan pesan jelas, bukan diam-diam salah hitung.

    2026-08-05 — dibuat saat memasang pemilih satuan di 6 titik masuk stok
    (ROADMAP P1): sebelumnya tiap titik memakai `core.uom.factor_of` yang HANYA
    tahu kemasan material, sehingga satuan seperti "gram" atau "yard" ditolak
    walau BOM/Costing sudah lama bisa mengonversinya.
    """
    f, _base, st, note = line_factor(material, unit)
    if st in ('base', 'uom', 'global', 'fabric'):
        return float(f), st
    raise uom_core.UomError(
        note or f"Satuan '{norm_unit(unit)}' tidak bisa dikonversi ke satuan dasar.")


# ── Indeks master material (satu query untuk semua baris) ────────────────────
async def material_index(db, materials: Iterable[dict]) -> dict:
    """Ambil master material untuk sekumpulan baris BOM sekali jalan.

    Return dict berisi dua peta: {'by_id': {...}, 'by_code': {...}}.
    """
    ids = {m.get('material_id') for m in materials if m.get('material_id')}
    codes = {str(m.get('code') or '').strip().upper() for m in materials if m.get('code')}
    by_id, by_code = {}, {}
    if ids:
        async for d in db.rahaza_materials.find({'id': {'$in': list(ids)}}, {'_id': 0}):
            by_id[d['id']] = d
    if codes:
        async for d in db.rahaza_materials.find({'code': {'$in': list(codes)}}, {'_id': 0}):
            by_code[str(d.get('code') or '').upper()] = d
    return {'by_id': by_id, 'by_code': by_code}


def find_material(index: dict, line: dict) -> Optional[dict]:
    if not index:
        return None
    mid = line.get('material_id')
    if mid and mid in index.get('by_id', {}):
        return index['by_id'][mid]
    code = str(line.get('code') or '').strip().upper()
    if code and code in index.get('by_code', {}):
        return index['by_code'][code]
    return None


def annotate_line(line: dict, material: Optional[dict]) -> dict:
    """Tambahkan qty_base/unit_base/uom_* pada satu baris BOM (tidak merusak field lain)."""
    try:
        qty = float(line.get('qty') or 0)
    except (TypeError, ValueError):
        qty = 0.0
    factor, base, status, note = line_factor(material, line.get('unit'))
    out = dict(line)
    out['unit'] = norm_unit(line.get('unit')) or base
    out['unit_base'] = base
    out['uom_factor'] = round(factor, 8)
    out['qty_base'] = round(qty * factor, 6)
    out['uom_status'] = status
    out['uom_note'] = note
    if material:
        out.setdefault('material_id', material.get('id'))
        if not out.get('code'):
            out['code'] = str(material.get('code') or '').upper()
        out['unit_cost_base'] = float(material.get('unit_cost') or 0)
    return out


async def annotate_materials(db, materials: Iterable[dict]) -> tuple:
    """Anotasi seluruh baris BOM + kumpulkan peringatan yang perlu ditindak."""
    rows = list(materials or [])
    if not rows:
        return [], []
    index = await material_index(db, rows)
    out, warnings = [], []
    for line in rows:
        mat = find_material(index, line)
        ann = annotate_line(line, mat)
        if ann['uom_status'] in ('mismatch', 'unlinked'):
            warnings.append(f"{ann.get('name') or ann.get('code') or '(tanpa nama)'}: {ann['uom_note']}")
        out.append(ann)
    return out, warnings


async def ensure_uom(db, bom_or_materials) -> tuple:
    """Baca materials sebuah BOM dan PASTIKAN qty_base/unit_base terisi.

    Dipakai semua konsumen hilir (MRP, MI gudang, Surat Jalan, HPP, PDF) supaya
    BOM lama yang belum punya `qty_base` pun tetap dihitung benar saat runtime.
    Return (materials, warnings).
    """
    from routes.rahaza_bom import get_bom_materials  # impor lokal: hindari siklus
    if isinstance(bom_or_materials, dict):
        mats = get_bom_materials(bom_or_materials)
    else:
        mats = list(bom_or_materials or [])
    if not mats:
        return [], []
    need = [m for m in mats if m.get('qty_base') in (None, '') or not m.get('unit_base')]
    if not need:
        return mats, [f"{m.get('name')}: {m.get('uom_note')}" for m in mats
                      if m.get('uom_status') in ('mismatch', 'unlinked') and m.get('uom_note')]
    return await annotate_materials(db, mats)


def qty_base_of(line: dict) -> float:
    """Ambil qty satuan dasar dari sebuah baris (fallback qty mentah)."""
    v = line.get('qty_base')
    if v in (None, ''):
        v = line.get('qty') or 0
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def base_unit_of(line: dict) -> str:
    return norm_unit(line.get('unit_base') or line.get('unit') or 'pcs')


def allowed_units(material: dict | None) -> list:
    """Daftar satuan yang boleh dipakai baris BOM untuk material ini (untuk dropdown).

    Isi: satuan dasar + kemasan resmi + satuan sedimensi dari tabel global +
    (khusus kain ber-gsm/lebar) satuan silang meter ⇄ kg.
    """
    base = uom_core.base_uom_of(material)
    rows = []
    seen = set()

    def add(code, label, factor, source):
        c = norm_unit(code)
        if not c or c in seen:
            return
        seen.add(c)
        rows.append({'unit': c, 'label': label, 'factor_to_base': round(float(factor), 8),
                     'source': source})

    add(base, f"{base} (satuan dasar)", 1.0, 'base')
    for r in uom_core.resolve_uoms(material):
        if not r.get('is_base'):
            add(r['code'], f"{r['code']} = {r['factor']:g} {base}", r['factor'], 'uom')
    dim = dimension_of(base)
    if dim:
        for code in _DIMENSIONS[dim]:
            f = global_factor(code, base)
            if f:
                add(code, f"{code} = {f:g} {base}", f, 'global')
    kg_per_m = fabric_kg_per_meter(material)
    if kg_per_m:
        cross = ['m', 'yard', 'cm'] if norm_unit(base) in ('kg', 'gram') else ['kg', 'gram']
        for code in cross:
            f, _b, st, _n = line_factor(material, code)
            if st == 'fabric':
                add(code, f"{code} ≈ {f:g} {base} (via gramasi & lebar)", f, 'fabric')
    return rows
