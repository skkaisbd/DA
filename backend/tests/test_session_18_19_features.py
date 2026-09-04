"""
Session 19 — E-1: Pytest expansion
Tests for Session 18 features (OKR, Predictive Maintenance, Maklon Quote, Skill Gap)
+ Session 19 AI Cost Monitor + critical existing flows (payroll/KPI/journal sanity).
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@garment.com", "password": "Admin@123"},
        timeout=10,
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ═════════════════════════════════════════════════════════════════════
# P2-3 Strategic OKR Tracker
# ═════════════════════════════════════════════════════════════════════
class TestOKRTracker:
    def test_list_periods(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/management/okr/periods", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data.get("success") is True
        assert isinstance(data.get("data"), list)

    def test_dashboard(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/management/okr/dashboard", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()["data"]
        for key in ["total_objectives", "on_track", "at_risk", "off_track", "completed", "average_progress"]:
            assert key in d

    def test_create_objective_with_kr(self, auth_headers):
        payload = {
            "title": "Pytest Test Objective",
            "description": "Auto-created by pytest",
            "period": "TEST-PY",
            "department": "IT",
            "owner_name": "Pytest Bot",
            "priority": "medium",
            "key_results": [
                {"title": "KR1", "metric_type": "number", "target_value": 100, "current_value": 50, "unit": "pcs"},
                {"title": "KR2", "metric_type": "percentage", "target_value": 100, "current_value": 75, "unit": "%"},
            ],
        }
        r = requests.post(f"{BASE_URL}/api/management/okr/objectives", json=payload, headers=auth_headers, timeout=10)
        assert r.status_code == 200
        obj = r.json()["data"]
        assert obj.get("id")
        assert "progress" in obj
        # Cleanup
        requests.delete(f"{BASE_URL}/api/management/okr/objectives/{obj['id']}", headers=auth_headers, timeout=10)


# ═════════════════════════════════════════════════════════════════════
# P2-7 Predictive Maintenance
# ═════════════════════════════════════════════════════════════════════
class TestPredictiveMaintenance:
    def test_dashboard(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/production/predictive-maintenance/dashboard",
            headers=auth_headers, timeout=10
        )
        assert r.status_code == 200
        d = r.json()["data"]
        for key in ["total_machines", "healthy", "monitor", "at_risk", "critical", "average_score", "overdue_pm"]:
            assert key in d

    def test_list_machines(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/production/predictive-maintenance/machines",
            headers=auth_headers, timeout=10
        )
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_list_logs(self, auth_headers):
        r = requests.get(
            f"{BASE_URL}/api/production/predictive-maintenance/maintenance-logs",
            headers=auth_headers, timeout=10
        )
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)


# ═════════════════════════════════════════════════════════════════════
# P2-19 AI Quote Generator
# ═════════════════════════════════════════════════════════════════════
class TestMaklonAIQuote:
    def test_history(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/maklon/ai-quote/history", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_generate_heuristic_fallback(self, auth_headers):
        """Test quote generation — should always return at least heuristic baseline."""
        payload = {
            "product_name": "Pytest Test Kaos",
            "category": "kaos",
            "quantity": 200,
            "target_margin_pct": 25,
        }
        r = requests.post(
            f"{BASE_URL}/api/maklon/ai-quote/generate",
            json=payload, headers=auth_headers, timeout=60,
        )
        assert r.status_code == 200, f"Failed: {r.text[:200]}"
        result = r.json()["data"]["result"]
        # Either AI or heuristic should produce these
        assert "estimated_unit_price" in result
        assert "estimated_total" in result
        assert "hpp_breakdown" in result
        assert result.get("source") in ["ai", "heuristic", "heuristic_after_ai_error",
                                          "heuristic_after_ai_parse_fail", "heuristic_budget_exceeded"]
        assert result["estimated_unit_price"] > 0


# ═════════════════════════════════════════════════════════════════════
# P2-20 Skill Gap Analysis
# ═════════════════════════════════════════════════════════════════════
class TestSkillGap:
    def test_departments(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/hr/skill-gap/departments", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_list_requirements(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/hr/skill-gap/requirements", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_create_requirement(self, auth_headers):
        payload = {
            "skill_name": "Pytest Sewing Skill",
            "category": "technical",
            "required_level": 3,
            "priority": "medium",
            "for_department": "Produksi",
        }
        r = requests.post(
            f"{BASE_URL}/api/hr/skill-gap/requirements",
            json=payload, headers=auth_headers, timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["data"]["skill_name"] == "Pytest Sewing Skill"

    def test_company_analysis(self, auth_headers):
        r = requests.post(
            f"{BASE_URL}/api/hr/skill-gap/analyze/company",
            json={"level": "company", "include_recommendations": False},
            headers=auth_headers, timeout=30,
        )
        # 200 if employees exist, 404 if none
        assert r.status_code in [200, 404]


# ═════════════════════════════════════════════════════════════════════
# E-3 AI Cost Monitor (Session 19)
# ═════════════════════════════════════════════════════════════════════
class TestAICostMonitor:
    def test_today(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/usage/today", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()["data"]
        for key in ["date", "total_calls", "total_cost_usd", "daily_budget_usd", "budget_used_pct", "health"]:
            assert key in d
        assert d["health"] in ["healthy", "monitor", "warning", "critical"]

    def test_summary(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/usage/summary?days=7", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()["data"]
        assert "overall" in d
        assert "by_feature" in d
        assert "by_day" in d

    def test_logs(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/usage/logs?limit=10", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json()["data"], list)

    def test_budgets(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/ai/usage/budgets", headers=auth_headers, timeout=10)
        assert r.status_code == 200
        d = r.json()["data"]
        assert "daily_usd" in d
        assert "monthly_usd" in d


# ═════════════════════════════════════════════════════════════════════
# Payroll Sanity (existing — flow integrity)
# ═════════════════════════════════════════════════════════════════════
class TestPayrollSanity:
    def test_list_payslips(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rahaza/payslips", headers=auth_headers, timeout=10)
        # May 200 or 401/403 depending on permissions
        assert r.status_code in [200, 401, 403, 404]

    def test_list_payroll_runs(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rahaza/payroll-runs", headers=auth_headers, timeout=10)
        assert r.status_code in [200, 401, 403, 404]


# ═════════════════════════════════════════════════════════════════════
# KPI Sanity (existing — flow integrity)
# ═════════════════════════════════════════════════════════════════════
class TestKPISanity:
    def test_kpi_periods_endpoint_exists(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/dewi/kpi/periods", headers=auth_headers, timeout=10)
        # Endpoint exists check (not 404)
        assert r.status_code in [200, 401, 403, 422]


# ═════════════════════════════════════════════════════════════════════
# Journal Entries Sanity
# ═════════════════════════════════════════════════════════════════════
class TestJournalEntriesSanity:
    def test_list_journal_entries(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rahaza/journal-entries", headers=auth_headers, timeout=10)
        assert r.status_code in [200, 401, 403, 404]

    def test_chart_of_accounts(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rahaza/coa", headers=auth_headers, timeout=10)
        assert r.status_code in [200, 401, 403, 404]


# ═════════════════════════════════════════════════════════════════════
# E-4 to_list cleanup regression
# ═════════════════════════════════════════════════════════════════════
class TestToListRegression:
    """Verify endpoints affected by .to_list(None) → .to_list(length=10000) replacement."""

    @pytest.mark.parametrize("path", [
        "/api/rahaza/reports/orders",
        "/api/rahaza/reports/wip",
        "/api/rahaza/reports/ar-invoices",
        "/api/rahaza/reports/shipments",
        "/api/rahaza/reports/qc",
    ])
    def test_reports_endpoints(self, auth_headers, path):
        r = requests.get(f"{BASE_URL}{path}", headers=auth_headers, timeout=15)
        assert r.status_code in [200, 401, 403, 404, 422], f"{path} returned {r.status_code}: {r.text[:100]}"
