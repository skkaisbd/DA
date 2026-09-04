"""POC: tahap lifecycle RnD 7 langkah + PIC sample, rapor keputusan mingguan,
ambang peringatan PO/AR yang bisa diatur.

Jalankan: python3 /app/scripts/poc_rnd_stages_alerts.py
Membersihkan artefaknya sendiri di akhir (style/sample uji + ambang dipulihkan).
"""
import os
import sys
import requests

API = os.environ.get('API_URL') or 'http://localhost:8001'
CODE = 'ZZ-POC-TAHAP-1'
ok, fail = 0, 0


def check(label, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
        print(f'  PASS · {label}')
    else:
        fail += 1
        print(f'  FAIL · {label} {extra}')


s = requests.Session()
r = s.post(f'{API}/api/auth/login', json={'email': 'admin@garment.com', 'password': 'Admin@123'})
r.raise_for_status()
tok = r.json().get('token') or r.json().get('access_token')
H = {'Authorization': f'Bearer {tok}'}

for st in s.get(f'{API}/api/dewi/rnd/styles?search={CODE}', headers=H).json():
    if st['style_code'] == CODE:
        s.delete(f"{API}/api/dewi/rnd/styles/{st['id']}", headers=H)

print('=== A. AMBANG PERINGATAN (PO & AR terpisah) ===')
r = s.get(f'{API}/api/rahaza/management/alert-config', headers=H)
check('GET alert-config 200', r.status_code == 200, r.text[:150])
orig = r.json()
check('bawaan po_warn_days=3', orig['defaults']['po_warn_days'] == 3, str(orig.get('defaults')))

r = s.put(f'{API}/api/rahaza/management/alert-config', headers=H,
          json={'po_warn_days': 10, 'ar_warn_days': 2})
check('PUT ambang 200', r.status_code == 200, r.text[:200])
cfg = r.json() if r.status_code == 200 else {}
check('po_warn_days tersimpan 10', cfg.get('po_warn_days') == 10, str(cfg))
check('ar_warn_days tersimpan 2', cfg.get('ar_warn_days') == 2, str(cfg))

for bad in ({'po_warn_days': 99}, {'po_warn_days': 'abc'}, {}):
    rb = s.put(f'{API}/api/rahaza/management/alert-config', headers=H, json=bad)
    check(f'input tidak sah {bad} → 400', rb.status_code == 400, rb.text[:120])

r = s.get(f'{API}/api/rahaza/management/alerts', headers=H)
check('preview alerts memakai ambang tersimpan', r.status_code == 200 and
      r.json().get('po_warn_days') == 10 and r.json().get('ar_warn_days') == 2,
      r.text[:200])
prev10 = r.json()
r0 = s.get(f'{API}/api/rahaza/management/alerts?warn_days=0', headers=H)
check('override warn_days=0 tetap dihormati', r0.json().get('po_warn_days') == 0, r0.text[:150])
check('ambang lebih longgar ⇒ temuan PO >= ambang ketat',
      prev10['po_count'] >= r0.json()['po_count'],
      f"10h={prev10['po_count']} 0h={r0.json()['po_count']}")

r = s.put(f'{API}/api/rahaza/management/alert-config', headers=H,
          json={'po_warn_days': orig['po_warn_days'], 'ar_warn_days': orig['ar_warn_days'],
                'rnd_stale_days': orig['rnd_stale_days']})
check('ambang dipulihkan', r.status_code == 200 and r.json()['po_warn_days'] == orig['po_warn_days'],
      r.text[:150])

print('=== B. TAHAP LIFECYCLE RnD 7 LANGKAH ===')
r = s.get(f'{API}/api/dewi/rnd/lifecycle', headers=H)
check('GET /lifecycle 200', r.status_code == 200, r.text[:200])
lc = r.json()
keys = [x['key'] for x in lc['stages']]
check('7 tahap berurutan', keys == ['draft', 'pending_owner_review', 'approved_for_launch',
                                   'techpack', 'pattern', 'sample', 'promoted'], str(keys))
check('jumlah tahap = jumlah style',
      sum(x['count'] for x in lc['stages']) == lc['total_styles'],
      f"{sum(x['count'] for x in lc['stages'])} vs {lc['total_styles']}")
check('ada baris per style', isinstance(lc.get('styles'), list))
check('totals memuat tech_packs & sample_pics',
      'tech_packs' in lc['totals'] and 'sample_pics' in lc['totals'], str(lc['totals']))

r = s.get(f'{API}/api/dewi/rnd/approvals/pending', headers=H)
check('funnel di /approvals/pending kini 7 tahap', len(r.json()['funnel']) == 7,
      str(len(r.json()['funnel'])))
check('funnel = stages lifecycle (satu sumber angka)',
      [f['count'] for f in r.json()['funnel']] == [x['count'] for x in lc['stages']],
      f"{[f['count'] for f in r.json()['funnel']]} vs {[x['count'] for x in lc['stages']]}")

print('=== C. PIC / PEMBUAT SAMPLE ===')
r = s.post(f'{API}/api/dewi/rnd/styles', headers=H, json={
    'style_code': CODE, 'style_name': 'POC Tahap RnD', 'status': 'active'})
style_id = r.json()['id']
check('style uji dibuat', r.status_code == 200, r.text[:150])
r = s.post(f'{API}/api/dewi/rnd/sample-requests', headers=H, json={
    'style_id': style_id, 'quantity': 3, 'priority': 'high',
    'sample_pic': 'Bu Sri (Sample Room)', 'due_date': '2026-08-20'})
check('sample request dengan PIC 200', r.status_code == 200, r.text[:200])
sample_id = r.json().get('id')
check('sample_pic tersimpan', r.json().get('sample_pic') == 'Bu Sri (Sample Room)', r.text[:200])

lc2 = s.get(f'{API}/api/dewi/rnd/lifecycle', headers=H).json()
row = next((x for x in lc2['styles'] if x['id'] == style_id), None)
check('style uji ada di tabel lifecycle', row is not None)
if row:
    check('tahap = sample', row['stage'] == 'sample', row['stage'])
    check('PIC tampil di baris', row['sample']['pic'] == 'Bu Sri (Sample Room)', str(row['sample']))
    check('langkah berikutnya terisi', bool(row['next_action']), row.get('next_action'))
check('sample_pics dihitung', lc2['totals']['sample_pics'] >= 1, str(lc2['totals']))

s.post(f'{API}/api/dewi/rnd/sample-requests/{sample_id}/submit', headers=H)
pend = s.get(f'{API}/api/dewi/rnd/approvals/pending', headers=H).json()
item = next((i for i in pend['items'] if i['id'] == sample_id), None)
check('sample muncul di antrean keputusan', item is not None)
if item:
    check('PIC ada di detail cockpit',
          item['detail'].get('PIC / Pembuat Sample') == 'Bu Sri (Sample Room)', str(item['detail']))
    check('PIC ada di subtitle', 'PIC Bu Sri' in item['subtitle'], item['subtitle'])

print('=== D. RAPOR KEPUTUSAN RnD MINGGUAN ===')
r = s.get(f'{API}/api/dewi/rnd/reports/weekly-decisions', headers=H)
check('pratinjau rapor 200', r.status_code == 200, r.text[:200])
rep = r.json()
for k in ('approved', 'rejected', 'pending', 'stale', 'counts', 'week_key', 'stale_days'):
    check(f'rapor punya "{k}"', k in rep, str(list(rep.keys()))[:200])
check('stale_days default 7', rep['stale_days'] == 7, str(rep['stale_days']))
r = s.get(f'{API}/api/dewi/rnd/reports/weekly-decisions?days=30&stale_days=0', headers=H)
check('parameter days & stale_days dihormati',
      r.json()['days'] == 30 and r.json()['stale_days'] == 0, r.text[:150])
check('stale_days=0 ⇒ semua yang menunggu masuk daftar tertunda',
      r.json()['counts']['stale'] == r.json()['counts']['pending'],
      str(r.json()['counts']))

r = s.post(f'{API}/api/dewi/rnd/reports/weekly-decisions/send', headers=H, json={})
check('kirim rapor 200', r.status_code == 200, r.text[:200])
sent = r.json()
check('notifikasi terkirim ke penerima', sent['sent'] >= 1, str(sent.get('sent')))
week_key = sent['week_key']
r2 = s.post(f'{API}/api/dewi/rnd/reports/weekly-decisions/send', headers=H, json={})
check('kirim ulang manual tetap boleh (force)', r2.json()['sent'] >= 1, r2.text[:150])
r3 = s.post(f'{API}/api/dewi/rnd/reports/weekly-decisions/send', headers=H, json={'days': 0})
check('days tidak sah → 400', r3.status_code == 400, r3.text[:120])

print('=== E. IDEMPOTENSI JOB MINGGUAN ===')
import asyncio  # noqa: E402
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')
from dotenv import load_dotenv  # noqa: E402
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from services.rnd_decision_report import send_rnd_decision_report  # noqa: E402


async def _run():
    cli = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = cli[os.environ['DB_NAME']]
    out = await send_rnd_decision_report(db)   # tanpa force → harus dilewati
    n = await db.notifications.count_documents(
        {'subtype': 'rnd_weekly_decisions', 'source_ref': f'rnd-weekly-{week_key}'})
    return out, n


out, notif_n = asyncio.run(_run())
check('job tanpa force dilewati (idempoten per pekan)', out['sent'] == 0 and out['skipped'],
      str(out.get('skipped')))
check('notifikasi pekan ini tercatat', notif_n >= 1, str(notif_n))

print('=== F. BERSIHKAN ===')
s.delete(f'{API}/api/dewi/rnd/sample-requests/{sample_id}', headers=H)
d = s.delete(f'{API}/api/dewi/rnd/styles/{style_id}', headers=H)
check('style uji dihapus (+revisi ikut)', d.status_code == 200, d.text[:150])


async def _cleanup():
    cli = AsyncIOMotorClient(os.environ['MONGO_URL'])
    db = cli[os.environ['DB_NAME']]
    res = await db.notifications.delete_many({'subtype': 'rnd_weekly_decisions'})
    orphan = await db.dewi_rnd_revisions.delete_many({'style_id': style_id})
    left = await db.dewi_rnd_sample_requests.count_documents({'style_id': style_id})
    return res.deleted_count, orphan.deleted_count, left


n_notif, n_rev, n_sample = asyncio.run(_cleanup())
print(f'  · notifikasi uji dibersihkan: {n_notif} · revisi sisa: {n_rev} · sample sisa: {n_sample}')
check('sample uji bersih', n_sample == 0, str(n_sample))
lc3 = s.get(f'{API}/api/dewi/rnd/lifecycle', headers=H).json()
check('style uji tidak lagi ada di lifecycle',
      all(x['id'] != style_id for x in lc3['styles']))

print(f'\n== {ok} PASS / {fail} FAIL ==')
sys.exit(1 if fail else 0)
