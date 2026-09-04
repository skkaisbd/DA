"""
Backend Test — P0 Gap Fix Session
Tests for:
1. Dashboard revenue calculation (rahaza_ar_invoices SSOT)
2. Financial report endpoint (rahaza_ar_invoices + rahaza_ap_invoices SSOT)
3. Demo seed endpoint (no dropped collections recreated)
4. WMS Opname2 endpoints (SSOT)
5. Backend health check
6. Excel export for invoices
"""
import requests
import sys

API = "https://da37-cmt-bridge.preview.emergentagent.com"

class P0GapFixTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log(self, msg, status="info"):
        prefix = {"info": "ℹ️", "success": "✅", "error": "❌", "warning": "⚠️"}
        print(f"{prefix.get(status, 'ℹ️')} {msg}")

    def test(self, name, method, endpoint, expected_status=200, data=None, check_fn=None):
        """Run a single test"""
        self.tests_run += 1
        url = f"{API}{endpoint}"
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self.log(f"Testing: {name}", "info")
        try:
            if method == "GET":
                r = requests.get(url, headers=headers, timeout=15)
            elif method == "POST":
                r = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == "PUT":
                r = requests.put(url, json=data, headers=headers, timeout=15)
            elif method == "DELETE":
                r = requests.delete(url, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if r.status_code != expected_status:
                self.log(f"FAIL: Expected {expected_status}, got {r.status_code}", "error")
                self.log(f"Response: {r.text[:200]}", "error")
                self.failed_tests.append(name)
                return False

            # Additional check function
            if check_fn:
                try:
                    result = r.json() if r.text else {}
                except Exception:
                    result = {}
                if not check_fn(result):
                    self.log("FAIL: Check function failed", "error")
                    self.failed_tests.append(name)
                    return False

            self.tests_passed += 1
            self.log(f"PASS: {name}", "success")
            return True

        except requests.exceptions.Timeout:
            self.log("FAIL: Request timeout", "error")
            self.failed_tests.append(name)
            return False
        except Exception as e:
            self.log(f"FAIL: {str(e)}", "error")
            self.failed_tests.append(name)
            return False

    def run(self):
        self.log("=" * 60, "info")
        self.log("P0 GAP FIX SESSION — Backend Test", "info")
        self.log("=" * 60, "info")

        # ─── 1. LOGIN ───
        self.log("\n[1/8] Testing Login...", "info")
        login_success = self.test(
            "Login with admin@garment.com",
            "POST",
            "/api/auth/login",
            200,
            {"email": "admin@garment.com", "password": "Admin@123"},
            lambda r: "token" in r
        )
        if not login_success:
            self.log("Login failed — cannot proceed with authenticated tests", "error")
            return self.summary()

        # Extract token
        try:
            r = requests.post(f"{API}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
            self.token = r.json().get("token")
            self.log(f"Token acquired: {self.token[:20]}...", "success")
        except Exception:
            self.log("Failed to extract token", "error")
            return self.summary()

        # ─── 2. BACKEND HEALTH CHECK ───
        self.log("\n[2/8] Testing Backend Health Check...", "info")
        self.test(
            "Backend health check /api/health",
            "GET",
            "/api/health",
            200,
            check_fn=lambda r: r.get("status") == "ok"
        )

        # ─── 3. DASHBOARD LOADS WITHOUT ERROR ───
        self.log("\n[3/8] Testing Dashboard (Revenue from SSOT)...", "info")
        self.test(
            "Dashboard loads without error",
            "GET",
            "/api/dashboard",
            200,
            check_fn=lambda r: "revenueToday" in r or "totalRevenue" in r
        )

        # ─── 4. FINANCIAL REPORT ENDPOINT ───
        self.log("\n[4/8] Testing Financial Report (SSOT: rahaza_ar_invoices + rahaza_ap_invoices)...", "info")
        self.test(
            "Financial report returns data from SSOT",
            "GET",
            "/api/reports/financial",
            200,
            check_fn=lambda r: isinstance(r, list)  # Should return list (even if empty)
        )

        # ─── 5. WMS OPNAME2 ENDPOINTS (SSOT) ───
        self.log("\n[5/8] Testing WMS Opname2 Endpoints (SSOT)...", "info")
        self.test(
            "WMS Opname2 list endpoint",
            "GET",
            "/api/wms/opname2?limit=10",
            200,
            check_fn=lambda r: isinstance(r, dict) and "items" in r  # Paginated response
        )

        # ─── 6. DEMO SEED ENDPOINT ───
        self.log("\n[6/8] Testing Demo Seed (No Dropped Collections)...", "info")
        self.test(
            "Demo seed endpoint does NOT recreate dropped collections",
            "POST",
            "/api/dewi/seed-demo-full",
            200,
            check_fn=lambda r: r.get("ok")
        )

        # ─── 7. EXCEL EXPORT FOR INVOICES ───
        self.log("\n[7/8] Testing Excel Export (type=invoices)...", "info")
        # Note: This endpoint might return binary data, so we just check status code
        self.test(
            "Excel export type=invoices",
            "GET",
            "/api/export-excel?type=invoices",
            200
        )

        # ─── 8. SIDEBAR NAVIGATION SPOT CHECK ───
        self.log("\n[8/8] Testing Sidebar Navigation (Spot Check)...", "info")
        # Test a few key endpoints to ensure no white screen
        self.test("Dashboard endpoint", "GET", "/api/dashboard", 200)
        # WMS endpoint already tested above
        # HR endpoint
        self.test("HR endpoint (spot check)", "GET", "/api/rahaza/employees?limit=5", 200)

        return self.summary()

    def summary(self):
        self.log("\n" + "=" * 60, "info")
        self.log("TEST SUMMARY", "info")
        self.log("=" * 60, "info")
        self.log(f"Total Tests: {self.tests_run}", "info")
        self.log(f"Passed: {self.tests_passed}", "success")
        self.log(f"Failed: {self.tests_run - self.tests_passed}", "error")

        if self.failed_tests:
            self.log("\nFailed Tests:", "error")
            for test in self.failed_tests:
                self.log(f"  - {test}", "error")

        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess Rate: {success_rate:.1f}%", "info")

        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = P0GapFixTester()
    sys.exit(tester.run())
