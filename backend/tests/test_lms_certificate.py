"""
LMS Certificate PDF - Backend API tests
Testing GET /api/portal/training/{enrollment_id}/certificate
Session 6: Verifikasi LMS Certificate PDF implementation
"""
import pytest
import requests
import os
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://da37-cmt-bridge.preview.emergentagent.com').rstrip('/')

# Test data storage
test_data = {
    "token": None,
    "employee_id": None,
    "course_id": None,
    "enrollment_id": None,
}


@pytest.fixture(scope="module")
def auth_headers():
    """Login and get auth token"""
    print(f"\n🔐 Logging in to {BASE_URL}/api/auth/login")
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123"
    })
    assert resp.status_code == 200, f"❌ Login failed: {resp.text}"
    data = resp.json()
    token = data.get("token") or data.get("access_token")
    assert token, "❌ No token returned from login"
    test_data["token"] = token
    print("✅ Login successful, token received")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


class TestHealthCheck:
    """Test 1: Health check"""
    def test_health(self):
        print(f"\n🏥 Testing health endpoint: {BASE_URL}/api/health")
        r = requests.get(f"{BASE_URL}/api/health")
        assert r.status_code == 200, f"❌ Health check failed: {r.text}"
        data = r.json()
        assert data.get("status") == "ok", f"❌ Health status not ok: {data}"
        assert data.get("db") == "connected", f"❌ DB not connected: {data}"
        print(f"✅ Health check passed: {data}")


class TestLogin:
    """Test 2: Login with admin credentials"""
    def test_login(self, auth_headers):
        print("\n🔑 Testing login with admin@garment.com")
        assert test_data["token"] is not None
        print(f"✅ Login test passed, token: {test_data['token'][:20]}...")


class TestProfileAndEmployeeLink:
    """Test 3: Check profile and employee link"""
    def test_get_profile(self, auth_headers):
        print("\n👤 Testing GET /api/portal/profile")
        r = requests.get(f"{BASE_URL}/api/portal/profile", headers=auth_headers)
        assert r.status_code == 200, f"❌ Profile fetch failed: {r.text}"
        data = r.json()
        print(f"✅ Profile data: email={data.get('email')}, is_linked={data.get('is_linked')}, employee_id={data.get('employee_id')}")
        
        # Store employee_id if linked
        if data.get("is_linked") and data.get("employee_id"):
            test_data["employee_id"] = data.get("employee_id")
            print(f"✅ User is linked to employee: {test_data['employee_id']}")
        else:
            print("⚠️  User is NOT linked to employee - will need to create/link employee")


class TestCreateEmployeeIfNeeded:
    """Test 4: Create employee and link if not already linked"""
    def test_ensure_employee_link(self, auth_headers):
        if test_data["employee_id"]:
            print(f"\n✅ Employee already linked: {test_data['employee_id']}")
            return
        
        print("\n👷 Creating test employee for admin user")
        
        # First, get current user info
        r = requests.get(f"{BASE_URL}/api/portal/profile", headers=auth_headers)
        user_data = r.json()
        user_id = user_data.get("user_id")
        
        # Create employee via rahaza endpoint
        emp_payload = {
            "name": "Admin Test Employee",
            "employee_code": f"EMP-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "email": "admin@garment.com",
            "job_title": "Administrator",
            "department": "IT",
            "status": "aktif",
            "hire_date": "2024-01-01",
        }
        
        print(f"📝 Creating employee: {emp_payload['employee_code']}")
        r = requests.post(f"{BASE_URL}/api/rahaza/employees", headers=auth_headers, json=emp_payload)
        
        if r.status_code == 200:
            emp_data = r.json()
            emp_id = emp_data.get("id") or emp_data.get("employee_id")
            print(f"✅ Employee created: {emp_id}")
            test_data["employee_id"] = emp_id
            
            # Link user to employee via rahaza self admin endpoint
            print(f"🔗 Linking user {user_id} to employee {emp_id}")
            link_r = requests.put(f"{BASE_URL}/api/rahaza/self/admin/link-employee", 
                                 headers=auth_headers, 
                                 json={"user_id": user_id, "employee_id": emp_id})
            if link_r.status_code == 200:
                print("✅ User linked to employee successfully")
            else:
                print(f"⚠️  User link failed: {link_r.status_code} - {link_r.text}")
        else:
            # Try to find existing employee
            print(f"⚠️  Employee creation returned {r.status_code}, trying to find existing employee")
            r = requests.get(f"{BASE_URL}/api/rahaza/employees", headers=auth_headers, params={"q": "admin"})
            if r.status_code == 200:
                emps = r.json().get("employees", [])
                if emps:
                    test_data["employee_id"] = emps[0].get("id") or emps[0].get("employee_id")
                    print(f"✅ Found existing employee: {test_data['employee_id']}")


class TestTrainingEndpoint:
    """Test 5: Test GET /api/portal/training"""
    def test_get_training_list(self, auth_headers):
        print("\n📚 Testing GET /api/portal/training")
        r = requests.get(f"{BASE_URL}/api/portal/training", headers=auth_headers)
        
        if r.status_code == 409:
            print("⚠️  Training endpoint returns 409 (user not linked to employee)")
            print(f"   Response: {r.json()}")
            # This is expected if user is not linked
            assert test_data["employee_id"] is None, "User should not be linked"
        elif r.status_code == 200:
            data = r.json()
            print(f"✅ Training list retrieved: {data.get('total', 0)} enrollments")
            print(f"   Employee: {data.get('employee')}")
            print(f"   Items: {len(data.get('items', []))}")
        else:
            pytest.fail(f"❌ Unexpected status code: {r.status_code} - {r.text}")


class TestCreateCourse:
    """Test 6: Create a test course"""
    def test_create_course(self, auth_headers):
        print("\n📖 Creating test course via POST /api/dewi/lms/courses")
        
        course_payload = {
            "title": f"Test Course - Certificate Verification {datetime.now().strftime('%Y%m%d%H%M%S')}",
            "description": "Test course for certificate PDF generation testing",
            "category": "Testing",
            "level": "Beginner",
            "instructor": "Test Instructor",
            "duration_hours": 2,
            "status": "active",
            "pass_score": 70,
            "certificate_template": "standard"
        }
        
        r = requests.post(f"{BASE_URL}/api/dewi/lms/courses", headers=auth_headers, json=course_payload)
        assert r.status_code == 200, f"❌ Course creation failed: {r.status_code} - {r.text}"
        
        data = r.json()
        course = data.get("course", {})
        test_data["course_id"] = course.get("course_id")
        
        print("✅ Course created successfully")
        print(f"   Course ID: {test_data['course_id']}")
        print(f"   Title: {course.get('title')}")


class TestCreateEnrollment:
    """Test 7: Create enrollment for the test employee"""
    def test_create_enrollment(self, auth_headers):
        if not test_data["employee_id"]:
            pytest.skip("⚠️  No employee_id available - skipping enrollment creation")
        
        if not test_data["course_id"]:
            pytest.skip("⚠️  No course_id available - skipping enrollment creation")
        
        print(f"\n📝 Creating enrollment via POST /api/dewi/lms/courses/{test_data['course_id']}/enroll")
        
        enroll_payload = {
            "employee_ids": [test_data["employee_id"]]
        }
        
        r = requests.post(
            f"{BASE_URL}/api/dewi/lms/courses/{test_data['course_id']}/enroll",
            headers=auth_headers,
            json=enroll_payload
        )
        assert r.status_code == 200, f"❌ Enrollment creation failed: {r.status_code} - {r.text}"
        
        data = r.json()
        print(f"✅ Enrollment created: {data.get('enrolled_count')} employee(s) enrolled")
        
        # Get enrollment ID by listing enrollments
        r = requests.get(
            f"{BASE_URL}/api/dewi/lms/enrollments",
            headers=auth_headers,
            params={"employee_id": test_data["employee_id"], "course_id": test_data["course_id"]}
        )
        assert r.status_code == 200, f"❌ Failed to fetch enrollments: {r.text}"
        
        enrollments = r.json().get("enrollments", [])
        if enrollments:
            test_data["enrollment_id"] = enrollments[0].get("enrollment_id")
            print(f"✅ Enrollment ID: {test_data['enrollment_id']}")
            print(f"   Status: {enrollments[0].get('status')}")
            print(f"   Progress: {enrollments[0].get('progress_pct')}%")


class TestCompleteEnrollment:
    """Test 8: Mark enrollment as completed"""
    def test_complete_enrollment(self, auth_headers):
        if not test_data["enrollment_id"]:
            pytest.skip("⚠️  No enrollment_id available - skipping completion")
        
        print(f"\n✅ Marking enrollment as completed via PUT /api/dewi/lms/enrollments/{test_data['enrollment_id']}/progress")
        
        complete_payload = {
            "status": "completed",
            "progress_pct": 100,
            "quiz_score": 85
        }
        
        r = requests.put(
            f"{BASE_URL}/api/dewi/lms/enrollments/{test_data['enrollment_id']}/progress",
            headers=auth_headers,
            json=complete_payload
        )
        assert r.status_code == 200, f"❌ Enrollment completion failed: {r.status_code} - {r.text}"
        
        data = r.json()
        enrollment = data.get("enrollment", {})
        print("✅ Enrollment marked as completed")
        print(f"   Status: {enrollment.get('status')}")
        print(f"   Progress: {enrollment.get('progress_pct')}%")
        print(f"   Passed: {enrollment.get('passed')}")
        print(f"   Certificate Issued: {enrollment.get('certificate_issued')}")
        print(f"   Certificate No: {enrollment.get('certificate_no')}")
        
        assert enrollment.get("status") == "completed", "❌ Status should be completed"
        assert enrollment.get("passed") is True, "❌ Should be marked as passed"
        assert enrollment.get("certificate_issued") is True, "❌ Certificate should be issued"


class TestCertificateDownload:
    """Test 9: Download certificate PDF"""
    def test_download_certificate(self, auth_headers):
        if not test_data["enrollment_id"]:
            pytest.skip("⚠️  No enrollment_id available - skipping certificate download")
        
        print(f"\n🎓 Testing certificate download: GET /api/portal/training/{test_data['enrollment_id']}/certificate")
        
        r = requests.get(
            f"{BASE_URL}/api/portal/training/{test_data['enrollment_id']}/certificate",
            headers=auth_headers
        )
        
        print(f"   Response status: {r.status_code}")
        print(f"   Content-Type: {r.headers.get('Content-Type')}")
        print(f"   Content-Length: {len(r.content)} bytes")
        
        assert r.status_code == 200, f"❌ Certificate download failed: {r.status_code} - {r.text}"
        assert r.headers.get("Content-Type") == "application/pdf", f"❌ Wrong content type: {r.headers.get('Content-Type')}"
        assert len(r.content) > 1000, f"❌ PDF too small: {len(r.content)} bytes"
        
        # Check PDF magic bytes
        assert r.content[:4] == b'%PDF', "❌ Not a valid PDF file"
        
        print("✅ Certificate PDF downloaded successfully")
        print(f"   Size: {len(r.content)} bytes")
        print(f"   Valid PDF: {r.content[:8]}")
        
        # Save for inspection
        with open("/tmp/test_certificate.pdf", "wb") as f:
            f.write(r.content)
        print("   Saved to: /tmp/test_certificate.pdf")


class TestCertificateValidation:
    """Test 10: Validate certificate endpoint error cases"""
    def test_certificate_not_completed(self, auth_headers):
        """Test that certificate fails for non-completed enrollment"""
        if not test_data["course_id"] or not test_data["employee_id"]:
            pytest.skip("⚠️  Missing test data - skipping validation test")
        
        print("\n🔍 Testing certificate validation: non-completed enrollment should fail")
        
        # Create another enrollment but don't complete it
        enroll_payload = {"employee_ids": [test_data["employee_id"]]}
        r = requests.post(
            f"{BASE_URL}/api/dewi/lms/courses/{test_data['course_id']}/enroll",
            headers=auth_headers,
            json=enroll_payload
        )
        
        if r.status_code == 200:
            # Get the new enrollment
            r = requests.get(
                f"{BASE_URL}/api/dewi/lms/enrollments",
                headers=auth_headers,
                params={"employee_id": test_data["employee_id"], "course_id": test_data["course_id"]}
            )
            enrollments = r.json().get("enrollments", [])
            incomplete_enrollment = None
            for e in enrollments:
                if e.get("status") != "completed":
                    incomplete_enrollment = e.get("enrollment_id")
                    break
            
            if incomplete_enrollment:
                print(f"   Testing with incomplete enrollment: {incomplete_enrollment}")
                r = requests.get(
                    f"{BASE_URL}/api/portal/training/{incomplete_enrollment}/certificate",
                    headers=auth_headers
                )
                assert r.status_code == 400, f"❌ Should return 400 for incomplete enrollment, got {r.status_code}"
                print(f"✅ Correctly rejected incomplete enrollment: {r.json().get('detail')}")
    
    def test_certificate_not_found(self, auth_headers):
        """Test that certificate fails for non-existent enrollment"""
        print("\n🔍 Testing certificate validation: non-existent enrollment should fail")
        
        fake_id = "nonexistent-enrollment-id-12345"
        r = requests.get(
            f"{BASE_URL}/api/portal/training/{fake_id}/certificate",
            headers=auth_headers
        )
        assert r.status_code == 404, f"❌ Should return 404 for non-existent enrollment, got {r.status_code}"
        print(f"✅ Correctly returned 404 for non-existent enrollment: {r.json().get('detail')}")


if __name__ == "__main__":
    print("=" * 80)
    print("LMS CERTIFICATE PDF - BACKEND TEST SUITE")
    print("=" * 80)
    pytest.main([__file__, "-v", "-s"])
