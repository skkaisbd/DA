"""/api/assets/predictive-maintenance/* — alerts, acknowledge, acknowledgments.

LITERAL paths (under /predictive-maintenance) — must register before /{asset_id}.
"""
from datetime import date, datetime
from typing import Optional
from dateutil.relativedelta import relativedelta
from fastapi import Request, HTTPException, Query

from database import get_db
from auth import require_auth
from ._helpers import router, _uid, _now, _ser, _safe_avg_interval_days


@router.get("/predictive-maintenance/alerts")
async def predictive_maintenance_alerts(
    request: Request,
    upcoming_window_days: int = Query(30, ge=1, le=365),
    stale_months: int = Query(6, ge=1, le=36),
    high_frequency_window_days: int = Query(90, ge=7, le=365),
    high_frequency_threshold: int = Query(3, ge=2, le=20),
    category_id: Optional[str] = Query(None),
):
    """Categorized alerts: overdue, upcoming, stale, high_frequency, predicted."""
    await require_auth(request)
    db = get_db()
    today = date.today()
    today_iso = today.isoformat()

    asset_filter = {"status": {"$ne": "disposed"}}
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

    if not assets:
        return {
            "generated_at": _now().isoformat(),
            "config": {
                "upcoming_window_days": upcoming_window_days,
                "stale_months": stale_months,
                "high_frequency_window_days": high_frequency_window_days,
                "high_frequency_threshold": high_frequency_threshold,
            },
            "summary": {
                "overdue_count": 0, "upcoming_count": 0, "stale_count": 0,
                "high_frequency_count": 0, "predicted_count": 0, "total_alerts": 0,
                "critical_count": 0,
            },
            "overdue": [], "upcoming": [], "stale": [],
            "high_frequency": [], "predicted": [],
        }

    asset_map = {a["id"]: a for a in assets}
    asset_ids = list(asset_map.keys())

    pipeline = [
        {"$match": {"asset_id": {"$in": asset_ids}}},
        {"$sort": {"maintenance_date": -1}},
        {"$group": {
            "_id": "$asset_id",
            "last_date": {"$first": "$maintenance_date"},
            "last_status": {"$first": "$status"},
            "last_type": {"$first": "$type"},
            "last_next_scheduled": {"$first": "$next_scheduled"},
            "last_cost": {"$first": "$cost"},
            "history": {"$push": {
                "date": "$maintenance_date",
                "cost": "$cost",
                "type": "$type",
                "next_scheduled": "$next_scheduled",
            }},
            "total_count": {"$sum": 1},
        }},
    ]
    maint_agg = await db.dewi_asset_maintenance.aggregate(pipeline).to_list(5000)
    maint_map = {m["_id"]: m for m in maint_agg}

    hf_window_start = (today - relativedelta(days=high_frequency_window_days)).isoformat()
    recent_pipeline = [
        {"$match": {
            "asset_id": {"$in": asset_ids},
            "maintenance_date": {"$gte": hf_window_start},
        }},
        {"$group": {"_id": "$asset_id", "recent_count": {"$sum": 1},
                    "recent_total_cost": {"$sum": "$cost"}}},
    ]
    recent_agg = await db.dewi_asset_maintenance.aggregate(recent_pipeline).to_list(5000)
    recent_map = {r["_id"]: r for r in recent_agg}

    ack_recent = await db.dewi_asset_pm_acknowledgments.find(
        {"acknowledged_at": {"$gte": (_now() - relativedelta(days=30)).isoformat()}},
        {"_id": 0, "asset_id": 1, "alert_kind": 1},
    ).to_list(5000)
    ack_set = {(a["asset_id"], a["alert_kind"]) for a in ack_recent}

    overdue, upcoming, stale, high_frequency, predicted = [], [], [], [], []

    stale_cutoff = (today - relativedelta(months=stale_months)).isoformat()
    upcoming_cutoff = (today + relativedelta(days=upcoming_window_days)).isoformat()

    for aid, asset in asset_map.items():
        m = maint_map.get(aid)
        recent = recent_map.get(aid)
        base = {
            "asset_id": aid,
            "asset_name": asset.get("name"),
            "asset_number": asset.get("asset_number"),
            "category_id": asset.get("category_id"),
            "category_name": asset.get("category_name"),
            "current_assignee": asset.get("assigned_to_name"),
            "current_status": asset.get("status"),
            "purchase_cost": asset.get("purchase_cost") or 0,
        }

        if m and m.get("last_next_scheduled") and str(m["last_next_scheduled"])[:10] < today_iso:
            days_overdue = (today - datetime.strptime(str(m["last_next_scheduled"])[:10], "%Y-%m-%d").date()).days
            if (aid, "overdue") not in ack_set:
                overdue.append({
                    **base,
                    "kind": "overdue",
                    "severity": "critical" if days_overdue > 14 else "warning",
                    "scheduled_date": str(m["last_next_scheduled"])[:10],
                    "days_overdue": days_overdue,
                    "last_maintenance_date": m["last_date"],
                    "last_type": m["last_type"],
                    "recommended_action": "Lakukan maintenance segera. Aset telah melewati jadwal.",
                })
        elif m and m.get("last_next_scheduled") and today_iso <= str(m["last_next_scheduled"])[:10] <= upcoming_cutoff:
            days_until = (datetime.strptime(str(m["last_next_scheduled"])[:10], "%Y-%m-%d").date() - today).days
            if (aid, "upcoming") not in ack_set:
                upcoming.append({
                    **base,
                    "kind": "upcoming",
                    "severity": "warning" if days_until <= 7 else "info",
                    "scheduled_date": str(m["last_next_scheduled"])[:10],
                    "days_until": days_until,
                    "last_maintenance_date": m["last_date"],
                    "last_type": m["last_type"],
                    "recommended_action": f"Siapkan maintenance dalam {days_until} hari.",
                })

        if m and m.get("last_date") and m["last_date"] < stale_cutoff:
            already_alerted = any(o["asset_id"] == aid for o in overdue) or any(u["asset_id"] == aid for u in upcoming)
            if not already_alerted and (aid, "stale") not in ack_set:
                last_date = datetime.strptime(str(m["last_date"])[:10], "%Y-%m-%d").date()
                days_since = (today - last_date).days
                months_since = round(days_since / 30.5, 1)
                stale.append({
                    **base,
                    "kind": "stale",
                    "severity": "warning" if months_since > stale_months * 1.5 else "info",
                    "last_maintenance_date": m["last_date"],
                    "days_since_maintenance": days_since,
                    "months_since_maintenance": months_since,
                    "last_type": m["last_type"],
                    "total_maintenance_count": m["total_count"],
                    "recommended_action": f"Jadwalkan inspeksi rutin. Sudah {months_since} bulan tanpa maintenance.",
                })

        if recent and recent["recent_count"] >= high_frequency_threshold:
            if (aid, "high_frequency") not in ack_set:
                high_frequency.append({
                    **base,
                    "kind": "high_frequency",
                    "severity": "critical" if recent["recent_count"] >= high_frequency_threshold * 2 else "warning",
                    "recent_count": recent["recent_count"],
                    "recent_total_cost": round(recent["recent_total_cost"] or 0, 2),
                    "window_days": high_frequency_window_days,
                    "last_maintenance_date": m["last_date"] if m else None,
                    "recommended_action": (
                        f"Pola maintenance abnormal terdeteksi: {recent['recent_count']}x dalam "
                        f"{high_frequency_window_days} hari. Pertimbangkan replacement atau "
                        f"investigasi root cause."
                    ),
                })

        if m and not m.get("last_next_scheduled") and m.get("total_count", 0) >= 2:
            dates = [h["date"] for h in m["history"] if h.get("date")]
            avg_days = _safe_avg_interval_days(dates)
            if avg_days and avg_days > 0:
                last_date = datetime.strptime(str(m["last_date"])[:10], "%Y-%m-%d").date()
                predicted_due = last_date + relativedelta(days=int(avg_days))
                if predicted_due <= (today + relativedelta(days=upcoming_window_days)):
                    already_alerted = any(o["asset_id"] == aid for o in overdue) or any(u["asset_id"] == aid for u in upcoming)
                    if not already_alerted and (aid, "predicted") not in ack_set:
                        days_offset = (predicted_due - today).days
                        predicted.append({
                            **base,
                            "kind": "predicted",
                            "severity": "warning" if days_offset < 0 else "info",
                            "last_maintenance_date": m["last_date"],
                            "avg_interval_days": round(avg_days, 1),
                            "predicted_next_due_date": predicted_due.isoformat(),
                            "days_offset": days_offset,
                            "total_maintenance_count": m["total_count"],
                            "recommended_action": (
                                f"Berdasarkan pola historical ({m['total_count']}x maintenance, "
                                f"avg {round(avg_days)} hari interval), maintenance berikutnya "
                                f"diprediksi {'sudah lewat' if days_offset < 0 else f'dalam {days_offset} hari'}."
                            ),
                        })

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    overdue.sort(key=lambda x: (-x["days_overdue"], severity_order.get(x["severity"], 9)))
    upcoming.sort(key=lambda x: (x["days_until"], severity_order.get(x["severity"], 9)))
    stale.sort(key=lambda x: (-x["days_since_maintenance"], severity_order.get(x["severity"], 9)))
    high_frequency.sort(key=lambda x: (-x["recent_count"], severity_order.get(x["severity"], 9)))
    predicted.sort(key=lambda x: (x["days_offset"], severity_order.get(x["severity"], 9)))

    summary = {
        "overdue_count": len(overdue),
        "upcoming_count": len(upcoming),
        "stale_count": len(stale),
        "high_frequency_count": len(high_frequency),
        "predicted_count": len(predicted),
        "total_alerts": len(overdue) + len(upcoming) + len(stale) + len(high_frequency) + len(predicted),
        "critical_count": sum(1 for li in [overdue, upcoming, stale, high_frequency, predicted]
                               for x in li if x.get("severity") == "critical"),
    }

    return {
        "generated_at": _now().isoformat(),
        "config": {
            "upcoming_window_days": upcoming_window_days,
            "stale_months": stale_months,
            "high_frequency_window_days": high_frequency_window_days,
            "high_frequency_threshold": high_frequency_threshold,
        },
        "summary": summary,
        "overdue": overdue,
        "upcoming": upcoming,
        "stale": stale,
        "high_frequency": high_frequency,
        "predicted": predicted,
    }


@router.post("/predictive-maintenance/acknowledge")
async def acknowledge_pm_alert(request: Request):
    """Acknowledge a PM alert so it stops appearing for 30 days.
    Body: { asset_id, alert_kind, note? }
    """
    user = await require_auth(request)
    db = get_db()
    body = await request.json()
    asset_id = body.get("asset_id")
    alert_kind = body.get("alert_kind")
    if not asset_id or not alert_kind:
        raise HTTPException(400, "asset_id dan alert_kind wajib diisi")
    if alert_kind not in {"overdue", "upcoming", "stale", "high_frequency", "predicted"}:
        raise HTTPException(400, "alert_kind tidak valid")

    doc = {
        "id": _uid(),
        "asset_id": asset_id,
        "alert_kind": alert_kind,
        "note": (body.get("note") or "").strip(),
        "acknowledged_by_id": user["id"],
        "acknowledged_by_name": user.get("name", ""),
        "acknowledged_at": _now().isoformat(),
    }
    await db.dewi_asset_pm_acknowledgments.insert_one(doc)
    return _ser(doc)


@router.get("/predictive-maintenance/acknowledgments")
async def list_pm_acknowledgments(
    request: Request,
    asset_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """List recent PM acknowledgments."""
    await require_auth(request)
    db = get_db()
    flt: dict = {}
    if asset_id:
        flt["asset_id"] = asset_id
    rows = await db.dewi_asset_pm_acknowledgments.find(
        flt, {"_id": 0}
    ).sort("acknowledged_at", -1).limit(limit).to_list(limit)
    return [_ser(r) for r in rows]
