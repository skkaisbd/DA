"""Seed a CLEAN consolidated-buyer-shipment demo scenario for UI verification.

Creates (idempotent) 2 maklon POs for the SAME buyer, each with a fully-received
Approved cmt_receipt that has NOT been dispatched yet. This lets the frontend
"Konsolidasi (multi-PO)" create flow be exercised end-to-end in the browser:
  Portal Maklon -> "Dispatch Buyer CMT" -> centang "Gabungkan beberapa PO" ->
  pilih buyer -> centang 2 CMT receipts lintas-PO -> isi qty -> Simpan.

Idempotent: if the demo buyer already has >=2 open POs with Approved receipts,
it prints "already seeded" and exits without creating duplicates.

Run:  cd /app/backend && python3 scripts/seed_phase_d_ui_demo.py
"""
import asyncio
import sys
import time

import httpx

BASE = "http://localhost:8001/api"
ADMIN = ("admin@garment.com", "Admin@123")
VENDOR = ("cmtvendor@dewiaditya.id", "Dewi@123")
# Buyer name: override via argv[1]; --force (any arg) always creates fresh.
BUYER = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "PT Konsolidasi Demo"
FORCE = "--force" in sys.argv
# Business type: --biz internal | --biz maklon (default maklon).
BIZ = "internal" if "--biz=internal" in sys.argv or ("--biz" in sys.argv and "internal" in sys.argv) else "maklon"


async def login(c, email, pw):
    r = await c.post(f"{BASE}/auth/login", json={"email": email, "password": pw})
    r.raise_for_status()
    return r.json()["token"]


async def create_maklon_po(c, H, qty, rate, tag, po_number, model_id=None, size_id=None, color_id=None):
    item = {
        "product_name": f"Kaos Konsolidasi {tag}", "sku": f"KD-{tag}-M", "size": "M",
        "color": "Navy", "qty": qty,
        "cmt_price_snapshot": rate, "selling_price_snapshot": rate * 2,
    }
    if model_id:
        item["model_id"] = model_id
    if size_id:
        item["size_id"] = size_id
    if color_id:
        item["color_id"] = color_id
    body = {
        "po_number": po_number, "business_type": BIZ, "status": "Confirmed",
        "customer_name": BUYER, "items": [item],
    }
    r = await c.post(f"{BASE}/production-pos", headers=H, json=body)
    assert r.status_code == 201, f"create PO failed {r.status_code}: {r.text[:300]}"
    po = r.json()
    return po, po["items"][0]


async def declare_and_approve_receipt(c, H_V, H_A, po, item, ship_qty):
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


async def main():
    async with httpx.AsyncClient(timeout=90) as c:
        admin = await login(c, *ADMIN)
        vendor = await login(c, *VENDOR)
        H_A = {"Authorization": f"Bearer {admin}"}
        H_V = {"Authorization": f"Bearer {vendor}"}

        # ensure maklon vendor/client exist
        await c.post(f"{BASE}/seed/maklon-full", headers=H_A)

        # idempotency: does BUYER already have >=2 open POs (this business type)?
        r = await c.get(f"{BASE}/production-pos?business_type={BIZ}", headers=H_A)
        r.raise_for_status()
        pos = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        existing = [p for p in pos if (p.get("customer_name") or "").strip() == BUYER
                    and p.get("status") in ("Confirmed", "In Production")]
        if len(existing) >= 2 and not FORCE:
            print(f"[seed:phase_d_ui] already seeded — buyer '{BUYER}' has {len(existing)} open {BIZ} POs. Skipping.")
            for p in existing[:5]:
                print("   -", p.get("po_number"), p.get("status"))
            return

        stamp = int(time.time())
        # Internal POs require model_id + size_id (rahaza master, D3 rule).
        model_id = size_id = color_id = None
        if BIZ == "internal":
            rm = await c.get(f"{BASE}/rahaza/models", headers=H_A)
            models = rm.json() if isinstance(rm.json(), list) else rm.json().get("items", [])
            assert models, "no rahaza_models seeded — cannot create internal PO (needs model_id)"
            model_id = models[0]["id"]
            rs = await c.get(f"{BASE}/rahaza/sizes", headers=H_A)
            sizes = rs.json() if isinstance(rs.json(), list) else rs.json().get("items", [])
            size_id = next((s["id"] for s in sizes if (s.get("name") or "").upper() == "M"), sizes[0]["id"] if sizes else None)
            rc = await c.get(f"{BASE}/rahaza/colors", headers=H_A)
            colors = rc.json() if isinstance(rc.json(), list) else rc.json().get("items", [])
            color_id = next((cc["id"] for cc in colors if (cc.get("name") or "").lower() == "navy"), colors[0]["id"] if colors else None)
            print(f"[seed:phase_d_ui] internal FK model={model_id} size={size_id} color={color_id}")
        print(f"[seed:phase_d_ui] creating 2 fresh {BIZ} POs for buyer '{BUYER}' (stamp={stamp})")
        poA, itA = await create_maklon_po(c, H_A, qty=100, rate=15000, tag="A", po_number=f"PO-KD-{stamp}-A", model_id=model_id, size_id=size_id, color_id=color_id)
        poB, itB = await create_maklon_po(c, H_A, qty=80, rate=12000, tag="B", po_number=f"PO-KD-{stamp}-B", model_id=model_id, size_id=size_id, color_id=color_id)
        rA = await declare_and_approve_receipt(c, H_V, H_A, poA, itA, ship_qty=100)
        rB = await declare_and_approve_receipt(c, H_V, H_A, poB, itB, ship_qty=80)
        _portal = "Produksi > Dispatch ke Buyer" if BIZ == "internal" else "Maklon > Dispatch Buyer CMT"
        print(f"[seed:phase_d_ui] DONE. buyer='{BUYER}' business_type={BIZ}")
        print(f"   PO-A={poA['po_number']} (100 pcs) receipt={rA[:8]} Approved")
        print(f"   PO-B={poB['po_number']} (80 pcs)  receipt={rB[:8]} Approved")
        print(f"   -> Portal {_portal} > 'Gabungkan beberapa PO' > pilih buyer > centang 2 receipt.")


if __name__ == "__main__":
    asyncio.run(main())
