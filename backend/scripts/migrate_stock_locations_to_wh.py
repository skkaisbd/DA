"""FASE C — Migrasi location_id stok kanonik: rahaza_locations (storage) → wh_zones.

Menggeser `rahaza_material_stock.location_id` dari id LEGACY `rahaza_locations`
(yang ada di `wh_location_migration_map`) ke id KANONIK `wh_zones`.

Sifat:
  * IDEMPOTENT — baris yang sudah di wh_zone tidak disentuh; rerun = no-op.
  * ROW-MERGE — bila (material_id, wh_zone_id) sudah punya baris, qty & reserved
    di-SUM ke baris target lalu baris lama DIHAPUS (jaga alias & available).
  * JURNAL — tiap perubahan dicatat ke `wh_stock_location_migration_log` untuk
    audit + rollback.
  * DUAL-READ aman — pembaca agregasi lintas-lokasi tidak berubah nilainya.

Pakai:
  python -m scripts.migrate_stock_locations_to_wh --dry-run     # simulasi
  python -m scripts.migrate_stock_locations_to_wh               # eksekusi
  python -m scripts.migrate_stock_locations_to_wh --rollback    # kembalikan via jurnal

Catatan: di preview DB kosong → no-op. Skrip diuji dgn data dummy lalu dibersihkan.
"""
import argparse
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

STOCK = "rahaza_material_stock"
LOG = "wh_stock_location_migration_log"


def _now():
    return datetime.now(timezone.utc)


def _uid():
    return str(uuid.uuid4())


def _r(v):
    try:
        return round(float(v or 0), 4)
    except (TypeError, ValueError):
        return 0.0


def _qty(row):
    for k in ("qty", "total_qty", "quantity"):
        if row.get(k) is not None:
            return _r(row.get(k))
    return 0.0


def _reserved(row):
    for k in ("reserved_quantity", "reserved"):
        if row.get(k) is not None:
            return _r(row.get(k))
    return 0.0


def _canonical_fields(qty, reserved):
    avail = _r(qty - reserved)
    return {
        "qty": _r(qty), "total_qty": _r(qty), "quantity": _r(qty),
        "reserved_quantity": _r(reserved),
        "available_quantity": avail, "available": avail,
        "updated_at": _now(),
    }


async def _get_db():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    return client, client[os.environ.get("DB_NAME", "garment_erp")]


async def rahaza_to_wh_map(db) -> dict:
    out = {}
    async for e in db.wh_location_migration_map.find({"active": True}, {"_id": 0}):
        rid, wid = e.get("rahaza_location_id"), e.get("wh_zone_id")
        if rid and wid:
            out[rid] = wid
    return out


async def migrate(db, dry_run: bool):
    mp = await rahaza_to_wh_map(db)
    stats = {"scanned": 0, "moved": 0, "merged": 0, "skipped": 0, "actions": []}
    if not mp:
        print("[migrate] Peta migrasi kosong (tak ada rahaza_location_id → wh_zone). No-op.")
        return stats

    rows = await db[STOCK].find({"location_id": {"$in": list(mp.keys())}}, {"_id": 0}).to_list(100000)
    stats["scanned"] = len(rows)
    for row in rows:
        old_loc = row.get("location_id")
        new_loc = mp.get(old_loc)
        mid = row.get("material_id")
        if not new_loc or not mid or new_loc == old_loc:
            stats["skipped"] += 1
            continue
        qty = _qty(row)
        reserved = _reserved(row)
        target = await db[STOCK].find_one({"material_id": mid, "location_id": new_loc}, {"_id": 0})
        if target and target.get("id") != row.get("id"):
            # MERGE ke target
            new_qty = _r(_qty(target) + qty)
            new_res = _r(_reserved(target) + reserved)
            action = {
                "type": "merge", "stock_id": row.get("id"), "material_id": mid,
                "old_location_id": old_loc, "new_location_id": new_loc,
                "merged_into": target.get("id"),
                "moved_qty": qty, "moved_reserved": reserved,
                "at": _now(),
            }
            if not dry_run:
                await db[STOCK].update_one({"id": target["id"]}, {"$set": _canonical_fields(new_qty, new_res)})
                await db[STOCK].delete_one({"id": row["id"]})
                await db[LOG].insert_one({"id": _uid(), **action})
            stats["merged"] += 1
            stats["actions"].append(action)
        else:
            # MOVE in-place (ubah location_id)
            action = {
                "type": "move", "stock_id": row.get("id"), "material_id": mid,
                "old_location_id": old_loc, "new_location_id": new_loc,
                "merged_into": None, "moved_qty": qty, "moved_reserved": reserved,
                "at": _now(),
            }
            if not dry_run:
                await db[STOCK].update_one({"id": row["id"]}, {"$set": {"location_id": new_loc, "updated_at": _now()}})
                await db[LOG].insert_one({"id": _uid(), **action})
            stats["moved"] += 1
            stats["actions"].append(action)
    return stats


async def rollback(db, dry_run: bool):
    """Kembalikan berdasarkan jurnal (urutan terbalik)."""
    logs = await db[LOG].find({}, {"_id": 0}).sort("at", -1).to_list(100000)
    stats = {"reverted_move": 0, "reverted_merge": 0}
    for lg in logs:
        if lg["type"] == "move":
            if not dry_run:
                await db[STOCK].update_one({"id": lg["stock_id"]},
                                           {"$set": {"location_id": lg["old_location_id"], "updated_at": _now()}})
            stats["reverted_move"] += 1
        elif lg["type"] == "merge":
            # Kembalikan baris lama + kurangi target
            if not dry_run:
                q = _r(lg.get("moved_qty"))
                r = _r(lg.get("moved_reserved"))
                tgt = await db[STOCK].find_one({"id": lg["merged_into"]}, {"_id": 0})
                if tgt:
                    await db[STOCK].update_one({"id": tgt["id"]},
                                               {"$set": _canonical_fields(_r(_qty(tgt) - q), _r(_reserved(tgt) - r))})
                await db[STOCK].insert_one({
                    "id": lg["stock_id"], "material_id": lg["material_id"],
                    "location_id": lg["old_location_id"], **_canonical_fields(q, r),
                    "created_at": _now(),
                })
            stats["reverted_merge"] += 1
    if not dry_run:
        await db[LOG].delete_many({})
    return stats


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--rollback", action="store_true")
    args = ap.parse_args()

    client, db = await _get_db()
    try:
        if args.rollback:
            stats = await rollback(db, args.dry_run)
            print(f"[rollback] {'(dry-run) ' if args.dry_run else ''}{stats}")
        else:
            stats = await migrate(db, args.dry_run)
            print(f"[migrate] {'(dry-run) ' if args.dry_run else ''}scanned={stats['scanned']} "
                  f"moved={stats['moved']} merged={stats['merged']} skipped={stats['skipped']}")
    finally:
        client.close()


if __name__ == "__main__":
    asyncio.run(main())
