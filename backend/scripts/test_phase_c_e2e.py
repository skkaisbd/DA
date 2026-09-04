"""Phase C end-to-end test — PO Closure Rules + K5 cleanup.

Self-seeding (idempotent). Creates fresh maklon POs (unique po_number per run)
and drives the real CMT->DA->Buyer chain, then exercises closure.

Scenarios (GUIDELINE_CMT_FLOW.md §12.3):
  7.  Auto-close 100%  -> PUT qty_received making Σ>=ordered => status 'Completed'.
  8.  Close short       -> POST /close-short {deadline_expired} => 'Closed Short',
                           qty_short correct, draft-AR shrunk to qty_received.
  8b. Credit note       -> AR issued (sent) then close-short => credit note draft.
  9.  K5 cleanup        -> defect POST 410, maklon QC POST 410, progress gate
                           rejects Σ>available WITHOUT mentioning defect.
"""
import asyncio
import time
import httpx
import motor.motor_asyncio

BASE = "http://localhost:8001/api"
ADMIN = ("admin@garment.com", "Admin@123")
VENDOR = ("cmtvendor@dewiaditya.id", "Dewi@123")
STAMP = int(time.time())


def hr(m):
    print("\n" + "=" * 70 + f"\n{m}\n" + "=" * 70)


async def login(c, email, pw):
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


async def create_maklon_po(c, H, qty, rate, tag):
    po_number = f"PO-MK-C{STAMP}-{tag}"
    body = {
        "po_number": po_number, "business_type": "maklon", "status": "Confirmed",
        "customer_name": "PT Phase C Buyer",
        "items": [{
            "product_name": f"Kaos Phase C {tag}", "sku": f"PC-{tag}-M", "size": "M",
            "color": "Hitam", "qty": qty, "cmt_price_snapshot": rate,
        }],
    }
    r = await c.post(f"{BASE}/production-pos", headers=H, json=body)
    assert r.status_code == 201, f"create PO failed {r.status_code}: {r.text[:300]}"
    po = r.json()
    return po, po["items"][0]


async def declare_receive_dispatch(c, H_V, H_A, po, item, ship_qty, receive_qty):
    """Full chain: vendor declare -> DA approve receipt -> DA dispatch to buyer
    -> set qty_received. Returns (buyer_shipment_id, [item_ids])."""
    po_id = po["id"]; poi = item["id"]; sku = item["sku"]
    # 1. Vendor declares to DA
    r = await c.post(f"{BASE}/buyer-shipments", headers=H_V, json={
        "po_id": po_id,
        "items": [{"po_item_id": poi, "sku": sku, "product_name": item["product_name"],
                   "size": item.get("size"), "color": item.get("color"),
                   "qty_shipped": ship_qty}],
    })
    assert r.status_code == 201, f"vendor declare failed {r.status_code}: {r.text[:300]}"
    receipt_id = r.json()["related_cmt_receipt_id"]
    assert receipt_id, "no cmt_receipt auto-created"
    # 2. DA fills line qty_actual=ship_qty reject=0
    r = await c.get(f"{BASE}/prod/cmt-receipts/{receipt_id}", headers=H_A)
    r.raise_for_status()
    for ln in r.json()["lines"]:
        r2 = await c.put(f"{BASE}/prod/cmt-receipts/{receipt_id}/lines/{ln['id']}", headers=H_A,
                         json={"qty_actual": ln["qty_shipped_by_cmt"], "reject_qty": 0,
                               "reject_reason": "", "photos": []})
        r2.raise_for_status()
    # 3. Submit + approve
    (await c.post(f"{BASE}/prod/cmt-receipts/{receipt_id}/submit", headers=H_A)).raise_for_status()
    (await c.post(f"{BASE}/prod/cmt-receipts/{receipt_id}/approve", headers=H_A)).raise_for_status()
    # 4. DA dispatch to buyer
    r = await c.post(f"{BASE}/buyer-shipments", headers=H_A, json={
        "po_id": po_id, "source_receipt_ids": [receipt_id],
        "items": [{"po_item_id": poi, "sku": sku, "qty_shipped": ship_qty}],
    })
    assert r.status_code == 201, f"DA dispatch failed {r.status_code}: {r.text[:300]}"
    bsid = r.json()["id"]
    # 5. Get item ids + set qty_received
    r = await c.get(f"{BASE}/buyer-shipments/{bsid}", headers=H_A)
    r.raise_for_status()
    items = r.json()["items"]
    last = None
    remaining = receive_qty
    for it in items:
        take = min(remaining, it.get("qty_shipped", 0))
        r2 = await c.put(f"{BASE}/buyer-shipment-items/{it['id']}/received", headers=H_A,
                         json={"qty_received": take})
        r2.raise_for_status()
        last = r2.json()
        remaining -= take
    return bsid, last


async def transition(c, H_A, po_id, statuses):
    for s in statuses:
        r = await c.post(f"{BASE}/production-pos/{po_id}/status", headers=H_A, json={"status": s})
        assert r.status_code == 200, f"transition -> {s} failed {r.status_code}: {r.text[:200]}"


async def main():
    async with httpx.AsyncClient(timeout=90) as c:
        admin = await login(c, *ADMIN)
        vendor = await login(c, *VENDOR)
        H_A = {"Authorization": f"Bearer {admin}"}
        H_V = {"Authorization": f"Bearer {vendor}"}
        # seed (idempotent) for K5 progress test data
        await c.post(f"{BASE}/seed/maklon-full", headers=H_A)
        db = motor.motor_asyncio.AsyncIOMotorClient("mongodb://localhost:27017").test_database

        # ── Scenario 7: auto-close 100% ─────────────────────────────────────
        hr("SCENARIO 7: Auto-close 100%")
        po, item = await create_maklon_po(c, H_A, qty=6, rate=15000, tag="S7")
        _, recv_resp = await declare_receive_dispatch(c, H_V, H_A, po, item, ship_qty=6, receive_qty=6)
        ac = (recv_resp or {}).get("po_auto_close") or {}
        print(f"  po_auto_close={ac}")
        r = await c.get(f"{BASE}/production-pos/{po['id']}", headers=H_A)
        st = r.json().get("status"); cr = r.json().get("closed_reason")
        print(f"  PO status={st} closed_reason={cr}")
        assert st == "Completed", f"expected Completed got {st}"
        assert cr == "full_fulfillment", f"expected full_fulfillment got {cr}"
        print("  [OK] Auto-closed to Completed on full fulfillment")

        # ── Scenario 8: close short (draft AR -> shrink to received) ────────
        hr("SCENARIO 8: Close short (deadline_expired), AR draft")
        po, item = await create_maklon_po(c, H_A, qty=10, rate=12000, tag="S8")
        await declare_receive_dispatch(c, H_V, H_A, po, item, ship_qty=8, receive_qty=8)
        await transition(c, H_A, po["id"], ["Distributed", "In Production"])
        r = await c.post(f"{BASE}/production-pos/{po['id']}/close-short", headers=H_A,
                         json={"closed_reason": "deadline_expired", "notes": "buyer batalkan sisa"})
        assert r.status_code == 200, f"close-short failed {r.status_code}: {r.text[:300]}"
        d = r.json()
        print(f"  status={d['status']} qty_short={d['qty_short']} pct={d['qty_short_pct']} finance={d['finance']}")
        assert d["status"] == "Closed Short"
        assert d["qty_short"] == 2, f"expected qty_short=2 got {d['qty_short']}"
        # invariant: short + received == ordered
        assert d["qty_short"] + d["qty_received"] == d["qty_ordered"]
        assert d["finance"].get("credit_note_created") is False, "draft AR should NOT create credit note"
        print("  [OK] Closed Short, qty_short=2, invariant holds, AR draft path")

        # ── Scenario 8b: close short with AR issued -> credit note draft ────
        hr("SCENARIO 8b: Close short with AR ISSUED -> credit note draft")
        po, item = await create_maklon_po(c, H_A, qty=10, rate=20000, tag="S8B")
        await declare_receive_dispatch(c, H_V, H_A, po, item, ship_qty=7, receive_qty=7)
        # simulate AR already issued
        mirror = await db.dewi_maklon_pos.find_one({"id": po["id"]})
        assert mirror and mirror.get("ar_invoice_id"), "AR mirror/invoice should exist for confirmed maklon PO"
        await db.rahaza_ar_invoices.update_one({"id": mirror["ar_invoice_id"]}, {"$set": {"status": "sent"}})
        await transition(c, H_A, po["id"], ["Distributed", "In Production"])
        r = await c.post(f"{BASE}/production-pos/{po['id']}/close-short", headers=H_A,
                         json={"closed_reason": "mutual_agreement"})
        assert r.status_code == 200, f"close-short 8b failed {r.status_code}: {r.text[:300]}"
        fin = r.json()["finance"]
        print(f"  qty_short={r.json()['qty_short']} finance={fin}")
        assert fin.get("credit_note_created") is True, f"expected credit note, got {fin}"
        assert fin.get("amount") == 3 * 20000, f"expected 60000 got {fin.get('amount')}"
        # verify listed
        r = await c.get(f"{BASE}/production-pos/{po['id']}/credit-notes", headers=H_A)
        cns = r.json()
        assert len(cns) == 1 and cns[0]["status"] == "draft"
        print(f"  [OK] Credit note draft {cns[0]['credit_note_number']} Rp {cns[0]['total_amount']:,.0f}")

        # ── Scenario 9: K5 cleanup ──────────────────────────────────────────
        hr("SCENARIO 9: K5 cleanup (410s + progress gate without defect)")
        r = await c.post(f"{BASE}/material-defect-reports", headers=H_A,
                         json={"job_item_id": "x", "defect_qty": 1})
        print(f"  POST /material-defect-reports -> {r.status_code}")
        assert r.status_code == 410, f"expected 410 got {r.status_code}"

        r = await c.post(f"{BASE}/dewi/maklon/qc", headers=H_A,
                         json={"order_id": "x", "stage": "final", "qty_inspected": 1})
        print(f"  POST /dewi/maklon/qc -> {r.status_code}")
        assert r.status_code == 410, f"expected 410 got {r.status_code}"

        # progress gate — seed job JOB-MK-DEMO-2 ji1: available_qty=100, produced=80
        r = await c.get(f"{BASE}/production-job-items?job_id=po-mk-demo-2-job1", headers=H_A)
        jis = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
        ji = next((j for j in jis if int(j.get("available_qty", 0)) >= int(j.get("produced_qty", 0))), jis[0])
        avail = int(ji["available_qty"]); prod = int(ji.get("produced_qty", 0))
        over = avail - prod + 5   # exceeds capacity
        r = await c.post(f"{BASE}/production-progress", headers=H_A,
                         json={"job_item_id": ji["id"], "completed_quantity": over})
        print(f"  over-progress -> {r.status_code}: {r.text[:160]}")
        assert r.status_code == 400
        low = r.text.lower()
        assert "defect" not in low and "cacat" not in low, "gate message must NOT mention defect"
        # valid small progress within capacity
        room = max(1, avail - prod - 1)
        r = await c.post(f"{BASE}/production-progress", headers=H_A,
                         json={"job_item_id": ji["id"], "completed_quantity": min(room, 3)})
        print(f"  within-capacity progress -> {r.status_code}")
        assert r.status_code in (200, 201)
        print("  [OK] K5: defect/QC deprecated (410); progress gate = Σ≤available (no defect mention)")

        hr("✅ ALL PHASE C E2E SCENARIOS PASS")


if __name__ == "__main__":
    asyncio.run(main())
