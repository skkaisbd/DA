"""
Portal Saya - Workspace
Notes, Todos, Reminders, Quick Links, Calendar
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(tags=["portal-workspace"])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _now_iso(): return _now().isoformat()

async def _get_linked_employee(db, user_id: str):
    """Wrapper tipis di atas SSOT `utils.employee_identity` (FASE 15).

    DULU modul ini hanya melihat `users.employee_id`; kalau tautan itu belum
    dibuat, Portal Saya menampilkan halaman kosong padahal karyawannya ada
    (cocok lewat `user_id`/email). Empat modul punya versi berbeda-beda —
    sekarang semuanya memakai satu resolver.
    """
    from utils.employee_identity import resolve_my_employee
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return user, None
    return user, await resolve_my_employee(db, user)

@router.get("/notes")
async def list_notes(request: Request, skip: int = 0, limit: int = 50):
    user = await require_auth(request)
    db = get_db()
    q = {"user_id": user["id"]}
    total = await db.portal_notes.count_documents(q)
    rows = await db.portal_notes.find(q, {"_id": 0}).sort(
        [("is_pinned", -1), ("updated_at", -1)]
    ).skip(skip).limit(limit).to_list(500)
    return {"total": total, "skip": skip, "limit": limit, "has_more": (skip + limit) < total, "items": rows}


@router.post("/notes")
async def create_note(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    doc = {
        "id": _uid(),
        "user_id": user["id"],
        "title": body.get("title", "Catatan Baru"),
        "content": body.get("content", ""),
        "color": body.get("color", "#ffffff"),
        "is_pinned": body.get("is_pinned", False),
        "tags": body.get("tags", []),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.portal_notes.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/notes/{note_id}")
async def update_note(note_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    note = await db.portal_notes.find_one({"id": note_id, "user_id": user["id"]})
    if not note:
        raise HTTPException(404, "Catatan tidak ditemukan.")
    body = await request.json()
    allowed = ["title", "content", "color", "is_pinned", "tags"]
    upd = {k: v for k, v in body.items() if k in allowed}
    upd["updated_at"] = _now_iso()
    await db.portal_notes.update_one({"id": note_id}, {"$set": upd})
    out = await db.portal_notes.find_one({"id": note_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/notes/{note_id}")
async def delete_note(note_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.portal_notes.delete_one({"id": note_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Catatan tidak ditemukan.")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════
# WORKSPACE — TODOS
# ══════════════════════════════════════════════════════════════

@router.get("/todos")
async def list_todos(
    request: Request,
    done: Optional[bool] = None,
    priority: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
):
    user = await require_auth(request)
    db = get_db()
    q = {"user_id": user["id"]}
    if done is not None:
        q["done"] = done
    if priority:
        q["priority"] = priority
    total = await db.portal_todos.count_documents(q)
    rows = await db.portal_todos.find(q, {"_id": 0}).sort(
        [("done", 1), ("priority_order", 1), ("created_at", -1)]
    ).skip(skip).limit(limit).to_list(500)
    return {"total": total, "skip": skip, "limit": limit, "has_more": (skip + limit) < total, "items": rows}


@router.post("/todos")
async def create_todo(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    title = body.get("title", "").strip()
    if not title:
        raise HTTPException(400, "title wajib diisi.")
    priority = body.get("priority", "medium")
    priority_order = {"high": 1, "medium": 2, "low": 3}.get(priority, 2)
    doc = {
        "id": _uid(),
        "user_id": user["id"],
        "title": title,
        "notes": body.get("notes", ""),
        "done": False,
        "priority": priority,
        "priority_order": priority_order,
        "due_date": body.get("due_date", ""),
        "tags": body.get("tags", []),
        "done_at": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.portal_todos.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/todos/{todo_id}")
async def update_todo(todo_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    todo = await db.portal_todos.find_one({"id": todo_id, "user_id": user["id"]})
    if not todo:
        raise HTTPException(404, "Todo tidak ditemukan.")
    body = await request.json()
    allowed = ["title", "notes", "done", "priority", "due_date", "tags"]
    upd = {k: v for k, v in body.items() if k in allowed}
    if "priority" in upd:
        upd["priority_order"] = {"high": 1, "medium": 2, "low": 3}.get(upd["priority"], 2)
    if upd.get("done") is True and not todo.get("done"):
        upd["done_at"] = _now_iso()
    elif upd.get("done") is False:
        upd["done_at"] = None
    upd["updated_at"] = _now_iso()
    await db.portal_todos.update_one({"id": todo_id}, {"$set": upd})
    out = await db.portal_todos.find_one({"id": todo_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/todos/{todo_id}")
async def delete_todo(todo_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.portal_todos.delete_one({"id": todo_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Todo tidak ditemukan.")
    return {"ok": True}


# ══════════════════════════════════════════════════════════════
# WORKSPACE — REMINDERS
# ══════════════════════════════════════════════════════════════

@router.get("/reminders")
async def list_reminders(request: Request, show_done: bool = False, skip: int = 0, limit: int = 50):
    user = await require_auth(request)
    db = get_db()
    q = {"user_id": user["id"]}
    if not show_done:
        q["is_done"] = False
    total = await db.portal_reminders.count_documents(q)
    rows = await db.portal_reminders.find(q, {"_id": 0}).sort("remind_at", 1).skip(skip).limit(limit).to_list(500)
    return {"total": total, "skip": skip, "limit": limit, "has_more": (skip + limit) < total, "items": rows}


@router.post("/reminders")
async def create_reminder(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    title = body.get("title", "").strip()
    remind_at = body.get("remind_at", "")
    if not title:
        raise HTTPException(400, "title wajib diisi.")
    doc = {
        "id": _uid(),
        "user_id": user["id"],
        "title": title,
        "description": body.get("description", ""),
        "remind_at": remind_at,
        "recurrence": body.get("recurrence", "once"),  # once/daily/weekly
        "is_done": False,
        "whatsapp_enabled": body.get("whatsapp_enabled", False),
        "whatsapp_number": body.get("whatsapp_number", ""),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.portal_reminders.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/reminders/{rem_id}")
async def update_reminder(rem_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    rem = await db.portal_reminders.find_one({"id": rem_id, "user_id": user["id"]})
    if not rem:
        raise HTTPException(404, "Reminder tidak ditemukan.")
    body = await request.json()
    allowed = ["title", "description", "remind_at", "recurrence", "is_done", "whatsapp_enabled", "whatsapp_number"]
    upd = {k: v for k, v in body.items() if k in allowed}
    upd["updated_at"] = _now_iso()
    await db.portal_reminders.update_one({"id": rem_id}, {"$set": upd})
    out = await db.portal_reminders.find_one({"id": rem_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/reminders/{rem_id}")
async def delete_reminder(rem_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.portal_reminders.delete_one({"id": rem_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Reminder tidak ditemukan.")
    return {"ok": True}


@router.get("/reminders/due")
async def get_due_reminders(request: Request):
    """Get reminders that are due (for notification polling)."""
    user = await require_auth(request)
    db = get_db()
    now_iso = _now_iso()
    rows = await db.portal_reminders.find(
        {"user_id": user["id"], "is_done": False, "remind_at": {"$lte": now_iso}},
        {"_id": 0}
    ).to_list(20)
    return {"items": rows}


# ══════════════════════════════════════════════════════════════
# WORKSPACE — QUICK LINKS
# ══════════════════════════════════════════════════════════════

@router.get("/quick-links")
async def list_quick_links(request: Request):
    user = await require_auth(request)
    db = get_db()
    rows = await db.portal_quick_links.find(
        {"user_id": user["id"]}, {"_id": 0}
    ).sort("order_seq", 1).to_list(50)
    return {"total": len(rows), "items": rows}


@router.post("/quick-links")
async def add_quick_link(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    label = body.get("label", "").strip()
    module_id = body.get("module_id", "").strip()
    if not label or not module_id:
        raise HTTPException(400, "label dan module_id wajib diisi.")
    # Get next order
    max_seq = await db.portal_quick_links.count_documents({"user_id": user["id"]})
    doc = {
        "id": _uid(),
        "user_id": user["id"],
        "module_id": module_id,
        "label": label,
        "icon": body.get("icon", "link"),
        "portal": body.get("portal", ""),
        "order_seq": max_seq,
        "created_at": _now_iso(),
    }
    await db.portal_quick_links.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/quick-links/reorder")
async def reorder_quick_links(request: Request):
    """Receives [{id, order_seq}] and bulk-updates all links for the user."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()   # list of {id, order_seq}
    items = body if isinstance(body, list) else body.get("items", [])
    for item in items:
        if item.get("id"):
            await db.portal_quick_links.update_one(
                {"id": item["id"], "user_id": user["id"]},
                {"$set": {"order_seq": int(item.get("order_seq", 0))}}
            )
    return {"ok": True, "updated": len(items)}


@router.put("/quick-links/{link_id}")
async def update_quick_link(link_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    lnk = await db.portal_quick_links.find_one({"id": link_id, "user_id": user["id"]})
    if not lnk:
        raise HTTPException(404, "Quick link tidak ditemukan.")
    body = await request.json()
    allowed = ["label", "icon", "order_seq"]
    upd = {k: v for k, v in body.items() if k in allowed}
    await db.portal_quick_links.update_one({"id": link_id}, {"$set": upd})
    out = await db.portal_quick_links.find_one({"id": link_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/quick-links/{link_id}")
async def delete_quick_link(link_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.portal_quick_links.delete_one({"id": link_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Quick link tidak ditemukan.")
    # Renumber remaining links to keep seq contiguous
    remaining = await db.portal_quick_links.find(
        {"user_id": user["id"]}, {"_id": 0, "id": 1}
    ).sort("order_seq", 1).to_list(50)
    for i, r in enumerate(remaining):
        await db.portal_quick_links.update_one({"id": r["id"]}, {"$set": {"order_seq": i}})
    return {"ok": True}


# ══════════════════════════════════════════════════════════════
# WORKSPACE — CALENDAR EVENTS
# ══════════════════════════════════════════════════════════════

@router.get("/calendar")
async def list_calendar_events(
    request: Request,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
):
    user = await require_auth(request)
    db = get_db()
    q = {"user_id": user["id"]}
    if from_:
        q["date"] = {"$gte": from_}
    if to:
        q.setdefault("date", {})["$lte"] = to
    rows = await db.portal_calendar_events.find(q, {"_id": 0}).sort("date", 1).to_list(200)
    return {"total": len(rows), "items": rows}


@router.post("/calendar")
async def create_calendar_event(request: Request):
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    title = body.get("title", "").strip()
    ev_date = body.get("date", "")
    if not title or not ev_date:
        raise HTTPException(400, "title dan date wajib diisi.")
    doc = {
        "id": _uid(),
        "user_id": user["id"],
        "title": title,
        "date": ev_date,
        "end_date": body.get("end_date", ev_date),
        "time": body.get("time", ""),
        "description": body.get("description", ""),
        "color": body.get("color", "#6366f1"),
        "type": "personal",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.portal_calendar_events.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.put("/calendar/{event_id}")
async def update_calendar_event(event_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    ev = await db.portal_calendar_events.find_one({"id": event_id, "user_id": user["id"]})
    if not ev:
        raise HTTPException(404, "Event tidak ditemukan.")
    body = await request.json()
    allowed = ["title", "date", "end_date", "time", "description", "color"]
    upd = {k: v for k, v in body.items() if k in allowed}
    upd["updated_at"] = _now_iso()
    await db.portal_calendar_events.update_one({"id": event_id}, {"$set": upd})
    out = await db.portal_calendar_events.find_one({"id": event_id}, {"_id": 0})
    return serialize_doc(out)


@router.delete("/calendar/{event_id}")
async def delete_calendar_event(event_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    res = await db.portal_calendar_events.delete_one({"id": event_id, "user_id": user["id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Event tidak ditemukan.")
    return {"ok": True}


@router.get("/calendar/combined")
async def combined_calendar(
    request: Request,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
):
    """Gabungan kalender: personal events + HR (cuti/lembur) + reminders."""
    user = await require_auth(request)
    db = get_db()
    uid = user["id"]
    _, emp = await _get_linked_employee(db, uid)
    emp_id = emp["id"] if emp else None

    if not from_:
        from_ = date.today().replace(day=1).isoformat()
    if not to:
        # last day of month
        m = date.fromisoformat(from_)
        next_m = (m.replace(day=28) + timedelta(days=4)).replace(day=1)
        to = (next_m - timedelta(days=1)).isoformat()

    events = []

    # 1. Personal events
    p_events = await db.portal_calendar_events.find(
        {"user_id": uid, "date": {"$gte": from_, "$lte": to}}, {"_id": 0}
    ).to_list(200)
    events.extend(p_events)

    # 2. Reminders as events
    rems = await db.portal_reminders.find(
        {"user_id": uid, "is_done": False,
         "remind_at": {"$gte": from_ + "T00:00:00", "$lte": to + "T23:59:59"}},
        {"_id": 0}
    ).to_list(50)
    for r in rems:
        events.append({
            "id": r["id"],
            "title": f"Reminder: {r['title']}",
            "date": r.get("remind_at", "")[:10],
            "time": r.get("remind_at", "")[11:16],
            "color": "#f59e0b",
            "type": "reminder",
            "source": r,
        })

    # 3. Leave requests
    if emp_id:
        leaves = await db.rahaza_leave_requests.find(
            {"employee_id": emp_id,
             "status": {"$in": ["approved", "pending"]},
             "from_date": {"$lte": to},
             "to_date": {"$gte": from_}},
            {"_id": 0}
        ).to_list(50)
        for lv in leaves:
            color = "#22c55e" if lv.get("status") == "approved" else "#f59e0b"
            events.append({
                "id": lv["id"],
                "title": f"{lv.get('leave_type_name', 'Cuti')}: {lv.get('status', '')}",
                "date": lv.get("from_date", ""),
                "end_date": lv.get("to_date", lv.get("from_date", "")),
                "color": color,
                "type": "leave",
                "source": lv,
            })

    # 4. Overtime
    if emp_id:
        ots = await db.rahaza_overtime_requests.find(
            {"employee_id": emp_id,
             "date": {"$gte": from_, "$lte": to}},
            {"_id": 0}
        ).to_list(50)
        for ot in ots:
            events.append({
                "id": ot["id"],
                "title": f"Lembur ({ot.get('hours', 0)}j)",
                "date": ot.get("date", ""),
                "color": "#8b5cf6",
                "type": "overtime",
                "source": ot,
            })

    events.sort(key=lambda e: e.get("date", ""))
    return {"from": from_, "to": to, "total": len(events), "events": events}
