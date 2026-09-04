#!/usr/bin/env python3
"""
Backend API Testing Script for Session #17
Tests BACKLOG-A..E + RC-12 + regression smoke tests
"""
import requests
import json
import sys
from datetime import datetime

# Backend URL from environment
BACKEND_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Global token storage
TOKEN = None

def login():
    """Login and get auth token"""
    global TOKEN
    print("🔐 Logging in as admin...")
    resp = requests.post(f"{BACKEND_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} - {resp.text}")
        sys.exit(1)
    data = resp.json()
    TOKEN = data.get("token") or data.get("access_token")
    if not TOKEN:
        print(f"❌ No token in response: {data}")
        sys.exit(1)
    print(f"✅ Login successful")
    return TOKEN

def headers():
    """Return auth headers"""
    return {"Authorization": f"Bearer {TOKEN}"}

def test_result(name, passed, details=""):
    """Print test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status} | {name}")
    if details:
        print(f"    {details}")
    return passed

# ============================================================================
# A. BACKLOG-B — HR Shifts canonical (rahaza_shifts)
# ============================================================================

def test_backlog_b():
    """Test HR Shifts with canonical rahaza_shifts collection"""
    print("\n" + "="*80)
    print("A. BACKLOG-B — HR Shifts Canonical (rahaza_shifts)")
    print("="*80)
    
    results = []
    
    # A.1 - GET /api/hr/shifts → 200, items with DEFAULT + 4 canonical shifts
    print("\nA.1 - GET /api/hr/shifts (list all shifts)")
    resp = requests.get(f"{BACKEND_URL}/hr/shifts", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        items = data.get("data", [])
        # Check for DEFAULT + 4 canonical (OFF/S1/S2/S3)
        shift_codes = [s.get("shift_code") for s in items]
        has_default = "DEFAULT" in shift_codes
        has_off = "OFF" in shift_codes
        has_s1 = "S1" in shift_codes
        has_s2 = "S2" in shift_codes
        has_s3 = "S3" in shift_codes
        
        # Check each shift has required fields
        all_have_fields = all(
            s.get("shift_code") and s.get("shift_name") and 
            s.get("start_time") and s.get("effective_hours") is not None
            for s in items
        )
        
        passed = (has_default and has_off and has_s1 and has_s2 and has_s3 and all_have_fields)
        results.append(test_result(
            "A.1 GET /api/hr/shifts → DEFAULT + 4 canonical shifts (OFF/S1/S2/S3)",
            passed,
            f"Found shifts: {shift_codes}, all_have_fields={all_have_fields}"
        ))
    else:
        results.append(test_result("A.1 GET /api/hr/shifts", False, f"Status: {resp.status_code}"))
    
    # A.2 - GET /api/hr/shifts/summary → total_shifts=4 (canonical only, before seed-defaults)
    print("\nA.2 - GET /api/hr/shifts/summary")
    resp = requests.get(f"{BACKEND_URL}/hr/shifts/summary", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        summary = data.get("data", {})
        total_shifts = summary.get("total_shifts", 0)
        # After seed-defaults may have been called, we expect 4 canonical + 5 defaults = 9
        # But initially should be 4. Let's check if >= 4
        passed = total_shifts >= 4
        results.append(test_result(
            "A.2 GET /api/hr/shifts/summary → total_shifts >= 4",
            passed,
            f"total_shifts={total_shifts}"
        ))
    else:
        results.append(test_result("A.2 GET /api/hr/shifts/summary", False, f"Status: {resp.status_code}"))
    
    # A.3 - POST /api/hr/shifts (create TESTX) - use unique code
    print("\nA.3 - POST /api/hr/shifts (create shift TESTX)")
    test_shift_id = None
    
    # Use timestamp to make shift code unique
    import time
    test_code = f"TESTX{int(time.time()) % 10000}"
    
    resp = requests.post(f"{BACKEND_URL}/hr/shifts", headers=headers(), json={
        "shift_code": test_code,
        "shift_name": "Shift Test X",
        "start_time": "06:00",
        "end_time": "14:00",
        "break_duration_minutes": 60,
        "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri"],
        "is_overnight": False,
        "color": "#FF5733"
    })
    if resp.status_code == 200:
        data = resp.json()
        shift_data = data.get("data", {})
        test_shift_id = shift_data.get("id")
        results.append(test_result(
            "A.3 POST /api/hr/shifts (create TESTX)",
            True,
            f"Created shift_id={test_shift_id}, code={test_code}"
        ))
    else:
        results.append(test_result("A.3 POST /api/hr/shifts", False, f"Status: {resp.status_code}, Response: {resp.text[:200]}"))
    
    # A.4 - GET /api/hr/shifts → TESTX appears
    if test_shift_id:
        print(f"\nA.4 - GET /api/hr/shifts (verify {test_code} appears)")
        resp = requests.get(f"{BACKEND_URL}/hr/shifts", headers=headers())
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            shift_codes = [s.get("shift_code") for s in items]
            has_test = test_code in shift_codes
            results.append(test_result(
                f"A.4 GET /api/hr/shifts → {test_code} appears",
                has_test,
                f"shift_codes={shift_codes}"
            ))
        else:
            results.append(test_result("A.4 GET /api/hr/shifts", False, f"Status: {resp.status_code}"))
        
        # A.5 - DELETE /api/hr/shifts/{id}
        print(f"\nA.5 - DELETE /api/hr/shifts/{test_shift_id}")
        resp = requests.delete(f"{BACKEND_URL}/hr/shifts/{test_shift_id}", headers=headers())
        if resp.status_code == 200:
            results.append(test_result("A.5 DELETE /api/hr/shifts/{id}", True))
        else:
            results.append(test_result("A.5 DELETE /api/hr/shifts/{id}", False, f"Status: {resp.status_code}"))
        
        # A.6 - GET /api/hr/shifts (status=active) → test shift not present, 4 canonical still there
        print(f"\nA.6 - GET /api/hr/shifts?status=active (verify {test_code} deleted, 4 canonical remain)")
        resp = requests.get(f"{BACKEND_URL}/hr/shifts?status=active", headers=headers())
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("data", [])
            shift_codes = [s.get("shift_code") for s in items if s.get("shift_code") != "DEFAULT"]
            has_test = test_code in shift_codes
            has_off = "OFF" in shift_codes
            has_s1 = "S1" in shift_codes
            has_s2 = "S2" in shift_codes
            has_s3 = "S3" in shift_codes
            passed = (not has_test and has_off and has_s1 and has_s2 and has_s3)
            results.append(test_result(
                f"A.6 GET /api/hr/shifts?status=active → {test_code} deleted, 4 canonical remain",
                passed,
                f"shift_codes={shift_codes}, has_test={has_test}"
            ))
        else:
            results.append(test_result("A.6 GET /api/hr/shifts?status=active", False, f"Status: {resp.status_code}"))
    
    # A.7 - POST /api/hr/shifts/seed-defaults → 200, no deletion of canonical
    print("\nA.7 - POST /api/hr/shifts/seed-defaults (idempotent, no deletion)")
    resp = requests.post(f"{BACKEND_URL}/hr/shifts/seed-defaults", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        message = data.get("message", "")
        results.append(test_result(
            "A.7 POST /api/hr/shifts/seed-defaults",
            True,
            f"message={message}"
        ))
        
        # Verify 4 canonical + 5 default templates exist
        resp2 = requests.get(f"{BACKEND_URL}/hr/shifts", headers=headers())
        if resp2.status_code == 200:
            data2 = resp2.json()
            items2 = data2.get("data", [])
            shift_codes2 = [s.get("shift_code") for s in items2 if s.get("shift_code") != "DEFAULT"]
            # Should have OFF/S1/S2/S3 + PAGI/SIANG/MALAM/NORMAL/FLEKSIBEL (or similar)
            has_canonical = all(c in shift_codes2 for c in ["OFF", "S1", "S2", "S3"])
            results.append(test_result(
                "A.7 Verify canonical shifts still present after seed-defaults",
                has_canonical,
                f"shift_codes={shift_codes2}"
            ))
    else:
        results.append(test_result("A.7 POST /api/hr/shifts/seed-defaults", False, f"Status: {resp.status_code}"))
    
    # A.8 - Regression: GET /api/reports/executive/summary (HR section)
    print("\nA.8 - Regression: GET /api/reports/executive/summary?year=2026&month=5")
    resp = requests.get(f"{BACKEND_URL}/reports/executive/summary?year=2026&month=5", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        hr_data = data.get("hr", {})
        attendance_rate = hr_data.get("attendance_rate_pct", 0)
        passed = attendance_rate > 0
        results.append(test_result(
            "A.8 Regression: HR summary attendance_rate_pct > 0",
            passed,
            f"attendance_rate_pct={attendance_rate}"
        ))
    else:
        results.append(test_result("A.8 GET /api/reports/executive/summary", False, f"Status: {resp.status_code}"))
    
    return results

# ============================================================================
# B. BACKLOG-C — Archive CMT legacy routers
# ============================================================================

def test_backlog_c():
    """Test archived CMT legacy routers return 404"""
    print("\n" + "="*80)
    print("B. BACKLOG-C — Archive CMT Legacy Routers")
    print("="*80)
    
    results = []
    
    # B.1 - GET /api/dewi/cmt/jobs → 404
    print("\nB.1 - GET /api/dewi/cmt/jobs → 404 (archived)")
    resp = requests.get(f"{BACKEND_URL}/dewi/cmt/jobs", headers=headers())
    passed = resp.status_code == 404
    results.append(test_result(
        "B.1 GET /api/dewi/cmt/jobs → 404",
        passed,
        f"Status: {resp.status_code}"
    ))
    
    # B.2 - GET /api/dewi/cmt/delivery-orders → 404
    print("\nB.2 - GET /api/dewi/cmt/delivery-orders → 404 (archived)")
    resp = requests.get(f"{BACKEND_URL}/dewi/cmt/delivery-orders", headers=headers())
    passed = resp.status_code == 404
    results.append(test_result(
        "B.2 GET /api/dewi/cmt/delivery-orders → 404",
        passed,
        f"Status: {resp.status_code}"
    ))
    
    # B.3 - GET /api/dewi/reports/daily → 200 (phase7 still works)
    print("\nB.3 - GET /api/dewi/reports/daily → 200 (phase7 still active)")
    resp = requests.get(f"{BACKEND_URL}/dewi/reports/daily", headers=headers())
    passed = resp.status_code == 200
    results.append(test_result(
        "B.3 GET /api/dewi/reports/daily → 200",
        passed,
        f"Status: {resp.status_code}"
    ))
    
    # B.4 - GET /api/dewi/cmt/lifecycle/summary → 200 (lifecycle still active)
    print("\nB.4 - GET /api/dewi/cmt/lifecycle/summary → 200 (lifecycle still active)")
    resp = requests.get(f"{BACKEND_URL}/dewi/cmt/lifecycle/summary", headers=headers())
    passed = resp.status_code == 200
    results.append(test_result(
        "B.4 GET /api/dewi/cmt/lifecycle/summary → 200",
        passed,
        f"Status: {resp.status_code}"
    ))
    
    # B.5 - GET /api/prod/cmt-receipts/summary → 200 (packing still active)
    print("\nB.5 - GET /api/prod/cmt-receipts/summary → 200 (packing still active)")
    resp = requests.get(f"{BACKEND_URL}/prod/cmt-receipts/summary", headers=headers())
    passed = resp.status_code == 200
    results.append(test_result(
        "B.5 GET /api/prod/cmt-receipts/summary → 200",
        passed,
        f"Status: {resp.status_code}"
    ))
    
    return results

# ============================================================================
# C. BACKLOG-D — Onboarding canonical
# ============================================================================

def test_backlog_d():
    """Test onboarding templates and checklists"""
    print("\n" + "="*80)
    print("C. BACKLOG-D — Onboarding Canonical")
    print("="*80)
    
    results = []
    
    # C.1 - GET /api/dewi/onboarding/templates → >= 1 template
    print("\nC.1 - GET /api/dewi/onboarding/templates → >= 1 template")
    resp = requests.get(f"{BACKEND_URL}/dewi/onboarding/templates", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        templates = data.get("templates", [])
        passed = len(templates) >= 1
        results.append(test_result(
            "C.1 GET /api/dewi/onboarding/templates → >= 1 template",
            passed,
            f"Found {len(templates)} template(s)"
        ))
    else:
        results.append(test_result("C.1 GET /api/dewi/onboarding/templates", False, f"Status: {resp.status_code}"))
    
    # C.2 - GET /api/dewi/onboarding/checklists → total=3, items have tasks[] and progress_pct
    print("\nC.2 - GET /api/dewi/onboarding/checklists → total=3, items have tasks[] and progress_pct")
    resp = requests.get(f"{BACKEND_URL}/dewi/onboarding/checklists", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        checklists = data.get("checklists", [])
        total = len(checklists)
        
        # Check each checklist has tasks[] and progress_pct
        all_have_fields = all(
            isinstance(c.get("tasks"), list) and 
            c.get("progress_pct") is not None
            for c in checklists
        )
        
        passed = (total == 3 and all_have_fields)
        results.append(test_result(
            "C.2 GET /api/dewi/onboarding/checklists → total=3, all have tasks[] and progress_pct",
            passed,
            f"total={total}, all_have_fields={all_have_fields}"
        ))
    else:
        results.append(test_result("C.2 GET /api/dewi/onboarding/checklists", False, f"Status: {resp.status_code}"))
    
    return results

# ============================================================================
# D. RC-12(1a) — payroll_entries phantom write removed
# ============================================================================

def test_rc12():
    """Test payroll_entries phantom write removed"""
    print("\n" + "="*80)
    print("D. RC-12(1a) — Payroll Entries Phantom Write Removed")
    print("="*80)
    
    results = []
    
    # D.1 - POST /api/marketing/livehost/payment/sync-to-finance (note: singular 'payment')
    print("\nD.1 - POST /api/marketing/livehost/payment/sync-to-finance?month=2026-06")
    resp = requests.post(f"{BACKEND_URL}/marketing/livehost/payment/sync-to-finance?month=2026-06", headers=headers())
    # Should be 200 with message (no payments to sync is OK) or 200 with synced data
    # Should NOT be 500
    passed = resp.status_code == 200
    if resp.status_code == 200:
        data = resp.json()
        message = data.get("message", "")
        results.append(test_result(
            "D.1 POST /api/marketing/livehost/payment/sync-to-finance → 200 (not 500)",
            True,
            f"message={message}"
        ))
    else:
        results.append(test_result(
            "D.1 POST /api/marketing/livehost/payment/sync-to-finance",
            False,
            f"Status: {resp.status_code}"
        ))
    
    # D.2 - Smoke: GET /api/marketing/livehost
    print("\nD.2 - Smoke: GET /api/marketing/livehost → 200")
    resp = requests.get(f"{BACKEND_URL}/marketing/livehost", headers=headers())
    passed = resp.status_code == 200
    results.append(test_result(
        "D.2 GET /api/marketing/livehost → 200",
        passed,
        f"Status: {resp.status_code}"
    ))
    
    return results

# ============================================================================
# E. RC-15 expansion — live analytics
# ============================================================================

def test_rc15():
    """Test live analytics expansion"""
    print("\n" + "="*80)
    print("E. RC-15 Expansion — Live Analytics")
    print("="*80)
    
    results = []
    
    # E.1 - GET /api/marketing/live/analytics/overview?days=90
    print("\nE.1 - GET /api/marketing/live/analytics/overview?days=90")
    resp = requests.get(f"{BACKEND_URL}/marketing/live/analytics/overview?days=90", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        kpi = data.get("kpi", {})
        total_revenue = kpi.get("total_revenue_rp", 0)
        total_sessions = kpi.get("total_sessions", 0)
        total_orders = kpi.get("total_orders", 0)
        
        passed = (total_revenue > 100_000_000 and total_sessions > 0 and total_orders > 0)
        results.append(test_result(
            "E.1 GET /api/marketing/live/analytics/overview → revenue > 100M, sessions > 0, orders > 0",
            passed,
            f"revenue={total_revenue:,.0f}, sessions={total_sessions}, orders={total_orders}"
        ))
    else:
        results.append(test_result("E.1 GET /api/marketing/live/analytics/overview", False, f"Status: {resp.status_code}"))
    
    # E.2 - Regression: GET /api/marketing/live/summary
    print("\nE.2 - Regression: GET /api/marketing/live/summary → 200, total_revenue > 0")
    resp = requests.get(f"{BACKEND_URL}/marketing/live/summary", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        # Response structure: {"success": true, "data": {"total_revenue": ...}}
        data_obj = data.get("data", {})
        total_revenue = data_obj.get("total_revenue", 0)
        passed = total_revenue > 0
        results.append(test_result(
            "E.2 GET /api/marketing/live/summary → total_revenue > 0",
            passed,
            f"total_revenue={total_revenue:,.0f}"
        ))
    else:
        results.append(test_result("E.2 GET /api/marketing/live/summary", False, f"Status: {resp.status_code}"))
    
    return results

# ============================================================================
# F. Regression Smoke Tests
# ============================================================================

def test_regression_smoke():
    """Test regression smoke tests"""
    print("\n" + "="*80)
    print("F. Regression Smoke Tests")
    print("="*80)
    
    results = []
    
    # F.1 - GET /api/health
    print("\nF.1 - GET /api/health → ok")
    resp = requests.get(f"{BACKEND_URL}/health")
    if resp.status_code == 200:
        data = resp.json()
        status = data.get("status", "")
        passed = status == "ok"
        results.append(test_result(
            "F.1 GET /api/health → ok",
            passed,
            f"status={status}"
        ))
    else:
        results.append(test_result("F.1 GET /api/health", False, f"Status: {resp.status_code}"))
    
    # F.2 - GET /api/rahaza/leave-balances
    print("\nF.2 - GET /api/rahaza/leave-balances → 200, 50+ balances")
    resp = requests.get(f"{BACKEND_URL}/rahaza/leave-balances", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        # Response structure: {"ok": true, "balances": [...]}
        balances = data.get("balances", [])
        passed = len(balances) >= 50
        results.append(test_result(
            "F.2 GET /api/rahaza/leave-balances → 50+ balances",
            passed,
            f"Found {len(balances)} balances"
        ))
    else:
        results.append(test_result("F.2 GET /api/rahaza/leave-balances", False, f"Status: {resp.status_code}"))
    
    # F.3 - GET /api/dashboard
    print("\nF.3 - GET /api/dashboard → totalRevenue > 0")
    resp = requests.get(f"{BACKEND_URL}/dashboard", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        total_revenue = data.get("totalRevenue", 0)
        passed = total_revenue > 0
        results.append(test_result(
            "F.3 GET /api/dashboard → totalRevenue > 0",
            passed,
            f"totalRevenue={total_revenue:,.0f}"
        ))
    else:
        results.append(test_result("F.3 GET /api/dashboard", False, f"Status: {resp.status_code}"))
    
    # F.4 - GET /api/portal/dashboard
    print("\nF.4 - GET /api/portal/dashboard → is_linked=true")
    resp = requests.get(f"{BACKEND_URL}/portal/dashboard", headers=headers())
    if resp.status_code == 200:
        data = resp.json()
        is_linked = data.get("is_linked", False)
        passed = is_linked == True
        results.append(test_result(
            "F.4 GET /api/portal/dashboard → is_linked=true",
            passed,
            f"is_linked={is_linked}"
        ))
    else:
        results.append(test_result("F.4 GET /api/portal/dashboard", False, f"Status: {resp.status_code}"))
    
    return results

# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    print("="*80)
    print("SESSION #17 BACKEND API TESTING")
    print("="*80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Time: {datetime.now().isoformat()}")
    print("="*80)
    
    # Login
    login()
    
    # Run all test suites
    all_results = []
    
    all_results.extend(test_backlog_b())
    all_results.extend(test_backlog_c())
    all_results.extend(test_backlog_d())
    all_results.extend(test_rc12())
    all_results.extend(test_rc15())
    all_results.extend(test_regression_smoke())
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    total = len(all_results)
    passed = sum(1 for r in all_results if r)
    failed = total - passed
    pass_rate = (passed / total * 100) if total > 0 else 0
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Pass Rate: {pass_rate:.1f}%")
    print("="*80)
    
    # Exit with appropriate code
    sys.exit(0 if failed == 0 else 1)

if __name__ == "__main__":
    main()
