"""
Marketing Integration Settings — Platform API Keys Placeholder
Phase 3 Week 12: UI untuk menyimpan API keys Shopee / TikTok / Tokopedia
(tanpa melakukan actual API calls — placeholder siap digunakan saat Phase 4)
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from database import get_db
from auth import require_auth
from routes.shared import require_portal

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketing/integration-settings", tags=["marketing-integration-settings"])

PLATFORMS = ["shopee", "tiktok", "tokopedia"]

PLATFORM_META = {
    "shopee": {
        "name": "Shopee Partner API",
        "icon": "🛒",
        "color": "#EE4D2D",
        "fields": [
            {"key": "partner_id",  "label": "Partner ID",  "type": "text",     "placeholder": "Shopee Partner ID"},
            {"key": "partner_key", "label": "Partner Key", "type": "password", "placeholder": "Shopee Partner Secret Key"},
            {"key": "shop_id",     "label": "Shop ID",     "type": "text",     "placeholder": "Shop ID"},
        ],
        "docs_url": "https://open.shopee.com/documents",
        "note": "Butuh akun Shopee Open Platform dengan shop_id dan partner credentials.",
    },
    "tiktok": {
        "name": "TikTok Shop API",
        "icon": "🎵",
        "color": "#000000",
        "fields": [
            {"key": "app_key",    "label": "App Key",    "type": "text",     "placeholder": "TikTok App Key"},
            {"key": "app_secret", "label": "App Secret", "type": "password", "placeholder": "TikTok App Secret"},
            {"key": "shop_cipher","label": "Shop Cipher","type": "text",     "placeholder": "(opsional) Shop Cipher"},
        ],
        "docs_url": "https://partner.tiktokshop.com/doc",
        "note": "Butuh TikTok Shop Partner Account dan akses ke TikTok Open Platform.",
    },
    "tokopedia": {
        "name": "Tokopedia API",
        "icon": "🟢",
        "color": "#42B549",
        "fields": [
            {"key": "client_id",     "label": "Client ID",     "type": "text",     "placeholder": "Tokopedia Client ID"},
            {"key": "client_secret", "label": "Client Secret", "type": "password", "placeholder": "Tokopedia Client Secret"},
            {"key": "shop_id",       "label": "Shop ID",       "type": "text",     "placeholder": "Tokopedia Shop ID"},
        ],
        "docs_url": "https://developer.tokopedia.com",
        "note": "Butuh akun seller Tokopedia dan akses ke Tokopedia Seller API.",
    },
}


def _now() -> datetime:
    return datetime.now(timezone.utc)

def _mask(v: str) -> str:
    """Mask secret values for safe display."""
    if not v:
        return ""
    if len(v) <= 8:
        return "*" * len(v)
    return v[:3] + "*" * (len(v) - 6) + v[-3:]

def serialize(obj):
    if isinstance(obj, list):
        return [serialize(i) for i in obj]
    if isinstance(obj, dict):
        return {k: serialize(v) for k, v in obj.items() if k != "_id"}
    if isinstance(obj, datetime):
        return obj.isoformat()
    return obj


@router.get("/meta")
async def get_meta(request: Request):
    """Return platform metadata (field definitions, docs URLs, etc.)"""
    await require_portal(request, "toko")  # RBAC read-guard (BUG-AUTH-1)
    return {"success": True, "platforms": PLATFORM_META}


@router.get("")
async def list_configs(request: Request):
    """Return all platform configs (with secrets masked)."""
    await require_auth(request)
    db = get_db()
    configs = {}
    for p in PLATFORMS:
        doc = await db.marketing_integration_settings.find_one({"platform": p}, {"_id": 0})
        if doc:
            # Mask all password fields
            for f in PLATFORM_META.get(p, {}).get("fields", []):
                if f["type"] == "password" and doc.get(f["key"]):
                    doc[f"_{f['key']}_masked"] = _mask(str(doc[f["key"]]))
                    doc[f["key"]] = ""  # never send plaintext
            configs[p] = serialize(doc)
        else:
            configs[p] = {"platform": p, "connected": False, "credentials": {}}
    return {"success": True, "data": configs}


class IntegrationConfigIn(BaseModel):
    credentials: Dict[str, Any] = {}


@router.put("/{platform}")
async def save_config(platform: str, body: IntegrationConfigIn, request: Request):
    """Save platform credentials (only update non-empty fields)."""
    await require_auth(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Platform '{platform}' not supported. Use: {PLATFORMS}")
    db = get_db()

    existing = await db.marketing_integration_settings.find_one({"platform": platform}, {"_id": 0}) or {}

    # Only overwrite non-empty credential values
    merged_creds = dict(existing.get("credentials", {}))
    for k, v in body.credentials.items():
        if v:  # never overwrite with blank
            merged_creds[k] = v

    # Check if any required field is present (simple connectivity check)
    meta_fields = PLATFORM_META.get(platform, {}).get("fields", [])
    required_keys = [f["key"] for f in meta_fields]
    connected = all(merged_creds.get(k) for k in required_keys if k != "shop_cipher")

    doc = {
        "platform": platform,
        "connected": connected,
        "credentials": merged_creds,
        "updated_at": _now(),
    }
    if not existing:
        doc["created_at"] = _now()

    await db.marketing_integration_settings.update_one(
        {"platform": platform}, {"$set": doc}, upsert=True
    )

    # Return masked version
    for f in meta_fields:
        if f["type"] == "password" and merged_creds.get(f["key"]):
            merged_creds[f"_{f['key']}_masked"] = _mask(str(merged_creds[f["key"]]))
            merged_creds[f["key"]] = ""

    return {"success": True, "data": {**serialize(doc), "credentials": merged_creds}}


@router.delete("/{platform}")
async def disconnect_platform(platform: str, request: Request):
    """Clear all credentials for this platform."""
    await require_auth(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Platform '{platform}' not supported")
    db = get_db()
    await db.marketing_integration_settings.update_one(
        {"platform": platform},
        {"$set": {"connected": False, "credentials": {}, "updated_at": _now()}},
        upsert=True
    )
    return {"success": True, "message": f"Credentials for {platform} cleared"}


@router.post("/{platform}/test")
async def test_connection(platform: str, request: Request):
    """Simulate a connection test (Phase 4 will do real API call)."""
    await require_auth(request)
    if platform not in PLATFORMS:
        raise HTTPException(400, f"Platform '{platform}' not supported")
    db = get_db()
    doc = await db.marketing_integration_settings.find_one({"platform": platform}, {"_id": 0})
    if not doc or not doc.get("connected"):
        return {
            "success": False,
            "status": "not_configured",
            "message": f"Platform {platform} belum dikonfigurasi. Masukkan credentials terlebih dahulu.",
            "note": "Phase 4 akan mengaktifkan real API connection test."
        }
    # Placeholder test — pretend success (no real API call yet)
    platform_name = PLATFORM_META.get(platform, {}).get("name", platform)
    return {
        "success": True,
        "status": "placeholder_ok",
        "message": f"Credentials untuk {platform_name} tersimpan. Koneksi real akan diaktifkan di Phase 4 (Direct API Integration).",
        "note": "Test koneksi nyata (OAuth / Access Token) membutuhkan API keys yang valid dari platform."
    }
