"""
P2 Consolidation #12 — Shipping Flows Migration (Session #11.8)
================================================================

Purpose:
  Consolidate 4 overlapping shipping collections into 2 clear SSOTs (Single
  Source Of Truth) per FORENSIC_09_CONSOLIDATION_PLAN.md spec.

Before consolidation (4 collections, overlapping concerns):
  1. rahaza_shipments              — outbound to customer (PT Rahaza era)
  2. dewi_cmt_delivery_orders      — outbound to CMT vendor (DO/Surat Jalan)
  3. wh_delivery_notes             — outbound to customer (WMS-side)
  4. wh_cmt_dispatches             — outbound to CMT vendor (WMS-side)

After consolidation (2 clear flows):
  A. CUSTOMER SHIPPING (Outbound to Customer):
       SSOT = wh_delivery_notes
       Absorbs: rahaza_shipments (via this migration with original_id traceability)

  B. CMT DISPATCHING (Outbound to CMT vendor):
       SSOT = wh_cmt_dispatches
       Absorbs: dewi_cmt_delivery_orders (via this migration with original_id traceability)

Properties of this script:
  * IDEMPOTENT — safe to run multiple times. Detects already-migrated docs via
    `migrated_from` + `original_id` fields and skips them.
  * NON-DESTRUCTIVE — source collections are NOT deleted. Only docs are copied
    to target collections with field mapping + traceability fields.
  * DRY-RUN SUPPORTED — pass --dry-run to print what would happen without writing.

Run:
    python scripts/migrate_shipping_consolidation.py             # actually migrate
    python scripts/migrate_shipping_consolidation.py --dry-run   # just preview

Source collections remain reachable via deprecated routes (kept for backward
compat per TD-008 rule: monitor 1 week before deletion).
"""
from __future__ import annotations
import argparse
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

# Make `from database import get_db` work when running as standalone script
_ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT_DIR / '.env')

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
import asyncio  # noqa: E402


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Field mappings ────────────────────────────────────────────────────────────
#
# rahaza_shipments -> wh_delivery_notes:
#   shipment_number       → dn_number
#   order_id              → reference_id
#   order_number_snapshot → reference_number
#   customer_id           → recipient_id
#   customer_name_snapshot→ recipient_name
#   customer_address_*    → recipient_address
#   shipment_date         → shipment_date
#   driver_name           → driver_name
#   vehicle_number        → vehicle_number
#   items                 → items (passthrough)
#   status                → status
#   ... plus traceability fields:
#   migrated_from         = 'rahaza_shipments'
#   original_id           = <original _id or .id>
#   migrated_at           = ISO now
#
# dewi_cmt_delivery_orders -> wh_cmt_dispatches:
#   do_number             → dispatch_number
#   cutting_batch_id      → cutting_batch_id (passthrough)
#   cmt_partner_id        → cmt_partner_id (passthrough)
#   items                 → items (passthrough)
#   status                → status
#   issued_at/received_at → issued_at/received_at
#   ... plus traceability fields (same as above with origin='dewi_cmt_delivery_orders').

CUSTOMER_FIELD_MAP = {
    'shipment_number': 'dn_number',
    'order_id': 'reference_id',
    'order_number_snapshot': 'reference_number',
    'customer_id': 'recipient_id',
    'customer_name_snapshot': 'recipient_name',
    'customer_address_snapshot': 'recipient_address',
    'shipment_date': 'shipment_date',
    'driver_name': 'driver_name',
    'vehicle_number': 'vehicle_number',
    'items': 'items',
    'status': 'status',
    'dispatched_at': 'dispatched_at',
    'delivered_at': 'delivered_at',
    'notes': 'notes',
    'created_at': 'source_created_at',
    'created_by': 'source_created_by',
}

CMT_FIELD_MAP = {
    'do_number': 'dispatch_number',
    'cutting_batch_id': 'cutting_batch_id',
    'cmt_partner_id': 'cmt_partner_id',
    'cmt_job_id': 'cmt_job_id',
    'items': 'items',
    'status': 'status',
    'issued_at': 'issued_at',
    'received_at': 'received_at',
    'notes': 'notes',
    'created_at': 'source_created_at',
    'created_by': 'source_created_by',
}


def _map_fields(source_doc: dict, field_map: dict) -> dict:
    """Apply field mapping; passthrough fields kept as-is."""
    out = {}
    for src_key, value in source_doc.items():
        if src_key == '_id':
            continue
        out_key = field_map.get(src_key, src_key)
        out[out_key] = value
    return out


async def _migrate_collection(
    db,
    source_name: str,
    target_name: str,
    field_map: dict,
    origin_label: str,
    *,
    dry_run: bool,
) -> dict:
    source = db[source_name]
    target = db[target_name]

    stats = {'source': source_name, 'target': target_name, 'total_source': 0,
             'already_migrated': 0, 'migrated_now': 0, 'skipped': 0}

    stats['total_source'] = await source.count_documents({})
    if stats['total_source'] == 0:
        return stats

    async for doc in source.find({}):
        original_id = doc.get('id') or str(doc.get('_id'))
        # Idempotence check
        existing = await target.find_one({
            'migrated_from': origin_label,
            'original_id': original_id,
        })
        if existing:
            stats['already_migrated'] += 1
            continue

        mapped = _map_fields(doc, field_map)
        mapped['migrated_from'] = origin_label
        mapped['original_id'] = original_id
        mapped['migrated_at'] = _now_iso()
        # Keep id field if present (target collections use string id, not _id)
        if 'id' not in mapped and doc.get('id'):
            mapped['id'] = doc['id']

        if dry_run:
            stats['skipped'] += 1
        else:
            try:
                await target.insert_one(mapped)
                stats['migrated_now'] += 1
            except Exception as e:
                print(f"  [WARN] insert failed for original_id={original_id}: {e}")
                stats['skipped'] += 1

    return stats


def _print_stats(label: str, stats: dict, dry_run: bool):
    print(f"\n--- {label} ---")
    print(f"  Source ({stats['source']}):    {stats['total_source']} docs")
    print(f"  Already migrated (target):    {stats['already_migrated']}")
    print(f"  {'Would migrate' if dry_run else 'Migrated now'}: {stats['migrated_now'] if not dry_run else stats['skipped']}")
    print(f"  Skipped (errors):             {stats['skipped'] if not dry_run else 0}")


async def main():
    parser = argparse.ArgumentParser(description='Shipping Flows Consolidation Migration')
    parser.add_argument('--dry-run', action='store_true', help='Preview without writing')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'garment_erp')

    print('=' * 64)
    print('  P2 Consolidation #12 — Shipping Flows Migration')
    print('=' * 64)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    print(f'  Mode:        {"DRY-RUN (no writes)" if args.dry_run else "LIVE (will write)"}')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        # Flow A: Customer Shipping — rahaza_shipments → wh_delivery_notes
        stats_a = await _migrate_collection(
            db,
            source_name='rahaza_shipments',
            target_name='wh_delivery_notes',
            field_map=CUSTOMER_FIELD_MAP,
            origin_label='rahaza_shipments',
            dry_run=args.dry_run,
        )
        _print_stats('Flow A: Customer Shipping (rahaza_shipments → wh_delivery_notes)',
                     stats_a, args.dry_run)

        # Flow B: CMT Dispatching — dewi_cmt_delivery_orders → wh_cmt_dispatches
        stats_b = await _migrate_collection(
            db,
            source_name='dewi_cmt_delivery_orders',
            target_name='wh_cmt_dispatches',
            field_map=CMT_FIELD_MAP,
            origin_label='dewi_cmt_delivery_orders',
            dry_run=args.dry_run,
        )
        _print_stats('Flow B: CMT Dispatching (dewi_cmt_delivery_orders → wh_cmt_dispatches)',
                     stats_b, args.dry_run)

        # Summary
        total_source = stats_a['total_source'] + stats_b['total_source']
        total_migrated = stats_a['migrated_now'] + stats_b['migrated_now']
        total_already = stats_a['already_migrated'] + stats_b['already_migrated']
        total_skipped = stats_a['skipped'] + stats_b['skipped']

        print('\n' + '=' * 64)
        print('  Summary')
        print('=' * 64)
        print(f'  Total source documents:   {total_source}')
        print(f'  Already migrated:         {total_already}')
        print(f'  Migrated this run:        {total_migrated}')
        print(f'  Skipped:                  {total_skipped}')
        print()
        if args.dry_run:
            print('  DRY-RUN COMPLETE. No data was written.')
        else:
            print('  ✅ MIGRATION COMPLETE.')
            print('     Source collections preserved (deletion deferred per TD-008 — monitor 1 week).')
        print('=' * 64)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
