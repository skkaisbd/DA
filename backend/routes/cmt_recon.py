"""
routes/cmt_recon.py — Endpoint READ-ONLY: Rekonsiliasi Dispatch (Fase 5 / Konsolidasi).
Menegaskan pemisahan permanen vendor_shipments (maklon/pcs) vs wh_cmt_dispatches (WMS/meter)
dan mendeteksi tumpang-tindih (split-brain). TIDAK menulis / menggabung data.
Prefix: /api/dewi/cmt-recon
"""
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, check_role, serialize_doc
from routes.production_rbac import PROD_ADMIN_ROLES
from services.cmt_recon import dispatch_reconciliation

router = APIRouter(prefix="/api/dewi/cmt-recon", tags=["dewi-cmt-recon"])


@router.get("/dispatch")
async def get_dispatch_recon(request: Request):
    """Rekonsiliasi 2 domain dispatch CMT + deteksi tumpang-tindih. READ-ONLY."""
    user = await require_auth(request)
    if not check_role(user, PROD_ADMIN_ROLES):
        raise HTTPException(403, "Hanya admin produksi/maklon yang boleh mengakses rekonsiliasi dispatch CMT.")
    db = get_db()
    return serialize_doc(await dispatch_reconciliation(db))
