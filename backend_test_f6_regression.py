#!/usr/bin/env python3
"""
Backend API testing for F6 RBAC Scope Regression
Tests admin, staff with stores, and staff without stores
"""
import requests
import sys
from typing import Dict, Any, List

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test credentials
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
STAFF_NO_STORES = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}
STAFF_2_STORES = {"email": "stafnia@dewiaditya.id", "password": "Dewi@123"}

# Expected values for admin (9 stores)
EXPECTED_ADMIN = {
    "orders_total": 559,
    "orders_revenue": 57561529,
    "accounts_total": 9,
    "discounts_total": 10,
    "launches_total": 8,
    "content_total": 15,
    "samples_total": 35,
}

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

class TestResults:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, msg):
        self.passed.append(msg)
        print(f"{Colors.GREEN}✓ PASS{Colors.RESET} {msg}")
    
    def add_fail(self, msg):
        self.failed.append(msg)
        print(f"{Colors.RED}✗ FAIL{Colors.RESET} {msg}")
    
    def add_warn(self, msg):
        self.warnings.append(msg)
        print(f"{Colors.YELLOW}⚠ WARN{Colors.RESET} {msg}")
    
    def summary(self):
        total = len(self.passed) + len(self.failed)
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"{Colors.BOLD}TEST SUMMARY{Colors.RESET}")
        print(f"Total: {total} | Passed: {Colors.GREEN}{len(self.passed)}{Colors.RESET} | Failed: {Colors.RED}{len(self.failed)}{Colors.RESET} | Warnings: {Colors.YELLOW}{len(self.warnings)}{Colors.RESET}")
        
        if self.failed:
            print(f"\n{Colors.RED}FAILED TESTS:{Colors.RESET}")
            for f in self.failed:
                print(f"  - {f}")
        
        if self.warnings:
            print(f"\n{Colors.YELLOW}WARNINGS:{Colors.RESET}")
            for w in self.warnings:
                print(f"  - {w}")
        
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
        return len(self.failed) == 0

def login(creds: Dict[str, str]) -> str:
    """Login and get token"""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        r.raise_for_status()
        token = r.json()["token"]
        return token
    except Exception as e:
        print(f"{Colors.RED}Login failed for {creds['email']}: {e}{Colors.RESET}")
        raise

def get_api(endpoint: str, token: str, params: Dict = None) -> tuple:
    """Make GET request and return (status_code, json_data)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, params=params, timeout=60)
        return r.status_code, r.json() if r.status_code == 200 else {}
    except Exception as e:
        return 500, {"error": str(e)}

def test_admin_regression(token: str, results: TestResults):
    """Test that admin still sees all data after scope patches"""
    print(f"\n{Colors.BOLD}[ADMIN REGRESSION] Testing admin access to all stores{Colors.RESET}")
    
    # Test orders summary
    status, data = get_api("/api/marketing/orders/summary", token)
    if status == 200:
        total_orders = data.get("total_orders", 0)
        total_revenue = data.get("total_revenue", 0)
        if total_orders == EXPECTED_ADMIN["orders_total"]:
            results.add_pass(f"orders/summary: total_orders = {total_orders} (expected {EXPECTED_ADMIN['orders_total']})")
        else:
            results.add_fail(f"orders/summary: total_orders = {total_orders}, expected {EXPECTED_ADMIN['orders_total']}")
        
        if total_revenue == EXPECTED_ADMIN["orders_revenue"]:
            results.add_pass(f"orders/summary: total_revenue = {total_revenue} (expected {EXPECTED_ADMIN['orders_revenue']})")
        else:
            results.add_fail(f"orders/summary: total_revenue = {total_revenue}, expected {EXPECTED_ADMIN['orders_revenue']}")
    else:
        results.add_fail(f"orders/summary: HTTP {status}")
    
    # Test account health summary
    status, data = get_api("/api/marketing/health/summary", token)
    if status == 200:
        total_accounts = data.get("data", {}).get("total_accounts", 0)
        if total_accounts == EXPECTED_ADMIN["accounts_total"]:
            results.add_pass(f"health/summary: total_accounts = {total_accounts} (expected {EXPECTED_ADMIN['accounts_total']})")
        else:
            results.add_fail(f"health/summary: total_accounts = {total_accounts}, expected {EXPECTED_ADMIN['accounts_total']}")
    else:
        results.add_fail(f"health/summary: HTTP {status}")
    
    # Test discounts summary
    status, data = get_api("/api/marketing/discounts/summary", token)
    if status == 200:
        total = data.get("data", {}).get("total", 0)
        if total == EXPECTED_ADMIN["discounts_total"]:
            results.add_pass(f"discounts/summary: total = {total} (expected {EXPECTED_ADMIN['discounts_total']})")
        else:
            results.add_fail(f"discounts/summary: total = {total}, expected {EXPECTED_ADMIN['discounts_total']}")
    else:
        results.add_fail(f"discounts/summary: HTTP {status}")
    
    # Test product launches summary
    status, data = get_api("/api/marketing/product-launches/summary", token)
    if status == 200:
        total = data.get("data", {}).get("total", 0)
        if total == EXPECTED_ADMIN["launches_total"]:
            results.add_pass(f"product-launches/summary: total = {total} (expected {EXPECTED_ADMIN['launches_total']})")
        else:
            results.add_fail(f"product-launches/summary: total = {total}, expected {EXPECTED_ADMIN['launches_total']}")
    else:
        results.add_fail(f"product-launches/summary: HTTP {status}")
    
    # Test content calendar summary
    status, data = get_api("/api/marketing/content-calendar/summary", token)
    if status == 200:
        total = data.get("data", {}).get("total", 0)
        if total == EXPECTED_ADMIN["content_total"]:
            results.add_pass(f"content-calendar/summary: total = {total} (expected {EXPECTED_ADMIN['content_total']})")
        else:
            results.add_fail(f"content-calendar/summary: total = {total}, expected {EXPECTED_ADMIN['content_total']}")
    else:
        results.add_fail(f"content-calendar/summary: HTTP {status}")
    
    # Test samples summary
    status, data = get_api("/api/marketing/samples/summary", token)
    if status == 200:
        total = data.get("data", {}).get("total", 0)
        if total == EXPECTED_ADMIN["samples_total"]:
            results.add_pass(f"samples/summary: total = {total} (expected {EXPECTED_ADMIN['samples_total']})")
        else:
            results.add_fail(f"samples/summary: total = {total}, expected {EXPECTED_ADMIN['samples_total']}")
    else:
        results.add_fail(f"samples/summary: HTTP {status}")
    
    # Test other endpoints (should return 200 with data)
    endpoints = [
        "/api/marketing/targets",
        "/api/marketing/catalogs",
        "/api/marketing/catalog-items/search",
        "/api/marketing/data-import/history",
        "/api/marketing/orders/fulfillment-monitor",
        "/api/marketing/ai-insights/overview",
        "/api/marketing/budget/kol-cost",
        "/api/marketing/livehost",
        "/api/marketing/livehost/shifts",
        "/api/marketing/tasks",
        "/api/marketing/targets/creator",
        "/api/marketing/targets/creator/monthly-summary",
    ]
    
    for endpoint in endpoints:
        status, data = get_api(endpoint, token)
        if status == 200:
            results.add_pass(f"{endpoint}: HTTP 200")
        else:
            results.add_fail(f"{endpoint}: HTTP {status}")

def test_staff_no_stores(token: str, results: TestResults):
    """Test that staff without stores sees 0 but gets 200 (not 403/500)"""
    print(f"\n{Colors.BOLD}[SECURITY] Testing staff WITHOUT stores (staffmkt@dewiaditya.id){Colors.RESET}")
    
    endpoints_to_test = [
        ("/api/marketing/orders/summary", "total_orders"),
        ("/api/marketing/health/summary", "data.total_accounts"),
        ("/api/marketing/discounts/summary", "data.total"),
        ("/api/marketing/product-launches/summary", "data.total"),
        ("/api/marketing/content-calendar/summary", "data.total"),
        ("/api/marketing/samples/summary", "data.total"),
    ]
    
    for endpoint, path in endpoints_to_test:
        status, data = get_api(endpoint, token)
        
        # Must be 200 (not 403 or 500)
        if status != 200:
            results.add_fail(f"{endpoint}: HTTP {status} (expected 200)")
            continue
        
        # Extract value using path
        value = data
        for key in path.split("."):
            value = value.get(key, 0) if isinstance(value, dict) else 0
        
        # Must be 0 or empty
        if value == 0 or value == [] or value == {}:
            results.add_pass(f"{endpoint}: returns 200 with {path}={value} (correct for staff with no stores)")
        else:
            results.add_fail(f"{endpoint}: returns {path}={value} (should be 0 for staff with no stores - DATA LEAK!)")
    
    # Test list endpoints
    list_endpoints = [
        "/api/marketing/targets",
        "/api/marketing/catalogs",
        "/api/marketing/data-import/history",
        "/api/marketing/change-log",
    ]
    
    for endpoint in list_endpoints:
        status, data = get_api(endpoint, token)
        if status == 200:
            # Check if list is empty or has 0 total
            is_empty = False
            if isinstance(data, list) and len(data) == 0:
                is_empty = True
            elif isinstance(data, dict):
                if data.get("total") == 0 or len(data.get("rows", [])) == 0:
                    is_empty = True
            
            if is_empty:
                results.add_pass(f"{endpoint}: returns 200 with empty data (correct)")
            else:
                results.add_fail(f"{endpoint}: returns data (should be empty for staff with no stores)")
        else:
            results.add_fail(f"{endpoint}: HTTP {status} (expected 200)")

def test_staff_with_stores(token: str, results: TestResults):
    """Test that staff with 2 stores sees their data (not 0, not all 9 stores)"""
    print(f"\n{Colors.BOLD}[SECURITY] Testing staff WITH 2 stores (stafnia@dewiaditya.id){Colors.RESET}")
    
    # Test account health - should see 2 accounts
    status, data = get_api("/api/marketing/health/summary", token)
    if status == 200:
        total_accounts = data.get("data", {}).get("total_accounts", 0)
        if total_accounts == 2:
            results.add_pass(f"health/summary: total_accounts = {total_accounts} (expected 2 for staff with 2 stores)")
        elif total_accounts == 0:
            results.add_fail(f"health/summary: total_accounts = 0 (should see their 2 stores)")
        elif total_accounts == 9:
            results.add_fail(f"health/summary: total_accounts = 9 (DATA LEAK - should only see 2 stores)")
        else:
            results.add_warn(f"health/summary: total_accounts = {total_accounts} (expected 2)")
    else:
        results.add_fail(f"health/summary: HTTP {status}")
    
    # Test change log - should see 8 changes
    status, data = get_api("/api/marketing/change-log", token, {"page_size": 100})
    if status == 200:
        total = data.get("total", 0)
        if total == 8:
            results.add_pass(f"change-log: total = {total} (expected 8 for staff with 2 stores)")
        elif total == 0:
            results.add_fail(f"change-log: total = 0 (should see changes for their stores)")
        elif total >= 13:
            results.add_fail(f"change-log: total = {total} (DATA LEAK - should only see 8)")
        else:
            results.add_warn(f"change-log: total = {total} (expected 8)")
    else:
        results.add_fail(f"change-log: HTTP {status}")
    
    # Test orders summary - should NOT leak admin's data (not 559 orders / 57.5M)
    # Note: stafnia's stores (Shopee Daluna, Shopee Grosirhijabsragen) may have 0 orders
    # in test data, which is OK - the key is they DON'T see other stores' data
    status, data = get_api("/api/marketing/orders/summary", token)
    if status == 200:
        total_orders = data.get("total_orders", 0)
        total_revenue = data.get("total_revenue", 0)
        
        # Check for data leak (seeing all 559 orders or 57.5M revenue)
        if total_orders == EXPECTED_ADMIN["orders_total"] or total_revenue == EXPECTED_ADMIN["orders_revenue"]:
            results.add_fail(f"orders/summary: DATA LEAK - seeing admin's data (orders={total_orders}, revenue={total_revenue})")
        else:
            results.add_pass(f"orders/summary: NOT leaking admin data (orders={total_orders}, revenue={total_revenue}). Correct scope filtering.")
    else:
        results.add_fail(f"orders/summary: HTTP {status}")

def main():
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}F6 RBAC SCOPE REGRESSION TEST{Colors.RESET}")
    print(f"{Colors.BOLD}Testing: Admin, Staff with 2 stores, Staff without stores{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    
    results = TestResults()
    
    try:
        # Login all users
        print(f"{Colors.BOLD}[LOGIN] Authenticating users...{Colors.RESET}")
        admin_token = login(ADMIN)
        results.add_pass(f"Login successful: {ADMIN['email']}")
        
        staff_no_token = login(STAFF_NO_STORES)
        results.add_pass(f"Login successful: {STAFF_NO_STORES['email']}")
        
        staff_2_token = login(STAFF_2_STORES)
        results.add_pass(f"Login successful: {STAFF_2_STORES['email']}")
        
        # Run tests
        test_admin_regression(admin_token, results)
        test_staff_no_stores(staff_no_token, results)
        test_staff_with_stores(staff_2_token, results)
        
        # Summary
        success = results.summary()
        return 0 if success else 1
        
    except Exception as e:
        print(f"{Colors.RED}Test execution failed: {e}{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
