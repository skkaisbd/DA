#!/usr/bin/env python3
"""Bersihkan artefak data uji R&D (dipakai setelah verifikasi F1-F4).

Hanya menyentuh dokumen yang KODENYA jelas milik uji coba:
  style   : VRF* UIT* AUD* TPU* REN* GATE*
  material: UIM* VRFMAT*
  HPP     : HPPLEG* HPP-VRF* HPP-LEG* HPP-GATE*  (+ HPP milik style uji)
  warna   : master warna yang dibuat skrip uji (Verify Teal…, UI Test Olive…, Test Teal)
Data demo bootstrap TIDAK disentuh. Jalankan dengan --dry untuk melihat saja.
"""
import os
import re
import sys

from pymongo import MongoClient

STYLE_RX = re.compile(r'^(VRF|UIT|AUD|TPU|REN|GATE)', re.I)
MAT_RX = re.compile(r'^(UIM|VRFMAT)', re.I)
HPP_RX = re.compile(r'^(HPPLEG|HPP-VRF|HPP-LEG|HPP-GATE)', re.I)
COLOR_NAME_RX = re.compile(r'^(Verify Teal|UI Test Olive|Test Teal|Verify )', re.I)

dry = '--dry' in sys.argv
mongo_url = os.environ.get('MONGO_URL')
db_name = os.environ.get('DB_NAME')
if not mongo_url or not db_name:
    # baca dari backend/.env bila dijalankan di luar proses backend
    from pathlib import Path
    env = (Path(__file__).parent.parent / 'backend' / '.env').read_text()
    for line in env.splitlines():
        if line.startswith('MONGO_URL='):
            mongo_url = line.split('=', 1)[1].strip().strip('"').strip("'")
        if line.startswith('DB_NAME='):
            db_name = line.split('=', 1)[1].strip().strip('"').strip("'")

db = MongoClient(mongo_url)[db_name]

styles = [s for s in db.dewi_rnd_styles.find({}, {'_id': 0, 'id': 1, 'style_code': 1})
          if STYLE_RX.match(str(s.get('style_code') or ''))]
sids = [s['id'] for s in styles]
print(f'style uji     : {len(styles)} → {[s["style_code"] for s in styles]}')

counts = {}


def rm(coll, q, label):
    n = db[coll].count_documents(q)
    counts[label] = n
    if n and not dry:
        db[coll].delete_many(q)
    return n


if sids:
    rm('dewi_rnd_variants', {'style_id': {'$in': sids}}, 'varian')
    rm('dewi_rnd_tech_packs', {'style_id': {'$in': sids}}, 'tech pack')
    rm('dewi_rnd_hpp', {'style_id': {'$in': sids}}, 'HPP (per style uji)')
    rm('dewi_rnd_revisions', {'style_id': {'$in': sids}}, 'revisi')

hpp_codes = [h['hpp_code'] for h in db.dewi_rnd_hpp.find({}, {'_id': 0, 'hpp_code': 1})
             if HPP_RX.match(str(h.get('hpp_code') or ''))]
if hpp_codes:
    rm('dewi_rnd_hpp', {'hpp_code': {'$in': hpp_codes}}, 'HPP (per kode uji)')

mats = [m['id'] for m in db.dewi_rnd_materials.find({}, {'_id': 0, 'id': 1, 'material_code': 1})
        if MAT_RX.match(str(m.get('material_code') or ''))]
if mats:
    rm('dewi_rnd_materials', {'id': {'$in': mats}}, 'material R&D')

cols = [c['id'] for c in db.rahaza_colors.find({}, {'_id': 0, 'id': 1, 'name': 1})
        if COLOR_NAME_RX.match(str(c.get('name') or ''))]
if cols:
    # jangan hapus warna yang dipakai varian sungguhan
    used = {v.get('color_id') for v in db.dewi_rnd_variants.find({}, {'_id': 0, 'color_id': 1})}
    used |= {v.get('color_id') for v in db.rahaza_model_variants.find({}, {'_id': 0, 'color_id': 1})}
    safe = [c for c in cols if c not in used]
    rm('rahaza_colors', {'id': {'$in': safe}}, 'master warna uji')

if sids:
    rm('dewi_rnd_styles', {'id': {'$in': sids}}, 'style')

for k, v in counts.items():
    print(f'  {"(dry) " if dry else ""}hapus {k:24s}: {v}')
print('SELESAI' + (' (dry-run, tidak ada yang dihapus)' if dry else ''))
