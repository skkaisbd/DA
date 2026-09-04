"""
Session 17 Batch 1 — P2-11: Auto Shift Scheduler

Features:
- Customizable shift templates
- Auto-generate schedules based on skills, availability, workload balance
- Manual trigger only
- Constraint handling (max hours, rest periods, skill requirements)
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hr/shift-scheduler", tags=["shift-scheduler"])

# ============================================================================
# MODELS
# ============================================================================

class ShiftTemplate(BaseModel):
    name: str
    start_time: str  # HH:MM format
    end_time: str
    required_skills: List[str] = []
    min_employees: int = 1
    max_employees: int = 10

class ScheduleConstraints(BaseModel):
    max_hours_per_week: int = 48
    min_rest_hours: int = 12
    prefer_consecutive_days: bool = True
    balance_workload: bool = True

class GenerateScheduleRequest(BaseModel):
    start_date: str
    end_date: str
    department: Optional[str] = None
    shift_templates: List[str]  # Template IDs
    constraints: ScheduleConstraints = ScheduleConstraints()

# ============================================================================
# SHIFT TEMPLATES
# ============================================================================

@router.post("/templates")
async def create_shift_template(request: Request, template: ShiftTemplate):
    """Create a new shift template."""
    await require_auth(request)
    db = get_db()
    
    template_data = template.dict()
    template_data["id"] = str(uuid.uuid4())
    template_data["created_at"] = datetime.now(timezone.utc).isoformat()
    template_data["created_by"] = request.state.user.get("id")
    
    await db["rahaza_shift_templates"].insert_one(template_data)
    
    # Remove MongoDB _id before returning
    template_data.pop("_id", None)
    
    return {
        "success": True,
        "data": template_data,
        "message": "Shift template created"
    }

@router.get("/templates")
async def list_shift_templates(request: Request):
    """List all shift templates."""
    await require_auth(request)
    db = get_db()
    
    templates = await db["rahaza_shift_templates"].find().to_list(length=100)
    for t in templates:
        t.pop("_id", None)
    
    return {
        "success": True,
        "data": templates
    }

@router.delete("/templates/{template_id}")
async def delete_shift_template(request: Request, template_id: str):
    """Delete a shift template."""
    await require_auth(request)
    db = get_db()
    
    result = await db["rahaza_shift_templates"].delete_one({"id": template_id})
    
    if result.deleted_count == 0:
        raise HTTPException(404, "Template not found")
    
    return {
        "success": True,
        "message": "Template deleted"
    }

# ============================================================================
# SCHEDULE GENERATION
# ============================================================================

@router.post("/generate")
async def generate_schedule(request: Request, gen_request: GenerateScheduleRequest):
    """Generate shift schedule automatically."""
    await require_auth(request)
    db = get_db()
    
    # Fetch employees
    query = {"status": "active"}
    if gen_request.department:
        query["department"] = gen_request.department
    
    employees = await db["rahaza_employees"].find(query).to_list(length=500)
    
    if not employees:
        raise HTTPException(400, "No employees found for scheduling")
    
    # Fetch shift templates
    templates = await db["rahaza_shift_templates"].find(
        {"id": {"$in": gen_request.shift_templates}}
    ).to_list(length=50)
    
    if not templates:
        raise HTTPException(400, "No shift templates found")
    
    # Generate schedule logic
    schedule = await _generate_schedule_logic(
        employees,
        templates,
        gen_request.start_date,
        gen_request.end_date,
        gen_request.constraints
    )
    
    # Save schedule
    schedule_doc = {
        "id": str(uuid.uuid4()),
        "start_date": gen_request.start_date,
        "end_date": gen_request.end_date,
        "department": gen_request.department,
        "shifts": schedule["shifts"],
        "metadata": schedule["metadata"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": request.state.user.get("id"),
        "status": "draft"
    }
    
    await db["rahaza_schedules"].insert_one(schedule_doc)
    
    # Remove MongoDB _id before returning
    schedule_doc.pop("_id", None)
    
    return {
        "success": True,
        "data": schedule_doc,
        "message": "Schedule generated successfully"
    }

async def _generate_schedule_logic(
    employees: List[Dict],
    templates: List[Dict],
    start_date: str,
    end_date: str,
    constraints: ScheduleConstraints
) -> Dict[str, Any]:
    """Core scheduling algorithm."""
    from datetime import datetime
    import random
    
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    
    shifts = []
    employee_hours = {emp["id"]: 0 for emp in employees}
    employee_last_shift = {emp["id"]: None for emp in employees}
    
    current_date = start
    while current_date <= end:
        date_str = current_date.strftime("%Y-%m-%d")
        
        for template in templates:
            # Calculate required employees
            required = template.get("min_employees", 1)
            
            # Filter eligible employees
            eligible = []
            for emp in employees:
                emp_id = emp["id"]
                
                # Check max hours constraint
                if employee_hours[emp_id] >= constraints.max_hours_per_week:
                    continue
                
                # Check rest hours constraint
                if employee_last_shift[emp_id]:
                    last_end = datetime.fromisoformat(employee_last_shift[emp_id])
                    if (current_date - last_end).total_seconds() / 3600 < constraints.min_rest_hours:
                        continue
                
                # Check skill requirements
                emp_skills = emp.get("skills", [])
                required_skills = template.get("required_skills", [])
                if required_skills and not any(s in emp_skills for s in required_skills):
                    continue
                
                eligible.append(emp)
            
            # Select employees (prefer balanced workload)
            if constraints.balance_workload:
                eligible.sort(key=lambda e: employee_hours[e["id"]])
            else:
                random.shuffle(eligible)
            
            selected = eligible[:required]
            
            if len(selected) < required:
                logger.warning(f"Not enough employees for {template['name']} on {date_str}")
            
            # Create shift assignments
            for emp in selected:
                emp_id = emp["id"]
                shift_duration = 8  # Simplified: 8 hours per shift
                
                shifts.append({
                    "id": str(uuid.uuid4()),
                    "date": date_str,
                    "shift_name": template["name"],
                    "start_time": template["start_time"],
                    "end_time": template["end_time"],
                    "employee_id": emp_id,
                    "employee_name": emp["name"],
                    "department": emp.get("department", "N/A")
                })
                
                employee_hours[emp_id] += shift_duration
                employee_last_shift[emp_id] = current_date.isoformat()
        
        current_date += timedelta(days=1)
    
    # Calculate metadata
    total_hours = sum(employee_hours.values())
    avg_hours = total_hours / len(employees) if employees else 0
    
    return {
        "shifts": shifts,
        "metadata": {
            "total_shifts": len(shifts),
            "total_hours": total_hours,
            "average_hours_per_employee": round(avg_hours, 2),
            "employees_scheduled": len([h for h in employee_hours.values() if h > 0])
        }
    }

# ============================================================================
# SCHEDULE MANAGEMENT
# ============================================================================

@router.get("/schedules")
async def list_schedules(request: Request, status: Optional[str] = None, limit: int = Query(20, ge=1, le=500)):
    """List all schedules."""
    await require_auth(request)
    db = get_db()
    
    query = {}
    if status:
        query["status"] = status
    
    schedules = await db["rahaza_schedules"].find(query).sort("generated_at", -1).limit(limit).to_list(length=limit)
    for s in schedules:
        s.pop("_id", None)
    
    return {
        "success": True,
        "data": schedules
    }

@router.get("/schedules/{schedule_id}")
async def get_schedule(request: Request, schedule_id: str):
    """Get schedule details."""
    await require_auth(request)
    db = get_db()
    
    schedule = await db["rahaza_schedules"].find_one({"id": schedule_id})
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    
    schedule.pop("_id", None)
    
    return {
        "success": True,
        "data": schedule
    }

@router.patch("/schedules/{schedule_id}/publish")
async def publish_schedule(request: Request, schedule_id: str):
    """Publish a schedule (change status to published)."""
    await require_auth(request)
    db = get_db()
    
    result = await db["rahaza_schedules"].update_one(
        {"id": schedule_id},
        {"$set": {"status": "published", "published_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(404, "Schedule not found")
    
    return {
        "success": True,
        "message": "Schedule published"
    }

@router.delete("/schedules/{schedule_id}")
async def delete_schedule(request: Request, schedule_id: str):
    """Delete a schedule."""
    await require_auth(request)
    db = get_db()
    
    result = await db["rahaza_schedules"].delete_one({"id": schedule_id})
    
    if result.deleted_count == 0:
        raise HTTPException(404, "Schedule not found")
    
    return {
        "success": True,
        "message": "Schedule deleted"
    }
