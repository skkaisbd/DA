"""
Session #11.16 Phase B — Drop Legacy `invoices` + `payments` Collections
========================================================================
Following Session #11.16 Phase B refactor of `routes/finance.py` to stub
mode (all reads return [], all writes return 410 Gone), these 2 legacy
landing collections can now be dropped. The corresponding indexes in
`server.py` (6 lines) are also removed in the same session.

Collections to drop:
  1. invoices  — legacy generic AR+AP+Maklon (now split into
                 `rahaza_ar_invoices` / `rahaza_ap_invoices` /
                 `dewi_maklon_invoices`)
  2. payments  — legacy generic payment ledger (now split per-domain into
                 `rahaza_ar_receipts` / `rahaza_ap_payments` /
                 `dewi_maklon_payments` / `dewi_maklon_advance_payments`)

Usage:
    # Dry-run (default): just print counts, do nothing destructive
    python migrations/drop_invoices_payments_collections.py --dry-run

    # Live drop (refuses if any target is non-empty unless --force)
    python migrations/drop_invoices_payments_collections.py

    # Force drop (DANGEROUS — only after manual review)
    python migrations/drop_invoices_payments_collections.py --force

Reference:
    /app/plan.md → Phase B (Session #11.16)
    /app/FORENSIC_04_DATA_ARCHITECTURE.md → Cluster 5 (Finance)
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
    'invoices',
    'payments',
]

SSOT_MAP = {
    'invoices':  'rahaza_ar_invoices / rahaza_ap_invoices / dewi_maklon_invoices',
    'payments':  'rahaza_ar_receipts / rahaza_ap_payments / dewi_maklon_payments',
}

# Auxiliary legacy collections (NOT dropped by this script — they remain
# functional for routing compat or aren't in our drop scope yet)
AUXILIARY_COLLECTIONS = [
    'invoice_adjustments',
    'invoice_edit_requests',
    'invoice_change_history',
]


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
        description='Session #11.16 Phase B — Drop legacy invoices + payments collections')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only report counts; do nothing destructive')
    parser.add_argument('--force', action='store_true',
                        help='Drop even if collections are non-empty (DANGEROUS)')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 78)
    print('  Session #11.16 Phase B — Drop Legacy `invoices` + `payments` Collections')
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
            'rahaza_ar_invoices':         None,
            'rahaza_ap_invoices':         None,
            'dewi_maklon_invoices':       None,
            'rahaza_ar_receipts':         None,
            'rahaza_ap_payments':         None,
            'dewi_maklon_payments':       None,
            'dewi_maklon_advance_payments': None,
        }
        for s in list(ssot_check.keys()):
            ssot_check[s] = await _count_safe(db, s)

        print('  SSOT successor counts (for context):')
        for s, n in ssot_check.items():
            disp = 'does not exist' if n == -1 else f'{n} docs'
            print(f'    {s:<32}{disp}')
        print()

        print('  Auxiliary legacy collections (NOT dropped by this script):')
        for col in AUXILIARY_COLLECTIONS:
            n = await _count_safe(db, col)
            disp = 'does not exist' if n == -1 else f'{n} docs'
            print(f'    {col:<32}{disp}')
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
        print('     Both legacy `invoices` + `payments` collections dropped.')
        print('     Backend collection count should decrease by 2 after restart.')
        print('=' * 78)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
