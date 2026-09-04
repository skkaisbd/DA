#!/usr/bin/env python3
"""verify_ia_c_backend_fixes.py — bukti 2 perbaikan backend FASE IA-C (self-cleaning).

Dua perbaikan ini TIDAK tercakup ronde testing_agent iteration_179, jadi diuji di sini
lewat ALUR API NYATA, lalu SELURUH artefaknya dihapus (termasuk stok FG yang bertambah
dan tagihan yang lahir) supaya data demo tidak melenceng.

  FIX-1  `POST /api/prod/cmt-receipts/{id}/lines` menghitung ulang total header.
         Dulu hanya PUT yang menghitung ⇒ `total_shipped_by_cmt` tinggal 0 ⇒ SETIAP
         tagihan CMT lahir dengan `variance_flagged=True` (alarm palsu 100%).

  FIX-2  Job internal MEWARISI pelaksana dari PO. Dulu dipatok "Produksi Internal"
         ⇒ PO internal yang dijahitkan mitra CMT kehilangan identitas pelaksana
         (Tracking Produksi menumpuk semuanya di satu baris; Portal Vendor mitra kosong).
         Diuji dua arah: PO dengan vendor → job ikut vendor; PO tanpa vendor → tetap
         "Produksi Internal" (tidak ada regresi).

Jalankan:  cd /app && python3 tests/verify_ia_c_backend_fixes.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone

sys.path.insert(0, "/app/scripts/lib")
from gr_common import db_handle  # noqa: E402

API = os.environ.get("API_BASE", "http://localhost:8001")
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
TAG = "QA-IA-C"
PASS, FAIL = [], []


def call(method, path, token=None, body=None):
    req = urllib.request.Request(f"{API}{path}",
                                 data=json.dumps(body).encode() if body is not None else None,
                                 method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail else ""))


def main():  # noqa: C901
    db = db_handle()
    st, res = call("POST", "/api/auth/login", None, ADMIN)
    if st != 200:
        raise SystemExit(f"login gagal {st}")
    tok = res["token"]
    now = datetime.now(timezone.utc).isoformat()
    created = {"receipts": [], "pos": [], "jobs": []}

    try:
        # ── FIX-1 ────────────────────────────────────────────────────────────
        st, rc = call("POST", "/api/prod/cmt-receipts", tok, {
            "cmt_name": "CV Jahit Mitra CMT", "cmt_vendor_id": "demo-vn-jmc",
            "po_id": "po-int-demo-4", "po_number": "PO-INT-DEMO-4",
            "business_type": "internal", "delivery_note": TAG, "notes": TAG})
        check("FIX-1 buat penerimaan CMT", st == 201, f"HTTP {st}")
        rid = rc["id"]
        created["receipts"].append(rid)
        st, _ = call("POST", f"/api/prod/cmt-receipts/{rid}/lines", tok, {
            "sku_code": "DA-TS01-ALLSIZE", "product_name": "Kaos Basic Dewi Aditya",
            "color": "Hitam", "size": "ALLSIZE", "qty_expected": 10,
            "qty_shipped_by_cmt": 10, "qty_actual": 9, "reject_qty": 1,
            "reject_reason": TAG, "po_item_id": "po-int-demo-4-i1"})
        check("FIX-1 tambah baris", st == 201, f"HTTP {st}")

        hdr = db.cmt_receipts.find_one({"id": rid}, {"_id": 0})
        check("FIX-1 total header dihitung saat POST /lines",
              (hdr.get("total_shipped_by_cmt"), hdr.get("total_actual"), hdr.get("total_rejected")) == (10, 9, 1),
              f"shipped={hdr.get('total_shipped_by_cmt')} actual={hdr.get('total_actual')} "
              f"reject={hdr.get('total_rejected')} (sebelum perbaikan: 0/0/0)")

        call("POST", f"/api/prod/cmt-receipts/{rid}/submit", tok)
        st, ap = call("POST", f"/api/prod/cmt-receipts/{rid}/approve", tok)
        check("FIX-1 approve penerimaan", st == 200, f"HTTP {st}")
        pay = db.dewi_cmt_payments.find_one({"source_receipt_id": rid}, {"_id": 0})
        check("FIX-1 tagihan TIDAK ditandai varian palsu",
              pay is not None and pay.get("variance_flagged") is False,
              f"variance_flagged={pay.get('variance_flagged') if pay else 'tagihan tak lahir'}")
        check("FIX-1 nilai tagihan = qty_actual × tarif",
              pay is not None and float(pay.get("subtotal", 0)) == 9 * 15000.0,
              f"subtotal={pay.get('subtotal') if pay else '-'} (harus 135.000)")

        # ── FIX-2 ────────────────────────────────────────────────────────────
        for tag, vendor in (("VEND", ("demo-vn-jmc", "CV Jahit Mitra CMT")), ("SELF", (None, None))):
            pid = f"qa-ia-c-po-{tag.lower()}-{uuid.uuid4().hex[:6]}"
            created["pos"].append(pid)
            db.production_pos.insert_one({
                "id": pid, "po_number": f"{TAG}-PO-{tag}", "customer_name": "Gudang FG Sendiri",
                "vendor_id": vendor[0], "vendor_name": vendor[1] or "Produksi Internal",
                "business_type": "internal", "status": "Confirmed", "po_date": now,
                "created_by": TAG, "created_at": now, "updated_at": now})
            db.po_items.insert_one({
                "id": f"{pid}-i1", "po_id": pid, "po_number": f"{TAG}-PO-{tag}",
                "product_name": "Kaos Basic Dewi Aditya", "sku": "DA-TS01-ALLSIZE",
                "size": "ALLSIZE", "color": "Hitam", "qty": 5, "serial_number": f"{TAG}-{tag}",
                "cmt_price_snapshot": 15000.0, "created_at": now})
            st, job = call("POST", "/api/production-jobs", tok, {"po_id": pid})
            if st == 201:
                created["jobs"].append(job["id"])
            expect = vendor[1] or "Produksi Internal"
            check(f"FIX-2 job dari PO {tag} → pelaksana '{expect}'",
                  st == 201 and job.get("vendor_name") == expect and job.get("vendor_id") == vendor[0],
                  f"HTTP {st}, vendor_name={job.get('vendor_name') if st == 201 else job}")
    finally:
        # ── BERSIH-BERSIH TOTAL ──────────────────────────────────────────────
        for rid in created["receipts"]:
            lines = list(db.cmt_receipt_lines.find({"receipt_id": rid}, {"_id": 0}))
            for ln in lines:   # kembalikan stok FG yang bertambah saat approve
                qty = int(ln.get("qty_actual") or 0)
                mv = db.rahaza_fg_movements.find_one({"ref_id": rid, "sku_code": ln.get("sku_code")})
                if mv and qty:
                    db.rahaza_material_stock.update_one(
                        {"material_id": mv["material_id"], "inventory_category": "fg_internal"},
                        {"$inc": {"qty": -qty, "total_qty": -qty, "quantity": -qty,
                                  "available_quantity": -qty}})
            db.rahaza_fg_movements.delete_many({"ref_id": rid})
            db.cmt_receipt_lines.delete_many({"receipt_id": rid})
            db.dewi_cmt_payments.delete_many({"source_receipt_id": rid})
            db.cmt_receipts.delete_one({"id": rid})
        for jid in created["jobs"]:
            db.production_job_items.delete_many({"job_id": jid})
            db.rahaza_material_issues.delete_many({"job_id": jid})
            db.production_jobs.delete_one({"id": jid})
        for pid in created["pos"]:
            db.po_items.delete_many({"po_id": pid})
            db.dewi_accessory_requests.delete_many({"po_id": pid})
            db.production_pos.delete_one({"id": pid})
        leftovers = (db.cmt_receipts.count_documents({"delivery_note": TAG})
                     + db.production_pos.count_documents({"po_number": {"$regex": f"^{TAG}"}})
                     + db.dewi_cmt_payments.count_documents({"notes": {"$regex": TAG}}))
        print(f"\n  bersih-bersih: sisa artefak {TAG} = {leftovers}")

    print(f"\n  RINGKASAN: {len(PASS)} PASS / {len(FAIL)} FAIL")
    for f in FAIL:
        print(f"    ✗ {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
