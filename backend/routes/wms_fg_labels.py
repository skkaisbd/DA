"""WMS — Label BARANG JADI (FG): SKU + QR + barcode (100×70 mm).

Endpoint:
  GET  /api/wms/fg/{fg_id}/label-pdf     — satu label
  POST /api/wms/fg/labels/batch-pdf      — banyak label pada A4
  POST /api/wms/fg/label-pdf/custom      — label dari data bebas (ad-hoc)

FASE H-3 (2026-08-16) — DUA perbaikan yang bukan kosmetik:

1. **Sumber data FG diperluas ke SSOT yang sebenarnya.** Semua endpoint di sini
   dulu HANYA membaca `rahaza_fg_matrix`, dan koleksi itu **KOSONG (0 dokumen)**
   di basis data ini. Barang jadi yang nyata hidup di `rahaza_materials`
   (`type='fg'`, 332 dokumen, lahir otomatis dari varian master produk). Artinya
   setiap permintaan label FG dijawab **404 "tidak ditemukan"** untuk barang yang
   jelas ADA — cacat yang tidak mungkin terlihat dari daftar endpoint karena
   endpoint-nya sendiri "ada" dan tidak pernah error.

2. Gambar labelnya dipindah ke `core/label_render.py` (SSOT) — sebelumnya
   digambar dua kali (satu label vs batch) dengan kode terpisah.
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
router = APIRouter(prefix="/api/wms/fg", tags=["wms-fg-labels"])

MAX_BATCH = 100


async def _auth_or_token(request: Request, token: Optional[str] = None):
    if token:
        user = verify_token_str(token)
        if user:
            return user
    return await require_auth(request)


async def _find_fg(db, fg_id: str) -> Optional[dict]:
    """Cari FG di matrix lama DULU, lalu di SSOT `rahaza_materials` (type='fg')."""
    fg = await db.rahaza_fg_matrix.find_one(
        {"$or": [{"id": fg_id}, {"sku": fg_id}, {"sku_code": fg_id}]}, {"_id": 0})
    if fg:
        return fg
    return await db.rahaza_materials.find_one(
        {"type": "fg", "$or": [{"id": fg_id}, {"code": fg_id}, {"sku": fg_id}]}, {"_id": 0})


async def _find_fg_many(db, ids: List[str]) -> List[dict]:
    rows = await db.rahaza_fg_matrix.find(
        {"$or": [{"id": {"$in": ids}}, {"sku": {"$in": ids}},
                 {"sku_code": {"$in": ids}}]}, {"_id": 0}).to_list(MAX_BATCH)
    seen = {str(r.get("id"))for r in rows} | {str(r.get("sku")) for r in rows}
    rest = [i for i in ids if i not in seen]
    if rest:
        rows += await db.rahaza_materials.find(
            {"type": "fg", "$or": [{"id": {"$in": rest}}, {"code": {"$in": rest}},
                                   {"sku": {"$in": rest}}]},
            {"_id": 0}).to_list(MAX_BATCH)
    return rows


@router.get("/{fg_id}/label-pdf")
async def fg_label_pdf(fg_id: str, request: Request, token: Optional[str] = Query(None)):
    await _auth_or_token(request, token)
    db = get_db()
    fg = await _find_fg(db, fg_id)
    if not fg:
        raise HTTPException(404, f"Barang jadi tidak ditemukan: {fg_id}")
    if not lr.LABELS_OK:
        raise HTTPException(500, "Pustaka pencetak label tidak tersedia")
    pdf = lr.single_label_pdf("fg", fg)
    fname = f"fg-{lr.code_of(fg)}.pdf"
    return StreamingResponse(pdf, media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{fname}"'})


class BatchFGLabelsIn(BaseModel):
    fg_ids: List[str]


@router.post("/labels/batch-pdf")
async def batch_fg_labels_pdf(data: BatchFGLabelsIn, request: Request):
    await require_auth(request)
    if not data.fg_ids:
        raise HTTPException(400, "fg_ids tidak boleh kosong")
    if len(data.fg_ids) > MAX_BATCH:
        raise HTTPException(400, f"Maksimal {MAX_BATCH} item per batch")
    if not lr.LABELS_OK:
        raise HTTPException(500, "Pustaka pencetak label tidak tersedia")

    db = get_db()
    fg_items = await _find_fg_many(db, data.fg_ids)
    if not fg_items:
        raise HTTPException(404, "Tidak ada barang jadi ditemukan")
    pdf = lr.grid_labels_pdf("fg", fg_items, title=f"FG Labels ({len(fg_items)})")
    return StreamingResponse(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="fg_labels_batch_{len(fg_items)}.pdf"'})


@router.post("/label-pdf/custom")
async def custom_fg_label_pdf(fg: dict, request: Request):
    """Label dari data bebas (ad-hoc) — WAJIB memuat `sku`."""
    await require_auth(request)
    if not fg.get("sku"):
        raise HTTPException(400, "Field 'sku' wajib diisi")
    if not lr.LABELS_OK:
        raise HTTPException(500, "Pustaka pencetak label tidak tersedia")
    pdf = lr.single_label_pdf("fg", fg)
    return StreamingResponse(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="fg-custom-{fg["sku"]}.pdf"'})
