# ruff: noqa: F401
"""
dewi_kpi_periods.py — Period Configuration Management
Extracted from dewi_kpi.py (2729 LOC monolith)

Refactored: Session #11.19 Final - CAREFUL APPROACH
"""
from fastapi import APIRouter, Request, HTTPException, Query
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.dewi_kpi_shared import (
    _uid, _now, _s, _grade,
    _require_hr, _get_linked_employee,
    _calc_section_score, _calc_attitude_score, _calc_absensi_score,
    DEFAULT_QUESTIONS,
)
from routes.shared import get_pagination_params, paginated_response
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dewi/kpi", tags=["dewi-kpi-periods"])

@router.get("/periods")
async def list_periods(request: Request):
    await require_auth(request)
    db = get_db()
    sp = request.query_params
    # Dual-mode: paginated or full list
    if sp.get("page") or sp.get("limit"):
        page, limit, skip = get_pagination_params(request, default_limit=20)
        total = await db.da_kpi_periods.count_documents({})
        docs = await db.da_kpi_periods.find({}, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)
        result = []
        for d in docs:
            d = _s(d)
            d["participant_count"] = len(d.get("participant_employee_ids", []))
            result.append(d)
        return paginated_response(result, total, page, limit)
    docs = await db.da_kpi_periods.find({}, {"_id": 0}).sort("created_at", -1).to_list(100)
    # Enrich with participant count
    result = []
    for d in docs:
        d = _s(d)
        d["participant_count"] = len(d.get("participant_employee_ids", []))
        result.append(d)
    return {"ok": True, "periods": result}


@router.post("/periods")
async def create_period(request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    name = (body.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "Nama periode wajib diisi.")

    doc = {
        "period_id": _uid(),
        "name": name,
        "period_from": body.get("period_from") or "",
        "period_to": body.get("period_to") or "",
        "working_days": int(body.get("working_days") or 26),
        "status": "draft",
        "participant_employee_ids": body.get("participant_employee_ids") or [],
        "supervisor_assignments": body.get("supervisor_assignments") or [],
        "notes": body.get("notes") or "",
        "created_by": user["id"],
        "created_by_name": user.get("name", ""),
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.da_kpi_periods.insert_one(doc)
    return {"ok": True, "period": _s(doc)}


@router.put("/periods/{period_id}")
async def update_period(period_id: str, request: Request):
    user = await _require_hr(request)
    db = get_db()
    body = await request.json()

    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")

    # Only allow certain status transitions
    new_status = body.get("status")
    if new_status:
        valid_transitions = {
            "draft": ["open", "draft"],
            "open": ["closed", "open"],
            "closed": ["finalized", "closed"],
            "finalized": ["finalized"],
        }
        current = period.get("status", "draft")
        if new_status not in valid_transitions.get(current, []):
            raise HTTPException(400, f"Tidak bisa ubah status dari '{current}' ke '{new_status}'.")

    allowed = ["name", "period_from", "period_to", "working_days", "status",
               "participant_employee_ids", "supervisor_assignments", "notes"]
    upd = {k: body[k] for k in allowed if k in body}
    upd["updated_at"] = _now()
    upd["updated_by"] = user["id"]

    # Auto-generate peer assignments when opening
    if new_status == "open" and "participant_employee_ids" in upd:
        upd["peer_assignments"] = await _auto_generate_peer_assignments(
            db, upd["participant_employee_ids"]
        )
    elif new_status == "open" and period.get("participant_employee_ids"):
        upd["peer_assignments"] = await _auto_generate_peer_assignments(
            db, period["participant_employee_ids"]
        )

    await db.da_kpi_periods.update_one({"period_id": period_id}, {"$set": upd})
    doc = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    return {"ok": True, "period": _s(doc)}


async def _auto_generate_peer_assignments(db, emp_ids: list) -> list:
    """
    Buat peer assignment: karyawan satu lokasi/departemen saling menilai.
    Returns list of {reviewer_id, evaluatee_id}
    """
    if not emp_ids:
        return []

    emps = await db.rahaza_employees.find(
        {"id": {"$in": emp_ids}},
        {"_id": 0, "id": 1, "location_id": 1, "department": 1}
    ).to_list(500)

    # Group by location_id or department
    groups = {}
    for e in emps:
        key = e.get("location_id") or e.get("department") or "default"
        groups.setdefault(key, []).append(e["id"])

    assignments = []
    for group_key, members in groups.items():
        if len(members) < 2:
            continue
        for reviewer in members:
            for evaluatee in members:
                if reviewer != evaluatee:
                    assignments.append({"reviewer_id": reviewer, "evaluatee_id": evaluatee})

    return assignments


@router.delete("/periods/{period_id}")
async def delete_period(period_id: str, request: Request):
    await _require_hr(request)
    db = get_db()
    period = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not period:
        raise HTTPException(404, "Periode tidak ditemukan.")
    if period.get("status") not in ("draft",):
        raise HTTPException(400, "Hanya periode berstatus 'draft' yang bisa dihapus.")
    await db.da_kpi_periods.delete_one({"period_id": period_id})
    return {"ok": True, "message": "Periode dihapus."}


@router.get("/periods/{period_id}")
async def get_period(period_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.da_kpi_periods.find_one({"period_id": period_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Periode tidak ditemukan.")
    return {"ok": True, "period": _s(doc)}


# ═══════════════════════════════════════════════════════════════════════════════
# QUESTION BANK (HR ADMIN)
# ═══════════════════════════════════════════════════════════════════════════════

