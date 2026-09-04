# SESI 2026-08-14 (#8c) — **IMPOR BERTINDIH**: deteksi dobel di pratinjau + lubang stok/uang ditutup

> Pertanyaan pemilik: impor tanggal 1–7 lalu 5–12 ⇒ apakah dobel tanggal 5–7 terdeteksi, dan apakah
> baris yang sama (kunci: no. pesanan) ikut terupdate bila di berkas baru statusnya berubah jadi
> dibatalkan?

**Jawabannya YA untuk keduanya**, tetapi audit menemukan **cacat uang/stok** pada jalur itu:
mode "Perbarui yang lama" menulis `status` dengan `$set` mentah ⇒ pesanan yang dibatalkan berkas
baru **tidak melepas reservasi stok** (risiko barang sama dijanjikan ke dua pembeli), tetap di
antrean gudang, dan status bisa **MUNDUR** saat berkas lama diunggah ulang. Sekarang status wajib
lewat SSOT `core.order_status.apply_status` (`forward_only` + bukti batal/retur + pelepasan
reservasi + jejak), dan penolakan transisi dijelaskan di catatan hasil.

**Deteksi dobel dipindah ke PRATINJAU** (dulu hanya muncul sesudah commit): respons unggah/pemetaan
membawa `duplicates` = jumlah `existing`/`new`, kunci dedupe yang dipakai, rentang tanggal berkas,
**rentang tanggal yang bertindih**, dan contoh baris + status sekarang. Layar langkah 5
menampilkannya persis di atas pemilih "Lewati / Perbarui yang lama".

**Bukti:** `test_core_f8_assign_ingat_scorecard.py` **47/47 PASS** (13 penjaga baru seksi `[D]`).

**Catatan penting:** pencocokan **per BARIS** (kunci dedupe), **bukan per rentang tanggal** — jadi
mengimpor rentang beririsan tidak pernah melahirkan baris kembar. Untuk **laporan iklan Shopee**
justru sebaliknya: periode yang beririsan **ditolak 409** karena biayanya per-periode (anti dobel
hitung anggaran).

---

# SESI 2026-08-14 (#8b) — **F8 SELESAI**: Assign Toko (SPV) · “Ingat Pemetaan Saya” · Scorecard Kreator

> Permintaan user: **(1)** “Selesaikan layar SPV untuk menetapkan staf pemegang tiap toko lengkap
> dengan riwayatnya”, **(2)** “Tawarkan pemetaan kolom yang tersimpan dari impor sebelumnya agar
> berkas rutin harian langsung siap sekali klik”, **(3)** “Tampilkan konten dan omzet tiap kreator
> dengan target vs aktual, tanpa mencampur GMV KPI dan omzet pesanan”.

## 0) TEMUAN AUDIT — ketiganya SUDAH ADA, yang belum ada justru yang membuatnya bisa DIPERCAYA

| Fitur | Keadaan sebelum sesi ini | Yang sebenarnya hilang |
|---|---|---|
| Assign Toko | endpoint + layar (tab “Assign Staf”) lengkap | **alasan tidak wajib** (padahal kepala berkasnya menjanjikan), **jejaknya dimusnahkan gate**, tidak ada sudut pandang per-ORANG, staf nonaktif tak ditandai |
| Ingat Pemetaan | mesin sudah mengingat & memakai ulang pemetaan | **diingat DIAM-DIAM** (layar tak pernah menyebutnya), **tidak bisa dilupakan**, **pemetaan basi diterima apa adanya** |
| Scorecard Kreator | 15 kolom, 3 sumber uang dipisah, basis penilaian tertulis | **tidak bisa ditelusuri** (tak ada jalan melihat konten/pesanan/sesi pembentuk angka), tanpa paginasi/CSV, dan **layarnya selalu kosong** karena tak ada seed kreator |

### CACAT NYATA YANG DITEMUKAN & DITUTUP
`test_core_f7_kpi_impor.py` membersihkan dirinya dengan
`delete_many({"account_id": aid, "entity": "marketing_platform_accounts"})` pada
`marketing_change_log`. Toko uji = **toko shopee aktif pertama (toko NYATA)**. Artinya **setiap
`bash scripts/gate.sh` memusnahkan seluruh riwayat “siapa memegang toko ini”** — satu-satunya
jawaban untuk “kenapa akses toko saya dicabut?”. Diukur: `marketing_change_log` = **0 dokumen**
walau log backend memuat perubahan assign. Sekarang hanya baris bertanda `[gate-kpiimpor]` yang
dihapus, dan penjaga statik `A-2e` menahannya kalau kembali longgar.

## 1) YANG DIKERJAKAN

### A. Assign Toko (SPV)
* **Backend** (`routes/marketing_account_assign.py`): `reason` **WAJIB** (≥4 huruf ⇒ 400 dengan
  contoh kalimat) diperiksa SESUDAH validasi daftar staf supaya galat spesifik tidak tertutup ·
  `GET /by-staff` (satu staf memegang toko apa; **staf dengan 0 toko ikut terdaftar** — dialah yang
  melihat layar kosong) · `GET /history` (riwayat SEMUA toko, berpaginasi, berlingkup F6) ·
  staf berakun **NONAKTIF** ditandai + `warnings[]` (“tidak ada orang yang bisa login untuk toko
  ini”) · `overview` menambah `unassigned_count`/`stale_count` (toko yang seluruh pemegangnya
  nonaktif dihitung **belum terpegang**).
* **Layar** (`AccountAssignView.jsx`): **3 tampilan** (Per Toko · Per Staf · Riwayat) · pencarian +
  filter “hanya yang belum terpegang” + paginasi 10/hal · tombol **Simpan terkunci** sampai alasan
  diisi (dengan hint yang menjelaskan kenapa) · **panel akibat MENETAP** (nama toko, alasan yang
  tercatat, efek 403, peringatan akun nonaktif) — bukan toast 5 detik.

### B. “Ingat Pemetaan Saya”
* **Backend** (`routes/marketing_data_import.py`): respons unggah kini membawa **`format_memory`**
  (`use_count`, `last_used_at`, `last_used_by`, `saved_at`, `dropped[]`) · pemetaan tersimpan
  **DIVALIDASI terhadap skema**: entri yang menunjuk field yang sudah tidak ada **dibuang** dan
  kolomnya **dipetakan ulang mesin** (dulu diterima apa adanya ⇒ kolomnya hilang dari hasil tanpa
  galat) · kolom berkas yang tidak ada di ingatan tetap memakai hasil mesin ·
  `GET /formats` (daftar yang diingat) · `DELETE /formats/{fingerprint}?source_type=` (**lupakan**).
* **Layar** (`DataImportWizard.jsx`): panel **“Pemetaan ini DIINGAT dari impor sebelumnya”** —
  dipakai N×, terakhir oleh siapa & kapan, **“ini bukan tebakan AI”**, peringatan bila ada pemetaan
  yang dibuang · tombol **“Lupakan pemetaan ini”** + keterangan menetap sesudahnya · dialog daftar
  semua susunan kolom yang diingat (bisa dibuka **sebelum** unggah dari langkah 3).

### C. Scorecard Kreator
* **Backend** (`routes/marketing_targets.py`): `GET /creator/{id}/detail` — **konten · pesanan ·
  sesi** baris demi baris; totalnya memakai **sumber rumus yang SAMA** dengan scorecard
  (`EXCLUDED_FOR_REVENUE`, `order_revenue_product`) sehingga wajib sama persis; pesanan yang
  dikecualikan **tetap tampil** dengan `counted:false` + sebabnya.
  **PERLU KEPUTUSAN PEMILIK (dibuat TERLIHAT, tidak diubah diam-diam):** `EXCLUDED_FOR_REVENUE`
  hanya memuat `cancelled`, jadi pesanan **`returned` IKUT dihitung** sebagai omzet. Mengubahnya
  menyentuh F2 (rekap harian) & F5 (siklus target) sekaligus ⇒ respons rincian memuat catatan
  “PERLU KEPUTUSAN PEMILIK …” beserta jumlah & nilainya.
* **Layar** (`CreatorScorecardView.jsx`): klik **“Lihat asalnya”** ⇒ dialog rincian (4 kartu total +
  3 tab daftar, tanpa satu pun angka gabungan) · paginasi 10/hal · pencarian kreator ·
  **unduh CSV** (kolom uang tetap terpisah, sengaja tanpa kolom “total”) · CTA “Tetapkan target
  kreator”.
* **Seeder** `backend/scripts/seed_marketing_creator_demo.py` (idempoten, **tidak** membuat master
  toko baru, sengaja menyisakan 1 kreator tanpa target & 2 konten tanpa KPI) + didaftarkan di
  `scripts/bootstrap.sh`. Tanpa ini layar Scorecard selalu berbunyi “belum ada kreator” pada
  environment segar — fitur jadi tampak belum jadi dan cacatnya tak pernah terlihat.

## 2) BUKTI

* `python3 test_core_f8_assign_ingat_scorecard.py` → **34 PASS · 0 GAGAL**.
* **Dibuktikan MERAH (25/34)** saat tiga fitur dilepas sekaligus (alasan dijadikan opsional,
  `format_memory` dimatikan, pembersihan gate dikembalikan ke versi lama) → dipulihkan ⇒ 34/34.
* `bash scripts/gate.sh` → **25/25 VERDICT HIJAU** (gate baru **INV-MKTOPS**).
* Verifikasi layar sendiri (Playwright, bundel statis baru), **0 console/page error**:
  A1 3 tampilan + cari (“1 dari 3 toko”) + paginasi · A2 Simpan terkunci tanpa alasan (juga saat
  “ab”), sesudah disimpan panel akibat menetap menyebut alasannya · A3 Riwayat global memuat baris
  baru (pelaku · ditambah · alasan) & Per Staf berubah 0 ⇒ 1 toko · B1 dialog daftar format ·
  B2 panel “sudah dipakai 2× — terakhir oleh admin@garment.com” · B3 lupakan ⇒ panel hilang +
  keterangan menetap · C1 3 kreator dengan **3 basis penilaian berbeda**, 1 “Belum ada target” +
  CTA, cari “rina” ⇒ 1 baris · C2 dialog rincian (Konten 5 · Pesanan · Sesi 2) dengan tanda
  “tidak dihitung” beserta sebabnya · regresi 3 tab konten + Daftar Toko tanpa crash.
* Agen uji (iter 57 & 58): **0 bug ditemukan**; keduanya berhenti karena sesi Playwright antar
  panggilan terputus (batasan lingkungan uji) — sisa cerita diselesaikan main agent dalam satu sesi.

## 3) SISA / LANGKAH BERIKUTNYA

1. **KEPUTUSAN PEMILIK:** apakah pesanan **`returned`** harus keluar dari omzet? Kalau ya, itu
   perubahan lintas-F2/F5 (rekap harian + siklus target + scorecard) dan wajib satu kartu kerja
   sendiri beserta gate-nya.
2. Berkas **Ekspor B & C asli** masih dibutuhkan untuk melepas label “pemetaan perlu diperiksa”.
3. Sesi live kreator masih dua bentuk field (`viewers` vs `peak_viewers` di seeder lama
   `scripts/seed_marketing_demo.py`) — seeder itu satu-satunya penulis yang tidak menulis
   `viewers`, sehingga kolom “Penonton” 0 untuk data lamanya. Rapikan bila seeder itu dipakai lagi.

---

# SESI 2026-08-14 (#8) — **F3 SELESAI**: Impor Ekspor B/C (status pengiriman) + “Batalkan impor” yang menepati janji

> Lanjutan sesi #7 yang berhenti **di tengah edit layar** (`DataImportWizard.jsx`): JSX penolong
> pemetaan sudah ditulis, tetapi dua fungsinya (`sampleFor`, `unmappedCols`) **belum pernah
> didefinisikan** ⇒ layar “Pemetaan kolom” pasti **crash** (ReferenceError) saat dibuka.
> Sesi ini menutup itu dan MENYELESAIKAN seluruh sisa kartu F3 (F3.D … F3.K).

## 0) TITIK BERHENTI SESI SEBELUMNYA (diukur, bukan dugaan)

| Kartu | Status saat sesi ini dimulai |
|---|---|
| F3.A mesin pemulihan `update_only` | SELESAI (backend) |
| F3.B rollback sesi `update_only` | SELESAI (backend) |
| F3.C endpoint `undo-report` + angka pemulihan disimpan di sesi | SELESAI (backend) |
| F3.G `test_core_f3_fulfillment.py` 52/52 | SELESAI |
| **F3.D** ringkasan hasil khusus `update_only` | **separuh** (badge & 2 peringatan ada; layar HASIL masih generik) |
| **F3.E** UI pemetaan pintar | **RUSAK** (`sampleFor`/`unmappedCols` tidak ada ⇒ crash) |
| **F3.F** Riwayat impor (kolom “Diperbarui”, tombol jujur, laporan pemulihan) | belum |
| F3.H gate · F3.I rebuild+verifikasi layar · F3.J testing agent · F3.K dokumen | belum |

Lingkungan juga harus dibangun ulang dari repo (`/app` datang sebagai template kosong):
`rsync` repo → `/app` (env platform dipertahankan) → `bash scripts/bootstrap.sh`. Pod **restart di
tengah build** (06:00) sehingga seed sempat kosong; diselesaikan dengan `bootstrap.sh --skip-deps`
(seed OK, 6 akun login 200).

## 1) YANG DIKERJAKAN & MENGAPA (semuanya soal salah-baca yang mahal)

### F3.E — layar “Pemetaan kolom” yang bisa DIPERIKSA (dan tidak crash)
* **`sampleFor(column)`** → kolom baru **“Contoh isi”** (nilai asli baris pertama yang tidak kosong,
  dibaca dari `preview[].original`, tanpa permintaan jaringan tambahan). Tanpa ini staf memilih
  field untuk nama kolom yang tidak ia kenali — misalnya `Order SN` vs `Order ID`.
* **`unmappedCols`** → kalimat “N kolom berkas tidak dipakai — itu boleh” (kolom tak dikenal
  **tidak** ditebak diam-diam).
* **`requiredHints`** → **pembalikan** usulan mesin: dari *kolom → field* menjadi
  **field WAJIB → kolom kandidat**, tampil sebagai tombol **“pakai kolom «X» (98%)”**. Tanpa
  pembalikan itu, satu-satunya petunjuk adalah badge kecil “wajib belum terpetakan”, dan staf harus
  membuka 40+ dropdown untuk mencari kolom yang cocok.
* **Backend (`core/marketing_import_engine.auto_map` + `_cand_list`)**: pilihan mesin sekarang JUGA
  dicatat sebagai **usulan #1**. Sebelumnya kolom `exact`/`synonym` punya `candidates: []`, sehingga
  begitu staf melepas kolom itu (“— tidak dipakai —”) **usulannya hilang selamanya**.
* Badge “N kolom punya usulan menunggu keputusan Anda” + skor keyakinan pada badge `mirip/perlu dipilih`.

### F3.D — layar HASIL untuk impor “hanya memperbarui”
Empat kartu yang sama dipakai untuk dua bentuk impor yang artinya berbeda. Pada Ekspor B/C
**“Baris masuk 0” adalah hasil yang BENAR**, tetapi staf membacanya sebagai gagal lalu mengunggah
ulang Ekspor A — dan justru pengulangan itu yang mengembalikan pesanan yang sudah dikirim ke
“perlu dikirim”. Sekarang: urutan kartu dibalik (**Pesanan diperbarui** jadi kartu utama), angka 0
diberi keterangannya sendiri, ada kartu **“Bisa dipulihkan”**, plus larangan eksplisit
*“Jangan unggah ulang Ekspor A untuk memperbaiki angka ini”*.
Backend: `_commit_message()` — kalimat hasil menyebut arti angkanya (bukan “0 baris masuk”),
dan respons commit menambah `update_only` + `undo_count`.

### F3.F — Riwayat impor yang jujur
* Kolom **“Diperbarui”** (`updated_count`) di samping “Masuk”, plus keterangan tabel; baris
  `update_only` diberi badge **“hanya memperbarui”** dan kolom Masuk-nya ditandai 0 by-design.
* Tombol berlabel **“Batalkan & pulihkan”** (bukan “Batalkan impor”) untuk jenis `update_only` —
  dua akibat berbeda tidak boleh memakai satu label.
* **Dialog konfirmasi memuat angka sebenarnya** (dibaca dari `undo-report` SEBELUM tombol dipakai):
  berapa pesanan yang dikembalikan, dan peringatan bahwa pesanan **batal/retur tidak dihidupkan**.
* **Dialog “Laporan pemulihan”** (menetap, bisa dibuka lagi besok dari Riwayat): 7 angka
  (diperbarui · dipulihkan · status dipulihkan · hanya field · sudah tidak ada · jejak belum/sudah
  dipakai), catatan per pesanan **dalam bahasa manusia** (bukan JSON), dan tabel jejak
  (No. Pesanan · status sebelum diimpor · sudah dipulihkan kapan). Sesudah pembatalan, laporan ini
  **dibuka otomatis** bila ada pemulihan — angka “N pesanan hanya field-nya yang dipulihkan” adalah
  pekerjaan manual yang mustahil dikerjakan dari toast 5 detik.

## 2) BUKTI (bukan klaim)

* `python3 test_core_f3_fulfillment.py` → **55 PASS · 0 GAGAL** (52 lama + 3 penjaga baru).
* **Penjaga baru dibuktikan MERAH saat fiturnya dilepas**: dengan `_cand_list` dikembalikan ke
  `candidates[:3]`, **F3-M8 & F3-M10 FAIL** (53/55) → lalu dipulihkan ⇒ 55/55.
  * `F3-M8` kolom yang dilepas TETAP menyimpan usulan mesin (sekali klik bisa dikembalikan)
  * `F3-M9` pratinjau membawa isi asli per kolom (kolom “Contoh isi” tidak kosong)
  * `F3-M10` field WAJIB yang dilepas: laporan menyebutnya **DAN** masih ada kolom yang mengusulkannya
* Gate: `run_gate "… (INV-MKTFULFILL)"` ditambahkan di `scripts/gate.sh` (+ daftar SKIP saat backend mati).
* Verifikasi layar sendiri (Playwright, bundel statis baru): kartu jenis (2 badge) → langkah 2 →
  unggah `samples/ekspor_B_status_dikirim_contoh.csv` → langkah 4 (**Contoh isi** terisi:
  `DEMO-A-1001`, `Dikirim`, `JX1234567890`) → lepas field wajib ⇒ panel merah + tombol
  **“pakai kolom «Order Status» (98%)”** + tombol “Lihat pratinjau” **terkunci** → satu klik ⇒ siap →
  commit ⇒ **Diperbarui 2 · Ditolak 1 · Baris masuk 0 (“0 memang benar”) · Bisa dipulihkan 2** →
  Riwayat (kolom Diperbarui = 2) → “Batalkan & pulihkan” ⇒ pratinjau menyebut **2 pesanan** →
  laporan pemulihan (2 dipulihkan, jejak 2 dipakai, tabel `DEMO-A-1001/1002` ← `paid`).
* Berkas contoh baru untuk staf & agen uji: `samples/ekspor_A_pesanan_contoh.csv`,
  `samples/ekspor_B_status_dikirim_contoh.csv`, `samples/ekspor_C_batal_retur_contoh.csv`.

## 3) KONTRAK SSOT

`memory/SSOT_KONTRAK_DATA_2026-08-12.md` → section baru **§PEMULIHAN IMPOR —
`marketing_data_import_undo`** (field, idempotensi, `_NEVER_RESTORE`, `_TERMINAL_KEEP`, angka
pemulihan yang disimpan di sesi, kunci periode) + field sesi yang WAJIB dibaca layar.

## 4) SISA / LANGKAH BERIKUTNYA

1. **Pemetaan Ekspor B/C masih berlabel “belum diverifikasi”** — labelnya baru bisa dilepas setelah
   owner mengirim **berkas Ekspor B & C asli** (yang ada sekarang disusun dari bentuk Ekspor A).
2. Tiga tugas user yang masih menunggu dari sesi #7: **Impor KPI Shopee (F7.2)** sudah ada
   (`shopee_*` source types + `test_core_f7_kpi_impor.py`) — sisa **Assign Toko (layar SPV)** dan
   **Scorecard Kreator (layar)** bila belum lengkap di UI.
3. ~~`mapping_unverified` berbunyi “…sebelum menyimpan” walau dibaca sesudah commit~~ — **SUDAH
   DIPOLES di sesi ini**: pada langkah 6 judulnya menjadi “Hasil di atas memakai pemetaan yang
   BELUM diverifikasi” + jalan keluarnya (batalkan & unggah ulang, jangan menambal manual).

---

# SESI 2026-08-13 (#7) — **RECOVERY INSIDEN** + lanjut 3 tugas: **Impor KPI Shopee → Assign Toko → Scorecard Kreator**

> Permintaan user terbaru: lanjutkan sesuai rekomendasi, file Shopee yang diberikan **hanya contoh** (jangan tergantung datanya), dan lanjut 3 task tertunda berurutan.

## 0) INSIDEN LINGKUNGAN (14:01) — **KORUPSI DISK MASIF** → SUDAH DIPULIHKAN ✅

**Kejadian:** container restart 14:01 menyebabkan banyak file berubah menjadi null-bytes (bukan bug kode). Dampak:
- `/etc/supervisor/*` rusak (supervisorctl gagal parse)
- Python venv `/root/.venv` rusak berat (banyak site-packages null) → backend tidak bisa start
- `frontend/src` & `scripts/` banyak file null
- `node_modules` & `yarn.lock` korup → yarn install gagal
- MongoDB gagal start karena metadata WiredTiger + `storage.bson` berisi null

**Pemulihan (diukur & dilakukan):**
- Restore 522 berkas tracked yang korup dari git (`git checkout -- <paths>`)
- Pulihkan supervisor config utama + hilangkan conf proxy yang korup
- Rebuild venv dari `backend/requirements.txt` (pip OK)
- MongoDB: perbaiki `WiredTiger` + buang `storage.bson` korup + `mongod --repair` **berhasil**, DB tidak hilang
- Frontend: bersihkan `yarn.lock` + reinstall `node_modules`, lalu `bash scripts/rebuild_frontend.sh`
- Verifikasi: `bash scripts/gate.sh` **22/22 HIJAU**

**Catatan pencegahan:** setelah fitur selesai, disarankan lakukan **push/backup ke GitHub** (cadangan di luar disk ephemeral) agar insiden sejenis tidak menghapus pekerjaan.

---

## 1) STATUS SAAT INI (setelah recovery)

- Backend: RUNNING, `GET /api/health` 200
- MongoDB: RUNNING, `test_database` ada
- Frontend: static bundle server RUNNING (port 3000), rebuild sukses
- Gate: `scripts/gate.sh` 22/22 HIJAU

**Yang sudah ada dari sesi-sesi sebelumnya (tetap berlaku):**
- F4 Katalog ✅
- F5 Siklus target·anggaran·omzet ✅
- F6 inti RBAC per toko + change-log endpoint ✅ (dibuktikan `test_core_f6_f7.py`)
- F7 inti konten+kreator (published_url guard, KPI, laporan performa) ✅ (dibuktikan `test_core_f6_f7.py`)

**Yang akan dikerjakan berikutnya (3 tugas user):**
1) **Impor KPI Shopee** (konten + iklan + statistik toko)
2) **Assign Toko (SPV)** (assign/unassign staf per toko + jejak)
3) **Scorecard Kreator** (target vs aktual, dipisah GMV KPI vs omzet pesanan)

---

## 2) UPDATE OBJECTIVES (tujuan yang disesuaikan)

1. **Impor KPI Shopee tanpa AI**: file Shopee (CSV/XLSX) yang punya metadata/section/blank rows tetap bisa diimpor lewat mesin impor SSOT (`marketing_import_schema` + `marketing_import_engine`) dengan **pranormalisasi deterministik**.
2. **Tidak ada dobel hitung omzet**: GMV dari KPI konten **tidak dijumlah** dengan omzet pesanan (`marketing_orders`). Ditampilkan berdampingan seperti pola F7 performance.
3. **RBAC operasional**: SPV bisa assign toko ke staf; staf langsung kehilangan akses (403) saat di-unassign.
4. **Scorecard kreator**: satu endpoint dan satu layar yang mempertemukan target kreator (`marketing_creator_targets`) + KPI konten (`marketing_content_calendar.kpi`) + omzet pesanan (`marketing_orders.creator_id`) **tanpa mencampur sumber angka**.

---

## 3) IMPLEMENTATION PLAN — Tahap demi tahap

### 3.1 F7.2 — Impor KPI Shopee (prioritas 1)

#### A. Desain skema & SourceType baru (SSOT)
Tambahkan jenis impor baru di `backend/core/marketing_import_schema.py`:

1) `shopee_shop_kpi` (group: Penjualan/KPI)
- **Input:** XLSX “Shopee shop stats” (contoh berisi banyak sheet)
- **Output:** koleksi baru `marketing_platform_kpi_daily`
- **Account scope:** required
- **Dedupe:** (`account_id`, `date`, `metric_scope`) atau bentuk field kanonik yang stabil

2) `shopee_content_kpi` (group: Konten)
- **Input:** CSV “Live 1d export”, “overview-v2”, “video-overview-v3” (struktur header ganda + blok section “Sumber Penonton”)
- **Output:** `marketing_platform_kpi_daily` (agar KPI harian tersimpan konsisten)
- **Catatan:** baris section & baris kosong harus dibuang; angka utama harian diambil dari baris utama (row data dengan `Periode Data` valid)

3) `shopee_ads_cpc` (group: Iklan)
- **Input:** CSV “Data Keseluruhan Iklan CPC” (ada metadata header 6 baris lalu tabel)
- **Output:** `marketing_ads_data` (koleksi yang sudah ada)
- **Kunci penting agar F5 terbaca:** field `date` harus bisa dipakai `_auto_ads` (`date` diawali `YYYY-MM`). Solusi:
  - simpan `date` sebagai string `YYYY-MM-DD` untuk **start date** periode (atau datetime) + pastikan query `_auto_ads` cocok
  - bila tetap `datetime`, pastikan `_auto_ads` tidak hanya `$regex` string (perlu patch minimal agar menerima datetime)

4) `content_performance` (group: Konten)
- **Input:** CSV/XLSX KPI per konten (contoh tidak diberikan, jadi dibuat generik)
- **Output:** update/insert ke `marketing_content_calendar` via **kunci `published_url`**
- **Aturan:** status `posted` wajib URL; impor harus menolak/menandai baris tanpa URL

> **Catatan SSOT:** bila menambah koleksi baru `marketing_platform_kpi_daily`, wajib:
> - daftar di `backend/core/collection_registry.py`
> - tulis kontrak ringkas di `memory/SSOT_KONTRAK_DATA_2026-08-12.md` (minimal: tujuan, field wajib, dedupe key)

#### B. Pranormalisasi file Shopee (tanpa AI)
**Masalah nyata:** file Shopee mengandung:
- metadata header (beberapa baris sebelum tabel)
- header ganda (baris 0 = judul grup kolom, baris 1 = header sebenarnya)
- blok section (contoh “Kunjungan - Sumber Penonton - …” yang bukan baris data)

**Solusi:** buat modul baru `backend/core/marketing_import_prenorm.py`:
- `prenorm_shopee_ads_cpc(rows)`: buang metadata sampai menemukan header tabel `Urutan,Nama Iklan,...`
- `prenorm_shopee_overview(rows)`: ambil hanya baris data utama (tanggal) dan buang section blocks
- `prenorm_shopee_shop_stats_xlsx(sheet_rows)`: untuk xlsx, ambil block tabel “Tanggal …” lalu jadikan baris harian

Tambahkan properti `prenorm` pada `SourceType` (atau mekanisme setara) sehingga `routes/marketing_data_import.upload()` memanggil prenorm berdasarkan `source_type`.

#### C. Implement commit handler spesifik (bila perlu)
- Reuse commit generic di `routes/marketing_data_import.py` selama dokumen output sudah sesuai.
- Untuk `content_performance`: commit harus **update existing** entry di `marketing_content_calendar` bila `published_url` sama (dedupe by URL), bukan insert duplikat.

#### D. Frontend: update wizard impor
File terkait: `frontend/src/components/erp/marketing/DataImportWizard.jsx`
- Tambahkan kartu jenis impor baru (4 SourceType) di daftar
- Untuk jenis yang account-scope required: pilih toko + tanggal/period (manual) bila dibutuhkan
- Tampilkan preview mapping + summary (valid/warn/error) seperti jenis lain
- Pastikan pesan error prenorm/mapping **menetap** (bukan hanya toast)

#### E. Bukti & test
Tambahkan core test baru:
- `test_core_f7_kpi_impor.py`:
  - upload contoh file Shopee (pakai contoh yang ada di artefak sebagai fixture, tapi test harus robust terhadap nilai)
  - pastikan prenorm membuang metadata/section
  - commit menghasilkan dokumen ke target collection
  - untuk ads: pastikan `_auto_ads` F5 membaca spend (atau patch `_auto_ads` agar kompatibel)
  - untuk content_performance: update entry by `published_url` dan KPI tersimpan + derived dihitung

Registrasikan ke `scripts/gate.sh` agar gate tetap 22/22 (atau bertambah 1 tapi tetap HIJAU).

---

### 3.2 Assign Toko (SPV) (prioritas 2)

#### A. Backend API
Tambah route baru (hindari konflik dengan `/accounts/{id}`):
- `POST /api/marketing/account-assign/assign`
- `POST /api/marketing/account-assign/unassign`
- `GET /api/marketing/account-assign/history?account_id=...`

Implementasi:
- Hanya role `owner/admin/superadmin/spv_marketing/manager_marketing` yang boleh menulis
- Update `marketing_platform_accounts.assigned_staff[]` (addToSet/pull)
- Tulis jejak ke `marketing_change_log` via `core/marketing_cycle.log_change`:
  - entity=`marketing_platform_accounts`, action=`assign_staff|unassign_staff`
  - before/after memuat daftar staf atau delta

#### B. Frontend UI
Tambahkan tab/section di `AccountManagementModule.jsx`:
- Panel “Assign Staff” per toko:
  - list staf marketing eligible
  - tombol assign/unassign
  - tampilkan assigned_staff saat ini
  - link “Riwayat perubahan”

#### C. Bukti
- Update/extend `test_core_f6_f7.py` atau test baru untuk:
  - assign staff ke toko → staff melihat toko
  - unassign → staff 403 pada cycle/orders
  - change-log memuat aksi assign/unassign

---

### 3.3 Scorecard Kreator (prioritas 3)

#### A. Backend endpoint
Tambah endpoint baru (di `routes/marketing_targets.py` atau file baru khusus laporan):
- `GET /api/marketing/targets/creator/scorecard?year=YYYY&month=MM&creator_id?=&account_id?=`

Perhitungan:
- Target: `marketing_creator_targets` (revenue_target/sessions_target/viewers_target)
- Aktual KPI konten: agregasi dari `marketing_content_calendar` (posted + kpi)
- Aktual omzet pesanan: agregasi dari `marketing_orders.creator_id` (dipisah dari GMV KPI)
- (Opsional) sesi kreator jika ada koleksi `marketing_creator_sessions`

Output:
- per kreator: target vs actual, % pencapaian
- tampilkan dua angka uang: `gmv_kpi` dan `order_revenue`

#### B. Frontend UI
Tempat paling aman (satu pintu, tidak bikin modul kembar):
- Tambahkan tab “Scorecard Kreator” di `ContentCalendarModule.jsx` (sejajar dengan “Performa Konten”)
- Reuse komponen table+cards pattern

#### C. Bukti
- Core test memverifikasi:
  - endpoint mengembalikan target & actual
  - `gmv_kpi` tidak dijumlah dengan `order_revenue`
  - catatan “dua sumber angka” muncul seperti F7 performance

---

## 4) CHANGELOG DOKUMEN / PLAN UPDATE

Plan lama menyatakan F6/F7 masih sebagian; **audit terbaru** setelah recovery menunjukkan:
- F6 inti sudah selesai (RBAC + change-log endpoint + test) ✅
- F7 inti sudah selesai (published_url guard + KPI + performance UI) ✅
- Sisa F7 berikutnya adalah **impor KPI konten** dan **scorecard** (yang menjadi fokus plan update ini)

---

## 5) Gate wajib hijau setiap akhir tahap
```bash
cd /app && bash scripts/gate.sh
cd /app && python3 scripts/gate_marketing_ssot.py
cd /app && python3 scripts/verify_marketing_scope.py
cd /app && python3 scripts/verify_marketing_cycle.py
# setelah menambah test baru:
cd /app && python3 test_core_f7_kpi_impor.py
```

## 6) Catatan lingkungan (tetap)
- Frontend = **static bundle**, setiap perubahan `frontend/src` wajib:
  - `bash /app/scripts/rebuild_frontend.sh`
- Kredensial marketing:
  - `marketing@dewiaditya.id` / `Dewi@123` (manager_marketing)
  - `staffmkt@dewiaditya.id` / `Dewi@123` (staff_marketing)

---

# SESI 2026-08-13 (#6) — F4 **DIVERIFIKASI** + F5 **SIKLUS TARGET·ANGGARAN·OMZET SELESAI** ✅

> (Bagian ini dipertahankan dari plan sebelumnya; tidak diubah kecuali status recovery di atas.)

## 1) VERIFIKASI TITIK BERHENTI (F4) — 6/6 bukti TERPENUHI
| Bukti F4 | Hasil |
|---|---|
| 1–4 status turunan · pagar bukti tayang · foto master · kontrak baris | `test_core_f4_katalog.py` **36/36 PASS** |
| 5 layar `marketing-catalog` ≥19 kolom + pengalih Tabel/Kartu + bertahan | **21 kolom**, toggle OK, `catalog_items_view` bertahan |
| 5b deep-link `toko-products` ⇒ diarahkan | mendarat di **Manajemen Katalog Produk**, sidebar menyorot benar |
| 6 `stock_summary.by_status` = total item | PASS |

## 2) FASE F5 SELESAI — satu layar siklus, realisasi otomatis, kunci periode, peringatan
| # | Isi | Berkas |
|---|---|---|
| F5.1 | `core/marketing_cycle.py` SSOT angka siklus + endpoint cycle | `core/marketing_cycle.py`, `routes/marketing_budget.py` |
| F5.2 | Realisasi anggaran otomatis + bukti | idem |
| F5.3 | Kunci periode + 423 + commit impor ditolak sebelum simpan | idem |
| F5.4 | Flags/peringatan dari satu fungsi | `core/marketing_cycle.py` |
| F5.5 | Layar CycleView + dialog + bukti | FE marketing |

**Bukti:** `bash scripts/gate.sh` 22/22 HIJAU; `test_core_f5_siklus.py` 58/58 PASS.

---

# plan.md — RENCANA EKSEKUSI (aktif)

> Dokumen sumber tetap sama:
> 1) `memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md`
> 2) `memory/SSOT_KONTRAK_DATA_2026-08-12.md`
> 3) `memory/VERIFIKASI_2026-08-12.md`
> 4) `memory/REGISTRY_KOLEKSI_MARKETING.md`

## Status fase (ringkas, diperbarui)
- F0 ✅
- F1 ✅
- F2 ✅
- F3 🟡 (monitoring UI selesai; sisa impor Ekspor B/C masih menunggu BD-1)
- F4 ✅
- F5 ✅
- F6 ✅ **(inti RBAC per toko + jejak sudah terbukti)**
- F7 ✅ **(inti konten+kreator sudah terbukti)**; berikutnya: **impor KPI konten + scorecard**
- F8 🟡 (laporan mingguan selesai; sisa impor/form KPI menunggu BD-3)
- F9 ⏳ (blocked BD-2)
- F10 ⏳
