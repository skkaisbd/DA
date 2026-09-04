"""
Session 28 Feature Tests
========================
Tests for new Portal Marketing features:
1. Marketing Account Monthly Targets (GET/POST /api/marketing/targets)
2. Marketing Reports - Daily (GET /api/marketing/reports/daily)
3. Marketing Reports - Monthly (GET /api/marketing/reports/monthly)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


@pytest.fixture(scope="module")
def auth_token():
    """Get auth token for admin account."""
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garnet.com",  # wrong email to trigger skip
    })
    # Try correct credentials
    res = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123",
    })
    if res.status_code == 200:
        data = res.json()
        token = data.get("token") or data.get("access_token")
        if token:
            return token
    pytest.skip(f"Authentication failed (status {res.status_code}) — skipping all tests")


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ── TEST: AUTH ────────────────────────────────────────────────────────────────

class TestAuth:
    """Verify admin login works correctly."""

    def test_login_success(self):
        res = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "admin@garment.com",
            "password": "Admin@123",
        })
        assert res.status_code == 200, f"Login failed: {res.text}"
        data = res.json()
        assert "token" in data or "access_token" in data, "No token in response"


# ── TEST: MARKETING TARGETS ───────────────────────────────────────────────────

class TestMarketingTargets:
    """Tests for /api/marketing/targets endpoints."""

    def test_get_targets_requires_auth(self):
        """GET targets without auth returns 401 or 403."""
        res = requests.get(f"{BASE_URL}/api/marketing/targets")
        assert res.status_code in (401, 403), f"Expected 401/403, got {res.status_code}"

    def test_get_targets_current_month(self, headers):
        """GET targets for current month returns valid list."""
        res = requests.get(f"{BASE_URL}/api/marketing/targets", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"

    def test_get_targets_specific_month(self, headers):
        """GET targets for specific year/month works."""
        res = requests.get(f"{BASE_URL}/api/marketing/targets?year=2026&month=2", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert isinstance(data, list)

    def test_get_targets_monthly_summary(self, headers):
        """GET /api/marketing/targets/monthly-summary returns period + accounts."""
        res = requests.get(f"{BASE_URL}/api/marketing/targets/monthly-summary?year=2026&month=2", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert "period" in data, "Missing 'period' key in response"
        assert "accounts" in data, "Missing 'accounts' key in response"
        assert "summary" in data, "Missing 'summary' key in response"
        # Validate period structure
        period = data["period"]
        assert period["year"] == 2026
        assert period["month"] == 2
        # Validate accounts is a list
        assert isinstance(data["accounts"], list), "accounts should be a list"

    def test_monthly_summary_account_structure(self, headers):
        """Monthly summary account rows have required fields."""
        res = requests.get(f"{BASE_URL}/api/marketing/targets/monthly-summary?year=2026&month=2", headers=headers)
        assert res.status_code == 200
        data = res.json()
        if data["accounts"]:
            row = data["accounts"][0]
            assert "account_id" in row
            assert "account_name" in row
            assert "target" in row
            assert "actual" in row
            assert "achievement" in row
            assert "task_stats" in row
            # Validate target sub-fields
            tgt = row["target"]
            assert "revenue" in tgt
            assert "orders" in tgt
            assert "health_score" in tgt
            # Validate actual sub-fields
            actual = row["actual"]
            assert "revenue" in actual
            assert "orders" in actual
            assert "sales_days" in actual

    def test_upsert_target_missing_auth(self):
        """POST target without auth returns 401/403."""
        res = requests.post(f"{BASE_URL}/api/marketing/targets", json={
            "account_id": "test-id",
            "year": 2026,
            "month": 2,
            "revenue_target": 50_000_000,
            "orders_target": 500,
            "health_score_target": 80,
        })
        assert res.status_code in (401, 403), f"Expected 401/403, got {res.status_code}"

    def test_upsert_target_invalid_account(self, headers):
        """POST target for non-existent account returns 404."""
        res = requests.post(f"{BASE_URL}/api/marketing/targets", json={
            "account_id": "non-existent-account-id-xyz",
            "year": 2026,
            "month": 2,
            "revenue_target": 50_000_000,
            "orders_target": 500,
            "health_score_target": 80,
        }, headers=headers)
        assert res.status_code == 404, f"Expected 404 for non-existent account, got {res.status_code}: {res.text}"

    def test_upsert_target_for_existing_account(self, headers):
        """POST target for an existing account succeeds."""
        # First get any active account
        acc_res = requests.get(f"{BASE_URL}/api/marketing/accounts?status=active", headers=headers)
        if acc_res.status_code != 200 or not acc_res.json():
            pytest.skip("No active accounts found to test target upsert")

        accounts = acc_res.json()
        if not isinstance(accounts, list) or not accounts:
            pytest.skip("No accounts available")

        # Use the accounts list (could be a dict with 'accounts' key or a direct list)
        if isinstance(accounts, dict):
            acc_list = accounts.get("accounts", [])
        else:
            acc_list = accounts

        if not acc_list:
            pytest.skip("No accounts available")

        acc = acc_list[0]
        acc_id = acc.get("id")

        res = requests.post(f"{BASE_URL}/api/marketing/targets", json={
            "account_id": acc_id,
            "year": 2026,
            "month": 1,   # Use Jan 2026 to not interfere with current month tests
            "revenue_target": 10_000_000,
            "orders_target": 100,
            "health_score_target": 75,
            "notes": "TEST_session28_target",
        }, headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert "target" in data, f"No 'target' key in response: {data}"
        tgt = data["target"]
        assert tgt["account_id"] == acc_id
        assert tgt["revenue_target"] == 10_000_000
        assert tgt["orders_target"] == 100
        assert tgt["health_score_target"] == 75

    def test_upsert_target_upsert_behavior(self, headers):
        """POST target twice for same (account, year, month) → updates, not duplicates."""
        acc_res = requests.get(f"{BASE_URL}/api/marketing/accounts?status=active", headers=headers)
        if acc_res.status_code != 200:
            pytest.skip("Cannot get accounts")
        accounts = acc_res.json()
        if isinstance(accounts, dict):
            acc_list = accounts.get("accounts", [])
        else:
            acc_list = accounts
        if not acc_list:
            pytest.skip("No accounts available")

        acc_id = acc_list[0].get("id")
        payload = {
            "account_id": acc_id,
            "year": 2026,
            "month": 1,
            "revenue_target": 20_000_000,
            "orders_target": 200,
            "health_score_target": 85,
        }
        res1 = requests.post(f"{BASE_URL}/api/marketing/targets", json=payload, headers=headers)
        assert res1.status_code == 200

        # Update same period
        payload["revenue_target"] = 25_000_000
        res2 = requests.post(f"{BASE_URL}/api/marketing/targets", json=payload, headers=headers)
        assert res2.status_code == 200
        data2 = res2.json()
        tgt2 = data2["target"]
        assert tgt2["revenue_target"] == 25_000_000, "Upsert should update revenue_target"

        # Verify only one target exists for this period
        get_res = requests.get(
            f"{BASE_URL}/api/marketing/targets?account_id={acc_id}&year=2026&month=1",
            headers=headers
        )
        assert get_res.status_code == 200
        targets = get_res.json()
        assert isinstance(targets, list)
        # Should have at most 1 target for this account+year+month
        matching = [t for t in targets if t.get("account_id") == acc_id]
        assert len(matching) <= 1, f"Expected max 1 target, got {len(matching)}"


# ── TEST: DAILY REPORT ────────────────────────────────────────────────────────

class TestDailyReport:
    """Tests for GET /api/marketing/reports/daily."""

    def test_daily_report_requires_auth(self):
        """Without auth, daily report returns 401/403."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/daily")
        assert res.status_code in (401, 403), f"Expected 401/403, got {res.status_code}"

    def test_daily_report_default_date(self, headers):
        """GET daily report without date uses yesterday."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/daily", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert "summary" in data, "Missing 'summary' key"
        assert "accounts" in data, "Missing 'accounts' key"
        assert "target_date" in data, "Missing 'target_date' key"
        assert "generated_at" in data, "Missing 'generated_at' key"

    def test_daily_report_specific_date(self, headers):
        """GET daily report with specific date."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/daily?date=2026-02-01", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert data["target_date"] == "2026-02-01", f"Expected target_date='2026-02-01', got '{data.get('target_date')}'"

    def test_daily_report_summary_structure(self, headers):
        """Daily report summary has correct KPI fields."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/daily", headers=headers)
        assert res.status_code == 200
        s = res.json()["summary"]
        assert "accounts_total" in s, "Missing accounts_total"
        assert "accounts_sales_entered" in s, "Missing accounts_sales_entered"
        assert "accounts_sales_missing" in s, "Missing accounts_sales_missing"
        assert "sales_input_rate" in s, "Missing sales_input_rate"
        assert "tasks_done_today" in s, "Missing tasks_done_today"
        assert "tasks_overdue" in s, "Missing tasks_overdue"
        assert "tasks_pending_approval" in s, "Missing tasks_pending_approval"
        # Check numeric types
        assert isinstance(s["accounts_total"], int), "accounts_total should be int"
        assert isinstance(s["sales_input_rate"], (int, float)), "sales_input_rate should be numeric"

    def test_daily_report_accounts_structure(self, headers):
        """Daily report accounts rows have required fields."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/daily", headers=headers)
        assert res.status_code == 200
        data = res.json()
        accounts = data["accounts"]
        assert isinstance(accounts, list), "accounts should be a list"
        if accounts:
            row = accounts[0]
            assert "account_id" in row
            assert "account_name" in row
            assert "account_code" in row
            assert "platform" in row
            assert "sales_status" in row
            ss = row["sales_status"]
            assert "entered_total" in ss, "Missing entered_total in sales_status"
            assert "entered_live" in ss, "Missing entered_live in sales_status"
            assert "revenue" in ss, "Missing revenue in sales_status"
            assert "orders" in ss, "Missing orders in sales_status"
            assert "pending_action_tasks" in row, "Missing pending_action_tasks"
            assert "overdue_count" in row, "Missing overdue_count"

    def test_daily_report_math_consistency(self, headers):
        """entered + missing should equal total accounts."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/daily", headers=headers)
        assert res.status_code == 200
        s = res.json()["summary"]
        assert s["accounts_sales_entered"] + s["accounts_sales_missing"] == s["accounts_total"], \
            f"entered({s['accounts_sales_entered']}) + missing({s['accounts_sales_missing']}) != total({s['accounts_total']})"


# ── TEST: MONTHLY REPORT ──────────────────────────────────────────────────────

class TestMonthlyReport:
    """Tests for GET /api/marketing/reports/monthly."""

    def test_monthly_report_requires_auth(self):
        """Without auth, monthly report returns 401/403."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/monthly")
        assert res.status_code in (401, 403), f"Expected 401/403, got {res.status_code}"

    def test_monthly_report_default_period(self, headers):
        """GET monthly report without params returns current month."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/monthly", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        assert "period" in data, "Missing 'period' key"
        assert "summary" in data, "Missing 'summary' key"
        assert "accounts" in data, "Missing 'accounts' key"

    def test_monthly_report_specific_period(self, headers):
        """GET monthly report with year/month params."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/monthly?year=2026&month=1", headers=headers)
        assert res.status_code == 200, f"Status {res.status_code}: {res.text}"
        data = res.json()
        period = data["period"]
        assert period["year"] == 2026
        assert period["month"] == 1

    def test_monthly_report_summary_fields(self, headers):
        """Monthly report summary has all required KPI fields."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/monthly", headers=headers)
        assert res.status_code == 200
        s = res.json()["summary"]
        assert "total_accounts" in s, "Missing total_accounts"
        assert "rev_target" in s, "Missing rev_target"
        assert "rev_actual" in s, "Missing rev_actual"
        assert "ord_target" in s, "Missing ord_target"
        assert "ord_actual" in s, "Missing ord_actual"
        assert "task_completion" in s, "Missing task_completion"
        assert "avg_sales_input_rate" in s, "Missing avg_sales_input_rate"

    def test_monthly_report_account_row_structure(self, headers):
        """Monthly report account rows have complete structure."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/monthly", headers=headers)
        assert res.status_code == 200
        data = res.json()
        if data["accounts"]:
            row = data["accounts"][0]
            assert "account_id" in row
            assert "account_name" in row
            assert "target" in row
            assert "actual" in row
            assert "achievement" in row
            assert "task_stats" in row
            assert "daily_chart" in row, "Missing daily_chart for per-day mini chart"
            # Check achievement status values are valid
            ach = row["achievement"]
            assert "revenue_pct" in ach
            assert "orders_pct" in ach
            assert "revenue_status" in ach
            assert "orders_status" in ach
            if ach["revenue_status"] is not None:
                assert ach["revenue_status"] in ("on_track", "warning", "behind", "no_target"), \
                    f"Unexpected status value: {ach['revenue_status']}"

    def test_monthly_report_actual_input_rate_range(self, headers):
        """Monthly report actual.input_rate is between 0 and 100."""
        res = requests.get(f"{BASE_URL}/api/marketing/reports/monthly", headers=headers)
        assert res.status_code == 200
        data = res.json()
        for row in data["accounts"]:
            rate = row["actual"]["input_rate"]
            assert 0 <= rate <= 100, f"input_rate={rate} out of range [0,100] for account {row['account_name']}"
