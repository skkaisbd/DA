"""
Iteration 21 — Audit Gudang (WMS), Maklon, Marketing.
Regression guard: production seed must populate every previously-empty
collection/endpoint and fix the 4 critical regressions:
  1. Maklon dashboard client names (seed wrote company_name, app reads name)
  2. Marketing KOL leaderboard 500 (creator missing creator_code)
  3. LiveHost empty (wrong collection: marketing_livehost_hosts vs marketing_livehosts)
  4. Fulfillment queue empty (marketing_orders lacked fulfillment_status)
Plus: marketing-targets actuals (marketing_sales_data revenue_type=total).

Assumes the production seed (POST /api/seed/production-full) has been run.
Backed by /app/test_reports/iteration_21.json.
"""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="session")
def client():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return s


def _n(payload, *keys):
    """Return length of the first list found at top-level or under given keys."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for k in keys:
            v = payload.get(k)
            if isinstance(v, list):
                return len(v)
    return 0


# ───────────────────────── GUDANG / WMS ─────────────────────────
@pytest.mark.parametrize("path,keys,minimum", [
    ("/api/wms/legacy/locations", (), 5),
    ("/api/wms/legacy/stock", (), 10),
    ("/api/wms/legacy/receiving", (), 8),
    ("/api/wms/legacy/putaway", (), 3),
    ("/api/rahaza/material-stock", (), 15),
    ("/api/rahaza/material-movements", (), 20),
    ("/api/wms/cmt-dispatches", ("items",), 5),
    ("/api/wms/delivery-notes", ("items",), 6),
    ("/api/wms/fabric-rolls", ("items",), 10),
    ("/api/wms/opname2", ("items",), 3),
    ("/api/wms/buildings", (), 1),
    ("/api/rahaza/grn-qc/supplier-scorecard", (), 1),
    ("/api/wh/returns", (), 6),
    ("/api/fulfillment/inventory/available", ("items",), 5),
])
def test_gudang_endpoints_have_data(client, path, keys, minimum):
    r = client.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code} {r.text[:150]}"
    assert _n(r.json(), *keys) >= minimum, f"{path} returned too few rows"


def test_fulfillment_queue_populated(client):
    r = client.get(f"{BASE_URL}/api/fulfillment/summary", timeout=30)
    assert r.status_code == 200
    s = r.json()
    active = sum(s.get(k, 0) for k in ("pending_fulfillment", "allocated", "picking", "packed_ready"))
    assert active > 0, f"Fulfillment queue empty: {s}"


# ───────────────────────── MAKLON ─────────────────────────
def test_maklon_pos_and_client_names(client):
    r = client.get(f"{BASE_URL}/api/dewi/maklon/pos", timeout=30)
    assert r.status_code == 200
    pos = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert len(pos) >= 5, "Expected >=5 maklon POs"
    # Regression: client_name must be populated (not blank)
    assert any((p.get("client_name") or "").strip() for p in pos), "Maklon PO client_name blank"


@pytest.mark.parametrize("path,minimum", [
    ("/api/dewi/maklon/samples", 5),
    ("/api/dewi/maklon/invoices", 3),
    ("/api/dewi/maklon/payments", 3),
    ("/api/dewi/maklon/qc", 8),
    ("/api/dewi/maklon/dispatches", 4),
])
def test_maklon_subendpoints(client, path, minimum):
    r = client.get(f"{BASE_URL}{path}", timeout=30)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    assert _n(r.json(), "items", "data") >= minimum, f"{path} too few rows"


# ───────────────────────── MARKETING ─────────────────────────
def test_kol_leaderboard_no_500(client):
    """Regression: leaderboard used to 500 on missing creator_code."""
    r = client.get(f"{BASE_URL}/api/marketing/kol/leaderboard", timeout=30)
    assert r.status_code == 200, f"leaderboard -> {r.status_code} {r.text[:150]}"
    assert _n(r.json(), "leaderboard") >= 1


def test_livehosts_populated(client):
    """Regression: hosts written to wrong collection name."""
    r = client.get(f"{BASE_URL}/api/marketing/livehost", timeout=30)
    assert r.status_code == 200
    assert _n(r.json()) >= 4, "Expected >=4 live hosts"


def test_livehost_analytics(client):
    r = client.get(f"{BASE_URL}/api/marketing/livehost/analytics/host-performance", timeout=30)
    assert r.status_code == 200
    assert r.json().get("total_hosts", 0) >= 1


def test_targets_actuals_populated(client):
    """Regression: monthly-summary actual revenue was Rp 0 (marketing_sales_data empty)."""
    r = client.get(f"{BASE_URL}/api/marketing/targets/monthly-summary", timeout=30)
    assert r.status_code == 200
    summary = r.json().get("summary", {})
    assert summary.get("rev_actual", 0) > 0, f"Targets actual revenue is 0: {summary}"
    assert summary.get("ord_actual", 0) > 0
