"""Iteration 109 restore verification: AR aging (canonical), posting profiles, balance sheet, CMT billing."""
import os
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login failed {r.status_code}: {r.text[:300]}")
    token = r.json().get("token") or r.json().get("access_token")
    assert token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# --- AR aging canonical ---
class TestArAging:
    def test_ar_aging_total_matches_details(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/ar-aging", timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        details = data.get("details") or data.get("rows") or []
        assert isinstance(details, list)
        total = data.get("total", data.get("total_outstanding"))
        s = sum(float(d.get("amount_due") or 0) for d in details)
        assert total is not None, f"no total field in keys={list(data.keys())}"
        assert abs(float(total) - s) < 1.0, f"total {total} != sum details {s}"

    def test_ar_aging_source_internal(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/ar-aging?source=internal", timeout=90)
        assert r.status_code == 200, r.text[:300]
        details = r.json().get("details") or []
        srcs = {d.get("source") for d in details}
        assert srcs <= {"internal"}, f"unexpected sources: {srcs}"

    def test_ar_aging_source_maklon(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/ar-aging?source=maklon", timeout=90)
        assert r.status_code == 200, r.text[:300]
        details = r.json().get("details") or []
        srcs = {d.get("source") for d in details}
        assert srcs <= {"maklon"}, f"unexpected sources: {srcs}"

    def test_maklon_aging_report(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/maklon/reports/aging", timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        rows = data.get("rows") if isinstance(data, dict) else data
        assert isinstance(rows, list)
        if rows:
            row = rows[0]
            for k in ("balance_amount", "client_name", "bucket"):
                assert k in row, f"missing {k} in {list(row.keys())}"


# --- posting profiles ---
class TestPostingProfiles:
    def test_cmt_ap_invoice_mapping(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/posting-profiles", timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        prof = next((p for p in items if p.get("event_type") == "cmt_ap_invoice"), None)
        assert prof, "cmt_ap_invoice profile missing"
        m = prof.get("mapping") or {}
        assert m.get("debit_cmt_wip_internal") == "1-1403", m
        assert m.get("debit_cmt_expense_maklon") == "7-120", m


# --- reports / billing ---
class TestReports:
    def test_balance_sheet_balanced(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/finance/reports/balance-sheet", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("balanced") is True, r.json()

    def test_cmt_billing_list(self, client):
        r = client.get(f"{BASE_URL}/api/production/cmt-billing", timeout=90)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        items = data.get("items") if isinstance(data, dict) else data
        assert isinstance(items, list)
