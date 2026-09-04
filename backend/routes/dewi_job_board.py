"""
Session 17 Batch 1 — P2-12: Internal Job Board

Features:
- Job posting by HR + Department managers
- Form submission dengan CV/docs
- Skill requirements matching
- Application tracking
- Career path visualization
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hr/job-board", tags=["job-board"])

# ============================================================================
# MODELS
# ============================================================================

class JobPosting(BaseModel):
    title: str
    department: str
    location: str
    job_type: str  # full-time, part-time, contract
    level: str  # junior, mid, senior, lead, manager
    description: str
    responsibilities: List[str]
    required_skills: List[str]
    preferred_skills: List[str] = []
    salary_range_min: Optional[int] = Field(default=None, ge=0)
    salary_range_max: Optional[int] = Field(default=None, ge=0)
    deadline: str  # ISO date

class JobApplication(BaseModel):
    job_id: str
    cover_letter: str
    additional_info: Optional[str] = None
    resume_url: Optional[str] = None

# ============================================================================
# JOB POSTINGS
# ============================================================================

@router.post("/jobs")
async def create_job_posting(request: Request, job: JobPosting):
    """Create a new job posting."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    user_role = user.get("role", "")
    
    # Authorization: HR or managers can post
    if user_role not in ["superadmin", "hr", "manager"]:
        raise HTTPException(403, "Only HR and managers can post jobs")
    
    job_data = job.dict()
    job_data["id"] = str(uuid.uuid4())
    job_data["posted_by"] = user.get("id")
    job_data["posted_by_name"] = user.get("name", "Unknown")
    job_data["posted_at"] = datetime.now(timezone.utc).isoformat()
    job_data["status"] = "open"
    job_data["application_count"] = 0
    
    await db["rahaza_job_postings"].insert_one(job_data)
    job_data.pop("_id", None)
    
    return {
        "success": True,
        "data": job_data,
        "message": "Job posted successfully"
    }

@router.get("/jobs")
async def list_job_postings(
    request: Request,
    status: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500)
):
    """List all job postings."""
    await require_auth(request)
    db = get_db()
    
    query = {}
    if status:
        query["status"] = status
    if department:
        query["department"] = department
    
    jobs = await db["rahaza_job_postings"].find(query).sort("posted_at", -1).limit(limit).to_list(length=limit)
    for j in jobs:
        j.pop("_id", None)
    
    return {
        "success": True,
        "data": jobs
    }

@router.get("/jobs/{job_id}")
async def get_job_posting(request: Request, job_id: str):
    """Get job posting details with skill matching."""
    await require_auth(request)
    db = get_db()
    
    job = await db["rahaza_job_postings"].find_one({"id": job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    
    job.pop("_id", None)
    
    # Skill matching for current user
    user = request.state.user
    employee = await db["rahaza_employees"].find_one({"id": user.get("id")})
    
    if employee:
        user_skills = employee.get("skills", [])
        required_skills = job.get("required_skills", [])
        preferred_skills = job.get("preferred_skills", [])
        
        # Calculate match score
        required_match = len([s for s in required_skills if s in user_skills])
        preferred_match = len([s for s in preferred_skills if s in user_skills])
        
        total_required = len(required_skills) if required_skills else 1
        total_preferred = len(preferred_skills) if preferred_skills else 1
        
        required_percentage = (required_match / total_required) * 100
        preferred_percentage = (preferred_match / total_preferred) * 100
        
        # Overall match (70% weight on required, 30% on preferred)
        overall_match = (required_percentage * 0.7) + (preferred_percentage * 0.3)
        
        job["skill_match"] = {
            "overall_score": round(overall_match, 1),
            "required_match": f"{required_match}/{len(required_skills)}",
            "preferred_match": f"{preferred_match}/{len(preferred_skills)}",
            "missing_required": [s for s in required_skills if s not in user_skills],
            "missing_preferred": [s for s in preferred_skills if s not in user_skills],
            "recommendation": "Strongly Recommended" if overall_match >= 80 else
                            "Recommended" if overall_match >= 60 else
                            "Consider" if overall_match >= 40 else
                            "Not Recommended"
        }
    
    return {
        "success": True,
        "data": job
    }

@router.patch("/jobs/{job_id}/close")
async def close_job_posting(request: Request, job_id: str):
    """Close a job posting."""
    await require_auth(request)
    db = get_db()
    
    result = await db["rahaza_job_postings"].update_one(
        {"id": job_id},
        {"$set": {"status": "closed", "closed_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(404, "Job not found")
    
    return {
        "success": True,
        "message": "Job closed"
    }

@router.delete("/jobs/{job_id}")
async def delete_job_posting(request: Request, job_id: str):
    """Delete a job posting."""
    await require_auth(request)
    db = get_db()
    
    result = await db["rahaza_job_postings"].delete_one({"id": job_id})
    
    if result.deleted_count == 0:
        raise HTTPException(404, "Job not found")
    
    return {
        "success": True,
        "message": "Job deleted"
    }

# ============================================================================
# JOB APPLICATIONS
# ============================================================================

@router.post("/applications")
async def submit_application(request: Request, application: JobApplication):
    """Submit a job application."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    
    # Check if job exists
    job = await db["rahaza_job_postings"].find_one({"id": application.job_id})
    if not job:
        raise HTTPException(404, "Job not found")
    
    if job.get("status") != "open":
        raise HTTPException(400, "This job is no longer accepting applications")
    
    # Check if already applied
    existing = await db["rahaza_job_applications"].find_one({
        "job_id": application.job_id,
        "applicant_id": user.get("id")
    })
    
    if existing:
        raise HTTPException(400, "You have already applied to this job")
    
    # Get applicant details
    employee = await db["rahaza_employees"].find_one({"id": user.get("id")})
    
    app_data = application.dict()
    app_data["id"] = str(uuid.uuid4())
    app_data["applicant_id"] = user.get("id")
    app_data["applicant_name"] = employee.get("name") if employee else user.get("name", "Unknown")
    app_data["applicant_department"] = employee.get("department") if employee else "N/A"
    app_data["applicant_current_title"] = employee.get("job_title") if employee else "N/A"
    app_data["job_title"] = job.get("title")
    app_data["applied_at"] = datetime.now(timezone.utc).isoformat()
    app_data["status"] = "pending"
    
    await db["rahaza_job_applications"].insert_one(app_data)
    app_data.pop("_id", None)
    
    # Update application count
    await db["rahaza_job_postings"].update_one(
        {"id": application.job_id},
        {"$inc": {"application_count": 1}}
    )
    
    return {
        "success": True,
        "data": app_data,
        "message": "Application submitted successfully"
    }

@router.get("/applications/my")
async def get_my_applications(request: Request):
    """Get current user's applications."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    
    applications = await db["rahaza_job_applications"].find(
        {"applicant_id": user.get("id")}
    ).sort("applied_at", -1).to_list(length=100)
    
    for app in applications:
        app.pop("_id", None)
    
    return {
        "success": True,
        "data": applications
    }

@router.get("/applications")
async def list_applications(
    request: Request,
    job_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500)
):
    """List applications (HR/Manager view)."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    if user.get("role") not in ["superadmin", "hr", "manager"]:
        raise HTTPException(403, "Unauthorized")
    
    query = {}
    if job_id:
        query["job_id"] = job_id
    if status:
        query["status"] = status
    
    applications = await db["rahaza_job_applications"].find(query).sort("applied_at", -1).limit(limit).to_list(length=limit)
    
    for app in applications:
        app.pop("_id", None)
    
    return {
        "success": True,
        "data": applications
    }

@router.patch("/applications/{app_id}/status")
async def update_application_status(request: Request, app_id: str, status: str = Query(...)):
    """Update application status."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    if user.get("role") not in ["superadmin", "hr", "manager"]:
        raise HTTPException(403, "Unauthorized")
    
    valid_statuses = ["pending", "reviewing", "shortlisted", "rejected", "accepted"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    
    result = await db["rahaza_job_applications"].update_one(
        {"id": app_id},
        {"$set": {"status": status, "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(404, "Application not found")
    
    return {
        "success": True,
        "message": f"Application status updated to {status}"
    }

# ============================================================================
# CAREER PATH
# ============================================================================

@router.get("/career-paths")
async def get_career_paths(request: Request, current_title: Optional[str] = Query(None)):
    """Get career path suggestions."""
    await require_auth(request)
    db = get_db()
    
    # Simplified career path data (could be enriched with ML in future)
    career_paths = {
        "Junior Developer": ["Mid Developer", "Senior Developer"],
        "Mid Developer": ["Senior Developer", "Tech Lead"],
        "Senior Developer": ["Tech Lead", "Engineering Manager", "Principal Engineer"],
        "Operator": ["Senior Operator", "Supervisor", "Line Leader"],
        "Supervisor": ["Line Leader", "Production Manager"],
        "Staff": ["Senior Staff", "Coordinator", "Supervisor"],
    }
    
    if current_title and current_title in career_paths:
        next_roles = career_paths[current_title]
        
        # Get job postings for next roles
        jobs = await db["rahaza_job_postings"].find({
            "title": {"$in": next_roles},
            "status": "open"
        }).to_list(length=50)
        
        for j in jobs:
            j.pop("_id", None)
        
        return {
            "success": True,
            "data": {
                "current_title": current_title,
                "next_roles": next_roles,
                "available_openings": jobs
            }
        }
    
    return {
        "success": True,
        "data": {
            "message": "Career paths available for specific titles",
            "available_paths": list(career_paths.keys())
        }
    }
