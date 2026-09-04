"""
WS-E verification — outbound goods wiring ke wh_pending_movements + scan-out.
Cakupan:
  1. Dispatch buyer (fulfillment): dispatch → awaiting_scanout (stok TIDAK turun),
     scan-out → stok turun + reserved lepas + order dispatched.
  2. SJ Internal issue: buat pending outbound_rm best-effort (baris ter-resolve).
  3. CMT dispatch: buat pending outbound_rm per line.

Run: python /app/tests/verify_wse_outbound.py
Self-cleaning: menghapus semua data uji di akhir.
"""
import os
import uuid
import sys
from datetime import datetime, timezone

import requests
from pymongo import MongoClient

BASE = "http://localhost:8001"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "garment_erp")

db = MongoClient(MONGO_URL)[DB_NAME]

TAG = "WSE_TEST"
uid = lambda: str(uuid.uuid4())
now = lambda: datetime.now(timezone.utc)

results = []
def check(name, cond, detail=""):
    results.append((name, cond, detail))
    print(f"[{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def login():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    return r.json()["token"]


def cleanup():
    db.rahaza_material_stock.delete_many({"_wse_tag": TAG})
    db.rahaza_materials.delete_many({"_wse_tag": TAG})
    db.marketing_orders.delete_many({"_wse_tag": TAG})
    db.wh_pending_movements.delete_many({"notes": {"$regex": "WSE"}})
    db.wh_pending_movements.delete_many({"source_ref": {"$regex": "WSE"}})
    db.wh_delivery_notes.delete_many({"_wse_tag": TAG})
    db.wh_cmt_dispatches.delete_many({"_wse_tag": TAG})
    db.rahaza_fg_movements.delete_many({"notes": {"$regex": "WSE"}})


def test_dispatch_buyer(H):
    print("\n=== TEST 1: Dispatch Buyer (fulfillment) ===")
    material_id = uid()
    stock_id = uid()
    # FG stock: qty=100, reserved=10, available=90 (seolah 10 sudah dialokasikan)
    db.rahaza_material_stock.insert_one({
        "id": stock_id, "material_id": material_id, "location_id": "LOC-WSE",
        "material_code": "FG-WSE-1", "material_name": "FG WSE Test",
        "ownership": "cv_da", "inventory_category": "fg_internal",
        "qty": 100, "total_qty": 100, "quantity": 100,
        "available_quantity": 90, "reserved_quantity": 10,
        "unit": "pcs", "_wse_tag": TAG,
    })
    order_id = uid()
    order_code = f"WSE-ORD-{uid()[:6]}"
    db.marketing_orders.insert_one({
        "id": order_id, "order_id": order_code, "_wse_tag": TAG,
        "customer_name": "WSE Buyer", "city": "Bandung", "product_name": "FG WSE Test", "quantity": 10,
        "fulfillment_status": "packed_ready",
        "fulfillment_items": [{
            "material_id": material_id, "stock_id": stock_id,
            "sku_code": "FG-WSE-1", "material_name": "FG WSE Test",
            "qty_allocated": 10, "location_id": "LOC-WSE",
        }],
        "created_at": now().isoformat(),
    })

    # Dispatch
    r = requests.post(f"{BASE}/api/fulfillment/orders/{order_id}/dispatch", headers=H,
                      json={"tracking_number": "WSE123", "courier": "JNE", "notes": "WSE test"})
    check("dispatch HTTP 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return
    dj = r.json()
    check("dispatch → awaiting_scanout", dj.get("fulfillment_status") == "awaiting_scanout", str(dj.get("fulfillment_status")))
    check("dispatch → scan_out_required", dj.get("scan_out_required") is True)
    pend = dj.get("pending_movements", [])
    check("dispatch buat 1 pending outbound_fg", len(pend) == 1, f"count={len(pend)}")

    # Stock harus MASIH 100 (belum turun), reserved masih 10
    s = db.rahaza_material_stock.find_one({"id": stock_id})
    check("stok BELUM turun setelah dispatch (qty=100)", s.get("qty") == 100, f"qty={s.get('qty')}")
    check("reserved masih 10 setelah dispatch", s.get("reserved_quantity") == 10, f"reserved={s.get('reserved_quantity')}")

    # Order status di DB
    o = db.marketing_orders.find_one({"id": order_id})
    check("order status awaiting_scanout di DB", o.get("fulfillment_status") == "awaiting_scanout", str(o.get("fulfillment_status")))

    # Scan-out
    pending_id = pend[0]["pending_id"]
    r2 = requests.post(f"{BASE}/api/wms/pending/{pending_id}/scan-out", headers=H,
                       json={"scanned_qty": 10, "notes": "WSE scan out"})
    check("scan-out HTTP 200", r2.status_code == 200, f"status={r2.status_code} body={r2.text[:200]}")
    if r2.status_code == 200:
        sj = r2.json()
        check("scan-out status confirmed", sj.get("status") == "confirmed", str(sj.get("status")))
        fin = sj.get("finalize") or {}
        check("finalize dipicu (ok/dispatched)", fin.get("ok") is True and fin.get("dispatched") is True, str(fin))

    # Stock harus turun ke 90, reserved ke 0
    s2 = db.rahaza_material_stock.find_one({"id": stock_id})
    check("stok turun ke 90 setelah scan-out", s2.get("qty") == 90, f"qty={s2.get('qty')}")
    check("reserved lepas ke 0 setelah scan-out", s2.get("reserved_quantity") == 0, f"reserved={s2.get('reserved_quantity')}")

    # Order → dispatched
    o2 = db.marketing_orders.find_one({"id": order_id})
    check("order → dispatched setelah scan-out", o2.get("fulfillment_status") == "dispatched", str(o2.get("fulfillment_status")))
    check("dispatched_at terisi", bool(o2.get("dispatched_at")))


def test_sj_internal(H):
    print("\n=== TEST 2: SJ Internal issue ===")
    mat_id = uid()
    db.rahaza_materials.insert_one({"id": mat_id, "code": "RM-WSE-INT", "name": "Kain WSE Internal",
                                    "unit": "meter", "_wse_tag": TAG})
    # Create SJ-INTERNAL dengan 1 line resolvable + 1 line unresolvable
    r = requests.post(f"{BASE}/api/wms/delivery-notes", headers=H, json={
        "sj_type": "SJ-INTERNAL", "recipient_name": "Gudang B WSE",
        "lines": [
            {"description": "Kain WSE", "qty": 5, "unit": "meter", "material_code": "RM-WSE-INT"},
            {"description": "Item tak dikenal", "qty": 3, "unit": "pcs", "material_code": "RM-UNKNOWN-XYZ"},
        ],
    })
    check("SJ create HTTP 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return
    sj = r.json()["sj"]
    sj_id = sj["id"]
    db.wh_delivery_notes.update_one({"id": sj_id}, {"$set": {"_wse_tag": TAG}})
    # Issue
    r2 = requests.post(f"{BASE}/api/wms/delivery-notes/{sj_id}/issue", headers=H, json={})
    check("SJ issue HTTP 200", r2.status_code == 200, f"status={r2.status_code} body={r2.text[:200]}")
    if r2.status_code != 200:
        return
    body = r2.json()
    pend = body.get("wms_pending", [])
    check("SJ-INTERNAL buat 1 pending (best-effort, hanya line ter-resolve)", len(pend) == 1, f"count={len(pend)}")
    if pend:
        mv = db.wh_pending_movements.find_one({"id": pend[0]["pending_id"]})
        check("pending type outbound_rm", mv and mv.get("type") == "outbound_rm", str(mv.get("type") if mv else None))
        check("pending source_type delivery_note", mv and mv.get("source_type") == "delivery_note", str(mv.get("source_type") if mv else None))
        check("pending qty=5", mv and mv.get("expected_qty") == 5, str(mv.get("expected_qty") if mv else None))


def test_cmt_dispatch(H):
    print("\n=== TEST 3: CMT dispatch ===")
    mat_id = uid()
    db.rahaza_materials.insert_one({"id": mat_id, "code": "RM-WSE-CMT", "name": "Kain WSE CMT",
                                    "unit": "meter", "_wse_tag": TAG})
    # Create dispatch draft
    r = requests.post(f"{BASE}/api/wms/cmt-dispatches", headers=H, json={
        "cmt_name": "CMT WSE Vendor",
        "lines": [{"material_id": mat_id, "material_code": "RM-WSE-CMT", "material_name": "Kain WSE CMT",
                   "qty": 20, "unit": "meter"}],
    })
    check("CMT create HTTP 200", r.status_code == 200, f"status={r.status_code} body={r.text[:200]}")
    if r.status_code != 200:
        return
    disp = r.json()["dispatch"]
    disp_id = disp["id"]
    db.wh_cmt_dispatches.update_one({"id": disp_id}, {"$set": {"_wse_tag": TAG}})
    # Execute dispatch
    r2 = requests.post(f"{BASE}/api/wms/cmt-dispatches/{disp_id}/dispatch", headers=H, json={})
    check("CMT dispatch HTTP 200", r2.status_code == 200, f"status={r2.status_code} body={r2.text[:200]}")
    if r2.status_code != 200:
        return
    body = r2.json()
    pend = body.get("wms_pending", [])
    check("CMT dispatch buat 1 pending outbound_rm", len(pend) == 1, f"count={len(pend)}")
    check("CMT SJ-CMT dibuat", bool(body.get("sj_number")), str(body.get("sj_number")))
    if pend:
        mv = db.wh_pending_movements.find_one({"id": pend[0]["pending_id"]})
        check("pending source_type cmt_dispatch", mv and mv.get("source_type") == "cmt_dispatch", str(mv.get("source_type") if mv else None))
        check("pending qty=20", mv and mv.get("expected_qty") == 20, str(mv.get("expected_qty") if mv else None))


def main():
    cleanup()
    token = login()
    H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        test_dispatch_buyer(H)
        test_sj_internal(H)
        test_cmt_dispatch(H)
    finally:
        cleanup()

    passed = sum(1 for _, c, _ in results if c)
    total = len(results)
    print(f"\n===== WS-E RESULT: {passed}/{total} PASS =====")
    fails = [(n, d) for n, c, d in results if not c]
    if fails:
        print("FAILURES:")
        for n, d in fails:
            print(f"  - {n}: {d}")
        sys.exit(1)
    print("ALL WS-E CHECKS PASSED")


if __name__ == "__main__":
    main()
