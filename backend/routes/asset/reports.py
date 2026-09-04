"""/api/assets/reports/utilization (+ CSV export).

LITERAL paths under /reports/* — must register before /{asset_id} catch-all.
"""
from datetime import date
from typing import Optional
from dateutil.relativedelta import relativedelta
from fastapi import Request, HTTPException, Query, Response

from database import get_db
from auth import require_auth
from ._helpers import (
    router,
    _parse_date_yyyymmdd, _days_between, _intersect_days,
)


@router.get("/reports/utilization")
async def asset_utilization_report(
    request: Request,
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (default: 90 days ago)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)"),
    category_id: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    underutilized_threshold: int = Query(30, ge=0, le=100,
                                          description="Asset is underutilized if utilization% < this"),
    limit: int = Query(100, ge=1, le=500, description="Max assets returned in detailed list"),
):
    """
    Asset Utilization Report.
    utilization% = (sum of assigned days within window / window days) × 100
    """
    await require_auth(request)
    db = get_db()

    today = date.today()
    win_start = _parse_date_yyyymmdd(date_from, today - relativedelta(days=90))
    win_end = _parse_date_yyyymmdd(date_to, today)
    if win_end < win_start:
        raise HTTPException(400, "date_to harus >= date_from")
    win_days = _days_between(win_start, win_end)

    asset_filter: dict = {"status": {"$ne": "disposed"}}
    if category_id:
        asset_filter["category_id"] = category_id
    assets = await db.dewi_assets.find(
        asset_filter,
        {
            "_id": 0,
            "id": 1, "name": 1, "asset_number": 1, "category_id": 1, "category_name": 1,
            "status": 1, "purchase_cost": 1, "purchase_date": 1,
            "assigned_to_id": 1, "assigned_to_name": 1,
        },
    ).to_list(5000)

    asset_ids = [a["id"] for a in assets]
    if not asset_ids:
        return {
            "window": {"date_from": win_start.isoformat(), "date_to": win_end.isoformat(), "days": win_days},
            "summary": {
                "total_assets": 0, "assets_in_use_today": 0,
                "avg_utilization_pct": 0, "fully_utilized_count": 0,
                "underutilized_count": 0, "idle_in_window_count": 0,
                "total_purchase_cost": 0, "underutilized_value_at_risk": 0,
            },
            "by_category": [], "by_assignee": [],
            "top_utilized": [], "underutilized": [], "idle_assets": [],
            "status_breakdown": {"active": 0, "in_maintenance": 0, "disposed": 0},
        }

    assn_filter: dict = {
        "asset_id": {"$in": asset_ids},
        "$or": [
            {"returned_date": None},
            {"returned_date": {"$gte": win_start.isoformat()}},
        ],
        "assigned_date": {"$lte": win_end.isoformat()},
    }
    if assignee_id:
        assn_filter["assigned_to_id"] = assignee_id

    assignments = await db.dewi_asset_assignments.find(
        assn_filter, {"_id": 0}
    ).to_list(20000)

    asset_util: dict = {}
    for a in assets:
        asset_util[a["id"]] = {
            "asset": a,
            "assigned_days": 0,
            "assignment_count": 0,
            "current_assignee": a.get("assigned_to_name") or None,
            "current_assignee_id": a.get("assigned_to_id") or None,
            "last_assigned_date": None,
            "last_returned_date": None,
        }

    for ass in assignments:
        aid = ass.get("asset_id")
        if aid not in asset_util:
            continue
        a_start = _parse_date_yyyymmdd(ass.get("assigned_date"), win_start)
        a_end_str = ass.get("returned_date")
        a_end = _parse_date_yyyymmdd(a_end_str, today) if a_end_str else today
        overlap = _intersect_days(a_start, a_end, win_start, win_end)
        bucket = asset_util[aid]
        bucket["assigned_days"] += overlap
        bucket["assignment_count"] += 1
        if not bucket["last_assigned_date"] or ass.get("assigned_date", "") > bucket["last_assigned_date"]:
            bucket["last_assigned_date"] = ass.get("assigned_date")
        if a_end_str and (not bucket["last_returned_date"] or a_end_str > bucket["last_returned_date"]):
            bucket["last_returned_date"] = a_end_str

    enriched, full_count, under_count, idle_count = [], 0, 0, 0
    total_util_sum, in_use_today, total_value_at_risk = 0.0, 0, 0.0

    for aid, b in asset_util.items():
        purchase_date = _parse_date_yyyymmdd(b["asset"].get("purchase_date"), win_start)
        effective_start = max(win_start, purchase_date)
        effective_days = _days_between(effective_start, win_end)
        if effective_days <= 0:
            util_pct = 0.0
        else:
            asgn_days = min(b["assigned_days"], effective_days)
            util_pct = round(asgn_days / effective_days * 100, 1)

        b["utilization_pct"] = util_pct
        b["effective_window_days"] = effective_days
        b["asset_id"] = aid
        b["asset_name"] = b["asset"].get("name")
        b["asset_number"] = b["asset"].get("asset_number")
        b["category_id"] = b["asset"].get("category_id")
        b["category_name"] = b["asset"].get("category_name")
        b["purchase_cost"] = b["asset"].get("purchase_cost") or 0
        b["status"] = b["asset"].get("status")

        total_util_sum += util_pct
        if util_pct >= 95:
            full_count += 1
        if util_pct < underutilized_threshold:
            under_count += 1
            total_value_at_risk += b["purchase_cost"]
        if b["assigned_days"] == 0:
            idle_count += 1
        if b["current_assignee_id"]:
            in_use_today += 1

        b.pop("asset", None)
        enriched.append(b)

    total_assets = len(enriched)
    avg_util = round(total_util_sum / total_assets, 1) if total_assets else 0.0

    enriched_desc = sorted(enriched, key=lambda x: x["utilization_pct"], reverse=True)
    enriched_asc = sorted(enriched, key=lambda x: x["utilization_pct"])
    top_utilized = enriched_desc[:limit]
    underutilized = [e for e in enriched_asc if e["utilization_pct"] < underutilized_threshold][:limit]
    idle_assets = [e for e in enriched if e["assigned_days"] == 0][:limit]

    cat_map: dict = {}
    for e in enriched:
        cid = e["category_id"] or "_uncategorized_"
        cname = e["category_name"] or "Uncategorized"
        if cid not in cat_map:
            cat_map[cid] = {
                "category_id": cid, "category_name": cname,
                "asset_count": 0, "total_utilization_sum": 0.0,
                "underutilized_count": 0, "idle_count": 0,
                "total_purchase_cost": 0.0,
            }
        c = cat_map[cid]
        c["asset_count"] += 1
        c["total_utilization_sum"] += e["utilization_pct"]
        c["total_purchase_cost"] += e["purchase_cost"]
        if e["utilization_pct"] < underutilized_threshold:
            c["underutilized_count"] += 1
        if e["assigned_days"] == 0:
            c["idle_count"] += 1

    by_category = []
    for c in cat_map.values():
        avg = round(c["total_utilization_sum"] / c["asset_count"], 1) if c["asset_count"] else 0
        by_category.append({
            "category_id": c["category_id"],
            "category_name": c["category_name"],
            "asset_count": c["asset_count"],
            "avg_utilization_pct": avg,
            "underutilized_count": c["underutilized_count"],
            "idle_count": c["idle_count"],
            "total_purchase_cost": round(c["total_purchase_cost"], 2),
        })
    by_category.sort(key=lambda x: x["avg_utilization_pct"], reverse=True)

    assignee_map: dict = {}
    for ass in assignments:
        aid = ass.get("assigned_to_id") or "_unknown_"
        aname = ass.get("assigned_to_name") or "—"
        if aid not in assignee_map:
            assignee_map[aid] = {
                "assignee_id": aid, "assignee_name": aname,
                "asset_count": set(), "total_assigned_days": 0,
            }
        a_start = _parse_date_yyyymmdd(ass.get("assigned_date"), win_start)
        a_end = _parse_date_yyyymmdd(ass.get("returned_date"), today) if ass.get("returned_date") else today
        overlap = _intersect_days(a_start, a_end, win_start, win_end)
        assignee_map[aid]["asset_count"].add(ass.get("asset_id"))
        assignee_map[aid]["total_assigned_days"] += overlap

    by_assignee = []
    for a in assignee_map.values():
        by_assignee.append({
            "assignee_id": a["assignee_id"],
            "assignee_name": a["assignee_name"],
            "unique_assets": len(a["asset_count"]),
            "total_assigned_days": a["total_assigned_days"],
        })
    by_assignee.sort(key=lambda x: x["total_assigned_days"], reverse=True)
    by_assignee = by_assignee[:50]

    status_breakdown = {
        "active": sum(1 for e in enriched if e["status"] == "active"),
        "in_maintenance": sum(1 for e in enriched if e["status"] == "in_maintenance"),
        "disposed": 0,
    }

    total_purchase_cost = round(sum(e["purchase_cost"] for e in enriched), 2)

    return {
        "window": {
            "date_from": win_start.isoformat(),
            "date_to": win_end.isoformat(),
            "days": win_days,
        },
        "filters": {
            "category_id": category_id,
            "assignee_id": assignee_id,
            "underutilized_threshold": underutilized_threshold,
        },
        "summary": {
            "total_assets": total_assets,
            "assets_in_use_today": in_use_today,
            "avg_utilization_pct": avg_util,
            "fully_utilized_count": full_count,
            "underutilized_count": under_count,
            "idle_in_window_count": idle_count,
            "total_purchase_cost": total_purchase_cost,
            "underutilized_value_at_risk": round(total_value_at_risk, 2),
        },
        "by_category": by_category,
        "by_assignee": by_assignee,
        "top_utilized": top_utilized,
        "underutilized": underutilized,
        "idle_assets": idle_assets,
        "status_breakdown": status_breakdown,
    }


@router.get("/reports/utilization/export.csv")
async def asset_utilization_export_csv(
    request: Request,
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    category_id: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    underutilized_threshold: int = Query(30, ge=0, le=100),
):
    """Export full utilization report as CSV."""
    import csv
    import io

    rpt = await asset_utilization_report(
        request,
        date_from=date_from,
        date_to=date_to,
        category_id=category_id,
        assignee_id=assignee_id,
        underutilized_threshold=underutilized_threshold,
        limit=5000,
    )

    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([
        "Asset Number", "Asset Name", "Category", "Status",
        "Utilization %", "Assigned Days", "Effective Days",
        "Assignment Count", "Current Assignee",
        "Last Assigned Date", "Last Returned Date",
        "Purchase Cost",
    ])
    for e in rpt["top_utilized"]:
        w.writerow([
            e.get("asset_number") or "",
            e.get("asset_name") or "",
            e.get("category_name") or "",
            e.get("status") or "",
            e.get("utilization_pct"),
            e.get("assigned_days"),
            e.get("effective_window_days"),
            e.get("assignment_count"),
            e.get("current_assignee") or "",
            e.get("last_assigned_date") or "",
            e.get("last_returned_date") or "",
            e.get("purchase_cost"),
        ])
    out.seek(0)

    filename = f"asset_utilization_{rpt['window']['date_from']}_to_{rpt['window']['date_to']}.csv"
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
