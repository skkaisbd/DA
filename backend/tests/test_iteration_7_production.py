"""
Iteration 7 - Production Portal Backend Tests
Focus: Production write-flows + multi-step chains + regression checks on:
  - qc.py operator-performance aggregate refactor (=> /api/qc/analytics/rework-by-operator)
  - dewi_predictive_maintenance.py _id:0 projections

Auth: admin@garment.com / Admin@123
Skip 503 (AI/WebPush) and 409 (admin-not-employee) as expected.
"""
import os
import time
import pytest
import requests

def _load_base_url():
    v = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not v:
        # Fallback: read from frontend/.env directly
        try:
            with open("/app/frontend/.env") as f:
                for line in f:
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        v = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return v.rstrip("/")


BASE_URL = _load_base_url()
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

EMAIL = "admin@garment.com"
PASSWORD = "Admin@123"

# ─────────────────────────── Fixtures ───────────────────────────
@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


def _ok(resp, allowed=(200, 201)):
    return resp.status_code in allowed


def _expected(resp):
    """Treat 503 (AI/WebPush) and 409 (admin-not-employee) as expected non-failures."""
    return resp.status_code in (503, 409)


# ─────────────────────────── Regression: QC operator-performance refactor ───────────────────────────
class TestQCRegression:
    def test_qc_rework_by_operator(self, client):
        r = client.get(f"{BASE_URL}/api/qc/analytics/rework-by-operator", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        assert isinstance(data, list)
        if data:
            row = data[0]
            assert "operator_name" in row
            assert "rework_rate_pct" in row
            assert "pass_rate_pct" in row
            # ensure no leaked _id
            assert "_id" not in row

    def test_qc_dashboard(self, client):
        r = client.get(f"{BASE_URL}/api/qc/dashboard", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        # Actual keys returned by qc.py qc_dashboard (verified against route)
        for k in ("total_inspections", "approved", "rework", "rejected", "pass_rate"):
            assert k in d, f"missing key {k} in qc dashboard response keys={list(d.keys())}"

    def test_qc_inspections_list(self, client):
        r = client.get(f"{BASE_URL}/api/qc/inspections", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Regression: Predictive Maintenance _id:0 projection ───────────────────────────
class TestPredictiveMaintenanceRegression:
    def test_pm_machines(self, client):
        r = client.get(f"{BASE_URL}/api/production/predictive-maintenance/machines", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        data = r.json()
        # Must not leak ObjectId
        if isinstance(data, list) and data:
            for m in data:
                assert "_id" not in m

    def test_pm_dashboard(self, client):
        r = client.get(f"{BASE_URL}/api/production/predictive-maintenance/dashboard", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert isinstance(d, dict)

    def test_pm_maintenance_logs(self, client):
        r = client.get(f"{BASE_URL}/api/production/predictive-maintenance/maintenance-logs", timeout=30)
        assert r.status_code == 200
        data = r.json()
        if isinstance(data, list):
            for log in data:
                assert "_id" not in log

    def test_pm_machine_health_if_machine_exists(self, client):
        # Pull a machine id and request its health (verifies _gather_machine_data projections)
        mr = client.get(f"{BASE_URL}/api/production/predictive-maintenance/machines", timeout=30)
        if mr.status_code != 200:
            pytest.skip(f"machines endpoint not OK: {mr.status_code}")
        machines = mr.json() if isinstance(mr.json(), list) else []
        if not machines:
            pytest.skip("No machines in DB to exercise machine_data projection")
        mid = machines[0].get("id") or machines[0].get("machine_id")
        if not mid:
            pytest.skip("Machine has no id field")
        r = client.get(f"{BASE_URL}/api/production/predictive-maintenance/machines/{mid}/health", timeout=30)
        # Must not 500 (the projection refactor should keep it healthy)
        assert r.status_code != 500, f"Machine health 500: {r.text}"


# ─────────────────────────── Production master data (read) ───────────────────────────
class TestProductionMasterData:
    def test_models(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/models", timeout=30)
        assert r.status_code == 200

    def test_sizes(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/sizes", timeout=30)
        assert r.status_code == 200

    def test_processes(self, client):
        # Processes used in execution
        r = client.get(f"{BASE_URL}/api/rahaza/processes", timeout=30)
        # accept 200 or 404 if not implemented as standalone resource
        assert r.status_code in (200, 404)

    def test_sop_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/sop", timeout=30)
        assert r.status_code == 200

    def test_bom_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/boms", timeout=30)
        assert r.status_code == 200

    def test_defect_codes(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/defect-codes", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Production Orders -> Work Orders chain ───────────────────────────
@pytest.fixture(scope="class")
def order_chain(client):
    """Create internal-mode order then return ids needed by chain tests.
    Creates a TEST model on-the-fly if no models exist in DB.
    """
    models = client.get(f"{BASE_URL}/api/rahaza/models", timeout=30).json()
    sizes = client.get(f"{BASE_URL}/api/rahaza/sizes", timeout=30).json()
    if not sizes:
        pytest.skip("No sizes exist - cannot create order")

    created_model_id = None
    if not models:
        # Create a TEST model so we can exercise the chain
        ts = int(time.time()) % 100000
        mr = client.post(f"{BASE_URL}/api/rahaza/models",
                        json={"code": f"TEST{ts}", "name": "TEST iter7 model",
                              "category": "Sweater", "yarn_kg_per_pcs": 0.5}, timeout=30)
        assert mr.status_code in (200, 201), f"create model failed: {mr.status_code} {mr.text}"
        created_model_id = mr.json()["id"]
        models = [mr.json()]

    model_id = models[0]["id"]
    size_id = sizes[0]["id"]

    payload = {
        "is_internal": True,
        "order_date": "2026-01-15",
        "due_date": "2026-02-15",
        "items": [{"model_id": model_id, "size_id": size_id, "qty": 50, "notes": "TEST iteration_7"}],
        "notes": "TEST_iter7_order",
    }
    r = client.post(f"{BASE_URL}/api/rahaza/orders", json=payload, timeout=30)
    assert r.status_code in (200, 201), f"create order failed: {r.status_code} {r.text}"
    order = r.json()
    yield {"order_id": order["id"], "order_number": order["order_number"],
           "model_id": model_id, "size_id": size_id, "created_model_id": created_model_id}

    # Cleanup
    try:
        client.delete(f"{BASE_URL}/api/rahaza/orders/{order['id']}", timeout=20)
    except Exception:
        pass
    if created_model_id:
        try:
            client.delete(f"{BASE_URL}/api/rahaza/models/{created_model_id}", timeout=20)
        except Exception:
            pass


class TestProductionChain:
    def test_order_persisted(self, client, order_chain):
        r = client.get(f"{BASE_URL}/api/rahaza/orders/{order_chain['order_id']}", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d["order_number"] == order_chain["order_number"]
        assert d["status"] == "draft"
        assert "_id" not in d

    def test_orders_list_includes_new(self, client, order_chain):
        r = client.get(f"{BASE_URL}/api/rahaza/orders", timeout=30)
        assert r.status_code == 200
        nums = [o.get("order_number") for o in r.json()]
        assert order_chain["order_number"] in nums

    def test_order_status_transition(self, client, order_chain):
        # Move to 'confirmed' or next valid status (route accepts JSON body with target status)
        r = client.post(
            f"{BASE_URL}/api/rahaza/orders/{order_chain['order_id']}/status",
            json={"status": "confirmed"}, timeout=30,
        )
        # Some impls require specific transitions; accept 200/400
        assert r.status_code in (200, 400), f"{r.status_code} {r.text}"

    def test_generate_work_orders(self, client, order_chain):
        # Move to confirmed first (required by WO gen)
        client.post(f"{BASE_URL}/api/rahaza/orders/{order_chain['order_id']}/status",
                   json={"status": "confirmed"}, timeout=30)
        r = client.post(
            f"{BASE_URL}/api/rahaza/orders/{order_chain['order_id']}/generate-work-orders",
            json={}, timeout=60,
        )
        assert r.status_code in (200, 201), f"{r.status_code} {r.text}"
        data = r.json()
        # Expect created list and total_created
        assert "created" in data
        assert "total_created" in data
        assert data["total_created"] >= 1
        assert isinstance(data["created"], list) and len(data["created"]) >= 1
        wo = data["created"][0]
        assert "id" in wo
        assert "wo_number" in wo
        assert "_id" not in wo
        order_chain["wo_id"] = wo["id"]

    def test_wo_persisted_and_visible(self, client, order_chain):
        wo_id = order_chain.get("wo_id")
        if not wo_id:
            pytest.skip("No WO generated in previous step")
        r = client.get(f"{BASE_URL}/api/rahaza/work-orders/{wo_id}", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        d = r.json()
        assert d["id"] == wo_id
        assert "_id" not in d

    def test_work_orders_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/work-orders", timeout=30)
        assert r.status_code == 200
        wos = r.json()
        if isinstance(wos, list) and wos:
            for wo in wos:
                assert "_id" not in wo

    def test_work_orders_statuses(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/work-orders-statuses", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Bundles & Cutting (reads, write-flow gated on data) ───────────────────────────
class TestBundlesCutting:
    def test_bundles_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/bundles", timeout=30)
        assert r.status_code == 200

    def test_bundles_statuses(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/bundles-statuses", timeout=30)
        assert r.status_code == 200

    def test_bundles_rework_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/bundles-rework", timeout=30)
        assert r.status_code == 200

    def test_cutting_requests(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cutting/requests", timeout=30)
        assert r.status_code == 200

    def test_cutting_batches(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cutting/batches", timeout=30)
        assert r.status_code == 200

    def test_cutting_summary(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cutting/summary", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Execution stages (reads + simple endpoints) ───────────────────────────
class TestExecution:
    def test_execution_my_work(self, client):
        # Endpoint requires query param operator_id; without it returns 400 (validation)
        # Admin is not linked to employee so 409 also acceptable.
        r = client.get(f"{BASE_URL}/api/rahaza/execution/my-work", timeout=30)
        assert r.status_code in (200, 400, 409), f"{r.status_code} {r.text}"

    def test_execution_flow_summary(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/execution/flow-summary", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"

    def test_execution_recent_events(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/execution/recent-events", timeout=30)
        assert r.status_code == 200

    def test_execution_history(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/execution/simple-input/history", timeout=30)
        assert r.status_code == 200

    def test_execution_process_board(self, client):
        # SEW/FIN/QC/PCK
        for code in ("sewing", "finishing", "qc", "packing"):
            r = client.get(f"{BASE_URL}/api/rahaza/execution/process/{code}/board", timeout=30)
            assert r.status_code in (200, 404), f"process {code}: {r.status_code} {r.text}"


# ─────────────────────────── Material Reservation & Returns ───────────────────────────
class TestMaterialFlow:
    def test_material_reservations_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/material-reservations", timeout=30)
        assert r.status_code == 200

    def test_material_returns_list(self, client):
        r = client.get(f"{BASE_URL}/api/production/material-returns", timeout=30)
        assert r.status_code == 200

    def test_material_returns_summary(self, client):
        r = client.get(f"{BASE_URL}/api/production/material-returns/summary", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── CMT lifecycle ───────────────────────────
class TestCMT:
    def test_cmt_partners(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/partners", timeout=30)
        assert r.status_code == 200

    def test_cmt_jobs(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/jobs", timeout=30)
        assert r.status_code == 200

    def test_cmt_deliveries(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/deliveries", timeout=30)
        assert r.status_code == 200

    def test_cmt_payments(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/payments", timeout=30)
        assert r.status_code == 200

    def test_cmt_summary(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/summary", timeout=30)
        assert r.status_code == 200

    def test_cmt_lifecycle_summary(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/lifecycle/summary", timeout=30)
        assert r.status_code == 200

    def test_cmt_progress_list(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/progress", timeout=30)
        assert r.status_code == 200

    def test_cmt_progress_daily(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/progress/daily-summary", timeout=30)
        assert r.status_code == 200

    def test_cmt_progress_monthly(self, client):
        # Endpoint requires year & month query params
        r = client.get(f"{BASE_URL}/api/dewi/cmt/progress/monthly-report?year=2026&month=1", timeout=30)
        assert r.status_code == 200, f"{r.status_code} {r.text}"

    def test_cmt_delivery_orders(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt/delivery-orders", timeout=30)
        assert r.status_code == 200

    def test_cmt_receipts(self, client):
        r = client.get(f"{BASE_URL}/api/prod/cmt-receipts", timeout=30)
        assert r.status_code == 200

    def test_cmt_receipts_summary(self, client):
        r = client.get(f"{BASE_URL}/api/prod/cmt-receipts/summary", timeout=30)
        assert r.status_code == 200

    def test_cmt_component_requests(self, client):
        r = client.get(f"{BASE_URL}/api/dewi/cmt-component-requests", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Monitoring/Analytics ───────────────────────────
class TestMonitoring:
    def test_line_monitoring_live(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/monitoring/live-status", timeout=30)
        assert r.status_code == 200

    def test_line_monitoring_alerts(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/monitoring/alerts", timeout=30)
        assert r.status_code == 200

    def test_andon_active(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/andon/active", timeout=30)
        assert r.status_code == 200

    def test_andon_history(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/andon/history", timeout=30)
        assert r.status_code == 200

    def test_oee_daily(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/oee/daily", timeout=30)
        assert r.status_code == 200

    def test_oee_summary(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/oee/summary", timeout=30)
        assert r.status_code == 200

    def test_downtime_list(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/downtime", timeout=30)
        assert r.status_code == 200

    def test_downtime_summary(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/downtime/summary", timeout=30)
        assert r.status_code == 200

    def test_downtime_reason_codes(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/downtime/reason-codes", timeout=30)
        assert r.status_code == 200

    def test_backlog(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/backlog", timeout=30)
        assert r.status_code == 200

    def test_production_calendar(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/production-calendar", timeout=30)
        assert r.status_code == 200

    def test_production_calendar_working_days(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/production-calendar/working-days?start=2026-01-01&end=2026-01-31", timeout=30)
        assert r.status_code in (200, 422), f"{r.status_code} {r.text}"


# ─────────────────────────── QC v2 + AQL + GRN-QC ───────────────────────────
class TestQCV2:
    def test_defect_codes_v2(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/defect-codes", timeout=30)
        assert r.status_code == 200

    def test_qc_events_v2(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/qc-events", timeout=30)
        assert r.status_code == 200

    def test_qc_pareto(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/qc/pareto", timeout=30)
        assert r.status_code == 200

    def test_qc_fpy(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/qc/fpy", timeout=30)
        assert r.status_code == 200

    def test_qc_summary(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/qc/summary", timeout=30)
        assert r.status_code == 200

    def test_aql_reference(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/aql/reference", timeout=30)
        assert r.status_code == 200

    def test_grn_inspections(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/grn-qc/grn-inspections", timeout=30)
        assert r.status_code == 200

    def test_grn_supplier_scorecard(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/grn-qc/supplier-scorecard", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Rework ───────────────────────────
class TestRework:
    def test_rework_settings(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/rework/settings", timeout=30)
        assert r.status_code == 200

    def test_rework_open(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/rework/open", timeout=30)
        assert r.status_code == 200

    def test_rework_summary(self, client):
        r = client.get(f"{BASE_URL}/api/rahaza/rework/summary", timeout=30)
        assert r.status_code == 200


# ─────────────────────────── Production Control Tower ───────────────────────────
class TestControlTower:
    def test_control_tower(self, client):
        r = client.get(f"{BASE_URL}/api/prod/control-tower", timeout=60)
        assert r.status_code == 200, f"{r.status_code} {r.text}"

    def test_control_tower_wo_list(self, client):
        r = client.get(f"{BASE_URL}/api/prod/control-tower/wo-list", timeout=60)
        assert r.status_code == 200

    def test_control_tower_alerts(self, client):
        r = client.get(f"{BASE_URL}/api/prod/control-tower/alerts", timeout=60)
        assert r.status_code == 200
