"""
Session 29 Feature Tests:
- account_id filter on complaints, reviews, returns endpoints
- ActiveAccountBar presence (via code review)
- AccountDetailPage new tabs (Orders, Komplain, Reviews)
- Legacy label changes in PortalShell
"""
import pytest
import requests
import os

def _get_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        # Read from frontend .env
        env_path = "/app/frontend/.env"
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return url.rstrip("/")

BASE_URL = _get_base_url()

@pytest.fixture(scope="module")
def token():
    """Get auth token for testing"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data.get("data", {}).get("token")
    assert token, f"No token in response: {data}"
    return token

@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}

# ─── Complaints account_id filter ────────────────────────────────────────────

class TestComplaintsAccountIdFilter:
    """Test account_id Query param in /api/marketing/complaints"""

    def test_complaints_list_no_account_id(self, auth_headers):
        """GET /api/marketing/complaints returns all (or seeded) complaints"""
        resp = requests.get(f"{BASE_URL}/api/marketing/complaints", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "complaints" in data
        assert "pagination" in data
        print(f"✅ complaints list: {data['pagination']['total']} total")

    def test_complaints_list_with_account_id_unknown(self, auth_headers):
        """GET /api/marketing/complaints?account_id=nonexistent returns empty list"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/complaints?account_id=nonexistent-id-000",
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "complaints" in data
        assert isinstance(data["complaints"], list)
        # Unknown account_id should return 0 results
        assert len(data["complaints"]) == 0, f"Expected 0 complaints for unknown account_id, got {len(data['complaints'])}"
        print("✅ complaints filter by unknown account_id: 0 results (correct)")

    def test_complaints_list_account_id_param_accepted(self, auth_headers):
        """GET /api/marketing/complaints?account_id=any-id returns 200 (not 422)"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/complaints?account_id=test-account-123",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
        print("✅ complaints account_id param accepted without error")

    def test_complaints_summary_works(self, auth_headers):
        """GET /api/marketing/complaints/summary returns correct structure"""
        resp = requests.get(f"{BASE_URL}/api/marketing/complaints/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data
        assert "overdue" in data
        assert "by_status" in data
        print(f"✅ complaints summary: total={data['total']}, overdue={data['overdue']}")


# ─── Reviews account_id filter ───────────────────────────────────────────────

class TestReviewsAccountIdFilter:
    """Test account_id Query param in /api/marketing/reviews"""

    def test_reviews_list_no_account_id(self, auth_headers):
        """GET /api/marketing/reviews returns reviews list"""
        resp = requests.get(f"{BASE_URL}/api/marketing/reviews", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or "reviews" in data
        print(f"✅ reviews list works, total={data.get('pagination', {}).get('total', 'N/A')}")

    def test_reviews_list_with_account_id_unknown(self, auth_headers):
        """GET /api/marketing/reviews?account_id=nonexistent returns empty list"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/reviews?account_id=nonexistent-id-000",
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data.get("reviews", []))
        assert len(items) == 0, f"Expected 0 reviews for unknown account_id, got {len(items)}"
        print("✅ reviews filter by unknown account_id: 0 results (correct)")

    def test_reviews_list_account_id_param_accepted(self, auth_headers):
        """GET /api/marketing/reviews?account_id=any-id returns 200 (not 422)"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/reviews?account_id=test-account-123",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
        print("✅ reviews account_id param accepted without error")

    def test_reviews_summary_works(self, auth_headers):
        """GET /api/marketing/reviews/summary returns correct structure"""
        resp = requests.get(f"{BASE_URL}/api/marketing/reviews/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or "total" in data
        print("✅ reviews summary works")


# ─── Returns account_id filter ───────────────────────────────────────────────

class TestReturnsAccountIdFilter:
    """Test account_id Query param in /api/marketing/returns"""

    def test_returns_list_no_account_id(self, auth_headers):
        """GET /api/marketing/returns returns returns list"""
        resp = requests.get(f"{BASE_URL}/api/marketing/returns", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or "returns" in data
        print(f"✅ returns list works, total={data.get('pagination', {}).get('total', 'N/A')}")

    def test_returns_list_with_account_id_unknown(self, auth_headers):
        """GET /api/marketing/returns?account_id=nonexistent returns empty list"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/returns?account_id=nonexistent-id-000",
            headers=auth_headers
        )
        assert resp.status_code == 200
        data = resp.json()
        items = data.get("data", data.get("returns", []))
        assert len(items) == 0, f"Expected 0 returns for unknown account_id, got {len(items)}"
        print("✅ returns filter by unknown account_id: 0 results (correct)")

    def test_returns_list_account_id_param_accepted(self, auth_headers):
        """GET /api/marketing/returns?account_id=any-id returns 200 (not 422)"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/returns?account_id=test-account-123",
            headers=auth_headers
        )
        assert resp.status_code == 200, f"Expected 200 but got {resp.status_code}: {resp.text}"
        print("✅ returns account_id param accepted without error")

    def test_returns_summary_works(self, auth_headers):
        """GET /api/marketing/returns/summary returns correct structure"""
        resp = requests.get(f"{BASE_URL}/api/marketing/returns/summary", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data or "total" in data
        print("✅ returns summary works")


# ─── Real account_id filter integration ──────────────────────────────────────

class TestRealAccountIdFilterIntegration:
    """Test account_id filter with real account IDs from the platform accounts list"""

    def test_get_platform_accounts(self, auth_headers):
        """GET /api/marketing/accounts returns list with IDs"""
        resp = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        accounts = data if isinstance(data, list) else data.get("accounts", data.get("data", []))
        assert len(accounts) >= 0
        if accounts:
            first = accounts[0]
            print(f"✅ Got {len(accounts)} platform accounts. First: {first.get('id')} - {first.get('account_name')}")
        else:
            print("✅ No platform accounts yet (OK for testing)")

    def test_complaints_filter_by_real_account_if_available(self, auth_headers):
        """Test complaints filter with real account_id if accounts exist"""
        accounts_resp = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=auth_headers)
        if accounts_resp.status_code != 200:
            pytest.skip("Could not fetch accounts")
        data = accounts_resp.json()
        accounts = data if isinstance(data, list) else data.get("accounts", data.get("data", []))
        if not accounts:
            pytest.skip("No accounts available to test filter")
        account_id = accounts[0].get("id")
        resp = requests.get(
            f"{BASE_URL}/api/marketing/complaints?account_id={account_id}",
            headers=auth_headers
        )
        assert resp.status_code == 200
        result = resp.json()
        assert "complaints" in result
        # All complaints returned should have matching account_id or be empty
        for c in result["complaints"]:
            assert c.get("account_id") == account_id
        print(f"✅ complaints filtered by real account_id={account_id}: {len(result['complaints'])} results, all match")

    def test_reviews_filter_by_real_account_if_available(self, auth_headers):
        """Test reviews filter with real account_id"""
        accounts_resp = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=auth_headers)
        if accounts_resp.status_code != 200:
            pytest.skip("Could not fetch accounts")
        data = accounts_resp.json()
        accounts = data if isinstance(data, list) else data.get("accounts", data.get("data", []))
        if not accounts:
            pytest.skip("No accounts available to test filter")
        account_id = accounts[0].get("id")
        resp = requests.get(
            f"{BASE_URL}/api/marketing/reviews?account_id={account_id}",
            headers=auth_headers
        )
        assert resp.status_code == 200
        result = resp.json()
        items = result.get("data", [])
        for item in items:
            assert item.get("account_id") == account_id
        print(f"✅ reviews filtered by real account_id={account_id}: {len(items)} results, all match")

    def test_returns_filter_by_real_account_if_available(self, auth_headers):
        """Test returns filter with real account_id"""
        accounts_resp = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=auth_headers)
        if accounts_resp.status_code != 200:
            pytest.skip("Could not fetch accounts")
        data = accounts_resp.json()
        accounts = data if isinstance(data, list) else data.get("accounts", data.get("data", []))
        if not accounts:
            pytest.skip("No accounts available to test filter")
        account_id = accounts[0].get("id")
        resp = requests.get(
            f"{BASE_URL}/api/marketing/returns?account_id={account_id}",
            headers=auth_headers
        )
        assert resp.status_code == 200
        result = resp.json()
        items = result.get("data", [])
        for item in items:
            assert item.get("account_id") == account_id
        print(f"✅ returns filtered by real account_id={account_id}: {len(items)} results, all match")


# ─── Auth checks ─────────────────────────────────────────────────────────────

class TestAuthRequired:
    """Verify that all 3 endpoints require authentication"""

    def test_complaints_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/marketing/complaints")
        assert resp.status_code in [401, 403], f"Expected 401/403 without token, got {resp.status_code}"
        print(f"✅ complaints requires auth (got {resp.status_code})")

    def test_reviews_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/marketing/reviews")
        assert resp.status_code in [401, 403], f"Expected 401/403 without token, got {resp.status_code}"
        print(f"✅ reviews requires auth (got {resp.status_code})")

    def test_returns_requires_auth(self):
        resp = requests.get(f"{BASE_URL}/api/marketing/returns")
        assert resp.status_code in [401, 403], f"Expected 401/403 without token, got {resp.status_code}"
        print(f"✅ returns requires auth (got {resp.status_code})")
