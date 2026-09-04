"""Migration 2026-07-16 — Phase A Self-Heal Child Jobs (GUIDELINE_CMT_FLOW.md §9.4)

Menyembuhkan data existing yang rusak akibat Bug A: shipment
ADDITIONAL/REPLACEMENT yang inspeksinya sudah submit tapi child
production_job tidak pernah dibuat (karena guard status='Received'
di vendor_shipment.py:414 fail — sudah di-fix Phase A).

Sifat:
- **IDEMPOTENT** — aman dijalankan berkali-kali.
- Read-only untuk shipment yang sudah punya child_job.
- Print counter (candidate, created, skipped_no_parent, skipped_zero_qty,
  skipped_already_exists).
- Exit 0 saat sukses.

Runbook:
    cd /app/backend && python3 scripts/migrations/2026_07_16_phase_a_self_heal_child_jobs.py [--dry-run]

Opsi:
    --dry-run   Cek saja, jangan tulis. Bagus untuk audit sebelum eksekusi.
"""
import argparse
import asyncio
import logging
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient

# Import helper dari route module (path setup untuk /app/backend)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from routes.vendor_shipment import _create_child_job_from_inspection

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('migrate.phase_a_self_heal')

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


async def run(dry_run: bool):
    log.info(f'[migrate:phase_a_self_heal] MONGO_URL={MONGO_URL}  DB={DB_NAME}  dry_run={dry_run}')
    mongo = AsyncIOMotorClient(MONGO_URL)
    db = mongo[DB_NAME]

    # Cari kandidat: shipments ADDITIONAL/REPLACEMENT yang inspection_status=Inspected
    # dan belum punya production_job dengan vendor_shipment_id=shipment.id.
    candidates = await db.vendor_shipments.find({
        'parent_shipment_id': {'$ne': None, '$exists': True},
        'inspection_status': 'Inspected',
    }).to_list(None)
    # Filter out empty string parent_shipment_id
    candidates = [c for c in candidates if c.get('parent_shipment_id')]

    counter = {
        'candidates': len(candidates),
        'created': 0,
        'skipped_already_exists': 0,
        'skipped_no_parent': 0,
        'skipped_no_inspection': 0,
        'skipped_zero_qty': 0,
        'promoted_status_only': 0,
    }
    log.info(f'  Kandidat: {counter["candidates"]} shipment ADDITIONAL/REPLACEMENT ter-inspect.')

    for ship in candidates:
        sid = ship['id']
        # Skip jika sudah ada production_job
        already = await db.production_jobs.find_one({'vendor_shipment_id': sid}, {'_id': 0, 'id': 1})
        if already:
            counter['skipped_already_exists'] += 1
            continue
        # Skip jika parent shipment tidak punya parent_job
        parent_job = await db.production_jobs.find_one(
            {'vendor_shipment_id': ship['parent_shipment_id']}, {'_id': 0, 'id': 1}
        )
        if not parent_job:
            counter['skipped_no_parent'] += 1
            log.info(f'  ⚠ SKIP  shipment {ship.get("shipment_number")} '
                  f'({sid[:8]}): parent belum punya production_job.')
            continue
        # Ambil inspection
        insp = await db.vendor_material_inspections.find_one({'shipment_id': sid})
        if not insp:
            counter['skipped_no_inspection'] += 1
            log.info(f'  ⚠ SKIP  shipment {ship.get("shipment_number")} '
                  f'({sid[:8]}): inspection_status=Inspected tapi tidak ada record.')
            continue
        insp_items = await db.vendor_material_inspection_items.find(
            {'inspection_id': insp['id']}
        ).to_list(None)
        material_items = [i for i in insp_items if i.get('item_type') != 'accessory']
        total_received = sum(int(i.get('received_qty', 0) or 0) for i in material_items)
        if total_received <= 0:
            counter['skipped_zero_qty'] += 1
            log.info(f'  ⚠ SKIP  shipment {ship.get("shipment_number")} '
                  f'({sid[:8]}): total_received=0.')
            continue

        if dry_run:
            counter['created'] += 1
            log.info(f'  → WOULD CREATE child_job untuk shipment {ship.get("shipment_number")} '
                  f'({sid[:8]}): total_received={total_received}, parent_job_id={parent_job["id"][:8]}...')
        else:
            # Kalau status masih 'Sent', promote juga (Phase A semantics)
            if ship.get('status') != 'Received':
                await db.vendor_shipments.update_one(
                    {'id': sid},
                    {'$set': {'status': 'Received', 'received_at': ship.get('inspected_at')
                              or ship.get('updated_at'), 'updated_at': ship.get('updated_at')}}
                )
                ship['status'] = 'Received'
                counter['promoted_status_only'] += 1
            child_id = await _create_child_job_from_inspection(
                db, ship, insp, insp_items, actor='migration:phase_a_self_heal'
            )
            if child_id:
                counter['created'] += 1
                log.info(f'  ✓ CREATED child_job {child_id[:8]}... untuk shipment '
                      f'{ship.get("shipment_number")} ({sid[:8]})')
            else:
                # Should not happen given filters above, but log for safety.
                counter['skipped_zero_qty'] += 1
                log.info(f'  ⚠ SKIP (helper returned None) shipment {ship.get("shipment_number")}')

    log.info('')
    log.info('  ─── COUNTER ─────────────────────────────────────────')
    for k, v in counter.items():
        log.info(f'    {k:26s}= {v}')
    log.info('  ─────────────────────────────────────────────────────')

    # Idempotency verification: re-scan and expect 0 new candidates
    if not dry_run and counter['created'] > 0:
        remaining = 0
        recheck = await db.vendor_shipments.find({
            'parent_shipment_id': {'$ne': None, '$exists': True},
            'inspection_status': 'Inspected',
        }).to_list(None)
        for ship in recheck:
            if not ship.get('parent_shipment_id'):
                continue
            if await db.production_jobs.find_one({'vendor_shipment_id': ship['id']}, {'_id': 0, 'id': 1}):
                continue
            parent_job = await db.production_jobs.find_one(
                {'vendor_shipment_id': ship['parent_shipment_id']}, {'_id': 0, 'id': 1}
            )
            if not parent_job:
                continue
            insp = await db.vendor_material_inspections.find_one({'shipment_id': ship['id']})
            if not insp:
                continue
            insp_items = await db.vendor_material_inspection_items.find(
                {'inspection_id': insp['id']}
            ).to_list(None)
            total_received = sum(int(i.get('received_qty', 0) or 0)
                                 for i in insp_items if i.get('item_type') != 'accessory')
            if total_received > 0:
                remaining += 1
        log.info(f'  Idempotency check: {remaining} kandidat tersisa (harus 0).')
        if remaining > 0:
            log.info('  ✗ IDEMPOTENCY VIOLATED — re-run should have 0 pending')
            mongo.close()
            sys.exit(2)

    mongo.close()
    log.info('  ✓ Migration complete.')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true',
                    help='Cek saja, jangan tulis.')
    args = ap.parse_args()
    asyncio.run(run(args.dry_run))
