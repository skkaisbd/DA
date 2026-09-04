#!/usr/bin/env python3
"""Backend API testing for F6 RBAC & Change Log features (UI testing support)"""
import requests
import sys
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test credentials from test_credentials.md
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
STAFF_NO_STORES = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}
STAFF_2_STORES = {"email": "stafnia@dewiaditya.id", "password": "Dewi@123"}
STAFF_1_STORE = {"email": "stafrio@dewiaditya.id", "password": "Dewi@123"}
MANAGER = {"email": "marketing@dewiaditya.id", "password": "Dewi@123"}

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def log(msg, status="INFO"):
    color = Colors.GREEN if status == "PASS" else Colors.RED if status == "FAIL" else Colors.YELLOW
    print(f"{color}{status}{Colors.RESET} {msg}")

def login(creds):
    """Login and get token"""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        r.raise_for_status()
        token = r.json()["token"]
        return token
    except Exception as e:
        log(f"Login failed for {creds['email']}: {e}", "FAIL")
        return None

def test_login_all_users():
    """Test login for all user types"""
    print(f"\n{Colors.BOLD}=== Testing Login for All Users ==={Colors.RESET}")
    
    users = [
        ("Admin", ADMIN),
        ("Staff (no stores)", STAFF_NO_STORES),
        ("Staff (2 stores)", STAFF_2_STORES),
        ("Staff (1 store)", STAFF_1_STORE),
        ("Manager", MANAGER)
    ]
    
    tokens = {}
    for name, creds in users:
        token = login(creds)
        if token:
            tokens[name] = token
            log(f"Login successful: {name} ({creds['email']})", "PASS")
        else:
            log(f"Login failed: {name} ({creds['email']})", "FAIL")
            return None
    
    return tokens

def test_change_log_api(tokens):
    """Test change log API endpoints"""
    print(f"\n{Colors.BOLD}=== Testing Change Log API ==={Colors.RESET}")
    
    admin_token = tokens.get("Admin")
    staff_no_stores_token = tokens.get("Staff (no stores)")
    staff_2_stores_token = tokens.get("Staff (2 stores)")
    
    if not all([admin_token, staff_no_stores_token, staff_2_stores_token]):
        log("Missing required tokens", "FAIL")
        return False
    
    # Test 1: Admin can access change log
    try:
        r = requests.get(
            f"{BASE_URL}/api/marketing/change-log?page_size=5",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("ok") and "total" in data and "rows" in data:
                log(f"Admin: Change log accessible (total={data.get('total')})", "PASS")
            else:
                log(f"Admin: Change log response missing required fields", "FAIL")
                return False
        else:
            log(f"Admin: Change log HTTP {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"Admin: Change log error: {e}", "FAIL")
        return False
    
    # Test 2: Staff with no stores sees empty or limited data
    try:
        r = requests.get(
            f"{BASE_URL}/api/marketing/change-log?page_size=5",
            headers={"Authorization": f"Bearer {staff_no_stores_token}"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            total_staff_no_stores = data.get("total", 0)
            log(f"Staff (no stores): Change log accessible (total={total_staff_no_stores})", "PASS")
        else:
            log(f"Staff (no stores): Change log HTTP {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"Staff (no stores): Change log error: {e}", "FAIL")
        return False
    
    # Test 3: Staff with 2 stores sees limited data
    try:
        r = requests.get(
            f"{BASE_URL}/api/marketing/change-log?page_size=5",
            headers={"Authorization": f"Bearer {staff_2_stores_token}"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            total_staff_2_stores = data.get("total", 0)
            log(f"Staff (2 stores): Change log accessible (total={total_staff_2_stores})", "PASS")
            
            # Staff with 2 stores should see less than admin
            admin_r = requests.get(
                f"{BASE_URL}/api/marketing/change-log?page_size=5",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30
            )
            admin_total = admin_r.json().get("total", 0)
            
            if total_staff_2_stores <= admin_total:
                log(f"RBAC: Staff (2 stores) sees {total_staff_2_stores} <= Admin sees {admin_total}", "PASS")
            else:
                log(f"RBAC: Staff (2 stores) sees MORE than admin ({total_staff_2_stores} > {admin_total})", "FAIL")
                return False
        else:
            log(f"Staff (2 stores): Change log HTTP {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"Staff (2 stores): Change log error: {e}", "FAIL")
        return False
    
    # Test 4: Change log stats endpoint
    try:
        r = requests.get(
            f"{BASE_URL}/api/marketing/change-log/stats?days=30",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            if "total" in data and "number_changes" in data and "permission_changes" in data:
                log(f"Change log stats: total={data.get('total')}, numbers={data.get('number_changes')}, permissions={data.get('permission_changes')}", "PASS")
            else:
                log("Change log stats: missing required fields", "FAIL")
                return False
        else:
            log(f"Change log stats HTTP {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"Change log stats error: {e}", "FAIL")
        return False
    
    # Test 5: Filter by only_permissions
    try:
        r = requests.get(
            f"{BASE_URL}/api/marketing/change-log?only_permissions=true&page_size=50",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            rows = data.get("rows", [])
            all_permissions = all(row.get("kind") == "kewenangan" for row in rows)
            if all_permissions:
                log(f"Filter only_permissions: all {len(rows)} rows are 'kewenangan'", "PASS")
            else:
                log(f"Filter only_permissions: some rows are not 'kewenangan'", "FAIL")
                return False
        else:
            log(f"Filter only_permissions HTTP {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"Filter only_permissions error: {e}", "FAIL")
        return False
    
    return True

def test_rbac_security(tokens):
    """Test RBAC security - staff with no stores should get 403 for other stores"""
    print(f"\n{Colors.BOLD}=== Testing RBAC Security ==={Colors.RESET}")
    
    admin_token = tokens.get("Admin")
    staff_no_stores_token = tokens.get("Staff (no stores)")
    
    if not all([admin_token, staff_no_stores_token]):
        log("Missing required tokens", "FAIL")
        return False
    
    # First, get a store ID from admin
    try:
        r = requests.get(
            f"{BASE_URL}/api/marketing/accounts",
            headers={"Authorization": f"Bearer {admin_token}"},
            timeout=30
        )
        if r.status_code == 200:
            data = r.json()
            # Handle both list and dict responses
            if isinstance(data, list):
                accounts = data
            else:
                accounts = data.get("accounts", [])
            
            if not accounts:
                log("No accounts found", "WARN")
                return True
            
            test_account_id = accounts[0].get("id")
            test_account_name = accounts[0].get("account_name")
            
            # Test: Staff with no stores should get 403 when accessing this store
            r = requests.get(
                f"{BASE_URL}/api/marketing/cycle/summary",
                headers={"Authorization": f"Bearer {staff_no_stores_token}"},
                params={"account_id": test_account_id, "period": "2026-07"},
                timeout=30
            )
            
            if r.status_code == 403:
                detail = r.json().get("detail", "")
                if test_account_name in detail and "SPV" in detail:
                    log(f"RBAC: Staff (no stores) correctly blocked from {test_account_name} with helpful message", "PASS")
                else:
                    log(f"RBAC: Staff (no stores) got 403 but message unclear: {detail[:100]}", "WARN")
            else:
                log(f"RBAC: Staff (no stores) should get 403 but got {r.status_code}", "FAIL")
                return False
            
            # Test: Admin should be able to access
            r = requests.get(
                f"{BASE_URL}/api/marketing/cycle/summary",
                headers={"Authorization": f"Bearer {admin_token}"},
                params={"account_id": test_account_id, "period": "2026-07"},
                timeout=30
            )
            
            if r.status_code == 200:
                log(f"RBAC: Admin can access {test_account_name}", "PASS")
            else:
                log(f"RBAC: Admin should access store but got {r.status_code}", "FAIL")
                return False
        else:
            log(f"Could not get accounts list: HTTP {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"RBAC security test error: {e}", "FAIL")
        return False
    
    return True

def test_list_endpoints_scope(tokens):
    """Test that list endpoints respect scope"""
    print(f"\n{Colors.BOLD}=== Testing List Endpoints Scope ==={Colors.RESET}")
    
    admin_token = tokens.get("Admin")
    staff_no_stores_token = tokens.get("Staff (no stores)")
    staff_2_stores_token = tokens.get("Staff (2 stores)")
    
    if not all([admin_token, staff_no_stores_token, staff_2_stores_token]):
        log("Missing required tokens", "FAIL")
        return False
    
    endpoints = [
        "/api/marketing/reports/daily",
        "/api/marketing/reports/monthly?year=2026&month=7",
        "/api/marketing/cycle/overview?period=2026-07",
    ]
    
    for endpoint in endpoints:
        try:
            # Admin should see data
            r_admin = requests.get(
                f"{BASE_URL}{endpoint}",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30
            )
            
            # Staff with no stores should see empty or very limited data
            r_staff_no = requests.get(
                f"{BASE_URL}{endpoint}",
                headers={"Authorization": f"Bearer {staff_no_stores_token}"},
                timeout=30
            )
            
            # Staff with 2 stores should see some data but less than admin
            r_staff_2 = requests.get(
                f"{BASE_URL}{endpoint}",
                headers={"Authorization": f"Bearer {staff_2_stores_token}"},
                timeout=30
            )
            
            if r_admin.status_code == 200 and r_staff_no.status_code == 200 and r_staff_2.status_code == 200:
                admin_data = r_admin.json()
                staff_no_data = r_staff_no.json()
                staff_2_data = r_staff_2.json()
                
                # Get counts
                admin_count = len(admin_data.get("accounts", admin_data.get("rows", [])))
                staff_no_count = len(staff_no_data.get("accounts", staff_no_data.get("rows", [])))
                staff_2_count = len(staff_2_data.get("accounts", staff_2_data.get("rows", [])))
                
                if staff_no_count == 0 and staff_2_count <= admin_count:
                    log(f"{endpoint}: Scope OK (admin={admin_count}, staff_2={staff_2_count}, staff_no={staff_no_count})", "PASS")
                else:
                    log(f"{endpoint}: Scope issue (admin={admin_count}, staff_2={staff_2_count}, staff_no={staff_no_count})", "FAIL")
                    return False
            else:
                log(f"{endpoint}: HTTP errors (admin={r_admin.status_code}, staff_no={r_staff_no.status_code}, staff_2={r_staff_2.status_code})", "FAIL")
                return False
        except Exception as e:
            log(f"{endpoint}: Error {e}", "FAIL")
            return False
    
    return True

def main():
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}Backend API Testing - F6 RBAC & Change Log{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    
    # Test 1: Login all users
    tokens = test_login_all_users()
    if not tokens:
        log("Login tests failed", "FAIL")
        return 1
    
    # Test 2: Change log API
    if not test_change_log_api(tokens):
        log("Change log API tests failed", "FAIL")
        return 1
    
    # Test 3: RBAC security
    if not test_rbac_security(tokens):
        log("RBAC security tests failed", "FAIL")
        return 1
    
    # Test 4: List endpoints scope
    if not test_list_endpoints_scope(tokens):
        log("List endpoints scope tests failed", "FAIL")
        return 1
    
    print(f"\n{Colors.BOLD}{Colors.GREEN}All backend tests passed!{Colors.RESET}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
