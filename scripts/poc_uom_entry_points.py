#!/usr/bin/env python3
"""poc_uom_entry_points.py — bukti konversi satuan di 2 titik masuk stok terakhir.

Menguji:
  * POST /api/wms/putaway/place   dengan `input_uom`
  * POST /api/wms/opname3/scan    dan /scan-undo dengan `input_uom`

Semua artefak uji dibersihkan di akhir (material, stok, ledger, bin, sesi).
    python3 scripts/poc_uom_entry_points.py
"""
from __future__ import annotations

import os
import sys
import uuid
import asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
except Exception:  # noqa: BLE001
    pass

import requests  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

API = os.environ.get("INTERNAL_API_URL", "http://localhost:8001")
MAT_CODE = "ZZTEST-UOM-A1"
BIN_BARCODE = "ZZBIN-UOM-A1"

results: list[tuple[bool, str]] = []


def check(cond: bool, label: str):
    results.append((bool(cond), label))
    print(("  ✓ " if cond else "  ✗ ") + label)


def db():
    return AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


async def setup():
    d = db()
    await teardown(d, quiet=True)
    loc = await d.rahaza_locations.find_one({}, {"_id": 0, "id": 1})
    mat_id = str(uuid.uuid4())
    await d.rahaza_materials.insert_one({
        "id": mat_id, "code": MAT_CODE, "name": "Uji Konversi Satuan", "type": "accessory",
        "unit": "pcs", "base_uom": "pcs", "pack_unit": "box", "pack_size": 12.0,
        "display_in_packs": True, "purchase_uom": "box", "issue_uom": "pcs", "display_uom": "box",
        "unit_cost": 1000.0, "active": True,
        "uoms": [
            {"code": "pcs", "name": "PCS", "factor": 1.0, "is_base": True, "level": 0},
            {"code": "box", "name": "BOX", "factor": 12.0, "is_base": False, "level": 1,
             "parent": "pcs", "is_purchase_default": True, "is_display_default": True},
        ],
    })
    await d.rahaza_material_stock.insert_one({
        "id": str(uuid.uuid4()), "material_id": mat_id,
        "location_id": (loc or {}).get("id"), "qty": 120.0,
    })
    bin_id = str(uuid.uuid4())
    await d.wh_positions.insert_one({
        "id": bin_id, "barcode": BIN_BARCODE, "label": "UJI-A1", "status": "empty", "qty": 0,
    })
    return mat_id, bin_id


async def teardown(d=None, quiet: bool = False):
    d = d if d is not None else db()
    mats = await d.rahaza_materials.find({"code": MAT_CODE}, {"_id": 0, "id": 1}).to_list(10)
    ids = [m["id"] for m in mats]
    if ids:
        await d.rahaza_material_stock.delete_many({"material_id": {"$in": ids}})
        await d.rahaza_stock_ledger.delete_many({"material_id": {"$in": ids}})
        await d.wh_placement_movements.delete_many({"material_id": {"$in": ids}})
        await d.wh_opname3_counts.delete_many({"material_id": {"$in": ids}})
        await d.rahaza_materials.delete_many({"code": MAT_CODE})
    bins = await d.wh_positions.find({"barcode": BIN_BARCODE}, {"_id": 0, "id": 1}).to_list(10)
    if bins:
        bid = [b["id"] for b in bins]
        await d.wh_opname3_counts.delete_many({"bin_id": {"$in": bid}})
        await d.wh_positions.delete_many({"barcode": BIN_BARCODE})
    for s in await d.wh_opname3_sessions.find({"notes": "POC-UOM-A1"}, {"_id": 0, "id": 1}).to_list(50):
        await d.wh_opname3_counts.delete_many({"session_id": s["id"]})
        await d.wh_opname3_sessions.delete_many({"id": s["id"]})
    if not quiet:
        print("  · artefak uji dibersihkan")


def login() -> dict:
    r = requests.post(f"{API}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    r.raise_for_status()
    b = r.json()
    return {"Authorization": f"Bearer {b.get('access_token') or b.get('token')}"}


def main():
    mat_id, bin_id = asyncio.run(setup())
    hdr = login()
    try:
        print("\n1) Put-away dengan input_uom=box")
        r = requests.post(f"{API}/api/wms/putaway/place", headers=hdr, timeout=30, json={
            "material_id": mat_id, "qty": 2, "input_uom": "box", "position_barcode": BIN_BARCODE})
        body = r.json()
        check(r.status_code == 200, f"HTTP 200 (dapat {r.status_code}: {str(body)[:100]})")
        check(body.get("placed_qty") == 24, f"2 box → 24 pcs ditempatkan (dapat {body.get('placed_qty')})")
        check(body.get("remaining_unshelved") == 96, f"sisa belum dirak 96 pcs (dapat {body.get('remaining_unshelved')})")

        print("\n2) Put-away tanpa input_uom (perilaku lama TIDAK berubah)")
        r = requests.post(f"{API}/api/wms/putaway/place", headers=hdr, timeout=30, json={
            "material_id": mat_id, "qty": 6, "position_barcode": BIN_BARCODE})
        body = r.json()
        check(body.get("placed_qty") == 6, f"6 → 6 pcs (dapat {body.get('placed_qty')})")

        print("\n3) Put-away satuan tak dikenal → 400")
        r = requests.post(f"{API}/api/wms/putaway/place", headers=hdr, timeout=30, json={
            "material_id": mat_id, "qty": 1, "input_uom": "karung", "position_barcode": BIN_BARCODE})
        check(r.status_code == 400, f"HTTP 400 (dapat {r.status_code})")

        print("\n4) Opname scan dengan input_uom=box")
        r = requests.post(f"{API}/api/wms/opname3/sessions", headers=hdr, timeout=30,
                          json={"scope_type": "all", "notes": "POC-UOM-A1"})
        sess = r.json()
        check(r.status_code == 200, f"sesi dibuat (dapat {r.status_code})")
        sid = sess.get("id")

        r = requests.post(f"{API}/api/wms/opname3/scan", headers=hdr, timeout=30, json={
            "session_id": sid, "bin_id": bin_id, "item_material_id": mat_id,
            "qty": 1, "input_uom": "box"})
        body = r.json()
        check(body.get("counted_qty") == 12, f"1 box → tercatat 12 pcs (dapat {body.get('counted_qty')})")
        check(body.get("base_uom") == "pcs", f"base_uom=pcs (dapat {body.get('base_uom')})")

        r = requests.post(f"{API}/api/wms/opname3/scan", headers=hdr, timeout=30, json={
            "session_id": sid, "bin_id": bin_id, "item_material_id": mat_id, "qty": 12})
        check(r.json().get("counted_qty") == 24, f"+12 pcs → 24 (dapat {r.json().get('counted_qty')})")

        r = requests.post(f"{API}/api/wms/opname3/scan-undo", headers=hdr, timeout=30, json={
            "session_id": sid, "bin_id": bin_id, "item_material_id": mat_id,
            "qty": 1, "input_uom": "box"})
        check(r.json().get("counted_qty") == 12, f"undo 1 box → 12 (dapat {r.json().get('counted_qty')})")

        r = requests.post(f"{API}/api/wms/opname3/scan", headers=hdr, timeout=30, json={
            "session_id": sid, "bin_id": bin_id, "item_material_id": mat_id,
            "qty": 1, "input_uom": "karung"})
        check(r.status_code == 400, f"satuan asing ditolak 400 (dapat {r.status_code})")
    finally:
        print("\n5) Bersih-bersih")
        asyncio.run(teardown())

    ok = sum(1 for c, _ in results if c)
    print(f"\n{'='*60}\n{ok}/{len(results)} LULUS")
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
