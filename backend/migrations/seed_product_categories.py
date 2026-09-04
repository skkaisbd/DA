#!/usr/bin/env python3
"""seed_product_categories.py — F2 · isi master kategori produk (keputusan K-2).

14 kategori yang disetujui owner 2026-08-10, masing-masing dengan **prefix SKU**
(dipakai membuat kode produk otomatis `VST-0001` — keputusan K-1A).

Idempoten: kategori yang sudah ada (by `code`) dilewati, tidak ditimpa.

Pakai::
    python3 backend/migrations/seed_product_categories.py --dry-run
    python3 backend/migrations/seed_product_categories.py --apply
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.product_master import DEFAULT_CATEGORIES  # noqa: E402
from pymongo import MongoClient  # noqa: E402

G, Y, X, BOLD = '\033[92m', '\033[93m', '\033[0m', '\033[1m'


def main() -> int:
    apply = '--apply' in sys.argv
    db = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
                     )[os.environ.get('DB_NAME', 'test_database')]
    coll = db.rahaza_product_categories
    now = datetime.now(timezone.utc)

    print(f'{BOLD}seed_product_categories — {"APPLY" if apply else "DRY-RUN"}{X}')
    print(f'  kategori di DB sekarang: {coll.count_documents({})}')

    new, skip = [], []
    for c in DEFAULT_CATEGORIES:
        (skip if coll.find_one({'code': c['code']}) else new).append(c)

    print(f'\n  akan DIBUAT ({len(new)}):')
    for c in new:
        print(f"    · {c['sku_prefix']:4s} {c['code']:10s} {c['name']}")
    if skip:
        print(f'\n  sudah ada, dilewati ({len(skip)}): '
              f"{', '.join(c['code'] for c in skip)}")

    if apply and new:
        coll.insert_many([{
            'id': str(uuid.uuid4()), **c, 'description': '', 'active': True,
            'created_from': 'seed', 'created_at': now, 'updated_at': now,
        } for c in new])
        print(f'\n  {G}DITERAPKAN: {len(new)} kategori dibuat. '
              f'Total sekarang: {coll.count_documents({})}{X}')
    elif not apply:
        print(f'\n  {Y}DRY-RUN — tidak ada dokumen yang diubah.{X}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
