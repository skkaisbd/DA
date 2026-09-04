"""
Maklon Adapter — Konversi antara legacy order shape (dewi_maklon_orders) dan
PO shape baru (dewi_maklon_pos).

Digunakan saat konsumen lama (client portal, dashboards, billing) membaca dari
`dewi_maklon_pos` tetapi perlu menyajikan data dalam bentuk order legacy untuk
kompatibilitas API yang sudah ada di frontend.

Schema mapping:
    legacy order                  ←→ new PO
    ─────────────                    ───────
    id                               id
    order_code                       po_number
    client_id                        client_id
    client_name                      client_name
    product_name                     items[0].product_description (atau "Multi-item PO")
    product_category                 items[0].artikel (atau "")
    qty_ordered                      total_qty
    qty_per_size                     (derived dari items[*].size)
    colors                           (derived dari items[*].color, unique list)
    price_per_pcs                    items[0].cmt_rate_per_pcs (atau avg)
    total_value                      total_value
    order_date                       po_date
    deadline_date                    deadline
    completion_date                  (notes / N/A)
    status                           status_legacy (mapped from PO status + production stage)
    progress_percentage              (computed from qty_produced / total_qty)
    fabric_provided_by               (default 'client')
    material_notes                   notes (header)
    wo_ids                           items[*].wo_id (compact, unique)
    linked_wo_ids                    items[*].wo_id (same)
    delivery_method                  'pickup' (default)
    delivery_address                 None
    revision_count                   0 (default)
    stage_qty                        (derived from items[*].qty_produced/dispatched)
    notes                            notes

Status mapping (PO → legacy order):
    draft               → draft
    confirmed           → confirmed
    in_production       → cutting (default mid-stage)
    partial_delivered   → packing
    completed           → completed
    invoiced            → invoiced
    cancelled           → cancelled
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


PO_TO_LEGACY_STATUS: Dict[str, str] = {
    'draft': 'draft',
    'confirmed': 'confirmed',
    'in_production': 'cutting',  # default mid-stage; client portal still shows progress %
    'partial_delivered': 'packing',
    'completed': 'completed',
    'invoiced': 'invoiced',
    'cancelled': 'cancelled',
}


LEGACY_TO_PO_STATUS: Dict[str, str] = {
    'draft': 'draft',
    'confirmed': 'confirmed',
    'material_ready': 'confirmed',
    'cutting': 'in_production',
    'sewing': 'in_production',
    'qc': 'in_production',
    'packing': 'in_production',
    'completed': 'completed',
    'invoiced': 'invoiced',
    'cancelled': 'cancelled',
}


# P1.B cleanup field translation: legacy order field → PO field
LEGACY_TO_PO_ORDER_FIELDS: Dict[str, str] = {
    "order_code": "po_number",
    "order_date": "po_date",
    "deadline_date": "deadline",
    "linked_wo_ids": "_legacy_linked_wo_ids",
    "stage_qty": "legacy_stage_qty",
    "stage": "status",                          # legacy 'stage' field → PO 'status'
    "progress_percentage": "legacy_progress_pct",
    "material_notes": "notes",
    "completion_date": "legacy_completion_date",
    "invoice_id": "ar_invoice_id",
    "invoice_number": "ar_invoice_number",
}


def translate_legacy_order_update(update: Any) -> Any:
    """Translate $set/$unset operators with legacy field names → PO field names.
    Also maps status values when status is in $set.
    """
    if not isinstance(update, dict):
        return update
    out: Dict[str, Any] = {}
    for op, val in update.items():
        if op.startswith("$") and isinstance(val, dict):
            translated = {}
            for k, v in val.items():
                # Translate field name
                new_k = LEGACY_TO_PO_ORDER_FIELDS.get(k, k)
                # Translate status value if mapping op
                if k == "status" and isinstance(v, str) and op == "$set":
                    v = LEGACY_TO_PO_STATUS.get(v, v)
                translated[new_k] = v
            out[op] = translated
        else:
            out[op] = val
    return out


def translate_legacy_order_query(query: Any, _parent_key: str = "") -> Any:
    """Translate legacy field names in a find/count query → PO field names.

    Recursively walks dict/list to handle nested operators like $and, $or, $in,
    $gte, $regex, etc. Also maps status values when "status"/"stage" key encountered,
    including inside $in/$nin arrays.

    Example:
      {"order_date": {"$gte": "..."}}     →  {"po_date": {"$gte": "..."}}
      {"stage": {"$in": ["cutting"]}}     →  {"status": {"$in": ["in_production"]}}
      {"status": "completed"}             →  {"status": "completed"}
    """
    if not isinstance(query, dict):
        return query
    # Track if we're inside a status/stage operator value (e.g. {"status": {"$in": [...]}})
    status_keys = {"status", "stage"}
    is_status_value = _parent_key in status_keys

    out: Dict[str, Any] = {}
    for k, v in query.items():
        # Translate field name (skip operators that start with $)
        new_k = k if k.startswith("$") else LEGACY_TO_PO_ORDER_FIELDS.get(k, k)

        # Determine if this key is status/stage (or its renamed form)
        next_parent = k if k in status_keys else (_parent_key if k.startswith("$") else "")

        if isinstance(v, dict):
            new_v = translate_legacy_order_query(v, _parent_key=next_parent)
        elif isinstance(v, list):
            # If we're inside a status $in/$nin/$all operator, translate each value
            if is_status_value and _parent_key in status_keys:
                new_v = [LEGACY_TO_PO_STATUS.get(item, item) if isinstance(item, str) else item for item in v]
            else:
                new_v = [translate_legacy_order_query(item, _parent_key=next_parent) if isinstance(item, dict) else item for item in v]
        elif (k in status_keys or is_status_value) and isinstance(v, str):
            new_v = LEGACY_TO_PO_STATUS.get(v, v)
        else:
            new_v = v
        out[new_k] = new_v
    return out


def po_to_legacy_order(po: Dict[str, Any]) -> Dict[str, Any]:
    """Convert a `dewi_maklon_pos` document into a legacy `dewi_maklon_orders` shape.

    Loss-free for top-level metadata; aggregates multi-item POs into a synthetic
    order with `total_qty` and a `multi_item` flag.

    Safe with missing keys.
    """
    if not po:
        return {}

    items: List[Dict[str, Any]] = po.get('items', []) or []
    qty_per_size: List[Dict[str, Any]] = []
    colors: List[str] = []
    wo_ids: List[str] = []
    total_qty_produced = 0
    total_qty_dispatched = 0
    product_name_parts: List[str] = []
    product_category = ''
    price_sum_weighted = 0.0
    qty_total = 0

    for it in items:
        size = (it.get('size') or '').strip()
        color = (it.get('color') or '').strip()
        qty = int(it.get('qty') or 0)
        qty_total += qty
        if size:
            qty_per_size.append({'size': size, 'qty': qty})
        if color and color not in colors:
            colors.append(color)
        wo_id = it.get('wo_id')
        if wo_id and wo_id not in wo_ids:
            wo_ids.append(wo_id)
        total_qty_produced += int(it.get('qty_produced') or 0)
        total_qty_dispatched += int(it.get('qty_dispatched') or 0)
        desc = (it.get('product_description') or it.get('artikel') or '').strip()
        if desc and desc not in product_name_parts:
            product_name_parts.append(desc)
        if not product_category:
            product_category = it.get('artikel') or ''
        rate = float(it.get('selling_price_per_pcs') or it.get('cmt_rate_per_pcs') or 0)
        price_sum_weighted += rate * qty

    total_qty = int(po.get('total_qty') or qty_total or 0)
    if total_qty <= 0:
        total_qty = qty_total or 0
    avg_price = round(price_sum_weighted / total_qty, 2) if total_qty > 0 else 0.0
    product_name = (
        ' / '.join(product_name_parts) if product_name_parts else po.get('po_number', '')
    )
    progress_pct = 0
    if total_qty > 0:
        progress_pct = min(100, int(round((total_qty_produced or total_qty_dispatched) * 100 / total_qty)))

    status_legacy = PO_TO_LEGACY_STATUS.get(po.get('status', 'draft'), 'draft')
    # Refine: if dispatched > 0 but not yet completed, show "packing"
    if total_qty_dispatched > 0 and status_legacy in ('confirmed', 'cutting'):
        status_legacy = 'packing'

    return {
        'id': po.get('id'),
        'order_code': po.get('po_number'),
        'client_id': po.get('client_id'),
        'client_name': po.get('client_name'),
        'product_name': product_name,
        'product_category': product_category,
        'qty_ordered': total_qty,
        'qty_per_size': qty_per_size,
        'colors': colors,
        'price_per_pcs': avg_price,
        'total_value': float(po.get('total_value') or 0),
        'order_date': po.get('po_date'),
        'deadline_date': po.get('deadline'),
        'completion_date': po.get('completion_date'),
        'status': status_legacy,
        'progress_percentage': progress_pct,
        'fabric_provided_by': po.get('fabric_provided_by', 'client'),
        'material_notes': po.get('notes', ''),
        'wo_ids': wo_ids,
        'linked_wo_ids': wo_ids,
        'cmt_job_ids': [],
        'delivery_method': po.get('delivery_method', 'pickup'),
        'delivery_address': po.get('delivery_address'),
        'revision_count': int(po.get('revision_count') or 0),
        'notes': po.get('notes', ''),
        'created_at': po.get('created_at'),
        'updated_at': po.get('updated_at'),
        'created_by': po.get('created_by_name') or po.get('created_by'),
        'confirmed_by': po.get('confirmed_by'),
        'sync_mode': 'wo' if wo_ids else 'manual',
        'stage_qty': {
            'qty_produced': total_qty_produced,
            'qty_dispatched': total_qty_dispatched,
        },
        # Trace flag
        '_source': 'dewi_maklon_pos',
        '_po_status': po.get('status'),
        '_po_items_count': len(items),
        # Finance-related
        'invoice_id': po.get('ar_invoice_id'),
        'invoice_number': po.get('ar_invoice_number'),
        'payment_status': po.get('payment_status', 'unpaid'),
    }


def order_to_po_create_payload(order: Dict[str, Any]) -> Dict[str, Any]:
    """Convert legacy order doc → a payload suitable for inserting into dewi_maklon_pos.

    Used by the migration script. Returns the FULL PO doc shape with all required
    fields populated. The migration script can then upsert this by id.
    """
    from uuid import uuid4
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    po_id = order.get('id') or str(uuid4())
    items: List[Dict[str, Any]] = []
    total_qty = int(order.get('qty_ordered') or 0)
    qty_per_size = order.get('qty_per_size') or []
    colors = order.get('colors') or []
    price = float(order.get('price_per_pcs') or 0)
    product_name = order.get('product_name', 'Unknown Product')
    artikel = order.get('product_category') or product_name

    if qty_per_size and isinstance(qty_per_size, list):
        for idx, sz in enumerate(qty_per_size, start=1):
            size = sz.get('size', 'All')
            qty = int(sz.get('qty', 0) or 0)
            if qty <= 0:
                continue
            color = colors[0] if colors else ''
            items.append({
                'item_id': str(uuid4()),
                'idx': idx,
                'seri_no': f'S{idx:02d}',
                'artikel': artikel,
                'sku_code': '',
                'color': color,
                'size': size,
                'qty': qty,
                'qty_produced': 0,
                'qty_dispatched': 0,
                'cmt_rate_per_pcs': price,
                'subtotal': round(price * qty, 2),
                'product_description': product_name,
                'notes': '',
                'wo_id': None,
                'wo_number': None,
                'status': 'pending',
            })
    if not items:
        # Fallback: single item with total qty
        items.append({
            'item_id': str(uuid4()),
            'idx': 1,
            'seri_no': 'S01',
            'artikel': artikel,
            'sku_code': '',
            'color': colors[0] if colors else '',
            'size': 'All',
            'qty': total_qty,
            'qty_produced': 0,
            'qty_dispatched': 0,
            'cmt_rate_per_pcs': price,
            'subtotal': round(price * total_qty, 2),
            'product_description': product_name,
            'notes': '',
            'wo_id': None,
            'wo_number': None,
            'status': 'pending',
        })

    # If legacy already has linked_wo_ids, distribute to first item
    legacy_wo_ids = order.get('linked_wo_ids') or order.get('wo_ids') or []
    if legacy_wo_ids and items:
        items[0]['wo_id'] = legacy_wo_ids[0]

    total_value = float(order.get('total_value') or 0)
    if total_value <= 0:
        total_value = sum(i['subtotal'] for i in items)

    return {
        'id': po_id,
        'po_number': order.get('order_code') or f'MKLN-LEGACY-{po_id[:8]}',
        'client_id': order.get('client_id'),
        'client_name': order.get('client_name', ''),
        'client_code': order.get('client_code', 'CLT'),
        'po_date': order.get('order_date'),
        'deadline': order.get('deadline_date'),
        'payment_terms': order.get('payment_terms', 'net_30'),
        'status': LEGACY_TO_PO_STATUS.get(order.get('status', 'draft'), 'draft'),
        'items': items,
        'total_qty': total_qty if total_qty > 0 else sum(i['qty'] for i in items),
        'total_value': total_value,
        'notes': order.get('notes', '') or order.get('material_notes', '') or '',
        # Finance tracking
        'ar_invoice_id': order.get('invoice_id'),
        'ar_invoice_number': order.get('invoice_number'),
        'payment_status': order.get('payment_status', 'unpaid'),
        'advance_payment': 0.0,
        'amount_paid': 0.0,
        # GL tracking
        'gl_posted_at': None,
        'gl_je_id': None,
        'post_error': None,
        # Legacy traceability
        'legacy_order_id': order.get('id'),
        'legacy_order_code': order.get('order_code'),
        'legacy_stage_qty': order.get('stage_qty', {}),
        'legacy_progress_pct': order.get('progress_percentage', 0),
        'legacy_completion_date': order.get('completion_date'),
        'migrated_from': 'dewi_maklon_orders',
        'migrated_at': now,
        'created_at': order.get('created_at') or now,
        'updated_at': now,
        'created_by': order.get('created_by', 'migration'),
        'created_by_name': order.get('created_by', 'migration'),
    }


async def find_maklon_record(db, order_or_po_id: str) -> Optional[Dict[str, Any]]:
    """Look up a maklon record by id in `dewi_maklon_pos` (SSOT, P1.B cleanup
    completed 2026-05-23). Legacy `dewi_maklon_orders` collection has been
    deprecated. Returns the raw PO document with a `_collection` marker.
    """
    po = await db.dewi_maklon_pos.find_one({'id': order_or_po_id}, {'_id': 0})
    if po:
        po['_collection'] = 'dewi_maklon_pos'
        return po
    # Also try by po_number / order_code (legacy back-compat)
    po = await db.dewi_maklon_pos.find_one({'po_number': order_or_po_id}, {'_id': 0})
    if po:
        po['_collection'] = 'dewi_maklon_pos'
        return po
    return None


# ── P1.B cleanup wrapper: dewi_maklon_orders → dewi_maklon_pos shim ─────────

class _MaklonOrdersView:
    """Wrap dewi_maklon_pos collection so callers can use legacy dewi_maklon_orders
    API contract. Auto-projects via po_to_legacy_order on reads, auto-converts via
    order_to_po_create_payload on inserts, translates field names + status on updates
    AND on read queries (via translate_legacy_order_query).
    """
    def __init__(self, db):
        self._c = db.dewi_maklon_pos

    async def find_one(self, query=None, *a, **k):
        q = translate_legacy_order_query(query or {})
        doc = await self._c.find_one(q, *a, **k)
        return po_to_legacy_order(doc) if doc else None

    def find(self, query=None, *a, **k):
        q = translate_legacy_order_query(query or {})
        cur = self._c.find(q, *a, **k)
        return _MaklonOrdersCursor(cur)

    async def count_documents(self, query=None, *a, **k):
        q = translate_legacy_order_query(query or {})
        return await self._c.count_documents(q, *a, **k)

    async def insert_one(self, doc, **k):
        po_doc = order_to_po_create_payload(doc)
        return await self._c.insert_one(po_doc, **k)

    async def update_one(self, query, update, **k):
        q = translate_legacy_order_query(query)
        return await self._c.update_one(q, translate_legacy_order_update(update), **k)

    async def update_many(self, query, update, **k):
        q = translate_legacy_order_query(query)
        return await self._c.update_many(q, translate_legacy_order_update(update), **k)

    async def delete_one(self, query, **k):
        q = translate_legacy_order_query(query)
        return await self._c.delete_one(q, **k)

    def aggregate(self, pipeline, **k):
        """Proxy aggregate to underlying collection. Caller is responsible for using
        PO field names in the pipeline (e.g. 'total_value', 'po_date', not legacy names).
        Returns the native motor cursor so the caller can `.to_list(...)` it normally.
        """
        return self._c.aggregate(pipeline, **k)


class _MaklonOrdersCursor:
    def __init__(self, cur):
        self._cur = cur

    def sort(self, *a, **k):
        self._cur = self._cur.sort(*a, **k)
        return self

    def skip(self, n):
        self._cur = self._cur.skip(n)
        return self

    def limit(self, n):
        self._cur = self._cur.limit(n)
        return self

    async def to_list(self, length=None):
        docs = await self._cur.to_list(length=length)
        return [po_to_legacy_order(d) for d in docs]


def legacy_orders_view(db):
    """Returns a legacy-shaped view of dewi_maklon_pos for P1.B back-compat."""
    return _MaklonOrdersView(db)
