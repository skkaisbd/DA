"""
Backend Test — HR Approval Inbox (Phase 26)
Tests all endpoints for the unified HR approval inbox aggregator.
"""
import requests
import sys
from datetime import datetime, timedelta
import os

# Get backend URL from env
BACKEND_URL = os.getenv('REACT_APP_BACKEND_URL', 'https://da37-cmt-bridge.preview.emergentagent.com')
API_BASE = f"{BACKEND_URL}/api"

class HRInboxTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_leave_id = None
        self.test_overtime_id = None
        self.employee_id = "b2473b34-16ba-4bfa-8c34-edaa7da76d42"  # Budi Santoso
        self.leave_type_id = "214d14f3-d7af-409b-9859-dd17caf652b7"  # Annual Leave

    def log(self, msg):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

    def test(self, name, method, endpoint, expected_status, data=None, headers=None):
        """Run a single test"""
        url = f"{API_BASE}/{endpoint}"
        self.tests_run += 1
        self.log(f"🔍 Test #{self.tests_run}: {name}")
        
        try:
            h = headers or {}
            if self.token and 'Authorization' not in h:
                h['Authorization'] = f'Bearer {self.token}'
            h['Content-Type'] = 'application/json'

            if method == 'GET':
                r = requests.get(url, headers=h, timeout=10)
            elif method == 'POST':
                r = requests.post(url, json=data, headers=h, timeout=10)
            elif method == 'PUT':
                r = requests.put(url, json=data, headers=h, timeout=10)
            elif method == 'DELETE':
                r = requests.delete(url, headers=h, timeout=10)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = r.status_code == expected_status
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS — Status {r.status_code}")
                try:
                    return True, r.json()
                except Exception:
                    return True, {}
            else:
                self.log(f"❌ FAIL — Expected {expected_status}, got {r.status_code}")
                try:
                    err = r.json()
                    self.log(f"   Response: {err}")
                except Exception:
                    self.log(f"   Response: {r.text[:200]}")
                return False, {}

        except Exception as e:
            self.log(f"❌ FAIL — Exception: {str(e)}")
            return False, {}

    def run_all_tests(self):
        self.log("=" * 70)
        self.log("HR APPROVAL INBOX — Backend Test Suite (Phase 26)")
        self.log("=" * 70)

        # 1. Login
        self.log("\n📌 Step 1: Authentication")
        success, resp = self.test(
            "Login as admin",
            "POST",
            "auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"}
        )
        if not success or 'token' not in resp:
            self.log("❌ Login failed — cannot proceed")
            return False
        self.token = resp['token']
        self.log(f"✓ Token obtained: {self.token[:20]}...")

        # 2. GET /api/hr/inbox/summary (with auth)
        self.log("\n📌 Step 2: Inbox Summary")
        success, summary = self.test(
            "GET /api/hr/inbox/summary",
            "GET",
            "hr/inbox/summary",
            200
        )
        if success:
            self.log(f"   Summary: {summary}")
            self.log(f"   Total pending: {summary.get('total_pending', 0)}")
            self.log(f"   Leave: {summary.get('leave', 0)}, Overtime: {summary.get('overtime', 0)}")
            self.log(f"   Salary Adj: {summary.get('salary_adjustment', 0)}, Resignation: {summary.get('resignation', 0)}")

        # 3. GET /api/hr/inbox (all items)
        self.log("\n📌 Step 3: List All Inbox Items")
        success, inbox = self.test(
            "GET /api/hr/inbox",
            "GET",
            "hr/inbox",
            200
        )
        if success:
            self.log(f"   Total items: {inbox.get('total', 0)}")
            self.log(f"   Counts: {inbox.get('counts', {})}")
            items = inbox.get('items', [])
            if items:
                self.log(f"   First item: {items[0].get('type')} — {items[0].get('title')}")

        # 4. GET /api/hr/inbox?type=leave (filtered)
        self.log("\n📌 Step 4: Filter by Type (Leave)")
        success, filtered = self.test(
            "GET /api/hr/inbox?type=leave",
            "GET",
            "hr/inbox?type=leave",
            200
        )
        if success:
            self.log(f"   Leave items: {filtered.get('counts', {}).get('leave', 0)}")

        # 5. GET /api/hr/inbox?type=overtime (filtered)
        self.log("\n📌 Step 5: Filter by Type (Overtime)")
        success, filtered = self.test(
            "GET /api/hr/inbox?type=overtime",
            "GET",
            "hr/inbox?type=overtime",
            200
        )
        if success:
            self.log(f"   Overtime items: {filtered.get('counts', {}).get('overtime', 0)}")

        # 6. GET /api/hr/inbox?type=invalid (should 400)
        self.log("\n📌 Step 6: Invalid Type Filter (should 400)")
        self.test(
            "GET /api/hr/inbox?type=invalid",
            "GET",
            "hr/inbox?type=invalid",
            400
        )

        # 7. GET /api/hr/inbox without auth (should 401/403)
        self.log("\n📌 Step 7: No Auth (should 401/403)")
        # Note: This test expects 401, but if it returns 200, it's a CRITICAL security bug
        success, _ = self.test(
            "GET /api/hr/inbox (no auth)",
            "GET",
            "hr/inbox",
            401,
            headers={}
        )
        if not success:
            self.log("⚠️  CRITICAL SECURITY BUG: Endpoint accessible without auth!")

        # 8. Create fresh leave request
        self.log("\n📌 Step 8: Create Fresh Leave Request")
        from_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')
        to_date = (datetime.now() + timedelta(days=32)).strftime('%Y-%m-%d')
        # Note: endpoint returns 200, not 201
        url = f"{API_BASE}/rahaza/leaves/request"
        try:
            r = requests.post(url, json={
                "employee_id": self.employee_id,
                "leave_type_id": self.leave_type_id,
                "from_date": from_date,
                "to_date": to_date,
                "reason": "Test leave for HR inbox approval",
                "request_type": "full_day"
            }, headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}, timeout=10)
            self.tests_run += 1
            if r.status_code in (200, 201):
                leave_resp = r.json()
                if 'id' in leave_resp:
                    self.test_leave_id = leave_resp['id']
                    self.tests_passed += 1
                    self.log(f"✅ PASS — Leave request created: {self.test_leave_id}")
                else:
                    self.log("❌ FAIL — No ID in response")
            else:
                self.log(f"❌ FAIL — Status {r.status_code}")
        except Exception as e:
            self.tests_run += 1
            self.log(f"❌ FAIL — Exception: {e}")

        # 9. Approve leave via HR inbox
        if self.test_leave_id:
            self.log("\n📌 Step 9: Approve Leave via HR Inbox")
            success, approve_resp = self.test(
                f"POST /api/hr/inbox/leave/{self.test_leave_id}/approve",
                "POST",
                f"hr/inbox/leave/{self.test_leave_id}/approve",
                200,
                data={"note": "Approved via HR inbox test"}
            )
            if success:
                self.log(f"   New status: {approve_resp.get('new_status')}")

            # 10. Try to approve again (should 400)
            self.log("\n📌 Step 10: Approve Already-Approved (should 400)")
            self.test(
                f"POST /api/hr/inbox/leave/{self.test_leave_id}/approve (again)",
                "POST",
                f"hr/inbox/leave/{self.test_leave_id}/approve",
                400,
                data={"note": "Second approval"}
            )

        # 11. Create fresh overtime request
        self.log("\n📌 Step 11: Create Fresh Overtime Request")
        ot_date = (datetime.now() + timedelta(days=5)).strftime('%Y-%m-%d')
        # Note: endpoint returns 200, not 201
        url = f"{API_BASE}/rahaza/overtime"
        try:
            r = requests.post(url, json={
                "employee_id": self.employee_id,
                "date": ot_date,
                "start_time": "18:00",
                "end_time": "22:00",
                "hours": 4.0,
                "reason": "Test overtime for HR inbox approval"
            }, headers={'Authorization': f'Bearer {self.token}', 'Content-Type': 'application/json'}, timeout=10)
            self.tests_run += 1
            if r.status_code in (200, 201):
                ot_resp = r.json()
                # Response has nested structure: {ok: true, overtime: {...}}
                if 'overtime' in ot_resp and 'id' in ot_resp['overtime']:
                    self.test_overtime_id = ot_resp['overtime']['id']
                    self.tests_passed += 1
                    self.log(f"✅ PASS — Overtime request created: {self.test_overtime_id}")
                elif 'id' in ot_resp:
                    self.test_overtime_id = ot_resp['id']
                    self.tests_passed += 1
                    self.log(f"✅ PASS — Overtime request created: {self.test_overtime_id}")
                else:
                    self.log("❌ FAIL — No ID in response")
            else:
                self.log(f"❌ FAIL — Status {r.status_code}")
        except Exception as e:
            self.tests_run += 1
            self.log(f"❌ FAIL — Exception: {e}")

        # 12. Reject overtime with empty reason (should 400)
        if self.test_overtime_id:
            self.log("\n📌 Step 12: Reject Overtime with Empty Reason (should 400)")
            self.test(
                f"POST /api/hr/inbox/overtime/{self.test_overtime_id}/reject (no reason)",
                "POST",
                f"hr/inbox/overtime/{self.test_overtime_id}/reject",
                400,
                data={}
            )

            # 13. Reject overtime with reason (should 200)
            self.log("\n📌 Step 13: Reject Overtime with Reason")
            success, reject_resp = self.test(
                f"POST /api/hr/inbox/overtime/{self.test_overtime_id}/reject",
                "POST",
                f"hr/inbox/overtime/{self.test_overtime_id}/reject",
                200,
                data={"reason": "Conflict with production deadline"}
            )
            if success:
                self.log(f"   New status: {reject_resp.get('new_status')}")

        # 14. Approve non-existent (should 404)
        self.log("\n📌 Step 14: Approve Non-Existent Leave (should 404)")
        self.test(
            "POST /api/hr/inbox/leave/fake-id-12345/approve",
            "POST",
            "hr/inbox/leave/fake-id-12345/approve",
            404,
            data={"note": "Test"}
        )

        # 15. Regression: Verify existing per-module endpoints still work
        self.log("\n📌 Step 15: Regression — Existing Endpoints")
        
        # 15a. GET /api/rahaza/leaves?status=pending_approval
        success, leaves = self.test(
            "GET /api/rahaza/leaves?status=pending_approval",
            "GET",
            "rahaza/leaves?status=pending_approval",
            200
        )
        if success:
            self.log(f"   Pending leaves: {len(leaves.get('items', []))}")

        # 15b. GET /api/rahaza/overtime
        success, overtime = self.test(
            "GET /api/rahaza/overtime",
            "GET",
            "rahaza/overtime",
            200
        )
        if success:
            self.log(f"   Overtime requests: {len(overtime.get('items', []))}")

        # Final summary
        self.log("\n" + "=" * 70)
        self.log("📊 BACKEND TEST RESULTS")
        self.log("=" * 70)
        self.log(f"Tests Run:    {self.tests_run}")
        self.log(f"Tests Passed: {self.tests_passed}")
        self.log(f"Tests Failed: {self.tests_run - self.tests_passed}")
        self.log(f"Success Rate: {(self.tests_passed / self.tests_run * 100):.1f}%")
        self.log("=" * 70)

        return self.tests_passed == self.tests_run


def main():
    tester = HRInboxTester()
    success = tester.run_all_tests()
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
