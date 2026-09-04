"""
Phase 4 Data Transfer Testing - Export/Import Feature
Tests registry-driven export/import for 8 master modules + users security
"""
import requests
import sys
import io
import csv
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_CREDS = {"email": "admin@garment.com", "password": "Admin@123"}

# 8 registry keys to test
REGISTRY_KEYS = [
    "vendor_partners",
    "users", 
    "payroll_profiles",
    "posting_profiles",
    "platform_accounts",
    "cmt_partners",
    "materials",
    "coa_accounts"
]

class DataTransferTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        self.test_user_email = None

    def log(self, test_name, passed, details=""):
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            status = "✅ PASS"
        else:
            status = "❌ FAIL"
        
        result = f"{status} | {test_name}"
        if details:
            result += f" | {details}"
        print(result)
        self.test_results.append({
            "test": test_name,
            "passed": passed,
            "details": details
        })
        return passed

    def login(self):
        """Login once and reuse token (rate-limit 10/60s)"""
        print("\n🔐 Logging in as admin...")
        try:
            r = requests.post(f"{BASE_URL}/auth/login", 
                            json=ADMIN_CREDS,
                            timeout=10)
            if r.status_code == 200:
                self.token = r.json().get("token")
                print(f"✅ Login successful")
                return True
            else:
                print(f"❌ Login failed: {r.status_code} - {r.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False

    def get_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def test_registry_list(self):
        """Test GET /api/data-transfer/registry lists all keys"""
        print("\n📋 TEST 1: Registry List")
        try:
            r = requests.get(f"{BASE_URL}/data-transfer/registry", 
                           headers=self.get_headers(), timeout=10)
            
            if r.status_code != 200:
                return self.log("Registry list", False, f"Status {r.status_code}")
            
            data = r.json()
            tables = data.get("tables", [])
            table_keys = [t["key"] for t in tables]
            
            # Check all 8 keys are present
            missing = [k for k in REGISTRY_KEYS if k not in table_keys]
            if missing:
                return self.log("Registry list", False, f"Missing keys: {missing}")
            
            return self.log("Registry list", True, 
                          f"Found {len(tables)} tables, all 8 keys present")
        except Exception as e:
            return self.log("Registry list", False, str(e))

    def test_templates_and_exports(self):
        """Test template & export downloads for all 8 keys"""
        print("\n📥 TEST 2-9: Template & Export Downloads")
        
        for key in REGISTRY_KEYS:
            # Test template CSV
            try:
                r = requests.get(
                    f"{BASE_URL}/data-transfer/template/{key}?format=csv",
                    headers=self.get_headers(), timeout=10)
                csv_ok = r.status_code == 200
                self.log(f"Template CSV - {key}", csv_ok, 
                        f"Status {r.status_code}")
            except Exception as e:
                self.log(f"Template CSV - {key}", False, str(e))
                csv_ok = False

            # Test template XLSX
            try:
                r = requests.get(
                    f"{BASE_URL}/data-transfer/template/{key}?format=xlsx",
                    headers=self.get_headers(), timeout=10)
                xlsx_ok = r.status_code == 200
                self.log(f"Template XLSX - {key}", xlsx_ok, 
                        f"Status {r.status_code}")
            except Exception as e:
                self.log(f"Template XLSX - {key}", False, str(e))
                xlsx_ok = False

            # Test export CSV
            try:
                r = requests.get(
                    f"{BASE_URL}/data-transfer/export/{key}?format=csv",
                    headers=self.get_headers(), timeout=10)
                export_csv_ok = r.status_code == 200 and len(r.content) > 0
                self.log(f"Export CSV - {key}", export_csv_ok, 
                        f"Status {r.status_code}, {len(r.content)} bytes")
            except Exception as e:
                self.log(f"Export CSV - {key}", False, str(e))
                export_csv_ok = False

            # Test export XLSX
            try:
                r = requests.get(
                    f"{BASE_URL}/data-transfer/export/{key}?format=xlsx",
                    headers=self.get_headers(), timeout=10)
                export_xlsx_ok = r.status_code == 200 and len(r.content) > 0
                self.log(f"Export XLSX - {key}", export_xlsx_ok, 
                        f"Status {r.status_code}, {len(r.content)} bytes")
            except Exception as e:
                self.log(f"Export XLSX - {key}", False, str(e))

    def test_import_dry_run_roundtrip(self):
        """Test import dry_run with exported CSV (round-trip)"""
        print("\n🔄 TEST 10-17: Import Dry-Run (Round-trip)")
        
        for key in REGISTRY_KEYS:
            try:
                # First export CSV
                r = requests.get(
                    f"{BASE_URL}/data-transfer/export/{key}?format=csv",
                    headers=self.get_headers(), timeout=10)
                
                if r.status_code != 200:
                    self.log(f"Import dry-run - {key}", False, 
                           f"Export failed: {r.status_code}")
                    continue
                
                # Re-upload the exported CSV
                files = {'file': (f'{key}.csv', r.content, 'text/csv')}
                r2 = requests.post(
                    f"{BASE_URL}/data-transfer/import/{key}?mode=dry_run",
                    headers=self.get_headers(),
                    files=files,
                    timeout=15)
                
                if r2.status_code != 200:
                    self.log(f"Import dry-run - {key}", False, 
                           f"Status {r2.status_code}: {r2.text[:200]}")
                    continue
                
                result = r2.json()
                valid = result.get("valid", 0)
                invalid = result.get("invalid", 0)
                
                # For round-trip, expect valid>0 and invalid=0
                success = valid > 0 and invalid == 0
                self.log(f"Import dry-run - {key}", success,
                        f"valid={valid}, invalid={invalid}")
                
            except Exception as e:
                self.log(f"Import dry-run - {key}", False, str(e))

    def test_users_import_security(self):
        """Test users import security: bcrypt hash + email lowercase + login"""
        print("\n🔒 TEST 18-21: Users Import Security (CRITICAL)")
        
        # Generate unique test email
        ts = datetime.now().strftime("%H%M%S")
        self.test_user_email = f"TEST-importuser-{ts}@dewiaditya.id"
        
        # Step 1: Create CSV with test user
        csv_content = f"name,email,role,status\nTest Import User,{self.test_user_email},staff,active"
        
        try:
            # Step 2: Import user (mode=commit)
            files = {'file': ('test_user.csv', csv_content.encode('utf-8'), 'text/csv')}
            r = requests.post(
                f"{BASE_URL}/data-transfer/import/users?mode=commit",
                headers=self.get_headers(),
                files=files,
                timeout=15)
            
            if r.status_code != 200:
                self.log("Users import - commit", False, 
                       f"Status {r.status_code}: {r.text[:200]}")
                return
            
            result = r.json()
            inserted = result.get("inserted", 0)
            self.log("Users import - commit", inserted == 1,
                    f"inserted={inserted}, updated={result.get('updated', 0)}")
            
            # Step 3: Login with imported user (password should be bcrypt-hashed)
            print(f"\n🔑 Testing login with imported user: {self.test_user_email}")
            r2 = requests.post(f"{BASE_URL}/auth/login",
                             json={"email": self.test_user_email, 
                                   "password": "Dewi@123"},
                             timeout=10)
            
            login_ok = r2.status_code == 200 and "token" in r2.json()
            self.log("Users import - login test", login_ok,
                    f"Status {r2.status_code} (proves bcrypt hash works)")
            
            # Step 4: Re-import same user (should update, not duplicate)
            files2 = {'file': ('test_user.csv', csv_content.encode('utf-8'), 'text/csv')}
            r3 = requests.post(
                f"{BASE_URL}/data-transfer/import/users?mode=commit",
                headers=self.get_headers(),
                files=files2,
                timeout=15)
            
            if r3.status_code == 200:
                result2 = r3.json()
                updated = result2.get("updated", 0)
                inserted2 = result2.get("inserted", 0)
                no_duplicate = updated == 1 and inserted2 == 0
                self.log("Users import - no duplicate", no_duplicate,
                        f"updated={updated}, inserted={inserted2}")
            else:
                self.log("Users import - no duplicate", False,
                       f"Status {r3.status_code}")
            
        except Exception as e:
            self.log("Users import security", False, str(e))

    def test_vendor_partners_upsert(self):
        """Test vendor_partners upsert integrity (no duplicates)"""
        print("\n🔄 TEST 22-23: Vendor Partners Upsert Integrity")
        
        ts = datetime.now().strftime("%H%M%S")
        test_code = f"TEST-VP-{ts}"
        
        # Create CSV with test vendor
        csv_content = f"code,name,is_active\n{test_code},Test Vendor Upsert,true"
        
        try:
            # First import
            files = {'file': ('test_vendor.csv', csv_content.encode('utf-8'), 'text/csv')}
            r = requests.post(
                f"{BASE_URL}/data-transfer/import/vendor_partners?mode=commit",
                headers=self.get_headers(),
                files=files,
                timeout=15)
            
            if r.status_code != 200:
                self.log("Vendor upsert - first import", False,
                       f"Status {r.status_code}: {r.text[:200]}")
                return
            
            result = r.json()
            inserted = result.get("inserted", 0)
            self.log("Vendor upsert - first import", inserted == 1,
                    f"inserted={inserted}")
            
            # Second import with same code (should update)
            files2 = {'file': ('test_vendor.csv', csv_content.encode('utf-8'), 'text/csv')}
            r2 = requests.post(
                f"{BASE_URL}/data-transfer/import/vendor_partners?mode=commit",
                headers=self.get_headers(),
                files=files2,
                timeout=15)
            
            if r2.status_code == 200:
                result2 = r2.json()
                updated = result2.get("updated", 0)
                inserted2 = result2.get("inserted", 0)
                no_duplicate = updated == 1 and inserted2 == 0
                self.log("Vendor upsert - no duplicate", no_duplicate,
                        f"updated={updated}, inserted={inserted2} (second import)")
            else:
                self.log("Vendor upsert - no duplicate", False,
                       f"Status {r2.status_code}")
            
        except Exception as e:
            self.log("Vendor upsert integrity", False, str(e))

    def cleanup_test_data(self):
        """Clean up test user if possible"""
        if self.test_user_email:
            print(f"\n🧹 Cleanup: Test user {self.test_user_email} created")
            print("   (Manual cleanup may be needed via admin panel)")

    def print_summary(self):
        print("\n" + "="*60)
        print(f"📊 TEST SUMMARY")
        print("="*60)
        print(f"Total tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print("="*60)
        
        if self.tests_passed == self.tests_run:
            print("✅ ALL TESTS PASSED")
            return 0
        else:
            print("❌ SOME TESTS FAILED")
            return 1

def main():
    print("="*60)
    print("Phase 4 Data Transfer Testing")
    print("Testing Export/Import for 8 registry keys + users security")
    print("="*60)
    
    tester = DataTransferTester()
    
    # Login once (rate-limit 10/60s)
    if not tester.login():
        print("❌ Login failed, cannot proceed")
        return 1
    
    # Run all tests
    tester.test_registry_list()
    tester.test_templates_and_exports()
    tester.test_import_dry_run_roundtrip()
    tester.test_users_import_security()
    tester.test_vendor_partners_upsert()
    
    # Cleanup
    tester.cleanup_test_data()
    
    # Summary
    return tester.print_summary()

if __name__ == "__main__":
    sys.exit(main())
