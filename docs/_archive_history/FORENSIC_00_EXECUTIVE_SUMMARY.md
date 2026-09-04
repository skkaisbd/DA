# FORENSIC AUDIT — EXECUTIVE SUMMARY
## CV. Dewi Aditya ERP System

**Tanggal Audit:** 22 Mei 2026  
**Auditor:** Neo (AI Full-Stack Engineer)  
**Tipe Audit:** 12-Lens Forensic Analysis (Business Process + UX + Architecture)  
**Status Sistem:** ⚠️ HEAVY TECHNICAL DEBT — Memerlukan konsolidasi besar  

---

## 🔥 TOP-LEVEL FINDINGS

### Skala Sistem (Inventarisasi Penuh)

| Aset | Jumlah | Status |
|------|--------|--------|
| Backend Route Files | **194 files** | 🔴 Terlalu fragmentasi |
| Frontend Components (ERP) | **270 components** | 🔴 Banyak duplikasi |
| MongoDB Collections | **280+ collections** | 🔴 Multiple sources of truth |
| Sidebar Portals | **11 portals** | 🟡 Beberapa portal redundan |
| Sidebar Menu Items | **~180 items** | 🔴 Cognitive load tinggi |
| Broken Menus (no registry) | **4 items** | 🔴 Critical bug |
| Section Mismatches | **8+ items** | 🟡 IA issue |

### Status Kesehatan Per Dimensi

| Dimensi Audit | Skor | Status |
|---------------|------|--------|
| **L1 Information Architecture** | 4/10 | 🔴 Sidebar terlalu padat, naming tidak konsisten |
| **L2 Business Process Engineering** | 3/10 | 🔴 Banyak duplicate workflow (Cutting, Accessories, KOL) |
| **L3 UX Systems Engineering** | 4/10 | 🔴 Click depth tinggi, form complexity tinggi |
| **L4 Operational Efficiency** | 5/10 | 🟡 Repetitive input di banyak modul |
| **L5 Human-Centered System** | 4/10 | 🔴 Mental model tidak konsisten (per-developer naming) |
| **L6 Workflow Consolidation** | 3/10 | 🔴 Banyak modul satu-flow tapi terpisah |
| **L7 Domain-Driven Design** | 4/10 | 🔴 Boundary domain tidak jelas (Rahaza vs Dewi prefix) |
| **L8 Data Architecture** | 2/10 | 🔴 SSOT issues serius (Materials, Accessories, Orders) |
| **L9 Cross-Module Dependencies** | 4/10 | 🔴 Dead code, orphan modules, legacy flows |
| **L10 Design System** | 6/10 | 🟡 Komponen pattern relatif konsisten (shadcn) |
| **L11 Naming Consistency** | 3/10 | 🔴 Mix Indonesian/English/Prefix (rahaza/dewi/wms/wh) |
| **L12 Interaction Pattern** | 6/10 | 🟡 CRUD pattern OK, tapi search/filter beragam |

**Overall System Health: 4.0/10** — Membutuhkan refactoring besar untuk mencapai enterprise-grade.

---

## 🚨 TOP 10 CRITICAL FINDINGS

### 🔴 #1 — Database Multi-SSOT untuk Aksesoris (CRITICAL)
**Problem:** 4 sistem paralel mengelola data aksesoris yang sama  
**Impact:** Data sync failure, stock report inkonsisten  
**Decision:** **MERGE** ke `rahaza_materials` (with type=accessory) + buat alias view  
**Effort:** ~16 jam | **Risk:** Medium (data migration)

### 🔴 #2 — Database Duplikat untuk Maklon Orders
**Problem:** `dewi_maklon_orders` (lama) vs `dewi_maklon_pos` (baru)  
**Impact:** Reporting Maklon terfragmentasi  
**Decision:** **MIGRATE** `dewi_maklon_orders` → `dewi_maklon_pos`, deprecate yang lama  
**Effort:** ~12 jam | **Risk:** Medium

### 🔴 #3 — 4 Menu Sidebar Broken (TIDAK PUNYA KOMPONEN)
**Items:** `maklon-cmt`, `maklon-packing`, `prod-rework-board`, `prod-alert-settings`  
**Decision:** Re-map ke komponen yang ada ATAU hapus dari sidebar  
**Effort:** ~1 jam | **Risk:** Low

### 🔴 #4 — Dua Sistem Cutting Tidak Terhubung
**Problem:** `prod-cutting` (planning, `dewi_cutting_*`) vs `prod-exec-cutting` (execution, `rahaza_process_execution`)  
**Impact:** Data planning tidak sinkron dengan execution  
**Decision:** **MERGE** menjadi 1 modul dengan 2 tab (Planning + Execution)  
**Effort:** ~24 jam | **Risk:** High (banyak dependency)

### 🔴 #5 — 3 Sistem Warehouse Paralel
**Problem:** `warehouse_*` (oldest) vs `rahaza_*` (production-tied) vs `wh_*` (newest WMS)  
**Impact:** Data inventory tidak konsisten antar modul  
**Decision:** **CONSOLIDATE** ke `wh_*` (newest, ~16 collections), migrate yang lain  
**Effort:** ~32 jam | **Risk:** High

### 🔴 #6 — Legacy Toko Data (`dewi_toko_*`) Masih Tergantung
**Problem:** 8 collections `dewi_toko_*` masih dipakai parsial padahal sudah ada Marketing
**Decision:** **AUDIT each collection**: yang dipakai → migrate ke marketing_*; yang orphan → delete
**Effort:** ~16 jam | **Risk:** Medium

### 🔴 #7 — Sidebar Cognitive Overload (180 items)
**Problem:** User harus scroll panjang, naming inkonsisten, banyak "BARU" badge  
**Decision:** **CONSOLIDATE** menjadi ~110 items dengan tab/sub-tab grouping  
**Effort:** ~24 jam | **Risk:** Low (hanya UI)

### 🟠 #8 — Section Misplacement (8 items)
**Problem:** Item ada di section yang salah secara bisnis  
**Examples:** `marketing-livehost` di "KOL" padahal HR-related; `cmt-progress` di Maklon padahal Production  
**Decision:** **RELOCATE** sesuai business mental model  
**Effort:** ~2 jam | **Risk:** Low

### 🟠 #9 — Multiple KOL/Creator Systems
**Problem:** `dewi_kol_*` (old) + `marketing_kol_*` + `marketing_creator_*` + `toko-kol` modules
**Decision:** **CONSOLIDATE** ke `marketing_kol_creators` + `marketing_creator_*` cluster  
**Effort:** ~16 jam | **Risk:** Medium

### 🟠 #10 — Naming Convention Chaos
**Problem:** Mix prefix `rahaza_` (production), `dewi_` (newer), `wms_` (warehouse), `wh_` (newest), `marketing_` (newest marketing), plus generic (`users`, `invoices`)
**Decision:** **DOCUMENT** namespace convention; phase out `rahaza_` & `dewi_` over time  
**Effort:** Long-term (gradual) | **Risk:** Low

---

## 📊 BUSINESS PROCESS HEALTH MAP

| Business Process | Status | Issues |
|------------------|--------|--------|
| **Procure-to-Pay (P2P)** | 🟡 PARTIAL | PO → GR link broken (no GR-from-PO implementation) |
| **Order-to-Cash (O2C)** | 🟢 OK | Working end-to-end (Order → WO → Production → Shipment → Invoice) |
| **Make-to-Stock (M2S)** | 🟢 OK | Functional via Production Wizard |
| **Maklon Flow (B2B Order)** | 🔴 BROKEN | 2 DB schemas in parallel, no unified workflow |
| **CMT Outsourcing** | 🟡 PARTIAL | Component requests work, but progress reporting fragmented |
| **Hire-to-Retire (H2R)** | 🟢 OK | Comprehensive (recruitment, onboarding, attendance, payroll, exit) |
| **Asset Lifecycle** | 🟡 PARTIAL | Acquisition + assignment work; transfer/disposal missing UI |
| **Marketing Performance** | 🟢 OK | Multi-channel sales tracking working |
| **Inventory (3 systems)** | 🔴 FRAGMENTED | Multiple SSOT issue |
| **Accessory Management** | 🔴 FRAGMENTED | 4 systems parallel |

---

## 🎯 STRATEGIC RECOMMENDATIONS

### IMMEDIATE (P0 - 1-2 hari)
1. Fix 4 broken sidebar menus (re-map atau hapus)
2. Relocate 8 menu items ke section yang benar
3. Hapus duplicate stock view (`wh-accessory-stock` → tab dalam `wh-stock`)

### SHORT-TERM (P1 - 1 minggu)
4. Konsolidasi accessories: `acc_items` → `rahaza_materials` (atau sebaliknya)
5. Deprecate `dewi_maklon_orders`, gunakan `dewi_maklon_pos` saja
6. Audit & cleanup `dewi_toko_*` legacy collections
7. Implementasi "Create GR from PO" flow

### MEDIUM-TERM (P2 - 2-3 minggu)
8. Merge Cutting Planning + Execution menjadi 1 modul bertab
9. Konsolidasi 3 warehouse systems → 1 (`wh_*` sebagai primary)
10. Implementasi GAP_ANALYSIS_REPORT.md items (Comm Hub, Asset Transfer, Workspace)

### LONG-TERM (P3 - 1-2 bulan)
11. Refactor namespace: phase out `rahaza_*` → `prod_*` & `hr_*`
12. Implement Domain-Driven Design dengan bounded contexts yang jelas
13. Build shared kernel untuk: Master Data, Notifications, Audit Log
14. Standardize search/filter patterns across all modules

---

## 💰 EFFORT & ROI ESTIMATE

| Phase | Duration | Effort (hr) | Items | ROI |
|-------|----------|-------------|-------|-----|
| P0 — Quick Wins | 1-2 hari | ~10 jam | 3 items | ⭐⭐⭐⭐⭐ |
| P1 — DB Consolidation | 1 minggu | ~50 jam | 4 items | ⭐⭐⭐⭐⭐ |
| P2 — Process Merging | 2-3 minggu | ~80 jam | 3 items | ⭐⭐⭐⭐ |
| P3 — Architecture | 1-2 bulan | ~160 jam | 4 items | ⭐⭐⭐ |
| **TOTAL** | **~2 bulan** | **~300 jam** | **14 items** | — |

**Projected System Health Post-Refactor: 8.5/10**

---

## 📁 DELIVERABLE INDEX

Lihat file `FORENSIC_01` sampai `FORENSIC_11` untuk detail lengkap setiap area:

1. `FORENSIC_01_INVENTORY_BASELINE.md` — Inventarisasi lengkap sistem
2. `FORENSIC_02_DEPENDENCY_GRAPH.md` — Peta keterkaitan Menu↔Route↔Component↔API↔DB
3. `FORENSIC_03_BUSINESS_PROCESS_MAP.md` — E2E business flow reconstruction
4. `FORENSIC_04_DATA_ARCHITECTURE.md` — DB consolidation plan dengan SSOT decisions
5. `FORENSIC_05_UX_EFFICIENCY_REPORT.md` — Cognitive load, click depth, friction
6. `FORENSIC_06_DESIGN_SYSTEM_AUDIT.md` — UI/pattern consistency findings
7. `FORENSIC_07_INFORMATION_ARCHITECTURE.md` — Sidebar/navigation restructure (before/after)
8. `FORENSIC_08_DEAD_CODE_INVENTORY.md` — List untuk dihapus
9. `FORENSIC_09_CONSOLIDATION_PLAN.md` — Workflow consolidation: yang mau di-merge
10. `FORENSIC_10_FUTURE_STATE_ARCHITECTURE.md` — Target arsitektur ideal
11. `FORENSIC_11_MIGRATION_ROADMAP.md` — Urutan eksekusi refactoring (P0→P3)

---

## ⚡ NEXT STEPS — DECISIONS REQUIRED

Mohon review dan berikan keputusan untuk hal berikut:

1. **Apakah saya mulai eksekusi P0 (Quick Wins) langsung?**  
2. **Untuk konsolidasi DB Aksesoris, mana arah merger:**
   - a) `acc_items` → `rahaza_materials` (favor Production)
   - b) `rahaza_materials` accessories → `acc_items` (favor Procurement Lifecycle)
   - c) Buat schema baru `inventory_items` sebagai SSOT
3. **Untuk Maklon DB, konfirmasi: deprecate `dewi_maklon_orders`?**
4. **Apakah seluruh proposal P0-P3 ini disetujui?** (Atau ada yang perlu di-reprioritize?)
