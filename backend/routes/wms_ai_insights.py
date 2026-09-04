"""WMS AI Insights — Phase 0 OPTIMIZED.

AI-powered analytics for WMS modules. Standardised to Claude (Anthropic)
via Emergent Universal Key. Uses DB-level aggregations to avoid over-fetching.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Request
from pydantic import BaseModel

from auth import require_auth
from database import get_db
from services.ai import SystemPrompts, call_claude, LLMUnavailable
from services.ai_aggregates import wms_aggregates as wms_agg

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wms/ai", tags=["wms-ai-insights"])

_LLM_KEY_PRESENT = bool(os.environ.get("EMERGENT_LLM_KEY"))
if _LLM_KEY_PRESENT:
    logger.info("WMS AI insights enabled (Claude via Emergent key).")
else:
    logger.warning(
        "EMERGENT_LLM_KEY belum dikonfigurasi — /api/wms/ai/* tetap aktif "
        "tetapi akan mengembalikan 503 saat dipanggil."
    )


class QualityAnalysisRequest(BaseModel):
    roll_ids: list[str] = []
    time_period_days: int = 30


class MaterialRecommendationRequest(BaseModel):
    cmt_partner_id: str
    material_type: Optional[str] = None


class VariancePredictionRequest(BaseModel):
    zone_ids: list[str] = []
    cycle_type: str = "full"


@router.post("/fabric-rolls/quality-analysis")
async def analyze_fabric_quality_patterns(
    data: QualityAnalysisRequest, request: Request,
):
    await require_auth(request)
    db = get_db()

    summary = await wms_agg.fabric_quality_breakdown(
        db, roll_ids=data.roll_ids or None,
    )
    if summary["total_rejections"] == 0:
        return {
            "analysis": "Tidak ada data QC rejection yang cukup untuk dianalisis.",
            "insights": [],
            "recommendations": [],
        }

    text_lines = [
        f"- {b['supplier_color']}: {b['count']} rejections "
        f"({', '.join(b['materials']) if b['materials'] else 'N/A'})"
        for b in summary["breakdown"]
    ]
    summary_text = "\n".join(text_lines)

    user_prompt = (
        "Analisis data rejection fabric rolls berikut:\n\n"
        f"Total rolls rejected: {summary['total_rejections']}\n"
        f"Period: {data.time_period_days} hari terakhir\n\n"
        f"Breakdown per supplier & material:\n{summary_text}\n\n"
        "Berikan analisis komprehensif tentang:\n"
        "1. Pattern yang terdeteksi\n"
        "2. Kemungkinan root cause\n"
        "3. Rekomendasi untuk supplier dan QC team"
    )

    ai_analysis = await call_claude(
        system_message=SystemPrompts.WMS_FABRIC_QUALITY,
        user_message=user_prompt,
        session_tag="wms-fabric-quality",
        db=db,
    )
    return {
        "analysis": ai_analysis,
        "data_summary": {
            "total_rejections": summary["total_rejections"],
            "affected_suppliers": summary["affected_suppliers"],
            "period_days": data.time_period_days,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/cmt-dispatches/smart-recommendations")
async def get_smart_material_recommendations(
    data: MaterialRecommendationRequest, request: Request,
):
    await require_auth(request)
    db = get_db()

    perf = await wms_agg.cmt_dispatch_performance(
        db, cmt_partner_id=data.cmt_partner_id,
    )
    if perf["dispatch_count"] < 3:
        return {
            "recommendations": [],
            "message": (
                "Data historis belum cukup untuk memberikan rekomendasi AI. "
                "Minimum 3 dispatch diperlukan."
            ),
            "confidence": "low",
        }

    materials = perf["materials"]
    text_lines = [
        f"- {m['material_name']}: {m['dispatch_count']}x dispatch, "
        f"return rate {m['return_rate']}%"
        for m in materials
    ]
    stats_text = "\n".join(text_lines)

    user_prompt = (
        "Analisis historical dispatch data untuk CMT partner:\n\n"
        f"Partner ID: {data.cmt_partner_id}\n"
        f"Total dispatches: {perf['dispatch_count']}\n\n"
        f"Material performance:\n{stats_text}\n\n"
        "Berikan 3-5 rekomendasi material terbaik dengan alasan mengapa material "
        "tersebut cocok untuk partner ini.\n"
        "Pertimbangkan: return rate, frequency, dan consistency."
    )

    ai_recommendations = await call_claude(
        system_message=SystemPrompts.WMS_CMT_RECOMMEND,
        user_message=user_prompt,
        session_tag="wms-cmt-recommend",
        db=db,
    )

    top_materials = sorted(
        materials, key=lambda x: x.get("success_score", 0), reverse=True,
    )[:5]
    return {
        "ai_analysis": ai_recommendations,
        "top_materials": [
            {
                "material_name": m["material_name"],
                "dispatch_count": m["dispatch_count"],
                "return_rate": m["return_rate"],
                "success_score": m["success_score"],
            }
            for m in top_materials
        ],
        "confidence": "high" if perf["dispatch_count"] >= 10 else "medium",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/opname/predict-variances")
async def predict_cycle_variances(
    data: VariancePredictionRequest, request: Request,
):
    await require_auth(request)
    db = get_db()

    history = await wms_agg.opname_variance_history(db)
    if history["sessions_analysed"] == 0:
        return {
            "predictions": [],
            "message": "Belum ada data historical variance untuk prediksi",
            "confidence": "low",
        }

    variance_text = "\n".join([
        f"- Zone {b['zone']}: {b['variance_count']} variances "
        f"({b['distinct_materials']} materials berbeda)"
        for b in history["breakdown"]
    ])

    user_prompt = (
        f"Analisis historical variance data dari {history['sessions_analysed']} "
        f"cycle terakhir:\n\n"
        f"Total variances detected: {history['total_variances']}\n"
        f"Cycle type yang akan dilakukan: {data.cycle_type}\n\n"
        f"Breakdown variance per zone:\n{variance_text}\n\n"
        f"Target zones untuk cycle baru: "
        f"{', '.join(data.zone_ids) if data.zone_ids else 'All zones'}\n\n"
        "Prediksi:\n"
        "1. Zone mana yang high-risk untuk variance\n"
        "2. Material type apa yang perlu extra attention\n"
        "3. Recommended approach untuk minimize variance"
    )

    ai_prediction = await call_claude(
        system_message=SystemPrompts.WMS_VARIANCE_PREDICT,
        user_message=user_prompt,
        session_tag="wms-variance-predict",
        db=db,
    )

    risk_zones = history["breakdown"][:5]
    return {
        "ai_prediction": ai_prediction,
        "high_risk_zones": [
            {
                "zone_id": z["zone"],
                "variance_count": z["variance_count"],
                "risk_level": "high" if z["variance_count"] > 5 else "medium",
            }
            for z in risk_zones
        ],
        "confidence": "high" if history["sessions_analysed"] >= 10 else "medium",
        "based_on_cycles": history["sessions_analysed"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health")
async def ai_health_check(request: Request):
    await require_auth(request)
    available = bool(os.environ.get("EMERGENT_LLM_KEY"))
    return {
        "ai_service": "available" if available else "unavailable",
        "model": "claude-sonnet-4-5-20250929",
        "provider": "anthropic via Emergent Universal Key (emergentintegrations)",
    }


__all__ = ["router", "LLMUnavailable"]
