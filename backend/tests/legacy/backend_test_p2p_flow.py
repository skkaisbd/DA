"""
Backend Test Suite: P1.C P2P Flow Completion — Create GR from PO
=================================================================
Tests the new P2P flow endpoints and anti over-receive validation.

Test Coverage:
- GET /api/rahaza/purchase-orders/{po_id}/remaining (PO not found, draft PO, approved PO)
- POST /api/rahaza/purchase-orders/{po_id}/create-gr (various scenarios)
- GET /api/rahaza/purchase-orders/{po_id}/grs (audit trail)
- PUT /api/wms/legacy/receiving/{receipt_id} with over-receive validation
- End-to-end P2P flow (create PO → approve → create GR → receive → verify stock)
- Status transition from partially_received → fully_received

Public endpoint: https://da37-cmt-bridge.preview.emergentagent.com
Admin credentials: admin@garment.com / Admin@123
"""

import requests
import sys
import uuid
from datetime import datetime, date
from typing import Optional, Dict, Any, List

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


class P2PFlowTester:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.admin_token: Optional[str] = None
        self.tests_run = 0
        self.tests_passed = 0
        self.errors: List[Dict] = []
        
        # Test data IDs
        self.test_run_id = uuid.uuid4().hex[:6].upper()
        self.material_ids: List[str] = []
        self.test_po_id: Optional[str] = None
        self.test_po_number: Optional[str] = None
        self.gr_ids: List[str] = []

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

    def setup_test_materials(self) -> bool:
        """Setup: Create 3 test materials for PO."""
        self.log("Setting up test materials...")
        
        # Use direct MongoDB insert via API (or create via materials endpoint if available)
        # For now, we'll create materials via the materials endpoint
        materials = [
            {"code": f"TEST-P2P-{self.test_run_id}-Y01", "name": f"Test Yarn {self.test_run_id}", 
             "type": "yarn", "unit": "kg", "min_stock": 0, "active": True},
            {"code": f"TEST-P2P-{self.test_run_id}-A01", "name": f"Test Button {self.test_run_id}", 
             "type": "accessory", "unit": "pcs", "min_stock": 0, "active": True},
            {"code": f"TEST-P2P-{self.test_run_id}-A02", "name": f"Test Thread {self.test_run_id}", 
             "type": "accessory", "unit": "rol", "min_stock": 0, "active": True},
        ]
        
        for mat in materials:
            success, response = self.run_test(
                f"Create material {mat['code']}",
                "POST",
                "/api/rahaza/materials",
                200,
                data=mat,
                token=self.admin_token
            )
            if success and 'id' in response:
                self.material_ids.append(response['id'])
                self.log(f"   Material created: {response['id']}")
            else:
                self.log(f"   ⚠ Failed to create material {mat['code']}", "WARN")
                return False
        
        return len(self.material_ids) == 3

    def test_get_remaining_po_not_found(self) -> bool:
        """Test 1: GET /remaining with non-existent PO → 404."""
        fake_po_id = str(uuid.uuid4())
        success, response = self.run_test(
            "GET /remaining with non-existent PO (expect 404)",
            "GET",
            f"/api/rahaza/purchase-orders/{fake_po_id}/remaining",
            404,
            token=self.admin_token
        )
        return success

    def test_create_draft_po(self) -> bool:
        """Test 2: Create draft PO with 3 items."""
        if len(self.material_ids) != 3:
            self.log("   ⚠ Skipping: materials not set up", "WARN")
            return False

        po_payload = {
            "vendor_name": f"Test Vendor P2P {self.test_run_id}",
            "vendor_contact": "0812-TEST",
            "po_date": date.today().isoformat(),
            "expected_delivery_date": "2026-12-31",
            "notes": f"Test PO for P2P flow {self.test_run_id}",
            "items": [
                {"material_id": self.material_ids[0], "qty_ordered": 100, "unit_cost": 50000},
                {"material_id": self.material_ids[1], "qty_ordered": 500, "unit_cost": 1000},
                {"material_id": self.material_ids[2], "qty_ordered": 20, "unit_cost": 25000},
            ],
        }
        
        success, response = self.run_test(
            "Create draft PO with 3 items",
            "POST",
            "/api/rahaza/purchase-orders",
            200,
            data=po_payload,
            token=self.admin_token
        )
        
        if success and 'id' in response:
            self.test_po_id = response['id']
            self.test_po_number = response.get('po_number', 'N/A')
            status = response.get('status', '')
            self.log(f"   PO created: {self.test_po_number} (ID: {self.test_po_id}, status: {status})")
            return status == 'draft'
        return False

    def test_get_remaining_draft_po(self) -> bool:
        """Test 3: GET /remaining for draft PO → 200 with full remaining."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "GET /remaining for draft PO (expect 200 with full remaining)",
            "GET",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/remaining",
            200,
            token=self.admin_token
        )
        
        if success:
            total_remaining = response.get('total_remaining', 0)
            items_remaining = response.get('items_remaining', [])
            self.log(f"   Total remaining: {total_remaining}, Items: {len(items_remaining)}")
            # Expected: 100 + 500 + 20 = 620
            if total_remaining == 620 and len(items_remaining) == 3:
                self.log("   ✓ Draft PO returns full remaining qty")
                return True
            else:
                self.log(f"   ⚠ Expected total_remaining=620, got {total_remaining}", "WARN")
                return False
        return False

    def test_create_gr_from_draft_po_fail(self) -> bool:
        """Test 4: POST /create-gr from draft PO → 400 (only approved/partially_received allowed)."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "POST /create-gr from draft PO (expect 400)",
            "POST",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/create-gr",
            400,
            data={"notes": f"Test GR from draft PO {self.test_run_id}"},
            token=self.admin_token
        )
        return success

    def test_submit_and_approve_po(self) -> bool:
        """Test 5: Submit and approve PO."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        # Submit
        success, response = self.run_test(
            "Submit PO for approval",
            "POST",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/submit",
            200,
            token=self.admin_token
        )
        if not success:
            return False

        # Approve
        success, response = self.run_test(
            "Approve PO",
            "POST",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/approve",
            200,
            token=self.admin_token
        )
        
        if success:
            status = response.get('status', '')
            self.log(f"   PO status: {status}")
            return status == 'approved'
        return False

    def test_get_remaining_approved_po(self) -> bool:
        """Test 6: GET /remaining for approved PO → 200 with full remaining."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "GET /remaining for approved PO (expect 200 with full remaining)",
            "GET",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/remaining",
            200,
            token=self.admin_token
        )
        
        if success:
            total_remaining = response.get('total_remaining', 0)
            items_remaining = response.get('items_remaining', [])
            self.log(f"   Total remaining: {total_remaining}, Items: {len(items_remaining)}")
            if total_remaining == 620 and len(items_remaining) == 3:
                self.log("   ✓ Approved PO returns full remaining qty")
                return True
            else:
                self.log(f"   ⚠ Expected total_remaining=620, got {total_remaining}", "WARN")
                return False
        return False

    def test_create_gr_from_approved_po(self) -> bool:
        """Test 7: POST /create-gr from approved PO → 200 with draft GR."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "POST /create-gr from approved PO (expect 200)",
            "POST",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/create-gr",
            200,
            data={"notes": f"Test GR#1 from approved PO {self.test_run_id}"},
            token=self.admin_token
        )
        
        if success:
            gr_id = response.get('id')
            gr_number = response.get('receipt_number', 'N/A')
            status = response.get('status', '')
            po_id = response.get('po_id', '')
            po_number = response.get('po_number', '')
            enforce_po_qty = response.get('enforce_po_qty', False)
            items = response.get('items', [])
            
            self.log(f"   GR created: {gr_number} (ID: {gr_id})")
            self.log(f"   Status: {status}, PO: {po_number}, enforce_po_qty: {enforce_po_qty}")
            self.log(f"   Items: {len(items)}")
            
            if gr_id:
                self.gr_ids.append(gr_id)
            
            # Verify expectations
            checks = [
                (status == 'draft', f"status=draft (got {status})"),
                (po_id == self.test_po_id, f"po_id matches (got {po_id})"),
                (po_number == self.test_po_number, f"po_number matches (got {po_number})"),
                (enforce_po_qty is True, f"enforce_po_qty=True (got {enforce_po_qty})"),
                (len(items) == 3, f"3 items (got {len(items)})"),
            ]
            
            all_passed = True
            for check, desc in checks:
                if not check:
                    self.log(f"   ⚠ Check failed: {desc}", "WARN")
                    all_passed = False
            
            if all_passed:
                self.log("   ✓ GR created with correct attributes")
            
            return all_passed
        return False

    def test_receive_partial_gr(self) -> bool:
        """Test 8: Receive half of each line in GR1 → PO status=partially_received."""
        if not self.gr_ids:
            self.log("   ⚠ Skipping: no GR created", "WARN")
            return False

        gr_id = self.gr_ids[0]
        
        # Get GR details first
        success, gr = self.run_test(
            "Get GR details before receiving",
            "GET",
            f"/api/wms/legacy/receiving/{gr_id}",
            200,
            token=self.admin_token
        )
        
        if not success:
            return False
        
        # Update items with half received
        items = gr.get('items', [])
        items[0]['received_qty'] = 50   # 100 -> 50
        items[1]['received_qty'] = 250  # 500 -> 250
        items[2]['received_qty'] = 10   # 20 -> 10
        
        success, response = self.run_test(
            "Receive partial qty (half of each line)",
            "PUT",
            f"/api/wms/legacy/receiving/{gr_id}",
            200,
            data={"status": "received", "items": items},
            token=self.admin_token
        )
        
        if success:
            status = response.get('status', '')
            self.log(f"   GR status: {status}")
            return status == 'received'
        return False

    def test_verify_po_partially_received(self) -> bool:
        """Test 9: Verify PO status=partially_received and qty_received updated."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "Verify PO status=partially_received",
            "GET",
            f"/api/rahaza/purchase-orders/{self.test_po_id}",
            200,
            token=self.admin_token
        )
        
        if success:
            status = response.get('status', '')
            items = response.get('items', [])
            
            self.log(f"   PO status: {status}")
            
            # Verify qty_received per item
            expected_received = [50, 250, 10]
            all_correct = True
            for i, item in enumerate(items):
                qty_received = item.get('qty_received', 0)
                expected = expected_received[i]
                self.log(f"   Item {i+1}: qty_received={qty_received} (expected {expected})")
                if qty_received != expected:
                    all_correct = False
            
            if status == 'partially_received' and all_correct:
                self.log("   ✓ PO status and qty_received correct")
                return True
            else:
                self.log("   ⚠ Expected status=partially_received with correct qty_received", "WARN")
                return False
        return False

    def test_create_gr2_from_partially_received_po(self) -> bool:
        """Test 10: POST /create-gr from partially_received PO → 200 with remaining qty."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "POST /create-gr from partially_received PO (expect remaining qty)",
            "POST",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/create-gr",
            200,
            data={"notes": f"Test GR#2 from partially_received PO {self.test_run_id}"},
            token=self.admin_token
        )
        
        if success:
            gr_id = response.get('id')
            gr_number = response.get('receipt_number', 'N/A')
            items = response.get('items', [])
            
            self.log(f"   GR2 created: {gr_number} (ID: {gr_id})")
            
            if gr_id:
                self.gr_ids.append(gr_id)
            
            # Verify expected_qty = remaining (50, 250, 10)
            expected_qtys = [50, 250, 10]
            all_correct = True
            for i, item in enumerate(items):
                expected_qty = item.get('expected_qty', 0)
                expected = expected_qtys[i]
                self.log(f"   Item {i+1}: expected_qty={expected_qty} (expected {expected})")
                if expected_qty != expected:
                    all_correct = False
            
            if all_correct:
                self.log("   ✓ GR2 expected_qty = remaining qty")
                return True
            else:
                self.log("   ⚠ GR2 expected_qty incorrect", "WARN")
                return False
        return False

    def test_over_receive_validation(self) -> bool:
        """Test 11: Try to over-receive in GR2 → 400 with error message."""
        if len(self.gr_ids) < 2:
            self.log("   ⚠ Skipping: GR2 not created", "WARN")
            return False

        gr2_id = self.gr_ids[1]
        
        # Get GR2 details
        success, gr2 = self.run_test(
            "Get GR2 details before over-receive attempt",
            "GET",
            f"/api/wms/legacy/receiving/{gr2_id}",
            200,
            token=self.admin_token
        )
        
        if not success:
            return False
        
        # Try to over-receive (way more than allowed)
        items = gr2.get('items', [])
        items[0]['received_qty'] = 999  # Way more than remaining 50
        items[1]['received_qty'] = 250  # OK
        items[2]['received_qty'] = 10   # OK
        
        success, response = self.run_test(
            "Try to over-receive (expect 400)",
            "PUT",
            f"/api/wms/legacy/receiving/{gr2_id}",
            400,
            data={"status": "received", "items": items},
            token=self.admin_token
        )
        
        # Note: success here means we got the expected 400 status
        return success

    def test_normal_receive_gr2(self) -> bool:
        """Test 12: Normal receive of remaining qty in GR2 → PO status=fully_received."""
        if len(self.gr_ids) < 2:
            self.log("   ⚠ Skipping: GR2 not created", "WARN")
            return False

        gr2_id = self.gr_ids[1]
        
        # Get GR2 details
        success, gr2 = self.run_test(
            "Get GR2 details before normal receive",
            "GET",
            f"/api/wms/legacy/receiving/{gr2_id}",
            200,
            token=self.admin_token
        )
        
        if not success:
            return False
        
        # Normal receive (remaining qty)
        items = gr2.get('items', [])
        items[0]['received_qty'] = 50
        items[1]['received_qty'] = 250
        items[2]['received_qty'] = 10
        
        success, response = self.run_test(
            "Normal receive of remaining qty",
            "PUT",
            f"/api/wms/legacy/receiving/{gr2_id}",
            200,
            data={"status": "received", "items": items},
            token=self.admin_token
        )
        
        if success:
            status = response.get('status', '')
            self.log(f"   GR2 status: {status}")
            return status == 'received'
        return False

    def test_verify_po_fully_received(self) -> bool:
        """Test 13: Verify PO status=fully_received."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "Verify PO status=fully_received",
            "GET",
            f"/api/rahaza/purchase-orders/{self.test_po_id}",
            200,
            token=self.admin_token
        )
        
        if success:
            status = response.get('status', '')
            items = response.get('items', [])
            
            self.log(f"   PO status: {status}")
            
            # Verify all qty_received = qty_ordered
            all_fully_received = True
            for i, item in enumerate(items):
                qty_ordered = item.get('qty_ordered', 0)
                qty_received = item.get('qty_received', 0)
                self.log(f"   Item {i+1}: qty_received={qty_received}, qty_ordered={qty_ordered}")
                if qty_received != qty_ordered:
                    all_fully_received = False
            
            if status == 'fully_received' and all_fully_received:
                self.log("   ✓ PO fully received")
                return True
            else:
                self.log("   ⚠ Expected status=fully_received with all qty received", "WARN")
                return False
        return False

    def test_create_gr_from_fully_received_po_fail(self) -> bool:
        """Test 14: POST /create-gr from fully_received PO → 400."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "POST /create-gr from fully_received PO (expect 400)",
            "POST",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/create-gr",
            400,
            data={"notes": f"Test GR#3 should fail {self.test_run_id}"},
            token=self.admin_token
        )
        return success

    def test_get_grs_audit_trail(self) -> bool:
        """Test 15: GET /grs → audit trail (should return 2 GRs)."""
        if not self.test_po_id:
            self.log("   ⚠ Skipping: no test PO", "WARN")
            return False

        success, response = self.run_test(
            "GET /grs audit trail (expect 2 GRs)",
            "GET",
            f"/api/rahaza/purchase-orders/{self.test_po_id}/grs",
            200,
            token=self.admin_token
        )
        
        if success and isinstance(response, list):
            self.log(f"   GRs found: {len(response)}")
            
            for i, gr in enumerate(response):
                receipt_number = gr.get('receipt_number', 'N/A')
                status = gr.get('status', 'N/A')
                items_count = gr.get('items_count', 0)
                total_expected = gr.get('total_expected', 0)
                total_received = gr.get('total_received', 0)
                total_net = gr.get('total_net', 0)
                self.log(f"   GR {i+1}: {receipt_number}, status={status}, items={items_count}, "
                        f"expected={total_expected}, received={total_received}, net={total_net}")
            
            if len(response) == 2:
                self.log("   ✓ Audit trail returns 2 GRs")
                return True
            else:
                self.log(f"   ⚠ Expected 2 GRs, got {len(response)}", "WARN")
                return False
        return False

    def cleanup_test_data(self):
        """Cleanup: Delete test PO, GRs, and materials."""
        self.log("Cleaning up test data...")
        
        # Delete GRs
        for gr_id in self.gr_ids:
            try:
                requests.delete(
                    f"{self.base_url}/api/wms/legacy/receiving/{gr_id}",
                    headers={'Authorization': f'Bearer {self.admin_token}'},
                    timeout=10
                )
                self.log(f"   Deleted GR: {gr_id}")
            except Exception as e:
                self.log(f"   ⚠ Failed to delete GR {gr_id}: {e}", "WARN")
        
        # Delete PO
        if self.test_po_id:
            try:
                requests.delete(
                    f"{self.base_url}/api/rahaza/purchase-orders/{self.test_po_id}",
                    headers={'Authorization': f'Bearer {self.admin_token}'},
                    timeout=10
                )
                self.log(f"   Deleted PO: {self.test_po_id}")
            except Exception as e:
                self.log(f"   ⚠ Failed to delete PO {self.test_po_id}: {e}", "WARN")
        
        # Delete materials
        for mat_id in self.material_ids:
            try:
                requests.delete(
                    f"{self.base_url}/api/rahaza/materials/{mat_id}",
                    headers={'Authorization': f'Bearer {self.admin_token}'},
                    timeout=10
                )
                self.log(f"   Deleted material: {mat_id}")
            except Exception as e:
                self.log(f"   ⚠ Failed to delete material {mat_id}: {e}", "WARN")

    def run_all_tests(self):
        """Run all tests in sequence."""
        self.log("=" * 80)
        self.log("P1.C P2P Flow Completion — Backend Test Suite")
        self.log("=" * 80)
        self.log(f"Base URL: {self.base_url}")
        self.log(f"Admin: {ADMIN_EMAIL}")
        self.log(f"Test Run ID: {self.test_run_id}")
        self.log("")

        # Test 0: Admin login (prerequisite)
        if not self.test_admin_login():
            self.log("❌ Admin login failed. Aborting tests.", "ERROR")
            return 1

        # Setup test materials
        if not self.setup_test_materials():
            self.log("❌ Failed to setup test materials. Aborting tests.", "ERROR")
            return 1

        # Run all tests
        self.test_get_remaining_po_not_found()
        self.test_create_draft_po()
        self.test_get_remaining_draft_po()
        self.test_create_gr_from_draft_po_fail()
        self.test_submit_and_approve_po()
        self.test_get_remaining_approved_po()
        self.test_create_gr_from_approved_po()
        self.test_receive_partial_gr()
        self.test_verify_po_partially_received()
        self.test_create_gr2_from_partially_received_po()
        self.test_over_receive_validation()
        self.test_normal_receive_gr2()
        self.test_verify_po_fully_received()
        self.test_create_gr_from_fully_received_po_fail()
        self.test_get_grs_audit_trail()

        # Cleanup
        self.cleanup_test_data()

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

        return 0 if success_rate >= 90 else 1


def main():
    tester = P2PFlowTester(BASE_URL)
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
