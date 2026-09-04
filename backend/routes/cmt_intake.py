"""
routes/cmt_intake.py — Endpoint READ-ONLY: INTAKE BENAR (Fase 3 / S1 POTONGAN MASUK + cek-seri).

Semua agregasi dari SSOT via services/cmt_intake.py. TIDAK menulis data, TIDAK ada field baru.
Sumber seri = po_items.serial_number (yang sudah ada). Sumber potongan masuk = vendor_shipments.
Prefix: /api/dewi/cmt-intake
"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from routes.production_rbac import PROD_ADMIN_ROLES
from routes.shared import can_act
from services.cmt_intake import cek_seri, serial_lookup, intake_batches

router = APIRouter(prefix="/api/dewi/cmt-intake", tags=["dewi-cmt-intake"])


def _require_admin(user: dict):
    # 2026-08-06 — gerbang izin terpusat (routes.shared.can_act, fallback aman).
    if not can_act(user, "cmt.view", "cmt.intake.manage", "production.manage",
                   legacy_roles=PROD_ADMIN_ROLES):
        raise HTTPException(403, "Akses ditolak: butuh izin monitoring intake CMT (cmt.view).")


@router.get("/cek-seri")
async def get_cek_seri(
    request: Request,
    scope: str = Query("maklon", description="maklon|all"),
):
    """Laporan deteksi seri DOBEL antar baris PO (po_items.serial_number). READ-ONLY."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    if scope not in ("maklon", "all"):
        scope = "maklon"
    return serialize_doc(await cek_seri(db, scope=scope))


@router.get("/serial-lookup")
async def get_serial_lookup(
    request: Request,
    serial: str = Query(..., min_length=1, description="Nomor seri yang dicek"),
    exclude_po_id: Optional[str] = Query(None),
    exclude_item_id: Optional[str] = Query(None),
    scope: str = Query("all", description="all|maklon"),
):
    """Cek 1 seri untuk PERINGATAN saat BUAT ORDER (tidak block). READ-ONLY."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    if scope not in ("maklon", "all"):
        scope = "all"
    return serialize_doc(await serial_lookup(
        db, serial=serial, exclude_po_id=exclude_po_id,
        exclude_item_id=exclude_item_id, scope=scope,
    ))


@router.get("/batches")
async def get_intake_batches(
    request: Request,
    po_id: Optional[str] = Query(None, description="Filter 1 PO"),
    scope: str = Query("maklon", description="maklon|all"),
):
    """View per-batch POTONGAN MASUK (DA→CMT) dari vendor_shipments. READ-ONLY."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    if scope not in ("maklon", "all"):
        scope = "maklon"
    return serialize_doc(await intake_batches(db, po_id=po_id, scope=scope))
