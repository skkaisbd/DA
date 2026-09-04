#!/usr/bin/env python3
"""INV-RND2 — Padankan Ukuran + peringatan "harga master sudah berubah" di DAFTAR HPP.

Dipanggil dari `scripts/gate.sh`. Kriteria masuk gate hanya satu:
"kalau pemeriksaan ini hilang, apakah UANG / DATA bisa rusak tanpa ada yang tahu?"

| Kode      | Yang dijaga | Kalau rusak |
|-----------|-------------|-------------|
| SM-1..3   | Layar Padankan Ukuran melihat label dari `size_list` **dan** `dewi_rnd_variants.sizes` (varian hasil impor Excel), lalu benar-benar membuat `matched:true` | Ukuran "belum dipadankan" MEMBLOKIR PO produksi internal (`validate_internal_item` → 400) ⇒ alur R&D → PO mentok |
| SM-4      | Ukuran tetap teks BEBAS: `size_list` style TIDAK diubah oleh pemadanan | Kebijakan B1 (keputusan owner #3) diam-diam dibatalkan |
| SM-5      | Kode ukuran master hasil pembuatan selalu BERSIH (tanpa spasi/garis miring) | `'28/30'` masuk ke kode master ⇒ SKU FG jadi `STYLE-NVY-28/30` |
| SM-6      | Sekali klik "Padankan Semua" menghabiskan seluruh sisa | Layar ada tapi tidak menyelesaikan apa pun |
| SM-7      | **INTI:** setelah dipadankan, promosi ke produksi TIDAK membuat ukuran master baru dan SKU-nya bersih | Master ukuran KEMBAR (`ALLSIZE` + `ALL SIZE`) ⇒ stok & SKU pecah, tak bisa ditelusuri |
| SM-8      | Pemadanan idempoten + input salah ditolak (404/400) | Master ukuran membengkak tiap klik |
| ST-1..3   | Daftar HPP menandai baris yang harga masternya sudah berubah, dan angkanya SAMA dengan `/stale-check` | Harga jual ditetapkan dari HPP yang sudah basi tanpa ada yang tahu |
| ST-4      | **UANG:** perubahan harga master TIDAK menggeser satu rupiah pun angka HPP tersimpan | Angka historis berubah sendiri ⇒ laporan & harga jual tidak bisa dipercaya |
| ST-5      | Dokumen HPP LAMA (tanpa `cost_lines`) & baris `manual` tidak pernah ditandai basi | Peringatan palsu di mana-mana ⇒ orang berhenti mempercayainya |

Jalankan: python scripts/verify_rnd_size_mapping_stale.py
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('VERIFY_BASE', 'http://localhost:8001')
EMAIL = os.environ.get('VERIFY_EMAIL', 'admin@garment.com')
PASSWORD = os.environ.get('VERIFY_PASSWORD', 'Admin@123')

G, R, Y, B, X = '\033[92m', '\033[91m', '\033[93m', '\033[1m', '\033[0m'
FINDINGS = []
CHECKED = 0


def req(method, path, body=None, token=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(f'{BASE}{path}', data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(r, timeout=90) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {'detail': raw[:300]}


def inv(code, ok, msg):
    global CHECKED
    CHECKED += 1
    if ok:
        print(f'    {G}✓{X} {code} — {msg}')
    else:
        print(f'    {R}✗ {code} — {msg}{X}')
        FINDINGS.append(f'{code}: {msg}')
    return ok


def _db():
    """Mongo langsung — untuk BUKTI MENTAH (master ukuran, harga master)."""
    from pathlib import Path
    from pymongo import MongoClient
    env = (Path(__file__).resolve().parent.parent / 'backend' / '.env').read_text()
    url = name = None
    for line in env.splitlines():
        if line.startswith('MONGO_URL='):
            url = line.split('=', 1)[1].strip().strip('"').strip("'")
        if line.startswith('DB_NAME='):
            name = line.split('=', 1)[1].strip().strip('"').strip("'")
    return MongoClient(url)[name or 'test_database']


def main():
    print(f'\n{B}=================================================================={X}')
    print(f'  {Y}INV-RND2{X} — Padankan Ukuran · harga master basi di DAFTAR HPP (UANG)')
    print(f'{B}=================================================================={X}')

    code, out = req('POST', '/api/auth/login', {'email': EMAIL, 'password': PASSWORD})
    if code != 200:
        print(f'  {R}Login gagal (HTTP {code}) — gate tidak bisa dijalankan.{X}')
        return 1
    tok = (out or {}).get('access_token') or (out or {}).get('token')

    db = _db()
    stamp = str(int(time.time()))[-6:]
    scode = f'GATE{stamp}'
    # Label yang SENGAJA tidak ada di master: unik per-run supaya gate tidak
    # bergantung pada sisa data run sebelumnya.
    LBL_NEW = f'{stamp[-2:]}/{stamp[:2]}'      # mis. '76/15' — mengandung garis miring
    LBL_ALIAS = 'Free Size'                    # harus dipadankan ke ALLSIZE lewat alias
    made = {'hpps': [], 'sizes': [], 'models': []}

    code, style = req('POST', '/api/dewi/rnd/styles',
                      {'style_code': scode, 'style_name': 'Gate Padankan Ukuran',
                       'status': 'draft', 'rnd_type': 'internal_product'}, tok)
    if code != 200:
        print(f'  {R}Tidak bisa membuat style uji (HTTP {code}: {style}){X}')
        return 1
    sid_ = style['id']

    price_backup = None
    try:
        # ═════════════ BAGIAN 1 — PADANKAN UKURAN ═════════════
        SIZES = ['M', LBL_ALIAS, LBL_NEW]
        code_sl, sl = req('PUT', f'/api/dewi/rnd/styles/{sid_}/size-list',
                          {'size_list': SIZES}, tok)
        smap = {m['size']: m for m in (sl or {}).get('size_map') or []}
        inv('SM-1', code_sl == 200 and smap.get('M', {}).get('matched') is True
            and smap.get(LBL_NEW, {}).get('matched') is False,
            f"style menyimpan ukuran bebas; 'M' matched, '{LBL_NEW}' belum dipadankan "
            f"(unmatched={(sl or {}).get('unmatched')})")

        # varian memakai ukuran yang sama → inilah yang benar-benar dipromosikan
        code_b, bulk = req('POST', '/api/dewi/rnd/variants/bulk', {
            'style_id': sid_, 'style_code': scode,
            'colors': [{'code': 'NVY'}], 'sizes': SIZES,
        }, tok)

        code_ov, ov = req('GET', f'/api/dewi/rnd/size-mapping?style_id={sid_}', None, tok)
        labels = [i['label'] for i in (ov or {}).get('items') or []]
        target = next((i for i in (ov or {}).get('items') or [] if i['label'] == LBL_NEW), None)
        inv('SM-2', code_ov == 200 and LBL_NEW in labels and target is not None
            and target['used_by_count'] >= 1 and target['from_variants'] is True,
            f"ringkasan melihat '{LBL_NEW}' (dipakai {(target or {}).get('used_by_count')} style, "
            f"terbaca juga dari varian={(target or {}).get('from_variants')}); "
            f"varian bulk HTTP {code_b}, {len((bulk or {}).get('variants') or [])} varian")

        # 'Free Size' harus SUDAH matched otomatis lewat alias baku (ALLSIZE)
        matched_labels = {m['label']: m for m in (ov or {}).get('matched') or []}
        inv('SM-3', LBL_ALIAS in matched_labels
            and matched_labels[LBL_ALIAS]['code'] == 'ALLSIZE',
            f"'{LBL_ALIAS}' dipadankan otomatis ke master "
            f"{matched_labels.get(LBL_ALIAS, {}).get('code')} (alias baku garmen)")

        sizes_before = {s['code'] for s in db.rahaza_sizes.find({}, {'_id': 0, 'code': 1})}
        code_ap, ap = req('POST', '/api/dewi/rnd/size-mapping/apply', {
            'mappings': [{'label': LBL_NEW, 'create_new': True}],
        }, tok)
        res0 = ((ap or {}).get('results') or [{}])[0]
        new_code = res0.get('code')
        if new_code:
            made['sizes'].append(new_code)

        # SM-4 — `size_list` style TIDAK BOLEH berubah (kebijakan B1)
        _, sl2 = req('GET', f'/api/dewi/rnd/styles/{sid_}/size-list', None, tok)
        smap2 = {m['size']: m for m in (sl2 or {}).get('size_map') or []}
        inv('SM-4', code_ap == 200 and (sl2 or {}).get('size_list') == SIZES
            and smap2.get(LBL_NEW, {}).get('matched') is True,
            f"pemadanan TIDAK mengubah size_list (tetap {(sl2 or {}).get('size_list')}) "
            f"tapi '{LBL_NEW}' kini matched={smap2.get(LBL_NEW, {}).get('matched')} "
            f"→ {smap2.get(LBL_NEW, {}).get('size_code')}")

        inv('SM-5', bool(new_code) and ' ' not in new_code and '/' not in new_code,
            f"kode master baru '{new_code}' bersih (tanpa spasi / garis miring) "
            f"dari label '{LBL_NEW}'")

        code_au, au = req('POST', '/api/dewi/rnd/size-mapping/auto',
                          {'style_id': sid_, 'create_missing': True}, tok)
        for r_ in ((au or {}).get('results') or []):
            if r_.get('code') and r_['code'] not in sizes_before:
                made['sizes'].append(r_['code'])
        inv('SM-6', code_au == 200 and (au or {}).get('unmatched_after') == 0,
            f"sekali klik: sisa {(au or {}).get('unmatched_before')} → "
            f"{(au or {}).get('unmatched_after')} belum dipadankan")

        # SM-8 — input salah ditolak, pemadanan ulang idempoten
        bad1, _ = req('POST', '/api/dewi/rnd/size-mapping/apply',
                      {'mappings': [{'label': LBL_NEW, 'size_id': 'tidak-ada'}]}, tok)
        bad2, _ = req('POST', '/api/dewi/rnd/size-mapping/apply', {'mappings': []}, tok)
        n_before = db.rahaza_sizes.count_documents({})
        req('POST', '/api/dewi/rnd/size-mapping/apply',
            {'mappings': [{'label': LBL_NEW, 'create_new': True}]}, tok)
        n_after = db.rahaza_sizes.count_documents({})
        inv('SM-8', bad1 == 404 and bad2 == 400 and n_before == n_after,
            f'size_id ngawur → HTTP {bad1}, daftar kosong → HTTP {bad2}, '
            f'padankan ulang idempoten (master ukuran {n_before} → {n_after})')

        # ═════════════ SM-7 — INTI: promosi tidak mencemari master ═════════════
        req('POST', f'/api/dewi/rnd/styles/{sid_}/submit-for-review', {}, tok)
        req('POST', f'/api/dewi/rnd/styles/{sid_}/owner-approve', {}, tok)
        codes_pre = {s['code'] for s in db.rahaza_sizes.find({}, {'_id': 0, 'code': 1})}
        code_pr, promo = req('POST', f'/api/dewi/rnd/styles/{sid_}/promote-to-production', {}, tok)
        if promo and promo.get('model_id'):
            made['models'].append(promo['model_id'])
        codes_post = {s['code'] for s in db.rahaza_sizes.find({}, {'_id': 0, 'code': 1})}
        skus = [v['sku'] for v in db.rahaza_model_variants.find(
            {'model_id': (promo or {}).get('model_id')}, {'_id': 0, 'sku': 1})]
        dirty = [s for s in skus if ' ' in s or '/' in s]
        inv('SM-7', code_pr == 200 and codes_post == codes_pre and not dirty and skus,
            f'promosi TIDAK menambah ukuran master (baru: '
            f'{sorted(codes_post - codes_pre) or "tidak ada"}) & {len(skus)} SKU bersih: '
            f'{skus[:3]}' + (f' — KOTOR: {dirty}' if dirty else ''))

        # ═════════════ BAGIAN 2 — HARGA MASTER BASI DI DAFTAR ═════════════
        _, mopts = req('GET', '/api/dewi/rnd/material-options', None, tok)
        priced = next((m for m in (mopts or []) if float(m.get('unit_cost') or 0) > 0), None)
        if not priced:
            inv('ST-setup', False, 'tidak ada material master berharga — bagian UANG dilewati')
        else:
            mid = priced['material_id']
            lines = [
                {'label': 'Baris Master', 'source': 'master',
                 'material_id': mid, 'qty': 2, 'unit': 'pcs'},
                {'label': 'Baris Manual', 'source': 'manual',
                 'qty': 1, 'unit': 'pcs', 'unit_cost_used': 7000},
            ]
            code_c, hpp = req('POST', '/api/dewi/rnd/hpp-calculator', {
                'hpp_code': f'HPP-GATE{stamp}', 'style_id': sid_, 'cost_lines': lines,
                'cmt_cost_per_pcs': 10000, 'overhead_pct': 10, 'margin_pct': 30,
            }, tok)
            if code_c != 200:
                inv('ST-setup', False, f'gagal membuat HPP uji HTTP {code_c}: {hpp}')
            else:
                made['hpps'].append(hpp['id'])
                saved = {
                    'direct': round(float(hpp['direct_cost']), 2),
                    'hpp': round(float(hpp['hpp_total']), 2),
                    'sell': round(float(hpp['selling_price_proposal']), 2),
                    'lines': [round(float(l.get('line_cost') or 0), 2)
                              for l in (hpp.get('cost_lines') or [])],
                }

                _, lst0 = req('GET', f'/api/dewi/rnd/hpp-calculator?style_id={sid_}', None, tok)
                row0 = next((r for r in (lst0 or []) if r['id'] == hpp['id']), {})
                inv('ST-1', row0.get('stale_count') == 0 and row0.get('stale_checked_lines') == 1,
                    f"daftar HPP baru: stale_count={row0.get('stale_count')} "
                    f"(baris diperiksa {row0.get('stale_checked_lines')} — hanya sumber master, "
                    f"baris manual dilewati)")

                # ── harga master DIUBAH di belakang HPP ini ──
                mdoc = db.rahaza_materials.find_one({'id': mid}, {'_id': 0})
                price_backup = (mid, mdoc.get('unit_cost'))
                new_price = round(float(mdoc.get('unit_cost') or 0) + 1234, 2)
                db.rahaza_materials.update_one({'id': mid}, {'$set': {'unit_cost': new_price}})

                _, lst1 = req('GET', f'/api/dewi/rnd/hpp-calculator?style_id={sid_}', None, tok)
                row1 = next((r for r in (lst1 or []) if r['id'] == hpp['id']), {})
                sline = ((row1.get('stale_lines') or [{}])[0])
                inv('ST-2', row1.get('stale_count') == 1
                    and abs(float(row1.get('stale_delta_total') or 0) - 1234) < 0.01
                    and sline.get('direction') == 'naik',
                    f"setelah harga master naik 1.234: stale_count={row1.get('stale_count')}, "
                    f"delta_total={row1.get('stale_delta_total')}, arah={sline.get('direction')}, "
                    f"baris='{sline.get('label')}'")

                code_sc, sc = req('GET', f"/api/dewi/rnd/hpp-calculator/{hpp['id']}/stale-check",
                                  None, tok)
                inv('ST-3', code_sc == 200
                    and sc.get('stale_count') == row1.get('stale_count')
                    and abs(float((sc.get('stale_lines') or [{}])[0].get('delta') or 0)
                            - float(sline.get('delta') or 0)) < 0.01,
                    f"DAFTAR dan FORM sepakat: daftar {row1.get('stale_count')} baris basi vs "
                    f"stale-check {sc.get('stale_count')} baris, delta sama")

                # ── ST-4: UANG — angka tersimpan TIDAK BOLEH bergeser ──
                after = {
                    'direct': round(float(row1.get('direct_cost') or 0), 2),
                    'hpp': round(float(row1.get('hpp_total') or 0), 2),
                    'sell': round(float(row1.get('selling_price_proposal') or 0), 2),
                    'lines': [round(float(l.get('line_cost') or 0), 2)
                              for l in (row1.get('cost_lines') or [])],
                }
                inv('ST-4', after == saved,
                    f"harga master berubah TAPI angka HPP tersimpan tetap: direct "
                    f"{saved['direct']}→{after['direct']}, hpp {saved['hpp']}→{after['hpp']}, "
                    f"jual {saved['sell']}→{after['sell']}, baris {saved['lines']}→{after['lines']}")

                # ── ST-5: dokumen LAMA & baris manual tidak pernah ditandai ──
                _, legacy = req('POST', '/api/dewi/rnd/hpp-calculator', {
                    'hpp_code': f'HPP-GATELEG{stamp}', 'style_id': sid_, 'use_bom': False,
                    'fabric_usage_per_pcs': 2, 'fabric_price_per_meter': 50000,
                    'accessories_cost': [{'name': 'Label', 'unit_cost': 500, 'qty': 2}],
                    'cmt_cost_per_pcs': 10000, 'overhead_pct': 10, 'margin_pct': 30,
                }, tok)
                made['hpps'].append(legacy['id'])
                _, lst2 = req('GET', f'/api/dewi/rnd/hpp-calculator?style_id={sid_}', None, tok)
                rowl = next((r for r in (lst2 or []) if r['id'] == legacy['id']), {})
                inv('ST-5', rowl.get('cost_lines_legacy') is True
                    and rowl.get('stale_count') == 0
                    and rowl.get('stale_checked_lines') == 0
                    and abs(float(rowl.get('hpp_total') or 0) - 122100.0) < 0.01,
                    f"dokumen HPP lama: legacy={rowl.get('cost_lines_legacy')}, "
                    f"stale_count={rowl.get('stale_count')} (0 baris diperiksa — semua manual), "
                    f"hpp_total {rowl.get('hpp_total')} tetap 122100")
    finally:
        if price_backup:
            db.rahaza_materials.update_one({'id': price_backup[0]},
                                           {'$set': {'unit_cost': price_backup[1]}})
        for hid in made['hpps']:
            req('DELETE', f'/api/dewi/rnd/hpp-calculator/{hid}', None, tok)
        _, vs = req('GET', f'/api/dewi/rnd/variants?style_id={sid_}', None, tok)
        for v in (vs or []):
            req('DELETE', f"/api/dewi/rnd/variants/{v['id']}", None, tok)
        req('DELETE', f'/api/dewi/rnd/styles/{sid_}', None, tok)
        db.dewi_rnd_styles.delete_many({'id': sid_})
        for mid_ in made['models']:
            db.rahaza_model_variants.delete_many({'model_id': mid_})
            db.rahaza_models.delete_many({'id': mid_})
        # Sesi #33 — riwayat harga material uji ikut dibuang (anti baris YATIM di
        # layar Riwayat Harga Barang; dijaga INV-F38 C16).
        _mids_uji = [m['id'] for m in db.rahaza_materials.find(
            {'code': {'$regex': f'^{scode}'}}, {'_id': 0, 'id': 1})]
        if _mids_uji:
            db.rahaza_material_cost_history.delete_many({'material_id': {'$in': _mids_uji}})
        db.rahaza_materials.delete_many({'code': {'$regex': f'^{scode}'}})
        # ukuran master yang DIBUAT gate ini dibuang lagi (jangan tinggalkan sampah)
        if made['sizes']:
            db.rahaza_sizes.delete_many({'code': {'$in': made['sizes']},
                                         'created_from': 'rnd_size_mapping'})
        # size_map style demo dipulihkan agar tidak menunjuk ukuran yang sudah dibuang
        db.dewi_rnd_styles.update_many(
            {'size_map.size_code': {'$in': made['sizes']}},
            {'$unset': {'size_map': ''}})

    print(f'\n{B}------------------------------------------------------------------{X}')
    print(f'  INV-RND2: {CHECKED} invarian diperiksa — {len(FINDINGS)} temuan')
    if FINDINGS:
        for f_ in FINDINGS:
            print(f'  {R}· {f_}{X}')
        print(f'  {R}{B}✗ INV-RND2 MERAH{X}')
        return 1
    print(f'  {G}{B}✓ INV-RND2 HIJAU — alur R&D→PO tidak mentok & UANG HPP tidak bergeser.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
