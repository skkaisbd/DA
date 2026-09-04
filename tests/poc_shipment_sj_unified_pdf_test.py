#!/usr/bin/env python3
"""
POC — Penyatuan Pengiriman -> Surat Jalan (Phase 5A).
Memastikan PDF Engine (vendor-shipment, buyer-shipment, buyer-shipment-dispatch)
kini memakai branding perusahaan (pdf_common) + tanda tangan configurable
(pdf-doc-settings) + dukungan ?preview=1 (inline).

Self-clean. Exit 0 = PASS.
"""
import os, sys, uuid, requests
sys.path.insert(0, "/app/backend")
os.chdir("/app/backend")
from pymongo import MongoClient
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
BASE = "http://localhost:8001/api"
PASS = FAIL = 0
TAG = "POC_SJ_UNIFIED"


def check(c, m):
    global PASS, FAIL
    if c:
        PASS += 1; print(f"  ✅ {m}")
    else:
        FAIL += 1; print(f"  ❌ {m}")


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=15)
    return r.json()["token"]


def now():
    return datetime.now(timezone.utc)


def seed():
    vsid = str(uuid.uuid4())
    bsid = str(uuid.uuid4())
    db.vendor_shipments.insert_one({
        "id": vsid, "shipment_number": "SJ-VEND-POC-001",
        "delivery_note_number": "SJ/POC/2026/07/0001",
        "vendor_id": "poc-vendor", "vendor_name": "CV Vendor CMT Uji",
        "po_id": "poc-po", "po_number": "PO-POC-001",
        "shipment_date": now(), "shipment_type": "NORMAL",
        "status": "Sent", "notes": "Kirim kain untuk produksi POC", "_tag": TAG,
    })
    db.vendor_shipment_items.insert_many([
        {"id": str(uuid.uuid4()), "shipment_id": vsid, "po_number": "PO-POC-001",
         "product_name": "Kain Katun", "sku": "KTN-01", "size": "-", "color": "Navy",
         "qty_sent": 120, "_tag": TAG},
        {"id": str(uuid.uuid4()), "shipment_id": vsid, "po_number": "PO-POC-001",
         "product_name": "Rib", "sku": "RIB-02", "size": "-", "color": "Navy",
         "qty_sent": 8, "_tag": TAG},
    ])
    db.buyer_shipments.insert_one({
        "id": bsid, "shipment_number": "SJ-BUY-POC-001", "po_number": "PO-POC-001",
        "customer_name": "PT Buyer Uji", "vendor_name": "CV Vendor CMT Uji",
        "ship_status": "Pending", "status": "Pending",
        "created_at": now(), "_tag": TAG,
    })
    db.buyer_shipment_items.insert_many([
        {"id": str(uuid.uuid4()), "shipment_id": bsid, "po_item_id": "poc-poi-1",
         "product_name": "Kaos Polos", "sku": "KAOS-01", "size": "L", "color": "Navy",
         "ordered_qty": 100, "qty_shipped": 60, "dispatch_seq": 1,
         "dispatch_date": now(), "_tag": TAG},
    ])
    return vsid, bsid


def set_sig(token, doc_type, sigs):
    requests.put(f"{BASE}/pdf-doc-settings/{doc_type}",
                 headers={"Authorization": f"Bearer {token}"},
                 json={"signatures": sigs, "show_signatures": True}, timeout=15)


def pdf_ok(token, url, label, expect_inline):
    r = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=25)
    check(r.status_code == 200, f"{label}: HTTP {r.status_code}")
    check(r.headers.get("content-type", "").startswith("application/pdf"),
          f"{label}: content-type pdf ({r.headers.get('content-type')})")
    check(r.content[:4] == b"%PDF", f"{label}: PDF valid (%PDF, {len(r.content)} bytes)")
    check(len(r.content) > 1500, f"{label}: ukuran non-trivial")
    disp = r.headers.get("content-disposition", "")
    if expect_inline:
        check("inline" in disp, f"{label}: preview=1 -> inline ({disp[:40]})")
    else:
        check("attachment" in disp, f"{label}: tanpa preview -> attachment ({disp[:40]})")


def main():
    global FAIL
    token = login()
    hdr = {"Authorization": f"Bearer {token}"}
    vsid, bsid = seed()
    try:
        # konfigurasi tanda tangan custom untuk kedua doc_type
        set_sig(token, "vendor-shipment", [
            {"key": "sender", "label": "Pengirim", "name_source": "custom",
             "custom_name": "Budi (Gudang)", "role_label": "Produksi"},
            {"key": "receiver", "label": "Penerima", "name_source": "field",
             "field_key": "vendor_name", "role_label": "Vendor"},
        ])
        set_sig(token, "buyer-shipment-dispatch", [
            {"key": "sender", "label": "Pengirim", "name_source": "custom",
             "custom_name": "Budi (Gudang)", "role_label": "Produksi"},
            {"key": "receiver", "label": "Penerima", "name_source": "field",
             "field_key": "buyer_name", "role_label": "Buyer"},
        ])

        print("\n== A: Vendor Shipment (Surat Jalan Material) ==")
        pdf_ok(token, f"{BASE}/export-pdf?type=vendor-shipment&id={vsid}&preview=1",
               "vendor-shipment preview", expect_inline=True)
        pdf_ok(token, f"{BASE}/export-pdf?type=vendor-shipment&id={vsid}",
               "vendor-shipment attach", expect_inline=False)

        print("\n== B: Buyer Shipment Dispatch ==")
        pdf_ok(token, f"{BASE}/export-pdf?type=buyer-shipment-dispatch&shipment_id={bsid}&dispatch_seq=1&preview=1",
               "buyer-dispatch preview", expect_inline=True)

        print("\n== C: Buyer Shipment Kumulatif ==")
        pdf_ok(token, f"{BASE}/export-pdf?type=buyer-shipment&id={bsid}&preview=1",
               "buyer-cumulative preview", expect_inline=True)

        print("\n== D: Regression — WMS Delivery Notes list tetap hidup ==")
        r = requests.get(f"{BASE}/wms/delivery-notes", headers=hdr, timeout=15)
        check(r.status_code == 200, f"wms delivery-notes list HTTP {r.status_code}")
    finally:
        db.vendor_shipments.delete_many({"_tag": TAG})
        db.vendor_shipment_items.delete_many({"_tag": TAG})
        db.buyer_shipments.delete_many({"_tag": TAG})
        db.buyer_shipment_items.delete_many({"_tag": TAG})
        db.pdf_document_settings.delete_many({"doc_type": {"$in": ["vendor-shipment", "buyer-shipment-dispatch"]}})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); FAIL += 1
    print(f"\n==== RESULT: {PASS} PASS / {FAIL} FAIL ====")
    sys.exit(0 if FAIL == 0 else 1)
