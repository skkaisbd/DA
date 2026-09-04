"""WMS — Label barcode BAHAN (kain, aksesoris, trims, kemasan, potongan).

Endpoint:
  GET  /api/wms/materials/{material_id}/label-pdf   — satu label (90×50 mm)
  POST /api/wms/materials/labels/batch-pdf          — banyak label pada A4

FASE H-3 (2026-08-16): gambar labelnya DIPINDAH ke `core/label_render.py`
(SSOT). Berkas ini tinggal mengurus HTTP + ambil data. Dua cacat yang ikut
tertutup oleh pemindahan itu (rinciannya di docstring core):
  · batch memakai 3 kolom × 90 mm pada A4 selebar 210 mm ⇒ kolom ketiga
    tercetak DI LUAR halaman;
  · satuan dibaca dari `uom` yang tidak ada di `rahaza_materials` (namanya
    `unit`) ⇒ semua label bahan mencetak "pcs", termasuk kain ber-satuan kg.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from auth import require_auth, verify_token_str
from core import label_render as lr
from database import get_db

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/materials", tags=["wms-material-labels"])

MAX_BATCH = 100


async def _auth_or_token(request: Request, token: Optional[str] = None):
    if token:
        user = verify_token_str(token)
        if user:
            return user
    return await require_auth(request)


async def _attach_stock(db, materials: List[dict]):
    """Stok + lokasi utama per material (dipakai di label bila diminta)."""
    ids = [m["id"] for m in materials if m.get("id")]
    if not ids:
        return
    per: dict = {}
    async for s in db.rahaza_material_stock.find(
            {"material_id": {"$in": ids}},
            {"_id": 0, "material_id": 1, "qty": 1, "location_id": 1}):
        per.setdefault(s["material_id"], []).append(s)
    loc_ids = list({s.get("location_id") for rows in per.values()
                    for s in rows if s.get("location_id")})
    loc_map: dict = {}
    if loc_ids:
        # RC-19: SSOT `rahaza_material_stock` memakai `location_id`; labelnya
        # bisa datang dari master lokasi ATAU posisi WMS.
        async for loc in db.rahaza_locations.find(
                {"id": {"$in": loc_ids}}, {"_id": 0, "id": 1, "code": 1, "name": 1}):
            loc_map[loc["id"]] = loc.get("code") or loc.get("name") or "-"
        async for pos in db.wh_positions.find(
                {"id": {"$in": loc_ids}}, {"_id": 0, "id": 1, "label": 1, "barcode": 1}):
            loc_map.setdefault(pos["id"], pos.get("label") or pos.get("barcode") or "-")
    for m in materials:
        rows = per.get(m.get("id")) or []
        if not rows:
            continue
        m["stock_qty"] = sum(float(s.get("qty") or 0) for s in rows)
        main = next((s.get("location_id") for s in rows
                     if float(s.get("qty") or 0) > 0 and s.get("location_id")), None)
        m["location"] = loc_map.get(main, "-")


@router.get("/{material_id}/label-pdf")
async def material_label_pdf(
    material_id: str,
    request: Request,
    token: Optional[str] = Query(None),
    include_stock: bool = Query(True, description="Cetak stok & lokasi di label"),
):
    await _auth_or_token(request, token)
    db = get_db()
    material = await db.rahaza_materials.find_one(
        {"$or": [{"id": material_id}, {"code": material_id}]}, {"_id": 0})
    if not material:
        raise HTTPException(404, f"Material tidak ditemukan: {material_id}")
    if include_stock:
        await _attach_stock(db, [material])
    if not lr.LABELS_OK:
        raise HTTPException(500, "Pustaka pencetak label tidak tersedia")
    pdf = lr.single_label_pdf("material", material, include_stock=include_stock)
    fname = f"material-{material.get('code', material_id)}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class BatchMaterialLabelsIn(BaseModel):
    material_ids: List[str]
    include_stock: bool = True


@router.post("/labels/batch-pdf")
async def batch_material_labels_pdf(data: BatchMaterialLabelsIn, request: Request):
    await require_auth(request)
    if not data.material_ids:
        raise HTTPException(400, "material_ids tidak boleh kosong")
    if len(data.material_ids) > MAX_BATCH:
        raise HTTPException(400, f"Maksimal {MAX_BATCH} material per batch")
    if not lr.LABELS_OK:
        raise HTTPException(500, "Pustaka pencetak label tidak tersedia")

    db = get_db()
    materials = await db.rahaza_materials.find(
        {"$or": [{"id": {"$in": data.material_ids}},
                 {"code": {"$in": data.material_ids}}]}, {"_id": 0}).to_list(MAX_BATCH)
    if not materials:
        raise HTTPException(404, "Tidak ada material ditemukan")
    if data.include_stock:
        await _attach_stock(db, materials)

    pdf = lr.grid_labels_pdf("material", materials, include_stock=data.include_stock,
                             title=f"Material Labels ({len(materials)})")
    return StreamingResponse(pdf, media_type="application/pdf", headers={
        "Content-Disposition":
            f'attachment; filename="material_labels_batch_{len(materials)}.pdf"'})
