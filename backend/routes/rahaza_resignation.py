"""
CV. Dewi Aditya — Employee Resignation / Exit Flow (Phase 9.3 P2)

Proper offboarding: status tracking, exit interview, clearance items.

Employee extra fields (via PUT /api/rahaza/employees/{id}):
  - employee_status: 'active' | 'resigned' | 'terminated' | 'retired'
  - resignation_date, last_working_date
  - reason_for_leaving, rehire_eligible (bool)
  - exit_interview: { conducted_at, conducted_by, notes, nps_score }
  - clearance: { asset_returned, final_payslip_issued, bpjs_transferred,
                 handover_done, notes }
"""
import uuid
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth

router = APIRouter(prefix="/api/rahaza/resignation", tags=["rahaza-resignation"])


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


async def _require_hr(request: Request):
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr", "manager"):
        raise HTTPException(403, "Hanya HR yang dapat proses resignasi.")
    return user


@router.post("/submit/{employee_id}")
async def submit_resignation(employee_id: str, request: Request):
    """Karyawan / HR submits resignation notice."""
    user = await require_auth(request)
    db = get_db()
    body = await request.json()

    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")

    # Permission: self or HR
    is_hr = user.get("role") in ("superadmin", "admin", "owner", "hr", "manager")
    is_self = user.get("employee_id") == employee_id
    if not (is_hr or is_self):
        raise HTTPException(403, "Tidak boleh submit untuk karyawan lain.")

    upd = {
        "employee_status": "resigning",  # pending HR acceptance
        "resignation_date": body.get("resignation_date") or date.today().isoformat(),
        "last_working_date": body.get("last_working_date"),
        "reason_for_leaving": body.get("reason_for_leaving") or "",
        "resignation_notes": body.get("notes") or "",
        "resignation_submitted_by": user["id"],
        "resignation_submitted_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_employees.update_one({"id": employee_id}, {"$set": upd})
    return {"ok": True, "status": "resigning"}


@router.post("/accept/{employee_id}")
async def accept_resignation(employee_id: str, request: Request):
    """HR accepts resignation — set status to 'resigned', deactivate."""
    user = await _require_hr(request)
    db = get_db()

    body = await request.json()
    rehire_eligible = bool(body.get("rehire_eligible", True))

    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")

    upd = {
        "employee_status": "resigned",
        "active": False,
        "rehire_eligible": rehire_eligible,
        "resignation_accepted_by": user["id"],
        "resignation_accepted_at": _now(),
        "updated_at": _now(),
    }
    await db.rahaza_employees.update_one({"id": employee_id}, {"$set": upd})
    return {"ok": True}


@router.post("/exit-interview/{employee_id}")
async def save_exit_interview(employee_id: str, request: Request):
    """Save exit interview results."""
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")

    interview = {
        "conducted_at": _now().isoformat(),
        "conducted_by": user.get("name", ""),
        "notes": body.get("notes") or "",
        "nps_score": int(body.get("nps_score") or 0),  # 0-10
        "positive_feedback": body.get("positive_feedback") or "",
        "improvement_areas": body.get("improvement_areas") or "",
        "would_recommend": bool(body.get("would_recommend", False)),
    }
    await db.rahaza_employees.update_one(
        {"id": employee_id},
        {"$set": {"exit_interview": interview, "updated_at": _now()}}
    )
    return {"ok": True, "interview": interview}


@router.put("/clearance/{employee_id}")
async def update_clearance(employee_id: str, request: Request):
    """Update clearance checklist items."""
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    emp = await db.rahaza_employees.find_one({"id": employee_id}, {"_id": 0})
    if not emp:
        raise HTTPException(404, "Karyawan tidak ditemukan.")
    existing = emp.get("clearance") or {}

    items = ["asset_returned", "final_payslip_issued", "bpjs_transferred",
             "handover_done", "account_disabled", "id_card_returned"]
    for it in items:
        if it in body:
            existing[it] = bool(body[it])
    if "notes" in body:
        existing["notes"] = body["notes"]
    existing["updated_at"] = _now().isoformat()
    existing["updated_by"] = user.get("name", "")

    await db.rahaza_employees.update_one(
        {"id": employee_id},
        {"$set": {"clearance": existing, "updated_at": _now()}}
    )
    return {"ok": True, "clearance": existing}


@router.get("/list")
async def list_resignations(request: Request, status: Optional[str] = None):
    """List employees who are resigning or have resigned."""
    await require_auth(request)
    db = get_db()
    filt = {"employee_status": {"$in": ["resigning", "resigned", "terminated"]}}
    if status:
        filt["employee_status"] = status
    docs = await db.rahaza_employees.find(filt, {"_id": 0}).sort("resignation_date", -1).to_list(500)
    return {"ok": True, "items": [_s(d) for d in docs]}
