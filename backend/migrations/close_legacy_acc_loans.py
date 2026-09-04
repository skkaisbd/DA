"""Migration: TUTUP PINJAMAN AKSESORIS LEGACY (`acc_loans`) secara TERPANDU.

Created: 2026-07-25 (FASE 10 — prasyarat drop grup `accessory_legacy`)
Reversible: YES (jurnal `legacy_loan_close_log` → `--rollback <log_id>`)

KENAPA
Peminjaman sudah pindah ke domain ASET (`dewi_asset_loans`, ACC-3). Sisa dokumen
`acc_loans` berstatus `Active` menghalangi drop koleksi: kalau langsung di-drop,
stok aksesoris yang DULU dipotong saat pinjam tidak akan pernah kembali dan nilai
persediaan jadi salah selamanya.

APA YANG DILAKUKAN (sama persis dengan tombol "Kembalikan" versi lama)
  1. Setiap pinjaman `Active` → stok aksesoris DIKEMBALIKAN (+qty) ke area aksesoris,
  2. Kartu stok mendapat baris `receive` bertanda "penutupan pinjaman legacy",
  3. Dokumen pinjaman ditandai `status='closed_legacy'` + `closed_reason` + waktu,
  4. Semua langkah dicatat di `legacy_loan_close_log` supaya bisa DIBATALKAN.

ALUR WAJIB:  --audit  →  --dry-run  →  --execute  →  verifikasi  →  (--rollback bila perlu)

Contoh:
    python3 migrations/close_legacy_acc_loans.py --audit
    python3 migrations/close_legacy_acc_loans.py --dry-run
    python3 migrations/close_legacy_acc_loans.py --execute
    python3 migrations/close_legacy_acc_loans.py --logs
    python3 migrations/close_legacy_acc_loans.py --rollback <log_id>

Opsi:
    --no-restore-stock   tutup pinjaman TANPA mengembalikan stok (dipakai bila stok
                         sudah direkonsiliasi lewat opname; tetap tercatat di jurnal)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

_BE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BE, ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

LOG_COLL = "legacy_loan_close_log"
LOANS = "acc_loans"
CLOSED_STATUS = "closed_legacy"
SYSTEM_ACTOR = {"id": "system-migration", "name": "Migrasi FASE 10"}


def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "test_database")]


def _now():
    return datetime.now(timezone.utc)


def _p(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


async def _active_loans(db) -> list[dict]:
    names = await db.list_collection_names()
    if LOANS not in names:
        return []
    return await db[LOANS].find({"status": "Active"}, {"_id": 0}).to_list(5000)


async def audit(db) -> int:
    _p("AUDIT — pinjaman aksesoris legacy")
    names = await db.list_collection_names()
    if LOANS not in names:
        print(f"Koleksi `{LOANS}` tidak ada di database ini ⇒ tidak ada yang perlu ditutup.")
        print("Grup `accessory_legacy` SIAP dari sisi pinjaman.")
        return 0
    total = await db[LOANS].count_documents({})
    active = await db[LOANS].count_documents({"status": "Active"})
    returned = await db[LOANS].count_documents({"status": "Returned"})
    closed = await db[LOANS].count_documents({"status": CLOSED_STATUS})
    print(f"total dokumen        : {total}")
    print(f"  Active (menggantung): {active}")
    print(f"  Returned            : {returned}")
    print(f"  closed_legacy       : {closed}")
    if active:
        print("\nDaftar pinjaman yang masih menggantung:")
        for ln in await _active_loans(db):
            items = ", ".join(
                f"{it.get('acc_name') or it.get('acc_id')} {it.get('qty')} {it.get('unit', '')}".strip()
                for it in (ln.get("items") or [])) or "(tanpa item)"
            print(f"  - {ln.get('loan_number')} · {ln.get('borrower_name')} "
                  f"({ln.get('borrower_divisi', '-')}) · {items}")
        print(f"\n⚠ {active} pinjaman harus ditutup dulu sebelum `acc_loans` boleh di-drop.")
    else:
        print("\nTidak ada pinjaman menggantung ⇒ siap di-drop.")
    return 0


async def _close(db, *, dry_run: bool, restore_stock: bool) -> int:
    mode = "DRY-RUN (tidak menulis apa pun)" if dry_run else "EKSEKUSI"
    _p(f"TUTUP PINJAMAN LEGACY — {mode}"
       + ("" if restore_stock else " · TANPA pengembalian stok"))
    loans = await _active_loans(db)
    if not loans:
        print("Tidak ada pinjaman berstatus Active — no-op.")
        return 0

    from core.accessory_stock import add_stock, get_accessory_location_id  # noqa: E402
    from routes.dewi_accessories_stock import _log_movement  # noqa: E402

    log_id = str(uuid.uuid4())
    entries: list[dict] = []
    loc_id = None if dry_run else await get_accessory_location_id(db)

    for ln in loans:
        moves: list[dict] = []
        for it in ln.get("items") or []:
            acc_id = it.get("acc_id")
            try:
                qty = float(it.get("qty") or 0)
            except (TypeError, ValueError):
                qty = 0.0
            if not acc_id or qty <= 0:
                continue
            mat = await db.rahaza_materials.find_one({"id": acc_id},
                                                     {"_id": 0, "code": 1, "name": 1})
            label = (mat or {}).get("code") or acc_id
            if dry_run:
                print(f"  [dry-run] {ln.get('loan_number')}: +{qty:g} → {label}"
                      if restore_stock else
                      f"  [dry-run] {ln.get('loan_number')}: {label} (stok tidak diubah)")
                moves.append({"material_id": acc_id, "qty": qty, "restored": restore_stock})
                continue
            mv_id = ""
            if restore_stock:
                await add_stock(db, acc_id, loc_id, qty)
                mv = await _log_movement(
                    db, SYSTEM_ACTOR, material_id=acc_id, mv_type="receive", qty=qty,
                    related_type="legacy_loan_close", related_ref=ln.get("id", ""),
                    notes=(f"Penutupan pinjaman legacy {ln.get('loan_number')} — "
                           f"{ln.get('borrower_name', '')}"),
                )
                mv_id = (mv or {}).get("id", "")
                print(f"  · {ln.get('loan_number')}: stok {label} dikembalikan +{qty:g}")
            moves.append({"material_id": acc_id, "qty": qty, "restored": restore_stock,
                          "movement_id": mv_id})
        if not dry_run:
            await db[LOANS].update_one({"id": ln["id"]}, {"$set": {
                "status": CLOSED_STATUS,
                "closed_reason": ("Ditutup otomatis saat migrasi FASE 10 — peminjaman pindah ke "
                                  "Manajemen Aset (dewi_asset_loans)."),
                "closed_at": _now(),
                "closed_by": SYSTEM_ACTOR["name"],
                "stock_restored": restore_stock,
                "legacy_close_log_id": log_id,
                "updated_at": _now(),
            }})
        entries.append({"loan_id": ln["id"], "loan_number": ln.get("loan_number"),
                        "borrower": ln.get("borrower_name"), "prev_status": "Active",
                        "moves": moves})

    print(f"\n{'Akan ditutup' if dry_run else 'Ditutup'}: {len(entries)} pinjaman · "
          f"{sum(len(e['moves']) for e in entries)} baris item")
    if dry_run:
        print("Tidak ada perubahan yang ditulis (dry-run).")
        return 0

    await db[LOG_COLL].insert_one({
        "id": log_id,
        "kind": "close_legacy_acc_loans",
        "created_at": _now(),
        "restore_stock": restore_stock,
        "loans_closed": len(entries),
        "entries": entries,
        "rolled_back": False,
    })
    print(f"Jurnal migrasi: {log_id}  (batalkan dengan --rollback {log_id})")
    return 0


async def rollback(db, log_id: str) -> int:
    _p(f"ROLLBACK penutupan pinjaman — {log_id}")
    log = await db[LOG_COLL].find_one({"id": log_id})
    if not log:
        print("Jurnal tidak ditemukan.")
        return 1
    if log.get("rolled_back"):
        print("Jurnal ini SUDAH pernah di-rollback — ditolak (mencegah stok dobel).")
        return 1

    from core.accessory_stock import add_stock, get_accessory_location_id  # noqa: E402

    loc_id = await get_accessory_location_id(db)
    restored = 0
    for e in log.get("entries", []):
        for mv in e.get("moves", []):
            if mv.get("restored") and mv.get("qty"):
                await add_stock(db, mv["material_id"], loc_id, -float(mv["qty"]))
                if mv.get("movement_id"):
                    await db.rahaza_material_movements.delete_one({"id": mv["movement_id"]})
                    await db.rahaza_stock_ledger.delete_many({"ref_id": mv["movement_id"]})
                restored += 1
        await db[LOANS].update_one({"id": e["loan_id"]}, {
            "$set": {"status": e.get("prev_status", "Active"), "updated_at": _now()},
            "$unset": {"closed_reason": "", "closed_at": "", "closed_by": "",
                       "stock_restored": "", "legacy_close_log_id": ""},
        })
    await db[LOG_COLL].update_one({"id": log_id}, {"$set": {
        "rolled_back": True, "rolled_back_at": _now()}})
    print(f"Dipulihkan: {len(log.get('entries', []))} pinjaman · {restored} baris stok dikembalikan.")
    return 0


async def logs(db) -> int:
    _p("JURNAL PENUTUPAN PINJAMAN LEGACY")
    rows = await db[LOG_COLL].find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    if not rows:
        print("(belum ada)")
        return 0
    for r in rows:
        print(f"  {r['id']} · {r.get('created_at')} · {r.get('loans_closed')} pinjaman · "
              f"restore_stock={r.get('restore_stock')} · rolled_back={r.get('rolled_back')}")
    return 0


async def main() -> int:
    ap = argparse.ArgumentParser(description="Tutup pinjaman aksesoris legacy (acc_loans)")
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--rollback", metavar="LOG_ID")
    ap.add_argument("--logs", action="store_true")
    ap.add_argument("--no-restore-stock", action="store_true",
                    help="tutup tanpa mengembalikan stok (stok sudah direkonsiliasi opname)")
    args = ap.parse_args()

    client, db = _db()
    try:
        if args.audit:
            return await audit(db)
        if args.dry_run:
            return await _close(db, dry_run=True, restore_stock=not args.no_restore_stock)
        if args.execute:
            return await _close(db, dry_run=False, restore_stock=not args.no_restore_stock)
        if args.rollback:
            return await rollback(db, args.rollback)
        if args.logs:
            return await logs(db)
        ap.print_help()
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
