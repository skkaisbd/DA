# 🧪 COMPREHENSIVE FINANCE PORTAL TESTING PLAN
## CV. Dewi Aditya ERP - Finance Module Testing

---

## 📋 TEST SCOPE

Testing akan mencakup **SEMUA modul** di Portal Finance dengan simulate user activities:

### 🎯 KATEGORI TESTING

**1. TRANSAKSI (AR & AP)** - 6 modules
**2. KAS & PEMBAYARAN** - 8 modules  
**3. AKUNTANSI & LAPORAN** - 19 modules
**TOTAL:** 33 Finance Modules

---

## 🔍 DETAILED TEST SCENARIOS

### A. TRANSAKSI (AR & AP)

#### 1. Dashboard Keuangan (`finance-dashboard`)
**Test Scenarios:**
- TS-F001: Load dashboard → Verify KPI cards rendering
- TS-F002: Check revenue vs expense chart
- TS-F003: Verify cash flow metrics
- TS-F004: Test date range filter
- TS-F005: Check responsive layout (mobile/desktop)

**Expected Behavior:**
- Dashboard loads within 3 seconds
- All charts render without error
- KPI numbers are calculated correctly
- Filter updates data dynamically

#### 2. Invoice Penjualan AR (`fin-ar-invoices`)
**Test Scenarios:**
- TS-F006: View list of AR invoices
- TS-F007: Create new AR invoice (manual entry)
- TS-F008: Edit draft invoice
- TS-F009: Post invoice to GL
- TS-F010: Record payment for invoice
- TS-F011: Mark invoice as paid
- TS-F012: Cancel invoice
- TS-F013: Export invoice to PDF
- TS-F014: Filter invoices by status (draft/posted/paid/overdue)
- TS-F015: Search invoice by customer name

**Expected Behavior:**
- CRUD operations work without error
- GL posting creates journal entries
- Payment recording updates outstanding amount
- Status transitions follow business rules
- PDF generation includes all invoice details

#### 3. AR 360° (`fin-ar-360`)
**Test Scenarios:**
- TS-F016: View aging report (0-30, 31-60, 61-90, >90 days)
- TS-F017: Customer statement generation
- TS-F018: Overdue alert visualization
- TS-F019: Export aging report to Excel

**Expected Behavior:**
- Aging buckets calculated correctly
- Statement shows all transactions for customer
- Alerts show only overdue invoices

#### 4. Permintaan Pengadaan PR (`fin-procurement-requests`)
**Test Scenarios:**
- TS-F020: Create procurement request
- TS-F021: Submit for approval
- TS-F022: Approve/Reject PR
- TS-F023: Convert approved PR to PO

**Expected Behavior:**
- Approval workflow triggers correctly
- Status changes reflected in real-time

#### 5. 3-Way Match (`fin-3way-match`)
**Test Scenarios:**
- TS-F024: View PO without GRN
- TS-F025: View GRN without Invoice
- TS-F026: Match PO-GRN-Invoice
- TS-F027: Flag quantity variance
- TS-F028: Flag price variance
- TS-F029: Approve matched set

**Expected Behavior:**
- Variances calculated accurately
- Tolerance rules applied
- Approval required for variance > threshold

#### 6. Persetujuan Invoice (`fin-approval`)
**Test Scenarios:**
- TS-F030: View pending invoices
- TS-F031: Approve invoice
- TS-F032: Reject invoice with notes
- TS-F033: View approval history

**Expected Behavior:**
- Only authorized users can approve
- Rejection notes stored
- Email notification sent (if configured)

---

### B. KAS & PEMBAYARAN

#### 7. Kas & Bank (`fin-cash`)
**Test Scenarios:**
- TS-F034: View all bank accounts
- TS-F035: Add new bank account
- TS-F036: Record cash receipt
- TS-F037: Record cash disbursement
- TS-F038: View transaction history per account

**Expected Behavior:**
- Account balance updated after transaction
- Transaction list sorted by date desc

#### 8. Kas Kecil (`fin-petty-cash`)
**Test Scenarios:**
- TS-F039: Create petty cash fund
- TS-F040: Record petty cash expense
- TS-F041: Replenish petty cash
- TS-F042: View petty cash report

**Expected Behavior:**
- Fund balance tracked accurately
- Replenishment resets balance

#### 9. Transfer Bank (`fin-bank-transfer`)
**Test Scenarios:**
- TS-F043: Create internal transfer (bank to bank)
- TS-F044: Create external transfer (to vendor)
- TS-F045: Record transfer fee
- TS-F046: Cancel transfer (before execution)

**Expected Behavior:**
- Source account debited
- Destination account credited
- Transfer fee recorded as expense

#### 10. Rekonsiliasi Bank (`fin-bank-recon`)
**Test Scenarios:**
- TS-F047: Import bank statement (CSV/Excel)
- TS-F048: Auto-match transactions
- TS-F049: Manual match transaction
- TS-F050: Flag unmatched items
- TS-F051: Finalize reconciliation
- TS-F052: View recon history

**Expected Behavior:**
- Auto-match finds >80% matches
- Manual match allows user override
- Final balance = book balance + unmatched

#### 11. AI Cash Flow Prediction (`fin-ai-cashflow`)
**Test Scenarios:**
- TS-F053: Generate 30-day forecast
- TS-F054: Generate 90-day forecast
- TS-F055: View forecast accuracy score
- TS-F056: Export forecast to Excel

**Expected Behavior:**
- Forecast based on historical patterns
- Confidence interval shown
- Alerts for predicted negative balance

#### 12. Pengeluaran (`fin-expenses`)
**Test Scenarios:**
- TS-F057: Record operational expense
- TS-F058: Categorize expense
- TS-F059: Attach receipt (image upload)
- TS-F060: Submit expense for approval
- TS-F061: Approve expense
- TS-F062: Post expense to GL

**Expected Behavior:**
- Image upload works (max 5MB)
- Expense categories from master data
- GL posting creates debit/credit entries

#### 13. Klaim Karyawan (`fin-expense-settlement`)
**Test Scenarios:**
- TS-F063: View pending employee claims
- TS-F064: Review claim details (receipts)
- TS-F065: Approve claim for payment
- TS-F066: Reject claim with reason
- TS-F067: Process batch payment
- TS-F068: Mark claims as paid

**Expected Behavior:**
- Receipt images displayed correctly
- Approval workflow followed
- Batch payment creates journal entry

#### 14. Queue Settlement Dinas (`fin-settlement-queue`)
**Test Scenarios:**
- TS-F069: View pending travel settlements
- TS-F070: Process settlement
- TS-F071: Calculate per diem (auto)
- TS-F072: Mark as completed

**Expected Behavior:**
- Per diem calculation based on config
- Settlement updates employee advance

---

### C. AKUNTANSI & LAPORAN

#### 15. Pusat Biaya (`fin-cost-centers`)
**Test Scenarios:**
- TS-F073: Create cost center
- TS-F074: Edit cost center
- TS-F075: Assign cost center to transaction
- TS-F076: View cost center report

**Expected Behavior:**
- Cost center hierarchy supported
- Transactions grouped by cost center

#### 16. HPP / Costing (`fin-hpp`)
**Test Scenarios:**
- TS-F077: Calculate COGS for production order
- TS-F078: View material cost breakdown
- TS-F079: View labor cost breakdown
- TS-F080: View overhead allocation
- TS-F081: Compare standard vs actual cost

**Expected Behavior:**
- COGS = Material + Labor + Overhead
- Variance highlighted if >5%

#### 17. Rekap Keuangan (`fin-recap`)
**Test Scenarios:**
- TS-F082: Generate monthly recap
- TS-F083: Compare month-over-month
- TS-F084: Export recap to PDF

**Expected Behavior:**
- Recap shows revenue, cost, profit
- MoM comparison shows % change

#### 18. Bagan Akun COA (`fin-coa`)
**Test Scenarios:**
- TS-F085: View COA tree structure
- TS-F086: Add new account
- TS-F087: Edit account properties
- TS-F088: Deactivate account
- TS-F089: Search account by code/name
- TS-F090: Export COA to Excel

**Expected Behavior:**
- Tree structure navigable
- Account type constraints enforced (Asset/Liability/etc)
- Search instant (< 500ms)

#### 19. Jurnal Umum (`fin-journal-entry`)
**Test Scenarios:**
- TS-F091: Create manual journal entry
- TS-F092: Add debit line item
- TS-F093: Add credit line item
- TS-F094: Verify debit = credit (balanced)
- TS-F095: Post journal to GL
- TS-F096: Reverse journal entry
- TS-F097: Attach supporting document

**Expected Behavior:**
- Entry must balance before posting
- Posted entries cannot be edited
- Reversal creates opposite entry

#### 20. Daftar Jurnal (`fin-journal-list`)
**Test Scenarios:**
- TS-F098: View all journals
- TS-F099: Filter by date range
- TS-F100: Filter by status (draft/posted)
- TS-F101: Search by reference number
- TS-F102: Export journal list to Excel

**Expected Behavior:**
- List paginated (50 per page)
- Filter updates instantly

#### 21. Profil Posting GL (`fin-posting-profiles`)
**Test Scenarios:**
- TS-F103: Create posting profile
- TS-F104: Map transaction type to GL accounts
- TS-F105: Edit posting profile
- TS-F106: Test posting profile (dry run)

**Expected Behavior:**
- Profile ensures consistent GL posting
- Dry run shows journal preview

#### 22. GL Mapping Expense (`fin-gl-mapping-config`)
**Test Scenarios:**
- TS-F107: Map expense category to GL account
- TS-F108: Test mapping with sample expense
- TS-F109: Update mapping

**Expected Behavior:**
- Mapping used for auto-posting expense

#### 23. Master Kategori Expense (`fin-expense-category-master`)
**Test Scenarios:**
- TS-F110: Create expense category
- TS-F111: Edit category
- TS-F112: Deactivate category

**Expected Behavior:**
- Categories appear in expense dropdown

#### 24. Periode Akuntansi (`fin-periods`)
**Test Scenarios:**
- TS-F113: Create new fiscal year
- TS-F114: Open period for posting
- TS-F115: Close period (lock posting)
- TS-F116: Reopen period (with permission)

**Expected Behavior:**
- Cannot post to closed period
- Period must be sequential

#### 25. Neraca Saldo TB (`fin-trial-balance`)
**Test Scenarios:**
- TS-F117: Generate trial balance for period
- TS-F118: Verify total debit = total credit
- TS-F119: Drill down to account detail
- TS-F120: Export TB to Excel

**Expected Behavior:**
- Report balanced
- Drill-down shows transactions

#### 26. Buku Besar GL (`fin-general-ledger`)
**Test Scenarios:**
- TS-F121: View GL for single account
- TS-F122: Filter by date range
- TS-F123: View running balance
- TS-F124: Export GL to PDF

**Expected Behavior:**
- Transactions sorted chronologically
- Running balance calculated correctly

#### 27. Laba Rugi P&L (`fin-pnl`)
**Test Scenarios:**
- TS-F125: Generate P&L for month
- TS-F126: Generate P&L for quarter
- TS-F127: Generate P&L for year
- TS-F128: Compare periods (YoY, MoM)
- TS-F129: Export P&L to PDF

**Expected Behavior:**
- Revenue - Expense = Net Income
- Comparison shows variance

#### 28. Neraca (`fin-balance-sheet`)
**Test Scenarios:**
- TS-F130: Generate balance sheet
- TS-F131: Verify Assets = Liabilities + Equity
- TS-F132: View as of specific date
- TS-F133: Export to PDF

**Expected Behavior:**
- Report balanced
- Date selector works

#### 29. Laporan Arus Kas (`fin-cash-flow`)
**Test Scenarios:**
- TS-F134: Generate cash flow statement
- TS-F135: View by category (Operating/Investing/Financing)
- TS-F136: Compare periods
- TS-F137: Export to Excel

**Expected Behavior:**
- Cash flow = Cash in - Cash out
- Categories properly classified

#### 30. Aging Hutang AP (`fin-ap-aging`)
**Test Scenarios:**
- TS-F138: View AP aging report
- TS-F139: Group by vendor
- TS-F140: Filter by due date
- TS-F141: Export to Excel

**Expected Behavior:**
- Aging buckets accurate
- Vendor list complete

#### 31. Anggaran Budget (`fin-budget`)
**Test Scenarios:**
- TS-F142: Create annual budget
- TS-F143: Allocate budget by cost center
- TS-F144: Compare actual vs budget
- TS-F145: View variance report

**Expected Behavior:**
- Variance = Actual - Budget
- Alerts for >10% variance

#### 32. Aset Tetap (`fin-fixed-assets`)
**Test Scenarios:**
- TS-F146: Register new fixed asset
- TS-F147: Calculate depreciation (straight line)
- TS-F148: Calculate depreciation (declining balance)
- TS-F149: View asset register
- TS-F150: Dispose asset

**Expected Behavior:**
- Depreciation posted monthly
- Asset value decreases over time
- Disposal creates gain/loss

#### 33. Executive Report Hub (`fin-executive-report`)
**Test Scenarios:**
- TS-F151: View executive dashboard
- TS-F152: Download executive summary PDF
- TS-F153: View key metrics (KPI)

**Expected Behavior:**
- Dashboard aggregates all finance KPIs
- PDF includes charts

---

### D. OPERASI KHUSUS (PHASE B)

#### 34. Pencatatan Akrual (`fin-accruals`)
**Test Scenarios:**
- TS-F154: Record expense accrual
- TS-F155: Record revenue accrual
- TS-F156: Reverse accrual

**Expected Behavior:**
- Accrual creates adjusting entry
- Reversal in next period

#### 35. Depresiasi Aset Batch (`fin-asset-depreciation`)
**Test Scenarios:**
- TS-F157: Run batch depreciation for month
- TS-F158: Preview depreciation entries
- TS-F159: Post depreciation to GL

**Expected Behavior:**
- All assets depreciated in batch
- Journal entry created

#### 36. Hapus Buku Piutang Macet (`fin-bad-debt-writeoff`)
**Test Scenarios:**
- TS-F160: Identify bad debt invoice
- TS-F161: Write off invoice
- TS-F162: Post to bad debt expense

**Expected Behavior:**
- AR balance reduced
- Bad debt expense increased

#### 37. Pelepasan Aset Tetap (`fin-asset-disposal`)
**Test Scenarios:**
- TS-F163: Record asset disposal (sale)
- TS-F164: Calculate gain/loss on disposal
- TS-F165: Post disposal journal

**Expected Behavior:**
- Asset removed from register
- Gain/loss posted to P&L

#### 38. Diskon Pembelian AP (`fin-purchase-discount`)
**Test Scenarios:**
- TS-F166: Apply early payment discount
- TS-F167: Calculate discount amount
- TS-F168: Post discount to GL

**Expected Behavior:**
- AP reduced by discount
- Discount income recorded

---

## 📊 TEST EXECUTION PRIORITY

### 🔴 CRITICAL (Must Work) - P0
- Dashboard loading
- AR Invoice CRUD
- Journal Entry posting
- Trial Balance accuracy
- P&L generation
- Balance Sheet balance check

### 🟡 HIGH (Core Features) - P1
- Bank reconciliation
- Expense approval workflow
- Cost center assignment
- COA management
- Cash flow statement

### 🟢 MEDIUM (Important) - P2
- AI Cash flow prediction
- 3-way match
- Executive reports
- Asset depreciation batch

### ⚪ LOW (Nice to Have) - P3
- PDF exports
- Excel exports
- Period comparison charts

---

## 🎯 SUCCESS CRITERIA

### Functional Requirements
- ✅ All CRUD operations work without error
- ✅ No console errors in browser
- ✅ Data persists correctly in MongoDB
- ✅ Calculations are mathematically accurate
- ✅ Workflows follow business logic

### Performance Requirements
- ✅ Page load < 3 seconds
- ✅ API response < 2 seconds
- ✅ No memory leaks
- ✅ Smooth UI interactions (60fps)

### Data Integrity
- ✅ Trial Balance always balanced
- ✅ Balance Sheet: Assets = Liabilities + Equity
- ✅ Journal entries always balanced (Debit = Credit)
- ✅ No orphaned transactions
- ✅ Referential integrity maintained

---

## 🔧 TEST EXECUTION METHOD

**Testing Agent will be used for:**
- Comprehensive UI testing with Playwright
- User flow simulation
- Screenshot verification
- Console error detection

**Manual verification for:**
- Financial calculation accuracy
- Report formatting
- Business logic compliance

---

**Test Plan Created:** 2 Juni 2026  
**Total Test Scenarios:** 168 scenarios  
**Estimated Testing Time:** 2-3 hours  
**Testing Tool:** testing_agent_v3 + Manual Analysis
