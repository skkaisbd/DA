"""
Migration: Legacy Toko (dewi_toko_*) → SSOT (marketing_*)
==========================================================
Task: P1.D Legacy Toko Migration (FORENSIC_04 Cluster 3)
Created: 2026-05-23
Reversible: NO (idempotent re-runs safe; legacy collections NOT dropped)

Mappings:
    dewi_toko_products       → marketing_catalog_items (under "Toko Legacy" marketing_catalogs parent)
    dewi_toko_channels       → marketing_platform_accounts (_legacy_toko=True)
    dewi_toko_channel_syncs  → marketing_stock_syncs (_legacy_toko=True)
    dewi_toko_orders         → marketing_orders (_legacy_toko=True)
    dewi_toko_returns        → marketing_returns (_legacy_toko=True)
    dewi_toko_reviews        → marketing_reviews (_legacy_toko=True)

Preserved (no marketing_* equivalent):
    dewi_toko_flashsales, dewi_toko_pack_batches

Idempotency: upsert by `id`; re-runs skip docs already mirrored.

Usage:
    cd /app/backend
    python migrations/migrate_toko_data.py             # dry-run
    python migrations/migrate_toko_data.py --execute   # apply for real
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from routes._toko_adapter import (  # noqa: E402
    get_or_create_toko_legacy_catalog,
    toko_product_to_catalog_item,
    toko_channel_to_platform_account,
    toko_sync_to_marketing,
    toko_order_to_marketing,
    toko_return_to_marketing,
    toko_review_to_marketing,
)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "garment_erp")


async def _migrate_collection(
    db, src_name: str, tgt_name: str, transform, *, dry_run: bool,
    transform_kwargs=None,
) -> dict:
    src = db[src_name]
    tgt = db[tgt_name]
    transform_kwargs = transform_kwargs or {}

    src_count = await src.count_documents({})
    if src_count == 0:
        return {"src": 0, "migrated": 0, "skipped_existing": 0, "samples": []}

    migrated = 0
    skipped = 0
    samples: list = []
    cursor = src.find({}, {"_id": 0})
    async for old in cursor:
        try:
            new = transform(old, **transform_kwargs) if transform_kwargs else transform(old)
        except Exception as e:
            print(f"[WARN] transform failed for {src_name}: {e}")
            continue
        if not new.get("id"):
            continue
        existing = await tgt.find_one({"id": new["id"]}, {"_id": 0, "id": 1})
        if existing:
            skipped += 1
            continue
        if not dry_run:
            await tgt.update_one({"id": new["id"]}, {"$set": new}, upsert=True)
        migrated += 1
        if len(samples) < 3:
            samples.append({"action": "upsert", "id": new["id"]})
    return {"src": src_count, "migrated": migrated, "skipped_existing": skipped, "samples": samples}


async def validate(db) -> dict:
    return {
        "dewi_toko_products": await db.dewi_toko_products.count_documents({}),
        "dewi_toko_channels": await db.dewi_toko_channels.count_documents({}),
        "dewi_toko_channel_syncs": await db.dewi_toko_channel_syncs.count_documents({}),
        "dewi_toko_orders": await db.dewi_toko_orders.count_documents({}),
        "dewi_toko_returns": await db.dewi_toko_returns.count_documents({}),
        "dewi_toko_reviews": await db.dewi_toko_reviews.count_documents({}),
        "marketing_catalog_items_legacy": await db.marketing_catalog_items.count_documents(
            {"_legacy_toko": True}
        ),
        "marketing_platform_accounts_legacy": await db.marketing_platform_accounts.count_documents(
            {"_legacy_toko": True}
        ),
        "marketing_stock_syncs_legacy": await db.marketing_stock_syncs.count_documents(
            {"_legacy_toko": True}
        ),
        "marketing_orders_legacy": await db.marketing_orders.count_documents({"_legacy_toko": True}),
        "marketing_returns_legacy": await db.marketing_returns.count_documents({"_legacy_toko": True}),
        "marketing_reviews_legacy": await db.marketing_reviews.count_documents({"_legacy_toko": True}),
    }


async def main(execute: bool) -> int:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"=== Migration: Legacy Toko → marketing_* ({mode}) ===")
    print(f"DB: {DB_NAME}\n")

    print("Pre-migration validation:")
    print(json.dumps(await validate(db), indent=2))
    print()

    # Catalog id for products
    catalog_id = await get_or_create_toko_legacy_catalog(db) if execute else "<dry-run-pending>"
    print(f"Toko Legacy catalog id: {catalog_id}\n")

    print("Step 1/6 → dewi_toko_products → marketing_catalog_items")
    if execute:
        r1 = await _migrate_collection(
            db, "dewi_toko_products", "marketing_catalog_items",
            toko_product_to_catalog_item, dry_run=False,
            transform_kwargs={"catalog_id": catalog_id},
        )
    else:
        # dry-run with fake catalog_id
        r1 = await _migrate_collection(
            db, "dewi_toko_products", "marketing_catalog_items",
            lambda x: toko_product_to_catalog_item(x, "<dry-run>"),
            dry_run=True,
        )
    print(json.dumps(r1, indent=2, default=str))
    print()

    print("Step 2/6 → dewi_toko_channels → marketing_platform_accounts")
    r2 = await _migrate_collection(
        db, "dewi_toko_channels", "marketing_platform_accounts",
        toko_channel_to_platform_account, dry_run=not execute,
    )
    print(json.dumps(r2, indent=2, default=str))
    print()

    print("Step 3/6 → dewi_toko_channel_syncs → marketing_stock_syncs")
    r3 = await _migrate_collection(
        db, "dewi_toko_channel_syncs", "marketing_stock_syncs",
        toko_sync_to_marketing, dry_run=not execute,
    )
    print(json.dumps(r3, indent=2, default=str))
    print()

    print("Step 4/6 → dewi_toko_orders → marketing_orders")
    r4 = await _migrate_collection(
        db, "dewi_toko_orders", "marketing_orders",
        toko_order_to_marketing, dry_run=not execute,
    )
    print(json.dumps(r4, indent=2, default=str))
    print()

    print("Step 5/6 → dewi_toko_returns → marketing_returns")
    r5 = await _migrate_collection(
        db, "dewi_toko_returns", "marketing_returns",
        toko_return_to_marketing, dry_run=not execute,
    )
    print(json.dumps(r5, indent=2, default=str))
    print()

    print("Step 6/6 → dewi_toko_reviews → marketing_reviews")
    r6 = await _migrate_collection(
        db, "dewi_toko_reviews", "marketing_reviews",
        toko_review_to_marketing, dry_run=not execute,
    )
    print(json.dumps(r6, indent=2, default=str))
    print()

    print("Post-migration validation:")
    print(json.dumps(await validate(db), indent=2))
    print()

    print("Notes:")
    print("  • Preserved (no marketing equivalent): dewi_toko_flashsales, dewi_toko_pack_batches")
    print("  • Legacy collections NOT dropped (1-week monitoring per protocol).")
    print("  • Re-run is safe (idempotent via id matching).")
    if not execute:
        print("  • To apply for real, run with: --execute")
    print()
    print(f"Migration {mode}: DONE")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate dewi_toko_* legacy data to marketing_* SSOT.")
    parser.add_argument("--execute", action="store_true", help="Apply changes (otherwise dry-run).")
    args = parser.parse_args()
    code = asyncio.run(main(execute=args.execute))
    sys.exit(code)
