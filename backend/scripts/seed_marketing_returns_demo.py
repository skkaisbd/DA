#!/usr/bin/env python3
"""seed_marketing_returns_demo.py — buat keadaan **RETUR** yang bisa dilihat di layar.

KENAPA SEEDER INI ADA
---------------------
Keputusan pemilik sesi #9: layar harus menampilkan **omzet bruto DAN omzet setelah
retur**. Masalahnya, seluruh data demo (559 pesanan dari ekspor TikTok) berstatus
`paid` — **nol retur**. Tanpa seeder ini, fitur yang sudah jadi tampak belum jadi:
kartu "Setelah retur" selalu sama dengan bruto, peringatan `returns_high` tidak
pernah bisa dibuktikan menyala, dan cacat sesungguhnya tak akan pernah terlihat
(layar kosong tidak bisa salah).

CARA KERJA — memakai jalur RESMI, bukan menulis status langsung
---------------------------------------------------------------
Status diubah lewat `core.order_status.apply_status`, satu-satunya penulis status
pesanan. Artinya seeder ini juga membuktikan janji produk yang lain:
  · reservasi stok pesanan retur **DILEPAS** (barang tidak dijanjikan dua kali);
  · `returned` itu **TERMINAL** — tidak bisa dihidupkan lagi (termasuk oleh
    "batalkan impor");
  · `status_history[]` mencatat siapa/kapan/dari jalur mana.
Sesudah status berubah, rekap harian hari-hari yang tersentuh **dihitung ulang**
oleh mesin yang sama dengan impor (`marketing_daily_rollup.recompute_pairs`),
sehingga `fulfillment.returned_revenue_product` ikut lahir.

IDEMPOTEN: kalau toko target sudah punya >= target retur, seeder berhenti.
TIDAK ADA `--cleanup`: retur adalah status TERMINAL by design — menyediakan
tombol "batalkan retur" berarti berbohong tentang stok yang sudah dilepas.

Pakai:
    cd /app/backend && python3 scripts/seed_marketing_returns_demo.py
    cd /app/backend && python3 scripts/seed_marketing_returns_demo.py --count 8
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv                                     # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient                 # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from core import marketing_daily_rollup as rollup                  # noqa: E402
from core import order_status as ostat                             # noqa: E402

C = {"g": "\033[92m", "y": "\033[93m", "r": "\033[91m", "b": "\033[1m", "x": "\033[0m"}
ACTOR = {"id": "seed-returns-demo", "email": "seed@dewiaditya.id",
         "full_name": "Seeder Retur Demo", "role": "superadmin"}


def arg(name: str, default):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


async def main() -> int:
    want = int(arg("--count", 6))
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    print(f"{C['b']}seed retur demo — target {want} pesanan retur{C['x']}")

    # 1. toko dengan pesanan TERBANYAK (di situlah layar siklus punya isi)
    agg = await db.marketing_orders.aggregate([
        {"$group": {"_id": "$account_id", "n": {"$sum": 1}}},
        {"$sort": {"n": -1}}, {"$limit": 1}]).to_list(1)
    if not agg:
        print(f"{C['r']}  tidak ada pesanan sama sekali — jalankan "
              f"scripts/seed_marketing_cycle_demo.py dulu{C['x']}")
        return 1
    aid = agg[0]["_id"]
    acc = await db.marketing_platform_accounts.find_one({"id": aid}, {"_id": 0}) or {}
    print(f"  toko: {acc.get('account_name') or aid} ({agg[0]['n']} pesanan)")

    already = await db.marketing_orders.count_documents(
        {"account_id": aid, "status": "returned"})
    if already >= want:
        print(f"{C['y']}  sudah ada {already} pesanan retur — idempoten, tidak "
              f"menambah{C['x']}")
        return 0

    # 2. ambil pesanan yang PALING BESAR nilainya dari beberapa hari berbeda,
    #    supaya persen retur cukup terlihat DAN tersebar di lebih dari satu hari
    #    (kalau menumpuk di satu hari, cakupan retur per hari tak bisa dinilai).
    cands = await db.marketing_orders.find(
        {"account_id": aid, "status": {"$in": ["paid", "delivered", "shipped"]}},
        {"_id": 0, "id": 1, "order_id": 1, "order_date": 1, "revenue_product": 1,
         "status": 1}).sort("revenue_product", -1).to_list(400)
    picked, seen_days = [], {}
    for o in cands:
        day = rollup.order_date_key(o.get("order_date")) or "?"
        if seen_days.get(day, 0) >= 2:      # maksimum 2 retur per hari
            continue
        seen_days[day] = seen_days.get(day, 0) + 1
        picked.append(o)
        if len(picked) >= (want - already):
            break
    if not picked:
        print(f"{C['r']}  tak ada pesanan yang bisa diretur{C['x']}")
        return 1

    # 3. ubah status lewat SSOT (reservasi dilepas + jejak ditulis)
    pairs, ok, fail = set(), 0, 0
    for o in picked:
        try:
            await ostat.apply_status(
                db, o["id"], "returned", user=ACTOR,
                note="[demo-retur] pembeli mengembalikan barang (data contoh sesi #9)",
                source="seed_returns_demo", cancel_evidence=True)
            ok += 1
            d = rollup.order_date_key(o.get("order_date"))
            if d:
                pairs.add((aid, d))
        except Exception as e:                       # noqa: BLE001
            fail += 1
            print(f"{C['y']}  gagal {o.get('order_id')}: {type(e).__name__} {e}{C['x']}")

    # 4. rekap harian dihitung ulang oleh mesin yang sama dengan impor
    res = await rollup.recompute_pairs(db, pairs, actor="seed_returns_demo")
    print(f"  status diubah: {ok} ok · {fail} gagal · rekap dihitung ulang: "
          f"{res.get('dates')} hari")

    tot = await db.marketing_orders.count_documents({"account_id": aid, "status": "returned"})
    val = await db.marketing_orders.aggregate([
        {"$match": {"account_id": aid, "status": "returned"}},
        {"$group": {"_id": None, "v": {"$sum": "$revenue_product"}}}]).to_list(1)
    nilai = (val[0]["v"] if val else 0) or 0
    print(f"{C['g']}{C['b']}SELESAI{C['x']} — {tot} pesanan retur senilai "
          f"Rp {nilai:,.0f}".replace(",", ".") +
          "  · buka: Portal Marketing → Target & Budget → tab \"Siklus Bulan Ini\" "
          "(pilih bulan yang sama dengan pesanannya)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
