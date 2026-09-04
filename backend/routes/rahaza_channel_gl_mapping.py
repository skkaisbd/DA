"""
Channel-to-GL Mapping
CV. Dewi Aditya — per-platform revenue routing untuk AR Invoice OS

Collection: rahaza_channel_gl_mapping
Setiap channel penjualan (toko Shopee, TikTok, Tokopedia, Maklon) punya:
  - debit_ar     : akun Piutang yang didebet (1-1301 Maklon / 1-1303 OS)
  - credit_revenue: akun Pendapatan yang dikredit (4-111..4-131, 4-210, 4-220)

Endpoints:
  GET  /api/rahaza/channel-gl-mapping          — list semua channel
  POST /api/rahaza/channel-gl-mapping          — buat channel baru
  PUT  /api/rahaza/channel-gl-mapping/{id}     — update channel
  DELETE /api/rahaza/channel-gl-mapping/{id}   — hapus channel
  POST /api/rahaza/channel-gl-mapping/seed-da  — seed default DA channels
"""

from fastapi import APIRouter, HTTPException, Request
from database import get_db
from auth import require_auth
from datetime import datetime, timezone
import uuid

router = APIRouter(prefix="/api/rahaza/channel-gl-mapping", tags=["Rahaza-ChannelGL"])


def _now():
    return datetime.now(timezone.utc).isoformat()


def _uid():
    return str(uuid.uuid4())


async def _require_fin(request: Request) -> dict:
    user = await require_auth(request)
    role = (user.get("role") or "").lower()
    if role in ("superadmin", "admin", "owner", "finance", "manager", "accountant"):
        return user
    raise HTTPException(403, "Akses ditolak — Finance/Admin only.")


# ─── Seed Data: DA Channels ──────────────────────────────────────────────────
# Format: (channel_key, channel_label, platform, debit_ar, credit_revenue)
DA_CHANNELS = [
    # Shopee
    ("shopee_grosirhijabsragen",  "Shopee – Grosirhijabsragen",  "shopee",    "1-1303", "4-111"),
    ("shopee_daluna",             "Shopee – Daluna",             "shopee",    "1-1303", "4-112"),
    ("shopee_moen",               "Shopee – Moen",               "shopee",    "1-1303", "4-113"),
    ("shopee_lainnya",            "Shopee – Lain-lain",          "shopee",    "1-1303", "4-114"),
    # TikTok Shop
    ("tiktok_daluna",             "TikTok – Daluna",             "tiktok",    "1-1303", "4-121"),
    ("tiktok_outfit_boutique",    "TikTok – Outfit Boutique",    "tiktok",    "1-1303", "4-122"),
    ("tiktok_style_by_moen",      "TikTok – Style by Moen",      "tiktok",    "1-1303", "4-123"),
    ("tiktok_fatimahijab",        "TikTok – Fatimahijab",        "tiktok",    "1-1303", "4-124"),
    ("tiktok_dezza_kids",         "TikTok – Dezza Kids",         "tiktok",    "1-1303", "4-125"),
    ("tiktok_lainnya",            "TikTok – Lain-lain",          "tiktok",    "1-1303", "4-126"),
    # Tokopedia
    ("tokopedia",                 "Tokopedia",                   "tokopedia", "1-1303", "4-131"),
    # Maklon
    ("maklon_snbm",               "Maklon – SnBm (Sablon & Bordir)", "maklon","1-1301", "4-210"),
    ("maklon_lainnya",            "Maklon – Klien Lain-lain",    "maklon",    "1-1301", "4-220"),
]

# ─── Helper: lookup channel GL by key ────────────────────────────────────────
async def get_channel_gl(db, channel_key: str) -> dict | None:
    """Return channel GL mapping doc or None if not found."""
    if not channel_key:
        return None
    return await db.rahaza_channel_gl_mapping.find_one(
        {"channel_key": channel_key, "active": True}, {"_id": 0}
    )


# ─── CRUD ────────────────────────────────────────────────────────────────────
@router.get("")
async def list_channels(request: Request):
    """Daftar semua channel GL mapping, diurutkan per platform."""
    await require_auth(request)
    db = get_db()
    docs = await db.rahaza_channel_gl_mapping.find(
        {"active": True}, {"_id": 0}
    ).sort([("platform", 1), ("channel_label", 1)]).to_list(200)
    return docs


@router.post("")
async def create_channel(request: Request):
    """Buat channel GL mapping baru."""
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    channel_key = (body.get("channel_key") or "").strip().lower().replace(" ", "_")
    if not channel_key:
        raise HTTPException(400, "channel_key wajib.")
    existing = await db.rahaza_channel_gl_mapping.find_one({"channel_key": channel_key})
    if existing:
        raise HTTPException(409, f"channel_key '{channel_key}' sudah ada.")
    doc = {
        "id": _uid(),
        "channel_key": channel_key,
        "channel_label": body.get("channel_label") or channel_key,
        "platform": (body.get("platform") or "other").lower(),
        "debit_ar": body.get("debit_ar") or "1-1303",
        "credit_revenue": body.get("credit_revenue") or "4-121",
        "active": True,
        "created_at": _now(), "updated_at": _now(),
        "created_by": user["id"], "created_by_name": user.get("name", ""),
    }
    await db.rahaza_channel_gl_mapping.insert_one(doc)
    return {k: v for k, v in doc.items() if k != "_id"}


@router.put("/{cid}")
async def update_channel(cid: str, request: Request):
    """Update channel GL mapping."""
    user = await _require_fin(request)
    db = get_db()
    body = await request.json()
    doc = await db.rahaza_channel_gl_mapping.find_one({"id": cid})
    if not doc:
        raise HTTPException(404, "Channel tidak ditemukan.")
    upd = {
        "channel_label":  body.get("channel_label", doc.get("channel_label")),
        "platform":       body.get("platform", doc.get("platform")),
        "debit_ar":       body.get("debit_ar", doc.get("debit_ar")),
        "credit_revenue": body.get("credit_revenue", doc.get("credit_revenue")),
        "updated_at": _now(),
        "updated_by": user["id"],
        "updated_by_name": user.get("name", ""),
    }
    await db.rahaza_channel_gl_mapping.update_one({"id": cid}, {"$set": upd})
    out = await db.rahaza_channel_gl_mapping.find_one({"id": cid}, {"_id": 0})
    return out


@router.delete("/{cid}")
async def delete_channel(cid: str, request: Request):
    """Soft-delete channel GL mapping."""
    user = await _require_fin(request)
    db = get_db()
    doc = await db.rahaza_channel_gl_mapping.find_one({"id": cid})
    if not doc:
        raise HTTPException(404, "Channel tidak ditemukan.")
    await db.rahaza_channel_gl_mapping.update_one(
        {"id": cid},
        {"$set": {"active": False, "updated_at": _now(), "updated_by": user["id"]}}
    )
    return {"ok": True}


# ─── Seed DA ─────────────────────────────────────────────────────────────────
@router.post("/seed-da")
async def seed_da_channels(request: Request):
    """Seed 13 channel default CV. Dewi Aditya. Idempotent — skip yang sudah ada."""
    user = await _require_fin(request)
    db = get_db()
    existing_keys: set = set()
    async for d in db.rahaza_channel_gl_mapping.find({}, {"channel_key": 1}):
        existing_keys.add(d["channel_key"])
    inserted = 0
    skipped = 0
    for channel_key, channel_label, platform, debit_ar, credit_revenue in DA_CHANNELS:
        if channel_key in existing_keys:
            skipped += 1
            continue
        doc = {
            "id": _uid(), "channel_key": channel_key, "channel_label": channel_label,
            "platform": platform, "debit_ar": debit_ar, "credit_revenue": credit_revenue,
            "active": True, "created_at": _now(), "updated_at": _now(),
            "created_by": user["id"], "created_by_name": user.get("name", ""),
        }
        await db.rahaza_channel_gl_mapping.insert_one(doc)
        inserted += 1
    return {"ok": True, "inserted": inserted, "skipped": skipped, "total": len(DA_CHANNELS)}
