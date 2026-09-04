#!/usr/bin/env python3
"""Backend API testing for F6 RBAC scope feature - Marketing scope guard & change log"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test credentials
ADMIN_CREDS = {"email": "admin@garment.com", "password": "Admin@123"}
STAFF_CREDS = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}  # NO stores assigned
SPV_CREDS = {"email": "spv@dewiaditya.id", "password": "Dewi@123"}  # Sees all stores

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
    def add(self, name, passed, detail=""):
        self.tests.append({"name": name, "passed": passed, "detail": detail})
        if passed:
            self.passed += 1
            print(f"{Colors.GREEN}✓ PASS{Colors.RESET} {name}")
        else:
            self.failed += 1
            print(f"{Colors.RED}✗ FAIL{Colors.RESET} {name}")
        if detail:
            print(f"         {detail}")
    
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}Test Summary: {self.passed}/{total} passed{Colors.RESET}")
        if self.failed > 0:
            print(f"{Colors.RED}{Colors.BOLD}FAILED TESTS:{Colors.RESET}")
            for t in self.tests:
                if not t["passed"]:
                    print(f"  {Colors.RED}✗{Colors.RESET} {t['name']}")
        else:
            print(f"{Colors.GREEN}{Colors.BOLD}ALL TESTS PASSED!{Colors.RESET}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        return self.failed == 0

def login(creds, label):
    """Login and get token"""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        r.raise_for_status()
        token = r.json()["token"]
        print(f"{Colors.GREEN}✓{Colors.RESET} Login successful: {label}")
        return token
    except Exception as e:
        print(f"{Colors.RED}✗{Colors.RESET} Login failed for {label}: {e}")
        return None

def get_first_account_id(token):
    """Get first active account ID for testing"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=headers, timeout=30)
        if r.status_code == 200:
            accounts = r.json().get("accounts", [])
            if accounts:
                return accounts[0].get("id")
    except:
        pass
    return None

def test_security_endpoints(results, admin_token, staff_token, account_id):
    """Test that staff without stores gets 403, admin gets 200"""
    print(f"\n{Colors.YELLOW}[SECURITY] Testing endpoint access control{Colors.RESET}")
    
    if not account_id:
        results.add("Security: Get account_id", False, "No account_id available")
        return
    
    # Test endpoints that should return 403 for staff without stores
    test_cases = [
        ("GET", f"/api/marketing/cycle/summary?account_id={account_id}&period=2026-07", None),
        ("GET", f"/api/marketing/accounts/{account_id}/sales", None),
        ("POST", f"/api/marketing/sales/recompute?account_id={account_id}&date_from=2026-07-05", None),
        ("POST", f"/api/marketing/sales-data", {"account_id": account_id, "date": "2027-05-05", "revenue_type": "total", "revenue": 1}),
    ]
    
    for method, endpoint, body in test_cases:
        # Test with staff token (should be 403)
        headers_staff = {"Authorization": f"Bearer {staff_token}"}
        try:
            if method == "GET":
                r_staff = requests.get(f"{BASE_URL}{endpoint}", headers=headers_staff, timeout=30)
            else:
                r_staff = requests.post(f"{BASE_URL}{endpoint}", headers=headers_staff, json=body, timeout=30)
            
            staff_403 = r_staff.status_code == 403
            
            # Check if message mentions store name and SPV
            detail_msg = r_staff.json().get("detail", "") if r_staff.status_code == 403 else ""
            has_hint = "SPV" in detail_msg or "assign" in detail_msg.lower()
            
            results.add(
                f"Security: {method} {endpoint.split('?')[0][:50]} → 403 for staff",
                staff_403,
                f"HTTP {r_staff.status_code}, hint present: {has_hint}"
            )
        except Exception as e:
            results.add(f"Security: {method} {endpoint[:50]} → 403 for staff", False, str(e))
        
        # Test with admin token (should be 200)
        headers_admin = {"Authorization": f"Bearer {admin_token}"}
        try:
            if method == "GET":
                r_admin = requests.get(f"{BASE_URL}{endpoint}", headers=headers_admin, timeout=30)
            else:
                r_admin = requests.post(f"{BASE_URL}{endpoint}", headers=headers_admin, json=body, timeout=30)
            
            admin_200 = r_admin.status_code == 200
            results.add(
                f"Security: {method} {endpoint.split('?')[0][:50]} → 200 for admin",
                admin_200,
                f"HTTP {r_admin.status_code}"
            )
        except Exception as e:
            results.add(f"Security: {method} {endpoint[:50]} → 200 for admin", False, str(e))

def test_data_leak_prevention(results, admin_token, staff_token):
    """Test that staff sees less data than admin (no data leak)"""
    print(f"\n{Colors.YELLOW}[DATA LEAK] Testing data visibility scope{Colors.RESET}")
    
    # Endpoints that should return different data for staff vs admin
    endpoints = [
        ("/api/marketing/reports/daily", "accounts"),
        ("/api/marketing/reports/monthly?year=2026&month=7", "accounts"),
        ("/api/marketing/ads/summary", "data.total_spend"),
        ("/api/marketing/complaints", "complaints"),
        ("/api/marketing/live/sessions", "data.sessions"),
        ("/api/marketing/data-import/sessions", "sessions"),
        ("/api/marketing/cycle/overview?period=2026-07", "rows"),
    ]
    
    for endpoint, data_path in endpoints:
        try:
            # Get staff response
            headers_staff = {"Authorization": f"Bearer {staff_token}"}
            r_staff = requests.get(f"{BASE_URL}{endpoint}", headers=headers_staff, timeout=30)
            
            # Get admin response
            headers_admin = {"Authorization": f"Bearer {admin_token}"}
            r_admin = requests.get(f"{BASE_URL}{endpoint}", headers=headers_admin, timeout=30)
            
            if r_staff.status_code == 200 and r_admin.status_code == 200:
                # Extract data using path
                staff_data = r_staff.json()
                admin_data = r_admin.json()
                
                for key in data_path.split("."):
                    staff_data = staff_data.get(key, []) if isinstance(staff_data, dict) else staff_data
                    admin_data = admin_data.get(key, []) if isinstance(admin_data, dict) else admin_data
                
                # Count/value comparison
                staff_val = len(staff_data) if isinstance(staff_data, list) else (staff_data or 0)
                admin_val = len(admin_data) if isinstance(admin_data, list) else (admin_data or 0)
                
                # Staff should see less or equal data (and if admin has data, staff should have less)
                no_leak = (staff_val <= admin_val) and (staff_val < admin_val if admin_val > 0 else True)
                
                results.add(
                    f"Data Leak: {endpoint[:50]}",
                    no_leak,
                    f"staff={staff_val}, admin={admin_val}"
                )
            else:
                results.add(
                    f"Data Leak: {endpoint[:50]}",
                    False,
                    f"HTTP staff={r_staff.status_code}, admin={r_admin.status_code}"
                )
        except Exception as e:
            results.add(f"Data Leak: {endpoint[:50]}", False, str(e))

def test_change_log_api(results, admin_token, staff_token):
    """Test change log API functionality"""
    print(f"\n{Colors.YELLOW}[CHANGE LOG] Testing change log API{Colors.RESET}")
    
    headers_admin = {"Authorization": f"Bearer {admin_token}"}
    
    # Test basic change log endpoint
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/change-log?page_size=5", headers=headers_admin, timeout=30)
        if r.status_code == 200:
            data = r.json()
            has_ok = data.get("ok") == True
            has_total = isinstance(data.get("total"), int)
            has_rows = isinstance(data.get("rows"), list)
            has_pages = "total_pages" in data
            
            results.add(
                "Change Log: Basic endpoint structure",
                has_ok and has_total and has_rows and has_pages,
                f"ok={has_ok}, total={data.get('total')}, rows={len(data.get('rows', []))}, pages={data.get('total_pages')}"
            )
            
            # Check if rows have proper structure
            rows = data.get("rows", [])
            if rows:
                row = rows[0]
                has_changes = "changes" in row
                has_kind = row.get("kind") in ["kewenangan", "angka"]
                has_actor = "actor_name" in row and "actor_role" in row
                
                results.add(
                    "Change Log: Row structure (changes, kind, actor)",
                    has_changes and has_kind and has_actor,
                    f"kind={row.get('kind')}, actor={row.get('actor_name')}"
                )
                
                # Check changes structure
                changes = row.get("changes", [])
                if changes:
                    change = changes[0]
                    has_field = "field_label" in change
                    has_before_after = "before" in change and "after" in change
                    
                    results.add(
                        "Change Log: Changes have field_label, before, after",
                        has_field and has_before_after,
                        f"field={change.get('field_label')}"
                    )
            
            # Check filters
            filters = data.get("filters", {})
            has_entities = isinstance(filters.get("entities"), list)
            has_actions = isinstance(filters.get("actions"), list)
            has_actors = isinstance(filters.get("actors"), list)
            
            results.add(
                "Change Log: Filters present (entities, actions, actors)",
                has_entities and has_actions and has_actors,
                f"entities={len(filters.get('entities', []))}, actions={len(filters.get('actions', []))}, actors={len(filters.get('actors', []))}"
            )
            
            # Check data notes
            notes = data.get("data_notes", [])
            has_readonly_note = any("READ-ONLY" in note for note in notes)
            
            results.add(
                "Change Log: Data notes include READ-ONLY mention",
                has_readonly_note,
                f"notes count={len(notes)}"
            )
        else:
            results.add("Change Log: Basic endpoint", False, f"HTTP {r.status_code}")
    except Exception as e:
        results.add("Change Log: Basic endpoint", False, str(e))
    
    # Test stats endpoint
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/change-log/stats?days=30", headers=headers_admin, timeout=30)
        if r.status_code == 200:
            data = r.json()
            has_total = isinstance(data.get("total"), int)
            has_perm = isinstance(data.get("permission_changes"), int)
            has_num = isinstance(data.get("number_changes"), int)
            total_matches = data.get("total") == data.get("permission_changes", 0) + data.get("number_changes", 0)
            
            results.add(
                "Change Log: Stats endpoint (total = perm + number)",
                has_total and has_perm and has_num and total_matches,
                f"total={data.get('total')}, perm={data.get('permission_changes')}, num={data.get('number_changes')}"
            )
        else:
            results.add("Change Log: Stats endpoint", False, f"HTTP {r.status_code}")
    except Exception as e:
        results.add("Change Log: Stats endpoint", False, str(e))
    
    # Test filter: only permissions
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/change-log?only_permissions=true&page_size=50", headers=headers_admin, timeout=30)
        if r.status_code == 200:
            data = r.json()
            rows = data.get("rows", [])
            all_perm = all(row.get("kind") == "kewenangan" for row in rows) if rows else True
            
            results.add(
                "Change Log: Filter only_permissions works",
                all_perm,
                f"total={data.get('total')}, all are kewenangan={all_perm}"
            )
        else:
            results.add("Change Log: Filter only_permissions", False, f"HTTP {r.status_code}")
    except Exception as e:
        results.add("Change Log: Filter only_permissions", False, str(e))
    
    # Test staff scope on change log
    try:
        headers_staff = {"Authorization": f"Bearer {staff_token}"}
        r_staff = requests.get(f"{BASE_URL}/api/marketing/change-log?page_size=100", headers=headers_staff, timeout=30)
        r_admin = requests.get(f"{BASE_URL}/api/marketing/change-log?page_size=100", headers=headers_admin, timeout=30)
        
        if r_staff.status_code == 200 and r_admin.status_code == 200:
            staff_total = r_staff.json().get("total", 0)
            admin_total = r_admin.json().get("total", 0)
            staff_notes = r_staff.json().get("data_notes", [])
            
            # Staff should see less or equal
            scope_works = staff_total <= admin_total
            
            # Staff should be told about scope limitation
            has_scope_note = any("di-assign" in note or "assign" in note.lower() for note in staff_notes)
            
            results.add(
                "Change Log: Staff sees scoped data with note",
                scope_works and has_scope_note,
                f"staff_total={staff_total}, admin_total={admin_total}, has_note={has_scope_note}"
            )
        else:
            results.add("Change Log: Staff scope", False, f"HTTP staff={r_staff.status_code}, admin={r_admin.status_code}")
    except Exception as e:
        results.add("Change Log: Staff scope", False, str(e))
    
    # Test that change log has NO write endpoints (should be 404/405)
    for method in ["POST", "PUT", "DELETE"]:
        try:
            if method == "POST":
                r = requests.post(f"{BASE_URL}/api/marketing/change-log", headers=headers_admin, json={}, timeout=30)
            elif method == "PUT":
                r = requests.put(f"{BASE_URL}/api/marketing/change-log/test", headers=headers_admin, json={}, timeout=30)
            else:
                r = requests.delete(f"{BASE_URL}/api/marketing/change-log/test", headers=headers_admin, timeout=30)
            
            is_blocked = r.status_code in [404, 405]
            results.add(
                f"Change Log: {method} endpoint blocked (404/405)",
                is_blocked,
                f"HTTP {r.status_code}"
            )
        except Exception as e:
            results.add(f"Change Log: {method} endpoint blocked", False, str(e))

def test_staff_empty_screens(results, staff_token):
    """Test that staff without stores sees empty data (not crash)"""
    print(f"\n{Colors.YELLOW}[EMPTY SCREENS] Testing staff without stores sees empty data{Colors.RESET}")
    
    # Endpoints that should return 200 but with empty/minimal data for staff without stores
    endpoints = [
        "/api/marketing/reports/daily",
        "/api/marketing/cycle/overview?period=2026-07",
        "/api/marketing/live/sessions",
        "/api/marketing/complaints",
        "/api/marketing/data-import/sessions",
    ]
    
    headers = {"Authorization": f"Bearer {staff_token}"}
    
    for endpoint in endpoints:
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=30)
            
            # Should return 200 (not crash)
            is_200 = r.status_code == 200
            
            results.add(
                f"Empty Screen: {endpoint[:50]} returns 200",
                is_200,
                f"HTTP {r.status_code}"
            )
        except Exception as e:
            results.add(f"Empty Screen: {endpoint[:50]}", False, str(e))

def main():
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}F6 RBAC Backend API Testing{Colors.RESET}")
    print(f"{Colors.BOLD}Testing: Marketing scope guard + change log{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    
    results = TestResults()
    
    # Login
    print(f"{Colors.YELLOW}[LOGIN] Authenticating users{Colors.RESET}")
    admin_token = login(ADMIN_CREDS, "Admin")
    staff_token = login(STAFF_CREDS, "Staff (no stores)")
    spv_token = login(SPV_CREDS, "SPV")
    
    if not admin_token or not staff_token:
        print(f"{Colors.RED}Cannot proceed without tokens{Colors.RESET}")
        return 1
    
    # Get an account ID for testing
    account_id = get_first_account_id(admin_token)
    if account_id:
        print(f"{Colors.GREEN}✓{Colors.RESET} Got test account_id: {account_id[:8]}...")
    else:
        print(f"{Colors.YELLOW}⚠{Colors.RESET} No account_id found, some tests will be skipped")
    
    # Run tests
    test_security_endpoints(results, admin_token, staff_token, account_id)
    test_data_leak_prevention(results, admin_token, staff_token)
    test_change_log_api(results, admin_token, staff_token)
    test_staff_empty_screens(results, staff_token)
    
    # Summary
    success = results.summary()
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
