"""
Portal Saya - Orchestrator
Self-Service Employee Portal + Personal Workspace
"""
from fastapi import APIRouter
from routes import (
    dewi_portal_saya_hr,
    dewi_portal_saya_workspace
)

router = APIRouter(prefix="/api/portal", tags=["portal-saya"])

router.include_router(dewi_portal_saya_hr.router, prefix="")
router.include_router(dewi_portal_saya_workspace.router, prefix="")
