"""
Session 12 — P1-8: Multi-metric KOL Leaderboard
Leaderboard dengan metrics: viewers, orders/session, conversion rate
"""
import logging
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, Query
from database import get_db
from auth import require_auth
# F6 (sesi #9) — leaderboard KOL WAJIB berlingkup toko.
from core import marketing_account_scope as _scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/kol-leaderboard", tags=["marketing-kol-leaderboard"])


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
#  P1-8: KOL LEADERBOARD MULTI-METRIC
# ═══════════════════════════════════════════════════════════════════════════

@router.get("/")
async def get_kol_leaderboard(
    request: Request,
    days: int = Query(30, description="Period dalam hari"),
    sort_by: str = Query("conversion_rate", description="revenue, viewers, orders_per_session, conversion_rate")
):
    """
    P1-8: KOL Leaderboard dengan multi-metric.
    
    Metrics:
    - Total Revenue
    - Total Viewers
    - Orders per Session (avg)
    - Conversion Rate (%)
    """
    user = await require_auth(request)
    db = get_db()

    # Calculate date range — RC-16: field `date` di marketing_creator_sessions
    # bertipe STRING "YYYY-MM-DD" → bandingkan sebagai string
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = end_date.strftime("%Y-%m-%d")
    
    # Aggregate pipeline — RC-16: SSOT sesi KOL = marketing_creator_sessions
    # (marketing_live_sessions = sesi LIVEHOST, tanpa kol_id/creator_id)
    pipeline = [
        {
            # F6 (sesi #9): peringkat kreator ikut lingkup toko — staf pemegang
            # satu toko tidak boleh menilai kreator toko lain dari angka omzetnya.
            "$match": await _scope.scope_filter(
                db, user, {"date": {"$gte": start_str, "$lte": end_str}})
        },
        {
            "$group": {
                "_id": "$creator_id",
                "kol_name": {"$first": "$creator_name"},
                "total_revenue": {"$sum": {"$ifNull": ["$revenue", 0]}},
                "total_viewers": {"$sum": {"$ifNull": ["$viewers", 0]}},
                "total_orders": {"$sum": {"$ifNull": ["$orders", 0]}},
                "session_count": {"$sum": 1}
            }
        },
        {
            "$addFields": {
                "orders_per_session": {
                    "$cond": [
                        {"$gt": ["$session_count", 0]},
                        {"$divide": ["$total_orders", "$session_count"]},
                        0
                    ]
                },
                "conversion_rate": {
                    "$cond": [
                        {"$gt": ["$total_viewers", 0]},
                        {"$multiply": [
                            {"$divide": ["$total_orders", "$total_viewers"]},
                            100
                        ]},
                        0
                    ]
                }
            }
        }
    ]
    
    # Add sorting
    sort_field_map = {
        "revenue": "total_revenue",
        "viewers": "total_viewers",
        "orders_per_session": "orders_per_session",
        "conversion_rate": "conversion_rate"
    }
    
    sort_field = sort_field_map.get(sort_by, "conversion_rate")
    pipeline.append({"$sort": {sort_field: -1}})
    pipeline.append({"$limit": 100})
    
    # Execute aggregation — RC-16: SSOT marketing_creator_sessions
    cursor = db.marketing_creator_sessions.aggregate(pipeline)
    results = await cursor.to_list(length=100)
    
    # Add rank
    for idx, item in enumerate(results, start=1):
        item["rank"] = idx
        item["kol_id"] = item.pop("_id")
    
    # Calculate overall stats
    total_revenue = sum(r["total_revenue"] for r in results)
    total_viewers = sum(r["total_viewers"] for r in results)
    total_orders = sum(r["total_orders"] for r in results)
    avg_conversion = (total_orders / total_viewers * 100) if total_viewers > 0 else 0
    
    return ok(
        data=serialize(results),
        meta={
            "count": len(results),
            "period_days": days,
            "sort_by": sort_by,
            "overall_stats": {
                "total_revenue": total_revenue,
                "total_viewers": total_viewers,
                "total_orders": total_orders,
                "avg_conversion_rate": round(avg_conversion, 2)
            }
        }
    )


@router.get("/{kol_id}/detail")
async def get_kol_detail(
    kol_id: str,
    request: Request,
    days: int = Query(30, description="Period dalam hari")
):
    """
    Detail metrics untuk KOL tertentu.
    """
    await require_auth(request)
    db = get_db()
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    # Get all sessions for this KOL — RC-16: SSOT marketing_creator_sessions
    # (filter creator_id; `date` string "YYYY-MM-DD")
    sessions = await db.marketing_creator_sessions.find(
        {
            "creator_id": kol_id,
            "date": {"$gte": start_date.strftime("%Y-%m-%d"), "$lte": end_date.strftime("%Y-%m-%d")}
        }
    ).sort("date", -1).to_list(length=100)
    
    if not sessions:
        return ok(data={"kol_id": kol_id, "sessions": [], "metrics": None})
    
    # Calculate metrics
    total_revenue = sum(s.get("revenue", 0) for s in sessions)
    total_viewers = sum(s.get("viewers", 0) for s in sessions)
    total_orders = sum(s.get("orders", 0) for s in sessions)
    session_count = len(sessions)
    
    orders_per_session = total_orders / session_count if session_count > 0 else 0
    conversion_rate = (total_orders / total_viewers * 100) if total_viewers > 0 else 0
    
    metrics = {
        "total_revenue": total_revenue,
        "total_viewers": total_viewers,
        "total_orders": total_orders,
        "session_count": session_count,
        "orders_per_session": round(orders_per_session, 2),
        "conversion_rate": round(conversion_rate, 2),
        "avg_revenue_per_session": round(total_revenue / session_count, 2) if session_count > 0 else 0
    }
    
    return ok(
        data={
            "kol_id": kol_id,
            "kol_name": sessions[0].get("kol_name", "Unknown"),
            "sessions": serialize(sessions),
            "metrics": metrics,
            "period_days": days
        }
    )
