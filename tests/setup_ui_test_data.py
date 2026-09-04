#!/usr/bin/env python3
"""Setup persistent test data for UI testing (UJI-SELISIH-* prefix)."""
import sys
import time
from datetime import date

import requests
from pymongo import MongoClient

API = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
VENDOR_EMAIL = "ujicmt@dewiaditya.id"
VENDOR_PASS = "Dewi@123"
VENDOR_ID = "uji-vendor-cmt-ssot"
MARK = "UJI-SELISIH"

env = {}
for line in open("/app/backend/.env", encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]

TOK = ""
VTOK = ""


def H(tok=None):
    return {"Authorization": f"Bearer {tok or TOK}", "Content-Type": "application/json"}


def call(m, p, body=None, tok=None):
    r = requests.request(m, f"{API}{p}", headers=H(tok), json=body, timeout=180)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"raw": r.text[:200]}


def bootstrap():
    global TOK, VTOK
    TOK = requests.post(f"{API}/api/auth/login", json=ADMIN, timeout=60).json()["token"]
    if not db.vendor_partners.find_one({"id": VENDOR_ID}):
        db.vendor_partners.insert_one({
            "id": VENDOR_ID, "code": "UJI-CMT-SSOT", "name": "CV Uji Jahit SSOT",
            "partner_type": "cmt", "phone": "0800000000", "address": "Uji",
            "active": True, "notes": MARK,
        })
    u = db.users.find_one({"email": VENDOR_EMAIL})
    if not u:
        call("POST", "/api/users", {
            "name": "Vendor Uji SSOT", "email": VENDOR_EMAIL, "password": VENDOR_PASS,
            "role": "cmt_vendor", "vendor_id": VENDOR_ID, "cmt_vendor_id": VENDOR_ID,
        }, tok=TOK)
    else:
        db.users.update_one({"email": VENDOR_EMAIL},
                            {"$set": {"vendor_id": VENDOR_ID, "cmt_vendor_id": VENDOR_ID,
                                      "role": "cmt_vendor", "status": "active"}})
    VTOK = requests.post(f"{API}/api/auth/login",
                         json={"email": VENDOR_EMAIL, "password": VENDOR_PASS},
                         timeout=60).json().get("token", "")
    print(f"✓ Bootstrap OK (admin token={bool(TOK)}, vendor token={bool(VTOK)})")


def make_po_with_short(sku: str, qty_claimed: int, qty_actual: int, label: str):
    """Create PO with CMT shortage."""
    st, po = call("POST", "/api/production-pos", {
        "po_number": f"{MARK}-{label}", "business_type": "maklon", "vendor_id": VENDOR_ID,
        "customer_name": "UJI Buyer Selisih", "status": "Confirmed", "notes": MARK,
        "po_date": str(date.today()), "deadline": str(date.today()),
        "items": [{"product_name": f"Kaos Uji {label}", "sku": sku, "size": "L",
                   "color": "Hitam", "qty": qty_claimed}]})
    poi = db.po_items.find_one({"po_id": po["id"]}, {"_id": 0})
    
    # Material shipment
    st, vs = call("POST", "/api/vendor-shipments", {
        "shipment_number": f"{MARK}-SJM-{label}", "vendor_id": VENDOR_ID, "po_id": po["id"],
        "po_number": po["po_number"], "shipment_date": str(date.today()),
        "shipment_type": "NORMAL", "notes": MARK,
        "items": [{"po_id": po["id"], "po_item_id": poi["id"], "sku": sku,
                   "product_name": poi.get("product_name", ""), "size": poi.get("size", ""),
                   "color": poi.get("color", ""), "qty_sent": qty_claimed}]})
    call("PUT", f"/api/vendor-shipments/{vs['id']}", {"status": "Received"})
    vsi = db.vendor_shipment_items.find_one({"shipment_id": vs["id"]}, {"_id": 0})
    call("POST", "/api/vendor-material-inspections", {
        "shipment_id": vs["id"], "vendor_id": VENDOR_ID, "inspection_date": str(date.today()),
        "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi["id"], "sku": sku, "ordered_qty": qty_claimed,
                   "received_qty": qty_claimed, "missing_qty": 0}]})
    
    # Production job
    st, job = call("POST", "/api/production-jobs",
                   {"vendor_shipment_id": vs["id"], "vendor_id": VENDOR_ID, "po_id": po["id"]})
    ji = db.production_job_items.find_one({"job_id": job["id"]}, {"_id": 0})
    call("POST", "/api/production-progress", {"job_item_id": ji["id"], 
                                              "completed_quantity": qty_claimed,
                                              "progress_date": str(date.today())})
    
    # Vendor declares shipment
    st, d = call("POST", "/api/buyer-shipments", {
        "po_id": po["id"], "job_id": job["id"], "shipment_date": str(date.today()),
        "notes": MARK,
        "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
                   "product_name": ji.get("product_name", ""), "qty_shipped": qty_claimed}]},
        tok=VTOK)
    
    # DA receives and does QC
    rec = db.cmt_receipts.find_one({"related_shipment_id": d.get("id")}, {"_id": 0},
                                   sort=[("created_at", -1)])
    line = db.cmt_receipt_lines.find_one({"receipt_id": rec["id"]}, {"_id": 0})
    call("PUT", f"/api/prod/cmt-receipts/{rec['id']}/lines/{line['id']}",
         {"qty_actual": qty_actual, "reject_qty": 0})
    call("POST", f"/api/prod/cmt-receipts/{rec['id']}/complete-qc", {})
    
    short = db.cmt_short_shipments.find_one({"receipt_line_id": line["id"]}, {"_id": 0})
    return po, rec, short


def make_buyer_short(sku: str, qty_shipped: int, qty_received: int, label: str):
    """Create PO with buyer shortage."""
    st, po = call("POST", "/api/production-pos", {
        "po_number": f"{MARK}-BYR-{label}", "business_type": "maklon", "vendor_id": VENDOR_ID,
        "customer_name": "UJI Buyer Selisih", "status": "Confirmed", "notes": MARK,
        "po_date": str(date.today()), "deadline": str(date.today()),
        "items": [{"product_name": f"Kaos Buyer {label}", "sku": sku, "size": "L",
                   "color": "Hitam", "qty": qty_shipped}]})
    poi = db.po_items.find_one({"po_id": po["id"]}, {"_id": 0})
    
    # Material shipment
    st, vs = call("POST", "/api/vendor-shipments", {
        "shipment_number": f"{MARK}-SJMB-{label}", "vendor_id": VENDOR_ID, "po_id": po["id"],
        "po_number": po["po_number"], "shipment_date": str(date.today()),
        "shipment_type": "NORMAL", "notes": MARK,
        "items": [{"po_id": po["id"], "po_item_id": poi["id"], "sku": sku,
                   "product_name": poi.get("product_name", ""), "size": poi.get("size", ""),
                   "color": poi.get("color", ""), "qty_sent": qty_shipped}]})
    call("PUT", f"/api/vendor-shipments/{vs['id']}", {"status": "Received"})
    vsi = db.vendor_shipment_items.find_one({"shipment_id": vs["id"]}, {"_id": 0})
    call("POST", "/api/vendor-material-inspections", {
        "shipment_id": vs["id"], "vendor_id": VENDOR_ID, "inspection_date": str(date.today()),
        "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi["id"], "sku": sku, "ordered_qty": qty_shipped,
                   "received_qty": qty_shipped, "missing_qty": 0}]})
    
    # Production job
    st, job = call("POST", "/api/production-jobs",
                   {"vendor_shipment_id": vs["id"], "vendor_id": VENDOR_ID, "po_id": po["id"]})
    ji = db.production_job_items.find_one({"job_id": job["id"]}, {"_id": 0})
    call("POST", "/api/production-progress", {"job_item_id": ji["id"], 
                                              "completed_quantity": qty_shipped,
                                              "progress_date": str(date.today())})
    
    # Vendor declares shipment to DA
    st, d = call("POST", "/api/buyer-shipments", {
        "po_id": po["id"], "job_id": job["id"], "shipment_date": str(date.today()),
        "notes": MARK,
        "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
                   "product_name": ji.get("product_name", ""), "qty_shipped": qty_shipped}]},
        tok=VTOK)
    
    # DA receives and does QC (full qty)
    rec = db.cmt_receipts.find_one({"related_shipment_id": d.get("id")}, {"_id": 0},
                                   sort=[("created_at", -1)])
    line = db.cmt_receipt_lines.find_one({"receipt_id": rec["id"]}, {"_id": 0})
    call("PUT", f"/api/prod/cmt-receipts/{rec['id']}/lines/{line['id']}",
         {"qty_actual": qty_shipped, "reject_qty": 0})
    call("POST", f"/api/prod/cmt-receipts/{rec['id']}/complete-qc", {})
    
    # Ship to buyer
    st, bs = call("POST", "/api/buyer-shipments", {
        "receiver_type": "buyer", "source_receipt_ids": [rec["id"]], "vendor_id": VENDOR_ID,
        "shipment_date": str(date.today()), "notes": MARK,
        "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
                   "qty_shipped": qty_shipped}]})
    
    # Buyer receives less
    bsi = db.buyer_shipment_items.find_one({"shipment_id": bs.get("id")}, {"_id": 0})
    call("PUT", f"/api/buyer-shipment-items/{bsi['id']}/received",
         {"qty_received": qty_received, "reason": "UJI: buyer hitung kurang"})
    
    bshort = db.buyer_short_records.find_one({"shipment_item_id": bsi["id"]}, {"_id": 0})
    return po, bs, bshort


def main():
    print("Setting up UI test data...")
    bootstrap()
    
    # Check if data already exists
    existing_cmt = db.cmt_short_shipments.count_documents({"status": "open"})
    existing_buyer = db.buyer_short_records.count_documents({"status": "open"})
    
    if existing_cmt > 0 or existing_buyer > 0:
        print(f"✓ Test data already exists (CMT shorts: {existing_cmt}, Buyer shorts: {existing_buyer})")
        return 0
    
    print("\n1. Creating CMT shortage (claim 60, received 50, short 10)...")
    po1, rec1, short1 = make_po_with_short(f"{MARK}-SKU-CMT", 60, 50, "CMT-001")
    print(f"   ✓ PO: {po1['po_number']}, Short: {(short1 or {}).get('short_number', 'N/A')}")
    
    print("\n2. Creating buyer shortage (shipped 50, received 45, short 5)...")
    po2, bs2, bshort2 = make_buyer_short(f"{MARK}-SKU-BYR", 50, 45, "BYR-001")
    print(f"   ✓ PO: {po2['po_number']}, Short: {(bshort2 or {}).get('short_number', 'N/A')}")
    
    # Verify
    final_cmt = db.cmt_short_shipments.count_documents({"status": "open"})
    final_buyer = db.buyer_short_records.count_documents({"status": "open"})
    print(f"\n✓ Setup complete! CMT shorts: {final_cmt}, Buyer shorts: {final_buyer}")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
