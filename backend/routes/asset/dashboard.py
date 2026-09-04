"""GET /api/assets/dashboard — top-level KPIs, category breakdown, recent + expiring counts."""
from datetime import date, timedelta
from fastapi import Request

from database import get_db
from auth import require_auth
from ._helpers import router, _ser, _ensure_default_categories


@router.get("/dashboard")
async def get_asset_dashboard(request: Request):
    await require_auth(request)
    db = get_db()
    await _ensure_default_categories(db)

    total = await db.dewi_assets.count_documents({"status": {"$ne": "disposed"}})
    active = await db.dewi_assets.count_documents({"status": "active"})
    in_maintenance = await db.dewi_assets.count_documents({"status": "in_maintenance"})
    disposed = await db.dewi_assets.count_documents({"status": "disposed"})

    pipeline = [
        {"$match": {"status": {"$ne": "disposed"}}},
        {"$group": {
            "_id": None,
            "total_cost": {"$sum": "$purchase_cost"},
            "total_accumulated_depr": {"$sum": "$accumulated_depreciation"},
        }},
    ]
    agg = await db.dewi_assets.aggregate(pipeline).to_list(1)
    totals = agg[0] if agg else {"total_cost": 0, "total_accumulated_depr": 0}
    nbv = totals["total_cost"] - totals["total_accumulated_depr"]

    cat_pipeline = [
        {"$match": {"status": {"$ne": "disposed"}}},
        {"$group": {"_id": "$category_name", "count": {"$sum": 1}, "total_cost": {"$sum": "$purchase_cost"}}},
        {"$sort": {"count": -1}},
    ]
    by_category = await db.dewi_assets.aggregate(cat_pipeline).to_list(20)

    recent = await db.dewi_assets.find(
        {}, {"_id": 0, "id": 1, "name": 1, "asset_number": 1, "status": 1,
             "purchase_cost": 1, "category_name": 1, "created_at": 1}
    ).sort("created_at", -1).limit(5).to_list(5)

    current_period = date.today().strftime("%Y-%m")
    depr_this_month = await db.dewi_asset_depreciation.aggregate([
        {"$match": {"period": current_period}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    depr_amount = depr_this_month[0]["total"] if depr_this_month else 0

    today_str = date.today().isoformat()
    in_30_days = (date.today() + timedelta(days=30)).isoformat()
    warranty_expiring_count = await db.dewi_assets.count_documents({
        "warranty_expiry_date": {"$gte": today_str, "$lte": in_30_days},
        "status": {"$ne": "disposed"},
    })
    insurance_expiring_count = await db.dewi_assets.count_documents({
        "insurance_expiry_date": {"$gte": today_str, "$lte": in_30_days},
        "status": {"$ne": "disposed"},
    })

    return {
        "summary": {
            "total_assets": total,
            "active": active,
            "in_maintenance": in_maintenance,
            "disposed": disposed,
            "total_purchase_cost": round(totals["total_cost"], 2),
            "total_accumulated_depreciation": round(totals["total_accumulated_depr"], 2),
            "total_nbv": round(nbv, 2),
            "depreciation_this_month": round(depr_amount, 2),
            "warranty_expiring_soon": warranty_expiring_count,
            "insurance_expiring_soon": insurance_expiring_count,
        },
        "by_category": [
            {"category": b["_id"], "count": b["count"], "total_cost": b["total_cost"]}
            for b in by_category
        ],
        "recent_assets": [_ser(a) for a in recent],
    }
