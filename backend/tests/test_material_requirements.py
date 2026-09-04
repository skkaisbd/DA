"""Focused test for POST /api/rahaza/material-requirements (Fase 5 MRP-lite).
Seeds properly material_id-linked data, verifies cross-line aggregation +
stock/shortfall + PO mode, then cleans up its own test docs.
"""
import asyncio, os, sys, uuid
from datetime import datetime, timezone
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001"
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB = os.environ.get("DB_NAME", "test_database")
SIZE_L = "a3539e1f-06dc-4462-b5e9-9e6958a5e8ce"  # existing seeded size L

MAT_ID = "mrp-test-mat-1"
MODEL_A = "mrp-test-model-a"
MODEL_B = "mrp-test-model-b"
BOM_A = "mrp-test-bom-a"
BOM_B = "mrp-test-bom-b"


def now():
    return datetime.now(timezone.utc)


def token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    return r.json()["token"]


async def seed(db):
    await cleanup(db)
    await db.rahaza_materials.insert_one({"id": MAT_ID, "code": "TESTYRN", "name": "Test Yarn 30s",
                                          "type": "yarn", "material_type": "yarn", "unit": "kg",
                                          "unit_cost": 50000,
                                          "active": True, "created_at": now(), "updated_at": now()})
    # stock: onhand 30, reserved 5 -> available 25
    await db.rahaza_material_stock.insert_one({"id": str(uuid.uuid4()), "material_id": MAT_ID,
                                               "location_id": "MRP-TEST-LOC", "qty": 30,
                                               "reserved_quantity": 5, "created_at": now()})
    for mid, code, name in [(MODEL_A, "MRPA", "MRP Test A"), (MODEL_B, "MRPB", "MRP Test B")]:
        await db.rahaza_models.insert_one({"id": mid, "code": code, "name": name, "category": "Test",
                                           "active": True, "created_at": now(), "updated_at": now()})
    # BOM A@L uses 0.25 kg/pcs; BOM B@L uses 0.10 kg/pcs (both linked to MAT_ID)
    for bid, mid, qty in [(BOM_A, MODEL_A, 0.25), (BOM_B, MODEL_B, 0.10)]:
        await db.rahaza_boms.insert_one({
            "id": bid, "model_id": mid, "size_id": SIZE_L, "color": "", "version": 1,
            "is_active": True, "active": True,
            "materials": [{"material_id": MAT_ID, "code": "TESTYRN", "name": "Test Yarn 30s",
                           "material_type": "yarn", "category": "", "category_name": "Benang",
                           "qty": qty, "unit": "kg", "notes": ""}],
            "created_at": now(), "updated_at": now(),
        })


async def cleanup(db):
    await db.rahaza_materials.delete_many({"id": MAT_ID})
    await db.rahaza_material_stock.delete_many({"material_id": MAT_ID})
    await db.rahaza_models.delete_many({"id": {"$in": [MODEL_A, MODEL_B]}})
    await db.rahaza_boms.delete_many({"id": {"$in": [BOM_A, BOM_B]}})


async def main():
    client = AsyncIOMotorClient(MONGO)
    db = client[DB]
    ok = True
    try:
        await seed(db)
        tok = token()
        H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

        # --- Manual lines: A@L x100 (0.25) + B@L x200 (0.10) = 25 + 20 = 45 kg required ---
        r = requests.post(f"{BASE}/api/rahaza/material-requirements", headers=H, json={
            "lines": [{"model_id": MODEL_A, "size_id": SIZE_L, "qty_pcs": 100},
                      {"model_id": MODEL_B, "size_id": SIZE_L, "qty_pcs": 200}],
            "rounding": "none", "include_stock": True,
        })
        assert r.status_code == 200, f"manual mode HTTP {r.status_code}: {r.text[:200]}"
        d = r.json()
        print("MANUAL mode:", d["totals"])
        agg = d["aggregated"]
        assert len(agg) == 1, f"expected 1 aggregated material, got {len(agg)}"
        m = agg[0]
        assert abs(m["total_required"] - 45.0) < 1e-6, f"required should be 45, got {m['total_required']}"
        assert m["onhand"] == 30.0, f"onhand should be 30, got {m['onhand']}"
        assert m["available"] == 25.0, f"available should be 25, got {m['available']}"
        assert abs(m["shortfall"] - 20.0) < 1e-6, f"shortfall should be 20, got {m['shortfall']}"
        # FASE 11: alias legacy `total_yarn_kg` tidak ditulis lagi → pakai nama kanonik.
        assert d["totals"]["total_material_kg"] == 45.0
        assert d["totals"]["total_shortfall_lines"] == 1
        assert d["totals"]["lines_resolved_count"] == 2
        print("  cross-line aggregation + stock + shortfall: OK (45 req, 25 avail, 20 short)")

        # --- cost estimate: 45 kg x 50000 = 2,250,000 (source=material) ---
        assert abs(m["unit_cost"] - 50000.0) < 1e-6, f"unit_cost should be 50000, got {m['unit_cost']}"
        assert m["cost_source"] == "material", f"cost_source should be material, got {m['cost_source']}"
        assert abs(m["subtotal_cost"] - 2250000.0) < 1e-6, f"subtotal should be 2,250,000, got {m['subtotal_cost']}"
        assert abs(d["totals"]["grand_total_cost"] - 2250000.0) < 1e-6, f"grand_total_cost wrong: {d['totals']['grand_total_cost']}"
        print("  cost estimate (material unit_cost) OK: Rp", int(d["totals"]["grand_total_cost"]))

        # --- rounding ceil check on a fractional line ---
        r2 = requests.post(f"{BASE}/api/rahaza/material-requirements", headers=H, json={
            "lines": [{"model_id": MODEL_A, "size_id": SIZE_L, "qty_pcs": 3}],  # 0.25*3=0.75
            "rounding": "ceil",
        })
        d2 = r2.json()
        assert d2["aggregated"][0]["total_required"] == 0.75, d2["aggregated"][0]["total_required"]
        print("  kg rounding (ceil, 3dp) OK:", d2["aggregated"][0]["total_required"])

        # --- line without BOM (model B at a size with no BOM) ---
        r3 = requests.post(f"{BASE}/api/rahaza/material-requirements", headers=H, json={
            "lines": [{"model_id": MODEL_A, "size_id": "nonexistent-size", "qty_pcs": 10}],
        })
        d3 = r3.json()
        assert d3["totals"]["lines_without_bom_count"] == 1, d3["totals"]
        print("  line-without-BOM handled gracefully: OK")

        # --- PO mode (existing demo internal PO) ---
        r4 = requests.post(f"{BASE}/api/rahaza/material-requirements", headers=H,
                           json={"po_id": "po-int-demo-1"})
        assert r4.status_code == 200, r4.text[:200]
        d4 = r4.json()
        assert d4["source"] == "po" and d4["po"]["po_number"] == "PO-INT-DEMO-1"
        assert d4["totals"]["total_material_lines"] >= 1
        print("  PO mode:", d4["po"]["po_number"], d4["totals"])

        print("\n✅ ALL MRP ASSERTIONS PASSED")
    except AssertionError as e:
        ok = False
        print(f"\n❌ ASSERTION FAILED: {e}")
    except Exception as e:
        ok = False
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
    finally:
        await cleanup(db)
        print("(test docs cleaned up)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
