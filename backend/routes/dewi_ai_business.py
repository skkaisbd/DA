"""Session 14 — P2 AI Features (Business Intelligence) — Phase 0 OPTIMIZED.

Endpoints (prefix /api/ai-business):
  POST /daily-summary        — Narrative business summary (Claude + app-cache)
  GET  /daily-summary/history
  POST /revenue-forecast     — Revenue trend forecast (Claude)
  POST /fraud-detection      — Anomaly detection in transactions (Claude)
  POST /production-optimize  — Production scheduling recommendation (Claude)

Changes vs previous version:
* All LLM calls go through `services.ai.llm_client.call_claude` / `cached_call_claude`.
* Standardized to Claude (Anthropic) per project directive.
* Heavy MongoDB queries replaced by aggregation helpers in `services.ai_aggregates.*`.
* No raw `.find({}).to_list(N)` of full collections.
* Backwards-compatible response shape.
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Query, Request

from auth import require_auth
from database import get_db
from routes._maklon_adapter import legacy_orders_view as _lmo
from services.ai import SystemPrompts, call_claude, cached_call_claude
from services.ai_aggregates import (
    finance_aggregates as fin_agg,
    production_aggregates as prod_agg,
    wms_aggregates as wms_agg,
    hr_aggregates as hr_agg,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai-business", tags=["ai-business"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def ok(data=None, meta=None):
    r = {"success": True}
    if data is not None:
        r["data"] = data
    if meta is not None:
        r["metadata"] = meta
    return r


def _serialize_for_json(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _serialize_for_json(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, list):
        return [_serialize_for_json(i) for i in obj]
    return obj


def _safe_parse_json(raw: str) -> dict | None:
    """Try to extract a JSON object from raw LLM text. Return None on failure."""
    try:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(raw[start:end])
    except Exception:
        return None
    return None


# ═══ P2-1: DAILY BUSINESS SUMMARY ════════════════════════════════════════════════
@router.post("/daily-summary")
async def generate_daily_summary(
    request: Request,
    days: int = Query(1, description="Periode ringkasan (default 1 hari)"),
):
    """P2-1: Aggregates metrics via DB pipelines, then asks Claude for narrative."""
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)
    since_iso = since.isoformat()

    fin = await fin_agg.daily_finance_metrics(db, since_iso=since_iso)
    live = await fin_agg.daily_live_session_revenue(db, since=since)
    prod = await prod_agg.production_summary(db, since_iso=since_iso)
    maklon = await prod_agg.maklon_summary(db, since_iso=since_iso, lmo_adapter=_lmo)
    att_issues = await hr_agg.attendance_issues(db, since=since)
    low_stock = await wms_agg.low_stock_count(db)

    metrics = {
        "periode": f"{days} hari terakhir",
        "tanggal": _now().strftime("%d %B %Y"),
        "produksi": prod,
        "keuangan": {
            "invoice_baru": fin["invoice_count"],
            "invoice_lunas": fin["paid_count"],
            "total_invoiced_rp": fin["total_invoiced_rp"],
        },
        "maklon": maklon,
        "sdm": {"isu_kehadiran": att_issues},
        "marketing": {
            "sesi_live": live["session_count"],
            "revenue_live_rp": live["revenue_rp"],
        },
        "alert": {"stok_rendah": low_stock},
    }

    user_prompt = f"Data bisnis hari ini:\n{json.dumps(metrics, ensure_ascii=False, indent=2)}"

    # App-level response cache (1 hour). Stable across same metrics + same period.
    cached = await cached_call_claude(
        db,
        system_message=SystemPrompts.DEWI_DAILY_SUMMARY,
        user_message=user_prompt,
        cache_namespace="daily_summary",
        cache_key_extra=[str(days), str(_now().date())],
        ttl_seconds=3600,
        session_tag="daily-summary",
    )
    summary_text = cached["text"]

    doc = {
        "id": str(uuid.uuid4()),
        "type": "daily_summary",
        "period_days": days,
        "metrics": metrics,
        "summary": summary_text,
        "generated_at": _now().isoformat(),
        "cache_hit": cached.get("cache_hit", False),
    }
    await db.ai_business_summaries.insert_one(doc)

    return ok(data={
        "summary": summary_text,
        "metrics": metrics,
        "generated_at": doc["generated_at"],
        "cache_hit": doc["cache_hit"],
    })


@router.get("/daily-summary/history")
async def get_summary_history(request: Request, limit: int = Query(10, ge=1, le=200)):
    await require_auth(request)
    db = get_db()
    docs = await db.ai_business_summaries.find(
        {"type": "daily_summary"}, {"_id": 0},
    ).sort("generated_at", -1).limit(limit).to_list(limit)
    return ok(data=_serialize_for_json(docs))


# ═══ P2-2: REVENUE FORECAST ═══════════════════════════════════════════════════════
@router.post("/revenue-forecast")
async def revenue_forecast(
    request: Request,
    months: int = Query(3, description="Berapa bulan ke depan yang diprediksi"),
):
    """P2-2: Aggregates 6-month revenue via DB pipelines, then forecasts via Claude."""
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=180)
    since_iso = since.isoformat()

    monthly_summary = await fin_agg.monthly_revenue_rollup(
        db,
        since_iso=since_iso,
        lmo_adapter=_lmo,
        since_datetime=since,
    )

    user_prompt = (
        "Data pendapatan historis 6 bulan terakhir:\n"
        f"{json.dumps(monthly_summary, ensure_ascii=False, indent=2)}\n\n"
        f"Buat prediksi untuk {months} bulan ke depan."
    )

    raw_response = await call_claude(
        system_message=SystemPrompts.DEWI_REVENUE_FORECAST,
        user_message=user_prompt,
        session_tag="revenue-forecast",
        db=db,
    )

    forecast_data = _safe_parse_json(raw_response) or {
        "analysis": raw_response,
        "forecast_months": [],
        "key_insights": [],
        "recommendation": "",
    }

    return ok(data={
        "historical": monthly_summary,
        "forecast": forecast_data,
        "forecast_months": months,
    })


# ═══ P2-4: FRAUD DETECTION ════════════════════════════════════════════════════════
@router.post("/fraud-detection")
async def fraud_detection(
    request: Request,
    days: int = Query(30, description="Periode analisis"),
):
    """P2-4: Detect transaction anomalies (Claude).

    All heavy lifting (avg/std, outliers, top adjustments) done via DB pipelines.
    """
    await require_auth(request)
    db = get_db()

    since = _now() - timedelta(days=days)
    since_iso = since.isoformat()
    signals = await fin_agg.fraud_detection_signals(db, since_iso=since_iso, since_dt=since)

    summary_data = {
        "periode_hari": days,
        "total_invoice": signals["invoice_stats"]["count"],
        "total_pembayaran": signals["payment_count"],
        "total_adjustment_stok": len(signals["top_stock_adjustments"]),
        "anomali_statistik": signals["top_invoice_outliers"][:10],
        "avg_invoice": signals["invoice_stats"]["avg"],
        "std_invoice": signals["invoice_stats"]["std"],
    }

    user_prompt = (
        f"Data transaksi {days} hari terakhir:\n"
        f"{json.dumps(summary_data, ensure_ascii=False, indent=2)}"
    )

    raw_response = await call_claude(
        system_message=SystemPrompts.DEWI_FRAUD_DETECTION,
        user_message=user_prompt,
        session_tag="fraud-detect",
        db=db,
    )

    fraud_data = _safe_parse_json(raw_response) or {
        "risk_level": "low",
        "overall_assessment": raw_response,
        "anomalies_found": signals["top_invoice_outliers"],
        "recommended_actions": [],
    }

    return ok(data={
        "statistical_anomalies": signals["top_invoice_outliers"],
        "ai_analysis": fraud_data,
        "period_days": days,
        "transaction_summary": summary_data,
    })


# ═══ P2-6: PRODUCTION OPTIMIZER ═════════════════════════════════════════════════════
@router.post("/production-optimize")
async def production_optimize(request: Request):
    await require_auth(request)
    db = get_db()

    counts = await prod_agg.production_counts(db, lmo_adapter=_lmo)
    emp_count = await hr_agg.production_employee_count(db)
    low_mat = await wms_agg.critical_materials_count(db)
    wo_details = await prod_agg.active_workorders(db, limit=10)
    maklon_details = await prod_agg.active_maklon(db, lmo_adapter=_lmo, limit=10)

    data = {
        "work_orders_aktif": counts["wo_active"],
        "maklon_orders_aktif": counts["maklon_active"],
        "karyawan_produksi": emp_count,
        "material_kritis": low_mat,
        "wo_details": _serialize_for_json(wo_details),
        "maklon_details": _serialize_for_json(maklon_details),
    }

    user_prompt = f"Status produksi saat ini:\n{json.dumps(data, ensure_ascii=False, indent=2)}"

    raw_response = await call_claude(
        system_message=SystemPrompts.DEWI_PRODUCTION_OPTIMIZE,
        user_message=user_prompt,
        session_tag="prod-optimize",
        db=db,
    )

    opt_data = _safe_parse_json(raw_response) or {
        "capacity_status": "normal",
        "overall_assessment": raw_response,
        "scheduling_suggestions": [],
    }

    return ok(data={"current_state": data, "optimization": opt_data})
