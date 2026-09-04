"""
Generator PDF untuk Lembar Kerja Produksi (LKP) PT Rahaza ERP.
Menggunakan reportlab. A4 portrait, multi-page, Bahasa Indonesia.

Sections (sesuai brief):
  A. Header / Identitas Dokumen (logo, judul, no LKP, QR, tanggal cetak, status, versi)
  B. Informasi Order & WO
  C. Informasi Produk / Style (foto, tech pack, size chart)
  D. Bill of Materials (BOM) — tabel benang & aksesoris
  E. Assignment & Resource (lini, mesin, operator, shift, target)
  F. Urutan Proses (Rajut → Linking → Sewing → Steam → QC → Packing)
  G. SOP / Work Instruction per proses
  H. Quality Control Checkpoints (defect codes, AQL, toleransi)
  I. Packing & Finishing Instruction
  J. Signature / Approval Block
  K. Catatan Khusus
  L. Footer (halaman X dari Y, kontak quick, QR feedback)

Security patches:
  H5: All user-supplied text is escaped via xml.sax.saxutils.escape before
      being passed to ReportLab Paragraph (prevents HTML injection in PDF).
  L1: Unused imports removed (getSampleStyleSheet, KeepTogether, PageBreak, TA_RIGHT, TA_JUSTIFY).
  L5: Dead class _LKPPageMixin removed.
"""
import logging
import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape as _xml_escape  # H5

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    BaseDocTemplate, Frame, PageTemplate, Paragraph, Spacer, Table, TableStyle,
    Image as RLImage,
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER

try:
    import qrcode
    QR_AVAILABLE = True
except Exception:
    QR_AVAILABLE = False


# H5: Escape helper — prevents HTML injection in Paragraph content
def _safe(value) -> str:
    """Escape user-supplied text before inserting into ReportLab Paragraph."""
    return _xml_escape(str(value or "")).replace("\n", "<br/>")


# ─── Color Palette ──────────────────────────────────────────────────────
PRIMARY = colors.HexColor("#0f4c81")  # navy
ACCENT = colors.HexColor("#d97706")  # amber
LIGHT_BG = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#cbd5e1")
TEXT_MUTED = colors.HexColor("#475569")
PRIORITY_COLOR = {
    "normal": colors.HexColor("#64748b"),
    "high":   colors.HexColor("#d97706"),
    "urgent": colors.HexColor("#dc2626"),
}


# ─── Styles ─────────────────────────────────────────────────────────────
def _styles():
    styles = {
        "title":      ParagraphStyle("title",      fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=PRIMARY, alignment=TA_LEFT),
        "subtitle":   ParagraphStyle("subtitle",   fontName="Helvetica",      fontSize=9,  leading=11, textColor=TEXT_MUTED, alignment=TA_LEFT),
        "h1":         ParagraphStyle("h1",         fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=PRIMARY,  spaceBefore=8, spaceAfter=4),
        "h2":         ParagraphStyle("h2",         fontName="Helvetica-Bold", fontSize=10, leading=13, textColor=PRIMARY,  spaceBefore=4, spaceAfter=2),
        "body":       ParagraphStyle("body",       fontName="Helvetica",      fontSize=9,  leading=12, textColor=colors.black),
        "body_small": ParagraphStyle("body_small", fontName="Helvetica",      fontSize=8,  leading=10, textColor=colors.black),
        "muted":      ParagraphStyle("muted",      fontName="Helvetica",      fontSize=8,  leading=10, textColor=TEXT_MUTED),
        "kv_label":   ParagraphStyle("kv_label",   fontName="Helvetica-Bold", fontSize=9,  leading=11, textColor=TEXT_MUTED),
        "kv_value":   ParagraphStyle("kv_value",   fontName="Helvetica",      fontSize=9,  leading=11, textColor=colors.black),
        "badge":      ParagraphStyle("badge",      fontName="Helvetica-Bold", fontSize=8,  leading=10, textColor=colors.white, alignment=TA_CENTER),
        "footer":     ParagraphStyle("footer",     fontName="Helvetica",      fontSize=7,  leading=9,  textColor=TEXT_MUTED, alignment=TA_CENTER),
    }
    return styles


# ─── QR Code helper ─────────────────────────────────────────────────────
def _qr_image(data: str, size_mm: int = 22):
    if not QR_AVAILABLE:
        return None
    try:
        img = qrcode.make(data)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        return RLImage(bio, width=size_mm * mm, height=size_mm * mm)
    except Exception:
        return None


# ─── PageTemplate w/ header & footer ────────────────────────────────────
def _draw_header_footer(canv: canvas.Canvas, doc, meta: dict):
    canv.saveState()
    width, height = A4

    # Header strip
    canv.setFillColor(PRIMARY)
    canv.rect(0, height - 18 * mm, width, 18 * mm, fill=1, stroke=0)

    # Logo / company text (trusted — comes from company_settings, not raw user input)
    canv.setFillColor(colors.white)
    canv.setFont("Helvetica-Bold", 14)
    canv.drawString(15 * mm, height - 10 * mm, meta.get("company_name", "PT RAHAZA GLOBAL INDONESIA"))
    canv.setFont("Helvetica", 8)
    canv.drawString(15 * mm, height - 14 * mm, meta.get("company_addr", "Knit Garment Manufacturing — Production Work Sheet"))

    # Right header: LKP number & date
    canv.setFont("Helvetica-Bold", 9)
    canv.drawRightString(width - 15 * mm, height - 8 * mm, f"NO. {meta.get('lkp_number', '-')}")
    canv.setFont("Helvetica", 8)
    canv.drawRightString(width - 15 * mm, height - 12 * mm, f"Versi {meta.get('version', 1)}  ·  {meta.get('print_date', '')}")
    canv.drawRightString(width - 15 * mm, height - 15.5 * mm, f"Status: {meta.get('status_label', 'RELEASED')}")

    # Footer
    canv.setStrokeColor(BORDER)
    canv.setLineWidth(0.5)
    canv.line(15 * mm, 15 * mm, width - 15 * mm, 15 * mm)
    canv.setFont("Helvetica", 7)
    canv.setFillColor(TEXT_MUTED)
    page_num = canv.getPageNumber()
    canv.drawString(15 * mm, 10 * mm, f"WO: {meta.get('wo_number', '-')}  ·  Customer: {meta.get('customer', '-')}  ·  Model: {meta.get('model', '-')}")
    canv.drawCentredString(width / 2, 10 * mm, "Dokumen ini bersifat resmi. Mohon dijaga & dikembalikan ke leader saat shift berakhir.")
    canv.drawRightString(width - 15 * mm, 10 * mm, f"Halaman {page_num}")
    canv.drawString(15 * mm, 6.5 * mm, f"Kontak: Supervisor Lini · PPIC  ·  Cetakan: {meta.get('printed_by', '-')}")

    canv.restoreState()


# ─── Section builders ──────────────────────────────────────────────────
def _kv_table(rows, col_widths=None, label_color=TEXT_MUTED):
    """Helper: 2-column key/value table."""
    style = TableStyle([
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TEXTCOLOR", (0, 0), (0, -1), label_color),
        ("FONTNAME", (1, 0), (1, -1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
    ])
    cw = col_widths or [40 * mm, 60 * mm]
    return Table(rows, colWidths=cw, style=style)


def _section_header(text, styles):
    """Blue bar section header."""
    p = Paragraph(f"<b>{text}</b>", styles["h1"])
    t = Table([[p]], colWidths=[180 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT_BG),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBEFORE", (0, 0), (0, -1), 3, PRIMARY),
    ]))
    return t


def _priority_badge(priority: str, styles):
    p = (priority or "normal").lower()
    color = PRIORITY_COLOR.get(p, TEXT_MUTED)
    label = {"normal": "NORMAL", "high": "HIGH", "urgent": "URGENT"}.get(p, p.upper())
    para = Paragraph(label, ParagraphStyle("badge_p", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, alignment=TA_CENTER, leading=10))
    return Table([[para]], colWidths=[20 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), color),
        ("BOX", (0, 0), (-1, -1), 0, color),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))


def _build_section_b(content, styles):
    """B. Informasi Order & WO."""
    wo = content.get("work_order") or {}
    order = content.get("order") or {}
    rows = [
        ["No. Work Order:", wo.get("wo_number", "-")],
        ["No. Order:", order.get("order_number") or "Manual / Internal"],
        ["Customer / Buyer:", order.get("customer_name", "-")],
        ["Tanggal Order:", order.get("order_date", "-")],
        ["Target Mulai:", wo.get("target_start_date", "-")],
        ["Due Date / Deadline:", wo.get("target_end_date", "-")],
        ["Total Quantity:", f"{wo.get('qty', 0)} pcs"],
        ["Size:", wo.get("size_code", "-")],
    ]
    kv = _kv_table(rows, col_widths=[42 * mm, 60 * mm])

    # Priority badge
    prio_table = Table(
        [[Paragraph("<b>Prioritas</b>", styles["kv_label"]), _priority_badge(wo.get("priority", "normal"), styles)]],
        colWidths=[40 * mm, 25 * mm]
    )
    return [
        _section_header("B. INFORMASI ORDER & WORK ORDER", styles),
        Spacer(1, 3 * mm),
        Table([[kv, prio_table]], colWidths=[110 * mm, 70 * mm], style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])),
        Spacer(1, 4 * mm),
    ]


def _build_section_c(content, styles, image_files):
    """C. Informasi Produk / Style — foto + tech pack."""
    model = content.get("model") or {}
    tech = content.get("tech_pack") or {}
    rows = [
        ["Kode Model:", model.get("code", "-")],
        ["Nama Model:", model.get("name", "-")],
        ["Kategori:", model.get("category", "-")],
        # H5: tech pack fields may come from user
        ["Warna Utama:", _safe(tech.get("color", "-"))],
        ["Color Code / Lot Benang:", _safe(tech.get("color_code", "-"))],
        ["Gauge:", _safe(tech.get("gauge", "-"))],
        ["Berat per pcs (target):", _safe(tech.get("weight_per_pcs", "-"))],
        ["Knit Structure:", _safe(tech.get("knit_structure", "-"))],
    ]
    info_kv = _kv_table(rows, col_widths=[45 * mm, 60 * mm])

    # Image grid (1-3 foto, max width 50mm each)
    img_cells = []
    for f in (image_files or [])[:3]:
        try:
            img = RLImage(f, width=45 * mm, height=45 * mm, kind="proportional")
            img_cells.append(img)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
    if not img_cells:
        img_cells = [Paragraph("<i>(Foto produk belum diupload pada master Model)</i>", styles["muted"])]

    img_table = Table([img_cells], colWidths=[50 * mm] * len(img_cells), style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    # Size chart / measurement — H5: escape user-supplied part/value
    measure_rows = tech.get("measurements") or []
    measure_block = []
    if measure_rows:
        m_data = [["Bagian", "Toleransi (cm)"]] + [
            [_safe(m.get("part", "")), _safe(m.get("value", ""))] for m in measure_rows
        ]
        m_tbl = Table(m_data, colWidths=[55 * mm, 50 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        measure_block = [Spacer(1, 3 * mm), Paragraph("<b>Size Chart / Measurement</b>", styles["h2"]), m_tbl]

    return [
        _section_header("C. INFORMASI PRODUK / STYLE", styles),
        Spacer(1, 3 * mm),
        Table([[info_kv, img_table]], colWidths=[110 * mm, 70 * mm], style=TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ])),
        *measure_block,
        Spacer(1, 4 * mm),
    ]


def _build_section_d(content, styles):
    """D. Bill of Materials (Phase 7A Fase 1 — unified materials[])."""
    bom = content.get("bom_snapshot") or {}
    qty = int((content.get("work_order") or {}).get("qty") or 0)

    # Normalisasi ke daftar terunifikasi (dukung snapshot lama & materials[] baru)
    kg_types = ("yarn", "fabric", "kain", "benang", "interlining")
    lines = []
    mats = bom.get("materials")
    if isinstance(mats, list) and mats:
        for m in mats:
            is_kg = (m.get("unit") == "kg") or str(m.get("material_type") or "").lower() in kg_types
            lines.append({
                "name": m.get("name") or m.get("material_name") or "-",
                "cat": m.get("category_name") or (m.get("material_type") or ("Kain/Benang" if is_kg else "Aksesoris")),
                "per": float(m.get("qty") or 0),
                "unit": m.get("unit") or ("kg" if is_kg else "pcs"),
                "is_kg": is_kg,
            })
    else:
        for y in bom.get("yarn_materials") or []:
            lines.append({"name": y.get("material_name") or y.get("name") or "-",
                          "cat": y.get("category_name") or y.get("type") or "Benang",
                          "per": float(y.get("kg_per_pcs") or y.get("qty_kg") or 0),
                          "unit": "kg", "is_kg": True})
        for a in bom.get("accessory_materials") or []:
            lines.append({"name": a.get("material_name") or a.get("name") or "-",
                          "cat": a.get("category_name") or "Aksesoris",
                          "per": float(a.get("qty_per_pcs") or a.get("qty") or 0),
                          "unit": a.get("unit") or "pcs", "is_kg": False})

    data = [["#", "Material", "Kategori", "Qty/pcs", f"Total (×{qty})", "Unit"]]
    for i, ln in enumerate(lines, start=1):
        total = ln["per"] * qty
        per_s = f"{ln['per']:.4f}" if ln["is_kg"] else f"{ln['per']:.2f}"
        tot_s = f"{total:.3f}" if ln["is_kg"] else f"{total:.0f}"
        data.append([str(i), _safe(ln["name"]), _safe(ln["cat"]), per_s, tot_s, _safe(ln["unit"])])
    if len(data) == 1:
        data.append(["—", "(BOM belum di-snapshot — release WO untuk freeze)", "", "", "", ""])
    bom_tbl = Table(data, colWidths=[8 * mm, 60 * mm, 32 * mm, 22 * mm, 28 * mm, 15 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (3, 1), (4, -1), "RIGHT"),
    ]))

    checklist_text = """
    <b>☐ Material take-out checklist (Centang saat ambil dari Gudang):</b><br/>
    Operator/Leader Lini wajib memverifikasi semua material di atas tersedia secara fisik dan jumlah sesuai.
    Tanda tangan leader saat material lengkap diterima:
    """

    return [
        _section_header("D. BILL OF MATERIALS (BOM)", styles),
        Spacer(1, 3 * mm),
        Paragraph("<b>Daftar Material</b>", styles["h2"]),
        bom_tbl,
        Spacer(1, 3 * mm),
        Paragraph(checklist_text, styles["body_small"]),
        Spacer(1, 4 * mm),
    ]


def _build_section_e(content, styles):
    """E. Assignment & Resource."""
    asgn = content.get("assignment") or {}
    rows = [
        ["Lini Produksi:", asgn.get("line_name", "-")],
        ["Mesin:", asgn.get("machine_name", "-")],
        ["Gauge Mesin:", asgn.get("machine_gauge", "-")],
        ["Operator (utama):", asgn.get("operator_name", "-")],
        ["Shift:", asgn.get("shift_name", "-")],
        ["Tanggal Mulai:", asgn.get("start_date", "-")],
        ["Tanggal Selesai (estimasi):", asgn.get("end_date", "-")],
        ["Target / hari:", f"{asgn.get('daily_target', '-')} pcs"],
        ["Target / shift:", f"{asgn.get('shift_target', '-')} pcs"],
    ]
    return [
        _section_header("E. ASSIGNMENT & RESOURCE", styles),
        Spacer(1, 3 * mm),
        _kv_table(rows, col_widths=[55 * mm, 80 * mm]),
        Spacer(1, 4 * mm),
    ]


def _build_section_f(content, styles):
    """F. Urutan Proses Produksi."""
    flow = content.get("process_flow") or []
    data = [["#", "Proses", "Estimasi Durasi", "SAM (menit/pcs)", "PIC / Lini"]]
    for i, p in enumerate(flow, start=1):
        data.append([
            str(i),
            _safe(p.get("name", "-")),
            _safe(p.get("duration_estimate", "-")),
            f"{_safe(p.get('sam', '-'))}",
            _safe(p.get("line", "-")),
        ])
    if len(data) == 1:
        data.append(["—", "(Belum ada proses ter-assign)", "", "", ""])
    tbl = Table(data, colWidths=[10 * mm, 60 * mm, 35 * mm, 30 * mm, 35 * mm], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    flow_arrow = " → ".join([_safe(p.get("name", "-")) for p in flow]) or "Rajut → Linking → Sewing → Steam → QC → Packing"
    return [
        _section_header("F. URUTAN PROSES PRODUKSI", styles),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Flow:</b> {flow_arrow}", styles["body"]),
        Spacer(1, 2 * mm),
        Paragraph("<i>Catatan: Apabila QC fail → bundle ke proses REWORK → kembali ke QC.</i>", styles["muted"]),
        Spacer(1, 2 * mm),
        tbl,
        Spacer(1, 4 * mm),
    ]


def _build_section_g(content, styles):
    """G. SOP / Work Instruction per proses (KRITIS).
    H5: All user-supplied text (steps, tools, safety, acceptance_criteria, common_defects)
        is escaped via _safe() before passing to Paragraph.
    """
    sops = content.get("sop_steps") or []
    elems = [
        _section_header("G. SOP / WORK INSTRUCTION", styles),
        Spacer(1, 3 * mm),
        Paragraph("<i>Wajib dibaca operator sebelum mulai. Tanyakan ke leader bila ada yang kurang jelas.</i>", styles["muted"]),
        Spacer(1, 3 * mm),
    ]
    if not sops:
        elems.append(Paragraph("<i>(SOP belum diisi untuk WO ini.)</i>", styles["muted"]))
        elems.append(Spacer(1, 4 * mm))
        return elems
    for i, sop in enumerate(sops, start=1):
        # H5: escape process_name
        title = f"<b>{i}. {_safe(sop.get('process_name', 'Proses'))}</b>"
        elems.append(Paragraph(title, styles["h2"]))
        # Tools — H5: each item escaped
        tools = sop.get("tools") or []
        if tools:
            escaped_tools = ", ".join(_safe(t) for t in tools)
            elems.append(Paragraph(f"<b>Alat / Tools:</b> {escaped_tools}", styles["body_small"]))
        # Safety — H5
        safety = sop.get("safety") or []
        if safety:
            escaped_safety = "; ".join(_safe(s) for s in safety)
            elems.append(Paragraph(f"<b>Safety:</b> {escaped_safety}", styles["body_small"]))
        # Steps — H5: each step escaped
        steps = sop.get("steps") or []
        for j, step in enumerate(steps, start=1):
            elems.append(Paragraph(f"&nbsp;&nbsp;<b>{j}.</b> {_safe(step)}", styles["body"]))
        # Acceptance criteria — H5
        ac = sop.get("acceptance_criteria")
        if ac:
            elems.append(Spacer(1, 1 * mm))
            elems.append(Paragraph(f"<b>Kriteria Kualitas (Acceptance):</b> {_safe(ac)}", styles["body_small"]))
        # Common defects — H5
        defects = sop.get("common_defects") or []
        if defects:
            escaped_defects = ", ".join(_safe(d) for d in defects)
            elems.append(Paragraph(f"<b>Hindari Cacat Umum:</b> {escaped_defects}", styles["body_small"]))
        elems.append(Spacer(1, 3 * mm))
    elems.append(Spacer(1, 2 * mm))
    return elems


def _build_section_h(content, styles):
    """H. QC Checkpoints.
    H5: User-supplied checkpoints and defect descriptions are escaped.
    """
    qc = content.get("qc") or {}
    rows = [
        ["AQL Level:", _safe(qc.get("aql_level", "-"))],
        ["Sampling Rule:", _safe(qc.get("sampling_rule", "Sesuai master defect codes & standar internal"))],
        ["Toleransi Dimensi:", _safe(qc.get("dimensional_tolerance", "± 1 cm dari master measurement"))],
    ]
    elems = [
        _section_header("H. QUALITY CONTROL CHECKPOINTS", styles),
        Spacer(1, 3 * mm),
        _kv_table(rows, col_widths=[50 * mm, 100 * mm]),
        Spacer(1, 3 * mm),
    ]
    # Defect codes table — H5: descriptions escaped
    codes = qc.get("defect_codes_to_watch") or []
    if codes:
        data = [["Kode", "Kategori", "Severity", "Deskripsi"]]
        for c in codes:
            data.append([
                _safe(c.get("code", "-")),
                _safe(c.get("category", "-")),
                _safe(c.get("severity", "-")),
                Paragraph(_safe(c.get("description", "-")), styles["body_small"]),  # Paragraph for wrapping
            ])
        tbl = Table(data, colWidths=[20 * mm, 35 * mm, 20 * mm, 95 * mm], style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("GRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        elems.append(Paragraph("<b>Defect Codes yang Harus Diperhatikan</b>", styles["h2"]))
        elems.append(tbl)
    # Checkpoints — H5
    cps = qc.get("checkpoints") or []
    if cps:
        elems.append(Spacer(1, 2 * mm))
        elems.append(Paragraph("<b>Critical Checkpoints (centang saat dilakukan):</b>", styles["h2"]))
        for cp in cps:
            elems.append(Paragraph(f"&nbsp;&nbsp;☐  {_safe(cp)}", styles["body"]))
    elems.append(Spacer(1, 4 * mm))
    return elems


def _build_section_i(content, styles):
    """I. Packing Instruction.
    H5: All packing fields are escaped.
    """
    pk = content.get("packing") or {}
    body_text = _safe(pk.get("instruction") or "(Belum diisi.)")
    rows = [
        ["Cara Lipat:", _safe(pk.get("fold_method", "-"))],
        ["Polybag Spec:", _safe(pk.get("polybag_spec", "-"))],
        ["Hangtag Placement:", _safe(pk.get("hangtag_placement", "-"))],
        ["Qty per Carton:", _safe(str(pk.get("qty_per_carton", "-")))],
        ["Carton Spec:", _safe(pk.get("carton_spec", "-"))],
        ["Shipping Mark:", _safe(pk.get("shipping_mark", "-"))],
    ]
    return [
        _section_header("I. PACKING & FINISHING INSTRUCTION", styles),
        Spacer(1, 3 * mm),
        _kv_table(rows, col_widths=[45 * mm, 110 * mm]),
        Spacer(1, 2 * mm),
        Paragraph(f"<b>Instruksi tambahan:</b> {body_text}", styles["body_small"]),
        Spacer(1, 4 * mm),
    ]


def _build_section_j(styles):
    """J. Signature / Approval Block."""
    cells = [
        [Paragraph("<b>Disiapkan oleh<br/>(PPIC)</b>", styles["body_small"]),
         Paragraph("<b>Disetujui oleh<br/>(Supervisor / Manager)</b>", styles["body_small"]),
         Paragraph("<b>Diterima oleh<br/>(Leader Lini)</b>", styles["body_small"]),
         Paragraph("<b>Operator Pelaksana<br/>(saat selesai shift)</b>", styles["body_small"])],
        [Paragraph("<br/><br/><br/>(.....................)<br/>Tgl: ...........", styles["body_small"])] * 4,
    ]
    tbl = Table(cells, colWidths=[45 * mm] * 4, style=TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return [
        _section_header("J. SIGNATURE / APPROVAL", styles),
        Spacer(1, 3 * mm),
        tbl,
        Spacer(1, 4 * mm),
    ]


def _build_section_k(content, styles):
    """K. Catatan Khusus.
    H5: special_notes is escaped.
    """
    notes = _safe(content.get("special_notes") or "(Tidak ada catatan khusus.)")
    return [
        _section_header("K. CATATAN KHUSUS & INSTRUKSI TAMBAHAN", styles),
        Spacer(1, 3 * mm),
        Paragraph(notes, styles["body"]),
        Spacer(1, 4 * mm),
    ]


def _build_section_l_production_photos(content, styles, production_image_files=None):
    """L. Foto Produksi & QC — foto yang diupload ke LKP (QC check, defect evidence, progress)."""
    photos = production_image_files or []
    if not photos:
        return []  # Jika tidak ada foto, section ini tidak muncul di PDF

    cells = []
    captions = content.get("production_photo_captions") or []

    for idx, img_buf in enumerate(photos[:6]):  # max 6 foto per halaman (3x2)
        try:
            img = RLImage(img_buf, width=55 * mm, height=45 * mm, kind="proportional")
            caption_txt = captions[idx] if idx < len(captions) else f"Foto {idx + 1}"
            cell_content = [img, Paragraph(_safe(caption_txt), styles["body_small"])]
            cells.append(cell_content)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    if not cells:
        return []

    # Arrange in 3-column grid
    rows = []
    for i in range(0, len(cells), 3):
        row = cells[i:i + 3]
        while len(row) < 3:
            row.append("")
        rows.append(row)

    photo_table = Table(
        rows,
        colWidths=[60 * mm] * 3,
        style=TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.3, BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.3, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ])
    )
    return [
        _section_header("L. FOTO PRODUKSI & QC", styles),
        Spacer(1, 3 * mm),
        photo_table,
        Spacer(1, 4 * mm),
    ]


# ─── Main entry point ───────────────────────────────────────────────────
def build_lkp_pdf(content: dict, image_files=None, production_image_files=None) -> bytes:
    """
    Build LKP PDF from content dict. Returns bytes.

    `content` structure: (same as before, plus:)
      "production_photo_captions": ["QC Check 1", "Defect Detail", ...] — optional captions
    """
    buf = io.BytesIO()
    styles = _styles()

    meta = {
        "lkp_number": content.get("lkp_number", "-"),
        "version": content.get("version", 1),
        "status_label": content.get("status_label", "RELEASED"),
        "print_date": content.get("print_date", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        "printed_by": content.get("printed_by", "-"),
        "company_name": content.get("company_name", "PT RAHAZA GLOBAL INDONESIA"),
        "company_addr": content.get("company_addr", "Knit Garment Manufacturing — Production Work Sheet"),
        "wo_number": (content.get("work_order") or {}).get("wo_number", "-"),
        "customer": (content.get("order") or {}).get("customer_name", "-"),
        "model": (content.get("model") or {}).get("name", "-"),
    }

    doc = BaseDocTemplate(
        buf, pagesize=A4,
        leftMargin=15 * mm, rightMargin=15 * mm,
        topMargin=22 * mm, bottomMargin=18 * mm,
        title=f"LKP {meta['lkp_number']}",
    )
    frame = Frame(15 * mm, 18 * mm, doc.width, doc.height, id="main", showBoundary=0)
    template = PageTemplate(
        id="main",
        frames=[frame],
        onPage=lambda c, d, m=meta: _draw_header_footer(c, d, m),
    )
    doc.addPageTemplates([template])

    # ─ Build story ─
    story = []

    # A. Header band — judul & QR
    title_para = Paragraph("<b>LEMBAR KERJA PRODUKSI</b>", styles["title"])
    sub_para = Paragraph(
        f"Production Work Sheet · {meta['lkp_number']} · Versi {meta['version']}<br/>"
        f"Dicetak: {meta['print_date']} · Oleh: {meta['printed_by']}",
        styles["subtitle"]
    )
    qr = _qr_image(content.get("qr_data") or meta["lkp_number"], size_mm=24)
    title_block = [[title_para, qr or ""]]
    title_tbl = Table(title_block, colWidths=[150 * mm, 30 * mm], style=TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    story.append(title_tbl)
    story.append(sub_para)
    story.append(Spacer(1, 4 * mm))

    # B–K
    story.extend(_build_section_b(content, styles))
    story.extend(_build_section_c(content, styles, image_files))
    story.extend(_build_section_d(content, styles))
    story.extend(_build_section_e(content, styles))
    story.extend(_build_section_f(content, styles))
    story.extend(_build_section_g(content, styles))
    story.extend(_build_section_h(content, styles))
    story.extend(_build_section_i(content, styles))
    story.extend(_build_section_j(styles))
    story.extend(_build_section_k(content, styles))
    story.extend(_build_section_l_production_photos(content, styles, production_image_files))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
