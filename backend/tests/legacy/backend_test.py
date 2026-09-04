"""
TD-008 P3 Data Architecture — Opname Systems Consolidation Backend Tests
==========================================================================

Tests all opname-related endpoints:
- Phase 2: Migration script (dry-run, live, idempotent)
- Phase 3a: /api/wms/opname2/* (NEW SSOT endpoints)
- Phase 3b: /api/wms/opname (DEPRECATED backward compat)
- Phase 3c: /api/wms/ai/opname/predict-variances (fixed dead refs)
- Regression: /api/acc/opname/* (Session #7 accessory opname)
- Regression: /api/health
"""
import requests
import sys
import subprocess
from datetime import datetime

# Public endpoint from frontend/.env
API = "https://da37-cmt-bridge.preview.emergentagent.com"

class OpnameConsolidationTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.session_id = None  # Store created session ID for lifecycle tests

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

            success = response.status_code == expected_status
            
            if success:
                try:
                    resp_data = response.json()
                    # Check required keys if specified
                    if check_keys:
                        for key in check_keys:
                            if key not in resp_data:
                                self.log(f"FAILED - Missing key '{key}' in response", "FAIL")
                                return False, {}
                    self.tests_passed += 1
                    self.log(f"PASSED - Status: {response.status_code}", "PASS")
                    return True, resp_data
                except Exception as e:
                    if expected_status == 200:
                        self.log(f"FAILED - JSON parse error: {e}", "FAIL")
                        return False, {}
                    self.tests_passed += 1
                    self.log(f"PASSED - Status: {response.status_code}", "PASS")
                    return True, {}
            else:
                self.log(f"FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    self.log(f"Response: {response.json()}", "INFO")
                except Exception:
                    self.log(f"Response text: {response.text[:200]}", "INFO")
                return False, {}

        except Exception as e:
            self.log(f"FAILED - Error: {str(e)}", "FAIL")
            return False, {}

    def test_login(self):
        """Test login with admin credentials"""
        success, response = self.run_test(
            "Login (admin@garment.com)",
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
        """Test health check endpoint"""
        return self.run_test(
            "Health Check",
            "GET",
            "/api/health",
            200
        )[0]

    # ========== Phase 2: Migration Script Tests ==========
    
    def test_migration_dry_run(self):
        """Test migration script in dry-run mode"""
        self.log("Testing migration script (dry-run)...", "INFO")
        try:
            result = subprocess.run(
                ["python3", "-m", "migrations.migrate_opname_consolidation", "--dry-run"],
                cwd="/app/backend",
                capture_output=True,
                text=True,
                timeout=30
            )
            self.tests_run += 1
            if result.returncode == 0 and "DRY-RUN COMPLETE" in result.stdout:
                self.tests_passed += 1
                self.log("Migration dry-run PASSED", "PASS")
                return True
            else:
                self.log(f"Migration dry-run FAILED: {result.stderr}", "FAIL")
                return False
        except Exception as e:
            self.tests_run += 1
            self.log(f"Migration dry-run FAILED: {e}", "FAIL")
            return False

    def test_migration_live(self):
        """Test migration script in live mode"""
        self.log("Testing migration script (live)...", "INFO")
        try:
            result = subprocess.run(
                ["python3", "-m", "migrations.migrate_opname_consolidation"],
                cwd="/app/backend",
                capture_output=True,
                text=True,
                timeout=30
            )
            self.tests_run += 1
            if result.returncode == 0 and "MIGRATION COMPLETE" in result.stdout:
                self.tests_passed += 1
                self.log("Migration live PASSED", "PASS")
                return True
            else:
                self.log(f"Migration live FAILED: {result.stderr}", "FAIL")
                return False
        except Exception as e:
            self.tests_run += 1
            self.log(f"Migration live FAILED: {e}", "FAIL")
            return False

    def test_migration_idempotent(self):
        """Test migration script idempotency (re-run)"""
        self.log("Testing migration script (idempotent re-run)...", "INFO")
        try:
            result = subprocess.run(
                ["python3", "-m", "migrations.migrate_opname_consolidation"],
                cwd="/app/backend",
                capture_output=True,
                text=True,
                timeout=30
            )
            self.tests_run += 1
            # Should complete successfully even if no new data to migrate
            if result.returncode == 0:
                self.tests_passed += 1
                self.log("Migration idempotent re-run PASSED", "PASS")
                return True
            else:
                self.log(f"Migration idempotent FAILED: {result.stderr}", "FAIL")
                return False
        except Exception as e:
            self.tests_run += 1
            self.log(f"Migration idempotent FAILED: {e}", "FAIL")
            return False

    # ========== Phase 3a: NEW SSOT Endpoints /api/wms/opname2/* ==========

    def test_opname2_list(self):
        """Test GET /api/wms/opname2 (list with pagination)"""
        success, data = self.run_test(
            "GET /api/wms/opname2 (list)",
            "GET",
            "/api/wms/opname2?limit=20",
            200,
            check_keys=['items', 'pagination']
        )
        if success:
            self.log(f"Found {len(data.get('items', []))} sessions", "INFO")
        return success

    def test_opname2_stats(self):
        """Test GET /api/wms/opname2/stats (NEW endpoint)"""
        success, data = self.run_test(
            "GET /api/wms/opname2/stats (NEW)",
            "GET",
            "/api/wms/opname2/stats",
            200,
            check_keys=['total_sessions', 'by_status', 'active_count', 'approved_count', 'cancelled_count']
        )
        if success:
            self.log(f"Stats: total={data.get('total_sessions')}, active={data.get('active_count')}", "INFO")
        return success

    def test_opname2_start(self):
        """Test POST /api/wms/opname2/start (create session)"""
        success, data = self.run_test(
            "POST /api/wms/opname2/start (create session)",
            "POST",
            "/api/wms/opname2/start",
            200,
            data={
                "mode": "cycle_count",
                "scope_type": "all",
                "scope_id": "",
                "scope_label": "Test Opname TD-008",
                "notes": "Testing opname consolidation"
            },
            check_keys=['ok', 'session']
        )
        if success and data.get('session'):
            session = data['session']
            self.session_id = session.get('id')
            session_no = session.get('session_no', '')
            self.log(f"Created session: {session_no} (ID: {self.session_id})", "INFO")
            # Verify session_no format OPN/YYYY/MM/NNNN
            if session_no.startswith('OPN/'):
                self.log(f"Session number format correct: {session_no}", "INFO")
            else:
                self.log(f"Session number format incorrect: {session_no}", "FAIL")
                return False
        return success

    def test_opname2_get_detail(self):
        """Test GET /api/wms/opname2/{session_id} (detail with count_items[])"""
        if not self.session_id:
            self.log("Skipping detail test - no session_id", "INFO")
            return True
        
        success, data = self.run_test(
            f"GET /api/wms/opname2/{self.session_id} (detail)",
            "GET",
            f"/api/wms/opname2/{self.session_id}",
            200,
            check_keys=['id', 'session_no', 'status', 'count_items']
        )
        if success:
            self.log(f"Session status: {data.get('status')}, items: {len(data.get('count_items', []))}", "INFO")
        return success

    def test_opname2_scan(self):
        """Test POST /api/wms/opname2/{session_id}/scan (add count)"""
        if not self.session_id:
            self.log("Skipping scan test - no session_id", "INFO")
            return True
        
        success, data = self.run_test(
            f"POST /api/wms/opname2/{self.session_id}/scan (add count)",
            "POST",
            f"/api/wms/opname2/{self.session_id}/scan",
            200,
            data={
                "position_barcode": "TEST-POS-001",
                "position_id": "",
                "material_code": "MAT-TEST-001",
                "counted_qty": 10.0,
                "notes": "Test scan"
            },
            check_keys=['ok']
        )
        if success:
            self.log(f"Scan recorded: counted_items={data.get('counted_items')}/{data.get('total_items')}", "INFO")
        return success

    def test_opname2_submit(self):
        """Test POST /api/wms/opname2/{session_id}/submit (open → pending_approval)"""
        if not self.session_id:
            self.log("Skipping submit test - no session_id", "INFO")
            return True
        
        success, data = self.run_test(
            f"POST /api/wms/opname2/{self.session_id}/submit (submit for approval)",
            "POST",
            f"/api/wms/opname2/{self.session_id}/submit",
            200,
            data={},
            check_keys=['ok', 'pending_approval']
        )
        if success:
            self.log("Session submitted for approval", "INFO")
        return success

    def test_opname2_approve(self):
        """Test POST /api/wms/opname2/{session_id}/approve (pending_approval → approved)"""
        if not self.session_id:
            self.log("Skipping approve test - no session_id", "INFO")
            return True
        
        success, data = self.run_test(
            f"POST /api/wms/opname2/{self.session_id}/approve (approve)",
            "POST",
            f"/api/wms/opname2/{self.session_id}/approve",
            200,
            data={
                "apply_adjustments": True,
                "notes": "Approved by test"
            },
            check_keys=['ok']
        )
        if success:
            self.log(f"Session approved, adjustments_applied={data.get('adjustments_applied')}", "INFO")
        return success

    def test_opname2_cancel_new_session(self):
        """Test POST /api/wms/opname2/{session_id}/cancel (create new session and cancel)"""
        # Create a new session for cancel test
        success, data = self.run_test(
            "POST /api/wms/opname2/start (for cancel test)",
            "POST",
            "/api/wms/opname2/start",
            200,
            data={
                "mode": "cycle_count",
                "scope_type": "rack",
                "scope_id": "test-rack-001",
                "scope_label": "Test Rack for Cancel",
                "notes": "Will be cancelled"
            }
        )
        
        if not success or not data.get('session'):
            self.log("Failed to create session for cancel test", "FAIL")
            return False
        
        cancel_session_id = data['session']['id']
        
        # Now cancel it
        success, data = self.run_test(
            f"POST /api/wms/opname2/{cancel_session_id}/cancel",
            "POST",
            f"/api/wms/opname2/{cancel_session_id}/cancel",
            200,
            data={"reason": "Test cancellation"},
            check_keys=['ok']
        )
        return success

    # ========== Phase 3b: DEPRECATED Backward Compat ==========

    def test_opname_deprecated(self):
        """Test GET /api/wms/opname (DEPRECATED) returns 200 with []"""
        success, data = self.run_test(
            "GET /api/wms/opname (DEPRECATED backward compat)",
            "GET",
            "/api/wms/opname",
            200
        )
        if success:
            # Should return empty list or array
            if isinstance(data, list):
                self.log(f"DEPRECATED endpoint returns list with {len(data)} items", "INFO")
            else:
                self.log(f"DEPRECATED endpoint returns: {type(data)}", "INFO")
        return success

    # ========== Phase 3c: AI Insights Fix ==========

    def test_ai_opname_predict_variances(self):
        """Test POST /api/wms/ai/opname/predict-variances (fixed dead refs)"""
        success, data = self.run_test(
            "POST /api/wms/ai/opname/predict-variances (AI insights)",
            "POST",
            "/api/wms/ai/opname/predict-variances",
            200,
            data={
                "zone_ids": [],
                "cycle_type": "full"
            },
            check_keys=['confidence']
        )
        if success:
            self.log(f"AI prediction confidence: {data.get('confidence')}", "INFO")
            self.log(f"Based on {data.get('based_on_cycles', 0)} cycles", "INFO")
        return success

    # ========== Regression: Accessory Opname (Session #7) ==========

    def test_acc_opname_list(self):
        """Test GET /api/acc/opname (accessory opname from Session #7)"""
        success, data = self.run_test(
            "GET /api/acc/opname (accessory opname regression)",
            "GET",
            "/api/acc/opname",
            200
        )
        if success:
            if isinstance(data, list):
                self.log(f"Accessory opname returns {len(data)} sessions", "INFO")
            else:
                self.log(f"Accessory opname returns: {type(data)}", "INFO")
        return success

    def test_acc_dashboard(self):
        """Test GET /api/acc/dashboard (accessory dashboard regression)"""
        success, data = self.run_test(
            "GET /api/acc/dashboard (accessory dashboard)",
            "GET",
            "/api/acc/dashboard",
            200,
            check_keys=['total_items']
        )
        return success

    # ========== Summary ==========

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("  TD-008 Opname Consolidation Test Summary")
        print("="*70)
        print(f"  Tests Run:    {self.tests_run}")
        print(f"  Tests Passed: {self.tests_passed}")
        print(f"  Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"  Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print("="*70)
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    tester = OpnameConsolidationTester()
    
    print("="*70)
    print("  TD-008 P3 Data Architecture — Opname Consolidation Tests")
    print("="*70)
    print(f"  API Endpoint: {API}")
    print(f"  Test Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*70)
    print()

    # Login first
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1

    # Health check
    tester.test_health()

    # Phase 2: Migration Script Tests
    print("\n" + "="*70)
    print("  Phase 2: Migration Script Tests")
    print("="*70)
    tester.test_migration_dry_run()
    tester.test_migration_live()
    tester.test_migration_idempotent()

    # Phase 3a: NEW SSOT Endpoints
    print("\n" + "="*70)
    print("  Phase 3a: NEW SSOT Endpoints (/api/wms/opname2/*)")
    print("="*70)
    tester.test_opname2_list()
    tester.test_opname2_stats()
    tester.test_opname2_start()  # Creates session, stores session_id
    tester.test_opname2_get_detail()
    tester.test_opname2_scan()
    tester.test_opname2_submit()
    tester.test_opname2_approve()
    tester.test_opname2_cancel_new_session()

    # Phase 3b: DEPRECATED Backward Compat
    print("\n" + "="*70)
    print("  Phase 3b: DEPRECATED Backward Compatibility")
    print("="*70)
    tester.test_opname_deprecated()

    # Phase 3c: AI Insights
    print("\n" + "="*70)
    print("  Phase 3c: AI Insights (Fixed Dead Refs)")
    print("="*70)
    tester.test_ai_opname_predict_variances()

    # Regression: Accessory Opname
    print("\n" + "="*70)
    print("  Regression: Accessory Opname (Session #7)")
    print("="*70)
    tester.test_acc_opname_list()
    tester.test_acc_dashboard()

    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
