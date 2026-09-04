"""Iteration 106 verification: Fix #3 cancel path (delete mirror, revert AR to draft,
re-generate idempotent) + LOW #3 maklon PO auto numbering.

Run serially:  python3 -m pytest tests/test_iter106_maklon.py -q -p no:cacheprovider -n 0
Tokens expected in /tmp/ta.tok (admin).
"""
import os
import re

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
if not BASE:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")

be = dotenv_values("/app/backend/.env")
MONGO_URL = os.environ.get("MONGO_URL") or be.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or be.get("DB_NAME")

ADMIN = open("/tmp/ta.tok").read().strip()
H = {"Authorization": f"Bearer {ADMIN}", "Content-Type": "application/json"}

PO = "po-mk-demo-2"
AR_NUM = "INV-MKL-2026-0001"

mongo = MongoClient(MONGO_URL)
db = mongo[DB_NAME]

state = {}


def _ar_rows():
    return list(db.rahaza_ar_invoices.find({"linked_maklon_po_id": PO}, {"_id": 0}))


def _dewi_rows():
    return list(db.dewi_maklon_invoices.find({"order_id": PO}, {"_id": 0}))


# ---------- 0) precondition: leave PO uninvoiced ----------
class TestFix3CancelPath:
    def test_00_precondition_clean(self):
        for d in _dewi_rows():
            requests.post(f"{BASE}/api/dewi/maklon/invoices/{d['id']}/cancel", headers=H, timeout=60)
        r = requests.post(f"{BASE}/api/production-pos/{PO}/sync-maklon-finance", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        assert _dewi_rows() == [], "mirror docs still present before test"

    # 1) eligible list
    def test_01_eligible_contains_demo2(self):
        r = requests.get(f"{BASE}/api/dewi/maklon/invoices/eligible", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        rows = r.json()
        rows = rows.get("items") if isinstance(rows, dict) else rows
        row = next((x for x in rows if x.get("id") == PO), None)
        assert row, f"{PO} not in eligible: {[x.get('id') for x in rows]}"
        state["eligible"] = row
        assert row["source"] == "engine_ar"
        assert row["billable"] is True
        assert float(row["total_received"]) == 60
        assert float(row["total_ordered"]) == 150
        assert row["ar_invoice_number"] == AR_NUM
        assert row["client_name"] == "PT Aruna Activewear"

    # 2) generate
    def test_02_generate(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H,
                          json={"order_id": PO, "tax_pct": 11}, timeout=90)
        assert r.status_code == 200, r.text
        inv = r.json()
        state["inv_id"] = inv["id"]
        ars = _ar_rows()
        assert len(ars) == 1, f"expected exactly 1 AR row, got {len(ars)}"
        ar = ars[0]
        assert inv["id"] == ar["id"]
        assert inv["invoice_number"] == ar["invoice_number"] == AR_NUM
        assert inv["status"] == "issued"
        assert sum(float(l["qty"]) for l in inv["lines"]) == 60, inv["lines"]
        assert float(inv["total_amount"]) == 799200.0, inv["total_amount"]
        assert float(inv["subtotal"]) == 720000.0
        assert float(ar["total_amount"]) == 799200.0
        assert ar["status"] == "issued"

    # 3) duplicate generate blocked
    def test_03_generate_again_blocked(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H,
                          json={"order_id": PO, "tax_pct": 11}, timeout=60)
        assert r.status_code == 400, r.text
        assert "sudah memiliki invoice" in r.text

    # 4) 360 view
    def test_04_po_360(self):
        r = requests.get(f"{BASE}/api/dewi/maklon/pos/{PO}/360", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        assert float(d["kpis"]["invoiced_amount"]) == 799200.0, d["kpis"]
        assert d["ar_invoice"]["invoice_number"] == AR_NUM

    # 5) payment then delete payment
    def test_05_payment_and_unpay(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/payments", headers=H,
                          json={"invoice_id": state["inv_id"], "amount": 100000, "method": "transfer"},
                          timeout=60)
        assert r.status_code in (200, 201), r.text
        pay = r.json()
        pay_id = pay.get("id") or (pay.get("payment") or {}).get("id")
        assert pay_id, pay
        ar = _ar_rows()[0]
        assert float(ar["amount_paid"]) == 100000.0, ar
        dw = _dewi_rows()[0]
        assert dw["status"] == "partial_paid", dw["status"]

        r = requests.delete(f"{BASE}/api/dewi/maklon/payments/{pay_id}", headers=H, timeout=60)
        assert r.status_code in (200, 204), r.text
        ar = _ar_rows()[0]
        assert float(ar["amount_paid"]) == 0.0, ar
        dw = _dewi_rows()[0]
        assert dw["status"] == "issued", dw["status"]

    # 6) cancel
    def test_06_cancel(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/{state['inv_id']}/cancel",
                          headers=H, timeout=90)
        assert r.status_code == 200, r.text
        assert r.json().get("ar_status") == "draft", r.text
        ars = _ar_rows()
        assert len(ars) == 1, f"AR duplicated/removed after cancel: {len(ars)}"
        ar = ars[0]
        assert ar["id"] == state["inv_id"]
        assert ar["invoice_number"] == AR_NUM
        assert ar["status"] == "draft", ar["status"]
        assert float(ar["amount_paid"]) == 0.0
        assert ar.get("issued_at") is None, ar.get("issued_at")
        assert _dewi_rows() == [], f"mirror not deleted: {_dewi_rows()}"

        r = requests.get(f"{BASE}/api/dewi/maklon/pos", headers=H, timeout=60)
        assert r.status_code == 200
        rows = r.json()
        rows = rows.get("items") if isinstance(rows, dict) else rows
        po = next(x for x in rows if x["id"] == PO)
        assert po["status"] == "partial_delivered", po["status"]
        assert po.get("ar_invoice_number") == AR_NUM, po.get("ar_invoice_number")

    # 7) regenerate — no DuplicateKeyError
    def test_07_regenerate_same_number(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H,
                          json={"order_id": PO, "tax_pct": 11}, timeout=90)
        assert r.status_code == 200, r.text
        inv = r.json()
        assert inv["id"] == state["inv_id"]
        assert inv["invoice_number"] == AR_NUM
        assert db.dewi_maklon_invoices.count_documents({"invoice_number": AR_NUM}) == 1
        assert db.rahaza_ar_invoices.count_documents({"invoice_number": AR_NUM}) == 1
        assert float(inv["total_amount"]) == 799200.0

    # 8) cleanup — leave uninvoiced
    def test_08_cleanup_cancel_and_sync(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/{state['inv_id']}/cancel",
                          headers=H, timeout=90)
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE}/api/production-pos/{PO}/sync-maklon-finance", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("mirror_status") == "partial_delivered", body
        assert _dewi_rows() == []
        assert len(_ar_rows()) == 1


# ---------- LOW #3: auto numbering for maklon PO ----------
class TestAutoNumbering:
    def test_10_policy_is_auto(self):
        r = requests.get(f"{BASE}/api/doc-number-policy?key=production_pos.po_number_maklon",
                         headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        d = d.get("policy", d) if isinstance(d, dict) else d
        assert d.get("mode") == "auto", d
        assert d.get("format") == "PO-MKL-{YYYY}{MM}-{SEQ:4}", d

    def test_11_create_without_number(self):
        payload = {
            "business_type": "maklon", "buyer_id": "demo-cl-aruna", "vendor_id": "demo-vn-jmc",
            "status": "Confirmed",
            "items": [{"product_name": "Test Auto Num", "sku_code": "TEST-AUTO-M", "size": "M",
                       "color": "Hitam", "qty": 10, "selling_price_snapshot": 20000,
                       "cmt_price_snapshot": 12000}],
        }
        r = requests.post(f"{BASE}/api/production-pos", headers=H, json=payload, timeout=90)
        assert r.status_code in (200, 201), r.text
        po = r.json()
        po = po.get("po", po)
        state["auto_po_id"] = po["id"]
        assert re.match(r"^PO-MKL-\d{6}-\d{4}$", po["po_number"]), po["po_number"]

    def test_12_manual_number_rejected(self):
        payload = {
            "business_type": "maklon", "buyer_id": "demo-cl-aruna", "vendor_id": "demo-vn-jmc",
            "status": "Confirmed", "po_number": "PO-MANUAL-TEST-106",
            "items": [{"product_name": "Test Manual Num", "sku_code": "TEST-AUTO-M", "size": "M",
                       "color": "Hitam", "qty": 1, "selling_price_snapshot": 20000,
                       "cmt_price_snapshot": 12000}],
        }
        r = requests.post(f"{BASE}/api/production-pos", headers=H, json=payload, timeout=60)
        assert r.status_code == 400, r.text
        assert "OTOMATIS" in r.text.upper(), r.text

    def test_13_maklon_finance_mirror(self):
        pid = state.get("auto_po_id")
        assert pid, "PO creation failed"
        r = requests.get(f"{BASE}/api/production-pos/{pid}/maklon-finance", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        m = d.get("mirror") or {}
        assert m.get("status") == "confirmed", m.get("status")
        assert float(m.get("total_value") or 0) == 200000.0, m
        assert float(d.get("total_cmt_cost") or m.get("total_cmt_cost") or 0) == 120000.0, d
        assert float(d.get("gross_margin") or m.get("gross_margin") or 0) == 80000.0, d
        ar = d.get("ar_invoice") or {}
        assert ar.get("status") == "draft", ar
        assert float(ar["lines"][0]["unit_price"]) == 20000.0, ar["lines"]

    def test_14_delete_po_cascades(self):
        pid = state.get("auto_po_id")
        assert pid
        r = requests.delete(f"{BASE}/api/production-pos/{pid}", headers=H, timeout=60)
        assert r.status_code in (200, 204), r.text
        assert db.dewi_maklon_pos.count_documents({"id": pid}) == 0
        assert db.rahaza_ar_invoices.count_documents({"linked_maklon_po_id": pid}) == 0
        r = requests.get(f"{BASE}/api/production-pos/{pid}", headers=H, timeout=60)
        assert r.status_code == 404, r.status_code


# ---------- Edge cases around cancel/regenerate ----------
class TestCancelEdgeCases:
    def test_20_cancel_blocked_when_paid(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H,
                          json={"order_id": PO, "tax_pct": 11}, timeout=90)
        assert r.status_code == 200, r.text
        inv_id = r.json()["id"]
        state["edge_inv"] = inv_id
        r = requests.post(f"{BASE}/api/dewi/maklon/payments", headers=H,
                          json={"invoice_id": inv_id, "amount": 799200, "method": "transfer"}, timeout=60)
        assert r.status_code in (200, 201), r.text
        pay = r.json()
        pay_id = pay.get("id") or (pay.get("payment") or {}).get("id")
        assert _dewi_rows()[0]["status"] == "paid", _dewi_rows()[0]["status"]
        assert _ar_rows()[0]["status"] == "paid"
        # cancel must be rejected while paid
        rc = requests.post(f"{BASE}/api/dewi/maklon/invoices/{inv_id}/cancel", headers=H, timeout=60)
        assert rc.status_code == 400, rc.text
        assert _dewi_rows(), "mirror deleted despite cancel rejection"
        # overpayment guard
        ro = requests.post(f"{BASE}/api/dewi/maklon/payments", headers=H,
                           json={"invoice_id": inv_id, "amount": 1000, "method": "transfer"}, timeout=60)
        assert ro.status_code == 400, ro.text
        # unwind
        rd = requests.delete(f"{BASE}/api/dewi/maklon/payments/{pay_id}", headers=H, timeout=60)
        assert rd.status_code in (200, 204), rd.text

    def test_21_cancel_unknown_id_404(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/does-not-exist-106/cancel",
                          headers=H, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_22_generate_with_manual_number_rejected(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/{state['edge_inv']}/cancel",
                          headers=H, timeout=90)
        assert r.status_code == 200, r.text
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H,
                          json={"order_id": PO, "tax_pct": 11, "invoice_number": "INV-CUSTOM-106"},
                          timeout=60)
        assert r.status_code == 400, r.text
        assert AR_NUM in r.text, r.text
        assert _dewi_rows() == [], "mirror created despite rejection"

    def test_23_double_cancel_and_final_state(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H,
                          json={"order_id": PO, "tax_pct": 11}, timeout=90)
        assert r.status_code == 200, r.text
        inv_id = r.json()["id"]
        assert requests.post(f"{BASE}/api/dewi/maklon/invoices/{inv_id}/cancel", headers=H,
                             timeout=90).status_code == 200
        # second cancel on same id -> 404 (mirror already deleted), no 500
        r2 = requests.post(f"{BASE}/api/dewi/maklon/invoices/{inv_id}/cancel", headers=H, timeout=60)
        assert r2.status_code == 404, r2.status_code
        requests.post(f"{BASE}/api/production-pos/{PO}/sync-maklon-finance", headers=H, timeout=60)
        assert _dewi_rows() == []
        ars = _ar_rows()
        assert len(ars) == 1 and ars[0]["status"] == "draft" and ars[0]["invoice_number"] == AR_NUM
        assert db.dewi_maklon_payments.count_documents({"invoice_id": inv_id}) == 0
