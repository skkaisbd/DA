"""Migration 2026-07-18 — Phase D backfill buyer_shipment_items.po_id / po_number
and buyer_shipments.po_ids[] (PHASE_D_CONSOLIDATED_BUYER_SHIPMENT.md).

WHY: Phase D moves fulfillment/auto-close to be keyed on the ITEM's po_id so a
single consolidated surat jalan can span multiple POs. Legacy items only carry
po_item_id and legacy headers only carry a single po_id. This migration:
  - sets buyer_shipment_items.po_id + po_number (resolved via po_items -> production_pos),
  - sets buyer_shipments.po_ids[] = distinct item po_ids (fallback header po_id),
  - sets buyer_shipments.consolidated flag.

Sifat:
- IDEMPOTENT — aman dijalankan berkali-kali (skip yang sudah ter-backfill).
- Tidak menghapus / menimpa data yang sudah benar.
- Exit 0 saat sukses.

Runbook:
    cd /app/backend && python3 scripts/migrations/2026_07_18_phase_d_backfill_buyer_item_po_id.py [--dry-run]
"""
import argparse
import asyncio
import logging
import os
import sys

from motor.motor_asyncio import AsyncIOMotorClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('migrate.phase_d_backfill')

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


async def run(dry_run: bool):
    log.info(f'[migrate:phase_d] MONGO_URL={MONGO_URL} DB={DB_NAME} dry_run={dry_run}')
    db = AsyncIOMotorClient(MONGO_URL)[DB_NAME]

    # ── 1) Backfill items po_id / po_number ─────────────────────────────────
    items = await db.buyer_shipment_items.find(
        {'$or': [{'po_id': {'$exists': False}}, {'po_id': None}, {'po_id': ''}]},
        {'_id': 0, 'id': 1, 'po_item_id': 1}).to_list(None)
    # cache po_item -> (po_id, po_number)
    poi_ids = list({it.get('po_item_id') for it in items if it.get('po_item_id')})
    poi_map = {}
    if poi_ids:
        async for d in db.po_items.find({'id': {'$in': poi_ids}}, {'_id': 0, 'id': 1, 'po_id': 1}):
            poi_map[d['id']] = d.get('po_id')
    po_ids_needed = list({v for v in poi_map.values() if v})
    po_num_map = {}
    if po_ids_needed:
        async for p in db.production_pos.find({'id': {'$in': po_ids_needed}}, {'_id': 0, 'id': 1, 'po_number': 1}):
            po_num_map[p['id']] = p.get('po_number', '')

    item_updated = 0
    item_unresolved = 0
    for it in items:
        po_id = poi_map.get(it.get('po_item_id'))
        if not po_id:
            item_unresolved += 1
            continue
        if not dry_run:
            await db.buyer_shipment_items.update_one(
                {'id': it['id']},
                {'$set': {'po_id': po_id, 'po_number': po_num_map.get(po_id, '')}})
        item_updated += 1

    # ── 2) Backfill headers po_ids[] + consolidated flag ────────────────────
    ships = await db.buyer_shipments.find({}, {'_id': 0, 'id': 1, 'po_id': 1, 'po_ids': 1}).to_list(None)
    ship_updated = 0
    for s in ships:
        item_po_ids = await db.buyer_shipment_items.distinct('po_id', {'shipment_id': s['id']})
        item_po_ids = [p for p in item_po_ids if p]
        if not item_po_ids and s.get('po_id'):
            item_po_ids = [s['po_id']]
        new_po_ids = list(dict.fromkeys(item_po_ids))
        if set(new_po_ids) == set(s.get('po_ids') or []) and 'po_ids' in s:
            continue  # already correct
        if not dry_run:
            await db.buyer_shipments.update_one(
                {'id': s['id']},
                {'$set': {'po_ids': new_po_ids, 'consolidated': len(new_po_ids) > 1}})
        ship_updated += 1

    # ── 3) Backfill items ordered_qty (Phase D consolidated create omitted it) ─
    # Consolidated create payloads don't send ordered_qty per line, so existing
    # multi-PO SJ items were stored with ordered_qty=0 → Total Order/progress show
    # 0. Resolve from the origin po_item's qty. Idempotent (only touches 0/missing).
    oq_items = await db.buyer_shipment_items.find(
        {'$or': [{'ordered_qty': {'$exists': False}}, {'ordered_qty': 0}, {'ordered_qty': None}]},
        {'_id': 0, 'id': 1, 'po_item_id': 1}).to_list(None)
    oq_poi_ids = list({it.get('po_item_id') for it in oq_items if it.get('po_item_id')})
    oq_qty_map = {}
    if oq_poi_ids:
        async for d in db.po_items.find({'id': {'$in': oq_poi_ids}}, {'_id': 0, 'id': 1, 'qty': 1}):
            oq_qty_map[d['id']] = int(d.get('qty', 0) or 0)
    oq_updated = 0
    for it in oq_items:
        q = oq_qty_map.get(it.get('po_item_id'), 0)
        if q <= 0:
            continue
        if not dry_run:
            await db.buyer_shipment_items.update_one({'id': it['id']}, {'$set': {'ordered_qty': q}})
        oq_updated += 1

    log.info('─' * 60)
    log.info(f'items scanned (missing po_id) : {len(items)}')
    log.info(f'items backfilled              : {item_updated}')
    log.info(f'items unresolved (no po_item) : {item_unresolved}')
    log.info(f'shipments po_ids[] updated    : {ship_updated} / {len(ships)}')
    log.info(f'items ordered_qty backfilled  : {oq_updated} / {len(oq_items)}')
    log.info('[migrate:phase_d] DONE' + (' (dry-run, no writes)' if dry_run else ''))
    return 0


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()
    raise SystemExit(asyncio.run(run(args.dry_run)))
