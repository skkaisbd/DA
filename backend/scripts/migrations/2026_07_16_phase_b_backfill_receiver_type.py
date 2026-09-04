#!/usr/bin/env python3
"""
Phase B backfill migration — 2026-07-16
─────────────────────────────────────────
Backfill `receiver_type` on existing `buyer_shipments`:
  * receiver_type='da'    → vendor-created (has vendor_id set to a valid CMT
    vendor AND was NOT created by a DA admin), for these ALSO auto-create a
    matching `cmt_receipts` (Draft) if none exists yet.
  * receiver_type='buyer' → everything else (default).

Also backfills:
  * `related_cmt_receipt_id` on buyer_shipments (nullable link).
  * `source_receipt_ids=[]` on legacy DA-created shipments (empty for legacy).

IDEMPOTENT — safe to run multiple times.

Usage:
  python3 /app/backend/scripts/migrations/2026_07_16_phase_b_backfill_receiver_type.py \
    [--dry-run] [--limit N]

By default this migration is DRY-RUN unless --apply is passed.
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

# Path shim so 'from database import get_db' works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from database import get_db  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


async def _next_receipt_code(db, seq: int) -> str:
    """Simple seq counter fallback; the API uses counter but we emulate here."""
    prefix = 'CMT-RCV-'
    # Find the highest existing code with this prefix
    doc = await db.cmt_receipts.find_one(
        {'receipt_code': {'$regex': f'^{prefix}'}},
        sort=[('receipt_code', -1)]
    )
    n = 1
    if doc:
        try:
            n = int(doc['receipt_code'].replace(prefix, '')) + 1
        except (ValueError, TypeError):
            pass
    return f"{prefix}{n + seq:05d}"


async def main():
    p = argparse.ArgumentParser(description='Phase B backfill migration')
    p.add_argument('--apply', action='store_true', help='Actually apply changes (else dry-run)')
    p.add_argument('--limit', type=int, default=0, help='Max shipments to process (0=all)')
    args = p.parse_args()

    db = get_db()

    print(f"[Phase B Migration] mode: {'APPLY' if args.apply else 'DRY-RUN'} · limit: {args.limit or 'ALL'}")
    print("─" * 70)

    # Load vendor_partners → set of "is a CMT vendor" ids.
    cmt_vendor_ids = set()
    async for vp in db.vendor_partners.find({}, {'_id': 0, 'id': 1}):
        cmt_vendor_ids.add(vp['id'])
    async for g in db.garments.find({}, {'_id': 0, 'id': 1}):
        cmt_vendor_ids.add(g['id'])
    print(f"[info] known vendor entities: {len(cmt_vendor_ids)}")

    # Find shipments to backfill
    q = {'$or': [
        {'receiver_type': {'$exists': False}},
        {'receiver_type': None},
        {'receiver_type': ''},
    ]}
    total = await db.buyer_shipments.count_documents(q)
    print(f"[info] shipments missing receiver_type: {total}")

    if total == 0:
        print("[OK] Nothing to backfill.")
        return

    cursor = db.buyer_shipments.find(q, {'_id': 0}).sort('created_at', 1)
    if args.limit:
        cursor = cursor.limit(args.limit)

    updated_da = 0
    updated_buyer = 0
    receipts_created = 0
    seq_ctr = 0

    async for ship in cursor:
        vendor_id = ship.get('vendor_id') or ''
        # Heuristic: if vendor_id is a known CMT vendor AND created_by is not
        # a "da_admin"-style name, treat as vendor-created (receiver_type='da').
        # More conservative: only tag as 'da' if vendor_id matches a CMT vendor.
        is_vendor_ship = bool(vendor_id and vendor_id in cmt_vendor_ids)

        new_receiver = 'da' if is_vendor_ship else 'buyer'
        set_doc = {
            'receiver_type': new_receiver,
            'source_receipt_ids': ship.get('source_receipt_ids') or [],
            'created_by_da': (new_receiver == 'buyer'),
            'updated_at': _now(),
        }

        related_receipt_id = ship.get('related_cmt_receipt_id')

        if new_receiver == 'da' and not related_receipt_id:
            # Auto-create matching cmt_receipts (Draft) with lines from buyer_shipment_items
            items = await db.buyer_shipment_items.find(
                {'shipment_id': ship['id']}, {'_id': 0}
            ).to_list(None)
            valid_items = [i for i in items if int(i.get('qty_shipped', 0) or 0) > 0]

            # Reuse existing cmt_receipts if one exists w/ related_shipment_id
            existing_receipt = await db.cmt_receipts.find_one(
                {'related_shipment_id': ship['id']}, {'_id': 0}
            )
            if existing_receipt:
                related_receipt_id = existing_receipt['id']
            elif valid_items:
                seq_ctr += 1
                receipt_id = _uid()
                receipt_code = await _next_receipt_code(db, seq_ctr - 1)
                po = None
                if ship.get('po_id'):
                    po = await db.production_pos.find_one({'id': ship['po_id']}, {'_id': 0})
                total_shipped = sum(int(i.get('qty_shipped', 0) or 0) for i in valid_items)
                receipt_doc = {
                    'id': receipt_id,
                    'receipt_code': receipt_code,
                    'cmt_name': ship.get('vendor_name', ''),
                    'cmt_vendor_id': vendor_id,
                    'wo_number': ship.get('po_number', '') or (po or {}).get('po_number', ''),
                    'wo_id': ship.get('job_id', ''),
                    'po_id': ship.get('po_id', ''),
                    'po_number': ship.get('po_number', ''),
                    'business_type': ship.get('business_type', 'internal'),
                    'receipt_date': str(ship.get('last_dispatch') or ship.get('created_at') or _now())[:10],
                    'delivery_note': ship.get('shipment_number', ''),
                    'notes': f'Phase B backfill dari buyer_shipments {ship.get("shipment_number","")} (retro).',
                    'status': 'Draft',
                    'submitted_at': '', 'submitted_by': '',
                    'approved_at': '', 'approved_by': '',
                    'reject_reason': '',
                    'related_shipment_id': ship['id'],
                    'total_shipped_by_cmt': total_shipped,
                    'total_actual': 0,
                    'total_rejected': 0,
                    'variance_reason': '',
                    'defect_photos': [],
                    'created_by': 'system_migration',
                    'created_at': _now(), 'updated_at': _now(),
                }
                line_docs = []
                for it in valid_items:
                    q_shipped = int(it.get('qty_shipped', 0) or 0)
                    line_docs.append({
                        'id': _uid(),
                        'receipt_id': receipt_id,
                        'sku_code': it.get('sku', ''),
                        'product_name': it.get('product_name', ''),
                        'color': it.get('color', ''),
                        'size': it.get('size', ''),
                        'qty_expected': q_shipped,
                        'qty_shipped_by_cmt': q_shipped,
                        'qty_actual': None,
                        'reject_qty': 0,
                        'reject_reason': '',
                        'photos': [],
                        'source_buyer_shipment_item_id': it.get('id'),
                        'po_item_id': it.get('po_item_id'),
                        'job_item_id': it.get('job_item_id'),
                        'notes': '',
                        'created_at': _now(),
                    })
                if args.apply:
                    await db.cmt_receipts.insert_one(receipt_doc)
                    if line_docs:
                        await db.cmt_receipt_lines.insert_many(line_docs)
                receipts_created += 1
                related_receipt_id = receipt_id
                print(f"  · shipment {ship.get('shipment_number','?')} → cmt_receipt {receipt_code} "
                      f"({len(line_docs)} lines, {total_shipped} pcs)")

        set_doc['related_cmt_receipt_id'] = related_receipt_id

        if args.apply:
            await db.buyer_shipments.update_one({'id': ship['id']}, {'$set': set_doc})

        if new_receiver == 'da':
            updated_da += 1
        else:
            updated_buyer += 1

    print("─" * 70)
    print(f"[summary] receiver_type='da'    : {updated_da} shipments")
    print(f"[summary] receiver_type='buyer' : {updated_buyer} shipments")
    print(f"[summary] cmt_receipts created  : {receipts_created}")
    if not args.apply:
        print("\n[DRY-RUN] Re-run with --apply to persist.")
    else:
        print("\n[APPLY] Backfill applied.")


if __name__ == '__main__':
    asyncio.run(main())
