#!/usr/bin/env python3
"""
FASE 4 Legacy Cleanup Regression Test
CV. Dewi Aditya ERP — Production PO Module

Tests that removing legacy products/product_variants code did NOT break:
- Internal Production PO create/edit (uses rahaza_models + rahaza_variant_id)
- Maklon Production PO create/edit (uses buyer-catalog catalog_item_id)
- Deprecated endpoints still respond (backward-compat)
"""
import requests
import sys
import os
from datetime import datetime

# Read backend URL from frontend/.env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class Fase4RegressionTest:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}/api/{endpoint}"
        if headers is None:
            headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - {name} (Status: {response.status_code})", "PASS")
                try:
                    return True, response.json()
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                error_msg = f"Expected {expected_status}, got {response.status_code}"
                try:
                    error_detail = response.json()
                    error_msg += f" - {error_detail}"
                except Exception:
                    error_msg += f" - {response.text[:200]}"
                self.log(f"❌ FAIL - {name}: {error_msg}", "FAIL")
                self.failures.append(f"{name}: {error_msg}")
                return False, {}

        except Exception as e:
            self.tests_failed += 1
            error_msg = f"Exception: {str(e)}"
            self.log(f"❌ FAIL - {name}: {error_msg}", "FAIL")
            self.failures.append(f"{name}: {error_msg}")
            return False, {}

    def test_auth_login(self):
        """Test 1: Login with admin credentials"""
        self.log("=" * 60)
        self.log("TEST 1: Authentication")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"Token obtained: {self.token[:20]}...", "INFO")
            return True
        return False

    def test_role_accounts_login(self):
        """Test role accounts login"""
        role_accounts = [
            ("hr@dewiaditya.id", "Dewi@123"),
            ("finance@dewiaditya.id", "Dewi@123"),
            ("spv@dewiaditya.id", "Dewi@123"),
            ("gudang@dewiaditya.id", "Dewi@123"),
            ("maklon@dewiaditya.id", "Dewi@123"),
        ]
        
        for email, password in role_accounts:
            success, response = self.run_test(
                f"Role Account Login ({email})",
                "POST",
                "auth/login",
                200,
                data={"email": email, "password": password}
            )
            if not success:
                return False
        return True

    def test_deprecated_endpoints(self):
        """Test 2: Deprecated endpoints still respond (backward-compat)"""
        self.log("=" * 60)
        self.log("TEST 2: Deprecated Endpoints (Backward Compatibility)")
        self.log("=" * 60)
        
        # Test GET /api/products
        success, response = self.run_test(
            "GET /api/products (deprecated)",
            "GET",
            "products",
            200
        )
        if success:
            if isinstance(response, list):
                self.log(f"  → Returned array with {len(response)} items", "INFO")
            else:
                self.log(f"  → Response type: {type(response)}", "INFO")
        
        # Test GET /api/product-variants
        success, response = self.run_test(
            "GET /api/product-variants (deprecated)",
            "GET",
            "product-variants",
            200
        )
        if success:
            if isinstance(response, list):
                self.log(f"  → Returned array with {len(response)} items", "INFO")
            else:
                self.log(f"  → Response type: {type(response)}", "INFO")
        
        return True

    def test_internal_po_create(self):
        """Test 3: Internal Production PO create"""
        self.log("=" * 60)
        self.log("TEST 3: Internal Production PO Create")
        self.log("=" * 60)
        
        # First, get a model and variant
        self.log("Fetching internal model (int-demo-model-1)...")
        success, models = self.run_test(
            "GET /api/rahaza/models",
            "GET",
            "rahaza/models?active=true&limit=10",
            200
        )
        
        if not success:
            self.log("Failed to fetch models", "ERROR")
            return False
        
        # Find int-demo-model-1
        model = None
        if isinstance(models, list):
            model = next((m for m in models if m.get('id') == 'int-demo-model-1'), None)
        elif isinstance(models, dict) and 'items' in models:
            model = next((m for m in models['items'] if m.get('id') == 'int-demo-model-1'), None)
        
        if not model:
            self.log("Model int-demo-model-1 not found", "ERROR")
            return False
        
        self.log(f"Found model: {model.get('name')} ({model.get('code')})", "INFO")
        
        # Get variants for this model
        self.log(f"Fetching variants for model {model['id']}...")
        success, variants_data = self.run_test(
            f"GET /api/rahaza/models/{model['id']}/variants",
            "GET",
            f"rahaza/models/{model['id']}/variants",
            200
        )
        
        if not success:
            self.log("Failed to fetch variants", "ERROR")
            return False
        
        variants = variants_data.get('variants', []) if isinstance(variants_data, dict) else []
        if not variants:
            self.log("No variants found for model", "ERROR")
            return False
        
        variant = variants[0]
        self.log(f"Using variant: {variant.get('sku')} (color: {variant.get('color_name')}, size: {variant.get('size_code')})", "INFO")
        
        # Create Internal PO
        po_number = f"PO-INT-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        po_data = {
            "po_number": po_number,
            "customer_name": "Gudang FG Sendiri",
            "business_type": "internal",
            "po_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "model_id": model['id'],
                    "rahaza_variant_id": variant['id'],
                    "size_id": variant.get('size_id'),
                    "size": variant.get('size_code'),
                    "color": variant.get('color_name'),
                    "sku": variant.get('sku'),
                    "qty": 10,
                    "serial_number": f"SN-TEST-{datetime.now().strftime('%H%M%S')}"
                }
            ]
        }
        
        success, response = self.run_test(
            "Create Internal PO",
            "POST",
            "production-pos",
            201,
            data=po_data
        )
        
        if success:
            po_id = response.get('id')
            self.log(f"Created PO: {po_number} (ID: {po_id})", "INFO")
            
            # Verify the PO was created correctly
            success, po_detail = self.run_test(
                "GET created PO detail",
                "GET",
                f"production-pos/{po_id}",
                200
            )
            
            if success:
                items = po_detail.get('items', [])
                if items:
                    item = items[0]
                    self.log(f"  → Item model_id: {item.get('model_id')}", "INFO")
                    self.log(f"  → Item rahaza_variant_id: {item.get('rahaza_variant_id')}", "INFO")
                    self.log(f"  → Item SKU: {item.get('sku')}", "INFO")
                    self.log(f"  → Item size: {item.get('size')}", "INFO")
                    self.log(f"  → Item color: {item.get('color')}", "INFO")
                    
                    # Verify fields are correct
                    if (item.get('model_id') == model['id'] and 
                        item.get('rahaza_variant_id') == variant['id'] and
                        item.get('sku') == variant.get('sku')):
                        self.log("✅ PO item fields verified correctly", "PASS")
                        return True, po_id
                    else:
                        self.log("❌ PO item fields mismatch", "FAIL")
                        self.failures.append("Internal PO item fields mismatch")
                        return False, None
            
            return True, po_id
        
        return False, None

    def test_maklon_po_create(self):
        """Test 4: Maklon Production PO create"""
        self.log("=" * 60)
        self.log("TEST 4: Maklon Production PO Create")
        self.log("=" * 60)
        
        # Get maklon client
        self.log("Fetching maklon client (mk-client-demo-1)...")
        success, clients = self.run_test(
            "GET /api/dewi/maklon/clients",
            "GET",
            "dewi/maklon/clients",
            200
        )
        
        if not success:
            self.log("Failed to fetch maklon clients", "ERROR")
            return False
        
        client = None
        if isinstance(clients, list):
            client = next((c for c in clients if c.get('id') == 'mk-client-demo-1'), None)
        
        if not client:
            self.log("Client mk-client-demo-1 not found", "ERROR")
            return False
        
        self.log(f"Found client: {client.get('name')} ({client.get('code')})", "INFO")
        
        # Get buyer catalog for this client
        self.log(f"Fetching buyer catalog for client {client['id']}...")
        success, catalog = self.run_test(
            f"GET /api/dewi/maklon/buyer-catalog",
            "GET",
            f"dewi/maklon/buyer-catalog?client_id={client['id']}&status=active",
            200
        )
        
        if not success:
            self.log("Failed to fetch buyer catalog", "ERROR")
            return False
        
        if not catalog or len(catalog) == 0:
            self.log("No catalog items found", "ERROR")
            return False
        
        catalog_item = catalog[0]
        self.log(f"Using catalog item: {catalog_item.get('product_name')} ({catalog_item.get('artikel_code')})", "INFO")
        
        # Create Maklon PO
        po_number = f"PO-MK-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        po_data = {
            "po_number": po_number,
            "buyer_id": client['id'],
            "customer_name": client.get('name'),
            "business_type": "maklon",
            "po_date": datetime.now().strftime("%Y-%m-%d"),
            "items": [
                {
                    "catalog_item_id": catalog_item['id'],
                    "product_name": catalog_item.get('product_name'),
                    "sku": catalog_item.get('artikel_code'),
                    "qty": 5,
                    "cmt_price_snapshot": catalog_item.get('default_cmt_price', 0),
                    "selling_price_snapshot": catalog_item.get('default_selling_price', 0)
                }
            ]
        }
        
        success, response = self.run_test(
            "Create Maklon PO",
            "POST",
            "production-pos",
            201,
            data=po_data
        )
        
        if success:
            po_id = response.get('id')
            self.log(f"Created PO: {po_number} (ID: {po_id})", "INFO")
            
            # Verify the PO was created correctly
            success, po_detail = self.run_test(
                "GET created Maklon PO detail",
                "GET",
                f"production-pos/{po_id}",
                200
            )
            
            if success:
                items = po_detail.get('items', [])
                if items:
                    item = items[0]
                    self.log(f"  → Item catalog_item_id: {item.get('catalog_item_id')}", "INFO")
                    self.log(f"  → Item product_name: {item.get('product_name')}", "INFO")
                    
                    # Verify fields are correct
                    if item.get('catalog_item_id') == catalog_item['id']:
                        self.log("✅ Maklon PO item fields verified correctly", "PASS")
                        return True, po_id
                    else:
                        self.log("❌ Maklon PO item fields mismatch", "FAIL")
                        self.failures.append("Maklon PO item fields mismatch")
                        return False, None
            
            return True, po_id
        
        return False, None

    def test_internal_po_edit(self):
        """Test 5: Edit existing internal PO"""
        self.log("=" * 60)
        self.log("TEST 5: Internal PO Edit (Regression)")
        self.log("=" * 60)
        
        # Get existing internal POs
        self.log("Fetching existing internal POs...")
        success, pos_data = self.run_test(
            "GET /api/production-pos?business_type=internal",
            "GET",
            "production-pos?business_type=internal",
            200
        )
        
        if not success:
            self.log("Failed to fetch internal POs", "ERROR")
            return False
        
        # Extract POs from response
        pos = []
        if isinstance(pos_data, dict):
            if 'items' in pos_data:
                pos = pos_data['items']
            elif 'data' in pos_data:
                pos = pos_data['data']
        elif isinstance(pos_data, list):
            pos = pos_data
        
        # Find a demo PO
        demo_po = None
        for po in pos:
            po_num = po.get('po_number', '')
            if 'DEMO' in po_num.upper() or 'INT' in po_num.upper():
                demo_po = po
                break
        
        if not demo_po:
            self.log("No demo internal PO found to edit", "WARN")
            return True  # Not a failure, just skip
        
        po_id = demo_po['id']
        self.log(f"Editing PO: {demo_po.get('po_number')} (ID: {po_id})", "INFO")
        
        # Get full PO detail
        success, po_detail = self.run_test(
            f"GET PO detail for edit",
            "GET",
            f"production-pos/{po_id}",
            200
        )
        
        if not success:
            return False
        
        # Update PO (just change notes)
        update_data = {
            "notes": f"Updated by regression test at {datetime.now().isoformat()}"
        }
        
        success, response = self.run_test(
            "PUT /api/production-pos/{id} (edit)",
            "PUT",
            f"production-pos/{po_id}",
            200,
            data=update_data
        )
        
        if success:
            self.log("✅ PO edit successful (null-guarded legacy lookup worked)", "PASS")
            return True
        
        return False

    def test_list_internal_pos(self):
        """Test 6: List internal POs"""
        self.log("=" * 60)
        self.log("TEST 6: List Internal POs")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "GET /api/production-pos?business_type=internal",
            "GET",
            "production-pos?business_type=internal",
            200
        )
        
        if success:
            # Extract items
            items = []
            if isinstance(response, dict):
                if 'items' in response:
                    items = response['items']
                elif 'data' in response:
                    items = response['data']
            elif isinstance(response, list):
                items = response
            
            self.log(f"Found {len(items)} internal POs", "INFO")
            
            # Show first 3
            for i, po in enumerate(items[:3]):
                self.log(f"  {i+1}. {po.get('po_number')} - {po.get('customer_name')} ({po.get('status')})", "INFO")
            
            return True
        
        return False

    def test_list_maklon_pos(self):
        """Test 7: List maklon POs"""
        self.log("=" * 60)
        self.log("TEST 7: List Maklon POs")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "GET /api/production-pos?business_type=maklon",
            "GET",
            "production-pos?business_type=maklon",
            200
        )
        
        if success:
            # Extract items
            items = []
            if isinstance(response, dict):
                if 'items' in response:
                    items = response['items']
                elif 'data' in response:
                    items = response['data']
            elif isinstance(response, list):
                items = response
            
            self.log(f"Found {len(items)} maklon POs", "INFO")
            
            # Show first 3
            for i, po in enumerate(items[:3]):
                self.log(f"  {i+1}. {po.get('po_number')} - {po.get('customer_name')} ({po.get('status')})", "INFO")
            
            return True
        
        return False

    def run_all_tests(self):
        """Run all regression tests"""
        self.log("=" * 60)
        self.log("FASE 4 LEGACY CLEANUP REGRESSION TEST")
        self.log("CV. Dewi Aditya ERP - Production PO Module")
        self.log("=" * 60)
        self.log(f"Backend URL: {self.base_url}")
        self.log("")
        
        # Test 1: Authentication
        if not self.test_auth_login():
            self.log("Authentication failed, stopping tests", "ERROR")
            return False
        
        # Test role accounts
        self.test_role_accounts_login()
        
        # Test 2: Deprecated endpoints
        self.test_deprecated_endpoints()
        
        # Test 3: Internal PO create
        self.test_internal_po_create()
        
        # Test 4: Maklon PO create
        self.test_maklon_po_create()
        
        # Test 5: Internal PO edit
        self.test_internal_po_edit()
        
        # Test 6: List internal POs
        self.test_list_internal_pos()
        
        # Test 7: List maklon POs
        self.test_list_maklon_pos()
        
        return True

    def print_summary(self):
        """Print test summary"""
        self.log("")
        self.log("=" * 60)
        self.log("TEST SUMMARY")
        self.log("=" * 60)
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}")
        self.log(f"Failed: {self.tests_failed}")
        self.log(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%" if self.tests_run > 0 else "N/A")
        
        if self.failures:
            self.log("")
            self.log("FAILURES:")
            for i, failure in enumerate(self.failures, 1):
                self.log(f"  {i}. {failure}", "FAIL")
        
        self.log("=" * 60)
        
        return self.tests_failed == 0

def main():
    tester = Fase4RegressionTest()
    tester.run_all_tests()
    success = tester.print_summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
