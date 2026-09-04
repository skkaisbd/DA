# FORENSIC AUDIT — 03: BUSINESS PROCESS MAP
## End-to-End Business Flow Reconstruction

**Lensa:** L2 Business Process Engineering + L5 Human-Centered + L4 Operational Efficiency

---

## METODE

Untuk setiap proses bisnis utama, di-trace:
1. **Trigger** — Apa yang memulai flow
2. **Steps** — Tahapan yang dilewati user
3. **Modules Used** — Modul UI yang terlibat
4. **DB Collections** — Source of truth di setiap tahap
5. **Pain Points** — Bottleneck, duplikasi, atau friction
6. **Verdict** — Status flow saat ini

---

## BP1: PROCURE-TO-PAY (P2P) — Material/Fabric Procurement

### Ideal Flow
```
Material Request → Purchase Requisition → PO → GR (Goods Receipt) → 
Invoice Verification → Payment
```

### Actual Implementation
| Step | Module | Collection | Status |
|------|--------|------------|--------|
| 1. Material Request | (manual via Warehouse Smart alerts) | `rahaza_alerts` | 🟡 Indirect |
| 2. Purchase Requisition | (skipped — langsung PO) | — | 🔴 Missing step |
| 3. Purchase Order | `wh-purchase-orders` (PurchaseOrderModule) | `rahaza_purchase_orders` | ✅ |
| 4. Goods Receipt (GR) | `wh-receiving` (ReceivingModule) | `warehouse_receiving` (legacy) | ⚠️ LEGACY |
| 5. GR-from-PO link | **❌ NOT IMPLEMENTED** | — | 🔴 BROKEN LINK |
| 6. GR QC Check | `wh-supplier-scorecard` (SupplierScorecardModule) | `rahaza_grn_inspections` | ✅ |
| 7. Invoice Verification | `fin-ap` (AccountsPayableModule) | `rahaza_ap_invoices` | ✅ |
| 8. Payment | `fin-payments` (PaymentModule) | `rahaza_ap_payments`, `payments` | ⚠️ 2 collections |

### Pain Points
- 🔴 **Critical:** Tidak ada button "Create GR from PO" di UI. User harus manual entry GR.
- 🔴 **Missing:** Purchase Requisition step (departemen request → approval → PO)
- ⚠️ GR pakai system legacy `warehouse_receiving`

### Verdict
**🟡 PARTIAL** — Components ada tapi link antar step rusak. **Priority: P1**.

---

## BP2: ORDER-TO-CASH (O2C) — Customer Sales

### Ideal Flow
```
Customer Order → Sales Order Approval → Stock Allocation → 
Production (if not in stock) → Pick → Pack → Ship (DO) → Invoice → Payment
```

### Actual Implementation
| Step | Module | Collection | Status |
|------|--------|------------|--------|
| 1. Customer Order | `prod-orders` (RahazaOrdersModule) | `rahaza_orders` | ✅ |
| 2. Order → WO Cascade | `prod-wizard` (ProductionWizardModule) | `rahaza_work_orders` | ✅ |
| 3. Stock Reservation | `prod-material-reservation` | `rahaza_material_reservations` | ✅ |
| 4. Production Execution | `prod-exec-*` (ProcessExecutionModule x5) | `rahaza_process_execution` | ✅ |
| 5. FG Receipt | (auto via packing exec) | `rahaza_fg_inventory`, `rahaza_fg_movements` | ✅ |
| 6. Pick List | `wh-picklist` (WMSPickListModule) | `wh_picklists` | ✅ |
| 7. Shipment Creation | `prod-shipments` (RahazaShipmentsModule) | `rahaza_shipments` | ✅ |
| 8. Delivery Note | `wms-delivery-notes` | `wh_delivery_notes` | ✅ |
| 9. AR Invoice | `fin-ar-invoices` (RahazaARInvoicesModule) | `rahaza_ar_invoices` | ✅ |
| 10. Receipt | `fin-cash` + `fin-bank-recon` | `rahaza_ar_receipts`, `bank_recon_txns` | ✅ |

### Pain Points
- ⚠️ 2 shipping systems: `prod-shipments` vs `wms-delivery-notes` (yang seharusnya 1)
- ⚠️ FG stock di-track di `rahaza_materials` (type=fg) DAN `rahaza_fg_inventory` (2 sources)

### Verdict
**🟢 OK** — Flow lengkap, hanya ada minor consolidation needed.

---

## BP3: MAKE-TO-STOCK (M2S) — Production untuk Inventory

### Ideal Flow
```
Forecast/Reorder Trigger → Production Order → WO → 
Material Issue → Production → QC → FG Receipt
```

### Actual Implementation
Mostly OK, identik dengan BP2 minus customer order trigger. 

### Verdict
**🟢 OK** — Functional via Production Wizard.

---

## BP4: MAKLON FLOW (B2B Order — Customer ORDERS to Dewi Aditya)

### Ideal Flow
```
Client Quote Request → Quote Sent → PO/Order Confirmed → 
Sample Production → Sample Approval → BOM Finalized → 
Production WO → Production Execution → QC → Dispatch → 
Invoice (Maklon) → Payment
```

### Actual Implementation
| Step | Module | Collection | Status |
|------|--------|------------|--------|
| 1. Quote | `maklon-ai-quote` (MaklonAIQuoteModule) | (LLM-generated) | ✅ (NEW) |
| 2. **Order Confirmed** | **2 OPSI:** `maklon-orders` (OLD) ATAU `maklon-po` (NEW) | `dewi_maklon_orders` (lama) ATAU `dewi_maklon_pos` (baru) | 🔴 **PARALEL!** |
| 3. Sample Management | `maklon-samples` (MaklonSampleManagement) | `dewi_maklon_samples`, `dewi_maklon_sample_revisions` | ✅ |
| 4. BOM | (linked from PO) | `dewi_maklon_bom` | ✅ |
| 5. WO Creation | (manual link to `prod-work-orders`) | `rahaza_work_orders` | ⚠️ Manual |
| 6. Production Execution | `prod-exec-*` | `rahaza_process_execution` | ✅ |
| 7. QC Maklon | `maklon-qc` (MaklonQCTracking) | `dewi_maklon_qc_checks` | ✅ |
| 8. **Maklon Packing** | **❌ BROKEN** — `maklon-packing` di sidebar tapi no component | — | 🔴 **BROKEN** |
| 9. Dispatch | (linked from PO) | `dewi_maklon_dispatches` | ✅ |
| 10. Maklon Invoice | `maklon-billing` (MaklonBillingModule) | `dewi_maklon_invoices` | ✅ |
| 11. Payment | `maklon-billing` | `dewi_maklon_payments`, `dewi_maklon_advance_payments` | ✅ |
| 12. HPP Tracking | `maklon-hpp` (MaklonHppModule) | `dewi_maklon_hpp`, `dewi_hpp_snapshots_maklon` | ✅ |

### Pain Points
- 🔴 **CRITICAL:** Dua database schema paralel untuk order yang sama (`dewi_maklon_orders` vs `dewi_maklon_pos`)
- 🔴 **Broken UI:** `maklon-cmt` dan `maklon-packing` di sidebar tapi no component
- ⚠️ Manual link antara Maklon PO → internal Work Order (tidak ada auto-cascade)

### Verdict
**🔴 BROKEN** — P0 priority untuk konsolidasi DB + fix broken menus.

---

## BP5: CMT OUTSOURCING (Dewi Aditya → External CMT Vendors)

### Ideal Flow
```
WO assigned to CMT → Material Dispatch to CMT → 
CMT Vendor Produces → Progress Reports → Receipt Back → 
QC → Payment to CMT
```

### Actual Implementation
| Step | Module | Collection | Status |
|------|--------|------------|--------|
| 1. CMT Job Assignment | `prod-cmt` (CMTManagementModule) | `dewi_cmt_jobs`, `dewi_cmt_partners` | ✅ |
| 2. Material Dispatch | **2 OPSI:** `do-management` (DOManagementModule) ATAU `wms-cmt-dispatches` (WMSCMTDispatchesModule) | `dewi_cmt_delivery_orders` ATAU `wh_cmt_dispatches` | 🔴 **PARALEL!** |
| 3. CMT Receipt | `prod-cmt-packing` (CMTPackingModule) | `cmt_receipts`, `cmt_receipt_lines` | ✅ |
| 4. Progress Tracking | `cmt-progress` (CMTProgressModule) | `dewi_cmt_progress_reports` | ⚠️ In wrong portal (Maklon, should be Production) |
| 5. Component Shortage | `production-cmt-component-requests` | `dewi_cmt_component_requests` | ✅ |
| 6. CMT Payment | `prod-cmt` (within CMTManagementModule) | `dewi_cmt_payments` | ✅ |

### Pain Points
- 🔴 **2 dispatch systems paralel** (DO vs WMS CMT Dispatch)
- ⚠️ `cmt-progress` ditempatkan di Maklon portal padahal lebih natural di Production

### Verdict
**🟡 PARTIAL** — Functional tapi confusing dengan 2 dispatch.

---

## BP6: HIRE-TO-RETIRE (H2R)

### Ideal Flow
```
Recruitment → Hiring → Onboarding → Daily Operations (attendance, leave) → 
Performance Review → Career Development → Exit (Resignation/Termination)
```

### Actual Implementation
All steps implemented dengan baik. **2 minor issues:**
- 2 sistem attendance (`rahaza_attendance` + `dewi_attendance`) — ⚠️ duplicate
- 2 sistem performance (`hris_reviews` + `dewi_perf_reviews`) — ⚠️ duplicate

### Verdict
**🟢 OK** — Best-implemented business process dalam sistem.

---

## BP7: ASSET LIFECYCLE

### Ideal Flow
```
Acquisition → Asset Registration → Assignment to Employee → 
Maintenance Schedule → Transfer → Disposal
```

### Actual Implementation
| Step | Module | Collection | Status |
|------|--------|------------|--------|
| 1. Acquisition | `hr-assets` (HRAssetModule) atau Asset Portal | `dewi_assets`, `da_assets` | ⚠️ 2 systems |
| 2. Assignment | (within assets portal) | `dewi_asset_assignments`, `da_asset_assignments` | ⚠️ 2 systems |
| 3. Maintenance | (within assets portal) | `dewi_asset_maintenance`, `dewi_asset_pm_acknowledgments` | ✅ |
| 4. Transfer | **❌ MISSING UI** (backend exists: `dewi_asset_transfers`) | — | 🔴 **GAP** |
| 5. Depreciation | (auto-calc) | `dewi_asset_depreciation`, `rahaza_fixed_assets`, `rahaza_depr_schedules` | ⚠️ 2 systems |
| 6. Disposal | (partial) | `dewi_asset_disposal_requests` | ⚠️ |

### Pain Points
- 🔴 Backend ada tapi UI untuk Transfer hilang
- ⚠️ `dewi_assets` vs `da_assets` (2 systems!)
- ⚠️ Fixed Assets (`rahaza_fixed_assets`) di Finance terpisah dari Operational Assets (`dewi_assets`) — ini OK untuk akuntansi tapi link harus jelas

### Verdict
**🟡 PARTIAL** — Transfer UI missing, asset duplication issue.

---

## BP8: MARKETING PERFORMANCE FLOW

### Ideal Flow
```
Platform Setup → Daily Sales Input → Performance Tracking → 
Ads/Campaign Management → KOL/Creator Mgmt → 
Complaints/Returns Handling → Targets vs Actual
```

### Actual Implementation
Comprehensive coverage di marketing portal (26 menu items). **Pain Points:**
- 3 KOL/Creator systems paralel (lihat FORENSIC_04)
- 2 channels manager (lama via `dewi_toko_channels` vs baru via `marketing_platform_accounts`)
- `toko-pricing` (lama) vs `marketing-discounts` (baru) untuk promo

### Verdict
**🟢 OK** untuk modern flow, **⚠️ Legacy debt** menambah cognitive load.

---

## BP9: WAREHOUSE OPERATIONS — STOCK OPNAME

### Ideal Flow
```
Schedule Opname → Generate Count Sheet → Physical Counting → 
Variance Analysis → Adjustment → Close Cycle
```

### Actual Implementation
**🔴 3 SISTEM PARALEL UNTUK SAMA-SAMA OPNAME:**
1. `wh-opname` (OpnameModule) → `warehouse_opname` (legacy)
2. `wh-accessory-ops` includes opname via `acc_opname_sessions` + `acc_opname_lines`
3. `wms-opname-enhanced` (WMSOpnameEnhancedModule) → `wh_opname2_cycles` + `wh_opname2_variances` (newest, AI-enhanced)
4. Plus `wh_opname_sessions` + `wh_opname_lines` (mid generation, possibly orphan)

### Verdict
**🔴 BROKEN** — Tidak ada user yang bisa decide mana "the real opname". P1 consolidation needed.

---

## BP10: ACCESSORY MANAGEMENT (CRITICAL)

### Current Reality — 4 PARALLEL SYSTEMS!

**System A: `rahaza_materials` (type=accessory)**
- Integrated dengan production via Material Issue
- Stock di `rahaza_material_stock`
- Movement di `rahaza_material_movements`
- Accessed via: `wh-accessory-master` (UI), `wh-accessory-stock` (UI)

**System B: `acc_items` (standalone)**
- Has full procurement lifecycle:
  - `acc_items` (master)
  - `acc_stock_movements` (stock log)
  - `acc_purchase_requests` (procurement)
  - `acc_internal_requests` (RnD requests)
  - `acc_loans` (peminjaman internal)
  - `acc_opname_sessions` + `acc_opname_lines` (cycle counting)
- Accessed via: `wh-accessory-ops` (UI)

**System C: `accessories` (legacy generic)**
- Old generic collection, partial usage

**System D: Request Inbox**
- `dewi_accessory_requests` + `accessory_requests` (2 collections, naming collision!)
- Accessed via: `warehouse-accessory-requests`, `rnd-accessory-requests` aliases

### Pain Points
- User tidak tahu di mana "stok aksesoris yang benar"
- Material Issue ke production bisa miss accessories yang ada di System B
- Purchase Request System B tidak update stock di System A

### Verdict
**🔴 CRITICAL** — Highest priority untuk konsolidasi. Lihat FORENSIC_09 untuk consolidation plan.

---

## RINGKASAN BUSINESS PROCESS HEALTH

| Process | Coverage | Coherence | Verdict |
|---------|----------|-----------|---------|
| BP1 P2P | 80% | 60% | 🟡 |
| BP2 O2C | 95% | 90% | 🟢 |
| BP3 M2S | 90% | 90% | 🟢 |
| BP4 Maklon | 75% | 50% | 🔴 |
| BP5 CMT | 90% | 65% | 🟡 |
| BP6 H2R | 95% | 85% | 🟢 |
| BP7 Asset | 70% | 60% | 🟡 |
| BP8 Marketing | 85% | 70% | 🟢 |
| BP9 Opname | 90% | 30% | 🔴 |
| BP10 Accessory | 95% | 20% | 🔴 |

**Conclusion:** Coverage tinggi (rata-rata 87%) tapi Coherence rendah (rata-rata 62%) — sistem fungsional tapi terpecah.
