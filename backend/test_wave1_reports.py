"""
Test Wave 1: Portal Manajemen Data Source Fixes
Testing backend APIs for Ringkasan Bisnis & Laporan (Management & Maklon)

VERIFICATION TARGETS (from review_request):
- overview domain all/internal/maklon: real numbers with sources
- 7 report types filled (45/21/9/10/6/5/6 rows)
- dewi/reports daily: total_processed=718
- dewi/reports monthly: summary>0
- dewi/reports actual-vs-target: cmt_jobs & maklon_pos not empty
- dewi/reports po/{id}: accepts both production_pos id AND dewi_maklon_pos id
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

class Wave1Tester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        
    def log(self, msg, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {msg}")
    
    def test(self, name, condition, details=""):
        """Run a test and track results"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            self.log(f"✅ PASS: {name}", "PASS")
            if details:
                self.log(f"   {details}", "INFO")
            return True
        else:
            self.failed_tests.append({"name": name, "details": details})
            self.log(f"❌ FAIL: {name}", "FAIL")
            if details:
                self.log(f"   {details}", "ERROR")
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
                if self.token:
                    self.log("✅ Login successful")
                    return True
                else:
                    self.log("❌ No token in response", "ERROR")
                    return False
            else:
                self.log(f"❌ Login failed: {response.status_code} - {response.text}", "ERROR")
                return False
        except Exception as e:
            self.log(f"❌ Login error: {str(e)}", "ERROR")
            return False
    
    def get(self, endpoint):
        """Make GET request with auth"""
        headers = {"Authorization": f"Bearer {self.token}"}
        try:
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
            return response
        except Exception as e:
            self.log(f"Request error for {endpoint}: {str(e)}", "ERROR")
            return None
    
    def test_overview(self):
        """Test Ringkasan Bisnis endpoints"""
        self.log("\n=== TESTING RINGKASAN BISNIS ===")
        
        # Test domain=all
        self.log("Testing overview domain=all...")
        resp = self.get("/api/rahaza/management/overview?domain=all")
        if resp and resp.status_code == 200:
            data = resp.json()
            
            # Verify expected numbers
            orders_total = data.get("orders", {}).get("total", 0)
            orders_qty = data.get("orders", {}).get("qty_ordered", 0)
            prod_qty_produced = data.get("production", {}).get("qty_produced", 0)
            prod_qty_accepted = data.get("production", {}).get("qty_accepted", 0)
            delivery_receipts = data.get("delivery", {}).get("cmt_receipts", 0)
            finance_ar = data.get("finance", {}).get("ar_invoices", 0)
            warehouse_materials = data.get("warehouse", {}).get("materials_tracked", 0)
            
            self.test("Overview domain=all returns 200", True)
            self.test("Overview orders.total = 21", orders_total == 21, 
                     f"Expected 21, got {orders_total}")
            self.test("Overview orders.qty_ordered = 4570", orders_qty == 4570,
                     f"Expected 4570, got {orders_qty}")
            self.test("Overview production.qty_produced = 735", prod_qty_produced == 735,
                     f"Expected 735, got {prod_qty_produced}")
            self.test("Overview production.qty_accepted = 219", prod_qty_accepted == 219,
                     f"Expected 219, got {prod_qty_accepted}")
            self.test("Overview delivery.cmt_receipts = 7", delivery_receipts == 7,
                     f"Expected 7, got {delivery_receipts}")
            self.test("Overview finance.ar_invoices = 10", finance_ar == 10,
                     f"Expected 10, got {finance_ar}")
            self.test("Overview warehouse.materials_tracked = 498", warehouse_materials == 498,
                     f"Expected 498, got {warehouse_materials}")
            
            # Verify sources exist
            sources = data.get("sources", [])
            self.test("Overview has sources array", len(sources) > 0,
                     f"Found {len(sources)} sources")
        else:
            self.test("Overview domain=all returns 200", False,
                     f"Status: {resp.status_code if resp else 'No response'}")
        
        # Test domain=internal
        self.log("Testing overview domain=internal...")
        resp = self.get("/api/rahaza/management/overview?domain=internal")
        if resp and resp.status_code == 200:
            data = resp.json()
            orders_total = data.get("orders", {}).get("total", 0)
            self.test("Overview domain=internal returns 200", True)
            self.test("Overview internal orders.total = 4", orders_total == 4,
                     f"Expected 4, got {orders_total}")
        else:
            self.test("Overview domain=internal returns 200", False)
        
        # Test domain=maklon
        self.log("Testing overview domain=maklon...")
        resp = self.get("/api/rahaza/management/overview?domain=maklon")
        if resp and resp.status_code == 200:
            data = resp.json()
            orders_total = data.get("orders", {}).get("total", 0)
            self.test("Overview domain=maklon returns 200", True)
            self.test("Overview maklon orders.total = 17", orders_total == 17,
                     f"Expected 17, got {orders_total}")
        else:
            self.test("Overview domain=maklon returns 200", False)
    
    def test_daily_output(self):
        """Test daily output endpoint"""
        self.log("\n=== TESTING DAILY OUTPUT ===")
        resp = self.get("/api/rahaza/management/daily-output?domain=all&days=7")
        if resp and resp.status_code == 200:
            data = resp.json()
            timeline = data.get("timeline", [])
            self.test("Daily output returns 200", True)
            self.test("Daily output timeline length = 7", len(timeline) == 7,
                     f"Expected 7 days, got {len(timeline)}")
            
            # Check timeline structure
            if timeline:
                first_day = timeline[0]
                has_date = "date" in first_day
                has_total = "total" in first_day
                has_internal = "internal" in first_day
                has_maklon = "maklon" in first_day
                self.test("Daily output has correct structure", 
                         has_date and has_total and has_internal and has_maklon,
                         f"date:{has_date}, total:{has_total}, internal:{has_internal}, maklon:{has_maklon}")
            
            sources = data.get("sources", [])
            self.test("Daily output has sources", len(sources) > 0)
        else:
            self.test("Daily output returns 200", False)
    
    def test_top_models(self):
        """Test top models endpoint"""
        self.log("\n=== TESTING TOP MODELS ===")
        resp = self.get("/api/rahaza/management/top-models?domain=all&limit=5")
        if resp and resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            self.test("Top models returns 200", True)
            self.test("Top models has items", len(items) > 0,
                     f"Found {len(items)} items")
            
            # Check item structure
            if items:
                first_item = items[0]
                has_sku = "sku" in first_item
                has_name = "name" in first_item
                has_qty = "qty" in first_item
                has_accepted = "accepted" in first_item
                has_progress = "progress_pct" in first_item
                qty_gt_zero = first_item.get("qty", 0) > 0
                
                self.test("Top models item has correct structure",
                         has_sku and has_name and has_qty and has_accepted and has_progress,
                         f"sku:{has_sku}, name:{has_name}, qty:{has_qty}, accepted:{has_accepted}, progress:{has_progress}")
                self.test("Top models qty > 0", qty_gt_zero,
                         f"qty = {first_item.get('qty', 0)}")
        else:
            self.test("Top models returns 200", False)
    
    def test_top_customers(self):
        """Test top customers endpoint"""
        self.log("\n=== TESTING TOP CUSTOMERS ===")
        resp = self.get("/api/rahaza/management/top-customers?domain=maklon&limit=5")
        if resp and resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            self.test("Top customers returns 200", True)
            self.test("Top customers has items", len(items) > 0,
                     f"Found {len(items)} items")
            
            # Check for maklon customers with value
            if items:
                first_item = items[0]
                has_name = "name" in first_item
                has_orders = "orders" in first_item
                has_total_qty = "total_qty" in first_item
                has_total_value = "total_value" in first_item
                value_gt_zero = first_item.get("total_value", 0) > 0
                
                self.test("Top customers item has correct structure",
                         has_name and has_orders and has_total_qty and has_total_value)
                self.test("Top customers maklon total_value > 0", value_gt_zero,
                         f"total_value = {first_item.get('total_value', 0)}")
        else:
            self.test("Top customers returns 200", False)
    
    def test_on_time_delivery(self):
        """Test on-time delivery endpoint"""
        self.log("\n=== TESTING ON-TIME DELIVERY ===")
        resp = self.get("/api/rahaza/management/on-time-delivery?domain=all&days=90")
        if resp and resp.status_code == 200:
            data = resp.json()
            self.test("On-time delivery returns 200", True)
            
            has_total = "total_po" in data
            has_on_time = "on_time" in data
            has_late = "late" in data
            has_rate = "rate_pct" in data
            has_note = "measurable_note" in data
            has_examples = "late_examples" in data
            
            self.test("On-time delivery has correct structure",
                     has_total and has_on_time and has_late and has_rate and has_note and has_examples)
        else:
            self.test("On-time delivery returns 200", False)
    
    def test_reports(self):
        """Test Laporan Umum - 7 report types"""
        self.log("\n=== TESTING LAPORAN UMUM (7 TYPES) ===")
        
        expected_counts = {
            "production": 45,
            "per-po": 21,
            "progress": 9,
            "financial": 10,
            "shipment": 6,
            "rework": 5,
            "material-issue": 6
        }
        
        for report_type, expected_count in expected_counts.items():
            self.log(f"Testing report type: {report_type}...")
            resp = self.get(f"/api/rahaza/reports/{report_type}?domain=all&page=1&limit=50")
            
            if resp and resp.status_code == 200:
                data = resp.json()
                
                # Check if paginated response
                if "items" in data:
                    items = data.get("items", [])
                    total = data.get("pagination", {}).get("total", len(items))
                else:
                    items = data if isinstance(data, list) else []
                    total = len(items)
                
                self.test(f"Report {report_type} returns 200", True)
                self.test(f"Report {report_type} NOT EMPTY", len(items) > 0,
                         f"Expected ~{expected_count}, got {len(items)} items (total: {total})")
                
                # Verify column names for production report
                if report_type == "production" and items:
                    first_row = items[0]
                    has_no_po = "no_po" in first_row
                    has_qty_pesan = "qty_pesan" in first_row
                    has_qty_diterima = "qty_diterima" in first_row
                    
                    self.test(f"Report {report_type} has correct columns",
                             has_no_po and has_qty_pesan and has_qty_diterima,
                             f"no_po:{has_no_po}, qty_pesan:{has_qty_pesan}, qty_diterima:{has_qty_diterima}")
            else:
                self.test(f"Report {report_type} returns 200", False,
                         f"Status: {resp.status_code if resp else 'No response'}")
        
        # Test unknown report type returns 404
        self.log("Testing unknown report type...")
        resp = self.get("/api/rahaza/reports/ngawur?domain=all")
        if resp:
            self.test("Unknown report type returns 404", resp.status_code == 404,
                     f"Status: {resp.status_code}")
    
    def test_domain_filtering(self):
        """Test domain filtering on production report"""
        self.log("\n=== TESTING DOMAIN FILTERING ===")
        
        # Test internal domain
        resp = self.get("/api/rahaza/reports/production?domain=internal&page=1&limit=50")
        if resp and resp.status_code == 200:
            data = resp.json()
            items = data.get("items", []) if "items" in data else data
            
            self.test("Production report domain=internal returns 200", True)
            
            if items:
                # All rows should have domain='Internal'
                all_internal = all(row.get("domain") == "Internal" for row in items)
                self.test("Production report domain=internal filters correctly", all_internal,
                         f"Checked {len(items)} rows")
        
        # Test maklon domain
        resp = self.get("/api/rahaza/reports/production?domain=maklon&page=1&limit=50")
        if resp and resp.status_code == 200:
            data = resp.json()
            items = data.get("items", []) if "items" in data else data
            
            self.test("Production report domain=maklon returns 200", True)
            
            if items:
                # All rows should have domain='Maklon'
                all_maklon = all(row.get("domain") == "Maklon" for row in items)
                self.test("Production report domain=maklon filters correctly", all_maklon,
                         f"Checked {len(items)} rows")
    
    def test_dewi_reports_daily(self):
        """Test Laporan Maklon - Daily"""
        self.log("\n=== TESTING LAPORAN MAKLON - DAILY ===")
        resp = self.get("/api/dewi/reports/daily?date=2026-08-05")
        
        if resp and resp.status_code == 200:
            data = resp.json()
            self.test("Dewi daily report returns 200", True)
            
            total_processed = data.get("production", {}).get("total_processed", 0)
            by_vendor = data.get("production", {}).get("by_vendor", [])
            delivery_orders = data.get("delivery_orders", {})
            buyer_delivery = data.get("buyer_delivery", {})
            fulfillment = data.get("fulfillment", {})
            stock_adjustments = data.get("stock_adjustments", 0)
            sources = data.get("sources", [])
            
            self.test("Dewi daily total_processed > 0", total_processed > 0,
                     f"total_processed = {total_processed}")
            self.test("Dewi daily by_vendor not empty", len(by_vendor) > 0,
                     f"Found {len(by_vendor)} vendors")
            self.test("Dewi daily has delivery_orders", "issued" in delivery_orders and "received" in delivery_orders)
            self.test("Dewi daily has buyer_delivery", "qty_today" in buyer_delivery)
            self.test("Dewi daily has fulfillment", "dispatched_orders" in fulfillment)
            self.test("Dewi daily has stock_adjustments", isinstance(stock_adjustments, int))
            self.test("Dewi daily has sources", len(sources) > 0,
                     f"Found {len(sources)} sources")
        else:
            self.test("Dewi daily report returns 200", False)
    
    def test_dewi_reports_monthly(self):
        """Test Laporan Maklon - Monthly"""
        self.log("\n=== TESTING LAPORAN MAKLON - MONTHLY ===")
        resp = self.get("/api/dewi/reports/monthly?year=2026&month=8")
        
        if resp and resp.status_code == 200:
            data = resp.json()
            self.test("Dewi monthly report returns 200", True)
            
            summary = data.get("summary", {})
            total_processed = summary.get("total_processed", 0)
            production_by_vendor = data.get("production_by_vendor", [])
            maklon_by_client = data.get("maklon_by_client", [])
            
            self.test("Dewi monthly summary.total_processed > 0", total_processed > 0,
                     f"total_processed = {total_processed}")
            self.test("Dewi monthly production_by_vendor not empty", len(production_by_vendor) > 0,
                     f"Found {len(production_by_vendor)} vendors")
            self.test("Dewi monthly maklon_by_client not empty", len(maklon_by_client) > 0,
                     f"Found {len(maklon_by_client)} clients")
        else:
            self.test("Dewi monthly report returns 200", False)
    
    def test_dewi_reports_actual_vs_target(self):
        """Test Laporan Maklon - Actual vs Target"""
        self.log("\n=== TESTING LAPORAN MAKLON - ACTUAL VS TARGET ===")
        resp = self.get("/api/dewi/reports/actual-vs-target?period=2026-08")
        
        if resp and resp.status_code == 200:
            data = resp.json()
            self.test("Dewi actual-vs-target returns 200", True)
            
            cmt_jobs = data.get("cmt_jobs", [])
            maklon_pos = data.get("maklon_pos", [])
            
            self.test("Dewi actual-vs-target cmt_jobs not empty", len(cmt_jobs) > 0,
                     f"Found {len(cmt_jobs)} jobs")
            self.test("Dewi actual-vs-target maklon_pos not empty", len(maklon_pos) > 0,
                     f"Found {len(maklon_pos)} POs")
            
            # Check structure
            if cmt_jobs:
                first_job = cmt_jobs[0]
                has_target = "target" in first_job
                has_actual = "actual" in first_job
                target_filled = first_job.get("target", 0) > 0 or first_job.get("actual", 0) > 0
                self.test("Dewi actual-vs-target cmt_jobs has target & actual",
                         has_target and has_actual and target_filled)
        else:
            self.test("Dewi actual-vs-target returns 200", False)
    
    def test_dewi_reports_trend(self):
        """Test Laporan Maklon - Production Trend"""
        self.log("\n=== TESTING LAPORAN MAKLON - TREND ===")
        resp = self.get("/api/dewi/reports/production-trend?days=7")
        
        if resp and resp.status_code == 200:
            data = resp.json()
            self.test("Dewi production-trend returns 200", True)
            
            trend = data.get("trend", [])
            self.test("Dewi trend length = 7", len(trend) == 7,
                     f"Expected 7 days, got {len(trend)}")
            
            # Check if any day has total_processed > 0
            has_data = any(day.get("total_processed", 0) > 0 for day in trend)
            self.test("Dewi trend has data (total_processed > 0 for some days)", has_data)
        else:
            self.test("Dewi production-trend returns 200", False)
    
    def test_dewi_reports_po(self):
        """Test Laporan Maklon - Per PO (accepts both id types)"""
        self.log("\n=== TESTING LAPORAN MAKLON - PER PO ===")
        
        # First, get a list of POs to test
        resp = self.get("/api/dewi/maklon/pos?limit=5")
        if resp and resp.status_code == 200:
            pos = resp.json()
            if isinstance(pos, dict) and "items" in pos:
                pos = pos["items"]
            
            if pos:
                # Test with dewi_maklon_pos id
                first_po = pos[0]
                po_id = first_po.get("id")
                
                self.log(f"Testing PO report with dewi_maklon_pos id: {po_id}")
                resp = self.get(f"/api/dewi/reports/po/{po_id}")
                
                if resp and resp.status_code == 200:
                    data = resp.json()
                    self.test("Dewi PO report accepts dewi_maklon_pos id", True)
                    
                    progress = data.get("progress", {})
                    has_target = "target_qty" in progress
                    has_produced = "qty_produced" in progress
                    has_accepted = "qty_accepted" in progress
                    has_dispatched = "qty_dispatched" in progress
                    
                    self.test("Dewi PO report has progress data",
                             has_target and has_produced and has_accepted and has_dispatched)
                    
                    sources = data.get("sources", [])
                    self.test("Dewi PO report has sources", len(sources) > 0)
                else:
                    self.test("Dewi PO report accepts dewi_maklon_pos id", False)
                
                # Try to test with production_pos id if available
                production_po_id = first_po.get("production_po_id")
                if production_po_id:
                    self.log(f"Testing PO report with production_pos id: {production_po_id}")
                    resp = self.get(f"/api/dewi/reports/po/{production_po_id}")
                    
                    if resp and resp.status_code == 200:
                        self.test("Dewi PO report accepts production_pos id", True)
                    else:
                        self.test("Dewi PO report accepts production_pos id", False)
            else:
                self.log("No POs found to test", "WARN")
        else:
            self.log("Could not fetch PO list", "WARN")
    
    def test_csv_exports(self):
        """Test CSV export endpoints"""
        self.log("\n=== TESTING CSV EXPORTS ===")
        
        # Test daily CSV
        resp = self.get("/api/dewi/reports/export/daily.csv?date=2026-08-05")
        if resp and resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            has_csv = "text/csv" in content_type
            has_source_trace = "JEJAK SUMBER DATA" in resp.text or "SUMBER DATA" in resp.text
            
            self.test("Daily CSV export returns 200", True)
            self.test("Daily CSV has correct content-type", has_csv,
                     f"content-type: {content_type}")
            self.test("Daily CSV has source trace", has_source_trace)
        else:
            self.test("Daily CSV export returns 200", False)
        
        # Test monthly CSV
        resp = self.get("/api/dewi/reports/export/monthly.csv?year=2026&month=8")
        if resp and resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            has_csv = "text/csv" in content_type
            has_source_trace = "JEJAK SUMBER DATA" in resp.text or "SUMBER DATA" in resp.text
            
            self.test("Monthly CSV export returns 200", True)
            self.test("Monthly CSV has correct content-type", has_csv,
                     f"content-type: {content_type}")
            self.test("Monthly CSV has source trace", has_source_trace)
        else:
            self.test("Monthly CSV export returns 200", False)
    
    def run_all_tests(self):
        """Run all backend tests"""
        self.log("=" * 70)
        self.log("WAVE 1 BACKEND TESTING - Portal Manajemen Data Source Fixes")
        self.log("=" * 70)
        
        if not self.login():
            self.log("❌ Login failed, cannot proceed with tests", "ERROR")
            return False
        
        # Run all test suites
        self.test_overview()
        self.test_daily_output()
        self.test_top_models()
        self.test_top_customers()
        self.test_on_time_delivery()
        self.test_reports()
        self.test_domain_filtering()
        self.test_dewi_reports_daily()
        self.test_dewi_reports_monthly()
        self.test_dewi_reports_actual_vs_target()
        self.test_dewi_reports_trend()
        self.test_dewi_reports_po()
        self.test_csv_exports()
        
        # Print summary
        self.log("\n" + "=" * 70)
        self.log("TEST SUMMARY")
        self.log("=" * 70)
        self.log(f"Total tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}")
        self.log(f"Failed: {len(self.failed_tests)}")
        self.log(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        
        if self.failed_tests:
            self.log("\n❌ FAILED TESTS:")
            for i, test in enumerate(self.failed_tests, 1):
                self.log(f"{i}. {test['name']}")
                if test['details']:
                    self.log(f"   {test['details']}")
        
        return len(self.failed_tests) == 0

if __name__ == "__main__":
    tester = Wave1Tester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)
