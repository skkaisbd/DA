"""Iteration 108 regression: Bayar Vendor CMT, Aging Piutang tunggal, HPP absorption.

Run serially:  python3 -m pytest tests/test_iter108_finance.py -q -p no:cacheprovider -n 0
Login admin@garment.com/Admin@123 dilakukan otomatis.
"""
import asyncio
import os
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
be = dotenv_values("/app/backend/.env")
db = MongoClient(os.environ.get("MONGO_URL") or be["MONGO_URL"])[os.environ.get("DB_NAME") or be["DB_NAME"]]

_tok = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60).json()["token"]
H = {"Authorization": f"Bearer {_tok}", "Content-Type": "application/json"}
SFX = uuid.uuid4().hex[:6].upper()
PAY_ID = f"qa-cmt-{SFX.lower()}"
S = {}


def _je(source_type, source_ref):
    return db.rahaza_journal_entries.find_one({"source_module": source_type, "source_ref": source_ref}, {"_id": 0})


def _line(je, code):
    return next((l for l in je["lines"] if l.get("account_code") == code), None)


class TestCmtPay:
    def test_00_setup(self):
        requests.post(f"{BASE}/api/seed/maklon-full", headers=H, timeout=120)
        r = requests.post(f"{BASE}/api/rahaza/cash-accounts", headers=H, timeout=60, json={
            "code": f"QA-{SFX}", "name": f"QA Bank {SFX}", "type": "bank", "gl_account_code": "1-1201", "opening_balance": 0})
        assert r.status_code == 200, r.text
        S["acc"] = r.json()
        db.dewi_cmt_payments.insert_one({
            "id": PAY_ID, "payment_code": f"PAY-CMT-{SFX}", "cmt_name": "QA Vendor", "po_id": "po-int-demo-2",
            "subtotal": 300000, "total_penalty": 0, "net_amount": 300000, "total_amount": 300000,
            "status": "draft", "payment_date": "2026-09-04"})

    def test_01_partial_pay_posts_ap_to_wip(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/finance/cmt-payments/{PAY_ID}/pay", headers=H, timeout=60, json={
            "cash_account_id": S["acc"]["id"], "amount": 100000, "payment_date": "2026-09-04", "reference_no": "QA-1"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["gl_je_number"] and d["payment_status"] == "partial_paid"
        S["d1"] = d["id"]
        ap = _je("cmt_ap_invoice", f"cmt_ap:{PAY_ID}")
        assert ap and ap.get("status") != "voided"
        assert _line(ap, "1-1403")["debit"] == 300000 and _line(ap, "2-1100")["credit"] == 300000
        assert _line(ap, "5-231") is None
        pay = db.rahaza_journal_entries.find_one({"id": d["gl_je_id"]}, {"_id": 0})
        assert _line(pay, "2-1100")["debit"] == 100000
        bank = next(l for l in pay["lines"] if l["account_code"] != "2-1100")
        assert bank["credit"] == 100000 and bank["account_code"].startswith("1-120")

    def test_02_pay_rest_then_reject(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/finance/cmt-payments/{PAY_ID}/pay", headers=H, timeout=60,
                          json={"cash_account_id": S["acc"]["id"], "payment_date": "2026-09-04"})
        assert r.status_code == 200, r.text
        assert r.json()["amount"] == 200000 and r.json()["payment_status"] == "paid"
        r = requests.post(f"{BASE}/api/dewi/maklon/finance/cmt-payments/{PAY_ID}/pay", headers=H, timeout=60,
                          json={"cash_account_id": S["acc"]["id"]})
        assert r.status_code == 400 and "lunas" in r.text
        rows = requests.get(f"{BASE}/api/dewi/maklon/finance/cmt-payments/{PAY_ID}/disbursements", headers=H, timeout=60).json()
        assert len(rows) == 2

    def test_03_void_first(self):
        r = requests.post(f"{BASE}/api/dewi/maklon/finance/cmt-payments/{PAY_ID}/disbursements/{S['d1']}/void", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        p = db.dewi_cmt_payments.find_one({"id": PAY_ID}, {"_id": 0})
        assert p["status"] == "partial_paid" and p["paid_amount"] == 200000
        assert db.rahaza_cash_movements.find_one({"id": S["d1"]}) is None
        je = _je("ap_payment", f"appay:{S['d1']}:100000")
        assert je and je.get("status") == "voided"

    def test_04_billing_list(self):
        r = requests.get(f"{BASE}/api/production/cmt-billing", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        rows = r.json()
        rows = rows.get("items") if isinstance(rows, dict) else rows
        row = next((x for x in rows if x.get("id") == PAY_ID), None)
        assert row and row.get("paid_amount") == 200000 and row.get("outstanding_amount") == 100000


class TestArAging:
    def test_00_internal_invoice(self):
        cid = f"cust-qa-{SFX}"
        db.rahaza_customers.insert_one({"id": cid, "name": f"QA Cust {SFX}", "code": f"QC{SFX}", "active": True})
        r = requests.post(f"{BASE}/api/rahaza/ar-invoices", headers=H, timeout=60, json={
            "customer_id": cid, "customer_name": f"QA Cust {SFX}", "tax_pct": 0, "due_date": "2026-07-01",
            "items": [{"description": "QA", "qty": 1, "unit_price": 50000}]})
        assert r.status_code == 200, r.text
        S["ar"] = r.json()["id"]
        r = requests.post(f"{BASE}/api/rahaza/ar-invoices/{S['ar']}/send", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        doc = db.rahaza_ar_invoices.find_one({"id": S["ar"]}, {"_id": 0})
        assert doc["status"] == "issued"
        assert doc["total_amount"] == doc["amount_due"] == doc["total"] == doc["balance"] == 50000

    def test_01_partial_payment(self):
        r = requests.post(f"{BASE}/api/rahaza/ar-invoices/{S['ar']}/payment", headers=H, timeout=60,
                          json={"amount": 20000, "account_id": S["acc"]["id"], "payment_date": "2026-09-04"})
        assert r.status_code == 200, r.text
        doc = db.rahaza_ar_invoices.find_one({"id": S["ar"]}, {"_id": 0})
        assert doc["amount_paid"] == doc["paid_amount"] == 20000
        assert doc["amount_due"] == doc["balance"] == 30000 and doc["status"] == "partial_paid"

    def test_02_single_aging(self):
        for d in db.dewi_maklon_invoices.find({"order_id": "po-mk-demo-2"}, {"_id": 0, "id": 1}):
            requests.post(f"{BASE}/api/dewi/maklon/invoices/{d['id']}/cancel", headers=H, timeout=60)
        requests.post(f"{BASE}/api/production-pos/po-mk-demo-2/sync-maklon-finance", headers=H, timeout=60)
        r = requests.post(f"{BASE}/api/dewi/maklon/invoices/generate", headers=H, timeout=60, json={"order_id": "po-mk-demo-2", "tax_pct": 11})
        assert r.status_code == 200, r.text
        r = requests.get(f"{BASE}/api/rahaza/ar-aging", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        d = r.json()
        mine = next(x for x in d["details"] if x.get("id") == S["ar"])
        assert mine["source"] == "internal" and mine["amount_due"] == 30000
        assert any(x.get("source") == "maklon" for x in d["details"])
        assert round(sum(float(x.get("amount_due") or 0) for x in d["details"])) == d["total"]
        ri = requests.get(f"{BASE}/api/rahaza/ar-aging?source=internal", headers=H, timeout=60).json()
        assert all(x.get("source") == "internal" for x in ri["details"])
        rm = requests.get(f"{BASE}/api/rahaza/ar-aging?source=maklon", headers=H, timeout=60).json()
        mk = requests.get(f"{BASE}/api/dewi/maklon/reports/aging", headers=H, timeout=60)
        assert mk.status_code == 200, mk.text
        mkd = mk.json()
        assert round(float(mkd.get("total") or 0)) == rm["total"]
        rows = mkd.get("rows") or mkd.get("details") or []
        assert rows and all("balance_amount" in x and "bucket" in x and "client_name" in x for x in rows)


class TestHppAbsorption:
    def test_00_wip_to_fg(self):
        from routes.rahaza_posting import post_wip_to_fg_on_job_complete
        from motor.motor_asyncio import AsyncIOMotorClient
        po = f"po-qa-{SFX}"
        db.fg_cost_layers.insert_one({"id": f"ly-{SFX}", "material_id": "m", "batch": {"po_id": po},
                                      "qty_in": 10, "unit_cost": 45000, "total_cost": 450000})
        job = {"id": f"job-{SFX}", "job_number": f"JOB-{SFX}", "po_id": po, "completed_at": "2026-09-04"}
        user = {"id": "qa", "name": "QA"}

        async def run():
            adb = AsyncIOMotorClient(be["MONGO_URL"])[be["DB_NAME"]]
            r1 = await post_wip_to_fg_on_job_complete(adb, job, user)
            r2 = await post_wip_to_fg_on_job_complete(adb, job, user)
            return r1, r2
        r1, r2 = asyncio.run(run())
        assert r1.get("ok"), r1
        assert r2.get("already_posted") or r2.get("skipped") == "already_posted", r2
        je = db.rahaza_journal_entries.find_one({"id": r1["je_id"]}, {"_id": 0})
        assert _line(je, "1-1404")["debit"] == 450000 and _line(je, "1-1403")["credit"] == 450000
        assert "(fg_cost_layers)" in _line(je, "1-1403")["description"]
        assert db.fg_cost_layers.find_one({"id": f"ly-{SFX}"})["gl_job_id"] == job["id"]

    def test_01_posting_profiles(self):
        r = requests.get(f"{BASE}/api/rahaza/posting-profiles", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        cmt = next(x for x in r.json() if x.get("event_type") == "cmt_ap_invoice")
        acc = cmt["mapping"]
        assert acc["debit_cmt_wip_internal"] == "1-1403" and acc["debit_cmt_expense_maklon"] == "7-120"


class TestRegression:
    def test_balance_sheet(self):
        r = requests.get(f"{BASE}/api/rahaza/finance/reports/balance-sheet", headers=H, timeout=120)
        assert r.status_code == 200 and r.json().get("balanced") is True, r.text
        assert requests.get(f"{BASE}/api/rahaza/ar-invoices", headers=H, timeout=60).status_code == 200
        assert requests.get(f"{BASE}/api/dewi/maklon/invoices", headers=H, timeout=60).status_code == 200

    def test_zz_cleanup_qa_data(self):
        """Bersihkan jejak uji (JE + cermin + subledger) agar GL seed tetap bersih. Invoice maklon demo dibiarkan."""
        acc = S.get("acc") or {}
        refs = {"$in": [f"cmt_ap:{PAY_ID}", f"wip_fg_job:job-{SFX}"] + ([f"ar:{S['ar']}"] if S.get("ar") else [])}
        q = {"$or": [{"source_ref": refs}]}
        if acc.get("gl_account_code"):
            q["$or"].append({"lines.account_code": acc["gl_account_code"]})
        if S.get("ar"):
            inv = db.rahaza_ar_invoices.find_one({"id": S["ar"]}, {"_id": 0, "invoice_number": 1}) or {}
            if inv.get("invoice_number"):
                q["$or"].append({"source_module": "ar_payment", "memo": {"$regex": inv["invoice_number"]}})
        je_ids = [j["id"] for j in db.rahaza_journal_entries.find(q, {"_id": 0, "id": 1})]
        db.rahaza_journal_entries.delete_many({"id": {"$in": je_ids}})
        db.rahaza_journal_lines.delete_many({"je_id": {"$in": je_ids}})
        db.dewi_cmt_payments.delete_one({"id": PAY_ID})
        db.dewi_cmt_disbursements.delete_many({"payment_id": PAY_ID})
        if S.get("ar"):
            db.rahaza_ar_invoices.delete_one({"id": S["ar"]})
        db.rahaza_customers.delete_many({"id": f"cust-qa-{SFX}"})
        # iter112: subledger COA pelanggan yang dibuat otomatis juga harus dibersihkan
        db.rahaza_coa_accounts.delete_many({"code": f"1-1301-QC{SFX}"})
        if acc.get("id"):
            db.rahaza_cash_movements.delete_many({"account_id": acc["id"]})
            db.rahaza_cash_accounts.delete_one({"id": acc["id"]})
            if (acc.get("gl_account_code") or "1-1201") != "1-1201":
                db.rahaza_coa_accounts.delete_one({"code": acc["gl_account_code"]})
        db.fg_cost_layers.delete_one({"id": f"ly-{SFX}"})
        orphan = db.rahaza_journal_lines.count_documents({"je_id": {"$nin": db.rahaza_journal_entries.distinct("id")}})
        assert orphan == 0, f"cermin baris yatim: {orphan}"
