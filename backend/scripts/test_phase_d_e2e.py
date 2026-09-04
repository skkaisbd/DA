"""Phase D end-to-end test — Consolidated Buyer Shipment (multi-PO surat jalan).

Proves that ONE DA->buyer surat jalan can carry items from MULTIPLE POs of the
same buyer while each PO's fulfillment/auto-close still works INDEPENDENTLY.

Self-seeding (idempotent) — creates fresh maklon POs with unique po_number.

Scenarios (PHASE_D_CONSOLIDATED_BUYER_SHIPMENT.md):
  D1. Consolidated dispatch across 3 POs (same buyer) -> 1 SJ, po_ids has 3,
      consolidated=true, shipment_number auto-generated (configured format).
  D2. Per-PO fulfillment correct within the consolidated SJ.
  D3. Independent auto-close: PO fully received -> 'Completed'; partially received
      PO stays open even though it's in the SAME surat jalan.
  D4. Single-buyer guard: consolidating POs of different buyers -> 400.
"""
import asyncio
import time
import httpx

BASE = "http://localhost:8001/api"
ADMIN = ("admin@garment.com", "Admin@123")
VENDOR = ("cmtvendor@dewiaditya.id", "Dewi@123")
STAMP = int(time.time())
BUYER = "PT Phase D Buyer"


def hr(m):
    print("\n" + "=" * 70 + f"\n{m}\n" + "=" * 70)


async def login(c, email, pw):
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


async def create_maklon_po(c, H, qty, rate, tag, buyer=BUYER):
    po_number = f"PO-MK-D{STAMP}-{tag}"
    body = {
        "po_number": po_number, "business_type": "maklon", "status": "Confirmed",
        "customer_name": buyer,
        "items": [{
            "product_name": f"Kaos Phase D {tag}", "sku": f"PD-{tag}-M", "size": "M",
            "color": "Hitam", "qty": qty, "cmt_price_snapshot": rate,
        }],
    }
    r = await c.post(f"{BASE}/production-pos", headers=H, json=body)
    assert r.status_code == 201, f"create PO failed {r.status_code}: {r.text[:300]}"
    po = r.json()
    return po, po["items"][0]


async def declare_and_approve_receipt(c, H_V, H_A, po, item, ship_qty):
    """Vendor declares CMT->DA, DA fills qty_actual=ship_qty, submit + approve.
    Returns the Approved cmt_receipt id."""
    po_id = po["id"]; poi = item["id"]; sku = item["sku"]
    r = await c.post(f"{BASE}/buyer-shipments", headers=H_V, json={
        "po_id": po_id,
        "items": [{"po_item_id": poi, "sku": sku, "product_name": item["product_name"],
                   "size": item.get("size"), "color": item.get("color"),
                   "qty_shipped": ship_qty}],
    })
    assert r.status_code == 201, f"vendor declare failed {r.status_code}: {r.text[:300]}"
    receipt_id = r.json()["related_cmt_receipt_id"]
    assert receipt_id, "no cmt_receipt auto-created"
    r = await c.get(f"{BASE}/prod/cmt-receipts/{receipt_id}", headers=H_A)
    r.raise_for_status()
    for ln in r.json()["lines"]:
        r2 = await c.put(f"{BASE}/prod/cmt-receipts/{receipt_id}/lines/{ln['id']}", headers=H_A,
                         json={"qty_actual": ln["qty_shipped_by_cmt"], "reject_qty": 0,
                               "reject_reason": "", "photos": []})
        r2.raise_for_status()
    (await c.post(f"{BASE}/prod/cmt-receipts/{receipt_id}/submit", headers=H_A)).raise_for_status()
    (await c.post(f"{BASE}/prod/cmt-receipts/{receipt_id}/approve", headers=H_A)).raise_for_status()
    return receipt_id


async def get_po(c, H, po_id):
    r = await c.get(f"{BASE}/production-pos/{po_id}", headers=H)
    r.raise_for_status()
    return r.json()


async def fulfillment(c, H, po_id):
    r = await c.get(f"{BASE}/production-pos/{po_id}/fulfillment", headers=H)
    r.raise_for_status()
    return r.json()


async def main():
    async with httpx.AsyncClient(timeout=90) as c:
        admin = await login(c, *ADMIN)
        vendor = await login(c, *VENDOR)
        H_A = {"Authorization": f"Bearer {admin}"}
        H_V = {"Authorization": f"Bearer {vendor}"}
        await c.post(f"{BASE}/seed/maklon-full", headers=H_A)

        # ── Build 3 POs of the SAME buyer + their Approved receipts ──────────
        hr("SETUP: 3 maklon POs (same buyer) + Approved CMT receipts")
        poA, itA = await create_maklon_po(c, H_A, qty=6, rate=15000, tag="A")
        poB, itB = await create_maklon_po(c, H_A, qty=10, rate=12000, tag="B")
        poC, itC = await create_maklon_po(c, H_A, qty=5, rate=20000, tag="C")
        rA = await declare_and_approve_receipt(c, H_V, H_A, poA, itA, ship_qty=6)
        rB = await declare_and_approve_receipt(c, H_V, H_A, poB, itB, ship_qty=8)  # partial (8/10)
        rC = await declare_and_approve_receipt(c, H_V, H_A, poC, itC, ship_qty=5)
        print(f"  receipts: A={rA[:8]} B={rB[:8]} C={rC[:8]}")

        # ── D1: ONE consolidated dispatch spanning 3 POs (NO po_id in body) ──
        hr("SCENARIO D1: 1 consolidated surat jalan across 3 POs")
        r = await c.post(f"{BASE}/buyer-shipments", headers=H_A, json={
            "source_receipt_ids": [rA, rB, rC],
            "items": [
                {"po_item_id": itA["id"], "sku": itA["sku"], "qty_shipped": 6},
                {"po_item_id": itB["id"], "sku": itB["sku"], "qty_shipped": 8},
                {"po_item_id": itC["id"], "sku": itC["sku"], "qty_shipped": 5},
            ],
        })
        assert r.status_code == 201, f"consolidated dispatch failed {r.status_code}: {r.text[:400]}"
        sj = r.json()
        bsid = sj["id"]
        print(f"  SJ number={sj['shipment_number']} po_ids={sj.get('po_ids')} consolidated={sj.get('consolidated')}")
        assert sj.get("consolidated") is True, "expected consolidated=true"
        assert set(sj.get("po_ids") or []) == {poA["id"], poB["id"], poC["id"]}, "po_ids must contain all 3 POs"
        assert sj["shipment_number"].startswith("SJ-BYR-"), f"unexpected SJ number {sj['shipment_number']}"
        print("  [OK] one SJ, 3 POs, auto-numbered")

        # ── D2/D3: set buyer-received per line -> per-PO fulfillment + auto-close
        hr("SCENARIO D2/D3: per-line received -> independent per-PO auto-close")
        r = await c.get(f"{BASE}/buyer-shipments/{bsid}", headers=H_A)
        r.raise_for_status()
        items = r.json()["items"]
        # map po_item_id -> shipment item id
        by_poi = {it["po_item_id"]: it for it in items}
        recv_plan = {itA["id"]: 6, itB["id"]: 8, itC["id"]: 5}
        closes = {}
        for poi_id, qty in recv_plan.items():
            sitem = by_poi[poi_id]
            r2 = await c.put(f"{BASE}/buyer-shipment-items/{sitem['id']}/received", headers=H_A,
                             json={"qty_received": qty})
            r2.raise_for_status()
            ac = (r2.json() or {}).get("po_auto_close") or {}
            closes[poi_id] = ac.get("closed")
        print(f"  auto_close per line: A={closes[itA['id']]} B={closes[itB['id']]} C={closes[itC['id']]}")

        stA = await get_po(c, H_A, poA["id"])
        stB = await get_po(c, H_A, poB["id"])
        stC = await get_po(c, H_A, poC["id"])
        print(f"  PO-A status={stA['status']} closed_reason={stA.get('closed_reason')}")
        print(f"  PO-B status={stB['status']} closed_reason={stB.get('closed_reason')}")
        print(f"  PO-C status={stC['status']} closed_reason={stC.get('closed_reason')}")
        assert stA["status"] == "Completed" and stA.get("closed_reason") == "full_fulfillment", "PO-A must auto-close"
        assert stC["status"] == "Completed" and stC.get("closed_reason") == "full_fulfillment", "PO-C must auto-close"
        assert stB["status"] != "Completed", "PO-B partially received must NOT auto-close (independence)"

        fB = await fulfillment(c, H_A, poB["id"])
        print(f"  PO-B fulfillment: ordered={fB['total_ordered']} received={fB['total_received']} short={fB['qty_short']}")
        assert fB["total_ordered"] == 10 and fB["total_received"] == 8 and fB["qty_short"] == 2, "PO-B fulfillment wrong"
        fA = await fulfillment(c, H_A, poA["id"])
        assert fA["total_received"] == 6 and fA["qty_short"] == 0, "PO-A fulfillment wrong"
        print("  [OK] per-PO fulfillment correct; auto-close independent within one consolidated SJ")

        # ── D4: single-buyer guard ───────────────────────────────────────────
        hr("SCENARIO D4: single-buyer guard (mixed buyers -> 400)")
        poX, itX = await create_maklon_po(c, H_A, qty=4, rate=10000, tag="X", buyer="PT OTHER BUYER")
        rX = await declare_and_approve_receipt(c, H_V, H_A, poX, itX, ship_qty=4)
        # try to consolidate PO-B (buyer PT Phase D Buyer) + PO-X (PT OTHER BUYER)
        r = await c.post(f"{BASE}/buyer-shipments", headers=H_A, json={
            "source_receipt_ids": [rB, rX],
            "items": [
                {"po_item_id": itB["id"], "sku": itB["sku"], "qty_shipped": 1},
                {"po_item_id": itX["id"], "sku": itX["sku"], "qty_shipped": 1},
            ],
        })
        print(f"  mixed-buyer dispatch -> {r.status_code}: {r.text[:160]}")
        assert r.status_code == 400 and "buyer" in r.text.lower(), "expected 400 single-buyer guard"
        print("  [OK] mixed-buyer consolidation rejected")

        hr("✅ ALL PHASE D E2E SCENARIOS PASS")


if __name__ == "__main__":
    asyncio.run(main())
