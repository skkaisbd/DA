"""Capacity Planning Lite — Phase 2 P0.

Rule-based capacity check on WO release + factory-level resource overview.

Endpoints:
  GET  /api/capacity/overview           — factory capacity snapshot
  POST /api/capacity/check-wo           — check if new WO fits in capacity
  GET  /api/capacity/utilization        — utilization trend (last 7 days)
  GET  /api/capacity/bottlenecks        — current bottleneck stations
  POST /api/capacity/simulate           — simulate adding WO to schedule
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from auth import require_auth
from database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/capacity", tags=["capacity-planning"])

DEFAULT_CONFIG = {
    "daily_capacity_pcs": 1000,
    "overload_threshold": 0.90,
    "critical_threshold": 1.10,
    "lead_time_buffer_days": 2,
    "working_hours_per_day": 8,
    "shifts_per_day": 1,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _get_config(db) -> dict:
    cfg = await db.capacity_config.find_one({}, {"_id": 0})
    if not cfg:
        return DEFAULT_CONFIG.copy()
    merged = DEFAULT_CONFIG.copy()
    merged.update({k: v for k, v in cfg.items() if k in DEFAULT_CONFIG})
    return merged


async def _active_wo_load(db) -> dict:
    today = date.today().isoformat()
    # RC-17: SSOT WO = rahaza_work_orders (production_work_orders = phantom/MISSING).
    # Peta field: quantity→qty, qty_completed→completed_qty, order_code→wo_number,
    # product_name→model_name, target_date→target_date||due_date; status rahaza:
    # in_progress/planned/released (bukan pending/not_started).
    pipeline = [
        {"$match": {"status": {"$in": ["in_progress", "planned", "released", "pending", "not_started"]}}},
        {"$project": {
            "_id": 0, "id": 1,
            "order_code": {"$ifNull": ["$wo_number", ""]},
            "product_name": {"$ifNull": ["$model_name", ""]},
            "quantity": {"$ifNull": ["$qty", 0]},
            "qty_completed": {"$ifNull": ["$completed_qty", 0]},
            "target_date": {"$ifNull": ["$target_date", "$due_date"]},
            "priority": 1, "status": 1,
        }},
        {"$limit": 200},
    ]
    wos = await db.rahaza_work_orders.aggregate(pipeline).to_list(200)
    overdue_count = 0
    at_risk_count = 0
    total_remaining = 0
    for wo in wos:
        remaining = max(0, int(wo.get("quantity") or 0) - int(wo.get("qty_completed") or 0))
        total_remaining += remaining
        due = str(wo.get("target_date") or "")
        if due and due[:10] < today:
            overdue_count += 1
        elif due and due[:10] <= (date.today() + timedelta(days=3)).isoformat():
            at_risk_count += 1
    return {
        "active_count": len(wos),
        "total_remaining_pcs": total_remaining,
        "overdue_count": overdue_count,
        "at_risk_count": at_risk_count,
        "wo_sample": [
            {
                "id": w["id"],
                "code": w.get("order_code", ""),
                "product": (w.get("product_name") or "")[:30],
                "remaining": max(0, int(w.get("quantity") or 0) - int(w.get("qty_completed") or 0)),
                "due": str(w.get("target_date", "")),
                "priority": w.get("priority", "normal"),
            }
            for w in wos[:10]
        ],
    }


async def _employee_headcount(db) -> int:
    return await db.rahaza_employees.count_documents({
        "employment_status": "active",
        "department": {"$in": ["Produksi", "Production", "Jahit", "Rajut", "Packing"]},
    })


async def _recent_daily_output(db, days: int = 7) -> list:
    # RC-17: rahaza_wip_events TIDAK punya field created_at — pakai event_date (string "YYYY-MM-DD")
    since = (date.today() - timedelta(days=days)).isoformat()
    pipeline = [
        {"$match": {"event_type": "output", "event_date": {"$gte": since}}},
        {"$project": {
            "_id": 0,
            "day": "$event_date",
            "qty": {"$toDouble": {"$ifNull": ["$qty", 0]}},
        }},
        {"$group": {"_id": "$day", "output_pcs": {"$sum": "$qty"}}},
        {"$sort": {"_id": 1}},
    ]
    rows = await db.rahaza_wip_events.aggregate(pipeline).to_list(days + 2)
    return [{"date": r["_id"], "output_pcs": int(r["output_pcs"])} for r in rows]


async def _downtime_today(db) -> int:
    today = date.today().isoformat()
    pipeline = [
        {"$match": {"start_at": {"$gte": today}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$duration_min", 0]}}}},
    ]
    rows = await db.rahaza_machine_downtime.aggregate(pipeline).to_list(1)
    return int(rows[0]["total"]) if rows else 0


def _compute_utilization(remaining_pcs: int, daily_capacity: int) -> dict:
    days_needed = (remaining_pcs + daily_capacity - 1) // daily_capacity if daily_capacity > 0 else 999
    util_ratio = remaining_pcs / max(daily_capacity, 1)
    if util_ratio >= 1.10:
        status = "critical"
        color = "red"
    elif util_ratio >= 0.90:
        status = "warning"
        color = "yellow"
    else:
        status = "normal"
        color = "green"
    return {
        "utilization_ratio": round(util_ratio, 3),
        "utilization_pct": round(util_ratio * 100, 1),
        "days_to_clear": days_needed,
        "status": status,
        "color": color,
    }


@router.get("/overview")
async def capacity_overview(request: Request):
    await require_auth(request)
    db = get_db()
    cfg = await _get_config(db)
    load = await _active_wo_load(db)
    headcount = await _employee_headcount(db)
    daily_output = await _recent_daily_output(db, days=7)
    dt_today = await _downtime_today(db)
    if daily_output:
        avg_output = sum(d["output_pcs"] for d in daily_output) / len(daily_output)
    else:
        avg_output = float(cfg["daily_capacity_pcs"])
    util = _compute_utilization(load["total_remaining_pcs"], int(avg_output) or cfg["daily_capacity_pcs"])
    return {
        "ok": True,
        "snapshot_at": _now().isoformat(),
        "config": cfg,
        "load": load,
        "utilization": util,
        "headcount_production": headcount,
        "downtime_today_min": dt_today,
        "avg_daily_output_pcs": round(avg_output, 1),
        "daily_output_trend": daily_output,
    }


class WOCheckRequest(BaseModel):
    quantity: int = Field(ge=0)
    target_days: int = 7
    priority: str = "normal"


@router.post("/check-wo")
async def check_wo_capacity(body: WOCheckRequest, request: Request):
    await require_auth(request)
    db = get_db()
    cfg = await _get_config(db)
    load = await _active_wo_load(db)
    daily_output = await _recent_daily_output(db, days=7)
    avg_output = (
        sum(d["output_pcs"] for d in daily_output) / len(daily_output)
        if daily_output else float(cfg["daily_capacity_pcs"])
    )
    effective_daily = max(1, int(avg_output))
    current_remaining = load["total_remaining_pcs"]
    new_total = current_remaining + body.quantity
    current_util = _compute_utilization(current_remaining, effective_daily)
    new_util = _compute_utilization(new_total, effective_daily)
    days_needed = (body.quantity + effective_daily - 1) // effective_daily
    buffer = cfg["lead_time_buffer_days"]
    if body.priority == "urgent":
        buffer = 0
    elif body.priority == "high":
        buffer = 1
    feasible = days_needed <= (body.target_days - buffer)
    recommended_start = date.today()
    if not feasible:
        excess = days_needed - body.target_days
        recommended_start = date.today() + timedelta(days=max(0, excess))
    warnings = []
    if new_util["status"] == "critical":
        warnings.append(f"Kapasitas akan over {round((new_util['utilization_ratio'] - 1) * 100, 0):.0f}% setelah WO ini.")
    if load["overdue_count"] > 0:
        warnings.append(f"{load['overdue_count']} WO sudah overdue.")
    if not feasible:
        warnings.append(f"WO butuh ~{days_needed} hari; target {body.target_days} hari tidak cukup.")
    return {
        "ok": True,
        "feasible": feasible,
        "quantity": body.quantity,
        "target_days": body.target_days,
        "effective_daily_capacity": effective_daily,
        "days_needed": days_needed,
        "recommended_start_date": recommended_start.isoformat(),
        "current_utilization": current_util,
        "projected_utilization": new_util,
        "warnings": warnings,
    }


@router.get("/utilization")
async def utilization_trend(
    request: Request,
    days: int = Query(7, ge=1, le=30),
):
    await require_auth(request)
    db = get_db()
    cfg = await _get_config(db)
    daily_output = await _recent_daily_output(db, days=days)
    cap = cfg["daily_capacity_pcs"]
    return {
        "ok": True,
        "days": days,
        "configured_capacity_pcs": cap,
        "data": [
            {
                "date": d["date"],
                "output_pcs": d["output_pcs"],
                "utilization_pct": round(d["output_pcs"] / cap * 100, 1),
                "status": "critical" if d["output_pcs"] >= cap * 1.1 else (
                    "warning" if d["output_pcs"] >= cap * 0.9 else "normal"
                ),
            }
            for d in daily_output
        ],
    }


@router.get("/bottlenecks")
async def get_bottlenecks(request: Request):
    await require_auth(request)
    db = get_db()
    since = (_now() - timedelta(days=7)).isoformat()
    pipeline = [
        {"$match": {"start_at": {"$gte": since}}},
        {"$project": {
            "_id": 0,
            "machine_id": {"$ifNull": ["$machine_id", "Unknown"]},
            "machine_name": {"$ifNull": ["$machine_name", "Unknown"]},
            "duration_min": {"$ifNull": ["$duration_min", 0]},
        }},
        {"$group": {
            "_id": {"machine_id": "$machine_id", "machine_name": "$machine_name"},
            "total_downtime_min": {"$sum": "$duration_min"},
            "event_count": {"$sum": 1},
        }},
        {"$sort": {"total_downtime_min": -1}},
        {"$limit": 10},
    ]
    rows = await db.rahaza_machine_downtime.aggregate(pipeline).to_list(10)
    return {
        "ok": True,
        "data": [
            {
                "machine_id": r["_id"]["machine_id"],
                "machine_name": r["_id"]["machine_name"],
                "total_downtime_min": r["total_downtime_min"],
                "event_count": r["event_count"],
                "severity": "high" if r["total_downtime_min"] > 120 else (
                    "medium" if r["total_downtime_min"] > 60 else "low"
                ),
            }
            for r in rows
        ],
        "period_days": 7,
    }


class SimulateRequest(BaseModel):
    quantity: int = Field(ge=0)
    product_name: str = ""
    start_date: Optional[str] = None
    priority: str = "normal"


@router.post("/simulate")
async def simulate_wo_schedule(body: SimulateRequest, request: Request):
    await require_auth(request)
    db = get_db()
    cfg = await _get_config(db)
    daily_output = await _recent_daily_output(db, days=14)
    avg = (
        sum(d["output_pcs"] for d in daily_output) / len(daily_output)
        if daily_output else float(cfg["daily_capacity_pcs"])
    )
    effective_daily = max(1, int(avg))
    load = await _active_wo_load(db)
    start = date.fromisoformat(body.start_date) if body.start_date else date.today()
    days_needed = (body.quantity + effective_daily - 1) // effective_daily
    est_completion = start + timedelta(days=days_needed + cfg["lead_time_buffer_days"])
    return {
        "ok": True,
        "product_name": body.product_name,
        "quantity": body.quantity,
        "start_date": start.isoformat(),
        "estimated_completion": est_completion.isoformat(),
        "days_needed": days_needed,
        "buffer_days": cfg["lead_time_buffer_days"],
        "effective_daily_capacity": effective_daily,
        "current_backlog_pcs": load["total_remaining_pcs"],
        "note": (
            f"Berdasarkan rata-rata output {effective_daily} pcs/hari (14 hari terakhir). "
            f"Backlog saat ini {load['total_remaining_pcs']} pcs."
        ),
    }
