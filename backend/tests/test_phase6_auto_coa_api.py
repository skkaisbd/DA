"""
Phase 6 Auto-COA API Testing
Tests all API endpoints for the 5-entity rollout (cmt_vendor, supplier, customer, channel, bank)
"""
import requests
import sys
import json
from datetime import datetime

class Phase6AutoCoaAPITester:
    def __init__(self, base_url="https://da37-cmt-bridge.preview.emergentagent.com"):
        self.base_url = base_url
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, passed, detail=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
        status = "✅ PASS" if passed else "❌ FAIL"
        msg = f"{status} - {name}"
        if detail:
            msg += f" | {detail}"
        print(msg)
        self.test_results.append({
            "name": name,
            "passed": passed,
            "detail": detail
        })
        return passed

    def login(self):
        """Login and get token"""
        print("\n🔐 Logging in as admin...")
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": "admin@garment.com", "password": "Admin@123"},
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                self.token = data.get("token")
                self.log_test("Login", self.token is not None, f"Token obtained")
                return True
            else:
                self.log_test("Login", False, f"Status {response.status_code}: {response.text[:100]}")
                return False
        except Exception as e:
            self.log_test("Login", False, f"Error: {str(e)}")
            return False

    def get_headers(self, with_auth=True):
        """Get request headers"""
        headers = {'Content-Type': 'application/json'}
        if with_auth and self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        return headers

    def test_get_settings(self):
        """Test 1: GET /api/rahaza/coa-auto/settings - verify 5 entities"""
        print("\n📋 Test 1: GET /api/rahaza/coa-auto/settings")
        try:
            response = requests.get(
                f"{self.base_url}/api/rahaza/coa-auto/settings",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("GET settings - status code", False, f"Expected 200, got {response.status_code}")
                return False
            
            self.log_test("GET settings - status code", True, "200 OK")
            
            data = response.json()
            entity_types = data.get("entity_types", {})
            
            # Check all 5 entities exist
            required_entities = ["cmt_vendor", "supplier", "customer", "channel", "bank"]
            for entity in required_entities:
                exists = entity in entity_types
                self.log_test(f"Entity '{entity}' exists", exists)
                if not exists:
                    continue
                
                cfg = entity_types[entity]
                # Check enabled=true
                self.log_test(f"Entity '{entity}' enabled", cfg.get("enabled") is True, f"enabled={cfg.get('enabled')}")
            
            # Check specific parent_codes
            expected_parents = {
                "cmt_vendor": "2-1100",
                "supplier": "2-1100",
                "customer": "1-1301",
                "channel": "1-220",
                "bank": "1-1200"
            }
            
            for entity, expected_parent in expected_parents.items():
                if entity in entity_types:
                    actual_parent = entity_types[entity].get("parent_code")
                    self.log_test(
                        f"Entity '{entity}' parent_code",
                        actual_parent == expected_parent,
                        f"Expected {expected_parent}, got {actual_parent}"
                    )
            
            return True
        except Exception as e:
            self.log_test("GET settings", False, f"Error: {str(e)}")
            return False

    def test_backfill_channel(self):
        """Test 2: POST /api/rahaza/coa-auto/backfill/channel - dry-run and commit"""
        print("\n🔄 Test 2: POST /api/rahaza/coa-auto/backfill/channel")
        
        # Test 2a: Dry-run (commit=false)
        try:
            response = requests.post(
                f"{self.base_url}/api/rahaza/coa-auto/backfill/channel?commit=false",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Backfill channel dry-run - status", False, f"Expected 200, got {response.status_code}")
                return False
            
            self.log_test("Backfill channel dry-run - status", True, "200 OK")
            
            data = response.json()
            self.log_test("Backfill channel dry-run - committed=false", data.get("committed") is False)
            self.log_test("Backfill channel dry-run - has counts", "total_entities" in data and "would_create" in data)
            
            total_entities = data.get("total_entities", 0)
            would_create = data.get("would_create", 0)
            already = data.get("already_have_account", 0)
            
            print(f"   📊 Dry-run results: total={total_entities}, would_create={would_create}, already={already}")
            
        except Exception as e:
            self.log_test("Backfill channel dry-run", False, f"Error: {str(e)}")
            return False
        
        # Test 2b: Commit (commit=true)
        try:
            response = requests.post(
                f"{self.base_url}/api/rahaza/coa-auto/backfill/channel?commit=true",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("Backfill channel commit - status", False, f"Expected 200, got {response.status_code}")
                return False
            
            self.log_test("Backfill channel commit - status", True, "200 OK")
            
            data = response.json()
            self.log_test("Backfill channel commit - committed=true", data.get("committed") is True)
            
            created = data.get("created", 0)
            print(f"   📊 Commit results: created={created}")
            
        except Exception as e:
            self.log_test("Backfill channel commit", False, f"Error: {str(e)}")
            return False
        
        # Test 2c: Idempotency - run commit again, should create 0
        try:
            response = requests.post(
                f"{self.base_url}/api/rahaza/coa-auto/backfill/channel?commit=true",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                created_second = data.get("created", 0)
                self.log_test("Backfill channel idempotency", created_second == 0, f"Second commit created={created_second} (should be 0)")
            else:
                self.log_test("Backfill channel idempotency", False, f"Status {response.status_code}")
                
        except Exception as e:
            self.log_test("Backfill channel idempotency", False, f"Error: {str(e)}")
        
        return True

    def test_backfill_empty_collections(self):
        """Test 3: POST backfill for supplier and bank (empty collections)"""
        print("\n📭 Test 3: Backfill empty collections (supplier, bank)")
        
        for entity_type in ["supplier", "bank"]:
            try:
                response = requests.post(
                    f"{self.base_url}/api/rahaza/coa-auto/backfill/{entity_type}?commit=false",
                    headers=self.get_headers(),
                    timeout=10
                )
                
                if response.status_code != 200:
                    self.log_test(f"Backfill {entity_type} - status", False, f"Expected 200, got {response.status_code}")
                    continue
                
                self.log_test(f"Backfill {entity_type} - status", True, "200 OK")
                
                data = response.json()
                total_entities = data.get("total_entities", -1)
                
                # Should be 0 for empty collections
                self.log_test(
                    f"Backfill {entity_type} - total_entities",
                    total_entities == 0,
                    f"Expected 0, got {total_entities}"
                )
                
                # Should have no errors
                errors = data.get("errors", [])
                self.log_test(f"Backfill {entity_type} - no errors", len(errors) == 0, f"Errors: {len(errors)}")
                
            except Exception as e:
                self.log_test(f"Backfill {entity_type}", False, f"Error: {str(e)}")
        
        return True

    def test_get_accounts(self):
        """Test 4: GET /api/rahaza/coa/accounts?active_only=true - verify subledger accounts"""
        print("\n🏦 Test 4: GET /api/rahaza/coa/accounts - verify subledger accounts")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/rahaza/coa/accounts?active_only=true",
                headers=self.get_headers(),
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("GET accounts - status", False, f"Expected 200, got {response.status_code}")
                return False
            
            self.log_test("GET accounts - status", True, "200 OK")
            
            data = response.json()
            accounts = data if isinstance(data, list) else data.get("accounts", data.get("items", []))
            
            # Look for channel subledger accounts (1-220-*)
            channel_accounts = [a for a in accounts if a.get("code", "").startswith("1-220-")]
            self.log_test(
                "Channel subledger accounts exist",
                len(channel_accounts) > 0,
                f"Found {len(channel_accounts)} accounts starting with '1-220-'"
            )
            
            if channel_accounts:
                # Verify properties of first channel account
                acc = channel_accounts[0]
                self.log_test("Channel account - parent_code=1-220", acc.get("parent_code") == "1-220")
                self.log_test("Channel account - is_group=false", acc.get("is_group") is False)
                self.log_test("Channel account - normal_balance=DEBIT", acc.get("normal_balance") == "DEBIT")
            
            # Look for CMT vendor subledger accounts (2-1100-CMT-*)
            cmt_accounts = [a for a in accounts if a.get("code", "").startswith("2-1100-CMT-")]
            self.log_test(
                "CMT vendor subledger accounts exist",
                len(cmt_accounts) > 0,
                f"Found {len(cmt_accounts)} accounts starting with '2-1100-CMT-'"
            )
            
            if cmt_accounts:
                # Verify properties of first CMT account
                acc = cmt_accounts[0]
                self.log_test("CMT account - parent_code=2-1100", acc.get("parent_code") == "2-1100")
                self.log_test("CMT account - is_group=false", acc.get("is_group") is False)
                self.log_test("CMT account - normal_balance=CREDIT", acc.get("normal_balance") == "CREDIT")
            
            return True
        except Exception as e:
            self.log_test("GET accounts", False, f"Error: {str(e)}")
            return False

    def test_put_settings(self):
        """Test 5: PUT /api/rahaza/coa-auto/settings - toggle, change parent, invalid parent, then RESET"""
        print("\n⚙️  Test 5: PUT /api/rahaza/coa-auto/settings")
        
        # Test 5a: Toggle supplier.enabled to false
        try:
            payload = {
                "entity_types": {
                    "supplier": {
                        "enabled": False,
                        "parent_code": "2-1100"
                    }
                }
            }
            
            response = requests.put(
                f"{self.base_url}/api/rahaza/coa-auto/settings",
                headers=self.get_headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("PUT settings - toggle enabled", False, f"Expected 200, got {response.status_code}")
            else:
                self.log_test("PUT settings - toggle enabled", True, "200 OK")
                
                # Verify the change
                get_response = requests.get(
                    f"{self.base_url}/api/rahaza/coa-auto/settings",
                    headers=self.get_headers(),
                    timeout=10
                )
                if get_response.status_code == 200:
                    data = get_response.json()
                    supplier_enabled = data.get("entity_types", {}).get("supplier", {}).get("enabled")
                    self.log_test("PUT settings - verify toggle", supplier_enabled is False, f"supplier.enabled={supplier_enabled}")
                
        except Exception as e:
            self.log_test("PUT settings - toggle enabled", False, f"Error: {str(e)}")
        
        # Test 5b: Change parent_code to a valid code
        try:
            payload = {
                "entity_types": {
                    "supplier": {
                        "enabled": True,
                        "parent_code": "2-1100"  # Valid code
                    }
                }
            }
            
            response = requests.put(
                f"{self.base_url}/api/rahaza/coa-auto/settings",
                headers=self.get_headers(),
                json=payload,
                timeout=10
            )
            
            self.log_test("PUT settings - valid parent_code", response.status_code == 200, f"Status {response.status_code}")
            
        except Exception as e:
            self.log_test("PUT settings - valid parent_code", False, f"Error: {str(e)}")
        
        # Test 5c: Try invalid parent_code (should return 400)
        try:
            payload = {
                "entity_types": {
                    "supplier": {
                        "enabled": True,
                        "parent_code": "ZZ-9999"  # Invalid code
                    }
                }
            }
            
            response = requests.put(
                f"{self.base_url}/api/rahaza/coa-auto/settings",
                headers=self.get_headers(),
                json=payload,
                timeout=10
            )
            
            self.log_test("PUT settings - invalid parent_code returns 400", response.status_code == 400, f"Status {response.status_code}")
            
        except Exception as e:
            self.log_test("PUT settings - invalid parent_code", False, f"Error: {str(e)}")
        
        # Test 5d: RESET all 5 entities to defaults
        print("\n   🔄 Resetting all 5 entities to defaults...")
        try:
            payload = {
                "entity_types": {
                    "cmt_vendor": {"enabled": True, "parent_code": "2-1100"},
                    "supplier": {"enabled": True, "parent_code": "2-1100"},
                    "customer": {"enabled": True, "parent_code": "1-1301"},
                    "channel": {"enabled": True, "parent_code": "1-220"},
                    "bank": {"enabled": True, "parent_code": "1-1200"}
                }
            }
            
            response = requests.put(
                f"{self.base_url}/api/rahaza/coa-auto/settings",
                headers=self.get_headers(),
                json=payload,
                timeout=10
            )
            
            if response.status_code != 200:
                self.log_test("PUT settings - RESET to defaults", False, f"Expected 200, got {response.status_code}")
            else:
                self.log_test("PUT settings - RESET to defaults", True, "200 OK")
                
                # Verify all are reset
                get_response = requests.get(
                    f"{self.base_url}/api/rahaza/coa-auto/settings",
                    headers=self.get_headers(),
                    timeout=10
                )
                if get_response.status_code == 200:
                    data = get_response.json()
                    entity_types = data.get("entity_types", {})
                    
                    all_correct = True
                    for entity, expected in payload["entity_types"].items():
                        actual = entity_types.get(entity, {})
                        if actual.get("enabled") != expected["enabled"] or actual.get("parent_code") != expected["parent_code"]:
                            all_correct = False
                            break
                    
                    self.log_test("PUT settings - verify RESET", all_correct, "All 5 entities reset to defaults")
                
        except Exception as e:
            self.log_test("PUT settings - RESET", False, f"Error: {str(e)}")
        
        return True

    def test_rbac(self):
        """Test 6: RBAC - GET without token should return 401/403"""
        print("\n🔒 Test 6: RBAC - GET /api/rahaza/coa-auto/settings without token")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/rahaza/coa-auto/settings",
                headers={'Content-Type': 'application/json'},  # No Authorization header
                timeout=10
            )
            
            # Should return 401 or 403
            is_unauthorized = response.status_code in [401, 403]
            self.log_test(
                "RBAC - no token returns 401/403",
                is_unauthorized,
                f"Status {response.status_code} (expected 401 or 403)"
            )
            
            return is_unauthorized
        except Exception as e:
            self.log_test("RBAC test", False, f"Error: {str(e)}")
            return False

    def run_all_tests(self):
        """Run all tests"""
        print("=" * 80)
        print("🧪 Phase 6 Auto-COA API Testing")
        print("=" * 80)
        
        # Login first
        if not self.login():
            print("\n❌ Login failed. Cannot proceed with tests.")
            return False
        
        # Run all tests
        self.test_get_settings()
        self.test_backfill_channel()
        self.test_backfill_empty_collections()
        self.test_get_accounts()
        self.test_put_settings()
        self.test_rbac()
        
        # Print summary
        print("\n" + "=" * 80)
        print(f"📊 Test Summary: {self.tests_passed}/{self.tests_run} tests passed")
        print("=" * 80)
        
        if self.tests_passed == self.tests_run:
            print("✅ All tests passed!")
            return True
        else:
            print(f"❌ {self.tests_run - self.tests_passed} test(s) failed")
            return False

def main():
    tester = Phase6AutoCoaAPITester()
    success = tester.run_all_tests()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
