"""
CV. Dewi Aditya — AI Action Items (Phase 8.6)

Menyimpan rekomendasi AI (dari daily summary, root-cause, predictive delay)
sebagai task yang bisa di-assign ke karyawan & di-track sampai selesai.

Collection:
  dewi_ai_actions
    - action_id (UUID)
    - title (string, wajib)
    - description (string)
    - source (daily-summary | root-cause | predictive-delay | chat | manual)
    - source_ref (optional: WO id / chat session / date snippet)
    - priority (low | medium | high | critical)
    - status (open | in_progress | done | dismissed)
    - assignee_id / assignee_name (optional)
    - due_date (YYYY-MM-DD)
    - created_by / created_at / completed_at
    - notes
"""
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Optional
from fastapi import APIRouter, Query, Request, HTTPException
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/dewi/ai-actions", tags=["dewi-ai-actions"])

VALID_SOURCES = {"daily-summary", "root-cause", "predictive-delay", "chat", "manual"}
VALID_PRIORITIES = {"low", "medium", "high", "critical"}
VALID_STATUSES = {"open", "in_progress", "done", "dismissed"}


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _s(d):
    if not d:
        return None
    d = dict(d)
    d.pop("_id", None)
    for k, v in d.items():
        if isinstance(v, datetime):
            d[k] = v.isoformat()
    return d


@router.get("")
async def list_actions(
    request: Request,
    status: Optional[str] = None,
    assignee_id: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
):
    await require_auth(request)
    db = get_db()
    filt: dict = {}
    if status:
        filt["status"] = status
    if assignee_id:
        filt["assignee_id"] = assignee_id
    if source:
        filt["source"] = source
    docs = await db.dewi_ai_actions.find(filt, {"_id": 0}).sort("created_at", -1).to_list(limit)
    return {"ok": True, "actions": [_s(d) for d in docs]}


@router.get("/stats")
async def get_stats(request: Request):
    await require_auth(request)
    db = get_db()
    pipeline = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    stats = {d["_id"]: d["count"] async for d in db.dewi_ai_actions.aggregate(pipeline)}
    # Due soon (open, due within 3 days)
    today = date.today().isoformat()
    in_3 = (date.today() + timedelta(days=3)).isoformat()
    due_soon = await db.dewi_ai_actions.count_documents({
        "status": {"$in": ["open", "in_progress"]},
        "due_date": {"$gte": today, "$lte": in_3},
    })
    overdue = await db.dewi_ai_actions.count_documents({
        "status": {"$in": ["open", "in_progress"]},
        "due_date": {"$lt": today},
    })
    return {
        "ok": True,
        "open": stats.get("open", 0),
        "in_progress": stats.get("in_progress", 0),
        "done": stats.get("done", 0),
        "dismissed": stats.get("dismissed", 0),
        "due_soon": due_soon,
        "overdue": overdue,
    }


@router.post("")
async def create_action(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    title = (body.get("title") or "").strip()
    if not title:
        raise HTTPException(400, "title wajib diisi.")

    source = body.get("source") or "manual"
    if source not in VALID_SOURCES:
        raise HTTPException(400, f"source tidak valid. Pilih: {', '.join(VALID_SOURCES)}")

    priority = body.get("priority") or "medium"
    if priority not in VALID_PRIORITIES:
        priority = "medium"

    # Resolve assignee if provided
    assignee_id = body.get("assignee_id") or None
    assignee_name = body.get("assignee_name") or None
    if assignee_id and not assignee_name:
        emp = await db.rahaza_employees.find_one({"id": assignee_id}, {"_id": 0, "name": 1})
        if emp:
            assignee_name = emp.get("name")

    doc = {
        "action_id": _uid(),
        "title": title,
        "description": body.get("description") or "",
        "source": source,
        "source_ref": body.get("source_ref") or "",
        "priority": priority,
        "status": "open",
        "assignee_id": assignee_id,
        "assignee_name": assignee_name,
        "due_date": body.get("due_date") or "",
        "notes": body.get("notes") or "",
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
        "completed_at": None,
    }
    await db.dewi_ai_actions.insert_one(doc)
    return {"ok": True, "action": _s(doc)}


@router.put("/{action_id}")
async def update_action(action_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    allowed = ["title", "description", "priority", "status", "assignee_id",
               "assignee_name", "due_date", "notes"]
    upd = {k: body[k] for k in allowed if k in body}

    if "status" in upd and upd["status"] not in VALID_STATUSES:
        raise HTTPException(400, "status tidak valid.")
    if "priority" in upd and upd["priority"] not in VALID_PRIORITIES:
        raise HTTPException(400, "priority tidak valid.")

    # Auto-populate assignee_name if assignee_id changed
    if upd.get("assignee_id") and not upd.get("assignee_name"):
        emp = await db.rahaza_employees.find_one({"id": upd["assignee_id"]}, {"_id": 0, "name": 1})
        if emp:
            upd["assignee_name"] = emp.get("name")

    if upd.get("status") == "done":
        upd["completed_at"] = _now()
        upd["completed_by"] = user["id"]
    elif upd.get("status") in ("open", "in_progress"):
        upd["completed_at"] = None

    upd["updated_at"] = _now()
    res = await db.dewi_ai_actions.update_one({"action_id": action_id}, {"$set": upd})
    if res.matched_count == 0:
        raise HTTPException(404, "Action tidak ditemukan.")
    doc = await db.dewi_ai_actions.find_one({"action_id": action_id}, {"_id": 0})
    return {"ok": True, "action": _s(doc)}


@router.delete("/{action_id}")
async def delete_action(action_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.dewi_ai_actions.delete_one({"action_id": action_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Action tidak ditemukan.")
    return {"ok": True}
