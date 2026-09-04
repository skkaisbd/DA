"""
CV. Dewi Aditya — Portal Maklon Billing & Invoice
Phase 3C: Auto-generate invoice from orders, payment tracking, monthly reports, HPP

Collections:
- dewi_maklon_invoices: Invoice header + lines
- dewi_maklon_payments: Payment records against invoices
- dewi_maklon_hpp: HPP (Cost of Goods) breakdown per order
"""
import logging
from fastapi import APIRouter, HTTPException, Depends
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone, timedelta, date
from database import get_db
from auth import require_auth
from routes.dewi_system_config import get_config_value
from routes._maklon_adapter import find_maklon_record, po_to_legacy_order
from utils.data_quality import SkipTracker
import uuid

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/dewi/maklon', tags=['Dewi-Maklon-Billing'], dependencies=[Depends(deny_external_dep)])
# ══════════════════════════════════════════════════════════════════════════════
# MODELS
# ══════════════════════════════════════════════════════════════════════════════

INVOICE_STATUSES = ['draft', 'issued', 'partial_paid', 'paid', 'overdue', 'cancelled']
PAYMENT_METHODS = ['transfer', 'cash', 'check', 'giro', 'other']

class InvoiceGenerateIn(BaseModel):
    order_id: str
    tax_pct: Optional[float] = Field(default=None, ge=0)
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    issue_date: Optional[str] = None  # YYYY-MM-DD
    # FASE G (sesi #18) — nomor invoice ketikan; hanya sah bila kebijakan penomoran
    # jenis dokumen ini disetel MANUAL (kalau OTOMATIS, nomor ketikan ditolak).
    invoice_number: Optional[str] = None

class InvoiceUpdateIn(BaseModel):
    notes: Optional[str] = None
    tax_pct: Optional[float] = Field(default=None, ge=0)
    discount_amount: Optional[float] = Field(default=None, ge=0)
    due_date: Optional[str] = None

class PaymentIn(BaseModel):
    invoice_id: str
    amount: float = Field(..., gt=0)
    method: str = Field(default='transfer')
    reference_no: Optional[str] = None
    payment_date: Optional[str] = None
    notes: Optional[str] = None
    cash_account_id: Optional[str] = None  # rahaza_cash_accounts.id → akun bank GL (Dr)

class HPPComponent(BaseModel):
    name: str
    category: str = Field(default='material', description="material | labor | overhead | packaging | other")
    qty: float = Field(ge=0, default=1)
    unit: Optional[str] = 'pcs'
    unit_cost: float = Field(ge=0, default=0)
    total: Optional[float] = Field(default=None, ge=0)  # auto-calc

class HPPIn(BaseModel):
    order_id: str
    components: List[HPPComponent] = Field(default_factory=list)
    overhead_pct: Optional[float] = None
    profit_margin_pct: Optional[float] = None
    notes: Optional[str] = None

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _clean(doc: dict) -> dict:
    if not doc:
        return doc
    doc.pop('_id', None)
    return doc

async def _next_invoice_number(db, prefix: str, requested: str = '') -> str:
    """Nomor invoice maklon manual — race-safe & formatnya bisa diatur owner
    (kunci `dewi_maklon_invoices.invoice_number`, token {PREFIX}).

    FASE G (sesi #18): lewat `issue_number` supaya mode OTOMATIS/MANUAL yang disetel
    System Admin benar-benar DITEGAKKAN (mode manual = nomor diketik tetapi wajib
    mengikuti polanya; mode otomatis MENOLAK nomor ketikan, bukan mengabaikannya).
    """
    from core.doc_number_policy import issue_number
    return await issue_number(db, 'dewi_maklon_invoices.invoice_number',
                              ctx={'PREFIX': prefix}, requested=requested)

def _payment_term_days(term: str) -> int:
    mapping = {'net_7': 7, 'net_14': 14, 'net_30': 30, 'net_60': 60}
    return mapping.get(term, 30)

async def _recalc_invoice(db, invoice_id: str) -> dict:
    """Recalculate subtotal, tax, total, paid, balance. Update status."""
    inv = await db.dewi_maklon_invoices.find_one({'id': invoice_id})
    if not inv:
        return {}
    subtotal = sum(float(ln.get('line_total', 0) or 0) for ln in inv.get('lines', []))
    discount = float(inv.get('discount_amount', 0) or 0)
    tax_pct = float(inv.get('tax_pct', 0) or 0)
    tax_base = max(subtotal - discount, 0)
    tax_amount = round(tax_base * tax_pct / 100, 2)
    total = round(tax_base + tax_amount, 2)

    payments = await db.dewi_maklon_payments.find({'invoice_id': invoice_id}).to_list(length=100)
    paid = round(sum(float(p.get('amount', 0) or 0) for p in payments), 2)
    balance = round(total - paid, 2)

    # Status resolution
    status = inv.get('status', 'draft')
    if status != 'cancelled':
        if paid <= 0:
            now = datetime.now(timezone.utc).date()
            due = inv.get('due_date')
            try:
                due_d = date.fromisoformat(due) if due else None
            except ValueError:
                due_d = None
            if due_d and due_d < now and status != 'draft':
                status = 'overdue'
            elif status == 'draft':
                status = 'draft'
            else:
                status = 'issued'
        elif paid < total:
            status = 'partial_paid'
        else:
            status = 'paid'

    update = {
        'subtotal': round(subtotal, 2),
        'tax_amount': tax_amount,
        'total_amount': total,
        'paid_amount': paid,
        'balance_amount': balance,
        'status': status,
        'updated_at': datetime.now(timezone.utc),
    }
    await db.dewi_maklon_invoices.update_one({'id': invoice_id}, {'$set': update})
    # SATU SUMBER INVOICE: dokumen layar Invoice adalah cermin AR otomatis (`rahaza_ar_invoices`,
    # id sama). Pembayaran/pajak/status dirambatkan supaya Finance & Maklon membaca angka yang sama.
    if inv.get('ar_invoice_id'):
        ar_status = {'paid': 'paid', 'cancelled': 'cancelled', 'draft': 'draft', 'partial_paid': 'partial_paid',
                     'overdue': 'overdue'}.get(status, 'issued')
        await db.rahaza_ar_invoices.update_one({'id': inv['ar_invoice_id']}, {'$set': {
            'tax_pct': tax_pct, 'tax_amount': tax_amount, 'discount_amount': discount,
            'subtotal': round(subtotal, 2), 'total_amount': total,
            'amount_paid': paid, 'amount_due': balance, 'status': ar_status,
            'total': total, 'paid_amount': paid, 'balance': balance,  # cermin lama (H-01)
            'updated_at': datetime.now(timezone.utc)}})
    return update


async def _billable_preview(db, mirror: dict) -> dict:
    from routes.production_maklon_bridge import billable_lines_for_po
    bill = await billable_lines_for_po(db, mirror['id'])
    return {
        'id': mirror['id'], 'source': 'engine_ar', 'po_number': mirror.get('po_number'),
        'order_code': mirror.get('po_number'), 'client_id': mirror.get('client_id'),
        'client_name': mirror.get('client_name'), 'status': mirror.get('status'),
        'ar_invoice_number': mirror.get('ar_invoice_number'),
        'total_ordered': bill['total_ordered'], 'total_received': bill['total_received'],
        'subtotal': bill['subtotal'], 'line_count': len(bill['lines']), 'lines': bill['lines'],
        'billable': bool(bill['lines']),
    }


async def _generate_from_engine_ar(db, mirror: dict, payload: 'InvoiceGenerateIn', user: dict) -> dict:
    """PO engine (mirror production_pos): TERBITKAN AR otomatis yang sudah ada — bukan
    membuat dokumen/nomor kedua. Nomor = nomor AR; qty = yang diterima klien × harga jasa."""
    from routes.production_maklon_bridge import billable_lines_for_po, try_sync_maklon_finance
    po_id = mirror['id']
    if mirror.get('status') in ('draft', 'cancelled'):
        raise HTTPException(400, f"PO berstatus {mirror.get('status')} tidak bisa diinvoice")
    existing = await db.dewi_maklon_invoices.find_one(
        {'order_id': po_id, 'status': {'$ne': 'cancelled'}}, {'_id': 0, 'invoice_number': 1})
    if existing:
        raise HTTPException(400, f'PO sudah memiliki invoice {existing.get("invoice_number")}')
    ar = None
    if mirror.get('ar_invoice_id'):
        ar = await db.rahaza_ar_invoices.find_one(
            {'id': mirror['ar_invoice_id'], 'source_module': 'maklon_po'}, {'_id': 0})
    if not ar:
        await try_sync_maklon_finance(db, po_id, user)
        m2 = await db.dewi_maklon_pos.find_one({'id': po_id}, {'_id': 0, 'ar_invoice_id': 1}) or {}
        if m2.get('ar_invoice_id'):
            ar = await db.rahaza_ar_invoices.find_one({'id': m2['ar_invoice_id']}, {'_id': 0})
    if not ar:
        raise HTTPException(400, 'AR otomatis belum terbentuk — PO harus sudah Confirmed')
    # AR 'issued' TANPA dokumen layar aktif = yatim (cancel lama tidak sempat mengembalikan
    # AR ke draft). Selama belum dibayar & belum diposting GL, terbitkan ulang saja.
    ar_status = ar.get('status') or 'draft'
    orphan_issued = (ar_status == 'issued' and not ar.get('gl_posted_at')
                     and float(ar.get('amount_paid') or 0) <= 0)
    if ar_status != 'draft' and not orphan_issued:
        raise HTTPException(400, f"AR {ar.get('invoice_number')} sudah berstatus {ar_status}")
    if (payload.invoice_number or '').strip() and payload.invoice_number.strip() != ar.get('invoice_number'):
        raise HTTPException(400, f"Nomor invoice PO ini mengikuti AR otomatis {ar.get('invoice_number')} — "
                                 'kosongkan kolom nomor.')
    bill = await billable_lines_for_po(db, po_id)
    if not bill['lines']:
        raise HTTPException(400, 'Belum ada qty yang dikirim/diterima klien — tidak ada yang bisa ditagih')

    tax_default = float(await get_config_value(db, 'maklon_tax_pct', 11.0) or 0)
    term_default = await get_config_value(db, 'maklon_payment_terms_default', 'net_30') or 'net_30'
    tax_pct = payload.tax_pct if payload.tax_pct is not None else tax_default
    term = payload.payment_terms or term_default
    issue = payload.issue_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    try:
        issue_d = date.fromisoformat(issue)
    except ValueError:
        raise HTTPException(400, 'issue_date tidak valid (YYYY-MM-DD)')
    due_d = issue_d + timedelta(days=_payment_term_days(term))
    now = datetime.now(timezone.utc)
    subtotal = bill['subtotal']
    tax_amount = round(subtotal * tax_pct / 100, 2)
    total = round(subtotal + tax_amount, 2)

    await db.rahaza_ar_invoices.update_one({'id': ar['id']}, {'$set': {
        'lines': bill['lines'], 'subtotal': subtotal, 'tax_pct': tax_pct, 'tax_amount': tax_amount,
        'discount_amount': 0.0, 'total_amount': total, 'amount_paid': 0.0, 'amount_due': total,
        'invoice_date': issue_d.isoformat(), 'due_date': due_d.isoformat(), 'payment_terms': term,
        'status': 'issued', 'issued_at': now, 'issued_by': user.get('name', ''),
        'billing_basis': 'received_qty_x_selling_price',
        'notes': (payload.notes or ar.get('notes') or ''), 'updated_at': now}})
    doc = {
        'id': ar['id'], 'invoice_number': ar['invoice_number'], 'ar_invoice_id': ar['id'],
        'source': 'engine_ar', 'order_id': po_id, 'order_code': mirror.get('po_number'),
        'po_id': po_id, 'po_number': mirror.get('po_number'),
        'client_id': mirror.get('client_id'), 'client_name': mirror.get('client_name'),
        'issue_date': issue_d.isoformat(), 'due_date': due_d.isoformat(), 'payment_terms': term,
        'tax_pct': tax_pct, 'discount_amount': 0.0,
        'lines': [{'description': ln['description'], 'qty': ln['qty'], 'unit': 'pcs',
                   'unit_price': ln['unit_price'], 'line_total': ln['line_total'],
                   'item_id': ln['item_id'], 'sku': ln['sku'], 'qty_ordered': ln['qty_ordered']}
                  for ln in bill['lines']],
        'subtotal': subtotal, 'tax_amount': 0.0, 'total_amount': 0.0, 'paid_amount': 0.0,
        'balance_amount': 0.0, 'status': 'issued', 'notes': payload.notes,
        'created_at': now, 'updated_at': now, 'created_by': user.get('name', 'System'),
    }
    # Idempoten: dokumen cancelled lama dgn id/nomor sama (sisa cancel versi lama) tidak boleh
    # membuat unique index `invoice_number` menolak penerbitan ulang (iter 105 DuplicateKeyError).
    await db.dewi_maklon_invoices.delete_many({
        'status': 'cancelled',
        '$or': [{'id': ar['id']}, {'invoice_number': ar['invoice_number']}]})
    await db.dewi_maklon_invoices.replace_one({'id': ar['id']}, doc, upsert=True)
    await db.dewi_maklon_pos.update_one({'id': po_id}, {'$set': {
        'status': 'invoiced', 'ar_invoice_id': ar['id'], 'ar_invoice_number': ar['invoice_number'],
        'updated_at': now}})
    await _recalc_invoice(db, doc['id'])
    # C-06: penerbitan invoice maklon WAJIB masuk GL (Dr AR / Cr Pendapatan / Cr PPN) — non-fatal.
    from routes.dewi_maklon_finance import post_maklon_ar_invoice
    po_fresh = await db.dewi_maklon_pos.find_one({'id': po_id}, {'_id': 0}) or mirror
    await post_maklon_ar_invoice(db, po_fresh, user)
    await _notify_client_invoice(db, doc, mirror.get('po_number'))
    return _clean(await db.dewi_maklon_invoices.find_one({'id': doc['id']}))


async def _notify_client_invoice(db, doc: dict, order_code: str):
    try:
        from routes.dewi_notifications import queue_for_client
        body = (f"Invoice baru {doc.get('invoice_number')} untuk order {order_code} telah diterbitkan. "
                f"Total Rp {int(doc.get('total_amount') or 0):,}, jatuh tempo {doc.get('due_date')}.").replace(',', '.')
        await queue_for_client(db, client_id=doc.get('client_id'),
                               subject=f"Invoice baru — {doc.get('invoice_number')}", body=body,
                               event_type='invoice_issued', source_ref=doc['id'],
                               meta={'invoice_number': doc.get('invoice_number'), 'total': doc.get('total_amount')})
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

# ══════════════════════════════════════════════════════════════════════════════
# INVOICE ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/invoices')
async def list_invoices(
    status: Optional[str] = None,
    client_id: Optional[str] = None,
    order_id: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    db = get_db()
    query = {}
    if status:
        query['status'] = status
    if client_id:
        query['client_id'] = client_id
    if order_id:
        query['order_id'] = order_id
    if from_date or to_date:
        rng = {}
        if from_date:
            rng['$gte'] = from_date
        if to_date:
            rng['$lte'] = to_date
        query['issue_date'] = rng
    items = await db.dewi_maklon_invoices.find(query).sort('issue_date', -1).to_list(length=500)
    return [_clean(i) for i in items]

@router.get('/invoices/eligible')
async def list_eligible_for_invoice(user: dict = Depends(require_auth)):
    """PO yang bisa ditagih: mirror engine (AR otomatis, qty diterima × harga jasa) + PO legacy
    tanpa mirror. Satu daftar untuk dialog Generate supaya angka pratinjau = angka dokumen."""
    db = get_db()
    invoiced = set(await db.dewi_maklon_invoices.distinct('order_id', {'status': {'$ne': 'cancelled'}}))
    out = []
    async for po in db.dewi_maklon_pos.find(
            {'status': {'$nin': ['draft', 'cancelled', 'invoiced']}}, {'_id': 0}).sort('created_at', -1):
        if po['id'] in invoiced:
            continue
        if po.get('mirror_of') == 'production_pos':
            out.append(await _billable_preview(db, po))
        else:
            legacy = po_to_legacy_order(po)
            qty = int(legacy.get('qty_ordered', 0) or 0)
            price = float(legacy.get('price_per_pcs', 0) or 0)
            out.append({'id': po['id'], 'source': 'legacy', 'po_number': po.get('po_number'),
                        'order_code': legacy.get('order_code'), 'client_id': po.get('client_id'),
                        'client_name': po.get('client_name'), 'status': po.get('status'),
                        'ar_invoice_number': None, 'total_ordered': qty, 'total_received': qty,
                        'subtotal': round(qty * price, 2), 'line_count': 1, 'lines': [], 'billable': qty > 0})
    return out


@router.get('/invoices/{invoice_id}')
async def get_invoice(invoice_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({'id': invoice_id})
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    payments = await db.dewi_maklon_payments.find({'invoice_id': invoice_id}).sort('payment_date', -1).to_list(length=100)
    inv = _clean(inv)
    inv['payments'] = [_clean(p) for p in payments]
    return inv


@router.get('/invoices/{invoice_id}/pdf')
async def get_invoice_pdf(invoice_id: str, user: dict = Depends(require_auth)):
    """Admin-side: download invoice PDF."""
    from fastapi.responses import Response
    from utils.invoice_pdf import build_invoice_pdf
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({'id': invoice_id})
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    cl = await db.dewi_maklon_clients.find_one({'id': inv.get('client_id')}) or {}
    co = await db.company_settings.find_one({}) or {}
    # SESI #19 — kop/kolom/tanda tangan/footer invoice mengikuti TEMPLATE PDF pemilik
    # (layar "PDF & Kop Surat"). Tanpa ini invoice tetap memakai kop tanam kode
    # tanpa logo/NPWP sementara dokumen lain sudah mengikuti setelan.
    from utils.pdf_common import get_company_profile, get_doc_settings
    _ds = await get_doc_settings(db, 'invoice-maklon')
    pdf = build_invoice_pdf(invoice=inv, client=cl, company=co,
                            template=(_ds or {}).get('_template'),
                            profile=await get_company_profile(db))
    return Response(
        content=pdf,
        media_type='application/pdf',
        headers={
            'Content-Disposition': f'inline; filename="Invoice_{inv.get("invoice_number")}.pdf"',
        },
    )

@router.post('/invoices/generate')
async def generate_invoice(payload: InvoiceGenerateIn, user: dict = Depends(require_auth)):
    """Auto-generate invoice from a maklon order/PO."""
    db = get_db()
    # P1.B: lookup in dewi_maklon_pos FIRST (SSOT), fallback to dewi_maklon_orders
    rec = await find_maklon_record(db, payload.order_id)
    if not rec:
        raise HTTPException(404, 'Order tidak ditemukan')
    is_po = rec.get('_collection') == 'dewi_maklon_pos'
    if is_po and rec.get('mirror_of') == 'production_pos':
        return await _generate_from_engine_ar(db, rec, payload, user)
    # Normalize to legacy order shape for the rest of the flow
    order = po_to_legacy_order(rec) if is_po else rec
    order_id_canonical = order.get('id')

    legacy_status = order.get('status', 'draft')
    if legacy_status in ['draft', 'cancelled']:
        raise HTTPException(400, f'Order dengan status {legacy_status} tidak bisa diinvoice')

    # Check existing non-cancelled invoice for this order
    existing = await db.dewi_maklon_invoices.find_one({
        'order_id': payload.order_id,
        'status': {'$ne': 'cancelled'}
    })
    if existing:
        raise HTTPException(400, f'Order sudah memiliki invoice {existing.get("invoice_number")}')

    # Resolve configs
    prefix = await get_config_value(db, 'maklon_invoice_prefix', 'INV-MKL')
    tax_default = float(await get_config_value(db, 'maklon_tax_pct', 11.0) or 0)
    term_default = await get_config_value(db, 'maklon_payment_terms_default', 'net_30') or 'net_30'

    tax_pct = payload.tax_pct if payload.tax_pct is not None else tax_default
    term = payload.payment_terms or term_default

    issue = payload.issue_date or datetime.now(timezone.utc).strftime('%Y-%m-%d')
    try:
        issue_d = date.fromisoformat(issue)
    except ValueError:
        raise HTTPException(400, 'issue_date tidak valid (YYYY-MM-DD)')
    due_d = issue_d + timedelta(days=_payment_term_days(term))

    line = {
        'description': f"{order.get('product_name')} ({order.get('product_category', '-')})",
        'qty': int(order.get('qty_ordered', 0) or 0),
        'unit': 'pcs',
        'unit_price': float(order.get('price_per_pcs', 0) or 0),
        'line_total': round(float(order.get('price_per_pcs', 0) or 0) * int(order.get('qty_ordered', 0) or 0), 2),
    }

    invoice_number = await _next_invoice_number(db, prefix,
                                                requested=(payload.invoice_number or ''))
    now = datetime.now(timezone.utc)
    doc = {
        'id': str(uuid.uuid4()),
        'invoice_number': invoice_number,
        'order_id': order.get('id'),
        'order_code': order.get('order_code'),
        'client_id': order.get('client_id'),
        'client_name': order.get('client_name'),
        'issue_date': issue_d.isoformat(),
        'due_date': due_d.isoformat(),
        'payment_terms': term,
        'tax_pct': tax_pct,
        'discount_amount': 0.0,
        'lines': [line],
        'subtotal': line['line_total'],
        'tax_amount': 0.0,
        'total_amount': 0.0,
        'paid_amount': 0.0,
        'balance_amount': 0.0,
        'status': 'issued',
        'notes': payload.notes,
        'created_at': now,
        'updated_at': now,
        'created_by': user.get('name', 'System'),
    }
    await db.dewi_maklon_invoices.insert_one(doc)

    # Mark order as invoiced (post-P1.B cleanup: only dewi_maklon_pos exists as SSOT)
    if is_po:
        await db.dewi_maklon_pos.update_one(
            {'id': order_id_canonical},
            {'$set': {'status': 'invoiced', 'ar_invoice_id': doc['id'],
                      'ar_invoice_number': invoice_number, 'updated_at': now}}
        )

    await _recalc_invoice(db, doc['id'])
    # C-06: invoice maklon (jalur legacy) juga masuk GL — cermin dokumen invoice ini sendiri.
    from routes.dewi_maklon_finance import post_maklon_ar_invoice
    await post_maklon_ar_invoice(db, {
        'id': order_id_canonical if is_po else None, 'ar_invoice_id': doc['id'],
        'po_number': order.get('order_code'), 'client_id': order.get('client_id'),
        'client_name': order.get('client_name'), 'po_date': issue_d.isoformat()}, user)

    # Phase 4 P1: notify klien
    try:
        from routes.dewi_notifications import queue_for_client
        body = (
            f"Invoice baru {invoice_number} untuk order {order.get('order_code')} "
            f"telah diterbitkan. Total Rp {int(doc.get('total_amount') or 0):,}, "
            f"jatuh tempo {doc.get('due_date')}."
        ).replace(',', '.')
        await queue_for_client(
            db,
            client_id=order.get('client_id'),
            subject=f"Invoice baru — {invoice_number}",
            body=body,
            event_type='invoice_issued',
            source_ref=doc['id'],
            meta={'invoice_number': invoice_number, 'total': doc.get('total_amount')},
        )
    except Exception:
        logging.getLogger(__name__).debug("suppressed exception", exc_info=True)

    refreshed = await db.dewi_maklon_invoices.find_one({'id': doc['id']})
    return _clean(refreshed)

@router.put('/invoices/{invoice_id}')
async def update_invoice(invoice_id: str, payload: InvoiceUpdateIn, user: dict = Depends(require_auth)):
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({'id': invoice_id})
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    if inv.get('status') == 'paid':
        raise HTTPException(400, 'Invoice sudah lunas, tidak dapat diubah')

    update = {k: v for k, v in payload.dict(exclude_unset=True).items() if v is not None}
    if update:
        update['updated_at'] = datetime.now(timezone.utc)
        await db.dewi_maklon_invoices.update_one({'id': invoice_id}, {'$set': update})
    await _recalc_invoice(db, invoice_id)
    return {'message': 'Invoice diperbarui'}

@router.post('/invoices/{invoice_id}/cancel')
async def cancel_invoice(invoice_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({'id': invoice_id})
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    if inv.get('paid_amount', 0) > 0:
        raise HTTPException(400, 'Invoice yang sudah dibayar tidak bisa dibatalkan')
    now_ts = datetime.now(timezone.utc)
    from routes.dewi_maklon_finance import void_maklon_ar_posting
    if inv.get('ar_invoice_id'):
        ar = await db.rahaza_ar_invoices.find_one({'id': inv['ar_invoice_id']}, {'_id': 0}) or {}
        # C-06: invoice belum dibayar → jurnal penerbitan di-VOID otomatis (periode harus terbuka).
        v = await void_maklon_ar_posting(db, inv['ar_invoice_id'], inv.get('order_id'), user,
                                         reason=f'Invoice {inv.get("invoice_number")} dibatalkan')
        if not v.get('ok'):
            raise HTTPException(400, f"Jurnal GL tidak bisa di-void: {v.get('error')}")
        # AR kembali menjadi draft supaya bisa diterbitkan ulang dengan qty terbaru.
        total = float(ar.get('total_amount') or 0)
        await db.rahaza_ar_invoices.update_one({'id': inv['ar_invoice_id']}, {'$set': {
            'status': 'draft', 'amount_paid': 0.0, 'amount_due': total,
            'issued_at': None, 'issued_by': None, 'updated_at': now_ts}})
    order_id = inv.get('order_id')
    if inv.get('source') == 'engine_ar':
        # SATU SUMBER: dokumen layar hanyalah cermin AR (id & nomor SAMA). Menyimpannya sebagai
        # 'cancelled' membuat unique index invoice_number menolak penerbitan ulang (iter 105).
        # AR draft-nya tetap hidup ⇒ cukup hapus cerminnya + pembayaran (pasti 0).
        await db.dewi_maklon_payments.delete_many({'invoice_id': invoice_id})
        await db.dewi_maklon_invoices.delete_one({'id': invoice_id})
        if order_id:
            from routes.production_maklon_bridge import try_sync_maklon_finance
            await db.dewi_maklon_pos.update_one(
                {'id': order_id, 'status': 'invoiced'},
                {'$set': {'status': 'completed', 'updated_at': now_ts}})
            await try_sync_maklon_finance(db, order_id, user)
        return {'message': 'Invoice dibatalkan', 'ar_status': 'draft'}
    if not inv.get('ar_invoice_id'):
        v = await void_maklon_ar_posting(db, invoice_id, order_id, user,
                                         reason=f'Invoice {inv.get("invoice_number")} dibatalkan')
        if not v.get('ok'):
            raise HTTPException(400, f"Jurnal GL tidak bisa di-void: {v.get('error')}")
    await db.dewi_maklon_invoices.update_one(
        {'id': invoice_id},
        {'$set': {'status': 'cancelled', 'updated_at': now_ts}}
    )
    # Revert order status (best-effort) to completed on dewi_maklon_pos (SSOT)
    if order_id:
        await db.dewi_maklon_pos.update_one(
            {'id': order_id, 'status': 'invoiced'},
            {'$set': {'status': 'completed', 'updated_at': now_ts}}
        )
    return {'message': 'Invoice dibatalkan'}

# ══════════════════════════════════════════════════════════════════════════════
# PAYMENT ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.post('/payments')
async def record_payment(payload: PaymentIn, user: dict = Depends(require_auth)):
    db = get_db()
    inv = await db.dewi_maklon_invoices.find_one({'id': payload.invoice_id})
    if not inv:
        raise HTTPException(404, 'Invoice tidak ditemukan')
    if inv.get('status') == 'cancelled':
        raise HTTPException(400, 'Invoice dibatalkan')
    if payload.method not in PAYMENT_METHODS:
        raise HTTPException(400, f'Method tidak valid. Valid: {PAYMENT_METHODS}')

    # Prevent overpayment
    outstanding = float(inv.get('balance_amount', 0) or 0)
    if outstanding <= 0:
        outstanding = float(inv.get('total_amount', 0) or 0) - float(inv.get('paid_amount', 0) or 0)
    if payload.amount > outstanding + 0.01:
        raise HTTPException(400, f'Pembayaran melebihi saldo tagihan (Rp {outstanding:,.0f})')

    now = datetime.now(timezone.utc)
    pay_date = payload.payment_date or now.strftime('%Y-%m-%d')
    doc = {
        'id': str(uuid.uuid4()),
        'invoice_id': payload.invoice_id,
        'invoice_number': inv.get('invoice_number'),
        'client_id': inv.get('client_id'),
        'client_name': inv.get('client_name'),
        'amount': float(payload.amount),
        'method': payload.method,
        'reference_no': payload.reference_no,
        'payment_date': pay_date,
        'notes': payload.notes,
        'cash_account_id': payload.cash_account_id,
        'created_at': now,
        'created_by': user.get('name', 'System'),
    }
    if payload.cash_account_id and not await db.rahaza_cash_accounts.find_one({'id': payload.cash_account_id}, {'_id': 1}):
        raise HTTPException(400, 'Rekening kas/bank tidak ditemukan')
    await db.dewi_maklon_payments.insert_one(doc)
    await _recalc_invoice(db, payload.invoice_id)
    # C-06: penerimaan kas maklon → Dr Bank / Cr AR (akun AR yang sama dgn jurnal penerbitan).
    from routes.dewi_maklon_finance import post_maklon_payment
    gl = await post_maklon_payment(db, inv, doc, user)
    return {'message': 'Pembayaran dicatat', 'id': doc['id'],
            'gl_je_number': gl.get('je_number'), 'gl_error': gl.get('error')}

@router.get('/payments')
async def list_payments(
    invoice_id: Optional[str] = None,
    client_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    db = get_db()
    query = {}
    if invoice_id:
        query['invoice_id'] = invoice_id
    if client_id:
        query['client_id'] = client_id
    items = await db.dewi_maklon_payments.find(query).sort('payment_date', -1).to_list(length=500)
    return [_clean(p) for p in items]

@router.delete('/payments/{payment_id}')
async def delete_payment(payment_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    pay = await db.dewi_maklon_payments.find_one({'id': payment_id})
    if not pay:
        raise HTTPException(404, 'Payment tidak ditemukan')
    from routes.dewi_maklon_finance import void_maklon_payment
    v = await void_maklon_payment(db, pay, user, reason='Pembayaran maklon dihapus')
    if not v.get('ok'):
        raise HTTPException(400, f"Jurnal GL tidak bisa di-void: {v.get('error')}")
    await db.dewi_maklon_payments.delete_one({'id': payment_id})
    await _recalc_invoice(db, pay['invoice_id'])
    return {'message': 'Payment dihapus'}

# ══════════════════════════════════════════════════════════════════════════════
# HPP ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/hpp/{order_id}')
async def get_hpp(order_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    hpp = await db.dewi_maklon_hpp.find_one({'order_id': order_id})
    if not hpp:
        raise HTTPException(404, 'HPP belum diinput untuk order ini')
    return _clean(hpp)

@router.post('/hpp')
async def upsert_hpp(payload: HPPIn, user: dict = Depends(require_auth)):
    """Create or update HPP for an order."""
    db = get_db()
    # P1.B: SSOT is dewi_maklon_pos, fallback to legacy
    rec = await find_maklon_record(db, payload.order_id)
    if not rec:
        raise HTTPException(404, 'Order tidak ditemukan')

    # Normalize record shape (PO or legacy) to legacy-order view
    is_po = rec.get('_collection') == 'dewi_maklon_pos'
    order = po_to_legacy_order(rec) if is_po else rec

    overhead_default = float(await get_config_value(db, 'hpp_overhead_pct', 15.0) or 0)
    profit_default = float(await get_config_value(db, 'hpp_profit_margin_pct', 20.0) or 0)
    overhead_pct = payload.overhead_pct if payload.overhead_pct is not None else overhead_default
    profit_pct = payload.profit_margin_pct if payload.profit_margin_pct is not None else profit_default

    components = []
    for c in payload.components:
        cd = c.dict()
        cd['total'] = round(float(cd.get('qty', 0) or 0) * float(cd.get('unit_cost', 0) or 0), 2)
        components.append(cd)

    direct_cost = sum(c['total'] for c in components)
    overhead_amount = round(direct_cost * overhead_pct / 100, 2)
    qty_ordered = int(order.get('qty_ordered', 0) or 0) or 1
    total_hpp = round(direct_cost + overhead_amount, 2)
    hpp_per_pcs = round(total_hpp / qty_ordered, 2)
    suggested_price = round(hpp_per_pcs * (1 + profit_pct / 100), 2)
    current_price = float(order.get('price_per_pcs', 0) or 0)
    actual_margin_pct = round(((current_price - hpp_per_pcs) / hpp_per_pcs) * 100, 2) if hpp_per_pcs > 0 else 0

    now = datetime.now(timezone.utc)
    doc = {
        'order_id': payload.order_id,
        'order_code': order.get('order_code'),
        'client_id': order.get('client_id'),
        'client_name': order.get('client_name'),
        'qty_ordered': qty_ordered,
        'components': components,
        'direct_cost': round(direct_cost, 2),
        'overhead_pct': overhead_pct,
        'overhead_amount': overhead_amount,
        'profit_margin_pct': profit_pct,
        'total_hpp': total_hpp,
        'hpp_per_pcs': hpp_per_pcs,
        'suggested_price_per_pcs': suggested_price,
        'current_price_per_pcs': current_price,
        'actual_margin_pct': actual_margin_pct,
        'notes': payload.notes,
        'updated_at': now,
        'updated_by': user.get('name', 'System'),
    }
    existing = await db.dewi_maklon_hpp.find_one({'order_id': payload.order_id})
    if existing:
        await db.dewi_maklon_hpp.update_one({'order_id': payload.order_id}, {'$set': doc})
        hpp_id = existing.get('id')
    else:
        doc['id'] = str(uuid.uuid4())
        doc['created_at'] = now
        doc['created_by'] = user.get('name', 'System')
        await db.dewi_maklon_hpp.insert_one(doc)
        hpp_id = doc['id']
    return {'message': 'HPP tersimpan', 'id': hpp_id, 'hpp_per_pcs': hpp_per_pcs, 'actual_margin_pct': actual_margin_pct}

# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/reports/billing-summary')
async def billing_summary(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    client_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """Aggregate billing numbers (revenue, outstanding, overdue)."""
    db = get_db()
    query = {'status': {'$ne': 'cancelled'}}
    if client_id:
        query['client_id'] = client_id
    if from_date or to_date:
        rng = {}
        if from_date:
            rng['$gte'] = from_date
        if to_date:
            rng['$lte'] = to_date
        query['issue_date'] = rng

    invoices = await db.dewi_maklon_invoices.find(query).to_list(length=2000)
    total_invoices = len(invoices)
    total_billed = round(sum(float(i.get('total_amount', 0) or 0) for i in invoices), 2)
    total_paid = round(sum(float(i.get('paid_amount', 0) or 0) for i in invoices), 2)
    total_outstanding = round(total_billed - total_paid, 2)

    # Overdue
    #
    # 2026-08-07 — dua cacat di blok ini:
    #   1. invoice yang `due_date`-nya rusak di-`continue` DIAM-DIAM ⇒ hilang dari
    #      hitungan jatuh tempo; total tampak wajar dan tak ada yang menagih.
    #   2. `except ValueError` TIDAK menangkap `TypeError`. Bila `due_date` bernilai
    #      None (key ada, isinya null — bentuk yang nyata di data lama),
    #      `date.fromisoformat(None)` melempar TypeError ⇒ endpoint 500, BUKAN
    #      "cuma satu baris dilewati". Ekspektasinya diperlebar.
    today = datetime.now(timezone.utc).date()
    dq = SkipTracker("ringkasan tagihan maklon (jatuh tempo)")
    overdue_amount = 0.0
    overdue_count = 0
    for i in invoices:
        try:
            d = date.fromisoformat(i.get('due_date') or '2099-12-31')
        except (ValueError, TypeError) as e:
            dq.skip(doc_id=i.get('id'), label=i.get('invoice_number'),
                    field='due_date', value=i.get('due_date'), error=e)
            continue
        if d < today and i.get('status') in ('issued', 'partial_paid', 'overdue'):
            overdue_count += 1
            overdue_amount += float(i.get('balance_amount', 0) or 0)
    overdue_amount = round(overdue_amount, 2)
    dq.log(logger)

    # By status breakdown
    by_status = {}
    for s in INVOICE_STATUSES:
        by_status[s] = {
            'count': len([i for i in invoices if i.get('status') == s]),
            'amount': round(sum(float(i.get('total_amount', 0) or 0) for i in invoices if i.get('status') == s), 2),
        }

    return {
        'total_invoices': total_invoices,
        'total_billed': total_billed,
        'total_paid': total_paid,
        'total_outstanding': total_outstanding,
        'overdue_count': overdue_count,
        'overdue_amount': overdue_amount,
        'by_status': by_status,
    }

@router.get('/reports/monthly-billing')
async def monthly_billing(
    year: Optional[int] = None,
    client_id: Optional[str] = None,
    user: dict = Depends(require_auth)
):
    """Monthly billing aggregation per client."""
    db = get_db()
    target_year = year or datetime.now(timezone.utc).year
    query = {
        'status': {'$ne': 'cancelled'},
        'issue_date': {'$gte': f'{target_year}-01-01', '$lte': f'{target_year}-12-31'},
    }
    if client_id:
        query['client_id'] = client_id

    invoices = await db.dewi_maklon_invoices.find(query).to_list(length=5000)

    # Bucket by month & client
    buckets: Dict[str, Dict[str, Any]] = {}
    for i in invoices:
        issue = i.get('issue_date', '')
        month_key = issue[:7] if len(issue) >= 7 else 'unknown'
        cid = i.get('client_id', 'unknown')
        key = f'{month_key}|{cid}'
        if key not in buckets:
            buckets[key] = {
                'month': month_key,
                'client_id': cid,
                'client_name': i.get('client_name'),
                'invoices_count': 0,
                'total_billed': 0.0,
                'total_paid': 0.0,
                'total_outstanding': 0.0,
            }
        b = buckets[key]
        b['invoices_count'] += 1
        b['total_billed'] += float(i.get('total_amount', 0) or 0)
        b['total_paid'] += float(i.get('paid_amount', 0) or 0)
        b['total_outstanding'] += float(i.get('balance_amount', 0) or 0)

    # Round
    rows = []
    for b in buckets.values():
        rows.append({
            **b,
            'total_billed': round(b['total_billed'], 2),
            'total_paid': round(b['total_paid'], 2),
            'total_outstanding': round(b['total_outstanding'], 2),
        })
    rows.sort(key=lambda x: (x['month'], x.get('client_name') or ''))
    return {'year': target_year, 'rows': rows}

@router.get('/reports/aging')
async def aging_report(user: dict = Depends(require_auth)):
    """Aging tagihan maklon — membaca sumber yang SAMA dgn /api/rahaza/ar-aging (H-01), filter source=maklon."""
    db = get_db()
    from routes.rahaza_ar_canonical import compute_ar_aging
    res = await compute_ar_aging(db, source='maklon')
    b = res['buckets']
    buckets = {'current': b['current'], '1_30': b['1_30'], '31_60': b['31_60'], '61_90': b['61_90'],
               'over_90': b['90_plus'], 'tanpa_jatuh_tempo': b['tanpa_jatuh_tempo']}
    rows = [{'invoice_number': r.get('invoice_number'), 'client_name': r.get('client_name'),
             'issue_date': r.get('invoice_date') or r.get('issue_date'), 'due_date': r.get('due_date'),
             'total_amount': r['total_amount'], 'balance_amount': r['amount_due'], 'status': r['status'],
             'days_overdue': r['days_overdue'], 'bucket': 'over_90' if r['bucket'] == '90_plus' else r['bucket'],
             'due_date_valid': r['due_date_valid']} for r in res['rows']]
    return {'buckets': buckets, 'rows': rows, 'total': res['total'], 'data_quality': res['data_quality']}
