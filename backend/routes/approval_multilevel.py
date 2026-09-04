"""
Multi-Level Approval Workflow — Routes
CV. Dewi Aditya — Task 2.4

Prefix: /api/approvals

Endpoints:
  GET  /chains                         list approval chain configs
  POST /chains                         create chain config
  PUT  /chains/{id}                    update chain config
  DELETE /chains/{id}                  delete (deactivate) chain

  POST /requests                       submit new approval request
  GET  /requests                       list requests (admin/manager)
  GET  /requests/{id}                  detail
  POST /requests/{id}/approve          approve at current level
  POST /requests/{id}/reject           reject at current level
  POST /requests/{id}/cancel           cancel (requester only)

  GET  /pending                        pending items for current user
  GET  /summary                        summary counts for dashboard widget
"""
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, log_activity
from services.approval_chain_service import (
    create_approval_request,
    process_action,
    get_pending_for_user,
    seed_default_chains,
)
from utils.counters import next_counter
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/approvals", tags=["multi-level-approval"])


def _coerce_id(id_str: str):
    """Coba konversi ke int, fallback ke string untuk MongoDB lookup."""
    try:
        return int(id_str)
    except (ValueError, TypeError):
        return id_str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Pydantic models ──────────────────────────────────────────────────────────

class ApprovalLevelModel(BaseModel):
    level: int
    role: str
    label: str


class ChainCreateModel(BaseModel):
    type: str
    name: str
    condition: dict = Field(default_factory=dict)
    levels: List[ApprovalLevelModel]


class ChainUpdateModel(BaseModel):
    name: Optional[str] = None
    condition: Optional[dict] = None
    levels: Optional[List[ApprovalLevelModel]] = None
    is_active: Optional[bool] = None


class RequestCreateModel(BaseModel):
    type: str
    ref_id: str
    ref_code: str
    subject: str = ""
    meta: dict = Field(default_factory=dict)


class ActionModel(BaseModel):
    note: str = ""


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ok(data=None, message="", **kwargs):
    resp = {"status": "ok"}
    if message:
        resp["message"] = message
    if data is not None:
        resp["data"] = data
    resp.update(kwargs)
    return resp


# ─── Chain config endpoints ───────────────────────────────────────────────────

@router.get("/chains")
async def list_chains(
    request: Request,
    type: Optional[str] = None,
    active_only: bool = True,
):
    await require_auth(request)
    db = get_db()
    q = {}
    if active_only:
        q["is_active"] = True
    if type:
        q["type"] = type
    items = await db.approval_chains.find(q, {"_id": 0}).sort("type", 1).to_list(200)
    return _ok(items, total=len(items))


@router.post("/chains")
async def create_chain(request: Request, body: ChainCreateModel):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Hanya admin/owner yang dapat membuat chain.")
    db = get_db()
    chain_id = await next_counter(db, "approval_chains")
    doc = {
        "id": chain_id,
        "type": body.type,
        "name": body.name,
        "condition": body.condition,
        "levels": [lv.dict() for lv in body.levels],
        "is_active": True,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.approval_chains.insert_one({"_id": chain_id, **doc})
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "create",
        "approval_chains",
        f"Chain {chain_id}: {body.dict()}"
    )
    return _ok(doc, message="Chain berhasil dibuat.")


@router.put("/chains/{chain_id}")
async def update_chain(request: Request, chain_id: str, body: ChainUpdateModel):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Hanya admin/owner yang dapat mengubah chain.")
    db = get_db()
    doc = await db.approval_chains.find_one({"id": _coerce_id(chain_id)})
    if not doc:
        raise HTTPException(404, "Chain tidak ditemukan.")
    update = {k: v for k, v in body.dict(exclude_none=True).items()}
    if "levels" in update:
        update["levels"] = [lv.dict() if hasattr(lv, 'dict') else lv for lv in update["levels"]]
    update["updated_at"] = _now()
    await db.approval_chains.update_one({"id": _coerce_id(chain_id)}, {"$set": update})
    return _ok(message="Chain berhasil diupdate.")


@router.delete("/chains/{chain_id}")
async def delete_chain(request: Request, chain_id: str):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Hanya admin/owner yang dapat menghapus chain.")
    db = get_db()
    await db.approval_chains.update_one(
        {"id": _coerce_id(chain_id)}, {"$set": {"is_active": False, "updated_at": _now()}}
    )
    return _ok(message="Chain berhasil dinonaktifkan.")


# ─── Approval request endpoints ────────────────────────────────────────────────

@router.post("/requests")
async def submit_request(request: Request, body: RequestCreateModel):
    user = await require_auth(request)
    db = get_db()
    requester = {
        "id": str(user.get("id") or user.get("_id") or ""),
        "name": user.get("full_name") or user.get("name") or user.get("email") or "",
        "email": user.get("email") or "",
    }
    doc = await create_approval_request(
        db,
        req_type=body.type,
        ref_id=body.ref_id,
        ref_code=body.ref_code,
        requester=requester,
        meta=body.meta,
        subject=body.subject,
    )
    if not doc:
        raise HTTPException(400, f"Tidak ada approval chain yang cocok untuk tipe '{body.type}'.")
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "submit",
        "approval_requests",
        f"Request {doc['id']}: {body.dict()}"
    )
    return _ok(doc, message="Permintaan approval berhasil diajukan.")


@router.get("/requests")
async def list_requests(
    request: Request,
    status: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if type:
        q["type"] = type
    total = await db.approval_requests.count_documents(q)
    items = await db.approval_requests.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return _ok(items, total=total, skip=skip, limit=limit)


@router.get("/requests/{request_id}")
async def get_request(request: Request, request_id: str):
    await require_auth(request)
    db = get_db()
    doc = await db.approval_requests.find_one({"id": _coerce_id(request_id)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Approval request tidak ditemukan.")
    return _ok(doc)


@router.post("/requests/{request_id}/approve")
async def approve_request(request: Request, request_id: str, body: ActionModel):
    user = await require_auth(request)
    db = get_db()
    try:
        updated = await process_action(db, _coerce_id(request_id), "approve", user, body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "approve",
        "approval_requests",
        f"Request {request_id}: {body.note}"
    )
    return _ok(updated, message="Disetujui.")


@router.post("/requests/{request_id}/reject")
async def reject_request(request: Request, request_id: str, body: ActionModel):
    user = await require_auth(request)
    db = get_db()
    try:
        updated = await process_action(db, _coerce_id(request_id), "reject", user, body.note)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "reject",
        "approval_requests",
        f"Request {request_id}: {body.note}"
    )
    return _ok(updated, message="Ditolak.")


@router.post("/requests/{request_id}/cancel")
async def cancel_request(request: Request, request_id: str, body: ActionModel):
    user = await require_auth(request)
    db = get_db()
    doc = await db.approval_requests.find_one({"id": _coerce_id(request_id)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Request tidak ditemukan.")
    requester_id = str(user.get("id") or user.get("_id") or "")
    role = (user.get("role") or "").lower()
    if doc["requester_id"] != requester_id and role not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Hanya requester atau admin yang dapat membatalkan.")
    if doc["status"] not in ("pending",):
        raise HTTPException(400, f"Request sudah {doc['status']}, tidak bisa dibatalkan.")
    now = _now()
    await db.approval_requests.update_one(
        {"id": _coerce_id(request_id)},
        {"$set": {"status": "cancelled", "updated_at": now, "completed_at": now, "cancel_note": body.note}},
    )
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("name") or user.get("email") or "",
        "cancel",
        "approval_requests",
        f"Request {request_id} cancelled"
    )
    return _ok(message="Request dibatalkan.")


# ─── Pending for current user ──────────────────────────────────────────────────

@router.get("/pending")
async def my_pending(request: Request, limit: int = Query(50, ge=1, le=200)):
    user = await require_auth(request)
    db = get_db()
    role = (user.get("role") or "").lower()
    user_id = str(user.get("id") or user.get("_id") or "")
    items = await get_pending_for_user(db, role, user_id, limit)
    return _ok(items, total=len(items))


@router.get("/summary")
async def approval_summary(request: Request):
    user = await require_auth(request)
    db = get_db()
    role = (user.get("role") or "").lower()
    user_id = str(user.get("id") or user.get("_id") or "")

    total_pending = await db.approval_requests.count_documents({"status": "pending"})
    my_pending_list = await get_pending_for_user(db, role, user_id, 200)
    approved_today = await db.approval_requests.count_documents({
        "status": "approved",
        "completed_at": {"$gte": datetime.now(timezone.utc).strftime("%Y-%m-%d")},
    })
    by_type = await db.approval_requests.aggregate([
        {"$group": {"_id": "$type", "count": {"$sum": 1}, "pending": {"$sum": {"$cond": [{"$eq": ["$status", "pending"]}, 1, 0]}}}},
    ]).to_list(50)

    return _ok({
        "total_pending": total_pending,
        "my_pending_count": len(my_pending_list),
        "approved_today": approved_today,
        "by_type": [{"type": b["_id"], "total": b["count"], "pending": b["pending"]} for b in by_type],
    })


@router.post("/seed-chains")
async def seed_chains(request: Request):
    """Seed default approval chains (admin only) — REPLACE ALL."""
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Admin only.")
    db = get_db()
    # Force re-seed
    await db.approval_chains.delete_many({})
    await seed_default_chains(db)
    total = await db.approval_chains.count_documents({})
    return _ok(message=f"Berhasil seed {total} default chains.")


@router.post("/seed-missing-chains")
async def seed_missing_chains(request: Request):
    """Tambah chains yang belum ada — IDEMPOTENT, tidak menghapus yang sudah ada."""
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Admin only.")
    db = get_db()
    from services.approval_chain_service import seed_missing_chains as _seed
    result = await _seed(db)
    return _ok(
        message=f"Ditambahkan {result['added']} chain baru, {result['skipped']} chain sudah ada.",
        data=result,
    )
