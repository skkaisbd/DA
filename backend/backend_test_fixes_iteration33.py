#!/usr/bin/env python3
"""
Backend Test for Iteration 33 - Verification of 5 Fixes
========================================================
Tests all fixes from iteration_32 follow-up:
1. FIX 1: GET /api/rahaza/ar-aging routing (was wired to bad-debt write-off)
2. FIX 1b: Honest aging bucket (tanpa_jatuh_tempo) for null/invalid due dates
3. FIX 2: Pydantic money coercion in BOM templates (Indonesian format)
4. FIX 3: Money parser SSOT (utils/money.py)
5. FIX 4: Guardrail script for dangling decorators
6. FIX 5: GRN-QC supplier scorecard endpoints
7. REGRESSIONS: Quarantine flow, order validation, AI endpoints
"""
import requests
import sys
import os
from datetime import datetime, date
from pymongo import MongoClient

# Backend URL from environment
BASE_URL = os.getenv("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com")
API_BASE = f"{BASE_URL}/api"

# MongoDB connection
MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017/")
DB_NAME = os.getenv("DB_NAME", "test_database")

class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.token = None
        self.mongo_client = None
        self.db = None
        self.test_artifacts = []  # Track items to clean up
        
    def setup_mongo(self):
        """Connect to MongoDB for direct data manipulation"""
        try:
            self.mongo_client = MongoClient(MONGO_URL)
            self.db = self.mongo_client[DB_NAME]
            print("✓ MongoDB connection established")
            return True
        except Exception as e:
            print(f"✗ MongoDB connection failed: {e}")
            return False
    
    def cleanup_mongo(self):
        """Close MongoDB connection"""
        if self.mongo_client:
            self.mongo_client.close()
    
    def login(self, email, password):
        """Login and get token"""
        try:
            response = requests.post(
                f"{API_BASE}/auth/login",
                json={"email": email, "password": password},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                print(f"✓ Logged in as {email}")
                return True
            else:
                print(f"✗ Login failed: {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Login error: {e}")
            return False
    
    def headers(self):
        """Get auth headers"""
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}
    
    def test(self, name, method, endpoint, expected_status, data=None, params=None, check_fn=None):
        """Run a single API test"""
        self.tests_run += 1
        url = f"{API_BASE}/{endpoint}"
        
        print(f"\n🔍 Test {self.tests_run}: {name}")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=self.headers(), params=params, timeout=15)
            elif method == "POST":
                response = requests.post(url, json=data, headers=self.headers(), timeout=15)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=self.headers(), timeout=15)
            elif method == "DELETE":
                response = requests.delete(url, headers=self.headers(), timeout=15)
            else:
                print(f"✗ Unknown method: {method}")
                return False
            
            # Check status code
            if response.status_code != expected_status:
                print(f"✗ FAILED - Expected {expected_status}, got {response.status_code}")
                print(f"  Response: {response.text[:200]}")
                return False
            
            # Run custom check function if provided
            if check_fn:
                try:
                    response_data = response.json() if response.text else {}
                except Exception:
                    response_data = {}
                
                result = check_fn(response_data)
                if not result:
                    print(f"✗ FAILED - Custom check failed")
                    return False
            
            self.tests_passed += 1
            print(f"✅ PASSED - Status: {response.status_code}")
            return True
            
        except Exception as e:
            print(f"✗ FAILED - Error: {str(e)}")
            return False
    
    def cleanup_test_data(self):
        """Clean up all test artifacts"""
        print(f"\n🧹 Cleaning up {len(self.test_artifacts)} test artifacts...")
        for artifact in self.test_artifacts:
            try:
                collection = artifact.get("collection")
                query = artifact.get("query")
                if collection and query:
                    result = self.db[collection].delete_many(query)
                    print(f"  ✓ Deleted {result.deleted_count} from {collection}")
            except Exception as e:
                print(f"  ✗ Cleanup error: {e}")
    
    def summary(self):
        """Print test summary"""
        print(f"\n{'='*60}")
        print(f"📊 Test Summary")
        print(f"{'='*60}")
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print(f"{'='*60}")
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    runner = TestRunner()
    
    # Setup
    print("="*60)
    print("Backend Test - Iteration 33 Fixes Verification")
    print("="*60)
    
    if not runner.setup_mongo():
        return 1
    
    # Login as admin
    if not runner.login("admin@garment.com", "Admin@123"):
        return 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 1: GET /api/rahaza/ar-aging routing fix
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("FIX 1: AR Aging Endpoint Routing")
    print("="*60)
    
    # Count journal entries before
    journal_count_before = runner.db.rahaza_journal_entries.count_documents({})
    
    # Test 1a: GET /ar-aging returns 200 with NO query params required
    def check_ar_aging(data):
        if "buckets" not in data:
            print("  ✗ Missing 'buckets' key")
            return False
        if "total" not in data:
            print("  ✗ Missing 'total' key")
            return False
        if "details" not in data:
            print("  ✗ Missing 'details' key")
            return False
        if "data_quality" not in data:
            print("  ✗ Missing 'data_quality' key")
            return False
        
        # Check for 6 buckets including new tanpa_jatuh_tempo
        buckets = data["buckets"]
        required_buckets = ["current", "1_30", "31_60", "61_90", "90_plus", "tanpa_jatuh_tempo"]
        for bucket in required_buckets:
            if bucket not in buckets:
                print(f"  ✗ Missing bucket: {bucket}")
                return False
        
        print(f"  ✓ All 6 buckets present: {list(buckets.keys())}")
        print(f"  ✓ Total: {data['total']}")
        return True
    
    runner.test(
        "GET /ar-aging returns 200 with all buckets",
        "GET", "rahaza/ar-aging", 200,
        check_fn=check_ar_aging
    )
    
    # Test 1b: Verify NO journal entries were created by GET call
    journal_count_after = runner.db.rahaza_journal_entries.count_documents({})
    runner.tests_run += 1
    if journal_count_before == journal_count_after:
        runner.tests_passed += 1
        print(f"\n🔍 Test {runner.tests_run}: GET /ar-aging does NOT create journal entries")
        print(f"✅ PASSED - Journal count unchanged: {journal_count_before}")
    else:
        print(f"\n🔍 Test {runner.tests_run}: GET /ar-aging does NOT create journal entries")
        print(f"✗ FAILED - Journal count changed: {journal_count_before} → {journal_count_after}")
    
    # Test 1c: POST /ar-invoices/{iid}/write-off-bad-debt still exists
    # (We won't actually call it, just verify GET on that path returns 405)
    runner.test(
        "GET on write-off endpoint returns 405 (POST-only)",
        "GET", "rahaza/ar-invoices/dummy-id/write-off-bad-debt", 405
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 1b: Honest aging bucket for null/invalid due dates
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("FIX 1b: Honest Aging Bucket (tanpa_jatuh_tempo)")
    print("="*60)
    
    # Insert test invoices directly into MongoDB
    test_invoice_1 = {
        "id": f"test-ar-null-{datetime.now().strftime('%H%M%S')}",
        "invoice_number": f"TEST-NULL-{datetime.now().strftime('%H%M%S')}",
        "customer_id": "test-customer",
        "status": "sent",
        "due_date": None,  # NULL due date
        "total": 7500000,
        "paid_amount": 0,
        "balance": 7500000,
        "created_at": datetime.utcnow()
    }
    
    test_invoice_2 = {
        "id": f"test-ar-invalid-{datetime.now().strftime('%H%M%S')}",
        "invoice_number": f"TEST-INVALID-{datetime.now().strftime('%H%M%S')}",
        "customer_id": "test-customer",
        "status": "sent",
        "due_date": "31/12/2026",  # Invalid format (DD/MM/YYYY instead of YYYY-MM-DD)
        "total": 7500000,
        "paid_amount": 0,
        "balance": 7500000,
        "created_at": datetime.utcnow()
    }
    
    try:
        runner.db.rahaza_ar_invoices.insert_one(test_invoice_1)
        runner.db.rahaza_ar_invoices.insert_one(test_invoice_2)
        print(f"✓ Inserted 2 test AR invoices")
        
        # Track for cleanup
        runner.test_artifacts.append({
            "collection": "rahaza_ar_invoices",
            "query": {"id": {"$in": [test_invoice_1["id"], test_invoice_2["id"]]}}
        })
        
        # Get AR aging report
        response = requests.get(
            f"{API_BASE}/rahaza/ar-aging",
            headers=runner.headers(),
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            buckets = data.get("buckets", {})
            tanpa_jatuh_tempo = buckets.get("tanpa_jatuh_tempo", 0)
            current = buckets.get("current", 0)
            total = data.get("total", 0)
            data_quality = data.get("data_quality", {})
            
            runner.tests_run += 1
            print(f"\n🔍 Test {runner.tests_run}: Invoices with null/invalid due_date go to tanpa_jatuh_tempo")
            
            # Check that tanpa_jatuh_tempo has at least our 15M (7.5M * 2)
            if tanpa_jatuh_tempo >= 15000000:
                runner.tests_passed += 1
                print(f"✅ PASSED - tanpa_jatuh_tempo: {tanpa_jatuh_tempo:,.0f} (includes our 15M)")
            else:
                print(f"✗ FAILED - tanpa_jatuh_tempo: {tanpa_jatuh_tempo:,.0f} (expected >= 15M)")
            
            # Check data_quality reports the issues
            runner.tests_run += 1
            print(f"\n🔍 Test {runner.tests_run}: data_quality reports skipped invoices")
            
            dilewati = data_quality.get("dilewati", 0)
            if dilewati >= 2:
                runner.tests_passed += 1
                print(f"✅ PASSED - data_quality.dilewati: {dilewati} (includes our 2 test invoices)")
                print(f"  Details: {data_quality.get('detail', [])[:3]}")
            else:
                print(f"✗ FAILED - data_quality.dilewati: {dilewati} (expected >= 2)")
        
        # Cleanup test invoices
        runner.db.rahaza_ar_invoices.delete_many({"id": {"$in": [test_invoice_1["id"], test_invoice_2["id"]]}})
        print(f"✓ Cleaned up test AR invoices")
        
    except Exception as e:
        print(f"✗ Test setup error: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 2: Pydantic money coercion in BOM templates
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("FIX 2: BOM Template Money Parsing (Indonesian Format)")
    print("="*60)
    
    # Test 2a: Indonesian format "85.000" becomes 85000.0 (not 85.0)
    bom_payload_indonesian = {
        "buyer_catalog_id": "mk-cat-demo-hoodie",
        "version_label": "Test Indonesian Format",
        "materials": [
            {
                "material_name": "Test Fabric",
                "unit": "meter",
                "qty_per_pcs": "0.600",  # 0.6 meter (not 600!)
                "cost_per_unit": "85.000",  # 85,000 IDR (not 85!)
                "category": "fabric"
            }
        ],
        "set_active": False
    }
    
    def check_bom_indonesian(data):
        item = data.get("item", {})
        materials = item.get("materials", [])
        if not materials:
            print("  ✗ No materials in response")
            return False
        
        mat = materials[0]
        qty = mat.get("qty_per_pcs")
        cost = mat.get("cost_per_unit")
        total_cost = item.get("total_cost_per_pcs")
        
        print(f"  qty_per_pcs: {qty} (expected 0.6)")
        print(f"  cost_per_unit: {cost} (expected 85000.0)")
        print(f"  total_cost_per_pcs: {total_cost} (expected 51000.0)")
        
        # Check values
        if abs(qty - 0.6) > 0.01:
            print(f"  ✗ qty_per_pcs wrong: {qty} != 0.6")
            return False
        if abs(cost - 85000.0) > 1:
            print(f"  ✗ cost_per_unit wrong: {cost} != 85000.0")
            return False
        if abs(total_cost - 51000.0) > 1:
            print(f"  ✗ total_cost_per_pcs wrong: {total_cost} != 51000.0")
            return False
        
        # Track for cleanup
        runner.test_artifacts.append({
            "collection": "dewi_maklon_bom_templates",
            "query": {"id": item.get("id")}
        })
        
        return True
    
    runner.test(
        "POST BOM with Indonesian format (85.000 → 85000.0)",
        "POST", "dewi/maklon/bom-templates", 201,
        data=bom_payload_indonesian,
        check_fn=check_bom_indonesian
    )
    
    # Test 2b: Invalid string returns 422 with clear message
    bom_payload_invalid = {
        "buyer_catalog_id": "mk-cat-demo-hoodie",
        "materials": [
            {
                "material_name": "Test Invalid",
                "unit": "pcs",
                "qty_per_pcs": 1,
                "cost_per_unit": "mahal sekali",  # Invalid!
                "category": "accessories"
            }
        ],
        "set_active": False
    }
    
    runner.test(
        "POST BOM with invalid cost returns 422",
        "POST", "dewi/maklon/bom-templates", 422,
        data=bom_payload_invalid
    )
    
    # Test 2c: Plain JSON numbers still work (regression check)
    bom_payload_json = {
        "buyer_catalog_id": "mk-cat-demo-hoodie",
        "materials": [
            {
                "material_name": "Test JSON Numbers",
                "unit": "pcs",
                "qty_per_pcs": 4,
                "cost_per_unit": 250,
                "category": "accessories"
            }
        ],
        "set_active": False
    }
    
    def check_bom_json(data):
        item = data.get("item", {})
        total_cost = item.get("total_cost_per_pcs")
        expected = 4 * 250  # 1000
        
        if abs(total_cost - expected) > 1:
            print(f"  ✗ total_cost_per_pcs: {total_cost} != {expected}")
            return False
        
        # Track for cleanup
        runner.test_artifacts.append({
            "collection": "dewi_maklon_bom_templates",
            "query": {"id": item.get("id")}
        })
        
        return True
    
    runner.test(
        "POST BOM with plain JSON numbers still works",
        "POST", "dewi/maklon/bom-templates", 201,
        data=bom_payload_json,
        check_fn=check_bom_json
    )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 3: Money parser SSOT verification
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("FIX 3: Money Parser SSOT (utils/money.py)")
    print("="*60)
    
    # Direct import test
    try:
        sys.path.insert(0, '/app/backend')
        from utils.money import parse_id_number
        
        test_cases = [
            ("85.000", 85000.0),
            ("1.250.000", 1250000.0),
            ("1.234.567,89", 1234567.89),
            ("150,5", 150.5),
            ("0.600", 0.6),  # Critical fix!
            ("0.6", 0.6),
            ("1.5", 1.5),
            ("150.75", 150.75),
            ("85000", 85000.0),
            ("Rp 1.500.000", 1500000.0),
            ("(1.000)", -1000.0),
        ]
        
        for input_val, expected in test_cases:
            runner.tests_run += 1
            try:
                result = parse_id_number(input_val)
                if abs(result - expected) < 0.01:
                    runner.tests_passed += 1
                    print(f"\n🔍 Test {runner.tests_run}: parse_id_number('{input_val}')")
                    print(f"✅ PASSED - Result: {result} (expected {expected})")
                else:
                    print(f"\n🔍 Test {runner.tests_run}: parse_id_number('{input_val}')")
                    print(f"✗ FAILED - Result: {result} != {expected}")
            except Exception as e:
                print(f"\n🔍 Test {runner.tests_run}: parse_id_number('{input_val}')")
                print(f"✗ FAILED - Error: {e}")
        
    except Exception as e:
        print(f"✗ Import error: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 4: Guardrail script verification
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("FIX 4: Guardrail Script (verify_unreachable_code.py)")
    print("="*60)
    
    # Test 4a: Self-test passes
    import subprocess
    
    runner.tests_run += 1
    try:
        result = subprocess.run(
            ["python3", "/app/scripts/guardrails/verify_unreachable_code.py", "--self-test"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if "LULUS" in result.stdout and result.returncode == 0:
            runner.tests_passed += 1
            print(f"\n🔍 Test {runner.tests_run}: Guardrail self-test")
            print(f"✅ PASSED - Self-test LULUS")
        else:
            print(f"\n🔍 Test {runner.tests_run}: Guardrail self-test")
            print(f"✗ FAILED - Self-test did not pass")
            print(f"  Output: {result.stdout[:200]}")
    except Exception as e:
        print(f"\n🔍 Test {runner.tests_run}: Guardrail self-test")
        print(f"✗ FAILED - Error: {e}")
    
    # Test 4b: Actual check exits 0 (no dangling decorators found)
    runner.tests_run += 1
    try:
        result = subprocess.run(
            ["python3", "/app/scripts/guardrails/verify_unreachable_code.py"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Check for exit code 0 and HIJAU (green/pass)
        if result.returncode == 0 and "HIJAU" in result.stdout:
            runner.tests_passed += 1
            print(f"\n🔍 Test {runner.tests_run}: Guardrail actual check")
            print(f"✅ PASSED - Exit code 0, HIJAU (no blocking violations)")
        else:
            print(f"\n🔍 Test {runner.tests_run}: Guardrail actual check")
            print(f"✗ FAILED - Exit code: {result.returncode}")
            print(f"  Output: {result.stdout[:300]}")
    except Exception as e:
        print(f"\n🔍 Test {runner.tests_run}: Guardrail actual check")
        print(f"✗ FAILED - Error: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FIX 5: GRN-QC supplier scorecard endpoints
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("FIX 5: GRN-QC Supplier Scorecard Endpoints")
    print("="*60)
    
    # Test 5a: LIST endpoint returns array (no data_quality required)
    def check_scorecard_list(data):
        if not isinstance(data, list):
            print(f"  ✗ Response is not an array: {type(data)}")
            return False
        print(f"  ✓ Response is array with {len(data)} items")
        return True
    
    runner.test(
        "GET /grn-qc/supplier-scorecard (list) returns array",
        "GET", "rahaza/grn-qc/supplier-scorecard", 200,
        check_fn=check_scorecard_list
    )
    
    # Test 5b: DETAIL endpoint has data_quality
    # First, get a supplier name from the list
    try:
        response = requests.get(
            f"{API_BASE}/rahaza/grn-qc/supplier-scorecard",
            headers=runner.headers(),
            timeout=15
        )
        
        if response.status_code == 200:
            suppliers = response.json()
            if suppliers and len(suppliers) > 0:
                supplier_name = suppliers[0].get("supplier_name")
                
                if supplier_name:
                    def check_scorecard_detail(data):
                        if "data_quality" not in data:
                            print("  ✗ Missing 'data_quality' field")
                            return False
                        print(f"  ✓ data_quality present: {data['data_quality']}")
                        return True
                    
                    runner.test(
                        f"GET /grn-qc/supplier-scorecard/{supplier_name} has data_quality",
                        "GET", f"rahaza/grn-qc/supplier-scorecard/{supplier_name}", 200,
                        check_fn=check_scorecard_detail
                    )
                else:
                    print("  ⚠ No supplier_name in first item, skipping detail test")
            else:
                print("  ⚠ No suppliers in list, skipping detail test")
    except Exception as e:
        print(f"  ⚠ Could not test detail endpoint: {e}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # REGRESSIONS: Must still pass
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "="*60)
    print("REGRESSION TESTS")
    print("="*60)
    
    # Regression 1: Quarantine summary
    def check_quarantine_summary(data):
        required_keys = ["unblocked_items", "unblocked_qty", "unblocked_groups"]
        for key in required_keys:
            if key not in data:
                print(f"  ✗ Missing key: {key}")
                return False
        print(f"  ✓ All new keys present: {required_keys}")
        return True
    
    runner.test(
        "GET /wms/quarantine/summary has new keys",
        "GET", "wms/quarantine/summary", 200,
        check_fn=check_quarantine_summary
    )
    
    # Regression 2: Order validation (non-numeric qty returns 400)
    order_payload_invalid = {
        "customer_name": "Test Customer",
        "items": [
            {
                "product_name": "Test Product",
                "qty": "abc",  # Invalid!
                "unit_price": 1000
            }
        ]
    }
    
    runner.test(
        "POST /rahaza/orders with non-numeric qty returns 400",
        "POST", "rahaza/orders", 400,
        data=order_payload_invalid
    )
    
    # Regression 3: Valid order still works
    order_payload_valid = {
        "customer_name": "Test Customer",
        "items": [
            {
                "product_name": "Test Product",
                "qty": 10,
                "unit_price": 1000
            }
        ]
    }
    
    def check_order_created(data):
        if "id" not in data:
            print("  ✗ No order ID in response")
            return False
        
        # Track for cleanup
        runner.test_artifacts.append({
            "collection": "rahaza_orders",
            "query": {"id": data.get("id")}
        })
        
        return True
    
    runner.test(
        "POST /rahaza/orders with valid data returns 200",
        "POST", "rahaza/orders", 200,
        data=order_payload_valid,
        check_fn=check_order_created
    )
    
    # Regression 4: AI predictive delay has data_quality (NO LLM required)
    def check_ai_data_quality(data):
        if "data_quality" not in data:
            print("  ✗ Missing 'data_quality' field")
            return False
        print(f"  ✓ data_quality present")
        return True
    
    runner.test(
        "GET /rahaza/ai/predictive-delay has data_quality",
        "GET", "rahaza/ai/predictive-delay", 200,
        check_fn=check_ai_data_quality
    )
    
    # Regression 5: Management alerts has data_quality
    runner.test(
        "GET /rahaza/management/alerts has data_quality",
        "GET", "rahaza/management/alerts", 200,
        check_fn=check_ai_data_quality
    )
    
    # Cleanup
    runner.cleanup_test_data()
    runner.cleanup_mongo()
    
    # Summary
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
