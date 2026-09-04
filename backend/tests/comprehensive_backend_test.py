"""
CV. Dewi Aditya ERP System - Comprehensive Backend Testing (Opsi A)
====================================================================

Systematic testing of ALL 65 endpoints across 12 business domains:
- AUTH, HEALTH, HR, PRODUCTION, WAREHOUSE, FINANCE, MAKLON, MARKETING,
  ASSETS, APPROVALS, NOTIFICATIONS, PORTAL, COMMUNICATION, COLLAB, RnD,
  KPI, LMS, PROCUREMENT, MANAGEMENT, ANALYTICS, REPORTS, AI-BUSINESS

Login: admin@garment.com / Admin@123
Token field: 'token' (not 'access_token')
All endpoints use /api prefix
"""
import requests
import sys
import json
from datetime import datetime
from typing import Tuple

# Public endpoint from frontend/.env
API = "https://da37-cmt-bridge.preview.emergentagent.com"

class ComprehensiveERPTester:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.failed_tests = []
        self.passed_tests = []
        self.domain_stats = {}

    def log(self, msg, status="INFO"):
        prefix = "✅" if status == "PASS" else "❌" if status == "FAIL" else "🔍"
        print(f"{prefix} {msg}")

    def run_test(self, domain: str, name: str, method: str, endpoint: str, 
                 expected_status: int, data=None, check_keys=None) -> Tuple[bool, dict]:
        """Run a single API test"""
        url = f"{API}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'

        self.tests_run += 1
        
        # Initialize domain stats
        if domain not in self.domain_stats:
            self.domain_stats[domain] = {'total': 0, 'passed': 0, 'failed': 0}
        self.domain_stats[domain]['total'] += 1
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)

            success = response.status_code == expected_status
            
            if success:
                try:
                    resp_data = response.json() if response.text else {}
                    # Check required keys if specified
                    if check_keys:
                        for key in check_keys:
                            if key not in resp_data:
                                self.log(f"[{domain}] {name} - Missing key '{key}'", "FAIL")
                                self.failed_tests.append({
                                    'domain': domain,
                                    'name': name,
                                    'endpoint': endpoint,
                                    'issue': f"Missing key '{key}' in response"
                                })
                                self.domain_stats[domain]['failed'] += 1
                                return False, {}
                    
                    self.tests_passed += 1
                    self.domain_stats[domain]['passed'] += 1
                    self.passed_tests.append(f"[{domain}] {name}")
                    self.log(f"[{domain}] {name} - Status: {response.status_code}", "PASS")
                    return True, resp_data
                except Exception as e:
                    if expected_status == 200:
                        self.log(f"[{domain}] {name} - JSON parse error: {e}", "FAIL")
                        self.failed_tests.append({
                            'domain': domain,
                            'name': name,
                            'endpoint': endpoint,
                            'issue': f"JSON parse error: {e}"
                        })
                        self.domain_stats[domain]['failed'] += 1
                        return False, {}
                    self.tests_passed += 1
                    self.domain_stats[domain]['passed'] += 1
                    self.passed_tests.append(f"[{domain}] {name}")
                    self.log(f"[{domain}] {name} - Status: {response.status_code}", "PASS")
                    return True, {}
            else:
                error_msg = f"Expected {expected_status}, got {response.status_code}"
                self.log(f"[{domain}] {name} - {error_msg}", "FAIL")
                try:
                    error_detail = response.json()
                    self.log(f"Response: {json.dumps(error_detail)[:200]}", "INFO")
                except Exception:
                    self.log(f"Response text: {response.text[:200]}", "INFO")
                
                self.failed_tests.append({
                    'domain': domain,
                    'name': name,
                    'endpoint': endpoint,
                    'issue': error_msg,
                    'status_code': response.status_code
                })
                self.domain_stats[domain]['failed'] += 1
                return False, {}

        except Exception as e:
            self.log(f"[{domain}] {name} - Error: {str(e)}", "FAIL")
            self.failed_tests.append({
                'domain': domain,
                'name': name,
                'endpoint': endpoint,
                'issue': f"Exception: {str(e)}"
            })
            self.domain_stats[domain]['failed'] += 1
            return False, {}

    # ========== AUTH & HEALTH ==========
    
    def test_login(self):
        """Test login with admin credentials"""
        success, response = self.run_test(
            "AUTH",
            "Login (admin@garment.com)",
            "POST",
            "/api/auth/login",
            200,
            data={"email": "admin@garment.com", "password": "Admin@123"},
            check_keys=['token']
        )
        if success and 'token' in response:
            self.token = response['token']
            self.log(f"Token obtained: {self.token[:30]}...", "INFO")
            return True
        return False

    def test_health(self):
        """Test health check endpoint"""
        return self.run_test("HEALTH", "Health Check", "GET", "/api/health", 200)[0]

    # ========== HR DOMAIN (10 endpoints) ==========
    
    def test_hr_employees(self):
        return self.run_test("HR", "List Employees", "GET", "/api/rahaza/employees", 200)[0]
    
    def test_hr_attendance(self):
        return self.run_test("HR", "List Attendance", "GET", "/api/rahaza/attendance", 200)[0]
    
    def test_hr_leaves(self):
        return self.run_test("HR", "List Leaves", "GET", "/api/rahaza/leaves", 200)[0]
    
    def test_hr_leave_balance(self):
        return self.run_test("HR", "Leave Balance", "GET", "/api/rahaza/leaves/balance", 200)[0]
    
    def test_hr_payroll_runs(self):
        return self.run_test("HR", "Payroll Runs", "GET", "/api/rahaza/payroll-runs", 200)[0]
    
    def test_hr_dashboard(self):
        return self.run_test("HR", "HR Dashboard", "GET", "/api/rahaza/hr/dashboard", 200)[0]
    
    def test_hr_inbox(self):
        return self.run_test("HR", "HR Inbox", "GET", "/api/hr/inbox", 200)[0]
    
    def test_hr_shifts(self):
        return self.run_test("HR", "Shifts", "GET", "/api/hr/shifts", 200)[0]
    
    def test_hr_salary_adjustments(self):
        return self.run_test("HR", "Salary Adjustments", "GET", "/api/rahaza/salary-adjustments", 200)[0]
    
    def test_hr_grn_qc(self):
        return self.run_test("HR", "GRN QC Inspections", "GET", "/api/rahaza/grn-qc/grn-inspections", 200)[0]

    # ========== PRODUCTION DOMAIN (7 endpoints) ==========
    
    def test_production_work_orders(self):
        return self.run_test("PRODUCTION", "Work Orders", "GET", "/api/rahaza/work-orders", 200)[0]
    
    def test_production_materials(self):
        return self.run_test("PRODUCTION", "Materials", "GET", "/api/rahaza/materials", 200)[0]
    
    def test_production_material_issues(self):
        return self.run_test("PRODUCTION", "Material Issues", "GET", "/api/rahaza/material-issues", 200)[0]
    
    def test_production_material_returns(self):
        return self.run_test("PRODUCTION", "Material Returns", "GET", "/api/rahaza/production/material-returns", 200)[0]
    
    def test_production_styles(self):
        return self.run_test("PRODUCTION", "Styles", "GET", "/api/rahaza/styles", 200)[0]
    
    def test_production_purchase_orders(self):
        return self.run_test("PRODUCTION", "Purchase Orders", "GET", "/api/rahaza/purchase-orders", 200)[0]
    
    def test_production_execution_board(self):
        return self.run_test("PRODUCTION", "Execution Board", "GET", "/api/rahaza/execution/my-work", 200)[0]

    # ========== WAREHOUSE DOMAIN (6 endpoints) ==========
    
    def test_warehouse_delivery_notes(self):
        return self.run_test("WAREHOUSE", "Delivery Notes", "GET", "/api/wms/delivery-notes", 200)[0]
    
    def test_warehouse_cmt_dispatches(self):
        return self.run_test("WAREHOUSE", "CMT Dispatches", "GET", "/api/wms/cmt-dispatches", 200)[0]
    
    def test_warehouse_opname_sessions(self):
        return self.run_test("WAREHOUSE", "Opname Sessions", "GET", "/api/wms/opname2", 200)[0]
    
    def test_warehouse_fabric_rolls(self):
        return self.run_test("WAREHOUSE", "Fabric Rolls", "GET", "/api/wms/fabric-rolls", 200)[0]
    
    def test_warehouse_picklist(self):
        return self.run_test("WAREHOUSE", "Picklist", "GET", "/api/wms/picklist", 200)[0]
    
    def test_warehouse_positions(self):
        return self.run_test("WAREHOUSE", "Positions", "GET", "/api/wms/positions", 200)[0]
    
    def test_warehouse_legacy_dashboard(self):
        return self.run_test("WAREHOUSE", "Legacy Dashboard", "GET", "/api/wms/legacy/dashboard", 200)[0]

    # ========== FINANCE DOMAIN (6 endpoints) ==========
    
    def test_finance_ar_invoices(self):
        return self.run_test("FINANCE", "AR Invoices", "GET", "/api/rahaza/ar-invoices", 200)[0]
    
    def test_finance_ap_invoices(self):
        return self.run_test("FINANCE", "AP Invoices", "GET", "/api/rahaza/ap-invoices", 200)[0]
    
    def test_finance_budgets(self):
        return self.run_test("FINANCE", "Budgets", "GET", "/api/rahaza/finance/budgets", 200)[0]
    
    def test_finance_budget_summary(self):
        return self.run_test("FINANCE", "Budget Summary", "GET", "/api/rahaza/finance/budget-summary", 200)[0]
    
    def test_finance_bank_recon(self):
        return self.run_test("FINANCE", "Bank Recon Sessions", "GET", "/api/finance/bank-recon/sessions", 200)[0]
    
    def test_finance_3way_match(self):
        return self.run_test("FINANCE", "3-Way Match", "GET", "/api/rahaza/3way-match", 200)[0]

    # ========== MAKLON DOMAIN (5 endpoints) ==========
    
    def test_maklon_clients(self):
        return self.run_test("MAKLON", "Clients", "GET", "/api/dewi/maklon/clients", 200)[0]
    
    def test_maklon_orders(self):
        return self.run_test("MAKLON", "Orders", "GET", "/api/dewi/maklon/orders", 200)[0]
    
    def test_maklon_bom(self):
        return self.run_test("MAKLON", "BOM", "GET", "/api/dewi/maklon/bom", 200)[0]
    
    def test_maklon_cmt_orders(self):
        return self.run_test("MAKLON", "CMT Orders", "GET", "/api/dewi/cmt/orders", 200)[0]
    
    def test_maklon_summary(self):
        return self.run_test("MAKLON", "Summary Dashboard", "GET", "/api/dewi/maklon/summary", 200)[0]

    # ========== MARKETING DOMAIN (4 endpoints) ==========
    
    def test_marketing_accounts(self):
        return self.run_test("MARKETING", "Accounts", "GET", "/api/marketing/accounts", 200)[0]
    
    def test_marketing_kol_creators(self):
        return self.run_test("MARKETING", "KOL Creators", "GET", "/api/marketing/kol/creators", 200)[0]
    
    def test_marketing_catalogs(self):
        return self.run_test("MARKETING", "Catalogs", "GET", "/api/marketing/catalogs", 200)[0]
    
    def test_marketing_livehost(self):
        return self.run_test("MARKETING", "Livehost", "GET", "/api/marketing/livehost", 200)[0]

    # ========== ASSETS DOMAIN (3 endpoints) ==========
    
    def test_assets_list(self):
        return self.run_test("ASSETS", "List Assets", "GET", "/api/assets", 200)[0]
    
    def test_assets_dashboard(self):
        return self.run_test("ASSETS", "Dashboard", "GET", "/api/assets/dashboard", 200)[0]
    
    def test_assets_categories(self):
        return self.run_test("ASSETS", "Categories", "GET", "/api/assets/categories", 200)[0]

    # ========== APPROVALS DOMAIN (3 endpoints) ==========
    
    def test_approvals_chains(self):
        return self.run_test("APPROVALS", "Approval Chains", "GET", "/api/approvals/chains", 200)[0]
    
    def test_approvals_pending(self):
        return self.run_test("APPROVALS", "Pending Approvals", "GET", "/api/approvals/pending", 200)[0]
    
    def test_approvals_summary(self):
        return self.run_test("APPROVALS", "Approval Summary", "GET", "/api/approvals/summary", 200)[0]

    # ========== NOTIFICATIONS DOMAIN (2 endpoints) ==========
    
    def test_notifications_unified(self):
        return self.run_test("NOTIFICATIONS", "Unified Notifications", "GET", "/api/notifications/unified", 200)[0]
    
    def test_notifications_stats(self):
        return self.run_test("NOTIFICATIONS", "Notification Stats", "GET", "/api/notifications/unified/stats", 200)[0]

    # ========== PORTAL DOMAIN (2 endpoints) ==========
    
    def test_portal_profile(self):
        return self.run_test("PORTAL", "Employee Profile", "GET", "/api/portal-saya/profile", 200)[0]
    
    def test_portal_attendance(self):
        return self.run_test("PORTAL", "My Attendance", "GET", "/api/portal-saya/attendance", 200)[0]

    # ========== OTHER DOMAINS (1 endpoint each) ==========
    
    def test_communication_channels(self):
        return self.run_test("COMMUNICATION", "Channels", "GET", "/api/comm/channels", 200)[0]
    
    def test_collab_workspaces(self):
        return self.run_test("COLLAB", "Workspaces", "GET", "/api/collab/workspaces", 200)[0]
    
    def test_rnd_analytics(self):
        return self.run_test("RnD", "Analytics", "GET", "/api/dewi/rnd/analytics", 200)[0]
    
    def test_rnd_hpp(self):
        return self.run_test("RnD", "HPP Calculator", "GET", "/api/dewi/rnd/hpp-calculator", 200)[0]
    
    def test_kpi_periods(self):
        return self.run_test("KPI", "KPI Periods", "GET", "/api/dewi/kpi/periods", 200)[0]
    
    def test_lms_courses(self):
        return self.run_test("LMS", "Courses", "GET", "/api/dewi/lms/courses", 200)[0]
    
    def test_procurement_pr(self):
        return self.run_test("PROCUREMENT", "Purchase Requests", "GET", "/api/procurement/purchase-requests", 200)[0]
    
    def test_management_dashboard(self):
        return self.run_test("MANAGEMENT", "Dashboard", "GET", "/api/management/dashboard", 200)[0]
    
    def test_analytics_dashboard(self):
        return self.run_test("ANALYTICS", "Dashboard", "GET", "/api/analytics/dashboard", 200)[0]
    
    def test_reports_list(self):
        return self.run_test("REPORTS", "List Reports", "GET", "/api/reports/list", 200)[0]
    
    def test_ai_business_dashboard(self):
        return self.run_test("AI-BUSINESS", "Dashboard", "GET", "/api/ai-business/dashboard", 200)[0]

    # ========== MULTI-LEVEL APPROVAL TEST ==========
    
    def test_approval_create_request(self):
        return self.run_test(
            "APPROVALS",
            "Create Test Approval Request",
            "POST",
            "/api/approvals/requests",
            200,
            data={
                "domain": "leave",
                "ref_id": "test123",
                "title": "Test Leave"
            }
        )[0]

    # ========== SUMMARY ==========

    def print_summary(self):
        """Print comprehensive test summary"""
        print("\n" + "="*80)
        print("  CV. Dewi Aditya ERP - Comprehensive Backend Test Summary")
        print("="*80)
        print(f"  Total Tests:  {self.tests_run}")
        print(f"  Passed:       {self.tests_passed} ({(self.tests_passed/self.tests_run*100):.1f}%)")
        print(f"  Failed:       {len(self.failed_tests)} ({(len(self.failed_tests)/self.tests_run*100):.1f}%)")
        print("="*80)
        
        # Domain-wise breakdown
        print("\n📊 Domain-wise Results:")
        print("-"*80)
        for domain, stats in sorted(self.domain_stats.items()):
            success_rate = (stats['passed'] / stats['total'] * 100) if stats['total'] > 0 else 0
            status = "✅" if stats['failed'] == 0 else "⚠️" if success_rate >= 50 else "❌"
            print(f"{status} {domain:20s} | Total: {stats['total']:2d} | Passed: {stats['passed']:2d} | Failed: {stats['failed']:2d} | Rate: {success_rate:5.1f}%")
        
        # Failed tests detail
        if self.failed_tests:
            print("\n❌ Failed Tests Detail:")
            print("-"*80)
            for i, test in enumerate(self.failed_tests, 1):
                print(f"{i}. [{test['domain']}] {test['name']}")
                print(f"   Endpoint: {test['endpoint']}")
                print(f"   Issue: {test['issue']}")
                if 'status_code' in test:
                    print(f"   Status Code: {test['status_code']}")
                print()
        
        print("="*80)
        return 0 if len(self.failed_tests) == 0 else 1


def main():
    tester = ComprehensiveERPTester()
    
    print("="*80)
    print("  CV. Dewi Aditya ERP System - Comprehensive Backend Testing (Opsi A)")
    print("="*80)
    print(f"  API Endpoint: {API}")
    print(f"  Test Time:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Credentials:  admin@garment.com / Admin@123")
    print("="*80)
    print()

    # 1. AUTH & HEALTH
    print("\n" + "="*80)
    print("  1. AUTH & HEALTH (2 tests)")
    print("="*80)
    if not tester.test_login():
        print("\n❌ Login failed, stopping tests")
        return 1
    tester.test_health()

    # 2. HR DOMAIN
    print("\n" + "="*80)
    print("  2. HR DOMAIN (10 tests)")
    print("="*80)
    tester.test_hr_employees()
    tester.test_hr_attendance()
    tester.test_hr_leaves()
    tester.test_hr_leave_balance()
    tester.test_hr_payroll_runs()
    tester.test_hr_dashboard()
    tester.test_hr_inbox()
    tester.test_hr_shifts()
    tester.test_hr_salary_adjustments()
    tester.test_hr_grn_qc()

    # 3. PRODUCTION DOMAIN
    print("\n" + "="*80)
    print("  3. PRODUCTION DOMAIN (7 tests)")
    print("="*80)
    tester.test_production_work_orders()
    tester.test_production_materials()
    tester.test_production_material_issues()
    tester.test_production_material_returns()
    tester.test_production_styles()
    tester.test_production_purchase_orders()
    tester.test_production_execution_board()

    # 4. WAREHOUSE DOMAIN
    print("\n" + "="*80)
    print("  4. WAREHOUSE DOMAIN (7 tests)")
    print("="*80)
    tester.test_warehouse_delivery_notes()
    tester.test_warehouse_cmt_dispatches()
    tester.test_warehouse_opname_sessions()
    tester.test_warehouse_fabric_rolls()
    tester.test_warehouse_picklist()
    tester.test_warehouse_positions()
    tester.test_warehouse_legacy_dashboard()

    # 5. FINANCE DOMAIN
    print("\n" + "="*80)
    print("  5. FINANCE DOMAIN (6 tests)")
    print("="*80)
    tester.test_finance_ar_invoices()
    tester.test_finance_ap_invoices()
    tester.test_finance_budgets()
    tester.test_finance_budget_summary()
    tester.test_finance_bank_recon()
    tester.test_finance_3way_match()

    # 6. MAKLON DOMAIN
    print("\n" + "="*80)
    print("  6. MAKLON DOMAIN (5 tests)")
    print("="*80)
    tester.test_maklon_clients()
    tester.test_maklon_orders()
    tester.test_maklon_bom()
    tester.test_maklon_cmt_orders()
    tester.test_maklon_summary()

    # 7. MARKETING DOMAIN
    print("\n" + "="*80)
    print("  7. MARKETING DOMAIN (4 tests)")
    print("="*80)
    tester.test_marketing_accounts()
    tester.test_marketing_kol_creators()
    tester.test_marketing_catalogs()
    tester.test_marketing_livehost()

    # 8. ASSETS DOMAIN
    print("\n" + "="*80)
    print("  8. ASSETS DOMAIN (3 tests)")
    print("="*80)
    tester.test_assets_list()
    tester.test_assets_dashboard()
    tester.test_assets_categories()

    # 9. APPROVALS DOMAIN
    print("\n" + "="*80)
    print("  9. APPROVALS DOMAIN (4 tests)")
    print("="*80)
    tester.test_approvals_chains()
    tester.test_approvals_pending()
    tester.test_approvals_summary()
    tester.test_approval_create_request()

    # 10. NOTIFICATIONS DOMAIN
    print("\n" + "="*80)
    print("  10. NOTIFICATIONS DOMAIN (2 tests)")
    print("="*80)
    tester.test_notifications_unified()
    tester.test_notifications_stats()

    # 11. PORTAL DOMAIN
    print("\n" + "="*80)
    print("  11. PORTAL DOMAIN (2 tests)")
    print("="*80)
    tester.test_portal_profile()
    tester.test_portal_attendance()

    # 12. OTHER DOMAINS
    print("\n" + "="*80)
    print("  12. OTHER DOMAINS (11 tests)")
    print("="*80)
    tester.test_communication_channels()
    tester.test_collab_workspaces()
    tester.test_rnd_analytics()
    tester.test_rnd_hpp()
    tester.test_kpi_periods()
    tester.test_lms_courses()
    tester.test_procurement_pr()
    tester.test_management_dashboard()
    tester.test_analytics_dashboard()
    tester.test_reports_list()
    tester.test_ai_business_dashboard()

    # Print summary
    return tester.print_summary()


if __name__ == "__main__":
    sys.exit(main())
