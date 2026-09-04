"""
DA37/DA40 ERP for CV. Dewi Aditya — Session #11.18 EXTENDED part 2
Regression Test after fixing GET /api/dewi/maklon/summary 500 error

Bug Fixed:
- _MaklonOrdersView class in routes/_maklon_adapter.py was MISSING the `aggregate` method
- This caused AttributeError when /api/dewi/maklon/summary called _lmo(db).aggregate(pipeline)
- Fix: Added `aggregate(pipeline, **k)` method that proxies to underlying motor collection

Expected Results:
- All 20 endpoints should return 200 (19 were passing before + 1 newly fixed)
- GET /api/dewi/maklon/summary should now return 200 with proper structure
"""
import requests
import sys

# Public endpoint from frontend/.env
API = "https://da37-cmt-bridge.preview.emergentagent.com"

class MaklonSummaryRegressionTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []

    def log(self, msg, status="INFO"):
        prefix = "✅" if status == "PASS" else "❌" if status == "FAIL" else "🔍"
        print(f"{prefix} {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None, check_keys=None):
        """Run a single API test"""
        url = f"{API}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)

            success = response.status_code == expected_status
            
            if success:
                try:
                    resp_data = response.json()
                    # Check required keys if specified
                    if check_keys:
                        missing_keys = [key for key in check_keys if key not in resp_data]
                        if missing_keys:
                            self.log(f"FAILED - Missing keys: {missing_keys}", "FAIL")
                            self.failed_tests.append(f"{name} - Missing keys: {missing_keys}")
                            return False, {}
                    self.tests_passed += 1
                    self.log(f"PASSED - Status: {response.status_code}", "PASS")
                    return True, resp_data
                except Exception as e:
                    if expected_status == 200:
                        self.log(f"FAILED - JSON parse error: {e}", "FAIL")
                        self.failed_tests.append(f"{name} - JSON parse error")
                        return False, {}
                    self.tests_passed += 1
                    self.log(f"PASSED - Status: {response.status_code}", "PASS")
                    return True, {}
            else:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.failed_tests.append(f"{name} - Expected {expected_status}, got {response.status_code}")
                try:
                    error_detail = response.json()
                    self.log(f"Response: {error_detail}", "INFO")
                except Exception:
                    self.log(f"Response text: {response.text[:300]}", "INFO")
                return False, {}

        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            self.failed_tests.append(f"{name} - Exception: {str(e)}")
            return False, {}

    def test_login(self):
        """Test login with admin credentials"""
        self.log("=" * 80, "INFO")
        self.log("PHASE 1: Authentication", "INFO")
        self.log("=" * 80, "INFO")
        
        success, response = self.run_test(
            "POST /api/auth/login (admin@garment.com)",
            "POST",
            "/api/auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"}
        )
        if success:
            # Try both 'access_token' and 'token' keys
            token = response.get('access_token') or response.get('token')
            if token:
                self.token = token
                self.log(f"Token obtained: {self.token[:30]}...", "INFO")
                return True
            else:
                self.log(f"No token found in response. Keys: {list(response.keys())}", "FAIL")
        return False

    def test_health(self):
        """Test health check endpoint"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 2: Health Check", "INFO")
        self.log("=" * 80, "INFO")
        
        success, response = self.run_test(
            "GET /api/health",
            "GET",
            "/api/health",
            200,
            check_keys=['status']
        )
        return success

    def test_maklon_summary(self):
        """Test the FIXED maklon summary endpoint - KEY BUG FIX"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 3: Maklon Summary (KEY BUG FIX)", "INFO")
        self.log("=" * 80, "INFO")
        
        success, response = self.run_test(
            "GET /api/dewi/maklon/summary (PREVIOUSLY 500, NOW SHOULD BE 200)",
            "GET",
            "/api/dewi/maklon/summary",
            200,
            check_keys=['total_clients', 'total_orders', 'total_revenue']
        )
        if success:
            self.log(f"Summary data: clients={response.get('total_clients')}, orders={response.get('total_orders')}, revenue={response.get('total_revenue')}", "INFO")
        return success

    def test_maklon_endpoints(self):
        """Test maklon-related endpoints"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 4: Maklon Endpoints", "INFO")
        self.log("=" * 80, "INFO")
        
        results = []
        
        # Test maklon PO list
        success, _ = self.run_test(
            "GET /api/dewi/maklon/pos",
            "GET",
            "/api/dewi/maklon/pos",
            200
        )
        results.append(success)
        
        return all(results)

    def test_core_endpoints(self):
        """Test core system endpoints"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 5: Core System Endpoints", "INFO")
        self.log("=" * 80, "INFO")
        
        results = []
        
        # Products
        success, _ = self.run_test(
            "GET /api/products",
            "GET",
            "/api/products",
            200
        )
        results.append(success)
        
        # Work Orders
        success, _ = self.run_test(
            "GET /api/work-orders",
            "GET",
            "/api/work-orders",
            200
        )
        results.append(success)
        
        return all(results)

    def test_rahaza_endpoints(self):
        """Test Rahaza module endpoints"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 6: Rahaza Module Endpoints", "INFO")
        self.log("=" * 80, "INFO")
        
        results = []
        
        # Employees
        success, _ = self.run_test(
            "GET /api/rahaza/employees",
            "GET",
            "/api/rahaza/employees",
            200
        )
        results.append(success)
        
        # Work Orders
        success, _ = self.run_test(
            "GET /api/rahaza/work-orders",
            "GET",
            "/api/rahaza/work-orders",
            200
        )
        results.append(success)
        
        # Salary Grades (F601 fix regression check)
        success, _ = self.run_test(
            "GET /api/rahaza/salary-grades (F601 fix regression check)",
            "GET",
            "/api/rahaza/salary-grades",
            200
        )
        results.append(success)
        
        return all(results)

    def test_wms_endpoints(self):
        """Test WMS endpoints"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 7: WMS Endpoints", "INFO")
        self.log("=" * 80, "INFO")
        
        results = []
        
        # Buildings
        success, _ = self.run_test(
            "GET /api/wms/buildings",
            "GET",
            "/api/wms/buildings",
            200
        )
        results.append(success)
        
        return all(results)

    def test_notification_endpoints(self):
        """Test notification endpoints"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 8: Notification Endpoints", "INFO")
        self.log("=" * 80, "INFO")
        
        results = []
        
        # Notifications list
        success, _ = self.run_test(
            "GET /api/notifications?limit=5",
            "GET",
            "/api/notifications?limit=5",
            200
        )
        results.append(success)
        
        # Unread count
        success, _ = self.run_test(
            "GET /api/notifications/unread-count",
            "GET",
            "/api/notifications/unread-count",
            200
        )
        results.append(success)
        
        return all(results)

    def test_marketing_endpoints(self):
        """Test marketing module endpoints"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 9: Marketing Module Endpoints", "INFO")
        self.log("=" * 80, "INFO")
        
        results = []
        
        # Orders summary
        success, _ = self.run_test(
            "GET /api/marketing/orders/summary",
            "GET",
            "/api/marketing/orders/summary",
            200
        )
        results.append(success)
        
        # Complaints summary
        success, _ = self.run_test(
            "GET /api/marketing/complaints/summary",
            "GET",
            "/api/marketing/complaints/summary",
            200
        )
        results.append(success)
        
        # Health summary
        success, _ = self.run_test(
            "GET /api/marketing/health/summary",
            "GET",
            "/api/marketing/health/summary",
            200
        )
        results.append(success)
        
        # Discounts summary
        success, _ = self.run_test(
            "GET /api/marketing/discounts/summary",
            "GET",
            "/api/marketing/discounts/summary",
            200
        )
        results.append(success)
        
        # Product launches summary
        success, _ = self.run_test(
            "GET /api/marketing/product-launches/summary",
            "GET",
            "/api/marketing/product-launches/summary",
            200
        )
        results.append(success)
        
        # Content calendar summary
        success, _ = self.run_test(
            "GET /api/marketing/content-calendar/summary",
            "GET",
            "/api/marketing/content-calendar/summary",
            200
        )
        results.append(success)
        
        # Alerts evaluate
        success, _ = self.run_test(
            "POST /api/marketing/alerts/evaluate",
            "POST",
            "/api/marketing/alerts/evaluate",
            200,
            data={}
        )
        results.append(success)
        
        return all(results)

    def test_search_endpoint(self):
        """Test global search endpoint"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("PHASE 10: Global Search Endpoint", "INFO")
        self.log("=" * 80, "INFO")
        
        success, _ = self.run_test(
            "GET /api/global-search?q=test",
            "GET",
            "/api/global-search?q=test",
            200
        )
        return success

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 80, "INFO")
        
        pass_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "PASS" if self.tests_passed == self.tests_run else "INFO")
        self.log(f"Failed: {self.tests_run - self.tests_passed}", "FAIL" if self.tests_run - self.tests_passed > 0 else "INFO")
        self.log(f"Pass Rate: {pass_rate:.1f}%", "PASS" if pass_rate == 100 else "INFO")
        
        if self.failed_tests:
            self.log("\nFailed Tests:", "FAIL")
            for test in self.failed_tests:
                self.log(f"  - {test}", "FAIL")
        
        return self.tests_passed == self.tests_run


def main():
    tester = MaklonSummaryRegressionTester()
    
    print("\n" + "=" * 80)
    print("DA37/DA40 ERP - Session #11.18 EXTENDED part 2 Regression Test")
    print("Testing: Maklon Summary Aggregate Fix + Full Endpoint Regression")
    print("=" * 80 + "\n")
    
    # Phase 1: Login
    if not tester.test_login():
        print("\n❌ Login failed. Cannot proceed with tests.")
        return 1
    
    # Phase 2: Health check
    tester.test_health()
    
    # Phase 3: KEY BUG FIX - Maklon Summary
    tester.test_maklon_summary()
    
    # Phase 4: Maklon endpoints
    tester.test_maklon_endpoints()
    
    # Phase 5: Core endpoints
    tester.test_core_endpoints()
    
    # Phase 6: Rahaza endpoints
    tester.test_rahaza_endpoints()
    
    # Phase 7: WMS endpoints
    tester.test_wms_endpoints()
    
    # Phase 8: Notification endpoints
    tester.test_notification_endpoints()
    
    # Phase 9: Marketing endpoints
    tester.test_marketing_endpoints()
    
    # Phase 10: Search endpoint
    tester.test_search_endpoint()
    
    # Print summary
    all_passed = tester.print_summary()
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
