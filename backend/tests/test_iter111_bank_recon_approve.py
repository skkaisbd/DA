"""Iteration 111: bank-recon approve guards (explained=true direct approve, unmatched guard) + regression."""
import os
import uuid

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL") or "").rstrip("/")
be = dotenv_values("/app/backend/.env")
db = MongoClient(os.environ.get("MONGO_URL") or be["MONGO_URL"])[os.environ.get("DB_NAME") or be["DB_NAME"]]

_tok = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"},
                     timeout=60).json()["token"]
H = {"Authorization": f"Bearer {_tok}", "Content-Type": "application/json"}
R = f"{BASE}/api/finance/bank-recon"
SFX = uuid.uuid4().hex[:6].upper()
S = {}


class TestApproveGuards:
    def test_00_setup_account_and_session(self):
        r = requests.post(f"{BASE}/api/rahaza/cash-accounts", headers=H, timeout=60, json={
            "code": f"R111-{SFX}", "name": f"Bank Iter111 {SFX}", "type": "bank",
            "gl_account_code": "1-1201", "opening_balance": 0})
        assert r.status_code in (200, 201), r.text
        S["acc"] = r.json()
        r = requests.post(f"{R}/sessions", headers=H, timeout=60,
                          json={"period": "2026-06", "cash_account_id": S["acc"]["id"], "closing_balance": 0})
        assert r.status_code == 200, r.text
        S["sid"] = r.json()["id"]

    def test_01_unmatched_guard_blocks_approve(self):
        sid = S["sid"]
        r = requests.post(f"{R}/sessions/{sid}/import-bulk", headers=H, timeout=60, json={"transactions": [
            {"txn_date": "2026-06-05", "description": "TEST_Biaya admin", "amount": 6500, "direction": "out"}]})
        assert r.status_code == 200 and r.json()["imported"] == 1, r.text
        r = requests.post(f"{R}/sessions/{sid}/approve", headers=H, timeout=60, json={"confirm_unexplained": True})
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"
        assert "belum dicocokkan" in r.text, r.text[:300]

    def test_02_settlement_candidates_direction_guard(self):
        sid = S["sid"]
        out_txn = db.bank_recon_txns.find_one({"session_id": sid, "direction": "out"}, {"_id": 0})
        r = requests.get(f"{R}/sessions/{sid}/transactions/{out_txn['id']}/settlement-candidates",
                         headers=H, timeout=60)
        assert r.status_code == 400 and "MASUK" in r.text, f"{r.status_code} {r.text[:200]}"
        r2 = requests.post(f"{R}/sessions/{sid}/import-bulk", headers=H, timeout=60, json={"transactions": [
            {"txn_date": "2026-06-06", "description": "TEST_Setoran", "amount": 250000, "direction": "in"}]})
        assert r2.status_code == 200, r2.text
        in_txn = db.bank_recon_txns.find_one({"session_id": sid, "direction": "in"}, {"_id": 0})
        r3 = requests.get(f"{R}/sessions/{sid}/transactions/{in_txn['id']}/settlement-candidates",
                          headers=H, timeout=60)
        assert r3.status_code == 200 and "items" in r3.json(), f"{r3.status_code} {r3.text[:200]}"

    def test_03_explained_session_approves_without_confirm(self):
        sid = S["sid"]
        for t in list(db.bank_recon_txns.find({"session_id": sid}, {"_id": 0, "id": 1})):
            assert requests.delete(f"{R}/sessions/{sid}/transactions/{t['id']}", headers=H,
                                   timeout=60).status_code == 200
        d = requests.get(f"{R}/sessions/{sid}", headers=H, timeout=60).json()
        adjusted = d["summary"]["adjusted_gl_balance"]
        r = requests.put(f"{R}/sessions/{sid}", headers=H, timeout=60, json={"closing_balance": adjusted})
        assert r.status_code == 200, r.text
        d = requests.get(f"{R}/sessions/{sid}", headers=H, timeout=60).json()
        assert d["summary"]["explained"] is True, d["summary"]
        r = requests.post(f"{R}/sessions/{sid}/approve", headers=H, timeout=60, json={})
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        j = r.json()
        S["approved"] = True
        assert j["status"] == "approved"
        assert j["approved_with_unexplained"] is False, j.get("approved_with_unexplained")
        assert j["approved_summary"]["explained"] is True
        # persisted snapshot readable via GET
        g = requests.get(f"{R}/sessions/{sid}", headers=H, timeout=60).json()
        assert g["status"] == "approved" and g["approved_summary"]["explained"] is True
        assert "_id" not in g

    def test_04_approved_session_is_immutable(self):
        sid = S["sid"]
        r = requests.put(f"{R}/sessions/{sid}", headers=H, timeout=60, json={"closing_balance": 1})
        assert r.status_code == 400, r.text[:200]
        r = requests.delete(f"{R}/sessions/{sid}", headers=H, timeout=60)
        assert r.status_code == 400, r.text[:200]

    def test_99_cleanup(self):
        sid = S.get("sid")
        if sid:
            db.bank_recon_sessions.delete_one({"id": sid})
            db.bank_recon_txns.delete_many({"session_id": sid})
            db.bank_recon_matches.delete_many({"session_id": sid})
            assert db.bank_recon_sessions.count_documents({"id": sid}) == 0
        if S.get("acc"):
            db.rahaza_cash_accounts.delete_one({"id": S["acc"]["id"]})
            if (S["acc"].get("gl_account_code") or "1-1201") != "1-1201":
                db.rahaza_coa_accounts.delete_one({"code": S["acc"]["gl_account_code"]})


class TestRegression111:
    def test_balance_sheet_balanced(self):
        r = requests.get(f"{BASE}/api/rahaza/finance/reports/balance-sheet", headers=H, timeout=120)
        assert r.status_code == 200, r.text
        assert r.json().get("balanced") is True

    def test_bank_recon_summary(self):
        r = requests.get(f"{R}/summary", headers=H, timeout=60)
        assert r.status_code == 200, r.text
        j = r.json()
        assert isinstance(j.get("total_sessions"), int) and j["approved"] >= 0
