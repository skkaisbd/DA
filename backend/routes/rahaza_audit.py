"""
PT Rahaza ERP — Audit Trail (Phase 12.3)

Koleksi: rahaza_audit_logs
  {id, entity_type, entity_id, action, user_id, user_name,
   before, after, diff, timestamp, ip}

Helper:
  - log_audit(db, entity_type, entity_id, action, before, after, user, request=None)
  - compute_diff(before, after) — field-level change set

Endpoint:
  - GET /api/audit-logs?entity_type=&entity_id=&action=&limit=
"""
from fastapi import APIRouter, Request
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
import uuid
from utils.query_guards import q_int

router = APIRouter(prefix="/api/audit-logs", tags=["Audit"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def compute_diff(before: dict, after: dict) -> dict:
    """Compute field-level diff: {field: {before, after}} untuk field yang berubah."""
    if not isinstance(before, dict):
        before = {}
    if not isinstance(after, dict):
        after = {}
    diff = {}
    all_keys = set(before.keys()) | set(after.keys())
    for k in all_keys:
        if k in ("_id", "updated_at"):  # skip noise
            continue
        b = before.get(k)
        a = after.get(k)
        if b != a:
            diff[k] = {"before": b, "after": a}
    return diff


async def log_audit(db, *, entity_type: str, entity_id: str, action: str,
                    before: dict = None, after: dict = None,
                    user: dict = None, request: Request = None):
    """Insert 1 audit log entry. Never raise — audit failure tidak boleh break flow utama."""
    try:
        diff = compute_diff(before or {}, after or {})
        ip = None
        if request:
            ip = request.client.host if request.client else None
        doc = {
            "id": str(uuid.uuid4()),
            "entity_type": entity_type,
            "entity_id": entity_id,
            "action": action,  # 'create' | 'update' | 'delete' | 'status_change' | 'confirm' | 'cancel' | 'approve'
            "user_id": (user or {}).get("id") or (user or {}).get("user_id"),
            "user_name": (user or {}).get("name") or (user or {}).get("email"),
            "user_role": (user or {}).get("role"),
            "before": before,
            "after": after,
            "diff": diff,
            "ip": ip,
            "timestamp": _now(),
        }
        await db.rahaza_audit_logs.insert_one(dict(doc))
        return doc
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"audit log failed: {e}")
        return None


@router.get("")
async def list_audit_logs(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    q = {}
    if sp.get("entity_type"):
        q["entity_type"] = sp["entity_type"]
    if sp.get("entity_id"):
        q["entity_id"] = sp["entity_id"]
    if sp.get("action"):
        q["action"] = sp["action"]
    if sp.get("user_id"):
        q["user_id"] = sp["user_id"]
    limit = q_int(sp.get("limit"), default=100, name="limit", minimum=1, maximum=500, clamp=True)
    rows = await db.rahaza_audit_logs.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(500)
    return {"items": rows, "total": len(rows)}
