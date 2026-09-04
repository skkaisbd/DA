"""
Marketing AI Insights Dashboard — Backend Routes
Gap 2: AI-powered insights: sales forecast, sentiment analysis, actionable recommendations
"""
import uuid
import logging
import os
import json
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request, HTTPException
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri (middleware
# hanya menolak permintaan yang MENYEBUT toko, ia tidak tahu isi jawaban).
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth
from ai_llm import LlmChat, UserMessage
from utils.waktu import now_wib

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/ai-insights", tags=["marketing-ai-insights"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def success_response(data=None, metadata=None):
    r = {"success": True}
    if data is not None:
        r["data"] = data
    if metadata is not None:
        r["metadata"] = metadata
    return r


def _now():
    return datetime.now(timezone.utc)


def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


# ─────────────────────────────────────────────
# Helper: fetch aggregated context data
# ─────────────────────────────────────────────

async def _get_orders_context(db, sq: dict | None = None) -> dict:
    """Get 30-day orders summary. `sq` = penyaring lingkup toko (F6)."""
    sq = dict(sq or {})
    since = _now() - timedelta(days=30)
    total = await db.marketing_orders.count_documents(dict(sq))
    recent = await db.marketing_orders.count_documents({**sq, "created_at": {"$gte": since}})

    pipeline = [
        {"$match": {**sq, "created_at": {"$gte": since}}},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
            "count": {"$sum": 1},
            "revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}}
        }},
        {"$sort": {"_id": 1}}
    ]
    daily_trend = []
    async for d in db.marketing_orders.aggregate(pipeline):
        daily_trend.append({"date": d["_id"], "orders": d["count"], "revenue": d["revenue"]})

    status_counts = {}
    pipeline2 = [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
    async for d in db.marketing_orders.aggregate(pipeline2):
        status_counts[d["_id"]] = d["count"]

    return {"total": total, "recent_30d": recent, "daily_trend": daily_trend[-14:], "status_counts": status_counts}


async def _get_complaints_context(db, sq: dict | None = None) -> dict:
    """Get complaints summary for sentiment. `sq` = lingkup toko (F6)."""
    sq = dict(sq or {})
    total = await db.marketing_complaints.count_documents(dict(sq))
    since = _now() - timedelta(days=30)
    recent = await db.marketing_complaints.count_documents({**sq, "created_at": {"$gte": since}})
    overdue = await db.marketing_complaints.count_documents({**sq, "sla_status": "overdue"})

    cat_pipeline = [{"$match": dict(sq)}, {"$group": {"_id": "$category", "count": {"$sum": 1}}}]
    categories = {}
    async for d in db.marketing_complaints.aggregate(cat_pipeline):
        if d["_id"]:
            categories[d["_id"]] = d["count"]

    # Sample recent texts for AI
    samples = await db.marketing_complaints.find(
        {"created_at": {"$gte": since}},
        {"complaint_text": 1, "category": 1, "sla_status": 1}
    ).limit(20).to_list(20)

    return {"total": total, "recent_30d": recent, "overdue": overdue,
            "categories": categories, "sample_texts": [
                {"text": s.get("complaint_text", ""), "category": s.get("category", "")}
                for s in samples
            ]}


async def _get_reviews_context(db, sq: dict | None = None) -> dict:
    """Get reviews/ratings summary. `sq` = lingkup toko (F6)."""
    sq = dict(sq or {})
    total = await db.marketing_reviews.count_documents(dict(sq))
    avg_pipeline = [{"$match": dict(sq)},
                    {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}]
    avg_result = await db.marketing_reviews.aggregate(avg_pipeline).to_list(1)
    avg_rating = avg_result[0]["avg_rating"] if avg_result else 0

    dist_pipeline = [{"$match": dict(sq)}, {"$group": {"_id": "$rating", "count": {"$sum": 1}}}]
    rating_dist = {}
    async for d in db.marketing_reviews.aggregate(dist_pipeline):
        rating_dist[str(d["_id"])] = d["count"]

    low_reviews = await db.marketing_reviews.find(
        {**sq, "rating": {"$lte": 2}},
        {"review_text": 1, "product_name": 1, "rating": 1}
    ).sort("created_at", -1).limit(10).to_list(10)

    return {"total": total, "avg_rating": round(avg_rating, 2),
            "rating_distribution": rating_dist,
            "recent_low_reviews": [
                {"text": r.get("review_text", ""), "product": r.get("product_name", ""), "rating": r.get("rating", 0)}
                for r in low_reviews
            ]}


async def _get_discounts_context(db, sq: dict | None = None) -> dict:
    """Expiring and active discounts. `sq` = lingkup toko (F6)."""
    sq = dict(sq or {})
    now = _now()
    soon = now + timedelta(days=3)
    expiring = await db.marketing_discounts.count_documents(
        {**sq, "end_date": {"$gte": now, "$lte": soon}})
    active = await db.marketing_discounts.count_documents(
        {**sq, "start_date": {"$lte": now}, "end_date": {"$gte": now}})
    return {"active": active, "expiring_soon": expiring}


async def _get_health_context(db, sq: dict | None = None) -> dict:
    """Latest account health. `sq` = lingkup toko (F6)."""
    sq = dict(sq or {})
    pipeline = [
        {"$match": dict(sq)},
        {"$sort": {"snapshot_date": -1}},
        {"$group": {"_id": "$account_name", "latest": {"$first": "$$ROOT"}}}
    ]
    accounts = []
    async for d in db.marketing_account_health.aggregate(pipeline):
        accounts.append({"account": d["_id"], "status": d["latest"].get("status"), "ses_score": d["latest"].get("ses_score")})
    critical = [a for a in accounts if a["status"] == "critical"]
    warning = [a for a in accounts if a["status"] == "warning"]
    return {"accounts": accounts, "critical_count": len(critical), "warning_count": len(warning)}


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────

@router.get("/overview")
async def get_overview(request: Request):
    """Agregasi context data dari semua modul marketing (tanpa AI call)."""
    user = await require_auth(request)
    db = get_db()

    # F6 (sesi #10) — ringkasan lintas modul ini adalah bahan kesimpulan AI;
    # memberi staf angka 9 toko di sini sama saja dengan membocorkannya di layar.
    sq = await _scope.scope_filter(db, user, {})
    orders = await _get_orders_context(db, sq)
    complaints = await _get_complaints_context(db, sq)
    reviews = await _get_reviews_context(db, sq)
    discounts = await _get_discounts_context(db, sq)
    health = await _get_health_context(db, sq)

    return success_response(data={
        "orders": orders,
        "complaints": complaints,
        "reviews": reviews,
        "discounts": discounts,
        "health": health,
        "generated_at": _now().isoformat()
    })


@router.post("/forecast")
async def sales_forecast(request: Request):
    """AI 7-day sales forecast based on recent orders trend."""
    await require_auth(request)
    db = get_db()

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi (EMERGENT_LLM_KEY missing)")

    orders = await _get_orders_context(db)
    daily_trend = orders["daily_trend"]

    if len(daily_trend) < 3:
        return success_response(data={
            "forecast": [],
            "summary": "Data historis terlalu sedikit untuk forecast. Minimal 3 hari data diperlukan.",
            "confidence": "low"
        })

    trend_text = "\n".join([f"  {d['date']}: {d['orders']} orders, Rp{d['revenue']:,.0f}" for d in daily_trend])

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"forecast-{uuid.uuid4().hex[:8]}",
        system_message="Kamu adalah analis data e-commerce Indonesia. Berikan forecast yang realistis dan actionable. Respond only with valid JSON."
    ).with_model("executive")

    prompt = (
        f"Data penjualan harian 14 hari terakhir (CV Dewi Aditya, fashion brand Indonesia):\n{trend_text}\n\n"
        f"Total orders 30 hari: {orders['total']}\n"
        f"Status breakdown: {json.dumps(orders.get('status_counts', {}))}\n\n"
        f"Berikan forecast 7 hari ke depan dalam format JSON persis:\n"
        f"{{\"forecast\": ["
        f"  {{\"day\": 1, \"date\": \"YYYY-MM-DD\", \"predicted_orders\": 45, \"predicted_revenue\": 5000000, \"confidence\": \"high\"}}"
        f"], \"trend\": \"upward|stable|downward\", \"confidence\": \"high|medium|low\", "
        f"\"summary\": \"Ringkasan singkat tren dan prediksi dalam Bahasa Indonesia\", "
        f"\"key_factors\": [\"faktor1\", \"faktor2\"]}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        result = json.loads(clean)
        return success_response(data=result, metadata={"historical_days": len(daily_trend)})
    except Exception as e:
        logger.error(f"Forecast error: {e}")
        # Fallback: simple moving average
        if daily_trend:
            avg_orders = sum(d["orders"] for d in daily_trend[-7:]) / min(7, len(daily_trend))
            avg_rev = sum(d["revenue"] for d in daily_trend[-7:]) / min(7, len(daily_trend))
            from datetime import timedelta as td
            forecast = []
            for i in range(1, 8):
                day_date = (now_wib() + td(days=i)).strftime("%Y-%m-%d")
                forecast.append({"day": i, "date": day_date, "predicted_orders": round(avg_orders), "predicted_revenue": round(avg_rev), "confidence": "low"})
            return success_response(data={"forecast": forecast, "trend": "stable", "confidence": "low", "summary": "Forecast menggunakan rata-rata 7 hari (AI tidak tersedia)", "key_factors": ["Data historis"]}, metadata={"fallback": True})
        raise HTTPException(500, f"Forecast gagal: {e}")


@router.post("/sentiment")
async def sentiment_analysis(request: Request):
    """AI sentiment analysis dari complaints + reviews."""
    await require_auth(request)
    db = get_db()

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi")

    complaints = await _get_complaints_context(db)
    reviews = await _get_reviews_context(db)

    all_texts = []
    for c in complaints.get("sample_texts", []):
        if c["text"]:
            all_texts.append(f"[Komplain] {c['text'][:200]}")
    for r in reviews.get("recent_low_reviews", []):
        if r["text"]:
            all_texts.append(f"[Review bintang {r['rating']}] {r['text'][:200]} — Produk: {r.get('product','')}")

    if not all_texts:
        return success_response(data={
            "overall_sentiment": "neutral",
            "sentiment_score": 0.0,
            "themes": [],
            "summary": "Belum ada data komplain/review untuk dianalisis.",
            "top_issues": [],
            "recommendations": []
        })

    texts_sample = "\n".join(all_texts[:25])

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"sentiment-{uuid.uuid4().hex[:8]}",
        system_message="Kamu adalah analis sentimen customer untuk brand fashion Indonesia. Respond only with valid JSON."
    ).with_model("executive")

    prompt = (
        f"Analisis sentimen customer dari {len(all_texts)} data komplain/review:\n\n{texts_sample}\n\n"
        f"Statistik:\n"
        f"- Total komplain 30 hari: {complaints['recent_30d']}, overdue: {complaints['overdue']}\n"
        f"- Rata-rata rating: {reviews['avg_rating']}/5.0 dari {reviews['total']} review\n"
        f"- Top kategori komplain: {json.dumps(complaints.get('categories', {}))}\n\n"
        f"Return JSON persis:\n"
        f"{{\"overall_sentiment\": \"positive|neutral|negative\", "
        f"\"sentiment_score\": -1.0_to_1.0, "
        f"\"themes\": [{{\"theme\": \"nama tema\", \"frequency\": 5, \"sentiment\": \"negative\", \"impact\": \"high|medium|low\"}}], "
        f"\"top_issues\": [{{\"issue\": \"masalah utama\", \"count\": 10, \"urgency\": \"high|medium|low\"}}], "
        f"\"summary\": \"ringkasan 2-3 kalimat Bahasa Indonesia\", "
        f"\"recommendations\": [\"rekomendasi aksi 1\", \"rekomendasi aksi 2\"]}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        result = json.loads(clean)
        return success_response(data=result, metadata={"texts_analyzed": len(all_texts)})
    except Exception as e:
        logger.error(f"Sentiment error: {e}")
        raise HTTPException(500, f"Analisis sentimen gagal: {e}")


@router.post("/recommendations")
async def get_recommendations(request: Request):
    """AI-generated prioritized action items for marketing team."""
    await require_auth(request)
    db = get_db()

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi")

    # Gather all context
    orders = await _get_orders_context(db)
    complaints = await _get_complaints_context(db)
    reviews = await _get_reviews_context(db)
    discounts = await _get_discounts_context(db)
    health = await _get_health_context(db)

    # Get upcoming launches
    upcoming_launches = await db.marketing_product_launches.count_documents(
        {"status": "planning", "launch_date": {"$gte": _now(), "$lte": _now() + timedelta(days=14)}}
    )

    # Content today
    today = now_wib().strftime("%Y-%m-%d")
    content_today = await db.marketing_content_calendar.count_documents(
        {"post_date": {"$regex": f"^{today}"}, "status": {"$nin": ["posted", "cancelled"]}}
    )

    context = {
        "orders_last_30d": orders["recent_30d"],
        "complaints_overdue": complaints["overdue"],
        "avg_rating": reviews["avg_rating"],
        "discounts_expiring_soon": discounts["expiring_soon"],
        "critical_accounts": health["critical_count"],
        "warning_accounts": health["warning_count"],
        "upcoming_launches_14d": upcoming_launches,
        "content_pending_today": content_today,
        "top_complaint_categories": dict(sorted(complaints.get("categories", {}).items(), key=lambda x: -x[1])[:3])
    }

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"recommend-{uuid.uuid4().hex[:8]}",
        system_message="Kamu adalah konsultan marketing e-commerce Indonesia untuk brand fashion. Berikan rekomendasi praktis dan prioritas yang jelas. Respond only with valid JSON."
    ).with_model("executive")

    prompt = (
        f"Status marketing CV Dewi Aditya hari ini:\n{json.dumps(context, ensure_ascii=False, indent=2)}\n\n"
        f"Berikan 5-8 action item yang diprioritaskan. Return JSON persis:\n"
        f"{{\"action_items\": ["
        f"  {{\"priority\": 1, \"urgency\": \"urgent|high|medium|low\", "
        f"  \"title\": \"judul aksi singkat\", "
        f"  \"description\": \"deskripsi detail langkah konkret Bahasa Indonesia\", "
        f"  \"module\": \"complaints|orders|content|discounts|health|ads|launches\", "
        f"  \"estimated_impact\": \"dampak yang diharapkan\"}}], "
        f"\"overall_health\": \"healthy|needs_attention|critical\", "
        f"\"summary\": \"ringkasan situasi Bahasa Indonesia 2 kalimat\"}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        result = json.loads(clean)
        return success_response(data=result, metadata={"context": context})
    except Exception as e:
        logger.error(f"Recommendations error: {e}")
        raise HTTPException(500, f"Rekomendasi gagal: {e}")
