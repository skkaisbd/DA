"""
Backend API Testing — KEPUTUSAN #1, #2, #5
CV. Dewi Aditya ERP — Marketing Portal Business Decisions

Tests:
1. KEP#1: AR disabled (Sales→AR bridge OFF, Finance AR/Journals intact)
2. KEP#2: Catalog pricing (4 fields: harga_jual/coret/original, hpp from RnD)
3. KEP#2: RnD HPP BOM calculator (auto-cost from BOM × unit_cost)
4. KEP#5: Budget per store × month × category (ads/kol/livehost/sample/diskon)
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

class KEPTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.passed_tests = []
        
    def log(self, msg: str, level: str = "INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")
    
    def test(self, name: str, method: str, endpoint: str, expected_status: int, 
             data=None, params=None, check_detail_code=None, check_fields=None) -> tuple:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}{endpoint}"
        
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        
        self.log(f"Testing: {name}", "TEST")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=headers, params=params, timeout=15)
            elif method == "POST":
                response = requests.post(url, headers=headers, json=data, timeout=15)
            elif method == "PUT":
                response = requests.put(url, headers=headers, json=data, timeout=15)
            elif method == "DELETE":
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                self.log(f"❌ FAILED - Unknown method: {method}", "ERROR")
                self.tests_failed += 1
                self.failed_tests.append({"test": name, "reason": f"Unknown method: {method}"})
                return False, {}
            
            success = response.status_code == expected_status
            
            if not success:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    err_detail = response.json()
                    self.log(f"   Response: {json.dumps(err_detail, indent=2)}", "DEBUG")
                except:
                    self.log(f"   Response text: {response.text[:200]}", "DEBUG")
                self.failed_tests.append({"test": name, "reason": f"Status {response.status_code} != {expected_status}"})
                return False, {}
            
            # Additional checks
            try:
                json_data = response.json() if response.text else {}
                
                # Check detail.code if specified
                if check_detail_code:
                    detail = json_data.get('detail', {})
                    if isinstance(detail, dict):
                        code = detail.get('code')
                        if code != check_detail_code:
                            success = False
                            self.log(f"❌ FAILED - Expected detail.code='{check_detail_code}', got '{code}'", "FAIL")
                            self.tests_failed += 1
                            self.failed_tests.append({"test": name, "reason": f"detail.code mismatch"})
                            return False, json_data
                
                # Check required fields
                if check_fields:
                    for field in check_fields:
                        if field not in json_data:
                            success = False
                            self.log(f"❌ FAILED - Missing required field: {field}", "FAIL")
                            self.tests_failed += 1
                            self.failed_tests.append({"test": name, "reason": f"Missing field: {field}"})
                            return False, json_data
                
                if success:
                    self.tests_passed += 1
                    self.log(f"✅ PASSED - Status: {response.status_code}", "PASS")
                    self.passed_tests.append(name)
                    return True, json_data
                    
            except Exception as e:
                if success:
                    self.tests_passed += 1
                    self.log(f"✅ PASSED - Status: {response.status_code}", "PASS")
                    self.passed_tests.append(name)
                    return True, {}
                else:
                    self.tests_failed += 1
                    self.log(f"❌ FAILED - Exception: {str(e)}", "ERROR")
                    self.failed_tests.append({"test": name, "reason": str(e)})
                    return False, {}
                    
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAILED - Exception: {str(e)}", "ERROR")
            self.failed_tests.append({"test": name, "reason": str(e)})
            return False, {}
    
    def login(self):
        """Login as admin"""
        self.log("=== AUTHENTICATION ===", "INFO")
        success, data = self.test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if success and 'token' in data:
            self.token = data['token']
            self.log(f"✅ Logged in as {ADMIN_EMAIL}", "INFO")
            return True
        else:
            self.log("❌ Login failed", "ERROR")
            return False
    
    def test_kep1_ar_disabled(self):
        """KEP#1: AR disabled — Sales→AR bridge OFF"""
        self.log("\n=== KEP#1: AR DISABLED (Sales→AR Bridge OFF) ===", "INFO")
        
        # 1. Get an account_id
        success, data = self.test(
            "Get marketing accounts",
            "GET",
            "/api/marketing/accounts",
            200,
            params={"status": "active"}
        )
        accounts = data if isinstance(data, list) else data.get('accounts', [])
        if not success or not accounts:
            self.log("⚠️  No marketing accounts found, skipping AR test", "WARN")
            return
        
        account_id = accounts[0]['id']
        self.log(f"Using account_id: {account_id}", "DEBUG")
        
        # 2. Test generate-ar-batch returns 410 with MARKETING_AR_DISABLED
        success, data = self.test(
            "KEP#1: POST /sales-data/generate-ar-batch returns 410",
            "POST",
            "/api/marketing/sales-data/generate-ar-batch",
            410,
            data={
                "date_from": "2025-08-01",
                "date_to": "2025-08-31",
                "account_id": account_id,
                "revenue_type": "total",
                "grouping": "daily"
            },
            check_detail_code="MARKETING_AR_DISABLED"
        )
        
        # 3. Verify Finance AR still works
        self.test(
            "KEP#1: Finance AR invoices still accessible (GET /rahaza/ar-invoices)",
            "GET",
            "/api/rahaza/ar-invoices",
            200
        )
        
        # 4. Verify Journals still work
        self.test(
            "KEP#1: Finance journals still accessible (GET /rahaza/journals)",
            "GET",
            "/api/rahaza/journals",
            200
        )
        
        # 5. Verify sales-data creation still works
        self.test(
            "KEP#1: Sales data creation still works (POST /sales-data)",
            "POST",
            "/api/marketing/sales-data",
            200,
            data={
                "account_id": account_id,
                "date": "2025-08-15",
                "revenue_type": "total",
                "revenue": 5000000,
                "orders": 50,
                "aov": 100000
            }
        )
    
    def test_kep2_catalog_pricing(self):
        """KEP#2: Catalog pricing — 4 separate price fields"""
        self.log("\n=== KEP#2: CATALOG PRICING (4 Fields: jual/coret/original, hpp) ===", "INFO")
        
        # 1. Get or create a catalog
        success, data = self.test(
            "Get marketing accounts for catalog",
            "GET",
            "/api/marketing/accounts",
            200,
            params={"status": "active"}
        )
        accounts = data if isinstance(data, list) else data.get('accounts', [])
        if not success or not accounts:
            self.log("⚠️  No marketing accounts found, skipping catalog test", "WARN")
            return
        
        account_id = accounts[0]['id']
        
        # Get existing catalogs
        success, data = self.test(
            "Get existing catalogs",
            "GET",
            "/api/marketing/catalogs",
            200,
            params={"account_id": account_id}
        )
        
        catalog_id = None
        if success and data.get('catalogs') and len(data['catalogs']) > 0:
            catalog_id = data['catalogs'][0]['id']
            self.log(f"Using existing catalog_id: {catalog_id}", "DEBUG")
        else:
            # Create a catalog
            success, data = self.test(
                "Create test catalog",
                "POST",
                "/api/marketing/catalogs",
                200,
                data={
                    "account_id": account_id,
                    "name": f"Test Catalog KEP2 {datetime.now().strftime('%H%M%S')}",
                    "description": "Test catalog for KEP#2 pricing",
                    "is_active": True
                }
            )
            if success and data.get('catalog'):
                catalog_id = data['catalog']['id']
                self.log(f"Created catalog_id: {catalog_id}", "DEBUG")
        
        if not catalog_id:
            self.log("❌ Failed to get/create catalog", "ERROR")
            return
        
        # 2. Create catalog item with 4 price fields
        success, data = self.test(
            "KEP#2: Create catalog item with 4 price fields",
            "POST",
            f"/api/marketing/catalogs/{catalog_id}/items",
            201,
            data={
                "sku": f"TEST-KEP2-{datetime.now().strftime('%H%M%S')}",
                "name": "Test Product KEP2",
                "harga_jual": 150000,
                "harga_coret": 180000,
                "harga_original": 200000,
                "stock_quantity": 10,
                "stock_alert_threshold": 5
            }
        )
        
        if not success or not data.get('item'):
            self.log("❌ Failed to create catalog item", "ERROR")
            return
        
        item_id = data['item']['id']
        self.log(f"Created item_id: {item_id}", "DEBUG")
        
        # 3. GET item and verify all 4 price fields + legacy mirror
        success, data = self.test(
            "KEP#2: GET catalog items and verify pricing fields",
            "GET",
            f"/api/marketing/catalogs/{catalog_id}/items",
            200
        )
        
        if success and data.get('items'):
            item = next((i for i in data['items'] if i['id'] == item_id), None)
            if item:
                # Check kanonik fields
                assert item.get('harga_jual') == 150000, f"harga_jual mismatch: {item.get('harga_jual')}"
                assert item.get('harga_coret') == 180000, f"harga_coret mismatch: {item.get('harga_coret')}"
                assert item.get('harga_original') == 200000, f"harga_original mismatch: {item.get('harga_original')}"
                assert 'hpp' in item, "hpp field missing"
                assert item.get('hpp') >= 0, f"hpp should be >= 0, got {item.get('hpp')}"
                
                # Check legacy mirror
                assert item.get('price') == 150000, f"legacy price mismatch: {item.get('price')}"
                assert item.get('original_price') == 180000, f"legacy original_price mismatch: {item.get('original_price')}"
                
                self.log(f"✅ All pricing fields verified: jual={item['harga_jual']}, coret={item['harga_coret']}, original={item['harga_original']}, hpp={item['hpp']}", "PASS")
                self.tests_passed += 1
                self.passed_tests.append("KEP#2: Pricing fields verification")
            else:
                self.log("❌ Item not found in response", "ERROR")
                self.tests_failed += 1
                self.failed_tests.append({"test": "KEP#2: Pricing fields verification", "reason": "Item not found"})
        
        # 4. Update item and verify persistence
        success, data = self.test(
            "KEP#2: Update item harga_jual to 160000",
            "PUT",
            f"/api/marketing/catalogs/{catalog_id}/items/{item_id}",
            200,
            data={"harga_jual": 160000}
        )
        
        if success and data.get('item'):
            assert data['item'].get('harga_jual') == 160000, f"Updated harga_jual mismatch: {data['item'].get('harga_jual')}"
            assert data['item'].get('price') == 160000, f"Updated legacy price mismatch: {data['item'].get('price')}"
            self.log(f"✅ Update persisted: harga_jual={data['item']['harga_jual']}", "PASS")
    
    def test_kep2_rnd_hpp_bom(self):
        """KEP#2: RnD HPP BOM calculator"""
        self.log("\n=== KEP#2: RnD HPP BOM CALCULATOR (Auto-cost from BOM) ===", "INFO")
        
        # Test compute-from-bom with sample BOM
        success, data = self.test(
            "KEP#2: POST /rnd/hpp-calculator/compute-from-bom",
            "POST",
            "/api/dewi/rnd/hpp-calculator/compute-from-bom",
            200,
            data={
                "bom_items": [
                    {"material_code": "X", "qty": 2, "unit_cost": 10000},
                    {"material_code": "Y", "qty": 1, "unit_cost": 5000}
                ],
                "cmt_cost_per_pcs": 5000,
                "cutting_cost_per_pcs": 1000,
                "packaging_cost_per_pcs": 500,
                "overhead_pct": 10,
                "margin_pct": 30
            }
        )
        
        if success:
            # Verify math: bom_material_cost = 2*10000 + 1*5000 = 25000
            expected_bom_cost = 25000
            actual_bom_cost = data.get('bom_material_cost', 0)
            assert actual_bom_cost == expected_bom_cost, f"bom_material_cost mismatch: expected {expected_bom_cost}, got {actual_bom_cost}"
            
            # Verify hpp_total = (25000 + 5000 + 1000 + 500) * 1.1 = 31500 * 1.1 = 34650
            # But rounding might differ, let's check the formula
            direct_cost = expected_bom_cost + 5000 + 1000 + 500  # 31500
            overhead_val = direct_cost * 0.1  # 3150
            expected_hpp = round(direct_cost + overhead_val, 2)  # 34650
            actual_hpp = data.get('hpp_total', 0)
            
            self.log(f"BOM cost: {actual_bom_cost}, HPP total: {actual_hpp}, Selling price proposal: {data.get('selling_price_proposal')}", "DEBUG")
            
            # Allow small rounding difference
            assert abs(actual_hpp - expected_hpp) < 1, f"hpp_total mismatch: expected ~{expected_hpp}, got {actual_hpp}"
            assert 'selling_price_proposal' in data, "selling_price_proposal missing"
            
            self.log(f"✅ BOM math verified: bom_cost={actual_bom_cost}, hpp={actual_hpp}", "PASS")
            self.tests_passed += 1
            self.passed_tests.append("KEP#2: RnD HPP BOM math verification")
    
    def test_kep5_budget(self):
        """KEP#5: Budget per store × month × category"""
        self.log("\n=== KEP#5: BUDGET (Store × Month × Category) ===", "INFO")
        
        # 1. Get an account
        success, data = self.test(
            "Get marketing accounts for budget",
            "GET",
            "/api/marketing/accounts",
            200,
            params={"status": "active"}
        )
        accounts = data if isinstance(data, list) else data.get('accounts', [])
        if not success or not accounts:
            self.log("⚠️  No marketing accounts found, skipping budget test", "WARN")
            return
        
        account_id = accounts[0]['id']
        period = datetime.now().strftime("%Y-%m")
        self.log(f"Using account_id: {account_id}, period: {period}", "DEBUG")
        
        # 2. PUT budget
        success, data = self.test(
            "KEP#5: PUT budget with 5 categories",
            "PUT",
            "/api/marketing/budget",
            200,
            data={
                "account_id": account_id,
                "period": period,
                "budget_by_category": {
                    "ads": 1000000,
                    "kol": 2000000,
                    "livehost": 1500000,
                    "sample": 500000,
                    "diskon": 800000
                }
            }
        )
        
        if success:
            assert data.get('total_budget') == 5800000, f"total_budget mismatch: {data.get('total_budget')}"
            self.log(f"✅ Budget saved: total={data.get('total_budget')}", "PASS")
        
        # 3. POST spend (ads)
        success, data = self.test(
            "KEP#5: POST spend (ads, 400000)",
            "POST",
            "/api/marketing/budget/spend",
            200,
            data={
                "account_id": account_id,
                "period": period,
                "category": "ads",
                "amount": 400000,
                "description": "Test ads spend"
            }
        )
        
        # 4. POST spend (diskon, over budget)
        success, data = self.test(
            "KEP#5: POST spend (diskon, 900000 — over budget)",
            "POST",
            "/api/marketing/budget/spend",
            200,
            data={
                "account_id": account_id,
                "period": period,
                "category": "diskon",
                "amount": 900000,
                "description": "Test diskon spend (over)"
            }
        )
        
        # 5. GET summary and verify
        success, data = self.test(
            "KEP#5: GET budget summary",
            "GET",
            "/api/marketing/budget/summary",
            200,
            params={"account_id": account_id, "period": period}
        )
        
        if success:
            categories = {c['category']: c for c in data.get('categories', [])}
            
            # Check ads: spend=400000, used_pct=40, status=under
            ads = categories.get('ads', {})
            assert ads.get('spend') == 400000, f"ads spend mismatch: {ads.get('spend')}"
            assert ads.get('used_pct') == 40, f"ads used_pct mismatch: {ads.get('used_pct')}"
            assert ads.get('status') == 'under', f"ads status mismatch: {ads.get('status')}"
            
            # Check diskon: spend=900000, status=over, remaining=-100000
            diskon = categories.get('diskon', {})
            assert diskon.get('spend') == 900000, f"diskon spend mismatch: {diskon.get('spend')}"
            assert diskon.get('status') == 'over', f"diskon status mismatch: {diskon.get('status')}"
            assert diskon.get('remaining') == -100000, f"diskon remaining mismatch: {diskon.get('remaining')}"
            
            # Check totals
            assert 'total_budget' in data, "total_budget missing"
            assert 'total_spend' in data, "total_spend missing"
            assert 'roi_pct' in data, "roi_pct missing"
            
            self.log(f"✅ Budget summary verified: ads under (40%), diskon over (-100k), ROI={data.get('roi_pct')}%", "PASS")
            self.tests_passed += 1
            self.passed_tests.append("KEP#5: Budget summary verification")
        
        # 6. GET KOL cost list
        success, data = self.test(
            "KEP#5: GET KOL cost list",
            "GET",
            "/api/marketing/budget/kol-cost",
            200,
            params={"account_id": account_id}
        )
        
        if success and data.get('creators'):
            creator = data['creators'][0]
            creator_id = creator['creator_id']
            self.log(f"Found creator: {creator.get('name')} ({creator_id})", "DEBUG")
            
            # 7. PUT KOL cost config
            success, data = self.test(
                "KEP#5: PUT KOL cost config (both: fee 500k + commission 10%)",
                "PUT",
                f"/api/marketing/budget/kol-cost/{creator_id}",
                200,
                data={
                    "fee_type": "both",
                    "fixed_fee": 500000,
                    "commission_pct": 10
                }
            )
            
            if success:
                cfg = data.get('cost_config', {})
                assert cfg.get('fee_type') == 'both', f"fee_type mismatch: {cfg.get('fee_type')}"
                assert cfg.get('fixed_fee') == 500000, f"fixed_fee mismatch: {cfg.get('fixed_fee')}"
                assert cfg.get('commission_pct') == 10, f"commission_pct mismatch: {cfg.get('commission_pct')}"
                self.log(f"✅ KOL cost config saved: {cfg}", "PASS")
        
        # 8. Test invalid category
        success, data = self.test(
            "KEP#5: POST spend with invalid category returns 400",
            "POST",
            "/api/marketing/budget/spend",
            400,
            data={
                "account_id": account_id,
                "period": period,
                "category": "invalid_category",
                "amount": 100000
            }
        )
    
    def run_all_tests(self):
        """Run all KEP tests"""
        self.log("=" * 80, "INFO")
        self.log("CV. DEWI ADITYA — KEP #1, #2, #5 BACKEND API TESTS", "INFO")
        self.log("=" * 80, "INFO")
        
        if not self.login():
            self.log("❌ Authentication failed, aborting tests", "ERROR")
            return False
        
        self.test_kep1_ar_disabled()
        self.test_kep2_catalog_pricing()
        self.test_kep2_rnd_hpp_bom()
        self.test_kep5_budget()
        
        # Summary
        self.log("\n" + "=" * 80, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 80, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"✅ Passed: {self.tests_passed}", "PASS")
        self.log(f"❌ Failed: {self.tests_failed}", "FAIL")
        
        if self.tests_failed > 0:
            self.log("\nFailed Tests:", "FAIL")
            for fail in self.failed_tests:
                self.log(f"  - {fail['test']}: {fail['reason']}", "FAIL")
        
        self.log("\nPassed Tests:", "PASS")
        for test in self.passed_tests:
            self.log(f"  - {test}", "PASS")
        
        return self.tests_failed == 0

if __name__ == "__main__":
    tester = KEPTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
