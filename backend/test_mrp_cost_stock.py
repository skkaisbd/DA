"""
Backend Testing — Material Requirements Planning (MRP) Cost & Stock Polish
Tests Fase 5 MRP feature with cost estimation and real stock integration.

Test scenarios:
1. Cost fields present with correct values for PO-INT-DEMO-1
2. Real stock (not null/n/a) for demo materials  
3. include_cost=false flag working
4. Manual mode with cost
5. Regression: validation and cross-line aggregation
"""
import requests
import sys

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Demo data constants
PO_ID = "po-int-demo-1"
PO_NUMBER = "PO-INT-DEMO-1"
MODEL_ID = "int-demo-model-1"
SIZE_L_ID = "a3539e1f-06dc-4462-b5e9-9e6958a5e8ce"

# Expected values for PO-INT-DEMO-1
EXPECTED_YRN_UNIT_COST = 20000  # YRN-DA-CTN
EXPECTED_YRN_QTY = 50  # kg
EXPECTED_YRN_SUBTOTAL = 1000000  # 50 × 20000

EXPECTED_ACC_UNIT_COST = 500  # ACC-DA-LBL
EXPECTED_ACC_QTY = 200  # pcs
EXPECTED_ACC_SUBTOTAL = 100000  # 200 × 500

EXPECTED_GRAND_TOTAL = 1100000  # 1,000,000 + 100,000

EXPECTED_YRN_STOCK = 450  # kg
EXPECTED_ACC_STOCK = 1800  # pcs


class MRPTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        
    def log(self, msg, level="INFO"):
        prefix = "✅" if level == "PASS" else "❌" if level == "FAIL" else "🔍"
        print(f"{prefix} {msg}")
    
    def test(self, name, condition, error_msg=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"PASS: {name}", "PASS")
            return True
        else:
            self.log(f"FAIL: {name} - {error_msg}", "FAIL")
            return False
    
    def login(self):
        """Login and get admin token"""
        try:
            r = requests.post(f"{BASE_URL}/auth/login", 
                            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                            timeout=10)
            if r.status_code == 200:
                self.token = r.json().get("token")
                return True
            else:
                self.log(f"Login failed: {r.status_code} - {r.text[:200]}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Login exception: {e}", "FAIL")
            return False
    
    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_po_mode_with_cost(self):
        """Test 1: PO mode with cost fields present and correct values"""
        print("\n[TEST 1] PO Mode with Cost Estimation")
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={"po_id": PO_ID},
                timeout=15
            )
            
            if not self.test("PO mode request successful", r.status_code == 200, 
                           f"Status {r.status_code}: {r.text[:200]}"):
                return False
            
            data = r.json()
            
            # Check response structure
            self.test("Response has 'source' field", "source" in data and data["source"] == "po")
            self.test("Response has 'po' metadata", "po" in data and data["po"]["po_number"] == PO_NUMBER)
            self.test("Response has 'aggregated' array", "aggregated" in data and isinstance(data["aggregated"], list))
            self.test("Response has 'totals' object", "totals" in data and isinstance(data["totals"], dict))
            
            # Check include_cost is True by default
            self.test("include_cost is True by default", data.get("include_cost") == True)
            
            aggregated = data.get("aggregated", [])
            totals = data.get("totals", {})
            
            # Should have at least 2 materials (YRN-DA-CTN and ACC-DA-LBL)
            self.test("Has aggregated materials", len(aggregated) >= 2, 
                     f"Expected >= 2 materials, got {len(aggregated)}")
            
            # Find YRN-DA-CTN and ACC-DA-LBL
            yrn_mat = None
            acc_mat = None
            for mat in aggregated:
                if mat.get("code") == "YRN-DA-CTN":
                    yrn_mat = mat
                elif mat.get("code") == "ACC-DA-LBL":
                    acc_mat = mat
            
            # Test YRN-DA-CTN cost fields
            if yrn_mat:
                self.log(f"Found YRN-DA-CTN: {yrn_mat}")
                self.test("YRN-DA-CTN has unit_cost", "unit_cost" in yrn_mat and yrn_mat["unit_cost"] is not None)
                self.test("YRN-DA-CTN unit_cost is 20000", 
                         abs(yrn_mat.get("unit_cost", 0) - EXPECTED_YRN_UNIT_COST) < 0.01,
                         f"Expected {EXPECTED_YRN_UNIT_COST}, got {yrn_mat.get('unit_cost')}")
                self.test("YRN-DA-CTN has subtotal_cost", "subtotal_cost" in yrn_mat and yrn_mat["subtotal_cost"] is not None)
                self.test("YRN-DA-CTN subtotal is 1,000,000", 
                         abs(yrn_mat.get("subtotal_cost", 0) - EXPECTED_YRN_SUBTOTAL) < 0.01,
                         f"Expected {EXPECTED_YRN_SUBTOTAL}, got {yrn_mat.get('subtotal_cost')}")
                self.test("YRN-DA-CTN cost_source is 'material'", 
                         yrn_mat.get("cost_source") == "material",
                         f"Expected 'material', got {yrn_mat.get('cost_source')}")
            else:
                self.test("YRN-DA-CTN found in aggregated", False, "Material not found")
            
            # Test ACC-DA-LBL cost fields
            if acc_mat:
                self.log(f"Found ACC-DA-LBL: {acc_mat}")
                self.test("ACC-DA-LBL has unit_cost", "unit_cost" in acc_mat and acc_mat["unit_cost"] is not None)
                self.test("ACC-DA-LBL unit_cost is 500", 
                         abs(acc_mat.get("unit_cost", 0) - EXPECTED_ACC_UNIT_COST) < 0.01,
                         f"Expected {EXPECTED_ACC_UNIT_COST}, got {acc_mat.get('unit_cost')}")
                self.test("ACC-DA-LBL has subtotal_cost", "subtotal_cost" in acc_mat and acc_mat["subtotal_cost"] is not None)
                self.test("ACC-DA-LBL subtotal is 100,000", 
                         abs(acc_mat.get("subtotal_cost", 0) - EXPECTED_ACC_SUBTOTAL) < 0.01,
                         f"Expected {EXPECTED_ACC_SUBTOTAL}, got {acc_mat.get('subtotal_cost')}")
                self.test("ACC-DA-LBL cost_source is 'material'", 
                         acc_mat.get("cost_source") == "material",
                         f"Expected 'material', got {acc_mat.get('cost_source')}")
            else:
                self.test("ACC-DA-LBL found in aggregated", False, "Material not found")
            
            # Test grand_total_cost
            self.test("Totals has grand_total_cost", "grand_total_cost" in totals)
            self.test("Grand total cost is 1,100,000", 
                     abs(totals.get("grand_total_cost", 0) - EXPECTED_GRAND_TOTAL) < 0.01,
                     f"Expected {EXPECTED_GRAND_TOTAL}, got {totals.get('grand_total_cost')}")
            
            return True
            
        except Exception as e:
            self.log(f"Test 1 exception: {e}", "FAIL")
            return False
    
    def test_real_stock(self):
        """Test 2: Real stock values (not null/n/a)"""
        print("\n[TEST 2] Real Stock Integration")
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={"po_id": PO_ID, "include_stock": True},
                timeout=15
            )
            
            if not self.test("Stock request successful", r.status_code == 200, 
                           f"Status {r.status_code}: {r.text[:200]}"):
                return False
            
            data = r.json()
            aggregated = data.get("aggregated", [])
            totals = data.get("totals", {})
            
            # Find YRN-DA-CTN and ACC-DA-LBL
            yrn_mat = None
            acc_mat = None
            for mat in aggregated:
                if mat.get("code") == "YRN-DA-CTN":
                    yrn_mat = mat
                elif mat.get("code") == "ACC-DA-LBL":
                    acc_mat = mat
            
            # Test YRN-DA-CTN stock
            if yrn_mat:
                self.log(f"YRN-DA-CTN stock: onhand={yrn_mat.get('onhand')}, available={yrn_mat.get('available')}, shortfall={yrn_mat.get('shortfall')}")
                self.test("YRN-DA-CTN has onhand (not null)", 
                         yrn_mat.get("onhand") is not None,
                         f"onhand is {yrn_mat.get('onhand')}")
                self.test("YRN-DA-CTN onhand is ~450", 
                         abs(yrn_mat.get("onhand", 0) - EXPECTED_YRN_STOCK) < 1,
                         f"Expected ~{EXPECTED_YRN_STOCK}, got {yrn_mat.get('onhand')}")
                self.test("YRN-DA-CTN has available (not null)", 
                         yrn_mat.get("available") is not None)
                self.test("YRN-DA-CTN available is ~450", 
                         abs(yrn_mat.get("available", 0) - EXPECTED_YRN_STOCK) < 1,
                         f"Expected ~{EXPECTED_YRN_STOCK}, got {yrn_mat.get('available')}")
                self.test("YRN-DA-CTN shortfall is 0", 
                         yrn_mat.get("shortfall", -1) == 0,
                         f"Expected 0, got {yrn_mat.get('shortfall')}")
            
            # Test ACC-DA-LBL stock
            if acc_mat:
                self.log(f"ACC-DA-LBL stock: onhand={acc_mat.get('onhand')}, available={acc_mat.get('available')}, shortfall={acc_mat.get('shortfall')}")
                self.test("ACC-DA-LBL has onhand (not null)", 
                         acc_mat.get("onhand") is not None,
                         f"onhand is {acc_mat.get('onhand')}")
                self.test("ACC-DA-LBL onhand is ~1800", 
                         abs(acc_mat.get("onhand", 0) - EXPECTED_ACC_STOCK) < 1,
                         f"Expected ~{EXPECTED_ACC_STOCK}, got {acc_mat.get('onhand')}")
                self.test("ACC-DA-LBL has available (not null)", 
                         acc_mat.get("available") is not None)
                self.test("ACC-DA-LBL available is ~1800", 
                         abs(acc_mat.get("available", 0) - EXPECTED_ACC_STOCK) < 1,
                         f"Expected ~{EXPECTED_ACC_STOCK}, got {acc_mat.get('available')}")
                self.test("ACC-DA-LBL shortfall is 0", 
                         acc_mat.get("shortfall", -1) == 0,
                         f"Expected 0, got {acc_mat.get('shortfall')}")
            
            # Test total_shortfall_lines
            self.test("total_shortfall_lines is 0", 
                     totals.get("total_shortfall_lines", -1) == 0,
                     f"Expected 0, got {totals.get('total_shortfall_lines')}")
            
            return True
            
        except Exception as e:
            self.log(f"Test 2 exception: {e}", "FAIL")
            return False
    
    def test_include_cost_false(self):
        """Test 3: include_cost=false flag"""
        print("\n[TEST 3] include_cost=false Flag")
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={"po_id": PO_ID, "include_cost": False},
                timeout=15
            )
            
            if not self.test("include_cost=false request successful", r.status_code == 200, 
                           f"Status {r.status_code}: {r.text[:200]}"):
                return False
            
            data = r.json()
            aggregated = data.get("aggregated", [])
            totals = data.get("totals", {})
            
            # Check include_cost is False
            self.test("include_cost is False", data.get("include_cost") == False)
            
            # Check that cost fields are null/absent or 0
            if len(aggregated) > 0:
                mat = aggregated[0]
                self.test("Material unit_cost is null or absent", 
                         mat.get("unit_cost") is None or "unit_cost" not in mat,
                         f"unit_cost should be null/absent, got {mat.get('unit_cost')}")
            
            # Check grand_total_cost is 0 or absent
            self.test("grand_total_cost is 0 or absent", 
                     totals.get("grand_total_cost", 0) == 0,
                     f"Expected 0, got {totals.get('grand_total_cost')}")
            
            # Should not error
            self.test("No error with include_cost=false", True)
            
            return True
            
        except Exception as e:
            self.log(f"Test 3 exception: {e}", "FAIL")
            return False
    
    def test_manual_mode_with_cost(self):
        """Test 4: Manual mode with cost"""
        print("\n[TEST 4] Manual Mode with Cost")
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={
                    "lines": [
                        {
                            "model_id": MODEL_ID,
                            "size_id": SIZE_L_ID,
                            "qty_pcs": 100
                        }
                    ]
                },
                timeout=15
            )
            
            if not self.test("Manual mode request successful", r.status_code == 200, 
                           f"Status {r.status_code}: {r.text[:200]}"):
                return False
            
            data = r.json()
            aggregated = data.get("aggregated", [])
            totals = data.get("totals", {})
            
            # Check response structure
            self.test("Manual mode source is 'lines'", data.get("source") == "lines")
            self.test("Has aggregated materials", len(aggregated) > 0)
            
            # Check cost fields are present
            if len(aggregated) > 0:
                mat = aggregated[0]
                self.test("Material has unit_cost", "unit_cost" in mat)
                self.test("Material has subtotal_cost", "subtotal_cost" in mat)
                self.test("Material has cost_source", "cost_source" in mat)
            
            # Check grand_total_cost > 0
            self.test("grand_total_cost > 0", 
                     totals.get("grand_total_cost", 0) > 0,
                     f"Expected > 0, got {totals.get('grand_total_cost')}")
            
            return True
            
        except Exception as e:
            self.log(f"Test 4 exception: {e}", "FAIL")
            return False
    
    def test_validation_regression(self):
        """Test 5: Validation regression (empty body, nonexistent po_id, no auth)"""
        print("\n[TEST 5] Validation Regression")
        
        # Test 5a: Empty body should return 400
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={},
                timeout=10
            )
            self.test("Empty body returns 400", r.status_code == 400,
                     f"Expected 400, got {r.status_code}")
        except Exception as e:
            self.log(f"Test 5a exception: {e}", "FAIL")
        
        # Test 5b: Nonexistent po_id should return 404
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={"po_id": "nonexistent-po-id-12345"},
                timeout=10
            )
            self.test("Nonexistent po_id returns 404", r.status_code == 404,
                     f"Expected 404, got {r.status_code}")
        except Exception as e:
            self.log(f"Test 5b exception: {e}", "FAIL")
        
        # Test 5c: No auth should return 401 or 403
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers={"Content-Type": "application/json"},
                json={"po_id": PO_ID},
                timeout=10
            )
            self.test("No auth returns 401 or 403", r.status_code in [401, 403],
                     f"Expected 401 or 403, got {r.status_code}")
        except Exception as e:
            self.log(f"Test 5c exception: {e}", "FAIL")
        
        # Test 5d: Cross-line aggregation (multiple lines with same material)
        try:
            r = requests.post(
                f"{BASE_URL}/rahaza/material-requirements",
                headers=self.get_headers(),
                json={
                    "lines": [
                        {"model_id": MODEL_ID, "size_id": SIZE_L_ID, "qty_pcs": 50},
                        {"model_id": MODEL_ID, "size_id": SIZE_L_ID, "qty_pcs": 50}
                    ]
                },
                timeout=15
            )
            if r.status_code == 200:
                data = r.json()
                # Should aggregate correctly (100 pcs total)
                self.test("Cross-line aggregation successful", 
                         data.get("totals", {}).get("grand_qty_pcs", 0) == 100,
                         f"Expected 100 pcs total, got {data.get('totals', {}).get('grand_qty_pcs')}")
            else:
                self.test("Cross-line aggregation request", False, 
                         f"Status {r.status_code}: {r.text[:200]}")
        except Exception as e:
            self.log(f"Test 5d exception: {e}", "FAIL")
        
        return True
    
    def run_all_tests(self):
        print("\n" + "="*80)
        print("MATERIAL REQUIREMENTS PLANNING (MRP) — COST & STOCK POLISH TESTING")
        print("="*80 + "\n")
        
        # Login
        print("[AUTH] Logging in as admin...")
        if not self.login():
            print("\n❌ Cannot proceed without admin token")
            return False
        self.log("Admin login successful", "PASS")
        
        # Run all tests
        self.test_po_mode_with_cost()
        self.test_real_stock()
        self.test_include_cost_false()
        self.test_manual_mode_with_cost()
        self.test_validation_regression()
        
        # Summary
        print("\n" + "="*80)
        print(f"TESTS COMPLETED: {self.tests_passed}/{self.tests_run} passed")
        print("="*80 + "\n")
        
        return self.tests_passed == self.tests_run


def main():
    tester = MRPTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
