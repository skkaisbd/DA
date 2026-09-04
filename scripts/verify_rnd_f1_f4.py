#!/usr/bin/env python3
"""Verifikasi gabungan R&D F1–F4 (proposal PROPOSAL_RND_WARNA_UKURAN_TECHPACK_HPP.md).

SATU skrip, satu kali jalan — menguji langsung lewat HTTP seperti pemakai sungguhan
(bukan memanggil fungsi internal), supaya yang dibuktikan adalah perilaku API.

Jalankan:  python scripts/verify_rnd_f1_f4.py [--only F1]
"""
import argparse
import json
import uuid
import os
import sys
import time
import urllib.error
import urllib.request

BASE = os.environ.get('VERIFY_BASE', 'http://localhost:8001')
EMAIL = os.environ.get('VERIFY_EMAIL', 'admin@garment.com')
PASSWORD = os.environ.get('VERIFY_PASSWORD', 'Admin@123')

G, R, Y, B, X = '\033[92m', '\033[91m', '\033[93m', '\033[1m', '\033[0m'
RESULTS = []


def req(method, path, body=None, token=None, expect=None):
    url = f'{BASE}{path}'
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header('Content-Type', 'application/json')
    if token:
        r.add_header('Authorization', f'Bearer {token}')
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            raw = resp.read().decode()
            code, payload = resp.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = {'detail': raw[:300]}
        code = e.code
    if expect is not None and code != expect:
        raise AssertionError(f'{method} {path} → HTTP {code} (harap {expect}): {payload}')
    return code, payload


def check(name, ok, detail=''):
    RESULTS.append((name, bool(ok), detail))
    mark = f'{G}✓{X}' if ok else f'{R}✗{X}'
    print(f'  {mark} {name}' + (f'  {Y}{detail}{X}' if detail else ''))
    return bool(ok)


def login():
    _, out = req('POST', '/api/auth/login', {'email': EMAIL, 'password': PASSWORD}, expect=200)
    return out['access_token'] if 'access_token' in out else out['token']


def ensure_style(tok, code, name):
    _, styles = req('GET', f'/api/dewi/rnd/styles?search={code}', token=tok, expect=200)
    for s in styles:
        if s.get('style_code') == code:
            return s
    _, s = req('POST', '/api/dewi/rnd/styles',
               {'style_code': code, 'style_name': name, 'category': 'Verify',
                'status': 'draft'}, token=tok, expect=200)
    return s


def cleanup_variants(tok, style_id):
    _, vs = req('GET', f'/api/dewi/rnd/variants?style_id={style_id}', token=tok, expect=200)
    for v in vs:
        req('DELETE', f"/api/dewi/rnd/variants/{v['id']}", token=tok)


# ══════════════════════════════════════════════════════════════════════════════
def test_f1(tok):
    print(f'\n{B}▶ F1 — Warna multi (fan-out) · master inline · SKU kanonik · anti-kembar{X}')
    # Kode warna harus benar-benar unik antar-run, kalau tidak POST color-options
    # kena 409 dan seluruh rangkaian F1 gagal berantai (temuan testing agent).
    stamp = str(int(time.time()))[-5:]
    uniq = uuid.uuid4().hex[:4].upper()
    style = ensure_style(tok, f'VRF{stamp}', 'Verify Hoodie')
    sid_ = style['id']
    cleanup_variants(tok, sid_)

    # US-1a: master warna terbaca dari layar R&D
    _, colors = req('GET', '/api/dewi/rnd/color-options', token=tok, expect=200)
    check('US2 master warna terbaca dari layar R&D (color-options)',
          isinstance(colors, list) and len(colors) >= 5,
          f'{len(colors)} warna')
    by_code = {c['code']: c for c in colors}

    # US-2: bikin warna BARU dari layar R&D → langsung ada di daftar
    newname = f'Verify Teal {uniq}'
    newcode = f'VT{uniq}'
    code, created = req('POST', '/api/dewi/rnd/color-options',
                        {'name': newname, 'code': newcode, 'hex': '#0E7490'}, token=tok)
    ok_created = code == 200 and created.get('color_id')
    _, colors2 = req('GET', '/api/dewi/rnd/color-options', token=tok, expect=200)
    check('US2 warna baru dibuat dari layar R&D & langsung muncul di dropdown',
          ok_created and any(c['code'] == newcode for c in colors2),
          f'{newcode} / {newname}')

    # US-2b: kode kembar ditolak dengan pesan jelas
    code_dup, dup = req('POST', '/api/dewi/rnd/color-options',
                        {'name': 'Lain lagi', 'code': newcode, 'hex': '#111111'}, token=tok)
    check('US2 kode warna kembar ditolak 409 + pesan jelas',
          code_dup == 409 and 'sudah dipakai' in str(dup.get('detail', '')),
          str(dup.get('detail', ''))[:70])

    # US-1: FAN-OUT — 1 kali simpan, 3 warna × 4 ukuran → 3 dokumen varian
    picks = [by_code.get('NVY'), by_code.get('HTM'), {'color_id': created.get('color_id')}]
    picks = [p for p in picks if p]
    sizes = ['XS', 'S', 'M', 'XL']
    code_bulk, out = req('POST', '/api/dewi/rnd/variants/bulk', {
        'style_id': sid_, 'sizes': sizes,
        'colors': [{'color_id': p.get('color_id')} for p in picks],
        'status': 'active', 'notes': 'verify fan-out',
    }, token=tok)
    ok_fanout = code_bulk == 200 and out.get('created_count') == len(picks)
    check(f'US1 fan-out: 1 simpan → {len(picks)} dokumen varian',
          ok_fanout, f"created_count={out.get('created_count')} detail={str(out.get('detail',''))[:60]}")

    # US-3: SKU kanonik {STYLE}-{COLOR_CODE}-{SIZE}
    _, vs = req('GET', f'/api/dewi/rnd/variants?style_id={sid_}', token=tok, expect=200)
    bad = []
    for v in vs:
        for s in v.get('sizes', []):
            want = f"{style['style_code']}-{v.get('color_code')}-{s['size']}".upper()
            if s.get('sku') != want:
                bad.append((s.get('sku'), want))
    check('US3 SKU mengikuti SSOT {STYLE}-{COLOR_CODE}-{SIZE}',
          len(vs) == len(picks) and not bad,
          f'{len(vs)*len(sizes)} SKU diperiksa' if not bad else f'salah: {bad[:2]}')

    # SKU tidak boleh lagi memakai 3 huruf NAMA warna
    navy = next((v for v in vs if v.get('color_code') == 'NVY'), None)
    check('US3 SKU tidak lagi memakai 3 huruf NAMA warna (bug §2.5.1 tutup)',
          navy is not None and navy['sizes'][0]['sku'].startswith(f"{style['style_code']}-NVY-"),
          navy['sizes'][0]['sku'] if navy else 'varian NVY tidak ada')

    # US-4: varian kembar ditolak (bulk & single)
    code_dup2, dup2 = req('POST', '/api/dewi/rnd/variants/bulk', {
        'style_id': sid_, 'sizes': sizes,
        'colors': [{'color_id': picks[0].get('color_id')}],
    }, token=tok)
    check('US4 bulk: warna yang sudah ada di style ditolak 409',
          code_dup2 == 409 and 'sudah punya varian' in str(dup2.get('detail', '')),
          str(dup2.get('detail', ''))[:70])

    code_dup3, dup3 = req('POST', '/api/dewi/rnd/variants', {
        'style_id': sid_, 'style_code': style['style_code'],
        'color': 'Navy', 'sizes': [{'size': 'M'}],
    }, token=tok)
    check('US4 single: varian kembar (style+warna) ditolak 409',
          code_dup3 == 409, str(dup3.get('detail', ''))[:70])

    code_dup4, dup4 = req('POST', '/api/dewi/rnd/variants/bulk', {
        'style_id': sid_, 'sizes': sizes,
        'colors': [{'code': 'PTH'}, {'code': 'PTH'}],
    }, token=tok)
    check('US4 warna kembar DI DALAM satu input ditolak 409',
          code_dup4 == 409 and 'kembar' in str(dup4.get('detail', '')).lower(),
          str(dup4.get('detail', ''))[:70])

    # US-5: SKU drift terdeteksi + bisa diperbaiki per baris
    _, legacy = req('POST', '/api/dewi/rnd/variants', {
        'style_id': sid_, 'style_code': style['style_code'], 'style_name': style['style_name'],
        'color': 'Kuning', 'sizes': [{'size': 'L', 'sku': f"{style['style_code']}-L-KUN"}],
    }, token=tok, expect=200)
    _, audit = req('GET', f'/api/dewi/rnd/variants/sku-audit?style_id={sid_}', token=tok, expect=200)
    found = next((i for i in audit['items'] if i['variant_id'] == legacy['id']), None)
    check('US5 laporan "SKU tidak sesuai SSOT" menemukan SKU terbalik',
          found is not None and found['drift_count'] == 1,
          f"drift_rows={audit['drift_rows']}")

    _, fixed = req('POST', f"/api/dewi/rnd/variants/{legacy['id']}/fix-sku", token=tok, expect=200)
    _, audit2 = req('GET', f'/api/dewi/rnd/variants/sku-audit?style_id={sid_}', token=tok, expect=200)
    still = next((i for i in audit2['items'] if i['variant_id'] == legacy['id']), None)
    check('US5 tombol perbaiki per baris membuat SKU jadi kanonik',
          fixed.get('changed_count') == 1 and (still is None or still['drift_count'] == 0),
          str(fixed.get('changed'))[:80])

    # Bonus: warna bahan R&D (§A akhir)
    mcode = f'VRFMAT{stamp}'
    code_m, mat = req('POST', '/api/dewi/rnd/materials', {
        'material_code': mcode, 'material_name': 'Fleece Verify',
        'price_per_unit': 85000, 'price_unit': 'kg',
        'colors': [{'code': 'NVY'}, {'code': 'HTM'}, {'name': newname}],
    }, token=tok)
    ok_mat = code_m == 200 and len(mat.get('colors') or []) == 3
    check('§A warna bahan R&D tersimpan & terpadan ke master',
          ok_mat, f"colors={[c.get('code') for c in (mat.get('colors') or [])]}")
    if code_m == 200:
        req('DELETE', f"/api/dewi/rnd/materials/{mat['id']}", token=tok)

    return sid_, style


# ══════════════════════════════════════════════════════════════════════════════
def test_f2(tok, style):
    print(f'\n{B}▶ F2 — Ukuran bebas per style (B1: padan otomatis ke master bila nama sama){X}')
    sid_ = style['id']

    # Default: fallback ke daftar lama bila style belum punya size_list
    _, d = req('GET', f'/api/dewi/rnd/styles/{sid_}/size-list', token=tok, expect=200)
    check('US1 style tanpa size_list tetap dapat daftar bawaan (fallback)',
          isinstance(d.get('size_list'), list) and len(d['size_list']) > 0,
          f"{d.get('size_list')} · source={d.get('source')}")

    # Simpan daftar bebas (termasuk yang tidak ada di master)
    wanted = ['S', 'M', 'L', 'All Size', '28/30']
    _, saved = req('PUT', f'/api/dewi/rnd/styles/{sid_}/size-list',
                   {'size_list': wanted + ['M']}, token=tok, expect=200)
    check('US1 daftar ukuran bebas tersimpan per style (kembar dibuang, urutan dijaga)',
          saved.get('size_list') == wanted, str(saved.get('size_list')))

    _, again = req('GET', f'/api/dewi/rnd/styles/{sid_}/size-list', token=tok, expect=200)
    check('US2 daftar yang sama dibaca ulang (dipakai Varian & Tech Pack)',
          again.get('size_list') == wanted and again.get('source') == 'style',
          f"source={again.get('source')}")

    smap = {m['size']: m for m in (again.get('size_map') or [])}
    check('US3 B1 — ukuran yang namanya sama dipadankan ke master (size_id terisi)',
          bool(smap.get('M', {}).get('size_id')) and smap.get('M', {}).get('matched') is True,
          f"M → size_id={str(smap.get('M', {}).get('size_id'))[:8]}…")
    check('US3 B1 — ukuran bebas yang tidak ada di master ditandai "belum dipadankan"',
          smap.get('28/30', {}).get('matched') is False
          and '28/30' in (again.get('unmatched') or []),
          f"unmatched={again.get('unmatched')}")

    # size_range dihitung otomatis
    check('US4 size_range dihitung otomatis dari daftar (tidak diketik lagi)',
          again.get('size_range') == f'{wanted[0]}-{wanted[-1]}',
          str(again.get('size_range')))
    check('US4 base_size otomatis diambil dari daftar (bukan teks bebas)',
          again.get('base_size') in wanted, str(again.get('base_size')))

    # Daftar kosong ditolak
    code_e, err = req('PUT', f'/api/dewi/rnd/styles/{sid_}/size-list', {'size_list': []}, token=tok)
    check('US1 daftar ukuran kosong ditolak 400 (biar tidak ada style tanpa ukuran)',
          code_e == 400, str(err.get('detail', ''))[:70])
    return wanted


# ══════════════════════════════════════════════════════════════════════════════
def test_f3(tok, style, size_list):
    print(f'\n{B}▶ F3 — Tech Pack: badge tanpa-master · size terikat · measurements ber-col_id{X}')
    sid_ = style['id']

    _, mopts = req('GET', '/api/dewi/rnd/material-options', token=tok, expect=200)
    linked = mopts[0] if mopts else None

    payload = {
        'style_id': sid_, 'style_code': style['style_code'], 'style_name': style['style_name'],
        'version': 'vVERIFY',
        'bom_items': [
            {'material': linked['name'] if linked else 'Kain X', 'material_id': linked['material_id'] if linked else '',
             'qty': 2, 'unit': 'meter'},
            {'material': 'Label woven custom TANPA MASTER', 'qty': 1, 'unit': 'pcs'},
        ],
        'fabrics': [{'name': 'CONDRU', 'role': 'main', 'color_code': 'NVY'}],
        'fabric_consumption': [{'size': 'M', 'fabric_role': 'main', 'length_cm': 463, 'width_cm': 150}],
        'size_columns': ['S', 'M', 'L'],
        'measurements': [{'point': 'LD', 'values': {'S': '50', 'M': '52', 'L': '54'}}],
        'colorways': [{'code': 'NVY'}, {'code': 'HTM'}],
        'base_size': 'M',
    }
    _, tp = req('POST', '/api/dewi/rnd/tech-packs', payload, token=tok, expect=200)

    boms = tp.get('bom_items') or []
    unlinked = [b for b in boms if not b.get('master_linked')]
    check('US1 baris BOM tanpa tautan master DITANDAI (master_linked=false)',
          len(unlinked) == 1 and unlinked[0].get('material', '').startswith('Label woven'),
          f"unlinked={len(unlinked)} · warn={str(unlinked[0].get('master_link_note',''))[:44] if unlinked else ''}")
    check('US1 ringkasan jumlah baris tanpa master tersedia untuk badge di layar',
          tp.get('bom_unlinked_count') == 1, f"bom_unlinked_count={tp.get('bom_unlinked_count')}")

    cols = tp.get('size_columns') or []
    ok_shape = all(isinstance(c, dict) and c.get('col_id') and c.get('label') for c in cols)
    check('US2 size_columns memakai {col_id,label} yang stabil',
          ok_shape and len(cols) == 3, str([c.get('label') for c in cols if isinstance(c, dict)]))

    meas = (tp.get('measurements') or [{}])[0]
    keyed_by_id = all(k in [c['col_id'] for c in cols] for k in (meas.get('values') or {}))
    check('US2 nilai measurement dikunci col_id (bukan nama kolom)',
          keyed_by_id and len(meas.get('values') or {}) == 3,
          f"values={meas.get('values')}")

    # ── INTI C3: ganti NAMA kolom → nilai TIDAK boleh hilang ──
    before = dict(meas.get('values') or {})
    renamed = [{'col_id': c['col_id'], 'label': ('EXTRA L' if c['label'] == 'L' else c['label'])} for c in cols]
    _, tp2 = req('PUT', f"/api/dewi/rnd/tech-packs/{tp['id']}",
                 {'size_columns': renamed, 'measurements': tp['measurements']}, token=tok, expect=200)
    after = dict(((tp2.get('measurements') or [{}])[0]).get('values') or {})
    labels2 = [c['label'] for c in (tp2.get('size_columns') or [])]
    check('US2 GANTI NAMA kolom ukuran TIDAK menghilangkan nilai (bug §2.3.3 tutup)',
          after == before and 'EXTRA L' in labels2,
          f'{len(before)} nilai sebelum → {len(after)} sesudah · label={labels2}')

    # Legacy techpack (size_columns = list string, values by label) harus ikut termigrasi
    _, legacy = req('POST', '/api/dewi/rnd/tech-packs', {
        'style_id': sid_, 'style_code': style['style_code'], 'version': 'vLEGACY',
        'size_columns': ['S', 'XL'],
        'measurements': [{'point': 'PJ', 'S': '60', 'XL': '66'}],
    }, token=tok, expect=200)
    lcols = {c['label']: c['col_id'] for c in (legacy.get('size_columns') or [])}
    lvals = ((legacy.get('measurements') or [{}])[0]).get('values') or {}
    check('US2 techpack lama (nilai per NAMA kolom) dipetakan ke col_id tanpa kehilangan',
          len(lvals) == 2 and lvals.get(lcols.get('S')) == '60' and lvals.get(lcols.get('XL')) == '66',
          f'values_legacy={bool(((legacy.get("measurements") or [{}])[0]).get("values_legacy"))}')

    cw = tp.get('colorways') or []
    check('US4 colorways tech pack terpadan ke master warna',
          len(cw) == 2 and all(c.get('color_id') for c in cw),
          str([c.get('code') for c in cw]))
    check('US5 baris kain menyimpan warna dari master',
          ((tp.get('fabrics') or [{}])[0]).get('color_name') in ('Navy', 'NVY'),
          str((tp.get('fabrics') or [{}])[0].get('color_name')))
    check('US3 size_range tech pack dihitung dari size_list style',
          bool(tp.get('size_range')), f"base={tp.get('base_size')} range={tp.get('size_range')}")

    req('DELETE', f"/api/dewi/rnd/tech-packs/{legacy['id']}", token=tok)
    return tp


# ══════════════════════════════════════════════════════════════════════════════
def test_f4(tok, style, tp):
    print(f'\n{B}▶ F4 — HPP hybrid: sumber PER BARIS (Master/Techpack/Manual) + D1 override{X}')
    sid_ = style['id']
    _, mopts = req('GET', '/api/dewi/rnd/material-options', token=tok, expect=200)
    priced = next((m for m in mopts if m.get('unit_cost', 0) > 0), None)

    lines = [
        {'label': 'Kain dari master', 'source': 'master',
         'material_id': (priced or {}).get('material_id', ''), 'qty': 2, 'unit': 'meter'},
        {'label': 'Label woven custom', 'source': 'manual', 'unit_cost_used': 1200, 'qty': 1, 'unit': 'pcs'},
        {'label': 'Bordir khusus', 'source': 'manual', 'unit_cost_used': 3500, 'qty': 1, 'unit': 'pcs'},
    ]
    _, prev = req('POST', '/api/dewi/rnd/hpp-calculator/preview', {
        'style_id': sid_, 'cost_lines': lines,
        'cmt_cost_per_pcs': 18000, 'cutting_cost_per_pcs': 1000,
        'packaging_cost_per_pcs': 500, 'overhead_pct': 10, 'margin_pct': 30,
    }, token=tok, expect=200)
    out_lines = prev.get('cost_lines') or []
    total_lines = round(sum(float(l.get('line_cost') or 0) for l in out_lines), 2)
    check('US1 Master + Manual bisa BERCAMPUR dalam satu HPP',
          len(out_lines) == 3 and len({l['source'] for l in out_lines}) == 2,
          f"sumber={sorted({l['source'] for l in out_lines})}")
    check('US1 material_cost = Σ SEMUA baris apa pun sumbernya',
          abs(float(prev.get('material_cost') or 0) - total_lines) < 0.01,
          f"material_cost={prev.get('material_cost')} Σbaris={total_lines}")

    # Tarik dari techpack BOM
    _, pulled = req('POST', '/api/dewi/rnd/hpp-calculator/cost-lines/from-techpack',
                    {'style_id': sid_}, token=tok, expect=200)
    tlines = pulled.get('cost_lines') or []
    check('US4 "Tarik dari Techpack BOM" menghasilkan baris bersumber techpack',
          len(tlines) >= 1 and all(l['source'] == 'techpack' for l in tlines),
          f'{len(tlines)} baris')

    # Campur 3 sumber sekaligus
    mixed = lines + tlines
    _, prev3 = req('POST', '/api/dewi/rnd/hpp-calculator/preview', {
        'style_id': sid_, 'cost_lines': mixed, 'cmt_cost_per_pcs': 18000,
    }, token=tok, expect=200)
    srcs = sorted({l['source'] for l in (prev3.get('cost_lines') or [])})
    check('US1 tiga sumber (Master+Techpack+Manual) sekaligus & totalnya benar',
          srcs == ['manual', 'master', 'techpack']
          and abs(float(prev3.get('material_cost') or 0)
                  - round(sum(float(l.get('line_cost') or 0) for l in prev3['cost_lines']), 2)) < 0.01,
          f'sumber={srcs} total={prev3.get("material_cost")}')

    # D1: override WAJIB beralasan
    bad = [{'label': 'Kain nego', 'source': 'master',
            'material_id': (priced or {}).get('material_id', ''), 'qty': 1, 'unit': 'meter',
            'override': True, 'unit_cost_used': 70000}]
    code_bad, errp = req('POST', '/api/dewi/rnd/hpp-calculator/preview',
                         {'style_id': sid_, 'cost_lines': bad}, token=tok)
    check('US2 D1 — override harga master TANPA alasan ditolak 400',
          code_bad == 400 and 'alasan' in str(errp.get('detail', '')).lower(),
          str(errp.get('detail', ''))[:70])

    good = [dict(bad[0], override_reason='Nego supplier turun 15rb (PO 2026-08)')]
    _, okp = req('POST', '/api/dewi/rnd/hpp-calculator/preview',
                 {'style_id': sid_, 'cost_lines': good}, token=tok, expect=200)
    l0 = (okp.get('cost_lines') or [{}])[0]
    check('US2 D1 — override BERALASAN diterima, alasan & harga master tercatat',
          l0.get('override') is True and l0.get('override_reason')
          and float(l0.get('unit_cost_master') or 0) > 0
          and float(l0.get('unit_cost_used')) == 70000,
          f"master={l0.get('unit_cost_master')} dipakai={l0.get('unit_cost_used')}")

    # Simpan + baca ulang
    _, saved = req('POST', '/api/dewi/rnd/hpp-calculator', {
        'hpp_code': f'HPP-VRF{int(time.time()) % 100000}', 'style_id': sid_,
        'style_code': style['style_code'], 'cost_lines': mixed,
        'cmt_cost_per_pcs': 18000, 'overhead_pct': 10, 'margin_pct': 30,
    }, token=tok, expect=200)
    check('US1 HPP hybrid tersimpan dengan cost_lines + total konsisten',
          len(saved.get('cost_lines') or []) == len(mixed)
          and float(saved.get('material_cost') or 0) > 0
          and saved.get('material_source') == 'cost_lines',
          f"hpp_total={saved.get('hpp_total')}")

    # US3: harga master berubah → baris ditandai basi
    if priced:
        _, stale = req('GET', f"/api/dewi/rnd/hpp-calculator/{saved['id']}/stale-check", token=tok, expect=200)
        check('US3 pemeriksaan "harga master sudah berubah?" tersedia',
              'stale_lines' in stale, f"stale={stale.get('stale_count')}")

    # US5: dokumen HPP LAMA (use_bom) tetap terbaca & angkanya tidak berubah
    _, legacy = req('POST', '/api/dewi/rnd/hpp-calculator', {
        'hpp_code': f'HPP-LEG{int(time.time()) % 100000}', 'style_id': sid_,
        'use_bom': False, 'fabric_usage_per_pcs': 2, 'fabric_price_per_meter': 50000,
        'accessories_cost': [{'name': 'Label', 'unit_cost': 500, 'qty': 2}],
        'cmt_cost_per_pcs': 10000, 'overhead_pct': 10, 'margin_pct': 30,
    }, token=tok, expect=200)
    expect_direct = 2 * 50000 + 1000 + 10000
    check('US5 dokumen HPP lama (manual/use_bom) angkanya TIDAK berubah',
          abs(float(legacy['direct_cost']) - expect_direct) < 0.01
          and abs(float(legacy['hpp_total']) - expect_direct * 1.1) < 0.01,
          f"direct={legacy['direct_cost']} (harap {expect_direct}) hpp={legacy['hpp_total']}")

    _, reread = req('GET', f'/api/dewi/rnd/hpp-calculator?style_id={sid_}', token=tok, expect=200)
    legacy_re = next((r for r in reread if r['id'] == legacy['id']), {})
    check('US5 HPP lama dibaca sebagai baris "manual" tanpa mengubah total',
          abs(float(legacy_re.get('hpp_total') or 0) - float(legacy['hpp_total'])) < 0.01,
          f"hpp_total={legacy_re.get('hpp_total')}")

    for hid in (saved['id'], legacy['id']):
        req('DELETE', f'/api/dewi/rnd/hpp-calculator/{hid}', token=tok)


# ══════════════════════════════════════════════════════════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='', help='F1 / F2 / F3 / F4 (default: semua)')
    args = ap.parse_args()
    only = args.only.upper()

    print(f'{B}VERIFIKASI R&D F1–F4{X}  base={BASE}  user={EMAIL}')
    tok = login()
    print(f'  {G}✓{X} login OK')

    style = None
    sizes = ['S', 'M', 'L', 'All Size', '28/30']
    tp = None
    if not only or only == 'F1':
        _, style = test_f1(tok)
    if style is None:
        style = ensure_style(tok, 'VRFBASE', 'Verify Base Style')
    if not only or only == 'F2':
        sizes = test_f2(tok, style)
    if not only or only == 'F3':
        tp = test_f3(tok, style, sizes)
    if not only or only == 'F4':
        if tp is None:
            _, tps = req('GET', f"/api/dewi/rnd/tech-packs?style_id={style['id']}", token=tok, expect=200)
            tp = tps[0] if tps else None
        test_f4(tok, style, tp)

    passed = sum(1 for _, ok, _ in RESULTS if ok)
    total = len(RESULTS)
    print(f'\n{B}══════════════════════════════════════════════════{X}')
    for name, ok, detail in RESULTS:
        if not ok:
            print(f'  {R}GAGAL{X} {name} — {detail}')
    verdict = f'{G}{B}HIJAU{X}' if passed == total else f'{R}{B}MERAH{X}'
    print(f'  {passed}/{total} lulus → VERDICT: {verdict}')
    sys.exit(0 if passed == total else 1)


if __name__ == '__main__':
    main()
