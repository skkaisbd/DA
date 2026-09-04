"""
PT Rahaza — End-of-Shift PDF Generator
Generates a clean A4 PDF summary for a shift handover record.
"""
import io
from datetime import datetime, timezone
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle

# ─── Colors ──────────────────────────────────────────────────────────
BRAND_DARK  = colors.HexColor("#0f172a")
BRAND_MID   = colors.HexColor("#1e293b")
BRAND_BLUE  = colors.HexColor("#3b82f6")
BRAND_GREEN = colors.HexColor("#10b981")
BRAND_AMBER = colors.HexColor("#f59e0b")
BRAND_RED   = colors.HexColor("#ef4444")
BORDER      = colors.HexColor("#334155")
LIGHT_GREY  = colors.HexColor("#f1f5f9")
TEXT_MAIN   = colors.HexColor("#0f172a")
TEXT_MID    = colors.HexColor("#475569")
WHITE       = colors.white

PAGE_W, PAGE_H = A4
MARGIN = 18 * mm


def _safe(val) -> str:
    if val is None:
        return "-"
    return str(val).replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")


def _styles():
    base = getSampleStyleSheet()
    s = {}
    s["title"] = ParagraphStyle(
        "title", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=16,
        textColor=WHITE, leading=20, alignment=TA_CENTER,
    )
    s["sub"] = ParagraphStyle(
        "sub", parent=base["Normal"],
        fontName="Helvetica", fontSize=9,
        textColor=colors.HexColor("#94a3b8"), leading=12, alignment=TA_CENTER,
    )
    s["section_hdr"] = ParagraphStyle(
        "section_hdr", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=9.5,
        textColor=WHITE, leading=14, spaceBefore=2,
    )
    s["cell_hdr"] = ParagraphStyle(
        "cell_hdr", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=8.5,
        textColor=TEXT_MID, leading=12,
    )
    s["cell"] = ParagraphStyle(
        "cell", parent=base["Normal"],
        fontName="Helvetica", fontSize=8.5,
        textColor=TEXT_MAIN, leading=12,
    )
    s["cell_bold"] = ParagraphStyle(
        "cell_bold", parent=base["Normal"],
        fontName="Helvetica-Bold", fontSize=8.5,
        textColor=TEXT_MAIN, leading=12,
    )
    s["label"] = ParagraphStyle(
        "label", parent=base["Normal"],
        fontName="Helvetica", fontSize=8,
        textColor=TEXT_MID, leading=11,
    )
    s["note"] = ParagraphStyle(
        "note", parent=base["Normal"],
        fontName="Helvetica-Oblique", fontSize=8,
        textColor=TEXT_MID, leading=11,
    )
    return s


def _section_header(label: str, styles):
    return Table(
        [[Paragraph(label, styles["section_hdr"])]],
        colWidths=[PAGE_W - 2 * MARGIN],
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_BLUE),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("ROUNDEDCORNERS", [3, 3, 3, 3]),
        ])
    )


def _info_table(rows: list, styles):
    """Two-column key-value table for shift info."""
    table_rows = []
    for i in range(0, len(rows), 2):
        pair = rows[i:i + 2]
        row = []
        for label, value in pair:
            row += [
                Paragraph(_safe(label), styles["cell_hdr"]),
                Paragraph(_safe(value), styles["cell"]),
            ]
        if len(pair) < 2:
            row += ["", ""]
        table_rows.append(row)

    col_w = (PAGE_W - 2 * MARGIN) / 4
    t = Table(table_rows, colWidths=[col_w] * 4)
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
    ]))
    return t


def _checklist_table(checklist: list, styles):
    if not checklist:
        return Paragraph("(Tidak ada checklist)", styles["note"])
    rows = [[
        Paragraph("Status", styles["cell_hdr"]),
        Paragraph("Item", styles["cell_hdr"]),
        Paragraph("Catatan", styles["cell_hdr"]),
    ]]
    for item in checklist:
        ok = item.get("value", False)
        rows.append([
            Paragraph("✓ OK" if ok else "✗ Tidak", ParagraphStyle(
                "ck", fontName="Helvetica-Bold", fontSize=8.5,
                textColor=BRAND_GREEN if ok else BRAND_AMBER, leading=12,
            )),
            Paragraph(_safe(item.get("label", "")), styles["cell"]),
            Paragraph(_safe(item.get("notes", "") or "-"), styles["note"]),
        ])
    cw = PAGE_W - 2 * MARGIN
    t = Table(rows, colWidths=[cw * 0.15, cw * 0.45, cw * 0.40])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))
    return t


def _issues_table(issues: list, styles):
    if not issues:
        return Paragraph("(Tidak ada masalah yang dilaporkan)", styles["note"])
    rows = [[
        Paragraph("Tipe", styles["cell_hdr"]),
        Paragraph("Prioritas", styles["cell_hdr"]),
        Paragraph("Deskripsi", styles["cell_hdr"]),
    ]]
    prio_color = {"high": BRAND_RED, "medium": BRAND_AMBER, "low": BRAND_GREEN}
    for iss in issues:
        prio = iss.get("priority", "medium")
        rows.append([
            Paragraph(_safe(iss.get("type", "-").upper()), styles["cell_bold"]),
            Paragraph(prio.upper(), ParagraphStyle(
                "pr", fontName="Helvetica-Bold", fontSize=8.5,
                textColor=prio_color.get(prio, TEXT_MID), leading=12,
            )),
            Paragraph(_safe(iss.get("description", "-")), styles["cell"]),
        ])
    cw = PAGE_W - 2 * MARGIN
    t = Table(rows, colWidths=[cw * 0.15, cw * 0.15, cw * 0.70])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))
    return t


def _tasks_table(tasks: list, styles):
    if not tasks:
        return Paragraph("(Tidak ada task tertunda)", styles["note"])
    rows = [[
        Paragraph("No", styles["cell_hdr"]),
        Paragraph("Deskripsi Task", styles["cell_hdr"]),
        Paragraph("Ditugaskan Ke", styles["cell_hdr"]),
    ]]
    for i, t in enumerate(tasks):
        rows.append([
            Paragraph(str(i + 1), styles["cell"]),
            Paragraph(_safe(t.get("description", "-")), styles["cell"]),
            Paragraph(_safe(t.get("assigned_to") or "-"), styles["cell"]),
        ])
    cw = PAGE_W - 2 * MARGIN
    tbl = Table(rows, colWidths=[cw * 0.08, cw * 0.62, cw * 0.30])
    tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
        ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
    ]))
    return tbl


def _signature_block(handover: dict, styles):
    """Signature/sign-off block."""
    cw = (PAGE_W - 2 * MARGIN) / 2

    def _sig_cell(title, name, date_str):
        return Table(
            [
                [Paragraph(title, styles["cell_hdr"])],
                [Spacer(1, 18 * mm)],
                [HRFlowable(width=cw * 0.7, color=BORDER)],
                [Paragraph(f"Nama: {_safe(name)}", styles["cell"])],
                [Paragraph(f"Tanggal: {_safe(date_str)}", styles["cell"])],
            ],
            colWidths=[cw - 6],
            style=TableStyle([
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ])
        )

    supervisor_name = handover.get("supervisor_name") or handover.get("created_by_name") or "-"
    supervisor_date = (handover.get("date") or "")[:10]
    signed_by = handover.get("signed_off_by_name") or "-"
    signed_date = (handover.get("signed_off_at") or "")[:10]

    row = [[
        _sig_cell("Dibuat oleh (Supervisor Shift Ini)", supervisor_name, supervisor_date),
        _sig_cell("Diterima oleh (Supervisor Shift Berikutnya)", signed_by, signed_date),
    ]]
    return Table(row, colWidths=[cw, cw], style=TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))


def build_shift_report_pdf(handover: dict, wo_summary: list = None) -> bytes:
    """
    Build End-of-Shift PDF for a handover record.

    handover: dict from rahaza_shift_handovers collection
    wo_summary: list of WO progress dicts [{wo_number, model_code, qty, qty_produced, status}]
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
        title=f"Laporan Akhir Shift — {handover.get('date', '')}"
    )
    styles = _styles()
    story = []

    # ─── Cover Header ────────────────────────────────────────────────
    header_table = Table(
        [[Paragraph("PT RAHAZA GLOBAL INDONESIA", styles["title"]),
          Paragraph("LAPORAN AKHIR SHIFT", styles["title"])],
         [Paragraph("Jl. Industri Garment No.1 | Bandung, Jawa Barat", styles["sub"]),
          Paragraph("End-of-Shift Report", styles["sub"])]],
        colWidths=[(PAGE_W - 2 * MARGIN) / 2] * 2,
        style=TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), BRAND_DARK),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ])
    )
    story.append(header_table)
    story.append(Spacer(1, 5 * mm))

    # ─── A. Info Shift ───────────────────────────────────────────────
    story.append(_section_header("A. INFORMASI SHIFT", styles))
    story.append(Spacer(1, 2 * mm))
    story.append(_info_table([
        ("Tanggal", handover.get("date") or "-"),
        ("Shift", handover.get("shift_name") or handover.get("shift_code") or "-"),
        ("Supervisor Shift", handover.get("supervisor_name") or handover.get("created_by_name") or "-"),
        ("Status", ("SIGNED OFF" if handover.get("status") == "signed_off" else "AKTIF / BELUM SIGN OFF")),
        ("Jam Sign-Off", (handover.get("signed_off_at") or "-")[:16]),
        ("Diterima Oleh", handover.get("signed_off_by_name") or "-"),
        ("Catatan Sign-Off", handover.get("sign_off_notes") or "-"),
        ("Waktu Buat", (handover.get("created_at") or "-")[:16]),
    ], styles))
    story.append(Spacer(1, 4 * mm))

    # ─── B. Catatan Umum ─────────────────────────────────────────────
    story.append(_section_header("B. CATATAN UMUM", styles))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(_safe(handover.get("notes") or "(Tidak ada catatan umum)"), styles["cell"]))
    story.append(Spacer(1, 4 * mm))

    # ─── C. Checklist Shift ──────────────────────────────────────────
    story.append(_section_header("C. CHECKLIST SHIFT", styles))
    story.append(Spacer(1, 2 * mm))
    story.append(_checklist_table(handover.get("checklist") or [], styles))
    story.append(Spacer(1, 4 * mm))

    # ─── D. Masalah yang Dihadapi ────────────────────────────────────
    story.append(_section_header("D. MASALAH YANG DIHADAPI", styles))
    story.append(Spacer(1, 2 * mm))
    story.append(_issues_table(handover.get("issues") or [], styles))
    story.append(Spacer(1, 4 * mm))

    # ─── E. Task Tertunda ────────────────────────────────────────────
    story.append(_section_header("E. TASK TERTUNDA UNTUK SHIFT BERIKUTNYA", styles))
    story.append(Spacer(1, 2 * mm))
    story.append(_tasks_table(handover.get("pending_tasks") or [], styles))
    story.append(Spacer(1, 4 * mm))

    # ─── F. Progres Work Order ───────────────────────────────────────
    if wo_summary:
        story.append(_section_header("F. PROGRES WORK ORDER (LINI INI)", styles))
        story.append(Spacer(1, 2 * mm))
        wo_rows = [[
            Paragraph("WO#", styles["cell_hdr"]),
            Paragraph("Model", styles["cell_hdr"]),
            Paragraph("Target", styles["cell_hdr"]),
            Paragraph("Diproduksi", styles["cell_hdr"]),
            Paragraph("Lolos QC", styles["cell_hdr"]),
            Paragraph("Status", styles["cell_hdr"]),
        ]]
        for wo in wo_summary[:15]:
            status = _safe(wo.get("status", "-"))
            st_color = BRAND_GREEN if status in ("completed",) else BRAND_AMBER if status == "in_progress" else TEXT_MID
            wo_rows.append([
                Paragraph(_safe(wo.get("wo_number", "-")), styles["cell"]),
                Paragraph(_safe(wo.get("model_code", "-")), styles["cell"]),
                Paragraph(str(wo.get("qty", 0)), styles["cell"]),
                Paragraph(str(wo.get("qty_produced", 0)), styles["cell"]),
                Paragraph(str(wo.get("qty_passed_qc", 0)), styles["cell"]),
                Paragraph(status.upper(), ParagraphStyle(
                    "ws", fontName="Helvetica-Bold", fontSize=8, textColor=st_color, leading=12,
                )),
            ])
        cw = PAGE_W - 2 * MARGIN
        wo_t = Table(wo_rows, colWidths=[cw * 0.22, cw * 0.18, cw * 0.12, cw * 0.16, cw * 0.16, cw * 0.16])
        wo_t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), LIGHT_GREY),
            ("LINEBELOW", (0, 0), (-1, -1), 0.3, BORDER),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, LIGHT_GREY]),
        ]))
        story.append(wo_t)
        story.append(Spacer(1, 4 * mm))

    # ─── G. Tanda Tangan ─────────────────────────────────────────────
    story.append(_section_header("G. TANDA TANGAN & SERAH TERIMA", styles))
    story.append(Spacer(1, 4 * mm))
    story.append(_signature_block(handover, styles))
    story.append(Spacer(1, 6 * mm))

    # Footer
    story.append(HRFlowable(width=PAGE_W - 2 * MARGIN, color=BORDER))
    story.append(Spacer(1, 2 * mm))
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    story.append(Paragraph(
        f"Dicetak: {now_str} | Dokumen resmi PT Rahaza Global Indonesia | Sistem ERP Rahaza v2.5",
        styles["note"]
    ))

    doc.build(story)
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes
