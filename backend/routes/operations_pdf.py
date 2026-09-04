# ruff: noqa: F401
"""
operations_pdf.py — PDF Export Endpoint
Endpoint: /api/export-pdf

Refactored: Session #11.19 Phase 3.2.6 (split from operations_export.py 1277 LOC)
Split: Excel export → operations_excel.py, PDF configs → operations_pdf_configs.py, PDF helpers → operations_pdf_helpers.py
"""
import uuid
from pathlib import Path
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from database import get_db
from auth import require_auth, log_activity, serialize_doc
from routes.shared import _fmt_date, _fmt_money
from routes.operations_pdf_helpers import (
    _pdf_styles, _pdf_table_style, _pdf_total_row_style, _build_pdf,
    _pdf_header, _pdf_footer, _safe_str, enrich_with_product_photos,
    _get_pdf_config, tpl_table_parts,
    _pdf_header_branded, _pdf_signature_block, _pdf_footer_branded,
    _pdf_data_table, _pdf_info_pairs,
    CONTENT_W_PORTRAIT, CONTENT_W_LANDSCAPE, content_width,
)
from utils.pdf_common import get_company_profile, get_doc_settings
from routes.rahaza_bom import get_bom_materials, _is_kglike
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar
import logging
from datetime import datetime, timezone
from io import BytesIO
from utils.waktu import now_wib

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operations-pdf"])


# Label kategori material (general) — sumber: master rahaza_materials.type.
# Bukan hardcode "Kain/Benang"; mengikuti master data bahan (bisa berkembang).
_MATERIAL_TYPE_LABEL = {
    'yarn': 'Benang',
    'fabric': 'Kain',
    'accessory': 'Aksesoris',
    'fg': 'Barang Jadi',
    'packaging': 'Packaging',
}


def _fmt_qty_id(v):
    """Format kuantitas gaya Indonesia (ribuan '.', desimal ','), buang nol berlebih."""
    try:
        f = float(v)
    except (ValueError, TypeError):
        return str(v if v is not None else 0)
    if f == int(f):
        return f"{int(f):,}".replace(',', '.')
    s = f"{f:,.3f}".replace(',', '§').replace('.', ',').replace('§', '.')
    return s.rstrip('0').rstrip(',')


async def _aggregate_bom_for_po(db, po_id: str):
    """Read-only: agregasi kebutuhan material dari BOM aktif (rahaza_boms) per item
    PO × qty. Mendukung BOM per-varian (model+size+warna) — prefer BOM warna spesifik,
    fallback ke BOM umum (color kosong). Kategori diambil dari entry BOM (`category_name`)
    bila ada, else diresolusi dari master `rahaza_materials`.
    Return list[{code, name, category, unit, qty}] terurut kategori→nama.
    Khusus tampilan dokumen SPP Internal — tidak menulis master apa pun."""
    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(1000)
    need = {}
    for it in po_items:
        model_id = it.get('model_id')
        size_id = it.get('size_id')
        color = (it.get('color') or '').strip()
        qty = int(it.get('qty') or 0)
        if not model_id or not size_id or qty <= 0:
            continue
        bom = None
        if color:
            bom = await db.rahaza_boms.find_one(
                {'model_id': model_id, 'size_id': size_id, 'color': color,
                 'is_active': True, 'active': {'$ne': False}}, {'_id': 0})
        if not bom:  # fallback BOM umum (warna kosong/tak ada)
            bom = await db.rahaza_boms.find_one(
                {'model_id': model_id, 'size_id': size_id,
                 'color': {'$in': ['', None]}, 'is_active': True, 'active': {'$ne': False}},
                {'_id': 0})
        if not bom:  # fallback terakhir: tanpa filter color (BOM lama)
            bom = await db.rahaza_boms.find_one(
                {'model_id': model_id, 'size_id': size_id, 'is_active': True,
                 'active': {'$ne': False}}, {'_id': 0})
        if not bom:
            continue
        # BOM generik (Phase 7A Fase 1): satu daftar materials[]. Kain/benang
        # (kg-like) & aksesoris digabung; kategori diambil dari entry/master.
        # 2026-08-02 · SATUAN: qty dikonversi ke SATUAN DASAR material dulu supaya
        # dokumen kebutuhan material tidak mencampur meter/gram dengan kg.
        bom_mats, _uw = await bom_uom.ensure_uom(db, bom)
        for m in bom_mats:
            code = (m.get('code') or '').strip().upper()
            if not code:
                continue
            base_unit = bom_uom.base_unit_of(m)
            origin = 'yarn' if _is_kglike({**m, 'unit': base_unit}) else 'accessory'
            e = need.setdefault(code, {'code': code, 'name': m.get('name') or code,
                                       '_origin': origin, 'category_name': m.get('category_name') or '',
                                       'unit': (base_unit or ('kg' if origin == 'yarn' else 'pcs')), 'qty': 0.0})
            e['qty'] += bom_uom.qty_base_of(m) * qty
    if not need:
        return []
    # Resolusi kategori & unit & nama dari master rahaza_materials (batch, by code)
    codes = list(need.keys())
    masters = {}
    async for m in db.rahaza_materials.find({'code': {'$in': codes}}, {'_id': 0}):
        masters[(m.get('code') or '').strip().upper()] = m
    for code, e in need.items():
        m = masters.get(code)
        # Prioritas kategori: (1) category_name dari entry BOM, (2) master.category_name,
        # (3) label dari master.type, (4) fallback origin.
        cat = e.get('category_name') or ''
        if not cat and m:
            cat = m.get('category_name') or ''
            if not cat and m.get('type'):
                cat = _MATERIAL_TYPE_LABEL.get(m['type'], str(m['type']).title())
        if not cat:
            cat = 'Aksesoris' if e['_origin'] == 'accessory' else 'Benang'
        e['category'] = cat
        if m and m.get('unit'):
            e['unit'] = m['unit']
        if m and m.get('name'):
            e['name'] = m['name']
        e.pop('_origin', None)
        e.pop('category_name', None)
    return sorted(need.values(), key=lambda x: (x['category'].lower(), x['name'].lower()))


MATERIAL_TYPE_LABEL = _MATERIAL_TYPE_LABEL  # alias publik (dipakai modul lain bila perlu)


# ══════════════════════════════════════════════════════════════════════════════
# AKSESORIS PADA SURAT JALAN MATERIAL (perbaikan 2026-08-01)
# Laporan owner: "surat jalan pengiriman material ke CMT tidak ada kolom
# aksesoris (aksesoris tidak ter-export)". Akar masalah: generator SJ hanya
# membaca `vendor_shipment_items` (kain/produk), sementara aksesoris disimpan di
# DUA tempat lain: `accessory_shipment_items` (aksesoris yang benar-benar
# dikirim, termasuk lewat child shipment ADDITIONAL/REPLACEMENT) dan
# `po_accessories` (kebutuhan aksesoris pada PO — inilah yang tampil di UI
# "Aksesoris terkait PO"). Keduanya kini digabung ke PDF.
# ══════════════════════════════════════════════════════════════════════════════
async def _collect_shipment_accessories(db, ship: dict, items: list) -> list:
    """Kumpulkan baris aksesoris untuk Surat Jalan sebuah vendor shipment."""
    sid = ship.get('id')
    child_ids = [c['id'] for c in await db.vendor_shipments
                 .find({'parent_shipment_id': sid}, {'_id': 0, 'id': 1}).to_list(200)]
    ship_ids = [x for x in ([sid] + child_ids) if x]

    sent = await db.accessory_shipment_items.find(
        {'shipment_id': {'$in': ship_ids}}, {'_id': 0}).to_list(1000) if ship_ids else []

    po_ids = {ship.get('po_id')} | {i.get('po_id') for i in (items or [])}
    po_ids = {p for p in po_ids if p}
    po_needs = await db.po_accessories.find(
        {'po_id': {'$in': list(po_ids)}}, {'_id': 0}).to_list(1000) if po_ids else []

    # nomor PO untuk baris po_accessories (koleksi itu hanya menyimpan po_id)
    po_num_map = {}
    for i in (items or []):
        if i.get('po_id') and i.get('po_number'):
            po_num_map[i['po_id']] = i['po_number']
    if ship.get('po_id') and ship.get('po_number'):
        po_num_map.setdefault(ship['po_id'], ship['po_number'])
    missing_nums = [p for p in po_ids if p not in po_num_map]
    if missing_nums:
        for po in await db.production_pos.find(
                {'id': {'$in': missing_nums}}, {'_id': 0, 'id': 1, 'po_number': 1}).to_list(200):
            po_num_map[po['id']] = po.get('po_number', '')

    def _key(a):
        return ((a.get('accessory_code') or a.get('accessory_name') or '').strip().lower(),
                (a.get('po_id') or '').strip())

    rows, seen = [], set()
    for a in sent:
        seen.add(_key(a))
        rows.append({
            'code': a.get('accessory_code', ''),
            'name': a.get('accessory_name', ''),
            'po_number': a.get('po_number') or po_num_map.get(a.get('po_id'), ''),
            'qty': a.get('qty_sent', 0) or 0,
            'unit': a.get('unit', 'pcs'),
            'source': 'Dikirim',
            'notes': a.get('notes', '') or a.get('shipment_type', ''),
        })
    for a in po_needs:
        if _key(a) in seen:
            continue
        rows.append({
            'code': a.get('accessory_code', ''),
            'name': a.get('accessory_name', ''),
            'po_number': po_num_map.get(a.get('po_id'), ''),
            'qty': a.get('qty_needed', 0) or 0,
            'unit': a.get('unit', 'pcs'),
            'source': 'Kebutuhan PO',
            'notes': a.get('notes', ''),
        })
    rows.sort(key=lambda r: (r['source'] != 'Dikirim', (r['name'] or '').lower()))
    return rows


def _append_accessory_table(elements, acc_rows, styles):
    """Tambahkan blok tabel AKSESORIS ke dokumen (dipakai Surat Jalan material)."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    elements.append(Spacer(1, 5 * mm))
    if not acc_rows:
        elements.append(Paragraph(
            "<b>AKSESORIS / KOMPONEN PENDUKUNG:</b> <i>tidak ada aksesoris pada pengiriman ini.</i>",
            styles['Normal']))
        return elements
    elements.append(Paragraph("<b>AKSESORIS / KOMPONEN PENDUKUNG</b>", styles['Heading4']))
    headers = ['No', 'Kode', 'Aksesoris', 'PO', 'Qty', 'Satuan', 'Sumber', 'Catatan']
    data = [[idx,
             _safe_str(a['code'], 20),
             _safe_str(a['name'], 50),
             _safe_str(a['po_number'], 20),
             _fmt_qty_id(a['qty']),
             _safe_str(a['unit'], 10),
             a['source'],
             _safe_str(a['notes'], 40)]
            for idx, a in enumerate(acc_rows, 1)]
    total = sum(float(a['qty'] or 0) for a in acc_rows)
    data.append(['', '', 'TOTAL AKSESORIS', '', _fmt_qty_id(total), '', '', ''])
    t = _pdf_data_table(headers, data,
                        weights=[0.4, 1.2, 2.4, 1.2, 0.8, 0.7, 1.0, 1.6],
                        right_cols=[4], total_row=True)
    elements.append(t)
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "<i>Sumber baris: <b>Dikirim</b> = aksesoris yang menyertai pengiriman ini "
        "(termasuk pengiriman tambahan/pengganti). <b>Kebutuhan PO</b> = kebutuhan "
        "aksesoris pada PO terkait yang belum tercatat sebagai kiriman terpisah.</i>",
        styles['Normal']))
    return elements


async def _collect_maklon_bom_bulk(db, ship: dict, items: list) -> tuple:
    """Baris kain/benang (bulk) dari BOM maklon per-PO untuk blok REFERENSI di SJ.

    Aksesoris tidak diambil di sini karena sudah punya tabelnya sendiri (lewat
    `po_accessories`, yang kini juga diisi otomatis dari BOM template maklon).
    """
    po_ids = {ship.get('po_id')} | {i.get('po_id') for i in (items or [])}
    po_ids = {p for p in po_ids if p}
    if not po_ids:
        return [], []
    boms = await db.dewi_maklon_bom.find({'po_id': {'$in': list(po_ids)}}, {'_id': 0}).to_list(50)
    rows, templates = [], []
    for b in boms:
        for t in (b.get('source_templates') or []):
            lbl = f"v{t.get('version')}" + (f" ({t.get('label')})" if t.get('label') else '')
            if lbl not in templates:
                templates.append(lbl)
        for m in (b.get('materials') or []):
            is_bulk = (m.get('line_type') == 'bulk') or (
                m.get('line_type') is None and (m.get('material_category') == 'fabric'))
            if not is_bulk or float(m.get('qty_estimated') or m.get('qty_total_est') or 0) <= 0:
                continue
            rows.append({
                'name': m.get('material_name', ''),
                'category': m.get('material_category', ''),
                'per_pcs': m.get('qty_per_pcs', 0),
                'qty': m.get('qty_estimated') or m.get('qty_total_est') or 0,
                'unit': m.get('unit', ''),
                'owner': 'Klien' if (m.get('ownership') or 'client_provided') == 'client_provided' else 'CV. DA',
                'po_number': b.get('po_number', ''),
            })
    rows.sort(key=lambda r: (r['name'] or '').lower())
    return rows, templates


def _append_maklon_bom_table(elements, rows, templates, styles):
    """Blok REFERENSI kebutuhan kain/benang per BOM maklon di Surat Jalan."""
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, Spacer
    if not rows:
        return elements
    elements.append(Spacer(1, 5 * mm))
    elements.append(Paragraph("<b>KEBUTUHAN MATERIAL PER BOM (REFERENSI)</b>", styles['Heading4']))
    headers = ['No', 'Material', 'Kategori', 'Qty/pcs', 'Qty Kebutuhan', 'Satuan', 'Dipasok', 'PO']
    data = [[i,
             _safe_str(r['name'], 45),
             _safe_str(r['category'], 14),
             _fmt_qty_id(r['per_pcs']),
             _fmt_qty_id(r['qty']),
             _safe_str(r['unit'], 10),
             r['owner'],
             _safe_str(r['po_number'], 18)]
            for i, r in enumerate(rows, 1)]
    elements.append(_pdf_data_table(headers, data,
                                    weights=[0.4, 2.6, 1.1, 0.9, 1.2, 0.7, 0.9, 1.2],
                                    right_cols=[3, 4]))
    elements.append(Spacer(1, 2 * mm))
    elements.append(Paragraph(
        "<i>Angka di atas adalah <b>kebutuhan menurut BOM</b>"
        + (f" (template {', '.join(templates)})" if templates else "")
        + ", bukan daftar barang yang dikirim pada surat jalan ini. Dipakai CMT untuk "
        "memverifikasi kelengkapan material.</i>", styles['Normal']))
    return elements


# ══════════════════════════════════════════════════════════════════════════════
# PANDUAN PRODUK / PRODUKSI (SOP) — PDF baru (permintaan owner 2026-08-01)
# Tombolnya diletakkan bersebelahan dengan "Cetak Surat Jalan (PDF)" di detail
# pengiriman CMT supaya user tidak perlu berpindah-pindah modul.
# Sumber SOP: dewi_maklon_buyer_catalog (Maklon) & rahaza_models (Internal) —
# sama dengan endpoint production-guide di portal vendor, jadi satu kebenaran.
# ══════════════════════════════════════════════════════════════════════════════
_UPLOAD_ROOT = Path('/app/uploads')


def _resolve_local_upload(url_or_path: str):
    """Ubah URL/berkas simpanan jadi path lokal yang aman (None bila bukan lokal)."""
    s = str(url_or_path or '').strip()
    if not s or s.startswith(('http://', 'https://', 'data:')):
        return None
    for pref in ('/api/uploads/', 'api/uploads/', '/uploads/', 'uploads/'):
        if s.startswith(pref):
            s = s[len(pref):]
            break
    s = s.lstrip('/')
    try:
        p = (_UPLOAD_ROOT / s).resolve()
        root = _UPLOAD_ROOT.resolve()
        if root != p and root not in p.parents:
            return None            # cegah keluar dari folder unggahan
        return p if p.is_file() else None
    except Exception:  # noqa: BLE001
        return None


def _pdf_image(url_or_path: str, max_w_pt: float = 170, max_h_pt: float = 130):
    """Flowable gambar berskala proporsional; None bila berkas tak bisa dipakai."""
    path = _resolve_local_upload(url_or_path)
    if not path:
        return None
    try:
        from reportlab.platypus import Image as RLImage
        from PIL import Image as PILImage
        with PILImage.open(path) as im:
            w, h = im.size
        if not w or not h:
            return None
        ratio = min(max_w_pt / float(w), max_h_pt / float(h), 1.0)
        return RLImage(str(path), width=w * ratio, height=h * ratio)
    except Exception:  # noqa: BLE001
        logger.debug("gagal memuat gambar panduan: %s", url_or_path, exc_info=True)
        return None


def _guide_from_catalog(cat: dict) -> dict:
    return {
        'source_label': 'Katalog Buyer (Maklon)',
        'code': cat.get('artikel_code', ''),
        'name': cat.get('product_name', ''),
        'description': cat.get('description', ''),
        'sop_steps': list(cat.get('sop_steps') or []),
        'reference_videos': list(cat.get('reference_videos') or []),
        'reference_images': ([{'url': cat.get('hero_image_url'), 'caption': 'Foto utama'}]
                             if cat.get('hero_image_url') else [])
                            + list(cat.get('reference_images') or []),
        'sop_updated_at': cat.get('sop_updated_at'),
        'sop_updated_by': cat.get('sop_updated_by', ''),
    }


def _guide_from_model(mdl: dict) -> dict:
    return {
        'source_label': 'Master Produk (Internal)',
        'code': mdl.get('code', ''),
        'name': mdl.get('name', ''),
        'description': mdl.get('description', ''),
        'sop_steps': list(mdl.get('sop_steps') or []),
        'reference_videos': list(mdl.get('reference_videos') or []),
        'reference_images': list(mdl.get('reference_images') or [])
                            + [{'url': p, 'caption': ''} for p in (mdl.get('image_paths') or [])],
        'sop_updated_at': mdl.get('sop_updated_at'),
        'sop_updated_by': mdl.get('sop_updated_by', ''),
    }


async def _guides_from_article_refs(db, catalog_ids, model_ids) -> list:
    guides = []
    for cid in [c for c in dict.fromkeys(catalog_ids) if c]:
        cat = await db.dewi_maklon_buyer_catalog.find_one({'id': cid}, {'_id': 0})
        if cat:
            guides.append(_guide_from_catalog(cat))
    for mid in [m for m in dict.fromkeys(model_ids) if m]:
        mdl = await db.rahaza_models.find_one({'id': mid}, {'_id': 0})
        if mdl:
            guides.append(_guide_from_model(mdl))
    return guides


async def _resolve_production_guide(db, ref_id: str) -> dict:
    """Resolusi Panduan Produk dari id apa pun: vendor shipment / job / artikel.

    Dibuat fleksibel supaya SATU tombol bisa dipakai di banyak layar tanpa
    menambah navigasi: tombol di detail pengiriman CMT mengirim id shipment,
    portal vendor bisa mengirim id job, master produk mengirim id artikel.
    """
    if not ref_id:
        raise HTTPException(400, 'id required')

    # 1) vendor shipment (kasus utama: tombol di detail pengiriman material CMT)
    ship = await db.vendor_shipments.find_one({'id': ref_id}, {'_id': 0})
    if ship:
        items = await db.vendor_shipment_items.find({'shipment_id': ref_id}, {'_id': 0}).to_list(500)
        poi_ids = [i.get('po_item_id') or i.get('source_po_item_id') for i in items]
        poi_ids = [p for p in poi_ids if p]
        po_items = await db.po_items.find({'id': {'$in': poi_ids}}, {'_id': 0}).to_list(500) if poi_ids else []
        if not po_items:
            po_ids = [p for p in ({ship.get('po_id')} | {i.get('po_id') for i in items}) if p]
            po_items = await db.po_items.find({'po_id': {'$in': po_ids}}, {'_id': 0}).to_list(500) if po_ids else []
        guides = await _guides_from_article_refs(
            db, [p.get('catalog_item_id') for p in po_items], [p.get('model_id') for p in po_items])
        return {
            'guides': guides,
            'title': 'PANDUAN PRODUK & PROSES PRODUKSI',
            'info_pairs': [
                ('No Surat Jalan', ship.get('delivery_note_number') or ship.get('shipment_number', '')),
                ('No Shipment', ship.get('shipment_number', '')),
                ('Vendor / CMT', ship.get('vendor_name', '')),
                ('No PO', ship.get('po_number', '-')),
                ('Jenis Bisnis', 'Maklon (CMT)' if ship.get('business_type') == 'maklon' else 'Internal'),
                ('Tanggal Kirim', _fmt_date(ship.get('shipment_date'))),
            ],
            'filename': f"Panduan-Produk-{ship.get('shipment_number', ref_id)}.pdf",
            'context_kind': 'vendor_shipment',
        }

    # 2) production job (portal vendor / produksi)
    job = await db.production_jobs.find_one({'id': ref_id}, {'_id': 0})
    if job:
        job_items = await db.production_job_items.find({'job_id': ref_id}, {'_id': 0}).to_list(500)
        cat_ids = [j.get('catalog_item_id') for j in job_items]
        mdl_ids = [j.get('model_id') for j in job_items]
        if not any(cat_ids) and not any(mdl_ids):
            poi_ids = [j.get('po_item_id') for j in job_items if j.get('po_item_id')]
            po_items = await db.po_items.find({'id': {'$in': poi_ids}}, {'_id': 0}).to_list(500) if poi_ids else []
            if not po_items and job.get('po_id'):
                po_items = await db.po_items.find({'po_id': job['po_id']}, {'_id': 0}).to_list(500)
            cat_ids = [p.get('catalog_item_id') for p in po_items]
            mdl_ids = [p.get('model_id') for p in po_items]
        guides = await _guides_from_article_refs(db, cat_ids, mdl_ids)
        return {
            'guides': guides,
            'title': 'PANDUAN PRODUK & PROSES PRODUKSI',
            'info_pairs': [
                ('No Pekerjaan', job.get('job_number', '')),
                ('Vendor / CMT', job.get('vendor_name', '-')),
                ('No PO', job.get('po_number', '-')),
                ('Jenis Bisnis', 'Maklon (CMT)' if job.get('business_type') == 'maklon' else 'Internal'),
            ],
            'filename': f"Panduan-Produk-{job.get('job_number', ref_id)}.pdf",
            'context_kind': 'production_job',
        }

    # 3) langsung artikel (katalog buyer / master produk)
    cat = await db.dewi_maklon_buyer_catalog.find_one({'id': ref_id}, {'_id': 0})
    if cat:
        g = _guide_from_catalog(cat)
        return {'guides': [g], 'title': 'PANDUAN PRODUK & PROSES PRODUKSI',
                'info_pairs': [('Artikel', g['code']), ('Nama Produk', g['name'])],
                'filename': f"Panduan-Produk-{g['code'] or ref_id}.pdf",
                'context_kind': 'buyer_catalog'}
    mdl = await db.rahaza_models.find_one({'id': ref_id}, {'_id': 0})
    if mdl:
        g = _guide_from_model(mdl)
        return {'guides': [g], 'title': 'PANDUAN PRODUK & PROSES PRODUKSI',
                'info_pairs': [('Kode Produk', g['code']), ('Nama Produk', g['name'])],
                'filename': f"Panduan-Produk-{g['code'] or ref_id}.pdf",
                'context_kind': 'rahaza_model'}

    raise HTTPException(404, 'Data acuan panduan tidak ditemukan (shipment/pekerjaan/artikel)')


@router.get("/export-pdf")
async def export_pdf(request: Request):
    user = await require_auth(request)
    db = get_db()
    sp = request.query_params
    pdf_type = sp.get('type', '')
    config_id = sp.get('config_id')
    try:
        from reportlab.lib.units import mm
        from reportlab.lib import colors
        from reportlab.platypus import Table, TableStyle, Paragraph, Spacer
        buf = BytesIO()
        styles = _pdf_styles()
        settings = await db.company_settings.find_one({'type': 'general'}) or {}
        company_name = settings.get('company_name', 'Garment ERP')
        settings.get('pdf_header_line1', '')
        settings.get('pdf_header_line2', '')
        settings.get('pdf_footer_text', '')

        # Unified branding profile (dipakai oleh generator Surat Jalan shipment).
        profile = await get_company_profile(db)
        _preview = sp.get('preview') in ('1', 'true', 'yes')

        def _pdf_response(buffer, filename):
            disposition = 'inline' if _preview else 'attachment'
            return StreamingResponse(
                buffer, media_type="application/pdf",
                headers={"Content-Disposition": f'{disposition}; filename="{filename}"'})

        # Get optional custom column config.
        # W2 — `?cols=` = pilihan kolom SEKALI CETAK dari layar (menang atas config_id
        # dan template), supaya pemakai bisa memilih kolom (mis. Serial No) tanpa
        # harus mengubah setelan global lebih dulu.
        config = await _get_pdf_config(db, pdf_type, config_id, cols=sp.get('cols'))

        # ──── PRODUCTION PO (SPP - Surat Perintah Produksi) ────
        if pdf_type == 'production-po':
            po_id = sp.get('id')
            if not po_id:
                raise HTTPException(400, 'id required')
            po = await db.production_pos.find_one({'id': po_id}, {'_id': 0})
            if not po:
                raise HTTPException(404, 'PO not found')
            items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(500)
            if not items:
                raise HTTPException(404, 'No items in this PO')
            accessories = await db.po_accessories.find({'po_id': po_id}, {'_id': 0}).to_list(500)
            # production_pos berisi Internal & Maklon → bedakan via business_type.
            is_internal = (po.get('business_type') != 'maklon')
            scope_label = 'INTERNAL' if is_internal else 'MAKLON'
            doc_settings = await get_doc_settings(db, 'production-po')
            elements = []
            _pdf_header_branded(
                elements, profile, doc_settings,
                f'SURAT PERINTAH PRODUKSI (SPP) — {scope_label}',
                info_pairs=[
                    ('No PO', po.get('po_number', '')), ('Customer', po.get('customer_name', '')),
                    ('Vendor/CMT', po.get('vendor_name', '')), ('Status', po.get('status', '')),
                    ('Tanggal PO', _fmt_date(po.get('po_date'))), ('Deadline', _fmt_date(po.get('deadline'))),
                    ('Delivery Deadline', _fmt_date(po.get('delivery_deadline'))), ('Tipe', scope_label),
                ], avail=CONTENT_W_LANDSCAPE)
            # Items table (lebar kolom proporsional + kolom angka rata-kanan)
            all_col_keys = ['no', 'serial', 'product', 'sku', 'size', 'color', 'qty', 'price', 'cmt']
            all_headers = ['No', 'Serial No', 'Produk', 'SKU', 'Size', 'Warna', 'Qty', 'Harga', 'CMT']
            weight_map = {'no': 0.5, 'serial': 1.4, 'product': 2.6, 'sku': 1.4, 'size': 0.7,
                          'color': 1.0, 'qty': 0.8, 'price': 1.3, 'cmt': 1.3}
            data_rows = []
            for idx, item in enumerate(items, 1):
                data_rows.append([
                    idx, _safe_str(item.get('serial_number')), _safe_str(item.get('product_name'), 70),
                    _safe_str(item.get('sku')), _safe_str(item.get('size')), _safe_str(item.get('color')),
                    item.get('qty', 0), _fmt_money(item.get('selling_price_snapshot', 0)),
                    _fmt_money(item.get('cmt_price_snapshot', 0))
                ])
            headers, data_rows, active_keys, weights, right_cols, _ds = await tpl_table_parts(
                db, 'production-po', all_col_keys, all_headers, data_rows,
                weight_map=weight_map, numeric_keys=('qty', 'price', 'cmt'), config=config)
            total_qty = sum(i.get('qty', 0) for i in items)
            total_row = [''] * len(headers)
            if 'qty' in active_keys:
                qi = active_keys.index('qty')
                if qi > 0:
                    total_row[qi - 1] = 'TOTAL'
                total_row[qi] = total_qty
            elif total_row:
                total_row[0] = 'TOTAL'
            data_rows.append(total_row)
            t = _pdf_data_table(headers, data_rows, weights=weights, right_cols=right_cols,
                                total_row=True, page='landscape',
                                style=(doc_settings.get('_template') or {}).get('table'))
            elements.append(t)
            # ── BOM section — HANYA untuk SPP Internal (Maklon dikecualikan) ──
            if is_internal:
                bom_rows = await _aggregate_bom_for_po(db, po_id)
                elements.append(Spacer(1, 6*mm))
                elements.append(Paragraph("<b>Kebutuhan Material (BOM)</b>", styles['Heading3']))
                if bom_rows:
                    bom_headers = ['No', 'Kode', 'Nama Material', 'Kategori', 'Qty Kebutuhan', 'Satuan']
                    bom_data = [[i, b['code'], b['name'], b['category'], _fmt_qty_id(b['qty']), b['unit']]
                                for i, b in enumerate(bom_rows, 1)]
                    bt = _pdf_data_table(bom_headers, bom_data,
                                         weights=[0.5, 1.5, 3.0, 1.4, 1.5, 1.0],
                                         right_cols=[4], page='landscape')
                    elements.append(bt)
                else:
                    elements.append(Paragraph(
                        "<i>Belum ada BOM aktif untuk model/size pada PO ini.</i>", styles['Normal']))
            # ── Accessories section (dari po_accessories) ──
            if accessories:
                elements.append(Spacer(1, 6*mm))
                elements.append(Paragraph("<b>Aksesoris Dibutuhkan</b>", styles['Heading3']))
                acc_headers = ['No', 'Aksesoris', 'Kode', 'Qty', 'Satuan', 'Catatan']
                acc_rows = [[idx, acc.get('accessory_name', ''), acc.get('accessory_code', ''),
                             _fmt_qty_id(acc.get('qty_needed', 0)), acc.get('unit', 'pcs'),
                             _safe_str(acc.get('notes', ''), 80)]
                            for idx, acc in enumerate(accessories, 1)]
                at = _pdf_data_table(acc_headers, acc_rows,
                                     weights=[0.5, 2.6, 1.5, 1.0, 1.0, 2.6],
                                     right_cols=[3], page='landscape')
                elements.append(at)
            if po.get('notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Catatan:</b> {_safe_str(po.get('notes', ''), 300)}", styles['Normal']))
            sig_context = {'vendor_name': po.get('vendor_name', ''), 'po_number': po.get('po_number', '')}
            _pdf_signature_block(elements, doc_settings, sig_context)
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements, page='landscape')
            return _pdf_response(buf, f"SPP-{po.get('po_number', 'unknown')}.pdf")

        # ──── VENDOR SHIPMENT (Surat Jalan Material) ────
        elif pdf_type == 'vendor-shipment':
            sid = sp.get('id')
            if not sid:
                raise HTTPException(400, 'id required')
            ship = await db.vendor_shipments.find_one({'id': sid}, {'_id': 0})
            if not ship:
                raise HTTPException(404, 'Shipment not found')
            items = await db.vendor_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(500)
            doc_settings = await get_doc_settings(db, 'vendor-shipment')
            elements = []
            _pdf_header_branded(elements, profile, doc_settings, 'SURAT JALAN — PENGIRIMAN MATERIAL KE VENDOR', info_pairs=[
                ('No Surat Jalan', ship.get('delivery_note_number') or ship.get('shipment_number', '')),
                ('No Shipment', ship.get('shipment_number', '')),
                ('Vendor', ship.get('vendor_name', '')),
                ('No PO', ship.get('po_number', '-')),
                ('Tipe', ship.get('shipment_type', 'NORMAL')),
                ('Tanggal', _fmt_date(ship.get('shipment_date'))),
            ])
            all_col_keys = ['no', 'po', 'serial', 'product', 'sku', 'size', 'color', 'qty_sent']
            all_headers = ['No', 'PO', 'Serial', 'Produk', 'SKU', 'Size', 'Warna', 'Qty Kirim']
            weight_map = {'no': 0.5, 'po': 1.3, 'serial': 1.3, 'product': 2.4, 'sku': 1.4,
                          'size': 0.7, 'color': 1.0, 'qty_sent': 1.0}
            data_rows = []
            for idx, i in enumerate(items, 1):
                data_rows.append([idx, _safe_str(i.get('po_number')), _safe_str(i.get('serial_number')),
                    _safe_str(i.get('product_name'), 60), _safe_str(i.get('sku')),
                    _safe_str(i.get('size')), _safe_str(i.get('color')), i.get('qty_sent', 0)])
            headers, data_rows, active_keys, weights, right_cols, _ds = await tpl_table_parts(
                db, 'vendor-shipment', all_col_keys, all_headers, data_rows,
                weight_map=weight_map, numeric_keys=('qty_sent',), config=config)
            total_row = [''] * len(headers)
            if 'qty_sent' in active_keys:
                qi = active_keys.index('qty_sent')
                if qi > 0:
                    total_row[qi - 1] = 'TOTAL'
                total_row[qi] = sum(i.get('qty_sent', 0) for i in items)
            elif total_row:
                total_row[0] = 'TOTAL'
            data_rows.append(total_row)
            t = _pdf_data_table(headers, data_rows, weights=weights, right_cols=right_cols,
                                total_row=True,
                                style=(doc_settings.get('_template') or {}).get('table'))
            elements.append(t)
            # AKSESORIS — dulu HILANG dari surat jalan (laporan owner 2026-08-01).
            acc_rows = await _collect_shipment_accessories(db, ship, items)
            _append_accessory_table(elements, acc_rows, styles)
            # KEBUTUHAN MATERIAL PER BOM (maklon) — sambungan BOM template → SJ.
            bom_rows, bom_templates = await _collect_maklon_bom_bulk(db, ship, items)
            _append_maklon_bom_table(elements, bom_rows, bom_templates, styles)
            if ship.get('notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Catatan:</b> {_safe_str(ship.get('notes',''), 160)}", styles['Normal']))
            # Signature area (configurable via pdf-doc-settings)
            sig_context = {
                'vendor_name': ship.get('vendor_name', ''),
                'shipment_number': ship.get('shipment_number', ''),
            }
            _pdf_signature_block(elements, doc_settings, sig_context)
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements)
            return _pdf_response(buf, f"SJ-Material-{ship.get('shipment_number','')}.pdf")

        # ──── SURAT JALAN CMT → DA (W5, permintaan pemilik 2026-08-20) ────
        # Sumber = BARIS PENERIMAAN FG yang dipilih di layar "Terima FG dari CMT"
        # (satu penerimaan = satu surat jalan). Kolom hasil QC (Qty Terima/Reject)
        # adalah PILIHAN lewat `?cols=` sehingga dokumen yang sama bisa dicetak
        # "sebelum QC" maupun "setelah QC" — bukan dua jenis dokumen terpisah.
        elif pdf_type == 'cmt-delivery-note':
            rid = sp.get('id')
            if not rid:
                raise HTTPException(400, 'id required')
            receipt = await db.cmt_receipts.find_one({'id': rid}, {'_id': 0})
            if not receipt:
                raise HTTPException(404, 'Penerimaan FG dari CMT tidak ditemukan')
            from core import cmt_delivery_note as cdn
            dn = await cdn.ensure_number(db, receipt, actor=user)
            rows_src = await cdn.build_lines(db, rid)
            doc_settings = await get_doc_settings(db, 'cmt-delivery-note')
            qc_done = str(receipt.get('status') or '').lower() in ('completed_qc', 'approved', 'done')
            elements = []
            _pdf_header_branded(
                elements, profile, doc_settings,
                'SURAT JALAN — PENGIRIMAN BARANG JADI DARI CMT KE DA',
                info_pairs=[
                    ('No Surat Jalan', dn.get('dn_number', '')),
                    ('No Penerimaan', receipt.get('receipt_code', '')),
                    ('Vendor CMT (pengirim)', receipt.get('cmt_name', '') or '-'),
                    ('No PO', receipt.get('po_number', '') or '-'),
                    ('SJ Vendor', receipt.get('delivery_note', '') or '-'),
                    ('Tanggal Terima', _fmt_date(receipt.get('receipt_date') or receipt.get('created_at'))),
                    ('Tujuan', 'Gudang DA'),
                    ('Status QC', 'Selesai QC' if qc_done else 'Sedang QC'),
                ], avail=CONTENT_W_LANDSCAPE)
            all_col_keys = ['no', 'serial', 'sku', 'product', 'size', 'color',
                            'qty_sent', 'qty_received', 'qty_reject', 'notes']
            all_headers = ['No', 'Serial No', 'SKU', 'Nama Produk', 'Size', 'Warna',
                           'Qty Kirim', 'Qty Terima', 'Qty Reject', 'Keterangan']
            numeric = ('qty_sent', 'qty_received', 'qty_reject')
            data_rows = []
            for idx, ln in enumerate(rows_src, 1):
                data_rows.append([
                    idx, _safe_str(ln['serial']), _safe_str(ln['sku']),
                    _safe_str(ln['product'], 60), _safe_str(ln['size']), _safe_str(ln['color']),
                    _fmt_qty_id(ln['qty_sent']), _fmt_qty_id(ln['qty_received']),
                    _fmt_qty_id(ln['qty_reject']), _safe_str(ln['notes'], 60),
                ])
            headers, data_rows, active_keys, weights, right_cols, _ds = await tpl_table_parts(
                db, 'cmt-delivery-note', all_col_keys, all_headers, data_rows,
                numeric_keys=numeric, config=config)
            total_row = [''] * len(headers)
            labeled = False
            for key in numeric:
                if key not in active_keys:
                    continue
                ci = active_keys.index(key)
                total_row[ci] = _fmt_qty_id(sum(ln[key] for ln in rows_src))
                if not labeled and ci > 0 and not total_row[ci - 1]:
                    total_row[ci - 1] = 'TOTAL'
                    labeled = True
            if not labeled and total_row:
                total_row[0] = 'TOTAL'
            data_rows.append(total_row)
            elements.append(_pdf_data_table(
                headers, data_rows, weights=weights, right_cols=right_cols,
                total_row=True, page='landscape',
                style=(doc_settings.get('_template') or {}).get('table')))
            if not qc_done:
                elements.append(Spacer(1, 3*mm))
                elements.append(Paragraph(
                    "<i>Catatan: QC penerimaan ini BELUM selesai — kolom Qty Terima / "
                    "Qty Reject masih dapat berubah setelah pemeriksaan.</i>", styles['Normal']))
            if receipt.get('notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(
                    f"<b>Catatan:</b> {_safe_str(receipt.get('notes', ''), 300)}", styles['Normal']))
            _pdf_signature_block(elements, doc_settings, {
                'cmt_name': receipt.get('cmt_name', ''),
                'dn_number': dn.get('dn_number', ''),
                'receipt_code': receipt.get('receipt_code', ''),
                'po_number': receipt.get('po_number', ''),
            })
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements, page='landscape')
            return _pdf_response(buf, f"SJ-CMT-{receipt.get('receipt_code', 'unknown')}.pdf")

        # ──── PANDUAN PRODUK & PROSES PRODUKSI (SOP) ────
        # Satu tombol dipakai dari beberapa layar: id boleh berupa vendor
        # shipment (detail pengiriman CMT), production job, atau id artikel.
        elif pdf_type == 'production-guide':
            ref_id = sp.get('id') or sp.get('shipment_id') or sp.get('job_id')
            ctx = await _resolve_production_guide(db, ref_id)
            guides = ctx['guides']
            doc_settings = await get_doc_settings(db, 'production-guide')
            elements = []
            _pdf_header_branded(elements, profile, doc_settings, ctx['title'],
                                info_pairs=ctx['info_pairs'])

            if not guides:
                elements.append(Paragraph(
                    "<b>Belum ada artikel master (Katalog Buyer / Master Produk) yang tertaut "
                    "ke dokumen ini.</b>", styles['Normal']))
                elements.append(Spacer(1, 3 * mm))
                elements.append(Paragraph(
                    "Lengkapi tautan artikel pada PO/pekerjaan, lalu isi Panduan Produksi di "
                    "Katalog Buyer → Panduan Produksi (Maklon) atau Master Produk (Internal).",
                    styles['Normal']))
            for gi, g in enumerate(guides, 1):
                if gi > 1:
                    elements.append(Spacer(1, 6 * mm))
                title_line = ' — '.join([x for x in [_safe_str(g.get('code'), 30),
                                                     _safe_str(g.get('name'), 60)] if x]) or 'Artikel'
                elements.append(Paragraph(f"<b>{gi}. {title_line}</b>", styles['Heading3']))
                meta_bits = [g.get('source_label', '')]
                if g.get('sop_updated_at'):
                    meta_bits.append(f"SOP diperbarui: {_fmt_date(g.get('sop_updated_at'))}")
                if g.get('sop_updated_by'):
                    meta_bits.append(f"oleh {_safe_str(g.get('sop_updated_by'), 40)}")
                elements.append(Paragraph(
                    f"<i>{_safe_str(' · '.join([m for m in meta_bits if m]), 160)}</i>", styles['Normal']))
                if g.get('description'):
                    elements.append(Spacer(1, 2 * mm))
                    elements.append(Paragraph(
                        f"<b>Deskripsi:</b> {_safe_str(g.get('description'), 600)}", styles['Normal']))

                steps = g.get('sop_steps') or []
                elements.append(Spacer(1, 3 * mm))
                if steps:
                    rows = []
                    for si, s in enumerate(steps, 1):
                        if isinstance(s, dict):
                            seq = s.get('seq') or si
                            rows.append([seq, _safe_str(s.get('title', ''), 60),
                                         _safe_str(s.get('description', ''), 400)])
                        else:
                            rows.append([si, _safe_str(s, 60), ''])
                    elements.append(_pdf_data_table(
                        ['No', 'Langkah', 'Rincian / Standar Kerja'], rows,
                        weights=[0.4, 2.0, 4.2]))
                else:
                    elements.append(Paragraph(
                        "<i>Langkah SOP belum diisi untuk artikel ini.</i>", styles['Normal']))

                # Gambar acuan (langkah + referensi) — hanya berkas lokal yang bisa disematkan.
                img_specs = []
                for s in steps:
                    if isinstance(s, dict) and s.get('image_path'):
                        img_specs.append({'url': s['image_path'],
                                          'caption': _safe_str(s.get('title', ''), 40)})
                for im in (g.get('reference_images') or []):
                    if isinstance(im, dict) and im.get('url'):
                        img_specs.append({'url': im['url'], 'caption': _safe_str(im.get('caption', ''), 40)})
                flow_imgs = []
                for spec in img_specs[:6]:
                    img = _pdf_image(spec['url'])
                    if img:
                        flow_imgs.append((img, spec['caption']))
                if flow_imgs:
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(Paragraph("<b>Gambar acuan</b>", styles['Heading4']))
                    cells, caps = [], []
                    for img, cap in flow_imgs:
                        cells.append(img)
                        caps.append(Paragraph(f"<i>{cap or '-'}</i>", styles['SmallCell']))
                    grid, cap_row = [], []
                    for i in range(0, len(cells), 3):
                        grid.append(cells[i:i + 3] + [''] * (3 - len(cells[i:i + 3])))
                        cap_row.append(caps[i:i + 3] + [''] * (3 - len(caps[i:i + 3])))
                    tbl_rows = []
                    for r, c in zip(grid, cap_row):
                        tbl_rows.append(r)
                        tbl_rows.append(c)
                    it = Table(tbl_rows, colWidths=[172, 172, 172])
                    it.setStyle(TableStyle([
                        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
                    ]))
                    elements.append(it)

                vids = [v for v in (g.get('reference_videos') or []) if isinstance(v, dict) and v.get('url')]
                if vids:
                    elements.append(Spacer(1, 3 * mm))
                    elements.append(Paragraph("<b>Video acuan</b>", styles['Heading4']))
                    for v in vids[:8]:
                        elements.append(Paragraph(
                            f"• {_safe_str(v.get('title', '') or 'Video', 60)} — "
                            f"{_safe_str(v.get('url', ''), 120)}", styles['Normal']))

            sig_context = {'vendor_name': '', 'shipment_number': ''}
            for k, v in ctx['info_pairs']:
                if k.startswith('Vendor'):
                    sig_context['vendor_name'] = v
                if k == 'No Shipment':
                    sig_context['shipment_number'] = v
            _pdf_signature_block(elements, doc_settings, sig_context)
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements)
            return _pdf_response(buf, ctx['filename'])

        # ──── VENDOR INSPECTION PDF ────
        elif pdf_type == 'vendor-inspection':
            insp_id = sp.get('id')
            if not insp_id:
                raise HTTPException(400, 'id required')
            insp = await db.vendor_material_inspections.find_one({'id': insp_id}, {'_id': 0})
            if not insp:
                raise HTTPException(404, 'Inspection not found')
            shipment = await db.vendor_shipments.find_one({'id': insp.get('shipment_id')}, {'_id': 0})
            # Get PO info
            po_id = (shipment or {}).get('po_id', '')
            if not po_id:
                first_si = await db.vendor_shipment_items.find_one({'shipment_id': insp.get('shipment_id')})
                if first_si:
                    po_id = first_si.get('po_id', '')
            po = await db.production_pos.find_one({'id': po_id}, {'_id': 0}) if po_id else None
            # Get invoice if linked — FORENSIC_12 GAP-01: legacy `invoices` dropped.
            # Read from rahaza_ap_invoices (SSOT for AP invoices).
            invoice = await db.rahaza_ap_invoices.find_one({'po_id': po_id}, {'_id': 0}) if po_id else None
            # Get all inspection items
            all_insp_items = await db.vendor_material_inspection_items.find({'inspection_id': insp_id}, {'_id': 0}).to_list(500)
            material_items = [i for i in all_insp_items if i.get('item_type') != 'accessory']
            accessory_items = [i for i in all_insp_items if i.get('item_type') == 'accessory']
            # Prefetch product categories in single batch
            mat_pnames = list({(it.get('product_name') or '') for it in material_items if it.get('product_name')})
            mat_categories = {}
            if mat_pnames:
                async for prod in db.products.find(
                    {'product_name': {'$in': mat_pnames}}, {'_id': 0, 'product_name': 1, 'category': 1}
                ):
                    mat_categories[prod['product_name']] = prod.get('category', '-')
            elements = []
            info_pairs = [
                ('No PO', (po or {}).get('po_number', '-')),
                ('No Invoice', (invoice or {}).get('invoice_number', '-')),
                ('Vendor', insp.get('vendor_name', '')),
                ('Tanggal Inspeksi', _fmt_date(insp.get('inspection_date'))),
                ('No Shipment', insp.get('shipment_number', '')),
                ('Status', insp.get('status', '')),
            ]
            _pdf_header(elements, company_name, 'Laporan Inspeksi Material (Vendor)', info_pairs=info_pairs)
            # Material items table
            if material_items:
                elements.append(Paragraph("<b>Material Items:</b>", styles['Heading3']))
                headers = ['No', 'Produk', 'SKU', 'Size', 'Warna', 'Qty Dikirim', 'Qty Diterima', 'Qty Missing', 'Catatan']
                data_rows = []
                for idx, item in enumerate(material_items, 1):
                    category = mat_categories.get(item.get('product_name', ''), '-')
                    data_rows.append([
                        idx, f"{item.get('product_name', '')}\n({category})",
                        item.get('sku', ''), item.get('size', ''), item.get('color', ''),
                        item.get('ordered_qty', 0), item.get('received_qty', 0),
                        item.get('missing_qty', 0), _safe_str(item.get('condition_notes', ''))
                    ])
                td = [headers] + data_rows
                total_row = ['', '', '', '', 'TOTAL',
                    sum(i.get('ordered_qty', 0) for i in material_items),
                    sum(i.get('received_qty', 0) for i in material_items),
                    sum(i.get('missing_qty', 0) for i in material_items), '']
                td.append(total_row)
                cw = [25, 90, 60, 40, 50, 55, 55, 55, 90]
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(_pdf_total_row_style())
                elements.append(t)
            # Accessory items table
            if accessory_items:
                elements.append(Spacer(1, 6*mm))
                elements.append(Paragraph("<b>Aksesoris Items:</b>", styles['Heading3']))
                acc_headers = ['No', 'Aksesoris', 'Kode', 'Satuan', 'Qty Dikirim', 'Qty Diterima', 'Qty Missing', 'Catatan']
                acc_rows = []
                for idx, acc in enumerate(accessory_items, 1):
                    acc_rows.append([
                        idx, acc.get('accessory_name', ''), acc.get('accessory_code', ''),
                        acc.get('unit', 'pcs'), acc.get('ordered_qty', 0),
                        acc.get('received_qty', 0), acc.get('missing_qty', 0),
                        _safe_str(acc.get('condition_notes', ''))
                    ])
                acc_td = [acc_headers] + acc_rows
                acc_total = ['', '', '', 'TOTAL',
                    sum(a.get('ordered_qty', 0) for a in accessory_items),
                    sum(a.get('received_qty', 0) for a in accessory_items),
                    sum(a.get('missing_qty', 0) for a in accessory_items), '']
                acc_td.append(acc_total)
                acc_cw = [25, 100, 70, 45, 60, 60, 60, 90]
                at = Table(acc_td, colWidths=acc_cw, repeatRows=1)
                at.setStyle(_pdf_table_style())
                at.setStyle(_pdf_total_row_style())
                elements.append(at)
            if insp.get('overall_notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Catatan Umum:</b> {insp.get('overall_notes', '')}", styles['Normal']))
            # Signature
            elements.append(Spacer(1, 12*mm))
            sig_data = [['Inspektor', '', 'Pengirim (Vendor)'], ['', '', ''], ['_________________', '', '_________________']]
            st = Table(sig_data, colWidths=[180, 100, 180])
            st.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 9)]))
            elements.append(st)
            _pdf_footer(elements)
            _build_pdf(buf, elements, page='landscape')
            fname = f"Inspeksi-{insp.get('shipment_number', 'unknown')}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── BUYER SHIPMENT DISPATCH ────
        elif pdf_type == 'buyer-shipment-dispatch':
            shipment_id = sp.get('shipment_id')
            dispatch_seq = int(sp.get('dispatch_seq', 0))
            if not shipment_id or not dispatch_seq:
                raise HTTPException(400, 'shipment_id and dispatch_seq required')
            bs = await db.buyer_shipments.find_one({'id': shipment_id}, {'_id': 0})
            if not bs:
                raise HTTPException(404, 'Buyer shipment not found')
            items = await db.buyer_shipment_items.find({
                'shipment_id': shipment_id, 'dispatch_seq': dispatch_seq
            }, {'_id': 0}).to_list(500)
            if not items:
                raise HTTPException(404, f'No items for dispatch #{dispatch_seq}')
            all_items = await db.buyer_shipment_items.find({'shipment_id': shipment_id}).to_list(500)
            cumulative_by_poi = {}
            for ai in all_items:
                key = ai.get('po_item_id') or ai['id']
                if key not in cumulative_by_poi:
                    cumulative_by_poi[key] = {'ordered': ai.get('ordered_qty', 0), 'shipped': 0}
                if ai.get('dispatch_seq', 1) <= dispatch_seq:
                    cumulative_by_poi[key]['shipped'] += ai.get('qty_shipped', 0)
            doc_settings = await get_doc_settings(db, 'buyer-shipment-dispatch')
            elements = []
            # GAP D — surat jalan gabungan: header harus menyebut SEMUA PO.
            _d_po_ids = [p for p in (bs.get('po_ids') or []) if p] or (
                [bs['po_id']] if bs.get('po_id') else [])
            for _it in all_items:
                if _it.get('po_id') and _it['po_id'] not in _d_po_ids:
                    _d_po_ids.append(_it['po_id'])
            _d_po_meta = {}
            if _d_po_ids:
                async for _p in db.production_pos.find(
                        {'id': {'$in': _d_po_ids}}, {'_id': 0, 'id': 1, 'po_number': 1}):
                    _d_po_meta[_p['id']] = _p
            _d_po_numbers = [(_d_po_meta.get(p) or {}).get('po_number', '') for p in _d_po_ids]
            _d_po_numbers = [n for n in _d_po_numbers if n] or (
                [bs.get('po_number', '')] if bs.get('po_number') else [])
            _pdf_header_branded(elements, profile, doc_settings, f'SURAT JALAN — DISPATCH KE BUYER #{dispatch_seq}', info_pairs=[
                ('No Shipment', bs.get('shipment_number', '')),
                ('No PO', _safe_str(', '.join(_d_po_numbers) if _d_po_numbers else '-', 90)),
                ('Customer', bs.get('customer_name', '')), ('Vendor', bs.get('vendor_name', '')),
                ('Tanggal Dispatch', _fmt_date(items[0].get('dispatch_date', ''))), ('Dispatch #', str(dispatch_seq)),
            ], avail=CONTENT_W_LANDSCAPE)
            all_col_keys = ['no', 'po', 'serial', 'product', 'sku', 'size', 'color', 'ordered', 'this_dispatch', 'cumul_shipped', 'remaining']
            headers = ['No', 'No. PO', 'Serial', 'Produk', 'SKU', 'Size', 'Warna',
                       'Qty Order', 'Dikirim Kali Ini', 'Total Dikirim', 'Sisa']
            # FASE F — bobot lebar kolom per KEY supaya tetap benar walau sebagian
            # kolom disembunyikan lewat konfigurasi PDF (`config['columns']`).
            weight_map = {'no': 0.45, 'po': 1.4, 'serial': 1.0, 'product': 2.4, 'sku': 1.4,
                          'size': 0.6, 'color': 0.85, 'ordered': 0.95, 'this_dispatch': 1.2,
                          'cumul_shipped': 1.1, 'remaining': 0.75}
            num_keys = {'ordered', 'this_dispatch', 'cumul_shipped', 'remaining'}
            data_rows = []
            for idx, item in enumerate(items, 1):
                key = item.get('po_item_id') or item['id']
                cum = cumulative_by_poi.get(key, {'ordered': 0, 'shipped': 0})
                data_rows.append([
                    idx,
                    _safe_str(item.get('po_number')
                              or (_d_po_meta.get(item.get('po_id')) or {}).get('po_number', '')
                              or bs.get('po_number', ''), 24),
                    _safe_str(item.get('serial_number')), _safe_str(item.get('product_name'), 60),
                    _safe_str(item.get('sku')), _safe_str(item.get('size')), _safe_str(item.get('color')),
                    f"{item.get('ordered_qty', 0):,}".replace(',', '.'),
                    f"{item.get('qty_shipped', 0):,}".replace(',', '.'),
                    f"{cum['shipped']:,}".replace(',', '.'),
                    f"{max(0, cum['ordered'] - cum['shipped']):,}".replace(',', '.'),
                ])
            active_keys = all_col_keys
            headers, data_rows, active_keys, weights, right_cols, _ds = await tpl_table_parts(
                db, 'buyer-shipment-dispatch', all_col_keys, headers, data_rows,
                weight_map=weight_map, numeric_keys=tuple(num_keys), config=config)
            total_this = sum(i.get('qty_shipped', 0) for i in items)
            total_cum = sum(v['shipped'] for v in cumulative_by_poi.values())
            total_ord = sum(v['ordered'] for v in cumulative_by_poi.values())
            totals_by_key = {
                'ordered': total_ord, 'this_dispatch': total_this,
                'cumul_shipped': total_cum, 'remaining': max(0, total_ord - total_cum),
            }
            # Baris TOTAL dibangun per KEY — dulu memakai indeks negatif
            # (`total_row[-5] = 'TOTAL'`) sehingga label bisa mendarat di kolom
            # yang salah begitu ada kolom disembunyikan.
            total_row = []
            label_placed = False
            for k in active_keys:
                if k in totals_by_key:
                    total_row.append(f"{totals_by_key[k]:,}".replace(',', '.'))
                elif not label_placed and k == 'product':
                    total_row.append('TOTAL')
                    label_placed = True
                else:
                    total_row.append('')
            if not label_placed and total_row:
                total_row[0] = 'TOTAL'
            data_rows.append(total_row)
            elements.append(_pdf_data_table(
                headers, data_rows, weights=weights, right_cols=right_cols,
                total_row=True, page='landscape',
                style=(doc_settings.get('_template') or {}).get('table')))
            sig_context = {
                'buyer_name': bs.get('customer_name') or bs.get('vendor_name', ''),
                'shipment_number': bs.get('shipment_number', ''),
            }
            _pdf_signature_block(elements, doc_settings, sig_context, page='landscape')
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements, page='landscape')
            fname = f"buyer_dispatch_{bs.get('shipment_number','')}_D{dispatch_seq}.pdf"
            return _pdf_response(buf, fname)

        # ──── BUYER SHIPMENT (Cumulative Summary - all dispatches combined) ────
        elif pdf_type == 'buyer-shipment':
            sid = sp.get('id')
            if not sid:
                raise HTTPException(400, 'id required')
            bs = await db.buyer_shipments.find_one({'id': sid}, {'_id': 0})
            if not bs:
                raise HTTPException(404, 'Buyer shipment not found')
            all_items = await db.buyer_shipment_items.find({'shipment_id': sid}, {'_id': 0}).to_list(500)
            doc_settings = await get_doc_settings(db, 'buyer-shipment-dispatch')
            elements = []
            total_dispatches = max((i.get('dispatch_seq', 1) for i in all_items), default=0)
            # ── GAP D (audit 2026-07-31) — SURAT JALAN GABUNGAN MULTI-PO ──────────
            # BUG NYATA: header `No PO` KOSONG dan tabel item TIDAK punya kolom No. PO
            # untuk surat jalan gabungan (header memang lintas PO), sehingga dokumen
            # yang dikirim ke buyer tidak menyebut PO apa pun. Sekarang: daftar semua
            # PO di header + kolom No. PO + SUBTOTAL per PO.
            _po_ids = [p for p in (bs.get('po_ids') or []) if p]
            if not _po_ids and bs.get('po_id'):
                _po_ids = [bs['po_id']]
            for _it in all_items:
                if _it.get('po_id') and _it['po_id'] not in _po_ids:
                    _po_ids.append(_it['po_id'])
            _po_meta = {}
            if _po_ids:
                async for _p in db.production_pos.find(
                        {'id': {'$in': _po_ids}},
                        {'_id': 0, 'id': 1, 'po_number': 1, 'customer_name': 1}):
                    _po_meta[_p['id']] = _p
            _po_numbers = [(_po_meta.get(p) or {}).get('po_number', '') for p in _po_ids]
            _po_numbers = [n for n in _po_numbers if n] or (
                [bs.get('po_number', '')] if bs.get('po_number') else [])
            is_consolidated = bool(bs.get('consolidated') or bs.get('is_consolidated')) or len(_po_ids) > 1
            _po_label = (', '.join(_po_numbers) if _po_numbers else '-')
            _title = ('SURAT JALAN BUYER — GABUNGAN ' + str(len(_po_ids)) + ' PO'
                      if is_consolidated else 'SURAT JALAN BUYER — REKAP KUMULATIF')
            _pdf_header_branded(elements, profile, doc_settings, _title, info_pairs=[
                ('No Shipment', bs.get('shipment_number', '')),
                ('No PO', _safe_str(_po_label, 90)),
                ('Customer', bs.get('customer_name', '')), ('Vendor', bs.get('vendor_name', '')),
                ('Status', bs.get('status', bs.get('ship_status', ''))),
                ('Total Dispatch', str(total_dispatches)),
                ('Jenis Dokumen', 'Gabungan lintas PO' if is_consolidated else 'Satu PO'),
            ], avail=CONTENT_W_LANDSCAPE)
            # Build cumulative summary per po_item (not per dispatch), grouped per PO
            poi_cumulative = {}
            for item in all_items:
                key = item.get('po_item_id') or f"{item.get('serial_number','')}|{item.get('sku','')}|{item.get('size','')}|{item.get('color','')}"
                if key not in poi_cumulative:
                    poi_cumulative[key] = {
                        'po_id': item.get('po_id') or bs.get('po_id') or '',
                        'po_number': (item.get('po_number')
                                      or (_po_meta.get(item.get('po_id')) or {}).get('po_number', '')
                                      or bs.get('po_number', '')),
                        'serial_number': item.get('serial_number', ''),
                        'product_name': item.get('product_name', ''),
                        'sku': item.get('sku', ''),
                        'size': item.get('size', ''),
                        'color': item.get('color', ''),
                        'ordered_qty': item.get('ordered_qty', 0),
                        'total_shipped': 0,
                    }
                poi_cumulative[key]['total_shipped'] += item.get('qty_shipped', 0)
            if not poi_cumulative:
                elements.append(Paragraph("Belum ada item dispatch pada surat jalan ini.",
                                          styles['Normal']))
            else:
                # ── FASE F (2026-08-15) — DOKUMEN INI DULU TUMPANG TINDIH ─────
                # Cacat yang diperbaiki, terbukti dari kode (bukan selera):
                #   1. Baris "SUBTOTAL {po}" ditulis ke KOLOM 'Color' yang lebarnya
                #      44 pt memakai `Table()` mentah berisi STRING (bukan
                #      Paragraph) ⇒ tidak ada word-wrap ⇒ teks meluber menimpa
                #      kolom angka di sebelahnya ("SUBTOTAL test-po00" + "100").
                #   2. `cw` hardcode berjumlah 569 pt sementara lebar konten A4
                #      landscape margin 12 mm = 773,8 pt ⇒ tabel hanya mengisi 73%
                #      halaman padahal margin kiri-kanan terlihat lega.
                #   3. Subtotal per PO DIHAPUS atas keputusan pemilik: dokumen ini
                #      adalah REKAP KUMULATIF, dan rincian per pengiriman sudah
                #      punya surat jalannya sendiri (per dispatch). Kolom "No. PO"
                #      tetap ada sehingga asal setiap baris tidak hilang.
                headers = ['No', 'No. PO', 'Serial', 'Produk', 'SKU', 'Size', 'Warna',
                           'Qty Order', 'Total Dikirim', 'Sisa']
                weights = [0.45, 1.5, 1.1, 2.6, 1.5, 0.6, 0.9, 0.95, 1.15, 0.8]
                right_cols = {7, 8, 9}
                data_rows = []
                for idx, cum in enumerate(
                        sorted(poi_cumulative.values(),
                               key=lambda c: (c['po_number'] or '', c['sku'] or '')), 1):
                    remaining = max(0, cum['ordered_qty'] - cum['total_shipped'])
                    data_rows.append([
                        idx, _safe_str(cum['po_number'] or '-', 24),
                        _safe_str(cum['serial_number']), _safe_str(cum['product_name'], 60),
                        _safe_str(cum['sku']), _safe_str(cum['size']), _safe_str(cum['color']),
                        f"{cum['ordered_qty']:,}".replace(',', '.'),
                        f"{cum['total_shipped']:,}".replace(',', '.'),
                        f"{remaining:,}".replace(',', '.'),
                    ])
                total_ordered = sum(v['ordered_qty'] for v in poi_cumulative.values())
                total_shipped = sum(v['total_shipped'] for v in poi_cumulative.values())
                total_remaining = max(0, total_ordered - total_shipped)
                data_rows.append(['', '', '', 'TOTAL', '', '', '',
                                  f"{total_ordered:,}".replace(',', '.'),
                                  f"{total_shipped:,}".replace(',', '.'),
                                  f"{total_remaining:,}".replace(',', '.')])
                elements.append(_pdf_data_table(
                    headers, data_rows, weights=weights, right_cols=right_cols,
                    total_row=True, page='landscape'))
            sig_context = {
                'buyer_name': bs.get('customer_name') or bs.get('vendor_name', ''),
                'shipment_number': bs.get('shipment_number', ''),
            }
            _pdf_signature_block(elements, doc_settings, sig_context, page='landscape')
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements, page='landscape')
            fname = f"Buyer-Shipment-{bs.get('shipment_number', sid)}-Kumulatif.pdf"
            return _pdf_response(buf, fname)

        # ──── PRODUCTION RETURN ────
        elif pdf_type == 'production-return':
            rid = sp.get('id')
            if not rid:
                raise HTTPException(400, 'id required')
            ret = await db.production_returns.find_one({'id': rid}, {'_id': 0})
            if not ret:
                raise HTTPException(404, 'Production return not found')
            items = await db.production_return_items.find({'return_id': rid}, {'_id': 0}).to_list(500)
            elements = []
            _pdf_header(elements, company_name, 'Surat Retur Produksi', info_pairs=[
                ('Return No', ret.get('return_number', '')), ('PO Number', ret.get('reference_po_number', '')),
                ('Customer', ret.get('customer_name', '')), ('Status', ret.get('status', '')),
                ('Return Date', _fmt_date(ret.get('return_date'))), ('Reason', _safe_str(ret.get('return_reason', ''), 60)),
            ])
            if items:
                td = [['No', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty Returned', 'Notes']]
                for idx, i in enumerate(items, 1):
                    td.append([idx, _safe_str(i.get('serial_number')), _safe_str(i.get('product_name')),
                               _safe_str(i.get('sku')), _safe_str(i.get('size')), _safe_str(i.get('color')),
                               i.get('return_qty', 0), _safe_str(i.get('notes', ''), 30)])
                total_row = ['', '', '', '', '', 'TOTAL', sum(i.get('return_qty', 0) for i in items), '']
                td.append(total_row)
                cw = [25, 60, 100, 70, 40, 50, 65, 80]
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                t.setStyle(_pdf_total_row_style())
                elements.append(t)
            else:
                elements.append(Paragraph("No return items found.", styles['Normal']))
            if ret.get('notes'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Notes:</b> {ret.get('notes', '')}", styles['Normal']))
            _pdf_footer(elements)
            _build_pdf(buf, elements)
            fname = f"Retur-{ret.get('return_number', rid)}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── MATERIAL REQUEST ────
        elif pdf_type == 'material-request':
            req_id = sp.get('id')
            if not req_id:
                raise HTTPException(400, 'id required')
            req = await db.material_requests.find_one({'id': req_id}, {'_id': 0})
            if not req:
                raise HTTPException(404, 'Material request not found')
            elements = []
            req_type = req.get('request_type', 'ADDITIONAL')
            _pdf_header(elements, company_name, f'Surat Permohonan Material ({req_type})', info_pairs=[
                ('Request No', req.get('request_number', '')), ('PO Number', req.get('po_number', '')),
                ('Vendor', req.get('vendor_name', '')), ('Status', req.get('status', '')),
                ('Total Qty', req.get('total_requested_qty', 0)),
                ('Child Shipment', req.get('child_shipment_number', '-')),
            ])
            # Request items if available
            req_items = req.get('items', [])
            if req_items:
                td = [['No', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty Requested']]
                for idx, i in enumerate(req_items, 1):
                    td.append([idx, _safe_str(i.get('serial_number')), _safe_str(i.get('product_name')),
                               _safe_str(i.get('sku')), _safe_str(i.get('size')), _safe_str(i.get('color')),
                               i.get('qty_requested', i.get('requested_qty', 0))])
                cw = [25, 65, 110, 75, 45, 55, 70]
                t = Table(td, colWidths=cw, repeatRows=1)
                t.setStyle(_pdf_table_style())
                elements.append(t)
            else:
                elements.append(Paragraph(f"Total Requested Quantity: <b>{req.get('total_requested_qty', 0)}</b>", styles['Normal']))
            if req.get('reason'):
                elements.append(Spacer(1, 4*mm))
                elements.append(Paragraph(f"<b>Reason:</b> {req.get('reason', '')}", styles['Normal']))
            # Approval signatures
            elements.append(Spacer(1, 15*mm))
            sig_data = [['Diajukan oleh:', '', 'Disetujui oleh:'], ['', '', ''], ['_________________', '', '_________________']]
            st = Table(sig_data, colWidths=[180, 100, 180])
            st.setStyle(TableStyle([('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('FONTSIZE', (0, 0), (-1, -1), 9)]))
            elements.append(st)
            _pdf_footer(elements)
            _build_pdf(buf, elements)
            fname = f"Permohonan-{req.get('request_number', req_id)}.pdf"
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename={fname}"})

        # ──── PRODUCTION REPORT (full) ────
        elif pdf_type == 'production-report':
            elements = []
            # SESI #19 — laporan ikut memakai kop TEMPLATE (dulu `_pdf_header` polos:
            # hanya nama perusahaan, tanpa logo/telepon/NPWP dan tanpa garis kop).
            doc_settings = await get_doc_settings(db, 'production-report')
            _pdf_header_branded(elements, profile, doc_settings, 'LAPORAN PRODUKSI',
                                avail=CONTENT_W_LANDSCAPE)
            pos = await db.production_pos.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
            all_col_keys = ['no', 'date', 'po', 'serial', 'product', 'sku', 'size', 'color', 'qty', 'price', 'cmt', 'vendor', 'produced', 'shipped']
            headers = ['No', 'Date', 'PO', 'Serial', 'Product', 'SKU', 'Size', 'Color', 'Qty', 'Price', 'CMT', 'Vendor', 'Produced', 'Shipped']
            data_rows = []
            rn = 1
            for po in pos:
                items = await db.po_items.find({'po_id': po['id']}).to_list(500)
                for item in items:
                    ji = await db.production_job_items.find({'po_item_id': item['id']}).to_list(500)
                    produced = sum(j.get('produced_qty', 0) for j in ji)
                    bi = await db.buyer_shipment_items.find({'po_item_id': item['id']}).to_list(500)
                    shipped = sum(b.get('qty_shipped', 0) for b in bi)
                    data_rows.append([rn, _fmt_date(po.get('po_date')), _safe_str(po.get('po_number'), 15),
                        _safe_str(item.get('serial_number'), 15), _safe_str(item.get('product_name'), 20),
                        _safe_str(item.get('sku'), 15), _safe_str(item.get('size'), 8), _safe_str(item.get('color'), 10),
                        item.get('qty', 0), _fmt_money(item.get('selling_price_snapshot', 0)),
                        _fmt_money(item.get('cmt_price_snapshot', 0)),
                        _safe_str(po.get('vendor_name'), 15), produced, shipped])
                    rn += 1
            # W2 (sesi #29) — penyaringan kolom KEDUA di sini dihapus (lihat catatan
            # pada laporan generik di bawah): `tpl_table_parts` sudah menyaring, dan
            # menyaring dua kali membuat indeks kolom meleset ⇒ cetakan gagal 500.
            if not data_rows:
                elements.append(Paragraph("Tidak ada data produksi.", styles['Normal']))
            else:
                # SESI #19 — memakai `_pdf_data_table`: lebar kolom PROPORSIONAL
                # (dulu `int(680 / len(headers))` — angka ajaib 680 pt padahal lebar
                # konten A4 landscape 773,8 pt ⇒ tabel tidak penuh) + sel melipat.
                _h, _rows, _keys, _w, _rc, _ds = await tpl_table_parts(
                    db, 'production-report', all_col_keys, headers, data_rows,
                    numeric_keys=('qty', 'price', 'cmt', 'produced', 'shipped'),
                    config=config)
                elements.append(_pdf_data_table(
                    _h, _rows, weights=_w, right_cols=_rc, page='landscape',
                    style=(doc_settings.get('_template') or {}).get('table')))
            _pdf_signature_block(elements, doc_settings,
                                 {'printed_by': (user or {}).get('name', '')},
                                 page='landscape')
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements, page='landscape')
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename=production_report_{now_wib().strftime('%Y%m%d')}.pdf"})

        # ──── REPORT-* (Reuse /api/reports/{type} query logic) ────
        elif pdf_type.startswith('report-'):
            report_type = pdf_type[7:]  # strip 'report-' prefix
            valid_report_types = ['production', 'progress', 'financial', 'shipment', 'defect', 'return', 'missing-material', 'replacement', 'accessory']
            if report_type not in valid_report_types:
                return JSONResponse({'error': f'Unknown report type: {report_type}', 'available': valid_report_types}, status_code=400)

            # ── Get report data by reusing the same query logic as /api/reports/{type} ──
            report_data = []

            if report_type == 'production':
                po_query = {}
                if sp.get('status'):
                    po_query['status'] = sp['status']
                pos = await db.production_pos.find(po_query, {'_id': 0}).sort('created_at', -1).to_list(500)
                # Batch fetch all po_items (one query)
                po_ids = [po['id'] for po in pos]
                items_by_po = {}
                if po_ids:
                    async for it in db.po_items.find({'po_id': {'$in': po_ids}}):
                        items_by_po.setdefault(it['po_id'], []).append(it)
                for po in pos:
                    if sp.get('vendor_id') and po.get('vendor_id') != sp['vendor_id']:
                        continue
                    items = items_by_po.get(po['id'], [])
                    for item in items:
                        if sp.get('serial_number') and item.get('serial_number') != sp['serial_number']:
                            continue
                        report_data.append({
                            'tanggal': _fmt_date(po.get('po_date', po.get('created_at'))),
                            'no_po': po.get('po_number', ''), 'no_seri': item.get('serial_number', ''),
                            'nama_produk': item.get('product_name', ''), 'sku': item.get('sku', ''),
                            'size': item.get('size', ''), 'warna': item.get('color', ''),
                            'output_qty': item.get('qty', 0),
                            'harga': item.get('selling_price_snapshot', 0), 'hpp': item.get('cmt_price_snapshot', 0),
                            'garment': po.get('vendor_name', ''), 'po_status': po.get('status', ''),
                        })
                headers = ['No', 'Tanggal', 'No PO', 'Serial', 'Produk', 'SKU', 'Size', 'Warna', 'Qty', 'Harga', 'HPP/CMT', 'Vendor', 'Status']
                all_col_keys = ['no', 'tanggal', 'no_po', 'no_seri', 'nama_produk', 'sku', 'size', 'warna', 'output_qty', 'harga', 'hpp', 'garment', 'po_status']

            elif report_type == 'progress':
                progs = await db.production_progress.find({}, {'_id': 0}).sort('progress_date', -1).to_list(500)
                # Batch prefetch
                ji_ids = list({p.get('job_item_id') for p in progs if p.get('job_item_id')})
                job_ids = list({p.get('job_id') for p in progs if p.get('job_id')})
                ji_map = {}
                if ji_ids:
                    async for d in db.production_job_items.find({'id': {'$in': ji_ids}}):
                        ji_map[d['id']] = d
                jobs_map = {}
                if job_ids:
                    async for d in db.production_jobs.find({'id': {'$in': job_ids}}):
                        jobs_map[d['id']] = d
                for p in progs:
                    ji = ji_map.get(p.get('job_item_id'))
                    job = jobs_map.get(p.get('job_id'))
                    if sp.get('vendor_id') and (job or {}).get('vendor_id') != sp['vendor_id']:
                        continue
                    report_data.append({
                        'date': _fmt_date(p.get('progress_date')),
                        'job_number': (job or {}).get('job_number', ''),
                        'po_number': (job or {}).get('po_number', ''),
                        'vendor_name': (job or {}).get('vendor_name', ''),
                        'serial_number': (ji or {}).get('serial_number', ''),
                        'sku': (ji or {}).get('sku', p.get('sku', '')),
                        'product_name': (ji or {}).get('product_name', p.get('product_name', '')),
                        'qty_progress': p.get('completed_quantity', 0),
                        'notes': p.get('notes', ''), 'recorded_by': p.get('recorded_by', '')
                    })
                headers = ['No', 'Tanggal', 'Job', 'PO', 'Vendor', 'Serial', 'SKU', 'Produk', 'Qty', 'Catatan', 'Dicatat oleh']
                all_col_keys = ['no', 'date', 'job_number', 'po_number', 'vendor_name', 'serial_number', 'sku', 'product_name', 'qty_progress', 'notes', 'recorded_by']

            elif report_type == 'financial':
                # FORENSIC_12 GAP-01: legacy `invoices` dropped. Read from SSOT.
                inv_query = {}
                if sp.get('status'):
                    inv_query['status'] = sp['status']
                ar_invs = await db.rahaza_ar_invoices.find(inv_query, {'_id': 0}).sort('created_at', -1).to_list(500)
                ap_invs = await db.rahaza_ap_invoices.find(inv_query, {'_id': 0}).sort('created_at', -1).to_list(500)
                invoices = ar_invs + ap_invs
                for inv in invoices:
                    report_data.append({
                        'invoice_number': inv.get('invoice_number', ''),
                        'category': inv.get('invoice_category', inv.get('type', '')),
                        'po_number': inv.get('po_number', inv.get('order_number', '')),
                        'vendor_or_buyer': inv.get('vendor_name', inv.get('customer_name', '')),
                        'amount': inv.get('total_amount', inv.get('total', inv.get('amount', 0))),
                        'paid': inv.get('total_paid', inv.get('paid_amount', 0)),
                        'remaining': inv.get('remaining_balance', 0),
                        'status': inv.get('status', ''),
                        'date': _fmt_date(inv.get('invoice_date', inv.get('created_at'))),
                    })
                headers = ['No', 'Invoice No', 'Category', 'PO', 'Vendor/Buyer', 'Amount', 'Paid', 'Remaining', 'Status', 'Date']
                all_col_keys = ['no', 'invoice_number', 'category', 'po_number', 'vendor_or_buyer', 'amount', 'paid', 'remaining', 'status', 'date']

            elif report_type == 'shipment':
                vs = await db.vendor_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
                bsh = await db.buyer_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
                for v in vs:
                    if sp.get('vendor_id') and v.get('vendor_id') != sp['vendor_id']:
                        continue
                    items = await db.vendor_shipment_items.find({'shipment_id': v['id']}).to_list(500)
                    report_data.append({
                        'direction': 'VENDOR', 'shipment_number': v.get('shipment_number', ''),
                        'shipment_type': v.get('shipment_type', 'NORMAL'), 'vendor_name': v.get('vendor_name', ''),
                        'status': v.get('status', ''), 'inspection': v.get('inspection_status', 'Pending'),
                        'date': _fmt_date(v.get('shipment_date', v.get('created_at'))),
                        'total_qty': sum(i.get('qty_sent', 0) for i in items), 'items': len(items)
                    })
                for b in bsh:
                    if sp.get('vendor_id') and b.get('vendor_id') != sp['vendor_id']:
                        continue
                    items = await db.buyer_shipment_items.find({'shipment_id': b['id']}).to_list(500)
                    report_data.append({
                        'direction': 'BUYER', 'shipment_number': b.get('shipment_number', ''),
                        'shipment_type': 'NORMAL', 'vendor_name': b.get('vendor_name', ''),
                        'status': b.get('status', b.get('ship_status', '')), 'inspection': '-',
                        'date': _fmt_date(b.get('created_at')),
                        'total_qty': sum(i.get('qty_shipped', 0) for i in items), 'items': len(items)
                    })
                headers = ['No', 'Direction', 'Shipment No', 'Type', 'Vendor', 'Status', 'Inspection', 'Date', 'Qty', 'Items']
                all_col_keys = ['no', 'direction', 'shipment_number', 'shipment_type', 'vendor_name', 'status', 'inspection', 'date', 'total_qty', 'items']

            elif report_type == 'defect':
                defects = await db.material_defect_reports.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
                for d in defects:
                    if sp.get('vendor_id') and d.get('vendor_id') != sp['vendor_id']:
                        continue
                    report_data.append({
                        'date': _fmt_date(d.get('report_date', d.get('created_at'))),
                        'sku': d.get('sku', ''), 'product_name': d.get('product_name', ''),
                        'size': d.get('size', ''), 'color': d.get('color', ''),
                        'defect_qty': d.get('defect_qty', 0), 'defect_type': d.get('defect_type', ''),
                        'description': d.get('description', ''), 'status': d.get('status', '')
                    })
                headers = ['No', 'Tanggal', 'SKU', 'Produk', 'Size', 'Warna', 'Qty Defect', 'Tipe', 'Deskripsi', 'Status']
                all_col_keys = ['no', 'date', 'sku', 'product_name', 'size', 'color', 'defect_qty', 'defect_type', 'description', 'status']

            elif report_type == 'return':
                returns = await db.production_returns.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
                for r in returns:
                    items = await db.production_return_items.find({'return_id': r['id']}).to_list(500)
                    report_data.append({
                        'return_number': r.get('return_number', ''), 'po_number': r.get('reference_po_number', ''),
                        'customer_name': r.get('customer_name', ''), 'return_date': _fmt_date(r.get('return_date')),
                        'total_qty': sum(i.get('return_qty', 0) for i in items), 'item_count': len(items),
                        'reason': r.get('return_reason', ''), 'status': r.get('status', ''),
                    })
                headers = ['No', 'Return No', 'PO', 'Customer', 'Date', 'Total Qty', 'Items', 'Reason', 'Status']
                all_col_keys = ['no', 'return_number', 'po_number', 'customer_name', 'return_date', 'total_qty', 'item_count', 'reason', 'status']

            elif report_type == 'missing-material':
                reqs = await db.material_requests.find({'request_type': 'ADDITIONAL'}, {'_id': 0}).sort('created_at', -1).to_list(500)
                for r in reqs:
                    if sp.get('vendor_id') and r.get('vendor_id') != sp['vendor_id']:
                        continue
                    report_data.append({
                        'request_number': r.get('request_number', ''), 'vendor_name': r.get('vendor_name', ''),
                        'po_number': r.get('po_number', ''), 'total_qty': r.get('total_requested_qty', 0),
                        'reason': r.get('reason', ''), 'status': r.get('status', ''),
                        'child_shipment': r.get('child_shipment_number', '-'),
                        'date': _fmt_date(r.get('created_at')),
                    })
                headers = ['No', 'Request No', 'Vendor', 'PO', 'Qty', 'Reason', 'Status', 'Child Shipment', 'Date']
                all_col_keys = ['no', 'request_number', 'vendor_name', 'po_number', 'total_qty', 'reason', 'status', 'child_shipment', 'date']

            elif report_type == 'replacement':
                reqs = await db.material_requests.find({'request_type': 'REPLACEMENT'}, {'_id': 0}).sort('created_at', -1).to_list(500)
                for r in reqs:
                    if sp.get('vendor_id') and r.get('vendor_id') != sp['vendor_id']:
                        continue
                    report_data.append({
                        'request_number': r.get('request_number', ''), 'vendor_name': r.get('vendor_name', ''),
                        'po_number': r.get('po_number', ''), 'total_qty': r.get('total_requested_qty', 0),
                        'reason': r.get('reason', ''), 'status': r.get('status', ''),
                        'child_shipment': r.get('child_shipment_number', '-'),
                        'date': _fmt_date(r.get('created_at')),
                    })
                headers = ['No', 'Request No', 'Vendor', 'PO', 'Qty', 'Reason', 'Status', 'Child Shipment', 'Date']
                all_col_keys = ['no', 'request_number', 'vendor_name', 'po_number', 'total_qty', 'reason', 'status', 'child_shipment', 'date']

            elif report_type == 'accessory':
                acc_ships = await db.accessory_shipments.find({}, {'_id': 0}).sort('created_at', -1).to_list(500)
                for s in acc_ships:
                    if sp.get('vendor_id') and s.get('vendor_id') != sp['vendor_id']:
                        continue
                    items = await db.accessory_shipment_items.find({'shipment_id': s['id']}).to_list(500)
                    for item in items:
                        report_data.append({
                            'shipment_number': s.get('shipment_number', ''), 'vendor_name': s.get('vendor_name', ''),
                            'po_number': s.get('po_number', ''), 'date': _fmt_date(s.get('shipment_date')),
                            'accessory_name': item.get('accessory_name', ''), 'accessory_code': item.get('accessory_code', ''),
                            'qty_sent': item.get('qty_sent', 0), 'unit': item.get('unit', 'pcs'),
                            'status': s.get('status', ''),
                        })
                headers = ['No', 'Shipment', 'Vendor', 'PO', 'Date', 'Accessory', 'Code', 'Qty', 'Unit', 'Status']
                all_col_keys = ['no', 'shipment_number', 'vendor_name', 'po_number', 'date', 'accessory_name', 'accessory_code', 'qty_sent', 'unit', 'status']
            else:
                return JSONResponse({'error': f'Unhandled report type: {report_type}'}, status_code=400)

            # Build the report PDF
            report_labels = {
                'production': 'Laporan Produksi', 'progress': 'Laporan Progres Produksi',
                'financial': 'Laporan Keuangan', 'shipment': 'Laporan Pengiriman',
                'defect': 'Laporan Defect Material', 'return': 'Laporan Retur Produksi',
                'missing-material': 'Laporan Material Hilang/Tambahan', 'replacement': 'Laporan Material Pengganti',
                'accessory': 'Laporan Aksesoris',
            }
            elements = []
            title = report_labels.get(report_type, f'Report: {report_type}')
            filter_info = []
            if sp.get('vendor_id'):
                vendor = await db.garments.find_one({'id': sp['vendor_id']})
                filter_info.append(('Vendor', (vendor or {}).get('garment_name', sp['vendor_id'])))
            if sp.get('date_from'):
                filter_info.append(('From', sp['date_from']))
            if sp.get('date_to'):
                filter_info.append(('To', sp['date_to']))
            if sp.get('status'):
                filter_info.append(('Status', sp['status']))
            # SESI #19 — kop laporan dari TEMPLATE (dulu `_pdf_header` polos).
            doc_settings = await get_doc_settings(db, pdf_type)
            _pdf_header_branded(elements, profile, doc_settings, title.upper(),
                                info_pairs=filter_info if filter_info else None,
                                avail=CONTENT_W_LANDSCAPE)

            if not report_data:
                elements.append(Paragraph("Tidak ada data ditemukan untuk filter yang dipilih.", styles['Normal']))
            else:
                # Build table data
                data_rows = []
                for idx, row in enumerate(report_data, 1):
                    row_values = [idx]
                    for key in all_col_keys[1:]:  # skip 'no'
                        val = row.get(key, '')
                        if key in ('harga', 'hpp', 'amount', 'paid', 'remaining'):
                            val = _fmt_money(val)
                        elif key in ('output_qty', 'qty_progress', 'defect_qty', 'total_qty', 'item_count', 'items', 'qty_sent'):
                            val = val if val else 0
                        else:
                            val = _safe_str(val, 25)
                        row_values.append(val)
                    data_rows.append(row_values)
                # W2 (sesi #29) — DULU di sini ada `_filter_columns(...)` KEDUA:
                # kolom sudah difilter di sini, lalu `tpl_table_parts` di bawah
                # memfilter LAGI memakai `all_col_keys` yang masih utuh ⇒ indeks
                # kolom meleset dan cetakan GAGAL 500 ("list index out of range").
                # Artinya konfigurasi kolom bernama (`?config_id=`) pun sebenarnya
                # tidak pernah bisa dipakai pada laporan-laporan ini. Sekarang
                # penyaringan kolom hanya terjadi di SATU tempat: tpl_table_parts.
                # SESI #19 — satu jalur tabel untuk semua laporan: lebar proporsional
                # penuh halaman + sel melipat (dulu `int(page_width / num_cols)` dengan
                # angka ajaib 680/445 pt dan STRING mentah tanpa word-wrap).
                _h, _rows, _keys, _w, _rc, _ds = await tpl_table_parts(
                    db, pdf_type, all_col_keys, headers, data_rows,
                    numeric_keys=('harga', 'hpp', 'amount', 'paid', 'remaining',
                                  'output_qty', 'qty_progress', 'defect_qty',
                                  'total_qty', 'item_count', 'items', 'qty_sent'),
                    config=config)
                headers = _h
                elements.append(_pdf_data_table(
                    _h, _rows, weights=_w, right_cols=_rc, page='landscape',
                    style=(doc_settings.get('_template') or {}).get('table')))

            elements.append(Spacer(1, 4*mm))
            elements.append(Paragraph(f"<i>Total Records: {len(report_data)}</i>", styles['Normal']))
            _pdf_signature_block(elements, doc_settings,
                                 {'printed_by': (user or {}).get('name', '')},
                                 page='landscape')
            _pdf_footer_branded(elements, profile, doc_settings)
            _build_pdf(buf, elements, page='landscape')
            return StreamingResponse(buf, media_type="application/pdf",
                                     headers={"Content-Disposition": f"attachment; filename=laporan_{report_type}_{now_wib().strftime('%Y%m%d')}.pdf"})

        else:
            all_types = [
                'production-po', 'vendor-shipment', 'buyer-shipment', 'buyer-shipment-dispatch',
                'production-return', 'material-request', 'production-report', 'production-guide',
                'report-production', 'report-progress', 'report-financial', 'report-shipment',
                'report-defect', 'report-return', 'report-missing-material', 'report-replacement', 'report-accessory'
            ]
            return JSONResponse({'error': f'Unknown PDF type: {pdf_type}', 'available_types': all_types}, status_code=400)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"PDF export error: {e}", exc_info=True)
        raise HTTPException(500, f"PDF export failed: {str(e)}")


# ─── PDF EXPORT CONFIGURATION CRUD ───────────────────────────────────────────

# Available columns per PDF type (used by config UI)
