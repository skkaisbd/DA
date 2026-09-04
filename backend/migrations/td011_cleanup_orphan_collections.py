"""
P3 TD-011 Cleanup Orphan Collections — Session #11.13
=====================================================
Drop empty, deprecated/orphan collections after Sessions #11.9 → #11.12
consolidations.

IMPORTANT BEHAVIOR NOTE (read this first):
  After dropping a collection, server.py's startup_event() may re-create some
  of them when it calls `create_index()` on still-actively-referenced
  collections (e.g. `accessories`, `invoices`, `payments`, `warehouse_*`,
  `dewi_kol_*`). MongoDB auto-creates a collection on first index/insert.

  This is the EXPECTED behavior — these collections are still referenced by
  active routes (operations.py, finance.py, production.py, dewi_kol.py,
  dewi_warehouse_smart.py). Truly removing them requires:
    1. Deprecating/removing the routes that reference them.
    2. Removing the corresponding `create_index` calls from server.py.

  This script handles the "drop empty + safe re-create after backend restart"
  step. Truly orphaned collections (no server.py index, no route reference)
  remain permanently gone after restart (e.g. the 4 legacy notification
  collections cleaned in Session #11.12).


Categories of orphans cleaned by this script:

CATEGORY A — User-listed orphans (TD-011 baseline):
    accessories                 (replaced by rahaza_materials)
    work_orders                 (replaced by rahaza_work_orders)
    production_work_orders      (orphan)
    dewi_attendance             (replaced by rahaza_attendance)
    dewi_perf_cycles            (replaced by hris_cycles)
    dewi_perf_assignments       (replaced by hris_assignments)
    dewi_perf_kpis              (replaced by hris_kpi_assignments)
    dewi_perf_reviews           (replaced by hris_reviews)
    dewi_kol_creators           (replaced by marketing_kol_creators)
    dewi_kol_deals              (replaced by marketing_creator_deals)
    dewi_kol_samples            (replaced by marketing_creator_samples)
    invoices                    (replaced by rahaza_ar_invoices + dewi_maklon_invoices)
    rahaza_invoices             (orphan)
    payments                    (replaced by rahaza_payments + dewi_maklon_payments)
    warehouse_inbound           (orphan)
    warehouse_outbound          (orphan)
    warehouse_stock             (replaced by rahaza_material_stock)
    warehouse_transfers         (orphan)
    warehouse_items             (orphan)
    warehouse_movements         (replaced by rahaza_material_movements)
    warehouse_locations         (replaced by wh_positions)
    warehouse_opname            (replaced by wh_opname2_cycles)
    warehouse_putaway           (replaced by wh_pending_movements)

CATEGORY B — Notification SSOT cleanup (TD-010 Phase B, Session #11.12):
    dewi_notifications          (replaced by notifications SSOT, type='dewi')
    rahaza_notifications        (replaced by notifications SSOT, type='rahaza')
    collab_notifications        (replaced by notifications SSOT, type='collab')
    marketing_livehost_notifications  (replaced by notifications SSOT, type='marketing_livehost')

CATEGORY C — Counter SSOT cleanup (TD-010 Opsi A, Session #11.11):
    dewi_counters               (replaced by counters SSOT, namespace='dewi')
    rahaza_counters             (replaced by counters SSOT, namespace='rahaza')
    rahaza_bundle_counters      (replaced by counters SSOT, namespace='rahaza_bundle')
    wh_counters                 (replaced by counters SSOT, namespace='wh')

CATEGORY D — Accessory request SSOT cleanup (TD-009, Session #11.10):
    accessory_requests          (replaced by dewi_accessory_requests SSOT)
    acc_opname_sessions         (replaced by wh_opname2_cycles)
    acc_opname_lines            (replaced by wh_opname2_variances)

CATEGORY E — Opname SSOT cleanup (TD-008, Session #11.9):
    wh_opname_sessions          (replaced by wh_opname2_cycles)
    wh_opname_lines             (replaced by wh_opname2_variances)
    wh_opname_sessions2         (intermediate; replaced by wh_opname2_cycles)
    wh_fg_movements             (replaced by rahaza_fg_movements)

CATEGORY F — Other identified orphans from FORENSIC_04:
    dewi_maklon_orders          (orphan, replaced by dewi_maklon_pos)
    dewi_toko_orders            (orphan; sidebar removed)
    dewi_invoices               (orphan)
    rahaza_payments             (consolidated into dewi_maklon_payments)
    old_buyers / old_clients    (orphan)

SAFETY:
- Default DRY-RUN — only reports counts.
- Refuses to drop a collection if it contains documents (unless --force).
- Drops only collections that EXIST in the DB (silently skips non-existent).
- After drop, recommends backend restart so server.py recreates indexes for
  collections still referenced by active code (auto-recreated on first write).

Usage:
    # Dry-run (default safety)
    python migrations/td011_cleanup_orphan_collections.py --dry-run

    # Live drop (refuses if any candidate has docs)
    python migrations/td011_cleanup_orphan_collections.py

    # Force drop (drops even if collections are non-empty — DANGEROUS)
    python migrations/td011_cleanup_orphan_collections.py --force

    # Only drop specific category
    python migrations/td011_cleanup_orphan_collections.py --category B
"""
from __future__ import annotations
import argparse
import asyncio
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / '.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


CATEGORIES: dict[str, dict] = {
    'A': {
        'name': 'User-listed orphans (TD-011 baseline)',
        'collections': [
            'accessories', 'work_orders', 'production_work_orders',
            'dewi_attendance',
            'dewi_perf_cycles', 'dewi_perf_assignments', 'dewi_perf_kpis', 'dewi_perf_reviews',
            'dewi_kol_creators', 'dewi_kol_deals', 'dewi_kol_samples',
            'invoices', 'rahaza_invoices', 'payments',
            'warehouse_inbound', 'warehouse_outbound', 'warehouse_stock',
            'warehouse_transfers', 'warehouse_items', 'warehouse_movements',
            'warehouse_locations', 'warehouse_opname', 'warehouse_putaway',
        ],
    },
    'B': {
        'name': 'Notification SSOT cleanup (TD-010 Phase B, Session #11.12)',
        'collections': [
            'dewi_notifications', 'rahaza_notifications',
            'collab_notifications', 'marketing_livehost_notifications',
        ],
    },
    'C': {
        'name': 'Counter SSOT cleanup (TD-010 Opsi A, Session #11.11)',
        'collections': [
            'dewi_counters', 'rahaza_counters',
            'rahaza_bundle_counters', 'wh_counters',
        ],
    },
    'D': {
        'name': 'Accessory request SSOT cleanup (TD-009, Session #11.10)',
        'collections': [
            'accessory_requests',
            'acc_opname_sessions', 'acc_opname_lines',
        ],
    },
    'E': {
        'name': 'Opname SSOT cleanup (TD-008, Session #11.9)',
        'collections': [
            'wh_opname_sessions', 'wh_opname_lines', 'wh_opname_sessions2',
            'wh_fg_movements',
        ],
    },
    'F': {
        'name': 'Other identified orphans (FORENSIC_04)',
        'collections': [
            'dewi_maklon_orders', 'dewi_toko_orders', 'dewi_invoices',
            'rahaza_payments',
            'old_buyers', 'old_clients', 'dewi_old_clients',
            'toko_channels', 'toko_pricing', 'toko_products', 'toko_orders',
            'wms_locations', 'wms_items', 'wms_movements', 'wms_stock',
            'wms_inbound', 'wms_outbound', 'wms_putaway',
        ],
    },
}


def _hr(char='═', width=78):
    print(char * width)


async def main():
    parser = argparse.ArgumentParser(
        description='P3 TD-011 Cleanup — Drop empty orphan collections')
    parser.add_argument('--dry-run', action='store_true',
                        help='Only report; never destruct')
    parser.add_argument('--force', action='store_true',
                        help='Drop even if non-empty (DANGEROUS)')
    parser.add_argument(
        '--category', choices=list(CATEGORIES.keys()), default=None,
        help='Only act on a specific category (default: all categories)')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    _hr()
    print('  P3 TD-011 Cleanup — Drop Orphan Collections (Session #11.13)')
    _hr()
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    if args.dry_run:
        mode = 'DRY-RUN (no destructive action)'
    elif args.force:
        mode = 'LIVE + FORCE (drops even non-empty)'
    else:
        mode = 'LIVE (refuses if non-empty)'
    print(f'  Mode:        {mode}')
    print(f'  Category:    {args.category or "ALL"}')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]
        all_existing = set(await db.list_collection_names())
        total_before = len(all_existing)

        per_category_summary = []
        all_drops: list[tuple[str, int]] = []
        all_skips_nonexistent: list[str] = []
        all_refuse_nonempty: list[tuple[str, int]] = []

        categories = (
            {args.category: CATEGORIES[args.category]}
            if args.category else CATEGORIES
        )

        for key, cat in categories.items():
            print(f'  ── Category {key}: {cat["name"]} ──')
            cat_drops, cat_skips, cat_refuse = [], [], []
            for col in cat['collections']:
                if col not in all_existing:
                    cat_skips.append(col)
                    continue
                n = await db[col].count_documents({})
                if n == 0:
                    cat_drops.append((col, 0))
                else:
                    cat_refuse.append((col, n))
            for col in cat_drops:
                print(f"    ✓ would drop (empty): {col[0]}")
            for col in cat_skips:
                print(f"    ⊘ skip (not in DB):   {col}")
            for col, n in cat_refuse:
                print(f"    ⚠ REFUSE (has docs):  {col} ({n})")
            print()
            all_drops.extend(cat_drops)
            all_skips_nonexistent.extend(cat_skips)
            all_refuse_nonempty.extend(cat_refuse)
            per_category_summary.append({
                'key': key, 'name': cat['name'],
                'drops': cat_drops, 'skips': cat_skips, 'refuse': cat_refuse,
            })

        _hr()
        print('  SUMMARY')
        _hr()
        print(f'  DB collections before:                 {total_before}')
        print(f'  Will DROP (empty + on whitelist):      {len(all_drops)}')
        print(f'  Will SKIP (not present in DB):         {len(all_skips_nonexistent)}')
        print(f'  Will REFUSE (non-empty, on whitelist): {len(all_refuse_nonempty)}')
        print()
        if all_refuse_nonempty:
            print('  ⚠ NON-EMPTY collections that need manual review:')
            for col, n in all_refuse_nonempty:
                print(f'    - {col} ({n} docs)')
            print()

        if args.dry_run:
            print('  DRY-RUN — no changes made. Re-run without --dry-run to drop.')
            _hr()
            return

        if all_refuse_nonempty and not args.force:
            print('  ❌ ABORT: Some candidate collections contain documents.')
            print('     Investigate them, then either:')
            print('       - drop the data first manually, OR')
            print('       - use --force to drop anyway (DANGEROUS).')
            _hr()
            sys.exit(2)

        # Drop phase
        print('  Dropping empty collections...')
        dropped, errors = 0, 0
        for col, _ in all_drops:
            try:
                await db.drop_collection(col)
                print(f'    ✓ dropped {col}')
                dropped += 1
            except Exception as e:
                print(f'    ✗ {col}: {e}')
                errors += 1
        if args.force:
            for col, n in all_refuse_nonempty:
                try:
                    await db.drop_collection(col)
                    print(f'    ⚠ FORCED drop of non-empty {col} (had {n} docs)')
                    dropped += 1
                except Exception as e:
                    print(f'    ✗ {col}: {e}')
                    errors += 1
        print()

        all_existing_after = await db.list_collection_names()
        total_after = len(all_existing_after)

        _hr()
        print(f'  ✅ DONE. Collections: {total_before} → {total_after} ({total_before - total_after} removed)')
        print(f'     Dropped: {dropped} | Errors: {errors}')
        print()
        if dropped > 0:
            print('  ⚠ RECOMMENDED NEXT STEP:')
            print('     Restart the backend to allow server.py @startup_event')
            print('     to recreate indexes for collections still referenced by')
            print('     active routes (e.g. accessories, invoices, payments,')
            print('     warehouse_stock, warehouse_movements, dewi_kol_*).')
            print('     Command:   sudo supervisorctl restart backend')
        _hr()

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
