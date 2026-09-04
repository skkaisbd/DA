import os, asyncio, json, requests
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
import sys; sys.path.insert(0, '/app/backend')

A='http://localhost:8001/api'; H={'Authorization': f"Bearer {open('/app/.tok_admin').read().strip()}"}
R={}

async def main():
    db=AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    ids0=set(await db.rahaza_journal_entries.distinct('id'))
    # Insert fg_cost_layer
    await db.fg_cost_layers.delete_many({'id':'ly-qa1'})
    await db.fg_cost_layers.insert_one({'id':'ly-qa1','material_id':'m','batch':{'po_id':'po-qa'},'qty_in':10,'unit_cost':45000,'total_cost':450000,'gl_job_id':None})
    from routes.rahaza_posting import post_wip_to_fg_on_job_complete
    job={'id':'job-qa','job_number':'JOB-QA','po_id':'po-qa','completed_at':'2026-09-04'}
    user={'id':'admin','email':'admin@garment.com'}
    r1 = await post_wip_to_fg_on_job_complete(db, job, user)
    R['first_call']=r1
    je=None
    if r1 and r1.get('je_id'):
        je=await db.rahaza_journal_entries.find_one({'id':r1['je_id']},{'_id':0})
    R['je_lines']= je and [(l['account_code'],l['debit'],l['credit'],l.get('description','')) for l in je['lines']]
    layer=await db.fg_cost_layers.find_one({'id':'ly-qa1'},{'_id':0})
    R['layer_gl_job_id']=layer.get('gl_job_id')
    r2 = await post_wip_to_fg_on_job_complete(db, job, user)
    R['second_call']=r2
    # posting-profiles
    pp = requests.get(f'{A}/rahaza/posting-profiles', headers=H).json()
    prof = pp.get('cmt_ap_invoice') if isinstance(pp,dict) else None
    if not prof and isinstance(pp,list):
        prof = next((x for x in pp if x.get('key')=='cmt_ap_invoice'), None)
    R['posting_profile_cmt_ap']=prof
    # balance sheet regression
    bs = requests.get(f'{A}/rahaza/finance/reports/balance-sheet', headers=H).json()
    R['bs_balanced']=bs.get('balanced')
    R['ar_inv_status']=requests.get(f'{A}/rahaza/ar-invoices', headers=H).status_code
    R['mk_inv_status']=requests.get(f'{A}/dewi/maklon/invoices', headers=H).status_code
    print(json.dumps(R,indent=1,default=str))
    # cleanup
    new=[i for i in await db.rahaza_journal_entries.distinct('id') if i not in ids0]
    await db.rahaza_journal_lines.delete_many({'je_id':{'$in':new}})
    await db.rahaza_journal_entries.delete_many({'id':{'$in':new}})
    await db.fg_cost_layers.delete_many({'id':'ly-qa1'})
    print('JE cleanup done, remaining:', await db.rahaza_journal_entries.count_documents({}))
asyncio.run(main())
