#!/usr/bin/env python3
"""normalize_model_active.py — F1 · tutup **T1 (kode produk kembar)**.

Akar masalah (TERBUKTI lewat HTTP):
  * form manual menulis `active: True`
  * promosi R&D menulis `status: 'active'` **tanpa** `active`
  * index unik `rahaza_models.code` memakai `partialFilterExpression {active: true}`
⇒ dokumen hasil promosi berada **di luar** index, dan pengecekan duplikat API
  memakai filter yang sama ⇒ `POST /api/rahaza/models` dengan kode yang sudah ada
  membalas **HTTP 200** (seharusnya 409) ⇒ dua master berkode sama.

Yang dikerjakan (idempoten):
  1. Isi `active` untuk dokumen yang belum punya — dari `status`
     (`inactive`/`archived`/`deleted` → False, selain itu → True).
  2. **LAPORKAN** kode kembar yang sudah ada — **TIDAK** digabung otomatis.
     Penggabungan master produk menyentuh varian/FG/stok/BOM: itu keputusan
     manusia, bukan tebakan skrip.

Pakai::
    python3 backend/migrations/normalize_model_active.py --dry-run
    python3 backend/migrations/normalize_model_active.py --apply
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pymongo import MongoClient  # noqa: E402

G, R, Y, X, BOLD = '\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m'
DEAD_STATUS = {'inactive', 'archived', 'deleted', 'nonaktif'}


def main() -> int:
    apply = '--apply' in sys.argv
    dry = not apply
    db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                     )[os.environ.get('DB_NAME', 'test_database')]

    print(f'{BOLD}normalize_model_active — {"DRY-RUN" if dry else "APPLY"}{X}')

    missing = list(db.rahaza_models.find({'active': {'$exists': False}}, {'_id': 0}))
    to_true = [m for m in missing if (m.get('status') or 'active').lower() not in DEAD_STATUS]
    to_false = [m for m in missing if (m.get('status') or 'active').lower() in DEAD_STATUS]

    print(f'\n  dokumen tanpa field `active` : {len(missing)}')
    print(f'    → akan di-set active=True   : {len(to_true)}')
    for m in to_true[:20]:
        print(f'        · {m.get("code")} — {m.get("name")} (status={m.get("status")})')
    if len(to_true) > 20:
        print(f'        … dan {len(to_true) - 20} lagi')
    print(f'    → akan di-set active=False  : {len(to_false)}')
    for m in to_false[:20]:
        print(f'        · {m.get("code")} — status={m.get("status")}')

    if apply:
        n1 = n2 = 0
        if to_true:
            n1 = db.rahaza_models.update_many(
                {'id': {'$in': [m['id'] for m in to_true]}},
                {'$set': {'active': True}}).modified_count
        if to_false:
            n2 = db.rahaza_models.update_many(
                {'id': {'$in': [m['id'] for m in to_false]}},
                {'$set': {'active': False}}).modified_count
        print(f'\n  {G}DITERAPKAN: active=True → {n1} · active=False → {n2}{X}')

    # ── kode kembar: LAPORKAN saja ──────────────────────────────────────
    dups = list(db.rahaza_models.aggregate([
        {'$group': {'_id': {'$toUpper': '$code'},
                    'n': {'$sum': 1},
                    'ids': {'$push': '$id'},
                    'names': {'$push': '$name'}}},
        {'$match': {'n': {'$gt': 1}}},
        {'$sort': {'n': -1}},
    ]))
    print(f'\n  kode produk KEMBAR: {len(dups)}')
    for d in dups:
        print(f'    {R}✗ {d["_id"]} ×{d["n"]}{X} — {d["names"]}')
        for i in d['ids']:
            v = db.rahaza_model_variants.count_documents({'model_id': i})
            fg = db.rahaza_materials.count_documents({'type': 'fg', 'model_id': i})
            print(f'        id={i}  varian={v}  FG={fg}')
    if dups:
        print(f'\n  {Y}Kode kembar TIDAK digabung otomatis — penggabungan menyentuh '
              f'varian/FG/stok/BOM.{X}')
        print(f'  {Y}Pilih master yang dipertahankan, lalu ubah kode yang lain lewat '
              f'layar Master Produk.{X}')

    left = db.rahaza_models.count_documents({'active': {'$exists': False}})
    print(f'\n  sisa dokumen tanpa `active`: {left}')
    if dry:
        print(f'  {Y}DRY-RUN — tidak ada dokumen yang diubah. '
              f'Jalankan dengan --apply untuk menerapkan.{X}')
    return 0 if (apply and left == 0) or dry else 1


if __name__ == '__main__':
    sys.exit(main())
