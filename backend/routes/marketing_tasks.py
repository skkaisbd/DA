# ruff: noqa: F401
"""
marketing_tasks.py — Task Management
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
Endpoints: POST /tasks, GET /tasks, GET /tasks/{id}, PUT /tasks/{id}, POST /tasks/{id}/approve, POST /tasks/{id}/reject, DELETE /tasks/{id}, POST /tasks/{id}/complete-action, GET /tasks-stats, POST /auto-create-tasks/trigger
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri: jaring
# pengaman middleware hanya menolak permintaan yang MENYEBUT toko, ia tidak
# tahu isi jawaban. Tanpa ini staf pemegang satu toko membaca angka 9 toko.
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.marketing_shared import _uid, _now, _get_user, _sanitize, TaskCreate, TaskUpdate, TaskCompleteAction, _generate_task_code, _is_pic_role, _recalculate_health_score
from core import marketing_sales_shape as _shape

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing', tags=['Marketing-Tasks'])

@router.post("/tasks")
async def create_task(data: TaskCreate, request: Request):
    """
    Create new task (manual or from template).
    Only PIC Marketing can create tasks.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    
    # Validate task_type
    valid_types = ["data_entry", "review", "analysis", "reporting", "operational"]
    if data.task_type not in valid_types:
        raise HTTPException(400, f"task_type must be one of: {', '.join(valid_types)}")
    
    # Validate priority
    valid_priority = ["high", "medium", "low"]
    if data.priority not in valid_priority:
        raise HTTPException(400, f"priority must be one of: {', '.join(valid_priority)}")
    
    # Build task document
    task = {
        "id": _uid(),
        "task_code": _generate_task_code(),
        "title": _sanitize(data.title, 300),
        "description": _sanitize(data.description or "", 2000),
        "task_type": data.task_type,
        "recurrence": data.recurrence,
        "recurrence_config": data.recurrence_config.dict() if data.recurrence_config else {},
        "assigned_to": data.assigned_to,
        "assigned_by": user.get("id"),
        "account_id": data.account_id,
        "priority": data.priority,
        "due_date": data.due_date,
        "status": "to_do",
        "checklist": data.checklist or [],
        "attachments": [],
        "completion_notes": "",
        "approval_status": None,
        "approved_by": None,
        "approved_at": None,
        # ── Actionable task linkage ──
        "related_entity": data.related_entity,
        "related_entity_id": data.related_entity_id,
        "related_form_data": data.related_form_data or {},
        "action_type": data.action_type,
        "action_executed_at": None,
        "action_result": None,
        "created_at": _now(),
        "updated_at": _now()
    }
    
    await db.marketing_tasks.insert_one(task)
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "create",
        "marketing_task",
        f"Created task: {data.title}"
    )
    
    return serialize_doc({"message": "Task created", "task": task})


@router.get("/tasks")
async def list_tasks(
    request: Request,
    status: Optional[str] = Query(None, description="Filter by status"),
    assigned_to: Optional[str] = Query(None, description="Filter by assigned user"),
    account_id: Optional[str] = Query(None, description="Filter by account"),
    priority: Optional[str] = Query(None, description="Filter by priority"),
    approval_status: Optional[str] = Query(None, description="pending | approved | rejected"),
    page: int = Query(default=1, ge=1, description="Halaman (mulai dari 1)"),
    limit: int = Query(default=20, ge=1, le=100, description="Jumlah per halaman (max 100)"),
):
    """
    List tasks dengan filter + pagination.
    Staff hanya melihat task yang di-assign ke mereka, PIC melihat semua.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)

    # F6 (sesi #10) — tugas marketing menempel pada toko; staf pemegang satu toko
    # tidak boleh melihat (apalagi mengambil) tugas toko lain.
    query = await _scope.scope_filter(db, user, {})

    user_role = user.get("role", "staff")
    if user_role == "staff":
        query["assigned_to"] = user.get("id")

    if status:
        query["status"] = status
    if assigned_to:
        query["assigned_to"] = assigned_to
    if account_id:
        query["account_id"] = account_id
    if priority:
        query["priority"] = priority
    if approval_status:
        query["approval_status"] = approval_status

    total = await db.marketing_tasks.count_documents(query)
    skip = (page - 1) * limit
    tasks = await db.marketing_tasks.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(500)

    return serialize_doc({
        "tasks": tasks,
        "pagination": {
            "total": total,
            "page": page,
            "limit": limit,
            "total_pages": (total + limit - 1) // limit if total > 0 else 1,
            "has_next": skip + limit < total,
            "has_prev": page > 1,
        }
    })


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, request: Request):
    """Get task detail"""
    await require_auth(request)
    db = get_db()
    
    task = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    
    return serialize_doc(task)


@router.put("/tasks/{task_id}")
async def update_task(task_id: str, data: TaskUpdate, request: Request):
    """Update task"""
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    
    task = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    
    # Build update dict
    update_data = {}
    if data.title is not None:
        update_data["title"] = _sanitize(data.title, 300)
    if data.description is not None:
        update_data["description"] = _sanitize(data.description, 2000)
    if data.status is not None:
        valid_status = ["to_do", "in_progress", "pending_approval", "done", "cancelled"]
        if data.status not in valid_status:
            raise HTTPException(400, f"status must be one of: {', '.join(valid_status)}")
        update_data["status"] = data.status
        
        # If status is pending_approval, set approval_status to pending
        if data.status == "pending_approval":
            update_data["approval_status"] = "pending"
    
    if data.assigned_to is not None:
        update_data["assigned_to"] = data.assigned_to
    if data.priority is not None:
        update_data["priority"] = data.priority
    if data.due_date is not None:
        update_data["due_date"] = data.due_date
    if data.checklist is not None:
        update_data["checklist"] = data.checklist
    if data.completion_notes is not None:
        update_data["completion_notes"] = data.completion_notes
    
    update_data["updated_at"] = _now()
    
    await db.marketing_tasks.update_one(
        {"id": task_id},
        {"$set": update_data}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "update",
        "marketing_task",
        f"Updated task: {task['title']}"
    )
    
    # Get updated task
    updated = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    return serialize_doc({"message": "Task updated", "task": updated})


@router.post("/tasks/{task_id}/approve")
async def approve_task(task_id: str, request: Request):
    """
    PIC Marketing approves task.
    Only tasks with status=pending_approval can be approved.
    Allowed roles: admin/owner/superadmin/manager_*/pic_marketing/pic_toko.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)

    if not _is_pic_role(user):
        raise HTTPException(403, "Hanya PIC Marketing (admin/owner/manager) yang dapat approve task")

    task = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    
    if task["status"] != "pending_approval":
        raise HTTPException(400, "Task must be in 'pending_approval' status to approve")
    
    # Update task
    await db.marketing_tasks.update_one(
        {"id": task_id},
        {"$set": {
            "status": "done",
            "approval_status": "approved",
            "approved_by": user.get("id"),
            "approved_at": _now(),
            "updated_at": _now()
        }}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "approve",
        "marketing_task",
        f"Approved task: {task['title']}"
    )
    
    return serialize_doc({"message": "Task approved"})


@router.post("/tasks/{task_id}/reject")
async def reject_task(task_id: str, reason: str, request: Request):
    """
    PIC Marketing rejects task.
    Task goes back to 'in_progress' status.
    Allowed roles: admin/owner/superadmin/manager_*/pic_marketing/pic_toko.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)

    if not _is_pic_role(user):
        raise HTTPException(403, "Hanya PIC Marketing (admin/owner/manager) yang dapat reject task")

    task = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    
    if task["status"] != "pending_approval":
        raise HTTPException(400, "Task must be in 'pending_approval' status to reject")
    
    # Update task - back to in_progress
    await db.marketing_tasks.update_one(
        {"id": task_id},
        {"$set": {
            "status": "in_progress",
            "approval_status": "rejected",
            "approved_by": user.get("id"),
            "approved_at": _now(),
            "completion_notes": f"[REJECTED] {reason}",
            "updated_at": _now()
        }}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "reject",
        "marketing_task",
        f"Rejected task: {task['title']} - Reason: {reason}"
    )
    
    return serialize_doc({"message": "Task rejected", "reason": reason})


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str, request: Request):
    """
    Delete task (soft delete - set status to cancelled).
    Only PIC can delete tasks.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    
    task = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task not found")
    
    await db.marketing_tasks.update_one(
        {"id": task_id},
        {"$set": {"status": "cancelled", "updated_at": _now()}}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "delete",
        "marketing_task",
        f"Cancelled task: {task['title']}"
    )
    
    return serialize_doc({"message": "Task cancelled"})


# ══════════════════════════════════════════════════════════════════════════════
# ACTIONABLE TASKS — Complete with inline action (Phase 3)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/tasks/{task_id}/complete-action")
async def complete_task_action(task_id: str, payload: TaskCompleteAction, request: Request):
    """
    Execute a task's bound action and mark task as done.
    
    Supported action_type values:
      - submit_form: Create new entity (e.g., sales_data) using action_data
      - approve_reject: Update existing entity status (e.g., approve return)
      - review_content: Add response text (e.g., reply review)
      - manual_check: No action, just mark done with notes
    
    Supported related_entity values:
      - sales_data: Create sales entry (auto-fills account_id, date from related_form_data)
      - return: Update return status (related_entity_id required)
      - review: Add response to review (related_entity_id required)
      - complaint: Update complaint status
      - content: Update content status
    """
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    
    task = await db.marketing_tasks.find_one({"id": task_id}, {"_id": 0})
    if not task:
        raise HTTPException(404, "Task tidak ditemukan")
    
    if task.get("status") in ("done", "cancelled"):
        raise HTTPException(409, f"Task sudah berstatus '{task.get('status')}', tidak bisa di-action lagi.")
    
    action_type = task.get("action_type") or "manual_check"
    related = task.get("related_entity")
    related_id = task.get("related_entity_id")
    form_data = task.get("related_form_data") or {}
    action_data = payload.action_data or {}
    
    action_result = {"success": False, "message": "", "created_id": None}
    
    try:
        # ─── ACTION: submit_form ───
        if action_type == "submit_form":
            if related == "sales_data":
                # Compose sales data record (merge pre-fill + user input)
                merged = {**form_data, **action_data}
                if not merged.get("account_id"):
                    raise HTTPException(400, "account_id wajib untuk sales_data action")
                
                # Get account details for denormalization
                acc = await db.marketing_platform_accounts.find_one({"id": merged["account_id"]}, {"_id": 0})
                if not acc:
                    raise HTTPException(404, "Account tidak ditemukan")
                
                revenue = float(merged.get("revenue", 0))
                orders = int(merged.get("orders", 0))

                # F0.2 (2026-08-12) — bentuk dokumen dari pembuat kanonik yang sama
                # dengan entri manual & impor (`core.marketing_sales_shape`), bukan
                # dict yang disusun ulang di sini (dulu: `fulfillment`/`customer_
                # satisfaction` selalu `{}` sehingga skor kesehatan berbeda).
                sales_doc = _shape.build_daily_doc(
                    account=acc,
                    date=merged.get("date") or _now().strftime("%Y-%m-%d"),
                    revenue_type=merged.get("revenue_type", "total"),
                    flat={k: v for k, v in merged.items()
                          if k not in ("account_id", "date", "revenue_type")},
                    source=_shape.SOURCE_TASK,
                    extra={
                        "id": _uid(),
                        "import_history_id": None,
                        "task_id": task_id,
                        "created_by": user.get("email", "system"),
                        "created_at": _now(),
                    },
                )
                
                # Check duplicate
                existing = await db.marketing_sales_data.find_one({
                    "account_id": sales_doc["account_id"],
                    "date": sales_doc["date"],
                    "revenue_type": sales_doc["revenue_type"],
                }, {"_id": 0})
                if existing:
                    raise HTTPException(409, f"Sales data untuk {sales_doc['date']} ({sales_doc['revenue_type']}) sudah ada")
                
                await db.marketing_sales_data.insert_one(sales_doc)
                # Trigger health recalc
                await _recalculate_health_score(db, merged["account_id"])
                action_result = {"success": True, "message": "Sales data berhasil disubmit", "created_id": sales_doc["id"]}
            
            else:
                raise HTTPException(400, f"submit_form action belum support entity: {related}")
        
        # ─── ACTION: approve_reject ───
        elif action_type == "approve_reject":
            decision = action_data.get("decision")  # 'approve' | 'reject'
            reason = action_data.get("reason", "")
            
            if decision not in ("approve", "reject"):
                raise HTTPException(400, "action_data.decision wajib: 'approve' atau 'reject'")
            if not related_id:
                raise HTTPException(400, "related_entity_id wajib untuk approve_reject action")
            
            if related == "return":
                new_status = "approved" if decision == "approve" else "rejected"
                upd = {
                    "status": new_status,
                    "appeal_status": "approved" if decision == "approve" else "rejected",
                    "appeal_result": reason or ("Disetujui via task" if decision == "approve" else "Ditolak via task"),
                    "updated_at": _now(),
                }
                result = await db.marketing_returns.update_one({"id": related_id}, {"$set": upd})
                if result.matched_count == 0:
                    raise HTTPException(404, "Return tidak ditemukan")
                action_result = {"success": True, "message": f"Return berhasil di-{decision}", "created_id": related_id}
            else:
                raise HTTPException(400, f"approve_reject action belum support entity: {related}")
        
        # ─── ACTION: review_content ───
        elif action_type == "review_content":
            response_text = action_data.get("response_text", "")
            if not response_text:
                raise HTTPException(400, "action_data.response_text wajib")
            
            if related == "review":
                if not related_id:
                    raise HTTPException(400, "related_entity_id wajib")
                result = await db.marketing_reviews.update_one(
                    {"id": related_id},
                    {"$set": {
                        "response_text": response_text,
                        "response_date": _now(),
                        "status": "responded",
                        "updated_at": _now(),
                    }}
                )
                if result.matched_count == 0:
                    raise HTTPException(404, "Review tidak ditemukan")
                action_result = {"success": True, "message": "Review berhasil dibalas", "created_id": related_id}
            else:
                raise HTTPException(400, f"review_content action belum support entity: {related}")
        
        # ─── ACTION: manual_check ───
        elif action_type == "manual_check":
            action_result = {"success": True, "message": "Task ditandai selesai (manual check)", "created_id": None}
        
        else:
            raise HTTPException(400, f"Unknown action_type: {action_type}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Task action failed: {e}", exc_info=True)
        raise HTTPException(500, f"Action gagal: {str(e)}")
    
    # Mark task as done
    await db.marketing_tasks.update_one(
        {"id": task_id},
        {"$set": {
            "status": "done",
            "completion_notes": payload.completion_notes or action_result["message"],
            "action_executed_at": _now(),
            "action_result": action_result,
            "updated_at": _now(),
        }}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "complete_action",
        "marketing_task",
        f"Task action executed: {task['title']} - {action_result['message']}"
    )
    
    return serialize_doc({
        "message": "Task action completed successfully",
        "result": action_result,
    })


# ══════════════════════════════════════════════════════════════════════════════
# TASK TEMPLATES
# ══════════════════════════════════════════════════════════════════════════════
