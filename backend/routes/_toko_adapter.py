"""
Toko Adapter — Konversi antara legacy `dewi_toko_*` dan modern `marketing_*`.

Bagian dari P1.D Legacy Toko Migration (FORENSIC_04 Cluster 3).

Mapping:
    dewi_toko_products       ←→ marketing_catalog_items (under a "Toko Legacy" marketing_catalogs parent)
    dewi_toko_channels       ←→ marketing_platform_accounts (legacy_toko=True flag)
    dewi_toko_channel_syncs  ←→ marketing_stock_syncs
    dewi_toko_orders         ←→ marketing_orders
    dewi_toko_returns        ←→ marketing_returns
    dewi_toko_reviews        ←→ marketing_reviews

Preserved (no marketing_* equivalent, keep as-is for now):
    dewi_toko_flashsales      — Toko-specific flashsale tooling
    dewi_toko_pack_batches    — Toko-specific packing batches

API contract preserved: frontend `/api/dewi/toko/*` masih bisa diakses.
Backend internally writes to marketing_* (SSOT) and reads from there as well.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict


# Toko channel code → marketing platform name
CHANNEL_TO_PLATFORM: Dict[str, str] = {
    "shopee": "shopee",
    "tiktok": "tiktok",
    "tokopedia": "tokopedia",
    "lazada": "lazada",
    "blibli": "blibli",
    "instagram": "instagram",
    "whatsapp": "whatsapp",
}


PLATFORM_TO_CHANNEL: Dict[str, str] = {v: k for k, v in CHANNEL_TO_PLATFORM.items()}


# Toko order status → marketing order status (already very close)
TOKO_TO_MKT_ORDER_STATUS: Dict[str, str] = {
    "new": "new",
    "packed": "packed",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "closed": "delivered",
    "returned": "returned",
}


MKT_TO_TOKO_ORDER_STATUS: Dict[str, str] = {
    "new": "new",
    "packed": "packed",
    "shipped": "shipped",
    "delivered": "delivered",
    "cancelled": "cancelled",
    "returned": "returned",
}


# Field name translation map: toko field → marketing field (for update operations)
TOKO_TO_MKT_ORDER_FIELDS: Dict[str, str] = {
    "packed_at": "packed_date",
    "shipped_at": "shipped_date",
    "delivered_at": "delivered_date",
    "cancelled_at": "cancelled_date",
    "total_amount": "total_payment",
    "customer_city": "city",
    "notes": "note",
    "order_number": "_legacy_order_number",
    "order_ref": "order_id",
}


def translate_toko_order_update(update: Dict[str, Any]) -> Dict[str, Any]:
    """Translate a MongoDB update doc with toko-shape fields to marketing-shape.

    Handles `$set`, `$unset`, `$inc` operators with field name mapping.
    """
    if not isinstance(update, dict):
        return update
    out: Dict[str, Any] = {}
    for op, val in update.items():
        if op.startswith("$") and isinstance(val, dict):
            translated = {}
            for k, v in val.items():
                new_k = TOKO_TO_MKT_ORDER_FIELDS.get(k, k)
                translated[new_k] = v
            out[op] = translated
        else:
            out[op] = val
    return out


TOKO_LEGACY_CATALOG_NAME = "Toko Legacy (Auto-Created)"


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _now():
    return datetime.now(timezone.utc)


def _id():
    return str(uuid.uuid4())


async def get_or_create_toko_legacy_catalog(db) -> str:
    """Return id of the auto-created legacy catalog. Creates if missing (idempotent)."""
    cat = await db.marketing_catalogs.find_one(
        {"_toko_legacy": True}, {"_id": 0, "id": 1}
    )
    if cat:
        return cat["id"]
    new_id = _id()
    await db.marketing_catalogs.insert_one({
        "id": new_id,
        "name": TOKO_LEGACY_CATALOG_NAME,
        "description": "Auto-created catalog untuk migrasi dewi_toko_products → marketing_catalog_items (P1.D).",
        "account_id": None,
        "platform": "multi",
        "status": "active",
        "_toko_legacy": True,
        "created_at": _now(),
        "updated_at": _now(),
    })
    return new_id


# ──────────────────────────────────────────────────────────────────────────────
# PRODUCTS: dewi_toko_products ↔ marketing_catalog_items
# ──────────────────────────────────────────────────────────────────────────────

def toko_product_to_catalog_item(p: Dict[str, Any], catalog_id: str) -> Dict[str, Any]:
    """Convert dewi_toko_products doc → marketing_catalog_items doc."""
    if not p:
        return {}
    return {
        "id": p.get("id") or _id(),
        "catalog_id": catalog_id,
        "sku_code": (p.get("sku_code") or "").strip().upper(),
        "name": p.get("name", ""),
        "description": p.get("description", ""),
        "category": p.get("category", "Toko Legacy"),
        "base_price": float(p.get("base_price") or 0),
        "cost_price": float(p.get("cost_price") or 0),
        "channel_prices": p.get("channel_prices") or [],
        "variants": p.get("variants") or [],
        "photos": p.get("photos") or [],
        "stock_total": int(p.get("stock_total") or 0),
        "stock_reserved": int(p.get("stock_reserved") or 0),
        "weight_grams": p.get("weight_grams"),
        "status": p.get("status") or "draft",
        "tags": p.get("tags") or [],
        "sales_count_total": int(p.get("sales_count_total") or 0),
        # Trace
        "_source": "dewi_toko_products",
        "_legacy_toko": True,
        "created_by": p.get("created_by", "migration"),
        "created_at": p.get("created_at") or _now(),
        "updated_at": _now(),
    }


def catalog_item_to_toko_product(it: Dict[str, Any]) -> Dict[str, Any]:
    """Project marketing_catalog_items → dewi_toko_products shape."""
    if not it:
        return {}
    return {
        "id": it.get("id"),
        "sku_code": it.get("sku_code", ""),
        "name": it.get("name", ""),
        "description": it.get("description", ""),
        "category": it.get("category", ""),
        "base_price": float(it.get("base_price") or 0),
        "cost_price": float(it.get("cost_price") or 0),
        "channel_prices": it.get("channel_prices") or [],
        "variants": it.get("variants") or [],
        "photos": it.get("photos") or [],
        "stock_total": int(it.get("stock_total") or 0),
        "stock_reserved": int(it.get("stock_reserved") or 0),
        "weight_grams": it.get("weight_grams"),
        "status": it.get("status", "draft"),
        "tags": it.get("tags") or [],
        "sales_count_total": int(it.get("sales_count_total") or 0),
        "_source": "marketing_catalog_items",
        "created_by": it.get("created_by", ""),
        "created_at": it.get("created_at"),
        "updated_at": it.get("updated_at"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# CHANNELS: dewi_toko_channels ↔ marketing_platform_accounts
# ──────────────────────────────────────────────────────────────────────────────

def toko_channel_to_platform_account(ch: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dewi_toko_channels doc → marketing_platform_accounts doc."""
    if not ch:
        return {}
    code = (ch.get("code") or "").lower()
    platform = CHANNEL_TO_PLATFORM.get(code, code)
    return {
        "id": ch.get("id") or _id(),
        "platform": platform,
        "channel_code": code,  # preserve for back-compat
        "code": code,  # alias for legacy filter compatibility
        "name": ch.get("name") or platform.capitalize(),
        "account_name": ch.get("account_name") or ch.get("name") or platform.capitalize(),
        "username": ch.get("username") or "",
        "shop_id": ch.get("shop_id") or "",
        "enabled": bool(ch.get("enabled", False)),
        "mock": bool(ch.get("mock", True)),
        "credentials": ch.get("credentials") or {},
        "fee_pct": float(ch.get("fee_pct") or 0),
        "commission_pct": float(ch.get("commission_pct") or 0),
        "notes": ch.get("notes") or "",
        "api_token_status": ch.get("api_token_status") or "not_set",
        "auto_sync_enabled": bool(ch.get("auto_sync_enabled", False)),
        "last_sync_at": ch.get("last_sync_at"),
        "last_sync_status": ch.get("last_sync_status") or "pending",
        "last_sync_counts": ch.get("last_sync_counts") or {},
        "status": ch.get("status") or "active",
        "_legacy_toko": True,
        "_source": "dewi_toko_channels",
        "created_at": ch.get("created_at") or _now(),
        "updated_at": _now(),
    }


def platform_account_to_toko_channel(acc: Dict[str, Any]) -> Dict[str, Any]:
    """Project marketing_platform_accounts → dewi_toko_channels shape."""
    if not acc:
        return {}
    code = acc.get("code") or acc.get("channel_code") or PLATFORM_TO_CHANNEL.get(
        (acc.get("platform") or "").lower(), acc.get("platform") or "unknown"
    )
    return {
        "id": acc.get("id"),
        "code": code,
        "name": acc.get("name") or acc.get("account_name") or code.capitalize(),
        "account_name": acc.get("account_name", ""),
        "username": acc.get("username", ""),
        "shop_id": acc.get("shop_id", ""),
        "enabled": bool(acc.get("enabled", False)),
        "mock": bool(acc.get("mock", True)),
        "credentials": acc.get("credentials") or {},
        "fee_pct": float(acc.get("fee_pct") or 0),
        "commission_pct": float(acc.get("commission_pct") or 0),
        "notes": acc.get("notes") or "",
        "api_token_status": acc.get("api_token_status", "not_set"),
        "auto_sync_enabled": bool(acc.get("auto_sync_enabled", False)),
        "last_sync_at": acc.get("last_sync_at"),
        "last_sync_status": acc.get("last_sync_status", "pending"),
        "last_sync_counts": acc.get("last_sync_counts") or {},
        "status": acc.get("status", "active"),
        "_source": "marketing_platform_accounts",
        "created_at": acc.get("created_at"),
        "updated_at": acc.get("updated_at"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# ORDERS: dewi_toko_orders ↔ marketing_orders
# ──────────────────────────────────────────────────────────────────────────────

def toko_order_to_marketing(o: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dewi_toko_orders → marketing_orders."""
    if not o:
        return {}
    items = o.get("items") or []
    # marketing_orders is largely flat: pick first item for sku_id/name (multi-item gets line summary)
    primary = items[0] if items else {}
    qty_total = sum(int(it.get("qty") or 0) for it in items)
    total_amount = float(o.get("total_amount") or 0)
    fee_amount = float(o.get("fee_amount") or 0)
    net_amount = float(o.get("net_amount") or (total_amount - fee_amount))

    channel_code = (o.get("channel_code") or "").lower()
    platform = CHANNEL_TO_PLATFORM.get(channel_code, channel_code)
    status = TOKO_TO_MKT_ORDER_STATUS.get(o.get("status", "new"), "new")

    return {
        "id": o.get("id") or _id(),
        "order_id": o.get("order_number") or o.get("order_ref") or _id()[:8],
        "platform": platform,
        "channel_code": channel_code,
        "account_name": o.get("channel_code") or platform,
        "product_name": primary.get("name") or primary.get("sku_code") or "(multi item)",
        "sku_id": primary.get("sku_code") or "",
        "variation": primary.get("variant") or "",
        "items": items,  # preserve full
        "quantity": qty_total,
        "price_original": float(primary.get("price") or 0),
        "price_final": float(primary.get("price") or 0),
        "discount_seller": 0.0,
        "shipping_cost": float(o.get("shipping_cost") or 0),
        "total_payment": total_amount,
        "fee_amount": fee_amount,
        "net_amount": net_amount,
        "revenue": net_amount,
        "payment_method": o.get("payment_method", ""),
        "status": status,
        "courier": o.get("courier", ""),
        "tracking_number": o.get("tracking_number"),
        "customer_name": o.get("customer_name", ""),
        "customer_phone": o.get("customer_phone", ""),
        "customer_address": o.get("customer_address", ""),
        "city": o.get("customer_city", ""),
        "note": o.get("notes", ""),
        "order_date": o.get("created_at") or _now(),
        "packed_date": o.get("packed_at"),
        "shipped_date": o.get("shipped_at"),
        "delivered_date": o.get("delivered_at"),
        "cancelled_date": o.get("cancelled_at"),
        "pack_batch_id": o.get("pack_batch_id"),
        "_source_type": "dewi_toko_orders",
        "_legacy_toko": True,
        "_legacy_order_number": o.get("order_number"),
        "created_at": o.get("created_at") or _now(),
        "updated_at": _now(),
    }


def marketing_to_toko_order(mo: Dict[str, Any]) -> Dict[str, Any]:
    """Project marketing_orders → dewi_toko_orders shape."""
    if not mo:
        return {}
    status = MKT_TO_TOKO_ORDER_STATUS.get(mo.get("status", "new"), "new")
    items = mo.get("items") or []
    if not items and mo.get("sku_id"):
        items = [{
            "sku_code": mo.get("sku_id", ""),
            "name": mo.get("product_name", ""),
            "qty": int(mo.get("quantity") or 1),
            "price": float(mo.get("price_final") or mo.get("price_original") or 0),
            "variant": mo.get("variation", ""),
        }]
    return {
        "id": mo.get("id"),
        "order_number": mo.get("_legacy_order_number") or mo.get("order_id"),
        "order_ref": mo.get("order_id"),
        "channel_code": mo.get("channel_code") or PLATFORM_TO_CHANNEL.get(
            (mo.get("platform") or "").lower(), mo.get("platform") or ""
        ),
        "customer_name": mo.get("customer_name", ""),
        "customer_address": mo.get("customer_address", ""),
        "customer_city": mo.get("city", ""),
        "customer_phone": mo.get("customer_phone", ""),
        "items": items,
        "total_amount": float(mo.get("total_payment") or 0),
        "fee_amount": float(mo.get("fee_amount") or 0),
        "net_amount": float(mo.get("net_amount") or mo.get("revenue") or 0),
        "shipping_cost": float(mo.get("shipping_cost") or 0),
        "payment_method": mo.get("payment_method", ""),
        "status": status,
        "courier": mo.get("courier", ""),
        "tracking_number": mo.get("tracking_number"),
        "notes": mo.get("note", ""),
        "pack_batch_id": mo.get("pack_batch_id"),
        "packed_at": mo.get("packed_date"),
        "shipped_at": mo.get("shipped_date"),
        "delivered_at": mo.get("delivered_date"),
        "cancelled_at": mo.get("cancelled_date"),
        "_source": "marketing_orders",
        "created_by": mo.get("created_by"),
        "created_at": mo.get("created_at") or mo.get("order_date"),
        "updated_at": mo.get("updated_at"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# RETURNS: dewi_toko_returns ↔ marketing_returns
# ──────────────────────────────────────────────────────────────────────────────

def toko_return_to_marketing(r: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dewi_toko_returns → marketing_returns."""
    if not r:
        return {}
    return {
        "id": r.get("id") or _id(),
        "return_number": r.get("return_number") or f"RET-{_id()[:8].upper()}",
        "order_id": r.get("order_id"),
        "order_number": r.get("order_number"),
        "account_id": None,
        "channel_code": r.get("channel_code", ""),
        "return_type": r.get("return_type") or "customer_refund",
        "customer_name": r.get("customer_name", ""),
        "reason": r.get("reason", ""),
        "reason_category": r.get("reason_category") or "other",
        "evidence_notes": r.get("evidence_notes", ""),
        "evidence_photos": r.get("evidence_photos") or [],
        "estimated_value": float(r.get("estimated_value") or 0),
        "status": r.get("status") or "new",
        "decision": r.get("decision") or "pending",
        "decision_notes": r.get("decision_notes", ""),
        "tracking_number": r.get("tracking_number"),
        "_legacy_toko": True,
        "_source": "dewi_toko_returns",
        "created_by": r.get("created_by", "migration"),
        "created_at": r.get("created_at") or _now(),
        "updated_at": _now(),
    }


def marketing_return_to_toko(mr: Dict[str, Any]) -> Dict[str, Any]:
    """Project marketing_returns → dewi_toko_returns shape."""
    if not mr:
        return {}
    return {
        "id": mr.get("id"),
        "return_number": mr.get("return_number"),
        "order_id": mr.get("order_id"),
        "order_number": mr.get("order_number"),
        "channel_code": mr.get("channel_code", ""),
        "return_type": mr.get("return_type") or "customer_refund",
        "customer_name": mr.get("customer_name", ""),
        "reason": mr.get("reason", ""),
        "evidence_notes": mr.get("evidence_notes", ""),
        "estimated_value": float(mr.get("estimated_value") or 0),
        "status": mr.get("status", "new"),
        "decision": mr.get("decision", "pending"),
        "decision_notes": mr.get("decision_notes", ""),
        "tracking_number": mr.get("tracking_number"),
        "_source": "marketing_returns",
        "created_by": mr.get("created_by"),
        "created_at": mr.get("created_at"),
        "updated_at": mr.get("updated_at"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# REVIEWS: dewi_toko_reviews ↔ marketing_reviews
# ──────────────────────────────────────────────────────────────────────────────

def toko_review_to_marketing(rv: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dewi_toko_reviews → marketing_reviews."""
    if not rv:
        return {}
    channel = (rv.get("channel_code") or "shopee").lower()
    return {
        "id": rv.get("id") or _id(),
        "channel_code": channel,
        "platform": CHANNEL_TO_PLATFORM.get(channel, channel),
        "order_ref": rv.get("order_ref"),
        "customer_name": rv.get("customer_name", ""),
        "rating": int(rv.get("rating") or 5),
        "review_text": rv.get("review_text", ""),
        "sku_code": rv.get("sku_code"),
        "status": rv.get("status") or "unread",
        "response_text": rv.get("response_text"),
        "responded_at": rv.get("responded_at"),
        "_legacy_toko": True,
        "_source": "dewi_toko_reviews",
        "created_by": rv.get("created_by"),
        "created_at": rv.get("created_at") or _now(),
        "updated_at": _now(),
    }


def marketing_review_to_toko(mrv: Dict[str, Any]) -> Dict[str, Any]:
    """Project marketing_reviews → dewi_toko_reviews shape."""
    if not mrv:
        return {}
    return {
        "id": mrv.get("id"),
        "channel_code": mrv.get("channel_code") or PLATFORM_TO_CHANNEL.get(
            (mrv.get("platform") or "").lower(), mrv.get("platform") or "shopee"
        ),
        "order_ref": mrv.get("order_ref"),
        "customer_name": mrv.get("customer_name", ""),
        "rating": int(mrv.get("rating") or 5),
        "review_text": mrv.get("review_text", ""),
        "sku_code": mrv.get("sku_code"),
        "status": mrv.get("status", "unread"),
        "response_text": mrv.get("response_text"),
        "responded_at": mrv.get("responded_at"),
        "_source": "marketing_reviews",
        "created_by": mrv.get("created_by"),
        "created_at": mrv.get("created_at"),
        "updated_at": mrv.get("updated_at"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# SYNC LOGS: dewi_toko_channel_syncs ↔ marketing_stock_syncs
# ──────────────────────────────────────────────────────────────────────────────

def toko_sync_to_marketing(s: Dict[str, Any]) -> Dict[str, Any]:
    """Convert dewi_toko_channel_syncs → marketing_stock_syncs."""
    if not s:
        return {}
    return {
        "id": s.get("id") or _id(),
        "channel_code": s.get("channel_code", ""),
        "platform": CHANNEL_TO_PLATFORM.get((s.get("channel_code") or "").lower(), s.get("channel_code", "")),
        "sync_type": s.get("sync_type") or "stock",
        "trigger": s.get("trigger") or "manual",
        "status": s.get("status") or "pending",
        "items_count": int(s.get("items_count") or 0),
        "success_count": int(s.get("success_count") or 0),
        "error_count": int(s.get("error_count") or 0),
        "error_message": s.get("error_message"),
        "started_at": s.get("started_at") or _now(),
        "completed_at": s.get("completed_at"),
        "_legacy_toko": True,
        "_source": "dewi_toko_channel_syncs",
        "created_at": s.get("started_at") or s.get("created_at") or _now(),
    }
