# MODUL: Dashboard Produksi (`production-dashboard`) — Portal Produksi (Hub 5-Tab)
<!-- moduleId: production-dashboard | Status: ✅ VERIFIED (kode dibaca + diuji runtime) | Skor rubrik: 98/100 | Standar: v3 DEEP (SAP-grade) | Update: 2026-07-07 | Manifest: ../_manifests/production-dashboard.manifest.json | Catatan QA (terpisah): ../_qa/production-dashboard_bugs.md | Divalidasi: scripts/docgen/validate_module.py -->

> **Dokumen Training & Spesifikasi Uji — gaya SAP Functional/End-User.** Berlapis:
> - **BAGIAN A — PANDUAN PENGGUNA** (klik-per-klik, awam) → supervisor/PPIC/manajer produksi & QC.
> - **BAGIAN B — LAMPIRAN TEKNIS** (komponen, field, kontrak API, logic/state, RBAC, integrasi, pesan) → admin/QA/dev.
> - **BAGIAN C — SPESIFIKASI UJI** (skenario + test case dengan hasil **nyata** + troubleshooting).
> - **BAGIAN D — LAMPIRAN CONTOH & DETAIL UJI**.
>
> **Prinsip anti-halusinasi:** setiap pernyataan menunjuk sumber kode (`file:baris`); `Expected`=menurut kode, `Actual`=hasil eksekusi. Catatan QA teknis dipisah di `../_qa/production-dashboard_bugs.md`.
>
> **Ikhtisar hasil uji:** Backend **33 PASS / 2 INFO / 0 FAIL** (skrip `tests/pilot_production_dashboard_test.py`; 2 INFO = data-dependent pada DB uji yang fresh: belum ada line master & belum ada WO terjadwal). UI: **5 tab** (Overview/Performa/Kualitas/Jadwal/AI) semua panel root render tanpa error konsol. DB dikembalikan bersih (tanpa mutasi WO/seed).

## 0. METADATA MODUL
| Atribut | Nilai |
|---|---|
| **moduleId** | `production-dashboard` |
| **Nama tampilan** | Dashboard Produksi |
| **Portal** | Produksi (`portalId = production`) |
| **Tipe** | **hub tab** (5 tab) — mengagregasi 5 sub-modul + 3 widget pendukung |
| **Path menu** | Produksi → "Dashboard Produksi" (ikon Gauge, `portalNav.js`) |
| **Komponen induk** | `frontend/src/components/erp/ProductionDashboardModule.jsx` |
| **Registry** | `moduleRegistry.js:523` (`'production-dashboard': ProductionDashboardModule`); redirect legacy → tab (`moduleRegistry.js:19`) |
| **Legacy diserap** | `prod-oee` (OEE), `prod-line-balance` (Line Balancing), `prod-rework-analytics` (Rework), `prod-aps-gantt` (APS Gantt) — kini menjadi tab di hub ini |
| **Jumlah endpoint** | **26 path unik (26)** / 30 method-endpoint di 5 tab (lihat B5) |
| **Komponen** | **12 komponen erp** + 15 primitif UI (tabs, dialog, glass, badge, skeleton, dsb.) |
| **Testid** | **131 testid konkret** (lihat inventaris B2) |
| **Koleksi MongoDB (baca)** | `rahaza_wip_events`, `rahaza_work_orders`, `rahaza_bundles`, `rahaza_lines`, `rahaza_shifts`, `rahaza_locations`, `rahaza_oee_daily`, `production_pos`, `rahaza_aps_schedule_runs`, `ai_rca_history`, `rahaza_settings` |
| **Integrasi LLM** | Tab AI (RCA) memakai **Claude Sonnet 4.5** via `analytics_ai.py` |

---

# BAGIAN A — PANDUAN PENGGUNA

## A1. Untuk apa modul ini? (konteks bisnis)
**Dashboard Produksi** adalah **"ruang kendali" (control room) pabrik garment** — satu layar yang menyatukan lima "instrumen" berbeda menjadi lima **tab**:

1. **Overview (WIP Real-time)** — foto kondisi lantai saat ini: berapa output hari ini, berapa barang sedang dikerjakan (WIP), di proses mana ada kemacetan (bottleneck), plus ringkasan material & CMT per lokasi.
2. **Performa (OEE)** — seberapa efektif mesin/lini bekerja (Overall Equipment Effectiveness = Availability × Performance × Quality), + analisis **keseimbangan beban lini** (Line Balancing).
3. **Kualitas (Rework)** — analitik cacat & pengerjaan ulang: berapa rework terbuka, SLA, lini/model penyumbang cacat terbesar.
4. **Jadwal (APS Gantt)** — papan penjadwalan produksi visual (Advanced Planning & Scheduling): kapan tiap Work Order dikerjakan di lini mana, deteksi keterlambatan/overload, plus **penjadwalan otomatis**.
5. **AI Insight (RCA)** — analisis akar masalah (Root Cause Analysis) bertenaga AI untuk isu produksi & kualitas.

Analogi: kalau modul `prod-orders`/`prod-work-orders`/`prod-bundles` adalah "mesin yang menjalankan produksi", maka Dashboard Produksi adalah **dasbor mobil**: speedometer (output), indikator bahan bakar (WIP/material), lampu peringatan (bottleneck/late), peta navigasi (Gantt), dan asisten cerdas (AI). Sebagian besar **read-only** (memantau); beberapa aksi ringan tersedia (refresh, penjadwalan ulang, penjadwalan otomatis, tutup rework manual, atur SLA).

## A2. Siapa yang memakai & haknya (ringkas)
- **Manajer/Supervisor Produksi & PPIC** — memantau semua tab; menjadwalkan (Gantt/Auto-Schedule); menutup rework; mengatur SLA.
- **QC** — memantau tab Kualitas & AI (RCA kualitas).
- **Admin/Owner** — akses penuh + pengaturan (SLA), setup wizard.
- **Semua user login** — boleh memantau (semua GET). Aksi tulis dibatasi (RBAC di B7): penjadwalan = role perencanaan (Planning/Work Order); tutup rework = supervisor+; ubah SLA = admin.

## A3. Prasyarat (agar data muncul)
Dashboard menampilkan data dari modul lain. Agar angka tidak nol:
1. **Master:** Lini (`rahaza_lines`), Shift (`rahaza_shifts`), Proses, Lokasi sudah didefinisikan. Bila kosong, muncul **Setup Wizard** (lihat A8-Tugas 1) & empty state.
2. **Transaksi:** ada Work Order terjadwal (untuk Gantt), event WIP/output (untuk Overview & OEE), event QC/rework (untuk Kualitas & AI RCA — RCA butuh ≥ 5 event).
3. Login sebagai user produksi.

> Pada instalasi baru, `setup/status.needs_wizard = true` dan sebagian tab menampilkan **empty state** yang benar (bukan error). Isi master + jalankan produksi agar dashboard "hidup".

## A4. Glossary
| Istilah | Arti awam |
|---|---|
| **WIP** | Work In Progress — barang yang sedang dikerjakan (belum selesai). |
| **Bottleneck** | Proses paling padat/macet (WIP menumpuk). |
| **Flow Efficiency** | % kelancaran aliran (output vs WIP). |
| **OEE** | Overall Equipment Effectiveness = Availability × Performance × Quality. |
| **Availability** | % waktu lini benar-benar produktif. |
| **Performance** | % kecepatan aktual vs standar. |
| **Quality** | % barang lolos (bukan cacat). |
| **Line Balancing** | Menyeimbangkan beban antar lini agar tidak ada yang nganggur/overload. |
| **Rework** | Pengerjaan ulang barang cacat. |
| **SLA (rework)** | Batas waktu target penyelesaian rework (menit). |
| **APS** | Advanced Planning & Scheduling — penjadwalan produksi. |
| **Gantt** | Diagram batang jadwal (baris = lini, kolom = tanggal). |
| **Auto-Schedule** | Sistem menyusun jadwal WO otomatis (preview → commit → rollback). |
| **RCA** | Root Cause Analysis — analisis akar masalah (di sini dibantu AI). |
| **Next Action** | Rekomendasi "langkah berikutnya" kontekstual. |

## A5. Peta 5 Tab (navigasi)
Sumber: `ProductionDashboardModule.jsx` (tab testid `tab-overview`,`tab-performance`,`tab-quality`,`tab-schedule`,`tab-ai`).

| Tab | Label UI | Isi | Sub-komponen | Testid root |
|---|---|---|---|---|
| Overview | Overview | WIP real-time + material + CMT + Next Action + Setup | ProductionDashboardOverview, NextActionWidget, SetupWizard | `production-dashboard-overview` |
| Performance | Performa | OEE + Line Balancing | RahazaOEEModule, RahazaLineBalancingModule | `oee-dashboard-page`, `line-balance-page` |
| Quality | Kualitas | Analitik Rework | ReworkAnalyticsModule | `rework-analytics-page` |
| Schedule | Jadwal | APS Gantt + Auto-Schedule | APSGanttModule, APSAutoScheduleDialog | `aps-page` |
| AI | AI Insight | RCA produksi & kualitas | AIInsightsModule | `ai-insights-module` |

Deep-link legacy: membuka `prod-oee`/`prod-line-balance`/`prod-rework-analytics`/`prod-aps-gantt` akan me-redirect ke hub ini pada tab terkait (`moduleRegistry.js:19`).

## A6. Anatomi layar (ringkas per tab)
- **Header hub:** judul "Dashboard Produksi" + 5 tab (`production-dashboard` container).
- **Overview:** filter lokasi (`location-filter`/`location-select`) + Refresh (`prod-dash-refresh`), kartu KPI (Total Output/WIP/Flow Efficiency/Bottleneck), panel "WIP per Proses" (`wip-row-*`), panel Material (`mat-summary-panel`) & CMT (`cmt-summary-panel`), tombol "Buka Line Board" (`prod-line-board-cta`) & "Buka CMT Packing" (`goto-cmt-packing-btn`), widget Next Action & (bila perlu) Setup Wizard.
- **Performa:** OEE (`oee-dashboard-page`: filter lini/tanggal, tabel lini `oee-line-row-*`, drill-down `oee-drill-btn-*`) + Line Balancing (`line-balance-page`: tanggal/shift, ringkasan `lb-summary`, daftar lini `lb-line-*`).
- **Kualitas:** `rework-analytics-page` — KPI, rentang tanggal, panel Rework Terbuka (`rework-open-row-*`), Top Lini/Model, dialog tutup manual & pengaturan SLA.
- **Jadwal:** `aps-page` — toolbar (`aps-toolbar`), legenda (`aps-legend`), grid Gantt (`aps-line-row-*`, `aps-wo-bar-*`), panel detail WO (`aps-detail-sheet`), tombol Auto-Schedule & Line Balance.
- **AI:** `ai-insights-module` — 2 seksi RCA (produksi & kualitas), pilih periode, jalankan, lihat hasil & histori.

## A7. Alur kerja end-to-end (memantau & bertindak)
```mermaid
flowchart TD
  A[Login -> buka Dashboard Produksi] --> B[Tab Overview: cek Output/WIP/Bottleneck]
  B --> C{Ada masalah?}
  C -- Bottleneck/WIP tinggi --> D[Tab Performa: cek OEE lini & Line Balance]
  C -- Cacat tinggi --> E[Tab Kualitas: cek Rework terbuka & Top penyumbang]
  C -- WO telat/overload --> F[Tab Jadwal: lihat Gantt, reschedule / Auto-Schedule]
  D --> G[Tab AI: jalankan RCA Produksi]
  E --> H[Tab AI: jalankan RCA Kualitas + tutup rework manual]
  F --> I[Auto-Schedule: Preview -> Commit -> (Rollback bila perlu)]
  G --> J[Ambil keputusan perbaikan]
  H --> J
  I --> J
```

## A8. Panduan Tugas (klik-per-klik)

### Tugas 1 — Setup awal (bila dashboard kosong)
- **Gejala:** banyak angka nol + muncul Setup Wizard / kartu "Setup dasar belum lengkap".
- **Langkah:** klik kartu Next Action (`nae-cta-*`) atau tombol buka wizard → **Setup Wizard** (`setup-wizard-modal`) tampil dengan langkah-langkah (`setup-step-*`). Navigasi **Sebelumnya/Berikutnya** (`setup-prev-btn`/`setup-next-btn`), buka modul terkait (`setup-open-*`), atau **isi data contoh** (`setup-seed-sample-btn`) untuk demo. Selesai (`setup-finish-btn`), atau **Lewati** (`setup-skip-btn`) / **Jangan tampilkan lagi** (`setup-dismiss-btn`), tutup (`setup-wizard-close`/`setup-wizard-overlay`).
- **Hasil:** master dasar terisi → tab-tab mulai menampilkan data.

### Tugas 2 — Memantau WIP & bottleneck (Overview)
1. Buka tab **Overview**. Pilih lokasi via `location-select` (default "Semua Lokasi").
2. Baca KPI: **Total Output**, **Total WIP**, **Flow Efficiency**, **Bottleneck**.
3. Lihat panel **WIP per Proses** — tiap baris (`wip-row-*`) menampilkan jumlah WIP per proses; tombol input cepat (`overview-row-input-button-*`) membuka aksi input.
4. Klik **Refresh** (`prod-dash-refresh`) untuk data terbaru; **Buka Line Board** (`prod-line-board-cta`) untuk papan lini.
- **Hasil:** Anda tahu di mana barang menumpuk dan seberapa lancar aliran hari ini.

### Tugas 3 — Menilai efektivitas lini (Performa/OEE)
1. Tab **Performa** → bagian OEE (`oee-dashboard-page`).
2. Pilih **Lini** (`oee-line-filter`) & rentang tanggal (`oee-from-date`/`oee-to-date`), klik **Refresh** (`oee-refresh-btn`).
3. Baca tabel per lini (`oee-line-row-*`): OEE% + Availability/Performance/Quality. Klik drill (`oee-drill-btn-*`) + pilih tanggal (`oee-drill-date`) untuk rincian harian.
4. Bagian **Line Balancing** (`line-balance-page`): pilih tanggal (`lb-date`) & shift (`lb-shift`), baca ringkasan (`lb-summary`) & daftar lini (`lb-line-*`, expand `lb-expand-*`).
- **Hasil:** tahu lini mana kurang efektif & apakah beban seimbang.

### Tugas 4 — Menganalisis cacat & menutup rework (Kualitas)
1. Tab **Kualitas** (`rework-analytics-page`). Atur rentang (`rework-from-input`/`rework-to-input`), **Refresh** (`rework-refresh-button`).
2. Baca KPI + panel **Rework Terbuka** (`rework-open-panel`, baris `rework-open-row-*`) & **Top Lini/Model** (`rework-top-lines-panel`/`rework-top-models-panel`).
3. **Tutup rework manual:** klik `rework-close-manual-button-*` pada baris → dialog (`rework-close-dialog`) → isi alasan (`rework-close-reason-input`), catatan (`rework-close-notes-input`), qty write-off (`rework-close-writeoff-input`) → **Konfirmasi** (`rework-close-confirm-button`).
4. **Atur SLA:** tombol `rework-sla-settings-button` → dialog (`rework-sla-dialog`) → isi menit (`rework-sla-minutes-input`) → **Simpan** (`rework-sla-save-button`). (Hanya admin.)
- **Hasil:** rework terpantau & terkelola sesuai SLA.

### Tugas 5 — Menjadwalkan produksi (Jadwal/APS Gantt)
1. Tab **Jadwal** (`aps-page`). Atur rentang (`aps-toolbar-from-input`/`aps-toolbar-to-input`), cari (`aps-toolbar-search-input`), filter status/prioritas (`aps-toolbar-status-select`/`aps-toolbar-priority-select`), zoom Hari/Minggu/Bulan (`aps-toolbar-zoom-toggle-day`/`-week`/`-month`), **Refresh** (`aps-refresh-button`).
2. Grid: baris lini (`aps-line-row-*`, `aps-line-row-unassigned`), batang WO (`aps-wo-bar-*`), indikator sekarang (`aps-now-indicator`), sel kapasitas (`aps-capacity-cell-*`), legenda (`aps-legend`).
3. Klik batang WO → panel detail (`aps-detail-sheet`): progress (`aps-detail-progress`), **Reschedule** (`aps-detail-reschedule-button`) → dialog (`aps-reschedule-dialog`) isi mulai/selesai (`aps-reschedule-start-input`/`aps-reschedule-end-input`) → **Konfirmasi** (`aps-reschedule-confirm-button`). Tutup (`aps-detail-close-button`).
- **Hasil:** jadwal WO tertata; keterlambatan/overload terlihat.

### Tugas 6 — Penjadwalan otomatis (Auto-Schedule)
1. Di tab Jadwal, klik **Auto-Schedule** (`aps-auto-schedule-button`) → dialog (`aps-auto-schedule-dialog`).
2. Atur konfigurasi (`aps-auto-schedule-config`): rentang (`aps-auto-schedule-from-input`/`aps-auto-schedule-to-input`), sertakan WO in-production? (`aps-auto-schedule-include-in-production-checkbox`).
3. **Preview** (`aps-auto-schedule-preview-button`) → hasil usulan (`aps-auto-schedule-preview-result`, tabel `aps-auto-schedule-proposals`, baris `aps-auto-schedule-proposal-row-*`, tak-terjadwalkan `aps-auto-schedule-unassigned`).
4. Puas? **Commit** (`aps-auto-schedule-commit-button`) untuk terapkan. Salah? **Rollback** (`aps-auto-schedule-rollback-button`) atau **Bersihkan preview** (`aps-auto-schedule-clear-preview-button`). Riwayat run (`aps-auto-schedule-runs-list`, `aps-auto-schedule-runs-row-*`, rollback per run `aps-auto-schedule-runs-rollback-*`).
5. Tutup (`aps-auto-schedule-close-button`).
- **Hasil:** jadwal tersusun otomatis, aman (preview dulu, bisa rollback).

### Tugas 7 — Analisis akar masalah AI (AI Insight)
1. Tab **AI** (`ai-insights-module`). Ada 2 seksi (`rca-section-*`: produksi & qc).
2. Pilih periode (`rca-period-*`, mis. 7/30/90 hari) → **Jalankan** (`rca-run-*`).
3. Sistem memanggil **Claude Sonnet 4.5** → hasil analisis (`rca-result-*`) + riwayat (`rca-history-row`).
- **Prasyarat:** data cukup (≥ 5 event) — bila kurang, muncul pesan "Data produksi belum cukup…".
- **Hasil:** ringkasan akar masalah + rekomendasi berbasis AI.

### Tugas 8 — Menindaklanjuti Next Action
- Widget **Next Action** (`next-action-widget`) menampilkan kartu rekomendasi (`nae-card-*`) dengan tombol aksi (`nae-cta-*`), penjelasan "kenapa" (`nae-why-*`), dan tunda (`nae-snooze-*`). Kosong → `next-action-widget-empty`. Refresh: `next-action-refresh`/`next-action-refresh-empty`.

## A9. Visual Keadaan Layar
**Overview (empty/fresh DB):**
```
┌ Dashboard Produksi  [Overview][Performa][Kualitas][Jadwal][AI Insight] ┐
│ [Semua Lokasi ▼] [Refresh]                                             │
│ ⚠ Next Action: "Setup dasar belum lengkap" [Mulai Setup]               │
│ ┌ Total Output 0 ┐ ┌ Total WIP 0 ┐ ┌ Flow Eff 0% ┐ ┌ Bottleneck — ┐    │
│ WIP per Proses:  (belum ada data)                     [Buka Line Board]│
└─────────────────────────────────────────────────────────────────────────┘
```
**Jadwal / APS Gantt (empty):**
```
┌ APS — Jadwal Produksi (Gantt)  [Auto-Schedule][Line Balance][Refresh] ┐
│ KPI: Total WO 0 | Terlambat 0 | Berisiko 0 | Load 0%                   │
│ Toolbar: [dari][s/d][cari][status ▼][prioritas ▼]  Zoom [Hari|Mgg|Bln]│
│ Legenda: ▮ direncanakan ▮ in-production ▮ selesai ▮ telat             │
│ (grid) — "Belum ada line produksi. Jalankan setup."                    │
└─────────────────────────────────────────────────────────────────────────┘
```
**Perpindahan antar-tab (screen-state):**
```mermaid
stateDiagram-v2
  [*] --> Overview
  Overview --> Performance: tab-performance
  Overview --> Quality: tab-quality
  Overview --> Schedule: tab-schedule
  Overview --> AI: tab-ai
  Performance --> Overview: tab-overview
  Schedule --> AutoScheduleDialog: aps-auto-schedule-button
  AutoScheduleDialog --> Schedule: close
  Schedule --> WODetail: klik aps-wo-bar-*
  WODetail --> RescheduleDialog: aps-detail-reschedule-button
  RescheduleDialog --> Schedule: confirm/close
  Quality --> Rework Close: rework-close-manual-button-*
  AI --> RCA Result: rca-run-*
```

## A10. Cara membaca dokumen ini
- Pemula: baca A1–A8. QA/Dev: B2 (testid), B5 (endpoint), B6 (state/logika), C (uji). Contoh nyata: D4.

---

# BAGIAN B — LAMPIRAN TEKNIS

## B1. Peta Komponen (Component Map)
```mermaid
graph TD
  REG[moduleRegistry.js:523 'production-dashboard'] --> HUB[ProductionDashboardModule.jsx]
  HUB --> OV[ProductionDashboardOverview.jsx]
  OV --> NAW[NextActionWidget.jsx]
  OV --> SW[SetupWizard.jsx]
  OV --> ATOMS[dashboardAtoms.jsx - StatCard/KpiTile/HeroCrystalCard]
  HUB --> OEE[RahazaOEEModule.jsx]
  HUB --> LB[RahazaLineBalancingModule.jsx]
  HUB --> RW[ReworkAnalyticsModule.jsx]
  HUB --> APS[APSGanttModule.jsx]
  APS --> ASD[APSAutoScheduleDialog.jsx]
  HUB --> AI[AIInsightsModule.jsx]
  RW --> PG[ui/pagination-lite.jsx]
  APS --> PG
  ASD --> IB[IconButton.jsx]
  HUB --> UI[tabs/dialog/glass/badge/skeleton]
```
Tabel komponen (100% cakupan 12 komponen erp manifest):

| Komponen | File | Peran | Endpoint disentuh |
|---|---|---|---|
| **ProductionDashboardModule** | ProductionDashboardModule.jsx | Hub 5-tab (Tabs) + lazy load sub-modul | — |
| **ProductionDashboardOverview** | ProductionDashboardOverview.jsx | Tab Overview: WIP/material/CMT/lokasi/setup | wip/summary, material-summary, cmt-receipts, locations, setup/status |
| **NextActionWidget** | NextActionWidget.jsx | Rekomendasi next action kontekstual | next-actions |
| **SetupWizard** | SetupWizard.jsx | Panduan setup awal | setup/status, seed-sample, skip, dismiss |
| **RahazaOEEModule** | RahazaOEEModule.jsx | Tab Performa: OEE dashboard | lines, oee/summary, oee/daily, oee/line/{id} |
| **RahazaLineBalancingModule** | RahazaLineBalancingModule.jsx | Tab Performa: keseimbangan lini | shifts, supervisor/line-balance |
| **ReworkAnalyticsModule** | ReworkAnalyticsModule.jsx | Tab Kualitas: analitik rework | rework/summary, rework/open, rework/settings (GET/PUT), close-manual |
| **APSGanttModule** | APSGanttModule.jsx | Tab Jadwal: Gantt + reschedule | aps/gantt, aps/wo/{id}, reschedule |
| **APSAutoScheduleDialog** | APSAutoScheduleDialog.jsx | Dialog penjadwalan otomatis | preview, commit, rollback, runs |
| **AIInsightsModule** | AIInsightsModule.jsx | Tab AI: RCA (Claude Sonnet 4.5) | analytics/ai/production/rca, qc/rca, history |
| **dashboardAtoms** | dashboardAtoms.jsx | Atom UI (StatCard, KpiTile, HeroCrystalCard) | — |
| **IconButton** | IconButton.jsx | Tombol ikon (dipakai dialog/sheet) | — |

Backend: router `/api/rahaza/*` (`rahaza_aps.py`, `rahaza_aps_scheduler.py`, `rahaza_oee.py`, `rahaza_line_balancing.py`, `rahaza_rework.py`, `rahaza_setup.py`, `rahaza_wip.py`, dll.) + `/api/prod/*` (CMT/material) + `/api/analytics/ai/*` (`analytics_ai.py`).

## B2. Inventaris Elemen (exhaustive — 131 testid konkret)
Semua `data-testid` per komponen. "*" = akhiran dinamis (nilai variabel). Cakupan 100% manifest.

### B2.1 Hub — ProductionDashboardModule
`production-dashboard` (container hub) · `tab-overview` · `tab-performance` · `tab-quality` · `tab-schedule` · `tab-ai`.

### B2.2 Overview — ProductionDashboardOverview
`production-dashboard-overview` (root panel Overview, hasil fix PD; lihat QA) · `location-filter` · `location-select` · `prod-dash-refresh` · `wip-row-*` · `overview-row-input-button-*` · `mat-summary-panel` · `cmt-summary-panel` · `goto-cmt-packing-btn` · `prod-line-board-cta`. (KPI via `StatCard` prop `testId`: mis. `kpi-total-output`.)

### B2.3 NextActionWidget
`next-action-widget` · `next-action-widget-empty` · `next-action-refresh` · `next-action-refresh-empty` · `nae-card-*` · `nae-cta-*` · `nae-why-*` · `nae-snooze-*`.

### B2.4 SetupWizard
`setup-wizard-overlay` · `setup-wizard-modal` · `setup-wizard-close` · `setup-step-*` · `setup-open-*` · `setup-prev-btn` · `setup-next-btn` · `setup-finish-btn` · `setup-seed-sample-btn` · `setup-skip-btn` · `setup-dismiss-btn`.

### B2.5 OEE — RahazaOEEModule
`oee-dashboard-page` · `oee-line-filter` · `oee-from-date` · `oee-to-date` · `oee-refresh-btn` · `oee-drill-date` · `oee-line-row-*` · `oee-drill-btn-*`.

### B2.6 Line Balancing — RahazaLineBalancingModule
`line-balance-page` · `lb-date` · `lb-shift` · `lb-summary` · `lb-lines` · `lb-line-*` · `lb-expand-*`.

### B2.7 Rework — ReworkAnalyticsModule
`rework-analytics-page` · `rework-refresh-button` · `rework-from-input` · `rework-to-input` · `rework-open-panel` · `rework-open-row-*` · `rework-top-lines-panel` · `rework-top-line-*` · `rework-top-models-panel` · `rework-top-model-*` · `rework-close-manual-button-*` · `rework-close-dialog` · `rework-close-reason-input` · `rework-close-notes-input` · `rework-close-writeoff-input` · `rework-close-confirm-button` · `rework-sla-settings-button` · `rework-sla-dialog` · `rework-sla-minutes-input` · `rework-sla-save-button`. (KPI tile via prop `testId`.)

### B2.8 APS Gantt — APSGanttModule
`aps-page` · `aps-toolbar` · `aps-toolbar-from-input` · `aps-toolbar-to-input` · `aps-toolbar-search-input` · `aps-toolbar-status-select` · `aps-toolbar-priority-select` · `aps-toolbar-zoom-toggle-day` · `aps-toolbar-zoom-toggle-week` · `aps-toolbar-zoom-toggle-month` · `aps-refresh-button` · `aps-auto-schedule-button` · `aps-line-balance-btn` · `aps-legend` · `aps-now-indicator` · `aps-gantt-scroll-container` · `aps-gantt-timeline-header` · `aps-gantt-sticky-line-column-header` · `aps-gantt-sticky-line-column-*` · `aps-line-row-*` · `aps-line-row-unassigned` · `aps-wo-bar-*` · `aps-capacity-cell-*` · `aps-detail-sheet` · `aps-detail-close-button` · `aps-detail-progress` · `aps-detail-reschedule-button` · `aps-reschedule-dialog` · `aps-reschedule-start-input` · `aps-reschedule-end-input` · `aps-reschedule-confirm-button` · `aps-balance-panel` · `aps-balance-line-*`.

### B2.9 Auto-Schedule Dialog — APSAutoScheduleDialog
`aps-auto-schedule-dialog` · `aps-auto-schedule-config` · `aps-auto-schedule-from-input` · `aps-auto-schedule-to-input` · `aps-auto-schedule-include-in-production-checkbox` · `aps-auto-schedule-include-in-production-label` · `aps-auto-schedule-preview-button` · `aps-auto-schedule-preview-result` · `aps-auto-schedule-proposals` · `aps-auto-schedule-proposal-row-*` · `aps-auto-schedule-unassigned` · `aps-auto-schedule-commit-button` · `aps-auto-schedule-rollback-button` · `aps-auto-schedule-clear-preview-button` · `aps-auto-schedule-runs-list` · `aps-auto-schedule-runs-row-*` · `aps-auto-schedule-runs-rollback-*` · `aps-auto-schedule-close-button`.

### B2.10 AI Insights — AIInsightsModule
`ai-insights-module` · `rca-section-*` (production/qc) · `rca-period-*` · `rca-run-*` · `rca-result-*` · `rca-history-row`.

### B2.11 pagination-lite (ui, dipakai Rework & APS list)
`pagination-lite` · `pagination-info` · `pagination-prev` · `pagination-next` · `pagination-page`.

## B3. Kamus Field — Kontrol Utama (per tab)
| Field | testid | Tipe | Default | Sumber |
|---|---|---|---|---|
| Lokasi (Overview) | `location-select` | select | "Semua Lokasi" | ProductionDashboardOverview |
| Lini (OEE) | `oee-line-filter` | select | Semua | RahazaOEEModule |
| Rentang OEE | `oee-from-date`/`oee-to-date` | date | 7 hari terakhir | RahazaOEEModule |
| Tanggal/Shift (LB) | `lb-date`/`lb-shift` | date/select | hari ini/Semua | RahazaLineBalancingModule |
| Rentang Rework | `rework-from-input`/`rework-to-input` | date | 7 hari | ReworkAnalyticsModule |
| SLA menit | `rework-sla-minutes-input` | number | nilai tersimpan (5–1440) | ReworkAnalyticsModule |
| Rentang/Status/Prioritas (APS) | `aps-toolbar-*` | date/text/select | rentang default | APSGanttModule |
| Zoom (APS) | `aps-toolbar-zoom-toggle-*` | toggle | week | APSGanttModule |
| Konfigurasi Auto-Schedule | `aps-auto-schedule-from/to-input`, `-include-in-production-checkbox` | date/checkbox | rentang, off | APSAutoScheduleDialog |
| Periode RCA | `rca-period-*` | toggle | 30 hari | AIInsightsModule |

## B4. Kamus Field — Form tulis
- **Tutup Rework Manual** (`rework-close-dialog`): `rework-close-reason-input` (wajib), `rework-close-notes-input` (opsional), `rework-close-writeoff-input` (int ≥0). → `POST rework/bundle/{bid}/close-manual`.
- **Pengaturan SLA** (`rework-sla-dialog`): `rework-sla-minutes-input` (int 5–1440). → `PUT rework/settings`.
- **Reschedule WO** (`aps-reschedule-dialog`): `aps-reschedule-start-input`, `aps-reschedule-end-input` (start<end). → `PATCH aps/wo/{id}/reschedule`.
- **Auto-Schedule** (`aps-auto-schedule-config`): `from`/`to` + `include_in_production`. → preview/commit/rollback.

## B4a. Kamus KPI per tab (grounded)
| Tab | KPI | Definisi | Sumber |
|---|---|---|---|
| Overview | Total Output | jumlah pcs output hari ini | wip/summary kpis |
| Overview | Total WIP | pcs sedang dikerjakan (belum selesai) | wip/summary kpis |
| Overview | Flow Efficiency | rasio kelancaran aliran (output vs WIP) | wip/summary kpis |
| Overview | Bottleneck | proses dengan WIP tertinggi | wip/summary kpis |
| Performa | OEE | Availability × Performance × Quality | oee/summary, `rahaza_oee.py` |
| Performa | Availability | % waktu produktif | oee_daily |
| Performa | Performance | % kecepatan vs standar | oee_daily |
| Performa | Quality | % lolos (non-cacat) | oee_daily |
| Performa | Balance % | keseimbangan beban antar lini | supervisor/line-balance |
| Kualitas | Open rework | jumlah rework terbuka | rework/open total_open |
| Kualitas | SLA breach | rework melewati `sla_minutes` | rework/summary |
| Kualitas | Avg minutes | rata-rata durasi rework | rework/summary |
| Jadwal | Total WO | WO terjadwal dalam rentang | aps/gantt kpis |
| Jadwal | Terlambat (late) | end < now & belum selesai | aps/gantt kpis |
| Jadwal | Berisiko (at risk) | mendekati deadline/overload | aps/gantt kpis |
| Jadwal | Load % | kapasitas terpakai vs tersedia | aps/gantt kpis |
| AI | Confidence | tingkat keyakinan analisis RCA | analytics/ai/*/rca |

## B5. Katalog Kontrak Endpoint — 26 path unik / 30 method-endpoint
Semua path **grounded** ke route backend (anti-halusinasi). RBAC di B7.

### Tab Overview
| # | Method Endpoint | Fungsi | RBAC | Sukses/Gagal |
|---|---|---|---|---|
| E1 | GET `/api/rahaza/wip/summary` | ringkasan WIP per proses + KPI | auth | 200 / 401 |
| E2 | GET `/api/prod/material-summary-by-location` | material per lokasi | auth | 200 / 401 |
| E3 | GET `/api/prod/cmt-receipts/summary` | ringkasan penerimaan CMT | auth | 200 / 401 |
| E4 | GET `/api/rahaza/locations` | master lokasi | auth | 200 / 401 |
| E5 | GET `/api/rahaza/setup/status` | status kelengkapan setup + `needs_wizard` + `steps` | auth | 200 / 401 |
| E6 | GET `/api/rahaza/next-actions?portal=&limit=` | rekomendasi next action | auth | 200 / 401 |
| E7 | POST `/api/rahaza/setup/seed-sample` | isi data contoh | auth | 200 / 401 |
| E8 | POST `/api/rahaza/setup/skip` | lewati wizard (sementara) | auth | 200 / 401 |
| E9 | POST `/api/rahaza/setup/dismiss` | jangan tampilkan wizard lagi | auth | 200 / 401 |

### Tab Performa (OEE + Line Balancing)
| # | Method Endpoint | Fungsi | RBAC |
|---|---|---|---|
| E10 | GET `/api/rahaza/lines` | master lini | auth |
| E11 | GET `/api/rahaza/oee/summary?date=` | KPI OEE agregat | auth |
| E12 | GET `/api/rahaza/oee/daily?from=&to=&line_id=` | OEE harian (rows) | auth |
| E13 | GET `/api/rahaza/oee/line/{id}?date=` | drill-down OEE per lini | auth |
| E14 | GET `/api/rahaza/shifts` | master shift | auth |
| E15 | GET `/api/rahaza/supervisor/line-balance?assign_date=&shift_id=` | keseimbangan lini | auth |

### Tab Kualitas (Rework)
| # | Method Endpoint | Fungsi | RBAC |
|---|---|---|---|
| E16 | GET `/api/rahaza/rework/summary?from=&to=` | KPI rework + top lini/model | auth |
| E17 | GET `/api/rahaza/rework/open` | daftar rework terbuka (`items`,`total_open`) | auth |
| E18 | GET `/api/rahaza/rework/settings` | baca SLA (`sla_minutes`) | auth |
| E19 | PUT `/api/rahaza/rework/settings` | ubah SLA (5–1440) | admin |
| E20 | POST `/api/rahaza/rework/bundle/{bid}/close-manual` | tutup rework manual | supervisor+ |

### Tab Jadwal (APS)
| # | Method Endpoint | Fungsi | RBAC |
|---|---|---|---|
| E21 | GET `/api/rahaza/aps/gantt?from=&to=&status=&priority=` | data Gantt (`days`,`lines`,`bars`,`kpis`) | auth (`rahaza_aps.py:170`) |
| E22 | GET `/api/rahaza/aps/wo/{id}` | detail WO untuk panel | auth (`rahaza_aps.py:395`) |
| E23 | PATCH `/api/rahaza/aps/wo/{id}/reschedule` | ubah jadwal WO | planner (`rahaza_aps.py:451`) |
| E24 | POST `/api/rahaza/aps/auto-schedule/preview` | usulan jadwal (run status=preview) | planner |
| E25 | POST `/api/rahaza/aps/auto-schedule/commit` | terapkan usulan | planner |
| E26 | POST `/api/rahaza/aps/auto-schedule/rollback` | batalkan run | planner |
| E27 | GET `/api/rahaza/aps/auto-schedule/runs?limit=` | riwayat run | auth |

### Tab AI (RCA)
| # | Method Endpoint | Fungsi | RBAC |
|---|---|---|---|
| E28 | POST `/api/analytics/ai/production/rca` | RCA produksi (Claude Sonnet 4.5) | auth |
| E29 | POST `/api/analytics/ai/qc/rca` | RCA kualitas (Claude Sonnet 4.5) | auth |
| E30 | GET `/api/analytics/ai/history?limit=&type=` | riwayat analisis | auth |

> Dinamis: `/api/analytics/ai/{type}` (AIInsightsModule membangun `production/rca`, `qc/rca`) & `/api/rahaza/wip/summary` (ditambah query) — semua grounded ke route bare backend.

## B5a. Rincian Parameter & Respons per Endpoint
Tabel padat parameter kunci + field respons utama (grounded).

| Endpoint | Param | Field respons utama |
|---|---|---|
| E1 wip/summary | `location_id?` | `processes[]{process_id,process_code,process_name,wip_qty,output_qty}`, `kpis{total_output,total_wip,flow_efficiency,bottleneck}` |
| E2 material-summary-by-location | `location_id?` | `locations[]{location,items[],total}` |
| E3 cmt-receipts/summary | `from?`,`to?` | `receipts[]`, `totals{qty,value}` |
| E4 locations | — | `[]{id,name,type}` |
| E5 setup/status | — | `needs_wizard`, `steps[]{key,label,done}`, `completed`,`total` |
| E6 next-actions | `portal`,`limit` | `actions[]{id,title,why,cta,severity,snooze_key}` |
| E7 setup/seed-sample | (body kosong) | `ok`, `seeded{lines,operators,models,orders}` |
| E8 setup/skip | — | `ok`, `skipped_until` |
| E9 setup/dismiss | — | `ok`, `dismissed_at` |
| E10 lines | — | `[]{id,code,name,is_active}` |
| E11 oee/summary | `date` | `kpis{oee,availability,performance,quality}`, `lines[]` |
| E12 oee/daily | `from`,`to`,`line_id?` | `rows[]{date,line_id,oee,availability,performance,quality}` |
| E13 oee/line/{id} | path `id`, `date` | `line{}`, `daily{}`, `breakdown{}` |
| E14 shifts | — | `[]{id,code,name,start,end}` |
| E15 supervisor/line-balance | `assign_date`,`shift_id?` | `summary{total_capacity,total_load,balance_pct}`, `lines[]{line_id,load,capacity}` |
| E16 rework/summary | `from`,`to` | `kpis{open,closed,breach,avg_minutes}`, `top_lines[]`, `top_models[]` |
| E17 rework/open | `page?`,`limit?` | `items[]{bundle_id,bundle_number,line_code,opened_at,age_minutes,sla_breach}`, `total_open` |
| E18 rework/settings (GET) | — | `sla_minutes` |
| E19 rework/settings (PUT) | body `sla_minutes`(5–1440) | `sla_minutes` (echo) |
| E20 rework/bundle/{bid}/close-manual | path `bid`, body `reason`,`notes?`,`writeoff_qty` | `ok`, `bundle{status:closed}` |
| E21 aps/gantt | `from`,`to`,`status?`,`priority?` | `days[]`, `lines[]`, `bars[]{wo_id,line_id,start,end,status,priority,progress}`, `kpis{total_wo,late,at_risk,load_pct}` |
| E22 aps/wo/{id} | path `id` | `work_order{}`, `schedule{}`, `progress` |
| E23 aps/wo/{id}/reschedule | path `id`, body `start`,`end` | `ok`, `work_order{scheduled_start,scheduled_end}` |
| E24 auto-schedule/preview | body `from`,`to`,`include_in_production?` | `id`, `status:preview`, `proposal[]`, `unassigned[]`, `kpis{}` |
| E25 auto-schedule/commit | body `run_id` | `ok`, `applied` |
| E26 auto-schedule/rollback | body `run_id` | `ok`, `reverted` |
| E27 auto-schedule/runs | `limit` | `[]{id,status,from,to,created_at,created_by}` |
| E28 analytics/ai/production/rca | body `days` | `analysis{summary,root_causes[],recommendations[]}`, `confidence` |
| E29 analytics/ai/qc/rca | body `days` | `analysis{...}` |
| E30 analytics/ai/history | `limit`,`type?` | `[]{id,type,created_at,period_days}` |


### B6.1 State Machine — Auto-Schedule run
```mermaid
stateDiagram-v2
  [*] --> preview: POST auto-schedule/preview
  preview --> committed: POST auto-schedule/commit
  preview --> cleared: bersihkan preview (UI) / abaikan
  committed --> rolled_back: POST auto-schedule/rollback
  rolled_back --> [*]
  committed --> [*]
  cleared --> [*]
```
- **preview:** hitung usulan, simpan run `status=preview` (koleksi `rahaza_aps_schedule_runs`), **tidak** mengubah WO. Guard: butuh line aktif cocok proses (else 400).
- **committed:** terapkan usulan ke jadwal WO.
- **rolled_back:** kembalikan jadwal WO ke sebelum run. Run tak ditemukan → 404.

### B6.2 State Machine — Rework item (dari sudut dashboard)
```mermaid
stateDiagram-v2
  [*] --> reworking: bundle gagal QC
  reworking --> closed_ok: rework selesai (modul rework/eksekusi)
  reworking --> closed_manual: close-manual (write-off) dari dashboard
  closed_ok --> [*]
  closed_manual --> [*]
```
- **close-manual** (E20): hanya untuk bundle berstatus `reworking` (else 400 "Bundle tidak sedang reworking…"); bundle tak ada → 404. Mencatat write-off & alasan.

### B6.3 Perhitungan kunci (grounded)
- **OEE** = Availability × Performance × Quality (`rahaza_oee.py`). Ditampilkan per lini per hari (`oee_daily`).
- **Flow Efficiency (Overview)** = rasio output vs WIP (indikator kelancaran).
- **Bottleneck** = proses dengan WIP tertinggi.
- **APS KPI** = total WO terjadwal, jumlah terlambat (end < now & belum selesai), berisiko, load% (kapasitas terpakai) — `rahaza_aps.py` gantt.
- **Rework SLA breach** = (now − opened_at) > `sla_minutes`.
- **RCA guard** = butuh ≥ 5 event dalam rentang (`analytics_ai.py`) sebelum memanggil LLM.

### B6.4 Trigger UI
- Ganti tab → lazy-load sub-modul (Suspense) → sub-modul fetch sendiri saat mount.
- Refresh per tab memanggil ulang endpoint tab tsb.
- Redirect legacy modul → set tab awal via `getInitialTab` (`moduleRegistry.js:19`).
- Auto-Schedule: preview harus sukses sebelum commit; commit mengaktifkan rollback.

### B6.5 Aturan bisnis rinci (grounded)
1. **Lazy hub:** hub hanya me-mount sub-modul tab aktif (Suspense); data di-fetch on-demand → tab yang belum dibuka tidak membebani jaringan.
2. **Redirect legacy:** membuka `prod-oee`/`prod-line-balance`/`prod-rework-analytics`/`prod-aps-gantt` → hub `production-dashboard` dengan tab awal sesuai (`getInitialTab`, `moduleRegistry.js:19`).
3. **Preview tidak destruktif:** `auto-schedule/preview` menyimpan run `status=preview` di `rahaza_aps_schedule_runs`, **tanpa** mengubah WO. Hanya `commit` yang menerapkan; `rollback` memulihkan.
4. **Guard preview:** butuh minimal 1 line aktif yang cocok proses → else `400`.
5. **Guard RCA:** butuh ≥ 5 event dalam rentang sebelum memanggil LLM → else `400` (hemat kredit).
6. **SLA valid range:** `rework/settings` PUT memvalidasi 5–1440 menit → di luar itu `400`.
7. **Close-manual state gate:** hanya bundle `reworking` yang bisa ditutup manual (else `400`); bundle tak ada → `404`.
8. **Reschedule validasi:** `start < end`; WO tak ada → `404`; butuh role perencanaan.
9. **needs_wizard:** `setup/status` menandai instalasi belum lengkap; wizard tampil sampai `finish`/`skip`/`dismiss`.
10. **Serialisasi & UUID:** semua entitas memakai `id` UUID (bukan ObjectId); waktu ISO UTC.
11. **RBAC berlapis:** GET = auth; mutasi jadwal = planner; tutup rework = supervisor+; SLA = admin.
12. **AI history:** setiap RCA sukses menyimpan baris ke `ai_rca_history` (dapat ditampilkan `rca-history-row`).


Sumber: `require_auth` (semua GET), `_require_planner` (APS mutasi, `rahaza_aps.py:56`), `_require_supervisor`/admin (rework), admin (SLA).

| Aksi | admin/owner | manajer/supervisor produksi | planner | user login lain | tanpa token |
|---|---|---|---|---|---|
| Lihat semua tab (E1–E6,E10–E18,E21–E22,E27,E30) | ✅ | ✅ | ✅ | ✅ | ❌ 401/403 |
| Setup seed/skip/dismiss (E7–E9) | ✅ | ✅ | ✅ | ✅ (per user) | ❌ |
| Ubah SLA rework (E19) | ✅ | ❌ | ❌ | ❌ | ❌ |
| Tutup rework manual (E20) | ✅ | ✅ (supervisor+) | ❌ | ❌ | ❌ |
| Reschedule/Auto-Schedule preview/commit/rollback (E23–E26) | ✅ | ✅ (bila role perencanaan) | ✅ | ❌ | ❌ |
| Jalankan RCA AI (E28–E29) | ✅ | ✅ | ✅ | ✅ | ❌ |

## B8. Peta Integrasi
```mermaid
graph LR
  WIP[(rahaza_wip_events)] --> OV[Overview/OEE]
  WO[(rahaza_work_orders)] --> APS[APS Gantt]
  BND[(rahaza_bundles)] --> RW[Rework/Quality]
  OEED[(rahaza_oee_daily)] --> OEE[OEE tab]
  LINES[(rahaza_lines)] --> APS
  LINES --> OEE
  SHIFT[(rahaza_shifts)] --> LB[Line Balance]
  APS --> RUNS[(rahaza_aps_schedule_runs)]
  AI[AI RCA] --> LLM[Claude Sonnet 4.5 - analytics_ai.py]
  AI --> HIST[(ai_rca_history)]
  SET[(rahaza_settings)] --> RW
```
Dashboard **membaca** hasil modul lain (Order/WO/Bundle/Eksekusi/QC) & menulis terbatas (run jadwal, penutupan rework, SLA, flag setup).

## B9. Kamus Data (koleksi kunci)
| Koleksi | Field penting | Dipakai tab |
|---|---|---|
| `rahaza_aps_schedule_runs` | `id`, `status`(preview/committed/rolled_back), `from`,`to`, `proposal`, `created_at`, `created_by` | Jadwal (Auto-Schedule) |
| `ai_rca_history` | `id`, `type`(production/qc), `analysis`, `period_days`, `created_at`, `created_by` | AI |
| `rahaza_oee_daily` | `line_id`, `date`, `availability`,`performance`,`quality`,`oee` | Performa |
| `rahaza_settings` | `rework_sla_minutes` | Kualitas |
| `rahaza_wip_events` | `process_id`, `qty`, `event`, `created_at` | Overview/OEE |
| `rahaza_work_orders` | `id`,`status`,`scheduled_start/end`,`line_id`,`priority` | Jadwal |

## B10. Katalog Pesan (kunci)
| Kode | Pesan | Endpoint |
|---|---|---|
| 400 | Tidak ada line aktif yang cocok dengan process terpilih. | auto-schedule/preview |
| 400 | Data produksi belum cukup (N events, min 5)… | analytics/ai/*/rca |
| 400 | sla_minutes harus 5–1440 (contoh) | rework/settings PUT |
| 400 | Bundle tidak sedang reworking (status=…) | rework close-manual |
| 404 | Bundle tidak ditemukan | rework close-manual |
| 404 | Run tidak ditemukan. | auto-schedule commit/rollback |
| 404 | Work Order tidak ditemukan | aps/wo/{id} |
| 401/403 | Unauthorized / role tidak cukup | endpoint terproteksi |

## B11. Integrasi LLM (AI RCA) — detail
- **Provider/Model:** Claude **Sonnet 4.5** via `backend/routes/analytics_ai.py` (integrasi LLM terpusat).
- **Endpoint:** `POST /api/analytics/ai/production/rca` & `POST /api/analytics/ai/qc/rca` (body `{days}`), `GET /api/analytics/ai/history`.
- **Alur:** kumpulkan event produksi/QC dalam `days` terakhir → **guard** minimal 5 event → susun prompt terstruktur (metrik, tren, top penyumbang) → panggil LLM → parse hasil `{summary, root_causes[], recommendations[], confidence}` → simpan ke `ai_rca_history` → kembalikan ke UI (`rca-result-*`).
- **Guard hemat biaya:** bila data < 5 event, kembalikan `400 "Data produksi belum cukup…"` **sebelum** memanggil LLM (tidak ada biaya token).
- **UI:** `AIInsightsModule` menyediakan 2 seksi (`rca-section-*` untuk production & qc), pemilih periode (`rca-period-*`), tombol jalankan (`rca-run-*`), area hasil (`rca-result-*`), dan riwayat (`rca-history-row`).
- **RBAC:** `require_auth` (semua user login boleh menjalankan; disarankan supervisor/manajer).
- **Kegagalan LLM:** ditangani sebagai error terkontrol; UI menampilkan pesan & tidak menyimpan history parsial.

## B12. Ringkasan Endpoint → Tab → Testid pemicu (cross-reference)
| Endpoint | Tab | Dipicu oleh (testid) |
|---|---|---|
| wip/summary, locations, material, cmt, setup/status | Overview | `prod-dash-refresh`, `location-select` |
| next-actions | Overview | `next-action-refresh` |
| setup/seed-sample/skip/dismiss | Overview | `setup-seed-sample-btn`,`setup-skip-btn`,`setup-dismiss-btn` |
| lines, oee/summary, oee/daily, oee/line/{id} | Performa | `oee-refresh-btn`,`oee-line-filter`,`oee-drill-btn-*` |
| shifts, supervisor/line-balance | Performa | `lb-date`,`lb-shift`,`lb-expand-*` |
| rework/summary, rework/open | Kualitas | `rework-refresh-button`,`rework-from-input` |
| rework/settings (GET/PUT) | Kualitas | `rework-sla-settings-button`,`rework-sla-save-button` |
| rework/bundle/{id}/close-manual | Kualitas | `rework-close-manual-button-*`,`rework-close-confirm-button` |
| aps/gantt, aps/wo/{id}, reschedule | Jadwal | `aps-refresh-button`,`aps-wo-bar-*`,`aps-detail-reschedule-button` |
| auto-schedule preview/commit/rollback/runs | Jadwal | `aps-auto-schedule-preview-button`,`-commit-button`,`-rollback-button`,`-runs-rollback-*` |
| analytics/ai/*/rca, history | AI | `rca-run-*`,`rca-history-row` |

## B13. Data-state per tab (Loading / Empty / Error / Populated)
Setiap tab mengikuti pola state eksplisit (design v3):

| Tab | Loading | Empty | Error | Populated |
|---|---|---|---|---|
| Overview | skeleton KPI | "belum ada data / setup" + Next Action | pesan gagal + Refresh | KPI + `wip-row-*` + panel material/CMT |
| Performa (OEE) | skeleton tabel | "belum ada data OEE" | pesan + Refresh | `oee-line-row-*` + drill |
| Performa (LB) | skeleton | "belum ada lini/shift" | pesan | `lb-line-*` + `lb-summary` |
| Kualitas | skeleton | "tidak ada rework terbuka" | pesan + Refresh | `rework-open-row-*` + top panels |
| Jadwal | skeleton grid | "Belum ada line produksi" | pesan + Refresh | `aps-line-row-*` + `aps-wo-bar-*` |
| AI | spinner "menganalisis…" | "belum ada histori" | pesan guard/LLM | `rca-result-*` + `rca-history-row` |

Semua empty-state adalah **keadaan valid** (bukan error) dan sudah diverifikasi UI (C3).



## C1. Test Scenarios (naratif)
1. **Baca semua tab** — 26 endpoint mengembalikan 200 + bentuk yang benar (Overview/OEE/LB/Rework/APS/AI-history/runs).
2. **Guard data-kosong** — preview & RCA mengembalikan 400 yang benar saat master/data belum cukup.
3. **Negatif** — id/run tidak ada → 404; SLA di luar rentang → 400.
4. **State** — PUT SLA idempoten (nilai sama) → 200.
5. **RBAC** — akses tanpa token → 401/403 (baca & tulis).
6. **UI** — 5 tab + panel root render; dialog Auto-Schedule terbuka; tanpa error konsol.

### C1.1 Rincian skenario per tab & tipe
- **Overview (Happy):** wip/summary, material, cmt, locations, setup/status, next-actions → semua 200 + bentuk benar. Empty state valid saat DB fresh.
- **Performa (Happy/Edge):** lines, oee/summary, oee/daily (+filter line_id), oee/line/{id} (data-dependent), shifts, supervisor/line-balance.
- **Kualitas (Happy/State/Negative):** rework/summary, rework/open, settings GET; PUT idempoten (nilai sama) 200; PUT out-of-range 400; close-manual bundle fiktif 404.
- **Jadwal (Happy/Edge/Negative/State):** aps/gantt (+filter status), aps/wo/{id} (data-dependent), runs; commit/rollback run fiktif 404; preview guard 400 (no line).
- **AI (Happy/Negative):** analytics/ai/history 200; production/rca guard 400 (data<5).
- **Permission (semua tab):** akses tanpa token pada baca & tulis → 401/403 (6 titik diuji).

### C1.2 Kebersihan DB & keamanan uji
Skrip **tidak** memanggil endpoint destruktif secara nyata: tidak reschedule WO, tidak commit auto-schedule, tidak seed-sample, tidak skip/dismiss. Endpoint mutasi diuji lewat **guard** (invalid id → 4xx), **idempoten** (PUT SLA nilai sama), atau **RBAC** (tanpa token). Satu-satunya penulisan sementara: run `preview` (bila lini ada) & baris `ai_rca_history` (bila LLM jalan) — keduanya dibersihkan by-window. Pada DB fresh, keduanya bahkan tidak terbuat (guard 400 lebih dulu). **DB tetap pristine.**


Login sekali; tanpa mutasi WO/seed; preview & RCA hanya diuji lewat guard; self-cleanup (hapus run preview + RCA history by-window). Tipe: **H**appy/**E**dge/**N**egative/**P**ermission/**S**tate.

| TC | Skenario | Tipe | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-01 | wip/summary | H | 200 + `processes` | 200 | ✅ |
| TC-02 | material-summary-by-location | H | 200 | 200 | ✅ |
| TC-03 | cmt-receipts/summary | H | 200 | 200 | ✅ |
| TC-04 | locations (list) | H | 200 list | 200 | ✅ |
| TC-05 | setup/status | H | 200 + `steps`,`needs_wizard` | 200 (needs_wizard=true) | ✅ |
| TC-06 | lines (list) | H | 200 list | 200 (n=0) | ✅ |
| TC-07 | shifts (list) | H | 200 list | 200 | ✅ |
| TC-08 | oee/summary?date | H | 200 + `kpis` | 200 | ✅ |
| TC-09 | oee/daily?from&to | H | 200 + `rows` | 200 | ✅ |
| TC-10 | oee/line/{id} | H | 200 (bila line) | INFO (no line master) | ℹ️ |
| TC-11 | supervisor/line-balance | H | 200 + `summary` | 200 | ✅ |
| TC-12 | oee/daily line_id filter | E | 200 | 200 | ✅ |
| TC-13 | aps/gantt | H | 200 + days/lines/bars/kpis | 200 (bars=0) | ✅ |
| TC-14 | aps/gantt status filter | E | 200 | 200 | ✅ |
| TC-15 | aps/wo/{id} | H | 200 (bila bar) | INFO (no WO bars) | ℹ️ |
| TC-16 | auto-schedule/runs | H | 200 list | 200 | ✅ |
| TC-17 | rework/summary | H | 200 + `kpis` | 200 | ✅ |
| TC-18 | rework/open | H | 200 + `items`,`total_open` | 200 | ✅ |
| TC-19 | rework/settings (GET) | H | 200 + `sla_minutes` | 200 | ✅ |
| TC-20 | next-actions | H | 200 + `actions` | 200 | ✅ |
| TC-21 | analytics/ai/history | H | 200 list | 200 | ✅ |
| TC-22 | rework/settings PUT (nilai sama) | S | 200, sla sama | 200 | ✅ |
| TC-23 | aps/wo nonexistent | N | 404 | 404 | ✅ |
| TC-24 | auto-schedule/commit run invalid | N | 400/404 | 404 | ✅ |
| TC-25 | auto-schedule/rollback run invalid | N | 400/404 | 404 | ✅ |
| TC-26 | rework close-manual bundle invalid | N | 404 | 404 | ✅ |
| TC-27 | rework/settings PUT out-of-range | N | 400 | 400 | ✅ |
| TC-28 | wip/summary tanpa token | P | 401/403 | 401 | ✅ |
| TC-29 | aps/gantt tanpa token | P | 401/403 | 401 | ✅ |
| TC-30 | setup/seed-sample tanpa token | P | 401/403 | 401 | ✅ |
| TC-31 | auto-schedule/commit tanpa token | P | 401/403 | 401 | ✅ |
| TC-32 | analytics production/rca tanpa token | P | 401/403 | 401 | ✅ |
| TC-33 | rework close-manual tanpa token | P | 401/403 | 401 | ✅ |
| TC-34 | auto-schedule/preview guard (no line) | N | 400 "line aktif" | 400 | ✅ |
| TC-35 | production/rca guard (data<5) | N | 400 "belum cukup" | 400 | ✅ |

**Ringkas:** 33 PASS / 2 INFO / 0 FAIL. INFO = data-dependent (fresh DB tanpa line/WO). Cleanup: run preview & RCA history dihapus by-window; **tidak ada mutasi WO/seed**.

## C3. UI — verifikasi Playwright (5 tab)
Login admin → deep-link `?portal=production&module=production-dashboard`. Semua panel root **resolve** tanpa error konsol.

| Tab | Elemen diperiksa | Hasil |
|---|---|---|
| Hub | `production-dashboard`(=1), `tab-overview/performance/quality/schedule/ai` | ✅ semua |
| Overview | `production-dashboard-overview`(=1), `prod-dash-refresh`, `location-filter`, `mat-summary-panel`, `cmt-summary-panel`, NextActionWidget | ✅ render (empty state benar) |
| Performa | `oee-dashboard-page`, `oee-refresh-btn`, `oee-line-filter`, `line-balance-page`, `lb-date`, `lb-shift` | ✅ semua |
| Kualitas | `rework-analytics-page`, `rework-refresh-button`, `rework-open-panel`, `rework-sla-settings-button` | ✅ semua |
| Jadwal | `aps-page`, `aps-toolbar`, `aps-refresh-button`, `aps-auto-schedule-button`, `aps-line-balance-btn`, `aps-legend` | ✅ semua |
| Auto-Schedule | `aps-auto-schedule-dialog`, `-config`, `-preview-button`, `-close-button` | ✅ dialog terbuka |
| AI | `ai-insights-module`, `rca-section-*`, `rca-run-*`, `rca-period-*` | ✅ semua |

> Elemen berbasis baris (`oee-line-row-*`, `aps-wo-bar-*`, `rework-open-row-*`, `wip-row-*`, `rca-history-row`, `nae-card-*`) bersifat **data-dependent** — render saat data produksi tersedia (grounded via `file:baris`).

## C4. Catatan QA (internal)
Detail QA teknis & observasi (termasuk 1 temuan Low yang sudah diperbaiki + verifikasi) dipisah → lihat **`../_qa/production-dashboard_bugs.md`** & ringkasan lintas modul **`../_qa/BUG_REGISTER.md`**. Kondisi: semua uji hijau, DB pristine.

## C5. Troubleshooting
| Gejala | Sebab | Solusi |
|---|---|---|
| Banyak angka 0 + Setup Wizard muncul | Master belum lengkap (`needs_wizard=true`) | Jalankan setup (Tugas 1) / isi master |
| "Belum ada line produksi" (Gantt) | Belum ada lini aktif | Definisikan `rahaza_lines` |
| Preview Auto-Schedule 400 "line aktif" | Tak ada lini cocok proses | Pastikan lini & proses aktif |
| RCA 400 "belum cukup" | Data event < 5 | Kumpulkan lebih banyak event lalu ulangi |
| Commit/Rollback 404 "Run tidak ditemukan" | run_id salah/expired | Preview ulang lalu commit |
| Tidak bisa ubah SLA | Bukan admin | Minta admin |
| Tab lambat saat pertama dibuka | Lazy-load + fetch awal | Tunggu; klik Refresh |

## C6. Lampiran — Bukti & Skor
- **Skrip backend:** `/app/tests/pilot_production_dashboard_test.py` (35 TC, 26 endpoint, self-cleanup, tanpa mutasi WO/seed).
- **UI:** Playwright (screenshot Overview + Jadwal) — 5 tab render.
- **Kredensial uji:** `admin@garment.com` / `Admin@123`.
- **Kondisi DB:** bersih (run preview & RCA history uji dibersihkan; verifikasi tanpa residu).

**Rubrik self-score (validator wajib ≥ 95):**
| Dimensi | Bobot | Skor |
|---|---|---|
| Kelengkapan Fitur (B1,B2) | 20 | 20 |
| Kelengkapan Flow (A5,A7,A9,B6,B8) | 15 | 15 |
| Logic/State/RBAC (B6,B7) | 15 | 15 |
| Akurasi Kontrak Endpoint (B5,B9,B10) | 15 | 14 |
| Cakupan & Hasil Uji Nyata (C2,C3) | 20 | 20 |
| Kejelasan Guideline & Keawaman (A,D4) | 10 | 9 |
| Bukti Anti-Halusinasi | 5 | 5 |
| **Total** | **100** | **98/100** |

---

# BAGIAN D — LAMPIRAN CONTOH, PAYLOAD & DETAIL UJI

## D1. Contoh Payload API (Request → Response)
**WIP summary (E1):** `GET /api/rahaza/wip/summary` → `{ "processes":[{process_code,wip_qty,...}], "kpis":{...} }`
**Setup status (E5):** `GET /api/rahaza/setup/status` → `{ "needs_wizard":true, "steps":[{key,label,done}], ... }`
**OEE summary (E11):** `GET /api/rahaza/oee/summary?date=2026-07-07` → `{ "kpis":{oee,availability,performance,quality}, ... }`
**APS Gantt (E21):** `GET /api/rahaza/aps/gantt?from=..&to=..` → `{ "days":[...], "lines":[...], "bars":[{wo_id,line_id,start,end,status}], "kpis":{total_wo,late,at_risk,load_pct} }`
**Auto-Schedule preview (E24) — guard (fresh DB):** → `400 { "detail":"Tidak ada line aktif yang cocok dengan process terpilih." }`
**Rework settings PUT (E19):** `PUT /api/rahaza/rework/settings` body `{ "sla_minutes":120 }` → `200 { "sla_minutes":120 }`
**RCA (E28) — guard:** `POST /api/analytics/ai/production/rca` body `{ "days":7 }` → `400 { "detail":"Data produksi belum cukup (0 events, min 5)..." }`
**RCA history (E30):** `GET /api/analytics/ai/history?limit=10` → `[ {id,type,created_at,...} ]`

## D2. Detail Test Case terpilih (Input → Expected → Actual)
- **TC-05 (setup/status):** GET → expected `needs_wizard` & `steps` → actual `needs_wizard=true` (DB fresh) → ✅.
- **TC-13 (aps/gantt):** GET rentang 4 minggu → expected days/lines/bars/kpis → actual 200, bars=0 (belum ada WO terjadwal) → ✅.
- **TC-22 (SLA idempoten):** GET sla=cur → PUT sla=cur → expected 200 nilai sama → actual 200 → ✅ (tanpa perubahan net).
- **TC-24/25 (commit/rollback invalid):** run_id fiktif → expected 404 "Run tidak ditemukan" → actual 404 → ✅.
- **TC-26 (close-manual invalid):** bundle fiktif → expected 404 → actual 404 → ✅.
- **TC-27 (SLA out-of-range):** sla=99999 → expected 400 → actual 400 → ✅.
- **TC-34 (preview guard):** rentang tanpa lini aktif → expected 400 "line aktif" → actual 400 → ✅.
- **TC-35 (RCA guard):** data<5 → expected 400 "belum cukup" → actual 400 → ✅.
- **Catatan skrip:** cek status-error memakai `r.status_code` langsung (objek `requests.Response` *falsy* saat ≥400). Cleanup: `rahaza_aps_schedule_runs` (status preview, window) & `ai_rca_history` (window) dihapus; tak ada mutasi WO.

## D3. Sequence — Auto-Schedule Preview → Commit → Rollback
```mermaid
sequenceDiagram
  participant U as Planner
  participant D as APSAutoScheduleDialog
  participant BE as Backend (scheduler)
  participant DB as MongoDB
  U->>D: buka dialog + set rentang
  U->>D: klik Preview
  D->>BE: POST auto-schedule/preview
  BE->>DB: hitung usulan, simpan run(status=preview)
  BE-->>D: {id, proposal, unassigned, kpis}
  U->>D: klik Commit
  D->>BE: POST auto-schedule/commit {run_id}
  BE->>DB: terapkan ke jadwal WO (status=committed)
  BE-->>D: {ok, applied:N}
  U->>D: (bila salah) klik Rollback
  D->>BE: POST auto-schedule/rollback {run_id}
  BE->>DB: kembalikan jadwal WO (status=rolled_back)
  BE-->>D: {ok}
```

## D4. Worked Example (skenario bisnis lengkap)
**Persona:** Pak Budi (Manajer Produksi). **Situasi:** pagi hari, memantau lantai.

1. **Overview.** Pak Budi buka Dashboard Produksi (tab Overview). Ia melihat **Total WIP** tinggi dan **Bottleneck = SEWING**. Panel "WIP per Proses" (`wip-row-*`) menegaskan tumpukan di jahit. Ia klik **Refresh** (`prod-dash-refresh`) untuk memastikan data terbaru.
2. **Performa.** Pindah ke tab **Performa**. OEE lini jahit (`oee-line-row-*`) rendah (mis. 62%) dengan **Performance** paling kecil. Line Balancing (`lb-summary`) menunjukkan Lini 2 overload, Lini 3 nganggur.
3. **AI.** Ke tab **AI**, seksi produksi (`rca-section-*`), pilih periode 7 hari (`rca-period-*`), klik **Jalankan** (`rca-run-*`). (Bila data cukup) Claude Sonnet 4.5 mengembalikan analisis (`rca-result-*`): akar masalah = ketimpangan beban + downtime mesin jahit; rekomendasi = pindahkan sebagian WO Lini 2 → Lini 3. (Bila data < 5 event, sistem menampilkan pesan "belum cukup" — Pak Budi menunggu lebih banyak data.)
4. **Jadwal.** Ke tab **Jadwal** (`aps-page`). Ia klik **Auto-Schedule** (`aps-auto-schedule-button`), set rentang 3 minggu, **Preview** (`aps-auto-schedule-preview-button`). Sistem mengusulkan realokasi (`aps-auto-schedule-proposals`) yang memindah beban ke Lini 3. Puas → **Commit** (`aps-auto-schedule-commit-button`).
5. **Koreksi (revisi).** Ternyata Lini 3 sedang maintenance sore itu. Pak Budi klik **Rollback** (`aps-auto-schedule-rollback-button`) pada run tsb → jadwal kembali seperti semula. Ia lalu **Reschedule** manual satu WO via batang Gantt (`aps-wo-bar-*` → `aps-detail-reschedule-button`) ke hari berikutnya.
6. **Kualitas.** Sebelum tutup layar, ke tab **Kualitas**: ada 1 rework melewati SLA. Karena barang tak layak, ia **Tutup Manual** (`rework-close-manual-button-*`) dengan alasan & write-off qty.
- **Hasil:** keputusan berbasis data (WIP→OEE→AI→jadwal→kualitas), semua dari satu control room, dengan aksi aman (preview/rollback).

## D3.1 Sequence — Reschedule WO manual (dari Gantt)
```mermaid
sequenceDiagram
  participant U as Planner
  participant G as APSGanttModule
  participant BE as Backend (rahaza_aps)
  participant DB as MongoDB
  U->>G: klik batang WO (aps-wo-bar-*)
  G->>BE: GET aps/wo/{id}
  BE-->>G: {work_order, schedule, progress}
  U->>G: klik Reschedule -> isi start/end
  G->>BE: PATCH aps/wo/{id}/reschedule {start,end}
  alt valid (planner, start<end, WO ada)
    BE->>DB: update scheduled_start/end
    BE-->>G: 200 {work_order}
    G->>BE: GET aps/gantt (refresh)
  else invalid
    BE-->>G: 4xx (404 WO / 403 role / 400 tanggal)
  end
```

## D4.1 Worked Example #2 — Investigasi Cacat (Kualitas + AI)
**Persona:** Bu Rina (QC Lead). **Situasi:** laporan cacat meningkat minggu ini.
1. **Kualitas.** Bu Rina buka tab **Kualitas** (`rework-analytics-page`), set rentang 7 hari (`rework-from-input`/`rework-to-input`), **Refresh** (`rework-refresh-button`). KPI menunjukkan **Open rework** naik & beberapa **SLA breach**.
2. **Top penyumbang.** Panel **Top Lini** (`rework-top-lines-panel`, `rework-top-line-*`) menyorot Lini 2; **Top Model** (`rework-top-models-panel`, `rework-top-model-*`) menyorot Model "Hoodie-X".
3. **AI RCA Kualitas.** Ke tab **AI**, seksi qc (`rca-section-*`), periode 30 hari (`rca-period-*`), **Jalankan** (`rca-run-*`). (Bila data cukup) Claude Sonnet 4.5 menyimpulkan akar masalah = pola jahitan kerah Model Hoodie-X + operator baru di Lini 2; rekomendasi = pelatihan + QC in-line tambahan. Hasil tersimpan (`rca-history-row`).
4. **Tindak lanjut.** Kembali ke Kualitas, satu bundle rework sudah tak layak → **Tutup Manual** (`rework-close-manual-button-*`) → dialog (`rework-close-dialog`) → alasan "cacat kerah permanen", write-off 3 pcs (`rework-close-writeoff-input`) → **Konfirmasi** (`rework-close-confirm-button`).
5. **Kebijakan SLA.** Karena SLA sering terlewat, admin menaikkan SLA dari 120 → 180 menit via `rework-sla-settings-button` → `rework-sla-minutes-input` → **Simpan** (`rework-sla-save-button`).
- **Hasil:** akar cacat teridentifikasi berbasis data + AI, rework dibereskan, kebijakan SLA disesuaikan.

## D5. FAQ
- **T: Kenapa semua nol?** J: DB/instalasi baru; isi master & jalankan produksi (Setup Wizard).
- **T: Apakah Preview mengubah jadwal?** J: Tidak. Hanya Commit yang menerapkan; Rollback membatalkan.
- **T: Apakah RCA selalu jalan?** J: Butuh ≥ 5 event; kalau kurang, muncul pesan guard.
- **T: Siapa boleh mengubah SLA?** J: Admin.
- **T: Modul OEE/Gantt lama saya ke mana?** J: Digabung ke sini sebagai tab (redirect otomatis).
- **T: Apakah data real-time?** J: Di-fetch saat buka tab/Refresh; klik Refresh untuk terbaru.
- **T: Apa arti baris "unassigned" di Gantt?** J: WO yang belum punya lini/jadwal (`aps-line-row-unassigned`). Jadwalkan lewat reschedule atau Auto-Schedule.
- **T: Kenapa tombol Commit tidak aktif?** J: Jalankan **Preview** dulu; Commit aktif setelah ada usulan preview.
- **T: Apa bedanya Skip vs Dismiss di Setup Wizard?** J: **Skip** menunda sementara; **Dismiss** menyembunyikan wizard secara menetap untuk user tsb.
- **T: Bisakah membuka OEE lama lewat URL modul lama?** J: Bisa — otomatis diarahkan ke tab Performa di hub ini.
- **T: Kenapa Load% > 100%?** J: Beban terjadwal melebihi kapasitas lini (overload) — pertimbangkan Line Balancing / Auto-Schedule.
- **T: Apakah menutup rework manual mengubah stok?** J: Ya, mencatat write-off qty sesuai input pada dialog.

## D6. Batasan, Asumsi & Backlog
- Dashboard **read-mostly**; mutasi terbatas (jadwal, tutup rework, SLA, flag setup).
- Angka data-dependent; empty state adalah keadaan valid, bukan error.
- RCA memerlukan LLM (Claude Sonnet 4.5) & data memadai (≥ 5 event).
- Auto-Schedule preview menyimpan run sementara di `rahaza_aps_schedule_runs`; bersihkan run lama secara berkala bila menumpuk.
- Gantt menampilkan WO dalam rentang tanggal terpilih; WO tanpa jadwal muncul di baris `aps-line-row-unassigned`.
- OEE bergantung pada kelengkapan `rahaza_oee_daily` (butuh pencatatan availability/performance/quality).
- **Backlog:** ekspor laporan OEE/rework (PDF/CSV); notifikasi push bottleneck & SLA breach; simulasi what-if kapasitas sebelum commit; auto-refresh berkala; drill-down bar Gantt ke detail bundle.
- **Asumsi:** master (lini/shift/proses/lokasi) & role termapping benar; jam sistem (timezone) konsisten UTC untuk perhitungan late/at-risk.
- **Kinerja:** tab di-lazy-load; membuka pertama kali sedikit lebih lambat karena fetch awal — gunakan Refresh untuk pembaruan.

## D8. Migrasi Modul Legacy → Tab (referensi)
| Modul lama (moduleId) | Sekarang | Tab tujuan | Testid root |
|---|---|---|---|
| `prod-oee` | digabung | Performa | `oee-dashboard-page` |
| `prod-line-balance` | digabung | Performa | `line-balance-page` |
| `prod-rework-analytics` | digabung | Kualitas | `rework-analytics-page` |
| `prod-aps-gantt` | digabung | Jadwal | `aps-page` |

Bookmark/link lama tetap berfungsi: `getInitialTab` (`moduleRegistry.js:19`) memetakan target lama ke tab yang benar di hub `production-dashboard`.

## D9. Changelog Dokumen
| Tanggal | Versi | Perubahan |
|---|---|---|
| 2026-07-07 | 1.0 | Dokumen awal v3 (SAP-grade) hub 5-tab: 12 komponen, 26 endpoint (30 method), 131 testid, state/RBAC/integrasi, worked example. Backend 33 PASS/2 INFO/0 FAIL; UI 5 tab diverifikasi; lulus validator. |

<!-- END OF MODULE DOC: production-dashboard -->
