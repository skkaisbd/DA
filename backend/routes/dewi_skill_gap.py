"""
Session 17 Batch 1 — P2-20: Skill Gap Analysis

Features:
- Multi-level analysis (Individual, Department, Company-wide)
- Comprehensive action plans (training + hiring recommendations)
- Skill matrix management
- Gap identification with priority scoring
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hr/skill-gap", tags=["skill-gap"])

# ============================================================================
# MODELS
# ============================================================================

class SkillRequirement(BaseModel):
    skill_name: str
    category: str  # technical, soft, domain
    required_level: int  # 1-5
    priority: str  # critical, high, medium, low
    for_role: Optional[str] = None
    for_department: Optional[str] = None

class AnalysisRequest(BaseModel):
    level: str  # individual, department, company
    target_id: Optional[str] = None  # employee_id or department name
    include_recommendations: bool = True

# ============================================================================
# SKILL REQUIREMENTS MANAGEMENT
# ============================================================================

@router.get("/departments")
async def list_departments(request: Request):
    """List unique departments from active employees (helper for frontend dropdowns)."""
    await require_auth(request)
    db = get_db()
    departments = await db["rahaza_employees"].distinct("department", {"active": True})
    departments = sorted([d for d in departments if d])
    return {
        "success": True,
        "data": departments
    }

@router.post("/requirements")
async def create_skill_requirement(request: Request, requirement: SkillRequirement):
    """Define skill requirements for roles/departments."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    if user.get("role") not in ["superadmin", "hr", "manager"]:
        raise HTTPException(403, "Unauthorized")
    
    req_data = requirement.dict()
    req_data["id"] = str(uuid.uuid4())
    req_data["created_by"] = user.get("id")
    req_data["created_at"] = datetime.now(timezone.utc).isoformat()
    
    await db["rahaza_skill_requirements"].insert_one(req_data)
    req_data.pop("_id", None)
    
    return {
        "success": True,
        "data": req_data,
        "message": "Skill requirement created"
    }

@router.get("/requirements")
async def list_skill_requirements(
    request: Request,
    for_role: Optional[str] = Query(None),
    for_department: Optional[str] = Query(None)
):
    """List skill requirements."""
    await require_auth(request)
    db = get_db()
    
    query = {}
    if for_role:
        query["for_role"] = for_role
    if for_department:
        query["for_department"] = for_department
    
    requirements = await db["rahaza_skill_requirements"].find(query).to_list(length=200)
    for r in requirements:
        r.pop("_id", None)
    
    return {
        "success": True,
        "data": requirements
    }

# ============================================================================
# INDIVIDUAL ANALYSIS
# ============================================================================

@router.post("/analyze/individual")
async def analyze_individual(request: Request, analysis: AnalysisRequest):
    """Analyze skill gaps for an individual employee."""
    await require_auth(request)
    db = get_db()
    
    employee_id = analysis.target_id
    if not employee_id:
        # Analyze current user
        employee_id = request.state.user.get("id")
    
    employee = await db["rahaza_employees"].find_one({"id": employee_id})
    if not employee:
        raise HTTPException(404, "Employee not found")
    
    # Get employee skills
    employee.get("skills", [])
    current_skill_levels = employee.get("skill_levels", {})  # {skill_name: level}
    
    # Get required skills for their role
    job_title = employee.get("job_title")
    department = employee.get("department")
    
    requirements = await db["rahaza_skill_requirements"].find({
        "$or": [
            {"for_role": job_title},
            {"for_department": department}
        ]
    }).to_list(length=100)
    
    # Calculate gaps
    gaps = []
    for req in requirements:
        skill_name = req["skill_name"]
        required_level = req["required_level"]
        current_level = current_skill_levels.get(skill_name, 0)
        
        if current_level < required_level:
            gap_size = required_level - current_level
            gaps.append({
                "skill_name": skill_name,
                "category": req["category"],
                "current_level": current_level,
                "required_level": required_level,
                "gap_size": gap_size,
                "priority": req["priority"],
                "gap_percentage": round((gap_size / required_level) * 100, 1)
            })
    
    # Sort by priority and gap size
    priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    gaps.sort(key=lambda g: (priority_order.get(g["priority"], 4), -g["gap_size"]))
    
    # Generate recommendations if requested
    recommendations = []
    if analysis.include_recommendations:
        recommendations = await _generate_individual_recommendations(gaps, employee)
    
    result = {
        "employee_id": employee_id,
        "employee_name": employee.get("name"),
        "job_title": job_title,
        "department": department,
        "total_gaps": len(gaps),
        "critical_gaps": len([g for g in gaps if g["priority"] == "critical"]),
        "gaps": gaps,
        "recommendations": recommendations,
        "analyzed_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Save analysis
    result["id"] = str(uuid.uuid4())
    result["level"] = "individual"
    await db["rahaza_skill_analyses"].insert_one(result)
    result.pop("_id", None)
    
    return {
        "success": True,
        "data": result
    }

async def _generate_individual_recommendations(gaps: List[Dict], employee: Dict) -> List[Dict]:
    """Generate training and development recommendations."""
    recommendations = []
    
    # Group gaps by category
    by_category = {}
    for gap in gaps[:10]:  # Top 10 gaps
        cat = gap["category"]
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append(gap)
    
    # Generate recommendations per category
    for category, cat_gaps in by_category.items():
        skills = [g["skill_name"] for g in cat_gaps]
        
        recommendations.append({
            "type": "training",
            "category": category,
            "title": f"{category.title()} Skills Development Program",
            "description": f"Focus on developing: {', '.join(skills)}",
            "skills_addressed": skills,
            "estimated_duration": "3-6 months",
            "priority": cat_gaps[0]["priority"],
            "suggested_actions": [
                "Enroll in relevant online courses (Coursera, Udemy)",
                "Attend workshops or seminars",
                "Seek mentorship from senior team members",
                "Practice through real project assignments"
            ]
        })
    
    return recommendations

# ============================================================================
# DEPARTMENT ANALYSIS
# ============================================================================

@router.post("/analyze/department")
async def analyze_department(request: Request, analysis: AnalysisRequest):
    """Analyze skill gaps at department level."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    if user.get("role") not in ["superadmin", "hr", "manager"]:
        raise HTTPException(403, "Unauthorized")
    
    department_name = analysis.target_id
    if not department_name:
        raise HTTPException(400, "Department name required")
    
    # Get all employees in department
    employees = await db["rahaza_employees"].find({
        "department": department_name,
        "active": True
    }).to_list(length=500)
    
    if not employees:
        raise HTTPException(404, "No employees found in department")
    
    # Get department skill requirements
    requirements = await db["rahaza_skill_requirements"].find({
        "for_department": department_name
    }).to_list(length=100)
    
    # Aggregate skills
    skill_coverage = {}  # {skill_name: {total_employees, employees_with_skill, avg_level}}
    
    for req in requirements:
        skill_name = req["skill_name"]
        skill_coverage[skill_name] = {
            "required_level": req["required_level"],
            "priority": req["priority"],
            "category": req["category"],
            "total_employees": len(employees),
            "employees_with_skill": 0,
            "total_level": 0,
            "gap_employees": []
        }
    
    # Calculate coverage
    for emp in employees:
        emp.get("skills", [])
        emp_skill_levels = emp.get("skill_levels", {})
        
        for skill_name in skill_coverage:
            coverage = skill_coverage[skill_name]
            current_level = emp_skill_levels.get(skill_name, 0)
            
            if current_level > 0:
                coverage["employees_with_skill"] += 1
                coverage["total_level"] += current_level
            
            if current_level < coverage["required_level"]:
                coverage["gap_employees"].append({
                    "employee_id": emp["id"],
                    "employee_name": emp["name"],
                    "current_level": current_level,
                    "gap_size": coverage["required_level"] - current_level
                })
    
    # Calculate metrics
    gaps = []
    for skill_name, coverage in skill_coverage.items():
        avg_level = coverage["total_level"] / coverage["total_employees"] if coverage["total_employees"] > 0 else 0
        coverage_percentage = (coverage["employees_with_skill"] / coverage["total_employees"]) * 100 if coverage["total_employees"] > 0 else 0
        
        gaps.append({
            "skill_name": skill_name,
            "category": coverage["category"],
            "required_level": coverage["required_level"],
            "average_level": round(avg_level, 2),
            "coverage_percentage": round(coverage_percentage, 1),
            "employees_with_gap": len(coverage["gap_employees"]),
            "priority": coverage["priority"],
            "gap_severity": "High" if coverage_percentage < 50 else "Medium" if coverage_percentage < 75 else "Low"
        })
    
    # Generate recommendations
    recommendations = []
    if analysis.include_recommendations:
        recommendations = await _generate_department_recommendations(gaps, department_name, len(employees))
    
    result = {
        "department": department_name,
        "total_employees": len(employees),
        "total_gaps": len(gaps),
        "critical_gaps": len([g for g in gaps if g["priority"] == "critical"]),
        "gaps": gaps,
        "recommendations": recommendations,
        "analyzed_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Save analysis
    result["id"] = str(uuid.uuid4())
    result["level"] = "department"
    await db["rahaza_skill_analyses"].insert_one(result)
    result.pop("_id", None)
    
    return {
        "success": True,
        "data": result
    }

async def _generate_department_recommendations(gaps: List[Dict], department: str, employee_count: int) -> List[Dict]:
    """Generate department-level recommendations."""
    recommendations = []
    
    # Training recommendations for low coverage skills
    low_coverage = [g for g in gaps if g["coverage_percentage"] < 50]
    if low_coverage:
        recommendations.append({
            "type": "training_program",
            "title": f"Department-wide {department} Skills Training",
            "description": f"Launch training program for {len(low_coverage)} critical skills with low coverage",
            "skills": [g["skill_name"] for g in low_coverage[:5]],
            "estimated_cost": f"${employee_count * 500:,}",
            "timeline": "6 months",
            "priority": "high"
        })
    
    # Hiring recommendations for critical gaps
    critical_gaps = [g for g in gaps if g["priority"] == "critical" and g["coverage_percentage"] < 30]
    if critical_gaps:
        recommendations.append({
            "type": "hiring",
            "title": "Hire specialists for critical skill gaps",
            "description": f"Consider hiring {len(critical_gaps)} specialists to fill critical skill gaps",
            "skills_needed": [g["skill_name"] for g in critical_gaps],
            "positions_suggested": len(critical_gaps),
            "priority": "critical"
        })
    
    return recommendations

# ============================================================================
# COMPANY-WIDE ANALYSIS
# ============================================================================

@router.post("/analyze/company")
async def analyze_company(request: Request, analysis: AnalysisRequest):
    """Analyze skill gaps across entire company."""
    await require_auth(request)
    db = get_db()
    
    user = request.state.user
    if user.get("role") not in ["superadmin", "hr"]:
        raise HTTPException(403, "Unauthorized - requires HR access")
    
    # Get all active employees
    employees = await db["rahaza_employees"].find({"active": True}).to_list(length=2000)
    
    if not employees:
        raise HTTPException(404, "No employees found")
    
    # Get all skill requirements
    requirements = await db["rahaza_skill_requirements"].find().to_list(length=500)
    
    # Department breakdown
    departments = {}
    for emp in employees:
        dept = emp.get("department", "Unknown")
        if dept not in departments:
            departments[dept] = []
        departments[dept].append(emp)
    
    # Analyze each department
    dept_analyses = []
    for dept_name, dept_employees in departments.items():
        dept_req = [r for r in requirements if r.get("for_department") == dept_name]
        
        if dept_req:
            analysis_result = {
                "department": dept_name,
                "employee_count": len(dept_employees),
                "skill_requirements": len(dept_req),
                "avg_coverage": 0  # Simplified - could be more detailed
            }
            dept_analyses.append(analysis_result)
    
    # Overall recommendations
    recommendations = []
    if analysis.include_recommendations:
        recommendations = [
            {
                "type": "strategic",
                "title": "Company-wide Skills Development Initiative",
                "description": "Launch comprehensive upskilling program across all departments",
                "estimated_budget": f"${len(employees) * 1000:,}",
                "timeline": "12 months",
                "expected_impact": "Reduce skill gaps by 60%"
            },
            {
                "type": "hiring",
                "title": "Strategic Hiring Plan",
                "description": "Hire key talent to fill critical skill gaps that cannot be filled through training",
                "positions_needed": len([r for r in requirements if r.get("priority") == "critical"]) // 3,
                "timeline": "6 months"
            }
        ]
    
    result = {
        "total_employees": len(employees),
        "total_departments": len(departments),
        "department_breakdown": dept_analyses,
        "recommendations": recommendations,
        "analyzed_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Save analysis
    result["id"] = str(uuid.uuid4())
    result["level"] = "company"
    await db["rahaza_skill_analyses"].insert_one(result)
    result.pop("_id", None)
    
    return {
        "success": True,
        "data": result
    }

# ============================================================================
# ANALYSIS HISTORY
# ============================================================================

@router.get("/analyses")
async def list_analyses(
    request: Request,
    level: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=500)
):
    """List past skill gap analyses."""
    await require_auth(request)
    db = get_db()
    
    query = {}
    if level:
        query["level"] = level
    
    analyses = await db["rahaza_skill_analyses"].find(query).sort("analyzed_at", -1).limit(limit).to_list(length=limit)
    
    for a in analyses:
        a.pop("_id", None)
        # Remove detailed gaps from list view
        if "gaps" in a:
            a["gap_count"] = len(a["gaps"])
            a.pop("gaps")
    
    return {
        "success": True,
        "data": analyses
    }
