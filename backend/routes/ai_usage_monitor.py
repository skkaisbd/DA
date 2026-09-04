"""
Session 19 — E-3: AI Cost Monitoring API

Endpoints (prefix: /api/ai/usage)
- GET  /summary              — aggregated stats (period configurable)
- GET  /logs                 — recent log entries
- GET  /budgets              — current budget configuration
- GET  /today                — today's usage status (real-time)

Access: superadmin / admin / manager / owner only.
"""
from fastapi import APIRouter, Request, Query, HTTPException, Body
from datetime import datetime, timezone
from auth import require_auth
from ai_cost_tracker import (
    get_usage_summary,
    get_recent_logs,
    get_ai_settings,
    invalidate_ai_settings_cache,
    TIER_MODELS,
    DEFAULT_DAILY_BUDGET_USD,
    DEFAULT_MONTHLY_BUDGET_USD,
    DEFAULT_PER_FEATURE_DAILY_USD,
)
from database import get_db

router = APIRouter(prefix="/api/ai/usage", tags=["ai-usage-monitor"])

# WS-B(d) — grup fitur AI yang dapat di-on/off oleh admin (match by prefix).
AI_FEATURE_GROUPS = [
    {"key": "executive-narrative", "label": "Analisis Eksekutif AI"},
    {"key": "daily-summary", "label": "Ringkasan Bisnis Harian"},
    {"key": "revenue-forecast", "label": "Prediksi Pendapatan"},
    {"key": "cashflow", "label": "Prediksi Arus Kas"},
    {"key": "fraud-detect", "label": "Deteksi Anomali / Fraud"},
    {"key": "prod-optimize", "label": "Optimasi Produksi"},
    {"key": "marketing", "label": "AI Marketing & Insights"},
    {"key": "maklon", "label": "Estimasi Harga Maklon"},
    {"key": "wms", "label": "AI Gudang (WMS)"},
    {"key": "smart-import", "label": "Smart Import (mapping AI)"},
    {"key": "rahaza", "label": "Asisten AI Rahaza"},
    {"key": "career", "label": "Career Coach SDM"},
]


async def _check_admin(request: Request):
    user = await require_auth(request)
    if user.get("role") not in ["superadmin", "admin", "manager", "owner"]:
        raise HTTPException(403, "Admin access required")
    return user


@router.get("/summary")
async def usage_summary(request: Request, days: int = Query(7, ge=1, le=90)):
    await _check_admin(request)
    summary = await get_usage_summary(days)
    return {"success": True, "data": summary}


@router.get("/logs")
async def usage_logs(
    request: Request,
    limit: int = Query(50, ge=1, le=500),
    feature: str = Query(None),
):
    await _check_admin(request)
    logs = await get_recent_logs(limit, feature)
    return {"success": True, "data": logs}


@router.get("/budgets")
async def get_budgets(request: Request):
    await _check_admin(request)
    return {
        "success": True,
        "data": {
            "daily_usd": DEFAULT_DAILY_BUDGET_USD,
            "monthly_usd": DEFAULT_MONTHLY_BUDGET_USD,
            "per_feature_daily_usd": DEFAULT_PER_FEATURE_DAILY_USD,
            "info": "Configurable via env vars: LLM_DAILY_BUDGET_USD / LLM_MONTHLY_BUDGET_USD / LLM_PER_FEATURE_DAILY_USD",
        },
    }


@router.get("/today")
async def today_status(request: Request):
    await _check_admin(request)
    db = get_db()
    today = datetime.now(timezone.utc).date().isoformat()
    settings = await get_ai_settings(db)
    daily_budget = float(settings.get("daily_budget_usd") or DEFAULT_DAILY_BUDGET_USD)

    # Total today
    overall = await db.rahaza_ai_usage_logs.aggregate([
        {"$match": {"date": today}},
        {"$group": {
            "_id": None,
            "calls": {"$sum": 1},
            "successful": {"$sum": {"$cond": ["$success", 1, 0]}},
            "failed": {"$sum": {"$cond": ["$success", 0, 1]}},
            "cost_usd": {"$sum": "$cost_usd"},
            "tokens": {"$sum": "$tokens_total"},
        }},
    ]).to_list(length=1)
    stats = overall[0] if overall else {
        "calls": 0, "successful": 0, "failed": 0, "cost_usd": 0, "tokens": 0
    }
    stats.pop("_id", None)
    cost = round(stats.get("cost_usd", 0), 4)

    # Top features today
    top_features = await db.rahaza_ai_usage_logs.aggregate([
        {"$match": {"date": today}},
        {"$group": {
            "_id": "$feature",
            "calls": {"$sum": 1},
            "cost_usd": {"$sum": "$cost_usd"},
        }},
        {"$project": {
            "_id": 0, "feature": "$_id", "calls": 1,
            "cost_usd": {"$round": ["$cost_usd", 4]},
        }},
        {"$sort": {"cost_usd": -1}},
        {"$limit": 10},
    ]).to_list(length=10)

    pct_daily = (cost / daily_budget * 100) if daily_budget > 0 else 0
    health = (
        "critical" if pct_daily >= 100 else
        "warning" if pct_daily >= 80 else
        "monitor" if pct_daily >= 50 else
        "healthy"
    )

    return {
        "success": True,
        "data": {
            "date": today,
            "total_calls": stats.get("calls", 0),
            "successful_calls": stats.get("successful", 0),
            "failed_calls": stats.get("failed", 0),
            "total_cost_usd": cost,
            "total_tokens": stats.get("tokens", 0),
            "daily_budget_usd": daily_budget,
            "budget_used_pct": round(pct_daily, 1),
            "health": health,
            "top_features": top_features,
        },
    }


# ── WS-B(d): AI Settings (Admin gear) ────────────────────────────────────────
@router.get("/settings")
async def get_settings(request: Request):
    """Setting AI saat ini (budget, tier default, master switch, toggle fitur)."""
    await _check_admin(request)
    db = get_db()
    settings = await get_ai_settings(db, force=True)
    return {
        "success": True,
        "data": {
            **settings,
            "feature_groups": AI_FEATURE_GROUPS,
            "tiers": list(TIER_MODELS.keys()),
            "tier_models": {k: f"{v[0]}/{v[1]}" for k, v in TIER_MODELS.items()},
            "env_defaults": {
                "daily_budget_usd": DEFAULT_DAILY_BUDGET_USD,
                "monthly_budget_usd": DEFAULT_MONTHLY_BUDGET_USD,
                "per_feature_daily_usd": DEFAULT_PER_FEATURE_DAILY_USD,
            },
        },
    }


@router.put("/settings")
async def update_settings(request: Request, payload: dict = Body(...)):
    """Update setting AI. Hanya superadmin/admin/owner (bukan manager)."""
    user = await require_auth(request)
    if user.get("role") not in ["superadmin", "admin", "owner"]:
        raise HTTPException(403, "Hanya admin/owner yang boleh mengubah setting AI")
    db = get_db()

    allowed = {
        "ai_enabled", "daily_budget_usd", "monthly_budget_usd",
        "per_feature_daily_usd", "default_tier", "disabled_features",
    }
    update = {}
    for k in allowed:
        if k not in payload:
            continue
        v = payload[k]
        if k == "ai_enabled":
            update[k] = bool(v)
        elif k in ("daily_budget_usd", "monthly_budget_usd", "per_feature_daily_usd"):
            try:
                fv = float(v)
            except (TypeError, ValueError):
                raise HTTPException(400, f"{k} harus berupa angka")
            if fv < 0:
                raise HTTPException(400, f"{k} tidak boleh negatif")
            update[k] = round(fv, 4)
        elif k == "default_tier":
            if v not in TIER_MODELS:
                raise HTTPException(400, f"default_tier harus salah satu dari {list(TIER_MODELS.keys())}")
            update[k] = v
        elif k == "disabled_features":
            if not isinstance(v, list):
                raise HTTPException(400, "disabled_features harus berupa list")
            update[k] = [str(x).strip() for x in v if str(x).strip()]

    if not update:
        raise HTTPException(400, "Tidak ada field valid untuk diupdate")

    update["updated_at"] = datetime.now(timezone.utc).isoformat()
    update["updated_by"] = user.get("email") or user.get("id")
    await db.ai_config.update_one({"id": "global"}, {"$set": update, "$setOnInsert": {"id": "global"}}, upsert=True)
    invalidate_ai_settings_cache()

    settings = await get_ai_settings(db, force=True)
    return {"success": True, "data": settings, "message": "Setting AI berhasil disimpan"}
