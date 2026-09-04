#!/usr/bin/env python3
"""seed_demo_cmt_billing_internal.py — data demo pintu **Invoice (Tagihan CMT)** Produksi.

KENAPA ADA (FASE IA-C, 2026-07-26)
──────────────────────────────────
Arahan owner: "Produksi & Maklon flownya sama — dua-duanya dilempar ke CMT; bedanya
buyer-nya DA sendiri". Tapi seeder demo lama (`tests/seed_demo_produksi_maklon.py`)
membuat 3 PO internal yang SELURUHNYA dikerjakan sendiri (vendor_id=None, tarif CMT 0),
sehingga:
  · `cmt_receipts`      = 0 dokumen  → pintu "Terima FG dari CMT" kosong
  · `dewi_cmt_payments` = 0 dokumen  → pintu "Invoice" kosong

Script ini melengkapi demo dengan SATU PO internal yang **dijahitkan ke mitra CMT**
(pola nyata DA), lalu menjalankan **alur asli lewat HTTP API** — bukan menyuntik
dokumen tagihan langsung ke DB:

    PO internal (vendor CMT + tarif jahit)
      → POST /api/prod/cmt-receipts            (Terima FG dari CMT — draft)
      → POST .../lines                          (hitung fisik: actual & reject)
      → POST .../submit → POST .../approve      (stok FG masuk + AP matang)
      → dewi_cmt_payments status draft          (pintu Invoice terisi)
      → POST /api/dewi/maklon/finance/cmt-payments/{id}/post-ap   (1 tagihan diposting GL)

Hasil: pintu Invoice punya 2 baris — 1 BELUM diposting (tombol "Posting AP" bisa dicoba)
dan 1 SUDAH punya jurnal GL (kolom "Jurnal GL" terisi). Nilainya dihitung dari
qty_actual × cmt_price_snapshot, bukan angka karangan.

IDEMPOTEN: dijalankan ulang tidak menggandakan apa pun (kunci: po_number PO-INT-DEMO-4
dan delivery_note bertanda DEMO-CMT-BILL-1/2).

Jalankan:  cd /app && python3 scripts/seed_demo_cmt_billing_internal.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, "/app/scripts/lib")
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
ADMIN = {"email": os.environ.get("ADMIN_EMAIL", "admin@garment.com"),
         "password": os.environ.get("ADMIN_PASS", "Admin@123")}

PO_ID = "po-int-demo-4"
PO_NUMBER = "PO-INT-DEMO-4"
ITEM_ID = "po-int-demo-4-i1"
# FASE 22 — JANGAN hardcode id vendor. `tests/seed_demo_produksi_maklon.py`
# MENGADOPSI id master yang sudah ada (mis. `mk-vendor-demo-1` buatan
# /api/seed/maklon-full) supaya tidak menabrak unique index `code`. Kalau di sini
# id-nya dipaku "demo-vn-jmc", `production_jobs.vendor_id` jadi YATIM: portal
# vendor `cmtvendor@dewiaditya.id` (tertaut ke id master yang benar) TIDAK melihat
# job ini — cacat relasi yang lolos karena semua endpoint tetap HTTP 200.
VENDOR_CODE = "JMC"
VENDOR_ID = "demo-vn-jmc"           # fallback; ditimpa oleh resolve_vendor()
VENDOR_NAME = "CV Jahit Mitra CMT"


def resolve_vendor(db):
    """Ambil vendor CMT dari master (by code) → id yang SAH."""
    global VENDOR_ID, VENDOR_NAME
    v = (db.vendor_partners.find_one({"code": VENDOR_CODE}, {"_id": 0, "id": 1, "name": 1, "garment_name": 1})
         or db.vendor_partners.find_one({"name": VENDOR_NAME}, {"_id": 0, "id": 1, "name": 1, "garment_name": 1}))
    if v and v.get("id"):
        if v["id"] != VENDOR_ID:
            print(f"  vendor {VENDOR_CODE} dipakai dari master: {v['id']}")
        VENDOR_ID = v["id"]
        VENDOR_NAME = v.get("garment_name") or v.get("name") or VENDOR_NAME
    else:
        print(f"  ! vendor {VENDOR_CODE} tidak ada di vendor_partners — jalankan seed master dulu")
    return VENDOR_ID, VENDOR_NAME
SKU = "DA-TS01-ALLSIZE"
QTY = 150
CMT_RATE = 15000.0
PRODUCED = 145                       # 80 + 65 pcs yang benar-benar diterima DA
MARK1 = "DEMO-CMT-BILL-1"
MARK2 = "DEMO-CMT-BILL-2"


def now():
    return datetime.now(timezone.utc).isoformat()


def call(method, path, token=None, body=None):
    url = f"{API}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


def ensure_po(db):
    """PO internal yang dijahitkan ke mitra CMT (idempoten)."""
    t = now()
    po = {
        "id": PO_ID, "po_number": PO_NUMBER, "customer_name": "Gudang FG Sendiri",
        "buyer_id": None, "vendor_id": VENDOR_ID, "vendor_name": VENDOR_NAME,
        "po_date": t, "deadline": None, "delivery_deadline": None,
        "status": "Confirmed", "business_type": "internal",
        "notes": "Produksi internal dijahitkan ke mitra CMT (tarif jasa jahit per pcs)",
        "created_by": "Andi Pratama (Admin Produksi)", "created_at": t, "updated_at": t,
    }
    db.production_pos.update_one({"id": PO_ID}, {"$set": po}, upsert=True)
    item = {
        "id": ITEM_ID, "po_id": PO_ID, "po_number": PO_NUMBER,
        "product_id": None, "product_name": "Kaos Basic Dewi Aditya",
        "model_id": "demo-model-da-ts01", "size": "ALLSIZE", "color": "Hitam",
        "sku": SKU, "qty": QTY, "serial_number": "SN-INT4-A",
        "selling_price_snapshot": 0.0, "cmt_price_snapshot": CMT_RATE,
        "vendor_id": VENDOR_ID, "vendor_name": VENDOR_NAME, "created_at": t,
    }
    db.po_items.update_one({"id": ITEM_ID}, {"$set": item}, upsert=True)
    print(f"  PO {PO_NUMBER} → {VENDOR_NAME}, {QTY} pcs @ Rp {CMT_RATE:,.0f}/pcs  ok")


def ensure_job(db, token):
    """Production Job untuk PO ini + progres jahit yang dilaporkan mitra CMT (idempoten).

    Job dibuat lewat API asli (`POST /api/production-jobs`) supaya pewarisan pelaksana
    dari PO (FASE IA-C) ikut teruji. Progres ditulis langsung ke DB — pola yang sama
    dipakai seeder demo lain — karena jalur progres internal digate Material Issue
    gudang yang tidak relevan untuk pekerjaan yang dijahit mitra CMT.
    """
    job = db.production_jobs.find_one({"po_id": PO_ID}, {"_id": 0})
    if not job:
        st, job = call("POST", "/api/production-jobs", token, {"po_id": PO_ID})
        if st != 201:
            raise SystemExit(f"gagal buat job: {st} {job}")
        print(f"  Job {job.get('job_number')} → pelaksana {job.get('vendor_name')} ok")
    ji = db.production_job_items.find_one({"job_id": job["id"]}, {"_id": 0})
    if ji and int(ji.get("produced_qty", 0) or 0) < PRODUCED:
        db.production_job_items.update_one({"id": ji["id"]}, {"$set": {"produced_qty": PRODUCED}})
        db.production_progress.update_one(
            {"job_item_id": ji["id"], "notes": "Lapor jahit mitra CMT (demo)"},
            {"$set": {"job_id": job["id"], "job_item_id": ji["id"], "sku": SKU,
                      "product_name": "Kaos Basic Dewi Aditya", "size": "ALLSIZE", "color": "Hitam",
                      "progress_date": now(), "completed_quantity": PRODUCED,
                      "recorded_by": VENDOR_NAME, "created_at": now()}},
            upsert=True)
        print(f"  Progres jahit mitra CMT: {PRODUCED}/{QTY} pcs tercatat ok")
    return job


def make_receipt(token, mark, qty_actual, reject, note):
    """Jalankan alur Terima FG dari CMT lewat API (draft → lines → submit → approve)."""
    st, doc = call("POST", "/api/prod/cmt-receipts", token, {
        "cmt_name": VENDOR_NAME, "cmt_vendor_id": VENDOR_ID,
        "po_id": PO_ID, "po_number": PO_NUMBER, "business_type": "internal",
        "delivery_note": mark, "notes": note,
    })
    if st != 201:
        raise SystemExit(f"gagal buat cmt_receipt: {st} {doc}")
    rid = doc["id"]
    st, ln = call("POST", f"/api/prod/cmt-receipts/{rid}/lines", token, {
        "sku_code": SKU, "product_name": "Kaos Basic Dewi Aditya",
        "color": "Hitam", "size": "ALLSIZE",
        "qty_expected": qty_actual + reject, "qty_shipped_by_cmt": qty_actual + reject,
        "qty_actual": qty_actual, "reject_qty": reject,
        "reject_reason": "Jahitan tidak rapi" if reject else "",
        "po_item_id": ITEM_ID,
    })
    if st != 201:
        raise SystemExit(f"gagal tambah baris: {st} {ln}")
    st, _ = call("POST", f"/api/prod/cmt-receipts/{rid}/submit", token)
    if st != 200:
        raise SystemExit(f"gagal submit: {st}")
    st, res = call("POST", f"/api/prod/cmt-receipts/{rid}/approve", token)
    if st != 200:
        raise SystemExit(f"gagal approve: {st} {res}")
    ap = res.get("ap_mature") or {}
    print(f"  {res.get('receipt_code')} approved — actual {qty_actual} pcs, reject {reject} pcs "
          f"→ tagihan {ap.get('payment_code')} Rp {float(ap.get('amount', 0)):,.0f}")
    return ap.get("payment_id")


def main():
    db = db_handle()
    print("SEED DEMO — Tagihan CMT untuk PO internal")
    st, res = call("POST", "/api/auth/login", None, ADMIN)
    if st != 200:
        raise SystemExit(f"login admin gagal ({st}) — backend hidup? {res}")
    token = res["token"]

    resolve_vendor(db)
    ensure_po(db)
    ensure_job(db, token)

    existing = list(db.cmt_receipts.find({"delivery_note": {"$in": [MARK1, MARK2]}}, {"_id": 0, "id": 1}))
    if existing:
        n = db.dewi_cmt_payments.count_documents({"po_id": PO_ID})
        print(f"  Sudah ada {len(existing)} penerimaan demo & {n} tagihan — idempoten, tidak diulang.")
        return 0

    make_receipt(token, MARK1, qty_actual=80, reject=2,
                 note="Kiriman parsial pertama dari mitra CMT")
    pid2 = make_receipt(token, MARK2, qty_actual=65, reject=3,
                        note="Kiriman kedua — pelunasan PO")

    if pid2:
        st, r = call("POST", f"/api/dewi/maklon/finance/cmt-payments/{pid2}/post-ap", token)
        print(f"  Posting AP tagihan ke-2 → HTTP {st} {r if st != 200 else r.get('je_number')}")

    total = db.dewi_cmt_payments.count_documents({"po_id": PO_ID})
    print(f"  SELESAI — {total} tagihan CMT untuk {PO_NUMBER} siap tampil di pintu Invoice.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
