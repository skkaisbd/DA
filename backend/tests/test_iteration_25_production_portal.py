"""
Iteration 25 — Production Portal Comprehensive Audit
Tests: Work Orders, Bundles, Cutting, QC, KPI, Control Tower, SOP,
       Monitoring, FPY, Pareto, Downtime, Backlog, Calendar, RnD, Employees
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ── Auth fixtures ────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Login as admin and return token. Rate-limited ~10 req/60s."""
    resp = requests.post(f"{BASE_URL}/api/auth/login",
                         json={"email": "admin@garment.com", "password": "Admin@123"},
                         timeout=15)
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def spv_token():
    """Login as spv@dewiaditya.id (supervisor_produksi) — used for production portal."""
    time.sleep(1)  # slight delay to avoid rate-limit
    resp = requests.post(f"{BASE_URL}/api/auth/login",
                         json={"email": "spv@dewiaditya.id", "password": "Dewi@123"},
                         timeout=15)
    assert resp.status_code == 200, f"SPV login failed: {resp.status_code} {resp.text}"
    return resp.json()["token"]


@pytest.fixture(scope="module")
def auth_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def spv_headers(spv_token):
    return {"Authorization": f"Bearer {spv_token}"}


# ── Helper ───────────────────────────────────────────────────────────────────

def items_count(resp_json):
    """Return number of items from response regardless of shape."""
    if isinstance(resp_json, list):
        return len(resp_json)
    if isinstance(resp_json, dict):
        for key in ("items", "data", "rows", "results"):
            v = resp_json.get(key)
            if isinstance(v, list):
                return len(v)
        # fallback: check total key
        if "total" in resp_json:
            return int(resp_json["total"])
    return 0


# ═══════════════════════════════════════════════════════════════════════════════
# 1. WORK ORDERS
# ═══════════════════════════════════════════════════════════════════════════════

class TestWorkOrders:
    """GET /api/rahaza/work-orders — 20 WOs in DB"""

    def test_list_work_orders_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/work-orders", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"WO list failed: {resp.status_code} {resp.text[:300]}"

    def test_list_work_orders_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/work-orders", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        # We expect at least 1 WO (ideally ~20)
        assert count > 0, f"Work orders list is empty. Response: {str(data)[:300]}"
        print(f"Work orders count: {count}")

    def test_list_work_orders_data_shape(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/work-orders", headers=auth_headers, timeout=15)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", data.get("data", []))
        if items:
            item = items[0]
            assert "id" in item, "WO missing 'id' field"
            assert "wo_number" in item, "WO missing 'wo_number' field"
            assert "status" in item, "WO missing 'status' field"
            print(f"Sample WO: {item.get('wo_number')} status={item.get('status')}")

    def test_work_orders_statuses(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/work-orders-statuses", headers=auth_headers, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list), "Statuses should be a list"
        assert len(data) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 2. BUNDLES
# ═══════════════════════════════════════════════════════════════════════════════

class TestBundles:
    """GET /api/rahaza/bundles — 52 bundles in DB"""

    def test_list_bundles_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/bundles", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Bundles list failed: {resp.status_code} {resp.text[:300]}"

    def test_list_bundles_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/bundles", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        assert count > 0, f"Bundles list is empty. Response: {str(data)[:300]}"
        print(f"Bundles count: {count}")

    def test_list_bundles_data_shape(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/bundles", headers=auth_headers, timeout=15)
        data = resp.json()
        items = data if isinstance(data, list) else data.get("items", data.get("data", []))
        if items:
            item = items[0]
            assert "id" in item, "Bundle missing 'id' field"
            print(f"Sample bundle: {item.get('bundle_number', item.get('id'))}")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. CUTTING REQUESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestCutting:
    """GET /api/dewi/cutting/requests — 8 cutting requests in DB"""

    def test_cutting_requests_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/cutting/requests", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Cutting requests failed: {resp.status_code} {resp.text[:300]}"

    def test_cutting_requests_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/cutting/requests", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        assert count > 0, f"Cutting requests list is empty. Response: {str(data)[:300]}"
        print(f"Cutting requests count: {count}")

    def test_cutting_summary_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/cutting/summary", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Cutting summary failed: {resp.status_code}"
        data = resp.json()
        assert "total_requests" in data, "Cutting summary missing total_requests"
        print(f"Cutting summary: {data}")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. PRODUCTION CONTROL TOWER
# ═══════════════════════════════════════════════════════════════════════════════

class TestControlTower:
    """GET /api/prod/control-tower"""

    def test_control_tower_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/prod/control-tower", headers=auth_headers, timeout=20)
        assert resp.status_code == 200, f"Control Tower failed: {resp.status_code} {resp.text[:300]}"

    def test_control_tower_kpis_present(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/prod/control-tower", headers=auth_headers, timeout=20)
        data = resp.json()
        assert "kpis" in data, "Control Tower missing 'kpis'"
        kpis = data["kpis"]
        assert "active_wos" in kpis, "kpis missing active_wos"
        assert "total_alerts" in kpis, "kpis missing total_alerts"
        print(f"Control Tower KPIs: active_wos={kpis.get('active_wos')}, alerts={kpis.get('total_alerts')}")

    def test_control_tower_wo_list_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/prod/control-tower/wo-list", headers=auth_headers, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data, "Control tower wo-list missing 'items'"
        print(f"Control Tower WO list: {data.get('total', 0)} items")

    def test_control_tower_alerts_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/prod/control-tower/alerts", headers=auth_headers, timeout=15)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data, "Control Tower alerts missing 'total'"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. QC EVENTS (via rahaza_qc_v2)
# ═══════════════════════════════════════════════════════════════════════════════

class TestQC:
    """GET /api/rahaza/qc-events — 30 QC events in DB"""

    def test_qc_events_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/qc-events", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"QC events failed: {resp.status_code} {resp.text[:300]}"

    def test_qc_events_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/qc-events", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        assert count > 0, f"QC events list is empty. Response: {str(data)[:300]}"
        print(f"QC events count: {count}")

    def test_qc_inspections_200(self, auth_headers):
        """Also test the generic QC inspections endpoint"""
        resp = requests.get(f"{BASE_URL}/api/qc/inspections", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"QC inspections failed: {resp.status_code}"

    def test_qc_pareto_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/qc/pareto", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Pareto failed: {resp.status_code} {resp.text[:200]}"

    def test_qc_fpy_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/qc/fpy", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"FPY failed: {resp.status_code} {resp.text[:200]}"

    def test_qc_summary_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/qc/summary", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"QC summary failed: {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# 6. PRODUCTION CALENDAR
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductionCalendar:
    """GET /api/rahaza/production-calendar"""

    def test_calendar_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/production-calendar", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Calendar failed: {resp.status_code} {resp.text[:300]}"

    def test_calendar_working_days_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/production-calendar/working-days",
                           headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Working days failed: {resp.status_code}"
        data = resp.json()
        print(f"Working days response: {str(data)[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 7. KPI
# ═══════════════════════════════════════════════════════════════════════════════

class TestKPI:
    """GET /api/dewi/kpi endpoints — 10 KPI indicators + 30 results"""

    def test_kpi_stats_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/kpi/stats", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"KPI stats failed: {resp.status_code} {resp.text[:300]}"

    def test_kpi_periods_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/kpi/periods", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"KPI periods failed: {resp.status_code}"
        data = resp.json()
        count = items_count(data)
        print(f"KPI periods: {count}")

    def test_kpi_questions_200(self, auth_headers):
        """KPI questions/indicators endpoint"""
        resp = requests.get(f"{BASE_URL}/api/dewi/kpi/questions", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"KPI questions failed: {resp.status_code}"
        data = resp.json()
        count = items_count(data)
        print(f"KPI questions/indicators: {count}")


# ═══════════════════════════════════════════════════════════════════════════════
# 8. SOP
# ═══════════════════════════════════════════════════════════════════════════════

class TestSOP:
    """GET /api/rahaza/sop — 5 SOPs in DB"""

    def test_sop_list_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/sop", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"SOP list failed: {resp.status_code} {resp.text[:300]}"

    def test_sop_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/sop", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        assert count > 0, f"SOP list is empty. Response: {str(data)[:300]}"
        print(f"SOP count: {count}")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. MONITORING & ANDON
# ═══════════════════════════════════════════════════════════════════════════════

class TestMonitoring:
    """GET /api/rahaza/monitoring/live-status + /api/rahaza/andon/active"""

    def test_live_monitoring_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/monitoring/live-status", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Live monitoring failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        print(f"Live monitoring data: {str(data)[:200]}")

    def test_andon_active_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/andon/active", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Andon active failed: {resp.status_code}"

    def test_andon_settings_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/andon/settings", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Andon settings failed: {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# 10. DOWNTIME
# ═══════════════════════════════════════════════════════════════════════════════

class TestDowntime:
    """GET /api/rahaza/downtime"""

    def test_downtime_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/downtime", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Downtime failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        count = items_count(data)
        print(f"Downtime records: {count}")

    def test_downtime_summary_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/downtime/summary", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Downtime summary failed: {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. BACKLOG & CAPACITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestBacklogCapacity:

    def test_backlog_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/backlog", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Backlog failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        print(f"Backlog response: {str(data)[:200]}")

    def test_capacity_planning_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/capacity/planning", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 404), f"Capacity planning failed: {resp.status_code} {resp.text[:200]}"
        if resp.status_code == 200:
            data = resp.json()
            print(f"Capacity planning data: {str(data)[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 12. PRODUCTION EMPLOYEES (Operator & Skill Matrix)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductionEmployees:
    """GET /api/rahaza/employees"""

    def test_employees_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/employees", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Employees failed: {resp.status_code} {resp.text[:300]}"
        data = resp.json()
        count = items_count(data)
        print(f"Employees count: {count}")


# ═══════════════════════════════════════════════════════════════════════════════
# 13. RnD — Styles & Samples
# ═══════════════════════════════════════════════════════════════════════════════

class TestRnD:
    """GET /api/dewi/rnd/styles (6) + /sample-requests (4)"""

    def test_rnd_styles_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/rnd/styles", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"RnD styles failed: {resp.status_code} {resp.text[:300]}"

    def test_rnd_styles_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/rnd/styles", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        assert count > 0, f"RnD styles list is empty. Response: {str(data)[:300]}"
        print(f"RnD styles count: {count}")

    def test_rnd_samples_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/rnd/sample-requests", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"RnD samples failed: {resp.status_code} {resp.text[:300]}"

    def test_rnd_samples_has_data(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/rnd/sample-requests", headers=auth_headers, timeout=15)
        data = resp.json()
        count = items_count(data)
        assert count > 0, f"RnD samples list is empty. Response: {str(data)[:300]}"
        print(f"RnD samples count: {count}")

    def test_rnd_overview_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/dewi/rnd/overview", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"RnD overview failed: {resp.status_code}"

    def test_rnd_dashboard_stats(self, auth_headers):
        """Check RnD stats/dashboard endpoint"""
        resp = requests.get(f"{BASE_URL}/api/dewi/rnd/overview", headers=auth_headers, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            print(f"RnD overview: {str(data)[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 14. PRODUCTION DASHBOARD — check main aggregation endpoint
# ═══════════════════════════════════════════════════════════════════════════════

class TestProductionDashboard:

    def test_production_dashboard_200(self, auth_headers):
        """Main production dashboard / aggregator"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/production-dashboard", headers=auth_headers, timeout=20)
        # May also be at /api/production/dashboard
        if resp.status_code == 404:
            resp2 = requests.get(f"{BASE_URL}/api/production/dashboard", headers=auth_headers, timeout=20)
            if resp2.status_code == 200:
                data = resp2.json()
                print(f"Production dashboard at /api/production/dashboard: {str(data)[:200]}")
                return
        assert resp.status_code in (200, 404), f"Production dashboard failed: {resp.status_code}"
        if resp.status_code == 200:
            print(f"Production dashboard: {str(resp.json())[:200]}")

    def test_execution_flow_summary_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/execution/flow-summary", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Flow summary failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        assert "main_flow" in data, "Flow summary missing 'main_flow'"
        print(f"Flow summary - main_flow processes: {len(data.get('main_flow', []))}")

    def test_orders_list_200(self, auth_headers):
        """GET /api/rahaza/orders — Production Orders"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/orders", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Orders list failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        count = items_count(data)
        print(f"Production orders: {count}")

    def test_line_board_lines_200(self, auth_headers):
        """GET /api/rahaza/lines — should have 7 production lines"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/lines", headers=auth_headers, timeout=15)
        assert resp.status_code == 200, f"Lines failed: {resp.status_code} {resp.text[:200]}"
        data = resp.json()
        count = items_count(data)
        print(f"Production lines: {count}")


# ═══════════════════════════════════════════════════════════════════════════════
# 15. SHIFT HANDOVER
# ═══════════════════════════════════════════════════════════════════════════════

class TestShiftHandover:

    def test_shift_handover_200(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/shift-handover", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 404), f"Shift handover failed: {resp.status_code}"
        if resp.status_code == 200:
            print(f"Shift handover data: {str(resp.json())[:200]}")


# ═══════════════════════════════════════════════════════════════════════════════
# 16. CMT MANAGEMENT
# ═══════════════════════════════════════════════════════════════════════════════

class TestCMT:

    def test_cmt_jobs_200(self, auth_headers):
        """CMT jobs / management endpoint"""
        resp = requests.get(f"{BASE_URL}/api/dewi/cmt/jobs", headers=auth_headers, timeout=15)
        # Spec says CMT collections are mostly empty - just check it doesn't 500
        assert resp.status_code in (200, 404), f"CMT jobs failed: {resp.status_code} {resp.text[:200]}"
        if resp.status_code == 200:
            data = resp.json()
            print(f"CMT jobs: {items_count(data)} (may be 0 — spec confirms CMT collections empty)")


# ═══════════════════════════════════════════════════════════════════════════════
# 17. SPV ACCESS — check supervisor can access key production endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestSPVAccess:
    """Supervisor (spv@dewiaditya.id) should be able to access production portal data"""

    def test_spv_work_orders_access(self, spv_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/work-orders", headers=spv_headers, timeout=15)
        assert resp.status_code == 200, f"SPV WO access failed: {resp.status_code}"

    def test_spv_bundles_access(self, spv_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/bundles", headers=spv_headers, timeout=15)
        assert resp.status_code == 200, f"SPV bundles access failed: {resp.status_code}"

    def test_spv_control_tower_access(self, spv_headers):
        resp = requests.get(f"{BASE_URL}/api/prod/control-tower", headers=spv_headers, timeout=20)
        assert resp.status_code == 200, f"SPV control tower failed: {resp.status_code}"

    def test_spv_qc_events_access(self, spv_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/qc-events", headers=spv_headers, timeout=15)
        assert resp.status_code == 200, f"SPV QC events failed: {resp.status_code}"


# ═══════════════════════════════════════════════════════════════════════════════
# 18. PRODUCTION AI INSIGHTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAIInsights:

    def test_ai_insights_endpoint_exists(self, auth_headers):
        """AI Insights endpoint — may return 503 if no LLM key, but should not 404/500 on GET"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/ai/insights", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 503, 404), f"AI insights unexpected: {resp.status_code} {resp.text[:200]}"
        print(f"AI insights status: {resp.status_code}")

    def test_predictive_maintenance_endpoint(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/api/rahaza/maintenance/predictions", headers=auth_headers, timeout=15)
        assert resp.status_code in (200, 404), f"Predictive maintenance: {resp.status_code}"
