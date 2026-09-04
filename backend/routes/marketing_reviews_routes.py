"""
Rating & Review Management Module — Backend Routes
Phase 3 Week 13: Manajemen rating dan review produk dari berbagai platform
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel
from database import get_db
from auth import require_auth
# F6 (sesi #9) — daftar & ringkasan WAJIB berlingkup toko (core/marketing_account_scope).
from core import marketing_account_scope as _scope
from routes.shared import require_portal
import os
from ai_llm import LlmChat, UserMessage
import json

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/reviews", tags=["marketing-reviews"])

EMERGENT_LLM_KEY = os.environ.get("EMERGENT_LLM_KEY", "")

REVIEW_CATEGORIES = [
    "produk_tidak_sesuai_deskripsi",
    "produk_salah",
    "bahan_kurang_baik",
    "ukuran_tidak_sesuai",
    "warna_berbeda",
    "jahitan_cacat",
    "kualitas_bagus",
    "sesuai_ekspektasi",
    "tanpa_keterangan"
]

CATEGORY_LABELS = {
    "produk_tidak_sesuai_deskripsi": "Produk Tidak Sesuai Deskripsi",
    "produk_salah": "Produk Yang Dikirim Salah",
    "bahan_kurang_baik": "Bahan Kurang Baik",
    "ukuran_tidak_sesuai": "Ukuran Tidak Sesuai",
    "warna_berbeda": "Warna Berbeda",
    "jahitan_cacat": "Jahitan Cacat/Bolong",
    "kualitas_bagus": "Kualitas Bagus",
    "sesuai_ekspektasi": "Sesuai Ekspektasi",
    "tanpa_keterangan": "Tanpa Keterangan"
}

PLATFORMS = ["shopee", "tiktok", "tokopedia", "instagram"]

# ── Helpers ───────────────────────────────────────────────────────────────────
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

# ── Seed ─────────────────────────────────────────────────────────────────────
async def seed_reviews_if_empty():
    db = get_db()
    if await db.marketing_reviews.count_documents({}) > 0:
        return

    import random
    from datetime import timedelta
    
    products = [
        "Gamis Daluna Basic", "Khimar Syari Premium", "Tunik Busui Friendly",
        "Set Gamis + Khimar", "Outer Cardigan", "Rok Plisket Panjang",
        "Dress Casual", "Hijab Segiempat", "Inner Manset", "Celana Kulot"
    ]
    
    
    reviews_data = [
        # Rating rendah (1-2 bintang)
        {"rating": 1, "category": "ukuran_tidak_sesuai", "review": "terlalu kecil, ukuran XL seperti M beda sekali kecil"},
        {"rating": 2, "category": "produk_tidak_sesuai_deskripsi", "review": "Produk tidak sesuai deskripsi, warna berbeda"},
        {"rating": 1, "category": "bahan_kurang_baik", "review": "Kainnya lumayan tipis kecewa"},
        {"rating": 2, "category": "jahitan_cacat", "review": "jahitan kurang bagus, ada yang bolong"},
        {"rating": 1, "category": "ukuran_tidak_sesuai", "review": "terlalu sempit di bagian dada"},
        {"rating": 2, "category": "warna_berbeda", "review": "Beda warna dengan foto, lebih gelap"},
        # Rating sedang (3 bintang)
        {"rating": 3, "category": "sesuai_ekspektasi", "review": "Biasa saja, sesuai harga"},
        {"rating": 3, "category": "bahan_kurang_baik", "review": "Bahan tipis tapi masih oke lah"},
        # Rating tinggi (4-5 bintang)
        {"rating": 5, "category": "kualitas_bagus", "review": "Bahannya bagus, jahitan rapi, puas!"},
        {"rating": 5, "category": "sesuai_ekspektasi", "review": "Sesuai deskripsi, pengiriman cepat"},
        {"rating": 4, "category": "kualitas_bagus", "review": "Bagus, tapi agak panjang di lengan"},
        {"rating": 5, "category": "sesuai_ekspektasi", "review": "Recommended! Adem dan nyaman"},
        {"rating": 4, "category": "kualitas_bagus", "review": "Bahan premium, worth it"},
    ]
    
    # Gunakan platform accounts nyata jika ada
    real_accounts = await db.marketing_platform_accounts.find(
        {"status": "active"}, {"_id": 0, "id": 1, "account_name": 1, "platform": 1}
    ).to_list(50)
    seed_accounts = [(a["id"], a["account_name"], a["platform"]) for a in real_accounts] if real_accounts else [
        (None, "DA Official Shopee", "shopee"), (None, "Daluna TikTok Shop", "tiktok"), (None, "Garmen Tokopedia", "tokopedia")
    ]

    # F14 — ulasan demo memakai nomor pesanan karangan; sekarang diambil dari
    # order yang benar-benar ada supaya bisa ditelusuri ke transaksinya.
    _orders = await db.marketing_orders.find(
        {}, {"_id": 0, "order_id": 1, "account_id": 1, "account_name": 1,
             "platform": 1, "product_name": 1, "catalog_item_id": 1}).to_list(500)

    entries = []
    base = _now()
    
    for i in range(40):
        day_offset = random.randint(-30, 0)
        review_date = base + timedelta(days=day_offset)
        
        review_template = random.choice(reviews_data)
        _ord = random.choice(_orders) if _orders else None
        if _ord:
            acc_id = _ord.get("account_id")
            acc_name = _ord.get("account_name", "")
            acc_platform = _ord.get("platform", "")
        else:
            acc_id, acc_name, acc_platform = random.choice(seed_accounts)

        entries.append({
            "id": str(uuid.uuid4()),
            "date": review_date.date().isoformat(),
            "order_id": (_ord or {}).get("order_id", ""),
            "catalog_item_id": (_ord or {}).get("catalog_item_id"),
            "platform": acc_platform,
            "account_id": acc_id,
            "account_name": acc_name,
            "rating": review_template["rating"],
            "product": (_ord or {}).get("product_name") or random.choice(products),
            "category": review_template["category"],
            "category_label": CATEGORY_LABELS.get(review_template["category"], review_template["category"]),
            "review_text": review_template["review"],
            "screenshot_url": "",
            "response_text": "",
            "response_date": None,
            "status": "pending" if review_template["rating"] <= 2 else "reviewed",
            "created_by": "system",
            "created_at": _now(),
            "updated_at": _now(),
        })
    
    if entries:
        await db.marketing_reviews.insert_many(entries)
    logger.info(f"[marketing_reviews] seeded {len(entries)} entries")

# ── Models ───────────────────────────────────────────────────────────────────
class ReviewIn(BaseModel):
    account_id: Optional[str] = None  # UUID dari marketing_platform_accounts
    account_name: Optional[str] = None
    date: str
    order_id: str
    # F14 — `platform` TURUNAN dari akun, bukan diketik/dikirim layar.
    # Kalau boleh dikirim bebas, satu akun Shopee bisa punya baris
    # berplatform 'tiktok' dan laporan per platform ikut salah.
    platform: Optional[str] = None
    rating: int
    catalog_item_id: Optional[str] = None   # F15 — produk DIPILIH dari katalog
    product: Optional[str] = ""             # turunan dari item katalog
    category: Optional[str] = "tanpa_keterangan"
    review_text: str
    screenshot_url: Optional[str] = ""
    response_text: Optional[str] = ""

class ReviewUpdate(BaseModel):
    catalog_item_id: Optional[str] = None
    account_id: Optional[str] = None
    account_name: Optional[str] = None
    date: Optional[str] = None
    order_id: Optional[str] = None
    platform: Optional[str] = None
    rating: Optional[int] = None
    product: Optional[str] = None
    category: Optional[str] = None
    review_text: Optional[str] = None
    screenshot_url: Optional[str] = None
    response_text: Optional[str] = None
    status: Optional[str] = None

# ── F15 — PRODUK DIPILIH DARI KATALOG TOKO, BUKAN DIKETIK ────────────────────
# Sebelum ini `product` adalah teks bebas. Akibatnya "Gamis Daluna Basic" dan
# "Gamis Daluna basic" menjadi DUA produk di laporan, dan pertanyaan "produk mana
# yang paling banyak diretur / paling buruk ulasannya" tidak bisa dijawab karena
# angkanya terpecah. Sekarang layar mengirim `catalog_item_id`, dan nama produk
# serta SKU-nya diambil dari MASTER — tidak mungkin lagi beda ejaan.
async def _resolve_catalog_item(db, catalog_item_id: str, account_id: str) -> dict:
    """Item katalog WAJIB milik toko yang sama. Item toko lain ditolak, karena
    ulasan/retur toko A yang menunjuk produk toko B akan merusak dua laporan
    sekaligus tanpa terlihat."""
    item = await db.marketing_catalog_items.find_one({"id": catalog_item_id},
                                                     {"_id": 0})
    if not item:
        raise HTTPException(404, f"Item katalog '{catalog_item_id}' tidak ditemukan")
    if account_id and item.get("account_id") and item["account_id"] != account_id:
        raise HTTPException(400, "Item katalog itu bukan milik toko yang dipilih. "
                                 "Pilih produk dari katalog toko tersebut.")
    return item

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/categories")
async def get_categories(request: Request):
    await require_portal(request, "toko")  # RBAC read-guard (BUG-AUTH-1)
    return {"success": True, "categories": [{"value": k, "label": v} for k, v in CATEGORY_LABELS.items()]}

@router.get("/platforms")
async def get_platforms(request: Request):
    await require_portal(request, "toko")  # RBAC read-guard (BUG-AUTH-1)
    labels = {"shopee": "Shopee", "tiktok": "TikTok", "tokopedia": "Tokopedia", "instagram": "Instagram"}
    return {"success": True, "platforms": [{"value": p, "label": labels.get(p, p)} for p in PLATFORMS]}

@router.get("/summary")
async def get_summary(request: Request):
    user = await require_auth(request)
    await seed_reviews_if_empty()
    db = get_db()

    # F6 (sesi #9) — ringkasan ulasan WAJIB berlingkup toko.
    _s = await _scope.scope_filter(db, user, None)
    total = await db.marketing_reviews.count_documents(_s)
    pending = await db.marketing_reviews.count_documents({**_s, "status": "pending"})
    reviewed = await db.marketing_reviews.count_documents({**_s, "status": "reviewed"})

    # Rating distribution — ikut lingkup toko, kalau tidak "total" dan pecahannya
    # akan bercerita tentang dua himpunan yang berbeda.
    rating_1 = await db.marketing_reviews.count_documents({**_s, "rating": 1})
    rating_2 = await db.marketing_reviews.count_documents({**_s, "rating": 2})
    rating_3 = await db.marketing_reviews.count_documents({**_s, "rating": 3})
    rating_4 = await db.marketing_reviews.count_documents({**_s, "rating": 4})
    rating_5 = await db.marketing_reviews.count_documents({**_s, "rating": 5})

    # Average rating
    pipeline = ([{"$match": _s}] if _s else []) + [
        {"$group": {"_id": None, "avg_rating": {"$avg": "$rating"}}}]
    avg_result = await db.marketing_reviews.aggregate(pipeline).to_list(1)
    avg_rating = round(avg_result[0]["avg_rating"], 2) if avg_result else 0
    
    # Low rating count (1-2 stars)
    low_rating = rating_1 + rating_2
    
    # By platform
    pipeline_platform = ([{"$match": _s}] if _s else []) + [
        {"$group": {"_id": "$platform", "count": {"$sum": 1}}}]
    by_platform_raw = await db.marketing_reviews.aggregate(pipeline_platform).to_list(100)
    by_platform = {r["_id"]: r["count"] for r in by_platform_raw if r["_id"]}

    return {
        "success": True,
        "data": {
            "total": total,
            "pending": pending,
            "reviewed": reviewed,
            "low_rating": low_rating,
            "avg_rating": avg_rating,
            "rating_distribution": {
                "1": rating_1,
                "2": rating_2,
                "3": rating_3,
                "4": rating_4,
                "5": rating_5,
            },
            "by_platform": by_platform,
        }
    }

@router.get("")
async def list_reviews(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    status: str = Query(default=""),
    platform: str = Query(default=""),
    rating: int = Query(default=0),
    category: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    search: str = Query(default=""),
    account_id: str = Query(default=""),
):
    user = await require_auth(request)
    await seed_reviews_if_empty()
    db = get_db()

    q = await _scope.scope_filter(db, user, None)
    if status:
        q["status"] = status
    if platform:
        q["platform"] = platform
    if rating > 0:
        q["rating"] = rating
    if category:
        q["category"] = category
    if date_from:
        q.setdefault("date", {})["$gte"] = date_from
    if date_to:
        q.setdefault("date", {})["$lte"] = date_to
    if account_id:
        q["account_id"] = account_id
    if search:
        q["$or"] = [
            {"order_id": {"$regex": search, "$options": "i"}},
            {"product": {"$regex": search, "$options": "i"}},
            {"review_text": {"$regex": search, "$options": "i"}},
        ]

    total = await db.marketing_reviews.count_documents(q)
    skip = (page - 1) * page_size
    items = await db.marketing_reviews.find(q, {"_id": 0})\
                    .sort("date", -1).skip(skip).limit(page_size).to_list(page_size)
    
    return {
        "success": True,
        "data": serialize(items),
        "pagination": {
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": (total + page_size - 1) // page_size
        }
    }

@router.get("/{review_id}")
async def get_review(review_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    review = await db.marketing_reviews.find_one({"id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(404, "Review not found")
    return {"success": True, "data": serialize(review)}

@router.post("")
async def create_review(body: ReviewIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    # ── F14 (perbaikan lanjutan) — LINGKUP TOKO & `platform` DARI MASTER ──────
    # Sesi sebelumnya membuat `platform` opsional supaya layar tidak perlu
    # mengetiknya, TETAPI endpoint ini masih menyimpan `body.platform` apa adanya.
    # Akibatnya setiap ulasan baru tersimpan `platform: null` (terbukti pada uji
    # terakhir), sehingga kartu "Ulasan per Platform" dan filter platform
    # kehilangan SEMUA baris baru — tanpa satu pun error. Sekarang toko WAJIB
    # dipilih dan `account_name`/`platform` diambil dari master lewat SSOT
    # `core.marketing_account_scope`, jadi mustahil ada ulasan akun Shopee yang
    # berplatform 'tiktok'.
    from core import marketing_account_scope as _scope
    account = await _scope.require_account(db, body.account_id)
    # F15 — produk berasal dari item katalog toko (bukan teks bebas).
    _item = None
    if getattr(body, "catalog_item_id", None):
        _item = await _resolve_catalog_item(db, body.catalog_item_id, account["id"])
    elif not (getattr(body, "product", "") or "").strip():
        raise HTTPException(400, "Produk wajib: pilih item dari katalog toko.")

    review = {
        "id": str(uuid.uuid4()),
        "date": body.date,
        "order_id": body.order_id,
        "rating": body.rating,
        "catalog_item_id": _item.get("id") if _item else None,
        "sku": _item.get("sku", "") if _item else "",
        "product": (_item.get("name") if _item else body.product) or "",
        "category": body.category,
        "category_label": CATEGORY_LABELS.get(body.category, body.category),
        "review_text": body.review_text,
        "screenshot_url": body.screenshot_url or "",
        "response_text": body.response_text or "",
        "response_date": _now() if body.response_text else None,
        "status": "pending",
        "created_by": user.get("email", "unknown"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _scope.stamp_account(review, account)   # account_id · account_name · platform
    await db.marketing_reviews.insert_one(review)
    return {"success": True, "data": serialize(review)}

@router.put("/{review_id}")
async def update_review(review_id: str, body: ReviewUpdate, request: Request):
    await require_auth(request)
    db = get_db()

    existing = await db.marketing_reviews.find_one({"id": review_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Review not found")

    upd = {k: v for k, v in body.dict().items() if v is not None}
    # F14 — `platform`/`account_name` TIDAK BOLEH diubah bebas dari layar; kalau
    # tokonya dipindahkan, keduanya diambil ulang dari master.
    upd.pop("platform", None)
    upd.pop("account_name", None)
    if upd.get("account_id"):
        from core import marketing_account_scope as _scope
        _acc = await _scope.require_account(db, upd["account_id"])
        _scope.stamp_account(upd, _acc)
    if upd.get("catalog_item_id"):
        _it = await _resolve_catalog_item(
            db, upd["catalog_item_id"],
            upd.get("account_id") or existing.get("account_id"))
        upd["sku"] = _it.get("sku", "")
        upd["product"] = _it.get("name", "")
    if "category" in upd:
        upd["category_label"] = CATEGORY_LABELS.get(upd["category"], upd["category"])
    if "response_text" in upd and upd["response_text"] and not existing.get("response_date"):
        upd["response_date"] = _now()
        upd["status"] = "reviewed"
    upd["updated_at"] = _now()
    
    await db.marketing_reviews.update_one({"id": review_id}, {"$set": upd})
    updated = {**existing, **upd}
    return {"success": True, "data": serialize(updated)}

@router.delete("/{review_id}")
async def delete_review(review_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_reviews.delete_one({"id": review_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Review not found")
    return {"success": True, "message": "Deleted"}

@router.post("/{review_id}/respond")
async def respond_to_review(review_id: str, request: Request):
    await require_auth(request)
    body = await request.json()
    response_text = body.get("response_text", "")
    
    if not response_text:
        raise HTTPException(400, "Response text required")
    
    db = get_db()
    existing = await db.marketing_reviews.find_one({"id": review_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Review not found")
    
    await db.marketing_reviews.update_one(
        {"id": review_id},
        {"$set": {
            "response_text": response_text,
            "response_date": _now(),
            "status": "reviewed",
            "updated_at": _now()
        }}
    )
    return {"success": True, "message": "Response sent"}

@router.post("/{review_id}/ai-categorize")
async def ai_categorize_review(review_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    review = await db.marketing_reviews.find_one({"id": review_id}, {"_id": 0})
    if not review:
        raise HTTPException(404, "Review not found")

    if not EMERGENT_LLM_KEY:
        raise HTTPException(503, "AI not configured")

    review_text = review.get("review_text", "")
    rating = review.get("rating", 0)

    chat = LlmChat(
        api_key=EMERGENT_LLM_KEY,
        session_id=f"review-categorize-{review_id[:8]}",
        system_message="Kamu adalah AI classifier untuk review produk fashion muslim Indonesia. Kategorikan review ke salah satu kategori yang sesuai. Respond ONLY with valid JSON."
    ).with_model("openai", "gpt-4o-mini")

    categories_str = ", ".join([f"{k} ({v})" for k, v in CATEGORY_LABELS.items()])
    prompt = (
        f"Kategorikan review berikut:\n"
        f"Rating: {rating} bintang\n"
        f"Review: \"{review_text}\"\n\n"
        f"Pilih SATU kategori yang paling sesuai dari:\n{categories_str}\n\n"
        f"Return JSON persis: {{\"category\": \"<category_key>\", \"confidence\": 0.95, \"reasoning\": \"penjelasan singkat\"}}"
    )

    try:
        response = await chat.send_message(UserMessage(text=prompt))
        clean = response.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        result = json.loads(clean.strip())

        category = result.get("category", "tanpa_keterangan")
        
        await db.marketing_reviews.update_one(
            {"id": review_id},
            {"$set": {
                "category": category,
                "category_label": CATEGORY_LABELS.get(category, category),
                "updated_at": _now()
            }}
        )
        return {"success": True, "result": result, "applied_category": category}
    except Exception as e:
        raise HTTPException(500, f"AI categorization failed: {e}")
