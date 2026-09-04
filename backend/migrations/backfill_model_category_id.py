#!/usr/bin/env python3
"""backfill_model_category_id.py — F3 · kategori TEKS lama → `category_id` (K-5a).

Masalah yang ditutup:
  * **P3** `category` teks bebas — nilai di luar dropdown diterima server
    (terbukti tersimpan `'Rok Lipit Sekolah'`).
  * **T2** ada **4 kosakata kategori** yang tidak pernah bertemu antar-modul.

Keputusan owner **K-5a**: yang cocok dipetakan; yang **tidak dikenal DIBUATKAN
entri master otomatis** (`created_from='migrasi'`) — **nol data hilang**.
Yang kosong dilaporkan apa adanya, **tidak ditebak**.

Pakai::
    python3 backend/migrations/backfill_model_category_id.py --dry-run
    python3 backend/migrations/backfill_model_category_id.py --apply
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import product_master as pm  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

G, R, Y, X, BOLD = '\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m'


async def run(apply: bool) -> int:
    client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
    db = client[os.environ.get('DB_NAME', 'test_database')]

    print(f'{BOLD}backfill_model_category_id — {"APPLY" if apply else "DRY-RUN"}{X}')
    await pm.seed_default_categories(db)

    models = await db.rahaza_models.find(
        {'$or': [{'category_id': {'$exists': False}}, {'category_id': None}]},
        {'_id': 0}).to_list(5000)
    print(f'  model tanpa `category_id`: {len(models)}')

    plan, empty, created_cats = [], [], []
    for m in models:
        text = (m.get('category') or '').strip()
        if not text:
            empty.append(m)
            continue
        cat = await pm.resolve_category_by_text(db, text, allow_create=False)
        if not cat:
            if apply:
                cat = await pm.resolve_category_by_text(db, text, allow_create=True)
                created_cats.append(cat.get('code'))
            else:
                created_cats.append(f'(baru) {text}')
                cat = {'id': None, 'code': '?', 'name': text}
        plan.append((m, cat))

    print(f'\n  akan dipetakan ({len(plan)}):')
    for m, c in plan[:40]:
        print(f"    · {m.get('code'):22s} '{m.get('category')}' → {c.get('code')} / {c.get('name')}")
    if len(plan) > 40:
        print(f'    … dan {len(plan) - 40} lagi')
    if created_cats:
        print(f'\n  {Y}kategori master BARU dibuat dari nilai tak dikenal (K-5a): '
              f'{sorted(set(created_cats))}{X}')
    if empty:
        print(f'\n  {Y}model dengan kategori KOSONG ({len(empty)}) — TIDAK ditebak, '
              f'harus dipilih manusia di layar Master Produk:{X}')
        for m in empty[:20]:
            print(f"    · {m.get('code')} — {m.get('name')}")

    if apply:
        n = 0
        for m, c in plan:
            if not c.get('id'):
                continue
            patch = pm.category_patch(c)
            patch['updated_at'] = pm._now()
            await db.rahaza_models.update_one({'id': m['id']}, {'$set': patch})
            n += 1
        print(f'\n  {G}DITERAPKAN: {n} model dapat `category_id`.{X}')
        left = await db.rahaza_models.count_documents(
            {'category_id': {'$in': [None]}, 'category': {'$nin': ['', None]}})
        print(f'  sisa model berkategori teks tanpa `category_id`: {left}')
    else:
        print(f'\n  {Y}DRY-RUN — tidak ada dokumen yang diubah.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(run('--apply' in sys.argv)))
