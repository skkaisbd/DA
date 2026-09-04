#!/usr/bin/env python3
"""Backend API tests for Quarantine Module - Round 2 (untested flows from iteration_164)"""

import requests
import sys
import os
from datetime import datetime

class QuarantineBackendTester:
    def __init__(self):
        self.base_url = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com")
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
    def log(self, status, test_name, message=""):
        """Log test result"""
        self.tests_run += 1
        if status == "PASS":
            self.tests_passed += 1
            print(f"✅ PASS: {test_name}")
        elif status == "FAIL":
            print(f"❌ FAIL: {test_name} - {message}")
        elif status == "SKIP":
            print(f"⏭️  SKIP: {test_name} - {message}")
        else:
            print(f"ℹ️  INFO: {test_name} - {message}")
        
        self.test_results.append({
            "test": test_name,
            "status": status,
            "message": message
        })
        
    def login(self, email, password):
        """Login and get token"""
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                if self.token:
                    self.log("PASS", f"Login as {email}")
                    return True
                else:
                    self.log("FAIL", f"Login as {email}", "No token in response")
                    return False
            else:
                self.log("FAIL", f"Login as {email}", f"Status {response.status_code}: {response.text[:200]}")
                return False
        except Exception as e:
            self.log("FAIL", f"Login as {email}", str(e))
            return False
    
    def get_headers(self):
        """Get auth headers"""
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test_b9_manual_quarantine_with_correct_location(self):
        """B9: Manual quarantine via API with correct location that has stock"""
        print("\n=== B9: Manual Quarantine via API (with correct location) ===")
        
        try:
            # Step 1: Get TEST-Q6-BTN material
            response = requests.get(
                f"{self.base_url}/api/rahaza/materials?search=TEST-Q6-BTN",
                headers=self.get_headers(),
                timeout=30
            )
            if response.status_code != 200:
                self.log("FAIL", "B9-1: Get TEST-Q6-BTN material", f"Status {response.status_code}")
                return
            
            materials = response.json()
            if isinstance(materials, dict):
                materials = materials.get("items", [])
            
            btn_material = next((m for m in materials if m.get("code") == "TEST-Q6-BTN"), None)
            if not btn_material:
                self.log("FAIL", "B9-1: Get TEST-Q6-BTN material", "Material not found")
                return
            
            material_id = btn_material["id"]
            self.log("PASS", "B9-1: Get TEST-Q6-BTN material", f"ID: {material_id}")
            
            # Step 2: Get material stock to find location with stock
            response = requests.get(
                f"{self.base_url}/api/rahaza/material-stock?material_id={material_id}",
                headers=self.get_headers(),
                timeout=30
            )
            if response.status_code != 200:
                self.log("FAIL", "B9-2: Get material stock", f"Status {response.status_code}")
                return
            
            stock_data = response.json()
            if isinstance(stock_data, dict):
                stock_data = stock_data.get("items", [])
            
            # Find location with available stock (not quarantine location)
            valid_location = None
            for stock in stock_data:
                qty = stock.get("quantity", 0) or stock.get("qty", 0)
                available = stock.get("available_quantity", qty)
                location_id = stock.get("location_id")
                
                # Skip quarantine locations and locations without available stock
                if available > 0 and not stock.get("quarantine", False):
                    valid_location = location_id
                    self.log("PASS", "B9-2: Find location with stock", f"Location: {location_id}, Available: {available}")
                    break
            
            if not valid_location:
                self.log("SKIP", "B9-2: Find location with stock", "No location with available stock found")
                return
            
            # Step 3: Test manual quarantine with correct location
            payload = {
                "material_id": material_id,
                "qty": 10,
                "from_location_id": valid_location,
                "unit": "pcs",
                "reason_code": "DAMAGED_PACKAGING",
                "notes": "B9 test - manual quarantine with correct location"
            }
            
            response = requests.post(
                f"{self.base_url}/api/wms/quarantine/manual",
                headers=self.get_headers(),
                json=payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                # Verify response structure
                if data.get("id") and data.get("material_id") == material_id:
                    # Verify valued=True (manual quarantine from storage)
                    if data.get("valued") == True:
                        # Verify unit follows material master
                        if data.get("unit") == "pcs":
                            # Verify reject_reasons is populated
                            reasons = data.get("reject_reasons", [])
                            if reasons and reasons[0].get("code") == "DAMAGED_PACKAGING":
                                self.log("PASS", "B9-3: Manual quarantine API", "All fields correct")
                            else:
                                self.log("FAIL", "B9-3: Manual quarantine API", f"reject_reasons not populated correctly: {reasons}")
                        else:
                            self.log("FAIL", "B9-3: Manual quarantine API", f"Unit incorrect: {data.get('unit')}")
                    else:
                        self.log("FAIL", "B9-3: Manual quarantine API", f"valued should be True, got {data.get('valued')}")
                else:
                    self.log("FAIL", "B9-3: Manual quarantine API", "Response structure incorrect")
            else:
                self.log("FAIL", "B9-3: Manual quarantine API", f"Status {response.status_code}: {response.text[:200]}")
            
            # Step 4: Test negative cases
            # 4a: qty <= 0
            response = requests.post(
                f"{self.base_url}/api/wms/quarantine/manual",
                headers=self.get_headers(),
                json={**payload, "qty": 0},
                timeout=30
            )
            if response.status_code == 400:
                self.log("PASS", "B9-4a: Negative test qty<=0", "Correctly rejected")
            else:
                self.log("FAIL", "B9-4a: Negative test qty<=0", f"Expected 400, got {response.status_code}")
            
            # 4b: from_location_id empty
            response = requests.post(
                f"{self.base_url}/api/wms/quarantine/manual",
                headers=self.get_headers(),
                json={**payload, "from_location_id": ""},
                timeout=30
            )
            if response.status_code == 400:
                self.log("PASS", "B9-4b: Negative test empty location", "Correctly rejected")
            else:
                self.log("FAIL", "B9-4b: Negative test empty location", f"Expected 400, got {response.status_code}")
            
            # 4c: from_location_id = quarantine location
            # Get quarantine location
            response = requests.get(
                f"{self.base_url}/api/wms/quarantine/location",
                headers=self.get_headers(),
                timeout=30
            )
            if response.status_code == 200:
                q_loc = response.json().get("id")
                response = requests.post(
                    f"{self.base_url}/api/wms/quarantine/manual",
                    headers=self.get_headers(),
                    json={**payload, "from_location_id": q_loc},
                    timeout=30
                )
                if response.status_code == 400:
                    self.log("PASS", "B9-4c: Negative test quarantine location", "Correctly rejected")
                else:
                    self.log("FAIL", "B9-4c: Negative test quarantine location", f"Expected 400, got {response.status_code}")
            
            # 4d: qty exceeds stock
            response = requests.post(
                f"{self.base_url}/api/wms/quarantine/manual",
                headers=self.get_headers(),
                json={**payload, "qty": 999999},
                timeout=30
            )
            if response.status_code == 400:
                error_msg = response.text
                if "stok" in error_msg.lower() or "insufficient" in error_msg.lower():
                    self.log("PASS", "B9-4d: Negative test qty exceeds stock", "Correctly rejected with informative message")
                else:
                    self.log("PASS", "B9-4d: Negative test qty exceeds stock", f"Rejected but message could be clearer: {error_msg[:100]}")
            else:
                self.log("FAIL", "B9-4d: Negative test qty exceeds stock", f"Expected 400, got {response.status_code}")
                
        except Exception as e:
            self.log("FAIL", "B9: Manual quarantine test", str(e))
    
    def test_b10_guard_validations(self):
        """B10: Guard validations for disposition actions"""
        print("\n=== B10: Guard Validations ===")
        
        try:
            # Step 1: Get open quarantine items
            response = requests.get(
                f"{self.base_url}/api/wms/quarantine?status=open",
                headers=self.get_headers(),
                timeout=30
            )
            if response.status_code != 200:
                self.log("FAIL", "B10-1: Get open items", f"Status {response.status_code}")
                return
            
            open_items = response.json()
            if isinstance(open_items, dict):
                open_items = open_items.get("items", [])
            
            if not open_items:
                self.log("SKIP", "B10-1: Get open items", "No open items found")
                return
            
            test_item = open_items[0]
            item_id = test_item["id"]
            remaining_qty = test_item.get("remaining_qty", 0)
            self.log("PASS", "B10-1: Get open items", f"Found item {item_id} with remaining_qty={remaining_qty}")
            
            # Step 2: Test qty exceeds remaining_qty
            # Get storage locations for release
            response = requests.get(
                f"{self.base_url}/api/rahaza/storage-locations",
                headers=self.get_headers(),
                timeout=30
            )
            if response.status_code != 200:
                self.log("FAIL", "B10-2a: Get storage locations", f"Status {response.status_code}")
                return
            
            locations = response.json()
            if isinstance(locations, dict):
                locations = locations.get("items", [])
            
            if not locations:
                self.log("SKIP", "B10-2a: Get storage locations", "No locations found")
                return
            
            target_location = locations[0]["id"]
            
            # Try to release with qty > remaining_qty
            response = requests.post(
                f"{self.base_url}/api/wms/quarantine/{item_id}/release",
                headers=self.get_headers(),
                json={
                    "qty": remaining_qty + 100,
                    "to_location_id": target_location,
                    "notes": "B10 test - qty exceeds remaining"
                },
                timeout=30
            )
            
            if response.status_code == 400:
                error_msg = response.text
                if "melebihi" in error_msg.lower() or "exceed" in error_msg.lower():
                    self.log("PASS", "B10-2: Qty exceeds remaining_qty", "Correctly rejected with clear message")
                else:
                    self.log("PASS", "B10-2: Qty exceeds remaining_qty", f"Rejected but message: {error_msg[:100]}")
            else:
                self.log("FAIL", "B10-2: Qty exceeds remaining_qty", f"Expected 400, got {response.status_code}")
            
            # Step 3: Test closed item
            # Get closed items
            response = requests.get(
                f"{self.base_url}/api/wms/quarantine?status=closed",
                headers=self.get_headers(),
                timeout=30
            )
            
            closed_items = []
            if response.status_code == 200:
                closed_items = response.json()
                if isinstance(closed_items, dict):
                    closed_items = closed_items.get("items", [])
            
            if closed_items:
                closed_item_id = closed_items[0]["id"]
                response = requests.post(
                    f"{self.base_url}/api/wms/quarantine/{closed_item_id}/release",
                    headers=self.get_headers(),
                    json={
                        "qty": 1,
                        "to_location_id": target_location,
                        "notes": "B10 test - closed item"
                    },
                    timeout=30
                )
                
                if response.status_code == 400:
                    error_msg = response.text
                    if "ditutup" in error_msg.lower() or "closed" in error_msg.lower():
                        self.log("PASS", "B10-3: Closed item validation", "Correctly rejected")
                    else:
                        self.log("PASS", "B10-3: Closed item validation", f"Rejected: {error_msg[:100]}")
                else:
                    self.log("FAIL", "B10-3: Closed item validation", f"Expected 400, got {response.status_code}")
            else:
                self.log("SKIP", "B10-3: Closed item validation", "No closed items to test")
            
            # Step 4: Test invalid item_id
            response = requests.post(
                f"{self.base_url}/api/wms/quarantine/invalid-id-12345/release",
                headers=self.get_headers(),
                json={
                    "qty": 1,
                    "to_location_id": target_location,
                    "notes": "B10 test - invalid id"
                },
                timeout=30
            )
            
            if response.status_code == 404:
                self.log("PASS", "B10-4: Invalid item_id", "Correctly returned 404")
            else:
                self.log("FAIL", "B10-4: Invalid item_id", f"Expected 404, got {response.status_code}")
                
        except Exception as e:
            self.log("FAIL", "B10: Guard validations", str(e))
    
    def run_all_tests(self):
        """Run all backend tests"""
        print("=" * 80)
        print("QUARANTINE MODULE - BACKEND API TESTS (ROUND 2)")
        print("=" * 80)
        
        # Login as admin
        if not self.login("admin@garment.com", "Admin@123"):
            print("\n❌ Cannot proceed without login")
            return False
        
        # Run tests
        self.test_b9_manual_quarantine_with_correct_location()
        self.test_b10_guard_validations()
        
        # Summary
        print("\n" + "=" * 80)
        print(f"BACKEND TESTS SUMMARY: {self.tests_passed}/{self.tests_run} PASSED")
        print("=" * 80)
        
        return self.tests_passed == self.tests_run

def main():
    tester = QuarantineBackendTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
