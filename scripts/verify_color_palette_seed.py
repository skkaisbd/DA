#!/usr/bin/env python3
"""INV-COLOR — palet warna master TIDAK BOLEH tercemar warna sampah.

Kenapa pemeriksaan ini ada (bug nyata, ditemukan 2026-08-08):
`rahaza_colors` di-seed **lazy** dan HANYA bila koleksinya kosong, tetapi
penyemaian itu dulu hanya dipasang di endpoint DAFTAR
(`GET /api/rahaza/colors`, `GET /api/dewi/rnd/color-options`).
Pintu lain — `utils.variant_ssot.ensure_color()` yang dipakai importir Excel,
promosi varian R&D → master, dan skrip gate — TIDAK menyemai.

Akibatnya, di database hasil bootstrap BERSIH, siapa pun yang memanggil
`ensure_color(code='NVY')` lebih dulu akan membuat
`{code:'NVY', name:'NVY', hex:'#CCCCCC'}` — warna SAMPAH — dan karena koleksi
jadi tidak-kosong, **palet 15 warna asli tidak pernah ter-seed lagi**.
Dua kerusakan yang mahal:
  1. Dropdown warna R&D hanya berisi warna abu-abu tak bernama.
  2. Warna yang sama pecah dua (`NVY`/'NVY' sampah + `NAV`/'Navy') ⇒ deteksi
     varian kembar lolos dan SKU tidak pernah cocok dengan SKU FG di gudang.

Pemeriksaan ini dijalankan di DATABASE SEMENTARA (bukan DB aplikasi) supaya
tidak pernah mengubah data sungguhan.

Jalankan: python scripts/verify_color_palette_seed.py
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'backend'))

G, R, Y, B, X = '\033[92m', '\033[91m', '\033[93m', '\033[1m', '\033[0m'
FINDINGS = []


def inv(code, ok, msg):
    print(f'    {G}✓{X} {code} — {msg}' if ok else f'    {R}✗ {code} — {msg}{X}')
    if not ok:
        FINDINGS.append(f'{code}: {msg}')
    return ok


def _env(key, default=''):
    val = os.environ.get(key)
    if val:
        return val
    env_file = Path(__file__).resolve().parent.parent / 'backend' / '.env'
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            if line.startswith(f'{key}='):
                return line.split('=', 1)[1].strip().strip('"').strip("'")
    return default


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    from utils.variant_ssot import ensure_color
    from routes.rahaza_variants import DEFAULT_COLORS

    mongo_url = _env('MONGO_URL', 'mongodb://localhost:27017')
    scratch = f"{_env('DB_NAME', 'test_database')}__inv_color_scratch"
    client = AsyncIOMotorClient(mongo_url)

    print(f'\n{B}=================================================================={X}')
    print(f'  {Y}INV-COLOR{X} — palet warna master bebas warna sampah (SSOT warna/SKU)')
    print(f'{B}=================================================================={X}')
    print(f'    DB sementara: {scratch} (dibuang setelah selesai)')

    try:
        await client.drop_database(scratch)
        db = client[scratch]

        # ── INV-COLOR-1: pintu terbawah `ensure_color` ikut menyemai palet ──
        # Ini SKENARIO BUG-nya: DB kosong, pemanggil pertama pakai KODE palet.
        got = await ensure_color(db, code='NVY', name='NVY')
        total = await db.rahaza_colors.count_documents({})
        inv('INV-COLOR-1',
            total == len(DEFAULT_COLORS) and got and got.get('name') == 'Navy'
            and got.get('hex') == '#1E3A5F',
            f"ensure_color(code='NVY') di DB kosong → palet ter-seed {total}/"
            f"{len(DEFAULT_COLORS)} & mengembalikan warna ASLI "
            f"({got.get('code')}/{got.get('name')}/{got.get('hex')}), bukan sampah")

        # ── INV-COLOR-2: tidak ada warna sampah (#CCCCCC dengan nama = kode) ──
        junk = [c for c in await db.rahaza_colors.find({}, {'_id': 0}).to_list(500)
                if c.get('hex') == '#CCCCCC' and c.get('name') == c.get('code')]
        inv('INV-COLOR-2', not junk,
            f'tidak ada warna sampah (hex #CCCCCC & nama=kode) — ditemukan {len(junk)}'
            + (f' {[c["code"] for c in junk[:3]]}' if junk else ''))

        # ── INV-COLOR-3: NAMA palet tidak boleh pecah jadi dua kode ──
        # Dulu: 'NVY'/'NVY' (sampah) + 'NAV'/'Navy' (dibuat lewat nama) hidup bersama.
        by_name = await ensure_color(db, name='Navy')
        codes = await db.rahaza_colors.find({'name': 'Navy'}, {'_id': 0}).to_list(50)
        inv('INV-COLOR-3',
            by_name and by_name.get('code') == 'NVY' and len(codes) == 1,
            f"ensure_color(name='Navy') menunjuk warna yang SAMA (kode "
            f"{(by_name or {}).get('code')}) — 'Navy' hanya punya {len(codes)} kode")

        # ── INV-COLOR-4: warna yang MEMANG baru tetap boleh dibuat ──
        novel = await ensure_color(db, name='Lavender Uji', hex_val='#B57EDC')
        after = await db.rahaza_colors.count_documents({})
        inv('INV-COLOR-4',
            novel and novel.get('name') == 'Lavender Uji'
            and after == len(DEFAULT_COLORS) + 1,
            f'warna benar-benar baru tetap dibuat (kode {(novel or {}).get("code")}), '
            f'total {after} = palet + 1')

        # ── INV-COLOR-5: idempoten — panggilan kedua tidak menambah dokumen ──
        again = await ensure_color(db, code='NVY')
        final = await db.rahaza_colors.count_documents({})
        inv('INV-COLOR-5',
            again and again.get('id') == got.get('id') and final == after,
            f'panggilan ulang idempoten — id sama & total tetap {final}')

        # ── INV-COLOR-6: palet yang SENGAJA dihapus tidak dihidupkan kembali ──
        # Penyemaian hanya saat KOSONG, jadi menghapus 1 warna harus tetap terhapus.
        await db.rahaza_colors.delete_one({'code': 'KRM'})
        await ensure_color(db, code='NVY')
        krm = await db.rahaza_colors.count_documents({'code': 'KRM'})
        inv('INV-COLOR-6', krm == 0,
            'warna palet yang sengaja dihapus TIDAK dihidupkan kembali '
            f'(KRM masih {krm} dokumen)')
    finally:
        await client.drop_database(scratch)

    print(f'\n{B}------------------------------------------------------------------{X}')
    print(f'  INV-COLOR: 6 invarian diperiksa — {len(FINDINGS)} temuan')
    for f in FINDINGS:
        print(f'  {R}· {f}{X}')
    if FINDINGS:
        print(f'  {R}{B}✗ INV-COLOR MERAH{X}')
        return 1
    print(f'  {G}{B}✓ INV-COLOR HIJAU — palet warna master bersih & SKU tidak pecah.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
