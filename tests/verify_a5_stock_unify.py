"""A5 verification — unifikasi skema rahaza_material_stock.

Membuktikan: setiap jalur tulis menjaga `qty` (kanonik) + alias selaras,
dan reader lintas-domain melihat semua stok. Idempoten & bersih-bersih sendiri.
"""
import asyncio
import os
import sys
import uuid

sys.path.insert(0, "/app/backend")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from core.stock_schema import read_qty, read_available, read_reserved, inc_all_qty  # noqa: E402
import routes.dewi_accessories_stock as acc_stock  # noqa: E402

TAG = "A5TEST-" + uuid.uuid4().hex[:8]
FAILS = []


def check(name, cond, extra=""):
    status = "PASS" if cond else "FAIL"
    if not cond:
        FAILS.append(name)
    print(f"  [{status}] {name} {extra}")


async def main():
    url = os.environ.get("MONGO_URL")
    dbn = os.environ.get("DB_NAME", "garment_erp")
    db = AsyncIOMotorClient(url)[dbn]
    coll = db.rahaza_material_stock

    # ── 0. Pastikan lokasi aksesoris ada ──
    acc_loc_id = await acc_stock._get_accessory_location_id(db)
    print(f"acc_loc_id={acc_loc_id}")

    # ── 1. Jalur AKSESORIS (_add_stock) ──
    acc_mat = f"{TAG}-ACC"
    await acc_stock._add_stock(db, acc_mat, acc_loc_id, 120.0)
    await acc_stock._add_stock(db, acc_mat, acc_loc_id, 30.0)   # total 150
    doc = await coll.find_one({"material_id": acc_mat}, {"_id": 0})
    print("  accessory doc:", doc)
    check("ACC punya qty kanonik", doc and doc.get("qty") == 150.0)
    check("ACC qty==total_qty==quantity", doc and doc.get("qty") == doc.get("total_qty") == doc.get("quantity") == 150.0)
    check("ACC punya location_id datar", doc and doc.get("location_id") == acc_loc_id)
    check("ACC punya id UUID", doc and bool(doc.get("id")))
    # reader aksesoris
    q = await acc_stock._stock_qty(db, acc_mat)
    check("ACC _stock_qty baca 150", q == 150.0, f"(got {q})")

    # ── 2. Cross-read: reader $sum:$qty (spt alerts/fg_matrix) melihat stok aksesoris ──
    agg = await coll.aggregate([
        {"$match": {"material_id": acc_mat}},
        {"$group": {"_id": None, "total": {"$sum": "$qty"}}},
    ]).to_list(1)
    total_qty_sum = float(agg[0]["total"]) if agg else 0.0
    check("Cross-read $sum:$qty lihat aksesoris (150)", total_qty_sum == 150.0, f"(got {total_qty_sum})")

    # ── 3. Jalur FG receipt (bentuk dokumen cmt_packing.approve) ──
    fg_mat = f"FG-{TAG}"
    fg_id = str(uuid.uuid4())
    await coll.insert_one({
        "id": fg_id, "material_id": fg_mat, "material_name": "Kaos Uji A5",
        "type": "finished_goods", "inventory_category": "fg_internal", "ownership": "cv_da",
        "qty": 100.0, "total_qty": 100.0, "quantity": 100.0,
        "available_quantity": 100.0, "reserved_quantity": 0,
        "unit": "pcs", "location": "gudang_fg",
    })
    # simulasi terima tambahan (approve $inc)
    await coll.update_one({"id": fg_id}, {"$inc": {**inc_all_qty(50.0), "available_quantity": 50.0}})
    fg = await coll.find_one({"id": fg_id}, {"_id": 0})
    check("FG qty==quantity==150 setelah receive", fg.get("qty") == fg.get("quantity") == 150.0, f"(qty={fg.get('qty')})")
    check("FG available==150", read_available(fg) == 150.0)

    # ── 4. Jalur fulfillment allocate (reserve): available -=40, reserved +=40; fisik tetap ──
    await coll.update_one({"id": fg_id}, {"$inc": {"available_quantity": -40.0, "reserved_quantity": 40.0}})
    fg = await coll.find_one({"id": fg_id}, {"_id": 0})
    check("FG setelah reserve: qty tetap 150 (fisik)", read_qty(fg) == 150.0, f"(qty={read_qty(fg)})")
    check("FG setelah reserve: available 110", read_available(fg) == 110.0, f"(avail={read_available(fg)})")
    check("FG setelah reserve: reserved 40", read_reserved(fg) == 40.0)

    # ── 5. Jalur fulfillment dispatch: fisik keluar 40 → qty/quantity -=40, reserved -=40 ──
    await coll.update_one({"id": fg_id}, {"$inc": {**inc_all_qty(-40.0), "reserved_quantity": -40.0}})
    fg = await coll.find_one({"id": fg_id}, {"_id": 0})
    check("FG dispatch: qty==quantity==110", fg.get("qty") == fg.get("quantity") == 110.0, f"(qty={fg.get('qty')})")
    check("FG dispatch: available tetap 110", read_available(fg) == 110.0, f"(avail={read_available(fg)})")
    check("FG dispatch: reserved 0", read_reserved(fg) == 0.0)

    # ── 6. read_qty fallback lintas-skema (dok legacy) ──
    check("read_qty dok qty-only", read_qty({"qty": 7}) == 7.0)
    check("read_qty dok total_qty-only", read_qty({"total_qty": 9}) == 9.0)
    check("read_qty dok quantity-only", read_qty({"quantity": 11}) == 11.0)
    check("read_qty dok kosong -> 0", read_qty({}) == 0.0)

    # ── cleanup ──
    await coll.delete_many({"material_id": {"$in": [acc_mat, fg_mat]}})
    print(f"\nCleanup done. FAILS={FAILS}")
    print("RESULT:", "ALL PASS" if not FAILS else f"{len(FAILS)} FAIL")
    sys.exit(1 if FAILS else 0)


asyncio.run(main())
