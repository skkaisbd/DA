# Development Plan — **REKAP HARIAN CMT** (sesi 2026-08-08, SELESAI)

> ⏭️ **SESI AKTIF SEKARANG = FASE 5 "`closed_at` — REKAP TANGGAL LAMPAU BERHENTI MENEBAK" — lihat bagian paling bawah berkas ini.**
> Bagian di bawah ini adalah arsip sesi Rekap Harian yang sudah selesai; jangan diulang.
>
> 🔜 **BERIKUTNYA (menunggu keputusan owner K-1…K-9): MASTER KATEGORI PRODUK · HPP · HARGA JUAL ·
> HUBUNGAN MASTER ↔ KATALOG MARKETING** — rencana lengkap + semua endpoint terpengaruh:
> **`docs/PLAN_MASTER_PRODUK_KATEGORI_HARGA.md`** (BAGIAN 1–7 master produk · **BAGIAN 8** katalog
> marketing: 11 gap, gate `INV-KATALOG`, fase F7–F9).
> Inventaris field: `memory/AUDIT_MASTER_PRODUK_INTERNAL.md` · bukti:
> `python3 scripts/_prove_master_produk_logic_gaps.py` (9/9) +
> `python3 scripts/_prove_catalog_master_gaps.py` (10/10, READ-ONLY).

> **STATUS: SELESAI & TERVERIFIKASI ✅**
>
> **BUKTI (semua dijalankan, bukan dikutip):**
> * `python3 test_core_rekap_harian.py` → **102/102 LULUS** (POC isolasi lewat HTTP sungguhan)
> * `python3 scripts/verify_rekap_harian.py` (gate baru **INV-REKAP**) → **22/22 HIJAU**
> * `bash scripts/gate.sh` → **18/18 PASS · VERDICT HIJAU** (17 gate lama + INV-REKAP)
> * `bash scripts/rebuild_frontend.sh` → build OK, frontend HTTP 200
> * testing agent iteration_38 → backend **14/14 (100%)**, frontend 100%, **0 bug, 0 action item**
> * Verifikasi UI klik-penuh oleh main agent → **10/10 user story PASS** (§5)
> * UANG: total tagihan CMT **2.435.000 → 2.435.000** (tidak bergeser)
> * Drift alat uji (`POCRK` / `__REKAPTEST__`) = **0**; AR invoice maklon yatim = **0**;
>   state demo dipulihkan persis seperti sebelum uji (surat jalan demo kembali `Sent`,
>   nol reminder rekap sisa)

> Sesi sebelumnya ("Portal CMT Override / Input Vendor CMT") juga SELESAI. Rencana + buktinya
> diarsipkan ke **`memory/PLAN_ARSIP_2026-08-08_CMT_OVERRIDE.md`** — jangan diulang.

---

## 0) Permintaan owner (verbatim)

> "**Rekap Harian**: Beri saya satu layar berisi vendor mana saja yang belum diisi hari ini,
> biar staf tidak ada yang terlewat."

Tempatnya **DI DALAM pintu "Input Vendor CMT"**, bukan pintu baru — staf sudah membuka layar
itu tiap pagi, dan dari rekap bisa langsung klik → isi. (Pintu baru = satu tempat lagi yang
harus diingat, dan rekap tanpa jalan ke pengisiannya hanya jadi laporan.)

### Keputusan owner (dikonfirmasi di awal sesi ini)

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Arti "sudah diisi hari ini" | **c — Per-tugas (checklist)**: satu baris per vendor, kolom per jenis pekerjaan (`Terima ✓ · Inspeksi — · Progress ✗ · Kirim —`) supaya kelihatan **yang kurang apa**, bukan cuma merah/hijau |
| 2 | Vendor mana yang muncul | **a — SEMUA vendor aktif** di master CMT (yang tidak punya pekerjaan tetap muncul, ditandai "tidak ada pekerjaan") |
| 3 | Vendor mengisi sendiri dari portalnya | **a — Dihitung "sudah diisi"**, tetap ditandai sumbernya (`vendor` / `staf DA`) |
| 4 | Munculnya di mana | **a — Tampilan PERTAMA** pintu "Input Vendor CMT"; kartu pilih vendor turun ke bawahnya |
| 5 | Tambahan | **Ketiganya**: (a) lihat tanggal lain, (b) Export Excel + PDF, (c) Kirim reminder ke vendor yang belum diisi |

---

## 1) Pemulihan lingkungan (SELESAI sebelum menyentuh kode)

`/app` kembali berisi **template kosong** (pola yang sama seperti sesi lalu). Dipulihkan:

1. `git clone --depth 1 https://github.com/gksaabajana/da` → `rsync` ke `/app`
   (kecuali `.git`, `.env`, `node_modules`, `.emergent`).
2. `mongorestore --gzip --drop` dari `backups/auto_20260807_190000` → **198 koleksi, 1218 dokumen**.
3. `EMERGENT_LLM_KEY=… bash scripts/bootstrap.sh` → **108 detik**, backend healthy,
   frontend static bundle HTTP 200, 6 akun login HTTP 200.
4. `python3 scripts/seed_cmt_override_demo.py` → 3 vendor CMT
   (`CV Jahit Mitra CMT`, `CV Tanpa Sistem CMT`, `CV Punya Akun CMT`) + PO 200 pcs +
   surat jalan `Sent` + reminder `pending` → kondisi persis akhir sesi lalu.

---

## 2) ⚠️ Audit dulu — definisi "terisi hari ini" TIDAK boleh ditebak

Rekap ini menyatakan sebuah vendor "belum diisi". Kalau definisinya salah, staf akan mengejar
vendor yang sudah setor (atau lebih buruk: **melewatkan** vendor yang belum) — dan angka
progress inilah dasar **tagihan CMT**. Karena itu 8 jalur tulis diperiksa satu per satu di
kode + tipe datanya diperiksa langsung di Mongo.

| Tugas harian | Koleksi | "Ada pekerjaan" (✗ kalau belum) | "Terisi hari ini" (✓) | Field waktu | Tipe di DB |
|---|---|---|---|---|---|
| Terima Material | `vendor_shipments` | `status='Sent'` | `status='Received'` + diterima hari ini | `received_at` | **TIDAK ADA / string** ⚠️ |
| Inspeksi Material | `vendor_material_inspections` | shipment `Received` & `inspection_status≠Inspected` | inspeksi dibuat hari ini | `created_at` | `Date` ✅ |
| Progress Produksi | `production_progress` | job `In Progress` | ada setoran bertanggal hari ini | `progress_date` | `Date` ✅ |
| Kirim (CMT→DA/buyer) | `buyer_shipment_items` | Σ`produced_qty` > Σ`qty_shipped` | ada dispatch hari ini | `dispatch_date` | `Date` ✅ |
| Balas Reminder | `reminders` | `status='pending'` | dibalas hari ini | `response_date` | `Date` ✅ |

### 🔴 BUG NYATA yang ditemukan audit (bukan bagian permintaan, tapi memblokir fitur ini)

**`received_at` tidak pernah ditulis server.** `PUT /api/vendor-shipments/{id}` menyimpan
`{**body, updated_at: now()}` — jadi satu-satunya sumber `received_at` adalah
`VendorReceiving.jsx:65` yang mengirim `received_at: new Date()` dari **browser**. Akibatnya:

1. nilainya masuk sebagai **string ISO**, sementara semua field waktu lain `Date` ⇒
   query rentang `{$gte: Date, $lt: Date}` **tidak akan pernah cocok** (Mongo membandingkan
   antar-tipe berdasarkan urutan BSON, bukan nilai) ⇒ kolom "Terima" akan **selalu ✗**;
2. jamnya **jam komputer staf** — kalau salah setel, tanggal penerimaan material ikut salah,
   dan tanggal itu dipakai laporan;
3. terbukti empiris: **0 dokumen** `vendor_shipments` punya field `received_at` sama sekali.

**Perbaikan:** server yang mengisi `received_at = now()` pada transisi `Sent → Received`
(mengabaikan kiriman browser). Kecil, di jalur uang, dan wajib ada supaya rekap tidak bohong.

### Jebakan desain yang ikut ditutup

**Reminder rekap tidak boleh membuat vendor abadi-merah.** Tombol "Kirim reminder" membuat
dokumen `reminders` berstatus `pending` — yang, kalau dihitung apa adanya, langsung membuat
kolom "Balas Reminder" jadi ✗ pada hari yang sama ⇒ vendor **tidak akan pernah bisa hijau**
dan tombolnya jadi jebakan. Karena itu reminder ber-`reminder_type='daily_recap'` dengan
`recap_date == tanggal rekap` **dikecualikan** dari hitungan "ada pekerjaan" pada tanggal itu
(hari berikutnya tetap dihitung — reminder yang tak dibalas memang pekerjaan tertunda).

---

## 3) Keputusan arsitektur

* **SSOT satu berkas** `backend/core/cmt_daily_recap.py` — definisi 5 tugas + perhitungannya.
  Endpoint layar, endpoint export, dan endpoint reminder **memakai fungsi yang sama**, jadi
  mustahil "layar bilang 3 vendor merah tapi Excel-nya 5".
* **Batas hari = WIB** lewat `utils.waktu.wib_day_bounds_utc()` (jam sistem container UTC;
  memakai `datetime.now()` polos akan salah selama 07 jam tiap hari — sudah jadi bug di repo ini).
* **Agregasi per-koleksi, bukan per-vendor** (`$group` by `vendor_id`) — jumlah query tetap
  konstan (±10) walau vendor CMT bertambah jadi ratusan.
* `production_progress` **tidak punya** `vendor_id` (menempel ke `job_id`) ⇒ vendor
  diresolusi lewat `production_jobs`, pola yang sama dengan `_vendor_filter()` di panel audit.
* Rekap **mengabaikan** header `X-CMT-Override-Vendor` (ini pandangan lintas-vendor milik
  staf). Akun vendor tetap **403** lewat `_guard()` yang sudah ada.

---

## 4) Yang akan dikerjakan

### 4.1 Backend
* **BARU** `core/cmt_daily_recap.py` — `TASKS`, `build_recap(db, day)`, `pending_vendor_rows()`.
* **BARU** `utils/cmt_recap_export.py` — `build_xlsx()` & `build_pdf()` (openpyxl + reportlab,
  keduanya sudah ada di `requirements.txt`; **tanpa dependensi baru**).
* `routes/cmt_override_routes.py` — 3 endpoint baru:
  * `GET  /api/cmt-override/daily-recap?date=YYYY-MM-DD`
  * `POST /api/cmt-override/daily-recap/remind` (idempoten per vendor per tanggal)
  * `GET  /api/cmt-override/daily-recap/export?date=&format=xlsx|pdf`
* `routes/vendor_shipment.py` — **BUG-FIX** `received_at` diisi server.

### 4.2 Frontend
* **BARU** `components/erp/cmt-override/CMTOverrideDailyRecap.jsx` — tabel checklist 5 kolom,
  navigasi tanggal (◀ / kalender / ▶ / "Hari ini"), kartu ringkasan, filter "hanya belum
  lengkap", tombol Export Excel/PDF, tombol Kirim reminder.
* `CMTOverridePortalModule.jsx` — rekap jadi **blok pertama**; klik chip ✗/✓ → `pickVendor()`
  dengan **tab modul yang relevan** langsung terbuka (bukan selalu Dashboard).

### 4.3 Alat & uji
* **BARU** `test_core_rekap_harian.py` — POC Fase 1, **satu** berkas, HTTP sungguhan.
* **BARU** `scripts/verify_rekap_harian.py` (gate **INV-REKAP**) + didaftarkan ke `scripts/gate.sh`
  ⇒ gate naik **17 → 18**.

---

## 5) User Stories — hasil verifikasi (10/10 PASS lewat LAYAR)

| # | Alur | Hasil |
|---|---|---|
| 1 | Buka "Input Vendor CMT" → rekap **langsung** terlihat paling atas | ✅ blok `cmt-recap-panel` dirender tanpa klik apa pun, di atas kartu vendor |
| 2 | Kelihatan **yang kurang apa** per vendor | ✅ 5 kolom; mis. `Terima: BELUM diisi · 1 surat jalan menunggu dikonfirmasi`, `Kirim: BELUM diisi · 40 pcs selesai belum dikirim` |
| 3 | Vendor tanpa pekerjaan tidak dihitung merah | ✅ **CV Punya Akun CMT** = badge "Tidak ada pekerjaan", semua kolom "—" |
| 4 | Dari rekap **langsung mengisi** | ✅ klik chip ✗ *Progress Produksi* → mode override **CV Jahit Mitra CMT** + tab **Progress Produksi** langsung aktif; "Ganti vendor" kembali ke rekap |
| 5 | Yang diisi **vendor sendiri** ikut ✓ dan ditandai | ✅ tanggal 8 Agu: baris CV Jahit Mitra CMT hijau/amber berlabel **"diisi vendor"**; setelah staf mengisi → **"diisi staf DA"** |
| 6 | Lihat **tanggal lain** | ✅ ◀ / kalender / ▶ / "Hari ini"; 9 Agu (2 merah) vs 8 Agu (1 merah + 1 sebagian) — isi tabel & kartu ringkasan ikut berubah, muncul badge "TANGGAL LAIN" + catatan *as-of* |
| 7 | **Unduh** rekap | ✅ `rekap-harian-cmt-20260809.xlsx` & `.pdf`; angka "BELUM diisi" di Excel == `summary.vendors_pending` API (diuji POC & gate) |
| 8 | **Tegur** vendor yang belum diisi sekali klik | ✅ panel konfirmasi mendaftar vendor + tugasnya → toast **"Reminder terkirim ke 2 vendor."**; klik kedua → **"Tidak ada yang dikirim — 2 vendor sudah ditegur untuk tanggal ini."**; reminder terlihat di **Inbox Reminder** vendor |
| 9 | Role tak berwenang tidak bisa menembus | ✅ `hr` → 403 di ketiga pintu (recap/remind/export), akun vendor → 403, tanpa token → 401 |
| 10 | Angka **tidak bergeser** karena fitur ini | ✅ tagihan CMT 2.435.000 → 2.435.000; nol dokumen sisa uji |

**Rantai penuh lewat layar (bukti bug-fix `received_at`):** chip ✗ *Terima Material* pada
CV Tanpa Sistem CMT → tab Penerimaan Material → tombol **"Konfirmasi Terima"** (dialog native
di-accept) → kembali ke rekap → kolom Terima berubah menjadi
**"Sudah diisi · 1 surat jalan diterima · diisi staf DA"** dan kolom **Inspeksi otomatis menjadi ✗
"1 kiriman belum diinspeksi"**. Sebelum perbaikan, perpindahan ini **mustahil** terjadi karena
`received_at` tersimpan sebagai string.

---

## 6) Status pengerjaan

| Fase | Isi | Status |
|---|---|---|
| 0 | Pulihkan lingkungan + audit write-path | ✅ SELESAI |
| 1 | Backend SSOT + 3 endpoint + bug-fix `received_at` + POC 102/102 | ✅ SELESAI |
| 2 | Frontend rekap + klik-tembus + export + reminder + rebuild | ✅ SELESAI |
| 3 | Gate INV-REKAP (22/22) + `gate.sh` 18/18 + testing agent 0 bug + dokumen memori | ✅ SELESAI |

### Konsekuensi terbuka / backlog berikutnya

1. **Job yang sudah ditutup tidak terhitung pada rekap tanggal lampau.** Kolom "menunggu" dihitung
   per akhir hari itu memakai stempel waktu peristiwa, tetapi `production_jobs` **tidak menyimpan
   kapan job ditutup** ⇒ job yang ditutup setelah tanggal itu tidak lagi terhitung "job jalan" pada
   tanggal itu. Sudah ditampilkan sebagai catatan di layar (`as_of_note`). Perbaikan sesungguhnya =
   menambahkan `closed_at` pada `production_jobs` (perlu migrasi + backfill).
2. **Rekap belum punya jadwal otomatis.** Owner hanya meminta layar; kalau nanti ingin "teguran
   otomatis tiap jam 16.00 WIB", jalurnya sudah ada (`utils/scheduler.py`) dan endpoint remind
   sudah idempoten, jadi tinggal didaftarkan.
3. **Kolom rekap tetap 5.** "Permintaan Material" & "Laporan Variance" sengaja TIDAK dijadikan
   kolom karena sifatnya kejadian luar biasa, bukan pekerjaan harian — menambahkannya membuat 7
   kolom yang hampir selalu "—" dan yang merah jadi sulit ditemukan.
4. Backlog sesi sebelumnya masih berlaku: badge di layar **Invoice CMT** belum diverifikasi VISUAL
   (baru tampil setelah AP matang); `dewi_cmt_payments` memakai DUA master CMT; warna baris BOM
   belum dibatasi ke `dewi_rnd_materials.colors[]`; `except Exception: pass` di 6 titik jalur
   stok/uang; 44 titik penomoran `count_documents()+1`.

---

## 7) Catatan lingkungan (jangan "diperbaiki" balik)

* Frontend = **STATIC BUNDLE** (`frontend/static_server.js`). Setiap perubahan `frontend/src`
  WAJIB diikuti `bash scripts/rebuild_frontend.sh`. Jangan `yarn start`.
* Sidebar hanya menampilkan pintu **section AKTIF**; taruh pintu penting di section pertama.
* Deep-link modul butuh **KEDUA** parameter: `/?portal=<portal>&module=<module-id>`.
* Beberapa aksi vendor memakai `window.confirm()` native ⇒ Playwright wajib
  `page.on("dialog", lambda d: d.accept())`.
* Password akun vendor demo `cmtvendor@dewiaditya.id` = **`Dewi@123`**;
  `cmt.punyaakun@dewiaditya.id` = **`Vendor@123`**. Kredensial lain: `memory/test_credentials.md`.
* Kalau menulis alat uji: bersihkan TURUNAN (`rahaza_ar_invoices`, `dewi_maklon_pos`,
  `dewi_cmt_component_requests`, `cmt_receipts`) dan lakukan **sweep seluruh koleksi**.


---
---

# FASE 4 — **REKAP MINGGUAN CMT** (sesi 2026-08-10, BERJALAN)

## 4.0) Pemulihan lingkungan (SELESAI sebelum menyentuh kode)

`/app` kembali berisi template kosong. Dipulihkan **dalam 159 detik**:

1. `git clone https://github.com/kamaaajahbamama/da` → `rsync` ke `/app`
   (kecuali `.git`, `.env`, `node_modules`, `__pycache__`).
2. `mongorestore --gzip --drop` dari `backups/auto_20260807_190000` → **1218 dokumen**.
3. `EMERGENT_LLM_KEY=… bash scripts/bootstrap.sh` → backend healthy, bundle statis
   HTTP 200, **6 akun login HTTP 200**.
4. `python3 scripts/seed_cmt_override_demo.py` → 3 vendor CMT demo (kondisi persis
   akhir sesi lalu). `GET /api/cmt-override/daily-recap` → **HTTP 200**.

**Temuan pemulihan:** `prefetch_context()` (todo "BE refactor `_prefetch()`") ternyata
**SUDAH ada dan sudah dipakai** `build_recap(ctx=…)` di commit terakhir — jadi kinerja
"7× build_recap tidak membaca master 7×" sudah tertangani, tinggal DIBUKTIKAN oleh POC.

## 4.1) ⚠️ Keputusan owner Rekap Mingguan — CARA MENDAPATKANNYA

Keputusan sesi lalu **hilang** (hanya judul todo yang tersimpan; `plan.md` belum
pernah ditulis — itu justru todo yang sedang berjalan saat sesi terputus). Karena
angka rekap = dasar **tagihan CMT**, definisinya **TIDAK ditebak**: owner ditanya
ulang. Jawaban pertama memilih dua opsi bertentangan pada 3 pertanyaan, jadi
ditanya sekali lagi sampai tunggal.

| # | Pertanyaan | Keputusan FINAL |
|---|---|---|
| 1 | Batas pekan | **7 hari terakhir BERGULIR** (`akhir−6 … akhir`), bukan Senin–Minggu ISO |
| 2 | Arti "hari terlambat" | **DUA angka terpisah, tidak ada yang dibuang**: `days_late` = hari `pending` (ada pekerjaan menunggu, NOL bukti) → merah, dipakai mengurutkan; `days_unfinished` = hari `pending`+`partial` (masih ada sisa) → amber |
| 3 | Kolom baris vendor | **Daftar lengkap**: 7 kotak hari · Terlambat · Belum beres · Hari tanpa setoran · Total pcs disetor · Total pcs dikirim · sparkline tren pcs · streak |
| 4 | Streak | **Rentetan beruntun PALING AKHIR**, dihitung mundur dari hari terakhir yang sudah berjalan; **putus** kalau ada hari `pending` **ATAU** `partial` |
| 5 | Tombol tab Mingguan | Export **Excel + PDF**; klik kotak hari → **pindah ke tab Harian tanggal itu**; **plus** tombol reminder yang menegur untuk **satu tanggal jelas** (hari terakhir yang sudah berjalan) memakai endpoint idempoten yang sama ⚠️ *interpretasi — owner memilih "ada" di ronde 1; mudah dicabut kalau tidak dikehendaki* |

### Aturan turunan yang ditulis EKSPLISIT (supaya tidak jadi tebakan berikutnya)

* **"Hari tanpa setoran"** = hari berjalan di mana vendor **punya job jalan**
  (`progress.state != 'none'`) tetapi `progress.done_today == 0`. Vendor yang memang
  tidak punya job TIDAK dihitung "tanpa setoran" — menghukum vendor karena tidak
  diberi pekerjaan adalah angka bohong.
* **Hari `idle` bersifat NETRAL untuk streak**: tidak memutus (vendor tidak salah
  apa-apa) tetapi juga tidak menambah (tidak ada prestasi). Hanya `done` menambah.
* **Hari di MASA DEPAN** (> hari ini WIB) diberi state `future`, **tidak** dihitung
  ke angka mana pun, dan `build_recap` tidak dipanggil untuk hari itu.

## 4.2) Keputusan arsitektur

* **`build_week()` TIDAK menghitung apa pun sendiri.** Ia memanggil `build_recap()`
  7× (dengan `ctx` bersama dari `prefetch_context()`) dan hanya **meringkas**
  hasilnya. Konsekuensi yang disengaja: mustahil tab Mingguan berdebat dengan tab
  Harian, karena angkanya memang benda yang sama. Ini juga yang diuji POC.
* **Sasaran tombol reminder mingguan = `pending_vendor_rows(recap[remind_date])`** —
  fungsi yang SAMA dengan tab Harian, jadi dua tombol tidak akan pernah memilih
  vendor berbeda untuk tanggal yang sama.
* **Pemilik state tanggal pindah ke `CMTOverrideRecapPanel.jsx`.** Kalau tiap tab
  menyimpan tanggalnya sendiri, klik kotak hari di Mingguan tidak akan bisa
  memindahkan tab Harian ke tanggal itu (permintaan owner 5) — jadi induknya yang
  memegang `day`, dan `CMTOverrideDailyRecap` dibuat **terkendali** (`day` +
  `onDayChange`), tetap punya state sendiri bila prop tidak diberikan.

## 4.3) Yang dikerjakan

**Backend**
* `core/cmt_daily_recap.py` — `WEEK_DAYS`, `week_range()`, `build_week()`.
* `utils/cmt_recap_export.py` — `build_week_xlsx()` + `build_week_pdf()`.
* `routes/cmt_override_routes.py` — `GET /api/cmt-override/weekly-recap`,
  `GET /api/cmt-override/weekly-recap/export?format=xlsx|pdf`.

**Frontend**
* **BARU** `cmt-override/CMTOverrideRecapPanel.jsx` — tab **Harian | Mingguan**, pemilik `day`.
* **BARU** `cmt-override/CMTOverrideWeeklyRecap.jsx` — 7 kotak hari per vendor,
  sparkline pcs, kolom terlambat/belum beres/tanpa setoran/streak, export, reminder.
* `CMTOverrideDailyRecap.jsx` — jadi terkendali (`day`/`onDayChange`).
* `CMTOverridePortalModule.jsx` — render Panel, bukan DailyRecap langsung.

**Alat & uji**
* `test_core_rekap_harian.py` — bagian mingguan (konsistensi harian↔mingguan,
  rentang bergulir, urutan, streak, hari tanpa setoran, export, RBAC, kinerja).
* `scripts/verify_rekap_harian.py` — invarian mingguan baru di gate **INV-REKAP**.

## 4.4) User Stories — hasil verifikasi (11/11 PASS)

| # | Alur | Hasil |
|---|---|---|
| 1 | Buka "Input Vendor CMT" → ada tab **Harian \| Mingguan**, Harian tetap tampil pertama | ✅ `cmt-recap-tabs` dirender; `cmt-recap-tab-harian` `data-active="true"` saat dibuka |
| 2 | Tab Mingguan menampilkan 7 kotak hari per vendor untuk 7 hari terakhir | ✅ 3 vendor × 7 kotak = 21 kotak; kepala kolom `Sel 4 … Sen 10` + badge "aman / N belum" per hari |
| 3 | Kelihatan vendor mana yang paling sering terlambat (terburuk di atas) | ✅ urutan `['late','late','idle']`, di antara yang terlambat `days_late` menurun `[2,1]` |
| 4 | Klik kotak hari → **pindah ke tab Harian pada tanggal itu** | ✅ klik kotak `2026-08-08` → tab Harian aktif dan `cmt-recap-date-input` = `2026-08-08` (bukan hari ini). Kepala kolom hari juga bisa diklik |
| 5 | Angka mingguan **sama** dengan angka harian tanggal yang sama | ✅ 7 hari × semua vendor cocok (POC §12, gate RK-21, testing agent Test 7 & 8). Contoh: sparkline 08-08 = 100 pcs, tab Harian 08-08 = "100 pcs progress masuk" |
| 6 | Tren pcs per hari terlihat + total pcs disetor/dikirim sepekan | ✅ sparkline SVG `data-values="0,0,0,0,100,0,0"`; kartu "Pcs disetor sepekan 100 / 60 pcs dikirim" |
| 7 | Streak terlihat & putus tepat pada hari `pending`/`partial` | ✅ "0 · putus: hari terlambat"; POC membuktikan pola *beres → tanpa pekerjaan → beres* = **streak 2** (hari tanpa pekerjaan NETRAL) |
| 8 | Unduh Excel + PDF mingguan; angkanya sama dengan layar | ✅ `rekap-mingguan-cmt-20260804-20260810.xlsx` & `.pdf` benar-benar terunduh; angka Excel == API DAN urutan baris == layar (gate RK-25) |
| 9 | Reminder dari tab Mingguan menegur untuk **tanggal yang jelas**, idempoten | ✅ panel konfirmasi menyebut `2026-08-10` + daftar vendor & tugasnya → "Reminder terkirim ke 2 vendor untuk tanggal 2026-08-10."; klik kedua → "Tidak ada yang dikirim — 2 vendor sudah ditegur untuk 2026-08-10" |
| 10 | Role tak berwenang 403; akun vendor 403; tanpa token 401 | ✅ `hr` → 403 di weekly-recap & exportnya, akun vendor → 403, tanpa token → 401, header override DIABAIKAN |
| 11 | UANG tidak bergeser & nol jejak data uji | ✅ tagihan CMT **2.435.000 → 2.435.000**; nol reminder rekap sisa; SJ demo kembali `Sent`; nol jejak `POCRK`/`__REKAPTEST__` |

## 4.5) Status pengerjaan Fase 4 — **SELESAI**

| Langkah | Isi | Status |
|---|---|---|
| 4.0 | Pulihkan lingkungan (clone → mongorestore 1218 dok → bootstrap 159s → seed demo) | ✅ SELESAI |
| 4.1 | Keputusan owner dicatat (ditanya ulang karena catatannya hilang) | ✅ SELESAI |
| 4.2 | BE `build_week()` + `week_range()` + export xlsx/pdf + 2 endpoint | ✅ SELESAI |
| 4.3 | POC `test_core_rekap_harian.py` → **169/169 LULUS** (102 lama + 67 mingguan) | ✅ SELESAI |
| 4.4 | FE `CMTOverrideRecapPanel` + `CMTOverrideWeeklyRecap` + `recapDates` + rebuild bundle | ✅ SELESAI |
| 4.5 | Gate **INV-REKAP 30 OK** (RK-20…RK-27 baru) + `gate.sh` **18/18 VERDICT HIJAU** | ✅ SELESAI |
| 4.6 | `testing_agent_v3` iteration_39 → backend **17/17**, frontend 100%, **0 bug, 0 action item** | ✅ SELESAI |
| 4.7 | Dokumen memori diperbarui (plan, README, HANDOFF, CHANGELOG, PRD, test_result) | ✅ SELESAI |

### Temuan sesi ini yang perlu diketahui agent berikutnya

1. **`prefetch_context()` sudah ada sebelum sesi ini** (commit terakhir sesi lalu) — todo "BE refactor
   `_prefetch()`" ternyata sudah selesai; yang kurang hanya BUKTI. Sekarang dijaga gate **RK-27**
   (mingguan tidak boleh lebih mahal daripada 7× harian) supaya refactor berikutnya tidak
   menghapusnya tanpa ada yang sadar.
2. **Berkas uji buatan testing agent diperbaiki, bukan dibuang.**
   `backend_test_fase4_mingguan.py` (17 uji, READ-ONLY — 32 GET + 4 login, tidak menulis apa pun jadi
   tidak perlu bersih-bersih) awalnya menyematkan tanggal MATI (`date=2026-08-08`,
   `future=2026-08-12`). Dua akibatnya: (a) **rusak besok** — uji "tanggal masa depan" mengasumsikan
   2026-08-12 = hari ini + 2; (b) **LULUS KOSONG** — uji `remind_pending` memakai tanggal yang di data
   demo NOL vendor merah, jadi ia membandingkan himpunan kosong dengan himpunan kosong dan mencetak
   "PASS (0 vendors)". Sekarang semua tanggal dihitung dari hari ini **WIB**, jendela yang dipakai =
   jendela BERJALAN (datanya tidak kosong ⇒ benar-benar membandingkan 2 vendor), dan bila suatu hari
   himpunannya kosong skrip **mengatakannya terus terang** alih-alih mencetak PASS yang menenangkan.
3. **Interpretasi yang perlu ditegaskan owner:** tombol reminder di tab Mingguan ADA (owner memilih
   "ada" pada ronde pertama), dan ia menegur untuk **hari terakhir yang sudah berjalan** memakai
   endpoint idempoten `POST /daily-recap/remind` yang sama. Mudah dicabut kalau owner ternyata hanya
   ingin tombol itu di tab Harian: hapus blok tombol + panel konfirmasi di
   `CMTOverrideWeeklyRecap.jsx` (backend tidak perlu diubah — `remind_date`/`remind_pending` hanya
   berhenti dipakai).

### Backlog terbuka (belum dikerjakan, bukan regresi)

1. ~~`production_jobs` **tidak menyimpan `closed_at`** ⇒ job yang ditutup setelah suatu tanggal tidak
   lagi terhitung "job jalan" pada tanggal itu (berlaku untuk harian DAN mingguan; sudah ditulis di
   `as_of_note` kedua layar). Perbaikan sesungguhnya = migrasi + backfill `closed_at`.~~
   ✅ **SELESAI di FASE 5** (lihat bagian paling bawah berkas ini) — `core/production_job_lifecycle.py`
   + migrasi backfill + gate RK-28/RK-28b/RK-29/RK-30.
2. Rekap belum punya **jadwal otomatis** (mis. teguran 16.00 WIB). Jalurnya sudah ada
   (`utils/scheduler.py`) dan endpoint remind sudah idempoten — tinggal didaftarkan.
3. Mingguan belum punya **perbandingan antar-pekan** ("pekan ini vs pekan lalu"). `?date=` sudah bisa
   menggeser jendela, jadi tinggal memanggil dua kali dan menampilkan deltanya.
4. Backlog sesi sebelumnya masih berlaku: badge layar **Invoice CMT** belum diverifikasi VISUAL;
   `dewi_cmt_payments` memakai DUA master CMT; warna baris BOM belum dibatasi ke
   `dewi_rnd_materials.colors[]`; `except Exception: pass` di 6 titik jalur stok/uang;
   44 titik penomoran `count_documents()+1`.

---
---

# FASE 5 — **`closed_at`: REKAP TANGGAL LAMPAU BERHENTI MENEBAK** (sesi 2026-08-10, SELESAI)

> **STATUS: SELESAI & TERVERIFIKASI ✅**
>
> **BUKTI (semua benar-benar dijalankan di lingkungan ini, bukan dikutip dari sesi lalu):**
> * `python3 test_core_rekap_harian.py` → **191/191 LULUS** (169 lama + 22 baru fase 5)
> * `python3 scripts/verify_rekap_harian.py` (INV-REKAP) → **34 OK / 0 FAIL**
>   (baru: **RK-28, RK-28b, RK-29, RK-30**)
> * `bash scripts/gate.sh` → **18/18 PASS · VERDICT HIJAU**
> * `bash scripts/gate.sh --full` → **22/22 PASS · VERDICT HIJAU** (18 + 4 alur produk HR)
> * `bash scripts/rebuild_frontend.sh` → build OK, frontend HTTP **200**
> * Verifikasi VISUAL sendiri (Playwright): peringatan job warisan tampil di tab **Harian**
>   DAN **Mingguan**, tanpa kalimat kembar dengan baris info abu-abu
> * UANG: tagihan CMT **2.435.000 → 2.435.000** (tidak bergeser, dicek sebelum & sesudah)
> * Nol jejak data uji (`POCRK` / `__REKAPTEST__` / `__FASE5VIS__`) tertinggal di DB

## 5.0) Kenapa fase ini ada — backlog nomor 1 fase 4

Fase 4 menutup rekap mingguan tetapi meninggalkan satu **kebohongan struktural** yang
ditulis jujur sebagai catatan di layar:

> `production_jobs` tidak menyimpan **kapan** job ditutup, jadi "job jalan pada tanggal X"
> dijawab dari **status SEKARANG**.

Akibat nyatanya: job yang dibuka **Senin**, tidak disetor Senin, lalu **ditutup Rabu**
**HILANG** dari rekap hari Senin. Padahal Senin itu vendor MEMANG punya pekerjaan yang tidak
dikerjakan. Rekap tanggal lampau jadi terlalu bersih — **kelalaian yang sudah terjadi terhapus
sendiri begitu job-nya ditutup**. Karena progress produksi adalah **dasar tagihan CMT**,
laporan yang memaafkan dirinya sendiri seperti itu tidak bisa dipakai memverifikasi apa pun:
setiap bantahan vendor ("saya tidak pernah bolong") tidak bisa diuji.

Ini bukan "sulit dihitung", tapi **mustahil** — datanya memang tidak pernah disimpan.

## 5.1) Keputusan arsitektur

| # | Keputusan | Alasan yang memaksa |
|---|---|---|
| 1 | **SATU penulis stempel**: `core/production_job_lifecycle.close_job()` | Ada **DUA** jalur penutup job (auto-complete `production_execution.py` + Quick Complete `production_pos.py`). Kalau masing-masing menulis `closed_at` sendiri, suatu hari salah satunya lupa atau menulis tipe berbeda — dan rekap tanggal lampau kembali bohong TANPA ada yang tahu. Ini pelajaran langsung dari bug `received_at` fase 3 |
| 2 | **`closed_at` TIDAK diterima dari body permintaan** | Persis cara `received_at` dulu masuk sebagai STRING dari jam komputer staf. Stempel yang dipakai laporan wajib ditulis SERVER |
| 3 | **SATU aturan "masih jalan saat itu"**: `was_open_at(job, moment)` | Dipakai rekap harian DAN mingguan. Kalau disalin, dua tab akan mulai berbeda pada kasus pinggir — dan itu angka tagihan |
| 4 | **Status tak dikenal dianggap TERBUKA** | Dua arah salahnya tidak seimbang: menganggap tertutup padahal terbuka membuat pekerjaan nyata HILANG dari rekap ⇒ progress tidak diisi ⇒ uang tidak bisa ditagih. Menganggap terbuka padahal tertutup hanya membuat satu baris tampak merah dan langsung diselidiki orang |
| 5 | **Tutup PERTAMA yang menang** (idempoten); stempel **perkiraan** migrasi boleh digantikan pengamatan sungguhan | Waktu tutup yang benar adalah yang pertama. Tapi tebakan tidak boleh mengalahkan fakta |
| 6 | Job warisan **TIDAK ditebak diam-diam** — `was_open_at` mengembalikan `False` (perilaku lama) dan jumlahnya **DIAKUI di layar** | Menebak tanggal untuk laporan yang dipakai memverifikasi tagihan lebih berbahaya daripada mengaku tidak tahu. Migrasi yang memperbaikinya, bukan asumsi |

## 5.2) Yang dikerjakan

**Backend**
* **BARU** `core/production_job_lifecycle.py` — `JOB_CLOSED_STATUSES`, `is_closed_status()`,
  `close_job()` (satu-satunya penulis `closed_at`), `was_open_at()`,
  `needs_closed_at_backfill()`.
* **BARU** `migrations/add_closed_at_to_production_jobs.py` — backfill job warisan dari
  `updated_at` (fallback `created_at`), ditandai `closed_at_estimated: True`; dokumen tanpa
  penanda waktu apa pun **DILEWATI dan dilaporkan**, bukan dikarang. Idempoten.
* `routes/production_execution.py` — jalur tutup #1 (auto-complete) memakai `close_job()`.
* `routes/production_pos.py` — jalur tutup #2 (Quick Complete) memakai `close_job()`.
* `core/cmt_daily_recap.py` — "job jalan" memakai `was_open_at()`; membawa `closed_at` +
  `closed_at_estimated` di proyeksi; melaporkan `legacy_jobs_without_closed_at`.

**Backend (lanjutan sesi ini — kejujuran yang sampai ke layar)**
* `core/cmt_daily_recap.py` — `as_of_note` **dipecah**: `as_of_note_base` (kalimat aturan) +
  `legacy_note` (kalimat AKSI). `as_of_note` tetap **utuh persis seperti sebelumnya** karena
  berkas export & pemanggil API lain membacanya sebagai satu kalimat. `build_week()`
  **mengambil** `legacy_note` dari rekap harian (tidak menyusun ulang) — kalau ditulis dua
  kali, suatu hari kedua layar akan menyuruh menjalankan migrasi yang berbeda.
  Bentuk respons dijaga tetap pada cabang "tidak ada vendor" (layar tidak boleh menebak
  apakah sebuah field ada).

**Frontend**
* `CMTOverrideDailyRecap.jsx` — peringatan **amber** `cmt-recap-legacy-jobs` (jumlah job
  warisan + perintah migrasi) + baris info abu-abu kini memakai `as_of_note_base`
  (jadi kalimatnya tidak kembar).
* `CMTOverrideWeeklyRecap.jsx` — peringatan **amber** `cmt-week-legacy-jobs`. Sebelum ini tab
  Mingguan **tidak pernah menyebut** keterbatasan itu sama sekali, padahal jendela 7 hari
  justru yang paling terpengaruh: satu job warisan bisa membuat beberapa kotak hari tampak
  lebih bersih daripada kenyataannya.

**Alat & uji**
* `test_core_rekap_harian.py` — §17 (`closed_at` ditulis server, tanggal lampau ikut terhitung,
  suntikan klien diabaikan) + §18 (migrasi backfill: diakui dulu, baru diperbaiki, idempoten,
  mingguan otomatis ikut benar). 169 → **191** pemeriksaan.
* `scripts/verify_rekap_harian.py` — **RK-28** (job ditutup hari ini tetap terhitung pada
  tanggal sebelumnya, tidak pada tanggal sesudahnya) · **RK-28b** (`closed_at`/`status` kiriman
  browser diabaikan) · **RK-29** (integritas SELURUH DB: nol job tertutup tanpa `closed_at`) ·
  **RK-30** (job warisan dilaporkan apa adanya ke layar harian DAN mingguan; `as_of_note` =
  `as_of_note_base` + `legacy_note`). 30 → **34** kode.

## 5.3) User Stories — hasil verifikasi (8/8 PASS)

| # | Alur | Hasil |
|---|---|---|
| 1 | Job dibuka H-2, tidak disetor, lalu **ditutup hari ini** → rekap H-1 tetap menampilkan "1 job jalan, belum ada setoran" | ✅ RK-28 `menunggu_kemarin=1` · POC §17 |
| 2 | Job yang sama **tidak lagi** terhitung pada tanggal SESUDAH penutupan | ✅ RK-28 `menunggu_besok=0` |
| 3 | `closed_at` tersimpan sebagai **tanggal BSON** yang ditulis server, bukan string dari browser | ✅ RK-28 `closed_at_tipe=datetime` · POC "closed_at hasil PENGAMATAN tidak ditandai perkiraan" |
| 4 | Browser mengirim `closed_at`/`status` saat membuat job → **diabaikan** | ✅ RK-28b (HTTP 400/diabaikan) · POC §17 |
| 5 | **Kedua** jalur penutup (auto-complete & Quick Complete) menulis stempel ⇒ nol job tertutup tanpa `closed_at` di seluruh DB | ✅ RK-29 `0` |
| 6 | Job warisan (tertutup sebelum fitur ada) **tidak ditebak**, tetapi jumlahnya **diakui** di layar Harian **dan** Mingguan beserta perintah migrasinya | ✅ RK-30 `harian=1, mingguan=1` · verifikasi visual: banner amber di kedua tab |
| 7 | Setelah migrasi dijalankan, job warisan itu **ikut terhitung** untuk tanggal lampau dan peringatannya **hilang** | ✅ POC §18 (`0 → 1` lalu catatan lenyap) |
| 8 | Angka Mingguan tetap **identik** dengan Harian setelah semua perubahan ini | ✅ RK-21 (`selisih: []`) · POC "mingguan otomatis ikut benar" |

## 5.4) Status pengerjaan Fase 5 — **SELESAI**

| Langkah | Isi | Status |
|---|---|---|
| 5.0 | Pulihkan lingkungan (clone → `mongorestore` 198 koleksi → bootstrap 220s → seed demo CMT) | ✅ SELESAI |
| 5.1 | BE `production_job_lifecycle.py` + 2 jalur tutup memakai `close_job()` + migrasi backfill | ✅ SELESAI |
| 5.2 | POC `test_core_rekap_harian.py` **191/191** | ✅ SELESAI |
| 5.3 | Gate **INV-REKAP 34 OK / 0 FAIL** (RK-28, RK-28b, RK-29, RK-30) | ✅ SELESAI |
| 5.4 | **Dokumen gate diperbarui** (docstring INV-REKAP: kelas masalah 11–14) | ✅ SELESAI |
| 5.5 | **Suite penuh diperiksa ulang** — `gate.sh` 18/18 & `gate.sh --full` 22/22 HIJAU (edit menyentuh jalur job produksi, jadi gate lain WAJIB dicek ulang) | ✅ SELESAI |
| 5.6 | FE: peringatan job warisan di tab Harian + Mingguan, rebuild bundle, verifikasi visual | ✅ SELESAI |
| 5.7 | Dokumen memori diperbarui (plan, README, HANDOFF, CHANGELOG, PRD, test_result) | ✅ SELESAI |
| 5.8 | `testing_agent_v3` end-to-end | ✅ SELESAI (lihat `test_result.md`) |
| 5.9 | **BUG SETUP diperbaiki di akarnya** — probe `1c-3` di `bootstrap.sh` + `.bootstrap_cache/` di-gitignore + `frontend/yarn.lock` di-commit (sebelumnya `yarn install` DILEWATI diam-diam pada setiap clone baru) | ✅ SELESAI (diuji dua arah) |

### Catatan lingkungan untuk agent berikutnya

* `/app` datang **kosong** (template) lagi. Dipulihkan: `git clone --depth 50
  https://github.com/kaanakamanaua/da` → `rsync` (kecuali `.env`, `.git`, `node_modules`) →
  `mongorestore --gzip --drop backups/auto_20260807_190000` (**198 koleksi**) →
  `EMERGENT_LLM_KEY=… bash scripts/bootstrap.sh` (**220s**) →
  `python3 scripts/seed_cmt_override_demo.py`.
* **`yarn install` DILEWATI diam-diam pada clone baru** sehingga
  `@simplewebauthn/browser@13.3.0` — dipakai `src/pages/AbsenPage.jsx` — **tidak terpasang** dan
  `yarn build` MERAH (`Module not found`), yang muncul sebagai `build/ MISSING` di ringkasan
  bootstrap. **Akar masalahnya ditemukan sesi ini** (bukan "lockfile drift" seperti dugaan
  Session #25): `.bootstrap_cache/fe.md5` ikut TER-COMMIT ke repo, `frontend/yarn.lock` TIDAK ada
  di repo (jadi `FE_HASH` = md5(package.json + yarn.lock milik TEMPLATE platform) → nilainya
  reproducible persis sama setiap sesi ⇒ marker selalu cocok), dan `node_modules/` milik template
  platform sudah ada ⇒ **ketiga** syarat skip terpenuhi. **SUDAH DIPERBAIKI**: probe kenyataan
  `1c-3` di `scripts/bootstrap.sh` + `.bootstrap_cache/` masuk `.gitignore` +
  `frontend/yarn.lock` kini di-commit. Obat manual kalau gejalanya kembali:
  `cd /app/frontend && yarn install --prefer-offline` lalu `bash scripts/rebuild_frontend.sh`.
* Backup di repo hanya sampai `auto_20260807_190000`, jadi data demo CMT harus di-seed ulang
  (`vendor_partners` = master CMT, bukan `dewi_cmt_vendors`).

### Backlog terbuka (belum dikerjakan, bukan regresi)

1. Rekap belum punya **jadwal otomatis** (mis. teguran 16.00 WIB). Jalurnya sudah ada
   (`utils/scheduler.py`) dan endpoint remind sudah idempoten — tinggal didaftarkan.
2. Mingguan belum punya **perbandingan antar-pekan** ("pekan ini vs pekan lalu"). `?date=`
   sudah bisa menggeser jendela, jadi tinggal memanggil dua kali dan menampilkan deltanya.
3. `closed_at` belum dipakai di luar rekap CMT. Layar lain yang masih bertanya "job jalan?"
   dari status sekarang (mis. laporan produksi harian) bisa ikut memakai `was_open_at()`.
4. Backlog sesi sebelumnya masih berlaku: badge layar **Invoice CMT** belum diverifikasi VISUAL;
   `dewi_cmt_payments` memakai DUA master CMT; warna baris BOM belum dibatasi ke
   `dewi_rnd_materials.colors[]`; `except Exception: pass` di 6 titik jalur stok/uang.

