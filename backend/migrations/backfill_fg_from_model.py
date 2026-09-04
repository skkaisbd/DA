#!/usr/bin/env python3
"""backfill_fg_from_model.py — F3/F8 · segarkan FG & item katalog dari master.

Menyembuhkan data BASI yang sudah TERBUKTI:
  * **P2b** `category` disalin ke FG saat FG dibuat dan **tidak pernah** diperbarui
    ⇒ ubah kategori di master, FG & katalog tetap kategori LAMA selamanya.
  * **P4b** `weight_gram` dibaca `ensure_fg_material()` tetapi tidak pernah ditulis
    ⇒ berat FG selalu 0.
  * **P1b** produk manual ⇒ `FG.hpp = 0` ⇒ margin katalog mustahil dihitung
    (sekarang `base_hpp` manual ikut dipakai lewat `resolve_hpp`).

⚠️  RISIKO YANG DIAKUI: propagasi ini akan MENGUBAH kategori FG yang selama ini
    basi. Itu memang tujuannya, tetapi **laporan lama yang di-grup per kategori
    bisa bergeser**. Karena itu WAJIB `--dry-run` dulu dan hasilnya ditunjukkan
    ke owner sebelum `--apply`.

UANG tidak digeser: HPP R&D yang sudah ada tidak pernah ditimpa — `resolve_hpp()`
mendahulukan `model.hpp` (R&D) dan hanya memakai `base_hpp` bila R&D kosong.

Pakai::
    python3 backend/migrations/backfill_fg_from_model.py --dry-run
    python3 backend/migrations/backfill_fg_from_model.py --apply
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import product_master as pm  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

G, R, Y, X, BOLD, DIM = '\033[92m', '\033[91m', '\033[93m', '\033[0m', '\033[1m', '\033[2m'


async def run(apply: bool) -> int:
    client = AsyncIOMotorClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
    db = client[os.environ.get('DB_NAME', 'test_database')]

    print(f'{BOLD}backfill_fg_from_model — {"APPLY" if apply else "DRY-RUN"}{X}')
    models = await db.rahaza_models.find({}, {'_id': 0}).to_list(5000)
    print(f'  master produk: {len(models)}')

    changes = []
    for m in models:
        want = pm.master_display_fields(m)
        fgs = await db.rahaza_materials.find(
            {'type': 'fg', 'model_id': m['id']}, {'_id': 0}).to_list(2000)
        for fg in fgs:
            diff = {k: (fg.get(k), v) for k, v in want.items()
                    if k != 'retail_price_master' and fg.get(k) != v}
            if diff:
                changes.append(('FG', m.get('code'), fg.get('code'), diff))
        fg_ids = [f['id'] for f in fgs]
        q = {'$or': [{'model_id': m['id']}]}
        if fg_ids:
            q['$or'].extend([{'fg_material_id': {'$in': fg_ids}},
                             {'material_id': {'$in': fg_ids}}])
        items = await db.marketing_catalog_items.find(q, {'_id': 0}).to_list(2000)
        for it in items:
            diff = {k: (it.get(k), v) for k, v in want.items() if it.get(k) != v}
            if diff:
                changes.append(('ITEM', m.get('code'), it.get('sku'), diff))

    print(f'\n  dokumen yang akan berubah: {len(changes)}')
    for kind, mcode, code, diff in changes[:40]:
        bits = ', '.join(f'{k}: {a!r} → {b!r}' for k, (a, b) in diff.items())
        print(f'    · [{kind}] {mcode} / {code}: {bits}')
    if len(changes) > 40:
        print(f'    … dan {len(changes) - 40} lagi')

    cat_shift = [c for c in changes if 'category' in c[3] or 'category_name' in c[3]]
    if cat_shift:
        print(f'\n  {Y}⚠ {len(cat_shift)} dokumen akan BERGANTI KATEGORI — laporan lama '
              f'yang di-grup per kategori bisa bergeser. Tunjukkan ini ke owner.{X}')

    if apply:
        total = {'fg': 0, 'items': 0}
        for m in models:
            res = await pm.propagate_master_changes(db, m)
            total['fg'] += res['fg']
            total['items'] += res['items']
        print(f"\n  {G}DITERAPKAN: FG {total['fg']} · item katalog {total['items']}{X}")
    else:
        print(f'\n  {Y}DRY-RUN — tidak ada dokumen yang diubah.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(asyncio.run(run('--apply' in sys.argv)))
