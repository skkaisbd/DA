"""
Session #11.18 EXTENDED Part 2 — Backend Regression Test
==========================================================

Backend was NOT changed in this session - only frontend changes (Jest tests + lazy loading + ESLint fixes).
This is a health check to verify backend remains healthy and all endpoints used by the new test files 
+ lazy-loaded components still work correctly.

Tests 20+ endpoints covering:
- Auth & Health
- Products, Orders, Work Orders
- Rahaza (employees, work-orders, salary-grades)
- WMS (buildings)
- Maklon (summary, POs)
- Notifications (list, unread count)
- Marketing (orders, complaints, health, discounts, product-launches, content-calendar, alerts)
- Global Search
"""
import requests
import sys
from datetime import datetime

# Public endpoint from frontend/.env
API = "https://da37-cmt-bridge.preview.emergentagent.com"

class Session11_18RegressionTester:
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
                        for key in check_keys:
                            if key not in resp_data:
                                self.log(f"FAILED - Missing key '{key}' in response", "FAIL")
                                self.failed_tests.append(f"{name} - Missing key '{key}'")
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
                self.failed_tests.append(f"{name} - Status {response.status_code} (expected {expected_status})")
                try:
                    error_detail = response.json()
                    self.log(f"Response: {error_detail}", "INFO")
                except Exception:
                    self.log(f"Response text: {response.text[:200]}", "INFO")
                return False, {}

        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            self.failed_tests.append(f"{name} - {str(e)}")
            return False, {}

    # ========== Auth & Health ==========

    def test_login(self):
        """Test POST /api/auth/login with admin@garment.com / Admin@123"""
        success, response = self.run_test(
            "POST /api/auth/login (admin@garment.com)",
            "POST",
            "/api/auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"},
            check_keys=['token']
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"Token obtained: {self.token[:20]}...", "INFO")
            return True
        return False

    def test_health(self):
        """Test GET /api/health"""
        return self.run_test(
            "GET /api/health",
            "GET",
            "/api/health",
            200,
            check_keys=['status', 'db']
        )[0]

    # ========== Products, Orders, Work Orders ==========

    def test_products(self):
        """Test GET /api/products"""
        return self.run_test(
            "GET /api/products",
            "GET",
            "/api/products",
            200
        )[0]

    def test_orders(self):
        """Test GET /api/orders"""
        return self.run_test(
            "GET /api/orders",
            "GET",
            "/api/orders",
            200
        )[0]

    def test_work_orders(self):
        """Test GET /api/work-orders"""
        return self.run_test(
            "GET /api/work-orders",
            "GET",
            "/api/work-orders",
            200
        )[0]

    # ========== Rahaza Endpoints ==========

    def test_rahaza_employees(self):
        """Test GET /api/rahaza/employees"""
        return self.run_test(
            "GET /api/rahaza/employees",
            "GET",
            "/api/rahaza/employees",
            200
        )[0]

    def test_rahaza_work_orders(self):
        """Test GET /api/rahaza/work-orders"""
        return self.run_test(
            "GET /api/rahaza/work-orders",
            "GET",
            "/api/rahaza/work-orders",
            200
        )[0]

    def test_rahaza_salary_grades(self):
        """Test GET /api/rahaza/salary-grades (verify F601 fix from prior session)"""
        return self.run_test(
            "GET /api/rahaza/salary-grades",
            "GET",
            "/api/rahaza/salary-grades",
            200,
            check_keys=['ok', 'grades']
        )[0]

    # ========== WMS Endpoints ==========

    def test_wms_buildings(self):
        """Test GET /api/wms/buildings"""
        return self.run_test(
            "GET /api/wms/buildings",
            "GET",
            "/api/wms/buildings",
            200
        )[0]

    # ========== Maklon Endpoints ==========

    def test_maklon_summary(self):
        """Test GET /api/dewi/maklon/summary (MaklonDashboard endpoint)"""
        return self.run_test(
            "GET /api/dewi/maklon/summary",
            "GET",
            "/api/dewi/maklon/summary",
            200
        )[0]

    def test_maklon_pos(self):
        """Test GET /api/dewi/maklon/pos (MaklonDashboard orders endpoint)"""
        return self.run_test(
            "GET /api/dewi/maklon/pos",
            "GET",
            "/api/dewi/maklon/pos",
            200
        )[0]

    # ========== Notifications Endpoints ==========

    def test_notifications_list(self):
        """Test GET /api/notifications?limit=5 (NotificationBell endpoint)"""
        return self.run_test(
            "GET /api/notifications?limit=5",
            "GET",
            "/api/notifications?limit=5",
            200
        )[0]

    def test_notifications_unread_count(self):
        """Test GET /api/notifications/unread-count (NotificationBell endpoint)"""
        return self.run_test(
            "GET /api/notifications/unread-count",
            "GET",
            "/api/notifications/unread-count",
            200
        )[0]

    # ========== Marketing Endpoints ==========

    def test_marketing_orders_summary(self):
        """Test GET /api/marketing/orders/summary (MarketingOverviewDashboard endpoint)"""
        return self.run_test(
            "GET /api/marketing/orders/summary",
            "GET",
            "/api/marketing/orders/summary",
            200
        )[0]

    def test_marketing_complaints_summary(self):
        """Test GET /api/marketing/complaints/summary (MarketingOverviewDashboard endpoint)"""
        return self.run_test(
            "GET /api/marketing/complaints/summary",
            "GET",
            "/api/marketing/complaints/summary",
            200
        )[0]

    def test_marketing_health_summary(self):
        """Test GET /api/marketing/health/summary"""
        return self.run_test(
            "GET /api/marketing/health/summary",
            "GET",
            "/api/marketing/health/summary",
            200
        )[0]

    def test_marketing_discounts_summary(self):
        """Test GET /api/marketing/discounts/summary"""
        return self.run_test(
            "GET /api/marketing/discounts/summary",
            "GET",
            "/api/marketing/discounts/summary",
            200
        )[0]

    def test_marketing_product_launches_summary(self):
        """Test GET /api/marketing/product-launches/summary"""
        return self.run_test(
            "GET /api/marketing/product-launches/summary",
            "GET",
            "/api/marketing/product-launches/summary",
            200
        )[0]

    def test_marketing_content_calendar_summary(self):
        """Test GET /api/marketing/content-calendar/summary"""
        return self.run_test(
            "GET /api/marketing/content-calendar/summary",
            "GET",
            "/api/marketing/content-calendar/summary",
            200
        )[0]

    def test_marketing_alerts_evaluate(self):
        """Test POST /api/marketing/alerts/evaluate (MarketingOverviewDashboard Cek Alert button)"""
        return self.run_test(
            "POST /api/marketing/alerts/evaluate",
            "POST",
            "/api/marketing/alerts/evaluate",
            200,
            data={}
        )[0]

    # ========== Global Search ==========

    def test_global_search(self):
        """Test GET /api/global-search?q=test (GlobalSearch endpoint)"""
        return self.run_test(
            "GET /api/global-search?q=test",
            "GET",
            "/api/global-search?q=test",
            200
        )[0]

    # ========== Summary ==========

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("  Session #11.18 Backend Regression Test Summary")
        print("="*70)
        print(f"  Tests Run:    {self.tests_run}")
        print(f"  Tests Passed: {self.tests_passed}")
        print(f"  Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"  Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n  Failed Tests:")
            for i, test in enumerate(self.failed_tests, 1):
                print(f"    {i}. {test}")
        
        print("="*70)
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = Session11_18RegressionTester()
    
    print("="*70)
    print("  Session #11.18 EXTENDED Part 2 — Backend Regression Test")
    print("="*70)
    print(f"  API Endpoint: {API}")
    print(f"  Test Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Credentials:  admin@garment.com / Admin@123")
    print("="*70)
    print()

    # Login first
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1

    # Health check
    print("\n" + "="*70)
    print("  Auth & Health")
    print("="*70)
    tester.test_health()

    # Products, Orders, Work Orders
    print("\n" + "="*70)
    print("  Products, Orders, Work Orders")
    print("="*70)
    tester.test_products()
    tester.test_orders()
    tester.test_work_orders()

    # Rahaza Endpoints
    print("\n" + "="*70)
    print("  Rahaza Endpoints")
    print("="*70)
    tester.test_rahaza_employees()
    tester.test_rahaza_work_orders()
    tester.test_rahaza_salary_grades()

    # WMS Endpoints
    print("\n" + "="*70)
    print("  WMS Endpoints")
    print("="*70)
    tester.test_wms_buildings()

    # Maklon Endpoints
    print("\n" + "="*70)
    print("  Maklon Endpoints")
    print("="*70)
    tester.test_maklon_summary()
    tester.test_maklon_pos()

    # Notifications Endpoints
    print("\n" + "="*70)
    print("  Notifications Endpoints")
    print("="*70)
    tester.test_notifications_list()
    tester.test_notifications_unread_count()

    # Marketing Endpoints
    print("\n" + "="*70)
    print("  Marketing Endpoints")
    print("="*70)
    tester.test_marketing_orders_summary()
    tester.test_marketing_complaints_summary()
    tester.test_marketing_health_summary()
    tester.test_marketing_discounts_summary()
    tester.test_marketing_product_launches_summary()
    tester.test_marketing_content_calendar_summary()
    tester.test_marketing_alerts_evaluate()

    # Global Search
    print("\n" + "="*70)
    print("  Global Search")
    print("="*70)
    tester.test_global_search()

    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
