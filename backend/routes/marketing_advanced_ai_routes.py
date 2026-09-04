"""
Phase 5 — Advanced AI Features
A) Dynamic Pricing (ON/OFF + configurable guardrails + suggestion workflow)
B) Churn Prediction (RFM + AI explanation)
C) A/B Testing (content experiments + AI winner conclusion)
"""
import uuid
import logging
import os
import json
import math
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
from database import get_db
from auth import require_auth
from ai_llm import LlmChat, UserMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/advanced-ai", tags=["marketing-advanced-ai"])
EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")


def _now(): return datetime.now(timezone.utc)

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
#  PHASE 5A — DYNAMIC PRICING
# ═══════════════════════════════════════════════════════════════════════════

DEFAULT_PRICING_SETTINGS = {
    "enabled": False,
    "mode": "suggest_only",            # suggest_only | auto_apply
    "approval_required": True,
    "min_margin_pct_global": 25.0,      # minimum margin (%) harga setelah adjustment
    "max_price_increase_pct_per_run": 10.0,
    "max_price_decrease_pct_per_run": 15.0,
    "rounding_rule": 500,              # round to nearest X (e.g. 500, 1000)
    "exclude_skus": [],
    "exclude_categories": [],
    "include_platforms": ["shopee", "tiktok", "tokopedia"],
    "reason_weights": {
        "demand": 0.35,
        "stock": 0.25,
        "reviews": 0.20,
        "ads": 0.10,
        "complaints": 0.10
    },
    "run_cooldown_minutes": 30,         # min gap between runs
    "updated_at": None,
    "updated_by": None
}


class PricingSettingsIn(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    approval_required: Optional[bool] = None
    min_margin_pct_global: Optional[float] = None
    max_price_increase_pct_per_run: Optional[float] = Field(default=None, ge=0)
    max_price_decrease_pct_per_run: Optional[float] = Field(default=None, ge=0)
    rounding_rule: Optional[int] = None
    exclude_skus: Optional[List[str]] = None
    exclude_categories: Optional[List[str]] = None
    include_platforms: Optional[List[str]] = None
    run_cooldown_minutes: Optional[int] = None


async def _get_pricing_settings(db) -> dict:
    doc = await db.marketing_dynamic_pricing_settings.find_one({"_type": "settings"})
    if not doc:
        return {**DEFAULT_PRICING_SETTINGS}
    doc.pop("_id", None)
    return doc


@router.get("/pricing/settings")
async def get_pricing_settings(request: Request):
    await require_auth(request)
    db = get_db()
    settings = await _get_pricing_settings(db)
    return ok(data=serialize(settings))


@router.put("/pricing/settings")
async def update_pricing_settings(payload: PricingSettingsIn, request: Request):
    await require_auth(request)
    db = get_db()
    current = await _get_pricing_settings(db)
    update = {k: v for k, v in payload.dict().items() if v is not None}
    merged = {**current, **update, "_type": "settings", "updated_at": _now(), "updated_by": "admin"}
    await db.marketing_dynamic_pricing_settings.update_one(
        {"_type": "settings"}, {"$set": merged}, upsert=True
    )
    merged.pop("_id", None)
    return ok(data=serialize(merged), meta={"message": "Settings disimpan"})


@router.post("/pricing/run")
async def run_pricing_suggestions(request: Request):
    """Generate dynamic pricing suggestions berdasarkan data penjualan + AI analysis."""
    await require_auth(request)
    db = get_db()
    settings = await _get_pricing_settings(db)

    if not settings.get("enabled"):
        raise HTTPException(400, "Dynamic Pricing sedang OFF. Aktifkan di Settings terlebih dahulu.")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi")

    # Rate limit check
    cooldown = settings.get("run_cooldown_minutes", 30)
    last = await db.marketing_dynamic_pricing_events.find_one(
        {"event_type": "run"}, sort=[("created_at", -1)]
    )
    if last:
        gap = (_now() - last["created_at"].replace(tzinfo=timezone.utc)).total_seconds() / 60
        if gap < cooldown:
            remain = round(cooldown - gap)
            raise HTTPException(429, f"Terlalu sering. Coba lagi dalam {remain} menit.")

    # Kumpulkan data produk dari orders (derive pricing context)
    pipeline = [
        {"$group": {
            "_id": "$product_name",
            "total_orders_30d": {"$sum": 1},
            "avg_price": {"$avg": {"$ifNull": ["$unit_price", "$price", 0]}},
            "total_revenue": {"$sum": {"$ifNull": ["$total_amount", 0]}},
            "return_count": {"$sum": {"$cond": [{"$eq": ["$status", "returned"]}, 1, 0]}},
            "cancel_count": {"$sum": {"$cond": [{"$eq": ["$status", "cancelled"]}, 1, 0]}}
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"total_orders_30d": -1}},
        {"$limit": 20}
    ]
    products = []
    async for p in db.marketing_orders.aggregate(pipeline):
        products.append({
            "product": p["_id"],
            "orders_30d": p["total_orders_30d"],
            "avg_price_rp": round(p["avg_price"] or 0),
            "revenue_30d": round(p["total_revenue"] or 0),
            "return_rate_pct": round(p["return_count"] / max(p["total_orders_30d"], 1) * 100, 1),
            "cancel_rate_pct": round(p["cancel_count"] / max(p["total_orders_30d"], 1) * 100, 1),
        })

    # Review scores per product
    rev_pipeline = [
        {"$group": {
            "_id": "$product_name",
            "avg_rating": {"$avg": "$rating"},
            "review_count": {"$sum": 1}
        }}
    ]
    review_map = {}
    async for r in db.marketing_reviews.aggregate(rev_pipeline):
        review_map[r["_id"]] = {"avg_rating": round(r["avg_rating"] or 0, 1), "review_count": r["review_count"]}

    # Complaints per product
    comp_pipeline = [
        {"$group": {"_id": "$product_name", "complaints_30d": {"$sum": 1}}}
    ]
    comp_map = {}
    async for c in db.marketing_complaints.aggregate(comp_pipeline):
        comp_map[c["_id"]] = c["complaints_30d"]

    if not products:
        # Seed with sample products if empty
        products = [
            {"product": "Dress Batik Premium", "orders_30d": 45, "avg_price_rp": 185000, "revenue_30d": 8325000, "return_rate_pct": 2.2, "cancel_rate_pct": 1.1},
            {"product": "Kebaya Modern", "orders_30d": 28, "avg_price_rp": 320000, "revenue_30d": 8960000, "return_rate_pct": 1.4, "cancel_rate_pct": 3.5},
            {"product": "Blouse Casual", "orders_30d": 62, "avg_price_rp": 95000, "revenue_30d": 5890000, "return_rate_pct": 0.8, "cancel_rate_pct": 4.8},
            {"product": "Rok Plisket", "orders_30d": 8, "avg_price_rp": 145000, "revenue_30d": 1160000, "return_rate_pct": 5.0, "cancel_rate_pct": 12.5},
            {"product": "Celana Palazzo", "orders_30d": 34, "avg_price_rp": 110000, "revenue_30d": 3740000, "return_rate_pct": 1.5, "cancel_rate_pct": 2.9},
        ]

    # Enrich with reviews & complaints
    for p in products:
        rv = review_map.get(p["product"], {})
        p["avg_rating"] = rv.get("avg_rating", 4.5)
        p["review_count"] = rv.get("review_count", 0)
        p["complaints_30d"] = comp_map.get(p["product"], 0)

    # AI pricing analysis
    cfg_summary = {
        "min_margin_pct": settings["min_margin_pct_global"],
        "max_increase_pct": settings["max_price_increase_pct_per_run"],
        "max_decrease_pct": settings["max_price_decrease_pct_per_run"],
        "rounding": settings["rounding_rule"]
    }

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"pricing-{uuid.uuid4().hex[:8]}",
        system_message=(
            "Kamu adalah sistem dynamic pricing untuk brand fashion Indonesia CV Dewi Aditya. "
            "Berikan rekomendasi harga yang cerdas, aman, dan realistis. "
            "Pertimbangkan demand, review, complaint, dan guardrails. "
            "Respond only with valid JSON."
        )
    ).with_model("openai", "gpt-4o-mini")

    prompt = (
        f"Data produk 30 hari terakhir:\n{json.dumps(products, ensure_ascii=False, indent=2)}\n\n"
        f"Konfigurasi guardrails:\n{json.dumps(cfg_summary, ensure_ascii=False)}\n\n"
        f"Untuk setiap produk, tentukan apakah harga harus naik, turun, atau tetap. "
        f"Hitung suggested_price_rp (sudah dibulatkan ke {settings['rounding_rule']}). "
        f"Jika avg_price_rp = 0, skip produk tersebut.\n\n"
        f"Return JSON persis:\n"
        f"{{\"suggestions\": ["
        f"{{\"product\": \"nama produk\", "
        f"\"current_price_rp\": 185000, "
        f"\"suggested_price_rp\": 195000, "
        f"\"direction\": \"increase|decrease|hold\", "
        f"\"change_pct\": 5.4, "
        f"\"confidence\": \"high|medium|low\", "
        f"\"primary_reason\": \"demand tinggi (45 orders/30 hari)\", "
        f"\"secondary_reasons\": [\"rating 4.8 ★\"], "
        f"\"guardrail_ok\": true, "
        f"\"guardrail_note\": \"null atau penjelasan jika ada batasan yang tersentuh\""
        f"}}]}}"
    )

    suggestions_created = []
    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        ai_result = json.loads(clean)

        for s in ai_result.get("suggestions", []):
            if s.get("direction") == "hold" or s.get("current_price_rp", 0) == 0:
                continue
            doc = {
                "id": str(uuid.uuid4()),
                "product": s.get("product", ""),
                "current_price_rp": s.get("current_price_rp", 0),
                "suggested_price_rp": s.get("suggested_price_rp", 0),
                "direction": s.get("direction", "hold"),
                "change_pct": s.get("change_pct", 0),
                "confidence": s.get("confidence", "medium"),
                "primary_reason": s.get("primary_reason", ""),
                "secondary_reasons": s.get("secondary_reasons", []),
                "guardrail_ok": s.get("guardrail_ok", True),
                "guardrail_note": s.get("guardrail_note"),
                "status": "pending",
                "created_at": _now(),
                "updated_at": _now(),
                "applied_at": None,
                "decided_by": None
            }
            await db.marketing_dynamic_pricing_suggestions.insert_one(doc)
            doc.pop("_id", None)
            suggestions_created.append(doc)

    except Exception as e:
        logger.error(f"Pricing AI error: {e}")
        raise HTTPException(500, f"AI pricing gagal: {e}")

    # Log run event
    await db.marketing_dynamic_pricing_events.insert_one({
        "id": str(uuid.uuid4()),
        "event_type": "run",
        "suggestions_count": len(suggestions_created),
        "created_at": _now(),
        "actor": "admin"
    })

    return ok(
        data={"suggestions": serialize(suggestions_created)},
        meta={"count": len(suggestions_created), "products_analyzed": len(products)}
    )


@router.get("/pricing/suggestions")
async def list_pricing_suggestions(
    request: Request,
    status: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20)
):
    await require_auth(request)
    db = get_db()
    filt = {}
    if status:
        filt["status"] = status
    if direction:
        filt["direction"] = direction
    total = await db.marketing_dynamic_pricing_suggestions.count_documents(filt)
    skip = (page - 1) * page_size
    docs = await db.marketing_dynamic_pricing_suggestions.find(filt).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return ok(
        data={"suggestions": serialize(docs)},
        meta={"total": total, "page": page, "page_size": page_size,
              "total_pages": max(1, math.ceil(total / page_size))}
    )


@router.post("/pricing/suggestions/{suggestion_id}/approve")
async def approve_suggestion(suggestion_id: str, request: Request):
    from routes.shared import require_perm
    await require_perm(
        request, 'toko.approve', 'toko.manage', 'pricing.approve',
        legacy_roles=('manager_marketing', 'pic_marketing', 'pic_toko',
                      'manager', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menyetujui usulan harga.')
    db = get_db()
    doc = await db.marketing_dynamic_pricing_suggestions.find_one({"id": suggestion_id})
    if not doc:
        raise HTTPException(404, "Suggestion tidak ditemukan")
    if doc["status"] != "pending":
        raise HTTPException(400, f"Status sudah {doc['status']}")
    await db.marketing_dynamic_pricing_suggestions.update_one(
        {"id": suggestion_id},
        {"$set": {"status": "approved", "updated_at": _now(), "decided_by": "admin"}}
    )
    await db.marketing_dynamic_pricing_events.insert_one({
        "id": str(uuid.uuid4()), "event_type": "approve",
        "suggestion_id": suggestion_id, "product": doc["product"],
        "current_price_rp": doc["current_price_rp"], "suggested_price_rp": doc["suggested_price_rp"],
        "created_at": _now(), "actor": "admin"
    })
    return ok(data={"status": "approved"})


@router.post("/pricing/suggestions/{suggestion_id}/reject")
async def reject_suggestion(
    suggestion_id: str, request: Request,
    reason: Optional[str] = Query(None)
):
    from routes.shared import require_perm
    await require_perm(
        request, 'toko.approve', 'toko.manage', 'pricing.approve',
        legacy_roles=('manager_marketing', 'pic_marketing', 'pic_toko',
                      'manager', 'owner', 'admin', 'superadmin'),
        message='Akses ditolak: Anda tidak berhak menolak usulan harga.')
    db = get_db()
    doc = await db.marketing_dynamic_pricing_suggestions.find_one({"id": suggestion_id})
    if not doc:
        raise HTTPException(404, "Suggestion tidak ditemukan")
    if doc["status"] not in ["pending", "approved"]:
        raise HTTPException(400, f"Status sudah {doc['status']}")
    await db.marketing_dynamic_pricing_suggestions.update_one(
        {"id": suggestion_id},
        {"$set": {"status": "rejected", "updated_at": _now(), "decided_by": "admin", "reject_reason": reason}}
    )
    await db.marketing_dynamic_pricing_events.insert_one({
        "id": str(uuid.uuid4()), "event_type": "reject",
        "suggestion_id": suggestion_id, "product": doc["product"],
        "reason": reason, "created_at": _now(), "actor": "admin"
    })
    return ok(data={"status": "rejected"})


@router.post("/pricing/suggestions/{suggestion_id}/apply")
async def apply_suggestion(suggestion_id: str, request: Request):
    """Mark as applied (in real system would push to platform API)."""
    await require_auth(request)
    db = get_db()
    settings = await _get_pricing_settings(db)
    if not settings.get("enabled"):
        raise HTTPException(400, "Dynamic Pricing sedang OFF")
    doc = await db.marketing_dynamic_pricing_suggestions.find_one({"id": suggestion_id})
    if not doc:
        raise HTTPException(404, "Suggestion tidak ditemukan")
    if doc["status"] not in ["pending", "approved"]:
        raise HTTPException(400, f"Tidak bisa apply status '{doc['status']}'")
    await db.marketing_dynamic_pricing_suggestions.update_one(
        {"id": suggestion_id},
        {"$set": {"status": "applied", "applied_at": _now(), "updated_at": _now(), "decided_by": "admin"}}
    )
    await db.marketing_dynamic_pricing_events.insert_one({
        "id": str(uuid.uuid4()), "event_type": "apply",
        "suggestion_id": suggestion_id, "product": doc["product"],
        "old_price_rp": doc["current_price_rp"], "new_price_rp": doc["suggested_price_rp"],
        "change_pct": doc["change_pct"], "created_at": _now(), "actor": "admin"
    })
    return ok(data={"status": "applied", "new_price_rp": doc["suggested_price_rp"]})


@router.get("/pricing/events")
async def list_pricing_events(
    request: Request,
    page: int = Query(1, ge=1),
    page_size: int = Query(30)
):
    await require_auth(request)
    db = get_db()
    total = await db.marketing_dynamic_pricing_events.count_documents({})
    skip = (page - 1) * page_size
    docs = await db.marketing_dynamic_pricing_events.find({}).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return ok(data={"events": serialize(docs)}, meta={"total": total})


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 5B — CHURN PREDICTION
# ═══════════════════════════════════════════════════════════════════════════

@router.post("/churn/run")
async def run_churn_analysis(request: Request):
    """RFM-based churn analysis + AI explanation & recommendations."""
    await require_auth(request)
    db = get_db()
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi")

    # Build customer profiles from orders
    now = _now()
    pipeline = [
        {"$match": {"status": {"$nin": ["cancelled", "returned"]}}},
        {"$group": {
            "_id": "$buyer_name",
            "last_order": {"$max": "$created_at"},
            "first_order": {"$min": "$created_at"},
            "order_count": {"$sum": 1},
            "total_spent": {"$sum": {"$ifNull": ["$total_amount", 0]}},
            "platforms": {"$addToSet": "$platform"}
        }},
        {"$match": {"_id": {"$ne": None}}},
        {"$sort": {"last_order": -1}},
        {"$limit": 200}
    ]

    customers = []
    async for c in db.marketing_orders.aggregate(pipeline):
        last_dt = c["last_order"]
        if hasattr(last_dt, 'tzinfo') and last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        first_dt = c["first_order"]
        if hasattr(first_dt, 'tzinfo') and first_dt.tzinfo is None:
            first_dt = first_dt.replace(tzinfo=timezone.utc)

        recency_days = (now - last_dt).days
        tenure_days = max((now - first_dt).days, 1)
        freq_per_month = c["order_count"] / max(tenure_days / 30, 1)

        # RFM scoring (1–5)
        r = 5 if recency_days <= 14 else 4 if recency_days <= 30 else 3 if recency_days <= 60 else 2 if recency_days <= 90 else 1
        f = 5 if c["order_count"] >= 10 else 4 if c["order_count"] >= 5 else 3 if c["order_count"] >= 3 else 2 if c["order_count"] >= 2 else 1
        m = 5 if c["total_spent"] >= 2000000 else 4 if c["total_spent"] >= 1000000 else 3 if c["total_spent"] >= 500000 else 2 if c["total_spent"] >= 200000 else 1
        rfm = r + f + m

        # Churn risk
        if rfm >= 12:
            risk = "low"
        elif rfm >= 8:
            risk = "medium"
        elif rfm >= 5:
            risk = "high"
        else:
            risk = "critical"

        customers.append({
            "customer": c["_id"],
            "recency_days": recency_days,
            "order_count": c["order_count"],
            "total_spent_rp": round(c["total_spent"]),
            "freq_per_month": round(freq_per_month, 1),
            "r_score": r, "f_score": f, "m_score": m,
            "rfm_total": rfm,
            "churn_risk": risk,
            "platforms": c["platforms"]
        })

    if not customers:
        # Demo data
        import random
        random.seed(42)
        names = ["Ayu Sari", "Budi Santoso", "Citra Dewi", "Deni Rahman", "Eka Putri",
                 "Fani Lestari", "Gilang Pratama", "Hana Safitri", "Irwan Setiawan", "Joko Widodo",
                 "Kartika Sari", "Lukman Hakim", "Maya Indah", "Nurul Hidayah", "Oscar Pratama"]
        for name in names:
            rec_days = random.choice([5, 15, 35, 55, 80, 120, 150, 200])
            cnt = random.randint(1, 15)
            spent = random.randint(100000, 3000000)
            r = 5 if rec_days <= 14 else 4 if rec_days <= 30 else 3 if rec_days <= 60 else 2 if rec_days <= 90 else 1
            f = 5 if cnt >= 10 else 4 if cnt >= 5 else 3 if cnt >= 3 else 2 if cnt >= 2 else 1
            m = 5 if spent >= 2000000 else 4 if spent >= 1000000 else 3 if spent >= 500000 else 2 if spent >= 200000 else 1
            rfm = r + f + m
            risk = "low" if rfm >= 12 else "medium" if rfm >= 8 else "high" if rfm >= 5 else "critical"
            customers.append({"customer": name, "recency_days": rec_days, "order_count": cnt,
                              "total_spent_rp": spent, "freq_per_month": round(cnt / 3, 1),
                              "r_score": r, "f_score": f, "m_score": m, "rfm_total": rfm,
                              "churn_risk": risk, "platforms": ["shopee"]})

    # Summary
    segments = {"low": [], "medium": [], "high": [], "critical": []}
    for c in customers:
        segments[c["churn_risk"]].append(c)

    # AI explanation for high/critical customers
    high_risk = [c for c in customers if c["churn_risk"] in ["high", "critical"]][:10]

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"churn-{uuid.uuid4().hex[:8]}",
        system_message="Kamu adalah customer retention specialist untuk brand fashion Indonesia. Berikan rekomendasi retensi yang praktis dan empati. Respond only with valid JSON."
    ).with_model("openai", "gpt-4o-mini")

    prompt = (
        f"Data customer berisiko churn (high/critical) dari CV Dewi Aditya (fashion brand):\n"
        f"{json.dumps(high_risk, ensure_ascii=False, indent=2)}\n\n"
        f"Summary segment: low={len(segments['low'])}, medium={len(segments['medium'])}, high={len(segments['high'])}, critical={len(segments['critical'])}\n\n"
        f"Return JSON persis:\n"
        f"{{\"segment_insights\": {{"
        f"  \"critical\": \"insight 1-2 kalimat\","
        f"  \"high\": \"insight 1-2 kalimat\","
        f"  \"medium\": \"insight 1-2 kalimat\","
        f"  \"low\": \"insight 1-2 kalimat\""
        f"}},"
        f"\"customer_actions\": ["
        f"  {{\"customer\": \"nama\", \"risk\": \"critical\", \"action\": \"aksi retensi konkret\", \"channel\": \"WA/Email/push\", \"message_template\": \"template pesan Bahasa Indonesia\"}}"
        f"],"
        f"\"general_strategy\": \"strategi retensi umum 2-3 kalimat\","
        f"\"quick_wins\": [\"aksi cepat 1\", \"aksi cepat 2\"]}}"
    )

    ai_result = {}
    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        ai_result = json.loads(clean)
    except Exception as e:
        logger.error(f"Churn AI error: {e}")
        ai_result = {"general_strategy": "Error AI. Data RFM tersedia.", "quick_wins": []}

    # Build action map
    action_map = {a["customer"]: a for a in ai_result.get("customer_actions", [])}
    for c in customers:
        if c["customer"] in action_map:
            c["ai_action"] = action_map[c["customer"]].get("action")
            c["ai_channel"] = action_map[c["customer"]].get("channel")
            c["ai_template"] = action_map[c["customer"]].get("message_template")

    # Upsert churn scores
    for c in customers:
        await db.marketing_churn_scores.update_one(
            {"customer": c["customer"]},
            {"$set": {**c, "analyzed_at": _now()}},
            upsert=True
        )

    return ok(data={
        "summary": {
            "total_customers": len(customers),
            "segments": {k: len(v) for k, v in segments.items()},
            "segment_insights": ai_result.get("segment_insights", {}),
            "general_strategy": ai_result.get("general_strategy", ""),
            "quick_wins": ai_result.get("quick_wins", [])
        },
        "customers": serialize(customers)
    }, meta={"analyzed_at": _now().isoformat()})


@router.get("/churn/scores")
async def get_churn_scores(
    request: Request,
    risk: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(30)
):
    await require_auth(request)
    db = get_db()
    filt = {}
    if risk:
        filt["churn_risk"] = risk
    total = await db.marketing_churn_scores.count_documents(filt)
    skip = (page - 1) * page_size
    docs = await db.marketing_churn_scores.find(filt).sort("rfm_total", 1).skip(skip).limit(page_size).to_list(page_size)
    return ok(data={"customers": serialize(docs)}, meta={"total": total, "page": page})


# ═══════════════════════════════════════════════════════════════════════════
#  PHASE 5C — A/B TESTING
# ═══════════════════════════════════════════════════════════════════════════

class ABExperimentIn(BaseModel):
    name: str
    hypothesis: str
    test_type: str = "content_hook"    # content_hook | pricing | discount | product_title
    platform: str = "tiktok"
    variants: List[dict] = Field(default=[])
    goal_metric: str = "conversion"    # conversion | ctr | engagement
    duration_days: int = 7


class ABResultIn(BaseModel):
    variant_id: str
    views: Optional[int] = 0
    clicks: Optional[int] = 0
    orders: Optional[int] = 0
    revenue_rp: Optional[float] = 0
    engagement: Optional[float] = 0


@router.post("/ab-tests")
async def create_ab_test(payload: ABExperimentIn, request: Request):
    await require_auth(request)
    db = get_db()

    variants = []
    for i, v in enumerate(payload.variants):
        variants.append({
            "id": str(uuid.uuid4()),
            "label": v.get("label", f"Variant {chr(65+i)}"),
            "content": v.get("content", ""),
            "views": 0, "clicks": 0, "orders": 0, "revenue_rp": 0, "engagement": 0,
            "ctr": 0.0, "conversion_rate": 0.0
        })

    if not variants:
        # Default 2 blank variants
        variants = [
            {"id": str(uuid.uuid4()), "label": "Variant A", "content": "", "views": 0, "clicks": 0, "orders": 0, "revenue_rp": 0, "engagement": 0, "ctr": 0.0, "conversion_rate": 0.0},
            {"id": str(uuid.uuid4()), "label": "Variant B", "content": "", "views": 0, "clicks": 0, "orders": 0, "revenue_rp": 0, "engagement": 0, "ctr": 0.0, "conversion_rate": 0.0}
        ]

    start_date = _now()
    end_date = start_date + timedelta(days=payload.duration_days)

    doc = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "hypothesis": payload.hypothesis,
        "test_type": payload.test_type,
        "platform": payload.platform,
        "goal_metric": payload.goal_metric,
        "duration_days": payload.duration_days,
        "status": "draft",
        "variants": variants,
        "winner_variant_id": None,
        "winner_reason": None,
        "start_date": start_date,
        "end_date": end_date,
        "created_at": _now(),
        "updated_at": _now()
    }
    await db.marketing_ab_experiments.insert_one(doc)
    doc.pop("_id", None)
    return ok(data=serialize(doc))


@router.get("/ab-tests")
async def list_ab_tests(
    request: Request,
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20)
):
    await require_auth(request)
    db = get_db()
    filt = {}
    if status:
        filt["status"] = status
    total = await db.marketing_ab_experiments.count_documents(filt)
    skip = (page - 1) * page_size
    docs = await db.marketing_ab_experiments.find(filt).sort("created_at", -1).skip(skip).limit(page_size).to_list(page_size)
    return ok(data={"experiments": serialize(docs)}, meta={"total": total})


@router.get("/ab-tests/{exp_id}")
async def get_ab_test(exp_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.marketing_ab_experiments.find_one({"id": exp_id})
    if not doc:
        raise HTTPException(404, "Experiment tidak ditemukan")
    return ok(data=serialize(doc))


@router.patch("/ab-tests/{exp_id}/status")
async def update_ab_status(
    exp_id: str, request: Request,
    new_status: str = Query(...)
):
    await require_auth(request)
    db = get_db()
    valid = ["draft", "running", "paused", "concluded"]
    if new_status not in valid:
        raise HTTPException(400, f"Status harus salah satu dari {valid}")
    doc = await db.marketing_ab_experiments.find_one({"id": exp_id})
    if not doc:
        raise HTTPException(404, "Experiment tidak ditemukan")
    await db.marketing_ab_experiments.update_one(
        {"id": exp_id},
        {"$set": {"status": new_status, "updated_at": _now()}}
    )
    return ok(data={"status": new_status})


@router.post("/ab-tests/{exp_id}/record")
async def record_ab_result(exp_id: str, payload: ABResultIn, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.marketing_ab_experiments.find_one({"id": exp_id})
    if not doc:
        raise HTTPException(404, "Experiment tidak ditemukan")

    variants = doc.get("variants", [])
    updated = False
    for v in variants:
        if v["id"] == payload.variant_id:
            v["views"]     = payload.views or 0
            v["clicks"]    = payload.clicks or 0
            v["orders"]    = payload.orders or 0
            v["revenue_rp"]= payload.revenue_rp or 0
            v["engagement"]= payload.engagement or 0
            v["ctr"]       = round(v["clicks"] / max(v["views"], 1) * 100, 2)
            v["conversion_rate"] = round(v["orders"] / max(v["clicks"], 1) * 100, 2)
            updated = True
            break

    if not updated:
        raise HTTPException(404, "Variant tidak ditemukan")
    await db.marketing_ab_experiments.update_one(
        {"id": exp_id}, {"$set": {"variants": variants, "updated_at": _now()}}
    )
    return ok(data={"message": "Hasil diperbarui"})


@router.post("/ab-tests/{exp_id}/conclude")
async def conclude_ab_test(exp_id: str, request: Request):
    """AI decides winner based on goal metric and data."""
    await require_auth(request)
    db = get_db()
    doc = await db.marketing_ab_experiments.find_one({"id": exp_id})
    if not doc:
        raise HTTPException(404, "Experiment tidak ditemukan")
    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi")

    variants = doc.get("variants", [])
    if not any(v.get("views", 0) > 0 for v in variants):
        raise HTTPException(400, "Belum ada data hasil yang diinput. Gunakan tombol 'Input Hasil' terlebih dahulu.")

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"ab-conclude-{uuid.uuid4().hex[:8]}",
        system_message="Kamu adalah analis marketing A/B testing untuk brand fashion Indonesia. Berikan kesimpulan yang jelas berdasarkan data. Respond only with valid JSON."
    ).with_model("openai", "gpt-4o-mini")

    prompt = (
        f"A/B Experiment: {doc['name']}\n"
        f"Hypothesis: {doc['hypothesis']}\n"
        f"Goal Metric: {doc['goal_metric']}\n"
        f"Test Type: {doc['test_type']} | Platform: {doc['platform']}\n\n"
        f"Data variants:\n{json.dumps(variants, ensure_ascii=False, indent=2)}\n\n"
        f"Tentukan pemenang berdasarkan goal metric ({doc['goal_metric']}). "
        f"Jika tidak ada perbedaan signifikan (< 5%), nyatakan inconclusive.\n\n"
        f"Return JSON persis:\n"
        f"{{\"winner_label\": \"Variant A atau label pemenang\", "
        f"\"winner_variant_id\": \"id variant\", "
        f"\"is_conclusive\": true, "
        f"\"confidence\": \"high|medium|low\", "
        f"\"winner_reason\": \"alasan 2-3 kalimat mengapa ini pemenang\", "
        f"\"improvement_pct\": 12.5, "
        f"\"key_insight\": \"insight utama dari eksperimen ini\", "
        f"\"recommendation\": \"rekomendasi langkah selanjutnya\"}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = "\n".join(clean.split("\n")[1:-1])
        result = json.loads(clean)
    except Exception as e:
        logger.error(f"AB conclude error: {e}")
        raise HTTPException(500, f"AI conclude gagal: {e}")

    await db.marketing_ab_experiments.update_one(
        {"id": exp_id},
        {"$set": {
            "status": "concluded",
            "winner_variant_id": result.get("winner_variant_id"),
            "winner_label": result.get("winner_label"),
            "winner_reason": result.get("winner_reason"),
            "is_conclusive": result.get("is_conclusive", True),
            "confidence": result.get("confidence"),
            "improvement_pct": result.get("improvement_pct"),
            "key_insight": result.get("key_insight"),
            "recommendation": result.get("recommendation"),
            "updated_at": _now()
        }}
    )
    return ok(data=serialize(result))


@router.patch("/ab-tests/{exp_id}/variants/{variant_id}")
async def update_variant_content(exp_id: str, variant_id: str, request: Request):
    """Update variant content (label, content text)."""
    await require_auth(request)
    body = await request.json()
    db = get_db()
    doc = await db.marketing_ab_experiments.find_one({"id": exp_id})
    if not doc:
        raise HTTPException(404, "Experiment tidak ditemukan")
    variants = doc.get("variants", [])
    for v in variants:
        if v["id"] == variant_id:
            if "label" in body:
                v["label"] = body["label"]
            if "content" in body:
                v["content"] = body["content"]
    await db.marketing_ab_experiments.update_one(
        {"id": exp_id}, {"$set": {"variants": variants, "updated_at": _now()}}
    )
    return ok(data={"message": "Variant diperbarui"})
