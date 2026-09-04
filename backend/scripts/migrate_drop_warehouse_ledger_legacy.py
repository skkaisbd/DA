"""FASE F — Archive & DROP koleksi ledger gudang LEGACY (GEN-1).

Koleksi target (sudah TANPA writer & reader sejak Fase E2 + Fase F/F+):
  - warehouse_stock       (superseded by rahaza_material_stock)
  - warehouse_movements   (superseded by rahaza_stock_ledger + rahaza_material_movements)
  - warehouse_putaway     (superseded by wms_putaway.py / wh_placement_movements)
  - warehouse_opname      (superseded by wms_opname3.py / wh_opname_sessions*)
  - warehouse_locations   (FASE F+: SSOT lokasi = wh_zones + rahaza_locations; get_locations kanonik,
                           create/update/delete_location → 410, dropdown ReceivingModule pakai
                           /api/rahaza/storage-locations)

DIPERTAHANKAN (JANGAN di-drop, masih LIVE via bridge /api/wms/legacy/*):
  - warehouse_receiving   (Goods Receipt / GR, 3-way match)

Sifat:
  * IDEMPOTENT — koleksi yang sudah tidak ada dilewati; rerun = no-op.
  * ARSIP DULU — isi tiap koleksi di-copy ke `wh_legacy_archive_<coll>` SEBELUM drop
    (tidak menghilangkan histori; bisa di-rollback).
  * JURNAL — tiap aksi dicatat ke `wh_legacy_drop_log`.

Pakai:
  python -m scripts.migrate_drop_warehouse_ledger_legacy --dry-run   # simulasi (hitung saja)
  python -m scripts.migrate_drop_warehouse_ledger_legacy             # arsip + drop
  python -m scripts.migrate_drop_warehouse_ledger_legacy --rollback  # restore dari arsip

Catatan: di preview DB (fresh) koleksi ini kosong/absen → no-op aman. Untuk DB
produksi user, arsip menjaga histori legacy sebelum di-drop.
"""
import argparse
import asyncio
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

LEGACY_COLLECTIONS = [
    "warehouse_stock",
    "warehouse_movements",
    "warehouse_putaway",
    "warehouse_opname",
    "warehouse_locations",  # FASE F+ : dropdown ReceivingModule sudah pindah ke SSOT storage-locations
]
ARCHIVE_PREFIX = "wh_legacy_archive_"
LOG = "wh_legacy_drop_log"


def _now():
    return datetime.now(timezone.utc)


def _get_db():
    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ.get("DB_NAME", "garment_erp")
    client = AsyncIOMotorClient(mongo_url)
    return client, client[db_name]


async def run(dry_run: bool, rollback: bool):
    client, db = _get_db()
    try:
        existing = set(await db.list_collection_names())

        if rollback:
            print("=== ROLLBACK: restore koleksi legacy dari arsip ===")
            for coll in LEGACY_COLLECTIONS:
                arch = ARCHIVE_PREFIX + coll
                if arch not in existing:
                    print(f"[skip] arsip {arch} tidak ada")
                    continue
                n = await db[arch].count_documents({})
                if dry_run:
                    print(f"[dry-run] {arch}: {n} docs → akan di-restore ke {coll}")
                    continue
                if n > 0:
                    docs = await db[arch].find({}).to_list(length=None)
                    # bersihkan target dulu agar idempotent, lalu insert balik (preserve _id)
                    if coll in await db.list_collection_names():
                        await db[coll].drop()
                    await db[coll].insert_many(docs)
                await db[arch].drop()
                await db[LOG].insert_one({
                    "action": "rollback", "collection": coll, "archive": arch,
                    "restored": n, "at": _now(),
                })
                print(f"[rollback] {coll} <- {arch}: {n} docs")
            return

        print("=== FORWARD: arsip + drop koleksi ledger legacy ===")
        for coll in LEGACY_COLLECTIONS:
            if coll not in existing:
                print(f"[skip] {coll} tidak ada (sudah drop / belum pernah dibuat)")
                continue
            n = await db[coll].count_documents({})
            arch = ARCHIVE_PREFIX + coll
            if dry_run:
                print(f"[dry-run] {coll}: {n} docs → arsip ke {arch} lalu DROP")
                continue
            if n > 0:
                docs = await db[coll].find({}).to_list(length=None)
                # arsip idempotent: ganti isi arsip dgn snapshot terbaru
                if arch in await db.list_collection_names():
                    await db[arch].drop()
                await db[arch].insert_many(docs)
            await db[coll].drop()
            await db[LOG].insert_one({
                "action": "archive_and_drop", "collection": coll, "archive": arch,
                "archived": n, "at": _now(),
            })
            print(f"[drop] {coll}: {n} docs diarsip ke {arch}, koleksi di-DROP")

        # ringkasan
        after = set(await db.list_collection_names())
        still = [c for c in LEGACY_COLLECTIONS if c in after]
        print("\n=== RINGKASAN ===")
        print(f"Koleksi legacy tersisa (harus kosong): {still}")
        print("Koleksi DIPERTAHANKAN (live): warehouse_receiving")
    finally:
        client.close()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Archive & drop legacy warehouse ledger collections (FASE F).")
    ap.add_argument("--dry-run", action="store_true", help="Hitung saja, tidak mengubah DB.")
    ap.add_argument("--rollback", action="store_true", help="Restore koleksi dari arsip wh_legacy_archive_*.")
    args = ap.parse_args()
    asyncio.run(run(dry_run=args.dry_run, rollback=args.rollback))
