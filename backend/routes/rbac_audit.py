"""routes/rbac_audit.py — Audit RBAC approval & notifikasi (Portal Sysadmin)."""
from fastapi import APIRouter, HTTPException, Request

from auth import require_auth
from database import get_db
from routes.shared import SUPER_ROLES, can_act

router = APIRouter(prefix="/api/admin/rbac-audit", tags=["rbac-audit"])


@router.get("")
async def get_rbac_audit(request: Request):
    """Hasil audit: endpoint keputusan tanpa izin + notifikasi tanpa target."""
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role not in SUPER_ROLES and not can_act(user, "sysadmin.manage", "settings.manage"):
        raise HTTPException(403, "Akses ditolak: audit RBAC khusus admin/owner.")
    from services.rbac_audit import run_audit
    return await run_audit(get_db())
