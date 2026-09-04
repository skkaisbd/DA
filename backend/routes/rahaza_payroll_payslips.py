# ruff: noqa: F401
"""
rahaza_payroll_payslips.py — Payslip Management & PDF
Extracted from rahaza_payroll.py (1539 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #4
Endpoints: GET /payslips, GET /payslips/{id}, PUT /payslips/{id}, GET /payslips/{id}/pdf
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_payroll_shared import (
    _uid, _now, VALID_SCHEMES, VALID_PERIOD_TYPES, VALID_RUN_STATUS,
    _get_applicable_allowances, _require_hr,
    _payslip_totals, _recompute_run_totals,
)
from routes.rahaza_posting import post_payroll_run
from utils.saga import SagaExecutor
from utils.pdf_common import get_company_profile, get_doc_settings, resolve_signature_name
import uuid
import io
import csv
import logging
from datetime import datetime, timezone, date, timedelta
from typing import Optional

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rahaza", tags=["rahaza-payroll-payslips"])

# ─── PDF helpers ────────────────────────────────────────────────────────────────

def _idr(n):
    """Format angka ke Rupiah Indonesia, contoh: 1500000 → Rp 1.500.000"""
    try:
        n = int(round(float(n or 0)))
    except Exception:
        n = 0
    return f"Rp {n:,}".replace(",", ".")


def _build_payslip_pdf(slip: dict, run: dict, profile: dict = None, doc_settings: dict = None) -> io.BytesIO:
    """
    Generate satu halaman slip gaji (A5) untuk satu karyawan.
    Mengembalikan BytesIO berisi PDF.
    profile/doc_settings (opsional) → branding perusahaan + konfigurasi tanda tangan.
    """
    profile = profile or {}
    doc_settings = doc_settings or {}
    _company_name = (profile.get("company_name") or "CV. DEWI ADITYA")
    _company_sub = (profile.get("tagline") or profile.get("address") or "Industri Garmen")
    from reportlab.lib.pagesizes import A5
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        HRFlowable,
    )

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A5,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=10 * mm,
        bottomMargin=10 * mm,
    )

    W = A5[0] - 24 * mm  # usable width

    # ── styles ────────────────────────────────────────────────────────────────
    getSampleStyleSheet()
    NAVY   = colors.HexColor("#1a2a4a")
    TEAL   = colors.HexColor("#0f6b8e")
    LIGHT  = colors.HexColor("#f0f6fa")
    GREY   = colors.HexColor("#6b7280")
    BLACK  = colors.black
    WHITE  = colors.white
    GREEN  = colors.HexColor("#1a7a4a")
    RED    = colors.HexColor("#b91c1c")

    h1  = ParagraphStyle("h1",  fontSize=13, fontName="Helvetica-Bold",  textColor=NAVY,  leading=16)
    ParagraphStyle("h2",  fontSize=9,  fontName="Helvetica",       textColor=TEAL,  leading=12)
    h3  = ParagraphStyle("h3",  fontSize=7,  fontName="Helvetica",       textColor=GREY,  leading=9)
    lbl = ParagraphStyle("lbl", fontSize=7.5, fontName="Helvetica-Bold", textColor=NAVY,  leading=10)
    val = ParagraphStyle("val", fontSize=7.5, fontName="Helvetica",      textColor=BLACK, leading=10)
    mono= ParagraphStyle("mono",fontSize=7.5, fontName="Courier",        textColor=BLACK, leading=10)
    ParagraphStyle("rgt", fontSize=7.5, fontName="Helvetica",      textColor=BLACK, leading=10, alignment=TA_RIGHT)
    net_style = ParagraphStyle("net", fontSize=11, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_RIGHT, leading=14)
    net_lbl   = ParagraphStyle("netl",fontSize=9,  fontName="Helvetica-Bold", textColor=WHITE, leading=12)

    # ── header: company logo + slip info ─────────────────────────────────────
    # Get company config (optional)
    company_tbl = Table(
        [[
            Paragraph(f"<b>{_company_name}</b>", h1),
            Paragraph(f"<b>SLIP GAJI</b><br/><font size='7' color='#6b7280'>{run.get('run_number', '')}</font>", ParagraphStyle("sr", fontSize=9, fontName="Helvetica-Bold", textColor=TEAL, alignment=TA_RIGHT, leading=12)),
        ]],
        colWidths=[W * 0.6, W * 0.4],
    )
    company_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    sub_tbl = Table(
        [[
            Paragraph(_company_sub, h3),
            Paragraph(
                f"Periode: {slip.get('period_from', '')} s/d {slip.get('period_to', '')}",
                ParagraphStyle("pd", fontSize=7, fontName="Helvetica", textColor=GREY, alignment=TA_RIGHT, leading=9)
            ),
        ]],
        colWidths=[W * 0.6, W * 0.4],
    )
    sub_tbl.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    # ── employee info box ──────────────────────────────────────────────────────
    scheme_labels = {"pcs": "Borongan Pcs", "hourly": "Borongan Jam", "weekly": "Mingguan", "monthly": "Bulanan"}
    scheme = scheme_labels.get(slip.get("pay_scheme", ""), slip.get("pay_scheme", "-"))
    emp_rows = [
        ["Nama Karyawan", slip.get("employee_name", "-"), "Kode", slip.get("employee_code", "-")],
        ["Skema Gaji",    scheme,                          "Hadir", f"{slip.get('days_hadir', 0)} hari"],
        ["Jam Kerja",     f"{slip.get('total_hours_worked', 0)} jam", "Lembur", f"{slip.get('overtime_hours', 0)} jam"],
    ]
    emp_tbl = Table(
        [
            [Paragraph(r[0], lbl), Paragraph(str(r[1]), val), Paragraph(r[2], lbl), Paragraph(str(r[3]), val)]
            for r in emp_rows
        ],
        colWidths=[W * 0.22, W * 0.33, W * 0.16, W * 0.29],
    )
    emp_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), LIGHT),
        ("ROWBACKGROUND",(0, 0), (-1, 0),  colors.HexColor("#dbeaf4")),
        ("BOX",          (0, 0), (-1, -1), 0.5, TEAL),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.HexColor("#c0d8e8")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    # ── earnings table ──────────────────────────────────────────────────────────
    earn_header = [
        Paragraph("Uraian Pendapatan", lbl),
        Paragraph("Qty", ParagraphStyle("lbl_c", fontSize=7.5, fontName="Helvetica-Bold", textColor=NAVY, alignment=TA_RIGHT, leading=10)),
        Paragraph("Satuan", ParagraphStyle("lbl_c2", fontSize=7.5, fontName="Helvetica-Bold", textColor=NAVY, alignment=TA_RIGHT, leading=10)),
        Paragraph("Jumlah", ParagraphStyle("lbl_r", fontSize=7.5, fontName="Helvetica-Bold", textColor=NAVY, alignment=TA_RIGHT, leading=10)),
    ]
    earn_rows = [earn_header]
    for e in (slip.get("earnings") or []):
        earn_rows.append([
            Paragraph(e.get("label", ""), val),
            Paragraph(str(e.get("qty", "")), mono),
            Paragraph(str(e.get("unit", "")), mono),
            Paragraph(_idr(e.get("amount", 0)), ParagraphStyle("am_r", fontSize=7.5, fontName="Courier", textColor=BLACK, alignment=TA_RIGHT, leading=10)),
        ])
    # overtime row
    if slip.get("overtime_amount", 0) > 0:
        earn_rows.append([
            Paragraph(f"Uang Lembur ({slip.get('overtime_hours', 0)} jam × {_idr(slip.get('overtime_rate', 0))})", val),
            Paragraph("", val),
            Paragraph("", val),
            Paragraph(_idr(slip.get("overtime_amount", 0)), ParagraphStyle("am_r2", fontSize=7.5, fontName="Courier", textColor=BLACK, alignment=TA_RIGHT, leading=10)),
        ])
    earn_tbl = Table(earn_rows, colWidths=[W * 0.47, W * 0.13, W * 0.14, W * 0.26])
    earn_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0),  TEAL),
        ("TEXTCOLOR",    (0, 0), (-1, 0),  WHITE),
        ("ROWBACKGROUND",(0, 1), (-1, -1), None),
        ("ROWBACKGROUND",(0, 1), (-1, -1), LIGHT),
        ("ROWBACKGROUND",(0, 2), (-1, -2), WHITE),
        ("BOX",          (0, 0), (-1, -1), 0.5, TEAL),
        ("LINEBELOW",    (0, 0), (-1, 0),  0.5, TEAL),
        ("GRID",         (0, 1), (-1, -1), 0.2, colors.HexColor("#d1e4ed")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    # earnings subtotal row
    earn_sub = Table(
        [[
            Paragraph("Total Pendapatan", ParagraphStyle("sub_l", fontSize=8, fontName="Helvetica-Bold", textColor=TEAL, leading=10)),
            Paragraph(_idr(slip.get("gross_pay", 0)), ParagraphStyle("sub_r", fontSize=8, fontName="Courier-Bold", textColor=TEAL, alignment=TA_RIGHT, leading=10)),
        ]],
        colWidths=[W * 0.74, W * 0.26],
    )
    earn_sub.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#dbeaf4")),
        ("BOX",          (0, 0), (-1, -1), 0.5, TEAL),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("LEFTPADDING",  (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))

    # ── allowances table (DA tunjangan tetap) ──────────────────────────────────
    allowance_items_data = slip.get("allowances") or []
    allowance_elements = []
    if allowance_items_data:
        alw_header = [
            Paragraph("Tunjangan", ParagraphStyle("ah_l", fontSize=7.5, fontName="Helvetica-Bold", textColor=WHITE, leading=10)),
            Paragraph("Jumlah", ParagraphStyle("ah_r", fontSize=7.5, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_RIGHT, leading=10)),
        ]
        alw_rows = [alw_header]
        for alw in allowance_items_data:
            alw_rows.append([
                Paragraph(alw.get("label", ""), val),
                Paragraph(_idr(alw.get("amount", 0)), ParagraphStyle("alw_r", fontSize=7.5, fontName="Courier", textColor=GREEN, alignment=TA_RIGHT, leading=10)),
            ])
        alw_tbl = Table(alw_rows, colWidths=[W * 0.74, W * 0.26])
        alw_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#1a7a4a")),
            ("ROWBACKGROUND",(0, 1), (-1, -1), colors.HexColor("#f0faf5")),
            ("BOX",          (0, 0), (-1, -1), 0.5, colors.HexColor("#1a7a4a")),
            ("GRID",         (0, 1), (-1, -1), 0.2, colors.HexColor("#b0e0c0")),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        allowance_elements = [Spacer(1, 3 * mm), alw_tbl]

    # ── deductions table ────────────────────────────────────────────────────────
    ded_rows_data = slip.get("deductions") or []
    ded_elements = []
    if ded_rows_data:
        ded_header = [
            Paragraph("Potongan", ParagraphStyle("dh_l", fontSize=7.5, fontName="Helvetica-Bold", textColor=WHITE, leading=10)),
            Paragraph("Jumlah", ParagraphStyle("dh_r", fontSize=7.5, fontName="Helvetica-Bold", textColor=WHITE, alignment=TA_RIGHT, leading=10)),
        ]
        ded_rows = [ded_header]
        for d in ded_rows_data:
            ded_rows.append([
                Paragraph(d.get("label", ""), val),
                Paragraph(_idr(d.get("amount", 0)), ParagraphStyle("dr_r", fontSize=7.5, fontName="Courier", textColor=RED, alignment=TA_RIGHT, leading=10)),
            ])
        ded_tbl = Table(ded_rows, colWidths=[W * 0.74, W * 0.26])
        ded_tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0, 0), (-1, 0),  colors.HexColor("#c0392b")),
            ("ROWBACKGROUND",(0, 1), (-1, -1), colors.HexColor("#fff5f5")),
            ("BOX",          (0, 0), (-1, -1), 0.5, colors.HexColor("#c0392b")),
            ("GRID",         (0, 1), (-1, -1), 0.2, colors.HexColor("#fcc")),
            ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING",   (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
            ("LEFTPADDING",  (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ]))
        ded_elements = [Spacer(1, 3 * mm), ded_tbl]

    # ── net pay box ─────────────────────────────────────────────────────────────
    net_tbl = Table(
        [[
            Paragraph("GAJI BERSIH", net_lbl),
            Paragraph(_idr(slip.get("net_pay", 0)), net_style),
        ]],
        colWidths=[W * 0.45, W * 0.55],
    )
    net_tbl.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), NAVY),
        ("BOX",          (0, 0), (-1, -1), 0,   NAVY),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("LEFTPADDING",  (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("ROUNDEDCORNERS", [3]),
    ]))

    # ── attendance summary bar ──────────────────────────────────────────────────
    att_cells = [
        [Paragraph("Hadir", h3), Paragraph(str(slip.get("days_hadir", 0)), lbl)],
        [Paragraph("Jam Kerja", h3), Paragraph(f"{slip.get('total_hours_worked', 0)} j", lbl)],
        [Paragraph("Lembur", h3), Paragraph(f"{slip.get('overtime_hours', 0)} j", lbl)],
    ]
    att_bar = Table(
        [list(sum(att_cells, []))],
        colWidths=[W / 6] * 6,
    )
    att_bar.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), colors.HexColor("#f0f6fa")),
        ("BOX",          (0, 0), (-1, -1), 0.3, TEAL),
        ("GRID",         (0, 0), (-1, -1), 0.2, colors.HexColor("#c0d8e8")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))

    # ── notes ───────────────────────────────────────────────────────────────────
    notes_el = []
    if slip.get("notes"):
        notes_el = [
            Spacer(1, 2 * mm),
            Paragraph(f"<i>Catatan: {slip['notes']}</i>", h3),
        ]

    # ── signature section (configurable — P1d) ──────────────────────────────────
    sig_context = {
        "employee_name": slip.get("employee_name", ""),
        "employee_code": slip.get("employee_code", ""),
        "run_number": run.get("run_number", ""),
        "approved_by": run.get("approved_by_name") or run.get("posted_by_name", ""),
    }
    sig_defs = doc_settings.get("signatures") or [
        {"label": "Disetujui oleh", "name_source": "custom", "custom_name": "", "role_label": "Manager / HRD"},
        {"label": "Diterima oleh", "name_source": "field", "field_key": "employee_name", "role_label": "Karyawan"},
    ]
    show_sig = doc_settings.get("show_signatures", True)
    sig_style = ParagraphStyle("sig", fontSize=7, fontName="Helvetica", textColor=GREY, alignment=TA_CENTER, leading=9)
    header_cells, name_cells = [], []
    for sd in sig_defs:
        nm = resolve_signature_name(sd, sig_context) or "________________"
        role = sd.get("role_label", "")
        header_cells.append(Paragraph(f"{sd.get('label','')},", h3))
        name_cells.append(Paragraph(f"({nm})<br/><font size='6'>{role}</font>", sig_style))
    ncol = max(len(sig_defs), 1)
    sig_tbl = Table(
        [header_cells, [Spacer(1, 12 * mm)] * ncol, name_cells],
        colWidths=[W / ncol] * ncol,
    )
    sig_tbl.setStyle(TableStyle([
        ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))

    # ── assemble ────────────────────────────────────────────────────────────────
    # SESI #19 — kop memakai TEMPLATE PDF pemilik bila ada (logo, telepon, NPWP,
    # tata letak). Kop lama (nama + tagline + garis tebal) TETAP dipakai sebagai
    # cadangan supaya slip gaji tidak pernah gagal cetak hanya karena template
    # belum diatur. Sisa tata letak A5 (kotak karyawan, blok gaji bersih,
    # watermark RAHASIA) sengaja TIDAK diubah: itu bagian yang sudah baik.
    _tpl = (doc_settings or {}).get("_template") or {}
    kop_els = []
    if _tpl.get("header"):
        try:
            from core.pdf_template import header_flowables
            kop_els = header_flowables(
                _tpl["header"], profile, "SLIP GAJI",
                info_pairs=[
                    ("No. Run", run.get("run_number", "")),
                    ("Periode", f"{slip.get('period_from', '')} s/d {slip.get('period_to', '')}"),
                ], avail=W)
        except Exception as e:  # noqa: BLE001
            log.warning("[payslip] kop template gagal dipakai, memakai kop lama: %s", e)
            kop_els = []

    story = [
        *(kop_els if kop_els else [
            company_tbl,
            sub_tbl,
            HRFlowable(width="100%", thickness=1.5, color=TEAL, spaceAfter=4),
        ]),
        emp_tbl,
        Spacer(1, 3 * mm),
        earn_tbl,
        earn_sub,
        *allowance_elements,
        *ded_elements,
        Spacer(1, 3 * mm),
        net_tbl,
        Spacer(1, 3 * mm),
        att_bar,
        *notes_el,
        Spacer(1, 5 * mm),
        *([HRFlowable(width="100%", thickness=0.5, color=GREY, spaceAfter=4), sig_tbl] if show_sig else []),
        Spacer(1, 2 * mm),
        Paragraph(
            f"<i>Slip ini dicetak secara otomatis oleh Sistem ERP CV. Dewi Aditya · {_now().strftime('%d/%m/%Y %H:%M')}</i>",
            ParagraphStyle("foot", fontSize=5.5, fontName="Helvetica-Oblique", textColor=GREY, alignment=TA_CENTER, leading=7)
        ),
    ]

    # ── watermark NAMA PERUSAHAAN + label RAHASIA (diagonal, abu muda) ────────
    # FASE 15 (permintaan user 2026-07-26): watermark harus menampilkan nama
    # perusahaan ("CV. DEWI ADITYA"), bukan hanya kata "RAHASIA". Nama diambil
    # dari profil perusahaan supaya ikut berubah bila perusahaan ganti nama.
    _wm_text = (_company_name or "CV. DEWI ADITYA").upper()
    # BUG-3: slip dari run yang MASIH DRAFT harus terlihat jelas belum final —
    # angkanya masih bisa berubah saat run difinalisasi.
    _is_draft = str(run.get("status", "")).lower() in ("", "draft")

    def _rahasia_watermark(canvas, _doc):
        canvas.saveState()
        try:
            canvas.setFillColorRGB(0.82, 0.82, 0.82, alpha=0.30)
        except TypeError:
            # older reportlab — no alpha param
            canvas.setFillColorRGB(0.88, 0.88, 0.88)
        canvas.translate(A5[0] / 2, A5[1] / 2)
        canvas.rotate(45)
        # Ukuran huruf disesuaikan panjang nama supaya tidak terpotong di A5.
        size = 46 if len(_wm_text) <= 16 else max(22, int(740 / len(_wm_text)))
        canvas.setFont("Helvetica-Bold", size)
        canvas.drawCentredString(0, 6 * mm, _wm_text)
        canvas.setFont("Helvetica-Bold", 20)
        canvas.drawCentredString(0, -10 * mm, "RAHASIA")
        if _is_draft:
            canvas.setFont("Helvetica-Bold", 14)
            canvas.drawCentredString(0, -24 * mm, "DRAFT - BELUM FINAL")
        canvas.restoreState()

    doc.build(story, onFirstPage=_rahasia_watermark, onLaterPages=_rahasia_watermark)
    buf.seek(0)
    return buf


@router.get("/payslips/{pid}/pdf")
async def export_payslip_pdf(pid: str, request: Request):
    """Unduh PDF satu slip gaji.

    BUG-3 (2026-07-26):
      · Karyawan TIDAK BISA mengunduh slip gajinya sendiri — endpoint menolak
        403 dengan pesan "Hubungi HR untuk salinan resmi", dan Portal Saya sama
        sekali tidak punya tombol unduh. Padahal slip gaji adalah dokumen milik
        karyawan (dipakai untuk pengajuan kredit, dsb).
      · Kepemilikan diperiksa lewat `user.get("employee_id")` MENTAH dari JWT
        (umur 24 jam) ⇒ karyawan yang baru ditautkan HR tetap ditolak.
    Sekarang: HR/Admin/Manager boleh semua slip; karyawan boleh slip MILIKNYA,
    dengan identitas dari SSOT `utils/employee_identity`.
    """
    user = await require_auth(request)
    db = get_db()
    role = (user.get("role") or "").lower()
    slip = await db.rahaza_payslips.find_one({"id": pid}, {"_id": 0})
    if not slip:
        raise HTTPException(404, "Payslip tidak ditemukan.")

    can_download_all = role in ("superadmin", "admin", "owner", "hr", "manager")
    if not can_download_all:
        from utils.employee_identity import resolve_my_employee
        emp = await resolve_my_employee(db, user)
        if not emp or emp.get("id") != slip.get("employee_id"):
            raise HTTPException(
                403, "Anda hanya bisa mengunduh slip gaji milik Anda sendiri.")

    run = await db.rahaza_payroll_runs.find_one({"id": slip.get("run_id", "")}, {"_id": 0}) or {}
    profile = await get_company_profile(db)
    doc_settings = await get_doc_settings(db, "payslip")
    try:
        buf = _build_payslip_pdf(dict(slip), dict(run), profile=profile, doc_settings=doc_settings)
    except Exception as e:
        log.error(f"PDF generation error: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate PDF: {e}")
    fname = f"slip_{slip.get('employee_code', 'EMP')}_{slip.get('period_from', '')}_{slip.get('period_to', '')}.pdf"
    fname = fname.replace(" ", "_")
    preview = request.query_params.get("preview") in ("1", "true", "yes")
    disposition = "inline" if preview else "attachment"
    return StreamingResponse(
        buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{fname}"'},
    )


@router.get("/payroll-runs/{run_id}/pdf")
async def export_run_pdf(run_id: str, request: Request):
    """Download PDF bundle berisi SEMUA slip gaji dalam satu run (1 halaman per karyawan)."""
    await require_auth(request)
    db = get_db()
    run = await db.rahaza_payroll_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Payroll run tidak ditemukan.")
    payslips = await db.rahaza_payslips.find(
        {"run_id": run_id}, {"_id": 0}
    ).sort("employee_code", 1).to_list(500)
    if not payslips:
        raise HTTPException(404, "Tidak ada payslip dalam run ini.")

    profile = await get_company_profile(db)
    doc_settings = await get_doc_settings(db, "payslip")
    try:
        from PyPDF2 import PdfWriter, PdfReader
        writer = PdfWriter()
        for slip in payslips:
            single_buf = _build_payslip_pdf(dict(slip), dict(run), profile=profile, doc_settings=doc_settings)
            reader = PdfReader(single_buf)
            for page in reader.pages:
                writer.add_page(page)
        out_buf = io.BytesIO()
        writer.write(out_buf)
        out_buf.seek(0)
    except ImportError:
        # Fallback: merge via concatenation into one buffer per-slip
        # Generate each slip separately and concatenate raw PDF bytes as ZIP
        import zipfile
        out_buf = io.BytesIO()
        with zipfile.ZipFile(out_buf, mode='w', compression=zipfile.ZIP_DEFLATED) as zf:
            for slip in payslips:
                single_buf = _build_payslip_pdf(dict(slip), dict(run), profile=profile, doc_settings=doc_settings)
                fname = f"slip_{slip.get('employee_code', 'EMP')}.pdf"
                zf.writestr(fname, single_buf.read())
        out_buf.seek(0)
        run_num = run.get("run_number", run_id[:8])
        return StreamingResponse(
            out_buf,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="payroll_{run_num}_slips.zip"'},
        )

    run_num = run.get("run_number", run_id[:8])
    fname = f"payroll_{run_num}_all_slips.pdf"
    return StreamingResponse(
        out_buf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── PAYSLIPS ──────────────────────────────────────────────────────────────────
@router.get("/payslips")
async def list_payslips(request: Request, run_id: Optional[str] = None, employee_id: Optional[str] = None, employee_code: Optional[str] = None):
    await require_auth(request)
    db = get_db()
    q = {}
    if run_id:
        q["run_id"] = run_id
    if employee_id:
        q["employee_id"] = employee_id
    if employee_code:
        q["employee_code"] = employee_code
    rows = await db.rahaza_payslips.find(q, {"_id": 0}).sort("employee_code", 1).to_list(500)
    return serialize_doc(rows)


@router.get("/payslips/{pid}")
async def get_payslip(pid: str, request: Request):
    await require_auth(request)
    db = get_db()
    row = await db.rahaza_payslips.find_one({"id": pid}, {"_id": 0})
    if not row:
        raise HTTPException(404, "Payslip tidak ditemukan.")
    return serialize_doc(row)


@router.put("/payslips/{pid}")
async def update_payslip(pid: str, request: Request):
    """Update deductions & notes saja (untuk adjust manual). Hanya jika run masih draft."""
    user = await _require_hr(request)
    db = get_db()
    slip = await db.rahaza_payslips.find_one({"id": pid}, {"_id": 0})
    if not slip:
        raise HTTPException(404, "Payslip tidak ditemukan.")
    run = await db.rahaza_payroll_runs.find_one({"id": slip["run_id"]}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Run induk tidak ditemukan.")
    if run.get("status") != "draft":
        raise HTTPException(400, "Run sudah di-finalize — slip tidak bisa diubah.")

    body = await request.json()
    deductions = body.get("deductions") or []
    norm_ded = []
    for d in deductions:
        label = (d.get("label") or "").strip()
        amount = float(d.get("amount") or 0)
        if not label or amount <= 0:
            continue
        norm_ded.append({"label": label, "amount": round(amount)})
    ded_total, net = _payslip_totals(slip, deductions=norm_ded)
    await db.rahaza_payslips.update_one({"id": pid}, {"$set": {
        "deductions": norm_ded,
        "deductions_total": ded_total,
        "net_pay": net,
        "notes": body.get("notes") or slip.get("notes", ""),
        "updated_at": _now(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    }})
    # FASE 20 — WAJIB: `post_payroll_run()` menyusun jurnal GL dari HEADER run,
    # bukan dari payslip. Sebelum ini slip diubah tanpa menyinkronkan header,
    # sehingga `total_net`/`total_deductions` di header (yang dipakai jurnal,
    # export Excel, dan kartu ringkasan) menyimpang dari jumlah slip sebenarnya.
    await _recompute_run_totals(db, slip["run_id"])
    out = await db.rahaza_payslips.find_one({"id": pid}, {"_id": 0})
    return serialize_doc(out)


# ─── PENYESUAIAN MANUAL PAYSLIP ──────────────────────────────────────────────
# FASE 20 — endpoint ini DIPANGGIL FE (`RahazaPayrollRunModule` → tombol "Adj")
# tetapi TIDAK PERNAH ADA di backend: `manual_deduction` & `adjustment_notes`
# nol hasil pencarian di seluruh `backend/`. Jadi kolom "Adj" selalu menampilkan
# 0 dan setiap penyimpanan hilang tanpa pesan error (404 senyap, FE tidak
# memeriksa `res.ok`).
#
# Sengaja TIDAK dialihkan ke `PUT /payslips/{pid}` yang sudah ada, karena
# semantiknya beda: PUT MENGGANTI seluruh array `deductions` (akan menghapus
# BPJS/PPh21/kasbon hasil hitungan sistem) dan menulis ke `notes`, sementara FE
# menampilkan `manual_deduction` + `adjustment_notes`.
@router.post("/payroll-runs/{run_id}/payslips/{slip_id}/adjust")
async def adjust_payslip(run_id: str, slip_id: str, request: Request):
    """Set penyesuaian manual (potongan + catatan) pada satu payslip.

    Idempoten: mengirim nilai yang sama dua kali menghasilkan angka yang sama —
    `manual_deduction` DIGANTI, bukan ditambahkan.
    """
    user = await _require_hr(request)
    db = get_db()

    slip = await db.rahaza_payslips.find_one({"id": slip_id}, {"_id": 0})
    if not slip:
        raise HTTPException(404, "Payslip tidak ditemukan.")
    # Slip harus benar-benar milik run di URL — kalau tidak, satu run bisa
    # dipakai untuk mengubah slip run lain (IDOR + total header jadi salah).
    if slip.get("run_id") != run_id:
        raise HTTPException(404, "Payslip tidak ada di payroll run tersebut.")

    run = await db.rahaza_payroll_runs.find_one({"id": run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, "Payroll run tidak ditemukan.")
    if run.get("status") != "draft":
        raise HTTPException(400, "Run sudah di-finalize — slip tidak bisa diubah.")

    body = await request.json()
    raw = body.get("deduction", body.get("manual_deduction"))
    try:
        deduction = float(raw or 0)
    except (TypeError, ValueError):
        raise HTTPException(400, "Nilai penyesuaian harus berupa angka.")
    if deduction < 0:
        raise HTTPException(400, "Penyesuaian tidak boleh negatif.")
    gross = float(slip.get("gross_pay") or 0)
    base_ded = sum(round(float(d.get("amount") or 0)) for d in (slip.get("deductions") or []))
    # Batas atas: total potongan tidak boleh melebihi bruto (net negatif =
    # karyawan berutang ke perusahaan lewat payroll — bukan alur yang didukung).
    if round(deduction) + base_ded > gross:
        raise HTTPException(
            400,
            f"Penyesuaian terlalu besar: potongan sistem {base_ded:,.0f} + "
            f"penyesuaian {deduction:,.0f} melebihi bruto {gross:,.0f}.".replace(",", "."),
        )

    notes = (body.get("notes") or "").strip()
    ded_total, net = _payslip_totals(slip, manual_deduction=deduction)
    await db.rahaza_payslips.update_one({"id": slip_id}, {"$set": {
        "manual_deduction": round(deduction),
        "adjustment_notes": notes,
        "deductions_total": ded_total,
        "net_pay": net,
        "updated_at": _now(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    }})
    totals = await _recompute_run_totals(db, run_id)
    await log_activity(user["id"], user.get("name", ""), "adjust", "rahaza.payslip",
                       f"{slip.get('employee_code', slip_id)} → {round(deduction)}")
    out = await db.rahaza_payslips.find_one({"id": slip_id}, {"_id": 0})
    return {"ok": True, "payslip": serialize_doc(out), "run_totals": serialize_doc(totals)}
