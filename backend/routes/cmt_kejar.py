"""
routes/cmt_kejar.py — Endpoint READ-ONLY: KEJAR CMT (S3/M4/M5) + Dashboard Owner CMT (M2).
Semua agregasi dari SSOT via services/cmt_kejar.py. Tidak menulis data.
Prefix: /api/dewi/cmt-kejar
"""
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth
from routes.production_rbac import PROD_ADMIN_ROLES
from routes.shared import can_act
from services.cmt_kejar import list_kejar, owner_dashboard, compute_po_kejar, get_buffer_config

router = APIRouter(prefix="/api/dewi/cmt-kejar", tags=["dewi-cmt-kejar"])


def _require_admin(user: dict):
    # 2026-08-06 — gerbang izin terpusat (routes.shared.can_act, fallback aman).
    if not can_act(user, "cmt.view", "cmt.kejar.manage", "production.manage",
                   legacy_roles=PROD_ADMIN_ROLES):
        raise HTTPException(403, "Akses ditolak: butuh izin monitoring CMT (cmt.view).")


@router.get("")
async def get_kejar(
    request: Request,
    bucket: Optional[str] = Query(None, description="telat|jatuh_tempo|mendekati|on_track|aman|tanpa_deadline"),
    include_closed: bool = False,
    scope: Optional[str] = Query(None, description="running (default, PO berjalan) | all"),
):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    return await list_kejar(db, bucket=bucket, only_open=not include_closed, scope=scope)


@router.get("/dashboard")
async def get_owner_dashboard(
    request: Request,
    scope: Optional[str] = Query(None, description="running (default, PO berjalan) | all"),
):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    return await owner_dashboard(db, scope=scope)


@router.get("/po/{po_id}")
async def get_po_kejar(po_id: str, request: Request):
    user = await require_auth(request)
    _require_admin(user)
    db = get_db()
    po = await db.production_pos.find_one({"id": po_id, "business_type": "maklon"}, {"_id": 0})
    if not po:
        raise HTTPException(404, "PO maklon tidak ditemukan")
    cfg = await get_buffer_config(db)
    return await compute_po_kejar(db, po, cfg)
