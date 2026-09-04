# ruff: noqa: F401
"""
marketing_task_templates.py — Task Template Management
Extracted from marketing.py (1757 LOC monolith)

Refactored: Session #11.19 Phase 3.2 Batch #3
Endpoints: POST /task-templates, GET /task-templates, GET /task-templates/{id}, PUT /task-templates/{id}, DELETE /task-templates/{id}
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Request, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.query_guards import q_date
from routes.marketing_shared import _uid, _now, _get_user, _sanitize, TaskTemplateCreate, RecurrenceConfig

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/marketing', tags=['Marketing-Task Templates'])

@router.post("/task-templates")
async def create_task_template(data: TaskTemplateCreate, request: Request):
    """
    Create task template for recurring tasks.
    Only PIC Marketing can create templates.
    """
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    
    template = {
        "id": _uid(),
        "template_name": _sanitize(data.template_name, 200),
        "title": _sanitize(data.title, 300),
        "description": _sanitize(data.description or "", 2000),
        "task_type": data.task_type,
        "recurrence": data.recurrence,
        "recurrence_config": data.recurrence_config.dict(),
        "default_assigned_role": data.default_assigned_role,
        "account_id": data.account_id,
        "priority": data.priority,
        "checklist_template": data.checklist_template or [],
        "is_active": data.is_active,
        "created_by": user.get("id"),
        "created_at": _now(),
        "updated_at": _now()
    }
    
    await db.marketing_task_templates.insert_one(template)
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "create",
        "marketing_task_template",
        f"Created task template: {data.template_name}"
    )
    
    return serialize_doc({"message": "Task template created", "template": template})


@router.get("/task-templates")
async def list_task_templates(
    request: Request,
    is_active: Optional[bool] = Query(None, description="Filter by active status")
):
    """List all task templates"""
    await require_auth(request)
    db = get_db()
    
    query = {}
    if is_active is not None:
        query["is_active"] = is_active
    
    templates = await db.marketing_task_templates.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    return serialize_doc(templates)


@router.get("/task-templates/{template_id}")
async def get_task_template(template_id: str, request: Request):
    """Get task template detail"""
    await require_auth(request)
    db = get_db()
    
    template = await db.marketing_task_templates.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(404, "Task template not found")
    
    return serialize_doc(template)


@router.put("/task-templates/{template_id}")
async def update_task_template(template_id: str, data: TaskTemplateCreate, request: Request):
    """Update task template"""
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    
    template = await db.marketing_task_templates.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(404, "Task template not found")
    
    update_data = {
        "template_name": data.template_name,
        "title": data.title,
        "description": data.description or "",
        "task_type": data.task_type,
        "recurrence": data.recurrence,
        "recurrence_config": data.recurrence_config.dict(),
        "default_assigned_role": data.default_assigned_role,
        "account_id": data.account_id,
        "priority": data.priority,
        "checklist_template": data.checklist_template or [],
        "is_active": data.is_active,
        "updated_at": _now()
    }
    
    await db.marketing_task_templates.update_one(
        {"id": template_id},
        {"$set": update_data}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "update",
        "marketing_task_template",
        f"Updated task template: {data.template_name}"
    )
    
    updated = await db.marketing_task_templates.find_one({"id": template_id}, {"_id": 0})
    return serialize_doc({"message": "Task template updated", "template": updated})


@router.delete("/task-templates/{template_id}")
async def delete_task_template(template_id: str, request: Request):
    """Delete task template (set is_active=false)"""
    await require_auth(request)
    db = get_db()
    user = _get_user(request)
    
    template = await db.marketing_task_templates.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(404, "Task template not found")
    
    await db.marketing_task_templates.update_one(
        {"id": template_id},
        {"$set": {"is_active": False, "updated_at": _now()}}
    )
    
    await log_activity(
        user.get("id", "system"),
        user.get("name") or user.get("email", "system"),
        "delete",
        "marketing_task_template",
        f"Deactivated task template: {template['template_name']}"
    )
    
    return serialize_doc({"message": "Task template deactivated"})


# ══════════════════════════════════════════════════════════════════════════════
# TASK STATISTICS & REPORTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/tasks-stats")
async def get_tasks_stats(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None)
):
    """
    Get task completion statistics.
    For PIC dashboard to see task completion rate.
    """
    await require_auth(request)
    db = get_db()
    
    # Date range default: last 30 days
    if not date_to:
        date_to = _now().strftime("%Y-%m-%d")
    if not date_from:
        date_from = (_now() - timedelta(days=30)).strftime("%Y-%m-%d")

    # BUG-R11-A: validasi dulu — tanggal sampah dulu bikin HTTP 500
    date_from = q_date(date_from, name="date_from").isoformat()
    date_to = q_date(date_to, name="date_to").isoformat()

    # Get tasks in date range
    query = {
        "created_at": {
            "$gte": datetime.fromisoformat(date_from + "T00:00:00+00:00"),
            "$lte": datetime.fromisoformat(date_to + "T23:59:59+00:00")
        }
    }

    # F6 (ditemukan gate INV-F6RBAC, sesi #12) — statistik ini DULU dihitung
    # atas SELURUH tugas, jadi staf yang tidak punya toko satu pun tetap membaca
    # angka 9 toko (admin=20 · staf=20). Endpoint DAFTAR sudah menyaring, tetapi
    # endpoint RINGKAS-nya tidak — dan justru ringkasan itulah yang dibaca orang
    # lebih dulu di dashboard. Jaring pengaman middleware tidak menolongnya:
    # permintaan ini tidak MENYEBUT toko mana pun, jadi tidak ada yang bisa
    # ditolak. Penyaringan harus dilakukan endpointnya sendiri.
    _user = await require_auth(request)
    from core import marketing_account_scope as _scope
    _vis = await _scope.visible_account_ids(db, _user)
    if _vis is not None:
        query["account_id"] = {"$in": _vis}

    tasks = await db.marketing_tasks.find(query, {"_id": 0}).to_list(500)
    
    # Calculate stats
    total = len(tasks)
    by_status = {
        "to_do": len([t for t in tasks if t["status"] == "to_do"]),
        "in_progress": len([t for t in tasks if t["status"] == "in_progress"]),
        "pending_approval": len([t for t in tasks if t["status"] == "pending_approval"]),
        "done": len([t for t in tasks if t["status"] == "done"]),
        "cancelled": len([t for t in tasks if t["status"] == "cancelled"])
    }
    
    completion_rate = (by_status["done"] / total * 100) if total > 0 else 0
    
    # Overdue tasks
    now = _now()
    overdue = len([t for t in tasks if t.get("due_date") and datetime.fromisoformat(t["due_date"]) < now and t["status"] not in ["done", "cancelled"]])
    
    return serialize_doc({
        "period": {"date_from": date_from, "date_to": date_to},
        "total_tasks": total,
        "by_status": by_status,
        "completion_rate": round(completion_rate, 2),
        "overdue_count": overdue
    })


# ══════════════════════════════════════════════════════════════════════════════
# MANUAL TRIGGER — Auto-create tasks (untuk testing tanpa wait cron)
# ══════════════════════════════════════════════════════════════════════════════

@router.post("/auto-create-tasks/trigger")
async def trigger_auto_create_tasks(request: Request):
    """
    Manual trigger for auto-create marketing tasks job (sales reminder + health alert).
    Admin/PIC only.
    """
    user = await require_auth(request)
    role = user.get("role", "")
    if role not in ["admin", "owner", "superadmin", "pic_marketing", "pic_toko", "manager_marketing"]:
        raise HTTPException(403, "Hanya admin/PIC/manager marketing yang bisa trigger ini")
    
    try:
        from utils.scheduler import job_auto_create_marketing_tasks
        await job_auto_create_marketing_tasks()
        return serialize_doc({"message": "Auto-create tasks triggered successfully", "status": "completed"})
    except Exception as e:
        logger.exception(f"Manual trigger failed: {e}")
        raise HTTPException(500, f"Trigger gagal: {str(e)}")
