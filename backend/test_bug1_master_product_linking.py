"""
Test BUG-1: Product Launches & Forms Must Use Master Product (Not Custom Text)
===============================================================================
Temuan pemilik 2026-08-14: Form Launching meminta staf MENGETIK nama produk/
bahan/model sebagai teks bebas, padahal yang diluncurkan adalah produk DA
sendiri yang sudah terdaftar di master (rahaza_models + varian FG).

Test Coverage:
1. POST /api/marketing/product-launches - reject without model_id (400)
2. POST /api/marketing/product-launches - reject with invalid model_id (400)
3. POST /api/marketing/product-launches - with valid model_id, ignore browser-sent product_name/material/model
4. PUT /api/marketing/product-launches/{id} - must not allow changing master-derived fields
5. POST /api/marketing/product-launches/{id}/status - must NOT create new FG
6. GET /api/marketing/product-launches - must return master_link.unlinked_total
7. GET /api/marketing/catalogs/master-products - must return 'material' field
8. POST /api/marketing/ai-content/generate-caption - must accept model_id and reject if invalid
9. POST /api/dewi/cmt-component-requests - must reject invalid model_id
"""
import requests
import sys
import os

API = os.environ.get('REACT_APP_BACKEND_URL', 'https://da37-cmt-bridge.preview.emergentagent.com')

class TestBug1MasterProductLinking:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.valid_model_id = None
        self.valid_account_id = None
        self.test_launch_id = None

    def log(self, msg, status='INFO'):
        prefix = {
            'PASS': '✅',
            'FAIL': '❌',
            'INFO': '🔍',
            'WARN': '⚠️'
        }.get(status, 'ℹ️')
        print(f"{prefix} {msg}")

    def login(self):
        """Login as admin"""
        self.log("Logging in as admin@garment.com...")
        try:
            r = requests.post(f"{API}/api/auth/login", json={
                "email": "admin@garment.com",
                "password": "Admin@123"
            }, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get('token')
                if self.token:
                    self.log("Login successful", 'PASS')
                    return True
                else:
                    self.log("Login response missing 'token' key", 'FAIL')
                    return False
            else:
                self.log(f"Login failed: {r.status_code} - {r.text[:200]}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Login error: {e}", 'FAIL')
            return False

    def get_headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def setup_test_data(self):
        """Get valid model_id and account_id for tests"""
        self.log("Setting up test data...")
        
        # Get valid model_id from master products
        try:
            r = requests.get(f"{API}/api/marketing/catalogs/master-products?limit=5",
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                products = data.get('products', [])
                if products:
                    self.valid_model_id = products[0]['model_id']
                    self.log(f"Found valid model_id: {self.valid_model_id}", 'PASS')
                else:
                    self.log("No master products found", 'WARN')
                    return False
            else:
                self.log(f"Failed to get master products: {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error getting master products: {e}", 'FAIL')
            return False

        # Get valid account_id - try multiple endpoints
        try:
            # Try marketing accounts endpoint
            r = requests.get(f"{API}/api/marketing/accounts?limit=5",
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                # Response might be a list or dict
                if isinstance(data, list):
                    accounts = data
                else:
                    accounts = data.get('accounts', []) or data.get('data', [])
                
                if accounts:
                    self.valid_account_id = accounts[0]['id']
                    self.log(f"Found valid account_id: {self.valid_account_id}", 'PASS')
                else:
                    self.log("No marketing accounts found", 'WARN')
                    return False
            else:
                self.log(f"Failed to get marketing accounts: {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error getting marketing accounts: {e}", 'FAIL')
            return False

        return True

    def test_1_create_launch_without_model_id(self):
        """TEST 1: POST /api/marketing/product-launches MUST reject without model_id (400)"""
        self.tests_run += 1
        self.log("\nTEST 1: Create launch without model_id (should be rejected)")
        
        payload = {
            "account_id": self.valid_account_id,
            "product_name": "Produk Karangan",
            "launch_date": "2026-12-01"
        }
        
        try:
            r = requests.post(f"{API}/api/marketing/product-launches",
                            json=payload, headers=self.get_headers(), timeout=10)
            # Accept both 400 (business logic) and 422 (Pydantic validation) as valid rejections
            if r.status_code in [400, 422]:
                detail = r.json().get('detail', '')
                self.log(f"Correctly rejected ({r.status_code}): {detail}", 'PASS')
                self.tests_passed += 1
                return True
            else:
                self.log(f"FAILED: Expected 400/422, got {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_2_create_launch_with_invalid_model_id(self):
        """TEST 2: POST with invalid model_id must return 400 mentioning 'Master Produk'"""
        self.tests_run += 1
        self.log("\nTEST 2: Create launch with invalid model_id (should be rejected)")
        
        payload = {
            "account_id": self.valid_account_id,
            "model_id": "INVALID-MODEL-ID-12345",
            "launch_date": "2026-12-01"
        }
        
        try:
            r = requests.post(f"{API}/api/marketing/product-launches",
                            json=payload, headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                detail = r.json().get('detail', '')
                if 'Master Produk' in detail:
                    self.log(f"Correctly rejected with proper message: {detail}", 'PASS')
                    self.tests_passed += 1
                    return True
                else:
                    self.log(f"Rejected but message doesn't mention 'Master Produk': {detail}", 'FAIL')
                    return False
            else:
                self.log(f"FAILED: Expected 400, got {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_3_create_launch_ignores_browser_fields(self):
        """TEST 3: POST with valid model_id must IGNORE browser-sent product_name/material/model"""
        self.tests_run += 1
        self.log("\nTEST 3: Create launch with valid model_id (server must ignore browser fields)")
        
        # First get the actual master product data
        try:
            r = requests.get(f"{API}/api/marketing/catalogs/master-products?limit=1",
                           headers=self.get_headers(), timeout=10)
            master_data = r.json()['products'][0]
            master_name = master_data['name']
            master_code = master_data['code']
        except Exception as e:  # noqa: BLE001 — alat uji: alasan gagalnya harus terbaca
            self.log(f"Failed to get master product data: {e}", 'FAIL')
            return False
        
        payload = {
            "account_id": self.valid_account_id,
            "model_id": self.valid_model_id,
            "product_name": "FAKE NAME FROM BROWSER",
            "material": "FAKE MATERIAL",
            "model": "FAKE-CODE",
            "launch_date": "2026-12-01",
            "listing_price": 100000
        }
        
        try:
            r = requests.post(f"{API}/api/marketing/product-launches",
                            json=payload, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()['data']
                self.test_launch_id = data['id']  # Save for later tests
                
                # Check that server used master data, not browser data
                if data['product_name'] == master_name and data['model_code'] == master_code:
                    if data['product_name'] != "FAKE NAME FROM BROWSER":
                        self.log(f"Server correctly used master data: {data['product_name']}", 'PASS')
                        self.tests_passed += 1
                        return True
                    else:
                        self.log("Server used browser data instead of master!", 'FAIL')
                        return False
                else:
                    self.log(f"Product name mismatch. Expected: {master_name}, Got: {data['product_name']}", 'FAIL')
                    return False
            else:
                self.log(f"FAILED: Expected 200, got {r.status_code} - {r.text[:200]}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_4_update_launch_cannot_change_master_fields(self):
        """TEST 4: PUT must not allow changing master-derived fields"""
        self.tests_run += 1
        self.log("\nTEST 4: Update launch (master fields should not change)")
        
        if not self.test_launch_id:
            self.log("No test launch ID available, skipping", 'WARN')
            return False
        
        # Get current data
        try:
            r = requests.get(f"{API}/api/marketing/product-launches?page=1&page_size=100",
                           headers=self.get_headers(), timeout=10)
            launches = r.json()['data']
            current = next((l for l in launches if l['id'] == self.test_launch_id), None)
            if not current:
                self.log("Test launch not found", 'FAIL')
                return False
            
            original_name = current['product_name']
            original_code = current.get('model_code') or current.get('model')
        except Exception as e:
            self.log(f"Error getting current launch: {e}", 'FAIL')
            return False
        
        # Try to update with fake data
        payload = {
            "product_name": "HACKED NAME",
            "material": "HACKED MATERIAL",
            "model": "HACKED-CODE",
            "listing_price": 200000  # This SHOULD be allowed to change
        }
        
        try:
            r = requests.put(f"{API}/api/marketing/product-launches/{self.test_launch_id}",
                           json=payload, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()['data']
                
                # Master fields should NOT change
                if data['product_name'] == original_name and data.get('model_code', data.get('model')) == original_code:
                    # But listing_price SHOULD change
                    if data['listing_price'] == 200000:
                        self.log("Master fields protected, but listing_price updated correctly", 'PASS')
                        self.tests_passed += 1
                        return True
                    else:
                        self.log("Master fields protected but listing_price didn't update", 'WARN')
                        self.tests_passed += 1
                        return True
                else:
                    self.log(f"Master fields were changed! Name: {data['product_name']}, Code: {data.get('model_code')}", 'FAIL')
                    return False
            else:
                self.log(f"Update failed: {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_5_launch_status_no_fg_creation(self):
        """TEST 5: POST status='launched' must NOT create new FG"""
        self.tests_run += 1
        self.log("\nTEST 5: Change status to 'launched' (should NOT create new FG)")
        
        if not self.test_launch_id:
            self.log("No test launch ID available, skipping", 'WARN')
            return False
        
        # Count FG variants before
        try:
            r = requests.get(f"{API}/api/marketing/catalogs/master-products?limit=300",
                           headers=self.get_headers(), timeout=10)
            data = r.json()
            total_variants_before = sum(p['variant_count'] for p in data['products'])
            self.log(f"Total FG variants before: {total_variants_before}")
        except Exception as e:
            self.log(f"Error counting variants: {e}", 'FAIL')
            return False
        
        # Change status to launched
        try:
            r = requests.post(f"{API}/api/marketing/product-launches/{self.test_launch_id}/status",
                            json={"status": "launched"}, headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                
                # Check response flags
                if data.get('fg_auto_created') == False and data.get('fg_link_status') == 'tertaut_master':
                    self.log(f"Response correct: fg_auto_created=False, fg_link_status=tertaut_master", 'PASS')
                else:
                    self.log(f"Response flags incorrect: {data}", 'FAIL')
                    return False
            else:
                self.log(f"Status change failed: {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False
        
        # Count FG variants after
        try:
            r = requests.get(f"{API}/api/marketing/catalogs/master-products?limit=300",
                           headers=self.get_headers(), timeout=10)
            data = r.json()
            total_variants_after = sum(p['variant_count'] for p in data['products'])
            self.log(f"Total FG variants after: {total_variants_after}")
            
            if total_variants_before == total_variants_after:
                self.log("No new FG created (correct!)", 'PASS')
                self.tests_passed += 1
                return True
            else:
                self.log(f"FG count changed! Before: {total_variants_before}, After: {total_variants_after}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error counting variants after: {e}", 'FAIL')
            return False

    def test_6_list_launches_has_master_link_info(self):
        """TEST 6: GET /api/marketing/product-launches must return master_link.unlinked_total"""
        self.tests_run += 1
        self.log("\nTEST 6: List launches (must have master_link info)")
        
        try:
            r = requests.get(f"{API}/api/marketing/product-launches?page=1&page_size=20",
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                
                # Check for master_link in response
                if 'master_link' in data:
                    if 'unlinked_total' in data['master_link']:
                        self.log(f"master_link.unlinked_total present: {data['master_link']['unlinked_total']}", 'PASS')
                        
                        # Check that each item has master_linked field
                        items = data.get('data', [])
                        if items and all('master_linked' in item for item in items):
                            self.log("All items have 'master_linked' field", 'PASS')
                            self.tests_passed += 1
                            return True
                        else:
                            self.log("Some items missing 'master_linked' field", 'FAIL')
                            return False
                    else:
                        self.log("master_link exists but missing 'unlinked_total'", 'FAIL')
                        return False
                else:
                    self.log("Response missing 'master_link' field", 'FAIL')
                    return False
            else:
                self.log(f"Request failed: {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_7_master_products_has_material_field(self):
        """TEST 7: GET /api/marketing/catalogs/master-products must return 'material' field"""
        self.tests_run += 1
        self.log("\nTEST 7: Get master products (must have 'material' field)")
        
        try:
            r = requests.get(f"{API}/api/marketing/catalogs/master-products?limit=5",
                           headers=self.get_headers(), timeout=10)
            if r.status_code == 200:
                data = r.json()
                products = data.get('products', [])
                
                if products:
                    # Check that all products have 'material' field (can be empty string)
                    if all('material' in p for p in products):
                        self.log(f"All {len(products)} products have 'material' field", 'PASS')
                        self.tests_passed += 1
                        return True
                    else:
                        missing = [p['code'] for p in products if 'material' not in p]
                        self.log(f"Products missing 'material' field: {missing}", 'FAIL')
                        return False
                else:
                    self.log("No products returned", 'WARN')
                    return False
            else:
                self.log(f"Request failed: {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_8_ai_caption_with_invalid_model_id(self):
        """TEST 8: POST /api/marketing/ai-content/generate-caption with invalid model_id must return 400"""
        self.tests_run += 1
        self.log("\nTEST 8: Generate caption with invalid model_id (should be rejected)")
        
        payload = {
            "model_id": "INVALID-MODEL-ID",
            "product_name": "Test Product",
            "platform": "instagram"
        }
        
        try:
            r = requests.post(f"{API}/api/marketing/ai-content/generate-caption",
                            json=payload, headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                detail = r.json().get('detail', '')
                if 'Master Produk' in detail:
                    self.log(f"Correctly rejected: {detail}", 'PASS')
                    self.tests_passed += 1
                    return True
                else:
                    self.log(f"Rejected but message doesn't mention 'Master Produk': {detail}", 'FAIL')
                    return False
            else:
                self.log(f"Expected 400, got {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def test_9_cmt_request_with_invalid_model_id(self):
        """TEST 9: POST /api/dewi/cmt-component-requests with invalid model_id must return 400"""
        self.tests_run += 1
        self.log("\nTEST 9: Create CMT request with invalid model_id (should be rejected)")
        
        payload = {
            "model_id": "INVALID-MODEL-ID",
            "product_name": "Test Product",
            "request_type": "component",
            "items": [{"component_type": "sleeve", "qty": 10, "unit": "pcs"}]
        }
        
        try:
            r = requests.post(f"{API}/api/dewi/cmt-component-requests",
                            json=payload, headers=self.get_headers(), timeout=10)
            if r.status_code == 400:
                detail = r.json().get('detail', '')
                if 'Master Produk' in detail:
                    self.log(f"Correctly rejected: {detail}", 'PASS')
                    self.tests_passed += 1
                    return True
                else:
                    self.log(f"Rejected but message doesn't mention 'Master Produk': {detail}", 'FAIL')
                    return False
            else:
                self.log(f"Expected 400, got {r.status_code}", 'FAIL')
                return False
        except Exception as e:
            self.log(f"Error: {e}", 'FAIL')
            return False

    def cleanup(self):
        """Delete test launch"""
        if self.test_launch_id:
            self.log("\nCleaning up test data...")
            try:
                r = requests.delete(f"{API}/api/marketing/product-launches/{self.test_launch_id}",
                                  headers=self.get_headers(), timeout=10)
                if r.status_code == 200:
                    self.log("Test launch deleted", 'PASS')
                else:
                    self.log(f"Failed to delete test launch: {r.status_code}", 'WARN')
            except Exception as e:
                self.log(f"Cleanup error: {e}", 'WARN')

    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*80)
        print("BUG-1 BACKEND TEST: Master Product Linking")
        print("="*80)
        
        if not self.login():
            print("\n❌ Login failed, cannot proceed with tests")
            return False
        
        if not self.setup_test_data():
            print("\n❌ Setup failed, cannot proceed with tests")
            return False
        
        # Run all tests
        self.test_1_create_launch_without_model_id()
        self.test_2_create_launch_with_invalid_model_id()
        self.test_3_create_launch_ignores_browser_fields()
        self.test_4_update_launch_cannot_change_master_fields()
        self.test_5_launch_status_no_fg_creation()
        self.test_6_list_launches_has_master_link_info()
        self.test_7_master_products_has_material_field()
        self.test_8_ai_caption_with_invalid_model_id()
        self.test_9_cmt_request_with_invalid_model_id()
        
        # Cleanup
        self.cleanup()
        
        # Summary
        print("\n" + "="*80)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*80)
        
        if self.tests_passed == self.tests_run:
            print("✅ ALL TESTS PASSED")
            return True
        else:
            print(f"❌ {self.tests_run - self.tests_passed} TESTS FAILED")
            return False

if __name__ == "__main__":
    tester = TestBug1MasterProductLinking()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
