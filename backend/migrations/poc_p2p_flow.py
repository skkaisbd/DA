"""
POC: P2P Flow Completion — Create GR from PO (P1.C)

Membuktikan end-to-end Procure-to-Pay flow:
  1. Setup: create material(s) + create PO with 3 items
  2. Submit + Approve PO
  3. POST /api/rahaza/purchase-orders/{po_id}/create-gr → expect GR draft
     dengan items dari PO (expected_qty = qty_ordered untuk awal)
  4. Update GR: input received_qty = setengah qty utk semua item, status=received
  5. Verify: PO status = 'partially_received', qty_received per line updated
  6. Verify: rahaza_material_stock bertambah sesuai net qty
  7. Create GR kedua dari PO → expected_qty = sisanya
  8. Coba over-receive (received_qty > remaining) → expect HTTP 400
  9. Update GR kedua normal → status=received
  10. Verify: PO status = 'fully_received'
  11. Coba create GR ketiga dari fully_received PO → expect HTTP 400

Usage:
    cd /app/backend && python migrations/poc_p2p_flow.py
"""
import asyncio
import os
import sys
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import httpx  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE = "http://localhost:8001"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
RUN = uuid.uuid4().hex[:6].upper()


async def login(client) -> str:
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()["token"]


async def main() -> int:
    print(f"=== POC P2P Flow (Create GR from PO) — run={RUN} ===")
    results: list = []

    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "garment_erp")]

    async with httpx.AsyncClient() as client:
        token = await login(client)
        H = {"Authorization": f"Bearer {token}"}
        print("[OK] Login")

        # Cleanup prior POC residue
        await db.rahaza_purchase_orders.delete_many({"po_number": {"$regex": f"_POC{RUN}"}})
        await db.warehouse_receiving.delete_many({"notes": {"$regex": f"POC{RUN}"}})

        # ───── Setup materials ─────
        mat_ids = []
        for i, (name, code, mtype, unit, min_st) in enumerate([
            (f"POC{RUN} Yarn Cotton 30s", f"POC{RUN}-Y01", "yarn", "kg", 0),
            (f"POC{RUN} Button Plastic 12mm", f"POC{RUN}-A01", "accessory", "pcs", 0),
            (f"POC{RUN} Thread Polyester", f"POC{RUN}-A02", "accessory", "rol", 0),
        ]):
            mid = str(uuid.uuid4())
            await db.rahaza_materials.insert_one({
                "id": mid, "code": code, "name": name, "type": mtype, "unit": unit,
                "active": True, "min_stock": min_st, "category": "POC",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
            mat_ids.append(mid)
        print("[OK] Seeded 3 materials")

        # ───── US1: Create PO with 3 items ─────
        po_payload = {
            "vendor_name": f"POC Vendor {RUN}",
            "vendor_contact": "0812-POC",
            "po_date": "2026-05-22",
            "expected_delivery_date": "2026-06-01",
            "notes": f"POC{RUN} test PO",
            "items": [
                {"material_id": mat_ids[0], "qty_ordered": 100, "unit_cost": 50000},
                {"material_id": mat_ids[1], "qty_ordered": 500, "unit_cost": 1000},
                {"material_id": mat_ids[2], "qty_ordered": 20, "unit_cost": 25000},
            ],
        }
        r = await client.post(f"{BASE}/api/rahaza/purchase-orders", headers=H, json=po_payload, timeout=20.0)
        assert r.status_code in (200, 201), f"US1 FAILED: {r.status_code} {r.text}"
        po = r.json()
        # Tag PO number for cleanup
        await db.rahaza_purchase_orders.update_one(
            {"id": po["id"]},
            {"$set": {"po_number": po["po_number"] + f"_POC{RUN}"}},
        )
        po["po_number"] = po["po_number"] + f"_POC{RUN}"
        po_id = po["id"]
        assert len(po["items"]) == 3
        assert po["status"] == "draft"
        results.append(("US1: Create PO with 3 items", True, f"po={po['po_number']}, status={po['status']}"))
        print(f"[PASS] US1: PO created (id={po_id}, po_number={po['po_number']})")

        # ───── US2: Submit + Approve PO ─────
        r = await client.post(f"{BASE}/api/rahaza/purchase-orders/{po_id}/submit", headers=H, timeout=10.0)
        assert r.status_code == 200, f"submit FAILED: {r.text}"
        r = await client.post(f"{BASE}/api/rahaza/purchase-orders/{po_id}/approve", headers=H, timeout=10.0)
        assert r.status_code == 200, f"approve FAILED: {r.text}"
        po2 = r.json()
        assert po2["status"] == "approved"
        results.append(("US2: Submit + Approve PO", True, f"status={po2['status']}"))
        print("[PASS] US2: PO Approved")

        # ───── US3: GET /purchase-orders/{po_id}/remaining ─────
        r = await client.get(f"{BASE}/api/rahaza/purchase-orders/{po_id}/remaining", headers=H, timeout=10.0)
        assert r.status_code == 200, f"remaining FAILED: {r.text}"
        rem = r.json()
        assert rem["total_remaining"] == 620.0  # 100 + 500 + 20
        assert len(rem["items_remaining"]) == 3
        for ir in rem["items_remaining"]:
            assert ir["qty_remaining"] == ir["qty_ordered"]
        results.append(("US3: GET remaining endpoint", True, f"total_remaining={rem['total_remaining']}"))
        print("[PASS] US3: PO remaining = 620 across 3 items")

        # ───── US4: POST /create-gr → expect draft GR ─────
        r = await client.post(
            f"{BASE}/api/rahaza/purchase-orders/{po_id}/create-gr",
            headers=H,
            json={"notes": f"POC{RUN} GR#1 from PO"},
            timeout=15.0,
        )
        assert r.status_code in (200, 201), f"create-gr FAILED: {r.status_code} {r.text}"
        gr1 = r.json()
        assert gr1["status"] == "draft"
        assert gr1["po_id"] == po_id
        assert gr1["po_number"] == po["po_number"]
        assert gr1["enforce_po_qty"] is True
        assert len(gr1["items"]) == 3
        for it in gr1["items"]:
            assert it["expected_qty"] > 0
            assert it["received_qty"] == 0
        gr1_id = gr1["id"]
        results.append(("US4: Create GR from PO", True, f"gr={gr1['receipt_number']}, items=3, status=draft"))
        print(f"[PASS] US4: GR draft created ({gr1['receipt_number']})")

        # ───── US5: Receive HALF of each line, set status=received ─────
        gr1["items"][0]["received_qty"] = 50   # 100 -> 50
        gr1["items"][1]["received_qty"] = 250  # 500 -> 250
        gr1["items"][2]["received_qty"] = 10   # 20  -> 10
        r = await client.put(
            f"{BASE}/api/wms/legacy/receiving/{gr1_id}",
            headers=H,
            json={"status": "received", "items": gr1["items"]},
            timeout=15.0,
        )
        assert r.status_code == 200, f"GR1 receive FAILED: {r.status_code} {r.text}"
        gr1_updated = r.json()
        assert gr1_updated["status"] == "received"
        results.append(("US5: Receive half (partial)", True, "GR1 status=received"))
        print("[PASS] US5: GR1 received partially")

        # ───── US6: Verify PO partially_received + qty_received updated ─────
        r = await client.get(f"{BASE}/api/rahaza/purchase-orders/{po_id}", headers=H, timeout=10.0)
        po3 = r.json()
        assert po3["status"] == "partially_received", f"Expected partially_received, got {po3['status']}"
        po3_recv = {it["material_id"]: it["qty_received"] for it in po3["items"]}
        assert po3_recv[mat_ids[0]] == 50
        assert po3_recv[mat_ids[1]] == 250
        assert po3_recv[mat_ids[2]] == 10
        results.append(("US6: PO status partially_received", True, "qty_received synced"))
        print("[PASS] US6: PO status=partially_received, qty_received synced")

        # ───── US7: Verify rahaza_material_stock incremented ─────
        for mid, expected_qty in zip(mat_ids, [50, 250, 10]):
            stock_rows = await db.rahaza_material_stock.find({"material_id": mid}, {"_id": 0}).to_list(10)
            total = sum(float(s.get("qty") or 0) for s in stock_rows)
            assert total >= expected_qty, f"Stock mismatch for {mid}: total={total}, expected>={expected_qty}"
        results.append(("US7: rahaza_material_stock synced", True, "all 3 materials reflect GR1 net qty"))
        print("[PASS] US7: rahaza_material_stock reflects GR1")

        # ───── US8: Create GR2 from PO (remaining) → expected_qty = sisanya ─────
        r = await client.post(
            f"{BASE}/api/rahaza/purchase-orders/{po_id}/create-gr",
            headers=H,
            json={"notes": f"POC{RUN} GR#2 from PO"},
            timeout=15.0,
        )
        assert r.status_code in (200, 201), f"create-gr#2 FAILED: {r.text}"
        gr2 = r.json()
        assert len(gr2["items"]) == 3
        # GR2 expected = qty_remaining = original - half
        exp_map = {it["material_id"]: it["expected_qty"] for it in gr2["items"]}
        assert exp_map[mat_ids[0]] == 50   # 100-50
        assert exp_map[mat_ids[1]] == 250  # 500-250
        assert exp_map[mat_ids[2]] == 10   # 20-10
        gr2_id = gr2["id"]
        results.append(("US8: Create 2nd GR (remaining qty only)", True, "expected_qty = remaining"))
        print("[PASS] US8: GR2 expected_qty correctly = remaining qty")

        # ───── US9: Try OVER-receive (received_qty > expected) → expect 400 ─────
        gr2_over = json.loads(json.dumps(gr2))  # deep copy
        gr2_over["items"][0]["received_qty"] = 999  # Way more than allowed (50)
        gr2_over["items"][1]["received_qty"] = 250  # OK
        gr2_over["items"][2]["received_qty"] = 10   # OK
        r = await client.put(
            f"{BASE}/api/wms/legacy/receiving/{gr2_id}",
            headers=H,
            json={"status": "received", "items": gr2_over["items"]},
            timeout=15.0,
        )
        assert r.status_code == 400, f"Over-receive should fail with 400, got {r.status_code} {r.text}"
        assert "Over-receive" in r.text or "melebihi" in r.text.lower() or "over" in r.text.lower()
        results.append(("US9: Over-receive rejected (HTTP 400)", True, "anti over-receive validation works"))
        print("[PASS] US9: Over-receive correctly rejected")

        # Verify GR2 still draft (failed update didn't persist status)
        r = await client.get(f"{BASE}/api/wms/legacy/receiving/{gr2_id}", headers=H, timeout=10.0)
        gr2_check = r.json()
        # NOTE: items may have been updated even though status=received failed; depends on order of operations
        # We don't strictly require gr2 to still be draft here; just that status didn't transition
        assert gr2_check["status"] != "received", f"GR2 should not be received after over-receive attempt: status={gr2_check['status']}"

        # ───── US10: Normal receive of remaining → PO fully_received ─────
        gr2["items"][0]["received_qty"] = 50
        gr2["items"][1]["received_qty"] = 250
        gr2["items"][2]["received_qty"] = 10
        r = await client.put(
            f"{BASE}/api/wms/legacy/receiving/{gr2_id}",
            headers=H,
            json={"status": "received", "items": gr2["items"]},
            timeout=15.0,
        )
        assert r.status_code == 200, f"GR2 receive FAILED: {r.text}"
        results.append(("US10: Normal receive completes PO", True, "GR2 received"))
        print("[PASS] US10: GR2 received normally")

        # ───── US11: Verify PO fully_received ─────
        r = await client.get(f"{BASE}/api/rahaza/purchase-orders/{po_id}", headers=H, timeout=10.0)
        po4 = r.json()
        assert po4["status"] == "fully_received", f"Expected fully_received, got {po4['status']}"
        results.append(("US11: PO status=fully_received", True, "after total receive completes"))
        print("[PASS] US11: PO status=fully_received")

        # ───── US12: Try create GR from fully_received PO → 400 ─────
        r = await client.post(
            f"{BASE}/api/rahaza/purchase-orders/{po_id}/create-gr",
            headers=H,
            json={"notes": f"POC{RUN} GR#3 should fail"},
            timeout=10.0,
        )
        assert r.status_code == 400, f"Should fail for fully_received PO, got {r.status_code}"
        assert "fully_received" in r.text.lower() or "approved" in r.text.lower() or "tersisa" in r.text.lower() or "sudah" in r.text.lower()
        results.append(("US12: Cannot create GR from fully_received PO", True, "HTTP 400"))
        print("[PASS] US12: Cannot create GR from fully_received PO")

        # ───── US13: GET /grs → audit trail ─────
        r = await client.get(f"{BASE}/api/rahaza/purchase-orders/{po_id}/grs", headers=H, timeout=10.0)
        assert r.status_code == 200
        grs = r.json()
        assert len(grs) == 2
        for grs_row in grs:
            assert grs_row["status"] in ("received", "draft")
        results.append(("US13: GET /grs audit trail", True, f"found {len(grs)} GRs"))
        print("[PASS] US13: PO/grs audit trail returns 2 GRs")

    # Cleanup
    await db.warehouse_receiving.delete_many({"po_id": po_id})
    await db.rahaza_purchase_orders.delete_one({"id": po_id})
    for mid in mat_ids:
        await db.rahaza_materials.delete_one({"id": mid})
        await db.rahaza_material_stock.delete_many({"material_id": mid})
        await db.rahaza_material_movements.delete_many({"material_id": mid})
    print("\n[CLEANUP] Removed POC residue")

    print("\n=== POC RESULTS ===")
    for name, ok, info in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} ({info})")

    if all(ok for _, ok, _ in results):
        print("\nPOC P2P FLOW: SUCCESS")
        return 0
    print("\nPOC P2P FLOW: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
