# PROPOSAL FINAL — PORTAL PRODUKSI = CERMIN PORTAL MAKLON ("maklon" → "internal")

> **Status: ✅ SELESAI DIEKSEKUSI 2026-07-26 — Fase A · B1 · B2 · B3 · C · C2 · D · E · E2 semua tuntas.**
> Keputusan D1 (§2) diambil: **opsi (a) — pintu "Invoice" = Tagihan CMT** (`prod-cmt-billing`).
> Ringkasan hasil + bukti ada di **§5 HASIL EKSEKUSI** di akhir dokumen ini.
>
> _(Teks di bawah ini adalah proposal aslinya; sengaja tidak diubah supaya jejak keputusan utuh.)_
>
> **Status asli: PROPOSAL v3 (final, menunggu 1 keputusan) — BELUM DIEKSEKUSI.**
>
> Arahan owner 2026-07-26 yang dipakai sebagai hukum di dokumen ini:
> 1. Produksi & Maklon **flownya sama** (dua-duanya dilempar ke CMT). Bedanya: DA tidak lempar ke
>    buyer eksternal karena **buyer-nya DA sendiri** ⇒ langkah itu jadi **serah-terima → masuk
>    inventory DA sebagai FG**.
> 2. **Nama menu di-mirror** dari Maklon supaya user tidak bingung; kata "Maklon" → "Internal".
> 3. Di MONITORING PROGRESS **harus ada Tracking Produksi DAN Production Jobs**, tapi **hanya PO internal**.
> 4. **Input Progress & Operan Shift = tidak relevan ⇒ deprecate.**
> 5. **Retur Material = duplikasi** (material sudah diurus di Kirim Material CMT) ⇒ **deprecate**.
> 6. **Invoice tetap dibutuhkan** di Produksi ⇒ section 4 tetap "KEUANGAN & ANALITIK".
> 7. **Data internal & maklon harus terpisah** supaya manajemennya mudah.

---

## 1. Struktur final (4 section, datar 2 tingkat — persis pola Maklon)

| Maklon (acuan) | **Produksi (final)** | moduleId | keterangan |
|---|---|---|---|
| **MASTER DATA** | **MASTER DATA** | | |
| Data Klien | *(tidak ada)* | — | buyer = DA sendiri |
| Katalog Buyer | **Master Produk** | `prod-master-product-hub` | Produk & BOM · Lokasi Kerja · Operator |
| Vendor CMT | **Vendor CMT** | `vendor-admin` | **nama & modul SAMA** (belum ada di Produksi) |
| — | **Master Proses** | `prod-master-process-hub` | Proses · SOP · Kalender |
| **PRODUKSI MAKLON** | **PRODUKSI INTERNAL** | | urutan langkah **identik** |
| PO Maklon | **PO Internal** | `prod-pos-internal` | sudah scope `business_type=internal` |
| Kelola Sampel | *(tidak ada)* | — | tak ada SSOT sampel internal; sampling ada di Portal RnD |
| Kirim Material CMT | **Kirim Material CMT** | `prod-shipments-vendor` | **SAMA** (modul sudah auto-scope per portal) |
| Terima FG dari CMT | **Terima FG dari CMT** | `da-cmt-receive` | **SAMA** |
| Permak / Perbaikan | **Permak / Perbaikan** | `cmt-permak` | **SAMA** (belum ada di Produksi) |
| Dispatch ke Buyer | **Serah Terima FG** | `prod-shipments-buyer` | serah-terima → **masuk inventory DA sebagai FG** |
| Tutup PO (Closure) | **Tutup PO** | `po-closure` | buang tanda kurung |
| **MONITORING PROGRESS** | **MONITORING PROGRESS** | | |
| Dashboard Maklon | **Dashboard Produksi** | `production-dashboard` | landing |
| Monitoring CMT | **Pusat Kendali** | `prod-control-tower` | `cmt-monitor` mematok `?scope=maklon` di backend (`cmt_intake.py:26-33` hanya terima `maklon\|all`) ⇒ tak bisa dipakai internal tanpa ubah backend |
| Tracking Produksi | **Tracking Produksi** | `prod-monitoring` **(DIPERBAIKI)** | **SAMA** — sekarang MATI (§3 cacat A); diperbaiki + scope internal |
| Production Jobs | **Production Jobs** | `prod-work-orders` | **SAMA** — + scope internal (§3 cacat B) |
| Laporan Variance | **Laporan Variance** | `prod-variance` | **SAMA** |
| **KEUANGAN & ANALITIK** | **KEUANGAN & ANALITIK** | | |
| Invoice | **Invoice** | ⚠ **butuh keputusan D1** | lihat §2 |
| HPP Jahit | **HPP Produksi** | `fin-hpp` | padanan langsung |
| Estimasi AI | **Estimasi AI** | `prod-ai-insights` **(direpoint)** | sekarang isinya AI **SDM** (§3 cacat C) |
| — | **Kebutuhan Material** | `prod-material-requirements` | pindah dari section Monitoring (MRP = hitungan) |
| — | **Analitik Produksi** | `prod-analytics-hub` | AQL · Downtime · Kapasitas |
| — | **Perawatan Mesin** | `prod-predictive-maintenance` | rename dari "Predictive Maintenance" |

**Hasil: 4 section · datar 2 tingkat · 3 + 6 + 5 + 6 = 20 pintu · maks 6 item/section**
(sebelumnya: 3 section, 3 tingkat, 12 pintu menumpuk di satu section).

### Pintu yang DI-DEPRECATE (dicabut dari menu; `moduleId` **tetap** di `MODULE_REGISTRY` ⇒ deep-link lama tidak mati)
| pintu | alasan |
|---|---|
| **Input Progress** (`prod-progress`) | arahan owner — progres masuk dari CMT/Portal Vendor. Sekalian: **tombol "+Input" per proses di Dashboard Produksi juga MATI** — memanggil `openQuickInput()` sementara `QuickInputPanel` sudah diarsip FASE 5 dan **tak ada komponen yang merender `quickInputOpen`** (dibuktikan grep) ⇒ tombol tanpa efek, ikut dibersihkan |
| **Operan Shift** (`prod-shift-handover`) | arahan owner — tidak relevan |
| **Retur Material** (`prod-material-returns`) | arahan owner — duplikasi alur material |
| **AI Actions** (`hr-ai-hub`) | isinya hub AI **SDM** (Attrition/Skill Gap/Coaching); tetap tersedia di Portal SDM |

---

## 2. Satu keputusan tersisa: "Invoice" untuk produksi internal

Fakta yang saya cek langsung:
- Modul `maklon-billing` = **invoice ke KLIEN maklon** (`/api/dewi/maklon/invoices`, SSOT `dewi_maklon_pos`) ⇒ **tidak bisa dipakai internal** (internal tak punya klien eksternal).
- Uang yang benar-benar keluar di produksi internal = **jasa jahit ke vendor CMT**. Di backend jalurnya **sudah ada**: `dewi_cmt_payments` (**2 dokumen di DB**) + `POST /api/dewi/maklon/finance/cmt-payments/{id}/post-ap` → jurnal `cmt_ap_invoice` (Dr Biaya CMT / Cr Hutang Vendor). **Tapi belum ada modul UI-nya sama sekali** (grep FE: 0 pemanggil).

| Opsi | Isi pintu "Invoice" di Produksi | Kerja | Catatan |
|---|---|---|---|
| **a. (REKOMENDASI)** | **Tagihan CMT** — daftar `dewi_cmt_payments` per PO internal + status + tombol *Post AP* (endpoint sudah ada) | modul UI baru **kecil** (list + detail + 1 aksi) | inilah "invoice" yang nyata di produksi internal; sekarang backend-nya jalan tanpa UI |
| b. | Shortcut ke pintu AP Keuangan yang sudah ada (`fin-3way-match` / `fin-approval`) | nol modul baru | tapi tidak ter-scope PO internal ⇒ manajemen tak sepraktis (a) |
| c. | Invoice penjualan FG (AR) | — | itu domain Portal Marketing/Keuangan, bukan produksi |

---

## 3. 3 cacat produk yang ikut ditutup (ketemu saat menyamakan alur)

| kode | cacat | bukti | perbaikan |
|---|---|---|---|
| **A** | Pintu **"Monitoring Produksi" MATI** → `apiGet('/production-monitoring-v2')`; **0 route** di backend mengandung "monitoring"; HTTP **404**; error ditelan `catch → setData([])` ⇒ layar "Tidak ada data" padahal DB punya 3 `production_jobs` | `engine/ProductionMonitoringModule.jsx:49`; screenshot | jadi **"Tracking Produksi"**: endpoint baru per-vendor (`vendor_id/vendor_name/total_jobs/total_qty/total_produced/total_shipped_to_buyer/progress_pct/performance/jobs[]`) dari `production_jobs`+`production_job_items`, **difilter `business_type=internal`** |
| **B** | **"Production Jobs" mencampur internal + maklon** → `/api/distribusi-kerja` (`production_execution.py:639`) `po_query = {}` tanpa filter. DB: 3 PO internal + **2 PO maklon**; hierarki yang dikembalikan memang memuat `PO-MK-DEMO-1/2` | probe API + DB | tambah param `business_type` (pola `production_pos.py:102-107` yang sudah ada) + FE kirim scope portal (pola `portalId === 'maklon' ? 'maklon' : 'internal'` yang sudah dipakai 3 modul lain) |
| **C** | **2 pintu "AI" di Produksi isinya AI SDM** → `prod-ai-insights` = `RahazaAIModule` (= tab `hr-ai-hub/insights`), `hr-ai-hub` = hub HR AI. AI produksi asli (`AIInsightsModule` → `/api/analytics/ai/*`, hidup) cuma jadi tab Dashboard | `moduleRegistry.js:842-843` | `prod-ai-insights` → `AIInsightsModule` (label "Estimasi AI"); tab "AI Insight" di Dashboard dihapus (anti pintu-kembar-tab); `hr-ai-hub` dicabut dari Produksi |

**Pemisahan data (arahan #7)** dikerjakan di 4 titik: `distribusi-kerja` (Production Jobs), endpoint Tracking baru, `production-variances` (dicek dulu apakah sudah dukung `business_type`; kalau belum, ditambah), dan verifikasi ulang 3 modul yang sudah auto-scope (Kirim Material / Serah Terima FG / Tutup PO).

---

## 4. Rencana eksekusi

| Fase | Isi | Risiko |
|---|---|---|
| **A** | Tulis ulang blok `production` di `portalNav.js` (4 section datar, nama mirror), rename label, cabut 4 pintu, arahkan ulang redirect legacy (`prod-line-board`/`prod-backlog`/`prod-andon-board`/`prod-monitoring-hub` → `prod-monitoring` yang sudah diperbaiki) | rendah — data tak disentuh, 0 moduleId dihapus |
| **B** | Cacat **A**: endpoint tracking baru + repoint modul · Cacat **B**: filter `business_type` · Cacat **C**: repoint AI + hapus 2 tab kembar + bersihkan tombol "+Input" mati | sedang — 2 endpoint backend + 5 file FE |
| **C** | Pintu **Invoice** sesuai keputusan D1 | sedang (opsi a) / rendah (opsi b) |
| **D** | Guard anti-kambuh di `check_nav_map.py`: `NAV-FLAT` (larang 3 tingkat), `NAV-MAX>8`, `NAV-LABEL` (tanpa tanda kurung), `NAV-DUPTAB` (pintu = tab pintu lain), **`NAV-DEADCALL`** (gate kontrak sekarang **buta** pada `apiGet('/x')` tanpa literal `/api` — 40 path FE lolos radar; itu sebab cacat A tak terdeteksi walau gate 12/12 hijau). Tiap guard **dibuktikan MERAH dulu** | rendah |
| **E** | Verifikasi: `analyze_ia_production.py` before/after · `check_nav_map.py` · `gate.sh` 12/12 · `yarn build` + `rebuild_frontend.sh` · screenshot 4 section · `testing_agent_v3` (buka SEMUA pintu; Produksi hanya PO internal; deep-link lama mendarat benar) | — |

Setelah Produksi beres → portal berikutnya dengan pola yang sama (usulan urutan: Keuangan → Gudang+Aksesoris → SDM → Marketing → Manajemen).

---

## 5. HASIL EKSEKUSI (2026-07-26, sesi lanjutan #6)

### 5.1 Yang benar-benar berubah

| Fase | Isi | Berkas utama |
|---|---|---|
| **A** | Blok `production` di nav ditulis ulang: **4 section datar 2 tingkat, 20 pintu, maks 6 pintu/section** (sebelumnya 3 section, 3 tingkat, 12 pintu menumpuk di satu section). Nama di-mirror dari Maklon. 4 pintu dicabut dari menu (`prod-progress`, `prod-shift-handover`, `prod-material-returns`, `hr-ai-hub`) — **moduleId tetap di registry ⇒ deep-link lama tidak mati** | `frontend/src/components/erp/portal-shell/portalNav.js` |
| **B1** | **Cacat A ditutup.** `GET /api/production-tracking` (BARU) — agregasi Production Jobs **per pelaksana**, wajib `business_type`. Menggantikan `/api/production-monitoring-v2` yang tidak pernah ada di backend (404 ditelan `catch → setData([])` ⇒ layar "Tidak ada data" padahal DB berisi job). Perhitungan memakai `_enrich_jobs()` yang sama dengan `/api/production-jobs` (satu penghitung, bukan dua) | `backend/routes/production_execution.py`, `frontend/.../engine/ProductionMonitoringModule.jsx` |
| **B2** | **Cacat B ditutup.** `/api/distribusi-kerja` + `/api/production-variances` menerima `business_type` ⇒ Production Jobs & Laporan Variance di Portal Produksi hanya PO internal, di Portal Maklon hanya PO maklon | `backend/routes/production_execution.py`, `frontend/.../engine/WorkOrderModule.jsx`, `OverproductionModule.jsx` |
| **B3** | **Cacat C ditutup.** `prod-ai-insights` ("Estimasi AI") dialihkan dari modul AI **SDM** ke AI **produksi** asli; tab AI kembar di Dashboard Produksi dihapus; tombol "+Input" mati (memanggil panel yang sudah diarsip) dibersihkan | `moduleRegistry.js`, `ProductionDashboardModule.jsx`, `ProductionDashboardOverview.jsx` |
| **C** | Pintu **Invoice = Tagihan CMT** (keputusan D1 opsi a): daftar `dewi_cmt_payments` per PO internal + KPI + detail + tombol *Posting AP*. Endpoint baca baru; **posting GL tetap memakai endpoint lama** supaya logika jurnal tidak terduplikasi | `backend/routes/production_cmt_billing.py`, `frontend/.../ProductionCMTBillingModule.jsx` |
| **C2** | Bundle statis dibangun ulang + verifikasi visual 4 section di preview | `scripts/rebuild_frontend.sh` |
| **D** | **5 guard anti-kambuh** di `check_nav_map.py`: `NAV-FLAT`, `NAV-MAX(>8)`, `NAV-LABEL`, `NAV-DUPTAB`, `NAV-DEADCALL`. Tiap guard **dibuktikan MERAH** (§5.3). Gate ini sekarang menjalankan **self-test sintetis setiap kali dijalankan** — guard yang diam otomatis membuat gate MERAH (`NAV-GUARD-DEAD`) | `scripts/guardrails/check_nav_map.py`, `scripts/lib/fe_static.py` (baru) |
| **D2** | 5 pelanggaran NYATA yang langsung ditangkap guard baru **diperbaiki**: Portal Keuangan diratakan (3 section bergrup → **6 section datar**, isi & urutan pintu tidak berubah) dan label bertanda kurung dibuang (`Retur Fisik (Gudang)` → `Retur Fisik`, `Piutang (AR)` → section `PIUTANG AR`, `Pengadaan (P2P)` → `PENGADAAN P2P`) | `portalNav.js` |
| **E/E2** | Verifikasi menyeluruh (§5.4) | — |

### 5.2 3 bug NYATA lain yang ketemu saat mengisi pintu Invoice dengan data alur asli

1. **Akun biaya CMT salah** — profil `cmt_ap_invoice` memakai `6-2200` dengan komentar "Biaya Jasa CMT", padahal di CoA yang ter-seed **6-2200 = "Listrik & Air Kantor"**. Artinya setiap tagihan jasa jahit yang diposting menambah beban listrik & air, HPP produksi kurang saji. Sekarang dipisah per domain: **internal → `5-231 Biaya Vendor CMT – Jahit` (COGS)**, **maklon → `7-120 Biaya Vendor CMT – Maklon`**, dengan jaring pengaman untuk DB lama + migrasi `backend/migrations/fix_cmt_ap_posting_profile.py`. Memo jurnal juga dulu kehilangan nomor tagihan (`payment_number` tak pernah ada; yang benar `payment_code`).
2. **Total header `cmt_receipts` tidak dihitung saat menambah baris** — hanya `PUT /lines/{id}` yang menghitung, `POST /lines` tidak ⇒ `total_shipped_by_cmt` tinggal 0 ⇒ **setiap** tagihan CMT lahir dengan `variance_flagged=True` (alarm "kiriman tidak cocok" yang selalu menyala = alarm yang diabaikan). Diperbaiki dengan satu helper `_recalc_receipt_totals()` + migrasi `backend/migrations/backfill_cmt_receipt_totals.py`.
3. **Job internal kehilangan pelaksana CMT** — `create_internal_job()` mematok `vendor_id=None / "Produksi Internal"`, padahal arahan owner #1 menyatakan produksi internal pun dilempar ke mitra CMT. Akibatnya Tracking Produksi menumpuk semua job di satu baris dan Portal Vendor mitra tidak pernah melihat job itu. Sekarang pelaksana **diwarisi dari PO** (PO tanpa vendor tetap "Produksi Internal" — tidak ada regresi).

### 5.3 Bukti MERAH tiap guard (Fase D)

| Guard | Bukti |
|---|---|
| NAV-FLAT | MERAH pada kode nyata: `[finance] section 'DASHBOARD & TRANSAKSI'` & `'AKUNTANSI & LAPORAN'` memakai `groups` |
| NAV-LABEL | MERAH pada kode nyata: `Retur Fisik (Gudang)`, group `Piutang (AR)`, `Pengadaan (P2P)` |
| NAV-MAX | MERAH pada section sintetis berisi 9 pintu |
| NAV-DUPTAB | MERAH pada hub sintetis yang tabnya = pintu lain di portal yang sama |
| NAV-DEADCALL | MERAH pada **cacat A yang ditanam ulang**: `apiGet('/production-monitoring-v2')` → `[production] pintu 'prod-monitoring' memanggil /api/production-monitoring-v2{} — TIDAK ADA route backend`; kembali HIJAU setelah dikembalikan |

Berkas bukti: `test_reports/guardrails/evidence/` (`INV-NAV-01_RED_before_fase_D.json`, `NAV_GUARD_SELFTEST_RED.txt`, `NAV_DEADCALL_RED_cacatA.txt`, `analyze_ia_production_AFTER.txt`).

**Catatan penting soal NAV-DEADCALL:** daftar route diambil dari **OpenAPI runtime** (1655 path) digabung hasil AST, karena AST saja melewatkan router yang prefix-nya dipasang di `include_router()` (mis. `/api/assets/loans` hanya muncul di OpenAPI). Bila backend mati, temuan otomatis diturunkan jadi WARN — menuduh "endpoint tidak ada" berdasar parser yang diketahui tidak lengkap adalah cara tercepat membuat guard diabaikan.

### 5.4 Verifikasi

- `bash scripts/gate.sh` → **12/12 PASS, VERDICT HIJAU** (`memory/GATE_RECEIPT.md`).
- `python3 scripts/guardrails/check_nav_map.py` → **HIJAU**, 12 portal · 40 section · 184 pintu · 360 id registry · self-test 6/6 guard menyala.
- `python3 scripts/analyze_ia_production.py` → Produksi: **4 section · 20 pintu · maks 6/section · 0 pakai groups**; **tidak ada satu pun portal yang masih memakai `groups`**.
- Baseline SSOT aksesoris `scripts/lib/acc_baseline.py` = **Rp 9.663.750 / 32.200 qty** (utuh, tidak melenceng).
- `testing_agent_v3` iteration_179: **backend 19/19 (100%)**, frontend 23/25 (2 temuan hanya soal deteksi teks otomatis, bukan bug), **0 critical**.
- `python3 tests/verify_ia_c_backend_fixes.py` → **8/8 PASS** (menguji 2 perbaikan yang belum tercakup agen: total header penerimaan CMT & pewarisan pelaksana job) — **self-cleaning**, 0 artefak tersisa.
- Data demo pintu Invoice dibuat lewat **alur nyata** (`scripts/seed_demo_cmt_billing_internal.py`, idempoten, sudah dipasang di `scripts/seed_demo_all.sh`): PO-INT-DEMO-4 (150 pcs @ Rp 15.000 ke CV Jahit Mitra CMT) → 2 penerimaan CMT (80+2 dan 65+3) → 2 tagihan (Rp 1.200.000 belum posting + Rp 975.000 sudah posting `JE-…-0005` ke akun 5-231).
