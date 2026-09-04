# ruff: noqa: F401, F811
"""
operations.py — Thin Orchestrator (Deprecated Accessory Stubs Only)

Refactored: Session #11.19 Phase 3.2 — Backend Monster Routes Cleanup
Previous: 2354 LOC monolith with all operations logic
Current: ~200 LOC stub-only orchestrator

Active operations endpoints moved to focused sub-modules:
- operations_reminders.py  — Vendor reminder CRUD
- operations_serials.py    — Serial tracking & timeline
- operations_reports.py    — Report generation
- operations_import.py     — Data import & templates
- operations_export.py     — Excel/PDF export + PDF config CRUD

DEPRECATION NOTICE (Session #11.14 + Sprint A.0):
This module only contains LEGACY ORPHAN `/api/accessories/*` and
`/api/accessory-*` stub endpoints that return empty arrays or 410 Gone.
These collections were dropped in Phase A.0. Active accessory operations
now go through `/api/acc/items/*` (rahaza_materials SSOT with type='accessory')
and `/api/dewi/accessory-requests/*`.

See FORENSIC_04 Cluster 1 for full accessory consolidation history.
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth
from routes.shared import get_pagination_params, paginated_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["operations"])

logger.info(
    "[DEPRECATION] /api/accessories/* (legacy orphan) is DEPRECATED — superseded by "
    "/api/acc/items/* (rahaza_materials SSOT, filter type='accessory'). "
    "See FORENSIC_04 Cluster 1."
)

# ─── ACCESSORY MANAGEMENT (DEPRECATED — use /api/acc/items instead) ─────────
_ACC_DEPR_MSG = (
    "DEPRECATED: /api/accessories/* — use /api/acc/items/* (rahaza_materials SSOT). "
    "Collection dropped. See FORENSIC_04 Cluster 1 + Sprint A.0."
)
_ACC_REQ_DEPR_MSG = (
    "DEPRECATED: /api/accessory-requests/* — use /api/dewi/accessory-requests. "
    "Collection dropped. See P3 TD-009 + Sprint A.0."
)


@router.get("/accessories")
async def get_accessories(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] GET /api/accessories called — %s", _ACC_DEPR_MSG)
    sp = request.query_params
    empty: list = []
    if sp.get('page') or sp.get('limit'):
        page, limit, _ = get_pagination_params(request, default_limit=50)
        return paginated_response(empty, 0, page, limit)
    return empty


@router.post("/accessories")
async def create_accessory(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] POST /api/accessories called — %s", _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


@router.put("/accessories/{acc_id}")
async def update_accessory(acc_id: str, request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] PUT /api/accessories/%s called — %s", acc_id, _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


@router.delete("/accessories/{acc_id}")
async def delete_accessory(acc_id: str, request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] DELETE /api/accessories/%s called — %s", acc_id, _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


# ─── ACCESSORY SHIPMENTS (DEPRECATED — Sprint A.0) ───────────────────────────
@router.get("/accessory-shipments")
async def get_acc_shipments(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] GET /api/accessory-shipments — %s", _ACC_DEPR_MSG)
    sp = request.query_params
    empty: list = []
    if sp.get('page') or sp.get('limit'):
        page, limit, _ = get_pagination_params(request, default_limit=50)
        return paginated_response(empty, 0, page, limit)
    return empty


@router.post("/accessory-shipments")
async def create_acc_shipment(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] POST /api/accessory-shipments — %s", _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


@router.put("/accessory-shipments/{sid}")
async def update_acc_shipment(sid: str, request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] PUT /api/accessory-shipments/%s — %s", sid, _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


@router.delete("/accessory-shipments/{sid}")
async def delete_acc_shipment(sid: str, request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] DELETE /api/accessory-shipments/%s — %s", sid, _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


# ─── ACCESSORY INSPECTIONS (DEPRECATED — Sprint A.0) ─────────────────────────
@router.get("/accessory-inspections")
async def get_acc_inspections(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] GET /api/accessory-inspections — %s", _ACC_DEPR_MSG)
    sp = request.query_params
    empty: list = []
    if sp.get('page') or sp.get('limit'):
        page, limit, _ = get_pagination_params(request, default_limit=50)
        return paginated_response(empty, 0, page, limit)
    return empty


@router.post("/accessory-inspections")
async def create_acc_inspection(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] POST /api/accessory-inspections — %s", _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


# ─── ACCESSORY DEFECTS (DEPRECATED — Sprint A.0) ─────────────────────────────
@router.get("/accessory-defects")
async def get_acc_defects(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] GET /api/accessory-defects — %s", _ACC_DEPR_MSG)
    sp = request.query_params
    empty: list = []
    if sp.get('page') or sp.get('limit'):
        page, limit, _ = get_pagination_params(request, default_limit=50)
        return paginated_response(empty, 0, page, limit)
    return empty


@router.post("/accessory-defects")
async def create_acc_defect(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] POST /api/accessory-defects — %s", _ACC_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/acc/items", "message": _ACC_DEPR_MSG})


# ─── ACCESSORY REQUESTS (DEPRECATED — Sprint A.0, P3 TD-009) ─────────────────
@router.get("/accessory-requests")
async def get_acc_requests(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] GET /api/accessory-requests — %s", _ACC_REQ_DEPR_MSG)
    sp = request.query_params
    empty: list = []
    if sp.get('page') or sp.get('limit'):
        page, limit, _ = get_pagination_params(request, default_limit=50)
        return paginated_response(empty, 0, page, limit)
    return empty


@router.post("/accessory-requests")
async def create_acc_request(request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] POST /api/accessory-requests — %s", _ACC_REQ_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/dewi/accessory-requests", "message": _ACC_REQ_DEPR_MSG})


@router.put("/accessory-requests/{req_id}")
async def update_acc_request(req_id: str, request: Request):
    await require_auth(request)
    logger.warning("[DEPRECATED-NOOP] PUT /api/accessory-requests/%s — %s", req_id, _ACC_REQ_DEPR_MSG)
    raise HTTPException(410, detail={"deprecated": True, "use": "/api/dewi/accessory-requests", "message": _ACC_REQ_DEPR_MSG})
