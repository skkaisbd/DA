"""/api/assets/expiring-alerts and /api/assets/my-assets.

These must be registered as LITERAL paths BEFORE the catch-all /{asset_id}.
"""
from datetime import date, timedelta
from fastapi import Request

from database import get_db
from auth import require_auth
from ._helpers import router, _ser


@router.get("/expiring-alerts")
async def get_expiring_alerts(request: Request, days: int = 30):
    """Aset dengan warranty atau insurance yang akan expired dalam N hari ke depan."""
    await require_auth(request)
    db = get_db()
    today_str = date.today().isoformat()
    future_str = (date.today() + timedelta(days=days)).isoformat()

    warranty_expiring = await db.dewi_assets.find(
        {"warranty_expiry_date": {"$gte": today_str, "$lte": future_str}, "status": {"$ne": "disposed"}},
        {"_id": 0},
    ).sort("warranty_expiry_date", 1).to_list(50)

    insurance_expiring = await db.dewi_assets.find(
        {"insurance_expiry_date": {"$gte": today_str, "$lte": future_str}, "status": {"$ne": "disposed"}},
        {"_id": 0},
    ).sort("insurance_expiry_date", 1).to_list(50)

    warranty_expired = await db.dewi_assets.find(
        {"warranty_expiry_date": {"$ne": None, "$lt": today_str}, "status": {"$ne": "disposed"}},
        {"_id": 0},
    ).sort("warranty_expiry_date", -1).limit(20).to_list(20)

    insurance_expired = await db.dewi_assets.find(
        {"insurance_expiry_date": {"$ne": None, "$lt": today_str}, "status": {"$ne": "disposed"}},
        {"_id": 0},
    ).sort("insurance_expiry_date", -1).limit(20).to_list(20)

    return {
        "warranty_expiring":  [_ser(a) for a in warranty_expiring],
        "warranty_expired":   [_ser(a) for a in warranty_expired],
        "insurance_expiring": [_ser(a) for a in insurance_expiring],
        "insurance_expired":  [_ser(a) for a in insurance_expired],
    }


@router.get("/my-assets")
async def get_my_assets(request: Request):
    """Aset yang ditugaskan ke user saat ini (untuk Portal Saya)."""
    user = await require_auth(request)
    db = get_db()
    assets = await db.dewi_assets.find(
        {"assigned_to_id": user["id"], "status": {"$ne": "disposed"}},
        {"_id": 0},
    ).sort("name", 1).to_list(100)
    return [_ser(a) for a in assets]
