"""Payroll Automation — Phase 3 P1.

Layanan automation di atas payroll engine yang sudah ada (rahaza_payroll.py).

Endpoints:
  GET  /api/payroll/automation/dashboard         — KPI overview: pending/draft/finalized runs
  GET  /api/payroll/automation/schedule          — get current auto-run schedule config
  POST /api/payroll/automation/schedule          — set/update auto-run schedule
  POST /api/payroll/automation/trigger           — manually trigger payroll run for period
  GET  /api/payroll/automation/attendance-sync   — preview attendance-to-payroll mapping
  POST /api/payroll/automation/attendance-sync   — sync attendance days to payroll run
  GET  /api/payroll/automation/alerts            — list payroll alerts (missing profile, overdue)
  GET  /api/payroll/automation/history           — run history with status timeline

Note: Actual payroll computation delegated to existing /api/rahaza/payroll-runs.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from auth import require_auth, serialize_doc
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payroll/automation", tags=["payroll-automation"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# 1. Dashboard KPI
# ---------------------------------------------------------------------------
@router.get("/dashboard")
async def payroll_dashboard(request: Request):
    """Aggregate payroll run status across all periods."""
    await require_auth(request)
    db = get_db()

    # Payroll runs summary
    pipeline_runs = [
        {"$group": {
            "_id": "$status",
            "count": {"$sum": 1},
            "total_net": {"$sum": {"$ifNull": ["$total_net_pay", 0]}},
        }},
    ]
    run_rows = await db.rahaza_payroll_runs.aggregate(pipeline_runs).to_list(20)
    run_summary: dict = {}
    for r in run_rows:
        run_summary[r["_id"] or "unknown"] = {
            "count": r["count"],
            "total_net_rp": r["total_net"],
        }

    # Latest run
    latest_run = await db.rahaza_payroll_runs.find_one(
        {},
        {"_id": 0, "id": 1, "run_number": 1, "period": 1, "status": 1, "total_net_pay": 1,
         "employee_count": 1, "created_at": 1},
        sort=[("created_at", -1)],
    )

    # Employee count with payroll profile
    with_profile = await db.rahaza_payroll_profiles.count_documents({"active": True})
    total_employees = await db.rahaza_employees.count_documents({"active": True})
    without_profile = max(0, total_employees - with_profile)

    # Payslips this month
    this_month = _now().strftime("%Y-%m")
    payslips_this_month = await db.rahaza_payslips.count_documents(
        {"period_from": {"$gte": f"{this_month}-01"}}
    )

    # Schedule config
    schedule = await db.payroll_automation_config.find_one({}, {"_id": 0}) or {}

    # Total disbursed YTD (run yang sudah finalized ATAU paid = sudah dicairkan)
    year_start = f"{_now().year}-01-01"
    ytd_pipeline = [
        {"$match": {"status": {"$in": ["finalized", "paid"]},
                    "period_from": {"$gte": year_start}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$total_net_pay", 0]}}}},
    ]
    ytd_rows = await db.rahaza_payroll_runs.aggregate(ytd_pipeline).to_list(1)
    total_disbursed_ytd = ytd_rows[0]["total"] if ytd_rows else 0

    return {
        "ok": True,
        "run_summary": run_summary,
        "latest_run": serialize_doc(latest_run) if latest_run else None,
        "employee_profile_coverage": {
            "total_active_employees": total_employees,
            "with_payroll_profile": with_profile,
            "without_profile": without_profile,
            "coverage_pct": round(with_profile / max(total_employees, 1) * 100, 1),
        },
        "payslips_this_month": payslips_this_month,
        "total_disbursed_ytd": total_disbursed_ytd,
        "automation_schedule": schedule,
    }


# ---------------------------------------------------------------------------
# 2. Schedule Config
# ---------------------------------------------------------------------------
class ScheduleConfig(BaseModel):
    enabled: bool = False
    run_day_of_month: int = 25       # day to trigger auto-run
    period_offset_months: int = 0    # 0 = current month, -1 = previous month
    auto_finalize: bool = False      # if True, auto-finalize draft run
    notify_hr_email: Optional[str] = None
    notes: str = ""


@router.get("/schedule")
async def get_schedule(request: Request):
    await require_auth(request)
    db = get_db()
    cfg = await db.payroll_automation_config.find_one({}, {"_id": 0})
    return {"ok": True, "data": cfg or {"enabled": False}}


@router.post("/schedule")
async def set_schedule(body: ScheduleConfig, request: Request):
    await require_auth(request)
    db = get_db()
    data = body.model_dump()
    data["updated_at"] = _now().isoformat()
    data["updated_by"] = getattr(request.state, "user", {}).get("email", "")
    await db.payroll_automation_config.replace_one({}, data, upsert=True)
    return {"ok": True, "data": data}


# ---------------------------------------------------------------------------
# 3. Manual Trigger
# ---------------------------------------------------------------------------
class TriggerBody(BaseModel):
    period_from: str          # YYYY-MM-DD
    period_to: str            # YYYY-MM-DD
    notes: str = "Auto-triggered via Payroll Automation"


@router.post("/trigger")
async def trigger_payroll_run(body: TriggerBody, request: Request):
    """Create a payroll run for the given period (delegates to existing engine)."""
    await require_auth(request)
    db = get_db()
    user = getattr(request.state, "user", {})

    # Check if run already exists for this period
    existing = await db.rahaza_payroll_runs.find_one(
        {"period.from": body.period_from, "period.to": body.period_to},
        {"_id": 0, "id": 1, "run_number": 1, "status": 1},
    )
    if existing:
        return {
            "ok": True,
            "status": "already_exists",
            "run": serialize_doc(existing),
            "message": f"Payroll run untuk periode {body.period_from}—{body.period_to} sudah ada.",
        }

    # Collect active employees with payroll profiles
    profiles = await db.rahaza_payroll_profiles.find(
        {"active": True}, {"_id": 0}
    ).to_list(500)
    if not profiles:
        raise HTTPException(422, "Tidak ada profil payroll aktif. Buat profil dulu.")

    # Get run number — RC-5 fix: atomic race-safe numbering (was count_documents()+1)
    now = _now()
    from utils.counters import gen_prefixed_number
    run_number = await gen_prefixed_number(
        db, "rahaza_payroll_runs", "run_number", now.strftime("PAY-%Y%m-"), 3)

    # Create the run document
    run_doc = {
        "id": _uid(),
        "run_number": run_number,
        "period": {"from": body.period_from, "to": body.period_to},
        "status": "draft",
        "notes": body.notes,
        "triggered_by": user.get("email", "automation"),
        "trigger_mode": "manual_automation",
        "employee_count": len(profiles),
        "total_gross_pay": 0,
        "total_net_pay": 0,
        "total_deductions": 0,
        "payslip_ids": [],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    await db.rahaza_payroll_runs.insert_one(run_doc)

    # Log automation event
    await db.payroll_automation_log.insert_one({
        "id": _uid(),
        "run_id": run_doc["id"],
        "run_number": run_number,
        "action": "triggered",
        "period_from": body.period_from,
        "period_to": body.period_to,
        "triggered_by": user.get("email", "automation"),
        "at": now.isoformat(),
    })

    return {
        "ok": True,
        "status": "created",
        "run_id": run_doc["id"],
        "run_number": run_number,
        "employee_count": len(profiles),
        "next_step": f"Buka /api/rahaza/payroll-runs/{run_doc['id']} untuk compute payslips.",
    }


# ---------------------------------------------------------------------------
# 4. Attendance-to-Payroll Sync (preview + apply)
# ---------------------------------------------------------------------------
@router.get("/attendance-sync")
async def preview_attendance_sync(
    request: Request,
    period_from: str = Query(...),
    period_to: str = Query(...),
):
    """Preview which employees have attendance data for the period."""
    await require_auth(request)
    db = get_db()

    # Get active employees
    employees = await db.rahaza_employees.find(
        {"employment_status": "active"},
        {"_id": 0, "id": 1, "name": 1, "department": 1},
    ).to_list(500)

    # Count attendance days per employee
    pipeline = [
        {"$match": {
            "date": {"$gte": period_from, "$lte": period_to},
            "status": {"$in": ["present", "hadir", "H"]},
        }},
        {"$group": {
            "_id": "$employee_id",
            "days_present": {"$sum": 1},
            "days_late": {"$sum": {"$cond": [{"$eq": ["$is_late", True]}, 1, 0]}},
        }},
    ]
    # RC-01: SSOT absensi live = rahaza_attendance_events (rahaza_attendance = seed-only, stale)
    att_rows = await db.rahaza_attendance_events.aggregate(pipeline).to_list(500)
    att_map = {r["_id"]: r for r in att_rows}

    # Build sync preview
    preview = []
    for emp in employees:
        att = att_map.get(emp["id"], {})
        preview.append({
            "employee_id": emp["id"],
            "employee_name": emp["name"],
            "department": emp.get("department", ""),
            "days_present": att.get("days_present", 0),
            "days_late": att.get("days_late", 0),
            "has_profile": await db.rahaza_payroll_profiles.count_documents(
                {"employee_id": emp["id"], "active": True}
            ) > 0,
        })

    present_count = sum(1 for p in preview if p["days_present"] > 0)
    no_profile_count = sum(1 for p in preview if not p["has_profile"])

    return {
        "ok": True,
        "period": {"from": period_from, "to": period_to},
        "summary": {
            "total_employees": len(employees),
            "with_attendance_data": present_count,
            "without_profile": no_profile_count,
        },
        "preview": preview,
    }


class AttendanceSyncBody(BaseModel):
    run_id: str
    period_from: str
    period_to: str


@router.post("/attendance-sync")
async def apply_attendance_sync(body: AttendanceSyncBody, request: Request):
    """Sync attendance data into an existing payroll run (store days_worked per payslip)."""
    await require_auth(request)
    db = get_db()

    run = await db.rahaza_payroll_runs.find_one({"id": body.run_id}, {"_id": 0})
    if not run:
        raise HTTPException(404, f"Payroll run {body.run_id} tidak ditemukan")
    if run.get("status") == "finalized":
        raise HTTPException(409, "Tidak bisa sync attendance ke run yang sudah finalized")

    # Aggregate attendance for period
    pipeline = [
        {"$match": {
            "date": {"$gte": body.period_from, "$lte": body.period_to},
            "status": {"$in": ["present", "hadir", "H"]},
        }},
        {"$group": {
            "_id": "$employee_id",
            "days_present": {"$sum": 1},
            "days_late": {"$sum": {"$cond": [{"$eq": ["$is_late", True]}, 1, 0]}},
            "overtime_hours": {"$sum": {"$ifNull": ["$overtime_hours", 0]}},
        }},
    ]
    # RC-01: SSOT absensi live = rahaza_attendance_events
    att_rows = await db.rahaza_attendance_events.aggregate(pipeline).to_list(500)
    att_map = {r["_id"]: r for r in att_rows}

    # RC-01/K1: sumber lembur nyata = rahaza_overtime_requests (approved) —
    # field overtime_hours di events selalu 0 dari seed; JOIN per employee+periode.
    ot_pipeline = [
        {"$match": {
            "date": {"$gte": body.period_from, "$lte": body.period_to},
            "status": "approved",
        }},
        {"$group": {"_id": "$employee_id", "hours": {"$sum": {"$ifNull": ["$hours", 0]}}}},
    ]
    ot_rows = await db.rahaza_overtime_requests.aggregate(ot_pipeline).to_list(500)
    ot_map = {r["_id"]: float(r.get("hours") or 0) for r in ot_rows}

    # Update payslips in this run
    updated = 0
    async for payslip in db.rahaza_payslips.find({"run_id": body.run_id}, {"_id": 0, "id": 1, "employee_id": 1}):
        emp_id = payslip.get("employee_id")
        att = att_map.get(emp_id, {})
        ot_hours = ot_map.get(emp_id) or float(att.get("overtime_hours", 0) or 0)
        await db.rahaza_payslips.update_one(
            {"id": payslip["id"]},
            {"$set": {
                "days_worked": att.get("days_present", 0),
                "days_late": att.get("days_late", 0),
                "overtime_hours_synced": ot_hours,
                "attendance_synced_at": _now().isoformat(),
            }},
        )
        updated += 1

    return {
        "ok": True,
        "run_id": body.run_id,
        "payslips_updated": updated,
        "attendance_records_used": len(att_map),
        "message": f"{updated} payslip diupdate dengan data attendance.",
    }


# ---------------------------------------------------------------------------
# 5. Payroll Alerts
# ---------------------------------------------------------------------------
@router.get("/alerts")
async def payroll_alerts(request: Request):
    await require_auth(request)
    db = get_db()
    alerts = []

    # Alert 1: employees without payroll profile
    total_active = await db.rahaza_employees.count_documents({"employment_status": "active"})
    with_profile = await db.rahaza_payroll_profiles.count_documents({"active": True})
    without = max(0, total_active - with_profile)
    if without > 0:
        alerts.append({
            "type": "missing_profile",
            "severity": "warning",
            "message": f"{without} karyawan aktif belum punya profil payroll.",
            "count": without,
            "action": "Buat profil payroll untuk karyawan tersebut.",
        })

    # Alert 2: draft runs older than 3 days
    three_days_ago = (_now() - timedelta(days=3)).isoformat()
    stale_drafts = await db.rahaza_payroll_runs.count_documents(
        {"status": "draft", "created_at": {"$lte": three_days_ago}}
    )
    if stale_drafts > 0:
        alerts.append({
            "type": "stale_draft",
            "severity": "warning",
            "message": f"{stale_drafts} payroll run masih draft >3 hari.",
            "count": stale_drafts,
            "action": "Finalize atau hapus draft yang tidak diperlukan.",
        })

    # Alert 3: current month not yet started
    current_month = _now().strftime("%Y-%m")
    this_month_run = await db.rahaza_payroll_runs.find_one(
        {"period.from": {"$gte": f"{current_month}-01"}},
        {"_id": 0, "id": 1},
    )
    today = date.today()
    if not this_month_run and today.day >= 20:
        alerts.append({
            "type": "no_run_this_month",
            "severity": "info",
            "message": f"Belum ada payroll run untuk {current_month}. Tanggal sudah {today.day}.",
            "count": 0,
            "action": "Buat atau trigger payroll run bulan ini.",
        })

    return {"ok": True, "data": alerts, "total": len(alerts)}


# ---------------------------------------------------------------------------
# 6. History (last N runs with timeline)
# ---------------------------------------------------------------------------
@router.get("/history")
async def run_history(
    request: Request,
    limit: int = Query(12, ge=1, le=36),
):
    await require_auth(request)
    db = get_db()
    runs = await db.rahaza_payroll_runs.find(
        {},
        {"_id": 0, "id": 1, "run_number": 1, "period": 1, "status": 1,
         "employee_count": 1, "total_net_pay": 1, "created_at": 1, "finalized_at": 1},
    ).sort("created_at", -1).limit(limit).to_list(limit)

    # Enrich with automation log entries
    run_ids = [r["id"] for r in runs]
    logs = await db.payroll_automation_log.find(
        {"run_id": {"$in": run_ids}},
        {"_id": 0},
    ).to_list(200)
    log_map: dict[str, list] = {}
    for lg in logs:
        log_map.setdefault(lg["run_id"], []).append(lg)

    return {
        "ok": True,
        "data": [
            {
                **serialize_doc(r),
                "automation_events": log_map.get(r["id"], []),
            }
            for r in runs
        ],
    }
