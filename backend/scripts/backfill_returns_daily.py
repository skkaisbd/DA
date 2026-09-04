#!/usr/bin/env python3
"""backfill_returns_daily.py — isi `fulfillment.returned_revenue_product` &
`returned_units` pada rekap harian TURUNAN yang lahir sebelum sesi #9.

KENAPA SKRIP INI ADA
--------------------
Sesi #9 menambah dua field turunan supaya "omzet setelah retur" bisa dihitung
pada basis omzet PRODUK (bukan cuma order amount). Dokumen rekap harian yang
sudah ada di DB tidak punya field itu. `core.marketing_returns.from_daily_rows`
sengaja menyatakan hari seperti itu **BELUM DIKETAHUI** (bukan nol) supaya tidak
ada net yang salah tampil — dan skrip ini yang menutup keadaan transisi itu.

Cara kerjanya: kumpulkan pasangan (toko, tanggal) dari `marketing_orders`, lalu
panggil `core.marketing_daily_rollup.recompute_pairs` — mesin rekap harian yang
SAMA yang dipakai impor & layar. Jadi tidak ada rumus kedua di sini.

Aman & idempoten:
  · hanya dokumen **turunan** yang disentuh (override SPV & entri manual dilewati,
    kecuali `--force`);
  · tidak membuat/menghapus pesanan;
  · dijalankan ulang tidak mengubah hasil.

Pakai:
    cd /app/backend && python3 scripts/backfill_returns_daily.py            # jalan
    cd /app/backend && python3 scripts/backfill_returns_daily.py --dry-run  # lihat saja
    cd /app/backend && python3 scripts/backfill_returns_daily.py --force    # timpa override
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv                                    # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from core import marketing_daily_rollup as rollup                 # noqa: E402

C = {"g": "\033[92m", "y": "\033[93m", "r": "\033[91m", "b": "\033[1m", "x": "\033[0m"}


async def main() -> int:
    dry = "--dry-run" in sys.argv
    force = "--force" in sys.argv
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    print(f"{C['b']}backfill retur rekap harian — dry_run={dry} force={force}{C['x']}")

    # 1. hari mana saja yang punya pesanan
    pairs = await rollup.pairs_from_orders(db, {})
    print(f"  pasangan (toko, tanggal) dari pesanan: {len(pairs)}")

    # 2. berapa yang memang masih basi (retur ada tapi nilai produknya belum)
    stale = await db[rollup.DAILY].count_documents({
        "fulfillment.returned_orders": {"$gt": 0},
        "fulfillment.returned_value": {"$gt": 0},
        "$or": [{"fulfillment.returned_revenue_product": {"$exists": False}},
                {"fulfillment.returned_revenue_product": 0}],
    })
    print(f"  rekap harian dengan retur TANPA nilai produk: {stale}")

    if dry:
        print(f"{C['y']}  (dry-run) tidak ada yang diubah{C['x']}")
        return 0

    res = await rollup.recompute_pairs(db, pairs, force=force, actor="backfill_returns")
    print(f"  hasil: {res}")

    left = await db[rollup.DAILY].count_documents({
        "fulfillment.returned_orders": {"$gt": 0},
        "fulfillment.returned_value": {"$gt": 0},
        "$or": [{"fulfillment.returned_revenue_product": {"$exists": False}},
                {"fulfillment.returned_revenue_product": 0}],
    })
    filled = await db[rollup.DAILY].count_documents(
        {"fulfillment.returned_revenue_product": {"$gt": 0}})
    print(f"  sesudah: {filled} rekap membawa nilai retur produk · sisa basi {left}")
    if left and not force:
        print(f"{C['y']}  sisa {left} dokumen tidak turunan (override/manual) — "
              f"pakai --force bila memang ingin ditimpa{C['x']}")
    print(f"{C['g']}{C['b']}SELESAI{C['x']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
