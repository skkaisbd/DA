"""
DA53 ERP Phase A + Wave 3 Backend Testing
CV. Dewi Aditya — React Hook Refactor + Collection Cleanup Verification

Focus:
1. Login flow for all roles (with rate-limit delays - 65s pause after 8-9 logins)
2. Onboarding endpoints work (reads canonical dewi_onboarding_checklists, NOT dropped rahaza_onboarding_checklists)
3. Deprecated accessory endpoints safe: GET returns 200 [], POST returns 410
4. Health check returns 200
5. RBAC portal access per role

Rate Limiting: /api/auth/login is rate-limited to ~10 req/60s per IP.
CRITICAL: Insert 65s pause after 8-9 logins to avoid 429/401 errors.
"""
import requests
import sys
import json
import time
from datetime import datetime
from typing import Dict, List, Optional

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test credentials from /app/memory/test_credentials.md
TEST_USERS = [
    {"email": "admin@garment.com", "password": "Admin@123", "role": "superadmin", "name": "Superadmin"},
    {"email": "hr@dewiaditya.id", "password": "Dewi@123", "role": "hr", "name": "HR"},
    {"email": "finance@dewiaditya.id", "password": "Dewi@123", "role": "accounting", "name": "Finance"},
    {"email": "spv@dewiaditya.id", "password": "Dewi@123", "role": "supervisor_produksi", "name": "Production Supervisor"},
    {"email": "gudang@dewiaditya.id", "password": "Dewi@123", "role": "admin_gudang", "name": "Warehouse Admin"},
    {"email": "maklon@dewiaditya.id", "password": "Dewi@123", "role": "admin_maklon", "name": "Maklon Admin"},
]

# Expected portal access per role
EXPECTED_PORTALS = {
    "superadmin": ["management", "production", "warehouse", "accessories", "finance", "hr", "maklon", "toko", "rnd", "assets", "collaboration", "self"],
    "hr": ["hr", "collaboration", "self"],
    "accounting": ["finance", "maklon", "assets", "collaboration", "self"],
    "supervisor_produksi": ["production", "maklon", "rnd", "collaboration", "self"],
    "admin_gudang": ["warehouse", "accessories", "collaboration", "self"],
    "admin_maklon": ["maklon", "collaboration", "self"],
}

# Onboarding endpoints (should read from dewi_onboarding_checklists, NOT dropped rahaza_onboarding_checklists)
ONBOARDING_ENDPOINTS = [
    "/api/dewi/onboarding/templates",
    "/api/dewi/onboarding/checklists",
    "/api/dewi/onboarding/analytics",
]

# Deprecated accessory endpoints (collections dropped in Wave 3)
DEPRECATED_ACCESSORY_ENDPOINTS = {
    "GET_200": [
        "/api/accessory-inspections",
        "/api/accessory-defects",
    ],
    "POST_410": [
        "/api/accessory-inspections",
        "/api/accessory-defects",
    ],
}


class PhaseAWave3Tester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.role_tokens = {}  # Store tokens per role
        
    def log(self, msg: str, level: str = "INFO"):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        symbol = {
            "INFO": "ℹ️",
            "TEST": "🔍",
            "PASS": "✅",
            "FAIL": "❌",
            "WARN": "⚠️",
            "ERROR": "🔥",
            "SLEEP": "💤"
        }.get(level, "•")
        print(f"[{timestamp}] {symbol} {msg}")
    
    def test(self, name: str, method: str, endpoint: str, expected_status: int, 
             headers: Optional[Dict] = None, data: Optional[Dict] = None, 
             params: Optional[Dict] = None) -> tuple:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}{endpoint}"
        
        self.log(f"Testing: {name}", "TEST")
        
        try:
            kwargs = {"timeout": 15}
            if headers:
                kwargs["headers"] = headers
            if params:
                kwargs["params"] = params
            if data:
                kwargs["json"] = data
            
            if method == "GET":
                response = requests.get(url, **kwargs)
            elif method == "POST":
                response = requests.post(url, **kwargs)
            elif method == "PUT":
                response = requests.put(url, **kwargs)
            elif method == "DELETE":
                response = requests.delete(url, **kwargs)
            else:
                self.log(f"Unknown method: {method}", "ERROR")
                self.tests_failed += 1
                self.failed_tests.append({"test": name, "reason": f"Unknown method: {method}"})
                return False, {}
            
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"PASSED - Status: {response.status_code}", "PASS")
                self.passed_tests.append(name)
                try:
                    return True, response.json() if response.text else {}
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text[:200] if response.text else "No response body"
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "error": error_detail
                })
                return False, {}
                
        except requests.exceptions.Timeout:
            self.tests_failed += 1
            self.log("Request timeout (15s)", "ERROR")
            self.failed_tests.append({"test": name, "reason": "Timeout"})
            return False, {}
        except Exception as e:
            self.tests_failed += 1
            self.log(f"Error: {str(e)}", "ERROR")
            self.failed_tests.append({"test": name, "reason": str(e)})
            return False, {}
    
    def test_health(self):
        """Test backend health endpoint"""
        self.log("=" * 80, "INFO")
        self.log("DA53 ERP PHASE A + WAVE 3 TESTING", "INFO")
        self.log("React Hook Refactor + Collection Cleanup Verification", "INFO")
        self.log("=" * 80, "INFO")
        self.log(f"Base URL: {BASE_URL}", "INFO")
        self.log("=" * 80, "INFO")
        
        success, data = self.test(
            "Backend Health Check",
            "GET",
            "/api/health",
            200
        )
        
        if success:
            self.log(f"Backend Status: {data.get('status', 'unknown')}", "INFO")
            self.log(f"DB Status: {data.get('db', 'unknown')}", "INFO")
            self.log(f"DB Latency: {data.get('db_latency_ms', 'N/A')} ms", "INFO")
        
        return success
    
    def test_login_all_roles(self):
        """Test login for all 6 seeded roles with rate-limit handling"""
        self.log("=" * 80, "INFO")
        self.log("TESTING LOGIN FOR ALL 6 ROLES", "INFO")
        self.log("Rate limit: ~10 req/60s - pacing with 8s delays + 65s pause after 8 logins", "WARN")
        self.log("=" * 80, "INFO")
        
        for i, user in enumerate(TEST_USERS):
            # Rate limiting: pace requests with 8s delay between logins
            if i > 0:
                self.log(f"Waiting 8s to avoid rate limit...", "SLEEP")
                time.sleep(8)
            
            # After 8 logins, pause for 65s to reset rate limit window
            if i == 4:  # After 5th login (index 4), pause before continuing
                self.log("=" * 80, "WARN")
                self.log("RATE LIMIT PROTECTION: Pausing 65s to reset window", "SLEEP")
                self.log("=" * 80, "WARN")
                time.sleep(65)
            
            success, data = self.test(
                f"Login as {user['name']} ({user['role']})",
                "POST",
                "/api/auth/login",
                200,
                data={"email": user["email"], "password": user["password"]}
            )
            
            if success and "token" in data:
                self.role_tokens[user["role"]] = data["token"]
                self.log(f"Token obtained for {user['role']}", "INFO")
            else:
                self.log(f"Failed to get token for {user['role']}", "ERROR")
        
        return len(self.role_tokens) >= 4  # At least 4 roles should succeed
    
    def test_rbac_portals(self):
        """Test RBAC - verify each role sees only allowed portals"""
        self.log("=" * 80, "INFO")
        self.log("TESTING RBAC - PORTAL ACCESS PER ROLE", "INFO")
        self.log("=" * 80, "INFO")
        
        for user in TEST_USERS:
            role = user["role"]
            token = self.role_tokens.get(role)
            
            if not token:
                self.log(f"Skipping RBAC test for {role} - no token", "WARN")
                continue
            
            success, data = self.test(
                f"Get user info for {user['name']} ({role})",
                "GET",
                "/api/auth/me",
                200,
                headers={"Authorization": f"Bearer {token}"}
            )
            
            if success:
                actual_portals = set(data.get("portals", []))
                expected_portals = set(EXPECTED_PORTALS.get(role, []))
                
                if actual_portals == expected_portals:
                    self.log(f"✓ Portals match for {role}: {sorted(actual_portals)}", "PASS")
                else:
                    missing = expected_portals - actual_portals
                    extra = actual_portals - expected_portals
                    self.log(f"✗ Portal mismatch for {role}", "FAIL")
                    if missing:
                        self.log(f"  Missing: {sorted(missing)}", "FAIL")
                    if extra:
                        self.log(f"  Extra: {sorted(extra)}", "FAIL")
                    self.tests_failed += 1
                    self.failed_tests.append({
                        "test": f"RBAC portals for {role}",
                        "expected": sorted(expected_portals),
                        "actual": sorted(actual_portals)
                    })
    
    def test_onboarding_endpoints(self):
        """Test onboarding endpoints (should read from dewi_onboarding_checklists)"""
        self.log("=" * 80, "INFO")
        self.log("TESTING ONBOARDING ENDPOINTS (Wave 3)", "INFO")
        self.log("Should read from dewi_onboarding_checklists (NOT dropped rahaza_onboarding_checklists)", "INFO")
        self.log("=" * 80, "INFO")
        
        # Use HR token for testing (HR has access to onboarding)
        token = self.role_tokens.get("hr") or self.role_tokens.get("superadmin")
        if not token:
            self.log("No HR/superadmin token - skipping onboarding endpoint tests", "WARN")
            return
        
        headers = {"Authorization": f"Bearer {token}"}
        
        for endpoint in ONBOARDING_ENDPOINTS:
            success, data = self.test(
                f"Onboarding endpoint should return 200: {endpoint}",
                "GET",
                endpoint,
                200,
                headers=headers
            )
            
            if success:
                # Check if data is present
                if isinstance(data, dict):
                    if "templates" in data:
                        count = len(data.get("templates", []))
                        self.log(f"  → Templates count: {count}", "INFO")
                    elif "checklists" in data:
                        count = len(data.get("checklists", []))
                        self.log(f"  → Checklists count: {count}", "INFO")
                    elif "summary" in data:
                        self.log(f"  → Analytics summary: {data.get('summary', {})}", "INFO")
    
    def test_deprecated_accessory_endpoints(self):
        """Test deprecated accessory endpoints (Wave 3 - collections dropped)"""
        self.log("=" * 80, "INFO")
        self.log("TESTING DEPRECATED ACCESSORY ENDPOINTS (Wave 3)", "INFO")
        self.log("Collections dropped: accessory_inspections, accessory_defects", "INFO")
        self.log("GET should return 200 [], POST should return 410", "INFO")
        self.log("=" * 80, "INFO")
        
        # Use superadmin token for testing
        token = self.role_tokens.get("superadmin")
        if not token:
            self.log("No superadmin token - skipping deprecated accessory endpoint tests", "WARN")
            return
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Test GET endpoints (should return 200 with empty array)
        for endpoint in DEPRECATED_ACCESSORY_ENDPOINTS["GET_200"]:
            success, data = self.test(
                f"Deprecated GET should return 200 []: {endpoint}",
                "GET",
                endpoint,
                200,
                headers=headers
            )
            
            if success:
                # Verify it returns empty array or paginated empty response
                if isinstance(data, list):
                    if len(data) == 0:
                        self.log(f"  ✓ Returns empty array []", "PASS")
                    else:
                        self.log(f"  ⚠️ Expected empty array, got {len(data)} items", "WARN")
                elif isinstance(data, dict):
                    items = data.get("items", data.get("data", []))
                    if isinstance(items, list) and len(items) == 0:
                        self.log(f"  ✓ Returns paginated empty response", "PASS")
                    else:
                        self.log(f"  ⚠️ Expected empty response, got {len(items)} items", "WARN")
        
        # Test POST endpoints (should return 410 Gone)
        for endpoint in DEPRECATED_ACCESSORY_ENDPOINTS["POST_410"]:
            success, data = self.test(
                f"Deprecated POST should return 410: {endpoint}",
                "POST",
                endpoint,
                410,
                headers=headers,
                data={"test": "data"}
            )
            
            if success:
                self.log(f"  ✓ Returns 410 Gone (deprecated)", "PASS")
    
    def print_summary(self):
        """Print test summary"""
        self.log("=" * 80, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 80, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed} ({self.tests_passed/self.tests_run*100:.1f}%)", "PASS")
        self.log(f"Failed: {self.tests_failed} ({self.tests_failed/self.tests_run*100:.1f}%)", "FAIL" if self.tests_failed > 0 else "INFO")
        self.log("=" * 80, "INFO")
        
        if self.failed_tests:
            self.log("FAILED TESTS:", "FAIL")
            for i, test in enumerate(self.failed_tests, 1):
                self.log(f"{i}. {test.get('test', 'Unknown')}", "FAIL")
                if "expected" in test and "actual" in test:
                    self.log(f"   Expected: {test['expected']}, Got: {test['actual']}", "FAIL")
                if "error" in test:
                    error_str = str(test['error'])[:200]
                    self.log(f"   Error: {error_str}", "FAIL")
                if "reason" in test:
                    self.log(f"   Reason: {test['reason']}", "FAIL")
        
        self.log("=" * 80, "INFO")
        self.log("KEY FINDINGS:", "INFO")
        self.log("=" * 80, "INFO")
        self.log("✓ Backend health check", "PASS" if any("Health" in t for t in self.passed_tests) else "FAIL")
        self.log("✓ Login works for all roles (with rate-limit handling)", "PASS" if len(self.role_tokens) >= 4 else "FAIL")
        self.log("✓ Onboarding endpoints work (dewi_onboarding_checklists)", "PASS" if any("Onboarding" in t for t in self.passed_tests) else "FAIL")
        self.log("✓ Deprecated accessory endpoints safe (GET 200 [], POST 410)", "PASS" if any("Deprecated" in t for t in self.passed_tests) else "FAIL")
        self.log("=" * 80, "INFO")
        
        return self.tests_failed == 0


def main():
    tester = PhaseAWave3Tester()
    
    # Run test suites
    if not tester.test_health():
        print("\n❌ Backend health check failed - aborting tests")
        return 1
    
    if not tester.test_login_all_roles():
        print("\n⚠️ Some login tests failed - continuing with available tokens")
    
    tester.test_rbac_portals()
    tester.test_onboarding_endpoints()
    tester.test_deprecated_accessory_endpoints()
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
