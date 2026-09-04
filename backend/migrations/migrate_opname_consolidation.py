"""
P3 Data Architecture (TD-008) — Opname Systems Consolidation (Session #11.9)
============================================================================

Purpose:
  Consolidate 3 parallel opname systems into 1 SSOT (Single Source Of Truth)
  per FORENSIC_04_DATA_ARCHITECTURE.md Cluster 3 (Warehouse/Inventory).

Before consolidation (3 generations + dead refs):
  GEN1 (legacy)      — warehouse_opname              (routes: warehouse.py)
  GEN2 (scanner)     — wh_opname_sessions + wh_opname_lines (routes: wms_opname.py)
  GEN3 SSOT          — wh_opname_sessions2           (routes: wms_opname2.py,
                                                        dewi_accessories_full.py)
  DEAD REFS          — wh_opname2_cycles + wh_opname2_variances (never existed,
                       only referenced by wms_ai_insights.py — fixed in same session)

After consolidation (1 SSOT with domain discriminator):
  wh_opname_sessions2
    - domain='warehouse_legacy'  ← absorbs warehouse_opname  (GEN1)
    - domain='warehouse_scan'    ← absorbs wh_opname_sessions/lines (GEN2)
    - domain='warehouse'         ← native cycle/full count via wms_opname2.py (GEN3)
    - domain='accessory'         ← already migrated via Session #7 (kept untouched)

Properties of this script:
  * IDEMPOTENT — safe to run multiple times. Detects already-migrated docs via
    `migrated_from` + `original_id` fields and skips them.
  * NON-DESTRUCTIVE — source collections are NOT deleted. Only docs are copied
    to target with field mapping + traceability fields.
  * DRY-RUN SUPPORTED — pass --dry-run to preview without writing.
  * EMPTY-SAFE — clean execution when source collections are empty.

Run:
    python migrations/migrate_opname_consolidation.py             # actually migrate
    python migrations/migrate_opname_consolidation.py --dry-run   # just preview

Source collections remain reachable via deprecated routes (kept for backward
compat per TD-008 rule: monitor 1 week before deletion).
"""
from __future__ import annotations
import argparse
import sys
import os
import uuid
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


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


# ── Status mappings (legacy → SSOT) ───────────────────────────────────────────
# Legacy wh_opname_sessions statuses: draft, in_progress, completed, cancelled
# Legacy warehouse_opname statuses (free-form): Active, Completed, Cancelled, etc.
# SSOT wh_opname_sessions2 statuses: open, counted, pending_approval, approved, cancelled

_STATUS_GEN2_TO_SSOT = {
    'draft':       'open',
    'in_progress': 'open',
    'completed':   'approved',
    'cancelled':   'cancelled',
}

_STATUS_GEN1_TO_SSOT = {
    'Active':      'open',
    'In Progress': 'open',
    'Completed':   'approved',
    'Cancelled':   'cancelled',
    'cancelled':   'cancelled',
    'completed':   'approved',
    'active':      'open',
}


def _norm_status_gen2(s: str | None) -> str:
    if not s:
        return 'open'
    return _STATUS_GEN2_TO_SSOT.get(s, 'open')


def _norm_status_gen1(s: str | None) -> str:
    if not s:
        return 'open'
    return _STATUS_GEN1_TO_SSOT.get(s, 'open')


# ─────────────────────────────────────────────────────────────────────────────
# GEN2 Migration: wh_opname_sessions + wh_opname_lines → wh_opname_sessions2
#
# Session field mapping:
#   ref_number              → session_no
#   rack_id                 → scope_id
#   rack_code/name          → scope_label (rack_code preferred)
#   status                  → status (normalized)
#   total_positions         → total_items
#   scanned_positions       → counted_items
#   started_at/by           → created_at/by
#   completed_at/by         → approved_at/by
#   notes                   → notes
#
# Lines (wh_opname_lines) projected into embedded count_items[]:
#   position_id             → position_id
#   position_barcode        → position_barcode
#   system_material_code    → material_code
#   system_material_name    → material_name
#   system_qty              → system_qty
#   counted_qty             → counted_qty
#   diff                    → variance
#   system_unit             → unit
#   notes                   → notes
#   scanned                 → counted (bool)
# ─────────────────────────────────────────────────────────────────────────────

def _project_gen2_line(line: dict) -> dict:
    return {
        'position_id':       line.get('position_id'),
        'position_barcode':  line.get('position_barcode', ''),
        'material_code':     line.get('counted_material_code') or line.get('system_material_code', ''),
        'material_name':     line.get('counted_material_name') or line.get('system_material_name', ''),
        'system_qty':        float(line.get('system_qty', 0) or 0),
        'counted_qty':       line.get('counted_qty'),
        'variance':          line.get('diff'),
        'variance_pct':      None,
        'unit':              line.get('system_unit', 'pcs'),
        'notes':             line.get('notes', ''),
        'counted':           bool(line.get('scanned')),
    }


async def _project_gen2_session(db, session: dict) -> dict:
    """Build SSOT-shaped doc from GEN2 wh_opname_sessions + its lines."""
    lines = await db.wh_opname_lines.find(
        {'session_id': session.get('id')}, {'_id': 0}
    ).to_list(2000)
    count_items = [_project_gen2_line(ln) for ln in lines]
    counted_items = sum(1 for ci in count_items if ci.get('counted'))
    variance_items = sum(
        1 for ci in count_items
        if ci.get('counted') and (ci.get('variance') or 0) != 0
    )

    return {
        'id':              session.get('id') or str(uuid.uuid4()),
        'session_no':      session.get('ref_number', ''),
        'mode':            'cycle_count',
        'scope_type':      'rack',
        'scope_id':        session.get('rack_id', ''),
        'scope_label':     session.get('rack_code') or session.get('rack_name', ''),
        'status':          _norm_status_gen2(session.get('status')),
        'domain':          'warehouse_scan',
        'count_items':     count_items,
        'total_items':     int(session.get('total_positions', len(count_items)) or len(count_items)),
        'counted_items':   counted_items,
        'total_variance_items': variance_items,
        'total_variance_value': 0.0,
        'notes':           session.get('notes', ''),
        'created_at':      session.get('started_at') or _now_dt(),
        'created_by':      session.get('started_by_name') or session.get('started_by', 'migration'),
        'counted_by':      session.get('completed_by'),
        'approved_by':     session.get('completed_by'),
        'approved_at':     session.get('completed_at'),
        'closed_at':       session.get('completed_at') or session.get('cancelled_at'),
    }


# ─────────────────────────────────────────────────────────────────────────────
# GEN1 Migration: warehouse_opname → wh_opname_sessions2
#
# warehouse_opname shape is loose/legacy. Map common fields:
#   opname_number           → session_no
#   warehouse_id            → scope_id
#   warehouse_name/code     → scope_label
#   status                  → status (normalized via gen1 mapping)
#   items[]                 → count_items[] (best-effort projection)
#   created_at/by           → created_at/by
#   notes                   → notes
# ─────────────────────────────────────────────────────────────────────────────

def _project_gen1_item(item: dict) -> dict:
    """Best-effort projection of legacy warehouse_opname items[] to count_items[] shape."""
    return {
        'position_id':       item.get('position_id') or item.get('material_id', ''),
        'position_barcode':  item.get('barcode', ''),
        'material_code':     item.get('material_code') or item.get('item_code', ''),
        'material_name':     item.get('material_name') or item.get('item_name', ''),
        'system_qty':        float(item.get('system_qty', item.get('expected_qty', 0)) or 0),
        'counted_qty':       item.get('counted_qty') or item.get('actual_qty'),
        'variance':          item.get('variance') or item.get('diff'),
        'variance_pct':      None,
        'unit':              item.get('unit', 'pcs'),
        'notes':             item.get('notes', ''),
        'counted':           item.get('counted_qty') is not None
                              or item.get('actual_qty') is not None,
    }


def _project_gen1_session(opname: dict) -> dict:
    items_raw = opname.get('items') or opname.get('lines') or []
    count_items = [_project_gen1_item(it) for it in items_raw if isinstance(it, dict)]
    counted_items = sum(1 for ci in count_items if ci.get('counted'))
    variance_items = sum(
        1 for ci in count_items
        if ci.get('counted') and (ci.get('variance') or 0) != 0
    )

    return {
        'id':              opname.get('id') or str(uuid.uuid4()),
        'session_no':      opname.get('opname_number') or opname.get('ref_number', ''),
        'mode':            'full_count',
        'scope_type':      'all',
        'scope_id':        opname.get('warehouse_id', ''),
        'scope_label':     opname.get('warehouse_name')
                            or opname.get('warehouse_code')
                            or 'warehouse',
        'status':          _norm_status_gen1(opname.get('status')),
        'domain':          'warehouse_legacy',
        'count_items':     count_items,
        'total_items':     int(opname.get('total_items', len(count_items)) or len(count_items)),
        'counted_items':   counted_items,
        'total_variance_items': variance_items,
        'total_variance_value': 0.0,
        'notes':           opname.get('notes', ''),
        'created_at':      opname.get('created_at') or _now_dt(),
        'created_by':      opname.get('created_by', 'migration'),
        'counted_by':      opname.get('completed_by'),
        'approved_by':     opname.get('approved_by') or opname.get('completed_by'),
        'approved_at':     opname.get('approved_at') or opname.get('completed_at'),
        'closed_at':       opname.get('completed_at') or opname.get('cancelled_at'),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Migration runner
# ─────────────────────────────────────────────────────────────────────────────

async def _migrate_gen2(db, *, dry_run: bool) -> dict:
    """Migrate wh_opname_sessions + wh_opname_lines → wh_opname_sessions2."""
    stats = {
        'source':          'wh_opname_sessions',
        'target':          'wh_opname_sessions2 (domain=warehouse_scan)',
        'total_source':    0,
        'already_migrated': 0,
        'migrated_now':    0,
        'skipped':         0,
    }

    stats['total_source'] = await db.wh_opname_sessions.count_documents({})
    if stats['total_source'] == 0:
        return stats

    async for session in db.wh_opname_sessions.find({}):
        original_id = session.get('id') or str(session.get('_id'))
        # Idempotence check
        existing = await db.wh_opname_sessions2.find_one({
            'migrated_from': 'wh_opname_sessions',
            'original_id':   original_id,
        })
        if existing:
            stats['already_migrated'] += 1
            continue

        mapped = await _project_gen2_session(db, session)
        mapped['migrated_from'] = 'wh_opname_sessions'
        mapped['original_id']   = original_id
        mapped['migrated_at']   = _now_iso()

        if dry_run:
            stats['skipped'] += 1
        else:
            try:
                await db.wh_opname_sessions2.insert_one(mapped)
                stats['migrated_now'] += 1
            except Exception as e:
                print(f"  [WARN] GEN2 insert failed for original_id={original_id}: {e}")
                stats['skipped'] += 1

    return stats


async def _migrate_gen1(db, *, dry_run: bool) -> dict:
    """Migrate warehouse_opname → wh_opname_sessions2."""
    stats = {
        'source':          'warehouse_opname',
        'target':          'wh_opname_sessions2 (domain=warehouse_legacy)',
        'total_source':    0,
        'already_migrated': 0,
        'migrated_now':    0,
        'skipped':         0,
    }

    stats['total_source'] = await db.warehouse_opname.count_documents({})
    if stats['total_source'] == 0:
        return stats

    async for opname in db.warehouse_opname.find({}):
        original_id = opname.get('id') or str(opname.get('_id'))
        # Idempotence check
        existing = await db.wh_opname_sessions2.find_one({
            'migrated_from': 'warehouse_opname',
            'original_id':   original_id,
        })
        if existing:
            stats['already_migrated'] += 1
            continue

        mapped = _project_gen1_session(opname)
        mapped['migrated_from'] = 'warehouse_opname'
        mapped['original_id']   = original_id
        mapped['migrated_at']   = _now_iso()

        if dry_run:
            stats['skipped'] += 1
        else:
            try:
                await db.wh_opname_sessions2.insert_one(mapped)
                stats['migrated_now'] += 1
            except Exception as e:
                print(f"  [WARN] GEN1 insert failed for original_id={original_id}: {e}")
                stats['skipped'] += 1

    return stats


def _print_stats(label: str, stats: dict, dry_run: bool):
    print(f"\n--- {label} ---")
    print(f"  Source ({stats['source']:<30}): {stats['total_source']} docs")
    print(f"  Already migrated (target):       {stats['already_migrated']}")
    action = 'Would migrate' if dry_run else 'Migrated now'
    print(f"  {action:<24}:        {stats['skipped'] if dry_run else stats['migrated_now']}")
    if not dry_run:
        print(f"  Skipped (errors):                {stats['skipped']}")


async def main():
    parser = argparse.ArgumentParser(
        description='P3 TD-008 — Opname Systems Consolidation Migration')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without writing to DB')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 70)
    print('  P3 TD-008 — Opname Systems Consolidation Migration')
    print('=' * 70)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    print(f'  Mode:        {"DRY-RUN (no writes)" if args.dry_run else "LIVE (will write)"}')
    print('  Target SSOT: wh_opname_sessions2')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]

        # Flow A: GEN2 — wh_opname_sessions + wh_opname_lines → SSOT
        stats_a = await _migrate_gen2(db, dry_run=args.dry_run)
        _print_stats(
            'Flow A: GEN2 (wh_opname_sessions + lines → wh_opname_sessions2)',
            stats_a, args.dry_run)

        # Flow B: GEN1 — warehouse_opname → SSOT
        stats_b = await _migrate_gen1(db, dry_run=args.dry_run)
        _print_stats(
            'Flow B: GEN1 (warehouse_opname → wh_opname_sessions2)',
            stats_b, args.dry_run)

        # Summary
        total_source = stats_a['total_source'] + stats_b['total_source']
        total_migrated = stats_a['migrated_now'] + stats_b['migrated_now']
        total_already = stats_a['already_migrated'] + stats_b['already_migrated']
        total_skipped = stats_a['skipped'] + stats_b['skipped']

        print('\n' + '=' * 70)
        print('  Summary')
        print('=' * 70)
        print(f'  Total source documents:    {total_source}')
        print(f'  Already migrated:          {total_already}')
        if args.dry_run:
            print(f'  Would migrate this run:    {total_skipped}')
            print()
            print('  DRY-RUN COMPLETE. No data was written.')
        else:
            print(f'  Migrated this run:         {total_migrated}')
            print(f'  Skipped (errors):          {total_skipped}')
            print()
            print('  ✅ MIGRATION COMPLETE.')
            print('     Source collections preserved (deletion deferred per TD-008 —'
                  ' monitor 1 week).')
        print('=' * 70)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
