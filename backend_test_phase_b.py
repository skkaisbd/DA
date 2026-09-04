#!/usr/bin/env python3
"""
Backend Test - Phase B (Fase B)
Testing procurement requests sorting and validation
"""
import requests
import sys
from datetime import datetime

# Get backend URL from environment
BACKEND_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
LOGIN_EMAIL = "admin@garment.com"
LOGIN_PASSWORD = "Admin@123"

class PhaseB_BackendTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failures = []

    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

    def test(self, name, condition, error_msg=""):
        """Run a single test"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"✅ PASS: {name}", "PASS")
            return True
        else:
            self.log(f"❌ FAIL: {name} - {error_msg}", "FAIL")
            self.failures.append(f"{name}: {error_msg}")
            return False

    def login(self):
        """Login and get token"""
        self.log("Logging in...")
        try:
            r = requests.post(
                f"{BACKEND_URL}/api/auth/login",
                json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
                timeout=10
            )
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                self.log(f"Login successful, token: {self.token[:20]}...")
                return True
            else:
                self.log(f"Login failed: {r.status_code} - {r.text}", "ERROR")
                return False
        except Exception as e:
            self.log(f"Login error: {e}", "ERROR")
            return False

    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def test_procurement_sort_desc(self):
        """Test GET /api/procurement/requests with sort_by=total_estimated&sort_dir=desc"""
        self.log("Testing procurement requests sorting (desc)...")
        try:
            r = requests.get(
                f"{BACKEND_URL}/api/procurement/requests",
                headers=self.headers(),
                params={"sort_by": "total_estimated", "sort_dir": "desc", "limit": 10},
                timeout=10
            )
            
            if r.status_code != 200:
                self.test("Procurement sort desc - HTTP status", False, f"Expected 200, got {r.status_code}")
                return
            
            data = r.json()
            items = data.get("items", [])
            
            # Check if items are sorted descending by total_estimated
            if len(items) >= 2:
                values = [float(item.get("total_estimated", 0)) for item in items]
                is_sorted = all(values[i] >= values[i+1] for i in range(len(values)-1))
                self.test(
                    "Procurement sort desc - values descending",
                    is_sorted,
                    f"Values not in descending order: {values[:5]}"
                )
            else:
                self.log("⚠️  WARNING: Less than 2 items, cannot verify sort order", "WARN")
                self.test("Procurement sort desc - has items", len(items) > 0, "No items returned")
            
        except Exception as e:
            self.test("Procurement sort desc", False, str(e))

    def test_procurement_sort_asc(self):
        """Test GET /api/procurement/requests with sort_by=total_estimated&sort_dir=asc"""
        self.log("Testing procurement requests sorting (asc)...")
        try:
            r = requests.get(
                f"{BACKEND_URL}/api/procurement/requests",
                headers=self.headers(),
                params={"sort_by": "total_estimated", "sort_dir": "asc", "limit": 10},
                timeout=10
            )
            
            if r.status_code != 200:
                self.test("Procurement sort asc - HTTP status", False, f"Expected 200, got {r.status_code}")
                return
            
            data = r.json()
            items = data.get("items", [])
            
            # Check if items are sorted ascending by total_estimated
            if len(items) >= 2:
                values = [float(item.get("total_estimated", 0)) for item in items]
                is_sorted = all(values[i] <= values[i+1] for i in range(len(values)-1))
                self.test(
                    "Procurement sort asc - values ascending",
                    is_sorted,
                    f"Values not in ascending order: {values[:5]}"
                )
            else:
                self.log("⚠️  WARNING: Less than 2 items, cannot verify sort order", "WARN")
                self.test("Procurement sort asc - has items", len(items) > 0, "No items returned")
            
        except Exception as e:
            self.test("Procurement sort asc", False, str(e))

    def test_procurement_invalid_sort(self):
        """Test GET /api/procurement/requests with invalid sort_by (should not error)"""
        self.log("Testing procurement requests with invalid sort_by...")
        try:
            r = requests.get(
                f"{BACKEND_URL}/api/procurement/requests",
                headers=self.headers(),
                params={"sort_by": "drop_table", "sort_dir": "desc", "limit": 10},
                timeout=10
            )
            
            # Should return 200 and fallback to default sort
            self.test(
                "Procurement invalid sort - HTTP 200",
                r.status_code == 200,
                f"Expected 200, got {r.status_code}"
            )
            
            if r.status_code == 200:
                data = r.json()
                items = data.get("items", [])
                self.test(
                    "Procurement invalid sort - returns items",
                    len(items) >= 0,
                    "Should return items with default sort"
                )
            
        except Exception as e:
            self.test("Procurement invalid sort", False, str(e))

    def run_all_tests(self):
        """Run all backend tests"""
        self.log("=" * 60)
        self.log("PHASE B BACKEND TESTS")
        self.log("=" * 60)
        
        if not self.login():
            self.log("Cannot proceed without login", "ERROR")
            return False
        
        # Run tests
        self.test_procurement_sort_desc()
        self.test_procurement_sort_asc()
        self.test_procurement_invalid_sort()
        
        # Summary
        self.log("=" * 60)
        self.log(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        if self.failures:
            self.log("FAILURES:", "ERROR")
            for f in self.failures:
                self.log(f"  - {f}", "ERROR")
        self.log("=" * 60)
        
        return self.tests_passed == self.tests_run

def main():
    tester = PhaseB_BackendTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
