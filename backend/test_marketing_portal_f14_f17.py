"""
Backend test untuk Portal Marketing F14-F17
Verifikasi independen sesudah audit & perbaikan 2026-08-11
"""
import requests
import sys
import os
import io
import csv
from datetime import datetime

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com")
API_BASE = f"{BASE_URL}/api"

class MarketingPortalTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.account_id = None
        self.host_id = None
        self.creator_id = None
        self.session_id = None
        self.ads_id = None
        self.live_id = None
        self.sample_id = None

    def log(self, msg, status="INFO"):
        prefix = {"PASS": "✅", "FAIL": "❌", "INFO": "🔍"}.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def test(self, name, method, endpoint, expected_status, data=None, files=None, headers=None):
        """Run a single API test"""
        url = f"{API_BASE}/{endpoint}"
        h = {"Content-Type": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if headers:
            h.update(headers)
        if files:
            h.pop("Content-Type", None)

        self.tests_run += 1
        self.log(f"Testing {name}...", "INFO")
        
        try:
            if method == "GET":
                response = requests.get(url, headers=h, timeout=10)
            elif method == "POST":
                if files:
                    response = requests.post(url, data=data, files=files, headers=h, timeout=10)
                else:
                    response = requests.post(url, json=data, headers=h, timeout=10)
            elif method == "PUT":
                response = requests.put(url, json=data, headers=h, timeout=10)
            elif method == "DELETE":
                response = requests.delete(url, headers=h, timeout=10)
            else:
                raise ValueError(f"Unknown method: {method}")

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"PASS: {name} - Status {response.status_code}", "PASS")
                try:
                    return True, response.json()
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"FAIL: {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    self.log(f"  Response: {response.text[:200]}", "FAIL")
                except Exception:
                    pass
                return False, {}

        except Exception as e:
            self.tests_failed += 1
            self.log(f"FAIL: {name} - Error: {str(e)}", "FAIL")
            return False, {}

    def login(self):
        """Login and get token"""
        self.log("=== LOGIN ===", "INFO")
        success, response = self.test(
            "Login as admin",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"}
        )
        if success and "token" in response:
            self.token = response["token"]
            self.log(f"Token obtained: {self.token[:20]}...", "PASS")
            return True
        return False

    def test_f17_import_source_types(self):
        """F17 - GET /source-types harus mengembalikan >=15 jenis data"""
        self.log("\n=== F17: DATA IMPORT SOURCE TYPES ===", "INFO")
        success, response = self.test(
            "GET /source-types",
            "GET",
            "marketing/data-import/source-types",
            200
        )
        if success:
            types = response.get("source_types", [])
            if len(types) >= 15:
                self.log(f"Found {len(types)} source types (>=15 required)", "PASS")
                # Check specific collections
                discounts = next((t for t in types if t.get("key") == "discounts"), None)
                samples = next((t for t in types if t.get("key") == "samples"), None)
                if discounts and discounts.get("collection") == "marketing_discounts":
                    self.log("discounts -> marketing_discounts ✓", "PASS")
                else:
                    self.log(f"discounts collection wrong: {discounts}", "FAIL")
                if samples and samples.get("collection") == "marketing_samples":
                    self.log("samples -> marketing_samples ✓", "PASS")
                else:
                    self.log(f"samples collection wrong: {samples}", "FAIL")
            else:
                self.log(f"Only {len(types)} source types found, expected >=15", "FAIL")

    def test_f17_import_templates(self):
        """F17 - Template download"""
        self.log("\n=== F17: TEMPLATE DOWNLOAD ===", "INFO")
        
        # Test valid template
        success, _ = self.test(
            "GET /template/orders?fmt=xlsx",
            "GET",
            "marketing/data-import/template/orders?fmt=xlsx",
            200
        )
        
        success, _ = self.test(
            "GET /template/orders?fmt=csv",
            "GET",
            "marketing/data-import/template/orders?fmt=csv",
            200
        )
        
        # Test invalid source type
        success, _ = self.test(
            "GET /template/tidak_ada (should 400)",
            "GET",
            "marketing/data-import/template/tidak_ada",
            400
        )

    def test_f17_context_options(self):
        """F17 - Context options with host filtering"""
        self.log("\n=== F17: CONTEXT OPTIONS ===", "INFO")
        
        # Get accounts first
        success, response = self.test(
            "GET /context-options for live_sessions",
            "GET",
            "marketing/data-import/context-options?source_type=live_sessions",
            200
        )
        if success:
            accounts = response.get("accounts", [])
            if accounts:
                self.account_id = accounts[0].get("id")
                self.log(f"Using account_id: {self.account_id}", "INFO")
                
                # Get hosts for this account
                success2, response2 = self.test(
                    f"GET /context-options with account_id",
                    "GET",
                    f"marketing/data-import/context-options?source_type=live_sessions&account_id={self.account_id}",
                    200
                )
                if success2:
                    hosts = response2.get("hosts", [])
                    self.log(f"Found {len(hosts)} hosts assigned to account", "INFO")
                    if hosts:
                        self.host_id = hosts[0].get("id")
                        self.log(f"Using host_id: {self.host_id}", "INFO")

    def test_f17_upload_csv(self):
        """F17 - Upload CSV with Indonesian formatting"""
        self.log("\n=== F17: CSV UPLOAD ===", "INFO")
        
        if not self.account_id:
            self.log("Skipping upload test - no account_id", "FAIL")
            return
        
        # Test: upload without account_id for account-scoped type (should 400)
        csv_content = "Nama Kampanye,Tanggal,Biaya\nTest Campaign,2024-01-01,Rp 1.250.000"
        csv_file = io.BytesIO(csv_content.encode('utf-8'))
        
        success, _ = self.test(
            "POST /upload without account_id (should 400)",
            "POST",
            "marketing/data-import/upload",
            400,
            data={
                "source_type": "ads",
            },
            files={"file": ("test.csv", csv_file, "text/csv")}
        )
        
        # Test: live_sessions without host_id (should 400)
        if self.account_id:
            csv_file2 = io.BytesIO(csv_content.encode('utf-8'))
            success, _ = self.test(
                "POST /upload live_sessions without host_id (should 400)",
                "POST",
                "marketing/data-import/upload",
                400,
                data={
                    "source_type": "live_sessions",
                    "account_id": self.account_id,
                },
                files={"file": ("test.csv", csv_file2, "text/csv")}
            )
        
        # Test: valid upload with Indonesian formatting
        if self.account_id and self.host_id:
            csv_indo = """Judul Sesi;Tanggal;Durasi (menit);Penonton Puncak;Total Penonton;Suka;Komentar;Bagikan;Pesanan;Pendapatan
Sesi Live Test;2024-01-15;120;1.240;3.500;850;420;85;125;Rp 15.250.000"""
            csv_file3 = io.BytesIO(csv_indo.encode('utf-8'))
            
            success, response = self.test(
                "POST /upload with Indonesian CSV",
                "POST",
                "marketing/data-import/upload",
                200,
                data={
                    "source_type": "live_sessions",
                    "account_id": self.account_id,
                    "host_id": self.host_id,
                },
                files={"file": ("test_indo.csv", csv_file3, "text/csv")}
            )
            
            if success:
                session = response.get("session", {})
                self.session_id = session.get("id")
                if session.get("status") == "ready" and session.get("ai_used") == False:
                    self.log("CSV uploaded: status=ready, ai_used=false ✓", "PASS")
                    # Check if numbers parsed correctly
                    preview = response.get("preview", [])
                    if preview:
                        first_row = preview[0].get("data", {})
                        revenue = first_row.get("revenue", 0)
                        viewers = first_row.get("total_viewers", 0)
                        if revenue == 15250000 and viewers == 3500:
                            self.log(f"Indonesian numbers parsed correctly: revenue={revenue}, viewers={viewers}", "PASS")
                        else:
                            self.log(f"Number parsing issue: revenue={revenue} (expected 15250000), viewers={viewers} (expected 3500)", "FAIL")
                else:
                    self.log(f"Session status: {session.get('status')}, ai_used: {session.get('ai_used')}", "FAIL")

    def test_f17_full_flow(self):
        """F17 - Full import flow: upload -> mapping -> commit -> rollback"""
        self.log("\n=== F17: FULL IMPORT FLOW ===", "INFO")
        
        if not self.session_id:
            self.log("Skipping flow test - no session_id", "FAIL")
            return
        
        # Get session
        success, response = self.test(
            "GET /sessions/{id}",
            "GET",
            f"marketing/data-import/sessions/{self.session_id}",
            200
        )
        
        if success:
            session = response.get("session", {})
            mapping = session.get("mapping", [])
            
            # Test: mapping with two columns to one field (should 400)
            bad_mapping = [
                {"column": "col1", "field": "title"},
                {"column": "col2", "field": "title"}  # duplicate field
            ]
            success, _ = self.test(
                "PUT /mapping with duplicate field (should 400)",
                "PUT",
                f"marketing/data-import/sessions/{self.session_id}/mapping",
                400,
                data={"mapping": bad_mapping}
            )
            
            # Commit session
            success, response = self.test(
                "POST /commit",
                "POST",
                f"marketing/data-import/sessions/{self.session_id}/commit",
                200,
                data={"on_duplicate": "skip", "skip_warnings": False}
            )
            
            if success:
                inserted = response.get("inserted", 0)
                self.log(f"Committed {inserted} rows", "PASS")
                
                # Get errors CSV
                success, _ = self.test(
                    "GET /errors.csv",
                    "GET",
                    f"marketing/data-import/sessions/{self.session_id}/errors.csv",
                    200
                )
                
                # Rollback
                success, response = self.test(
                    "POST /rollback",
                    "POST",
                    f"marketing/data-import/sessions/{self.session_id}/rollback",
                    200
                )
                
                if success:
                    deleted = response.get("deleted", 0)
                    self.log(f"Rolled back {deleted} rows", "PASS")
                    
                    # Try rollback again (should 400)
                    success, _ = self.test(
                        "POST /rollback again (should 400)",
                        "POST",
                        f"marketing/data-import/sessions/{self.session_id}/rollback",
                        400
                    )
        
        # Get history
        success, _ = self.test(
            "GET /history",
            "GET",
            "marketing/data-import/history",
            200
        )

    def test_f14_account_scope(self):
        """F14 - Account scope filtering"""
        self.log("\n=== F14: ACCOUNT SCOPE FILTERING ===", "INFO")
        
        if not self.account_id:
            self.log("Skipping scope test - no account_id", "FAIL")
            return
        
        endpoints = [
            "marketing/orders",
            "marketing/samples",
            "marketing/ads/campaigns",
            "marketing/live/sessions",
            "marketing/content-calendar",
            "marketing/discounts",
            "marketing/product-launches",
        ]
        
        for endpoint in endpoints:
            success, response = self.test(
                f"GET /{endpoint}?account_id={self.account_id}",
                "GET",
                f"{endpoint}?account_id={self.account_id}",
                200
            )
            if success:
                # Handle different response structures
                items = []
                if isinstance(response, dict):
                    if "data" in response:
                        data = response["data"]
                        if isinstance(data, dict):
                            data_key = "campaigns" if "campaigns" in endpoint else "sessions" if "sessions" in endpoint else "data"
                            items = data.get(data_key, [])
                        elif isinstance(data, list):
                            items = data
                    else:
                        data_key = "campaigns" if "campaigns" in endpoint else "sessions" if "sessions" in endpoint else "data"
                        items = response.get(data_key, [])
                elif isinstance(response, list):
                    items = response
                
                # Check if all items have matching account_id
                if items:
                    mismatched = [item for item in items if item.get("account_id") != self.account_id]
                    if mismatched:
                        self.log(f"{endpoint}: Found {len(mismatched)} items with wrong account_id", "FAIL")
                    else:
                        self.log(f"{endpoint}: All {len(items)} items have correct account_id", "PASS")
        
        # Test summary endpoints
        summary_endpoints = [
            "marketing/orders/summary",
            "marketing/samples/summary",
            "marketing/ads/summary",
            "marketing/live/summary",
            "marketing/content-calendar/summary",
            "marketing/discounts/summary",
        ]
        
        for endpoint in summary_endpoints:
            success, _ = self.test(
                f"GET /{endpoint}?account_id={self.account_id}",
                "GET",
                f"{endpoint}?account_id={self.account_id}",
                200
            )

    def test_f16_ads_crud(self):
        """F16 - Ads CRUD with calculated fields"""
        self.log("\n=== F16: ADS CRUD ===", "INFO")
        
        if not self.account_id:
            self.log("Skipping ads test - no account_id", "FAIL")
            return
        
        # Test: create without account_id (should 4xx)
        success, _ = self.test(
            "POST /ads/campaigns without account_id (should 400)",
            "POST",
            "marketing/ads/campaigns",
            400,
            data={
                "date": "2024-01-15",
                "campaign_name": "Test Campaign",
                "spend": 1000000,
                "impressions": 50000,
                "clicks": 1500,
                "conversions": 75,
                "revenue": 3000000
            }
        )
        
        # Test: create with account_id
        success, response = self.test(
            "POST /ads/campaigns with account_id",
            "POST",
            "marketing/ads/campaigns",
            201,
            data={
                "account_id": self.account_id,
                "date": "2024-01-15",
                "campaign_name": "Test Campaign",
                "ad_platform": "shopee_ads",
                "spend": 1000000,
                "impressions": 50000,
                "clicks": 1500,
                "conversions": 75,
                "revenue": 3000000
            }
        )
        
        if success:
            ads_data = response.get("data", {})
            self.ads_id = ads_data.get("id")
            # Check calculated fields
            ctr = ads_data.get("ctr", 0)
            cpa = ads_data.get("cpa", 0)
            roas = ads_data.get("roas", 0)
            expected_ctr = round(1500 / 50000 * 100, 2)  # 3.0
            expected_cpa = round(1000000 / 75, 2)  # 13333.33
            expected_roas = round(3000000 / 1000000, 2)  # 3.0
            
            if abs(ctr - expected_ctr) < 0.1 and abs(cpa - expected_cpa) < 1 and abs(roas - expected_roas) < 0.1:
                self.log(f"Calculated fields correct: CTR={ctr}, CPA={cpa}, ROAS={roas}", "PASS")
            else:
                self.log(f"Calculated fields wrong: CTR={ctr} (exp {expected_ctr}), CPA={cpa} (exp {expected_cpa}), ROAS={roas} (exp {expected_roas})", "FAIL")
            
            # Test: GET by id
            success, _ = self.test(
                f"GET /ads/campaigns/{self.ads_id}",
                "GET",
                f"marketing/ads/campaigns/{self.ads_id}",
                200
            )
            
            # Test: PUT
            success, _ = self.test(
                f"PUT /ads/campaigns/{self.ads_id}",
                "PUT",
                f"marketing/ads/campaigns/{self.ads_id}",
                200,
                data={"spend": 1200000}
            )
            
            # Test: DELETE
            success, _ = self.test(
                f"DELETE /ads/campaigns/{self.ads_id}",
                "DELETE",
                f"marketing/ads/campaigns/{self.ads_id}",
                200
            )
        
        # Test: GET /platforms
        success, response = self.test(
            "GET /ads/platforms",
            "GET",
            "marketing/ads/platforms",
            200
        )
        if success:
            platforms = response.get("ad_platforms", [])
            self.log(f"Found {len(platforms)} ad platforms", "PASS")

    def test_f16_live_crud(self):
        """F16 - Live sessions CRUD with host validation"""
        self.log("\n=== F16: LIVE SESSIONS CRUD ===", "INFO")
        
        if not self.account_id or not self.host_id:
            self.log("Skipping live test - no account_id or host_id", "FAIL")
            return
        
        # Test: create without account_id (should 400)
        success, _ = self.test(
            "POST /live/sessions without account_id (should 400)",
            "POST",
            "marketing/live/sessions",
            400,
            data={
                "host_id": self.host_id,
                "session_date": "2024-01-15",
                "title": "Test Live",
                "duration_minutes": 120,
                "total_viewers": 1000,
                "orders": 50,
                "revenue": 2500000
            }
        )
        
        # Test: create with valid data
        success, response = self.test(
            "POST /live/sessions with valid data",
            "POST",
            "marketing/live/sessions",
            201,
            data={
                "account_id": self.account_id,
                "host_id": self.host_id,
                "session_date": "2024-01-15",
                "title": "Test Live Session",
                "duration_minutes": 120,
                "peak_viewers": 800,
                "total_viewers": 2000,
                "likes": 500,
                "comments": 200,
                "shares": 50,
                "orders": 100,
                "revenue": 5000000,
                "units_sold": 150,
                "products_featured": 10
            }
        )
        
        if success:
            live_data = response.get("data", {})
            self.live_id = live_data.get("id")
            # Check calculated fields
            engagement = live_data.get("engagement_rate", 0)
            conversion = live_data.get("conversion_rate", 0)
            aov = live_data.get("aov", 0)
            expected_engagement = round((500 + 200 + 50) / 2000 * 100, 2)  # 37.5
            expected_conversion = round(100 / 2000 * 100, 2)  # 5.0
            expected_aov = round(5000000 / 100, 2)  # 50000
            
            if abs(engagement - expected_engagement) < 0.1 and abs(conversion - expected_conversion) < 0.1:
                self.log(f"Calculated fields correct: engagement={engagement}%, conversion={conversion}%, aov={aov}", "PASS")
            else:
                self.log(f"Calculated fields wrong: engagement={engagement} (exp {expected_engagement}), conversion={conversion} (exp {expected_conversion})", "FAIL")
            
            # Test: GET by id
            success, _ = self.test(
                f"GET /live/sessions/{self.live_id}",
                "GET",
                f"marketing/live/sessions/{self.live_id}",
                200
            )
            
            # Test: PUT
            success, _ = self.test(
                f"PUT /live/sessions/{self.live_id}",
                "PUT",
                f"marketing/live/sessions/{self.live_id}",
                200,
                data={"revenue": 5500000}
            )
            
            # Test: DELETE
            success, _ = self.test(
                f"DELETE /live/sessions/{self.live_id}",
                "DELETE",
                f"marketing/live/sessions/{self.live_id}",
                200
            )
        
        # Test: GET /statuses
        success, _ = self.test(
            "GET /live/statuses",
            "GET",
            "marketing/live/statuses",
            200
        )

    def test_f16_live_summary_revenue(self):
        """F16 - Live summary should show revenue > 0"""
        self.log("\n=== F16: LIVE SUMMARY REVENUE ===", "INFO")
        
        success, response = self.test(
            "GET /live/summary",
            "GET",
            "marketing/live/summary",
            200
        )
        
        if success:
            data = response.get("data", {})
            total_revenue = data.get("total_revenue", 0)
            total_orders = data.get("total_orders", 0)
            
            if total_revenue > 0 and total_orders > 0:
                self.log(f"Live summary shows revenue: Rp {total_revenue:,.0f}, orders: {total_orders}", "PASS")
            else:
                self.log(f"Live summary revenue issue: revenue={total_revenue}, orders={total_orders}", "FAIL")
        
        # Test all analytics endpoints
        analytics_endpoints = [
            "marketing/live/analytics/overview",
            "marketing/live/analytics/platform-breakdown",
            "marketing/live/analytics/revenue-trend",
            "marketing/live/analytics/product-performance",
            "marketing/live/analytics/sessions-comparison",
            "marketing/live/analytics/account-health",
            "marketing/live/analytics/host-leaderboard",
        ]
        
        for endpoint in analytics_endpoints:
            success, response = self.test(
                f"GET /{endpoint}",
                "GET",
                endpoint,
                200
            )
            if success and "overview" in endpoint:
                kpi = response.get("data", {}).get("kpi", {})
                revenue = kpi.get("total_revenue_rp", 0)
                if revenue > 0:
                    self.log(f"Analytics overview revenue: Rp {revenue:,.0f}", "PASS")

    def test_f15_samples_master(self):
        """F15 - Samples using master data"""
        self.log("\n=== F15: SAMPLES WITH MASTER ===", "INFO")
        
        if not self.account_id:
            self.log("Skipping samples test - no account_id", "FAIL")
            return
        
        # Get creators for this account
        success, response = self.test(
            "GET /context-options for samples",
            "GET",
            f"marketing/data-import/context-options?source_type=samples&account_id={self.account_id}",
            200
        )
        
        if success:
            creators = response.get("creators", [])
            if creators:
                self.creator_id = creators[0].get("id")
                self.log(f"Using creator_id: {self.creator_id}", "INFO")
        
        # Test: create without account_id (should 400)
        success, _ = self.test(
            "POST /samples without account_id (should 400)",
            "POST",
            "marketing/samples",
            400,
            data={
                "date": "2024-01-15",
                "sample_type": "live",
                "platform": "tiktok",
                "product": "Test Product",
                "size": "M",
                "color": "Black",
                "quantity": 2,
                "hpp": 50000,
                "ongkir": 15000,
                "courier": "jnt"
            }
        )
        
        # Test: create with valid data
        if self.creator_id:
            success, response = self.test(
                "POST /samples with creator_id",
                "POST",
                "marketing/samples",
                200,
                data={
                    "account_id": self.account_id,
                    "creator_id": self.creator_id,
                    "date": "2024-01-15",
                    "sample_type": "live",
                    "platform": "tiktok",
                    "product": "Test Product",
                    "size": "M",
                    "color": "Black",
                    "quantity": 2,
                    "hpp": 50000,
                    "ongkir": 15000,
                    "courier": "jnt"
                }
            )
            
            if success:
                sample_data = response.get("data", {})
                self.sample_id = sample_data.get("id")
                total_hpp = sample_data.get("total_hpp", 0)
                if total_hpp == 100000:  # 2 * 50000
                    self.log(f"Sample total_hpp calculated correctly: {total_hpp}", "PASS")
                
                # Clean up
                if self.sample_id:
                    self.test(
                        f"DELETE /samples/{self.sample_id}",
                        "DELETE",
                        f"marketing/samples/{self.sample_id}",
                        200
                    )

    def test_f15_product_launches(self):
        """F15 - Product launches with account_id"""
        self.log("\n=== F15: PRODUCT LAUNCHES ===", "INFO")
        
        if not self.account_id:
            self.log("Skipping product launches test - no account_id", "FAIL")
            return
        
        # Test: create without account_id (should 4xx)
        success, _ = self.test(
            "POST /product-launches without account_id (should 4xx)",
            "POST",
            "marketing/product-launches",
            400,
            data={
                "launch_date": "2024-02-01",
                "product_name": "New Collection",
                "description": "Test launch"
            }
        )

    def run_all_tests(self):
        """Run all tests"""
        self.log("=" * 60, "INFO")
        self.log("MARKETING PORTAL BACKEND TEST - F14-F17", "INFO")
        self.log("=" * 60, "INFO")
        
        if not self.login():
            self.log("Login failed, stopping tests", "FAIL")
            return 1
        
        # F17 - Data Import
        self.test_f17_import_source_types()
        self.test_f17_import_templates()
        self.test_f17_context_options()
        self.test_f17_upload_csv()
        self.test_f17_full_flow()
        
        # F14 - Account Scope
        self.test_f14_account_scope()
        
        # F16 - CRUD
        self.test_f16_ads_crud()
        self.test_f16_live_crud()
        self.test_f16_live_summary_revenue()
        
        # F15 - Master Data
        self.test_f15_samples_master()
        self.test_f15_product_launches()
        
        # Summary
        self.log("\n" + "=" * 60, "INFO")
        self.log(f"TESTS COMPLETED: {self.tests_run} total", "INFO")
        self.log(f"✅ PASSED: {self.tests_passed}", "PASS")
        self.log(f"❌ FAILED: {self.tests_failed}", "FAIL")
        self.log("=" * 60, "INFO")
        
        return 0 if self.tests_failed == 0 else 1


def main():
    tester = MarketingPortalTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
