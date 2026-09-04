"""
Migration: Aksesoris (acc_*) → SSOT (rahaza_*)
============================================
Task: P1.A Accessory Consolidation (FORENSIC_04 Cluster 1)
Created: 2026-05-22
Reversible: NO (idempotent re-runs are safe; legacy data is preserved, NOT dropped)

Mappings:
    acc_items                → rahaza_materials (type='accessory')
    acc_stock_movements      → rahaza_material_movements (domain='accessory')
                               + adjust rahaza_material_stock running totals

Preserved (no migration needed - already unique features):
    acc_internal_requests, acc_loans, acc_purchase_requests,
    acc_opname_sessions, acc_opname_lines

Behaviour:
    - DRY-RUN (default): print counts, sample transform, NO writes
    - --execute: perform idempotent upserts + log movements + update stock totals

Idempotency:
    - rahaza_materials upsert by `id` (matches acc_items.id)
    - rahaza_material_movements skipped if a row with id+legacy_movement_type
      already present (so re-runs are safe)
    - rahaza_material_stock recomputed from sum of movements per material at end

Usage:
    cd /app/backend
    python migrations/migrate_accessories.py             # dry-run (default)
    python migrations/migrate_accessories.py --execute   # actually write
    python migrations/migrate_accessories.py --execute --no-recompute-stock
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "garment_erp")


# Allowed accessory unit values (must match rahaza_inventory MATERIAL_UNITS)
_VALID_UNITS = {
    "m", "cm", "yard", "inch",
    "kg", "gram", "ton",
    "pcs", "lusin", "kodi", "gross", "helai", "set", "pair",
    "rol", "gulung", "bal", "karton", "pak", "sak",
    "liter", "ml",
}


def _normalize_unit(u: str) -> str:
    u = (u or "pcs").strip().lower()
    aliases = {
        "piece": "pcs", "pieces": "pcs", "buah": "pcs",
        "meter": "m", "centimeter": "cm",
        "kilogram": "kg", "gr": "gram", "grams": "gram",
        "pasang": "pair", "rolls": "rol", "roll": "rol",
        "pack": "pak", "packs": "pak", "dus": "karton",
    }
    u = aliases.get(u, u)
    return u if u in _VALID_UNITS else "pcs"


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def transform_item(old: dict) -> dict:
    """Convert acc_items doc -> rahaza_materials doc (type='accessory')."""
    mid = old.get("id") or str(uuid.uuid4())
    return {
        "id": mid,
        "code": (old.get("code") or "").strip().upper() or f"ACC-{mid[:8].upper()}",
        "name": (old.get("name") or "").strip() or "(no name)",
        "type": "accessory",
        "unit": _normalize_unit(old.get("unit") or "pcs"),
        "category": old.get("category") or "Umum",
        "description": old.get("description", ""),
        "min_stock": float(old.get("min_stock") or 0),
        "supplier": old.get("supplier", ""),
        "notes": old.get("notes", ""),
        "active": not bool(old.get("deleted", False)),
        "created_by": old.get("created_by", "migration"),
        "created_at": old.get("created_at") or _now_iso(),
        "updated_at": _now_iso(),
        "migrated_from": "acc_items",
        "migrated_at": _now_iso(),
    }


def transform_movement(old: dict, accessory_loc_id: str | None) -> dict:
    """Convert acc_stock_movements doc -> rahaza_material_movements doc."""
    mid = old.get("id") or str(uuid.uuid4())
    legacy_mt = (old.get("movement_type") or "").upper()
    qty_signed = float(old.get("qty_signed") or 0)

    # canonical type
    if legacy_mt in ("IN", "LOAN_RETURN"):
        mv_type = "receive"
    elif legacy_mt in ("OUT", "LOAN_OUT"):
        mv_type = "issue"
    elif legacy_mt == "ADJUST":
        mv_type = "adjust"
    else:
        mv_type = "adjust" if qty_signed != abs(qty_signed) else "receive"

    qty_abs = abs(qty_signed)
    # ADJUST keeps signed qty (positive or negative)
    qty_for_row = qty_signed if mv_type == "adjust" else qty_abs

    return {
        "id": mid,
        "type": mv_type,
        "material_id": old.get("acc_id"),
        "qty": float(qty_for_row),
        "from_location_id": accessory_loc_id if mv_type in ("issue",) or (mv_type == "adjust" and qty_signed < 0) else None,
        "to_location_id": accessory_loc_id if mv_type in ("receive",) or (mv_type == "adjust" and qty_signed > 0) else None,
        "ref_type": old.get("ref_type", ""),
        "ref_id": old.get("ref_id", ""),
        "ref_number": old.get("ref_number", ""),
        "notes": old.get("notes", ""),
        "legacy_movement_type": legacy_mt or mv_type.upper(),
        "domain": "accessory",
        "created_at": old.get("created_at") or _now_iso(),
        "timestamp": old.get("created_at") or _now_iso(),
        "created_by": old.get("created_by", "migration"),
        "created_by_name": old.get("created_by", "migration"),
        "migrated_from": "acc_stock_movements",
        "migrated_at": _now_iso(),
    }


async def get_or_create_accessory_loc(db, dry_run: bool) -> str | None:
    loc = await db.rahaza_locations.find_one({"code": "ZNA-AKSESORIS"}, {"_id": 0, "id": 1})
    if loc:
        return loc["id"]
    if dry_run:
        return "<would-create-ZNA-AKSESORIS>"
    new_id = str(uuid.uuid4())
    await db.rahaza_locations.insert_one({
        "id": new_id,
        "code": "ZNA-AKSESORIS",
        "name": "Area Aksesoris",
        "type": "zona",
        "created_at": _now(),
        "updated_at": _now(),
    })
    return new_id


async def migrate_items(db, dry_run: bool) -> dict:
    """Migrate acc_items -> rahaza_materials (type='accessory')."""
    src_count = await db.acc_items.count_documents({})
    already = await db.rahaza_materials.count_documents({"type": "accessory"})
    if src_count == 0:
        return {"src": 0, "already_target": already, "migrated": 0, "skipped_existing": 0, "samples": []}

    cursor = db.acc_items.find({}, {"_id": 0})
    migrated = 0
    skipped = 0
    samples: list[dict] = []
    async for old in cursor:
        new = transform_item(old)
        # Skip if a doc with same id already exists as accessory type
        exists = await db.rahaza_materials.find_one({"id": new["id"]}, {"_id": 0, "id": 1, "type": 1})
        if exists and exists.get("type") == "accessory":
            skipped += 1
            if len(samples) < 3:
                samples.append({"action": "skip-existing", "id": new["id"], "code": new["code"]})
            continue
        if not dry_run:
            await db.rahaza_materials.update_one(
                {"id": new["id"]},
                {"$set": new},
                upsert=True,
            )
        migrated += 1
        if len(samples) < 5:
            samples.append({"action": "upsert", "id": new["id"], "code": new["code"], "name": new["name"]})

    return {
        "src": src_count,
        "already_target": already,
        "migrated": migrated,
        "skipped_existing": skipped,
        "samples": samples,
    }


async def migrate_movements(db, dry_run: bool, accessory_loc_id: str | None) -> dict:
    src_count = await db.acc_stock_movements.count_documents({})
    if src_count == 0:
        return {"src": 0, "migrated": 0, "skipped_existing": 0, "samples": []}

    cursor = db.acc_stock_movements.find({}, {"_id": 0})
    migrated = 0
    skipped = 0
    samples: list[dict] = []
    async for old in cursor:
        new = transform_movement(old, accessory_loc_id)
        if not new.get("material_id"):
            # Orphan movement, skip
            skipped += 1
            continue
        exists = await db.rahaza_material_movements.find_one({"id": new["id"]}, {"_id": 0, "id": 1})
        if exists:
            skipped += 1
            continue
        if not dry_run:
            await db.rahaza_material_movements.insert_one(new)
        migrated += 1
        if len(samples) < 5:
            samples.append({
                "action": "insert", "id": new["id"],
                "type": new["type"], "qty": new["qty"],
                "material_id": new["material_id"],
            })
    return {"src": src_count, "migrated": migrated, "skipped_existing": skipped, "samples": samples}


async def recompute_accessory_stock(db, dry_run: bool, accessory_loc_id: str | None) -> dict:
    """After migration, recompute rahaza_material_stock for all accessory materials.

    Strategy:
      - For each accessory material id:
        - Sum qty across all movements (receive +, issue -, adjust signed)
        - Upsert one rahaza_material_stock row at ZNA-AKSESORIS with that total
      - If migration left other locations untouched, we DON'T zero them out
        (only update the accessory loc total to match aggregated movements).
    """
    if not accessory_loc_id:
        return {"updated": 0, "samples": []}

    pipeline = [
        {"$match": {"domain": "accessory"}},
        {"$lookup": {
            "from": "rahaza_materials",
            "localField": "material_id",
            "foreignField": "id",
            "as": "_mat",
        }},
        {"$unwind": "$_mat"},
        {"$match": {"_mat.type": "accessory"}},
        {"$group": {
            "_id": "$material_id",
            "total_in": {"$sum": {
                "$cond": [{"$eq": ["$type", "receive"]}, "$qty", 0]
            }},
            "total_out": {"$sum": {
                "$cond": [{"$eq": ["$type", "issue"]}, "$qty", 0]
            }},
            "total_adjust": {"$sum": {
                "$cond": [{"$eq": ["$type", "adjust"]}, "$qty", 0]
            }},
        }},
    ]
    rows = await db.rahaza_material_movements.aggregate(pipeline).to_list(10000)
    updated = 0
    samples: list[dict] = []
    for r in rows:
        mid = r["_id"]
        net = float(r["total_in"]) - float(r["total_out"]) + float(r["total_adjust"])
        if not dry_run:
            await db.rahaza_material_stock.update_one(
                {"material_id": mid, "location_id": accessory_loc_id},
                {
                    "$set": {"qty": net, "updated_at": _now()},
                    "$setOnInsert": {"id": str(uuid.uuid4())},
                },
                upsert=True,
            )
        updated += 1
        if len(samples) < 5:
            samples.append({"material_id": mid, "computed_qty": net})
    return {"updated": updated, "samples": samples}


async def validate(db) -> dict:
    """Validation report (run in both dry-run and execute mode)."""
    src_items = await db.acc_items.count_documents({})
    src_movs = await db.acc_stock_movements.count_documents({})
    tgt_acc_mats = await db.rahaza_materials.count_documents({"type": "accessory"})
    tgt_acc_movs = await db.rahaza_material_movements.count_documents({"domain": "accessory"})
    return {
        "src_acc_items": src_items,
        "src_acc_stock_movements": src_movs,
        "target_rahaza_materials(type=accessory)": tgt_acc_mats,
        "target_rahaza_material_movements(domain=accessory)": tgt_acc_movs,
    }


async def main(execute: bool, recompute_stock: bool) -> int:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    mode = "EXECUTE" if execute else "DRY-RUN"
    print(f"=== Migration: Aksesoris → SSOT ({mode}) ===")
    print(f"DB: {DB_NAME}")
    print()

    loc_id = await get_or_create_accessory_loc(db, dry_run=not execute)
    print(f"Accessory location id: {loc_id}")
    print()

    print("Pre-migration validation:")
    pre = await validate(db)
    print(json.dumps(pre, indent=2))
    print()

    print("Step 1/3 → migrate acc_items → rahaza_materials")
    r1 = await migrate_items(db, dry_run=not execute)
    print(json.dumps(r1, indent=2, default=str))
    print()

    print("Step 2/3 → migrate acc_stock_movements → rahaza_material_movements")
    r2 = await migrate_movements(db, dry_run=not execute, accessory_loc_id=loc_id if execute else None)
    print(json.dumps(r2, indent=2, default=str))
    print()

    if recompute_stock and execute:
        print("Step 3/3 → recompute rahaza_material_stock from migrated movements")
        r3 = await recompute_accessory_stock(db, dry_run=False, accessory_loc_id=loc_id)
        print(json.dumps(r3, indent=2, default=str))
        print()
    elif recompute_stock and not execute:
        print("Step 3/3 → SKIPPED in dry-run (would recompute rahaza_material_stock)")
        print()
    else:
        print("Step 3/3 → SKIPPED (--no-recompute-stock)")
        print()

    print("Post-migration validation:")
    post = await validate(db)
    print(json.dumps(post, indent=2))
    print()

    print("Notes:")
    print("  • Legacy collections (acc_items, acc_stock_movements) are NOT dropped.")
    print("  • Re-run is safe (idempotent via id matching).")
    if not execute:
        print("  • To apply for real, run with: --execute")
    print()
    print(f"Migration {mode}: DONE")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Migrate acc_* legacy data to rahaza_* SSOT.")
    parser.add_argument("--execute", action="store_true", help="Apply changes. Otherwise dry-run.")
    parser.add_argument("--no-recompute-stock", action="store_true",
                        help="Do not recompute rahaza_material_stock totals after migration.")
    args = parser.parse_args()
    code = asyncio.run(main(execute=args.execute, recompute_stock=not args.no_recompute_stock))
    sys.exit(code)
