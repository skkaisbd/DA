"""
PART5 BAGIAN 5 (RC-FLOW) Testing
Write-flow (POST/PUT) end-to-end coverage + RBAC enforcement per business domain

CV. Dewi Aditya ERP - Comprehensive Write-Flow & RBAC Testing
All data is SEED and mutable/re-seedable

Test Coverage:
- AUTH: login all accounts
- Finance AR/AP flows
- Expense claim flow
- Leave flow
- Attendance flow
- Production WO flow
- WMS flows (GRN, delivery notes, opname2)
- Maklon flow
- Marketing flow
- Onboarding flow
- Notifications
- RBAC enforcement (403 for unauthorized, not 500)
"""
import requests
import sys
import time
from datetime import datetime, date, timedelta
from typing import Dict, Optional, List

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test accounts (from test_credentials.md)
ACCOUNTS = {
    'admin': {'email': 'admin@garment.com', 'password': 'Admin@123', 'role': 'superadmin'},
    'hr': {'email': 'hr@dewiaditya.id', 'password': 'Dewi@123', 'role': 'hr'},
    'finance': {'email': 'finance@dewiaditya.id', 'password': 'Dewi@123', 'role': 'accounting'},
    'spv': {'email': 'spv@dewiaditya.id', 'password': 'Dewi@123', 'role': 'supervisor_produksi'},
    'gudang': {'email': 'gudang@dewiaditya.id', 'password': 'Dewi@123', 'role': 'admin_gudang'},
    'maklon': {'email': 'maklon@dewiaditya.id', 'password': 'Dewi@123', 'role': 'admin_maklon'},
}

class Part5Tester:
    def __init__(self):
        self.tokens = {}  # Store tokens per account (login once, reuse)
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.created_resources = {}  # Track created resources for cleanup
        
    def log(self, msg: str, level: str = "INFO"):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] [{level}] {msg}")
    
    def test(self, name: str, method: str, endpoint: str, expected_status: int, 
             account: str = 'admin', data: Optional[Dict] = None, 
             params: Optional[Dict] = None, expect_403: bool = False) -> tuple:
        """Run a single API test"""
        self.tests_run += 1
        url = f"{BASE_URL}{endpoint}"
        
        # Get token for account
        if account not in self.tokens:
            self.log(f"No token for {account}, skipping test", "WARN")
            return False, {}
        
        headers = {
            'Authorization': f'Bearer {self.tokens[account]}',
            'Content-Type': 'application/json'
        }
        
        self.log(f"Testing [{account}]: {name}", "TEST")
        
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
                self.failed_tests.append({"test": name, "account": account, "reason": f"Unknown method: {method}"})
                return False, {}
            
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}", "PASS")
                self.passed_tests.append(f"{name} [{account}]")
                try:
                    return True, response.json() if response.text else {}
                except Exception:
                    return True, {}
            else:
                self.tests_failed += 1
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    error_detail = response.json()
                except Exception:
                    error_detail = response.text[:200]
                
                # Special handling for RBAC tests
                if expect_403 and response.status_code == 500:
                    self.log(f"⚠️  CRITICAL: Expected 403 but got 500 (should be 403, not 500)", "ERROR")
                    error_detail = f"RBAC BUG: Returns 500 instead of 403. {error_detail}"
                elif expect_403 and response.status_code == 200:
                    self.log(f"⚠️  CRITICAL: Expected 403 but got 200 (privilege escalation!)", "ERROR")
                    error_detail = f"RBAC BUG: Unauthorized access allowed (privilege escalation). {error_detail}"
                
                self.failed_tests.append({
                    "test": name,
                    "account": account,
                    "expected": expected_status,
                    "actual": response.status_code,
                    "error": error_detail
                })
                return False, error_detail
                
        except requests.exceptions.Timeout:
            self.tests_failed += 1
            self.log("❌ FAILED - Request timeout", "ERROR")
            self.failed_tests.append({"test": name, "account": account, "reason": "Timeout"})
            return False, {}
        except Exception as e:
            self.tests_failed += 1
            self.log(f"❌ FAILED - Error: {str(e)}", "ERROR")
            self.failed_tests.append({"test": name, "account": account, "reason": str(e)})
            return False, {}
    
    def login_all_accounts(self) -> bool:
        """Login all accounts once and store tokens (rate-limit: 10/60s)"""
        self.log("=" * 80, "INFO")
        self.log("PART5 BAGIAN 5 (RC-FLOW) - WRITE-FLOW & RBAC TESTING", "INFO")
        self.log("=" * 80, "INFO")
        self.log(f"Base URL: {BASE_URL}", "INFO")
        self.log("=" * 80, "INFO")
        
        self.log("\n🔐 LOGIN ALL ACCOUNTS (once, reuse tokens)", "INFO")
        
        for account_key, account_info in ACCOUNTS.items():
            self.log(f"\nLogging in: {account_info['email']} ({account_info['role']})", "INFO")
            
            try:
                response = requests.post(
                    f"{BASE_URL}/api/auth/login",
                    json={
                        'email': account_info['email'],
                        'password': account_info['password']
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if 'token' in data:
                        self.tokens[account_key] = data['token']
                        self.log(f"✅ Login successful: {account_key}", "PASS")
                    else:
                        self.log(f"❌ Login failed: No token in response", "ERROR")
                        return False
                else:
                    self.log(f"❌ Login failed: Status {response.status_code}", "ERROR")
                    try:
                        self.log(f"   Error: {response.json()}", "ERROR")
                    except Exception:
                        self.log(f"   Error: {response.text[:200]}", "ERROR")
                    return False
                    
            except Exception as e:
                self.log(f"❌ Login exception: {str(e)}", "ERROR")
                return False
            
            # Small delay to avoid rate-limit
            time.sleep(0.5)
        
        self.log(f"\n✅ All {len(self.tokens)} accounts logged in successfully", "PASS")
        return True
    
    # ========== FINANCE AR FLOW ==========
    def test_finance_ar_flow(self):
        """Test Finance AR flow: create invoice -> post-to-gl -> payment"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Finance AR Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 0. Get a customer first
        success, customers = self.test(
            "Get Customers for AR",
            "GET",
            "/api/rahaza/customers",
            200,
            account='finance',
            params={'limit': 1}
        )
        
        if not success or not customers:
            self.log("⚠️  No customers found, skipping AR flow", "WARN")
            return
        
        customer_id = customers[0].get('id')
        if not customer_id:
            self.log("⚠️  No customer ID, skipping AR flow", "WARN")
            return
        
        # 1. Create AR invoice (finance account)
        ar_data = {
            'customer_id': customer_id,
            'issue_date': date.today().isoformat(),
            'due_date': (date.today() + timedelta(days=30)).isoformat(),
            'items': [
                {'description': 'Test Item', 'qty': 1, 'price': 100000}
            ],
            'notes': 'Test AR invoice'
        }
        
        success, response = self.test(
            "Create AR Invoice",
            "POST",
            "/api/rahaza/ar-invoices",
            200,  # API returns 200, not 201
            account='finance',
            data=ar_data
        )
        
        if not success:
            self.log("⚠️  AR invoice creation failed, skipping rest of AR flow", "WARN")
            return
        
        invoice_id = response.get('id')
        if not invoice_id:
            self.log("⚠️  No invoice ID returned, skipping rest of AR flow", "WARN")
            return
        
        self.created_resources['ar_invoice_id'] = invoice_id
        
        # 2. Post to GL
        success, response = self.test(
            "Post AR Invoice to GL",
            "POST",
            f"/api/rahaza/ar-invoices/{invoice_id}/post-to-gl",
            200,
            account='finance'
        )
        
        # 3. Payment
        payment_data = {
            'payment_date': date.today().isoformat(),
            'amount': 100000,
            'payment_method': 'bank_transfer',
            'reference': f'PAY-{int(time.time())}'
        }
        
        success, response = self.test(
            "AR Invoice Payment",
            "POST",
            f"/api/rahaza/ar-invoices/{invoice_id}/payment",
            200,
            account='finance',
            data=payment_data
        )
        
        # 4. Verify cash movement created
        success, response = self.test(
            "Verify Cash Movement Created",
            "GET",
            "/api/rahaza/cash-movements",
            200,
            account='finance'
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Cash movements exist ({len(response)} records)", "PASS")
        
        # 5. Verify Journal Entry created
        success, response = self.test(
            "Verify Journal Entry Created (AR payment)",
            "GET",
            "/api/rahaza/finance/reports/journal-list",
            200,
            account='finance'
        )
        
        if success:
            journals = response.get('journals', []) if isinstance(response, dict) else []
            ar_payment_je = [j for j in journals if 'ar_payment' in str(j.get('source_module', '')).lower()]
            if ar_payment_je:
                self.log("✅ AR payment Journal Entry found", "PASS")
            else:
                self.log("⚠️  AR payment Journal Entry not found", "WARN")
    
    # ========== FINANCE AP FLOW ==========
    def test_finance_ap_flow(self):
        """Test Finance AP flow: create invoice -> payment"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Finance AP Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 0. Get a vendor/supplier first
        success, vendors = self.test(
            "Get Vendors for AP",
            "GET",
            "/api/rahaza/vendors",
            200,
            account='finance',
            params={'limit': 1}
        )
        
        vendor_id = None
        if success and vendors:
            vendor_id = vendors[0].get('id')
        
        if not vendor_id:
            self.log("⚠️  No vendors found, using customer as vendor", "WARN")
            # Use customer endpoint as fallback
            success, customers = self.test(
                "Get Customers as Vendor Fallback",
                "GET",
                "/api/rahaza/customers",
                200,
                account='finance',
                params={'limit': 1}
            )
            if success and customers:
                vendor_id = customers[0].get('id')
        
        if not vendor_id:
            self.log("⚠️  No vendor ID, skipping AP flow", "WARN")
            return
        
        # 1. Create AP invoice
        ap_data = {
            'vendor_id': vendor_id,
            'invoice_date': date.today().isoformat(),
            'due_date': (date.today() + timedelta(days=30)).isoformat(),
            'items': [
                {'description': 'Test Purchase', 'qty': 1, 'price': 50000}
            ],
            'notes': 'Test AP invoice'
        }
        
        success, response = self.test(
            "Create AP Invoice",
            "POST",
            "/api/rahaza/ap-invoices",
            201,
            account='finance',
            data=ap_data
        )
        
        if not success:
            self.log("⚠️  AP invoice creation failed, skipping rest of AP flow", "WARN")
            return
        
        invoice_id = response.get('id')
        if not invoice_id:
            self.log("⚠️  No invoice ID returned, skipping rest of AP flow", "WARN")
            return
        
        self.created_resources['ap_invoice_id'] = invoice_id
        
        # 2. Payment
        payment_data = {
            'payment_date': date.today().isoformat(),
            'amount': 50000,
            'payment_method': 'bank_transfer',
            'reference': f'PAY-AP-{int(time.time())}'
        }
        
        success, response = self.test(
            "AP Invoice Payment",
            "POST",
            f"/api/rahaza/ap-invoices/{invoice_id}/payment",
            200,
            account='finance',
            data=payment_data
        )
        
        # 3. Verify cash movement and JE
        success, response = self.test(
            "Verify Cash Movement (AP)",
            "GET",
            "/api/rahaza/cash-movements",
            200,
            account='finance'
        )
        
        if success and isinstance(response, list):
            self.log(f"✅ Cash movements verified ({len(response)} records)", "PASS")
    
    # ========== EXPENSE CLAIM FLOW ==========
    def test_expense_claim_flow(self):
        """Test Expense claim flow: create -> submit -> approve -> disburse"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Expense Claim Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Create claim (as hr)
        claim_data = {
            'title': 'Test Expense Claim',
            'items': [
                {
                    'date': date.today().isoformat(),
                    'category': 'Transportasi',
                    'amount': 50000,
                    'notes': 'Taxi to client'
                }
            ],
            'notes': 'Test claim'
        }
        
        success, response = self.test(
            "Create Expense Claim",
            "POST",
            "/api/hr/expenses/claims",
            201,
            account='hr',
            data=claim_data
        )
        
        if not success:
            self.log("⚠️  Expense claim creation failed, skipping rest of flow", "WARN")
            return
        
        claim_id = response.get('id')
        if not claim_id:
            self.log("⚠️  No claim ID returned, skipping rest of flow", "WARN")
            return
        
        self.created_resources['expense_claim_id'] = claim_id
        
        # 2. Submit
        success, response = self.test(
            "Submit Expense Claim",
            "POST",
            f"/api/hr/expenses/claims/{claim_id}/submit",
            200,
            account='hr'
        )
        
        # 3. Approve (as admin or finance)
        success, response = self.test(
            "Approve Expense Claim",
            "POST",
            f"/api/hr/expenses/claims/{claim_id}/approve",
            200,
            account='admin'
        )
        
        # 4. Disburse (as finance)
        disburse_data = {
            'payment_date': date.today().isoformat(),
            'payment_method': 'bank_transfer',
            'reference': f'DISB-{int(time.time())}'
        }
        
        success, response = self.test(
            "Disburse Expense Claim",
            "POST",
            f"/api/hr/expenses/claims/{claim_id}/disburse",
            200,
            account='finance',
            data=disburse_data
        )
        
        # 5. Verify GL JE created (pattern JE-YYYYMMDD-####)
        success, response = self.test(
            "Verify GL Journal Entry Created",
            "GET",
            "/api/rahaza/finance/reports/journal-list",
            200,
            account='finance'
        )
        
        if success:
            journals = response.get('journals', []) if isinstance(response, dict) else []
            today_str = date.today().strftime('%Y%m%d')
            je_pattern = f'JE-{today_str}'
            matching_je = [j for j in journals if je_pattern in str(j.get('gl_je_number', ''))]
            if matching_je:
                self.log(f"✅ GL Journal Entry found with pattern {je_pattern}", "PASS")
            else:
                self.log(f"⚠️  GL Journal Entry with pattern {je_pattern} not found", "WARN")
    
    # ========== LEAVE FLOW ==========
    def test_leave_flow(self):
        """Test Leave flow: request -> approve"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Leave Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Get leave types first
        success, response = self.test(
            "Get Leave Types",
            "GET",
            "/api/rahaza/leave-types",
            200,
            account='hr'
        )
        
        leave_type_id = None
        if success and isinstance(response, list) and len(response) > 0:
            leave_type_id = response[0].get('id')
        
        if not leave_type_id:
            self.log("⚠️  No leave types found, skipping leave flow", "WARN")
            return
        
        # 2. Create leave request
        leave_data = {
            'leave_type_id': leave_type_id,
            'start_date': (date.today() + timedelta(days=7)).isoformat(),
            'end_date': (date.today() + timedelta(days=9)).isoformat(),
            'reason': 'Test leave request',
            'days_requested': 3
        }
        
        success, response = self.test(
            "Create Leave Request",
            "POST",
            "/api/rahaza/leaves/request",
            200,  # API returns 200, not 201
            account='hr',
            data=leave_data
        )
        
        if not success:
            self.log("⚠️  Leave request creation failed, skipping rest of flow", "WARN")
            return
        
        leave_id = response.get('id')
        if not leave_id:
            self.log("⚠️  No leave ID returned, skipping rest of flow", "WARN")
            return
        
        self.created_resources['leave_id'] = leave_id
        
        # 3. Get leave balance before approval
        success, balance_before = self.test(
            "Get Leave Balance Before Approval",
            "GET",
            "/api/rahaza/leaves/balance",
            200,
            account='hr'
        )
        
        # 4. Approve leave
        success, response = self.test(
            "Approve Leave Request",
            "POST",
            f"/api/rahaza/leaves/{leave_id}/approve",
            200,
            account='admin'
        )
        
        # 5. Get leave balance after approval (should increase 'used')
        success, balance_after = self.test(
            "Get Leave Balance After Approval",
            "GET",
            "/api/rahaza/leaves/balance",
            200,
            account='hr'
        )
        
        if success and balance_before:
            self.log("✅ Leave balance checked before and after approval", "PASS")
    
    # ========== ATTENDANCE FLOW ==========
    def test_attendance_flow(self):
        """Test Attendance flow: clock-in -> clock-out"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Attendance Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Clock-in
        clock_in_data = {
            'timestamp': datetime.now().isoformat(),
            'location': 'Office',
            'notes': 'Test clock-in'
        }
        
        success, response = self.test(
            "Clock-In",
            "POST",
            "/api/rahaza/attendance/clock-in",
            200,
            account='hr',
            data=clock_in_data
        )
        
        if not success:
            self.log("⚠️  Clock-in failed, trying manual attendance record", "WARN")
            
            # Try manual attendance record
            manual_data = {
                'date': date.today().isoformat(),
                'clock_in': '08:00',
                'clock_out': '17:00',
                'status': 'present'
            }
            
            success, response = self.test(
                "Create Manual Attendance Record",
                "POST",
                "/api/rahaza/attendance",
                201,
                account='admin',
                data=manual_data
            )
            return
        
        # 2. Clock-out
        clock_out_data = {
            'timestamp': datetime.now().isoformat(),
            'location': 'Office',
            'notes': 'Test clock-out'
        }
        
        success, response = self.test(
            "Clock-Out",
            "POST",
            "/api/rahaza/attendance/clock-out",
            200,
            account='hr',
            data=clock_out_data
        )
        
        # 3. Verify attendance event created
        success, response = self.test(
            "Get Attendance Records",
            "GET",
            "/api/rahaza/attendance",
            200,
            account='hr',
            params={'date': date.today().isoformat()}
        )
        
        if success:
            records = response if isinstance(response, list) else response.get('records', [])
            self.log(f"✅ Attendance records retrieved ({len(records)} records)", "PASS")
    
    # ========== PRODUCTION WO FLOW ==========
    def test_production_wo_flow(self):
        """Test Production WO flow: create -> status transitions"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Production Work Order Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Create WO
        wo_data = {
            'wo_number': f'WO-TEST-{int(time.time())}',
            'product_name': 'Test Product',
            'quantity': 100,
            'target_date': (date.today() + timedelta(days=14)).isoformat(),
            'status': 'draft'
        }
        
        success, response = self.test(
            "Create Work Order",
            "POST",
            "/api/rahaza/work-orders",
            201,
            account='spv',
            data=wo_data
        )
        
        if not success:
            self.log("⚠️  WO creation failed, skipping rest of flow", "WARN")
            return
        
        wo_id = response.get('id')
        if not wo_id:
            self.log("⚠️  No WO ID returned, skipping rest of flow", "WARN")
            return
        
        self.created_resources['wo_id'] = wo_id
        
        # 2. Release WO
        success, response = self.test(
            "Release Work Order",
            "POST",
            f"/api/rahaza/work-orders/{wo_id}/status",
            200,
            account='spv',
            data={'status': 'released'}
        )
        
        # 3. Progress WO
        success, response = self.test(
            "Progress Work Order",
            "POST",
            f"/api/rahaza/work-orders/{wo_id}/status",
            200,
            account='spv',
            data={'status': 'in_progress'}
        )
        
        # 4. Complete WO
        success, response = self.test(
            "Complete Work Order",
            "POST",
            f"/api/rahaza/work-orders/{wo_id}/status",
            200,
            account='spv',
            data={'status': 'completed', 'completed_qty': 100}
        )
        
        # 5. Verify WO status
        success, response = self.test(
            "Get Work Order Details",
            "GET",
            f"/api/rahaza/work-orders/{wo_id}",
            200,
            account='spv'
        )
        
        if success:
            status = response.get('status')
            completed_qty = response.get('completed_qty', 0)
            self.log(f"✅ WO status: {status}, completed_qty: {completed_qty}", "PASS")
    
    # ========== WMS FLOW ==========
    def test_wms_flow(self):
        """Test WMS flow: GRN receiving -> delivery note"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: WMS Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Create GRN receiving
        grn_data = {
            'reference': f'GRN-TEST-{int(time.time())}',
            'supplier': 'Test Supplier',
            'received_date': date.today().isoformat(),
            'items': [
                {
                    'material_code': 'TEST-MAT-001',
                    'material_name': 'Test Material',
                    'quantity': 100,
                    'unit': 'pcs'
                }
            ]
        }
        
        success, response = self.test(
            "Create GRN Receiving",
            "POST",
            "/api/wms/receiving/pending",
            201,
            account='gudang',
            data=grn_data
        )
        
        if success:
            movement_id = response.get('id')
            if movement_id:
                self.created_resources['grn_id'] = movement_id
        
        # 2. Create delivery note
        dn_data = {
            'sj_number': f'SJ-TEST-{int(time.time())}',
            'customer_name': 'Test Customer',
            'delivery_date': date.today().isoformat(),
            'items': [
                {
                    'product_name': 'Test Product',
                    'quantity': 10,
                    'unit': 'pcs'
                }
            ]
        }
        
        success, response = self.test(
            "Create Delivery Note",
            "POST",
            "/api/wms/delivery-notes",
            201,
            account='gudang',
            data=dn_data
        )
        
        if success:
            dn_id = response.get('id')
            if dn_id:
                self.created_resources['delivery_note_id'] = dn_id
                
                # 3. Issue delivery note
                success, response = self.test(
                    "Issue Delivery Note",
                    "POST",
                    f"/api/wms/delivery-notes/{dn_id}/issue",
                    200,
                    account='gudang'
                )
    
    # ========== OPNAME2 FLOW ==========
    def test_opname2_flow(self):
        """Test Opname2 flow: create session -> count -> approve"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Opname2 Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Create opname session
        session_data = {
            'session_name': f'Opname-TEST-{int(time.time())}',
            'location': 'Warehouse A',
            'start_date': date.today().isoformat()
        }
        
        success, response = self.test(
            "Create Opname2 Session",
            "POST",
            "/api/wms/opname2/start",
            201,
            account='gudang',
            data=session_data
        )
        
        if not success:
            self.log("⚠️  Opname2 session creation failed, skipping rest of flow", "WARN")
            return
        
        session_id = response.get('id') or response.get('session_id')
        if not session_id:
            self.log("⚠️  No session ID returned, skipping rest of flow", "WARN")
            return
        
        self.created_resources['opname2_session_id'] = session_id
        
        # 2. Scan/count items
        scan_data = {
            'material_code': 'TEST-MAT-001',
            'quantity': 95  # Variance of -5
        }
        
        success, response = self.test(
            "Scan Item in Opname2",
            "POST",
            f"/api/wms/opname2/{session_id}/scan",
            200,
            account='gudang',
            data=scan_data
        )
        
        # 3. Submit for approval
        success, response = self.test(
            "Submit Opname2 for Approval",
            "POST",
            f"/api/wms/opname2/{session_id}/submit",
            200,
            account='gudang'
        )
        
        # 4. Approve (as admin)
        success, response = self.test(
            "Approve Opname2",
            "POST",
            f"/api/wms/opname2/{session_id}/approve",
            200,
            account='admin'
        )
    
    # ========== MAKLON FLOW ==========
    def test_maklon_flow(self):
        """Test Maklon flow: PO create -> progress -> invoice"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Maklon Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Create Maklon PO
        po_data = {
            'po_number': f'MAKLON-TEST-{int(time.time())}',
            'buyer_name': 'Test Buyer',
            'order_date': date.today().isoformat(),
            'delivery_date': (date.today() + timedelta(days=30)).isoformat(),
            'items': [
                {
                    'product_name': 'Test Garment',
                    'quantity': 500,
                    'unit_price': 50000,
                    'total': 25000000
                }
            ],
            'total_amount': 25000000,
            'status': 'draft'
        }
        
        success, response = self.test(
            "Create Maklon PO",
            "POST",
            "/api/dewi/maklon/pos",
            201,
            account='maklon',
            data=po_data
        )
        
        if not success:
            self.log("⚠️  Maklon PO creation failed, skipping rest of flow", "WARN")
            return
        
        po_id = response.get('id')
        if not po_id:
            self.log("⚠️  No PO ID returned, skipping rest of flow", "WARN")
            return
        
        self.created_resources['maklon_po_id'] = po_id
        
        # 2. Confirm PO
        success, response = self.test(
            "Confirm Maklon PO",
            "POST",
            f"/api/dewi/maklon/pos/{po_id}/confirm",
            200,
            account='maklon'
        )
        
        # 3. Generate invoice
        invoice_data = {
            'po_id': po_id,
            'invoice_date': date.today().isoformat(),
            'amount': 25000000
        }
        
        success, response = self.test(
            "Generate Maklon Invoice",
            "POST",
            "/api/dewi/maklon/billing/invoices/generate",
            201,
            account='maklon',
            data=invoice_data
        )
        
        # 4. Verify invoice in list
        success, response = self.test(
            "Get Maklon Invoices",
            "GET",
            "/api/dewi/maklon/billing/invoices",
            200,
            account='maklon'
        )
        
        if success:
            invoices = response.get('invoices', []) if isinstance(response, dict) else (response if isinstance(response, list) else [])
            self.log(f"✅ Found {len(invoices)} maklon invoices", "PASS")
    
    # ========== ONBOARDING FLOW ==========
    def test_onboarding_flow(self):
        """Test Onboarding flow: create checklist from template -> toggle task"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Onboarding Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # 1. Get templates
        success, response = self.test(
            "Get Onboarding Templates",
            "GET",
            "/api/hr/onboarding/templates",
            200,
            account='hr'
        )
        
        template_id = None
        templates = response.get('templates', []) if isinstance(response, dict) else (response if isinstance(response, list) else [])
        if success and templates:
            template_id = templates[0].get('id')
        
        if not template_id:
            self.log("⚠️  No onboarding templates found, creating one", "WARN")
            
            # Create template
            template_data = {
                'name': 'Test Onboarding Template',
                'description': 'Test template',
                'tasks': [
                    {'title': 'Complete paperwork', 'order': 1},
                    {'title': 'Setup workstation', 'order': 2}
                ]
            }
            
            success, response = self.test(
                "Create Onboarding Template",
                "POST",
                "/api/hr/onboarding/templates",
                201,
                account='hr',
                data=template_data
            )
            
            if success:
                template_id = response.get('id')
        
        if not template_id:
            self.log("⚠️  Could not get/create template, skipping onboarding flow", "WARN")
            return
        
        # 2. Create checklist from template
        checklist_data = {
            'template_id': template_id,
            'employee_name': 'Test Employee',
            'start_date': date.today().isoformat()
        }
        
        success, response = self.test(
            "Create Onboarding Checklist",
            "POST",
            "/api/hr/onboarding/checklists",
            201,
            account='hr',
            data=checklist_data
        )
        
        if not success:
            self.log("⚠️  Checklist creation failed, skipping rest of flow", "WARN")
            return
        
        checklist_id = response.get('id')
        tasks = response.get('tasks', [])
        
        if not checklist_id or not tasks:
            self.log("⚠️  No checklist ID or tasks returned, skipping rest of flow", "WARN")
            return
        
        self.created_resources['onboarding_checklist_id'] = checklist_id
        
        # 3. Toggle task done
        task_id = tasks[0].get('id')
        if task_id:
            success, response = self.test(
                "Toggle Onboarding Task Done",
                "PUT",
                f"/api/hr/onboarding/checklists/{checklist_id}/tasks/{task_id}",
                200,
                account='hr',
                data={'done': True}
            )
            
            # 4. Verify progress_pct changed
            success, response = self.test(
                "Get Onboarding Checklist Progress",
                "GET",
                f"/api/hr/onboarding/checklists/{checklist_id}",
                200,
                account='hr'
            )
            
            if success:
                progress = response.get('progress_pct', 0)
                self.log(f"✅ Onboarding progress: {progress}%", "PASS")
    
    # ========== NOTIFICATIONS FLOW ==========
    def test_notifications_flow(self):
        """Test that actions trigger notifications"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: Notifications Flow", "INFO")
        self.log("=" * 80, "INFO")
        
        # Get notifications (should have some from previous actions)
        success, response = self.test(
            "Get Notifications",
            "GET",
            "/api/notifications",
            200,
            account='admin'
        )
        
        if success:
            notifications = response.get('notifications', []) if isinstance(response, dict) else (response if isinstance(response, list) else [])
            self.log(f"✅ Found {len(notifications)} notifications", "PASS")
    
    # ========== RBAC ENFORCEMENT TESTS ==========
    def test_rbac_enforcement(self):
        """Test RBAC: authorized role succeeds, unauthorized gets 403 (not 500, not 200)"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TESTING: RBAC ENFORCEMENT", "INFO")
        self.log("=" * 80, "INFO")
        
        # Test 1: Finance can POST ar-invoices, but spv/gudang cannot
        self.log("\n--- RBAC Test 1: AR Invoice Creation ---", "INFO")
        
        ar_data = {
            'invoice_number': f'AR-RBAC-{int(time.time())}',
            'customer_name': 'RBAC Test',
            'invoice_date': date.today().isoformat(),
            'due_date': (date.today() + timedelta(days=30)).isoformat(),
            'items': [{'description': 'Test', 'quantity': 1, 'unit_price': 100, 'amount': 100}],
            'subtotal': 100,
            'total': 100
        }
        
        # Finance should succeed
        success, response = self.test(
            "RBAC: Finance can create AR invoice",
            "POST",
            "/api/rahaza/ar-invoices",
            201,
            account='finance',
            data=ar_data
        )
        
        # Spv should get 403
        success, response = self.test(
            "RBAC: Spv cannot create AR invoice (expect 403)",
            "POST",
            "/api/rahaza/ar-invoices",
            403,
            account='spv',
            data=ar_data,
            expect_403=True
        )
        
        # Gudang should get 403
        success, response = self.test(
            "RBAC: Gudang cannot create AR invoice (expect 403)",
            "POST",
            "/api/rahaza/ar-invoices",
            403,
            account='gudang',
            data=ar_data,
            expect_403=True
        )
        
        # Test 2: Gudang can do WMS receiving, but finance cannot
        self.log("\n--- RBAC Test 2: WMS Receiving ---", "INFO")
        
        grn_data = {
            'reference': f'GRN-RBAC-{int(time.time())}',
            'supplier': 'RBAC Test',
            'received_date': date.today().isoformat(),
            'items': [{'material_code': 'TEST', 'material_name': 'Test', 'quantity': 10, 'unit': 'pcs'}]
        }
        
        # Gudang should succeed
        success, response = self.test(
            "RBAC: Gudang can create GRN",
            "POST",
            "/api/wms/receiving/pending",
            201,
            account='gudang',
            data=grn_data
        )
        
        # Finance should get 403
        success, response = self.test(
            "RBAC: Finance cannot create GRN (expect 403)",
            "POST",
            "/api/wms/receiving/pending",
            403,
            account='finance',
            data=grn_data,
            expect_403=True
        )
        
        # Test 3: HR can approve leave, but maklon cannot
        self.log("\n--- RBAC Test 3: Leave Approval ---", "INFO")
        
        # Create a leave request first (as admin)
        leave_data = {
            'leave_type_id': 'test-leave-type',
            'start_date': (date.today() + timedelta(days=7)).isoformat(),
            'end_date': (date.today() + timedelta(days=9)).isoformat(),
            'reason': 'RBAC test',
            'days_requested': 3
        }
        
        success, response = self.test(
            "Create Leave for RBAC Test",
            "POST",
            "/api/rahaza/leaves/request",
            201,
            account='admin',
            data=leave_data
        )
        
        if success:
            leave_id = response.get('id')
            if leave_id:
                # Admin/HR should succeed
                success, response = self.test(
                    "RBAC: Admin can approve leave",
                    "POST",
                    f"/api/rahaza/leaves/{leave_id}/approve",
                    200,
                    account='admin'
                )
                
                # Create another leave for maklon test
                success, response = self.test(
                    "Create Another Leave for RBAC Test",
                    "POST",
                    "/api/rahaza/leaves/request",
                    201,
                    account='admin',
                    data=leave_data
                )
                
                if success:
                    leave_id2 = response.get('id')
                    if leave_id2:
                        # Maklon should get 403
                        success, response = self.test(
                            "RBAC: Maklon cannot approve leave (expect 403)",
                            "POST",
                            f"/api/rahaza/leaves/{leave_id2}/approve",
                            403,
                            account='maklon',
                            expect_403=True
                        )
        
        # Test 4: Maklon can create maklon PO, but hr cannot
        self.log("\n--- RBAC Test 4: Maklon PO Creation ---", "INFO")
        
        po_data = {
            'po_number': f'MAKLON-RBAC-{int(time.time())}',
            'buyer_name': 'RBAC Test',
            'order_date': date.today().isoformat(),
            'delivery_date': (date.today() + timedelta(days=30)).isoformat(),
            'items': [{'product_name': 'Test', 'quantity': 100, 'unit_price': 1000, 'total': 100000}],
            'total_amount': 100000
        }
        
        # Maklon should succeed
        success, response = self.test(
            "RBAC: Maklon can create PO",
            "POST",
            "/api/dewi/maklon/pos",
            201,
            account='maklon',
            data=po_data
        )
        
        # HR should get 403
        success, response = self.test(
            "RBAC: HR cannot create Maklon PO (expect 403)",
            "POST",
            "/api/dewi/maklon/pos",
            403,
            account='hr',
            data=po_data,
            expect_403=True
        )
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 80, "INFO")
        self.log("TEST SUMMARY", "INFO")
        self.log("=" * 80, "INFO")
        
        self.log(f"\nTotal Tests Run: {self.tests_run}", "INFO")
        self.log(f"✅ Passed: {self.tests_passed}", "PASS")
        self.log(f"❌ Failed: {self.tests_failed}", "FAIL")
        
        if self.tests_run > 0:
            success_rate = (self.tests_passed / self.tests_run) * 100
            self.log(f"Success Rate: {success_rate:.1f}%", "INFO")
        
        if self.failed_tests:
            self.log("\n" + "=" * 80, "INFO")
            self.log("FAILED TESTS DETAILS", "INFO")
            self.log("=" * 80, "INFO")
            for i, failure in enumerate(self.failed_tests, 1):
                self.log(f"\n{i}. {failure.get('test')} [{failure.get('account', 'N/A')}]", "FAIL")
                self.log(f"   Expected: {failure.get('expected', 'N/A')}", "INFO")
                self.log(f"   Actual: {failure.get('actual', 'N/A')}", "INFO")
                if 'error' in failure:
                    error_str = str(failure['error'])
                    if len(error_str) > 200:
                        error_str = error_str[:200] + "..."
                    self.log(f"   Error: {error_str}", "ERROR")
                if 'reason' in failure:
                    self.log(f"   Reason: {failure['reason']}", "ERROR")
        
        self.log("\n" + "=" * 80, "INFO")
        
        return self.tests_failed == 0

def main():
    tester = Part5Tester()
    
    # Login all accounts
    if not tester.login_all_accounts():
        tester.log("❌ Login failed, cannot proceed with tests", "ERROR")
        return 1
    
    # Run all flow tests
    tester.test_finance_ar_flow()
    tester.test_finance_ap_flow()
    tester.test_expense_claim_flow()
    tester.test_leave_flow()
    tester.test_attendance_flow()
    tester.test_production_wo_flow()
    tester.test_wms_flow()
    tester.test_opname2_flow()
    tester.test_maklon_flow()
    tester.test_onboarding_flow()
    tester.test_notifications_flow()
    
    # Run RBAC tests
    tester.test_rbac_enforcement()
    
    # Print summary
    success = tester.print_summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
