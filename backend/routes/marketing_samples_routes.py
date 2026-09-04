"""
Sample Delivery Tracking Module — Backend Routes
Phase 3 Week 13: Tracking pengiriman sample produk ke reseller/KOL
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, Query
from pydantic import BaseModel, Field
# F6 (sesi #10) — endpoint DAFTAR/RINGKAS wajib menyaring sendiri: jaring
# pengaman middleware hanya menolak permintaan yang MENYEBUT toko, ia tidak
# tahu isi jawaban. Tanpa ini staf pemegang satu toko membaca angka 9 toko.
from core import marketing_account_scope as _scope
from database import get_db
from auth import require_auth

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/samples", tags=["marketing-samples"])

SAMPLE_TYPES = ["live", "video"]
PLATFORMS = ["tiktok", "instagram", "shopee", "tokopedia"]
COURIERS = ["jnt", "spx", "sicepat", "jne", "anteraja", "ninja", "grab", "gojek"]
SAMPLE_STATUSES = ["pending", "shipped", "delivered", "returned", "cancelled"]
PROGRESS_STATUSES = ["open", "follow_up", "sold", "no_response", "closed"]

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
async def seed_samples_if_empty():
    db = get_db()
    if await db.marketing_samples.count_documents({}) > 0:
        return

    import random
    
    products = [
        "Gamis Daluna Basic", "Khimar Syari Premium", "Tunik Busui Friendly",
        "Set Gamis + Khimar", "Outer Cardigan", "Rok Plisket Panjang",
        "Dress Casual", "Hijab Segiempat"
    ]
    
    # F14 — sample demo dulu memakai `username` teks bebas dan TIDAK punya
    # `account_id`/`creator_id` (35/35 kosong) ⇒ biaya sample tidak bisa dibebankan
    # ke toko mana pun, dan performa kreator tidak bisa dihitung.
    from core import marketing_account_scope as _scope
    from core.marketing_master_seed import ensure_demo_creators
    _accounts = await _scope.seed_account_pool(db)
    await ensure_demo_creators(db)
    _creators = await db.marketing_kol_creators.find(
        {}, {"_id": 0, "id": 1, "name": 1, "creator_code": 1, "platforms": 1,
             "assigned_account_ids": 1}).to_list(100)

    def _creator_handle(c):
        p = (c or {}).get("platforms") or {}
        return p.get("tiktok") or p.get("instagram") or (c or {}).get("creator_code") \
            or (c or {}).get("name") or ""

    usernames = [_creator_handle(c) for c in _creators] or [
        "@ayufashion", "@budihijab", "@citramuslimah", "@dinarmodest",
        "@evisyari", "@farahbusana", "@ginaootd", "@hanastyle"
    ]
    
    sizes = ["S", "M", "L", "XL", "XXL"]
    colors = ["Hitam", "Navy", "Maroon", "Olive", "Abu-abu", "Coklat"]
    couriers_list = ["jnt", "spx", "sicepat"]
    
    entries = []
    base = _now()
    
    for i in range(35):
        day_offset = random.randint(-45, 0)
        sample_date = base + timedelta(days=day_offset)
        
        quantity = random.randint(1, 3)
        hpp = random.randint(50000, 150000)
        ongkir = random.randint(15000, 35000)
        sample_type = random.choice(["live", "video", "video"])
        
        progress = random.choice(["open", "follow_up", "sold", "no_response", "closed"])
        shipment_status = "delivered" if progress in ["sold", "closed"] else "shipped" if progress == "follow_up" else "pending"
        
        _acc = random.choice(_accounts)
        _cand = [c for c in _creators
                 if _acc["id"] in (c.get("assigned_account_ids") or [])] or _creators
        _cr = random.choice(_cand) if _cand else None
        entries.append({
            "id": str(uuid.uuid4()),
            "date": sample_date.date().isoformat(),
            "account_id": _acc["id"],
            "account_name": _acc.get("account_name", ""),
            "creator_id": (_cr or {}).get("id"),
            "username": (_creator_handle(_cr) if _cr else random.choice(usernames)),
            "sample_type": sample_type,
            "sample_type_label": "Live Streaming" if sample_type == "live" else "Video Review",
            "platform": _acc.get("platform", "tiktok"),
            "product": random.choice(products),
            "size": random.choice(sizes),
            "color": random.choice(colors),
            "quantity": quantity,
            "hpp": hpp,
            "total_hpp": hpp * quantity,
            "ongkir": ongkir,
            "courier": random.choice(couriers_list),
            "video_link": f"https://vt.tiktok.com/ZS{random.randint(1000000, 9999999)}/" if sample_type == "video" else "",
            "screenshot_url": "",
            "shipment_status": shipment_status,
            "progress": progress,
            "sales_update": "Terjual 5 pcs" if progress == "sold" else "Sedang follow up" if progress == "follow_up" else "Belum ada respon" if progress == "no_response" else "",
            "notes": "",
            "_seed_origin": True,
            "created_by": "system",
            "created_at": _now(),
            "updated_at": _now(),
        })
    
    if entries:
        await db.marketing_samples.insert_many(entries)
    logger.info(f"[marketing_samples] seeded {len(entries)} entries")

# ── Models ───────────────────────────────────────────────────────────────────
class SampleIn(BaseModel):
    # ── F14/F15 ───────────────────────────────────────────────────────────────
    # `account_id` dulu TIDAK ADA sama sekali (35/35 dokumen tanpa lingkup toko)
    # ⇒ biaya sample tidak bisa dibebankan ke toko mana pun.
    # `creator_id` menggantikan `username` sebagai identitas kreator: username
    # teks bebas membuat satu kreator pecah jadi beberapa baris laporan begitu
    # ejaannya beda satu karakter. `username` tetap disimpan sebagai TURUNAN.
    account_id: str
    creator_id: Optional[str] = None
    catalog_item_id: Optional[str] = None
    date: str
    username: Optional[str] = ""
    sample_type: str
    platform: str
    product: str
    size: str
    color: str
    quantity: int = Field(ge=0)
    hpp: float = Field(ge=0)
    ongkir: float
    courier: str
    video_link: Optional[str] = ""
    notes: Optional[str] = ""

class SampleUpdate(BaseModel):
    account_id: Optional[str] = None
    creator_id: Optional[str] = None
    catalog_item_id: Optional[str] = None
    date: Optional[str] = None
    username: Optional[str] = None
    sample_type: Optional[str] = None
    platform: Optional[str] = None
    product: Optional[str] = None
    size: Optional[str] = None
    color: Optional[str] = None
    quantity: Optional[int] = Field(default=None, ge=0)
    hpp: Optional[float] = Field(default=None, ge=0)
    ongkir: Optional[float] = None
    courier: Optional[str] = None
    video_link: Optional[str] = None
    screenshot_url: Optional[str] = None
    shipment_status: Optional[str] = None
    progress: Optional[str] = None
    sales_update: Optional[str] = None
    notes: Optional[str] = None

# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/summary")
async def get_summary(request: Request,
                      account_id: str = Query(default="")):
    user = await require_auth(request)
    await seed_samples_if_empty()
    db = get_db()
    _sq = await _scope.scope_filter(
        db, user, {"account_id": account_id} if account_id else {})

    total = await db.marketing_samples.count_documents(dict(_sq))
    pending = await db.marketing_samples.count_documents({**_sq, "shipment_status": "pending"})
    shipped = await db.marketing_samples.count_documents({**_sq, "shipment_status": "shipped"})
    delivered = await db.marketing_samples.count_documents({**_sq, "shipment_status": "delivered"})
    
    # Progress summary
    open_count = await db.marketing_samples.count_documents({**_sq, "progress": "open"})
    sold_count = await db.marketing_samples.count_documents({**_sq, "progress": "sold"})
    follow_up = await db.marketing_samples.count_documents({**_sq, "progress": "follow_up"})
    no_response = await db.marketing_samples.count_documents({**_sq, "progress": "no_response"})
    
    # Total investment
    pipeline_cost = ([{"$match": dict(_sq)}] if _sq else []) + [
        {"$group": {"_id": None, "total_hpp": {"$sum": "$total_hpp"},
                    "total_ongkir": {"$sum": "$ongkir"}}}]
    cost_result = await db.marketing_samples.aggregate(pipeline_cost).to_list(1)
    total_hpp = cost_result[0]["total_hpp"] if cost_result else 0
    total_ongkir = cost_result[0]["total_ongkir"] if cost_result else 0
    total_investment = total_hpp + total_ongkir

    return {
        "success": True,
        "data": {
            "total": total,
            "pending": pending,
            "shipped": shipped,
            "delivered": delivered,
            "open": open_count,
            "sold": sold_count,
            "follow_up": follow_up,
            "no_response": no_response,
            "total_investment": total_investment,
            "total_hpp": total_hpp,
            "total_ongkir": total_ongkir,
        }
    }

@router.get("")
async def list_samples(
    request: Request,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, le=100),
    account_id: str = Query(default="", description="F14 — filter per toko"),
    creator_id: str = Query(default=""),
    shipment_status: str = Query(default=""),
    progress: str = Query(default=""),
    platform: str = Query(default=""),
    sample_type: str = Query(default=""),
    date_from: str = Query(default=""),
    date_to: str = Query(default=""),
    search: str = Query(default=""),
):
    user = await require_auth(request)
    await seed_samples_if_empty()
    db = get_db()

    q = await _scope.scope_filter(
        db, user, {"account_id": account_id} if account_id else {})
    if creator_id:
        q["creator_id"] = creator_id
    if shipment_status:
        q["shipment_status"] = shipment_status
    if progress:
        q["progress"] = progress
    if platform:
        q["platform"] = platform
    if sample_type:
        q["sample_type"] = sample_type
    if date_from:
        q.setdefault("date", {})["$gte"] = date_from
    if date_to:
        q.setdefault("date", {})["$lte"] = date_to
    if search:
        q["$or"] = [
            {"username": {"$regex": search, "$options": "i"}},
            {"product": {"$regex": search, "$options": "i"}},
            {"sales_update": {"$regex": search, "$options": "i"}},
        ]

    total = await db.marketing_samples.count_documents(q)
    skip = (page - 1) * page_size
    items = await db.marketing_samples.find(q, {"_id": 0})\
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

@router.get("/{sample_id}")
async def get_sample(sample_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    sample = await db.marketing_samples.find_one({"id": sample_id}, {"_id": 0})
    if not sample:
        raise HTTPException(404, "Sample not found")
    return {"success": True, "data": serialize(sample)}

@router.post("")
async def create_sample(body: SampleIn, request: Request):
    await require_auth(request)
    user = _get_user(request)
    db = get_db()
    from core import marketing_account_scope as _scope

    # F14 — toko wajib & sah; F15 — kreator wajib SUDAH di-assign ke toko itu.
    account = await _scope.require_account(db, body.account_id)
    creator = None
    username = body.username or ""
    if body.creator_id:
        creator = await _scope.assert_creator_assigned(db, body.creator_id,
                                                       account["id"])
        _p = creator.get("platforms") or {}
        username = (_p.get("tiktok") or _p.get("instagram")
                    or creator.get("creator_code") or creator.get("name") or "")

    # HPP: kalau item katalog dipilih, HPP-nya ikut MASTER — bukan diketik ulang.
    hpp = body.hpp
    item = None
    if body.catalog_item_id:
        item = await db.marketing_catalog_items.find_one(
            {"id": body.catalog_item_id}, {"_id": 0})
        if not item:
            raise HTTPException(404, "Item katalog tidak ditemukan")
        if not hpp:
            hpp = float(item.get("hpp") or 0)

    total_hpp = hpp * body.quantity

    sample = {
        "id": str(uuid.uuid4()),
        "date": body.date,
        "creator_id": (creator or {}).get("id"),
        "creator_name": (creator or {}).get("name", ""),
        "username": username,
        "catalog_item_id": body.catalog_item_id,
        "sku": (item or {}).get("sku", ""),
        "sample_type": body.sample_type,
        "sample_type_label": "Live Streaming" if body.sample_type == "live" else "Video Review",
        "platform": account.get("platform") or body.platform,
        "product": (item or {}).get("name") or body.product,
        "size": body.size,
        "color": body.color,
        "quantity": body.quantity,
        "hpp": hpp,
        "total_hpp": total_hpp,
        "ongkir": body.ongkir,
        "courier": body.courier,
        "video_link": body.video_link or "",
        "screenshot_url": "",
        "shipment_status": "pending",
        "progress": "open",
        "sales_update": "",
        "notes": body.notes or "",
        "created_by": user.get("email", "unknown"),
        "created_at": _now(),
        "updated_at": _now(),
    }
    _scope.stamp_account(sample, account)
    await db.marketing_samples.insert_one(sample)
    return {"success": True, "data": serialize(sample)}

@router.put("/{sample_id}")
async def update_sample(sample_id: str, body: SampleUpdate, request: Request):
    await require_auth(request)
    db = get_db()

    existing = await db.marketing_samples.find_one({"id": sample_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Sample not found")

    upd = {k: v for k, v in body.dict().items() if v is not None}
    
    # Recalculate total_hpp if quantity or hpp changed
    if "quantity" in upd or "hpp" in upd:
        qty = upd.get("quantity", existing.get("quantity", 1))
        hpp = upd.get("hpp", existing.get("hpp", 0))
        upd["total_hpp"] = qty * hpp
    
    if "sample_type" in upd:
        upd["sample_type_label"] = "Live Streaming" if upd["sample_type"] == "live" else "Video Review"
    
    upd["updated_at"] = _now()
    
    await db.marketing_samples.update_one({"id": sample_id}, {"$set": upd})
    updated = {**existing, **upd}
    return {"success": True, "data": serialize(updated)}

@router.delete("/{sample_id}")
async def delete_sample(sample_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    res = await db.marketing_samples.delete_one({"id": sample_id})
    if res.deleted_count == 0:
        raise HTTPException(404, "Sample not found")
    return {"success": True, "message": "Deleted"}

@router.post("/{sample_id}/ship")
async def ship_sample(sample_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    existing = await db.marketing_samples.find_one({"id": sample_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Sample not found")
    
    await db.marketing_samples.update_one(
        {"id": sample_id},
        {"$set": {
            "shipment_status": "shipped",
            "updated_at": _now()
        }}
    )
    return {"success": True, "message": "Sample marked as shipped"}

@router.post("/{sample_id}/deliver")
async def deliver_sample(sample_id: str, request: Request):
    await require_auth(request)
    db = get_db()
    existing = await db.marketing_samples.find_one({"id": sample_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Sample not found")
    
    await db.marketing_samples.update_one(
        {"id": sample_id},
        {"$set": {
            "shipment_status": "delivered",
            "progress": "follow_up",
            "updated_at": _now()
        }}
    )
    return {"success": True, "message": "Sample marked as delivered"}

@router.post("/{sample_id}/update-progress")
async def update_progress(sample_id: str, request: Request):
    await require_auth(request)
    body = await request.json()
    progress = body.get("progress", "")
    sales_update = body.get("sales_update", "")
    
    if progress not in PROGRESS_STATUSES:
        raise HTTPException(400, f"Invalid progress: {progress}")
    
    db = get_db()
    existing = await db.marketing_samples.find_one({"id": sample_id}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "Sample not found")
    
    await db.marketing_samples.update_one(
        {"id": sample_id},
        {"$set": {
            "progress": progress,
            "sales_update": sales_update,
            "updated_at": _now()
        }}
    )
    return {"success": True, "message": "Progress updated"}
