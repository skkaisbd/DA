# 🔧 SSOT MASTER REPAIR PLAN — PART 5 (FINAL REPAIR)
## UI Theme Sync (113 file) · Full Frontend Review (309 modul) · Full Flow & RBAC Coverage

> **Status:** RENCANA EKSEKUSI — dokumen ini adalah **SATU-SATUNYA KEBENARAN (TRUTH)** untuk pekerjaan final repair. Ikuti PERSIS, jangan improvisasi.
> **Ditulis agar agent/model AI PEMULA pun bisa mengeksekusi**: setiap langkah dieja satu-per-satu, dengan perintah copy-paste, kriteria lulus/gagal yang tegas, dan template laporan.
> **JANGAN sentuh lagi** apa pun yang sudah diperbaiki di Part 1–4 + Session #16/#17 (lihat `/app/memory/CHANGELOG.md`). Bila ragu apakah sesuatu sudah dicakup — cek CHANGELOG dulu, baru kerjakan.
> **Data**: SEMUA data adalah seed. Boleh hilang/di-reset kapan pun (arahan user). Prioritas = sistem bersih & benar.

---

# BAGIAN 0 — KONTEKS, STATUS TERKINI & ATURAN MUTLAK

### 0.1 Status yang SUDAH selesai (JANGAN dikerjakan ulang)
- **Aliran data/SSOT**: RC-01..RC-29 tuntas. Sweep 930 GET = **0 crash**. Tidak ada lagi duplikasi SSOT tingkat data (47 phantom-read diperbaiki; 216 dormant terklasifikasi sah; 15 orphan diputuskan).
- **Duplikasi menu**: 15 menu → 5 hub (`fin-journal-hub`, `marketing-ai-hub`, `hr-ai-hub`, `marketing-live-hub`, `rnd-costing-hub`); CMT/opname/shipping legacy redirect; 4 router CMT diarsip.
- **Backend**: JANGAN ubah backend kecuali diminta eksplisit di BAGIAN 5 (flow coverage) — dan itu pun HANYA jika bug ditemukan lewat prosedur BAGIAN 5.

### 0.2 Tiga pekerjaan PART 5 (urutan wajib)
| Kode | Pekerjaan | Skala | Bagian |
|---|---|---|---|
| **RC-UI-01** | Sinkronisasi tema: ganti SEMUA warna hardcode gelap → token tema semantik | 113 file / ±629 kemunculan | BAGIAN 1–3 |
| **RC-UI-02** | Review render SEMUA modul terdaftar (deep-link satu-per-satu) | ±309 id modul | BAGIAN 4 |
| **RC-FLOW** | Cakupan write-flow (POST/PUT/DELETE) + RBAC per portal | per domain | BAGIAN 5 |

### 0.3 ATURAN MUTLAK (pelanggaran = pekerjaan ditolak)
1. **SATU file = SATU commit-unit.** Selesaikan 1 file penuh (fix → lint → compile → verifikasi visual) SEBELUM pindah file berikutnya.
2. **JANGAN mengubah logika** (state, fetch, handler, props) saat RC-UI-01 — HANYA string className.
3. **JANGAN menyentuh file di `_archive/`** dan file yang di-comment di moduleRegistry.
4. **Gunakan HANYA tabel konversi BAGIAN 1.** Jika menemukan kelas yang tidak ada di tabel → tulis di laporan sebagai `PERLU-KEPUTUSAN`, JANGAN menebak.
5. Setelah SETIAP file: `yarn tidak perlu` — hot reload otomatis; cukup cek log compile (perintah di BAGIAN 2 langkah 6).
6. Setiap modul selesai → tulis laporan `FINAL REPAIR MODUL <nama>` (template BAGIAN 2.9) ke `/app/memory/FINAL_REPAIR_LOG.md` (append, jangan menimpa).
7. Kredensial uji: `admin@garment.com` / `Admin@123`. Rate-limit login 10/60 dtk — login sekali, reuse.
8. Navigasi modul TERBUKTI: login di UI → jalankan di console/JS: `window.location.hash='<module-id>'` → reload halaman.

---

# BAGIAN 1 — RC-UI-01: TABEL KONVERSI WARNA (SATU-SATUNYA ACUAN)

### 1.1 Kenapa ini bug
Aplikasi punya 2 tema (light/dark) berbasis CSS variables (shadcn). Kelas seperti `bg-zinc-900` = HITAM PERMANEN — di tema terang kartu jadi hitam, teks abu tak terbaca (bukti: screenshot user di modul Live Session Analytics). Token semantik (`bg-card`, `text-foreground`, dst.) otomatis mengikuti tema.

### 1.2 TABEL KONVERSI WAJIB (ganti string PERSIS kolom kiri → kolom kanan)
| ❌ Hardcode (cari string ini) | ✅ Ganti dengan | Makna |
|---|---|---|
| `bg-zinc-950`, `bg-zinc-900`, `bg-slate-900`, `bg-gray-900`, `bg-neutral-900`, `bg-stone-900` | `bg-card` | permukaan kartu |
| `bg-zinc-800`, `bg-slate-800`, `bg-gray-800` | `bg-muted` | permukaan sekunder |
| `bg-zinc-700`, `bg-slate-700` | `bg-muted-foreground/30` | bar/track |
| `bg-black` (sebagai latar konten) | `bg-card` | — |
| `hover:bg-zinc-800/30`, `hover:bg-zinc-800`, `hover:bg-slate-800` | `hover:bg-muted/50` | hover baris |
| `border-zinc-800`, `border-zinc-700`, `border-zinc-600`, `border-slate-700/800`, `border-gray-700/800` | `border-border` | garis |
| `border-zinc-800/50` → `border-border/50` · `border-zinc-800/30` → `border-border/30` | (pertahankan opasitas) | — |
| `text-zinc-100`, `text-zinc-200`, `text-slate-100/200`, `text-gray-100/200` | `text-foreground` | teks utama |
| `text-zinc-300`, `text-slate-300`, `text-gray-300` | `text-foreground/80` | teks agak redup |
| `text-zinc-400`, `text-slate-400`, `text-gray-400` | `text-muted-foreground` | teks sekunder |
| `text-zinc-500`, `text-slate-500`, `text-gray-500` | `text-muted-foreground/80` | teks tersier |
| `text-zinc-600`, `text-slate-600`, `text-gray-600` | `text-muted-foreground/60` | teks paling redup |
| `divide-zinc-800`, `divide-slate-800` | `divide-border` | pemisah list |
| `ring-zinc-700/800` | `ring-border` | — |
| `placeholder-zinc-500` | `placeholder-muted-foreground` | — |

### 1.3 PENGECUALIAN SAH (JANGAN diganti — biarkan)
1. **`text-white` DI ATAS latar berwarna/gradien**: mis. `bg-purple-600 text-white`, `bg-gradient-to-r ... text-white`, `bg-emerald-500 text-white` (tombol/badge berwarna). Aturan cepat: jika dalam className yang SAMA ada `bg-<warna selain zinc/slate/gray/neutral/stone/black>` → `text-white` SAH.
2. **Warna aksen status**: `text-emerald-400`, `bg-red-500/15`, `border-amber-500/30` dst. = SAH (aksen, terbaca di 2 tema).
3. **Modul by-design GELAP PERMANEN** (layar TV/kiosk/scanner — memang selalu gelap): `erp/ShopFloorTV.jsx`, `erp/scanner/UniversalScanPortal.jsx` + file di folder `scanner/`. Ini DIKECUALIKAN dari RC-UI-01 (catat di laporan "SKIP by-design").
4. **Portal eksternal standalone** (`livehost/LiveHostPortalApp.jsx`, `kol-portal/*`, `client/*`, `vendor-cmt/*`): tema sendiri — kerjakan TERAKHIR (Wave U5) dan HANYA jika di tema terang terlihat rusak; jika portal memang full-dark by design → "SKIP by-design".
5. `dark:` variants (mis. `dark:bg-zinc-900`) = SAH (hanya aktif di dark mode) — JANGAN diubah. Yang dicari adalah kelas TANPA prefix `dark:`.

### 1.4 Contoh nyata (SUDAH dikerjakan sebagai acuan)
File `erp/marketing/LiveSessionAnalyticsDashboard.jsx` (pelanggar #1, 26+ kemunculan) **SUDAH diperbaiki** dengan tabel 1.2 — buka file itu untuk melihat hasil akhir yang benar. Gunakan sebagai referensi visual/kode.

---

# BAGIAN 2 — RESEP LANGKAH-DEMI-LANGKAH PER FILE (ikuti persis, jangan lompat)

> Kerjakan file sesuai urutan Wave di BAGIAN 3. Satu file = ulangi resep ini dari langkah 1.

**Langkah 1 — Lihat pelanggaran file:**
```bash
cd /app/frontend/src/components
grep -nE "(^|[^:])(bg|text|border|divide|ring)-(zinc|slate|gray|neutral|stone)-(100|200|300|400|500|600|700|800|900|950)|bg-black\b|text-white\b" <PATH_FILE> | head -60
```
**Langkah 2 — Untuk setiap baris hasil**: cocokkan kelasnya dengan tabel 1.2. Cek dulu pengecualian 1.3 (terutama `text-white`).
**Langkah 3 — Lakukan penggantian** memakai search-replace per string unik ATAU sed aman per-kelas:
```bash
sed -i 's/bg-zinc-900/bg-card/g; s/bg-zinc-800/bg-muted/g; s/border-zinc-800/border-border/g; s/border-zinc-700/border-border/g; s/text-zinc-400/text-muted-foreground/g; s/text-zinc-500/text-muted-foreground\/80/g; s/text-zinc-300/text-foreground\/80/g' <PATH_FILE>
```
(SESUAIKAN daftar sed dengan temuan langkah 1 — jangan jalankan sed untuk kelas yang tidak ada di file.)
**Langkah 4 — Pastikan 0 sisa** (kecuali pengecualian):
```bash
grep -cE "(bg|text|border)-(zinc|slate|gray)-(300|400|500|600|700|800|900)" <PATH_FILE>   # target: 0
```
**Langkah 5 — Lint file** (tool lint JS pada path file; harus 0 error baru).
**Langkah 6 — Cek compile:**
```bash
tail -5 /var/log/supervisor/frontend.out.log   # harus ada "compiled successfully" terbaru tanpa ERROR
```
**Langkah 7 — Verifikasi visual 2 tema** (Playwright/screenshot): login → `window.location.hash='<module-id>'` → reload → screenshot; lalu toggle tema (tombol theme di TopBar, atau `document.documentElement.classList.toggle('dark')`) → screenshot kedua. **LULUS bila**: di tema terang TIDAK ada kartu hitam/teks tak terbaca; di tema gelap tetap normal.
**Langkah 8 — Jika modul tidak punya id di nav** (komponen dipakai di dalam modul lain): verifikasi lewat modul induknya (cari pemakainya: `grep -rn "<NamaKomponen" src/`).
**Langkah 9 — Tulis laporan** (template 2.9) → append ke `/app/memory/FINAL_REPAIR_LOG.md`.

### 2.9 TEMPLATE LAPORAN (WAJIB per modul — bahasa Indonesia)
```markdown
## FINAL REPAIR MODUL <NamaModul / module-id>
- File: <path>
- Kemunculan awal: <angka dari inventaris> | Sisa setelah fix: 0 (pengecualian: <daftar/nihil>)
- Kelas diganti: <ringkas, mis. bg-zinc-900→bg-card ×11, text-zinc-400→text-muted-foreground ×17>
- PERLU-KEPUTUSAN: <kelas yang tak ada di tabel 1.2, atau nihil>
- Verifikasi: compile OK ✅ | render terang OK ✅ | render gelap OK ✅ (screenshot: <path/tmp>)
- Status: SELESAI / SKIP by-design (alasan)
```

---

# BAGIAN 3 — INVENTARIS RESMI RC-UI-01 (113 file · ±629 kemunculan · basis grep 2026-07-02)

> Kolom Wave = urutan pengerjaan. Kerjakan U1 dulu (habiskan), lalu U2, dst. `LiveSessionAnalyticsDashboard.jsx` sudah ✅ SELESAI (contoh acuan).

> Regenerasi inventaris kapan pun: lihat APPENDIX H.


| # | File (relatif `src/components/`) | Kemunculan | Wave | Status |
|---|---|---|---|---|
| 1 | `erp/PayrollDashboardModule.jsx` | 50 | U3 (HR/Payroll) |  |
| 2 | `erp/ProcurementRequestModule.jsx` | 49 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 3 | `erp/ExecutiveReportModule.jsx` | 49 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 4 | `erp/marketing/MarketingWebhooksModule.jsx` | 45 | U2 (Marketing/Toko) |  |
| 5 | `erp/CapacityPlanningModule.jsx` | 43 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 6 | `creator/CreatorPortalApp.jsx` | 42 | U4 (Produksi/WMS/lainnya) |  |
| 7 | `erp/MultiLevelApprovalModule.jsx` | 35 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 8 | `erp/WMSFabricRollsModule.jsx` | 26 | U4 (Produksi/WMS/lainnya) |  |
| 9 | `erp/WMSCMTDispatchesModule.jsx` | 25 | U4 (Produksi/WMS/lainnya) |  |
| 10 | `erp/scanner/UniversalScanPortal.jsx` | 23 | U0-SKIP (by-design gelap — verifikasi saja) |  |
| 11 | `erp/WMSOpnameEnhancedModule.jsx` | 21 | U4 (Produksi/WMS/lainnya) |  |
| 12 | `erp/ProductionMaterialReturnsModule.jsx` | 20 | U4 (Produksi/WMS/lainnya) |  |
| 13 | `erp/WMSDeliveryNotesModule.jsx` | 18 | U4 (Produksi/WMS/lainnya) |  |
| 14 | `erp/WMSModule.jsx` | 12 | U4 (Produksi/WMS/lainnya) |  |
| 15 | `erp/CuttingProcessModule.jsx` | 6 | U4 (Produksi/WMS/lainnya) |  |
| 16 | `erp/TokoChannelManagerModule.jsx` | 5 | U2 (Marketing/Toko) |  |
| 17 | `erp/ShopFloorTV.jsx` | 5 | U0-SKIP (by-design gelap — verifikasi saja) |  |
| 18 | `erp/HROnboardingModule.jsx` | 5 | U3 (HR/Payroll) |  |
| 19 | `erp/HRATSModule.jsx` | 5 | U3 (HR/Payroll) |  |
| 20 | `erp/marketing/AdvancedAIModule.jsx` | 4 | U2 (Marketing/Toko) |  |
| 21 | `erp/RahazaARInvoicesModule.jsx` | 4 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 22 | `erp/EmployeeTravelSettlementModule.jsx` | 4 | U3 (HR/Payroll) |  |
| 23 | `erp/marketing/MarketingOverviewDashboard.jsx` | 3 | U2 (Marketing/Toko) |  |
| 24 | `erp/marketing/ContentCalendarModule.jsx` | 3 | U2 (Marketing/Toko) |  |
| 25 | `erp/marketing/ComplaintsManagementModule.jsx` | 3 | U2 (Marketing/Toko) |  |
| 26 | `erp/RnDStyleDetailPage.jsx` | 3 | U4 (Produksi/WMS/lainnya) |  |
| 27 | `erp/PurchaseOrderModule.jsx` | 3 | U4 (Produksi/WMS/lainnya) |  |
| 28 | `erp/PDFConfigModule.jsx` | 3 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 29 | `erp/FinanceKasbonModule.jsx` | 3 | U3 (HR/Payroll) |  |
| 30 | `erp/EmployeeLoansModule.jsx` | 3 | U3 (HR/Payroll) |  |
| 31 | `client/ClientSamples.jsx` | 3 | U5 (portal eksternal — terakhir) |  |
| 32 | `erp/portal/PeerFeedbackModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 33 | `erp/marketing/SampleDeliveryModule.jsx` | 2 | U2 (Marketing/Toko) |  |
| 34 | `erp/marketing/RatingReviewModule.jsx` | 2 | U2 (Marketing/Toko) |  |
| 35 | `erp/marketing/ProductLaunchModule.jsx` | 2 | U2 (Marketing/Toko) |  |
| 36 | `erp/marketing/MarketingIntegrationSettings.jsx` | 2 | U2 (Marketing/Toko) |  |
| 37 | `erp/marketing/DiscountCampaignModule.jsx` | 2 | U2 (Marketing/Toko) |  |
| 38 | `erp/marketing/AccountDetailPage.jsx` | 2 | U2 (Marketing/Toko) |  |
| 39 | `erp/_archive/HelpGuideModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 40 | `erp/SupplierScorecardModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 41 | `erp/RnDSamplesTab.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 42 | `erp/RnDPortalDashboard.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 43 | `erp/RahazaAttendanceApprovalModule.jsx` | 2 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 44 | `erp/MarketingAfterSalesHub.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 45 | `erp/KasbonStaffModule.jsx` | 2 | U3 (HR/Payroll) |  |
| 46 | `erp/KREATORRequestModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 47 | `erp/KOLCreatorModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 48 | `erp/HROrgChartModule.jsx` | 2 | U3 (HR/Payroll) |  |
| 49 | `erp/HRLMSModule.jsx` | 2 | U3 (HR/Payroll) |  |
| 50 | `erp/HRKasbonModule.jsx` | 2 | U3 (HR/Payroll) |  |
| 51 | `erp/FGStockMatrixView.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 52 | `erp/BadDebtWriteOffModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 53 | `erp/BackupRestoreModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 54 | `erp/AccrualsModule.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 55 | `erp/AccessoryRequestInbox.jsx` | 2 | U4 (Produksi/WMS/lainnya) |  |
| 56 | `vendor-cmt/VendorCMTPortalApp.jsx` | 1 | U5 (portal eksternal — terakhir) |  |
| 57 | `ui/sheet.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 58 | `ui/drawer.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 59 | `ui/dialog.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 60 | `ui/alert-dialog.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 61 | `livehost/LiveHostPortalApp.jsx` | 1 | U5 (portal eksternal — terakhir) |  |
| 62 | `erp/userGuide/ModuleTour.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 63 | `erp/scanner/UniversalScanner.jsx` | 1 | U0-SKIP (by-design gelap — verifikasi saja) |  |
| 64 | `erp/marketing/live-host/Badges.jsx` | 1 | U2 (Marketing/Toko) |  |
| 65 | `erp/marketing/ReturnsRefundsModule.jsx` | 1 | U2 (Marketing/Toko) |  |
| 66 | `erp/marketing/MarketingAIInsightsDashboard.jsx` | 1 | U2 (Marketing/Toko) |  |
| 67 | `erp/marketing/ImportCenterPage.jsx` | 1 | U2 (Marketing/Toko) |  |
| 68 | `erp/marketing/DailyReportModule.jsx` | 1 | U2 (Marketing/Toko) |  |
| 69 | `erp/marketing/AccountBadge.jsx` | 1 | U2 (Marketing/Toko) |  |
| 70 | `erp/collaboration/learning/VideoPlayer.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 71 | `erp/asset/components/PMAlertCard.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 72 | `erp/_archive/StyleMasterModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 73 | `erp/_archive/POWorkflowIndicator.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 74 | `erp/WarehouseDashboard.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 75 | `erp/TaskTemplatesModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 76 | `erp/SetupWizard.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 77 | `erp/RoleManagementModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 78 | `erp/RnDVariantModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 79 | `erp/RnDTechPackModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 80 | `erp/RnDRevisionsTab.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 81 | `erp/RnDPatternModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 82 | `erp/RnDMaterialsTab.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 83 | `erp/RahazaShipmentsModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 84 | `erp/RahazaShiftHandoverModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 85 | `erp/RahazaPayrollProfilesModule.jsx` | 1 | U3 (HR/Payroll) |  |
| 86 | `erp/RahazaMaterialIssueModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 87 | `erp/RahazaLeaveModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 88 | `erp/RahazaJournalListModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 89 | `erp/RahazaExpensesModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 90 | `erp/RahazaCostCentersModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 91 | `erp/RahazaCashAccountsModule.jsx` | 1 | U1 (Eksekutif/Finance/Approval — dampak visual terbesar) |  |
| 92 | `erp/PurchaseDiscountModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 93 | `erp/ProductionWorkspaceMaster.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 94 | `erp/PortalSayaProfile.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 95 | `erp/PortalSayaPayslip.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 96 | `erp/PortalSayaCuti.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 97 | `erp/MaklonSampleManagement.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 98 | `erp/KPIPortalModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 99 | `erp/InventoryScrapModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 100 | `erp/IntegrationSettingsModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 101 | `erp/ImportExportPanel.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 102 | `erp/CompanySettingsModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 103 | `erp/CMTComponentRequestModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 104 | `erp/BuyersModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 105 | `erp/AuditHistoryDrawer.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 106 | `erp/AssetDisposalModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 107 | `erp/AssetDepreciationModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 108 | `erp/AccountManagementModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 109 | `erp/AccountCard.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 110 | `erp/AIInsightsModule.jsx` | 1 | U4 (Produksi/WMS/lainnya) |  |
| 111 | `client/ClientOrders.jsx` | 1 | U5 (portal eksternal — terakhir) |  |
| 112 | `client/ClientInvoices.jsx` | 1 | U5 (portal eksternal — terakhir) |  |
| 113 | `client/ClientChangePasswordDialog.jsx` | 1 | U5 (portal eksternal — terakhir) |  |

---

# BAGIAN 4 — RC-UI-02: REVIEW RENDER SEMUA MODUL (±309 id)

### 4.1 Dapatkan daftar id modul (SATU-SATUNYA sumber)
```bash
cd /app/frontend/src/components/erp
grep -oE "^  '[a-z0-9-]+':" moduleRegistry.js | tr -d " ':" | sort > /tmp/module_ids.txt
wc -l /tmp/module_ids.txt
```
### 4.2 Prosedur per modul (batch 15–20 modul per sesi Playwright)
1. Login sekali (admin@garment.com / Admin@123).
2. Untuk tiap id: `window.location.hash='<id>'` → reload → tunggu 6–8 dtk → baca `document.body.innerText`.
3. Klasifikasikan (WAJIB salah satu):
   - **OK-DATA**: render + ada angka/baris data.
   - **OK-EMPTY-JUJUR**: render + empty-state dgn pesan jelas (bukan error). SAH utk modul dormant (lihat Part 4 BAGIAN 3 — JANGAN "diperbaiki").
   - **REDIRECT-OK**: pindah ke modul target (id legacy) — catat targetnya benar.
   - **ERROR**: ada teks "Portal Error"/"Something went wrong"/console error merah/blank putih → **BUG, buat kartu perbaikan** (format: id, gejala, file komponen, akar, fix 1 baris bila jelas; kalau akar tak jelas → PERLU-KEPUTUSAN).
4. Screenshot HANYA untuk yang ERROR (hemat).
5. Laporan per batch → append `/app/memory/FINAL_REPAIR_LOG.md`:
```markdown
## RENDER REVIEW BATCH <n> (<id pertama>..<id terakhir>)
| id | Klasifikasi | Catatan |
```
### 4.3 Aturan
- JANGAN klik tombol tulis (Create/Delete/Approve) di fase ini — fase ini READ-ONLY render.
- Modul dgn 401/403 (butuh role lain) → catat "AUTH-SCOPED", akan diuji di BAGIAN 5 RBAC.
- Selesai semua batch → rekap total: OK-DATA / OK-EMPTY / REDIRECT / ERROR / AUTH-SCOPED. Target akhir: **ERROR = 0**.

---

# BAGIAN 5 — RC-FLOW: CAKUPAN WRITE-FLOW + RBAC (di luar Part 1–4)

> Part 1–4 sudah menguji GET menyeluruh + ±5 write-flow. Bagian ini menutup sisanya. Data BOLEH rusak (semua seed; re-seed kapan pun: `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo` sebagai admin).

### 5.1 Matrix login RBAC (password semua: Dewi@123, admin: Admin@123)
| Akun | Role | Portal yang diuji |
|---|---|---|
| admin@garment.com | superadmin | semua (baseline) |
| hr@dewiaditya.id | hr | HR/SDM + Portal Saya |
| finance@dewiaditya.id | accounting | Finance |
| spv@dewiaditya.id | supervisor_produksi | Produksi |
| gudang@dewiaditya.id | admin_gudang | Warehouse/WMS |
| maklon@dewiaditya.id | admin_maklon | Maklon |

### 5.2 Daftar write-flow WAJIB per domain (uji end-to-end via API; 1 flow = create→(submit→approve)→verifikasi DB/GET→cleanup bila mudah)
| Domain | Flow (endpoint inti) | Bukti LULUS |
|---|---|---|
| Finance AR | buat AR invoice → `POST /api/rahaza/ar-invoices` → payment `POST .../{id}/payment` | invoice paid; `rahaza_cash_movements` +1; JE `source_module=ar_payment` muncul |
| Finance AP | buat AP invoice → payment | idem sisi AP |
| Expense | claim: create→submit→approve→disburse | `gl_je_number` pola `JE-YYYYMMDD-####`; JE ada di `rahaza_journal_entries` |
| Travel | request: create→approve→pay-advance; settlement: create→submit→post | JE travel_advance & travel_settlement muncul |
| Payroll | run: create→attendance-sync→finalize | payslips terisi `days_worked>0`, `overtime_hours_synced` sesuai `rahaza_overtime_requests` |
| Leave | request cuti: create→approve | `rahaza_leave_balances.used` bertambah |
| Attendance | clock-in/out (`/api/rahaza/attendance/*`) | event baru di `rahaza_attendance_events` |
| Produksi WO | WO create→release→WIP output event→QC event→complete | `completed_qty` naik; muncul di dashboard throughput |
| Cutting/Bundle | cutting request→batch→bundle print | bundle bertambah utk WO |
| WMS | GRN receive→putaway→stock naik; delivery note create→issue | `rahaza_material_stock`/`wh_delivery_notes` berubah |
| Opname2 | buat sesi→hitung→approve | selisih tercatat; stok ter-adjust |
| Marketing | input sesi live harian; creator session; order marketplace | angka masuk `live/summary` & leaderboard |
| Toko | order create→pack→ship | status order berubah |
| Maklon | PO maklon create→progress→invoice | `dewi_maklon_invoices` bertambah |
| RnD | style→sample request→approve (SUDAH teruji Part 4 B2 — cukup smoke) | — |
| Approval multilevel | buat chain → ajukan request → approve berjenjang | status chain berjalan |
| HR Shifts | create shift→assign→employee on-date (SUDAH teruji #17 — smoke) | — |
| Onboarding | buat checklist dari template→toggle task done | progress_pct berubah |
| Notifikasi | aksi yang memicu notif (submit claim) | dok baru di `notifications` |
| Portal Saya | update todo/reminder/note | tersimpan & tampil ulang |
### Aturan RBAC: ulangi 1–2 flow inti per portal memakai akun role terkait — LULUS bila role berwenang bisa & role lain ditolak (403), TANPA 500.
### Setiap bug ditemukan → tulis kartu `RC-FLOW-<domain>-<n>` (format kartu Part 1: file:baris, akar, langkah, verifikasi) di FINAL_REPAIR_LOG — **perbaiki backend HANYA lewat kartu ini**.

---

# BAGIAN 6 — URUTAN EKSEKUSI, DoD & ROLLBACK

**Urutan**: RC-UI-01 Wave U1→U2→U3→U4→U5 (BAGIAN 3) → RC-UI-02 (BAGIAN 4) → RC-FLOW (BAGIAN 5).
**Definition of Done PART 5:**
- [ ] Inventaris BAGIAN 3: semua baris berstatus SELESAI / SKIP by-design (dgn alasan) — regenerasi grep APPENDIX H = 0 file baru.
- [ ] RC-UI-02: 100% id modul terklasifikasi, ERROR = 0.
- [ ] RC-FLOW: semua baris tabel 5.2 LULUS; RBAC per portal LULUS; 0 kartu RC-FLOW terbuka.
- [ ] `yarn build` produksi sukses; testing agent frontend hijau utk sampel tiap wave.
- [ ] `/app/memory/FINAL_REPAIR_LOG.md` berisi laporan per modul lengkap.
**Rollback**: per file via git (`git checkout -- <file>`); tiap wave dimulai dari working tree bersih.

# APPENDIX H — PERINTAH REGENERASI INVENTARIS (kapan pun)
```bash
cd /app/frontend/src/components
grep -rcE "bg-(zinc|slate|gray|neutral|stone)-(700|800|900|950)|bg-black\b|border-(zinc|slate|gray)-(600|700|800)|text-(zinc|slate|gray)-(300|400|500|600)" --include="*.jsx" . 2>/dev/null | awk -F: '$2>0 {print $1"|"$2}' | sort -t'|' -k2 -rn
```


---

# BAGIAN 7 — RC-UI-03: STANDAR PAGINASI (arahan user: 10 baris)

### 7.1 Aturan
1. **SEMUA tabel/daftar** yang bisa berisi >10 baris WAJIB paginasi **10 baris per halaman** (default), dengan kontrol: «Prev · Page x/y · Next» + info "Menampilkan a–b dari N".
2. Komponen paginasi WAJIB SATU sumber: buat/pakai `src/components/ui/pagination-lite.jsx` (jika belum ada, buat sekali — props: `page, totalPages, total, onPageChange` — pakai token tema, BUKAN warna hardcode).
3. Backend TIDAK diubah: gunakan param `limit=10&skip/page` bila endpoint mendukung; jika tidak, paginasi client-side (slice) — catat di laporan mana yang client-side.
4. Larangan: `limit=100/500` tampil sekaligus tanpa paginasi; dropdown "rows per page" beragam (25/50) — seragamkan default 10 (boleh ada pilihan 10/25/50, default tetap 10).

### 7.2 Cara inventarisasi (jalankan, hasil = daftar kerja)
```bash
cd /app/frontend/src/components
# kandidat daftar TANPA paginasi: ada .map( atas array besar + tidak ada kata 'page'
grep -rlE "\.map\(" --include="*.jsx" erp | xargs grep -LiE "page|pagina" | sort > /tmp/pagination_todo.txt
wc -l /tmp/pagination_todo.txt
```
Lalu per file: buka, cari tabel utama (`<table`/`TableBody`/list card), terapkan pola:
```jsx
const [page, setPage] = useState(1);
const PAGE_SIZE = 10;
const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
const pagedRows = rows.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE);
// render pagedRows; reset setPage(1) saat filter/search berubah
```
Verifikasi: isi data > 10 → tabel menampilkan tepat 10 + kontrol berfungsi. Laporkan per modul (template 2.9, tambah baris "Paginasi: ✅ 10/hal").

---

# BAGIAN 8 — RC-IA-01: AUDIT INFORMATION ARCHITECTURE (struktur menu & fitur beririsan)

> Pemicu (temuan user, dijadikan KASUS ACUAN): fitur serupa terpencar — **Garment WMS → "Stock Opname"**, **Operasional Gudang → "Penyesuaian Gudang"**, **Inventory → "Unified Inventory Viewer"** — membingungkan, seharusnya satu rumpun. Ditambah bug menu-duplikat portal Aset (3 menu → 1 komponen tanpa pembeda; SUDAH diperbaiki sebagai contoh: lihat 8.4).

### 8.1 Deteksi WAJIB #1 — beberapa menu → komponen sama (bug kelas "pindah menu tak ada perubahan")
```bash
cd /app/frontend/src/components/erp
python3 - <<'PY'
import re, collections
s = open('moduleRegistry.js').read()
pairs = re.findall(r"'([a-z0-9-]+)':\s*(?:lazy\(\(\) => import\('(\./[^']+)'\)\)|([A-Za-z]+))", s)
by_target = collections.defaultdict(list)
for mid, imp, comp in pairs:
    by_target[imp or comp].append(mid)
nav = open('portal-shell/portalNav.js').read()
for target, ids in sorted(by_target.items()):
    ids_in_nav = [i for i in ids if f"id: '{i}'" in nav]
    if len(ids_in_nav) > 1:
        print(f"{target}: {ids_in_nav}")
PY
```
**Aturan vonis**: >1 menu aktif → komponen sama = DUPLIKAT. Fix yang diizinkan (pilih satu): (a) beri `defaultTab` berbeda via `makeModuleWithTab` (bila komponen ber-tab — pola 8.4), (b) sisakan 1 menu + jadikan lainnya redirect, (c) PERLU-KEPUTUSAN user bila tidak jelas. **DILARANG membiarkan dua menu identik tanpa pembeda.**
Catatan sah: id redirect (makeRedirect) & hub = BUKAN duplikat.

### 8.2 Deteksi WAJIB #2 — fitur beririsan lintas seksi (kasus WMS/Gudang/Inventory)
Metode: bangun **matriks menu → modul → endpoint inti → koleksi** untuk portal `warehouse` (dan tiap portal lain):
1. Ambil semua id menu portal dari `portalNav.js` (per section/group).
2. Untuk tiap modul: `grep -oE "api/[a-z0-9/_-]+" <file> | sort -u | head` → endpoint; dari endpoint, lihat koleksi (registry di arsip: /app/docs/_archive_history/SSOT_MASTER_REPAIR_PLAN*.md BAGIAN 1).
3. Tandai **IRISAN** bila ≥2 modul di seksi BERBEDA menyentuh koleksi/urusan sama (mis. stok, opname, penyesuaian).
4. Untuk tiap irisan, tulis kartu `RC-IA-<portal>-<n>` berisi: daftar modul, apa yang tumpang tindih, usul restrukturisasi (gabung jadi hub ber-tab / pindah seksi / arsip), dan dampak.
**Kasus acuan yang WAJIB dieksekusi lebih dulu (setelah persetujuan user):**
- `RC-IA-warehouse-1`: satukan rumpun **STOK & AKURASI** dalam SATU seksi: Unified Inventory Viewer (viewer stok) + Stock Opname (opname2 SSOT) + Penyesuaian Gudang (adjustments) → usul: 1 hub `wms-stock-hub` 3 tab ATAU 1 seksi menu "Stok & Akurasi" berisi 3 menu berurutan; hapus penyebaran lintas 3 seksi. (Pilihan final = keputusan user di dokumen usulan.)
- Audit sisa portal warehouse: "Operasional Gudang" vs "Advanced WMS" vs "Garment WMS" — petakan SEMUA menu; setiap fitur hampir-sama-beda-tipis → usulkan merge/arsip; target: setiap urusan punya SATU pintu.
### 8.3 Deliverable RC-IA-01
Dokumen `/app/IA_RESTRUCTURE_PROPOSAL.md`: per portal → tabel [menu sekarang | modul | endpoint/koleksi | masalah | usulan]. **JANGAN eksekusi perombakan nav sebelum user menyetujui dokumen ini** (kecuali bug kelas 8.1 yang boleh langsung diperbaiki karena jelas rusak).
### 8.4 Contoh fix menu-duplikat (SUDAH DIKERJAKAN — acuan)
Portal Aset: `asset-dashboard`/`asset-list`/`asset-procurement` dulu → `AssetManagementPortal` tanpa pembeda. Fix: komponen menerima prop `defaultTab` (`useState(defaultTab || 'dashboard')`) + registry pakai `makeModuleWithTab(AssetManagementPortalLazy, 'dashboard'|'assets'|'procurement')`. Pindah menu kini berpindah tab.

### 8.5 Update DoD PART 5 (menambah BAGIAN 6)
- [ ] Deteksi 8.1 = 0 duplikat tersisa di semua portal.
- [ ] Matriks 8.2 selesai utk 12 portal; semua kartu RC-IA tercatat di `IA_RESTRUCTURE_PROPOSAL.md`.
- [ ] RC-UI-03: `/tmp/pagination_todo.txt` habis (semua tabel 10/hal atau tercatat pengecualian dgn alasan).

---

# BAGIAN 9 — KOREKSI METODOLOGI (temuan user: audit BAGIAN 8 v1 TERLALU DANGKAL)

> **Pengakuan**: deteksi 8.1/8.2 hanya membaca level MENU (nav+registry) — TIDAK masuk ke TAB INTERNAL tiap halaman. Akibatnya duplikat "Stok Opname" (tab di dalam WMS Scanner vs menu resmi Opname Stok) LOLOS. Bug itu sudah diperbaiki (tab dihapus → kartu pengarah; lihat FINAL_REPAIR_LOG). Aturan di bawah WAJIB agar tidak terulang.

### 9.1 Deteksi WAJIB #3 — DUPLIKAT LEVEL-TAB (halaman-per-halaman)
Untuk SETIAP modul di registry (bukan hanya menu):
```bash
cd /app/frontend/src/components
# 1) daftar semua label tab per file:
grep -rnE "TabsTrigger|\{ id: '[a-z0-9_-]+', label:" erp/<FILE>.jsx | head -30
# 2) daftar endpoint yang dipakai file:
grep -oE "api/[a-z0-9/_${}-]+" erp/<FILE>.jsx | sort -u
```
Bangun tabel global `fitur → [semua lokasi: portal>menu>tab]`. **Vonis DUPLIKAT** bila 1 fitur (mis. opname, adjustment, receiving, PO, scan) muncul di ≥2 lokasi TANPA alasan tertulis. Fix yang diizinkan: hapus lokasi non-resmi + kartu pengarah ke lokasi RESMI (pola RC-IA-warehouse-0), atau minta keputusan user.
Prioritas periksa (irisan diketahui): WMSModule (tabs: Dashboard/Struktur/Satuan/Receiving/Opname[SUDAH]/Audit/Posisi) vs menu Receiving GRN (`wh-receiving`) vs Put-Away vs Unified Viewer — cek satu-per-satu apakah "Receiving/Scan" & "Posisi & Search" di WMSModule juga dobel pintu dgn menu lain.

### 9.2 WAJIB — ANALISIS FLOW KRITIS + UX (per flow, halaman-per-halaman, deep reasoning)
Untuk 10 flow kritis: **PO→GRN→PutAway→Stok**, **Opname→Adjust**, **WO→Cutting→Bundle→Sewing→QC→FG**, **FG→SuratJalan/DispatchCMT**, **Order Toko→Fulfillment**, **Expense claim→GL**, **Payroll**, **Cuti**, **AR invoice→payment**, **Maklon PO→invoice**:
1. Jalankan flow NYATA di UI klik-per-klik (bukan hanya API); catat: berapa klik, pindah menu berapa kali, di mana user harus "tahu sendiri" langkah berikutnya.
2. Nilai per halaman: (a) apakah CTA langkah-berikut ada di halaman hasil? (b) apakah istilah konsisten? (c) apakah data yang baru dibuat langsung terlihat tanpa refresh? (d) empty-state memberi arah?
3. Tulis kartu `RC-FLOW-UX-<n>` per cacat: lokasi persis, bukti (screenshot), akar, usulan fix eksplisit (komponen+perubahan), skor dampak (blokir/bikin-bingung/kosmetik).
4. Output: `/app/FLOW_UX_AUDIT.md` — per flow: diagram langkah aktual vs ideal + daftar kartu. Redesign menyeluruh DIBOLEHKAN user — usulkan berani (kurangi overwhelm: target ≤7 menu per seksi, 1 pintu per fitur).


### 9.3 EKSEKUSI §9.1 (Session #28) — sapu 4 portal + keputusan T-1..T-5
> Menindaklanjuti §9.1: portal yang belum disapu level-tab (Produksi/Finance/HR/Marketing) kini DIJALANKAN read-only. Skrip regenerable dipermanenkan di **`/app/scripts/tab_audit.py`** (refinasi: hanya TAB fungsional nyata — `TabsTrigger` + array hub `{key,label,Component}`; vonis kandidat murni dari LABEL tab, endpoint sbagai konteks). Dump: `/app/docs/tab_audit_session28_result.json`.

**Hasil 4 portal (menu ter-scan: Produksi 35 · Finance 36 · HR 30 · Marketing/Toko 25):**
- `attendance` → `hr-attendance-hub` vs `hr-inbox` = **T-4** (by-design + cross-link, sudah dieksekusi).
- `payroll` → `hr-admin` "Struktur Gaji" (master) vs `hr-inbox` "Gaji" (approval inbox) = **by-design** (unified-inbox).
- `asset` → `fin-acctg-adjust-hub` (aset tetap/GL) vs `hr-assets` (penugasan aset karyawan) = **domain berbeda**.
- `live` → `marketing-live-hub` (operasi live) vs `marketing-sales` "Live Revenue" (analitik) = **by-design**.
- **VONIS: 0 duplikat fungsional wajib-fix.** Konsisten dgn IA §7.3.

**Keputusan user 5 kandidat §7.2 (dieksekusi Session #28, detail di `IA_RESTRUCTURE_PROPOSAL.md` BAGIAN 8):**
- **T-1=B** (opname aksesoris = domain resmi terpisah, doc-only, tanpa ubah backend).
- **T-2=A** (`scope` prop `AccessoryRequestInbox`: RnD = read-only monitor).
- **T-3=A** (`scope` prop ringan `KREATORRequestModule`: marketing vs rnd default-filter + label; sekaligus perbaiki latent bug prop `currentUser` yg tak pernah dioper).
- **T-4=by-design + cross-link** (`hr-inbox` → `hr-attendance-hub` tab approval).
- **T-5=by-design + perjelas label** (3 label "Workspace" dibedakan tegas).

> Semua perubahan Session #28 = FRONTEND (scope/label/cross-link) + dokumentasi. **Tidak ada perubahan backend/SSOT** (patuh §8.3: perubahan IA lintas-portal/backend butuh persetujuan eksplisit).
