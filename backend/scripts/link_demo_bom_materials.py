"""
Demo data fixup (idempotent): tautkan material line pada BOM demo ke master
`rahaza_materials` (via `code`) dan pastikan ada stok di `rahaza_material_stock`,
supaya laporan Kebutuhan Material menampilkan On-hand/Tersedia/Kekurangan + biaya
NYATA (bukan `n/a`) di data demo.

Aman dijalankan berulang:
  · material master dibuat hanya jika belum ada (match by code).
  · stok dibuat hanya jika material belum punya baris stok.
  · BOM material line di-set `material_id` hanya jika masih null & code cocok.

Usage:  cd /app/backend && python scripts/link_demo_bom_materials.py
"""
import asyncio, os, sys, uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
except Exception:
    pass
from motor.motor_asyncio import AsyncIOMotorClient

from core import location_resolver, material_fields  # FASE 12: SSOT zona penyimpanan

# FASE 12 — dulu SEMUA stok demo ditulis ke lokasi pseudo `int-demo-loc-1`
# (`GDG-UTAMA-DEMO`) yang BUKAN zona penyimpanan sehingga tidak pernah muncul di
# Put-Away / Opname per-bin / dropdown lokasi. Sekarang hanya dipakai sebagai
# jaring pengaman terakhir bila struktur zona benar-benar belum ada.
DEMO_LOC_FALLBACK = "int-demo-loc-1"

# Material master yang WAJIB ada agar seluruh BOM demo tertaut (code -> spec + stok demo)
ENSURE_MATERIALS = [
    # (code, name, unit, type, unit_cost, demo_stock_qty)
    ("YRN-DA-CTN",     "Benang Cotton 30s",         "kg",  "yarn",      20000, 450),
    ("ACC-DA-LBL",     "Label Woven DA",            "pcs", "accessory", 500,   1800),
    ("YRN-ACR-28-BLU", "Benang Akrilik 2/28 Biru",  "kg",  "yarn",      45000, 300),
    ("ACC-BTN-12",     "Kancing bulat plastik 12mm","pcs", "accessory", 200,   5000),
    ("ACC-LBL-01",     "Label merek",               "pcs", "accessory", 350,   4000),
]


def now():
    return datetime.now(timezone.utc)


async def main():
    c = AsyncIOMotorClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = c[os.environ.get("DB_NAME", "test_database")]

    created_mat, created_stock, linked_lines = 0, 0, 0
    loc_index = await location_resolver.storage_location_index(db)

    def zone_for(mtype: str) -> str:
        role = material_fields.storage_role_of(mtype)
        return (loc_index.get("roles") or {}).get(role) or DEMO_LOC_FALLBACK

    # 1) ensure materials + demo stock
    code_to_id = {}
    for code, name, unit, mtype, cost, stock_qty in ENSURE_MATERIALS:
        m = await db.rahaza_materials.find_one({"code": code})
        if not m:
            mid = str(uuid.uuid4())
            await db.rahaza_materials.insert_one({
                "id": mid, "code": code, "name": name, "unit": unit, "type": mtype,
                "unit_cost": cost, "min_stock": 0, "active": True,
                "created_at": now(), "updated_at": now(), "_demo": True,
            })
            created_mat += 1
        else:
            mid = m["id"]
            # backfill unit_cost if missing/zero (keeps existing non-zero)
            if not m.get("unit_cost"):
                await db.rahaza_materials.update_one({"id": mid}, {"$set": {"unit_cost": cost, "updated_at": now()}})
        code_to_id[code] = mid
        # ensure at least one stock row
        has_stock = await db.rahaza_material_stock.find_one({"material_id": mid})
        if not has_stock:
            await db.rahaza_material_stock.insert_one({
                "id": str(uuid.uuid4()), "material_id": mid, "location_id": zone_for(mtype),
                "qty": float(stock_qty), "reserved_quantity": 0,
                "created_at": now(), "updated_at": now(), "_demo": True,
            })
            created_stock += 1

    # 2) link BOM material lines by code where material_id is null
    async for b in db.rahaza_boms.find({"active": True}):
        mats = b.get("materials") or []
        changed = False
        for mat in mats:
            if not mat.get("material_id"):
                code = (mat.get("code") or "").strip()
                if code and code in code_to_id:
                    mat["material_id"] = code_to_id[code]
                    changed = True
                    linked_lines += 1
        if changed:
            await db.rahaza_boms.update_one({"id": b["id"]}, {"$set": {"materials": mats, "updated_at": now()}})

    print(f"materials created : {created_mat}")
    print(f"stock rows created: {created_stock}")
    print(f"BOM lines linked  : {linked_lines}")
    print("DONE (idempotent).")
    c.close()


if __name__ == "__main__":
    asyncio.run(main())
