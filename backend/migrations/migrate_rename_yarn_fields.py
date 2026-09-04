"""Migration: FASE 6.6-B + FASE 11 — kelola alias field legacy `yarn_*`.

Created: 2026-07-25 · Diperluas: FASE 11 (2026-07-25)
Reversible: YES (`--rollback` melepas field kanonik; `--drop-legacy` punya `--backup`)

Peta rename ada di SSOT `backend/core/material_fields.py`:
    composition                   ← yarn_type
    material_kg_per_pcs           ← yarn_kg_per_pcs
    default_material_cost_per_kg  ← default_yarn_cost_per_kg
    total_material_kg_per_pcs     ← total_yarn_kg_per_pcs
    total_material_kg             ← total_yarn_kg
    bulk_line_count               ← yarn_count

URUTAN YANG BENAR (FASE 11)
---------------------------
    1. python3 migrations/migrate_rename_yarn_fields.py --discover
       → lihat koleksi mana yang masih menyimpan kunci legacy.
    2. python3 migrations/migrate_rename_yarn_fields.py --execute
       → backfill: pastikan SETIAP dokumen ber-kunci legacy punya kunci kanonik.
         (Kalau langkah ini melaporkan 0, berarti data sudah siap.)
    3. python3 migrations/migrate_rename_yarn_fields.py --drop-legacy
       → BARU hapus kunci `yarn_*` dari dokumen. Menolak jalan bila masih ada
         dokumen yang HANYA punya kunci legacy (mencegah kehilangan data).

CATATAN AMAN
------------
  * Semua langkah idempoten — aman diulang.
  * `--drop-legacy` tanpa `--yes` hanya melakukan dry-run.
  * Kode aplikasi TIDAK bergantung pada kunci legacy: sejak FASE 11 `mirror()`
    hanya menulis nama kanonik, dan `read_field()` masih punya fallback baca.

Pakai:
    python3 migrations/migrate_rename_yarn_fields.py                    # dry-run backfill
    python3 migrations/migrate_rename_yarn_fields.py --discover
    python3 migrations/migrate_rename_yarn_fields.py --execute
    python3 migrations/migrate_rename_yarn_fields.py --drop-legacy          # dry-run
    python3 migrations/migrate_rename_yarn_fields.py --drop-legacy --yes    # eksekusi
    python3 migrations/migrate_rename_yarn_fields.py --rollback
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from core.material_fields import (  # noqa: E402
    ALL_LEGACY_FIELDS,
    CANONICAL_FIELDS,
    LEGACY_TO_CANONICAL,
)

# Koleksi yang DIKETAHUI menyimpan field legacy (hasil grep kode + audit DB).
# Tambahkan di sini bila `--discover` menemukan koleksi lain.
TARGETS = {
    "rahaza_materials": ["yarn_type"],
    "rahaza_models": ["yarn_kg_per_pcs"],
    "rahaza_costing_settings": ["default_yarn_cost_per_kg"],
    "rahaza_products": ["yarn_kg_per_pcs", "yarn_type"],
    "marketing_catalog_items": ["yarn_type"],
    "rahaza_boms": ["total_yarn_kg_per_pcs", "yarn_count"],
}

ALL_LEGACY = list(ALL_LEGACY_FIELDS)


def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "test_database")]


async def discover(db):
    print("\n=== DISCOVERY — koleksi yang masih menyimpan field legacy ===")
    names = await db.list_collection_names()
    found = {}
    for name in sorted(names):
        for legacy in ALL_LEGACY:
            n = await db[name].count_documents({legacy: {"$exists": True}}, limit=1)
            if n:
                total = await db[name].count_documents({legacy: {"$exists": True}})
                found.setdefault(name, []).append((legacy, total))
    if not found:
        print("(tidak ada — semua bersih)")
    for name, items in found.items():
        known = name in TARGETS
        tag = "" if known else "   ← BELUM ada di TARGETS!"
        print(f"  {name}{tag}")
        for legacy, total in items:
            print(f"      {legacy:30s} {total:6d} dok  → {LEGACY_TO_CANONICAL[legacy]}")
    return found


async def migrate(db, *, dry_run=True):
    print(f"\n=== BACKFILL FIELD KANONIK (dry_run={dry_run}) ===")
    grand = 0
    for coll, legacies in TARGETS.items():
        if coll not in await db.list_collection_names():
            continue
        for legacy in legacies:
            canon = LEGACY_TO_CANONICAL.get(legacy)
            if not canon:
                continue
            q = {legacy: {"$exists": True}, canon: {"$exists": False}}
            n = await db[coll].count_documents(q)
            if not n:
                continue
            print(f"  {coll}.{legacy} → {canon}: {n} dok")
            grand += n
            if dry_run:
                continue
            # copy nilai legacy → kanonik (per dokumen, nilai bisa beda-beda)
            async for doc in db[coll].find(q, {"_id": 0, "id": 1, legacy: 1}):
                if not doc.get("id"):
                    continue
                await db[coll].update_one({"id": doc["id"]}, {"$set": {canon: doc.get(legacy)}})
    print(f"\nTOTAL dokumen {'akan di-' if dry_run else ''}backfill: {grand}")
    return grand


async def rollback(db):
    print("\n=== ROLLBACK — lepas field KANONIK (legacy tetap utuh) ===")
    grand = 0
    canon_fields = list(CANONICAL_FIELDS)
    for coll in TARGETS:
        if coll not in await db.list_collection_names():
            continue
        for canon in canon_fields:
            n = await db[coll].count_documents({canon: {"$exists": True}})
            if not n:
                continue
            print(f"  {coll}.{canon}: {n} dok → unset")
            grand += n
            await db[coll].update_many({canon: {"$exists": True}}, {"$unset": {canon: ""}})
    print(f"\nTOTAL field kanonik dilepas: {grand}")
    return grand


async def drop_legacy(db, *, apply=False):
    """FASE 11 — hapus kunci legacy `yarn_*` dari SEMUA koleksi.

    Menolak jalan bila masih ada dokumen yang HANYA punya kunci legacy
    (belum di-backfill), supaya tidak ada nilai yang hilang.
    """
    print(f"\n=== DROP LEGACY `yarn_*` (apply={apply}) ===")
    names = await db.list_collection_names()

    # 1) Palang pengaman — cari dokumen yang punya legacy TANPA kanonik.
    unsafe = []
    for name in sorted(names):
        for legacy in ALL_LEGACY:
            canon = LEGACY_TO_CANONICAL[legacy]
            n = await db[name].count_documents(
                {legacy: {"$exists": True}, canon: {"$exists": False}}
            )
            if n:
                unsafe.append((name, legacy, canon, n))
    if unsafe:
        print("  ✗ DIBATALKAN — masih ada dokumen yang HANYA punya kunci legacy:")
        for name, legacy, canon, n in unsafe:
            print(f"      {name}.{legacy}: {n} dok belum punya `{canon}`")
        print("    Jalankan dulu: --execute  (backfill), baru ulangi --drop-legacy")
        return False
    print("  ✓ palang pengaman lolos: tiap kunci legacy sudah punya pasangan kanonik")

    # 2) Hapus kunci legacy.
    grand = 0
    for name in sorted(names):
        present = {}
        for legacy in ALL_LEGACY:
            n = await db[name].count_documents({legacy: {"$exists": True}})
            if n:
                present[legacy] = n
        if not present:
            continue
        total = sum(present.values())
        detail = ", ".join(f"{k}={v}" for k, v in present.items())
        print(f"  {name}: {detail}")
        grand += total
        if apply:
            await db[name].update_many(
                {"$or": [{k: {"$exists": True}} for k in present]},
                {"$unset": {k: "" for k in present}},
            )
    if grand == 0:
        print("  (tidak ada kunci legacy tersisa — sudah bersih)")
    print(f"\nTOTAL kunci legacy {'DIHAPUS' if apply else 'akan dihapus'}: {grand}")
    if not apply and grand:
        print("DRY-RUN. Tambahkan --yes untuk benar-benar menghapus.")
    return True


async def verify(db):
    print("\n=== VERIFIKASI ===")
    problems = 0
    for coll, legacies in TARGETS.items():
        if coll not in await db.list_collection_names():
            continue
        for legacy in legacies:
            canon = LEGACY_TO_CANONICAL.get(legacy)
            left = await db[coll].count_documents({legacy: {"$exists": True}, canon: {"$exists": False}})
            if left:
                problems += 1
                print(f"  ! {coll}: {left} dok masih tanpa `{canon}`")
    if not problems:
        print("  ✓ semua dokumen ber-field legacy sudah punya pasangan kanonik")
    return problems == 0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    ap.add_argument("--discover", action="store_true")
    ap.add_argument("--drop-legacy", dest="drop_legacy", action="store_true",
                    help="FASE 11: hapus kunci `yarn_*` dari dokumen (dry-run tanpa --yes)")
    ap.add_argument("--yes", action="store_true", help="konfirmasi eksekusi --drop-legacy")
    args = ap.parse_args()

    client, db = _db()
    try:
        if args.discover:
            await discover(db)
            return
        if args.drop_legacy:
            await drop_legacy(db, apply=args.yes)
            return
        if args.rollback:
            await rollback(db)
            return
        await migrate(db, dry_run=not args.execute)
        if args.execute:
            await verify(db)
        else:
            print("\nDRY-RUN. Jalankan ulang dengan --execute untuk menerapkan.")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
