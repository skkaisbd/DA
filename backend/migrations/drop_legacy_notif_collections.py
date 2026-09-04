"""
P3 TD-010 Phase B Cleanup — Drop Legacy Notification Collections
================================================================
After Session #11.12 (TD-010 Phase B), the 4 legacy notification collections
should be empty because all writers now persist to the unified SSOT
`notifications` collection.

This script:
  1. Counts documents in each legacy collection.
  2. Aborts (safely) if any contain documents (unless --force is set).
  3. Drops the 4 legacy collections.

Usage:
    # Dry run (default): just show counts, do nothing destructive
    python migrations/drop_legacy_notif_collections.py --dry-run

    # Live drop (refuses if any collection is non-empty)
    python migrations/drop_legacy_notif_collections.py

    # Force drop (even if collections are non-empty — DANGEROUS)
    python migrations/drop_legacy_notif_collections.py --force

Recommended workflow:
  1. After deploying Session #11.12 refactor, monitor for 1 week.
  2. Verify all 4 legacy collections remain empty during normal operation.
  3. Run with --dry-run to confirm counts.
  4. Run without --dry-run to drop.
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


LEGACY_COLLECTIONS = [
    'dewi_notifications',
    'rahaza_notifications',
    'collab_notifications',
    'marketing_livehost_notifications',
]


async def main():
    parser = argparse.ArgumentParser(
        description='P3 TD-010 Phase B Cleanup — Drop legacy notification collections')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only report counts; do nothing destructive')
    parser.add_argument('--force', action='store_true',
                        help='Drop even if collections are non-empty (DANGEROUS)')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 72)
    print('  P3 TD-010 Phase B Cleanup — Drop Legacy Notification Collections')
    print('=' * 72)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    if args.dry_run:
        mode = 'DRY-RUN (no destructive action)'
    elif args.force:
        mode = 'LIVE + FORCE (drops even if non-empty)'
    else:
        mode = 'LIVE (refuses if non-empty)'
    print(f'  Mode:        {mode}')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        # 1. Audit counts in legacy + SSOT
        ssot_total = await db.notifications.count_documents({})
        ssot_by_type = {}
        for t in ('dewi', 'rahaza', 'collab', 'marketing_livehost'):
            ssot_by_type[t] = await db.notifications.count_documents({'type': t})

        legacy_counts = {}
        for col in LEGACY_COLLECTIONS:
            legacy_counts[col] = await db[col].count_documents({})

        print('  SSOT `notifications` collection counts:')
        print(f'    total                       = {ssot_total}')
        for t, n in ssot_by_type.items():
            print(f"    by type='{t}':{' ' * (24 - len(t))}{n}")
        print()
        print('  Legacy collection counts:')
        for col, n in legacy_counts.items():
            status = '✓ empty' if n == 0 else f'⚠ NON-EMPTY ({n})'
            print(f"    {col}{' ' * (40 - len(col))}{status}")
        print()

        total_legacy = sum(legacy_counts.values())

        if args.dry_run:
            print('  DRY-RUN — no changes made.')
            print('=' * 72)
            return

        if total_legacy > 0 and not args.force:
            print('  ❌ ABORT: Legacy collections contain documents.')
            print('     Re-run with --force to drop anyway, or with --dry-run')
            print('     to investigate.')
            print('=' * 72)
            sys.exit(2)

        # 2. Drop each legacy collection
        print('  Dropping legacy collections...')
        for col in LEGACY_COLLECTIONS:
            try:
                await db.drop_collection(col)
                print(f"    ✓ dropped {col}")
            except Exception as e:
                print(f"    ✗ {col}: {e}")
        print()
        print('  ✅ CLEANUP COMPLETE.')
        print('     All 4 legacy notification collections have been dropped.')
        print('     New SSOT writes continue to land in `notifications`.')
        print('=' * 72)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
