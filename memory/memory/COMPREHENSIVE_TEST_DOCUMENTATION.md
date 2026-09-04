# COMPREHENSIVE TEST DOCUMENTATION
**CV. Dewi Aditya ERP System**
**Generated:** 27 Mei 2026
**Purpose:** Complete testing documentation untuk semua business processes dan system flows

---

## SYSTEM OVERVIEW

**Total Endpoints:** 1,905 endpoints
**Total Domains:** 254 route files
**Architecture:** FastAPI (Backend) + React (Frontend) + MongoDB

### Endpoint Distribution by Prefix:
- `/api/rahaza/*` - Core business logic (Production, Finance, Inventory, HR, Payroll)
- `/api/dewi/*` - Maklon/CMT, Assets, Client Portal, AI features, Warehouse
- `/api/wms/*` - Warehouse Management System
- `/api/approvals/*` - Multi-level approval engine
- `/api/notifications/*` - Notification system (unified)
- `/api/marketing/*` - Marketing & Sales
- `/api/hr/*` - HR operations
- `/api/acc/*` - Accessories management
- `/api/finance/*` - Finance operations
- `/api/ai/*` - AI features

---

## BUSINESS DOMAINS & FLOWS

### 1. PRODUCTION DOMAIN
**Total Endpoints:** ~150+ endpoints
**Prefix:** `/api/rahaza/*`, `/api/work-orders/*`, `/api/production/*`

#### 1.1 Core Production Flows
| Flow ID | Flow Name | Start | Steps | End | Integration Points |
|---------|-----------|-------|-------|-----|-------------------|
| PROD-001 | Work Order Lifecycle | WO Creation | Release → Material Reserve → Issue → WIP → QC → Complete | Finished Goods | Warehouse, Finance |
| PROD-002 | Material Reservation | WO Release | Check availability → Reserve → Track | Material Issue | Warehouse |
| PROD-003 | Material Issue | WO Released | Generate issue → Warehouse approve → Stock deduct | Production | Warehouse, Ledger |
| PROD-004 | Material Return | Production | Create return → Approve → Warehouse receive → Stock add | Warehouse | Approval, Warehouse |
| PROD-005 | WIP Tracking | Production Start | Record progress → Update status → Track completion | Reports | Dashboard |
| PROD-006 | Production Completion | QC Pass | Complete WO → Receive FG → Update inventory | Warehouse | Warehouse, Finance |
| PROD-007 | Scrap Management | Production | Record scrap → Approve → Cost allocation | Finance | Approval, Finance |
| PROD-008 | Rework Management | QC Fail | Create rework → Re-process → QC → Complete | Warehouse | QC, Warehouse |
| PROD-009 | BOM Management | Product Design | Create BOM → Version control → Cost calculation | Production | Finance, Purchasing |
| PROD-010 | Production Scheduling | Planning | Create schedule → Capacity check → Assign | Execution | Resources |

#### 1.2 Key Endpoints
```
GET    /api/rahaza/work-orders
POST   /api/rahaza/work-orders
PUT    /api/rahaza/work-orders/{wo_id}
POST   /api/rahaza/work-orders/{wo_id}/release
POST   /api/rahaza/work-orders/{wo_id}/complete
GET    /api/rahaza/material-reservations
POST   /api/rahaza/material-reservations
GET    /api/rahaza/materials/{id}/availability
GET    /api/production/material-returns
POST   /api/production/material-returns
POST   /api/production/material-returns/{id}/submit
POST   /api/production/material-returns/{id}/approve
POST   /api/production/material-returns/{id}/receive
GET    /api/rahaza/bom
POST   /api/rahaza/bom
PUT    /api/rahaza/bom/{bom_id}
```

#### 1.3 Integration Points
- **→ Warehouse:** Material reservation, issue, return, FG receiving
- **→ Finance:** Cost tracking, WIP valuation, FG costing
- **→ Approval:** Material return approval, scrap approval
- **→ Quality:** QC checkpoints, inspection records

---

### 2. WAREHOUSE DOMAIN
**Total Endpoints:** ~120+ endpoints
**Prefix:** `/api/wms/*`, `/api/rahaza/inventory/*`, `/api/dewi/warehouse/*`

#### 2.1 Core Warehouse Flows
| Flow ID | Flow Name | Start | Steps | End | Integration Points |
|---------|-----------|-------|-------|-----|-------------------|
| WHS-001 | Goods Receipt | PO | GRN create → Inspect → Receive → Update stock | Inventory | Purchasing, Finance |
| WHS-002 | Stock Opname | Schedule | Create session → Count (blind/normal) → Submit → Approve → Adjust | Inventory | Approval, Finance |
| WHS-003 | Stock Movement | Request | Create movement → Approve → Execute → Update locations | Inventory | Approval |
| WHS-004 | Material Issue | Production request | Pick material → Validate → Issue → Deduct stock | Production | Production, Ledger |
| WHS-005 | Delivery Note | Sales Order | Create DN → Pick → Pack → Ship → Update | Sales | Sales, Finance |
| WHS-006 | Stock Allocation | Order | Reserve stock → Allocate → Track | Fulfillment | Sales, Production |
| WHS-007 | Stock Aging | Inventory | Calculate age → Generate report → Alert | Management | Reporting |
| WHS-008 | Batch/Lot Tracking | Receipt | Assign batch → Track movements → FIFO/FEFO | Usage | Quality, Compliance |
| WHS-009 | Cycle Count | Schedule | Select items → Count → Variance → Adjust | Inventory | Finance |
| WHS-010 | Min/Max Alerts | Monitoring | Check levels → Generate alert → Trigger PR | Purchasing | Purchasing |

#### 2.2 Key Endpoints
```
GET    /api/wms/opname2
POST   /api/wms/opname2
POST   /api/wms/opname2/{session_id}/scan
POST   /api/wms/opname2/{session_id}/submit
POST   /api/wms/opname2/{session_id}/approve
GET    /api/wms/delivery-notes
POST   /api/wms/delivery-notes
GET    /api/wms/picklist
POST   /api/wms/picklist
GET    /api/rahaza/inventory/materials
GET    /api/rahaza/inventory/movements
POST   /api/rahaza/inventory/adjustments
GET    /api/dewi/warehouse/receiving
POST   /api/dewi/warehouse/receiving
```

#### 2.3 Integration Points
- **→ Production:** Material issue, FG receiving, returns
- **→ Finance:** Stock valuation, adjustments, COGS
- **→ Sales:** Order fulfillment, delivery, stock allocation
- **→ Purchasing:** GRN, stock alerts, min/max triggers

---

### 3. FINANCE DOMAIN
**Total Endpoints:** ~100+ endpoints
**Prefix:** `/api/rahaza/finance/*`, `/api/finance/*`, `/api/dewi/finance/*`

#### 3.1 Core Finance Flows
| Flow ID | Flow Name | Start | Steps | End | Integration Points |
|---------|-----------|-------|-------|-----|-------------------|
| FIN-001 | AR Invoice | Sales Order | Create invoice → Approve → Send → Receive payment → Reconcile | AR Ledger | Sales, Bank |
| FIN-002 | AP Invoice | Vendor Invoice | Receive → Match (3-way) → Approve → Schedule payment → Pay | AP Ledger | Purchasing, Bank |
| FIN-003 | Journal Entry | Transaction | Create JE → Review → Post → Ledger update | GL | All modules |
| FIN-004 | Bank Reconciliation | Bank Statement | Import → Match → Reconcile → Adjust | Bank Account | All payments |
| FIN-005 | Cost Center Accounting | Transaction | Allocate cost → Track → Report | Management | Production, HR |
| FIN-006 | Asset Depreciation | Period End | Calculate depreciation → Post JE → Update asset value | Assets | Asset Mgmt |
| FIN-007 | Budget vs Actual | Period | Compare budget → Calculate variance → Alert | Management | All modules |
| FIN-008 | Tax Calculation | Transaction | Calculate tax → Accrue → File → Pay | Tax Authority | Sales, Purchasing |
| FIN-009 | Month-End Close | Period End | Reconcile all → Accrue → Close period → Lock | Next Period | All modules |
| FIN-010 | Cash Flow Forecast | Weekly | Analyze AR/AP → Project cash → Alert | Treasury | AR, AP |

#### 3.2 Key Endpoints
```
GET    /api/rahaza/finance/ar/invoices
POST   /api/rahaza/finance/ar/invoices
POST   /api/rahaza/finance/ar/invoices/{id}/approve
POST   /api/rahaza/finance/ar/invoices/{id}/payment
GET    /api/rahaza/finance/ap/invoices
POST   /api/rahaza/finance/ap/invoices
GET    /api/rahaza/journals
POST   /api/rahaza/journals
POST   /api/rahaza/journals/{id}/post
GET    /api/rahaza/coa
POST   /api/rahaza/coa
GET    /api/finance/bank-recon/sessions
POST   /api/finance/bank-recon/sessions
POST   /api/finance/bank-recon/sessions/{id}/match
```

---

### 4. HR & PAYROLL DOMAIN
**Total Endpoints:** ~80+ endpoints
**Prefix:** `/api/rahaza/payroll/*`, `/api/hr/*`, `/api/rahaza/attendance/*`

#### 4.1 Core HR Flows
| Flow ID | Flow Name | Start | Steps | End | Integration Points |
|---------|-----------|-------|-------|-----|-------------------|
| HR-001 | Employee Onboarding | Hire | Create profile → Assign → Orient → Activate | Active Employee | Finance, Asset |
| HR-002 | Attendance Tracking | Daily | Check-in → Work → Check-out → Calculate | Attendance Record | Payroll |
| HR-003 | Leave Management | Request | Submit leave → Approve → Deduct balance → Track | Leave Record | Approval, Payroll |
| HR-004 | Payroll Processing | Period End | Sync attendance → Calculate → Generate payslips → Approve → Post | Payment | Finance, Bank |
| HR-005 | Salary Adjustment | Request | Create request → Approve → Update profile → Effective | Employee Record | Approval, Finance |
| HR-006 | Resignation | Employee | Submit resignation → Handover → Exit interview → Clearance | Inactive | Finance, Asset |
| HR-007 | Shift Management | Schedule | Create shifts → Assign employees → Track adherence | Roster | Attendance |
| HR-008 | Training Management | Plan | Schedule training → Enroll → Conduct → Evaluate | Training Record | Performance |
| HR-009 | Performance Review | Period | Self-review → Manager review → Calibrate → Finalize | Review Record | Compensation |
| HR-010 | Overtime Approval | Request | Submit OT → Approve → Calculate pay → Add to payroll | Overtime Record | Approval, Payroll |

#### 4.2 Key Endpoints
```
GET    /api/rahaza/attendance
POST   /api/rahaza/attendance/check-in
POST   /api/rahaza/attendance/check-out
GET    /api/hr/shifts
POST   /api/hr/shifts
POST   /api/hr/shifts/{id}/assign
GET    /api/rahaza/payroll/runs
POST   /api/rahaza/payroll/runs
POST   /api/rahaza/payroll/runs/{id}/calculate
POST   /api/rahaza/payroll/runs/{id}/generate-payslips
GET    /api/rahaza/payroll/payslips
GET    /api/hr/inbox
POST   /api/hr/leave-requests
POST   /api/hr/leave-requests/{id}/approve
```

---

### 5. MAKLON/CMT DOMAIN
**Total Endpoints:** ~80+ endpoints
**Prefix:** `/api/dewi/maklon/*`, `/api/dewi/cmt/*`

#### 5.1 Core Maklon Flows
| Flow ID | Flow Name | Start | Steps | End | Integration Points |
|---------|-----------|-------|-------|-----|-------------------|
| MAK-001 | Client Onboarding | Lead | Register client → KYC → Create account → Activate | Active Client | Finance |
| MAK-002 | Sample Development | Client Request | Receive specs → Design → Produce sample → Submit | Sample Approval | RnD, Production |
| MAK-003 | Quotation | Inquiry | Cost calculation → Pricing → Send quote → Negotiate | Order | Finance |
| MAK-004 | CMT Order | Quote Approval | Create order → Receive material → Plan production → Track | Order In Progress | Production, Warehouse |
| MAK-005 | CMT Production | Order Start | Cut → Sew → QC → Finish → Pack | Ready to Ship | Production, QC |
| MAK-006 | Quality Inspection | Production Complete | Inspect → Record defects → Accept/Reject → Document | QC Report | Production |
| MAK-007 | Delivery to Client | QC Pass | Pack → Generate DN → Ship → Confirm delivery | Delivered | Warehouse, Finance |
| MAK-008 | CMT Billing | Delivery | Calculate charges → Create invoice → Send → Receive payment | Paid | Finance, AR |
| MAK-009 | Material Reconciliation | Order Close | Count material → Calculate usage → Reconcile → Return excess | Closed | Warehouse |
| MAK-010 | SLA Tracking | Order Lifecycle | Track lead time → Calculate on-time % → Alert delays → Report | SLA Dashboard | Management |

#### 5.2 Key Endpoints
```
GET    /api/dewi/maklon/clients
POST   /api/dewi/maklon/clients
PUT    /api/dewi/maklon/clients/{client_id}
GET    /api/dewi/maklon/pos
POST   /api/dewi/maklon/pos
PUT    /api/dewi/maklon/pos/{po_id}
GET    /api/dewi/maklon/summary
GET    /api/maklon/sla/dashboard
POST   /api/maklon/sla/lead-time/estimate
GET    /api/dewi/cmt/jobs
POST   /api/dewi/cmt/jobs
POST   /api/dewi/cmt/jobs/{job_id}/start
POST   /api/dewi/cmt/jobs/{job_id}/complete
```

---

### 6. APPROVAL SYSTEM (CROSS-DOMAIN)
**Total Endpoints:** ~15 endpoints
**Prefix:** `/api/approvals/*`, `/api/hr/inbox`

#### 6.1 Approval Engine Flows
| Flow ID | Flow Name | Applies To | Steps | Status Transitions |
|---------|-----------|------------|-------|-------------------|
| APP-001 | Single Level Approval | Leave, Overtime, Simple requests | Submit → Approve/Reject | pending → approved/rejected |
| APP-002 | Multi-Level Approval | Salary Adj, Large expenses, Material return | Submit → Manager → Director → Finance | pending_manager → pending_director → pending_finance → approved |
| APP-003 | Parallel Approval | Cross-dept initiatives | Submit → Multiple approvers simultaneously | pending → approved (when all approved) |
| APP-004 | Conditional Approval | Amount-based routing | Submit → Route based on conditions → Approve | varies by condition |
| APP-005 | Approval Delegation | Manager absence | Delegate authority → Proxy approve → Log | pending → approved (by delegate) |

#### 6.2 Key Endpoints
```
GET    /api/approvals/chains
POST   /api/approvals/chains
GET    /api/approvals/requests
POST   /api/approvals/requests
GET    /api/approvals/pending
POST   /api/approvals/requests/{id}/approve
POST   /api/approvals/requests/{id}/reject
GET    /api/hr/inbox
GET    /api/approvals/summary
```

---

## INTEGRATION TESTING MATRIX

### Critical Integration Points
| Integration | Module A | Module B | Data Flow | Validation Required |
|-------------|----------|----------|-----------|---------------------|
| INT-001 | Production | Warehouse | Material issue → Stock deduction | Stock qty decreased, ledger entry |
| INT-002 | Production | Warehouse | Material return → Stock addition | Stock qty increased, ledger entry |
| INT-003 | Production | Warehouse | WO complete → FG receiving | FG stock increased, WO closed |
| INT-004 | Production | Finance | Material issue → Cost allocation | WIP increased, cost tracked |
| INT-005 | Warehouse | Finance | Stock adjustment → GL entry | GL posted, stock value updated |
| INT-006 | HR | Finance | Payroll post → Payable | AP created, payroll expense posted |
| INT-007 | Sales | Warehouse | SO → Stock allocation | Stock reserved, allocation tracked |
| INT-008 | Purchasing | Warehouse | GRN → Stock receipt | Stock increased, PO updated |
| INT-009 | Purchasing | Finance | Invoice matching → AP | AP created, accrued liability |
| INT-010 | Approval | All Modules | Approval → Status change | Request approved, data updated |

---

## TEST SCENARIOS PRIORITIZATION

### Priority 1 - CRITICAL BUSINESS FLOWS (Must Test)
1. ✅ **Production → Warehouse Integration** (Material issue, return, FG receiving)
2. ✅ **Approval System** (Multi-level workflow)
3. ✅ **Material Reservation** (Availability calculation)
4. ✅ **Stock Opname Blind Mode** (Count without system qty visibility)
5. ✅ **Payroll Automation** (Attendance → Calculation → Payslip)
6. 🔄 **Finance AR/AP** (Invoice → Payment → Reconciliation)
7. 🔄 **Warehouse GRN** (PO → Receipt → Stock update)
8. 🔄 **Sales Order Fulfillment** (SO → Pick → Ship → Invoice)

### Priority 2 - IMPORTANT FLOWS (Should Test)
9. 🔄 **HR Leave Management** (Request → Approve → Balance deduction)
10. 🔄 **Maklon Order Lifecycle** (Order → Production → Delivery → Billing)
11. 🔄 **Bank Reconciliation** (Import → Match → Reconcile)
12. 🔄 **Budget Tracking** (Actual vs Budget, variance alerts)

### Priority 3 - SUPPORTING FLOWS (Nice to Test)
13. 🔄 **Asset Management** (Register → Assign → Depreciate)
14. 🔄 **RnD Sample Development** (Request → Design → Approve)
15. 🔄 **Training Management** (Schedule → Enroll → Complete)

---

## TEST DATA REQUIREMENTS

### Master Data Needed:
- ✅ Users (Admin, Manager, Employee) - EXISTS
- ✅ Materials (Raw materials, components) - EXISTS
- ✅ Products (Finished goods with BOM) - EXISTS
- ✅ Employees (With profiles, attendance) - EXISTS
- ✅ Clients (Maklon clients) - EXISTS
- 🔄 Vendors (Suppliers for purchasing) - NEED TO VERIFY
- 🔄 Chart of Accounts - NEED TO VERIFY
- 🔄 Tax Codes - NEED TO VERIFY

### Transaction Data for Testing:
- ✅ Work Orders (20 movements recorded)
- ✅ Material Reservations (Active reservations)
- ✅ Payroll Runs (3 runs in history)
- ✅ Approval Requests (5 pending)
- ✅ Opname Sessions (6 sessions)
- 🔄 Sales Orders
- 🔄 Purchase Orders
- 🔄 AR/AP Invoices

---

## TESTING APPROACH

### Phase 1: Endpoint Discovery & Validation ✅ DONE
- Cataloged 1,905 endpoints across 254 domains
- Identified prefix patterns
- Mapped integration points

### Phase 2: Critical Flow Testing ✅ DONE (93.5% success)
- Production-Warehouse integration ✅
- Material reservation & return ✅
- Multi-level approval ✅
- Stock opname blind mode ✅
- Payroll automation ✅

### Phase 3: Domain-by-Domain Testing 🔄 IN PROGRESS
- Finance domain (0% - endpoint pattern issue)
- Maklon/CMT domain (0% - endpoint pattern issue)
- HR & Payroll (10% - partial testing)
- Warehouse (33% - partial testing)
- Production (20% - partial testing)

### Phase 4: Integration Testing 🔄 PENDING
- Cross-module data flows
- End-to-end business cycles
- Data consistency validation
- Audit trail verification

### Phase 5: Performance & Load Testing 🔄 PENDING
- Concurrent user scenarios
- Large dataset handling
- Response time benchmarks

---

## TESTING STATUS SUMMARY

### Completed Tests:
- ✅ Integration flows (29/31 passed = 93.5%)
- ✅ Approval system (4/5 passed = 80%)
- ✅ Notification system (2/4 passed = 50%)
- ✅ Marketing (4/10 passed = 40%)
- ✅ Warehouse operations (4/12 passed = 33%)

### Pending Tests:
- 🔄 Finance domain (with correct endpoints)
- 🔄 Maklon/CMT domain (with correct endpoints)
- 🔄 RnD domain (with correct endpoints)
- 🔄 Asset management (with correct endpoints)
- 🔄 Purchasing domain
- 🔄 Sales domain

### Test Reports:
- `/app/test_reports/iteration_83.json` - Initial comprehensive test
- `/app/test_reports/iteration_84.json` - Integration testing
- `/app/test_reports/iteration_85.json` - Full domain discovery
- `/tmp/endpoint_catalog.json` - Complete endpoint catalog

---

## NEXT STEPS

1. **Generate Endpoint Map by Domain** - Group 1,905 endpoints by business domain
2. **Create Test Scripts with Correct Endpoints** - Update test scripts with proper prefix patterns
3. **Execute Domain-by-Domain Testing** - Systematic testing of all 12 domains
4. **Validate All Integration Points** - Test 10 critical integrations
5. **Document Results** - Comprehensive test report with coverage metrics

---

**Documentation Version:** 1.0
**Last Updated:** 27 Mei 2026
**Status:** Ready for systematic testing execution
