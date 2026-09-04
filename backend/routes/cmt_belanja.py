"""
routes/cmt_belanja.py — Endpoint READ-ONLY: BELANJA (Fase 4).
- GET /rekap-aksesoris : kebutuhan aksesoris (po_accessories + BOM×qty) per PO maklon.
- GET /kapasitas       : beban (outstanding di CMT) vs kapasitas (vendor_partners.capacity_pcs).

Semua agregasi dari SSOT via services/cmt_belanja.py. TIDAK menulis data.
(Set kapasitas dilakukan lewat owner-nya: PUT /api/vendor-portal/partners/{id} — field capacity_pcs.)
Prefix: /api/dewi/cmt-belanja
"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from routes.production_rbac import PROD_ADMIN_ROLES
from routes.shared import can_act
from services.cmt_belanja import rekap_aksesoris, capacity_overview

router = APIRouter(prefix="/api/dewi/cmt-belanja", tags=["dewi-cmt-belanja"])


def _require_admin(user: dict):
    # 2026-08-06 — gerbang izin terpusat (routes.shared.can_act, fallback aman).
    if not can_act(user, "cmt.view", "cmt.belanja.manage", "production.manage",
                   legacy_roles=PROD_ADMIN_ROLES):
        raise HTTPException(403, "Akses ditolak: butuh izin rekap belanja CMT (cmt.view).")


@router.get("/rekap-aksesoris")
async def get_rekap_aksesoris(
    request: Request,
    po_id: Optional[str] = Query(None, description="Filter 1 PO"),
    include_closed: bool = Query(False, description="Ikutkan PO Closed/Cancelled"),
):
    """Rekap kebutuhan aksesoris (po_accessories + turunan BOM). READ-ONLY."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    return serialize_doc(await rekap_aksesoris(db, po_id=po_id, only_open=not include_closed))


@router.get("/kapasitas")
async def get_kapasitas(request: Request):
    """Beban vs kapasitas per vendor CMT (vendor_partners.capacity_pcs). READ-ONLY."""
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    return serialize_doc(await capacity_overview(db))
