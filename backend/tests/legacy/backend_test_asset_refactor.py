"""
CV. Dewi Aditya ERP — Asset Management Refactor Confidence Test
================================================================
Testing all 41 endpoints after splitting 2392 LOC monolith into 14 sub-modules.

CRITICAL: Verify literal paths are NOT shadowed by /{asset_id} catch-all route.

Test credentials: admin@garment.com / Admin@123
"""
import requests
import sys
from datetime import datetime, date

# Configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


class AssetRefactorTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.user_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.created_asset_id = None
        self.created_category_id = None

    def log(self, message, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, 
                 files=None, verify_fn=None, is_binary=False):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {}
        
        if not files:
            headers['Content-Type'] = 'application/json'
        
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        self.log(f"Test #{self.tests_run}: {name}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, data=data, headers=headers, timeout=30)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                # Additional verification if provided
                if verify_fn and not is_binary:
                    try:
                        response_data = response.json() if response.text else {}
                        verify_result = verify_fn(response_data)
                        if not verify_result:
                            success = False
                            self.log("  ❌ FAILED - Verification failed", "ERROR")
                            self.test_results.append({
                                "test": name,
                                "status": "FAILED",
                                "reason": "Verification failed",
                                "endpoint": endpoint
                            })
                            return False, {}
                    except Exception as e:
                        success = False
                        self.log(f"  ❌ FAILED - Verification error: {str(e)}", "ERROR")
                        self.test_results.append({
                            "test": name,
                            "status": "FAILED",
                            "reason": f"Verification error: {str(e)}",
                            "endpoint": endpoint
                        })
                        return False, {}
            
            if success:
                self.tests_passed += 1
                self.log(f"  ✅ PASSED - Status: {response.status_code}")
                self.test_results.append({
                    "test": name,
                    "status": "PASSED",
                    "endpoint": endpoint
                })
                if is_binary:
                    return True, response.content
                return True, response.json() if response.text and not is_binary else {}
            else:
                self.log(f"  ❌ FAILED - Expected {expected_status}, got {response.status_code}", "ERROR")
                try:
                    error_detail = response.json() if response.text else response.text
                    self.log(f"     Response: {error_detail}", "ERROR")
                except Exception:
                    self.log(f"     Response: {response.text[:200]}", "ERROR")
                
                self.test_results.append({
                    "test": name,
                    "status": "FAILED",
                    "expected": expected_status,
                    "actual": response.status_code,
                    "endpoint": endpoint
                })
                return False, {}

        except Exception as e:
            self.log(f"  ❌ FAILED - Exception: {str(e)}", "ERROR")
            self.test_results.append({
                "test": name,
                "status": "FAILED",
                "reason": str(e),
                "endpoint": endpoint
            })
            return False, {}

    # ========== Authentication ==========
    def test_login(self):
        """Test login and get token"""
        self.log("=" * 60)
        self.log("PHASE 1: Authentication")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "Login as admin",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if success and 'token' in response:
            self.token = response['token']
            self.user_id = response.get('user', {}).get('id')
            self.log(f"  Token acquired, user_id: {self.user_id}")
            return True
        return False

    # ========== Dashboard ==========
    def test_dashboard(self):
        """Test GET /api/assets/dashboard"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 2: Dashboard")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "Get dashboard summary",
            "GET",
            "/api/assets/dashboard",
            200,
            verify_fn=lambda r: 'summary' in r and 'by_category' in r and 'recent_assets' in r
        )
        return success

    # ========== Categories CRUD ==========
    def test_categories_crud(self):
        """Test full CRUD on categories"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 3: Categories CRUD")
        self.log("=" * 60)
        
        # List categories
        success, response = self.run_test(
            "List categories",
            "GET",
            "/api/assets/categories",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        if not success:
            return False
        
        # Create category
        success, response = self.run_test(
            "Create category",
            "POST",
            "/api/assets/categories",
            200,
            data={
                "name": "Test Category",
                "code": "TST",
                "useful_life_years": 5,
                "depr_method": "straight_line"
            },
            verify_fn=lambda r: 'id' in r
        )
        if not success:
            return False
        
        self.created_category_id = response.get('id')
        self.log(f"  Created category ID: {self.created_category_id}")
        
        # Get category by ID
        success, response = self.run_test(
            "Get category by ID",
            "GET",
            f"/api/assets/categories/{self.created_category_id}",
            200,
            verify_fn=lambda r: r.get('code') == 'TST'
        )
        if not success:
            return False
        
        # Update category
        success, response = self.run_test(
            "Update category",
            "PUT",
            f"/api/assets/categories/{self.created_category_id}",
            200,
            data={
                "name": "Test Category Updated",
                "code": "TST",
                "useful_life_years": 6,
                "depr_method": "straight_line"
            }
        )
        if not success:
            return False
        
        # Delete category (will test later after asset cleanup)
        return True

    # ========== Asset Creation ==========
    def test_asset_creation(self):
        """Test POST /api/assets (creates asset + auto JE)"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 4: Asset Creation")
        self.log("=" * 60)
        
        # Get first category for asset creation
        success, categories = self.run_test(
            "Get categories for asset creation",
            "GET",
            "/api/assets/categories",
            200
        )
        if not success or not categories:
            self.log("  ❌ No categories available", "ERROR")
            return False
        
        category_id = categories[0].get('id')
        
        success, response = self.run_test(
            "Create asset with auto JE",
            "POST",
            "/api/assets",
            200,
            data={
                "name": "Test Laptop Dell XPS 15",
                "category_id": category_id,
                "purchase_cost": 15000000,
                "purchase_date": "2026-01-15",
                "residual_value": 1500000,
                "location": "Jakarta Office",
                "description": "Test asset for refactor validation",
                "warranty_expiry": "2027-01-15",
                "insurance_expiry": "2027-01-15"
            },
            verify_fn=lambda r: 'id' in r and 'asset_number' in r
        )
        
        if success:
            self.created_asset_id = response.get('id')
            self.log(f"  Created asset ID: {self.created_asset_id}")
            self.log(f"  Asset number: {response.get('asset_number')}")
            return True
        return False

    # ========== CRITICAL: Literal Path Resolution Tests ==========
    def test_literal_paths(self):
        """Test that literal paths are NOT shadowed by /{asset_id}"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 5: CRITICAL - Literal Path Resolution")
        self.log("=" * 60)
        
        all_passed = True
        
        # Test 1: /expiring-alerts (MUST NOT be treated as asset_id)
        success, _ = self.run_test(
            "GET /expiring-alerts (literal path)",
            "GET",
            "/api/assets/expiring-alerts?days=30",
            200,
            verify_fn=lambda r: 'warranty_expiring' in r and 'insurance_expiring' in r
        )
        all_passed = all_passed and success
        
        # Test 2: /my-assets (MUST NOT be treated as asset_id)
        success, _ = self.run_test(
            "GET /my-assets (literal path)",
            "GET",
            "/api/assets/my-assets",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Test 3: /disposal-requests (MUST NOT be treated as asset_id)
        success, _ = self.run_test(
            "GET /disposal-requests (literal path)",
            "GET",
            "/api/assets/disposal-requests?status=all",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Test 4: /batch-depreciate/{period} (MUST NOT be treated as asset_id)
        success, _ = self.run_test(
            "POST /batch-depreciate/2026-05 (literal path)",
            "POST",
            "/api/assets/batch-depreciate/2026-05",
            200,
            verify_fn=lambda r: 'period' in r and 'total_posted' in r
        )
        all_passed = all_passed and success
        
        # Test 5: /scan-by-number/{num} (MOST CRITICAL - MUST NOT be shadowed)
        if self.created_asset_id:
            # First get the asset to find its asset_number
            success, asset = self.run_test(
                "Get asset for scan-by-number test",
                "GET",
                f"/api/assets/{self.created_asset_id}",
                200
            )
            if success:
                asset_number = asset.get('asset_number')
                success, _ = self.run_test(
                    f"GET /scan-by-number/{asset_number} (CRITICAL literal path)",
                    "GET",
                    f"/api/assets/scan-by-number/{asset_number}",
                    200,
                    verify_fn=lambda r: r.get('asset_number') == asset_number
                )
                all_passed = all_passed and success
        
        # Test 6: /reports/utilization (MUST NOT be treated as asset_id)
        today = date.today().isoformat()
        success, _ = self.run_test(
            "GET /reports/utilization (literal path)",
            "GET",
            f"/api/assets/reports/utilization?start_date=2026-01-01&end_date={today}",
            200,
            verify_fn=lambda r: 'summary' in r and 'by_category' in r
        )
        all_passed = all_passed and success
        
        # Test 7: /predictive-maintenance/alerts (MUST NOT be treated as asset_id)
        success, _ = self.run_test(
            "GET /predictive-maintenance/alerts (literal path)",
            "GET",
            "/api/assets/predictive-maintenance/alerts",
            200,
            verify_fn=lambda r: 'overdue' in r and 'upcoming' in r
        )
        all_passed = all_passed and success
        
        return all_passed

    # ========== Asset Lifecycle ==========
    def test_asset_lifecycle(self):
        """Test full asset lifecycle operations"""
        if not self.created_asset_id:
            self.log("  ⚠️  Skipping lifecycle tests - no asset created", "WARN")
            return False
        
        self.log("\n" + "=" * 60)
        self.log("PHASE 6: Asset Lifecycle")
        self.log("=" * 60)
        
        all_passed = True
        
        # Get asset detail
        success, asset = self.run_test(
            "Get asset detail",
            "GET",
            f"/api/assets/{self.created_asset_id}",
            200,
            verify_fn=lambda r: 'nbv' in r and 'depreciation_history' in r
        )
        all_passed = all_passed and success
        
        # Update asset
        success, _ = self.run_test(
            "Update asset",
            "PUT",
            f"/api/assets/{self.created_asset_id}",
            200,
            data={
                "name": "Test Laptop Dell XPS 15 (Updated)",
                "location": "Bandung Office",
                "warranty_expiry": "2027-06-15"
            }
        )
        all_passed = all_passed and success
        
        # Assign asset
        success, _ = self.run_test(
            "Assign asset to user",
            "POST",
            f"/api/assets/{self.created_asset_id}/assign",
            200,
            data={
                "assigned_to_id": self.user_id,
                "assigned_to_name": "Admin User",
                "assigned_date": "2026-01-20",
                "notes": "Test assignment"
            }
        )
        all_passed = all_passed and success
        
        # Get assignments
        success, _ = self.run_test(
            "Get asset assignments",
            "GET",
            f"/api/assets/{self.created_asset_id}/assignments",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Add maintenance
        success, _ = self.run_test(
            "Add maintenance record",
            "POST",
            f"/api/assets/{self.created_asset_id}/maintenance",
            200,
            data={
                "maintenance_date": "2026-02-01",
                "maintenance_type": "preventive",
                "description": "Regular checkup",
                "cost": 500000,
                "performed_by": "IT Team"
            }
        )
        all_passed = all_passed and success
        
        # Get maintenance history
        success, _ = self.run_test(
            "Get maintenance history",
            "GET",
            f"/api/assets/{self.created_asset_id}/maintenance",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Transfer asset
        success, _ = self.run_test(
            "Transfer asset",
            "POST",
            f"/api/assets/{self.created_asset_id}/transfer",
            200,
            data={
                "from_location": "Jakarta Office",
                "to_location": "Surabaya Office",
                "transfer_date": "2026-02-15",
                "reason": "Office relocation",
                "transferred_by": self.user_id
            }
        )
        all_passed = all_passed and success
        
        # Get transfer history
        success, _ = self.run_test(
            "Get transfer history",
            "GET",
            f"/api/assets/{self.created_asset_id}/transfer-history",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Scan asset
        success, _ = self.run_test(
            "Scan asset",
            "POST",
            f"/api/assets/{self.created_asset_id}/scan",
            200,
            data={
                "scanned_by": self.user_id,
                "scanned_by_name": "Admin User",
                "location": "Surabaya Office"
            }
        )
        all_passed = all_passed and success
        
        # Get scan history
        success, _ = self.run_test(
            "Get scan history",
            "GET",
            f"/api/assets/{self.created_asset_id}/scan-history",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Depreciate asset for specific period
        success, _ = self.run_test(
            "Depreciate asset for period 2026-01",
            "POST",
            f"/api/assets/{self.created_asset_id}/depreciate/2026-01",
            200,
            verify_fn=lambda r: 'depreciation_amount' in r
        )
        all_passed = all_passed and success
        
        # Get depreciation history
        success, _ = self.run_test(
            "Get depreciation history",
            "GET",
            f"/api/assets/{self.created_asset_id}/depreciation-history",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        all_passed = all_passed and success
        
        # Unassign asset
        success, _ = self.run_test(
            "Unassign asset",
            "POST",
            f"/api/assets/{self.created_asset_id}/unassign",
            200,
            data={
                "unassigned_date": "2026-03-01",
                "notes": "Test unassignment"
            }
        )
        all_passed = all_passed and success
        
        return all_passed

    # ========== Binary Endpoints ==========
    def test_binary_endpoints(self):
        """Test barcode, qrcode, label-pdf generation"""
        if not self.created_asset_id:
            self.log("  ⚠️  Skipping binary tests - no asset created", "WARN")
            return False
        
        self.log("\n" + "=" * 60)
        self.log("PHASE 7: Binary Endpoints")
        self.log("=" * 60)
        
        all_passed = True
        
        # Get barcode (PNG)
        success, content = self.run_test(
            "Get barcode PNG",
            "GET",
            f"/api/assets/{self.created_asset_id}/barcode",
            200,
            is_binary=True
        )
        if success:
            self.log(f"  Barcode size: {len(content)} bytes")
        all_passed = all_passed and success
        
        # Get QR code (PNG)
        success, content = self.run_test(
            "Get QR code PNG",
            "GET",
            f"/api/assets/{self.created_asset_id}/qrcode",
            200,
            is_binary=True
        )
        if success:
            self.log(f"  QR code size: {len(content)} bytes")
        all_passed = all_passed and success
        
        # Get label PDF (standard template)
        success, content = self.run_test(
            "Get label PDF (standard)",
            "GET",
            f"/api/assets/{self.created_asset_id}/label-pdf?template=standard",
            200,
            is_binary=True
        )
        if success:
            self.log(f"  Label PDF size: {len(content)} bytes")
        all_passed = all_passed and success
        
        # Get label PDF (sticker template)
        success, content = self.run_test(
            "Get label PDF (sticker)",
            "GET",
            f"/api/assets/{self.created_asset_id}/label-pdf?template=sticker",
            200,
            is_binary=True
        )
        all_passed = all_passed and success
        
        # Get label PDF (A4 template)
        success, content = self.run_test(
            "Get label PDF (A4)",
            "GET",
            f"/api/assets/{self.created_asset_id}/label-pdf?template=a4",
            200,
            is_binary=True
        )
        all_passed = all_passed and success
        
        return all_passed

    # ========== Disposal Flow ==========
    def test_disposal_flow(self):
        """Test disposal request and approval flow"""
        if not self.created_asset_id:
            self.log("  ⚠️  Skipping disposal tests - no asset created", "WARN")
            return False
        
        self.log("\n" + "=" * 60)
        self.log("PHASE 8: Disposal Flow")
        self.log("=" * 60)
        
        all_passed = True
        
        # Request disposal
        success, response = self.run_test(
            "Request asset disposal",
            "POST",
            f"/api/assets/{self.created_asset_id}/request-disposal",
            200,
            data={
                "reason": "End of useful life",
                "requested_by": self.user_id,
                "requested_by_name": "Admin User"
            },
            verify_fn=lambda r: 'id' in r and 'status' in r
        )
        all_passed = all_passed and success
        
        if success:
            request_id = response.get('id')
            self.log(f"  Disposal request ID: {request_id}")
            
            # Get disposal requests
            success, requests = self.run_test(
                "Get disposal requests (pending)",
                "GET",
                "/api/assets/disposal-requests?status=pending",
                200,
                verify_fn=lambda r: isinstance(r, list)
            )
            all_passed = all_passed and success
            
            # Approve disposal request
            success, _ = self.run_test(
                "Approve disposal request",
                "PATCH",
                f"/api/assets/disposal-requests/{request_id}/approve",
                200,
                data={
                    "notes": "Approved for disposal"
                }
            )
            all_passed = all_passed and success
        
        return all_passed

    # ========== Bulk Import ==========
    def test_bulk_import(self):
        """Test bulk import endpoints"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 9: Bulk Import")
        self.log("=" * 60)
        
        all_passed = True
        
        # Get template
        success, content = self.run_test(
            "Download bulk import template (XLSX)",
            "GET",
            "/api/assets/bulk-import/template",
            200,
            is_binary=True
        )
        if success:
            self.log(f"  Template size: {len(content)} bytes")
        all_passed = all_passed and success
        
        # Preview import (with sample data)
        success, _ = self.run_test(
            "Preview bulk import",
            "POST",
            "/api/assets/bulk-import/preview",
            200,
            data={
                "data": [
                    {
                        "name": "Bulk Asset 1",
                        "category_code": "IT",
                        "purchase_cost": 5000000,
                        "purchase_date": "2026-01-01",
                        "location": "Jakarta"
                    }
                ]
            },
            verify_fn=lambda r: 'preview' in r
        )
        all_passed = all_passed and success
        
        return all_passed

    # ========== Reports ==========
    def test_reports(self):
        """Test utilization reports"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 10: Reports")
        self.log("=" * 60)
        
        all_passed = True
        
        today = date.today().isoformat()
        
        # Get utilization report
        success, _ = self.run_test(
            "Get utilization report",
            "GET",
            f"/api/assets/reports/utilization?start_date=2026-01-01&end_date={today}",
            200,
            verify_fn=lambda r: 'summary' in r and 'by_category' in r
        )
        all_passed = all_passed and success
        
        # Export utilization CSV
        success, content = self.run_test(
            "Export utilization CSV",
            "GET",
            f"/api/assets/reports/utilization/export.csv?start_date=2026-01-01&end_date={today}",
            200,
            is_binary=True
        )
        if success:
            self.log(f"  CSV size: {len(content)} bytes")
        all_passed = all_passed and success
        
        return all_passed

    # ========== Predictive Maintenance ==========
    def test_predictive_maintenance(self):
        """Test predictive maintenance alerts and acknowledgments"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 11: Predictive Maintenance")
        self.log("=" * 60)
        
        all_passed = True
        
        # Get alerts
        success, response = self.run_test(
            "Get predictive maintenance alerts",
            "GET",
            "/api/assets/predictive-maintenance/alerts",
            200,
            verify_fn=lambda r: all(k in r for k in ['overdue', 'upcoming', 'stale', 'high_frequency', 'predicted'])
        )
        all_passed = all_passed and success
        
        # Acknowledge alert (if any asset exists)
        if self.created_asset_id:
            success, _ = self.run_test(
                "Acknowledge maintenance alert",
                "POST",
                "/api/assets/predictive-maintenance/acknowledge",
                200,
                data={
                    "asset_id": self.created_asset_id,
                    "acknowledged_by": self.user_id,
                    "acknowledged_by_name": "Admin User",
                    "notes": "Scheduled for next month"
                }
            )
            all_passed = all_passed and success
            
            # Get acknowledgments
            success, _ = self.run_test(
                "Get acknowledgments",
                "GET",
                "/api/assets/predictive-maintenance/acknowledgments",
                200,
                verify_fn=lambda r: isinstance(r, list)
            )
            all_passed = all_passed and success
        
        return all_passed

    # ========== Asset List with Filters ==========
    def test_asset_list_filters(self):
        """Test GET /api/assets with various filters"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 12: Asset List & Filters")
        self.log("=" * 60)
        
        all_passed = True
        
        # List all assets (returns paginated response)
        success, response = self.run_test(
            "List all assets",
            "GET",
            "/api/assets",
            200,
            verify_fn=lambda r: 'items' in r and 'pagination' in r
        )
        all_passed = all_passed and success
        
        # Filter by status
        success, _ = self.run_test(
            "Filter assets by status=active",
            "GET",
            "/api/assets?status=active",
            200,
            verify_fn=lambda r: 'items' in r and 'pagination' in r
        )
        all_passed = all_passed and success
        
        # Filter by category
        if self.created_category_id:
            success, _ = self.run_test(
                "Filter assets by category_id",
                "GET",
                f"/api/assets?category_id={self.created_category_id}",
                200,
                verify_fn=lambda r: 'items' in r and 'pagination' in r
            )
            all_passed = all_passed and success
        
        # Search assets
        success, _ = self.run_test(
            "Search assets by name",
            "GET",
            "/api/assets?search=Laptop",
            200,
            verify_fn=lambda r: 'items' in r and 'pagination' in r
        )
        all_passed = all_passed and success
        
        # Filter by assigned_to
        success, _ = self.run_test(
            "Filter assets by assigned_to",
            "GET",
            f"/api/assets?assigned_to={self.user_id}",
            200,
            verify_fn=lambda r: 'items' in r and 'pagination' in r
        )
        all_passed = all_passed and success
        
        return all_passed

    # ========== Cleanup ==========
    def test_cleanup(self):
        """Clean up test data"""
        self.log("\n" + "=" * 60)
        self.log("PHASE 13: Cleanup")
        self.log("=" * 60)
        
        # Delete test category
        if self.created_category_id:
            success, _ = self.run_test(
                "Delete test category",
                "DELETE",
                f"/api/assets/categories/{self.created_category_id}",
                200
            )
        
        return True

    # ========== Main Test Runner ==========
    def run_all_tests(self):
        """Run all test phases"""
        self.log("=" * 60)
        self.log("CV. Dewi Aditya ERP - Asset Management Refactor Test")
        self.log("Testing 41 endpoints after 2392 LOC → 14 modules split")
        self.log("=" * 60)
        
        # Phase 1: Authentication
        if not self.test_login():
            self.log("\n❌ CRITICAL: Login failed, cannot proceed", "ERROR")
            return False
        
        # Phase 2: Dashboard
        self.test_dashboard()
        
        # Phase 3: Categories CRUD
        self.test_categories_crud()
        
        # Phase 4: Asset Creation
        self.test_asset_creation()
        
        # Phase 5: CRITICAL - Literal Path Resolution
        self.test_literal_paths()
        
        # Phase 6: Asset Lifecycle
        self.test_asset_lifecycle()
        
        # Phase 7: Binary Endpoints
        self.test_binary_endpoints()
        
        # Phase 8: Disposal Flow
        self.test_disposal_flow()
        
        # Phase 9: Bulk Import
        self.test_bulk_import()
        
        # Phase 10: Reports
        self.test_reports()
        
        # Phase 11: Predictive Maintenance
        self.test_predictive_maintenance()
        
        # Phase 12: Asset List & Filters
        self.test_asset_list_filters()
        
        # Phase 13: Cleanup
        self.test_cleanup()
        
        # Print summary
        self.print_summary()
        
        return self.tests_passed == self.tests_run

    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 60)
        self.log("TEST SUMMARY")
        self.log("=" * 60)
        self.log(f"Total tests run: {self.tests_run}")
        self.log(f"Tests passed: {self.tests_passed}")
        self.log(f"Tests failed: {self.tests_run - self.tests_passed}")
        self.log(f"Success rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        
        # Print failed tests
        failed_tests = [t for t in self.test_results if t['status'] == 'FAILED']
        if failed_tests:
            self.log("\n❌ FAILED TESTS:")
            for test in failed_tests:
                self.log(f"  - {test['test']}")
                self.log(f"    Endpoint: {test['endpoint']}")
                if 'reason' in test:
                    self.log(f"    Reason: {test['reason']}")
                elif 'expected' in test:
                    self.log(f"    Expected: {test['expected']}, Got: {test['actual']}")
        
        self.log("=" * 60)


def main():
    tester = AssetRefactorTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
