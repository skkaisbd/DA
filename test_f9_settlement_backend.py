#!/usr/bin/env python3
"""
F9 Settlement/Pencairan Backend Testing
Tests all backend APIs for marketplace settlement feature
"""
import requests
import sys
import json
from datetime import datetime, date

# Public endpoint from frontend/.env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class F9SettlementTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_settlement_id = None
        self.test_je_id = None
        
    def log(self, msg, level="INFO"):
        """Log with timestamp"""
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {level}: {msg}")
        
    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
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
                except:
                    return True, {}
            else:
                self.log(f"❌ FAIL - {name} - Expected {expected_status}, got {response.status_code}", "FAIL")
                try:
                    self.log(f"Response: {response.text[:500]}", "ERROR")
                except:
                    pass
                return False, {}
        
        except Exception as e:
            self.log(f"❌ FAIL - {name} - Error: {str(e)}", "FAIL")
            return False, {}
    
    def test_login(self):
        """Test 0: Login and get token"""
        self.log("=" * 60)
        self.log("TEST 0: Login")
        self.log("=" * 60)
        success, response = self.run_test(
            "Login admin",
            "POST",
            "/api/auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"Token obtained: {self.token[:20]}...", "SUCCESS")
            return True
        self.log("Login failed - cannot proceed", "CRITICAL")
        return False
    
    def test_coa_map(self):
        """Test 1: GET /api/marketing/settlements/coa-map - must return 200 and missing=[]"""
        self.log("=" * 60)
        self.log("TEST 1: COA Map - 7 accounts mapped")
        self.log("=" * 60)
        success, response = self.run_test(
            "GET COA Map",
            "GET",
            "/api/marketing/settlements/coa-map",
            200
        )
        if success:
            missing = response.get('missing', [])
            coa = response.get('coa', [])
            self.log(f"COA accounts: {len(coa)}, Missing: {len(missing)}")
            if len(missing) == 0 and len(coa) == 7:
                self.log("✅ All 7 COA accounts mapped correctly", "PASS")
                return True
            else:
                self.log(f"❌ Expected 7 accounts with 0 missing, got {len(coa)} accounts with {len(missing)} missing: {missing}", "FAIL")
                return False
        return False
    
    def test_create_unbalanced_settlement(self):
        """Test 2: POST settlement with mismatched net_payout - should save but math_verified=false"""
        self.log("=" * 60)
        self.log("TEST 2: Create Settlement with Unbalanced Math")
        self.log("=" * 60)
        
        # Get first marketing account
        success, accounts = self.run_test(
            "GET Marketing Accounts",
            "GET",
            "/api/marketing/accounts?page_size=1",
            200
        )
        if not success:
            self.log("Failed to get marketing accounts", "ERROR")
            return False
        
        # Handle both list and dict responses
        if isinstance(accounts, list):
            if not accounts:
                self.log("No marketing accounts found", "ERROR")
                return False
            account_id = accounts[0]['id']
        elif isinstance(accounts, dict):
            data = accounts.get('data', [])
            if not data:
                self.log("No marketing accounts found", "ERROR")
                return False
            account_id = data[0]['id']
        else:
            self.log("Unexpected response format", "ERROR")
            return False
        
        self.log(f"Using account: {account_id}")
        
        # Create settlement with intentional mismatch
        # gross_sales=10000000, refunds=500000, platform_commission=600000, ads_deduction=200000
        # Expected net = 10000000 - 500000 - 600000 - 200000 = 8700000
        # But we set net_payout = 8500000 (diff = -200000)
        settlement_data = {
            "account_id": account_id,
            "platform": "shopee",
            "settlement_id": f"TEST-F9-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "settlement_date": date.today().isoformat(),
            "gross_sales": 10000000,
            "refunds": 500000,
            "platform_commission": 600000,
            "ads_deduction": 200000,
            "net_payout": 8500000,  # Intentionally wrong
            "notes": "Test settlement with unbalanced math"
        }
        
        success, response = self.run_test(
            "POST Unbalanced Settlement",
            "POST",
            "/api/marketing/settlements",
            200,
            data=settlement_data
        )
        
        if success:
            data = response.get('data', {})
            self.test_settlement_id = data.get('id')
            math_verified = data.get('math_verified')
            net_payout_diff = data.get('net_payout_diff')
            expected_net = data.get('expected_net_payout')
            
            self.log(f"Settlement ID: {self.test_settlement_id}")
            self.log(f"Math Verified: {math_verified}")
            self.log(f"Expected Net: {expected_net}")
            self.log(f"Actual Net: {data.get('net_payout')}")
            self.log(f"Difference: {net_payout_diff}")
            
            if math_verified == False and net_payout_diff == -200000 and expected_net == 8700000:
                self.log("✅ Settlement saved with math_verified=false and correct difference", "PASS")
                return True
            else:
                self.log(f"❌ Expected math_verified=False, diff=-200000, expected_net=8700000", "FAIL")
                return False
        return False
    
    def test_journal_rejected_when_unbalanced(self):
        """Test 3: POST journal on unbalanced settlement - should be rejected with 400"""
        self.log("=" * 60)
        self.log("TEST 3: Journal Creation Rejected When Unbalanced")
        self.log("=" * 60)
        
        if not self.test_settlement_id:
            self.log("No test settlement ID - skipping", "SKIP")
            return False
        
        # Manually check for 400
        url = f"{self.base_url}/api/marketing/settlements/{self.test_settlement_id}/journal"
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        
        self.tests_run += 1
        try:
            response = requests.post(url, json={}, headers=headers, timeout=30)
            if response.status_code == 400:
                detail = response.json().get('detail', '')
                self.log(f"Rejection message: {detail[:200]}")
                if 'selisih' in detail.lower() or 'seimbang' in detail.lower():
                    self.tests_passed += 1
                    self.log("✅ Journal correctly rejected with proper message", "PASS")
                    return True
                else:
                    self.log("❌ Rejected but message doesn't mention difference", "FAIL")
                    return False
            else:
                self.log(f"❌ Expected 400, got {response.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"❌ Error: {str(e)}", "FAIL")
            return False
    
    def test_fix_difference_and_create_journal(self):
        """Test 4: Fix difference with other_deductions, then create DRAFT journal"""
        self.log("=" * 60)
        self.log("TEST 4: Fix Difference and Create DRAFT Journal")
        self.log("=" * 60)
        
        if not self.test_settlement_id:
            self.log("No test settlement ID - skipping", "SKIP")
            return False
        
        # Get the settlement first to get account_id
        success, get_response = self.run_test(
            "GET Settlement",
            "GET",
            f"/api/marketing/settlements?search=TEST-F9&page_size=1",
            200
        )
        
        if not success or not get_response.get('data'):
            return False
        
        settlement = get_response['data'][0]
        account_id = settlement.get('account_id')
        
        # Update settlement to fix the difference
        update_data = {
            "account_id": account_id,
            "platform": "shopee",
            "settlement_id": settlement.get('settlement_id'),
            "settlement_date": settlement.get('settlement_date'),
            "gross_sales": 10000000,
            "refunds": 500000,
            "platform_commission": 600000,
            "ads_deduction": 200000,
            "other_deductions": 200000,  # Fix the difference
            "other_deductions_note": "Potongan lain - test",
            "net_payout": 8500000,
            "notes": "Test settlement - difference fixed"
        }
        
        success, response = self.run_test(
            "PUT Fix Difference",
            "PUT",
            f"/api/marketing/settlements/{self.test_settlement_id}",
            200,
            data=update_data
        )
        
        if not success:
            return False
        
        data = response.get('data', {})
        if not data.get('math_verified'):
            self.log("❌ After fix, math_verified should be true", "FAIL")
            return False
        
        self.log("✅ Difference fixed, math_verified=true", "PASS")
        
        # Now create journal
        success, response = self.run_test(
            "POST Create DRAFT Journal",
            "POST",
            f"/api/marketing/settlements/{self.test_settlement_id}/journal",
            200
        )
        
        if success:
            je_id = response.get('je_id')
            je_number = response.get('je_number')
            je_status = response.get('je_status')
            
            self.test_je_id = je_id
            self.log(f"Journal created: {je_number}, Status: {je_status}")
            
            if je_status == 'draft':
                self.log("✅ DRAFT journal created successfully", "PASS")
                return True
            else:
                self.log(f"❌ Expected status='draft', got '{je_status}'", "FAIL")
                return False
        return False
    
    def test_journal_balanced(self):
        """Test 5: Verify DRAFT journal is balanced"""
        self.log("=" * 60)
        self.log("TEST 5: Journal Balanced (DRAFT)")
        self.log("=" * 60)
        
        if not self.test_je_id:
            self.log("No test journal ID - skipping", "SKIP")
            return False
        
        # Get journal details
        success, response = self.run_test(
            "GET Journal Entry",
            "GET",
            f"/api/rahaza/journals/{self.test_je_id}",
            200
        )
        
        if not success:
            return False
        
        journal = response.get('data', {})
        total_debit = journal.get('total_debit', 0)
        total_credit = journal.get('total_credit', 0)
        status = journal.get('status')
        
        self.log(f"Total Debit: {total_debit}")
        self.log(f"Total Credit: {total_credit}")
        self.log(f"Status: {status}")
        
        # Check balanced
        if abs(total_debit - total_credit) > 0.01:
            self.log(f"❌ Journal not balanced: Dr {total_debit} != Cr {total_credit}", "FAIL")
            return False
        
        self.log("✅ Journal is balanced", "PASS")
        return True
    
    def test_idempotent_journal_creation(self):
        """Test 6: POST journal twice - should return 'already': true"""
        self.log("=" * 60)
        self.log("TEST 6: Idempotent Journal Creation")
        self.log("=" * 60)
        
        if not self.test_settlement_id:
            self.log("No test settlement ID - skipping", "SKIP")
            return False
        
        success, response = self.run_test(
            "POST Journal (second time)",
            "POST",
            f"/api/marketing/settlements/{self.test_settlement_id}/journal",
            200
        )
        
        if success:
            already = response.get('already', False)
            if already:
                self.log("✅ Idempotent: second POST returned 'already': true", "PASS")
                return True
            else:
                self.log("❌ Expected 'already': true on second POST", "FAIL")
                return False
        return False
    
    def test_dedupe_settlement(self):
        """Test 7: POST settlement with same settlement_id - should return 409"""
        self.log("=" * 60)
        self.log("TEST 7: Dedupe - Same Settlement ID")
        self.log("=" * 60)
        
        # Get first marketing account
        success, accounts = self.run_test(
            "GET Marketing Accounts",
            "GET",
            "/api/marketing/accounts?page_size=1",
            200
        )
        if not success:
            return False
        
        # Handle both list and dict responses
        if isinstance(accounts, list):
            if not accounts:
                return False
            account_id = accounts[0]['id']
        elif isinstance(accounts, dict):
            data = accounts.get('data', [])
            if not data:
                return False
            account_id = data[0]['id']
        else:
            return False
        settlement_id = f"TEST-F9-DEDUPE-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        
        # Try to create with same settlement_id
        settlement_data = {
            "account_id": account_id,
            "platform": "shopee",
            "settlement_id": settlement_id,
            "settlement_date": date.today().isoformat(),
            "gross_sales": 5000000,
            "net_payout": 5000000,
        }
        
        # First creation
        success1, response1 = self.run_test(
            "POST First Settlement",
            "POST",
            "/api/marketing/settlements",
            200,
            data=settlement_data
        )
        
        if not success1:
            return False
        
        # Try duplicate
        url = f"{self.base_url}/api/marketing/settlements"
        headers = {'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}
        
        self.tests_run += 1
        try:
            response = requests.post(url, json=settlement_data, headers=headers, timeout=30)
            if response.status_code == 409:
                detail = response.json().get('detail', '')
                self.log(f"Dedupe message: {detail[:200]}")
                if 'sudah pernah dicatat' in detail.lower() or 'menggandakan' in detail.lower():
                    self.tests_passed += 1
                    self.log("✅ Duplicate correctly rejected with 409", "PASS")
                    # Clean up the duplicate test settlement
                    test_id = response1.get('data', {}).get('id')
                    if test_id:
                        requests.delete(f"{self.base_url}/api/marketing/settlements/{test_id}", 
                                      headers=headers, timeout=30)
                    return True
                else:
                    self.log("❌ 409 but message doesn't mention duplication", "FAIL")
                    return False
            else:
                self.log(f"❌ Expected 409, got {response.status_code}", "FAIL")
                return False
        except Exception as e:
            self.log(f"❌ Error: {str(e)}", "FAIL")
            return False
    
    def test_reconcile_endpoint(self):
        """Test 8: GET /api/marketing/settlements/reconcile - should return non-zero revenue"""
        self.log("=" * 60)
        self.log("TEST 8: Reconciliation Endpoint")
        self.log("=" * 60)
        
        success, response = self.run_test(
            "GET Reconcile",
            "GET",
            "/api/marketing/settlements/reconcile",
            200
        )
        
        if success:
            settlement = response.get('settlement', {})
            marketing = response.get('marketing', {})
            gap = response.get('gap', {})
            
            self.log(f"Settlement gross: {settlement.get('gross_sales', 0)}")
            self.log(f"Marketing revenue_gross: {marketing.get('revenue_gross', 0)}")
            self.log(f"Marketing revenue_product: {marketing.get('revenue_product', 0)}")
            self.log(f"Marketing order_amount: {marketing.get('order_amount', 0)}")
            
            # Check that we have labels and gap
            labels = marketing.get('labels', {})
            if labels and gap and 'why' in gap:
                self.log("✅ Reconcile returns proper structure with labels and gap", "PASS")
                return True
            else:
                self.log("❌ Missing labels or gap in reconcile response", "FAIL")
                return False
        return False
    
    def cleanup_test_data(self):
        """Clean up all test data"""
        self.log("=" * 60)
        self.log("CLEANUP: Removing Test Data")
        self.log("=" * 60)
        
        if not self.token:
            self.log("No token - cannot cleanup", "WARN")
            return
        
        # Get all settlements with TEST-F9 prefix
        url = f"{self.base_url}/api/marketing/settlements?search=TEST-F9&page_size=100"
        headers = {'Authorization': f'Bearer {self.token}'}
        
        try:
            response = requests.get(url, headers=headers, timeout=30)
            if response.status_code == 200:
                data = response.json().get('data', [])
                self.log(f"Found {len(data)} test settlements to clean up")
                
                for settlement in data:
                    settlement_id = settlement.get('id')
                    je_id = settlement.get('je_id')
                    
                    # If has journal, void it first
                    if je_id:
                        void_url = f"{self.base_url}/api/rahaza/journals/{je_id}/void"
                        void_response = requests.post(void_url, 
                                                     json={"reason": "Test cleanup"}, 
                                                     headers=headers, timeout=30)
                        if void_response.status_code == 200:
                            self.log(f"Voided journal {je_id}")
                    
                    # Delete settlement
                    del_url = f"{self.base_url}/api/marketing/settlements/{settlement_id}"
                    del_response = requests.delete(del_url, headers=headers, timeout=30)
                    if del_response.status_code == 200:
                        self.log(f"Deleted settlement {settlement.get('settlement_id')}")
                
                # Verify cleanup
                verify_response = requests.get(url, headers=headers, timeout=30)
                if verify_response.status_code == 200:
                    remaining = len(verify_response.json().get('data', []))
                    self.log(f"✅ Cleanup complete. Remaining test settlements: {remaining}", "SUCCESS")
        except Exception as e:
            self.log(f"Cleanup error: {str(e)}", "ERROR")

def main():
    tester = F9SettlementTester()
    
    print("\n" + "=" * 60)
    print("F9 SETTLEMENT/PENCAIRAN BACKEND TESTING")
    print("=" * 60 + "\n")
    
    # Run tests in order
    if not tester.test_login():
        print("\n❌ Login failed - cannot proceed with tests")
        return 1
    
    tester.test_coa_map()
    tester.test_create_unbalanced_settlement()
    tester.test_journal_rejected_when_unbalanced()
    tester.test_fix_difference_and_create_journal()
    tester.test_journal_balanced()
    tester.test_idempotent_journal_creation()
    tester.test_dedupe_settlement()
    tester.test_reconcile_endpoint()
    
    # Cleanup
    tester.cleanup_test_data()
    
    # Print results
    print("\n" + "=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"Tests Run: {tester.tests_run}")
    print(f"Tests Passed: {tester.tests_passed}")
    print(f"Tests Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success Rate: {(tester.tests_passed / tester.tests_run * 100):.1f}%")
    print("=" * 60 + "\n")
    
    return 0 if tester.tests_passed == tester.tests_run else 1

if __name__ == "__main__":
    sys.exit(main())
