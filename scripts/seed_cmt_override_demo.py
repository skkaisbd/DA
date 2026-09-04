#!/usr/bin/env python3
"""Seed IDEMPOTEN — data demo **Portal CMT Override** (Input Vendor CMT).

MENGAPA BERKAS INI ADA
----------------------
Fitur "Input Vendor CMT" hanya bisa dinilai kalau ADA vendor yang memang tidak
memakai sistem DAN ada pekerjaan yang menunggu diisi. Pada environment hasil
`bootstrap.sh`, master CMT (`vendor_partners`) hanya berisi **satu** vendor demo
— dan vendor itu justru PUNYA akun portal aktif. Akibatnya:

  · layar pemilih vendor hanya menampilkan satu kartu, sehingga kasus utama
    (vendor TANPA akun portal) tidak pernah terlihat;
  · peringatan "hati-hati dobel input" (keputusan owner 5a) tidak bisa
    dibandingkan dengan kasus yang tidak memicu peringatan;
  · 11 tab modul dibuka dalam keadaan kosong, jadi tidak ada yang bisa diuji
    lewat layar — persis keluhan "fiturnya ada tapi tabelnya kosong".

Skrip ini membuat dua vendor demo yang sengaja BERBEDA sifatnya:

  A. **CV Tanpa Sistem CMT** — TIDAK punya akun portal. Ini kasus nyata yang
     jadi alasan fitur override dibuat. Diberi PO maklon + surat jalan material
     berstatus `Sent`, sehingga staf bisa langsung: terima → inspeksi (ada
     barang kurang) → minta tambahan → buka job → isi progress → deklarasi kirim.
  B. **CV Punya Akun CMT** — punya akun portal AKTIF. Memilih vendor ini memicu
     peringatan dobel input, jadi jalur peringatan bisa dilihat apa adanya.

Sifat:
  · IDEMPOTEN — dijalankan berulang tidak menduplikasi (dicek per kode vendor
    dan per nomor dokumen);
  · memakai **API sungguhan**, bukan tulis langsung ke Mongo, supaya penomoran
    dokumen, jejak aktivitas, dan turunan (mirror PO maklon, AR invoice) lahir
    sama seperti dipakai pengguna;
  · TIDAK mengisi progress/deklarasi apa pun — itu justru pekerjaan yang harus
    dikerjakan staf lewat layar override (kalau di-seed, fiturnya tidak teruji);
  · `--cleanup` membuang SELURUH jejaknya, termasuk turunan uang (AR invoice
    maklon + mirror `dewi_maklon_pos`) supaya tidak meninggalkan piutang palsu.

Pakai:
    python3 /app/scripts/seed_cmt_override_demo.py
    python3 /app/scripts/seed_cmt_override_demo.py --cleanup
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

import requests

BASE = os.environ.get("POC_BASE", "http://localhost:8001")
API = f"{BASE}/api"
CLEANUP = "--cleanup" in sys.argv

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

# Penanda demo — dipakai untuk idempotensi & pembersihan.
TAG = "seed_cmt_override_demo"
V_A = {"code": "CMTNS", "name": "CV Tanpa Sistem CMT"}
V_B = {"code": "CMTPA", "name": "CV Punya Akun CMT"}
PO_NUMBER = "PO-CMTOV-DEMO-1"
SJ_NUMBER = "SJ-CMTOV-DEMO-1"
ACC_EMAIL = "cmt.punyaakun@dewiaditya.id"
ACC_PASSWORD = "Vendor@123"

G, R, Y, X = "\033[92m", "\033[91m", "\033[93m", "\033[0m"


def ok(m): print(f"  {G}✓{X} {m}")
def warn(m): print(f"  {Y}!{X} {m}")
def err(m): print(f"  {R}✗{X} {m}")


def login() -> str:
    r = requests.post(f"{API}/auth/login", timeout=30,
                      json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    return r.json()["token"]


def H(tok): return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}


def get_db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URL)[DB_NAME]


# ═══════════════════════════════════════════════════════════════════════════
def do_cleanup(tok):
    print("Membersihkan data demo Portal CMT Override…")
    db = get_db()
    vids = [v["id"] for v in db.vendor_partners.find(
        {"code": {"$in": [V_A["code"], V_B["code"]]}}, {"_id": 0, "id": 1})]
    pos = [p["id"] for p in db.production_pos.find({"po_number": PO_NUMBER}, {"_id": 0, "id": 1})]
    ships = [s["id"] for s in db.vendor_shipments.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    jobs = [j["id"] for j in db.production_jobs.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    insps = [i["id"] for i in db.vendor_material_inspections.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    bss = [b["id"] for b in db.buyer_shipments.find(
        {"vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []
    rcvs = [c["id"] for c in db.cmt_receipts.find(
        {"cmt_vendor_id": {"$in": vids}}, {"_id": 0, "id": 1})] if vids else []

    ops = [
        ("production_progress", {"job_id": {"$in": jobs}}),
        ("production_job_items", {"job_id": {"$in": jobs}}),
        ("production_jobs", {"id": {"$in": jobs}}),
        ("vendor_material_inspection_items", {"inspection_id": {"$in": insps}}),
        ("vendor_material_inspections", {"id": {"$in": insps}}),
        ("vendor_shipment_items", {"shipment_id": {"$in": ships}}),
        ("accessory_shipment_items", {"shipment_id": {"$in": ships}}),
        ("vendor_shipments", {"id": {"$in": ships}}),
        ("material_requests", {"vendor_id": {"$in": vids}}),
        ("production_variances", {"vendor_id": {"$in": vids}}),
        ("reminders", {"vendor_id": {"$in": vids}}),
        ("dewi_cmt_component_requests", {"vendor_id": {"$in": vids}}),
        ("buyer_shipment_items", {"shipment_id": {"$in": bss}}),
        ("buyer_shipments", {"id": {"$in": bss}}),
        ("cmt_receipt_lines", {"receipt_id": {"$in": rcvs}}),
        ("cmt_receipts", {"id": {"$in": rcvs}}),
        ("dewi_cmt_payments", {"vendor_id": {"$in": vids}}),
        ("po_accessories", {"po_id": {"$in": pos}}),
        ("po_items", {"po_id": {"$in": pos}}),
        ("dewi_maklon_bom", {"po_id": {"$in": pos}}),
        # UANG: mirror PO maklon + AR invoice turunannya WAJIB ikut dibuang,
        # kalau tidak akan tertinggal piutang yatim di laporan Keuangan.
        ("rahaza_ar_invoices", {"linked_maklon_po_id": {"$in": pos}}),
        ("dewi_maklon_pos", {"production_po_id": {"$in": pos}}),
        ("production_pos", {"id": {"$in": pos}}),
        ("users", {"email": ACC_EMAIL}),
        ("vendor_partners", {"id": {"$in": vids}}),
    ]
    total = 0
    for coll, q in ops:
        try:
            n = db[coll].delete_many(q).deleted_count
            if n:
                total += n
                print(f"    - {coll}: {n}")
        except Exception as e:  # noqa: BLE001
            warn(f"{coll}: {e}")
    ok(f"{total} dokumen demo dihapus")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
def main() -> int:
    try:
        tok = login()
    except Exception as e:  # noqa: BLE001
        err(f"login admin gagal: {e}")
        return 1
    h = H(tok)

    if CLEANUP:
        return do_cleanup(tok)

    print("Seed data demo Portal CMT Override (Input Vendor CMT)…")
    db = get_db()

    # ── 1. Dua vendor CMT dengan sifat sengaja berbeda ────────────────────────
    vendor_ids = {}
    for spec, note in (
        (V_A, "Vendor CMT yang TIDAK memakai sistem — datanya diisi staf DA "
              "lewat pintu Input Vendor CMT."),
        (V_B, "Vendor CMT yang PUNYA akun portal aktif — memilihnya di pintu "
              "Input Vendor CMT memicu peringatan dobel input."),
    ):
        existing = db.vendor_partners.find_one({"code": spec["code"]}, {"_id": 0, "id": 1})
        if existing:
            vendor_ids[spec["code"]] = existing["id"]
            ok(f"vendor '{spec['name']}' sudah ada — dilewati")
            continue
        r = requests.post(f"{API}/vendor-portal/partners", headers=h, timeout=30, json={
            "name": spec["name"], "code": spec["code"],
            "contact_name": "Bagian Produksi", "contact_phone": "0271-000000",
            "address": "Sragen, Jawa Tengah", "notes": f"{note} [{TAG}]",
            "capacity_pcs": 300, "capacity_note": "2 lini jahit",
        })
        if r.status_code != 200:
            err(f"gagal membuat vendor {spec['name']}: HTTP {r.status_code} {r.text[:180]}")
            return 1
        vendor_ids[spec["code"]] = r.json()["id"]
        ok(f"vendor '{spec['name']}' dibuat")

    va, vb = vendor_ids[V_A["code"]], vendor_ids[V_B["code"]]

    # ── 2. Akun portal AKTIF hanya untuk vendor B (pemicu peringatan 5a) ──────
    if db.users.find_one({"email": ACC_EMAIL}, {"_id": 0, "id": 1}):
        ok("akun portal vendor B sudah ada — dilewati")
    else:
        r = requests.post(f"{API}/vendor-portal/accounts", headers=h, timeout=30, json={
            "email": ACC_EMAIL, "name": f"{V_B['name']} (Vendor)",
            "password": ACC_PASSWORD, "partner_id": vb})
        if r.status_code in (200, 201):
            ok(f"akun portal vendor B dibuat ({ACC_EMAIL} / {ACC_PASSWORD})")
        else:
            warn(f"akun portal vendor B gagal: HTTP {r.status_code} {r.text[:160]}")
    # login sekali supaya `last_login_at` terisi oleh SISTEM (bukan ditulis tangan),
    # sehingga peringatan bisa menyebut tanggal login terakhir yang sah.
    try:
        rl = requests.post(f"{API}/auth/login", timeout=30,
                           json={"email": ACC_EMAIL, "password": ACC_PASSWORD})
        if rl.status_code == 200:
            ok("akun vendor B login sekali → last_login_at terisi")
        else:
            warn(f"login akun vendor B gagal (peringatan tanpa tanggal): HTTP {rl.status_code}")
    except Exception as e:  # noqa: BLE001
        warn(f"login akun vendor B gagal: {e}")

    # ── 3. PO maklon + surat jalan material untuk vendor A ───────────────────
    po = db.production_pos.find_one({"po_number": PO_NUMBER}, {"_id": 0, "id": 1})
    if po:
        po_id = po["id"]
        ok(f"PO {PO_NUMBER} sudah ada — dilewati")
    else:
        deadline = (datetime.now(timezone.utc) + timedelta(days=10)).date().isoformat()
        r = requests.post(f"{API}/production-pos", headers=h, timeout=60, json={
            "po_number": PO_NUMBER, "business_type": "maklon", "vendor_id": va,
            "customer_name": "PT Buyer Demo Override", "status": "Confirmed",
            "po_date": datetime.now(timezone.utc).date().isoformat(),
            "deadline": deadline, "delivery_deadline": deadline,
            "notes": f"PO demo untuk pintu Input Vendor CMT [{TAG}]",
            "items": [
                {"product_name": "Kaos Polo Demo", "sku": "CMTOV-POLO-M", "size": "M",
                 "color": "Navy", "color_code": "NVY", "qty": 120,
                 "serial_number": "SN-CMTOV-01", "cmt_price_snapshot": 9000},
                {"product_name": "Kaos Polo Demo", "sku": "CMTOV-POLO-L", "size": "L",
                 "color": "Navy", "color_code": "NVY", "qty": 80,
                 "serial_number": "SN-CMTOV-02", "cmt_price_snapshot": 9000},
            ]})
        if r.status_code not in (200, 201):
            err(f"gagal membuat PO: HTTP {r.status_code} {r.text[:200]}")
            return 1
        po_id = r.json()["id"]
        ok(f"PO maklon {PO_NUMBER} dibuat (200 pcs, 2 varian)")

    if db.vendor_shipments.find_one({"shipment_number": SJ_NUMBER}, {"_id": 0, "id": 1}):
        ok(f"surat jalan {SJ_NUMBER} sudah ada — dilewati")
    else:
        items = list(db.po_items.find({"po_id": po_id}, {"_id": 0, "id": 1, "qty": 1}))
        r = requests.post(f"{API}/vendor-shipments", headers=h, timeout=60, json={
            "shipment_number": SJ_NUMBER, "vendor_id": va, "po_id": po_id,
            "shipment_type": "NORMAL",
            "shipment_date": datetime.now(timezone.utc).date().isoformat(),
            "notes": f"Kirim material ke vendor tanpa sistem [{TAG}]",
            "items": [{"po_id": po_id, "po_item_id": it["id"], "qty_sent": it["qty"]}
                      for it in items]})
        if r.status_code in (200, 201):
            ok(f"surat jalan material {SJ_NUMBER} dibuat (status Sent — menunggu diterima)")
        else:
            err(f"gagal membuat surat jalan: HTTP {r.status_code} {r.text[:200]}")
            return 1

    # ── 4. Reminder dari DA supaya Inbox Reminder tidak kosong ───────────────
    if db.reminders.find_one({"vendor_id": va}, {"_id": 0, "id": 1}):
        ok("reminder untuk vendor A sudah ada — dilewati")
    else:
        r = requests.post(f"{API}/reminders", headers=h, timeout=30, json={
            "vendor_id": va, "po_id": po_id, "po_number": PO_NUMBER,
            "reminder_type": "deadline", "priority": "high",
            "subject": "Kabari progress harian",
            "message": ("Mohon kabari progress jahit setiap hari. Kalau vendor tidak "
                        "bisa mengisi portal, staf DA mengisikan lewat pintu "
                        "Input Vendor CMT.")})
        if r.status_code in (200, 201):
            ok("reminder untuk vendor A dibuat (status pending → bisa dibalas staf)")
        else:
            warn(f"reminder gagal: HTTP {r.status_code} {r.text[:160]}")

    print()
    ok("SELESAI. Buka Portal Produksi → 'Input Vendor CMT'.")
    print(f"    · {V_A['name']}  → tanpa akun portal, 1 kiriman menunggu diterima")
    print(f"    · {V_B['name']}  → punya akun portal aktif ⇒ muncul peringatan dobel input")
    return 0


if __name__ == "__main__":
    sys.exit(main())
