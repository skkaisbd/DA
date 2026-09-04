# plan.md — IA Fixes → Cleanup → Cutting Portal → Seed DA Master Data → UI Table & Button Refactor (UPDATED 2026-07-27)

## 1) Objectives
- Restructure IA (menu/section only) for **HR, Finance, Management, Assets, Accessories, Warehouse**; ensure **no broken deep-links** and guardrail `scripts/guardrails/check_nav_map.py` stays green.
- Normalize UX where sidebar menus only switch internal tabs (**Assets portal: remove sidebar; Accessories: single section**).
- Split **Portal Administrasi Sistem** out of Management portal; enforce access **super_admin + admin** (FE `portalAccess.js` + BE `routes/shared.py`).
- Confirm Warehouse **Pengeluaran Material** remains canonical and integrated with Production jobs/BOM.
- Add **Portal Cutting** (simple flow): roll kain (material) → potongan (new material master) with progress + complete, integrated with Warehouse + Production internal.
- Replace old synthetic seeds: **wipe DB** and seed **master data only** from provided Excel (exclude irrelevant sheet `Sheet1`).
- Verify backup/restore still works for new collections (including cutting collections even when empty).
- **Post-seed scale hardening:** ensure inventory APIs don’t silently truncate data with `.to_list(500)` and that UI badges/counts reflect paginated totals.
- **Light-mode UI clarity hardening (tables + buttons):** ensure all dense table pages have clear card surfaces, readable text contrast, and token-consistent button styling (no raw `bg-blue-*` etc).

## 2) Implementation Steps (Phased)

### Phase 1 — Review/Audit Report + Backlog Confirmation (DONE)
**User stories**
1. As an owner, I can see which menus are duplicates/tab-switchers so I can simplify navigation.
2. As an admin, I can see which modules are truly unreachable so we can safely backlog/remove.
3. As a developer, I can see which backend endpoint families have no FE callers to prioritize cleanup.
4. As a QA, I can verify nav wiring has 0 broken ids and guardrails pass.
5. As a stakeholder, I can confirm what from Excel becomes master data vs backlog.

**Steps (implemented)**
- Produced `docs/IA_AUDIT_REPORT.md` summarizing measured findings:
  - 0 broken nav ids; 0 FE→BE wiring breaks.
  - Menu-dupe patterns (AssetManagementPortal / AccessoryModule tab-only menus).
  - Dead code FE + moduleId triage + orphan backend endpoint families.
  - Excel mapping summary (HR, Techpack, CMT, Accessories, Fabric stock, FG stock, Marketing).
- Created `docs/BACKLOG_FROM_EXCEL.md` for data not fully representable without new dev.
- Froze invariants: deep-link safety via `moduleRegistry.js` + `App.js LEGACY_MODULE_TO_PORTAL`.

**Evidence**
- 314 route files; 2.123 endpoints; 297 ERP components; wiring FE↔BE clean.


### Phase 2 — IA v1 Restructure (Front-end only; keep moduleIds stable) (DONE)
**User stories**
1. As an HR user, I can find employee-related tasks under “Manajemen Karyawan” quickly.
2. As an HR admin, I can find org structure/settings under “Manajemen Organisasi”.
3. As an executive, I can access Management portal without system-admin noise.
4. As an asset user, I don’t see redundant sidebar entries that only switch tabs.
5. As an accessories user, I see a single clean section with the small set of features.

**Steps (implemented)**
- Updated `frontend/src/components/erp/portal-shell/portalNav.js`:
  - **HR portal** → 3 required sections (24 pintu utuh):
    1) *Manajemen Karyawan* (8)
    2) *Manajemen Organisasi* (8)
    3) *Analitik & Laporan* (8)
  - **Management portal** removed “Administrasi Sistem” section; now exec-only.
  - **New portal: sysadmin (Administrasi Sistem)** created; access restricted to super roles.
  - **Asset portal:** set `singleDoor: true` and introduced single menu door `asset-management`; PortalShell hides sidebar/pills for singleDoor portals. Legacy asset moduleIds kept for deep-link.
  - **Accessories portal:** collapsed into 1 section (7 pintu).
  - **Finance portal:** redesigned into coherent money-cycle sections (24 pintu utuh).
  - **Warehouse portal:** moved “Pengeluaran Material” into OUTBOUND; annotated integration to Production internal jobs.
- Updated access rules:
  - FE: `frontend/src/components/erp/portalAccess.js`
  - BE: `backend/routes/shared.py` (`PORTAL_ACCESS`)
- Updated portal selector and defaults:
  - `PortalSelector.jsx` now includes `sysadmin`.
  - `App.js` default module mapping updated (assets → `asset-management`, sysadmin → `mgmt-access-hub`).
- Guardrail enhancement:
  - Added **NAV-SOLO** enforcement for `singleDoor: true` portals (1 section × 1 pintu) in `scripts/guardrails/check_nav_map.py`.
- Verified: `python scripts/guardrails/check_nav_map.py` HIJAU.


### Phase 3 — Cleanup (dead code + dead registry entries) without breaking deep-links (DONE)
**User stories**
1. As a user, I don’t hit legacy screens accidentally via menu.
2. As a developer, build size and complexity reduce without removing needed deep-links.
3. As QA, I can still open legacy moduleIds via deep-link if required.
4. As admin, command palette/search remains accurate.
5. As ops, backup/restore remains stable after cleanup.

**Steps (implemented)**
- Removed 14 truly unreferenced FE files (not lazily imported).
- Triaged dead moduleIds:
  - 56 “truly dead” moduleIds → classified into redirects/duplicates vs “feature without door”.
- Fixed a real wiring gap discovered by audit:
  - Enabled menu door **Komponen Kurang** (`cmt-component-requests`) in Maklon portal.
- Documented orphan backend endpoint families as backlog (no removal executed).


### Phase 4 — Portal Cutting (MVP core flow) + Warehouse/Production integration (DONE)
**User stories**
1. As gudang, I can create a Cutting Request selecting roll kain from master material.
2. As gudang, I can record progress (partial output) and see remaining input balance.
3. As gudang, I can complete cutting and automatically create/update “Potongan” as a new material master.
4. As produksi internal, I can use potongan as BOM material and issue it to jobs (Material Issue flow).
5. As finance/audit, stock movements are traceable and consistent with ledger rules.

**Steps (implemented)**
- Backend:
  - Added `backend/routes/cutting.py` (`/api/cutting/*`): orders CRUD, start, progress, complete, cancel, dashboard, input-materials, rolls, output-materials.
  - New collections: `cutting_orders`, `cutting_progress`.
  - Stock movement via SSOT `core/stock_service` (`issue` kain, `add` potongan).
  - Output potongan = new `rahaza_materials` doc (`is_cut_panel`, `type:fabric`, `unit:pcs`, code `CUT-<STYLE>-<WARNA>-<SIZE>`) idempotent.
  - HPP potongan computed at complete and written to `unit_cost`.
  - Added `ensure_cutting_indexes()` invoked at backend startup so cutting collections exist even when empty (backup safety).
- Frontend:
  - Implemented UI modules:
    - `cutting/CuttingDashboard.jsx`
    - `cutting/CuttingOrdersModule.jsx`
    - `cutting/CuttingPanelsModule.jsx`
  - Registered new portal `cutting` in:
    - `portalNav.js`, `moduleRegistry.js`, `PortalSelector.jsx`, `App.js`, `portalAccess.js`
- Proof:
  - `scripts/poc_cutting_flow.py` PASS end-to-end (kain 100→83 kg; potongan 0→112 pcs; HPP computed correctly).


### Phase 5 — Seed Master Data from DA Excel (wipe DB; no transactions) (DONE)
**User stories**
1. As admin, I can reset DB and re-seed only master data safely.
2. As HR, I can see all employees from Excel in the system.
3. As gudang, I can see kain roll master and initial stock.
4. As accessories admin, I can see accessory master + initial stock.
5. As marketing lead, I can see marketplace accounts and PIC/team structure.

**Steps (implemented)**
- Implemented `scripts/seed_da_master_from_excel.py`:
  - Supports `--wipe` (drop all collections + restart backend).
  - Seeds master data only, with **saldo awal stok** written to SSOT ledger (flagged `saldo_awal`) unless `--no-stock`.
  - Ignores Aksesoris `Sheet1` (per owner).
  - Writes login list to `memory/SEED_CREDENTIALS.md` (default password: `Dewi@123`).
- Current seeded totals (after `--wipe`):
  - 25 employees + 25 user logins + 25 payroll profiles + 41 allowances
  - 58 vendor CMT
  - 143 fabric materials (+ saldo awal on subset)
  - 335 accessory materials (+ saldo awal on subset)
  - 553 FG materials (+ saldo awal on subset)
  - 55 models + 55 specs (SPEK PRODUK)
  - 19 techpack styles
  - 8 marketplace accounts + 6 monthly targets


### Phase 6 — Backup/Restore Verification + Full Regression (IN PROGRESS)
**User stories**
1. As ops, I can run backup and see new collections included.
2. As ops, I can restore selected collections to recover from mistakes.
3. As QA, I can run regression after IA and seeding.
4. As admin, I can confirm role-gated Admin System portal works.
5. As owner, I can navigate all portals without missing menus.

**Steps**
- **6a (DONE):**
  - Verified `mongodump`/`mongorestore` present.
  - Verified backup includes `cutting_orders` and `cutting_progress` even when empty (guaranteed by `ensure_cutting_indexes`).
- **6b (NEXT):**
  - Run end-to-end regression via `testing_agent_v3` across:
    - Portal selection incl. sysadmin/cutting
    - HR list shows 25 employees
    - Warehouse master shows full counts (no 500-cap truncation)
    - Cutting: create draft → start → progress → complete → potongan appears in Gudang materials
    - Backup UI flow + restore subset smoke
- **6c (NEXT):**
  - Fix all issues found by testing agent; re-run guardrails + targeted regressions.


### Phase 7 — Global UI Table & Button Refactor (light mode) (DONE; regression pending)
**User stories**
1. As a user in light mode, I can read dense tables clearly because the table is always on a solid card surface with visible boundaries.
2. As a user, I can trust that buttons use consistent brand tokens (no raw `bg-blue-*`) and text contrast is safe.
3. As an owner, I can get uniform table readability improvements across many modules without refactor one-by-one.

**Steps (implemented)**
1. **New UI primitives:**
   - Created `frontend/src/components/ui/data-card.jsx`:
     - `DataCard`, `DataCardHeader`, `DataTableShell`, `StatCard`, `EmptyRow`
     - All components use design tokens: `--card-surface`, `--glass-border`, `--shadow-card`, `hsl(var(--primary))`, `--radius-*`.
2. **Global baseline CSS (light-mode only):**
   - Added baseline CSS in `frontend/src/index.css` (outside `@layer` for precedence) with **9 blocks**:
     - Auto card surface for any wrapper that directly contains `> table` (solid white + hairline + radius + shadow) + anti double-border rules.
     - Table content styling: tinted header, row separators, zebra rows, hover, `tfoot`, sticky header guard.
     - Text readability: compress low-opacity utilities (`text-foreground/30..70`, `text-muted-foreground/30..70`) to `--muted-foreground`.
     - Buttons: map raw color buttons (blue/indigo/sky/violet/purple 500–800) to token `--primary` and `--primary-foreground`; semantic buttons forced to white text.
     - Fix bug: `text-foreground` on saturated backgrounds forced to white.
     - Pastel KPI blocks receive hairline + shadow.
     - `bg-foreground/5` and `/10` strengthened for separation.
     - Dark-mode idioms leaking into light: `bg-black/5..30` (non-overlay), `bg-white/5..10`, and `divide-white/*` corrected.
     - Pale text shades (200/300/400) across **22 color families** remapped to readable darker shades.
3. **Idempotent CSS generator:**
   - Added `scripts/gen_light_button_css.py`:
     - Regenerates the light-mode button mapping block using exact token match (`class~=`) so `hover:bg-blue-50` does **not** get hit.
     - Also generates the pale-text remap block.
4. **Targeted codemod for table wrappers:**
   - Added `scripts/codemod_table_wrappers.py`:
     - Updated **37** table-wrapper spots in **24** files from `bg-foreground/5`/`border-foreground/10` patterns → `bg-[var(--card-surface)] border-[var(--glass-border)] shadow-[var(--shadow-card)]`.
5. **Example module cleanup:**
   - `HRShiftManagementModule.jsx` KPI cards migrated to `StatCard`.

**Verification (completed)**
- Rebuilt static bundle multiple times; build OK.
- Captured screenshots across dense table/card pages:
  - HR: Data Karyawan, Shift Management
  - Warehouse: Master Item, Roll Kain
  - Finance: Dashboard, Rekap Keuangan, AR 360
  - Production: Production Jobs, Vendor CMT
  - Cutting: Order Cutting
  - Accessories: Master Stok, Request Internal
  - Marketing: Kelola Akun
  - Assets: Manajemen Aset
  - Maklon: Data Klien
  - Sysadmin: Kontrol Akses
- Dark + Classic mode smoke checked: no regression (all new rules scoped to `html.light`).
- `python scripts/guardrails/check_nav_map.py` remains **HIJAU** (0 pelanggaran).

**Remaining**
- Full regression via `testing_agent_v3` (mandatory), and fix any findings.


## 3) Next Actions (immediate)
1. Run `testing_agent_v3` full regression and capture results to `test_reports/`.
2. Address any failures; ensure `check_nav_map.py` stays HIJAU.
3. Confirm backlog decisions with owner:
   - Sheet `Memo` fabric-roll details mapping to `wh_fabric_rolls` (needs linking fabric name/color → roll).
   - Convert `SPEK PRODUK` (55 SKU) into official `rahaza_boms` (needs mapping accessory free-text → master codes + size).
   - Marketing transactional sheets remain intentionally not imported.

## 4) Success Criteria
- Guardrail `check_nav_map.py` passes; 0 broken menu ids; deep-links still resolve.
- HR IA matches 3 required sections; Finance and Management IA simplified; Admin System split and role-gated.
- Assets portal no longer shows redundant sidebar navigation; Accessories portal is 1 section.
- Warehouse “Pengeluaran Material” documented and demonstrably linked to Production internal jobs.
- Cutting MVP works end-to-end: input roll/material → progress → complete → potongan material exists, stock ledger entries correct, and potongan usable in downstream flows.
- DB can be wiped and re-seeded from Excel to master data only; no missing master entities (karyawan, produk/model, kain, aksesoris, FG, CMT/vendor, akun marketing).
- Backup/restore includes cutting collections and completes without errors.
- Inventory APIs and UI counts work at real data scale (no silent truncation at 500 rows; badges show correct totals).
- **Light mode UI:**
  - Dense table pages consistently show a visible card surface (white) with clear borders and readable row separation.
  - Buttons avoid raw Tailwind saturated colors; use `--primary`/`--primary-foreground` and safe contrast.
  - Dark/classic modes are not regressed by light-only overrides.
  - `testing_agent_v3` regression passes for representative modules.
