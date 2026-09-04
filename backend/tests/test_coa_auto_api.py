"""
Phase 5 COA Auto API Testing
Tests all /api/rahaza/coa-auto/* endpoints including RBAC, settings, backfill, and idempotency.
"""
import requests
import sys
import json
from datetime import datetime

class CoaAutoAPITester:
    def __init__(self, base_url="https://da37-cmt-bridge.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []
        self.original_settings = None

    def log(self, message, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, headers=None, expect_json=True):
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

            success = response.status_code == expected_status
            
            result = {
                "test": name,
                "passed": success,
                "expected_status": expected_status,
                "actual_status": response.status_code,
                "endpoint": endpoint
            }

            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - {name} (Status: {response.status_code})", "PASS")
                if expect_json:
                    try:
                        json_data = response.json()
                        result["response"] = json_data
                        return True, json_data
                    except Exception:
                        return True, {}
                return True, response.text
            else:
                self.log(f"❌ FAIL - {name} (Expected {expected_status}, got {response.status_code})", "FAIL")
                try:
                    result["response"] = response.json()
                except Exception:
                    result["response"] = response.text
                self.results.append(result)
                return False, result.get("response", {})

        except Exception as e:
            self.log(f"❌ FAIL - {name} (Error: {str(e)})", "FAIL")
            result = {
                "test": name,
                "passed": False,
                "error": str(e),
                "endpoint": endpoint
            }
            self.results.append(result)
            return False, {}

    def test_login(self, email, password):
        """Test login and get token"""
        self.log(f"Logging in as {email}...")
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": email, "password": password}
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"✅ Login successful, token obtained", "SUCCESS")
            return True
        self.log(f"❌ Login failed", "ERROR")
        return False

    def test_get_settings(self):
        """Test GET /api/rahaza/coa-auto/settings"""
        self.log("\n=== Testing GET Settings ===")
        success, response = self.run_test(
            "GET COA Auto Settings",
            "GET",
            "/api/rahaza/coa-auto/settings",
            200
        )
        
        if success:
            # Store original settings for restoration later
            self.original_settings = response
            
            # Verify entity_types exist
            entity_types = response.get('entity_types', {})
            
            # Check cmt_vendor exists
            if 'cmt_vendor' in entity_types:
                self.log(f"✅ cmt_vendor entity type found", "PASS")
                cmt = entity_types['cmt_vendor']
                self.log(f"   - enabled: {cmt.get('enabled')}")
                self.log(f"   - parent_code: {cmt.get('parent_code')}")
                self.log(f"   - collection: {cmt.get('collection')}")
            else:
                self.log(f"❌ cmt_vendor entity type NOT found", "FAIL")
                
            # Check bank exists
            if 'bank' in entity_types:
                self.log(f"✅ bank entity type found", "PASS")
                bank = entity_types['bank']
                self.log(f"   - enabled: {bank.get('enabled')}")
                self.log(f"   - parent_code: {bank.get('parent_code')}")
                self.log(f"   - collection: {bank.get('collection')}")
            else:
                self.log(f"❌ bank entity type NOT found", "FAIL")
                
        return success, response

    def test_put_settings_valid(self):
        """Test PUT /api/rahaza/coa-auto/settings with valid parent_code"""
        self.log("\n=== Testing PUT Settings (Valid) ===")
        
        # Change cmt_vendor parent_code to 2-1100 (should be valid)
        payload = {
            "entity_types": {
                "cmt_vendor": {
                    "enabled": True,
                    "parent_code": "2-1100"
                }
            }
        }
        
        success, response = self.run_test(
            "PUT Settings - Valid parent_code",
            "PUT",
            "/api/rahaza/coa-auto/settings",
            200,
            data=payload
        )
        
        if success:
            self.log(f"✅ Settings updated successfully", "PASS")
            
            # Verify the change persisted
            verify_success, verify_response = self.run_test(
                "Verify Settings Persisted",
                "GET",
                "/api/rahaza/coa-auto/settings",
                200
            )
            
            if verify_success:
                cmt = verify_response.get('entity_types', {}).get('cmt_vendor', {})
                if cmt.get('parent_code') == '2-1100':
                    self.log(f"✅ parent_code persisted correctly: {cmt.get('parent_code')}", "PASS")
                else:
                    self.log(f"❌ parent_code NOT persisted correctly", "FAIL")
                    
        return success

    def test_put_settings_invalid(self):
        """Test PUT /api/rahaza/coa-auto/settings with INVALID parent_code"""
        self.log("\n=== Testing PUT Settings (Invalid) ===")
        
        # Try to set invalid parent_code
        payload = {
            "entity_types": {
                "cmt_vendor": {
                    "enabled": True,
                    "parent_code": "ZZ-9999"  # Invalid code
                }
            }
        }
        
        success, response = self.run_test(
            "PUT Settings - Invalid parent_code (expect 400)",
            "PUT",
            "/api/rahaza/coa-auto/settings",
            400,
            data=payload
        )
        
        if success:
            self.log(f"✅ Invalid parent_code correctly rejected with 400", "PASS")
        else:
            self.log(f"❌ Invalid parent_code should return 400", "FAIL")
            
        return success

    def test_backfill_dry_run(self):
        """Test POST /api/rahaza/coa-auto/backfill/cmt_vendor?commit=false (dry-run)"""
        self.log("\n=== Testing Backfill Dry-Run ===")
        
        success, response = self.run_test(
            "Backfill cmt_vendor - Dry Run",
            "POST",
            "/api/rahaza/coa-auto/backfill/cmt_vendor?commit=false",
            200
        )
        
        if success:
            self.log(f"✅ Dry-run successful", "PASS")
            self.log(f"   - total_entities: {response.get('total_entities')}")
            self.log(f"   - already_have_account: {response.get('already_have_account')}")
            self.log(f"   - would_create: {response.get('would_create')}")
            self.log(f"   - committed: {response.get('committed')}")
            
            # Verify it's a dry-run (committed should be False)
            if response.get('committed') == False:
                self.log(f"✅ Confirmed dry-run (committed=false)", "PASS")
            else:
                self.log(f"❌ Should be dry-run but committed={response.get('committed')}", "FAIL")
                
        return success, response

    def test_backfill_commit(self):
        """Test POST /api/rahaza/coa-auto/backfill/cmt_vendor?commit=true"""
        self.log("\n=== Testing Backfill Commit ===")
        
        success, response = self.run_test(
            "Backfill cmt_vendor - Commit",
            "POST",
            "/api/rahaza/coa-auto/backfill/cmt_vendor?commit=true",
            200
        )
        
        if success:
            self.log(f"✅ Backfill commit successful", "PASS")
            self.log(f"   - total_entities: {response.get('total_entities')}")
            self.log(f"   - already_have_account: {response.get('already_have_account')}")
            self.log(f"   - created: {response.get('created')}")
            self.log(f"   - committed: {response.get('committed')}")
            
            # Verify it's committed
            if response.get('committed') == True:
                self.log(f"✅ Confirmed commit (committed=true)", "PASS")
            else:
                self.log(f"❌ Should be committed but committed={response.get('committed')}", "FAIL")
                
        return success, response

    def test_backfill_idempotency(self):
        """Test idempotency - second backfill should create 0 new accounts"""
        self.log("\n=== Testing Backfill Idempotency ===")
        
        success, response = self.run_test(
            "Backfill cmt_vendor - Idempotency Check",
            "POST",
            "/api/rahaza/coa-auto/backfill/cmt_vendor?commit=true",
            200
        )
        
        if success:
            created = response.get('created', -1)
            if created == 0:
                self.log(f"✅ Idempotency verified - created={created} (expected 0)", "PASS")
            else:
                self.log(f"❌ Idempotency FAILED - created={created} (expected 0)", "FAIL")
                
        return success

    def test_verify_subledger_accounts(self):
        """Test GET /api/rahaza/coa/accounts to verify created subledger accounts"""
        self.log("\n=== Testing Verify Subledger Accounts ===")
        
        success, response = self.run_test(
            "GET COA Accounts (active_only=true)",
            "GET",
            "/api/rahaza/coa/accounts?active_only=true",
            200
        )
        
        if success:
            accounts = response if isinstance(response, list) else response.get('accounts', response.get('items', []))
            
            # Find subledger accounts under 2-1100
            subledger_accounts = [
                acc for acc in accounts 
                if acc.get('code', '').startswith('2-1100-') and 
                acc.get('parent_code') == '2-1100' and
                acc.get('is_group') == False
            ]
            
            self.log(f"✅ Found {len(subledger_accounts)} subledger accounts under 2-1100", "PASS")
            
            if subledger_accounts:
                # Verify properties of first subledger account
                sample = subledger_accounts[0]
                self.log(f"   Sample account: {sample.get('code')} - {sample.get('name')}")
                self.log(f"   - parent_code: {sample.get('parent_code')}")
                self.log(f"   - is_group: {sample.get('is_group')}")
                self.log(f"   - normal_balance: {sample.get('normal_balance')}")
                self.log(f"   - active: {sample.get('active')}")
                
                # Verify normal_balance is CREDIT (for AP/liability)
                if sample.get('normal_balance') == 'CREDIT':
                    self.log(f"✅ normal_balance is CREDIT (correct for AP)", "PASS")
                else:
                    self.log(f"❌ normal_balance is {sample.get('normal_balance')} (expected CREDIT)", "FAIL")
                    
        return success

    def test_rbac_no_token(self):
        """Test RBAC - endpoints should require authentication"""
        self.log("\n=== Testing RBAC (No Token) ===")
        
        # Save current token
        saved_token = self.token
        self.token = None
        
        # Try to access settings without token
        headers = {'Content-Type': 'application/json'}
        success, response = self.run_test(
            "GET Settings without token (expect 401/403)",
            "GET",
            "/api/rahaza/coa-auto/settings",
            401,  # Expecting 401 or 403
            headers=headers
        )
        
        # If 401 didn't work, try 403
        if not success:
            success, response = self.run_test(
                "GET Settings without token (expect 403)",
                "GET",
                "/api/rahaza/coa-auto/settings",
                403,
                headers=headers
            )
        
        if success:
            self.log(f"✅ RBAC working - unauthorized access blocked", "PASS")
        else:
            self.log(f"❌ RBAC may not be working - should return 401/403", "FAIL")
            
        # Restore token
        self.token = saved_token
        
        return success

    def restore_settings(self):
        """Restore original settings"""
        if self.original_settings:
            self.log("\n=== Restoring Original Settings ===")
            
            # Restore cmt_vendor and bank to defaults
            payload = {
                "entity_types": {
                    "cmt_vendor": {
                        "enabled": True,
                        "parent_code": "2-1100"
                    },
                    "bank": {
                        "enabled": False,
                        "parent_code": "1-1200"
                    }
                }
            }
            
            success, response = self.run_test(
                "Restore Default Settings",
                "PUT",
                "/api/rahaza/coa-auto/settings",
                200,
                data=payload
            )
            
            if success:
                self.log(f"✅ Settings restored to defaults", "SUCCESS")
            else:
                self.log(f"⚠️  Failed to restore settings", "WARNING")

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*70)
        print(f"TEST SUMMARY")
        print("="*70)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print("="*70)
        
        if self.tests_passed == self.tests_run:
            print("✅ ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED")
            print("\nFailed Tests:")
            for result in self.results:
                if not result.get('passed', True):
                    print(f"  - {result.get('test')}: {result.get('error', 'Status mismatch')}")
        
        return 0 if self.tests_passed == self.tests_run else 1


def main():
    print("\n" + "="*70)
    print("Phase 5 COA Auto API Testing")
    print("="*70)
    
    tester = CoaAutoAPITester()
    
    # Login
    if not tester.test_login("admin@garment.com", "Admin@123"):
        print("❌ Login failed, cannot proceed with tests")
        return 1
    
    # Run all tests
    tester.test_get_settings()
    tester.test_put_settings_valid()
    tester.test_put_settings_invalid()
    tester.test_backfill_dry_run()
    tester.test_backfill_commit()
    tester.test_backfill_idempotency()
    tester.test_verify_subledger_accounts()
    tester.test_rbac_no_token()
    
    # Restore settings
    tester.restore_settings()
    
    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
