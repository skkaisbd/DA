"""POC: unggah foto desain RnD + riwayat revisi otomatis + bandingkan revisi.

Jalankan: python3 /app/scripts/poc_rnd_photo_compare.py
Membersihkan artefaknya sendiri di akhir.
"""
import io
import os
import sys
import requests

API = os.environ.get('API_URL') or 'http://localhost:8001'
CODE = 'ZZ-POC-FOTO-1'
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
token = r.json()['token'] if 'token' in r.json() else r.json()['access_token']
H = {'Authorization': f'Bearer {token}'}

# bersihkan sisa run sebelumnya
for st in s.get(f'{API}/api/dewi/rnd/styles?search={CODE}', headers=H).json():
    if st['style_code'] == CODE:
        s.delete(f"{API}/api/dewi/rnd/styles/{st['id']}", headers=H)

print('1. Buat style')
r = s.post(f'{API}/api/dewi/rnd/styles', headers=H, json={
    'style_code': CODE, 'style_name': 'POC Foto & Revisi', 'category': 'T-Shirt',
    'fabric_type': 'Cotton 24s', 'season': 'AW26', 'description': 'versi awal'})
check('create style 200', r.status_code == 200, r.text[:200])
style_id = r.json()['id']

print('2. Unggah 2 foto desain')
png = (b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00'
       b'\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00'
       b'\x00\x00IEND\xaeB`\x82')
img_ids = []
for i in (1, 2):
    r = s.post(f'{API}/api/dewi/rnd/styles/{style_id}/images', headers=H,
               files={'file': (f'sketsa{i}.png', io.BytesIO(png), 'image/png')})
    check(f'upload foto {i} 200', r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        img_ids.append(r.json()['id'])
        check(f'url foto {i} = /api/files/...', r.json()['url'].startswith('/api/files/'))

print('3. Tolak berkas non-gambar')
r = s.post(f'{API}/api/dewi/rnd/styles/{style_id}/images', headers=H,
           files={'file': ('a.txt', io.BytesIO(b'bukan gambar'), 'text/plain')})
check('non-gambar → 400', r.status_code == 400, r.text[:120])

print('4. Foto bisa diunduh dengan ?auth=token')
url = s.get(f'{API}/api/dewi/rnd/styles/{style_id}', headers=H).json()['design_images'][0]['url']
r = s.get(f'{API}{url}?auth={token}')
check('GET /api/files 200', r.status_code == 200, r.text[:120])
check('konten gambar', r.content[:4] == b'\x89PNG')

print('5. Ubah style → revisi otomatis')
r = s.put(f'{API}/api/dewi/rnd/styles/{style_id}', headers=H,
          json={'style_name': 'POC Foto & Revisi v2', 'fabric_type': 'Cotton 30s',
                'description': 'lengan diperpanjang'})
check('update style 200', r.status_code == 200, r.text[:200])
revs = s.get(f'{API}/api/dewi/rnd/revisions?style_id={style_id}', headers=H).json()
check('revisi tercatat >= 3 (2 foto + 1 ubah)', len(revs) >= 3, f'dapat {len(revs)}')
auto = [x for x in revs if x.get('source') == 'auto']
check('semua revisi ber-snapshot', all(x.get('snapshot') for x in auto), '')
last = sorted(revs, key=lambda x: x['revision_number'])[-1]
check('changed_fields terisi', len(last.get('changed_fields') or []) >= 2, str(last.get('changed_fields')))

print('6. Bandingkan revisi (bawaan)')
r = s.get(f'{API}/api/dewi/rnd/styles/{style_id}/revisions/compare', headers=H)
check('compare 200', r.status_code == 200, r.text[:200])
cmp = r.json()
check('ada daftar available (+current)', any(a['id'] == 'current' for a in cmp['available']))
check('ada baris field', len(cmp['fields']) >= 10, str(len(cmp.get('fields', []))))
check('ada field berubah', cmp['changed_count'] >= 1, str(cmp['changed_count']))

print('7. Bandingkan revisi pertama vs kondisi sekarang')
first = sorted(revs, key=lambda x: x['revision_number'])[0]
r = s.get(f'{API}/api/dewi/rnd/styles/{style_id}/revisions/compare',
          headers=H, params={'left': first['id'], 'right': 'current'})
cmp2 = r.json()
check('compare rev-1 vs current 200', r.status_code == 200, r.text[:200])
check('nama style berubah antar versi',
      any(f['key'] == 'style_name' and f['changed'] for f in cmp2['fields']),
      str([f for f in cmp2['fields'] if f['key'] == 'style_name']))
check('foto versi B = 2', len(cmp2['images']['right']) == 2, str(len(cmp2['images']['right'])))
check('foto versi A lebih sedikit (baru ditambah)',
      len(cmp2['images']['left']) < len(cmp2['images']['right']) or cmp2['images']['added'],
      f"A={len(cmp2['images']['left'])} B={len(cmp2['images']['right'])}")

print('8. Hapus 1 foto → revisi baru + hitungan turun')
r = s.delete(f'{API}/api/dewi/rnd/styles/{style_id}/images/{img_ids[0]}', headers=H)
check('delete foto 200', r.status_code == 200, r.text[:200])
check('sisa 1 foto', r.json().get('total_images') == 1, r.text[:120])
r = s.delete(f'{API}/api/dewi/rnd/styles/{style_id}/images/tidak-ada', headers=H)
check('hapus foto tak ada → 404', r.status_code == 404, r.text[:120])

print('9. Cockpit approval membawa revisions_count + foto')
s.post(f'{API}/api/dewi/rnd/styles/{style_id}/submit-for-review', headers=H, json={'notes': 'poc'})
pend = s.get(f'{API}/api/dewi/rnd/approvals/pending', headers=H).json()
item = next((i for i in pend['items'] if i['id'] == style_id), None)
check('style muncul di antrean keputusan', item is not None)
if item:
    check('images terisi di cockpit', len(item['images']) == 1, str(item['images']))
    check('revisions_count > 0', item.get('revisions_count', 0) > 0, str(item.get('revisions_count')))

print('10. Bersihkan')
for rev in s.get(f'{API}/api/dewi/rnd/revisions?style_id={style_id}', headers=H).json():
    s.delete(f"{API}/api/dewi/rnd/revisions/{rev['id']}", headers=H)
d = s.delete(f'{API}/api/dewi/rnd/styles/{style_id}', headers=H)
check('style dihapus', d.status_code == 200, d.text[:120])
left = [x for x in s.get(f'{API}/api/dewi/rnd/revisions?style_id={style_id}', headers=H).json()]
check('revisi bersih', len(left) == 0, str(len(left)))

print(f'\n== {ok} PASS / {fail} FAIL ==')
sys.exit(1 if fail else 0)
