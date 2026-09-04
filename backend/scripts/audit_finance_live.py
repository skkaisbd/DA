"""Uji nyata audit finance (read+write terkontrol, data uji ditandai AUDIT- lalu dibersihkan).
cd /app/backend && python3 scripts/audit_finance_live.py
"""
import os, asyncio, json, requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
A = 'http://localhost:8001/api'
TOK = open('/app/.tok_admin').read().strip()
H = {'Authorization': f'Bearer {TOK}', 'Content-Type': 'application/json'}
R = {}


def je_lines(db_lines):
    return [(l['account_code'], l['account_name'], l['debit'], l['credit']) for l in db_lines]


async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    created_je = []

    async def je_of(source_module, ref):
        je = await db.rahaza_journal_entries.find_one({'source_module': source_module, 'source_ref': ref}, {'_id': 0})
        if je:
            created_je.append(je['id'])
        return je

    # ── T1: AR invoice pelanggan (auto-COA customer) → issue → bayar
    cust = await db.rahaza_customers.find_one({}, {'_id': 0, 'id': 1, 'name': 1})
    tmp_cust = False
    if not cust:
        cust = {'id': 'audit-cust-1', 'name': 'AUDIT Customer', 'code': 'AUDIT'}
        await db.rahaza_customers.insert_one({**cust, 'active': True})
        tmp_cust = True
    R['T1_customer'] = cust
    await db.rahaza_cash_accounts.delete_many({'code': 'AUDIT-BANK'})
    r = requests.post(f'{A}/rahaza/cash-accounts', headers=H, json={'code': 'AUDIT-BANK', 'name': 'AUDIT Bank', 'type': 'bank', 'gl_account_code': '1-1201', 'opening_balance': 0})
    R['T1_cash_acc'] = r.status_code, r.text[:200]
    cash_id = r.json().get('id') if r.status_code in (200, 201) else None
    r = requests.post(f'{A}/rahaza/ar-invoices', headers=H, json={
        'customer_id': cust['id'], 'customer_name': cust['name'], 'items': [{'description': 'AUDIT item', 'qty': 2, 'unit_price': 100000}],
        'tax_pct': 11, 'notes': 'AUDIT-T1', 'sales_channel': ''})
    R['T1_create'] = r.status_code, r.text[:300]
    inv = r.json() if r.status_code in (200, 201) else {}
    iid = inv.get('id')
    if iid:
        r = requests.post(f'{A}/rahaza/ar-invoices/{iid}/send', headers=H, json={})
        R['T1_send'] = r.status_code, r.text[:200]
        je = await je_of('ar_invoice', f'ar:{iid}')
        R['T1_je_issue'] = je and je_lines(je['lines'])
        r = requests.post(f'{A}/rahaza/ar-invoices/{iid}/payment', headers=H, json={'amount': 100000, 'account_id': cash_id, 'payment_date': '2026-09-04'})
        R['T1_pay'] = r.status_code, r.text[:300]
        mv = await db.rahaza_cash_movements.find_one({'reference_id': iid}, {'_id': 0}) or await db.rahaza_cash_movements.find_one({'notes': {'$regex': inv.get('invoice_number', 'x')}}, {'_id': 0})
        jep = await db.rahaza_journal_entries.find_one({'source_module': 'ar_payment', 'source_ref': {'$regex': 'arpay:'}}, {'_id': 0}, sort=[('created_at', -1)])
        if jep:
            created_je.append(jep['id'])
        R['T1_je_pay'] = jep and je_lines(jep['lines'])
        inv2 = await db.rahaza_ar_invoices.find_one({'id': iid}, {'_id': 0})
        R['T1_inv_after'] = {k: inv2.get(k) for k in ('status', 'total', 'paid_amount', 'balance', 'gl_je_number', 'post_error')}
        # aging rahaza vs aging maklon
        r = requests.get(f'{A}/rahaza/ar-aging', headers=H)
        R['T1_ar_aging_total'] = r.json().get('total') if r.status_code == 200 else r.text[:200]

    # ── T2: AP-from-GR → akun debit
    gr = await db.rahaza_goods_receipts.find_one({'status': {'$in': ['received', 'completed', 'partial_received']}}, {'_id': 0, 'id': 1, 'receipt_number': 1, 'vendor_id': 1}) if 'rahaza_goods_receipts' in await db.list_collection_names() else None
    R['T2_gr'] = gr
    if gr:
        r = requests.post(f'{A}/rahaza/ap-invoices/from-gr', headers=H, json={'gr_ids': [gr['id']], 'tax_pct': 0, 'notes': 'AUDIT-T2'})
        R['T2_create'] = r.status_code, r.text[:300]
        ap = r.json() if r.status_code in (200, 201) else {}
        if ap.get('id'):
            r = requests.post(f"{A}/rahaza/ap-invoices/{ap['id']}/send", headers=H, json={})
            R['T2_send'] = r.status_code, r.text[:200]
            je = await je_of('ap_invoice', f"ap:{ap['id']}")
            R['T2_je'] = je and je_lines(je['lines'])
            await db.rahaza_ap_invoices.delete_one({'id': ap['id']})
            await db.rahaza_goods_receipts.update_one({'id': gr['id']}, {'$unset': {'ap_invoice_id': '', 'ap_invoice_number': '', 'invoiced_at': ''}})

    # ── T3: Maklon post-ar sebelum invoice generate (AR masih draft, qty ordered)
    mirror = await db.dewi_maklon_pos.find_one({'id': 'po-mk-demo-2'}, {'_id': 0})
    ar = await db.rahaza_ar_invoices.find_one({'id': mirror['ar_invoice_id']}, {'_id': 0})
    R['T3_ar_before'] = {k: ar.get(k) for k in ('status', 'total_amount', 'invoice_date', 'gl_je_id')}
    r = requests.post(f'{A}/dewi/maklon/pos/po-mk-demo-2/post-ar', headers=H)
    R['T3_post_ar'] = r.status_code, r.text[:300]
    je = await je_of('maklon_ar_invoice', f"maklon_ar:{mirror['ar_invoice_id']}")
    R['T3_je'] = je and {'date': je['date'], 'lines': je_lines(je['lines'])}
    ar = await db.rahaza_ar_invoices.find_one({'id': mirror['ar_invoice_id']}, {'_id': 0})
    R['T3_ar_after_postar'] = {k: ar.get(k) for k in ('status', 'total_amount', 'gl_je_id')}
    # sekarang generate invoice (qty received) → apakah JE ikut berubah?
    r = requests.post(f'{A}/dewi/maklon/invoices/generate', headers=H, json={'order_id': 'po-mk-demo-2', 'tax_pct': 11})
    R['T3_generate'] = r.status_code, r.text[:200]
    ar = await db.rahaza_ar_invoices.find_one({'id': mirror['ar_invoice_id']}, {'_id': 0})
    je2 = await db.rahaza_journal_entries.find_one({'source_module': 'maklon_ar_invoice', 'source_ref': f"maklon_ar:{mirror['ar_invoice_id']}", 'status': {'$ne': 'voided'}}, {'_id': 0})
    R['T3_after_generate'] = {'ar_total': ar.get('total_amount'), 'je_total': je2 and je2['total_debit'], 'je_count_active': await db.rahaza_journal_entries.count_documents({'source_ref': f"maklon_ar:{mirror['ar_invoice_id']}", 'status': {'$ne': 'voided'}})}
    if r.status_code == 200:
        inv_id = r.json()['id']
        r = requests.post(f'{A}/dewi/maklon/payments', headers=H, json={'invoice_id': inv_id, 'amount': 100000, 'method': 'transfer'})
        R['T3_payment'] = r.status_code
        R['T3_payment_je'] = await db.rahaza_journal_entries.count_documents({'$or': [{'source_ref': {'$regex': inv_id}}, {'memo': {'$regex': 'INV-MKL'}}], 'source_module': {'$in': ['ar_payment', 'maklon_ar_payment']}})
        pid = r.json().get('id')
        r = requests.get(f'{A}/rahaza/ar-aging', headers=H)
        R['T3_rahaza_aging_after_maklon'] = r.json().get('total') if r.status_code == 200 else r.text[:100]
        r = requests.get(f'{A}/dewi/maklon/reports/aging', headers=H)
        R['T3_maklon_aging'] = (r.json().get('total') or r.json().get('summary') or str(r.json())[:200]) if r.status_code == 200 else r.text[:100]
        # cancel → GL posted → 400 diharapkan
        r = requests.post(f'{A}/dewi/maklon/invoices/{inv_id}/cancel', headers=H)
        R['T3_cancel_when_gl_posted'] = r.status_code, r.text[:150]
        requests.delete(f'{A}/dewi/maklon/payments/{pid}', headers=H)

    # ── T4: Neraca dgn akun CURRENT_ASSET (1-1320) via jurnal manual
    r = requests.post(f'{A}/rahaza/journals', headers=H, json={'date': '2026-09-04', 'memo': 'AUDIT-T4 kasbon', 'lines': [
        {'account_code': '1-1320', 'debit': 500000, 'credit': 0, 'description': 'AUDIT'}, {'account_code': '1-1201', 'debit': 0, 'credit': 500000, 'description': 'AUDIT'}]})
    R['T4_create'] = r.status_code, r.text[:200]
    if r.status_code in (200, 201):
        jid = r.json().get('id')
        r = requests.post(f'{A}/rahaza/journals/{jid}/post', headers=H)
        R['T4_post'] = r.status_code
        created_je.append(jid)
    bs = requests.get(f'{A}/rahaza/finance/reports/balance-sheet', headers=H).json()
    R['T4_bs'] = {'balanced': bs.get('balanced'), 'totals': bs.get('totals')}
    tb = requests.get(f'{A}/rahaza/finance/reports/trial-balance', headers=H).json()
    R['T4_tb'] = {'balanced': tb.get('balanced'), 'totals': tb.get('totals')}
    pl = requests.get(f'{A}/rahaza/finance/reports/profit-loss', headers=H).json()
    R['T4_pl_totals'] = pl.get('totals')
    # cek apakah 1-1320 tampil di neraca
    R['T4_1320_in_bs'] = any(a['code'] == '1-1320' for a in bs['assets']['accounts'])

    # ── T5: jurnal ke periode yang belum ada di rahaza_periods → diterima?
    r = requests.post(f'{A}/rahaza/journals', headers=H, json={'date': '2019-01-15', 'memo': 'AUDIT-T5 backdate', 'lines': [
        {'account_code': '1-110', 'debit': 1000, 'credit': 0}, {'account_code': '4-1100', 'debit': 0, 'credit': 1000}]})
    R['T5_backdate_2019'] = r.status_code, r.text[:150]
    if r.status_code in (200, 201):
        created_je.append(r.json().get('id'))

    print(json.dumps(R, indent=1, default=str))

    # ── CLEANUP
    ids = [i for i in created_je if i]
    await db.rahaza_journal_lines.delete_many({'je_id': {'$in': ids}})
    await db.rahaza_journal_entries.delete_many({'id': {'$in': ids}})
    await db.rahaza_journal_entries.delete_many({'memo': {'$regex': 'AUDIT'}})
    await db.rahaza_journal_lines.delete_many({'description': 'AUDIT'})
    if iid:
        await db.rahaza_ar_invoices.delete_one({'id': iid})
        await db.rahaza_cash_movements.delete_many({'$or': [{'reference_id': iid}, {'account_id': cash_id}]})
        await db.rahaza_journal_entries.delete_many({'source_module': 'ar_payment', 'memo': {'$regex': inv.get('invoice_number', 'AUDIT')}})
    if cash_id:
        await db.rahaza_cash_accounts.delete_one({'id': cash_id})
    if tmp_cust:
        await db.rahaza_customers.delete_one({'id': cust['id']})
        await db.rahaza_coa_accounts.delete_many({'flags.subledger_entity_id': cust['id']})
        await db.rahaza_coa_accounts.delete_many({'name': {'$regex': 'AUDIT Customer'}})
    # maklon: kembalikan AR ke draft + hapus JE maklon + cermin invoice
    await db.rahaza_journal_entries.delete_many({'source_ref': f"maklon_ar:{mirror['ar_invoice_id']}"})
    await db.rahaza_journal_lines.delete_many({'source_ref': f"maklon_ar:{mirror['ar_invoice_id']}"})
    await db.dewi_maklon_payments.delete_many({'invoice_id': mirror['ar_invoice_id']})
    await db.dewi_maklon_invoices.delete_many({'order_id': 'po-mk-demo-2'})
    await db.rahaza_ar_invoices.update_one({'id': mirror['ar_invoice_id']}, {'$set': {'status': 'draft', 'gl_posted_at': None, 'gl_je_id': None, 'gl_je_number': None, 'amount_paid': 0.0, 'issued_at': None}})
    await db.dewi_maklon_pos.update_one({'id': 'po-mk-demo-2'}, {'$set': {'gl_posted_at': None, 'gl_je_id': None, 'gl_je_number': None, 'post_error': None}})
    requests.post(f'{A}/production-pos/po-mk-demo-2/sync-maklon-finance', headers=H)
    m = await db.dewi_maklon_pos.find_one({'id': 'po-mk-demo-2'}, {'_id': 0, 'status': 1})
    print('CLEANUP mirror status', m, 'JE left', await db.rahaza_journal_entries.count_documents({}), 'lines', await db.rahaza_journal_lines.count_documents({}))

asyncio.run(main())
