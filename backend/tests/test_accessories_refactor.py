#!/usr/bin/env python3
"""
Dewi Accessories Module - Refactoring Verification Test
Tests all 24 endpoints after splitting dewi_accessories_full.py into 7 modular files

Original: dewi_accessories_full.py (1199 LOC, 24 endpoints)
Refactored into:
- dewi_accessories_items.py (items CRUD)
- dewi_accessories_stock.py (stock management)
- dewi_accessories_requests.py (internal requests)
- dewi_accessories_loans.py (loans management)
- dewi_accessories_opname.py (stock opname)
- dewi_accessories_purchase.py (purchase requests)
- dewi_accessories_dashboard.py (dashboard)
- dewi_accessories_full.py (orchestrator)

SSOT integrations:
- rahaza_materials (items)
- rahaza_material_stock (stock)
- wh_opname_sessions2 (opname)

Admin credentials: admin@garment.com / Admin@123
"""

import requests
import sys
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class AccessoriesRefactorTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        
        # Store created IDs for cleanup and testing
        self.created_item_id = None
        self.created_request_id = None
        self.created_loan_id = None
        self.created_opname_id = None
        self.created_pr_id = None
        
    def log(self, message, level="INFO"):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
    
    def run_test(self, name, method, endpoint, expected_status, data=None, description=""):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        self.tests_run += 1
        self.log(f"Testing {name}...", "TEST")
        if description:
            self.log(f"  → {description}", "INFO")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - {name} (Status: {response.status_code})", "PASS")
                return True, response
            else:
                self.log(f"❌ FAIL - {name} (Expected {expected_status}, got {response.status_code})", "FAIL")
                self.log(f"  Response: {response.text[:200]}", "DEBUG")
                self.failed_tests.append({
                    'name': name,
                    'endpoint': endpoint,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:500]
                })
                return False, response
        
        except Exception as e:
            self.log(f"❌ ERROR - {name}: {str(e)}", "ERROR")
            self.failed_tests.append({
                'name': name,
                'endpoint': endpoint,
                'error': str(e)
            })
            return False, None
    
    def test_health(self):
        """Test health check endpoint"""
        self.log("=" * 60, "INFO")
        self.log("HEALTH CHECK", "INFO")
        self.log("=" * 60, "INFO")
        return self.run_test(
            "Health Check",
            "GET",
            "/api/health",
            200,
            description="Verify API is running"
        )
    
    def test_login(self):
        """Test admin login"""
        self.log("=" * 60, "INFO")
        self.log("AUTHENTICATION", "INFO")
        self.log("=" * 60, "INFO")
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"},
            description="Login with admin credentials"
        )
        if success and response:
            try:
                data = response.json()
                self.token = data.get('token')
                if self.token:
                    self.log(f"✓ Token obtained: {self.token[:20]}...", "INFO")
                    return True
                else:
                    self.log("✗ No token in response", "ERROR")
                    return False
            except Exception as e:
                self.log(f"✗ Failed to parse login response: {e}", "ERROR")
                return False
        return False
    
    def test_items_crud(self):
        """Test Items CRUD endpoints (4 endpoints)"""
        self.log("=" * 60, "INFO")
        self.log("ITEMS CRUD (4 endpoints)", "INFO")
        self.log("=" * 60, "INFO")
        
        # 1. GET /api/acc/items - List items
        success, response = self.run_test(
            "Items - List",
            "GET",
            "/api/acc/items",
            200,
            description="GET /api/acc/items - List all accessory items"
        )
        
        # 2. POST /api/acc/items - Create item
        test_item = {
            "name": f"Test Accessory {datetime.now().strftime('%H%M%S')}",
            "code": f"TEST-ACC-{datetime.now().strftime('%H%M%S')}",
            "category": "Testing",
            "unit": "pcs",
            "description": "Test item for refactoring verification",
            "min_stock": 10,
            "supplier": "Test Supplier"
        }
        success, response = self.run_test(
            "Items - Create",
            "POST",
            "/api/acc/items",
            201,
            data=test_item,
            description="POST /api/acc/items - Create new accessory item"
        )
        if success and response:
            try:
                data = response.json()
                self.created_item_id = data.get('id')
                self.log(f"✓ Created item ID: {self.created_item_id}", "INFO")
            except Exception as e:
                self.log(f"✗ Failed to parse create response: {e}", "ERROR")
        
        # 3. PUT /api/acc/items/{item_id} - Update item
        if self.created_item_id:
            update_data = {
                "name": "Updated Test Accessory",
                "description": "Updated description"
            }
            self.run_test(
                "Items - Update",
                "PUT",
                f"/api/acc/items/{self.created_item_id}",
                200,
                data=update_data,
                description=f"PUT /api/acc/items/{self.created_item_id} - Update item"
            )
        
        # 4. DELETE /api/acc/items/{item_id} - Delete item (soft delete)
        if self.created_item_id:
            self.run_test(
                "Items - Delete",
                "DELETE",
                f"/api/acc/items/{self.created_item_id}",
                200,
                description=f"DELETE /api/acc/items/{self.created_item_id} - Soft delete item"
            )
    
    def test_stock_management(self):
        """Test Stock Management endpoints (4 endpoints)"""
        self.log("=" * 60, "INFO")
        self.log("STOCK MANAGEMENT (4 endpoints)", "INFO")
        self.log("=" * 60, "INFO")
        
        # Create a test item for stock operations
        test_item = {
            "name": f"Stock Test Item {datetime.now().strftime('%H%M%S')}",
            "code": f"STK-TEST-{datetime.now().strftime('%H%M%S')}",
            "category": "Testing",
            "unit": "pcs"
        }
        success, response = self.run_test(
            "Stock - Create Test Item",
            "POST",
            "/api/acc/items",
            201,
            data=test_item,
            description="Create item for stock testing"
        )
        
        stock_test_item_id = None
        if success and response:
            try:
                data = response.json()
                stock_test_item_id = data.get('id')
                self.log(f"✓ Stock test item ID: {stock_test_item_id}", "INFO")
            except Exception as e:
                self.log(f"✗ Failed to parse response: {e}", "ERROR")
        
        # 5. GET /api/acc/stock - Stock overview
        self.run_test(
            "Stock - Overview",
            "GET",
            "/api/acc/stock",
            200,
            description="GET /api/acc/stock - Get stock overview"
        )
        
        # 6. GET /api/acc/stock/movements - Stock movements
        self.run_test(
            "Stock - Movements",
            "GET",
            "/api/acc/stock/movements",
            200,
            description="GET /api/acc/stock/movements - Get stock movements"
        )
        
        # 7. POST /api/acc/stock/receive - Receive stock
        if stock_test_item_id:
            receive_data = {
                "acc_id": stock_test_item_id,
                "qty": 100,
                "notes": "Test stock receive",
                "ref_type": "manual"
            }
            self.run_test(
                "Stock - Receive",
                "POST",
                "/api/acc/stock/receive",
                201,
                data=receive_data,
                description="POST /api/acc/stock/receive - Receive stock"
            )
        
        # 8. POST /api/acc/stock/issue - Issue stock
        if stock_test_item_id:
            issue_data = {
                "acc_id": stock_test_item_id,
                "qty": 10,
                "notes": "Test stock issue",
                "ref_type": "manual"
            }
            self.run_test(
                "Stock - Issue",
                "POST",
                "/api/acc/stock/issue",
                201,
                data=issue_data,
                description="POST /api/acc/stock/issue - Issue stock"
            )
    
    def test_internal_requests(self):
        """Test Internal Requests endpoints (3 endpoints)"""
        self.log("=" * 60, "INFO")
        self.log("INTERNAL REQUESTS (3 endpoints)", "INFO")
        self.log("=" * 60, "INFO")
        
        # 9. GET /api/acc/internal-requests - List requests
        self.run_test(
            "Internal Requests - List",
            "GET",
            "/api/acc/internal-requests",
            200,
            description="GET /api/acc/internal-requests - List internal requests"
        )
        
        # 10. POST /api/acc/internal-requests - Create request
        request_data = {
            "divisi": "Produksi",
            "requester_name": "Test User",
            "purpose": "Testing refactoring",
            "items": [
                {
                    "acc_id": "test-id",
                    "acc_name": "Test Item",
                    "qty_requested": 5,
                    "unit": "pcs"
                }
            ]
        }
        success, response = self.run_test(
            "Internal Requests - Create",
            "POST",
            "/api/acc/internal-requests",
            201,
            data=request_data,
            description="POST /api/acc/internal-requests - Create internal request"
        )
        if success and response:
            try:
                data = response.json()
                self.created_request_id = data.get('id')
                self.log(f"✓ Created request ID: {self.created_request_id}", "INFO")
            except Exception as e:
                self.log(f"✗ Failed to parse response: {e}", "ERROR")
        
        # 11. PUT /api/acc/internal-requests/{req_id} - Update request
        if self.created_request_id:
            update_data = {
                "status": "Approved",
                "admin_notes": "Approved for testing"
            }
            self.run_test(
                "Internal Requests - Update (Approve)",
                "PUT",
                f"/api/acc/internal-requests/{self.created_request_id}",
                200,
                data=update_data,
                description=f"PUT /api/acc/internal-requests/{self.created_request_id} - Approve request"
            )
    
    def test_loans(self):
        """Test Loans endpoints (3 endpoints)"""
        self.log("=" * 60, "INFO")
        self.log("LOANS (3 endpoints)", "INFO")
        self.log("=" * 60, "INFO")
        
        # 12. GET /api/acc/loans - List loans
        self.run_test(
            "Loans - List",
            "GET",
            "/api/acc/loans",
            200,
            description="GET /api/acc/loans - List all loans"
        )
        
        # 13. POST /api/acc/loans - Create loan
        loan_data = {
            "borrower_name": "Test Borrower",
            "borrower_divisi": "Testing",
            "purpose": "Testing refactoring",
            "items": [
                {
                    "acc_id": "test-id",
                    "acc_name": "Test Item",
                    "qty": 2,
                    "unit": "pcs"
                }
            ]
        }
        success, response = self.run_test(
            "Loans - Create",
            "POST",
            "/api/acc/loans",
            201,
            data=loan_data,
            description="POST /api/acc/loans - Create loan"
        )
        if success and response:
            try:
                data = response.json()
                self.created_loan_id = data.get('id')
                self.log(f"✓ Created loan ID: {self.created_loan_id}", "INFO")
            except Exception as e:
                self.log(f"✗ Failed to parse response: {e}", "ERROR")
        
        # 14. PUT /api/acc/loans/{loan_id}/return - Return loan
        if self.created_loan_id:
            return_data = {
                "return_notes": "Returned in good condition"
            }
            self.run_test(
                "Loans - Return",
                "PUT",
                f"/api/acc/loans/{self.created_loan_id}/return",
                200,
                data=return_data,
                description=f"PUT /api/acc/loans/{self.created_loan_id}/return - Return loan"
            )
    
    def test_opname(self):
        """Test Opname endpoints (6 endpoints)"""
        self.log("=" * 60, "INFO")
        self.log("OPNAME (6 endpoints)", "INFO")
        self.log("=" * 60, "INFO")
        
        # 15. GET /api/acc/opname - List opname sessions
        self.run_test(
            "Opname - List Sessions",
            "GET",
            "/api/acc/opname",
            200,
            description="GET /api/acc/opname - List opname sessions"
        )
        
        # 16. POST /api/acc/opname - Create opname session
        opname_data = {
            "notes": "Test opname session for refactoring verification"
        }
        success, response = self.run_test(
            "Opname - Create Session",
            "POST",
            "/api/acc/opname",
            201,
            data=opname_data,
            description="POST /api/acc/opname - Create opname session"
        )
        if success and response:
            try:
                data = response.json()
                self.created_opname_id = data.get('id')
                self.log(f"✓ Created opname session ID: {self.created_opname_id}", "INFO")
            except Exception as e:
                self.log(f"✗ Failed to parse response: {e}", "ERROR")
        
        # 17. GET /api/acc/opname/{session_id} - Get opname detail
        if self.created_opname_id:
            self.run_test(
                "Opname - Get Detail",
                "GET",
                f"/api/acc/opname/{self.created_opname_id}",
                200,
                description=f"GET /api/acc/opname/{self.created_opname_id} - Get opname detail"
            )
        
        # 18. PUT /api/acc/opname/{session_id}/count - Update count
        if self.created_opname_id:
            # Get the session detail to find an item to count
            success, response = self.run_test(
                "Opname - Get Detail for Count",
                "GET",
                f"/api/acc/opname/{self.created_opname_id}",
                200,
                description="Get opname detail to find item for counting"
            )
            
            if success and response:
                try:
                    data = response.json()
                    lines = data.get('lines', [])
                    if lines:
                        first_item = lines[0]
                        count_data = {
                            "acc_id": first_item.get('acc_id'),
                            "counted_qty": first_item.get('system_qty', 0),
                            "notes": "Test count"
                        }
                        self.run_test(
                            "Opname - Update Count",
                            "PUT",
                            f"/api/acc/opname/{self.created_opname_id}/count",
                            200,
                            data=count_data,
                            description=f"PUT /api/acc/opname/{self.created_opname_id}/count - Update count"
                        )
                except Exception as e:
                    self.log(f"✗ Failed to parse opname detail: {e}", "ERROR")
        
        # 19. POST /api/acc/opname/{session_id}/complete - Complete opname
        if self.created_opname_id:
            self.run_test(
                "Opname - Complete Session",
                "POST",
                f"/api/acc/opname/{self.created_opname_id}/complete",
                200,
                description=f"POST /api/acc/opname/{self.created_opname_id}/complete - Complete opname"
            )
        
        # 20. POST /api/acc/opname/{session_id}/cancel - Cancel opname (create new session first)
        cancel_opname_data = {
            "notes": "Test opname for cancellation"
        }
        success, response = self.run_test(
            "Opname - Create Session for Cancel",
            "POST",
            "/api/acc/opname",
            201,
            data=cancel_opname_data,
            description="Create opname session for cancel test"
        )
        
        cancel_opname_id = None
        if success and response:
            try:
                data = response.json()
                cancel_opname_id = data.get('id')
            except Exception as e:
                self.log(f"✗ Failed to parse response: {e}", "ERROR")
        
        if cancel_opname_id:
            self.run_test(
                "Opname - Cancel Session",
                "POST",
                f"/api/acc/opname/{cancel_opname_id}/cancel",
                200,
                description=f"POST /api/acc/opname/{cancel_opname_id}/cancel - Cancel opname"
            )
    
    def test_purchase_requests(self):
        """Test Purchase Requests endpoints (3 endpoints)"""
        self.log("=" * 60, "INFO")
        self.log("PURCHASE REQUESTS (3 endpoints)", "INFO")
        self.log("=" * 60, "INFO")
        
        # 21. GET /api/acc/purchase-requests - List purchase requests
        self.run_test(
            "Purchase Requests - List",
            "GET",
            "/api/acc/purchase-requests",
            200,
            description="GET /api/acc/purchase-requests - List purchase requests"
        )
        
        # 22. POST /api/acc/purchase-requests - Create purchase request
        pr_data = {
            "priority": "Normal",
            "purpose": "Testing refactoring",
            "supplier": "Test Supplier",
            "items": [
                {
                    "acc_id": "test-id",
                    "acc_name": "Test Item",
                    "qty_requested": 50,
                    "estimated_price": 10000,
                    "unit": "pcs"
                }
            ],
            "notes": "Test purchase request"
        }
        success, response = self.run_test(
            "Purchase Requests - Create",
            "POST",
            "/api/acc/purchase-requests",
            201,
            data=pr_data,
            description="POST /api/acc/purchase-requests - Create purchase request"
        )
        if success and response:
            try:
                data = response.json()
                self.created_pr_id = data.get('id')
                self.log(f"✓ Created PR ID: {self.created_pr_id}", "INFO")
            except Exception as e:
                self.log(f"✗ Failed to parse response: {e}", "ERROR")
        
        # 23. PUT /api/acc/purchase-requests/{pr_id} - Update purchase request
        if self.created_pr_id:
            update_data = {
                "status": "Submitted"
            }
            self.run_test(
                "Purchase Requests - Update (Submit)",
                "PUT",
                f"/api/acc/purchase-requests/{self.created_pr_id}",
                200,
                data=update_data,
                description=f"PUT /api/acc/purchase-requests/{self.created_pr_id} - Submit PR"
            )
    
    def test_dashboard(self):
        """Test Dashboard endpoint (1 endpoint)"""
        self.log("=" * 60, "INFO")
        self.log("DASHBOARD (1 endpoint)", "INFO")
        self.log("=" * 60, "INFO")
        
        # 24. GET /api/acc/dashboard - Dashboard overview
        self.run_test(
            "Dashboard - Overview",
            "GET",
            "/api/acc/dashboard",
            200,
            description="GET /api/acc/dashboard - Get dashboard overview with statistics"
        )
    
    def print_summary(self):
        """Print test summary"""
        self.log("=" * 60, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 60, "INFO")
        self.log(f"Total Tests: {self.tests_run}", "INFO")
        self.log(f"Passed: {self.tests_passed}", "INFO")
        self.log(f"Failed: {len(self.failed_tests)}", "INFO")
        self.log(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%", "INFO")
        
        if self.failed_tests:
            self.log("=" * 60, "INFO")
            self.log("FAILED TESTS DETAILS", "ERROR")
            self.log("=" * 60, "INFO")
            for i, test in enumerate(self.failed_tests, 1):
                self.log(f"{i}. {test.get('name', 'Unknown')}", "ERROR")
                self.log(f"   Endpoint: {test.get('endpoint', 'N/A')}", "ERROR")
                if 'error' in test:
                    self.log(f"   Error: {test['error']}", "ERROR")
                else:
                    self.log(f"   Expected: {test.get('expected', 'N/A')}, Got: {test.get('actual', 'N/A')}", "ERROR")
                    if test.get('response'):
                        self.log(f"   Response: {test['response'][:200]}", "ERROR")
        
        return self.tests_passed == self.tests_run

def main():
    """Main test execution"""
    print("\n" + "=" * 60)
    print("DEWI ACCESSORIES MODULE - REFACTORING VERIFICATION")
    print("Testing 24 endpoints across 7 modular files")
    print("=" * 60 + "\n")
    
    tester = AccessoriesRefactorTester()
    
    # Run tests in sequence
    if not tester.test_health():
        print("\n❌ Health check failed. Aborting tests.")
        return 1
    
    if not tester.test_login():
        print("\n❌ Login failed. Cannot proceed with authenticated tests.")
        return 1
    
    # Run all module tests
    tester.test_items_crud()
    tester.test_stock_management()
    tester.test_internal_requests()
    tester.test_loans()
    tester.test_opname()
    tester.test_purchase_requests()
    tester.test_dashboard()
    
    # Print summary
    all_passed = tester.print_summary()
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
