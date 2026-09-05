"""
Iter 112 QA — audit fixes finance (backend only).
Cakupan:
  1. RBAC modul /api/finance/bank-recon/* (gudang 403, finance/accounting 200, admin 200)
  2. Guard periode pada POST /sessions/{sid}/transactions/{txn_id}/adjust
  3. Legacy /api/rahaza/finance/bank-recon-adjustments + /post → cash movement + saldo + repost 400
  4. GET /api/rahaza/finance/reports/balance-sheet → orphan_account_lines
  5. Regresi: /api/rahaza/ar-aging, /api/finance/bank-recon/summary
Semua data uji dibersihkan langsung dari Mongo pada teardown session.
"""
import os
import uuid

import pytest
import requests
from pymongo import MongoClient
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
be = dotenv_values("/app/backend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
MONGO_URL = os.environ.get("MONGO_URL") or be.get("MONGO_URL")
DB_NAME = os.environ.get("DB_NAME") or be.get("DB_NAME")

ADMIN = ("admin@garment.com", "Admin@123")
FIN = ("finance@dewiaditya.id", "Dewi@123")
GUDANG = ("gudang@dewiaditya.id", "Dewi@123")

TAG = uuid.uuid4().hex[:6].upper()
STATE = {"cash_account_id": None, "cash_code": None, "gl_code": None, "session_id": None,
         "adj_ids": [], "je_ids": []}


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email} gagal: {r.status_code} {r.text[:300]}"
    data = r.json()
    token = data.get("access_token") or data.get("token")
    assert token, f"tidak ada token di respons login: {list(data)}"
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(scope="session")
def admin_h():
    return _login(*ADMIN)


@pytest.fixture(scope="session")
def fin_h():
    return _login(*FIN)


@pytest.fixture(scope="session")
def gudang_h():
    return _login(*GUDANG)


@pytest.fixture(scope="session")
def mdb():
    c = MongoClient(MONGO_URL)
    yield c[DB_NAME]
    c.close()


@pytest.fixture(scope="session", autouse=True)
def cleanup(mdb):
    yield
    db = mdb
    sid = STATE["session_id"]
    acc_id = STATE["cash_account_id"]
    gl_code = STATE["gl_code"]
    if sid:
        db.bank_recon_sessions.delete_many({"id": sid})
        db.bank_recon_txns.delete_many({"session_id": sid})
        db.bank_recon_matches.delete_many({"session_id": sid})
    # JE + mirror lines dari penyesuaian uji
    je_ids = set(STATE["je_ids"])
    if gl_code:
        for je in db.rahaza_journal_entries.find({"lines.account_code": gl_code}, {"_id": 0, "id": 1}):
            je_ids.add(je["id"])
    if je_ids:
        db.rahaza_journal_entries.delete_many({"id": {"$in": list(je_ids)}})
        db.rahaza_journal_lines.delete_many({"je_id": {"$in": list(je_ids)}})
    if acc_id:
        db.rahaza_cash_movements.delete_many({"account_id": acc_id})
        db.rahaza_bank_recon_adjustments.delete_many({"bank_account_id": acc_id})
        db.rahaza_cash_accounts.delete_many({"id": acc_id})
    if STATE["adj_ids"]:
        db.rahaza_bank_recon_adjustments.delete_many({"id": {"$in": STATE["adj_ids"]}})
    if STATE["cash_code"]:
        db.rahaza_coa_accounts.delete_many({"code": f"1-1200-{STATE['cash_code']}"})
    if gl_code and gl_code.startswith("1-1200-"):
        db.rahaza_coa_accounts.delete_many({"code": gl_code})


# ── 1. RBAC ────────────────────────────────────────────────────────────────
class TestRbacBankRecon:
    def test_gudang_denied_list_sessions(self, gudang_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions", headers=gudang_h, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_gudang_denied_summary(self, gudang_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/summary", headers=gudang_h, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_gudang_denied_create_session(self, gudang_h):
        r = requests.post(f"{BASE_URL}/api/finance/bank-recon/sessions", headers=gudang_h,
                          json={"period": "2026-04", "cash_account_id": "x"}, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_gudang_denied_gl_entries(self, gudang_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/gl-entries?period=2026-04&gl_account_code=1-1201",
                         headers=gudang_h, timeout=30)
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    def test_admin_allowed(self, admin_h):
        for path in ("/api/finance/bank-recon/sessions", "/api/finance/bank-recon/summary"):
            r = requests.get(f"{BASE_URL}{path}", headers=admin_h, timeout=30)
            assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"

    @pytest.mark.parametrize("method,path,payload", [
        ("post", "/sessions/nonexistent/import-bulk", {"transactions": []}),
        ("post", "/sessions/nonexistent/auto-match", {}),
        ("post", "/sessions/nonexistent/transactions/xx/adjust", {"adjustment_type": "bank_charge"}),
        ("post", "/sessions/nonexistent/approve", {}),
        ("post", "/sessions/nonexistent/match", {"txn_id": "x"}),
        ("get", "/sessions/nonexistent/internal-check", None),
        ("delete", "/sessions/nonexistent", None),
    ])
    def test_gudang_denied_write_endpoints(self, gudang_h, method, path, payload):
        """Gerbang modul harus menolak SEBELUM cek keberadaan sesi (403, bukan 404)."""
        url = f"{BASE_URL}/api/finance/bank-recon{path}"
        r = getattr(requests, method)(url, headers=gudang_h, json=payload, timeout=30)
        assert r.status_code == 403, f"{method.upper()} {path} → {r.status_code}: {r.text[:200]}"

    def test_finance_allowed_list(self, fin_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions", headers=fin_h, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        assert "items" in r.json()


# ── 2. Cash account + sesi + guard periode adjust ──────────────────────────
class TestSessionAndAdjustGuard:
    def test_01_admin_create_cash_account(self, admin_h):
        code = f"QA{TAG}"
        r = requests.post(f"{BASE_URL}/api/rahaza/cash-accounts", headers=admin_h, timeout=30,
                          json={"code": code, "name": f"QA Bank {TAG}", "type": "bank",
                                "gl_account_code": "1-1201", "opening_balance": 0})
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        acc = r.json()
        STATE["cash_account_id"] = acc["id"]
        STATE["cash_code"] = acc["code"]
        STATE["gl_code"] = acc.get("gl_account_code")
        assert STATE["gl_code"], f"cash account tanpa gl_account_code: {acc}"

    def test_02_finance_create_session(self, fin_h):
        r = requests.post(f"{BASE_URL}/api/finance/bank-recon/sessions", headers=fin_h, timeout=30,
                          json={"period": "2026-04", "cash_account_id": STATE["cash_account_id"],
                                "opening_balance": 0, "closing_balance": -9000,
                                "notes": f"QA iter112 {TAG}"})
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        s = r.json()
        STATE["session_id"] = s["id"]
        assert s["period"] == "2026-04"
        assert s["gl_account_code"] == STATE["gl_code"]
        assert s["status"] == "draft"

    def test_03_finance_import_manual_and_automatch(self, fin_h):
        sid = STATE["session_id"]
        r = requests.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/import-bulk", headers=fin_h, timeout=30,
                          json={"transactions": [
                              {"txn_date": "2026-05-03", "description": "QA out of period", "amount": 6500, "direction": "out"},
                              {"txn_date": "2026-04-10", "description": "QA biaya admin", "amount": 6500, "direction": "out"},
                          ]})
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        assert r.json()["imported"] == 2
        r2 = requests.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/auto-match", headers=fin_h, timeout=30, json={})
        assert r2.status_code == 200, f"auto-match {r2.status_code}: {r2.text[:300]}"

    def test_04_adjust_outside_period_rejected(self, fin_h):
        sid = STATE["session_id"]
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions", headers=fin_h, timeout=30)
        assert r.status_code == 200
        txns = {t["txn_date"]: t for t in r.json()["items"]}
        out_txn = txns["2026-05-03"]
        ra = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions/{out_txn['id']}/adjust",
            headers=fin_h, json={"adjustment_type": "bank_charge"}, timeout=30)
        assert ra.status_code == 400, f"expected 400, got {ra.status_code}: {ra.text[:300]}"
        assert "di luar periode sesi" in ra.text, ra.text[:300]

    def test_05_adjust_in_period_creates_je_and_movement(self, fin_h, mdb):
        sid = STATE["session_id"]
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions", headers=fin_h, timeout=30)
        txn = next(t for t in r.json()["items"] if t["txn_date"] == "2026-04-10")
        ra = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions/{txn['id']}/adjust",
            headers=fin_h, json={"adjustment_type": "bank_charge", "description": f"QA adj {TAG}"}, timeout=30)
        assert ra.status_code == 200, f"{ra.status_code}: {ra.text[:400]}"
        body = ra.json()
        assert body["ok"] is True
        assert body.get("je_number"), body
        STATE["adj_ids"].append(body["adjustment_id"])
        # JE ke akun bank sesi
        je = mdb.rahaza_journal_entries.find_one({"je_number": body["je_number"]}, {"_id": 0})
        assert je, "JE tidak ditemukan di Mongo"
        STATE["je_ids"].append(je["id"])
        codes = [ln.get("account_code") for ln in je.get("lines") or []]
        assert STATE["gl_code"] in codes, f"JE tidak menyentuh akun bank sesi {STATE['gl_code']}: {codes}"
        bank_line = next(ln for ln in je["lines"] if ln.get("account_code") == STATE["gl_code"])
        assert float(bank_line.get("credit") or 0) == 6500.0, bank_line
        # cash movement
        mv = mdb.rahaza_cash_movements.find_one({"ref_id": body["adjustment_id"]}, {"_id": 0})
        assert mv, "cash movement tidak dibuat"
        assert mv["direction"] == "out" and mv["amount"] == 6500.0
        assert mv["gl_je_id"] == je["id"]
        # mutasi ter-match
        tx = mdb.bank_recon_txns.find_one({"id": txn["id"]}, {"_id": 0})
        assert tx["is_matched"] is True, tx
        assert body["matched"] is True

    def test_06_internal_check_movement_ok(self, fin_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{STATE['session_id']}/internal-check",
                         headers=fin_h, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        adj_rows = [m for m in data["movements"] if m.get("category") == "bank_adjustment"]
        assert adj_rows, data
        for m in adj_rows:
            assert m["status"] == "ok", m


# ── 3. Legacy adjustments ──────────────────────────────────────────────────
class TestLegacyAdjustments:
    def test_01_create_and_post(self, admin_h, mdb):
        acc_id = STATE["cash_account_id"]
        before = mdb.rahaza_cash_accounts.find_one({"id": acc_id}, {"_id": 0, "balance": 1})["balance"]
        r = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments", headers=admin_h, timeout=30,
                          json={"bank_account_id": acc_id, "adjustment_type": "bank_charge", "amount": 2500,
                                "adjustment_date": "2026-04-15", "description": f"QA legacy adj {TAG}"})
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        adj = r.json()
        assert adj["status"] == "draft"
        STATE["adj_ids"].append(adj["id"])
        rp = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments/{adj['id']}/post",
                           headers=admin_h, timeout=30)
        assert rp.status_code == 200, f"post {rp.status_code}: {rp.text[:400]}"
        posted = rp.json()
        assert posted["status"] == "posted"
        assert posted.get("je_number"), posted
        je = mdb.rahaza_journal_entries.find_one({"id": posted["je_id"]}, {"_id": 0})
        assert je, "JE legacy tidak ada"
        STATE["je_ids"].append(je["id"])
        # cash movement
        mvs = list(mdb.rahaza_cash_movements.find({"ref_id": adj["id"]}, {"_id": 0}))
        assert len(mvs) == 1, f"expected 1 movement, got {len(mvs)}"
        mv = mvs[0]
        assert mv["direction"] == "out"
        assert mv["amount"] == 2500.0
        assert mv["gl_je_id"] == posted["je_id"]
        assert mv["category"] == "bank_adjustment" and mv["source_module"] == "bank_recon"
        # saldo berkurang 2500
        after = mdb.rahaza_cash_accounts.find_one({"id": acc_id}, {"_id": 0, "balance": 1})["balance"]
        assert round(before - after, 2) == 2500.0, f"before={before} after={after}"
        STATE["legacy_adj_id"] = adj["id"]

    def test_02_repost_returns_400_not_500(self, admin_h):
        adj_id = STATE.get("legacy_adj_id")
        assert adj_id
        r = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments/{adj_id}/post",
                          headers=admin_h, timeout=30)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:300]}"

    def test_03_gudang_denied_legacy_post(self, gudang_h):
        r = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments", headers=gudang_h, timeout=30,
                          json={"bank_account_id": STATE["cash_account_id"], "adjustment_type": "bank_charge",
                                "amount": 100, "adjustment_date": "2026-04-15", "description": "QA denied"})
        assert r.status_code == 403, f"expected 403, got {r.status_code}: {r.text[:200]}"

    @pytest.mark.parametrize("payload_extra,exp_dir,amount", [
        ({"expense_account": "6-2500"}, "out", 1500),
        ({"income_account": "4-910"}, "in", 1750),
    ])
    def test_05_other_type_direction_follows_account(self, admin_h, mdb, payload_extra, exp_dir, amount):
        """tipe 'other': expense_account → out, income_account → in (saldo & movement ikut)."""
        acc_id = STATE["cash_account_id"]
        before = mdb.rahaza_cash_accounts.find_one({"id": acc_id}, {"_id": 0, "balance": 1})["balance"]
        body = {"bank_account_id": acc_id, "adjustment_type": "other", "amount": amount,
                "adjustment_date": "2026-04-16", "description": f"QA other {exp_dir} {TAG}"}
        body.update(payload_extra)
        r = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments", headers=admin_h,
                          json=body, timeout=30)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        adj = r.json()
        STATE["adj_ids"].append(adj["id"])
        rp = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments/{adj['id']}/post",
                           headers=admin_h, timeout=30)
        assert rp.status_code == 200, f"post {rp.status_code}: {rp.text[:400]}"
        posted = rp.json()
        STATE["je_ids"].append(posted["je_id"])
        mv = mdb.rahaza_cash_movements.find_one({"ref_id": adj["id"]}, {"_id": 0})
        assert mv, "movement tidak dibuat untuk tipe other"
        assert mv["direction"] == exp_dir, mv
        after = mdb.rahaza_cash_accounts.find_one({"id": acc_id}, {"_id": 0, "balance": 1})["balance"]
        expected = before + amount if exp_dir == "in" else before - amount
        assert round(after, 2) == round(expected, 2), f"saldo {before} → {after}, expected {expected}"

    def test_06_missing_accounts_other_returns_400(self, admin_h):
        r = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments", headers=admin_h, timeout=30,
                          json={"bank_account_id": STATE["cash_account_id"], "adjustment_type": "other",
                                "amount": 900, "adjustment_date": "2026-04-16", "description": f"QA bad {TAG}"})
        assert r.status_code == 200, r.text[:200]
        adj = r.json()
        STATE["adj_ids"].append(adj["id"])
        rp = requests.post(f"{BASE_URL}/api/rahaza/finance/bank-recon-adjustments/{adj['id']}/post",
                           headers=admin_h, timeout=30)
        assert rp.status_code == 400, f"expected 400, got {rp.status_code}: {rp.text[:300]}"

    def test_07_internal_check_shows_legacy_movement_ok(self, fin_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{STATE['session_id']}/internal-check",
                         headers=fin_h, timeout=30)
        assert r.status_code == 200
        rows = [m for m in r.json()["movements"] if m["amount"] == 2500.0]
        assert rows, "movement legacy 2500 tidak tampil di internal-check"
        assert rows[0]["status"] == "ok", rows[0]


# ── 4/5. Balance sheet + regresi ───────────────────────────────────────────
class TestReportsRegression:
    def test_balance_sheet_orphan_field(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/rahaza/finance/reports/balance-sheet", headers=admin_h, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"
        data = r.json()
        assert "orphan_account_lines" in data, list(data)
        assert isinstance(data["orphan_account_lines"], list)
        assert data["orphan_account_lines"] == [], data["orphan_account_lines"]
        assert data["balanced"] is True, data.get("totals")

    def test_ar_aging(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/rahaza/ar-aging", headers=admin_h, timeout=60)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:300]}"

    def test_summary_admin(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/summary", headers=admin_h, timeout=30)
        assert r.status_code == 200, r.text[:200]
        assert "total_sessions" in r.json()
