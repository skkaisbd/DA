"""
Test Merge Verification — 6 Parallel Repos Consolidation
CV. Dewi Aditya ERP

Verifies:
1. After-Sales bridge idempotency (repo6)
2. Finance RBAC fix (repo5)

Backend already verified via 13 POC scripts (ALL PASS).
This script focuses on the specific merge-related changes.
"""
import requests
import sys
import uuid
from datetime import datetime

# PUBLIC ENDPOINT
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class MergeVerificationTester:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.admin_token = None
        self.finance_token = None
        self.test_data_ids = []  # Track created data for cleanup

    def log(self, msg, status="INFO"):
        prefix = {
            "PASS": "✅",
            "FAIL": "❌",
            "INFO": "🔍",
            "WARN": "⚠️"
        }.get(status, "ℹ️")
        print(f"{prefix} {msg}")

    def run_test(self, name, func):
        """Run a single test function"""
        self.tests_run += 1
        self.log(f"Testing: {name}", "INFO")
        try:
            func()
            self.tests_passed += 1
            self.log(f"PASSED: {name}", "PASS")
            return True
        except AssertionError as e:
            self.log(f"FAILED: {name} - {str(e)}", "FAIL")
            return False
        except Exception as e:
            self.log(f"ERROR: {name} - {str(e)}", "FAIL")
            return False

    def login(self, email, password):
        """Login and return token"""
        self.log(f"Logging in as {email}...")
        r = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
        data = r.json()
        token = data.get("token")
        assert token, "No token in response"
        self.log(f"Login successful: {email}")
        return token

    def headers(self, token):
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 1: After-Sales Bridge Idempotency (repo6)
    # ═══════════════════════════════════════════════════════════════════════════

    def test_1a_create_return(self):
        """Create a marketing return"""
        payload = {
            "account_id": None,
            "account_name": "Test Account",
            "date": datetime.now().date().isoformat(),
            "order_id": f"TEST-ORD-{uuid.uuid4().hex[:8]}",
            "platform": "shopee",
            "product": "Test Product",
            "price": 100000,
            "reason": "ukuran_salah",
            "reason_detail": "Test return for merge verification",
            "courier": "jnt",
            "refund_type": "full_refund",
            "notes": "Automated test - safe to delete"
        }
        r = requests.post(
            f"{BASE_URL}/api/marketing/returns",
            json=payload,
            headers=self.headers(self.admin_token),
            timeout=10
        )
        assert r.status_code == 200, f"Create return failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("success"), "Response not successful"
        ret = data.get("data")
        assert ret and ret.get("id"), "No return ID in response"
        self.test_return_id = ret["id"]
        self.test_data_ids.append(("marketing_return", self.test_return_id))
        self.log(f"Created return: {self.test_return_id}")

    def test_1b_approve_return(self):
        """Approve the return"""
        r = requests.post(
            f"{BASE_URL}/api/marketing/returns/{self.test_return_id}/approve",
            json={},
            headers=self.headers(self.admin_token),
            timeout=10
        )
        assert r.status_code == 200, f"Approve failed: {r.status_code} {r.text}"
        data = r.json()
        assert data.get("success"), "Approve not successful"
        self.log(f"Approved return: {self.test_return_id}")

    def test_1c_create_wh_return_idempotent(self):
        """Test idempotency: create wh_return twice, second call should return existing"""
        # First call - should create
        r1 = requests.post(
            f"{BASE_URL}/api/marketing/returns/{self.test_return_id}/create-wh-return",
            json={},
            headers=self.headers(self.admin_token),
            timeout=10
        )
        assert r1.status_code == 200, f"First create-wh-return failed: {r1.status_code} {r1.text}"
        data1 = r1.json()
        assert data1.get("success"), "First call not successful"
        wh_return_id = data1.get("data", {}).get("id") or data1.get("wh_return_id")
        assert wh_return_id, "No wh_return_id in first response"
        self.test_data_ids.append(("wh_return", wh_return_id))
        self.log(f"First call created wh_return: {wh_return_id}")

        # Second call - should return existing (idempotent)
        r2 = requests.post(
            f"{BASE_URL}/api/marketing/returns/{self.test_return_id}/create-wh-return",
            json={},
            headers=self.headers(self.admin_token),
            timeout=10
        )
        assert r2.status_code == 200, f"Second create-wh-return failed: {r2.status_code} {r2.text}"
        data2 = r2.json()
        assert data2.get("success"), "Second call not successful"
        assert data2.get("already_exists") == True, "Second call should indicate already_exists=True"
        wh_return_id_2 = data2.get("data", {}).get("id") or data2.get("wh_return_id")
        assert wh_return_id_2 == wh_return_id, f"Second call returned different wh_return_id: {wh_return_id_2} != {wh_return_id}"
        self.log(f"Second call returned same wh_return (idempotent): {wh_return_id_2}")

    def test_1d_guard_pending_return(self):
        """Guard: create-wh-return on pending return should be rejected with 400"""
        # Create a new return in pending status
        payload = {
            "account_id": None,
            "account_name": "Test Account 2",
            "date": datetime.now().date().isoformat(),
            "order_id": f"TEST-ORD-{uuid.uuid4().hex[:8]}",
            "platform": "shopee",
            "product": "Test Product 2",
            "price": 50000,
            "reason": "produk_cacat",
            "reason_detail": "Test guard for pending status",
            "courier": "jnt",
            "refund_type": "full_refund",
            "notes": "Automated test - safe to delete"
        }
        r = requests.post(
            f"{BASE_URL}/api/marketing/returns",
            json=payload,
            headers=self.headers(self.admin_token),
            timeout=10
        )
        assert r.status_code == 200, f"Create return failed: {r.status_code} {r.text}"
        data = r.json()
        pending_return_id = data.get("data", {}).get("id")
        assert pending_return_id, "No return ID"
        self.test_data_ids.append(("marketing_return", pending_return_id))
        self.log(f"Created pending return: {pending_return_id}")

        # Try to create wh_return on pending return - should fail with 400
        r_guard = requests.post(
            f"{BASE_URL}/api/marketing/returns/{pending_return_id}/create-wh-return",
            json={},
            headers=self.headers(self.admin_token),
            timeout=10
        )
        assert r_guard.status_code == 400, f"Expected 400 for pending return, got {r_guard.status_code}"
        self.log(f"Guard working: pending return rejected with 400")

    # ═══════════════════════════════════════════════════════════════════════════
    # TEST 2: Finance RBAC Fix (repo5)
    # ═══════════════════════════════════════════════════════════════════════════

    def test_2a_finance_petty_cash_create(self):
        """Finance user (role accounting) should be able to create petty cash fund"""
        payload = {
            "name": f"Test Fund {uuid.uuid4().hex[:6]}",
            "custodian_name": "Test Custodian",
            "opening_balance": 1000000,
            "bank_account_code": "1-1201",
            "notes": "Automated test - safe to delete"
        }
        r = requests.post(
            f"{BASE_URL}/api/finance/petty-cash/funds",
            json=payload,
            headers=self.headers(self.finance_token),
            timeout=10
        )
        assert r.status_code == 200, f"Create petty cash fund failed: {r.status_code} {r.text}"
        data = r.json()
        fund_id = data.get("id")
        assert fund_id, "No fund ID in response"
        self.test_fund_id = fund_id
        self.test_data_ids.append(("petty_cash_fund", fund_id))
        self.log(f"Finance user created petty cash fund: {fund_id}")

    def test_2b_finance_petty_cash_list(self):
        """Finance user should be able to list petty cash funds"""
        r = requests.get(
            f"{BASE_URL}/api/finance/petty-cash/funds",
            headers=self.headers(self.finance_token),
            timeout=10
        )
        assert r.status_code == 200, f"List petty cash funds failed: {r.status_code} {r.text}"
        data = r.json()
        assert "items" in data, "No items in response"
        self.log(f"Finance user listed petty cash funds: {len(data['items'])} items")

    def test_2c_finance_bank_transfer_create(self):
        """Finance user (role accounting) should be able to create bank transfer"""
        payload = {
            "from_account_code": "1-1201",
            "from_account_name": "Bank BCA",
            "to_account_code": "1-1202",
            "to_account_name": "Bank Mandiri",
            "amount": 500000,
            "transfer_date": datetime.now().date().isoformat(),
            "memo": "Automated test transfer - safe to delete",
            "ref_external": f"TEST-{uuid.uuid4().hex[:8]}"
        }
        r = requests.post(
            f"{BASE_URL}/api/finance/bank-transfers",
            json=payload,
            headers=self.headers(self.finance_token),
            timeout=10
        )
        assert r.status_code == 200, f"Create bank transfer failed: {r.status_code} {r.text}"
        data = r.json()
        transfer = data.get("transfer")
        assert transfer and transfer.get("id"), "No transfer ID in response"
        self.test_transfer_id = transfer["id"]
        self.test_data_ids.append(("bank_transfer", self.test_transfer_id))
        self.log(f"Finance user created bank transfer: {self.test_transfer_id}")

    def test_2d_finance_bank_transfer_list(self):
        """Finance user should be able to list bank transfers"""
        r = requests.get(
            f"{BASE_URL}/api/finance/bank-transfers",
            headers=self.headers(self.finance_token),
            timeout=10
        )
        assert r.status_code == 200, f"List bank transfers failed: {r.status_code} {r.text}"
        data = r.json()
        assert "items" in data, "No items in response"
        self.log(f"Finance user listed bank transfers: {len(data['items'])} items")

    # ═══════════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════

    def cleanup(self):
        """Clean up test data"""
        self.log("Cleaning up test data...", "INFO")
        for data_type, data_id in reversed(self.test_data_ids):
            try:
                if data_type == "marketing_return":
                    r = requests.delete(
                        f"{BASE_URL}/api/marketing/returns/{data_id}",
                        headers=self.headers(self.admin_token),
                        timeout=10
                    )
                    if r.status_code == 200:
                        self.log(f"Deleted marketing return: {data_id}")
                elif data_type == "wh_return":
                    r = requests.delete(
                        f"{BASE_URL}/api/wh/returns/{data_id}",
                        headers=self.headers(self.admin_token),
                        timeout=10
                    )
                    if r.status_code == 200:
                        self.log(f"Deleted wh_return: {data_id}")
                elif data_type == "petty_cash_fund":
                    # Close fund first
                    r = requests.post(
                        f"{BASE_URL}/api/finance/petty-cash/funds/{data_id}/close",
                        json={},
                        headers=self.headers(self.finance_token),
                        timeout=10
                    )
                    if r.status_code == 200:
                        self.log(f"Closed petty cash fund: {data_id}")
                elif data_type == "bank_transfer":
                    # Bank transfers can't be deleted, just log
                    self.log(f"Bank transfer {data_id} left in system (no delete endpoint)")
            except Exception as e:
                self.log(f"Cleanup error for {data_type} {data_id}: {str(e)}", "WARN")

    def run_all_tests(self):
        """Run all merge verification tests"""
        print("\n" + "="*80)
        print("MERGE VERIFICATION TEST SUITE")
        print("6 Parallel Repos Consolidation - CV. Dewi Aditya ERP")
        print("="*80 + "\n")

        # Login
        try:
            self.admin_token = self.login("admin@garment.com", "Admin@123")
            self.finance_token = self.login("finance@dewiaditya.id", "Dewi@123")
        except Exception as e:
            self.log(f"Login failed: {str(e)}", "FAIL")
            return 1

        # Test 1: After-Sales Bridge Idempotency
        print("\n" + "-"*80)
        print("TEST 1: After-Sales Bridge Idempotency (repo6)")
        print("-"*80)
        self.run_test("1a. Create marketing return", self.test_1a_create_return)
        self.run_test("1b. Approve return", self.test_1b_approve_return)
        self.run_test("1c. Create wh_return (idempotent - call 2x)", self.test_1c_create_wh_return_idempotent)
        self.run_test("1d. Guard: reject create-wh-return on pending return", self.test_1d_guard_pending_return)

        # Test 2: Finance RBAC Fix
        print("\n" + "-"*80)
        print("TEST 2: Finance RBAC Fix (repo5)")
        print("-"*80)
        self.run_test("2a. Finance user creates petty cash fund", self.test_2a_finance_petty_cash_create)
        self.run_test("2b. Finance user lists petty cash funds", self.test_2b_finance_petty_cash_list)
        self.run_test("2c. Finance user creates bank transfer", self.test_2c_finance_bank_transfer_create)
        self.run_test("2d. Finance user lists bank transfers", self.test_2d_finance_bank_transfer_list)

        # Cleanup
        print("\n" + "-"*80)
        print("CLEANUP")
        print("-"*80)
        self.cleanup()

        # Summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        print(f"Tests Run: {self.tests_run}")
        print(f"Tests Passed: {self.tests_passed}")
        print(f"Tests Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        print("="*80 + "\n")

        return 0 if self.tests_passed == self.tests_run else 1


if __name__ == "__main__":
    tester = MergeVerificationTester()
    sys.exit(tester.run_all_tests())
