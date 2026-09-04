"""
P3 Data Architecture (TD-009 Part C) — Accessory Requests Consolidation
=========================================================================
Session #11.10. Consolidates 3 parallel "accessory request" systems into 1
SSOT (`dewi_accessory_requests`) with a `request_type` discriminator field.

Mapping:
    accessory_requests          → dewi_accessory_requests (request_type=vendor_additional|vendor_replacement)
    acc_internal_requests       → dewi_accessory_requests (request_type=internal_issuance)
    dewi_accessory_requests     → KEEP as SSOT (request_type=rnd_sample for legacy docs without type)

Status normalization map (legacy → SSOT):
    Legacy `acc_internal_requests`:
        Pending   → submitted
        Approved  → allocated
        Issued    → delivered
        Rejected  → rejected
        Cancelled → cancelled
    Legacy `accessory_requests` (operations.py):
        Pending   → submitted
        Approved  → allocated   (note: side-effect of child shipment creation
                                 already happened in legacy route; SSOT just
                                 records the request)
        Rejected  → rejected

Properties:
    * IDEMPOTENT — safe to re-run via (migrated_from, original_id) tuple
    * NON-DESTRUCTIVE — source collections preserved
    * DRY-RUN SUPPORTED via --dry-run
    * EMPTY-SAFE — clean no-op on empty source collections

Run:
    python migrations/migrate_acc_requests_consolidation.py             # actually migrate
    python migrations/migrate_acc_requests_consolidation.py --dry-run   # preview

Note:
    Migrations A+B from FORENSIC_04 (`acc_items` → `rahaza_materials`,
    `acc_stock_movements` → `rahaza_material_movements`) are already covered
    by `migrate_accessories.py` (Session #7). This script handles the only
    remaining piece: `acc_internal_requests` → `dewi_accessory_requests`,
    plus the orphan `accessory_requests` collection (operations.py).
"""
from __future__ import annotations
import argparse
import sys
import os
import uuid
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


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


# ── Status mapping (legacy → SSOT) ────────────────────────────────────────────
_STATUS_INTERNAL = {
    'Pending':   'submitted',
    'Approved':  'allocated',
    'Issued':    'delivered',
    'Rejected':  'rejected',
    'Cancelled': 'cancelled',
    # already-SSOT statuses pass-through
    'submitted': 'submitted',
    'allocated': 'allocated',
    'delivered': 'delivered',
    'rejected':  'rejected',
    'cancelled': 'cancelled',
    'draft':     'draft',
}

_STATUS_VENDOR = {
    'Pending':   'submitted',
    'Approved':  'allocated',
    'Rejected':  'rejected',
    'Cancelled': 'cancelled',
    'submitted': 'submitted',
    'allocated': 'allocated',
    'rejected':  'rejected',
    'cancelled': 'cancelled',
}


def _norm_status(s, mapping: dict) -> str:
    if not s:
        return 'submitted'
    return mapping.get(s, 'submitted')


# ─────────────────────────────────────────────────────────────────────────────
# Flow A: acc_internal_requests → dewi_accessory_requests
#   request_type='internal_issuance'
#
# Source schema (acc_internal_requests):
#   id, request_number, divisi, requester_name, purpose, needed_by,
#   items[{acc_id, acc_name, qty_requested, ...}], status, admin_notes,
#   issued_by, issued_at, approved_by, approved_at, rejected_by, rejected_at,
#   created_by, created_at, updated_at
#
# Target schema (dewi_accessory_requests):
#   id, request_code, request_type, sample_request_id, style_id, style_code,
#   style_name, items[{material_code, material_name, qty, unit, notes}],
#   urgent, needed_by_date, notes, status, requester_id, requester_name,
#   allocated_by, allocated_at, delivered_by, delivered_at, rejection_reason,
#   created_at, updated_at
#   + new optional fields: divisi, purpose, admin_notes, ref_number
# ─────────────────────────────────────────────────────────────────────────────

def _project_internal_item(item: dict) -> dict:
    return {
        'material_code': item.get('acc_code') or item.get('material_code', '') or item.get('acc_id', ''),
        'material_name': item.get('acc_name') or item.get('material_name', ''),
        'qty':           float(item.get('qty_requested', item.get('qty', 0)) or 0),
        'unit':          item.get('unit', 'pcs'),
        'notes':         item.get('notes', ''),
    }


def _project_internal(doc: dict) -> dict:
    return {
        'id':                doc.get('id') or str(uuid.uuid4()),
        'request_code':      doc.get('request_number') or doc.get('request_code') or '',
        'request_type':      'internal_issuance',
        'sample_request_id': '',
        'style_id':          '',
        'style_code':        '',
        'style_name':        '',
        'items':             [_project_internal_item(i) for i in doc.get('items', []) or []],
        'urgent':            False,
        'needed_by_date':    doc.get('needed_by', ''),
        'notes':             doc.get('purpose', '') or doc.get('admin_notes', ''),
        # internal_issuance specific extras
        'divisi':            doc.get('divisi', ''),
        'purpose':           doc.get('purpose', ''),
        'admin_notes':       doc.get('admin_notes', ''),
        'status':            _norm_status(doc.get('status'), _STATUS_INTERNAL),
        'requester_id':      '',  # legacy didn't carry user id
        'requester_name':    doc.get('requester_name') or doc.get('created_by', ''),
        'allocated_by':      doc.get('approved_by'),
        'allocated_at':      doc.get('approved_at'),
        'delivered_by':      doc.get('issued_by'),
        'delivered_at':      doc.get('issued_at'),
        'rejection_reason':  doc.get('admin_notes') if doc.get('status') == 'Rejected' else None,
        'rejected_by':       doc.get('rejected_by'),
        'rejected_at':       doc.get('rejected_at'),
        'created_at':        doc.get('created_at') or _now_dt(),
        'updated_at':        doc.get('updated_at') or _now_dt(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Flow B: accessory_requests (operations.py) → dewi_accessory_requests
#   request_type='vendor_additional' or 'vendor_replacement'
#
# Source schema (accessory_requests):
#   id, request_number, request_type ('ADDITIONAL'|'REPLACEMENT'),
#   vendor_id, original_shipment_id, po_id, po_number,
#   items[{accessory_code, accessory_name, requested_qty, unit, ...}],
#   total_requested_qty, reason, status, admin_notes,
#   approved_by, approved_at, child_shipment_id, child_shipment_number,
#   created_by, created_at, updated_at
# ─────────────────────────────────────────────────────────────────────────────

_VENDOR_TYPE = {'ADDITIONAL': 'vendor_additional', 'REPLACEMENT': 'vendor_replacement'}


def _project_vendor_item(item: dict) -> dict:
    return {
        'material_code': item.get('accessory_code') or item.get('material_code', ''),
        'material_name': item.get('accessory_name') or item.get('material_name', ''),
        'qty':           float(item.get('requested_qty', item.get('qty', 0)) or 0),
        'unit':          item.get('unit', 'pcs'),
        'notes':         item.get('notes', ''),
    }


def _project_vendor(doc: dict) -> dict:
    legacy_type = (doc.get('request_type') or '').upper()
    return {
        'id':                doc.get('id') or str(uuid.uuid4()),
        'request_code':      doc.get('request_number') or doc.get('request_code') or '',
        'request_type':      _VENDOR_TYPE.get(legacy_type, 'vendor_additional'),
        'sample_request_id': '',
        'style_id':          '',
        'style_code':        '',
        'style_name':        '',
        'items':             [_project_vendor_item(i) for i in doc.get('items', []) or []],
        'urgent':            False,
        'needed_by_date':    '',
        'notes':             doc.get('reason', '') or doc.get('admin_notes', ''),
        # vendor-specific extras
        'vendor_id':              doc.get('vendor_id', ''),
        'original_shipment_id':   doc.get('original_shipment_id'),
        'po_id':                  doc.get('po_id'),
        'po_number':              doc.get('po_number', ''),
        'child_shipment_id':      doc.get('child_shipment_id'),
        'child_shipment_number':  doc.get('child_shipment_number', ''),
        'total_requested_qty':    doc.get('total_requested_qty'),
        'admin_notes':            doc.get('admin_notes', ''),
        'status':                 _norm_status(doc.get('status'), _STATUS_VENDOR),
        'requester_id':           '',
        'requester_name':         doc.get('created_by', ''),
        'allocated_by':           doc.get('approved_by'),
        'allocated_at':           doc.get('approved_at'),
        'delivered_by':           None,
        'delivered_at':           None,
        'rejection_reason':       doc.get('admin_notes') if doc.get('status') == 'Rejected' else None,
        'created_at':             doc.get('created_at') or _now_dt(),
        'updated_at':             doc.get('updated_at') or _now_dt(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Migration runner
# ─────────────────────────────────────────────────────────────────────────────

async def _migrate_collection(
    db, *, source_col: str, projector, dry_run: bool,
) -> dict:
    """Generic migration runner. Source → dewi_accessory_requests w/ idempotency."""
    stats = {
        'source':         source_col,
        'target':         'dewi_accessory_requests',
        'total_source':   0,
        'already_migrated': 0,
        'migrated_now':   0,
        'skipped':        0,
    }
    stats['total_source'] = await db[source_col].count_documents({})
    if stats['total_source'] == 0:
        return stats

    async for doc in db[source_col].find({}):
        original_id = doc.get('id') or str(doc.get('_id'))
        existing = await db.dewi_accessory_requests.find_one({
            'migrated_from': source_col,
            'original_id':   original_id,
        })
        if existing:
            stats['already_migrated'] += 1
            continue

        mapped = projector(doc)
        mapped['migrated_from'] = source_col
        mapped['original_id']   = original_id
        mapped['migrated_at']   = _now_iso()

        if dry_run:
            stats['skipped'] += 1
        else:
            try:
                await db.dewi_accessory_requests.insert_one(mapped)
                stats['migrated_now'] += 1
            except Exception as e:
                print(f"  [WARN] insert failed for {source_col}/{original_id}: {e}")
                stats['skipped'] += 1

    return stats


def _print_stats(label: str, stats: dict, dry_run: bool):
    print(f"\n--- {label} ---")
    print(f"  Source ({stats['source']:<32}): {stats['total_source']} docs")
    print(f"  Already migrated:                 {stats['already_migrated']}")
    action = 'Would migrate' if dry_run else 'Migrated now'
    print(f"  {action:<24}:          {stats['skipped'] if dry_run else stats['migrated_now']}")
    if not dry_run:
        print(f"  Skipped (errors):                 {stats['skipped']}")


async def main():
    parser = argparse.ArgumentParser(
        description='P3 TD-009 — Accessory Requests Consolidation Migration')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without writing to DB')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 72)
    print('  P3 TD-009 — Accessory Requests Consolidation Migration')
    print('=' * 72)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    print(f'  Mode:        {"DRY-RUN (no writes)" if args.dry_run else "LIVE (will write)"}')
    print('  Target SSOT: dewi_accessory_requests')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        stats_a = await _migrate_collection(
            db, source_col='acc_internal_requests',
            projector=_project_internal, dry_run=args.dry_run)
        _print_stats(
            'Flow A: acc_internal_requests → dewi_accessory_requests (internal_issuance)',
            stats_a, args.dry_run)

        stats_b = await _migrate_collection(
            db, source_col='accessory_requests',
            projector=_project_vendor, dry_run=args.dry_run)
        _print_stats(
            'Flow B: accessory_requests → dewi_accessory_requests (vendor_additional/replacement)',
            stats_b, args.dry_run)

        # Summary
        tot_src = stats_a['total_source'] + stats_b['total_source']
        tot_mig = stats_a['migrated_now'] + stats_b['migrated_now']
        tot_alr = stats_a['already_migrated'] + stats_b['already_migrated']
        tot_skp = stats_a['skipped'] + stats_b['skipped']

        print('\n' + '=' * 72)
        print('  Summary')
        print('=' * 72)
        print(f'  Total source documents:       {tot_src}')
        print(f'  Already migrated (idempotent):{tot_alr}')
        if args.dry_run:
            print(f'  Would migrate this run:       {tot_skp}')
            print()
            print('  DRY-RUN COMPLETE. No data was written.')
        else:
            print(f'  Migrated this run:            {tot_mig}')
            print(f'  Skipped (errors):             {tot_skp}')
            print()
            print('  ✅ MIGRATION COMPLETE.')
            print('     Source collections preserved (deletion deferred — monitor 1 week).')
        print('=' * 72)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
