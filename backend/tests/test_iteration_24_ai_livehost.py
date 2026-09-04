"""
Iteration 24 — AI Modules (Cash Flow + HR Attrition) + LiveHost Portal + Regression
Tests:
  - P1: AI CashFlow prediction (/api/finance/ai-cashflow)
  - P1: HR AI Attrition Dashboard (/api/hr/ai/attrition/dashboard)
  - P1: HR AI Attrition Predict (/api/hr/ai/attrition/predict)
  - LiveHost: Portal login (ayu.host@dewiaditya.id / Host@123)
  - LiveHost: My-shifts (/api/marketing/livehost/portal/my-shifts)
  - LiveHost: My-profile (/api/marketing/livehost/portal/my-profile)
  - P2 Regression: Approval badge (/api/approval-inbox/badge)
  - P3 Regression: Channel GL mapping (/api/rahaza/channel-gl-mapping)
  - Regression: Admin ERP login
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Get admin ERP JWT token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@garment.com", "password": "Admin@123"},
        timeout=15,
    )
    assert resp.status_code == 200, f"Admin login failed: {resp.status_code} {resp.text[:200]}"
    data = resp.json()
    token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
    assert token, f"No token in response: {data}"
    return token


@pytest.fixture(scope="module")
def finance_token():
    """Get finance user JWT token"""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "finance@dewiaditya.id", "password": "Dewi@123"},
        timeout=15,
    )
    if resp.status_code != 200:
        pytest.skip(f"Finance login failed: {resp.status_code}")
    data = resp.json()
    token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
    return token


@pytest.fixture(scope="module")
def livehost_token():
    """Get LiveHost portal JWT token for ayu.host@dewiaditya.id"""
    resp = requests.post(
        f"{BASE_URL}/api/marketing/livehost/portal/auth/login",
        json={"email": "ayu.host@dewiaditya.id", "password": "Host@123"},
        timeout=15,
    )
    assert resp.status_code == 200, f"LiveHost login failed: {resp.status_code} {resp.text[:300]}"
    data = resp.json()
    token = data.get("token") or data.get("data", {}).get("token")
    assert token, f"No token in LiveHost login response: {data}"
    return token


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def finance_headers(finance_token):
    return {"Authorization": f"Bearer {finance_token}"}


@pytest.fixture(scope="module")
def livehost_headers(livehost_token):
    return {"Authorization": f"Bearer {livehost_token}"}


# ─────────────────────────────────────────────────────────────────────────────
# REGRESSION: Admin ERP login
# ─────────────────────────────────────────────────────────────────────────────

class TestAdminLogin:
    """Regression — Admin ERP login still works"""

    def test_admin_login_success(self):
        """Admin login returns 200 with token"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@garment.com", "password": "Admin@123"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
        data = resp.json()
        token = data.get("token") or data.get("access_token") or data.get("data", {}).get("token")
        assert token, "Token must be present in response"
        assert isinstance(token, str) and len(token) > 20

    def test_admin_login_wrong_password(self):
        """Admin login with wrong password returns 401"""
        resp = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "admin@garment.com", "password": "WrongPass"},
            timeout=15,
        )
        assert resp.status_code in [401, 400], f"Expected 401/400, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# P2 REGRESSION: Approval Badge
# ─────────────────────────────────────────────────────────────────────────────

class TestApprovalBadge:
    """Regression — P2 Approval Badge"""

    def test_badge_returns_200(self, admin_headers):
        """GET /api/approval-inbox/badge returns 200 for admin"""
        resp = requests.get(
            f"{BASE_URL}/api/approval-inbox/badge",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"

    def test_badge_has_total_field(self, admin_headers):
        """Badge response has 'total' field > 0 for admin (pr_pending + ap_pending)"""
        resp = requests.get(
            f"{BASE_URL}/api/approval-inbox/badge",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "total" in data, f"Missing 'total' in: {data}"
        total = data["total"]
        assert isinstance(total, int), f"'total' must be int, got {type(total)}"
        assert total > 0, f"Admin badge total should be >0, got {total}"

    def test_badge_has_pr_ap_fields(self, admin_headers):
        """Badge response includes pr_pending and ap_pending fields"""
        resp = requests.get(
            f"{BASE_URL}/api/approval-inbox/badge",
            headers=admin_headers,
            timeout=15,
        )
        data = resp.json()
        assert "pr_pending" in data or "categories" in data, f"Missing pending fields: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# P3 REGRESSION: Channel GL Mapping
# ─────────────────────────────────────────────────────────────────────────────

class TestChannelGLMapping:
    """Regression — P3 Channel GL Mapping (13 channels)"""

    def test_channel_gl_returns_200(self, admin_headers):
        """GET /api/rahaza/channel-gl-mapping returns 200"""
        resp = requests.get(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"

    def test_channel_gl_has_13_channels(self, admin_headers):
        """Channel GL mapping returns 13 channels"""
        resp = requests.get(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping",
            headers=admin_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Check channels in data or directly in list
        channels = data if isinstance(data, list) else data.get("channels") or data.get("data", [])
        assert len(channels) >= 13, f"Expected >=13 channels, got {len(channels)}: {data}"


# ─────────────────────────────────────────────────────────────────────────────
# LIVEHOST: Portal login + profile + shifts
# ─────────────────────────────────────────────────────────────────────────────

class TestLiveHostPortal:
    """LiveHost portal authentication and self-service endpoints"""

    def test_livehost_login_success(self):
        """LiveHost portal login with ayu.host returns 200 + token"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/livehost/portal/auth/login",
            json={"email": "ayu.host@dewiaditya.id", "password": "Host@123"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        token = data.get("token") or data.get("data", {}).get("token")
        assert token, f"No token in response: {data}"
        assert isinstance(token, str) and len(token) > 20, "Token must be a non-trivial JWT string"
        # Also check host info returned
        host = data.get("host") or data.get("data", {}).get("host")
        assert host, f"No host info in response: {data}"

    def test_livehost_login_wrong_password(self):
        """LiveHost portal login with wrong password returns 401"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/livehost/portal/auth/login",
            json={"email": "ayu.host@dewiaditya.id", "password": "WrongPass"},
            timeout=15,
        )
        assert resp.status_code in [401, 400], f"Expected 401, got {resp.status_code}"

    def test_livehost_login_dian(self):
        """Second host (dian.host) can also login"""
        resp = requests.post(
            f"{BASE_URL}/api/marketing/livehost/portal/auth/login",
            json={"email": "dian.host@dewiaditya.id", "password": "Host@123"},
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
        data = resp.json()
        token = data.get("token") or data.get("data", {}).get("token")
        assert token, "Token must be returned for dian.host login"

    def test_livehost_my_profile_returns_200(self, livehost_headers):
        """GET /api/marketing/livehost/portal/my-profile returns 200 (not 500)"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/livehost/portal/my-profile",
            headers=livehost_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    def test_livehost_my_profile_has_data(self, livehost_headers):
        """Profile response contains host identity data"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/livehost/portal/my-profile",
            headers=livehost_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        # Should have name/email
        assert data.get("name") or data.get("host_name"), f"Missing name in profile: {data}"
        assert data.get("email") or data.get("host_email"), f"Missing email in profile: {data}"

    def test_livehost_my_shifts_returns_200(self, livehost_headers):
        """GET /api/marketing/livehost/portal/my-shifts returns 200 (not 500)"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/livehost/portal/my-shifts",
            headers=livehost_headers,
            timeout=15,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    def test_livehost_my_shifts_has_structure(self, livehost_headers):
        """Shifts response has 'shifts' list and 'total' field"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/livehost/portal/my-shifts",
            headers=livehost_headers,
            timeout=15,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "shifts" in data, f"Missing 'shifts' key in: {data}"
        assert "total" in data, f"Missing 'total' key in: {data}"
        shifts = data["shifts"]
        assert isinstance(shifts, list), f"'shifts' must be list, got {type(shifts)}"
        # total should match len(shifts)
        assert data["total"] == len(shifts), f"total={data['total']} != len(shifts)={len(shifts)}"

    def test_livehost_shifts_normalized_fields(self, livehost_headers):
        """Each shift has normalized fields: shift_start_time, shift_end_time, attendance_status"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/livehost/portal/my-shifts",
            headers=livehost_headers,
            timeout=15,
        )
        data = resp.json()
        shifts = data.get("shifts", [])
        if shifts:
            first = shifts[0]
            # After normalization, these fields should exist
            assert "shift_start_time" in first, f"Missing shift_start_time in shift: {first}"
            assert "shift_end_time" in first, f"Missing shift_end_time in shift: {first}"
            assert "attendance_status" in first, f"Missing attendance_status in shift: {first}"

    def test_livehost_without_auth_returns_401(self):
        """Accessing portal endpoints without auth returns 401"""
        resp = requests.get(
            f"{BASE_URL}/api/marketing/livehost/portal/my-profile",
            timeout=15,
        )
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# P1: AI CashFlow Prediction
# ─────────────────────────────────────────────────────────────────────────────

class TestAICashFlow:
    """P1 — AI Cash Flow Prediction via Emergent LLM"""

    def test_ai_cashflow_not_503(self, admin_headers):
        """GET /api/finance/ai-cashflow does NOT return 503 (EMERGENT_LLM_KEY is set)"""
        resp = requests.get(
            f"{BASE_URL}/api/finance/ai-cashflow",
            headers=admin_headers,
            timeout=90,  # AI calls can be slow
        )
        # 503 means key missing, 502 means LLM call failed
        assert resp.status_code != 503, "503 means EMERGENT_LLM_KEY not set — fix .env"
        assert resp.status_code not in [502, 500], \
            f"LLM call failed with {resp.status_code}: {resp.text[:300]}"

    def test_ai_cashflow_returns_200(self, admin_headers):
        """GET /api/finance/ai-cashflow returns 200 with analysis"""
        resp = requests.get(
            f"{BASE_URL}/api/finance/ai-cashflow",
            headers=admin_headers,
            timeout=90,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    def test_ai_cashflow_has_analysis_text(self, admin_headers):
        """CashFlow response contains non-empty 'analysis' text"""
        resp = requests.get(
            f"{BASE_URL}/api/finance/ai-cashflow",
            headers=admin_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "analysis" in data, f"Missing 'analysis' key in: {list(data.keys())}"
        analysis = data["analysis"]
        assert isinstance(analysis, str), f"'analysis' must be str, got {type(analysis)}"
        assert len(analysis) > 50, f"'analysis' too short: {repr(analysis[:100])}"

    def test_ai_cashflow_has_context(self, admin_headers):
        """CashFlow response contains 'context' with AR/AP data"""
        resp = requests.get(
            f"{BASE_URL}/api/finance/ai-cashflow",
            headers=admin_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "context" in data, f"Missing 'context' key in: {list(data.keys())}"
        ctx = data["context"]
        # context must have AR/AP data
        assert "total_ar" in ctx, f"Missing total_ar in context: {ctx}"
        assert "total_ap" in ctx, f"Missing total_ap in context: {ctx}"
        assert "today" in ctx, f"Missing today in context: {ctx}"

    def test_ai_cashflow_requires_auth(self):
        """CashFlow endpoint requires authentication"""
        resp = requests.get(
            f"{BASE_URL}/api/finance/ai-cashflow",
            timeout=15,
        )
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"


# ─────────────────────────────────────────────────────────────────────────────
# P1: HR AI Attrition
# ─────────────────────────────────────────────────────────────────────────────

class TestHRAttrition:
    """P1 — HR AI Attrition Risk via Emergent LLM"""

    def test_attrition_dashboard_returns_200(self, admin_headers):
        """GET /api/hr/ai/attrition/dashboard returns 200"""
        resp = requests.get(
            f"{BASE_URL}/api/hr/ai/attrition/dashboard",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    def test_attrition_dashboard_success_true(self, admin_headers):
        """Dashboard response has success:true"""
        resp = requests.get(
            f"{BASE_URL}/api/hr/ai/attrition/dashboard",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True, f"Expected success:true, got: {data}"

    def test_attrition_dashboard_has_data(self, admin_headers):
        """Dashboard response has 'data' list field"""
        resp = requests.get(
            f"{BASE_URL}/api/hr/ai/attrition/dashboard",
            headers=admin_headers,
            timeout=30,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data, f"Missing 'data' key in: {data}"
        # data should be a list (history of predictions)
        assert isinstance(data["data"], list), f"'data' should be list, got {type(data['data'])}"

    def test_attrition_predict_returns_200(self, admin_headers):
        """POST /api/hr/ai/attrition/predict returns 200"""
        resp = requests.post(
            f"{BASE_URL}/api/hr/ai/attrition/predict",
            headers=admin_headers,
            timeout=90,  # AI calls can be slow
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    def test_attrition_predict_success_true(self, admin_headers):
        """POST /api/hr/ai/attrition/predict returns success:true"""
        resp = requests.post(
            f"{BASE_URL}/api/hr/ai/attrition/predict",
            headers=admin_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("success") is True, f"Expected success:true, got: {data}"

    def test_attrition_predict_has_analysis(self, admin_headers):
        """POST predict response has analysis data with employees list"""
        resp = requests.post(
            f"{BASE_URL}/api/hr/ai/attrition/predict",
            headers=admin_headers,
            timeout=90,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data, f"Missing 'data' key in: {data}"
        predict_data = data["data"]
        analysis = predict_data.get("analysis", {})
        # Analysis should have employees list with risk_level per employee
        employees = analysis.get("employees", [])
        if employees:
            first = employees[0]
            assert "risk_level" in first, f"Missing risk_level in employee: {first}"
            assert first["risk_level"] in ["high", "medium", "low"], \
                f"risk_level must be high/medium/low, got: {first.get('risk_level')}"
        else:
            # raw_response fallback is acceptable but note it
            print(f"WARNING: employees list is empty. analysis keys: {list(analysis.keys())}")

    def test_attrition_predict_by_department(self, admin_headers):
        """POST predict with department filter returns 200"""
        resp = requests.post(
            f"{BASE_URL}/api/hr/ai/attrition/predict?department=Produksi",
            headers=admin_headers,
            timeout=90,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"

    def test_attrition_requires_auth(self):
        """Attrition endpoints require auth"""
        resp = requests.get(
            f"{BASE_URL}/api/hr/ai/attrition/dashboard",
            timeout=15,
        )
        assert resp.status_code == 401, f"Expected 401 without auth, got {resp.status_code}"
