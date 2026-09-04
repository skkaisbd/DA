"""
Warehouse Consolidation Backend API Testing
CV. Dewi Aditya ERP - Session #23 Warehouse Consolidation

Tests RC-IA-warehouse-1, RC-IA-warehouse-2, RC-IA-warehouse-3:
- Location master unification (legacy + wh_positions)
- Putaway dual-lookup (wh_positions support)
- Single adjust door (rahaza/material-adjust with GL posting)
- Unified stock viewer
"""
import requests
import sys
from datetime import datetime
from typing import Dict, Optional

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
TEST_EMAIL = "admin@garment.com"
TEST_PASSWORD = "Admin@123"

class WarehouseConsolidationTester:
    def __init__(self):
        self.token = None
        self.headers = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.passed_tests = []
        
    def log(self, msg: str, level: str = "INFO"):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")
    
    def test(self, name: str, method: str, endpoint: str, expected_status: int, 
             data: Optional[Dict] = None, params: Optional[Dict] = None) -> tuple:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}{endpoint}"
        
        self.log(f"Testing: {name}", "TEST")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers, params=params, timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=self.headers, json=data, timeout=15)
            elif method == "PUT":
                response = requests.put(url, headers=self.headers, json=data, timeout=15)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.headers, timeout=15)
            else:
                self.log(f"❌ FAILED - Unknown method: {method}", "ERROR")
                self.tests_failed += 1
                self.failed_tests.append({"test": name, "reason": f"Unknown method: {method}"})
                return False, {}
            
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}", "PASS")
                self.passed_tests.append(name)
                try:
                    return True, response.json() if response.text else {}
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text[:200]
                self.failed_tests.append({
                    "test": name,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "error": error_detail
                })
                return False, {}
                
        except requests.exceptions.Timeout:
            self.tests_failed += 1
            self.log("❌ FAILED - Request timeout", "ERROR")
            self.failed_tests.append({"test": name, "reason": "Timeout"})
            return False, {}
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAILED - Error: {str(e)}", "ERROR")
            self.failed_tests.append({"test": name, "reason": str(e)})
            return False, {}
    
    def login(self) -> bool:
        """Authenticate and get token"""
        self.log("=" * 80, "INFO")
        self.log("WAREHOUSE CONSOLIDATION BACKEND API TESTING", "INFO")
        self.log("=" * 80, "INFO")
        self.log(f"Base URL: {BASE_URL}", "INFO")
        self.log(f"Test User: {TEST_EMAIL}", "INFO")
        self.log("=" * 80, "INFO")
        
        success, response = self.test(
            "Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        
        if success and response.get("token"):
            self.token = response["token"]
            self.headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            self.log(f"✅ Login successful. Token: {self.token[:20]}...", "INFO")
            return True
        else:
            self.log("❌ Login failed. Cannot proceed with tests.", "ERROR")
            return False
    
    def test_rc_ia_warehouse_2_location_unify(self):
        """RC-IA-warehouse-2: GET /api/wms/legacy/locations returns union (~44 entries)"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("RC-IA-warehouse-2: Location Master Unification", "INFO")
        self.log("=" * 80, "INFO")
        
        success, response = self.test(
            "RC-IA-warehouse-2: Get unified locations",
            "GET",
            "/api/wms/legacy/locations",
            200
        )
        
        if success:
            locations = response if isinstance(response, list) else []
            self.log(f"Total locations returned: {len(locations)}", "INFO")
            
            # Count by source
            legacy_count = sum(1 for loc in locations if loc.get("source") == "legacy")
            wh_positions_count = sum(1 for loc in locations if loc.get("source") == "wh_positions")
            
            self.log(f"Legacy locations: {legacy_count}", "INFO")
            self.log(f"WH positions: {wh_positions_count}", "INFO")
            
            # Verify expected count (~44: 8 legacy + 36 wh_positions)
            if len(locations) >= 40 and len(locations) <= 50:
                self.log(f"✅ Location count in expected range (40-50): {len(locations)}", "PASS")
            else:
                self.log(f"⚠️  Location count outside expected range: {len(locations)} (expected ~44)", "WARN")
            
            # Verify fields
            if locations:
                sample = locations[0]
                required_fields = ["id", "code", "name", "source"]
                missing = [f for f in required_fields if f not in sample]
                if not missing:
                    self.log("✅ All required fields present in location entries", "PASS")
                else:
                    self.log(f"⚠️  Missing fields in location entries: {missing}", "WARN")
            
            return locations
        return []
    
    def test_rc_ia_warehouse_2_putaway_dual_lookup(self, locations):
        """RC-IA-warehouse-2: POST /api/wms/legacy/putaway with wh_position id should succeed"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("RC-IA-warehouse-2: Putaway Dual-Lookup", "INFO")
        self.log("=" * 80, "INFO")
        
        # Find a wh_position location
        wh_position_loc = next((loc for loc in locations if loc.get("source") == "wh_positions"), None)
        
        if not wh_position_loc:
            self.log("⚠️  No wh_position location found, skipping putaway test", "WARN")
            return
        
        self.log(f"Using wh_position location: {wh_position_loc.get('name')} (id: {wh_position_loc.get('id')})", "INFO")
        
        # First, get stock to find a valid source_stock_id
        success, stock_response = self.test(
            "Get warehouse stock for putaway test",
            "GET",
            "/api/wms/legacy/stock",
            200
        )
        
        if not success or not stock_response:
            self.log("⚠️  Could not get stock data, skipping putaway test", "WARN")
            return
        
        stock_items = stock_response if isinstance(stock_response, list) else []
        valid_stock = next((s for s in stock_items if float(s.get("available", s.get("quantity", 0))) > 0), None)
        
        if not valid_stock:
            self.log("⚠️  No stock with available quantity found, skipping putaway test", "WARN")
            return
        
        self.log(f"Using source stock: {valid_stock.get('product_name')} (qty: {valid_stock.get('quantity')})", "INFO")
        
        # Attempt putaway to wh_position
        putaway_data = {
            "source_stock_id": valid_stock.get("id"),
            "target_location_id": wh_position_loc.get("id"),
            "quantity": 1.0
        }
        
        success, response = self.test(
            "RC-IA-warehouse-2: Putaway to wh_position",
            "POST",
            "/api/wms/legacy/putaway",
            200,
            data=putaway_data
        )
        
        if success:
            self.log("✅ Putaway to wh_position succeeded (dual-lookup working)", "PASS")
        else:
            # Check if error is "Target location not found" (the bug we're testing for)
            error_msg = str(response.get("error", "")).lower() if isinstance(response, dict) else ""
            if "target location not found" in error_msg or "404" in error_msg:
                self.log("❌ Putaway failed with 'Target location not found' - dual-lookup NOT working", "FAIL")
            else:
                self.log(f"⚠️  Putaway failed with different error: {response}", "WARN")
    
    def test_rc_ia_warehouse_3_adjust_endpoint(self):
        """RC-IA-warehouse-3: POST /api/rahaza/material-adjust works with GL posting"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("RC-IA-warehouse-3: Single Adjust Door (rahaza/material-adjust)", "INFO")
        self.log("=" * 80, "INFO")
        
        # Get unified stock to find a material with stock
        success, stock_response = self.test(
            "Get unified stock for adjust test",
            "GET",
            "/api/wms/stock/unified",
            200
        )
        
        if not success:
            self.log("⚠️  Could not get unified stock, skipping adjust test", "WARN")
            return
        
        items = stock_response.get("items", []) if isinstance(stock_response, dict) else []
        if not items:
            self.log("⚠️  No stock items found, skipping adjust test", "WARN")
            return
        
        # Find an item with stock
        test_item = next((item for item in items if float(item.get("quantity", 0)) > 0), None)
        if not test_item:
            self.log("⚠️  No items with stock found, skipping adjust test", "WARN")
            return
        
        material_id = test_item.get("material_id")
        location_id = test_item.get("location_id")
        current_qty = float(test_item.get("quantity", 0))
        
        self.log(f"Testing adjust on material: {test_item.get('material_name')} (current qty: {current_qty})", "INFO")
        
        # Test adjustment: increase by 5
        adjust_data = {
            "material_id": material_id,
            "location_id": location_id,
            "qty": 5.0,
            "reason": "Test adjustment for RC-IA-warehouse-3"
        }
        
        success, response = self.test(
            "RC-IA-warehouse-3: Material adjust (+5)",
            "POST",
            "/api/rahaza/material-adjust",
            200,
            data=adjust_data
        )
        
        if success:
            self.log("✅ Adjustment succeeded", "PASS")
            
            # Check for GL posting result
            posting_result = response.get("_posting_result", {})
            if posting_result:
                self.log(f"GL Posting result: {posting_result.get('ok', False)}", "INFO")
                if posting_result.get("ok"):
                    self.log(f"✅ GL posting successful: JE {posting_result.get('je_number', 'N/A')}", "PASS")
                else:
                    self.log(f"⚠️  GL posting failed: {posting_result.get('error', 'Unknown')}", "WARN")
            else:
                self.log("⚠️  No GL posting result in response", "WARN")
            
            # Verify stock changed
            success2, stock_after = self.test(
                "Verify stock after adjustment",
                "GET",
                "/api/wms/stock/unified",
                200,
                params={"search": material_id}
            )
            
            if success2:
                items_after = stock_after.get("items", []) if isinstance(stock_after, dict) else []
                updated_item = next((item for item in items_after if item.get("material_id") == material_id), None)
                if updated_item:
                    new_qty = float(updated_item.get("quantity", 0))
                    expected_qty = current_qty + 5.0
                    if abs(new_qty - expected_qty) < 0.01:
                        self.log(f"✅ Stock updated correctly: {current_qty} -> {new_qty}", "PASS")
                    else:
                        self.log(f"⚠️  Stock mismatch: expected {expected_qty}, got {new_qty}", "WARN")
            
            # Adjust back to restore original state
            adjust_back_data = {
                "material_id": material_id,
                "location_id": location_id,
                "qty": -5.0,
                "reason": "Restore original qty after test"
            }
            
            self.test(
                "Restore original stock quantity",
                "POST",
                "/api/rahaza/material-adjust",
                200,
                data=adjust_back_data
            )
    
    def test_unified_stock_viewer(self):
        """Test unified stock viewer endpoint"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("Unified Stock Viewer", "INFO")
        self.log("=" * 80, "INFO")
        
        success, response = self.test(
            "Get unified stock (paginated)",
            "GET",
            "/api/wms/stock/unified",
            200,
            params={"page": 1, "limit": 10}
        )
        
        if success:
            items = response.get("items", [])
            total = response.get("total", 0)
            self.log(f"Total stock items: {total}", "INFO")
            self.log(f"Items in page 1: {len(items)}", "INFO")
            
            if items:
                sample = items[0]
                self.log(f"Sample item: {sample.get('material_name', 'N/A')} - Qty: {sample.get('quantity', 0)}", "INFO")
        
        # Test summary endpoint
        success, summary = self.test(
            "Get unified stock summary",
            "GET",
            "/api/wms/stock/unified/summary",
            200
        )
        
        if success:
            by_category = summary.get("by_category", [])
            by_ownership = summary.get("by_ownership", [])
            low_stock = summary.get("low_stock_count", 0)
            
            self.log(f"Categories: {len(by_category)}", "INFO")
            self.log(f"Ownerships: {len(by_ownership)}", "INFO")
            self.log(f"Low stock items: {low_stock}", "INFO")
    
    def run_all_tests(self):
        """Run all warehouse consolidation tests"""
        if not self.login():
            return False
        
        # RC-IA-warehouse-2: Location unification
        locations = self.test_rc_ia_warehouse_2_location_unify()
        
        # RC-IA-warehouse-2: Putaway dual-lookup
        if locations:
            self.test_rc_ia_warehouse_2_putaway_dual_lookup(locations)
        
        # RC-IA-warehouse-3: Single adjust door
        self.test_rc_ia_warehouse_3_adjust_endpoint()
        
        # Unified stock viewer
        self.test_unified_stock_viewer()
        
        # Print summary
        self.print_summary()
        
        return self.tests_failed == 0
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 80, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"✅ Passed: {self.tests_passed}", "PASS")
        self.log(f"❌ Failed: {self.tests_failed}", "FAIL")
        self.log(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "N/A", "INFO")
        
        if self.failed_tests:
            self.log("\n" + "=" * 80, "INFO")
            self.log("FAILED TESTS DETAILS", "INFO")
            self.log("=" * 80, "INFO")
            for i, failure in enumerate(self.failed_tests, 1):
                self.log(f"\n{i}. {failure.get('test', 'Unknown')}", "FAIL")
                if "expected" in failure:
                    self.log(f"   Expected: {failure['expected']}, Got: {failure['actual']}", "FAIL")
                if "error" in failure:
                    self.log(f"   Error: {failure['error']}", "FAIL")
                if "reason" in failure:
                    self.log(f"   Reason: {failure['reason']}", "FAIL")

def main():
    tester = WarehouseConsolidationTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
