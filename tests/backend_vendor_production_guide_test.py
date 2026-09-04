"""
Backend API Testing for Vendor Production Guide (Panduan Produksi)
Tests vendor-facing READ-ONLY production guide feature with scoping.

Test Coverage:
1. Admin login
2. Vendor A login & my-jobs (scoped to partner A)
3. Vendor A production-guide for own job (has_model=true, 3 SOP steps)
4. Vendor A production-guide for partner B job (404 - scoping)
5. Vendor B login & my-jobs (scoped to partner B)
6. Vendor B production-guide for own job
"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"

# Test credentials
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
VENDOR_A = {"email": "cmtvendor@dewiaditya.id", "password": "Dewi@123"}
VENDOR_B = {"email": "vendorb_poc@dewiaditya.id", "password": "Dewi@123"}

class VendorProductionGuideAPITester:
    def __init__(self):
        self.base_url = BASE_URL
        self.admin_token = None
        self.vendor_a_token = None
        self.vendor_b_token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.job_a_id = None
        self.job_b_id = None

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def run_test(self, name, method, endpoint, expected_status, token=None, data=None):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['Authorization'] = f'Bearer {token}'

        self.tests_run += 1
        self.log(f"🔍 Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)

            success = response.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASSED - Status: {response.status_code}")
                try:
                    return True, response.json()
                except:
                    return True, {}
            else:
                self.log(f"❌ FAILED - Expected {expected_status}, got {response.status_code}")
                try:
                    self.log(f"   Response: {response.text[:300]}")
                except:
                    pass
                return False, {}

        except Exception as e:
            self.log(f"❌ FAILED - Error: {str(e)}")
            return False, {}

    def test_admin_login(self):
        """Test admin login"""
        self.log("\n=== ADMIN LOGIN ===")
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/auth/login",
            200,
            data=ADMIN
        )
        if success and 'token' in response:
            self.admin_token = response['token']
            self.log(f"   Token obtained: {self.admin_token[:20]}...")
            return True
        return False

    def test_vendor_a_login(self):
        """Test Vendor A login"""
        self.log("\n=== VENDOR A LOGIN ===")
        success, response = self.run_test(
            "Vendor A Login (cmtvendor@dewiaditya.id)",
            "POST",
            "/auth/login",
            200,
            data=VENDOR_A
        )
        if success and 'token' in response:
            self.vendor_a_token = response['token']
            self.log(f"   Token obtained: {self.vendor_a_token[:20]}...")
            self.log(f"   User: {response.get('user', {}).get('name')}")
            self.log(f"   Role: {response.get('user', {}).get('role')}")
            return True
        return False

    def test_vendor_b_login(self):
        """Test Vendor B login"""
        self.log("\n=== VENDOR B LOGIN ===")
        success, response = self.run_test(
            "Vendor B Login (vendorb_poc@dewiaditya.id)",
            "POST",
            "/auth/login",
            200,
            data=VENDOR_B
        )
        if success and 'token' in response:
            self.vendor_b_token = response['token']
            self.log(f"   Token obtained: {self.vendor_b_token[:20]}...")
            self.log(f"   User: {response.get('user', {}).get('name')}")
            self.log(f"   Role: {response.get('user', {}).get('role')}")
            return True
        return False

    def test_vendor_a_my_jobs(self):
        """Test Vendor A my-jobs (scoped to partner A)"""
        self.log("\n=== VENDOR A: MY JOBS (SCOPING) ===")
        success, response = self.run_test(
            "Vendor A - Get My Jobs",
            "GET",
            "/vendor-portal/my-jobs",
            200,
            token=self.vendor_a_token
        )
        if success:
            jobs = response if isinstance(response, list) else []
            self.log(f"   Found {len(jobs)} jobs for Vendor A")
            
            # Find VJ-00001 (partner A job)
            job_a = next((j for j in jobs if j.get('job_number') == 'VJ-00001'), None)
            if job_a:
                self.job_a_id = job_a['id']
                self.log(f"   ✓ Found VJ-00001 (partner A job)")
                self.log(f"     Job ID: {self.job_a_id}")
                self.log(f"     Title: {job_a.get('title')}")
                self.log(f"     Model: {job_a.get('model_code')} - {job_a.get('model_name')}")
            else:
                self.log(f"   ⚠ VJ-00001 not found in job list")
            
            # Check that VJ-00002 (partner B job) is NOT in the list
            job_b_in_list = next((j for j in jobs if j.get('job_number') == 'VJ-00002'), None)
            if job_b_in_list:
                self.log(f"   ❌ SCOPING BREACH: Vendor A can see VJ-00002 (partner B job)")
                return False
            else:
                self.log(f"   ✓ SCOPING OK: VJ-00002 (partner B) not visible to Vendor A")
            
            return True
        return False

    def test_vendor_a_production_guide_own_job(self):
        """Test Vendor A production-guide for own job (should have SOP)"""
        self.log("\n=== VENDOR A: PRODUCTION GUIDE (OWN JOB) ===")
        if not self.job_a_id:
            self.log("   ⚠ No job_a_id available, skipping")
            return False
        
        success, response = self.run_test(
            "Vendor A - Get Production Guide for VJ-00001",
            "GET",
            f"/vendor-portal/my-jobs/{self.job_a_id}/production-guide",
            200,
            token=self.vendor_a_token
        )
        if success:
            has_model = response.get('has_model', False)
            model = response.get('model', {})
            
            self.log(f"   has_model: {has_model}")
            if has_model:
                self.log(f"   Model code: {model.get('code')}")
                self.log(f"   Model name: {model.get('name')}")
                
                # Check SOP steps
                sop_steps = model.get('sop_steps', [])
                self.log(f"   SOP steps: {len(sop_steps)}")
                if len(sop_steps) == 3:
                    self.log(f"   ✓ Has 3 SOP steps as expected")
                    for i, step in enumerate(sop_steps, 1):
                        self.log(f"     {i}. {step.get('title')}")
                else:
                    self.log(f"   ⚠ Expected 3 SOP steps, got {len(sop_steps)}")
                
                # Check reference videos
                videos = model.get('reference_videos', [])
                self.log(f"   Reference videos: {len(videos)}")
                if videos:
                    self.log(f"   ✓ Has reference videos")
                
                # Check reference images
                ref_images = model.get('reference_images', [])
                self.log(f"   Reference images: {len(ref_images)}")
                if ref_images:
                    self.log(f"   ✓ Has reference images")
                
                return True
            else:
                self.log(f"   ⚠ has_model=False, no guide available")
                return False
        return False

    def test_vendor_a_production_guide_other_job(self):
        """Test Vendor A production-guide for partner B job (should be 404)"""
        self.log("\n=== VENDOR A: PRODUCTION GUIDE (OTHER VENDOR JOB - SCOPING) ===")
        
        # First, get job B ID from admin
        if self.admin_token:
            success, response = self.run_test(
                "Admin - Get All Jobs",
                "GET",
                "/vendor-portal/jobs",
                200,
                token=self.admin_token
            )
            if success:
                jobs = response if isinstance(response, list) else []
                job_b = next((j for j in jobs if j.get('job_number') == 'VJ-00002'), None)
                if job_b:
                    self.job_b_id = job_b['id']
                    self.log(f"   Found VJ-00002 (partner B job), ID: {self.job_b_id}")
        
        if not self.job_b_id:
            self.log("   ⚠ No job_b_id available, skipping scoping test")
            return False
        
        # Try to access partner B's job guide as Vendor A (should fail with 404)
        success, response = self.run_test(
            "Vendor A - Try to Get Production Guide for VJ-00002 (partner B)",
            "GET",
            f"/vendor-portal/my-jobs/{self.job_b_id}/production-guide",
            404,
            token=self.vendor_a_token
        )
        if success:
            self.log(f"   ✓ SCOPING OK: Vendor A gets 404 for partner B job")
            return True
        else:
            self.log(f"   ❌ SCOPING BREACH: Vendor A can access partner B job guide")
            return False

    def test_vendor_b_my_jobs(self):
        """Test Vendor B my-jobs (scoped to partner B)"""
        self.log("\n=== VENDOR B: MY JOBS (SCOPING) ===")
        success, response = self.run_test(
            "Vendor B - Get My Jobs",
            "GET",
            "/vendor-portal/my-jobs",
            200,
            token=self.vendor_b_token
        )
        if success:
            jobs = response if isinstance(response, list) else []
            self.log(f"   Found {len(jobs)} jobs for Vendor B")
            
            # Find VJ-00002 (partner B job)
            job_b = next((j for j in jobs if j.get('job_number') == 'VJ-00002'), None)
            if job_b:
                self.log(f"   ✓ Found VJ-00002 (partner B job)")
                self.log(f"     Job ID: {job_b['id']}")
                self.log(f"     Title: {job_b.get('title')}")
            else:
                self.log(f"   ⚠ VJ-00002 not found in job list")
            
            # Check that VJ-00001 (partner A job) is NOT in the list
            job_a_in_list = next((j for j in jobs if j.get('job_number') == 'VJ-00001'), None)
            if job_a_in_list:
                self.log(f"   ❌ SCOPING BREACH: Vendor B can see VJ-00001 (partner A job)")
                return False
            else:
                self.log(f"   ✓ SCOPING OK: VJ-00001 (partner A) not visible to Vendor B")
            
            return True
        return False

    def test_vendor_b_production_guide(self):
        """Test Vendor B production-guide for own job"""
        self.log("\n=== VENDOR B: PRODUCTION GUIDE (OWN JOB) ===")
        if not self.job_b_id:
            self.log("   ⚠ No job_b_id available, skipping")
            return False
        
        success, response = self.run_test(
            "Vendor B - Get Production Guide for VJ-00002",
            "GET",
            f"/vendor-portal/my-jobs/{self.job_b_id}/production-guide",
            200,
            token=self.vendor_b_token
        )
        if success:
            has_model = response.get('has_model', False)
            self.log(f"   has_model: {has_model}")
            if has_model:
                model = response.get('model', {})
                self.log(f"   Model code: {model.get('code')}")
                self.log(f"   ✓ Vendor B can access own job guide")
            return True
        return False

def main():
    tester = VendorProductionGuideAPITester()
    
    print("=" * 80)
    print("VENDOR PRODUCTION GUIDE (PANDUAN PRODUKSI) - BACKEND API TESTING")
    print("=" * 80)
    
    # Run tests in sequence
    if not tester.test_admin_login():
        print("\n❌ Admin login failed, stopping tests")
        return 1

    if not tester.test_vendor_a_login():
        print("\n❌ Vendor A login failed, stopping tests")
        return 1

    if not tester.test_vendor_b_login():
        print("\n❌ Vendor B login failed, stopping tests")
        return 1

    # Test Vendor A flows
    tester.test_vendor_a_my_jobs()
    tester.test_vendor_a_production_guide_own_job()
    tester.test_vendor_a_production_guide_other_job()

    # Test Vendor B flows
    tester.test_vendor_b_my_jobs()
    tester.test_vendor_b_production_guide()

    # Print results
    print("\n" + "=" * 80)
    print(f"📊 RESULTS: {tester.tests_passed}/{tester.tests_run} tests passed")
    print("=" * 80)
    
    if tester.tests_passed == tester.tests_run:
        print("✅ ALL BACKEND TESTS PASSED")
        return 0
    else:
        failed = tester.tests_run - tester.tests_passed
        print(f"⚠️  {failed} test(s) failed")
        return 1

if __name__ == "__main__":
    sys.exit(main())
