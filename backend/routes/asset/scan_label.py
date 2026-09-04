"""Scan / barcode / qrcode / label-PDF endpoints (per asset).

Includes:
  POST /{asset_id}/scan
  GET  /{asset_id}/scan-history
  GET  /{asset_id}/barcode      (PNG)
  GET  /{asset_id}/qrcode       (PNG)
  GET  /{asset_id}/label-pdf    (PDF, supports template=standard|sticker|a4)

Note: /scan-by-number/{num} lives in scan_lookup.py (literal-path module).
"""
import io
import json
import logging
from fastapi import Request, HTTPException
from fastapi.responses import Response

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser

logger = logging.getLogger("asset_mgmt.scan_label")


@router.post("/{asset_id}/scan")
async def scan_asset(asset_id: str, request: Request):
    """Scan asset untuk tracking lokasi/movement."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    scan_doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "asset_number": asset["asset_number"],
        "asset_name": asset["name"],
        "scanned_by": user["id"],
        "scanned_by_name": user.get("name", ""),
        "scan_type": body.get("scan_type", "location_check"),
        "location": (body.get("location") or "").strip(),
        "notes": (body.get("notes") or "").strip(),
        "scanned_at": _now(),
    }
    await db.dewi_asset_scans.insert_one(scan_doc)

    update = {}
    if body.get("location"):
        update["location"] = body["location"]
        update["updated_at"] = _now()
    if update:
        await db.dewi_assets.update_one({"id": asset_id}, {"$set": update})

    return {"ok": True, "scan_id": scan_doc["id"], "asset": _ser(asset)}


@router.get("/{asset_id}/scan-history")
async def get_asset_scan_history(asset_id: str, request: Request):
    """Riwayat scan asset."""
    await require_auth(request)
    db = get_db()
    scans = await db.dewi_asset_scans.find(
        {"asset_id": asset_id}, {"_id": 0}
    ).sort("scanned_at", -1).limit(50).to_list(50)
    return [_ser(s) for s in scans]


@router.get("/{asset_id}/barcode")
async def get_asset_barcode(asset_id: str, request: Request):
    """Generate Code128 barcode image (PNG)."""
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0, "asset_number": 1, "name": 1})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    try:
        import barcode
        from barcode.writer import ImageWriter
        code_val = asset["asset_number"]
        bc_cls = barcode.get_barcode_class("code128")
        bc_obj = bc_cls(code_val, writer=ImageWriter())
        buf = io.BytesIO()
        bc_obj.write(buf, options={"write_text": True, "font_size": 12, "text_distance": 3, "module_height": 12})
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/png")
    except Exception as e:
        logger.error(f"Barcode generation error: {e}")
        raise HTTPException(500, "Gagal generate barcode")


@router.get("/{asset_id}/qrcode")
async def get_asset_qrcode(asset_id: str, request: Request):
    """Generate QR code image (PNG) dengan JSON lengkap + URL link."""
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")
    try:
        import qrcode
        base_url = request.base_url.scheme + "://" + request.base_url.netloc
        qr_data = {
            "type": "asset",
            "asset_id": asset["id"],
            "asset_number": asset["asset_number"],
            "name": asset["name"],
            "category": asset.get("category_name", ""),
            "location": asset.get("location", ""),
            "url": f"{base_url}/asset/{asset['id']}",
        }
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(json.dumps(qr_data))
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return Response(content=buf.read(), media_type="image/png")
    except Exception as e:
        logger.error(f"QR code generation error: {e}")
        raise HTTPException(500, "Gagal generate QR code")


@router.get("/{asset_id}/label-pdf")
async def get_asset_label_pdf(asset_id: str, request: Request, template: str = "standard"):
    """Generate printable label PDF (barcode + QR + asset info).
    Template: standard (90×50mm) | sticker (50×25mm, QR only) | a4 (A4 full page).
    """
    await require_auth(request)
    db = get_db()
    asset = await db.dewi_assets.find_one({"id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import mm
        from reportlab.lib.utils import ImageReader
        import barcode
        from barcode.writer import ImageWriter
        import qrcode

        buf = io.BytesIO()

        templates = {
            "standard": (90 * mm, 50 * mm),
            "sticker": (50 * mm, 25 * mm),
            "a4": (210 * mm, 297 * mm),
        }
        page_size = templates.get(template, templates["standard"])

        c = rl_canvas.Canvas(buf, pagesize=page_size)
        LW, LH = page_size

        if template == "sticker":
            base_url = request.base_url.scheme + "://" + request.base_url.netloc
            qr_data = json.dumps({
                "type": "asset",
                "asset_id": asset["id"],
                "asset_number": asset["asset_number"],
                "url": f"{base_url}/asset/{asset['id']}",
            })
            qr_obj = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                                   box_size=5, border=1)
            qr_obj.add_data(qr_data)
            qr_obj.make(fit=True)
            qr_img = qr_obj.make_image(fill_color="black", back_color="white")
            qr_buf = io.BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            c.drawImage(ImageReader(qr_buf), 2 * mm, 10 * mm, width=20 * mm, height=20 * mm)
            c.setFont("Helvetica-Bold", 7)
            c.drawString(24 * mm, 20 * mm, asset["asset_number"])
            c.setFont("Helvetica", 6)
            c.drawString(24 * mm, 16 * mm, asset["name"][:20])
        else:
            code_val = asset["asset_number"]
            bc_cls = barcode.get_barcode_class("code128")
            bc_obj = bc_cls(code_val, writer=ImageWriter())
            bc_buf = io.BytesIO()
            bc_obj.write(bc_buf, options={"write_text": False, "quiet_zone": 2, "module_height": 10})
            bc_buf.seek(0)
            c.drawImage(ImageReader(bc_buf), 5 * mm, LH - 22 * mm, width=80 * mm, height=18 * mm,
                        preserveAspectRatio=True)

            base_url = request.base_url.scheme + "://" + request.base_url.netloc
            qr_data = json.dumps({
                "type": "asset",
                "asset_id": asset["id"],
                "asset_number": asset["asset_number"],
                "name": asset["name"],
                "category": asset.get("category_name", ""),
                "location": asset.get("location", ""),
                "url": f"{base_url}/asset/{asset['id']}",
            })
            qr_obj = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                                   box_size=5, border=1)
            qr_obj.add_data(qr_data)
            qr_obj.make(fit=True)
            qr_img = qr_obj.make_image(fill_color="black", back_color="white")
            qr_buf = io.BytesIO()
            qr_img.save(qr_buf, format="PNG")
            qr_buf.seek(0)
            c.drawImage(ImageReader(qr_buf), LW - 25 * mm, 5 * mm, width=20 * mm, height=20 * mm)

            c.setFont("Helvetica-Bold", 11)
            c.drawString(5 * mm, LH - 28 * mm, asset["name"][:40])
            c.setFont("Helvetica", 8)
            c.drawString(5 * mm, LH - 33 * mm, f"Kode: {asset['asset_number']}")
            c.drawString(5 * mm, LH - 37 * mm, f"Kategori: {asset.get('category_name', '-')}")
            c.drawString(5 * mm, LH - 41 * mm, f"Lokasi: {asset.get('location', '-')}")
            c.setFont("Helvetica", 6)
            c.drawString(5 * mm, 3 * mm, f"CV. Dewi Aditya • {asset.get('purchase_date', '')}")

        c.showPage()
        c.save()
        buf.seek(0)
        return Response(
            content=buf.read(),
            media_type="application/pdf",
            headers={"Content-Disposition": f'inline; filename="asset-label-{asset["asset_number"]}.pdf"'},
        )
    except Exception as e:
        logger.error(f"Label PDF generation error: {e}")
        raise HTTPException(500, "Gagal generate label PDF")
