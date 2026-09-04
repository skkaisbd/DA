#!/usr/bin/env python3
"""
Comprehensive Backend API Test for LiveHost & Creator Self-Report (Phase 6)
Tests all endpoints using PUBLIC endpoint from frontend/.env
"""
import requests
import sys
import uuid
from datetime import datetime, timezone

# Configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Test data
TEST_SUFFIX = uuid.uuid4().hex[:6]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def check(self, condition, test_name, details=""):
        if condition:
            self.passed += 1
            print(f"  ✅ {test_name}")
            self.tests.append({"name": test_name, "status": "PASS", "details": details})
        else:
            self.failed += 1
            print(f"  ❌ {test_name} {details}")
            self.tests.append({"name": test_name, "status": "FAIL", "details": details})
    
    def summary(self):
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        return f"{self.passed}/{total} passed ({pct:.1f}%)"

results = TestResults()

# Test state
test_data = {
    "admin_token": None,
    "host_id": None,
    "host_email": f"test_host_{TEST_SUFFIX}@test.local",
    "host_token": None,
    "shift_id": None,
    "account_id": None,
    "creator_id": None,
    "creator_email": f"test_creator_{TEST_SUFFIX}@test.local",
    "creator_token": None,
}

def setup_test_account():
    """Create a test platform account"""
    print("\n=== SETUP: Creating Test Platform Account ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    # Try to find existing active account first
    r = requests.get(f"{BASE_URL}/marketing/platform-accounts", headers=headers, timeout=15)
    if r.status_code == 200:
        accounts = r.json()
        active_accounts = [a for a in accounts if a.get('status') == 'active']
        if active_accounts:
            test_data['account_id'] = active_accounts[0]['id']
            print(f"  ✅ Using existing account: {test_data['account_id']}")
            return
    
    # Create new account if none found
    account_data = {
        "account_code": f"TEST-{TEST_SUFFIX}",
        "account_name": f"Test Account {TEST_SUFFIX}",
        "platform": "shopee",
        "status": "active",
    }
    r = requests.post(f"{BASE_URL}/marketing/platform-accounts", headers=headers, json=account_data, timeout=15)
    if r.status_code == 200:
        test_data['account_id'] = r.json()['account']['id']
        print(f"  ✅ Created test account: {test_data['account_id']}")
    else:
        print(f"  ⚠️  Could not create account, will use fallback")
        test_data['account_id'] = "15044e38-ba64-44a3-b828-8a694b7e69dc"  # Fallback from requirements

def test_admin_login():
    """Test admin authentication"""
    print("\n=== TEST 1: Admin Login ===")
    try:
        r = requests.post(f"{BASE_URL}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=15)
        
        results.check(r.status_code == 200, "Admin login returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('token' in data, "Admin login returns token")
            test_data['admin_token'] = data.get('token')
        else:
            print(f"    Response: {r.text[:200]}")
    except Exception as e:
        results.check(False, "Admin login", f"Exception: {str(e)}")

def test_create_livehost():
    """Test POST /api/marketing/livehost (Bug A fix)"""
    print("\n=== TEST 2: Create LiveHost (Bug A) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        payload = {
            "name": f"Test Host {TEST_SUFFIX}",
            "email": test_data['host_email'],
            "password": "Host@123",
            "phone": "081234567890",
            "employment_type": "part_time",
            "hourly_rate": 50000,
            "assigned_account_ids": [test_data['account_id']],
            "notes": "Test host for automated testing"
        }
        
        r = requests.post(f"{BASE_URL}/marketing/livehost", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Create LiveHost returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('host' in data, "Response contains host object")
            if 'host' in data:
                test_data['host_id'] = data['host']['id']
                results.check(data['host']['name'] == payload['name'], "Host name matches")
                results.check(data['host']['email'] == payload['email'], "Host email matches")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Create LiveHost", f"Exception: {str(e)}")

def test_create_shift():
    """Test POST /api/marketing/livehost/shifts (ShiftCreate fix)"""
    print("\n=== TEST 3: Create Shift (ShiftCreate fix) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        payload = {
            "host_id": test_data['host_id'],
            "account_id": test_data['account_id'],
            "date": TODAY,
            "shift_type": "morning",
            "shift_start_time": "09:00",
            "shift_end_time": "13:00",
            "notes": "Test shift"
        }
        
        r = requests.post(f"{BASE_URL}/marketing/livehost/shifts", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Create shift returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('shift' in data, "Response contains shift object")
            if 'shift' in data:
                test_data['shift_id'] = data['shift']['id']
                results.check(data['shift']['host_id'] == payload['host_id'], "Shift host_id matches")
                results.check(data['shift']['date'] == payload['date'], "Shift date matches")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Create shift", f"Exception: {str(e)}")

def test_host_login():
    """Test POST /api/marketing/livehost/portal/auth/login"""
    print("\n=== TEST 4: LiveHost Portal Login ===")
    
    try:
        payload = {
            "email": test_data['host_email'],
            "password": "Host@123"
        }
        
        r = requests.post(f"{BASE_URL}/marketing/livehost/portal/auth/login", json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Host login returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('token' in data, "Host login returns token")
            test_data['host_token'] = data.get('token')
            results.check('host' in data, "Host login returns host object")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Host login", f"Exception: {str(e)}")

def test_clock_in_out():
    """Test POST /api/marketing/livehost/portal/clock (ClockInOut fix)"""
    print("\n=== TEST 5: Clock In/Out (ClockInOut fix) ===")
    headers = {"Authorization": f"Bearer {test_data['host_token']}"}
    
    try:
        # Clock In
        payload = {
            "shift_id": test_data['shift_id'],
            "action": "clock_in"
        }
        
        r = requests.post(f"{BASE_URL}/marketing/livehost/portal/clock", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Clock in returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('clock_in_time' in data, "Clock in returns clock_in_time")
            results.check('attendance_status' in data, "Clock in returns attendance_status")
        else:
            print(f"    Clock in response: {r.text[:300]}")
        
        # Clock Out
        payload['action'] = "clock_out"
        r = requests.post(f"{BASE_URL}/marketing/livehost/portal/clock", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Clock out returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('clock_out_time' in data, "Clock out returns clock_out_time")
            results.check('actual_duration_minutes' in data, "Clock out returns duration")
        else:
            print(f"    Clock out response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Clock in/out", f"Exception: {str(e)}")

def test_shift_performance():
    """Test POST /api/marketing/livehost/shifts/{shift_id}/performance (ShiftPerformanceRecord fix)"""
    print("\n=== TEST 6: Record Shift Performance (ShiftPerformanceRecord fix) ===")
    headers = {"Authorization": f"Bearer {test_data['host_token']}"}
    
    try:
        payload = {
            "shift_id": test_data['shift_id'],
            "platform": "shopee",
            "viewers": 1500,
            "peak_viewers": 350,
            "revenue": 6000000,
            "orders": 50,
            "items_promoted": ["Kaos Premium", "Celana Jeans"],
            "challenges_faced": "Koneksi sempat drop 2x",
            "notes": "Sesi berjalan lancar overall"
        }
        
        r = requests.post(
            f"{BASE_URL}/marketing/livehost/shifts/{test_data['shift_id']}/performance",
            headers=headers,
            json=payload,
            timeout=15
        )
        
        results.check(r.status_code == 200, "Record performance returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('message' in data, "Performance record returns success message")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Record shift performance", f"Exception: {str(e)}")

def test_sales_sync_after_host():
    """Test that marketing_sales_data is created with revenue_type='live' after host performance"""
    print("\n=== TEST 7: Sales Sync After Host Performance ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Get marketing dashboard to check total_revenue_live
        r = requests.get(f"{BASE_URL}/marketing/dashboard/overview", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Marketing dashboard accessible", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('summary' in data and 'total_revenue_live' in data.get('summary', {}), "Dashboard includes total_revenue_live")
            if 'summary' in data and 'total_revenue_live' in data['summary']:
                print(f"    Total live revenue: Rp {data['summary']['total_revenue_live']:,.0f}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Sales sync verification", f"Exception: {str(e)}")

def test_create_creator():
    """Test creating a creator for portal testing"""
    print("\n=== TEST 8: Create Creator ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        payload = {
            "name": f"Test Creator {TEST_SUFFIX}",
            "creator_code": f"KOL-TEST-{TEST_SUFFIX}",
            "login_email": test_data['creator_email'],
            "login_password": "Creator@123",
            "assigned_account_ids": [test_data['account_id']],
            "kpi_targets": {
                "monthly_revenue": 10000000,
                "monthly_sessions": 20,
                "monthly_viewers": 50000
            }
        }
        
        r = requests.post(f"{BASE_URL}/marketing/kol/creators", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Create creator returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('creator' in data, "Response contains creator object")
            if 'creator' in data:
                test_data['creator_id'] = data['creator']['id']
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Create creator", f"Exception: {str(e)}")

def test_creator_login():
    """Test POST /api/marketing/creator-portal/auth/login"""
    print("\n=== TEST 9: Creator Portal Login ===")
    
    try:
        payload = {
            "email": test_data['creator_email'],
            "password": "Creator@123"
        }
        
        r = requests.post(f"{BASE_URL}/marketing/creator-portal/auth/login", json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Creator login returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('token' in data, "Creator login returns token")
            test_data['creator_token'] = data.get('token')
            results.check('creator_id' in data, "Creator login returns creator_id")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Creator login", f"Exception: {str(e)}")

def test_creator_my_accounts():
    """Test GET /api/marketing/creator-portal/my-accounts"""
    print("\n=== TEST 10: Creator My Accounts ===")
    headers = {"Authorization": f"Bearer {test_data['creator_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/marketing/creator-portal/my-accounts", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get my accounts returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(isinstance(data, list), "My accounts returns array")
            results.check(len(data) > 0, "Creator has assigned accounts")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Creator my accounts", f"Exception: {str(e)}")

def test_creator_session():
    """Test POST /api/marketing/creator-portal/sessions (creator self-report)"""
    print("\n=== TEST 11: Creator Self-Report Session ===")
    headers = {"Authorization": f"Bearer {test_data['creator_token']}"}
    
    try:
        payload = {
            "account_id": test_data['account_id'],
            "date": TODAY,
            "platform": "shopee",
            "session_name": "Live Sore Test",
            "viewers": 900,
            "peak_viewers": 180,
            "revenue": 3500000,
            "orders": 30,
            "items_promoted": ["Jaket Hoodie", "Sweater"],
            "notes": "Test creator session"
        }
        
        r = requests.post(f"{BASE_URL}/marketing/creator-portal/sessions", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 200, "Create session returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('session' in data, "Response contains session object")
            if 'session' in data:
                results.check(data['session']['revenue'] == payload['revenue'], "Session revenue matches")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Creator session", f"Exception: {str(e)}")

def test_creator_my_sessions():
    """Test GET /api/marketing/creator-portal/my-sessions"""
    print("\n=== TEST 12: Creator My Sessions ===")
    headers = {"Authorization": f"Bearer {test_data['creator_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/marketing/creator-portal/my-sessions", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get my sessions returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(isinstance(data, list), "My sessions returns array")
            results.check(len(data) > 0, "Creator has sessions")
            if len(data) > 0:
                results.check(data[0].get('revenue') == 3500000, "Session revenue correct")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Creator my sessions", f"Exception: {str(e)}")

def test_creator_my_performance():
    """Test GET /api/marketing/creator-portal/my-performance"""
    print("\n=== TEST 13: Creator My Performance ===")
    headers = {"Authorization": f"Bearer {test_data['creator_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/marketing/creator-portal/my-performance", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get my performance returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('summary' in data, "Performance includes summary")
            if 'summary' in data:
                results.check(data['summary']['total_revenue'] == 3500000, "Performance total_revenue correct")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Creator my performance", f"Exception: {str(e)}")

def test_aggregated_sales_sync():
    """Test that sales are aggregated from both host and creator"""
    print("\n=== TEST 14: Aggregated Sales Sync (Host + Creator) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Expected: host revenue (6,000,000) + creator revenue (3,500,000) = 9,500,000
        r = requests.get(f"{BASE_URL}/marketing/dashboard/overview", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Dashboard accessible for aggregation check", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            if 'summary' in data and 'total_revenue_live' in data['summary']:
                # Note: Dashboard shows ALL live revenue, not just our test data
                # So we just verify it's present and non-zero
                results.check(data['summary']['total_revenue_live'] > 0, "Total live revenue is aggregated")
                print(f"    Total live revenue (all accounts): Rp {data['summary']['total_revenue_live']:,.0f}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Aggregated sales sync", f"Exception: {str(e)}")

def cleanup():
    """Clean up test data"""
    print("\n=== CLEANUP: Removing Test Data ===")
    if not test_data['admin_token']:
        print("  ⚠️  No admin token, skipping cleanup")
        return
    
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    # Delete shift
    if test_data['shift_id']:
        try:
            r = requests.delete(f"{BASE_URL}/marketing/livehost/shifts/{test_data['shift_id']}", headers=headers, timeout=10)
            print(f"  {'✅' if r.status_code in [200, 404] else '⚠️'} Deleted shift")
        except Exception:
            pass
    
    # Delete host
    if test_data['host_id']:
        try:
            r = requests.delete(f"{BASE_URL}/marketing/livehost/{test_data['host_id']}", headers=headers, timeout=10)
            print(f"  {'✅' if r.status_code in [200, 404] else '⚠️'} Deleted host")
        except Exception:
            pass
    
    # Delete creator
    if test_data['creator_id']:
        try:
            r = requests.delete(f"{BASE_URL}/marketing/kol/creators/{test_data['creator_id']}", headers=headers, timeout=10)
            print(f"  {'✅' if r.status_code in [200, 404] else '⚠️'} Deleted creator")
        except Exception:
            pass

def main():
    print("=" * 80)
    print("BACKEND API TEST - LiveHost & Creator Self-Report")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Suffix: {TEST_SUFFIX}")
    print(f"Test Date: {TODAY}")
    
    try:
        # Run tests in sequence
        test_admin_login()
        
        if not test_data['admin_token']:
            print("\n❌ CRITICAL: Admin login failed, cannot continue")
            return 1
        
        setup_test_account()
        
        if not test_data['account_id']:
            print("\n❌ CRITICAL: No account available, cannot continue")
            return 1
        
        test_create_livehost()
        test_create_shift()
        test_host_login()
        test_clock_in_out()
        test_shift_performance()
        test_sales_sync_after_host()
        
        test_create_creator()
        test_creator_login()
        test_creator_my_accounts()
        test_creator_session()
        test_creator_my_sessions()
        test_creator_my_performance()
        test_aggregated_sales_sync()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        cleanup()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Results: {results.summary()}")
    print(f"Passed: {results.passed}")
    print(f"Failed: {results.failed}")
    
    if results.failed > 0:
        print("\n❌ FAILED TESTS:")
        for test in results.tests:
            if test['status'] == 'FAIL':
                print(f"  - {test['name']}: {test['details']}")
    
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
