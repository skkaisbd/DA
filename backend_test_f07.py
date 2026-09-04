#!/usr/bin/env python3
"""
Backend API Test for F0.7 Marketing Accounts Management
Quick verification of backend endpoints before UI testing
"""
import requests
import sys
from datetime import datetime

class F07BackendTester:
    def __init__(self, base_url="https://da37-cmt-bridge.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.created_accounts = []

    def run_test(self, name, method, endpoint, expected_status, data=None, headers_extra=None):
        """Run a single API test"""
        url = f"{self.base_url}/{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        if headers_extra:
            headers.update(headers_extra)

        self.tests_run += 1
        print(f"\n🔍 Testing {name}...")
        
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
                print(f"✅ Passed - Status: {response.status_code}")
                try:
                    return True, response.json()
                except Exception:
                    return True, {}
            else:
                print(f"❌ Failed - Expected {expected_status}, got {response.status_code}")
                try:
                    print(f"   Response: {response.json()}")
                except Exception:
                    print(f"   Response: {response.text[:200]}")
                return False, {}

        except Exception as e:
            print(f"❌ Failed - Error: {str(e)}")
            return False, {}

    def test_login(self):
        """Test login and get token"""
        print("\n" + "="*80)
        print("BACKEND API TESTS - F0.7 Marketing Accounts Management")
        print("="*80)
        
        success, response = self.run_test(
            "Login",
            "POST",
            "api/auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"}
        )
        if success and ('token' in response or 'access_token' in response):
            self.token = response.get('token') or response.get('access_token')
            print(f"   Token obtained: {self.token[:20]}...")
            return True
        return False

    def test_get_accounts(self):
        """Test GET /api/marketing/accounts - should return 12 accounts"""
        success, response = self.run_test(
            "GET /api/marketing/accounts",
            "GET",
            "api/marketing/accounts",
            200
        )
        if success:
            accounts = response if isinstance(response, list) else response.get('accounts', [])
            print(f"   Found {len(accounts)} accounts")
            
            # Check for F0.7 fields
            if accounts:
                sample = accounts[0]
                f07_fields = ['coa_revenue_code', 'coa_cash_code', 'coa_receivable_code', 
                             'ar_account_code', 'revenue_basis', 'platform_warehouse_name',
                             'platform_shop_id', 'pic_user_id', 'pic_user_name']
                
                present_fields = [f for f in f07_fields if f in sample]
                print(f"   F0.7 fields present: {len(present_fields)}/{len(f07_fields)}")
                
                # Check for 9 real active shops
                active_shops = [a for a in accounts if a.get('status') == 'active' and not a.get('is_demo')]
                print(f"   Active real shops: {len(active_shops)}")
                
                # Check for specific shops mentioned in user stories
                expected_codes = ['SHOPEE-GROSIRHIJAB', 'SHOPEE-DALUNA', 'SHOPEE-MOEN', 
                                 'TIKTOK-DALUNA', 'TIKTOK-OUTFIT', 'TIKTOK-MOEN', 
                                 'TIKTOK-FATIMAHIJAB', 'TIKTOK-DEZZAKIDS', 'TOKPED-DA']
                found_codes = [a.get('account_code') for a in accounts if a.get('account_code') in expected_codes]
                print(f"   Expected shops found: {len(found_codes)}/{len(expected_codes)}")
                
                return len(accounts) >= 12 and len(present_fields) >= 7
        return False

    def test_coa_options(self):
        """Test GET /api/marketing/accounts/coa-options"""
        success, response = self.run_test(
            "GET /api/marketing/accounts/coa-options",
            "GET",
            "api/marketing/accounts/coa-options",
            200
        )
        if success:
            # Check structure
            has_revenue = 'revenue' in response and isinstance(response['revenue'], list)
            has_cash = 'cash' in response and isinstance(response['cash'], list)
            has_receivable = 'receivable' in response and isinstance(response['receivable'], list)
            has_defaults = 'default_cash' in response and 'default_receivable' in response
            has_fallback = 'fallback_revenue_by_platform' in response
            
            print(f"   Revenue options: {len(response.get('revenue', []))}")
            print(f"   Cash options: {len(response.get('cash', []))}")
            print(f"   Receivable options: {len(response.get('receivable', []))}")
            print(f"   Has defaults: {has_defaults}")
            print(f"   Has fallback: {has_fallback}")
            
            # Verify exclusions mentioned in user story
            revenue_codes = [r['code'] for r in response.get('revenue', [])]
            excluded = ['4-140', '4-141', '4-1200', '4-1300', '4-100']
            found_excluded = [c for c in excluded if c in revenue_codes]
            if found_excluded:
                print(f"   ⚠️  Found excluded codes in revenue: {found_excluded}")
            
            cash_codes = [c['code'] for c in response.get('cash', [])]
            excluded_cash = ['1-1300', '1-1301']
            found_excluded_cash = [c for c in excluded_cash if c in cash_codes]
            if found_excluded_cash:
                print(f"   ⚠️  Found excluded codes in cash: {found_excluded_cash}")
            
            return has_revenue and has_cash and has_receivable and has_defaults
        return False

    def test_create_account_full_f07(self):
        """Test POST /api/marketing/accounts with all F0.7 fields"""
        test_code = f"TEST-F07-{datetime.now().strftime('%H%M%S')}"
        
        # First get COA options to pick valid codes
        _, coa_opts = self.run_test(
            "Get COA options for create test",
            "GET",
            "api/marketing/accounts/coa-options",
            200
        )
        
        revenue_code = coa_opts.get('revenue', [{}])[0].get('code', '4-122')
        cash_code = coa_opts.get('default_cash', '1-131')
        receivable_code = coa_opts.get('default_receivable', '1-220')
        
        success, response = self.run_test(
            "POST /api/marketing/accounts (full F0.7)",
            "POST",
            "api/marketing/accounts",
            200,
            data={
                "account_code": test_code,
                "account_name": "Test F0.7 Account",
                "platform": "tiktokshop",
                "username": "test.f07",
                "group": "other",
                "has_api_integration": True,
                "coa_revenue_code": revenue_code,
                "coa_cash_code": cash_code,
                "coa_receivable_code": receivable_code,
                "revenue_basis": "produk_setelah_diskon",
                "platform_warehouse_name": "Test Warehouse",
                "platform_shop_id": "999888777",
                "pic_user_id": ""  # Empty PIC is valid
            }
        )
        
        if success:
            account = response.get('account', {})
            account_id = account.get('id')
            if account_id:
                self.created_accounts.append(account_id)
            
            # Check if ar_account_code was created
            ar_code = account.get('ar_account_code')
            if ar_code:
                print(f"   ✅ Auto COA account created: {ar_code}")
            else:
                print(f"   ⚠️  No ar_account_code in response")
            
            # Verify all F0.7 fields
            checks = {
                'coa_revenue_code': account.get('coa_revenue_code') == revenue_code,
                'coa_cash_code': account.get('coa_cash_code') == cash_code,
                'revenue_basis': account.get('revenue_basis') == 'produk_setelah_diskon',
                'platform_warehouse_name': account.get('platform_warehouse_name') == 'Test Warehouse',
                'platform_shop_id': account.get('platform_shop_id') == '999888777',
            }
            
            passed = sum(checks.values())
            print(f"   F0.7 fields verified: {passed}/{len(checks)}")
            
            return all(checks.values())
        return False

    def test_validation_errors(self):
        """Test validation: invalid COA code, invalid revenue_basis"""
        # Test 1: Invalid COA code
        success1, _ = self.run_test(
            "POST with invalid coa_revenue_code (should fail)",
            "POST",
            "api/marketing/accounts",
            400,
            data={
                "account_code": "TEST-INVALID-COA",
                "account_name": "Test Invalid",
                "platform": "shopee",
                "coa_revenue_code": "9-999",  # Invalid code
                "coa_cash_code": "1-131"
            }
        )
        
        # Test 2: Invalid revenue_basis
        success2, _ = self.run_test(
            "POST with invalid revenue_basis (should fail)",
            "POST",
            "api/marketing/accounts",
            400,
            data={
                "account_code": "TEST-INVALID-BASIS",
                "account_name": "Test Invalid Basis",
                "platform": "shopee",
                "revenue_basis": "asal_asalan"  # Invalid basis
            }
        )
        
        # Test 3: Group account as cash (9-000)
        success3, _ = self.run_test(
            "POST with group account as cash (should fail)",
            "POST",
            "api/marketing/accounts",
            400,
            data={
                "account_code": "TEST-GROUP-CASH",
                "account_name": "Test Group Cash",
                "platform": "shopee",
                "coa_cash_code": "9-000"  # Group expense account
            }
        )
        
        return success1 and success2 and success3

    def cleanup(self):
        """Clean up created test accounts"""
        print(f"\n🧹 Cleaning up {len(self.created_accounts)} test accounts...")
        for account_id in self.created_accounts:
            try:
                self.run_test(
                    f"Delete test account {account_id[:8]}",
                    "DELETE",
                    f"api/marketing/accounts/{account_id}",
                    200
                )
            except Exception:
                pass

    def run_all_tests(self):
        """Run all backend tests"""
        if not self.test_login():
            print("\n❌ Login failed, cannot continue")
            return 1
        
        print("\n" + "="*80)
        print("RUNNING BACKEND TESTS")
        print("="*80)
        
        # Core tests
        self.test_get_accounts()
        self.test_coa_options()
        self.test_create_account_full_f07()
        self.test_validation_errors()
        
        # Cleanup
        self.cleanup()
        
        # Print results
        print("\n" + "="*80)
        print(f"📊 BACKEND TEST RESULTS: {self.tests_passed}/{self.tests_run} PASSED")
        print("="*80)
        
        return 0 if self.tests_passed == self.tests_run else 1

def main():
    tester = F07BackendTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
