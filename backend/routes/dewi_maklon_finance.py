"""
CV. Dewi Aditya — Finance Integration untuk Maklon
Phase Production-Maklon Overhaul — Phase 4

Menutup gap kritis: Maklon Billing harus masuk Finance GL.

Fungsi:
  post_maklon_ar_invoice(db, po, user)    → Dr AR / Cr Pendapatan Jasa Maklon
  post_cmt_ap_invoice(db, payment, user)  → Dr Biaya CMT / Cr AP Vendor
  post_maklon_ar_payment(db, invoice, movement, user) → Dr Bank / Cr AR

Endpoints:
  POST /api/dewi/maklon/pos/{po_id}/post-ar      → Manual trigger post AR
  POST /api/dewi/maklon/pos/{po_id}/advance-payment → Input DP klien
  POST /api/dewi/cmt/payments/{payment_id}/post-ap   → Post CMT AP ke GL
"""
from fastapi import APIRouter, HTTPException, Depends
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, date
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_posting import _create_posted_je, _find_existing_je
from routes.rahaza_posting_profiles import get_mapping
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/dewi/maklon/finance', tags=['Dewi-Maklon-Finance'], dependencies=[Depends(deny_external_dep)])
def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# POSTING HELPERS (shared functions)
# ──────────────────────────────────────────────────────────────────────────────

async def post_maklon_ar_invoice(db, po: dict, user: dict) -> dict:
    """
    Post AR Invoice untuk Maklon PO ke Finance GL.
    Dr Piutang Usaha (AR) / Cr Pendapatan Jasa Maklon (+ Cr PPN Keluaran)
    - Nilai & tanggal = dokumen AR final (bukan nilai order / po_date).
    - Idempoten; bila JE lama ada tetapi nilainya berbeda (mis. post-ar manual saat
      draft lalu invoice di-generate) → JE lama di-void, diposting ulang (C-06c/H-09).
    """
    po_id = po.get('id')
    ar_invoice_id = po.get('ar_invoice_id')
    if not ar_invoice_id:
        return {'ok': False, 'error': 'PO belum punya AR Invoice. Confirm dulu.'}

    ar_doc = (await db.rahaza_ar_invoices.find_one({'id': ar_invoice_id}, {'_id': 0})
              or await db.dewi_maklon_invoices.find_one({'id': ar_invoice_id}, {'_id': 0}) or {})
    if (ar_doc.get('status') or 'draft') == 'draft':
        return {'ok': False, 'error': 'AR maklon masih draft — generate invoice dulu sebelum posting ke GL.'}
    total = round(float(ar_doc.get('total_amount') if ar_doc.get('total_amount') is not None else po.get('total_value', 0) or 0), 2)
    tax_amount = round(float(ar_doc.get('tax_amount') or 0), 2)
    revenue_amount = round(total - tax_amount, 2)
    if total <= 0:
        return {'ok': False, 'error': 'Nilai AR maklon 0 — tidak ada yang diposting.'}

    source_ref = f'maklon_ar:{ar_invoice_id}'
    existing = await _find_existing_je(db, 'maklon_ar_invoice', source_ref)
    if existing:
        if abs(float(existing.get('total_debit') or 0) - total) < 0.01:
            return {'ok': True, 'je_id': existing['id'], 'je_number': existing.get('je_number'), 'already_posted': True}
        from routes.rahaza_posting import _void_je_by_source
        v = await _void_je_by_source(db, 'maklon_ar_invoice', source_ref, user,
                                     reason=f'Nilai AR berubah {existing.get("total_debit")} → {total}; posting ulang')
        if not v.get('ok'):
            return {'ok': False, 'error': v.get('error')}

    mapping = await get_mapping(db, 'maklon_ar_invoice') or await get_mapping(db, 'ar_invoice')
    ar_code = mapping.get('debit_ar')
    rev_code = mapping.get('credit_revenue_maklon') or mapping.get('credit_revenue')
    tax_code = mapping.get('credit_tax_output')
    if not ar_code or not rev_code or (tax_amount > 0 and not tax_code):
        return {'ok': False, 'error': "Mapping 'maklon_ar_invoice' belum lengkap (debit_ar/credit_revenue_maklon/credit_tax_output)."}
    from routes.rahaza_posting import _resolve_ar_code
    ar_code = await _resolve_ar_code(db, ar_code, po.get('client_id') or ar_doc.get('customer_id'), None, user)

    lines = [
        {
            'account_code': ar_code,
            'debit': total,
            'credit': 0,
            'description': f'AR Jasa Maklon — {po.get("po_number","")} — {po.get("client_name","")}',
        },
        {
            'account_code': rev_code,
            'debit': 0,
            'credit': revenue_amount,
            'description': f'Pendapatan Jasa Maklon — {po.get("po_number","")}',
        },
    ]
    if tax_amount > 0:
        lines.append({
            'account_code': tax_code,
            'debit': 0,
            'credit': tax_amount,
            'description': f'PPN Keluaran — {po.get("po_number","")}',
        })

    je_date_s = (ar_doc.get('invoice_date') or ar_doc.get('issue_date') or po.get('po_date') or date.today().isoformat())
    try:
        je_date = date.fromisoformat(str(je_date_s)[:10])
    except ValueError:
        je_date = date.today()
    result = await _create_posted_je(
        db,
        je_date=je_date,
        memo=f'AR Jasa Maklon — {po.get("po_number","")} — {po.get("client_name","")}',
        source_module='maklon_ar_invoice',
        source_ref=source_ref,
        lines_raw=lines,
        user=user,
    )
    # Save result to AR Invoice
    if result.get('ok'):
        gl_set = {'gl_posted_at': _now(), 'gl_je_id': result['je_id'], 'gl_je_number': result['je_number'],
                  'gl_ar_account_code': ar_code, 'post_error': None}
        await db.rahaza_ar_invoices.update_one({'id': ar_invoice_id}, {'$set': gl_set})
        await db.dewi_maklon_invoices.update_one({'id': ar_invoice_id}, {'$set': gl_set})
        await db.dewi_maklon_pos.update_one(
            {'id': po_id},
            {'$set': {
                'gl_posted_at': _now(),
                'gl_je_id': result['je_id'],
                'gl_je_number': result.get('je_number'),
                'post_error': None,
            }}
        )
    else:
        await db.dewi_maklon_pos.update_one(
            {'id': po_id},
            {'$set': {'post_error': result.get('error'), 'post_error_at': _now()}}
        )
        await db.rahaza_ar_invoices.update_one(
            {'id': ar_invoice_id}, {'$set': {'post_error': result.get('error'), 'post_error_at': _now()}})
    return result


async def void_maklon_ar_posting(db, ar_invoice_id: str, po_id: str, user: dict, reason: str = '') -> dict:
    """Void jurnal penerbitan AR maklon (saat invoice dibatalkan) + bersihkan jejak GL."""
    from routes.rahaza_posting import _void_je_by_source
    res = await _void_je_by_source(db, 'maklon_ar_invoice', f'maklon_ar:{ar_invoice_id}', user, reason)
    if res.get('ok'):
        clear = {'gl_posted_at': None, 'gl_je_id': None, 'gl_je_number': None, 'post_error': None}
        await db.rahaza_ar_invoices.update_one({'id': ar_invoice_id}, {'$set': clear})
        if po_id:
            await db.dewi_maklon_pos.update_one({'id': po_id}, {'$set': clear})
    return res


async def post_maklon_payment(db, invoice: dict, payment: dict, user: dict) -> dict:
    """Pembayaran invoice maklon → Dr Bank / Cr AR (akun AR = jurnal penerbitan) + rahaza_cash_movements."""
    from routes.rahaza_posting import post_ar_payment
    ar_id = invoice.get('ar_invoice_id') or invoice.get('id')
    ar_doc = await db.rahaza_ar_invoices.find_one({'id': ar_id}, {'_id': 0}) or {}
    pseudo = {
        'id': ar_id,
        'invoice_number': invoice.get('invoice_number'),
        'customer_name': invoice.get('client_name'),
        'gl_ar_account_code': ar_doc.get('gl_ar_account_code') or invoice.get('gl_ar_account_code'),
    }
    if not pseudo['gl_ar_account_code']:
        mapping = await get_mapping(db, 'maklon_ar_invoice') or {}
        pseudo['gl_ar_account_code'] = mapping.get('debit_ar')
    cash_account_id = payment.get('cash_account_id')
    if cash_account_id:
        acc = await db.rahaza_cash_accounts.find_one({'id': cash_account_id}, {'_id': 0})
        if acc and not await db.rahaza_cash_movements.find_one({'id': payment['id']}, {'_id': 1}):
            await db.rahaza_cash_movements.insert_one({
                'id': payment['id'], 'account_id': cash_account_id, 'account_name': acc.get('name'),
                'direction': 'in', 'amount': round(float(payment['amount'])),
                'category': 'ar_payment', 'ref_id': ar_id, 'ref_label': invoice.get('invoice_number'),
                'source_module': 'maklon_payment',
                'date': payment.get('payment_date'), 'notes': payment.get('notes') or '',
                'timestamp': _now(), 'created_by': user.get('id'), 'created_by_name': user.get('name', ''),
            })
            await db.rahaza_cash_accounts.update_one({'id': cash_account_id},
                                                     {'$inc': {'balance': round(float(payment['amount']))}})
    result = await post_ar_payment(db, pseudo, float(payment['amount']), cash_account_id,
                                   payment.get('payment_date'), user, movement_id=payment['id'])
    upd = ({'gl_je_id': result.get('je_id'), 'gl_je_number': result.get('je_number'), 'post_error': None}
           if result.get('ok') else {'post_error': result.get('error'), 'post_error_at': _now()})
    await db.dewi_maklon_payments.update_one({'id': payment['id']}, {'$set': upd})
    return result


async def void_maklon_payment(db, payment: dict, user: dict, reason: str = '') -> dict:
    from routes.rahaza_posting import _void_je_by_source
    source_ref = f"arpay:{payment['id']}:{int(round(float(payment.get('amount') or 0)))}"
    res = await _void_je_by_source(db, 'ar_payment', source_ref, user, reason)
    mv = await db.rahaza_cash_movements.find_one({'id': payment['id']}, {'_id': 0})
    if mv:
        await db.rahaza_cash_movements.delete_one({'id': payment['id']})
        await db.rahaza_cash_accounts.update_one({'id': mv.get('account_id')},
                                                 {'$inc': {'balance': -float(mv.get('amount') or 0)}})
    return res


async def _cmt_expense_account(db, cmt_payment: dict, mapping: dict) -> tuple:
    """(account_code, domain) akun BIAYA untuk tagihan jasa jahit CMT.

    FASE IA-C (2026-07-26) — BUG AKUNTANSI NYATA: profil bawaan `cmt_ap_invoice`
    memakai `debit_cmt_expense = '6-2200'` dengan komentar "# Biaya Jasa CMT",
    padahal di CoA yang benar-benar ter-seed **6-2200 = "Listrik & Air Kantor"**.
    Akibatnya SETIAP tagihan jasa jahit yang diposting (termasuk lewat pintu Invoice
    Produksi yang baru) menambah beban Listrik & Air — HPP produksi kurang saji dan
    laporan biaya operasional membengkak tanpa sebab.

    Perbaikan sekaligus memenuhi arahan owner #7 (data internal & maklon terpisah):
      · PO internal → `5-231 Biaya Vendor CMT – Jahit` (COGS produksi DA sendiri)
      · PO maklon   → `7-120 Biaya Vendor CMT – Maklon` (biaya proyek maklon)
    Keduanya bisa ditimpa lewat Master Akuntansi (kunci `debit_cmt_expense_internal`
    / `debit_cmt_expense_maklon`), dan tetap jatuh ke `debit_cmt_expense` lama bila
    profil kustom pengguna hanya punya kunci itu.
    """
    domain = 'maklon'
    po_id = cmt_payment.get('po_id')
    if po_id:
        po = await db.production_pos.find_one({'id': po_id}, {'_id': 0, 'business_type': 1})
        if (po or {}).get('business_type') == 'internal':
            domain = 'internal'
    elif cmt_payment.get('job_ids'):
        domain = 'internal'   # CMT-flow: DA menjahitkan produk DA sendiri
    if domain == 'internal':
        # C-03: absorption — upah jahit produk DA sendiri → WIP (1-1403), keluar ke FG saat job selesai
        code = mapping.get('debit_cmt_wip_internal') or mapping.get('debit_cmt_expense_internal') or mapping.get('debit_cmt_expense')
    else:
        code = mapping.get('debit_cmt_expense_maklon') or mapping.get('debit_cmt_expense')
    if code == '6-2200':   # profil lama yang keliru (Listrik & Air Kantor) → ditolak, bukan ditebak
        code = None
    return code, domain


async def post_cmt_ap_invoice(db, cmt_payment: dict, user: dict) -> dict:
    """
    Post AP Invoice untuk CMT Payment ke Finance GL.
    Dr Biaya Vendor CMT (COGS internal / biaya maklon) / Cr Hutang Usaha (AP Vendor)
    """
    payment_id = cmt_payment.get('id')
    source_ref = f'cmt_ap:{payment_id}'
    existing = await _find_existing_je(db, 'cmt_ap_invoice', source_ref)
    if existing:
        return {'ok': True, 'je_id': existing['id'], 'je_number': existing.get('je_number'), 'already_posted': True}

    mapping = await get_mapping(db, 'cmt_ap_invoice')
    if not mapping:
        # Fallback
        mapping = await get_mapping(db, 'ap_invoice')
    if not mapping:
        return {'ok': False, 'error': 'Posting profile cmt_ap_invoice tidak ditemukan'}

    total = float(cmt_payment.get('subtotal', 0))
    if total <= 0:
        return {'ok': False, 'error': 'Total CMT payment = 0, tidak bisa di-post'}

    # Phase 5: per-vendor AP subledger. Resolve akun AP milik vendor CMT ini;
    # fallback ke akun kontrol (mapping credit_ap / 2-1100) bila fitur mati/gagal.
    ap_code = mapping.get('credit_ap')
    if not ap_code:
        return {'ok': False, 'error': "Mapping 'cmt_ap_invoice.credit_ap' belum diisi."}
    try:
        from routes.coa_auto import resolve_ap_account_for_cmt
        resolved = await resolve_ap_account_for_cmt(
            db, cmt_payment.get('cmt_partner_id'), cmt_payment.get('cmt_name'), user
        )
        if resolved:
            ap_code = resolved
    except Exception as _e:
        logger.warning(f'[cmt_ap] resolve subledger gagal, pakai kontrol: {_e}')

    expense_code, expense_domain = await _cmt_expense_account(db, cmt_payment, mapping)
    if not expense_code:
        return {'ok': False, 'error': "Mapping 'cmt_ap_invoice.debit_cmt_expense_internal/maklon' belum diisi."}

    lines = [
        {
            'account_code': expense_code,
            'debit': total,
            'credit': 0,
            'description': f'Biaya Jasa CMT {expense_domain} — {cmt_payment.get("cmt_name","")} — '
                           f'{cmt_payment.get("payment_code") or cmt_payment.get("payment_number","")}',
        },
        {
            'account_code': ap_code,
            'debit': 0,
            'credit': total,
            'description': f'AP CMT Vendor — {cmt_payment.get("cmt_name","")}',
        },
    ]

    # Penalty reduction
    penalty = float(cmt_payment.get('total_penalty', 0))
    if penalty > 0:
        if not mapping.get('debit_penalty_income'):
            return {'ok': False, 'error': "Mapping 'cmt_ap_invoice.debit_penalty_income' belum diisi."}
        lines[1]['credit'] = round(total - penalty, 2)
        lines.append({
            'account_code': mapping.get('debit_penalty_income'),
            'debit': 0,
            'credit': penalty,
            'description': f'Penalti keterlambatan CMT — {cmt_payment.get("cmt_name","")}',
        })

    je_date = date.fromisoformat(cmt_payment.get('payment_date') or date.today().isoformat())
    result = await _create_posted_je(
        db,
        je_date=je_date,
        memo=f'Biaya CMT — {cmt_payment.get("cmt_name","")} — '
             f'{cmt_payment.get("payment_code") or cmt_payment.get("payment_number","")}',
        source_module='cmt_ap_invoice',
        source_ref=source_ref,
        lines_raw=lines,
        user=user,
    )
    if result.get('ok'):
        await db.dewi_cmt_payments.update_one(
            {'id': payment_id},
            {'$set': {
                'gl_posted_at': _now(),
                'gl_je_id': result['je_id'],
                'gl_je_number': result.get('je_number'),
                'gl_ap_account_code': ap_code,
                'post_error': None,
            }}
        )
    else:
        await db.dewi_cmt_payments.update_one(
            {'id': payment_id},
            {'$set': {'post_error': result.get('error'), 'post_error_at': _now()}}
        )
    return result


# ──────────────────────────────────────────────────────────────────────────────
# API ENDPOINTS
# ──────────────────────────────────────────────────────────────────────────────

@router.post('/pos/{po_id}/post-ar')
async def post_ar_for_po(po_id: str, user: dict = Depends(require_auth)):
    """Trigger manual post AR Invoice ke Finance GL untuk Maklon PO."""
    db = get_db()
    po = await db.dewi_maklon_pos.find_one({'id': po_id})
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')
    if po.get('status') == 'draft':
        raise HTTPException(400, 'PO harus di-confirm dulu sebelum post ke Finance')

    result = await post_maklon_ar_invoice(db, po, user)
    if not result.get('ok'):
        raise HTTPException(400, result.get('error', 'Posting gagal'))
    return {
        'status': 'posted',
        'je_id': result.get('je_id'),
        'je_number': result.get('je_number'),
        'already_posted': result.get('already_posted', False),
    }


class AdvancePaymentIn(BaseModel):
    amount: float = Field(..., gt=0)
    payment_date: Optional[str] = None
    notes: Optional[str] = None
    bank_account: Optional[str] = None


@router.post('/pos/{po_id}/advance-payment')
async def record_advance_payment(po_id: str, payload: AdvancePaymentIn, user: dict = Depends(require_auth)):
    """Input DP/Uang Muka dari klien maklon."""
    db = get_db()
    po = await db.dewi_maklon_pos.find_one({'id': po_id})
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')

    payment_date = payload.payment_date or date.today().isoformat()

    # Finance GL: Dr Bank / Cr Uang Muka Diterima – Maklon (profil 'maklon_advance_payment';
    # tanpa fallback kode akun — mapping tidak lengkap = ditolak dgn pesan jelas).
    mapping = await get_mapping(db, 'maklon_advance_payment') or {}
    debit_acc = mapping.get('debit_cash_default')
    credit_acc = mapping.get('credit_advance_customer')
    if payload.bank_account:
        cash_acc = await db.rahaza_cash_accounts.find_one(
            {'$or': [{'id': payload.bank_account}, {'gl_account_code': payload.bank_account}]}, {'_id': 0})
        if cash_acc and cash_acc.get('gl_account_code'):
            debit_acc = cash_acc['gl_account_code']
    if not debit_acc or not credit_acc:
        raise HTTPException(400, "Posting profile 'maklon_advance_payment' belum lengkap (debit_cash_default/credit_advance_customer).")

    dp_id = _uid()
    lines = [
        {
            'account_code': debit_acc,
            'debit': payload.amount,
            'credit': 0,
            'description': f'DP Maklon — {po.get("po_number","")} — {po.get("client_name","")}',
        },
        {
            'account_code': credit_acc,  # Uang Muka Diterima – Maklon (postable)
            'debit': 0,
            'credit': payload.amount,
            'description': f'Uang Muka Klien Maklon — {po.get("po_number","")}',
        },
    ]
    je_date = date.fromisoformat(payment_date)
    je_result = await _create_posted_je(
        db,
        je_date=je_date,
        memo=f'DP Maklon — {po.get("po_number","")} — {po.get("client_name","")}',
        source_module='maklon_advance_payment',
        source_ref=f'dp:{po_id}:{dp_id}',
        lines_raw=lines,
        user=user,
    )

    # Update PO advance payment
    await db.dewi_maklon_pos.update_one(
        {'id': po_id},
        {'$inc': {'advance_payment': payload.amount}, '$set': {'updated_at': _now()}}
    )

    # Save DP record
    dp_doc = {
        'id': _uid(),
        'po_id': po_id,
        'po_number': po['po_number'],
        'client_id': po['client_id'],
        'client_name': po['client_name'],
        'amount': payload.amount,
        'payment_date': payment_date,
        'notes': payload.notes or '',
        'bank_account': payload.bank_account or '',
        'gl_je_id': je_result.get('je_id'),
        'gl_je_number': je_result.get('je_number'),
        'post_error': je_result.get('error') if not je_result.get('ok') else None,
        'created_at': _now(),
        'created_by': user.get('id'),
    }
    await db.dewi_maklon_advance_payments.insert_one(dp_doc)
    await log_activity(user.get('id', ''), user.get('name', ''), 'advance_payment', 'dewi_maklon_advance_payments',
                       f'DP Maklon {po.get("po_number")} — Rp {payload.amount:,.0f}')
    return serialize_doc(dp_doc)


@router.post('/cmt-payments/{payment_id}/post-ap')
async def post_ap_for_cmt_payment(payment_id: str, user: dict = Depends(require_auth)):
    """Post AP Invoice untuk pembayaran CMT Vendor ke Finance GL."""
    db = get_db()
    payment = await db.dewi_cmt_payments.find_one({'id': payment_id})
    if not payment:
        raise HTTPException(404, 'CMT Payment tidak ditemukan')

    result = await post_cmt_ap_invoice(db, payment, user)
    if not result.get('ok'):
        raise HTTPException(400, result.get('error', 'Posting gagal'))
    return {
        'status': 'posted',
        'je_id': result.get('je_id'),
        'je_number': result.get('je_number'),
        'already_posted': result.get('already_posted', False),
    }


# ──────────────────────────────────────────────────────────────────────────────
# H-03: PEMBAYARAN TAGIHAN CMT (Dr AP vendor CMT — akun sama dgn AP invoice / Cr Bank)
# ──────────────────────────────────────────────────────────────────────────────
class CmtPayIn(BaseModel):
    cash_account_id: str
    amount: Optional[float] = Field(default=None, gt=0)
    payment_date: Optional[str] = None
    reference_no: Optional[str] = None
    notes: Optional[str] = None


def _cmt_amount(p: dict) -> float:
    return float(p.get('net_amount') if p.get('net_amount') is not None else p.get('total_amount') or p.get('subtotal') or 0)


@router.get('/cmt-payments/{payment_id}/disbursements')
async def list_cmt_disbursements(payment_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    rows = await db.dewi_cmt_disbursements.find({'payment_id': payment_id, 'status': {'$ne': 'voided'}}, {'_id': 0}).sort('payment_date', -1).to_list(200)
    return serialize_doc(rows)


@router.post('/cmt-payments/{payment_id}/pay')
async def pay_cmt_payment(payment_id: str, payload: CmtPayIn, user: dict = Depends(require_auth)):
    """Bayar tagihan CMT dari rekening kas/bank. AP CMT diposting dulu bila belum; jurnal bayar otomatis."""
    db = get_db()
    payment = await db.dewi_cmt_payments.find_one({'id': payment_id}, {'_id': 0})
    if not payment:
        raise HTTPException(404, 'Tagihan CMT tidak ditemukan')
    if payment.get('status') in ('cancelled', 'void'):
        raise HTTPException(400, f"Tagihan berstatus {payment.get('status')} tidak bisa dibayar")
    acc = await db.rahaza_cash_accounts.find_one({'id': payload.cash_account_id}, {'_id': 0})
    if not acc:
        raise HTTPException(400, 'Rekening kas/bank tidak ditemukan')
    total = _cmt_amount(payment)
    paid_before = float(payment.get('paid_amount') or 0)
    outstanding = round(total - paid_before, 2)
    amount = float(payload.amount) if payload.amount else outstanding
    if outstanding <= 0:
        raise HTTPException(400, 'Tagihan sudah lunas')
    if amount > outstanding + 0.01:
        raise HTTPException(400, f'Pembayaran melebihi sisa tagihan (Rp {outstanding:,.0f})')
    if not payment.get('gl_je_id'):
        ap = await post_cmt_ap_invoice(db, payment, user)
        if not ap.get('ok'):
            raise HTTPException(400, f"AP CMT belum bisa diposting ke GL: {ap.get('error')}")
        payment = await db.dewi_cmt_payments.find_one({'id': payment_id}, {'_id': 0})
    pay_date = payload.payment_date or date.today().isoformat()
    did = _uid()
    await db.rahaza_cash_movements.insert_one({
        'id': did, 'account_id': acc['id'], 'account_name': acc.get('name'), 'direction': 'out', 'amount': round(amount),
        'category': 'ap_payment', 'ref_id': payment_id, 'ref_label': payment.get('payment_code'),
        'source_module': 'cmt_payment', 'date': pay_date, 'notes': payload.notes or '',
        'timestamp': _now(), 'created_by': user.get('id'), 'created_by_name': user.get('name', ''),
    })
    await db.rahaza_cash_accounts.update_one({'id': acc['id']}, {'$inc': {'balance': -round(amount)}})
    from routes.rahaza_posting import post_ap_payment
    pseudo = {'id': payment_id, 'invoice_number': payment.get('payment_code'), 'vendor_name': payment.get('cmt_name'),
              'gl_ap_account_code': payment.get('gl_ap_account_code')}
    gl = await post_ap_payment(db, pseudo, amount, acc['id'], pay_date, user, movement_id=did)
    paid_after = round(paid_before + amount, 2)
    status = 'paid' if paid_after >= total - 0.01 else 'partial_paid'
    doc = {'id': did, 'payment_id': payment_id, 'payment_code': payment.get('payment_code'), 'cmt_name': payment.get('cmt_name'),
           'amount': amount, 'payment_date': pay_date, 'cash_account_id': acc['id'], 'cash_account_name': acc.get('name'),
           'reference_no': payload.reference_no or '', 'notes': payload.notes or '', 'status': 'posted',
           'gl_je_id': gl.get('je_id'), 'gl_je_number': gl.get('je_number'), 'post_error': gl.get('error'),
           'created_at': _now(), 'created_by': user.get('id'), 'created_by_name': user.get('name', '')}
    await db.dewi_cmt_disbursements.insert_one(dict(doc))
    await db.dewi_cmt_payments.update_one({'id': payment_id}, {'$set': {
        'paid_amount': paid_after, 'outstanding_amount': round(total - paid_after, 2), 'status': status,
        'paid_at': _now() if status == 'paid' else None, 'last_payment_date': pay_date, 'updated_at': _now()}})
    await log_activity(user.get('id', ''), user.get('name', ''), 'pay_cmt', 'dewi_cmt_payments',
                       f"Bayar {payment.get('payment_code')} Rp {amount:,.0f} via {acc.get('name')}")
    return serialize_doc({**doc, 'payment_status': status, 'outstanding_amount': round(total - paid_after, 2)})


@router.post('/cmt-payments/{payment_id}/disbursements/{did}/void')
async def void_cmt_disbursement(payment_id: str, did: str, user: dict = Depends(require_auth)):
    db = get_db()
    d = await db.dewi_cmt_disbursements.find_one({'id': did, 'payment_id': payment_id, 'status': {'$ne': 'voided'}}, {'_id': 0})
    if not d:
        raise HTTPException(404, 'Pembayaran tidak ditemukan')
    from routes.rahaza_posting import _void_je_by_source
    v = await _void_je_by_source(db, 'ap_payment', f"appay:{did}:{int(round(float(d['amount'])))}", user, 'Pembayaran CMT dibatalkan')
    if not v.get('ok'):
        raise HTTPException(400, f"Jurnal tidak bisa di-void: {v.get('error')}")
    mv = await db.rahaza_cash_movements.find_one({'id': did}, {'_id': 0})
    if mv:
        await db.rahaza_cash_movements.delete_one({'id': did})
        await db.rahaza_cash_accounts.update_one({'id': mv['account_id']}, {'$inc': {'balance': float(mv['amount'])}})
    await db.dewi_cmt_disbursements.update_one({'id': did}, {'$set': {'status': 'voided', 'voided_at': _now(), 'voided_by': user.get('id')}})
    payment = await db.dewi_cmt_payments.find_one({'id': payment_id}, {'_id': 0})
    total = _cmt_amount(payment)
    paid = round(float(payment.get('paid_amount') or 0) - float(d['amount']), 2)
    paid = max(paid, 0.0)
    status = 'paid' if paid >= total - 0.01 else ('partial_paid' if paid > 0 else ('posted' if payment.get('gl_je_id') else 'draft'))
    await db.dewi_cmt_payments.update_one({'id': payment_id}, {'$set': {
        'paid_amount': paid, 'outstanding_amount': round(total - paid, 2), 'status': status, 'paid_at': None, 'updated_at': _now()}})
    return {'ok': True, 'payment_status': status, 'voided_je': v.get('je_number')}
