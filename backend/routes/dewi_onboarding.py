"""Phase 6.3 — Onboarding System
Modul: Template checklist onboarding, task tracking, dokumen karyawan baru
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from motor.motor_asyncio import AsyncIOMotorDatabase
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, timedelta
from typing import Optional
import uuid
import re

router = APIRouter(prefix="/api/dewi/onboarding", tags=["Onboarding"])

def now_utc():
    return datetime.now(timezone.utc)

def sid():
    return str(uuid.uuid4())

def serialize(doc):
    if doc is None:
        return None
    doc = dict(doc)
    doc.pop('_id', None)
    for k, v in doc.items():
        if isinstance(v, datetime):
            doc[k] = v.isoformat()
    return doc

# Default onboarding tasks
DEFAULT_TASKS = [
    {"title": "Menyiapkan seragam kerja", "category": "Administrasi", "day": 0, "assigned_to": "HR"},
    {"title": "Pembuatan ID Card & akses sistem", "category": "IT", "day": 0, "assigned_to": "IT"},
    {"title": "Orientasi perusahaan & tur fasilitas", "category": "HR", "day": 1, "assigned_to": "HR"},
    {"title": "Penandatanganan kontrak kerja", "category": "Legal", "day": 1, "assigned_to": "Karyawan"},
    {"title": "Pengisian formulir biodata lengkap", "category": "Administrasi", "day": 1, "assigned_to": "Karyawan"},
    {"title": "Submit foto formal", "category": "Administrasi", "day": 1, "assigned_to": "Karyawan"},
    {"title": "Registrasi akun sistem ERP", "category": "IT", "day": 2, "assigned_to": "IT"},
    {"title": "Training K3 & keselamatan kerja", "category": "Keselamatan", "day": 2, "assigned_to": "HR"},
    {"title": "Perkenalan dengan tim & supervisor", "category": "HR", "day": 2, "assigned_to": "Supervisor"},
    {"title": "Menyelesaikan kursus LMS: Orientasi Karyawan", "category": "Training", "day": 5, "assigned_to": "Karyawan"},
    {"title": "One-on-one dengan manajer langsung", "category": "HR", "day": 7, "assigned_to": "Manager"},
    {"title": "Penyerahan dokumen BPJS", "category": "Legal", "day": 7, "assigned_to": "Karyawan"},
    {"title": "Review 30 hari pertama", "category": "HR", "day": 30, "assigned_to": "Supervisor"},
]

# ──────────────────────────────────────────────────────────────────────────────
# TEMPLATES
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/templates")
async def list_templates(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    docs = await db.dewi_onboarding_templates.find({}).sort("name", 1).to_list(50)
    return {"ok": True, "templates": [serialize(d) for d in docs]}

@router.post("/templates")
async def create_template(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = {
        "template_id": sid(),
        "name": body.get("name", "Template Onboarding"),
        "dept": body.get("dept", "Semua"),
        "description": body.get("description", ""),
        "tasks": body.get("tasks", DEFAULT_TASKS),
        "duration_days": body.get("duration_days", 30),
        "is_default": body.get("is_default", False),
        "created_by": user.get("name", ""),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_onboarding_templates.insert_one(doc)
    return {"ok": True, "template": serialize(doc)}

@router.put("/templates/{template_id}")
async def update_template(
    template_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    upd = {k: body[k] for k in ["name","dept","description","tasks","duration_days","is_default"] if k in body}
    upd["updated_at"] = now_utc()
    await db.dewi_onboarding_templates.update_one({"template_id": template_id}, {"$set": upd})
    doc = await db.dewi_onboarding_templates.find_one({"template_id": template_id})
    return {"ok": True, "template": serialize(doc)}


@router.post("/templates/{template_id}/tasks")
async def add_template_task(
    template_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Add a task to an existing template."""
    tpl = await db.dewi_onboarding_templates.find_one({"template_id": template_id})
    if not tpl:
        raise HTTPException(404, "Template tidak ditemukan")
    task = {
        "task_id": sid(),
        "title": body.get("title", ""),
        "description": body.get("description", ""),
        "category": body.get("category", "Umum"),
        "assigned_to": body.get("assigned_to", "HR"),
        "day": body.get("day", 1),
    }
    tasks = tpl.get("tasks", [])
    tasks.append(task)
    await db.dewi_onboarding_templates.update_one(
        {"template_id": template_id},
        {"$set": {"tasks": tasks, "updated_at": now_utc()}}
    )
    doc = await db.dewi_onboarding_templates.find_one({"template_id": template_id})
    return {"ok": True, "template": serialize(doc)}


@router.delete("/templates/{template_id}/tasks/{task_id}")
async def delete_template_task(
    template_id: str, task_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    tpl = await db.dewi_onboarding_templates.find_one({"template_id": template_id})
    if not tpl:
        raise HTTPException(404, "Template tidak ditemukan")
    tasks = [t for t in tpl.get("tasks", []) if t.get("task_id") != task_id]
    await db.dewi_onboarding_templates.update_one(
        {"template_id": template_id},
        {"$set": {"tasks": tasks, "updated_at": now_utc()}}
    )
    return {"ok": True}

@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_onboarding_templates.delete_one({"template_id": template_id})
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# CHECKLISTS (per employee onboarding)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/checklists")
async def list_checklists(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    q: Optional[str] = None,
    page: int = Query(1, ge=1), limit: int = Query(20, ge=1, le=200),
):
    filt = {}
    if status:
        filt["status"] = status
    if employee_id:
        filt["employee_id"] = employee_id
    if q:
        filt["employee_name"] = {"$regex": re.escape(q), "$options": "i"}
    total = await db.dewi_onboarding_checklists.count_documents(filt)
    docs = await db.dewi_onboarding_checklists.find(filt).sort("start_date", -1).skip((page-1)*limit).limit(limit).to_list(limit)
    return {"ok": True, "total": total, "checklists": [serialize(d) for d in docs]}

@router.post("/checklists")
async def create_checklist(
    body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    employee_id = body.get("employee_id", "")
    employee_name = body.get("employee_name", "")
    
    # get employee details if not provided
    if employee_id and not employee_name:
        emp = await db.rahaza_employees.find_one({"employee_id": employee_id})
        if emp:
            employee_name = emp.get("name", employee_id)
    
    # get template tasks or use default
    template_id = body.get("template_id", "")
    tasks = DEFAULT_TASKS.copy()
    if template_id:
        tpl = await db.dewi_onboarding_templates.find_one({"template_id": template_id})
        if tpl:
            tasks = tpl.get("tasks", tasks)
    
    start_date = now_utc()
    # create task items with due dates
    task_items = []
    for t in tasks:
        due = start_date + timedelta(days=t.get("day", 1))
        task_items.append({
            "task_id": sid(),
            "title": t["title"],
            "category": t.get("category", "Umum"),
            "assigned_to": t.get("assigned_to", "HR"),
            "day": t.get("day", 1),
            "due_date": due,
            "status": "pending",  # pending/done/skipped
            "completed_at": None,
            "notes": "",
        })
    
    doc = {
        "checklist_id": sid(),
        "employee_id": employee_id,
        "employee_name": employee_name,
        "employee_dept": body.get("employee_dept", ""),
        "employee_position": body.get("employee_position", ""),
        "template_id": template_id,
        "start_date": start_date,
        "target_completion": body.get("target_completion", (start_date + timedelta(days=30)).isoformat()),
        "status": "active",  # active/completed/paused
        "tasks": task_items,
        "progress_pct": 0,
        "completed_tasks": 0,
        "total_tasks": len(task_items),
        "buddy": body.get("buddy", ""),
        "supervisor": body.get("supervisor", ""),
        "notes": body.get("notes", ""),
        "created_by": user.get("name", ""),
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_onboarding_checklists.insert_one(doc)
    return {"ok": True, "checklist": serialize(doc)}

@router.get("/checklists/{checklist_id}")
async def get_checklist(
    checklist_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    doc = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    if not doc:
        raise HTTPException(404, "Checklist tidak ditemukan")
    return {"ok": True, "checklist": serialize(doc)}

@router.put("/checklists/{checklist_id}/tasks/{task_id}")
async def update_task(
    checklist_id: str, task_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    cl = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    if not cl:
        raise HTTPException(404, "Checklist tidak ditemukan")

    tasks = cl.get("tasks", [])
    for t in tasks:
        if t["task_id"] == task_id:
            if "status" in body:
                t["status"] = body["status"]
            if "notes" in body:
                t["notes"] = body["notes"]
            if "title" in body:
                t["title"] = body["title"]
            if "description" in body:
                t["description"] = body["description"]
            if "assigned_to" in body:
                t["assigned_to"] = body["assigned_to"]
            if "due_date" in body:
                t["due_date"] = body["due_date"]
            if t["status"] == "done" and not t.get("completed_at"):
                t["completed_at"] = now_utc().isoformat()
                t["completed_by"] = user.get("name", "")
            if t["status"] == "pending":
                t["completed_at"] = None
                t["completed_by"] = None
            break

    done = sum(1 for t in tasks if t["status"] == "done")
    total = len(tasks)
    pct = round(done / total * 100) if total else 0
    overall_status = "completed" if pct == 100 else cl.get("status", "active")

    await db.dewi_onboarding_checklists.update_one(
        {"checklist_id": checklist_id},
        {"$set": {"tasks": tasks, "progress_pct": pct,
                  "completed_tasks": done, "status": overall_status,
                  "updated_at": now_utc()}}
    )
    doc = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    return {"ok": True, "checklist": serialize(doc)}


@router.post("/checklists/{checklist_id}/tasks")
async def add_custom_task(
    checklist_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Add a custom activity task to a running onboarding checklist."""
    cl = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    if not cl:
        raise HTTPException(404, "Checklist tidak ditemukan")

    task = {
        "task_id": sid(),
        "title": body.get("title", ""),
        "description": body.get("description", ""),
        "category": body.get("category", "Kustom"),
        "assigned_to": body.get("assigned_to", ""),
        "day": body.get("day", 0),
        "due_date": body.get("due_date"),
        "status": "pending",
        "completed_at": None,
        "completed_by": None,
        "notes": "",
        "is_custom": True,
    }
    tasks = cl.get("tasks", [])
    tasks.append(task)

    done = sum(1 for t in tasks if t["status"] == "done")
    total = len(tasks)
    pct = round(done / total * 100) if total else 0

    await db.dewi_onboarding_checklists.update_one(
        {"checklist_id": checklist_id},
        {"$set": {"tasks": tasks, "total_tasks": total,
                  "progress_pct": pct, "updated_at": now_utc()}}
    )
    doc = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    return {"ok": True, "checklist": serialize(doc)}


@router.delete("/checklists/{checklist_id}/tasks/{task_id}")
async def delete_custom_task(
    checklist_id: str, task_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    """Delete a task (preferably custom ones) from a running checklist."""
    cl = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    if not cl:
        raise HTTPException(404, "Checklist tidak ditemukan")

    tasks = [t for t in cl.get("tasks", []) if t.get("task_id") != task_id]
    done = sum(1 for t in tasks if t["status"] == "done")
    total = len(tasks)
    pct = round(done / total * 100) if total else 0

    await db.dewi_onboarding_checklists.update_one(
        {"checklist_id": checklist_id},
        {"$set": {"tasks": tasks, "total_tasks": total, "completed_tasks": done,
                  "progress_pct": pct, "updated_at": now_utc()}}
    )
    doc = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    return {"ok": True, "checklist": serialize(doc)}

@router.put("/checklists/{checklist_id}")
async def update_checklist(
    checklist_id: str, body: dict,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    allowed = ["status", "buddy", "supervisor", "notes", "target_completion"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = now_utc()
    await db.dewi_onboarding_checklists.update_one({"checklist_id": checklist_id}, {"$set": upd})
    doc = await db.dewi_onboarding_checklists.find_one({"checklist_id": checklist_id})
    return {"ok": True, "checklist": serialize(doc)}

@router.delete("/checklists/{checklist_id}")
async def delete_checklist(
    checklist_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_onboarding_checklists.delete_one({"checklist_id": checklist_id})
    return {"ok": True}

# ──────────────────────────────────────────────────────────────────────────────
# ANALYTICS
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/analytics")
async def onboarding_analytics(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    total = await db.dewi_onboarding_checklists.count_documents({})
    active = await db.dewi_onboarding_checklists.count_documents({"status": "active"})
    completed = await db.dewi_onboarding_checklists.count_documents({"status": "completed"})
    overdue = await db.dewi_onboarding_checklists.count_documents({
        "status": "active",
        "target_completion": {"$lt": now_utc().isoformat()}
    })
    
    # avg progress
    pipeline = [{"$group": {"_id": None, "avg_pct": {"$avg": "$progress_pct"}}}]
    avg_res = await db.dewi_onboarding_checklists.aggregate(pipeline).to_list(1)
    avg_progress = round(avg_res[0]["avg_pct"], 1) if avg_res else 0
    
    # recent
    recent = await db.dewi_onboarding_checklists.find({}).sort("created_at", -1).limit(5).to_list(5)
    
    return {
        "ok": True,
        "summary": {
            "total": total,
            "active": active,
            "completed": completed,
            "overdue": overdue,
            "avg_progress": avg_progress,
        },
        "recent": [serialize(d) for d in recent],
    }

# ──────────────────────────────────────────────────────────────────────────────
# SEED
# ──────────────────────────────────────────────────────────────────────────────

@router.post("/seed")
async def seed_onboarding(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user=Depends(require_auth),
):
    await db.dewi_onboarding_templates.delete_many({})
    await db.dewi_onboarding_checklists.delete_many({})
    
    # Create default template
    tpl = {
        "template_id": "tpl-001",
        "name": "Template Standar - Operator Produksi",
        "dept": "Produksi",
        "description": "Template onboarding untuk operator produksi baru",
        "tasks": DEFAULT_TASKS,
        "duration_days": 30,
        "is_default": True,
        "created_by": "Admin",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_onboarding_templates.insert_one(tpl)
    
    tpl2 = {
        "template_id": "tpl-002",
        "name": "Template Staf Administrasi & Kantor",
        "dept": "Administrasi",
        "description": "Template onboarding untuk staf administrasi dan kantor",
        "tasks": [
            {"title": "Penandatanganan kontrak kerja", "category": "Legal", "day": 1, "assigned_to": "Karyawan"},
            {"title": "Setup workstation & email kantor", "category": "IT", "day": 1, "assigned_to": "IT"},
            {"title": "Orientasi prosedur administrasi", "category": "HR", "day": 1, "assigned_to": "HR"},
            {"title": "Pengenalan stakeholder internal", "category": "HR", "day": 2, "assigned_to": "Manager"},
            {"title": "Training penggunaan sistem ERP", "category": "Training", "day": 3, "assigned_to": "IT"},
            {"title": "Review KPI dan target 3 bulan", "category": "HR", "day": 7, "assigned_to": "Supervisor"},
        ],
        "duration_days": 14,
        "is_default": False,
        "created_by": "Admin",
        "created_at": now_utc(),
        "updated_at": now_utc(),
    }
    await db.dewi_onboarding_templates.insert_one(tpl2)
    
    # Create sample checklists
    employees = await db.rahaza_employees.find({"active": True}).limit(4).to_list(4)
    for i, emp in enumerate(employees):
        tasks_copy = []
        progress = [60, 100, 30, 0][i % 4]
        for j, t in enumerate(DEFAULT_TASKS):
            due = now_utc() + timedelta(days=t.get("day", 1))
            done = (j < int(len(DEFAULT_TASKS) * progress / 100))
            tasks_copy.append({
                "task_id": sid(),
                "title": t["title"],
                "category": t.get("category", "Umum"),
                "assigned_to": t.get("assigned_to", "HR"),
                "day": t.get("day", 1),
                "due_date": due,
                "status": "done" if done else "pending",
                "completed_at": now_utc().isoformat() if done else None,
                "notes": "",
            })
        
        done_count = sum(1 for t in tasks_copy if t["status"] == "done")
        total = len(tasks_copy)
        pct = round(done_count / total * 100) if total else 0
        
        cl = {
            "checklist_id": sid(),
            "employee_id": emp.get("employee_id", str(i)),
            "employee_name": emp.get("name", f"Karyawan {i+1}"),
            "employee_dept": emp.get("department", "Produksi"),
            "employee_position": emp.get("position", "Operator"),
            "template_id": "tpl-001",
            "start_date": now_utc() - timedelta(days=[0, 14, 5, 25][i % 4]),
            "target_completion": (now_utc() + timedelta(days=[30, 5, 25, 10][i % 4])).isoformat(),
            "status": "completed" if pct == 100 else "active",
            "tasks": tasks_copy,
            "progress_pct": pct,
            "completed_tasks": done_count,
            "total_tasks": total,
            "buddy": "Senior Operator A",
            "supervisor": "Supervisor Lini 1",
            "notes": "",
            "created_by": "Admin",
            "created_at": now_utc(),
            "updated_at": now_utc(),
        }
        await db.dewi_onboarding_checklists.insert_one(cl)
    
    return {"ok": True, "message": "Onboarding seed selesai"}
