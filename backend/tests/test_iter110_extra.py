"""Iteration 110 extra checks: bank-recon summary/gl-entries/import-bulk + regression endpoints."""
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
R = f"{BASE}/api/finance/bank-recon"
SFX = uuid.uuid4().hex[:6].upper()
S = {}


class TestBankReconExtra:
    def test_00_summary(self):
        r = requests.get(f"{R}/summary", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), (dict, list))

    def test_01_gl_entries_requires_session(self):
        r = requests.get(f"{R}/gl-entries?period=2026-09", headers=H, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_02_import_bulk_direction(self):
        acc = requests.post(f"{BASE}/api/rahaza/cash-accounts", headers=H, timeout=60, json={
            "code": f"RX-{SFX}", "name": f"Bank Extra {SFX}", "type": "bank", "gl_account_code": "1-1201",
            "opening_balance": 0}).json()
        S["acc"] = acc
        r = requests.post(f"{R}/sessions", headers=H, timeout=60,
                          json={"period": "2026-07", "cash_account_id": acc["id"], "closing_balance": 0})
        assert r.status_code == 200, r.text
        sid = r.json()["id"]
        S["sid"] = sid
        r = requests.post(f"{R}/sessions/{sid}/import-bulk", headers=H, timeout=60, json={"transactions": [
            {"txn_date": "2026-07-05", "description": "Biaya admin", "amount": 6500, "direction": "out"},
            {"txn_date": "2026-07-06", "description": "Setoran", "amount": 250000, "direction": "in"},
        ]})
        assert r.status_code == 200, r.text
        assert r.json().get("imported") == 2, r.text
        rows = list(db.bank_recon_txns.find({"session_id": sid}, {"_id": 0}))
        by_amt = {x["amount"]: x for x in rows}
        assert by_amt[6500]["direction"] == "out"
        assert by_amt[250000]["direction"] == "in"
        # GET detail + list endpoint reflect imported txns
        d = requests.get(f"{R}/sessions/{sid}", headers=H, timeout=60).json()
        assert d["summary"]["bank_count"] == 2, d["summary"]
        assert d["summary"]["unmatched_bank_out"] == 6500 and d["summary"]["unmatched_bank_in"] == 250000
        lt = requests.get(f"{R}/sessions/{sid}/transactions", headers=H, timeout=60).json()
        assert lt["total"] == 2 and {x["direction"] for x in lt["items"]} == {"in", "out"}

    def test_03_settlement_candidates(self):
        sid = S["sid"]
        rows = list(db.bank_recon_txns.find({"session_id": sid, "direction": "in"}, {"_id": 0}))
        txn = rows[0]
        r = requests.get(f"{R}/sessions/{sid}/transactions/{txn['id']}/candidates", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        assert "items" in r.json()
        # settlement-candidates only for money-in
        r = requests.get(f"{R}/sessions/{sid}/transactions/{txn['id']}/settlement-candidates", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        assert "items" in r.json()
        out_txn = db.bank_recon_txns.find_one({"session_id": sid, "direction": "out"}, {"_id": 0})
        r2 = requests.get(f"{R}/sessions/{sid}/transactions/{out_txn['id']}/settlement-candidates", headers=H, timeout=60)
        assert r2.status_code == 400 and "MASUK" in r2.text, f"{r2.status_code} {r2.text[:200]}"
        rl = requests.post(f"{R}/sessions/{sid}/link-settlement", headers=H, timeout=60,
                           json={"txn_id": out_txn["id"], "settlement_doc_id": "x"})
        assert rl.status_code == 400 and "MASUK" in rl.text, rl.text[:200]
        # link-settlement with unknown settlement id must not 500
        r3 = requests.post(f"{R}/sessions/{sid}/link-settlement", headers=H, timeout=60,
                           json={"txn_id": txn["id"], "settlement_doc_id": "does-not-exist"})
        assert r3.status_code in (400, 404), f"{r3.status_code} {r3.text[:200]}"
        print("settlements in db:", db.marketing_settlements.count_documents({}))

    def test_04_approve_unexplained_requires_confirm(self):
        sid = S["sid"]
        # hapus semua mutasi agar unmatched_count = 0, lalu set closing ≠ saldo GL → explained=false
        for t in db.bank_recon_txns.find({"session_id": sid}, {"_id": 0, "id": 1}):
            requests.delete(f"{R}/sessions/{sid}/transactions/{t['id']}", headers=H, timeout=60)
        requests.put(f"{R}/sessions/{sid}", headers=H, timeout=60, json={"closing_balance": 987654321})
        d = requests.get(f"{R}/sessions/{sid}", headers=H, timeout=60).json()
        assert d["summary"]["explained"] is False
        r = requests.post(f"{R}/sessions/{sid}/approve", headers=H, timeout=60, json={})
        assert r.status_code == 409, f"{r.status_code} {r.text[:300]}"
        assert r.json()["detail"]["code"] == "unexplained_difference"
        r = requests.post(f"{R}/sessions/{sid}/approve", headers=H, timeout=60, json={"confirm_unexplained": True, "note": "uji"})
        assert r.status_code == 200, r.text
        j = r.json()
        assert j["status"] == "approved" and j["approved_with_unexplained"] is True
        assert j["approved_summary"]["explained"] is False and j["approval_note"] == "uji"
        S["approved"] = True

    def test_99_cleanup(self):
        sid = S.get("sid")
        if sid:
            if S.get("approved"):
                db.bank_recon_sessions.delete_one({"id": sid})
                db.bank_recon_txns.delete_many({"session_id": sid})
                db.bank_recon_matches.delete_many({"session_id": sid})
            else:
                requests.delete(f"{R}/sessions/{sid}", headers=H, timeout=60)
        if S.get("acc"):
            db.rahaza_cash_accounts.delete_one({"id": S["acc"]["id"]})
            if (S["acc"].get("gl_account_code") or "1-1201") != "1-1201":
                db.rahaza_coa_accounts.delete_one({"code": S["acc"]["gl_account_code"]})


class TestRegression:
    def test_balance_sheet_balanced(self):
        r = requests.get(f"{BASE}/api/rahaza/finance/reports/balance-sheet", headers=H, timeout=120)
        assert r.status_code == 200, r.text
        assert r.json().get("balanced") is True

    def test_ar_aging(self):
        r = requests.get(f"{BASE}/api/rahaza/ar-aging", headers=H, timeout=120)
        assert r.status_code == 200, r.text
