"""
HR Shift Management Routes — Task 1.2
CV. Dewi Aditya

Prefix: /api/hr/shifts

Endpoints:
  GET  /                           list semua shift templates
  POST /                           buat shift template baru
  GET  /{id}                       detail shift
  PUT  /{id}                       update shift
  DELETE /{id}                     hapus (soft delete) shift
  POST /seed-defaults               seed default shifts

  GET  /assignments                 list semua assignments
  POST /assignments                 assign shift ke employee
  PUT  /assignments/{id}            update assignment
  DELETE /assignments/{id}          batalkan assignment
  GET  /assignments/employee/{emp_id}  assignments untuk employee tertentu

  GET  /employee/{emp_id}/active    shift aktif untuk employee (termasuk fallback)
  GET  /employee/{emp_id}/on-date   shift employee pada tanggal tertentu
  POST /calculate-hours             hitung jam kerja berdasarkan shift

  GET  /summary                     ringkasan assignments per shift
"""
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, log_activity
from services.hr_shift_service import (
    create_shift,
    assign_shift,
    get_employee_shift,
    calculate_shift_hours,
    seed_default_shifts,
    DEFAULT_SHIFT,
    _to_hr_shape,
    _active_shift_query,
)
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/hr/shifts", tags=["hr-shifts"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _coerce_id(v: str):
    try:
        return int(v)
    except (ValueError, TypeError):
        return v


def _ok(data=None, message="", **kwargs):
    r = {"status": "ok"}
    if message:
        r["message"] = message
    if data is not None:
        r["data"] = data
    r.update(kwargs)
    return r


# ─── Pydantic ─────────────────────────────────────────────────────────────────

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class ShiftCreateModel(BaseModel):
    shift_code: str
    shift_name: str
    start_time: str              # HH:MM
    end_time: str                # HH:MM
    break_duration_minutes: int = 60
    days_active: List[str] = Field(default_factory=lambda: ["Mon","Tue","Wed","Thu","Fri"])
    is_overnight: bool = False
    is_default: bool = False
    color: str = "#64748b"
    description: str = ""


class ShiftUpdateModel(BaseModel):
    shift_name: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    break_duration_minutes: Optional[int] = None
    days_active: Optional[List[str]] = None
    is_overnight: Optional[bool] = None
    is_default: Optional[bool] = None
    color: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class AssignShiftModel(BaseModel):
    employee_id: str
    shift_id: str
    effective_from: str          # YYYY-MM-DD
    effective_until: Optional[str] = None
    department: str = ""
    notes: str = ""


class CalcHoursModel(BaseModel):
    clock_in: str
    clock_out: str
    shift_id: str


# ─── Shift templates ────────────────────────────────────────────────────────────

@router.get("")
async def list_shifts(
    request: Request,
    status: Optional[str] = "active",
    include_default: bool = True,
):
    await require_auth(request)
    db = get_db()
    # BACKLOG-B: kanonik = rahaza_shifts (hr_shifts lama terisolasi, di-retire)
    q = _active_shift_query(status)
    items_raw = await db.rahaza_shifts.find(q, {"_id": 0}).to_list(200)
    items = sorted((_to_hr_shape(i) for i in items_raw), key=lambda x: x.get("shift_code", ""))
    if include_default:
        items = [DEFAULT_SHIFT] + items
    return _ok(items, total=len(items))


@router.post("")
async def create_shift_endpoint(request: Request, body: ShiftCreateModel):
    user = await require_auth(request)
    db = get_db()
    try:
        doc = await create_shift(db, body.dict())
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("email") or "",
        "create_shift",
        "hr_shifts",
        body.shift_name,
    )
    return _ok(doc, message=f"Shift {body.shift_name} berhasil dibuat.")


@router.get("/summary")
async def shift_summary(request: Request):
    await require_auth(request)
    db = get_db()
    total_shifts = await db.rahaza_shifts.count_documents(_active_shift_query("active"))
    total_assigned = await db.hr_shift_assignments.count_documents({"status": "active"})
    by_shift = await db.hr_shift_assignments.aggregate([
        {"$match": {"status": "active"}},
        {"$group": {"_id": "$shift_name", "count": {"$sum": 1}, "color": {"$first": "$shift_color"}}},
        {"$sort": {"count": -1}},
    ]).to_list(50)
    return _ok({
        "total_shifts": total_shifts,
        "total_assigned_employees": total_assigned,
        "unassigned_uses_default": True,
        "by_shift": [{"shift_name": b["_id"], "count": b["count"], "color": b.get("color","#64748b")} for b in by_shift],
    })


@router.post("/seed-defaults")
async def seed_defaults(request: Request):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Admin only.")
    db = get_db()
    # BACKLOG-B: TIDAK ADA delete_many — rahaza_shifts kanonik dipakai attendance/APS;
    # seed idempotent by code (skip yang sudah ada).
    await seed_default_shifts(db)
    total = await db.rahaza_shifts.count_documents({})
    return _ok(message=f"Seed selesai (idempotent). Total shift sekarang: {total}.")


# ─── Assignments — HARUS sebelum /{shift_id} ──────────────────────────────────

@router.get("/assignments")
async def list_assignments(
    request: Request,
    status: Optional[str] = "active",
    department: Optional[str] = None,
    shift_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
):
    await require_auth(request)
    db = get_db()
    q = {}
    if status:
        q["status"] = status
    if department:
        q["department"] = department
    if shift_id:
        q["shift_id"] = _coerce_id(shift_id)
    total = await db.hr_shift_assignments.count_documents(q)
    items = await db.hr_shift_assignments.find(q, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
    return _ok(items, total=total, skip=skip, limit=limit)


@router.post("/assignments")
async def create_assignment(request: Request, body: AssignShiftModel):
    user = await require_auth(request)
    db = get_db()
    assigned_by = user.get("full_name") or user.get("email") or ""
    try:
        doc = await assign_shift(
            db,
            employee_id=body.employee_id,
            shift_id=body.shift_id,
            effective_from=body.effective_from,
            effective_until=body.effective_until,
            assigned_by=assigned_by,
            department=body.department,
            notes=body.notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    await log_activity(
        str(user.get("id") or user.get("_id") or ""),
        user.get("full_name") or user.get("email") or "",
        "assign_shift",
        "hr_shift_assignments",
        f"emp={body.employee_id} shift={body.shift_id}",
    )
    return _ok(doc, message="Shift berhasil di-assign ke karyawan.")


@router.get("/assignments/employee/{employee_id}")
async def get_employee_assignments(request: Request, employee_id: str):
    await require_auth(request)
    db = get_db()
    items = await db.hr_shift_assignments.find(
        {"employee_id": employee_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(50)
    return _ok(items, total=len(items))


@router.delete("/assignments/{assignment_id}")
async def cancel_assignment(request: Request, assignment_id: str):
    await require_auth(request)
    db = get_db()
    await db.hr_shift_assignments.update_one(
        {"id": _coerce_id(assignment_id)},
        {"$set": {"status": "cancelled", "updated_at": _now()}},
    )
    return _ok(message="Assignment dibatalkan.")


# ─── Employee shift lookup — HARUS sebelum /{shift_id} ───────────────────────

@router.get("/employee/{employee_id}/active")
async def employee_active_shift(request: Request, employee_id: str):
    await require_auth(request)
    db = get_db()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    shift = await get_employee_shift(db, employee_id, today)
    return _ok(shift)


@router.get("/employee/{employee_id}/on-date")
async def employee_shift_on_date(
    request: Request,
    employee_id: str,
    date: str = Query(..., description="YYYY-MM-DD"),
):
    await require_auth(request)
    db = get_db()
    shift = await get_employee_shift(db, employee_id, date)
    return _ok(shift)


@router.post("/calculate-hours")
async def calculate_hours(request: Request, body: CalcHoursModel):
    await require_auth(request)
    db = get_db()
    if body.shift_id == "default":
        from services.hr_shift_service import DEFAULT_SHIFT as DS
        shift = DS
    else:
        shift = await db.rahaza_shifts.find_one({"id": _coerce_id(body.shift_id)}, {"_id": 0})
        if not shift:
            raise HTTPException(404, "Shift tidak ditemukan.")
        shift = _to_hr_shape(shift)
    result = calculate_shift_hours(body.clock_in, body.clock_out, shift)
    return _ok(result)


# ─── Shift CRUD by ID — setelah semua static routes ──────────────────────────

@router.get("/{shift_id}")
async def get_shift(request: Request, shift_id: str):
    await require_auth(request)
    if shift_id == "default":
        return _ok(DEFAULT_SHIFT)
    db = get_db()
    doc = await db.rahaza_shifts.find_one({"id": _coerce_id(shift_id)}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Shift tidak ditemukan.")
    return _ok(_to_hr_shape(doc))


@router.put("/{shift_id}")
async def update_shift(request: Request, shift_id: str, body: ShiftUpdateModel):
    await require_auth(request)
    db = get_db()
    doc = await db.rahaza_shifts.find_one({"id": _coerce_id(shift_id)})
    if not doc:
        raise HTTPException(404, "Shift tidak ditemukan.")
    update = {k: v for k, v in body.dict(exclude_none=True).items()}
    st = update.get("start_time") or doc.get("start_time")
    et = update.get("end_time") or doc.get("end_time")
    brk = update.get("break_duration_minutes") or doc.get("break_duration_minutes", 60)
    ov = update.get("is_overnight") if "is_overnight" in update else doc.get("is_overnight", False)
    from services.hr_shift_service import _calc_effective_hours
    update["effective_hours"] = _calc_effective_hours(st, et, brk, ov)
    # BACKLOG-B: mirror ke field kanonik agar attendance/APS tetap konsisten
    if "shift_name" in update:
        update["name"] = update["shift_name"]
    if "start_time" in update:
        update["check_in_time"] = update["start_time"]
    if "end_time" in update:
        update["check_out_time"] = update["end_time"]
    update["working_hours"] = update["effective_hours"]
    if update.get("status"):
        update["active"] = update["status"] == "active"
    update["updated_at"] = _now()
    await db.rahaza_shifts.update_one({"id": _coerce_id(shift_id)}, {"$set": update})
    return _ok(message="Shift diupdate.")


@router.delete("/{shift_id}")
async def delete_shift(request: Request, shift_id: str):
    user = await require_auth(request)
    if (user.get("role") or "").lower() not in ("superadmin", "admin", "owner"):
        raise HTTPException(403, "Admin only.")
    db = get_db()
    await db.rahaza_shifts.update_one(
        {"id": _coerce_id(shift_id)},
        {"$set": {"status": "inactive", "active": False, "updated_at": _now()}},
    )
    return _ok(message="Shift dinonaktifkan.")
