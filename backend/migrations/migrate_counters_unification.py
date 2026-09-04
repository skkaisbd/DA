"""
P3 TD-010 Part A — Counters Unification Migration (Session #11.11)
====================================================================
Consolidates 3 parallel sequence counter collections into 1 SSOT.

Mapping:
    `dewi_counters`    → `counters` (namespace='dewi')
    `rahaza_counters`  → `counters` (namespace='rahaza')

Source: `counters` is already the SSOT (no migration needed for itself).

Schema handling:
  - `dewi_counters` uses `{_id: key, seq: N}` — identical to SSOT
  - `rahaza_counters` uses `{name: key, seq: N}` — `name` is mapped to `_id`

Conflict resolution:
  If a key already exists in `counters` (e.g., legacy & dewi both wrote
  `lkp_2026`), the MAX(seq) wins — ensures no sequence reuse causing
  duplicate IDs in downstream collections.

Properties:
  * IDEMPOTENT — safe to re-run (uses max-seq semantics, not blind insert)
  * NON-DESTRUCTIVE — source collections preserved (drop deferred 1-week monitor)
  * DRY-RUN SUPPORTED via --dry-run
  * EMPTY-SAFE — clean no-op when sources are empty

Run:
    python migrations/migrate_counters_unification.py             # actually migrate
    python migrations/migrate_counters_unification.py --dry-run   # preview
"""
from __future__ import annotations
import argparse
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT_DIR / '.env')

import asyncio  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


async def _migrate_counters(
    db, *,
    source_col: str,
    namespace: str,
    key_field: str = '_id',
    dry_run: bool,
) -> dict:
    """Migrate a single source counter collection → SSOT `counters`.

    `key_field` is '_id' for dewi_counters / source `counters`, but
    'name' for legacy rahaza_counters.
    """
    stats = {
        'source':           source_col,
        'namespace':        namespace,
        'total_source':     0,
        'merged_max_seq':   0,
        'inserted_new':     0,
        'updated_existing': 0,
        'no_change':        0,
        'errors':           0,
    }
    stats['total_source'] = await db[source_col].count_documents({})
    if stats['total_source'] == 0:
        return stats

    async for src in db[source_col].find({}):
        try:
            key = src.get(key_field) or src.get('_id') or src.get('name')
            if not key:
                stats['errors'] += 1
                continue

            src_seq = int(src.get('seq', 0) or 0)
            existing = await db.counters.find_one({'_id': key}, {'seq': 1})

            if existing is None:
                if dry_run:
                    stats['inserted_new'] += 1
                else:
                    await db.counters.insert_one({
                        '_id':       key,
                        'seq':       src_seq,
                        'namespace': namespace,
                        'migrated_from': source_col,
                        'migrated_at':   _now_iso(),
                    })
                    stats['inserted_new'] += 1
            else:
                cur_seq = int(existing.get('seq', 0) or 0)
                if src_seq > cur_seq:
                    if dry_run:
                        stats['updated_existing'] += 1
                    else:
                        await db.counters.update_one(
                            {'_id': key},
                            {
                                '$set': {'seq': src_seq, 'migrated_at': _now_iso()},
                                '$addToSet': {
                                    'migrated_from': source_col,
                                },
                            },
                        )
                        stats['updated_existing'] += 1
                else:
                    stats['no_change'] += 1
            stats['merged_max_seq'] = max(stats['merged_max_seq'], src_seq)
        except Exception as e:
            print(f"  [WARN] migration error for {source_col}: {e}")
            stats['errors'] += 1

    return stats


def _print_stats(label: str, stats: dict, dry_run: bool):
    print(f"\n--- {label} ---")
    print(f"  Source ({stats['source']:<28}) namespace='{stats['namespace']}'")
    print(f"  Total source documents:     {stats['total_source']}")
    action = 'Would insert' if dry_run else 'Inserted'
    print(f"  {action:<24}:    {stats['inserted_new']}")
    action = 'Would update (higher seq)' if dry_run else 'Updated (higher seq)'
    print(f"  {action:<24}:    {stats['updated_existing']}")
    print(f"  Unchanged (lower/equal seq):{stats['no_change']}")
    if stats['errors']:
        print(f"  Errors:                     {stats['errors']}")


async def main():
    parser = argparse.ArgumentParser(
        description='P3 TD-010 Part A — Counters Unification Migration')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without writing to DB')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 72)
    print('  P3 TD-010 Part A — Counters Unification Migration')
    print('=' * 72)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    print(f'  Mode:        {"DRY-RUN (no writes)" if args.dry_run else "LIVE (will write)"}')
    print('  Target SSOT: counters  (with namespace discriminator)')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        stats_a = await _migrate_counters(
            db, source_col='dewi_counters', namespace='dewi',
            key_field='_id', dry_run=args.dry_run)
        _print_stats('Flow A: dewi_counters → counters (namespace=dewi)',
                     stats_a, args.dry_run)

        stats_b = await _migrate_counters(
            db, source_col='rahaza_counters', namespace='rahaza',
            key_field='name', dry_run=args.dry_run)
        _print_stats('Flow B: rahaza_counters → counters (namespace=rahaza, key=name)',
                     stats_b, args.dry_run)

        stats_c = await _migrate_counters(
            db, source_col='rahaza_bundle_counters', namespace='rahaza',
            key_field='id', dry_run=args.dry_run)
        _print_stats('Flow C: rahaza_bundle_counters → counters (namespace=rahaza, key=id)',
                     stats_c, args.dry_run)

        stats_d = await _migrate_counters(
            db, source_col='wh_counters', namespace='wms',
            key_field='_id', dry_run=args.dry_run)
        _print_stats('Flow D: wh_counters → counters (namespace=wms)',
                     stats_d, args.dry_run)

        tot_src = sum(s['total_source'] for s in (stats_a, stats_b, stats_c, stats_d))
        tot_ins = sum(s['inserted_new'] for s in (stats_a, stats_b, stats_c, stats_d))
        tot_upd = sum(s['updated_existing'] for s in (stats_a, stats_b, stats_c, stats_d))

        print('\n' + '=' * 72)
        print('  Summary')
        print('=' * 72)
        print(f'  Total source documents:       {tot_src}')
        if args.dry_run:
            print(f'  Would insert (new keys):      {tot_ins}')
            print(f'  Would update (higher seq):    {tot_upd}')
            print()
            print('  DRY-RUN COMPLETE. No data was written.')
        else:
            print(f'  Inserted (new keys):          {tot_ins}')
            print(f'  Updated (higher seq):         {tot_upd}')
            print()
            print('  ✅ MIGRATION COMPLETE.')
            print('     Source collections preserved (deletion deferred — monitor 1 week).')
        print('=' * 72)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
