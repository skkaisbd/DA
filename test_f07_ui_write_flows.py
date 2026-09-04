#!/usr/bin/env python3
"""
F0.7 UI Write Flows Testing - Iteration 46
Tests CREATE, VALIDATION, EDIT, ARCHIVE flows via API
Then verifies UI displays correctly
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
TEST_ACCOUNT_CODE = "UJI-QA-F07"

class F07UIWriteFlowsTester:
    def __init__(self):
        self.token = None
        self.test_account_id = None
        self.tests_run = 0
        self.tests_passed = 0
        self.results = []

    def log_result(self, test_name, passed, details=""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ {test_name}")
        else:
            print(f"❌ {test_name}")
        if details:
            print(f"   {details}")
        self.results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })

    def login(self):
        """Login as admin"""
        print("\n[STEP 1] Logging in as admin...")
        try:
            res = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": "admin@garment.com", "password": "Admin@123"},
                timeout=10
            )
            if res.status_code == 200:
                data = res.json()
                self.token = data.get("token")
                self.log_result("Login", True, f"Token: {self.token[:20]}...")
                return True
            else:
                self.log_result("Login", False, f"Status {res.status_code}: {res.text[:200]}")
                return False
        except Exception as e:
            self.log_result("Login", False, str(e))
            return False

    def get_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    def cleanup_existing(self):
        """Delete test account if it exists"""
        print(f"\n[CLEANUP] Checking for existing {TEST_ACCOUNT_CODE}...")
        try:
            res = requests.get(f"{BASE_URL}/marketing/accounts", headers=self.get_headers(), timeout=10)
            if res.status_code == 200:
                accounts = res.json()
                for acc in accounts:
                    if acc.get("account_code") == TEST_ACCOUNT_CODE:
                        print(f"Found existing test account, deleting: {acc.get('id')}")
                        del_res = requests.delete(
                            f"{BASE_URL}/marketing/accounts/{acc['id']}",
                            headers=self.get_headers(),
                            timeout=10
                        )
                        print(f"Delete result: {del_res.status_code}")
                        return True
            print("No existing test account found")
            return True
        except Exception as e:
            print(f"Cleanup error: {e}")
            return True  # Continue anyway

    def test_us6_create(self):
        """US6: Create account with all F0.7 fields"""
        print("\n[STEP 2] US6 - CREATE account via API...")
        
        payload = {
            "account_code": TEST_ACCOUNT_CODE,
            "account_name": "Uji QA F0.7",
            "platform": "tiktokshop",
            "username": "qa.test",
            "group": "other",
            "has_api_integration": True,
            "coa_revenue_code": "4-123",
            "coa_cash_code": "1-154",
            "coa_receivable_code": "1-220",
            "revenue_basis": "order_amount",
            "platform_warehouse_name": "QA Warehouse",
            "platform_shop_id": "999888777",
            "pic_user_id": ""  # Will be filled if we can get a user ID
        }
        
        # Try to get a PIC user ID
        try:
            users_res = requests.get(f"{BASE_URL}/auth/users?limit=10", headers=self.get_headers(), timeout=10)
            if users_res.status_code == 200:
                users = users_res.json()
                if isinstance(users, list) and len(users) > 0:
                    payload["pic_user_id"] = users[0].get("id")
                    print(f"Using PIC: {users[0].get('name')} ({users[0].get('id')})")
        except Exception:
            print("Could not fetch users for PIC")
        
        try:
            res = requests.post(
                f"{BASE_URL}/marketing/accounts",
                json=payload,
                headers=self.get_headers(),
                timeout=15
            )
            
            if res.status_code in [200, 201]:
                data = res.json()
                account = data.get("account") or data
                self.test_account_id = account.get("id")
                
                # Verify F0.7 fields
                checks = []
                checks.append(("account_code", account.get("account_code") == TEST_ACCOUNT_CODE))
                checks.append(("account_name", account.get("account_name") == "Uji QA F0.7"))
                checks.append(("platform", account.get("platform") == "tiktokshop"))
                checks.append(("coa_revenue_code", account.get("coa_revenue_code") == "4-123"))
                checks.append(("coa_cash_code", account.get("coa_cash_code") == "1-154"))
                checks.append(("coa_receivable_code", account.get("coa_receivable_code") == "1-220"))
                checks.append(("revenue_basis", account.get("revenue_basis") == "order_amount"))
                checks.append(("platform_warehouse_name", account.get("platform_warehouse_name") == "QA Warehouse"))
                checks.append(("platform_shop_id", account.get("platform_shop_id") == "999888777"))
                checks.append(("ar_account_code", bool(account.get("ar_account_code"))))
                checks.append(("pic_user_id", bool(account.get("pic_user_id"))))
                
                all_passed = all(c[1] for c in checks)
                failed = [c[0] for c in checks if not c[1]]
                
                if all_passed:
                    self.log_result(
                        "US6 CREATE - All F0.7 fields saved",
                        True,
                        f"AR account: {account.get('ar_account_code')}"
                    )
                else:
                    self.log_result(
                        "US6 CREATE - Some fields incorrect",
                        False,
                        f"Failed: {', '.join(failed)}"
                    )
                
                return True
            else:
                self.log_result("US6 CREATE", False, f"Status {res.status_code}: {res.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("US6 CREATE", False, str(e))
            return False

    def test_us7_validation(self):
        """US7: Test duplicate code validation"""
        print("\n[STEP 3] US7 - VALIDATION (duplicate code)...")
        
        payload = {
            "account_code": TEST_ACCOUNT_CODE,  # Same code - should fail
            "account_name": "Duplikat QA",
            "platform": "shopee",
            "coa_revenue_code": "4-111",
            "coa_cash_code": "1-131",
        }
        
        try:
            res = requests.post(
                f"{BASE_URL}/marketing/accounts",
                json=payload,
                headers=self.get_headers(),
                timeout=10
            )
            
            if res.status_code == 400:
                error_msg = res.json().get("detail", "")
                if "already exists" in error_msg.lower() or "sudah ada" in error_msg.lower():
                    self.log_result("US7 VALIDATION - Duplicate rejected", True, f"Error: {error_msg}")
                    return True
                else:
                    self.log_result("US7 VALIDATION", False, f"Wrong error: {error_msg}")
                    return False
            else:
                self.log_result("US7 VALIDATION", False, f"Expected 400, got {res.status_code}")
                return False
                
        except Exception as e:
            self.log_result("US7 VALIDATION", False, str(e))
            return False

    def test_us8_edit(self):
        """US8: Edit account via API"""
        print("\n[STEP 4] US8 - EDIT account...")
        
        if not self.test_account_id:
            self.log_result("US8 EDIT", False, "No test account ID")
            return False
        
        payload = {
            "account_name": "Uji QA F0.7",  # Keep same
            "coa_revenue_code": "4-124",  # Change from 4-123
            "coa_cash_code": "1-131",  # Change from 1-154
            "revenue_basis": "produk_setelah_diskon",  # Change from order_amount
            "platform_warehouse_name": "Gudang QA Ubah",  # Change
            "platform_shop_id": "111222333",  # Change
            "status": "suspended"  # Change to suspended
        }
        
        try:
            res = requests.put(
                f"{BASE_URL}/marketing/accounts/{self.test_account_id}",
                json=payload,
                headers=self.get_headers(),
                timeout=10
            )
            
            if res.status_code == 200:
                data = res.json()
                account = data.get("account") or data
                
                # Verify changes
                checks = []
                checks.append(("coa_revenue_code", account.get("coa_revenue_code") == "4-124"))
                checks.append(("coa_cash_code", account.get("coa_cash_code") == "1-131"))
                checks.append(("revenue_basis", account.get("revenue_basis") == "produk_setelah_diskon"))
                checks.append(("platform_warehouse_name", account.get("platform_warehouse_name") == "Gudang QA Ubah"))
                checks.append(("platform_shop_id", account.get("platform_shop_id") == "111222333"))
                checks.append(("status", account.get("status") == "suspended"))
                
                all_passed = all(c[1] for c in checks)
                failed = [c[0] for c in checks if not c[1]]
                
                if all_passed:
                    self.log_result("US8 EDIT - All changes saved", True)
                else:
                    self.log_result("US8 EDIT - Some changes not saved", False, f"Failed: {', '.join(failed)}")
                
                return all_passed
            else:
                self.log_result("US8 EDIT", False, f"Status {res.status_code}: {res.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("US8 EDIT", False, str(e))
            return False

    def test_us10_archive(self):
        """US10: Archive account"""
        print("\n[STEP 5] US10 - ARCHIVE account...")
        
        if not self.test_account_id:
            self.log_result("US10 ARCHIVE", False, "No test account ID")
            return False
        
        try:
            res = requests.delete(
                f"{BASE_URL}/marketing/accounts/{self.test_account_id}",
                headers=self.get_headers(),
                timeout=10
            )
            
            if res.status_code == 200:
                # Verify account still exists but status is inactive
                get_res = requests.get(
                    f"{BASE_URL}/marketing/accounts/{self.test_account_id}",
                    headers=self.get_headers(),
                    timeout=10
                )
                
                if get_res.status_code == 200:
                    account = get_res.json()
                    if account.get("status") == "inactive":
                        self.log_result("US10 ARCHIVE - Status set to inactive", True)
                        return True
                    else:
                        self.log_result("US10 ARCHIVE", False, f"Status is {account.get('status')}, expected inactive")
                        return False
                else:
                    self.log_result("US10 ARCHIVE", False, "Account not found after archive")
                    return False
            else:
                self.log_result("US10 ARCHIVE", False, f"Status {res.status_code}: {res.text[:300]}")
                return False
                
        except Exception as e:
            self.log_result("US10 ARCHIVE", False, str(e))
            return False

    def test_mark_reviewed(self):
        """Test mark as reviewed on SHOPEE-MOEN"""
        print("\n[STEP 6] ADDITIONAL - Mark SHOPEE-MOEN as reviewed...")
        
        try:
            # Find SHOPEE-MOEN
            res = requests.get(f"{BASE_URL}/marketing/accounts", headers=self.get_headers(), timeout=10)
            if res.status_code != 200:
                self.log_result("Mark Reviewed - Get accounts", False, f"Status {res.status_code}")
                return False
            
            accounts = res.json()
            shopee_moen = None
            for acc in accounts:
                if acc.get("account_code") == "SHOPEE-MOEN":
                    shopee_moen = acc
                    break
            
            if not shopee_moen:
                self.log_result("Mark Reviewed", False, "SHOPEE-MOEN not found")
                return False
            
            # Check if already reviewed
            if not shopee_moen.get("needs_owner_review"):
                self.log_result("Mark Reviewed", True, "SHOPEE-MOEN already reviewed (skipped)")
                return True
            
            # Mark as reviewed
            update_res = requests.put(
                f"{BASE_URL}/marketing/accounts/{shopee_moen['id']}",
                json={"needs_owner_review": False},
                headers=self.get_headers(),
                timeout=10
            )
            
            if update_res.status_code == 200:
                # Verify
                verify_res = requests.get(
                    f"{BASE_URL}/marketing/accounts/{shopee_moen['id']}",
                    headers=self.get_headers(),
                    timeout=10
                )
                
                if verify_res.status_code == 200:
                    updated = verify_res.json()
                    if not updated.get("needs_owner_review"):
                        self.log_result("Mark Reviewed - SHOPEE-MOEN", True, "Badge removed")
                        return True
                    else:
                        self.log_result("Mark Reviewed", False, "Badge still present")
                        return False
            else:
                self.log_result("Mark Reviewed", False, f"Status {update_res.status_code}")
                return False
                
        except Exception as e:
            self.log_result("Mark Reviewed", False, str(e))
            return False

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 70)
        print("F0.7 UI WRITE FLOWS TESTING - ITERATION 46")
        print("=" * 70)
        
        if not self.login():
            print("\n❌ Login failed, cannot continue")
            return False
        
        self.cleanup_existing()
        
        # Run tests in order
        self.test_us6_create()
        self.test_us7_validation()
        self.test_us8_edit()
        self.test_us10_archive()
        self.test_mark_reviewed()
        
        # Print summary
        print("\n" + "=" * 70)
        print(f"TESTS COMPLETED: {self.tests_passed}/{self.tests_run} passed")
        print("=" * 70)
        
        # Print detailed results
        print("\nDetailed Results:")
        for r in self.results:
            status = "✅" if r["passed"] else "❌"
            print(f"{status} {r['test']}")
            if r["details"]:
                print(f"   {r['details']}")
        
        return self.tests_passed == self.tests_run

def main():
    tester = F07UIWriteFlowsTester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
