import { lazy, useEffect } from 'react';

// ─── CV. Dewi Aditya — Module Registry ────────────────────────────────────
//
// Portal baru yang ditambahkan:
//   - Portal Maklon (maklon-dashboard, maklon-*)
//   - Portal Toko Online (toko-dashboard, toko-*)
//
// Proses produksi diupdate:
//   - Rajut/Linking/Steam → Cutting/CMT-Sewing/Finishing
// ─────────────────────────────────────────────────────────────────────────────

// Helper: simple redirect component that switches to target module
function makeRedirect(targetId, tabKey) {
  return function RedirectModule({ onNavigate }) {
    useEffect(() => {
      if (tabKey) {
        // Store tab hint in sessionStorage for the target to pick up
        if (targetId === 'production-dashboard') {
          sessionStorage.setItem('prod_dashboard_tab', tabKey);
        } else if (targetId === 'prod-models-bom') {
          sessionStorage.setItem('models_bom_tab', tabKey);
        } else if (targetId === 'maklon-dashboard') {
          sessionStorage.setItem('maklon_dashboard_tab', tabKey);
        } else {
          // BACKLOG-A: hub generik membaca `hub_tab_<hubId>` (lihat erp/hubs/HubTabs.jsx)
          sessionStorage.setItem(`hub_tab_${targetId}`, tabKey);
        }
      }
      if (onNavigate) onNavigate(targetId);
    }, []); // eslint-disable-line react-hooks/exhaustive-deps
    return (
      <div className="flex items-center justify-center h-32">
        <div className="text-center">
          <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-[hsl(var(--primary))] mx-auto mb-2" />
          <p className="text-sm text-muted-foreground">Mengarahkan...</p>
        </div>
      </div>
    );
  };
}

// Helper: wrapper untuk modul dengan default tab (untuk Toko Online Phase 5B)
function makeModuleWithTab(ModuleComponent, defaultTab) {
  return function ModuleWithTabWrapper(props) {
    return <ModuleComponent {...props} defaultTab={defaultTab} />;
  };
}

// FASE 5: helper prop-injector utk modul engine (mis. businessType)
function withProps(ModuleComponent, extraProps) {
  return function ModuleWithPropsWrapper(props) {
    return <ModuleComponent {...props} {...extraProps} />;
  };
}

// ─── FASE 5: Engine Produksi & Maklon (port SOMMERVILLE) ─────────────────────
const EnginePOModule             = lazy(() => import('./engine/ProductionPOModule'));
const EngineJobsModule           = lazy(() => import('./engine/WorkOrderModule'));
const EngineProgressModule       = lazy(() => import('./engine/ProductionProgressModule'));
const EngineReturnModule         = lazy(() => import('./engine/ProductionReturnModule'));
const EngineBuyerShipmentModule  = lazy(() => import('./engine/BuyerShipmentModule'));
const EngineVendorShipmentModule = lazy(() => import('./engine/VendorShipmentModule'));
const EngineVarianceModule       = lazy(() => import('./engine/OverproductionModule'));
const EngineVarianceReport       = lazy(() => import('./engine/BuyerReceiptVarianceReport'));
const EngineMonitoringModule     = lazy(() => import('./engine/ProductionMonitoringModule'));
const EngineSerialModule         = lazy(() => import('./engine/SerialTrackingModule'));
const EngineDefectReportsModule  = lazy(() => import('./engine/MaterialDefectReportsModule'));
// Phase B (2026-07-16) — DA-admin proses FG dari CMT (cmt_receipts SSOT).
const EngineDAReceiveFromCMT     = lazy(() => import('./engine/DAReceiveFromCMTModule'));
// Phase C (2026-07-17) — PO Closure (auto-complete 100% + close-short + credit note).
const EnginePOClosure            = lazy(() => import('./engine/POClosureModule'));

// Dashboards
const ManagementDashboard = lazy(() => import('./ManagementDashboard'));
const WarehouseDashboard  = lazy(() => import('./WarehouseDashboard'));
const FinanceDashboard    = lazy(() => import('./FinanceDashboard'));
// Sprint 1.2: Replace placeholder with real HR Dashboard
const HRDashboard = lazy(() => import('./HRDashboard'));
const HRApprovalInboxModule = lazy(() => import('./HRApprovalInboxModule'));   // Phase 26 — P2 HR Approval Inbox
// Task 2.4: Multi-Level Approval Workflow
const MultiLevelApprovalModule = lazy(() => import('./MultiLevelApprovalModule'));
// Phase 3.3B: Unified Approval Hub (Aggregator)
const UnifiedApprovalHub = lazy(() => import('./UnifiedApprovalHub'));
// Task 1.2: Shift Management System
const HRShiftManagementModule = lazy(() => import('./HRShiftManagementModule'));
// Announcement Management (HR)
const AnnouncementModule = lazy(() => import('./AnnouncementModule'));

// Management — master data + administrasi
// [FASE 4 CLEANUP] ProductsModule de-registered — orphan module (not in any nav / MODULES map).
// It edited the legacy `products`/`product_variants` collections which are superseded by
// rahaza_models (Internal) and buyer-catalog (Maklon). File kept on disk but no longer imported.
const BuyersModule          = lazy(() => import('./BuyersModule'));
const ReportsModule         = lazy(() => import('./ReportsModule'));
const UserManagementModule  = lazy(() => import('./UserManagementModule'));
const RoleManagementModule  = lazy(() => import('./RoleManagementModule'));
const ActivityLogModule     = lazy(() => import('./ActivityLogModule'));
const CompanySettingsModule = lazy(() => import('./CompanySettingsModule'));
// SESI #19 — layar PDF SATU PINTU hidup sebagai TAB hub Pengaturan Sistem
// (`hubs/ManagementSystemHub.jsx`), jadi registry ini hanya mengarahkan deep-link
// lamanya ke sana; tidak ada impor langsung supaya isinya tidak punya dua pintu.
// Legacy HelpGuideModule replaced by RahazaUserGuideModule (Sprint 26)

// Warehouse
const ReceivingModule = lazy(() => import('./ReceivingModule'));
const PutAwayModule   = lazy(() => import('./PutAwayModule'));
// Fase 5 cleanup: OpnameModule.jsx (legacy /api/wms/legacy/opname) DIHAPUS dari disk.
// 'wh-opname' → WMSOpnameScanModule (scan-driven /api/wms/opname3 SSOT + finance).
// FASE F (2026-07-25): LocationsModule (legacy "Lokasi Bin") DIHAPUS — orphan/unmapped
// (SSOT lokasi = Struktur Gudang wh_*). Deep-link 'wh-bin' tetap redirect ke 'wh-structure'.
const AccessoryModule  = lazy(() => import('./AccessoryModule'));
// Portal Aksesoris dedicated modules (Session #11.21)
const AccessoriesDashboard = lazy(() => import('./AccessoriesDashboard'));
const AccessoriesReports   = lazy(() => import('./AccessoriesReports'));

// Phase B: 8 Frontend UI Modules (Finance, HR, Warehouse) - Added 2026-06-01
const AccrualsModule = lazy(() => import('./AccrualsModule'));
const AssetDepreciationModule = lazy(() => import('./AssetDepreciationModule'));
const BadDebtWriteOffModule = lazy(() => import('./BadDebtWriteOffModule'));
const AssetDisposalModule = lazy(() => import('./AssetDisposalModule'));
const PurchaseDiscountModule = lazy(() => import('./PurchaseDiscountModule'));
// W-T2.1 de-dup: EmployeeLoansModule (hr-employee-loans, Pinjaman Legacy) tidak lagi dipakai.
// Data 3 pinjaman legacy sudah dimigrasi ke dewi_kasbon_requests (type=pinjaman).
// 'hr-employee-loans' → makeRedirect('hr-kasbon'). Koleksi rahaza_employee_loans diarsip (tidak di-drop).
// const EmployeeLoansModule = lazy(() => import('./EmployeeLoansModule'));
const InventoryScrapModule = lazy(() => import('./InventoryScrapModule'));

// Backup & Restore System - Added 2026-06-01
const BackupRestoreModule = lazy(() => import('./BackupRestoreModule'));
const DocNumberingModule = lazy(() => import('./DocNumberingModule'));

const WHReturnsModule  = lazy(() => import('./WHReturnsModule'));
const QuarantineModule = lazy(() => import('./QuarantineModule'));  // FASE 6: Karantina QC (INV-8)
const StockSchemaHealthModule = lazy(() => import('./StockSchemaHealthModule'));  // FASE 6.6-A: kesehatan skema baris stok
// O1.2 — CMTPackingModule tidak lagi dipakai. FASE H-8: prod-cmt-packing → `da-cmt-receive`
// (Terima FG dari CMT, koleksi `cmt_receipts`) — bukan lagi ke wms-cmt-dispatches yang kosong.
// FASE 20 — SUDAH DIARSIP ke `_archive/`.
// const CMTPackingModule = lazy(() => import('./CMTPackingModule'));
// Task 2.5: Production Material Returns

// Finance — Legacy modules (InvoiceModule, PaymentModule, AccountsPayableModule,
// AccountsReceivableModule, ManualInvoiceModule) REMOVED in Session #11.17.
// Backend routes were deleted in Session #11.16 Phase D (finance.py + dewi_kol.py).
// Use SSOT modules: fin-ar-invoices (AR Invoices), fin-ar-360 (AR Aging),
// fin-ap-aging (AP Aging), maklon-billing (Maklon Invoices).
const FinancialRecapModule     = lazy(() => import('./FinancialRecapModule'));
const ThreeWayMatchModule      = lazy(() => import('./ThreeWayMatchModule'));     // Phase 27 — 3-way match dashboard
const ARLifecycleModule        = lazy(() => import('./ARLifecycleModule'));       // Phase 30 — AR 360° (Aging + Customer Statement)
const ApprovalModule           = lazy(() => import('./ApprovalModule'));
// Finance · Bank Reconciliation (P1)
const BankReconciliation       = lazy(() => import('./finance/BankReconciliation'));
// SESI #37 — Pencairan Marketplace: FORM & JURNAL milik Portal Keuangan
// (keputusan pemilik). Layar Marketing (`MarketingSettlementsView`) tetap baca-saja.
const FinanceSettlementModule  = lazy(() => import('./finance/FinanceSettlementModule'));
const CashFlowAI               = lazy(() => import('./finance/CashFlowAI'));

// Produksi · Master Data Rajut (PT Rahaza)
const RahazaLocationsModule = lazy(() => import('./RahazaLocationsModule'));
const RahazaProcessesModule = lazy(() => import('./RahazaProcessesModule'));
const RahazaShiftsModule    = lazy(() => import('./RahazaShiftsModule'));
const RahazaMachinesModule  = lazy(() => import('./RahazaMachinesModule'));
const RahazaLinesModule     = lazy(() => import('./RahazaLinesModule'));
const RahazaEmployeesModule = lazy(() => import('./RahazaEmployeesModule'));
const RahazaModelsModule    = lazy(() => import('./RahazaModelsModule'));
const RahazaSizesModule     = lazy(() => import('./RahazaSizesModule'));
const ProductionDashboardModule    = lazy(() => import('./ProductionDashboardModule'));
const ProductionControlTowerModule = lazy(() => import('./ProductionControlTowerModule')); // Phase 28 — P2 Workflow Consolidation #3
// FASE IA-1 (2026-07-26) — AI produksi ASLI (dulu cuma tab di dashboard) & pintu Invoice CMT.
const AIInsightsModule             = lazy(() => import('./AIInsightsModule'));
const ProductionCMTBillingModule   = lazy(() => import('./ProductionCMTBillingModule'));
const RahazaOrdersModule           = lazy(() => import('./RahazaOrdersModule'));
// RahazaBOMModule (v1, 406 LOC) REMOVED — Session #12 P1 dead code cleanup.
// 'prod-bom' → makeRedirect('prod-models-bom', 'bom') → uses RahazaModelsAndBOMModule (v2, SSOT).
// File archived at: src/components/erp/_archive/RahazaBOMModule.jsx
const RahazaAlertSettingsModule    = lazy(() => import('./RahazaAlertSettingsModule'));
const RahazaMaterialsModule        = lazy(() => import('./RahazaMaterialsModule'));
const RahazaStockModule            = lazy(() => import('./RahazaStockModule'));
const RahazaMaterialIssueModule    = lazy(() => import('./RahazaMaterialIssueModule'));
const RahazaAttendanceModule       = lazy(() => import('./RahazaAttendanceModule'));
const RahazaPayrollProfilesModule  = lazy(() => import('./RahazaPayrollProfilesModule'));
const RahazaPayrollRunModule       = lazy(() => import('./RahazaPayrollRunModule'));
const RahazaCostCentersModule      = lazy(() => import('./RahazaCostCentersModule'));
const RahazaARInvoicesModule       = lazy(() => import('./RahazaARInvoicesModule'));
const FinChannelGLMappingModule    = lazy(() => import('./FinChannelGLMappingModule'));
const RahazaCashAccountsModule     = lazy(() => import('./RahazaCashAccountsModule'));
const RahazaExpensesModule         = lazy(() => import('./RahazaExpensesModule'));
const RahazaHPPModule              = lazy(() => import('./RahazaHPPModule'));
const ProductCostingModule         = lazy(() => import('./costing/ProductCostingModule'));  // HPP per potong & per model
const SewingCostModule             = lazy(() => import('./costing/SewingCostModule'));      // sesi #34: biaya jahit SPK + HPP batch FIFO
const ManagementOverviewModule     = lazy(() => import('./ManagementOverviewModule'));
// O1.1 — RahazaShipmentsModule tidak lagi dipakai (prod-shipments → redirect wms-delivery-notes). Diarsip kelak.
// const RahazaShipmentsModule        = lazy(() => import('./RahazaShipmentsModule'));
const RahazaSOPModule              = lazy(() => import('./RahazaSOPModule'));

// Finance · Accounting Core (Phase F1)
const RahazaCOAModule             = lazy(() => import('./RahazaCOAModule'));
const RahazaJournalEntryModule    = lazy(() => import('./RahazaJournalEntryModule'));
const RahazaTrialBalanceModule    = lazy(() => import('./RahazaTrialBalanceModule'));
const RahazaPeriodsModule         = lazy(() => import('./RahazaPeriodsModule'));
const RahazaGeneralLedgerModule   = lazy(() => import('./RahazaGeneralLedgerModule'));

// Finance · Accounting Core (Phase F2)
const RahazaPostingProfilesModule = lazy(() => import('./RahazaPostingProfilesModule'));

// Phase 7: Marketing AR Bridge & Admin Setup Panel
const MarketingARBridgeModule     = lazy(() => import('./MarketingARBridgeModule'));
const AdminSetupPanelModule       = lazy(() => import('./AdminSetupPanelModule'));

const RahazaPnLModule             = lazy(() => import('./RahazaPnLModule'));
const RahazaHRReportsModule       = lazy(() => import('./RahazaHRReportsModule'));
const RahazaBalanceSheetModule    = lazy(() => import('./RahazaBalanceSheetModule'));
const RahazaJournalListModule     = lazy(() => import('./RahazaJournalListModule'));
const RahazaAPAgingModule         = lazy(() => import('./RahazaAPAgingModule'));

// Finance · Accounting Core (Phase F3)
const RahazaCashFlowModule        = lazy(() => import('./RahazaCashFlowModule'));
const BudgetModule                = lazy(() => import('./BudgetModule'));
const FixedAssetsModule           = lazy(() => import('./FixedAssetsModule'));

// Session 13 — SLA, Management Tools, Smart Warehouse
const MaklonSLADashboard         = lazy(() => import('./MaklonSLADashboard'));
const ManagementToolsModule      = lazy(() => import('./ManagementToolsModule'));
const WarehouseSmartModule       = lazy(() => import('./WarehouseSmartModule'));

// Phase 1/2 — Marketing Webhooks + Capacity Planning
const MarketingWebhooksModule    = lazy(() => import('./marketing/MarketingWebhooksModule'));
const ProcurementRequestModule  = lazy(() => import('./ProcurementRequestModule'));
const CapacityPlanningModule     = lazy(() => import('./CapacityPlanningModule'));

// Phase 2 Task 2.2 — Real-time Line Monitoring Dashboard

// Phase 3 — Live Session Analytics + Payroll Dashboard + Executive Report
const LiveSessionAnalyticsDashboard = lazy(() => import('./marketing/LiveSessionAnalyticsDashboard'));
const PayrollDashboardModule      = lazy(() => import('./PayrollDashboardModule'));
const ExecutiveReportModule       = lazy(() => import('./ExecutiveReportModule'));
const ReportsHubModule            = lazy(() => import('./ReportsHubModule'));

// Session 14 — AI Business Intelligence
const AIBusinessDashboard        = lazy(() => import('./AIBusinessDashboard'));

// Phase 21 — Decision Support & Quality Metrics
// FASE 5: Pareto & FPY (qc engine lama) diarsip.
const RahazaDowntimeModule        = lazy(() => import('./RahazaDowntimeModule'));

// Phase 20C — AI Layer
// FASE IA-1: RahazaAIModule (= "HR AI Insights") tidak lagi dipetakan dari registry.
// Modulnya tetap hidup & dipakai sebagai tab di `hubs/HRAIHub.jsx` (yang meng-import
// sendiri secara lazy). Deep-link 'hr-ai-insights' → makeRedirect('hr-ai-hub','insights').
// const RahazaAIModule              = lazy(() => import('./RahazaAIModule'));
const AssetManagementPortalLazy   = lazy(() => import('./AssetManagementPortal'));
// BACKLOG-A — Hub konsolidasi (T3.3/T3.4/T3.5/T3.6/T3.9)
const FinanceJournalHub  = lazy(() => import('./hubs/FinanceJournalHub'));
const MarketingAIHub     = lazy(() => import('./hubs/MarketingAIHub'));
const HRAIHub            = lazy(() => import('./hubs/HRAIHub'));
const MarketingLiveHub   = lazy(() => import('./hubs/MarketingLiveHub'));
const RnDCostingHub      = lazy(() => import('./hubs/RnDCostingHub'));
const WMSStockHub        = lazy(() => import('./hubs/WMSStockHub'));   // RC-IA-warehouse-1 (Opsi A)
// PHASE B — 5 hub anti-overwhelm
const HRExpenseTravelHub        = lazy(() => import('./hubs/HRExpenseTravelHub'));
const HRAttendanceHub           = lazy(() => import('./hubs/HRAttendanceHub'));
const FinanceAccountingAdjustHub = lazy(() => import('./hubs/FinanceAccountingAdjustHub'));
const RnDDesignHub              = lazy(() => import('./hubs/RnDDesignHub'));
// IA v2.1 (pilot Produksi + Keuangan) — konsolidasi analitik/monitoring/master jadi hub bertab.
const ProductionAnalyticsHub      = lazy(() => import('./hubs/ProductionAnalyticsHub'));
const ProductionMasterProcessHub  = lazy(() => import('./hubs/ProductionMasterProcessHub'));
const ProductionMasterProductHub  = lazy(() => import('./hubs/ProductionMasterProductHub'));
const FinanceReportsHub           = lazy(() => import('./hubs/FinanceReportsHub'));
const FinanceAccountingMasterHub  = lazy(() => import('./hubs/FinanceAccountingMasterHub'));
// IA v2.1 fase-2/3 — hub konsolidasi Manajemen, SDM, Marketing.
const ManagementAccessHub  = lazy(() => import('./hubs/ManagementAccessHub'));
const ManagementSystemHub  = lazy(() => import('./hubs/ManagementSystemHub'));
const HRPayrollHub         = lazy(() => import('./hubs/HRPayrollHub'));
const HRShiftHub           = lazy(() => import('./hubs/HRShiftHub'));
const HRLeaveHub           = lazy(() => import('./hubs/HRLeaveHub'));
const MarketingKOLHub      = lazy(() => import('./hubs/MarketingKOLHub'));

// Staff Self-Service Portal
const SelfServicePortal           = lazy(() => import('./SelfServicePortal'));

// Portal Saya — Self-Service HR + My Workspace
const PortalSayaDashboard         = lazy(() => import('./PortalSayaDashboard'));
const PortalSayaProfile           = lazy(() => import('./PortalSayaProfile'));
const PortalSayaCuti              = lazy(() => import('./PortalSayaCuti'));
// FASE 15 — absen (clock-in/out + istirahat + izin) DI DALAM Portal Saya, tidak
// lagi lompat ke halaman /absen yang terasa seperti login ulang.
const PortalSayaAbsen             = lazy(() => import('./PortalSayaAbsen'));
// FASE 16 — layar HR untuk menyetujui izin keluar + rekap istirahat/izin.
// Sebelumnya sesi keluar-masuk tersimpan di backend tapi TIDAK PUNYA layar apa pun.
const HRAttendanceSessionsModule  = lazy(() => import('./HRAttendanceSessionsModule'));
const PortalSayaPayslip           = lazy(() => import('./PortalSayaPayslip'));
const PortalSayaTraining          = lazy(() => import('./PortalSayaTraining'));
const PortalSayaNotifikasi        = lazy(() => import('./PortalSayaNotifikasi'));
const WorkspaceHub                = lazy(() => import('./WorkspaceHub'));

// Phase 12 — Kasbon & Pinjaman Karyawan
const KasbonStaffModule           = lazy(() => import('./KasbonStaffModule'));
const HRKasbonModule              = lazy(() => import('./HRKasbonModule'));
const FinanceKasbonModule         = lazy(() => import('./FinanceKasbonModule'));

// Phase 8 — DA KPI System
const HRKPIModule                 = lazy(() => import('./HRKPIModule'));
const KPIPortalModule             = lazy(() => import('./KPIPortalModule'));

// Phase 8 — DA Employee Assets & Payroll Allowances
const HRAssetModule               = lazy(() => import('./HRAssetModule'));
const RahazaPayrollAllowancesModule = lazy(() => import('./RahazaPayrollAllowancesModule'));

// Sprint 42 — Salary Adjustment (Raise) Workflow with Dual Approval
const RahazaSalaryAdjustmentModule = lazy(() => import('./RahazaSalaryAdjustmentModule'));

// Phase 8.6 — AI Action Items
const AIActionsModule             = lazy(() => import('./AIActionsModule'));

// Phase 8.7 — HR Employee full-field module (replaces RahazaEmployeesModule)
const HREmployeeModule            = lazy(() => import('./HREmployeeModule'));

// Phase 8.8-9.1 — Leave Balances + Overtime Request
const HRLeaveBalancesModule       = lazy(() => import('./HRLeaveBalancesModule'));
const RahazaOvertimeModule        = lazy(() => import('./RahazaOvertimeModule'));

// Phase 9.2+ — HR Admin (Salary Grades, Resignation, Office, Seed) + 360 Feedback
const HRAdminModule               = lazy(() => import('./HRAdminModule'));
const HR360FeedbackModule         = lazy(() => import('./HR360FeedbackModule'));

// Phase 7.9 — WMS Pick List Generator
const WMSPickListModule           = lazy(() => import('./WMSPickListModule'));
// WMS P0/P1 Garment Features
const WMSFabricRollsModule        = lazy(() => import('./WMSFabricRollsModule'));
const WMSDeliveryNotesModule      = lazy(() => import('./WMSDeliveryNotesModule'));
const WMSCMTDispatchesModule      = lazy(() => import('./WMSCMTDispatchesModule'));
// FASE H-3 (2026-08-16): menu "Buat Barcode" — label bahan & barang jadi.
const WMSBarcodeModule            = lazy(() => import('./WMSBarcodeModule'));
const WMSOpnameScanModule         = lazy(() => import('./WMSOpnameScanModule'));  // Fase 4: opname scan-driven (SSOT); Fase 5: menggantikan WMSOpnameEnhancedModule (dihapus)

// ─── Portal Maklon (Fase 3) ───────────────────────────────────────────────────
const MaklonDashboard = lazy(() => import('./MaklonDashboard'));
const MaklonClientManagement = lazy(() => import('./MaklonClientManagement'));
// Phase M1: Buyer Catalog (master artikel buyer Maklon, terpisah dari DA Product Master)
const MaklonBuyerCatalogModule = lazy(() => import('./MaklonBuyerCatalogModule'));
// MaklonOrderModule removed (Phase C cleanup 2026-05-23) — module was redirected
// to maklon-po (MaklonPOModule). All Maklon order CRUD now happens at /api/dewi/maklon/pos.
// Fase 3B: Sample & QC
const MaklonSampleManagement = lazy(() => import('./MaklonSampleManagement'));
const MaklonQCTracking = lazy(() => import('./MaklonQCTracking'));
const MaklonProductionTracking = lazy(() => import('./MaklonProductionTracking'));
// Fase 3C: Billing & HPP
const MaklonBillingModule = lazy(() => import('./MaklonBillingModule'));
const MaklonHppModule = lazy(() => import('./MaklonHppModule'));
const MaklonSystemConfigModule = lazy(() => import('./MaklonSystemConfigModule'));
const NotificationCenterModule = lazy(() => import('./NotificationCenterModule'));

// ── Production-Maklon Overhaul — New Modules ────────────────────────────────
// FASE 22 (2026-07-31) — `MaklonPOModule` DIARSIP ke `_archive/MaklonPOModule.jsx`.
// AKAR MASALAH YANG BARU DITEMUKAN: modul ini sudah lama TIDAK BISA DIBUKA
// (registry: 'maklon-po' → redirect 'maklon-pos-engine'), tapi masih ikut
// di-`lazy()`-import di sini. Akibatnya sesi sebelumnya "memperbaiki dropdown
// Varian PO Maklon" DI FILE INI — perbaikan yang tidak pernah dilihat pengguna
// (keluhan #1 owner tetap ada). Form PO Maklon yang NYATA dipakai =
// `engine/ProductionPOModule.jsx` (businessType='maklon').
const MaklonPO360Module = lazy(() => import('./MaklonPO360Module'));    // 360° unified view per PO (Phase 25)
const CMTPermakModule   = lazy(() => import('./CMTPermakModule'));      // Permak/Rework (Maklon Revamp M1)
const CMTMonitorModule  = lazy(() => import('./CMTMonitorModule'));     // Monitoring CMT: Dashboard Owner + Kejar (Fase 2)
// O1.2 — CMTProgressModule & CMTLifecycleModule tidak lagi dipakai (redirect ke WMS/Vendor).
// FASE 20 — SUDAH DIARSIP ke `_archive/` (file-nya masih memanggil endpoint '/api/dewi/cmt/*' yang tak ada).
// const CMTProgressModule = lazy(() => import('./CMTProgressModule'));    // CMT progress + DO
// const CMTLifecycleModule = lazy(() => import('./CMTLifecycleModule'));   // Phase 29 — Vendor lifecycle dashboard
// FASE 7: VendorPortalModule (portal vendor LAMA, model vendor_jobs) dipensiunkan.
const VendorCMTEnginePortal = lazy(() => import('../vendor-cmt/VendorCMTEnginePortal'));  // portal vendor SSOT (/api/production-*)
const VendorAccountsAdminModule = lazy(() => import('./VendorAccountsAdminModule'));  // Session #11.21 — Admin kelola vendor
// 2026-08-08 — Portal CMT Override: staf DA mengisi 11 modul portal vendor CMT
// ATAS NAMA vendor yang tidak memakai sistem (keputusan owner 1a/2b/3a/4a/5a).
// SSOT scoping + jejak audit: backend/core/cmt_override.py
const CMTOverridePortalModule = lazy(() => import('./CMTOverridePortalModule'));

// ─── Portal Toko Online → Marketing (rebrand in-place) ────────────────────────
// `toko-dashboard` sekarang = MarketingDashboard (Phase 1+2 Marketing Portal).
// Legacy TokoDashboardModule disimpan sebagai redirect ke toko-dashboard (Phase 3.3A)
const MarketingDashboard = lazy(() => import('./MarketingDashboard'));
const AccountManagementModule = lazy(() => import('./AccountManagementModule'));
const AccountBulkReviewModule = lazy(() => import('./marketing/AccountBulkReviewModule'));
const SalesDataEntryModule = lazy(() => import('./SalesDataEntryModule'));
const TaskManagementModule = lazy(() => import('./TaskManagementModule'));
const ApprovalInboxModule = lazy(() => import('./ApprovalInboxModule'));
const TaskTemplatesModule = lazy(() => import('./TaskTemplatesModule'));
// Consolidation #9 & #10 — Hub modules (2026-05-23)
const MarketingAfterSalesHub  = lazy(() => import('./MarketingAfterSalesHub'));   // Komplain + Returns + Log
const MarketingTaskHubModule   = lazy(() => import('./MarketingTaskHubModule'));  // Kanban + Approval + Templates
// Consolidation #3 & #13 — Warehouse + Production master hubs (2026-05-23)
const WarehouseMasterHub        = lazy(() => import('./WarehouseMasterHub'));         // Material + FG Master
// SESI #33 — Daftar Belanja Mingguan (usul beli dari ambang → PR) & Riwayat Harga Barang
const WeeklyShoppingListModule  = lazy(() => import('./WeeklyShoppingListModule'));
const MaterialCostHistoryModule = lazy(() => import('./MaterialCostHistoryModule'));
const ProductionWorkspaceMaster = lazy(() => import('./ProductionWorkspaceMaster')); // Lokasi + Lini + Mesin + Shift
// Consolidation #8 & #14 — Marketing Reports + HR Performance hubs (2026-05-23)
const MarketingReportsHub   = lazy(() => import('./MarketingReportsHub'));   // Overview + Sales + Ads + Daily + Monthly
const MarketingSettlementsView = lazy(() => import('./marketing/MarketingSettlementsView')); // sesi #34: pencairan marketplace (lihat saja)
const HRPerformanceHub      = lazy(() => import('./HRPerformanceHub'));      // KPI + Annual Review + 360° Feedback
const ImportCenterModule = lazy(() => import('./ImportCenterModule'));
const CatalogManagementModule = lazy(() => import('./CatalogManagementModule'));
// ── Sesi #20 — Sinkronisasi Marketing ⇄ Gudang ──────────────────────────────
// `sku-bridge`  : master pemetaan SKU platform (TikTok/Shopee) ⇄ master gudang.
//                 Menutup keluhan "id gudang & marketing tidak sinkron" — terukur
//                 0/601 baris pesanan tertaut sebelum layar ini ada.
// `sync-audit`  : forensik sinkronisasi lintas portal yang bisa dibuka pemilik
//                 sendiri (dulu hanya skrip di komputer pengembang).
const SkuBridgeModule = lazy(() => import('./SkuBridgeModule'));
const SyncAuditModule = lazy(() => import('./SyncAuditModule'));
const KOLCreatorModule = lazy(() => import('./KOLCreatorModule'));

// Phase 2 Week 4-5: Orders & Complaints Management
const UnifiedOrdersDashboard = lazy(() => import('./marketing/UnifiedOrdersDashboard'));
// F3 (2026-08-12) — MONITORING PENGIRIMAN. Pintu harian tersendiri karena isinya
// bukan "daftar semua pesanan" (itu Order Terpadu) melainkan **apa yang harus
// dikejar hari ini**: belum dikirim, LEWAT BATAS kirim (sumber penalti platform &
// pembatalan otomatis), batal, retur — dengan batas hari per toko yang bisa diubah.
const FulfillmentMonitorModule = lazy(() => import('./marketing/FulfillmentMonitorModule'));
const ComplaintsManagementModule = lazy(() => import('./marketing/ComplaintsManagementModule'));

// Phase 3 Week 6-7: Account Health, Sales Performance, Ads, Live Sessions
const AccountHealthDashboard = lazy(() => import('./marketing/AccountHealthDashboard'));
const SalesPerformanceDashboard = lazy(() => import('./marketing/SalesPerformanceDashboard'));
const AdsPerformanceDashboard = lazy(() => import('./marketing/AdsPerformanceDashboard'));
const LiveSessionModule = lazy(() => import('./marketing/LiveSessionModule'));

// Phase 3 Week 8-10: Content Calendar, Discount Campaign, Product Launch
const ContentCalendarModule = lazy(() => import('./marketing/ContentCalendarModule'));
const DiscountCampaignModule = lazy(() => import('./marketing/DiscountCampaignModule'));
const ProductLaunchModule = lazy(() => import('./marketing/ProductLaunchModule'));

// Phase 3 Week 11-12: Marketing Overview Dashboard + Integration Settings
const MarketingOverviewDashboard = lazy(() => import('./marketing/MarketingOverviewDashboard'));
const MarketingAIInsightsDashboard = lazy(() => import('./marketing/MarketingAIInsightsDashboard'));
const AdvancedAIModule = lazy(() => import('./marketing/AdvancedAIModule'));
const MarketingIntegrationSettings = lazy(() => import('./marketing/MarketingIntegrationSettings'));

// Session 12: AI Content & Image Generator, KOL Leaderboard, Scheduler
const AIContentGeneratorModule = lazy(() => import('./marketing/AIContentGeneratorModule'));
const AIImageGeneratorModule   = lazy(() => import('./marketing/AIImageGeneratorModule'));
const KOLLeaderboardModule     = lazy(() => import('./marketing/KOLLeaderboardModule'));
const MarketingSchedulerModule = lazy(() => import('./marketing/MarketingSchedulerModule'));

// Phase 3 Week 13: Fitur Internal (Rating/Review, Returns, Sample Delivery)
const RatingReviewModule = lazy(() => import('./marketing/RatingReviewModule'));
const ReturnsRefundsModule = lazy(() => import('./marketing/ReturnsRefundsModule'));
const SampleDeliveryModule = lazy(() => import('./marketing/SampleDeliveryModule'));
// Session 28 — LiveHost Management (Phase 1-4)
const LiveHostModule = lazy(() => import('./marketing/LiveHostModule'));
// Session 28 — Marketing PIC Reports & Targets
const AccountTargetsModule = lazy(() => import('./marketing/AccountTargetsModule'));
// F6.5 (sesi #9) — jejak perubahan marketing (layar "siapa mengubah apa").
const MarketingChangeLogModule = lazy(() => import('./marketing/MarketingChangeLogModule'));
const DailyReportModule    = lazy(() => import('./marketing/DailyReportModule'));
const MonthlyReportModule  = lazy(() => import('./marketing/MonthlyReportModule'));

// DEPRECATED (Phase 3.3A): toko-dashboard-legacy dan toko-dashboard-classic sekarang redirect ke toko-dashboard SSOT
// const TokoDashboard = lazy(() => import('./TokoDashboard'));
// const TokoDashboardModule = lazy(() => import('./TokoDashboardModule'));
const TokoChannelManagerModule = lazy(() => import('./TokoChannelManagerModule'));
// Phase 5B: Orders, Pricing/Flashsale, KOL, CS/Returns
const TokoOrdersModule = lazy(() => import('./TokoOrdersModule'));
const FulfillmentModule = lazy(() => import('./FulfillmentModule'));  // Phase 6: Online Order Bridge
// O1.1 — DOManagementModule tidak lagi dipakai. FASE H-8: do-management → `prod-shipments-vendor`
// (Kirim Material CMT, koleksi `vendor_shipments`) — bukan lagi ke wms-cmt-dispatches yang kosong.
// const DOManagementModule = lazy(() => import('./DOManagementModule'));  // Phase 2 Enhancement: DO System
const UnifiedInventoryModule = lazy(() => import('./UnifiedInventoryModule'));  // Phase 2 Enhancement: Unified Inventory
const Phase7ReportingModule = lazy(() => import('./Phase7ReportingModule'));  // Phase 7: Laporan & Dashboard
const TokoPricingFlashsaleModule = lazy(() => import('./TokoPricingFlashsaleModule'));
// TokoKOLModule removed in Session #11.17 — use marketing-kol (SSOT KOL Mgmt),
// marketing-kol-leaderboard (SSOT KOL Leaderboard), marketing-creators (Creator Portal).
const TokoCSReturnsModule = lazy(() => import('./TokoCSReturnsModule'));

// ─── Fase 2: Cutting & CMT ────────────────────────────────────────────────────
// O1.2 — CMTManagementModule tidak lagi dipakai (prod-cmt → redirect vendor-admin).
// FASE 20 — SUDAH DIARSIP ke `_archive/`.
// const CMTManagementModule  = lazy(() => import('./CMTManagementModule'));

// ─── Phase 6 — HRIS (Full) ───────────────────────────────────────────────────
const HRPerformanceModule = lazy(() => import('./HRPerformanceModule'));
const HRLMSModule = lazy(() => import('./HRLMSModule'));
const HROnboardingModule = lazy(() => import('./HROnboardingModule'));
const HRATSModule = lazy(() => import('./HRATSModule'));
const HROrgChartModule = lazy(() => import('./HROrgChartModule'));

// ─── Phase 7 — RnD & Style Master ────────────────────────────────────────────
const RnDModule = lazy(() => import('./RnDModule'));

// ─── Session 26 — Portal RnD (dedicated portal, 2026-05-15) ─────────────────
const RnDPortalDashboard      = lazy(() => import('./RnDPortalDashboard'));
const RnDVariantModule        = lazy(() => import('./RnDVariantModule'));
const RnDPatternModule        = lazy(() => import('./RnDPatternModule'));
const RnDHPPCalculatorModule  = lazy(() => import('./RnDHPPCalculatorModule'));
const RnDAnalyticsModule      = lazy(() => import('./RnDAnalyticsModule'));
// Re-use existing tabs as standalone portal modules:
const RnDStylesTab    = lazy(() => import('./RnDStylesTab'));
const RnDProductViewer = lazy(() => import('./RnDProductViewer'));  // sesi #34: katalog produk final RnD + status SSOT
const RnDSamplesTab   = lazy(() => import('./RnDSamplesTab'));
const RnDMaterialsTab = lazy(() => import('./RnDMaterialsTab'));
const RnDCostingTab   = lazy(() => import('./RnDCostingTab'));
const RnDRevisionsTab = lazy(() => import('./RnDRevisionsTab'));
// Session 27 — Tech Pack Manager + Style Detail View
const RnDTechPackModule = lazy(() => import('./RnDTechPackModule'));
const RnDStyleDetailPage = lazy(() => import('./RnDStyleDetailPage'));

// ─── Session 27 — GAP P0 SOP (KREATOR Requests, Accessory Requests, CMT Shortage) ──
const KREATORRequestModule       = lazy(() => import('./KREATORRequestModule'));
const AccessoryRequestInbox      = lazy(() => import('./AccessoryRequestInbox'));
const CMTComponentRequestModule  = lazy(() => import('./CMTComponentRequestModule'));

// Sprint 2.1 — Purchase Orders
const PurchaseOrderModule = lazy(() => import('./PurchaseOrderModule'));
// Sprint 2.3 — Leave Management
const RahazaLeaveModule = lazy(() => import('./RahazaLeaveModule'));

// Sprint 42 — Smart Auto-Attendance (Selfie+AI, WebAuthn, ZKTeco, Approval Queue)
const RahazaAutoAttendanceModule = lazy(() => import('./RahazaAutoAttendanceModule'));
const RahazaAttendanceApprovalModule = lazy(() => import('./RahazaAttendanceApprovalModule'));
// Sprint 3.1 — HR Reports
const RahazaLineBalancingModule = lazy(() => import('./RahazaLineBalancingModule'));

// Phase 22B — Shift Handover, Material Reservation, Production Calendar
const RahazaShiftHandoverModule      = lazy(() => import('./RahazaShiftHandoverModule'));
const RahazaProductionCalendarModule  = lazy(() => import('./RahazaProductionCalendarModule'));
// Phase 23 — OEE Dashboard
// User Guide
const RahazaUserGuideModule = lazy(() => import('./RahazaUserGuideModule'));
// Sprint 27 — AQL Sampling Calculator
const RahazaAQLCalculatorModule = lazy(() => import('./RahazaAQLCalculatorModule'));

// Navigation Refinement — New Combined Modules
const RahazaModelsAndBOMModule  = lazy(() => import('./RahazaModelsAndBOMModule'));
const RahazaMaterialRequirementsModule = lazy(() => import('./RahazaMaterialRequirementsModule')); // Fase 5: MRP-lite
const IntegrationSettingsModule = lazy(() => import('./IntegrationSettingsModule'));

// FG Inventory (Produk Jadi)
const RahazaFGInventoryModule   = lazy(() => import('./RahazaFGInventoryModule'));

// Session 22 (Phase 4) — P1 GRN Quality Check + Supplier Scorecard
const SupplierScorecardModule   = lazy(() => import('./SupplierScorecardModule'));
// ─── Portal Pengadaan (2026-08-06) — procurement dilepas dari Gudang/Keuangan ──
const ProcurementDashboardModule = lazy(() => import('./procurement/ProcurementDashboardModule'));
const SupplierMasterModule       = lazy(() => import('./procurement/SupplierMasterModule'));
const ProcurementSpendModule     = lazy(() => import('./procurement/ProcurementSpendModule'));
const SupplierInvoiceModule      = lazy(() => import('./procurement/SupplierInvoiceModule'));

// WMS (Phase 7 — Warehouse Management System w/ Scanner)
const WMSModule                 = lazy(() => import('./WMSModule'));

// Production Automation (Phase 4)

// Session 15 — HR AI & Portal Saya Extensions
const HRResumeScreeningModule = lazy(() => import('./hr/HRResumeScreeningModule'));
const HRAttritionModule = lazy(() => import('./hr/HRAttritionModule'));
const HRCoachingModule = lazy(() => import('./hr/HRCoachingModule'));
const MyDocumentsModule = lazy(() => import('./portal/MyDocumentsModule'));
const MyAnnualReviewModule = lazy(() => import('./portal/MyAnnualReviewModule'));
const PeerFeedbackModule = lazy(() => import('./portal/PeerFeedbackModule'));

// Session 17 Batch 1 — HR/SDM Features (P2-11, P2-12, P2-16)
const ShiftSchedulerModule = lazy(() => import('./hr/ShiftSchedulerModule'));
const JobBoardModule = lazy(() => import('./hr/JobBoardModule'));
const CareerCoachModule = lazy(() => import('./portal/CareerCoachModule'));

// Session 18 — P2-20 Skill Gap Analysis (HR)
const HRSkillGapModule = lazy(() => import('./hr/HRSkillGapModule'));

// Session 18 — P2-3 OKR Tracker, P2-7 Predictive Maintenance, P2-19 Maklon AI Quote
const OKRTrackerModule = lazy(() => import('./OKRTrackerModule'));
const PredictiveMaintenanceModule = lazy(() => import('./PredictiveMaintenanceModule'));
const MaklonAIQuoteModule = lazy(() => import('./MaklonAIQuoteModule'));

// Session 19 — E-3: AI Usage Monitor (Admin only)
const AIUsageMonitorModule = lazy(() => import('./AIUsageMonitorModule'));

// ─── Employee Expense Management (EEM) ────────────────────────────────────
const EmployeeExpenseModule      = lazy(() => import('./EmployeeExpenseModule'));
const EmployeeTravelModule       = lazy(() => import('./EmployeeTravelModule'));
const EmployeeExpenseApprovalModule = lazy(() => import('./EmployeeExpenseApprovalModule'));
const EmployeePerDiemAdminModule = lazy(() => import('./EmployeePerDiemAdminModule'));
const EmployeeTravelSettlementModule = lazy(() => import('./EmployeeTravelSettlementModule'));
const FinanceExpenseHub = lazy(() => import('./hubs/FinanceExpenseHub'));  // RC-FLOW-UX de-dup: 2 pintu expense → 1 hub ber-tab
const EmployeeExpenseGLMappingModule = lazy(() => import('./EmployeeExpenseGLMappingModule'));
const EmployeeExpenseCategoryMasterModule = lazy(() => import('./EmployeeExpenseCategoryMasterModule')); // Phase 5D
const PettyCashModule      = lazy(() => import('./PettyCashModule'));      // Phase 6B
const BankTransferModule   = lazy(() => import('./BankTransferModule'));   // Phase 6C

// Module map — id → component. IDs MUST be unique.
export const MODULE_REGISTRY = {
  // Portal dashboards
  'management-dashboard': ManagementDashboard,
  'production-dashboard': ProductionDashboardModule,
  'prod-control-tower':   ProductionControlTowerModule,    // Phase 28 — Unified daily ops dashboard
  'warehouse-dashboard':  WarehouseDashboard,
  'finance-dashboard':    FinanceDashboard,
  // Sprint 1.2: Real HR Dashboard
  'hr-dashboard':         HRDashboard,
  'hr-inbox':             HRApprovalInboxModule,    // Phase 26 — Unified HR Approval Inbox
  'approval-multilevel':  MultiLevelApprovalModule,  // Task 2.4 — Multi-Level Approval Workflow
  'hr-announcements':     AnnouncementModule,
  'hr-shift-management':  HRShiftManagementModule,   // Task 1.2 — Shift Management System

  // ─── Employee Expense Management (EEM) ─────────────────────────────────
  // PHASE B (6.1.4 #2): 5 menu HR expense/travel → 1 hub "Expense & Perjalanan". Deep-link tab aman.
  'hr-expense-hub':           HRExpenseTravelHub,
  'hr-expense-claims':        makeRedirect('hr-expense-hub', 'claims'),
  'hr-travel-requests':       makeRedirect('hr-expense-hub', 'travel'),
  'hr-travel-settlement':     makeRedirect('hr-expense-hub', 'settlement'),
  'hr-expense-approval':      makeRedirect('hr-expense-hub', 'approval'),
  'hr-per-diem-config':       makeRedirect('hr-expense-hub', 'perdiem'),
  'fin-expense-settlement':   makeRedirect('fin-expenses', 'settlement'),  // RC-FLOW-UX de-dup: buka tab settlement di hub fin-expenses (deep-link aman)
  'fin-settlement-queue':     EmployeeTravelSettlementModule, // Finance settlement queue (entry point for Finance)
  'fin-gl-mapping-config':    EmployeeExpenseGLMappingModule, // GL Mapping Configuration (Finance/Admin)
  'fin-expense-category-master': EmployeeExpenseCategoryMasterModule, // Master Kategori Expense (Phase 5D)
  'fin-petty-cash':     PettyCashModule,    // Kas Kecil / Petty Cash (Phase 6B)
  'fin-marketplace-settlement': FinanceSettlementModule,  // SESI #37 — pencairan marketplace (input + jurnal)
  'fin-bank-transfer':  BankTransferModule, // Transfer Bank Antar Rekening (Phase 6C)
  // Sprint 1.3: Master Karyawan exposed in HR portal
  'hr-employees':         HREmployeeModule,
  // Sprint 42: Smart Auto-Attendance
  // PHASE B (6.1.4 #3): 3 menu absensi → 1 hub "Absensi". Deep-link tab aman.
  'hr-attendance-hub':      HRAttendanceHub,
  'hr-attendance-sessions': HRAttendanceSessionsModule,   // FASE 16: istirahat & izin
  'hr-auto-attendance':   makeRedirect('hr-attendance-hub', 'auto'),
  'hr-attendance-approval': makeRedirect('hr-attendance-hub', 'approval'),
  // Management · Master Data & Admin
  'mgmt-customers':    BuyersModule,
  'mgmt-reports':      ReportsModule,
  'mgmt-users':        UserManagementModule,
  'mgmt-roles':        RoleManagementModule,
  // 2026-08-06 — matriks izin dihapus (dua tempat pengaturan membingungkan owner).
  // Deep-link lama diarahkan ke hub Kontrol Akses tab "Peran & Hak Akses".
  'mgmt-role-matrix':  makeRedirect('mgmt-access-hub', 'roles'),
  'mgmt-activity':     ActivityLogModule,
  'mgmt-company':      CompanySettingsModule,
  // SESI #19 — 'mgmt-pdf' & kawan-kawannya MENGARAH ke hub Pengaturan Sistem pada
  // tab 'pdf' (pola `makeRedirect` yang sama dipakai deep-link lama lainnya).
  // Alasannya bukan gaya: bila layar ini juga dipasang sebagai modul langsung,
  // isi yang sama punya DUA pintu (tab hub + menu langsung) — tepat pelanggaran
  // yang dijaga guard NAV-DUPTAB, dan pemakai yang masuk lewat deep-link kehilangan
  // tab tetangganya (Perusahaan, API Keys) tanpa tahu kenapa.
  'mgmt-pdf':          makeRedirect('mgmt-system-hub', 'pdf'),
  'mgmt-pdf-doc':      makeRedirect('mgmt-system-hub', 'pdf'),
  'sys-pdf-templates': makeRedirect('mgmt-system-hub', 'pdf'),
  'mgmt-help':         RahazaUserGuideModule,

  // Warehouse
  'wh-receiving':  ReceivingModule,
  'wh-putaway':    PutAwayModule,
  'wh-opname':     WMSOpnameScanModule,  // Fase 4: opname scan-driven (SSOT + finance) — langsung, tanpa redirect
  // FASE E: "Lokasi Bin" (legacy warehouse_locations) → redirect ke Struktur Gudang (SSOT lokasi wh_*).
  'wh-bin':        makeRedirect('wh-structure'),
  'wh-accessory':  AccessoryModule,
  'wh-returns':    WHReturnsModule,
  // FASE 6 (INV-8): Karantina QC — barang reject QC (stok diblokir) + disposisi
  'wh-quarantine': QuarantineModule,
  // FASE 6.6-A: Kesehatan & rekonsiliasi skema baris stok (juga tab di hub Stok & Akurasi)
  'wh-stock-schema': StockSchemaHealthModule,
  // Sprint 2.1: Purchase Orders — pintu resmi PINDAH ke Portal Pengadaan
  // (`proc-purchase-orders`). Id lama DIPERTAHANKAN supaya bookmark/notifikasi
  // lama tetap membuka modulnya (deep-link resolve via App.js).
  'wh-purchase-orders': PurchaseOrderModule,
  // FASE E: monolit "Scanner Barcode" dipecah → menu terpisah (WMSModule section-mode).
  'wh-structure':  withProps(WMSModule, { section: 'structure' }),
  'wh-units':      withProps(WMSModule, { section: 'units' }),
  'wh-scan':       withProps(WMSModule, { section: 'receiving' }),
  'wh-audit':      withProps(WMSModule, { section: 'audit' }),
  // Legacy id 'wms' → arahkan ke Struktur Gudang (monolit "Scanner Barcode" dibubarkan Fase E).
  'wms':           makeRedirect('wh-structure'),

  // Finance — Legacy module IDs (fin-ar, fin-ap, fin-invoices, fin-manual-invoice, fin-payments)
  // REMOVED in Session #11.17 (post Phase D). Backend routes already 404 (Session #11.16 Phase D).
  // Use SSOT routes instead: fin-ar-invoices, fin-ar-360, fin-ap-aging, maklon-billing.
  'fin-3way-match':    ThreeWayMatchModule,         // Phase 27 — PO ↔ GR ↔ AP 3-way reconciliation
  'fin-ar-360':        ARLifecycleModule,           // Phase 30 — AR 360° (Aging matrix + customer statement)
  'fin-approval':      ApprovalModule,
  'fin-recap':         FinancialRecapModule,
  // Finance · Bank Reconciliation (P1)
  'fin-bank-recon':    BankReconciliation,
  'fin-ai-cashflow':   CashFlowAI,

  // Produksi · Master Data (Fase 3)
  'prod-locations': RahazaLocationsModule,   // deeplink backward compat
  'prod-processes': RahazaProcessesModule,
  'prod-shifts':    RahazaShiftsModule,      // deeplink backward compat
  'prod-machines':  RahazaMachinesModule,    // deeplink backward compat
  'prod-lines':     RahazaLinesModule,       // deeplink backward compat
  'prod-employees': RahazaEmployeesModule,
  // Consolidation #13: Production Workspace Master (replaces 4 entries in sidebar)
  'prod-workspace-master': ProductionWorkspaceMaster,

  // Input Harian Sederhana (tanpa bundle/line — beriringan dengan existing flow)
  'prod-simple-input': makeRedirect('prod-progress'),  // FASE 5: engine lama diarsip

  // Produksi · Eksekusi (Fase 4)
  'prod-assignments':  makeRedirect('prod-work-orders'),  // FASE 5
  'prod-bulk-mi':      makeRedirect('wh-material-issue'),  // FASE 5
  'prod-line-board':   makeRedirect('prod-monitoring'),  // FASE 5

  // Phase 2 Task 2.2 — Real-time Line Monitoring Dashboard
  'prod-monitoring':   EngineMonitoringModule,  // FASE 5: monitoring engine baru

  // Produksi · Order (Fase 5a) — CLEANUP: legacy RahazaOrdersModule (rahaza_orders + tombol Generate WO 404)
  // di-nonaktifkan dari UI → redirect ke PO Internal engine (alur hidup). Router backend tetap ada (dibaca modul lain).
  'prod-orders':       makeRedirect('prod-pos-internal'),

  // Produksi · BOM + WO (Fase 5b & 5c)
  'prod-work-orders':  EngineJobsModule,  // FASE 5: production jobs engine baru

  // ── FASE 5: Engine Produksi & Maklon (SOMMERVILLE) ───────────────────────
  // CLEANUP: 'prod-pos' (semua PO, campur maklon+internal) melanggar pemisahan Master Data →
  // redirect ke PO Internal (Portal Produksi = internal saja).
  'prod-pos':              makeRedirect('prod-pos-internal'),
  'prod-pos-internal':     withProps(EnginePOModule, { businessType: 'internal' }),
  'maklon-pos-engine':     withProps(EnginePOModule, { businessType: 'maklon' }),
  'prod-progress':         EngineProgressModule,       // input progress per job-item (operator+proses)
  'prod-defects':          makeRedirect('prod-progress'),  // K5 (Phase C): laporan defect material DEPRECATED — reject FG dicatat di DA CMT-receipt
  'prod-shipments-buyer':  EngineBuyerShipmentModule,  // dispatch bertahap ke buyer
  'prod-shipments-vendor': EngineVendorShipmentModule, // kirim material ke vendor CMT
  // Phase B (2026-07-16): DA-admin proses FG dari CMT (T3 receipt inspection).
  'da-cmt-receive':        EngineDAReceiveFromCMT,     // Terima FG dari CMT (cmt_receipts SSOT)
  'cmt-permak':            CMTPermakModule,            // Permak/Rework — rework mengurangi FG (Maklon Revamp M1)
  'cmt-monitor':           CMTMonitorModule,           // Monitoring CMT: Dashboard Owner + Kejar CMT (Fase 2)
  'po-closure':            EnginePOClosure,            // Phase C: Tutup PO (auto-complete + close short)
  // FASE 22 — ALIAS DEEP-LINK (id "manusiawi" yang dipakai di catatan owner/QA).
  // Sebelumnya hash yang tidak dikenal DIAM-DIAM memantul ke halaman "Pilih Portal"
  // sehingga pengujian menyimpulkan "modulnya hilang". Alias ini menutup jurang itu.
  'da-receive-from-cmt':   makeRedirect('da-cmt-receive'),
  'production-po':         makeRedirect('prod-pos-internal'),
  'production-monitoring': makeRedirect('prod-monitoring'),
  'production-progress':   makeRedirect('prod-progress'),
  'maklon-po-engine':      makeRedirect('maklon-pos-engine'),
  'prod-variance':         EngineVarianceModule,       // variance/overproduction
  'prod-variance-report':  EngineVarianceReport,       // laporan variance penerimaan buyer
  'prod-serial-engine':    EngineSerialModule,         // serial tracking engine baru


  // Produksi · Bundle Traceability (Phase 17A)
  'prod-bundles':      makeRedirect('prod-work-orders'),  // FASE 5: bundles dihapus

  // ── P0 FIX: Previously broken menus ────────────────────────────────────
  // Papan Rework — was missing mapping, falls back to ManagementDashboard
  'prod-rework-board':    makeRedirect('prod-material-returns'),  // FASE 5
  // Pengaturan Alert — was missing mapping
  'prod-alert-settings':  RahazaAlertSettingsModule,

  // IA v2.1 — Hub konsolidasi Produksi (menu = hub; moduleId lama tetap sbg deep-link standalone)
  'prod-monitoring-hub':     makeRedirect('prod-monitoring'),  // FASE 5
  'prod-analytics-hub':      ProductionAnalyticsHub,
  'prod-master-process-hub': ProductionMasterProcessHub,
  'prod-master-product-hub': ProductionMasterProductHub,

  // Produksi · Eksekusi Proses — CV. Dewi Aditya (Cutting/CMT/Finishing/QC/Packing)
  // PHASE B (6.1.4 #1): 5 menu prod-exec-* → 1 hub "Eksekusi Proses". Deep-link tab tetap aman.
  'prod-exec-hub':      makeRedirect('prod-progress'),  // FASE 5: eksekusi = input progress engine
  'prod-exec-cutting':  makeRedirect('prod-progress'),  // FASE 5
  'prod-exec-sewing':   makeRedirect('prod-progress'),
  'prod-exec-finishing':makeRedirect('prod-progress'),
  'prod-exec-qc':       makeRedirect('prod-progress'),
  'prod-exec-rework':   makeRedirect('prod-progress'),
  'prod-exec-packing':  makeRedirect('prod-progress'),
  // Legacy PT Rahaza (redirect ke proses setara, backward compat)
  'prod-exec-rajut':    makeRedirect('prod-progress'),
  'prod-exec-linking':  makeRedirect('prod-progress'),
  'prod-exec-steam':    makeRedirect('prod-progress'),
  'prod-exec-washer':   makeRedirect('prod-progress'),
  'prod-exec-sontek':   makeRedirect('prod-progress'),

  // Warehouse · Inventory Rahaza (Fase 7)
  'wh-materials':      RahazaMaterialsModule,     // deeplink backward compat
  // RC-IA-warehouse-1 (Opsi A): 3 modul stok → wms-stock-hub (deep-link tab)
  'wms-stock-hub':     WMSStockHub,
  'wh-stock':          makeRedirect('wms-stock-hub', 'stock'),

  // Consolidation #3: Master Hub (replaces wh-materials + wh-fg in sidebar)
  'wh-master':         WarehouseMasterHub,
  // SESI #33 — dua pintu baru portal Gudang
  'wh-shopping-list':  WeeklyShoppingListModule,
  'wh-cost-history':   MaterialCostHistoryModule,
  'wh-material-issue': RahazaMaterialIssueModule,
  // Accessory modules (mapped from restructured IA)
  'wh-accessory-master': RahazaMaterialsModule,  // Reuse materials module for accessory master
  'wh-accessory-stock':  RahazaStockModule,      // Reuse stock module for accessory stock
  'wh-accessory-ops':    makeRedirect('accessories-master-stock'),  // RC-IA-3a: de-dup — transaksi & opname aksesoris resmi di Portal Aksesoris (domain terpisah dari material)
  // FG Inventory
  'wh-fg':             RahazaFGInventoryModule,   // deeplink backward compat

  // Session 22 (Phase 4) — Supplier Quality Scorecard (P1 GRN QC)
  'wh-supplier-scorecard': SupplierScorecardModule,

  // HR · Attendance (Fase 8a)
  'hr-attendance':     makeRedirect('hr-attendance-hub', 'manual'),   // PHASE B: → hub tab manual
  'hr-overtime':       RahazaOvertimeModule,

  // HR · Payroll (Fase 8b + 8c)
  'hr-payroll-profiles':  RahazaPayrollProfilesModule,
  'hr-payroll-run':       RahazaPayrollRunModule,
  'hr-payroll-dashboard': PayrollDashboardModule,      // Phase 3 — Payroll Automation Dashboard

  // Sprint 2.3: Leave Management
  'hr-leave':            RahazaLeaveModule,
  'hr-leave-balances':   HRLeaveBalancesModule,
  'hr-admin':            HRAdminModule,
  'hr-360-feedback':     HR360FeedbackModule,         // deeplink backward compat
  // Consolidation #14: HR Performance Hub (replaces 3 entries in sidebar)
  'hr-performance-hub':  HRPerformanceHub,
  
  // Sprint 3.1: HR Reports
  'hr-reports':          RahazaHRReportsModule,

  // Finance · Enhanced (Fase 8.5)
  'fin-cost-centers':  RahazaCostCentersModule,
  'fin-ar-invoices':   RahazaARInvoicesModule,
  'fin-channel-gl':    FinChannelGLMappingModule,   // P3 — Channel GL Mapping (revenue routing)
  'fin-cash':          RahazaCashAccountsModule,
  'fin-expenses':      FinanceExpenseHub,  // RC-FLOW-UX de-dup: hub ber-tab (Pengeluaran + Klaim Disbursement)

  // Finance · HPP (Fase 9)
  'fin-hpp':           RahazaHPPModule,
  // 2026-08-23 — HPP per Potong & per Model: HPP produk lahir dari BOM × harga
  // pembelian + upah CMT + upah cutting/internal (bukan ketikan master).
  'fin-hpp-produk':    ProductCostingModule,
  // sesi #34 — pintu INPUT biaya jahit per SKU/pcs di SPK + viewer HPP batch (FIFO).
  'prod-sewing-cost':  SewingCostModule,

  // Management · Overview (Fase 10)
  'mgmt-overview':     ManagementOverviewModule,

  // Produksi · Sales Closure (Fase 14)
  'prod-shipments':    makeRedirect('wms-delivery-notes'),  // O1.1 — SSOT surat jalan = WMS Delivery Notes (rahaza_shipments kosong)

  // Management · Master Data (Fase 5a — ganti BuyersModule dengan Rahaza Customers)
  // 2026-08-06 DIHAPUS: 'mgmt-rahaza-customers' (Data Pelanggan) — master duplikat &
  // kosong (rahaza_customers = 0 dokumen). Pelanggan nyata: klien maklon
  // (dewi_maklon_clients) & buyer PO. Keputusan owner: hapus menunya.

  // Produksi · Andon Panel (Phase 18B)
  'prod-andon-board': makeRedirect('prod-monitoring'),  // FASE 5: andon dihapus

  // Produksi · SOP Inline (Phase 18D)
  'prod-sop': RahazaSOPModule,

  // Finance · Accounting Core (Phase F1)
  'fin-coa':               RahazaCOAModule,
  'fin-journal-hub':       FinanceJournalHub,       // BACKLOG-A T3.3

  // IA v2.1 — Hub konsolidasi Keuangan (menu = hub; moduleId lama tetap sbg deep-link standalone)
  'fin-reports-hub':            FinanceReportsHub,
  'fin-accounting-master-hub':  FinanceAccountingMasterHub,

  // IA v2.1 fase-2/3 — hub konsolidasi (deep-link moduleId lama tetap ada di registry)
  'mgmt-access-hub':   ManagementAccessHub,
  'mgmt-system-hub':   ManagementSystemHub,
  'hr-payroll-hub':    HRPayrollHub,
  'hr-shift-hub':      HRShiftHub,
  'hr-leave-hub':      HRLeaveHub,
  'marketing-kol-hub': MarketingKOLHub,
  'fin-journal-entry':     makeRedirect('fin-journal-hub', 'entry'),   // T3.3 → hub
  'fin-trial-balance':     RahazaTrialBalanceModule,
  'fin-general-ledger':    RahazaGeneralLedgerModule,
  'fin-periods':           RahazaPeriodsModule,

  // Finance · Accounting Core (Phase F2)
  'fin-posting-profiles':  RahazaPostingProfilesModule,
  'fin-pnl':               RahazaPnLModule,
  'fin-balance-sheet':     RahazaBalanceSheetModule,
  'fin-journal-list':      makeRedirect('fin-journal-hub', 'list'),    // T3.3 → hub
  'fin-ap-aging':          RahazaAPAgingModule,

  // Finance · Accounting Core (Phase F3)
  'fin-cash-flow':         RahazaCashFlowModule,
  'fin-budget':            BudgetModule,
  'fin-fixed-assets':      FixedAssetsModule,
  'fin-executive-report':  ExecutiveReportModule,      // Phase 3 — Executive Report Hub
  'reports-hub':           ReportsHubModule,           // WS-B(b) — Pusat Laporan terpusat

  // Finance · Phase B (2026-06-01) — 8 UI Modules for Advanced Features
  // PHASE B (6.1.4 #4): 5 menu jurnal-otomatis → 1 hub "Penyesuaian Akuntansi". Deep-link tab aman.
  'fin-acctg-adjust-hub':      FinanceAccountingAdjustHub,
  'fin-accruals':              makeRedirect('fin-acctg-adjust-hub', 'accruals'),
  'fin-asset-depreciation':    makeRedirect('fin-acctg-adjust-hub', 'depreciation'),
  'fin-bad-debt-writeoff':     makeRedirect('fin-acctg-adjust-hub', 'baddebt'),
  'fin-asset-disposal':        makeRedirect('fin-acctg-adjust-hub', 'disposal'),
  'fin-purchase-discount':     makeRedirect('fin-acctg-adjust-hub', 'discount'),

  // HR · Phase B — Employee Loans Module (W-T2.1: legacy → redirect ke Kasbon & Pinjaman kanonik)
  'hr-employee-loans':         makeRedirect('hr-kasbon'),

  // Phase 12 — Kasbon & Pinjaman Karyawan
  'hr-kasbon':                 HRKasbonModule,
  'fin-kasbon':                FinanceKasbonModule,

  // Warehouse · Phase B — Inventory Adjustments
  // RC-IA-warehouse-3: jalur adjust RESMI (rahaza/material-adjust + posting GL). Kini tab di wms-stock-hub.
  'wh-inventory-adjustments':  makeRedirect('wms-stock-hub', 'adjust'),

  // Management · System Administration
  'mgmt-backup-restore':       BackupRestoreModule,
  'sys-doc-numbering':         DocNumberingModule,

  // Session 13 — SLA Dashboard, Management Tools, Smart Warehouse
  // Phase 3.3A Batch 2: maklon-sla-dashboard konsolidasi ke maklon-dashboard sebagai tab
  'maklon-sla-dashboard':  makeRedirect('maklon-dashboard', 'sla'),  // DEPRECATED → redirect ke maklon-dashboard tab SLA
  'mgmt-tools':            ManagementToolsModule,
  'warehouse-smart':       WarehouseSmartModule,

  // Session 14 — AI Business Intelligence
  'ai-business-dashboard': AIBusinessDashboard,  // Direct access masih bekerja (redirect dari sidebar dihapus DA46)

  // Phase 21 — Decision Support & Quality Metrics
  'prod-defect-codes':     makeRedirect('prod-progress'),  // K5 (Phase C): defect reports deprecated
  'prod-pareto':           makeRedirect('prod-progress'),  // K5 (Phase C)

  // Phase 7: Marketing AR Bridge & Admin Setup
  'marketing-ar-bridge': MarketingARBridgeModule,
  'admin-setup-panel': AdminSetupPanelModule,

  'prod-fpy':              makeRedirect('prod-progress'),  // K5 (Phase C)
  'prod-downtime':              RahazaDowntimeModule,
  'prod-backlog':               makeRedirect('prod-monitoring'),  // FASE 5
  'fin-procurement-requests': ProcurementRequestModule,    // P1.C — Procure-to-Pay PR Flow
  'procurement-requests':     ProcurementRequestModule,    // alias

  // ─── PORTAL PENGADAAN (2026-08-06) ─────────────────────────────────────────
  // Portal baru: procurement dilepas dari Gudang (PO, Penilaian Supplier),
  // Keuangan (Permintaan Pengadaan, Rekonsiliasi PO), dan Aksesoris (Purchase
  // Request). Id `proc-*` adalah pintu RESMI; id lama tetap hidup untuk deep-link.
  'proc-dashboard':        ProcurementDashboardModule,
  'proc-suppliers':        SupplierMasterModule,
  'proc-scorecard':        SupplierScorecardModule,
  'proc-analytics':        ProcurementSpendModule,
  'proc-requests':         ProcurementRequestModule,
  'proc-purchase-orders':  PurchaseOrderModule,
  // 2026-08-06 — pintu pengadaan HANYA tab pembelian (`allowedTabs`), supaya
  // Master/Stok/Opname/Valuasi aksesoris tetap menjadi urusan Portal Aksesoris.
  'proc-accessory-pr':     withProps(AccessoryModule, {
    defaultTab: 'pr',
    allowedTabs: ['pr'],
    headerTitle: 'Request Pembelian Aksesoris',
    headerSubtitle: 'Ajukan & pantau pembelian aksesoris (kancing, label, hangtag, kemasan) ke supplier.',
  }),
  'proc-3way-match':       ThreeWayMatchModule,
  'proc-ap-invoices':      SupplierInvoiceModule,

  'prod-capacity-planning':     CapacityPlanningModule,   // Phase 2 — Capacity Planning Lite

  // Phase 20C — AI Insights
  // FASE IA-1 (2026-07-26): 'prod-ai-insights' DULU menunjuk RahazaAIModule = modul
  // "HR AI Insights" (identik dgn tab hr-ai-hub/insights) ⇒ pintu Produksi berlabel AI
  // produksi tapi isinya AI SDM. Sekarang menunjuk AI produksi yang benar
  // (/api/analytics/ai/*). Modul HR AI tetap diakses lewat Portal SDM (hr-ai-hub).
  'prod-ai-insights':      AIInsightsModule,
  'hr-ai-hub':             HRAIHub,                                     // BACKLOG-A T3.5
  'hr-ai-insights':        makeRedirect('hr-ai-hub', 'insights'),       // T3.5 → hub

  // FASE IA-1 — pintu "Invoice" (Tagihan CMT / AP jasa jahit). Backend sudah lama
  // menerbitkan `dewi_cmt_payments` tanpa ada layar yang menampilkannya.
  'prod-cmt-billing':      ProductionCMTBillingModule,

  // Session 15 — HR AI Extensions
  'hr-resume-screening':   HRResumeScreeningModule,
  'hr-attrition':          makeRedirect('hr-ai-hub', 'attrition'),      // T3.5 → hub
  'hr-coaching':           makeRedirect('hr-ai-hub', 'coaching'),       // T3.5 → hub

  // Session 17 — HR/SDM Features
  'hr-shift-scheduler':    ShiftSchedulerModule,
  'hr-job-board':          JobBoardModule,
  
  // Session 18 — P2-20 Skill Gap Analysis
  'hr-skill-gap':          makeRedirect('hr-ai-hub', 'skill-gap'),      // T3.5 → hub
  
  // Session 18 — P2-3 OKR Tracker, P2-7 Predictive Maintenance, P2-19 Maklon AI Quote
  'mgmt-okr':              OKRTrackerModule,
  'prod-predictive-maintenance': PredictiveMaintenanceModule,
  'maklon-ai-quote':       MaklonAIQuoteModule,
  
  // Session 19 — E-3 AI Usage Monitor
  'ai-usage-monitor':      AIUsageMonitorModule,
  
  // Phase 3.3B — Unified Approval Hub (Aggregator Dashboard)
  'unified-approval-hub':  UnifiedApprovalHub,
  
  // Session 17 — Portal Saya AI Features
  'portal-career-coach':   CareerCoachModule,

  // Staff Self-Service Portal
  'self-dashboard':        SelfServicePortal,

  // Portal Saya — Self-Service HR + My Workspace
  'portal-dashboard':      PortalSayaDashboard,
  'portal-profile':        PortalSayaProfile,
  'portal-cuti':           PortalSayaCuti,
  'portal-absen':          PortalSayaAbsen,
  'portal-payslip':        PortalSayaPayslip,
  'portal-training':       PortalSayaTraining,
  'portal-notifikasi':     PortalSayaNotifikasi,
  'portal-workspace':      WorkspaceHub,
  'portal-kasbon':         KasbonStaffModule,
  
  // Session 15 — Portal Saya Extensions
  'portal-documents':      MyDocumentsModule,
  'portal-annual-review':  MyAnnualReviewModule,
  'portal-peer-feedback':  PeerFeedbackModule,

  // Phase 22B — Shift Handover, Material Reservation, Production Calendar
  'prod-shift-handover':       RahazaShiftHandoverModule,
  'prod-material-reservation': makeRedirect('wh-material-issue'),  // FASE 5
  'prod-production-calendar':  RahazaProductionCalendarModule,
  // Sprint 27 — AQL Sampling Calculator
  'prod-aql-calculator':       RahazaAQLCalculatorModule,

  // ─── Navigation Refinement Phase 1 — New Combined Modules ───────────────
  // Task 1.3: Model + BOM + Sizes combined
  'prod-models-bom':       RahazaModelsAndBOMModule,
  // Fase 5: Laporan Kebutuhan Material (MRP-lite agregasi BOM)
  'prod-material-requirements': RahazaMaterialRequirementsModule,
  // Task 2 (Sistem): API Key management
  'mgmt-integrations':     IntegrationSettingsModule,

  // ─── Production Automation (Phase 4) ──────────────────────────────────────
  // Production Wizard (P0) - gabung Order → WO → Release → Bundles
  'prod-wizard':           makeRedirect('prod-pos-internal'),  // FASE 5: PO internal engine

  // ─── Portal Maklon (Fase 3) ───────────────────────────────────────────────
  'maklon-dashboard': MaklonDashboard,
  // 2026-08-05 — pintu langsung ke tab "Alur Produksi" (sumber
  // GET /api/prod/dashboard?business_type=maklon; label akhir "Dispatch ke Buyer")
  'maklon-alur-produksi': makeModuleWithTab(MaklonDashboard, 'alur'),
  'maklon-clients':   MaklonClientManagement,
  // Phase M1: Buyer Catalog (master artikel buyer Maklon)
  'maklon-buyer-catalog': MaklonBuyerCatalogModule,
  // 'maklon-orders' removed (Phase C 2026-05-23) — redirects below alias to maklon-po
  // Fase 3B: Sample & QC
  'maklon-samples':   MaklonSampleManagement,
  'maklon-qc':        makeRedirect('maklon-dashboard'),  // K5 (Phase C): stage-based QC DEPRECATED — reject FG dicatat di DA CMT-receipt
  'maklon-tracking':  MaklonProductionTracking,
  // Fase 3C: Billing & HPP + System Config
  'maklon-billing':   MaklonBillingModule,
  'maklon-hpp':       MaklonHppModule,
  'maklon-config':    MaklonSystemConfigModule,
  // Phase 4 P1: Notification Center
  'maklon-notifications': NotificationCenterModule,

  // ── Production-Maklon Overhaul — New Modules ────────────────────────────
  // CLEANUP: MaklonPOModule (PO Maklon LAMA, native dewi_maklon_pos) dinonaktifkan dari UI →
  // semua pembuatan PO Maklon lewat engine (maklon-pos-engine). dewi_maklon_pos tetap ada
  // sebagai MIRROR untuk Finance (via production_maklon_bridge). Deep-link lama → engine.
  'maklon-po':          makeRedirect('maklon-pos-engine'),
  'maklon-po-360':      MaklonPO360Module,     // Unified 360° view per PO (baca mirror dewi_maklon_pos — tetap valid)
  // O1.2 — CMT de-dup: koleksi dewi_cmt_* KOSONG; SSOT = WMS + Vendor Portal. Redirect deep-link lama.
  // FASE H-8 (2026-08-16, keputusan owner "jangan ada layar kosong"): alias ini dulu
  // mengarah ke `wms-cmt-dispatches` yang koleksinya (`wh_cmt_dispatches`) 0 dokumen.
  // Sekarang diarahkan ke pintu yang BENAR-BENAR mengerjakan pekerjaan itu: progres CMT
  // dipantau di Monitoring CMT (`cmt-monitor`), bukan di layar pengiriman.
  'cmt-progress':       makeRedirect('cmt-monitor'),          // was CMTProgressModule → wms-cmt-dispatches (kosong)
  'cmt-lifecycle':      makeRedirect('vendor-admin'),        // was CMTLifecycleModule
  
  // Session #11.21 — Vendor CMT Portal (2026-05-27)
  // FASE 7 (audit 2026-07-31, cacat CRIT CMT-1): modul portal vendor LAMA
  // dipensiunkan. Model datanya sendiri (`vendor_jobs`/`vendor_progress_reports`)
  // tidak tersambung ke PO/dispatch/tagihan — progress yang diisi di sini tidak
  // berpengaruh apa pun. Portal vendor yang BENAR = engine/VendorPortalApp.jsx
  // (otomatis dibuka saat login role `cmt_vendor`, memakai /api/production-*).
  // Deep-link lama diarahkan ke portal vendor engine agar tidak menjadi menu hantu.
  'vendor-portal':      VendorCMTEnginePortal,      // DEPRECATED alias → portal vendor SSOT
  'vendor-admin':       VendorAccountsAdminModule,  // Admin: kelola vendor partners + accounts + jobs
  // Pintu "Input Vendor CMT" — mengisi portal vendor ATAS NAMA vendor CMT yang
  // tidak memakai sistem. RBAC pintu dijaga komponennya sendiri (ALLOWED_ROLES)
  // DAN backend (core/cmt_override.OVERRIDE_ROLES) — dua lapis, bukan satu.
  'cmt-override-portal': CMTOverridePortalModule,

  // ─── Portal Marketing (eks-Toko Online — Rebrand in-place) ────────────────
  // Marketing Phase 1+2+3: Multi-account dashboard, Sales data, Task Management
  'toko-dashboard':         MarketingDashboard,        // SSOT: Marketing Dashboard (Phase 1+2+3)
  // Phase 3.3A: toko-dashboard-legacy & toko-dashboard-classic → redirect ke SSOT
  // makeRedirect digunakan agar deep-link lama tetap aman
  'toko-dashboard-legacy':  makeRedirect('toko-dashboard'),   // DEPRECATED → redirect ke toko-dashboard
  'toko-dashboard-classic': makeRedirect('toko-dashboard'),   // DEPRECATED → redirect ke toko-dashboard
  'marketing-accounts':     AccountManagementModule,   // NEW Phase 1
  'marketing-account-review': AccountBulkReviewModule,  // BD-5 koreksi massal data toko
  'marketing-sales':        SalesDataEntryModule,      // NEW Phase 2
  'marketing-import':       ImportCenterModule,        // Phase 1 Universal Smart Import Engine
  // sesi #34 — pintu PENCAIRAN marketplace di portal Marketing (backend F9 sudah
  // ada sejak 2026-08-14 tetapi tanpa layar; pemilik: "di mana menu pencairan?").
  'marketing-settlements':  MarketingSettlementsView,
  // Sesi #20 — jembatan identitas barang & audit sinkronisasi
  'sku-bridge':             SkuBridgeModule,
  'sync-audit':             SyncAuditModule,
  'marketing-kol':          KOLCreatorModule,           // KOL Management
  'marketing-catalog':      CatalogManagementModule,   // Phase 5 Catalog Management
  'marketing-tasks':        TaskManagementModule,      // NEW Phase 3 — Kanban
  'marketing-approvals':    ApprovalInboxModule,       // NEW Phase 3 — Approval Inbox
  'marketing-templates':    TaskTemplatesModule,       // NEW Phase 3 — Templates
  // Consolidation #10: Task Hub (replaces 3 entries above in sidebar)
  'marketing-task-hub':     MarketingTaskHubModule,    // Hub: Kanban + Approval + Templates
  // Phase 2 Week 4-5: Orders & Complaints
  'marketing-orders':       UnifiedOrdersDashboard,    // NEW Phase 2 Week 4 — Unified Orders Dashboard
  'marketing-fulfillment':  FulfillmentMonitorModule,  // F3 — Monitoring Pengiriman (belum dikirim / lewat batas / batal / retur)
  // F8 & KATALOG-DARI-MASTER hidup sebagai TAB di hub yang sudah ada (satu pintu
  // per fungsi — aturan IA v2.1). Deep-link-nya menunjuk KOMPONEN HUB-nya langsung
  // dan hub membaca `moduleId` untuk memilih tab awal.
  //
  // Kenapa BUKAN `makeRedirect(...)`: pola redirect menitipkan kunci tab di
  // sessionStorage lalu memanggil `onNavigate`, jadi tab yang benar bergantung pada
  // URUTAN mount (redirect harus menulis SEBELUM hub membaca). Uji layar 2026-08-12
  // membuktikan urutan itu tidak bisa diandalkan: deep-link mendarat di tab pertama
  // (Overview / Katalog) sehingga layar yang diminta seolah tidak ada. `moduleId`
  // sudah dikirim App.js ke setiap modul, jadi tidak ada balapan sama sekali.
  'marketing-weekly-report':       MarketingReportsHub,      // F8 — mendarat di tab 'Rapat Mingguan'
  'marketing-catalog-from-master': CatalogManagementModule,  // mendarat di tab 'Isi dari Master'
  // Consolidation #9: After Sales Hub (replaces marketing-complaints + marketing-returns in sidebar)
  'marketing-after-sales':  MarketingAfterSalesHub,   // Hub: Komplain + Returns + Resolution Log
  // RC-FLOW-UX-11d (Session #26): standalone deep-link → redirect ke hub tab yang tepat.
  // Alasan: 5 pintu paralel untuk fitur identik. Sisakan 1 pintu Marketing = `marketing-after-sales`.
  'marketing-complaints':   makeRedirect('marketing-after-sales', 'complaints'), // was ComplaintsManagementModule (standalone)
  // Phase 3 Week 6-7: Account Health, Sales Performance, Ads, Live
  'marketing-health':       AccountHealthDashboard,     // NEW Phase 3 Week 6 — Account Health Dashboard
  'marketing-performance':  SalesPerformanceDashboard,  // deeplink backward compat
  'marketing-ads':          AdsPerformanceDashboard,    // deeplink backward compat
  'marketing-live-hub':      MarketingLiveHub,           // BACKLOG-A T3.6
  'marketing-live':          makeRedirect('marketing-live-hub', 'sessions'),  // T3.6 → hub
  // Phase 3 Week 8-10: Content Calendar, Discount, Product Launch
  'marketing-content-calendar': ContentCalendarModule,  // Phase 3 Week 8
  'marketing-discounts':        DiscountCampaignModule, // Phase 3 Week 9
  'marketing-product-launches': ProductLaunchModule,    // Phase 3 Week 10
  // Phase 3 Week 11-12: Overview + Integration Settings
  'marketing-overview':              MarketingOverviewDashboard,    // deeplink backward compat
  // Consolidation #8: Marketing Reports Hub (replaces 5 entries in sidebar)
  'marketing-reports':               MarketingReportsHub,
  'marketing-integration-settings':  MarketingIntegrationSettings, // Phase 3 Week 12
  'marketing-webhooks':              MarketingWebhooksModule,      // Phase 1/2 — Webhook Events Monitor
  'marketing-live-analytics':        makeRedirect('marketing-live-hub', 'analytics'), // T3.6 → hub
  'marketing-ai-hub':                MarketingAIHub,               // BACKLOG-A T3.4
  'marketing-ai-insights':           makeRedirect('marketing-ai-hub', 'insights'),  // T3.4 → hub
  'marketing-advanced-ai':           makeRedirect('marketing-ai-hub', 'advanced'),  // T3.4 → hub
  // Session 12 — P1-4, P1-5, P1-8, P1-6/7
  'marketing-ai-content':            makeRedirect('marketing-ai-hub', 'content'),   // T3.4 → hub
  'marketing-ai-image':              makeRedirect('marketing-ai-hub', 'image'),     // T3.4 → hub
  'marketing-kol-leaderboard':       KOLLeaderboardModule,
  'marketing-scheduler':             MarketingSchedulerModule,
  // Phase 3 Week 13: Fitur Internal
  'marketing-reviews':   RatingReviewModule,      // Phase 3 Week 13 — Rating & Review Management
  // RC-FLOW-UX-11d (Session #26): standalone → redirect ke hub tab.
  'marketing-returns':   makeRedirect('marketing-after-sales', 'returns'), // was ReturnsRefundsModule (standalone)
  'marketing-samples':   SampleDeliveryModule,    // Phase 3 Week 13 — Sample Delivery Tracking
  'marketing-livehost':  makeRedirect('marketing-live-hub', 'livehost'),  // T3.6 → hub
  'marketing-targets':   AccountTargetsModule,    // Session 28 — Monthly Target per Akun
  // F5 — layar SIKLUS (target → anggaran → omzet) dipakai DUA portal dengan
  // KOMPONEN YANG SAMA lewat prop `scope`. Menyalin komponennya akan melahirkan
  // dua layar yang bisa menampilkan angka berbeda untuk bulan yang sama.
  'mgmt-marketing-cycle': withProps(AccountTargetsModule, { scope: 'management' }),
  // F6.5 (sesi #9) — layar "siapa mengubah apa". SATU komponen dipakai Portal
  // Marketing & Portal Manajemen (prop `scope` hanya mengubah kalimat judul):
  // menyalin komponennya akan melahirkan dua layar audit yang bisa bercerita beda.
  'marketing-change-log': MarketingChangeLogModule,
  'mgmt-marketing-change-log': withProps(MarketingChangeLogModule, { scope: 'management' }),
  'marketing-daily-report':   DailyReportModule,   // deeplink backward compat
  'marketing-monthly-report': MonthlyReportModule, // deeplink backward compat

  // Existing Toko Online (legacy operasional marketplace)
  // F4.4 — `toko-products` adalah PINTU KEMBAR katalog produk (dua layar untuk satu
  // fungsi ⇒ dua kebenaran). Sejak F4, katalog punya satu layar dengan dua tampilan
  // (Tabel + Kartu) di `marketing-catalog`, jadi deep-link lama diarahkan ke sana.
  // F10 (2026-08-13) — berkas `TokoProductCatalogModule.jsx` SUDAH DIHAPUS sesudah
  // pengalihan ini terbukti bekerja (uji layar F4: mendarat di "Manajemen Katalog
  // Produk", sidebar menyorot benar). Deep-link lama tetap hidup lewat pengalih
  // di bawah — jadi tidak ada tautan yang mati, tetapi kodenya berhenti bercabang.
  'toko-products':  makeRedirect('marketing-catalog'),
  'toko-channels':  TokoChannelManagerModule,
  // Phase 5B: Orders (dengan tab variant)
  'toko-orders':    makeModuleWithTab(TokoOrdersModule, 'orders'),
  'toko-packing':   makeModuleWithTab(TokoOrdersModule, 'packing'),
  'toko-shipping':  makeModuleWithTab(TokoOrdersModule, 'shipping'),
  // Phase 6: Fulfillment (Online Order Bridge: Marketing → Inventory)
  'fulfillment':    FulfillmentModule,
  // Phase 2 Enhancement: DO Management + Unified Inventory Viewer
  // FASE H-8 (2026-08-16): dulu → `wms-cmt-dispatches` (koleksi `wh_cmt_dispatches` = 0
  // dokumen ⇒ layar kosong). Surat jalan/pengiriman material ke CMT yang NYATA hidup di
  // `vendor_shipments` lewat pintu "Kirim Material CMT".
  'do-management':      makeRedirect('prod-shipments-vendor'),
  'unified-inventory':  makeRedirect('wms-stock-hub', 'viewer'),  // RC-IA-warehouse-1: viewer tab di stock hub

  // Phase 7 — Laporan & Dashboard
  'phase7-reports':     Phase7ReportingModule,
  // Phase 5B: Pricing & Flashsale
  'toko-pricing':   TokoPricingFlashsaleModule,
  // Phase 5B: KOL Management — REMOVED in Session #11.17 (post Phase C+D).
  // Use marketing-kol (SSOT) and marketing-kol-leaderboard from Marketing portal.
  // Phase 5B: Customer Service & Returns
  // RC-FLOW-UX-11d (Session #26): TokoCS/TokoReturns memanggil endpoint yang SAMA
  // dengan marketing-after-sales → redirect ke hub tab yang tepat.
  'toko-cs':        makeRedirect('marketing-after-sales', 'complaints'), // was makeModuleWithTab(TokoCSReturnsModule, 'cs')
  'toko-returns':   makeRedirect('marketing-after-sales', 'returns'),    // was makeModuleWithTab(TokoCSReturnsModule, 'returns')

  // ─── Fase 2: Cutting & CMT ────────────────────────────────────────────────
  'prod-cutting': makeRedirect('prod-progress'),  // FASE 5: cutting engine lama diarsip
  'prod-cmt':         makeRedirect('vendor-admin'),        // O1.2 — was CMTManagementModule (dewi_cmt_* kosong)
  // FASE H-8 (2026-08-16): "packing CMT" = MENERIMA hasil jadi dari CMT (QC + posting FG,
  // koleksi `cmt_receipts`). Dulu dialihkan ke `wms-cmt-dispatches` yang koleksi
  // dispatch-nya 0 dokumen. Pintu yang benar-benar mengerjakannya: "Terima FG dari CMT".
  'prod-cmt-packing': makeRedirect('da-cmt-receive'),
  'prod-material-returns': EngineReturnModule,  // FASE 5: returns engine baru

  // ─── Phase 6 — HRIS (Full) ────────────────────────────────────────────────
  'hr-performance': HRPerformanceModule,     // deeplink backward compat
  'hr-kpi':         HRKPIModule,             // deeplink backward compat
  'hr-lms':         HRLMSModule,
  'hr-onboarding':  HROnboardingModule,
  'hr-recruitment': HRATSModule,
  'hr-org-chart':   HROrgChartModule,
  'kpi-portal': KPIPortalModule,
  'hr-assets': HRAssetModule,
  'hr-payroll-allowances': RahazaPayrollAllowancesModule,
  // Sprint 42 — Salary Adjustment with Dual Approval (Manager + HR)
  'hr-salary-adjustments': RahazaSalaryAdjustmentModule,
  'ai-actions': makeRedirect('hr-ai-hub', 'actions'),                   // T3.5 → hub
  'wh-picklist': WMSPickListModule,
  // WMS P0/P1 Garment Features
  'wms-fabric-rolls':    WMSFabricRollsModule,
  'wms-delivery-notes':  WMSDeliveryNotesModule,
  'wms-cmt-dispatches':  WMSCMTDispatchesModule,
  // FASE H-3 (2026-08-16): pintu BARU "Buat Barcode" (label bahan & barang jadi).
  'wh-barcode':          WMSBarcodeModule,
  'wms-opname-enhanced': WMSOpnameScanModule,   // Fase 4: dialihkan ke opname scan-driven (SSOT + finance)
  'wms-opname-scan':     WMSOpnameScanModule,

  // ─── Phase 7 — RnD & Style Master ─────────────────────────────────────────
  'rnd-module': RnDModule,

  // ─── Session 26 — Portal RnD (dedicated portal modules, 2026-05-15) ────────
  'rnd-dashboard':  RnDPortalDashboard,
  // PHASE B (6.1.4 #5): 5 modul desain/dokumentasi → 1 hub "Desain & Tech Pack". Deep-link tab aman.
  'rnd-design-hub': RnDDesignHub,
  'rnd-styles':     makeRedirect('rnd-design-hub', 'styles'),
  // sesi #34 — viewer produk final RnD (master data) + status sync marketing/produksi
  'rnd-product-viewer': RnDProductViewer,
  'rnd-variants':   makeRedirect('rnd-design-hub', 'variants'),
  'rnd-samples':    RnDSamplesTab,
  'rnd-revisions':  makeRedirect('rnd-design-hub', 'revisions'),
  'rnd-materials':  RnDMaterialsTab,
  'rnd-patterns':   makeRedirect('rnd-design-hub', 'patterns'),
  'rnd-costing-hub': RnDCostingHub,                       // BACKLOG-A T3.9
  'rnd-costing':    makeRedirect('rnd-costing-hub', 'costing'), // T3.9 → hub
  'rnd-hpp':        makeRedirect('rnd-costing-hub', 'hpp'),     // T3.9 → hub
  'rnd-analytics':  RnDAnalyticsModule,
  // Session 27 — RnD Enhancement: Tech Pack Management + Style Detail View
  'rnd-techpack':   makeRedirect('rnd-design-hub', 'techpack'),
  'rnd-style-detail': RnDStyleDetailPage,  // Modal/Side panel, tidak untuk routing langsung

  // ─── Session 27 — GAP P0 SOP (KREATOR Requests, Accessory Inbox, CMT Shortage) ───
  'marketing-kreator-requests':       KREATORRequestModule,
  'rnd-kreator-requests':             KREATORRequestModule,  // alias agar bisa diakses dari Portal RnD
  'warehouse-accessory-requests':     AccessoryRequestInbox,
  'rnd-accessory-requests':           AccessoryRequestInbox,  // alias untuk RnD self-monitor
  'production-cmt-component-requests': CMTComponentRequestModule,
  'cmt-component-requests':           CMTComponentRequestModule,  // alias generic

  // ─── New Portals: Collaboration (Communication + Workspace + Learning) + Asset Management ───────────────────
  'collaboration':            lazy(() => import('./CollaborationPortal')),
  'collab-workspace':         lazy(() => import('./WorkspacePortal')),  // Spreadsheet Workspace
  'collab-communication':     lazy(() => import('./CommunicationHubPortal')),  // Direct access
  // IA v4 (FASE IA-2) — Portal Aset kini SATU pintu (`asset-management`); sidebar
  // dihapus karena 4 pintu lama hanyalah tab dari komponen yang sama.
  // Id lama DIPERTAHANKAN sebagai deep-link (bookmark `#asset-list` dsb. tetap
  // mendarat di tab yang benar), tapi TIDAK lagi muncul di menu.
  'asset-management':         makeModuleWithTab(AssetManagementPortalLazy, 'dashboard'),
  'asset-dashboard':          makeModuleWithTab(AssetManagementPortalLazy, 'dashboard'),
  'asset-list':               makeModuleWithTab(AssetManagementPortalLazy, 'assets'),
  'asset-procurement':        makeModuleWithTab(AssetManagementPortalLazy, 'procurement'),
  // ACC-3 — Peminjaman Alat & Aset: relokasi dari Portal Aksesoris (`accessories-loans`)
  // ke domain Aset. Lihat memory/PRODUKSI_E9_AKSESORIS.md §ACC-3 + PRODUKSI_E7_ASET.md §AST-3.
  'asset-loans':              makeModuleWithTab(AssetManagementPortalLazy, 'loans'),

  // ─── Portal Cutting (FASE IA-4) — roll kain ➜ kain pola/potongan ──────────
  'cutting-dashboard': lazy(() => import('./cutting/CuttingDashboard')),
  'cutting-orders':    lazy(() => import('./cutting/CuttingOrdersModule')),
  'cutting-panels':    lazy(() => import('./cutting/CuttingPanelsModule')),
  // Pengaturan notifikasi berkategori (Portal Administrasi Sistem)
  'sys-notif-config':  lazy(() => import('./NotificationSettingsModule')),
  'sys-rbac-audit':    lazy(() => import('./RbacAuditModule')),

  // ─── Portal Aksesoris — MVP (Session #11.21) ──────────────────────────────
  'accessories-dashboard':        AccessoriesDashboard,
  'accessories-master-stock':     makeModuleWithTab(AccessoryModule, 'master'),
  'accessories-opname':           makeModuleWithTab(AccessoryModule, 'opname'),
  'accessories-internal-request': makeModuleWithTab(AccessoryModule, 'internal'),
  'accessories-inbox':            AccessoryRequestInbox,
  'accessories-loans':            makeModuleWithTab(AccessoryModule, 'pinjam'),
  'accessories-purchase':         makeModuleWithTab(AccessoryModule, 'pr'),
  'accessories-reports':          AccessoriesReports,

  // ─── Redirect stubs — backwards compatibility ──────────────────────────
  // P0 FIX: Maklon legacy items moved to Production portal
  // maklon-orders → maklon-po (new PO system)
  'maklon-orders':           makeRedirect('maklon-pos-engine'),
  // maklon-cmt and maklon-packing belong in Production portal (CMT is outsourcing, part of production)
  'maklon-cmt':              makeRedirect('vendor-admin'),        // O1.2 — hindari chain (was → prod-cmt)
  'maklon-packing':          makeRedirect('da-cmt-receive'),      // FASE H-8 — was wms-cmt-dispatches (koleksi kosong)
  // Task 1.1: mgmt-products → prod-models-bom
  'mgmt-products':           makeRedirect('prod-models-bom', 'models'),
  // FASE 5: reservasi per-WO dihapus — arahkan ke Material Issue gudang
  'wh-material-reservation': makeRedirect('wh-material-issue'),
  // Task 1.2: old individual dashboard modules → production-dashboard (with tab hint)
  'prod-oee':                makeRedirect('production-dashboard', 'performance'),
  'prod-line-balance':       makeRedirect('production-dashboard', 'performance'),
  'prod-rework-analytics':   makeRedirect('production-dashboard', 'quality'),
  'prod-aps-gantt':          makeRedirect('production-dashboard', 'schedule'),
  // Task 1.3: old individual model/bom/sizes → prod-models-bom (with tab hint)
  'prod-models':             makeRedirect('prod-models-bom', 'models'),
  'prod-bom':                makeRedirect('prod-models-bom', 'bom'),
  'prod-sizes':              makeRedirect('prod-models-bom', 'sizes'),
};

export const DEFAULT_MODULE = ManagementDashboard;
