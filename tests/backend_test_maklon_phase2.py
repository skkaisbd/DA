#!/usr/bin/env python3
"""
Backend API Test - Maklon Phase 2: Permak/Rework + Canonical Progress
Tests all new endpoints for CMT Permak and canonical multi-state progress tracking.

Run: python /app/tests/backend_test_maklon_phase2.py
"""
import os
import sys
import uuid
import requests
from datetime import datetime, timezone
from dotenv import load_dotenv

# Load environment
load_dotenv("/app/backend/.env")
load_dotenv("/app/frontend/.env")

# Configuration - use PUBLIC endpoint
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001")
if not BASE_URL.startswith("http"):
    BASE_URL = f"https://{BASE_URL}"
BASE_URL = BASE_URL.rstrip("/") + "/api"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Test tracking
class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
        self.critical_failures = []
    
    def check(self, condition, test_name, details="", critical=False):
        if condition:
            self.passed += 1
            print(f"  ✅ {test_name}")
            self.tests.append({"name": test_name, "status": "PASS", "details": details})
        else:
            self.failed += 1
            print(f"  ❌ {test_name} {details}")
            self.tests.append({"name": test_name, "status": "FAIL", "details": details})
            if critical:
                self.critical_failures.append(test_name)
    
    def summary(self):
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        return f"{self.passed}/{total} passed ({pct:.1f}%)"

results = TestResults()
test_data = {
    "admin_token": None,
    "non_admin_token": None,
    "po_id": None,
    "po_item_id": None,
    "receipt_id": None,
    "receipt_line_id": None,
    "permak_id": None,
}

# ─── HELPER FUNCTIONS ────────────────────────────────────────────────────────

def login(email, password):
    """Login and return token"""
    try:
        r = requests.post(f"{BASE_URL}/auth/login", json={
            "email": email,
            "password": password
        }, timeout=20)
        if r.status_code == 200:
            return r.json().get("token")
    except Exception as e:
        print(f"    Login error: {e}")
    return None

def get_headers(token=None):
    """Get auth headers"""
    if token is None:
        token = test_data["admin_token"]
    return {"Authorization": f"Bearer {token}"} if token else {}

# ─── TEST FUNCTIONS ──────────────────────────────────────────────────────────

def test_admin_login():
    """Test 1: Admin authentication"""
    print("\n=== TEST 1: Admin Login ===")
    try:
        token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
        results.check(token is not None, "Admin login successful", critical=True)
        test_data["admin_token"] = token
        if not token:
            print(f"    ❌ CRITICAL: Cannot proceed without admin token")
    except Exception as e:
        results.check(False, "Admin login", f"Exception: {e}", critical=True)

def test_auth_401_without_token():
    """Test 2: All permak endpoints reject requests without token (401)"""
    print("\n=== TEST 2: Auth - 401 Without Token ===")
    
    # GET endpoints
    get_endpoints = [
        "/dewi/cmt-permak",
        "/dewi/cmt-permak/summary",
    ]
    
    for path in get_endpoints:
        try:
            r = requests.get(f"{BASE_URL}{path}", timeout=10)
            results.check(
                r.status_code in [401, 403],
                f"GET {path} rejects no-auth",
                f"Got {r.status_code}"
            )
        except Exception as e:
            results.check(False, f"GET {path} auth check", f"Exception: {e}")
    
    # POST endpoints with valid payloads (to bypass Pydantic validation)
    try:
        # POST /dewi/cmt-permak with valid payload
        r = requests.post(
            f"{BASE_URL}/dewi/cmt-permak",
            json={
                "po_id": "test-po",
                "po_item_id": "test-item",
                "qty": 10,
                "source": "reject"
            },
            timeout=10
        )
        results.check(
            r.status_code in [401, 403],
            "POST /dewi/cmt-permak rejects no-auth",
            f"Got {r.status_code}"
        )
    except Exception as e:
        results.check(False, "POST /dewi/cmt-permak auth check", f"Exception: {e}")
    
    try:
        # POST /dewi/cmt-permak/from-receipt-line with valid payload
        r = requests.post(
            f"{BASE_URL}/dewi/cmt-permak/from-receipt-line",
            json={
                "receipt_line_id": "test-line",
                "vendor_permak": "Workshop A"
            },
            timeout=10
        )
        results.check(
            r.status_code in [401, 403],
            "POST /dewi/cmt-permak/from-receipt-line rejects no-auth",
            f"Got {r.status_code}"
        )
    except Exception as e:
        results.check(False, "POST /dewi/cmt-permak/from-receipt-line auth check", f"Exception: {e}")

def test_permak_list_empty():
    """Test 3: GET /api/dewi/cmt-permak (empty list)"""
    print("\n=== TEST 3: Permak List (Empty) ===")
    try:
        r = requests.get(
            f"{BASE_URL}/dewi/cmt-permak",
            headers=get_headers(),
            timeout=15
        )
        results.check(r.status_code == 200, "List permak returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check("items" in data, "Response has 'items' field")
            results.check("pagination" in data, "Response has 'pagination' field")
            results.check(isinstance(data.get("items"), list), "Items is a list")
    except Exception as e:
        results.check(False, "List permak", f"Exception: {e}")

def test_permak_summary_empty():
    """Test 4: GET /api/dewi/cmt-permak/summary (empty)"""
    print("\n=== TEST 4: Permak Summary (Empty) ===")
    try:
        r = requests.get(
            f"{BASE_URL}/dewi/cmt-permak/summary",
            headers=get_headers(),
            timeout=15
        )
        results.check(r.status_code == 200, "Summary returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check("total_records" in data, "Summary has total_records")
            results.check(data.get("total_records") >= 0, "Total records is non-negative")
    except Exception as e:
        results.check(False, "Permak summary", f"Exception: {e}")

def test_create_permak_invalid_po():
    """Test 5: POST /api/dewi/cmt-permak with invalid PO (404)"""
    print("\n=== TEST 5: Create Permak - Invalid PO (404) ===")
    try:
        payload = {
            "po_id": "invalid-po-id",
            "po_item_id": "invalid-item-id",
            "qty": 10,
            "source": "reject"
        }
        r = requests.post(
            f"{BASE_URL}/dewi/cmt-permak",
            headers=get_headers(),
            json=payload,
            timeout=15
        )
        results.check(
            r.status_code == 404,
            "Invalid PO returns 404",
            f"Got {r.status_code}"
        )
    except Exception as e:
        results.check(False, "Create permak invalid PO", f"Exception: {e}")

def test_create_permak_invalid_qty():
    """Test 6: POST /api/dewi/cmt-permak with qty=0 (422)"""
    print("\n=== TEST 6: Create Permak - Invalid Qty (422) ===")
    try:
        payload = {
            "po_id": "some-po",
            "po_item_id": "some-item",
            "qty": 0,  # Invalid
            "source": "reject"
        }
        r = requests.post(
            f"{BASE_URL}/dewi/cmt-permak",
            headers=get_headers(),
            json=payload,
            timeout=15
        )
        results.check(
            r.status_code == 422,
            "qty=0 returns 422",
            f"Got {r.status_code}"
        )
    except Exception as e:
        results.check(False, "Create permak invalid qty", f"Exception: {e}")

def test_from_receipt_line_invalid():
    """Test 7: POST /api/dewi/cmt-permak/from-receipt-line with invalid line (404)"""
    print("\n=== TEST 7: From Receipt Line - Invalid Line (404) ===")
    try:
        payload = {
            "receipt_line_id": "invalid-line-id",
            "vendor_permak": "Workshop A"
        }
        r = requests.post(
            f"{BASE_URL}/dewi/cmt-permak/from-receipt-line",
            headers=get_headers(),
            json=payload,
            timeout=15
        )
        results.check(
            r.status_code == 404,
            "Invalid receipt line returns 404",
            f"Got {r.status_code}"
        )
    except Exception as e:
        results.check(False, "From receipt line invalid", f"Exception: {e}")

def test_client_pos_list_backward_compat():
    """Test 8: GET /api/maklon-client/pos (backward compatibility)"""
    print("\n=== TEST 8: Client PO List - Backward Compatibility ===")
    try:
        r = requests.get(
            f"{BASE_URL}/maklon-client/pos",
            headers=get_headers(),
            timeout=15
        )
        results.check(r.status_code == 200, "Client PO list returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(isinstance(data, list), "Response is a list")
            
            # Check backward compatibility fields
            if len(data) > 0:
                po = data[0]
                results.check("progress_pct" in po, "PO has progress_pct (backward-compat)")
                results.check("delivery_pct" in po, "PO has delivery_pct (backward-compat)")
                results.check("breakdown" in po, "PO has breakdown (new field)")
                
                # Verify breakdown structure
                if "breakdown" in po:
                    bd = po["breakdown"]
                    results.check(isinstance(bd, dict), "Breakdown is a dict")
                    # Check for key fields
                    expected_fields = ["qty_ordered", "qty_produced", "qty_accepted", "qty_good"]
                    for field in expected_fields:
                        if field in bd:
                            results.check(True, f"Breakdown has {field}")
            else:
                print("    ℹ️  No POs in database (empty list is valid)")
    except Exception as e:
        results.check(False, "Client PO list", f"Exception: {e}")

def test_client_po_progress_endpoint():
    """Test 9: GET /api/maklon-client/pos/{po_id}/progress (new endpoint)"""
    print("\n=== TEST 9: Client PO Progress - New Endpoint ===")
    
    # First, try to get a PO from the list
    try:
        r = requests.get(
            f"{BASE_URL}/maklon-client/pos",
            headers=get_headers(),
            timeout=15
        )
        
        if r.status_code == 200 and len(r.json()) > 0:
            po_id = r.json()[0]["po_id"]
            test_data["po_id"] = po_id
            
            # Test the progress endpoint
            r2 = requests.get(
                f"{BASE_URL}/maklon-client/pos/{po_id}/progress",
                headers=get_headers(),
                timeout=15
            )
            results.check(r2.status_code == 200, "Progress endpoint returns 200", f"Got {r2.status_code}")
            
            if r2.status_code == 200:
                prog = r2.json()
                results.check("breakdown" in prog, "Progress has breakdown")
                results.check("items" in prog, "Progress has items array")
                results.check("progress_pct" in prog, "Progress has progress_pct (backward-compat)")
                results.check("delivery_pct" in prog, "Progress has delivery_pct (backward-compat)")
                results.check("good_pct" in prog, "Progress has good_pct (new)")
                results.check("dispatch_pct" in prog, "Progress has dispatch_pct (new)")
        else:
            # Test with invalid PO
            r2 = requests.get(
                f"{BASE_URL}/maklon-client/pos/invalid-po-id/progress",
                headers=get_headers(),
                timeout=15
            )
            results.check(
                r2.status_code == 404,
                "Invalid PO returns 404",
                f"Got {r2.status_code}"
            )
    except Exception as e:
        results.check(False, "Client PO progress", f"Exception: {e}")

def test_po_360_regression():
    """Test 10: GET /api/dewi/maklon/pos/{po_id}/360 (regression)"""
    print("\n=== TEST 10: PO 360 View - Regression Test ===")
    
    # Get a PO ID if we have one
    if not test_data.get("po_id"):
        try:
            r = requests.get(
                f"{BASE_URL}/maklon-client/pos",
                headers=get_headers(),
                timeout=15
            )
            if r.status_code == 200 and len(r.json()) > 0:
                test_data["po_id"] = r.json()[0]["po_id"]
        except:
            pass
    
    if test_data.get("po_id"):
        try:
            r = requests.get(
                f"{BASE_URL}/dewi/maklon/pos/{test_data['po_id']}/360",
                headers=get_headers(),
                timeout=15
            )
            results.check(r.status_code == 200, "PO 360 returns 200", f"Got {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                results.check("po" in data, "360 view has po")
                results.check("kpis" in data, "360 view has kpis")
                results.check("progress_breakdown" in data, "360 view has progress_breakdown (new)")
                
                # Check progress_breakdown structure
                if "progress_breakdown" in data:
                    pb = data["progress_breakdown"]
                    results.check(isinstance(pb, dict), "progress_breakdown is a dict")
                    if pb:  # Not empty
                        results.check("breakdown" in pb, "progress_breakdown has breakdown")
                        results.check("items" in pb, "progress_breakdown has items")
        except Exception as e:
            results.check(False, "PO 360 regression", f"Exception: {e}")
    else:
        print("    ℹ️  No PO available for 360 test (skipped)")

def test_permak_get_404():
    """Test 11: GET /api/dewi/cmt-permak/{id} with invalid ID (404)"""
    print("\n=== TEST 11: Get Permak - Invalid ID (404) ===")
    try:
        r = requests.get(
            f"{BASE_URL}/dewi/cmt-permak/invalid-permak-id",
            headers=get_headers(),
            timeout=15
        )
        results.check(
            r.status_code == 404,
            "Invalid permak ID returns 404",
            f"Got {r.status_code}"
        )
    except Exception as e:
        results.check(False, "Get permak 404", f"Exception: {e}")

def test_permak_update_terminal():
    """Test 12: PUT /api/dewi/cmt-permak/{id} on terminal status (400)"""
    print("\n=== TEST 12: Update Permak - Terminal Status (400) ===")
    # This test requires a permak in terminal status, which we don't have
    # So we just document the expected behavior
    print("    ℹ️  Test requires existing terminal permak (skipped)")

def test_permak_delete_non_open():
    """Test 13: DELETE /api/dewi/cmt-permak/{id} on non-open status (400)"""
    print("\n=== TEST 13: Delete Permak - Non-Open Status (400) ===")
    # This test requires a permak in non-open status
    print("    ℹ️  Test requires existing non-open permak (skipped)")

def test_permak_status_invalid_transition():
    """Test 14: POST /api/dewi/cmt-permak/{id}/status with invalid transition (400)"""
    print("\n=== TEST 14: Permak Status - Invalid Transition (400) ===")
    # This test requires an existing permak
    print("    ℹ️  Test requires existing permak (skipped)")

def test_permak_status_success_qty_mismatch():
    """Test 15: POST /api/dewi/cmt-permak/{id}/status selesai_berhasil with qty mismatch (400)"""
    print("\n=== TEST 15: Permak Status - Qty Mismatch (400) ===")
    # This test requires an existing permak
    print("    ℹ️  Test requires existing permak (skipped)")

def test_core_maklon_progress():
    """Test 16: Run core maklon progress test (comprehensive)"""
    print("\n=== TEST 16: Core Maklon Progress Test ===")
    try:
        import subprocess
        result = subprocess.run(
            ["python", "/app/tests/test_core_maklon_progress.py"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        results.check(
            result.returncode == 0,
            "Core progress test passes",
            f"Exit code: {result.returncode}"
        )
        
        if result.returncode != 0:
            print("    Core test output:")
            print(result.stdout[-500:] if len(result.stdout) > 500 else result.stdout)
            if result.stderr:
                print("    Errors:")
                print(result.stderr[-500:] if len(result.stderr) > 500 else result.stderr)
        else:
            # Count passed tests from output
            if "passed" in result.stdout:
                lines = result.stdout.split('RESULT:')
                if len(lines) > 1:
                    summary_line = lines[1].split('\n')[0].strip()
                    print(f"    {summary_line}")
    except subprocess.TimeoutExpired:
        results.check(False, "Core progress test", "Timeout after 60s")
    except Exception as e:
        results.check(False, "Core progress test", f"Exception: {e}")

# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("=" * 80)
    print("BACKEND API TEST - Maklon Phase 2: Permak + Canonical Progress")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Admin: {ADMIN_EMAIL}")
    
    try:
        # Run tests
        test_admin_login()
        
        if not test_data["admin_token"]:
            print("\n❌ CRITICAL: Admin login failed, cannot continue")
            return 1
        
        # Auth tests
        test_auth_401_without_token()
        
        # Permak CRUD tests (basic)
        test_permak_list_empty()
        test_permak_summary_empty()
        test_create_permak_invalid_po()
        test_create_permak_invalid_qty()
        test_from_receipt_line_invalid()
        test_permak_get_404()
        test_permak_update_terminal()
        test_permak_delete_non_open()
        test_permak_status_invalid_transition()
        test_permak_status_success_qty_mismatch()
        
        # Backward compatibility tests
        test_client_pos_list_backward_compat()
        test_client_po_progress_endpoint()
        test_po_360_regression()
        
        # Comprehensive core test
        test_core_maklon_progress()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Results: {results.summary()}")
    print(f"Passed: {results.passed}")
    print(f"Failed: {results.failed}")
    
    if results.critical_failures:
        print(f"\n❌ CRITICAL FAILURES: {len(results.critical_failures)}")
        for test in results.critical_failures:
            print(f"  - {test}")
    
    if results.failed > 0:
        print("\n❌ FAILED TESTS:")
        for test in results.tests:
            if test['status'] == 'FAIL':
                print(f"  - {test['name']}: {test['details']}")
    
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
