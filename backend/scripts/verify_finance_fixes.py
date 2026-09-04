"""Uji nyata perbaikan audit finance (C-01, C-02, C-04, C-05, C-06, H-04). Data uji ditandai FIXTEST- lalu dibersihkan.
cd /app/backend && python3 scripts/verify_finance_fixes.py
"""
import os, asyncio, json, requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')
A = 'http://localhost:8001/api'
TOK = open('/app/.tok_admin').read().strip()
H = {'Authorization': f'Bearer {TOK}', 'Content-Type': 'application/json'}
R = {}
FAIL = []


def check(name, cond, detail=''):
    R[name] = ('PASS' if cond else 'FAIL', detail)
    if not cond:
        FAIL.append(name)


def je_lines(lines):
    return [(l['account_code'], l['debit'], l['credit']) for l in lines]


async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    je_before = await db.rahaza_journal_entries.count_documents({})
    je_ids_before = set(await db.rahaza_journal_entries.distinct('id'))

    # ── C-04/C-05/H-04: COA & profil
    a1320 = await db.rahaza_coa_accounts.find_one({'code': '1-1320'}, {'_id': 0})
    check('C04_1-1320_type_ASSET', a1320 and a1320['type'] == 'ASSET' and a1320['normal_balance'] == 'DEBIT', a1320 and (a1320['type'], a1320['normal_balance']))
    grni = await db.rahaza_coa_accounts.find_one({'code': '2-1150'}, {'_id': 0})
    check('C02_GRNI_account', grni and grni['parent_code'] == '2-1000' and grni['active'], grni and grni['name'])
    disp = await db.rahaza_posting_profiles.find_one({'event_type': 'asset_disposal'}, {'_id': 0})
    check('C05_asset_disposal_profile', disp['mapping']['credit_fixed_asset'] == '1-2500' and disp['mapping']['debit_accum_depr'] == '1-2501', disp['mapping'])
    legacy_active = await db.rahaza_coa_accounts.count_documents({'code': {'$in': ['1-110', '1-131', '1-210', '1-220', '2-110', '2-120', '1-310', '1-330']}, 'active': True})
    check('H04_legacy_deactivated', legacy_active == 0, f'legacy aktif={legacy_active}')
    bad = []
    async for p in db.rahaza_posting_profiles.find({}, {'_id': 0}):
        for role, code in p['mapping'].items():
            acc = await db.rahaza_coa_accounts.find_one({'code': code}, {'_id': 0, 'active': 1, 'is_group': 1})
            if not acc or not acc.get('active') or acc.get('is_group'):
                bad.append(f"{p['event_type']}.{role}={code}")
    check('H04_all_profiles_valid_active_leaf', not bad, bad)

    # ── C-01: AR pelanggan (subledger) → bayar → tutup di akun yang sama
    cust = {'id': 'fixtest-cust-1', 'name': 'FIXTEST Customer', 'code': 'FIXTEST', 'active': True}
    await db.rahaza_customers.delete_many({'id': cust['id']})
    await db.rahaza_customers.insert_one(dict(cust))
    await db.rahaza_cash_accounts.delete_many({'code': 'FIXTEST-BANK'})
    r = requests.post(f'{A}/rahaza/cash-accounts', headers=H, json={'code': 'FIXTEST-BANK', 'name': 'FIXTEST Bank', 'type': 'bank', 'gl_account_code': '1-1201', 'opening_balance': 0})
    cash = r.json() if r.status_code in (200, 201) else {}
    cash_id = cash.get('id')
    R['cash_account'] = (r.status_code, cash.get('gl_account_code'))
    r = requests.post(f'{A}/rahaza/ar-invoices', headers=H, json={
        'customer_id': cust['id'], 'customer_name': cust['name'],
        'items': [{'description': 'FIXTEST item', 'qty': 2, 'unit_price': 100000}], 'tax_pct': 11, 'notes': 'FIXTEST-C01'})
    inv = r.json() if r.status_code in (200, 201) else {}
    iid = inv.get('id')
    R['ar_create'] = (r.status_code, inv.get('invoice_number'))
    ar_code_issue = ar_code_pay = ar_code_wo = None
    if iid:
        requests.post(f'{A}/rahaza/ar-invoices/{iid}/send', headers=H, json={})
        je = await db.rahaza_journal_entries.find_one({'source_module': 'ar_invoice', 'source_ref': f'ar:{iid}'}, {'_id': 0})
        ar_code_issue = je and max(je['lines'], key=lambda l: l['debit'])['account_code']
        inv_db = await db.rahaza_ar_invoices.find_one({'id': iid}, {'_id': 0})
        check('C01_ar_gl_account_stored', inv_db.get('gl_ar_account_code') == ar_code_issue, (inv_db.get('gl_ar_account_code'), ar_code_issue))
        r = requests.post(f'{A}/rahaza/ar-invoices/{iid}/payment', headers=H, json={'amount': 100000, 'account_id': cash_id, 'payment_date': '2026-09-04'})
        pr = r.json().get('_posting_result') if r.status_code == 200 else r.text[:200]
        R['ar_pay'] = (r.status_code, pr)
        jep = await db.rahaza_journal_entries.find_one({'source_module': 'ar_payment', 'memo': {'$regex': inv.get('invoice_number', 'x')}}, {'_id': 0})
        ar_code_pay = jep and [l['account_code'] for l in jep['lines'] if l['credit'] > 0][0]
        check('C01_ar_payment_same_account', ar_code_issue and ar_code_pay == ar_code_issue, (ar_code_issue, ar_code_pay))
        bank_gl = (await db.rahaza_cash_accounts.find_one({'id': cash_id}, {'_id': 0}) or {}).get('gl_account_code')
        check('C01_ar_payment_debit_bank', jep and [l['account_code'] for l in jep['lines'] if l['debit'] > 0][0] == bank_gl, (bank_gl, jep and je_lines(jep['lines'])))
        # write-off sisa
        r = requests.post(f'{A}/rahaza/ar-invoices/{iid}/write-off-bad-debt', headers=H, json={'reason': 'FIXTEST write-off'})
        jew = await db.rahaza_journal_entries.find_one({'source_module': 'bad_debt_writeoff', 'source_ref': f'bad_debt:{iid}'}, {'_id': 0})
        ar_code_wo = jew and [l['account_code'] for l in jew['lines'] if l['credit'] > 0][0]
        check('C01_writeoff_same_account', ar_code_wo == ar_code_issue, (r.status_code, ar_code_issue, ar_code_wo, jew and je_lines(jew['lines'])))
        # saldo subledger = 0
        agg = await db.rahaza_journal_lines.aggregate([{'$match': {'account_code': ar_code_issue}}, {'$group': {'_id': None, 'd': {'$sum': '$debit'}, 'c': {'$sum': '$credit'}}}]).to_list(1)
        check('C01_subledger_balance_zero', agg and round(agg[0]['d'] - agg[0]['c'], 2) == 0, agg)

    # ── C-06: maklon generate → JE; bayar → JE (Dr bank/Cr AR sama); cancel ditolak saat sudah bayar; hapus bayar → void; cancel → void
    mirror = await db.dewi_maklon_pos.find_one({'id': 'po-mk-demo-2'}, {'_id': 0})
    ar_id = mirror and mirror.get('ar_invoice_id')
    R['maklon_mirror'] = (mirror and mirror.get('status'), ar_id)
    r = requests.post(f'{A}/dewi/maklon/finance/pos/po-mk-demo-2/post-ar', headers=H)
    check('C06_post_ar_rejected_when_draft', r.status_code == 400, (r.status_code, r.text[:120]))
    r = requests.post(f'{A}/dewi/maklon/invoices/generate', headers=H, json={'order_id': 'po-mk-demo-2', 'tax_pct': 11})
    R['maklon_generate'] = (r.status_code, r.text[:200])
    inv_id = r.json().get('id') if r.status_code == 200 else None
    if inv_id:
        ar = await db.rahaza_ar_invoices.find_one({'id': ar_id}, {'_id': 0})
        je = await db.rahaza_journal_entries.find_one({'source_module': 'maklon_ar_invoice', 'source_ref': f'maklon_ar:{ar_id}', 'status': 'posted'}, {'_id': 0})
        check('C06_generate_posts_je', je is not None and abs(je['total_debit'] - float(ar['total_amount'])) < 0.01,
              {'ar_total': ar.get('total_amount'), 'je': je and (je['date'], je['total_debit'], je_lines(je['lines'])), 'invoice_date': ar.get('invoice_date'), 'post_error': ar.get('post_error')})
        check('C06_je_date_is_invoice_date', je and je['date'] == ar.get('invoice_date'), (je and je['date'], ar.get('invoice_date')))
        mk_ar_code = je and max(je['lines'], key=lambda l: l['debit'])['account_code']
        r = requests.post(f'{A}/dewi/maklon/payments', headers=H, json={'invoice_id': inv_id, 'amount': 100000, 'method': 'transfer', 'cash_account_id': cash_id, 'payment_date': '2026-09-04'})
        pay = r.json() if r.status_code == 200 else {}
        R['maklon_pay'] = (r.status_code, pay)
        pid = pay.get('id')
        jep = pid and await db.rahaza_journal_entries.find_one({'source_module': 'ar_payment', 'source_ref': {'$regex': f'arpay:{pid}'}, 'status': 'posted'}, {'_id': 0})
        check('C06_payment_posts_je', jep is not None and [l['account_code'] for l in jep['lines'] if l['credit'] > 0][0] == mk_ar_code and [l['account_code'] for l in jep['lines'] if l['debit'] > 0][0] == bank_gl,
              jep and je_lines(jep['lines']))
        mv = pid and await db.rahaza_cash_movements.find_one({'id': pid}, {'_id': 0})
        check('C06_payment_cash_movement', bool(mv), mv and (mv['amount'], mv['account_id'] == cash_id))
        r = requests.post(f'{A}/dewi/maklon/invoices/{inv_id}/cancel', headers=H)
        check('C06_cancel_rejected_when_paid', r.status_code == 400, (r.status_code, r.text[:100]))
        r = requests.delete(f'{A}/dewi/maklon/payments/{pid}', headers=H)
        jep2 = await db.rahaza_journal_entries.find_one({'id': jep['id']}, {'_id': 0}) if jep else None
        check('C06_delete_payment_voids_je', r.status_code == 200 and jep2 and jep2['status'] == 'voided' and not await db.rahaza_cash_movements.find_one({'id': pid}), (r.status_code, jep2 and jep2['status']))
        r = requests.post(f'{A}/dewi/maklon/invoices/{inv_id}/cancel', headers=H)
        je3 = await db.rahaza_journal_entries.find_one({'id': je['id']}, {'_id': 0}) if je else None
        ar3 = await db.rahaza_ar_invoices.find_one({'id': ar_id}, {'_id': 0})
        check('C06_cancel_voids_je_and_ar_draft', r.status_code == 200 and je3 and je3['status'] == 'voided' and ar3['status'] == 'draft' and not ar3.get('gl_posted_at'), (r.status_code, r.text[:100], je3 and je3['status'], ar3.get('status')))
        check('C06_no_orphan_mirror_lines', await db.rahaza_journal_lines.count_documents({'je_id': {'$in': [je['id'], jep['id'] if jep else 'x']}}) == 0)

    # ── C-02: GR baru (material seed) → status received → JE Dr Persediaan / Cr GRNI
    mat = await db.rahaza_materials.find_one({'type': {'$in': ['fabric', 'kain', 'raw', 'accessory', 'aksesoris']}}, {'_id': 0}) \
        or await db.rahaza_materials.find_one({}, {'_id': 0})
    loc = await db.rahaza_locations.find_one({'active': True}, {'_id': 0})
    gr = None
    gr_created = None
    if mat and loc:
        r = requests.post(f'{A}/warehouse/receiving', headers=H, json={
            'source_type': 'supplier', 'supplier_name': 'FIXTEST Supplier', 'location_id': loc['id'], 'location_name': loc.get('name', ''),
            'notes': 'FIXTEST-C02', 'items': [{'material_id': mat['id'], 'material_name': mat.get('name'), 'product_name': mat.get('name'),
                                              'sku': mat.get('code'), 'expected_qty': 10, 'received_qty': 10, 'unit': mat.get('unit', 'pcs'), 'unit_price': 25000}]})
        R['gr_create'] = (r.status_code, r.text[:150])
        if r.status_code in (200, 201):
            gr_created = r.json()
            items = gr_created.get('items') or []
            r = requests.put(f"{A}/warehouse/receiving/{gr_created['id']}", headers=H, json={'status': 'received', 'items': items})
            R['gr_receive'] = (r.status_code, r.text[:150])
            mv = await db.rahaza_material_movements.find_one({'reference_id': gr_created['id'], 'type': 'receive'}, {'_id': 0})
            je = mv and await db.rahaza_journal_entries.find_one({'source_module': 'inventory_receive', 'source_ref': f"mvrcv:{mv['id']}"}, {'_id': 0})
            check('C02_gr_posts_dr_inventory_cr_grni', je and je_lines(je['lines']) == [('1-1401', 250000.0, 0.0), ('2-1150', 0.0, 250000.0)], (mv and mv.get('unit_cost'), je and je_lines(je['lines'])))
            gr = await db.warehouse_receiving.find_one({'id': gr_created['id']}, {'_id': 0})
    else:
        R['C02_gr_skipped'] = 'tidak ada material/lokasi seed'
    R['gr_found'] = gr and (gr.get('receipt_number'), gr.get('supplier_name'), gr.get('status'), gr.get('ap_invoice_id'))
    ap_id = None
    if gr and not gr.get('ap_invoice_id'):
        r = requests.post(f'{A}/rahaza/ap-invoices/from-gr', headers=H, json={'gr_ids': [gr['id']], 'tax_pct': 0, 'notes': 'FIXTEST-C02'})
        R['ap_from_gr'] = (r.status_code, r.text[:200])
        ap = r.json() if r.status_code in (200, 201) else {}
        ap_id = ap.get('id')
        if ap_id:
            check('C02_ap_gl_debit_code_grni', ap.get('gl_debit_code') == '2-1150', ap.get('gl_debit_code'))
            r = requests.post(f'{A}/rahaza/ap-invoices/{ap_id}/send', headers=H, json={})
            je = await db.rahaza_journal_entries.find_one({'source_module': 'ap_invoice', 'source_ref': f'ap:{ap_id}'}, {'_id': 0})
            check('C02_ap_je_dr_grni_cr_ap', je and [l['account_code'] for l in je['lines'] if l['debit'] > 0] == ['2-1150'] and '6-2200' not in [l['account_code'] for l in je['lines']], (r.status_code, je and je_lines(je['lines'])))
            ap_db = await db.rahaza_ap_invoices.find_one({'id': ap_id}, {'_id': 0})
            ap_code_issue = je and [l['account_code'] for l in je['lines'] if l['credit'] > 0][0]
            check('C01_ap_gl_account_stored', ap_db.get('gl_ap_account_code') == ap_code_issue, (ap_db.get('gl_ap_account_code'), ap_code_issue))
            r = requests.post(f'{A}/rahaza/ap-invoices/{ap_id}/payment', headers=H, json={'amount': 1000, 'account_id': cash_id, 'payment_date': '2026-09-04'})
            jep = await db.rahaza_journal_entries.find_one({'source_module': 'ap_payment', 'memo': {'$regex': ap.get('invoice_number', 'x')}}, {'_id': 0})
            check('C01_ap_payment_same_account', jep and [l['account_code'] for l in jep['lines'] if l['debit'] > 0][0] == ap_code_issue, (r.status_code, ap_code_issue, jep and je_lines(jep['lines'])))
    else:
        R['C02_skipped'] = 'tidak ada GR bebas invoice di seed'

    # ── C-04: neraca seimbang dgn 1-1320 (dulu CURRENT_ASSET)
    r = requests.post(f'{A}/rahaza/journals', headers=H, json={'date': '2026-09-04', 'memo': 'FIXTEST-C04 kasbon', 'lines': [
        {'account_code': '1-1320', 'debit': 500000, 'credit': 0, 'description': 'FIXTEST'}, {'account_code': '1-1201', 'debit': 0, 'credit': 500000, 'description': 'FIXTEST'}]})
    jid = r.json().get('id') if r.status_code in (200, 201) else None
    if jid:
        requests.post(f'{A}/rahaza/journals/{jid}/post', headers=H)
    bs = requests.get(f'{A}/rahaza/finance/reports/balance-sheet', headers=H).json()
    check('C04_balance_sheet_balanced', bs.get('balanced') is True, bs.get('totals'))
    check('C04_1-1320_in_assets', any(a['code'] == '1-1320' for a in bs['assets']['accounts']))
    tb = requests.get(f'{A}/rahaza/finance/reports/trial-balance', headers=H).json()
    check('C04_trial_balance_balanced', tb.get('balanced') is True, tb.get('totals'))
    # posting ke akun legacy nonaktif ditolak
    r = requests.post(f'{A}/rahaza/journals', headers=H, json={'date': '2026-09-04', 'memo': 'FIXTEST legacy', 'lines': [
        {'account_code': '1-110', 'debit': 1000, 'credit': 0}, {'account_code': '4-1100', 'debit': 0, 'credit': 1000}]})
    jl = r.json().get('id') if r.status_code in (200, 201) else None
    if jl:
        r = requests.post(f'{A}/rahaza/journals/{jl}/post', headers=H)
    check('H04_legacy_account_rejected', r.status_code >= 400, (r.status_code, r.text[:120]))

    print(json.dumps(R, indent=1, default=str))
    print('FAILED:', FAIL)

    # ── CLEANUP
    new_ids = [i for i in await db.rahaza_journal_entries.distinct('id') if i not in je_ids_before]
    await db.rahaza_journal_lines.delete_many({'je_id': {'$in': new_ids}})
    await db.rahaza_journal_entries.delete_many({'id': {'$in': new_ids}})
    await db.rahaza_journal_lines.delete_many({'$or': [{'description': {'$regex': 'FIXTEST'}}, {'source_ref': {'$regex': f'(ar:|arpay:|bad_debt:){iid}'}}]})
    for coll in ('rahaza_journal_entries', 'rahaza_journal_lines'):
        await db[coll].delete_many({'$or': [
            {'memo': {'$regex': 'FIXTEST'}},
            {'source_ref': {'$regex': f'{iid}'}} if iid else {'_x': 1},
            {'source_ref': {'$regex': f'{ap_id}'}} if ap_id else {'_x': 1},
            {'source_ref': {'$regex': f'maklon_ar:{ar_id}'}} if ar_id else {'_x': 1},
            {'source_module': 'ar_payment', 'memo': {'$regex': 'INV-MK|PO-MK'}},
        ]})
    if iid:
        await db.rahaza_ar_invoices.delete_one({'id': iid})
    if ap_id:
        await db.rahaza_ap_invoices.delete_one({'id': ap_id})
    if gr_created:
        # kembalikan stok & jejak GR uji
        import sys; sys.path.insert(0, '/app/backend')
        from core import stock_service
        try:
            await stock_service.issue(mat['id'], loc['id'], 10, ref={'source': 'fixtest_cleanup'}, actor={'id': 'fixtest'}, db=db)
        except Exception as e:
            print('cleanup stok gagal (abaikan):', e)
        await db.warehouse_receiving.delete_one({'id': gr_created['id']})
        await db.rahaza_material_movements.delete_many({'reference_id': gr_created['id']})
        await db.rahaza_stock_ledger.delete_many({'ref.ref_id': gr_created['id']})
    await db.rahaza_cash_movements.delete_many({'account_id': cash_id})
    if cash_id:
        await db.rahaza_cash_accounts.delete_one({'id': cash_id})
    await db.rahaza_customers.delete_one({'id': cust['id']})
    await db.rahaza_coa_accounts.delete_many({'flags.subledger_entity_id': cust['id']})
    await db.rahaza_coa_accounts.delete_many({'name': {'$regex': 'FIXTEST'}})
    if ar_id:
        await db.dewi_maklon_payments.delete_many({'invoice_id': ar_id})
        await db.dewi_maklon_invoices.delete_many({'order_id': 'po-mk-demo-2'})
        await db.rahaza_ar_invoices.update_one({'id': ar_id}, {'$set': {'status': 'draft', 'gl_posted_at': None, 'gl_je_id': None, 'gl_je_number': None, 'amount_paid': 0.0, 'issued_at': None, 'post_error': None}})
        await db.dewi_maklon_pos.update_one({'id': 'po-mk-demo-2'}, {'$set': {'gl_posted_at': None, 'gl_je_id': None, 'gl_je_number': None, 'post_error': None}})
        requests.post(f'{A}/production-pos/po-mk-demo-2/sync-maklon-finance', headers=H)
    print('JE before', je_before, 'after cleanup', await db.rahaza_journal_entries.count_documents({}), 'lines', await db.rahaza_journal_lines.count_documents({}))

asyncio.run(main())
