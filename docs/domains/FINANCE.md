# Finance Domain — Technical Reference

> **Portal:** Finance (`finance-portal`)  
> **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ Production-ready, all P2 tasks complete

---

## 1. Business Overview

Covers end-to-end financial management for CV. Dewi Aditya:
- Chart of Accounts (COA) & General Ledger
- Accounts Receivable (AR) — invoicing, collections, AR 360°
- Accounts Payable (AP) — vendor invoices, payments
- Procurement (PR → PO → GR → AP)
- Purchase Requests & Purchase Orders
- Journal entries & auto-posting
- Budget management
- Bank Reconciliation
- Cashflow management & AI insights
- Financial reports (P&L, Balance Sheet, Cashflow)
- Fixed assets accounting

---

## 2. Key MongoDB Collections

| Collection | Purpose | SSOT? |
|---|---|---|
| `rahaza_coa` | Chart of Accounts | ✅ SSOT |
| `rahaza_journals` | Journal entries (double-entry) | ✅ SSOT |
| `rahaza_pos` | Purchase Orders (PO-YYYYMMDD-NNN) | ✅ SSOT |
| `rahaza_grns` | Goods Receipt Notes | ✅ SSOT |
| `rahaza_ap_invoices` | AP invoices from GRN | ✅ SSOT |
| `rahaza_ar_invoices` | AR invoices to customers | ✅ SSOT |
| `rahaza_ar_payments` | AR payment receipts | ✅ SSOT |
| `dewi_purchase_requests` | Purchase Requests (PR-YYYYMMDD-NNN) | ✅ SSOT |
| `rahaza_budget` | Budget per period + account | ✅ SSOT |
| `rahaza_bank_accounts` | Bank accounts master | ✅ SSOT |
| `rahaza_bank_transactions` | Bank transactions (imported) | ✅ SSOT |
| `rahaza_bank_recon_sessions` | Bank reconciliation sessions | ✅ SSOT |
| `rahaza_expense_claims` | Employee expense claims | ✅ SSOT |
| `rahaza_fixed_assets` | Fixed asset register | ✅ SSOT |
| `rahaza_asset_depreciation` | Asset depreciation schedule | ✅ SSOT |
| `rahaza_posting_profiles` | Auto-posting GL profiles | ✅ SSOT |
| `counters` | PO/GR/AP/AR sequence numbers | ✅ SSOT (shared) |

---

## 3. Key API Endpoints

### Purchase Request → PO Flow (Session #11.19)
```
POST /api/dewi/procurement/requests          — create PR
GET  /api/dewi/procurement/requests          — list PRs
PUT  /api/dewi/procurement/requests/{id}/approve — approve PR
POST /api/dewi/procurement/requests/{id}/create-po — convert PR → PO
GET  /api/rahaza/pos                         — list POs
POST /api/rahaza/pos                         — create PO directly
GET  /api/rahaza/pos/{id}                    — PO detail
PUT  /api/rahaza/pos/{id}                    — update PO
```

### Goods Receipt
```
GET  /api/rahaza/grns                        — list GRNs
POST /api/rahaza/grns                        — create GRN from PO
POST /api/rahaza/grns/{id}/confirm           — confirm receipt
GET  /api/rahaza/grns/pending-ap             — GRNs pending AP creation
```

### Accounts Payable
```
GET  /api/rahaza/ap/invoices                 — list AP invoices
POST /api/rahaza/ap/from-gr                  — create AP from GRN
POST /api/rahaza/ap/invoices/{id}/pay        — record payment
GET  /api/rahaza/ap/aging                    — AP aging report
```

### Accounts Receivable
```
GET  /api/rahaza/ar/invoices                 — list AR invoices
POST /api/rahaza/ar/invoices                 — create AR invoice
POST /api/rahaza/ar/invoices/{id}/pay        — record payment
GET  /api/rahaza/ar/360                      — AR 360° view per customer
GET  /api/rahaza/ar/aging                    — AR aging report
GET  /api/dewi/ar/overdue-scan               — overdue invoice scan
```

### GL & Journals
```
GET  /api/rahaza/journals                    — list journal entries
POST /api/rahaza/journals                    — create manual journal
GET  /api/rahaza/coa                         — chart of accounts
POST /api/rahaza/coa                         — create account
GET  /api/rahaza/fin-reports/pl              — P&L report
GET  /api/rahaza/fin-reports/balance-sheet   — balance sheet
GET  /api/rahaza/fin-reports/cashflow        — cashflow statement
```

### Bank Reconciliation
```
GET  /api/dewi/bank-recon/sessions           — list sessions
POST /api/dewi/bank-recon/sessions           — start new session
POST /api/dewi/bank-recon/sessions/{id}/match — match transaction
GET  /api/dewi/bank-recon/unmatched          — unmatched items
```

### Budget
```
GET  /api/rahaza/budget                      — list budgets
POST /api/rahaza/budget                      — create budget line
GET  /api/rahaza/budget/vs-actual            — budget vs actual
```

### AI Cashflow
```
GET  /api/dewi/cashflow-ai/analysis          — AI cashflow analysis
POST /api/dewi/cashflow-ai/forecast          — AI cashflow forecast
```

---

## 4. Key Frontend Modules

| Module File | Portal Nav ID | Description |
|---|---|---|
| `FinanceDashboard.jsx` | `finance-dashboard` | Finance overview & KPIs |
| `ARLifecycleModule.jsx` | `finance-ar` | AR 360° lifecycle view |
| `BudgetModule.jsx` | `finance-budget` | Budget management |
| `FixedAssetsModule.jsx` | `finance-fixed-assets` | Fixed asset register |
| `BankReconciliationModule.jsx` | `finance-bank-recon` | Bank reconciliation |
| `FinancialRecapModule.jsx` | `finance-recap` | Financial reports (P&L, BS) |
| `ProcurementModule.jsx` | `procurement` | PR → PO workflow |
| `PurchaseRequestModule.jsx` | `proc-requests` | Purchase requests |
| `PurchaseOrderModule.jsx` | `proc-pos` | Purchase orders |

---

## 5. Business Flows

### P2P (Procure to Pay)
```
Purchase Request (dewi_purchase_requests)
  → Approval (approval chain — optional)
  → Convert to PO (rahaza_pos)
  → GRN (rahaza_grns) — receive goods
  → AP Invoice (rahaza_ap_invoices)
  → AP Payment → GL Entry (Dr AP / Cr Bank)
```

### O2C (Order to Cash)
```
Customer Order (rahaza_orders)
  → Production / Delivery
  → AR Invoice (rahaza_ar_invoices)
  → AR Payment Receipt
  → GL Entry (Dr Bank / Cr AR)
  → Bank Reconciliation
```

### Payroll GL Posting (auto on finalize)
```
Payroll Run finalized → post_payroll_payment():
  Dr 2-1200 Hutang Gaji / Cr [bank_code]
Pay BPJS → payroll-runs/{id}/pay-bpjs:
  Dr Hutang BPJS / Cr Bank
Pay PPh21 → payroll-runs/{id}/pay-pph21:
  Dr Hutang PPh21 / Cr Bank
```

---

## 6. Auto-Posting Profiles

`rahaza_posting_profiles` collection configures automatic GL entries:

| Event | Dr Account | Cr Account |
|---|---|---|
| GRN Confirmation | Inventory/Materials | AP Payable |
| AP Payment | AP Payable | Bank |
| AR Invoice | AR Receivable | Revenue |
| AR Payment | Bank | AR Receivable |
| Material Issue | WIP | Inventory |
| Payroll Finalize | Salary Expense | Salary Payable |
| BPJS Payment | BPJS Payable | Bank |

---

## 7. Key Backend Files

| File | Purpose |
|---|---|
| `routes/dewi_procurement.py` | PR → PO procurement flow |
| `routes/rahaza_po.py` | Purchase Order management |
| `routes/rahaza_ap_from_gr.py` | AP from GRN auto-creation |
| `routes/rahaza_ar_360.py` | AR 360° view |
| `routes/rahaza_finance.py` | Finance core (AR/AP CRUD) |
| `routes/rahaza_fin_reports.py` | Financial reports (P&L, BS, CF) |
| `routes/rahaza_journals.py` | GL journal entries |
| `routes/rahaza_coa.py` | Chart of accounts |
| `routes/rahaza_budget.py` | Budget management |
| `routes/rahaza_bank_reconciliation.py` | Bank reconciliation |
| `routes/rahaza_posting.py` | Auto-posting profiles & execution |
| `routes/rahaza_posting_profiles.py` | Posting profile config |
| `routes/rahaza_fixed_assets.py` | Fixed asset register + depreciation |
| `routes/dewi_cashflow_ai.py` | AI cashflow analysis |
| `routes/dewi_bank_reconciliation.py` | Bank recon UI endpoints |

---

## 8. Recent Relevant Sessions

- **#11.19 (2026-05-27):** PR → PO full workflow (create PR, convert to PO, approval chain)
- **#11.16 Phase B (2026-05-25):** Finance collection consolidation via deprecation stub
- **Session #2 (2026-05-23):** AR 360° view, AR lifecycle module
- **Session #28 (2026-05):** BPJS/PPh21 payment GL entries, payroll GL posting

---

## 9. Notes

- PO numbers: `PO-YYYYMMDD-NNN` (daily counter via `counters` SSOT, namespace='generic')
- AP numbers: `AP-YYMM-NNNN` (monthly counter via `counters` SSOT)
- AR invoice overdue scan: scheduled daily at 01:00 via `job_scan_overdue_invoices()`
- Finance migration (Session #11.16 Phase B): legacy finance routes wrapped via deprecation stub; actual data now in SSOT collections
