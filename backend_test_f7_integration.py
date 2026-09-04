#!/usr/bin/env python3
"""Backend Integration Test for F7.2 (Shopee KPI Import), F6.4 (Assign Toko), F7.4 (Scorecard)"""
import os
import sys
import requests
from datetime import datetime

# Use public endpoint
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test credentials
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
MGR = {"email": "marketing@dewiaditya.id", "password": "Dewi@123"}
STAFF = {"email": "staffmkt@dewiaditya.id", "password": "Dewi@123"}

class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
        
    def test(self, name, condition, details=""):
        self.tests.append(name)
        if condition:
            self.passed += 1
            print(f"  {Colors.GREEN}✓ PASS{Colors.RESET}  {name}" + (f" — {details}" if details else ""))
            return True
        else:
            self.failed += 1
            print(f"  {Colors.RED}✗ FAIL{Colors.RESET}  {name}" + (f" — {details}" if details else ""))
            return False
    
    def summary(self):
        total = self.passed + self.failed
        color = Colors.GREEN if self.failed == 0 else Colors.RED
        print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
        print(f"SUMMARY: {color}{self.passed}/{total} PASSED{Colors.RESET}")
        if self.failed > 0:
            print(f"{Colors.RED}Failed tests:{Colors.RESET}")
            for i, name in enumerate(self.tests):
                if i >= self.passed:
                    print(f"  - {name}")
        print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
        return 0 if self.failed == 0 else 1

def login(creds):
    """Login and return token"""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
        if r.status_code == 200:
            return r.json().get("token")
        print(f"Login failed for {creds['email']}: {r.status_code} {r.text[:200]}")
        return None
    except Exception as e:
        print(f"Login error for {creds['email']}: {e}")
        return None

def main():
    runner = TestRunner()
    print(f"{Colors.BOLD}{'='*80}")
    print("BACKEND INTEGRATION TEST - F7.2 (KPI Import) + F6.4 (Assign) + F7.4 (Scorecard)")
    print(f"{'='*80}{Colors.RESET}\n")
    
    # Login
    print(f"{Colors.YELLOW}[1] AUTHENTICATION{Colors.RESET}")
    admin_token = login(ADMIN)
    mgr_token = login(MGR)
    staff_token = login(STAFF)
    
    runner.test("Admin login", admin_token is not None, f"token={'***' if admin_token else 'None'}")
    runner.test("Manager login", mgr_token is not None, f"token={'***' if mgr_token else 'None'}")
    runner.test("Staff login", staff_token is not None, f"token={'***' if staff_token else 'None'}")
    
    if not all([admin_token, mgr_token, staff_token]):
        print(f"\n{Colors.RED}Cannot proceed without valid tokens{Colors.RESET}")
        return runner.summary()
    
    AH = {"Authorization": f"Bearer {admin_token}"}
    MH = {"Authorization": f"Bearer {mgr_token}"}
    SH = {"Authorization": f"Bearer {staff_token}"}
    
    # Get accounts
    print(f"\n{Colors.YELLOW}[2] MARKETING ACCOUNTS{Colors.RESET}")
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=AH, timeout=30)
        runner.test("GET /api/marketing/accounts", r.status_code == 200, f"status={r.status_code}")
        accounts = r.json() if r.status_code == 200 else []
        shopee_accounts = [a for a in accounts if a.get("platform") == "shopee"]
        runner.test("Shopee accounts exist", len(shopee_accounts) > 0, f"found {len(shopee_accounts)} Shopee accounts")
        
        if shopee_accounts:
            test_account = shopee_accounts[0]
            account_id = test_account["id"]
            print(f"    Using account: {test_account.get('account_name')} (id={account_id})")
        else:
            print(f"{Colors.RED}No Shopee accounts found, skipping account-specific tests{Colors.RESET}")
            account_id = None
    except Exception as e:
        runner.test("GET /api/marketing/accounts", False, f"error: {e}")
        account_id = None
    
    # Test Platform KPI endpoints
    print(f"\n{Colors.YELLOW}[3] PLATFORM KPI ENDPOINTS{Colors.RESET}")
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/platform-kpi/summary", headers=MH, timeout=30)
        runner.test("GET /api/marketing/platform-kpi/summary", r.status_code == 200, f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            runner.test("Summary has channels", "channels" in data, f"keys={list(data.keys())}")
            runner.test("Summary has data_notes", "data_notes" in data and len(data.get("data_notes", [])) > 0, 
                       f"notes count={len(data.get('data_notes', []))}")
    except Exception as e:
        runner.test("GET /api/marketing/platform-kpi/summary", False, f"error: {e}")
    
    if account_id:
        try:
            r = requests.get(f"{BASE_URL}/api/marketing/platform-kpi/summary?account_id={account_id}", 
                           headers=MH, timeout=30)
            runner.test("GET /api/marketing/platform-kpi/summary with account_id", r.status_code == 200, 
                       f"status={r.status_code}")
        except Exception as e:
            runner.test("GET /api/marketing/platform-kpi/summary with account_id", False, f"error: {e}")
        
        try:
            r = requests.get(f"{BASE_URL}/api/marketing/platform-kpi?account_id={account_id}", 
                           headers=MH, timeout=30)
            runner.test("GET /api/marketing/platform-kpi (rows)", r.status_code == 200, f"status={r.status_code}")
            if r.status_code == 200:
                data = r.json()
                runner.test("KPI rows response has data_notes", "data_notes" in data, 
                           f"has rows={data.get('total', 0)}")
        except Exception as e:
            runner.test("GET /api/marketing/platform-kpi (rows)", False, f"error: {e}")
    
    # Test Account Assignment endpoints
    print(f"\n{Colors.YELLOW}[4] ACCOUNT ASSIGNMENT (F6.4){Colors.RESET}")
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/account-assign/staff-options", headers=MH, timeout=30)
        runner.test("GET /api/marketing/account-assign/staff-options", r.status_code == 200, 
                   f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            runner.test("Staff options has candidates", "options" in data and len(data.get("options", [])) > 0,
                       f"found {len(data.get('options', []))} staff")
    except Exception as e:
        runner.test("GET /api/marketing/account-assign/staff-options", False, f"error: {e}")
    
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/account-assign/overview", headers=MH, timeout=30)
        runner.test("GET /api/marketing/account-assign/overview", r.status_code == 200, 
                   f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            runner.test("Overview has rows", "rows" in data, f"accounts={len(data.get('rows', []))}")
            runner.test("Overview has can_edit flag", "can_edit" in data, f"can_edit={data.get('can_edit')}")
    except Exception as e:
        runner.test("GET /api/marketing/account-assign/overview", False, f"error: {e}")
    
    # Test RBAC: staff should get 403 when trying to assign
    if account_id:
        try:
            r = requests.post(f"{BASE_URL}/api/marketing/account-assign/{account_id}", 
                            headers={**SH, "Content-Type": "application/json"},
                            json={"staff_ids": [], "reason": "test"}, timeout=30)
            runner.test("Staff cannot assign (403)", r.status_code == 403, f"status={r.status_code}")
        except Exception as e:
            runner.test("Staff cannot assign (403)", False, f"error: {e}")
    
    # Test Creator Scorecard
    print(f"\n{Colors.YELLOW}[5] CREATOR SCORECARD (F7.4){Colors.RESET}")
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/targets/creator/scorecard?year=2026&month=8", 
                        headers=MH, timeout=30)
        runner.test("GET /api/marketing/targets/creator/scorecard", r.status_code == 200, 
                   f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            runner.test("Scorecard has rows", "rows" in data, f"creators={len(data.get('rows', []))}")
            runner.test("Scorecard has data_notes", "data_notes" in data and len(data.get("data_notes", [])) > 0,
                       f"notes count={len(data.get('data_notes', []))}")
            
            # Check structure of first row if exists
            rows = data.get("rows", [])
            if rows:
                row = rows[0]
                has_target = "target" in row
                has_actual = "actual" in row
                has_achievement = "achievement" in row
                runner.test("Scorecard row has required fields", 
                           has_target and has_actual and has_achievement,
                           f"target={has_target}, actual={has_actual}, achievement={has_achievement}")
                
                if has_actual:
                    actual = row["actual"]
                    has_three_revenues = all(k in actual for k in ["order_revenue", "session_revenue", "gmv_kpi"])
                    runner.test("Actual has three separate revenue fields", has_three_revenues,
                               f"keys={list(actual.keys())[:5]}")
    except Exception as e:
        runner.test("GET /api/marketing/targets/creator/scorecard", False, f"error: {e}")
    
    # Test Data Import endpoints
    print(f"\n{Colors.YELLOW}[6] DATA IMPORT ENDPOINTS{Colors.RESET}")
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/data-import/source-types", headers=AH, timeout=30)
        runner.test("GET /api/marketing/data-import/source-types", r.status_code == 200, 
                   f"status={r.status_code}")
        if r.status_code == 200:
            data = r.json()
            source_types = data.get("source_types", [])
            runner.test("Source types list exists", len(source_types) > 0, f"found {len(source_types)} types")
            
            # Check for new Shopee types
            keys = [st.get("key") for st in source_types]
            has_shop_kpi = "shopee_shop_kpi" in keys
            has_content_kpi = "shopee_content_kpi" in keys
            has_ads_cpc = "shopee_ads_cpc" in keys
            has_content_perf = "content_performance" in keys
            
            runner.test("Has shopee_shop_kpi source type", has_shop_kpi, f"found={has_shop_kpi}")
            runner.test("Has shopee_content_kpi source type", has_content_kpi, f"found={has_content_kpi}")
            runner.test("Has shopee_ads_cpc source type", has_ads_cpc, f"found={has_ads_cpc}")
            runner.test("Has content_performance source type", has_content_perf, f"found={has_content_perf}")
    except Exception as e:
        runner.test("GET /api/marketing/data-import/source-types", False, f"error: {e}")
    
    # Test import sessions list
    try:
        r = requests.get(f"{BASE_URL}/api/marketing/data-import/sessions", headers=AH, timeout=30)
        runner.test("GET /api/marketing/data-import/sessions", r.status_code == 200, 
                   f"status={r.status_code}")
    except Exception as e:
        runner.test("GET /api/marketing/data-import/sessions", False, f"error: {e}")
    
    # Test Marketing Cycle (for ads budget realization)
    print(f"\n{Colors.YELLOW}[7] MARKETING CYCLE (Budget Realization){Colors.RESET}")
    if account_id:
        try:
            r = requests.get(f"{BASE_URL}/api/marketing/cycle/summary?account_id={account_id}&period=2026-08", 
                           headers=AH, timeout=30)
            runner.test("GET /api/marketing/cycle/summary", r.status_code == 200, 
                       f"status={r.status_code}")
        except Exception as e:
            runner.test("GET /api/marketing/cycle/summary", False, f"error: {e}")
    
    return runner.summary()

if __name__ == "__main__":
    sys.exit(main())
