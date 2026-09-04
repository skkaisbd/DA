"""
Session 13 — P1-12: Audit Log Permission Changes
Extension dari rahaza_audit.py:
- Endpoint dedicated untuk audit perubahan role/permission user
- Filter: user, role, date range
- Log otomatis saat admin ubah role user

P1-13: Weekly Digest Internal
- GET /api/management/weekly-digest — Aggregated KPIs for past 7 days
- POST /api/management/weekly-digest/generate — Trigger manual generation
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/management", tags=["management-tools"])


def _now():
    return datetime.now(timezone.utc)


def ok(data=None, meta=None):
    r = {"success": True}
    if data is not None:
        r["data"] = data
    if meta is not None:
        r["metadata"] = meta
    return r


def serialize(o):
    if isinstance(o, list):
        return [serialize(i) for i in o]
    if isinstance(o, dict):
        return {k: serialize(v) for k, v in o.items() if k != "_id"}
    if isinstance(o, datetime):
        return o.isoformat()
    return o


# ═══════════════════════════════════════════════════════════════════════════
#  P1-12: AUDIT LOG PERMISSION CHANGES
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/audit/permissions")
async def get_permission_audit_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=200),
    user_id: Optional[str] = None,
    role: Optional[str] = None,
    days: int = Query(30),
):
    """
    P1-12: Audit log khusus perubahan permission/role.
    Sources:
    - rahaza_audit_logs: entity_type='user', field diff contains 'role'
    - Direct changes via rahaza_users collection
    """
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)

    # Query audit logs for role changes
    query = {
        "timestamp": {"$gte": since.isoformat()},
        "$or": [
            {"entity_type": "user", "action": {"$in": ["role_change", "permission_change", "update"]}},
            {"action": "role_change"},
            {"action": "permission_change"},
        ]
    }
    if user_id:
        query["entity_id"] = user_id

    logs = await db.rahaza_audit_logs.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(length=limit)

    # Filter only logs that have role/permission in diff
    perm_logs = []
    for log in logs:
        diff = log.get("diff", {})
        if "role" in diff or "permissions" in diff or log.get("action") in ("role_change", "permission_change"):
            perm_logs.append(log)

    # Also get recent user updates from users collection (direct role info)
    # RC-07: SSOT users (rahaza_users = phantom)
    users = await db.users.find({}, {"_id": 0, "password": 0}).sort("updated_at", -1).limit(100).to_list(100)

    # Create synthetic audit view for current role state
    current_roles = [{
        "user_id": u.get("id"),
        "email": u.get("email"),
        "name": u.get("name"),
        "role": u.get("role"),
        "portal_access": u.get("portal_access", []),
        "updated_at": u.get("updated_at"),
        "is_active": u.get("is_active", True),
    } for u in users if role is None or u.get("role") == role]

    return ok(
        data={
            "permission_changes": serialize(perm_logs),
            "current_roles": current_roles[:50],
        },
        meta={
            "permission_change_count": len(perm_logs),
            "total_users": len(current_roles),
            "period_days": days,
        }
    )


# ═══════════════════════════════════════════════════════════════════════════
#  P1-13: WEEKLY DIGEST INTERNAL
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/weekly-digest")
async def get_weekly_digest(
    request: Request,
    days: int = Query(7, description="Periode digest (default 7 hari)"),
):
    """
    P1-13: Weekly Digest Internal.
    Summarizes key metrics for the past N days:
    - Orders & Production
    - Finance (invoicing)
    - HR events
    - Marketing KPIs
    - Alerts
    """
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)
    since_str = since.isoformat()

    # --- Production: Work Orders --- (RC-07: SSOT rahaza_work_orders)
    total_wo = await db.rahaza_work_orders.count_documents({
        "created_at": {"$gte": since_str}
    })
    completed_wo = await db.rahaza_work_orders.count_documents({
        "status": "completed",
        "updated_at": {"$gte": since_str}
    })

    # --- Finance: Invoices --- (RC-07: SSOT rahaza_ar_invoices, field issue_date)
    invoices = await db.rahaza_ar_invoices.find(
        {"issue_date": {"$gte": since.strftime("%Y-%m-%d")}}, {"_id": 0, "total": 1, "status": 1}
    ).to_list(length=500)
    total_invoiced = sum(float(i.get("total", 0)) for i in invoices)
    paid_invoices = sum(1 for i in invoices if i.get("status") == "paid")

    # --- Maklon: Orders (P1.B: SSOT dewi_maklon_pos) ---
    maklon_orders = await db.dewi_maklon_pos.count_documents({
        "po_date": {"$gte": since_str}
    })
    maklon_completed = await db.dewi_maklon_pos.count_documents({
        "status": {"$in": ["completed", "invoiced"]},
        "updated_at": {"$gte": since_str}
    })

    # --- HR: Leave Requests ---
    leave_req = await db.rahaza_leave_requests.count_documents({
        "created_at": {"$gte": since_str}
    })

    # --- HR: Attendance Issues --- (RC-01/RC-07: SSOT rahaza_attendance_events;
    # status nyata hanya hadir/izin/sakit — 'late'/'absent' tidak pernah ada)
    attendance_issues = await db.rahaza_attendance_events.count_documents({
        "date": {"$gte": since.strftime("%Y-%m-%d")},
        "status": {"$in": ["izin", "sakit"]}
    })

    # --- Inventory: Low stock alerts ---
    low_stock_count = await db.rahaza_materials.count_documents({
        "active": True,
        "$expr": {"$lt": ["$total_qty", "$min_stock"]}
    })

    # --- Marketing: Live sessions revenue --- (RC-07: field SSOT gmv/total_orders;
    # session_date bertipe STRING "YYYY-MM-DD")
    sessions = await db.marketing_live_sessions.find(
        {"session_date": {"$gte": since.strftime("%Y-%m-%d")}},
        {"_id": 0, "gmv": 1, "total_orders": 1}
    ).to_list(length=200)
    live_revenue = sum(float(s.get("gmv", 0) or 0) for s in sessions)
    live_orders = sum(int(s.get("total_orders", 0) or 0) for s in sessions)

    # --- Warehouse Occupancy Alerts --- (RC-07: rahaza_racks = phantom; SSOT wh_racks
    # TIDAK punya field okupansi → metrik di-drop jujur, jangan mengarang angka)
    high_occupancy_racks = []

    digest = {
        "period_days": days,
        "generated_at": _now().isoformat(),
        "production": {
            "new_work_orders": total_wo,
            "completed_work_orders": completed_wo,
        },
        "finance": {
            "new_invoices": len(invoices),
            "paid_invoices": paid_invoices,
            "total_invoiced": total_invoiced,
        },
        "maklon": {
            "new_orders": maklon_orders,
            "completed_orders": maklon_completed,
        },
        "hr": {
            "leave_requests": leave_req,
            "attendance_issues": attendance_issues,
        },
        "marketing": {
            "live_sessions": len(sessions),
            "live_revenue": live_revenue,
            "live_orders": live_orders,
        },
        "alerts": {
            "low_stock_materials": low_stock_count,
            "high_occupancy_racks": len(high_occupancy_racks),
            "high_occupancy_rack_codes": high_occupancy_racks[:5],
        },
    }

    # Determine digest health
    alert_count = low_stock_count + len(high_occupancy_racks)
    digest["health"] = "good" if alert_count == 0 else ("warning" if alert_count <= 3 else "critical")
    digest["alert_count"] = alert_count

    return ok(data=digest)
