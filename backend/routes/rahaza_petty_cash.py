"""
Kas Kecil / Petty Cash (Imprest Fund) — Phase 6B
CV. Dewi Aditya ERP

Konsep:
  - Satu atau lebih fund (dana kas kecil) dengan saldo bergerak
  - Transaksi: expense, advance, return, replenish, close
  - Auto-posting GL untuk setiap transaksi
  - Hanya Finance/Admin yang bisa buat fund & replenish; Kasir input expense

Collections:
  rahaza_petty_cash_funds  — master fund
  rahaza_petty_cash_txns   — transaksi

Prefix: /api/finance/petty-cash
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, timezone, date
from database import get_db
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_posting import (
    _create_posted_je, _find_existing_je, get_mapping
)
import logging
import uuid

log = logging.getLogger(__name__)
router = APIRouter(prefix='/api/finance/petty-cash', tags=['Petty-Cash'])

# RC-FLOW-kasbank-1 FIX: role Finance kanonik di sistem = 'accounting'/'staff_keuangan'
# (bukan 'finance'). Sebelumnya akun finance@dewiaditya.id (role 'accounting') DITOLAK 403
# saat membuat/replenish/close dana kas kecil. Selaraskan dgn employee_expense_claims.py.
FINANCE_ROLES = ('superadmin', 'admin', 'owner', 'finance', 'accounting', 'staff_keuangan', 'finance_manager')
ALL_ROLES     = ('superadmin', 'admin', 'owner', 'finance', 'accounting', 'staff_keuangan', 'finance_manager', 'cashier', 'staff')

TXN_TYPES = ('expense', 'advance', 'return', 'replenish', 'opening')


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc).isoformat()


def _ser(doc: dict) -> dict:
    return serialize_doc(doc) if doc else {}


# ── Pydantic ────────────────────────────────────────────────────────────────

class FundCreate(BaseModel):
    name: str = Field(..., min_length=1)
    custodian_name: Optional[str] = None
    opening_balance: float = Field(0.0, ge=0)
    bank_account_code: Optional[str] = '1-1201'
    notes: Optional[str] = None


class TxnCreate(BaseModel):
    fund_id: str
    txn_type: str = Field(...)
    amount: float = Field(..., gt=0)
    txn_date: Optional[str] = None   # ISO date, default today
    category: Optional[str] = None   # expense category
    payee:    Optional[str] = None
    memo:     Optional[str] = None
    bank_account_code: Optional[str] = None  # untuk replenish: source bank


class ReplenishIn(BaseModel):
    amount: float = Field(..., gt=0)
    bank_account_code: Optional[str] = '1-1201'
    memo: Optional[str] = None
    txn_date: Optional[str] = None


# ── Helpers ─────────────────────────────────────────────────────────────────

async def _get_fund_or_404(db, fund_id: str) -> dict:
    fund = await db.rahaza_petty_cash_funds.find_one({'id': fund_id}, {'_id': 0})
    if not fund:
        raise HTTPException(404, 'Dana kas kecil tidak ditemukan.')
    return fund


async def _post_petty_cash_txn(db, txn: dict, user: dict) -> dict:
    """
    Auto-post JE untuk transaksi petty cash.
    - expense / advance:  Dr Expense (by category) / Cr Petty Cash (1-110)
    - replenish:          Dr Petty Cash (1-110) / Cr Bank
    - return:             Dr Petty Cash (1-110) / Cr Expense reversal
    - opening:            Dr Petty Cash (1-110) / Cr Bank (initial funding)
    """
    txn_id = txn['id']
    txn_type = txn['txn_type']
    amount = float(txn['amount'])
    source_ref = f'pctxn:{txn_id}'

    existing = await _find_existing_je(db, f'petty_cash_{txn_type}', source_ref)
    if existing:
        return {'ok': True, 'je_id': existing['id'], 'je_number': existing['je_number'], 'already_posted': True}

    try:
        je_date = date.fromisoformat((txn.get('txn_date') or str(date.today()))[:10])
    except Exception:
        je_date = date.today()

    petty_cash_code = '1-110'

    if txn_type in ('expense', 'advance'):
        # Ambil expense account dari GL mapping atau posting profile
        mapping = await get_mapping(db, 'petty_cash_expense')
        expense_code = mapping.get('debit_expense_default', '6-2200')
        # Cek apakah ada kategori yang dipetakan ke GL
        category = txn.get('category')
        if category:
            cat_map = await db.employee_expense_gl_mappings.find_one(
                {'category': category, 'is_active': True}, {'_id': 0, 'gl_account_code': 1}
            )
            if cat_map:
                expense_code = cat_map['gl_account_code']
        memo = f"Kas Kecil {txn_type.capitalize()}: {txn.get('memo') or txn.get('payee') or category or 'Pengeluaran'}"
        lines = [
            {'account_code': expense_code, 'debit': round(amount, 2), 'credit': 0,
             'description': memo},
            {'account_code': petty_cash_code, 'debit': 0, 'credit': round(amount, 2),
             'description': memo},
        ]
        event_type = 'petty_cash_expense'

    elif txn_type == 'return':
        # Pengembalian uang muka → Dr Petty Cash / Cr Expense/Advance
        mapping = await get_mapping(db, 'petty_cash_expense')
        expense_code = mapping.get('debit_expense_default', '6-2200')
        memo = f"Return Kas Kecil: {txn.get('memo') or 'Pengembalian'}"
        lines = [
            {'account_code': petty_cash_code, 'debit': round(amount, 2), 'credit': 0,
             'description': memo},
            {'account_code': expense_code, 'debit': 0, 'credit': round(amount, 2),
             'description': memo},
        ]
        event_type = 'petty_cash_expense'  # reuse event_type

    elif txn_type in ('replenish', 'opening'):
        mapping = await get_mapping(db, 'petty_cash_replenish')
        bank_code = txn.get('bank_account_code') or mapping.get('credit_bank_default', '1-1201')
        memo = txn.get('memo') or ('Pengisian Awal Kas Kecil' if txn_type == 'opening' else 'Replenishment Kas Kecil')
        lines = [
            {'account_code': petty_cash_code, 'debit': round(amount, 2), 'credit': 0,
             'description': memo},
            {'account_code': bank_code, 'debit': 0, 'credit': round(amount, 2),
             'description': memo},
        ]
        event_type = 'petty_cash_replenish'
    else:
        return {'ok': False, 'error': f'Tipe transaksi tidak dikenal: {txn_type}'}

    result = await _create_posted_je(db, je_date, memo, event_type, source_ref, lines, user)
    # Persist result on txn
    if result.get('ok'):
        upd = {'gl_posted': True, 'gl_je_id': result.get('je_id'), 'gl_je_number': result.get('je_number'), 'gl_error': None}
    else:
        upd = {'gl_posted': False, 'gl_je_id': None, 'gl_error': result.get('error')}
    await db.rahaza_petty_cash_txns.update_one({'id': txn_id}, {'$set': upd})
    return result


# ── Fund Endpoints ──────────────────────────────────────────────────────────

@router.get('/funds')
async def list_funds(user: dict = Depends(require_auth)):
    db = get_db()
    funds = await db.rahaza_petty_cash_funds.find({}, {'_id': 0}).sort('created_at', -1).to_list(100)
    return {'items': [_ser(f) for f in funds], 'total': len(funds)}


@router.post('/funds')
async def create_fund(body: FundCreate, user: dict = Depends(require_auth)):
    if user.get('role') not in FINANCE_ROLES:
        raise HTTPException(403, 'Hanya Finance/Admin yang bisa membuat dana kas kecil.')
    db = get_db()
    fund_id = _uid()
    now = _now()
    doc = {
        'id': fund_id,
        'name': body.name.strip(),
        'custodian_name': body.custodian_name or '',
        'opening_balance': body.opening_balance,
        'current_balance': body.opening_balance,
        'bank_account_code': body.bank_account_code or '1-1201',
        'notes': body.notes or '',
        'status': 'active',
        'created_at': now,
        'updated_at': now,
        'created_by': user['id'],
    }
    await db.rahaza_petty_cash_funds.insert_one(doc)

    # Post opening entry jika ada saldo awal
    if body.opening_balance > 0:
        txn_id = _uid()
        txn_doc = {
            'id': txn_id, 'fund_id': fund_id,
            'txn_type': 'opening',
            'amount': body.opening_balance,
            'txn_date': str(date.today()),
            'memo': f'Saldo awal dana {body.name}',
            'bank_account_code': body.bank_account_code or '1-1201',
            'category': None, 'payee': None,
            'gl_posted': False, 'gl_je_id': None, 'gl_error': None,
            'created_at': now, 'created_by': user['id'],
        }
        await db.rahaza_petty_cash_txns.insert_one(txn_doc)
        await _post_petty_cash_txn(db, txn_doc, user)

    await log_activity(user['id'], user.get('name', ''), 'CREATE_PETTY_CASH_FUND', 'petty_cash_fund', fund_id)
    return _ser(doc)


@router.get('/funds/{fund_id}')
async def get_fund(fund_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    fund = await _get_fund_or_404(db, fund_id)
    # Tambah ringkasan txn
    txns_count = await db.rahaza_petty_cash_txns.count_documents({'fund_id': fund_id})
    fund['txns_count'] = txns_count
    return _ser(fund)


@router.post('/funds/{fund_id}/replenish')
async def replenish_fund(fund_id: str, body: ReplenishIn, user: dict = Depends(require_auth)):
    if user.get('role') not in FINANCE_ROLES:
        raise HTTPException(403, 'Hanya Finance/Admin yang bisa replenish dana.')
    db = get_db()
    fund = await _get_fund_or_404(db, fund_id)
    if fund.get('status') != 'active':
        raise HTTPException(400, 'Dana kas kecil tidak aktif.')
    now = _now()
    txn_doc = {
        'id': _uid(), 'fund_id': fund_id,
        'txn_type': 'replenish',
        'amount': body.amount,
        'txn_date': body.txn_date or str(date.today()),
        'memo': body.memo or 'Replenishment Kas Kecil',
        'bank_account_code': body.bank_account_code or '1-1201',
        'category': None, 'payee': None,
        'gl_posted': False, 'gl_je_id': None, 'gl_error': None,
        'created_at': now, 'created_by': user['id'],
    }
    await db.rahaza_petty_cash_txns.insert_one(txn_doc)
    # Update fund balance
    await db.rahaza_petty_cash_funds.update_one(
        {'id': fund_id},
        {'$inc': {'current_balance': body.amount}, '$set': {'updated_at': now}}
    )
    posting_result = await _post_petty_cash_txn(db, txn_doc, user)
    await log_activity(user['id'], user.get('name', ''), 'REPLENISH_PETTY_CASH', 'petty_cash_fund', fund_id)
    return {
        'ok': True,
        'txn': _ser(txn_doc),
        'new_balance': fund['current_balance'] + body.amount,
        'gl_posting': posting_result,
    }


@router.post('/funds/{fund_id}/close')
async def close_fund(fund_id: str, user: dict = Depends(require_auth)):
    if user.get('role') not in FINANCE_ROLES:
        raise HTTPException(403, 'Hanya Finance/Admin yang bisa menutup dana.')
    db = get_db()
    fund = await _get_fund_or_404(db, fund_id)
    if fund.get('status') == 'closed':
        raise HTTPException(400, 'Dana sudah ditutup.')
    now = _now()
    # Jika masih ada saldo, kembalikan ke bank
    remaining = float(fund.get('current_balance') or 0)
    posting_result = None
    if remaining > 0:
        txn_doc = {
            'id': _uid(), 'fund_id': fund_id,
            'txn_type': 'return',
            'amount': remaining,
            'txn_date': str(date.today()),
            'memo': f'Penutupan dana {fund["name"]} - sisa saldo dikembalikan ke bank',
            'bank_account_code': fund.get('bank_account_code', '1-1201'),
            'category': None, 'payee': None,
            'gl_posted': False, 'gl_je_id': None, 'gl_error': None,
            'created_at': now, 'created_by': user['id'],
        }
        await db.rahaza_petty_cash_txns.insert_one(txn_doc)
        posting_result = await _post_petty_cash_txn(db, txn_doc, user)

    await db.rahaza_petty_cash_funds.update_one(
        {'id': fund_id},
        {'$set': {'status': 'closed', 'current_balance': 0, 'closed_at': now, 'updated_at': now}}
    )
    await log_activity(user['id'], user.get('name', ''), 'CLOSE_PETTY_CASH_FUND', 'petty_cash_fund', fund_id)
    return {'ok': True, 'returned_balance': remaining, 'gl_posting': posting_result}


# ── Transaction Endpoints ────────────────────────────────────────────────────

@router.post('/transactions')
async def create_txn(body: TxnCreate, user: dict = Depends(require_auth)):
    if body.txn_type not in ('expense', 'advance', 'return'):
        raise HTTPException(400, 'Hanya expense/advance/return yang bisa diinput via form. Replenish gunakan /funds/{id}/replenish.')
    db = get_db()
    fund = await _get_fund_or_404(db, body.fund_id)
    if fund.get('status') != 'active':
        raise HTTPException(400, 'Dana kas kecil tidak aktif.')

    # Cek saldo cukup untuk pengeluaran
    if body.txn_type in ('expense', 'advance'):
        if float(fund.get('current_balance', 0)) < body.amount:
            raise HTTPException(400, f'Saldo kas kecil tidak cukup. Saldo: {fund["current_balance"]:.2f}, Diminta: {body.amount:.2f}')

    now = _now()
    txn_doc = {
        'id': _uid(),
        'fund_id': body.fund_id,
        'txn_type': body.txn_type,
        'amount': body.amount,
        'txn_date': body.txn_date or str(date.today()),
        'category': body.category or '',
        'payee':    body.payee or '',
        'memo':     body.memo or '',
        'bank_account_code': body.bank_account_code or fund.get('bank_account_code', '1-1201'),
        'gl_posted': False, 'gl_je_id': None, 'gl_je_number': None, 'gl_error': None,
        'created_at': now,
        'created_by': user['id'],
        'created_by_name': user.get('name', user.get('email', '')),
    }
    await db.rahaza_petty_cash_txns.insert_one(txn_doc)

    # Update fund balance
    delta = -body.amount if body.txn_type in ('expense', 'advance') else body.amount
    await db.rahaza_petty_cash_funds.update_one(
        {'id': body.fund_id},
        {'$inc': {'current_balance': delta}, '$set': {'updated_at': now}}
    )

    posting_result = await _post_petty_cash_txn(db, txn_doc, user)
    await log_activity(user['id'], user.get('name', ''), f'PETTY_CASH_{body.txn_type.upper()}', 'petty_cash_txn', txn_doc['id'])
    return {
        'txn': _ser(txn_doc),
        'gl_posting': posting_result,
        'new_balance': float(fund.get('current_balance', 0)) + delta,
    }


@router.get('/transactions')
async def list_txns(
    fund_id: Optional[str] = Query(None),
    txn_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
    user: dict = Depends(require_auth),
):
    db = get_db()
    q = {}
    if fund_id:
        q['fund_id'] = fund_id
    if txn_type:
        q['txn_type'] = txn_type
    total = await db.rahaza_petty_cash_txns.count_documents(q)
    txns = await db.rahaza_petty_cash_txns.find(q, {'_id': 0}).sort('txn_date', -1).skip(skip).limit(limit).to_list(limit)
    return {'items': [_ser(t) for t in txns], 'total': total}


@router.post('/transactions/{txn_id}/retry-posting')
async def retry_txn_posting(txn_id: str, user: dict = Depends(require_auth)):
    if user.get('role') not in FINANCE_ROLES:
        raise HTTPException(403, 'Hanya Finance yang bisa retry posting.')
    db = get_db()
    txn = await db.rahaza_petty_cash_txns.find_one({'id': txn_id}, {'_id': 0})
    if not txn:
        raise HTTPException(404, 'Transaksi tidak ditemukan.')
    result = await _post_petty_cash_txn(db, txn, user)
    return result
