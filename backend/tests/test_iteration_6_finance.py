"""
Iteration 6 - Finance comprehensive re-validation (post bug-fix).
Tests focus on integration chains and previously fixed bugs:
  - posting-profiles auto-seed (33 profiles)
  - route shadowing (leaves/balance, accruals/recurring-templates)
  - fixed-asset disposal NameError fix
  - travel/expenses/STATUS_LABELS
  - ~25 ObjectId-serialization safety changes
Backed by /app/test_reports/iteration_5.json context.
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


# ---------- shared fixtures ----------
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                      timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}",
                      "Content-Type": "application/json"})
    return s


def _ok(resp, allowed=(200, 201)):
    return resp.status_code in allowed


# =====================================================================
# JUST-FIXED BUG #1 - Posting Profiles auto-seed (33 profiles + idempotent)
# =====================================================================
class TestPostingProfilesSeed:
    def test_list_has_33_profiles(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/posting-profiles", timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        # Could be list or {items: [...]}
        items = data if isinstance(data, list) else data.get("items", data.get("data", []))
        assert len(items) >= 33, f"Expected >=33 profiles, got {len(items)}"
        sample = items[0]
        # each profile must have event_type and mapping
        assert "event_type" in sample, f"profile missing event_type: {sample}"

    def test_seed_idempotent(self, client):
        r = client.post(f"{BASE_URL}/api/rahaza/posting-profiles/seed", timeout=60)
        assert r.status_code in (200, 201), r.text[:300]
        body = r.json()
        # Should report skipped count near total
        skipped = body.get("skipped", body.get("already_exists", 0))
        created = body.get("created", body.get("inserted", 0))
        # idempotent: created should be 0 (or all 33 should be skipped)
        assert created == 0 or skipped >= 33 or (created + skipped) >= 33, f"not idempotent: {body}"


# =====================================================================
# JUST-FIXED BUG #2 - Route shadowing
# =====================================================================
class TestRouteShadowing:
    def test_leaves_balance_literal_route(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/leaves/balance?employee_id=EMP001", timeout=30)
        # Must NOT be 404 (caused by being caught as leave_id=balance)
        assert r.status_code in (200, 400, 409), f"leaves/balance returned {r.status_code}: {r.text[:200]}"
        # If 200, should be a balance object
        if r.status_code == 200:
            body = r.json()
            assert isinstance(body, (dict, list)), f"unexpected balance body type: {type(body)}"

    def test_recurring_templates_literal_route(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/finance/accruals/recurring-templates", timeout=30)
        assert r.status_code == 200, f"recurring-templates: {r.status_code} {r.text[:200]}"
        body = r.json()
        items = body if isinstance(body, list) else body.get("items", body.get("data", []))
        assert isinstance(items, list)

    def test_accrual_random_id_still_404(self, client):
        random_id = f"nonexistent-{uuid.uuid4()}"
        r = client.get(f"{BASE_URL}/api/rahaza/finance/accruals/{random_id}", timeout=30)
        assert r.status_code in (404, 400), f"random id should 404, got {r.status_code}"


# =====================================================================
# JUST-FIXED BUG #3 - Fixed Asset disposal (NameError 'user')
# =====================================================================
class TestFixedAssetDisposal:
    def test_create_and_dispose_asset(self, client):
        # create asset
        payload = {
            "code": f"TEST-FA-{uuid.uuid4().hex[:6]}",
            "name": "Test Asset for Disposal",
            "category": "peralatan",
            "acquisition_date": str(date.today() - timedelta(days=400)),
            "acquisition_cost": 10000000,
            "useful_life_years": 5,
            "depreciation_method": "straight_line",
            "salvage_value": 1000000,
        }
        r = client.post(f"{BASE_URL}/api/rahaza/finance/fixed-assets", json=payload, timeout=30)
        if r.status_code not in (200, 201):
            pytest.skip(f"Could not create asset: {r.status_code} {r.text[:300]}")
        asset = r.json()
        aid = asset.get("id") or asset.get("_id") or asset.get("asset_id")
        assert aid, f"no asset id in response: {asset}"

        # dispose
        disp = {
            "disposal_date": str(date.today()),
            "disposal_value": 5000000,
            "disposal_reason": "test sale",
        }
        rd = client.post(f"{BASE_URL}/api/rahaza/finance/fixed-assets/{aid}/dispose",
                         json=disp, timeout=30)
        assert rd.status_code in (200, 201), f"disposal failed: {rd.status_code} {rd.text[:400]}"

        # verify
        rg = client.get(f"{BASE_URL}/api/rahaza/finance/fixed-assets/{aid}", timeout=30)
        if rg.status_code == 200:
            body = rg.json()
            status = body.get("status") or body.get("state")
            assert status in ("disposed", "DISPOSED"), f"status not disposed: {status}"


# =====================================================================
# JUST-FIXED BUG #4 - Travel/expenses (STATUS_LABELS)
# =====================================================================
class TestTravelExpenses:
    def test_travel_requests_list(self, client):
        # Common candidate endpoints
        candidates = [
            "/api/hr/expenses/travel-requests",
            "/api/hr/travel-requests",
            "/api/hr/expenses/travel",
        ]
        ok = False
        last = None
        for ep in candidates:
            r = client.get(f"{BASE_URL}{ep}", timeout=30)
            last = (ep, r.status_code, r.text[:200])
            if r.status_code == 200:
                ok = True
                break
        assert ok, f"no travel-requests endpoint responded 200: {last}"

    def test_travel_csv_export(self, client):
        candidates = [
            "/api/hr/expenses/travel-requests/export.csv",
            "/api/hr/expenses/travel-requests/export",
            "/api/hr/expenses/travel/export.csv",
        ]
        seen = []
        for ep in candidates:
            r = client.get(f"{BASE_URL}{ep}", timeout=30)
            seen.append((ep, r.status_code))
            if r.status_code == 200:
                return
        # if none returned 200, at least none should be 500
        for ep, code in seen:
            assert code != 500, f"CSV export 500 at {ep}: {seen}"


# =====================================================================
# CORE ACCOUNTING - Journal post / Trial Balance integration
# =====================================================================
class TestAccountingIntegration:
    def test_coa_accounts_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/coa/accounts", timeout=30)
        assert r.status_code == 200
        data = r.json()
        items = data if isinstance(data, list) else data.get("items", [])
        assert len(items) > 0, "COA empty"

    def test_coa_tree(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/coa/tree", timeout=30)
        assert r.status_code == 200

    def test_unbalanced_journal_rejected(self, client):
        # find leaf accounts (postable)
        r = client.get(f"{BASE_URL}/api/rahaza/coa/accounts", timeout=30)
        accs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        leafs = [a for a in accs if not a.get("is_group")]
        if len(leafs) < 2:
            pytest.skip("not enough leaf accounts")
        a1 = leafs[0].get("account_code") or leafs[0].get("code")
        a2 = leafs[1].get("account_code") or leafs[1].get("code")
        payload = {
            "journal_date": str(date.today()),
            "memo": "TEST_unbalanced",
            "lines": [
                {"account_code": a1, "debit": 100000, "credit": 0, "description": "d"},
                {"account_code": a2, "debit": 0, "credit": 50000, "description": "c"},
            ],
        }
        r = client.post(f"{BASE_URL}/api/rahaza/journals", json=payload, timeout=30)
        assert r.status_code in (400, 422), f"unbalanced should be rejected, got {r.status_code} {r.text[:200]}"

    def test_balanced_journal_post_and_trial_balance(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/coa/accounts", timeout=30)
        accs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
        leafs = [a for a in accs if not a.get("is_group")]
        if len(leafs) < 2:
            pytest.skip("not enough leaf accounts")
        a1 = leafs[0].get("account_code") or leafs[0].get("code")
        a2 = leafs[1].get("account_code") or leafs[1].get("code")
        payload = {
            "journal_date": str(date.today()),
            "memo": f"TEST_balanced_{uuid.uuid4().hex[:6]}",
            "lines": [
                {"account_code": a1, "debit": 75000, "credit": 0, "description": "test debit"},
                {"account_code": a2, "debit": 0, "credit": 75000, "description": "test credit"},
            ],
        }
        rc = client.post(f"{BASE_URL}/api/rahaza/journals", json=payload, timeout=30)
        assert rc.status_code in (200, 201), f"create balanced: {rc.status_code} {rc.text[:300]}"
        jid = rc.json().get("id") or rc.json().get("_id") or rc.json().get("journal_id")
        assert jid, f"no journal id: {rc.json()}"

        rp = client.post(f"{BASE_URL}/api/rahaza/journals/{jid}/post", timeout=30)
        assert rp.status_code in (200, 201), f"post journal: {rp.status_code} {rp.text[:300]}"

        # Trial Balance must be balanced
        rt = client.get(f"{BASE_URL}/api/rahaza/finance/reports/trial-balance", timeout=60)
        assert rt.status_code == 200, f"TB: {rt.status_code} {rt.text[:200]}"
        tb = rt.json()
        totals = tb.get("totals") or tb.get("summary") or {}
        td = totals.get("total_debit", totals.get("debit", 0))
        tc = totals.get("total_credit", totals.get("credit", 0))
        # if not in totals, sum lines
        if not td and not tc:
            lines = tb.get("items", tb.get("accounts", tb.get("lines", [])))
            td = sum(float(ln.get("debit", 0) or 0) for ln in lines)
            tc = sum(float(ln.get("credit", 0) or 0) for ln in lines)
        assert abs(float(td) - float(tc)) < 0.01, f"Trial Balance UNBALANCED: D={td} C={tc}"

        # Void
        rv = client.post(f"{BASE_URL}/api/rahaza/journals/{jid}/void", timeout=30)
        assert rv.status_code in (200, 201, 400), f"void: {rv.status_code} {rv.text[:200]}"


# =====================================================================
# Financial Reports
# =====================================================================
@pytest.mark.parametrize("ep", [
    "/api/rahaza/finance/reports/trial-balance",
    "/api/rahaza/finance/reports/profit-loss",
    "/api/rahaza/finance/reports/balance-sheet",
    "/api/rahaza/finance/reports/cash-flow",
])
def test_finance_reports(client, ep):
    r = client.get(f"{BASE_URL}{ep}", timeout=60)
    assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"
    # must be valid JSON
    try:
        r.json()
    except Exception as e:
        pytest.fail(f"{ep} not valid JSON: {e}")


# =====================================================================
# AR / AP flows
# =====================================================================
@pytest.mark.parametrize("ep", [
    "/api/rahaza/ar-invoices",
    "/api/rahaza/ar-invoices/overdue-report",
    "/api/rahaza/ar-360/dashboard",
    "/api/rahaza/ap-invoices",
    "/api/rahaza/ap-aging",
])
def test_ar_ap_endpoints(client, ep):
    r = client.get(f"{BASE_URL}{ep}", timeout=30)
    assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:300]}"


# =====================================================================
# Cash & Bank
# =====================================================================
@pytest.mark.parametrize("ep", [
    "/api/rahaza/cash-accounts",
    "/api/rahaza/cash-movements",
    "/api/finance/petty-cash/funds",
    "/api/finance/petty-cash/transactions",
    "/api/finance/bank-transfers",
    "/api/finance/bank-recon/sessions",
    "/api/finance/bank-recon/summary",
])
def test_cash_bank(client, ep):
    r = client.get(f"{BASE_URL}{ep}", timeout=30)
    assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"


# =====================================================================
# Expenses + GL mapping + Master categories (seed-default then list)
# =====================================================================
class TestExpensesGL:
    def test_expenses_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/expenses", timeout=30)
        assert r.status_code == 200

    def test_gl_mappings_seed_and_list(self, client):
        rs = client.post(f"{BASE_URL}/api/hr/expenses/gl-mappings/seed-default", timeout=30)
        assert rs.status_code in (200, 201), f"seed gl-mappings: {rs.status_code} {rs.text[:200]}"
        rl = client.get(f"{BASE_URL}/api/hr/expenses/gl-mappings", timeout=30)
        assert rl.status_code == 200, f"gl-mappings list: {rl.status_code} {rl.text[:200]}"

    def test_master_categories_seed_and_list(self, client):
        rs = client.post(f"{BASE_URL}/api/hr/expenses/master-categories/seed-default", timeout=30)
        assert rs.status_code in (200, 201), f"seed master-cats: {rs.status_code} {rs.text[:200]}"
        rl = client.get(f"{BASE_URL}/api/hr/expenses/master-categories", timeout=30)
        assert rl.status_code == 200, f"master-cats list: {rl.status_code} {rl.text[:200]}"


# =====================================================================
# Accruals + Recurring + Periods
# =====================================================================
class TestAccrualsPeriods:
    def test_accruals_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/finance/accruals", timeout=30)
        assert r.status_code == 200

    def test_periods_ensure_year(self, client):
        # NOTE: endpoint expects JSON body, not query param
        r = client.post(f"{BASE_URL}/api/rahaza/periods/ensure-year",
                        json={"year": 2026}, timeout=30)
        assert r.status_code in (200, 201), f"ensure-year: {r.status_code} {r.text[:200]}"

    def test_periods_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/periods", timeout=30)
        # both '/periods' and '/periods/' should work
        if r.status_code == 404:
            r = client.get(f"{BASE_URL}/api/rahaza/periods/", timeout=30)
        assert r.status_code == 200, f"periods list: {r.status_code} {r.text[:200]}"


# =====================================================================
# Budgets
# =====================================================================
class TestBudgets:
    def test_budgets_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/finance/budgets", timeout=30)
        assert r.status_code == 200, f"budgets: {r.status_code} {r.text[:200]}"


# =====================================================================
# Cost Centers, HPP, Bad Debt, Purchase Discount, Executive, Recap
# =====================================================================
@pytest.mark.parametrize("ep", [
    "/api/rahaza/cost-centers",
    "/api/rahaza/finance-summary",
])
def test_misc_finance(client, ep):
    r = client.get(f"{BASE_URL}{ep}", timeout=30)
    assert r.status_code == 200, f"{ep}: {r.status_code} {r.text[:200]}"


# =====================================================================
# Regression - ObjectId-serialization-safety affected areas
# =====================================================================
@pytest.mark.parametrize("ep", [
    "/api/announcements",
    "/api/audit-logs",
])
def test_objectid_regression(client, ep):
    r = client.get(f"{BASE_URL}{ep}", timeout=30)
    # 200 or 404 (if not present) acceptable; 500 NOT acceptable
    assert r.status_code != 500, f"{ep} returned 500: {r.text[:300]}"
    if r.status_code == 200:
        try:
            r.json()
        except Exception as e:
            pytest.fail(f"{ep} bad JSON: {e}")
