# FORENSIC AUDIT — 12: CURRENT STATE AUDIT
## Code Forensic: Before vs After Optimization + Gap Analysis
**Tanggal Audit:** 26 Mei 2026  
**Auditor:** Agent Session #12 (E2 model)  
**Referensi:** FORENSIC_00 → FORENSIC_11 (baseline), Session #11.18 EXTENDED Part 2 (last completed)

---

## 🎯 EXECUTIVE SUMMARY

| Dimensi | Baseline (awal FORENSIC) | Sebelum Session #11 | Sesudah #11.18 EP2 | Gap Tersisa |
|---------|------------------------|---------------------|---------------------|-------------|
| Backend ruff errors | ~2000+ | 2008 | **0** (production routes) | 2 (test file) |
| Frontend ESLint warnings | 140+ | 140 | **0** | 0 |
| Jest tests | 0 | 91 | **204** | Low coverage (3.3%) |
| Main bundle (gzip) | ~600 KB | 453 KB | **~222 KB** | Beberapa modul besar belum lazy |
| P1 Monster files (FE) | 6 monsters | 6 | **0 aktif** (semua refactored) | 15 FE >1000 LOC belum di-test |
| P1 Monster files (BE) | dewi_asset_mgmt + ... | resolved | **15 route >1000 LOC** | NEW gaps ditemukan |
| Collections | 175+ | 175 | **164** (-11) | 154 dari 164 MASIH KOSONG |
| Tech debt P2 | 14 tasks | 14 | **14/14 DONE** | 0 |
| Tech debt P3 | 5 tasks | 5 | **5/5 DONE** | 0 |

---

## 🔴 GAP KRITIS (Critical — HARUS DISELESAIKAN)

### GAP-01: Backend Routes Masih Membaca ke DROPPED Collections

**Severity:** 🔴 CRITICAL  
**Akar masalah:** Phase A/B/C/D berhasil **drop collection** dan **delete router files** — tapi TIDAK semua route yang consume collections ini diupdate.

#### Bukti:

| Collection (DROPPED) | Route yang Masih Baca/Tulis | Baris |
|---------------------|---------------------------|-------|
| `warehouse_stock` | `warehouse.py:159,332,357` | 18 refs |
| `warehouse_movements` | `warehouse.py:373,485`, `dewi_ai_business.py:311` | 12 refs |
| `warehouse_locations` | `warehouse.py:98,112`, `dewi_maklon.py:569` | 15 refs |
| `warehouse_opname` | `warehouse.py:639,685,695` | 6 refs |
| `accessories` | `operations.py:76,77,79` | 9 refs |
| `accessory_requests` | `operations.py:353,354,356` | 11 refs |
| `invoices` | `dashboard_routes.py:111`, `operations.py:982,1370,1708,2117` | 8 refs |
| `dewi_kol_creators` | `dewi_demo_seed.py:603,631,636` | 4 refs |
| `dewi_kol_deals` | `dewi_demo_seed.py:635,641,658` | 4 refs |
| `dewi_kol_samples` | `dewi_demo_seed.py:662,668,690` | 3 refs |

**Impact saat ini:**
- `warehouse.py` → endpoint seperti `/api/warehouse/locations`, `/api/warehouse/movements` RETURN EMPTY (collection kosong) bukan error, tapi data silent-missing
- `operations.py` → `/api/accessories/*`, `/api/accessory-requests/*` return empty list dari empty collection (bukan dari SSOT `rahaza_materials`)
- `dashboard_routes.py` → Dashboard finance mungkin menampilkan 0 invoice padahal SSOT `rahaza_ar_invoices` + `rahaza_ap_invoices` punya data
- `dewi_demo_seed.py` → Jika seed dijalankan, akan **re-create** dropped collections (defeating Phase C cleanup)

**Rekomendasi:**
```
PRIORITY 1: Fix dashboard_routes.py → point ke rahaza_ar_invoices + rahaza_ap_invoices
PRIORITY 2: Fix operations.py reads invoices → point ke SSOT atau remove
PRIORITY 3: Fix dewi_demo_seed.py → hapus/comment seed untuk dropped collections
PRIORITY 4: warehouse.py & dewi_maklon.py → audit apakah wms_* sudah cover use cases ini
```

---

### GAP-02: Frontend Masih Memanggil Deprecated Endpoints

**Severity:** 🔴 CRITICAL  
**Akar masalah:** Backend endpoint `/api/wms/opname/*` sudah di-deprecate (SSOT adalah `/api/wms/opname2/*`) tapi `WMSModule.jsx` belum diupdate.

#### Bukti:

| Frontend File | Deprecated Endpoint | SSOT Endpoint |
|--------------|--------------------|--------------------|
| `WMSModule.jsx:1003` | `/api/wms/opname?limit=30` | `/api/wms/opname2?...` |
| `WMSModule.jsx:1025` | `/api/wms/opname/start` | `/api/wms/opname2/start` |
| `WMSModule.jsx:1040` | `/api/wms/opname/${id}` | `/api/wms/opname2/${id}` |
| `WMSModule.jsx:1057` | `/api/wms/opname/${id}/scan` | `/api/wms/opname2/${id}/scan` |
| `WMSModule.jsx:1075` | `/api/wms/opname/${id}/complete` | `/api/wms/opname2/${id}/complete` |
| `WMSModule.jsx:1090` | `/api/wms/opname/${id}/cancel` | `/api/wms/opname2/${id}/cancel` |
| `WMSPickListModule.jsx:243` | `/api/rahaza/shipments` | `/api/wms/delivery-notes` |
| `RahazaARInvoicesModule.jsx:345` | `/api/rahaza/shipments/customer-statement/...` | tbd |

**Catatan:** `WMSOpnameEnhancedModule.jsx` sudah BENAR menggunakan `/api/wms/opname2/*` — inconsistency antar modul.

**Rekomendasi:**
```
Update WMSModule.jsx: ganti semua /api/wms/opname → /api/wms/opname2
Update WMSPickListModule.jsx: /api/rahaza/shipments → /api/wms/delivery-notes
Selesaikan RahazaARInvoicesModule.jsx customer-statement endpoint
```

---

## 🟠 GAP TINGGI (High — Perlu Diselesaikan Segera)

### GAP-03: Backend Monster Files — NEW DISCOVERY

**Severity:** 🟠 HIGH  
**Akar masalah:** Audit FORENSIC awal (P1) fokus pada 6 monster FRONTEND. Backend monster files baru terdefinisi dengan threshold >800 LOC tapi belum semua direfaktor.

| File | LOC | Status | Priority |
|------|-----|--------|----------|
| `routes/dewi_kpi.py` | **2726** | ❌ NOT in P1 list — NEW DISCOVERY | HIGH |
| `routes/operations.py` | **2580** | ⚠️ Has DEPRECATION log, tapi masih hidup | HIGH |
| `routes/marketing_livehost.py` | **2278** | ⚠️ Frontend refactored tapi BACKEND TIDAK | MEDIUM-HIGH |
| `routes/marketing.py` | **1757** | ❌ Not refactored | MEDIUM |
| `routes/rahaza_payroll.py` | **1539** | ❌ Not refactored | MEDIUM |
| `routes/dewi_rnd.py` | **1532** | ❌ Not refactored | MEDIUM |
| `routes/rahaza_admin.py` | **1343** | ❌ Not refactored | MEDIUM |
| `routes/rahaza_inventory.py` | **1307** | ❌ Not refactored | MEDIUM |
| `routes/marketing_kol.py` | **1298** | ❌ Not refactored | MEDIUM |
| `routes/production.py` | **1204** | ❌ (FORENSIC_08 flagged as orphan) | MEDIUM |
| `routes/marketing_catalog.py` | **1204** | ❌ Not refactored | MEDIUM |
| `routes/dewi_accessories_full.py` | **1199** | ⚠️ Has DEPRECATION log | MEDIUM |
| `backend/server.py` | **1589** | ⚠️ Orchestrator, expected large | LOW |
| `utils/scheduler.py` | **978** | ❌ Utils, tidak perlu refaktor tapi besar | LOW |

**Catatan penting:** Sesuai `AGENT_DEVELOPMENT_RULES.md` rule #4: **"No monster files (>500 lines React, >800 Python)"**. Ada 15 backend route files yang MELANGGAR aturan ini.

### GAP-04: 18 Legacy Test/Seed Files di Root Backend

**Severity:** 🟠 HIGH (code organization)  
File-file ini mencemari direktori production dan memperlambat ruff scan:

```
/app/backend/backend_test.py                    ← legacy test
/app/backend/backend_test_acc_opname_ssot.py    ← legacy test
/app/backend/backend_test_asset_refactor.py     ← legacy test
/app/backend/backend_test_hr_inbox.py           ← legacy test
/app/backend/backend_test_livehost.py           ← legacy test
/app/backend/backend_test_p2p_flow.py           ← legacy test  
/app/backend/backend_test_phase_c.py            ← legacy test
/app/backend/backend_test_td011_phase1.py       ← legacy test
/app/backend/backend_test_toko_migration.py     ← legacy test
/app/backend/comm_hub_test.py                   ← legacy test
/app/backend/create_test_order.py               ← utility script (2 ruff errors)
/app/backend/session_11_17_regression_test.py   ← legacy test
/app/backend/session_11_18_extended_part2_test.py ← legacy test
/app/backend/session_11_18_regression_test.py   ← legacy test
/app/backend/toko_consolidation_test.py         ← legacy test
/app/backend/seed_lms_courses.py               ← seed script
/app/backend/seed_lms_quiz_questions.py        ← seed script
/app/backend/cascade_delete.py                 ← utility
```

**Rekomendasi:** Pindahkan ke `/app/backend/tests/legacy/` atau hapus yang tidak relevan.

### GAP-05: Dead Code Frontend — V1 dan Orphan Components

**Severity:** 🟠 MEDIUM-HIGH  

| File | Status | Action |
|------|--------|--------|
| `RahazaBOMModule.jsx` (v1) | Di-registry sebagai `prod-bom` — TAPI `RahazaBOMModuleV2` juga ada | Verify mana yang aktif, hapus v1 jika sudah replaced |
| `TokoDashboard.jsx` | Di-registry, status "classic" | Verify vs `TokoDashboardModule.jsx` |
| `TokoProductCatalogModule.jsx` | Di-registry, FORENSIC_08 flagged | Verify vs `CatalogManagementModule.jsx` |
| `BuyersModule.jsx` | `mgmt-customers` di sidebar, 1 ref di registry | Verify vs `RahazaCustomersModule.jsx` |
| `SelfServicePortal.jsx` | 1 ref di registry | Verify vs `PortalSayaDashboard` |

---

## 🟡 GAP MEDIUM (Medium — Perlu Dijadwalkan)

### GAP-06: Frontend Test Coverage Sangat Rendah

**Severity:** 🟡 MEDIUM  

| Metric | Nilai | Target |
|--------|-------|--------|
| Test files | 15 | 30+ |
| Components covered | ~16/458 | 50+ |
| Coverage ratio | 3.3% | 15%+ |

**Modul kritis tanpa test (semua >1000 LOC):**
- `HRKPIModule.jsx` (1948 LOC) — HRIS core
- `WMSModule.jsx` (1762 LOC) — Warehouse core
- `CatalogManagementModule.jsx` (1345 LOC) — Marketing core
- `AccessoryModule.jsx` (1138 LOC) — Production core
- `APSGanttModule.jsx` (1092 LOC) — Planning core
- `Phase7ReportingModule.jsx` (1086 LOC) — Reporting core
- `MaklonPOModule.jsx` (1060 LOC) — Maklon core
- `RahazaBOMModuleV2.jsx` (1025 LOC) — BOM core
- `WorkspaceHub.jsx` (1004 LOC) — Collaboration core

### GAP-07: EMERGENT_LLM_KEY Tidak Dikonfigurasi

**Severity:** 🟡 MEDIUM  
107 referensi ke `EMERGENT_LLM_KEY` di backend routes, tapi key tidak ada di `.env`.  
Semua fitur AI (WMS AI Insights, Dewi AI Business, Marketing AI, dsb.) akan return **503 Service Unavailable**.

**Affected endpoints:** `/api/wms/ai/*`, `/api/dewi/ai-business/*`, `/api/marketing/ads/*`, `/api/dewi/predictive-maintenance/*`, dll.

---

## 🟢 GAP RENDAH (Low — Cosmetic/Nice to Have)

### GAP-08: Frontend Large Components Tanpa Lazy Loading (via moduleRegistry)

**Status:** SEBENARNYA SUDAH HANDLED  
Semua 233 komponen di moduleRegistry sudah `lazy()` — termasuk modul >1000 LOC. Verifikasi: `grep -c "const.*= lazy" /app/frontend/src/components/erp/moduleRegistry.js` → 233. ✅

**Bundle main (gzip) = ~222 KB — MATCHES SESSION #11.18 claim.** Raw size 705 KB adalah angka uncompressed.

### GAP-09: 2 Ruff Errors di create_test_order.py

```
F401: `os` imported but unused
F841: `result` assigned but never used
```

Minor — file ini utility/test script, bukan production route.

### GAP-10: wh_opname_sessions2 vs wh_opname_sessions Naming

Satu collection menggunakan suffix `2` — nama yang tidak ideal tapi berfungsi.

---

## 📊 BEFORE vs AFTER COMPARISON TABLE

### Backend Code Quality

| Metric | Sebelum FORENSIC | Sebelum #11 | Sesudah #11.18 EP2 | Gap Tersisa |
|--------|-----------------|-------------|---------------------|-------------|
| Ruff errors (prod) | ~2000+ | 2008 | **0** | 2 (test file) |
| Bare except | 50+ | ~10 | **0** | 0 |
| Unused imports | 100+ | ~30 | **0** | 0 |
| F-strings w/o placeholder | 200+ | ~93 | **0** | 0 |
| Monster route files (>1000 LOC) | 20+ | ~15 | **15** | NOT YET FIXED |
| Deprecated collection reads | N/A | ~50 | **71** | GAP-01 active |
| Test files in /root | N/A | 18 | **18** | GAP-04 |

### Frontend Code Quality

| Metric | Sebelum FORENSIC | Sebelum #11 | Sesudah #11.18 EP2 | Gap Tersisa |
|--------|-----------------|-------------|---------------------|-------------|
| ESLint warnings | 140+ | 140 | **0** | 0 |
| Monster components (>1000 LOC) | 20+ | 6 P1 | **15 untested** | GAP-06 |
| Jest tests | 0 | 91 | **204** | Low coverage |
| Lazy loaded modules | 0 | 0 | **233/260** | 27 unregistered |
| Main bundle (gzip) | ~600 KB | ~453 KB | **~222 KB** | Optimal |
| Dead code files (v1/orphan) | 30+ | ~10 | **~6** | GAP-05 |
| Deprecated endpoint calls | N/A | ~20 | **8** | GAP-02 |

### Data Architecture

| Metric | Sebelum FORENSIC | Sebelum #11 | Sesudah #11.18 EP2 | Gap Tersisa |
|--------|-----------------|-------------|---------------------|-------------|
| Total collections | 200+ | 175 | **164** | 154 kosong |
| Empty collections | 100+ | 175 | **154/164** | Banyak empty |
| Deprecated collections dropped | 0 | 0 | **11** (Phase A+B+C) | ~10 lagi bisa di-drop |
| Routes writing to dropped collections | N/A | N/A | **9 collections** | GAP-01 |
| SSOT coverage | Low | Medium | **High** | Gap-01 undermines |

---

## 🗺️ ROADMAP PRIORITAS

### 🔴 P0 (IMMEDIATE — Fix sebelum prod use)
1. **GAP-01**: Fix `dashboard_routes.py` dan `operations.py` reads ke `invoices` → SSOT
2. **GAP-01**: Fix `dewi_demo_seed.py` seed ke dropped collections
3. **GAP-02**: Update `WMSModule.jsx` dari `/api/wms/opname` → `/api/wms/opname2`

### 🟠 P1 (THIS SESSION — 2-4 jam)
4. **GAP-04**: Pindahkan 18 test files ke `tests/legacy/` (housekeeping)
5. **GAP-01**: Audit `warehouse.py` reads/writes ke dropped warehouse collections → apakah ada WMS alternative?
6. **GAP-05**: Verifikasi dan hapus `RahazaBOMModule.jsx` v1 jika sudah replaced

### 🟡 P2 (NEXT SESSION)
7. **GAP-03**: Refaktor `dewi_kpi.py` (2726 LOC) — NEW monster discovery
8. **GAP-03**: Refaktor `operations.py` (2580 LOC) — confirmed dead, partial deprecation
9. **GAP-06**: Expand Jest coverage: WMSModule, HRKPIModule, APSGanttModule

### 🟢 P3 (OPTIONAL)
10. **GAP-07**: Konfigurasi EMERGENT_LLM_KEY untuk AI features
11. **GAP-09**: Fix 2 ruff errors di create_test_order.py
12. **GAP-10**: Rename `wh_opname_sessions2` → `wh_opname_sessions`

---

## ✅ VERIFIED WORKING (No Gaps)

- ✅ `/api/health` → `{status:ok, db:connected}`
- ✅ Auth (JWT, login admin@garment.com/Admin@123)
- ✅ Frontend builds tanpa warning/error
- ✅ Jest 204/204 passing (15 test suites)
- ✅ Main bundle ~222 KB gzipped (51% reduction dari 453 KB)
- ✅ All P1 frontend monsters refactored
- ✅ All P2 workflow consolidations done (14/14)
- ✅ All P3 data architecture tasks done (5/5)
- ✅ All UI/UX tech debt cleared (TD-013/014/015/016)
- ✅ Backend ruff 0 errors (production routes)
- ✅ Frontend ESLint 0 warnings
- ✅ 11 collections properly dropped (Phase A+B+C)
- ✅ 233/260 module registry entries lazy-loaded
- ✅ 7 deprecated backend routes with clear DEPRECATION logs
- ✅ SSOT untuk: Accessory, Maklon, Toko, KOL, Finance, Notifications, Counters, Opname, Shipping

---

## ✅ P1 + P2 FIX LOG (Session #12)

| Fix | File(s) | Status |
|-----|---------|--------|
| **P1-1** Housekeeping: 19 legacy files → tests/legacy/ | backend root | ✅ DONE |
| **P1-1b** cascade_delete.py → utils/ + import updated | master_data.py, production_po.py | ✅ DONE |
| **P1-2** RahazaBOMModule.jsx v1 import removed | moduleRegistry.js | ✅ DONE |
| **P1-3** warehouse.py confirmed dead; dewi_ai_business + maklon location SSOT | 3 files | ✅ DONE |
| **P2-1** dewi_kpi.py (2726 LOC) → 7 files (max 550 LOC) | 7 new files | ✅ DONE |
| **P2-2** operations.py (2580 LOC) → 4 files + deprecated 380 LOC DELETED | 4 new files | ✅ DONE |
| Testing P1: 18/18 ✅ P2: 14/14 ✅ | iteration_64, iteration_65 | ✅ 100% |

*P0 fixes: 26 Mei 2026 — Session #12*
*P1 fixes: 26 Mei 2026 — Session #12*
*P2 fixes: 26 Mei 2026 — Session #12*
