#!/usr/bin/env python3
"""POC — buktikan rantai R&D → PO produksi BENAR-BENAR mentok / merusak master ukuran.

Dijalankan SEBELUM menulis fitur "Padankan Ukuran", supaya fitur itu menutup
masalah yang NYATA, bukan masalah yang saya kira ada.

Hipotesis yang diuji (semuanya lewat API sungguhan, bukan mock):

  H1  Ukuran R&D adalah teks bebas (kebijakan B1). `size_map` menandai mana yang
      "belum dipadankan" ke master `rahaza_sizes`.
  H2  `POST /styles/{id}/promote-to-production` MENGABAIKAN `size_map` dan
      memanggil `ensure_size(code=<label mentah>)`. Akibatnya:
        · 'All Size' → master ukuran BARU berkode 'ALL SIZE' padahal 'ALLSIZE'
          SUDAH ADA  ⇒ master ukuran KEMBAR (SSOT pecah)
        · '2XL'      → master ukuran BARU 'XXL' vs '2XL' hidup berdua
        · '28/30'    → kode master berisi garis miring ⇒ masuk ke SKU
      Padahal `size_map` untuk 'All Size' JELAS sudah `matched:true` → ALLSIZE.
  H3  Akibat H2, SKU FG hasil promosi memakai kode ukuran yang salah/berspasi,
      sehingga tidak akan pernah cocok dengan SKU yang dipakai gudang.

Kalau H2/H3 terbukti, layar "Padankan Ukuran" saja TIDAK CUKUP — promosi juga
harus menghormati `size_map`. Itulah yang mau dibuktikan di sini.

Jalankan: python scripts/poc_rnd_size_promotion.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = os.environ.get('BASE_URL', 'http://localhost:8001/api')
EMAIL = os.environ.get('GATE_EMAIL', 'admin@garment.com')
PASSWORD = os.environ.get('GATE_PASSWORD', 'Admin@123')

G, R, Y, B, X = '\033[92m', '\033[91m', '\033[93m', '\033[1m', '\033[0m'
RESULTS = []


def req(method, path, body=None, token=None):
    url = f"{BASE}{path}" if path.startswith('/api') is False else f"{BASE.rstrip('/api')}{path}"
    url = f"{BASE}{path[4:]}" if path.startswith('/api/') else f"{BASE}{path}"
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'raw': raw}
    except Exception as e:
        return 0, {'error': str(e)}


def show(code, verdict, msg):
    icon = f'{G}✓{X}' if verdict else f'{R}✗{X}'
    print(f'    {icon} {code} — {msg}')
    RESULTS.append((code, verdict, msg))


def db_sizes():
    """Baca master ukuran langsung dari Mongo (bukan lewat API) — bukti mentah."""
    from pymongo import MongoClient
    env = (Path(__file__).resolve().parent.parent / 'backend' / '.env').read_text()
    mongo_url = db_name = None
    for line in env.splitlines():
        if line.startswith('MONGO_URL='):
            mongo_url = line.split('=', 1)[1].strip().strip('"').strip("'")
        if line.startswith('DB_NAME='):
            db_name = line.split('=', 1)[1].strip().strip('"').strip("'")
    db = MongoClient(mongo_url)[db_name or 'test_database']
    return db, list(db.rahaza_sizes.find({}, {'_id': 0, 'id': 1, 'code': 1, 'name': 1}))


def main():
    print(f'\n{B}=================================================================={X}')
    print(f'  {Y}POC{X} — R&D → PO: apakah ukuran bebas merusak master / memblokir PO?')
    print(f'{B}=================================================================={X}')

    code, out = req('POST', '/auth/login', {'email': EMAIL, 'password': PASSWORD})
    tok = (out or {}).get('token') or (out or {}).get('access_token')
    if code != 200 or not tok:
        print(f'  {R}Login gagal HTTP {code}: {out}{X}')
        return 1

    db, sizes_before = db_sizes()
    print(f'    master ukuran SEBELUM: {sorted(s["code"] for s in sizes_before)}')

    stamp = str(int(time.time()))[-6:]
    scode = f'POCSZ{stamp}'
    code, style = req('POST', '/dewi/rnd/styles',
                      {'style_code': scode, 'style_name': 'POC Ukuran', 'status': 'draft',
                       'rnd_type': 'internal_product'}, tok)
    if code != 200:
        print(f'  {R}Tidak bisa membuat style HTTP {code}: {style}{X}')
        return 1
    sid = style['id']
    print(f'    style uji: {scode} ({sid})')

    try:
        # ── H1: ukuran bebas + size_map menandai yang belum dipadankan ──
        LABELS = ['All Size', '2XL', '28/30']
        code, sl = req('PUT', f'/dewi/rnd/styles/{sid}/size-list', {'size_list': LABELS}, tok)
        smap = {m['size']: m for m in (sl.get('size_map') or [])}
        show('H1', code == 200 and smap.get('All Size', {}).get('matched') is True
             and smap.get('2XL', {}).get('matched') is False
             and smap.get('28/30', {}).get('matched') is False,
             f"size_map: All Size matched={smap.get('All Size', {}).get('matched')} "
             f"(→{smap.get('All Size', {}).get('size_code')}), "
             f"2XL matched={smap.get('2XL', {}).get('matched')}, "
             f"28/30 matched={smap.get('28/30', {}).get('matched')} "
             f"| unmatched={sl.get('unmatched')}")

        # ── siapkan varian + naikkan status supaya bisa di-promote ──
        code, bulk = req('POST', '/dewi/rnd/variants/bulk', {
            'style_id': sid, 'style_code': scode,
            'colors': [{'code': 'NVY'}], 'sizes': LABELS,
        }, tok)
        if code != 200:
            show('SETUP', False, f'bulk varian gagal HTTP {code}: {bulk}')
            return 1
        req('POST', f'/dewi/rnd/styles/{sid}/submit-for-review', {}, tok)
        code_ap, _ = req('POST', f'/dewi/rnd/styles/{sid}/owner-approve', {}, tok)

        code_pr, promo = req('POST', f'/dewi/rnd/styles/{sid}/promote-to-production', {}, tok)
        if code_pr != 200:
            show('SETUP', False, f'promote gagal HTTP {code_pr}: {promo} (approve HTTP {code_ap})')
            return 1

        _, sizes_after = db_sizes()
        before_codes = {s['code'] for s in sizes_before}
        after_codes = {s['code'] for s in sizes_after}
        new_codes = sorted(after_codes - before_codes)

        # ── H2: master ukuran tercemar oleh label mentah ──
        # 'All Size' SUDAH matched ke ALLSIZE, jadi TIDAK BOLEH ada kode baru untuknya.
        dup_allsize = [c for c in new_codes if c.replace(' ', '') == 'ALLSIZE']
        show('H2a', len(dup_allsize) > 0,
             f"'All Size' sudah matched→ALLSIZE tapi promosi TETAP membuat kode baru "
             f"{dup_allsize} ⇒ master ukuran KEMBAR (BUG terbukti)"
             if dup_allsize else
             "'All Size' tidak membuat kode master baru (promosi menghormati size_map)")
        show('H2b', '2XL' in new_codes,
             f"'2XL' dibuat sebagai master baru walau 'XXL' sudah ada ⇒ satu ukuran dua kode "
             f"(BUG terbukti)" if '2XL' in new_codes else "'2XL' tidak membuat master baru")
        slashy = [c for c in new_codes if '/' in c or ' ' in c]
        show('H2c', len(slashy) > 0,
             f'kode master baru berisi spasi/garis miring: {slashy} ⇒ masuk ke SKU (BUG terbukti)'
             if slashy else 'tidak ada kode master dengan spasi/garis miring')
        print(f'    kode master BARU akibat promosi: {new_codes}')

        # ── H3: SKU FG hasil promosi memakai kode ukuran itu ──
        mv = list(db.rahaza_model_variants.find(
            {'model_id': promo.get('model_id')}, {'_id': 0, 'sku': 1, 'size_code': 1}))
        bad_sku = [v['sku'] for v in mv if ' ' in str(v.get('sku')) or '/' in str(v.get('sku'))]
        show('H3', len(bad_sku) > 0,
             f'SKU FG hasil promosi mengandung spasi/garis miring: {bad_sku} (BUG terbukti)'
             if bad_sku else f'SKU FG bersih: {[v["sku"] for v in mv]}')
        print(f'    SKU hasil promosi: {[v["sku"] for v in mv]}')

        # ── H4: apakah endpoint size-mapping sudah terdaftar? ──
        code_sm, sm = req('GET', '/dewi/rnd/size-mapping', None, tok)
        show('H4', code_sm == 200,
             f'GET /api/dewi/rnd/size-mapping HTTP {code_sm}'
             + ('' if code_sm == 200 else ' ⇒ router BELUM terdaftar (sisa sesi lalu)'))

    finally:
        # bersihkan artefak POC
        db.dewi_rnd_variants.delete_many({'style_id': sid})
        db.dewi_rnd_styles.delete_many({'id': sid})
        mids = [m['id'] for m in db.rahaza_models.find({'code': scode}, {'_id': 0, 'id': 1})]
        if mids:
            db.rahaza_model_variants.delete_many({'model_id': {'$in': mids}})
            db.rahaza_models.delete_many({'id': {'$in': mids}})
        db.rahaza_materials.delete_many({'code': {'$regex': f'^{scode}'}})
        print(f'    (artefak POC style {scode} dibersihkan)')

    print(f'\n{B}------------------------------------------------------------------{X}')
    proven = [c for c, v, _ in RESULTS if v and c.startswith('H2')]
    print(f'  Hipotesis kerusakan yang TERBUKTI: {proven or "tidak ada"}')
    print(f'  {Y}Kesimpulan:{X} layar "Padankan Ukuran" harus DISERTAI perbaikan promosi —')
    print('  promosi wajib memakai `size_map` (petunjuk B1) sebelum membuat ukuran baru.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
