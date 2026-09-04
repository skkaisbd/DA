import os, asyncio, json, requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
A='http://localhost:8001/api'; H={'Authorization': f"Bearer {open('/app/.tok_admin').read().strip()}", 'Content-Type':'application/json'}
R={}
async def main():
    db=AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    ids0=set(await db.rahaza_journal_entries.distinct('id'))
    # cash account
    r=requests.post(f'{A}/rahaza/cash-accounts',headers=H,json={'code':'T2-BANK','name':'T2 Bank','type':'bank','gl_account_code':'1-1201','opening_balance':0}); cash=r.json(); cid=cash['id']
    # internal AR
    await db.rahaza_customers.update_one({'id':'t2-cust'},{'$set':{'id':'t2-cust','name':'T2 Cust','code':'T2C','active':True}},upsert=True)
    r=requests.post(f'{A}/rahaza/ar-invoices',headers=H,json={'customer_id':'t2-cust','customer_name':'T2 Cust','items':[{'description':'x','qty':1,'unit_price':50000}],'tax_pct':0,'due_date':'2026-07-01'}); inv=r.json(); iid=inv['id']
    requests.post(f'{A}/rahaza/ar-invoices/{iid}/send',headers=H,json={})
    d=await db.rahaza_ar_invoices.find_one({'id':iid},{'_id':0}); R['ar_internal_fields']={k:d.get(k) for k in ('status','total','total_amount','amount_due','balance')}
    requests.post(f'{A}/rahaza/ar-invoices/{iid}/payment',headers=H,json={'amount':20000,'account_id':cid,'payment_date':'2026-09-04'})
    d=await db.rahaza_ar_invoices.find_one({'id':iid},{'_id':0}); R['ar_internal_after_pay']={k:d.get(k) for k in ('status','paid_amount','amount_paid','amount_due','balance')}
    # maklon invoice
    r=requests.post(f'{A}/dewi/maklon/invoices/generate',headers=H,json={'order_id':'po-mk-demo-2','tax_pct':11}); mk=r.json(); R['mk_gen']=(r.status_code, mk.get('total_amount'))
    ag=requests.get(f'{A}/rahaza/ar-aging',headers=H).json()
    R['aging_unified']={'total':ag['total'],'count':ag['count'],'rows':[(x['invoice_number'],x['source'],x['status'],x['amount_due'],x['bucket']) for x in ag['details']]}
    agm=requests.get(f'{A}/dewi/maklon/reports/aging',headers=H).json(); R['aging_maklon']={'total':agm.get('total'),'rows':[(x['invoice_number'],x['balance_amount'],x['status']) for x in agm['rows']]}
    agi=requests.get(f'{A}/rahaza/ar-aging?source=internal',headers=H).json(); R['aging_internal_total']=agi['total']
    # CMT payment: create a synthetic internal CMT bill
    pid='t2-cmt-pay-1'
    await db.dewi_cmt_payments.delete_many({'id':pid})
    await db.dewi_cmt_payments.insert_one({'id':pid,'payment_code':'PAY-CMT-T2','cmt_name':'T2 Vendor','cmt_partner_id':'','vendor_id':'','po_id':'po-int-demo-2','subtotal':300000.0,'total_penalty':0.0,'net_amount':300000.0,'total_amount':300000.0,'status':'draft','payment_date':'2026-09-04'})
    r=requests.post(f'{A}/dewi/maklon/finance/cmt-payments/{pid}/pay',headers=H,json={'cash_account_id':cid,'amount':100000,'payment_date':'2026-09-04','reference_no':'TF1'}); p1=r.json(); R['cmt_pay1']=(r.status_code,p1.get('gl_je_number'),p1.get('payment_status'),p1.get('post_error'))
    ap=await db.rahaza_journal_entries.find_one({'source_module':'cmt_ap_invoice','source_ref':f'cmt_ap:{pid}'},{'_id':0}); R['cmt_ap_je']=ap and [(l['account_code'],l['debit'],l['credit']) for l in ap['lines']]
    pj=await db.rahaza_journal_entries.find_one({'source_module':'ap_payment','source_ref':{'$regex':f"appay:{p1.get('id')}"}},{'_id':0}); R['cmt_pay_je']=pj and [(l['account_code'],l['debit'],l['credit']) for l in pj['lines']]
    r=requests.post(f'{A}/dewi/maklon/finance/cmt-payments/{pid}/pay',headers=H,json={'cash_account_id':cid}); p2=r.json(); R['cmt_pay2_rest']=(r.status_code,p2.get('amount'),p2.get('payment_status'))
    r=requests.post(f'{A}/dewi/maklon/finance/cmt-payments/{pid}/pay',headers=H,json={'cash_account_id':cid}); R['cmt_pay3_overpay']=(r.status_code,r.text[:80])
    r=requests.post(f'{A}/dewi/maklon/finance/cmt-payments/{pid}/disbursements/{p1["id"]}/void',headers=H); R['cmt_void']=(r.status_code,r.json())
    pd=await db.dewi_cmt_payments.find_one({'id':pid},{'_id':0}); R['cmt_after']={k:pd.get(k) for k in ('status','paid_amount','outstanding_amount')}
    ca=await db.rahaza_cash_accounts.find_one({'id':cid},{'_id':0}); R['cash_balance']=ca.get('balance')
    lst=requests.get(f'{A}/production/cmt-billing?business_type=internal',headers=H); R['cmt_billing_list']=lst.status_code
    ag2=requests.get(f'{A}/rahaza/ap-aging',headers=H); R['ap_aging']=ag2.status_code
    print(json.dumps(R,indent=1,default=str))
    # cleanup
    new=[i for i in await db.rahaza_journal_entries.distinct('id') if i not in ids0]
    await db.rahaza_journal_lines.delete_many({'je_id':{'$in':new}}); await db.rahaza_journal_entries.delete_many({'id':{'$in':new}})
    await db.rahaza_ar_invoices.delete_one({'id':iid}); await db.rahaza_cash_movements.delete_many({'account_id':cid}); await db.rahaza_cash_accounts.delete_one({'id':cid})
    await db.rahaza_coa_accounts.delete_many({'$or':[{'code':{'$regex':'T2-BANK'}},{'flags.subledger_entity_id':'t2-cust'}]}); await db.rahaza_customers.delete_one({'id':'t2-cust'}); await db.dewi_cmt_payments.delete_many({'id':pid}); await db.dewi_cmt_disbursements.delete_many({'payment_id':pid})
    ar_id=(await db.dewi_maklon_pos.find_one({'id':'po-mk-demo-2'},{'_id':0}))['ar_invoice_id']
    await db.dewi_maklon_payments.delete_many({'invoice_id':ar_id}); await db.dewi_maklon_invoices.delete_many({'order_id':'po-mk-demo-2'})
    await db.rahaza_ar_invoices.update_one({'id':ar_id},{'$set':{'status':'draft','gl_posted_at':None,'gl_je_id':None,'gl_je_number':None,'amount_paid':0.0,'issued_at':None,'post_error':None}})
    await db.dewi_maklon_pos.update_one({'id':'po-mk-demo-2'},{'$set':{'gl_posted_at':None,'gl_je_id':None,'gl_je_number':None,'post_error':None}})
    requests.post(f'{A}/production-pos/po-mk-demo-2/sync-maklon-finance',headers=H)
    print('JE left',await db.rahaza_journal_entries.count_documents({}))
asyncio.run(main())
