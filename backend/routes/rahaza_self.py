"""
PT Rahaza — Staff Self-Service Portal

Karyawan dapat melihat data personal mereka:
- Profil karyawan (linked employee)
- Kehadiran personal
- Payslip personal

Note: Admin dapat menghubungkan user ke employee melalui endpoint PUT /api/users/{user_id}/link-employee

Endpoints (prefix /api/rahaza/self):
  GET  /self/profile       — profil user + data karyawan
  GET  /self/attendance    — kehadiran personal (by logged-in user.employee_id)
  GET  /self/payslips      — payslip personal
  GET  /self/payslip/{id}  — detail payslip

Admin Utility:
  PUT  /self/admin/link-employee   — link user_id → employee_id (admin only)
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc
from datetime import datetime, timezone, date, timedelta
from typing import Optional
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/rahaza", tags=["rahaza-self"])


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


async def _get_employee_for_user(db, user_id: str):
    """Return (user, employee) untuk `user_id`.

    BUG-4 (2026-07-26): ini dulu SALINAN KELIMA aturan identitas karyawan
    (employee_id → user_id → email) dengan filter `active: True` yang berbeda
    dari SSOT (`active: {$ne: False}`) — karyawan lama tanpa field `active`
    tidak pernah ketemu. Sekarang mendelegasikan ke SSOT
    `utils/employee_identity.resolve_my_employee`.
    """
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return None, None
    from utils.employee_identity import resolve_my_employee
    emp = await resolve_my_employee(db, user)
    return user, emp


@router.get("/self/profile")
async def self_profile(request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_employee_for_user(db, user["id"])
    return {
        "user_id": user["id"],
        "name": user.get("name"),
        "email": user.get("email"),
        "role": user.get("role"),
        "employee_id": user.get("employee_id"),
        "employee": emp,
        "is_linked": emp is not None,
    }


@router.get("/self/attendance")
async def self_attendance(
    request: Request,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
    limit: int = 60,
):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_employee_for_user(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun Anda belum dihubungkan ke data karyawan. Hubungi Admin HR untuk menghubungkan akun Anda.")

    emp_id = emp["id"]
    if not from_:
        from_ = (date.today() - timedelta(days=30)).isoformat()
    if not to:
        to = date.today().isoformat()

    q = {
        "employee_id": emp_id,
        "date": {"$gte": from_, "$lte": to},
    }
    rows = await db.rahaza_attendance_events.find(q, {"_id": 0}).sort("date", -1).limit(limit).to_list(500)

    # Summary stats
    summary = {"hadir": 0, "izin": 0, "sakit": 0, "alfa": 0, "cuti": 0, "libur": 0}
    total_hours = 0.0
    for r in rows:
        s = r.get("status", "hadir")
        if s in summary:
            summary[s] += 1
        total_hours += r.get("hours_worked") or 0

    return {
        "employee_id": emp_id,
        "employee_name": emp.get("name"),
        "employee_code": emp.get("employee_code"),
        "from": from_, "to": to,
        "summary": summary,
        "total_hours_worked": round(total_hours, 1),
        "records": rows,
    }


@router.get("/self/payslips")
async def self_payslips(
    request: Request,
    from_: Optional[str] = Query(None, alias="from"),
    to: Optional[str] = None,
):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_employee_for_user(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun Anda belum dihubungkan ke data karyawan. Hubungi Admin HR.")

    emp_id = emp["id"]
    q = {"employee_id": emp_id}
    if from_ or to:
        q["period_from"] = {}
        if from_:
            q["period_from"]["$gte"] = from_
        if to:
            q["period_from"]["$lte"] = to

    slips = await db.rahaza_payslips.find(q, {"_id": 0}).sort("period_from", -1).to_list(500)

    # Enrich with run info
    run_ids = list({s.get("run_id") for s in slips if s.get("run_id")})
    runs = await db.rahaza_payroll_runs.find({"id": {"$in": run_ids}}, {"_id": 0}).to_list(500) if run_ids else []
    run_map = {r["id"]: r for r in runs}
    for s in slips:
        run = run_map.get(s.get("run_id"), {})
        s["run_period_label"] = f"{run.get('period_from', '')[:7]}" if run else ""
        s["run_status"] = run.get("status", "")

    return {
        "employee_id": emp_id,
        "employee_name": emp.get("name"),
        "employee_code": emp.get("employee_code"),
        "wage_scheme": emp.get("wage_scheme"),
        "pay_scheme": emp.get("pay_scheme") or emp.get("wage_scheme"),  # FIX: add pay_scheme alias
        "total_slips": len(slips),
        "slips": slips,
    }


@router.get("/self/payslip/{slip_id}")
async def self_payslip_detail(slip_id: str, request: Request):
    user = await require_auth(request)
    db = get_db()
    _, emp = await _get_employee_for_user(db, user["id"])
    if not emp:
        raise HTTPException(409, "Akun belum terhubung ke data karyawan.")

    slip = await db.rahaza_payslips.find_one({"id": slip_id, "employee_id": emp["id"]}, {"_id": 0})
    if not slip:
        raise HTTPException(404, "Payslip tidak ditemukan atau bukan milik Anda.")
    return serialize_doc(slip)


# ─── ADMIN: Link user → employee ─────────────────────────────────────────
@router.put("/self/admin/link-employee")
async def admin_link_employee(request: Request):
    user = await require_auth(request)
    if user.get("role") not in ["superadmin", "admin", "owner", "hr"]:
        raise HTTPException(403, "Hanya admin / HR yang boleh menghubungkan akun ke karyawan.")
    db = get_db()
    body = await request.json()
    user_id   = body.get("user_id")
    emp_id    = body.get("employee_id")  # pass null to unlink
    if not user_id:
        raise HTTPException(400, "user_id wajib diisi.")
    target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not target_user:
        raise HTTPException(404, "User tidak ditemukan.")
    if emp_id:
        emp = await db.rahaza_employees.find_one({"id": emp_id}, {"_id": 0})
        if not emp:
            raise HTTPException(404, "Karyawan tidak ditemukan.")
    await db.users.update_one({"id": user_id}, {"$set": {"employee_id": emp_id, "updated_at": _now().isoformat()}})
    return {"ok": True, "user_id": user_id, "employee_id": emp_id}
