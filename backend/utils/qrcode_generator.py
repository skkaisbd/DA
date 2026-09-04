"""
PT Rahaza ERP — QR Code + Bundle Ticket PDF generator (Phase 17B)

Generates:
- QR PNG bytes from an arbitrary payload (bundle_id or bundle_number).
- A printable A5-portrait bundle ticket PDF containing:
    * Company banner
    * Large QR code (payload = bundle_number)
    * Bundle metadata (bundle_number, WO, model, size, qty)
    * Sub-process checkbox bar (manual stamp fallback if QR is damaged)
    * Footer with created_at + bundle_id short suffix
- A multi-page PDF combining many bundle tickets (one per page) for bulk print.

Design notes:
- One ticket per A5 page (printable 4-up on A4 via printer imposition, or 2-up easily).
- Uses reportlab for PDF, `qrcode` + PIL for QR rendering.
- No external network. Pure in-memory generation.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Iterable, Optional

import qrcode
from qrcode.constants import ERROR_CORRECT_M
from reportlab.lib.pagesizes import A5
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from utils.waktu import now_wib


# ─── QR image ────────────────────────────────────────────────────────────────
def generate_qr_png(payload: str, box_size: int = 10, border: int = 2) -> bytes:
    """Return PNG bytes of a QR code for `payload`.

    Error correction level M is a good balance for factory-floor print wear.
    """
    if not payload:
        raise ValueError("payload is required for QR generation")
    qr = qrcode.QRCode(
        version=None,  # auto-fit
        error_correction=ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ─── Bundle ticket PDF (single + bulk) ──────────────────────────────────────
DEFAULT_STAMP_STEPS = [
    "Rajut",
    "Linking",
    "Sewing",
    "QC",
    "Washer",
    "Steam",
    "Packing",
]


def _fmt(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).strip()
    return s if s else "-"


def _draw_single_ticket(c: canvas.Canvas, bundle: dict, stamp_steps: Iterable[str]):
    """Render one bundle ticket on the current page. Assumes page size = A5."""
    page_w, page_h = A5  # 148 x 210 mm (portrait)

    margin = 10 * mm
    inner_w = page_w - 2 * margin

    # ─ Header banner
    c.setFillColorRGB(0.07, 0.09, 0.15)
    c.rect(0, page_h - 18 * mm, page_w, 18 * mm, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont("Helvetica-Bold", 13)
    c.drawString(margin, page_h - 10 * mm, "PT RAHAZA GLOBAL INDONESIA")
    c.setFont("Helvetica", 9)
    c.drawString(margin, page_h - 15 * mm, "Bundle Ticket — Traceability Label")
    # Right-side badge
    c.setFont("Helvetica-Bold", 10)
    badge = f"Status: {_fmt(bundle.get('status')).upper()}"
    c.drawRightString(page_w - margin, page_h - 10 * mm, badge)
    c.setFont("Helvetica", 8)
    created_at = bundle.get("created_at") or ""
    if created_at:
        try:
            # Handle both datetime objects and ISO strings
            if isinstance(created_at, datetime):
                dt = created_at
            else:
                dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            created_at_short = dt.strftime("%Y-%m-%d %H:%M")
        except Exception:
            # Fallback: try to extract first 16 chars if it's a string
            created_at_short = str(created_at)[:16] if created_at else "-"
    else:
        created_at_short = "-"
    c.drawRightString(page_w - margin, page_h - 15 * mm, f"Dicetak: {now_wib().strftime('%Y-%m-%d %H:%M')}")

    # ─ Bundle number (big)
    y_cursor = page_h - 18 * mm - 10 * mm
    c.setFillColorRGB(0, 0, 0)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(margin, y_cursor, _fmt(bundle.get("bundle_number")))
    c.setFont("Helvetica", 9)
    c.setFillColorRGB(0.35, 0.38, 0.45)
    c.drawString(margin, y_cursor - 5 * mm, f"Bundle ID: {_fmt(bundle.get('id'))[:18]}…")

    # ─ QR code (right side, big)
    qr_payload = _fmt(bundle.get("bundle_number"))
    qr_png = generate_qr_png(qr_payload, box_size=10, border=1)
    qr_size = 55 * mm
    qr_x = page_w - margin - qr_size
    qr_y = y_cursor - qr_size - 2 * mm
    c.drawImage(
        ImageReader(io.BytesIO(qr_png)),
        qr_x,
        qr_y,
        width=qr_size,
        height=qr_size,
        preserveAspectRatio=True,
        mask="auto",
    )
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.4, 0.45)
    c.drawCentredString(qr_x + qr_size / 2, qr_y - 3 * mm, "Scan via app Operator")

    # ─ Metadata block (left column)
    c.setFillColorRGB(0, 0, 0)
    meta_y = y_cursor - 12 * mm
    line_h = 7 * mm

    def _kv(label: str, value: str, y: float):
        c.setFont("Helvetica", 8)
        c.setFillColorRGB(0.45, 0.48, 0.55)
        c.drawString(margin, y, label.upper())
        c.setFont("Helvetica-Bold", 11)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(margin, y - 4.5 * mm, value)

    _kv("Work Order", _fmt(bundle.get("wo_number_snapshot")), meta_y)
    _kv("Model", f"{_fmt(bundle.get('model_code'))} — {_fmt(bundle.get('model_name'))[:24]}", meta_y - line_h)
    _kv("Size", _fmt(bundle.get("size_code")), meta_y - 2 * line_h)
    _kv("Qty", f"{_fmt(bundle.get('qty'))} pcs", meta_y - 3 * line_h)
    _kv("Current Process", _fmt(bundle.get("current_process_name")), meta_y - 4 * line_h)

    # ─ Stamp bar (manual fallback) — full width, below metadata & QR block
    steps = list(stamp_steps)
    stamp_top = qr_y - 10 * mm
    box_h = 14 * mm
    count = max(1, len(steps))
    cell_w = inner_w / count

    c.setLineWidth(0.7)
    c.setStrokeColorRGB(0.2, 0.22, 0.28)
    c.setFillColorRGB(0.95, 0.96, 0.98)
    c.rect(margin, stamp_top - box_h, inner_w, box_h, fill=1, stroke=1)

    for i, step in enumerate(steps):
        x = margin + i * cell_w
        if i > 0:
            c.line(x, stamp_top - box_h, x, stamp_top)
        c.setFont("Helvetica-Bold", 8)
        c.setFillColorRGB(0.15, 0.18, 0.25)
        c.drawCentredString(x + cell_w / 2, stamp_top - 4 * mm, step.upper())
        # placeholder checkbox
        box_side = 5 * mm
        cb_x = x + cell_w / 2 - box_side / 2
        cb_y = stamp_top - box_h + 2 * mm
        c.setLineWidth(0.6)
        c.setStrokeColorRGB(0.4, 0.45, 0.55)
        c.rect(cb_x, cb_y, box_side, box_side, fill=0, stroke=1)

    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.4, 0.45, 0.52)
    c.drawString(margin, stamp_top - box_h - 4 * mm,
                 "Stempel manual hanya sebagai cadangan bila QR rusak. Tetap utamakan scan via aplikasi.")

    # ─ Footer
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.55)
    c.drawString(margin, 8 * mm, f"Dibuat: {created_at_short}")
    c.drawRightString(page_w - margin, 8 * mm,
                      f"Rahaza ERP • Phase 17B • {_fmt(bundle.get('bundle_number'))}")


def render_bundle_ticket_pdf(bundle: dict, stamp_steps: Optional[Iterable[str]] = None) -> bytes:
    """Render a single bundle ticket as a one-page A5 PDF and return bytes."""
    steps = list(stamp_steps) if stamp_steps else DEFAULT_STAMP_STEPS
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    c.setTitle(f"Bundle Ticket {bundle.get('bundle_number') or ''}")
    _draw_single_ticket(c, bundle, steps)
    c.showPage()
    c.save()
    return buf.getvalue()


def render_bundle_tickets_bulk_pdf(bundles: Iterable[dict], stamp_steps: Optional[Iterable[str]] = None) -> bytes:
    """Render many bundles as a multi-page PDF (one ticket per page)."""
    steps = list(stamp_steps) if stamp_steps else DEFAULT_STAMP_STEPS
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A5)
    c.setTitle("Bundle Tickets (bulk print)")
    count = 0
    for b in bundles:
        _draw_single_ticket(c, b, steps)
        c.showPage()
        count += 1
    if count == 0:
        # Draw an empty placeholder page to avoid invalid PDF
        c.setFont("Helvetica", 12)
        c.drawString(20 * mm, A5[1] - 30 * mm, "Tidak ada bundle untuk dicetak.")
        c.showPage()
    c.save()
    return buf.getvalue()
