"""Uji alur SATUAN & KONVERSI (UoM) untuk RnD · BOM · Costing — 2026-08-02.

Membuktikan laporan owner "satuan & konversinya belum ada di RnD untuk BOM-nya,
termasuk costing" sudah tertutup:

  1. Master material menerima gramasi (gsm) & lebar (cm) → konversi meter ⇄ kg.
  2. /api/dewi/rnd/uom-options memberi daftar satuan sah + faktornya.
  3. Riset Material RnD punya satuan harga (price_unit), bukan selalu "per meter".
  4. Sample Costing dihitung SERVER dengan konversi satuan; rincian baris tersimpan
     (dulu POST membuang fabric_items/trim_items dan menulis total 0).
  5. Tech Pack BOM menyimpan qty_base/unit_base + status konversi.
  6. HPP dari BOM (compute-from-bom) memakai qty terkonversi, bukan qty mentah.

SEMUA artefak uji dibersihkan di akhir (lihat cleanup()).
Kredensial: admin@garment.com / Admin@123
"""
import os
import sys
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def api_base():
    with open(os.path.join(ROOT, 'frontend', '.env')) as fh:
        for line in fh:
            if line.startswith('REACT_APP_BACKEND_URL='):
                return line.split('=', 1)[1].strip()
    raise SystemExit('REACT_APP_BACKEND_URL tidak ditemukan')


API = api_base()
PASS, FAIL = [], []


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f"{'✅' if cond else '❌'} {name}{'' if cond else f' → {detail}'}")


def main():
    s = requests.Session()
    r = s.post(f'{API}/api/auth/login', json={'email': 'admin@garment.com', 'password': 'Admin@123'}, timeout=30)
    tok = r.json().get('token') or r.json().get('access_token')
    if not tok:
        raise SystemExit(f'login gagal: {r.status_code} {r.text[:200]}')
    s.headers.update({'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'})

    created = {'materials': [], 'rnd_materials': [], 'costings': [], 'techpacks': [],
               'styles': [], 'sample_requests': []}

    try:
        # ── 1. Master material: kain per KG + gramasi & lebar ──────────────────
        fab = s.post(f'{API}/api/rahaza/materials', json={
            'code': 'ZZTEST-UOM-KAIN', 'name': 'ZZTEST Kain Rajut UOM', 'type': 'fabric',
            'unit': 'kg', 'unit_cost': 100000, 'gsm': 240, 'width_cm': 160,
        }, timeout=30)
        check('POST /rahaza/materials terima gsm & width_cm', fab.status_code == 200,
              f'{fab.status_code} {fab.text[:200]}')
        fabric = fab.json()
        created['materials'].append(fabric['id'])
        check('gsm & width_cm tersimpan', fabric.get('gsm') == 240 and fabric.get('width_cm') == 160, str(fabric)[:200])

        acc = s.post(f'{API}/api/rahaza/materials', json={
            'code': 'ZZTEST-UOM-KANCING', 'name': 'ZZTEST Kancing UOM', 'type': 'accessory',
            'unit': 'pcs', 'unit_cost': 500,
        }, timeout=30)
        check('Master aksesoris (pcs) dibuat', acc.status_code == 200, acc.text[:200])
        accessory = acc.json()
        created['materials'].append(accessory['id'])

        # ── 2. Daftar satuan sah + faktor ─────────────────────────────────────
        uo = s.get(f'{API}/api/dewi/rnd/uom-options', params={'material_id': fabric['id']}, timeout=30).json()
        units = {u['unit']: u['factor_to_base'] for u in uo.get('units', [])}
        # 1 m = 240 g/m² × 1.60 m = 384 g = 0.384 kg
        check('uom-options: 1 m ≈ 0.384 kg (via gramasi & lebar)',
              abs(units.get('m', 0) - 0.384) < 0.001, str(units)[:300])
        check('uom-options: satuan dasar kg terdaftar', abs(units.get('kg', 0) - 1.0) < 1e-9, str(units)[:200])
        check('uom-options: gram dikonversi global (0.001 kg)',
              abs(units.get('gram', 0) - 0.001) < 1e-9, str(units)[:200])

        # ── 3. Riset Material: harga per KG (bukan per meter) ─────────────────
        rm = s.post(f'{API}/api/dewi/rnd/materials', json={
            'material_code': 'ZZTEST-RND-KG', 'material_name': 'ZZTEST Riset Kain per Kg',
            'price_per_unit': 90000, 'price_unit': 'kg', 'category': 'test',
        }, timeout=30)
        check('POST /dewi/rnd/materials dengan price_unit=kg', rm.status_code == 200, rm.text[:200])
        rnd_mat = rm.json()
        created['rnd_materials'].append(rnd_mat['id'])
        check('price_unit & price_per_unit tersimpan',
              rnd_mat.get('price_unit') == 'kg' and rnd_mat.get('price_per_unit') == 90000, str(rnd_mat)[:250])
        check('price_per_meter TIDAK dicermin saat satuan kg (0)',
              float(rnd_mat.get('price_per_meter') or 0) == 0, str(rnd_mat)[:250])

        # ── 4. Sample Costing: konversi meter→kg & lusin→pcs ──────────────────
        payload_lines = {
            'fabric_items': [
                {'name': 'ZZTEST Kain Rajut UOM', 'material_id': fabric['id'], 'qty': 2, 'unit': 'm', 'unit_cost': 0},
                {'name': 'ZZTEST Kain gram', 'material_id': fabric['id'], 'qty': 500, 'unit': 'gram', 'unit_cost': 0},
            ],
            'trim_items': [
                {'name': 'ZZTEST Kancing UOM', 'material_id': accessory['id'], 'qty': 1, 'unit': 'lusin', 'unit_cost': 0},
                {'name': 'Harga manual menang', 'material_id': accessory['id'], 'qty': 2, 'unit': 'pcs', 'unit_cost': 1000},
            ],
            'labor_cost': 5000, 'overhead_cost': 1000,
        }
        pv = s.post(f'{API}/api/dewi/rnd/sample-costing/preview', json=payload_lines, timeout=30)
        check('POST /sample-costing/preview 200', pv.status_code == 200, pv.text[:200])
        calc = pv.json()
        f0, f1 = calc['fabric_items'][0], calc['fabric_items'][1]
        t0, t1 = calc['trim_items'][0], calc['trim_items'][1]
        # 2 m → 0.768 kg × 100.000 = 76.800
        check('2 m kain → 0.768 kg × Rp100.000 = Rp76.800',
              abs(f0['qty_priced'] - 0.768) < 1e-6 and f0['total_cost'] == 76800.0, str(f0)[:300])
        # 500 gram → 0.5 kg × 100.000 = 50.000 (BUKAN 500 kg = 50 juta)
        check('500 gram → 0.5 kg × Rp100.000 = Rp50.000 (bukan 50 juta)',
              abs(f1['qty_priced'] - 0.5) < 1e-9 and f1['total_cost'] == 50000.0, str(f1)[:300])
        # 1 lusin → 12 pcs × 500 = 6.000
        check('1 lusin kancing → 12 pcs × Rp500 = Rp6.000',
              abs(t0['qty_priced'] - 12) < 1e-9 and t0['total_cost'] == 6000.0, str(t0)[:300])
        check('Harga yang diketik user MENANG (2 × Rp1.000 = Rp2.000)',
              t1['price_source'] == 'line' and t1['total_cost'] == 2000.0, str(t1)[:300])
        check('Total material = 134.800 & total = 140.800',
              calc['total_material_cost'] == 134800.0 and calc['total_cost'] == 140800.0,
              f"mat={calc['total_material_cost']} total={calc['total_cost']}")

        # satuan yang tidak bisa dikonversi → 1:1 + peringatan (keputusan owner)
        bad = s.post(f'{API}/api/dewi/rnd/sample-costing/preview', json={
            'fabric_items': [{'name': 'ZZTEST Kain Rajut UOM', 'material_id': fabric['id'],
                              'qty': 3, 'unit': 'rol', 'unit_cost': 0}],
        }, timeout=30).json()
        b0 = bad['fabric_items'][0]
        check("Satuan 'rol' tanpa faktor → mismatch + tetap dihitung 1:1",
              b0['uom_status'] == 'mismatch' and b0['total_cost'] == 300000.0
              and len(bad.get('uom_warnings') or []) == 1, str(b0)[:300])

        # ── 4b. Simpan costing: rincian & total HARUS tersimpan ───────────────
        # Uji MEMBUAT sendiri style + sample request supaya tidak bergantung pada
        # data seed (container segar tidak punya sample request → dulu uji ini di-skip).
        st = s.post(f'{API}/api/dewi/rnd/styles', json={
            'style_code': 'ZZTEST-UOM-STY', 'style_name': 'ZZTEST Style UOM Costing',
            'category': 'kaos', 'status': 'draft',
        }, timeout=30)
        check('POST /dewi/rnd/styles 200 (prasyarat sample request)', st.status_code == 200, st.text[:250])
        style = st.json()
        created['styles'].append(style['id'])

        srq = s.post(f'{API}/api/dewi/rnd/sample-requests', json={
            'style_id': style['id'], 'quantity': 2, 'priority': 'normal',
            'notes': 'ZZTEST UOM sample request',
        }, timeout=30)
        check('POST /dewi/rnd/sample-requests 200', srq.status_code == 200, srq.text[:250])
        req = srq.json()
        created['sample_requests'].append(req['id'])

        body = {**payload_lines, 'sample_request_id': req['id'],
                'sample_code': req.get('sample_code', ''), 'notes': 'ZZTEST UOM'}
        cr = s.post(f'{API}/api/dewi/rnd/sample-costing', json=body, timeout=30)
        check('POST /sample-costing 200', cr.status_code == 200, cr.text[:250])
        doc = cr.json()
        created['costings'].append(doc['id'])
        check('Rincian fabric_items TERSIMPAN (dulu hilang)', len(doc.get('fabric_items') or []) == 2, str(doc)[:250])
        check('Rincian trim_items TERSIMPAN', len(doc.get('trim_items') or []) == 2, str(doc)[:250])
        check('total_material_cost tersimpan benar (bukan 0)',
              doc.get('total_material_cost') == 134800.0, str(doc.get('total_material_cost')))
        check('Costing tertaut ke sample request + style',
              doc.get('sample_request_id') == req['id'] and doc.get('sample_code') == req.get('sample_code'),
              str({k: doc.get(k) for k in ('sample_request_id', 'sample_code')})[:200])

        # baris tersimpan HARUS memuat jejak konversi (satuan asal + qty terkonversi)
        sf0 = (doc.get('fabric_items') or [{}])[0]
        check('Baris tersimpan memuat jejak konversi (unit, qty_priced, uom_status)',
              sf0.get('unit') == 'm' and abs(float(sf0.get('qty_priced') or 0) - 0.768) < 1e-6
              and sf0.get('uom_status') in ('fabric', 'base', 'uom', 'global'), str(sf0)[:300])

        # GET detail = sama dengan hasil simpan (dibaca UI saat buka rincian)
        gd = s.get(f'{API}/api/dewi/rnd/sample-costing/{doc["id"]}', timeout=30)
        check('GET /sample-costing/{id} konsisten dengan hasil simpan',
              gd.status_code == 200 and len(gd.json().get('fabric_items') or []) == 2
              and gd.json().get('total_cost') == 140800.0, f'{gd.status_code} {gd.text[:200]}')

        # muncul di daftar yang dibaca UI (filter per sample request)
        ls = s.get(f'{API}/api/dewi/rnd/sample-costing', params={'sample_request_id': req['id']}, timeout=30)
        rows = ls.json() if isinstance(ls.json(), list) else ls.json().get('items', [])
        check('Costing muncul di GET /sample-costing?sample_request_id= (dipakai UI)',
              ls.status_code == 200 and any(r.get('id') == doc['id'] for r in rows), str(rows)[:200])

        up = s.put(f'{API}/api/dewi/rnd/sample-costing/{doc["id"]}',
                   json={'labor_cost': 9000}, timeout=30)
        check('PUT /sample-costing hitung ulang total (134.800+9.000+1.000)',
              up.status_code == 200 and up.json().get('total_cost') == 144800.0,
              f'{up.status_code} {up.text[:200]}')
        check('PUT tidak menghilangkan rincian baris',
              len(up.json().get('fabric_items') or []) == 2 and len(up.json().get('trim_items') or []) == 2,
              str(up.json())[:250])

        # PUT dengan qty baru → server WAJIB konversi ulang (bukan pakai angka lama)
        up2 = s.put(f'{API}/api/dewi/rnd/sample-costing/{doc["id"]}', json={
            'fabric_items': [{'name': 'ZZTEST Kain Rajut UOM', 'material_id': fabric['id'],
                              'qty': 1, 'unit': 'm', 'unit_cost': 0}],
            'trim_items': [], 'labor_cost': 0, 'overhead_cost': 0,
        }, timeout=30)
        check('PUT qty 1 m → 0.384 kg × Rp100.000 = Rp38.400 (konversi ulang server)',
              up2.status_code == 200 and up2.json().get('total_material_cost') == 38400.0,
              f'{up2.status_code} {str(up2.json())[:250]}')

        # ── 5. Tech Pack BOM: qty_base tersimpan ──────────────────────────────
        tp = s.post(f'{API}/api/dewi/rnd/tech-packs', json={
            'style_code': 'ZZTEST-UOM', 'style_name': 'ZZTEST Style UOM', 'version': 'vtest',
            'title': 'ZZTEST', 'bom_items': [
                {'material': 'ZZTEST Kain Rajut UOM', 'material_id': fabric['id'], 'qty': 1.5, 'unit': 'm'},
                {'material': 'ZZTEST Kancing UOM', 'material_id': accessory['id'], 'qty': 1, 'unit': 'lusin'},
                {'material': 'Bahan tanpa master', 'qty': 2, 'unit': 'rol'},
            ],
        }, timeout=30)
        check('POST /tech-packs 200', tp.status_code == 200, tp.text[:250])
        tpd = tp.json()
        created['techpacks'].append(tpd['id'])
        b = tpd['bom_items']
        check('BOM techpack: 1.5 m → 0.576 kg', abs(b[0]['qty_base'] - 0.576) < 1e-6, str(b[0])[:250])
        check('BOM techpack: 1 lusin → 12 pcs', abs(b[1]['qty_base'] - 12) < 1e-9, str(b[1])[:250])
        check('BOM techpack: baris tanpa master ditandai unlinked',
              b[2]['uom_status'] == 'unlinked', str(b[2])[:250])

        # ── 6. HPP dari BOM memakai qty terkonversi ───────────────────────────
        hp = s.post(f'{API}/api/dewi/rnd/hpp-calculator/compute-from-bom', json={
            'bom_items': tpd['bom_items'], 'cmt_cost_per_pcs': 0,
            'overhead_pct': 0, 'margin_pct': 0,
        }, timeout=30)
        check('POST /hpp-calculator/compute-from-bom 200', hp.status_code == 200, hp.text[:250])
        hd = hp.json()
        # 0.576 kg × 100.000 = 57.600 ; 12 pcs × 500 = 6.000 → 63.600
        check('HPP dari BOM = 63.600 (0.576 kg + 12 pcs)',
              hd.get('bom_material_cost') == 63600.0, str(hd.get('bom_material_cost')))
        br = {x['material_name']: x for x in hd.get('material_breakdown', [])}
        kain = br.get('ZZTEST Kain Rajut UOM', {})
        check('Breakdown menampilkan qty asli & qty dihitung',
              kain.get('qty') == 1.5 and abs(kain.get('qty_costed', 0) - 0.576) < 1e-6, str(kain)[:300])

        # ── 7. Audit BOM produksi tetap hijau ────────────────────────────────
        au = s.get(f'{API}/api/rahaza/bom-uom-audit', timeout=60)
        check('GET /rahaza/bom-uom-audit 200', au.status_code == 200, au.text[:200])

    finally:
        for cid in created['costings']:
            s.delete(f'{API}/api/dewi/rnd/sample-costing/{cid}', timeout=30)
            gone = s.get(f'{API}/api/dewi/rnd/sample-costing/{cid}', timeout=30)
            check('DELETE /sample-costing benar-benar menghapus (GET → 404)', gone.status_code == 404,
                  f'{gone.status_code}')
        for rid in created['sample_requests']:
            s.delete(f'{API}/api/dewi/rnd/sample-requests/{rid}', timeout=30)
        for stid in created['styles']:
            s.delete(f'{API}/api/dewi/rnd/styles/{stid}', timeout=30)
        for tid in created['techpacks']:
            s.delete(f'{API}/api/dewi/rnd/tech-packs/{tid}', timeout=30)
        for mid in created['rnd_materials']:
            s.delete(f'{API}/api/dewi/rnd/materials/{mid}', timeout=30)
        for mid in created['materials']:
            s.delete(f'{API}/api/rahaza/materials/{mid}', timeout=30)
        # DELETE master material hanya menonaktifkan (soft delete) → dokumen uji
        # dibuang total supaya baseline master tidak bertambah.
        try:
            from pymongo import MongoClient
            from dotenv import load_dotenv
            load_dotenv(os.path.join(ROOT, 'backend', '.env'))
            mdb = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
            purged = mdb.rahaza_materials.delete_many({'code': {'$regex': '^ZZTEST-UOM'}}).deleted_count
            purged += mdb.dewi_rnd_styles.delete_many({'style_code': {'$regex': '^ZZTEST-UOM'}}).deleted_count
            purged += mdb.dewi_rnd_sample_costing.delete_many({'notes': 'ZZTEST UOM'}).deleted_count
        except Exception as exc:                                    # pragma: no cover
            purged = f'gagal: {exc}'
        print(f"\n[cleanup] costing={len(created['costings'])} techpack={len(created['techpacks'])} "
              f"rnd_material={len(created['rnd_materials'])} material={len(created['materials'])} "
              f"style={len(created['styles'])} sample_request={len(created['sample_requests'])} "
              f"(purge master: {purged}) dibersihkan")

    print(f"\n=== {len(PASS)} PASS / {len(FAIL)} FAIL ===")
    if FAIL:
        for f in FAIL:
            print(' FAIL:', f)
    return 1 if FAIL else 0


if __name__ == '__main__':
    sys.exit(main())
