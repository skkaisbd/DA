"""
Marketing — Platform Account Stock Sync (Mock Provider)
========================================================

Replaces legacy `/api/dewi/toko/channels/{code}/sync` + `/sync-history`
endpoints as part of P1.D Phase B (Toko Frontend Cutover). Operates on
marketing_platform_accounts (filtered by `_legacy_toko=True`) and writes
log entries to marketing_stock_syncs.

Endpoints:
    POST /api/marketing/accounts/{account_id_or_code}/sync
        Trigger MOCK stock sync. Returns counts + duration_ms.
    GET  /api/marketing/accounts/{account_id_or_code}/sync-history?limit=20
        Returns latest sync log entries for the account.

Notes:
- Accepts either platform_account.id OR legacy channel `code` (shopee/tokopedia/...)
  for compatibility with frontend ChannelManager which uses `code`.
- Real provider integration replaces `_mock_sync_provider()` later.

Created: 2026-05-23 (Phase B.1 Toko Backend Prep)
"""
from __future__ import annotations

import random
import uuid
from typing import Optional, Dict, Any

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from database import get_db
from auth import require_auth
from utils.helpers import _now, _clean_list


router = APIRouter(
    prefix="/api/marketing/accounts",
    tags=["marketing-accounts-sync"],
)


CHANNEL_LABELS: Dict[str, str] = {
    "shopee": "Shopee",
    "tokopedia": "Tokopedia",
    "tiktok_shop": "TikTok Shop",
    "tiktokshop": "TikTok Shop",
    "tiktok": "TikTok",
    "lazada": "Lazada",
    "blibli": "Blibli",
    "website": "Website Sendiri",
}


# ── Legacy Toko Channel Config (PUT replacement for /api/dewi/toko/channels/{code})

class LegacyChannelConfigBody(BaseModel):
    """Body for updating legacy Toko channel configuration via marketing namespace."""
    enabled: Optional[bool] = None
    credentials: Optional[Dict[str, Any]] = None  # api_key, api_secret, shop_id, webhook_url
    fee_pct: Optional[float] = Field(default=None, ge=0)
    commission_pct: Optional[float] = None
    notes: Optional[str] = None


@router.put("/{account_key}/legacy-config")
async def update_legacy_channel_config(
    account_key: str,
    body: LegacyChannelConfigBody,
    user: dict = Depends(require_auth),
):
    """Update legacy Toko channel config (enabled, credentials, fees) via marketing
    namespace. Replaces legacy PUT /api/dewi/toko/channels/{code}.

    Credentials are stored as-is (encryption layer to be added later).
    """
    db = get_db()
    acc = await _resolve_account(db, account_key)
    if not acc:
        raise HTTPException(404, "Account/channel tidak ditemukan")

    update: Dict[str, Any] = {"updated_at": _now()}

    if body.enabled is not None:
        update["enabled"] = body.enabled
        update["status"] = "active" if body.enabled else "inactive"

    if body.credentials is not None:
        # Merge credentials non-destructively (skip empty strings = "clear")
        cur_creds = dict(acc.get("credentials") or {})
        for k, v in body.credentials.items():
            if v == "":
                cur_creds.pop(k, None)
            elif v is not None and not (isinstance(v, str) and v.startswith("***")):
                cur_creds[k] = v
        update["credentials"] = cur_creds
        # Update api_token_status flag
        has_real = any(
            v and not (isinstance(v, str) and v.startswith("***"))
            for k, v in cur_creds.items()
            if k in ("api_key", "api_secret")
        )
        update["api_token_status"] = "configured" if has_real else "not_set"

    if body.fee_pct is not None:
        update["fee_pct"] = float(body.fee_pct)
    if body.commission_pct is not None:
        update["commission_pct"] = float(body.commission_pct)
    if body.notes is not None:
        update["notes"] = body.notes

    await db.marketing_platform_accounts.update_one(
        {"id": acc["id"]},
        {"$set": update},
    )

    # Re-fetch & mask secrets in response
    updated = await db.marketing_platform_accounts.find_one(
        {"id": acc["id"]}, {"_id": 0}
    )
    if updated and updated.get("credentials"):
        masked = dict(updated.get("credentials") or {})
        for sk in ("api_key", "api_secret"):
            if masked.get(sk):
                v = str(masked[sk])
                masked[sk] = "***" + v[-4:] if len(v) > 4 else "***"
        updated["credentials"] = masked
    return {"ok": True, "channel": updated}


async def _resolve_account(db, account_key: str) -> Optional[Dict[str, Any]]:
    """Resolve account by id or legacy channel code.

    Tries platform_account.id first, then falls back to `code` / `channel_code`
    for legacy toko compatibility.
    """
    acc = await db.marketing_platform_accounts.find_one(
        {"id": account_key, "_legacy_toko": True}, {"_id": 0}
    )
    if acc:
        return acc
    acc = await db.marketing_platform_accounts.find_one(
        {"$or": [{"code": account_key}, {"channel_code": account_key}], "_legacy_toko": True},
        {"_id": 0},
    )
    return acc


def _mock_sync_provider(acc: Dict[str, Any]) -> Dict[str, Any]:
    """Simulate marketplace stock sync. Returns counts dict."""
    code = acc.get("code") or acc.get("channel_code") or acc.get("platform")
    return {
        "products": random.randint(3, 12),
        "orders": random.randint(0, 8),
        "errors": 0,
        "mock": True,
        "channel": code,
    }


@router.post("/{account_key}/sync")
async def sync_account(account_key: str, user: dict = Depends(require_auth)):
    """Trigger MOCK stock sync for a Toko legacy platform account."""
    db = get_db()
    acc = await _resolve_account(db, account_key)
    if not acc:
        raise HTTPException(404, "Account/channel tidak ditemukan")
    if not acc.get("enabled"):
        raise HTTPException(400, "Account belum di-enable. Aktifkan dulu sebelum sync.")

    started = _now()
    try:
        counts = _mock_sync_provider(acc)
        finished = _now()
        duration_ms = int((finished - started).total_seconds() * 1000)

        # Insert sync log directly to marketing_stock_syncs (with _legacy_toko=True)
        channel_code = acc.get("code") or acc.get("channel_code") or acc.get("platform")
        log_doc = {
            "id": str(uuid.uuid4()),
            "channel_code": channel_code,
            "platform": acc.get("platform") or channel_code,
            "account_id": acc.get("id"),
            "sync_type": "stock",
            "trigger": "manual",
            "status": "success",
            "items_count": counts.get("products", 0),
            "success_count": counts.get("products", 0),
            "error_count": counts.get("errors", 0),
            "error_message": None,
            "started_at": started,
            "completed_at": finished,
            "duration_ms": duration_ms,
            "counts": counts,
            "mock": True,
            "triggered_by": user.get("name", "System") if isinstance(user, dict) else "System",
            "_legacy_toko": True,
            "_source": "marketing_accounts_sync",
            "created_at": started,
        }
        await db.marketing_stock_syncs.insert_one(log_doc)

        # Update account last_sync info
        await db.marketing_platform_accounts.update_one(
            {"id": acc.get("id")},
            {"$set": {
                "last_sync_at": finished,
                "last_sync_status": "success",
                "last_sync_counts": counts,
                "updated_at": finished,
            }},
        )

        return {
            "message": f"Sync {CHANNEL_LABELS.get(channel_code, channel_code or 'channel')} berhasil (MOCK)",
            "counts": counts,
            "duration_ms": duration_ms,
            "account_id": acc.get("id"),
            "channel_code": channel_code,
        }
    except HTTPException:
        raise
    except Exception as e:
        finished = _now()
        channel_code = acc.get("code") or acc.get("channel_code") or acc.get("platform")
        fail_doc = {
            "id": str(uuid.uuid4()),
            "channel_code": channel_code,
            "platform": acc.get("platform") or channel_code,
            "account_id": acc.get("id"),
            "sync_type": "stock",
            "trigger": "manual",
            "status": "failed",
            "items_count": 0,
            "success_count": 0,
            "error_count": 1,
            "error_message": str(e),
            "started_at": started,
            "completed_at": finished,
            "duration_ms": int((finished - started).total_seconds() * 1000),
            "mock": True,
            "triggered_by": user.get("name", "System") if isinstance(user, dict) else "System",
            "_legacy_toko": True,
            "_source": "marketing_accounts_sync",
            "created_at": started,
        }
        await db.marketing_stock_syncs.insert_one(fail_doc)
        await db.marketing_platform_accounts.update_one(
            {"id": acc.get("id")},
            {"$set": {"last_sync_status": "failed", "last_sync_at": finished}},
        )
        raise HTTPException(500, f"Sync gagal: {e}")


@router.get("/{account_key}/sync-history")
async def account_sync_history(
    account_key: str,
    limit: int = Query(default=20, ge=1, le=100),
    user: dict = Depends(require_auth),
):
    """Return latest sync log entries for the given account/channel."""
    db = get_db()
    acc = await _resolve_account(db, account_key)
    if not acc:
        raise HTTPException(404, "Account/channel tidak ditemukan")

    # Build filter — match by account_id OR channel_code (back-compat)
    channel_code = acc.get("code") or acc.get("channel_code") or acc.get("platform")
    filt = {
        "_legacy_toko": True,
        "$or": [
            {"account_id": acc.get("id")},
            {"channel_code": channel_code},
        ],
    }

    cursor = db.marketing_stock_syncs.find(filt, {"_id": 0}).sort("started_at", -1).limit(limit)
    items = await cursor.to_list(length=limit)
    return _clean_list(items)
