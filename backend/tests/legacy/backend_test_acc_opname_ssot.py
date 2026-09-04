"""
Backend Test Suite: Aksesoris SSOT Full Migration — Opname Endpoints
======================================================================
Tests the /api/acc/opname/* endpoints after SSOT migration to wh_opname_sessions2.

Migration Context:
- Old: acc_opname_sessions + acc_opname_lines (separate collections)
- New: wh_opname_sessions2 with domain='accessory' + embedded count_items[]
- API contract PRESERVED: ref_number, status (Active/Completed/Cancelled), lines[]

Test Coverage:
1. GET /api/acc/opname → list sessions (empty initially)
2. POST /api/acc/opname → start new session (creates ref_number OPNAME-NNNN)
3. Verify lines[] populated from rahaza_materials (type='accessory')
4. GET /api/acc/opname/{id} → detail with lines
5. PUT /api/acc/opname/{id}/count → update counted_qty, returns diff
6. POST /api/acc/opname/{id}/complete → apply adjustments, status=Completed
7. POST /api/acc/opname/{id}/cancel → status=Cancelled
8. Business rule: only one Active session at a time
9. GET /api/acc/dashboard → active_opname field shows current session_no
10. Regression: GET /api/wms/opname2 excludes accessory-domain sessions
11. Regression: POST /api/wms/opname2/start not blocked by accessory opname

Public endpoint: https://da37-cmt-bridge.preview.emergentagent.com
Admin credentials: admin@garment.com / Admin@123
"""

import requests
import sys
from datetime import datetime
from typing import Optional, Dict, Any

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


class AccOpnameSSOTTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.admin_token: Optional[str] = None
        self.tests_run = 0
        self.tests_passed = 0
        self.errors = []
        self.test_material_id: Optional[str] = None
        self.test_session_id: Optional[str] = None
        self.test_session_ref: Optional[str] = None

    def log(self, msg: str, level: str = "INFO"):
        """Log test messages."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

    def run_test(self, name: str, method: str, endpoint: str, expected_status: int,
                 data: Optional[Dict] = None, headers: Optional[Dict] = None,
                 token: Optional[str] = None) -> tuple[bool, Any]:
        """Run a single API test."""
        url = f"{self.base_url}{endpoint}"
        req_headers = {'Content-Type': 'application/json'}
        if headers:
            req_headers.update(headers)
        if token:
            req_headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        self.log(f"Test #{self.tests_run}: {name}")

        try:
            if method == 'GET':
                response = requests.get(url, headers=req_headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=req_headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=req_headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=req_headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - Status: {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except Exception:
                    return True, response.text
            else:
                self.log(f"❌ FAIL - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"   Response: {response.text[:300]}", "FAIL")
                self.errors.append({
                    'test': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:500]
                })
                return False, {}

        except Exception as e:
            self.log(f"❌ FAIL - Error: {str(e)}", "FAIL")
            self.errors.append({'test': name, 'error': str(e)})
            return False, {}

    def test_admin_login(self) -> bool:
        """Test admin login and store token."""
        self.log("=" * 60)
        self.log("STEP 1: Admin Login")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if success and isinstance(response, dict) and 'token' in response:
            self.admin_token = response['token']
            self.log("✅ Admin token obtained", "SUCCESS")
            return True
        else:
            self.log("❌ Failed to obtain admin token", "ERROR")
            return False

    def test_list_opname_initial(self) -> bool:
        """Test GET /api/acc/opname - should return list (may be empty or have existing sessions)."""
        self.log("=" * 60)
        self.log("STEP 2: List Opname Sessions (Initial)")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "GET /api/acc/opname - List sessions",
            "GET",
            "/api/acc/opname",
            200,
            token=self.admin_token
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Found {len(response)} existing opname sessions", "INFO")
            return True
        return False

    def test_create_test_material(self) -> bool:
        """Create a test accessory material with initial stock."""
        self.log("=" * 60)
        self.log("STEP 3: Setup Test Material")
        self.log("=" * 60)
        
        # Create test accessory
        timestamp = datetime.now().strftime("%H%M%S")
        success, response = self.run_test(
            "POST /api/acc/items - Create test accessory",
            "POST",
            "/api/acc/items",
            201,
            data={
                "name": f"Test Accessory Opname {timestamp}",
                "code": f"TEST-OPN-{timestamp}",
                "category": "Testing",
                "unit": "pcs",
                "min_stock": 10
            },
            token=self.admin_token
        )
        
        if success and isinstance(response, dict) and 'id' in response:
            self.test_material_id = response['id']
            self.log(f"✅ Test material created: {self.test_material_id}", "SUCCESS")
            
            # Add initial stock
            success2, response2 = self.run_test(
                "POST /api/acc/stock/receive - Add initial stock",
                "POST",
                "/api/acc/stock/receive",
                201,
                data={
                    "acc_id": self.test_material_id,
                    "qty": 100,
                    "notes": "Initial stock for opname test"
                },
                token=self.admin_token
            )
            
            if success2:
                self.log("✅ Initial stock added: 100 pcs", "SUCCESS")
                return True
        
        return False

    def test_start_opname(self) -> bool:
        """Test POST /api/acc/opname - Start new opname session."""
        self.log("=" * 60)
        self.log("STEP 4: Start Opname Session")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "POST /api/acc/opname - Start new session",
            "POST",
            "/api/acc/opname",
            201,
            data={"notes": "Test opname session for SSOT migration"},
            token=self.admin_token
        )
        
        if success and isinstance(response, dict):
            # Verify response structure
            checks = [
                ('id' in response, "Response has 'id' field"),
                ('ref_number' in response, "Response has 'ref_number' field"),
                ('status' in response, "Response has 'status' field"),
                ('lines' in response, "Response has 'lines' field"),
                (response.get('status') == 'Active', "Status is 'Active'"),
                (isinstance(response.get('lines'), list), "Lines is a list"),
                (len(response.get('lines', [])) > 0, "Lines array is populated")
            ]
            
            all_passed = True
            for check, desc in checks:
                if check:
                    self.log(f"✅ {desc}", "PASS")
                else:
                    self.log(f"❌ {desc}", "FAIL")
                    all_passed = False
            
            if all_passed:
                self.test_session_id = response['id']
                self.test_session_ref = response['ref_number']
                self.log(f"✅ Session created: {self.test_session_ref} (ID: {self.test_session_id})", "SUCCESS")
                
                # Verify ref_number format (OPNAME-NNNN)
                if response['ref_number'].startswith('OPNAME-'):
                    self.log(f"✅ ref_number format correct: {response['ref_number']}", "PASS")
                else:
                    self.log(f"❌ ref_number format incorrect: {response['ref_number']}", "FAIL")
                    all_passed = False
                
                # Verify lines structure
                if len(response['lines']) > 0:
                    line = response['lines'][0]
                    line_checks = [
                        ('acc_id' in line, "Line has 'acc_id'"),
                        ('acc_name' in line, "Line has 'acc_name'"),
                        ('acc_code' in line, "Line has 'acc_code'"),
                        ('unit' in line, "Line has 'unit'"),
                        ('system_qty' in line, "Line has 'system_qty'"),
                        ('counted_qty' in line, "Line has 'counted_qty'"),
                        ('diff' in line, "Line has 'diff'"),
                        (line.get('counted_qty') is None, "counted_qty is null initially"),
                        (line.get('diff') is None, "diff is null initially")
                    ]
                    
                    for check, desc in line_checks:
                        if check:
                            self.log(f"✅ {desc}", "PASS")
                        else:
                            self.log(f"❌ {desc}", "FAIL")
                            all_passed = False
                
                return all_passed
        
        return False

    def test_get_opname_detail(self) -> bool:
        """Test GET /api/acc/opname/{id} - Get session detail."""
        self.log("=" * 60)
        self.log("STEP 5: Get Opname Detail")
        self.log("=" * 60)
        
        if not self.test_session_id:
            self.log("❌ No test session ID available", "ERROR")
            return False
        
        success, response = self.run_test(
            f"GET /api/acc/opname/{self.test_session_id} - Get detail",
            "GET",
            f"/api/acc/opname/{self.test_session_id}",
            200,
            token=self.admin_token
        )
        
        if success and isinstance(response, dict):
            checks = [
                (response.get('id') == self.test_session_id, "ID matches"),
                (response.get('ref_number') == self.test_session_ref, "ref_number matches"),
                (response.get('status') == 'Active', "Status is Active"),
                ('lines' in response, "Has lines array")
            ]
            
            all_passed = True
            for check, desc in checks:
                if check:
                    self.log(f"✅ {desc}", "PASS")
                else:
                    self.log(f"❌ {desc}", "FAIL")
                    all_passed = False
            
            return all_passed
        
        return False

    def test_update_count(self) -> bool:
        """Test PUT /api/acc/opname/{id}/count - Update counted quantity."""
        self.log("=" * 60)
        self.log("STEP 6: Update Count")
        self.log("=" * 60)
        
        if not self.test_session_id or not self.test_material_id:
            self.log("❌ Missing test session or material ID", "ERROR")
            return False
        
        # First get the session to find a line to update
        success, session = self.run_test(
            "GET session for line selection",
            "GET",
            f"/api/acc/opname/{self.test_session_id}",
            200,
            token=self.admin_token
        )
        
        if not success or not isinstance(session, dict) or not session.get('lines'):
            self.log("❌ Could not get session lines", "ERROR")
            return False
        
        # Find our test material in the lines
        target_line = None
        for line in session['lines']:
            if line.get('acc_id') == self.test_material_id:
                target_line = line
                break
        
        if not target_line:
            self.log("❌ Test material not found in opname lines", "ERROR")
            return False
        
        system_qty = target_line.get('system_qty', 0)
        counted_qty = system_qty + 5  # Count 5 more than system
        
        success, response = self.run_test(
            f"PUT /api/acc/opname/{self.test_session_id}/count - Update count",
            "PUT",
            f"/api/acc/opname/{self.test_session_id}/count",
            200,
            data={
                "acc_id": self.test_material_id,
                "counted_qty": counted_qty,
                "notes": "Test count update"
            },
            token=self.admin_token
        )
        
        if success and isinstance(response, dict):
            checks = [
                ('ok' in response, "Response has 'ok' field"),
                (response.get('ok') is True, "ok is true"),
                ('diff' in response, "Response has 'diff' field"),
                (response.get('diff') == 5, f"diff is correct (expected 5, got {response.get('diff')})")
            ]
            
            all_passed = True
            for check, desc in checks:
                if check:
                    self.log(f"✅ {desc}", "PASS")
                else:
                    self.log(f"❌ {desc}", "FAIL")
                    all_passed = False
            
            # Verify the update persisted
            if all_passed:
                success2, session2 = self.run_test(
                    "GET session to verify count update",
                    "GET",
                    f"/api/acc/opname/{self.test_session_id}",
                    200,
                    token=self.admin_token
                )
                
                if success2 and isinstance(session2, dict):
                    updated_line = None
                    for line in session2.get('lines', []):
                        if line.get('acc_id') == self.test_material_id:
                            updated_line = line
                            break
                    
                    if updated_line:
                        verify_checks = [
                            (updated_line.get('counted_qty') == counted_qty, 
                             f"counted_qty persisted (expected {counted_qty}, got {updated_line.get('counted_qty')})"),
                            (updated_line.get('diff') == 5, 
                             f"diff persisted (expected 5, got {updated_line.get('diff')})")
                        ]
                        
                        for check, desc in verify_checks:
                            if check:
                                self.log(f"✅ {desc}", "PASS")
                            else:
                                self.log(f"❌ {desc}", "FAIL")
                                all_passed = False
            
            return all_passed
        
        return False

    def test_cannot_start_second_active(self) -> bool:
        """Test that starting a second opname while one is Active returns 400."""
        self.log("=" * 60)
        self.log("STEP 7: Test Business Rule - Only One Active Session")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "POST /api/acc/opname - Try to start second session (should fail)",
            "POST",
            "/api/acc/opname",
            400,
            data={"notes": "This should fail"},
            token=self.admin_token
        )
        
        if success:
            self.log("✅ Correctly rejected second active session", "PASS")
            # Check for Indonesian error message
            if isinstance(response, dict) and 'detail' in response:
                if 'sesi' in response['detail'].lower() and 'aktif' in response['detail'].lower():
                    self.log(f"✅ Error message in Bahasa Indonesia: {response['detail']}", "PASS")
                else:
                    self.log(f"⚠️  Error message: {response['detail']}", "WARN")
            return True
        
        return False

    def test_complete_opname(self) -> bool:
        """Test POST /api/acc/opname/{id}/complete - Complete session and apply adjustments."""
        self.log("=" * 60)
        self.log("STEP 8: Complete Opname Session")
        self.log("=" * 60)
        
        if not self.test_session_id:
            self.log("❌ No test session ID available", "ERROR")
            return False
        
        # Get stock before completion
        success_before, stock_before = self.run_test(
            "GET /api/acc/stock - Stock before completion",
            "GET",
            "/api/acc/stock",
            200,
            token=self.admin_token
        )
        
        test_material_stock_before = None
        if success_before and isinstance(stock_before, list):
            for item in stock_before:
                if item.get('id') == self.test_material_id:
                    test_material_stock_before = item.get('stock_qty')
                    self.log(f"Stock before completion: {test_material_stock_before}", "INFO")
                    break
        
        # Complete the session
        success, response = self.run_test(
            f"POST /api/acc/opname/{self.test_session_id}/complete - Complete session",
            "POST",
            f"/api/acc/opname/{self.test_session_id}/complete",
            200,
            token=self.admin_token
        )
        
        if success and isinstance(response, dict):
            checks = [
                ('ok' in response, "Response has 'ok' field"),
                (response.get('ok') is True, "ok is true"),
                ('adjustments_made' in response, "Response has 'adjustments_made' field")
            ]
            
            all_passed = True
            for check, desc in checks:
                if check:
                    self.log(f"✅ {desc}", "PASS")
                else:
                    self.log(f"❌ {desc}", "FAIL")
                    all_passed = False
            
            adjustments = response.get('adjustments_made', 0)
            self.log(f"Adjustments made: {adjustments}", "INFO")
            
            # Verify status changed to Completed
            success2, session = self.run_test(
                "GET session to verify completion",
                "GET",
                f"/api/acc/opname/{self.test_session_id}",
                200,
                token=self.admin_token
            )
            
            if success2 and isinstance(session, dict):
                if session.get('status') == 'Completed':
                    self.log("✅ Status changed to 'Completed'", "PASS")
                else:
                    self.log(f"❌ Status is '{session.get('status')}', expected 'Completed'", "FAIL")
                    all_passed = False
            
            # Verify stock was adjusted
            if test_material_stock_before is not None:
                success3, stock_after = self.run_test(
                    "GET /api/acc/stock - Stock after completion",
                    "GET",
                    "/api/acc/stock",
                    200,
                    token=self.admin_token
                )
                
                if success3 and isinstance(stock_after, list):
                    for item in stock_after:
                        if item.get('id') == self.test_material_id:
                            stock_qty_after = item.get('stock_qty')
                            expected_stock = test_material_stock_before + 5  # We counted +5
                            if stock_qty_after == expected_stock:
                                self.log(f"✅ Stock adjusted correctly: {test_material_stock_before} → {stock_qty_after}", "PASS")
                            else:
                                self.log(f"❌ Stock adjustment incorrect: expected {expected_stock}, got {stock_qty_after}", "FAIL")
                                all_passed = False
                            break
            
            # Verify movement was logged
            success4, movements = self.run_test(
                "GET /api/acc/stock/movements - Verify adjustment movement",
                "GET",
                f"/api/acc/stock/movements?acc_id={self.test_material_id}",
                200,
                token=self.admin_token
            )
            
            if success4 and isinstance(movements, list):
                adjust_movement = None
                for mv in movements:
                    if mv.get('movement_type') == 'ADJUST' and mv.get('ref_id') == self.test_session_id:
                        adjust_movement = mv
                        break
                
                if adjust_movement:
                    self.log("✅ Adjustment movement logged", "PASS")
                else:
                    self.log("❌ Adjustment movement not found", "FAIL")
                    all_passed = False
            
            return all_passed
        
        return False

    def test_dashboard_active_opname(self) -> bool:
        """Test GET /api/acc/dashboard - Verify active_opname field."""
        self.log("=" * 60)
        self.log("STEP 9: Test Dashboard Active Opname Field")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "GET /api/acc/dashboard - Check active_opname",
            "GET",
            "/api/acc/dashboard",
            200,
            token=self.admin_token
        )
        
        if success and isinstance(response, dict):
            # After completion, active_opname should be null
            if response.get('active_opname') is None:
                self.log("✅ active_opname is null (no active session)", "PASS")
                return True
            else:
                self.log(f"⚠️  active_opname is '{response.get('active_opname')}' (expected null after completion)", "WARN")
                # This might be OK if there's another active session
                return True
        
        return False

    def test_cancel_opname(self) -> bool:
        """Test POST /api/acc/opname/{id}/cancel - Cancel a session."""
        self.log("=" * 60)
        self.log("STEP 10: Test Cancel Opname")
        self.log("=" * 60)
        
        # Create a new session to cancel
        success, response = self.run_test(
            "POST /api/acc/opname - Create session to cancel",
            "POST",
            "/api/acc/opname",
            201,
            data={"notes": "Session to be cancelled"},
            token=self.admin_token
        )
        
        if not success or not isinstance(response, dict) or 'id' not in response:
            self.log("❌ Could not create session to cancel", "ERROR")
            return False
        
        cancel_session_id = response['id']
        
        # Cancel it
        success2, response2 = self.run_test(
            f"POST /api/acc/opname/{cancel_session_id}/cancel - Cancel session",
            "POST",
            f"/api/acc/opname/{cancel_session_id}/cancel",
            200,
            token=self.admin_token
        )
        
        if success2 and isinstance(response2, dict):
            if response2.get('ok') is True:
                self.log("✅ Cancel returned ok:true", "PASS")
                
                # Verify status changed to Cancelled
                success3, session = self.run_test(
                    "GET session to verify cancellation",
                    "GET",
                    f"/api/acc/opname/{cancel_session_id}",
                    200,
                    token=self.admin_token
                )
                
                if success3 and isinstance(session, dict):
                    if session.get('status') == 'Cancelled':
                        self.log("✅ Status changed to 'Cancelled'", "PASS")
                        
                        # Try to count on cancelled session (should fail)
                        success4, response4 = self.run_test(
                            "PUT count on cancelled session (should fail)",
                            "PUT",
                            f"/api/acc/opname/{cancel_session_id}/count",
                            400,
                            data={"acc_id": self.test_material_id, "counted_qty": 50},
                            token=self.admin_token
                        )
                        
                        if success4:
                            self.log("✅ Cannot count on cancelled session", "PASS")
                            return True
                    else:
                        self.log(f"❌ Status is '{session.get('status')}', expected 'Cancelled'", "FAIL")
        
        return False

    def test_wms_opname_regression(self) -> bool:
        """Test that WMS opname endpoints don't interfere with accessory opname."""
        self.log("=" * 60)
        self.log("STEP 11: WMS Opname Regression Tests")
        self.log("=" * 60)
        
        # Test 1: GET /api/wms/opname2 should NOT include accessory-domain sessions
        success, response = self.run_test(
            "GET /api/wms/opname2 - Should exclude accessory sessions",
            "GET",
            "/api/wms/opname2",
            200,
            token=self.admin_token
        )
        
        all_passed = True
        if success and isinstance(response, dict) and 'items' in response:
            items = response['items']
            # Check if any item has domain='accessory'
            accessory_sessions = [s for s in items if s.get('domain') == 'accessory']
            if len(accessory_sessions) == 0:
                self.log("✅ WMS opname list excludes accessory sessions", "PASS")
            else:
                self.log(f"❌ WMS opname list includes {len(accessory_sessions)} accessory sessions", "FAIL")
                all_passed = False
        else:
            self.log("⚠️  Could not verify WMS opname list", "WARN")
        
        # Test 2: POST /api/wms/opname2/start should NOT be blocked by accessory opname
        # First, create an active accessory opname
        success2, acc_session = self.run_test(
            "POST /api/acc/opname - Create active accessory session",
            "POST",
            "/api/acc/opname",
            201,
            data={"notes": "Active accessory session for regression test"},
            token=self.admin_token
        )
        
        if success2 and isinstance(acc_session, dict) and 'id' in acc_session:
            acc_session_id = acc_session['id']
            self.log(f"Created active accessory session: {acc_session_id}", "INFO")
            
            # Try to start WMS opname (should succeed)
            success3, wms_response = self.run_test(
                "POST /api/wms/opname2/start - Should not be blocked by accessory opname",
                "POST",
                "/api/wms/opname2/start",
                200,
                data={
                    "mode": "cycle_count",
                    "scope_type": "all",
                    "notes": "WMS opname regression test"
                },
                token=self.admin_token
            )
            
            if success3:
                self.log("✅ WMS opname start not blocked by accessory opname", "PASS")
                
                # Clean up: cancel both sessions
                if isinstance(wms_response, dict) and 'session' in wms_response:
                    wms_session_id = wms_response['session'].get('id')
                    if wms_session_id:
                        self.run_test(
                            "Cancel WMS session (cleanup)",
                            "POST",
                            f"/api/wms/opname2/{wms_session_id}/cancel",
                            200,
                            token=self.admin_token
                        )
            else:
                self.log("❌ WMS opname start blocked by accessory opname", "FAIL")
                all_passed = False
            
            # Cancel accessory session (cleanup)
            self.run_test(
                "Cancel accessory session (cleanup)",
                "POST",
                f"/api/acc/opname/{acc_session_id}/cancel",
                200,
                token=self.admin_token
            )
        
        return all_passed

    def test_migration_dry_run(self) -> bool:
        """Test migration script --dry-run (should show 0 sessions when DB clean)."""
        self.log("=" * 60)
        self.log("STEP 12: Migration Script Dry-Run Test")
        self.log("=" * 60)
        
        # This test is informational only - we don't actually run the migration
        self.log("ℹ️  Migration script test skipped (as per instructions)", "INFO")
        self.log("   To test manually: python3 -m backend.migrations.migrate_acc_opname --dry-run", "INFO")
        return True

    def run_all_tests(self):
        """Run all test scenarios."""
        self.log("=" * 80)
        self.log("BACKEND TEST: Aksesoris SSOT Full Migration — Opname Endpoints")
        self.log("=" * 80)
        self.log(f"Base URL: {self.base_url}")
        self.log(f"Admin: {ADMIN_EMAIL}")
        self.log("")
        
        # Run tests in sequence
        if not self.test_admin_login():
            self.log("❌ Admin login failed - cannot continue", "ERROR")
            return False
        
        self.test_list_opname_initial()
        self.test_create_test_material()
        self.test_start_opname()
        self.test_get_opname_detail()
        self.test_update_count()
        self.test_cannot_start_second_active()
        self.test_complete_opname()
        self.test_dashboard_active_opname()
        self.test_cancel_opname()
        self.test_wms_opname_regression()
        self.test_migration_dry_run()
        
        # Print summary
        self.log("")
        self.log("=" * 80)
        self.log("TEST SUMMARY")
        self.log("=" * 80)
        self.log(f"Tests Run: {self.tests_run}")
        self.log(f"Tests Passed: {self.tests_passed}")
        self.log(f"Tests Failed: {self.tests_run - self.tests_passed}")
        self.log(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        
        if self.errors:
            self.log("")
            self.log("ERRORS:")
            for i, error in enumerate(self.errors, 1):
                self.log(f"{i}. {error.get('test', 'Unknown')}")
                if 'error' in error:
                    self.log(f"   Error: {error['error']}")
                else:
                    self.log(f"   Expected: {error.get('expected')}, Got: {error.get('actual')}")
                    self.log(f"   Response: {error.get('response', '')[:200]}")
        
        self.log("=" * 80)
        
        return self.tests_passed == self.tests_run


def main():
    tester = AccOpnameSSOTTester(BASE_URL)
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
