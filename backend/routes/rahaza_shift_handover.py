"""
PT Rahaza — Phase 22A: Shift Handover System

Endpoints (prefix /api/rahaza):
  Shift Handovers:
    GET  /shift-handovers                — list handovers (filter by date, shift)
    POST /shift-handovers                — create handover (end of shift)
    GET  /shift-handovers/{id}           — get handover detail
    PUT  /shift-handovers/{id}           — update handover
    GET  /shift-handovers/today          — get today's handovers
    GET  /shift-handovers/latest         — get latest handover for current shift
    
  Handover Templates:
    GET  /handover-templates             — list templates
    POST /handover-templates             — create template
    PUT  /handover-templates/{id}        — update template
    DELETE /handover-templates/{id}      — deactivate template

Purpose:
  - Supervisor creates handover notes at end of shift
  - Next shift supervisor can view previous notes
  - Checklist items ensure nothing missed
  - Historical record of shift-to-shift communication
"""
from fastapi import APIRouter, Request, HTTPException, Query
from fastapi.responses import Response
from database import get_db
from auth import require_auth
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-shift-handover"])


def _uid() -> str:
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


DEFAULT_CHECKLIST_ITEMS = [
    {"key": "production_target", "label": "Target produksi tercapai?", "type": "boolean"},
    {"key": "quality_issues", "label": "Ada masalah quality?", "type": "boolean"},
    {"key": "machine_downtime", "label": "Ada downtime mesin?", "type": "boolean"},
    {"key": "material_shortage", "label": "Ada kekurangan material?", "type": "boolean"},
    {"key": "safety_incidents", "label": "Ada insiden keselamatan?", "type": "boolean"},
    {"key": "pending_tasks", "label": "Ada task yang tertunda?", "type": "text"},
]


# ─── SHIFT HANDOVERS ───────────────────────────────────────────────────────
@router.get("/shift-handovers")
async def list_shift_handovers(
    request: Request,
    date_: Optional[str] = Query(None, alias="date", description="YYYY-MM-DD"),
    shift_id: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """List shift handovers with optional filters."""
    await require_auth(request)
    db = get_db()
    
    q = {}
    if date_:
        q["date"] = date_
    if shift_id:
        q["shift_id"] = shift_id
    
    handovers = await db.rahaza_shift_handovers.find(q, {"_id": 0}).sort("date", -1).limit(limit).to_list(500)
    
    # Enrich with shift info
    if handovers:
        shift_ids = list(set(h.get("shift_id") for h in handovers if h.get("shift_id")))
        if shift_ids:
            shifts = await db.rahaza_shifts.find({"id": {"$in": shift_ids}}, {"_id": 0}).to_list(500)
            shift_map = {s["id"]: s for s in shifts}
            for h in handovers:
                shift_info = shift_map.get(h.get("shift_id"), {})
                h["shift_name"] = shift_info.get("name")
                h["shift_code"] = shift_info.get("code")
    
    return handovers


@router.get("/shift-handovers/today")
async def get_today_handovers(request: Request):
    """Get all handovers for today."""
    await require_auth(request)
    db = get_db()
    
    today = date.today().isoformat()
    handovers = await db.rahaza_shift_handovers.find(
        {"date": today},
        {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    
    return handovers


@router.get("/shift-handovers/latest")
async def get_latest_handover(
    request: Request,
    shift_id: Optional[str] = None,
):
    """
    Get latest handover for current/specified shift.
    Useful for next shift supervisor to see previous shift notes.
    """
    await require_auth(request)
    db = get_db()
    
    q = {}
    if shift_id:
        q["shift_id"] = shift_id
    
    # Get latest from last 2 days
    two_days_ago = (date.today() - timedelta(days=2)).isoformat()
    q["date"] = {"$gte": two_days_ago}
    
    handover = await db.rahaza_shift_handovers.find_one(
        q,
        {"_id": 0},
        sort=[("date", -1), ("created_at", -1)]
    )
    
    if not handover:
        return None
    
    # Enrich with shift info
    if handover.get("shift_id"):
        shift = await db.rahaza_shifts.find_one({"id": handover["shift_id"]}, {"_id": 0})
        if shift:
            handover["shift_name"] = shift.get("name")
            handover["shift_code"] = shift.get("code")
    
    return handover


@router.post("/shift-handovers")
async def create_shift_handover(request: Request):
    """
    Create shift handover note.
    Body: {
      shift_id,
      date (YYYY-MM-DD),
      notes,
      checklist: [{key, value, notes}],
      issues: [{type, description, priority}],
      pending_tasks: [{description, assigned_to}]
    }
    """
    user = await require_auth(request)
    db = get_db()
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    
    shift_id = body.get("shift_id")
    handover_date = body.get("date", date.today().isoformat())
    notes = body.get("notes", "")
    checklist = body.get("checklist", [])
    issues = body.get("issues", [])
    pending_tasks = body.get("pending_tasks", [])
    
    if not shift_id:
        raise HTTPException(400, "shift_id wajib diisi")
    
    # Verify shift exists
    shift = await db.rahaza_shifts.find_one({"id": shift_id}, {"_id": 0})
    if not shift:
        raise HTTPException(404, "Shift tidak ditemukan")
    
    # Check if handover already exists for this shift+date
    existing = await db.rahaza_shift_handovers.find_one({
        "shift_id": shift_id,
        "date": handover_date,
    })
    if existing:
        raise HTTPException(400, f"Handover untuk shift ini pada tanggal {handover_date} sudah ada")
    
    handover = {
        "id": _uid(),
        "shift_id": shift_id,
        "shift_code": shift.get("code"),
        "shift_name": shift.get("name"),
        "date": handover_date,
        "notes": notes,
        "checklist": checklist,
        "issues": issues,
        "pending_tasks": pending_tasks,
        "supervisor_id": user.get("id"),
        "supervisor_name": user.get("name", user.get("email")),
        "status": "active",
        "created_at": _now().isoformat(),
        "updated_at": _now().isoformat(),
    }
    
    await db.rahaza_shift_handovers.insert_one(handover)
    handover.pop("_id", None)
    
    logger.info(f"Shift handover created for {shift.get('name')} on {handover_date} by {user.get('name')}")
    
    return handover


@router.get("/shift-handovers/{handover_id}")
async def get_shift_handover(handover_id: str, request: Request):
    """Get shift handover detail."""
    await require_auth(request)
    db = get_db()
    
    handover = await db.rahaza_shift_handovers.find_one({"id": handover_id}, {"_id": 0})
    if not handover:
        raise HTTPException(404, "Shift handover tidak ditemukan")
    
    return handover


@router.post("/shift-handovers/{handover_id}/sign-off")
async def sign_off_handover(handover_id: str, request: Request):
    """
    Supervisor/next-shift sign-off on a handover.
    Body: {notes (optional)}
    Transitions status: active → signed_off
    """
    user = await require_auth(request)
    db = get_db()

    handover = await db.rahaza_shift_handovers.find_one({"id": handover_id}, {"_id": 0})
    if not handover:
        raise HTTPException(404, "Shift handover tidak ditemukan")
    if handover.get("status") == "signed_off":
        raise HTTPException(400, "Handover sudah di-sign off sebelumnya")
    if handover.get("status") == "cancelled":
        raise HTTPException(400, "Handover telah dibatalkan")

    try:
        body = await request.json()
    except Exception:
        body = {}

    sign_off_notes = body.get("notes", "")

    upd = {
        "status": "signed_off",
        "signed_off_by_id": user.get("id"),
        "signed_off_by_name": user.get("name", user.get("email")),
        "signed_off_at": _now().isoformat(),
        "sign_off_notes": sign_off_notes,
        "updated_at": _now().isoformat(),
    }
    await db.rahaza_shift_handovers.update_one({"id": handover_id}, {"$set": upd})

    updated = await db.rahaza_shift_handovers.find_one({"id": handover_id}, {"_id": 0})
    logger.info(f"Handover {handover_id} signed off by {user.get('name')}")
    return updated


@router.put("/shift-handovers/{handover_id}")
async def update_shift_handover(handover_id: str, request: Request):
    """
    Update shift handover.
    Body: {notes, checklist, issues, pending_tasks}
    """
    user = await require_auth(request)
    db = get_db()
    
    handover = await db.rahaza_shift_handovers.find_one({"id": handover_id}, {"_id": 0})
    if not handover:
        raise HTTPException(404, "Shift handover tidak ditemukan")
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    
    updates = {}
    if "notes" in body:
        updates["notes"] = body["notes"]
    if "checklist" in body:
        updates["checklist"] = body["checklist"]
    if "issues" in body:
        updates["issues"] = body["issues"]
    if "pending_tasks" in body:
        updates["pending_tasks"] = body["pending_tasks"]
    
    if updates:
        updates["updated_at"] = _now().isoformat()
        updates["updated_by"] = user.get("id")
        updates["updated_by_name"] = user.get("name", user.get("email"))
        
        await db.rahaza_shift_handovers.update_one(
            {"id": handover_id},
            {"$set": updates}
        )
    
    updated = await db.rahaza_shift_handovers.find_one({"id": handover_id}, {"_id": 0})
    return updated


# ─── HANDOVER TEMPLATES ────────────────────────────────────────────────────
@router.get("/handover-templates")
async def list_handover_templates(request: Request, active_only: bool = True):
    """List handover checklist templates."""
    await require_auth(request)
    db = get_db()
    
    q = {"active": True} if active_only else {}
    templates = await db.rahaza_handover_templates.find(q, {"_id": 0}).sort("name", 1).to_list(500)
    
    return templates


@router.post("/handover-templates")
async def create_handover_template(request: Request):
    """
    Create handover checklist template.
    Body: {name, description, checklist_items: [{key, label, type}]}
    """
    user = await require_auth(request)
    db = get_db()
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    
    name = body.get("name", "").strip()
    if not name:
        raise HTTPException(400, "name wajib diisi")
    
    template = {
        "id": _uid(),
        "name": name,
        "description": body.get("description", ""),
        "checklist_items": body.get("checklist_items", DEFAULT_CHECKLIST_ITEMS),
        "active": True,
        "created_at": _now().isoformat(),
        "created_by": user.get("id"),
        "created_by_name": user.get("name", user.get("email")),
    }
    
    await db.rahaza_handover_templates.insert_one(template)
    template.pop("_id", None)
    
    return template


@router.put("/handover-templates/{template_id}")
async def update_handover_template(template_id: str, request: Request):
    """Update handover template."""
    await require_auth(request)
    db = get_db()
    
    template = await db.rahaza_handover_templates.find_one({"id": template_id}, {"_id": 0})
    if not template:
        raise HTTPException(404, "Template tidak ditemukan")
    
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON body")
    
    updates = {}
    if "name" in body:
        updates["name"] = body["name"].strip()
    if "description" in body:
        updates["description"] = body["description"]
    if "checklist_items" in body:
        updates["checklist_items"] = body["checklist_items"]
    
    if updates:
        updates["updated_at"] = _now().isoformat()
        await db.rahaza_handover_templates.update_one({"id": template_id}, {"$set": updates})
    
    updated = await db.rahaza_handover_templates.find_one({"id": template_id}, {"_id": 0})
    return updated


@router.delete("/handover-templates/{template_id}")
async def deactivate_handover_template(template_id: str, request: Request):
    """Deactivate handover template."""
    await require_auth(request)
    db = get_db()
    
    result = await db.rahaza_handover_templates.update_one(
        {"id": template_id},
        {"$set": {"active": False, "updated_at": _now().isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(404, "Template tidak ditemukan")
    
    return {"ok": True, "template_id": template_id, "status": "deactivated"}


@router.post("/handover-templates/seed-default")
async def seed_default_handover_template(request: Request):
    """Seed default handover checklist template."""
    await require_auth(request)
    db = get_db()
    
    existing = await db.rahaza_handover_templates.find_one({"name": "Default Checklist"})
    if existing:
        return {"ok": True, "message": "Default template already exists"}
    
    template = {
        "id": _uid(),
        "name": "Default Checklist",
        "description": "Checklist standar shift handover",
        "checklist_items": DEFAULT_CHECKLIST_ITEMS,
        "active": True,
        "created_at": _now().isoformat(),
        "created_by": "system",
        "created_by_name": "System",
    }
    
    await db.rahaza_handover_templates.insert_one(template)
    template.pop("_id", None)
    
    return {"ok": True, "template": template}



# ─── END-OF-SHIFT PDF ───────────────────────────────────────────────────────

@router.get("/shift-handovers/{handover_id}/pdf")
async def download_shift_report_pdf(handover_id: str, request: Request):
    """
    Download End-of-Shift Report PDF for a handover.
    Generates a clean PDF with shift info, checklist, issues, pending tasks,
    WO progress (filtered by the line in handover), and signature block.
    """
    user = await require_auth(request)
    db = get_db()

    handover = await db.rahaza_shift_handovers.find_one({"id": handover_id}, {"_id": 0})
    if not handover:
        raise HTTPException(404, "Shift handover tidak ditemukan")

    # Enrich shift name
    if handover.get("shift_id") and not handover.get("shift_name"):
        shift = await db.rahaza_shifts.find_one({"id": handover["shift_id"]}, {"_id": 0})
        if shift:
            handover["shift_name"] = shift.get("name", shift.get("code", ""))

    # Fetch WO summary for the line(s) mentioned in this handover
    wo_summary = []
    line_id = handover.get("line_id")
    line_code = handover.get("line_code")
    query = {}
    if line_id:
        query["line_id"] = line_id
    elif line_code:
        query["line_code"] = line_code
    else:
        # Fetch WOs from today regardless of line (limit 10)
        query["start_date"] = {"$lte": handover.get("date", date.today().isoformat())}

    wos = await db.rahaza_work_orders.find(
        {**query, "status": {"$in": ["released", "in_progress", "completed"]}},
        {"_id": 0, "wo_number": 1, "model_code": 1, "qty": 1,
         "qty_produced": 1, "qty_passed_qc": 1, "status": 1}
    ).limit(15).to_list(500)
    wo_summary = list(wos)

    try:
        from utils.shift_report_pdf import build_shift_report_pdf
        pdf_bytes = build_shift_report_pdf(handover, wo_summary=wo_summary)
    except Exception as e:
        logger.error(f"Shift PDF generation failed: {e}", exc_info=True)
        raise HTTPException(500, f"Gagal generate PDF: {e}")

    filename = f"Laporan-Shift_{handover.get('date','')}_v{handover.get('version',1)}.pdf"
    logger.info(f"Shift PDF generated for {handover_id} by {user.get('name')}")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )
