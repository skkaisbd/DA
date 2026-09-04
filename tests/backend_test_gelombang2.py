#!/usr/bin/env python3
"""
Backend Test - Gelombang 2: Reports Hub
Testing all 8 categories with real data verification
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

class ReportsHubTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def log(self, msg, level="INFO"):
        prefix = "✅" if level == "PASS" else "❌" if level == "FAIL" else "🔍"
        print(f"{prefix} {msg}")

    def test(self, name, condition, details=""):
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"PASS: {name}", "PASS")
            return True
        else:
            self.tests_failed += 1
            self.failures.append(f"{name}: {details}")
            self.log(f"FAIL: {name} - {details}", "FAIL")
            return False

    def login(self):
        """Login and get token"""
        self.log("Logging in as admin...")
        try:
            response = requests.post(
                f"{BASE_URL}/api/auth/login",
                json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                self.test("Login successful", self.token is not None, "No token received")
                return True
            else:
                self.test("Login successful", False, f"Status {response.status_code}")
                return False
        except Exception as e:
            self.test("Login successful", False, str(e))
            return False

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_categories_endpoint(self):
        """Test GET /api/rahaza/reports-hub/categories"""
        self.log("\n=== Testing Categories Endpoint ===")
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/reports-hub/categories",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test("Categories endpoint returns 200", response.status_code == 200,
                     f"Got {response.status_code}")
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            items = data.get("items", [])
            
            self.test("Categories response has 'items' key", "items" in data,
                     "Missing 'items' key")
            self.test("Returns 8 categories", len(items) == 8,
                     f"Got {len(items)} categories")
            
            # Check expected category IDs
            expected_ids = ["eksekutif", "produksi_internal", "maklon", "gudang",
                           "keuangan", "sdm", "rnd", "marketing"]
            actual_ids = [c.get("id") for c in items]
            
            for expected_id in expected_ids:
                self.test(f"Category '{expected_id}' exists",
                         expected_id in actual_ids,
                         f"Missing category: {expected_id}")
            
            # Check structure of first category
            if items:
                cat = items[0]
                self.test("Category has 'id' field", "id" in cat)
                self.test("Category has 'label' field", "label" in cat)
                self.test("Category has 'portal' field", "portal" in cat)
                self.test("Category has 'description' field", "description" in cat)
            
            return True
            
        except Exception as e:
            self.test("Categories endpoint accessible", False, str(e))
            return False

    def test_category_summary(self, category_id, expected_data):
        """Test GET /api/rahaza/reports-hub/summary?category=<id>"""
        self.log(f"\n=== Testing Category: {category_id} ===")
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/reports-hub/summary?category={category_id}",
                headers=self.get_headers(),
                timeout=15
            )
            
            self.test(f"{category_id}: Returns 200", response.status_code == 200,
                     f"Got {response.status_code}")
            
            if response.status_code != 200:
                return False
            
            data = response.json()
            
            # Check contract fields
            self.test(f"{category_id}: Has 'category' field",
                     "category" in data and data["category"] == category_id)
            self.test(f"{category_id}: Has 'label' field", "label" in data)
            self.test(f"{category_id}: Has 'portal' field", "portal" in data)
            self.test(f"{category_id}: Has 'description' field", "description" in data)
            self.test(f"{category_id}: Has 'date_from' field", "date_from" in data)
            self.test(f"{category_id}: Has 'date_to' field", "date_to" in data)
            self.test(f"{category_id}: Has 'kpis' array", "kpis" in data and isinstance(data["kpis"], list))
            self.test(f"{category_id}: Has 'tables' array", "tables" in data and isinstance(data["tables"], list))
            self.test(f"{category_id}: Has 'sources' array", "sources" in data and isinstance(data["sources"], list))
            
            # Check KPIs structure
            kpis = data.get("kpis", [])
            if kpis:
                kpi = kpis[0]
                self.test(f"{category_id}: KPI has 'label'", "label" in kpi)
                self.test(f"{category_id}: KPI has 'value'", "value" in kpi)
                self.test(f"{category_id}: KPI has 'format'", "format" in kpi)
                self.test(f"{category_id}: KPI has 'sub'", "sub" in kpi)
                self.test(f"{category_id}: KPI has 'tone'", "tone" in kpi)
            
            # Check tables structure
            tables = data.get("tables", [])
            self.test(f"{category_id}: Has at least 1 table", len(tables) >= 1,
                     f"Got {len(tables)} tables")
            
            if tables:
                table = tables[0]
                self.test(f"{category_id}: Table has 'id'", "id" in table)
                self.test(f"{category_id}: Table has 'title'", "title" in table)
                self.test(f"{category_id}: Table has 'subtitle'", "subtitle" in table)
                self.test(f"{category_id}: Table has 'columns'", "columns" in table and isinstance(table["columns"], list))
                self.test(f"{category_id}: Table has 'rows'", "rows" in table and isinstance(table["rows"], list))
                self.test(f"{category_id}: Table has 'module_id'", "module_id" in table)
                self.test(f"{category_id}: Table has 'module_label'", "module_label" in table)
                self.test(f"{category_id}: Table has 'empty_hint'", "empty_hint" in table)
                
                # Check columns structure
                if table.get("columns"):
                    col = table["columns"][0]
                    self.test(f"{category_id}: Column has 'key'", "key" in col)
                    self.test(f"{category_id}: Column has 'label'", "label" in col)
            
            # Check sources
            sources = data.get("sources", [])
            self.test(f"{category_id}: Has sources trace", len(sources) > 0,
                     "No sources provided")
            
            if sources:
                src = sources[0]
                self.test(f"{category_id}: Source has 'collection'", "collection" in src)
                self.test(f"{category_id}: Source has 'count'", "count" in src)
                self.test(f"{category_id}: Source has 'note'", "note" in src)
            
            # Verify data is REAL (not all zeros)
            if kpis:
                non_zero_kpis = [k for k in kpis if k.get("value") not in [0, "0", None, ""]]
                self.test(f"{category_id}: Has non-zero KPI values",
                         len(non_zero_kpis) > 0,
                         "All KPIs are zero or empty")
            
            if tables:
                tables_with_data = [t for t in tables if len(t.get("rows", [])) > 0]
                self.test(f"{category_id}: Has tables with data",
                         len(tables_with_data) > 0,
                         "All tables are empty")
            
            return True
            
        except Exception as e:
            self.test(f"{category_id}: Summary accessible", False, str(e))
            return False

    def test_invalid_category(self):
        """Test invalid category returns 404 with helpful message"""
        self.log("\n=== Testing Invalid Category ===")
        try:
            response = requests.get(
                f"{BASE_URL}/api/rahaza/reports-hub/summary?category=ngawur",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test("Invalid category returns 404", response.status_code == 404,
                     f"Got {response.status_code}")
            
            if response.status_code == 404:
                data = response.json()
                detail = data.get("detail", "")
                self.test("Error message mentions valid options",
                         "Pilihan:" in detail or "eksekutif" in detail,
                         f"Got: {detail}")
            
            return True
            
        except Exception as e:
            self.test("Invalid category handling", False, str(e))
            return False

    def test_period_parameters(self):
        """Test period parameters work correctly"""
        self.log("\n=== Testing Period Parameters ===")
        try:
            # Test with valid period
            response = requests.get(
                f"{BASE_URL}/api/rahaza/reports-hub/summary?category=marketing&date_from=2026-08-01&date_to=2026-08-05",
                headers=self.get_headers(),
                timeout=15
            )
            
            self.test("Period parameters: Returns 200", response.status_code == 200,
                     f"Got {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                self.test("Period parameters: date_from matches",
                         data.get("date_from") == "2026-08-01")
                self.test("Period parameters: date_to matches",
                         data.get("date_to") == "2026-08-05")
            
            # Test with invalid date
            response = requests.get(
                f"{BASE_URL}/api/rahaza/reports-hub/summary?category=marketing&date_from=abc",
                headers=self.get_headers(),
                timeout=10
            )
            
            self.test("Invalid date returns 400", response.status_code == 400,
                     f"Got {response.status_code}")
            
            return True
            
        except Exception as e:
            self.test("Period parameters handling", False, str(e))
            return False

    def test_module_registry(self):
        """Verify all module_id in tables exist in frontend moduleRegistry.js"""
        self.log("\n=== Verifying Module Registry ===")
        
        # Read moduleRegistry.js
        try:
            with open("/app/frontend/src/components/erp/moduleRegistry.js", "r") as f:
                registry_content = f.read()
        except Exception as e:
            self.test("Read moduleRegistry.js", False, str(e))
            return False
        
        # Expected module IDs from backend
        expected_modules = [
            "prod-monitoring", "fin-ar-360", "da-cmt-receive", "wh-materials",
            "wh-material-issue", "hr-attendance", "hr-employees", "rnd-styles",
            "marketing-catalog", "marketing-orders", "maklon-billing"
        ]
        
        for module_id in expected_modules:
            # Check if module_id exists in registry (as key in quotes)
            exists = f"'{module_id}'" in registry_content or f'"{module_id}"' in registry_content
            self.test(f"Module '{module_id}' registered in frontend",
                     exists,
                     f"Module not found in moduleRegistry.js")
        
        return True

    def run_all_tests(self):
        """Run all tests"""
        self.log("=" * 60)
        self.log("GELOMBANG 2 - Reports Hub Backend Testing")
        self.log("=" * 60)
        
        # Login
        if not self.login():
            self.log("\n❌ Login failed, cannot continue")
            return False
        
        # Test categories endpoint
        self.test_categories_endpoint()
        
        # Test all 8 categories
        categories = ["eksekutif", "produksi_internal", "maklon", "gudang",
                     "keuangan", "sdm", "rnd", "marketing"]
        
        for category_id in categories:
            self.test_category_summary(category_id, {})
        
        # Test error handling
        self.test_invalid_category()
        self.test_period_parameters()
        
        # Test module registry
        self.test_module_registry()
        
        # Print summary
        self.log("\n" + "=" * 60)
        self.log(f"SUMMARY: {self.tests_passed}/{self.tests_run} tests passed")
        if self.tests_failed > 0:
            self.log(f"\n❌ {self.tests_failed} FAILURES:")
            for failure in self.failures:
                self.log(f"  - {failure}")
        self.log("=" * 60)
        
        return self.tests_failed == 0

if __name__ == "__main__":
    tester = ReportsHubTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
