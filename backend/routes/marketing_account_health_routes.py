"""
Account Health Dashboard — Backend Routes
Phase 3 Week 6: Monitor kesehatan akun marketplace dari screenshot OCR
Gap 1 (2026-05): OCR screenshot endpoint via GPT-4o Vision
"""
import uuid
import logging
import os
import base64
import json
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, Field
from database import get_db
# F6 (sesi #10) — kesehatan akun adalah data PER TOKO: staf pemegang satu toko
# tidak boleh membaca skor & pelanggaran toko lain.
from core import marketing_account_scope as _scope
from auth import require_auth
from ai_llm import LlmChat, UserMessage, ImageContent
import random

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/health", tags=["marketing-health"])

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
async def seed_health_if_empty():
    """Auto-seed realistic account health snapshots if collection is empty.
    Menggunakan real platform accounts jika ada, fallback ke data dummy.
    """
    db = get_db()
    if await db.marketing_account_health.count_documents({}) > 0:
        return

    # Gunakan platform accounts nyata jika ada
    real_accs = await db.marketing_platform_accounts.find(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1}
    ).to_list(50)

    if real_accs:
        accounts = [{"id": a["id"], "platform": a["platform"], "name": a["account_name"]} for a in real_accs]
    else:
        accounts = [
            {"id": None, "platform": "shopee",    "name": "BajuKekinian_Official"},
            {"id": None, "platform": "tiktok",    "name": "fashionbae.id"},
            {"id": None, "platform": "tokopedia", "name": "Garmen Stylish Shop"},
        ]
    
    health_records = []
    for account in accounts:
        # Generate 10 snapshots per account (weekly for ~2.5 months)
        for i in range(10):
            snapshot_date = _now() - timedelta(weeks=10-i)
            
            # Simulate gradual improvement/decline
            trend = random.choice(["improving", "stable", "declining"])
            
            if trend == "improving":
                ses_score = 70 + (i * 2)  # improving over time
                late_shipment = max(0.5, 5 - (i * 0.3))
                cancellation = max(0.3, 3 - (i * 0.2))
            elif trend == "declining":
                ses_score = 90 - (i * 1.5)
                late_shipment = 1 + (i * 0.4)
                cancellation = 0.5 + (i * 0.3)
            else:  # stable
                ses_score = random.uniform(75, 85)
                late_shipment = random.uniform(1, 3)
                cancellation = random.uniform(0.5, 1.5)
            
            health_records.append({
                "id": str(uuid.uuid4()),
                "platform": account["platform"],
                "account_id": account.get("id"),
                "account_name": account["name"],
                "snapshot_date": snapshot_date,
                "ses_score": round(ses_score, 1),
                "late_shipment_rate": round(late_shipment, 2),
                "cancellation_rate": round(cancellation, 2),
                "response_rate": round(random.uniform(85, 98), 1),
                "response_time_hours": round(random.uniform(0.5, 4), 1),
                "order_defect_rate": round(random.uniform(0.1, 2), 2),
                "return_rate": round(random.uniform(1, 5), 2),
                "rating_score": round(random.uniform(4.3, 4.9), 2),
                "total_reviews": random.randint(500, 5000),
                "status": "healthy" if ses_score >= 75 and late_shipment < 3 and cancellation < 2 else "warning" if ses_score >= 60 else "critical",
                "notes": [],
                "created_at": snapshot_date,
                "updated_at": snapshot_date
            })
    
    if health_records:
        await db.marketing_account_health.insert_many(health_records)
        try:
            await db.marketing_account_health.create_index("id", unique=True, sparse=True)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        try:
            await db.marketing_account_health.create_index("platform")
            await db.marketing_account_health.create_index("account_name")
            await db.marketing_account_health.create_index("snapshot_date")
            await db.marketing_account_health.create_index("status")
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)
        logger.info(f"[seed] Inserted {len(health_records)} account health snapshots")

# ── Endpoints ──

@router.get("/summary")
async def health_summary(request: Request):
    user = await require_auth(request)
    db = get_db()
    await seed_health_if_empty()

    # Get latest snapshot per account — F6: hanya toko yang boleh dilihat pemakai
    pipeline = [
        {"$match": await _scope.scope_filter(db, user, {})},
        {"$sort": {"snapshot_date": -1}},
        {"$group": {
            "_id": {"platform": "$platform", "account": "$account_name"},
            "latest": {"$first": "$$ROOT"}
        }}
    ]
    
    latest_snapshots = []
    async for doc in db.marketing_account_health.aggregate(pipeline):
        latest_snapshots.append(doc["latest"])
    
    # Calculate summary
    total_accounts = len(latest_snapshots)
    healthy = sum(1 for s in latest_snapshots if s.get("status") == "healthy")
    warning = sum(1 for s in latest_snapshots if s.get("status") == "warning")
    critical = sum(1 for s in latest_snapshots if s.get("status") == "critical")
    
    avg_ses = sum(s.get("ses_score", 0) for s in latest_snapshots) / max(total_accounts, 1)
    avg_late_ship = sum(s.get("late_shipment_rate", 0) for s in latest_snapshots) / max(total_accounts, 1)
    
    by_platform = {}
    for snap in latest_snapshots:
        plat = snap.get("platform", "unknown")
        if plat not in by_platform:
            by_platform[plat] = {"count": 0, "healthy": 0, "warning": 0, "critical": 0}
        by_platform[plat]["count"] += 1
        by_platform[plat][snap.get("status", "healthy")] += 1
    
    return success_response(data={
        "total_accounts": total_accounts,
        "healthy": healthy,
        "warning": warning,
        "critical": critical,
        "avg_ses_score": round(avg_ses, 1),
        "avg_late_shipment_rate": round(avg_late_ship, 2),
        "by_platform": by_platform,
        "latest_snapshots": serialize(latest_snapshots)
    })

@router.get("/timeline")
async def health_timeline(
    request: Request,
    platform: Optional[str] = Query(None),
    account: Optional[str] = Query(None),
    days: int = Query(90, ge=7, le=365)
):
    user = await require_auth(request)
    db = get_db()
    await seed_health_if_empty()

    query = await _scope.scope_filter(
        db, user, {"snapshot_date": {"$gte": _now() - timedelta(days=days)}})
    if platform:
        query["platform"] = platform
    if account:
        query["account_name"] = account
    
    snapshots = await db.marketing_account_health.find(query).sort("snapshot_date", 1).to_list(1000)
    
    return success_response(
        data={"snapshots": serialize(snapshots)},
        metadata={"days": days, "count": len(snapshots)}
    )

@router.post("/ocr-screenshot")
async def ocr_account_health_screenshot(
    request: Request,
    file: UploadFile = File(...),
    account_name: str = Form(default=""),
    platform: str = Form(default="shopee"),
    account_id: str = Form(default="")
):
    """
    Upload screenshot dari Shopee/TikTok Seller Center health page.
    AI (GPT-4o vision) extract semua metric otomatis.
    """
    await require_auth(request)
    get_db()

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI tidak dikonfigurasi (EMERGENT_LLM_KEY missing)")

    # Validate file type
    if file.content_type not in ["image/png", "image/jpeg", "image/jpg", "image/webp"]:
        raise HTTPException(400, "File harus berupa gambar (PNG/JPG/WEBP)")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10MB limit
        raise HTTPException(400, "Ukuran file maksimal 10MB")

    # Convert to base64 for GPT-4o vision
    b64 = base64.b64encode(content).decode("utf-8")
    mime = file.content_type or "image/jpeg"

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"health-ocr-{uuid.uuid4().hex[:8]}",
        system_message=(
            "Kamu adalah sistem OCR khusus untuk membaca screenshot dashboard kesehatan akun marketplace Indonesia "
            "(Shopee Seller Center atau TikTok Seller Center). "
            "Extract semua metric yang terlihat dengan akurat. Respond only with valid JSON."
        )
    ).with_model("openai", "gpt-4o")

    prompt = (
        "Ini screenshot dari dashboard kesehatan akun marketplace Indonesia. "
        "Extract semua metric yang terlihat. Jika metric tidak terlihat, isi null.\n\n"
        "Return JSON persis (angka tanpa satuan, persentase tanpa %):\n"
        "{\"ses_score\": 85.5, \"rating_score\": 4.8, \"response_rate\": 95.2, "
        "\"response_time_hours\": 1.5, \"late_shipment_rate\": 2.1, \"cancellation_rate\": 0.8, "
        "\"order_defect_rate\": 0.5, \"return_rate\": 1.2, \"total_reviews\": 1250, "
        "\"detected_platform\": \"shopee|tiktok|tokopedia\", "
        "\"detected_account\": \"nama akun jika terlihat atau null\", "
        "\"snapshot_date\": \"tanggal yang terlihat di screenshot atau null\", "
        "\"status\": \"healthy|warning|critical berdasarkan metric\", "
        "\"extraction_notes\": \"catatan jika ada metric yang tidak jelas\"}"
    )

    try:
        response = await chat.send_message(UserMessage(
            text=prompt,
            images=[ImageContent(data=b64, mime_type=mime)]
        ))
        clean = response.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1])
        extracted = json.loads(clean)
    except Exception as e:
        logger.error(f"OCR error: {e}")
        raise HTTPException(500, f"OCR gagal: {e}")

    # Use AI-detected values, fallback to form input
    det_platform = extracted.get("detected_platform") or platform
    det_account  = extracted.get("detected_account") or account_name or "Unknown Account"

    # Compute status if not provided by AI
    status = extracted.get("status", "healthy")
    ses = extracted.get("ses_score") or 0
    late = extracted.get("late_shipment_rate") or 0
    cancel = extracted.get("cancellation_rate") or 0
    if ses < 60 or late > 5 or cancel > 3:
        status = "critical"
    elif ses < 75 or late > 3 or cancel > 2:
        status = "warning"

    return success_response(data={
        "extracted": extracted,
        "preview": {
            "account_id": account_id or None,  # FK to master accounts (UUID)
            "platform": det_platform,
            "account_name": det_account,
            "ses_score": extracted.get("ses_score"),
            "rating_score": extracted.get("rating_score"),
            "late_shipment_rate": extracted.get("late_shipment_rate"),
            "cancellation_rate": extracted.get("cancellation_rate"),
            "response_rate": extracted.get("response_rate"),
            "response_time_hours": extracted.get("response_time_hours"),
            "order_defect_rate": extracted.get("order_defect_rate"),
            "return_rate": extracted.get("return_rate"),
            "total_reviews": extracted.get("total_reviews"),
            "status": status,
            "extraction_notes": extracted.get("extraction_notes", "")
        }
    })


class ManualSnapshotIn(BaseModel):
    account_id: Optional[str] = None  # FK to marketing_platform_accounts (UUID)
    platform: str = "shopee"
    account_name: str
    ses_score: Optional[float] = None
    rating_score: Optional[float] = None
    response_rate: Optional[float] = Field(default=None, ge=0)
    response_time_hours: Optional[float] = None
    late_shipment_rate: Optional[float] = None
    cancellation_rate: Optional[float] = None
    order_defect_rate: Optional[float] = Field(default=None, ge=0)
    return_rate: Optional[float] = Field(default=None, ge=0)
    total_reviews: Optional[int] = Field(default=None, ge=0)
    snapshot_date: Optional[str] = None
    notes: Optional[str] = None


@router.post("/manual-snapshot")
async def create_manual_snapshot(payload: ManualSnapshotIn, request: Request):
    """Simpan snapshot kesehatan akun secara manual (atau setelah OCR + edit).
    
    Jika account_id disediakan, sistem juga akan:
    1. Update health_score di master account (marketing_platform_accounts)
    2. Trigger _recalculate_health_score untuk konsistensi
    """
    await require_auth(request)
    db = get_db()

    ses = payload.ses_score or 0
    late = payload.late_shipment_rate or 0
    cancel = payload.cancellation_rate or 0

    if ses < 60 or late > 5 or cancel > 3:
        status = "critical"
    elif ses < 75 or late > 3 or cancel > 2:
        status = "warning"
    else:
        status = "healthy"

    snap_dt = _now()
    if payload.snapshot_date:
        try:
            snap_dt = datetime.fromisoformat(payload.snapshot_date).replace(tzinfo=timezone.utc)
        except Exception:
            logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    doc = {
        "id": str(uuid.uuid4()),
        "account_id": payload.account_id,  # FK to master account
        "platform": payload.platform,
        "account_name": payload.account_name,
        "snapshot_date": snap_dt,
        "ses_score": payload.ses_score,
        "rating_score": payload.rating_score,
        "response_rate": payload.response_rate,
        "response_time_hours": payload.response_time_hours,
        "late_shipment_rate": payload.late_shipment_rate,
        "cancellation_rate": payload.cancellation_rate,
        "order_defect_rate": payload.order_defect_rate,
        "return_rate": payload.return_rate,
        "total_reviews": payload.total_reviews,
        "status": status,
        "notes": [payload.notes] if payload.notes else [],
        "source": "manual",
        "created_at": _now(),
        "updated_at": _now()
    }
    await db.marketing_account_health.insert_one(doc)

    # Trigger health score recalc on master account if linked
    if payload.account_id:
        try:
            # Lazy import to avoid circular dependency
            from routes.marketing import _recalculate_health_score
            await _recalculate_health_score(db, payload.account_id)
        except Exception as e:
            # Silent fail (snapshot already saved, just log)
            logger.warning(f"Failed to recalc health score for account {payload.account_id}: {e}")

    return success_response(data={"id": doc["id"], "status": status, "message": "Snapshot berhasil disimpan"})


@router.get("/accounts")
async def list_accounts(request: Request):
    user = await require_auth(request)
    db = get_db()

    # Utamakan platform accounts nyata, fallback ke distinct dari health collection.
    # F6: daftar toko untuk pemilih di layar wajib berlingkup pemakai — pemilih yang
    # memuat toko orang lain hanya melahirkan 403 yang tak bisa dijelaskan.
    real_accounts = await _scope.visible_accounts(
        db, user, base={"status": "active"},
        projection={"_id": 0, "account_name": 1, "platform": 1}, limit=200)

    if real_accounts:
        account_names = [a["account_name"] for a in real_accounts]
        platforms = list(set(a["platform"] for a in real_accounts))
    else:
        await seed_health_if_empty()
        _sq = await _scope.scope_filter(db, user, {})
        account_names = await db.marketing_account_health.distinct("account_name", _sq)
        platforms = await db.marketing_account_health.distinct("platform", _sq)

    return success_response(data={
        "accounts":  account_names,
        "platforms": platforms
    })
