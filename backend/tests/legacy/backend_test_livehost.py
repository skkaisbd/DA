"""
Backend Test for LiveHost Management Module (Session #11 Refactor Verification)
Tests all LiveHost APIs to ensure zero regressions after frontend refactoring.
"""
import requests
import sys
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


class LiveHostBackendTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.created_ids = {
            'hosts': [],
            'shifts': [],
            'scripts': [],
            'trainings': []
        }

    def log(self, message, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, verify_fn=None):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Test #{self.tests_run}: {name}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                # Additional verification if provided
                if verify_fn:
                    try:
                        response_data = response.json() if response.text else {}
                        verify_result = verify_fn(response_data)
                        if not verify_result:
                            success = False
                            self.log("  ❌ FAILED - Verification failed", "ERROR")
                            self.test_results.append({
                                "test": name,
                                "status": "FAILED",
                                "reason": "Verification failed",
                                "endpoint": endpoint
                            })
                            return False, {}
                    except Exception as e:
                        success = False
                        self.log(f"  ❌ FAILED - Verification error: {str(e)}", "ERROR")
                        self.test_results.append({
                            "test": name,
                            "status": "FAILED",
                            "reason": f"Verification error: {str(e)}",
                            "endpoint": endpoint
                        })
                        return False, {}
            
            if success:
                self.tests_passed += 1
                self.log(f"  ✅ PASSED - Status: {response.status_code}")
                self.test_results.append({
                    "test": name,
                    "status": "PASSED",
                    "endpoint": endpoint
                })
                return True, response.json() if response.text else {}
            else:
                self.log(f"  ❌ FAILED - Expected {expected_status}, got {response.status_code}", "ERROR")
                try:
                    error_detail = response.json()
                    self.log(f"     Error: {error_detail}", "ERROR")
                except Exception:
                    self.log(f"     Response: {response.text[:200]}", "ERROR")
                self.test_results.append({
                    "test": name,
                    "status": "FAILED",
                    "reason": f"Expected {expected_status}, got {response.status_code}",
                    "endpoint": endpoint
                })
                return False, {}

        except Exception as e:
            self.log(f"  ❌ FAILED - Exception: {str(e)}", "ERROR")
            self.test_results.append({
                "test": name,
                "status": "FAILED",
                "reason": str(e),
                "endpoint": endpoint
            })
            return False, {}

    def test_login(self):
        """Test admin login"""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log("✅ Login successful, token acquired")
            return True
        self.log("❌ Login failed", "ERROR")
        return False

    def test_create_livehost(self):
        """Test creating a LiveHost"""
        test_email = f"testhost_{datetime.now().strftime('%H%M%S')}@test.com"
        success, response = self.run_test(
            "Create LiveHost",
            "POST",
            "/api/marketing/livehost",
            200,
            data={
                "name": "Test LiveHost",
                "email": test_email,
                "password": "TestPass123!",
                "phone": "081234567890",
                "employment_type": "part_time",
                "hourly_rate": 50000,
                "shift_preferences": ["morning", "afternoon"],
                "language_skills": ["indonesia", "english"],
                "product_expertise": ["fashion", "beauty"],
                "assigned_account_ids": [],
                "notes": "Test host for refactor verification"
            },
            verify_fn=lambda r: 'host' in r and r['host'].get('email') == test_email
        )
        if success and 'host' in response:
            self.created_ids['hosts'].append(response['host']['id'])
            return True
        return False

    def test_list_livehosts(self):
        """Test listing LiveHosts"""
        success, response = self.run_test(
            "List LiveHosts",
            "GET",
            "/api/marketing/livehost",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        return success

    def test_list_livehosts_with_filter(self):
        """Test listing LiveHosts with status filter"""
        success, response = self.run_test(
            "List LiveHosts (status=active)",
            "GET",
            "/api/marketing/livehost?status=active",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        return success

    def test_update_livehost(self):
        """Test updating a LiveHost"""
        if not self.created_ids['hosts']:
            self.log("⚠️  Skipping update test - no host created", "WARN")
            return True
        
        host_id = self.created_ids['hosts'][0]
        success, response = self.run_test(
            "Update LiveHost",
            "PATCH",
            f"/api/marketing/livehost/{host_id}",
            200,
            data={
                "name": "Updated Test LiveHost",
                "hourly_rate": 60000,
                "notes": "Updated via test"
            }
        )
        return success

    def test_create_shift(self):
        """Test creating a shift"""
        if not self.created_ids['hosts']:
            self.log("⚠️  Skipping shift creation - no host created", "WARN")
            return True
        
        # Get first active account
        success, accounts = self.run_test(
            "Get Active Accounts for Shift",
            "GET",
            "/api/marketing/accounts?status=active",
            200
        )
        
        if not success or not accounts:
            self.log("⚠️  No active accounts found, skipping shift creation", "WARN")
            return True
        
        host_id = self.created_ids['hosts'][0]
        account_id = accounts[0]['id']
        tomorrow = (datetime.now() + timedelta(days=1)).strftime('%Y-%m-%d')
        
        success, response = self.run_test(
            "Create Shift",
            "POST",
            "/api/marketing/livehost/shifts",
            200,
            data={
                "host_id": host_id,
                "account_id": account_id,
                "date": tomorrow,
                "shift_type": "morning",
                "shift_start_time": "09:00",
                "shift_end_time": "13:00",
                "notes": "Test shift"
            },
            verify_fn=lambda r: 'shift' in r
        )
        
        if success and 'shift' in response:
            self.created_ids['shifts'].append(response['shift']['id'])
            return True
        return False

    def test_list_shifts(self):
        """Test listing shifts"""
        success, response = self.run_test(
            "List Shifts",
            "GET",
            "/api/marketing/livehost/shifts?page=1&limit=50",
            200,
            verify_fn=lambda r: 'shifts' in r and 'pagination' in r
        )
        return success

    def test_list_shifts_with_filter(self):
        """Test listing shifts with host filter"""
        if not self.created_ids['hosts']:
            self.log("⚠️  Skipping shift filter test - no host created", "WARN")
            return True
        
        host_id = self.created_ids['hosts'][0]
        success, response = self.run_test(
            "List Shifts (filtered by host)",
            "GET",
            f"/api/marketing/livehost/shifts?host_id={host_id}",
            200,
            verify_fn=lambda r: 'shifts' in r
        )
        return success

    def test_create_script(self):
        """Test creating a script"""
        success, response = self.run_test(
            "Create Script",
            "POST",
            "/api/marketing/livehost/scripts",
            200,
            data={
                "title": "Test Opening Script",
                "category": "opening",
                "script_text": "Halo semuanya! Selamat datang di live kami hari ini!",
                "language": "indonesia",
                "account_id": None,
                "products_applicable": ["fashion", "beauty"]
            },
            verify_fn=lambda r: 'script' in r
        )
        
        if success and 'script' in response:
            self.created_ids['scripts'].append(response['script']['id'])
            return True
        return False

    def test_list_scripts(self):
        """Test listing scripts"""
        success, response = self.run_test(
            "List Scripts",
            "GET",
            "/api/marketing/livehost/scripts",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        return success

    def test_list_scripts_with_filter(self):
        """Test listing scripts with category filter"""
        success, response = self.run_test(
            "List Scripts (category=opening)",
            "GET",
            "/api/marketing/livehost/scripts?category=opening",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        return success

    def test_create_training(self):
        """Test creating a training"""
        success, response = self.run_test(
            "Create Training",
            "POST",
            "/api/marketing/livehost/training",
            200,
            data={
                "title": "Test Product Knowledge Training",
                "category": "product_knowledge",
                "description": "Learn about our fashion products",
                "content_type": "video",
                "duration_minutes": 30,
                "is_required": True,
                "passing_score": 80,
                "expiry_months": 6
            },
            verify_fn=lambda r: 'training' in r
        )
        
        if success and 'training' in response:
            self.created_ids['trainings'].append(response['training']['id'])
            return True
        return False

    def test_list_trainings(self):
        """Test listing trainings"""
        success, response = self.run_test(
            "List Trainings",
            "GET",
            "/api/marketing/livehost/training",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        return success

    def test_assign_training(self):
        """Test assigning training to hosts"""
        if not self.created_ids['hosts'] or not self.created_ids['trainings']:
            self.log("⚠️  Skipping training assignment - no host or training created", "WARN")
            return True
        
        success, response = self.run_test(
            "Assign Training to Host",
            "POST",
            "/api/marketing/livehost/training/assign",
            200,
            data={
                "training_id": self.created_ids['trainings'][0],
                "host_ids": [self.created_ids['hosts'][0]]
            }
        )
        return success

    def test_delete_livehost(self):
        """Test deleting a LiveHost"""
        if not self.created_ids['hosts']:
            self.log("⚠️  Skipping delete test - no host created", "WARN")
            return True
        
        host_id = self.created_ids['hosts'][0]
        success, response = self.run_test(
            "Delete LiveHost",
            "DELETE",
            f"/api/marketing/livehost/{host_id}",
            200
        )
        return success

    def run_all_tests(self):
        """Run all tests in sequence"""
        self.log("=" * 80)
        self.log("LiveHost Management Backend API Tests (Session #11 Refactor Verification)")
        self.log("=" * 80)
        
        # Login first
        if not self.test_login():
            self.log("❌ Login failed, cannot proceed with tests", "ERROR")
            return False
        
        # Run all tests
        tests = [
            self.test_create_livehost,
            self.test_list_livehosts,
            self.test_list_livehosts_with_filter,
            self.test_update_livehost,
            self.test_create_shift,
            self.test_list_shifts,
            self.test_list_shifts_with_filter,
            self.test_create_script,
            self.test_list_scripts,
            self.test_list_scripts_with_filter,
            self.test_create_training,
            self.test_list_trainings,
            self.test_assign_training,
            self.test_delete_livehost,
        ]
        
        for test in tests:
            try:
                test()
            except Exception as e:
                self.log(f"❌ Test {test.__name__} raised exception: {str(e)}", "ERROR")
        
        # Print summary
        self.log("=" * 80)
        self.log(f"SUMMARY: {self.tests_passed}/{self.tests_run} tests passed")
        self.log("=" * 80)
        
        # Print failed tests
        failed_tests = [t for t in self.test_results if t['status'] == 'FAILED']
        if failed_tests:
            self.log("\n❌ FAILED TESTS:")
            for test in failed_tests:
                self.log(f"  - {test['test']}: {test.get('reason', 'Unknown')}")
        
        return self.tests_passed == self.tests_run


def main():
    tester = LiveHostBackendTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
