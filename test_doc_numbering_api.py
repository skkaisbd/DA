"""
Backend API Testing for Document Numbering Policy Enforcement
Tests API behavior for enforced vs non-enforced document types
"""
import requests
import sys

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"

class DocNumberingAPITest:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []

    def log(self, msg, status="INFO"):
        prefix = {
            "PASS": "✅",
            "FAIL": "❌",
            "INFO": "ℹ️",
            "WARN": "⚠️"
        }.get(status, "INFO")
        print(f"{prefix} {msg}")

    def login(self):
        """Login and get token"""
        self.log("Logging in as admin@garment.com...")
        try:
            response = requests.post(
                f"{BASE_URL}/auth/login",
                json={"email": "admin@garment.com", "password": "Admin@123"},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                if self.token:
                    self.log("Login successful", "PASS")
                    return True
                else:
                    self.log("Login response missing token", "FAIL")
                    return False
            else:
                self.log(f"Login failed: {response.status_code} - {response.text}", "FAIL")
                return False
        except Exception as e:
            self.log(f"Login error: {str(e)}", "FAIL")
            return False

    def test_reject_manual_mode_for_unenforced_type(self):
        """TEST 4: Verify API rejects manual mode for unenforced document types"""
        self.log("\n=== TEST 4: API Rejection for Unenforced Document Types ===")
        
        # Test 1: Try to set manual mode for unenforced type (should fail with 400)
        self.tests_run += 1
        self.log("Test 4.1: Attempting to set manual mode for 'rahaza_journal_entries.je_number' (unenforced)...")
        try:
            response = requests.put(
                f"{BASE_URL}/admin/doc-numbering",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json"
                },
                json={
                    "key": "rahaza_journal_entries.je_number",
                    "mode": "manual",
                    "active": True
                },
                timeout=10
            )
            
            if response.status_code == 400:
                data = response.json()
                detail = data.get("detail", "")
                if "belum bisa diubah" in detail.lower() or "belum" in detail.lower():
                    self.log(f"CORRECT: API rejected with 400 - {detail}", "PASS")
                    self.tests_passed += 1
                else:
                    self.log(f"FAIL: Got 400 but wrong message: {detail}", "FAIL")
                    self.tests_failed += 1
                    self.failures.append("Test 4.1: Wrong error message for unenforced type")
            else:
                self.log(f"FAIL: Expected 400, got {response.status_code} - {response.text}", "FAIL")
                self.tests_failed += 1
                self.failures.append(f"Test 4.1: Expected 400, got {response.status_code}")
        except Exception as e:
            self.log(f"FAIL: Error during test - {str(e)}", "FAIL")
            self.tests_failed += 1
            self.failures.append(f"Test 4.1: Exception - {str(e)}")

        # Test 2: Verify format change is still allowed for unenforced type (should succeed with 200)
        self.tests_run += 1
        self.log("Test 4.2: Attempting to change format for 'rahaza_journal_entries.je_number' (should succeed)...")
        try:
            response = requests.put(
                f"{BASE_URL}/admin/doc-numbering",
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Content-Type": "application/json"
                },
                json={
                    "key": "rahaza_journal_entries.je_number",
                    "format": "JE-{YYYY}{MM}{DD}-{SEQ:4}",
                    "active": True
                },
                timeout=10
            )
            
            if response.status_code == 200:
                self.log("CORRECT: Format change allowed for unenforced type", "PASS")
                self.tests_passed += 1
            else:
                self.log(f"FAIL: Expected 200, got {response.status_code} - {response.text}", "FAIL")
                self.tests_failed += 1
                self.failures.append(f"Test 4.2: Expected 200, got {response.status_code}")
        except Exception as e:
            self.log(f"FAIL: Error during test - {str(e)}", "FAIL")
            self.tests_failed += 1
            self.failures.append(f"Test 4.2: Exception - {str(e)}")

    def test_enforced_types_can_change_mode(self):
        """Verify enforced types can change mode successfully"""
        self.log("\n=== Additional Test: Enforced Types Can Change Mode ===")
        
        # Test changing mode for an enforced type (should succeed)
        self.tests_run += 1
        self.log("Testing mode change for 'dewi_kasbon_requests.request_number' (enforced)...")
        try:
            # First, get current mode
            response = requests.get(
                f"{BASE_URL}/admin/doc-numbering",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                items = data.get("items", [])
                kasbon_item = next((item for item in items if item["key"] == "dewi_kasbon_requests.request_number"), None)
                
                if kasbon_item:
                    current_mode = kasbon_item.get("mode", "auto")
                    new_mode = "manual" if current_mode == "auto" else "auto"
                    
                    # Try to change mode
                    response = requests.put(
                        f"{BASE_URL}/admin/doc-numbering",
                        headers={
                            "Authorization": f"Bearer {self.token}",
                            "Content-Type": "application/json"
                        },
                        json={
                            "key": "dewi_kasbon_requests.request_number",
                            "mode": new_mode,
                            "active": True
                        },
                        timeout=10
                    )
                    
                    if response.status_code == 200:
                        self.log(f"CORRECT: Mode change allowed for enforced type (changed to {new_mode})", "PASS")
                        self.tests_passed += 1
                        
                        # Change back to original mode
                        requests.put(
                            f"{BASE_URL}/admin/doc-numbering",
                            headers={
                                "Authorization": f"Bearer {self.token}",
                                "Content-Type": "application/json"
                            },
                            json={
                                "key": "dewi_kasbon_requests.request_number",
                                "mode": current_mode,
                                "active": True
                            },
                            timeout=10
                        )
                    else:
                        self.log(f"FAIL: Expected 200, got {response.status_code}", "FAIL")
                        self.tests_failed += 1
                        self.failures.append(f"Enforced type mode change failed: {response.status_code}")
                else:
                    self.log("WARN: Could not find kasbon item in registry", "WARN")
                    self.tests_failed += 1
                    self.failures.append("Could not find kasbon item")
            else:
                self.log(f"FAIL: Could not fetch doc numbering list: {response.status_code}", "FAIL")
                self.tests_failed += 1
                self.failures.append(f"Could not fetch doc numbering list: {response.status_code}")
        except Exception as e:
            self.log(f"FAIL: Error during test - {str(e)}", "FAIL")
            self.tests_failed += 1
            self.failures.append(f"Enforced type test exception - {str(e)}")

    def run_all_tests(self):
        """Run all backend tests"""
        self.log("=" * 60)
        self.log("BACKEND API TESTING - Document Numbering Policy")
        self.log("=" * 60)
        
        if not self.login():
            self.log("Cannot proceed without authentication", "FAIL")
            return False
        
        # Run tests
        self.test_reject_manual_mode_for_unenforced_type()
        self.test_enforced_types_can_change_mode()
        
        # Summary
        self.log("\n" + "=" * 60)
        self.log("TEST SUMMARY")
        self.log("=" * 60)
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}", "PASS")
        self.log(f"Failed: {self.tests_failed}", "FAIL" if self.tests_failed > 0 else "INFO")
        
        if self.failures:
            self.log("\nFailed Tests:")
            for failure in self.failures:
                self.log(f"  - {failure}", "FAIL")
        
        return self.tests_failed == 0

def main():
    tester = DocNumberingAPITest()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
