# ANALISIS — PDF Payslip · Surat Jalan (Vendor/Maklon) · Absen Portal Saya · Overlap Menu Lama

> Sesi analisis (read-only, TANPA rebuild UI / TANPA implementasi). Grounded ke kode nyata.
> Tujuan: memahami konteks 3 area yang diminta user + memetakan overlap dengan modul "adopsi lama".

---

## RINGKASAN EKSEKUTIF (TL;DR)

| # | Area | Temuan inti | Dampak |
|---|------|-------------|--------|
| A | **PDF Payslip / Slip Gaji** | PDF **sudah ada** (`rahaza_payroll_payslips.py`, A5, watermark RAHASIA) tapi **hardcode** "CV. DEWI ADITYA", **tidak** baca `company_settings`, **tidak** terdaftar di framework konfigurasi PDF (`pdf_export_configs`). | Tidak bisa dibranding/dikustom; header salah bila nama PT berubah. |
| B | **Surat Jalan (SJ)** | Ada **3 sub-sistem SJ paralel** (lihat §B). Yang dipakai flow vendor/maklon baru = SSOT `wh_delivery_notes` (`wms_delivery_notes.py`) — **hardcode** nama+alamat, **tanpa logo**, **tanpa config**. | Overlap dokumen; SJ baru tidak sinkron dengan konfigurasi lama. |
| C | **Absen Portal Saya** | Portal Saya "Kehadiran" (`self-dashboard`) sekarang **redirect ke `/absen`** (selfie+GPS+AI / WebAuthn). Check-in **langsung** lama (`/attendance/clock-in`, source `operator`) masih ada di backend tapi FE hanya dipakai di `_archive/OperatorView.jsx`. | Multiple entry-point absen; perlu pastikan tidak ada jalur langsung yang bocor. |
| D | **Overlap menu lama** | `prod-shipments-vendor` & `prod-shipments-buyer` (production POS lama, PDF `operations_pdf.py`) **masih aktif & muncul di 2 portal** (Produksi + Maklon), fungsinya overlap dengan `wms-cmt-dispatches` + `wms-delivery-notes` (SSOT baru). | Dua cara "kirim ke vendor/CMT" + dua generator SJ hidup bersamaan. |
| E | **Bonus bug: `company_settings` drift** | Doc hasil seed **tanpa** field `type:'general'`, sedangkan `admin.py`/`operations_pdf.py` query `{'type':'general'}` → tidak ketemu → fallback "Garment ERP"/"PT Garment ERP System" + berpotensi buat **doc kedua** yang konflik. | Bahkan PDF lama pun **tidak** menampilkan nama perusahaan asli sekarang. |

> **Kabar baik:** Infrastruktur branding PDF **sudah tersedia** — `company_settings` sudah punya
> `company_logo_url`, `pdf_header_line1/2`, `pdf_footer_text`, alamat, telp, dll, + UI admin
> `CompanySettingsModule.jsx`. Payslip & SJ SSOT tinggal *disambungkan* ke sumber ini (tidak
> perlu bikin framework baru).

---

## A. PDF PAYSLIP / SLIP GAJI

**File:** `backend/routes/rahaza_payroll_payslips.py`
- `_build_payslip_pdf(slip, run)` — reportlab, ukuran **A5**, watermark "RAHASIA".
- Endpoint: `GET /payslips/{pid}/pdf` (satu slip) + `GET /payroll-runs/{run_id}/pdf` (satu run bulk).
- **Line 89-94:** komentar "Get company config (optional)" tetapi nama perusahaan **di-hardcode**
  `"CV. DEWI ADITYA"` (line 93) dan subjudul `"Industri Garmen · CV. Dewi Aditya"` (line 105).
- **Tidak** ada import `company_settings`, **tidak** ada logo, **tidak** ada alamat/NPWP.

**Framework konfigurasi PDF** (`operations_pdf_configs.py` + `PDFConfigModule.jsx`):
- Tipe yang didukung: `production-po` (SPP), `vendor-shipment`, `buyer-shipment-dispatch`,
  `production-report`, + 9 tipe report. **Payslip TIDAK ada** di daftar `PDF_COLUMN_DEFINITIONS`.
- FE `PDF_TYPE_LABELS` juga tidak punya payslip.

**Kesimpulan A:** Payslip PDF fungsional tapi **statis** — tidak terhubung ke `company_settings`
maupun ke framework konfigurasi PDF. Ini persis yang dimaksud user "belum ada pdf configuration-nya".

---

## B. SURAT JALAN — TIGA SUB-SISTEM PARALEL (OVERLAP)

| Sistem | File | Collection/Sumber | Baca company_settings? | Logo? | Config? | Status |
|---|---|---|---|---|---|---|
| **1. SSOT baru** | `wms_delivery_notes.py` `GET /{sj_id}/pdf` | `wh_delivery_notes` (SJ-CMT/MAKLON/SUPPLIER/INTERNAL/ONLINE) | ❌ hardcode "CV. DEWI ADITYA" + alamat (line 324-325) | ❌ | ❌ | **AKTIF** — dipakai flow vendor/maklon/CMT baru (auto-create SJ) |
| **2. Production POS lama** | `operations_pdf.py` `GET /export-pdf` | `production_pos`/`vendor_shipment`/`buyer_shipment` | ✅ (tapi hanya `company_name`, via `{'type':'general'}` → lihat §E) | ❌ | ✅ (`vendor-shipment`, `buyer-shipment-dispatch`) | **AKTIF** — `prod-shipments-vendor/buyer` |
| **3. Rahaza shipments** | `rahaza_shipments.py` `/shipments/{id}/pdf` | `rahaza_shipments` | ✅ | ❌ | — | **DEPRECATED** (startup log) — modul FE sudah di-comment (`RahazaShipmentsModule` line 173-174), redirect ke `wms-delivery-notes` |

**Konteks "perubahan portal vendor & maklon":**
- Flow baru (plan.md Flow #4 CMT Vendor): `wms-cmt-dispatches` → execute → **auto-create `wh_delivery_notes` `sj_type=SJ-CMT`**.
- Jadi SJ kanonik sekarang = **sistem #1** (`wms_delivery_notes`), tetapi PDF-nya **paling primitif**
  (hardcode, tanpa logo, tanpa config) — kebalikan dari sistem #2 lama yang justru punya config.

**Kesimpulan B:** SJ baru (yang benar-benar dipakai vendor/maklon) perlu "disesuaikan" agar:
(1) baca `company_settings` (+logo), (2) opsional masuk framework config, (3) label tipe SJ sesuai
konteks penerima (CMT vs Klien Maklon vs Supplier). Sistem #2 lama (vendor-shipment/buyer-dispatch)
= kandidat kuat untuk **dikonsolidasi/di-deprecate** setelah SJ SSOT dilengkapi.

---

## C. ABSEN PORTAL SAYA (CHECK-IN)

**Alur saat ini:**
- Menu Portal Saya "Kehadiran" = `self-dashboard` → `SelfServicePortal.jsx`.
- `SelfServicePortal` **read-only** (GET `/api/rahaza/self/attendance`), + tombol
  **"Absen Sekarang"** (`data-testid="absen-now-btn"`, line 107) → `window.location.href='/absen'`.
- `/absen` → `pages/AbsenPage.jsx` (halaman mandiri, App.js line 502). Metode:
  - **Selfie + GPS + AI face-match** → `POST /api/rahaza/attendance/selfie/clock-in|out` (default).
  - **WebAuthn biometrik** → `POST /api/rahaza/attendance/webauthn/clock-in|out` (+register).
  - Status → `GET /api/rahaza/attendance/my-status`.

**Sistem absen (semua menulis ke SSOT `rahaza_attendance_events`):**
| Entry-point | Endpoint | source/method | Dipakai di FE |
|---|---|---|---|
| Langsung (lama) | `/attendance/clock-in`,`/clock-out` | `operator` | **hanya** `_archive/OperatorView.jsx` (arsip) |
| Selfie+GPS+AI (baru) | `/attendance/selfie/clock-in|out` | `selfie_geo_ai` | `/absen` (AbsenPage) ✅ |
| WebAuthn (baru) | `/attendance/webauthn/clock-in|out` | `webauthn` | `/absen` (AbsenPage) ✅ |
| ZKTeco device | `/attendance/zkteco/*` | `device_zkteco` | konfig HR |
| Manual HR (grid) | `/attendance/grid`,`/bulk` | manual | `RahazaAttendanceModule` (HR) |

**Kesimpulan C:** "tadi langsung checkin" = perilaku **lama** (clock-in langsung tanpa verifikasi,
via OperatorView yang kini diarsip). Sekarang Portal Saya sudah diarahkan ke `/absen`
(selfie/GPS/biometrik). SSOT collection **tunggal** (bagus, tidak ada double-write data). Yang perlu
dipastikan (analisis, bukan fix): (1) tidak ada tombol lain yang masih memanggil `/attendance/clock-in`
langsung; (2) apakah endpoint `clock-in` langsung mau **dipertahankan** (fallback HR) atau
**ditutup** agar semua absen mandiri lewat selfie/biometrik.

---

## D. OVERLAP MENU "ADOPSI LAMA" (fokus area di atas)

**Duplikasi menu nyata (dari `portalNav.js`):**
- `prod-shipments-vendor` ("Kirim Material Vendor") muncul di **Produksi** (line 177) **dan Maklon** (line 490).
- `prod-shipments-buyer` ("Dispatch ke Buyer") muncul di **Produksi** (line 178) **dan Maklon** (line 491).
- Keduanya = `EngineVendorShipmentModule` (production POS lama, PDF via `operations_pdf.py`).

**Overlap fungsional "kirim ke vendor/CMT":**
- LAMA: `prod-shipments-vendor` (vendor_shipment + operations_pdf SJ).
- BARU: `wms-cmt-dispatches` ("Kirim CMT", Gudang) → auto SJ-CMT di `wh_delivery_notes` +
  `wms-delivery-notes` ("Surat Jalan", Gudang).
- ⇒ **Dua jalur** mengirim material ke pihak ketiga menghasilkan **dua jenis Surat Jalan** berbeda.

**Sinyal deprecation lain (startup log) — konteks "adopsi lama" (di luar 3 area, tidak wajib disentuh):**
- `/api/accessories/*` → `/api/acc/items/*`; `/api/rahaza/shipments/*` → `/api/wms/delivery-notes/*`;
  `/api/wms/opname/*` → `/api/wms/opname2/*`; `/api/acc/internal-requests/*` → `/api/dewi/accessory-requests`;
  `warehouse_stock/movements/locations/opname` (GEN 1) → SSOT rahaza.
- File backup/legacy: `*_backup.py` (dewi_accessories_full, marketing_catalog, dewi_portal_saya,
  rahaza_auto_attendance), `dewi_kpi.py.old`, `dewi_kpi.py.pre-refactor-backup`.

**Kesimpulan D:** Overlap yang **relevan ke flow user** = jalur SJ vendor/buyer lama vs jalur
CMT-dispatch/SSOT baru + menu duplikat di 2 portal. Overlap lain (aksesoris/opname/notifikasi) sudah
di-deprecate secara backend & **tidak mengganggu flow utama** (sesuai kata user: "tidak apa apa jika
tidak mempengaruhi flow utama").

---

## E. BONUS — BUG DRIFT `company_settings` (mempengaruhi SEMUA PDF)

- **Seed** (`auth.py seed_initial_data`) → doc: `{company_name:'CV. DEWI ADITYA OFFICIAL',
  company_address:'Sragen, Jawa Tengah', company_tagline, npwp, phone, email}` — **tanpa `type`**.
- **admin.py** & **operations_pdf.py** query `company_settings.find_one({'type':'general'})`.
- Live DB: 1 doc, `type=None` ⇒ query `{'type':'general'}` **tidak match** ⇒ fallback default
  ("Garment ERP" / "PT Garment ERP System"), dan GET `/admin/company-settings` akan **membuat doc
  kedua** `type:'general'` bernama "PT Garment ERP System" (konflik nama).
- **Akibat:** meski `operations_pdf.py` "mendukung" company_settings, **saat ini PDF lama pun tidak
  menampilkan nama perusahaan seed**. Perlu diselaraskan (satu skema + `type:'general'`).

---

## REKOMENDASI (untuk keputusan user — BELUM dieksekusi)

**Prioritas 1 — Branding & config PDF (sumber tunggal):**
1. Selaraskan `company_settings` (skema tunggal + `type:'general'`, migrasi doc seed). *(fix drift §E)*
2. Buat helper bersama `get_company_profile(db)` → dipakai payslip PDF + SJ SSOT PDF.
3. Payslip PDF: baca company profile (+logo, +alamat/NPWP) alih-alih hardcode; opsional daftarkan
   `payslip` ke framework `pdf_export_configs` (pilih kolom komponen gaji).
4. SJ SSOT PDF (`wms_delivery_notes`): baca company profile (+logo); label penerima kontekstual
   (CMT / Klien Maklon / Supplier / Internal / Online).

**Prioritas 2 — De-overlap (butuh keputusan, menyentuh IA/menu):**
5. Putuskan nasib jalur SJ lama `prod-shipments-vendor/buyer` (operations_pdf): pertahankan sbg
   "vendor shipment inspeksi" atau redirect ke SSOT `wms-delivery-notes` (pola `LEGACY_MODULE_TO_PORTAL`).
6. Hilangkan **duplikasi** `prod-shipments-vendor/buyer` di portal Maklon **atau** Produksi (pilih satu owner).

**Prioritas 3 — Absen (konfirmasi kebijakan):**
7. Tetapkan apakah `/attendance/clock-in` langsung ditutup untuk self-service (hanya selfie/biometrik)
   atau dipertahankan sebagai fallback HR. Pastikan tidak ada tombol FE aktif yang memanggilnya langsung.

> Catatan: SEMUA di atas TANPA rebuild UI — hanya sambungkan data ke view statis yang sudah ada,
> plus penyesuaian generator PDF backend & (opsional) redirect menu.
