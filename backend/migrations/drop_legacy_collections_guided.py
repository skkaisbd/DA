"""Migration: drop koleksi legacy secara TERPANDU (FASE 8.8 / persiapan FASE 9).

Created: 2026-07-25
Reversible: YES (arsip `legacy_archive_<nama>_<ts>` + jurnal `legacy_drop_log` → `--rollback`)

Panduan lengkap + checklist: `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md`

ALUR WAJIB:  --audit  →  --dry-run  →  --execute  →  verifikasi  →  (--rollback bila perlu)

Contoh:
    python3 migrations/drop_legacy_collections_guided.py --audit
    python3 migrations/drop_legacy_collections_guided.py --group opname_v1 --dry-run
    python3 migrations/drop_legacy_collections_guided.py --group opname_v1 --execute
    python3 migrations/drop_legacy_collections_guided.py --logs
    python3 migrations/drop_legacy_collections_guided.py --rollback <log_id>
    python3 migrations/drop_legacy_collections_guided.py --purge-archives --older-than-days 30
"""
import argparse
import asyncio
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv  # noqa: E402

_BE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_BE, ".env"))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

LOG_COLL = "legacy_drop_log"
ARCHIVE_PREFIX = "legacy_archive_"

# Grup kandidat + alasan + status kesiapan (lihat panduan untuk detail prasyarat).
GROUPS = {
    "opname_v1": {
        "ready": True,
        "reason": "Opname GEN2 dihapus di FASE 5; SSOT = wh_opname_sessions2 (Opname3 scan-driven).",
        "collections": ["wh_opname_sessions", "wh_opname_items"],
    },
    "warehouse_ledger": {
        "ready": True,
        "reason": ("Ledger gudang legacy sudah dinetralkan di FASE F/F+ — SSOT = "
                   "rahaza_material_stock + rahaza_stock_ledger + wh_zones. "
                   "Skrip khusus: migrate_drop_warehouse_ledger_legacy.py."),
        "collections": ["warehouse_stock", "warehouse_movements", "warehouse_putaway",
                        "warehouse_opname", "warehouse_locations"],
    },
    "accessory_legacy": {
        "ready": True,
        "reason": ("PRASYARAT SELESAI di FASE 10 (2026-07-25): "
                   "(1) UI Request Internal & seluruh endpoint pindah ke SSOT "
                   "dewi_accessory_requests (request_type='internal_issuance') — endpoint "
                   "/api/acc/internal-requests/* kini 410, dan /deliver SSOT sudah memotong "
                   "stok + jurnal; (2) peminjaman pindah ke dewi_asset_loans — /api/acc/loans/* "
                   "kini 410, tab 'Peminjaman' dilepas dari UI, pinjaman lama ditutup lewat "
                   "migrations/close_legacy_acc_loans.py (stok dikembalikan, bisa rollback); "
                   "(3) _enrich_movement di 6 modul berhenti membaca koleksi legacy; "
                   "(4) KPI 'Dipinjam Aktif' diganti 'Perlu Diserahkan'."),
        "collections": ["acc_loans", "acc_internal_requests"],
    },
    "accessory_master_legacy": {
        "ready": True,
        "reason": "Sudah di-drop Session #11.16 Phase A (SSOT rahaza_materials). Jaring pengaman.",
        "collections": ["accessories", "accessory_requests"],
    },
}


def _db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "test_database")]


def _now():
    return datetime.now(timezone.utc)


def _p(title):
    print("\n" + "=" * 74)
    print(title)
    print("=" * 74)


def _code_refs(name: str) -> int:
    """Hitung rujukan nama koleksi di kode backend AKTIF (abaikan arsip/migrasi/cache).

    Heuristik — hasilnya WAJIB diverifikasi manual sebelum drop.
    """
    try:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", rf"\b{re.escape(name)}\b", _BE],
            capture_output=True, text=True, timeout=60,
        ).stdout
    except Exception:
        return -1
    keep = [
        ln for ln in out.splitlines()
        if "__pycache__" not in ln and "/migrations/" not in ln and "/_archive/" not in ln
        and "/tests/" not in ln
    ]
    return len(keep)


async def audit(db):
    _p("AUDIT — status koleksi kandidat")
    names = set(await db.list_collection_names())
    print(f"Total koleksi di database: {len(names)}\n")
    for gname, g in GROUPS.items():
        flag = "SIAP" if g["ready"] else "BELUM SIAP"
        print(f"[{flag}] grup {gname}")
        print(f"    alasan: {g['reason']}")
        for coll in g["collections"]:
            if coll in names:
                cnt = await db[coll].count_documents({})
                refs = _code_refs(coll)
                print(f"    - {coll:28s} ADA      docs={cnt:<8d} rujukan kode aktif={refs}")
            else:
                print(f"    - {coll:28s} tidak ada (no-op)")
        print()
    archives = sorted(n for n in names if n.startswith(ARCHIVE_PREFIX))
    if archives:
        print("Arsip yang tersimpan:")
        for a in archives:
            print(f"    - {a} ({await db[a].count_documents({})} dok)")


async def run_group(db, group: str, *, dry_run=True, force=False):
    g = GROUPS.get(group)
    if not g:
        print(f"Grup '{group}' tidak dikenal. Pilihan: {', '.join(GROUPS)}")
        return
    if not g["ready"] and not force:
        _p(f"GRUP '{group}' DITANDAI BELUM SIAP — DIBATALKAN")
        print(g["reason"])
        print("\nSelesaikan prasyarat di memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md §3.")
        print("Bila Anda benar-benar yakin, ulangi dengan --force (tanggung jawab Anda).")
        return

    _p(f"{'DRY-RUN' if dry_run else 'EKSEKUSI'} grup '{group}'")
    names = set(await db.list_collection_names())
    plan = []
    for coll in g["collections"]:
        if coll not in names:
            print(f"  - {coll}: tidak ada → skip")
            continue
        cnt = await db[coll].count_documents({})
        refs = _code_refs(coll)
        print(f"  - {coll}: {cnt} dok, rujukan kode aktif={refs}"
              + ("  ⚠ MASIH DIRUJUK KODE" if refs > 0 else ""))
        plan.append({"collection": coll, "docs": cnt, "code_refs": refs})

    if not plan:
        print("\nTidak ada yang perlu dikerjakan (semua koleksi sudah tidak ada).")
        return
    if dry_run:
        print("\nDRY-RUN — tidak ada yang ditulis. Jalankan ulang dengan --execute.")
        return

    ts = _now().strftime("%Y%m%d%H%M%S")
    log_id = str(uuid.uuid4())
    entries = []
    for item in plan:
        coll = item["collection"]
        archive = f"{ARCHIVE_PREFIX}{coll}_{ts}"
        moved = 0
        if item["docs"]:
            batch = []
            async for doc in db[coll].find({}):
                doc.pop("_id", None)
                batch.append(doc)
                if len(batch) >= 500:
                    await db[archive].insert_many(batch)
                    moved += len(batch)
                    batch = []
            if batch:
                await db[archive].insert_many(batch)
                moved += len(batch)
            archived_cnt = await db[archive].count_documents({})
            assert archived_cnt == item["docs"], \
                f"FATAL: arsip {archive} {archived_cnt} ≠ sumber {item['docs']} — drop DIBATALKAN"
        await db[coll].drop()
        print(f"  ✓ {coll}: {moved} dok diarsipkan ke {archive}, koleksi di-drop")
        entries.append({"collection": coll, "archive": archive, "docs": item["docs"],
                        "code_refs": item["code_refs"]})

    await db[LOG_COLL].insert_one({
        "id": log_id,
        "group": group,
        "created_at": _now(),
        "entries": entries,
        "restored_at": None,
    })
    print(f"\nlog_id = {log_id}   (rollback: --rollback {log_id})")
    print("LANGKAH BERIKUTNYA (WAJIB): hapus baris create_index koleksi ini dari "
          "server.py::startup_event, lalu restart backend dan pastikan koleksi TIDAK lahir kembali.")


async def rollback(db, log_id: str):
    _p(f"ROLLBACK {log_id}")
    log = await db[LOG_COLL].find_one({"id": log_id}, {"_id": 0})
    if not log:
        print("Log tidak ditemukan.")
        return
    if log.get("restored_at"):
        print("Log ini sudah pernah di-rollback.")
        return
    for e in log.get("entries", []):
        coll, archive = e["collection"], e["archive"]
        names = set(await db.list_collection_names())
        if archive not in names:
            print(f"  ! arsip {archive} tidak ada — {coll} tidak bisa dipulihkan")
            continue
        docs = []
        async for d in db[archive].find({}):
            d.pop("_id", None)
            docs.append(d)
        if docs:
            await db[coll].insert_many(docs)
        print(f"  ✓ {coll}: {len(docs)} dok dipulihkan dari {archive}")
    await db[LOG_COLL].update_one({"id": log_id}, {"$set": {"restored_at": _now()}})
    print("\nCATATAN: indeks TIDAK dipulihkan oleh skrip ini — restart backend agar "
          "startup_event membuatnya kembali (bila baris create_index masih ada).")


async def logs(db):
    _p("RIWAYAT DROP LEGACY")
    rows = await db[LOG_COLL].find({}, {"_id": 0}).sort("created_at", -1).to_list(50)
    if not rows:
        print("(belum ada eksekusi)")
    for r in rows:
        colls = ", ".join(e["collection"] for e in r.get("entries", []))
        print(f"- {r['id']} · {r.get('created_at')} · grup={r.get('group')} · "
              f"restored={bool(r.get('restored_at'))}\n    {colls}")


async def purge_archives(db, older_than_days: int, *, dry_run=True):
    _p(f"PURGE ARSIP > {older_than_days} hari (dry_run={dry_run})")
    cutoff = _now() - timedelta(days=older_than_days)
    names = sorted(n for n in await db.list_collection_names() if n.startswith(ARCHIVE_PREFIX))
    for n in names:
        m = re.search(r"_(\d{14})$", n)
        if not m:
            print(f"  ? {n}: tak bisa membaca timestamp — dilewati")
            continue
        when = datetime.strptime(m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
        if when >= cutoff:
            print(f"  - {n}: masih dalam periode aman ({when.date()})")
            continue
        print(f"  {'akan dihapus' if dry_run else 'dihapus'}: {n} ({when.date()})")
        if not dry_run:
            await db[n].drop()


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", action="store_true")
    ap.add_argument("--group", choices=list(GROUPS))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--force", action="store_true", help="paksa grup yang ditandai BELUM SIAP")
    ap.add_argument("--rollback", metavar="LOG_ID")
    ap.add_argument("--logs", action="store_true")
    ap.add_argument("--purge-archives", action="store_true")
    ap.add_argument("--older-than-days", type=int, default=30)
    args = ap.parse_args()

    client, db = _db()
    try:
        if args.logs:
            await logs(db)
        elif args.rollback:
            await rollback(db, args.rollback)
        elif args.purge_archives:
            await purge_archives(db, args.older_than_days, dry_run=not args.execute)
        elif args.group:
            await run_group(db, args.group, dry_run=not args.execute, force=args.force)
        else:
            await audit(db)
            print("\nBaca memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md sebelum menjalankan --execute.")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
