#!/usr/bin/env python3
"""_prove_master_produk_logic_gaps.py — BUKTIKAN cacat logika master produk internal.

Dipakai saat menyusun rencana perbaikan (permintaan owner 2026-08-10): "saya rasa ini
menyebabkan banyak error karena ada beberapa error logic". Dokumen rencana tidak boleh
berdiri di atas dugaan — jadi setiap klaim di `memory/AUDIT_MASTER_PRODUK_INTERNAL.md`
§5 dibuktikan di sini dengan data sungguhan lewat HTTP, lalu **dibersihkan**.

Yang dibuktikan:
  P1. Produk MANUAL (tanpa style R&D) ⇒ `rahaza_models.hpp` TIDAK ADA ⇒ FG-nya
      lahir `hpp = 0` ⇒ katalog marketing memakai HPP 0 (margin tidak bisa dihitung),
      dan TIDAK ADA cara mengisi HPP dari layar Master Produk.
  P2. `category` disalin ke FG saat FG dibuat, dan **tidak pernah diperbarui**:
      ubah kategori di master ⇒ FG (dan katalog yang mengambil darinya) tetap
      memakai kategori LAMA. Beda dengan HPP yang punya propagasi.
  P3. `category` adalah TEKS BEBAS: nilai di luar daftar dropdown diterima server.
  P4. `weight_gram` DIBACA dari model oleh `ensure_fg_material()` tetapi TIDAK PERNAH
      ditulis penulis mana pun ⇒ berat FG selalu 0.

Pakai::  python3 scripts/_prove_master_produk_logic_gaps.py
Aman: semua dokumen uji ditandai `__PROVE_MP__` dan dihapus di blok `finally`;
skrip mencetak sisa jejak (harus 0) dan jumlah dokumen akhir.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

from pymongo import MongoClient

API = 'http://localhost:8001/api'
MARK = '__PROVE_MP__'
G, R, Y, B, X, BOLD = ('\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[0m', '\033[1m')

_ok = _fail = 0


def call(method: str, path: str, tok: str | None = None, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={'Content-Type': 'application/json',
                 **({'Authorization': f'Bearer {tok}'} if tok else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:300].decode(errors='replace')


def show(cond: bool, code: str, claim: str, detail=''):
    global _ok, _fail
    if cond:
        _ok += 1
        print(f'  {G}[TERBUKTI]{X} {code} — {claim}'
              f'{f"  {Y}→ {detail}{X}" if detail else ""}')
    else:
        _fail += 1
        print(f'  {R}[TIDAK TERBUKTI]{X} {code} — {claim}'
              f'{f"  {Y}→ {detail}{X}" if detail else ""}')


def main() -> int:
    db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                     )[os.environ.get('DB_NAME', 'test_database')]
    st, log = call('POST', '/auth/login',
                   body={'email': 'admin@garment.com', 'password': 'Admin@123'})
    if st != 200:
        print(f'{R}login gagal HTTP {st}{X}')
        return 1
    tok = log['token']

    print(f'{B}{"=" * 92}{X}')
    print(f'  {BOLD}BUKTI CACAT LOGIKA — MASTER PRODUK INTERNAL DA{X}')
    print(f'{B}{"=" * 92}{X}')

    model_id = None
    try:
        # ── P3 + P1: buat produk MANUAL dengan kategori di LUAR daftar dropdown ──
        st, m = call('POST', '/rahaza/models', tok, {
            'code': 'ZZPROVE-MP', 'name': f'{MARK} Produk Uji',
            'category': 'Rok Lipit Sekolah',        # tidak ada di CATEGORIES frontend
            'description': MARK, 'material_kg_per_pcs': 0.4, 'bundle_size': 24})
        if st not in (200, 201):
            print(f'{R}gagal membuat model uji: HTTP {st} {m}{X}')
            return 1
        model_id = m['id']
        doc = db.rahaza_models.find_one({'id': model_id}, {'_id': 0})

        show(doc.get('category') == 'Rok Lipit Sekolah', 'P3',
             '`category` TEKS BEBAS — nilai di luar dropdown diterima server '
             '(tidak ada master kategori yang memvalidasi)',
             f'tersimpan: {doc.get("category")!r}')

        show('hpp' not in doc and 'retail_price' not in doc, 'P1a',
             'produk MANUAL lahir TANPA `hpp` dan TANPA harga jual — dan form Master '
             'Produk tidak punya kolomnya',
             f'kunci tersimpan: {sorted(doc.keys())}')

        show('weight_gram' not in doc, 'P4a',
             '`weight_gram` tidak ditulis penulis mana pun, padahal '
             '`ensure_fg_material()` membacanya dari model')

        # ── buat 1 varian ⇒ FG otomatis (SSOT) ──────────────────────────────
        color = db.rahaza_colors.find_one({'active': True}, {'_id': 0, 'id': 1, 'code': 1})
        size = db.rahaza_sizes.find_one({'active': {'$ne': False}}, {'_id': 0, 'id': 1, 'code': 1})
        st, gen = call('POST', f'/rahaza/models/{model_id}/variants/generate', tok,
                       {'color_ids': [color['id']], 'size_ids': [size['id']]})
        if st != 200:
            print(f'{R}generate varian gagal HTTP {st} {gen}{X}')
        sku = f"ZZPROVE-MP-{color['code']}-{size['code']}".upper()
        fg = db.rahaza_materials.find_one({'code': sku}, {'_id': 0}) or {}

        show(bool(fg), 'SSOT', 'varian melahirkan FG otomatis (code == SKU)', f'SKU={sku}')
        show(float(fg.get('hpp') or 0) == 0, 'P1b',
             'FG hasil produk manual lahir `hpp = 0` ⇒ katalog marketing memakai HPP 0 '
             '⇒ margin mustahil dihitung',
             f'FG.hpp={fg.get("hpp")}')
        show(float(fg.get('weight_gram') or 0) == 0, 'P4b',
             'FG lahir `weight_gram = 0` (dibaca dari field master yang tidak pernah ada) '
             '⇒ berat kirim/ongkir tidak bisa dipercaya',
             f'FG.weight_gram={fg.get("weight_gram")}')
        show(fg.get('category') == 'Rok Lipit Sekolah', 'P2a',
             '`category` model DISALIN ke FG saat FG dibuat',
             f'FG.category={fg.get("category")!r}')

        # ── P2: ubah kategori di master, lihat apakah FG ikut ────────────────
        st, _ = call('PUT', f'/rahaza/models/{model_id}', tok, {'category': 'Vest'})
        fg2 = db.rahaza_materials.find_one({'code': sku}, {'_id': 0}) or {}
        show(fg2.get('category') == 'Rok Lipit Sekolah', 'P2b',
             'kategori diubah di Master Produk (→ "Vest") tetapi FG TETAP kategori LAMA '
             '⇒ filter/grouping katalog marketing memakai nilai basi SELAMANYA',
             f'master=Vest · FG={fg2.get("category")!r}')

        # ── SKU tidak memuat kategori (permintaan owner) ─────────────────────
        show('VEST' not in (fg2.get('code') or '').upper(), 'P5',
             'SKU dibentuk hanya {MODEL}-{WARNA}-{SIZE} — kategori TIDAK ikut di SKU',
             f'SKU={fg2.get("code")}')
    finally:
        n = 0
        if model_id:
            n += db.rahaza_model_variants.delete_many({'model_id': model_id}).deleted_count
            n += db.rahaza_models.delete_many({'id': model_id}).deleted_count
        n += db.rahaza_materials.delete_many({'code': {'$regex': '^ZZPROVE-MP'}}).deleted_count
        n += db.rahaza_models.delete_many({'description': MARK}).deleted_count
        sisa = (db.rahaza_models.count_documents({'$or': [{'description': MARK},
                                                          {'code': 'ZZPROVE-MP'}]})
                + db.rahaza_materials.count_documents({'code': {'$regex': '^ZZPROVE-MP'}})
                + db.rahaza_model_variants.count_documents({'model_code': 'ZZPROVE-MP'}))
        print(f'\n  {B}CLEANUP{X}: {n} dokumen uji dihapus · sisa jejak = '
              f'{(G + "0" + X) if sisa == 0 else (R + str(sisa) + X)}')
        print(f'  rahaza_models={db.rahaza_models.count_documents({})} · '
              f'rahaza_model_variants={db.rahaza_model_variants.count_documents({})} · '
              f'FG={db.rahaza_materials.count_documents({"type": "fg"})}')

    print(f'\n{B}{"=" * 92}{X}')
    print(f'  HASIL: {G}{_ok} klaim TERBUKTI{X} / {R}{_fail} tidak terbukti{X}')
    print(f'{B}{"=" * 92}{X}')
    return 0 if _fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
