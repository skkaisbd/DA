"""
Backfill Legacy Toko Products to Marketing Catalog Shape
=========================================================

Adds marketing-native field names to legacy-migrated `marketing_catalog_items`
docs WITHOUT removing legacy toko fields (dual-shape, fully backward compatible
with the `_toko_adapter.catalog_item_to_toko_product()` projection used by
legacy `/api/dewi/toko/products/*` endpoints).

Field mapping (toko → marketing):
    sku_code      → sku
    base_price    → price
    cost_price    → original_price
    stock_total   → stock_quantity
    weight_grams  → weight_gram
    photos[]      → images[]
    status        → is_active (true if 'active', else false)
    -- variants[] preserved as-is (toko-specific feature)
    -- channel_prices[] preserved as-is (toko-specific feature)

Idempotent. Safe to re-run.

Run:
    python3 /app/backend/migrations/backfill_marketing_products.py [--dry-run]
"""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv()


async def backfill_products(db, dry_run: bool = False) -> dict:
    stats = {"checked": 0, "updated": 0, "skipped": 0, "details": []}

    cursor = db.marketing_catalog_items.find({"_legacy_toko": True})
    async for doc in cursor:
        stats["checked"] += 1
        patch: dict = {}

        # sku ← sku_code
        if not doc.get("sku") and doc.get("sku_code"):
            patch["sku"] = doc.get("sku_code")

        # price ← base_price
        if doc.get("price") is None and doc.get("base_price") is not None:
            patch["price"] = float(doc.get("base_price") or 0)

        # original_price ← cost_price
        if doc.get("original_price") is None and doc.get("cost_price") is not None:
            patch["original_price"] = float(doc.get("cost_price") or 0)

        # platform_price (no equivalent; set 0)
        if doc.get("platform_price") is None:
            patch["platform_price"] = 0.0

        # stock_quantity ← stock_total
        if doc.get("stock_quantity") is None and doc.get("stock_total") is not None:
            patch["stock_quantity"] = float(doc.get("stock_total") or 0)

        # stock_alert_threshold default
        if doc.get("stock_alert_threshold") is None:
            patch["stock_alert_threshold"] = 10.0

        # stock_status derived
        if not doc.get("stock_status"):
            sq = patch.get("stock_quantity") or doc.get("stock_total") or 0
            sat = patch.get("stock_alert_threshold") or doc.get("stock_alert_threshold") or 10
            if sq <= 0:
                patch["stock_status"] = "out_of_stock"
            elif sq <= sat:
                patch["stock_status"] = "low_stock"
            else:
                patch["stock_status"] = "in_stock"

        # weight_gram ← weight_grams
        if doc.get("weight_gram") is None and doc.get("weight_grams") is not None:
            patch["weight_gram"] = float(doc.get("weight_grams") or 0)

        # images ← photos
        if not doc.get("images") and doc.get("photos"):
            patch["images"] = list(doc.get("photos") or [])

        # variant_info — derive from variants[] (first variant or empty)
        if not doc.get("variant_info"):
            variants = doc.get("variants") or []
            if variants:
                first = variants[0]
                parts = []
                if first.get("color"):
                    parts.append(f"Warna: {first.get('color')}")
                if first.get("size"):
                    parts.append(f"Size: {first.get('size')}")
                patch["variant_info"] = ", ".join(parts) if parts else (first.get("name") or "")
            else:
                patch["variant_info"] = ""

        # is_active ← status
        if doc.get("is_active") is None:
            status = doc.get("status") or "draft"
            patch["is_active"] = (status == "active")

        # platform_url default
        if not doc.get("platform_url"):
            patch["platform_url"] = ""

        # source marker
        if not doc.get("source"):
            patch["source"] = "legacy_toko"

        # tags ensure
        if doc.get("tags") is None:
            patch["tags"] = []

        if patch:
            patch["updated_at"] = datetime.now(timezone.utc)
            stats["details"].append({"id": doc["id"], "fields": list(patch.keys())})
            if not dry_run:
                await db.marketing_catalog_items.update_one(
                    {"id": doc["id"]},
                    {"$set": patch},
                )
            stats["updated"] += 1
        else:
            stats["skipped"] += 1

    return stats


async def main(dry_run: bool):
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db_name = os.environ.get("DB_NAME", "cv_dewi_aditya")
    db = client[db_name]

    print(f"== Backfill Marketing Products {'(DRY-RUN)' if dry_run else '(EXECUTE)'} ==")
    print(f"DB: {db_name}")
    print()

    rt = await backfill_products(db, dry_run=dry_run)
    print(f"[products] checked={rt['checked']}  updated={rt['updated']}  skipped={rt['skipped']}")
    for d in rt["details"][:5]:
        print(f"           - {d['id']}: {d['fields']}")
    print()
    print("Done.")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    asyncio.run(main(dry_run))
