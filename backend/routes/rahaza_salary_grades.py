"""
CV. Dewi Aditya — Salary Grades / Struktur Gaji per Tier (Phase 9.2 P2)

Master salary bands with min / mid / max per grade.
Assigned per-employee. Used for payroll transparency & fairness audit.

Collection: rahaza_salary_grades
  { id, grade_code, grade_name, level, department (opt),
    min_salary, mid_salary, max_salary, currency='IDR',
    description, is_active, created_at, updated_at }

Employee field: salary_grade_id (reference) — linked via
  PUT /api/rahaza/employees/{id} with body {salary_grade_id}
"""
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/rahaza/salary-grades", tags=["rahaza-salary-grades"])


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


async def _require_admin(request: Request):
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya Admin/HR yang dapat mengelola struktur gaji.")
    return user


@router.get("")
async def list_grades(request: Request, active_only: bool = True):
    await require_auth(request)
    db = get_db()
    filt = {"is_active": True} if active_only else {}
    docs = await db.rahaza_salary_grades.find(filt, {"_id": 0}).sort("level", 1).to_list(500)
    return {"ok": True, "grades": [_s(d) for d in docs]}


@router.post("")
async def create_grade(request: Request):
    await _require_admin(request)
    db = get_db()
    body = await request.json()
    code = (body.get("grade_code") or "").strip().upper()
    if not code:
        raise HTTPException(400, "grade_code wajib.")
    if await db.rahaza_salary_grades.find_one({"grade_code": code}):
        raise HTTPException(409, f"Grade '{code}' sudah ada.")
    doc = {
        "id": _uid(),
        "grade_code": code,
        "grade_name": body.get("grade_name") or code,
        "level": int(body.get("level") or 1),
        "department": body.get("department") or "",
        "min_salary": float(body.get("min_salary") or 0),
        "mid_salary": float(body.get("mid_salary") or 0),
        "max_salary": float(body.get("max_salary") or 0),
        "currency": body.get("currency") or "IDR",
        "description": body.get("description") or "",
        "is_active": bool(body.get("is_active", True)),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_salary_grades.insert_one(doc)
    return {"ok": True, "grade": _s(doc)}


@router.put("/{grade_id}")
async def update_grade(grade_id: str, request: Request):
    await _require_admin(request)
    db = get_db()
    body = await request.json()
    body.pop("_id", None)
    body.pop("id", None)
    body.pop("created_at", None)
    body["updated_at"] = _now()
    res = await db.rahaza_salary_grades.update_one({"id": grade_id}, {"$set": body})
    if res.matched_count == 0:
        raise HTTPException(404, "Grade tidak ditemukan.")
    doc = await db.rahaza_salary_grades.find_one({"id": grade_id}, {"_id": 0})
    return {"ok": True, "grade": _s(doc)}


@router.delete("/{grade_id}")
async def delete_grade(grade_id: str, request: Request):
    await _require_admin(request)
    db = get_db()
    # Soft delete
    res = await db.rahaza_salary_grades.update_one(
        {"id": grade_id}, {"$set": {"is_active": False, "updated_at": _now()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Grade tidak ditemukan.")
    return {"ok": True}


@router.get("/audit")
async def audit(request: Request):
    """Check employees whose base_rate is outside their assigned grade range."""
    await require_auth(request)
    db = get_db()
    grades = await db.rahaza_salary_grades.find({"is_active": True}, {"_id": 0}).to_list(500)
    grade_map = {g["id"]: g for g in grades}

    employees = await db.rahaza_employees.find(
        {"active": True, "salary_grade_id": {"$exists": True, "$nin": [None, ""]}},
        {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "salary_grade_id": 1, "base_rate": 1},
    ).to_list(500)

    violations = []
    for emp in employees:
        g = grade_map.get(emp.get("salary_grade_id"))
        if not g:
            continue
        rate = float(emp.get("base_rate") or 0)
        if rate < g["min_salary"] or rate > g["max_salary"]:
            violations.append({
                "employee_code": emp["employee_code"],
                "name": emp["name"],
                "grade": g["grade_name"],
                "base_rate": rate,
                "grade_min": g["min_salary"],
                "grade_max": g["max_salary"],
                "status": "below" if rate < g["min_salary"] else "above",
            })
    return {"ok": True, "violations": violations, "total_graded": len(employees), "total_grades": len(grades)}
