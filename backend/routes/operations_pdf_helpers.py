# ruff: noqa: F401
"""
operations_pdf_helpers.py — PDF Generation Helper Functions
Utilities for PDF styling, table generation, and config management

Refactored: Session #11.19 Phase 3.2.6 (split from operations_pdf.py 900 LOC)
Used by: operations_pdf.py (main PDF export endpoint)
"""
import logging
from datetime import datetime
from utils.waktu import now_wib

logger = logging.getLogger(__name__)


# ─── LEBAR KONTEN HALAMAN (FASE F, 2026-08-15) ───────────────────────────────
# Dulu lebar tersedia ditulis sebagai angka ajaib: 515 (potrait) dan 786
# (landscape). Keduanya SALAH terhadap `_build_pdf()` yang memakai A4 dengan
# margin 12 mm:
#     potrait   : 595,28 pt − 2 × 34,02 pt = 527,2 pt  (dulu 515 → 12 pt terbuang)
#     landscape : 841,89 pt − 2 × 34,02 pt = 773,8 pt  (dulu 786 → 12 pt MELIMPAH
#                 keluar halaman, ReportLab memampatkan/meluberkan tabel)
# Akibat yang terlihat pemilik: tabel surat jalan hanya mengisi sebagian halaman
# padahal margin kiri-kanan lebar, dan sebagian dokumen melebar keluar.
#
# SESI #19 — angkanya kini TINGGAL DI SATU TEMPAT (`core/pdf_template.py`) karena
# editor template & pratinjau memakai geometri yang sama. Nama-nama di bawah tetap
# diekspor dari berkas ini supaya seluruh generator lama tidak perlu disentuh.
from core.pdf_template import (CONTENT_W_LANDSCAPE, CONTENT_W_PORTRAIT,  # noqa: E402
                               PDF_MARGIN_PT, content_width)


# ─── PDF Styling Helpers ─────────────────────────────────────────────────────
def _pdf_styles():
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='SmallCell', fontSize=7, leading=9, wordWrap='LTR'))
    styles.add(ParagraphStyle(name='SmallCellBold', fontSize=7, leading=9, fontName='Helvetica-Bold', wordWrap='LTR'))
    return styles


def _pdf_table_style(style=None):
    """Gaya tabel data. `style` (SESI #19) datang dari template PDF pemilik.

    Bawaannya SENGAJA identik dengan gaya lama (header #334155, zebra, grid) supaya
    dokumen yang belum diatur pemilik tetap tercetak sama persis seperti sebelumnya.
    """
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle
    style = style or {}
    try:
        bg = colors.HexColor(str(style.get('header_bg') or '#334155'))
    except Exception:  # noqa: BLE001
        bg = colors.HexColor('#334155')
    cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), bg),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]
    if style.get('grid', True):
        cmds.append(('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')))
    else:
        cmds.append(('LINEBELOW', (0, 0), (-1, 0), 0.6, colors.HexColor('#94a3b8')))
    if style.get('zebra', True):
        cmds.append(('ROWBACKGROUNDS', (0, 1), (-1, -1),
                     [colors.white, colors.HexColor('#f8fafc')]))
    return TableStyle(cmds)


def _pdf_total_row_style():
    from reportlab.lib import colors
    from reportlab.platypus import TableStyle
    return TableStyle([
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
    ])


# ─── Shared layout builders (fix overlap + lebar kolom konsisten) ─────────────
def _pdf_info_pairs(elements, info_pairs, avail=CONTENT_W_PORTRAIT):
    """Blok info (label: value) 2-kolom-pasang dengan value auto-wrap (anti-tumpang-tindih)."""
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    if not info_pairs:
        return elements
    kstyle = ParagraphStyle('ik', fontSize=8.5, leading=11, fontName='Helvetica-Bold')
    vstyle = ParagraphStyle('iv', fontSize=8.5, leading=11, wordWrap='LTR')

    def esc(v):
        return str(v if v not in (None, '') else '-').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    rows, row = [], []
    for i, (k, v) in enumerate(info_pairs):
        row.extend([Paragraph(f"{esc(k)}", kstyle), Paragraph(esc(v), vstyle)])
        if len(row) >= 4 or i == len(info_pairs) - 1:
            while len(row) < 4:
                row.append('')
            rows.append(row)
            row = []
    # label sempit, value lebar
    lw = max(70, avail * 0.16)
    vw = (avail - 2 * lw) / 2
    it = Table(rows, colWidths=[lw, vw, lw, vw])
    it.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 1), ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
    ]))
    elements.append(it)
    elements.append(Spacer(1, 4 * mm))
    return elements


def _pdf_data_table(headers, rows, *, weights=None, right_cols=None, total_row=False,
                    page=None, style=None):
    """Tabel data rapi & konsisten: sel teks auto-wrap (Paragraph) + lebar kolom PROPORSIONAL.

    headers   : list[str]
    rows      : list[list] (nilai mentah)
    weights   : list[float] bobot relatif lebar per kolom (default rata)
    right_cols: iterable index kolom rata-kanan (kolom angka)
    total_row : True → baris terakhir diberi gaya TOTAL
    page      : 'landscape' untuk lebar halaman lebih besar
    style     : (SESI #19) gaya dari template PDF pemilik (header_bg/zebra/grid/font_size)
    """
    from reportlab.platypus import Paragraph, Table
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_RIGHT
    from reportlab.lib import colors

    n = len(headers)
    right = set(right_cols or [])
    avail = content_width(page)
    if not weights or len(weights) != n:
        weights = [1] * n
    tot = float(sum(weights)) or 1.0
    col_w = [avail * (w / tot) for w in weights]

    # FASE H-7 (2026-08-16): `leading` dinaikkan 9,5 → 10,8 pt.
    # Sebab yang terukur: pada sel yang teksnya MELIPAT ke baris kedua, kotak glyph
    # ReportLab setinggi ±10,3 pt sedangkan jarak antarbaris hanya 9,5 pt ⇒ dua baris
    # dalam SATU sel saling tumpang tindih ±0,8 pt. Tidak terlihat mata, tetapi itu
    # tetap tumpang tindih sungguhan (terdeteksi penjaga INV-F17 yang mengukur bbox
    # PDF jadi) dan pada font/ukuran lain bisa benar-benar bertabrakan.
    # 10,8 = 1,44 × ukuran font — cukup untuk semua sel yang melipat, tanpa membuat
    # tabel jadi tinggi berlebihan.
    _LEAD = 10.8
    # SESI #19 — ukuran font boleh diatur pemilik, TETAPI `leading` selalu dihitung
    # 1,44 × ukuran font. Menyetel font lebih besar tanpa menaikkan leading adalah
    # cacat yang sudah pernah terjadi (sesi #16: tumpang tindih 0,8 pt di SEMUA
    # dokumen) dan dijaga penjaga INV-F17. Jadi angkanya diturunkan, bukan diketik.
    try:
        _fs = float((style or {}).get('font_size') or 7.5)
    except (TypeError, ValueError):
        _fs = 7.5
    _fs = max(6.0, min(10.0, _fs))
    _LEAD = round(_fs * 1.44, 2)
    cellL = ParagraphStyle('cL', fontSize=_fs, leading=_LEAD, wordWrap='LTR')
    cellR = ParagraphStyle('cR', fontSize=_fs, leading=_LEAD, alignment=TA_RIGHT, wordWrap='LTR')
    hL = ParagraphStyle('hL', fontSize=_fs, leading=_LEAD, fontName='Helvetica-Bold', textColor=colors.white)
    hR = ParagraphStyle('hR', fontSize=_fs, leading=_LEAD, fontName='Helvetica-Bold', textColor=colors.white, alignment=TA_RIGHT)

    def esc(v):
        return str(v if v is not None else '').replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')

    body = [[Paragraph(esc(h), hR if i in right else hL) for i, h in enumerate(headers)]]
    for r in rows:
        body.append([Paragraph(esc(c), cellR if i in right else cellL) for i, c in enumerate(r)])
    t = Table(body, colWidths=col_w, repeatRows=1)
    t.setStyle(_pdf_table_style(style))
    if total_row:
        t.setStyle(_pdf_total_row_style())
    return t


def _build_pdf(buf, elements, page=None):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    ps = landscape(A4) if page == 'landscape' else A4
    doc = SimpleDocTemplate(buf, pagesize=ps, leftMargin=12*mm, rightMargin=12*mm, topMargin=12*mm, bottomMargin=12*mm)
    doc.build(elements)
    buf.seek(0)
    return buf


def _pdf_header(elements, company_name, title, subtitle=None, info_pairs=None,
                avail=CONTENT_W_PORTRAIT):
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.units import mm
    styles = _pdf_styles()
    elements.append(Paragraph(f"<b>{company_name}</b>", styles['Title']))
    elements.append(Paragraph(title, styles['Heading2']))
    if subtitle:
        elements.append(Paragraph(subtitle, styles['Normal']))
    elements.append(Spacer(1, 4*mm))
    if info_pairs:
        _pdf_info_pairs(elements, info_pairs, avail=avail)
    return elements


def _pdf_footer(elements):
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import mm
    styles = _pdf_styles()
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(f"<i>Generated: {now_wib().strftime('%d/%m/%Y %H:%M')}</i>", styles['Normal']))
    return elements


# ─── Branded helpers (PDF unified branding + configurable signatures) ─────────
# Additive — dipakai HANYA oleh generator surat jalan (vendor/buyer shipment) agar
# konsisten dengan framework `utils/pdf_common.py` (payslip & SJ SSOT). Tidak
# mengubah `_pdf_header`/`_pdf_footer` lama supaya generator lain tak terpengaruh.

def _pdf_header_branded(elements, profile, doc_settings, title, info_pairs=None, avail=CONTENT_W_PORTRAIT):
    """Header dokumen dengan profil perusahaan dinamis (kop) + judul.

    profile      : dict dari utils.pdf_common.get_company_profile()
    doc_settings : dict dari utils.pdf_common.get_doc_settings() (header_line1/2, show_logo)
    avail        : lebar konten (CONTENT_W_PORTRAIT / CONTENT_W_LANDSCAPE)

    SESI #19 — bila `doc_settings` membawa `_template` (template PDF pemilik dari
    koleksi `pdf_templates`), kop digambar oleh `core.pdf_template.header_flowables`
    sehingga LOGO, NPWP/telepon, tata letak, dan perataan yang diatur pemilik
    benar-benar tercetak. Tanpa template, jalur lama di bawah tetap dipakai —
    dokumen yang belum diatur tidak berubah penampilannya.
    """
    from reportlab.platypus import Paragraph, Spacer, Table, TableStyle
    from reportlab.lib import colors
    profile = profile or {}
    doc_settings = doc_settings or {}

    tpl = doc_settings.get('_template') or {}
    if tpl.get('header'):
        from core.pdf_template import header_flowables
        elements.extend(header_flowables(
            tpl['header'], profile, title, info_pairs=info_pairs, avail=avail))
        return elements

    styles = _pdf_styles()

    company_name = (doc_settings.get('header_line1') or profile.get('company_name') or 'CV. Dewi Aditya')
    elements.append(Paragraph(f"<b>{_safe_str(company_name, 80)}</b>", styles['Title']))

    line2 = doc_settings.get('header_line2') or profile.get('address') or profile.get('tagline') or ''
    if line2:
        elements.append(Paragraph(_safe_str(line2, 120), styles['Normal']))

    contact_bits = []
    if profile.get('phone'):
        contact_bits.append(f"Telp: {profile['phone']}")
    if profile.get('email'):
        contact_bits.append(str(profile['email']))
    if profile.get('website'):
        contact_bits.append(str(profile['website']))
    if profile.get('npwp'):
        contact_bits.append(f"NPWP: {profile['npwp']}")
    if contact_bits:
        elements.append(Paragraph(_safe_str(' | '.join(contact_bits), 150), styles['Normal']))

    # garis pemisah kop
    hr = Table([['']], colWidths=[avail])
    hr.setStyle(TableStyle([('LINEBELOW', (0, 0), (-1, -1), 0.8, colors.HexColor('#334155'))]))
    elements.append(hr)

    elements.append(Paragraph(f"<b>{title}</b>", styles['Heading2']))

    if info_pairs:
        from reportlab.platypus import Spacer
        from reportlab.lib.units import mm
        elements.append(Spacer(1, 2 * mm))
        _pdf_info_pairs(elements, info_pairs, avail=avail)
    return elements


def _pdf_signature_block(elements, doc_settings, context, max_cols=3, page=None):
    """Blok tanda tangan configurable dari doc_settings['signatures'].

    Menghormati show_signatures. Nama penandatangan ditentukan via
    utils.pdf_common.resolve_signature_name (custom / dari field / kosong).

    FASE F: lebar kolom mengikuti LEBAR KONTEN halaman (`page`), bukan angka
    ajaib 500 pt. Di halaman landscape blok tanda tangan dulu menumpuk di kiri
    dan menyisakan ruang kosong lebar di kanan.

    SESI #19: bila ada `_template`, blok digambar `core.pdf_template.signature_flowables`
    — bentuknya SUBJECT / ruang kosong / NAMA / catatan sesuai permintaan pemilik, dan
    blok ke-4 dan seterusnya TURUN KE BARIS BERIKUTNYA alih-alih hilang dipotong
    `max_cols` (dulu blok keempat lenyap tanpa pesan apa pun).
    """
    from reportlab.platypus import Spacer, Table, TableStyle
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from utils.pdf_common import resolve_signature_name

    doc_settings = doc_settings or {}
    tpl = doc_settings.get('_template') or {}
    if tpl.get('signatures'):
        from core.pdf_template import content_width as _cw
        from core.pdf_template import signature_flowables
        elements.extend(signature_flowables(tpl['signatures'], context or {},
                                            avail=_cw(page)))
        return elements

    if not doc_settings.get('show_signatures', True):
        return elements
    sigs = list(doc_settings.get('signatures') or [])[:max_cols]
    if not sigs:
        return elements

    labels, names, roles = [], [], []
    for sd in sigs:
        labels.append(_safe_str(sd.get('label', ''), 30))
        nm = resolve_signature_name(sd, context or {})
        names.append(f"( {nm} )" if nm else "( ............................ )")
        roles.append(_safe_str(sd.get('role_label', ''), 30))

    n = len(sigs)
    col_w = [content_width(page) / n] * n
    sig_data = [labels, [''] * n, names, roles]
    elements.append(Spacer(1, 14 * mm))
    st = Table(sig_data, colWidths=col_w)
    st.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTSIZE', (0, 0), (-1, 0), 9),
        ('FONTSIZE', (0, 2), (-1, 2), 9),
        ('FONTSIZE', (0, 3), (-1, 3), 7),
        ('TEXTCOLOR', (0, 3), (-1, 3), colors.HexColor('#64748b')),
        ('TOPPADDING', (0, 1), (-1, 1), 16),
        ('TOPPADDING', (0, 3), (-1, 3), 1),
    ]))
    elements.append(st)
    return elements


def _pdf_footer_branded(elements, profile=None, doc_settings=None):
    """Footer dengan teks footer perusahaan (bila ada) + timestamp generate."""
    from reportlab.platypus import Paragraph, Spacer
    from reportlab.lib.units import mm
    profile = profile or {}
    doc_settings = doc_settings or {}
    tpl = doc_settings.get('_template') or {}
    if tpl.get('footer'):
        from core.pdf_template import footer_flowables
        elements.extend(footer_flowables(tpl['footer'], profile))
        return elements
    styles = _pdf_styles()
    elements.append(Spacer(1, 8 * mm))
    footer_text = doc_settings.get('footer_text') or profile.get('pdf_footer_text') or ''
    if footer_text:
        elements.append(Paragraph(_safe_str(footer_text, 160), styles['Normal']))
    elements.append(Paragraph(
        f"<i>Dicetak: {now_wib().strftime('%d/%m/%Y %H:%M')}</i>", styles['Normal']))
    return elements


def _safe_str(v, max_len=40):
    s = str(v or '')
    return s[:max_len] if len(s) > max_len else s


async def enrich_with_product_photos(items, db):
    """Add product photo_url to items that have a product_name. Single batch query."""
    if not items:
        return items
    pnames = list({(it.get('product_name') or '').strip() for it in items if it.get('product_name')})
    photos = {}
    if pnames:
        prods = await db.products.find(
            {'product_name': {'$in': pnames}}, {'_id': 0, 'product_name': 1, 'photo_url': 1}
        ).to_list(500)
        photos = {p['product_name']: p.get('photo_url', '') for p in prods}
    for item in items:
        if item.get('product_name'):
            item['product_photo'] = photos.get(item['product_name'], '')
    return items


# ─── PDF Export Config Helpers ───────────────────────────────────────────────
async def _get_pdf_config(db, pdf_type, config_id=None, cols=None):
    """Konfigurasi kolom PDF: pilihan SEKALI-CETAK (`cols`) > konfigurasi bernama > default.

    W2 (sesi #29, permintaan pemilik: *"untuk produksi ada data no serial namun di
    pdf tidak ada pilihannya, jadi saya ingin semua data collection bisa di export
    juga dan bisa di pilih user"*).

    Sebelum ini kolom HANYA bisa diatur lewat layar setelan (template PDF /
    `pdf_export_configs` bernama) — jadi pemakai yang sedang mencetak satu dokumen
    tidak punya cara memilih kolomnya, dan kolom **Serial No** yang sudah ada di
    registry tidak pernah muncul sebagai pilihan di layar cetak.

    Sekarang layar boleh mengirim `?cols=serial,product,qty` untuk SEKALI cetak:
      * kunci divalidasi terhadap SSOT `data/pdf_doc_registry` — kunci karangan
        diabaikan (bukan error) supaya tautan lama/typo tidak menggagalkan cetakan;
      * kolom WAJIB (`required`) selalu disertakan walau tidak dicentang, karena
        tanpa nomor baris dokumennya tidak bisa dibaca;
      * bila tidak ada satu pun kunci sah → kembali ke perilaku lama (template/default).
    """
    if cols:
        from data.pdf_doc_registry import columns_of, required_keys
        wanted = [c.strip() for c in str(cols).split(",") if c.strip()]
        known = [c["key"] for c in columns_of(pdf_type)]
        picked = [k for k in known if k in set(wanted)]          # urutan mengikuti SSOT
        for r in required_keys(pdf_type):                        # kolom wajib tetap ikut
            if r not in picked and r in known:
                picked.insert(known.index(r) if known.index(r) < len(picked) else len(picked), r)
        if picked:
            return {"pdf_type": pdf_type, "name": "pilihan sekali cetak",
                    "columns": picked, "_adhoc": True}
    if config_id:
        cfg = await db.pdf_export_configs.find_one({'id': config_id}, {'_id': 0})
        if cfg:
            return cfg
    # Try default for this type
    cfg = await db.pdf_export_configs.find_one({'pdf_type': pdf_type, 'is_default': True}, {'_id': 0})
    return cfg


def _filter_columns(headers, all_col_keys, selected_keys, data_rows):
    """Filter table columns based on selected keys from config."""
    if not selected_keys:
        return headers, data_rows
    indices = [i for i, k in enumerate(all_col_keys) if k in selected_keys]
    if not indices:
        return headers, data_rows
    new_headers = [headers[i] for i in indices]
    new_rows = [[row[i] if i < len(row) else '' for i in indices] for row in data_rows]
    return new_headers, new_rows


# ─── KOLOM DARI TEMPLATE PDF (SESI #19) ──────────────────────────────────────
async def tpl_table_parts(db, doc_key, all_col_keys, all_headers, data_rows, *,
                          weight_map=None, numeric_keys=(), config=None):
    """Susunan tabel yang BENAR-BENAR diminta pemilik: tampil/tidak + URUTAN + lebar.

    Menggantikan pasangan `_get_pdf_config` + `_filter_columns` yang hanya bisa
    MENYEMBUNYIKAN kolom (urutan selalu urutan kode, kolom baru tidak mungkin).

    `config` = konfigurasi kolom WARISAN (`pdf_export_configs`) yang masih boleh
    dikirim lewat `?config_id=`; bila ada, ia menang supaya tautan lama yang menunjuk
    satu konfigurasi bernama tetap menghasilkan dokumen yang sama seperti dulu.

    Kembalian: (headers, rows, keys, weights, right_cols, doc_settings)
    """
    from core.pdf_template import apply_columns, column_weights
    from data.pdf_doc_registry import weights_of
    from utils.pdf_common import get_doc_settings

    doc_settings = await get_doc_settings(db, doc_key)
    tpl = (doc_settings or {}).get('_template') or {}
    tpl_cols = tpl.get('columns') or []

    if config and config.get('columns'):
        headers, rows = _filter_columns(all_headers, all_col_keys, config['columns'], data_rows)
        keys = [k for k in all_col_keys if k in set(config['columns'])]
    else:
        headers, rows, keys = apply_columns(tpl_cols, all_col_keys, all_headers, data_rows)

    fallback = dict(weights_of(doc_key))
    fallback.update(weight_map or {})
    weights = column_weights(tpl_cols, keys, fallback)
    right = []
    by_key = {c.get('key'): c for c in tpl_cols}
    for i, k in enumerate(keys):
        al = (by_key.get(k) or {}).get('align')
        if al == 'right' or (al in (None, '', 'left') and k in set(numeric_keys)):
            right.append(i)
    return headers, rows, keys, weights, right, doc_settings
