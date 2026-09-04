#!/usr/bin/env python3
"""
seed_consolidated_buyer_shipment_demo.py — FASE 22 (menutup temuan CONS-2 &
membuat keluhan #6 owner bisa DILIHAT: "dispatch ke buyer + gabungkan beberapa
PO ... child shipment tidak bisa diambil datanya").

Data demo lama TIDAK punya satu pun Surat Jalan Buyer GABUNGAN, jadi walau
backend-nya benar (dijaga INV-11), owner tidak pernah melihat buktinya di UI.

Skrip ini membuat — LEWAT ENDPOINT ASLI, bukan tulis mentah ke Mongo:
  2 PO maklon untuk BUYER YANG SAMA (PT Aruna Activewear) → kirim material ke
  vendor CMT → inspeksi → job → progres → deklarasi kirim vendor → QC selesai →
  1 SURAT JALAN BUYER GABUNGAN dari 2 penerimaan (2 PO) sekaligus.

Hasilnya di UI: Portal Produksi/Maklon → "Serah Terima FG / Dispatch ke Buyer" →
buka detail SJ gabungan → rincian per PO + sumber penerimaan + child shipment.

Pakai:
    python3 scripts/seed_consolidated_buyer_shipment_demo.py
    python3 scripts/seed_consolidated_buyer_shipment_demo.py --clean
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
G, Y, R, C, B, X = "\033[92m", "\033[93m", "\033[91m", "\033[96m", "\033[1m", "\033[0m"
MARK = "DEMO-SJ-GABUNGAN"
PO_A, PO_B = "PO-MKL-GAB-A", "PO-MKL-GAB-B"


def call(method, path, token=None, body=None):
    req = urllib.request.Request(f"{API}{path}",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:  # noqa: BLE001
            return e.code, {}
    except Exception as e:  # noqa: BLE001
        return -1, {"error": str(e)}


def login(email, pwd):
    st, r = call("POST", "/api/auth/login", None, {"email": email, "password": pwd})
    return r.get("token") if st == 200 else None


def clean(db):
    pos = list(db.production_pos.find({"po_number": {"$in": [PO_A, PO_B]}}, {"_id": 0, "id": 1}))
    ids = [p["id"] for p in pos]
    n = 0
    if ids:
        item_ids = [i["id"] for i in db.po_items.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        jobs = [j["id"] for j in db.production_jobs.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        vs = [s["id"] for s in db.vendor_shipments.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        bs = [s["id"] for s in db.buyer_shipments.find(
            {"$or": [{"po_id": {"$in": ids}}, {"po_ids": {"$in": ids}}]}, {"_id": 0, "id": 1})]
        rcpt = [r["id"] for r in db.cmt_receipts.find({"po_id": {"$in": ids}}, {"_id": 0, "id": 1})]
        for coll, q in (
            ("production_job_items", {"job_id": {"$in": jobs}}),
            ("production_progress", {"job_id": {"$in": jobs}}),
            ("production_jobs", {"id": {"$in": jobs}}),
            ("vendor_shipment_items", {"shipment_id": {"$in": vs}}),
            ("vendor_material_inspections", {"shipment_id": {"$in": vs}}),
            ("vendor_shipments", {"id": {"$in": vs}}),
            ("buyer_shipment_items", {"shipment_id": {"$in": bs}}),
            ("buyer_shipments", {"id": {"$in": bs}}),
            ("cmt_receipt_lines", {"receipt_id": {"$in": rcpt}}),
            ("cmt_receipts", {"id": {"$in": rcpt}}),
            ("dewi_cmt_payments", {"po_id": {"$in": ids}}),
            ("po_items", {"id": {"$in": item_ids}}),
            ("production_pos", {"id": {"$in": ids}}),
            ("dewi_maklon_pos", {"id": {"$in": ids}}),
        ):
            n += db[coll].delete_many(q).deleted_count
    print(f"  dibersihkan {n} dokumen demo SJ gabungan")
    return n


def build_po(db, adm, ven, po_number, qty, serial, client, cat, variant, vendor_id):
    st, po = call("POST", "/api/production-pos", adm, {
        "po_number": po_number, "business_type": "maklon", "buyer_id": client["id"],
        "vendor_id": vendor_id, "status": "Confirmed", "notes": MARK,
        "po_date": date.today().isoformat(), "deadline": date.today().isoformat(),
        "items": [{"catalog_item_id": cat["id"], "maklon_variant_id": variant.get("id") or variant.get("sku"),
                   "sku": variant.get("sku"), "color": variant.get("color"), "size": variant.get("size"),
                   "product_name": cat.get("product_name"), "qty": qty,
                   "cmt_price_snapshot": 18000, "serial_number": serial}]})
    if st not in (200, 201):
        print(f"{R}  gagal buat PO {po_number}: {st} {po}{X}")
        return None
    po_id = po["id"]
    poi = list(db.po_items.find({"po_id": po_id}, {"_id": 0}))[0]

    sj = f"SJ-MTR-{po_number}"
    st, vs = call("POST", "/api/vendor-shipments", adm, {
        "vendor_id": vendor_id, "shipment_number": sj, "po_id": po_id, "notes": MARK,
        "shipment_date": date.today().isoformat(), "shipment_type": "NORMAL",
        "items": [{"po_id": po_id, "po_item_id": poi["id"], "sku": poi.get("sku"), "qty_sent": qty}]})
    if st not in (200, 201):
        print(f"{R}  gagal kirim material {po_number}: {st} {vs}{X}")
        return None
    vs_id = vs["id"]
    vsi = list(db.vendor_shipment_items.find({"shipment_id": vs_id}, {"_id": 0}))
    call("PUT", f"/api/vendor-shipments/{vs_id}", ven or adm, {"status": "Received"})
    call("POST", "/api/vendor-material-inspections", ven or adm, {
        "shipment_id": vs_id, "overall_notes": MARK,
        "items": [{"shipment_item_id": vsi[0]["id"], "sku": vsi[0].get("sku"),
                   "ordered_qty": qty, "received_qty": qty, "missing_qty": 0}]})
    st, job = call("POST", "/api/production-jobs", adm, {
        "vendor_shipment_id": vs_id, "vendor_id": vendor_id, "po_id": po_id, "notes": MARK})
    if st not in (200, 201):
        print(f"{R}  gagal buat job {po_number}: {st} {job}{X}")
        return None
    job_id = job["id"]
    ji = list(db.production_job_items.find({"job_id": job_id}, {"_id": 0}))[0]
    call("POST", "/api/production-progress", ven or adm, {
        "job_item_id": ji["id"], "completed_quantity": qty,
        "progress_date": date.today().isoformat(), "notes": MARK})
    st, decl = call("POST", "/api/buyer-shipments", ven or adm, {
        "po_id": po_id, "job_id": job_id, "notes": MARK,
        "shipment_date": date.today().isoformat(),
        "items": [{"po_item_id": poi["id"], "job_item_id": ji["id"],
                   "sku": ji.get("sku"), "qty_shipped": qty}]})
    if st not in (200, 201):
        print(f"{R}  gagal deklarasi kirim vendor {po_number}: {st} {decl}{X}")
        return None
    time.sleep(1)
    rcpt = db.cmt_receipts.find_one({"related_shipment_id": decl["id"]}, {"_id": 0})
    if not rcpt:
        print(f"{R}  penerimaan CMT tidak terbentuk untuk {po_number}{X}")
        return None
    lines = list(db.cmt_receipt_lines.find({"receipt_id": rcpt["id"]}, {"_id": 0}))
    call("PUT", f"/api/prod/cmt-receipts/{rcpt['id']}/lines/{lines[0]['id']}", adm,
         {"qty_actual": qty, "reject_qty": 0})
    st, _ = call("POST", f"/api/prod/cmt-receipts/{rcpt['id']}/complete-qc", adm)
    print(f"{G}  ✓ {po_number}: {qty} pcs → job {job.get('job_number')} → "
          f"penerimaan {rcpt.get('receipt_code')} SELESAI QC (HTTP {st}){X}")
    return {"po_id": po_id, "po_item_id": poi["id"], "job_item_id": ji["id"],
            "sku": ji.get("sku"), "qty": qty, "receipt_id": rcpt["id"]}


def main() -> int:
    db = db_handle()
    if "--clean" in sys.argv:
        clean(db)
        return 0
    adm = login("admin@garment.com", "Admin@123")
    if not adm:
        print(f"{R}login admin gagal{X}")
        return 1
    ven = login("cmtvendor@dewiaditya.id", "Dewi@123")

    exist = db.buyer_shipments.find_one({"notes": MARK, "is_consolidated": True}, {"_id": 0, "shipment_number": 1})
    if exist:
        print(f"{Y}  SJ gabungan demo sudah ada: {exist.get('shipment_number')} — idempoten{X}")
        return 0
    clean(db)

    client = db.dewi_maklon_clients.find_one({"code": "ARNA"}, {"_id": 0})
    cat = db.dewi_maklon_buyer_catalog.find_one({"artikel_code": "ARN-HD"}, {"_id": 0})
    vendor = db.vendor_partners.find_one({"code": "JMC"}, {"_id": 0})
    if not (client and cat and vendor):
        print(f"{R}  master demo belum ada (klien ARNA / katalog ARN-HD / vendor JMC){X}")
        return 1
    variants = [v for v in (cat.get("variants") or []) if v.get("active") is not False]
    if len(variants) < 2:
        print(f"{R}  katalog ARN-HD butuh minimal 2 varian{X}")
        return 1
    print(f"{C}  Buyer {client['name']} · artikel {cat.get('artikel_code')} · vendor {vendor.get('name')}{X}")

    a = build_po(db, adm, ven, PO_A, 30, "SN-GAB-A", client, cat, variants[0], vendor["id"])
    b = build_po(db, adm, ven, PO_B, 20, "SN-GAB-B", client, cat, variants[1], vendor["id"])
    if not (a and b):
        return 1

    st, cons = call("POST", "/api/buyer-shipments", adm, {
        "source_receipt_ids": [a["receipt_id"], b["receipt_id"]],
        "notes": MARK, "shipment_date": date.today().isoformat(),
        "items": [
            {"po_item_id": a["po_item_id"], "job_item_id": a["job_item_id"],
             "sku": a["sku"], "qty_shipped": a["qty"]},
            {"po_item_id": b["po_item_id"], "job_item_id": b["job_item_id"],
             "sku": b["sku"], "qty_shipped": b["qty"]},
        ]})
    if st not in (200, 201):
        print(f"{R}  gagal buat SJ buyer GABUNGAN: {st} {cons}{X}")
        return 1
    st, detail = call("GET", f"/api/buyer-shipments/{cons['id']}", adm)
    pb = (detail or {}).get("po_breakdown") or []
    print(f"{G}{B}  ✓ SJ Buyer GABUNGAN {cons.get('shipment_number')} — "
          f"{len(pb)} PO, {len((detail or {}).get('items') or [])} item, "
          f"sumber penerimaan {len((detail or {}).get('source_receipts') or [])}{X}")
    for p in pb:
        print(f"      · {p.get('po_number')}: {p.get('qty_shipped')} pcs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
