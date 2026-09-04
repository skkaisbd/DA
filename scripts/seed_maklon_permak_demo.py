"""
Seed DEMO maklon scenario for Permak + canonical progress UI testing.
Idempotent (fixed ids). Leaves data in DB (tagged _demo='MAKLON_PERMAK_DEMO').

Creates: 1 maklon production_po + 2 po_items + production_job_items (produced)
+ Approved cmt_receipt + cmt_receipt_lines (with reject_qty) + buyer_shipment_items
+ minimal dewi_maklon_pos mirror (so PO-360 opens).

Run: python /app/scripts/seed_maklon_permak_demo.py
Clean: python /app/scripts/seed_maklon_permak_demo.py --clean
"""
import os
import sys
from datetime import datetime, timezone, timedelta
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
TAG = "MAKLON_PERMAK_DEMO"

PO_ID = "demo-maklon-po-0001"
IT1 = "demo-maklon-item-0001"
IT2 = "demo-maklon-item-0002"
RCPT = "demo-maklon-rcpt-0001"
LN1 = "demo-maklon-line-0001"
LN2 = "demo-maklon-line-0002"

# PO kedua — skenario TELAT (deadline lampau, sudah kirim ke CMT, belum disetor)
PO2_ID = "demo-maklon-po-0002"
IT3 = "demo-maklon-item-0003"

COLS = ["production_pos", "po_items", "production_job_items", "cmt_receipts",
        "cmt_receipt_lines", "buyer_shipment_items", "dewi_cmt_permak", "dewi_maklon_pos",
        "vendor_shipments", "vendor_shipment_items"]


def clean():
    for c in COLS:
        r = db[c].delete_many({"_demo": TAG})
        if r.deleted_count:
            print(f"  cleaned {r.deleted_count} from {c}")
    # permak dibuat via API (tanpa _demo) → hapus by po_id demo
    r = db.dewi_cmt_permak.delete_many({"po_id": {"$regex": "^demo-maklon-po"}})
    if r.deleted_count:
        print(f"  cleaned {r.deleted_count} demo permaks (by po_id)")


def _vendor_cmt():
    """Vendor CMT NYATA dari master (bukan sekadar nama teks).

    FASE 22 — dulu seeder ini hanya menulis `vendor_name`, tanpa `vendor_id`.
    Akibatnya kolom "Vendor CMT / SJ Rework" (keluhan #7) dan filter portal vendor
    KOSONG untuk data demo — padahal backend-nya benar. Sekarang ambil vendor JMC
    dari `vendor_partners` supaya relasinya sah.
    """
    v = (db.vendor_partners.find_one({"code": "JMC"}, {"_id": 0, "id": 1, "name": 1})
         or db.vendor_partners.find_one({"active": {"$ne": False}}, {"_id": 0, "id": 1, "name": 1})
         or {})
    return v.get("id"), v.get("name") or "CV Jahit Mitra CMT"


def seed():
    clean()
    now = datetime.now(timezone.utc)
    VENDOR_ID, VENDOR_NAME = _vendor_cmt()
    deadline = (now + timedelta(days=20)).date().isoformat()
    delivery_deadline = (now + timedelta(days=10)).date().isoformat()
    dispatch_date = (now - timedelta(days=6)).date().isoformat()

    db.production_pos.insert_one({
        "_demo": TAG, "id": PO_ID, "po_number": "PO-MKL-DEMO-001",
        "business_type": "maklon", "status": "In Production",
        "customer_name": "PT Contoh Buyer", "buyer_id": None,
        "vendor_id": VENDOR_ID, "vendor_name": VENDOR_NAME,
        "deadline": deadline, "delivery_deadline": delivery_deadline, "po_date": now.date().isoformat(),
        "total_qty": 300, "total_value": 45000000, "created_at": now,
    })
    items = [
        {"id": IT1, "sku": "KAOS-DEMO-L", "product_name": "Kaos Premium", "size": "L",
         "color": "Hitam", "qty": 200, "unit_price": 150000, "cmt_price_snapshot": 25000, "serial_number": "SN-L"},
        {"id": IT2, "sku": "KAOS-DEMO-M", "product_name": "Kaos Premium", "size": "M",
         "color": "Putih", "qty": 100, "unit_price": 150000, "cmt_price_snapshot": 25000, "serial_number": "SN-M"},
    ]
    # buku kuantitas (SSOT `core/production_qty_ledger`) — HARUS konsisten dengan
    # baris penerimaan di bawah: produced tetap penuh, accepted+reject = declared.
    LEDGER = {IT1: {"accepted": 185, "reject": 15}, IT2: {"accepted": 92, "reject": 8}}
    for it in items:
        db.po_items.insert_one({"_demo": TAG, "po_id": PO_ID, "created_at": now, **it})
        led = LEDGER[it["id"]]
        db.production_job_items.insert_one({
            "_demo": TAG, "id": f"ji-{it['id']}", "job_id": "demo-job",
            "po_item_id": it["id"], "produced_qty": it["qty"], "ordered_qty": it["qty"],
            "sku": it["sku"], "product_name": it["product_name"],
            "size": it["size"], "color": it["color"],
            "qty_declared": it["qty"], "qty_accepted": led["accepted"],
            "qty_reject": led["reject"], "qty_rework_open": led["reject"],
            "qty_repaired": 0, "qty_scrap": 0,
            "created_at": now,
        })

    # Penerimaan SELESAI QC (status kanonik `completed_qc` — FASE 4/22).
    # Dulu seeder ini menulis status LEGACY "Approved"; walau API menormalkan saat
    # dibaca, data demo-nya tetap memamerkan status yang sudah dihapus dari alur
    # (keluhan #5 owner). Sekarang datanya sendiri sudah kanonik.
    db.cmt_receipts.insert_one({
        "_demo": TAG, "id": RCPT, "receipt_code": "CMT-RCV-DEMO-001",
        "po_id": PO_ID, "po_number": "PO-MKL-DEMO-001",
        "cmt_vendor_id": VENDOR_ID, "cmt_name": VENDOR_NAME,
        "status": "completed_qc", "receipt_date": now.date().isoformat(),
        "total_shipped_by_cmt": 300, "total_actual": 277, "total_rejected": 23,
        "created_at": now, "completed_qc_at": now,
        # buku kuantitas sudah ditulis manual di atas → jangan diterapkan dua kali
        "qty_ledger_applied_at": now.isoformat(),
        "qty_ledger_result": {"job_items": 2, "quarantined": 0, "accepted": 277, "rejected": 23},
    })
    db.cmt_receipt_lines.insert_many([
        {"_demo": TAG, "id": LN1, "receipt_id": RCPT, "po_item_id": IT1,
         "job_item_id": f"ji-{IT1}",
         "sku_code": "KAOS-DEMO-L", "product_name": "Kaos Premium", "size": "L", "color": "Hitam",
         "qty_shipped_by_cmt": 200, "qty_actual": 185, "reject_qty": 15,
         "reject_reason": "jahitan lepas", "created_at": now},
        {"_demo": TAG, "id": LN2, "receipt_id": RCPT, "po_item_id": IT2,
         "job_item_id": f"ji-{IT2}",
         "sku_code": "KAOS-DEMO-M", "product_name": "Kaos Premium", "size": "M", "color": "Putih",
         "qty_shipped_by_cmt": 100, "qty_actual": 92, "reject_qty": 8,
         "reject_reason": "noda", "created_at": now},
    ])

    # Dispatched to buyer: L → 150, M → 60
    db.buyer_shipment_items.insert_many([
        {"_demo": TAG, "id": "bsi-L", "shipment_id": "bs-demo", "po_item_id": IT1,
         "qty_shipped": 150, "qty_received": 150, "created_at": now},
        {"_demo": TAG, "id": "bsi-M", "shipment_id": "bs-demo", "po_item_id": IT2,
         "qty_shipped": 60, "qty_received": 60, "created_at": now},
    ])

    # Minimal dewi_maklon_pos mirror (so PO-360 opens; id shared with production_pos)
    db.dewi_maklon_pos.insert_one({
        "_demo": TAG, "id": PO_ID, "mirror_of": "production_pos", "production_po_id": PO_ID,
        "po_number": "PO-MKL-DEMO-001", "client_name": "PT Contoh Buyer",
        "status": "in_production", "deadline": deadline,
        "total_qty": 300, "total_value": 45000000,
        "items": [
            {"item_id": IT1, "sku": "KAOS-DEMO-L", "product_name": "Kaos Premium", "size": "L",
             "color": "Hitam", "qty": 200, "qty_produced": 185, "qty_dispatched": 150, "status": "in_production"},
            {"item_id": IT2, "sku": "KAOS-DEMO-M", "product_name": "Kaos Premium", "size": "M",
             "color": "Putih", "qty": 100, "qty_produced": 92, "qty_dispatched": 60, "status": "in_production"},
        ],
        "created_at": now, "updated_at": now,
    })
    # Vendor shipments DA→CMT (potongan dikirim) — PO1: L 200, M 100 (semua sudah dikirim)
    db.vendor_shipments.insert_one({
        "_demo": TAG, "id": "demo-vs-0001", "shipment_number": "VS-DEMO-001",
        "po_id": PO_ID, "vendor_id": VENDOR_ID, "vendor_name": VENDOR_NAME, "status": "Received",
        "shipment_type": "REGULAR", "shipment_date": dispatch_date, "created_at": now,
    })
    db.vendor_shipment_items.insert_many([
        {"_demo": TAG, "id": "demo-vsi-L", "shipment_id": "demo-vs-0001", "po_item_id": IT1,
         "product_name": "Kaos Premium", "qty_sent": 200, "created_at": now},
        {"_demo": TAG, "id": "demo-vsi-M", "shipment_id": "demo-vs-0001", "po_item_id": IT2,
         "product_name": "Kaos Premium", "qty_sent": 100, "created_at": now},
    ])

    # ── PO kedua: TELAT (delivery_deadline lampau, sudah kirim ke CMT 120, belum ada setoran) ──
    late_delivery = (now - timedelta(days=4)).date().isoformat()   # target CMT = −4−buffer(3) = lewat jauh
    late_dispatch = (now - timedelta(days=18)).date().isoformat()
    v2 = (db.vendor_partners.find_one({"code": "RPK"}, {"_id": 0, "id": 1, "name": 1}) or {})
    V2_ID, V2_NAME = v2.get("id") or VENDOR_ID, v2.get("name") or VENDOR_NAME
    db.production_pos.insert_one({
        "_demo": TAG, "id": PO2_ID, "po_number": "PO-MKL-DEMO-002",
        "business_type": "maklon", "status": "In Production",
        "customer_name": "CV Mitra Telat", "buyer_id": None,
        "vendor_id": V2_ID, "vendor_name": V2_NAME,
        "deadline": (now + timedelta(days=2)).date().isoformat(),
        "delivery_deadline": late_delivery, "po_date": (now - timedelta(days=25)).date().isoformat(),
        "total_qty": 120, "total_value": 18000000, "created_at": now,
    })
    db.po_items.insert_one({
        "_demo": TAG, "id": IT3, "po_id": PO2_ID, "sku": "CELANA-DEMO-XL",
        "product_name": "Celana Chino", "size": "XL", "color": "Navy",
        "qty": 120, "unit_price": 150000, "cmt_price_snapshot": 30000,
        "serial_number": "SN-XL", "created_at": now,
    })
    db.production_job_items.insert_one({
        "_demo": TAG, "id": "demo-ji-3", "job_id": "demo-job-2",
        "po_item_id": IT3, "produced_qty": 40, "ordered_qty": 120,
        "sku": "CELANA-DEMO-XL", "product_name": "Celana Chino", "size": "XL", "color": "Navy",
        "qty_declared": 0, "qty_accepted": 0, "qty_reject": 0,
        "qty_rework_open": 0, "qty_repaired": 0, "qty_scrap": 0,
        "created_at": now,
    })
    db.vendor_shipments.insert_one({
        "_demo": TAG, "id": "demo-vs-0002", "shipment_number": "VS-DEMO-002",
        "po_id": PO2_ID, "vendor_id": V2_ID, "vendor_name": V2_NAME, "status": "Received",
        "shipment_type": "REGULAR", "shipment_date": late_dispatch, "created_at": now,
    })
    db.vendor_shipment_items.insert_one({
        "_demo": TAG, "id": "demo-vsi-XL", "shipment_id": "demo-vs-0002", "po_item_id": IT3,
        "product_name": "Celana Chino", "qty_sent": 120, "created_at": now,
    })
    db.dewi_maklon_pos.insert_one({
        "_demo": TAG, "id": PO2_ID, "mirror_of": "production_pos", "production_po_id": PO2_ID,
        "po_number": "PO-MKL-DEMO-002", "client_name": "CV Mitra Telat",
        "status": "in_production", "deadline": late_delivery,
        "total_qty": 120, "total_value": 18000000,
        "items": [{"item_id": IT3, "sku": "CELANA-DEMO-XL", "product_name": "Celana Chino",
                   "size": "XL", "color": "Navy", "qty": 120, "qty_produced": 40,
                   "qty_dispatched": 0, "status": "in_production"}],
        "created_at": now, "updated_at": now,
    })

    print(f"✅ Seeded demo maklon PO {PO_ID} (PO-MKL-DEMO-001)")
    print("   L: ordered 200, accepted 185, reject 15, dispatched 150")
    print("   M: ordered 100, accepted 92, reject 8, dispatched 60")
    print(f"✅ Seeded demo maklon PO {PO2_ID} (PO-MKL-DEMO-002) — skenario TELAT (sent 120, belum setor)")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
        print("cleaned demo data")
    else:
        seed()
