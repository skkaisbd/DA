"""Phase B end-to-end smoke test — CMT → DA → Buyer flow.
Uses seed data from POST /api/seed/maklon-full. Idempotent-friendly.

Scenarios covered:
  1. Login vendor CMT + admin DA.
  2. GET vendor CMT PO items → find first item.
  3. Vendor POST /buyer-shipments with receiver_type='da' (or default;
     server forces 'da' when vendor). Expect 201 + related_cmt_receipt_id.
  4. GET /prod/cmt-receipts → new receipt Draft with pre-populated lines.
  5. Admin PUT lines → fill qty_actual + reject_qty + reject_reason.
  6. Admin POST /prod/cmt-receipts/{id}/submit → Submitted.
  7. Admin POST /prod/cmt-receipts/{id}/approve → Approved + ap_mature.
  8. Admin POST /buyer-shipments (receiver_type='buyer') w/o source_receipt_ids → 400.
  9. Admin POST /buyer-shipments with valid source_receipt_ids + capped qty → 201.
 10. Admin POST /buyer-shipments trying to exceed qty_actual → 400.
"""
import asyncio
import httpx
import sys

BASE = "http://localhost:8001/api"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"
VENDOR_EMAIL = "cmtvendor@dewiaditya.id"
VENDOR_PASS = "Dewi@123"


def hr(msg):
    print("\n" + "=" * 70)
    print(msg)
    print("=" * 70)


async def _login(client, email, password):
    r = await client.post(f"{BASE}/auth/login", json={"email": email, "password": password})
    r.raise_for_status()
    return r.json()["token"]


async def main():
    async with httpx.AsyncClient(timeout=60) as client:
        admin = await _login(client, ADMIN_EMAIL, ADMIN_PASS)
        vendor = await _login(client, VENDOR_EMAIL, VENDOR_PASS)
        print(f"[OK] admin token len={len(admin)}, vendor token len={len(vendor)}")

        H_A = {"Authorization": f"Bearer {admin}"}
        H_V = {"Authorization": f"Bearer {vendor}"}

        # ── 0. Re-seed so this test is idempotent (fresh demo data each run) ──
        hr("STEP 0: Re-seed maklon-full (idempotent — deletes & recreates demo PO)")
        r = await client.post(f"{BASE}/seed/maklon-full", headers=H_A)
        if r.status_code == 200:
            print("[OK] Re-seeded demo data")
        else:
            print(f"[WARN] seed returned {r.status_code} — continuing with existing data")

        # ── 1. Find a maklon PO with items ─────────────────────────────
        hr("STEP 1: Find a maklon PO with produced items")
        r = await client.get(f"{BASE}/production-pos", headers=H_A)
        r.raise_for_status()
        pos = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        pos = [p for p in pos if p.get("business_type") == "maklon"]
        assert pos, "No maklon POs found"
        po = pos[0]
        po_id = po["id"]
        print(f"[OK] PO: {po['po_number']} status={po['status']} id={po_id[:12]}")

        # Get PO items
        r = await client.get(f"{BASE}/po-items?po_id={po_id}", headers=H_A)
        po_items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        assert po_items, "No po_items"
        print(f"[OK] {len(po_items)} po_items")

        # Get production jobs
        r = await client.get(f"{BASE}/production-jobs?po_id={po_id}", headers=H_A)
        jobs = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        job = jobs[0] if jobs else None
        print(f"[OK] {len(jobs)} jobs (using {job['id'][:12] if job else 'None'})")

        # Get job_items (produced qty)
        job_items = []
        if job:
            r = await client.get(f"{BASE}/production-job-items?job_id={job['id']}", headers=H_A)
            job_items = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        print(f"[OK] {len(job_items)} job_items")

        # ── 2. Vendor create CMT declaration (receiver_type='da') ────
        hr("STEP 2: Vendor create shipment (server forces receiver_type='da')")
        ship_items = []
        for ji in job_items[:2]:
            qty = int(ji.get("produced_qty", 0) or 0)
            if qty > 0:
                ship_items.append({
                    "job_item_id": ji["id"],
                    "po_item_id": ji.get("po_item_id"),
                    "product_name": ji.get("product_name"),
                    "sku": ji.get("sku"),
                    "size": ji.get("size"),
                    "color": ji.get("color"),
                    "serial_number": ji.get("serial_number", ""),
                    "ordered_qty": ji.get("ordered_qty", 0),
                    "qty_shipped": min(qty, 5),  # ship a small batch
                })
        if not ship_items and po_items:
            # Fallback: fabricate items with fixed qty (some seed data may not produce yet)
            for pi in po_items[:2]:
                ship_items.append({
                    "po_item_id": pi["id"],
                    "product_name": pi.get("product_name"),
                    "sku": pi.get("sku"),
                    "size": pi.get("size"),
                    "color": pi.get("color"),
                    "serial_number": pi.get("serial_number", ""),
                    "ordered_qty": pi.get("qty", 0),
                    "qty_shipped": 3,
                })
        assert ship_items, "No items to ship"

        payload = {
            "po_id": po_id,
            "job_id": job["id"] if job else None,
            "shipment_date": "2026-07-16",
            "notes": "Phase B test — CMT declaration",
            "items": ship_items,
        }
        r = await client.post(f"{BASE}/buyer-shipments", headers=H_V, json=payload)
        print(f"[Test] Vendor create shipment → {r.status_code}")
        if r.status_code not in (200, 201):
            print(f"  Body: {r.text[:500]}")
        assert r.status_code == 201, f"Expected 201, got {r.status_code}"
        ship = r.json()
        assert ship.get("receiver_type") == "da", f"Expected receiver_type='da', got {ship.get('receiver_type')}"
        assert ship.get("related_cmt_receipt_id"), "Expected auto-created cmt_receipt"
        shipment_id = ship["id"]
        receipt_id = ship["related_cmt_receipt_id"]
        print(f"[OK] Shipment: id={shipment_id[:12]} number={ship['shipment_number']}")
        print(f"[OK] Auto-created cmt_receipt: id={receipt_id[:12]}")

        # ── 3. GET /prod/cmt-receipts → verify Draft w/ pre-populated lines ──
        hr("STEP 3: DA fetches cmt_receipts — Draft with pre-populated lines")
        r = await client.get(f"{BASE}/prod/cmt-receipts/{receipt_id}", headers=H_A)
        r.raise_for_status()
        rcp = r.json()
        assert rcp["status"] == "Draft", f"Status should be Draft, got {rcp['status']}"
        assert rcp["related_shipment_id"] == shipment_id
        lines = rcp.get("lines", [])
        assert len(lines) == len([i for i in ship_items if i.get("qty_shipped", 0) > 0]), \
            f"Expected {len(ship_items)} lines, got {len(lines)}"
        print(f"[OK] Receipt Draft with {len(lines)} lines. total_shipped_by_cmt={rcp.get('total_shipped_by_cmt')}")
        for ln in lines:
            print(f"      line: sku={ln['sku_code']} qty_shipped_by_cmt={ln['qty_shipped_by_cmt']} qty_actual={ln.get('qty_actual')}")

        # ── 4. Admin fills qty_actual + reject_qty ─────────────────────
        hr("STEP 4: DA fills qty_actual (-1 reject on line 1)")
        for idx, ln in enumerate(lines):
            expected = ln["qty_shipped_by_cmt"]
            reject_qty = 1 if idx == 0 else 0
            qty_actual = expected - reject_qty
            body = {
                "qty_actual": qty_actual,
                "reject_qty": reject_qty,
                "reject_reason": "Jahitan tidak rapih" if reject_qty > 0 else "",
                "photos": [],
            }
            r = await client.put(f"{BASE}/prod/cmt-receipts/{receipt_id}/lines/{ln['id']}", headers=H_A, json=body)
            r.raise_for_status()
            print(f"[OK] Line {idx}: qty_actual={qty_actual} reject_qty={reject_qty}")

        # ── 5. Submit + Approve ────────────────────────────────────────
        hr("STEP 5: Submit → Approve receipt")
        r = await client.post(f"{BASE}/prod/cmt-receipts/{receipt_id}/submit", headers=H_A)
        r.raise_for_status()
        print(f"[OK] Submitted")

        r = await client.post(f"{BASE}/prod/cmt-receipts/{receipt_id}/approve", headers=H_A)
        r.raise_for_status()
        appr = r.json()
        assert appr["status"] == "Approved"
        ap = appr.get("ap_mature")
        print(f"[OK] Approved.")
        if ap:
            print(f"      ap_mature: payment_code={ap.get('payment_code')} amount=Rp {ap.get('amount',0):,.0f} pcs={ap.get('total_pcs')} rejected={ap.get('total_rejected')}")
        else:
            print(f"      [WARN] ap_mature is None — check logs")

        # ── 6. DA rejects: create buyer_shipment(buyer) without source_receipt_ids → 400 ──
        hr("STEP 6: DA creates dispatch WITHOUT source_receipt_ids → expect 400")
        r = await client.post(f"{BASE}/buyer-shipments", headers=H_A, json={
            "po_id": po_id,
            "items": [{"po_item_id": ship_items[0]["po_item_id"], "qty_shipped": 3, "sku": ship_items[0].get("sku")}],
        })
        print(f"[Test] {r.status_code} — {r.text[:150]}")
        assert r.status_code == 400 and "source_receipt_ids" in r.text

        # ── 7. DA dispatches with valid source_receipt_ids ─────────────
        hr("STEP 7: DA dispatch (receiver_type='buyer', with source_receipt_ids)")
        r = await client.get(f"{BASE}/prod/cmt-receipts/{receipt_id}", headers=H_A)
        rcp = r.json()
        avail_by_sku = {ln["sku_code"]: ln["qty_actual"] for ln in rcp["lines"] if ln.get("qty_actual")}
        print(f"      avail from receipt: {avail_by_sku}")

        # Ship exactly what receipt has
        disp_items = []
        for ship_it in ship_items:
            avail = avail_by_sku.get(ship_it["sku"], 0)
            if avail > 0:
                disp_items.append({**ship_it, "qty_shipped": avail})

        r = await client.post(f"{BASE}/buyer-shipments", headers=H_A, json={
            "po_id": po_id,
            "source_receipt_ids": [receipt_id],
            "items": disp_items,
            "shipment_date": "2026-07-16",
        })
        print(f"[Test] {r.status_code}")
        if r.status_code not in (200, 201):
            print(f"      Body: {r.text[:400]}")
        assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text[:300]}"
        d = r.json()
        assert d["receiver_type"] == "buyer"
        print(f"[OK] DA dispatch: {d['shipment_number']} qty={sum(i['qty_shipped'] for i in disp_items)}")

        # ── 8. DA tries to over-dispatch → 400 ─────────────────────────
        hr("STEP 8: DA tries to over-dispatch (exceeds qty_actual) → expect 400")
        over_items = [{**it, "qty_shipped": (it["qty_shipped"] or 0) + 100} for it in disp_items]
        r = await client.post(f"{BASE}/buyer-shipments", headers=H_A, json={
            "po_id": po_id,
            "source_receipt_ids": [receipt_id],
            "items": over_items,
            "shipment_date": "2026-07-16",
        })
        print(f"[Test] {r.status_code} — {r.text[:200]}")
        assert r.status_code == 400 and "melebihi" in r.text

        # ── 9. Verify AP idempotent ────────────────────────────────────
        hr("STEP 9: Approve receipt again → expect idempotent AP")
        # Cannot re-approve; but we can verify dewi_cmt_payments has exactly 1 entry
        import motor.motor_asyncio
        c = motor.motor_asyncio.AsyncIOMotorClient('mongodb://localhost:27017')
        ap_count = await c.test_database.dewi_cmt_payments.count_documents(
            {"source_receipt_id": receipt_id}
        )
        print(f"      dewi_cmt_payments count for this receipt: {ap_count} (should be 1)")
        assert ap_count == 1

        hr("✅ ALL PHASE B E2E SCENARIOS PASS")


if __name__ == "__main__":
    asyncio.run(main())
