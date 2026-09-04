# FORENSIC AUDIT — 02: DEPENDENCY GRAPH
## Cross-Module Dependency Mapping

**Format:** `Menu → Route → Component → API → DB Collection`

---

## 1. METODOLOGI

Untuk setiap menu item di sidebar, di-trace 5 lapisan:
1. **L1 Menu ID** — dari `PortalShell.jsx`
2. **L2 Component** — mapping di `moduleRegistry.js`
3. **L3 React Component** — file `.jsx` aktual
4. **L4 API Endpoint** — endpoint yang dipanggil component
5. **L5 DB Collection** — collection MongoDB yang ditulis/dibaca

---

## 2. DEPENDENCY MATRIX — PORTAL MANAGEMENT

| Menu ID | Component | API | DB Collection | Status |
|---------|-----------|-----|---------------|--------|
| management-dashboard | ManagementDashboard | /api/dashboard/* | aggregations | ✅ |
| mgmt-overview | ManagementOverviewModule | /api/management/overview | aggregations | ✅ |
| phase7-reports | Phase7ReportingModule | /api/dewi/reports/* | dewi_invoices, dewi_maklon_pos | ✅ |
| mgmt-reports | ReportsModule | /api/dashboard/reports | aggregations | ✅ |
| mgmt-rahaza-customers | RahazaCustomersModule | /api/rahaza/customers | rahaza_customers | ✅ |
| rnd-dashboard (shortcut) | RnDPortalDashboard | /api/dewi/rnd/* | dewi_rnd_* | ✅ |
| mgmt-users | UserManagementModule | /api/admin/users | users | ✅ |
| mgmt-roles | RoleManagementModule | /api/admin/roles | roles | ✅ |
| mgmt-role-matrix | RoleMatrixModule | /api/admin/role-permissions | role_permissions | ✅ |
| mgmt-activity | ActivityLogModule | /api/audit-logs | activity_logs, rahaza_audit_logs | ⚠️ 2 sources |
| mgmt-company | CompanySettingsModule | /api/admin/company | company_settings, rahaza_company_settings | ⚠️ 2 sources |
| mgmt-pdf | PDFConfigModule | /api/admin/pdf | pdf_export_configs | ✅ |
| mgmt-integrations | IntegrationSettingsModule | /api/rahaza/integration-settings | rahaza_integration_settings | ✅ |
| mgmt-help | RahazaUserGuideModule | static content | — | ✅ |
| mgmt-tools | ManagementToolsModule | /api/management/tools | aggregations | ✅ |
| ai-business-dashboard | AIBusinessDashboard | /api/ai-business/* | ai_business_summaries | ✅ |
| mgmt-okr | OKRTrackerModule | /api/management/okr | dewi_okr_objectives | ✅ |
| ai-usage-monitor | AIUsageMonitorModule | /api/ai/usage | rahaza_ai_usage_logs | ✅ |

---

## 3. DEPENDENCY MATRIX — PORTAL PRODUKSI (38 items)

### Operasional Harian
| Menu ID | Component | API | DB Collection | Status |
|---------|-----------|-----|---------------|--------|
| production-dashboard | ProductionDashboardModule | /api/rahaza/production-dashboard | aggregations | ✅ |
| prod-shipments | RahazaShipmentsModule | /api/rahaza/shipments | rahaza_shipments | ✅ |
| prod-wizard | ProductionWizardModule | /api/rahaza/wizard/* | rahaza_orders + rahaza_work_orders + rahaza_line_assignments | ✅ |
| prod-bulk-mi | RahazaBulkMIModule | /api/rahaza/bulk-material-issues | rahaza_material_issues | ✅ |
| prod-orders | RahazaOrdersModule | /api/rahaza/orders | rahaza_orders | ✅ |
| prod-work-orders | RahazaWorkOrdersModule | /api/rahaza/work-orders | rahaza_work_orders, work_orders (legacy?) | ⚠️ 2 sources |
| prod-bundles | RahazaBundlesModule | /api/rahaza/bundles | rahaza_bundles | ✅ |
| prod-material-reservation | RahazaMaterialReservationModule | /api/rahaza/material-reservation | rahaza_material_reservations | ✅ |
| prod-cutting | CuttingProcessModule | /api/dewi/cutting/* | dewi_cutting_requests, dewi_cutting_batches | ⚠️ Separate from exec-cutting |
| prod-assignments | RahazaLineAssignmentsModule | /api/rahaza/line-assignments | rahaza_line_assignments | ✅ |
| prod-shift-handover | RahazaShiftHandoverModule | /api/rahaza/shift-handovers | rahaza_shift_handovers | ✅ |
| **prod-rework-board** | **❌ MISSING** | — | — | 🔴 **BROKEN** |

### Proses Inti (5 tahap)
| Menu ID | Component | API | DB Collection | Status |
|---------|-----------|-----|---------------|--------|
| prod-exec-cutting | ProcessExecutionModule | /api/rahaza/process-execution | rahaza_process_execution | ✅ |
| prod-exec-sewing | ProcessExecutionModule | (same, processCode=SEWING) | rahaza_process_execution | ✅ |
| prod-exec-finishing | ProcessExecutionModule | (same, FINISHING) | rahaza_process_execution | ✅ |
| prod-exec-qc | ProcessExecutionModule | (same, QC) | rahaza_process_execution | ✅ |
| prod-exec-packing | ProcessExecutionModule | (same, PACKING) | rahaza_process_execution | ✅ |
| prod-cmt | CMTManagementModule | /api/dewi/cmt/* | dewi_cmt_partners, dewi_cmt_jobs, dewi_cmt_deliveries, dewi_cmt_payments | ✅ |
| prod-cmt-packing | CMTPackingModule | /api/dewi/cmt/packing | cmt_receipts, cmt_receipt_lines | ✅ |
| production-cmt-component-requests | CMTComponentRequestModule | /api/dewi/cmt-component-requests | dewi_cmt_component_requests | ✅ |
| prod-exec-rework | ProcessExecutionModule | (REWORK code) | rahaza_process_execution + rahaza_rework_close_log | ⚠️ 2 collections |

### Monitoring & Analytics
| Menu ID | Component | API | DB Collection | Status |
|---------|-----------|-----|---------------|--------|
| prod-line-board | LineBoardModule | /api/rahaza/line-board | aggregation of rahaza_process_execution | ✅ |
| prod-andon-board | AndonBoardModule | /api/rahaza/andon | rahaza_andon_events, rahaza_andon_settings | ✅ |
| **prod-alert-settings** | **❌ MISSING** | — | rahaza_alert_settings (exists in DB but no UI) | 🔴 **BROKEN** |
| prod-pareto | RahazaParetoModule | /api/rahaza/pareto | aggregation | ✅ |
| prod-fpy | RahazaFPYModule | /api/rahaza/fpy | aggregation | ✅ |
| prod-aql-calculator | RahazaAQLCalculatorModule | /api/rahaza/aql | client-side calc | ✅ |
| prod-downtime | RahazaDowntimeModule | /api/rahaza/downtime-events | rahaza_machine_downtime | ✅ |
| prod-backlog | RahazaBacklogModule | /api/rahaza/backlog | aggregation | ✅ |
| prod-ai-insights | RahazaAIModule | /api/rahaza/ai/* | rahaza_ai_chat_history, rahaza_ai_audit_logs | ✅ |
| ai-actions | AIActionsModule | /api/dewi/ai-actions | dewi_ai_actions | ✅ |
| prod-predictive-maintenance | PredictiveMaintenanceModule | /api/prod/predictive/* | aggregation from downtime | ✅ |

### Master Data (12 items)
All ✅ — standard CRUD mapping to corresponding `rahaza_*` collections.

---

## 4. DEPENDENCY MATRIX — PORTAL GUDANG (24 items)

### Inventori
| Menu ID | Component | DB Collection | Status |
|---------|-----------|---------------|--------|
| warehouse-dashboard | WarehouseDashboard | aggregations | ✅ |
| wh-materials | RahazaMaterialsModule | rahaza_materials | ✅ |
| wh-stock | RahazaStockModule | rahaza_material_stock, rahaza_material_movements | ✅ |
| wh-material-issue | RahazaMaterialIssueModule | rahaza_material_issues | ✅ |
| **wh-accessory-master** | RahazaMaterialsModule (SAMA!) | rahaza_materials (no filter!) | 🔴 **DUPLIKAT** |
| **wh-accessory-stock** | RahazaStockModule (SAMA!) | rahaza_material_stock (no filter!) | 🔴 **DUPLIKAT** |
| wh-fg | RahazaFGInventoryModule | rahaza_materials (type=fg), rahaza_fg_movements, rahaza_fg_issues | ✅ |
| unified-inventory | UnifiedInventoryModule | /api/wms/stock/unified (aggregator) | ✅ |

### Operasional Gudang
| Menu ID | Component | DB Collection | Status |
|---------|-----------|---------------|--------|
| wh-purchase-orders | PurchaseOrderModule | rahaza_purchase_orders | ✅ |
| wh-receiving | ReceivingModule | warehouse_receiving (legacy) | ⚠️ Legacy |
| do-management | DOManagementModule | dewi_cmt_delivery_orders | ✅ |
| fulfillment | FulfillmentModule | aggregations | ✅ |
| wh-supplier-scorecard | SupplierScorecardModule | derived from rahaza_grn_inspections | ✅ |
| wh-putaway | PutAwayModule | warehouse_putaway (legacy) | ⚠️ Legacy |
| wh-picklist | WMSPickListModule | wh_picklists | ✅ |
| wh-opname | OpnameModule | warehouse_opname (legacy) | ⚠️ Legacy (3 opname systems!) |
| wh-bin | LocationsModule | warehouse_locations (legacy) | ⚠️ Legacy |
| wh-accessory-ops | AccessoryModule | acc_items, acc_stock_movements, acc_internal_requests, acc_opname_*, acc_loans, acc_purchase_requests | 🔴 **Separate system** |
| warehouse-accessory-requests | AccessoryRequestInbox | acc_internal_requests, accessory_requests (⚠️ naming collision) | ⚠️ |
| wh-returns | WHReturnsModule | wh_returns | ✅ |
| warehouse-smart | WarehouseSmartModule | derived data | ✅ |

### Garment WMS (Advanced)
| Menu ID | Component | DB Collection | Status |
|---------|-----------|---------------|--------|
| wms | WMSModule | wh_buildings, wh_zones, wh_racks, wh_positions, wh_unit_master | ✅ |
| wms-fabric-rolls | WMSFabricRollsModule | wh_fabric_rolls, wh_fabric_roll_movements | ✅ |
| wms-delivery-notes | WMSDeliveryNotesModule | wh_delivery_notes | ✅ |
| wms-cmt-dispatches | WMSCMTDispatchesModule | wh_cmt_dispatches | ✅ |
| wms-opname-enhanced | WMSOpnameEnhancedModule | wh_opname2_cycles, wh_opname2_variances | ✅ (TAPI 3rd opname system!) |

**🔴 CRITICAL FINDING:** 3 Opname Systems Parallel:
1. `warehouse_opname` (oldest legacy)
2. `wh_opname_sessions` + `wh_opname_lines` (mid)
3. `wh_opname2_cycles` + `wh_opname2_variances` (newest AI-enhanced)

---

## 5. DEPENDENCY MATRIX — PORTAL MAKLON (14 items)

| Menu ID | Component | DB Collection | Status |
|---------|-----------|---------------|--------|
| maklon-dashboard | MaklonDashboard | aggregations | ✅ |
| maklon-clients | MaklonClientManagement | dewi_maklon_clients | ✅ |
| maklon-po | MaklonPOModule | dewi_maklon_pos (BARU) | ✅ |
| maklon-orders | MaklonOrderModule | dewi_maklon_orders (LAMA) | ⚠️ Legacy parallel |
| maklon-samples | MaklonSampleManagement | dewi_maklon_samples, dewi_maklon_sample_revisions | ✅ |
| maklon-tracking | MaklonProductionTracking | aggregations | ✅ |
| **maklon-cmt** | **❌ MISSING** | — | 🔴 **BROKEN** |
| cmt-progress | CMTProgressModule | dewi_cmt_progress_reports | ⚠️ In wrong portal |
| maklon-qc | MaklonQCTracking | dewi_maklon_qc_checks | ✅ |
| **maklon-packing** | **❌ MISSING** | — | 🔴 **BROKEN** |
| maklon-billing | MaklonBillingModule | dewi_maklon_invoices, dewi_maklon_payments | ✅ |
| maklon-hpp | MaklonHppModule | dewi_maklon_hpp, dewi_hpp_snapshots_* | ✅ |
| maklon-sla-dashboard | MaklonSLADashboard | aggregations | ✅ |
| maklon-ai-quote | MaklonAIQuoteModule | OpenAI API calls | ✅ |
| maklon-notifications | NotificationCenterModule | dewi_notifications | ✅ |
| maklon-config | MaklonSystemConfigModule | dewi_system_config | ✅ |

**🔴 Broken Menus in Maklon Portal:**
1. `maklon-cmt` — sidebar item but NOT in moduleRegistry (probably wanted to map to CMTManagementModule)
2. `maklon-packing` — sidebar item but NOT in moduleRegistry (probably wanted to map to CMTPackingModule)

---

## 6. DEPENDENCY MATRIX — PORTAL MARKETING (26 items)

[Truncated for brevity — see FORENSIC_07 for Marketing section restructure proposal]

Main findings:
- `toko-channels` and `toko-pricing` are labeled "(Lama)" — legacy modules
- 8 modules use `dewi_toko_*` collections (legacy data)
- 25+ modules use modern `marketing_*` collections
- KOL management has 3 implementations (KOLCreatorModule, KOLLeaderboardModule, TokoKOLModule)

---

## 7. DEPENDENCY MATRIX — PORTAL HR (30 items)

| Major Section | Key Collections | Status |
|---------------|-----------------|--------|
| Karyawan & Organisasi | rahaza_employees, dewi_org_units, dewi_org_positions, dewi_assets | ✅ |
| Rekrutmen | dewi_recruitment_jobs, dewi_recruitment_candidates, hr_ai_results | ✅ |
| Kehadiran | rahaza_attendance, rahaza_attendance_events, dewi_attendance | ⚠️ 2 attendance systems |
| Shift | rahaza_shifts, rahaza_line_assignments | ✅ |
| Lembur | rahaza_overtime_requests | ✅ |
| Cuti | rahaza_leave_requests, rahaza_leave_balances, rahaza_leave_types | ✅ |
| Kinerja | hris_cycles, hris_assignments, hris_reviews, dewi_perf_* | ⚠️ 2 systems (hris + dewi_perf) |
| LMS | dewi_lms_courses, dewi_lms_enrollments, dewi_lms_attempts, dewi_lms_quizzes | ✅ |
| Penggajian | rahaza_payroll_profiles, rahaza_payroll_runs, rahaza_payslips, da_payroll_allowances, rahaza_salary_grades, rahaza_salary_adjustments | ✅ |
| AI HR | hr_ai_results | ✅ |

---

## 8. PORTAL KOLABORASI & MANAJEMEN ASET (KECIL)

| Menu ID | Component | DB Collection | Status |
|---------|-----------|---------------|--------|
| collaboration | CollaborationPortal | comm_*, workspace_*, dewi_lms_* | ✅ (multi-source aggregation) |
| collab-workspace | WorkspacePortal | workspace_documents, workspace_shares, workspace_versions | ✅ |
| asset-dashboard | AssetManagementPortal | dewi_assets, da_assets, dewi_asset_assignments | ⚠️ 2 asset systems |
| asset-list | AssetManagementPortal | (same) | ⚠️ same |
| asset-procurement | AssetManagementPortal | dewi_procurement_requests | ✅ |

---

## 9. ORPHAN MENU IDS (di sidebar tapi tidak di registry)

```
prod-rework-board            → No mapping → Falls back to ManagementDashboard
prod-alert-settings          → No mapping → Falls back to ManagementDashboard
maklon-cmt                    → No mapping → Falls back to ManagementDashboard
maklon-packing                → No mapping → Falls back to ManagementDashboard
```

## 10. ORPHAN REGISTRY IDS (di registry tapi tidak di sidebar)

```
mgmt-customers           → BuyersModule           (replaced by mgmt-rahaza-customers)
wh-accessory             → AccessoryModule         (renamed to wh-accessory-ops)
self-dashboard           → SelfServicePortal       (legacy, kept for backward compat)
toko-dashboard-legacy    → TokoDashboard           (legacy backup)
toko-dashboard-classic   → TokoDashboardModule     (legacy backup)
toko-products            → TokoProductCatalogModule (orphan)
toko-orders              → TokoOrdersModule
toko-packing             → (same as orders, tab variant)
toko-shipping            → (same as orders, tab variant)
toko-kol                 → TokoKOLModule (legacy KOL)
toko-deals               → (tab variant)
toko-samples             → (tab variant)
toko-cs                  → TokoCSReturnsModule (legacy CS)
toko-returns             → (tab variant)
rnd-module               → RnDModule (old umbrella, replaced by separate rnd-* IDs)
cmt-component-requests   → alias for production-cmt-component-requests
rnd-kreator-requests     → alias
rnd-accessory-requests   → alias
prod-exec-rajut          → redirect (legacy PT Rahaza terminology)
prod-exec-linking        → redirect (legacy)
prod-exec-steam          → redirect (legacy)
prod-exec-washer         → redirect (legacy)
prod-exec-sontek         → redirect (legacy)
prod-oee, prod-line-balance, prod-rework-analytics, prod-aps-gantt → redirects to production-dashboard
prod-models, prod-bom, prod-sizes → redirects to prod-models-bom
mgmt-products            → redirect to prod-models-bom
wh-material-reservation  → redirect to prod-material-reservation
rnd-style-detail         → RnDStyleDetailPage (modal/inline, not routable)
collab-communication     → Direct access route (kept hidden)
```

**Total Orphan/Redirect IDs in Registry: ~30** (mostly legacy compatibility)

---

## 11. KEY CROSS-DOMAIN DEPENDENCIES

### A. Production → Inventory
```
WO created → Material Reservation needed → 
  Material Issue (single OR bulk) → 
  Stock decrement (rahaza_material_stock) → 
  Movement log (rahaza_material_movements)
```

### B. Marketing → Inventory → Production
```
Online Order received → 
  Fulfillment check FG stock → 
  (if not in stock) create Production Order → 
  Trigger WO creation
```

### C. RnD → Production → Inventory
```
Style approved → 
  BOM defined → 
  (cascades to) Material Requirements → 
  Procurement Request to Warehouse
```

### D. HR → Production (Operator Skills)
```
Employee data → 
  Skill matrix → 
  Line assignment eligibility → 
  Daily line assignment
```

### E. Maklon Order → Production Flow
```
Maklon PO received (dewi_maklon_pos) → 
  BOM (dewi_maklon_bom) → 
  Internal WO created (rahaza_work_orders) → 
  Production execution → 
  Dispatch to client (dewi_maklon_dispatches) → 
  Invoice (dewi_maklon_invoices)
```

### F. CMT Outsourcing Flow
```
WO created in-house → 
  CMT Job assigned (dewi_cmt_jobs) → 
  Material dispatch (do-management OR wms-cmt-dispatches) → 
  CMT vendor receives + sews → 
  Receipt back (cmt_receipts OR dewi_cmt_deliveries) → 
  Payment (dewi_cmt_payments)
```

**⚠️ Observation:** Many cross-domain flows touch 5-7 collections each. Refactoring impact is high.

---

## 12. CONCLUSION

Dependency mapping mengkonfirmasi:
- **15+ duplicate data flows** (most critical: accessories, opname, maklon orders)
- **4 broken menu mappings** (must fix immediately)
- **30+ orphan registry IDs** (cleanup opportunity)
- **Cross-domain entanglement** sangat tinggi (refactoring perlu careful sequencing)

Lihat `FORENSIC_04_DATA_ARCHITECTURE.md` untuk consolidation plan per cluster.
