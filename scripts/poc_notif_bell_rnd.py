"""POC: notifikasi rapor RnD & peringatan manajemen benar-benar muncul di BEL.

Bug 2026-08-07: `notification_categories._fetch` hanya membaca konvensi lama
(target_user_ids/target_roles) sehingga dokumen dari `notif_insert` (user_id)
tersimpan tapi tak pernah tampil di bel. Skrip ini membuktikan perbaikannya.

Jalankan: python3 /app/scripts/poc_notif_bell_rnd.py  (bersih-bersih di akhir)
"""
import os
import sys
import requests

API = os.environ.get('API_URL') or 'http://localhost:8001'
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
H = {'Authorization': f"Bearer {r.json().get('token') or r.json().get('access_token')}"}

base = s.get(f'{API}/api/notifications/categories', headers=H).json()
before_rnd = next((c for c in base['categories'] if c['key'] == 'rnd'), {}).get('unread', 0)

print('1. Kirim rapor keputusan RnD')
sent = s.post(f'{API}/api/dewi/rnd/reports/weekly-decisions/send', headers=H, json={}).json()
check('rapor terkirim', sent.get('sent', 0) >= 1, str(sent)[:150])
week_key = sent['week_key']

print('2. Bel menampilkan notifikasi tersebut di kategori RnD')
cats = s.get(f'{API}/api/notifications/categories', headers=H).json()
rnd = next((c for c in cats['categories'] if c['key'] == 'rnd'), None)
check('kategori RnD ada di bel', rnd is not None, str([c['key'] for c in cats['categories']]))
check('jumlah belum dibaca RnD naik', (rnd or {}).get('unread', 0) > before_rnd,
      f"sebelum={before_rnd} sesudah={(rnd or {}).get('unread')}")
check('total belum dibaca > 0', cats['total_unread'] > 0, str(cats['total_unread']))
check('rapor ada di daftar terbaru (latest)',
      any('Rapor keputusan RnD' in (n.get('title') or '') for n in cats['latest']),
      str([n.get('title') for n in cats['latest']])[:200])

print('3. Popup berkategori (yang dipakai bel) memuat rapor')
lst = s.get(f'{API}/api/notifications/categorized?category=rnd&limit=50', headers=H).json()
item = next((n for n in lst['items'] if (n.get('title') or '').startswith('Rapor keputusan RnD')), None)
check('rapor muncul di /categorized?category=rnd', item is not None,
      str([n.get('title') for n in lst['items']])[:200])
if item:
    check('kategori diturunkan = rnd', item['category'] == 'rnd', item.get('category'))
    check('isi rapor terbaca', 'disetujui' in (item.get('body') or ''), (item.get('body') or '')[:120])

print('4. Tandai sudah dibaca dari bel')
if item:
    r = s.post(f"{API}/api/notifications/unified/{item['id']}/mark-read", headers=H)
    check('mark-read 200', r.status_code == 200, r.text[:150])
    after = s.get(f'{API}/api/notifications/categories', headers=H).json()
    rnd2 = next((c for c in after['categories'] if c['key'] == 'rnd'), {})
    check('jumlah belum dibaca RnD turun', rnd2.get('unread', 99) < (rnd or {}).get('unread', 0),
          f"{(rnd or {}).get('unread')} → {rnd2.get('unread')}")

print('5. Bersihkan notifikasi uji')
sys.path.insert(0, '/app/backend')
os.chdir('/app/backend')
import asyncio  # noqa: E402
from dotenv import load_dotenv  # noqa: E402
load_dotenv('/app/backend/.env')
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def _clean():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    res = await db.notifications.delete_many({'subtype': 'rnd_weekly_decisions'})
    return res.deleted_count


print(f'  · notifikasi rapor dihapus: {asyncio.run(_clean())} (pekan {week_key})')
check('bel kembali bersih dari rapor uji',
      not any('Rapor keputusan RnD' in (n.get('title') or '')
              for n in s.get(f'{API}/api/notifications/categorized?category=rnd&limit=50',
                             headers=H).json()['items']))

print(f'\n== {ok} PASS / {fail} FAIL ==')
sys.exit(1 if fail else 0)
