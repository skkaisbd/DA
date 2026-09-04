"""
Backend tests for Kasbon & Pinjaman endpoints (Phase 12)
Tests: POST/GET requests, HR review, Finance disburse, stats, seed
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    data = r.json()
    return data.get("token") or data.get("access_token")

@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# ─── Stats ────────────────────────────────────────────────────────────────────
def test_kasbon_stats(auth_headers):
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/stats", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    stats = d.get("stats", {})
    assert "pending_hr" in stats
    assert "pending_finance" in stats
    assert "total_outstanding" in stats
    assert "this_month_requests" in stats
    print(f"Stats: {stats}")

# ─── Seed (should skip since data exists) ─────────────────────────────────────
def test_seed_skips_when_data_exists(auth_headers):
    r = requests.post(f"{BASE_URL}/api/dewi/kasbon/seed", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    # Either seeded or skipped
    msg = d.get("message", "")
    print(f"Seed response: {msg}")

# ─── List All ─────────────────────────────────────────────────────────────────
def test_list_all_requests(auth_headers):
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/requests", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    reqs = d.get("requests", [])
    assert isinstance(reqs, list)
    print(f"Total requests: {d.get('total')}")
    return reqs

# ─── My Requests ──────────────────────────────────────────────────────────────
def test_my_requests(auth_headers):
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/my-requests", headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    assert "requests" in d
    print(f"My requests count: {len(d['requests'])}")

# ─── Submit New Kasbon ────────────────────────────────────────────────────────
def test_submit_kasbon(auth_headers):
    payload = {
        "type": "kasbon",
        "amount": 500000,
        "purpose": "TEST_Biaya pengobatan",
        "notes": "Test submission",
        "installment_count": 1
    }
    r = requests.post(f"{BASE_URL}/api/dewi/kasbon/requests", json=payload, headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    req = d.get("request", {})
    assert req.get("type") == "kasbon"
    assert req.get("amount") == 500000
    assert req.get("status") == "submitted"
    assert req.get("id") is not None
    print(f"Created kasbon: {req.get('id')} - {req.get('request_number')}")
    return req

# ─── Submit Pinjaman ──────────────────────────────────────────────────────────
def test_submit_pinjaman(auth_headers):
    payload = {
        "type": "pinjaman",
        "amount": 3000000,
        "purpose": "TEST_Renovasi rumah",
        "installment_count": 3
    }
    r = requests.post(f"{BASE_URL}/api/dewi/kasbon/requests", json=payload, headers=auth_headers)
    assert r.status_code == 200
    d = r.json()
    assert d.get("ok") is True
    req = d.get("request", {})
    assert req.get("type") == "pinjaman"
    assert req.get("installment_count") == 3
    assert req.get("installment_amount") == 1000000
    print(f"Created pinjaman: {req.get('id')} - installment={req.get('installment_amount')}")

# ─── Submit Validation Errors ─────────────────────────────────────────────────
def test_submit_invalid_amount(auth_headers):
    r = requests.post(f"{BASE_URL}/api/dewi/kasbon/requests", 
                      json={"type": "kasbon", "amount": 0, "purpose": "test"},
                      headers=auth_headers)
    assert r.status_code == 400

def test_submit_invalid_type(auth_headers):
    r = requests.post(f"{BASE_URL}/api/dewi/kasbon/requests", 
                      json={"type": "invalid", "amount": 100000, "purpose": "test"},
                      headers=auth_headers)
    assert r.status_code == 400

# ─── HR Review Flow ───────────────────────────────────────────────────────────
def test_hr_review_approve(auth_headers):
    # Get a submitted request
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/requests?status=submitted&limit=1", headers=auth_headers)
    d = r.json()
    reqs = d.get("requests", [])
    if not reqs:
        pytest.skip("No submitted requests available for HR review")
    
    req_id = reqs[0]["id"]
    r2 = requests.patch(f"{BASE_URL}/api/dewi/kasbon/requests/{req_id}/hr-review",
                        json={"action": "approve", "notes": "TEST_Disetujui oleh testing"},
                        headers=auth_headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("ok") is True
    assert d2["request"]["status"] == "hr_approved"
    print(f"HR approved: {req_id}")
    return req_id

def test_hr_review_invalid_action(auth_headers):
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/requests?limit=1", headers=auth_headers)
    reqs = r.json().get("requests", [])
    if not reqs:
        pytest.skip("No requests")
    req_id = reqs[0]["id"]
    r2 = requests.patch(f"{BASE_URL}/api/dewi/kasbon/requests/{req_id}/hr-review",
                        json={"action": "invalid_action"},
                        headers=auth_headers)
    assert r2.status_code == 400

# ─── Finance Disburse ─────────────────────────────────────────────────────────
def test_finance_disburse(auth_headers):
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/requests?status=hr_approved&limit=1", headers=auth_headers)
    d = r.json()
    reqs = d.get("requests", [])
    if not reqs:
        pytest.skip("No hr_approved requests for disbursal")
    
    req_id = reqs[0]["id"]
    r2 = requests.patch(f"{BASE_URL}/api/dewi/kasbon/requests/{req_id}/disburse",
                        json={"disbursement_date": "2026-02-15", "deduction_start_period": "2026-03", "finance_notes": "TEST_Transfer done"},
                        headers=auth_headers)
    assert r2.status_code == 200
    d2 = r2.json()
    assert d2.get("ok") is True
    assert d2["request"]["status"] == "disbursed"
    print(f"Finance disbursed: {req_id}")

def test_disburse_wrong_status(auth_headers):
    # Try to disburse a submitted request (not hr_approved)
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/requests?status=submitted&limit=1", headers=auth_headers)
    d = r.json()
    reqs = d.get("requests", [])
    if not reqs:
        pytest.skip("No submitted requests")
    req_id = reqs[0]["id"]
    r2 = requests.patch(f"{BASE_URL}/api/dewi/kasbon/requests/{req_id}/disburse",
                        json={}, headers=auth_headers)
    assert r2.status_code == 400

# ─── Not Found ────────────────────────────────────────────────────────────────
def test_get_nonexistent_request(auth_headers):
    r = requests.get(f"{BASE_URL}/api/dewi/kasbon/requests/nonexistent-id", headers=auth_headers)
    assert r.status_code == 404
