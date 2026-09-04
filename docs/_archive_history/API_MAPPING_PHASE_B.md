# API Mapping Phase B: 8 Frontend UI Modules

## Status: FINAL MAPPING - Ready for Implementation

Created: 2026-06-01
Last Updated: 2026-06-01

---

## Overview
Dokumen ini memetakan 8 modul frontend baru dengan backend API endpoints yang sudah ada dan terverifikasi. Semua endpoint sudah di-forensic audit dan 100% functional.

---

## Module 1: AccrualsModule (Pencatatan Akrual)

### Frontend File
`/app/frontend/src/components/erp/AccrualsModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/finance/accruals`
**File:** `/app/backend/routes/rahaza_accruals.py` (terverifikasi ada)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/rahaza/finance/accruals` | List semua accrual entries | Query params: `?from=YYYY-MM-DD&to=YYYY-MM-DD&type=income/expense` | Array of accrual objects |
| POST | `/api/rahaza/finance/accruals` | Create new accrual entry | `{period, type, description, amount, account_id}` | Accrual object |
| PUT | `/api/rahaza/finance/accruals/{id}` | Update accrual | Same as POST | Updated object |
| DELETE | `/api/rahaza/finance/accruals/{id}` | Delete accrual | - | `{status: "ok"}` |
| POST | `/api/rahaza/finance/accruals/{id}/reverse` | Reverse accrual entry | `{reversal_date}` | Reversed entry |

### Data Schema
```javascript
{
  id: string,
  period: "2026-06",           // YYYY-MM
  type: "income" | "expense",
  description: string,
  amount: number,
  account_id: string,          // FK to COA
  account_code: string,
  account_name: string,
  status: "active" | "reversed",
  reversed_at: datetime | null,
  created_by: string,
  created_at: datetime
}
```

### UI Features Required
- Table dengan filter by period, type, status
- Form modal untuk create/edit
- Reverse action dengan konfirmasi
- Export to Excel button
- Summary cards: Total Income Accruals, Total Expense Accruals

### Icon & Navigation
- Icon: `FileText` from lucide-react
- Portal: `finance`
- Module ID: `fin-accruals`
- Label: "Pencatatan Akrual"

---

## Module 2: AssetDepreciationModule (Depresiasi Batch Aset)

### Frontend File
`/app/frontend/src/components/erp/AssetDepreciationModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/finance/fixed-assets`
**File:** `/app/backend/routes/rahaza_fixed_assets.py` (VERIFIED ✓)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/rahaza/finance/fixed-assets/depreciation-due` | Aset yang butuh posting depresiasi | - | Array of due depreciation schedules |
| POST | `/api/rahaza/finance/fixed-assets/run-batch-depreciation` | **RUN BATCH DEPRECIATION** | `{period: "2026-06", asset_ids: [], auto_post: true}` | Batch result with summary |
| GET | `/api/rahaza/finance/fixed-assets/depreciation-summary?period=2026-06` | Summary depresiasi per periode | Query: `?period=YYYY-MM` | Summary stats |
| GET | `/api/rahaza/finance/fixed-assets` | List all assets | Query: `?status=active&category=mesin` | Array of assets |
| POST | `/api/rahaza/finance/fixed-assets/{id}/post-depr/{period}` | Manual post single asset depreciation | - | Posted result |

### Data Schema
```javascript
// Batch Depreciation Request
{
  period: "2026-06",            // YYYY-MM
  asset_ids: [],                // Empty = all active assets
  auto_post: true               // Auto-post to GL
}

// Batch Result
{
  ok: true,
  period: "2026-06",
  assets_processed: 15,
  posted_count: 14,
  total_depreciation: 8500000,
  results: [
    {
      asset_id: string,
      asset_code: string,
      asset_name: string,
      status: "posted" | "already_posted" | "error" | "skipped",
      depr_amount: number,
      je_number: string,
      reason: string              // If error/skipped
    }
  ]
}
```

### UI Features Required
- Period selector (Month picker: YYYY-MM)
- Asset selector (multi-select with "Select All")
- Preview table: asset list with estimated depreciation amounts
- "Run Batch Depreciation" button with progress indicator
- Result table showing success/errors per asset
- Summary cards: Total Assets, Total Depreciation, Success Rate
- Export batch result to PDF

### Icon & Navigation
- Icon: `Calculator` from lucide-react
- Portal: `finance`
- Module ID: `fin-asset-depreciation`
- Label: "Depresiasi Aset (Batch)"

---

## Module 3: BadDebtWriteOffModule (Hapus Buku Piutang Macet)

### Frontend File
`/app/frontend/src/components/erp/BadDebtWriteOffModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/finance` (verified in `rahaza_finance.py`)
**File:** `/app/backend/routes/rahaza_finance.py` (VERIFIED ✓ - Line 320-471)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/rahaza/finance/ar-invoices/overdue-report?days=30` | List overdue AR invoices | Query: `?days=30` (minimum overdue days) | Overdue report with aging buckets |
| POST | `/api/rahaza/finance/ar-invoices/{id}/write-off-bad-debt` | **WRITE OFF BAD DEBT** | `{reason: string, write_off_date: "2026-06-01"}` | Updated invoice + GL posting result |
| GET | `/api/rahaza/finance/ar-invoices?status=overdue` | List AR invoices | Query: `?status=overdue&customer_id=xxx` | Array of invoices |
| GET | `/api/rahaza/finance/ar-aging` | AR aging report | - | Aging buckets summary |

### Data Schema
```javascript
// Write-Off Request
{
  reason: string,                // MANDATORY for audit trail
  write_off_date: "2026-06-01"   // Optional, default: today
}

// Invoice Object (After Write-Off)
{
  id: string,
  invoice_number: string,
  customer_id: string,
  customer_name: string,
  total: number,
  balance: number,
  status: "written_off",
  write_off_date: string,
  write_off_reason: string,
  write_off_amount: number,
  write_off_by: string,
  write_off_by_name: string,
  write_off_at: datetime,
  _posting_result: {ok: boolean, je_id: string, je_number: string}
}

// Overdue Report Response
{
  summary: {
    total_overdue_invoices: number,
    total_overdue_amount: number,
    high_risk_count: number,      // >180 days
    high_risk_amount: number
  },
  invoices: [
    {
      id, invoice_number, customer_id,
      due_date, overdue_days, balance,
      aging_bucket: "0-30 days" | "31-60 days" | "61-90 days" | "91-180 days" | ">180 days (bad debt candidate)"
    }
  ]
}
```

### UI Features Required
- **Overdue Report Table** with aging bucket badges
- Filter by: aging bucket, customer, minimum overdue days
- **Write-Off Action** button per row (with confirmation dialog)
- Write-off form modal: reason (required), write-off date
- Highlight high-risk invoices (>180 days) with red badge
- Summary cards: Total Overdue, High Risk Count, High Risk Amount
- Export to Excel with aging analysis

### Icon & Navigation
- Icon: `ShieldAlert` from lucide-react
- Portal: `finance`
- Module ID: `fin-bad-debt-writeoff`
- Label: "Hapus Buku Piutang Macet"

---

## Module 4: SalesDiscountModule (Diskon Penjualan)

### Frontend File
`/app/frontend/src/components/erp/SalesDiscountModule.jsx`

### Backend Endpoints
**Base Route:** `/api/marketing/discounts`
**File:** `/app/backend/routes/marketing_discounts_routes.py` (VERIFIED ✓)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/marketing/discounts` | List discount campaigns | Query: `?page=1&page_size=20&status=active&platform=shopee&search=xxx` | Paginated discounts |
| GET | `/api/marketing/discounts/summary` | Summary statistics | - | Stats by platform, status |
| GET | `/api/marketing/discounts/types` | Get discount types | - | Array of discount types |
| POST | `/api/marketing/discounts` | Create discount campaign | `{account_name, platform, name, discount_type, discount_value, start_date, end_date, ...}` | Created discount |
| PUT | `/api/marketing/discounts/{id}` | Update discount | Same as POST (partial) | Updated discount |
| DELETE | `/api/marketing/discounts/{id}` | Delete discount | - | `{success: true}` |

### Data Schema
```javascript
{
  id: string,
  account_id: string,                     // FK to marketing_platform_accounts
  account_name: string,
  platform: "shopee" | "tiktok" | "tokopedia" | "instagram" | "semua_platform",
  name: string,
  discount_type: "flash_sale" | "voucher" | "bundling" | "buy_x_get_y" | "free_shipping" | "diskon_persen" | "cashback" | "giveaway",
  discount_type_label: string,
  discount_value: number,
  discount_unit: "persen" | "nominal" | "unit",
  min_purchase: number,
  max_discount: number,
  start_date: "2026-06-01",
  end_date: "2026-06-15",
  status: "active" | "upcoming" | "expired",     // Auto-computed
  days_remaining: number | null,
  description: string,
  product_scope: "semua_produk" | string,
  created_by: string,
  created_at: datetime
}
```

### UI Features Required
- **Discount Campaign Table** with status badges (active: green, upcoming: blue, expired: gray)
- Filter by: platform, status, discount_type, account
- Create/Edit form modal dengan:
  - Account & Platform selector
  - Discount type dropdown
  - Value + Unit (%, Nominal Rp, Unit)
  - Date range picker (start_date - end_date)
  - Min purchase & max discount (optional)
- **"Days Remaining" indicator** for active campaigns
- **"Expiring Soon" warning** badge (< 3 days remaining)
- Summary cards: Total Campaigns, Active, Upcoming, Expiring Soon
- Platform distribution chart (pie/donut)

### Icon & Navigation
- Icon: `Tag` from lucide-react
- Portal: `toko` (Marketing Portal)
- Module ID: `marketing-discounts` (ALREADY EXISTS in registry - re-use)
- Label: "Kampanye Diskon"

**NOTE**: `marketing-discounts` sudah ada di moduleRegistry.js (line 792), jadi modul ini TIDAK perlu didaftarkan lagi. Kita hanya perlu membuat component baru `SalesDiscountModule.jsx` yang cleaner untuk fokus diskon penjualan.

---

## Module 5: AssetDisposalModule (Pelepasan Aset)

### Frontend File
`/app/frontend/src/components/erp/AssetDisposalModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/finance/fixed-assets`
**File:** `/app/backend/routes/rahaza_fixed_assets.py` (VERIFIED ✓ - Line 383-427)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/rahaza/finance/fixed-assets?status=active` | List active assets | Query: `?status=active&category=xxx&search=xxx` | Array of active assets |
| GET | `/api/rahaza/finance/fixed-assets/{id}` | Get asset detail | - | Asset object with NBV |
| POST | `/api/rahaza/finance/fixed-assets/{id}/dispose` | **DISPOSE ASSET** | `{disposal_date, disposal_value, notes}` | Disposal result + GL posting |
| GET | `/api/rahaza/finance/fixed-assets?status=disposed` | List disposed assets (history) | Query: `?status=disposed` | Array of disposed assets |

### Data Schema
```javascript
// Disposal Request
{
  disposal_date: "2026-06-01",    // Optional, default: today
  disposal_value: number,          // Selling price (could be 0)
  notes: string                    // Reason for disposal
}

// Disposal Response
{
  ok: true,
  gain_loss: number,               // disposal_value - NBV (+ = gain, - = loss)
  nbv_at_disposal: number,
  posting_result: {
    ok: boolean,
    je_id: string,
    je_number: string,
    error: string                  // If posting failed
  }
}

// Asset Object (Post-Disposal)
{
  id, code, name, category,
  purchase_cost, residual_value,
  accumulated_depreciation, book_value_current,
  status: "disposed",
  disposed_at: datetime,
  disposal_date: string,
  disposal_value: number,
  disposal_notes: string,
  disposal_gain_loss: number,
  nbv_at_disposal: number
}
```

### UI Features Required
- **Active Assets Table** dengan:
  - Filter by category, search by code/name
  - Columns: Code, Name, Category, Purchase Cost, NBV, Purchase Date
  - "Dispose" action button per row
- **Disposal Form Modal**:
  - Asset info display (read-only): code, name, current NBV
  - Disposal date picker
  - Disposal value input (Rp)
  - Notes textarea (required - reason for disposal)
  - Calculated Gain/Loss preview (disposal_value - NBV)
- **Disposal History Tab** (tab kedua):
  - Table of disposed assets
  - Columns: Code, Name, Disposal Date, NBV at Disposal, Disposal Value, Gain/Loss
- Summary cards: Total Active Assets, Total Disposed This Month, Avg Disposal Gain/Loss

### Icon & Navigation
- Icon: `PackageMinus` from lucide-react
- Portal: `finance`
- Module ID: `fin-asset-disposal`
- Label: "Pelepasan Aset Tetap"

---

## Module 6: PurchaseDiscountModule (Diskon Pembelian / AP Payment Discount)

### Frontend File
`/app/frontend/src/components/erp/PurchaseDiscountModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/finance/ap-invoices`
**File:** `/app/backend/routes/rahaza_finance.py` (VERIFIED ✓)

**NOTE**: Tidak ada endpoint khusus untuk "purchase discount" karena ini adalah **fitur early payment discount yang diterapkan saat AP payment**. Modul ini akan menampilkan:
1. List AP invoices yang eligible untuk early payment discount
2. Form payment dengan opsi apply discount jika bayar sebelum tanggal tertentu

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/rahaza/finance/ap-invoices?status=sent` | List unpaid AP invoices | Query: `?status=sent&vendor=xxx` | Array of AP invoices |
| POST | `/api/rahaza/finance/ap-invoices/{id}/payment` | Record AP payment (dengan optional discount) | `{amount, discount_amount, account_id, date, notes}` | Updated invoice + GL posting |
| GET | `/api/rahaza/finance/ap-invoices/{id}` | Get invoice detail | - | AP invoice object |

### Data Schema
```javascript
// AP Payment Request (with discount)
{
  amount: number,                 // Payment amount AFTER discount
  discount_amount: number,        // Early payment discount (optional)
  account_id: string,             // Cash account ID
  date: "2026-06-01",
  notes: string
}

// AP Invoice Object
{
  id, invoice_number, vendor_name,
  issue_date, due_date,
  subtotal, tax_amount, total,
  paid_amount, balance,
  status: "draft" | "sent" | "partial_paid" | "paid",
  items: [{description, qty, unit, price, amount}],
  // Early payment discount fields (jika ada)
  discount_terms: {
    discount_percent: number,      // e.g., 2%
    discount_days: number,         // e.g., 10 days from issue_date
    discount_deadline: string      // Calculated: issue_date + discount_days
  }
}
```

### UI Features Required
- **AP Invoices Table** dengan filter:
  - Show invoices with status "sent" or "partial_paid" (unpaid/partially paid)
  - Highlight invoices eligible untuk early payment discount (before discount deadline)
  - Columns: Invoice No, Vendor, Due Date, Balance, Discount Available, Action
- **Payment Form Modal**:
  - Invoice summary (read-only)
  - Payment amount input
  - **Early Payment Discount Section** (show if eligible):
    - Discount percent available
    - Discount deadline countdown
    - Auto-calculate discounted amount
  - Account selector (cash/bank account)
  - Payment date picker
  - Notes textarea
- Summary cards: Total Unpaid AP, Discount Available This Week, Total Saved (YTD)

### Icon & Navigation
- Icon: `HandCoins` from lucide-react
- Portal: `finance`
- Module ID: `fin-purchase-discount`
- Label: "Diskon Pembelian (AP Payment)"

---

## Module 7: EmployeeLoansModule (Pinjaman Karyawan)

### Frontend File
`/app/frontend/src/components/erp/EmployeeLoansModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/hr/employee-loans`
**File:** `/app/backend/routes/rahaza_employee_loans.py` (VERIFIED ✓)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| GET | `/api/rahaza/hr/employee-loans` | List all employee loans | Query: `?status=active&employee_id=xxx` | Array of loans |
| POST | `/api/rahaza/hr/employee-loans/disburse` | **DISBURSE NEW LOAN** | `{employee_id, loan_amount, installment_amount, installment_count, disbursement_date, first_deduction_period, notes}` | Created loan + GL posting |
| GET | `/api/rahaza/hr/employee-loans/{id}` | Get loan detail + repayment history | - | Loan object with repayments array |
| POST | `/api/rahaza/hr/employee-loans/{id}/repay` | Manual repayment (cash) | `{repayment_amount, repayment_date, notes}` | Updated loan |
| POST | `/api/rahaza/hr/employee-loans/{id}/deduct-from-payroll` | Payroll deduction (auto-called from payroll) | `{payroll_run_id, period, deduction_amount}` | Deduction result |
| GET | `/api/rahaza/hr/employee-loans/outstanding-by-employee/{employee_id}` | Outstanding loans per employee | - | Employee loans summary |

### Data Schema
```javascript
// Loan Disbursement Request
{
  employee_id: string,              // MANDATORY
  loan_amount: number,              // Total loan amount
  installment_amount: number,       // Amount per installment
  installment_count: number,        // Number of installments (e.g., 10)
  disbursement_date: "2026-06-01",  // Optional, default: today
  first_deduction_period: "2026-07", // YYYY-MM (first payroll deduction)
  notes: string
}

// Loan Object
{
  id, loan_number,
  employee_id, employee_name,
  loan_amount,
  installment_amount,
  installment_count,
  paid_installments,                // Count of paid installments
  paid_amount,
  outstanding_balance,
  disbursement_date,
  first_deduction_period,
  status: "active" | "paid_off" | "written_off",
  disbursed_by, disbursed_by_name,
  disbursed_at,
  gl_disbursement_je_id,
  gl_disbursement_je_number,
  repayments: [                      // Repayment history (from detail endpoint)
    {
      id, loan_id, repayment_amount, repayment_date,
      repayment_method: "manual" | "payroll",
      payroll_run_id, period,
      notes, created_at
    }
  ]
}
```

### UI Features Required
- **Loans Table** dengan tabs:
  - Tab 1: Active Loans
  - Tab 2: Paid Off Loans
  - Filter by employee, search by loan_number
- **Disburse New Loan Button** → Form Modal:
  - Employee selector (autocomplete dari `/api/rahaza/employees`)
  - Loan amount input
  - Installment amount & count inputs (auto-calculate total)
  - Disbursement date picker
  - First deduction period selector (Month picker YYYY-MM)
  - Notes textarea
- **Loan Detail Drawer** (click row):
  - Loan summary info
  - Repayment progress bar (paid_installments / installment_count)
  - **Repayment History Table** (from `repayments` array)
  - **Manual Repayment Button** → Form modal (amount, date, notes)
- Summary cards: Total Active Loans, Total Outstanding, Total Paid This Month

### Icon & Navigation
- Icon: `HandCoins` from lucide-react
- Portal: `hr`
- Module ID: `hr-employee-loans`
- Label: "Pinjaman Karyawan"

---

## Module 8: InventoryScrapModule (Penyusutan Inventory / Inventory Adjustment)

### Frontend File
`/app/frontend/src/components/erp/InventoryScrapModule.jsx`

### Backend Endpoints
**Base Route:** `/api/rahaza/inventory`
**File:** `/app/backend/routes/rahaza_inventory_stock.py` (VERIFIED ✓ - Line 210-238)

| Method | Endpoint | Purpose | Request Body | Response |
|--------|----------|---------|--------------|----------|
| POST | `/api/rahaza/inventory/material-adjust` | **CREATE ADJUSTMENT** (scrap/write-off) | `{material_id, location_id, qty, reason}` | Movement record + GL posting |
| GET | `/api/rahaza/inventory/material-stock` | Get current stock | Query: `?material_id=xxx&location_id=xxx` | Array of stock records |
| GET | `/api/rahaza/inventory/material-movements` | List movement history (adjustments) | Query: `?type=adjust&material_id=xxx&from=xxx&to=xxx` | Array of movements |
| GET | `/api/rahaza/inventory/materials` | List materials | Query: `?type=xxx&search=xxx` | Array of materials |

### Data Schema
```javascript
// Adjustment Request (POST /api/rahaza/inventory/material-adjust)
{
  material_id: string,              // MANDATORY
  location_id: string,              // MANDATORY
  qty: number,                      // Delta qty (negative for scrap/reduction)
  reason: string                    // MANDATORY - reason for adjustment
}

// Movement Record (Response after adjustment)
{
  id, 
  type: "adjust",
  material_id,
  material_code, material_name,
  qty,                              // Delta (negative = scrap/reduction)
  from_location_id: null,
  to_location_id: string,           // Location where adjustment happened
  location_code, location_name,
  ref_type: "adjustment",
  ref_id: null,
  notes: string,                    // Contains 'reason' field
  created_by, created_by_name,
  created_at,
  _posting_result: {                // GL posting info
    ok: boolean,
    je_id: string,
    je_number: string,
    error: string
  }
}

// Stock Record (GET /api/rahaza/inventory/material-stock)
{
  id,
  material_id, material_code, material_name,
  location_id, location_code, location_name,
  qty: number,                      // Current qty
  unit: string,
  min_stock: number,
  below_min: boolean,
  low_stock_reason: string
}
```

### UI Features Required
- **Adjustment History Table**:
  - Filter by date range, material, location
  - Columns: Date, Material, Location, Qty Adjustment, Reason, Created By
  - Show negative qty in red (scrap/reduction), positive in green (addition)
- **Create Adjustment Button** → Form Modal:
  - Material selector (autocomplete dengan stock info display)
  - Current stock display per location (read-only)
  - Location selector
  - Adjustment type radio buttons:
    - **Scrap / Damaged** (negative qty)
    - **Theft / Lost** (negative qty)
    - **Found / Addition** (positive qty)
    - **Stock Count Correction** (positive or negative)
  - Qty input with validation:
    - For negative adjustments: cannot exceed current stock
    - Clear indication of direction (± symbol)
  - Reason textarea (MANDATORY - audit trail requirement)
  - Warning alert if adjustment will make stock below minimum
- **Movement Detail Drawer** (click row):
  - Full movement info
  - Before/After stock calculation (if available)
  - GL posting info (JE number, status)
- Summary cards: Total Adjustments This Month, Total Scrap Value, Most Adjusted Materials (top 5)

### Icon & Navigation
- Icon: `PackageMinus` from lucide-react
- Portal: `warehouse`
- Module ID: `wh-inventory-adjustments`
- Label: "Penyesuaian Stok (Adjustment)"

### ⚠️ IMPORTANT NOTES
- **qty field**: Use NEGATIVE value untuk scrap/reduction (e.g., -50 untuk scrap 50 unit)
- **reason field**: MANDATORY - backend akan reject jika kosong
- **Current stock validation**: Frontend harus check current stock sebelum POST untuk prevent negative stock error
- **GL Auto-posting**: Backend automatically posts GL journal entry untuk inventory adjustments

---

## Implementation Checklist

### Pre-Implementation ✓
- [x] Mapping 8 modul ke backend endpoints
- [x] Verifikasi ketersediaan endpoint di backend (8/8 FULLY VERIFIED ✅)
- [x] Dokumentasi data schema dan API contracts
- [x] Identifikasi icon & navigation placement

### Implementation Priority
1. **P0 (Fully Verified - High Business Value)**: 
   - Module 2: AssetDepreciationModule (Batch depreciation - automate monthly process)
   - Module 3: BadDebtWriteOffModule (Financial compliance requirement)
   - Module 7: EmployeeLoansModule (HR payroll integration)
   
2. **P1 (Fully Verified - Medium Priority)**: 
   - Module 1: AccrualsModule (Accounting period-end)
   - Module 5: AssetDisposalModule (Asset lifecycle management)
   - Module 8: InventoryScrapModule (Inventory write-off)
   
3. **P2 (Needs UI Design Polish)**:
   - Module 4: SalesDiscountModule (existing module - just needs enhancement if required)
   - Module 6: PurchaseDiscountModule (payment discount logic - needs UI design)

### Next Steps
1. ✅ User konfirmasi mapping
2. ✅ Verify InventoryScrapModule backend endpoint (DONE - verified in rahaza_inventory_stock.py)
3. ⏭️ View 1-2 existing module patterns untuk styling consistency
4. ⏭️ Bulk create 8 modules menggunakan `mcp_bulk_file_writer`
5. ⏭️ Register modules di `moduleRegistry.js`
6. ⏭️ Add navigation entries di `portalNav.js`
7. ⏭️ Frontend lint check
8. ⏭️ Testing via screenshot tool
9. ⏭️ Call testing agent for comprehensive validation

---

## Technical Notes

### Common Patterns (dari existing modules)
- Menggunakan `GlassCard`, `GlassPanel`, `GlassInput` dari `@/components/ui/glass`
- `PageHeader` dari `./moduleAtoms.jsx`
- Format currency: `const fmt = (n) => \`Rp ${Number(n || 0).toLocaleString('id-ID')}\``
- Authorization: `const headers = { Authorization: \`Bearer ${token}\`, 'Content-Type': 'application/json' }`
- Error handling dengan try-catch + toast notification
- Loading states dengan spinner
- Empty states dengan helpful messages
- Export buttons menggunakan `ExportButtonGroup` component (jika ada)

### Design Consistency
- Follow existing module patterns dari `RahazaCashAccountsModule.jsx`
- Gunakan `data-testid` attributes untuk semua interactive elements
- Responsive design: mobile-first approach
- Color coding: success (green), warning (yellow), error (red), info (blue)
- Shadcn components untuk form elements (Button, Input, Select, Dialog, etc.)

### Navigation Structure
```javascript
// Finance Portal
'fin-accruals'              → Portal: finance, Section: ACCOUNTING CORE
'fin-asset-depreciation'     → Portal: finance, Section: ACCOUNTING CORE
'fin-bad-debt-writeoff'      → Portal: finance, Section: ACCOUNTING CORE
'fin-asset-disposal'         → Portal: finance, Section: ACCOUNTING CORE
'fin-purchase-discount'      → Portal: finance, Section: PAYABLES & CASH

// Marketing Portal
'marketing-discounts'        → Portal: toko (Marketing), Section: CAMPAIGNS & PROMO

// HR Portal
'hr-employee-loans'          → Portal: hr, Section: PAYROLL & BENEFITS

// Warehouse Portal
'wh-inventory-scrap'         → Portal: warehouse, Section: INVENTORY MANAGEMENT
```

---

## Backend Files Reference (All Verified ✅)
- ✅ `/app/backend/routes/rahaza_accruals.py` - Accruals endpoints
- ✅ `/app/backend/routes/rahaza_fixed_assets.py` - Fixed assets + depreciation endpoints (Line 434-640: batch depreciation)
- ✅ `/app/backend/routes/rahaza_finance.py` - AR/AP + bad debt write-off (Line 320-471: bad debt feature)
- ✅ `/app/backend/routes/marketing_discounts_routes.py` - Discount campaigns
- ✅ `/app/backend/routes/rahaza_employee_loans.py` - Employee loans
- ✅ `/app/backend/routes/rahaza_inventory_stock.py` - Material stock adjustments (Line 210-238: material-adjust endpoint)

---

**Document Status**: ✅ FINAL MAPPING - FULLY VERIFIED
**Ready for Implementation**: ✅ YES (8/8 modules verified)
**User Confirmation**: ✅ CONFIRMED
