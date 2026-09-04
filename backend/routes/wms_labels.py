"""
WMS — Printable Barcode Labels (PDF)
Generate label PDF berisi barcode Code128 untuk:
  - Single posisi: GET /api/wms/positions/{position_id}/label-pdf
  - Semua posisi dalam rak: GET /api/wms/racks/{rack_id}/labels-pdf
  - Multiple posisi by IDs: POST /api/wms/labels/batch-pdf {position_ids: [...]}

Layout: 3 kolom × 8 baris label per A4 (24 label/halaman),
       ukuran ~70mm × 35mm, mirip label printer industri.
"""

import io
from typing import List, Optional
from fastapi import APIRouter, HTTPException, Request, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from database import get_db
from auth import require_auth, verify_token_str

# ReportLab + python-barcode
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image as PILImage

router = APIRouter(prefix="/api/wms", tags=["wms-labels"])


# ─── Layout constants (A4) ───────────────────────────────────────────────────
PAGE_W, PAGE_H = A4   # 595 × 842 pt
COLS = 3
ROWS = 8
LABEL_W = 65 * mm
LABEL_H = 33 * mm
MARGIN_X = (PAGE_W - COLS * LABEL_W) / 2
MARGIN_Y = (PAGE_H - ROWS * LABEL_H) / 2


def _make_barcode_png(value: str) -> io.BytesIO:
    """Generate Code128 barcode as PNG bytes (in-memory)."""
    buf = io.BytesIO()
    writer = ImageWriter()
    # Tweak writer options for tighter label
    Code128(value, writer=writer).write(buf, options={
        "module_width": 0.30,
        "module_height": 10.0,
        "font_size": 7,
        "text_distance": 2.0,
        "quiet_zone": 1.5,
        "write_text": False,  # we draw text ourselves
    })
    buf.seek(0)
    return buf


def _draw_label(c: canvas.Canvas, x: float, y: float, position: dict):
    """Draw one label at (x, y) bottom-left corner."""
    barcode = position.get("barcode", "")
    label_text = position.get("label", "")
    bldg = position.get("building_code", "")
    zone = position.get("zone_code", "")
    rack = position.get("rack_code", "")

    # Border (faint)
    c.setStrokeColorRGB(0.85, 0.85, 0.85)
    c.setLineWidth(0.4)
    c.rect(x, y, LABEL_W, LABEL_H, stroke=1, fill=0)

    # Top text: location code path
    c.setFillColorRGB(0.2, 0.2, 0.2)
    c.setFont("Helvetica-Bold", 8)
    location_path = f"{bldg} / {zone} / {rack}"
    c.drawString(x + 3 * mm, y + LABEL_H - 5 * mm, location_path)

    # Sublabel
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.drawString(x + 3 * mm, y + LABEL_H - 9 * mm, label_text or "")

    # Barcode image
    try:
        png_buf = _make_barcode_png(barcode)
        img = PILImage.open(png_buf)
        # Convert to RGB for ReportLab
        if img.mode != "RGB":
            img = img.convert("RGB")
        # Resize keeping aspect ratio so it fits
        target_w = LABEL_W - 8 * mm
        target_h = 14 * mm
        from reportlab.lib.utils import ImageReader
        c.drawImage(ImageReader(img),
                    x + 4 * mm, y + 9 * mm,
                    width=target_w, height=target_h,
                    preserveAspectRatio=True, anchor='c', mask='auto')
    except Exception:
        # Fallback: draw text-only box
        c.setFont("Courier-Bold", 9)
        c.setFillColorRGB(0, 0, 0)
        c.drawString(x + 4 * mm, y + 16 * mm, "[Barcode N/A]")

    # Bottom: barcode value (human-readable)
    c.setFont("Courier", 7)
    c.setFillColorRGB(0.1, 0.1, 0.1)
    c.drawCentredString(x + LABEL_W / 2, y + 4 * mm, barcode)


def _build_pdf(positions: List[dict], title: str) -> io.BytesIO:
    """Build PDF with labels arranged on A4. Returns BytesIO."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title)

    per_page = COLS * ROWS
    total = len(positions)

    for i, pos in enumerate(positions):
        col = i % COLS
        row = (i // COLS) % ROWS
        x = MARGIN_X + col * LABEL_W
        # Top-down: row 0 is top, so y is computed from top
        y = PAGE_H - MARGIN_Y - (row + 1) * LABEL_H
        _draw_label(c, x, y, pos)

        # Page break
        if (i + 1) % per_page == 0 and (i + 1) < total:
            # Footer
            c.setFont("Helvetica", 7)
            c.setFillColorRGB(0.5, 0.5, 0.5)
            c.drawString(MARGIN_X, MARGIN_Y / 2, f"{title}  ·  Page {(i + 1) // per_page}")
            c.showPage()

    # Final page footer
    c.setFont("Helvetica", 7)
    c.setFillColorRGB(0.5, 0.5, 0.5)
    last_page = (total - 1) // per_page + 1 if total else 1
    c.drawString(MARGIN_X, MARGIN_Y / 2, f"{title}  ·  Page {last_page}  ·  {total} label")

    c.save()
    buf.seek(0)
    return buf


async def _auth_or_token(request: Request, token: Optional[str] = None):
    """Auth via Authorization header OR ?token= query param (browser-open PDF)."""
    if token:
        user = verify_token_str(token)
        if user:
            return user
    # Fallback to header
    return await require_auth(request)


# ══════════════════════════════════════════════════════════════════════════════
# Routes
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/positions/{position_id}/label-pdf")
async def position_label_pdf(position_id: str, request: Request, token: Optional[str] = Query(None)):
    """Single label PDF (1 label centered on page)."""
    await _auth_or_token(request, token)
    db = get_db()
    pos = await db.wh_positions.find_one({"id": position_id}, {"_id": 0})
    if not pos:
        raise HTTPException(404, "Posisi tidak ditemukan")
    pdf = _build_pdf([pos], f"Label-{pos.get('barcode')}")
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="label_{pos.get("barcode","pos")}.pdf"'},
    )


@router.get("/racks/{rack_id}/labels-pdf")
async def rack_labels_pdf(rack_id: str, request: Request, token: Optional[str] = Query(None)):
    """All labels for one rack (sheet-fit, 24 per A4)."""
    await _auth_or_token(request, token)
    db = get_db()
    rack = await db.wh_racks.find_one({"id": rack_id}, {"_id": 0})
    if not rack:
        raise HTTPException(404, "Rak tidak ditemukan")
    positions = await db.wh_positions.find({"rack_id": rack_id}, {"_id": 0})\
        .sort([("shelf_no", 1), ("slot_no", 1)]).to_list(500)
    if not positions:
        raise HTTPException(400, "Rak tidak memiliki posisi")
    title = f"Labels Rak {rack.get('building_code','')}-{rack.get('zone_code','')}-{rack.get('code','')}"
    pdf = _build_pdf(positions, title)
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="labels_rack_{rack.get("code","")}.pdf"'},
    )


class BatchLabelsIn(BaseModel):
    position_ids: List[str]


@router.post("/labels/batch-pdf")
async def batch_labels_pdf(data: BatchLabelsIn, request: Request):
    """Generate PDF for arbitrary set of position IDs."""
    await require_auth(request)
    if not data.position_ids:
        raise HTTPException(400, "position_ids tidak boleh kosong")
    db = get_db()
    positions = await db.wh_positions.find(
        {"id": {"$in": data.position_ids}}, {"_id": 0}
    ).sort([("building_code", 1), ("zone_code", 1), ("rack_code", 1), ("shelf_no", 1), ("slot_no", 1)]).to_list(500)
    if not positions:
        raise HTTPException(404, "Tidak ada posisi cocok")
    pdf = _build_pdf(positions, f"Labels Batch ({len(positions)} posisi)")
    return StreamingResponse(
        pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="labels_batch.pdf"'},
    )
