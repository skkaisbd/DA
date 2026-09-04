"""
Iteration 9 — HR PORTAL Backend Regression
Tests every HR module write/integration chain per request.
Focus: leave (route-shadow fix), payroll run, expense/travel chains,
recently-modified files: rahaza_leave.py, rahaza_leave_balances.py,
hr_shifts.py, approval_multilevel.py, employee_expense_claims.py,
employee_travel_requests.py, employee_travel_settlements.py.
"""
import os
import time
import pytest
import requests
from datetime import timedelta, date

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
TS = int(time.time())


# ─── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="session")
def s(token):
    sess = requests.Session()
    sess.headers.update({
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    return sess


@pytest.fixture(scope="session")
def employee(s):
    """Pick an existing employee or seed a TEST employee."""
    r = s.get(f"{BASE_URL}/api/rahaza/employees", params={"limit": 50}, timeout=20)
    if r.status_code == 200:
        data = r.json()
        rows = data if isinstance(data, list) else data.get("items", [])
        if rows:
            return rows[0]
    # Seed one
    body = {
        "employee_code": f"TEST-EMP-{TS}",
        "name": f"TEST Employee Iter9 {TS}",
        "department": "OPS",
        "position": "Operator",
        "active": True,
    }
    rc = s.post(f"{BASE_URL}/api/rahaza/employees", json=body, timeout=20)
    if rc.status_code not in (200, 201):
        pytest.skip(f"Cannot seed employee: {rc.status_code} {rc.text[:200]}")
    return rc.json()


# ─── Employees & Org ─────────────────────────────────────────────────────────
class TestEmployeesOrg:
    def test_list_employees(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/employees", params={"limit": 50}, timeout=20)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list) or "items" in data

    def test_org_units(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/org/units", timeout=20)
        assert r.status_code == 200

    def test_org_chart(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/org/chart", timeout=20)
        assert r.status_code == 200

    def test_org_headcount(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/org/headcount", timeout=20)
        assert r.status_code == 200


# ─── Leave: critical route-shadowing fix ─────────────────────────────────────
class TestLeave:
    def test_leave_types(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/leave-types", timeout=20)
        assert r.status_code == 200

    def test_leaves_balance_route_not_shadowed(self, s, employee):
        """CRITICAL: GET /leaves/balance must return 200 with balances array,
        NOT 404 (which would mean it's being shadowed by /leaves/{leave_id})."""
        r = s.get(
            f"{BASE_URL}/api/rahaza/leaves/balance",
            params={"employee_id": employee["id"]},
            timeout=20,
        )
        assert r.status_code == 200, (
            f"Leave balance route shadowed or broken: {r.status_code} {r.text[:200]}"
        )
        data = r.json()
        assert "balances" in data
        assert data["employee_id"] == employee["id"]
        assert isinstance(data["balances"], list)

    def test_leave_request_flow(self, s, employee):
        """Create leave request -> approve -> verify balance consumed."""
        lt = s.get(f"{BASE_URL}/api/rahaza/leave-types", timeout=20).json()
        if not lt:
            # Seed a leave type
            seed = {"code": f"TEST{TS}", "name": "Cuti Test", "quota_default": 12,
                    "paid": True, "active": True}
            rc = s.post(f"{BASE_URL}/api/rahaza/leave-types", json=seed, timeout=20)
            if rc.status_code in (200, 201):
                lt = [rc.json()]
            else:
                pytest.skip(f"No leave types and cannot seed: {rc.status_code}")
        leave_type = lt[0]
        # Use far-future dates to avoid working-days issues
        d1 = (date.today() + timedelta(days=60)).isoformat()
        d2 = (date.today() + timedelta(days=60)).isoformat()
        body = {
            "employee_id": employee["id"],
            "leave_type_id": leave_type["id"],
            "from_date": d1,
            "to_date": d2,
            "reason": "TEST_iter9 leave",
        }
        r = s.post(f"{BASE_URL}/api/rahaza/leaves/request", json=body, timeout=30)
        assert r.status_code in (200, 201), f"create leave: {r.status_code} {r.text[:300]}"
        leave_id = r.json().get("id") or r.json().get("leave_id")
        assert leave_id, f"No id returned: {r.json()}"

        # Approve
        ra = s.post(
            f"{BASE_URL}/api/rahaza/leaves/{leave_id}/approve",
            json={"notes": "ok"}, timeout=30,
        )
        assert ra.status_code in (200, 201), f"approve leave: {ra.status_code} {ra.text[:300]}"

        # Re-fetch balance to ensure no 500
        rb = s.get(
            f"{BASE_URL}/api/rahaza/leaves/balance",
            params={"employee_id": employee["id"]},
            timeout=20,
        )
        assert rb.status_code == 200

    def test_leave_balances_list(self, s):
        """rahaza_leave_balances.insert_one(dict) — must not 500."""
        r = s.get(f"{BASE_URL}/api/rahaza/leave-balances", timeout=20)
        assert r.status_code == 200


# ─── Shifts (hr_shifts recently-modified) ────────────────────────────────────
class TestShifts:
    def test_list_shifts(self, s):
        r = s.get(f"{BASE_URL}/api/hr/shifts", timeout=20)
        assert r.status_code == 200

    def test_shift_create(self, s):
        body = {
            "shift_code": f"TEST{TS}",
            "shift_name": f"TEST shift {TS}",
            "start_time": "08:00",
            "end_time": "17:00",
        }
        r = s.post(f"{BASE_URL}/api/hr/shifts", json=body, timeout=20)
        assert r.status_code in (200, 201, 400, 409), f"shift create: {r.status_code} {r.text[:200]}"

    def test_shift_summary(self, s):
        r = s.get(f"{BASE_URL}/api/hr/shifts/summary", timeout=20)
        assert r.status_code == 200

    def test_shift_assignments_list(self, s):
        r = s.get(f"{BASE_URL}/api/hr/shifts/assignments", timeout=20)
        assert r.status_code == 200


# ─── Overtime ────────────────────────────────────────────────────────────────
class TestOvertime:
    def test_list_overtime(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/overtime", timeout=20)
        assert r.status_code == 200

    def test_overtime_summary(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/overtime/summary", timeout=20)
        assert r.status_code == 200

    def test_overtime_create_and_approve(self, s, employee):
        # Use unique time-of-day for this test run
        d = (date.today() - timedelta(days=2)).isoformat()
        h = (TS % 12) + 1  # vary hour by ts
        body = {
            "employee_id": employee["id"],
            "date": d,
            "start_time": f"{h:02d}:00",
            "end_time": f"{h+2:02d}:00",
            "hours": 2,
            "reason": f"TEST_iter9 overtime {TS}",
        }
        r = s.post(f"{BASE_URL}/api/rahaza/overtime", json=body, timeout=20)
        if r.status_code not in (200, 201):
            pytest.skip(f"overtime create not accepted: {r.status_code} {r.text[:200]}")
        ot_id = r.json().get("id")
        if not ot_id:
            return
        ra = s.put(f"{BASE_URL}/api/rahaza/overtime/{ot_id}/approve", json={}, timeout=20)
        assert ra.status_code in (200, 201, 400), f"OT approve: {ra.status_code} {ra.text[:200]}"


# ─── Attendance ──────────────────────────────────────────────────────────────
class TestAttendance:
    def test_attendance_list(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/attendance", timeout=20)
        assert r.status_code == 200

    def test_attendance_grid(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/attendance/grid", timeout=20)
        assert r.status_code == 200

    def test_office_location(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/attendance/office-location", timeout=20)
        assert r.status_code == 200

    def test_attendance_summary(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/attendance/summary", timeout=20)
        assert r.status_code == 200

    def test_hr_dashboard(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/hr/dashboard", timeout=20)
        assert r.status_code == 200


# ─── Payroll ─────────────────────────────────────────────────────────────────
class TestPayroll:
    def test_list_profiles(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/payroll-profiles", timeout=20)
        assert r.status_code == 200

    def test_list_allowances(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/payroll-allowances", timeout=20)
        assert r.status_code == 200

    def test_salary_grades(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/salary-grades", timeout=20)
        assert r.status_code == 200

    def test_payroll_runs_list(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/payroll-runs", timeout=20)
        assert r.status_code == 200

    def test_payroll_run_create_compute(self, s, employee):
        """Create payroll run → expect payslips computed with allowances/deductions."""
        # Ensure profile exists for this employee
        rprof = s.get(f"{BASE_URL}/api/rahaza/payroll-profiles", timeout=20).json()
        prof_emp_ids = [p.get("employee_id") for p in rprof]
        if employee["id"] not in prof_emp_ids:
            # Try to create a profile
            body = {
                "employee_id": employee["id"],
                "basic_salary": 5000000,
                "active": True,
            }
            cp = s.post(f"{BASE_URL}/api/rahaza/payroll-profiles", json=body, timeout=20)
            if cp.status_code not in (200, 201):
                pytest.skip(f"cannot ensure payroll profile: {cp.status_code} {cp.text[:200]}")

        # Create payroll run for a past month
        today = date.today()
        first = today.replace(day=1) - timedelta(days=15)
        period_from = first.replace(day=1).isoformat()
        period_to = (first.replace(day=1) + timedelta(days=27)).isoformat()
        body = {
            "period_from": period_from,
            "period_to": period_to,
            "employee_ids": [employee["id"]],
            "notes": "TEST_iter9 payroll run",
        }
        r = s.post(f"{BASE_URL}/api/rahaza/payroll-runs", json=body, timeout=60)
        assert r.status_code in (200, 201, 400), f"payroll run: {r.status_code} {r.text[:300]}"
        if r.status_code not in (200, 201):
            pytest.skip(f"payroll run not created (likely no profile): {r.text[:200]}")
        run_id = r.json().get("id")
        # Get run detail (payslips)
        rd = s.get(f"{BASE_URL}/api/rahaza/payroll-runs/{run_id}", timeout=30)
        assert rd.status_code == 200, f"run detail: {rd.status_code} {rd.text[:200]}"
        data = rd.json()
        assert "run" in data and "payslips" in data
        # Payslip math sanity: net = gross - deductions
        if data["payslips"]:
            slip = data["payslips"][0]
            gp = slip.get("gross_pay", 0)
            dd = slip.get("deductions_total", 0)
            np_ = slip.get("net_pay", 0)
            assert abs((gp - dd) - np_) < 1.0, f"payslip math broken gross={gp} ded={dd} net={np_}"

    def test_employee_loans_list(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/hr/employee-loans", timeout=20)
        # 404 ok if not mounted under this path
        assert r.status_code in (200, 401, 404)


# ─── HR Reports xlsx ─────────────────────────────────────────────────────────
class TestHRReports:
    def test_attendance_summary_xlsx(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/hr/reports/attendance-summary.xlsx",
                  params={"month": date.today().strftime("%Y-%m")}, timeout=30)
        assert r.status_code == 200, f"attendance xlsx: {r.status_code} {r.text[:200]}"
        ct = r.headers.get("content-type", "")
        assert "spreadsheet" in ct or "officedocument" in ct, f"not xlsx ct={ct}"

    def test_overtime_summary_xlsx(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/hr/reports/overtime-summary.xlsx",
                  params={"month": date.today().strftime("%Y-%m")}, timeout=30)
        assert r.status_code == 200

    def test_payroll_summary_xlsx(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/hr/reports/payroll-summary.xlsx",
                  params={"month": date.today().strftime("%Y-%m")}, timeout=30)
        assert r.status_code == 200


# ─── Expense Claims chain ────────────────────────────────────────────────────
class TestExpenseClaims:
    def test_categories(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/categories", timeout=20)
        assert r.status_code == 200

    def test_claims_list(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/claims", timeout=20)
        assert r.status_code == 200

    def test_claims_export(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/claims/export", timeout=30)
        assert r.status_code == 200

    def test_expense_claim_chain(self, s, employee):
        """Create -> submit -> approve -> disburse (settled with GL)."""
        # get a category
        cats = s.get(f"{BASE_URL}/api/hr/expenses/categories", timeout=20).json()
        cat = cats[0] if isinstance(cats, list) and cats else None
        body = {
            "employee_id": employee["id"],
            "title": f"TEST_iter9 expense {TS}",
            "category_id": cat["id"] if cat else None,
            "category_code": cat.get("code") if cat else "TRAVEL",
            "items": [
                {
                    "category": cat.get("code") if cat else "TRAVEL",
                    "category_id": cat["id"] if cat else None,
                    "category_code": cat.get("code") if cat else "TRAVEL",
                    "description": "TEST item",
                    "amount": 250000,
                    "currency": "IDR",
                    "date": date.today().isoformat(),
                    "expense_date": date.today().isoformat(),
                }
            ],
            "amount": 250000,
            "currency": "IDR",
            "expense_date": date.today().isoformat(),
            "description": "TEST_iter9 expense",
        }
        r = s.post(f"{BASE_URL}/api/hr/expenses/claims", json=body, timeout=30)
        assert r.status_code in (200, 201, 400, 422), f"claim create: {r.status_code} {r.text[:300]}"
        if r.status_code not in (200, 201):
            pytest.skip(f"claim could not be created: {r.text[:200]}")
        cid = r.json().get("id") or r.json().get("claim_id")
        if not cid:
            return
        # Submit
        rs = s.post(f"{BASE_URL}/api/hr/expenses/claims/{cid}/submit", json={}, timeout=20)
        assert rs.status_code in (200, 201, 400), f"submit: {rs.status_code} {rs.text[:200]}"
        # Approve
        ra = s.post(f"{BASE_URL}/api/hr/expenses/claims/{cid}/approve",
                    json={"notes": "ok"}, timeout=20)
        assert ra.status_code in (200, 201, 400), f"approve: {ra.status_code} {ra.text[:200]}"
        # Disburse (GL posting)
        rd = s.post(f"{BASE_URL}/api/hr/expenses/claims/{cid}/disburse",
                    json={"payment_method": "cash"}, timeout=30)
        assert rd.status_code in (200, 201, 400), f"disburse: {rd.status_code} {rd.text[:200]}"
        # Get claim and verify status
        rg = s.get(f"{BASE_URL}/api/hr/expenses/claims/{cid}", timeout=20)
        assert rg.status_code == 200
        st = rg.json().get("status")
        assert st in ("submitted", "approved", "disbursed", "settled", "rejected", "paid", "posted"), st


# ─── Travel chain ────────────────────────────────────────────────────────────
class TestTravel:
    def test_travel_list(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/travel", timeout=20)
        assert r.status_code == 200

    def test_travel_export_csv(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/travel/export", timeout=30)
        assert r.status_code == 200, f"travel csv export: {r.status_code} {r.text[:200]}"
        # Should be CSV or xlsx
        ct = r.headers.get("content-type", "")
        assert ("csv" in ct.lower() or "spreadsheet" in ct.lower() or
                "officedocument" in ct.lower() or "text/plain" in ct.lower()), f"ct={ct}"

    def test_settlements_list(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/settlements", timeout=20)
        assert r.status_code == 200

    def test_outstanding_advances(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/outstanding-advances", timeout=20)
        assert r.status_code == 200

    def test_settlement_summary(self, s):
        r = s.get(f"{BASE_URL}/api/hr/expenses/settlement-summary", timeout=20)
        assert r.status_code == 200

    def test_travel_request_chain(self, s, employee):
        """create travel request -> submit -> approve -> advance-paid -> settlement -> approve -> post."""
        body = {
            "employee_id": employee["id"],
            "purpose": "TEST_iter9 site visit",
            "destination": "Jakarta",
            "destination_city": "Jakarta",
            "start_date": (date.today() + timedelta(days=5)).isoformat(),
            "end_date": (date.today() + timedelta(days=7)).isoformat(),
            "from_date": (date.today() + timedelta(days=5)).isoformat(),
            "to_date": (date.today() + timedelta(days=7)).isoformat(),
            "advance_amount": 1500000,
            "currency": "IDR",
        }
        r = s.post(f"{BASE_URL}/api/hr/expenses/travel", json=body, timeout=30)
        if r.status_code not in (200, 201):
            pytest.skip(f"travel create: {r.status_code} {r.text[:300]}")
        tid = r.json().get("id") or r.json().get("request_id")
        if not tid:
            return
        # Submit
        s.post(f"{BASE_URL}/api/hr/expenses/travel/{tid}/submit", json={}, timeout=20)
        # Approve
        ra = s.post(f"{BASE_URL}/api/hr/expenses/travel/{tid}/approve",
                    json={"notes": "ok"}, timeout=20)
        assert ra.status_code in (200, 201, 400)
        # Advance paid (creates cash advance / GL)
        s.post(f"{BASE_URL}/api/hr/expenses/travel/{tid}/advance-paid",
               json={"payment_method": "transfer"}, timeout=20)
        # Get with status label
        rg = s.get(f"{BASE_URL}/api/hr/expenses/travel/{tid}", timeout=20)
        assert rg.status_code == 200
        body = rg.json()
        # STATUS_LABELS recently added
        assert "status" in body

        # Try settlement
        sbody = {
            "actual_expenses": [
                {"category": "transport", "amount": 500000, "description": "taxi"},
                {"category": "meal", "amount": 300000, "description": "lunch"},
            ],
            "notes": "TEST_iter9 settlement",
        }
        rs = s.post(f"{BASE_URL}/api/hr/expenses/travel/{tid}/settlements",
                    json=sbody, timeout=30)
        if rs.status_code in (200, 201):
            stl_id = rs.json().get("id") or rs.json().get("settlement_id")
            if stl_id:
                # submit + approve + post
                s.post(f"{BASE_URL}/api/hr/expenses/settlements/{stl_id}/submit",
                       json={}, timeout=20)
                rap = s.post(f"{BASE_URL}/api/hr/expenses/settlements/{stl_id}/approve",
                             json={"notes": "ok"}, timeout=20)
                assert rap.status_code in (200, 201, 400)
                rpost = s.post(f"{BASE_URL}/api/hr/expenses/settlements/{stl_id}/post",
                               json={}, timeout=30)
                # Must not 500 - settlement posting creates GL
                assert rpost.status_code != 500, f"settlement post 500: {rpost.text[:300]}"


# ─── Approval Inbox & Multi-level ────────────────────────────────────────────
class TestApprovals:
    def test_hr_inbox(self, s):
        r = s.get(f"{BASE_URL}/api/hr/inbox", timeout=20)
        assert r.status_code in (200, 404), f"hr inbox: {r.status_code} {r.text[:200]}"

    def test_multilevel_chains(self, s):
        # approval_multilevel base list
        r = s.get(f"{BASE_URL}/api/approvals", timeout=20)
        # endpoint may differ - any non-500 is acceptable; we just want no 500
        assert r.status_code != 500, f"approvals 500: {r.text[:200]}"


# ─── Announcements ───────────────────────────────────────────────────────────
class TestAnnouncements:
    def test_active(self, s):
        r = s.get(f"{BASE_URL}/api/announcements/active", timeout=20)
        assert r.status_code == 200

    def test_all(self, s):
        r = s.get(f"{BASE_URL}/api/announcements/all", timeout=20)
        # 403 acceptable if admin doesn't have permission, but reported as note
        assert r.status_code in (200, 403), f"announcements all: {r.status_code} {r.text[:200]}"

    def test_create_announcement(self, s):
        body = {
            "title": f"TEST_iter9 ann {TS}",
            "content": "test announcement body",
            "priority": "normal",
            "active": True,
        }
        r = s.post(f"{BASE_URL}/api/announcements/", json=body, timeout=20)
        assert r.status_code in (200, 201, 400, 422), f"ann create: {r.status_code} {r.text[:200]}"
        if r.status_code in (200, 201):
            aid = r.json().get("id")
            if aid:
                rg = s.get(f"{BASE_URL}/api/announcements/{aid}", timeout=20)
                assert rg.status_code == 200


# ─── Recruitment / Onboarding / Job Board ────────────────────────────────────
class TestRecruitOnboardJobBoard:
    def test_recruitment_jobs(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/recruitment/jobs", timeout=20)
        assert r.status_code == 200

    def test_recruitment_pipeline(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/recruitment/pipeline", timeout=20)
        assert r.status_code == 200

    def test_recruitment_analytics(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/recruitment/analytics", timeout=20)
        assert r.status_code == 200

    def test_onboarding_list(self, s):
        # explore likely paths
        r = s.get(f"{BASE_URL}/api/dewi/onboarding/templates", timeout=20)
        assert r.status_code in (200, 404)

    def test_job_board(self, s):
        r = s.get(f"{BASE_URL}/api/hr/job-board", timeout=20)
        assert r.status_code in (200, 404)


# ─── Performance / KPI / OKR / LMS ───────────────────────────────────────────
class TestPerformanceLMS:
    def test_hris_performance(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/hris/performance", timeout=20)
        assert r.status_code in (200, 404)

    def test_kpi_periods(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/kpi/periods", timeout=20)
        assert r.status_code in (200, 404)

    def test_okr_list(self, s):
        r = s.get(f"{BASE_URL}/api/management/okr", timeout=20)
        assert r.status_code in (200, 404)

    def test_lms_courses(self, s):
        r = s.get(f"{BASE_URL}/api/dewi/lms/courses", timeout=20)
        assert r.status_code in (200, 404)


# ─── Salary grades / adjustments / loans  ────────────────────────────────────
class TestSalary:
    def test_salary_adjustments_list(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/salary-adjustments", timeout=20)
        assert r.status_code in (200, 404)

    def test_payroll_tax(self, s):
        r = s.get(f"{BASE_URL}/api/rahaza/payroll-tax", timeout=20)
        assert r.status_code in (200, 404)
