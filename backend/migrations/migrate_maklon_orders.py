"""
Migration: Maklon Orders (dewi_maklon_orders) → SSOT (dewi_maklon_pos)
========================================================================
Task: P1.B Maklon Orders Consolidation (FORENSIC_04 Cluster 2)
Created: 2026-05-22
Reversible: NO (idempotent re-runs safe; legacy collection is NOT dropped)

Legacy `dewi_maklon_orders` schema = single-product per order.
New `dewi_maklon_pos` schema      = multi-item per PO (richer).

Mapping (legacy → PO):
    id              → id                (preserve UUID)
    order_code      → po_number
    client_id       → client_id
    product_name    → items[0].product_description
    qty_ordered     → items[*].qty (split by qty_per_size if present)
    qty_per_size    → items[*]  (1 item per size)
    price_per_pcs   → items[*].cmt_rate_per_pcs
    total_value     → total_value
    order_date      → po_date
    deadline_date   → deadline
    status (legacy) → status (PO, mapped)
    linked_wo_ids   → items[0].wo_id (kept for traceability)
    stage_qty       → legacy_stage_qty (preserved as embedded field)

Idempotency:
    - Upsert into dewi_maklon_pos by `id` (same UUID as legacy order).
    - Skip if PO with that id already exists (re-runs safe).

Usage:
    cd /app/backend
    python migrations/migrate_maklon_orders.py             # dry-run
    python migrations/migrate_maklon_orders.py --execute   # apply for real
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

from routes._maklon_adapter import order_to_po_create_payload  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "garment_erp")


async def validate(db) -> dict:
    src = await db.dewi_maklon_orders.count_documents({})
    tgt = await db.dewi_maklon_pos.count_documents({})
    tgt_migrated = await db.dewi_maklon_pos.count_documents({"migrated_from": "dewi_maklon_orders"})
    return {
        "src_dewi_maklon_orders": src,
        "target_dewi_maklon_pos": tgt,
        "target_pos_migrated_from_legacy": tgt_migrated,
    }


async def migrate_orders(db, dry_run: bool) -> dict:
    src_count = await db.dewi_maklon_orders.count_documents({})
    if src_count == 0:
        return {"src": 0, "migrated": 0, "skipped_existing": 0, "samples": []}

    cursor = db.dewi_maklon_orders.find({}, {"_id": 0})
    migrated = 0
    skipped = 0
    samples: list = []
    async for old in cursor:
        old_id = old.get("id")
        if not old_id:
            skipped += 1
            continue
        # Idempotency: skip if PO with this id already exists
        existing = await db.dewi_maklon_pos.find_one({"id": old_id}, {"_id": 0, "id": 1})
        if existing:
            skipped += 1
            if len(samples) < 3:
                samples.append({"action": "skip-existing", "id": old_id, "order_code": old.get("order_code")})
            continue
        new_po = order_to_po_create_payload(old)
        if not dry_run:
            await db.dewi_maklon_pos.update_one(
                {"id": new_po["id"]},
                {"$set": new_po},
                upsert=True,
            )
        migrated += 1
        if len(samples) < 5:
            samples.append({
                "action": "upsert",
                "id": new_po["id"],
                "po_number": new_po["po_number"],
                "total_qty": new_po["total_qty"],
                "total_value": new_po["total_value"],
                "items_count": len(new_po["items"]),
                "status": new_po["status"],
            })
    return {
        "src": src_count,
        "migrated": migrated,
        "skipped_existing": skipped,
        "samples": samples,
    }


async def main(execute: bool) -> int:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"=== Migration: dewi_maklon_orders → dewi_maklon_pos ({mode}) ===")
    print(f"DB: {DB_NAME}\n")

    print("Pre-migration validation:")
    print(json.dumps(await validate(db), indent=2))
    print()

    print("Step 1/1 → migrate dewi_maklon_orders → dewi_maklon_pos")
    r = await migrate_orders(db, dry_run=not execute)
    print(json.dumps(r, indent=2, default=str))
    print()

    print("Post-migration validation:")
    print(json.dumps(await validate(db), indent=2))
    print()

    print("Notes:")
    print("  • Legacy collection (dewi_maklon_orders) is NOT dropped.")
    print("  • Re-run is safe (idempotent via id matching).")
    if not execute:
        print("  • To apply for real, run with: --execute")
    print()
    print(f"Migration {mode}: DONE")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate dewi_maklon_orders → dewi_maklon_pos.")
    parser.add_argument("--execute", action="store_true", help="Apply changes (otherwise dry-run).")
    args = parser.parse_args()
    code = asyncio.run(main(execute=args.execute))
    sys.exit(code)
