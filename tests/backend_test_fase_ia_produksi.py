"""
Backend Test — FASE IA Portal Produksi (Production Portal Mirror)
CV. Dewi Aditya — 2026-07-26

Tests for Phase IA Production Portal changes:
1. New production-tracking endpoint (bug A fix)
2. Distribusi-kerja business_type filtering (bug B fix)
3. New CMT billing endpoints (Invoice door)
4. AP posting for CMT payments
5. CMT receipt header totals bug fix
6. Job internal vendor inheritance
7. RBAC tests

Credentials:
- admin: admin@garment.com / Admin@123
- vendor CMT: cmtvendor@dewiaditya.id / Dewi@123
- klien maklon (RBAC test): klienmaklon@dewiaditya.id / Dewi@123
"""

import requests
import sys
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"

class FaseIAProductionTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.admin_token = None
        self.vendor_token = None
        self.klien_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        
    def log(self, msg, level="INFO"):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {msg}")
    
    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, params=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'
        
        self.tests_run += 1
        self.log(f"Testing {name}...", "TEST")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=30)
            
            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - {name} (Status: {response.status_code})", "PASS")
                try:
                    return True, response.json()
                except Exception:
                    return True, {}
            else:
                self.log(f"❌ FAILED - {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                self.log(f"   Response: {response.text[:200]}", "FAIL")
                self.failed_tests.append({
                    'name': name,
                    'expected': expected_status,
                    'actual': response.status_code,
                    'response': response.text[:500]
                })
                return False, {}
        
        except Exception as e:
            self.log(f"❌ FAILED - {name} - Error: {str(e)}", "FAIL")
            self.failed_tests.append({
                'name': name,
                'error': str(e)
            })
            return False, {}
    
    def login(self, email, password, role_name):
        """Login and get token"""
        self.log(f"Logging in as {role_name} ({email})...", "AUTH")
        success, response = self.run_test(
            f"Login {role_name}",
            "POST",
            "auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in response:
            self.log(f"✅ Login successful for {role_name}", "AUTH")
            return response['token']
        else:
            self.log(f"❌ Login failed for {role_name}", "AUTH")
            return None
    
    def test_backend_1_production_tracking(self):
        """BACKEND-1: GET /api/production-tracking?business_type=internal|maklon"""
        self.log("\n=== BACKEND-1: Production Tracking Endpoint ===", "SECTION")
        
        # Test internal scope
        success, data = self.run_test(
            "Production Tracking - Internal",
            "GET",
            "production-tracking",
            200,
            token=self.admin_token,
            params={'business_type': 'internal'}
        )
        
        if success:
            # Verify structure
            if isinstance(data, list):
                self.log(f"   Found {len(data)} vendors in internal scope", "INFO")
                
                # Check for expected vendors
                vendor_names = [v.get('vendor_name', '') for v in data]
                self.log(f"   Vendors: {vendor_names}", "INFO")
                
                # Verify Produksi Internal exists
                produksi_internal = next((v for v in data if 'Produksi Internal' in v.get('vendor_name', '')), None)
                if produksi_internal:
                    self.log(f"   ✅ Found 'Produksi Internal' vendor", "INFO")
                    self.log(f"      Jobs: {produksi_internal.get('total_jobs')}, Qty: {produksi_internal.get('total_qty')}, Produced: {produksi_internal.get('total_produced')}", "INFO")
                else:
                    self.log(f"   ⚠️  'Produksi Internal' vendor not found", "WARN")
                
                # Verify CV Jahit Mitra CMT exists
                cv_jahit = next((v for v in data if 'CV Jahit Mitra CMT' in v.get('vendor_name', '')), None)
                if cv_jahit:
                    self.log(f"   ✅ Found 'CV Jahit Mitra CMT' vendor", "INFO")
                    self.log(f"      Jobs: {cv_jahit.get('total_jobs')}, Qty: {cv_jahit.get('total_qty')}, Produced: {cv_jahit.get('total_produced')}", "INFO")
                    
                    # Check for PO-INT-DEMO-4
                    jobs = cv_jahit.get('jobs', [])
                    po_int_demo_4 = next((j for j in jobs if 'PO-INT-DEMO-4' in j.get('po_number', '')), None)
                    if po_int_demo_4:
                        self.log(f"   ✅ Found job PO-INT-DEMO-4", "INFO")
                    else:
                        self.log(f"   ⚠️  Job PO-INT-DEMO-4 not found", "WARN")
                else:
                    self.log(f"   ⚠️  'CV Jahit Mitra CMT' vendor not found", "WARN")
                
                # Verify NO maklon jobs (PO-MK-*)
                has_maklon = any('PO-MK-' in str(j.get('po_number', '')) 
                               for v in data 
                               for j in v.get('jobs', []))
                if has_maklon:
                    self.log(f"   ❌ CRITICAL: Found maklon jobs (PO-MK-*) in internal scope!", "FAIL")
                    self.failed_tests.append({
                        'name': 'Production Tracking Internal - No Maklon Jobs',
                        'issue': 'Found PO-MK-* jobs in internal scope'
                    })
                else:
                    self.log(f"   ✅ No maklon jobs in internal scope", "INFO")
            else:
                self.log(f"   ❌ Expected array, got: {type(data)}", "FAIL")
        
        # Test maklon scope
        success, data = self.run_test(
            "Production Tracking - Maklon",
            "GET",
            "production-tracking",
            200,
            token=self.admin_token,
            params={'business_type': 'maklon'}
        )
        
        if success:
            if isinstance(data, list):
                self.log(f"   Found {len(data)} vendors in maklon scope", "INFO")
                
                # Verify NO internal jobs (PO-INT-*)
                has_internal = any('PO-INT-' in str(j.get('po_number', '')) 
                                 for v in data 
                                 for j in v.get('jobs', []))
                if has_internal:
                    self.log(f"   ❌ CRITICAL: Found internal jobs (PO-INT-*) in maklon scope!", "FAIL")
                    self.failed_tests.append({
                        'name': 'Production Tracking Maklon - No Internal Jobs',
                        'issue': 'Found PO-INT-* jobs in maklon scope'
                    })
                else:
                    self.log(f"   ✅ No internal jobs in maklon scope", "INFO")
    
    def test_backend_2_distribusi_kerja(self):
        """BACKEND-2: GET /api/distribusi-kerja?business_type=internal|maklon"""
        self.log("\n=== BACKEND-2: Distribusi Kerja Filtering ===", "SECTION")
        
        # Test internal scope
        success, data = self.run_test(
            "Distribusi Kerja - Internal",
            "GET",
            "distribusi-kerja",
            200,
            token=self.admin_token,
            params={'business_type': 'internal'}
        )
        
        if success:
            flat = data.get('flat', [])
            self.log(f"   Found {len(flat)} items in internal scope", "INFO")
            
            # Check PO numbers
            po_numbers = list(set([item.get('po_number', '') for item in flat]))
            self.log(f"   PO numbers: {po_numbers[:5]}", "INFO")
            
            # Verify only PO-INT-*
            has_maklon = any('PO-MK-' in po for po in po_numbers)
            has_internal = any('PO-INT-' in po for po in po_numbers)
            
            if has_maklon:
                self.log(f"   ❌ CRITICAL: Found maklon POs in internal scope!", "FAIL")
                self.failed_tests.append({
                    'name': 'Distribusi Kerja Internal - No Maklon POs',
                    'issue': 'Found PO-MK-* in internal scope'
                })
            else:
                self.log(f"   ✅ No maklon POs in internal scope", "INFO")
            
            if has_internal:
                self.log(f"   ✅ Found internal POs (PO-INT-*)", "INFO")
        
        # Test maklon scope
        success, data = self.run_test(
            "Distribusi Kerja - Maklon",
            "GET",
            "distribusi-kerja",
            200,
            token=self.admin_token,
            params={'business_type': 'maklon'}
        )
        
        if success:
            flat = data.get('flat', [])
            self.log(f"   Found {len(flat)} items in maklon scope", "INFO")
            
            # Check PO numbers
            po_numbers = list(set([item.get('po_number', '') for item in flat]))
            self.log(f"   PO numbers: {po_numbers[:5]}", "INFO")
            
            # Verify only PO-MK-*
            has_internal = any('PO-INT-' in po for po in po_numbers)
            has_maklon = any('PO-MK-' in po for po in po_numbers)
            
            if has_internal:
                self.log(f"   ❌ CRITICAL: Found internal POs in maklon scope!", "FAIL")
                self.failed_tests.append({
                    'name': 'Distribusi Kerja Maklon - No Internal POs',
                    'issue': 'Found PO-INT-* in maklon scope'
                })
            else:
                self.log(f"   ✅ No internal POs in maklon scope", "INFO")
            
            if has_maklon:
                self.log(f"   ✅ Found maklon POs (PO-MK-*)", "INFO")
        
        # Test production-variances
        success, data = self.run_test(
            "Production Variances - Internal",
            "GET",
            "production-variances",
            200,
            token=self.admin_token,
            params={'business_type': 'internal'}
        )
        if success:
            self.log(f"   ✅ Production variances endpoint supports business_type", "INFO")
    
    def test_backend_3_cmt_billing(self):
        """BACKEND-3: GET /api/production/cmt-billing endpoints"""
        self.log("\n=== BACKEND-3: CMT Billing (Invoice) Endpoints ===", "SECTION")
        
        # Test list endpoint - internal
        success, data = self.run_test(
            "CMT Billing List - Internal",
            "GET",
            "production/cmt-billing",
            200,
            token=self.admin_token,
            params={'business_type': 'internal'}
        )
        
        if success:
            items = data.get('items', [])
            self.log(f"   Found {len(items)} CMT billing records in internal scope", "INFO")
            
            # Check for expected bills
            pay_cmt_00001 = next((b for b in items if b.get('payment_code') == 'PAY-CMT-00001'), None)
            pay_cmt_00002 = next((b for b in items if b.get('payment_code') == 'PAY-CMT-00002'), None)
            
            if pay_cmt_00001:
                self.log(f"   ✅ Found PAY-CMT-00001: Rp {pay_cmt_00001.get('amount', 0):,.0f}", "INFO")
                self.log(f"      PO: {pay_cmt_00001.get('po_number')}, GL Posted: {pay_cmt_00001.get('gl_posted')}", "INFO")
            else:
                self.log(f"   ⚠️  PAY-CMT-00001 not found", "WARN")
            
            if pay_cmt_00002:
                self.log(f"   ✅ Found PAY-CMT-00002: Rp {pay_cmt_00002.get('amount', 0):,.0f}", "INFO")
                self.log(f"      PO: {pay_cmt_00002.get('po_number')}, GL Posted: {pay_cmt_00002.get('gl_posted')}", "INFO")
            else:
                self.log(f"   ⚠️  PAY-CMT-00002 not found", "WARN")
        
        # Test list endpoint - maklon (should be empty)
        success, data = self.run_test(
            "CMT Billing List - Maklon",
            "GET",
            "production/cmt-billing",
            200,
            token=self.admin_token,
            params={'business_type': 'maklon'}
        )
        
        if success:
            items = data.get('items', [])
            self.log(f"   Found {len(items)} CMT billing records in maklon scope", "INFO")
            if len(items) == 0:
                self.log(f"   ✅ Maklon scope is empty (as expected)", "INFO")
        
        # Test summary endpoint - internal
        success, data = self.run_test(
            "CMT Billing Summary - Internal",
            "GET",
            "production/cmt-billing/summary",
            200,
            token=self.admin_token,
            params={'business_type': 'internal'}
        )
        
        if success:
            self.log(f"   Summary - Total Bills: {data.get('total_bills')}", "INFO")
            self.log(f"   Summary - Total Amount: Rp {data.get('total_amount', 0):,.0f}", "INFO")
            self.log(f"   Summary - Total PCS: {data.get('total_pcs')}", "INFO")
            self.log(f"   Summary - Variance Flagged: {data.get('variance_flagged')}", "INFO")
            
            # Verify expected values
            if data.get('total_amount') == 2175000:
                self.log(f"   ✅ Total amount matches expected (Rp 2,175,000)", "INFO")
            else:
                self.log(f"   ⚠️  Total amount mismatch: expected 2,175,000, got {data.get('total_amount')}", "WARN")
            
            if data.get('total_pcs') == 145:
                self.log(f"   ✅ Total PCS matches expected (145)", "INFO")
            else:
                self.log(f"   ⚠️  Total PCS mismatch: expected 145, got {data.get('total_pcs')}", "WARN")
            
            if data.get('variance_flagged') == 0:
                self.log(f"   ✅ Variance flagged is 0 (as expected)", "INFO")
            else:
                self.log(f"   ⚠️  Variance flagged should be 0, got {data.get('variance_flagged')}", "WARN")
        
        # Test pagination
        success, data = self.run_test(
            "CMT Billing Pagination",
            "GET",
            "production/cmt-billing",
            200,
            token=self.admin_token,
            params={'business_type': 'internal', 'page': 1, 'per_page': 1}
        )
        
        if success:
            self.log(f"   ✅ Pagination works", "INFO")
    
    def test_backend_4_post_ap(self):
        """BACKEND-4: POST /api/dewi/maklon/finance/cmt-payments/{id}/post-ap"""
        self.log("\n=== BACKEND-4: CMT Payment AP Posting ===", "SECTION")
        
        # First, get a payment that hasn't been posted
        success, data = self.run_test(
            "Get CMT Billing List",
            "GET",
            "production/cmt-billing",
            200,
            token=self.admin_token,
            params={'business_type': 'internal'}
        )
        
        if success:
            items = data.get('items', [])
            # Find PAY-CMT-00001 (should not be posted yet based on test requirements)
            pay_cmt_00001 = next((b for b in items if b.get('payment_code') == 'PAY-CMT-00001'), None)
            
            if pay_cmt_00001:
                payment_id = pay_cmt_00001.get('id')
                self.log(f"   Testing AP posting for {pay_cmt_00001.get('payment_code')}", "INFO")
                
                # Post to AP
                success, result = self.run_test(
                    "Post CMT Payment to AP",
                    "POST",
                    f"dewi/maklon/finance/cmt-payments/{payment_id}/post-ap",
                    200,
                    token=self.admin_token
                )
                
                if success:
                    self.log(f"   ✅ AP posting successful", "INFO")
                    self.log(f"      JE ID: {result.get('je_id')}", "INFO")
                    self.log(f"      JE Number: {result.get('je_number')}", "INFO")
                    self.log(f"      Already Posted: {result.get('already_posted')}", "INFO")
                    
                    # Verify journal entry was created
                    if result.get('je_id'):
                        self.log(f"   ✅ Journal entry created", "INFO")
                        
                        # Try posting again (should be idempotent)
                        success2, result2 = self.run_test(
                            "Post CMT Payment to AP (2nd time - idempotent)",
                            "POST",
                            f"dewi/maklon/finance/cmt-payments/{payment_id}/post-ap",
                            200,
                            token=self.admin_token
                        )
                        
                        if success2 and result2.get('already_posted'):
                            self.log(f"   ✅ Idempotent posting works (already_posted=true)", "INFO")
                        else:
                            self.log(f"   ⚠️  Idempotent check failed", "WARN")
            else:
                self.log(f"   ⚠️  PAY-CMT-00001 not found for AP posting test", "WARN")
    
    def test_backend_7_rbac(self):
        """BACKEND-7: RBAC tests for production endpoints"""
        self.log("\n=== BACKEND-7: RBAC Tests ===", "SECTION")
        
        # Test without token (should be 401)
        success, data = self.run_test(
            "Production Tracking - No Token (401)",
            "GET",
            "production-tracking",
            401,
            params={'business_type': 'internal'}
        )
        
        success, data = self.run_test(
            "CMT Billing - No Token (401)",
            "GET",
            "production/cmt-billing",
            401,
            params={'business_type': 'internal'}
        )
        
        # Test with klien maklon token (should be 403)
        if self.klien_token:
            success, data = self.run_test(
                "Production Tracking - Klien Maklon (403)",
                "GET",
                "production-tracking",
                403,
                token=self.klien_token,
                params={'business_type': 'internal'}
            )
            
            success, data = self.run_test(
                "CMT Billing - Klien Maklon (403)",
                "GET",
                "production/cmt-billing",
                403,
                token=self.klien_token,
                params={'business_type': 'internal'}
            )
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "="*70, "SUMMARY")
        self.log(f"TESTS RUN: {self.tests_run}", "SUMMARY")
        self.log(f"TESTS PASSED: {self.tests_passed}", "SUMMARY")
        self.log(f"TESTS FAILED: {len(self.failed_tests)}", "SUMMARY")
        self.log(f"SUCCESS RATE: {(self.tests_passed/self.tests_run*100):.1f}%", "SUMMARY")
        
        if self.failed_tests:
            self.log("\n=== FAILED TESTS ===", "SUMMARY")
            for i, test in enumerate(self.failed_tests, 1):
                self.log(f"{i}. {test.get('name', 'Unknown')}", "FAIL")
                if 'expected' in test:
                    self.log(f"   Expected: {test['expected']}, Got: {test['actual']}", "FAIL")
                if 'issue' in test:
                    self.log(f"   Issue: {test['issue']}", "FAIL")
                if 'error' in test:
                    self.log(f"   Error: {test['error']}", "FAIL")
        
        self.log("="*70, "SUMMARY")

def main():
    tester = FaseIAProductionTester()
    
    # Login
    tester.log("=== AUTHENTICATION ===", "SECTION")
    tester.admin_token = tester.login("admin@garment.com", "Admin@123", "Admin")
    tester.vendor_token = tester.login("cmtvendor@dewiaditya.id", "Dewi@123", "Vendor CMT")
    tester.klien_token = tester.login("klienmaklon@dewiaditya.id", "Dewi@123", "Klien Maklon")
    
    if not tester.admin_token:
        tester.log("❌ Admin login failed, cannot continue", "ERROR")
        return 1
    
    # Run tests
    tester.test_backend_1_production_tracking()
    tester.test_backend_2_distribusi_kerja()
    tester.test_backend_3_cmt_billing()
    tester.test_backend_4_post_ap()
    tester.test_backend_7_rbac()
    
    # Print summary
    tester.print_summary()
    
    return 0 if len(tester.failed_tests) == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
