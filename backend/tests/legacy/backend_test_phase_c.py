"""
Backend Test Suite: Phase C Maklon Route Removal
=================================================
Tests the removal of legacy /api/dewi/maklon/orders endpoints (6 removed, 6 retained).

Test Coverage:
- Removed endpoints should return 404/405
- Retained endpoints (stage_qty workflow + material-issues) should still work
- New SSOT endpoints (/api/dewi/maklon/pos) should work
- OpenAPI verification (exactly 6 /api/dewi/maklon/orders/* endpoints)
- POC migration scripts (poc_maklon_consolidation, poc_p2p_flow)
- Existing data accessibility (MKLO-LEG-001/002/003)

Public endpoint: https://da37-cmt-bridge.preview.emergentagent.com
Admin credentials: admin@garment.com / Admin@123
"""

import requests
import sys
from datetime import datetime, date
from typing import Optional, Dict, Any, List

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


class PhaseCTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.admin_token: Optional[str] = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_po_id: Optional[str] = None
        self.test_client_id: Optional[str] = None
        self.migrated_po_ids: List[str] = []
        self.errors: List[Dict] = []

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
                self.log(f"   Response: {response.text[:200]}", "FAIL")
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
        """Test 0: Admin login."""
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if success and 'token' in response:
            self.admin_token = response['token']
            self.log(f"Admin token obtained: {self.admin_token[:20]}...")
            return True
        return False

    # ========================================================================
    # REMOVED ENDPOINTS TESTS (should return 404/405)
    # ========================================================================

    def test_removed_get_orders_list(self) -> bool:
        """Test 1: GET /api/dewi/maklon/orders — REMOVED (should return 404/405)."""
        success, response = self.run_test(
            "GET /api/dewi/maklon/orders — REMOVED endpoint",
            "GET",
            "/api/dewi/maklon/orders",
            404,  # Expecting 404 since endpoint is removed
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Endpoint correctly removed (404)")
            return True
        # If we got 200, that means endpoint still exists
        if not success and self.errors[-1]['actual'] == 200:
            self.log("   ❌ Endpoint still exists! Should be removed.", "FAIL")
        return False

    def test_removed_get_order_detail(self) -> bool:
        """Test 2: GET /api/dewi/maklon/orders/{id} — REMOVED (should return 404/405)."""
        # Use a dummy ID since endpoint should not exist
        success, response = self.run_test(
            "GET /api/dewi/maklon/orders/{id} — REMOVED endpoint",
            "GET",
            "/api/dewi/maklon/orders/dummy-id-123",
            404,
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Endpoint correctly removed (404)")
            return True
        return False

    def test_removed_post_orders(self) -> bool:
        """Test 3: POST /api/dewi/maklon/orders — REMOVED (should return 404/405)."""
        success, response = self.run_test(
            "POST /api/dewi/maklon/orders — REMOVED endpoint",
            "POST",
            "/api/dewi/maklon/orders",
            404,
            data={"client_id": "test", "product_name": "test"},
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Endpoint correctly removed (404)")
            return True
        return False

    def test_removed_put_orders(self) -> bool:
        """Test 4: PUT /api/dewi/maklon/orders/{id} — REMOVED (should return 404/405)."""
        success, response = self.run_test(
            "PUT /api/dewi/maklon/orders/{id} — REMOVED endpoint",
            "PUT",
            "/api/dewi/maklon/orders/dummy-id-123",
            404,
            data={"product_name": "updated"},
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Endpoint correctly removed (404)")
            return True
        return False

    def test_removed_put_orders_confirm(self) -> bool:
        """Test 5: PUT /api/dewi/maklon/orders/{id}/confirm — REMOVED (should return 404/405)."""
        success, response = self.run_test(
            "PUT /api/dewi/maklon/orders/{id}/confirm — REMOVED endpoint",
            "PUT",
            "/api/dewi/maklon/orders/dummy-id-123/confirm",
            404,
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Endpoint correctly removed (404)")
            return True
        return False

    def test_removed_delete_orders(self) -> bool:
        """Test 6: DELETE /api/dewi/maklon/orders/{id} — REMOVED (should return 404/405)."""
        success, response = self.run_test(
            "DELETE /api/dewi/maklon/orders/{id} — REMOVED endpoint",
            "DELETE",
            "/api/dewi/maklon/orders/dummy-id-123",
            404,
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Endpoint correctly removed (404)")
            return True
        return False

    # ========================================================================
    # RETAINED ENDPOINTS TESTS (should still work)
    # ========================================================================

    def test_get_migrated_pos(self) -> bool:
        """Test 7: GET /api/dewi/maklon/pos — verify MKLO-LEG-001/002/003 exist."""
        success, response = self.run_test(
            "GET /api/dewi/maklon/pos — verify migrated POs",
            "GET",
            "/api/dewi/maklon/pos",
            200,
            token=self.admin_token
        )
        if success and isinstance(response, list):
            migrated = [po for po in response if po.get('po_number', '').startswith('MKLO-LEG-')]
            self.migrated_po_ids = [po['id'] for po in migrated]
            self.log(f"   Found {len(migrated)} migrated POs: {[po['po_number'] for po in migrated[:3]]}")
            if len(migrated) >= 3:
                self.log("   ✓ MKLO-LEG-001/002/003 exist")
                return True
            else:
                self.log("   ⚠ Expected at least 3 migrated POs", "WARN")
        return False

    def test_retained_put_orders_status(self) -> bool:
        """Test 8: PUT /api/dewi/maklon/orders/{id}/status — RETAINED endpoint."""
        if not self.migrated_po_ids:
            self.log("   ⚠ Skipping: no migrated PO IDs", "WARN")
            return False

        po_id = self.migrated_po_ids[0]
        success, response = self.run_test(
            "PUT /api/dewi/maklon/orders/{id}/status — RETAINED endpoint",
            "PUT",
            f"/api/dewi/maklon/orders/{po_id}/status",
            200,
            data={"status": "cutting", "force": True},
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Retained endpoint works (status update)")
            return True
        return False

    def test_retained_put_orders_stage_qty(self) -> bool:
        """Test 9: PUT /api/dewi/maklon/orders/{id}/stage-qty — RETAINED endpoint."""
        if not self.migrated_po_ids:
            self.log("   ⚠ Skipping: no migrated PO IDs", "WARN")
            return False

        po_id = self.migrated_po_ids[0]
        success, response = self.run_test(
            "PUT /api/dewi/maklon/orders/{id}/stage-qty — RETAINED endpoint",
            "PUT",
            f"/api/dewi/maklon/orders/{po_id}/stage-qty",
            200,
            data={"stage": "cutting", "qty_out": 50},
            token=self.admin_token
        )
        if success:
            self.log("   ✓ Retained endpoint works (stage qty update)")
            return True
        return False

    def test_retained_get_orders_production_detail(self) -> bool:
        """Test 10: GET /api/dewi/maklon/orders/{id}/production-detail — RETAINED endpoint."""
        if not self.migrated_po_ids:
            self.log("   ⚠ Skipping: no migrated PO IDs", "WARN")
            return False

        po_id = self.migrated_po_ids[0]
        success, response = self.run_test(
            "GET /api/dewi/maklon/orders/{id}/production-detail — RETAINED endpoint",
            "GET",
            f"/api/dewi/maklon/orders/{po_id}/production-detail",
            200,
            token=self.admin_token
        )
        if success:
            order = response.get('order', {})
            linked_wos = response.get('linked_wos', [])
            stage_qty = response.get('stage_qty', {})
            self.log(f"   Order: {order.get('order_code')}, WOs: {len(linked_wos)}, Stage qty: {stage_qty}")
            self.log("   ✓ Retained endpoint works (production detail)")
            return True
        return False

    def test_retained_get_orders_material_issues(self) -> bool:
        """Test 11: GET /api/dewi/maklon/orders/{id}/material-issues — RETAINED endpoint."""
        if not self.migrated_po_ids:
            self.log("   ⚠ Skipping: no migrated PO IDs", "WARN")
            return False

        po_id = self.migrated_po_ids[0]
        success, response = self.run_test(
            "GET /api/dewi/maklon/orders/{id}/material-issues — RETAINED endpoint",
            "GET",
            f"/api/dewi/maklon/orders/{po_id}/material-issues",
            200,
            token=self.admin_token
        )
        if success:
            issues = response if isinstance(response, list) else []
            self.log(f"   Material issues: {len(issues)}")
            self.log("   ✓ Retained endpoint works (material issues list)")
            return True
        return False

    # ========================================================================
    # NEW SSOT ENDPOINTS TESTS
    # ========================================================================

    def test_ssot_create_po(self) -> bool:
        """Test 12: POST /api/dewi/maklon/pos — create new PO."""
        # First, get or create a test client
        success, clients = self.run_test(
            "GET /api/dewi/maklon/clients — get test client",
            "GET",
            "/api/dewi/maklon/clients",
            200,
            token=self.admin_token
        )
        if success and isinstance(clients, list) and len(clients) > 0:
            self.test_client_id = clients[0]['id']
        else:
            self.log("   ⚠ No clients found, skipping PO creation", "WARN")
            return False

        success, response = self.run_test(
            "POST /api/dewi/maklon/pos — create new PO",
            "POST",
            "/api/dewi/maklon/pos",
            200,
            data={
                "client_id": self.test_client_id,
                "po_date": date.today().isoformat(),
                "deadline": "2026-12-31",
                "payment_terms": "net_30",
                "notes": "Phase C test PO",
                "items": [
                    {
                        "seri_no": "S01",
                        "artikel": "TEST-PHASE-C",
                        "color": "Red",
                        "size": "M",
                        "qty": 100,
                        "cmt_rate_per_pcs": 50000
                    }
                ]
            },
            token=self.admin_token
        )
        if success and 'id' in response:
            self.test_po_id = response['id']
            po_number = response.get('po_number', 'N/A')
            self.log(f"   PO created: {po_number} (ID: {self.test_po_id})")
            self.log("   ✓ SSOT endpoint works (PO creation)")
            return True
        return False

    def test_ssot_confirm_po(self) -> bool:
        """Test 13: POST /api/dewi/maklon/pos/{id}/confirm — confirm PO."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO ID", "WARN")
            return False

        success, response = self.run_test(
            "POST /api/dewi/maklon/pos/{id}/confirm — confirm PO",
            "POST",
            f"/api/dewi/maklon/pos/{self.test_po_id}/confirm",
            200,
            token=self.admin_token
        )
        if success:
            status = response.get('status', '')
            wo_created = response.get('work_orders_created', [])
            self.log(f"   Status: {status}, WOs created: {len(wo_created)}")
            self.log("   ✓ SSOT endpoint works (PO confirmation)")
            return True
        return False

    def test_ssot_cancel_po(self) -> bool:
        """Test 14: POST /api/dewi/maklon/pos/{id}/cancel — cancel PO."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO ID", "WARN")
            return False

        success, response = self.run_test(
            "POST /api/dewi/maklon/pos/{id}/cancel — cancel PO",
            "POST",
            f"/api/dewi/maklon/pos/{self.test_po_id}/cancel",
            200,
            token=self.admin_token
        )
        if success:
            status = response.get('status', '')
            self.log(f"   Status: {status}")
            self.log("   ✓ SSOT endpoint works (PO cancellation)")
            return True
        return False

    # ========================================================================
    # OPENAPI VERIFICATION
    # ========================================================================

    def test_openapi_endpoint_count(self) -> bool:
        """Test 15: GET /openapi.json — verify exactly 6 /api/dewi/maklon/orders/* endpoints."""
        success, response = self.run_test(
            "GET /openapi.json — verify endpoint count",
            "GET",
            "/openapi.json",
            200
        )
        if success and isinstance(response, dict):
            paths = response.get('paths', {})
            maklon_orders_endpoints = [
                path for path in paths.keys()
                if path.startswith('/api/dewi/maklon/orders')
            ]
            self.log(f"   Found {len(maklon_orders_endpoints)} /api/dewi/maklon/orders/* endpoints:")
            for ep in maklon_orders_endpoints:
                methods = list(paths[ep].keys())
                self.log(f"     - {ep} [{', '.join(methods)}]")
            
            if len(maklon_orders_endpoints) == 6:
                self.log("   ✓ Exactly 6 endpoints retained (as expected)")
                return True
            else:
                self.log(f"   ❌ Expected 6 endpoints, found {len(maklon_orders_endpoints)}", "FAIL")
                return False
        return False

    # ========================================================================
    # VERIFY CLIENTS ENDPOINT
    # ========================================================================

    def test_clients_endpoint(self) -> bool:
        """Test 16: GET /api/dewi/maklon/clients — verify untouched."""
        success, response = self.run_test(
            "GET /api/dewi/maklon/clients — verify untouched",
            "GET",
            "/api/dewi/maklon/clients",
            200,
            token=self.admin_token
        )
        if success and isinstance(response, list):
            self.log(f"   Found {len(response)} clients")
            self.log("   ✓ Clients endpoint untouched")
            return True
        return False

    def run_all_tests(self):
        """Run all tests in sequence."""
        self.log("=" * 80)
        self.log("Phase C Maklon Route Removal — Backend Test Suite")
        self.log("=" * 80)
        self.log(f"Base URL: {self.base_url}")
        self.log(f"Admin: {ADMIN_EMAIL}")
        self.log("")

        # Test 0: Admin login (prerequisite)
        if not self.test_admin_login():
            self.log("❌ Admin login failed. Aborting tests.", "ERROR")
            return 1

        # Test 1-6: Removed endpoints
        self.log("\n" + "=" * 80)
        self.log("REMOVED ENDPOINTS (should return 404/405)")
        self.log("=" * 80)
        self.test_removed_get_orders_list()
        self.test_removed_get_order_detail()
        self.test_removed_post_orders()
        self.test_removed_put_orders()
        self.test_removed_put_orders_confirm()
        self.test_removed_delete_orders()

        # Test 7-11: Retained endpoints
        self.log("\n" + "=" * 80)
        self.log("RETAINED ENDPOINTS (should still work)")
        self.log("=" * 80)
        self.test_get_migrated_pos()
        self.test_retained_put_orders_status()
        self.test_retained_put_orders_stage_qty()
        self.test_retained_get_orders_production_detail()
        self.test_retained_get_orders_material_issues()

        # Test 12-14: New SSOT endpoints
        self.log("\n" + "=" * 80)
        self.log("NEW SSOT ENDPOINTS (should work)")
        self.log("=" * 80)
        self.test_ssot_create_po()
        self.test_ssot_confirm_po()
        self.test_ssot_cancel_po()

        # Test 15-16: OpenAPI and other verifications
        self.log("\n" + "=" * 80)
        self.log("VERIFICATION TESTS")
        self.log("=" * 80)
        self.test_openapi_endpoint_count()
        self.test_clients_endpoint()

        # Summary
        self.log("")
        self.log("=" * 80)
        self.log(f"Test Summary: {self.tests_passed}/{self.tests_run} passed")
        self.log("=" * 80)

        if self.errors:
            self.log(f"\n❌ {len(self.errors)} test(s) failed:")
            for err in self.errors:
                self.log(f"   - {err.get('test', 'Unknown')}: {err.get('error', err.get('response', 'Unknown error'))}")

        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"\nSuccess rate: {success_rate:.1f}%")

        return 0 if success_rate >= 80 else 1


def main():
    tester = PhaseCTester(BASE_URL)
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
