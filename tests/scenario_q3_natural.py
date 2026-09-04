#!/usr/bin/env python3
"""scenario_q3_natural.py — UJI JALUR ALAMI: buyer terima KURANG dari yang dikirim.

Berbeda dari `scenario_owner_questions.py` (yang memakai Quick Complete sehingga PO
langsung berstatus 'Completed'), skrip ini menempuh alur NORMAL:
  PO → kirim material ke vendor → terima → inspeksi → job → progres produksi →
  penerimaan FG dari CMT (QC) → surat jalan ke buyer → buyer terima KURANG 5 pcs →
  tutup-kurang (close-short).

Tujuan: membuktikan apakah selisih penerimaan buyer memicu penyesuaian
(status PO, nota kredit / AR, kapasitas kirim ulang, stok FG).
"""
from __future__ import annotations

import json
import sys
import time
from datetime import date

import requests
from pymongo import MongoClient

API = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
G, R, Y, C, B, X = "\033[92m", "\033[91m", "\033[93m", "\033[96m", "\033[1m", "\033[0m"
S = time.strftime("%H%M%S")

env = {}
for line in open("/app/backend/.env", encoding="utf-8"):
    if "=" in line and not line.strip().startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"')
db = MongoClient(env["MONGO_URL"])[env["DB_NAME"]]
TOK = requests.post(f"{API}/api/auth/login", json=ADMIN, timeout=60).json()["token"]
H = {"Authorization": f"Bearer {TOK}", "Content-Type": "application/json"}
notes: list[str] = []


def call(m, p, body=None, ok=(200, 201)):
    r = requests.request(m, f"{API}{p}", headers=H, json=body, timeout=180)
    try:
        d = r.json()
    except Exception:
        d = {"raw": r.text[:200]}
    tag = f"{G}{r.status_code}{X}" if r.status_code in ok else f"{R}{r.status_code}{X}"
    print(f"    {tag} {m} {p} {'' if r.status_code in ok else str(d)[:260]}")
    return r.status_code, d


def fg(sku):
    mat = db.rahaza_materials.find_one({"code": sku}, {"_id": 0, "id": 1})
    if not mat:
        return -1
    return sum(float(x.get("qty") or 0) for x in
               db.rahaza_material_stock.find({"material_id": mat["id"]}, {"_id": 0, "qty": 1}))


print(f"{C}{B}{'═' * 78}\nUJI JALUR ALAMI — BUYER TERIMA KURANG 5 PCS DARI 100 YANG DIKIRIM\n{'═' * 78}{X}")
vpo = db.production_pos.find_one({"vendor_id": {"$nin": [None, ""]}}, {"_id": 0, "vendor_id": 1, "vendor_name": 1})
vendor_id, vendor_name = vpo["vendor_id"], vpo.get("vendor_name", "Vendor CMT")
sku = f"UJI-N-{S}"

print(f"\n{C}1. Buat PO 100 pcs (status Confirmed, TIDAK pakai Quick Complete){X}")
st, po = call("POST", "/api/production-pos", {
    "po_number": f"UJI-N-{S}", "business_type": "maklon", "vendor_id": vendor_id,
    "customer_name": "UJI Buyer Alami", "status": "Confirmed",
    "po_date": str(date.today()), "deadline": str(date.today()),
    "items": [{"product_name": "Jaket Uji Alami", "sku": sku, "size": "L",
               "color": "Abu", "qty": 100}]})
poi = db.po_items.find_one({"po_id": po["id"]}, {"_id": 0})

print(f"\n{C}2. Kirim material ke vendor → terima → inspeksi{X}")
st, vs = call("POST", "/api/vendor-shipments", {
    "shipment_number": f"UJI-SJM-{S}", "vendor_id": vendor_id, "po_id": po["id"],
    "po_number": po["po_number"], "shipment_date": str(date.today()), "shipment_type": "NORMAL",
    "items": [{"po_id": po["id"], "po_item_id": poi["id"], "sku": sku,
               "product_name": poi.get("product_name", ""), "size": poi.get("size", ""),
               "color": poi.get("color", ""), "qty_sent": 100}]})
vs_id = vs.get("id")
call("PUT", f"/api/vendor-shipments/{vs_id}", {"status": "Received"})
vsi = db.vendor_shipment_items.find_one({"shipment_id": vs_id}, {"_id": 0})
call("POST", "/api/vendor-material-inspections", {
    "shipment_id": vs_id, "vendor_id": vendor_id, "inspection_date": str(date.today()),
    "overall_notes": "uji alami",
    "items": [{"shipment_item_id": vsi["id"], "sku": sku, "ordered_qty": 100,
               "received_qty": 100, "missing_qty": 0}]})

print(f"\n{C}3. Buat job produksi + laporkan produksi 100 pcs{X}")
st, job = call("POST", "/api/production-jobs",
               {"vendor_shipment_id": vs_id, "vendor_id": vendor_id, "po_id": po["id"]})
ji = db.production_job_items.find_one({"job_id": job["id"]}, {"_id": 0})
call("POST", "/api/production-progress", {"job_item_id": ji["id"], "completed_quantity": 100,
                                          "progress_date": str(date.today())})
print(f"    status PO sekarang: {db.production_pos.find_one({'id': po['id']}, {'_id': 0, 'status': 1})}")

print(f"\n{C}4. DA terima FG dari CMT: 100 dikirim, 100 lolos QC{X}")
st, rc = call("POST", "/api/prod/cmt-receipts", {
    "cmt_name": vendor_name, "cmt_vendor_id": vendor_id, "po_id": po["id"],
    "po_number": po["po_number"], "business_type": "maklon", "notes": "uji alami"})
call("POST", f"/api/prod/cmt-receipts/{rc['id']}/lines", {
    "sku_code": sku, "product_name": ji.get("product_name", ""), "size": ji.get("size", ""),
    "color": ji.get("color", ""), "qty_expected": 100, "qty_shipped_by_cmt": 100,
    "qty_actual": 100, "reject_qty": 0, "po_item_id": ji["po_item_id"], "job_item_id": ji["id"]})
call("POST", f"/api/prod/cmt-receipts/{rc['id']}/complete-qc", {})
print(f"    stok FG {sku} setelah QC = {fg(sku)} pcs")

print(f"\n{C}5. Kirim 100 pcs ke buyer (surat jalan){X}")
st, bs = call("POST", "/api/buyer-shipments", {
    "receiver_type": "buyer", "source_receipt_ids": [rc["id"]], "vendor_id": vendor_id,
    "shipment_date": str(date.today()), "notes": "uji alami",
    "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
               "product_name": ji.get("product_name", ""), "qty_shipped": 100}]})
bsi = db.buyer_shipment_items.find_one({"shipment_id": bs.get("id")}, {"_id": 0})
po_now = db.production_pos.find_one({"id": po["id"]}, {"_id": 0, "status": 1})
print(f"    surat jalan {bs.get('shipment_number')} · status PO = {po_now.get('status')} "
      f"· stok FG {sku} = {fg(sku)} pcs")
if fg(sku) == 100:
    notes.append("Stok FG TIDAK berkurang saat 100 pcs dikirim ke buyer "
                 "(hanya bertambah saat terima dari CMT) → nilai stok gudang FG menggelembung")

print(f"\n{C}6. Buyer ternyata hanya menerima 95 pcs (selisih 5){X}")
st, recv = call("PUT", f"/api/buyer-shipment-items/{bsi['id']}/received",
                {"qty_received": 95, "reason": "uji: buyer hitung kurang 5"})
print(f"    variance API = {recv.get('variance')} · auto-close = "
      f"{json.dumps(recv.get('po_auto_close'), ensure_ascii=False)}")
st, ful = call("GET", f"/api/production-pos/{po['id']}/fulfillment")
print(f"    fulfillment: ordered={ful.get('total_ordered')} shipped={ful.get('total_shipped')} "
      f"received={ful.get('total_received')} short={ful.get('qty_short')} "
      f"is_full={ful.get('is_full')} status={ful.get('status')}")

print(f"\n{C}7. Tutup-kurang PO (close-short) — apakah muncul nota kredit / AR disesuaikan?{X}")
st, cs = call("POST", f"/api/production-pos/{po['id']}/close-short", {
    "closed_reason": "buyer_material_shortage", "reason": "uji kurang 5 pcs",
    "notes": "uji", "confirm": True})
print(f"    hasil: {json.dumps(cs, ensure_ascii=False)[:700]}")
cn = list(db.dewi_maklon_credit_notes.find({"po_id": po["id"]}, {"_id": 0, "credit_note_number": 1,
                                                                "total_amount": 1, "status": 1}))
mirror = db.dewi_maklon_pos.find_one({"id": po["id"]}, {"_id": 0, "ar_invoice_id": 1})
ar = db.rahaza_ar_invoices.find_one({"id": (mirror or {}).get("ar_invoice_id")},
                                    {"_id": 0, "invoice_number": 1, "status": 1, "total_amount": 1}) if mirror else None
print(f"    nota kredit: {cn or 'TIDAK ADA'}")
print(f"    invoice AR terkait: {ar or 'TIDAK ADA'}")
print(f"    status PO akhir: {db.production_pos.find_one({'id': po['id']}, {'_id': 0, 'status': 1, 'closed_reason': 1})}")

print(f"\n{C}8. Apakah 5 pcs yang tidak sampai bisa dikirim ulang?{X}")
st, again = call("POST", "/api/buyer-shipments", {
    "receiver_type": "buyer", "source_receipt_ids": [rc["id"]], "vendor_id": vendor_id,
    "shipment_date": str(date.today()),
    "items": [{"po_item_id": ji["po_item_id"], "job_item_id": ji["id"], "sku": sku,
               "qty_shipped": 5}]}, ok=(200, 201))
if st >= 400:
    notes.append("5 pcs selisih TIDAK bisa dikirim ulang: pagar source-receipt memakai qty_shipped "
                 "dispatch sebelumnya, bukan qty_received → kapasitas tidak terbuka "
                 f"(pesan: {str(again.get('detail'))[:120]})")

print(f"\n{C}{B}{'═' * 78}\nCATATAN TEMUAN\n{'═' * 78}{X}")
if not notes:
    print(f"  {G}tidak ada temuan{X}")
for i, n in enumerate(notes, 1):
    print(f"  {R}{i}.{X} {n}")
sys.exit(0)
