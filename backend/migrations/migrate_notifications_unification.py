"""
P3 TD-010 Part B — Notifications Unification Migration (Session #11.11)
========================================================================
Consolidates 4 parallel notification collections into 1 SSOT.

Mapping:
    `dewi_notifications`              → `notifications` (type='dewi')
    `rahaza_notifications`            → `notifications` (type='rahaza')
    `collab_notifications`            → `notifications` (type='collab')
    `marketing_livehost_notifications`→ `notifications` (type='marketing_livehost')

Unified schema (`notifications` SSOT):
    {
      'id': str,                  # UUID
      'type': str,                # 'dewi'|'rahaza'|'collab'|'marketing_livehost'
      'subtype': str|None,        # event_type / notif_type
      'severity': str,            # info|success|warning|error
      'user_id': str|None,        # recipient internal user id
      'title': str|None,
      'body': str,                # main message
      'channel': str|None,        # in_app|whatsapp|email|sse
      'recipient': str|None,      # phone/email when external delivery
      'source_type': str|None,
      'source_id': str|None,
      'source_url': str|None,
      'source_ref': str|None,
      'client_id': str|None,
      'host_id': str|None,
      'meta': dict,
      'status': str|None,         # queued|sent|failed|read
      'read': bool,
      'read_at': datetime|None,
      'created_at': datetime,
      'sent_at': datetime|None,
      'failed_reason': str|None,
      # Traceability:
      'migrated_from': str,
      'original_id': str,
      'migrated_at': str (ISO),
    }

Properties:
  * IDEMPOTENT via (migrated_from, original_id) tuple
  * NON-DESTRUCTIVE — sources preserved
  * DRY-RUN via --dry-run
  * EMPTY-SAFE

NOTE: Writer code in 17+ source files is NOT refactored in this script. Those
files continue to write to their original collections. This migration provides
the SSOT collection + traceable copy for the unified `/api/notifications/unified`
endpoint. Writer refactor is deferred to TD-010 Phase B (follow-up session).
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


# ─────────────────────────────────────────────────────────────────────────────
# Schema projectors per source collection.
# Each returns the unified-shape dict ready for insert.
# ─────────────────────────────────────────────────────────────────────────────

def _project_dewi(doc: dict) -> dict:
    """dewi_notifications has channel/recipient/event_type/status/sent_at fields."""
    status = doc.get('status') or 'queued'
    return {
        'id':           doc.get('id') or str(uuid.uuid4()),
        'type':         'dewi',
        'subtype':      doc.get('event_type'),
        'severity':     'info',
        'user_id':      None,
        'title':        doc.get('subject'),
        'body':         doc.get('body', ''),
        'channel':      doc.get('channel'),       # whatsapp|email
        'recipient':    doc.get('recipient'),
        'source_type':  None,
        'source_id':    None,
        'source_url':   None,
        'source_ref':   doc.get('source_ref'),
        'client_id':    doc.get('client_id'),
        'host_id':      None,
        'meta':         doc.get('meta') or {},
        'status':       status,
        'read':         False,
        'read_at':      None,
        'created_at':   doc.get('created_at') or _now_dt(),
        'sent_at':      doc.get('sent_at'),
        'failed_reason':doc.get('failed_reason'),
    }


def _project_rahaza(doc: dict) -> dict:
    """rahaza_notifications: lightweight in-app alerts. Schema varies — best-effort."""
    return {
        'id':           doc.get('id') or str(uuid.uuid4()),
        'type':         'rahaza',
        'subtype':      doc.get('type') or doc.get('event_type') or doc.get('category'),
        'severity':     doc.get('severity') or doc.get('level') or 'info',
        'user_id':      doc.get('user_id') or doc.get('to_user_id') or doc.get('recipient_id'),
        'title':        doc.get('title') or doc.get('subject'),
        'body':         doc.get('message') or doc.get('body') or doc.get('content', ''),
        'channel':      'in_app',
        'recipient':    None,
        'source_type':  doc.get('source_type') or doc.get('module'),
        'source_id':    doc.get('source_id') or doc.get('ref_id'),
        'source_url':   doc.get('source_url') or doc.get('link'),
        'source_ref':   doc.get('ref'),
        'client_id':    None,
        'host_id':      None,
        'meta':         doc.get('meta') or doc.get('metadata') or {},
        'status':       'queued',
        'read':         bool(doc.get('read', False)),
        'read_at':      doc.get('read_at'),
        'created_at':   doc.get('created_at') or _now_dt(),
        'sent_at':      None,
        'failed_reason':None,
    }


def _project_collab(doc: dict) -> dict:
    """collab_notifications: {notification_id, user_id, type, icon, title, content, source_type, source_id, source_url, metadata, read, read_at, created_at}."""
    return {
        'id':           doc.get('notification_id') or doc.get('id') or str(uuid.uuid4()),
        'type':         'collab',
        'subtype':      doc.get('type'),
        'severity':     'info',
        'user_id':      doc.get('user_id'),
        'title':        doc.get('title'),
        'body':         doc.get('content', ''),
        'channel':      'in_app',
        'recipient':    None,
        'source_type':  doc.get('source_type'),
        'source_id':    doc.get('source_id'),
        'source_url':   doc.get('source_url'),
        'source_ref':   None,
        'client_id':    None,
        'host_id':      None,
        'meta':         {**(doc.get('metadata') or {}), 'icon': doc.get('icon')},
        'status':       'queued',
        'read':         bool(doc.get('read', False)),
        'read_at':      doc.get('read_at'),
        'created_at':   doc.get('created_at') or _now_dt(),
        'sent_at':      None,
        'failed_reason':None,
    }


def _project_livehost(doc: dict) -> dict:
    """marketing_livehost_notifications: {id, host_id, type, severity, title, message, link, read, created_at}."""
    return {
        'id':           doc.get('id') or str(uuid.uuid4()),
        'type':         'marketing_livehost',
        'subtype':      doc.get('type'),
        'severity':     doc.get('severity') or 'info',
        'user_id':      None,
        'title':        doc.get('title'),
        'body':         doc.get('message', ''),
        'channel':      'sse',
        'recipient':    None,
        'source_type':  'marketing_livehost',
        'source_id':    doc.get('host_id'),
        'source_url':   doc.get('link'),
        'source_ref':   None,
        'client_id':    None,
        'host_id':      doc.get('host_id'),
        'meta':         {},
        'status':       'queued',
        'read':         bool(doc.get('read', False)),
        'read_at':      None,
        'created_at':   doc.get('created_at') or _now_dt(),
        'sent_at':      None,
        'failed_reason':None,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Migration runner
# ─────────────────────────────────────────────────────────────────────────────

async def _migrate(
    db, *, source_col: str, type_label: str, projector, dry_run: bool,
) -> dict:
    stats = {
        'source':            source_col,
        'type':              type_label,
        'total_source':      0,
        'already_migrated':  0,
        'migrated_now':      0,
        'errors':            0,
    }
    stats['total_source'] = await db[source_col].count_documents({})
    if stats['total_source'] == 0:
        return stats

    async for doc in db[source_col].find({}):
        try:
            original_id = doc.get('id') or doc.get('notification_id') or str(doc.get('_id'))
            existing = await db.notifications.find_one({
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

            if not dry_run:
                await db.notifications.insert_one(mapped)
            stats['migrated_now'] += 1
        except Exception as e:
            print(f"  [WARN] migration error for {source_col}: {e}")
            stats['errors'] += 1
    return stats


def _print_stats(label: str, stats: dict, dry_run: bool):
    print(f"\n--- {label} ---")
    print(f"  Source ({stats['source']:<33}) type='{stats['type']}'")
    print(f"  Total source documents:        {stats['total_source']}")
    print(f"  Already migrated:              {stats['already_migrated']}")
    action = 'Would migrate' if dry_run else 'Migrated now'
    print(f"  {action:<24}:       {stats['migrated_now']}")
    if stats['errors']:
        print(f"  Errors:                        {stats['errors']}")


async def main():
    parser = argparse.ArgumentParser(
        description='P3 TD-010 Part B — Notifications Unification Migration')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without writing to DB')
    args = parser.parse_args()

    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')

    print('=' * 72)
    print('  P3 TD-010 Part B — Notifications Unification Migration')
    print('=' * 72)
    print(f'  MongoDB:     {mongo_url}')
    print(f'  Database:    {db_name}')
    print(f'  Mode:        {"DRY-RUN (no writes)" if args.dry_run else "LIVE (will write)"}')
    print('  Target SSOT: notifications  (with `type` discriminator)')
    print()

    client = AsyncIOMotorClient(mongo_url)
    try:
        db = client[db_name]
        flows = [
            ('dewi_notifications',               'dewi',               _project_dewi),
            ('rahaza_notifications',             'rahaza',             _project_rahaza),
            ('collab_notifications',             'collab',             _project_collab),
            ('marketing_livehost_notifications', 'marketing_livehost', _project_livehost),
        ]
        results = []
        for src, t, proj in flows:
            s = await _migrate(db, source_col=src, type_label=t,
                               projector=proj, dry_run=args.dry_run)
            _print_stats(f'Flow: {src} → notifications (type={t})', s, args.dry_run)
            results.append(s)

        tot_src = sum(r['total_source'] for r in results)
        tot_mig = sum(r['migrated_now'] for r in results)
        tot_alr = sum(r['already_migrated'] for r in results)
        tot_err = sum(r['errors'] for r in results)

        print('\n' + '=' * 72)
        print('  Summary')
        print('=' * 72)
        print(f'  Total source documents:        {tot_src}')
        print(f'  Already migrated (idempotent): {tot_alr}')
        if args.dry_run:
            print(f'  Would migrate this run:        {tot_mig}')
            print()
            print('  DRY-RUN COMPLETE. No data was written.')
        else:
            print(f'  Migrated this run:             {tot_mig}')
            print(f'  Errors:                        {tot_err}')
            print()
            print('  ✅ MIGRATION COMPLETE.')
            print('     Source collections preserved (deletion deferred — monitor 1 week).')
            print('     Writer code refactor deferred to TD-010 Phase B follow-up session.')
        print('=' * 72)

    finally:
        client.close()


if __name__ == '__main__':
    asyncio.run(main())
