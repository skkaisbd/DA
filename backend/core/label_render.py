"""SSOT gambar label barcode — bahan (90×50 mm) & barang jadi (100×70 mm).

FASE H-3 (2026-08-16). Kenapa berkas ini ada — bukan kerapian:

1. Label bahan digambar DUA KALI dengan kode terpisah di `wms_material_labels.py`
   (sekali untuk PDF satu label, sekali lagi di dalam perulangan batch), dan hal
   yang sama berlaku untuk FG. Menu "Buat Barcode" akan menjadi definisi KETIGA.
   Dua definisi untuk satu label = dua cara sebuah kolom bisa hilang dari kertas
   tanpa ada yang tahu.

2. DUA CACAT NYATA yang ditemukan saat menulis ini dan ditutup di sini:
   * Batch label bahan memakai `COLS = 3` × 90 mm = **270 mm** pada A4 yang
     lebarnya **210 mm** ⇒ `MARGIN_X` NEGATIF dan kolom ketiga tercetak DI LUAR
     halaman (label ketiga hilang di setiap baris). Sekarang jumlah kolom/baris
     DIHITUNG dari ukuran halaman (`grid_geometry`) sehingga label mustahil
     keluar kertas — pelajaran yang sama dengan Fase F (lebar tabel PDF hardcode).
   * Satuan dibaca dari `material['uom']`. Field itu **TIDAK ADA** di
     `rahaza_materials` (namanya `unit`) ⇒ SEMUA label bahan mencetak "pcs",
     termasuk kain yang satuannya kg. Label yang salah satuan membuat orang
     gudang menimbang/menghitung barang dengan angka yang salah.

Nilai barcode SELALU kode master (`code`/`sku`). Tidak ada jalan mengetik kode
bebas: label yang kodenya dikarang akan discan menjadi item yang tidak ada.
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone

try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from barcode import Code128
    from barcode.writer import ImageWriter
    import qrcode
    from PIL import Image as PILImage
    LABELS_OK = True
except ImportError:  # pragma: no cover — lingkungan tanpa reportlab
    LABELS_OK = False
    mm = 72 / 25.4
    A4 = (595.27, 841.89)

log = logging.getLogger(__name__)

MATERIAL_LABEL_MM = (90.0, 50.0)
FG_LABEL_MM = (100.0, 70.0)


def label_size(kind: str):
    return FG_LABEL_MM if kind == "fg" else MATERIAL_LABEL_MM


def grid_geometry(page_w: float, page_h: float, lw: float, lh: float):
    """Kolom/baris yang BENAR-BENAR muat di halaman + margin terpusat.

    Dihitung, tidak dihardcode: label yang tidak muat = label yang hilang.
    """
    cols = max(1, int(page_w // lw))
    rows = max(1, int(page_h // lh))
    return cols, rows, (page_w - cols * lw) / 2, (page_h - rows * lh) / 2


def barcode_png(code: str) -> io.BytesIO:
    buf = io.BytesIO()
    Code128(code, writer=ImageWriter()).write(buf, options={
        "module_width": 0.32, "module_height": 9.0, "quiet_zone": 2.0,
        "text_distance": 2.0, "font_size": 6, "write_text": True,
    })
    buf.seek(0)
    return buf


def qr_png(payload: str) -> io.BytesIO:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L,
                       box_size=10, border=2)
    qr.add_data(payload)
    qr.make(fit=True)
    buf = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(buf, "PNG")
    buf.seek(0)
    return buf


def _png_reader(buf: io.BytesIO) -> "ImageReader":
    img = PILImage.open(buf)
    out = io.BytesIO()
    img.save(out, "PNG")
    out.seek(0)
    return ImageReader(out)


def _clip(c, text: str, font: str, size: float, max_w: float) -> str:
    """Potong teks agar tidak menabrak tepi label (bukan hitungan huruf kasar)."""
    text = str(text or "")
    if not text:
        return ""
    if c.stringWidth(text, font, size) <= max_w:
        return text
    while text and c.stringWidth(text + "…", font, size) > max_w:
        text = text[:-1]
    return text + "…"


def unit_of(mat: dict) -> str:
    """Satuan dasar item. `rahaza_materials` memakai `unit`; `uom` hanya alias."""
    return str(mat.get("unit") or mat.get("uom") or "pcs")


def code_of(doc: dict) -> str:
    return str(doc.get("code") or doc.get("sku") or doc.get("sku_code")
               or doc.get("material_code") or "N/A")


def _draw_barcode(c, code, x, y, w, h, fallback_font=("Courier", 6)):
    try:
        c.drawImage(_png_reader(barcode_png(code)), x, y, width=w, height=h,
                    preserveAspectRatio=True, anchor='sw')
    except Exception as e:  # noqa: BLE001
        log.warning("Barcode gagal untuk %s: %s", code, e)
        c.setFont(*fallback_font)
        c.drawString(x, y + h / 2, code)


def draw_material_label(c, x, y, w, h, mat: dict, include_stock: bool = True,
                        border: bool = True):
    """Label bahan/aksesoris. Semua koordinat relatif (x, y) sudut kiri-bawah."""
    pad = 3 * mm
    inner = w - 2 * pad
    if border:
        c.setStrokeColorRGB(0.82, 0.82, 0.82)
        c.setLineWidth(0.4)
        c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFillColorRGB(0.1, 0.1, 0.1)

    code = code_of(mat)
    unit = unit_of(mat)
    category = (mat.get("category") or mat.get("type") or "MATERIAL") or "MATERIAL"

    c.setFont("Helvetica-Bold", 8)
    c.drawString(x + pad, y + h - 7 * mm, "CV. DEWI ADITYA")
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + pad, y + h - 12 * mm, f"KODE: {_clip(c, code, 'Helvetica-Bold', 9, inner - 14 * mm)}")
    c.setFont("Helvetica", 7)
    c.drawString(x + pad, y + h - 17 * mm, _clip(c, mat.get("name") or "", "Helvetica", 7, inner))
    c.setFont("Helvetica", 6)
    c.drawString(x + pad, y + h - 21.5 * mm,
                 _clip(c, f"{str(category).upper()} · satuan: {unit}", "Helvetica", 6, inner))
    if include_stock and mat.get("stock_qty") is not None:
        c.drawString(x + pad, y + h - 25.5 * mm, _clip(
            c, f"Stok: {float(mat.get('stock_qty') or 0):,.2f} {unit} @ {mat.get('location') or '-'}",
            "Helvetica", 6, inner))
    _draw_barcode(c, code, x + pad, y + 4 * mm, inner, 16 * mm)


def draw_fg_label(c, x, y, w, h, fg: dict, border: bool = True):
    """Label barang jadi (SKU + QR + barcode)."""
    pad = 3 * mm
    inner = w - 2 * pad
    if border:
        c.setStrokeColorRGB(0.82, 0.82, 0.82)
        c.setLineWidth(0.4)
        c.rect(x, y, w, h, stroke=1, fill=0)
    c.setFillColorRGB(0.1, 0.1, 0.1)

    sku = code_of(fg)
    name = fg.get("product_name") or fg.get("name") or ""
    style = fg.get("style_code") or fg.get("model_code") or fg.get("model_name") or "-"
    color = fg.get("color_name") or fg.get("color") or "-"
    size = fg.get("size_code") or fg.get("size") or "-"

    c.setFont("Helvetica-Bold", 10)
    c.drawString(x + pad, y + h - 8 * mm, "CV. DEWI ADITYA")
    c.setFont("Helvetica", 7)
    c.drawString(x + pad, y + h - 12.5 * mm, "BARANG JADI")
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x + pad, y + h - 19 * mm, f"SKU: {_clip(c, sku, 'Helvetica-Bold', 11, inner - 12 * mm)}")
    c.setFont("Helvetica", 8)
    c.drawString(x + pad, y + h - 25 * mm, _clip(c, name, "Helvetica", 8, inner))
    c.setFont("Helvetica", 7)
    c.drawString(x + pad, y + h - 30 * mm,
                 _clip(c, f"Model: {style} · Warna: {color} · Ukuran: {size}", "Helvetica", 7, inner))
    batch = fg.get("batch_number") or ""
    if batch:
        c.setFont("Helvetica-Bold", 7)
        c.drawString(x + pad, y + h - 35 * mm, f"Batch: {batch}")

    qr_side = 22 * mm
    try:
        payload = json.dumps({"type": "fg", "sku": sku, "name": name,
                              "size": size, "color": color,
                              "at": datetime.now(timezone.utc).isoformat()})
        c.drawImage(_png_reader(qr_png(payload)), x + pad, y + 3 * mm,
                    width=qr_side, height=qr_side, preserveAspectRatio=True, anchor='sw')
    except Exception as e:  # noqa: BLE001
        log.warning("QR gagal untuk %s: %s", sku, e)
        qr_side = 0
    bx = x + pad + (qr_side + 3 * mm if qr_side else 0)
    _draw_barcode(c, sku, bx, y + 5 * mm, x + w - pad - bx, 18 * mm)


def _draw(c, kind, x, y, lw, lh, doc, include_stock, border=True):
    if kind == "fg":
        draw_fg_label(c, x, y, lw, lh, doc, border=border)
    else:
        draw_material_label(c, x, y, lw, lh, doc, include_stock=include_stock, border=border)


def single_label_pdf(kind: str, doc: dict, include_stock: bool = True) -> io.BytesIO:
    """PDF satu label seukuran labelnya (untuk printer thermal)."""
    lw_mm, lh_mm = label_size(kind)
    lw, lh = lw_mm * mm, lh_mm * mm
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(lw, lh))
    c.setTitle(f"Label {code_of(doc)}")
    _draw(c, kind, 0, 0, lw, lh, doc, include_stock, border=False)
    c.save()
    buf.seek(0)
    return buf


def grid_labels_pdf(kind: str, docs, include_stock: bool = True,
                    title: str = "") -> io.BytesIO:
    """PDF A4 berisi banyak label. `docs` sudah DIKEMBANGKAN (1 elemen = 1 label)."""
    lw_mm, lh_mm = label_size(kind)
    lw, lh = lw_mm * mm, lh_mm * mm
    page_w, page_h = A4
    cols, rows, mx, my = grid_geometry(page_w, page_h, lw, lh)
    per_page = cols * rows

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(title or f"Label batch ({len(docs)})")
    for idx, doc in enumerate(docs):
        slot = idx % per_page
        col, row = slot % cols, slot // cols
        x = mx + col * lw
        y = page_h - my - (row + 1) * lh
        _draw(c, kind, x, y, lw, lh, doc, include_stock)
        if slot == per_page - 1 and idx + 1 < len(docs):
            c.showPage()
    c.save()
    buf.seek(0)
    return buf
