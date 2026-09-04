/**
 * Maklon Order Adapter (Frontend)
 * ================================
 * Phase B Frontend Cutover (2026-05-23).
 *
 * Convert `dewi_maklon_pos` PO response shape → legacy order shape that the
 * Maklon UI modules already understand. This lets us point frontend at
 * `/api/dewi/maklon/pos` (new SSOT) without rewriting display/form logic.
 *
 * Status mapping (PO → legacy):
 *   draft             → draft
 *   confirmed         → confirmed
 *   in_production     → cutting (default mid-stage)
 *   partial_delivered → packing
 *   completed         → completed
 *   invoiced          → invoiced
 *   cancelled         → cancelled
 */

export const PO_TO_LEGACY_STATUS = {
  draft: 'draft',
  confirmed: 'confirmed',
  in_production: 'cutting',
  partial_delivered: 'packing',
  completed: 'completed',
  invoiced: 'invoiced',
  cancelled: 'cancelled',
};

/**
 * Convert a single PO doc → legacy order shape.
 *
 * Legacy fields expected by UI:
 *   id, order_code, client_id, client_name, product_name, product_category,
 *   qty_ordered, qty_per_size[], colors[], price_per_pcs, total_value,
 *   order_date, deadline_date, status, progress_percentage, fabric_provided_by,
 *   linked_wo_ids[], stage_qty{}, sync_mode, notes, created_at, updated_at,
 *   created_by, confirmed_by, completion_date,
 *   invoice_id, invoice_number, payment_status
 */
export function poToLegacyOrder(po) {
  if (!po || typeof po !== 'object') return null;

  const items = Array.isArray(po.items) ? po.items : [];
  const qty_per_size = [];
  const colors = [];
  const linked_wo_ids = [];
  let total_qty_produced = 0;
  let total_qty_dispatched = 0;
  const product_name_parts = [];
  let product_category = '';
  let price_sum_weighted = 0;
  let qty_total = 0;

  for (const it of items) {
    const size = (it.size || '').trim();
    const color = (it.color || '').trim();
    const qty = Number(it.qty || 0);
    qty_total += qty;
    if (size) qty_per_size.push({ size, qty });
    if (color && !colors.includes(color)) colors.push(color);
    if (it.wo_id && !linked_wo_ids.includes(it.wo_id)) linked_wo_ids.push(it.wo_id);
    total_qty_produced += Number(it.qty_produced || 0);
    total_qty_dispatched += Number(it.qty_dispatched || 0);
    const desc = (it.product_description || it.artikel || '').trim();
    if (desc && !product_name_parts.includes(desc)) product_name_parts.push(desc);
    if (!product_category) product_category = it.artikel || '';
    const rate = Number(it.cmt_rate_per_pcs || 0);
    price_sum_weighted += rate * qty;
  }

  let total_qty = Number(po.total_qty || qty_total || 0);
  if (total_qty <= 0) total_qty = qty_total;
  const avg_price = total_qty > 0 ? Math.round((price_sum_weighted / total_qty) * 100) / 100 : 0;
  const product_name = product_name_parts.length > 0
    ? product_name_parts.join(' / ')
    : (po.po_number || '');
  let progress_pct = 0;
  if (total_qty > 0) {
    progress_pct = Math.min(
      100,
      Math.round(((total_qty_produced || total_qty_dispatched) * 100) / total_qty)
    );
  }

  let status_legacy = PO_TO_LEGACY_STATUS[po.status] || 'draft';
  if (total_qty_dispatched > 0 && ['confirmed', 'cutting'].includes(status_legacy)) {
    status_legacy = 'packing';
  }

  return {
    id: po.id,
    order_code: po.po_number,
    client_id: po.client_id,
    client_name: po.client_name,
    product_name,
    product_category,
    qty_ordered: total_qty,
    qty_per_size,
    colors,
    price_per_pcs: avg_price,
    total_value: Number(po.total_value || 0),
    order_date: po.po_date,
    deadline_date: po.deadline,
    completion_date: po.completion_date || po.legacy_completion_date,
    status: status_legacy,
    progress_percentage: progress_pct,
    fabric_provided_by: po.fabric_provided_by || 'client',
    material_notes: po.notes || '',
    linked_wo_ids,
    wo_ids: linked_wo_ids,
    cmt_job_ids: [],
    delivery_method: po.delivery_method || 'pickup',
    delivery_address: po.delivery_address || null,
    revision_count: Number(po.revision_count || 0),
    notes: po.notes || '',
    created_at: po.created_at,
    updated_at: po.updated_at,
    created_by: po.created_by_name || po.created_by,
    confirmed_by: po.confirmed_by,
    sync_mode: linked_wo_ids.length > 0 ? 'wo' : 'manual',
    stage_qty: {
      qty_produced: total_qty_produced,
      qty_dispatched: total_qty_dispatched,
    },
    // Finance fields
    invoice_id: po.ar_invoice_id,
    invoice_number: po.ar_invoice_number,
    payment_status: po.payment_status || 'unpaid',
    // Trace
    _source: 'dewi_maklon_pos',
    _po_status: po.status,
    _po_items_count: items.length,
    _po_items: items,
  };
}

/** Convert array of POs → array of legacy orders. Empty/null safe. */
export function posToLegacyOrders(posList) {
  if (!Array.isArray(posList)) {
    // /api/dewi/maklon/pos returns {items: [], total, page, ...}
    if (posList && typeof posList === 'object' && Array.isArray(posList.items)) {
      return posList.items.map(poToLegacyOrder);
    }
    return [];
  }
  return posList.map(poToLegacyOrder).filter(Boolean);
}

/**
 * Helper: GET /api/dewi/maklon/pos with auth, returns array of legacy orders.
 * Use this in place of `fetch('/api/dewi/maklon/orders')` in modules that
 * only need the order list for selectors.
 */
export async function fetchMaklonOrders(headers, opts = {}) {
  const params = new URLSearchParams();
  if (opts.status) params.set('status', opts.status);
  if (opts.client_id) params.set('client_id', opts.client_id);
  if (opts.limit) params.set('limit', String(opts.limit));
  const url = `/api/dewi/maklon/pos${params.toString() ? `?${params.toString()}` : ''}`;
  const r = await fetch(url, { headers });
  if (!r.ok) {
    throw new Error(`Failed to load maklon orders: ${r.status}`);
  }
  const data = await r.json();
  return posToLegacyOrders(data);
}
