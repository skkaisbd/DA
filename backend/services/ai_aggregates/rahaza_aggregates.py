"""Rahaza ERP aggregates for AI endpoints (WIP/QC/downtime/alerts).

Replaces .find().to_list(500) patterns with $group pipelines.
"""
from __future__ import annotations

from datetime import date, datetime, timezone


async def daily_wip_output(db, *, d_start: str, d_end: str) -> int:
    """Sum of WIP output qty for a single day."""
    pipeline = [
        {"$match": {
            "event_type": "output",
            "created_at": {"$gte": d_start, "$lte": d_end},
        }},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$qty", 0]}}}},
    ]
    rows = await db.rahaza_wip_events.aggregate(pipeline).to_list(1)
    return int(rows[0]["total"]) if rows else 0


async def daily_qc_summary(db, *, d_start: str, d_end: str) -> dict:
    pipeline = [
        {"$match": {"created_at": {"$gte": d_start, "$lte": d_end}}},
        {"$group": {
            "_id": None,
            "checked": {"$sum": {"$ifNull": ["$checked_qty", 0]}},
            "fail": {"$sum": {"$ifNull": ["$fail_qty", 0]}},
        }},
    ]
    rows = await db.rahaza_qc_events.aggregate(pipeline).to_list(1)
    if not rows:
        return {"checked": 0, "fail": 0}
    r = rows[0]
    return {"checked": int(r.get("checked") or 0), "fail": int(r.get("fail") or 0)}


async def daily_target_qty(db, *, assign_date: str) -> int:
    pipeline = [
        {"$match": {"assign_date": assign_date}},
        {"$group": {"_id": None, "target": {"$sum": {"$ifNull": ["$target_qty", 0]}}}},
    ]
    rows = await db.rahaza_line_assignments.aggregate(pipeline).to_list(1)
    return int(rows[0]["target"]) if rows else 0


async def daily_downtime(db, *, d_start: str, d_end: str) -> int:
    pipeline = [
        {"$match": {"start_at": {"$gte": d_start, "$lte": d_end}}},
        {"$group": {"_id": None, "total": {"$sum": {"$ifNull": ["$duration_min", 0]}}}},
    ]
    rows = await db.rahaza_machine_downtime.aggregate(pipeline).to_list(1)
    return int(rows[0]["total"]) if rows else 0


async def active_alerts(db, *, limit: int = 5) -> list[dict]:
    return await db.rahaza_alerts.find(
        {"status": {"$in": ["active", "open", "triggered"]}},
        {"_id": 0, "id": 1, "message": 1, "severity": 1, "category": 1},
    ).limit(limit).to_list(limit)


async def wo_backlog(db) -> dict:
    """Counts for active and overdue WOs."""
    today = date.today().isoformat()
    active = await db.rahaza_work_orders.count_documents(
        {"status": {"$in": ["released", "in_progress"]}}
    )
    overdue = await db.rahaza_work_orders.count_documents({
        "status": {"$nin": ["completed", "cancelled"]},
        "due_date": {"$lt": today},
    })
    return {"active": active, "overdue": overdue}


async def weekly_qc_downtime(db, *, from_iso: str, to_iso: str) -> dict:
    """For root-cause: 7-day QC + downtime + alerts (counts only + small samples)."""
    qc = await daily_qc_summary(db, d_start=from_iso, d_end=to_iso + "T23:59:59Z")
    dt = await daily_downtime(db, d_start=from_iso, d_end=to_iso + "T23:59:59Z")
    downtime_events = await db.rahaza_machine_downtime.count_documents({
        "start_at": {"$gte": from_iso, "$lte": to_iso + "T23:59:59Z"}
    })
    qc_events = await db.rahaza_qc_events.count_documents({
        "created_at": {"$gte": from_iso, "$lte": to_iso + "T23:59:59Z"}
    })
    alerts = await active_alerts(db, limit=10)
    return {
        "qc_checked": qc["checked"],
        "qc_fail": qc["fail"],
        "downtime_minutes": dt,
        "downtime_event_count": downtime_events,
        "qc_event_count": qc_events,
        "alerts_active": len(alerts),
        "alert_messages": [a.get("message", "") for a in alerts[:3]],
    }


async def smart_search(db, *, query: str, today_iso: str | None = None, limit: int = 20) -> list[dict]:
    """DB-level smart search across WOs/orders/employees.

    Avoids the previous pattern of `.find({}).to_list(500)` then filtering in Python.
    """
    q = (query or "").strip()
    today_iso = today_iso or date.today().isoformat()
    results: list[dict] = []
    if not q:
        return results

    q_lower = q.lower()
    escaped = q.replace("\\", "\\\\").replace(".", "\\.")
    regex = {"$regex": escaped, "$options": "i"}

    # Work orders: OR over wo_number + intent keywords
    wo_filter = {"$or": [{"wo_number": regex}]}
    if "overdue" in q_lower or "terlambat" in q_lower:
        wo_filter["$or"].append({
            "due_date": {"$lt": today_iso},
            "status": {"$nin": ["completed", "cancelled"]},
        })
    if "aktif" in q_lower:
        wo_filter["$or"].append({"status": {"$in": ["in_progress", "released"]}})
    if "selesai" in q_lower:
        wo_filter["$or"].append({"status": "completed"})
    if "draft" in q_lower:
        wo_filter["$or"].append({"status": "draft"})
    wos = await db.rahaza_work_orders.find(
        wo_filter, {"_id": 0, "id": 1, "wo_number": 1, "status": 1}
    ).limit(limit).to_list(limit)
    for wo in wos:
        results.append({
            "type": "work_order", "id": wo.get("id"),
            "label": wo.get("wo_number") or wo.get("id"),
            "status": wo.get("status"),
        })
        if len(results) >= limit:
            return results[:limit]

    # Orders
    orders = await db.rahaza_orders.find(
        {"$or": [{"order_number": regex}, {"customer_name": regex}]},
        {"_id": 0, "id": 1, "order_number": 1, "customer_name": 1},
    ).limit(limit).to_list(limit)
    for o in orders:
        results.append({
            "type": "order", "id": o.get("id"),
            "label": o.get("order_number") or o.get("id"),
            "customer": o.get("customer_name"),
        })
        if len(results) >= limit:
            return results[:limit]

    # Employees (active only)
    emps = await db.rahaza_employees.find(
        {"active": True, "$or": [{"name": regex}, {"employee_code": regex}]},
        {"_id": 0, "id": 1, "name": 1, "employee_code": 1},
    ).limit(limit).to_list(limit)
    for e in emps:
        results.append({
            "type": "employee", "id": e.get("id"),
            "label": e.get("name") or "",
            "code": e.get("employee_code"),
        })
        if len(results) >= limit:
            return results[:limit]

    return results[:limit]


async def daily_wip_avg(db, *, since_iso: str) -> float:
    """Average daily output qty over a recent window (for predictive-delay)."""
    pipeline = [
        {"$match": {"event_type": "output", "created_at": {"$gte": since_iso}}},
        {"$project": {
            "_id": 0,
            "day": {"$substr": ["$created_at", 0, 10]},
            "qty": {"$toDouble": {"$ifNull": ["$qty", 0]}},
        }},
        {"$group": {"_id": "$day", "sum": {"$sum": "$qty"}}},
        {"$group": {"_id": None, "avg": {"$avg": "$sum"}}},
    ]
    rows = await db.rahaza_wip_events.aggregate(pipeline).to_list(1)
    if not rows or not rows[0].get("avg"):
        return 30.0  # fallback heuristic preserved from original logic
    return max(1.0, float(rows[0]["avg"]))


async def list_predictive_targets(db, *, wo_id: str | None) -> list[dict]:
    """Fetch WOs for predictive-delay (single or many)."""
    if wo_id:
        return await db.rahaza_work_orders.find(
            {"id": wo_id},
            {"_id": 0, "id": 1, "wo_number": 1, "due_date": 1, "qty": 1, "qty_produced": 1},
        ).to_list(1)
    return await db.rahaza_work_orders.find(
        {"status": {"$in": ["released", "in_progress"]}},
        {"_id": 0, "id": 1, "wo_number": 1, "due_date": 1, "qty": 1, "qty_produced": 1},
    ).sort("due_date", 1).limit(50).to_list(50)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
