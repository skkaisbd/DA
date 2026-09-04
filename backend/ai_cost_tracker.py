"""
AI Cost Tracker — central layer untuk monitor LLM usage di seluruh aplikasi.

Features:
- Tracks every LLM call: feature, user, model, tokens (estimate), latency, success/failure
- Cost estimation based on token count + model pricing
- Budget alert ketika cumulative cost mendekati limit
- Aggregation per-feature, per-day, per-user

Usage:
    from ai_cost_tracker import tracked_llm_call
    
    result = await tracked_llm_call(
        feature="daily_summary",
        user_id=user["id"],
        model=("openai", "gpt-5.1"),
        system_message="...",
        user_message="...",
        api_key=LLM_KEY,
    )
    # result.text — the LLM response
    # result.tokens_in / tokens_out — token counts
    # result.cost_usd — estimated cost
    # result.error — error if any (None if success)

Collection: rahaza_ai_usage_logs
"""
import os
import time
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from dataclasses import dataclass
from database import get_db

logger = logging.getLogger(__name__)

# Approximate pricing per 1M tokens (USD)
# Updated 2026 — these are estimates for Emergent LLM routing
MODEL_PRICING = {
    # OpenAI (legacy — dipertahankan utk histori log)
    ("openai", "gpt-5.1"): {"input": 5.0, "output": 15.0},
    ("openai", "gpt-5"): {"input": 5.0, "output": 15.0},
    ("openai", "gpt-4o"): {"input": 2.5, "output": 10.0},
    ("openai", "gpt-4o-mini"): {"input": 0.15, "output": 0.60},
    # Anthropic Claude (KANONIK — WS-C)
    ("anthropic", "claude-opus-4-8"): {"input": 15.0, "output": 75.0},
    ("anthropic", "claude-sonnet-5"): {"input": 3.0, "output": 15.0},
    ("anthropic", "claude-sonnet-4-6"): {"input": 3.0, "output": 15.0},
    ("anthropic", "claude-haiku-4-5-20251001"): {"input": 1.0, "output": 5.0},
    ("anthropic", "claude-sonnet-4.5"): {"input": 3.0, "output": 15.0},
    ("anthropic", "claude-sonnet-4"): {"input": 3.0, "output": 15.0},
    ("anthropic", "claude-haiku-4"): {"input": 0.25, "output": 1.25},
    # Google (legacy)
    ("google", "gemini-2.0-flash"): {"input": 0.10, "output": 0.40},
    ("google", "gemini-2.5-pro"): {"input": 1.25, "output": 5.0},
    # Default fallback
    ("default", "default"): {"input": 3.0, "output": 10.0},
}

# Budget limits (configurable via env, default values)
DEFAULT_DAILY_BUDGET_USD = float(os.environ.get("LLM_DAILY_BUDGET_USD", "5.0"))
DEFAULT_MONTHLY_BUDGET_USD = float(os.environ.get("LLM_MONTHLY_BUDGET_USD", "100.0"))
DEFAULT_PER_FEATURE_DAILY_USD = float(os.environ.get("LLM_PER_FEATURE_DAILY_USD", "2.0"))

# ── WS-C: kanonik Claude + tier by complexity ────────────────────────────────
# 2026-07-27: SEMUA panggilan AI memakai Anthropic Claude API LANGSUNG
# (SDK resmi `anthropic`) dengan kunci milik owner — bukan lagi lewat
# emergentintegrations / Emergent Universal Key.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Tier -> (provider, model). Semua fitur AI wajib lewat wrapper ini.
#   executive : reasoning berat / analitik eksekutif (opus)
#   standard  : mayoritas tugas (sonnet)
#   light     : klasifikasi/ekstraksi ringan & murah (haiku)
TIER_MODELS = {
    "executive": ("anthropic", "claude-opus-4-8"),
    "standard": ("anthropic", "claude-sonnet-5"),
    "light": ("anthropic", "claude-haiku-4-5-20251001"),
}
DEFAULT_TIER = "standard"
MAX_OUTPUT_TOKENS = int(os.environ.get("LLM_MAX_OUTPUT_TOKENS", "2048"))


# ── WS-B(d): DB-driven AI settings (budget + feature toggles + master switch) ─
# Disimpan di koleksi `ai_config` doc id="global". Fallback ke default/env.
_AI_SETTINGS_CACHE = {"data": None, "ts": 0.0}
_AI_SETTINGS_TTL = 20.0  # detik


def _default_ai_settings() -> dict:
    return {
        "ai_enabled": True,
        "daily_budget_usd": DEFAULT_DAILY_BUDGET_USD,
        "monthly_budget_usd": DEFAULT_MONTHLY_BUDGET_USD,
        "per_feature_daily_usd": DEFAULT_PER_FEATURE_DAILY_USD,
        "default_tier": DEFAULT_TIER,
        "disabled_features": [],
    }


async def get_ai_settings(db=None, force: bool = False) -> dict:
    """Ambil setting AI dari DB (cache 20s). Selalu mengembalikan dict lengkap."""
    now = time.time()
    if (not force) and _AI_SETTINGS_CACHE["data"] is not None and (now - _AI_SETTINGS_CACHE["ts"]) < _AI_SETTINGS_TTL:
        return _AI_SETTINGS_CACHE["data"]
    settings = _default_ai_settings()
    try:
        db = db if db is not None else get_db()
        doc = await db.ai_config.find_one({"id": "global"}, {"_id": 0})
        if doc:
            for k in list(settings.keys()):
                if k in doc and doc[k] is not None:
                    settings[k] = doc[k]
    except Exception as e:  # pragma: no cover
        logger.warning("get_ai_settings gagal, pakai default: %s", e)
    _AI_SETTINGS_CACHE["data"] = settings
    _AI_SETTINGS_CACHE["ts"] = now
    return settings


def invalidate_ai_settings_cache() -> None:
    _AI_SETTINGS_CACHE["data"] = None
    _AI_SETTINGS_CACHE["ts"] = 0.0


def _feature_disabled(feature: str, disabled: list) -> bool:
    """True bila `feature` cocok (exact atau prefix-grup) dengan salah satu entri disabled."""
    f = (feature or "").lower()
    for d in (disabled or []):
        d = (d or "").lower().strip()
        if not d:
            continue
        if f == d or f.startswith(d + "-"):
            return True
    return False


def resolve_model(model) -> Tuple[str, str]:
    """Terima tier string ('executive'/'standard'/'light') ATAU tuple (provider, model)."""
    if isinstance(model, str):
        return TIER_MODELS.get(model.lower(), TIER_MODELS[DEFAULT_TIER])
    if isinstance(model, (tuple, list)) and len(model) == 2:
        return (model[0], model[1])
    return TIER_MODELS[DEFAULT_TIER]


class AIError(Exception):
    """Kegagalan pemanggilan AI terpusat (termasuk over-budget)."""
    def __init__(self, message: str, over_budget: bool = False):
        super().__init__(message or "AI error")
        self.over_budget = over_budget


@dataclass
class TrackedResult:
    text: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    latency_ms: float = 0.0
    model: str = ""
    success: bool = False
    error: Optional[str] = None
    over_budget: bool = False
    budget_warning: Optional[str] = None


def _approx_tokens(text: str) -> int:
    """Rough heuristic: ~4 chars per token English, ~3 for Indonesian."""
    if not text:
        return 0
    return max(1, len(text) // 3)


def _calc_cost(model: Tuple[str, str], tokens_in: int, tokens_out: int) -> float:
    pricing = MODEL_PRICING.get(model, MODEL_PRICING[("default", "default")])
    return (tokens_in * pricing["input"] + tokens_out * pricing["output"]) / 1_000_000


async def _check_budget(db, feature: str, *, daily_budget=None, monthly_budget=None, per_feature_budget=None) -> Tuple[bool, Optional[str]]:
    """Check if we're approaching budget. Returns (over_budget, warning_message).

    Budget limits berasal dari setting DB (WS-B d); fallback ke default env.
    """
    daily_budget = DEFAULT_DAILY_BUDGET_USD if daily_budget is None else float(daily_budget)
    monthly_budget = DEFAULT_MONTHLY_BUDGET_USD if monthly_budget is None else float(monthly_budget)
    per_feature_budget = DEFAULT_PER_FEATURE_DAILY_USD if per_feature_budget is None else float(per_feature_budget)

    today = datetime.now(timezone.utc).date()
    month_start = today.replace(day=1)

    # Daily total
    daily_pipeline = [
        {"$match": {"date": today.isoformat(), "success": True}},
        {"$group": {"_id": None, "total": {"$sum": "$cost_usd"}}},
    ]
    daily_total_doc = await db.rahaza_ai_usage_logs.aggregate(daily_pipeline).to_list(length=1)
    daily_total = daily_total_doc[0]["total"] if daily_total_doc else 0.0

    if daily_total >= daily_budget:
        return True, f"Daily budget exceeded: ${daily_total:.4f} / ${daily_budget}"

    # Feature daily
    feat_pipeline = [
        {"$match": {"date": today.isoformat(), "feature": feature, "success": True}},
        {"$group": {"_id": None, "total": {"$sum": "$cost_usd"}}},
    ]
    feat_total_doc = await db.rahaza_ai_usage_logs.aggregate(feat_pipeline).to_list(length=1)
    feat_total = feat_total_doc[0]["total"] if feat_total_doc else 0.0
    if feat_total >= per_feature_budget:
        return True, f"Feature {feature} daily budget exceeded: ${feat_total:.4f} / ${per_feature_budget}"

    # Monthly total
    monthly_pipeline = [
        {"$match": {"date": {"$gte": month_start.isoformat()}, "success": True}},
        {"$group": {"_id": None, "total": {"$sum": "$cost_usd"}}},
    ]
    monthly_total_doc = await db.rahaza_ai_usage_logs.aggregate(monthly_pipeline).to_list(length=1)
    monthly_total = monthly_total_doc[0]["total"] if monthly_total_doc else 0.0
    if monthly_total >= monthly_budget:
        return True, f"Monthly budget exceeded: ${monthly_total:.4f} / ${monthly_budget}"

    # Warning thresholds
    if daily_total >= daily_budget * 0.8:
        return False, f"⚠️ Daily budget 80% reached: ${daily_total:.4f} / ${daily_budget}"
    if monthly_total >= monthly_budget * 0.8:
        return False, f"⚠️ Monthly budget 80% reached: ${monthly_total:.4f} / ${monthly_budget}"

    return False, None


async def log_usage(
    feature: str,
    user_id: Optional[str],
    model: Tuple[str, str],
    tokens_in: int,
    tokens_out: int,
    cost_usd: float,
    latency_ms: float,
    success: bool,
    error: Optional[str] = None,
):
    """Insert usage log into rahaza_ai_usage_logs."""
    try:
        db = get_db()
        await db.rahaza_ai_usage_logs.insert_one({
            "id": str(uuid.uuid4()),
            "feature": feature,
            "user_id": user_id,
            "model_provider": model[0] if isinstance(model, tuple) else "unknown",
            "model_name": model[1] if isinstance(model, tuple) else str(model),
            "tokens_in": int(tokens_in),
            "tokens_out": int(tokens_out),
            "tokens_total": int(tokens_in + tokens_out),
            "cost_usd": round(float(cost_usd), 6),
            "latency_ms": round(float(latency_ms), 2),
            "success": bool(success),
            "error": error,
            "date": datetime.now(timezone.utc).date().isoformat(),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"Failed to log AI usage: {e}")


async def tracked_llm_call(
    feature: str,
    user_id: Optional[str],
    model,
    system_message: str,
    user_message: str,
    api_key: Optional[str] = None,
    session_id: Optional[str] = None,
    skip_budget_check: bool = False,
    image_base64: Optional[str] = None,
    max_tokens: Optional[int] = None,
) -> TrackedResult:
    """Wrapper terpusat yang melacak biaya LLM.

    `model` bisa tier string ('executive'/'standard'/'light') atau tuple (provider, model).
    `api_key` default ke EMERGENT_LLM_KEY. `image_base64` untuk input vision (opsional).
    Return TrackedResult dengan .text saat sukses, .error saat gagal.
    """
    model = resolve_model(model)
    # 2026-07-27: hanya kunci Anthropic yang sah. Pemanggil lama masih meneruskan
    # EMERGENT_LLM_KEY secara eksplisit — abaikan dan pakai kunci Claude resmi.
    api_key = api_key if str(api_key or "").startswith("sk-ant-") else ANTHROPIC_API_KEY
    result = TrackedResult(model=f"{model[0]}/{model[1]}")
    db = get_db()

    if not api_key:
        result.error = "ANTHROPIC_API_KEY belum dikonfigurasi"
        return result

    # WS-B(d): setting DB — master switch, toggle fitur, & budget dari admin
    if not skip_budget_check:
        try:
            settings = await get_ai_settings(db)
            if not settings.get("ai_enabled", True):
                result.error = "AI dinonaktifkan oleh admin (master switch)."
                return result
            if _feature_disabled(feature, settings.get("disabled_features")):
                result.error = f"Fitur AI '{feature}' dinonaktifkan oleh admin."
                return result
        except Exception as e:
            logger.warning(f"AI settings load failed (continuing): {e}")
            settings = _default_ai_settings()

        # Budget check (limits dari settings)
        try:
            over, warning = await _check_budget(
                db, feature,
                daily_budget=settings.get("daily_budget_usd"),
                monthly_budget=settings.get("monthly_budget_usd"),
                per_feature_budget=settings.get("per_feature_daily_usd"),
            )
            if over:
                result.over_budget = True
                result.error = warning
                result.budget_warning = warning
                return result
            if warning:
                result.budget_warning = warning
        except Exception as e:
            logger.warning(f"Budget check failed (continuing): {e}")

    # Approximate input tokens (system + user)
    tokens_in_approx = _approx_tokens(system_message) + _approx_tokens(user_message)

    start = time.time()
    try:
        from anthropic import AsyncAnthropic
        client = AsyncAnthropic(api_key=api_key)

        if image_base64:
            content = [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/png", "data": image_base64}},
                {"type": "text", "text": user_message},
            ]
        else:
            content = user_message

        msg = await client.messages.create(
            model=model[1],
            max_tokens=int(max_tokens or MAX_OUTPUT_TOKENS),
            system=system_message or "",
            messages=[{"role": "user", "content": content}],
        )
        elapsed_ms = (time.time() - start) * 1000

        response = "".join(getattr(b, "text", "") for b in (msg.content or []))
        usage = getattr(msg, "usage", None)
        tokens_in = int(getattr(usage, "input_tokens", 0) or tokens_in_approx)
        tokens_out = int(getattr(usage, "output_tokens", 0) or _approx_tokens(response))
        cost = _calc_cost(model, tokens_in, tokens_out)

        result.text = response
        result.tokens_in = tokens_in
        result.tokens_out = tokens_out
        result.cost_usd = cost
        result.latency_ms = elapsed_ms
        result.success = True

        await log_usage(feature, user_id, model, tokens_in, tokens_out, cost, elapsed_ms, True)
        return result
    except Exception as e:
        elapsed_ms = (time.time() - start) * 1000
        result.error = str(e)
        result.latency_ms = elapsed_ms
        result.success = False
        await log_usage(feature, user_id, model, tokens_in_approx, 0, 0.0, elapsed_ms, False, str(e))
        return result


# ── WS-C: High-level helpers (dipakai semua route) ───────────────────────────
async def ai_complete(
    feature: str,
    system_message: str,
    user_message: str,
    tier: str = DEFAULT_TIER,
    user_id: Optional[str] = None,
    image_base64: Optional[str] = None,
    max_tokens: Optional[int] = None,
    session_id: Optional[str] = None,
    raise_on_error: bool = True,
) -> str:
    """Panggil AI dan kembalikan teks. Raise AIError bila gagal (default)."""
    res = await tracked_llm_call(
        feature=feature, user_id=user_id, model=tier,
        system_message=system_message, user_message=user_message,
        image_base64=image_base64, max_tokens=max_tokens, session_id=session_id,
    )
    if not res.success:
        if raise_on_error:
            raise AIError(res.error or "AI call gagal", over_budget=res.over_budget)
        return ""
    return res.text


def _extract_json(text: str):
    """Strip markdown fence & ekstrak objek/array JSON pertama; return parsed atau raise."""
    import json as _json
    import re as _re
    clean = (text or "").strip()
    if clean.startswith("```"):
        parts = clean.split("```")
        clean = parts[1] if len(parts) > 1 else clean
        if clean[:4].lower() == "json":
            clean = clean[4:]
        clean = clean.strip()
    try:
        return _json.loads(clean)
    except Exception:
        m = _re.search(r"(\{.*\}|\[.*\])", clean, _re.S)
        if m:
            return _json.loads(m.group(1))
        raise


async def ai_json(
    feature: str,
    system_message: str,
    user_message: str,
    tier: str = DEFAULT_TIER,
    user_id: Optional[str] = None,
    image_base64: Optional[str] = None,
    max_tokens: Optional[int] = None,
    default=None,
):
    """Structured output: minta JSON valid, parse robust. Return `default` bila gagal (jika diberikan), else raise AIError."""
    sys_json = (system_message or "").rstrip()
    if "json" not in sys_json.lower():
        sys_json += " Always respond with a single valid JSON value only — no prose, no markdown fences."
    res = await tracked_llm_call(
        feature=feature, user_id=user_id, model=tier,
        system_message=sys_json, user_message=user_message,
        image_base64=image_base64, max_tokens=max_tokens,
    )
    if not res.success:
        if default is not None:
            return default
        raise AIError(res.error or "AI JSON call gagal", over_budget=res.over_budget)
    try:
        return _extract_json(res.text)
    except Exception as e:
        if default is not None:
            return default
        raise AIError(f"Gagal parse JSON dari AI: {e}")


async def get_usage_summary(days: int = 7) -> dict:
    """Get aggregated usage stats for last N days."""
    db = get_db()
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
    
    # Overall totals
    overall = await db.rahaza_ai_usage_logs.aggregate([
        {"$match": {"date": {"$gte": cutoff}}},
        {"$group": {
            "_id": None,
            "total_calls": {"$sum": 1},
            "successful_calls": {"$sum": {"$cond": ["$success", 1, 0]}},
            "failed_calls": {"$sum": {"$cond": ["$success", 0, 1]}},
            "total_cost_usd": {"$sum": "$cost_usd"},
            "total_tokens": {"$sum": "$tokens_total"},
            "avg_latency_ms": {"$avg": "$latency_ms"},
        }},
    ]).to_list(length=1)
    
    overall_stats = overall[0] if overall else {
        "total_calls": 0, "successful_calls": 0, "failed_calls": 0,
        "total_cost_usd": 0, "total_tokens": 0, "avg_latency_ms": 0,
    }
    overall_stats.pop("_id", None)

    # By feature
    by_feature = await db.rahaza_ai_usage_logs.aggregate([
        {"$match": {"date": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$feature",
            "calls": {"$sum": 1},
            "successful": {"$sum": {"$cond": ["$success", 1, 0]}},
            "failed": {"$sum": {"$cond": ["$success", 0, 1]}},
            "cost_usd": {"$sum": "$cost_usd"},
            "tokens": {"$sum": "$tokens_total"},
            "avg_latency_ms": {"$avg": "$latency_ms"},
        }},
        {"$project": {
            "_id": 0, "feature": "$_id", "calls": 1, "successful": 1, "failed": 1,
            "cost_usd": {"$round": ["$cost_usd", 4]},
            "tokens": 1,
            "avg_latency_ms": {"$round": ["$avg_latency_ms", 0]},
        }},
        {"$sort": {"cost_usd": -1}},
    ]).to_list(length=100)
    
    # By day
    by_day = await db.rahaza_ai_usage_logs.aggregate([
        {"$match": {"date": {"$gte": cutoff}}},
        {"$group": {
            "_id": "$date",
            "calls": {"$sum": 1},
            "cost_usd": {"$sum": "$cost_usd"},
            "tokens": {"$sum": "$tokens_total"},
        }},
        {"$project": {
            "_id": 0, "date": "$_id", "calls": 1,
            "cost_usd": {"$round": ["$cost_usd", 4]},
            "tokens": 1,
        }},
        {"$sort": {"date": 1}},
    ]).to_list(length=days + 5)

    return {
        "period_days": days,
        "from_date": cutoff,
        "to_date": datetime.now(timezone.utc).date().isoformat(),
        "overall": {
            **overall_stats,
            "total_cost_usd": round(overall_stats.get("total_cost_usd", 0), 4),
            "avg_latency_ms": round(overall_stats.get("avg_latency_ms", 0) or 0, 0),
        },
        "by_feature": by_feature,
        "by_day": by_day,
        "budgets": {
            "daily_usd": DEFAULT_DAILY_BUDGET_USD,
            "monthly_usd": DEFAULT_MONTHLY_BUDGET_USD,
            "per_feature_daily_usd": DEFAULT_PER_FEATURE_DAILY_USD,
        },
    }


async def get_recent_logs(limit: int = 50, feature: Optional[str] = None) -> list:
    """Get recent usage log entries."""
    db = get_db()
    q = {}
    if feature:
        q["feature"] = feature
    logs = await db.rahaza_ai_usage_logs.find(q).sort("created_at", -1).to_list(length=limit)
    for log in logs:
        log.pop("_id", None)
    return logs
