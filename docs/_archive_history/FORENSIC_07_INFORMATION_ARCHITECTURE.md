# FORENSIC AUDIT — 07: INFORMATION ARCHITECTURE
## Sidebar / Navigation Restructure Plan (Before & After)

**Lensa:** L1 Information Architecture + L5 Human-Centered + L6 Workflow Consolidation

---

## PRINSIP RESTRUKTUR

1. **Task-Oriented Grouping** — Group by what user does, bukan by tech
2. **Max 15 items per section** — Below cognitive overload threshold
3. **No "Lama/Baru" labels** — Migrate or hide legacy
4. **No P0/P1/BARU badges leaking** — Use sparingly, with expiry
5. **Frequent tasks at top** — Daily ops first, masters last
6. **Hide rarely-used** — Move to "More" or footer

---

## PORTAL MANAJEMEN — RESTRUKTUR

### BEFORE (3 sections, 18 items)
```
RINGKASAN (6)
  Dashboard Eksekutif
  Ringkasan Bisnis
  Laporan & Dashboard (Maklon/CMT) [BARU]
  Laporan
  Data Pelanggan
  Portal RnD (Shortcut) [PORTAL]

SISTEM (8)
  Manajemen Pengguna
  Manajemen Peran
  Matriks Hak Akses
  Log Aktivitas
  Pengaturan Perusahaan
  Konfigurasi PDF
  Integrasi & API Keys
  Panduan Penggunaan

TOOLS & DIGEST (4)
  Weekly Digest & Audit [BARU]
  AI Business Intelligence [AI]
  Strategic OKR Tracker [BARU]
  AI Usage Monitor [BARU]
```

### AFTER (3 sections, 16 items)
```
DASHBOARD & LAPORAN (5)
  Dashboard Eksekutif
  Ringkasan Bisnis
  Laporan Konsolidasi          ← merge "Laporan" + "Laporan Maklon/CMT"
  Data Pelanggan
  Strategic OKR Tracker

INTELIGENSI & AI (3)
  AI Business Intelligence
  Weekly Digest & Audit
  AI Usage Monitor

ADMINISTRASI SISTEM (8)
  Manajemen Pengguna
  Akses & Peran                 ← merge "Manajemen Peran" + "Matriks Hak Akses"
  Pengaturan Perusahaan
  Konfigurasi Dokumen (PDF)
  Integrasi & API Keys
  Log Aktivitas
  Panduan Penggunaan
  Portal RnD (Shortcut)
```

**Reduction:** 18 → 16 items, removed 7 badges.

---

## PORTAL PRODUKSI — RESTRUKTUR

### BEFORE (4 sections, 38 items dengan 14 subgroup)
Terlalu padat dan kompleks. Banyak subgroup dengan 1-2 item saja.

### AFTER (4 sections, 28 items dengan 6 subgroup utama)
```
KOMANDO PRODUKSI (Dashboard & Live Ops)
  Dashboard Produksi              ← includes OEE, Backlog, Predictive Maintenance tabs
  Production Control Tower         ← NEW: gabung Line Board + Andon + Shift Handover (3 in 1!)
  Production Wizard
  Pengiriman & Surat Jalan

ALUR PRODUKSI (5 Tahap + CMT)
  Order → WO → Bundle               ← merge: prod-orders + prod-work-orders + prod-bundles dgn tab
  Material & Reservasi              ← merge: prod-material-reservation + prod-bulk-mi
  1. Cutting (Planning + Eksekusi) ← merge prod-cutting + prod-exec-cutting (BIG WIN!)
  2. Jahit (CMT internal + vendor) ← merge prod-exec-sewing + prod-cmt
  3. Finishing
  4. QC Final + Rework             ← merge prod-exec-qc + prod-exec-rework
  5. Packing (Internal + CMT)      ← merge prod-exec-packing + prod-cmt-packing

KUALITAS & ANALITIK
  Pareto Cacat
  First Pass Yield (FPY)
  AQL Sampling Tool
  Log Downtime
  AI Insights & Chatbot
  AI Action Items
  Predictive Maintenance
  Pengaturan Alert                  ← FIX: implement missing module

MASTER DATA
  Lokasi & Workspace                ← merge prod-locations + prod-lines + prod-machines + prod-shifts as tabs
  Proses & Standar (SOP, Defect)    ← merge prod-processes + prod-sop + prod-defect-codes
  Kalender Produksi
  Operator & Skill Matrix
  Master Produk & BOM
```

**Reduction:** 38 → ~28 items. **Tasks per click depth reduced ~30%.**

**Key Wins:**
- ✅ **Fix `prod-rework-board`** → merged into QC Final + Rework tab
- ✅ **Fix `prod-alert-settings`** → implemented in Quality section
- ✅ **Merge Cutting Planning + Execution** → 1 modul bertab (eliminates SSOT issue)
- ✅ **Merge CMT in Production** — CMT is part of production workflow, not separate

---

## PORTAL GUDANG — RESTRUKTUR

### BEFORE (3 sections, 24 items dengan 3 "isHeader" dummies)
Membingungkan karena Aksesoris punya 2 sub-system tidak jelas.

### AFTER (3 sections, 18 items — cleaner)
```
INVENTORI (Master & Stok)
  Dashboard Gudang
  Master Item (Material/Aksesoris/FG)  ← merge wh-materials + wh-accessory-master, single page dengan tab type
  Stok & Pergerakan                    ← merge wh-stock + wh-accessory-stock + wh-fg into tab view
  Unified Inventory Viewer
  Material Issue (Single + Bulk)       ← merge wh-material-issue + prod-bulk-mi via tab
  Reservasi Material

OPERASIONAL
  Purchase Order → GRN                 ← SINGLE FLOW: PO list + GRN button inline (NEW)
  Delivery Order (DO) + Surat Jalan    ← merge do-management + wms-delivery-notes
  Fulfillment (Order → FG Out)
  Pick List
  Put-Away & Lokasi (Bin)
  Stok Opname (Standard + Cycle Count) ← merge wh-opname + wms-opname-enhanced via tab
  Return & Refund
  Alert, Reorder & Undo
  Supplier Scorecard
  Inbox Permintaan Aksesoris

GARMENT WMS (Advanced)
  WMS Scanner & Setup
  Fabric Roll Tracking
  CMT Material Dispatch
```

**Reduction:** 24 → 18 items. **Resolves 4 SSOT issues** (Accessory, Stock, Opname, Receiving).

---

## PORTAL KEUANGAN — RESTRUKTUR

### BEFORE (3 sections, 25 items dengan 9 subgroup)

### AFTER (4 sections, 20 items)
```
DASHBOARD & ANALITIK
  Dashboard Keuangan
  Rekap Keuangan
  AI Cash Flow Prediction
  Laporan Arus Kas

AR & AP (Operasi Harian)
  Daftar Piutang (AR)
  Invoice Penjualan
  Hutang Vendor (AP)
  Invoice Vendor (Manual)
  Persetujuan Invoice
  Aging AR & AP                  ← merge fin-ap-aging + fin-ar-aging

KAS, BANK & PEMBAYARAN
  Kas & Bank
  Pembayaran
  Pengeluaran
  Rekonsiliasi Bank

AKUNTANSI INTI
  Bagan Akun (COA)
  Jurnal Umum + Daftar           ← merge fin-journal-entry + fin-journal-list
  Buku Besar (GL)
  Neraca Saldo
  Laba Rugi
  Neraca
  Pusat Biaya & HPP              ← merge fin-cost-centers + fin-hpp
  Periode & Posting Profile      ← merge fin-periods + fin-posting-profiles
  Anggaran
  Aset Tetap
```

**Reduction:** 25 → 20 items.

---

## PORTAL SDM — RESTRUKTUR

### BEFORE (6 sections, 30 items)
Terlalu banyak header dummy ("Onboarding", "Career Development", "Attendance", dll punya isHeader=true tapi cuma 1-2 child).

### AFTER (5 sections, 22 items)
```
DASHBOARD & ANALITIK SDM
  Dashboard SDM (Real-time + AI)  ← merge hr-dashboard + hr-ai-insights
  Predictive Attrition (AI)
  Skill Gap Analysis
  Laporan & Analitik SDM

KARYAWAN & ORGANISASI
  Data Karyawan & Kontrak
  Struktur Organisasi
  Aset Karyawan
  HR Admin & Seed

REKRUTMEN & PENGEMBANGAN
  Recruitment Pipeline             ← merge hr-recruitment + hr-resume-screening + hr-job-board via tabs
  Onboarding Checklist
  Learning Management
  Performance Coaching (AI)

KEHADIRAN & SHIFT (Daily Ops)
  Inbox Approval SDM               ← NEW: unified approvals (cuti+lembur+absen+salary adj)
  Absensi (Manual + Otomatis)     ← merge hr-attendance + hr-auto-attendance via tab
  Shift Scheduler
  Lembur & Overtime
  Cuti & Saldo                     ← merge hr-leave + hr-leave-balances

KINERJA & PENGGAJIAN
  KPI & Performance Review         ← merge hr-kpi + hr-performance + hr-360-feedback via tabs
  Profil & Tunjangan               ← merge hr-payroll-profiles + hr-payroll-allowances
  Kenaikan Gaji (Approval)
  Penggajian & Slip
```

**Reduction:** 30 → 22 items. **Big UX win:** Inbox Approval SDM — 1 stop for all pending approvals.

---

## PORTAL MARKETING — RESTRUKTUR

### BEFORE (5 sections, 26 items dengan banyak subgroup)
Banyak modul "Lama" yang masih exposed (`toko-channels`, `toko-pricing`).

### AFTER (5 sections, 22 items — legacy hidden)
```
DASHBOARD & OVERVIEW
  Marketing Overview
  Account Health
  Sales Performance
  Ads Performance

OPERASI HARIAN
  Manage Accounts                  ← sudah merge: marketing-accounts (single account mgmt)
  Input Sales Harian
  Universal Smart Import
  Unified Orders
  Kelola Komplain & Returns        ← merge marketing-complaints + marketing-returns
  Live Sessions

KAMPANYE & KONTEN
  Content Calendar
  Discount Campaign
  Product Launch
  Manajemen Katalog

KOL & CREATOR
  KOL & Creator Mgmt
  Kreator Requests
  LiveHost Management              ← KEEP (was misplaced — actually HR-tied, but OK here for now)
  KOL Leaderboard

AI & LAPORAN PIC
  AI Marketing Insights            ← merge marketing-ai-insights + marketing-advanced-ai
  AI Content & Image Generator     ← merge marketing-ai-content + marketing-ai-image
  Laporan PIC (Harian + Bulanan)   ← merge marketing-daily-report + marketing-monthly-report
  Target Bulanan per Akun
  Scheduler & Otomasi

PENGATURAN & SUPPORT
  Rating & Review Management
  Pengiriman Sample
  Task Management (Kanban+Approvals+Templates) ← merge marketing-tasks + approvals + templates via tabs
  API Integration Settings
  Notifikasi Provider
```

**Hidden (legacy):** `toko-channels`, `toko-pricing` — migrate to modern equivalents, then remove.

**Reduction:** 26 → 22 items.

---

## PORTAL MAKLON — RESTRUKTUR

### BEFORE (4 sections, 14 items — 2 broken)

### AFTER (3 sections, 10 items — all working + 360 view)
```
KLIEN & ORDER
  Dashboard Maklon
  Data Klien Maklon
  Maklon PO 360° View         ← NEW: single page tab-based untuk seluruh lifecycle 1 PO
                                  (replaces maklon-po, maklon-orders, maklon-samples, maklon-tracking, maklon-qc as tabs)
  AI Quote Generator

OPERASIONAL (CMT → dimove ke Production)
  HPP Jasa Jahit
  SLA Dashboard & Lead Time

KEUANGAN & PENGATURAN
  Invoice & Billing
  Notification Center
  System Config
```

**✅ FIX:**
- `maklon-cmt` → dimove ke Production (CMT belongs there)
- `maklon-packing` → dimove ke Production CMT Packing
- `cmt-progress` → dimove ke Production

**Reduction:** 14 → 10 items. Plus eliminates 2 broken menus.

---

## PORTAL SAYA — RESTRUKTUR

### BEFORE (3 sections, 13 items)

### AFTER (3 sections, 12 items — reorganized)
```
BERANDA & PROFIL
  Dashboard Saya
  Profil Saya
  Notifikasi Inbox

KEHADIRAN & WAKTU
  Kehadiran Saya
  Cuti & Lembur
  Slip Gaji Saya

KINERJA & PENGEMBANGAN
  KPI Saya
  My Annual Review
  Peer Feedback
  Training Saya
  AI Career Coach
  My Workspace                    ← IMPLEMENT (currently from WORKSPACE_DESIGN.md spec)
  Dokumen Saya
```

**Same count, better grouping.**

---

## PORTAL KOLABORASI — EXPAND (currently too sparse)

### BEFORE (1 section, 2 items)

### AFTER (3 sections, 8 items)
```
KOMUNIKASI
  Communication Hub                 ← main chat/channels
  Notifications & Mentions

WORKSPACE & DOKUMEN
  My Workspace (Spreadsheet)
  Shared Documents
  Activity Feed                     ← unified activity across all portals

LEARNING
  Course Catalog
  My Courses
  Study Groups
```

**Resolves:** Communication Hub gap, Workspace gap, Asset Mgmt gap (separate portal).

---

## PORTAL ASET (KEEP minor + expand)

### BEFORE (1 section, 3 items)

### AFTER (2 sections, 6 items)
```
MASTER & DASHBOARD
  Dashboard Aset
  Daftar Aset
  Kategori Aset

OPERASIONAL
  Penugasan & Transfer             ← NEW: implement transfer UI (gap!)
  Maintenance & PM                  ← includes preventive maintenance
  Disposal & Depresiasi             ← includes scrap/sale flow
  Request Pengadaan
```

**Resolves:** Asset Transfer gap from GAP_ANALYSIS_REPORT.md

---

## TOTAL ITEM REDUCTION

| Portal | Before | After | Reduction |
|--------|--------|-------|-----------|
| Manajemen | 18 | 16 | -11% |
| Produksi | 38 | 28 | -26% |
| Gudang | 24 | 18 | -25% |
| Keuangan | 25 | 20 | -20% |
| SDM | 30 | 22 | -27% |
| Marketing | 26 | 22 | -15% |
| Maklon | 14 | 10 | -29% |
| Portal Saya | 13 | 12 | -8% |
| Kolaborasi | 2 | 8 | +300% (expanded) |
| Aset | 3 | 6 | +100% (expanded) |
| RnD | 12 | 12 | 0% |
| **TOTAL** | **205** | **174** | **-15%** |

Plus eliminasi:
- 4 broken menu items (fixed)
- 8 misplaced menu items (relocated)
- 25+ "BARU" badges (cleaned)
- 10+ "P0/P1" technical labels (hidden)
- 4 "Lama" labels (legacy hidden)

---

## NAMING GLOSSARY (NEW)

Define konsisten:
```
Order        → "Order" (consistent, in Indonesian: "Pesanan")
Work Order   → "WO" abbreviated, or "Work Order"
Purchase Order → "PO"
Maklon PO    → "PO Maklon"
Master Data  → "Master" prefix in Indonesian: "Master ..."
Dashboard    → "Dashboard" (keep English, widely understood)
Inbox        → "Inbox" or "Kotak Masuk"
Approval     → "Persetujuan"
Report       → "Laporan"
Settings     → "Pengaturan"
```

---

## NEW "GLOBAL WORKSPACE" CONCEPT

Untuk mengurangi cross-portal navigation, propose **Global Workspace** sebagai entry default setelah login:

```
User login → Lihat "Workspace Saya":
  - Pending Approvals (cross-portal)
  - Today's Tasks (cross-portal)
  - Recent Items (last viewed)
  - Favorites (user-defined)
  - Quick Actions (role-based)
  - Notifications (recent)
```

Ini mengurangi portal switching dan menjadi anchor untuk daily work.
