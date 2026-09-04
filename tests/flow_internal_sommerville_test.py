"""POC Fase 3 — Produksi Internal (same base SOMMERVILLE + adapters E10).

AC yang diuji end-to-end via API (localhost:8001):
  1. PO internal (model rahaza_models, ACC-1 auto-explode) → Confirmed → job →
     MI draft → gudang confirm (stok SSOT turun + JE) → progress (operator+process →
     mirror wip, bukti payroll pcs) → job Completed → JE WIP→FG → dispatch → JE COGS.
  2. HPP snapshot anchor job_id, angka konsisten (material+labor+overhead AD-2).
  3. Guards: progress tanpa MI issued → 400; model_id invalid → 400; state machine.
  4. MKT-1 from-order + MKT-2 catalog model_id FK. allowed_next di detail PO.
Self-cleanup penuh (fixtures pymongo bertanda poc-int-*).
"""
import datetime
import os
import sys
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

API = os.environ.get('API_URL', 'http://localhost:8001')
ENV = dotenv_values('/app/backend/.env')
mdb = MongoClient(ENV['MONGO_URL'].strip('"'))[ENV['DB_NAME'].strip('"')]

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILED.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def login(email, password):
    r = requests.post(f"{API}/api/auth/login", json={'email': email, 'password': password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:150]}"
    return r.json()['token']


def H(tok):
    return {'Authorization': f'Bearer {tok}'}


MODEL_ID = 'poc-int-model-1'
ORDER_ID = 'poc-int-order-1'
CAT_ID = 'poc-int-cat-1'
EMP_ID = 'poc-int-emp-1'
LOC_ID = None
PO_NUMBER = 'PO-INT-POC-001'
NOWTS = datetime.datetime.now(datetime.timezone.utc)

state = {'created_settings': False, 'created_loc': False, 'po_ids': [], 'job_id': None,
         'mat_ids': [], 'mi_id': None, 'bs_id': None}


def setup_fixtures(admin):
    global LOC_ID
    sizes = requests.get(f"{API}/api/rahaza/sizes?active=true&limit=5", headers=H(admin), timeout=15).json()
    sizes = sizes if isinstance(sizes, list) else sizes.get('items', [])
    assert sizes, 'tidak ada master size'
    size_id = sizes[0]['id']
    size_code = sizes[0].get('code', '')

    mdb.rahaza_models.delete_many({'id': MODEL_ID})
    mdb.rahaza_models.insert_one({
        'id': MODEL_ID, 'code': 'ZZ-POCINT', 'name': 'Kaos Internal POC',
        'bundle_size': 30, 'active': True, 'created_by': 'poc-int', 'created_at': NOWTS,
    })
    mdb.rahaza_boms.delete_many({'model_id': MODEL_ID})
    mdb.rahaza_boms.insert_one({
        'id': 'poc-int-bom-1', 'model_id': MODEL_ID, 'size_id': size_id,
        'version': 1, 'is_active': True, 'active': True,
        'yarn_materials': [{'name': 'Benang POC Internal', 'code': 'YRN-POCINT', 'yarn_type': 'cotton', 'qty_kg': 0.2}],
        'accessory_materials': [{'name': 'Label POC Internal', 'code': 'ACC-POCINT', 'qty': 2, 'unit': 'pcs'}],
        'created_by': 'poc-int', 'created_at': NOWTS,
    })
    loc = mdb.rahaza_locations.find_one({'active': {'$ne': False}})
    if loc:
        LOC_ID = loc['id']
    else:
        LOC_ID = 'poc-int-loc-1'
        state['created_loc'] = True
        mdb.rahaza_locations.insert_one({'id': LOC_ID, 'code': 'POC-LOC', 'name': 'Lokasi POC', 'active': True, 'created_at': NOWTS})
    if not mdb.rahaza_costing_settings.find_one({'id': 'GLOBAL'}):
        state['created_settings'] = True
        mdb.rahaza_costing_settings.insert_one({
            'id': 'GLOBAL', 'overhead_rate_per_pcs': 1000,
            'default_yarn_cost_per_kg': 0, 'default_accessory_cost_per_unit': 0,
            'labor_rate_fallback_per_pcs': 0,
        })
    # operator + payroll profile pcs (fixture sendiri agar deterministik)
    mdb.rahaza_employees.delete_many({'id': EMP_ID})
    mdb.rahaza_payroll_profiles.delete_many({'employee_id': EMP_ID})
    mdb.rahaza_employees.insert_one({'id': EMP_ID, 'name': 'Operator POC Internal', 'active': True,
                                     'employment_type': 'daily', 'created_at': NOWTS})
    mdb.rahaza_payroll_profiles.insert_one({
        'id': 'poc-int-prof-1', 'employee_id': EMP_ID, 'pay_scheme': 'pcs',
        'base_rate': 500, 'pcs_process_rates': [], 'active': True, 'created_at': NOWTS,
    })
    proc = mdb.rahaza_processes.find_one({'active': {'$ne': False}})
    assert proc, 'tidak ada master proses rahaza'
    return size_id, size_code, proc['id']


def cleanup(admin):
    for pid in state['po_ids']:
        requests.delete(f"{API}/api/production-pos/{pid}", headers=H(admin), timeout=30)
    mdb.rahaza_models.delete_many({'id': MODEL_ID})
    mdb.rahaza_boms.delete_many({'model_id': MODEL_ID})
    mats = list(mdb.rahaza_materials.find({'code': {'$in': ['YRN-POCINT', 'ACC-POCINT']}}))
    mat_ids = [m['id'] for m in mats]
    mdb.rahaza_materials.delete_many({'id': {'$in': mat_ids}})
    mdb.rahaza_material_stock.delete_many({'material_id': {'$in': mat_ids}})
    mdb.rahaza_material_movements.delete_many({'material_id': {'$in': mat_ids}})
    if state['job_id']:
        mdb.rahaza_material_issues.delete_many({'job_id': state['job_id']})
        mdb.rahaza_wip_events.delete_many({'job_id': state['job_id']})
        mdb.rahaza_hpp_snapshots.delete_many({'job_id': state['job_id']})
    mdb.rahaza_journal_entries.delete_many({'source_ref': {'$regex': '^(wip_fg_job:|cogs_job:|mi:poc|payroll)'},
                                            'description': {'$regex': 'POC|poc-int|PO-INT-POC'}})
    if state['mi_id']:
        mdb.rahaza_journal_entries.delete_many({'source_ref': f"mi:{state['mi_id']}"})
    mdb.rahaza_orders.delete_many({'id': ORDER_ID})
    mdb.marketing_catalogs.delete_many({'id': CAT_ID})
    mdb.marketing_catalog_items.delete_many({'catalog_id': CAT_ID})
    mdb.rahaza_employees.delete_many({'id': EMP_ID})
    mdb.rahaza_payroll_profiles.delete_many({'employee_id': EMP_ID})
    run_ids = [r_['id'] for r_ in mdb.rahaza_payroll_runs.find({'notes': 'poc-int payroll evidence'}, {'id': 1})]
    if run_ids:
        mdb.rahaza_payslips.delete_many({'run_id': {'$in': run_ids}})
    mdb.rahaza_payroll_runs.delete_many({'notes': 'poc-int payroll evidence'})
    if state['created_loc']:
        mdb.rahaza_locations.delete_many({'id': LOC_ID})
    if state['created_settings']:
        mdb.rahaza_costing_settings.delete_many({'id': 'GLOBAL'})
    print('  cleanup selesai (fixtures poc-int-* dihapus)')


def main():
    admin = login('admin@garment.com', 'Admin@123')
    size_id, size_code, process_id = setup_fixtures(admin)
    settings = mdb.rahaza_costing_settings.find_one({'id': 'GLOBAL'}) or {}
    overhead_rate = float(settings.get('overhead_rate_per_pcs') or 0)
    print(f"== Fixtures siap (size={size_code}, loc={LOC_ID}, overhead_rate={overhead_rate}) ==")

    # cleanup PO leftover
    r = requests.get(f"{API}/api/production-pos", headers=H(admin), params={'search': 'PO-INT-POC'}, timeout=15)
    for po in (r.json() if r.status_code == 200 else []):
        if str(po.get('po_number', '')).startswith('PO-INT'):
            requests.delete(f"{API}/api/production-pos/{po['id']}", headers=H(admin), timeout=30)

    # ── AC-3: model_id invalid / hilang ──
    print("== D3: validasi model FK ==")
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': 'PO-INT-BAD-1', 'business_type': 'internal',
        'items': [{'model_id': 'tidak-ada', 'size_id': size_id, 'qty': 5}]}, timeout=15)
    check('PO internal model_id invalid → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': 'PO-INT-BAD-2', 'business_type': 'internal',
        'items': [{'size_id': size_id, 'qty': 5}]}, timeout=15)
    check('PO internal tanpa model_id → 400', r.status_code == 400, str(r.status_code))
    check('PO yatim tidak tertinggal', mdb.production_pos.count_documents({'po_number': {'$in': ['PO-INT-BAD-1', 'PO-INT-BAD-2']}}) == 0)

    # ── AC-1: create PO internal + ACC-1 ──
    print("== PO internal + auto-explode aksesoris (ACC-1) ==")
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PO_NUMBER, 'business_type': 'internal', 'customer_name': 'Gudang FG Sendiri',
        'items': [{'model_id': MODEL_ID, 'size_id': size_id, 'qty': 10, 'color': 'Hitam', 'serial_number': 'SN-INT-1'}],
    }, timeout=15)
    check('create PO internal 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    po = r.json()
    po_id = po['id']
    state['po_ids'].append(po_id)
    item = po['items'][0]
    check('snapshot dari model (name+sku)', item.get('product_name') == 'Kaos Internal POC'
          and item.get('sku') == f"ZZ-POCINT-{size_code}", f"{item.get('product_name')}/{item.get('sku')}")
    accs = requests.get(f"{API}/api/po-accessories", headers=H(admin), params={'po_id': po_id}, timeout=15).json()
    acc_row = next((a for a in accs if a.get('accessory_code') == 'ACC-POCINT'), None)
    check('ACC-1: po_accessories auto dari BOM (2×10=20, source bom_auto)',
          acc_row is not None and acc_row.get('qty_needed') == 20 and acc_row.get('source') == 'bom_auto',
          str(acc_row))

    # allowed_next (improvement)
    det = requests.get(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=15).json()
    check("allowed_next di detail PO = ['Confirmed'] + can_close False",
          det.get('allowed_next') == ['Confirmed'] and det.get('can_close') is False,
          f"{det.get('allowed_next')}/{det.get('can_close')}")

    r = requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    check('PO → Confirmed', r.status_code == 200, str(r.status_code))

    # ── Job internal (tanpa vendor shipment) + MI draft otomatis (GDG-2) ──
    print("== Job internal + MI draft-from-job (GDG-2) ==")
    r = requests.post(f"{API}/api/production-jobs", headers=H(admin), json={'po_id': po_id}, timeout=15)
    check('create job internal 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    job = r.json()
    job_id = job['id']
    state['job_id'] = job_id
    ji = job['items'][0]
    check('job business_type=internal + vendor "Produksi Internal"',
          job.get('business_type') == 'internal' and job.get('vendor_name') == 'Produksi Internal',
          f"{job.get('business_type')}/{job.get('vendor_name')}")
    mi = job.get('material_issue_draft') or {}
    state['mi_id'] = mi.get('id')
    check('MI draft otomatis tergenerate (2 material, anchor job_id)',
          mi.get('status') == 'draft' and mi.get('job_id') == job_id and len(mi.get('items', [])) == 2,
          str({k: mi.get(k) for k in ('status', 'job_id', 'mi_number')}))
    qty_map = {}
    for it_ in mi.get('items', []):
        mat = mdb.rahaza_materials.find_one({'id': it_['material_id']}) or {}
        qty_map[mat.get('code')] = it_['qty_required']
    check('kebutuhan BOM benar (yarn 2.0 kg, acc 20 pcs)',
          qty_map.get('YRN-POCINT') == 2.0 and qty_map.get('ACC-POCINT') == 20.0, str(qty_map))
    r = requests.get(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=15)
    check('PO → In Production', r.json().get('status') == 'In Production', r.json().get('status'))
    r = requests.post(f"{API}/api/production-jobs", headers=H(admin), json={'po_id': po_id}, timeout=15)
    check('job duplikat utk PO sama → 400', r.status_code == 400, str(r.status_code))

    # ── AC-3: progress SEBELUM material issued → 400 ──
    r = requests.post(f"{API}/api/production-progress", headers=H(admin),
                      json={'job_item_id': ji['id'], 'completed_quantity': 3}, timeout=15)
    check('GDG-2 gate: progress tanpa MI issued → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # ── Gudang: unit_cost + stok, lalu confirm MI → stok SSOT turun + JE ──
    print("== Gudang confirm MI → stok turun + JE inventory issue ==")
    mats = {m['code']: m for m in mdb.rahaza_materials.find({'code': {'$in': ['YRN-POCINT', 'ACC-POCINT']}})}
    mdb.rahaza_materials.update_one({'id': mats['YRN-POCINT']['id']}, {'$set': {'unit_cost': 20000}})
    mdb.rahaza_materials.update_one({'id': mats['ACC-POCINT']['id']}, {'$set': {'unit_cost': 500}})
    for m in mats.values():
        mdb.rahaza_material_stock.update_one(
            {'material_id': m['id'], 'location_id': LOC_ID},
            {'$set': {'qty': 999.0, 'updated_at': NOWTS}, '$setOnInsert': {'id': uuid.uuid4().hex}}, upsert=True)
    overrides = {m['id']: LOC_ID for m in mats.values()}
    r = requests.post(f"{API}/api/rahaza/material-issues/{state['mi_id']}/confirm", headers=H(admin),
                      json={'location_overrides': overrides}, timeout=30)
    check('MI confirm oleh gudang → issued', r.status_code == 200 and r.json().get('status') == 'issued',
          f"{r.status_code} {r.text[:150]}")
    post_res = (r.json() or {}).get('_posting_result') or {}
    check('JE inventory issue terposting (mi:{id})', bool(post_res.get('ok')), str(post_res)[:120])
    stok_yarn = mdb.rahaza_material_stock.find_one({'material_id': mats['YRN-POCINT']['id'], 'location_id': LOC_ID})
    stok_acc = mdb.rahaza_material_stock.find_one({'material_id': mats['ACC-POCINT']['id'], 'location_id': LOC_ID})
    check('stok SSOT berkurang (999→997.0 kg, 999→979 pcs)',
          stok_yarn['qty'] == 997.0 and stok_acc['qty'] == 979.0, f"{stok_yarn['qty']}/{stok_acc['qty']}")

    # ── HR-1: progress + operator+process → mirror wip ──
    print("== Progress + mirror wip_events (HR-1) ==")
    r = requests.post(f"{API}/api/production-progress", headers=H(admin),
                      json={'job_item_id': ji['id'], 'completed_quantity': 3, 'operator_id': 'tidak-ada', 'process_id': process_id}, timeout=15)
    check('operator_id invalid → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(admin),
                      json={'job_item_id': ji['id'], 'completed_quantity': 3, 'operator_id': EMP_ID}, timeout=15)
    check('operator tanpa process → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(admin),
                      json={'job_item_id': ji['id'], 'completed_quantity': 6, 'operator_id': EMP_ID, 'process_id': process_id}, timeout=15)
    check('progress +6 dengan operator → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    ev = mdb.rahaza_wip_events.find_one({'job_id': job_id})
    check('wip event mirror: employee_id+complete+qty_done+rate (payroll shape)',
          ev is not None and ev.get('employee_id') == EMP_ID and ev.get('event_type') == 'complete'
          and ev.get('qty_done') == 6 and ev.get('rate_per_pcs') == 500.0 and ev.get('work_order_id') is None,
          str({k: (ev or {}).get(k) for k in ('employee_id', 'event_type', 'qty_done', 'rate_per_pcs')}))
    r = requests.post(f"{API}/api/production-progress", headers=H(admin),
                      json={'job_item_id': ji['id'], 'completed_quantity': 5, 'operator_id': EMP_ID, 'process_id': process_id}, timeout=15)
    check('I-1: progress 6+5 > 10 → 400', r.status_code == 400, str(r.status_code))

    # ── Selesaikan job → AD-3 hook (HPP snapshot + WIP→FG) ──
    print("== Job Completed → HPP snapshot + JE WIP→FG (AD-3) ==")
    r = requests.post(f"{API}/api/production-progress", headers=H(admin),
                      json={'job_item_id': ji['id'], 'completed_quantity': 4, 'operator_id': EMP_ID, 'process_id': process_id}, timeout=30)
    check('progress +4 (total 10) → 201, job Completed', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    hook = (r.json() or {}).get('job_completed_hook') or {}
    wipfg = hook.get('wip_to_fg') or {}
    check('hook WIP→FG terposting (JE)', bool(wipfg.get('ok')) and bool(wipfg.get('je_number')), str(wipfg)[:150])
    job_after = mdb.production_jobs.find_one({'id': job_id})
    check('job status Completed', (job_after or {}).get('status') == 'Completed', str((job_after or {}).get('status')))

    # ── AC-2: HPP snapshot anchor job, angka konsisten ──
    print("== HPP per job (FIN-1/E10, AD-2) ==")
    hpp = requests.get(f"{API}/api/production-jobs/{job_id}/hpp", headers=H(admin), timeout=15).json()
    exp_material = 2.0 * 20000 + 20 * 500      # 50000
    exp_labor = 10 * 500                        # 5000
    exp_overhead = 10 * overhead_rate
    exp_total = exp_material + exp_labor + exp_overhead
    check('HPP material 50.000 | labor 5.000 | overhead sesuai rate',
          hpp.get('material_cost') == exp_material and hpp.get('labor_cost') == exp_labor
          and hpp.get('overhead_cost') == exp_overhead,
          f"m={hpp.get('material_cost')} l={hpp.get('labor_cost')} o={hpp.get('overhead_cost')} (exp {exp_material}/{exp_labor}/{exp_overhead})")
    check('HPP unit = total/produced', hpp.get('hpp_unit') == round(exp_total / 10), f"{hpp.get('hpp_unit')} vs {round(exp_total/10)}")
    snap = mdb.rahaza_hpp_snapshots.find_one({'job_id': job_id})
    check('snapshot tersimpan anchor job_id', snap is not None and snap.get('total_cost') == exp_total,
          str((snap or {}).get('total_cost')))
    je_wip = mdb.rahaza_journal_entries.find_one({'source_module': 'production_job', 'source_ref': f'wip_fg_job:{job_id}'})
    je_mi = mdb.rahaza_journal_entries.find_one({'source_module': 'inventory_issue', 'source_ref': f"mi:{state['mi_id']}"})
    check('JE WIP→FG = nilai JE material issue (basis MI)',
          je_wip is not None and je_mi is not None and je_wip.get('total_debit') == je_mi.get('total_debit'),
          f"wip={(je_wip or {}).get('total_debit')} mi={(je_mi or {}).get('total_debit')}")

    # ── Fulfillment → COGS (FIN-1) ──
    print("== Fulfillment dispatch → JE COGS ==")
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id,
        'items': [{'po_item_id': item['id'], 'job_item_id': ji['id'], 'ordered_qty': 10, 'qty_shipped': 6}]}, timeout=30)
    check('dispatch #1 (6 pcs) → 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    bs = r.json()
    state['bs_id'] = bs.get('id')
    cogs = bs.get('cogs_posting') or {}
    exp_cogs1 = round(hpp.get('hpp_unit', 0) * 6)
    check('COGS posting ok, amount = 6 × hpp_unit', bool(cogs.get('ok')) and round(cogs.get('amount', 0)) == exp_cogs1,
          f"{cogs.get('amount')} vs {exp_cogs1}")
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id,
        'items': [{'po_item_id': item['id'], 'job_item_id': ji['id'], 'ordered_qty': 10, 'qty_shipped': 4}]}, timeout=30)
    cogs2 = (r.json() or {}).get('cogs_posting') or {}
    check('dispatch #2 (4 pcs) → COGS seq2 terpisah', r.status_code == 200 and bool(cogs2.get('ok'))
          and not cogs2.get('already_posted'), str(cogs2)[:120])
    n_cogs = mdb.rahaza_journal_entries.count_documents({'source_module': 'buyer_dispatch',
                                                         'source_ref': {'$regex': f"^cogs_job:{state['bs_id']}"}})
    check('2 JE COGS (per dispatch, idempoten per seq)', n_cogs == 2, str(n_cogs))

    # ── Bukti payroll pcs membaca mirror ──
    print("== Payroll pcs evidence ==")
    today = datetime.date.today().isoformat()
    r = requests.post(f"{API}/api/rahaza/payroll-runs", headers=H(admin), json={
        'period_from': today, 'period_to': today, 'employee_ids': [EMP_ID], 'notes': 'poc-int payroll evidence'}, timeout=30)
    slip = None
    if r.status_code == 200:
        run = r.json()
        rd = requests.get(f"{API}/api/rahaza/payroll-runs/{run.get('id')}", headers=H(admin), timeout=30)
        slips = (rd.json() or {}).get('payslips') or [] if rd.status_code == 200 else []
        slip = next((s_ for s_ in slips if s_.get('employee_id') == EMP_ID), None)
    pcs_amount = 0
    if slip:
        for e_ in (slip.get('earnings') or []):
            if e_.get('type') == 'pcs':
                pcs_amount += float(e_.get('amount') or 0)
    check('payroll run: earnings pcs operator = 10 × 500 = 5.000', pcs_amount == 5000.0,
          f"{r.status_code} pcs={pcs_amount}")

    # ── MKT-1: from-order + MKT-2 catalog FK ──
    print("== MKT-1 from-order & MKT-2 catalog FK ==")
    mdb.rahaza_orders.delete_many({'id': ORDER_ID})
    mdb.rahaza_orders.insert_one({
        'id': ORDER_ID, 'order_number': 'ORD-POCINT-1', 'status': 'confirmed',
        'customer_id': None, 'customer_name_snapshot': 'Customer POC',
        'items': [{'model_id': MODEL_ID, 'size_id': size_id, 'qty': 5}],
        'created_at': NOWTS,
    })
    r = requests.post(f"{API}/api/production-pos/from-order/{ORDER_ID}", headers=H(admin), json={}, timeout=15)
    check('from-order → PO internal Draft 201', r.status_code == 201, f"{r.status_code} {r.text[:180]}")
    po2 = r.json() if r.status_code == 201 else {}
    if po2.get('id'):
        state['po_ids'].append(po2['id'])
    check('item dari order (model snapshot, qty 5) + accessories explode',
          po2.get('business_type') == 'internal' and po2.get('items', [{}])[0].get('qty') == 5
          and (po2.get('accessories_explode') or {}).get('rows', 0) >= 1,
          str(po2.get('accessories_explode')))
    r = requests.post(f"{API}/api/production-pos/from-order/{ORDER_ID}", headers=H(admin), json={}, timeout=15)
    check('from-order duplikat → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-pos/{po2['id']}/status", headers=H(admin), json={'status': 'Closed'}, timeout=15)
    check('state machine berlaku juga utk PO internal (Draft→Closed → 400)', r.status_code == 400, str(r.status_code))

    mdb.marketing_catalogs.delete_many({'id': CAT_ID})
    mdb.marketing_catalogs.insert_one({'id': CAT_ID, 'name': 'Katalog POC', 'account_id': 'poc', 'platform': 'shopee',
                                       'active': True, 'created_at': NOWTS})
    r = requests.post(f"{API}/api/marketing/catalogs/{CAT_ID}/items", headers=H(admin), json={
        'sku': 'POC-CAT-1', 'name': 'Item POC', 'price': 100000, 'model_id': 'tidak-ada'}, timeout=15)
    check('MKT-2: catalog item model_id invalid → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")
    r = requests.post(f"{API}/api/marketing/catalogs/{CAT_ID}/items", headers=H(admin), json={
        'sku': 'POC-CAT-1', 'name': 'Item POC', 'price': 100000, 'model_id': MODEL_ID}, timeout=15)
    check('MKT-2: catalog item model_id valid → 201 + tersimpan',
          r.status_code == 201 and (mdb.marketing_catalog_items.find_one({'catalog_id': CAT_ID}) or {}).get('model_id') == MODEL_ID,
          f"{r.status_code} {r.text[:120]}")

    print("== Cleanup ==")
    cleanup(admin)

    print(f"\n===== HASIL FASE 3: {PASS} PASS / {FAIL} FAIL =====")
    for f_ in FAILED:
        print(f"  ✗ {f_}")
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    try:
        main()
    except SystemExit:
        raise
    except Exception as e:
        print(f"\nFATAL: {e}")
        try:
            admin = login('admin@garment.com', 'Admin@123')
            cleanup(admin)
        except Exception as e2:
            print(f"cleanup gagal: {e2}")
        sys.exit(2)
