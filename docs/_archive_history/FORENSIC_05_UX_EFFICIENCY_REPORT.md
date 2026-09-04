# FORENSIC AUDIT — 05: UX EFFICIENCY REPORT
## Cognitive Load, Click Depth, & Operational Friction Analysis

**Lensa:** L3 UX Systems + L4 Operational Efficiency + L5 Human-Centered

---

## 1. COGNITIVE LOAD ANALYSIS

### 1.1 Sidebar Density Per Portal

| Portal | Sections | Items | Sub-Groups | Total Visible | Cognitive Load |
|--------|----------|-------|------------|---------------|----------------|
| Manajemen | 3 | 18 | 0 | 18 | 🟢 OK |
| Produksi | 4 | 22 | 14 (subgroups) | 38 | 🔴 HEAVY |
| Gudang | 3 | 24 | 0 | 24 | 🟡 HIGH |
| Keuangan | 3 | 25 | 9 | 25 | 🟡 HIGH |
| SDM | 6 | 30 | 0 | 30 | 🔴 HEAVY |
| RnD | 3 | 12 | 0 | 12 | 🟢 OK |
| Portal Saya | 3 | 13 | 0 | 13 | 🟢 OK |
| Maklon | 4 | 14 | 0 | 14 | 🟢 OK |
| Marketing | 5 | 26 | 12 | 26 | 🔴 HEAVY |
| Kolaborasi | 1 | 2 | 0 | 2 | 🟢 OK (too sparse) |
| Aset | 1 | 3 | 0 | 3 | 🟢 OK (too sparse) |

**Industry Benchmark:** Max 15-20 items per visible section. **Sistem ini melebihi standard untuk 5 portal** (Produksi, Gudang, Keuangan, SDM, Marketing).

### 1.2 Naming Inconsistency Examples

Di sidebar yang sama, ditemukan:
- **Manajemen Pengguna** vs **Manajemen Peran** vs **Matriks Hak Akses** vs **Manajemen Akses** (4 nama untuk konsep terkait)
- **Master Material** vs **Master Aksesoris** vs **Inventory & Pergerakan FG** (3 pola berbeda)
- **Order Produksi** vs **Work Order** vs **PO Maklon (Baru)** vs **Order Maklon (Lama)** (label "Baru/Lama" exposed ke user!)
- **Material Issue (Bulk)** vs **Material Issue (Single)** (clarifier OK tapi indikasi UX issue)
- **Channel Manager (Lama)** vs **Harga & Flashsale (Lama)** ("Lama" label kebocoran legacy)

### 1.3 Badge Overload

Badge yang muncul di sidebar:
- `BARU` — muncul **25+ kali**
- `AI` — muncul **8+ kali**
- `P0`, `P1` — muncul (technical priority leaked to UI!)
- `NEW` (English) vs `BARU` (Indonesian) mixed inconsistent

**Pain Point:** Badge "BARU" tidak punya expiry, sehingga setelah berbulan-bulan masih BARU. Hilangkan informasi yang berguna.

---

## 2. CLICK DEPTH ANALYSIS

### 2.1 Critical User Journeys

#### Journey A: "Buat Sales Order Baru"
```
Login → Pilih Portal Produksi → Klik "OPERASIONAL HARIAN" pill → 
Scroll sidebar ke "Order Produksi" → Klik "Buat Order Baru" button → 
Isi form (15-20 field) → Submit

Click depth: 5 clicks + 15-20 form fields
Friction: HIGH (banyak field, beberapa duplikat dari customer data)
```

#### Journey B: "Cek Stok Aksesoris"
```
User bingung pilih mana:
  Option 1: Gudang > INVENTORI > Stok & Pergerakan (rahaza_material_stock)
  Option 2: Gudang > INVENTORI > Master Aksesoris > Stok & Pergerakan (SAMA DATA)
  Option 3: Gudang > OPERASIONAL > Transaksi Aksesoris (acc_items - DATA BERBEDA)
  Option 4: Unified Inventory Viewer (aggregated)

Result: 3 click paths yang HASILNYA BERBEDA → trust issue
```

#### Journey C: "Approve Cuti Karyawan"
```
Login → Portal SDM → Klik "KEHADIRAN & SHIFT" → 
Scroll ke "Cuti & Izin" header → Klik "Izin & Cuti" → 
Filter status=pending → Klik row → Approve

Click depth: 6 clicks
Better: Workspace dashboard dengan "Pending Approvals" inbox → 1 klik
```

#### Journey D: "Maklon Order Tracking End-to-End"
```
Klien minta status PO maklon-nya. Internal user harus:
  1. Buka Maklon Portal > maklon-po > cari PO X
  2. Cek BOM → sample sudah?
  3. Pindah ke maklon-samples → cari sample untuk PO X
  4. Pindah ke maklon-tracking → cari production progress
  5. Pindah ke maklon-qc → cari QC status
  6. Pindah ke maklon-billing → cek invoice

Click depth: 6+ separate modules untuk 1 PO journey!
Better: Single "PO 360° View" dengan tabs internal
```

---

## 3. FORM COMPLEXITY ANALYSIS

### High-Complexity Forms (need simplification)

| Form | Fields | Required | Repetitive Input |
|------|--------|----------|------------------|
| Order Produksi (rahaza_orders) | 22 | 12 | Customer info partly duplicates customer master |
| Maklon PO | 18+ items + nested seri | 10 | BOM input separately needed |
| GRN (Goods Receipt) | 15 + line items | 8 | Cannot pre-fill from PO |
| Material Issue Bulk | 8 + N lines | 6 | Each line manual entry |
| Recruitment Job Post | 20 | 10 | Many fields duplicate from previous post |
| Payroll Profile Setup | 30+ | 18 | Should template-able |

### Pattern: "Fat Forms"
- Tidak ada "Save as Draft" untuk forms panjang
- Tidak ada multi-step wizard untuk complex flows (kecuali Production Wizard)
- Auto-fill dari master data tidak konsisten

---

## 4. REPETITIVE INPUT / DUPLICATE WORK

### Identified Friction Points

#### A. Manual Cross-Module Linking
```
Maklon PO created → User HARUS manually create Internal WO
Seharusnya: Auto-cascade WO from Maklon PO confirmation
```

#### B. Customer Data Re-entry
```
Order Produksi form punya field Customer Name, Address, Tax ID
Padahal data sudah ada di rahaza_customers
UI: Search/select customer harus pre-fill semua field
Kenyataan: Beberapa form masih ask user re-type
```

#### C. Multiple Login Per Session
```
User dengan multi-role butuh switch portal seringkali
Tidak ada "Global Inbox" yang menggabungkan pending tasks dari semua portal
```

#### D. PO → GR Flow Manual
```
User harus buka PO, copy info, lalu masuk GR module, paste info manual
Seharusnya: Button "Receive against this PO" di PO detail → auto-create draft GR
```

#### E. Approval Chain Manual
```
Approval invoice butuh user pindah ke fin-approval module
Seharusnya: Notification → click → approve inline
```

---

## 5. BOTTLENECK WORKFLOWS

### Identified Bottlenecks

1. **Production Daily Standup**
   - Harus buka 4 modul: Line Board, Andon Board, Shift Handover, Backlog
   - Better: 1 "Production Control Tower" dashboard yang gabung 4 ini

2. **Marketing Daily Reporting (PIC)**
   - Buka: Marketing Overview, Daily Report, Sales Performance, Account Health
   - Better: 1 dashboard "My Daily View" per PIC

3. **HR Morning Routine**
   - Buka: Absensi Harian, Approval Absen, Cuti, Lembur, Overtime Request
   - Better: 1 "HR Inbox" dengan tab pending items

4. **Finance End-of-Day**
   - Buka: Daftar Piutang, Hutang Vendor, Persetujuan Invoice, Rekap Keuangan
   - Better: "Finance Today" dashboard widget-based

---

## 6. MOBILE / RESPONSIVE FRICTION

- Sidebar di mobile butuh full open (no swipe gesture)
- Section pill nav hidden di mobile (only burger menu)
- Forms panjang sulit di-fill di mobile (tidak ada "next field" hint)
- Tabel data tidak responsive (horizontal scroll only)

---

## 7. SEARCH & DISCOVERY

### Current State
- Global Search di topbar (uses `/api/global-search`)
- Command Palette dengan Ctrl/Cmd+K
- Per-module search bar di hampir setiap module

### Issues
- Global search hanya menemukan **modules**, bukan **records** (data) di banyak kasus
- Tidak ada saved search / quick filter
- Tidak ada recent items / favorites
- Per-module search inkonsisten (debounce timing, filter chips, result count)

---

## 8. ERROR & EMPTY STATES

### Inkonsistensi
- Sebagian module pakai skeleton loader, sebagian pakai spinner
- Empty state design beragam (text only vs ilustrasi vs button-CTA)
- Error toasts pakai default sonner color (kadang clash dengan theme)

---

## 9. OPERATIONAL EFFICIENCY METRICS

### Estimated Time-to-Task (TTT) for Common Tasks

| Task | Current TTT | Optimal TTT | Gap |
|------|-------------|-------------|-----|
| Buat Order baru | ~3 min | ~1 min | 200% slower |
| Approve cuti karyawan | ~1.5 min | ~15 sec | 500% slower |
| Cek stok aksesoris specific item | ~45 sec | ~10 sec | 350% slower |
| Buat shipment dari WO completed | ~2 min | ~30 sec | 300% slower |
| Daily marketing report submit | ~10 min | ~3 min | 230% slower |
| Maklon PO progress check | ~5 min (6 modules) | ~1 min (1 dashboard) | 400% slower |

**Average operational slowdown: 3.6x optimal**

---

## 10. UX RECOMMENDATIONS (PRIORITIZED)

### 🔴 P0 — Quick UX Wins (1 hari)
1. Hapus badge "Lama/Baru" dari sidebar labels (move to internal docs)
2. Fix 4 broken menus (no fallback ke dashboard)
3. Relokasi 8 menu yang salah section
4. Hapus duplicate "Master Aksesoris" + "Stok Aksesoris" (consolidated ke `wh-stock` with tab filter)

### 🔴 P1 — Workflow Consolidation (1 minggu)
5. Buat **Maklon 360° View** — single page tab-based untuk 1 PO
6. Buat **Production Control Tower** — gabung Line Board + Andon + Shift Handover
7. Buat **HR Inbox** — unified pending approvals (cuti, lembur, salary adj)
8. Buat **Finance Today** dashboard widget
9. Auto-fill customer data dari master di semua order forms
10. Implementasi "Create GR from PO" flow (link bridging)

### 🟡 P2 — Polish & Standardization (2 minggu)
11. Standardize loading states (skeleton uniform)
12. Standardize empty states (illustration + CTA)
13. Standardize error toasts (theme-aligned)
14. Add "Save as Draft" untuk forms >10 fields
15. Add multi-step wizard untuk Order Produksi & Maklon PO
16. Add "Recent" + "Favorites" di sidebar footer

### 🟡 P3 — Advanced UX (1 bulan)
17. Implementasi global "Workspace Dashboard" (cross-portal pending tasks)
18. Implementasi mobile-first responsive (table cards, gesture nav)
19. Add search by RECORDS (not just modules) di global search
20. Add saved searches + filter presets

---

## CONCLUSION

UX Score saat ini: **4/10**

**Bottleneck utama:**
- Cognitive overload di sidebar (5 portal critically heavy)
- Click depth 3-6x optimal untuk task umum
- Forms panjang tanpa pre-fill dari master
- Workflow fragmentasi (1 PO = 6 modul terpisah)
- Approval chain manual

**Target Post-Refactor: 8/10**

Lihat `FORENSIC_07_INFORMATION_ARCHITECTURE.md` dan `FORENSIC_09_CONSOLIDATION_PLAN.md` untuk detail solusi.
