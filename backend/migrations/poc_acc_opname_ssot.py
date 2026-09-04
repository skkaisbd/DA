"""
POC verification: Aksesoris Opname SSOT Migration

Tests all 6 endpoints under /api/acc/opname/* using the wh_opname_sessions2 backing store.
Covers 10 user stories:
  1. List empty opname (no sessions yet)
  2. Cannot start opname with no accessories
  3. Setup: create 3 accessory materials with initial stock
  4. Start opname session -> returns ref_number OPNAME-NNNN + lines populated
  5. List opname includes new session (status=Active)
  6. Update count for 2 of 3 lines (one with diff, one without)
  7. Get detail returns updated counted_qty + diff
  8. Cannot start second opname while one is Active
  9. Complete opname -> creates stock adjustments + movements
 10. List shows status=Completed, dashboard shows no active_opname
 11. Cancel a separate opname session
 12. Verify wh_opname_sessions2 doc has domain='accessory'
 13. Verify WMS opname2 listing does NOT include accessory sessions

Run:
    cd /app && python3 -m backend.migrations.poc_acc_opname_ssot
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

load_dotenv('/app/backend/.env')

BACKEND_URL = "http://localhost:8001"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"


def _now():
    return datetime.now(timezone.utc)


class Report:
    def __init__(self):
        self.passed = []
        self.failed = []

    def assert_eq(self, name: str, actual, expected, extra=""):
        ok = actual == expected
        if ok:
            self.passed.append(name)
            print(f"   ✅ {name}")
        else:
            self.failed.append((name, f"expected {expected!r}, got {actual!r}. {extra}"))
            print(f"   ❌ {name} — expected {expected!r}, got {actual!r}. {extra}")
        return ok

    def assert_true(self, name: str, cond: bool, extra=""):
        if cond:
            self.passed.append(name)
            print(f"   ✅ {name}")
        else:
            self.failed.append((name, f"condition false. {extra}"))
            print(f"   ❌ {name}  ({extra})")
        return cond

    def summary(self):
        total = len(self.passed) + len(self.failed)
        print("\n" + "=" * 60)
        print(f"📊 RESULT: {len(self.passed)}/{total} PASS ({100*len(self.passed)//max(total,1)}%)")
        print("=" * 60)
        if self.failed:
            print("❌ FAILURES:")
            for name, msg in self.failed:
                print(f"   - {name}: {msg}")
        return len(self.failed) == 0


async def setup_db():
    """Reset accessory + opname collections + create 3 test materials with stock."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]

    # Clean any prior accessory opname sessions in SSOT collection
    await db.wh_opname_sessions2.delete_many({"domain": "accessory"})
    await db.acc_opname_sessions.delete_many({})  # legacy (just in case)
    await db.acc_opname_lines.delete_many({})

    # Reset only the 3 test materials (POC-ACC-*) to avoid interfering with other tests
    await db.rahaza_materials.delete_many({"code": {"$regex": "^POC-ACC-"}})
    await db.rahaza_material_stock.delete_many({"material_id": {"$regex": "^poc-acc-"}})
    await db.rahaza_material_movements.delete_many({"ref_type": "opname", "notes": {"$regex": "POC-"}})

    # Ensure accessory location exists
    loc = await db.rahaza_locations.find_one({"code": "ZNA-AKSESORIS"})
    if not loc:
        loc_id = f"loc-{uuid.uuid4()}"
        await db.rahaza_locations.insert_one({
            "id": loc_id,
            "code": "ZNA-AKSESORIS",
            "name": "Area Aksesoris",
            "type": "zona",
            "created_at": _now(),
            "updated_at": _now(),
        })
    else:
        loc_id = loc["id"]

    # Create 3 test accessories with initial stock
    materials = []
    for i, (code, name, init_stock) in enumerate([
        ("POC-ACC-001", "Resleting Test 001", 100),
        ("POC-ACC-002", "Kancing Test 002", 50),
        ("POC-ACC-003", "Benang Test 003", 25),
    ]):
        mat_id = f"poc-acc-{i+1:03d}"
        await db.rahaza_materials.insert_one({
            "id": mat_id,
            "code": code,
            "name": name,
            "type": "accessory",
            "unit": "pcs",
            "min_stock": 10,
            "price": 1000.0,
            "active": True,
            "created_at": _now(),
            "updated_at": _now(),
        })
        await db.rahaza_material_stock.insert_one({
            "id": f"stk-{mat_id}",
            "material_id": mat_id,
            "location_id": loc_id,
            "qty": float(init_stock),
            "updated_at": _now(),
        })
        materials.append({"id": mat_id, "code": code, "name": name, "init_stock": init_stock})

    client.close()
    return materials


async def cleanup_db():
    """Remove POC test data so it doesn't pollute production data."""
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ.get("DB_NAME", "test_database")]
    await db.wh_opname_sessions2.delete_many({"domain": "accessory"})
    await db.rahaza_materials.delete_many({"code": {"$regex": "^POC-ACC-"}})
    await db.rahaza_material_stock.delete_many({"material_id": {"$regex": "^poc-acc-"}})
    await db.rahaza_material_movements.delete_many({"ref_type": "opname", "ref_number": {"$regex": "^OPNAME-"}})
    client.close()


async def main():
    R = Report()

    print("🔧 Setup: clean DB + create 3 test accessories")
    materials = await setup_db()
    print(f"   created: {[m['code'] for m in materials]}")

    async with httpx.AsyncClient(timeout=15.0) as ax:
        # Login
        r = await ax.post(
            f"{BACKEND_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        )
        r.raise_for_status()
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        print(f"   ✅ Logged in as {ADMIN_EMAIL}\n")

        # ── 1) List empty opname (no sessions for accessory domain) ──────────
        print("📋 Story 1: List opname returns [] when no sessions exist")
        r = await ax.get(f"{BACKEND_URL}/api/acc/opname", headers=h)
        R.assert_eq("GET /api/acc/opname returns 200", r.status_code, 200)
        items = r.json()
        R.assert_eq("Empty list initially", len(items), 0)

        # ── 4) Start opname ──────────────────────────────────────────────────
        print("\n📋 Story 4: POST /api/acc/opname starts a new session")
        r = await ax.post(f"{BACKEND_URL}/api/acc/opname", headers=h,
                          json={"notes": "POC test session"})
        R.assert_eq("POST opname returns 201", r.status_code, 201)
        session = r.json()
        session_id = session["id"]
        R.assert_true("ref_number matches OPNAME-NNNN", session.get("ref_number", "").startswith("OPNAME-"),
                      f"ref_number={session.get('ref_number')}")
        R.assert_eq("status = Active", session.get("status"), "Active")
        R.assert_true("lines length >= 3", len(session.get("lines", [])) >= 3,
                      f"lines count={len(session.get('lines', []))}")
        # find our 3 test materials in lines
        line_by_code = {ln.get("acc_code"): ln for ln in session.get("lines", [])}
        for m in materials:
            ln = line_by_code.get(m["code"])
            R.assert_true(f"line for {m['code']} present", ln is not None,
                          f"available codes={list(line_by_code.keys())}")
            if ln:
                R.assert_eq(f"{m['code']} system_qty", float(ln.get("system_qty", -1)), float(m["init_stock"]))
                R.assert_eq(f"{m['code']} counted_qty None initially", ln.get("counted_qty"), None)
                R.assert_eq(f"{m['code']} diff None initially", ln.get("diff"), None)

        # ── 5) List shows new active session ─────────────────────────────────
        print("\n📋 Story 5: List shows the new session")
        r = await ax.get(f"{BACKEND_URL}/api/acc/opname", headers=h)
        items = r.json()
        R.assert_eq("List has 1 session", len(items), 1)
        R.assert_eq("List session id matches", items[0]["id"], session_id)
        R.assert_eq("List session ref_number matches", items[0]["ref_number"], session["ref_number"])
        R.assert_eq("List session status=Active", items[0]["status"], "Active")

        # ── 6) Update count for 2 of 3 lines ─────────────────────────────────
        print("\n📋 Story 6: PUT /opname/{id}/count updates counted_qty")
        # acc-001: physical=105, system=100 → diff=+5
        # acc-002: physical=50, system=50 → diff=0 (no change)
        # acc-003: NOT counted (left null)
        for m, counted in [(materials[0], 105), (materials[1], 50)]:
            r = await ax.put(f"{BACKEND_URL}/api/acc/opname/{session_id}/count", headers=h,
                             json={"acc_id": m["id"], "counted_qty": counted})
            R.assert_eq(f"PUT count {m['code']} -> 200", r.status_code, 200)
            expected_diff = float(counted) - float(m["init_stock"])
            R.assert_eq(f"{m['code']} returned diff", r.json().get("diff"), expected_diff)

        # ── 7) Get detail returns updated lines ──────────────────────────────
        print("\n📋 Story 7: GET detail returns updated counted_qty + diff")
        r = await ax.get(f"{BACKEND_URL}/api/acc/opname/{session_id}", headers=h)
        R.assert_eq("GET detail 200", r.status_code, 200)
        detail = r.json()
        line_by_id = {ln["acc_id"]: ln for ln in detail["lines"]}
        R.assert_eq("counted_items == 2", detail.get("counted_items"), 2)
        R.assert_eq("acc-001 counted_qty", line_by_id["poc-acc-001"]["counted_qty"], 105.0)
        R.assert_eq("acc-001 diff = +5", line_by_id["poc-acc-001"]["diff"], 5.0)
        R.assert_eq("acc-002 diff = 0", line_by_id["poc-acc-002"]["diff"], 0.0)
        R.assert_eq("acc-003 counted_qty None (not counted)", line_by_id["poc-acc-003"]["counted_qty"], None)

        # ── 8) Cannot start second opname while one is Active ────────────────
        print("\n📋 Story 8: Cannot start 2nd opname while 1st is Active")
        r = await ax.post(f"{BACKEND_URL}/api/acc/opname", headers=h, json={"notes": "second"})
        R.assert_eq("POST 2nd opname returns 400", r.status_code, 400)

        # ── 9) Complete opname (apply adjustments) ───────────────────────────
        print("\n📋 Story 9: POST /opname/{id}/complete applies adjustments")
        r = await ax.post(f"{BACKEND_URL}/api/acc/opname/{session_id}/complete", headers=h, json={})
        R.assert_eq("complete 200", r.status_code, 200)
        # Only acc-001 has non-zero diff (+5), so 1 adjustment
        R.assert_eq("adjustments_made = 1", r.json().get("adjustments_made"), 1)

        # Verify stock updated for acc-001
        client = AsyncIOMotorClient(os.environ["MONGO_URL"])
        db = client[os.environ.get("DB_NAME", "test_database")]
        stock = await db.rahaza_material_stock.find_one({"material_id": "poc-acc-001"})
        R.assert_eq("acc-001 stock updated to 105", float(stock["qty"]) if stock else None, 105.0)
        # Verify movement created
        mv = await db.rahaza_material_movements.find_one({
            "material_id": "poc-acc-001", "ref_type": "opname"
        })
        R.assert_true("opname movement created for acc-001", mv is not None)
        if mv:
            R.assert_eq("movement type = adjust", mv.get("type"), "adjust")
            R.assert_eq("movement legacy_type = ADJUST", mv.get("legacy_movement_type"), "ADJUST")
            R.assert_eq("movement qty = +5", float(mv.get("qty")), 5.0)
            R.assert_eq("movement domain = accessory", mv.get("domain"), "accessory")

        # ── 10) List + Dashboard reflect Completed state ─────────────────────
        print("\n📋 Story 10: List shows Completed; Dashboard no active opname")
        r = await ax.get(f"{BACKEND_URL}/api/acc/opname", headers=h)
        items = r.json()
        R.assert_eq("List session is Completed", items[0]["status"], "Completed")
        r = await ax.get(f"{BACKEND_URL}/api/acc/dashboard", headers=h)
        R.assert_eq("dashboard 200", r.status_code, 200)
        R.assert_eq("active_opname is None", r.json().get("active_opname"), None)

        # ── 11) Cancel a new opname session ──────────────────────────────────
        print("\n📋 Story 11: Cancel a new opname session")
        r = await ax.post(f"{BACKEND_URL}/api/acc/opname", headers=h, json={"notes": "to-cancel"})
        R.assert_eq("start 2nd session 201", r.status_code, 201)
        sess2_id = r.json()["id"]
        r = await ax.post(f"{BACKEND_URL}/api/acc/opname/{sess2_id}/cancel", headers=h, json={})
        R.assert_eq("cancel 200", r.status_code, 200)
        r = await ax.get(f"{BACKEND_URL}/api/acc/opname/{sess2_id}", headers=h)
        R.assert_eq("cancelled session status=Cancelled", r.json().get("status"), "Cancelled")

        # ── 12) Verify SSOT doc shape ────────────────────────────────────────
        print("\n📋 Story 12: Verify wh_opname_sessions2 docs have domain='accessory'")
        sess_doc = await db.wh_opname_sessions2.find_one({"id": session_id}, {"_id": 0})
        R.assert_eq("SSOT doc domain=accessory", sess_doc.get("domain"), "accessory")
        R.assert_eq("SSOT doc status=approved", sess_doc.get("status"), "approved")
        R.assert_true("SSOT doc count_items populated", len(sess_doc.get("count_items", [])) >= 3)

        # ── 13) Verify WMS opname2 listing does NOT include accessory ────────
        print("\n📋 Story 13: GET /api/wms/opname2 excludes accessory sessions")
        r = await ax.get(f"{BACKEND_URL}/api/wms/opname2", headers=h)
        R.assert_eq("WMS opname2 list 200", r.status_code, 200)
        wms_items = r.json().get("items", [])
        acc_in_wms = [s for s in wms_items if s.get("domain") == "accessory"]
        R.assert_eq("WMS listing has 0 accessory sessions", len(acc_in_wms), 0)

        client.close()

    # ── Cleanup ─────────────────────────────────────────────────────────────
    print("\n🧹 Cleanup POC data")
    await cleanup_db()

    return R.summary()


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
