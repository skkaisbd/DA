"""
Ads Performance Dashboard — Backend Routes
Phase 3 Week 7: Manage imported ads campaign data (Meta, TikTok, Google Ads)
Gap 3 (2026-05): AI recommendations endpoint
"""
import uuid
import logging
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, Query, HTTPException
from database import get_db
from auth import require_auth
# F6 (sesi #9) — daftar & ringkasan WAJIB berlingkup toko (core/marketing_account_scope).
from core import marketing_account_scope as _scope
from ai_llm import LlmChat, UserMessage
import random

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/ads", tags=["marketing-ads"])

# ── Standardized Response Helper ──
def success_response(data=None, pagination=None, metadata=None):
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if pagination is not None:
        response["pagination"] = pagination
    if metadata is not None:
        response["metadata"] = metadata
    return response

def _now() -> datetime:
    return datetime.now(timezone.utc)

def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj

def _get_user(request: Request) -> dict:
    return getattr(request.state, "user", {}) or {}

# ── Seed Demo Data ──
async def seed_ads_if_empty():
    """Auto-seed realistic ads campaign data if collection is empty."""
    db = get_db()
    if await db.marketing_ads_data.count_documents({}) > 0:
        return
    
    # F14 — iklan demo dulu TIDAK punya `account_id` sama sekali (25/25 kosong),
    # jadi biaya iklan tidak bisa dibandingkan dengan omzet toko mana pun.
    # `platform` = platform TOKO (konsisten dengan modul lain); saluran iklannya
    # disimpan terpisah di `ad_platform` karena Shopee Ads ≠ Meta Ads.
    from core import marketing_account_scope as _scope
    _accounts = await _scope.seed_account_pool(db)
    ad_platforms = ["shopee_ads", "tiktok_ads", "meta_ads", "google_ads"]
    campaign_names = [
        "Summer Fashion Collection",
        "Flash Sale Weekend",
        "New Arrival Promo",
        "Brand Awareness Q1",
        "Retargeting Campaign",
        "Lookalike Audience Test",
        "Product Launch - Kaos Premium"
    ]
    
    ads_records = []
    for i in range(25):  # 25 campaign snapshots
        account = random.choice(_accounts)
        platform = account.get("platform", "shopee")
        ad_platform = random.choice(ad_platforms)
        campaign = random.choice(campaign_names)
        date = _now() - timedelta(days=random.randint(1, 60))
        
        # F14 — angka demo lama tidak masuk akal (impresi ratusan juta, ROAS ribuan
        # kali) sehingga layar ROAS/CPA tidak bisa dipakai menilai apa pun. Sekarang
        # diturunkan dari CPM yang wajar untuk pasar Indonesia.
        spend = random.uniform(300000, 3000000)
        cpm = random.uniform(8000, 25000)                  # biaya per 1.000 impresi
        impressions = max(1, int(spend / cpm * 1000))
        clicks = int(impressions * random.uniform(0.008, 0.035))   # CTR 0,8-3,5%
        conversions = int(clicks * random.uniform(0.01, 0.06))     # CVR 1-6%
        revenue = conversions * random.uniform(70000, 220000)      # AOV
        
        ctr = (clicks / impressions * 100) if impressions > 0 else 0
        cpa = (spend / conversions) if conversions > 0 else 0
        roas = (revenue / spend) if spend > 0 else 0
        
        ads_records.append({
            "id": str(uuid.uuid4()),
            "platform": platform,
            "ad_platform": ad_platform,
            "account_id": account["id"],
            "account_name": account.get("account_name", ""),
            "campaign_name": f"{campaign} - {ad_platform.upper()}",
            "campaign_id": f"CMP-{uuid.uuid4().hex[:8]}",
            "date": date,
            "spend": round(spend, 2),
            "impressions": impressions,
            "clicks": clicks,
            "conversions": conversions,
            "revenue": round(revenue, 2),
            "ctr": round(ctr, 2),
            "cpa": round(cpa, 2),
            "roas": round(roas, 2),
            "status": "active" if random.random() > 0.3 else "paused",
            # F14 — penanda asal-usul: sebelum ini baris demo tidak bisa dibedakan
            # dari baris asli, sehingga migrasi harus menebak. Sekarang eksplisit.
            "_seed_origin": True,
            "created_by": "system",
            "created_at": date,
            "updated_at": date
        })
    
    if ads_records:
        await db.marketing_ads_data.insert_many(ads_records)
        try:
            await db.marketing_ads_data.create_index("id", unique=True, sparse=True)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        try:
            await db.marketing_ads_data.create_index("platform")
            await db.marketing_ads_data.create_index("campaign_id")
            await db.marketing_ads_data.create_index("date")
            await db.marketing_ads_data.create_index("status")
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        logger.info(f"[seed] Inserted {len(ads_records)} ads campaign records")

# ── Endpoints ──

@router.get("/summary")
async def ads_summary(request: Request,
                      account_id: Optional[str] = Query(None)):
    user = await require_auth(request)
    db = get_db()
    await seed_ads_if_empty()

    # F14 — ringkasan harus bisa dilingkupi toko yang sama dengan tabelnya.
    # F6 (sesi #9) — tanpa filter toko, staf berlingkup hanya menjumlah tokonya.
    _m = await _scope.scope_filter(db, user, {"account_id": account_id} if account_id else None)
    pipeline = ([{"$match": _m}] if _m else []) + [
        {"$group": {
            "_id": None,
            "total_spend": {"$sum": "$spend"},
            "total_revenue": {"$sum": "$revenue"},
            "total_impressions": {"$sum": "$impressions"},
            "total_clicks": {"$sum": "$clicks"},
            "total_conversions": {"$sum": "$conversions"},
            "campaigns": {"$sum": 1}
        }}
    ]
    
    result = await db.marketing_ads_data.aggregate(pipeline).to_list(1)
    stats = result[0] if result else {
        "total_spend": 0, "total_revenue": 0, "total_impressions": 0,
        "total_clicks": 0, "total_conversions": 0, "campaigns": 0
    }
    
    overall_roas = (stats["total_revenue"] / stats["total_spend"]) if stats["total_spend"] > 0 else 0
    overall_ctr = (stats["total_clicks"] / stats["total_impressions"] * 100) if stats["total_impressions"] > 0 else 0
    overall_cpa = (stats["total_spend"] / stats["total_conversions"]) if stats["total_conversions"] > 0 else 0
    
    # By platform
    platform_pipeline = [
        {"$group": {
            "_id": "$platform",
            "spend": {"$sum": "$spend"},
            "revenue": {"$sum": "$revenue"},
            "campaigns": {"$sum": 1}
        }}
    ]
    by_platform = {}
    async for doc in db.marketing_ads_data.aggregate(platform_pipeline):
        by_platform[doc["_id"]] = {
            "spend": doc["spend"],
            "revenue": doc["revenue"],
            "campaigns": doc["campaigns"],
            "roas": round((doc["revenue"] / doc["spend"]) if doc["spend"] > 0 else 0, 2)
        }
    
    return success_response(data={
        "total_spend": stats["total_spend"],
        "total_revenue": stats["total_revenue"],
        "total_campaigns": stats["campaigns"],
        "overall_roas": round(overall_roas, 2),
        "overall_ctr": round(overall_ctr, 2),
        "overall_cpa": round(overall_cpa, 2),
        "total_conversions": stats["total_conversions"],
        "by_platform": by_platform
    })

@router.get("/campaigns")
async def list_campaigns(
    request: Request,
    account_id: Optional[str] = Query(None, description="F14 — filter per toko"),
    platform: Optional[str] = Query(None),
    ad_platform: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=10, le=100)
):
    user = await require_auth(request)
    db = get_db()
    await seed_ads_if_empty()

    query = {}
    if account_id:
        query["account_id"] = account_id
    else:
        query = await _scope.scope_filter(db, user, query)
    if platform:
        query["platform"] = platform
    if ad_platform:
        query["ad_platform"] = ad_platform
    if status:
        query["status"] = status

    total = await db.marketing_ads_data.count_documents(query)
    skip = (page - 1) * page_size
    
    campaigns = await db.marketing_ads_data.find(query).sort("date", -1).skip(skip).limit(page_size).to_list(page_size)
    
    return success_response(
        data={"campaigns": serialize(campaigns)},
        pagination={
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size
        }
    )

@router.get("/performance-trend")
async def performance_trend(
    request: Request,
    days: int = Query(30, ge=7, le=90)
):
    user = await require_auth(request)
    db = get_db()
    await seed_ads_if_empty()

    start_dt = _now() - timedelta(days=days)

    pipeline = [
        {"$match": await _scope.scope_filter(db, user, {"date": {"$gte": start_dt}})},
        {"$group": {
            "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
            "spend": {"$sum": "$spend"},
            "revenue": {"$sum": "$revenue"},
            "conversions": {"$sum": "$conversions"}
        }},
        {"$sort": {"_id": 1}}
    ]
    
    trend = []
    async for doc in db.marketing_ads_data.aggregate(pipeline):
        roas = (doc["revenue"] / doc["spend"]) if doc["spend"] > 0 else 0
        trend.append({
            "date": doc["_id"],
            "spend": doc["spend"],
            "revenue": doc["revenue"],
            "conversions": doc["conversions"],
            "roas": round(roas, 2)
        })
    
    return success_response(data={"trend": trend}, metadata={"days": days})


@router.post("/ai-recommendations")
async def get_ai_recommendations(request: Request):
    """
    AI-generated recommendations untuk campaign optimization.
    Analisis ROAS, CTR, CPA dan berikan saran konkret per campaign.
    """
    await require_auth(request)
    db = get_db()
    await seed_ads_if_empty()

    if not EMERGENT_LLM_KEY:
        raise HTTPException(500, "AI tidak dikonfigurasi")

    # Ambil data campaign terakhir (max 20)
    campaigns = await db.marketing_ads_data.find({}).sort("date", -1).limit(20).to_list(20)

    if not campaigns:
        return success_response(data={"recommendations": [], "summary": "Belum ada data campaign."})

    # Build context
    camp_summary = []
    for c in campaigns:
        camp_summary.append({
            "nama": c.get("campaign_name", ""),
            "platform": c.get("platform", ""),
            "status": c.get("status", ""),
            "spend_rp": round(c.get("spend", 0)),
            "revenue_rp": round(c.get("revenue", 0)),
            "roas": c.get("roas", 0),
            "ctr_pct": c.get("ctr", 0),
            "cpa_rp": round(c.get("cpa", 0)),
            "conversions": c.get("conversions", 0)
        })

    # Aggregate platform stats
    platform_stats = {}
    for c in campaigns:
        p = c.get("platform", "unknown")
        if p not in platform_stats:
            platform_stats[p] = {"spend": 0, "revenue": 0, "campaigns": 0}
        platform_stats[p]["spend"] += c.get("spend", 0)
        platform_stats[p]["revenue"] += c.get("revenue", 0)
        platform_stats[p]["campaigns"] += 1
    for p in platform_stats:
        s = platform_stats[p]
        s["roas"] = round(s["revenue"] / s["spend"], 2) if s["spend"] > 0 else 0

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"ads-rec-{uuid.uuid4().hex[:8]}",
        system_message=(
            "Kamu adalah konsultan ads performance untuk brand fashion Indonesia. "
            "Berikan rekomendasi yang spesifik dan actionable per campaign. "
            "Respond only with valid JSON."
        )
    ).with_model("openai", "gpt-4o-mini")

    prompt = (
        f"Data ads campaign CV Dewi Aditya (fashion brand Indonesia):\n"
        f"Campaign list: {json.dumps(camp_summary, ensure_ascii=False)}\n"
        f"Platform summary: {json.dumps(platform_stats, ensure_ascii=False)}\n\n"
        f"Analisis dan berikan rekomendasi optimasi. Return JSON persis:\n"
        f"{{\"recommendations\": ["
        f"  {{\"type\": \"pause|scale_up|optimize|budget_shift|creative_refresh\", "
        f"  \"campaign\": \"nama campaign atau 'ALL'\", "
        f"  \"platform\": \"platform\", "
        f"  \"priority\": \"urgent|high|medium|low\", "
        f"  \"action\": \"aksi konkret yang harus dilakukan\", "
        f"  \"reason\": \"alasan berdasarkan data (ROAS/CTR/CPA)\", "
        f"  \"expected_impact\": \"dampak yang diharapkan\"}}], "
        f"\"best_platform\": \"platform terbaik\", "
        f"\"worst_platform\": \"platform terburuk\", "
        f"\"overall_roas\": 2.5, "
        f"\"summary\": \"ringkasan 2-3 kalimat Bahasa Indonesia\", "
        f"\"budget_advice\": \"saran alokasi budget\"}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        result = json.loads(clean)
        return success_response(data=result, metadata={"campaigns_analyzed": len(campaigns)})
    except Exception as e:
        logger.error(f"Ads AI recommendations error: {e}")
        raise HTTPException(500, f"Rekomendasi AI gagal: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# F16 — CRUD BIAYA IKLAN (sebelumnya TIDAK ADA SAMA SEKALI)
# ══════════════════════════════════════════════════════════════════════════════
# Audit 2026-08-11: berkas ini hanya punya endpoint GET. Artinya biaya iklan
# **tidak bisa dimasukkan lewat aplikasi** — satu-satunya sumbernya adalah data
# demo yang tidak pernah bisa diperbarui. Semua layar ROAS/CPA/CTR karena itu
# menampilkan angka yang tidak ada hubungannya dengan belanja iklan sebenarnya.
# CTR/CPA/ROAS DIHITUNG SERVER supaya tidak ada dua versi angka yang beredar.
from pydantic import BaseModel, Field as _PField      # noqa: E402

AD_PLATFORMS = ("shopee_ads", "tiktok_ads", "meta_ads", "google_ads",
                "affiliate", "lainnya")
AD_STATUSES = ("active", "paused", "ended")


class AdsEntryIn(BaseModel):
    account_id: str                                   # F14 — lingkup toko WAJIB
    date: str
    campaign_name: str
    campaign_id: Optional[str] = ""
    ad_platform: Optional[str] = "shopee_ads"
    ad_type: Optional[str] = ""
    spend: float = _PField(0, ge=0)
    impressions: int = _PField(0, ge=0)
    clicks: int = _PField(0, ge=0)
    conversions: int = _PField(0, ge=0)
    revenue: float = _PField(0, ge=0)
    status: Optional[str] = "active"
    notes: Optional[str] = ""


class AdsEntryUpdate(BaseModel):
    date: Optional[str] = None
    campaign_name: Optional[str] = None
    campaign_id: Optional[str] = None
    ad_platform: Optional[str] = None
    ad_type: Optional[str] = None
    spend: Optional[float] = _PField(None, ge=0)
    impressions: Optional[int] = _PField(None, ge=0)
    clicks: Optional[int] = _PField(None, ge=0)
    conversions: Optional[int] = _PField(None, ge=0)
    revenue: Optional[float] = _PField(None, ge=0)
    status: Optional[str] = None
    notes: Optional[str] = None


def _ads_derived(doc: dict) -> dict:
    """CTR/CPA/ROAS selalu turunan — tidak pernah diketik.

    Kalau ketiganya boleh diisi manual, laporan efisiensi iklan akan berisi
    campuran angka hitungan dan angka ketikan tanpa cara membedakannya.
    """
    def n(k):
        try:
            return float(doc.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
    spend, imp, clicks = n("spend"), n("impressions"), n("clicks")
    conv, rev = n("conversions"), n("revenue")
    doc["ctr"] = round(clicks / imp * 100, 2) if imp else 0
    doc["cpc"] = round(spend / clicks, 2) if clicks else 0
    doc["cpa"] = round(spend / conv, 2) if conv else 0
    doc["roas"] = round(rev / spend, 2) if spend else 0
    doc["cvr"] = round(conv / clicks * 100, 2) if clicks else 0
    return doc


def _parse_ads_date(raw: str) -> datetime:
    from core.marketing_import_engine import parse_date
    d, err = parse_date(raw)
    if err or d is None:
        raise HTTPException(400, f"Tanggal tidak dikenali: {err or raw}")
    return d


@router.get("/campaigns/{entry_id}")
async def get_ads_entry(entry_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    doc = await db.marketing_ads_data.find_one({"id": entry_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Data iklan tidak ditemukan")
    return success_response(data=serialize(doc))


@router.post("/campaigns", status_code=201)
async def create_ads_entry(body: AdsEntryIn, request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    from core import marketing_account_scope as _scope

    account = await _scope.require_account(db, body.account_id)
    if body.ad_platform and body.ad_platform not in AD_PLATFORMS:
        raise HTTPException(400, f"ad_platform harus salah satu: "
                                 f"{', '.join(AD_PLATFORMS)}")
    if body.status and body.status not in AD_STATUSES:
        raise HTTPException(400, f"status harus salah satu: {', '.join(AD_STATUSES)}")

    doc = body.dict()
    doc.pop("account_id", None)
    doc["date"] = _parse_ads_date(body.date)
    doc["id"] = str(uuid.uuid4())
    doc["campaign_id"] = body.campaign_id or f"CMP-{uuid.uuid4().hex[:8].upper()}"
    _scope.stamp_account(doc, account)
    _ads_derived(doc)
    doc["created_at"] = _now()
    doc["updated_at"] = _now()
    doc["created_by"] = user.get("email", "system")
    await db.marketing_ads_data.insert_one(dict(doc))
    doc.pop("_id", None)
    return success_response(data=serialize(doc))


@router.put("/campaigns/{entry_id}")
async def update_ads_entry(entry_id: str, body: AdsEntryUpdate, request: Request):
    await require_auth(request)
    user = getattr(request.state, "user", {}) or {}
    db = get_db()
    existing = await db.marketing_ads_data.find_one({"id": entry_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Data iklan tidak ditemukan")

    upd = {k: v for k, v in body.dict().items() if v is not None}
    if "date" in upd:
        upd["date"] = _parse_ads_date(upd["date"])
    if "ad_platform" in upd and upd["ad_platform"] not in AD_PLATFORMS:
        raise HTTPException(400, f"ad_platform harus salah satu: "
                                 f"{', '.join(AD_PLATFORMS)}")
    if "status" in upd and upd["status"] not in AD_STATUSES:
        raise HTTPException(400, f"status harus salah satu: {', '.join(AD_STATUSES)}")
    merged = {**existing, **upd}
    _ads_derived(merged)
    for k in ("ctr", "cpc", "cpa", "roas", "cvr"):
        upd[k] = merged[k]
    upd["updated_at"] = _now()
    upd["updated_by"] = user.get("email", "system")
    await db.marketing_ads_data.update_one({"id": entry_id}, {"$set": upd})
    return success_response(data=serialize({**existing, **upd}))


@router.delete("/campaigns/{entry_id}")
async def delete_ads_entry(entry_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_ads_data.delete_one({"id": entry_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Data iklan tidak ditemukan")
    return {"success": True, "message": "Data iklan dihapus"}


@router.get("/platforms")
async def ads_reference_lists(request: Request):
    """Daftar acuan dari SERVER — supaya layar tidak menyalin daftarnya sendiri.

    Audit menemukan layar marketing menyalin daftar platform/jenis diskon ke
    dalam kode JS. Begitu backend menambah satu pilihan, layar tidak tahu, dan
    data yang diketik staf jadi tidak cocok dengan validasi server.
    """
    await require_auth(request)
    return {"ok": True, "ad_platforms": list(AD_PLATFORMS),
            "statuses": list(AD_STATUSES)}
