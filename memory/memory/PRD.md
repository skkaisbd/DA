# DA25 ERP — Product Requirements Document

> **Version:** DA47 | **Last Updated:** 2026-05-27 (Session #11.20)  
> **Status:** ✅ ALL P0/P1/P2/P3/UI-UX Tasks COMPLETE

---

## 🚨 MANDATORY READING UNTUK SETIAP AGENT BARU

1. **`/app/AGENT_DEVELOPMENT_RULES.md`** — Rules anti-tech-debt (WAJIB dibaca)
2. **`/app/NEXT_AGENT_INSTRUCTIONS.md`** — Quick start guide + task options
3. **`/app/docs/SYSTEM_ARCHITECTURE.md`** — Arsitektur sistem lengkap
4. **`/app/docs/SESSION_LOG.md`** — Semua riwayat sesi (35+ sessions)
5. **`/app/FORENSIC_00_EXECUTIVE_SUMMARY.md`** — Hasil audit forensik

**Jangan skip pembacaan di atas — sistem ini punya history technical debt yang harus dihindari.**

---

## 📁 Navigasi Dokumen

### Domain Documentation (Per-Domain Reference)
| Domain | File | Covers |
|---|---|---|
| HR & Payroll | [`/app/docs/domains/HR_PAYROLL.md`](../docs/domains/HR_PAYROLL.md) | Karyawan, absensi, cuti, lembur, penggajian, KPI, rekrutmen, LMS |
| Production | [`/app/docs/domains/PRODUCTION.md`](../docs/domains/PRODUCTION.md) | WO, bundle, material, cutting, QC, WIP, Control Tower |
| Finance | [`/app/docs/domains/FINANCE.md`](../docs/domains/FINANCE.md) | COA/GL, AR/AP, P2P, budget, bank recon, laporan keuangan |
| Warehouse/WMS | [`/app/docs/domains/WAREHOUSE_WMS.md`](../docs/domains/WAREHOUSE_WMS.md) | Receiving, fabric rolls, opname, delivery notes, picklist |
| Maklon & CMT | [`/app/docs/domains/MAKLON_CMT.md`](../docs/domains/MAKLON_CMT.md) | Maklon PO, CMT progress, billing, client portal |
| Marketing & KOL | [`/app/docs/domains/MARKETING_KOL.md`](../docs/domains/MARKETING_KOL.md) | Akun marketplace, sales, KOL, LiveHost, campaigns |
| Asset & RnD | [`/app/docs/domains/ASSETS_RND.md`](../docs/domains/ASSETS_RND.md) | Asset register, maintenance, RnD styles, HPP |

### Architecture & History
| File | Content |
|---|---|
| [`/app/docs/SYSTEM_ARCHITECTURE.md`](../docs/SYSTEM_ARCHITECTURE.md) | Stack, SSOT, auth, notif, counters, scheduler, tech debt timeline |
| [`/app/docs/SESSION_LOG.md`](../docs/SESSION_LOG.md) | Semua session logs (35+ sesi, reverse chronological) |
| [`/app/FORENSIC_*.md`](../) | Hasil forensic audit 2026-05-22 (12 dokumen) |

---

## 📈 Current State Snapshot

### Sistem Saat Ini
- **Backend:** FastAPI, 1,485 endpoints, 200+ route modules
- **Frontend:** React 18, 279 ERP modules (lazy-loaded), bundle 222kB (51% reduction)
- **Database:** MongoDB, ~60 active SSOT collections
- **Tests:** iteration_92 — Backend 27/27 (✅), Frontend 9/9 (✅)
- **Health:** `/api/health` → OK, DB connected

### Portal yang Tersedia
| Portal | Nav ID | Status |
|---|---|---|
| 📊 Management Dashboard | `management-portal` | ✅ Active |
| 🏭 Production | `production-portal` | ✅ Active |
| 🧵 Warehouse/Gudang | `warehouse-portal` | ✅ Active |
| 💼 HR/HRIS | `hris-portal` | ✅ Active |
| 📀 Finance | `finance-portal` | ✅ Active |
| 🧵 Maklon | `maklon-portal` | ✅ Active |
| 📣 Marketing | `marketing-portal` | ✅ Active |
| 🔬 RnD | `rnd-portal` | ✅ Active |
| 👤 Portal Saya | `self-portal` | ✅ Active |
| 📦 Asset | `asset-portal` | ✅ Active |

---

## 🔑 Test Credentials

```
URL:      https://da37-cmt-bridge.preview.emergentagent.com
Email:    admin@garment.com
Password: Admin@123
Role:     Super Admin (semua akses)
```

---

## 📝 3 Session Terbaru

### Session #11.20 (2026-05-27) — Approval Chain Completion ✅
**Goal:** Fix incomplete approval chains.  
**What:** Tambah `resignation` + `asset_purchase` chains. Buat `seed_missing_chains()` idempotent.  
**Result:** 11 chains, 8 entity types. iteration_92: 100%.  
**Files:** `services/approval_chain_service.py`, `routes/approval_multilevel.py`

### Session #11.19 (2026-05-27) — Universal Scan + PR→PO ✅
**Goal:** Universal multi-entity scan FAB + PR→PO workflow.  
**What:** `universal_scan.py` (7 entity types), `UniversalScanPortal.jsx` (FAB + modal), PR→PO convert endpoint.  
**Result:** All tests pass.  
**Files:** `routes/universal_scan.py`, `components/erp/scanner/UniversalScanPortal.jsx`

### Session #11.18 (2026-05-27) — Jest Coverage + Bundle Optimization ✅
**Goal:** Jest 204 tests, bundle size 51% reduction (222kB), 2 bug fixes.  
**What:** Bundle split, lazy loading improvements, 2 regressions fixed.  
**Result:** iteration_90: 100%. Bundle: 451kB → 222kB.  
**Files:** `webpack.config.js`, multiple component fixes

> **For full session history:** See [`/app/docs/SESSION_LOG.md`](../docs/SESSION_LOG.md)

---

## 🏗️ Architecture Overview

```
Stack:     React 18 (CRA) + FastAPI (Python 3.11) + MongoDB
Auth:      JWT (HS256), 24h expiry, RBAC with role matrix
Realtime:  SSE (Server-Sent Events) for notifications + livehost
Counters:  SSOT: counters collection (namespace discriminator)
Notifs:    SSOT: notifications collection (type discriminator)
Scheduler: APScheduler (birthday, leave carry-forward, overdue scan)
Scan:      Universal Scan FAB (7 entity types)
Approval:  Multi-level chains (11 chains, 8 types)
```

> **Full architecture details:** [`/app/docs/SYSTEM_ARCHITECTURE.md`](../docs/SYSTEM_ARCHITECTURE.md)

---

## 📌 Key Files Quick Reference

| File | Purpose |
|---|---|
| `backend/server.py` | FastAPI entry, router registration, startup indexes |
| `backend/utils/counters.py` | Atomic counter SSOT helper |
| `backend/utils/notif_unified.py` | Notification SSOT helper |
| `backend/utils/scheduler.py` | Cron scheduler jobs |
| `backend/routes/approval_multilevel.py` | Unified approval chains |
| `backend/routes/universal_scan.py` | Universal entity scanner |
| `frontend/src/App.js` | React router |
| `frontend/src/components/erp/portal-shell/PortalShell.jsx` | Portal shell |
| `frontend/src/components/erp/portal-shell/portalNav.js` | Nav config |
| `frontend/src/components/erp/portal-shell/moduleRegistry.js` | Lazy module map |
| `frontend/src/components/erp/scanner/UniversalScanPortal.jsx` | Universal scan FAB |

---

## 🗔️ Tech Debt Status (ALL COMPLETE)

| Phase | Status | Details |
|---|---|---|
| P0 Quick Wins | ✅ DONE | Broken menus, badge cleanup, duplicates removed |
| P1 Data Consolidation | ✅ DONE | A: Accessories, B: Maklon, C: P2P Flow, D: Toko Migration |
| P2 Workflow (14 tasks) | ✅ DONE | All 14 workflow consolidations complete |
| P3 Architecture | ✅ DONE | Opname, Accessory, Counters, Notifications, Orphan collections |
| UI-UX | ✅ DONE | Hash routing, Jest 204, bundle 222kB, design consistency |
| Approval Chains | ✅ DONE | 11 chains, 8 entity types |
| Universal Scan | ✅ DONE | 7 entity types, FAB + modal |

**All P0/P1/P2/P3/UI-UX tasks: COMPLETE ✅**

---

## 👥 User Personas

| Role | Access | Portal |
|---|---|---|
| Super Admin | Semua fitur + user/role management | Management |
| Finance Staff | Invoice, payment, laporan keuangan | Finance |
| HR Staff | Karyawan, absensi, cuti, penggajian | HRIS |
| Production Staff | WO, bundle, material, WIP | Production |
| Marketing Staff (PIC) | Akun marketplace, sales, KOL, LiveHost | Marketing |
| Warehouse Staff | Receiving, opname, delivery | Warehouse |
| Maklon Staff | CMT, PO, billing | Maklon |
| RnD Staff | Style, design, HPP, sample | RnD |
| Employee (self) | Portal Saya: payslip, cuti, KPI | Portal Saya |

---

## 🌐 Language Requirement

**SELALU balas user dalam Bahasa Indonesia.** Semua UI labels, messages, dan dokumentasi internal dalam Bahasa Indonesia (kecuali technical terms).

---

*Dokumen ini adalah index. Untuk detail lengkap, lihat file di `/app/docs/`.*
