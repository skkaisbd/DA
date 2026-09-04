#!/usr/bin/env python3
"""seed_uji_potongan_nilai.py — data uji SEMENTARA untuk penguji layar (sesi #32).

Kenapa perlu: alur nilai potongan hanya bisa dilihat di layar kalau ada KAIN yang
(a) harganya sudah lahir dari penerimaan, dan (b) punya GULUNGAN — karena sejak
FASE H-6 order cutting menolak kain tanpa gulungan. Kain milik pemilik
(`YRN-DA-CTN`) punya stok & harga tetapi 0 gulungan, jadi tidak bisa dipakai
tanpa mengubah data aslinya.

Yang dibuat: 1 kain `UJI32-KAIN-<stamp>` diterima 120 m @ Rp25.000 (3 gulungan
@40 m) lewat jalur penerimaan barang SUNGGUHAN. Semua bertanda notes
"UJI SESI 32" supaya mudah dihapus.

Pakai:
    python3 scripts/seed_uji_potongan_nilai.py            # buat
    python3 scripts/seed_uji_potongan_nilai.py --cleanup  # hapus semua jejaknya
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(ROOT / "backend"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
MARK = "UJI SESI 32"
G, R, Y, X = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def call(method, path, token=None, body=None):
    req = urllib.request.Request(
        f"{API}{path}", data=json.dumps(body).encode() if body is not None else None,
        method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw or b"{}")
        except ValueError:
            return e.code, {"raw": raw[:300].decode(errors="ignore")}
    except Exception as e:  # noqa: BLE001
        return 0, {"error": str(e)}


def cleanup(db):
    mats = list(db.rahaza_materials.find({"code": {"$regex": "^UJI32-"}}, {"_id": 0, "id": 1}))
    mids = [m["id"] for m in mats]
    panels = [m["id"] for m in db.rahaza_materials.find(
        {"$or": [{"source_material_id": {"$in": mids}}, {"notes": {"$regex": MARK}}],
         "is_cut_panel": True}, {"_id": 0, "id": 1})]
    orders = [o["id"] for o in db.cutting_orders.find(
        {"$or": [{"input_material_id": {"$in": mids}}, {"notes": {"$regex": MARK}}]},
        {"_id": 0, "id": 1})]
    grs = [g["id"] for g in db.warehouse_receiving.find(
        {"notes": {"$regex": MARK}}, {"_id": 0, "id": 1})]
    rolls = [r["id"] for r in db.wh_fabric_rolls.find(
        {"material_id": {"$in": mids}}, {"_id": 0, "id": 1})]
    mis = [m["id"] for m in db.rahaza_material_issues.find(
        {"cutting_order_id": {"$in": orders}}, {"_id": 0, "id": 1})]
    allm = mids + panels
    n = {}
    for name, coll, q in (
        ("MI", "rahaza_material_issues", {"cutting_order_id": {"$in": orders}}),
        ("kartu", "rahaza_material_movements", {"$or": [{"ref_id": {"$in": mis}},
                                                        {"material_id": {"$in": allm}}]}),
        ("progres", "cutting_progress", {"cutting_order_id": {"$in": orders}}),
        ("order", "cutting_orders", {"id": {"$in": orders}}),
        ("roll_mv", "wh_fabric_roll_movements", {"roll_id": {"$in": rolls}}),
        ("roll", "wh_fabric_rolls", {"id": {"$in": rolls}}),
        ("GR", "warehouse_receiving", {"id": {"$in": grs}}),
        ("stok", "rahaza_material_stock", {"material_id": {"$in": allm}}),
        ("ledger", "rahaza_stock_ledger", {"material_id": {"$in": allm}}),
        ("harga", "rahaza_material_cost_history", {"material_id": {"$in": allm}}),
        ("master", "rahaza_materials", {"id": {"$in": allm}}),
    ):
        try:
            n[name] = db[coll].delete_many(q).deleted_count
        except Exception:  # noqa: BLE001
            n[name] = -1
    print(f"{Y}cleanup: " + " · ".join(f"{k}={v}" for k, v in n.items()) + X)


def main():
    db = db_handle()
    if "--cleanup" in sys.argv:
        cleanup(db)
        return 0
    st, d = call("POST", "/api/auth/login", None,
                 {"email": "admin@garment.com", "password": "Admin@123"})
    token = (d or {}).get("token")
    if not token:
        print(f"{R}login gagal HTTP {st}{X}")
        return 2
    stamp = time.strftime("%H%M%S")
    # `--unvalued` menyiapkan kain TANPA harga (unit_price 0) supaya kejujuran
    # "potongan belum bernilai" bisa diuji di layar.
    unvalued = "--unvalued" in sys.argv
    price = 0 if unvalued else 25000
    st, locs = call("GET", "/api/warehouse/locations", token)
    locs = locs if isinstance(locs, list) else (locs or {}).get("items") or []
    loc = next((x for x in locs if "KAIN" in str(x.get("code", "")).upper()), None) or locs[0]

    code = f"UJI32-KAIN-{'NOHARGA-' if unvalued else ''}{stamp}"
    st, mat = call("POST", "/api/rahaza/materials", token, {
        "code": code,
        "name": (f"Kain Uji TANPA Harga {stamp}" if unvalued
                 else f"Kain Uji Nilai Potongan {stamp}"),
        "type": "fabric", "unit": "m", "color": "Navy", "notes": MARK})
    if st != 200 or not (mat or {}).get("id"):
        print(f"{R}gagal membuat material: {mat}{X}")
        return 1
    st, gr = call("POST", "/api/wms/legacy/receiving", token, {
        "source_type": "supplier", "supplier_name": "PT Tekstil Uji 32",
        "location_id": loc.get("id"), "location_name": loc.get("name"), "notes": MARK,
        "items": [{
            "product_name": mat["name"], "sku": code, "material_id": mat["id"],
            "expected_qty": 120, "received_qty": 120, "rejected_qty": 0, "unit": "m",
            "unit_price": price, "inspection_status": "passed",
            "lot_number": f"LOT-UJI32-{stamp}",
            "rolls": [{"qty": 40, "color_lot": f"LOT-UJI32-{stamp}", "notes": ""} for _ in range(3)],
        }]})
    if st not in (200, 201):
        print(f"{R}gagal GR: {gr}{X}")
        return 1
    st, upd = call("PUT", f"/api/wms/legacy/receiving/{gr['id']}", token, {"status": "received"})
    if st != 200:
        print(f"{R}gagal terima GR: {upd}{X}")
        return 1
    rolls = list(db.wh_fabric_rolls.find({"material_id": mat["id"]}, {"_id": 0, "roll_no": 1}))
    fresh = db.rahaza_materials.find_one({"id": mat["id"]}, {"_id": 0, "unit_cost": 1})
    print(f"{G}SIAP{X} kain {code} · stok 120 m @ Rp{float(fresh.get('unit_cost') or 0):,.0f}/m · "
          f"{len(rolls)} gulungan ({', '.join(r['roll_no'] for r in rolls)}) @ {loc.get('name')}")
    print(f"{Y}Hapus lagi dengan: python3 scripts/seed_uji_potongan_nilai.py --cleanup{X}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
