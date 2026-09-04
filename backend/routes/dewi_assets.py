"""
CV. Dewi Aditya — Asset Karyawan (Employee Asset Management)

Tracking aset perusahaan yang dipinjamkan ke karyawan:
- CRUD master aset (laptop, seragam, helm, kendaraan, dll.)
- Assignment & return per karyawan
- Cetak label barcode PDF (per aset)

Collections:
  da_assets             — master aset
  da_asset_assignments  — riwayat penugasan per aset
"""
# ruff: noqa: F401

import uuid
import io
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import StreamingResponse
from pymongo import ReturnDocument
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/dewi/assets", tags=["dewi-assets"])

ASSET_CATEGORIES = [
    "Laptop/PC", "Seragam", "Helm/APD", "ID Card", "Kendaraan",
    "Peralatan", "Furnitur", "Handphone", "Kunci/Akses", "Lainnya"
]

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _s(doc):
    if not doc:
        return None
    doc = dict(doc)
    doc.pop("_id", None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc


async def _require_hr(request: Request):
    user = await require_auth(request)
    if (user.get("role") or "").lower() in ("superadmin","admin","owner","hr","manager","supervisor"):
        return user
    raise HTTPException(403, "Akses ditolak.")


# ─── MASTER ASET ─────────────────────────────────────────────────────────────

@router.get("")
async def list_assets(
    request: Request,
    category: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
):
    await require_auth(request)
    db = get_db()
    filt: dict = {}
    if category:
        filt["category"] = category
    if status:
        filt["status"] = status
    if search:
        filt["$or"] = [
            {"asset_name": {"$regex": search, "$options": "i"}},
            {"asset_code": {"$regex": search, "$options": "i"}},
            {"serial_number": {"$regex": search, "$options": "i"}},
        ]
    docs = await db.da_assets.find(filt, {"_id": 0}).sort("asset_code", 1).to_list(500)

    # Enrich with current assignment
    asset_ids = [d["asset_id"] for d in docs]
    assignments = await db.da_asset_assignments.find(
        {"asset_id": {"$in": asset_ids}, "status": "active"}, {"_id": 0}
    ).to_list(500)
    asgn_map = {a["asset_id"]: a for a in assignments}

    emp_ids = [a.get("employee_id") for a in assignments if a.get("employee_id")]
    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1}
    ).to_list(500) if emp_ids else []
    emp_map = {e["id"]: e for e in emps}

    result = []
    for d in docs:
        d = _s(d)
        a = asgn_map.get(d["asset_id"])
        if a:
            emp = emp_map.get(a.get("employee_id"), {})
            d["current_assignment"] = {
                "assignment_id": a["assignment_id"],
                "employee_id": a["employee_id"],
                "employee_name": emp.get("name", "—"),
                "employee_code": emp.get("employee_code", "—"),
                "assigned_date": a.get("assigned_date"),
            }
        else:
            d["current_assignment"] = None
        result.append(d)
    return {"ok": True, "assets": result}


@router.post("")
async def create_asset(request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    name = (body.get("asset_name") or "").strip()
    if not name:
        raise HTTPException(400, "asset_name wajib diisi.")

    doc = {
        "asset_id": _uid(),
        "asset_code": (body.get("asset_code") or "").strip().upper() or f"AST-{_uid()[:6].upper()}",
        "asset_name": name,
        "category": body.get("category") or "Lainnya",
        "serial_number": body.get("serial_number") or "",
        "purchase_date": body.get("purchase_date") or "",
        "purchase_price": float(body.get("purchase_price") or 0),
        "condition": body.get("condition") or "Baik",
        "status": "Available",
        "notes": body.get("notes") or "",
        "created_by": user["id"],
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.da_assets.insert_one(doc)
    return {"ok": True, "asset": _s(doc)}


@router.put("/{asset_id}")
async def update_asset(asset_id: str, request: Request):
    await _require_hr(request)
    db = get_db()
    body = await request.json()
    allowed = ["asset_code","asset_name","category","serial_number","purchase_date",
               "purchase_price","condition","notes"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = _now()
    res = await db.da_assets.update_one({"asset_id": asset_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Aset tidak ditemukan.")
    doc = await db.da_assets.find_one({"asset_id": asset_id}, {"_id": 0})
    return {"ok": True, "asset": _s(doc)}


@router.delete("/{asset_id}")
async def delete_asset(asset_id: str, request: Request):
    await _require_hr(request)
    db = get_db()
    # Check not assigned
    active = await db.da_asset_assignments.find_one({"asset_id": asset_id, "status": "active"})
    if active:
        raise HTTPException(400, "Aset masih sedang ditugaskan. Return dulu sebelum dihapus.")
    await db.da_assets.delete_one({"asset_id": asset_id})
    return {"ok": True}


# ─── ASSIGNMENT ──────────────────────────────────────────────────────────────

@router.post("/{asset_id}/assign")
async def assign_asset(asset_id: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    emp_id = body.get("employee_id")
    emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")

    # ── R10 concurrency hardening (TOCTOU-safe): atomically CLAIM the asset by
    # moving Available→Assigned inside the filter. Only one parallel request can
    # win the claim → no double-assign (CC4).
    asset = await db.da_assets.find_one_and_update(
        {"asset_id": asset_id, "status": "Available"},
        {"$set": {"status": "Assigned", "updated_at": _now()}},
        return_document=ReturnDocument.AFTER,
    )
    if not asset:
        existing = await db.da_assets.find_one({"asset_id": asset_id}, {"_id": 0})
        if not existing:
            raise HTTPException(404, "Aset tidak ditemukan.")
        raise HTTPException(400, f"Aset berstatus '{existing.get('status')}', tidak bisa ditugaskan.")

    asgn = {
        "assignment_id": _uid(),
        "asset_id": asset_id,
        "asset_code": asset.get("asset_code"),
        "asset_name": asset.get("asset_name"),
        "employee_id": emp_id,
        "employee_name": emp.get("name"),
        "employee_code": emp.get("employee_code"),
        "assigned_date": body.get("assigned_date") or _now().date().isoformat(),
        "expected_return_date": body.get("expected_return_date") or "",
        "notes": body.get("notes") or "",
        "assigned_by": user["id"],
        "assigned_by_name": user.get("name", ""),
        "status": "active",
        "created_at": _now(),
    }
    try:
        await db.da_asset_assignments.insert_one(asgn)
    except Exception:
        # Best-effort revert so a failed insert doesn't strand the asset as Assigned.
        await db.da_assets.update_one(
            {"asset_id": asset_id, "status": "Assigned"},
            {"$set": {"status": "Available", "updated_at": _now()}},
        )
        raise HTTPException(500, "Gagal membuat penugasan aset.")
    return {"ok": True, "assignment": _s(asgn)}


@router.post("/{asset_id}/return")
async def return_asset(asset_id: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    active = await db.da_asset_assignments.find_one({"asset_id": asset_id, "status": "active"}, {"_id": 0})
    if not active:
        raise HTTPException(404, "Tidak ada penugasan aktif untuk aset ini.")

    return_date = body.get("return_date") or _now().date().isoformat()
    condition = body.get("condition") or "Baik"

    # ── R10 concurrency hardening (TOCTOU-safe): atomically claim the ACTIVE
    # assignment (active→returned) so parallel returns can't double-process.
    claimed = await db.da_asset_assignments.find_one_and_update(
        {"asset_id": asset_id, "status": "active"},
        {"$set": {
            "status": "returned",
            "return_date": return_date,
            "return_condition": condition,
            "return_notes": body.get("notes") or "",
            "returned_by": user["id"],
            "returned_at": _now(),
        }},
        return_document=ReturnDocument.AFTER,
    )
    if not claimed:
        raise HTTPException(404, "Tidak ada penugasan aktif untuk aset ini.")

    new_status = "Available" if condition == "Baik" else "Maintenance" if condition == "Rusak" else "Disposed"
    await db.da_assets.update_one(
        {"asset_id": asset_id},
        {"$set": {"status": new_status, "condition": condition, "updated_at": _now()}}
    )
    return {"ok": True, "return_date": return_date, "new_status": new_status}


@router.get("/employee/{employee_id}")
async def assets_by_employee(employee_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    assignments = await db.da_asset_assignments.find(
        {"employee_id": employee_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)

    asset_ids = [a["asset_id"] for a in assignments]
    assets = await db.da_assets.find({"asset_id": {"$in": asset_ids}}, {"_id": 0}).to_list(500) if asset_ids else []
    asset_map = {a["asset_id"]: a for a in assets}

    result = []
    for a in assignments:
        a = _s(a)
        asset = _s(asset_map.get(a["asset_id"], {}))
        a["asset_detail"] = asset
        result.append(a)

    return {"ok": True, "assignments": result}


@router.get("/assignments")
async def list_all_assignments(request: Request, status: Optional[str] = "active"):
    await _require_hr(request)
    db = get_db()
    filt = {}
    if status:
        filt["status"] = status
    docs = await db.da_asset_assignments.find(filt, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"ok": True, "assignments": [_s(d) for d in docs]}


# ─── BARCODE LABEL PDF ────────────────────────────────────────────────────────

@router.get("/{asset_id}/label")
async def print_label(asset_id: str, request: Request):
    """Generate PDF barcode label untuk aset."""
    await require_auth(request)
    db = get_db()
    asset = await db.da_assets.find_one({"asset_id": asset_id}, {"_id": 0})
    if not asset:
        raise HTTPException(404, "Aset tidak ditemukan.")

    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.units import mm
        import barcode
        from barcode.writer import ImageWriter

        buf = io.BytesIO()
        # Label size: 90mm × 40mm (landscape)
        LW, LH = 90 * mm, 40 * mm
        c = rl_canvas.Canvas(buf, pagesize=(LW, LH))

        # Barcode
        code_val = asset.get("asset_code", asset_id[:8])
        try:
            bc_cls = barcode.get_barcode_class("code128")
            bc_obj = bc_cls(code_val, writer=ImageWriter())
            bc_buf = io.BytesIO()
            bc_obj.write(bc_buf, options={"write_text": False, "quiet_zone": 2, "module_height": 10})
            bc_buf.seek(0)
            from reportlab.lib.utils import ImageReader
            img = ImageReader(bc_buf)
            c.drawImage(img, 5 * mm, 16 * mm, width=80 * mm, height=18 * mm, preserveAspectRatio=True)
        except Exception:
            c.setFont("Helvetica", 8)
            c.drawString(5 * mm, 20 * mm, f"[{code_val}]")

        # Text
        c.setFont("Helvetica-Bold", 9)
        c.drawString(5 * mm, 10 * mm, asset.get("asset_name", "")[:35])
        c.setFont("Helvetica", 7)
        c.drawString(5 * mm, 6 * mm, f"Kode: {code_val}  |  Kategori: {asset.get('category','')}")
        c.drawString(5 * mm, 3 * mm, f"S/N: {asset.get('serial_number','—')}  |  CV. Dewi Aditya")
        # Border
        c.setStrokeColorRGB(0.2, 0.4, 0.6)
        c.setLineWidth(0.5)
        c.rect(1 * mm, 1 * mm, LW - 2 * mm, LH - 2 * mm)

        c.save()
        buf.seek(0)
        filename = f"label_{code_val}.pdf"
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except ImportError:
        raise HTTPException(500, "reportlab/python-barcode belum terinstall.")


@router.get("/labels/bulk")
async def print_bulk_labels(request: Request, category: Optional[str] = None):
    """Generate PDF semua label aset sekaligus."""
    await require_auth(request)
    db = get_db()
    filt = {}
    if category:
        filt["category"] = category
    assets = await db.da_assets.find(filt, {"_id": 0}).to_list(200)
    if not assets:
        raise HTTPException(404, "Tidak ada aset ditemukan.")

    try:
        from reportlab.pdfgen import canvas as rl_canvas
        from reportlab.lib.units import mm
        from reportlab.lib.pagesizes import A4
        import barcode
        from barcode.writer import ImageWriter
        from reportlab.lib.utils import ImageReader

        buf = io.BytesIO()
        PW, PH = A4
        c = rl_canvas.Canvas(buf, pagesize=A4)

        LW, LH = 85 * mm, 38 * mm
        cols, rows = 2, 7
        x_start, y_start = 10 * mm, PH - 15 * mm
        x_gap, y_gap = 5 * mm, 3 * mm

        cur_col, cur_row = 0, 0
        for asset in assets:
            x = x_start + cur_col * (LW + x_gap)
            y = y_start - (cur_row + 1) * (LH + y_gap)

            code_val = asset.get("asset_code", asset.get("asset_id", "")[:8])
            try:
                bc_cls = barcode.get_barcode_class("code128")
                bc_obj = bc_cls(code_val, writer=ImageWriter())
                bc_buf = io.BytesIO()
                bc_obj.write(bc_buf, options={"write_text": False, "quiet_zone": 2, "module_height": 8})
                bc_buf.seek(0)
                img = ImageReader(bc_buf)
                c.drawImage(img, x + 2 * mm, y + 14 * mm, width=81 * mm, height=15 * mm, preserveAspectRatio=True)
            except Exception:
                c.drawString(x + 2 * mm, y + 20 * mm, f"[{code_val}]")

            c.setFont("Helvetica-Bold", 8)
            c.drawString(x + 2 * mm, y + 9 * mm, asset.get("asset_name", "")[:35])
            c.setFont("Helvetica", 6)
            c.drawString(x + 2 * mm, y + 5 * mm, f"Kode: {code_val}")
            c.drawString(x + 2 * mm, y + 2 * mm, f"{asset.get('category','')}")
            c.setStrokeColorRGB(0.3, 0.5, 0.7)
            c.setLineWidth(0.4)
            c.rect(x, y, LW, LH)

            cur_col += 1
            if cur_col >= cols:
                cur_col = 0
                cur_row += 1
                if cur_row >= rows:
                    c.showPage()
                    cur_row = 0

        c.save()
        buf.seek(0)
        return StreamingResponse(buf, media_type="application/pdf",
                                 headers={"Content-Disposition": 'attachment; filename="labels_aset.pdf"'})
    except ImportError:
        raise HTTPException(500, "reportlab/python-barcode belum terinstall.")
