"""
Core test — Maklon canonical qty-progress + Permak (rework) flow.

Seeds a minimal SSOT scenario directly in Mongo, then exercises the live API
(permak CRUD + status machine + canonical progress) and asserts the FG math.

Run: python /app/tests/test_core_maklon_progress.py
"""
import os
import sys
import uuid
from datetime import datetime, timezone

import requests
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "test_database")
BASE = "http://localhost:8001"

TAG = "CORETEST_PERMAK"
db = MongoClient(MONGO_URL)[DB_NAME]

PASS, FAIL = [], []


def check(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  [{extra}]" if extra else ""))


def login():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=20)
    r.raise_for_status()
    return r.json()["token"]


def cleanup():
    for col in ["production_pos", "po_items", "production_job_items", "cmt_receipts",
                "cmt_receipt_lines", "buyer_shipment_items", "dewi_cmt_permak"]:
        db[col].delete_many({"_coretest": TAG})
    # Permak dibuat via API tidak ber-tag _coretest → hapus by po_number/po_id namespace
    db.dewi_cmt_permak.delete_many({"$or": [
        {"po_number": {"$regex": f"^{TAG}"}},
        {"po_id": {"$regex": f"^{TAG}"}},
    ]})


def seed():
    now = datetime.now(timezone.utc)
    po_id = f"{TAG}-po-{uuid.uuid4().hex[:8]}"
    item_id = f"{TAG}-item-{uuid.uuid4().hex[:8]}"
    receipt_id = f"{TAG}-rcpt-{uuid.uuid4().hex[:8]}"
    line_id = f"{TAG}-line-{uuid.uuid4().hex[:8]}"

    db.production_pos.insert_one({
        "_coretest": TAG, "id": po_id, "po_number": f"{TAG}/001",
        "business_type": "maklon", "status": "In Production",
        "customer_name": "PT Uji Permak", "buyer_id": None,
        "created_at": now,
    })
    db.po_items.insert_one({
        "_coretest": TAG, "id": item_id, "po_id": po_id, "sku": "SKU-UJI-01",
        "product_name": "Kaos Uji", "size": "L", "color": "Hitam",
        "qty": 100, "unit_price": 50000, "created_at": now,
    })
    # produced (legacy progress source) = 100
    db.production_job_items.insert_one({
        "_coretest": TAG, "id": f"{TAG}-ji", "job_id": f"{TAG}-job",
        "po_item_id": item_id, "produced_qty": 100, "ordered_qty": 100, "created_at": now,
    })
    # Approved cmt_receipt: returned=100, accepted=90, reject=10
    db.cmt_receipts.insert_one({
        "_coretest": TAG, "id": receipt_id, "po_id": po_id, "po_number": f"{TAG}/001",
        "status": "Approved", "created_at": now,
    })
    db.cmt_receipt_lines.insert_one({
        "_coretest": TAG, "id": line_id, "receipt_id": receipt_id, "po_item_id": item_id,
        "sku_code": "SKU-UJI-01", "product_name": "Kaos Uji", "size": "L", "color": "Hitam",
        "qty_shipped_by_cmt": 100, "qty_actual": 90, "reject_qty": 10,
        "reject_reason": "jahitan lepas", "created_at": now,
    })
    # dispatched to buyer = 80
    db.buyer_shipment_items.insert_one({
        "_coretest": TAG, "id": f"{TAG}-bsi", "shipment_id": f"{TAG}-bs",
        "po_item_id": item_id, "qty_shipped": 80, "qty_received": 80, "created_at": now,
    })
    return {"po_id": po_id, "item_id": item_id, "receipt_id": receipt_id, "line_id": line_id}


def get_progress(H, po_id):
    r = requests.get(f"{BASE}/api/maklon-client/pos/{po_id}/progress", headers=H, timeout=20)
    r.raise_for_status()
    return r.json()


def main():
    cleanup()
    ids = seed()
    token = login()
    H = {"Authorization": f"Bearer {token}"}
    po_id, line_id = ids["po_id"], ids["line_id"]

    print("\n── Stage 0: baseline canonical progress ─────────────────────")
    p = get_progress(H, po_id)
    b = p["breakdown"]
    check("qty_ordered=100", b["qty_ordered"] == 100, b["qty_ordered"])
    check("qty_produced=100", b["qty_produced"] == 100)
    check("qty_returned_cmt=100", b["qty_returned_cmt"] == 100)
    check("qty_accepted=90", b["qty_accepted"] == 90)
    check("qty_reject_qc=10", b["qty_reject_qc"] == 10)
    check("qty_dispatched=80", b["qty_dispatched"] == 80)
    check("qty_good=90 (accepted, no rework)", b["qty_good"] == 90, b["qty_good"])
    check("qty_good_ready=10 (90-80)", b["qty_good_ready"] == 10, b["qty_good_ready"])
    check("INVARIANT returned==accepted+reject",
          b["qty_returned_cmt"] == b["qty_accepted"] + b["qty_reject_qc"])
    check("progress_pct=100 (produced, backward-compat)", p["progress_pct"] == 100)
    check("delivery_pct=80 (received, backward-compat)", p["delivery_pct"] == 80)

    print("\n── Stage 1: kirim reject ke permak (from-receipt-line, qty=10) ─")
    r = requests.post(f"{BASE}/api/dewi/cmt-permak/from-receipt-line", headers=H,
                      json={"receipt_line_id": line_id, "vendor_permak": "Workshop A"}, timeout=20)
    check("from-receipt-line 200", r.status_code == 200, r.status_code)
    permak = r.json()
    pid = permak["id"]
    check("permak qty=10 (default sisa reject)", permak["qty"] == 10, permak.get("qty"))
    check("permak source=reject", permak["source"] == "reject")
    check("permak status=open", permak["status"] == "open")

    p = get_progress(H, po_id)["breakdown"]
    check("rework_open=10", p["qty_rework_open"] == 10, p["qty_rework_open"])
    check("qty_good still 90 (reject WIP tak nambah good)", p["qty_good"] == 90, p["qty_good"])

    print("\n── Stage 2: guard — permak lagi melebihi sisa reject → 400 ───")
    r = requests.post(f"{BASE}/api/dewi/cmt-permak/from-receipt-line", headers=H,
                      json={"receipt_line_id": line_id, "qty": 5}, timeout=20)
    check("over-permak ditolak 400", r.status_code == 400, r.status_code)

    print("\n── Stage 3: selesai_berhasil (fixed=7, scrap=3) ─────────────")
    r = requests.post(f"{BASE}/api/dewi/cmt-permak/{pid}/status", headers=H,
                      json={"status": "selesai_berhasil", "qty_fixed": 7, "qty_scrap": 3}, timeout=20)
    check("status→selesai_berhasil 200", r.status_code == 200, r.status_code)
    p = get_progress(H, po_id)["breakdown"]
    check("rework_fixed=7", p["qty_rework_fixed"] == 7, p["qty_rework_fixed"])
    check("scrap=3", p["qty_scrap"] == 3, p["qty_scrap"])
    check("rework_open=0", p["qty_rework_open"] == 0, p["qty_rework_open"])
    check("qty_good=97 (90+7 reject repaired)", p["qty_good"] == 97, p["qty_good"])
    check("qty_good_ready=17 (97-80)", p["qty_good_ready"] == 17, p["qty_good_ready"])

    print("\n── Stage 4: bad-transition (terminal→open) ditolak ──────────")
    r = requests.post(f"{BASE}/api/dewi/cmt-permak/{pid}/status", headers=H,
                      json={"status": "open"}, timeout=20)
    check("terminal→open ditolak 400", r.status_code == 400, r.status_code)

    print("\n── Stage 5: permak dari GOOD pool (mengurangi FG) ───────────")
    r = requests.post(f"{BASE}/api/dewi/cmt-permak", headers=H, json={
        "po_id": po_id, "po_item_id": ids["item_id"], "qty": 5, "source": "good",
        "reason": "found defect after acceptance"}, timeout=20)
    check("create good-permak 200", r.status_code == 200, r.status_code)
    gid = r.json()["id"]
    p = get_progress(H, po_id)["breakdown"]
    check("qty_good=92 (97-5 good ditarik WIP)", p["qty_good"] == 92, p["qty_good"])

    # scrap the good permak → permanent loss
    r = requests.post(f"{BASE}/api/dewi/cmt-permak/{gid}/status", headers=H,
                      json={"status": "gagal_buang"}, timeout=20)
    check("good permak→gagal_buang 200", r.status_code == 200, r.status_code)
    p = get_progress(H, po_id)["breakdown"]
    check("qty_good=92 (good scrap permanen)", p["qty_good"] == 92, p["qty_good"])

    print("\n── Stage 6: summary endpoint ────────────────────────────────")
    r = requests.get(f"{BASE}/api/dewi/cmt-permak/summary?po_id={po_id}", headers=H, timeout=20)
    s = r.json()
    check("summary total_records=2", s["total_records"] == 2, s.get("total_records"))
    check("summary selesai_berhasil=1", s["selesai_berhasil"] == 1)
    check("summary gagal_buang=1", s["gagal_buang"] == 1)

    print("\n── Stage 7: backward-compat client portal /pos ──────────────")
    r = requests.get(f"{BASE}/api/maklon-client/pos", headers=H, timeout=20)
    rows = [x for x in r.json() if x["po_id"] == po_id]
    check("PO muncul di /pos", len(rows) == 1, len(rows))
    if rows:
        row = rows[0]
        check("/pos progress_pct=100 (produced)", row["progress_pct"] == 100, row["progress_pct"])
        check("/pos delivery_pct=80 (received)", row["delivery_pct"] == 80, row["delivery_pct"])
        check("/pos ada breakdown baru", isinstance(row.get("breakdown"), dict) and row["breakdown"].get("qty_good") == 92,
              row.get("breakdown", {}).get("qty_good"))

    cleanup()
    print("\n" + "=" * 60)
    print(f"RESULT: {len(PASS)} passed, {len(FAIL)} failed")
    if FAIL:
        print("FAILED:", FAIL)
        sys.exit(1)
    print("🎉 ALL CORE PROGRESS+PERMAK CHECKS PASSED")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        cleanup()
        print(f"\n❌ EXCEPTION: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
