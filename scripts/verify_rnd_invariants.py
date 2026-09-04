#!/usr/bin/env python3
"""INV-RND — invarian R&D yang cacatnya merusak DATA atau UANG tanpa terlihat.

Dipanggil dari `scripts/gate.sh`. Kriteria masuk gate hanya satu:
"kalau pemeriksaan ini hilang, apakah UANG / DATA bisa rusak tanpa ada yang tahu?"

| Kode        | Yang dijaga | Kalau rusak |
|-------------|-------------|-------------|
| INV-RND-1   | Ganti NAMA kolom ukuran tech pack tidak boleh menghilangkan nilai measurement (`col_id` stabil) | Spesifikasi ukuran produksi lenyap diam-diam ⇒ produk salah jahit |
| INV-RND-2   | Menghapus kolom ukuran tidak membuang nilainya (pindah ke `orphan_values`) | idem |
| INV-RND-3   | SKU varian R&D memakai urutan SSOT `{STYLE}-{COLOR}-{SIZE}` | SKU R&D tak pernah cocok SKU FG ⇒ stok & penjualan tak bisa ditelusuri |
| INV-RND-4   | Varian kembar (style+warna) ditolak | Dua varian sama ⇒ qty plan & SKU ganda |
| INV-RND-5   | UANG: HPP hybrid = Σ SEMUA baris `cost_lines` (master+techpack+manual) | Total HPP salah ⇒ harga jual salah |
| INV-RND-6   | UANG: override harga master WAJIB beralasan (kebijakan D1) | Harga berubah tanpa jejak |
| INV-RND-7   | UANG: dokumen HPP LAMA (`use_bom`) angkanya tidak bergeser | Angka historis berubah sendiri |
| INV-RND-8   | Baris BOM tanpa tautan master DITANDAI | HPP dari BOM salah diam-diam (keluhan asli owner) |

Semua diuji lewat HTTP seperti pemakai sungguhan, lalu datanya dibersihkan.
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
        with urllib.request.urlopen(r, timeout=60) as resp:
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


def main():
    print(f'\n{B}=================================================================={X}')
    print(f'  {Y}INV-RND{X} — Tech Pack col_id · SKU SSOT · varian kembar · HPP hybrid (UANG)')
    print(f'{B}=================================================================={X}')

    code, out = req('POST', '/api/auth/login', {'email': EMAIL, 'password': PASSWORD})
    if code != 200:
        print(f'  {R}Login gagal (HTTP {code}) — gate tidak bisa dijalankan.{X}')
        return 1
    tok = out.get('access_token') or out.get('token')

    stamp = str(int(time.time()))[-6:]
    scode = f'GATE{stamp}'
    code, style = req('POST', '/api/dewi/rnd/styles',
                      {'style_code': scode, 'style_name': 'Gate RnD Style', 'status': 'draft'}, tok)
    if code != 200:
        print(f'  {R}Tidak bisa membuat style uji (HTTP {code}: {style}){X}')
        return 1
    sid_ = style['id']
    made = {'style': sid_, 'tps': [], 'hpps': []}

    try:
        # ── INV-RND-1 & 2: measurements tidak boleh hilang ──
        _, tp = req('POST', '/api/dewi/rnd/tech-packs', {
            'style_id': sid_, 'style_code': scode, 'version': 'gate',
            'size_columns': ['S', 'M', 'XL'],
            'measurements': [{'point': 'LD', 'values': {'S': '50', 'M': '52', 'XL': '56'}},
                             {'point': 'PJ', 'values': {'S': '60', 'M': '62', 'XL': '66'}}],
        }, tok)
        made['tps'].append(tp['id'])
        cols = tp.get('size_columns') or []
        before = [dict(m.get('values') or {}) for m in (tp.get('measurements') or [])]
        n_before = sum(len(v) for v in before)

        shaped = all(isinstance(c, dict) and c.get('col_id') for c in cols)
        inv('INV-RND-1a', shaped and n_before == 6,
            f'size_columns ber-col_id & {n_before}/6 nilai measurement tersimpan')

        renamed = [{'col_id': c['col_id'],
                    'label': 'EXTRA LARGE' if c['label'] == 'XL' else c['label']} for c in cols]
        _, tp2 = req('PUT', f"/api/dewi/rnd/tech-packs/{tp['id']}",
                     {'size_columns': renamed, 'measurements': tp['measurements']}, tok)
        after = [dict(m.get('values') or {}) for m in (tp2.get('measurements') or [])]
        n_after = sum(len(v) for v in after)
        labels = [c['label'] for c in (tp2.get('size_columns') or [])]
        inv('INV-RND-1', after == before and 'EXTRA LARGE' in labels,
            f'ganti nama kolom XL→EXTRA LARGE: nilai {n_before} → {n_after} (harus sama, tidak yatim)')

        # hapus satu kolom → nilainya harus pindah ke orphan_values, bukan hilang
        kept = [c for c in renamed if c['label'] != 'S']
        gone = next(c for c in renamed if c['label'] == 'S')
        moved = []
        for m in tp2['measurements']:
            vals = dict(m.get('values') or {})
            orph = dict(m.get('orphan_values') or {})
            if gone['col_id'] in vals:
                orph['S'] = vals.pop(gone['col_id'])
            moved.append({**m, 'values': vals, 'orphan_values': orph})
        _, tp3 = req('PUT', f"/api/dewi/rnd/tech-packs/{tp['id']}",
                     {'size_columns': kept, 'measurements': moved}, tok)
        rows3 = tp3.get('measurements') or []
        n3 = sum(len(m.get('values') or {}) for m in rows3)
        n3orph = sum(len(m.get('orphan_values') or {}) for m in rows3)
        inv('INV-RND-2', n3 + n3orph == n_before,
            f'hapus kolom S: {n3} nilai aktif + {n3orph} cadangan = {n_before} (tidak ada yang dibuang)')

        # ── INV-RND-8: baris BOM tanpa master ditandai ──
        _, tp4 = req('PUT', f"/api/dewi/rnd/tech-packs/{tp['id']}", {
            'bom_items': [{'material': 'Baris tanpa master (gate)', 'qty': 1, 'unit': 'pcs'}],
        }, tok)
        items = tp4.get('bom_items') or []
        inv('INV-RND-8', len(items) == 1 and items[0].get('master_linked') is False
            and tp4.get('bom_unlinked_count') == 1,
            'baris BOM tanpa tautan master ditandai (master_linked=false + bom_unlinked_count)')

        # ── INV-RND-3 & 4: SKU SSOT + varian kembar ──
        _, bulk = req('POST', '/api/dewi/rnd/variants/bulk', {
            'style_id': sid_, 'style_code': scode,
            'colors': [{'code': 'NVY'}, {'code': 'HTM'}], 'sizes': ['S', 'M'],
        }, tok)
        vs = bulk.get('variants') or []
        wrong = [s['sku'] for v in vs for s in v.get('sizes', [])
                 if s['sku'] != f"{scode}-{v['color_code']}-{s['size']}".upper()]
        inv('INV-RND-3', len(vs) == 2 and not wrong,
            f'fan-out 2 warna → 2 varian, {len(vs) * 2} SKU semuanya {{STYLE}}-{{COLOR}}-{{SIZE}}'
            + (f' — SALAH: {wrong[:2]}' if wrong else ''))

        dup_code, dup = req('POST', '/api/dewi/rnd/variants/bulk', {
            'style_id': sid_, 'style_code': scode,
            'colors': [{'code': 'NVY'}], 'sizes': ['S'],
        }, tok)
        dup2_code, _ = req('POST', '/api/dewi/rnd/variants', {
            'style_id': sid_, 'style_code': scode, 'color': 'Navy', 'sizes': [{'size': 'M'}],
        }, tok)
        inv('INV-RND-4', dup_code == 409 and dup2_code == 409,
            f'varian kembar ditolak (bulk HTTP {dup_code}, tunggal HTTP {dup2_code})')

        # ── INV-RND-9: sku-audit harus TAHAN bentuk `sizes` daftar STRING ──
        # Importir Excel menulis sizes=['S','M'] (bukan dict). Pembaca yang
        # mengasumsikan dict akan 500 pada data impor sungguhan (terbukti 2026-08-07).
        body_str_sizes = {'style_id': sid_, 'style_code': scode, 'style_name': 'Gate RnD Style',
                          'color': 'Tosca', 'sizes': ['S', 'M']}
        code_s, vstr = req('POST', '/api/dewi/rnd/variants', body_str_sizes, tok)
        # Audit dijalankan TANPA filter style: harus tahan SEMUA bentuk `sizes` yang
        # benar-benar ada di database (termasuk 115 varian hasil impor Excel).
        code_a, aud = req('GET', '/api/dewi/rnd/variants/sku-audit', None, tok)
        inv('INV-RND-9', code_a == 200 and isinstance(aud, dict) and 'items' in aud,
            f'sku-audit tahan SEMUA bentuk `sizes` di DB — HTTP {code_a}, '
            f'{(aud or {}).get("checked_variants")} varian diperiksa')

        if code_s == 200:
            code_f, fx = req('POST', f"/api/dewi/rnd/variants/{vstr['id']}/fix-sku", None, tok)
            _, after_v = req('GET', f'/api/dewi/rnd/variants?style_id={sid_}', None, tok)
            mine = next((x for x in (after_v or []) if x['id'] == vstr['id']), {})
            rows = mine.get('sizes') or []
            ok_shape = all(isinstance(r, dict) for r in rows)
            ok_sku = all(str(r.get('sku', '')).upper()
                         == f"{scode}-{mine.get('color_code')}-{r.get('size')}".upper()
                         for r in rows)
            inv('INV-RND-9b', code_f == 200 and len(rows) == 2 and ok_shape and ok_sku,
                f'varian ber-`sizes` STRING dinaikkan ke bentuk objek + SKU kanonik '
                f'(HTTP {code_f}, {[r.get("sku") for r in rows]})')

        # ── INV-RND-5 & 6: UANG — HPP hybrid ──
        _, mopts = req('GET', '/api/dewi/rnd/material-options', None, tok)
        priced = next((m for m in mopts if float(m.get('unit_cost') or 0) > 0), None)
        lines = [
            {'label': 'Manual A', 'source': 'manual', 'qty': 2, 'unit': 'pcs', 'unit_cost_used': 1500},
            {'label': 'Manual B', 'source': 'manual', 'qty': 1, 'unit': 'pcs', 'unit_cost_used': 3500},
        ]
        if priced:
            lines.append({'label': 'Master', 'source': 'master',
                          'material_id': priced['material_id'], 'qty': 1, 'unit': 'pcs'})
        _, prev = req('POST', '/api/dewi/rnd/hpp-calculator/preview',
                      {'style_id': sid_, 'cost_lines': lines, 'cmt_cost_per_pcs': 5000,
                       'overhead_pct': 10, 'margin_pct': 30}, tok)
        got = prev.get('cost_lines') or []
        ssum = round(sum(float(l.get('line_cost') or 0) for l in got), 2)
        mc = round(float(prev.get('material_cost') or 0), 2)
        direct = round(float(prev.get('direct_cost') or 0), 2)
        inv('INV-RND-5', len(got) == len(lines) and abs(mc - ssum) < 0.01
            and abs(direct - (mc + 5000)) < 0.01,
            f'Σ{len(got)} baris = {ssum} = material_cost {mc}; direct_cost {direct} = material + CMT')

        bad_code, bad = req('POST', '/api/dewi/rnd/hpp-calculator/preview', {
            'style_id': sid_,
            'cost_lines': [{'label': 'Nego', 'source': 'master',
                            'material_id': (priced or {}).get('material_id', ''),
                            'qty': 1, 'unit': 'pcs', 'override': True, 'unit_cost_used': 1}],
        }, tok)
        inv('INV-RND-6', bad_code == 400 and 'alasan' in str(bad.get('detail', '')).lower(),
            f'override harga master tanpa alasan ditolak (HTTP {bad_code}) — kebijakan D1')

        # ── INV-RND-7: UANG — dokumen HPP lama tidak bergeser ──
        _, legacy = req('POST', '/api/dewi/rnd/hpp-calculator', {
            'hpp_code': f'HPP-GATE{stamp}', 'style_id': sid_, 'use_bom': False,
            'fabric_usage_per_pcs': 2, 'fabric_price_per_meter': 50000,
            'accessories_cost': [{'name': 'Label', 'unit_cost': 500, 'qty': 2}],
            'cmt_cost_per_pcs': 10000, 'overhead_pct': 10, 'margin_pct': 30,
        }, tok)
        made['hpps'].append(legacy['id'])
        want_direct = 2 * 50000 + 1000 + 10000
        want_hpp = round(want_direct * 1.1, 2)
        _, lst = req('GET', f'/api/dewi/rnd/hpp-calculator?style_id={sid_}', None, tok)
        re_read = next((r for r in lst if r['id'] == legacy['id']), {})
        inv('INV-RND-7',
            abs(float(legacy['direct_cost']) - want_direct) < 0.01
            and abs(float(legacy['hpp_total']) - want_hpp) < 0.01
            and abs(float(re_read.get('hpp_total') or 0) - want_hpp) < 0.01
            and len(re_read.get('cost_lines') or []) == 2,
            f'HPP lama: direct {legacy["direct_cost"]} (harap {want_direct}), '
            f'hpp {legacy["hpp_total"]} (harap {want_hpp}), dibaca sebagai 2 baris manual')

    finally:
        for hid in made['hpps']:
            req('DELETE', f'/api/dewi/rnd/hpp-calculator/{hid}', None, tok)
        for tid in made['tps']:
            req('DELETE', f'/api/dewi/rnd/tech-packs/{tid}', None, tok)
        _, vs = req('GET', f'/api/dewi/rnd/variants?style_id={sid_}', None, tok)
        for v in (vs or []):
            req('DELETE', f"/api/dewi/rnd/variants/{v['id']}", None, tok)
        req('DELETE', f'/api/dewi/rnd/styles/{sid_}', None, tok)

    print(f'\n{B}------------------------------------------------------------------{X}')
    print(f'  INV-RND: {CHECKED} invarian diperiksa — {len(FINDINGS)} temuan')
    if FINDINGS:
        for f_ in FINDINGS:
            print(f'  {R}· {f_}{X}')
        print(f'  {R}{B}✗ INV-RND MERAH{X}')
        return 1
    print(f'  {G}{B}✓ INV-RND HIJAU — DATA measurement & UANG HPP terjaga.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
