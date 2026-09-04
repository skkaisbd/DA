# HR & Payroll Domain — Technical Reference

> **Portal:** HRIS (`hris-portal`)  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready, all P1/P2 tasks complete

---

## 1. Business Overview

Covers the full HR lifecycle for CV. Dewi Aditya employees:
- Employee master data & organization
- Attendance (manual + auto via ZKTeco/WebAuthn/selfie)
- Leave management (quota, requests, approvals, carry-forward)
- Overtime requests & approvals
- Payroll computation (gross, deductions, BPJS, PPh21, net)
- Payslip generation & employee portal
- KPI & performance reviews
- Recruitment (ATS, job board)
- LMS (courses, quizzes, certificates)
- HR approvals unified inbox

---

## 2. Key MongoDB Collections

| Collection | Purpose | SSOT? |
|---|---|---|
| `rahaza_employees` | Employee master data | ✅ SSOT |
| `rahaza_attendance_events` | Daily attendance per employee | ✅ SSOT |
| `rahaza_leave_types` | Leave type master (annual, sick, etc.) | ✅ SSOT |
| `rahaza_leave_requests` | Leave requests & approval status | ✅ SSOT |
| `rahaza_leave_balances` | Leave quota remaining per employee | ✅ SSOT |
| `rahaza_overtime_requests` | Overtime requests & approval | ✅ SSOT |
| `rahaza_payroll_runs` | Payroll run per period | ✅ SSOT |
| `rahaza_payroll_slips` | Individual payslips per employee | ✅ SSOT |
| `rahaza_salary_grades` | Salary grade definitions | ✅ SSOT |
| `rahaza_salary_adjustments` | Individual salary change requests | ✅ SSOT |
| `rahaza_allowances` | Allowance types & amounts | ✅ SSOT |
| `rahaza_shifts` | Shift definitions (Morning, Afternoon) | ✅ SSOT |
| `rahaza_shift_assignments` | Daily shift per employee | ✅ SSOT |
| `da_kpi_periods` | KPI review periods | ✅ SSOT |
| `da_kpi_assignments` | KPI assignment per employee | ✅ SSOT |
| `da_kpi_results` | KPI results & scores | ✅ SSOT |
| `dewi_recruitment_jobs` | Job postings | ✅ SSOT |
| `dewi_recruitment_applicants` | Applicant tracking | ✅ SSOT |
| `lms_courses` | LMS course catalog | ✅ SSOT |
| `lms_enrollments` | Course enrollments | ✅ SSOT |
| `rahaza_360_reviews` | 360° peer feedback | ✅ SSOT |
| `rahaza_skill_gaps` | Skill gap analysis | ✅ SSOT |
| `rahaza_resignations` | Resignation requests | ✅ SSOT |
| `webauthn_credentials` | WebAuthn credentials for attendance | ✅ SSOT |

---

## 3. Key API Endpoints

### Employees
```
GET  /api/rahaza/employees           — list employees
POST /api/rahaza/employees           — create employee
GET  /api/rahaza/employees/{id}      — get employee detail
PUT  /api/rahaza/employees/{id}      — update employee
DEL  /api/rahaza/employees/{id}      — soft delete
GET  /api/rahaza/employees/org-chart — organization chart
```

### Attendance
```
GET  /api/rahaza/attendance           — list attendance
POST /api/rahaza/attendance           — manual check-in
GET  /api/rahaza/attendance/today     — today's attendance summary
POST /api/auto-attendance/check-in    — ZKTeco/selfie auto check-in
POST /api/auto-attendance/check-out   — auto check-out
GET  /api/auto-attendance/status      — live attendance status board
```

### Leave
```
GET  /api/rahaza/leave                — list leave requests
POST /api/rahaza/leave                — create leave request
PUT  /api/rahaza/leave/{id}/approve   — approve (manager/HR)
PUT  /api/rahaza/leave/{id}/reject    — reject
GET  /api/rahaza/leave-balances       — employee leave balances
POST /api/rahaza/leave-balances/sync  — sync balances
```

### Overtime
```
GET  /api/rahaza/overtime             — list overtime requests
POST /api/rahaza/overtime             — create request
PUT  /api/rahaza/overtime/{id}/approve
PUT  /api/rahaza/overtime/{id}/reject
```

### Payroll
```
GET  /api/rahaza/payroll-runs         — list payroll runs
POST /api/rahaza/payroll-runs         — create run (compute)
POST /api/rahaza/payroll-runs/{id}/finalize — finalize & send payslip notifs
POST /api/rahaza/payroll-runs/{id}/pay-bpjs — pay BPJS → GL entry
POST /api/rahaza/payroll-runs/{id}/pay-pph21 — pay PPh21 → GL entry
GET  /api/rahaza/payslips/{employee_id}/{run_id} — get payslip
```

### KPI
```
GET  /api/dewi/kpi/periods            — list KPI periods
POST /api/dewi/kpi/periods            — create period
GET  /api/dewi/kpi/assignments        — list assignments
POST /api/dewi/kpi/assignments        — assign KPI to employee
GET  /api/dewi/kpi/results            — list results
POST /api/dewi/kpi/results            — submit result
GET  /api/dewi/kpi/trend/{employee_id} — monthly KPI trend chart data
GET  /api/dewi/kpi/leaderboard        — KPI leaderboard
```

### Recruitment
```
GET  /api/dewi/recruitment/jobs       — list jobs
POST /api/dewi/recruitment/jobs       — post job
GET  /api/dewi/recruitment/applicants — list applicants
POST /api/dewi/recruitment/applicants — create applicant
PUT  /api/dewi/recruitment/applicants/{id}/status — update stage
```

### LMS
```
GET  /api/lms/courses                 — course catalog
POST /api/lms/courses                 — create course
POST /api/lms/enroll                  — enroll employee
GET  /api/lms/student/courses         — my courses (student view)
POST /api/lms/quiz/submit             — submit quiz
GET  /api/lms/certificates            — certificates
```

### Unified Approval Hub
```
GET  /api/approval/requests           — all pending approvals
GET  /api/approval/requests?type=leave — filter by type
POST /api/approval/requests/{id}/approve
POST /api/approval/requests/{id}/reject
GET  /api/approval/chains             — list approval chains
POST /api/approval/chains             — create chain
```

---

## 4. Key Frontend Modules

| Module File | Portal Nav ID | Description |
|---|---|---|
| `HRDashboard.jsx` | `hris-dashboard` | HR overview, KPIs, headcount stats |
| `HREmployeeModule.jsx` | `hris-employees` | Employee master CRUD |
| `HRAdminModule.jsx` | `hris-admin` | HR admin panel |
| `HRApprovalInboxModule.jsx` | `hr-approval-inbox` | Unified HR approval inbox |
| `HRKPIModule.jsx` | `hris-kpi` | KPI management |
| `HRATSModule.jsx` | `hris-ats` | Applicant tracking system |
| `HR360FeedbackModule.jsx` | `hris-360` | 360° peer feedback |
| `HRAssetModule.jsx` | `hris-asset` | HR asset tracker |
| `PayrollModule.jsx` (via portal-shell) | `hris-payroll` | Payroll runs & payslips |
| `AttendanceModule.jsx` | `hris-attendance` | Attendance management |
| `ShiftSchedulerModule.jsx` | `hris-shift` | Shift scheduling |
| `LMSModule.jsx` | `hris-lms` | Learning management |
| `SkillGapModule.jsx` | `hris-skillgap` | Skill gap analysis |
| `HRPerformanceModule.jsx` | `hris-performance` | Annual performance reviews |

### Portal Saya (Employee Self-Service)
| Module | Feature |
|---|---|
| `PortalSayaModule.jsx` | Dashboard overview for logged-in employee |
| My Payslip tab | View slip gaji + attendance summary |
| My Leave tab | Apply leave + check balance |
| My KPI tab | View KPI scores by period |
| My Workspace | Notepad, Todo, Reminder, Calendar, Quick Links |
| My Documents | Upload & view personal docs |
| AI Career Coach | AI-powered career development report |

---

## 5. Business Flows

### H2R (Hire to Retire)
```
Recruitment → New Employee → Onboarding → Attendance → Payroll → KPI → Resign
     ↓               ↓            ↓             ↓           ↓        ↓       ↓
  HRATS      rahaza_employees  Checklist    Events       Runs    Results  Resign req
```

### Payroll Cycle
```
1. Create Payroll Run (select period)
2. System computes: base salary + allowances + OT pay + deductions
3. BPJS & PPh21 computed separately
4. Review & finalize → Payslip notifications sent to employees
5. Pay BPJS → GL entry (Dr Hutang BPJS / Cr Bank)
6. Pay PPh21 → GL entry (Dr Hutang PPh21 / Cr Bank)
```

### Leave Carry-Forward (Auto Scheduler)
```
Every Jan 1 at 01:00:
  For each employee: carry min(remaining_annual, 5) days to next year
  Creates notification to employee + HR
```

---

## 6. Approval Chain Configuration

Leave & overtime use `approval_chains` collection:
```json
{
  "entity_type": "leave",
  "steps": [
    {"step": 1, "approver_role": "Manager", "timeout_hours": 24},
    {"step": 2, "approver_role": "HR", "timeout_hours": 48}
  ],
  "escalation_policy": "skip_to_next"
}
```

---

## 7. Key Backend Files

| File | Purpose |
|---|---|
| `routes/rahaza_attendance.py` | Attendance CRUD |
| `routes/rahaza_auto_attendance.py` | ZKTeco/selfie check-in |
| `routes/rahaza_leave.py` | Leave requests |
| `routes/rahaza_leave_balances.py` | Leave balance management |
| `routes/rahaza_overtime.py` | Overtime requests |
| `routes/rahaza_payroll_runs.py` | Payroll computation & finalize |
| `routes/rahaza_payroll_payslips.py` | Payslip generation |
| `routes/rahaza_salary_grades.py` | Salary grade definitions |
| `routes/rahaza_salary_adjustments.py` | Salary adjustment requests |
| `routes/dewi_kpi_periods.py` | KPI period management |
| `routes/dewi_kpi_results.py` | KPI result submission |
| `routes/dewi_recruitment.py` | Recruitment ATS |
| `routes/dewi_lms.py` | LMS course management |
| `routes/rahaza_resignation.py` | Resignation workflow |
| `routes/hr_approval_inbox.py` | Unified HR approval |
| `routes/approval_multilevel.py` | Multi-level approval chains |

---

## 8. Recent Relevant Sessions

- **#11.20 (2026-05-27):** Approval chain completion — leave, overtime, salary, resignation chains configured
- **Session #28 (2026-05):** KPI Monthly Trend panel, AI Career Coach, leave carry-forward scheduler, BPJS/PPh21 payment GL entries, manager notifications
- **Session #9 (2026-05-24):** HR Approval Inbox consolidation (unified 5 approval lists into 1 hub)

---

## 9. Known Tech Debt / Notes

- `dewi_kpi.py.old` and `dewi_kpi.py.pre-refactor-backup` are backup files — do NOT delete without verifying `dewi_kpi_*.py` modules cover all cases
- Auto-attendance WebAuthn (`rahaza_auto_attendance_webauthn.py`) requires HTTPS in production
- ZKTeco integration (`rahaza_auto_attendance_zkteco.py`) needs device IP configuration
