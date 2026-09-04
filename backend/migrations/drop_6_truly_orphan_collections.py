"""
Session #11.16 Phase A — Drop 6 Truly-Orphan Empty Collections
==============================================================
Following the pre-drop audit in Session #11.15, these 6 collections were
identified as **truly orphan** — meaning:

  • All have zero documents (empty)
  • Zero frontend `fetch('/api/...')` references
  • No active sidebar entry that depends on them
  • All backend write paths exist only in deprecated route files
    (no UI trigger; cannot be called externally without manual curl)

This script safely drops them and reports cross-check stats against
their SSOT successors.

Collections to drop:
  1. warehouse_stock         (SSOT: rahaza_material_stock)
  2. warehouse_movements     (SSOT: rahaza_material_movements)
  3. warehouse_locations     (SSOT: wh_positions)
  4. warehouse_opname        (SSOT: wh_opname2_cycles / wh_opname_sessions2)
  5. accessories             (SSOT: rahaza_materials with type='accessory')
  6. accessory_requests      (SSOT: dewi_accessory_requests with
                              request_type='vendor_additional'/'vendor_replacement')

Usage:
    # Dry-run (default): just print counts, do nothing destructive
    python migrations/drop_6_truly_orphan_collections.py --dry-run

    # Live drop (REFUSES if any target collection has documents)
    python migrations/drop_6_truly_orphan_collections.py

    # Force drop (even if non-empty — DANGEROUS, use only after manual review)
    python migrations/drop_6_truly_orphan_collections.py --force

Reference:
    - /app/plan.md → Phase A roadmap (Session #11.15)
    - /app/FORENSIC_04_DATA_ARCHITECTURE.md → Clusters 1 & 3
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


TARGET_COLLECTIONS = [
    'warehouse_stock',
    'warehouse_movements',
    'warehouse_locations',
    'warehouse_opname',
    'accessories',
    'accessory_requests',
]

# Map each legacy collection to its SSOT successor for visibility.
SSOT_MAP = {
    'warehouse_stock':      'rahaza_material_stock',
    'warehouse_movements':  'rahaza_material_movements',
    'warehouse_locations':  'wh_positions',
    'warehouse_opname':     'wh_opname_sessions2',
    'accessories':          'rahaza_materials (type=accessory)',
    'accessory_requests':   'dewi_accessory_requests',
}


async def _count_safe(db, col_name: str) -> int:
    """Return doc count of a collection — 0 if collection does not exist."""
    try:
        existing = await db.list_collection_names(filter={'name': col_name})
        if not existing:
            return -1  # sentinel for "does not exist"
        return await db[col_name].count_documents({})
    except Exception:
        return -1


async def main():
    parser = argparse.ArgumentParser(
        description='Session #11.16 Phase A — Drop 6 truly-orphan empty collections')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only report counts; do nothing destructive')
    parser.add_argument('--force', action='store_true',
                        help='Drop even if collections are non-empty (DANGEROUS)')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 78)
    print('  Session #11.16 Phase A — Drop 6 Truly-Orphan Empty Collections')
    print('=' * 78)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    if args.dry_run:
        mode = 'DRY-RUN (no destructive action)'
    elif args.force:
        mode = 'LIVE + FORCE (drops even if non-empty)'
    else:
        mode = 'LIVE (refuses if any target is non-empty)'
    print(f'  Mode:        {mode}')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        # 1. Pre-flight audit
        print('  Target collection counts:')
        legacy_counts: dict[str, int] = {}
        nonempty: list[str] = []
        nonexistent: list[str] = []
        for col in TARGET_COLLECTIONS:
            n = await _count_safe(db, col)
            legacy_counts[col] = n
            if n == -1:
                status = '∅ does not exist'
                nonexistent.append(col)
            elif n == 0:
                status = '✓ empty'
            else:
                status = f'⚠ NON-EMPTY ({n})'
                nonempty.append(col)
            ssot = SSOT_MAP.get(col, '—')
            print(f'    {col:<32}{status:<22} → SSOT: {ssot}')
        print()

        # 2. SSOT counts (for cross-visibility / sanity check)
        ssot_check = {
            'rahaza_material_stock':       None,
            'rahaza_material_movements':   None,
            'wh_positions':                None,
            'wh_opname_sessions2':         None,
            'rahaza_materials':            None,
            'dewi_accessory_requests':     None,
        }
        for s in list(ssot_check.keys()):
            ssot_check[s] = await _count_safe(db, s)

        print('  SSOT successor counts (for context):')
        for s, n in ssot_check.items():
            if n == -1:
                disp = 'does not exist'
            else:
                disp = f'{n} docs'
            print(f'    {s:<32}{disp}')
        print()

        # 3. Dry-run exit
        if args.dry_run:
            print('  DRY-RUN — no changes made.')
            print('=' * 78)
            return

        # 4. Safety gate
        if nonempty and not args.force:
            print('  ❌ ABORT: One or more target collections contain documents:')
            for col in nonempty:
                print(f'      - {col} ({legacy_counts[col]} docs)')
            print('     Re-run with --force to drop anyway, or with --dry-run to investigate.')
            print('=' * 78)
            sys.exit(2)

        # 5. Drop collections
        print('  Dropping target collections...')
        dropped_count = 0
        skipped_count = 0
        for col in TARGET_COLLECTIONS:
            if col in nonexistent:
                print(f'    · skipped (does not exist) {col}')
                skipped_count += 1
                continue
            try:
                await db.drop_collection(col)
                print(f'    ✓ dropped {col}')
                dropped_count += 1
            except Exception as e:
                print(f'    ✗ {col}: {e}')
        print()
        print(f'  Result: {dropped_count} dropped, {skipped_count} skipped (already absent).')
        print()

        # 6. Post-drop verification
        print('  Post-drop verification:')
        still_present = []
        for col in TARGET_COLLECTIONS:
            existing = await db.list_collection_names(filter={'name': col})
            if existing:
                still_present.append(col)
                print(f'    ⚠ {col}: STILL PRESENT (was something auto-recreating it?)')
            else:
                print(f'    ✓ {col}: GONE')
        print()

        if still_present:
            print('  ⚠ WARNING: Some collections are still present.')
            print('     They may have been auto-recreated by a stale write before')
            print('     dropping; re-run to confirm.')
            sys.exit(3)

        print('  ✅ CLEANUP COMPLETE.')
        print('     All 6 truly-orphan collections have been dropped.')
        print('     Backend collection count should decrease by 6 after restart.')
        print('=' * 78)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
