"""
Marketing — Toko Dashboard Overview
====================================

Replaces legacy `/api/dewi/toko/dashboard` endpoint as part of P1.D Phase B
(Toko Frontend Cutover). Reads directly from marketing_* SSOT collections
(filtered by `_legacy_toko=True`) without any toko-shape projection.

Endpoints:
    GET /api/marketing/dashboard/toko-overview
        Aggregated overview: products stats, channel cards, top products,
        recent stock sync logs, total inventory value.

Source-of-Truth:
    - marketing_catalog_items  (filter: _legacy_toko=True)
    - marketing_platform_accounts (filter: _legacy_toko=True)
    - marketing_stock_syncs (filter: _legacy_toko=True)

Created: 2026-05-23 (Phase B.1 Toko Backend Prep)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from typing import List, Dict, Any

from database import get_db
from auth import require_auth
from utils.helpers import _clean_list


router = APIRouter(
    prefix="/api/marketing/dashboard",
    tags=["marketing-dashboard-toko"],
)


@router.get("/toko-overview")
async def toko_overview(user: dict = Depends(require_auth)) -> Dict[str, Any]:
    """
    Aggregated dashboard for Toko legacy modules backed by marketing_* SSOT.

    Returns:
        {
            "products": { total, active, draft, low_stock, inventory_value },
            "channels": { total, enabled, cards: [...] },
            "top_products": [...top 5 by sales_count_total...],
            "recent_syncs": [...latest 5 sync log entries...],
            "mock_mode": true
        }
    """
    db = get_db()

    # ── Products (marketing_catalog_items, filter _legacy_toko)
    items_coll = db.marketing_catalog_items
    legacy_filter = {"_legacy_toko": True}

    total_products = await items_coll.count_documents(legacy_filter)
    active_products = await items_coll.count_documents({**legacy_filter, "status": "active"})
    draft_products = await items_coll.count_documents({**legacy_filter, "status": "draft"})
    low_stock = await items_coll.count_documents({
        **legacy_filter,
        "status": "active",
        "stock_total": {"$lt": 10},
    })

    # Inventory value (sum stock_total * base_price for active+draft)
    pipeline_value = [
        {"$match": {**legacy_filter, "status": {"$in": ["active", "draft"]}}},
        {"$group": {
            "_id": None,
            "total": {"$sum": {"$multiply": ["$stock_total", "$base_price"]}},
        }},
    ]
    total_value = 0.0
    async for d in items_coll.aggregate(pipeline_value):
        total_value = float(d.get("total") or 0)

    # ── Channels (marketing_platform_accounts, filter _legacy_toko)
    channels_coll = db.marketing_platform_accounts
    channels_cursor = channels_coll.find(legacy_filter).sort("code", 1)
    channels: List[Dict[str, Any]] = await channels_cursor.to_list(length=50)

    enabled_channels = 0
    channel_cards: List[Dict[str, Any]] = []
    for c in channels:
        if c.get("enabled"):
            enabled_channels += 1
        channel_cards.append({
            "code": c.get("code") or c.get("channel_code"),
            "name": c.get("name") or c.get("account_name"),
            "enabled": bool(c.get("enabled", False)),
            "last_sync_at": c.get("last_sync_at"),
            "last_sync_counts": c.get("last_sync_counts") or {},
        })

    # ── Top 5 products by sales_count_total
    top_products_cursor = items_coll.find(
        legacy_filter, {"_id": 0}
    ).sort("sales_count_total", -1).limit(5)
    top_products = await top_products_cursor.to_list(length=5)
    # Normalize photo URLs, ensure plain dicts
    top_products = _clean_list(top_products)

    # ── Recent stock sync (latest 5 across all legacy channels)
    syncs_coll = db.marketing_stock_syncs
    recent_syncs_cursor = syncs_coll.find(legacy_filter, {"_id": 0}).sort("started_at", -1).limit(5)
    recent_syncs = await recent_syncs_cursor.to_list(length=5)
    recent_syncs = _clean_list(recent_syncs)

    return {
        "products": {
            "total": total_products,
            "active": active_products,
            "draft": draft_products,
            "low_stock": low_stock,
            "inventory_value": total_value,
        },
        "channels": {
            "total": len(channels),
            "enabled": enabled_channels,
            "cards": channel_cards,
        },
        "top_products": top_products,
        "recent_syncs": recent_syncs,
        "mock_mode": True,
    }
