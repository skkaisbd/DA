# FORENSIC AUDIT — 09: CONSOLIDATION PLAN
## Workflow Consolidation — Yang Akan Di-Merge & Alasannya

**Lensa:** L6 Workflow Consolidation + L2 Business Process Engineering

---

## PRINSIP KONSOLIDASI

1. **Same business goal = 1 module** — Tanpa kurangi functionality
2. **Tab-based untuk variant** — Bukan menu baru
3. **Filter-based untuk subset** — Bukan duplicate UI
4. **Wizard-based untuk multi-step** — Bukan multiple modules
5. **Inbox-based untuk approvals** — Unified across domains

---

## CONSOLIDATION #1: AKSESORIS — 4 sistem → 1 SSOT

### Current (4 systems)
```
UI:
  wh-accessory-master   (RahazaMaterialsModule, no filter)
  wh-accessory-stock    (RahazaStockModule, no filter)
  wh-accessory-ops      (AccessoryModule, separate)
  warehouse-accessory-requests (AccessoryRequestInbox)

Backend:
  /api/rahaza/materials
  /api/rahaza/material-stock
  /api/acc/* (full lifecycle)
  /api/dewi/accessory-requests

DB:
  rahaza_materials
  acc_items, acc_stock_movements, acc_purchase_requests, acc_loans, acc_opname_*
  accessory_requests, dewi_accessory_requests
  accessories (legacy)
```

### Target (1 system)
```
UI:
  wh-stock (with tab filter: All / Material / Accessory / FG)
  wh-master (with tab filter: same)
  wh-accessory-ops (Specialized features: loans, internal requests)
  warehouse-accessory-requests (Inbox)

Backend:
  /api/inventory/items?type=accessory       (unified)
  /api/inventory/stock?type=accessory
  /api/accessory/loans                       (specialized)
  /api/accessory/internal-requests           (specialized)
  /api/accessory/purchase-requests           (specialized, OR merge into purchase-orders)

DB:
  rahaza_materials (with type field)
  rahaza_material_stock
  rahaza_material_movements
  accessory_loans (specialized, renamed)
  accessory_purchase_requests (or part of rahaza_purchase_orders)
  accessory_internal_requests (consolidated)
```

### Migration Steps
1. ✅ Add `type` field to `rahaza_materials` if not exists (already exists)
2. Script: Migrate `acc_items` records to `rahaza_materials` with `type='accessory'`
3. Script: Migrate `acc_stock_movements` to `rahaza_material_movements`
4. Backend: Rewrite `/api/acc/items` and `/api/acc/stock-movements` to query `rahaza_*`
5. Backend: Keep `/api/acc/loans`, `/api/acc/purchase-requests`, `/api/acc/internal-requests` as specialized
6. Backend: Consolidate `accessory_requests` + `dewi_accessory_requests` into `accessory_requests`
7. Frontend: Remove sidebar items `wh-accessory-master`, `wh-accessory-stock`
8. Frontend: Update `wh-master`, `wh-stock` to support type filter tab
9. Test: End-to-end accessory flow (request → PO → GR → issue → opname)
10. Delete: `acc_items`, `acc_stock_movements`, `acc_opname_*`, `accessories`

**Effort: ~24 hours | Risk: Medium**

---

## CONSOLIDATION #2: CUTTING (Planning + Execution)

### Current
```
prod-cutting         → CuttingProcessModule → dewi_cutting_requests, dewi_cutting_batches
prod-exec-cutting    → ProcessExecutionModule (CUTTING code) → rahaza_process_execution
```

### Target
```
prod-cutting         → CuttingHubModule (with 2 tabs)
                         Tab 1: Planning (existing CuttingProcessModule logic)
                         Tab 2: Execution (existing ProcessExecutionModule logic)
```

### Migration
1. Build `CuttingHubModule.jsx` as parent with tab navigation
2. Tab "Planning" embeds existing CuttingProcessModule
3. Tab "Execution" embeds existing ProcessExecutionModule with processCode=CUTTING
4. Add **data link**: Cutting batch → auto-create production execution input
5. Remove `prod-exec-cutting` from sidebar (still accessible via redirect)

**Effort: ~16 hours | Risk: Medium** (preserves both systems, adds linking)

---

## CONSOLIDATION #3: STOK & MASTER (3 → 1 dengan tab)

### Current
```
wh-materials          → Master Material (rahaza_materials filter type=material)
wh-accessory-master   → Master Aksesoris (rahaza_materials no filter, but labeled accessory)
wh-fg                 → Master FG (rahaza_materials filter type=fg)
wh-stock              → Stok Material
wh-accessory-stock    → Stok Aksesoris (same as wh-stock!)
```

### Target
```
wh-master             → Master Item with type tab filter [Material | Aksesoris | FG | All]
wh-stock              → Stok with type tab filter [Material | Aksesoris | FG | All]
```

**Effort: ~6 hours | Risk: Low**

---

## CONSOLIDATION #4: OPNAME (3 → 1)

### Current
```
wh-opname             → OpnameModule (legacy warehouse_opname)
acc opname (in wh-accessory-ops) → acc_opname_sessions, acc_opname_lines
wms-opname-enhanced   → WMSOpnameEnhancedModule (wh_opname2_*)
```

### Target
```
wh-opname             → OpnameHubModule with 2 modes:
                         Mode 1: Standard Opname (full count cycle)
                         Mode 2: Cycle Counting (frequent partial)
                       AI-enhanced features applied to both.
                       Single DB: wh_opname2_cycles + wh_opname2_variances
```

### Migration
1. Build `OpnameHubModule` with mode switcher
2. Backend: Add mode field to `wh_opname2_cycles`
3. Migrate `warehouse_opname` data to `wh_opname2_cycles` (legacy data preservation)
4. Migrate `acc_opname_sessions` data to `wh_opname2_cycles` (with item_type field)
5. Remove sidebar `wh-opname` (legacy) and accessory opname tab
6. Use `wms-opname-enhanced` as the new "Stok Opname" entry

**Effort: ~16 hours | Risk: Medium**

---

## CONSOLIDATION #5: MAKLON 360° VIEW (6 modules → 1 tab-based)

### Current Pain
Untuk 1 Maklon PO, user harus buka:
- `maklon-po` atau `maklon-orders` (info dasar)
- `maklon-samples` (sampling)
- `maklon-tracking` (production progress)
- `maklon-qc` (QC status)
- `maklon-billing` (invoice & payment)
- `maklon-hpp` (costing snapshot)

### Target
```
maklon-po-360         → New module "Maklon PO 360° View"
  Tab 1: Detail PO + BOM
  Tab 2: Sampling & Revisions
  Tab 3: Production Tracking
  Tab 4: QC Status
  Tab 5: Billing & Payment
  Tab 6: HPP Snapshot
  Tab 7: Timeline/Activity Log
```

List view tetap di `maklon-po` sebagai entry, lalu klik row → 360° View.

### Migration
1. Build `MaklonPO360View.jsx` as router
2. Each existing module becomes a tab component
3. Sidebar: Keep `maklon-po` (list), add no new menu
4. Detail action: "View 360°" button on each PO row

**Effort: ~20 hours | Risk: Low** (additive, doesn't break existing)

---

## CONSOLIDATION #6: HR UNIFIED APPROVAL INBOX

### Current
Approval terpisah di:
- `hr-leave` (cuti)
- `hr-overtime` (lembur)
- `hr-attendance-approval` (absen)
- `hr-salary-adjustments` (kenaikan gaji)
- `hr-resignation` (resignasi)

Manajer harus buka 5 modul untuk approve hal yang berbeda.

### Target
```
hr-inbox              → New "Inbox Approval SDM"
  Filter chips: [All | Cuti | Lembur | Absen | Salary | Resignasi]
  Each card: Type icon + Request summary + Approve/Reject buttons
  Click card: Full detail in drawer/sheet
```

**Effort: ~12 hours | Risk: Low**

---

## CONSOLIDATION #7: PRODUCTION CONTROL TOWER

### Current
Daily production monitoring tersebar:
- `prod-line-board` (real-time output)
- `prod-andon-board` (alerts)
- `prod-shift-handover` (shift notes)
- `prod-backlog` (forecast)

### Target
```
production-control-tower → Single dashboard with 4 panels:
  Panel 1: Live Line Board (top-left)
  Panel 2: Andon Alerts (top-right)
  Panel 3: Shift Handover (bottom-left)
  Panel 4: Backlog Forecast (bottom-right)
  Each panel has "Open Full View" link for detailed view.
```

**Effort: ~16 hours | Risk: Low**

---

## CONSOLIDATION #8: MARKETING REPORTS

### Current
- `marketing-daily-report` (per PIC)
- `marketing-monthly-report` (per PIC)
- `marketing-overview` (executive)
- `marketing-performance` (sales perf)
- `marketing-ads` (ads perf)

### Target
```
marketing-reports     → Marketing Reports Hub with tabs:
  Tab 1: Overview (executive)
  Tab 2: Performance (sales, ads, KOL)
  Tab 3: Daily Report (PIC submission + history)
  Tab 4: Monthly Report (PIC submission + history)
  Tab 5: Targets vs Actual
```

**Effort: ~12 hours | Risk: Low**

---

## CONSOLIDATION #9: KOMPLAIN & RETURN (Marketing)

### Current
- `marketing-complaints` (komplain)
- `marketing-returns` (returns)

Keduanya post-sale customer issue.

### Target
```
marketing-after-sales → "Komplain & Returns" unified
  Tab 1: Komplain (text-based)
  Tab 2: Returns & Refunds (product return)
  Tab 3: Resolution Log (history)
```

**Effort: ~6 hours | Risk: Low**

---

## CONSOLIDATION #10: TASK MANAGEMENT (Marketing)

### Current
- `marketing-tasks` (Kanban)
- `marketing-approvals` (Approval Inbox)
- `marketing-templates` (Templates)

### Target
```
marketing-task-hub    → Task Hub dengan tabs:
  Tab 1: Kanban Board
  Tab 2: My Pending Approvals
  Tab 3: Templates
```

**Effort: ~6 hours | Risk: Low**

---

## CONSOLIDATION #11: CMT VENDOR FLOW (Move to Production)

### Current
- `prod-cmt` di Production (CMTManagementModule)
- `maklon-cmt` di Maklon (BROKEN, no component!)
- `cmt-progress` di Maklon (should be in Production)
- `prod-cmt-packing` di Production

CMT adalah **outsourcing production**, harusnya semua di Production portal.

### Target (all in Production)
```
Production > CMT (sub-section):
  prod-cmt              → Vendor Management & Job Assignment
  prod-cmt-progress     ← MOVED from Maklon (was cmt-progress)
  prod-cmt-packing      → Receipt from CMT
  cmt-component-requests→ Shortage requests
  cmt-dispatch          ← NEW: unified dispatch (replaces do-management + wms-cmt-dispatches)
```

Maklon portal hanya focus on **client-facing** PO management, bukan CMT vendor flow.

**Effort: ~8 hours | Risk: Low**

---

## CONSOLIDATION #12: SHIPPING / DELIVERY (3 → 2)

### Current
- `prod-shipments` (RahazaShipmentsModule) → rahaza_shipments
- `do-management` (DOManagementModule) → dewi_cmt_delivery_orders
- `wms-delivery-notes` (WMSDeliveryNotesModule) → wh_delivery_notes
- `wms-cmt-dispatches` (WMSCMTDispatchesModule) → wh_cmt_dispatches

### Target (2 clear flows)
```
Customer Shipping (Outbound to Customer):
  warehouse > delivery-notes → wh_delivery_notes (SSOT)
  Includes prod-shipments info via API integration

CMT Dispatching (Outbound to CMT vendor):
  warehouse > cmt-dispatches → wh_cmt_dispatches (SSOT)
  Includes do-management info via migration
```

**Effort: ~16 hours | Risk: Medium**

---

## CONSOLIDATION #13: MASTER PRODUKSI (4 modul → 1 dengan tab)

### Current
- `prod-locations` (Lokasi)
- `prod-lines` (Lini)
- `prod-machines` (Mesin)
- `prod-shifts` (Shift)

Keempatnya saling terkait (location > line > machines; shift assignment).

### Target
```
prod-workspace-master → "Master Workspace" with tabs:
  Tab 1: Lokasi & Zona
  Tab 2: Lini Produksi
  Tab 3: Mesin
  Tab 4: Shift Kerja
  Tab 5: Visual Layout (NEW - workspace map)
```

**Effort: ~10 hours | Risk: Low**

---

## CONSOLIDATION #14: KPI & PERFORMANCE (HR)

### Current
- `hr-kpi` (Operational KPI)
- `hr-performance` (Annual Review)
- `hr-360-feedback` (Peer feedback)
- `kpi-portal` (employee-side KPI view)

### Target
```
HR Manager Side (in HR Portal):
  hr-performance → "Performance Management" with tabs:
    Tab 1: Operational KPI (monthly)
    Tab 2: Annual Reviews
    Tab 3: 360° Feedback Cycles
    Tab 4: Goal Setting (OKR)

Employee Side (in Portal Saya):
  portal-performance → "Performance Saya" with tabs:
    Tab 1: My KPI
    Tab 2: My Annual Review
    Tab 3: My Peer Feedback (give & receive)
    Tab 4: My Goals
```

**Effort: ~12 hours | Risk: Low**

---

## SUMMARY: 14 KONSOLIDASI

| # | Konsolidasi | Saved Modules | Effort | Risk |
|---|-------------|---------------|--------|------|
| 1 | Aksesoris SSOT | 3 → 1 | 24h | Medium |
| 2 | Cutting (Plan+Exec) | 2 → 1 | 16h | Medium |
| 3 | Stok & Master tab | 5 → 2 | 6h | Low |
| 4 | Opname unified | 3 → 1 | 16h | Medium |
| 5 | Maklon PO 360° | 6 → 1 view | 20h | Low |
| 6 | HR Approval Inbox | 5 → 1 | 12h | Low |
| 7 | Production Control Tower | 4 → 1 | 16h | Low |
| 8 | Marketing Reports Hub | 5 → 1 | 12h | Low |
| 9 | Komplain & Return | 2 → 1 | 6h | Low |
| 10 | Marketing Task Hub | 3 → 1 | 6h | Low |
| 11 | CMT to Production | (relocate) | 8h | Low |
| 12 | Shipping clear flows | 4 → 2 | 16h | Medium |
| 13 | Production Workspace Master | 4 → 1 | 10h | Low |
| 14 | KPI & Performance | 4 → 2 | 12h | Low |
| **TOTAL** | — | **~50 → ~16** | **180h** | — |

**Sidebar items reduced by ~30%.**  
**Total effort: ~180 hours (~22 working days)**

---

## EXPECTED USER IMPACT

### Before Konsolidasi
- Average click-to-task: 3.6x optimal
- Cognitive load: High (180+ sidebar items)
- Cross-portal navigation: Frequent
- Approval scattered
- Reports scattered

### After Konsolidasi
- Average click-to-task: 1.5x optimal
- Cognitive load: Medium (110-130 sidebar items)
- Cross-portal navigation: Reduced 50%
- Approvals unified per role
- Reports per domain unified

**Estimated productivity gain: 25-40%** untuk daily operations.
