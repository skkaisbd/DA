"""
Session #11.16 Phase C — Drop Legacy `dewi_kol_*` Collections
========================================================================
Following Session #11.16 Phase C refactor of `routes/dewi_kol.py` to stub
mode (all reads return [] or zeroed dict, all writes return 410 Gone),
these 3 legacy KOL collections can now be dropped. The corresponding
indexes in `server.py` (6 lines) are also removed in the same session.

Collections to drop:
  1. dewi_kol_creators  — legacy creator master (now `marketing_kol_creators`)
  2. dewi_kol_deals     — legacy deal/campaign (now `marketing_kol_sessions`)
  3. dewi_kol_samples   — legacy sample tracking (now `marketing_creator_item_requests`)

Usage:
    # Dry-run (default): just print counts, do nothing destructive
    python migrations/drop_dewi_kol_collections.py --dry-run

    # Live drop (refuses if any target is non-empty unless --force)
    python migrations/drop_dewi_kol_collections.py

    # Force drop (DANGEROUS — only after manual review)
    python migrations/drop_dewi_kol_collections.py --force

Reference:
    /app/plan.md → Phase C (Session #11.16)
    /app/FORENSIC_04_DATA_ARCHITECTURE.md → Cluster 6 (KOL / Marketing)
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
    'dewi_kol_creators',
    'dewi_kol_deals',
    'dewi_kol_samples',
]

SSOT_MAP = {
    'dewi_kol_creators': 'marketing_kol_creators',
    'dewi_kol_deals':    'marketing_kol_sessions',
    'dewi_kol_samples':  'marketing_creator_item_requests',
}


async def _count_safe(db, col_name: str) -> int:
    try:
        existing = await db.list_collection_names(filter={'name': col_name})
        if not existing:
            return -1
        return await db[col_name].count_documents({})
    except Exception:
        return -1


async def main():
    parser = argparse.ArgumentParser(
        description='Session #11.16 Phase C — Drop legacy dewi_kol_* collections')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only report counts; do nothing destructive')
    parser.add_argument('--force', action='store_true',
                        help='Drop even if collections are non-empty (DANGEROUS)')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 78)
    print('  Session #11.16 Phase C — Drop Legacy `dewi_kol_*` Collections')
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

        # SSOT successor counts for cross-visibility
        ssot_check = {
            'marketing_kol_creators':         None,
            'marketing_kol_sessions':         None,
            'marketing_creator_item_requests': None,
            'marketing_creator_catalog':      None,
        }
        for s in list(ssot_check.keys()):
            ssot_check[s] = await _count_safe(db, s)

        print('  SSOT successor counts (for context):')
        for s, n in ssot_check.items():
            disp = 'does not exist' if n == -1 else f'{n} docs'
            print(f'    {s:<32}{disp}')
        print()

        if args.dry_run:
            print('  DRY-RUN — no changes made.')
            print('=' * 78)
            return

        if nonempty and not args.force:
            print('  ❌ ABORT: One or more target collections contain documents:')
            for col in nonempty:
                print(f'      - {col} ({legacy_counts[col]} docs)')
            print('     Re-run with --force to drop anyway, or --dry-run to investigate.')
            print('=' * 78)
            sys.exit(2)

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

        # Post-drop verification
        print('  Post-drop verification:')
        still_present = []
        for col in TARGET_COLLECTIONS:
            existing = await db.list_collection_names(filter={'name': col})
            if existing:
                still_present.append(col)
                print(f'    ⚠ {col}: STILL PRESENT (auto-recreated?)')
            else:
                print(f'    ✓ {col}: GONE')
        print()

        if still_present:
            print('  ⚠ WARNING: Some collections are still present.')
            print('     Likely auto-recreated by a stale write before dropping.')
            sys.exit(3)

        print('  ✅ CLEANUP COMPLETE.')
        print('     All 3 legacy dewi_kol_* collections dropped.')
        print('     Backend collection count should decrease by 3 after restart.')
        print('=' * 78)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
