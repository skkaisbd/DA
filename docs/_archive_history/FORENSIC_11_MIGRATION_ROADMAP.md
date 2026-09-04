# FORENSIC AUDIT — 11: MIGRATION ROADMAP
## Urutan Eksekusi Refactoring (P0 → P3)

**Lensa:** Strategic Sequencing dengan Risk Management

---

## ROADMAP OVERVIEW

```
Week 1       Week 2       Week 3       Week 4       Week 5-6     Week 7-8
[P0: Quick] [P1: DB-A]   [P1: DB-B]   [P1: Procurement] [P2: Consol] [P3: Arch]
   Wins       Aksesoris    Maklon      P2P Flow         Workflows    Cleanup
```

---

## P0 — QUICK WINS (1-2 hari)

### Goal
Perbaiki bug-bug visible dan UX issues yang quick-win. Zero data risk.

### Tasks

#### Task P0.1: Fix Broken Menus (1 jam)
- [ ] Map `prod-rework-board` ke `BundleReworkBoard` (existing component)
- [ ] Decide untuk `prod-alert-settings`: implement `RahazaAlertSettingsModule` ATAU hapus dari sidebar
- [ ] Map `maklon-cmt` → redirect ke `prod-cmt` (CMTManagementModule) ATAU hapus dari sidebar
- [ ] Map `maklon-packing` → redirect ke `prod-cmt-packing` ATAU hapus dari sidebar

**File affected:** `frontend/src/components/erp/moduleRegistry.js`, `PortalShell.jsx`

#### Task P0.2: Relocate Misplaced Menus (1 jam)
- [ ] Move `cmt-progress` dari Maklon → Production portal
- [ ] Move `marketing-livehost` ke section yang tepat (current: "KOL & Creator", consider: "HR-Sales Hybrid")
- [ ] Verify 6 lainnya yang flagged misplaced di MENU_ANALYSIS_REPORT

**File affected:** `frontend/src/components/erp/PortalShell.jsx`

#### Task P0.3: Hide Legacy Sidebar Labels (30 menit)
- [ ] Hapus label "(Lama)" dari `toko-channels` dan `toko-pricing`
- [ ] Hapus label "(Baru)" / "(Lama)" dari Maklon orders
- [ ] Hide `toko-channels` dan `toko-pricing` dari sidebar (deprecated)

**File affected:** `frontend/src/components/erp/PortalShell.jsx`

#### Task P0.4: Cleanup Backup Files (15 menit)
- [ ] Delete `RahazaHPPModule.jsx.backup`
- [ ] Audit & delete placeholder files (HRDashboardPlaceholder, ProductionDashboardPlaceholder) if confirmed orphan

#### Task P0.5: Remove Duplicate Stock Views (2 jam)
- [ ] Remove `wh-accessory-master` dari sidebar (alias of wh-materials)
- [ ] Remove `wh-accessory-stock` dari sidebar (alias of wh-stock)
- [ ] Add type filter tab di `wh-master` dan `wh-stock`
- [ ] Update sidebar header: "Bahan Baku & Material" jadi single header

**Files affected:**
- `frontend/src/components/erp/PortalShell.jsx`
- `frontend/src/components/erp/RahazaMaterialsModule.jsx`
- `frontend/src/components/erp/RahazaStockModule.jsx`

### P0 Acceptance Criteria
- [ ] Tidak ada menu yang fallback ke ManagementDashboard
- [ ] Tidak ada label "Lama"/"Baru" di sidebar
- [ ] Backup files removed
- [ ] Sidebar item count berkurang 5+
- [ ] All test cases pass (regression)

**Total Effort: ~5 jam**  
**Risk: Low**  
**Need user approval untuk decisions di Task P0.1 (delete vs implement broken menus)**

---

## P1.A — ACCESSORY CONSOLIDATION (3-4 hari)

### Goal
Konsolidasi 4 sistem aksesoris menjadi 1 SSOT.

### Pre-requisites
- [ ] **USER DECISION:** Konfirmasi target schema (rahaza_materials sebagai SSOT) — see FORENSIC_04
- [ ] Backup database
- [ ] Test data scenarios in staging

### Tasks

#### Task P1.A.1: Schema Mapping (4 jam)
- [ ] Map `acc_items` fields → `rahaza_materials` fields
- [ ] Add missing fields ke `rahaza_materials` (procurement-related: vendor_id, lead_time, etc.)
- [ ] Map `acc_stock_movements` → `rahaza_material_movements`
- [ ] Document field migration

#### Task P1.A.2: Migration Script (4 jam)
- [ ] Write Python script `/app/backend/migrations/migrate_accessories.py`
- [ ] Test in dry-run mode
- [ ] Validate counts match

#### Task P1.A.3: Backend Route Update (8 jam)
- [ ] Update `routes/dewi_accessories_full.py`:
  - `/api/acc/items` → query `rahaza_materials` with type=accessory
  - `/api/acc/stock-movements` → query `rahaza_material_movements`
- [ ] Preserve specialized routes:
  - `/api/acc/loans` (specialized)
  - `/api/acc/internal-requests`
  - `/api/acc/purchase-requests`
  - `/api/acc/opname-*` → redirect ke wh_opname2
- [ ] Update all writers (POST endpoints) to write ke rahaza_materials

#### Task P1.A.4: Frontend Update (4 jam)
- [ ] Update `AccessoryModule.jsx` (the wh-accessory-ops module):
  - Items tab → fetch from unified API
  - Stock tab → fetch from unified API
  - Keep specialized tabs: Loans, Internal Requests, Purchase Requests
  - Move Opname tab ke wh-opname module
- [ ] Test end-to-end accessory flow

#### Task P1.A.5: Data Migration + Validation (4 jam)
- [ ] Run migration script in production (with backup)
- [ ] Validate data counts
- [ ] Validate test scenarios pass
- [ ] Delete legacy collections (acc_items, acc_stock_movements, acc_opname_*)

#### Task P1.A.6: Update Sidebar (1 jam)
- [ ] Remove `wh-accessory-master`, `wh-accessory-stock` from sidebar
- [ ] Keep `wh-accessory-ops` (now as specialized accessory operations)
- [ ] Verify Inbox Request still works

### Acceptance Criteria
- [ ] Single source of truth: rahaza_materials
- [ ] Production Material Issue can include accessories from new SSOT
- [ ] Procurement Request flow still works
- [ ] Internal Loan flow still works
- [ ] Reports show consistent data
- [ ] No orphan API endpoints

**Total Effort: ~25 jam | Risk: Medium**

---

## P1.B — MAKLON ORDERS CONSOLIDATION (2 hari)

### Goal
Deprecate `dewi_maklon_orders` (lama), gunakan `dewi_maklon_pos` (baru) sebagai SSOT.

### Tasks

#### Task P1.B.1: Identify Dependencies (2 jam)
- [ ] Grep `dewi_maklon_orders` di seluruh codebase
- [ ] Identify production endpoints yang read dari old collection
- [ ] Map old fields to new fields

#### Task P1.B.2: Data Migration (2 jam)
- [ ] Write migration script
- [ ] Migrate orphan records (yang ada di old, tidak di new)
- [ ] Validate

#### Task P1.B.3: Update Backend (4 jam)
- [ ] Update routes yang read `dewi_maklon_orders` to read `dewi_maklon_pos`
- [ ] Keep `dewi_maklon.py` route file for backward compat (proxy ke new)
- [ ] Plan deprecation timeline

#### Task P1.B.4: Update Frontend (2 jam)
- [ ] Remove `maklon-orders` (lama) from sidebar
- [ ] Update any module that references old DB
- [ ] Test maklon flow end-to-end

#### Task P1.B.5: Verify & Delete (2 jam)
- [ ] Run all tests
- [ ] Verify no writes to `dewi_maklon_orders` for 1 week (monitoring)
- [ ] Delete legacy collection

**Total Effort: ~12 jam | Risk: Medium**

---

## P1.C — PROCURE-TO-PAY COMPLETION (2 hari)

### Goal
Fix broken link: PO → GR (Goods Receipt) flow.

### Tasks

#### Task P1.C.1: Add "Receive against PO" Action (4 jam)
- [ ] Backend: Add endpoint `POST /api/rahaza/grn/from-po/{po_id}`
  - Pre-fills items from PO
  - Creates draft GR
- [ ] Backend: Decide — use `warehouse_receiving` (legacy) atau `wh_*` (new)?
  - **Recommendation:** Migrate ReceivingModule ke wh_* generation
- [ ] Frontend: Add button "Receive against this PO" di PO detail view
- [ ] Frontend: Pre-fill GR form from PO data

#### Task P1.C.2: GR → PO Link (3 jam)
- [ ] Backend: Track `po_id` field in GR
- [ ] Backend: Auto-update PO status (partial/fully received)
- [ ] Frontend: Show "Receive Status" badge di PO list

#### Task P1.C.3: GR QC Integration (3 jam)
- [ ] Verify GR triggers `rahaza_grn_inspections` (already implemented?)
- [ ] Add GR → Invoice cascade hint

#### Task P1.C.4: Test E2E P2P Flow (4 jam)
- [ ] Create PO → Approve → Receive → QC → Invoice → Pay
- [ ] Verify all status updates cascade
- [ ] Verify data consistency

**Total Effort: ~14 jam | Risk: Medium**

---

## P1.D — LEGACY TOKO MIGRATION (2-3 hari)

### Goal
Migrate atau hapus 8 `dewi_toko_*` collections.

### Tasks

#### Task P1.D.1: Audit Each Collection (2 jam)
Untuk setiap dari 8 collections, cek:
- Apakah masih ada writes? (last_updated)
- Apakah masih ada UI yang baca?
- Apakah ada equivalent modern (`marketing_*`)?

#### Task P1.D.2: Migration Plan (2 jam)
```
dewi_toko_channels         → marketing_platform_accounts (migrate data)
dewi_toko_channel_syncs    → marketing_stock_syncs (migrate)
dewi_toko_flashsales       → marketing_discounts (with type=flashsale)
dewi_toko_orders           → marketing_orders (migrate)
dewi_toko_pack_batches     → keep or migrate to fulfillment_*
dewi_toko_products         → marketing_catalog_items (migrate)
dewi_toko_returns          → marketing_returns (migrate)
dewi_toko_reviews          → marketing_reviews (migrate)
```

#### Task P1.D.3: Write Migration Scripts (8 jam)
- [ ] 8 migration scripts (one per collection)
- [ ] Test in dry-run

#### Task P1.D.4: Execute Migration (4 jam)
- [ ] Run migrations with backup
- [ ] Validate counts
- [ ] Update all backend routes
- [ ] Delete legacy collections (after monitoring 1 week)

#### Task P1.D.5: Frontend Cleanup (2 jam)
- [ ] Remove sidebar items `toko-channels`, `toko-pricing` (already done in P0.3)
- [ ] Verify modules still work
- [ ] Remove orphan registry IDs (toko-products, toko-orders, etc.)

**Total Effort: ~18 jam | Risk: Medium**

---

## P2 — WORKFLOW CONSOLIDATION (1-2 minggu)

### Goal
Implementasi 14 konsolidasi dari FORENSIC_09.

### Sequencing (Low-risk first)

#### Week 1
- [ ] **Day 1-2:** Consolidation #3 (Stok/Master tab), #5 (Maklon 360°)
- [ ] **Day 3:** Consolidation #6 (HR Inbox), #9 (Komplain & Return)
- [ ] **Day 4:** Consolidation #10 (Marketing Task Hub), #11 (CMT to Production)
- [ ] **Day 5:** Consolidation #13 (Production Workspace Master), #14 (KPI & Performance)

#### Week 2
- [ ] **Day 1:** Consolidation #7 (Production Control Tower)
- [ ] **Day 2:** Consolidation #8 (Marketing Reports Hub)
- [ ] **Day 3-4:** Consolidation #12 (Shipping flows)
- [ ] **Day 5:** Consolidation #4 (Opname unified)

#### Week 3 (high-risk last)
- [ ] **Day 1-3:** Consolidation #2 (Cutting Planning + Execution merge)

**Total Effort: ~180 jam (~22 working days) | Risk: Mixed**

---

## P2 — GAP_ANALYSIS_REPORT.md ITEMS

Setelah konsolidasi P1+P2, kerjakan fitur original yang masih pending dari `GAP_ANALYSIS_REPORT.md`:

### G1: Communication Hub Enhancements (~16 jam)
- [ ] File attachments support di messages
- [ ] Message edit/delete
- [ ] Read receipts
- [ ] Search in conversations

### G2: Asset Management Completion (~20 jam)
- [ ] Asset Transfer UI (backend exists: `dewi_asset_transfers`)
- [ ] Photo upload untuk assets
- [ ] Asset disposal workflow UI
- [ ] Asset depreciation auto-schedule

### G3: My Workspace Implementation (~24 jam)
- [ ] Spreadsheet-like editor (based on WORKSPACE_DESIGN.md)
- [ ] Sharing & collaboration
- [ ] Version history
- [ ] Templates

### G4: Marketing Seed Data (~4 jam)
- [ ] Add seed data untuk demo:
  - 3 platform accounts (Shopee, Tokopedia, TikTok)
  - Sample sales data 3 bulan
  - Sample KOL creators
  - Sample orders

**Total Effort: ~64 jam | Risk: Low**

---

## P3 — ARCHITECTURE LONG-TERM (1-2 bulan)

### Goal
Mencapai future-state architecture dari FORENSIC_10.

### Tasks

#### P3.1: Notification Unification (8 jam)
- [ ] Design unified `notifications` collection schema
- [ ] Migrate `rahaza_notifications`, `collab_notifications`, `marketing_livehost_notifications` ke unified
- [ ] Update all writers
- [ ] Backward-compat API

#### P3.2: Counters Unification (4 jam)
- [ ] Unified `counters` with namespace field
- [ ] Migrate `dewi_counters`, `rahaza_counters`, `wh_counters`, `rahaza_bundle_counters`
- [ ] Update all sequence generators

#### P3.3: Performance Cleanup (8 jam)
- [ ] Migrate `dewi_perf_*` → `hris_*`
- [ ] Migrate `da_kpi_*` → `hris_kpi_*`
- [ ] Delete legacy

#### P3.4: Asset Cleanup (4 jam)
- [ ] Verify `dewi_assets` vs `da_assets` — consolidate
- [ ] Verify `dewi_asset_assignments` vs `da_asset_assignments`

#### P3.5: KOL Unification (8 jam)
- [ ] Migrate `dewi_kol_*` (3 collections) → `marketing_kol_creators` + `marketing_creator_*`
- [ ] Delete legacy

#### P3.6: Warehouse Gen 1 Cleanup (16 jam)
- [ ] Migrate `warehouse_*` (6 collections) ke `wh_*` atau `rahaza_*`
- [ ] Update ReceivingModule, PutAwayModule, OpnameModule (legacy) untuk pakai new schema
- [ ] Delete legacy

#### P3.7: Search Enhancement (16 jam)
- [ ] Implement record-level global search (not just modules)
- [ ] Add saved searches
- [ ] Add recent items + favorites

#### P3.8: Design System Standardization (24 jam)
- [ ] Deprecate `Modal.jsx` (custom), migrate to Shadcn `Dialog`
- [ ] Deprecate `DataTable.jsx` v1, migrate to V2 (touch ~30 modules)
- [ ] Standardize filter bar component
- [ ] Standardize form layout
- [ ] Storybook setup

#### P3.9: Global Workspace Dashboard (24 jam)
- [ ] Build cross-portal workspace dashboard
- [ ] Cross-context pending approvals inbox
- [ ] Recent items + favorites
- [ ] Role-based widgets

#### P3.10: Naming Convention Phase Out (Long-term, gradual)
- [ ] Document migration map
- [ ] Add aliases for backward compat
- [ ] Gradual migration over 6-12 months

**Total Effort: ~120 jam | Risk: Mixed**

---

## TOTAL ROADMAP EFFORT

| Phase | Effort (hours) | Effort (working days) | Risk |
|-------|---------------|----------------------|------|
| P0 Quick Wins | 5 | 0.5 | Low |
| P1.A Aksesoris | 25 | 3 | Medium |
| P1.B Maklon Orders | 12 | 1.5 | Medium |
| P1.C P2P Flow | 14 | 1.5 | Medium |
| P1.D Toko Migration | 18 | 2 | Medium |
| P2 Consolidations (14) | 180 | 22 | Mixed |
| P2 GAP Items (4) | 64 | 8 | Low |
| P3 Long-term (10) | 120 | 15 | Mixed |
| **TOTAL** | **438 jam** | **~54 working days (~11 weeks)** | **Mixed** |

---

## RISK MITIGATION

### Database Migrations
- **Always:** Backup before migration
- **Always:** Run dry-run first
- **Always:** Validate counts after migration
- **Always:** Keep legacy collections for 1 week post-migration as fallback

### Breaking Changes
- **API Versioning:** Use `/api/v1/*` for new endpoints, keep old for backward compat
- **Frontend:** Use feature flags untuk gradual rollout
- **Tests:** Run regression tests after each change

### User Impact
- **Communication:** Inform users about menu changes 1 week in advance
- **Training:** Update user guide untuk new flows
- **Support:** Have rollback plan ready

---

## SUCCESS METRICS

### Technical
- [ ] Backend route files: 194 → ~150 (-23%)
- [ ] Frontend components: 270 → ~220 (-19%)
- [ ] MongoDB collections: 280 → ~230 (-18%)
- [ ] Sidebar items: 205 → ~140 (-32%)
- [ ] Test coverage: improve to 60%+
- [ ] Code duplication: reduce 30%+

### Business
- [ ] Average time-to-task: 3.6x → 1.5x optimal (-60%)
- [ ] User satisfaction: TBD via survey
- [ ] New employee onboarding: 4 weeks → 2 weeks (-50%)
- [ ] Bug reports: reduce 30%+
- [ ] Maklon flow click depth: 6 modules → 1 view

### Architecture
- [ ] All P2P/O2C/M2S flows functional E2E
- [ ] Single SSOT per business entity (no parallel systems)
- [ ] Clear domain boundaries (8 bounded contexts)
- [ ] Unified notification, counter, audit

---

## NEXT IMMEDIATE STEPS

Setelah Anda review semua 12 deliverables forensik ini:

1. **Approve roadmap** (atau ajukan reprioritization)
2. **Decide critical:**
   - Mana arah konsolidasi aksesoris? (rahaza_materials sebagai SSOT — recommended)
   - Deprecate `dewi_maklon_orders`? (recommended: yes)
   - Hapus 4 broken menus atau implement? (recommended: 2 hapus, 2 fix)
   - Mulai dari P0 langsung?
3. **Saya akan eksekusi** tahap demi tahap dengan **konfirmasi per major step**
4. **Setiap selesai phase**, saya akan **report progress** dan **minta approval untuk next phase**

Audit forensik **SELESAI** — sekarang menunggu keputusan eksekusi dari Anda. 🚀
