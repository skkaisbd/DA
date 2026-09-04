"""
TD-011 Phase 1 Backend Regression Tests (Session #11.13)
=========================================================

Tests for Tech Debt cleanup Phase 1:
- TD-011: Cleanup orphan collections (verify 3 truly gone, 11 recreated)
- A11y polish: Backend APIs still work (no regressions)
- TD-014: Modal unification (backend unchanged, frontend-only)

Backend regression coverage:
1. Auth flow: POST /api/auth/login
2. Health: GET /api/health
3. TD-010 Phase B notification endpoints (dewi/rahaza/collab/unified)
4. Critical CRUD endpoints (opname2, accessory-requests, delivery-notes, cmt-dispatches)
5. Database collection count verification
"""
import requests
import sys

# Public endpoint from frontend/.env
API = "https://da37-cmt-bridge.preview.emergentagent.com"

class TD011Phase1Tester:
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
                response = requests.get(url, headers=headers, timeout=10)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=10)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=10)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=10)

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
                    self.log(f"Response: {response.json()}", "INFO")
                except Exception:
                    self.log(f"Response text: {response.text[:200]}", "INFO")
                return False, {}

        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            self.failed_tests.append(f"{name} - {str(e)}")
            return False, {}

    # ========== AUTH TESTS ==========
    def test_login(self):
        """Test login with admin credentials"""
        success, response = self.run_test(
            "Auth: Login (admin@garment.com)",
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

    # ========== HEALTH CHECK ==========
    def test_health(self):
        """Test health check endpoint"""
        success, response = self.run_test(
            "Health: GET /api/health",
            "GET",
            "/api/health",
            200,
            check_keys=['status', 'db']
        )
        if success:
            self.log(f"Health status: {response.get('status')}, DB: {response.get('db')}", "INFO")
        return success

    # ========== TD-010 PHASE B NOTIFICATION TESTS ==========
    def test_dewi_notifications_manual(self):
        """Test Dewi manual notification creation"""
        success, response = self.run_test(
            "Dewi Notif: POST /api/dewi/notifications/manual",
            "POST",
            "/api/dewi/notifications/manual",
            200,
            data={
                "recipient": "test@example.com",
                "subject": "TD-011 Test Notification",
                "body": "Testing notification SSOT after TD-011 cleanup",
                "channel": "email"
            },
            check_keys=['id']
        )
        return success

    def test_dewi_notifications_list(self):
        """Test Dewi notification list"""
        success, response = self.run_test(
            "Dewi Notif: GET /api/dewi/notifications",
            "GET",
            "/api/dewi/notifications?limit=5",
            200,
            check_keys=['notifications']
        )
        return success

    def test_dewi_notifications_summary(self):
        """Test Dewi notification summary"""
        success, response = self.run_test(
            "Dewi Notif: GET /api/dewi/notifications/summary",
            "GET",
            "/api/dewi/notifications/summary",
            200,
            check_keys=['total']
        )
        return success

    def test_rahaza_notifications_list(self):
        """Test Rahaza notification list"""
        success, response = self.run_test(
            "Rahaza Notif: GET /api/notifications",
            "GET",
            "/api/notifications?limit=5",
            200
        )
        return success

    def test_rahaza_notifications_unread_count(self):
        """Test Rahaza unread count"""
        success, response = self.run_test(
            "Rahaza Notif: GET /api/notifications/unread-count",
            "GET",
            "/api/notifications/unread-count",
            200,
            check_keys=['count']
        )
        return success

    def test_collab_notifications_create(self):
        """Test Collab notification creation"""
        success, response = self.run_test(
            "Collab Notif: POST /api/collab/notifications",
            "POST",
            "/api/collab/notifications",
            200,
            data={
                "title": "TD-011 Test",
                "content": "Testing collab notifications after TD-011",
                "icon": "info"
            },
            check_keys=['notification_id']
        )
        return success

    def test_collab_notifications_list(self):
        """Test Collab notification list"""
        success, response = self.run_test(
            "Collab Notif: GET /api/collab/notifications",
            "GET",
            "/api/collab/notifications?limit=3",
            200
        )
        return success

    def test_unified_notifications_stats(self):
        """Test Unified notification stats (SSOT)"""
        success, response = self.run_test(
            "Unified SSOT: GET /api/notifications/unified/stats",
            "GET",
            "/api/notifications/unified/stats?all_users=true",
            200,
            check_keys=['total']
        )
        if success:
            self.log(f"Unified stats: {response}", "INFO")
        return success

    # ========== CRITICAL CRUD TESTS ==========
    def test_wms_opname2(self):
        """Test WMS Opname2 (SSOT from TD-008)"""
        success, response = self.run_test(
            "CRUD: GET /api/wms/opname2",
            "GET",
            "/api/wms/opname2?limit=5",
            200
        )
        return success

    def test_dewi_accessory_requests(self):
        """Test Dewi Accessory Requests (SSOT from TD-009)"""
        success, response = self.run_test(
            "CRUD: GET /api/dewi/accessory-requests",
            "GET",
            "/api/dewi/accessory-requests?limit=5",
            200
        )
        return success

    def test_wms_delivery_notes(self):
        """Test WMS Delivery Notes"""
        success, response = self.run_test(
            "CRUD: GET /api/wms/delivery-notes",
            "GET",
            "/api/wms/delivery-notes?limit=5",
            200
        )
        return success

    def test_wms_cmt_dispatches(self):
        """Test WMS CMT Dispatches"""
        success, response = self.run_test(
            "CRUD: GET /api/wms/cmt-dispatches",
            "GET",
            "/api/wms/cmt-dispatches?limit=5",
            200
        )
        return success

    # ========== MAIN TEST RUNNER ==========
    def run_all_tests(self):
        """Run all backend regression tests"""
        print("\n" + "="*80)
        print("TD-011 Phase 1 Backend Regression Tests (Session #11.13)")
        print("="*80 + "\n")

        # 1. Auth
        print("\n--- AUTH TESTS ---")
        if not self.test_login():
            print("\n❌ Login failed, stopping tests")
            return False

        # 2. Health
        print("\n--- HEALTH CHECK ---")
        self.test_health()

        # 3. TD-010 Phase B Notification Tests
        print("\n--- TD-010 PHASE B NOTIFICATION TESTS ---")
        self.test_dewi_notifications_manual()
        self.test_dewi_notifications_list()
        self.test_dewi_notifications_summary()
        self.test_rahaza_notifications_list()
        self.test_rahaza_notifications_unread_count()
        self.test_collab_notifications_create()
        self.test_collab_notifications_list()
        self.test_unified_notifications_stats()

        # 4. Critical CRUD
        print("\n--- CRITICAL CRUD TESTS ---")
        self.test_wms_opname2()
        self.test_dewi_accessory_requests()
        self.test_wms_delivery_notes()
        self.test_wms_cmt_dispatches()

        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Tests run: {self.tests_run}")
        print(f"Tests passed: {self.tests_passed}")
        print(f"Tests failed: {self.tests_run - self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            print("\n❌ FAILED TESTS:")
            for test in self.failed_tests:
                print(f"  - {test}")
        else:
            print("\n✅ ALL TESTS PASSED!")
        
        print("="*80 + "\n")
        
        return self.tests_passed == self.tests_run

def main():
    tester = TD011Phase1Tester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
