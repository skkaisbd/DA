"""Audit read-only: integritas GL, cermin baris, COA, rekonsiliasi AR/AP vs GL, cash ledger.
Jalankan: cd /app/backend && python3 scripts/audit_finance_integrity.py
"""
import os, asyncio, json
from collections import defaultdict
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')


async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    out = {}
    jes = await db.rahaza_journal_entries.find({}, {'_id': 0}).to_list(None)
    lines = await db.rahaza_journal_lines.find({}, {'_id': 0}).to_list(None)
    coa = {a['code']: a for a in await db.rahaza_coa_accounts.find({}, {'_id': 0}).to_list(None)}
    out['counts'] = {'je': len(jes), 'lines': len(lines), 'coa': len(coa),
                     'je_by_status': dict(__import__('collections').Counter(j.get('status') for j in jes)),
                     'je_by_source': dict(__import__('collections').Counter(j.get('source_module') for j in jes))}

    # 1) JE seimbang?
    unbalanced = [j['je_number'] for j in jes if round(sum(l['debit'] for l in j['lines']), 2) != round(sum(l['credit'] for l in j['lines']), 2)]
    out['unbalanced_je'] = unbalanced

    # 2) Cermin baris vs entri posted
    posted_ids = {j['id'] for j in jes if j.get('status') == 'posted'}
    lines_by_je = defaultdict(list)
    for l in lines:
        lines_by_je[l['je_id']].append(l)
    missing_mirror = [j['je_number'] for j in jes if j.get('status') == 'posted' and j['id'] not in lines_by_je]
    orphan_mirror = sorted({l['je_id'] for l in lines if l['je_id'] not in posted_ids})
    dup_mirror = [j['je_number'] for j in jes if j.get('status') == 'posted' and len(lines_by_je.get(j['id'], [])) != len([x for x in j['lines'] if (x['debit'] or x['credit'])])]
    out['mirror'] = {'posted_without_mirror': missing_mirror, 'mirror_for_nonposted_or_missing_je': orphan_mirror, 'mirror_count_mismatch': dup_mirror}

    # 3) Akun tidak ada / grup / nonaktif
    bad_acc = defaultdict(list)
    for l in lines:
        a = coa.get(l['account_code'])
        if not a:
            bad_acc['missing'].append(l['account_code'])
        elif a.get('is_group'):
            bad_acc['group'].append(l['account_code'])
        elif not a.get('active', True):
            bad_acc['inactive'].append(l['account_code'])
    out['bad_accounts_in_lines'] = {k: sorted(set(v)) for k, v in bad_acc.items()}
    # tipe akun di baris vs master
    type_drift = sorted({l['account_code'] for l in lines if coa.get(l['account_code']) and coa[l['account_code']].get('type') != l.get('account_type')})
    out['account_type_drift_in_mirror'] = type_drift

    # 4) Duplikat source_ref aktif
    seen = defaultdict(list)
    for j in jes:
        if j.get('status') != 'voided':
            seen[(j.get('source_module'), j.get('source_ref'))].append(j['je_number'])
    out['duplicate_active_source_ref'] = {f'{k[0]}|{k[1]}': v for k, v in seen.items() if len(v) > 1}

    # 5) TB balanced (dari mirror)
    td = round(sum(l['debit'] for l in lines), 2); tc = round(sum(l['credit'] for l in lines), 2)
    out['mirror_totals'] = {'debit': td, 'credit': tc, 'balanced': td == tc}

    # 6) COA sanity
    out['coa_issues'] = {
        'no_type': [c for c, a in coa.items() if not a.get('type')],
        'no_normal_balance': [c for c, a in coa.items() if not a.get('normal_balance')],
        'type_normal_mismatch': [c for c, a in coa.items() if a.get('type') in ('ASSET', 'EXPENSE', 'COGS', 'OTHER_EXPENSE') and a.get('normal_balance') != 'DEBIT'
                                 or a.get('type') in ('LIABILITY', 'EQUITY', 'REVENUE', 'OTHER_INCOME') and a.get('normal_balance') != 'CREDIT'],
        'parent_missing': [c for c, a in coa.items() if a.get('parent_code') and a['parent_code'] not in coa],
    }

    # 7) Mapping posting profile → akun ada?
    profs = await db.rahaza_posting_profiles.find({}, {'_id': 0}).to_list(None)
    prof_bad = {}
    for p in profs:
        m = p.get('mapping') or {}
        bad = {k: v for k, v in m.items() if v and (v not in coa or coa[v].get('is_group') or not coa[v].get('active', True))}
        if bad:
            prof_bad[p['event_type']] = bad
    out['posting_profile_bad_accounts'] = prof_bad
    out['posting_profiles'] = {p['event_type']: {'active': p.get('active'), 'mapping': p.get('mapping')} for p in profs}

    # 8) AR issued/paid vs GL posted
    ars = await db.rahaza_ar_invoices.find({}, {'_id': 0}).to_list(None)
    ar_stats = defaultdict(int)
    ar_not_posted = []
    ar_paid_mismatch = []
    for a in ars:
        ar_stats[a.get('status')] += 1
        if a.get('status') in ('issued', 'partial_paid', 'paid', 'overdue') and not a.get('gl_je_id'):
            ar_not_posted.append((a.get('invoice_number'), a.get('status'), a.get('source_module'), a.get('post_error')))
        due = round(float(a.get('total_amount') or a.get('total') or 0) - float(a.get('amount_paid') or 0), 2)
        if a.get('amount_due') is not None and round(float(a.get('amount_due')), 2) != due:
            ar_paid_mismatch.append((a.get('invoice_number'), a.get('amount_due'), due))
    out['ar'] = {'status': dict(ar_stats), 'issued_not_gl_posted': ar_not_posted[:30], 'amount_due_mismatch': ar_paid_mismatch[:20],
                 'fields_total_variants': dict(__import__('collections').Counter(str(('total_amount' in a, 'total' in a)) for a in ars))}
    aps = await db.rahaza_ap_invoices.find({}, {'_id': 0}).to_list(None)
    ap_stats = defaultdict(int); ap_not_posted = []
    for a in aps:
        ap_stats[a.get('status')] += 1
        if a.get('status') in ('issued', 'partial_paid', 'paid', 'approved', 'overdue') and not a.get('gl_je_id'):
            ap_not_posted.append((a.get('invoice_number'), a.get('status'), a.get('source_module'), a.get('post_error')))
    out['ap'] = {'status': dict(ap_stats), 'issued_not_gl_posted': ap_not_posted[:30],
                 'fields_total_variants': dict(__import__('collections').Counter(str(('total_amount' in a, 'total' in a)) for a in aps))}

    # 9) Subledger vs GL: saldo AR kontrol GL vs Σ amount_due AR terbuka
    def gl_bal(code_prefix):
        d = sum(l['debit'] for l in lines if l['account_code'].startswith(code_prefix)); c = sum(l['credit'] for l in lines if l['account_code'].startswith(code_prefix))
        return round(d - c, 2)
    ar_open = round(sum(float(a.get('amount_due') or 0) for a in ars if a.get('status') in ('issued', 'partial_paid', 'overdue')), 2)
    ap_open = round(sum(float(a.get('amount_due') or a.get('balance') or 0) for a in aps if a.get('status') in ('issued', 'partial_paid', 'approved', 'overdue')), 2)
    ar_codes = sorted({l['account_code'] for l in lines if coa.get(l['account_code'], {}).get('name', '').lower().startswith('piutang')})
    ap_codes = sorted({l['account_code'] for l in lines if 'hutang usaha' in coa.get(l['account_code'], {}).get('name', '').lower() or 'utang usaha' in coa.get(l['account_code'], {}).get('name', '').lower()})
    out['subledger_vs_gl'] = {
        'ar_open_subledger': ar_open, 'ar_gl_codes_used': ar_codes,
        'ar_gl_balance': round(sum(gl_bal(c) for c in ar_codes), 2),
        'ap_open_subledger': ap_open, 'ap_gl_codes_used': ap_codes,
        'ap_gl_balance': round(-sum(gl_bal(c) for c in ap_codes), 2),
    }

    # 10) Cash accounts: balance vs Σ movements vs GL
    cash = await db.rahaza_cash_accounts.find({}, {'_id': 0}).to_list(None)
    mv = await db.rahaza_cash_movements.find({}, {'_id': 0}).to_list(None)
    mv_by_acc = defaultdict(float)
    for m in mv:
        amt = float(m.get('amount') or 0)
        mv_by_acc[m.get('account_id')] += amt if m.get('direction', m.get('type')) in ('in', 'IN', 'inflow', 'credit_in') else (-amt if m.get('direction', m.get('type')) in ('out', 'OUT', 'outflow') else amt)
    out['cash_accounts'] = [{'name': c.get('name'), 'gl': c.get('gl_account_code'), 'balance': c.get('balance'), 'opening': c.get('opening_balance'),
                             'sum_movements': round(mv_by_acc.get(c['id'], 0), 2),
                             'gl_balance': gl_bal(c['gl_account_code']) if c.get('gl_account_code') else None} for c in cash]
    out['cash_movement_keys'] = sorted({k for m in mv[:50] for k in m.keys()})
    out['cash_movement_gl_unposted'] = sum(1 for m in mv if not m.get('gl_je_id'))
    out['cash_movement_total'] = len(mv)

    # 11) Periode
    out['periods'] = [(p.get('period_code'), p.get('status')) for p in await db.rahaza_periods.find({}, {'_id': 0}).sort('period_code', 1).to_list(None)]
    # 12) posting errors di dokumen sumber
    for coll in ['rahaza_ar_invoices', 'rahaza_ap_invoices', 'rahaza_expenses', 'rahaza_material_movements', 'rahaza_material_issues', 'buyer_shipments', 'rahaza_payroll_runs', 'production_jobs']:
        n = await db[coll].count_documents({'post_error': {'$nin': [None, '']}})
        n2 = await db[coll].count_documents({'$or': [{'wip_error': {'$nin': [None, '']}}, {'cogs_seq1_error': {'$nin': [None, '']}}]})
        if n or n2:
            out.setdefault('post_errors', {})[coll] = {'post_error': n, 'other_error': n2,
                                                       'samples': [d.get('post_error') or d.get('wip_error') or d.get('cogs_seq1_error') async for d in db[coll].find({'$or': [{'post_error': {'$nin': [None, '']}}, {'wip_error': {'$nin': [None, '']}}, {'cogs_seq1_error': {'$nin': [None, '']}}]}, {'_id': 0, 'post_error': 1, 'wip_error': 1, 'cogs_seq1_error': 1}).limit(3)]}
    print(json.dumps(out, indent=1, default=str))

asyncio.run(main())
