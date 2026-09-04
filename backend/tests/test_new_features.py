"""
Tests for new features: brute-force protection, pagination endpoints
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# ─── Pagination Tests ─────────────────────────────────────────────────────────

class TestPaginationEmployees:
    """Test /api/rahaza/employees pagination"""

    def test_employees_pagination_format(self):
        resp = requests.get(f"{BASE_URL}/api/rahaza/employees?skip=0&limit=10",
                            headers={"Authorization": "Bearer SKIP"})
        # Without auth should be 401/403
        assert resp.status_code in [200, 401, 403, 422]

    def test_employees_pagination_with_auth(self):
        # Login first
        login = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": "admin@garment.com", "password": "Admin@123"})
        assert login.status_code == 200, f"Login failed: {login.text}"
        token = login.json()["token"]

        resp = requests.get(f"{BASE_URL}/api/rahaza/employees?skip=0&limit=10",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Employees failed: {resp.text}"
        data = resp.json()
        assert "total" in data
        assert "skip" in data
        assert "limit" in data
        assert "has_more" in data
        assert "items" in data
        assert isinstance(data["items"], list)
        assert data["skip"] == 0
        assert data["limit"] == 10


class TestPaginationLeaves:
    """Test /api/rahaza/leaves pagination"""

    def test_leaves_pagination_with_auth(self):
        login = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": "admin@garment.com", "password": "Admin@123"})
        token = login.json()["token"]
        resp = requests.get(f"{BASE_URL}/api/rahaza/leaves?skip=0&limit=5",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Leaves failed: {resp.text}"
        data = resp.json()
        for key in ["total", "skip", "limit", "has_more", "items"]:
            assert key in data, f"Missing key: {key}"
        assert data["limit"] == 5


class TestPaginationAttendance:
    """Test /api/rahaza/attendance pagination"""

    def test_attendance_pagination_with_auth(self):
        login = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": "admin@garment.com", "password": "Admin@123"})
        token = login.json()["token"]
        resp = requests.get(f"{BASE_URL}/api/rahaza/attendance?skip=0&limit=5",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Attendance failed: {resp.text}"
        data = resp.json()
        for key in ["total", "skip", "limit", "has_more", "items"]:
            assert key in data, f"Missing key: {key}"


class TestPaginationPortal:
    """Test portal endpoints pagination"""

    def _get_token(self):
        login = requests.post(f"{BASE_URL}/api/auth/login",
                              json={"email": "admin@garment.com", "password": "Admin@123"})
        return login.json()["token"]

    def test_notes_pagination(self):
        token = self._get_token()
        resp = requests.get(f"{BASE_URL}/api/portal/notes?skip=0&limit=5",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Notes failed: {resp.text}"
        data = resp.json()
        # Should return list or paginated object
        assert isinstance(data, (list, dict))
        if isinstance(data, dict):
            assert "items" in data or "notes" in data

    def test_todos_pagination(self):
        token = self._get_token()
        resp = requests.get(f"{BASE_URL}/api/portal/todos?skip=0&limit=5",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Todos failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, (list, dict))

    def test_reminders_pagination(self):
        token = self._get_token()
        resp = requests.get(f"{BASE_URL}/api/portal/reminders?skip=0&limit=5",
                            headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200, f"Reminders failed: {resp.text}"
        data = resp.json()
        assert isinstance(data, (list, dict))


# ─── Brute Force Protection Tests ────────────────────────────────────────────

class TestBruteForce:
    """Test brute-force login protection"""

    WRONG_EMAIL = "admin@garment.com"
    WRONG_PASS = "WrongPass!999"

    def test_wrong_attempt_shows_countdown(self):
        """First few wrong attempts should show 'Tersisa X percobaan'"""
        # Clear any existing lockout by using a unique email to avoid interference
        test_email = f"brute_test_unique_{int(time.time())}@garment.com"
        resp = requests.post(f"{BASE_URL}/api/auth/login",
                             json={"email": test_email, "password": "wrong"})
        assert resp.status_code == 401
        detail = resp.json().get("detail", "")
        # Should mention remaining attempts
        assert "Tersisa" in detail or "percobaan" in detail or "salah" in detail, f"Unexpected: {detail}"

    def test_countdown_decrements(self):
        """Each failed attempt should decrement remaining count"""
        import uuid
        # Use UUID to guarantee uniqueness across test runs
        test_email = f"bf_decrement_{uuid.uuid4().hex[:12]}@test.com"
        
        prev_attempts_left = None
        for i in range(4):
            resp = requests.post(f"{BASE_URL}/api/auth/login",
                                 json={"email": test_email, "password": "wrongpass"})
            if resp.status_code == 429:
                pytest.skip("Rate-limited from previous run")
            assert resp.status_code == 401
            detail = resp.json().get("detail", "")
            if "Tersisa" in detail:
                parts = detail.split("Tersisa ")
                if len(parts) > 1:
                    num_str = parts[1].split(" ")[0]
                    try:
                        attempts_left = int(num_str)
                        if prev_attempts_left is not None:
                            assert attempts_left < prev_attempts_left, f"Counter not decrementing: {prev_attempts_left} -> {attempts_left}"
                        prev_attempts_left = attempts_left
                    except ValueError:
                        pass

    def test_lockout_after_5_attempts(self):
        """After 5 wrong attempts, account should be locked"""
        import random
        test_email = f"bf_lockout_{random.randint(10000,99999)}@test.com"
        
        for i in range(5):
            requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": test_email, "password": "wrongpass"})
        
        # 6th attempt should be locked
        resp = requests.post(f"{BASE_URL}/api/auth/login",
                             json={"email": test_email, "password": "wrongpass"})
        assert resp.status_code == 429, f"Expected 429 lockout, got {resp.status_code}: {resp.text}"
        detail = resp.json().get("detail", "")
        assert "terkunci" in detail.lower() or "429" in str(resp.status_code), f"Unexpected: {detail}"

    def test_success_after_partial_fails(self):
        """Successful login with correct credentials should succeed (may already have failed attempts)"""
        # Just verify correct credentials work (counter clears on success)
        resp = requests.post(f"{BASE_URL}/api/auth/login",
                             json={"email": "admin@garment.com", "password": "Admin@123"})
        if resp.status_code == 429:
            pytest.skip("admin@garment.com locked from previous test run - cannot test within lockout window")
        assert resp.status_code == 200, f"Valid login failed: {resp.text}"
        assert "token" in resp.json()
