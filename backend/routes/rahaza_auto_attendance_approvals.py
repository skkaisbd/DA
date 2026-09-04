"""
Rahaza Auto-Attendance - Approvals
HR Approval Queue for pending attendance
"""
import uuid
import os
from datetime import datetime, timezone, date
from typing import Optional
from fastapi import APIRouter, Request, HTTPException
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from dotenv import load_dotenv

load_dotenv()

# WebAuthn imports (graceful fallback)
WEBAUTHN_AVAILABLE = False
try:
    from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
    from webauthn.helpers.exceptions import (
        InvalidRegistrationResponse,
        InvalidAuthenticationResponse,
    )
    WEBAUTHN_AVAILABLE = True
except Exception:
    def base64url_to_bytes(s): return b""
    def bytes_to_base64url(b): return ""
    class InvalidRegistrationResponse(Exception):
        pass
    class InvalidAuthenticationResponse(Exception):
        pass

# AI Face Compare

router = APIRouter(tags=["rahaza-auto-attendance-approvals"])

# Config
RP_ID = os.environ.get("WEBAUTHN_RP_ID", "analytics-builds.preview.emergentagent.com")
RP_NAME = os.environ.get("WEBAUTHN_RP_NAME", "Dewi Aditya ERP")
ORIGIN = os.environ.get("WEBAUTHN_ORIGIN", "https://da37-cmt-bridge.preview.emergentagent.com")
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()




@router.get("/attendance/approvals")
async def list_approval_queue(
    request: Request,
    status: Optional[str] = "pending",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    employee_id: Optional[str] = None,
):
    """Daftar absen yang perlu persetujuan HR."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya HR/Admin.")
    db = get_db()

    q = {}
    if status and status != "all":
        q["approval_status"] = status
    if employee_id:
        q["employee_id"] = employee_id
    if from_date or to_date:
        q["date"] = {}
        if from_date:
            q["date"]["$gte"] = from_date
        if to_date:
            q["date"]["$lte"] = to_date

    rows = await db.rahaza_attendance_events.find(q, {"_id": 0}).sort("date", -1).to_list(500)

    # Enrich with employee info
    emp_ids = list({r["employee_id"] for r in rows if r.get("employee_id")})
    emps = await db.rahaza_employees.find({"id": {"$in": emp_ids}}, {"_id": 0, "id": 1, "name": 1, "employee_code": 1, "department": 1}).to_list(500)
    e_map = {e["id"]: e for e in emps}
    for r in rows:
        e = e_map.get(r.get("employee_id")) or {}
        r["employee_name"] = e.get("name", "?")
        r["employee_code"] = e.get("employee_code", "-")
        r["department"] = e.get("department", "-")

    return serialize_doc(rows)


@router.post("/attendance/approvals/{event_id}/approve")
async def approve_attendance(event_id: str, request: Request):
    """HR menyetujui absen yang pending."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya HR/Admin.")
    db = get_db()
    body = await request.json()
    notes = body.get("notes", "")

    ev = await db.rahaza_attendance_events.find_one({"id": event_id})
    if not ev:
        raise HTTPException(404, "Record absen tidak ditemukan.")

    now = _now()
    await db.rahaza_attendance_events.update_one({"id": event_id}, {"$set": {
        "approval_status": "approved",
        "approval_by": user["id"],
        "approval_by_name": user.get("name", ""),
        "approval_notes": notes,
        "approval_at": now,
        "status": "hadir",
        "updated_by": user["id"], "updated_by_name": user.get("name", ""), "updated_at": now,
    }})
    await log_activity(user["id"], user.get("name", ""), "approve-attendance", "attendance", event_id)
    return {"ok": True, "message": "Absen disetujui."}


@router.post("/attendance/approvals/{event_id}/reject")
async def reject_attendance(event_id: str, request: Request):
    """HR menolak absen yang pending."""
    user = await require_auth(request)
    if user.get("role") not in ("superadmin", "admin", "owner", "hr"):
        raise HTTPException(403, "Hanya HR/Admin.")
    db = get_db()
    body = await request.json()
    notes = body.get("notes", "")

    ev = await db.rahaza_attendance_events.find_one({"id": event_id})
    if not ev:
        raise HTTPException(404, "Record absen tidak ditemukan.")

    now = _now()
    await db.rahaza_attendance_events.update_one({"id": event_id}, {"$set": {
        "approval_status": "rejected",
        "approval_by": user["id"],
        "approval_by_name": user.get("name", ""),
        "approval_notes": notes,
        "approval_at": now,
        "status": "alfa",
        "updated_by": user["id"], "updated_by_name": user.get("name", ""), "updated_at": now,
    }})
    await log_activity(user["id"], user.get("name", ""), "reject-attendance", "attendance", event_id)
    return {"ok": True, "message": "Absen ditolak."}


