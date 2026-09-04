"""
CV. Dewi Aditya / Rahaza — AP Invoice from GR + 3-way Match Dashboard
Phase 27 — P2P Flow Completion

Endpoints:
- GET  /api/rahaza/grs/available-for-invoice  — list GRs received but not yet invoiced
- POST /api/rahaza/ap-invoices/from-gr        — create AP Invoice from one or more GRs
- GET  /api/rahaza/3way-match                 — dashboard PO ↔ GR ↔ AP Invoice reconciliation
- GET  /api/rahaza/3way-match/{po_id}         — detail view for one PO

3-way Match Logic:
- For each PO: compute ordered_qty/value, received_qty/value (from GR), invoiced_qty/value (from AP Invoice linked via po_id/gr_id).
- Variance = invoiced - received (qty), or invoiced_amount - (received_qty * po_price).
- Status:
    matched    → all 3 align within tolerance (default 0.5%)
    variance   → variance > tolerance
    over       → invoiced > received (over-billing)
    under      → invoiced < received (under-billing)
    pending    → no invoice yet
"""

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, date
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from utils.counters import next_counter, gen_prefixed_number
from routes.rahaza_posting_profiles import get_mapping
import uuid
import logging

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/rahaza', tags=['rahaza-ap-from-gr'])

VARIANCE_TOLERANCE_PCT = 0.5  # ± 0.5% considered matched

# ─────────────────────────────────────────────────────────────────────────────
# PERAN KEUANGAN — SSOT, JANGAN DITULIS ULANG DI TEMPAT LAIN
# ─────────────────────────────────────────────────────────────────────────────
# BUG DITEMUKAN 2026-08-07 DI LAYAR: `_require_finance` memakai daftar peran
# yang ditulis SENDIRI di berkas ini — ('finance', 'manager', 'accountant') —
# padahal peran keuangan yang BENAR-BENAR ada di aplikasi ini adalah
# `accounting`, `staff_keuangan`, `manager_keuangan` (lihat
# `backend/scripts/seed_role_accounts.py` dan `core/pr_approval.FINANCE_APPROVER_ROLES`).
#
# Akibat nyatanya: akun staf keuangan sungguhan (`finance@dewiaditya.id`,
# role `accounting`) mendapat **403** di DUA pintu yang justru pekerjaannya:
#   · 3-Way Match (mencocokkan PO ↔ Penerimaan ↔ Faktur SEBELUM supplier dibayar)
#   · daftar penerimaan yang siap difakturkan
# Menu-nya tampil, layarnya terbuka, tapi datanya selalu kosong — kontrol uang
# yang MATI DIAM-DIAM. Ini kelas bug yang sama dengan laporan owner soal
# Request Aksesoris: DAFTAR PERAN YANG DIDUPLIKASI lalu menyimpang dari kenyataan.
#
# Sekarang gerbangnya memakai helper SSOT `routes.shared.require_perm` (izin
# dinamis menang; daftar peran lama hanya jaring pengaman) — sama seperti modul
# keuangan lain (mis. `dewi_bank_reconciliation.py`).
FINANCE_LEGACY_ROLES = (
    'accounting', 'staff_keuangan', 'manager_keuangan', 'finance', 'finance_manager',
    'accountant', 'manager', 'owner', 'admin', 'superadmin',
)


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)
def _today_iso(): return date.today().isoformat()


async def _require_finance_view(request: Request):
    """Boleh MELIHAT hutang/3-way-match (read-only).

    3-Way Match & daftar penerimaan siap-faktur adalah layar READ-ONLY di dalam
    **Portal Pengadaan**. Kalau gerbangnya keuangan-saja, maka `admin_pengadaan`,
    `manager_pengadaan`, `purchasing`, dan `admin_gudang` — yang menu-nya JELAS
    menampilkan pintu itu — semuanya kena 403 di portalnya sendiri. Jadi izin
    baca mengikuti akses Portal Pengadaan + izin keuangan; yang MENGUBAH hutang
    (membuat faktur) tetap keuangan saja (`_require_finance`).
    """
    from routes.shared import PORTAL_ACCESS, require_perm
    return await require_perm(
        request, 'fin.ap.view', 'fin.ap.manage', 'finance.manage', 'proc.po.manage',
        legacy_roles=FINANCE_LEGACY_ROLES + tuple(PORTAL_ACCESS.get('procurement', ())),
        message='Akses ditolak: butuh akses Portal Pengadaan atau keuangan.')


async def _require_finance(request: Request):
    """Boleh MENGUBAH hutang (membuat faktur dari penerimaan)."""
    from routes.shared import require_perm
    return await require_perm(
        request, 'fin.ap.manage', 'finance.manage',
        legacy_roles=FINANCE_LEGACY_ROLES,
        message='Akses ditolak: butuh izin mengelola hutang supplier (AP).')


# ─────────────────────────────────────────────────────────────────────────────
# Number generators
# ─────────────────────────────────────────────────────────────────────────────
async def _gen_ap_number(db) -> str:
    """Nomor invoice hutang AP-YYMM-NNNN — race-safe & formatnya bisa diatur owner
    (kunci `rahaza_ap_invoices.invoice_number`)."""
    yymm = date.today().strftime('%y%m')
    return await gen_prefixed_number(db, 'rahaza_ap_invoices', 'invoice_number',
                                     f'AP-{yymm}-', 4)


# ─────────────────────────────────────────────────────────────────────────────
# GRs Available for Invoice
# ─────────────────────────────────────────────────────────────────────────────
@router.get('/grs/available-for-invoice')
async def grs_available_for_invoice(
    vendor_name: Optional[str] = None,
    po_id: Optional[str] = None,
    request: Request = None,
):
    """
    List GRs that are received but NOT yet invoiced.
    
    Criteria:
    - status in ('received', 'completed', 'partial_received') — GR sudah dikerjakan
    - At least one item has received_qty > 0
    - GR doc has no `ap_invoice_id` field yet (not yet invoiced)
    
    Filters: vendor_name, po_id.
    """
    await _require_finance_view(request)
    db = get_db()
    q: Dict[str, Any] = {
        'status': {'$in': ['received', 'completed', 'partial_received']},
        '$or': [
            {'ap_invoice_id': {'$exists': False}},
            {'ap_invoice_id': None},
            {'ap_invoice_id': ''},
        ]
    }
    if vendor_name:
        q['supplier_name'] = {'$regex': vendor_name, '$options': 'i'}
    if po_id:
        q['po_id'] = po_id

    grs = await db.warehouse_receiving.find(q, {'_id': 0}).sort('created_at', -1).limit(200).to_list(200)

    out = []
    for gr in grs:
        items = gr.get('items') or []
        total_received = sum(float(i.get('received_qty', 0) or 0) for i in items)
        if total_received <= 0:
            # Skip GR with no actual received qty (might still be a draft)
            continue
        total_rejected = sum(float(i.get('rejected_qty', 0) or 0) for i in items)
        total_net = total_received - total_rejected
        # Compute receivable amount = sum(received_qty * unit_cost) for net items
        receivable_amount = sum(
            float(i.get('received_qty', 0) or 0) * float(i.get('unit_cost') or i.get('unit_price') or 0)
            - float(i.get('rejected_qty', 0) or 0) * float(i.get('unit_cost') or i.get('unit_price') or 0)
            for i in items
        )
        out.append({
            'id': gr['id'],
            'receipt_number': gr.get('receipt_number'),
            'po_id': gr.get('po_id'),
            'po_number': gr.get('po_number'),
            'supplier_name': gr.get('supplier_name'),
            'supplier_id': gr.get('supplier_id'),
            'supplier_code': gr.get('supplier_code'),
            'status': gr.get('status'),
            'received_at': gr.get('received_at') or gr.get('completed_at') or gr.get('updated_at'),
            'items_count': len(items),
            'total_expected': sum(float(i.get('expected_qty', 0) or 0) for i in items),
            'total_received': total_received,
            'total_rejected': total_rejected,
            'total_net': total_net,
            'receivable_amount': round(receivable_amount, 2),
        })
    return {'total': len(out), 'items': serialize_doc(out)}


# ─────────────────────────────────────────────────────────────────────────────
# Create AP Invoice from GR(s)
# ─────────────────────────────────────────────────────────────────────────────
class CreateAPFromGRItem(BaseModel):
    gr_item_id: str
    invoiced_qty: float = Field(..., gt=0)
    unit_price: Optional[float] = Field(default=None, ge=0)  # Override price; default = GR unit_cost
    description: Optional[str] = None


class CreateAPFromGRPayload(BaseModel):
    gr_ids: List[str] = Field(..., min_length=1)
    items_override: Optional[List[CreateAPFromGRItem]] = None  # optional partial invoicing
    tax_pct: Optional[float] = Field(default=0.0, ge=0)
    issue_date: Optional[str] = None
    due_date: Optional[str] = None
    notes: Optional[str] = None
    payment_terms: Optional[str] = None


@router.post('/ap-invoices/from-gr', status_code=201)
async def create_ap_invoice_from_gr(payload: CreateAPFromGRPayload, request: Request):
    """
    Create AP Invoice from one or more Goods Receipts.

    Workflow:
    1. Validate all GRs exist, status received/completed, not yet invoiced, same vendor.
    2. Build invoice lines from GR.items (received_qty - rejected_qty) × unit_cost.
    3. If `items_override` provided, only invoice those specific lines with custom qty/price.
    4. Create AP Invoice in `rahaza_ap_invoices` with status='draft', linkages to PO + GR(s).
    5. Mark all GRs with ap_invoice_id, ap_invoice_number, invoiced_at.

    Returns the new AP invoice doc.
    """
    user = await _require_finance(request)
    db = get_db()

    grs = await db.warehouse_receiving.find(
        {'id': {'$in': payload.gr_ids}}, {'_id': 0}
    ).to_list(length=len(payload.gr_ids))
    found_ids = {g['id'] for g in grs}
    missing = set(payload.gr_ids) - found_ids
    if missing:
        raise HTTPException(404, f'GR tidak ditemukan: {sorted(missing)}')

    # Validate all GRs: status, not yet invoiced, same vendor
    vendor_name = None
    po_ids = set()
    po_numbers = set()
    for gr in grs:
        if gr.get('status') not in ('received', 'completed', 'partial_received'):
            raise HTTPException(400, f"GR {gr.get('receipt_number')} status '{gr.get('status')}' belum siap di-invoice.")
        if gr.get('ap_invoice_id'):
            raise HTTPException(400, f"GR {gr.get('receipt_number')} sudah memiliki AP Invoice {gr.get('ap_invoice_number')}.")
        gr_vendor = (gr.get('supplier_name') or '').strip()
        if not gr_vendor:
            raise HTTPException(400, f"GR {gr.get('receipt_number')} tidak ada supplier_name.")
        if vendor_name is None:
            vendor_name = gr_vendor
        elif vendor_name.lower() != gr_vendor.lower():
            raise HTTPException(400, f'GRs harus dari supplier yang sama. Mismatch: {vendor_name} vs {gr_vendor}.')
        if gr.get('po_id'):
            po_ids.add(gr['po_id'])
        if gr.get('po_number'):
            po_numbers.add(gr['po_number'])

    if not vendor_name:
        raise HTTPException(400, 'Vendor tidak teridentifikasi dari GRs.')

    # Build override map if provided
    override_map = {it.gr_item_id: it for it in (payload.items_override or [])}

    # Build invoice items
    inv_items: List[Dict[str, Any]] = []
    for gr in grs:
        for li in (gr.get('items') or []):
            li_id = li.get('id') or li.get('po_item_id')
            received_qty = float(li.get('received_qty', 0) or 0)
            rejected_qty = float(li.get('rejected_qty', 0) or 0)
            net_qty = received_qty - rejected_qty
            unit_cost = float(li.get('unit_cost') or li.get('unit_price') or 0)  # GR manual simpan unit_price

            if override_map:
                # Only invoice items in override map
                if li_id not in override_map:
                    continue
                ov = override_map[li_id]
                inv_qty = ov.invoiced_qty
                inv_price = ov.unit_price if ov.unit_price is not None else unit_cost
                inv_desc = ov.description or li.get('material_name') or li.get('product_name') or ''
            else:
                if net_qty <= 0:
                    continue
                inv_qty = net_qty
                inv_price = unit_cost
                inv_desc = li.get('material_name') or li.get('product_name') or 'Item'

            amt = round(inv_qty * inv_price, 2)
            inv_items.append({
                'id': _uid(),
                'gr_id': gr['id'],
                'gr_number': gr.get('receipt_number'),
                'gr_item_id': li_id,
                'po_item_id': li.get('po_item_id'),
                'material_id': li.get('material_id'),
                'material_name': li.get('material_name') or li.get('product_name'),
                'description': inv_desc,
                # `unit` = satuan DASAR (qty di GR selalu satuan dasar, INV-UOM-2);
                # `po_uom` = satuan beli PO supaya faktur bisa dicetak dalam kemasan
                'unit': li.get('base_uom') or li.get('unit') or 'pcs',
                'po_uom': li.get('po_uom') or li.get('base_uom') or li.get('unit') or 'pcs',
                'uom_factor': float(li.get('uom_factor') or 1),
                'qty': inv_qty,
                'qty_input': round(inv_qty / (float(li.get('uom_factor') or 1) or 1), 6),
                'price': inv_price,
                'price_input': round(inv_price * (float(li.get('uom_factor') or 1) or 1), 4),
                'amount': amt,
            })

    if not inv_items:
        raise HTTPException(400, 'Tidak ada item yang bisa di-invoice (semua sudah di-invoice / quantity 0).')

    subtotal = sum(it['amount'] for it in inv_items)
    tax_pct = float(payload.tax_pct or 0)
    tax_amount = round(subtotal * tax_pct / 100, 2)
    total = round(subtotal + tax_amount, 2)

    # Determine supplier linkage (SSOT master) + vendor_code dari PO bila ada
    vendor_code = ''
    supplier_id = None
    supplier_code = None
    for gr in grs:
        if gr.get('supplier_id'):
            supplier_id = gr['supplier_id']
            supplier_code = gr.get('supplier_code')
            break
    if po_ids:
        po_doc = await db.rahaza_purchase_orders.find_one(
            {'id': {'$in': list(po_ids)}},
            {'_id': 0, 'vendor_code': 1, 'supplier_id': 1, 'supplier_code': 1,
             'payment_terms': 1})
        if po_doc:
            vendor_code = po_doc.get('vendor_code', '') or po_doc.get('supplier_code', '') or ''
            supplier_id = supplier_id or po_doc.get('supplier_id')
            supplier_code = supplier_code or po_doc.get('supplier_code')
    if not supplier_id and vendor_name:
        # PO/GR lama tanpa tautan: resolusi lewat nama ternormalisasi master supplier
        try:
            from routes.procurement_suppliers import name_key as _nk
            sup = await db.rahaza_suppliers.find_one(
                {'name_key': _nk(vendor_name)}, {'_id': 0, 'id': 1, 'code': 1})
            if sup:
                supplier_id = sup['id']
                supplier_code = sup.get('code')
        except Exception:
            log.debug('resolusi supplier via name_key gagal', exc_info=True)
    if supplier_code and not vendor_code:
        vendor_code = supplier_code

    invoice_number = await _gen_ap_number(db)
    doc = {
        'id': _uid(),
        'invoice_number': invoice_number,
        'vendor_name': vendor_name,
        'vendor_code': vendor_code,
        'supplier_id': supplier_id,
        'supplier_code': supplier_code,
        'issue_date': payload.issue_date or _today_iso(),
        'due_date': payload.due_date or _today_iso(),
        'items': inv_items,
        'subtotal': round(subtotal, 2),
        'tax_pct': tax_pct,
        'tax_amount': tax_amount,
        'total': total,
        'paid_amount': 0,
        'balance': total,
        'status': 'draft',
        'notes': payload.notes or f'Auto-created from GR(s) {", ".join(sorted(gr.get("receipt_number","") for gr in grs))}',
        'payment_terms': payload.payment_terms,
        # P2P 3-way match linkage
        'source': 'gr',
        # C-02: tagihan atas barang yang SUDAH diterima → Dr GRNI (bukan beban), Cr AP
        'gl_debit_code': (await get_mapping(db, 'ap_invoice')).get('debit_grni'),
        'gr_ids': sorted([gr['id'] for gr in grs]),
        'gr_numbers': sorted([gr.get('receipt_number', '') for gr in grs]),
        'po_ids': sorted(po_ids),
        'po_numbers': sorted(po_numbers),
        'created_at': _now(),
        'updated_at': _now(),
        'created_by': user['id'],
        'created_by_name': user.get('name', ''),
    }
    await db.rahaza_ap_invoices.insert_one(doc)

    # Stamp ap_invoice_id on all GRs
    await db.warehouse_receiving.update_many(
        {'id': {'$in': payload.gr_ids}},
        {'$set': {
            'ap_invoice_id': doc['id'],
            'ap_invoice_number': invoice_number,
            'invoiced_at': _now(),
            'updated_at': _now(),
        }}
    )

    await log_activity(
        user['id'], user.get('name', ''),
        'create_from_gr', 'rahaza_ap_invoices',
        f'Buat AP Invoice {invoice_number} dari {len(grs)} GR. Total Rp {int(total):,}',
    )
    return serialize_doc(doc)


# ─────────────────────────────────────────────────────────────────────────────
# 3-way Match Dashboard
# ─────────────────────────────────────────────────────────────────────────────
@router.get('/3way-match')
async def three_way_match_dashboard(
    request: Request,
    status: Optional[str] = Query(None, description='Filter: matched|variance|over|under|pending'),
    vendor_name: Optional[str] = None,
    supplier_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """
    PO ↔ GR ↔ AP Invoice reconciliation dashboard.
    
    Returns one row per PO with:
    - po_id, po_number, vendor_name, total_value (ordered)
    - gr_count, total_received_qty, total_received_value
    - invoice_count, total_invoiced_value, total_paid
    - qty_variance, value_variance, variance_pct
    - status (matched / variance / over / under / pending)
    """
    await _require_finance_view(request)
    db = get_db()

    po_query: Dict[str, Any] = {
        'status': {'$in': ['approved', 'partially_received', 'fully_received']}
    }
    if vendor_name:
        po_query['vendor_name'] = {'$regex': vendor_name, '$options': 'i'}
    if supplier_id:
        po_query['supplier_id'] = supplier_id

    pos = await db.rahaza_purchase_orders.find(
        po_query, {'_id': 0}
    ).sort('po_date', -1).limit(limit).to_list(limit)

    rows = []
    for po in pos:
        po_id = po['id']
        items = po.get('items', []) or []
        total_ordered_qty = sum(float(it.get('qty_ordered', 0) or 0) for it in items)
        # Compute ordered_value: prefer doc field, fallback to summed line subtotals (handles older POs without total_value)
        total_ordered_value = float(po.get('total_value', 0) or 0)
        if total_ordered_value <= 0 and items:
            total_ordered_value = sum(
                float(it.get('subtotal', 0) or 0) or (float(it.get('qty_ordered', 0) or 0) * float(it.get('unit_cost', 0) or 0))
                for it in items
            )

        # GRs
        grs = await db.warehouse_receiving.find(
            {'po_id': po_id, 'status': {'$in': ['received', 'completed', 'partial_received']}},
            {'_id': 0}
        ).to_list(length=200)
        gr_count = len(grs)
        total_received_qty = 0.0
        total_received_value = 0.0
        for gr in grs:
            for li in (gr.get('items') or []):
                rq = float(li.get('received_qty', 0) or 0)
                rj = float(li.get('rejected_qty', 0) or 0)
                uc = float(li.get('unit_cost') or li.get('unit_price') or 0)
                total_received_qty += rq - rj
                total_received_value += (rq - rj) * uc

        # AP Invoices linked
        invoices = await db.rahaza_ap_invoices.find(
            {'po_ids': po_id, 'status': {'$ne': 'cancelled'}},
            {'_id': 0}
        ).to_list(length=200)
        invoice_count = len(invoices)
        total_invoiced_qty = 0.0
        total_invoiced_value = 0.0      # tax-inclusive (for display)
        total_invoiced_subtotal = 0.0   # pre-tax (matching basis vs goods value)
        total_paid = 0.0
        for inv in invoices:
            inv_total = float(inv.get('total', 0) or 0)
            total_invoiced_value += inv_total
            inv_subtotal = inv.get('subtotal')
            if inv_subtotal is None:
                inv_subtotal = inv_total - float(inv.get('tax_amount', 0) or 0)
            total_invoiced_subtotal += float(inv_subtotal or 0)
            total_paid += float(inv.get('paid_amount', 0) or 0)
            for li in (inv.get('items') or []):
                total_invoiced_qty += float(li.get('qty', 0) or 0)

        # Variance — compare pre-tax invoice value against goods received value
        # (PPN/tax is not part of the goods value, so it must be excluded here).
        qty_variance = round(total_invoiced_qty - total_received_qty, 4)
        value_variance = round(total_invoiced_subtotal - total_received_value, 2)
        variance_pct = (
            (value_variance / total_received_value * 100) if total_received_value > 0 else 0
        )

        if invoice_count == 0:
            match_status = 'pending'
        elif abs(variance_pct) <= VARIANCE_TOLERANCE_PCT:
            match_status = 'matched'
        elif value_variance > 0:
            match_status = 'over'
        else:
            match_status = 'under'

        if status and status != match_status:
            continue

        rows.append({
            'po_id': po_id,
            'po_number': po.get('po_number'),
            'po_date': po.get('po_date'),
            'vendor_name': po.get('vendor_name'),
            'vendor_code': po.get('vendor_code', '') or po.get('supplier_code', ''),
            'supplier_id': po.get('supplier_id'),
            'supplier_code': po.get('supplier_code'),
            'po_status': po.get('status'),
            'total_ordered_qty': round(total_ordered_qty, 4),
            'total_ordered_value': round(total_ordered_value, 2),
            'gr_count': gr_count,
            'total_received_qty': round(total_received_qty, 4),
            'total_received_value': round(total_received_value, 2),
            'invoice_count': invoice_count,
            'total_invoiced_qty': round(total_invoiced_qty, 4),
            'total_invoiced_value': round(total_invoiced_value, 2),
            'total_paid': round(total_paid, 2),
            'qty_variance': qty_variance,
            'value_variance': value_variance,
            'variance_pct': round(variance_pct, 2),
            'match_status': match_status,
        })

    # Summary KPIs
    kpis = {
        'total_pos': len(rows),
        'matched': sum(1 for r in rows if r['match_status'] == 'matched'),
        'pending': sum(1 for r in rows if r['match_status'] == 'pending'),
        'variance': sum(1 for r in rows if r['match_status'] in ('over', 'under')),
        'over': sum(1 for r in rows if r['match_status'] == 'over'),
        'under': sum(1 for r in rows if r['match_status'] == 'under'),
        'total_ordered_value': round(sum(r['total_ordered_value'] for r in rows), 2),
        'total_received_value': round(sum(r['total_received_value'] for r in rows), 2),
        'total_invoiced_value': round(sum(r['total_invoiced_value'] for r in rows), 2),
        'total_paid': round(sum(r['total_paid'] for r in rows), 2),
    }

    return {'kpis': kpis, 'rows': rows, 'tolerance_pct': VARIANCE_TOLERANCE_PCT}


@router.get('/3way-match/{po_id}')
async def three_way_match_detail(po_id: str, request: Request):
    """Detail line-by-line PO ↔ GR ↔ AP Invoice reconciliation for one PO."""
    await _require_finance_view(request)
    db = get_db()

    po = await db.rahaza_purchase_orders.find_one({'id': po_id}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')

    grs = await db.warehouse_receiving.find({'po_id': po_id}, {'_id': 0}).to_list(length=200)
    invoices = await db.rahaza_ap_invoices.find(
        {'po_ids': po_id, 'status': {'$ne': 'cancelled'}}, {'_id': 0}
    ).to_list(length=200)

    # ── Per-line breakdown ───────────────────────────────────────────────────
    # 2026-08-06 (Portal Pengadaan) BUGFIX: dulu kunci baris = `material_id`.
    # Satu PO yang memesan MATERIAL SAMA dua kali (mis. 10 karton + 5 bungkus,
    # atau harga beda per batch) membuat kedua baris SALING MENIMPA ⇒ satu baris
    # hilang dari rekonsiliasi dan variance jadi salah. Kunci kanonik sekarang
    # adalah `po_items[].id` (stabil & unik), dengan peta bantu material_id →
    # baris HANYA bila material itu muncul sekali (kompatibilitas GR/invoice lama
    # yang tidak menyimpan `po_item_id`).
    po_items = po.get('items') or []
    line_map: Dict[str, Dict[str, Any]] = {}
    mid_alias: Dict[str, Any] = {}   # material_id -> line key | None (bila ambigu)
    for idx, it in enumerate(po_items):
        key = it.get('id') or f"line-{idx}"
        factor = float(it.get('uom_factor') or 1) or 1
        line_map[key] = {
            'po_item_id': it.get('id'),
            'material_id': it.get('material_id'),
            'material_code': it.get('material_code'),
            'material_name': (it.get('material_name') or it.get('description')
                              or '(item bebas)'),
            'unit': it.get('base_uom') or it.get('unit', 'pcs'),
            'uom': it.get('uom') or it.get('base_uom') or it.get('unit', 'pcs'),
            'uom_factor': factor,
            'po_qty': float(it.get('qty_ordered', 0) or 0),
            'po_qty_input': round(float(it.get('qty_ordered', 0) or 0) / factor, 6),
            'po_unit_cost': float(it.get('unit_cost', 0) or 0),
            'po_unit_cost_input': float(it.get('unit_cost_input')
                                        or float(it.get('unit_cost', 0) or 0) * factor),
            'po_subtotal': float(it.get('subtotal', 0) or 0)
            or round(float(it.get('qty_ordered', 0) or 0) * float(it.get('unit_cost', 0) or 0), 2),
            'received_qty': 0,
            'rejected_qty': 0,
            'net_qty': 0,
            'received_value': 0,
            'invoiced_qty': 0,
            'invoiced_amount': 0,
        }
        mid = it.get('material_id')
        if mid:
            mid_alias[mid] = key if mid not in mid_alias else None

    def _resolve_line(li: Dict[str, Any]):
        k = li.get('po_item_id')
        if k and k in line_map:
            return k
        mid = li.get('material_id')
        if mid and mid_alias.get(mid):
            return mid_alias[mid]
        return None

    for gr in grs:
        for li in (gr.get('items') or []):
            key = _resolve_line(li)
            if not key:
                continue
            rq = float(li.get('received_qty', 0) or 0)
            rj = float(li.get('rejected_qty', 0) or 0)
            uc = float(li.get('unit_cost', 0) or 0)
            line_map[key]['received_qty'] += rq
            line_map[key]['rejected_qty'] += rj
            line_map[key]['net_qty'] += rq - rj
            line_map[key]['received_value'] += (rq - rj) * uc

    for inv in invoices:
        for li in (inv.get('items') or []):
            key = _resolve_line(li)
            if not key:
                continue
            line_map[key]['invoiced_qty'] += float(li.get('qty', 0) or 0)
            line_map[key]['invoiced_amount'] += float(li.get('amount', 0) or 0)

    # Compute variance + status per line
    lines = []
    for key, ld in line_map.items():
        qty_variance = round(ld['invoiced_qty'] - ld['net_qty'], 4)
        value_variance = round(ld['invoiced_amount'] - ld['received_value'], 2)
        variance_pct = (value_variance / ld['received_value'] * 100) if ld['received_value'] > 0 else 0
        if ld['invoiced_qty'] == 0:
            status = 'pending'
        elif abs(variance_pct) <= VARIANCE_TOLERANCE_PCT:
            status = 'matched'
        elif value_variance > 0:
            status = 'over'
        else:
            status = 'under'
        ld.update({
            'qty_variance': qty_variance,
            'value_variance': value_variance,
            'variance_pct': round(variance_pct, 2),
            'match_status': status,
            'po_subtotal': round(ld['po_subtotal'], 2),
            'received_value': round(ld['received_value'], 2),
            'invoiced_amount': round(ld['invoiced_amount'], 2),
        })
        lines.append(ld)

    return {
        'po': serialize_doc(po),
        'grs': serialize_doc(grs),
        'invoices': serialize_doc(invoices),
        'lines': lines,
        'tolerance_pct': VARIANCE_TOLERANCE_PCT,
    }
