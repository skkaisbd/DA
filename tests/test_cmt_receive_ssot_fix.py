"""
Backend Test: CMT Receive SSOT Fix Verification
Tests the fix for BUG-1 (orphan FG-{sku} → real FG master UUID linkage)

Bug Context:
- User reported: "Terima FG dari CMT" module shows list but no action works
- Root cause: approve endpoint posted FG stock using orphan 'FG-{sku}' id
  instead of canonical FG master UUID in rahaza_materials
- Fix: approve now calls _ensure_fg_for_cmt_line() to resolve real FG master

Test Flow:
1. GET /api/prod/cmt-receipts?status=Draft → verify CMT-RCV-00001 exists
2. GET /api/prod/cmt-receipts/{id} → get detail with lines
3. PUT /api/prod/cmt-receipts/{id}/lines/{line_id} → set qty_actual=100 for both lines
4. POST /api/prod/cmt-receipts/{id}/submit → status Submitted
5. POST /api/prod/cmt-receipts/{id}/approve → status Approved
6. CRITICAL VERIFICATION: FG stock posted to REAL master (NOT orphan 'FG-{sku}')
   a) rahaza_materials doc exists with type='fg', code='123-NVY-S' (UUID id)
   b) rahaza_material_stock row exists with material_id=that UUID (NOT 'FG-123-NVY-S')
   c) FG queryable via GET /api/rahaza/materials?type=fg
   d) NO orphan 'FG-' string prefix material_id in rahaza_material_stock
"""
import requests
import sys
import json
from typing import Dict, Any

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Test data
RECEIPT_CODE = "CMT-RCV-00001"
TEST_SKUS = ["123-NVY-S", "123-NVY-M"]
QTY_PER_LINE = 100


class CMTReceiveSSoTTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        self.receipt_id = None
        self.line_ids = {}
        self.fg_material_ids = {}  # {sku: material_id}

    def log(self, msg: str, level: str = "INFO"):
        """Log test messages"""
        prefix = {"INFO": "ℹ️", "PASS": "✅", "FAIL": "❌", "WARN": "⚠️"}
        print(f"{prefix.get(level, 'ℹ️')} {msg}")

    def run_test(self, name: str, test_func):
        """Run a single test and track results"""
        self.tests_run += 1
        self.log(f"\n{'='*70}", "INFO")
        self.log(f"Test #{self.tests_run}: {name}", "INFO")
        self.log(f"{'='*70}", "INFO")
        try:
            test_func()
            self.tests_passed += 1
            self.log(f"✅ PASSED: {name}", "PASS")
        except AssertionError as e:
            self.tests_failed += 1
            self.failures.append({"test": name, "error": str(e)})
            self.log(f"❌ FAILED: {name} - {e}", "FAIL")
        except Exception as e:
            self.tests_failed += 1
            self.failures.append({"test": name, "error": f"Exception: {str(e)}"})
            self.log(f"❌ ERROR: {name} - {e}", "FAIL")

    def login(self):
        """Login as admin and get JWT token"""
        self.log("Logging in as admin...", "INFO")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
            assert response.status_code == 200, f"Login failed with status {response.status_code}: {response.text}"
            data = response.json()
            assert "token" in data, f"No token in login response: {data}"
            self.token = data["token"]
            self.log(f"✅ Login successful. Token: {self.token[:20]}...", "PASS")
        except Exception as e:
            self.log(f"❌ Login failed: {e}", "FAIL")
            sys.exit(1)

    def get_headers(self, with_auth: bool = True) -> Dict[str, str]:
        """Get request headers"""
        headers = {"Content-Type": "application/json"}
        if with_auth and self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def test_1_get_draft_receipts(self):
        """Test 1: GET /api/prod/cmt-receipts?status=Draft"""
        response = requests.get(
            f"{BASE_URL}/prod/cmt-receipts?status=Draft",
            headers=self.get_headers(),
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # Find CMT-RCV-00001
        receipt = next((r for r in data if r.get("receipt_code") == RECEIPT_CODE), None)
        assert receipt is not None, f"Receipt {RECEIPT_CODE} not found in Draft receipts. Available: {[r.get('receipt_code') for r in data]}"
        
        self.receipt_id = receipt["id"]
        self.log(f"✓ Found receipt {RECEIPT_CODE} with id={self.receipt_id}", "PASS")
        self.log(f"✓ Status: {receipt.get('status')}", "PASS")
        self.log(f"✓ CMT: {receipt.get('cmt_name')}", "PASS")

    def test_2_get_receipt_detail(self):
        """Test 2: GET /api/prod/cmt-receipts/{id} - get detail with lines"""
        assert self.receipt_id, "Receipt ID not set from previous test"
        
        response = requests.get(
            f"{BASE_URL}/prod/cmt-receipts/{self.receipt_id}",
            headers=self.get_headers(),
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "lines" in data, "No 'lines' field in receipt detail"
        
        lines = data["lines"]
        assert len(lines) >= 2, f"Expected at least 2 lines, got {len(lines)}"
        
        # Verify test SKUs exist
        for sku in TEST_SKUS:
            line = next((l for l in lines if l.get("sku_code") == sku), None)
            assert line is not None, f"Line with SKU {sku} not found. Available SKUs: {[l.get('sku_code') for l in lines]}"
            
            self.line_ids[sku] = line["id"]
            qty_shipped = line.get("qty_shipped_by_cmt", 0)
            
            self.log(f"✓ Found line: SKU={sku}, id={line['id']}, qty_shipped_by_cmt={qty_shipped}", "PASS")
            assert qty_shipped == QTY_PER_LINE, f"Expected qty_shipped_by_cmt={QTY_PER_LINE}, got {qty_shipped}"

    def test_3_update_line_qty_actual(self):
        """Test 3: PUT /api/prod/cmt-receipts/{id}/lines/{line_id} - set qty_actual"""
        assert self.receipt_id, "Receipt ID not set"
        assert self.line_ids, "Line IDs not set"
        
        for sku, line_id in self.line_ids.items():
            self.log(f"Updating line {sku} (id={line_id}) with qty_actual={QTY_PER_LINE}", "INFO")
            
            response = requests.put(
                f"{BASE_URL}/prod/cmt-receipts/{self.receipt_id}/lines/{line_id}",
                headers=self.get_headers(),
                json={"qty_actual": QTY_PER_LINE, "reject_qty": 0},
                timeout=10
            )
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            data = response.json()
            assert data.get("qty_actual") == QTY_PER_LINE, f"qty_actual not updated. Got: {data.get('qty_actual')}"
            
            self.log(f"✓ Line {sku} updated: qty_actual={data.get('qty_actual')}", "PASS")

    def test_4_submit_receipt(self):
        """Test 4: POST /api/prod/cmt-receipts/{id}/submit - submit to approval"""
        assert self.receipt_id, "Receipt ID not set"
        
        response = requests.post(
            f"{BASE_URL}/prod/cmt-receipts/{self.receipt_id}/submit",
            headers=self.get_headers(),
            json={},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "Submitted", f"Expected status=Submitted, got {data.get('status')}"
        
        self.log(f"✓ Receipt submitted. Status: {data.get('status')}", "PASS")
        self.log(f"✓ Submitted by: {data.get('submitted_by')}", "PASS")

    def test_5_approve_receipt(self):
        """Test 5: POST /api/prod/cmt-receipts/{id}/approve - approve and post FG stock"""
        assert self.receipt_id, "Receipt ID not set"
        
        response = requests.post(
            f"{BASE_URL}/prod/cmt-receipts/{self.receipt_id}/approve",
            headers=self.get_headers(),
            json={},
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "Approved", f"Expected status=Approved, got {data.get('status')}"
        
        self.log(f"✓ Receipt approved. Status: {data.get('status')}", "PASS")
        self.log(f"✓ Approved by: {data.get('approved_by')}", "PASS")
        
        # Check if AP mature info is present (optional/best-effort)
        if "ap_mature" in data:
            ap = data["ap_mature"]
            self.log(f"✓ AP mature info present: {ap}", "PASS")
        else:
            self.log(f"⚠️  AP mature info not present (optional/best-effort)", "WARN")

    def test_6_verify_fg_materials_exist(self):
        """Test 6a: Verify rahaza_materials docs exist with type='fg', code==SKU (UUID id)"""
        self.log("Verifying FG materials exist in rahaza_materials...", "INFO")
        
        for sku in TEST_SKUS:
            # Try to get FG material by code
            response = requests.get(
                f"{BASE_URL}/rahaza/materials?type=fg&code={sku}",
                headers=self.get_headers(),
                timeout=10
            )
            
            # If endpoint doesn't support filtering, get all and filter
            if response.status_code == 404 or response.status_code == 400:
                self.log(f"⚠️  Endpoint doesn't support filtering, trying GET all materials", "WARN")
                response = requests.get(
                    f"{BASE_URL}/rahaza/materials",
                    headers=self.get_headers(),
                    timeout=10
                )
            
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            
            data = response.json()
            materials = data if isinstance(data, list) else data.get("materials", [])
            
            # Find FG with matching code
            fg = next((m for m in materials if m.get("type") == "fg" and m.get("code", "").upper() == sku.upper()), None)
            
            assert fg is not None, f"FG material with code={sku} not found. Available FG codes: {[m.get('code') for m in materials if m.get('type') == 'fg']}"
            
            material_id = fg.get("id")
            assert material_id, f"FG material {sku} has no 'id' field"
            
            # Verify it's a UUID (not a string like 'FG-{sku}')
            assert len(material_id) > 20, f"FG material_id looks like orphan string: {material_id}"
            assert not material_id.startswith("FG-"), f"FG material_id has 'FG-' prefix (orphan): {material_id}"
            
            self.fg_material_ids[sku] = material_id
            
            self.log(f"✓ FG material found: code={sku}, id={material_id}, name={fg.get('name')}", "PASS")

    def test_7_verify_material_stock_linked_correctly(self):
        """Test 6b: Verify rahaza_material_stock rows use REAL FG material UUID (NOT 'FG-{sku}')"""
        self.log("Verifying material stock linked to real FG masters...", "INFO")
        
        # Get all material stock
        response = requests.get(
            f"{BASE_URL}/rahaza/material-stock",
            headers=self.get_headers(),
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        stocks = data if isinstance(data, list) else data.get("stocks", [])
        
        for sku in TEST_SKUS:
            expected_material_id = self.fg_material_ids.get(sku)
            assert expected_material_id, f"FG material_id for {sku} not found from previous test"
            
            # Find stock row for this FG
            stock = next((s for s in stocks 
                         if s.get("material_id") == expected_material_id 
                         and s.get("inventory_category") == "fg_internal"
                         and s.get("ownership") == "cv_da"), None)
            
            assert stock is not None, f"Stock row for FG {sku} (material_id={expected_material_id}) not found. Available material_ids: {[s.get('material_id') for s in stocks if s.get('inventory_category') == 'fg_internal']}"
            
            qty = stock.get("qty") or stock.get("quantity") or stock.get("total_qty")
            assert qty >= QTY_PER_LINE, f"Expected qty >= {QTY_PER_LINE}, got {qty}"
            
            # Verify material_name and material_code are populated
            assert stock.get("material_code"), f"material_code not populated in stock row"
            assert stock.get("material_name"), f"material_name not populated in stock row"
            
            self.log(f"✓ Stock row found: SKU={sku}, material_id={expected_material_id}, qty={qty}", "PASS")
            self.log(f"  material_code={stock.get('material_code')}, material_name={stock.get('material_name')}", "INFO")

    def test_8_verify_no_orphan_fg_prefix(self):
        """Test 6d: Verify NO orphan 'FG-' string prefix material_id in rahaza_material_stock"""
        self.log("Verifying no orphan 'FG-' prefix material_ids...", "INFO")
        
        response = requests.get(
            f"{BASE_URL}/rahaza/material-stock",
            headers=self.get_headers(),
            timeout=10
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        stocks = data if isinstance(data, list) else data.get("stocks", [])
        
        # Check for any stock rows with material_id starting with 'FG-' for our test SKUs
        orphan_stocks = [s for s in stocks 
                        if s.get("material_id", "").startswith("FG-") 
                        and any(sku in s.get("material_id", "") for sku in TEST_SKUS)]
        
        if orphan_stocks:
            self.log(f"❌ Found orphan 'FG-' prefix material_ids: {[s.get('material_id') for s in orphan_stocks]}", "FAIL")
            assert False, f"Found {len(orphan_stocks)} orphan 'FG-' prefix material_ids (BUG NOT FIXED)"
        
        self.log(f"✓ No orphan 'FG-' prefix material_ids found for test SKUs", "PASS")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print("TEST SUMMARY")
        print("="*70)
        print(f"Total tests run: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        
        if self.failures:
            print("\n" + "="*70)
            print("FAILURES:")
            print("="*70)
            for i, failure in enumerate(self.failures, 1):
                print(f"\n{i}. {failure['test']}")
                print(f"   Error: {failure['error']}")
        
        print("\n" + "="*70)
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        print(f"Success Rate: {success_rate:.1f}%")
        print("="*70)
        
        return 0 if self.tests_failed == 0 else 1


def main():
    tester = CMTReceiveSSoTTester()
    
    # Login
    tester.login()
    
    # Run tests in order
    tester.run_test("1. GET Draft Receipts", tester.test_1_get_draft_receipts)
    tester.run_test("2. GET Receipt Detail with Lines", tester.test_2_get_receipt_detail)
    tester.run_test("3. Update Line qty_actual", tester.test_3_update_line_qty_actual)
    tester.run_test("4. Submit Receipt", tester.test_4_submit_receipt)
    tester.run_test("5. Approve Receipt (FG Stock Posting)", tester.test_5_approve_receipt)
    tester.run_test("6a. Verify FG Materials Exist (UUID, NOT 'FG-' prefix)", tester.test_6_verify_fg_materials_exist)
    tester.run_test("6b. Verify Material Stock Linked to Real FG UUID", tester.test_7_verify_material_stock_linked_correctly)
    tester.run_test("6d. Verify NO Orphan 'FG-' Prefix", tester.test_8_verify_no_orphan_fg_prefix)
    
    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
