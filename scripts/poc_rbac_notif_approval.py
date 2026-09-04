"""POC RBAC: isolasi notifikasi lintas role + gerbang izin approval (2026-08-07).

Pertanyaan owner: "pastikan notifikasi & approval terhubung RBAC — jangan
sampai role A menerima notifikasi role B."

Skrip ini memakai akun nyata dari /app/memory/test_credentials.md dan
membersihkan semua notifikasi ujinya sendiri.

Jalankan: python3 /app/scripts/poc_rbac_notif_approval.py
"""
import os
import sys
import asyncio
import requests

API = os.environ.get('API_URL') or 'http://localhost:8001'
ok, fail = 0, 0

ACCOUNTS = {
    'admin': ('admin@garment.com', 'Admin@123'),
    'hr': ('hr@dewiaditya.id', 'Dewi@123'),
    'finance': ('finance@dewiaditya.id', 'Dewi@123'),
    'supervisor_produksi': ('spv@dewiaditya.id', 'Dewi@123'),
    'admin_gudang': ('gudang@dewiaditya.id', 'Dewi@123'),
    'admin_maklon': ('maklon@dewiaditya.id', 'Dewi@123'),
}


def check(label, cond, extra=''):
    global ok, fail
    if cond:
        ok += 1
        print(f'  PASS · {label}')
    else:
        fail += 1
        print(f'  FAIL · {label} {extra}')


def login(email, pw, attempts=6):
    """Login dengan sabar: rate limit 10 percobaan/60 detik → tunggu lalu ulangi."""
    import time
    r = None
    for i in range(attempts):
        r = requests.post(f'{API}/api/auth/login', json={'email': email, 'password': pw})
        if r.status_code == 200:
            break
        if r.status_code in (429, 423):
            time.sleep(20)
            continue
        break
    if r is None or r.status_code != 200:
        print(f'    (login {email} → {r.status_code if r else "?"} {r.text[:80] if r else ""})')
        return None, None
    j = r.json()
    tok = j.get('token') or j.get('access_token')
    me = requests.get(f'{API}/api/auth/me', headers={'Authorization': f'Bearer {tok}'})
    return tok, (me.json() if me.status_code == 200 else {})


sess = {}
print('0. Login semua akun uji')
for key, (email, pw) in ACCOUNTS.items():
    tok, me = login(email, pw)
    if tok:
        sess[key] = {'token': tok, 'me': me, 'H': {'Authorization': f'Bearer {tok}'}}
        print(f'  · {key:20} {email:32} role={me.get("role")} id={str(me.get("id"))[:8]}')
    else:
        print(f'  ! {key} gagal login ({email}) — dilewati')

check('akun admin tersedia', 'admin' in sess)
need_two = [k for k in ('hr', 'finance', 'supervisor_produksi', 'admin_gudang', 'admin_maklon')
            if k in sess]
check('minimal 2 akun non-admin untuk uji isolasi', len(need_two) >= 2, str(need_two))

sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')
from dotenv import load_dotenv  # noqa: E402
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from utils.notif_unified import notif_insert  # noqa: E402

MARK = 'POC-RBAC-2026'


async def seed():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    a = sess[need_two[0]]
    b = sess[need_two[1]]
    role_a = (a['me'].get('role') or '').lower()
    role_b = (b['me'].get('role') or '').lower()
    out = {}
    # 1) personal untuk A
    out['personal_a'] = await notif_insert(
        db, type='rahaza', subtype='poc_rbac_personal', title=f'{MARK} personal A',
        body='rahasia A', user_id=a['me']['id'], status='sent')
    # 2) role A saja
    out['role_a'] = await notif_insert(
        db, type='rahaza', subtype='poc_rbac_role', title=f'{MARK} role {role_a}',
        body=f'khusus {role_a}', target_roles=[role_a], status='sent')
    # 3) role B saja
    out['role_b'] = await notif_insert(
        db, type='rahaza', subtype='poc_rbac_role', title=f'{MARK} role {role_b}',
        body=f'khusus {role_b}', target_roles=[role_b], status='sent')
    # 4) tanpa target (harus hanya admin/owner)
    out['no_target'] = await notif_insert(
        db, type='rahaza', subtype='poc_rbac_untargeted', title=f'{MARK} tanpa target',
        body='siaran lama', status='sent')
    # 5) role A dengan kategori yang MEMANG milik portalnya (subtype memuat
    #    'leave' → kategori 'hr'). Dipakai menguji pembisuan per orang: kategori
    #    biasa boleh dibisukan, "Untuk Saya" tidak.
    out['role_a_hr'] = await notif_insert(
        db, type='rahaza', subtype='poc_rbac_leave_request', title=f'{MARK} kategori hr',
        body='pengajuan cuti', target_roles=[role_a], status='sent')
    return out, role_a, role_b


ids, role_a, role_b = asyncio.run(seed())
A, B = sess[need_two[0]], sess[need_two[1]]


def titles_for(s, url='/api/notifications/categorized?limit=200'):
    r = requests.get(f'{API}{url}', headers=s['H'])
    if r.status_code != 200:
        return None
    return [n.get('title') or '' for n in r.json().get('items', [])]


print('1. Isolasi di bel notifikasi + inbox')
ta, tb = titles_for(A), titles_for(B)
ua = titles_for(A, '/api/notifications/unified?limit=200') or []
ub = titles_for(B, '/api/notifications/unified?limit=200') or []
check('A melihat notifikasi personalnya di inbox', any(f'{MARK} personal A' in t for t in ua))
check(f'A melihat notifikasi role {role_a} di inbox',
      any(f'{MARK} role {role_a}' in t for t in ua))
check(f'B melihat notifikasi role {role_b} di inbox',
      any(f'{MARK} role {role_b}' in t for t in ub))
check('B TIDAK melihat notifikasi personal A di inbox',
      not any(f'{MARK} personal A' in t for t in ub))
check('A melihat notifikasi personalnya', any(f'{MARK} personal A' in t for t in ta))
check('B TIDAK melihat notifikasi personal A',
      not any(f'{MARK} personal A' in t for t in tb), str([t for t in tb if MARK in t]))
check(f'A melihat notifikasi role {role_a}', any(f'{MARK} role {role_a}' in t for t in ta))
check(f'B TIDAK melihat notifikasi role {role_a}',
      not any(f'{MARK} role {role_a}' in t for t in tb), str([t for t in tb if MARK in t]))
check(f'B melihat notifikasi role {role_b}', any(f'{MARK} role {role_b}' in t for t in tb))
check(f'A TIDAK melihat notifikasi role {role_b}',
      not any(f'{MARK} role {role_b}' in t for t in ta), str([t for t in ta if MARK in t]))
check('notifikasi tanpa target tidak bocor ke A/B',
      not any(f'{MARK} tanpa target' in t for t in ta + tb))
tadm = titles_for(sess['admin'])
check('admin tetap bisa melihat notifikasi tanpa target',
      any(f'{MARK} tanpa target' in t for t in tadm))

print('1b. Kategori "Untuk Saya" + pembisuan milik sendiri (2026-08-07)')


def cat_summary(s):
    r = requests.get(f'{API}/api/notifications/categories', headers=s['H'])
    return r.json() if r.status_code == 200 else {}


def items_of(s, cat):
    r = requests.get(f'{API}/api/notifications/categorized?category={cat}&limit=200',
                     headers=s['H'])
    return [n.get('title') or '' for n in r.json().get('items', [])] if r.status_code == 200 else []


sumA = cat_summary(A)
keysA = [c['key'] for c in sumA.get('categories', [])]
check('kategori "Untuk Saya" tersedia untuk peran non-admin', 'personal' in keysA, str(keysA))
pers = items_of(A, 'personal')
check('notifikasi personal A masuk kategori "Untuk Saya"',
      any(f'{MARK} personal A' in t for t in pers), str([t for t in pers if MARK in t]))
check('notifikasi role A (kategori di luar portalnya) juga masuk "Untuk Saya"',
      any(f'{MARK} role {role_a}' in t for t in pers))
hr_items = items_of(A, 'hr')
check(f'notifikasi berkategori hr tampil di kategori hr untuk {role_a}',
      any(f'{MARK} kategori hr' in t for t in hr_items),
      str([t for t in hr_items if MARK in t]))
tot_cat = sum(c.get('total', 0) for c in sumA.get('categories', []))
all_items = titles_for(A, '/api/notifications/categorized?limit=300') or []
check('angka di bel sama dengan jumlah isi popup', tot_cat == len(all_items),
      f'kategori={tot_cat} popup={len(all_items)}')

r = requests.put(f'{API}/api/notifications/my-category-prefs', headers=A['H'],
                 json={'muted_categories': ['hr', 'personal']})
pbody = r.json() if r.status_code == 200 else {}
check('permintaan membisukan "Untuk Saya" diabaikan (tetap aktif)',
      r.status_code == 200 and 'personal' not in (pbody.get('muted_categories') or []),
      f'{r.status_code} {str(pbody)[:120]}')
check('kategori hr tercatat dibisukan', 'hr' in (pbody.get('muted_categories') or []),
      str(pbody)[:120])
after = titles_for(A, '/api/notifications/categorized?limit=300') or []
check('notifikasi berkategori hr hilang dari bel setelah dibisukan',
      not any(f'{MARK} kategori hr' in t for t in after),
      str([t for t in after if MARK in t]))
check('notifikasi "Untuk Saya" tetap tampil walau mencoba dibisukan',
      any(f'{MARK} personal A' in t for t in after))
requests.put(f'{API}/api/notifications/my-category-prefs', headers=A['H'],
             json={'muted_categories': []})
back = titles_for(A, '/api/notifications/categorized?limit=300') or []
check('notifikasi berkategori hr kembali setelah pembisuan dilepas',
      any(f'{MARK} kategori hr' in t for t in back))
r = requests.get(f'{API}/api/notifications/my-category-prefs', headers=A['H'])
pref = r.json() if r.status_code == 200 else {}
check('layar preferensi menyebut "Untuk Saya" terkunci',
      'personal' in (pref.get('locked_categories') or []), str(pref)[:160])


print('2. Isolasi di inbox unified (kebocoran ?user_id / all_users)')
r = requests.get(f'{API}/api/notifications/unified?user_id={A["me"]["id"]}', headers=B['H'])
check('B tidak boleh membaca inbox A lewat ?user_id → 403', r.status_code == 403, r.text[:150])
r = requests.get(f'{API}/api/notifications/unified?all_users=true', headers=B['H'])
check('B tidak boleh all_users=true → 403', r.status_code == 403, r.text[:150])
r = requests.get(f'{API}/api/notifications/unified?all_users=true', headers=sess['admin']['H'])
check('admin masih boleh all_users=true', r.status_code == 200, r.text[:150])
r = requests.get(f'{API}/api/notifications/unified?limit=200', headers=B['H'])
tb2 = [n.get('title') or '' for n in r.json().get('items', [])]
check('inbox unified B bersih dari notifikasi A',
      not any(f'{MARK} personal A' in t or f'{MARK} role {role_a}' in t for t in tb2),
      str([t for t in tb2 if MARK in t]))
r = requests.get(f'{API}/api/notifications/unified/stats?all_users=true', headers=B['H'])
check('statistik all_users juga ditolak untuk B', r.status_code == 403, r.text[:120])

print('3. Tandai dibaca bersifat per orang')
r = requests.post(f'{API}/api/notifications/unified/{ids["role_b"]}/mark-read', headers=A['H'])
check('A tidak bisa menandai notifikasi role B → 404', r.status_code == 404, r.text[:120])
r = requests.post(f'{API}/api/notifications/unified/{ids["role_b"]}/mark-read', headers=B['H'])
check('B bisa menandai notifikasinya sendiri', r.status_code == 200, r.text[:120])


async def read_state():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    doc = await db.notifications.find_one({'id': ids['role_b']}, {'_id': 0})
    return doc.get('read'), ((doc.get('meta') or {}).get('read_by') or [])


read_flag, read_by = asyncio.run(read_state())
check('status baca disimpan per penerima (read_by), bukan global',
      B['me']['id'] in read_by and not read_flag, f'read={read_flag} read_by={read_by}')

print('4. Outbox notifikasi klien hanya untuk manajemen')
non_mgmt = next((k for k in ('supervisor_produksi', 'admin_gudang') if k in sess), None)
if non_mgmt:
    r = requests.get(f'{API}/api/dewi/notifications', headers=sess[non_mgmt]['H'])
    check(f'{non_mgmt} tidak boleh membuka outbox klien → 403', r.status_code == 403, r.text[:120])
    r = requests.put(f'{API}/api/dewi/notifications/provider-config',
                     headers=sess[non_mgmt]['H'], json={'whatsapp_provider': 'mock'})
    check(f'{non_mgmt} tidak boleh mengubah konfigurasi provider → 403',
          r.status_code == 403, r.text[:120])
r = requests.get(f'{API}/api/dewi/notifications', headers=sess['admin']['H'])
check('admin tetap bisa membuka outbox klien', r.status_code == 200, r.text[:120])

print('5. Gerbang izin pada endpoint keputusan')
adm = sess['admin']['H']
# style RnD → keputusan khusus owner/admin
r = requests.post(f'{API}/api/dewi/rnd/styles', headers=adm, json={
    'style_code': 'ZZ-POC-RBAC-1', 'style_name': 'POC RBAC'})
style_id = r.json().get('id')
requests.post(f'{API}/api/dewi/rnd/styles/{style_id}/submit-for-review', headers=adm,
              json={'notes': 'poc'})
for key in need_two:
    r = requests.post(f'{API}/api/dewi/rnd/styles/{style_id}/owner-approve',
                      headers=sess[key]['H'], json={'notes': 'coba'})
    check(f'{key} tidak bisa owner-approve style → 403', r.status_code == 403, r.text[:130])
r = requests.post(f'{API}/api/dewi/rnd/styles/{style_id}/owner-approve', headers=adm,
                  json={'notes': 'poc setuju'})
check('admin bisa owner-approve style', r.status_code == 200, r.text[:150])

cases = [
    ('sample RnD', 'POST', '/api/dewi/rnd/sample-requests/does-not-exist/approve', {}),
    ('pola RnD', 'POST', '/api/dewi/rnd/patterns/does-not-exist/approve', None),
    ('tech pack', 'POST', '/api/dewi/rnd/tech-packs/does-not-exist/approve', None),
    ('permintaan pembelian', 'POST', '/api/procurement/requests/x/approve', {}),
    ('anggaran', 'POST', '/api/rahaza/finance/budgets/x/approve', {}),
    ('rekonsiliasi bank', 'POST', '/api/finance/bank-recon/sessions/x/approve', {}),
    ('retur marketing', 'POST', '/api/marketing/returns/x/approve', {}),
    ('penerimaan CMT (reject)', 'POST', '/api/prod/cmt-receipts/x/reject', {}),
    ('roll kain (reject)', 'POST', '/api/wms/fabric-rolls/x/reject', {'reason': 'poc'}),
]
blocked_role = need_two[0]
for label, method, path, payload in cases:
    r = requests.request(method, f'{API}{path}', headers=sess[blocked_role]['H'], json=payload)
    check(f'{blocked_role} ditolak pada {label} (403, bukan 404/400)',
          r.status_code == 403, f'{r.status_code} {r.text[:110]}')

print('6. Halaman audit RBAC (Portal Sysadmin)')
r = requests.get(f'{API}/api/admin/rbac-audit', headers=adm)
check('audit RBAC 200 untuk admin', r.status_code == 200, r.text[:150])
aud = r.json() if r.status_code == 200 else {}
check('audit melaporkan endpoint keputusan', (aud.get('code', {}).get('approvals', {})
                                              .get('total', 0)) > 50, str(aud.get('code', {}).get('approvals', {}))[:120])
check('audit melaporkan penulis notifikasi',
      aud.get('code', {}).get('notification_writers', {}).get('total', 0) >= 20)
check('audit melaporkan fakta data notifikasi', 'total' in aud.get('data', {}))
r = requests.get(f'{API}/api/admin/rbac-audit', headers=sess[blocked_role]['H'])
check(f'{blocked_role} tidak boleh membuka audit RBAC → 403', r.status_code == 403, r.text[:120])

print('7. Bersihkan')
requests.delete(f'{API}/api/dewi/rnd/styles/{style_id}', headers=adm)


async def cleanup():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    res = await db.notifications.delete_many({'subtype': {'$regex': '^poc_rbac_'}})
    rev = await db.dewi_rnd_revisions.delete_many({'style_id': style_id})
    # preferensi pembisuan akun uji A dibersihkan agar tidak mengganggu demo
    await db.notif_user_prefs.delete_one({'user_id': A['me']['id']})
    return res.deleted_count, rev.deleted_count


n_notif, n_rev = asyncio.run(cleanup())
print(f'  · notifikasi uji dihapus: {n_notif} · revisi style uji dihapus: {n_rev}')
check('notifikasi uji bersih', n_notif >= 5, str(n_notif))

print(f'\n== {ok} PASS / {fail} FAIL ==')
sys.exit(1 if fail else 0)
