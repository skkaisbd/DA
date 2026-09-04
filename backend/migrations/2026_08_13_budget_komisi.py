#!/usr/bin/env python3
"""2026_08_13_budget_komisi.py — F5.2: kategori anggaran **komisi** untuk dokumen lama.

KENAPA MIGRASI INI ADA
----------------------
F5 menambah kategori `komisi` ke rencana anggaran. Dokumen `marketing_budgets` yang
lahir sebelum ini hanya punya 5 kunci (`ads`, `kol`, `livehost`, `sample`, `diskon`).
Pembaca yang menjumlahkan `budget_by_category[c] for c in CATEGORIES` akan aman
karena defaultnya 0, TETAPI layar yang menampilkan tabel kategori akan menunjukkan
baris `komisi` "hilang" pada bulan lama dan "ada" pada bulan baru — dua bentuk
dokumen untuk satu arti, yang persis kelas masalah yang F0 tutup.

Migrasi ini **idempoten**: hanya menambah kunci yang belum ada, tidak menyentuh
angka yang sudah tersimpan.

Pakai:
    cd /app/backend && python3 migrations/2026_08_13_budget_komisi.py            # dry-run
    cd /app/backend && python3 migrations/2026_08_13_budget_komisi.py --apply
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, "/app/backend")

from dotenv import load_dotenv  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

load_dotenv("/app/backend/.env")

NEW_KEYS = ("komisi",)


async def main(apply: bool) -> int:
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    docs = await db.marketing_budgets.find({}, {"_id": 0}).to_list(10000)
    need = [d for d in docs
            if any(k not in (d.get("budget_by_category") or {}) for k in NEW_KEYS)]
    print(f"marketing_budgets   : {len(docs)} dokumen")
    print(f"perlu ditambah kunci: {len(need)} dokumen  (kunci: {', '.join(NEW_KEYS)})")
    if not need:
        print("tidak ada yang perlu diubah — idempoten OK")
        return 0
    if not apply:
        for d in need[:10]:
            print(f"  · {d.get('account_name', d.get('account_id'))} {d.get('period')}")
        print("\n(dry-run) jalankan ulang dengan --apply untuk menerapkan")
        return 0
    n = 0
    for d in need:
        sets = {f"budget_by_category.{k}": 0.0 for k in NEW_KEYS
                if k not in (d.get("budget_by_category") or {})}
        if not sets:
            continue
        await db.marketing_budgets.update_one({"id": d["id"]}, {"$set": sets})
        n += 1
    print(f"selesai — {n} dokumen diperbarui")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main("--apply" in sys.argv)))
