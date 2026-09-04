# [2026-08-26 #40] **AUDIT PORTAL MARKETING → IMPOR PINTAR DAPAT PINTU DI LAYAR** (INV-F45) + data uji dibersihkan

Permintaan pemilik: *"untuk portal marketing, development sesi terakhir (7 hari kebelakang) sudahkah
anda cek… apakah ada bug? cek dan evaluasi terlebih dahulu"* → audit dulu (temuan dicatat, tidak
langsung diperbaiki), lalu pemilik memilih 3 pekerjaan: pulihkan wizard impor · hidupkan deteksi
otomatis · bersihkan data uji. Temuan lengkap: `memory/TEMUAN_AUDIT_MARKETING_SESI40.md`.

## A. Audit — 12 gate marketing HIJAU, tetapi DUA fitur ternyata tanpa pintu
Alur impor diuji ujung-ke-ujung dengan **7 berkas ASLI pemilik** + Ekspor B/C sintetis
(`scripts/audit_sesi40_impor_marketing.py` 30 OK · `scripts/audit_sesi40_undo_fulfillment.py` 17 OK):
pratinjau = hasil commit, penjualan harian tidak melahirkan jurnal GL, rekap harian turunan dihitung
ulang saat commit DAN rollback, status mundur/menghidupkan pesanan batal ditolak dengan alasan, dan
perbaikan UNDO `update_only` sesi #38/#39 memang bekerja (6 diperbarui → 6 jejak → 5 dipulihkan +
1 terminal dilaporkan jujur).

Yang rusak justru di LAYAR:
* **Langkah 1 "Impor Data" KOSONG** — daftar jenis disaring per kelompok (`group_key === groupKey`)
  tetapi **tidak ada satu pun tempat yang mengisi `groupKey`**; pemilih 6 kelompok (sesi #37) tidak
  pernah dirender. Layar menjawab **"0 dari 22 jenis data"**; satu-satunya jalan adalah menebak kata
  kunci pencarian.
* **Deteksi otomatis (sesi #34) tidak dipanggil frontend sama sekali** — `POST /data-import/detect`
  dan `GET /source-groups` hidup & benar di backend (6/7 berkas asli dikenali tepat), tetapi tidak
  ada satu berkas FE pun yang memanggilnya. Lint memperlihatkannya sebagai state mati
  (`setGroups`, `setGroupKey`, `setDetectRes`, `setShowDeprecated`, `hiddenInGroup`, `detectRanking`).

## B. Perbaikan
1. **`DataImportWizard.jsx`** — langkah 1 sekarang punya DUA jalan: panel **"Belum tahu ini jenis
   data apa? Unggah berkasnya dulu"** (memanggil `/detect`, menampilkan platform + bukti kolom +
   4 usulan berperingkat dengan skor & kolom wajib yang hilang + tombol **"Pakai jenis ini"** yang
   langsung mengisi jenis, kelompok, dan toko bila hanya satu yang cocok), atau **6 kartu kelompok**
   dari `/source-groups`. Ditambah tombol **"Semua kelompok"**, penghitung yang jujur
   ("22 jenis data dalam 6 kelompok"), tombol **jenis usang**, dan peringatan keras untuk berkas
   **0 baris** sebelum diunggah.
2. **`routes/marketing_settlements.py`** — helper baru `_je_still_binding()`: jurnal yang sudah
   **void** tidak lagi mengunci pencairannya. Sebelumnya pesan "void jurnalnya dulu di Portal
   Finance" mengarah ke jalan buntu (pemeriksanya hanya melihat ADA/TIDAK `je_id`), sehingga
   pencairan salah-input tidak bisa diperbaiki maupun dihapus selamanya. Saat diperbaiki sesudah
   void, tautan `je_*` DILEPAS (jejaknya disimpan di `je_voided_ref`) dan `can.edit/journal` di layar
   detail memakai aturan yang SAMA.
3. **Gate `test_core_f6_rbac_scope.py`** — `_weight()` membuang `sla_default`, `labels`, `named`.
   Ketiganya KONSTANTA/penjelasan, bukan angka milik toko; saat data memang kosong keduanya membuat
   jawaban admin & staf berbobot sama >0 sehingga sweep menuduh kebocoran atas jawaban yang
   seluruhnya 0/[] (2 tuduhan palsu: `orders/fulfillment-monitor`, `settlements/reconcile`).

## C. Data uji dibersihkan lewat PINTU RESMI (`scripts/cleanup_sesi40_artefak_uji.py --apply`)
* Pencairan uji `SET-TEST-001` (Rp 8.000.000) → jurnal **JE-20260820-0001** yang sudah **POSTED**
  (Rp 10.100.000) **di-void** (nilainya keluar dari buku besar lewat `_unmirror_lines`), lalu
  pencairannya dihapus. Layar Pencairan Marketplace kembali **Rp 0 · 0 pencairan tercatat**.
  Dokumen jurnal ber-status `voided` SENGAJA dibiarkan sebagai jejak audit pembatalan.
* Sesi impor `00c29756…` (`TikTok_UntukDikirim_2026-07-19.xlsx`) di-**rollback**: **559 pesanan**
  uji dihapus dan rekap harian turunan 10 tanggal ikut dihitung ulang ke 0.

## D. Gate baru — INV-F45 (27 invarian)
`scripts/verify_impor_pintar_pintu_layar.py`, terdaftar di `scripts/gate.sh`
("LAYAR/UANG — impor pintar punya pintu + pencairan void tidak mengunci"). Menjaga: layar memanggil
`/source-groups` & `/detect`, tidak ada state mati, **tidak ada jenis tanpa kelompok**, **tidak ada
kelompok kosong** (akar bug layar kosong), usulan deteksi membawa bukti, berkas 0 baris dilaporkan
apa adanya, dan siklus jurnal pencairan (POSTED mengunci → VOID melepas → bisa diperbaiki/dihapus).

## E. Audit penguji independen (iteration_97) — 0 critical, 3 catatan kecil
Penguji menulis `backend/tests/test_iter97_sesi40_impor_settlement.py` (**8 uji, 8 lulus**:
`/source-groups`, `/source-types`, `/detect` termasuk berkas 0-baris & penolakan `.pdf` & wajib auth,
serta siklus pencairan POST → dedupe 409 → jurnal → post → PUT/DELETE 400 → void → PUT/DELETE 200 →
GET 404) dan mengulang seluruh alur layar. **Satu catatan diperbaiki langsung:** header langkah 1
memakai `types.length` (**22**, termasuk jenis usang) sedangkan badge per kartu kelompok menghitung
yang aktif (**21**) ⇒ satu layar memuat dua angka yang tampak bertentangan. Sekarang SATU sumber:
`activeTypeCount` (**21**) dan jenis usang **disebut**, tidak disembunyikan tanpa keterangan —
"21 jenis data dalam 6 kelompok · 1 usang disembunyikan"; penghitung per kelompok juga memakai basis
yang sama ("7 dari 21"). Dua catatan lain dibiarkan sebagai backlog kecil (filter toko di layar
Pencairan masih `<select>` HTML, dan 92 sesi impor staging yang tidak dilanjutkan belum punya TTL).

## Bukti
12 gate marketing HIJAU (termasuk INV-F6RBAC 100/100 sesudah tuduhan palsu ditutup) · INV-F45 27/27 ·
audit E2E 30 OK + 17 OK · `npx eslint src/components/erp/marketing/DataImportWizard.jsx` 0 error ·
3× `rebuild_frontend.sh` sukses · `pytest tests/test_iter97_sesi40_impor_settlement.py` 8/8 · layar diverifikasi Playwright (6 kartu kelompok · deteksi berkas
asli Shopee → usulan `marketplace_orders` 93% → "Pakai jenis ini" → langkah 2) · 0 console error.

## Pelajaran
**State React yang dideklarasikan tapi tak pernah dipakai pada layar bisnis bukan sekadar lint** —
itu tanda fitur yang HILANG saat berkas dipulihkan/di-refactor. Backend hijau + gate hijau tidak
membuktikan fiturnya bisa dipakai; yang membuktikan hanya membuka layarnya.

# [2026-08-26 #38] **COGS PENGIRIMAN MEMAKAI BIAYA BATCH YANG NYATA** (INV-F44) + PEMULIHAN CONTAINER

Permintaan pemilik: *"lanjutkan development dari repo ini … sebelumnya development terhenti"*.
Repo dipulihkan dari GitHub ke container baru, lalu dikerjakan butir **#1 di `plan.md` bagian
"PR berikutnya"**: menyambungkan COGS FIFO ke jurnal.

## A. Pekerjaan utama — jurnal COGS berhenti memakai perkiraan
`routes/rahaza_posting.post_cogs_on_buyer_dispatch` dulu memakai **snapshot HPP per SPK**, padahal
sesi #34 sudah menuliskan biaya batch yang BENAR-BENAR keluar ke baris pengiriman (`fg_cogs`,
`fg_cogs_layers`, `fg_cogs_uncosted_qty`). Akibatnya satu pengiriman punya **dua angka biaya**:
gudang mencatat biaya nyata, buku besar mencatat perkiraan — dan laba per pengiriman selalu salah
tanpa satu pun galat.

* Helper baru `_fifo_cogs_for_dispatch()` menerjemahkan lapisan yang terpakai menjadi tiga komponen
  akun: **bahan** · **upah** (jahit + permak + upah internal) · **overhead**, memakai `breakdown`
  lapisan dan diskala supaya **Σ komponen = `fg_cogs`** (tidak ada rupiah yang lahir dari pembulatan).
* Urutan dasar biaya JUJUR: `fifo_batch` → `hpp_snapshot`. Dasar yang dipakai ikut ke hasil
  (`basis`) **dan ke memo jurnal**, jadi pembaca laba tahu angkanya nyata atau perkiraan.
* Lapisan tanpa rincian tidak ditebak: seluruh nilainya masuk **BAHAN** dan disebut di `gaps[]`.
* `uncosted_qty` (pcs yang keluar tanpa lapisan biaya) **tidak ditutup** — ia dikembalikan beserta
  catatan "COGS ini lebih rendah dari kenyataan sampai biaya jahit & BOM batch masuknya dilengkapi".
* Tanpa lapisan DAN tanpa snapshot ⇒ **tidak ada jurnal karangan**; penolakannya menyebut langkah
  perbaikannya.
* **Pintu di layar** (aturan repo: backend baru wajib punya pintu): Riwayat Dispatch di layar
  *Serah Terima FG → Buyer Shipment* kini punya kolom **HPP Batch (FIFO)** per baris + total per
  dispatch, dan menandai "… pcs tanpa lapisan biaya". Baris lama (dikirim sebelum lapisan biaya
  dipasang) tampil **"—"**, bukan Rp 0.
* Gate baru **INV-F44** (`scripts/verify_cogs_fifo_jurnal.py`, 10 invarian) — termasuk **J10** yang
  menempuh pintu NYATA: lapisan masuk → stok masuk → `_issue_fg_for_dispatch` → jurnal.

## B. Pemulihan container (sebelum satu baris pun diubah) — 17 gate MERAH, semuanya ditutup
Container baru + `mongorestore backups/auto_20260825_190000` ⇒ `gate.sh --full` **MERAH (17 gate)**.
Sebabnya BUKAN kode sesi #37; ini pelajaran yang layak diingat:

| Sebab | Bukti | Perbaikan |
|---|---|---|
| **Penjaga seed HR tertipu 1 karyawan** | `bootstrap.sh` melewati seluruh seed karena `employees>0`, padahal 1 karyawan itu sisa penyemai lain ⇒ 5 akun peran tanpa `employee_id` ⇒ absen/cuti/payslip **35 kegagalan** dengan pesan "Akun Anda belum ditautkan ke data karyawan" | ambang jadi **≥5** + peringatan yang berbunyi |
| **Penyemai varian membuat warna kembar** | `seed_internal_variants.py` menyaring hanya lewat KODE, jadi "Hitam" (BLK) tetap dibuat walau master sudah punya "Hitam" (HTM) ⇒ palet kembar (INV-F30/V11) + 165 varian bayangan | dedup lewat **NAMA** (`_norm_color_name`); 165 varian + 5 warna kembar (tak terpakai di stok/katalog/pesanan) dihapus |
| **Gate memaku id vendor** | `verify_produksi_maklon_invariants` memakai `mk-vendor-demo-1`, sementara `maklon_seed._upsert` **mengadopsi** master JMC yang sudah ada (`demo-vn-jmc`) ⇒ surat jalan uji lahir tanpa baris ⇒ gate **pecah (IndexError)**, bukan melapor | vendor dicari lewat **KODE** |
| **Gate menuduh tumpang tindih lintas HALAMAN** | rekap surat jalan tumbuh jadi 2 halaman ⇒ baris "Dicetak: …" di puncak halaman 2 dituduh menabrak nama perusahaan di puncak halaman 1 | tumpang tindih diukur **per halaman** |
| **Gate memakai kreator tipe `new`** | kreator `new` memang TIDAK dapat insentif (keputusan pemilik) ⇒ gate berteriak "insentif salah hitung" atas jawaban yang BENAR | gate memilih kreator yang **berhak**; kreator `new` diuji berbeda: 0 rupiah **wajib** disertai alasan |
| **Gate memakai katalog tanpa tautan FG** | `POST /marketing/orders` menolak item katalog yang belum tertaut master FG (penjaga yang benar, dipasang setelah gate ditulis) ⇒ CYC-8a 400 | gate memilih item yang **sudah tertaut** |
| Data warisan | buku kuantitas melenceng · dispatch tanpa mutasi stok FG · job tertutup tanpa `closed_at` · 22 retur pembeli belum punya pekerjaan Retur Fisik · master maklon (katalog ARN-HD) hilang · rantai onboarding varian kosong | dijalankan alat yang memang disediakan gate-nya: `recompute_qty_ledger.py`, `repair_selisih_ssot.py --apply --topup-fg`, `migrations/add_closed_at_to_production_jobs.py --execute`, `POST /api/wh/returns/sync-marketing`, `POST /api/seed/maklon-full`, onboarding varian "Jennifer Blouse" (53 SKU platform → 40 varian kanonik) |

`bash scripts/gate.sh --full` → **65 gate · VERDICT HIJAU**.

## C. Audit penguji independen (iteration_96) — 1 cacat kejujuran ditemukan & ditutup
Penguji menulis `backend/tests/test_iter96_cogs_fifo_journal.py` (13 uji) dan menemukan lubang yang
gate J6 sendiri **tidak** menutup: pada satu SJ **CAMPURAN** (1 baris berbiaya + 1 baris yang keluar
SEPENUHNYA tanpa lapisan biaya), baris yang gratis total dilewati `continue` **sebelum**
`uncosted_qty` dijumlahkan ⇒ jurnal terbit Rp 40.000 dengan `uncosted_qty=0` dan tanpa catatan —
10 pcs keluar gratis tanpa jejak. Diperbaiki (kekurangan dijumlahkan LEBIH DULU + `gaps[]` menyebut
SKU-nya) dan gate diperluas: **J6b** menguji tepat kasus campuran itu (INV-F44 kini 11 invarian).
Dua temuan layar juga ditutup: `fg_cogs == 0` dulu tampil **"Rp 0"** (angka karangan yang justru
ditolak backend) ⇒ sekarang **"belum berbiaya"**; dan kolom HPP Batch (FIFO) kini juga ada di
**dialog Detail** (jalan yang lebih sering dipakai staf), bukan hanya di baris yang di-expand.
Regresi: `cd /app/backend && python3 -m pytest tests/test_iter96_cogs_fifo_journal.py` → **13/13**.

## Pelajaran (jangan diulang)
1. **Penjaga "sudah ter-seed" berambang 1 adalah bug menunggu waktu.** Satu dokumen sisa penyemai
   lain sudah cukup untuk mematikan seluruh seed dan menjatuhkan 3 gate produk.
2. **Alat ukur bisa salah tanpa kodenya salah.** 6 dari 17 kegagalan adalah GATE yang memaku id,
   memilih data yang tidak layak uji, atau mengukur lintas halaman. Periksa klaim gate seperti
   memeriksa klaim penguji manusia — tetapi jangan pernah melunakkan invariannya untuk lewat.
3. **Penyemai yang menyaring lewat KODE, bukan lewat NAMA/identitas nyata, melahirkan master
   kembar.** Kembar itu tidak pernah berbunyi; ia hanya menggandakan varian di belakang layar.
4. **`memory/test_credentials.md` kosong** padahal seluruh gate & penguji membacanya. Sudah diisi
   (11 akun + 2 portal luar + catatan rate-limit login).

---

# [2026-08-24 #36] **IMPOR MASTER DATA** — template Excel + importir dua tahap (INV-F41)

Permintaan pemilik: *"saya ingin import data real … yang wajib adalah master data? data apa saja
yang wajib saya import dan buatkan templatenya"*. Pilihan pemilik: **template kanonik**, data demo
**dibiarkan** (pembersihan dilakukan di produksi), impor lewat **skrip**, **saldo awal belum**,
lingkup **semua master**, dan **aksesoris wajib punya master & ikut BOM**.

## Yang DIUKUR lebih dulu (bukan tebakan)
Isi basis data saat ditanya: 332 material (318 FG · 2 kain · 2 benang · **10 aksesoris**) ·
12 model · **0 BOM** · 0 lokasi kantor · 16 karyawan · 5 vendor · 12 akun toko · 78 katalog ·
CoA 353 akun + 33 posting profile (**sudah siap, tidak perlu diimpor**). Artinya penghambat
utama bukan "data belum ada" melainkan **BOM & lokasi kosong** — tanpa keduanya HPP tidak bisa
dihitung dan stok tidak bisa masuk.

## Yang DIKERJAKAN
* **`scripts/master_template_spec.py`** — SATU sumber definisi kolom (dipakai bersama pembuat
  template & importir; kalau dipisah, template dan importir pasti beda diam-diam).
* **`scripts/master_template_generate.py`** → `data_import/TEMPLATE_MASTER_DA.xlsx`:
  `00_PETUNJUK` + **16 sheet** berurut sesuai ketergantungan + `99_DAFTAR_PILIHAN`.
  01 Lokasi · 02 Karyawan(+payroll) · 03 Warna · 04 Ukuran · 05 Proses · 06 Kain/Benang ·
  **07 Aksesoris** · 08 Model · 09 Barang Jadi (SKU) · **10 BOM (kain + aksesoris)** ·
  11 Vendor CMT · 12 Klien Maklon · 13 Akun Toko · 14 Katalog Jual · 15 KOL/Kreator ·
  16 Livehost. Kolom wajib disorot; baris contoh diberi awalan `#` sehingga template boleh
  langsung diimpor tanpa memasukkan data karangan.
* **`scripts/import_master_template.py`** — importir **dua tahap**: seluruh berkas diperiksa
  dulu tanpa menulis, penyimpanan (`--apply`) hanya berjalan bila laporan bersih ⇒ **tidak ada
  impor separuh**. Idempoten (kode = kunci upsert), **tidak menghapus apa pun**, mengenali
  **referensi silang di berkas yang sama** (BOM boleh menunjuk kain yang baru diisi di sheet 06),
  setiap dokumen ditandai `import_batch`. Penolakan yang berbunyi jelas: kolom wajib kosong ·
  enum ngawur · kode ukuran berspasi/garis miring (merusak SKU) · material BOM tak dikenal ·
  barang jadi dipakai sebagai komponen BOM · qty BOM bukan angka · harga jual katalog 0 ·
  kreator tipe `new` diberi insentif · live host tanpa NIK karyawan · kode kembar.
* **`memory/PANDUAN_IMPOR_MASTER.md`** — urutan wajib + akibat nyata bila tiap master kosong.

## Dua cacat importir yang ditemukan gate SENDIRI, lalu ditutup
1. **Dry-run tidak pernah bisa bersih di basis data kosong** — BOM/katalog dicek ke basis data,
   sehingga material yang lahir di sheet 06/07 berkas yang sama dilaporkan "tidak ada". Pemakai
   akan belajar mengabaikan laporan pemeriksaan. → registri `pending` dalam-berkas.
2. **`--apply` menulis 20 dokumen sebelum melaporkan error** (impor separuh). → dipecah menjadi
   validasi penuh → baru menulis.

## Bug lama yang ikut tertangkap (bukan bagian permintaan)
`INV-F36` mendadak MERAH: **penerimaan barang balas 500** (`E11000 GR-00064`). Sebabnya bukan
kode hari ini — **pencacah nomor dokumen tertinggal** di 66 sementara dokumen nyata sudah
GR-00308, karena penyemai/impor menulis dokumen bernomor LANGSUNG tanpa menaikkan pencacah, dan
lazy-init hanya jalan sekali. `utils/counters.gen_prefixed_number()` kini **menyembuhkan diri**:
tabrakan dideteksi, pencacah didorong ke angka tertinggi yang nyata, lalu diulang. Pencacah GR
yang sudah melenceng diperbaiki. Ini berlaku untuk SELURUH nomor dokumen (PO, GR, SPK, JE, invoice).

**Gate baru INV-F41** (`scripts/verify_impor_master_template.py`, **22 invarian**, bersih-bersih
sendiri): template lengkap · baris `#` dilewati · dry-run tidak menulis · 9 bentuk baris cacat
dilaporkan per baris · tanpa impor separuh · idempoten · FG tertaut model/warna/ukuran · BOM
memuat aksesoris · karyawan dapat profil payroll · live host bermode gaji bulanan HR · kreator
tanpa password · katalog tertaut SKU+toko.

`bash scripts/gate.sh --full` → **64 gate · 0 FAIL · VERDICT HIJAU**.

---

# [2026-08-24 #35b] **AUDIT ULANG SESI #35** — 8 cacat ditemukan sendiri & ditutup

Permintaan pemilik: *"recheck kembali development hari ini, doublecheck apakah ada bug atau cacat
design, pastikan fungsionalitasnya aman, pastikan expected input output aman."* Audit kode + 3
putaran uji UI tambahan (iteration_93/94/95) menemukan **8 cacat**; semuanya ditutup:

| # | Cacat | Kenapa berbahaya | Perbaikan |
|---|---|---|---|
| 1 | `POST /content-calendar/{id}/kpi` **tanpa pagar lingkup toko** (hanya `require_auth`) | staf toko A bisa menulis KPI konten toko B ⇒ angkanya masuk rekap toko itu. Baru terpapar karena dialog "Isi KPI" adalah pemanggil pertama endpoint lama ini | `assert_account_visible()` ⇒ **403** |
| 2 | KPI **negatif / CTR > 100% / engagement > 3× views / engagement tanpa views** diterima | laporan performa & keputusan insentif memakai angka mustahil | ditolak **400** dengan pesan yang menyebut dugaan sebabnya (mis. kolom views & likes tertukar) |
| 3 | KPI **parsial menghapus angka lain** (semua field bawaan 0) | pengirim yang hanya membawa `views` diam-diam menghapus GMV/pesanan yang sudah benar — jebakan pasti meledak saat importir laporan konten dipasang | field `None` ⇒ **nilai lama dipertahankan**; layar mengirim `null` untuk kolom yang dikosongkan |
| 4 | Daftar/rekap **terpotong senyap** (500 / 5.000 baris) | total di layar tampak lengkap padahal kurang dari kenyataan | flag `truncated` + catatan "DAFTAR TERPOTONG …" |
| 5 | `POST /weekly-report/send` menerima `creator_ids` **bebas** | staf bisa mengirim rapor kreator di luar lingkup tokonya | **403**; `/weekly-report` & `/runs` juga dijaga |
| 6 | daftar id lingkup kosong (`[]`) dibaca sebagai **"tidak menyaring"** | staf tanpa toko melihat SELURUH kreator (ditangkap gate INV-F6RBAC B2-SWEEP) | `creator_ids is not None` yang menentukan |
| 7 | **layar kosong tidak jujur**: "belum ada konten" padahal sebabnya kewenangan | pemakai (dan admin) menyimpulkan datanya hilang | `scope_empty` + pesan "kosong karena KEWENANGAN"; catatan cakupan KPI disembunyikan saat itu |
| 8 | **pekan masa depan** bisa dibuka (portal kreator & layar staf) | metrik 0 pekan yang belum terjadi terbaca "performa nol" | tombol "pekan depan" **disabled** di pekan berjalan + nilai tanggal **di-clamp** ke hari ini (bukan hanya atribut `max`) |

Tambahan kualitas: **platform konten diturunkan dari tokonya** bila field `platform` kosong
(sebelumnya seluruh rekap "Per Platform" jatuh ke satu baris `(kosong)` — pertanyaan pemilik
"per toko/platform" tidak benar-benar terjawab); label kelompok kosong dinamai jelas
(`(tanpa platform)` / `(tanpa toko)` / `(tanpa jenis)`); hint "belum ada konten pada pekan ini"
di kartu kreator; `last_sent` tidak lagi mengangkut badan email panjang; muatan `body_text`
dikeluarkan dari daftar.

**Bukti**: gate **INV-F40 naik 17 → 24 invarian** (grup C: pagar masukan & lingkup pada jalur
TULIS) · `bash scripts/gate.sh --full` → **0 FAIL, VERDICT HIJAU** · testing agent
iteration_93 (5/5), iteration_94, iteration_95 (**5/5, 0 temuan**) · data uji QA dipulihkan
(9 dari 15 konten ber-KPI, log kirim rapor uji dihapus).

---

# [2026-08-24 #35] **KPI KONTEN PER KONTEN (input manual)** · **RAPOR KREATOR MINGGUAN**

## Permintaan pemilik
1. **KPI konten** harus bisa dibaca **per konten / per jenis / per toko / per KOL**; sumber angka
   views & engagement **diinput manual** staf marketing (impor menyusul bila berkasnya dikirim).
2. **Rapor kreator mingguan** (sebelumnya ditunda karena WhatsApp butuh penyedia berbayar) —
   dikerjakan lewat **email SMTP yang sudah ada** + bisa dibaca kreator di portalnya.

## Yang DIUKUR lebih dulu
| Klaim | Angka nyata sebelum perbaikan |
|---|---|
| "KPI konten belum bisa diisi" | `POST /content-calendar/{id}/kpi` ada sejak F7.3 tetapi **0 layar** memanggilnya ⇒ seluruh angka views/engagement/GMV konten hanya bisa lahir dari penyemai demo |
| "tidak bisa lihat per konten" | `/performance` hanya `group_by=creator\|content_type\|account` — **tidak ada** cara membaca KPI SATU konten (padahal konten itulah satuan yang dinilai) |
| "rapor mingguan tidak ada" | insentif dibaca per **3 bulan**, performa per **bulan** ⇒ kreator baru tahu tertinggal saat periodenya hampir habis |

## Yang DIKERJAKAN
* **`GET /api/marketing/content-calendar/performance/contents` (baru)** — satu baris = satu konten,
  lengkap `kpi` + `kpi_derived` + `kpi_filled`. Filter `kpi_state=all|filled|missing`, `creator_id`,
  `content_type`, `platform`, dan `sort=views|gmv|engagement|cvr|date`. **Baris tanpa KPI TIDAK
  disembunyikan** — itu justru daftar kerja yang harus diisi (ditandai kuning di layar).
* **`group_by=platform`** ditambahkan ke `/performance`, sehingga KPI bisa dibaca per konten ·
  per jenis · per toko · per platform · per KOL dari SATU layar (`ContentPerformanceView`).
* **`ContentKpiDialog.jsx` (baru)** — pengisian KPI **manual** dari layar Performa Konten. Angka
  turunan (engagement, eng. rate, CVR, GMV/view, AOV) **tidak bisa diketik**: ditampilkan sebagai
  hitungan hidup, yang tersimpan adalah hitungan SERVER. **Tanpa link terbit → ditolak 400**
  (klien juga menolak) karena angka yang tidak bisa dicek ulang ke platform tidak layak masuk laporan.
* **`core/creator_weekly_report.py` (baru)** — rapor **7 hari BERGULIR** (sama seperti Rekap
  Mingguan CMT; pekan ISO membuat rapor Senin pagi berumur satu hari). Per kreator: konten/tayang,
  views, engagement, pesanan & GMV (KPI platform), **omzet pesanan nyata** (`marketing_orders.creator_id`)
  **berdampingan dan tidak dijumlah**, pcs pekan ini, rincian per jenis konten, 3 konten teratas,
  dan **nominal insentif yang DIBACA dari layar insentif** (`marketing_kol_incentive._summary`) —
  tidak dihitung ulang supaya tidak ada dua angka rupiah.
* **`routes/marketing_creator_weekly_report.py` (baru)** — `GET /api/marketing/kol/weekly-report`,
  `POST /weekly-report/send` (**idempoten per (kreator, pekan)**, tombol berubah "Kirim ulang"),
  `GET /weekly-report/runs`. SMTP belum diisi ⇒ status **`skipped_no_smtp`** + alasannya disebut,
  rapor TETAP tersimpan dan tetap bisa dibaca kreator — tidak pernah gagal senyap. Kreator tanpa
  email portal dilaporkan `no_email` (bukan diam-diam dilewati).
* **Portal kreator** — `GET /api/marketing/creator-portal/my-weekly-report` + kartu **Rapor
  Mingguan** di halaman Performa dengan **pemilih pekan (‹ pekan lalu / pekan depan ›)** supaya
  kreator bisa mencocokkan rapor yang dikirim admin. Dihitung dari SATU sumber yang sama dengan
  layar staf; **tanpa HPP/margin/kredensial** (dijaga gate).
* **Catatan kejujuran data** ditambah: "Omzet pesanan Rp 0 karena belum ada pesanan ber-kreator
  pada rentang ini" — supaya kolom Rp 0 tidak dibaca sebagai "kreator tidak menjual".
* **Bug ikutan yang ditemukan & diperbaiki**: `KOLCreatorModule.jsx` memanggil `loadData()` yang
  tidak pernah ada saat panel Insentif ditutup (`loadData is not defined`); rentang bawaan layar
  Performa Konten diubah dari "awal bulan" ke **30 hari bergulir** (dibuka tanggal 1, layar tampak
  kosong padahal data pekan lalu ada).
* **Kebocoran lingkup toko (ditangkap gate INV-F6RBAC B2-SWEEP saat sesi ini)**: daftar kosong
  hasil penyaringan toko sempat dibaca sebagai "tidak menyaring" ⇒ staf tanpa lingkup toko melihat
  15 kreator sama seperti admin. Sekarang `creator_ids is not None` yang menentukan, `weekly-report`
  & `/runs` menolak kreator di luar lingkup dengan **403**.

## Gate baru
**INV-F40** (`scripts/verify_kpi_konten_rapor_mingguan.py`, **17 invarian**, membersihkan datanya
sendiri): KPI tanpa link ditolak; turunan KPI = hitungan server; semua = belum + sudah (tidak ada
baris disembunyikan); rekap kelompok & daftar per-konten sepakat pada total views; 5 pengelompokan
dilayani; pekan = 7 hari bergulir; insentif tidak dihitung ulang; GMV & omzet tetap dua kolom;
kirim idempoten; SMTP kosong tidak gagal senyap; rapor kreator bebas HPP/margin; kreator tanpa
konten tetap dilaporkan.

`bash scripts/gate.sh --full` → **63 gate · 0 FAIL · VERDICT HIJAU** ·
`testing_agent` iteration_91 **10/10 skenario UI LULUS, 0 console error**.
Data uji dibersihkan (KPI uji dikembalikan, dokumen pengiriman uji dihapus).

---

# [2026-08-23 #34] **BIAYA JAHIT MASUK HPP** · **IMPOR PINTAR** · **PORTAL KREATOR HIDUP** · **HOST DIGAJI BULANAN**

## Permintaan pemilik
1. **Produksi**: di mana input **biaya jahit**? HPP harus **BOM + jahit (+ permak)**, jadi **FIFO per
   batch**, dan HPP harus **mudah dilihat** — termasuk dari Marketing.
2. **Marketing**: (a) **di mana menu pencairan** akun marketplace? nominalnya harus terlihat di portal
   marketing; (b) periode **budget jadi 7 hari** (dulu 1 bulan) — mode bulanan **jangan dihapus**,
   cukup bisa dikonfigurasi; (c) **impor Excel terasa "bodoh"**: platform seharusnya terdeteksi dari
   akun toko, sistem harus tahu kalau user salah pilih jenis data, harus ada **viewer tabel**, dan
   **arah pemetaan dibalik** (acuan = kolom TEMPLATE sistem, lalu pilih kolom berkas), UI lebih
   kompak; angka ber-"Rp"/titik harus terbaca; (d) portal **KOL & Kreator**: tidak bisa login,
   katalog assigned, request barang, **tanpa HPP**, tambah **domisili**, **3 tipe** kreator, insentif
   **per pcs** + periode; (e) **livehost digaji bulanan** — sesi berbayar dihapus; (f) KPI konten
   harus bisa **per konten / jenis / toko / KOL**.
3. **RnD**: viewer **produk final** seperti katalog (foto + info), status **sync ke katalog
   marketing**, dan **SSOT tidak boleh broken** (link ke produksi benar).

## Yang DIUKUR lebih dulu (bukan dugaan)
| Klaim | Angka nyata sebelum perbaikan |
|---|---|
| "biaya jahit tidak ada input" | `po_items.cmt_price_snapshot` dipakai 3 pembaca (monitoring CMT, tagihan CMT, kalkulator HPP) tetapi SPK internal **selalu 0** (`production_internal_adapter.py:600`) dan **0 layar** bisa mengisinya |
| "permak tidak masuk HPP" | `dewi_cmt_permak.total_cost` ada, **0 referensi** dari `core/product_costing` |
| "menu pencairan hilang" | backend `marketing_settlements.py` **539 baris lengkap**, **0 layar** memanggilnya |
| "impor bodoh" | 7 berkas ASLI pemilik diukur: `pesanan_tiktok` 65/65 kolom, tetapi `order_pesanan_shopee` **14/50**, `retur_refund_shopee` **2/46**, `retur_refund_tiktok` **4/25**, `ads_tiktok` **3/26**; **0 mekanisme** deteksi platform/jenis |
| "tidak bisa login portal kreator" | 3 kreator demo di DB **tanpa `login_email` & tanpa hash** |
| "katalog kreator kosong" | portal membaca `marketing_creator_catalog` (**0 dokumen**); katalog nyata `marketing_catalog_items` (**81 dokumen**) |
| "livehost per sesi" | upah dihitung jam × tarif + 10% omzet − denda ⇒ gaji lahir **di luar payroll** |
| "budget 1 bulan" | format `YYYY-MM` dikunci di **20+ tempat** |
| "RnD tanpa viewer" | master barang jadi **321 SKU**, **0 layar** menampilkannya sebagai katalog |

## Yang DIKERJAKAN
* **`core/fg_cost_layers.py` (baru)** — lapisan **HPP batch FIFO** barang jadi. Lahir di SATU pintu
  (`core/production_qty_ledger.post_fg_accepted`) saat FG lolos QC masuk gudang. Isi lapisan =
  bahan (BOM) + **jahit (SPK)** + **permak** + upah internal, lengkap **rincian & `gaps[]`**
  (komponen yang belum diketahui **tidak ditebak**). Angka layar: `hpp_fifo_avg` = **rata-rata
  tertimbang lapisan yang MASIH bersisa** (keputusan pemilik) + `hpp_last_batch`; ditulis ke master
  FG & item katalog marketing dengan `hpp_source='fifo_batch'`.
* **`routes/production_sewing_cost.py` + layar `Biaya Jahit` (prod-sewing-cost)** — staf mengetik
  **tarif per SKU per pcs**, sistem yang mengalikan qty (total baris + total SPK); usulan tarif
  diambil dari **SPK sebelumnya / master partner CMT** (bukan angka karangan); tersimpan di
  `po_items` (SSOT lama) + jejak `cmt_price_set_by/at`. `product_costing.resolve_cmt_rate` kini
  memakai sumber **`spk_actual`** (rata-rata tertimbang qty) sebelum jatuh ke job CMT lama.
* **Impor pintar** — `core/marketing_import_engine`: `detect_platform` (sidik kolom per platform),
  `score_headers`, `detect_source_type`; endpoint **`POST /detect`**; `session.detection` +
  **`session.raw_preview` (10 baris mentah)** pada `/upload`. Skema diperkaya dari **berkas ASLI**
  pemilik: pesanan Shopee **39/50** kolom (dulu 14), retur Shopee/TikTok & iklan TikTok GMV Max
  dikenali; alasan/tipe/status retur diberi **kamus + fallback + `*_raw`** supaya teks bebas platform
  tidak menolak seluruh berkas. UI: **viewer tabel isi berkas**, **pemetaan dibalik** (satu baris per
  kolom template), banner **"jenis ini sepertinya bukan yang Anda pilih"** dengan bukti jumlah kolom.
* **Pencairan marketplace** — layar `marketing-settlements` (**lihat saja**, sesuai keputusan
  pemilik): 4 kartu KPI (dicairkan / bruto / potongan / belum seimbang), filter toko, unduh CSV dari
  baris yang terlihat.
* **Periode anggaran 7 hari (default)** — `YYYY-MM-DD` = periode 7 hari, `YYYY-MM` tetap sah;
  `GET/PUT /api/marketing/budget/period-settings`; `core/marketing_cycle.valid_period` menerima
  kedua bentuk (dulu 500 → layar Rp 0 senyap).
* **Portal Kreator** — kredensial kreator lama dilengkapi otomatis + endpoint
  `POST /kol/creators/{id}/portal-account`; katalog dibaca dari **SSOT `marketing_catalog_items`**
  dengan **DAFTAR PUTIH field** (tanpa HPP/margin — hanya harga jual & stok); `request barang`
  berhenti 500 (nama/SKU dibaca dengan fallback antar-skema). Kreator: **domisili**, **3 tipe**
  (`new` boleh tanpa akun portal), **insentif** (`per_pcs` / `target_bonus` / keduanya) dengan
  **tracker pcs diinput staf marketing** dan **periode default 3 bulan** (tutup periode ⇒ hitungan
  0, entri lama tetap sebagai bukti bayar).
* **Live host digaji bulanan** — `core/livehost_salary.py` (baru) membaca **`rahaza_payroll_profiles`
  (SSOT payroll HR)**; upah per-sesi dinolkan (nilai lama disimpan `legacy_pay`), log aktivitas live
  TETAP; biaya anggaran live host = gaji bulanan dibagi antar toko yang dilayani + prorata hari.
* **RnD `Produk Final` (rnd-product-viewer)** — 321 SKU final sebagai katalog: foto, HPP batch vs
  perkiraan BOM, harga jual, stok, status **sync katalog marketing**, dan **kekurangan SSOT
  per produk** (BOM belum ada / belum di katalog / biaya jahit SPK kosong / belum pernah diproduksi).
* **Mesin identitas varian** diajari pola nyata dari berkas pemilik: `(6-7th)` (usia), `1 PCS`
  (isi), `FIT TO M` (catatan muat), `DEWASA & L ANAK` (opsi DWSANK), `BUNDLING` (BDL) — 8 variasi
  yang dulu **tidak terbaca sama sekali** sekarang terbaca (INV-F30/V1c).

## Gate baru
**INV-F39** (`scripts/verify_biaya_jahit_hpp_batch_impor_pintar.py`, 23 invarian): biaya jahit
tersimpan di `po_items` & total = tarif × qty; `hpp_fifo_avg` = rata-rata tertimbang lapisan bersisa;
portal kreator **tanpa** field HPP/margin; platform & salah-pilih-jenis terdeteksi pada berkas ASLI;
tidak ada shift bersaldo upah per-sesi; `budget/summary` 200 untuk periode 7 hari **dan** bulanan;
tutup periode insentif kembali 0 tanpa menghapus bukti; viewer RnD menyebut kekurangan SSOT.

Seluruh suite: `bash scripts/gate.sh` → **62 gate · VERDICT HIJAU**.

## Bekas kaki yang dibersihkan (sampah data lama, bukan dari alur produk)
1 baris `rahaza_material_cost_history` yatim (alat ukur lama), 1 baris stok + 1 kartu stok + 1
`wh_returns` (**RET-20260819-014**) yang menunjuk material sudah terhapus tanpa SKU sehingga
identitasnya mustahil dipulihkan.


## Tambahan sesi #34 (lanjutan permintaan pemilik: "Tautkan SKU SPK")
* **Alat "Tautkan SKU SPK → master"** (`GET /api/production/sewing-cost/unlinked`,
  `POST /api/production/sewing-cost/link/{po_item_id}`) tampil **di layar Biaya Jahit itu sendiri**,
  bukan layar lain — karena di situlah orang mengetik angka yang berisiko hilang. Alat ini
  **mengusulkan** pasangan master beserta **alasannya** (kode sepadan / model sama / ukuran sama /
  nama mirip) dan menyebut **berapa rupiah ongkos jahit yang menggantung**; SKU asli disimpan
  (`sku_original`, `sku_link_by/at/note`) supaya penautan bisa diperiksa dan dibatalkan.
* **Data demo ditautkan sebagian, dengan sengaja**: 4 dari 7 baris SPK ditautkan karena buktinya
  meyakinkan (skor ≥ 0,7) — `ARN-HD-M → ARN-HD-NVY-M` (0,81) dan 3× `DA-TS01-ALLSIZE →
  DA-TS01-PTH-ALLSIZE` (1,0). **3 baris sisanya (`ARN-HD-L`, `ARN-PL-M`, `ARN-PL-L`, ongkos jahit
  Rp 3.600.000) DIBIARKAN TERLIHAT belum tertaut** karena masternya memang tidak ada; menautkannya
  ke kandidat berskor 0,4–0,56 sama dengan mengarang identitas barang, dan itu merusak HPP lebih
  parah daripada membiarkan kekurangannya terbaca. Layar menyebutnya per baris.
* Buktinya berjalan: `DA-TS01-PTH-ALLSIZE` sekarang menunjukkan **3 baris SPK · 500 pcs · BOM siap ·
  HPP/pcs Rp 15.000** (bahan 5.500 + jahit 9.000 + internal 500).
* Gate **INV-F39** bertambah menjadi **26 invarian** (A5 pelaporan SSOT per baris, A6 nominal
  menggantung + `fg_material_id` wajib terisi saat menautkan, A7 usulan wajib menyebut dasarnya).
* **Belum dikerjakan atas permintaan pemilik ("skip dulu")**: impor berkas pencairan (berkas asli
  belum dikirim) dan rapor kreator mingguan via WhatsApp (butuh penyedia berbayar + nomor tujuan).

## Tambahan sesi #34 (permintaan pemilik: "lanjutkan ke fitur dulu, soal data di akhir")
* **BIAYA IKUT KELUAR BERSAMA BARANGNYA (FIFO keluar).** `core.production_qty_ledger.issue_fg` —
  satu-satunya pintu barang jadi KELUAR (dipakai `buyer_shipment` scan-out & pemenuhan) — sekarang
  memanggil `fg_cost_layers.consume_fifo()`. Kenapa penting: tanpa ini `qty_remaining` lapisan tidak
  pernah berkurang, jadi `hpp_fifo_avg` **membeku pada batch yang barangnya sudah terjual** dan HPP
  tidak akan pernah mengikuti kenaikan harga kain. Terbukti dengan uji terkontrol (self-cleaning):
  2 batch masuk (100 pcs HPP 15.000 + 100 pcs HPP 19.000) ⇒ `hpp_fifo_avg` 17.000; keluar 100 pcs
  ⇒ **lapisan TERTUA yang dimakan** (COGS 1.500.000 @15.000) dan `hpp_fifo_avg` bergerak ke 19.000.
  COGS + lapisan terpakai + `uncosted_qty` disimpan di baris pengiriman (`fg_cogs`,
  `fg_cogs_layers`, `fg_cogs_uncosted_qty`). **Barang tetap boleh keluar** walau biayanya gagal
  dihitung (stok fisik adalah kebenaran gudang), tetapi `uncosted_qty > 0` **dilaporkan** — itu tanda
  batch masuknya belum punya HPP, bukan tanda semuanya beres.
* **PAPAN MARGIN di layar Produk Final RnD** — urut **margin paling tipis dulu**, kartu KPI margin
  rata-rata + jumlah produk **margin tipis/minus**, dan margin per kartu (merah minus, kuning <15%,
  hijau sehat). Produk yang HPP **atau** harga jualnya belum ada **TIDAK dihitung bermargin 0** —
  jumlahnya disebut terpisah ("54 produk belum bisa dihitung"), supaya papan ini tidak menyamarkan
  data yang belum ada. Keadaan hari ini: margin rata-rata **57%** dari 6 produk yang lengkap.
* Gate **INV-F39** kini **27 invarian** (tambahan **B3**: tiap dokumen konsumsi lapisan wajib
  memakan lapisan tertua lebih dulu dan qty-nya utuh — Σ lapisan + `uncosted_qty` == qty keluar).

---

# [2026-08-23 #32] **NILAI POTONGAN LAHIR SAAT DIPOTONG** · **POTONGAN YATIM PUNYA PENJAGA & PEMBERSIH**

> Catatan serah-terima: entri ini ditulis pada sesi #33. Sesi #32 **terputus tepat saat menulis
> dokumentasi** — `plan.md` sesi #32 sempat tersimpan (kini diarsipkan ke
> `memory/PLAN_ARSIP_2026-08-23_SESI32_NILAI_POTONGAN.md`), tetapi CHANGELOG, INVARIANTS, dan
> HANDOFF belum. KODE, gate **INV-F37**, dan **backup DB `backups/auto_20260823_190000`** sesi #32
> sudah lengkap dan terbukti hijau di container baru sesi #33 (`gate.sh` → 55 gate HIJAU sebelum
> satu baris pun diubah).

## Permintaan pemilik
1. Tutup DoD sesi #31: jalankan penguji independen untuk layar **HPP per Potong** & kartu **BOM di
   dialog Cutting**, perbaiki semua temuan, lalu dokumentasi + backup DB baru.
2. Perbaiki dua cacat "material potongan" yang pemilik temukan sendiri lewat mongosh:
   **(a)** potongan menjadi **yatim** (order cutting / kain sumber hilang) ⇒ perlu penjaga +
   pembersih; **(b)** **harga/HPP potongan = 0**.
3. Fitur backlog lain (Daftar Belanja Mingguan · Riwayat Harga Barang · Isi Ambang Massal) ditunda.

## Yang diukur lebih dahulu (data hidup)
- `complete` order cutting menghitung nilai potongan dari harga kain yang **di-snapshot saat order
  dibuat**. Pada satu order uji: nilai yang dicatat **Rp600.000** padahal nilai kain yang benar-benar
  keluar **Rp641.379,31** ⇒ **Rp41.379 hilang tanpa jejak pada satu order saja**.
- Master potongan (`rahaza_materials type='panel'`, dibuat otomatis oleh `start`) tidak menyimpan
  **siapa induknya** ⇒ tidak ada cara memeriksa keyatiman.
- Sumber sampah yang sebenarnya bukan alur produk, tetapi **ALAT UKUR**:
  `scripts/verify_fase_h6b_cutting_issue.py` (gate INV-F24) menghapus master potongan memakai
  **REGEX KODE** `^(VFH6B-|CUT-GATE-F24)`, sementara sejak sesi #30 kode potongan diturunkan dari
  NAMA MODEL (`CUT-JEPIT-JEDAI-…`) ⇒ regex tak pernah cocok ⇒ **satu master sampah menumpuk setiap
  kali gate dijalankan**. Itulah "potongan yatim" yang pemilik lihat.
- `scripts/verify_uom_roll_dan_style_master.py` membersihkan progres cutting dengan nama field yang
  salah (`order_id`, seharusnya `cutting_order_id`).

## Yang dikerjakan
**SSOT baru `core/cut_panel_value.py`** — satu pintu `apply_progress_value()` dipanggil setiap
laporan progres cutting: `nilai kain keluar = qty × unit_cost kain SAAT ITU`,
`HPP masuk/pcs = nilai / pcs jadi`, lalu **rata-rata bergerak** ke master potongan lewat SSOT
`core/accessory_valuation` (+ riwayat harga). `panel_onhand()` dibaca **SEBELUM** `stock_service.add`
(kalau sesudah, qty yang baru masuk ikut menjadi penyebut). Kain belum bernilai ⇒
`value_status='unvalued'` + `notify_unvalued` ke Admin Gudang — bukan diam-diam Rp0.
`order_value_totals()` = Σ nilai progres, dipakai `complete`.

**SSOT baru `core/cut_panel_health.py`** — definisi "potongan yatim" (`order_missing`,
`source_missing`, `source_inactive`, `source_unknown`), bukti kelayakan hapus (stok, buku besar stok,
kartu stok, rujukan BOM/MI/PR/PO/GR), `scan()`, `cleanup()` (idempoten), dan penjaga alur
`remove_if_unused()`.

**`routes/cutting.py`** — master potongan menyimpan `cutting_order_id` / `cutting_order_number` /
`created_from` (bukti kepemilikan) + `value_status`; `add_progress` memindahkan nilai & menyimpan
jejaknya (`fabric_unit_cost`, `value_out`, `panel_unit_cost_before/after`); `complete` memakai Σ nilai
progres dan **tidak** menimpa master (kecuali order lama yang masternya masih 0 — diisi sekali,
sumber `cutting_complete_backfill`); `cancel` & `delete` memanggil penjaga; `GET /output-materials`
mengirim nilai + asal + status + penanda yatim; endpoint baru **`GET /api/cutting/panels/health`** &
**`POST /api/cutting/panels/cleanup`**.

**Frontend** — layar **Master Potongan** (`cutting-panels`) dirombak: 4 kartu ringkasan (termasuk
**Nilai Persediaan** & **Belum Bernilai**), tabel 10 kolom (Order Cutting · Nilai · Status Nilai +
penanda **yatim** per baris), kartu **"Potongan yatim"** berisi alasan per baris, kolom "Bisa
dibersihkan?", dan tombol **Bersihkan yang aman (n)** dengan konfirmasi dua langkah. **Order
Cutting** — Riwayat Progres dapat kolom **"Nilai kain keluar"** & **"HPP potongan"** (menyebut "dari
Rp… rata-rata bergerak"), toast nilai berpindah, serta peringatan bertahan-lama bila kain belum
bernilai.

**Temuan penguji independen sesi #31 yang diperbaiki** — (1) alamat URL tidak mengikuti layar
(`syncModuleHash` di `App.js`: navigasi, sidebar, pindah portal, kembali ke pemilih portal, logout);
(2) sel margin hanya "—" ⇒ sekarang berbunyi **"harga jual belum ada"**; (3) teks peringatan deviasi
BOM menyambung (`"25 kg— pastikan"`); (4) daftar ukuran di kartu BOM kini menandai `ALLSIZE · ada BOM`.

**Alat ukur yang MEMBOCORKAN data — diperbaiki** — INV-F24 menghapus master potongan lewat **`id`**
(bukan regex kode); `verify_uom_roll_dan_style_master.py` memakai nama field yang benar.

## Bukti
- POC `test_core_potongan_nilai_dan_yatim.py` **13/13 PASS**, self-cleaning (total stok kembali).
- Gate baru **INV-F37** `scripts/verify_potongan_nilai_dan_yatim.py` — **12 invarian**, C12 memeriksa
  **KEADAAN AKHIR: 0 potongan yatim** sesudah bersih-bersih, jadi kebocoran alat ukur mana pun
  otomatis MERAH.
- `bash scripts/gate.sh` → **VERDICT HIJAU 55 gate**.
- Alur dibuktikan di browser: progres 10 m ⇒ 20 pcs → *"Nilai kain keluar Rp 250.000 · Rp 25.000/m |
  HPP potongan Rp 12.500/pcs"*; progres 5 m ⇒ 5 pcs → *"Rp 125.000 | Rp 15.000/pcs dari Rp 12.500
  (rata-rata bergerak)"*; Master Potongan → *"25 pcs · Rp 15.000 · Rp 375.000 · bernilai"*; `cancel`
  → *"Master potongan CUT-JEPIT-JEDAI-NAVY-XL ikut dibersihkan karena belum pernah dipakai"*.
- **Backup DB** `backups/auto_20260823_190000` (2,4 MB · 230 koleksi · 6.414 dokumen).

## Pelajaran
1. **Alat ukur adalah SUMBER SAMPAH yang nyata.** Penjaga yang mencocokkan **REGEX KODE** akan
   berhenti bekerja tanpa suara begitu pola kode berubah. Hapus lewat **`id`**, dan tambahkan
   invarian **KEADAAN AKHIR** (0 yatim) supaya kebocoran alat ukur sendiri ikut MERAH.
2. **Nilai harus berpindah pada saat barangnya bergerak**, bukan pada saat dokumen ditutup. Harga
   yang di-snapshot saat order dibuat sudah basi ketika kain benar-benar dipotong.
3. **Baca stok SEBELUM menambah stok** kalau ingin rata-rata bergerak yang benar — kalau dibaca
   sesudah `add`, qty yang baru masuk ikut menjadi penyebut.

---
---


# [2026-08-23 #31] **HPP PER POTONG & PER MODEL** (lahir dari pembelian + BOM + upah) · **BOM DI DIALOG CUTTING**

## Permintaan pemilik
Melanjutkan usulan akhir sesi #30 yang dipilih pemilik: **(A) HPP per potong & per model** lebih
dulu, lalu **(B) BOM di dialog Cutting**. Komponen biaya yang diminta: **kain + aksesoris + upah
CMT** dan **+ upah cutting/internal**. Overhead tidak diwajibkan.

## Yang diukur lebih dahulu (data hidup)
- `rahaza_materials` type='fg' = **321 dokumen, SEMUANYA `hpp: 0` & `hpp_source: 'none'`** ⇒ HPP
  produk jadi belum pernah lahir, walau harga BAHAN sudah lahir dari pembelian sejak sesi #30.
- Satu-satunya sumber HPP model: `core/product_master.resolve_hpp` = `hpp_rnd` (kalkulator R&D) →
  `base_hpp` (**KETIKAN MANUAL**) → 0. Ini justru pola yang pemilik tolak di sesi #30.
- Karena itu kolom **HPP & margin** di Katalog Marketing (`CatalogItemsView`) selalu 0 / "belum ada"
  ⇒ margin tidak bisa diketahui sebelum harga jual ditetapkan.
- `rahaza_boms` hanya **2 dokumen** (2 model punya BOM 1 ukuran); 11 dari 13 model belum ada BOM.
- Order Cutting: `planned_input_qty` (rencana pemakaian kain) **diketik manual** walau BOM per
  model+size sudah menyimpan kebutuhan per pcs.
- Upah yang tersedia nyata: `rahaza_wip_events` (CUTTING @Rp500/pcs, ter-anchor model),
  `rahaza_processes` (6 proses), `dewi_cmt_partners.rate_per_pcs` (7.500–9.000),
  `dewi_cmt_jobs.sewing_rate_per_pcs`.

## Yang dikerjakan
**SSOT baru `core/product_costing.py`** — HPP/pcs per (model, ukuran):
`bahan (BOM × unit_cost hasil pembelian, SADAR SATUAN via core/bom_uom) + upah CMT + upah
cutting/internal [+ overhead OPSIONAL, default MATI]`. Setiap komponen SELALU melaporkan `source`
+ `note`; yang belum ada masuk `gaps[]` dengan `action` + layar tujuan perbaikan. Rantai upah:
`owner` (dikunci pemilik, tersimpan di `rahaza_model_costing` + siapa/kapan) → `wip_actual`
(rata-rata tertimbang laporan produksi, proses jahit/CMT DIKECUALIKAN supaya tidak dobel) →
`settings_process_rates` → `settings_fallback` → kekurangan. Kandidat tarif NYATA (partner CMT /
job CMT / profil payroll borongan) selalu dikirim supaya pemilik memilih, bukan menebak.

**API baru `/api/costing`** (`routes/product_costing.py`): `GET /models` (daftar + kekurangan),
`GET /models/{id}` (rincian per ukuran + baris BOM + margin), `POST /models/{id}/apply`,
`POST /apply-all`, `PUT /models/{id}/labor` (kunci upah), `GET/PUT /settings`, `GET /processes`,
`GET /snapshots`.

**Penerapan (apply)** menulis: `rahaza_models.hpp_bom` (+ `hpp_bom_by_size`), FG **per ukuran**
(`rahaza_materials.hpp`, `hpp_source='bom'`, `hpp_breakdown`), dan item katalog Marketing ⇒ **kolom
margin Marketing HIDUP**. Idempoten + snapshot audit `product_cost_snapshots`.
`resolve_hpp` kini **bom → rnd → manual → none** (model tanpa `hpp_bom` angkanya tidak berubah);
`_resolve_rnd_hpp` katalog mendahulukan FG ber-`hpp_source='bom'` supaya HPP **per ukuran** tidak
diratakan oleh angka model.

**BOM di dialog Cutting**: `GET /api/cutting/bom-requirement` (kebutuhan/pcs & total dalam satuan
kain + daftar aksesoris + kejujuran: `bom_missing`, `input_not_in_bom`, `fabric_uom_unclear`,
`bom_without_fabric`). Layar Order Cutting dapat kartu **"Kebutuhan menurut BOM"**, tombol
**"Pakai angka BOM"**, daftar aksesoris, dan peringatan bila rencana manual berbeda >10% dari BOM.

**Layar baru "HPP per Potong"** (`fin-hpp-produk`, di Portal Produksi & Keuangan): 4 kartu ringkasan,
target margin, saklar overhead, tabel per produk (bahan/CMT/internal/HPP/harga/margin/usulan harga +
badge sumber tiap angka), dialog rincian per ukuran (baris BOM lengkap: qty BOM → satuan dasar →
harga → biaya, plus status `unvalued`/`unlinked`/`uom_unclear`), pengunci upah dengan chip kandidat,
daftar kekurangan yang bisa diklik ke layar perbaikannya, tombol **Salin BOM ke ukuran lain**, dan
riwayat penerapan. Master Produk mendapat tautan pintas ke layar ini; label sumber HPP baru
(**BOM + pembelian**) ditambahkan di Master Produk & Katalog Marketing.

## Bukti
- POC `test_core_hpp_potong_dan_bom_cutting.py` **15/15 PASS** (self-cleaning): kain dibeli 100 m
  @25.000 & kancing 120 pcs @500 lewat PO→GR; BOM 150 **cm** + 0,5 **lusin** + 1 pcs label (belum
  pernah dibeli) ⇒ bahan **Rp40.500/pcs** (bukti cm→m & lusin→pcs), label jadi kekurangan
  `material_unvalued`; upah proses 700+300 = **1.000** (SEWING 9.999 diabaikan); upah dikunci
  8.500 + 1.500 ⇒ **HPP Rp50.500/pcs**; overhead hidup ⇒ **Rp51.500**; target 40% ⇒ usulan
  **Rp84.167**; harga katalog 100.000 ⇒ margin **Rp49.500 (49,5%)**; apply ⇒ FG & item katalog
  50.500 (`hpp_source='bom'`), 2× apply tetap sama + 2 snapshot; label akhirnya dibeli @250 ⇒
  bahan **40.750**, HPP **50.750**, status **ready** (kekurangan tertutup sendiri); BOM cutting
  1,5 m/pcs × 100 = **150 m** + 2 aksesoris; kain di luar BOM & ukuran tanpa BOM diperingatkan.
- Gate baru **INV-F36** (`scripts/verify_hpp_potong_dan_bom_cutting.py`, 12 invarian, self-cleaning)
  **12/12 PASS**, terdaftar di `scripts/gate.sh`.
- **Temuan dari layar yang langsung diperbaiki**: produk berharga jual tapi HPP belum bisa dihitung
  menampilkan **margin 100%** (biaya 0 dianggap benar). Sekarang margin hanya muncul bila harga DAN
  HPP dua-duanya diketahui (`margin_known`), lain-lain berbunyi "HPP belum ada".
- Data hidup: total stok tetap **33.503** sebelum & sesudah seluruh pengujian.

# [2026-08-21 #30] **SATUAN GULUNGAN JUJUR · STYLE POTONGAN DARI MASTER · HARGA DARI PEMBELIAN**

## Keluhan pemilik (verbatim)
1. *"saya masih melihat ada ketidaksesuaian UOM di roll, ketika purchasing itu yard namun di
   tracking roll menjadi meter jadinya yang diterima tidak sesuai dengan apa yang di PO … di roll
   itu jangan di paksakan meter agar uomnya jadi tidak kacau"*
2. *"ketika cutting harusnya ini nama produk atau style mengambil dari master data, fungsinya buat
   apa jadi ketika pembuatan bom dan ketika produksi sudah jelas ini produk ada"*
3. *"harga satuan diambil jangan dari master data, ambil dari pengadaan atau pembelian otomatis
   generate harga rata rata"* — untuk semua jenis kain maupun aksesoris.

## Yang diukur lebih dahulu
- **Tidak ada konversi yang benar-benar terjadi.** PO 650 yard → diterima 520 → reject 130 ⇒ **390
  yard dibagi 4 gulungan @97,5 yard**. Yang salah adalah SATUAN YANG DITULIS SISTEM:
  `ROLL_UOM` memaksa `rol`/`gulung` → `meter`; layar Roll Kain menulis kolom mati
  **"Sisa / Total (m)"** dan membaca nama field warisan `length_m`/`remaining_m` sebagai meter.
- Dialog **Issue** memberi pilihan satuan meter/kg: gulungan yard yang dikeluarkan sebagai "meter"
  tetap mengurangi angka yard (label bohong), dan bila dipilih "kg" sistem menjawab **"sisa 0"**
  padahal gulungannya penuh.
- `POST /api/cutting/orders` menerima `style_name` **ketikan bebas** dan tidak menyimpan `model_id`
  apa pun ⇒ order potongan tidak pernah menunjuk model di master (`rahaza_models`), padahal **BOM
  disimpan per model+size**. Satu style bisa punya banyak ejaan.
- Mesin HPP rata-rata bergerak (`core/accessory_valuation`) HANYA dipanggil dari penerimaan
  aksesoris. **Penerimaan Barang (GR) dari PO tidak pernah menyentuh harga** ⇒ harga hanya bisa
  diketik di Master Item, dan nilai persediaan memakai angka ketikan (atau 0).

## Yang dikerjakan
**Satuan gulungan (pilihan pemilik: apa adanya + info konversi kecil)**
- `core/fabric_roll_engine`: `ROLL_UOM` tidak lagi memaksa meter (`rol`→`rol`, `gulung`→`gulung`,
  `yard`→`yard`); `WEIGHT_UOMS` menentukan ember penyimpanan (dokumen lama tetap di ember yang sama,
  **tidak ada angka yang berpindah**); `TO_METER` + `with_display_uom()` menambahkan
  `uom`/`qty_total`/`qty_remaining` + info `qty_*_m` ("97,50 yard ≈ 89,15 m").
- `routes/wms_fabric_rolls`: daftar, detail, dan per-material mengirim satuan apa adanya;
  **pengeluaran gulungan wajib memakai satuan gulungan itu** (satuan lain → 400 dengan pesan jelas).
- Layar Roll Kain: kolom **"Sisa / Total" + kolom "Satuan"**, info "≈ … m", CSV mengikuti,
  dialog Issue satuannya **read-only** (mengikuti gulungan). Bonus: dialog Detail Roll yang selama
  ini **kosong** (state salah bentuk di `handleView`) ikut diperbaiki.

**Style potongan dari master (wajib + tombol "Model Baru")**
- `routes/cutting`: `model_id` WAJIB (validasi ke `rahaza_models`), `variant_id` opsional
  (divalidasi milik model itu). `style_name`/`style_sku`/`output_color`/`output_size` **diturunkan
  dari master**, dan order menyimpan `model_id`/`model_code`/`variant_id`/`size_id`/`color_id`
  sehingga menyambung ke BOM (per model+size) dan produksi. `PUT` menolak pengetikan nama style.
- Layar Cutting: dropdown **Model/Style** + **Varian (warna·size)** + tombol **"+ Model Baru"**
  (membuat model master langsung dari dialog, lalu terpilih otomatis) + pratinjau identitas potongan.

**Harga satuan lahir dari pembelian (rata-rata bergerak)**
- `routes/warehouse` (GR, juga dipakai bridge `/api/wms/legacy/receiving`): setiap penerimaan
  bernilai memanggil `accessory_valuation.apply_receipt_cost` dengan **harga dari PO**
  (`qty_before` dibaca SEBELUM stok ditambah) ⇒ berlaku untuk **semua jenis barang**, bukan hanya
  aksesoris. Kegagalan hitung harga tidak menggagalkan penerimaan (dicatat di log).
- Master Item **tidak bisa lagi mengetik harga**: `PUT` mengabaikan `unit_cost` dan SELALU membalas
  `harga_satuan_catatan` (arahkan ke Valuasi HPP untuk koreksi bernilai audit). `POST` masih
  menerima **harga awal** untuk barang lama tanpa pembelian, ditandai `cost_method="opening"`.
- Layar Master Item: saat mengedit, harga tampil sebagai **angka turunan** (nilai · sumber · harga
  beli terakhir · penjelasan); input harga hanya ada saat **membuat** barang baru.

## Bukti
- Gate baru **INV-F35** (`scripts/verify_uom_roll_dan_style_master.py`, 10 invarian) menjalankan
  alur nyata: material yard → PO 650 yard @42.000 → 520 diterima/130 reject → **4 gulungan @97,5
  yard (≈89,15 m)**; issue "meter" ditolak 400, "yard" berhasil; HPP jadi **42.000/yard
  (moving_average)**; kiriman harga 999 dari master diabaikan; cutting tanpa model 400. Seluruh
  artefak dipulihkan sendiri.
- `bash scripts/gate.sh` → **53 gate VERDICT HIJAU** (dua gate cutting lama ikut disesuaikan agar
  memakai `model_id` dari master).
- Penguji independen: iteration_86 (menemukan 1 bug HIGH: dialog Detail Roll kosong → diperbaiki)
  dan **iteration_87 HIJAU 100%** — rata-rata bergerak dibuktikan berjenjang: PO1 100@10.000 →
  HPP 10.000; PO2 100@20.000 → **HPP 15.000** (rata-rata, bukan harga terakhir); regresi Roll Kain,
  Cutting, Ambang Stok, dan Surat Jalan CMT tetap utuh. Uji regresi tersimpan di
  `backend/tests/test_iter87_moving_average_hpp.py`.


# [2026-08-21 #29c] **SURAT JALAN CMT → DA & ALERT STOK YANG BENAR-BENAR BERBUNYI** (W5 + W3)

## Keluhan / permintaan pemilik
1. *"buatkan surat jalan CMT yang kirim ke DA, export nya adakan saja di terima FG dari cmt"* (W5).
2. **Alert & Reorder tidak pernah berbunyi** — minta alert stok minimum dihidupkan (W3).

## Yang diukur lebih dahulu (data hidup)
- Katalog PDF punya **3 jenis surat jalan** (gudang · material ke vendor · dispatch buyer) tetapi
  **tidak ada untuk arah CMT → DA** — padahal itu arah barang MASUK gudang DA. Layar
  "Terima FG dari CMT" **tidak punya satu pun tombol cetak** ⇒ pengantar barang vendor tidak punya
  dokumen untuk ditandatangani.
- `cmt_receipt_lines` **tidak menyimpan `serial_number`** ⇒ surat jalan wajib me-resolve serial dari
  `po_items` / `buyer_shipment_items`, kalau tidak kolom Serial akan selalu kosong.
- `GET /api/rahaza/stock-thresholds/summary` → **333 material, 0 punya ambang** (`min_stock_qty` &
  `reorder_point` kosong SEMUA) ⇒ alarmnya tidak rusak, **ambangnya belum pernah diisi**, dan
  satu-satunya jalan mengisinya adalah modal Master Item **satu material per kali (333 kali)**.
- Ada **TIGA definisi "stok rendah"** yang hidup terpisah: layar alert (hanya `reorder_point`),
  notifikasi/bel (hanya `min_stock` legacy, `SUM($qty)`), dashboard (`min_stock_qty`→%→`min_stock`,
  `SUM($qty)`). Dua di antaranya memakai `SUM($qty)` sehingga **baris stok skema lama**
  (`total_qty`/`available_quantity`) tidak terbaca ⇒ pemilik mengisi ambang di satu tempat, layar
  lain tetap berkata "aman".

## Yang dikerjakan
**W5 — Surat Jalan CMT → DA**
- Jenis dokumen baru `cmt-delivery-note` di SSOT `data/pdf_doc_registry`: 10 kolom (No & Qty Kirim
  **wajib**; Serial · SKU · Produk · Size · Warna · Qty Terima · Qty Reject · Keterangan pilihan),
  halaman landscape, blok TTD bawaan **Pengirim (vendor CMT) · Pemeriksa QC · Penerima (Gudang DA)**.
- **Keputusan pemilik:** satu dokumen, dua versi cetak — kolom hasil QC adalah PILIHAN, bukan jenis
  dokumen kedua; default yang tercentang hanya **versi kirim murni**; boleh dicetak **kapan saja**
  (QC belum selesai → kolom QC kosong + catatan bahwa angkanya masih bisa berubah).
- Seri nomor baru `cmt_delivery_notes.dn_number` (`SJ-CMT/{YYYY}/{MM}/{SEQ:4}`) terdaftar di
  **Penomoran Dokumen** (status "selalu otomatis" beralasan: nomornya lahir saat dicetak).
- SSOT `core/cmt_delivery_note.py`: `ensure_number()` **idempoten per penerimaan** (cetak ulang
  memakai nomor yang SAMA, hanya jejak cetak bertambah) + `build_lines()` yang me-resolve serial
  dari master. Nomor lewat generator race-safe `utils.counters.gen_prefixed_number`, dan
  `dn_number` masuk daftar **index unik**.
- Cabang `?type=cmt-delivery-note&id=<receipt_id>` di `routes/operations_pdf.py` memakai
  konfigurasi kop/TTD yang SUDAH ada (`get_doc_settings` + `_pdf_header_branded` +
  `_pdf_signature_block`) dan tabel lewat `tpl_table_parts` (INV-F17/INV-F26 tetap terjaga).
- Layar: tombol **Surat Jalan** di setiap baris `DAReceiveFromCMTModule.jsx` → `PdfColumnPicker`
  dengan prop baru **`defaultKeys`** (kolom tercentang bawaan per dokumen).

**W3 — Alert stok hidup**
- SSOT **`core/stock_thresholds.py`** = SATU definisi "rendah": ambang dibaca berurutan
  `min_stock_qty` → `min_stock` (legacy) → `min_stock_percentage`; `reorder_point` = titik pesan
  ulang (peringatan); stok SELALU lewat `stock_service.onhand_map`; usulan dari pemakaian NYATA
  (`rahaza_stock_ledger` 30 hari) dan **tanpa pemakaian ⇒ usulan 0 + `no_usage_data`** (tidak menebak).
- Pembaca yang DISATUKAN ke SSOT itu: `GET /api/warehouse/alerts` (layar Alert & Reorder),
  `rahaza_alerts.check_low_stock` (notifikasi/bel), `GET /api/rahaza/materials?low_stock=true` &
  `/materials/reorder-alerts` (dashboard), dan `/warehouse/smart-reorder` (rumus usulan).
- Endpoint baru `GET/POST /api/rahaza/stock-thresholds*` (daftar + ringkasan + simpan massal,
  nilai negatif ditolak 400).
- Layar baru **Ambang Stok** = tab ke-3 di **Master Item** (`StockThresholdsModule.jsx`): 4 kartu
  ringkasan, filter (jenis · status · pencarian), input min stok & titik pesan ulang per baris,
  "Pakai usulan" per baris + "Pakai semua usulan", simpan massal.
- **Kejujuran layar**: Alert & Reorder kini menyebut *"333 dari 333 material belum punya ambang —
  selama ambangnya kosong, alert TIDAK akan pernah berbunyi"* + tautan langsung ke tab pengisian
  (deep-link `#wh-master=thresholds` lewat kontrak `hub_tab_<id>` yang sudah ada). Sebelumnya layar
  ini berkata **"Semua sistem normal"** padahal tidak ada apa pun yang dipantau.
- Master Item per-item juga dapat kolom **Titik Pesan Ulang** (`reorder_point`) yang tadinya hanya
  bisa diubah lewat API.

## Bukti
- Gate baru **INV-F33** (`scripts/verify_surat_jalan_cmt.py`, 10 invarian) & **INV-F34**
  (`scripts/verify_alert_stok_hidup.py`, 9 invarian) — keduanya memulihkan data hidup sendiri
  (nomor SJ uji dikembalikan, ambang material uji dipulihkan persis).
- `bash scripts/gate.sh` **52/52 PASS · VERDICT HIJAU** (89s).
- Penguji layar independen: **13/13 API pass**, alur UI penuh lolos — dialog kolom terbuka dengan
  **7 dari 10** kolom tercentang (QC tidak tercentang), nomor SJ idempoten, 400/404/401 benar;
  ambang 6000 pada ACC-BTN-12 (stok 5000) → alert muncul *"kurang 1000"*, lalu dipulihkan ke 0.
- Bukti dua arah W3: ambang dilanggar ⇒ alert muncul di layar + notifikasi + dashboard; ambang
  dikosongkan ⇒ alert hilang. Baris stok skema lama (`total_qty`) ikut terhitung (5.000 → 1.004.999).


# [2026-08-20 #29b] **TABEL STOK JADI TERBACA & KOLOM CETAK BISA DIPILIH** (W1 + W2)

## Keluhan pemilik
1. *"material id seharusnya tidak perlu ada di table ini"* + tabel FG "tidak sinkron" dengan Master
   Item Produk Jadi; minta kolom **kategori, warna, opsi** plus **filter**.
2. *"PDF masih belum lengkap … untuk produksi ada data no serial namun di pdf tidak ada pilihannya,
   jadi saya ingin semua data collection bisa di export juga dan bisa di pilih user"* (fokus
   **Maklon & Produksi**).

## Yang diukur lebih dahulu
- Layar **Stok & Akurasi** tab pertama (Viewer Stok Unified) menampilkan **UUID `material_id`
  sebagai kolom PERTAMA** dan mengekspornya ke CSV; tidak ada kolom kategori/warna/opsi padahal
  ketiganya sudah ada di master barang (hasil SSOT varian sesi #28).
- Layar itu menampilkan **BARIS STOK**, bukan master: **26 baris stok untuk 321 barang jadi** ⇒
  inilah sebab sesungguhnya keluhan "tidak sinkron" (bukan duplikasi data).
- Kolom **Serial No** SUDAH terdaftar di katalog kolom PDF (`data/pdf_doc_registry`), tetapi satu-
  satunya cara memilih kolom adalah lewat layar SETELAN ⇒ pemakai yang sedang mencetak tidak punya
  pintu. Lebih buruk: laporan produksi memfilter kolom **DUA KALI** (`_filter_columns` inline +
  `tpl_table_parts`) sehingga memakai konfigurasi kolom **menggagalkan cetakan 500 "list index out
  of range"** — artinya fitur pilih-kolom yang lama pun sebenarnya rusak.

## Yang dikerjakan
**W1 — tabel stok**
- `GET /api/rahaza/material-stock` & `GET /api/wms/stock/unified` kini mengirim identitas dari
  MASTER: `material_code`, `category_name`, `color_name`, `option_name`, `size_code`, satuan, lokasi
  (kode+nama). Tidak ada penebakan dari string SKU.
- Filter baru di viewer: `category`, `color`, `option`, `material_type` + `facets` (isi dropdown
  dibangun dari nilai yang benar-benar ada).
- Saklar **"tampilkan juga yang stoknya 0"** (`include_zero=1`) menambahkan barang master yang belum
  punya baris stok (qty 0, `no_stock_row`) ⇒ daftar bisa disamakan dengan Master Item: **26 → 322
  baris** (296 barang belum punya stok).
- Layar: kolom **Kategori · Warna · Opsi** + filternya di kedua tabel stok; **UUID material_id
  DIBUANG** dari tabel, dialog log/adjust, dan **ekspor CSV** (header kini "Kode Barang").
- Baris tanpa lokasi tidak bisa di-adjust (penyesuaian wajib menyebut lokasi) — diarahkan ke
  "Penerimaan" agar stok lahir dengan lokasi yang jelas.

**W2 — ekspor fleksibel**
- Backend: `?cols=a,b,c` pada `/api/export-pdf` = **pilihan kolom SEKALI CETAK** (menang atas
  template/konfig bernama, tidak mengubah setelan global). Kunci divalidasi terhadap SSOT katalog
  kolom; kolom **wajib** selalu ikut; kunci karangan diabaikan (bukan 500).
- **BUG LAMA DITUTUP**: penyaringan kolom ganda dihapus ⇒ konfigurasi kolom bernama (`?config_id=`)
  pada laporan produksi tidak lagi 500.
- Frontend: komponen baru **`PdfColumnPicker`** — dialog "Kolom PDF" yang membaca katalog kolom
  (`/api/pdf-export-columns`), menandai kolom wajib, mengingat pilihan per jenis dokumen, dan
  terpasang di **Laporan Produksi/Maklon** (`ReportsModule`) & **SPP Produksi/Maklon**
  (`ProductionPOModule`).

## Bukti
- Layar stok: kolom `BARANG · KATEGORI · WARNA · OPSI · JENIS · LOKASI · QTY · MIN STOK · STATUS`
  (tanpa kolom id), filter Kategori/Warna/Opsi hidup, saklar stok 0 mengubah **40 → 336 baris**
  ("296 barang belum punya stok"). Teks "Material ID" **0 kemunculan** di layar.
- Cetak dari layar (klik nyata, bukan API): pilih **No · Serial · Produk · Qty** → PDF terunduh
  `laporan_production_2026-08-20.pdf` berisi TEPAT 4 kolom itu dengan nomor seri (`SN-MK1-A`), dan
  kolom Vendor/Warna/HPP/SKU/Size **hilang**; kop surat tetap utuh.
- Gate baru **INV-F32** (11 invarian, read-only) HIJAU · `bash scripts/gate.sh` **VERDICT HIJAU 50
  gate** (INV-F31 & INV-F32 lulus, tanpa regresi) · stok tetap **33.503** (tidak ada data uji tertinggal).

---

# [2026-08-19 #29] **RETUR PEMBELI AKHIRNYA SAMPAI KE GUDANG DAN KEMBALI KE STOK** (W4)

## Keluhan pemilik
"Retur Fisik & Restock Gudang tidak terkoneksi/berhubungan ke portal marketing." Pemilik menegaskan:
kata **"usang" BUKAN berarti dimatikan** — fitur itu harus **DIHIDUPKAN**.

## Yang diukur lebih dahulu (bukan dugaan)
- `marketing_returns` = **30 dokumen retur pembeli NYATA**, `wh_returns` = **0** ⇒ layar Retur Fisik
  gudang **kosong selamanya**; `production_returns` & `production_return_items` = 0.
- Jembatan yang ada (`POST /api/marketing/returns/{id}/create-wh-return`): harus **diklik manual**,
  hanya boleh status approved/completed, dan mengirim **`sku_code=""` + `qty=1`** ⇒ gudang tidak tahu
  barang apa yang kembali.
- Lebih parah: tombol **"Restock ke Gudang"** pada `POST /api/wh/returns/{id}/resolve` menulis ke
  **`rahaza_fg_inventory` — koleksi MATI (0 dokumen)** — dan mencari item lewat `sku_code` yang selalu
  kosong. Artinya menekan tombol itu **100% tidak pernah menambah stok** dan tidak meninggalkan satu
  baris ledger pun. Barang retur hilang dari pembukuan stok tanpa satu pun error.

## Yang dikerjakan
- **`backend/core/returns_bridge.py` (SSOT baru)** — jembatan satu arah, idempoten, TIDAK MENEBAK:
  identitas barang dari `catalog_item_id` → `sku` → `marketing_orders.items[].fg_material_id`
  (hasil SKU Bridge sesi #28). Pesanan multi-baris tanpa penunjuk ⇒ pekerjaan tetap MUNCUL, ditandai
  `needs_manual_resolution`, stok TIDAK disentuh.
- **Stok hanya lewat satu pintu**: `core/stock_service.add` + baris `rahaza_stock_ledger`
  (`ref.ref_id` = id retur gudang). Penjaga atomik `restocked` dipasang SEBELUM stok ditambah ⇒ klik
  dua kali / dua proses paralel tidak bisa menggandakan stok.
- **Kondisi barang menentukan lokasi**: **Baik → `ZNA-FG`** (ikut stok jual) · **Rusak →
  `ZNA-KARANTINA`** yang oleh K-6a (`core/catalog_stock`) dikecualikan dari stok jual ⇒ barang rusak
  tidak bisa terjual, tetapi tetap tercatat fisiknya.
- **Otomatis sejak retur dibuat di Marketing** (keputusan pemilik) + jaring pengaman saat approve +
  tombol **"Tarik Retur dari Marketing"** untuk retur lama (idempoten).
- **Aksi cepat "Terima & Restock"** satu klik di gudang (timeline Received→Inspected→Resolved tetap
  ditulis lengkap), `relink` untuk retur yang belum tertaut, dan **pemilih barang dari MASTER**
  (`FGMaterialSelect`) menggantikan kolom teks bebas "SKU / Kode Produk" (INV-F14).
- **Layar menyatakan efek stok**: kolom **Efek Stok** (`+N stok jual` / `+N karantina` / `belum
  tertaut master`), spanduk angka jembatan, dan di Marketing "Efek stok: +2 karantina (ZNA-KARANTINA)".
- **Gate baru INV-F31** (`scripts/verify_jembatan_retur_marketing_gudang.py`, 15 invarian,
  self-cleaning penuh: membuat retur uji Baik/Rusak/ambigu pada data hidup, mengukur stok
  sebelum-sesudah, lalu mengembalikan semuanya).

## Bukti (sebelum → sesudah)
- `wh_returns` **0 → 22** · retur pembeli tanpa pekerjaan gudang **22 → 0** · baris ledger dari retur
  **0 → 21** · total stok **33.482 → 33.503** (+21 pcs barang retur benar-benar masuk) · 1 retur
  ambigu ditandai tanpa menyentuh stok.
- `bash scripts/gate.sh` **VERDICT HIJAU 49 gate** (INV-F31 hijau, tanpa regresi).
- Diverifikasi lewat DOM (bukan hanya API): retur Marketing kondisi **Rusak qty 2** ⇒ baris gudang
  **"+2 karantina"**, detail Marketing **"Efek stok: +2 karantina (ZNA-KARANTINA)"**. Seluruh data uji
  (milik saya & testing agent) dibersihkan; stok kembali persis 33.503.

## Catatan jujur
- Retur berstatus `rejected`/`cancelled` SENGAJA tidak dijembatani (barangnya tidak kembali).
- Bila retur yang sudah menambah stok kemudian DITOLAK, API `reject` mengembalikan **peringatan**
  berisi qty & lokasi supaya gudang bisa menyesuaikan — bukan diam-diam.

---

# [2026-08-19 #28] **IDENTITAS BARANG DITEGAKKAN** — 553 pesanan yang mandek akhirnya bisa dikerjakan gudang · penerimaan barang tidak lagi selalu 0

## Titik mula
`/app` datang sebagai template kosong; kode dipulihkan dari `github.com/akskxuyd/DA` +
`bash scripts/bootstrap.sh` (60 detik, 6 akun login HTTP 200). Pemilik menunjuk todo list sesi #20
(Jembatan SKU / INV-F29) dan bertanya "sudah kah anda cek perubahan ini". **Diukur lebih dahulu, dan
semuanya MEMANG SUDAH SELESAI**: `core/sku_bridge.py` 1.227 baris · `routes/sku_bridge.py` 12
endpoint · `routes/sync_audit.py` terpasang · RC-2 kosakata status diperbaiki lewat SSOT
`core/fulfillment_status.py` · `SkuBridgeModule.jsx` + `SyncAuditModule.jsx` terdaftar di registry &
sidebar · **INV-F29 HIJAU 19 invarian** · `gate.sh` **VERDICT HIJAU 47 gate**.

**Tetapi laporan audit sistem sendiri berkata MERAH skor 0.** Jembatannya dibangun, dan tidak satu
barang pun pernah dijembatani:
`A1 CRITICAL: NOL dari 601 baris pesanan menunjuk master gudang` ·
`A5: 553 pesanan di antrean gudang, TIDAK SATU PUN siap dialokasikan` ·
`A3: 83 SKU platform dipesan pembeli tetapi belum dikenal master`.

## Kenapa mandek (diukur pada 83 SKU nyata, bukan ditebak)
83 SKU itu ternyata hanya berasal dari **8 produk nyata** (Jennifer Blouse 53 SKU/409 pcs · Rachel
Oneset 6/73 · Victoria Top 8/65 · Ona Dress 6/30 · Biel Top 3/13 · Jepit Jedai 2/7 · Aisar Dress 3/4
· Rasha Blouse 2/2) dan **0 master yang cocok** (pencarian `Jennifer/Rachel/Victoria/ONA/BIEL/AISAR/
RASHA` semuanya 0 — master masih berisi produk demo Celana Jogger & Hoodie).

`sku_bridge.parse_variation` diuji pada 83 string itu: **83 SKU → hanya 35 identitas · 16 kelompok
TABRAKAN · 63 SKU (76%) dan 489 pcs (81%) tertimpa.** Terburuk **8 SKU berbeda jatuh ke satu
identitas `hitam/XL`**: `BLACK…PAKAI KARET` (39pcs) · `POLKA BLACK…PAKAI KARET (SMOOK)` (12) ·
`POLKA BLACK…TANPA KARET` (10) · `BLACK…TANPA KARET` (7) · dst. Dua akar sebab:
1. **Warna majemuk dipotong.** Pencocokan memakai *substring* (`if alias in n`) sehingga
   `POLKA WHITE` menemukan alias `white` → jadi `putih`; motif polkadot HILANG dan barang polkadot
   menjadi identik dengan barang polos.
2. **Dimensi ketiga dibuang.** `PAKAI KARET` / `TANPA KARET` / `PAKAI KARET (SMOOK)` tidak dibaca
   sama sekali, dan skema varian hanya punya 2 sumbu (warna × ukuran) — tidak ada tempat
   menyimpannya. Index unik `model_size_color_variant_unique` bahkan MENOLAK varian ber-opsi beda.
3. **Bonus cacat ketiga:** `clean_product_name` justru MEMBUANG nama produknya —
   `'ONA DRESS - Midi Dress Salur…'` → `'Midi Dress Salur…'` (**ONA hilang**);
   `'OUTFIT BOUTIQUE BIEL TOP | ATASAN RAYON…'` → `'Atasan Rayon'` (**BIEL TOP hilang**). Empat
   produk bisa lahir sebagai satu model bernama kalimat iklan.

Yang menyelamatkan: ambang `AUTO_MIN_CONFIDENCE` 0,82 + invarian S7 ("mesin menolak menebak")
memblokir semuanya ⇒ **belum ada data salah yang sempat tertulis.** Sistem jujur, tapi mandek total.

## Keputusan pemilik (dikonfirmasi, jangan ditebak ulang)
**1a** `PAKAI/TANPA KARET` & `(SMOOK)` = **dimensi ketiga resmi "Opsi"**, SKU jadi
`{MODEL}-{WARNA}-{UKURAN}-{OPSI}` · **2a** `POLKA WHITE`/`POLKA BLACK` = warna master tersendiri ·
**3a** listing tanpa keterangan karet = varian tersendiri beropsi **"Tidak Disebut"** (bukan digabung
— menggabungkan = mengarang) · **4a** `ODI ALL SIZE WARNA RANDOM` → warna **"Random / Campur"** ·
**5a** Jepit Jedai = kategori **Aksesoris** ukuran BESAR/KECIL, Rasha = JMB/STD, Rachel/Ona/Biel/
Aisar = ALLSIZE · **6a** warna master kembar **dirapikan**.

## POC lebih dahulu (inti tersulit, terpisah, sebelum satu baris UI ditulis)
`test_core_sku_identity.py` → **HIJAU 22 lulus / 0 gagal** pada data NYATA:
**83 SKU → 70 identitas · 0 tabrakan** (turun dari 16 kelompok/63 SKU) · **0 warna & 0 ukuran gagal
dibaca** (turun dari 18 & 20) · 13 pasang listing kembar benar-benar berbagi satu identitas ·
**330 SKU varian lama TIDAK berubah sedikit pun** · dry-run terbukti tidak menulis (11 koleksi
dipantau) · apply idempoten · rollback memulihkan bersih.

## Yang dikerjakan
- **`core/variant_identity.py` (baru, ±1.100 baris)** — SSOT identitas varian 3 dimensi:
  pemecah variasi yang **injektif** (variasi beda ⇒ identitas beda; variasi sama ⇒ identitas sama),
  kamus warna yang hanya menyatukan **sinonim bahasa** (nuansa TIDAK digabung: `Butter Yellow` bukan
  `Kuning`), penyalinan warna baru apa adanya (menyalin ≠ menebak), pembaca opsi, ukuran beranotasi
  (`XL (LD 120 CM)` → XL + spec), prefiks produk di variasi (`AISAR - MAHOGANY`), ukuran aksesoris
  (`JEDAI BESAR 5 cm`), `propose_model_name` yang mempertahankan nama produk, onboarding
  **per PRODUK** (rencana → terapkan, idempoten), rollback, dan perapian palet warna.
- **Skema aditif & kompatibel-balik**: master `rahaza_variant_options` (NA/KRT/NOK/SMK), kolom
  `option_*` pada 330 varian lama (`NA`), index unik dipindah **3 sumbu → 4 sumbu**. Opsi `NA` dan
  warna `TDI` **tidak masuk SKU** ⇒ SKU lama mustahil berubah (`AKS-0001-BESAR`, bukan
  `AKS-0001-TDI-BESAR`). `utils/variant_ssot.py` ikut membawa opsi ke FG (nama FG tidak lagi kembar
  untuk 'Pakai Karet' vs 'Tanpa Karet').
- **`routes/variant_onboarding.py`** — 10 endpoint: `products` · `plan` · `apply` · `rollback` ·
  `identity-preview` · `options` (GET/POST/DELETE) · `colors/duplicates` · `colors/merge` ·
  `masters/ensure`.
- **Layar**: tab **"Onboarding Produk"** (jadi tab pertama) & **"Opsi Varian"** di Jembatan SKU —
  8 kartu produk, "Susun Rencana" → pratinjau lengkap (varian + SKU yang akan lahir, warna/ukuran
  baru, jumlah SKU & baris pesanan), lalu "Terapkan". **Nama model tidak bisa diketik** (gate
  INV-F14): ia diturunkan server dan hanya ditampilkan; pemilik MENUNJUK model master lewat pemilih.
- **Perapian palet warna (6a)**: 5 kelompok kembar (`Putih` PTH+WHT · `Hitam` HTM+BLK · `Merah`
  MRH+RED · `Krem` KRM+CRM · `Abu`+`Abu-abu`) — satu model bahkan punya **dua varian "Putih"**
  (`DA-TS01-PTH-S` & `DA-TS01-WHT-S`). 80 varian kembar dihapus, 5 warna dinonaktifkan, apa pun yang
  punya stok/kartu/pesanan **DILEWATI dan dilaporkan** (bukan dibereskan diam-diam).
- **Audit sinkronisasi diperluas**: temuan **C5** (warna kembar) & **C6** (varian tanpa dimensi
  opsi) + 2 perbaikan ber-pratinjau (`merge_duplicate_colors`, `ensure_variant_option_dimension`).
  Temuan **B3** dipecah: fixture demo yang sengaja dibuat seeder (`LEGACY-NOLINK-001`) turun jadi
  **INFO B3d** — kalau fixture dihitung sebagai cacat, skor mustahil hijau dan pemilik dilatih
  mengabaikan temuan HIGH.

## Hasil bisnis (ini tolok ukurnya, bukan jumlah baris kode)
| | sebelum | sesudah |
|---|---|---|
| baris pesanan tertaut master | **0 / 601** | **601 / 601 (100%)** |
| pesanan antrean gudang siap | **0** dari 553 | **553** |
| SKU platform belum dikenal | 83 | **0** |
| pemetaan jembatan | 0 | 83 |
| `sync-audit` | **MERAH skor 0** (1 CRITICAL · 6 HIGH) | **HIJAU skor 79** (0 CRITICAL · 0 HIGH) |

8 produk lahir jadi master: `BLS-0001` Jennifer Blouse (40 varian) · `SET-0001` Rachel Oneset ·
`BLS-0002` Victoria Top · `DRS-0001` Ona Dress · `BLS-0003` Biel Top · `AKS-0003` Jepit Jedai ·
`DRS-0002` Aisar Dress · `BLS-0004` Rasha Blouse. Contoh yang dulu tertimpa, sekarang terpisah:
`BLS-0001-PBL-XL` · `-XL-KRT` · `-XL-NOK` · `-XL-SMK`.

## BUG FATAL YANG DILAPORKAN PEMILIK DI TENGAH SESI — dan ditutup
> "qty received di recieving goods masih tidak bisa diinputkan masih 0 … pembelian tidak bisa
> menambahkan barang, ini cacat fatal"

**Terreproduksi di layar**: GR-00001 menampilkan `Qty diharap 100` tetapi `Qty diterima 0` padahal
statusnya `received`. Akar masalahnya bukan kolomnya rusak — **kolomnya tidak ada**:
1. GR yang lahir dari PO (`create-gr`) selalu dibuat `received_qty: 0.0` (benar — barang belum
   dihitung), tetapi satu-satunya layar untuk memprosesnya (modal Detail) hanya **MENAMPILKAN** qty
   sebagai teks. Tombol yang tersedia hanya *Delete* dan *Confirm Received* ⇒ petugas cuma bisa
   mengkonfirmasi angka **NOL** ⇒ **stok tidak pernah bertambah.** Form "New Receipt" punya
   kolomnya, tetapi GR dari PO tidak pernah melewati form itu.
2. `handleStatusChange` **tidak** memetakan `reject_reason` (UI) → `reject_reasons[]` (kontrak
   karantina) — `handleCreate` melakukannya, jalur konfirmasi tidak ⇒ alasan reject hilang.
3. GR dari PO tidak punya `location_id` dan modal detail tidak punya pemilih lokasi ⇒ stok mendarat
   di baris **berlokasi kosong**: ada di sistem, tidak ada di rak mana pun.

**Perbaikan**: kolom `Qty Diterima`/`Qty Ditolak` per baris + select alasan reject + pemilih
**Lokasi Tujuan** + tombol *"Terima semua sesuai PO"* + ringkasan total + peringatan "masih 0" dan
tombol Confirm **dinonaktifkan** selama total 0 + peringatan over-receive. Pemetaan
`reject_reason → reject_reasons[]` diperbaiki. **Penjaga di API** (bukan hanya layar): transisi ke
`received` DITOLAK 400 bila total qty 0, dan DITOLAK 400 bila `location_id` kosong.

**Bukti**: pengujian lewat UI — 98 diterima / 2 ditolak (alasan `FABRIC_DEFECT`) → 96 pcs masuk
Area Aksesoris, 2 pcs ke Area Karantina QC, PO `qty_received=96`. **Testing agent iterasi 80**
menutup keterbatasan iterasi 79: mengetik `45` lalu **membaca kembali `45` dari DOM** (bukan 0),
`5` di kolom ditolak terbaca `5`, kedua penjaga 400 terbukti — **0 bug kritis, 0 peringatan.**

## Alat ukur tidak boleh mengotori data yang diukurnya (2 kebocoran gate ditutup)
- **`gate.sh` menggerus stok nyata.** Terukur: `ACC-DA-LBL` turun **10 pcs SETIAP kali gate
  dijalankan** (1800 → 1790 → 1780 → 1770 → 1760) karena `verify_fase_h1…clean()` menghapus dokumen
  MI-nya tetapi **tidak pernah mengembalikan stok** yang sudah dipotong. Lebih buruk: query hapus
  kartu stok memakai `ref_id` di tingkat atas padahal tersimpan bersarang (`ref.ref_id`) ⇒ **8 kartu
  stok YATIM** menunjuk MI yang sudah tidak ada. Keduanya diperbaiki; 40 pcs + 10 kg dipulihkan;
  dibuktikan dengan mengukur stok sebelum/sesudah gate: **selisih 0**.
- **Gate cutting meninggalkan rujukan rusak.** `verify_fase_h5_h6_roll` & `verify_fase_h6b…`
  menghapus MASTER potongan tetapi meninggalkan **baris stok & kartu stok**-nya ⇒ `sync-audit`
  melaporkan 2 rujukan rusak baru (D4/E1) tiap kali gate jalan. Id potongan sekarang diambil lebih
  dahulu, stok/kartunya dihapus, baru masternya.

## Penjaga baru — INV-F30 (23 invarian)
`scripts/verify_identitas_varian_3dimensi.py`: identitas injektif · warna majemuk utuh · tidak ada
pencocokan substring · dimensi ke-3 hidup di DB · index unik 4 sumbu · opsi dari master · SKU
kompatibel-balik · pratinjau tanpa tulis · apply idempoten · rantai pemetaan→varian→FG→katalog utuh ·
palet bebas kembar · SKU unik · **pintunya ada di layar** + endpoint yang dipanggil layar benar-benar
ada · nama model tidak membuang identitas produk · **0 rujukan stok menggantung**.
Bila masih ada produk belum tertaut, gate mengerjakan onboarding produk ber-opsi terbanyak lalu
**membatalkannya kembali** — ia tidak pernah "lulus dengan sopan" karena data ujinya tidak ada.

## Bukti akhir
`python3 test_core_sku_identity.py` → **22 lulus / 0 gagal** ·
`python3 scripts/verify_identitas_varian_3dimensi.py` → **HIJAU 23 invarian** ·
`bash scripts/gate.sh` → **VERDICT HIJAU, 48 gate** (47 lama + INV-F30, tanpa regresi) ·
`GET /api/sync-audit/report` → **HIJAU skor 79** ·
testing agent **iterasi 79 & 80: 100% lulus, 0 bug kritis**.

---

# [2026-08-19 #27] **FASE G DITUTUP** — 27 jenis dokumen benar-benar ditegakkan · katalog penomoran tidak lagi buta

## Titik mula
`/app` datang sebagai template kosong; kode dipulihkan dari `github.com/skaksudggd/DA` +
`bash scripts/bootstrap.sh`. Tiga gate yang MERAH pada receipt terakhir diukur ulang LEBIH DAHULU:
**INV-F14 34/34 · INV-MKTFULFILL 55/55 · INV-F10 21/21 · gate.sh VERDICT HIJAU** ⇒ pekerjaan sesi
lalu memang sudah selesai. Sisa roadmap yang dikerjakan sesi ini: **Fase G — 17 jenis dokumen
`pending_enforce`**.

## Yang dikerjakan
- **15 jenis dokumen disambungkan** ke satu pintu `core.doc_number_policy.issue_number`:
  Klaim Biaya · Perjalanan Dinas · Penyelesaian Dinas · Transfer Bank · Permak · Permintaan
  Komponen Kurang · Permintaan Aksesoris · Permintaan Kreator · Retur Produksi (RTN) ·
  Pengeluaran Barang Jadi · Permintaan Beli Aksesoris · Sampel Maklon · Aset Tetap ·
  Aset Inventaris (+ Order Penjualan yang kemudian diklasifikasi ulang, lihat di bawah).
  **Tiga di antaranya sebelumnya menerima nomor ketikan TANPA pemeriksaan apa pun**
  (`body.get('request_code') or gen_prefixed_number(...)`): pola bebas lolos, nomor kembar
  tidak dicek.
- **10 form yang "ditegakkan" tetapi TIDAK punya kolom nomor** dipasangi `<DocNumberField>`
  (mode MANUAL = dokumen mustahil dibuat dari layar): Pengeluaran FG · PR Aksesoris ·
  Sampel Maklon · Aset Tetap · Aset Inventaris · Penerimaan FG dari CMT · Invoice Maklon ·
  Invoice Piutang (AR) · Pengajuan Pinjaman · SPP/PO Maklon Produksi (didaftarkan).
- **Empat jenis dicabut/diklasifikasi ulang** karena setelannya mustahil dipakai:
  Pinjaman Karyawan legacy (pintu ditutup **HTTP 410**, koleksi sudah diarsipkan T2.1) ·
  Retur Material Produksi (menu di-deprecate pemilik) · Roll Kain (lahir dari rincian
  penerimaan kain — MANUAL justru MEMBUAT PENERIMAAN GAGAL) · PO Maklon koleksi maklon &
  Order Penjualan (layarnya sudah dinonaktifkan dari UI).
- **Dua cacat data**: kode Aset Tetap dibuat dengan nama field salah (`asset_code` vs field
  dokumen `code`) sehingga penyemaian counter membaca field yang tak pernah ada; dan 4 jenis
  punya format di katalog yang TIDAK PERNAH dipakai kode (kini pakai token `{ORDER}`,
  `{KATEGORI}`, `{TIPE}` sehingga pratinjau = nomor yang benar-benar akan lahir).
- **Seeder demo roll kain** diperbaiki: tidak lagi mengirim nomor (ditolak Fase G ⇒ bootstrap
  fresh-clone selalu "4 gagal" & layar Roll Kain kosong); idempotensi memakai tanda tangan
  bahan·warna·lot + penanda DEMO.

## Penjaga baru (INV-F25: 9 → 13 invarian)
- **G10** batch-3A pada dokumen sungguhan · **G11** pintu pinjaman legacy mati ·
  **G13** batch-3B pada dokumen sungguhan (Permak dilaporkan **TIDAK TERUKUR = MERAH** bila PO uji
  tak ada — bukan "lulus dengan sopan").
- **G12 — katalog wajib memuat SETIAP seri nomor yang dibuat kode.** G9 hanya memeriksa entri yang
  sudah ada; ia buta terhadap yang tak pernah didaftarkan. Audit menemukan **5 seri hidup di luar
  katalog** (Retur Produksi RTN · Job Produksi · Job Cetak Barcode · Kode Supplier · seri WO yang
  sudah mati). Pengecualian sekarang harus TERTULIS + beralasan.
- **G4 diperbaiki**: kunci uji "belum ditegakkan" dipilih dari registry (dua sesi berturut-turut
  gate ini merah karena kunci hardcode-nya ikut ditegakkan).
- **G7 diperketat**: setiap kunci `policy_enforced` wajib punya form yang (a) terdaftar, (b) membaca
  kebijakan, dan (c) **BISA DIBUKA dari UI**. Aturan (c) menemukan layar Order Penjualan yang
  file-nya masih ada tetapi menunya sudah dinonaktifkan.

## Bukti
- `python3 scripts/verify_fase_g2_penomoran_ditegakkan.py` → **HIJAU 13 invarian**.
- Katalog: **51 jenis — 27 ditegakkan · 23 selalu otomatis (beralasan) · 1 menunggu**
  (Kode Supplier, menunggu keputusan pemilik).
- `bash scripts/gate.sh` → **VERDICT HIJAU** (seluruh suite).
- **Testing agent iterasi 78: backend 45/45 PASS · UI 100% (semua butir HIJAU) · 0 isu.**
  Uji baru yang ikut ditinggalkan: `backend/backend_test_doc_numbering_session27.py`.

---

# [2026-06-18 #22] **MONITORING CMT DIRAPIKAN: 12 KARTU URUT ALUR PROSES + PEMERIKSA KESEIMBANGAN**

## Pertanyaan pemilik yang memicu ini
> "di card kirim ke buyer ada sisa kirim 90, itu dari mana nilainya? kalau disetor baru 100,
> logikanya disetor − dikirim buyer harusnya 40 kan?"

**Jawaban hasil pemeriksaan data (bukan tebakan):** 90 = **lolos QC 90 pcs** milik PO-MKL-…-9006
(disetor 100, 10 pcs reject ⇒ hanya 90 yang boleh dikirim), sedangkan **60 pcs yang sudah ke buyer
milik PO LAIN** (PO-MK-DEMO-2, penerimaannya bahkan masih `on_qc`). Jadi `100 − 60` mengurangkan dua
PO yang berbeda. Rumus sisa bisa kirim memang **per PO/per item**, bukan agregat. Yang salah bukan
angkanya, tapi **kartunya**: tahapan proses tidak terlihat sehingga mata pemakai menghubungkan angka
yang tidak sebanding.

## Yang dikerjakan (semua atas persetujuan pemilik)
- **12 kartu, diurut sesuai alur proses** (dan diberi nomor 1..12 di layar):
  1 Order (Qty PO) · 2 Belum Dikirim ke CMT *(sub: dari PO Draft)* · 3 Potongan ke CMT *(sub:
  +pengganti/tambahan)* · 4 Sisa di CMT *(sub: selisih belum sampai)* · 5 Disetor dari CMT *(sub: Nx
  setor)* · 6 **Lolos QC** · 7 **Reject Belum Jelas** (masih dipermak/belum diputuskan) ·
  8 **Permak Berhasil** · 9 **Scrap / Hilang** · 10 **Sisa Bisa Kirim** · 11 Sudah Dikirim ke Buyer ·
  12 **Biaya** (ongkos jahit + biaya permak dalam satu kartu, dua angka terpisah).
- **Kartu 'Biaya Permak' yang berdiri sendiri dihapus** (digabung ke kartu 12) dan slotnya dipakai
  **Scrap/Hilang** — qty yang benar-benar hilang / permak gagal, permintaan pemilik.
- **PO TELAT & Komponen Kurang turun** jadi 2 chip di panel "Distribusi Status Kejar"
  (`chip-po-telat`, `chip-komponen-kurang`) — tidak dihapus, hanya tidak lagi memakan slot kartu.
- **Baris pemeriksa keseimbangan** (`monitor-balance-strip`) — 5 identitas yang membuat kartu tidak
  bisa mengarang, tiap baris ✓/✗ dan yang ✗ bisa diklik untuk **menyebut PO penyebabnya**:
  ```
  Order            = Belum ke CMT + Potongan ke CMT
  Potongan ke CMT  = Sisa di CMT + Disetor
  Disetor          = Lolos QC + Reject
  Reject           = Permak Berhasil + Scrap + Belum Jelas
  Lolos QC + Permak Berhasil = Ke Buyer + Sisa Bisa Kirim
  ```
- **Sumber angka baru** semuanya dari `cmt_receipt_lines` yang sudah dibaca layar lain
  (`qty_actual`, `reject_qty`, `qty_reworked_ok`, `qty_reject_scrapped`, `qty_short`) — tidak ada
  koleksi baru, tidak ada rumus kedua.

## Temuan yang langsung ketangkap pemeriksa keseimbangan
**PO-MK-DEMO-2**: 60 pcs tercatat sudah dikirim ke buyer padahal penerimaannya belum di-QC
(data demo lama, dibuat sebelum pagar kapasitas Fase E ada). Identitas ke-5 menandainya ✗ dan
menyebut nomor PO-nya, jadi anomali seperti ini tidak bisa lagi lewat tanpa terlihat.

## Bukti
- Gate **INV-F28 naik jadi 11 invarian, HIJAU** — tambahan **F28-7** (5 identitas cocok pada PO uji:
  order 100 = gudang 0 + keCMT 100 · disetor 100 = lolos 90 + reject 10 · reject = permak 0 + scrap 0
  + belum jelas 10 · siap 90 = terkirim 40 + sisa 50) dan **F28-7b** (identitas yang pecah WAJIB
  menyebut PO penyebab — kalau bisu, gate merah). F28-6 kini memeriksa 18 pintu layar.
- **Gate penuh** `bash scripts/gate.sh` → **VERDICT HIJAU**.
- **Testing agent iterasi 77**: 5/5 uji backend + 5/5 butir UI LULUS (12 kartu urut & nilainya cocok
  dengan API, chip scope tetap bekerja, baris keseimbangan menyebut PO-MK-DEMO-2, kontras & tata
  letak 1920px bersih). **0 isu.**


---

# [2026-06-18 #21] **MONITORING CMT: POTONGAN SESUAI ORDER** — 2 kartu baru · sudut pandang PO · Papan Sisa Kirim · rantai PENGGANTI terlacak

## Cacat yang diukur lebih dulu (bukan dugaan)
`scripts/verify_monitoring_cmt_potongan.py` dijalankan SEBELUM perbaikan dan MERAH di 8 titik:
- **Potongan ke CMT 105 pcs untuk order 100 pcs.** `services/cmt_kejar.py` menjumlahkan SEMUA
  `vendor_shipment_items` milik PO, jadi surat jalan **ANAK** (pengganti/tambahan hasil persetujuan
  permintaan material) ikut ditambahkan ke potongan.
- **"Sisa di CMT" 5 pcs HANTU** walau CMT sudah menyetor semuanya — akibat langsung dari poin di atas
  (dikirim 105 − disetor 100).
- **PO `Completed` ikut dihitung.** Papan hanya membuang `Closed/Cancelled/Selesai`, jadi angka
  "yang sedang berjalan" tidak pernah bisa dilihat.
- **Tidak ada angka "belum dikirim ke CMT" maupun "sudah dikirim ke buyer"**, padahal keduanya bisa
  dihitung dari SSOT yang sudah dipakai layar lain.
- **Rantai PENGGANTI tidak terlacak**: persetujuan sudah menerbitkan SJ anak `…-R1` sejak lama,
  tetapi layar hanya melihat nomornya — tanpa kabar sudah diterima/diinspeksi atau belum.

## Yang dikerjakan
- **Potongan = kiriman NORMAL saja.** `shipment_kind()` memisahkan NORMAL vs anak (dari
  `parent_shipment_id` ATAU `shipment_type`, dengan lapis cadangan di level item). Kiriman anak
  **tidak dihilangkan**: `qty_sent_extra` + rinciannya tampil sebagai panel "kiriman di luar order"
  supaya tidak ada angka yang terasa hilang. "Sisa di CMT" ikut sembuh sendiri.
- **Dua kartu baru** (permintaan pemilik): **Belum Dikirim ke CMT** = Σ(order − terkirim NORMAL) untuk
  PO pada sudut pandang aktif, dengan sub-baris "dari PO Draft: X pcs"; **Sudah Dikirim ke Buyer** =
  dari SSOT `core/dispatch_capacity` (rumus yang sama dengan pagar `POST /api/buyer-shipments`,
  bukan rumus kedua) + sub "sisa bisa kirim".
- **Sudut pandang PO**: chip **"PO Berjalan"** (default; Draft · Confirmed · Distributed ·
  In Production) ↔ **"Semua PO"**. Seluruh kartu + papan Kejar CMT ikut berubah
  (`?scope=running|all` pada `/api/dewi/cmt-kejar` dan `/dashboard`).
- **Papan Sisa Kirim per PO** di tab "Kekurangan Kirim" (menu Dispatch ke Buyer): satu baris per PO
  (order · terkirim · progres · sisa order · sisa bisa kirim · surat jalan berjalan) + tombol yang
  langsung **melanjutkan** surat jalan <100% atau membuka form dengan PO itu terpilih. Angkanya
  digabung dari `/api/buyer-dispatch-outstanding` — tidak ada rumus baru.
- **Rantai PENGGANTI terlacak dua arah**: komponen `MaterialRequestTracker` menggambar
  Diajukan → Disetujui → **SJ pengganti (nomor)** → Diterima vendor → Diinspeksi, dipakai DI KEDUA
  layar (portal vendor CMT & layar admin). Backend menambah `child_shipment_status`,
  `child_received_at`, `child_inspected` pada `GET /api/material-requests`; SJ anak menunjuk balik
  (`material_request_number`) dan SJ induk melaporkan `child_qty_total` (juga di daftar).
- **Perbaikan ikutan**: PO berstatus `Confirmed` tidak termasuk daftar pilihan PO, jadi modal yang
  dibuka dari papan menampilkan dropdown kosong — `ensurePOInList()` menyisipkan PO itu supaya
  labelnya benar (`loadPOItems(poId, poOverride)`).

## Bukti
- Gate baru **`scripts/verify_monitoring_cmt_potongan.py` (INV-F28)** — 9 invarian HIJAU (dulu 8 MERAH),
  terdaftar di `scripts/gate.sh`. Termasuk F28-4c: **kartu ringkasan = penjumlahan baris papan**
  untuk 5 angka (anti dua rumus) dan F28-6: pintunya ADA di layar.
- **Gate penuh**: `bash scripts/gate.sh` → **24 gate, VERDICT HIJAU**.
- **Testing agent iterasi 75** (API + UI awal) dan **iterasi 76** (E2E dengan data nyata):
  10/10 uji backend + 5/5 butir UI LULUS — pelacak pengganti terlihat di dua layar, chip scope
  mengubah angka (4 PO/550 pcs berjalan → 5 PO/750 pcs semua), "dari PO Draft: 50 pcs" muncul,
  papan → "Dispatch Baru" → "Lanjut Dispatch" berjalan pada satu nomor surat jalan.
  **0 isu kritis, 0 isu UI, 0 isu desain.**
- Data uji layar bisa dibuat ulang kapan saja: `python3 scripts/_seed_uji_monitoring_cmt.py`
  (bersihkan dengan `--clean`).


---

# [2026-06-18 #20] **LIMA CACAT PRODUKSI/MAKLON DITUTUP** — permak menaikkan sisa kirim · dispatch lanjutan · aksesoris BOM di form PO · vendor CMT bisa minta PENGGANTI

## Temuan pembuka sesi: dua perbaikan layar sebenarnya BELUM PERNAH DITULIS
Sesi sebelumnya melaporkan tujuh berkas selesai, tetapi pengukuran ulang menunjukkan:
`BuyerShipmentModule.jsx` **tidak tersentuh sama sekali** (tombol "+ Dispatch" tidak ada) dan
`ProductionPOModule.jsx` hanya berisi **state `bomAcc` kosong** tanpa pemanggilan server maupun
panel — jadi dua dari lima keluhan pemilik masih 100% tidak terjangkau pemakai walaupun backendnya
sudah jadi. Tidak ada gate, tidak ada uji, dan komentar kode sudah menjanjikan gate **INV-F27** yang
belum pernah dibuat. Pelajarannya dicatat: *backend jadi ≠ fitur ada*.

## Yang dikerjakan
- **BUG 1 — permak ↔ reject (backend, dari sesi lalu, kini TERUKUR).** Permak dari form manual
  ("Buat Permak Baru", tanpa memilih baris penerimaan) ditautkan server ke baris penerimaan yang
  masih punya sisa reject (FIFO, `source_link_auto=true`, dipecah bila sisa reject tersebar di
  beberapa baris). Permak berhasil ⇒ `qty_reworked_ok` naik, stok FG dilepas dari karantina, dan
  **sisa bisa kirim ke buyer naik** sebesar qty permak. Qty melebihi sisa reject ditolak 400 dengan
  pesan yang menjelaskan, tanpa meninggalkan dokumen yatim.
- **BUG 2 — dispatch lanjutan pada surat jalan yang SAMA.** Backend menerima `shipment_id`
  (404 bila tidak ada — diperiksa **sebelum** pagar qty supaya pesannya tidak menyesatkan, 400 bila
  tipe penerima beda, 403 bila bukan milik vendor) dan menambah `dispatch_seq` berikutnya. **LAYAR
  (baru sesi ini):** tombol **"+ Dispatch"** di kolom Aksi tiap surat jalan yang belum 100%, modal
  "Lanjutkan Dispatch — <nomor>" dengan banner penjelas, nomor SJ & pilihan PO **terkunci**, sumber
  penerimaan + sisa bisa kirim dimuat ulang dari backend, tombol kirim berbunyi "Tambah Dispatch".
  Hasil: satu PO = satu surat jalan yang progresnya naik (40 → 70 → 100), bukan tiga nomor terpisah.
- **BUG 3 — aksesoris BOM di form buat PO maklon (LAYAR baru sesi ini).** Panel **read-only**
  "Aksesoris dari BOM Katalog" ikut berubah tiap artikel/qty disunting (debounce 400 ms) lewat
  `POST /api/dewi/maklon/bom-templates/preview-accessories` — **mesin yang sama** dengan yang menulis
  `po_accessories` saat PO disimpan, jadi angka di layar tidak mungkin berbeda dari yang tersimpan.
  Bagian "Aksesoris (Add-on)" diberi label "hanya yang DI LUAR BOM" agar tidak diketik dobel.
- **BUG 4 — vendor CMT bisa mengajukan material PENGGANTI.** Tombol "Buat Permintaan Pengganti" di
  tab PENGGANTI portal CMT + pemilih surat jalan + modal yang meneruskan `request_type` (bukan
  `ADDITIONAL` yang dihardcode).
- **BUG 5 — surat jalan ANAK tidak membawa aksesoris PO.** Detail & daftar sepakat:
  `po_accessories=[]`, `accessories_scope='own'`, `is_child_shipment=true`, `po_accessories_count=0`
  — kiriman pengganti hanya membawa isi kirimannya, jadi form inspeksi vendor tidak lagi memunculkan
  aksesoris yang tak pernah dikirim.

## Bukti
- **Sebelum:** `scripts/_repro_5bug_produksi_maklon.py` (dibuat sesi lalu) — kelima bug kini
  dilaporkan "TIDAK ADA".
- **Sesudah, permanen:** gate baru **`scripts/verify_permak_dispatch_aksesoris.py` (INV-F27)** —
  9 invarian HIJAU, membangun skenarionya sendiri lewat pembangun yang sama dengan INV-F16 (PO 100 =
  90 lolos QC + 10 reject), termasuk **F27-8 yang memeriksa pintunya ADA di layar** (tombol
  "+ Dispatch", panel aksesoris BOM, tombol permintaan pengganti). Terdaftar di `scripts/gate.sh`.
- **Gate penuh:** `bash scripts/gate.sh` → **23 PASS · 1 WARN · 0 FAIL · VERDICT HIJAU** (85 s).
- **Uji layar nyata (testing agent, iterasi 74):** tombol/banner/modal dispatch lanjutan,
  panel aksesoris BOM di modal "Buat PO Maklon", dan alur tombol PENGGANTI di portal vendor CMT
  semuanya terklik dan berperilaku benar; 0 isu kritis, 0 isu UI.
  Berkas uji tambahan `backend/tests/test_inv_f27_bugs.py` (butuh data uji lebih dulu:
  `python3 scripts/verify_fase_e_kapasitas_kirim.py --scenario-only`, kalau tidak ia SKIP).

## Catatan lingkungan
Preview menyajikan **bundel statis** (`node static_server.js`), bukan dev server — setiap perubahan
JSX **wajib** `bash scripts/rebuild_frontend.sh` sebelum diuji di layar (lihat
`memory/PREVIEW_STABLE_MODE.md`). `memory/test_credentials.md` yang sebelumnya kosong sudah diisi
ulang dengan 14 akun yang diverifikasi login HTTP 200.


---

# [2026-08-17 #18] **FASE G DITEGAKKAN** — setelan penomoran tidak lagi berbohong · Dashboard Marketing terbukti SUDAH selesai

## Temuan pertama: satu dari dua permintaan sudah selesai (ROADMAP basi)
Dashboard Marketing (D) ternyata sudah ditutup sesi #16 — diukur ulang:
`scripts/verify_fase_d_dashboard_marketing.py` HIJAU 8 invarian (pintu di sidebar Portal Marketing +
angka dari SSOT siklus + total dihitung backend + lingkup toko per pemakai). Terbukti di layar:
9 toko, target Rp 120jt, omzet Rp 4,4jt, anggaran 61,7%. **Entri ROADMAP-nya** yang salah, bukan
produknya — sudah diperbaiki supaya sesi berikutnya tidak membangun ulang yang sudah jalan.

## Masalah yang diukur (Fase G)
Layar Penomoran Dokumen menampilkan pilihan **Otomatis/Manual** untuk **49** jenis dokumen, tetapi
hanya **2** jalur tulis yang benar-benar memanggil `core.doc_number_policy.issue_number`. Untuk 47
jenis lain: setelan TERSIMPAN, TAMPIL di layar, dan dokumennya tetap bernomor otomatis. Ditambah
Kasbon & Pinjaman berbagi satu field/kunci (satu kebijakan untuk dua jenis dokumen), dan nomor yang
lahir (`KSB-00001`) tidak mengikuti format yang tertulis di layar (`KSB-{YYYY}{MM}-{SEQ:5}`).

## Yang dikerjakan
- **6 jenis dokumen baru lewat satu pintu `issue_number`** (total 8): CMT-RCV · Invoice Maklon
  (manual) · Invoice Piutang (AR) · Pengajuan Kasbon · Pengajuan Pinjaman Karyawan (kunci BARU) —
  di samping SPP, PO Maklon, Roll Kain.
- **Kunci registry baru** `dewi_kasbon_requests.request_number_pinjaman` (override
  `collection`/`field`) ⇒ memindah kebijakan Kasbon tidak menyeret Pinjaman.
- **Kejujuran setelan (inti sesi):** registry menandai `policy_enforced`; layar admin
  menyembunyikan pilihan mode untuk jenis yang belum ditegakkan (badge kuning **"Otomatis saja"** +
  alasannya), dan **API `PUT /api/admin/doc-numbering` juga MENOLAK** perubahan mode untuk jenis itu
  — menyembunyikan di layar saja tidak cukup karena API bisa dipanggil langsung. Format tetap boleh
  diubah untuk semua jenis. Hasil: **8 bisa diatur · 41 "Otomatis saja"**.
- **Komponen bersama** `components/erp/docnum/DocNumberField.jsx` + hook `useDocNumberPolicy` +
  helper `docNumberPayload`. Mode OTOMATIS ⇒ kolom terkunci menampilkan NOMOR BERIKUTNYA; mode
  MANUAL ⇒ kolom wajib + pola & contoh ditulis. Dipasang di form Ajukan Kasbon/Pinjaman.

## Bukti
- Gate baru **INV-F25** `scripts/verify_fase_g2_penomoran_ditegakkan.py` → HIJAU 7 invarian
  (G1 statik "yang mengaku ditegakkan benar-benar lewat issue_number" · G2 manual · G3 otomatis +
  nomor mengikuti format owner · G4 jenis belum ditegakkan menolak mode tetapi format boleh ·
  G5 Kasbon≠Pinjaman · G6 nomor kembar 409 · G7 layar memakai kebijakan), terpasang di `gate.sh`.
- `bash scripts/gate.sh` → **43/43 PASS · 0 FAIL · 0 SKIP · HIJAU**.

## Sisa
41 jenis dokumen masih "Otomatis saja". Pola menyambungkannya sudah terbukti: tandai
`policy_enforced` → ganti `gen_prefixed_number` jadi `issue_number(..., requested=...)` → pasang
`<DocNumberField>` di form → daftarkan jalur tulisnya di `WRITE_PATHS` gate INV-F25.

# [2026-08-17 #17] **FASE H-6b — FASE H DITUTUP 100%**: arus keluar Cutting punya DOKUMEN, stok tetap turun SEKALI

## Masalah yang diukur lebih dulu
Portal Cutting SUDAH benar memotong stok kain (`stock_service.issue` ⇒ `rahaza_material_stock` +
`rahaza_stock_ledger`) dan mengurangi sisa gulungan FIFO (`fabric_roll_engine.consume_rolls` +
`wh_fabric_roll_movements`). Yang TIDAK pernah ada: **satu pun dokumen `rahaza_material_issues`**
dan **satu pun baris kartu stok `rahaza_material_movements`** untuk arus keluar itu. Akibatnya layar
"Pengeluaran Material" hanya memuat 2 dari 3 pintu keluar gudang (MI manual/job internal + Kirim
Material CMT), sehingga pertanyaan *"material apa saja yang keluar hari ini?"* dijawab SALAH secara
sistematis dan kain yang dipotong tidak muncul di kartu stok.

## Yang dikerjakan
- **`backend/core/cutting_material_issue.py` (BARU)** — satu pintu penerbitan dokumen arus keluar
  Cutting. **TIDAK memotong stok**: ia hanya membuat DOKUMEN atas mutasi yang sudah terjadi di
  `routes/cutting.py` (`stock_moved_by='cutting'` tertulis di datanya). Memakai jalur approve MI di
  sini akan membuat kain berkurang DUA KALI untuk satu kali potong.
- **TIDAK ADA JURNAL** (`gl_posted=False` + `gl_skip_reason`). Cutting bukan pemakaian: nilai kain
  BERPINDAH menjadi nilai potongan (HPP potongan diisi saat order `complete`) dan potongan masih
  tercatat sebagai persediaan. `POST /material-issues/{id}/post-to-gl` kini **MENOLAK** dokumen
  cutting — tanpa penjaga itu satu klik admin cukup melahirkan **beban hantu** di buku besar.
- **Satu dokumen per laporan progres**, status langsung `issued`. Idempoten dua lapis: pencarian
  `cutting_progress_id` + **indeks unik sparse** pada koleksi MI.
- **Endpoint baru** `GET /api/cutting/issue-docs/missing` (progres yang kainnya sudah keluar tetapi
  belum berdokumen — sekalian MEMULIHKAN tautan yang hilang, supaya angkanya tidak menuduh salah) dan
  `POST /api/cutting/issue-docs/backfill` (retroaktif, idempoten, **tidak memotong stok lagi**).
- **Daftar jadi benar-benar satu daftar**: `GET /api/rahaza/material-issues?source=cutting|
  vendor_shipment|job|work_order|manual` (sumber asing → **400**, bukan diam-diam semua) + setiap
  baris membawa `source_key`/`source_label`/`first_unit`/`first_material_code`, plus rekap
  `GET /api/rahaza/material-issues/sources` (READ-ONLY). Klasifikasi sumber dibaca dari **BUKTI**
  (`ref_type`/tautan), bukan hanya field `source`, supaya dokumen LAMA ikut tergolong benar.
  **Route literal `/material-issues/sources` dideklarasikan SEBELUM `/{mid}`** (pelajaran sesi #16).
- **Layar** (bundel statis sudah di-rebuild): chip penyaring sumber berisi angka · kolom
  **Sumber** + **Acuan** · Total Qty bersatuan · dokumen Cutting TANPA tombol Approve/Hapus (diganti
  pintasan ke Portal Cutting) · panel detail **"Dari Portal Cutting"** (style · potongan jadi ·
  buangan · kode potongan · gulungan `−qty (sisa n)` · badge "diterbitkan retroaktif") + alasan
  **"Tidak dijurnal"**. Portal Cutting: kolom **"Dokumen keluar"** di Riwayat Progres + panel kuning
  **"N progres belum punya dokumen"** dengan tombol **"Terbitkan dokumen"**.
- **Rapi-rapi lint sesi #16: 13 → 0** pada `backend/routes/wms_delivery_notes.py` +
  `scripts/verify_fase_h7_h8_surat_jalan.py` (`typing.List` dibuang · `_in_range` ditulis ulang lebih
  terbaca · BLE001 diberi noqa **beserta alasan** · gate `chmod +x`). INV-F23 tetap HIJAU 8/8.

## Tiga cacat lain yang ikut ketemu karena SELURUH 42 gate dijalankan
1. **INV-F13 MENUDUH SALAH (penjaga, bukan produk).** `_count_columns()` mengambil `<thead>`
   PERTAMA di berkas; sejak H-5/H-7 menambah tabel baru DI ATAS tabel utama
   (`WMSFabricRollsModule`, `WMSDeliveryNotesModule`), penjaga mengukur tabel yang SALAH dan
   melaporkan "1 kolom" untuk tabel ber-11 kolom. **Dipresisikan** (dianc*ar* ke
   `data-testid="<prefix>-table"`), bukan dilonggarkan ⇒ 84/84 LULUS.
2. **INV-18 & INV-14 MERAH di container SEGAR (data demo, bukan kode).** Seeder demo maklon membuat
   dokumen dispatch buyer langsung di DB tanpa menambah stok FG; buku kuantitas job item ditulis
   inkremental (`$inc`) sehingga seed/hapus berulang meninggalkan angka menggantung. Remedinya sudah
   ada (`repair_selisih_ssot.py --apply --topup-fg`) tetapi hanya tertulis di HANDOFF dan dijalankan
   MANUAL tiap sesi → sekarang **dipasang di `scripts/bootstrap.sh`** (idempoten).
   Ditambah `scripts/seed_cmt_receipt_demo.py` supaya `cmt_receipts` tidak kosong (INV-F23 S8 selalu
   MERAH PALSU di container segar).
3. **KEBOCORAN NYATA AKIBAT H-6b.** Gate INV-F22 membuat order+progres cutting lalu
   membersihkannya — ia dibuat SEBELUM H-6b, jadi dokumen arus keluar yang kini lahir dari progres
   itu **TERTINGGAL YATIM** dan menumpuk di layar Gudang tiap kali gate jalan. Diperbaiki di tiga
   tempat: cleanup INV-F22, sweeper `cleanup_uji_h5_h6.py` (menyapu berdasarkan BUKTI ke-yatiman,
   karena materialnya sudah terhapus sehingga tak bisa dicari lewat awalan kode), dan **invarian
   baru C14**.
   > **Pelajaran umum:** menambahkan dokumen turunan pada sebuah alur = MEWAJIBKAN semua alat uji
   > alur itu ikut membersihkannya. Cari dulu siapa saja yang menghapus dokumen induknya.

## Temuan agen uji yang ikut ditutup
`GET /api/rahaza/materials/{id}` membalas **405** (path ada untuk PUT/DELETE, GET tidak) — tidak ada
pemanggil FE/mobile, jadi bukan fitur mati, hanya API tak simetris dengan `GET /material-issues/{mid}`.
Ditambahkan (+ ringkasan stok per lokasi) dan **diletakkan di baris PALING BAWAH berkas** karena
`/materials/reorder-alerts` & `/materials/uom-options` adalah route LITERAL di berkas yang sama:
kalau `{mid}` mendahuluinya, dropdown satuan di SELURUH layar mati diam-diam. Dijaga C12 (statik) +
C13 (runtime).

## Bukti
- `python3 test_core_h6b_cutting_mi.py` → **77/77 LULUS** (POC inti, self-cleaning, `--keep` untuk
  menyisakan data periksa di layar).
- Gate baru **INV-F24** `scripts/verify_fase_h6b_cutting_issue.py` → **HIJAU 14 invarian**
  (C1 kejujuran daftar "tanpa dokumen" · C2 dokumen cocok · C3 stok/ledger/kartu/gulungan bergerak
  SEKALI · C4 tanpa jurnal + post-to-gl ditolak · C5 tak bisa dihapus/di-approve · C6 penyaring
  jujur · C7 rekap READ-ONLY · C8 idempoten · C9 layar memakai fitur · C10..C13 urutan route ·
  C14 tanpa dokumen yatim), terpasang di `scripts/gate.sh` (+ daftar `skip_gate`).
- `bash scripts/gate.sh` → **42/42 PASS · 0 FAIL · 0 SKIP · VERDICT HIJAU**.
- Agen uji: 10 user story (A–J) terverifikasi lewat API + LAYAR, 0 bug UI.

# [2026-08-16 #16] **FASE H-7 & H-8** — satu daftar surat jalan lintas sumber · empat pintu lama tak lagi kosong

## H-7 — surat jalan: satu daftar, tiga sumber (read-only)
Terukur sebelum perbaikan: layar "Surat Jalan" HANYA membaca `wh_delivery_notes` (2 dokumen, keduanya
DEMO), sementara surat jalan operasional hidup di `vendor_shipments` (4) dan `buyer_shipment_items`
(8 pengiriman). Satu pertanyaan — "surat jalan apa saja yang keluar?" — butuh 3 layar di 2 portal.
- `GET /api/wms/delivery-notes/sources?source=&q=&date_from=&date_to=` menormalkan ketiga koleksi
  jadi satu daftar. **Dispatch buyer dipecah per `dispatch_seq`** karena itulah dokumen yang dibawa
  kurir; menggabungnya per PO akan menyembunyikan pengiriman ke-2 dan ke-3.
- Tiap baris mencetak **PDF resmi dokumen aslinya** (gudang `/{id}/pdf`, vendor
  `type=vendor-shipment`, buyer `type=buyer-shipment-dispatch` + kumulatif `type=buyer-shipment`).
  Tidak ada nomor baru, tidak ada generator PDF kedua. `wh_delivery_notes` TIDAK dipensiunkan —
  dia satu-satunya tempat surat jalan internal/manual dibuat.
- `GET /api/wms/delivery-notes/sources/recap-pdf` — rekap landscape (`_pdf_data_table`), 0 tumpang
  tindih, tabel 100% lebar konten, mendukung `?token=` untuk unduhan lewat `window.open`.
- **Cacat lama yang ikut ketemu:** `_pdf_data_table` memakai `leading` 9,5 pt untuk font 7,5 pt
  (kotak glyph ±10,3 pt) ⇒ **setiap sel yang teksnya melipat tumpang tindih ±0,8 pt di SEMUA
  dokumen**. Dinaikkan ke 10,8 pt; INV-F17 tetap HIJAU sesudahnya.
- Layar: tab pertama **"Semua Sumber"** + chip filter sumber berisi angka, rentang tanggal, cari,
  CSV, **Cetak Rekap**, dan per baris **PDF · PDF kumulatif · Buka sumber**. Tab lama & alur
  buat/issue/receive surat jalan gudang tetap utuh.

## H-8 — empat pintu lama diarahkan ke pekerjaan yang benar
`do-management` → `prod-shipments-vendor`; `prod-cmt-packing` & `maklon-packing` → `da-cmt-receive`
(packing CMT = MENERIMA hasil jadi + QC + posting FG, koleksi `cmt_receipts`); `cmt-progress` →
`cmt-monitor`. Semuanya dulu menunjuk `wms-cmt-dispatches` yang koleksinya 0 dokumen.

## Bukti
Gate baru **INV-F23** `scripts/verify_fase_h7_h8_surat_jalan.py` → HIJAU 8 invarian (kelengkapan
2+4+8=14 · PDF tiap sumber 200 · filter · dispatch per pengiriman · rekap rapi · agregasi read-only ·
alias tak berujung kosong), terpasang di `gate.sh`. Agen uji: backend 6/6 grup, layar 7/7 grup, 0 bug.
INV-F17 · INV-F19 · INV-F22 · INV-NAV-01 · INV-CONTRACT-01 tetap hijau.

# [2026-08-16 #15] **FASE H-5 & H-6** — gulungan kain LAHIR saat diterima, MATI saat dipotong

Melanjutkan pekerjaan yang berhenti di tengah. `python3 -m pyflakes backend/routes/warehouse.py`
melaporkan **4 undefined name** (`fabric_rolls` ×2, `fabric_roll_engine`, `rolls_created`): jalur
penerbitan gulungan sudah ditulis tetapi importnya belum ada. Backend tetap bisa start, jadi
kerusakannya baru muncul saat orang menekan *Confirm Received* pada penerimaan kain → HTTP 500.

## H-5 — gulungan lahir dari penerimaan, nomornya tidak diketik
- `routes/warehouse.py`: import `core.fabric_roll_engine`, inisialisasi `rolls_created`/`rolls_pending`,
  dan rincian roll SEMUA baris **divalidasi sebelum satu pun stok ditulis** — tidak ada GR setengah
  jadi (stok naik, gulungan gagal terbit). GR menyimpan `rolls_created`, `rolls_pending`,
  `rolls_summary`, dan per baris `roll_ids` + `roll_numbers`.
- `create_receiving` kini **menyimpan** `item.rolls`. Sebelumnya rincian yang sudah diisi layar
  dibuang senyap oleh backend, jadi sekeras apa pun layar dibuat, datanya tidak pernah sampai.
- `routes/wms_fabric_rolls.py`: `roll_no` **tidak lagi diketik** → `fabric_roll_engine.issue_roll_no()`
  lewat SSOT penomoran (`wh_fabric_rolls.roll_no`, bawaan `RL-{YYYY}{MM}-{SEQ:4}`, mode `auto`).
  Nomor ketikan DITOLAK **sambil menyebut nomor yang akan dipakai** — pemakai yang mengetik nomor
  lalu melihat nomor lain muncul akan menyimpulkan sistemnya rusak.
- Endpoint baru: `GET /api/wms/fabric-rolls/number-policy`, `GET …/missing-from-receipts`,
  `POST …/issue-from-receipt` (terbitkan gulungan untuk penerimaan yang sudah lewat; penerbitan
  kedua **409** supaya tidak ada dua gulungan untuk kain fisik yang sama).

## H-6 — Cutting wajib menunjuk gulungan (FIFO, satu pintu)
- `routes/cutting.py`: rencana pemakaian gulungan dihitung **sebelum** stok dipotong. Progres tanpa
  gulungan → 400 yang menyebutkan gulungan bersisa; sisa terpilih kurang → 400 dengan angkanya;
  kain yang belum punya gulungan → 400 **beserta jalan keluarnya**. Pengurangan roll manual (blok
  lama, hanya jalan kalau `roll_id` dikirim) diganti `allocate()` + `consume_rolls()`.
- `GET /api/cutting/rolls` kini objek `{items, total, roll_required, total_remaining, uom}`.
- Progres menyimpan `roll_consumption`/`roll_numbers` ⇒ pertanyaan buyer "gulungan mana yang dipakai
  untuk order ini" akhirnya bisa dijawab dari sistem.

## Layar (bundel statis di-rebuild)
- **Penerimaan Barang** — editor *Rincian Gulungan* per baris kain: tombol **Bagi rata**, indikator
  hijau/merah beserta selisih, nomor roll "otomatis"; bisa diisi saat membuat GR maupun saat
  konfirmasi; setelah konfirmasi muncul daftar nomor gulungan yang terbit + banner kuning untuk kain
  yang masuk stok tanpa gulungan.
- **Roll Kain** — input nomor roll dihapus (kotak "otomatis" + pola), tab **"Penerimaan tanpa roll"**
  (badge jumlah) + tombol **Terbitkan Roll**, detail gulungan menampilkan asal penerimaannya.
- **Order Cutting** — pemilih gulungan **WAJIB**, tombol *Catat* mati sebelum gulungan dipilih,
  pratinjau alokasi FIFO, kolom **"Gulungan dipakai"** di riwayat progres.

## Bukti
`test_core_h5_h6.py` **61/61** (2× jalan) · gate baru **INV-F22**
(`scripts/verify_fase_h5_h6_roll.py`) **HIJAU 15 invarian**, self-cleaning, sudah di `gate.sh` ·
agen uji: backend 52/52, 0 bug · gate lama tetap hijau (`verify_data_integrity` PASS 24,
`verify_concurrency` FAIL 0, INV-F21, INV-F19, HEALTH-01, INV-NAV-01, INV-CONTRACT-01,
INV-DEADCODE-01).

## Alat bantu
`scripts/cleanup_uji_h5_h6.py` — menyapu data pembuktian (`POC-*`, `TEST-H5*`, `TEST-H6*`, `VFH5-*`)
beserta gulungan, stok, ledger, GR, dan order cutting-nya. Laporan dulu, `--apply` untuk menghapus.
Counter nomor sengaja tidak dikembalikan: nomor gulungan bekas tidak boleh dipakai ulang.

# [2026-08-16 #14] **FASE H-2 · H-3 · H-4/H-9** — Portal Gudang: pintu yang benar-benar hidup

Tiga keluhan pemilik tentang Portal Gudang, ketiganya terbukti dengan angka SEBELUM diperbaiki.

## H-2 — "Pengeluaran Material tidak ada tombol buatnya"
`RahazaMaterialIssueModule.jsx` (488 baris) memang **tidak punya satu pun jalur create**: hanya
lihat / ajukan / setujui. Satu-satunya pembuatan MI dari layar adalah endpoint maklon lama yang
di backend sudah `deprecated=True`. Lebih dalam lagi: gerbang `POST /api/rahaza/material-issues`
memakai `_require_admin` yang hanya meloloskan role `admin/superadmin/owner` ⇒ **admin gudang dan
supervisor produksi — dua orang yang benar-benar mengerjakan pekerjaan ini — mendapat 403.**

- `_require_mi_editor` (baru, `rahaza_inventory_shared.py`): izin `inv.material_issue.manage` /
  `inventory.manage` / `warehouse.manage`, legacy role `admin_gudang` + `supervisor_produksi`
  (+ ppic/manager/warehouse_manager). Dipakai POST/PUT/submit. **Approve tetap terpisah**
  (`_require_mi_approver`) — pembuat permintaan tidak boleh sekaligus memotong stok.
- Layar: tombol **Buat MI** + dua jalur yang sengaja dibedakan — *dari job produksi* (kebutuhan
  DIHITUNG dari BOM job, tidak diketik ⇒ mustahil beda dengan rencana produksi) dan *manual dari
  master* (material wajib dipilih dari master, F14; barang jadi tidak ikut).
- Kalau backend memakai kembali MI yang sudah ada untuk job yang sama, layar **mengatakannya**
  ("MI untuk job ini SUDAH ADA: <no>"). Dulu dokumen lama dibuka tanpa pesan dan pemakai yakin
  baru membuat draft baru.
- Supervisor produksi tidak punya akses Portal Gudang, jadi pintu MI ditambahkan juga di
  **Portal Produksi → Produksi Internal** — tanpa itu kewenangan barunya tidak bisa dipakai.

## H-3 — "Buat Barcode belum ada menunya"
Endpoint label bahan & barang jadi sudah ada berbulan-bulan dengan **0 pemanggil UI**. Tiga cacat
yang baru kelihatan begitu layarnya dibuat:
1. **Label FG SELALU 404.** Jalur FG hanya membaca `rahaza_fg_matrix` yang **kosong (0 dokumen)**,
   sementara 332 barang jadi nyata hidup di `rahaza_materials` (`type='fg'`, lahir dari varian
   master). Sekarang pencarian FG jatuh ke SSOT itu.
2. **Batch label bahan mencetak di luar kertas.** `COLS = 3` × 90 mm = 270 mm pada A4 selebar
   210 mm ⇒ `MARGIN_X` negatif, kolom ketiga hilang di setiap baris. Kolom/baris sekarang
   DIHITUNG dari ukuran halaman (`core/label_render.grid_geometry`).
3. **Semua label bahan mencetak satuan "pcs"** — satuan dibaca dari `uom`, field yang tidak ada di
   `rahaza_materials` (namanya `unit`). Kain ber-satuan kg pun tertulis pcs.

Baru: `backend/core/label_render.py` (SSOT gambar label; label bahan dulu digambar dua kali),
`backend/routes/wms_barcode.py`, layar `wh-barcode` (dua tab: Bahan & Aksesoris · Barang Jadi).
Kemampuan yang memang diminta pemilik: **jumlah lembar per item** (dulu 1 label/item), **otomatis
dari PO produksi** (qty label = qty PO, tidak diketik ulang), 1 PDF gabungan, **riwayat cetak**
(`wh_barcode_print_jobs` — menjawab "kenapa ada dua label berkode sama di gudang").
Dua pagar: kode di luar master **ditolak** (barcode harus bisa discan jadi item nyata) dan batas
500 lembar/cetak (200 per baris).

## H-4/H-9 — dua menu mati dilepas, IA Gudang dirapikan
- `wh-scan` (Scan Gudang): antrean `wh_pending_movements` = **0 dokumen** dan endpoint pengisinya
  **tanpa satu pun pemanggil** di repo ⇒ layar permanen kosong. Scan tetap hidup melekat pada
  prosesnya (Penerimaan, Penyimpanan, Opname, Pengeluaran Material).
- `wms-cmt-dispatches` (Kirim CMT): `wh_cmt_dispatches` = **0 dokumen**; pekerjaan nyatanya di
  Portal Produksi (`vendor_shipments`) yang sejak H-1 juga menerbitkan MI + memotong stok.
- moduleId keduanya **TIDAK dihapus** dari registry ⇒ deep-link/bookmark lama tetap hidup.
- Section Gudang: Inventori & Stok · Inbound (+ **Roll Kain** dipindah ke sini) · Outbound ·
  Alat & Aksesoris (+ **Buat Barcode**).

## Regresi yang ditemukan penguji UI dan ditutup di sesi yang sama
Begitu satu modul punya pintu di DUA portal, `findPortalForModule()` di `App.js` mengembalikan
portal **pertama** menurut urutan deklarasi ⇒ `?module=wh-material-issue` bagi admin gudang
mendarat di Portal Produksi yang tidak ia punyai, lalu dibuang ke "Pilih Portal" **tanpa satu pun
pesan**. Ternyata sudah ada **14 modul lintas-portal** yang menanggung risiko ini jauh sebelum
H-2. Sekarang semua portal pemilik dikumpulkan lalu disaring dengan `canAccessPortal` (dan portal
yang sedang dipakai diutamakan). Dijaga invarian H2-6.

**Gate baru INV-F19** (`scripts/verify_fase_h_gudang.py`) — 16 invarian: kewenangan buat MI dua
peran · pembuat bisa mengajukan · jumlah lembar dihormati + tercatat di riwayat · label FG dari
SSOT · kode karangan ditolak · batas lembar ditegakkan · qty label = qty PO · geometri label tidak
pernah keluar halaman · pintu mati lepas dari sidebar tapi deep-link hidup · modul lintas-portal
diselesaikan lewat hak akses. `bash scripts/gate.sh` = **VERDICT HIJAU** (41 gate).
Uji UI (iteration_67): 11/12 skenario lulus di percobaan pertama, 1 regresi deep-link di atas
sudah diperbaiki + diberi pagar. Data uji dibersihkan (MI & job cetak = kembali ke keadaan awal).

---

# [2026-08-15 #13] **FASE E · F1/F2 · H-1** — satu rumus sisa kirim · PDF tidak tumpang tindih · kirim material memotong stok

## Akar semua keluhan dispatch: `qty_actual` SUDAH netto lolos QC
`dewi_cmt_packing.py` membuktikannya: `arrived = qty_actual + reject_qty`. Layar lama
menghitung `qty_actual − reject_qty` ⇒ **memotong reject dua kali** ("chip 90 kok jadi 80").
Backend justru benar; layarnya yang salah. Ditambah layar tidak mengurangi qty yang sudah
dikirim ⇒ form mem-prefill angka yang PASTI ditolak.

Ada **tiga** rumus untuk satu pertanyaan. Sekarang satu — `core/dispatch_capacity.py`:

    sisa bisa kirim = lolos QC + hasil permak − sudah dikirim

`sudah dikirim` per po_item melintasi SEMUA surat jalan buyer (bukan hanya receipt terpilih).
Dipakai bersama oleh layar, endpoint `/api/buyer-dispatch-capacity`, pagar
`POST /api/buyer-shipments`, dan tab Kekurangan Kirim.

## Reject yang diperbaiki akhirnya bisa dikirim
`apply_rework_outcome()` dulu hanya menaikkan stok FG + buku kuantitas job, tidak pernah
menyentuh `cmt_receipt_lines` yang justru dibaca pagar kirim ⇒ hasil permak MUSTAHIL dikirim.
Sekarang menambah **field baru** `qty_reworked_ok` — bukan menaikkan `qty_actual`/menurunkan
`reject_qty`, karena angka itu hasil inspeksi saat barang datang; mengubahnya retroaktif akan
menggeser laporan variance, AP vendor (dibayar per qty lolos), dan gate INV-14 diam-diam.
`retur_ke_cmt` dikecualikan (barangnya masuk lagi lewat penerimaan CMT baru).

## Cacat BARU yang ditemukan: SURAT JALAN YATIM
`POST /api/buyer-shipments` menulis header surat jalan SEBELUM pagar qty ⇒ setiap Simpan
yang ditolak meninggalkan dokumen "0 / 0 pcs" status Pending, nomor ikut terpakai, dan
pemakai menyangka pengirimannya "sudah pernah dilakukan". Pagar dipindah ke atas + migrasi
`2026_08_15_hapus_surat_jalan_buyer_yatim.py` (dry-run default) membersihkan 2 dokumen.
Nomor tidak didaur ulang. Dijaga invarian E-5.

## PDF: sebabnya terukur, bukan selera
Baris `SUBTOTAL {po}` ditulis ke kolom 'Color' selebar **44 pt** memakai `Table()` mentah
berisi STRING (tanpa word-wrap) ⇒ meluber menimpa kolom angka. Lebar kolom hardcode
**569 pt** vs lebar konten A4 landscape **773,8 pt** ⇒ terisi 73%. Helper malah memakai
`avail = 786` (12 pt MELIMPAH keluar halaman). Baris TOTAL memakai indeks negatif sehingga
labelnya bisa mendarat di kolom salah begitu ada kolom disembunyikan.
Semua diperbaiki; subtotal per PO dibuang dari dokumen kumulatif (kolom No. PO tetap ada).
Terukur: tumpang tindih **0**, tabel mengisi **100%** lebar konten, **0** teks keluar margin.

## Kirim material ke CMT akhirnya memotong stok (H-1)
`POST /api/vendor-shipments` dulu hanya menulis surat jalan + item **GARMEN** — bukan
material. NOL mutasi stok, NOL dokumen pengeluaran, NOL jurnal ⇒ kain & aksesoris keluar
gudang tanpa jejak. Sekarang (PO **INTERNAL**): MI terbit otomatis dari BOM, lokasi dipilih
sistem, stok berkurang, jurnal terposting, tautan dua arah tersimpan.
Inti `approve_mi` DIEKSTRAK ke `core/material_issue_engine.issue_material_issue()` supaya
"mengeluarkan material" punya SATU definisi. Stok kurang ⇒ surat jalan DITOLAK + dirollback
(0 dokumen tertinggal, 0 stok terpotong sebagian). **MAKLON dikecualikan** — materialnya
milik klien; memotong stok DA akan menghilangkan kain milik DA (invarian H1-6).
Ditambah `POST /api/vendor-shipments/material-preview` + panel di form supaya kekurangan
stok terlihat SEBELUM Simpan.

## Bukti
`bash scripts/gate.sh` **HIJAU** 40 gate (baru INV-F16 · INV-F17 · INV-F18) ·
E 11/11 · F 5/5 · H-1 6/6 · testing_agent iterasi 66: backend 100%, 0 bug ·
**dibuktikan MERAH lewat sabotase** dua kali (mematikan `qty_reworked_ok` ⇒ "sisa 0 pcs";
mematikan penerbitan MI ⇒ "stok turun 0").

# [2026-08-14 #12c] **FASE C / F9** — Pencairan marketplace: INPUT MANUAL (blokir BD-2 dihapus, bukan dihindari)

Aturan proyek melarang F9 dimulai tanpa contoh berkas asli: *"pemetaan kolom uang
tidak boleh ditebak"*. Keputusan pemilik: **input manual dulu** — dan itu MENGHAPUS
blokirnya, karena kalau staf mengisi field yang namanya jelas, tidak ada kolom yang
perlu ditebak siapa pun.

## Tiga aturan yang membuat angkanya bisa dipercaya
1. **`net_payout` diisi STAF dari mutasi bank**, bukan dihitung server. Server
   menghitung nilai *yang seharusnya* lalu menampilkan **SELISIH**-nya. Kalau server
   yang menghitung net, setiap potongan yang belum dikenal HILANG diam-diam — angkanya
   "cocok" karena kita sendiri yang membuatnya cocok. Selisih adalah satu-satunya
   petunjuk bahwa ada biaya yang belum tercatat.
2. **Selisih ≠ 0 ⇒ tidak boleh jadi jurnal.** Jurnal dari angka tak seimbang mustahil
   seimbang. Staf harus MENAMAI selisihnya di `other_deductions`/`adjustments`.
3. **Jurnalnya DRAFT**, dan baris cerminnya (`rahaza_journal_lines`) **tidak dibuat**
   sampai disetujui — kalau dibuat, angkanya sudah muncul di neraca saldo DAN akan
   tercatat DUA KALI saat `POST /journals/{id}/post` memanggil `_mirror_lines()`.

## Dua cacat yang ditemukan saat mengerjakannya
* **Rekonsiliasi sempat BOHONG:** memakai `total_amount` (tidak ada) + menyaring
  `order_date` sebagai string (aslinya `datetime`) ⇒ "559 pesanan, omzet Rp 0". Nol di
  sebelah 559 membuat seluruh selisih terlihat seperti kesalahan platform. Kini tiga
  definisi omzet dilaporkan apa adanya beserta labelnya.
* **Dedupe sempat tidak bekerja:** kunci memuat `platform`, padahal
  `_scope.stamp_account()` menimpanya ⇒ nilai yang dicari ≠ yang tersimpan, dan nomor
  pencairan sama bisa masuk dua kali (200 dua-duanya). Kunci diperbaiki ke
  `(account_id, settlement_id)` + **index unik** sebagai penjaga terakhir.
* **Bonus (gate INV-F6RBAC):** `/api/marketing/tasks-stats` menghitung SELURUH tugas ⇒
  staf tanpa toko membaca angka 9 toko. Endpoint daftar sudah menyaring, ringkasannya
  tidak — dan ringkasan itulah yang dibaca lebih dulu. Ditutup.

## Bukti
`coa-map` missing=[] · selisih terdeteksi · jurnal ditolak saat selisih · jurnal DRAFT
**seimbang Dr 10.000.000 = Cr 10.000.000** dengan **0 baris cermin** · idempoten ·
dedupe **409** · edit ditolak setelah ada jurnal · approve ⇒ posted + cermin 1× ·
`bash scripts/gate.sh` **HIJAU** · testing_agent iterasi 65: **0 bug kritis, 0 UI bug** ·
data uji dibersihkan (0 settlement, 0 jurnal).

# [2026-08-14 #12b] **FASE B** — 5 layar UANG/STOK ditutup + kelas Tailwind yang dirakit saat berjalan

## 1. Lima layar (dipilih dengan pertanyaan: kalau salah, berapa mahalnya?)

`HRKasbonModule` (antrian persetujuan kasbon ⇒ potongan gaji) · `KasbonStaffModule`
(riwayat kasbon karyawan) · `ReceivingModule` (**pintu masuk seluruh stok**; kolom *qty
ditolak* = dasar klaim ke supplier) · `ProcurementRequestModule` (komitmen belanja) ·
`AccessoriesDashboard` (nilai stok Rp 9,66 juta + item **belum dinilai**).

**Tidak dipilih & dicatat alasannya:** `PutAwayModule` adalah **wizard 3 langkah**, bukan
layar daftar. Memaksakan tabel di situ hanya supaya angka "KARTU-SAJA" turun akan merusak
alurnya — pola tidak boleh dikejar sebagai skor.

## 2. Dua keputusan yang bukan kosmetik

* **Pengurutan Pengadaan dipindah ke SERVER** (`sort_by`/`sort_dir` + daftar putih kolom).
  Layar yang mengurutkan sendiri hanya bisa mengurutkan halaman yang sedang dibuka, jadi
  *"PR mana yang nilainya PALING BESAR?"* dijawab dengan 15 baris pertama — **jawaban yang
  terlihat meyakinkan padahal salah**, lebih berbahaya daripada tidak ada pengurutan.
  Kolom di luar daftar putih jatuh ke `created_at`; mengurutkan dengan nama kolom karangan
  akan menghasilkan urutan acak yang terlihat sah.
* **Item aksesoris yang belum dinilai DIAKUI** (banner + penanda `BELUM`): selama angkanya
  > 0, total nilai stok pasti LEBIH RENDAH dari kenyataan, dan angka itu masuk laporan
  keuangan.

## 3. Cacat baru: kelas Tailwind DIRAKIT saat berjalan

    className={`bg-${color}-500/5 border border-${color}-500/20 …`}

Tailwind menghasilkan CSS dengan MEMBACA TEKS berkas sumber — ia tidak menjalankan
JavaScript. Kelas itu tidak pernah dibuat. Yang membuatnya nyaris mustahil dilihat: kadang
kelasnya KEBETULAN ada karena berkas LAIN memakainya secara harfiah.

**Diukur pada bundel hasil build sebelum perbaikan:** `bg-violet-500/5` ADA;
`bg-teal-500/5`, `border-teal-500/20`, `border-teal-500/25` **TIDAK ADA** ⇒ pada komponen
KPI yang SAMA, kartu "violet" benar dan kartu **"Perlu Diserahkan" (teal) tampil polos**.
Itu persis keluhan pemilik — dan sebabnya bisa dihitung, bukan selera.

Ditutup lewat `lib/tone.js` (nama warna dinamis, **kelas harfiah**) untuk **21 kejadian di
7 berkas**; penjaganya masuk `INV-F15`.

**Bonus (dari lint):** `TabBtn` didefinisikan DI DALAM komponen induk ⇒ React melihat tipe
komponen baru tiap render dan membongkar-pasang subtree: fokus keyboard hilang & state
ter-reset saat pemakai sedang mengetik. Terasa seperti "kadang nge-lag", jadi hampir tidak
pernah dilaporkan sebagai bug.

## 4. Bukti

* `test_core_f13` diperluas 4 → **9 layar** ⇒ **84/84 HIJAU**; ambang KARTU-SAJA
  **diketatkan 74 → 69**
* `test_core_f15` **15/15** (penjaga kelas dinamis ditambahkan)
* `bash scripts/gate.sh` **VERDICT HIJAU**
* `testing_agent_v3` iterasi 64: backend **4/4** · frontend **100%** · tampilan **100%** ·
  regresi **100%** · **0 bug**

# [2026-08-14 #12] **F13 ditutup** + 3 temuan pemilik: form wajib pakai MASTER · kartu punya latar

## 0. Titik berhenti: `gate.sh` RUSAK, bukan sekadar "belum ditambah"

`insert_text` terakhir sesi #11 menyisipkan `fi` **liar** di baris 380 ⇒
`bash -n scripts/gate.sh` = *syntax error near unexpected token `else`*.
Artinya **seluruh gate tidak bisa dijalankan** — bukan "satu gate belum terdaftar".
Diperbaiki dengan aturan yang sama yang melahirkannya: **satu edit per waktu,
`bash -n` setiap kali `gate.sh` disentuh.**

F13 sendiri ternyata **sudah selesai**: `test_core_f13` **39/39 pada jalan pertama**.
Yang hilang cuma entri gate + dokumen. Gate `INV-F13` didaftarkan di bagian **STATIK**
(sengaja bukan blok `AUTH_READY`) karena penjaganya membaca BERKAS layar, bukan HTTP:
kalau ditaruh di blok backend ia akan di-`skip` tiap backend mati — padahal justru saat
itulah regresi layar paling mungkin lolos.

## 1. Temuan pemilik #1 — "launching product masih custom field input"

### Diukur
`marketing_product_launches`: **8/8** dokumen tanpa `model_id`; nama/bahan/model teks
bebas, padahal `rahaza_models` berisi produk DA sungguhan + varian FG + HPP + harga resmi.

### Kenapa mahal (bukan kenyamanan mengetik)
1. **Master stok kotor.** `_auto_create_fg_from_launch()` membuat BARANG JADI dari teks:
   `code = style_code OR model OR product_name.replace(" ","-").upper()[:30]`.
   "Gamis Busui Friendly DA-2026 Series 1" ⇒ FG `GAMIS-BUSUI-FRIENDLY-DA-2026-S`, tanpa
   `model_id`, tanpa varian warna/ukuran, `hpp = 0`, kategori literal `"launch"`.
   Satu produk jadi DUA barang di master ⇒ "stok produk ini berapa?" punya DUA jawaban.
   Semuanya terjadi **tanpa satu pun galat** — hanya sebaris log info.
2. **Harga tak bisa direkonsiliasi** — rencana (ketikan) vs katalog vs master.
3. **Ejaan = identitas** ⇒ laporan per produk/bahan salah DIAM-DIAM.

### Ditutup
* `MasterProductSelect` — SATU pemilih ber-pencarian, membaca
  `GET /api/marketing/catalogs/master-products` (endpoint yang SAMA dengan Katalog dari
  Master) ⇒ dua layar mustahil menampilkan daftar produk berbeda.
* `_resolve_master_model()` — satu-satunya penulis field turunan master; **kiriman browser
  DIABAIKAN** (pelajaran `received_at`/`closed_at`). Dibuktikan runtime: POST membawa
  `"NAMA PALSU KIRIMAN BROWSER"` ⇒ tersimpan `"Celana Jogger Tapered Fit"`. PUT juga tidak
  bisa menimpanya (`MASTER_DERIVED_FIELDS` dibuang sebelum simpan) — kalau dibiarkan, dokumen
  akan terlihat "tertaut master" padahal isinya sudah berbeda: **lebih berbahaya daripada
  teks bebas terang-terangan**.
* `model_id` **WAJIB**; produk tak dikenal/non-aktif ⇒ **400 dengan alasan + jalan keluar**.
* **FG kembar tidak bisa lahir lagi** — penautan memakai varian FG master yang sudah ada;
  0 `insert_one` ke `rahaza_materials`. Dibuktikan: `launched` ⇒ FG **330 → 330**.
* **Warisan diakui, bukan ditebak** — `master_link.unlinked_total` dihitung server; banner
  amber + penanda per baris + peringatan di form Edit. Migrasi membuang **contoh** yang
  melanggar aturan (contoh yang salah MENGAJARKAN pola salah) tetapi **menolak menebak**
  padanan untuk dokumen NYATA: menebak = menautkan ke produk salah tanpa bisa dibedakan
  dari tautan yang benar.

## 2. Temuan pemilik #2 — "verifikasi semua form lainnya"

`scripts/_audit_form_master_refs.py` (582 layar · 10 konsep ber-master).
Jalan pertama **13 temuan**; sesudah triase **4 di antaranya TUDUHAN SALAH** dan
dikecualikan beserta alasannya (kategori BIAYA HR · kategori KPI · model ASET IT ·
form yang MEMBUAT masternya sendiri). Ini disengaja: penjaga yang salah tuduh berhenti
dipercaya, dan penjaga yang tidak dipercaya sama dengan tidak ada penjaga.

Yang benar-benar cacat & diperbaiki: `ProductLaunchModule` · `AIContentGeneratorModule`
(teksnya TAYANG ke pembeli ⇒ bahan karangan = klaim produk yang salah) ·
`CMTComponentRequestModule` · `MaklonAIQuoteModule` (dua mode: dari Katalog Buyer, atau
"artikel baru" yang DITANDAI — melarang teks bebas di penawaran justru membuat staf
memilih artikel yang MIRIP supaya form mau lanjut).

**Dua jebakan yang sempat membuat audit BOHONG:**
* `product_name: e.target.value` cocok dengan pola "diisi dari objek lain" ⇒ audit sempat
  melaporkan **0 temuan padahal semua kotak ketik masih utuh**.
* "ada pemilih di berkas ⇒ temuan gugur" terlalu longgar — satu berkas bisa punya pemilih
  DAN kotak ketik sekaligus, dan itu bentuk yang paling mudah lolos.

## 3. Temuan pemilik #3 — "cards lupa background, ada yang abu-abu"

Ketiganya tidak pernah menjadi galat ⇒ build & lint HIJAU sementara layarnya rusak.

* **23 kelas Tailwind RUSAK** (`bg-foreground/[0.06]0`) — sisa find/replace massal
  (`bg-white/60` → ganti `white/6` jadi `foreground/[0.06]`). Angka nyasar sesudah `]`
  membuat kelasnya tidak dikenal ⇒ **tidak ada CSS sama sekali** ⇒ elemen benar-benar
  tanpa latar. Dipetakan ke padanan sadar-tema **per konteks**; perkecualian disengaja:
  `UniversalScanPortal` memakai panel `bg-zinc-900` yang selalu gelap ⇒ `border-white/10`
  memang jawaban yang benar di sana.
* **56 teks `text-muted-foreground/50|60|70` di atas `bg-muted`** — rasio kontras
  **1.9–2.6** (lantai 3.0) di tema terang MAUPUN gelap. Modifikator dibuang ⇒ ± 4.3 / 4.9.
* **30 cadangan token `getItem('auth_token')`** padahal `auth_token` **tidak pernah
  ditulis** (`setItem` = 0); kunci benar `erp_token`. Cadangan yang mustahil bekerja lebih
  buruk daripada tidak ada cadangan: ia membuat orang berhenti mencurigai token.
* **Bonus:** `PickingListModal` memakai `accountFilter` milik komponen INDUK ⇒
  `ReferenceError` = layar putih begitu modal dibuka. Kini prop — sekaligus membuat daftar
  picking mengikuti toko yang dipilih, bukan diam-diam semua toko.

Audit pengukurnya **MENGHITUNG rasio kontras WCAG**; versi pertamanya memakai ambang
opasitas kasar dan menuduh `text-foreground/80` yang rasionya **8.6**.

## 4. Bukti

* `test_core_f13` **39/39** · sabotase ⇒ 38/39 MERAH
* `test_core_f14_form_pakai_master.py` **34/34** · sabotase ⇒ 33/34 MERAH (audit ikut menangkap)
* `test_core_f15_kartu_terbaca.py` **13/13** · sabotase ⇒ 12/13 MERAH
* `bash scripts/gate.sh` **HIJAU** — 3 gate baru: `INV-F13` · `INV-F14` · `INV-F15`
* Uji LAYAR (Playwright): pemilih master berisi 5 produk; memilih `CLN-0001` mengisi
  kategori/HPP/harga resmi/varian otomatis — **0 page error · 0 console error**

# [2026-08-14 #11b] **F12 SELESAI** — berkas ekspor yang diunggah ke TOKO SALAH tertangkap sebelum tersimpan

## 1. Lubang yang DIUKUR atas 22 jenis data

Penjaga toko yang ada ternyata hanya menempel pada SATU jenis: `marketplace_orders`
(`platform_guard` + `shop_guard`). Sisanya:

| Jenis | Penjaga | Akibat kalau salah pilih toko |
|---|---|---|
| **`marketplace_fulfillment` (Ekspor B/C)** | tidak ada | hanya "3 baris ditolak: belum pernah diimpor" |
| 20 jenis lain (KPI, iklan, konten, komplain, retur, sampel, …) | tidak ada | **MASUK ke toko yang salah tanpa satu pun galat** |

Kalimat "belum pernah diimpor" adalah cacat yang mahal justru karena BENAR: staf
menyimpulkan berkasnya rusak, lalu memilih jenis **"Pesanan Marketplace"** supaya "mau
masuk" ⇒ pesanan **HANTU** tanpa item/omzet/kreator, dan jumlah pesanan bulan itu naik tanpa
ada penjualan.

## 2. Yang dipakai: BUKTI, bukan dugaan

* **`SourceType.identity`** — tanda pengenal GLOBAL satu baris: nomor pesanan platform (7
  jenis), nomor komplain, URL konten. Kepemilikan nomor pesanan diperiksa di **SSOT
  `marketing_orders`**, bukan di koleksi turunan (retur/ulasan isinya tidak lengkap).
* **`NO_IDENTITY_REASON`** — 15 jenis yang isinya MEMANG tanpa penanda toko terdaftar
  **beserta alasannya**. Contoh: ekspor statistik toko Shopee hanya berisi TANGGAL & KANAL —
  setiap toko punya tanggal yang sama, jadi memakainya sebagai tanda pengenal akan **MENUDUH
  SALAH** (pelajaran sesi #10 tentang penjaga yang menuduh). Penjaga `A-1`: jenis baru tanpa
  `identity` **dan** tanpa alasan ⇒ gate MERAH.
* **Ambang** — mayoritas baris (≥ setengah) milik toko lain ⇒ **PENGHALANG** (commit 409 +
  tombol Simpan MATI); minoritas ⇒ **PERINGATAN** yang TETAP boleh disimpan. Peringatan tidak
  boleh mematikan Simpan: berkas gabungan itu ada, dan staf yang sedang MEMPERBAIKI keadaan
  tidak boleh terkunci di luar (dijaga `A-8`).
* **`content_sha256`** — bukti kedua untuk jenis tanpa penanda toko: berkas ber-ISI sama persis
  yang sudah DISIMPAN ke toko lain. Riwayat lama yang belum ber-sidik dihitung **di memori**
  (25 calon: jenis sama + jumlah baris sama) karena **jalur pratinjau tidak boleh menulis apa
  pun** — versi pertama sempat menulis cache sidik ke sesi milik toko LAIN, dan itu ditutup
  sebelum sempat jadi kebiasaan (`A-4`, plus `_shop_evidence` dimasukkan ke daftar penjaga
  "pratinjau tidak menulis" di `test_core_f11`).
* **SATU sumber** — `_shop_evidence()` dipakai `_commit_blockers()` **dan** pratinjau, jadi
  kalimat yang dibaca staf di pratinjau SAMA PERSIS dengan penolakan commit (`A-3`, `B-8`).

## 3. Bukti

* `python3 test_core_f12_sidik_toko.py` → **28/28 PASS**.
* **Dibuktikan MERAH lewat sabotase**: `_shop_evidence` dilumpuhkan ⇒ **7 penjaga gagal**,
  dan `B-7` menerima **HTTP 200** untuk berkas milik toko lain ⇒ lubangnya NYATA.
* `bash scripts/gate.sh` → **30/30 VERDICT HIJAU** (gate baru **INV-F12**).
* **Uji LAYAR** (Playwright, 0 page error · 0 console error): berkas *Shopee Daluna* diunggah
  ke *Shopee Moen* ⇒ panel MERAH *"4 dari 4 nomor pesanan … sudah tercatat pada toko LAIN —
  Shopee Daluna (mis. DEMO-A-1001, DEMO-A-1002, DEMO-A-1003) … Ganti toko tujuan ke 'Shopee
  Daluna' … Kalau diteruskan, angka yang sama akan tercatat di DUA toko"* + panel KUNING
  *"Berkas dengan ISI yang sama persis sudah pernah disimpan ke toko 'Shopee Daluna' pada
  2026-08-14 19:28 oleh admin@garment.com"* + tombol **Simpan MATI**.
* Kebersihan: seluruh jejak uji dibatalkan lewat rollback resmi ⇒ `marketing_orders` **559**,
  0 pesanan uji, 0 sesi uji, 0 periode terkunci.

## 4. KORUPSI SENYAP AKIBAT `search_replace` PARALEL (pelajaran lingkungan)

Dua `search_replace` dijalankan **paralel pada berkas yang SAMA** (`scripts/gate.sh`).
Hasilnya: entri gate F12 **hilang** dan 44 baris terakhir berkas **terduplikasi setengah
jalan** (`ODUK — payslip karyawan"…`). `bash` **menyembunyikan** kerusakan itu karena
`exit $OVERALL` dieksekusi SEBELUM sampahnya terbaca ⇒ gate melaporkan "29/29 HIJAU" padahal
gate ke-30 tidak pernah ada. Ditemukan `bash -n scripts/gate.sh`.

**Aturan yang dipegang sekarang:** satu berkas = satu edit per waktu, dan `bash -n` setiap
kali `scripts/gate.sh` disentuh. (Aturan ini sudah tertulis di HANDOFF sesi #8/#10 — kali ini
akibatnya terdokumentasi beserta gejalanya supaya tidak dianggap teoretis.)

## 5. Catatan jujur

* 3 toko **DEMO** (`SHOPEE-OFFICIAL`, `SHOPEE-RESELLER`, `TIKTOK-STORE`) tidak muncul di
  pemilih toko pada LAYAR karena `MarketingAccountSelect` menyaring `status=active` sementara
  dokumen DEMO tidak punya field itu. Uji layar memakai toko NYATA (Shopee Daluna/Moen), jadi
  tidak menghalangi — tetapi layak dirapikan (kartu kerja sendiri).
* Jenis KPI/iklan tetap **tidak bisa** dibuktikan salah-toko dari ISI berkasnya (alasannya
  tertulis di `NO_IDENTITY_REASON`); yang menjaganya adalah penolakan periode BERIRISAN per
  toko + peringatan "berkas identik pernah masuk toko lain".

# [2026-08-14 #11a] **F11 SELESAI** — pratinjau impor PER BARIS ditutup + gate INV-F11 · cacat "perubahan palsu" ditemukan lewat UJI LAYAR

## 0. Titik berhenti sesi lalu — diukur, bukan ditebak

Titik berhenti yang diberikan user adalah *pembacaan* `scripts/gate.sh` baris 255–345 — artinya
agent sesi lalu sedang mencari tempat mendaftarkan gate berikutnya. Yang ditemukan sesudah
bring-up: **F11 (Fase 4 — pratinjau impor per baris) sudah SELESAI DITULIS** (backend `/plan`,
`/plan.csv`, `/result.csv`, `_plan_rows`, `_commit_blockers`; layar `ImportPlanPanel.jsx` sudah
di-wire ke langkah 5 wizard) dan penjaganya `test_core_f11_pratinjau_impor.py` sudah ada —
**tetapi belum pernah dijalankan, dan gate `INV-F11` belum terdaftar**. Fitur yang tidak dijaga
gate = fitur yang boleh mati diam-diam pada sesi berikutnya.

Bring-up mengulang gejala sesi #8/#9/#10: **pod restart di tengah `yarn build`** ⇒ build selesai
tetapi seed tidak jalan ⇒ DB kosong padahal login admin sukses. `bootstrap.sh --skip-deps`
(idempoten, 54 detik) memulihkannya. Kuota container dikonfirmasi lagi (1 core / 2 GiB) ⇒ bundel
statis dipertahankan.

## 1. CACAT NYATA yang tidak bisa dilihat 45 penjaga backend: **PERUBAHAN PALSU**

Uji LAYAR mode **"Perbarui yang lama"** memajang untuk SETIAP baris:

    Waktu Pesanan Dibuat: 2026-08-05 10:15 → 2026-08-05 10:15

Sebabnya: MongoDB mengembalikan `datetime` **naive** (isinya UTC), berkas yang baru dibaca
menghasilkan `datetime` **ber-zona**; di Python `aware == naive` **selalu** False.

Kenapa ini bukan cacat kosmetik:
* staf belajar **mengabaikan** kolom "yang berubah" — padahal kolom itulah alasan panel ini ada;
* perubahan PALSU memakan kuota tampilan (`_DIFF_MAX = 14`) ⇒ perubahan **NYATA** bisa terdorong
  ke ringkasan "+N field lain" dan tidak terlihat;
* catatan jujur *"tidak ada nilai yang berubah — hanya penanda waktu pembaruan yang ditulis"*
  tidak pernah muncul, karena daftar perubahan tidak pernah kosong.

Ditutup di SATU tempat: **`_norm_dt()`** (menyamakan bentuk waktu) dipakai `_same()` — pembanding
tunggal yang sudah dipakai `_diff_changes()` dan `_plan_fulfillment_row()`.
Kelas cacat yang sama diperiksa di jejak audit: `marketing_change_log` **bersih** (50 perubahan
tercatat, 0 palsu) ⇒ tidak perlu ditambal.

## 2. Penjaga: 36 → 47 (11 penjaga BARU), dan dibuktikan MERAH dua kali

| Penjaga | Yang dijaga | Bukti MERAH |
|---|---|---|
| `B-12` | tidak ada perubahan dengan `before == after` | `_norm_dt` dilumpuhkan ⇒ **4 temuan** |
| `B-13` | baris "diperbarui" tanpa perubahan wajib menjelaskan diri | — |
| `A-9` | panel punya tabel baris + chip 5 akibat (termasuk `ditolak`) + cari + halaman + unduh | — |
| `A-10` | jumlah halaman dari `pagination.total` **server**, bukan panjang satu halaman (cacat "Halaman 1 dari 1" untuk berkas 5.000 baris) | — |
| `E-2b` | CSV rencana benar-benar memuat NILAI lama→baru, bukan hanya judul kolom | — |
| `F-1..F-6` | penyaring & halaman JUJUR: `only=` menyaring baris **dan** `total`, chip TIDAK ikut mengecil, `q=` menyempitkan tepat, `page_size=1` tidak mengecilkan `total`, halaman 2 memuat baris LAIN | — |
| (lama) `B-10` | nilai lama→baru untuk angka yang berubah | `_diff_changes` dipaksa `return [], 0` ⇒ GAGAL |

**Dua penjaga BARU yang sempat MENUDUH SALAH langsung diperbaiki** (pelajaran sesi #10):
`A-9` mencari testid `import-plan-filter-ditolak` padahal testid-nya dibuat dinamis
(`import-plan-filter-${a.key}`), dan `A-10` melarang string `rows.length` yang dipakai sah untuk
keadaan kosong. Penjaga yang menuduh salah dihaluskan **presisinya**, bukan dilonggarkan.

## 3. Gate

`INV-F11` didaftarkan di `scripts/gate.sh` (beserta entri `skip_gate` untuk keadaan backend mati)
dengan catatan lima cara termudah merusak fitur ini tanpa satu pun galat.
`bash scripts/gate.sh` → **29/29 · VERDICT HIJAU** (receipt: `memory/GATE_RECEIPT.md`).

## 4. Bukti LAYAR (Playwright, bundel statis, 0 page error · 0 console error)

* chip «semua 4 · 4 baru · … · 0 ditolak»; tabel 5 kolom; "4 baris menyentuh data · 0 tidak
  diapa-apakan · 0 tidak masuk";
* saring «baru» ⇒ 4 badge `baru`; chip «ditolak» **nonaktif** (hitungan 0); cari `DEMO-A-1001`
  ⇒ **1 baris**; dikosongkan ⇒ 4 baris;
* **angka hidup mengikuti mode**: Lewati ⇒ 4 dilewati (+"sudah ada (duplikat) · status sekarang:
  paid") ⇄ Perbarui ⇒ 4 diperbarui;
* `rencana-impor.csv` benar-benar terunduh (fetch ber-token);
* periode 2026-08 dikunci ⇒ panel merah **"Simpan akan DITOLAK — 1 penghalang"** + tombol
  **Simpan MATI**; periode dibuka kembali sesudah uji;
* commit sungguhan ⇒ "4 baris masuk" + tombol unduh laporan hasil.

**Kebersihan:** semua jejak uji dibatalkan lewat rollback/DELETE resmi ⇒ `marketing_orders`
kembali **559**, 0 pesanan `DEMO-A-*`, 0 sesi impor uji, 0 periode terkunci.

`testing_agent_v3` iterasi 61 **tidak dipakai sebagai bukti**: ia gagal memilih toko di `Select`
Radix lalu menyimpulkan cerita B–E "berfungsi" dari MEMBACA KODE. Semua cerita diverifikasi ulang
oleh main agent lewat Playwright.

## 5. YANG TIDAK DIKERJAKAN (jujur)

* **Salah toko SEPLATFORM belum terdeteksi**: berkas Shopee toko A diunggah ke Shopee toko B ⇒
  platform cocok, penjaga yang ada TIDAK menangkapnya, omzet masuk ke toko yang salah tanpa galat.
  Ini jadi Fase 2 sesi ini.
* F9 Settlement tetap belum dimulai (berkas Pencairan ASLI owner belum ada).
* Label "pemetaan Ekspor B/C belum diverifikasi" tetap dipasang.

# [2026-08-14 #10a] **F6 SELESAI** — lingkup toko per PEMAKAI ditutup sampai ke kartu ringkasan, jejak menjawab "kenapa"

## 0. Titik berhenti sesi lalu — diukur, bukan ditebak

`/app` datang sebagai template kosong ⇒ repo diklon ulang + `rsync` (env platform dipertahankan) +
`scripts/bootstrap.sh` (93 detik, 6 akun login HTTP 200, bundel statis 200). Lalu `scripts/gate.sh`
melaporkan **MERAH pada INV-F6RBAC** — padahal sesi #9 mengklaim 27/27 HIJAU.

**Penyebabnya bukan kebocoran, melainkan PENJAGA yang menuduh salah:** guard `B-*` menyatakan
"staf = admin ⇒ bocor". Di environment segar, SELURUH sesi kreator demo hanya ada di SATU toko —
toko yang justru di-assign gate ke staf uji. Dua angka yang sama itu **sah**.

Penjaganya diperkuat, bukan dilonggarkan: ditambahkan **pas B0 "staf tanpa toko"** — keadaan yang
tidak bisa ditafsir dua arti (nol toko ⇒ nol angka). Sama-besar hanya diterima bila pas B0
membuktikan endpoint itu MEMANG menyaring. Dibuktikan MERAH lewat sabotase (`scope_filter` dilepas
dari peringkat KOL ⇒ 5 temuan), lalu dipulihkan.

## 1. CACAT NYATA yang ditemukan lewat UJI LAYAR (bukan oleh 50 tes backend sesi lalu)

Layar **Laporan Marketing** dibuka sebagai `staffmkt@dewiaditya.id` (staf TANPA toko):

    Unified Orders 559 · Revenue Rp 57,6 jt · Account Health 9 akun · Discount 10 · Launch 8 · Konten 15

Kartu "Marketing Overview" memanggil **enam ringkasan** yang tidak pernah masuk daftar penjaga F6,
dan **lima di antaranya membocorkan angka sembilan toko**. Sweep otomatis atas SELURUH `@router.get`
marketing (109 endpoint) menemukan **47 endpoint** yang menjawab identik untuk staf-tanpa-toko dan
admin. **24 endpoint DATA ditambal**; 19 sisanya endpoint acuan/enum/konfigurasi yang SAH sama dan
sekarang terdaftar **beserta alasannya** (`SCOPE_EXEMPT`).

| Berkas | Yang ditutup |
|---|---|
| `routes/marketing_orders_routes.py` | `/orders/summary` (UANG: omzet 9 toko), `/orders/fulfillment-monitor`, `/orders/picking-list` |
| `routes/marketing_account_health_routes.py` | `/health/summary`, `/health/timeline`, `/health/accounts` |
| `routes/marketing_content_calendar_routes.py` | `/content-calendar`, `/monthly`, `/summary` (termasuk hitungan "bulan ini" yang lolos dari `_sq`) |
| `routes/marketing_discounts_routes.py` · `marketing_samples_routes.py` | daftar + ringkasan |
| `routes/marketing_product_launches_routes.py` | daftar + ringkasan (lintas-toko: pemilik ATAU sasaran) |
| `routes/marketing_targets.py` | `/targets`, `/targets/creator`, `/targets/creator/monthly-summary` (kreator dilingkupi lewat `assigned_account_ids`) |
| `routes/marketing_catalog_mgmt.py` · `marketing_catalog_search.py` | katalog toko + pemilih produk "Buat Order" |
| `routes/marketing_data_import.py` | **`/data-import/history`** — dari baris riwayat ada tombol "Batalkan & pulihkan" ⇒ jalan pintas mengubah data toko orang lain |
| `routes/marketing_ai_insights_routes.py` | `/ai-insights/overview` (bahan kesimpulan AI) |
| `routes/marketing_livehost_hosts.py` · `marketing_livehost_shifts.py` | master host + jadwal shift |
| `routes/marketing_tasks.py` · `marketing_budget.py` | daftar tugas · biaya KOL |

**Penjaga yang mencegahnya terulang:** `B2-SWEEP` di `test_core_f6_rbac_scope.py` MENEMUKAN sendiri
setiap `@router.get` marketing baru dan mengujinya dengan dua token. Berkas route ke-110 tidak perlu
mengingat aturan F6 — gate-nya yang ingat.

## 2. Cacat kedua: NOL yang tidak menjelaskan dirinya

Sesudah kebocoran ditutup, staf tanpa toko melihat **0 di mana-mana** — dan pemilih tokonya berbunyi
*"Belum ada akun toko. Buat dulu di Kelola Akun"*: **jalan buntu** (staf tidak boleh membuat toko)
sekaligus **salah** (tokonya ADA, hanya belum di-assign). Ditambah `NaN` di kartu KPI
(`fmt('—')` → `NaN`), layar itu membaca seperti aplikasi rusak.

* `NoStoreScopeNotice.jsx` (**BARU**) — panel MENETAP: sebab + jalan keluar ("minta SPV Marketing
  meng-assign toko Anda … ini bukan berarti tokonya tidak berjualan"). Dipasang di Laporan Marketing
  & Jejak Perubahan; tidak tampil untuk peran yang memang melihat semua toko.
* `MarketingPickers.jsx` — pesan kosong pemilih toko dibedakan untuk peran berlingkup.
* `MarketingOverviewDashboard.jsx` — `fmt()` mengembalikan `—` untuk nilai yang belum diketahui.

## 3. Jejak yang menjawab "KENAPA", bukan hanya "berapa"

Target & rencana anggaran dulu tercatat **tanpa alasan** (hanya kewenangan & kunci periode yang
punya). Sekarang `reason` (opsional) diterima `POST /api/marketing/targets` & `PUT /api/marketing/budget`,
diteruskan ke `marketing_change_log`, dan bisa diisi dari **3 layar** (dialog Target & Anggaran di
Siklus + form Target di Target & Budget + tab Alokasi Anggaran).
Kebisingan `kosong → kosong` ("Staf dicabut: belum ada → kosong") dibuang di `_diff`.

## 4. Environment segar tidak lagi melahirkan layar audit kosong

`scripts/seed_marketing_change_log_demo.py` (**BARU**, idempoten, lewat API resmi — jejak tidak boleh
dikarang) + terdaftar di `bootstrap.sh`: SPV meng-assign toko ke 2 staf demo (`stafnia@`, `stafrio@`),
target dibuat lalu DIUBAH (ada nilai lama → baru), anggaran diubah, periode ditutup lalu dibuka ⇒
**16 baris jejak · 10 angka · 6 kewenangan · 2 pelaku · 5 toko**. `staffmkt@` **sengaja** tanpa toko
(subjek uji negatif), dan `stafnia@` memegang toko yang PUNYA data supaya "staf berlingkup" tidak
selalu tampak nol.

## 5. BUKTI

* `python3 test_core_f6_rbac_scope.py` → **100/100 PASS** (dari 51: +pas B0, +sweep 109 endpoint,
  +alasan angka, +kebisingan jejak, +panel no-scope, +NaN).
* Dibuktikan **MERAH** lewat sabotase (5 temuan) ⇒ dipulihkan ⇒ 100/100.
* `bash scripts/gate.sh` → **27/27 · VERDICT HIJAU** (`memory/GATE_RECEIPT.md`).
* Layar (Playwright, 0 page error): jejak 13→16 baris dengan nilai lama → baru + alasan · filter
  kewenangan 3 baris · pencarian menyempit · CSV tanpa galat · Portal Manajemen identik ·
  staf 2 toko melihat 8 baris tokonya saja · staf tanpa toko: semua 0 + panel penjelasan.
* `testing_agent_v3` iterasi 59 & **60: backend 35/35, frontend 100%, 0 bug**.
* Regresi Fase 1 utuh: Siklus Jul 2026 — Omzet produk **Rp 59.783.811** (tidak bergeser) · Setelah
  retur **Rp 57.561.529** · TIKTOK-OUTFIT retur **Rp 2.222.282 · 6 pesanan** · Target Rp 105.000.000.

## 6. YANG TIDAK DIKERJAKAN (jujur)

* F9 Settlement tetap TIDAK dimulai (berkas Pencairan asli belum ada) — label "sebelum potongan
  platform" dipertahankan.
* 19 endpoint acuan/konfigurasi (enum, master produk perusahaan, ambang alert, ingatan pemetaan,
  daftar orang) **sengaja** sama untuk semua pemakai; alasannya tertulis di `SCOPE_EXEMPT` dan dijaga
  guard `B2-DAFTAR`.
* `/api/marketing/account-assign/staff-options` masih bisa dibaca staf (daftar ORANG, bukan angka
  toko). Bila owner ingin ini pun tertutup, itu kartu kerja sendiri (menyentuh layar SPV).

# [2026-08-14 #9a] **RETUR TERLIHAT** — omzet bruto vs omzet setelah retur (+ gate MERAH ditutup)

## 1. Gate MERAH di titik berhenti sesi lalu — penyebab SEBENARNYA

Receipt hanya punya SATU gate FAIL, dan bukan yang diduga (`INV-KPIIMPOR` justru **40/40 PASS**).
Yang gagal: **`INV-MKTCYCLE` → `CYC-5c`** ("catatan kejujuran data menyebut HPP secara terbuka").

**Cacat produknya nyata, bukan tes cerewet.** `core/marketing_cycle._data_notes()` pada keadaan
"belum ada pesanan per baris" hanya berbunyi *"Marjin belum bisa dihitung…"* — kata **HPP tidak
pernah muncul**, jadi pembaca layar melihat **marjin 0%** tanpa pernah tahu SEBABNYA ("belum ada
dasar hitung" mudah dibaca sebagai "jualan tanpa untung"). Sekarang catatannya menyebut HPP terbuka
beserta alasannya (HPP hanya diketahui dari pesanan yang tertaut item katalog).

**Cacat kedua: environment segar melahirkan MERAH & layar kosong yang bukan salah produk.** Empat
seeder hanya hidup sebagai perintah manual di HANDOFF ⇒ `bootstrap.sh` saja menghasilkan 3 toko DEMO
(9 toko NYATA hilang), `marketing_orders` KOSONG (⇒ `CYC-8` di-SKIP), katalog tanpa varian internal.
Keempatnya kini terdaftar di `scripts/bootstrap.sh`: `seed_marketing_real_accounts.py --apply` ·
`seed_internal_variants.py` · `seed_katalog_order_demo.py` · `seed_marketing_cycle_demo.py`.

## 2. KEPUTUSAN PEMILIK: tampilkan DUA angka omzet (bukan menggeser yang lama)

> *"Pesanan retur — tampilkan dua-duanya: omzet bruto & omzet setelah retur, tanpa mengubah angka
> lama."*

    omzet bruto = definisi LAMA (semua status kecuali `cancelled`; retur IKUT)   ← TIDAK BERUBAH
    nilai retur = Σ pesanan berstatus `returned`                                  ← BARU
    omzet net   = bruto − nilai retur                                             ← BARU

Target, capaian, pace, ROAS, dan seluruh lampiran rapat yang sudah beredar **tetap** memakai bruto.

### Satu kalkulator: `backend/core/marketing_returns.py` (BARU)
`split_from_orders()` (dari pesanan) · `from_daily_rows()` (dari rekap harian) · `resolve()`
(pilih basis toko lalu hitung net & persen) · `evaluate_flags()` (`returns_high` kuning ≥5% / merah
≥10%) · `data_note()` · `rp()`. Tiga hal yang dijaga di dalamnya:
* **dua basis uang tidak boleh tertukar** — nilai retur disimpan pada basis *omzet produk* DAN
  *order amount*; mengurangi order amount retur dari omzet produk memberi net terlalu kecil;
* **cakupan jujur** — retur hanya diketahui dari pesanan per baris. Hari yang rekapnya
  DIIMPOR/DIKETIK dilaporkan **belum diketahui**, bukan "0 retur";
* **rumus retur kedua dilarang** — dua pembaca lama memakai `revenue_product` dengan cadangan
  `revenue` yang dibaca langsung dari dokumen ⇒ **Rp 0** untuk pesanan yang diinput staf lewat layar.
  Laporan mingguan sekarang memakai pembaca kanonik.

### Yang berubah
| Berkas | Perubahan |
|---|---|
| `core/marketing_returns.py` | **BARU** — satu-satunya kalkulator retur |
| `core/marketing_sales_shape.py` | grup `fulfillment` + `returned_revenue_product`, `returned_units` (+ label & daftar field turunan) |
| `core/marketing_daily_rollup.py` | `summarize_orders` menulis nilai retur pada kedua basis lewat kalkulator |
| `core/marketing_cycle.py` | `actual_from_daily` membawa `returns_split` · `cycle_summary.actual` + `revenue_gross`/`returned_amount`/`returned_orders`/`returned_units`/`revenue_net_returns`/`returns_pct` · blok `returns` (label + cakupan) · flag `returns_high` · catatan retur SELALU ada · `cycle_overview.totals` + total retur & net · **`CYC-5c` ditutup** |
| `core/marketing_weekly_report.py` | pembaca kanonik + `nilai_retur`/`pcs_retur`/`omzet_setelah_retur`/`retur_persen` per toko & gabungan + catatan |
| `routes/marketing_targets.py` | scorecard & rincian kreator: bruto · retur · setelah retur; catatan "PERLU KEPUTUSAN PEMILIK" **diganti** keputusan yang diambil |
| `utils/marketing_weekly_export.py` | Excel: 2 kolom retur di UJUNG (tidak menggeser indeks baris GABUNGAN) · PDF: kartu "SETELAH RETUR" |
| `CycleView.jsx` | kartu KPI `cycle-kpi-returns` · 2 kolom tabel · blok `cycle-detail-returns` di dialog · tampilan kartu · CSV |
| `CreatorScorecardView.jsx` | kolom Retur & Pesanan setelah retur · KPI `scorecard-kpi-returns` · kartu "Setelah retur" di dialog rincian · CSV |
| `WeeklyMeetingReportModule.jsx` | tile `weekly-tile-setelah-retur` + 2 kolom tabel (per toko & gabungan) |
| `backend/scripts/backfill_returns_daily.py` | **BARU** — mengisi nilai retur produk pada rekap harian turunan yang lahir sebelum sesi ini (idempoten, lewat mesin rekap yang sama) |
| `backend/scripts/seed_marketing_returns_demo.py` | **BARU** — membuat keadaan retur lewat SSOT status (reservasi dilepas) supaya fitur tidak tampak "belum jadi" di environment segar; didaftarkan di `bootstrap.sh` |
| `backend/scripts/seed_marketing_creator_demo.py` | jaring pengaman: bila tidak ada pesanan `DEMO-A-`, tautkan sebagian pesanan yang ADA (termasuk yang retur) ke kreator #1 — bertanda `_seed_creator_link` |
| `test_core_returns_visibility.py` · `scripts/gate.sh` | **51 penjaga baru** + gate **INV-RETUR** |

## 3. BUKTI

* `python3 test_core_returns_visibility.py` → **51/51 PASS**.
* **Dibuktikan MERAH (5 temuan)** saat net disabotase menjadi `net = bruto` ⇒ dipulihkan ⇒ 51/51.
* `bash scripts/gate.sh` → **26/26 · VERDICT HIJAU** (`memory/GATE_RECEIPT.md`).
* Layar (Playwright, bundel statis baru), **0 page error**: Siklus Jul 2026 ⇒ Omzet produk
  **Rp 59.783.811 TIDAK berubah** · kartu "Setelah retur" **Rp 57.561.529** · sel tabel
  `cycle-returned-TIKTOK-OUTFIT` = **Rp 2.222.282 · 6 pesanan** (−3,7%).
* `testing_agent_v3` (iterasi 10): **22/22 lulus · 0 bug** — 8 user story + 6 uji API + regresi 8 tab.

## 4. YANG TIDAK DIKERJAKAN (jujur)

* **F9 Settlement TIDAK dimulai** — berkas Pencairan/Settlement asli dari owner belum ada, jadi
  potongan platform (komisi/biaya) tetap di luar angka omzet. Label "sebelum potongan platform"
  dipertahankan di semua layar.
* Label **"pemetaan belum diverifikasi"** pada impor Ekspor B/C tetap dipasang (masih menunggu
  berkas ASLI dari owner).
* `returned` **tetap** dihitung di bruto — itu keputusan pemilik, bukan kelalaian. Kalau nanti
  diminta keluar dari omzet, itu kartu kerja sendiri (menyentuh F2 + F5 + F7.4) dan gate-nya harus
  dibalik: bukti bahwa angka historis MEMANG berubah + laporan migrasinya.

---

# [2026-08-14 #8c] IMPOR BERTINDIH — deteksi dobel di PRATINJAU + **lubang stok/uang ditutup**

Pertanyaan pemilik: *"kalau saya impor 1–7 lalu 5–12, apakah dobelnya terdeteksi? lalu kalau baris
yang sama berubah jadi dibatalkan, apakah otomatis terupdate?"*

**Jawaban terukur:** ya untuk keduanya — pencocokan dilakukan **per BARIS** memakai kunci dedupe
(`account_id + platform + order_id`), **bukan per rentang tanggal**; jadi rentang beririsan tidak
melahirkan baris kembar. Tetapi dua hal harus diperbaiki dulu:

1. **CACAT UANG/STOK (ditutup).** Pada mode "Perbarui yang lama", versi lama menulis SELURUH dokumen
   dengan `$set` — termasuk `status`. Akibatnya pesanan yang di berkas baru "Dibatalkan" berubah
   status **tanpa melepas reservasi stok** (pesanan batal tetap menggenggam stok ⇒ barang yang sama
   bisa dijanjikan ke dua pembeli), tetap tertinggal di antrean gudang, dan status bisa **MUNDUR**
   diam-diam saat berkas lama diunggah ulang. Sekarang status dijalankan lewat SSOT
   `core.order_status.apply_status` (`forward_only`, bukti batal/retur, pelepasan reservasi, jejak)
   — sama seperti jalur Ekspor B/C. Penolakan transisi DIJELASKAN di catatan hasil.
2. **Deteksi dobel dipindah ke PRATINJAU.** Dulu jawaban "sudah ada (duplikat)" baru muncul SESUDAH
   commit, padahal justru sebelum itu staf memilih "Lewati / Perbarui". Sekarang respons unggah &
   pemetaan membawa `duplicates`: `existing`/`new`, kunci dedupe yang dipakai, **rentang tanggal
   berkas**, **rentang tanggal yang bertindih**, dan contoh baris beserta **status sekarang**.
   Layar langkah 5 menampilkannya di atas pemilih tersebut.

**Bukti:** `test_core_f8_assign_ingat_scorecard.py` **47/47 PASS** (+13 penjaga baru seksi `[D]`:
1–7 lalu 5–12 ⇒ 3 dikenali sudah ada / 5 baru · bertindih 5–7 Agu disebut · commit "Perbarui" ⇒
3 diperbarui + 5 masuk · status paid→cancelled lewat aturan status & reservasi dilepas · unggah ulang
berkas lama ⇒ status TETAP batal).

---

# [2026-08-14 #8b] F8 — **Assign Toko (SPV)** · **“Ingat Pemetaan Saya”** · **Scorecard Kreator**

Ketiga layar sudah ada; yang ditambahkan sesi ini adalah hal-hal yang membuatnya **bisa dipercaya**.

**CACAT NYATA yang ditutup:** `test_core_f7_kpi_impor.py` menghapus `marketing_change_log`
**per `account_id`** saat bersih-bersih. Toko ujinya = toko shopee aktif pertama (**toko NYATA**),
jadi **setiap `bash scripts/gate.sh` memusnahkan riwayat “siapa memegang toko ini”** (diukur:
change_log 0 dokumen walau log backend memuat perubahan). Sekarang hanya baris bertanda
`[gate-kpiimpor]` yang dihapus + penjaga statik `A-2e`.

**A. Assign Toko** — `reason` **WAJIB** (≥4 huruf ⇒ 400 + contoh kalimat; diperiksa sesudah validasi
daftar staf) · `GET /by-staff` (sudut pandang per ORANG; staf dengan **0 toko** ikut terdaftar) ·
`GET /history` (riwayat SEMUA toko, berpaginasi) · staf **NONAKTIF** ditandai + `warnings[]` ·
`unassigned_count`/`stale_count`. Layar: **3 tampilan** (Per Toko · Per Staf · Riwayat), cari +
filter + paginasi 10/hal, **Simpan terkunci tanpa alasan**, dan **panel akibat MENETAP**.

**B. Ingat Pemetaan Saya** — respons unggah membawa **`format_memory`** (dipakai N×, terakhir oleh
siapa/kapan, `dropped[]`); pemetaan tersimpan **divalidasi terhadap skema** (entri yang menunjuk
field yang sudah tidak ada dibuang & dipetakan ulang mesin — dulu diterima apa adanya sehingga
kolomnya hilang tanpa galat); `GET /formats` + `DELETE /formats/{fingerprint}` (**lupakan**).
Layar: panel “Pemetaan ini DIINGAT dari impor sebelumnya … **bukan tebakan AI**”, tombol
**“Lupakan pemetaan ini”**, dan dialog daftar semua susunan kolom yang diingat (juga dari langkah 3).

**C. Scorecard Kreator** — `GET /creator/{id}/detail`: **konten · pesanan · sesi** baris demi baris,
memakai rumus & filter yang SAMA dengan scorecard sehingga totalnya **wajib sama persis**; pesanan
yang dikecualikan tetap tampil dengan sebabnya. Layar: dialog rincian (4 kartu + 3 tab, tanpa angka
gabungan), paginasi, pencarian, **unduh CSV** (kolom uang tetap terpisah), CTA tetapkan target.
**PERLU KEPUTUSAN PEMILIK (dibuat terlihat, bukan diubah diam-diam):** `EXCLUDED_FOR_REVENUE` hanya
`('cancelled',)` ⇒ pesanan **`returned` masih dihitung** sebagai omzet.

**Seeder baru** `backend/scripts/seed_marketing_creator_demo.py` (idempoten; tidak membuat master
toko baru; sengaja menyisakan 1 kreator tanpa target & 2 konten tanpa KPI) + didaftarkan di
`scripts/bootstrap.sh` — tanpa ini layar Scorecard selalu kosong di environment segar.

**Bukti:** `test_core_f8_assign_ingat_scorecard.py` **34/34 PASS** (dibuktikan **MERAH 25/34** saat
3 fitur dilepas) · `scripts/gate.sh` **25/25 HIJAU** (gate baru **INV-MKTOPS**) · verifikasi layar
sendiri via Playwright untuk semua cerita A1–A3/B1–B3/C1–C2, **0 page error** · agen uji iter 57–58:
0 bug (berhenti karena batasan sesi Playwright, bukan bug aplikasi).

---

# [2026-08-14 #8] F3 — Impor **Ekspor B/C** (status pengiriman/pembatalan) + “Batalkan impor” yang menepati janji

**Layar (`DataImportWizard.jsx`).** Sesi sebelumnya berhenti di tengah edit: JSX penolong pemetaan
sudah ada, dua fungsinya (`sampleFor`, `unmappedCols`) belum pernah didefinisikan ⇒ langkah
“Pemetaan kolom” **crash**. Ditutup, lalu diselesaikan:

* **Pemetaan bisa diperiksa** — kolom **“Contoh isi”** (nilai asli dari `preview[].original`),
  keterangan “N kolom berkas tidak dipakai”, badge “N kolom punya usulan menunggu keputusan Anda”,
  skor keyakinan, dan **pembalikan usulan**: field **WAJIB** → tombol **“pakai kolom «X» (98%)”**
  (sekali klik, tetap keputusan manusia — mesin tidak pernah memasang sendiri).
* **Usulan mesin tidak lagi hilang.** `auto_map()` kini mencatat pilihannya sebagai **usulan #1**
  (dulu `exact`/`synonym` punya `candidates: []`, jadi melepas kolom = kehilangan usulan selamanya).
* **Layar HASIL untuk `update_only`** — “Baris masuk 0” diberi keterangannya sendiri, kartu utama
  jadi **Pesanan diperbarui**, plus kartu **Bisa dipulihkan** dan larangan
  *“jangan unggah ulang Ekspor A untuk memperbaiki angka ini”*. Backend `_commit_message()`
  menyebut arti angkanya; respons commit menambah `update_only` + `undo_count`.
* **Riwayat impor jujur** — kolom **“Diperbarui”**, badge “hanya memperbarui”, tombol
  **“Batalkan & pulihkan”** (label berbeda untuk akibat berbeda), **dialog konfirmasi memuat angka
  dari `undo-report`** sebelum tombol dipakai, dan **dialog “Laporan pemulihan”** yang MENETAP
  (7 angka + catatan per pesanan dalam bahasa manusia + tabel jejak). Laporan dibuka otomatis
  sesudah pembatalan yang memulihkan keadaan.

**Bukti:** `test_core_f3_fulfillment.py` **55/55 PASS** (52 lama + `F3-M8/M9/M10` baru); tiga penjaga
baru **dibuktikan MERAH** saat `_cand_list` dilepas (53/55) lalu hijau lagi; gate baru
`INV-MKTFULFILL` terdaftar di `scripts/gate.sh`; verifikasi layar sendiri via Playwright pada bundel
statis baru (mapping → commit → riwayat → batalkan → laporan pemulihan).
**SSOT:** `memory/SSOT_KONTRAK_DATA_2026-08-12.md` §PEMULIHAN IMPOR (`marketing_data_import_undo`).
**Contoh berkas untuk staf:** `samples/ekspor_A_pesanan_contoh.csv`,
`samples/ekspor_B_status_dikirim_contoh.csv`, `samples/ekspor_C_batal_retur_contoh.csv`.

---

# [2026-08-13 #7] F6 (RBAC per toko + jejak) & F7 (konten & kreator) — INTI SELESAI

F6: `core/marketing_account_scope` kini menjaga **visibilitas per pemakai**, bukan hanya lingkup data.
Staf yang di-assign 1 toko hanya melihat 1 toko; membuka toko lain ⇒ **403**; menetapkan target ⇒
**403** (keputusan SPV). Jejak perubahan target/anggaran/kunci bisa dibaca layar
(`GET /api/marketing/periods/change-log`) dan tampil sebagai panel **"Jejak perubahan"** di dialog
Detail Siklus — pertanyaan "target bulan lalu kok beda dengan notulen" akhirnya bisa dijawab
(nilai LAMA → BARU + nama & peran pelaku).

F7: konten kini punya **pemilik (kreator)**, **link terbit wajib** untuk status `posted` (400 bila
kosong/ngawur), dan **KPI** dengan angka turunan yang DIHITUNG (engagement rate, CVR, GMV/view).
`GET /content-calendar/performance` melaporkan per kreator/jenis/toko: konten · views · engagement ·
saves · CTR · order · **GMV (KPI platform)** dan **omzet pesanan** (`marketing_orders.creator_id`)
— **dipisah, tidak dijumlah**, plus **cakupan KPI** supaya pembaca tahu berapa bagian yang terukur.
Layar: pintu "Kalender Konten" kini dua tampilan (Kalender & Rencana | **Performa Konten**, tabel 16
kolom + Kartu) — satu pintu, bukan pintu kembar.

Bukti: `test_core_f6_f7.py` **21/21 PASS** · `bash scripts/gate.sh` **VERDICT HIJAU** ·
`check_nav_map` HIJAU · verifikasi layar oleh main agent (Playwright): tab Performa Konten (16 kolom,
catatan kejujuran) & panel Jejak perubahan tampil.

# [2026-08-13 #6] F4 DIVERIFIKASI + F5 SELESAI — SATU LAYAR SIKLUS TARGET · ANGGARAN · OMZET

## Konteks
Sesi sebelumnya berhenti tepat sesudah `search_replace` pada `moduleRegistry.js` (F4.4: deep-link
lama `toko-products` diarahkan ke `marketing-catalog`) lalu menjalankan rebuild. Permintaan user:
**verifikasi**, dan *"jika memori di container ini besar mungkin jangan dengan static build —
keputusan saya serahkan pada anda"*.

**Keputusan lingkungan (DIUKUR):** `cpu.max = 100000 100000` (kuota **1 core**) dan
`memory.max = 2 GiB`. `free -h` yang menyebut 62 GiB adalah memori HOST — yang berlaku adalah batas
cgroup. Karena itu **static bundle DIPERTAHANKAN** (dev server CRA mengompilasi 567 berkas ⇒ health
probe platform gagal ⇒ pod restart berulang ⇒ preview tak pernah menyala). Setiap ubah
`frontend/src` ⇒ `bash scripts/rebuild_frontend.sh` (±60–90 detik).

## F4 (Katalog) — 6/6 bukti terpenuhi
`test_core_f4_katalog.py` **36/36 PASS** (status turunan 6/6 · publish tanpa `platform_url` ⇒ 400 ·
`master_images` ikut terbawa tanpa unggah manual · kontrak 19 kolom baris · `by_status` = total item).
Di layar: tabel **21 kolom**, pengalih Tabel/Kartu bertahan (`catalog_items_view`), deep-link
`toko-products` mendarat di **Manajemen Katalog Produk**.

## F5 (baru) — siklus, realisasi otomatis, kunci periode, peringatan
* **`core/marketing_cycle.py`** = SSOT angka siklus. `cycle_summary` (1 toko × 1 bulan) &
  `cycle_overview` (semua toko + total + papan perhatian, **peringkat dihitung backend**).
  Endpoint `GET /api/marketing/cycle/summary` & `/overview` sengaja tinggal di
  `routes/marketing_budget.py` supaya anggaran berhenti menjadi pulau.
* **Omzet TIDAK dihitung ulang di sini** — dibaca dari rekap harian turunan (F2), jadi override SPV
  otomatis ikut terpakai dan tidak lahir "angka omzet keempat".
* **Realisasi anggaran otomatis + BUKTI**: `diskon` = Σ diskon penjual + subsidi ongkir dari pesanan
  (**Rp 48.020.983 dari 559 pesanan, tanpa satu pun entri manual** — sebelumnya kategori ini selalu
  Rp 0 karena hanya bisa diisi manual, dan anggaran yang selalu "aman" membuat keputusan diskon
  diambil tanpa tahu biayanya) · `ads` · **`komisi` (kategori BARU)** · `kol` (fee tetap) ·
  `livehost`. Angka otomatis **tidak** ditulis ke `marketing_spend_entries` (anti dobel-hitung).
* **Kunci periode** (`marketing_period_locks`): `GET/POST /api/marketing/periods/lock` + **HTTP 423**
  di 5 jalur tulis — target · anggaran · belanja · rekap harian · **commit impor** (ditolak SEBELUM
  satu baris tersimpan: 559 → 559, bukan separuh). 423 dipilih dengan sengaja (bukan 403): masalahnya
  bukan "kamu tak berhak" melainkan "bulannya sudah ditutup", dan jalan keluarnya minta SPV membuka.
  Semua aksi kunci/buka + ubah target/anggaran masuk **`marketing_change_log`** (pendahuluan F6).
* **Peringatan** dari SATU fungsi `evaluate_flags` (layar & lonceng notifikasi tidak mungkin beda):
  `target_behind` (pace − capaian) · `budget_warning`/`budget_overrun` · `budget_overrun_category` ·
  **`budget_unplanned_category`** · `hpp_coverage_low` · `target_missing`.
* **Marjin selalu ditemani cakupan HPP.** Marjin dari 3 item ber-HPP di antara 600 item adalah angka
  yang menipu; layar wajib bisa menyebut cakupannya. Bila cakupan < 80% ⇒ ROI berbasis marjin
  ditandai **tidak bisa dipercaya** (ROAS tetap sah).
* **LAYAR** `CycleView.jsx`: 6 KPI · papan "Perlu perhatian" · **tabel 21 kolom** + pengalih
  Tabel/Kartu (bertahan) · dialog Target/Anggaran/Kunci dengan **alasan wajib** dan galat yang
  **MENETAP di dalam dialog** (termasuk 423) · dialog Detail (rencana vs realisasi per kategori +
  kolom **Bukti**) · CSV · catatan kejujuran data. **Satu komponen, dua portal**: `marketing-targets`
  (Marketing) & `mgmt-marketing-cycle` (Manajemen) — angka terbukti IDENTIK.

## Cacat NYATA yang ditutup (ditemukan saat menguji)
1. **Pesanan MANUAL tidak menyimpan `account_id`** (penjaga F14 menolak order tanpa toko, tapi
   id-nya tak pernah ditulis) ⇒ setiap pesanan yang diinput staf menjadi baris **yatim**.
2. Pesanan manual tanpa **nama uang kanonik** & item pakai `qty`/`price` ⇒ menyumbang **Rp 0** ke
   omzet, anggaran diskon, dan marjin, tanpa satu pun galat. Ditutup di penulis (nama kanonik ikut
   ditulis) **dan** pembaca (`core/marketing_daily_rollup` kini punya pembaca defensif SATU definisi).
3. **Tidak ada hook rekap harian** saat pesanan manual dibuat, statusnya berubah, atau dihapus ⇒
   membatalkan pesanan tidak mengembalikan omzet hari itu.
4. Rekap **turunan** milik toko yang sudah dihapus dibiarkan ⇒ kini dihapus (`deleted_orphan`).
5. **ROI −100%** hanya karena HPP belum tertaut ⇒ kini "ROI belum bisa dihitung" + alasannya.
6. Kategori anggaran ber-rencana Rp 0 tetapi terpakai puluhan juta tidak pernah ditandai (pembagi
   nol) ⇒ flag `budget_unplanned_category`.
7. Portal berlabel **"Marketing"** ber-id `toko`: `?portal=marketing&module=…` mendarat di portal
   lain **tanpa pesan** (satu sesi uji penuh habis karenanya) ⇒ `PORTAL_ID_ALIASES` + fallback ke
   portal **pemilik modul** + guard **NAV-ALIAS** di `check_nav_map.py`.
8. Daftar "Terakhir" di sidebar menampilkan **id mentah** (`toko-products`) ⇒ hanya pintu bernama.
9. Gate `_audit_ui_tables_v2.py` **buta komponen anak** dan tidak mengenali pola pengalih repo ini
   (state `view` + tombol `*-view-table/grid`) dan judul kolom dari ARRAY ⇒ modul yang sudah benar
   dilaporkan "tanpa pengalih". Kini mengikuti import lokal 1 tingkat + `via` untuk penelusuran.

## Bukti
`test_core_f5_siklus.py` **58/58** · gate baru **INV-MKTCYCLE 31/31** (CYC-3 kunci diuji dengan
pelanggaran sintetis; CYC-8 rantai pesanan manual → rekap → siklus) · `test_core_f4_katalog.py`
**36/36** · `test_core_f1_f2_omzet.py` **59/59** (tanpa regresi) · `bash scripts/gate.sh` **22/22
VERDICT HIJAU** · `gate_marketing_ssot` **10/10** · `verify_marketing_scope` **32/32** ·
`check_nav_map` HIJAU · testing agent iter_53 & iter_55: **F5①–⑧ 8/8 PASS**, **F4①② PASS**.

## Data demo
`python3 scripts/seed_marketing_cycle_demo.py` (idempoten, `--cleanup`): 559 pesanan nyata Jul 2026 ·
TIKTOK-OUTFIT target 100 jt + anggaran 40 jt (tertinggal + terlampaui) · TikTok Dezza Kids target
5 jt tanpa pesanan ("belum ada data" ≠ nol) · Tokopedia tanpa target.

# [2026-08-08 lanjutan] REKAP HARIAN CMT — "vendor mana yang belum diisi hari ini"

## 2026-08-12 (#5) — 4 KEMAMPUAN BARU **BISA DIPAKAI DARI LAYAR** (backend 51/51 sudah ada, layarnya belum)

**Konteks:** sesi sebelumnya berhenti tepat sesudah backend keempat kemampuan terbukti
(`test_core_katalog_monitor_mingguan.py` **51/51 PASS**) dengan catatan *"Now the frontend for all
four"*. Tiga berkas layar sudah tertulis tetapi **belum ter-bundle** (import `./moduleAtoms` salah
path ⇒ gate lint MERAH) dan **belum punya pintu masuk** di navigasi/hub — jadi dari sudut pandang
pemakai keempat kemampuan itu **tidak ada**.

### 1. Monitoring Pengiriman (F3) — `marketing-fulfillment`, sidebar "Monitoring Kirim"
Bukan "daftar semua pesanan" (itu Order Terpadu) melainkan **apa yang harus dikejar hari ini**:
5 kartu angka (lewat batas · belum dikirim · menunggu terlama · batal/retur · sudah dikirim),
rekap per toko, tabel pesanan dengan kolom **Menunggu / Batas / Lewat / Tenggat**, unduh CSV, dan
**batas kirim per toko bisa diubah dari layar** (normal & pre-order). Batas sengaja TIDAK
dikarang di kode: daftar "merah" yang aturannya tersembunyi tidak bisa dipertanggungjawabkan
ke siapa pun. Catatan kejujuran data selalu ikut (mis. "BATAL & RETUR 0 karena Ekspor A tidak
memuatnya — jangan disimpulkan tidak ada pembatalan").

### 2. Laporan Rapat Mingguan (F8) — tab **Rapat Mingguan** di hub Laporan
Per toko + gabungan, vs minggu lalu, target prorata, pecahan 9 kanal, pemenuhan, ROAS, 6 catatan
kejujuran data, **PDF & Excel dari SATU sumber angka** (layar, PDF, dan Excel tidak mungkin
berbeda). Bukti angka: minggu **2026-W29 (13–19 Juli 2026)** = **Rp 46.301.365** · 429 pesanan
belum dikirim — sama dengan rekap harian di DB.

### 3. Isi Katalog dari Master Produk — tab **Isi dari Master** di Manajemen Katalog
Jalur lama hanya bisa menambah **satu varian ke satu katalog** per aksi ⇒ untuk 9 toko × puluhan
varian itu ratusan klik, dan yang benar-benar terjadi bukan "staf sabar" melainkan **katalog
dibiarkan kosong** — akibatnya item pesanan hasil impor tidak bisa ditautkan ke master sehingga
**marjin per pesanan tidak bisa dihitung sama sekali**. Sekarang: pilih produk master → centang
toko tujuan → satu tombol; HPP/kategori/berat/harga resmi **selalu** dari master (tidak ada kolom
untuk mengetiknya di layar ini — itulah cara "HPP Rp 0" lahir), katalog toko dibuatkan otomatis,
idempoten (varian yang sudah ada dilaporkan "sudah ada", bukan digandakan). Mode harga awal
(**harga resmi master** / **kosongkan, isi per toko nanti**) & batas peringatan stok kini ada di
layar — sebelumnya dua kemampuan backend itu tidak bisa dijangkau pemakai.

### 4. Gudang platform BELAJAR dari berkas — Wizard Impor langkah 4
Penjaga toko (F1) hanya bisa menahan "berkas masuk ke toko yang salah" kalau master toko sudah
menyimpan `platform_warehouse_name`, dan dari 9 toko hanya 1 yang terisi. Meminta pemilik
mengetik 8 nama dari ingatan justru berbahaya: satu salah ketik membuat penjaga menolak berkas
yang BENAR, dan staf akan belajar mengabaikan penjaga. Karena itu namanya diambil dari **ekspor
platform itu sendiri**: panel kuning menyebut gudang yang terbaca + tombol **"Simpan gudang '…'
ke master toko"**; hasilnya (termasuk penolakan 409 "gudang ini sudah dipakai toko lain" — petunjuk
terpenting bahwa tokonya salah pilih) **menetap di layar**, bukan toast 5 detik. Strip tujuan
impor kini juga menyebut **Gudang platform: … / belum diisi** sejak langkah 2.

### 6. Akun peran Portal Marketing akhirnya ADA (uji tidak lagi hanya sebagai superadmin)
`portalAccess.js` mengizinkan Portal Marketing untuk role `pic_toko` / `pic_marketing` /
`staff_marketing` / `marketing_kol` / `cs_staff` / `manager_marketing` — tetapi **tidak ada satu pun
akun** dengan role itu di DB (`spv@dewiaditya.id` ternyata `supervisor_produksi`, dan kartu Portal
Marketing untuknya berbunyi "Tidak ada akses"). Akibatnya seluruh pembuktian layar marketing —
termasuk empat kemampuan sesi ini — hanya pernah dilakukan sebagai **superadmin**, peran yang
melewati penyaringan portal & menu. Ditambahkan ke `seed_role_accounts.py` (idempoten):
`marketing@dewiaditya.id` (manager_marketing) dan `staffmkt@dewiaditya.id` (staff_marketing),
password `Dewi@123`. Diverifikasi: Monitoring Pengiriman, Laporan Rapat Mingguan, dan Isi Katalog
dari Master **terbuka & berdata** memakai akun marketing (bukan superadmin).

### 7. Cacat layar yang ditutup
1. `import { PageHeader } from './moduleAtoms'` (path salah) ⇒ gate lint MERAH + 3 layar tak
   mungkin ter-bundle. 2. Tabel rekap per toko Monitoring disembunyikan bila hanya 1 toko berdata,
   padahal tombol "Batas kirim" hanya ada di sana ⇒ batas kirim tak bisa diubah pada keadaan
   paling umum. 3. Toko **tanpa pesanan** tidak bisa disetel batasnya ⇒ tombol "Batas kirim toko
   ini" di toolbar. 4. Senin minggu dihitung dari **UTC** ⇒ di Asia/Jakarta rapat Senin pagi
   membuka **minggu lalu**; kini waktu lokal. 5. Deep-link tab lewat `makeRedirect` +
   `sessionStorage` **bergantung urutan mount** dan terbukti mendarat di tab pertama; kini tab
   awal dipilih dari prop **`moduleId`**. 6. Penolakan dialog batas kirim tidak terlihat (hanya
   toast) ⇒ pesan **menetap di dalam dialog** + validasi sisi layar + `data-testid` pada tombol
   Batal.

### Bukti
`test_core_katalog_monitor_mingguan.py` **51/51 PASS** ·
`scripts/_verify_fe_contract_monitor_weekly_katalog.py` (**baru**) **36/36 PASS** — memastikan
setiap **nama field yang dibaca JSX** benar-benar ada di respons endpoint (layar yang membaca
`overdue_days` sementara backend mengirim `over_by_days` tampil "—" di seluruh kolom tanpa satu pun
galat: uji API hijau, staf melihat tabel kosong) · `scripts/gate.sh` **21/21 HIJAU** ·
`gate_marketing_ssot` **10/10** · `verify_marketing_scope` **32/32** · `check_nav_map` (INV-NAV-01)
**HIJAU** · testing agent `iteration_52` **100%** (Fitur B 6/6 · Fitur A 5/5 · 4 perbaikan · regresi
tab hub) · Playwright main agent (A1–A3, deep-link 2 tab, validasi batas kirim).

---


## 2026-08-12 (#4) — F1 + F2 + F4 TERBUKTI DI LAYAR; 6 cacat nyata ditutup

**Konteks:** sesi sebelumnya menutup backend F1/F2/F4 (59/59 PASS) tetapi **tidak satu pun
dari 7 alur UI pernah terbukti** — testing agent berhenti di langkah 1 wizard karena memakai
`data-testid` yang salah. Sesi ini memulai dari lingkungan kosong (klon repo), memulihkan
seluruh lingkungan, lalu **membuktikan ketujuh alur di layar** — dan dalam prosesnya
menemukan enam cacat yang tidak mungkin terlihat dari uji API saja.

### 1. `<Toaster/>` shadcn tidak pernah dipasang — 57 modul bisu (`frontend/src/App.js`)
`hooks/use-toast` dipakai **57 modul** (Wizard Impor, dashboard marketing, dll), tetapi
`<Toaster/>`-nya tidak ada di pohon React. Akibatnya **semua** pesan sukses/gagal modul itu
hilang tanpa jejak: staf menekan "Simpan", layar diam, lalu dia menekan lagi (dobel data)
atau menyangka aplikasi menggantung. Sonner (dipakai modul lain) tetap dipasang berdampingan.

### 2. Langkah 1 wizard: jenis data yang paling sering dipakai terkubur
Grup diurutkan **alfabetis** (`Object.keys().sort()`) ⇒ "Penjualan" — yang memuat **Pesanan
Marketplace**, dipakai hampir setiap hari — jatuh di urutan **ke-7**, di bawah After-Sales,
Iklan, Katalog, Konten, Kreator, Live; staf harus menggulir melewati 14 kartu. Sekarang:
urutan mengikuti alur kerja (uang dulu), ada kotak **pencarian** (`import-type-search`), dan
kartu utama diberi badge **"paling sering"**.

### 3. Pagar F2 bisa dilangkahi lewat jalur IMPOR (`core/marketing_sales_shape.py`)
`POST /sales-data` sudah menolak 409 untuk tanggal turunan, tetapi jenis impor `sales_daily`
menulis ke koleksi **yang sama** dengan kunci alami yang sama, **tanpa pagar**. Dibuktikan
`scripts/_verify_f2_import_lock.py`: satu berkas Excel mengubah Rp 4.213.092 / 45 pesanan
(turunan dari 559 pesanan nyata) menjadi **Rp 1.000.000 / 5 pesanan**, dan dokumennya
kehilangan kuncinya (`source='import'`, `locked_source=False`) sehingga rollup berikutnya pun
tidak memulihkannya. **Dua angka omzet untuk satu hari kembali lagi.**
Perbaikan mengikuti prinsip rollup — *lindungi angkanya, jangan buang datanya*:
`derived_safe_update()` membuang grup `metrics`/`traffic` + field fulfillment turunan + field
akar identitas, menyimpan sisanya (rating, funnel, live, konten), dan barisnya dilaporkan
"sebagian disimpan" beserta alasan + jalan keluar (Override SPV).

### 4. PENJAGA TOKO — sidik gudang di dalam berkas (`shop_guard`)
Penjaga platform lama hanya menangkap "berkas Shopee masuk toko TikTok". Ia **tidak**
menangkap kesalahan yang jauh lebih mudah: memilih **1 dari 5 toko TikTok** yang namanya
mirip. **Terjadi nyata saat uji sesi ini:** 559 pesanan gudang 'Outfit Boutique'
(Rp 59.783.811) masuk ke **TikTok Daluna** — commit sukses, rekap harian terbentuk, dan
**tidak ada satu pun layar yang membantah**. Padahal buktinya ada di berkas: kolom
`Warehouse Name` = 'Outfit Boutique' pada seluruh 601 baris, dan master toko sudah
menyimpannya sejak F0.7 (`platform_warehouse_name`) — yang belum ada hanyalah pembandingnya.
Sekarang: (a) gudang berkas ≠ gudang toko tujuan ⇒ **400**; (b) toko tujuan belum mengisi
gudang tetapi gudang itu terdaftar pada toko lain ⇒ **400 yang menyebut nama toko
pemiliknya**; (c) tidak ada pemilik ⇒ tetap boleh, tapi sesi membawa `shop_guard_hint`.
Berkas unggahan yang ditolak langsung dibuang. Bukti: `scripts/_verify_f1_shop_guard.py`.

### 5. Kesalahan tujuan & penolakan kini TERLIHAT di layar (`DataImportWizard.jsx`)
- **Strip tujuan** di setiap langkah: "Masuk ke toko: TikTok Outfit Boutique
  (TIKTOK-OUTFIT · tiktokshop)" + nama berkas.
- **Panel penolakan MENETAP** untuk unggah & commit (`import-upload-error`,
  `import-commit-error`) + tombol "Ganti toko tujuan". Sebelumnya pesan penjaga hanya
  muncul 5 detik lalu layar langkah 3 kembali kosong tanpa keterangan apa pun.
- **Akibat rollback dijelaskan**: berapa tanggal rekap dihapus/dihitung ulang, dan berapa
  yang **TIDAK dikembalikan karena sudah di-override SPV** (perlu tindak lanjut manual).
- Banner `shop_guard_hint` bila gudang berkas tidak bisa dipastikan milik toko tujuan.

### 6. Jalan keluar SPV akhirnya ADA di layar (`SalesDataEntryModule.jsx`)
Backend punya `POST /sales-data?override=true&override_reason=…` sejak F2, tetapi **tidak ada
satu pun layar yang memanggilnya** — jadi kunci F2 bukan pagar, melainkan **kebuntuan**.
Sekarang, begitu (toko, tanggal, tipe) dipilih:
- pemberitahuan kunci menyebut angka turunannya ("omzet Rp 4.213.092 dari 45 pesanan"),
- **Revenue & Orders di-disable** (hanya keduanya — sisanya bukan turunan),
- tombol **Ganti Angka (Override SPV)** membuka **alasan wajib** dan mengisi kolom dengan
  angka turunan sebagai titik awal (mengetik ulang 7 angka dari nol = kesalahan baru),
- galat 409 (panjang, memuat jalan keluar) **ditahan di dalam form** + toast 12 detik;
  dulu hilang dalam 4 detik dan tidak pernah selesai dibaca.

### 7. Berkas unggahan yatim ikut dibersihkan (`backend/utils/scheduler.py`)
`cleanup_old_marketing_uploads` hanya menghapus berkas >30 hari. Berkas yang **sesinya sudah
tidak ada** (dihapus staf / pratinjau yang dibuang) tertinggal walau tak akan pernah bisa
dipakai lagi — satu sore uji meninggalkan **73 berkas ±18 MB**. Sekarang berkas yatim
(dengan jeda aman 1 jam) juga dihapus; kalau daftar sesi gagal dibaca, pembersihan yatim
**dilewati** supaya bukti impor tidak pernah terbuang karena galat baca.

### Bukti
`test_core_f1_f2_omzet.py` **59/59 PASS** · `scripts/_verify_f2_import_lock.py` PASS ·
`scripts/_verify_f1_shop_guard.py` PASS · `scripts/_verify_f4_health_after_import.py` PASS
(skor 60 → bintang **3 "Cukup"** + 5 pilar) · UI-1…UI-7 + UI-1b/UI-1c PASS ·
`scripts/gate.sh` **21/21 HIJAU** · `gate_marketing_ssot.py` 10/10 · `verify_marketing_scope.py` 32/32.
Data seed dikembalikan bersih (0 pesanan · 0 rekap · 0 sesi · 0 berkas yatim).

---

## 2026-08-11 (lanjutan #3) — F0.7 LAYAR Manajemen Akun: field baru bisa DIISI & DILIHAT

**Konteks:** backend F0.7 (tautan Finance per toko) sudah ada, tetapi layar
`AccountManagementModule.jsx` masih kartu-saja dengan 8 field — SEMUA field F0.7
(`coa_revenue_code`, `coa_cash_code`, `coa_receivable_code`, `revenue_basis`,
`platform_warehouse_name`, `platform_shop_id`) tidak pernah terlihat maupun bisa diisi.

**Yang berubah — FRONTEND** (`frontend/src/components/erp/AccountManagementModule.jsx`, ditulis ulang):
- **Tabel (default) + Kartu (alternatif)** sesuai aturan `plan.md`; **16 kolom**:
  Kode · Nama · Platform · Grup · Username · Status · PIC · Akun Pendapatan ·
  Rekening Pencairan · Piutang Platform · **Piutang Toko (otomatis = `ar_account_code`)** ·
  Basis Omzet · Gudang Platform · Shop ID · Skor · Aksi (kolom aksi sticky kanan).
  Paginasi 10/halaman (`ui/pagination-lite.jsx`). Audit `_audit_ui_tables_v2.py`:
  modul ini **keluar dari daftar KARTU-SAJA** (`th=16`, `toggle=true`, verdict bersih).
- Kolom COA menampilkan **kode + nama akun** (bukan nomor mentah) dari `/coa-options`;
  akun penampung bersama (mis. `4-114 … Lain-lain`) diberi badge **"penampung"**.
- Form buat/edit: dropdown **Akun Pendapatan** (dikelompokkan "Disarankan untuk
  <platform>" vs "Akun penjualan lain"), **Rekening Pencairan**, **Akun Piutang**,
  **Basis Omzet** (label panjang dari backend), **Gudang Platform**, **Shop ID**,
  **PIC (kini juga saat BUAT baru)**, switch integrasi API. Akun Pendapatan &
  Rekening Pencairan **wajib** — tak boleh ada toko tanpa alamat jurnal.
- BD-5: badge **"perlu ditinjau"** + tombol **"Tandai sudah ditinjau"** (tabel & kartu).
- Pencarian (kode/nama/username/kode COA/gudang/shop id), filter platform/status/grup,
  5 KPI tile yang bisa diklik (Total · Aktif · Tanpa PIC · Perlu Ditinjau · Tanpa Akun Pendapatan).

**Yang berubah — BACKEND** (`routes/marketing_accounts.py`, `routes/marketing_shared.py`):
- `PlatformAccountCreate` menerima `pic_user_id` (PIC bisa diisi sejak pembuatan,
  `pic_user_name` di-denormalisasi); `PlatformAccountUpdate` menerima `needs_owner_review`
  (+ jejak `owner_reviewed_at/by`).
- **BUG DITUTUP (ditemukan test_core):** validasi COA dulu hanya memeriksa "kode ada".
  Akibatnya `9-000 BIAYA UMUM & ADMINISTRASI` (akun **grup beban**) lolos sebagai
  "rekening pencairan". Sekarang `_validate_coa_role()` menolak akun grup, akun
  nonaktif, dan akun **salah peran** (pendapatan harus `is_sales` non-kontra; kas harus
  `is_cash|is_bank`; piutang harus `is_ar`) dengan pesan yang bisa ditindaklanjuti.
- `GET /accounts/coa-options` disaring pakai `flags`+`is_group`+`active` (bukan awalan
  kode) ⇒ daftar kas tidak lagi tercemar piutang/persediaan/pajak/akun grup;
  menambah `default_cash`, `fallback_revenue_by_platform`, `platform_channel_map`,
  dan `channel` per opsi pendapatan.
- Toko baru tanpa COA tetap dapat alamat jurnal: pendapatan penampung platform
  (`4-114`/`4-126`/`4-131`) + kas `1-131` + piutang `1-220` (semua diverifikasi ada;
  penanda `coa_revenue_source`). Respons POST kini **membaca ulang dokumen** sehingga
  `ar_account_code` (akun COA otomatis) langsung terlihat di UI.
- `scripts/backfill_marketing_channel_subledger.py` (baru; opsi `--apply`, `--prune-orphans`) +
  `seed_marketing_real_accounts.py` kini membuat **akun COA piutang per toko** (subledger anak `1-220`) — 9 toko hasil seed
  sebelumnya tidak punya akun buku besar sendiri karena seed menulis langsung ke DB.
  `--prune-orphans` membersihkan akun subledger yang tokonya sudah dihapus keras (sisa skrip uji).

**Bukti:** `python3 scripts/test_core_f07_accounts_ui.py` → **57 PASS / 0 GAGAL**
(HTTP nyata + verifikasi DB: auto-subledger anak 1-220, tautan `flags.subledger_entity_id`,
validasi 400 untuk COA palsu/grup/kontra/basis ngawur, PUT semua field baru, archive).
`bash scripts/gate.sh` → **21/21 HIJAU**; `scripts/gate_marketing_ssot.py` → **10/10 HIJAU**;
`scripts/verify_marketing_scope.py` → **32 PASS / 0 FAIL**.


## 2026-08-11 (lanjutan #2) — F18#3 Rincian Produk per Sesi Live + bugfix `platform: None`

**Cacat yang ditutup (dua-duanya SUNYI — tidak ada error, hanya angka salah):**

1. **Ulasan & Retur menyimpan `platform: null` pada SETIAP baris baru.** Sesi
   sebelumnya membuat `platform` opsional di model, tetapi `POST/PUT` masih
   menulis `body.platform` apa adanya. Bukti uji sebelumnya:
   `product: Blouse Batik Modern DA-020 | sku: DA-BBM-020 | platform: None`.
   Akibat: kartu & filter "per platform" kehilangan seluruh baris baru.
   Sekarang `POST/PUT /api/marketing/reviews` dan `/returns` wajib `account_id`
   (`require_account`) dan `account_name`/`platform` **selalu turunan master**
   (`stamp_account`); `platform`/`account_name` yang dikirim layar diabaikan.
2. **`GET /live/analytics/product-performance` mustahil berisi.** Endpoint itu
   meng-`$unwind` `products[]` yang tidak punya SATU PUN jalan pengisian (CRUD,
   impor, maupun seed tidak menulisnya) ⇒ selalu kosong. Cacat kedua di endpoint
   yang sama: parameter `account_id` **diterima tapi tidak dipakai** di `$match`,
   jadi filter toko di layar tidak berpengaruh — angka toko A tercampur toko B.

**BARU (backend):** `core/marketing_live_products.py` — SSOT rincian produk sesi
live (koleksi `marketing_live_session_products`, 1 baris = 1 produk pada 1 sesi):
produk WAJIB item katalog toko sesi · indeks unik `(session_id, catalog_item_id)`
(satu produk sekali per sesi, dijaga BASIS DATA bukan hanya kode) · omzet rincian
tidak boleh melebihi omzet sesi (toleransi 2%) · `revenue > 0` dengan `0` unit
ditolak · `units_sold = 0` SAH (produk dibawakan tapi tidak terjual) ·
harga rata-rata/HPP/margin dihitung server · `reconcile()` satu-satunya sumber
angka cakupan (layar & server memakai definisi yang sama) · seed demo untuk 18
sesi demo (50 baris) supaya DB baru tidak tampak rusak.

**Endpoint baru:** `GET/PUT/POST /api/marketing/live/sessions/{id}/products` ·
`PUT/DELETE .../products/{line_id}` · `POST .../products/sync-session-totals`
(aksi eksplisit "samakan total sesi", bukan efek samping) · `products[]` diterima
pada `POST/PUT /live/sessions` (satu form satu simpan) · hapus sesi ⇒ rincian ikut
terhapus (cascade, tanpa baris yatim) · `GET /live/sessions` menyertakan
`products_detail` per baris dalam SATU agregasi per halaman.

**Impor tanpa AI (F17) diperluas:** jenis data ke-16 `live_session_products`
(kolom SKU/nama/unit/omzet/order, sinonim ekspor marketplace) + konteks baru
`live_session` (sesi DIPILIH di wizard, bukan dicocokkan dari judul berkas) ·
baris ber-SKU yang tidak ada di katalog toko **DITOLAK dan ditandai galat di
PRATINJAU** (dulu pola lamanya: disimpan dengan tautan kosong lalu tidak pernah
muncul di laporan) · commit yang akan melebihi omzet sesi ditolak **sebelum**
menulis (tidak ada keadaan setengah tersimpan) · rollback tetap bekerja.

**BARU (frontend):** `marketing/LiveSessionProductsEditor.jsx` (baris produk pilih
dari katalog, rekonsiliasi hidup + bar cakupan) · `marketing/LiveSessionProductsDialog.jsx`
(tombol **Rincian** per baris tabel + "Samakan total sesi") · kolom **Rincian
Produk** di `LiveSessionModule` · tab **Produk Terlaris** + filter toko di
`LiveSessionAnalyticsDashboard` (endpoint yang dulu tanpa layar) · pemilih **sesi
live** di `DataImportWizard`.

**Gate:** INV-MKTSCOPE naik 28 → **32 kode** (MKS-24 lingkup toko rincian ·
MKS-25 baris yatim · MKS-26 produk dobel · MKS-27 rincian melebihi omzet sesi).
Ketiga detektor **dibuktikan MERAH** dengan pelanggaran sintetis lalu dibersihkan;
MKS-26 bahkan tidak bisa dilanggar lagi karena indeks unik menolaknya di DB.
`bash scripts/gate.sh` → **21/21 VERDICT HIJAU**.

**Bukti:** `test_core_live_session_products.py` **70 LULUS / 0 GAGAL** (HTTP nyata:
turunan platform, tolak katalog toko lain, rekonsiliasi, over-alokasi, analitik
berisi, impor→commit→rollback, cascade tanpa yatim) · layar diverifikasi lewat
browser.

**DITUNDA atas keputusan owner (butuh pembahasan proses bisnis):** F18#1 nota
kredit retur · F18#4 `generate-ar-batch`.

## 2026-08-11 — Portal Marketing F14–F17 (lingkup toko, CRUD hilang, impor tanpa AI)

**Diukur dulu:** 5 harness audit baru (`scripts/audit_marketing_*.py`) —
60/60 order · 25/25 iklan · 18/18 sesi live · 35/35 sample · 30/30 konten ·
10/10 diskon · 8/8 peluncuran tersimpan **tanpa `account_id`**; 9 rujukan yatim;
57 field teks bebas yang seharusnya menunjuk master.

**BARU (backend):** `core/marketing_account_scope.py` (SSOT lingkup toko) ·
`core/marketing_live_fields.py` (SSOT nama field sesi live) ·
`core/marketing_master_seed.py` (master host/kreator/katalog demo) ·
`core/marketing_import_schema.py` (15 jenis data impor + tujuan koleksi benar) ·
`core/marketing_import_engine.py` (baca CSV/XLSX, mapping exact→sinonim→fuzzy,
konversi rupiah/tanggal, template XLSX) · `routes/marketing_data_import.py`
(`/api/marketing/data-import/*`) · CRUD **Iklan** & **Sesi Live** (sebelumnya
hanya GET) · filter `?account_id=` pada 7 daftar + ringkasannya.

**DIPERBAIKI (cacat yang bisa ditunjuk):** ringkasan Live Selling dulu Rp 0 karena
menjumlahkan `$gmv`/`$total_orders`/`$cr_rate` yang tidak pernah ada ⇒ sekarang
Rp 512 jt · seluruh `/live/analytics/*` dulu 0/kosong karena `session_date`
datetime difilter dengan string ⇒ 7 endpoint hidup · impor dulu menulis kampanye
diskon ke `marketing_discount_campaigns` & sample ke `marketing_sample_shipments`
(dua koleksi yang tidak pernah dibaca layar) · 7 seed demo kini selalu berlingkup
toko · order demo memakai SKU katalog nyata (dulu 60/60 yatim).

**BARU (frontend):** `marketing/DataImportWizard.jsx` (stepper 6 langkah, jalur
utama tanpa AI) · `marketing/pickers/MarketingPickers.jsx` (pemilih akun/kreator/
host/item katalog; penyaringan per toko dikerjakan SERVER) ·
`marketing/AdsEntryDialog.jsx` · `marketing/LiveSessionDialog.jsx` ·
`ImportCenterModule.jsx` bertab (jalur AI lama hanya untuk buka/rollback).

**Gate:** `scripts/verify_marketing_scope.py` (INV-MKTSCOPE, 28 kode, self-test
pelanggaran sintetis MKS-22) dipasang di `scripts/gate.sh` → **21/21 HIJAU**.
**Migrasi:** `scripts/migrate_marketing_account_scope.py` (dry-run default) —
100 dipetakan, 5 akun dibuat dari nama di data, 86 baris demo tak berlingkup
dibuat ulang oleh seed yang sudah benar.

**Bukti:** `test_core_marketing_import_noai.py` 81/0 · integritas rujukan 9 → 0 ·
verifikasi layar lewat browser (wizard impor, Live Selling, Ads, Kirim Sample).
Sisa pekerjaan: `memory/HANDOFF_MARKETING_F14_F17.md` bagian "SISA PEKERJAAN".


**Permintaan owner (verbatim):** *"Rekap Harian: Beri saya satu layar berisi vendor mana saja yang
belum diisi hari ini, biar staf tidak ada yang terlewat."* Ditaruh **DI DALAM** pintu
"Input Vendor CMT", bukan pintu baru — staf sudah membukanya tiap pagi, dan dari rekap bisa
langsung klik → isi.

**Keputusan owner:** 1c checklist **per tugas** (bukan lampu hijau/merah tunggal) · 2a **semua
vendor aktif** tampil, yang tidak punya pekerjaan ditandai "tidak ada pekerjaan" · 3a data yang
**diisi vendor sendiri** ikut dihitung, sumbernya ditandai · 4a rekap = **blok pertama** layar ·
5 tambahan: lihat tanggal lain + export Excel/PDF + kirim reminder.

**Arsitektur:** SSOT tunggal `backend/core/cmt_daily_recap.py` (`TASKS`, `build_recap`,
`pending_vendor_rows`, `vendor_account_info`). Layar, berkas export, dan sasaran tombol reminder
memakai fungsi yang SAMA — mustahil "Excel bilang 5 merah, layar bilang 3". Batas hari memakai
`utils.waktu.wib_day_bounds_utc` (WIB), dan agregasi per-koleksi (`$group` by vendor) sehingga
jumlah query konstan (±10) walau vendor jadi ratusan.

**5 kolom tugas** dengan EMPAT status (sengaja empat, bukan dua): `done` ✓ · `partial` ✓+sisa ·
`pending` ✗ · `none` —. `partial` ada supaya rekap tidak mengaku "beres" ketika masih ada surat
jalan/pcs menganggur.

**🔴 BUG NYATA yang ditemukan audit & ditutup:** `received_at` pada `vendor_shipments` **tidak
pernah ditulis server**. Satu-satunya penulisnya adalah browser (`VendorReceiving.jsx:65` mengirim
`received_at: new Date()`), sehingga (1) nilainya masuk sebagai **STRING** sementara semua field
waktu lain `Date` ⇒ query rentang `{$gte: Date, $lt: Date}` **tidak pernah cocok** (Mongo
mengurutkan antar-tipe, bukan membandingkan nilai) ⇒ kolom "Terima" akan abadi ✗; (2) jamnya jam
komputer staf ⇒ TANGGAL PENERIMAAN MATERIAL bisa salah, dan tanggal itu dipakai laporan. Terbukti
empiris: **0 dokumen** punya field itu. Sekarang server yang menetapkannya pada transisi
`Sent → Received` (kiriman browser diabaikan).

**Jebakan yang ikut ditutup:**
* **Reminder rekap tidak boleh membuat vendor abadi-merah.** Tombol "kirim reminder" melahirkan
  `reminders` berstatus `pending`; kalau ikut dihitung, kolom "Balas Reminder" langsung ✗ pada hari
  yang sama dan vendor mustahil hijau ⇒ tombolnya jadi jebakan. Reminder
  `reminder_type='daily_recap'` dengan `recap_date` = tanggal rekap dikecualikan dari `waiting`
  tanggal itu; pada tanggal berikutnya tetap dihitung (reminder tak dibalas memang pekerjaan).
* **Rekap tanggal lampau tidak boleh bohong.** Kolom "menunggu" dihitung **per akhir hari itu**
  memakai stempel waktu peristiwa (`received_at` / `inspected_at` / `progress_date` /
  `dispatch_date` / `response_date`), bukan kondisi sekarang. Kalau memakai kondisi sekarang,
  supervisor yang mengecek kemarin akan melihat "tidak ada pekerjaan" untuk hari yang sebenarnya
  merah. Sisa perkiraan (didokumentasikan + tampil sebagai catatan di layar): job produksi yang
  ditutup SETELAH tanggal itu tidak lagi terhitung "job jalan", karena `production_jobs` tidak
  menyimpan kapan job ditutup.
* **`production_progress` tidak punya `vendor_id`** (menempel ke `job_id`); menyaringnya dengan
  `vendor_id` menghasilkan NOL selamanya ⇒ vendor diresolusi lewat `production_jobs`.
* Angka "selesai" untuk kolom Kirim diambil dari **`production_progress`** (log bertanggal), bukan
  `production_job_items.produced_qty` (total berjalan tanpa tanggal) — kalau memakai yang kedua,
  rekap tanggal lampau tidak akan pernah bisa benar. Keduanya terbukti sama besar pada data hidup.
* Konfirmasi kirim reminder memakai **panel di layar berisi daftar vendor + tugas yang kurang**,
  bukan `window.confirm()` — menegur vendor yang sudah setor tidak bisa ditarik kembali, jadi staf
  harus MELIHAT dulu siapa yang akan ditegur (dan panelnya bisa diuji otomatis).

**BARU:** `backend/core/cmt_daily_recap.py` · `backend/utils/cmt_recap_export.py` (Excel+PDF,
**tanpa dependensi baru**) · 3 endpoint `GET /api/cmt-override/daily-recap`,
`POST …/remind` (idempoten per vendor per tanggal), `GET …/export?format=xlsx|pdf` ·
`frontend/src/components/erp/cmt-override/CMTOverrideDailyRecap.jsx` ·
`test_core_rekap_harian.py` (POC) · `scripts/verify_rekap_harian.py` (gate **INV-REKAP**).
`list_override_vendors` di-refactor memakai `vendor_account_info` yang sama ⇒ dua layar tidak
pernah beda jawaban soal "punya akun portal".

**Klik-tembus:** setiap chip membawa `module` dari backend ⇒ klik chip ✗ "Progress Produksi"
langsung masuk mode override vendor itu DENGAN tab Progress terbuka (`pickVendor(v, moduleId)`).

**Bukti (semua dijalankan, bukan dikutip):** POC `python3 test_core_rekap_harian.py` →
**102/102 LULUS** · gate `python3 scripts/verify_rekap_harian.py` (INV-REKAP) → **22/22 HIJAU** ·
`bash scripts/gate.sh` → **18/18 PASS, VERDICT HIJAU** (gate naik 17 → 18) · testing_agent_v3
iteration_38 → backend 100% (14/14), frontend 100%, **0 bug** · verifikasi UI klik-penuh oleh main
agent → 10/10 user story PASS, termasuk rantai layar: chip ✗ "Terima Material" → Konfirmasi Terima
→ kembali ke rekap = **"Sudah diisi · 1 surat jalan diterima · diisi staf DA"** dan kolom Inspeksi
otomatis menjadi ✗ · toast "Reminder terkirim ke 2 vendor." lalu klik kedua "Tidak ada yang dikirim
— 2 vendor sudah ditegur untuk tanggal ini." · reminder terlihat di Inbox Reminder vendor ·
total tagihan CMT **2.435.000 → 2.435.000** (tidak bergeser) · drift alat uji
(`POCRK`/`__REKAPTEST__`) = 0 · AR invoice maklon yatim = 0.

**DIHAPUS:** `test_cmt_daily_recap.py` (dibuat testing agent) — redundan dengan INV-REKAP dan
**tidak membersihkan diri**: ia memanggil `POST …/remind` tanpa `vendor_ids` sehingga setiap kali
dijalankan mengirim teguran SUNGGUHAN ke semua vendor merah dan tidak pernah menghapusnya. Persis
kelas alat yang FASE 21 buang (52 skrip): penjaga yang jadi sumber sampah.

---

# [2026-08-08] PORTAL CMT OVERRIDE — "Input Vendor CMT" (staf DA mengisi atas nama vendor)

**Masalah:** vendor CMT banyak yang tidak memakai sistem; tagihan CMT dihitung dari progress,
jadi data yang tidak masuk = uang tidak bisa ditagih.

**Keputusan owner:** 1a semua 11 modul di-mirror · 2b role admin/superadmin/admin_produksi/
supervisor_produksi/ppic · 3a jejak "diinput staf DA" tercatat DAN kelihatan · 4a semua vendor
aktif di master CMT · 5a vendor ber-akun aktif tetap boleh, cukup diperingatkan.
Permintaan tambahan: pintu harus ADA JUGA di Portal Maklon.

**Arsitektur:** header `X-CMT-Override-Vendor` + SSOT `backend/core/cmt_override.py`
(resolve_override / stamp / apply_scope / effective_vendor_id). 11 komponen `engine/Vendor*.jsx`
DIPAKAI ULANG apa adanya — scoping dikerjakan backend, sehingga layar override mustahil
menampilkan angka berbeda dari yang vendor lihat.

**4 blocker ditutup:** `/vendor/dashboard` 403 keras · `/production-progress` tanpa filter vendor
· `_resolve_receiver_type` menolak `receiver_type='da'` dari staf · `PUT /reminders` hanya
menerima balasan dari role `vendor`.

**2 BUG PRE-EXISTING ikut ditutup:**
* riwayat progress portal vendor SELALU KOSONG (filter `garment_id` yang tidak pernah ditulis
  di jalur `job_item_id` — terbukti 0 dari 4 dokumen punya field itu);
* inbox reminder BOCOR ke semua vendor (scoping `role=='vendor'`, padahal role portal CMT
  `cmt_vendor`) + balasan reminder vendor CMT selalu diabaikan.

**UANG PALSU DIBERSIHKAN:** `verify_produksi_maklon_invariants.py` membuang `rahaza_ar_invoices`
lewat `notes` berisi penanda uji, padahal catatan AR ditulis jembatan maklon ⇒ tiap kali gate
jalan, 2 AR invoice maklon tertinggal sebagai PIUTANG YATIM. Terakumulasi **Rp 15.120.000
(14 dokumen)**. Pembersihan diperbaiki (berbasis FK + jaring pengaman AR yatim); 14 dokumen palsu
dihapus. AR yatim sekarang 0.

**Perbaikan akses:** `ppic` ditambahkan ke Portal Produksi & Maklon (FE portalAccess.js + BE
routes/shared.py) — sebelumnya PPIC punya izin fitur tapi tidak punya jalan ke portalnya.
Pintu nav kini bisa di-role-gate (`roles` + `navItemAllowed`) supaya tidak ada menu buntu.
Pintu "Tracking Vendor" (`prod-monitoring`) ditambahkan ke Portal Maklon: monitoring per-vendor
dulu hanya ada di Portal Produksi dan komponennya memilih domain `internal`, sehingga vendor CMT
maklon (dan badge-nya) tidak pernah terlihat.

**Bukti:** POC `test_core_cmt_override.py` 96/96 · gate baru INV-CMTOV
(`scripts/verify_cmt_override.py`) 19/19 · `gate.sh` 17/17 HIJAU · check_nav_map HIJAU ·
UI klik-penuh 11/11 user story · drift alat uji 0 · total tagihan CMT tidak bergeser
(2.435.000 → 2.435.000).

**Berkas baru:** `backend/core/cmt_override.py`, `backend/routes/cmt_override_routes.py`,
`frontend/src/components/erp/CMTOverridePortalModule.jsx`,
`frontend/src/components/erp/engine/StaffEntryBadge.jsx`,
`scripts/seed_cmt_override_demo.py`, `scripts/verify_cmt_override.py`, `test_core_cmt_override.py`.


---

## 2026-08-08 — R&D: PADANKAN UKURAN · PERINGATAN HARGA MASTER BASI (+2 bug SSOT)

Dua permintaan owner dari backlog `plan.md` §4 sesi lalu:
1. **Padankan Ukuran** — layar sekali-klik memetakan ukuran R&D "belum dipadankan" ke master
   produksi supaya alur R&D → PO tidak mentok.
2. **Peringatan Harga Basi** — tanda "harga master sudah berubah" tampil di **daftar** HPP,
   bukan cuma di dalam form Edit.

Baseline `bash scripts/gate.sh` dijalankan **sebelum** menyentuh kode. Hasilnya **MERAH 13/14**
di DB hasil bootstrap bersih — dan setelah ditelusuri, yang salah **bukan** penjaganya.

### ⚠️ Bug SSOT #1 — palet warna master tercemar warna sampah (penyebab baseline MERAH)

`rahaza_colors` di-seed **lazy** dan HANYA bila kosong, tetapi penyemaian itu dulu cuma dipasang
di endpoint **DAFTAR** (`GET /api/rahaza/colors`, `GET /api/dewi/rnd/color-options`). Pintu lain
— `utils.variant_ssot.ensure_color()`, dipakai **importir Excel** dan **promosi varian R&D →
master** — tidak menyemai. Rantai kerusakannya:

1. `ensure_color(code='NVY')` pertama membuat warna **SAMPAH** `{code:'NVY', name:'NVY',
   hex:'#CCCCCC'}`.
2. Koleksi jadi tidak-kosong ⇒ **palet 15 warna asli TIDAK PERNAH ter-seed** ⇒ dropdown warna
   R&D isinya warna abu-abu tanpa nama.
3. `'Navy'` lalu dibuat sebagai kode **KEDUA** (`NAV`) ⇒ satu warna hidup di dua kode ⇒ deteksi
   varian kembar **lolos** (inilah INV-RND-4 yang MERAH) dan SKU R&D tak akan cocok SKU FG.

Penyemaian palet dipindah ke **pintu terbawah** (`ensure_color`). Tetap idempoten & hanya saat
KOSONG, jadi warna yang **sengaja dihapus** pengguna tidak pernah dihidupkan kembali.
Dijaga gate baru **INV-COLOR** (`scripts/verify_color_palette_seed.py`, 6 invarian, dijalankan di
**DB SEMENTARA** supaya tidak menyentuh data aplikasi).

### ⚠️ Bug SSOT #2 — promosi ke produksi MENGABAIKAN `size_map` (ditemukan lewat POC, bukan mata)

Sebelum menulis fitur, dibuat POC `scripts/poc_rnd_size_promotion.py` untuk memastikan fiturnya
menutup masalah yang **nyata**. Tiga kerusakan **terbukti** (semua lewat API sungguhan):

* `'All Size'` yang **sudah** `matched→ALLSIZE` **tetap** membuat ukuran master kembar
  `'ALL SIZE'` — karena `promote_rnd_variants_to_master()` memanggil
  `ensure_size(code=<label mentah>)` dan tidak pernah melihat `size_map`.
* `'2XL'` dibuat sebagai master **kedua** walau `'XXL'` sudah ada ⇒ satu ukuran dua kode.
* `'28/30'` jadi **kode master bergaris-miring** ⇒ bocor ke SKU FG: `POCSZ…-NVY-28/30`,
  `POCSZ…-NVY-ALL SIZE`.

Artinya **layar Padankan Ukuran saja tidak cukup**. Dibuat SATU pintu pemadanan
`utils.variant_ssot.resolve_master_size()` yang dipakai **bersama** oleh `build_size_map()`
(layar) dan `promote_rnd_variants_to_master()` (promosi) — sehingga layar tidak mungkin bilang
"sudah dipadankan" sementara promosi membuat ukuran baru. Sesudah perbaikan POC melaporkan
**0 ukuran master baru** dan SKU bersih (`…-NVY-ALLSIZE`, `…-NVY-XXL`, `…-NVY-2830`).

`ensure_size()` sekarang **selalu membersihkan kode** (alfanumerik saja); `name` tetap menyimpan
tulisan aslinya. `promote_…` mengembalikan `sizes_created[]` supaya penambahan master ukuran
tidak lagi terjadi diam-diam.

### Padankan Ukuran — `routes/dewi_rnd_size_mapping.py` (ditulis ulang + DIDAFTARKAN)

Sisa sesi lalu: berkasnya **sudah ada** tapi **tidak pernah di-import** di `routes/dewi_rnd.py`
⇒ seluruh endpoint-nya **HTTP 404** (POC H4). Sesi lalu berhenti persis di titik itu.

* `GET  /api/dewi/rnd/size-mapping` — ringkasan + **saran** padanan (+ `?style_id=`)
* `POST /api/dewi/rnd/size-mapping/apply` — satu/banyak label (`size_id` atau `create_new`)
* `POST /api/dewi/rnd/size-mapping/auto` — **sekali klik** (`create_missing` opsional)

Tiga perbaikan penting dari draf sesi lalu:

1. **Bug `Query` default.** `size_mapping_auto` memanggil handler `size_mapping_overview`
   langsung dari Python, jadi `limit` menerima objek `Query(...)` FastAPI (bukan `int`) →
   `.to_list(Query)` pecah. Sekarang ada fungsi biasa `_overview(db, style_id, limit)`.
2. **Membaca DUA sumber label** — `dewi_rnd_styles.size_list` **dan** `dewi_rnd_variants.sizes`.
   Yang kedua WAJIB: varian hasil impor Excel (115 buah) labelnya bisa TIDAK ADA di `size_list`
   mana pun. **Terbukti:** `ONESET` dan `TOP` hanya muncul dari varian impor
   (`from_variants=true`, `from_size_list=false`). Kalau hanya membaca `size_list`, style hasil
   impor tetap mentok — itu setengah perbaikan.
3. **Alias ditulis ke master** (`rahaza_sizes.aliases[]`) supaya pemadanan berikutnya otomatis
   kena, tanpa tabel alias terpisah.

`size_list` style **TIDAK PERNAH** diubah — kebijakan **B1** utuh (dijaga SM-4).
Alias baku lapangan (`SIZE_ALIAS_GROUPS`: `2XL⇄XXL`, `3XL⇄XXXL`, `All Size⇄Free Size`, …)
sengaja **pendek & eksplisit**, bukan pencocokan "mirip-mirip": salah menebak ukuran = salah
potong kain = uang hilang.

### Peringatan harga master basi di DAFTAR HPP — `routes/dewi_rnd_hpp.py`

Definisi "basi" diekstrak jadi **satu** fungsi `_stale_lines_for_doc()` yang dipakai **bersama**
oleh `/stale-check` (form) dan `GET /hpp-calculator` (daftar), supaya daftar dan form tidak
mungkin menjawab berbeda untuk dokumen yang sama.

Field BARU per baris daftar: `stale_count`, `stale_delta_total`, `stale_checked_lines`,
`stale_lines[]` (`unit_cost_snapshot`, `unit_cost_now`, `delta`, `direction`,
`line_cost_saved`, `line_cost_now`). `?with_stale=false` untuk mematikan.

**Performa:** `_cost_one_line(…, cache)` memoisasi **hanya** pencarian master material —
aritmetikanya tidak disentuh sama sekali. Tanpa memo, satu kali membuka daftar bisa menembak
ribuan query (tiap baris menembak `rahaza_materials` 3× + `dewi_rnd_materials` 2×).

**UANG:** baris `manual` dan dokumen HPP **LAMA** (dibaca manual oleh `legacy_cost_lines`) tidak
pernah ditandai, dan **tidak ada satu angka tersimpan yang berubah** — dijaga ST-4 yang
membandingkan `direct`/`hpp`/`jual`/`line_cost` sebelum vs sesudah harga master diubah.

### Seeder R&D dilengkapi — `routes/dewi_rnd_overview.py`

Seeder dulu hanya menulis `styles[].variants[]` (bentuk LAMA tertanam di dokumen style) dan
**tidak pernah** mengisi `size_list`, `dewi_rnd_variants`, atau `dewi_rnd_hpp`. Akibatnya di DB
bersih layar **Varian**, **Padankan Ukuran**, dan **HPP** semuanya KOSONG — fiturnya tidak bisa
dipakai maupun dinilai tanpa mengetik data manual dulu.

`POST /api/dewi/rnd/seed?reset=true` sekarang juga membuat 7 `size_list` yang **sengaja
bercampur** (persis master `S/M/L/XL`, butuh alias `2XL`, dan benar-benar baru `28/30`,
`32/34`, `36/38`), 13 varian nyata lewat `_norm_sizes`/`_resolve_color`, dan 2 HPP (satu hybrid
Master+Manual, satu bergaya lama) yang dihitung lewat `compute_cost_lines`/`_calculate_hpp` —
fungsi yang SAMA dipakai endpoint sungguhan, jadi angkanya bukan karangan seeder.
`reset=true` ikut membersihkan varian & HPP demo (tetap idempoten).

### Frontend

* **`RnDSizeMappingModule.jsx` (BARU)** — tab **"Padankan Ukuran"** di hub `rnd-design-hub`
  (tab, bukan pintu sidebar ⇒ gate NAVIGASI tetap hijau). 4 kartu ringkasan, penjelasan
  **kenapa** ini penting, tombol **"Padankan Semua"**, saklar "boleh buat ukuran baru di
  master", pilih massal, dropdown master per baris + input kode, keadaan **all-clear**, dan
  panel transparansi "N ukuran sudah terhubung ke master".
* **`RnDHPPCalculatorModule.jsx`** — kolom baru **"Harga Master"** + banner ringkasan di atas
  tabel; badge bisa diklik → langsung membuka modal Edit HPP-nya. Dokumen tanpa baris master
  menampilkan `—`, bukan peringatan palsu.

### Bukti

`scripts/gate.sh` **16/16 HIJAU** (baseline MERAH 13/14) · `verify_rnd_size_mapping_stale.py`
**13/13** (gate baru INV-RND2) · `verify_color_palette_seed.py` **6/6** (gate baru INV-COLOR) ·
`verify_rnd_invariants.py` **11/11** · `verify_rnd_f1_f4.py` **39/39** ·
`backend/techpack_importer_test.py` **99/99** · `poc_rnd_size_promotion.py` 3 hipotesis
kerusakan TERBUKTI sebelum perbaikan, **NOL** sesudah · testing agent iteration_36 backend
**14/14**, 0 bug kritis/minor · verifikasi UI klik-penuh oleh main agent **6/6 alur**.

### Catatan jujur

* Testing agent menjalankan auto-mapping di tahap **backend** lebih dulu, sehingga saat masuk
  UI seluruh label sudah habis dan tabelnya kosong ⇒ alur klik (padankan per baris, dropdown,
  pilih massal, sekali-klik, peringatan saat "buat baru" dimatikan) **tidak tersentuh** olehnya.
  Enam alur itu diverifikasi sendiri lewat Playwright, lalu data uji dipulihkan.
* Pada clone segar, `yarn install` bisa **di-skip** karena marker `.bootstrap_cache/fe.md5` ikut
  tersalin dari repo padahal `node_modules` bawaan template belum berisi paket repo ini. Sesi
  ini kena: `@simplewebauthn/browser` hilang ⇒ `yarn build` gagal dengan "Module not found".
  Jalan keluar: `cd /app/frontend && yarn install` lalu `bash scripts/rebuild_frontend.sh`.
* Ukuran master hasil "buat baru" memakai `order_seq=50` (semua sama) ⇒ urutan tampilnya
  mengikuti abjad, bukan urutan ukuran sebenarnya. Belum ada layar untuk mengurutkan ulang.


## 2026-08-07 (lanjutan #3) — R&D: WARNA MULTI · UKURAN BEBAS · TECH PACK KUAT · HPP HYBRID

Lingkup diambil dari `memory/PROPOSAL_RND_WARNA_UKURAN_TECHPACK_HPP.md` (F1–F4). Owner menjawab
**"jalankan rekomendasi"**, jadi semua opsi yang masih terbuka di §7 proposal diambil sesuai
rekomendasi agent — tanpa menunggu jawaban lagi:

| Opsi §7 | Yang dipakai |
|---|---|
| Pemadanan ukuran | **B1** — ukuran tetap teks BEBAS, dipadankan otomatis ke `rahaza_sizes` bila namanya sama (`size_id` = petunjuk opsional), sisanya diberi badge "belum dipadankan" |
| Override harga master | **D1** — boleh, **alasan WAJIB**, tercatat + snapshot harga master |
| Urutan fase | **F1 → F2 → F3 → F4** |
| Tech Pack | **UI dan data**, keduanya |
| Warna material R&D | ikut di **F1** |

Baseline `bash scripts/gate.sh` dijalankan **sebelum** menyentuh kode (13/13 HIJAU) supaya
kegagalan lama tidak salah dituduhkan ke sesi ini.

### F1 — Warna multi lewat FAN-OUT (nol migrasi)

`routes/dewi_rnd_colors.py` (BARU):
* `GET/POST /api/dewi/rnd/color-options` — proxy tipis ke master `rahaza_colors`. POST menulis
  warna baru **ke master itu** (bukan koleksi bayangan) lalu langsung bisa dipilih ⇒ **tidak
  bolak-balik menu** (keputusan owner #2). Kode/nama kembar ditolak 409 dengan pesan yang
  menyebut warna pemilik kode tersebut. Role eksternal (vendor/klien) ditolak 403.
* `POST /api/dewi/rnd/variants/bulk` — **FAN-OUT**: satu request `colors[] × sizes[]`
  (+ `matrix` untuk override SKU/qty per sel) → **N dokumen** `dewi_rnd_variants`.
  Bentuk data TIDAK berubah ⇒ **nol migrasi**, semua pembaca lama aman, butirannya sama
  dengan SSOT `rahaza_model_variants`.
* `GET /variants/sku-audit` + `POST /variants/{id}/fix-sku` — SKU lama **TIDAK** ditulis ulang
  otomatis (bisa sudah tersebar); disediakan laporan + tombol perbaiki **per baris**.

**Dua bug proposal §2.5 ditutup:**
1. **Urutan SKU R&D terbalik.** `autoGenSKU()` dulu `{STYLE}-{SIZE}-{COLOR}` dan memakai 3 huruf
   **NAMA** warna. Sekarang memakai `utils/variant_ssot.build_variant_sku()` ⇒
   `{STYLE}-{COLOR_CODE}-{SIZE}` dengan **KODE** master ⇒ SKU R&D bisa cocok dengan SKU FG gudang.
2. **Varian kembar tidak dijaga.** `create_variant`/`update_variant`/`bulk` kini menolak 409 dan
   membandingkan lewat **master warna** (color_id → kode → nama CI), bukan teks bebas.

**Jebakan data yang ditemukan sendiri (TIDAK ada di proposal — wajib dilaporkan):**
Layar R&D lama menulis **HEX** ke field `color_code` (`color_code: '#ffffff'` di `emptyForm`),
padahal SSOT memakai `color_code` sebagai **KODE** master (`NVY`). Akibatnya
`promote_rnd_variants_to_master()` bisa membuat warna master **berkode `#1B2A5B`** — kode sampah
di master yang dipakai produksi & gudang. Sekarang dokumen baru menulis **keduanya secara
eksplisit** (`color_code` = KODE, `color_hex` = HEX), pembaca lama tetap aman lewat fungsi bantu
`hex_of_variant()`, dan `utils/variant_ssot.py` menolak nilai hex sebagai kode warna.

`dewi_rnd_materials.colors[]` ditambahkan (aditif, default `[]`) untuk permintaan "warna bahan".

**Frontend:** `RnDVariantModule.jsx` ditulis ulang mengikuti Gambar 1 proposal (baris warna N buah,
opsi **"+ Warna baru…"** dengan form inline + "Simpan ke Master", matriks **warna × ukuran**,
banner **"SKU tidak sesuai SSOT"** + tombol perbaiki per baris). `RnDColorPicker.jsx` (BARU)
menyediakan `useColorOptions` / `ColorSelect` / `ColorMultiSelect` yang dipakai ulang di
Riset Material dan Tech Pack.

### F2 — Ukuran BEBAS per style (kebijakan B1)

`routes/dewi_rnd_sizes.py` (BARU) — `GET/PUT /api/dewi/rnd/styles/{id}/size-list`.
`DEFAULT_SIZES = ['XS','S','M','L','XL','XXL','2XL','3XL']` dikeluarkan dari
`RnDVariantModule.jsx:22` dan menjadi **data** `dewi_rnd_styles.size_list` — boleh apa saja
(`"All Size"`, `"28/30"`). Kembar dibuang, urutan dijaga, daftar kosong ditolak 400.
`size_map` menyimpan petunjuk `size_id` (B1) dan menandai yang belum dipadankan.
`size_range` **dihitung**, `base_size` **dipilih dari daftar** ⇒ tumpang tindih §2.2 hilang.
Style lama tanpa `size_list` tetap mendapat 8 ukuran bawaan (fallback ⇒ nol migrasi).

### F3 — Tech Pack: 4 sambungan longgar ditutup

`utils/rnd_techpack.py` (BARU) + `_normalize_techpack_payload()` menjadi **satu pintu** untuk
POST maupun PUT tech pack:

| Kode | Isi |
|---|---|
| C1 | Baris BOM dapat `master_linked` + `master_link_note`; dokumen dapat `bom_unlinked_count`. UI: dropdown master jadi **kolom pertama**, baris tanpa master berlatar **merah** + peringatan + badge hitungan ⇒ HPP yang salah jadi **kelihatan**, tidak diam-diam |
| C2 | `fabric_consumption.size` → **dropdown** dari `size_list`; yang menyimpang ditandai `size_off_list` |
| C3 | `size_columns` → `[{col_id,label}]` **stabil**; `measurements[].values` dikunci `col_id` |
| C4 | `colorways[]` tech pack (rujuk master warna) |
| C5 | Kolom warna pada `fabrics[]` & `bom_items[]` |

**C3 adalah yang paling berbahaya dan sekarang terbukti tertutup.** Dulu `values` dikunci STRING
nama kolom, jadi mengganti nama kolom (`XL` → `EXTRA L`) membuat **seluruh nilai kolom itu yatim
tanpa peringatan** — spesifikasi ukuran jahit lenyap diam-diam. Migrasinya **idempoten** dan
**tidak membuang apa pun**: bentuk lama disimpan di `values_legacy`, kunci yang kolomnya sudah
hilang disimpan di `orphan_values` (bukan dihapus), dan `measurements_stats
{values_in, values_out, orphans}` membuat jumlahnya bisa **dibuktikan** gate.
Tiga bentuk lama diterima tanpa kehilangan: `values` ber-`col_id`, `values` ber-NAMA kolom, dan
baris pipih `{point, S:'50', M:'52'}`.

Kolom measurement tech pack **BARU** kini default = `size_list` style (§C "satu sumber"), tapi
tech pack hasil impor Excel yang memakai kategori `STANDAR/JUMBO` **tidak** ditimpa.

> ⚠️ **Jebakan yang terbukti (ditemukan gate, bukan mata):** klien mengirim balik
> `orphan_values`, tetapi normalizer versi pertama **membuangnya** — artinya nilai kolom yang
> dihapus akan hilang pada penyimpanan BERIKUTNYA. Ditemukan oleh INV-RND-2 lalu ditutup.

### F4 — HPP hybrid: sumber biaya PER BARIS (bukan saklar global)

Akar keluhan owner: `use_bom` adalah saklar **semua-atau-tidak**, sehingga **mustahil** sebagian
baris dari master dan sebagian custom. Sekarang `dewi_rnd_hpp.cost_lines[]` dengan
`source ∈ {master, techpack, manual}` per baris dan `total = Σ SEMUA baris`.

**Cara menjaga UANG lama tidak bergeser:** logika harga per baris **diekstrak apa adanya** dari
`_material_cost_from_bom()` menjadi `_cost_one_line()`; mode `use_bom` lama memanggil fungsi yang
sama, jadi angkanya tidak mungkin berubah karena refactor ini. Field `use_bom` **tetap disimpan**.
`legacy_cost_lines()` membaca dokumen lama sebagai "semua Techpack" (bila `use_bom`) atau "semua
Manual", **tanpa** menghitung ulang `hpp_total` tersimpan.

**Kebijakan D1 ditegakkan di backend:** override harga master tanpa `override_reason` ⇒ **400**,
pesannya menyebut nomor & nama barisnya. Snapshot `unit_cost_master` disimpan supaya
`GET /hpp-calculator/{id}/stale-check` bisa bilang "harga master sudah berubah, perbarui?" —
angka tersimpan **tidak pernah** diubah otomatis.

Endpoint baru: `POST /hpp-calculator/cost-lines/from-techpack`,
`GET /hpp-calculator/cmt-suggestions` (akhirnya memakai
`dewi_maklon_buyer_catalog.default_cmt_price` yang sudah lama ada tapi tidak pernah dipakai HPP),
`GET /hpp-calculator/{id}/stale-check`.

`RnDHPPCalculatorModule.jsx` ditulis ulang: tabel baris biaya **lebar penuh** (Sumber ▾ /
Referensi master / Qty / Harga master / Harga dipakai / **timpa harga** + Alasan wajib / Biaya),
tombol **Tarik dari Techpack BOM** · **Baris Master** · **Baris Manual**, banner harga master
basi + "Pakai harga master terbaru", saran CMT dari master, total hidup. Mode lama (kain +
aksesoris) tetap ada dan hanya tampil bila belum ada baris biaya.

### Gate baru: INV-RND (kriteria "kalau hilang, UANG/DATA rusak tanpa ada yang tahu")

`scripts/verify_rnd_invariants.py` (BARU) dipasang di `scripts/gate.sh` sebagai
**"DATA/UANG — R&D: ukuran tech pack, SKU SSOT, HPP hybrid (INV-RND)"** — 9 invarian:
ganti nama kolom tidak menghilangkan nilai · hapus kolom tidak membuang nilai · SKU SSOT ·
varian kembar ditolak · HPP hybrid = Σ semua baris · override wajib beralasan · dokumen HPP lama
tidak bergeser · baris BOM tanpa master ditandai. Datanya dibersihkan sendiri setelah jalan.

### Bug KETIGA yang ketemu saat pengujian pada DATA SUNGGUHAN (bukan data uji)

Setelah `techpack_importer_test.py` mengimpor sampel Excel asli (19 style · 78 tech pack ·
**115 varian**), `GET /api/dewi/rnd/variants/sku-audit` langsung **HTTP 500**:

```
File "/app/backend/routes/dewi_rnd_colors.py", line 396, in variants_sku_audit
AttributeError: 'str' object has no attribute 'get'
```

Sebabnya: **`dewi_rnd_variants.sizes` punya DUA bentuk di database yang sama.**
Importir Excel menulis daftar **STRING** (`['S','M','L']`), sedangkan layar Varian menulis
daftar **DICT** (`[{size, sku, qty_plan}]`). `utils/variant_ssot.promote_rnd_variants_to_master`
sudah lama menangani keduanya (`scode = s if isinstance(s, str) else …`), tapi pembaca baru tidak.

Ditutup dengan helper `size_rows(variant)` di `dewi_rnd_colors.py` yang dipakai `sku-audit`
**dan** `fix-sku`; `fix-sku` sekaligus menaikkan baris bentuk-string menjadi objek ber-SKU
kanonik. Frontend juga diperbaiki (`sizeRows()` di `RnDVariantModule.jsx`): sebelumnya
`v.sizes.filter(s => s.qty_plan > 0 || s.sku)` membuat **seluruh 115 varian hasil impor tidak
menampilkan chip ukuran sama sekali**; sekarang tampil, dan yang belum punya SKU diberi
keterangan jujur **"SKU belum dibuat"** (amber) — bukan disembunyikan.

Regresi dijaga **INV-RND-9 / 9b**: `sku-audit` dijalankan TANPA filter style, jadi gate
memaksa endpoint itu tahan SEMUA bentuk `sizes` yang benar-benar ada di database.
Hasil pada data impor: **115 varian diperiksa · 0 SKU tidak sesuai · 0 warna di luar master**
(membuktikan juga bahwa perbaikan hex-vs-kode di §F1 bekerja: 60 warna master, semua berkode
huruf, tidak ada `#RRGGBB`).

### Dua berkas uji lama yang ternyata sudah usang (ikut diperbaiki)

* `backend/techpack_importer_test.py` menunjuk URL preview lama (`rnd-cockpit-hub…`) yang kini
  **404**, jadi seluruh suite berhenti di TEST 1. `BASE_URL` sekarang diresolusi dari
  env `BASE_URL` → `frontend/.env` → `localhost:8001`.
* Test 9 memaksa `PUT /styles/{id}` dengan `status: approved_for_launch`, padahal status siklus
  hidup **dikunci** (hanya lewat `submit-for-review` / `owner-approve`) sejak sesi 2026-08-07.
  Diperbaiki memakai pintu keputusan yang benar. Efek sampingnya bagus: TEST 10–12 (varian
  kanonik · FG `code == SKU` · SOP dari tech pack) yang selama ini **di-skip** sekarang benar-benar
  jalan. Hasil: **99/99 (100%)** — naik dari 74/75 dengan 1 merah.
* Assertion `size_columns == ["STANDAR","JUMBO"]` diperbarui ke bentuk `[{col_id,label}]`
  + pemeriksaan baru bahwa `values` dikunci `col_id` dan `values_in == values_out == 6`.

### Importir Excel ikut dinormalkan

`routes/dewi_rnd_techpack_import.py` menulis **langsung** ke DB (tidak lewat endpoint
`/tech-packs`), jadi ia melewati normalizer. Akibatnya tech pack hasil impor menyimpan bentuk
LAMA (kolom string, nilai berkunci nama kolom) — persis bentuk yang membuat nilai ukuran yatim.
Sekarang importir memanggil `normalize_size_columns()` + `normalize_measurements()` juga.

### Bukti

| Alat | Hasil |
|---|---|
| `bash scripts/gate.sh` | **14/14 HIJAU** (13 lama + INV-RND baru) · 43 dtk |
| `python scripts/verify_rnd_f1_f4.py` | **39/39 HIJAU** (dijalankan 2× berurutan → stabil) |
| `python scripts/verify_rnd_invariants.py` | **9/9 HIJAU** |
| Verifikasi UI lewat browser | **25/25 PASS** — termasuk aritmatika HPP diperiksa angka per angka (Σ baris `400+0+3.500+600 = 4.500` = Total = "Biaya Material"; Direct `22.500`; HPP `24.750`; Harga jual `35.357`) dan dokumen HPP lama tetap `111.000 / 122.100` |
| `bash scripts/rebuild_frontend.sh` | bundle statis di-rebuild, frontend HTTP 200 |

**Catatan kejujuran:** testing agent (iteration_35) **tidak berhasil** menyelesaikan alur UI —
ia tersangkut karena dropdown aplikasi ini bukan `<select>` native (`SmartNativeSelect`) sehingga
`select_option()` gagal, plus navigasi hash-based. Karena itu seluruh 25 pemeriksaan UI di atas
dikerjakan **manual lewat Playwright oleh main agent**, dan pola interaksi yang benar
(`X-trigger` → `X-list`) sudah dicatat di `test_result.md` untuk sesi berikutnya. Testing agent
juga melaporkan skrip verifikasi "34/39" — penyebabnya **nyata**: kode warna uji hanya memakai
2 digit sehingga bentrok antar-run; sudah diperbaiki memakai UUID dan kini 39/39 berulang.

### Berkas baru / berubah

BARU: `backend/routes/dewi_rnd_colors.py` · `backend/routes/dewi_rnd_sizes.py` ·
`backend/utils/rnd_techpack.py` · `frontend/src/components/erp/RnDColorPicker.jsx` ·
`scripts/verify_rnd_f1_f4.py` · `scripts/verify_rnd_invariants.py` ·
`scripts/cleanup_rnd_test_data.py`

BERUBAH: `backend/routes/dewi_rnd.py` (registrasi) · `dewi_rnd_design.py` (anti-kembar + warna
master) · `dewi_rnd_styles.py` (`size_list`) · `dewi_rnd_materials.py` (`colors[]`) ·
`dewi_rnd_hpp.py` (tech pack normalizer + HPP hybrid) · `backend/utils/variant_ssot.py`
(tolak hex sebagai kode warna) · `frontend/.../RnDVariantModule.jsx` ·
`RnDTechPackModule.jsx` · `RnDHPPCalculatorModule.jsx` · `RnDMaterialsTab.jsx` ·
`Modal.jsx` (ukuran `3xl`, aditif) · `scripts/gate.sh` · `plan.md` · `test_result.md`

---

## 2026-08-07 (lanjutan #2) — KEGAGALAN SENYAP DITUTUP (stok & uang), TANGGAL IKUT WIB

Titik berhenti sesi lalu: dua edit di `core/quarantine.py` (mengubah `except Exception: pass`
menjadi `logger.error` + menyimpan `availability_blocked` di dokumen karantina). Kedua edit itu
**sudah tersimpan dan lolos compile**, jadi sesi ini melanjutkan dari sana — Prioritas 1, 2, dan 3
pada daftar backlog.

### Temuan pertama: DUA dari tiga prioritas TERNYATA SUDAH SELESAI (dokumennya usang)

Audit ulang dengan AST + grep, bukan membaca dokumen:

| Backlog | Klaim dokumen | Kenyataan yang diukur |
|---|---|---|
| P1 `except Exception: pass` | "17 titik, 6 di jalur stok & uang" | **5 titik `core/` SUDAH difix** sesi lalu (`stock_service`, `accessory_stock`, `stock_reconcile`, `quarantine` ×3). Tetapi audit yang LEBIH LEBAR (bukan hanya `pass`, juga `continue`/`return None` senyap) menemukan **65 handler senyap** di kode produksi, **14 di antaranya pada jalur stok/uang** — jauh lebih banyak dari yang tercatat |
| P2 penomoran balapan | "44 titik `count_documents()+1` belum diadopsi" | **SUDAH SELESAI SEMUA 44.** Setiap titik memakai `gen_prefixed_number` (komentar `RC-5 fix`), dan `ensure_unique_number_indexes()` sudah dipanggil di `server.py:1046`. Gate "UANG — nomor dokumen tak boleh kembar saat balapan" HIJAU |
| P3 datetime naive | "27 titik" | **47 titik** (`datetime.now()` polos ×46 + `datetime.utcnow()` ×1) |

### Temuan kedua: GATE MERAH dari bootstrap bersih — dan penjaganya sendiri yang bug

Baseline `bash scripts/gate.sh` pada database yang baru di-bootstrap: **MERAH, INV-4**
("stok FG salah / di luar SSOT stok"). Buktinya menunjukkan `lokasi_karantina_yang_diperiksa: null`
sementara 10 pcs reject duduk di lokasi lain.

Akarnya BUKAN produk: `scripts/verify_produksi_maklon_invariants.py` mengambil `q_loc`
**SEBELUM** QC dijalankan, padahal `core.quarantine.get_quarantine_location_id()`
**MENG-AUTO-PROVISION** lokasi karantina saat pertama dipakai. Di DB bersih lokasi itu belum ada
⇒ `q_loc = None` ⇒ reject terbaca sebagai "stok nyasar". Dibuktikan: INV-5 ("10 pcs reject masuk
karantina") LULUS di run yang sama, dan menjalankan ulang guard yang sama langsung **19/19 PASS**.
Artinya "gate 13/13 HIJAU" di dokumen lama **tidak pernah reproducible dari bootstrap bersih** —
justru kondisi yang dihadapi setiap sesi baru. Lokasi karantina kini di-resolve ULANG di titik
pemeriksaan.

### P1 — kebijakan BERTINGKAT (keputusan owner)

**Gagal keras (tolak transaksi)** untuk yang MENGUBAH ANGKA:

1. `routes/rahaza_fg_matrix.py` — release reservasi FG. Alasan lama (*"release harus tetap
   menandai released walau stok sudah bergeser"*) **keliru**: "stok bergeser" TIDAK melempar
   exception (`release_material` hanya melepas lebih sedikit), jadi yang tertangkap di `except`
   hanyalah error nyata. Efeknya reservasi hantu: baris ditandai `released` tetapi
   `reserved_quantity` TETAP ⇒ barang ada fisik, `available` terpotong selamanya, tanpa dokumen
   apa pun untuk melepasnya. Sekarang 500 + reservasi TIDAK diubah. Pelepasan SEBAGIAN dicatat
   (`release_shortfall`) dan dikembalikan sebagai `warning`.
2. `routes/rahaza_orders.py` — item pesanan dengan qty bukan angka dulu **dibuang diam-diam**
   ("BUG-002 fix … hindari 500"). Menghindari 500 benar, caranya salah: permintaan pelanggan
   LENYAP ⇒ order kurang ⇒ produksi kurang ⇒ tagihan kurang, tanpa jejak. SSOT baru
   `_clean_items()` (dipakai create & update): baris **benar-benar kosong** tetap dilewati (baris
   template UI), baris yang **sudah diisi** tetapi tidak lengkap / qty bukan angka / qty ≤ 0 →
   **400 yang menyebut NOMOR BARIS**. Uji `tests/pilot_prod_orders_test_v2.py` TC-30b yang
   mengabadikan perilaku lama ikut dikoreksi.
3. `routes/dewi_maklon_bom_templates.py` — `_compute_total_cost` dulu melewati baris material
   yang angkanya tidak sah ⇒ biaya baris itu dihitung **NOL** ⇒ `total_cost_per_pcs` lebih murah
   dari kenyataan, dan angka itu dasar quote/HPP maklon ⇒ bisa **menjual di bawah biaya**.
   Sekarang 400 dengan menyebut nama materialnya.

**Catat + tampilkan** (laporan/alert; melewati baris rusak tetap benar supaya satu dokumen kotor
tidak mematikan seluruh laporan) — SSOT baru **`utils/data_quality.py` (`SkipTracker`)**. Setiap
baris yang dilewati kini tercatat di log DAN dikembalikan lewat field `data_quality`
(bentuknya selalu sama, juga saat nol):

* `routes/rahaza_finance.py` — daftar AR jatuh tempo + `ar_aging`.
* `routes/dewi_maklon_billing.py` — ringkasan tagihan + `reports/aging`.
* `services/management_alerts.py` — peringatan deadline PO & piutang.
* `routes/dewi_client_portal.py` · `routes/rahaza_ai.py` · `routes/analytics_ai.py` ·
  `routes/rahaza_grn_qc.py`.

Tiga cacat tambahan ketemu saat mengerjakannya:

* **`except ValueError` TIDAK menangkap `TypeError`.** Bila `due_date` bernilai `null` (bentuk nyata
  di data lama), `date.fromisoformat(None)` melempar TypeError ⇒ endpoint **500**, bukan "satu baris
  dilewati". Terjadi di dua tempat di `dewi_maklon_billing.py`.
* **Ember aging menyembunyikan uang.** `ar_aging` memaksa `days_overdue = 0` untuk tanggal rusak ⇒
  piutang yang mungkin lewat berbulan-bulan **dilaporkan sebagai "current"**. Aging maklon lebih
  buruk: barisnya hilang dari buckets DAN dari total. Ember jujur **`tanpa_jatuh_tempo`**
  ditambahkan di keduanya (total tidak berubah, labelnya benar).
* **KPI naik karena data rusak.** Di `analytics_ai.py` WO bertanggal rusak mengecilkan PENYEBUT
  ketepatan waktu ⇒ persentase naik. Angka itu dikirim ke LLM, jadi kesimpulan AI ikut salah.
  Jumlah WO yang tak bisa dinilai sekarang disebut eksplisit di prompt.

Sisanya dicatat tanpa mengubah alur: `routes/dewi_wh_returns.py` (gagal sinkron ke Marketing ⇒
tombol "Terbitkan Credit Note" tak pernah aktif ⇒ retur pelanggan menggantung; kini ditandai
`mkt_sync_ok=false` + `mkt_sync_error`), `routes/buyer_shipment.py` (baris stok ber-qty bukan angka
⇒ stok tampak kurang ⇒ keluhan "stok jelas ada tapi katanya kurang"), `routes/dewi_cmt_permak.py`
(deadline rusak ⇒ permak **tidak pernah** ditandai H+3 ⇒ luput dari daftar kejar),
`utils/counters.py` (`except (ValueError, Exception)` — `Exception` sudah mencakup `ValueError`;
format kode master owner ditolak diam-diam sehingga SKU baru tetap pola lama).
`utils/email_sender.py` DIPERIKSA dan **dibiarkan**: `server.quit()` gagal setelah `sendmail`
berhasil memang bukan kegagalan kirim.

### P1 UX — kegagalan blokir jadi BISA DITINDAK, bukan hanya tercatat

Menyimpan `availability_blocked` saat pembuatan **tidak cukup**: dokumen karantina LAMA tak punya
field itu, dan blokir bisa hilang SETELAHNYA (jalur lain memanggil release/unreserve). Jadi
kebenarannya diambil dari **SSOT stok**, bukan dari flag:

* `core/quarantine.availability_audit()` — untuk setiap (material, lokasi karantina), total
  `remaining_qty` item terbuka HARUS tertutup penuh oleh `reserved_quantity`. Selisihnya = qty
  barang REJECT yang saat ini **masih terhitung tersedia**.
* `list_items()` menghitung `availability_blocked` per item dari audit itu (flag saat pembuatan
  tetap dibawa sebagai `availability_blocked_at_intake` untuk audit), plus filter `needs_action`.
* `summary()` menambah `unblocked_items` / `unblocked_qty` / `unblocked_groups`.
* **`POST /api/wms/quarantine/{id}/retry-block`** — tanpa ini daftar "perlu tindakan manual" cuma
  pengumuman; perbaikan harus lewat database.
* UI `QuarantineModule.jsx`: **banner merah** (jumlah + qty + material terdampak), **tab
  "Perlu Tindakan Manual"** berlencana, **badge per baris** (`TIDAK TERBLOKIR` / `terblokir`), dan
  tombol **"Coba Blokir Ulang"**.

Dibuktikan hidup: sabotase `reserved` 250→50 pada item karantina ⇒ `unblocked_items: 1`,
`unblocked_qty: 200`, filter `needs_action` memunculkan barisnya dengan
`availability_blocked_at_intake: true` (**bukti audit menangkap drift yang flag saja akan
LEWATKAN**) ⇒ retry-block memblokir 200 unit ⇒ kembali `unblocked_items: 0`.

### P3 — tanggal operasional ikut WIB (SSOT `utils/waktu.py`)

Jam sistem container **UTC**, tetapi tanggal kalender dipakai untuk periode & penomoran. Semua 47
titik salah pada jendela **07 jam setiap hari** (00:00–07:00 WIB). Yang paling merusak:

* `utils/counters.render_format` — token `{YYYY}{MM}{DD}` SEMUA nomor dokumen. Dibuktikan:
  pada 2025-12-31T17:30Z (= 2026-01-01 00:30 WIB) hasilnya kini `INV-20260101-` (dulu
  `INV-20251231-` ⇒ salah TAHUN).
* `utils/doc_numbering.py` — token nomor + bucket reset counter (yearly/monthly).
* Saldo cuti & payroll: `datetime.now().year` → `wib_year()` (`rahaza_leave.py`,
  `rahaza_leave_balances.py`, `services/leave_service.py`).
* Penomoran periode `%Y%m` klaim biaya / perjalanan / per-diem, dan PDF yang mencetak "…WIB"
  memakai jam UTC (selisih 7 jam pada dokumen yang diarsipkan).

`utils/waktu.py` sekarang satu-satunya pengertian waktu Jakarta: `now_utc` (penyimpanan tetap UTC
aware), `now_wib`, `today_wib`, `wib_year`, `wib_date_str`, `fmt_wib`, `wib_stamp`,
`wib_day_bounds_utc` (batas hari WIB dalam UTC untuk query rentang). Dua definisi lama
(`utils/employee_identity.WIB` offset tetap, `core/accessory_valuation._jakarta_date_str`)
kini menunjuk ke SSOT ini. Transform tercatat di
`scripts/migrations/2026_08_07_p3_naive_datetime_to_wib.py`.

### Temuan SETELAH testing agent (3 bug tambahan, 2 di antaranya UANG)

Testing agent melaporkan 37/40 backend + 100% frontend, 0 bug kritis, dengan 2 "minor". Menelusuri
kedua minor itu justru membuka **tiga bug yang lebih serius** dari yang dilaporkan:

1. **`GET /api/rahaza/ar-aging` sebenarnya memanggil WRITE-OFF PIUTANG MACET.**
   Testing agent hanya bisa bilang *"SKIPPED — requires iid parameter"*. Penyebabnya:
   `@router.get("/ar-aging")` adalah **dekorator MENGGANTUNG** — berdiri sendiri tanpa fungsi di
   bawahnya, dipisahkan baris kosong + blok komentar. Python **menumpuk** dekorator seperti itu ke
   `def` berikutnya, jadi dekorator itu menempel ke `write_off_bad_debt`. Akibatnya: (a) `GET /ar-aging` menjalankan operasi yang **memposting
   jurnal GL** (Dr Beban Piutang Macet / Cr Piutang) lewat **metode GET**, dan karena path
   `/ar-aging` tak punya `{iid}` FastAPI menjadikan `iid` query parameter WAJIB — itulah "minta
   iid" yang dilihat tester; (b) fungsi `ar_aging()` yang sesungguhnya **TIDAK PERNAH terdaftar**
   ⇒ laporan aging AR adalah **kode mati**. Dibuktikan dari tabel route aplikasi:
   `['GET'] /api/rahaza/ar-aging -> handler=write_off_bad_debt`. Setelah diperbaiki:
   `-> handler=ar_aging`, `GET /ar-aging` **HTTP 200**, dan write-off tetap **POST-only (GET 405)**.
   **Gate `verify_unreachable_code` (INV-DEADCODE-01) BUTA** terhadap pola ini — padahal
   docstring-nya sendiri mengaku hanya mencari "`def` tanpa dekorator". Cek kedua
   (`DANGLING_ROUTE_DEC`) **ditambahkan ke gate itu**, lengkap dengan `--self-test` yang
   membuktikan detektornya benar-benar bisa merah dan tidak menuduh alias path yang
   berdampingan-sengaja. Scan repo: **4661 fungsi, 0 sisa**.

2. **Pydantic MEMBACA "85.000" sebagai 85,0 — perbaikan `_compute_total_cost` bisa dilewati.**
   Tester menandai *"valid BOM template returns 422"*, yang ternyata salah payload di sisi mereka
   (payload benar → **201**, `total_cost_per_pcs` benar). Tetapi saat memverifikasinya sendiri,
   ketemu yang jauh lebih buruk: Pydantic v2 mode longgar mengubah string angka memakai aturan
   Python, bukan aturan Indonesia. `cost_per_unit: "85.000"` (delapan puluh lima **ribu**) menjadi
   **85.0**, dan `total_cost_per_pcs` tersimpan **51.0** padahal seharusnya **51000.0** —
   **SERIBU KALI lebih murah**. Guard `_compute_total_cost` tidak pernah berbunyi karena Pydantic
   sudah "berhasil" mengonversi sebelum kode saya jalan. Ini nyata sampai ke pengguna:
   `MaklonBuyerCatalogDetailDialog.jsx` mengirim **nilai mentah kotak input**
   (`e.target.value`), dan "85.000" adalah cara normal orang Indonesia menulis angka itu.
   Perbaikan: `field_validator(mode='before')` pada `BOMMaterialItem` yang memakai **SSOT yang
   sudah ada** `utils/money.parse_id_number` (titik = ribuan, koma = desimal) — bukan aturan baru.
   Hasil: `"85.000"` → **85000.0** (total **51000.0**), `"mahal sekali"` → **422** dengan pesan
   Indonesia yang jelas, angka JSON biasa → tetap **201** (tanpa regresi).

3. **`utils/money.parse_id_number("0.600")` mengembalikan 600.** Ditemukan saat memakai parser itu
   sebagai gerbang BOM. Aturan "satu titik + 3 digit = ribuan" benar untuk `150.000`, tetapi salah
   bila bagian bulatnya **0** — tidak ada yang menulis "nol ribu". Untuk `qty_per_pcs = "0.600"`
   (0,6 kg) itu berarti kebutuhan material **1000× lebih besar**. Aturannya dipertajam: pemisah
   ribuan hanya berlaku bila bagian bulat bukan nol. Diverifikasi: `85.000`→85000 ·
   `1.250.000`→1250000 · `1.234.567,89`→1234567.89 · `0.600`→**0.6** · `150.75`→150.75 ·
   `Rp 1.500.000`→1500000 · `(1.000)`→-1000.

Selain itu, titik buta ketiga ditutup dengan log (tanpa mengubah kontrak response):
`/supplier-scorecard` (daftar) memakai `$match {"inspected_at": {"$gte": ...}}`, dan di MongoDB
dokumen ber-`inspected_at` **STRING/null tidak pernah cocok** ⇒ inspeksi itu hilang dari scorecard
⇒ `accept_rate` supplier bisa tampak LEBIH BAIK dari kenyataan. Bahwa bentuk string itu nyata
terbukti dari endpoint detail yang harus menangani `isinstance(dt, str)`. Catatan: `data_quality`
milik saya memang ada di endpoint **detail** (`/supplier-scorecard/{supplier_name}`) — di situlah
tanggal di-parse di Python; tester menembak endpoint daftar.

Bukti ember jujur `tanpa_jatuh_tempo` (dijalankan, lalu artefaknya dihapus): dua invoice AR
@Rp 7.500.000 dengan `due_date` `null` dan `"31/12/2026"` ⇒ `tanpa_jatuh_tempo: 15.000.000`,
`current: 0`, `total: 15.000.000` (uang TIDAK hilang), dan `data_quality` menyebut **nomor
invoice** + alasan persisnya. **Dulu keduanya masuk ember `current`** = dilaporkan belum jatuh tempo.

### Bukti (dijalankan, bukan dikutip)

`bash scripts/gate.sh` → **13/13 HIJAU · 44 detik** (dari MERAH INV-4) ·
`verify_produksi_maklon_invariants` **19/19** · bootstrap bersih **85 detik, 6 login HTTP 200** ·
`yarn build` **Compiled successfully** · backend `/api/health` OK.

### BERIKUTNYA

1. Sisa handler senyap non-uang (±50 titik) — sudah dipetakan, tinggal ditriase satu per satu.
2. Nol test Jest/RTL di `frontend/` (`setupTests.js` sudah siap).
3. Approval PO (`rahaza_po.py`) belum memakai mesin SSOT `_eval_approval` seperti PR.
4. SLA reminder PR yang menunggu terlalu lama.
5. Tampilkan `data_quality` di layar Finance/Marketing (backend sudah mengirim; UI belum memakai).

---


## 2026-08-07 (lanjutan) — RANTAI PERSETUJUAN PR HIDUP UJUNG-KE-UJUNG (kotak persetujuan, pemisahan wewenang, ambang nilai)

Titik berhenti sesi lalu: *"the approval chain dead-ends in the UI — let me fix the inbox role
mapping."* Perbaikan pemetaan peran pada `/api/procurement/inbox` **memang sudah benar** dan
diverifikasi hijau lebih dulu sesi ini (`scripts/verify_pr_inbox_roles.py` → LULUS). Tetapi rantai
persetujuan **masih mati di layar**, dan penyebabnya bukan satu, melainkan sembilan.

### Yang sebenarnya mematikan rantai (semua dibuktikan dari kode + peran nyata di DB)

1. **Tidak ada layar kotak persetujuan sama sekali.** `grep -rn "procurement/inbox" frontend/src`
   → **kosong**. Endpoint yang diperbaiki sesi lalu **nol pemanggil**; approver harus menelusuri
   seluruh daftar PR untuk menemukan pekerjaannya.
2. **KEMBARAN bug yang sama hidup di FRONTEND — ini dead-end sebenarnya.**
   `ProcurementRequestModule.jsx:486` menyaring tombol Setujui/Tolak dengan daftar peran generik
   `['manager','dept_head','supervisor','finance','finance_manager','accountant','director','cfo','ceo']`.
   Peran NYATA di aplikasi ini: `finance@`=**accounting**, `spv@`=**supervisor_produksi**,
   `gudang@`=**admin_gudang**. Tidak satu pun cocok ⇒ **hanya admin/superadmin** yang bisa
   menyetujui dari UI. Backend mengizinkan, layarnya tidak menyediakan tombol.
3. **Approver berikutnya tidak pernah diberi tahu.** `_notify_procurement_event` hanya posting ke
   channel `#procurement-notifications` + DM ke **pembuat** PR.
4. **Tidak ada cek TAHAP di `/approve`.** `require_perm('purchasing.approve','finance.approve', legacy_roles=…)`
   ⇒ satu manager bisa mendorong `submitted→dept_approved→finance_approved→approved` sendiri,
   **termasuk menyetujui PR buatannya sendiri**. Lubang kontrol uang.
5. **`current_approver_role` ditulis `"finance"`** — peran yang tidak ada di aplikasi ini.

### Tiga bug BARU yang ditemukan POC (bukan dari pembacaan kode)

6. **`department` TIDAK PERNAH ada di JWT.** `auth.create_token` tidak memasukkannya, jadi
   `user.get("department")` selalu kosong di SELURUH backend. Dua akibat nyata: (a) approver
   departemen lain bisa menyetujui PR departemen mana pun; (b) kode inbox LAMA justru
   mengembalikan daftar **KOSONG** untuk approver bergantung-departemen
   (`if user_dept: … else: return []`) — itulah sebabnya kotak persetujuan `admin_gudang`
   **selalu kosong** walau perbaikan peran 2026-08-06 sudah benar. Perbaikan: `department` masuk
   token baru + `_with_department()` menambal dari DB untuk token yang masih berlaku (24 jam).
7. **Izin `*` milik admin membuat override tidak pernah tercatat.** `_stage_role_ok` menerima `*`
   sebagai bukti "peran tahap yang tepat" ⇒ setiap tindakan admin tampak sah. Sekarang peran super
   dinilai HANYA dari keanggotaan daftar peran tahap (`owner` memang approver tahap final).
8. **Rantai tidak tampil pada PR draft** (flag server tidak ikut di endpoint detail — hilang karena
   dua edit paralel pada berkas yang sama saling menimpa).

### Satu temuan lagi saat verifikasi UI

9. **Dialog detail PR tidak dimuat ulang setelah PO dibuat** ⇒ nomor PO tidak muncul dan tombol
   "Buat Purchase Order" masih ada padahal PO-nya sudah terbentuk.

### Keputusan owner yang diterapkan

* **Pemisahan wewenang KETAT**: peran per tahap (daftar SALING LEPAS — `manager_keuangan`
  dikeluarkan dari tahap final), larangan self-approval, larangan satu orang menyetujui dua tahap,
  batas departemen pada tahap pertama. **admin/owner tetap boleh override**, tetapi setiap
  pelanggaran yang ditembus DICATAT (`override: true`, `override_reasons`, label
  "(override admin)") dan tampil di riwayat + stepper.
* **Kedalaman rantai mengikuti NILAI PR** dengan ambang yang bisa diatur owner di layar
  **Ringkasan Bisnis** (blok "Ambang Persetujuan PR", satu layar dengan ambang hari yang sudah
  ada): ≤ `pr_1_stage_max` (Rp 1 jt) → 1 tahap · ≤ `pr_2_stage_max` (Rp 25 jt) → 2 tahap · di atas
  itu → 3 tahap. Disimpan di dokumen & endpoint yang SAMA (`dewi_mgmt_alert_config`,
  `GET/PUT /api/rahaza/management/alert-config`) dengan validator terpisah (hari 0..60 vs rupiah).
  **Rantai DIBEKUKAN saat submit** (`approval_chain`) supaya mengubah ambang besok tidak menggeser
  PR yang sudah berjalan.
* **Kotak persetujuan = TAB di dalam menu "Permintaan Pengadaan"** (bukan menu baru).

### Perubahan inti

* **SERVER JADI SATU-SATUNYA PENENTU IZIN.** Mesin tunggal `_eval_approval` dipakai oleh
  `/inbox`, daftar PR, detail PR, timeline, gerbang `/approve` & `/reject`, hitungan
  `my_pending_approval`, dan lencana TopBar. Setiap PR yang dikirim ke UI membawa
  `can_approve` / `can_reject` / `blocked_reason` / `chain` / `stage_label` /
  `next_approver_label`. Daftar peran di frontend **DIHAPUS** — frontend dilarang punya daftar
  sendiri (itu asal bug #2).
* **`/inbox` DITULIS ULANG** memakai mesin yang sama dengan gerbang aksi. Versi lama membangun
  daftar status lewat query lalu menghitung `can_approve` dengan aturan LAIN di bawahnya — dua
  aturan yang bisa (dan memang pernah) berbeda. Invarian baru: **setiap item inbox pasti bisa
  disetujui**, dan **angka lencana TopBar = jumlah isi kotak persetujuan**.
* **Lencana TopBar** (`routes/approval_badge.py`) berhenti memakai daftar peran **ke-4** dan
  berhenti menghitung hanya `status: "submitted"` (dulu staf keuangan melihat angka tahap
  DEPARTEMEN, sementara antrean `dept_approved` miliknya sendiri tidak pernah dihitung).
* **Notifikasi**: `_notify_stage_approvers` menulis lewat SSOT `notif_insert`
  (`type=rahaza`, `subtype=procurement_approval`) ke `target_user_ids` approver tahap berikutnya
  (tahap departemen difilter departemen PR; fallback `target_roles` bila belum ada penggunanya),
  `meta.link_module='proc-requests'` agar tombol Buka mengarah benar. Pemohon dikabari saat PR
  disetujui penuh / ditolak.
* **Penolakan wajib beralasan** (400 berbahasa Indonesia) — dulu PR bisa ditolak tanpa penjelasan.
* **`DELETE /api/procurement/requests/{id}` DIBUAT.** `verify_pr_inbox_roles.py` sudah
  memanggilnya sejak lama tetapi endpointnya **tidak ada**, dan 404-nya ditelan "best-effort" —
  itulah sebabnya PR uji "UJI INBOX — kancing plastik" menumpuk di data demo (2 tertinggal,
  sudah dibersihkan). Aturan: pemohon boleh hapus PR draft-nya; admin boleh hapus PR yang BELUM
  punya PO (PR yang sudah menghasilkan PO tidak boleh hilang dari jejak audit).
* **Akun tahap final + akses portal.** Tidak ada satu pun akun `director/cfo/ceo/owner` di DB ⇒
  PR 3 tahap tidak bisa diselesaikan siapa pun kecuali override admin. Ditambah
  **`direktur@dewiaditya.id` / `Dewi@123`** (role `director`). `PORTAL_ACCESS['procurement']` +
  cermin FE ditambah peran approver (`supervisor_produksi, manager, dept_head, manager_hr,
  manager_marketing, spv_packing, spv_cuting, director, cfo, ceo`) — tanpa ini approver tidak bisa
  MEMBUKA layar tempat kotak persetujuan berada. Izin baru `proc.pr.final_approve` masuk katalog
  supaya tahap final tidak bisa dibuka pemegang `finance.approve`.
* **Master Supplier ikut di-seed.** `bootstrap.sh` tidak pernah menyeed `rahaza_suppliers`, jadi
  environment segar selalu 0 supplier ⇒ layar Master Supplier / Penilaian Supplier / Analisis
  Belanja kosong DAN alur "PR disetujui → Buat Purchase Order" **mentok di UI** (dialog PO
  mewajibkan supplier dari master). Ditambah `scripts/seed_procurement_suppliers_demo.py`
  (idempoten, `--cleanup`, hanya master + daftar harga — tidak menyentuh stok/jurnal) dan
  dipanggil dari `bootstrap.sh`.

### Frontend

* `ProcurementRequestModule.jsx`: 3 tab (**Semua Permintaan · Menunggu Persetujuan Saya** dengan
  lencana jumlah **· Permintaan Saya**), tombol "Setujui" cepat per baris, total nilai yang
  menunggu, keadaan kosong yang menjelaskan SYARAT sebuah PR muncul di sana, **stepper rantai
  persetujuan** (penuh di dialog, ringkas di kartu) berisi siapa memutuskan + kapan + penanda
  override, `blocked_reason` ditampilkan saat tidak berhak (bukan tombol hilang tanpa kabar),
  peringatan kuning untuk admin yang menembus aturan, alasan penolakan ditampilkan, dan modul
  otomatis membuka tab kotak persetujuan bila ada pekerjaan menunggu (berhenti mengganggu setelah
  user memilih tab sendiri).
* `ManagementOverviewModule.jsx`: blok **"Ambang Persetujuan PR"** (2 input rupiah + pratinjau
  nilai + penjelasan bahwa ambang dibekukan saat PR diajukan).

### Uji

`scripts/poc_approval_chain.py` **73/73 PASS** (HTTP + unit mesin; menemukan bug #6, #7, #8) ·
`scripts/verify_pr_inbox_roles.py` **LULUS** · `bash scripts/gate.sh` **13/13 HIJAU** ·
testing agent iteration_26 (backend **26/26**, 0 bug), iteration_27 (UI inti, 0 bug),
iteration_28 (UI lanjutan A–E, 0 bug) · verifikasi browser: alur 3 tahap oleh 3 orang berbeda,
override admin tercatat, ambang tersimpan + validasinya, lencana TopBar = isi inbox, bel
notifikasi, 8 pintu Portal Pengadaan bersih, `hr@` tetap terkunci, dan PR → PO (PO-20260807-004
tertaut, status `in_procurement`).

**Pelajaran proses:** dua `search_replace` PARALEL pada berkas yang SAMA saling menimpa (perubahan
`get_request` hilang walau dilaporkan sukses). Edit berkas yang sama harus BERURUTAN.

## 2026-08-07 — BEL NOTIFIKASI RBAC HIJAU ("Untuk Saya"), AMBANG DIATUR OWNER, FOTO DESAIN RnD, KEBOCORAN BERKAS DITUTUP

Sesi sebelumnya terputus dengan **3 FAIL** pada `scripts/poc_rbac_notif_approval.py` (43/46):
notifikasi personal & per-role tidak muncul di **bel**, padahal muncul di inbox unified.

* **Akar masalah**: `GET /api/notifications/categorized` membuang notifikasi bila kategori turunannya
  di luar kategori portal milik peran user — **walaupun notifikasi itu dialamatkan langsung**
  kepadanya (`user_id` / `target_user_ids` / `target_roles`). `subtype` tak dikenal jatuh ke
  `sysadmin`, dan `sysadmin` hanya untuk admin ⇒ notifikasi pribadi staf hilang. Endpoint hitungan
  `/categories` sudah punya jaring penyelamat, endpoint daftar `/categorized` belum ⇒ angka di bel
  pun tidak cocok dengan isi popup.
* **Kategori bawaan `personal` = "Untuk Saya"**: selalu aktif untuk semua peran, tidak bisa ditutup
  admin, tidak bisa dibisukan user. Notifikasi yang dialamatkan langsung tapi kategorinya di luar
  jangkauan peran ditampung di sini (RBAC tidak dilonggarkan — aturan audiens
  `notif_audience_query` tetap satu-satunya penentu penerima).
* **Satu helper bersama** `category_scope()` + `effective_category()` dipakai `/categories` dan
  `/categorized` ⇒ angka bel = isi popup (diuji). Perbedaan yang disengaja: **celah RBAC** dialihkan
  ke "Untuk Saya", sedangkan kategori yang **dibisukan sendiri** oleh user benar-benar disembunyikan.
* **Bel akhirnya menampilkan isi pesan & tombol Buka**: backend menormalkan `body`↔`message` dan
  `link_module` (akar dokumen ATAU `meta`), sehingga notifikasi SSOT (`notif_insert`) tidak lagi
  tampil sebagai judul kosong tanpa tautan modul.
* **Layar baru "Notifikasi Saya"** (`NotificationPrefsDialog.jsx`) — ikon gerigi di dropdown bel +
  tombol di Pusat Notifikasi. `GET/PUT /api/notifications/my-category-prefs` sudah ada bertahun tapi
  belum pernah punya UI (fitur tak bisa dipakai). Kolom "Untuk Saya" di Aturan Notifikasi (admin)
  kini tercentang & non-aktif.
* **Ambang peringatan bisa diatur owner (diperluas)**: `dewi_mgmt_alert_config` kini menyimpan 4
  nilai — `po_warn_days`, `ar_warn_days`, **`rnd_attention_days`**, **`rnd_stale_days`**. SLA kokpit
  RnD (`routes/dewi_rnd_design.py::_sla`) berhenti memakai 3/7 hardcode dan
  `/api/dewi/rnd/approvals/pending` mengirim `thresholds` + penjelasan. Validasi 0..60 hari dan
  *perhatian* ≤ *terlambat* (400 berbahasa Indonesia). UI: 4 kotak angka di Ringkasan Bisnis
  (`alert-rnd-attention-input`, `alert-rnd-stale-input`) + kalimat ambang aktif di Ringkasan RnD.
* **Foto desain RnD**: endpoint `POST/DELETE /api/dewi/rnd/styles/{id}/images` sudah ada; sesi ini
  diverifikasi end-to-end (unggah → galeri kokpit manajemen & kolom FOTO tabel "Posisi Tiap Style" →
  hapus) dan 2 foto contoh dipasang pada style demo `DA-HD02-RND`. Menu `rnd-design-hub` diganti
  nama **"Tech Pack" → "Style & Desain"** karena layar unggah fotonya tidak bisa ditemukan owner.
* **KEAMANAN — `GET /api/files/{path}`**: dulu token di-decode dengan `verify_signature=False`,
  artinya JWT palsu pun diterima dan berkas apa pun (foto karyawan, dokumen HR, lampiran RnD) bisa
  diunduh. Sekarang tanda tangan diverifikasi lewat `auth.verify_token_str`; `?auth=<jwt>` tetap
  didukung karena `<img src>` tidak bisa mengirim header. Token palsu → 401 (diuji).
* **Batas laju login** 10 → **30 permintaan/60 detik per IP**, dan panggilan loopback tanpa
  `X-Forwarded-For` (skrip seed/uji internal) dibebaskan. Alasan nyata: satu kantor di belakang satu
  IP publik saling memblokir saat jam masuk, dan `seed_demo_all.sh` selalu gagal 429. Perlindungan
  brute force yang menghitung KEGAGALAN (5/15 menit per IP+email, 20/60 menit per email) tidak
  diubah — masih diuji lulus.
* **Kebersihan**: `plan.md` (1 byte NUL), `scripts/poc_rbac_notif_approval.py` (blok duplikat sisa
  sesi terputus yang membuat berkas tak bisa di-parse), `backend/backend_test.py` (URL preview
  dipatok di kode + akun HR yang tidak ada di DB) diperbaiki; `memory/test_credentials.md` dibuat
  ulang; tes buatan testing agent disimpan sebagai `scripts/verify_notif_rbac_alert_config.py`.
* **Uji**: POC RBAC **57/57** (11 pemeriksaan baru) · `backend/backend_test.py` **34/34** ·
  `scripts/verify_notif_rbac_alert_config.py` **48/48** ·
  `scripts/verify_rnd_style_status_guard.py` **17/17** · `gate.sh` **13/13 HIJAU** ·
  testing agent iteration_22 & iteration_23 **0 bug**.

### Temuan tambahan sesi ini (di luar permintaan, ditemukan saat verifikasi UI)
* **LUBANG ALUR — status style RnD bisa ditimpa dari form edit.** `PUT /api/dewi/rnd/styles/{id}`
  menerima `status` apa pun ⇒ siapa pun yang boleh menyunting style dapat menulis
  `approved_for_launch` (melewati keputusan owner, tanpa pemutus & alasan) atau menarik style yang
  sedang direview kembali ke `draft` tanpa jejak. Sekarang status siklus hidup
  (`pending_owner_review`, `approved_for_launch`) HANYA berpindah lewat `submit-for-review` /
  `owner-approve` / `owner-reject`; form edit hanya boleh `draft|active|archived` (403/400 dengan
  pesan Indonesia). Field non-status tetap bisa disunting saat menunggu keputusan.
* **UI menyesatkan**: dropdown Status di dialog *Edit Style* hanya punya draft/active/archived,
  sehingga style berstatus `pending_owner_review` **tampil sebagai "Draft"** — sekali disimpan,
  status review bisa hilang. Sekarang status keputusan tampil sebagai lencana **read-only**
  (`style-status-locked`) + penjelasan "Diatur lewat tombol Ajukan Review / Setujui / Tolak".
* **Layar unggah foto tidak bisa ditemukan**: menu RnD `rnd-design-hub` bernama **"Tech Pack"**
  padahal tab pertamanya "Style & Tech Pack" (tempat unggah foto desain) → diganti
  **"Style & Desain"**.
* **Kode mati dipakai kembali**: komponen `ReviewHistoryPanel` (menampilkan **siapa** memutuskan +
  alasan lengkap) tidak pernah dirender; tabel style hanya memotong alasan 40 karakter tanpa nama
  pemutus. Sekarang panel itu yang dipakai.
* **Skrip verifikasi dibuat aman untuk data demo**: `verify_rnd_style_status_guard.py` memakai style
  buangan `ZZ-VERIFY-*` (dibuat lalu dihapus) dan hanya **memeriksa** status 4 style demo. Artefak
  uji (revisi "Ubah Deskripsi", foto uji, status `MK-JKT-RND`) sudah dibersihkan.


## 2026-08-06 (lanjutan 3) — RIWAYAT KEPUTUSAN RnD + DETAIL & FOTO DI KOKPIT RnD

Owner: "Riwayat Keputusan RnD: tampilkan siapa menyetujui atau menolak style dan alasannya di satu
daftar" · "sepertinya rnd di management masih terlalu simple, harus bisa lihat detail, harus bisa
lihat foto yang di sematkan di rnd dll". Owner juga MEMBATALKAN rencana menyembunyikan 5 menu yang
belum terpakai — kelimanya tetap tampil (Rekonsiliasi PO, Persetujuan Invoice, Transfer Bank,
Kas Kecil, Roll Kain).

* **`GET /api/dewi/rnd/approvals/history`** (baru): satu daftar keputusan lintas jenis (style,
  permintaan sample, tech pack) — hasil (disetujui/ditolak), **siapa yang memutuskan**, kapan,
  **alasan/catatan**, status sekarang, dan penanda "naik produksi". Diurutkan terbaru di atas.
* **`GET /api/dewi/rnd/approvals/pending` diperkaya**: tiap item kini membawa `detail`
  (Deskripsi, Jenis RnD, Kategori, Bahan, Season, Klien/Buyer, Jumlah Varian, Dibuat),
  `images` (dinormalisasi dari `design_images` — menerima string URL maupun objek), serta
  `attachment_url`/`attachment_name` (tech pack).
* **Kokpit RnD** (`RnDPortalDashboard.jsx`): tombol **Detail** per antrean membuka dialog berisi
  grid spesifikasi + **galeri foto desain** (klik untuk membuka ukuran penuh) + tautan lampiran +
  "Langkah berikutnya", dengan tombol **Setujui/Tolak** langsung di dialog. Ditambah seksi
  **Riwayat Keputusan** berbentuk tabel (Jenis · Kode · Judul · Hasil · Diputuskan Oleh · Tanggal ·
  Alasan) + badge jumlah disetujui/ditolak.
* Bila dokumen belum punya gambar, ditampilkan penjelasan jujur ("Belum ada gambar dilampirkan…"),
  bukan area kosong.
* Uji: testing agent iteration_18 — **backend 55/55**, frontend 95% (satu catatan INFO soal urutan
  baris tabel yang memang diurutkan tanggal). Style uji milik penguji dibersihkan; data demo utuh
  (`DA-HD02-RND` tetap menunggu keputusan, `DA-PL03-RND` tetap disetujui).

## 2026-08-06 (lanjutan 2) — KOKPIT APPROVAL RnD · TRACKING PRODUKSI JUJUR · PERINGATAN OTOMATIS · AUDIT MENU ZOMBIE

### 1. Kokpit Approval RnD (Ringkasan RnD jadi layar keputusan)
Owner: "ringkasan rnd hanya cards yang besar sangat buruk... padahal ini step lifecycle crusial yang
butuh approve koordinasi antara staff rnd dengan manajement."
* Endpoint baru `GET /api/dewi/rnd/approvals/pending` menyatukan yang menunggu keputusan
  (style `pending_owner_review`, permintaan sample `submitted`, tech pack pending) + **umur tunggu
  (SLA: baru / perlu perhatian / terlambat >7 hari)** + tahapan lifecycle.
* `RnDPortalDashboard.jsx` ditulis ulang: **Antrean Keputusan** dengan tombol **Setujui / Tolak**
  (alasan wajib untuk style), **Tahapan Lifecycle** (Draft → Menunggu → Disetujui → Naik Produksi),
  lalu ringkasan angka dalam tile kecil — 3 baris kartu gradien raksasa dibuang.
* Endpoint approval-nya sudah ada bertahun tapi **tidak pernah dipakai UI**; sekarang dipakai:
  `styles/{id}/owner-approve|owner-reject`, `sample-requests/{id}/approve|reject`,
  `tech-packs/{id}/approve`.

### 2. Tracking Produksi membaca data nyata + menjelaskan yang kosong
* **Maklon**: panel "Work Order Terhubung" yang membaca `rahaza_work_orders` (0 dokumen) lewat
  endpoint `deprecated` DIGANTI panel **"Produksi Nyata (Job & Buku Kuantitas)"** dari
  `production_jobs` + `production_job_items` + `buyer_shipments` (via `/api/dewi/reports/po/{id}`).
* **PO draft tidak lagi disembunyikan** dari daftar (dulu difilter diam-diam sehingga PO yang baru
  dibuat "tidak muncul"); judul daftar menyebut berapa yang masih draft.
* Bila PO belum punya job, muncul penjelasan tegas: *"Progres produksi baru muncul setelah PO
  dikonfirmasi lalu didistribusi menjadi Production Job... angka 0 itu wajar, bukan data hilang."*
* **Internal** (`prod-monitoring`): empty-state diperjelas dengan sumber (`production_jobs`) dan
  langkah yang harus dilakukan.

### 3. Peringatan Otomatis ke manajemen (permintaan owner)
* `backend/services/management_alerts.py`: pindai PO yang deadline ≤ 3 hari / sudah lewat **dan**
  barangnya belum lengkap diterima, plus invoice AR yang mendekati/melewati jatuh tempo.
* Menulis lewat penulis kanonik `utils/notif_unified.notif_insert` ke koleksi SSOT `notifications`
  (type `rahaza`, subtype `po_deadline` / `ar_due`), **idempoten per dokumen per hari**.
* Job scheduler harian **07:00 Asia/Jakarta** (`management_alerts`) + pintu manual:
  `GET /api/rahaza/management/alerts` (pratinjau, tidak menulis) dan
  `POST /api/rahaza/management/alerts/scan` (kirim sekarang).
* Ringkasan Bisnis menampilkan kartu **"Peringatan Perlu Tindakan"**.
* Uji: 4 notifikasi terkirim ke 4 penerima manajemen, pemanggilan kedua 0 (idempoten).

### 4. Audit menu zombie (alat, bukan tebakan)
* `scripts/audit_menu_zombie.py` memetakan **menu → komponen → endpoint → koleksi** lalu memeriksa
  isi koleksinya. Hasil: **116 menu sehat · 5 kandidat · 1 redirect · 55 tanpa panggilan API**.
* Kelima kandidat (3-Way Match, Approval Invoice, Transfer Bank, Kas Kecil, Roll Kain) **punya
  penulis** di backend ⇒ **fitur belum terpakai**, bukan zombie → sengaja TIDAK dihapus.
* Yang benar-benar mati dan sudah dihapus: menu **Data Pelanggan** (gelombang 1) dan berkas
  `backend/services/notification_service.py` (tak diimpor siapa pun; menulis ke koleksi
  `dewi_notifications` yang tidak pernah ada).

Uji: testing agent iteration_17 — backend 23/24, frontend 90%; dua catatan LOW terbukti artefak
otomasi (job `management_alerts` ada di log scheduler; kesulitan selector navigasi). Data demo utuh
(style `DA-HD02-RND` tetap `pending_owner_review`).

## 2026-08-06 (lanjutan) — PORTAL MANAJEMEN: LAPORAN BERHENTI MEMBACA KOLEKSI MATI

Owner: "laporan laporan yang ada sepertinya belum berjalan dengan baik, tidak mengambil source data
yang benar... ringkasan bisnis saya yakin juga masih logic error mengambil collection data entah dari
mana... data pelanggan kosong, menu ini tidak perlu... sebenarnya apa yang salah dari system ini?"

### AKAR MASALAH (jawaban atas pertanyaan owner)
Migrasi ke SSOT dilakukan bertahap (production_pos/po_items/production_jobs/production_progress/
cmt_receipts/rahaza_stock_ledger), tetapi **lapisan laporan & ringkasan manajemen tidak pernah ikut
dimigrasi** dan modul lamanya tidak dibersihkan. Hasilnya "menu zombie": tampil rapi, membaca gudang
data yang sudah tidak ditulisi siapa pun.

Bukti (jumlah dokumen nyata): `rahaza_work_orders`=0 · `rahaza_customers`=0 · `rahaza_shipments`=0 ·
`rahaza_ap_invoices`=0 · `rahaza_cash_accounts`=0 · `rahaza_qc_events`=**koleksi tidak ada** ·
`rahaza_orders`=1 · `rahaza_wip_events`=2 · `dewi_cmt_progress_reports`=0 ·
`dewi_cmt_delivery_orders`=0 · `dewi_maklon_dispatches`=0.

### GELOMBANG 1 — sumber data laporan dipindah ke SSOT
* **Helper bersama baru** `backend/services/mgmt_analytics.py`: satu tempat mengambil cakupan
  PO → item → job → item job → buku kuantitas, dengan pemisahan domain
  (`internal` = produksi internal DA · `maklon`). Kuantitas SELALU lewat
  `core/production_qty_ledger.ledger_view()` → tidak ada rumus kedua.
* **`routes/rahaza_reports.py` ditulis ulang**: `/management/overview`, `/daily-output`,
  `/top-models`, `/top-customers`, `/on-time-delivery` + 7 laporan tabel
  (`production`, `per-po`, `progress`, `financial`, `shipment`, `rework`, `material-issue`).
  Semua menerima `?domain=` dan mengembalikan `sources` (jejak koleksi + jumlah dokumen).
  Tipe laporan tak dikenal kini 404 dengan daftar pilihan (dulu diam-diam mengembalikan `[]`).
* **`routes/dewi_phase7_reports.py` (Laporan Maklon) ditulis ulang** ke SSOT: penerimaan CMT +
  progres produksi + surat jalan CMT/buyer + klien maklon. `/reports/po/{id}` sekarang menerima id
  `production_pos` MAUPUN id `dewi_maklon_pos` (dulu sering 404). Ekspor CSV memuat bagian
  **JEJAK SUMBER DATA**.
* **Ringkasan Bisnis** (`ManagementOverviewModule.jsx`) ditulis ulang: pemilih domain
  **Gabungan / Internal DA / Maklon**, kartu "Tahapan PO" (Draft→Dikonfirmasi→Berjalan→Selesai),
  grafik output harian bertumpuk internal vs maklon, donut ketepatan kirim yang jujur
  ("hanya PO yang punya deadline DAN sudah dikirim yang dinilai"), dan jejak sumber di bawah.
  Contoh angka nyata sekarang: output 1.228 pcs · 219 diterima dari 735 produksi · 12 PO berjalan
  dari 21 · piutang Rp 12,18 jt.
* **Laporan Umum** (`ReportsModule.jsx`): pemilih domain, kolom mengikuti SSOT
  (NO PO/QTY PESAN/QTY DITERIMA/QTY REJECT, bukan NO WO/QTY ORDER lama), dan **"Rekap per PO"
  yang dulu di-hardcode kosong di frontend (`setData([])`) sekarang berisi 21 baris**.
* **Laporan Maklon** (`Phase7ReportingModule.jsx`): label diperbaiki (Delivery Orders → Pengiriman
  CMT / SJ ke CMT / Penerimaan; "Process Step" → "Sumber Data") + komponen `<SourceTrace/>`.
* **Bersih-bersih**: menu **Data Pelanggan** dihapus (nav + registry + `RahazaCustomersModule.jsx` +
  entri panduan) karena master duplikat & kosong; pelanggan nyata ada di `dewi_maklon_clients` (8)
  dan `production_pos.customer_name`.
* Uji: testing agent **backend 75/75 PASS**, frontend 100% (menu hilang, domain switch mengubah
  angka, 7 laporan terisi, jejak sumber tampil).

### GELOMBANG 2 — Pusat Laporan jadi benar-benar berguna
Dulu hanya katalog tautan statis ("yang ada malah direct ke portal lain"). Sekarang
`GET /api/rahaza/reports-hub/categories` + `GET /api/rahaza/reports-hub/summary?category=…`
melayani **8 kategori portal** — Eksekutif, Produksi Internal DA, Maklon, Gudang, Keuangan, SDM,
RnD, Marketing — masing-masing dengan **KPI ringkas + 1–2 tabel data nyata + tautan tindak lanjut +
jejak sumber**. Kontraknya generik (`kpis[]`, `tables[]` berisi `columns`/`rows`) sehingga menambah
kategori tidak perlu menyentuh komponen UI. `ReportsHubModule.jsx` dirombak: pemilih kategori,
tile KPI kecil (bukan kartu raksasa), tabel dengan unduh CSV per tabel, pemilih periode, dan
empty-state yang menjelaskan sebab kosong (mis. "Job terbentuk setelah PO dikonfirmasi lalu
didistribusi").
Contoh isi nyata: Eksekutif → 3 PO perlu perhatian + 10 piutang terbesar · Gudang → 498 material,
3 dokumen pengeluaran · Marketing → omzet Rp 19,9 jt dari 120 order.

### BELUM DIKERJAKAN (gelombang berikutnya, sesuai kesepakatan bertahap)
* G3: **Ringkasan RnD** → Kokpit Approval RnD untuk manajemen (endpoint approval sudah ada tapi
  belum dipakai UI); **Tracking Produksi Maklon** masih memakai endpoint `deprecated` yang membaca
  `rahaza_work_orders` (0 dokumen); kedua Tracking Produksi perlu empty-state jujur
  ("PO belum muncul karena belum didistribusi menjadi Production Job").
* G4: sisir portal lain untuk menu zombie sisanya + hapus route/koleksi legacy
  (mis. CRUD `/api/rahaza/customers` yang tidak lagi dipakai UI).

## 2026-08-06 — RBAC SATU TEMPAT: MATRIKS RAKSASA DIHAPUS, IZIN AKSI BENAR-BENAR BERLAKU

Owner melapor: "di sini ada dua pengaturan akses, membingungkan — buatkan 1, jangan duplikasi;
UI/UX-nya juga tolong perbaiki, matriksnya terlalu besar dan susah dikonfigurasi."

### Yang dihapus (sumber kebingungan)
* `frontend/src/components/erp/RoleMatrixModule.jsx` — matriks 13+ kolom peran × 129 baris izin.
* `PUT /api/roles/{id}/permissions` dan `POST /api/roles/matrix/bulk` — jalur simpan kedua.
* Tab hub "Kontrol Akses" dari **3 tab** (Pengguna | Peran | Hak Akses) jadi **2 tab**
  (Pengguna | **Peran & Hak Akses**). Deep-link lama `#mgmt-role-matrix` diarahkan ke tab baru.

### Satu katalog izin (SSOT)
`backend/data/permission_catalog.py` — 129 izin tersusun **portal → modul → izin**, tiap izin
punya metadata `action` (`view/input/manage/approve/run/export`). Metadata inilah yang membuat
pilihan cepat **Tidak ada / Lihat saja / Penuh** per modul dan preset **Lihat saja / Operator /
Approver / Penuh** bisa dihitung otomatis — tak ada daftar hardcode di frontend.
`GET /api/permissions` (datar, kompatibel lama) · `GET /api/permissions?grouped=1` (untuk UI baru).
Kunci izin divalidasi saat simpan → tidak ada izin "hantu" di DB.

### Satu layar konfigurasi (master–detail)
`RoleManagementModule.jsx` ditulis ulang: kiri daftar peran (cari + ringkasan pengguna/portal/izin),
kanan panel bertahap **1** Identitas (+ "Salin dari peran lain") · **2** Portal · **3** Hak Akses
(accordion per portal, pilih cepat per modul, chip per izin, preset) · **4** Menu disembunyikan
(collapsible) · **5** Riwayat perubahan. Ada indikator "Belum disimpan", tombol **Bandingkan**
(sheet selisih izin antar peran), konfirmasi hapus, dan toast `sonner` (tidak lagi `alert()`).

### Satu jalur simpan
`POST /api/roles` & `PUT /api/roles/{id}` menerima `name, description, portals, hidden_modules,
permissions` sekaligus. `GET /api/roles` kini mengirim `portals`, `hidden_modules`,
`permission_keys`, dan `user_count`. Peran yang masih dipakai pengguna tidak bisa dihapus.

### Izin aksi/approval AKHIRNYA berlaku di API (model "fallback aman")
Mesin tunggal di `backend/routes/shared.py`: `has_perm` · `can_act` · `require_perm` ·
`require_perm_dep` (+ `user_permissions`, `perms_configured`). Urutan: super role/`*` → izin yang
diminta → **bila izin peran masih kosong** pakai daftar role legacy (`legacy_roles`, atau
`legacy_any=True` untuk endpoint yang dulu terbuka bagi semua user login) → selain itu 403.
Artinya **tidak ada fitur yang mati**; begitu owner mencentang izin, daftar izin itulah yang berlaku
(UI memberi peringatan kuning eksplisit).

Sudah dipindah ke gerbang terpusat: approval Pengeluaran Material (MI), Cutting, CMT
(intake/belanja/kejar/permak), Penomoran Dokumen, approval Opname Gudang (2 titik),
approval perubahan Invoice, Inbox Approval SDM, dan Put-away Gudang.
`auth.require_auth` kini juga memuat `extra_permissions` per orang, dengan cache proses TTL 20 detik
+ invalidasi `bump_rbac_cache()` saat peran/pengguna diubah.

### Bukti uji (curl)
`admin_gudang` tanpa izin: `POST /api/cutting/orders` → **400** (lolos gerbang) ·
`GET /api/dewi/cmt-kejar` → **403** (sama seperti sebelumnya).
`admin_gudang` diberi HANYA `wh.putaway.manage`: cutting → **403**, put-away → **404** (lolos gerbang).
Izin dikosongkan lagi: cutting → **400** (kembali fallback aman).

### Lain-lain
* Role `admin_gudang` **direset** ke akses penuh (sesi lalu sengaja dibatasi untuk uji).
* `lib/rbac.jsx` dirapikan: `RequirePerm` sekarang benar-benar mendukung pemakaian
  `keys={[...]}` + `user` (sebelumnya prop itu diabaikan) tanpa merusak pemakaian lama.
* Panduan modul (`userGuide/moduleHelpData.js`) disesuaikan; entri "Matriks Peran & Izin" dihapus.
* Rincian lengkap: `memory/RBAC_KONSOLIDASI_2026-08-06.md`.
* Fitur AI tetap **di-skip** atas keputusan owner.

## 2026-08-05 — SATUAN DI 6 TITIK MASUK STOK · PENOMORAN DOKUMEN TAHAP 2 · DASHBOARD MAKLON

Repo di-clone ke container baru (preview `design-rnd-studio`), dipulihkan dengan `scripts/bootstrap.sh`
(96 detik: backend healthy, `yarn build` OK, seed dasar + demo, 6 akun login 200) lalu melanjutkan
titik berhenti sesi 2026-08-05 (commit `5d32b0c`, pekerjaan UoM RnD/BOM/Costing).

### A. Sisa sesi lalu ditutup — jalur SIMPAN Sample Costing akhirnya TERBUKTI
`backend/tests/flow_rnd_uom_test.py` dulu mengakhiri diri dengan 1 FAIL ("tidak ada sample request")
karena container segar tidak punya data sampel, sehingga **jalur simpan costing tidak pernah teruji**.
Uji sekarang MEMBUAT style + sample request sendiri lalu membuktikan: rincian `fabric_items`/`trim_items`
tersimpan, `total_material_cost` 134.800, `GET` detail konsisten, muncul di daftar per
`sample_request_id`, `PUT` menghitung ulang (144.800), `PUT` dengan qty baru **mengonversi ulang di
server** (1 m → 0,384 kg = 38.400), dan `DELETE` benar-benar 404. **38 PASS / 0 FAIL**, artefak bersih.

### B1. PEMILIH SATUAN di 6 titik masuk/keluar stok (ROADMAP P1 — backend siap, layarnya belum ada)
| Titik | Endpoint | Yang ditambahkan di layar |
|---|---|---|
| Penerimaan Gudang | `POST /api/wms/pending/{id}/scan-in` (`input_uom` **baru**) | dropdown satuan + pratinjau + catatan "dokumen memakai satuan X" |
| Put-away | `POST /api/wms/putaway/place` | dropdown + pratinjau + pagar "melebihi sisa belum dirak" |
| Opname Gudang | `POST /api/wms/opname3/scan` | "jumlah & satuan per scan" (dulu selalu +1 satuan dasar) |
| Opname Aksesoris | `PUT /api/acc/opname/{id}/count` | satuan hitung per baris + pratinjau |
| Pengeluaran Material (MI) | `POST/PUT /api/rahaza/material-issues` | qty **dan** satuan per baris (dulu qty tidak bisa diubah dari layar) |
| Aksesoris masuk/keluar | `POST /api/acc/stock/{receive,issue}` | `input_unit` menerima KODE SATUAN (dulu hanya base/pack) |
| Progres Cutting | `POST /api/cutting/orders/{id}/progress` (`input_uom` **baru**) | satuan pemakaian kain (rol/gram/yard) |

* **Satu endpoint opsi satuan** untuk semua layar: `GET /api/rahaza/materials/uom-options?material_ids=`
  (batch, di-cache di FE lewat `hooks/useUomOptions.js`). Alias ganda (`gr/g/kgs/metre/…`) disembunyikan.
* **Cakupan konversi diseragamkan** — helper baru `core/bom_uom.factor_to_base()` (kemasan master +
  satuan global sedimensi + kain m⇄kg via gramasi & lebar) sekarang dipakai `stock_service._conv` dan
  ketujuh titik di atas. Sebelumnya tiap titik memakai `core.uom.factor_of` yang HANYA tahu kemasan
  material, jadi "gram"/"yard" ditolak padahal BOM & Costing sudah lama bisa mengonversinya.
* **Satuan asing tetap ditolak 400** dengan pesan yang menyuruh melengkapi kemasan di Master Material —
  tidak pernah diam-diam dihitung 1:1 pada jalur stok.
* **BUG NYATA ditemukan & ditutup**: `PUT /api/rahaza/material-issues` memanggil `_norm_mi_items` TANPA
  peta master material ⇒ `qty_uom` **diabaikan diam-diam** (2 box tersimpan sebagai 2 pcs). Sekarang
  sama dengan jalur POST.
* Komponen UI bersama: `components/erp/uom/UomPicker.jsx` (`UomSelect`, `UomConversionHint`).
  Default = satuan dasar ⇒ **perilaku lama tidak berubah** bila operator tidak memilih apa pun.
* Alat baru: `tests/flow_uom_entry_points_ui_test.py` (**38/38**) · data demo `scripts/seed_uom_ui_demo.py`
  (kemasan 1 box = 12 pcs / 1 pak = 100 pcs / 1 rol = 25 kg, movement inbound, MI draft, order cutting).

### B2. PENOMORAN DOKUMEN TAHAP 2 — 11 penghasil nomor manual dipusatkan
Peta `scripts/map_document_numbers.py`: **18 → 7 temuan**, dan 7 sisanya memang BUKAN nomor dokumen
(kode rak `wms_structure`, tahun/bulan analitik livehost, seeder demo `rahaza_admin_helpers`, berkas uji).
Yang dipindah ke `utils.counters.gen_prefixed_number` (race-safe + **formatnya bisa diatur owner**):
PO pembelian · GR penerimaan · AP dari GR · klaim biaya karyawan · permohonan perjalanan dinas ·
penyelesaian dinas · PO maklon (`{KLIEN}`) · pengiriman maklon ke klien (`{KLIEN}`) · invoice maklon
manual (`{PREFIX}`) · invoice maklon otomatis (AR) · job vendor. Katalog layar **34 → 45 jenis**.
* Parameter baru `config_key` menutup kasus **dua jenis nomor menumpang satu koleksi+field**
  (`rahaza_ar_invoices.invoice_number` dipakai AR Finance *dan* invoice maklon) — tanpa itu satu format
  akan menimpa keduanya. Registry mendukung `collection`/`field` eksplisit (`target_of()`).
* Kontinuitas nomor dijaga oleh lazy-init `gen_prefixed_number` (membaca nomor tertinggi yang sudah ada).
* Alat baru: `tests/flow_doc_numbering_phase2_test.py` (**19/19**, termasuk **25 permintaan nomor
  bersamaan → 25 nomor unik**/INV-CNT-1, dua format berdampingan, dan reset ke bawaan).

### B3. DASHBOARD MAKLON — alur produksi maklon akhirnya terpasang
`GET /api/prod/dashboard?business_type=maklon` sudah ada sejak lama tetapi **belum pernah dipakai layar
mana pun**. Sekarang: tab **"Alur Produksi"** di Dashboard Maklon + pintu menu `maklon-alur-produksi`,
memakai komponen yang SAMA dengan Portal Produksi (`ProductionDashboardOverview`, hanya `businessType`
berbeda ⇒ nol duplikasi logika/angka). Label tahap akhir otomatis **"Dispatch ke Buyer"**. Klik tahap
"Cutting" terbukti berpindah ke Portal Cutting. `StatusBadge`/`STATUS_CONFIG` dipindah ke scope modul
(menghapus 1 pelanggaran `no-unstable-nested-components`).

### Perbaikan gate: INV-18 merah di container segar (bukan regresi sesi ini)
Seeder demo membuat dokumen **dispatch ke buyer LANGSUNG di DB** tanpa pernah mencatat hasil produksi
ke stok FG, sehingga invarian "setiap dispatch sudah mengurangi stok FG" selalu MERAH di container baru
(3 SJ demo). Flag baru `scripts/repair_selisih_ssot.py --topup-fg` (**KHUSUS DATA DEMO**) menambahkan
stok FG yang belum tercatat lalu menjalankan mutasi keluar lewat SSOT; dipanggil otomatis dari
`scripts/seed_demo_all.sh`. Untuk data nyata owner flag ini TIDAK boleh dipakai — di sana kekurangan
stok berarti ada QC/dokumen yang belum diselesaikan.

### Bukti (dijalankan ulang sesi ini)
`flow_rnd_uom_test` **38/38** · `flow_uom_entry_points_ui_test` **38/38** ·
`flow_doc_numbering_phase2_test` **19/19** · `poc_uom_entry_points` **11/11** ·
`bash scripts/gate.sh` **13/13 HIJAU** · `verify_uom_integrity` HIJAU (518 objek) ·
`check_nav_map` HIJAU (189 pintu / 372 id) · testing agent iterasi 12 & 13 **0 bug kritis** ·
14 portal dibuka di browser: **0 layar putih, 0 pageerror** · residu data uji **0**.

---

## 2026-08-01 — SELISIH KIRIM JADI WARGA KELAS SATU (GAP A–G dari HANDOFF_SELISIH_CMT_BUYER SELESAI)

Implementasi 7 gap yang ditelusuri sesi sebelumnya, memakai **keputusan owner 2026-08-01**:
selisih kirim BUKAN klaim finansial otomatis — penyebab tersering salah input progres / barang
ketinggalan, jadi **dokumen dikoreksi ke kenyataan** dan barangnya **dikirim ulang**; keputusan
finance (ditanggung CMT / DA) hanya untuk barang yang dinyatakan hilang (di sisi buyer: saat PO
ditutup). Koreksi boleh sepihak Admin DA + **notifikasi vendor** (tanpa sanggahan). **Tanpa batas
waktu** — selisih tetap `open` sampai diselesaikan.

| Gap | Yang dikerjakan | Bukti |
|---|---|---|
| **A+C** | Dokumen selisih `cmt_short_shipments` (`SEL-CMT-xxxxx`) + field buku kuantitas `qty_claimed_by_vendor` / `qty_short_open` / `qty_short_resolved`. `qty_declared` kini HANYA barang yang benar-benar sampai (`accepted+reject`); klaim vendor dipisah (`cmt_receipt_lines.qty_claimed_by_cmt`). Deklarasi vendor (`buyer_shipment_items.qty_shipped`) dirambatkan otomatis + `edit_history`, sisa kirim vendor NAIK lagi | A3a–A3h, A4a–A4b |
| **B** | `PUT /api/prod/cmt-receipts/{id}/lines/{lid}` setelah QC selesai → **409** (dulu 200 & angka bercabang) + dua fitur koreksi resmi: `…/koreksi-hasil-qc` (stok FG ikut dikoreksi lewat SSOT stok, `koreksi_history`, resync buku kuantitas) dan `…/koreksi-deklarasi` (klaim vendor + rambatan dokumen + notifikasi) | A5, B2a–B2d, B3 |
| **C** | Kiriman ULANG: setiap dispatch deklarasi vendor kini membuat penerimaan DA sendiri (`related_dispatch_seq`) — dulu hanya dispatch pertama. Barang yang sampai MENUTUP selisih lama otomatis (FIFO, `resolution='dikirim_ulang'`) | A6a–A6d |
| **D** | PDF Surat Jalan buyer: header memuat **daftar semua No. PO**, tabel dapat kolom **No. PO**, ada **SUBTOTAL per PO** (SJ gabungan & per-dispatch) | D1c–D1d |
| **E** | **Stok FG BERKURANG saat kirim ke buyer** (`core/production_qty_ledger.issue_fg` → `stock_service.issue`, `rahaza_fg_movements` OUT, idempoten per baris dispatch) + pre-check stok sebelum dokumen dibuat + pembalikan saat force-edit qty & saat SJ dihapus | C1a–C1b, edge 7a/8a |
| **F** | Kapasitas kirim ulang memakai **satu** definisi: qty EFEKTIF DITERIMA (`qty_received` ?? `qty_shipped`) | C3a, C3d |
| **G** | Selisih terima buyer `buyer_short_records` (`SEL-BYR-xxxxx`): dokumen SJ dikoreksi ke qty diterima, barang **kembali ke stok FG** (siap kirim ulang), notifikasi Admin+Finance, keputusan `tanggungan_cmt` / `tanggungan_da` (stok dihapusbukukan) / `dikirim_ulang` / `dibatalkan`; `close-short` kini SAH dari status **`Completed`** (penyesuaian pasca-penutupan) | C2a–C2d, E1a–E2b |

**Perbaikan turunan (ditemukan saat implementasi):** `buyer_shipment_items` menampung DUA hal
(deklarasi vendor→DA dan dispatch DA→buyer) tetapi dulu dijumlahkan jadi satu angka, sehingga begitu
DA mengirim ke buyer "sisa kirim" vendor ikut habis. Sekarang dipisah
(`total_declared_to_da` / `total_received_by_da` vs `total_shipped_to_buyer`).

**Invarian baru** (`scripts/verify_produksi_maklon_invariants.py`, plus mode `--audit-only` yang
bisa dijalankan atas data nyata tanpa membuat data uji):
* **INV-16** klaim vendor = yang sampai + selisih terdokumentasi
* **INV-17** tidak ada selisih kirim tanpa dokumen penyelesaian
* **INV-18** setiap dispatch ke buyer sudah mengurangi stok FG

**Alat baru:** `tests/scenario_selisih_ssot.py` (43 pemeriksaan, acceptance aturan owner) ·
`tests/backend_test_selisih_edge_cases.py` (12 kasus tepi) · `scripts/repair_selisih_ssot.py`
(perbaikan data lama: koreksi dokumen + backfill dokumen selisih + backfill mutasi stok FG keluar +
rekalkulasi buku kuantitas; `--dry-run` / `--apply`).

**UI:** `Terima FG dari CMT` (KPI "Belum sampai", panel Selisih Kirim + tombol Selesaikan, kolom
Klaim vendor / Sampai (dokumen) / Belum sampai, tombol **Koreksi hasil QC** & **Koreksi deklarasi**) ·
`Surat Jalan Buyer` (panel Selisih Terima Buyer + tombol Putuskan, laporan selisih dengan kolom
"Belum sampai" & KPI open) · `Portal Vendor CMT` (panel + banner kewajiban "BELUM SAMPAI di DA",
kolom Klaim kirim / Diterima DA / Belum sampai).

**Verifikasi:** `tests/scenario_selisih_ssot.py` **43/43** · `tests/backend_test_selisih_edge_cases.py`
**12/12** · `bash scripts/gate.sh` **13/13 HIJAU** · `verify_produksi_maklon_invariants.py --audit-only`
**INV-13…INV-18 hijau** · `recompute_qty_ledger.py --dry-run` bersih · UI diverifikasi di BROWSER
(termasuk submit kedua modal koreksi → toast + angka DB berubah konsisten).

---

## 2026-07-31 (sesi lanjutan) — PENELUSURAN TUNTAS: SELISIH KIRIM CMT→DA & SELISIH TERIMA DA→BUYER

Owner meminta verifikasi 3 skenario nyata di Portal Produksi/Maklon/Vendor CMT (bukan klaim dokumen).
Penelusuran dilakukan **empiris**: PO dibuat lewat API asli, alur lengkap dijalankan, angka dibaca dari
DB, lalu DB dipulihkan dari snapshot (0 sisa data uji). Hasil ⇒ **`memory/HANDOFF_SELISIH_CMT_BUYER.md`**
(dokumen utama untuk sesi berikutnya) + BUG-6…BUG-9 di `memory/BUG_REGISTRY.md`.

**Aturan bisnis yang DITEGASKAN owner (sebelumnya disalahpahami agent):**
`reject` (barang sampai tapi cacat) **≠** `selisih kirim` (barang tidak sampai).
Untuk selisih kirim: dokumen deklarasi vendor WAJIB dikoreksi ke qty nyata (100 → 90), 10 pcs sisanya
tetap **kewajiban vendor** untuk dicari, dan harus ada penyelesaian yang tercatat. Kebijakan
"progress vendor tetap 100" HANYA berlaku untuk kasus reject.

**Yang terbukti SUDAH BENAR:** reject → karantina → permak (sendiri/retur CMT) → `SJ-RWK-00001` →
buku kuantitas · surat jalan buyer **GABUNGAN 5 PO / 500 pcs** (`SJ-BYR-202607-0001`, `consolidated=true`,
laporan selisih per PO, pagar over-ship 400) · pencatatan qty diterima buyer + riwayat + alasan ·
`close-short` → PO `Closed Short` + **AR draft otomatis disesuaikan ke qty diterima**.

**Yang terbukti BELUM ADA / BUG (7 gap, 4 P0):**
A selisih kirim tanpa identitas & tanpa kewajiban vendor · B `PUT` baris penerimaan setelah QC selesai
diterima diam-diam (data bercabang) · C tidak ada fitur koreksi (penerimaan tambahan membuat
`qty_declared` 110) · D PDF SJ gabungan tanpa No. PO (header kosong, tabel tanpa kolom PO) ·
E **stok FG tidak berkurang saat kirim ke buyer** (bukti: 100 pcs dikirim, stok tetap 100) ·
F selisih buyer tidak membuka kapasitas kirim ulang (dua pagar, dua definisi) · G selisih buyer tanpa
tindak lanjut & `close-short` ditolak bila PO sudah `Completed` (status final).

**Alat baru:** `tests/scenario_owner_questions.py` (reproduksi 3 pertanyaan owner) ·
`tests/scenario_q3_natural.py` (alur alami tanpa Quick Complete → close-short/AR).
**Menunggu keputusan owner:** 4 pertanyaan kebijakan (siapa menanggung selisih, perlu persetujuan
vendor atau tidak, batas waktu penyelesaian) — §8 dokumen handoff.

---


## 2026-07-31 — RESTORE PORTAL DIPERBAIKI: penjaga limit FD mongod + pesan kegagalan informatif

Repo di-clone ke container baru, database dipulihkan dari file backup milik user lewat **jalur resmi
portal** (`POST /api/admin/backup/upload-file` → `POST /api/admin/backup/restore`). Dari situ ketemu
**bug nyata**: restore lewat Portal Administrasi Sistem **SELALU gagal HTTP 500 dengan `detail` KOSONG**
(`Restore error: 500: Restore failed: `).

**Akar (dua lapis):**
1. supervisord menjalankan `mongod` dengan soft limit `RLIMIT_NOFILE` **1024**. Restore 186 koleksi
   membuat WiredTiger memanggil directory-sync → `errno 24 Too many open files` →
   `WT_PANIC: the process must exit and restart` → **mongod abort (fassert)** → `mongorestore` terputus
   (`connection closed unexpectedly by the other side: EOF`). Konfigurasi supervisor **READ-ONLY**,
   jadi `minfds` tidak bisa diubah.
2. `scripts/restore.sh` mengarahkan stderr mongorestore ke stdout (`2>&1`) sehingga `result.stderr`
   SELALU kosong; endpoint hanya memakai stderr, lalu `except Exception` menelan `HTTPException`
   miliknya sendiri (dobel bungkus) → sebab kegagalan hilang total dari mata user.

**Fix:**
1. `backend/utils/mongod_fdlimit.py` (**BARU**) — naikkan soft limit nofile mongod via syscall
   `prlimit64` (fallback biner `prlimit`). Dipasang di: **startup backend**, job APScheduler
   **`mongod_fd_guard` (tiap 5 menit)**, dan **tepat sebelum** setiap backup/restore. Idempoten,
   tidak pernah menurunkan hard limit, tidak pernah melempar exception ke pemanggil.
   Skrip manual: `scripts/ensure_mongod_fdlimit.sh` (juga dipanggil `bootstrap.sh` langkah 1c).
2. `routes/admin_backup.py` — analisa **gabungan stdout+stderr**, 8 pola sebab diterjemahkan ke
   bahasa manusia + saran perbaikan (`_diagnose`), kode warna ANSI dibuang, log lengkap disimpan ke
   `/app/backups/<id>/restore_<ts>.log`, dan `except HTTPException: raise` menghentikan dobel-bungkus.
   Berlaku juga untuk `/create` (backup) dan `/restore-selective` (per-koleksi ikut berisi sebab+saran).
3. `components/erp/BackupRestoreModule.jsx` — panel error di dialog restore (Sebab / Saran perbaikan /
   kode keluar / log teknis yang bisa dibuka / path log), warna aman untuk tema terang & gelap,
   dialog **sengaja tetap terbuka** saat gagal supaya rincian terbaca.

**Bukti:** `python3 tests/verify_backup_restore_fix.py` **15/15 PASS** · restore asli lewat endpoint
**3.756 dokumen, 0 gagal** · setelah `supervisorctl restart mongodb` (limit balik ke 1024) endpoint
restore menaikkan sendiri **1024 → 200000** lalu sukses · panel error terbukti tampil di browser
(Playwright, tema terang) · auto-backup scheduler `auto_20260731_190000` sukses · login 6 akun
HTTP 200 · **186 koleksi utuh** (35 user, 1.043 material, 26 karyawan, 742 baris stok).

**Catatan operasional:** limit FD kembali ke 1024 setiap mongod restart — itu WAJAR dan sudah
ditangani penjaga otomatis di tiga titik di atas; tidak perlu tindakan manual.

---


## 2026-07-31 — FASE 22: verifikasi UI 7 keluhan owner + AUDIT RELASI DATA (sesi lanjutan)

Repo di-clone ulang ke container baru dan dilanjutkan dari titik iterasi 8 (testing agent belum
selesai memverifikasi UI). Hasil akhir: `gate.sh` **13/13 HIJAU**,
`verify_produksi_maklon_invariants.py` **16/16 HIJAU** (3 invarian baru), testing agent
iterasi 9 + 10 memverifikasi **7/7 keluhan owner di browser**, regresi **14 portal** bersih.

### Cacat yang BARU ditemukan & diperbaiki sesi ini (semuanya lolos dari sesi sebelumnya karena
### semua endpoint tetap menjawab HTTP 200)
1. **"Perbaikan hantu"** — dropdown Varian PO Maklon diperbaiki di `MaklonPOModule.jsx`, modul yang
   sudah lama TIDAK BISA DIBUKA (`registry: 'maklon-po' → 'maklon-pos-engine'`). Perbaikan nyata
   dipindah ke `engine/ProductionPOModule.jsx` (label `Navy · M — ARN-HD-NVY-M`, konfirmasi SKU
   hijau, testid `po-item-*`), modul mati diarsipkan ke `components/erp/_archive/`.
2. **`engine/DataTable.jsx` mengabaikan `onRowClick`** — prop diterima tapi tidak pernah dipasang ke
   `<tr>`, sehingga baris Surat Jalan Buyer TIDAK BISA di-expand → owner menyimpulkan
   "child shipment tidak bisa diambil datanya" (keluhan #6). Sekarang dipasang + tombol expand
   eksplisit + panel rincian per PO / sumber penerimaan / child shipment.
3. **Referensi vendor YATIM (7 dokumen)** — satu seeder memaku `vendor_id="demo-vn-jmc"` sementara
   master JMC ber-id `mk-vendor-demo-1`; job PO-INT-DEMO-4 tidak pernah muncul di Portal Vendor.
   Alat: `scripts/repair_orphan_vendor_refs.py`, dijaga **INV-13**.
4. **Buku kuantitas menggantung** — `qty_accepted 190 > produced 145` (mustahil). Alat:
   `scripts/recompute_qty_ledger.py` (bangun ulang dari penerimaan + permak), dijaga **INV-14**.
5. **2 Surat Jalan REWORK yatim** (permak sudah dihapus) — pembersih otomatis + **INV-15**.
6. **Kartu KPI "Terima FG dari CMT" per-tab** — menampilkan "Lolos QC 0 / Reject 0" saat tab
   Sedang QC walau ada 30 pcs reject di layar yang sama. Sekarang dari endpoint `summary` (global,
   + `pcs_accepted_total` / `pcs_reject_total` / `uncounted_lines`).
7. **Portal Vendor: baris job kosong** — expand hanya menulis "Klik Detail Lengkap untuk melihat
   semua item"; sekarang item dimuat inline dengan kolom Lolos QC DA / Reject / Rework.
8. **Surat jalan REWORK berlabel "Pengiriman Awal"** di portal vendor → `🔄 Retur Perbaikan
   (Rework)`; sisi admin dapat badge `🔄 REWORK`.
9. **Jebakan logout portal vendor/klien** — sesudah vendor logout, layar login vendor muncul dan
   akun admin ditolak TANPA jalan keluar (ini yang mematikan sesi pengujian iterasi 9). Sekarang
   logout kembali ke login utama, akun non-vendor dialihkan, + tautan "Masuk ke aplikasi utama".
10. **Seeder demo selalu mati di container segar** (`E11000 duplicate key code_1`) — sekarang
    mengadopsi master yang sudah ada (klien/vendor/model/lokasi/karyawan/BOM).
11. **Data demo memakai status legacy "Approved"** & tanpa `vendor_id`/ledger → dikanonikkan
    (`completed_qc`) dan dibuat konsisten dengan buku kuantitas.
12. **Deklarasi vendor (`SJ-CMT-DA-…`) tercampur** di daftar pengiriman ke buyer (ikut menghitung
    KPI) → saringan `Ke Buyer / Deklarasi Vendor → DA / Semua` + badge `VENDOR → DA`.

### Data demo baru (lewat endpoint asli, bukan tulis mentah)
- `scripts/seed_cmt_qc_flow_demo.py` — penerimaan `on_qc` siap dihitung inline + penerimaan
  `completed_qc` dengan reject bercabang (permak sendiri selesai, retur ke CMT → SJ-RWK, sisa di
  Antrean Reject); menghormati sisa kapasitas produksi.
- `scripts/seed_consolidated_buyer_shipment_demo.py` — 2 PO maklon PT Aruna → **1 Surat Jalan
  Buyer GABUNGAN** (`SJ-BYR-202607-0005`, 2 PO, 2 sumber penerimaan). Menutup temuan CONS-2.
- `scripts/archive_legacy_cmt_jobs.py` — 4 job CMT tanpa PO **diarsipkan** (keputusan owner):
  hilang dari KPI & laporan, tetap tersimpan di DB (`--restore` tersedia).
- `scripts/seed_demo_all.sh` kini menjalankan seluruh rantai + audit relasi di akhir.

## 2026-07-27 — SESI #7: UOM tuntas · Asisten ERP sadar-portal · Penomoran Dokumen · Backup lanjutan · Dashboard Produksi

Enam pekerjaan yang disetujui owner, semuanya diverifikasi lewat skrip POC + testing_agent
(`/app/test_reports/iteration_6.json`: backend 26/26, frontend semua elemen terverifikasi, 0 bug).

### A1 — `input_uom` di titik masuk stok terakhir
- `wms_putaway.py` (`POST /place`) dan `wms_opname3.py` (`/scan`, `/scan-undo`) kini menerima
  field OPSIONAL `input_uom`; angka dikonversi ke satuan dasar lewat SSOT `core/uom.py`,
  jejaknya disimpan (`input_qty`, `input_uom`, `uom_factor`). Tanpa field itu perilaku lama
  tidak berubah sama sekali. Satuan asing → 400, bukan 500.
- **Tiga file lain di daftar handoff sengaja TIDAK diubah** setelah diperiksa:
  `dewi_accessories_loans.py` & `dewi_accessories_requests.py` seluruh endpoint-nya sudah 410
  (mati, tidak lagi memutasi stok); `dewi_warehouse_smart.py` hanya MEMBALIK delta yang sudah
  tersimpan dalam satuan dasar — menambah konversi di sana justru akan jadi bug ganda-konversi.
- Bukti: `scripts/poc_uom_entry_points.py` **11/11**.

### A2 — Kolom kemasan di Ekspor/Impor Excel material
- Registry `data_transfer.py` bertambah `base_uom`, `pack_unit`, `pack_size`, `display_in_packs`
  → 478 item bisa diisi lewat satu berkas.
- Helper baru `_material_uom_fields()`: membangun `uoms` dari kolom Excel (bukan sekadar menulis
  cermin legacy — `apply_payload` akan mengabaikan pack baru bila `uoms` lama masih ada),
  mempertahankan tingkat kemasan lain (mis. karton) yang tidak disebut di berkas, dan otomatis
  menyetel purchase/issue/display UOM.
- **Pengaman inti**: mengganti `base_uom` item yang MASIH BERSTOK ditolak dengan pesan
  mengarahkan ke tombol *Ubah Satuan Dasar* — mencegah angka stok/HPP jadi salah diam-diam.
- Panduan owner: `docs/PANDUAN_UOM_EXCEL.md`.

### A3 — Daftar kerja rebase satuan dasar
- `scripts/uom_rebase_worklist.py` (`--export` / `--preview` / `--apply`) menghasilkan tepat
  **91 item** bersatuan kemasan (74 rol · 14 pak · 3 lusin). Menerapkannya memanggil endpoint
  rebase resmi — tidak ada logika kedua.

### B2 — Asisten ERP CV. Dewi Aditya (sadar portal, hemat biaya)
- Nama "Triyasa" **dihapus total** dari kode (nama itu keliru; perusahaan = CV. Dewi Aditya).
- Basis pengetahuan STATIS 12 portal: `backend/data/portal_kb/*.json` (ringkasan, prinsip,
  alur berlangkah, katalog modul, FAQ, saran pertanyaan).
- Mesin jawab `services/portal_assistant.py`: skor frasa-kunci + irisan kata, portal aktif
  diprioritaskan, portal lain didiskon 0,7×, dan `_intent_weight()` memastikan pertanyaan
  "bagaimana/cara" dijawab ALUR (langkah bernomor), bukan deskripsi fitur.
- Endpoint `routes/portal_assistant_routes.py`: `GET /api/assistant/context`,
  `POST /api/assistant/ask`, `GET|DELETE /api/assistant/history`. Riwayat per sesi tersimpan.
- Widget `AIChatbotWidget.jsx` menerima `portal` + `moduleId` dari `App.js`, menampilkan konteks
  portal, saran dinamis, lencana sumber (Panduan sistem / Dijawab AI), dan tautan lanjutan.
- **95% pertanyaan dijawab tanpa AI** (gratis, instan, tidak mengarang).

### B2b — SEMUA AI pindah ke Anthropic SDK resmi (permintaan owner)
- `ai_cost_tracker.tracked_llm_call()` — satu-satunya pintu LLM — sekarang memanggil
  `anthropic.AsyncAnthropic` langsung, memakai `usage.input_tokens/output_tokens` NYATA
  (sebelumnya perkiraan). `emergentintegrations` tidak dipakai lagi untuk teks.
- Model per tier: `claude-opus-4-8` (executive) · `claude-sonnet-5` (standard) ·
  `claude-haiku-4-5-20251001` (light).
- Kunci dibaca dari `ANTHROPIC_API_KEY`. Pemanggil lama yang masih meneruskan `EMERGENT_LLM_KEY`
  otomatis diabaikan (hanya kunci `sk-ant-` yang diterima).
- **`ANTHROPIC_API_KEY` MASIH KOSONG** — owner belum memberikannya. Semua fitur AI gagal dengan
  anggun (503 + pesan Indonesia), tidak ada layar yang rusak.

### B3 — Penomoran Dokumen & SKU
- `scripts/map_document_numbers.py` memetakan lebih dulu: 39 jenis dokumen race-safe lewat
  `gen_prefixed_number` + 18 penomoran manual (mayoritas sudah counter-based).
- `utils/counters.py`: `render_format()` (token `{YYYY} {YY} {MM} {DD} {SEQ:n}` + token konteks),
  `validate_format()`, `resolve_format()` (cache 10 dtk), `resolve_master_code()` (SKU tanpa urut).
  **`gen_prefixed_number` menjadi sadar-konfigurasi** → 35 jenis dokumen langsung bisa diatur
  TANPA menyentuh satu pun dari 85 pemanggilnya, dan tetap satu-satunya generator.
- Format rusak di DB **tidak pernah memblokir transaksi** — otomatis jatuh ke format bawaan kode.
- `data/doc_number_registry.py` (katalog + label + token), `routes/doc_numbering.py`
  (list/preview/save/reset/set-counter, khusus admin), `DocNumberingModule.jsx` (menu baru
  `sys-doc-numbering` di Portal Administrasi Sistem).
- Penurunan nomor urut ditolak bila sudah ada dokumen memakai awalan yang sama.
- Bukti: `scripts/poc_doc_numbering.py` **12/12**.

### B4 — Backup lanjutan: jelajah & kosongkan koleksi
- `GET /api/admin/backup/live-collections` — 187 koleksi DB aktif + jumlah dokumen +
  pengelompokan (`data/collection_registry.py`) + tanda terlindungi.
- `POST /api/admin/backup/clear-collections` — pengaman berlapis: super admin saja · ketik persis
  `KOSONGKAN` · koleksi fondasi (users/roles/counters/doc_number_configs/COA/`*_settings`)
  ditolak kecuali `allow_protected` · cadangan pengaman dibuat lebih dulu (default menyala) ·
  gagal membuat cadangan = pengosongan dibatalkan.
- Tab baru "Koleksi Database" (`DatabaseCollectionsPanel.jsx`) di layar Backup. Checkbox koleksi
  terlindungi **dinonaktifkan** sampai kuncinya dibuka sadar-risiko.

### B1 — Dashboard Produksi dirombak
- Grafik WIP per proses internal (Cutting→Sewing→Finishing→QC→Packing) **DIBUANG**: jahit
  dikerjakan vendor CMT dan Cutting punya portal sendiri, jadi angkanya selalu nol & menyesatkan.
- Endpoint agregat baru `GET /api/prod/dashboard` (satu panggilan, dipakai internal & maklon)
  memetakan perjalanan barang: **Rencana PO → Cutting → Di Vendor CMT → Terima & QC → Permak →
  Serah Terima FG**, plus rincian cutting (rendemen), beban per vendor CMT, mutu (tingkat cacat),
  dan daftar PO paling lama tidak bergerak.
- `ProductionDashboardOverview.jsx` ditulis ulang: 5 KPI, kartu perjalanan barang yang bisa
  diklik ke modulnya, tiga kartu rincian, pemilih periode 7/30/90 hari.
- Bukti: `scripts/poc_production_dashboard.py` **20/20** (skenario lengkap ditanam lalu dibersihkan).

### Verifikasi
Semua guardrail HIJAU: `check_nav_map` (2245) · `verify_uom_integrity` (1761) ·
`verify_rbac_idor` (699) · `verify_adversarial_5xx` · `verify_platform_lint_engine` ·
`verify_unreachable_code`. testing_agent iterasi 6: backend **26/26**, 0 bug kritis, 0 bug UI.

## 2026-07-26 — SESI LANJUTAN #6 (repo `gananmakajana/da`): FASE 20 (kontrak FE↔BE)

**Pemicu:** sesi sebelumnya berhenti saat menelusuri *"the 7 genuinely broken FE calls"*
dari temuan advisory `fe_be_contract` (92 WARN, 3 sesi ditulis sebagai "tech-debt").

**8 bug produk NYATA ditutup** (semua kelas "404 senyap / fitur mati diam-diam"):
- `/api/rahaza/master/employees` (4 titik: AIActions, HRAsset ×2, WMSPickList) → `/api/rahaza/employees`.
  **Bukan cuma URL** — endpoint benar membalas `{items}` sedangkan FE membaca `.rows`/`.employees`.
- `/api/finance/coa` → `/api/rahaza/coa/accounts` + parse ARRAY (dropdown akun GL tadinya kosong).
- `/api/rahaza/overtime-requests` **GET + POST** → `/api/rahaza/overtime` + kunci `.overtime`
  (GET-nya dibungkus `.catch()` ⇒ 404 tertelan; POST-nya membuat semua pengajuan lembur gagal).
- `/api/rahaza/payroll-runs/{id}/export`: implementasinya **ADA tapi jadi KODE MATI** di dalam
  `export_run_excel()` setelah `return` ⇒ dekorator hilang. Diekstrak jadi `export_run_csv`;
  FE beralih dari `window.open` (tak bisa kirim header Authorization) ke `downloadWithAuth`.
- `POST /payroll-runs/{id}/payslips/{sid}/adjust` **dibuat** (`manual_deduction`/`adjustment_notes`
  nol kemunculan di backend sebelumnya); FE kini memeriksa `res.ok` + input catatan diaktifkan.
- `/api/collab/link-preview` → `/api/collab/search/link-preview`.
- `/api/dewi/assets/by-code/{code}` → `/api/assets/scan-by-number/{n}` (**salah domain**:
  pemanggilnya membaca `asset_number`/`location` ⇒ aset TETAP, bukan aset karyawan) +
  `re.escape` supaya payload scan bersimbol regex → 404, bukan 500.
- `POST /orders/{id}/generate-work-orders`: **tombol dihapus, endpoint TIDAK dibuat** — engine
  `rahaza_work_orders` sengaja dipensiunkan FASE 4 (E10 DELETE); jalur pengguna sudah ada
  lewat `OnwardCTA → prod-work-orders`.

**Bug UANG yang ikut ditutup:** `PUT /payslips/{pid}` mengubah angka slip **tanpa** menyinkronkan
header run, padahal `post_payroll_run()` menyusun **jurnal GL dari header** ⇒ jurnal saat finalize
salah. SSOT baru `_payslip_totals()` + `_recompute_run_totals()` (`rahaza_payroll_shared.py`).

**4 blindspot GATE-nya sendiri ditutup** (gate menyembunyikan sebagian bug di atas):
- `_seg_match()` SIMETRIS ⇒ `{}` sisi FE dianggap wildcard, jadi `/assets/by-code/{}` "cocok"
  dengan `/assets/{}/assign`. Dibuat **asimetris**: 92 → **140** temuan (48 tak pernah terlihat).
- Route **WebSocket** tak ada di OpenAPI ⇒ `/api/comm/ws` selalu dituduh mati (false positive
  permanen). Sekarang dipanen dari sumber, termasuk router yang diimpor dari modul lain.
- Konstanta `const BASE = ${API}/api/...` dihitung sebagai panggilan ⇒ kode `FE_BASE_PREFIX` (INFO).
- `fe_calls()` membaca **KOMENTAR** ⇒ menulis "dulu `/api/x`" membuat gate melaporkan path yang
  justru sudah diperbaiki. Komentar kini dinetralkan (jumlah baris dipertahankan).

**Guardrail baru `INV-DEADCODE-01`** (`scripts/guardrails/verify_unreachable_code.py`, BLOCKING,
ter-wire di `gate.sh` + `guard.sh`): mendeteksi **"handler tergabung"** — statement mati setelah
`return` yang memuat `return` lain. CHECK D buta terhadap ini (tak ada `def` baru).
Membedakan `raise`-di-awal (pola deprekasi K5 yang SENGAJA → INFO) dari `return` (→ HIGH).

**Pembersihan O1.2 yang tertunda:** `CMTManagementModule`, `CMTProgressModule`, `CMTPackingModule`
(sudah lama di-comment di `moduleRegistry.js` dengan catatan "Diarsip kelak", tapi file-nya masih
memanggil 16 endpoint `/api/dewi/cmt/*` yang tak ada) → dipindah ke `_archive/`.

**Alat baru:** `scripts/triage_fe_dead_calls.py` (bucket ARCHIVE/DEADCODE/ARTIFACT/BASE_PREFIX/
DYNAMIC/REAL_404, setiap bucket sisa **dibuktikan** benign).

**Bukti:** `verify_fase20.py` **105 PASS / 0 FAIL** · `_prove_fase20_sentinel_red.sh` **4/4 MERAH**
lalu hijau lagi · `gate.sh` **10/10 HIJAU** · `run_all_verifications.sh` **514 PASS / 0 FAIL** ·
testing_agent_v3 iter_178 (backend **22/22**, 0 bug kritis, 0 bug UI) · `REAL_404 = 0` (dari 11) ·
`DEADCODE = 0` (dari 16) · `yarn build` Compiled successfully · baseline aksesoris tetap
**Rp 9.663.750** (nol drift) · Buku Besar seimbang.

**2 TEMUAN TAMBAHAN yang hanya muncul saat diverifikasi lewat UI/DB (bukan dari gate):**
- **Mismatch FIELD-level — semua kolom uang payslip Rp 0.** Gate kontrak hanya memeriksa PATH,
  jadi ini lolos total. FE membaca skema payslip LAMA (`base_salary`, `transport_allowance`,
  `meal_allowance`, `production_bonus`, `overtime_pay`, `total_deductions`, `net_salary`)
  sementara backend menulis (`earnings_total`, `allowance_total`, `overtime_amount`,
  `deductions_total`, `net_pay`). Diperbaiki di `RahazaPayrollRunModule.jsx` (kolom
  `Transport`/`Bonus Prod.` dihapus karena backend tak memisahkannya; ditambah `Bruto`),
  `PortalSayaPayslip.jsx` & `SelfServicePortal.jsx` (dua layar milik KARYAWAN sendiri).
  Nama lama dipertahankan sebagai fallback. Diverifikasi BUKAN bug: `RahazaHRReportsModule.jsx`
  (endpoint `hr/reports/payroll-summary` memang menghasilkan nama itu). Dijaga C7 (statik) + C8
  (runtime, membuat payroll run sendiri lalu menghapusnya).
- **Drift dari ALAT UJI, termasuk jurnal GL POSTED fiktif.** Testing agent mengklaim "All test
  data cleaned up successfully" — keliru: `PR-20260726-001` FINALIZED tertinggal (karena
  `DELETE /payroll-runs/{id}` hanya izinkan `draft` ⇒ gagal dalam diam), beserta **jurnal
  `JE-20260728-0001` POSTED Dr Rp 45.031.214** + 3 baris mirror, dan 1 request lembur pending.
  Ditutup dengan **`scripts/cleanup_fase20_qa.py`** (idempoten, `--dry-run`/`--apply`, bagian 4
  pemburu jurnal GL yatim): 24 dokumen dihapus; total debit Buku Besar 51.760.589 → 6.729.375
  (tepat sebesar jurnal fiktifnya), Dr == Cr tetap seimbang.

**Perbaikan alat:** deteksi "modul tak terjangkau" di `triage_fe_dead_calls.py` tadinya
**tidak pernah aktif** — pemakaian identifier dihitung `findall(ident) > 1` padahal pada baris
deklarasi namanya muncul dua kali (`const X` dan `import('./X')`). Setelah span deklarasi
dikecualikan: 0 → 18 modul terdeteksi (mis. `RahazaOrdersModule`), sementara `AIActionsModule`
tetap dianggap AKTIF karena dirender `hubs/HRAIHub.jsx`. Dijaga dua arah oleh B3b.

**Pelajaran kunci:** *menguji helper ≠ menguji pemakaiannya* — proof merah iterasi pertama hanya
2/4 karena assert-nya memanggil helper langsung, bukan memeriksa bahwa GATE memakainya.
Dan: *gate kontrak path-level tidak melihat mismatch field-level* — buka layarnya.



**FASE 16 — Absen wajib selfie+lokasi & izin berpersetujuan**
- SSOT baru `backend/utils/attendance_policy.py` (haversine, kebijakan wajib, simpan selfie).
- Router baru `backend/routes/rahaza_attendance_permits.py` (ajukan/setujui/tolak/batalkan izin + export XLSX rekap).
- Modul FE baru `HRAttendanceSessionsModule.jsx` (menu SDM "Istirahat & Izin").
- 8 bug nyata ditutup (selfie tak pernah disimpan, geofence `not_verified` dianggap lolos,
  haversine tersalin 6x, izin memotong jam tanpa persetujuan, seeder akun role menulis ke DB salah,
  kolom lat/lng UI beku, izin pending tampil "sedang keluar", jalur biometrik melewati geofence).
- Bukti: `verify_fase16_absen.py` 48/0 · `verify_fase15.py` 27/0 · testing_agent_v3 iter_176 (backend 51/51).

**FASE 17 — BUG-4 cuti**
- SSOT baru `backend/utils/leave_types.py` + migrasi `backfill_leave_types.py`.
- 7 bug nyata ditutup (field form dibuang, `paid` vs `unpaid` terbelah, PUT body mentah,
  identitas dari JWT basi, filter karyawan aktif salah, 500 saat input teks, UI tanpa Ubah/Nonaktifkan).
- Bukti: `verify_fase17_cuti.py` 35/0.

**FASE 18 — BUG-3 slip gaji PDF**
- Karyawan kini bisa mengunduh slip gajinya sendiri (Portal Saya → Slip Gaji → PDF);
  slip orang lain tetap 403. Penanda "DRAFT - BELUM FINAL" untuk run yang belum final.
- Isi PDF diverifikasi dengan ekstraksi teks: watermark + tanda tangan + breakdown lengkap.
- Bukti: `verify_fase18_payslip.py` 25/0.

# CHANGELOG — CV. Dewi Aditya ERP

## 2026-07-26 — FASE 13: HIGIENE DATA ALAT UJI (kebocoran stok, jurnal GL yatim, baseline residu)

> Konteks: environment di-clone dari `https://github.com/jjaakalamanaba/da` → `rsync` ke `/app`
> (exclude `.env`) → `bootstrap.sh` (49 detik, 6 login HTTP 200). **MongoDB container ini kosong
> total**, jadi semua angka dihasilkan ulang dari seeder — bukan dibaca dari dokumen.
> Pemicu: **audit DB mandiri user** menemukan `rahaza_costing_settings` tercemar `12345`/`77`
> yang harus dipulihkan MANUAL, padahal `cleanup_fase10_qa.py --dry-run` bilang "tidak ada drift".
> Rencana & bukti lengkap: **`docs/PLAN_FASE13.md`**.

### 0. VERIFIKASI KLAIM SESI SEBELUMNYA — 3 BENAR, 3 KELIRU
| Klaim | Kenyataan |
|---|---|
| `run_all_verifications.sh` 443 PASS / 0 FAIL | **TERBUKTI** |
| `gate.sh` 9/9 HIJAU · ESLint rc=0 | **TERBUKTI** |
| Baseline valuasi **Rp 9.667.750 / qty 32.220** | **KELIRU** → seharusnya **Rp 9.663.750 / 32.200** |
| `cleanup_fase10_qa.py --dry-run` = "data bersih" | **BUTA** terhadap `rahaza_costing_settings` |
| Regresi "SEMUA HIJAU" ⇒ tidak ada residu | **KELIRU** → total stok naik **+2 setiap run** |

### 1. TEMUAN 1 — `verify_phase_g_acc_opname.py` membocorkan stok + JURNAL GL YATIM
* **Akar 1:** skenario approve mengambil `lines[0]`/`lines[1]` dari snapshot opname — di DB
  ber-seed itu selalu **material demo nyata** `ACC-BTN-12` & `ACC-LBL-01`. Approve opname
  mengubah stok PERMANEN + memposting jurnal GL ⇒ `+5` / `-3` pcs per run.
* **Akar 2:** `_cleanup()` mencari mutasi dengan `{"related_ref": ...}` — field yang **TIDAK
  PERNAH TERSIMPAN**. `related_ref` cuma NAMA PARAMETER `_log_movement()` di
  `routes/dewi_accessories_opname.py:63`; yang disimpan `reference_id` (b.88) + `ref_id` (b.89).
  Dibuktikan di DB: `related_ref` cocok **0** dok, `reference_id` cocok **2** dok.
  Karena `gl_je_id` dikumpulkan lewat predikat salah itu, `rahaza_journal_lines` &
  `rahaza_journal_entries` **tidak ikut terhapus** ⇒ buku besar menumpuk **jurnal yatim**.
  Query ledger `{"ref.session_id": ...}` juga cocok 0 (dokumen nyata hanya `ref: {source}`).
* **Akar 3:** cleanup hanya di jalur sukses ⇒ exception/`timeout 900`/Ctrl-C ⇒ artefak tinggal.
* **Fix:** skrip memakai aksesoris uji **miliknya sendiri** (`QA-OPN-A/B`, stok lewat
  `POST /api/acc/stock/receive` karena `POST /api/acc/items` MENGABAIKAN `stock_qty`);
  assert baru *"item uji QA TIDAK menyentuh material demo ACC-*"*; `_cleanup()` pakai nama field
  benar; `run()` dibungkus `try/finally`; jaring pengaman `_restore_non_qa_stock()` memulihkan
  stok non-QA + membuang baris ledger yang lahir selama run.
* **Hasil:** 45 → **49 PASS / 0 FAIL**, artefak dibersihkan **13 → 35** dokumen.

### 2. TEMUAN 2 — pencemaran `rahaza_costing_settings` GLOBAL (yang user pulihkan manual)
`verify_fase11/12/66.py` meng-PUT nilai uji ke dokumen GLOBAL lalu memulihkan **hanya di jalur
sukses** — dan **tidak satu pun punya `try/finally`** (0 kemunculan). Nilai yang bisa tertinggal:
`12345`/`77` (fase12), `88000` (fase66), `4321` (fase11). Run berikutnya menangkap nilai cemar
itu sebagai `settings_before` lalu "memulihkannya" ⇒ **cemar jadi LENGKET**. Pola
`if settings_before:` juga melewatkan pemulihan bila dokumen semula belum ada (DB segar).
**Dampaknya bukan kosmetik:** dua field itu *fallback harga* penghitung HPP
(`compute_hpp_job` / `_compute_hpp` via `material_fields.read_field`) ⇒ **HPP salah diam-diam**,
kelas bug yang sama dengan BUG-B/B2 yang baru ditutup FASE 12.
* **Fix:** SSOT baru `scripts/lib/qa_state_guard.py` → `preserve_costing_settings(db)`
  (async context manager, pemulihan di `finally`; bila dokumen semula `None` maka **DIHAPUS**,
  bukan dibiarkan berisi nilai uji). Dipasang ke 3 skrip lewat perubahan **satu baris**
  (`async with httpx.AsyncClient(...) as c, preserve_costing_settings(db):`) sehingga seluruh
  blok terlindungi tanpa re-indentasi berisiko.

### 3. TEMUAN 3 — baseline "Rp 9.667.750" adalah RESIDU QA; `--apply` MENGARANG stok
Environment segar: `ACC-BTN-12 = 5.000`. Baseline dokumen: 5.020. Seluruh penulis stok dilacak,
tidak ada yang pernah menulis >5.000 (`link_demo_bom_materials.py` → 5000; angka `6` di
`rahaza_setup.py:260` itu qty **baris BOM**; `maklon_seed.py` tidak menyentuhnya).
Selisih 20 pcs = **4 run kebocoran × 5 pcs** (Temuan 1) — `plan.md:115` sendiri mencatat
"5.000 + 20 pcs". Residu itu dipatok jadi "angka sah" sehingga:
`--dry-run` **selalu** merah di environment segar · `--apply` **menyuntikkan 20 pcs persediaan
fiktif** (bagian EKSEKUSI menghapus baris stok lalu insert dari baseline) ·
`tests/backend_test_fase12.py` hard-assert `9667750 (±100)`/`32220 (±10)` ⇒ **FAIL PASTI**.
* **Bonus temuan:** berkas uji yang sama mematok `BASE_URL` ke preview container lama
  (`https://da37-cmt-bridge.preview.emergentagent.com`) yang **sudah mati** ⇒ menguji host salah.
* **Fix:** SSOT tunggal `scripts/lib/acc_baseline.py` — semua total **DITURUNKAN** dari tabel
  `STOCK_BASELINE × COST_BASELINE` + `assert` pengaman (qty **32.200**, nilai **Rp 9.663.750**,
  8 bernilai / 2 belum, unvalued_qty 3.300). `cleanup_fase10_qa.py` &
  `tests/backend_test_fase12.py` mengimpornya. `BASE_URL` dibaca dari `frontend/.env`.
  **Bagian 5 baru** di `cleanup_fase10_qa.py`: deteksi + pemulihan drift costing settings ⇒
  audit manual user kini **OTOMATIS**.

### 4. SENTINEL `scripts/verify_fase13.py` (33 assert, terdaftar terakhir di runner)
Bagian A SSOT vs `/api/acc/valuation` · B guard diuji **saat exception** + cek statis 3 skrip ·
C **sentinel drift**: jalankan `verify_phase_g_acc_opname.py` lalu buktikan **NOL DRIFT** pada
9 metrik · D artefak/dokumen yatim + cek nama field lewat **AST** (docstring dibuang, jadi bukan
sekadar cocok-kata) · E titik buta cleanup tertutup.
**Sentinelnya sendiri diuji:** bug lama ditanam ulang → sentinel **MERAH** di C1+C2+C3
(`{'stock_ledger': (0, 2)}`); dikembalikan → **33 PASS / 0 FAIL**.

### 5. BUKTI AKHIR
| Uji | Hasil |
|---|---|
| `scripts/run_all_verifications.sh` (11 skrip) | **480 PASS / 0 FAIL — SEMUA HIJAU** (dulu 443) |
| `scripts/verify_fase13.py` | **33 PASS / 0 FAIL** |
| `scripts/verify_phase_g_acc_opname.py` | **49 PASS / 0 FAIL** · cleanup 13 → 35 artefak |
| `scripts/gate.sh` | **SEMUA GATE HIJAU** (`memory/GATE_RECEIPT.md`) |
| **Drift sesudah regresi penuh + gate.sh** | **NOL pada 9 metrik** (sebelumnya +2 qty tiap run) |
| `cleanup_fase10_qa.py --dry-run` | 0 mutasi QA · "(tidak ada drift)" di bagian **4 DAN 5** |
| `/api/acc/valuation` | qty **32.200** · **Rp 9.663.750** · 8 bernilai / 2 belum |
| ESLint root + `/app/mobile` | rc=0 / rc=0 (0 error) |

### ⚠️ PELAJARAN BARU
1. **Alat uji adalah sumber tech-debt data yang paling sering terlewat.** Tiga sesi mengejar
   "data kotor" padahal penyebabnya skrip verify-nya sendiri. Perbaiki PENULISNYA.
2. **Angka baseline yang tidak reproducible dari seeder adalah RESIDU.** Kalau `--dry-run`
   selalu merah di environment segar, curigai baselinenya — bukan datanya.
3. **Alat "cleanup" yang menulis angka bisa MENGARANG data.** Restore-by-insert dengan baseline
   salah = menyuntikkan persediaan fiktif beserta nilai rupiahnya.
4. **Nama field Mongo wajib diverifikasi terhadap PENULISNYA.** `related_ref` terlihat benar
   (ada di signature backend) tapi tersimpan sebagai `reference_id`. Query yang cocok 0 dokumen
   gagal DIAM-DIAM — cek `count_documents()` dulu sebelum percaya sebuah cleanup.
5. **Pemulihan state global adalah tugas `finally`, bukan "kalau semua lancar".**
6. **Guard yang belum pernah terlihat MERAH bukan guard.** Tanam ulang bug-nya untuk membuktikan.

## 2026-07-26 — FASE 12: REKONSILIASI PETA LOKASI STOK + BUG-A / BUG-B / BUG-B2 / BUG-C

> Konteks: environment dipulihkan dari clone `https://github.com/jajanamakamana/da` → `rsync` ke
> `/app` (exclude `.env`) → `bootstrap.sh` (39 detik, 6 login HTTP 200).
> Pilihan user: **(A)** perbaiki BUG-A + BUG-B & jadikan seed baseline valuasi bagian `bootstrap.sh`,
> lalu **(C)** rekonsiliasi lokasi stok aksesoris. Rencana & bukti: **`docs/PLAN_FASE12.md`**.

### 0. VERIFIKASI KLAIM SESI SEBELUMNYA — 4 dari 5 KELIRU
| Klaim | Kenyataan |
|---|---|
| `run_all_verifications.sh` 410 PASS / 0 FAIL | **401 PASS / 9 FAIL** |
| bootstrap menyiapkan semua data uji | baseline valuasi aksesoris tak pernah di-seed ⇒ **8 FAIL palsu** |
| alias `yarn_*` berhenti ditulis (FASE 11) | **bocor** lewat `routes/maklon_seed.py` |
| `scripts/migrate_stock_locations_to_wh.py` (alat backlog #3) | **tidak pernah ada di repo** |
| ESLint hidup | **mati** dari `/app/mobile` (exit 2 = linter engine error) |

### 1. BUG-A — seeder menulis alias legacy `default_yarn_cost_per_kg`
`routes/maklon_seed.py` menulis kunci legacy secara harfiah ⇒ **setiap DB baru** langsung melanggar
kontrak FASE 11. Fix: `material_fields.mirror('default_material_cost_per_kg', 0)`.
DB dibersihkan (`migrate_rename_yarn_fields.py --execute` → `--drop-legacy --yes`, `--discover` bersih).
Sweep menyeluruh backend+frontend+scripts: tidak ada penulis/pembaca alias langsung yang tersisa.

### 2. BUG-B — HPP job internal memakai harga bahan 0 secara DIAM-DIAM
`production_internal_adapter.compute_hpp_job` membaca `settings.get('default_yarn_cost_per_kg')`
langsung. Sejak alias berhenti ditulis, nilainya selalu `None` ⇒ fallback = 0, **tanpa error**.
Fix: `material_fields.read_field(settings, 'default_material_cost_per_kg', 0)`.

### 3. BUG-B2 (BARU) — fallback salah kategori pada dua penghitung HPP
`rahaza_hpp.py` memakai `type == "yarn"` dan adapter internal `type in ("yarn","fabric")`, padahal
taksonomi kg-like resmi juga mencakup `kain`, `benang`, `interlining`. Material tsb tanpa `unit_cost`
mendapat fallback harga **aksesoris (per unit)**. Fix: SSOT baru
`core/material_fields.is_kglike_material(doc)` dipakai keduanya.

### 4. BUG-C — linter engine mati dari `/app/mobile`
Fallback `mobile/eslint.config.js` = `[{ ignores: ['**/*'] }]` ⇒ `npx eslint .` exit **2**
("all files are ignored") yang dibaca tool platform sebagai *linter engine error*. Fallback kini
tetap melint berkas JS biasa (tanpa aturan) dan hanya mengabaikan TS/TSX. mobile rc=0, root rc=0.

### 5. FASE 12 — penyakit ke-8 `unmapped_location` (backlog #3 TUNTAS)
- **`core/location_resolver.storage_location_index()`** — SSOT klasifikasi lokasi:
  `storage` (zona penyimpanan resmi + bin-nya) · `exempt` (lantai produksi & karantina QC —
  **tidak pernah dipindah otomatis**) · `unmapped` (bukan zona penyimpanan / id sudah dihapus).
  Plus `classify_location()` & `describe_location()`.
- **`core/stock_reconcile`** — baris di lokasi `unmapped` dipindah ke zona kanonik sesuai kategori
  material, lalu langkah "gabung kembar" yang sudah ada menyatukan bila baris tujuan sudah eksis
  (urutan hapus-dulu-baru-tulis tetap dipakai → aman dari `DuplicateKeyError` unique index).
  **PENGAMAN**: baris **qty negatif** & **material yatim** TIDAK ikut dipindah (kalau ikut,
  selisih negatif diam-diam menggerus stok zona tujuan) dan tidak dihitung `fixable`.
- **UI `StockSchemaHealthModule.jsx`** — kartu "Peta lokasi stok" (status per lokasi + chip zona
  tujuan per kategori), kolom "Usulan zona", ringkasan "Baris dipindah zona" + daftar `DARI → KE`,
  kolom "Dipindah" di riwayat.
- **Eksekusi data nyata**: 5 baris dipindah (`GDG-UTAMA-DEMO` → `ZNA-KAIN` 450/300 ·
  → `ZNA-AKSESORIS` 1.800/5.000/3.997), 1 baris kembar digabung, **total on-hand 33.020 → 33.020**.

### 6. AKAR MASALAH DITUTUP (supaya tidak berulang tiap re-seed)
| Penulis | Dulu | Sekarang |
|---|---|---|
| `routes/maklon_seed.py` | stok demo & pemotongan MI ke `int-demo-loc-1` | `_storage_zone_for()` → zona kanonik |
| `backend/scripts/link_demo_bom_materials.py` | `DEMO_LOC` hardcode | `zone_for(mtype)` via SSOT |
| `scripts/cleanup_fase10_qa.py` | `STOCK_BASELINE` mematok lokasi pseudo | `__ACC__` (zona aksesoris kanonik) |

### 7. HIGIENE ALAT UJI
- `bootstrap.sh` menjalankan `scripts/seed_acc_valuation_baseline.py` (idempoten) ⇒ tidak ada lagi
  8 FAIL palsu di environment segar.
- `run_all_verifications.sh`: peta `POST_CLEANUP` → `cleanup_test_f6.py --apply` otomatis setelah
  `verify_phase6_quarantine.py` (penyebab run ke-2 selalu merah), dan `verify_fase12.py` masuk daftar.
- 2 tes usang diperbaiki (`tests/test_material_requirements.py`, `test_mrp_fase5.py` — masih
  mengharapkan alias `total_yarn_kg`).
- `verify_fase66.py` A4/A5 diperbarui + 2 asersi BARU sebagai pagar penyakit ke-8.

### 8. BUKTI
`verify_fase12.py` **31 PASS/0 FAIL** · `run_all_verifications.sh` **443 PASS/0 FAIL (SEMUA HIJAU)` ·
`gate.sh` **9/9 HIJAU** · `sweep_query_robustness.py` **7.184 request → 0 error 500** ·
ESLint root & mobile rc=0 · valuasi aksesoris **PERSIS Rp 9.667.750** (8 bernilai / 2 belum dinilai) ·
`cleanup_fase10_qa.py --dry-run` = "(tidak ada drift)" · audit DB mandiri: 0 artefak uji tersisa.

---

## 2026-07-25 (lanjutan #4) — FASE 11: BUG-R11-A DITUTUP TUNTAS + 2 BUG BARU (BUG-4 & BUG-5) + ALIAS `yarn_*` DIHENTIKAN

> Konteks: environment fresh (template kosong) → clone `https://github.com/yogadevelopment02-bit/da`
> → `rsync` ke `/app` (exclude `.env`) → `yarn install` + `yarn build` + seed lengkap.
> Pilihan user untuk sesi ini: **perbaiki SEMUA** bug robustness; **hapus** alias legacy `yarn_*`;
> **lewati** verifikasi email nyata; **lewati** drop `accessory_legacy` di DB produksi.
> Rencana & bukti lengkap: **`docs/PLAN_FASE11.md`**.

### 0. VERIFIKASI KLAIM SESI SEBELUMNYA — dilakukan LEBIH DULU
- Klaim FASE 10 (**402 PASS / 0 FAIL**, login 6 akun 200) diuji ulang dari nol → **TERBUKTI BENAR**.
- **Dokumen ternyata USANG:** `BUG-R11-B`, `BUG-R11-SM-1`, `BUG-R11-SM-2`, dan `P3 ap-invoices` masih
  ditandai 🔴/🟡 OPEN di `memory/BUG_REGISTRY.md`, padahal probe langsung
  (`scripts/probe_open_bugs.py`) menunjukkan **keempatnya sudah sehat**. Registry diperbarui.

### 1. BUG-R11-A — DITUTUP TUNTAS (sebelumnya cuma "kelihatan" beres)
- **Kenapa lolos selama ini:** sesi lalu menguji dengan **8 sampel**; 7 di antaranya kebetulan yang
  sudah sembuh. Sisanya tidak pernah tersentuh.
- **Alat baru `scripts/sweep_query_robustness.py`** — menyapu **SELURUH** GET endpoint dari
  `/api/openapi.json` (898) × **8 varian query rusak** = **7.184 request**, read-only.
- **Hasil: 66 → 0 error 500** · endpoint bermasalah **51 → 0**.
- **Perbaikan:** helper baru **`backend/utils/query_guards.py`** (`q_int`, `q_float`, `q_bool`,
  `q_date`, `q_year_month`, `q_period`, `to_date`, `date_key`) + **46 endpoint di 36 file router**
  diberi batas `Query(ge=…, le=…)` / guard tanggal-bulan. `marketing_livehost_analytics.py`
  mendapat helper `_month_bounds()` menggantikan **5 salinan** `month.split('-')` yang tak terjaga.
- **Kejujuran:** 5 dari 51 "endpoint bermasalah" versi pertama adalah **false positive** — endpoint
  LLM (`/api/finance/ai-cashflow` ≈ 20 dtk) menahan slot koneksi saat sweep paralel sehingga
  tetangganya time-out. Diprobe serial: semuanya 200/404 dalam < 10 ms. Endpoint LLM kini di-skip
  dari sweep paralel **dan** diuji SERIAL di `verify_fase11.py` (validasi menolak dalam 0,05 dtk,
  jadi model tidak pernah dipanggil percuma).

### 2. BUG-4 (BARU, belum pernah tercatat) — `datetime` adalah SUBCLASS `date`
- **Gejala:** `GET /api/dewi/cmt/lifecycle` **HTTP 500 pada request POLOS**, tanpa parameter apa pun.
- **Akar:** `if isinstance(v, date)` juga bernilai True untuk `datetime`, sehingga objek BSON datetime
  lolos apa adanya → `datetime <= date` → `TypeError`. Lapisan kedua dari keluarga yang sama:
  `(...)[:10]` terhadap objek datetime → `'datetime.datetime' object is not subscriptable`.
- **Perbaikan:** cek `datetime` **sebelum** `date`; helper `_date_key()` untuk kunci perbandingan
  seragam; diterapkan di **3 file** berjebakan identik — `dewi_cmt_lifecycle.py`, `rahaza_ar_360.py`,
  `production_control_tower.py`.
- **Catatan jujur:** 2 file terakhir **belum meledak di preview** hanya karena datanya masih kosong;
  di DB produksi yang datanya nyata jebakannya aktif. Modul UI `cmt-lifecycle` sendiri saat ini
  di-redirect ke `vendor-admin`, jadi belum terpakai langsung dari layar.

### 3. BUG-5 (BARU) — kode akun modul Aset tidak ada di CoA
- **Gejala:** gate `verify_data_integrity` **INV-GL-3 MERAH**.
- **Akar:** modul Aset menulis kode akun **hardcode 4-digit** (`1500`, `1100`, `1590`, `8100`, `6300`)
  padahal CoA proyek berformat bersegmen (`1-2500`, `1-110`, …). **Tidak satu pun ada** di 264 akun
  CoA. Modul Aset juga satu-satunya yang **melewati** `rahaza_posting_profiles`, padahal profil
  `asset_acquisition` & `asset_disposal` sudah ada dan valid.
- **Dampak:** setiap pembelian/disposal aset menghasilkan jurnal ke **akun hantu** — tidak muncul di
  Buku Besar/Neraca Saldo per akun.
- **Perbaikan:** modul baru `backend/routes/asset/_accounts.py` → `resolve_asset_accounts(db)`
  mengambil kode dari posting profile (SSOT), memvalidasinya ke CoA, dan mengambil nama akun dari CoA.
  Dipakai di `assets_core.py` + `disposal.py` (2 jalur).

### 4. FASE 11.C — alias legacy `yarn_*` BERHENTI DITULIS (permintaan user)
- Prasyarat `GUIDELINE_DROP_LEGACY_COLLECTIONS.md` §5 diperiksa satu per satu dan **terpenuhi**
  (penulisan alias terpusat; semua pembacaan lewat helper; migrasi melaporkan 0 dokumen perlu backfill).
- `WRITE_ALIASES = {}` → `mirror()` hanya menulis nama kanonik; `with_aliases()` kini **membuang**
  kunci legacy dari response.
- **`LEGACY_READ_ALIASES` DIPERTAHANKAN** → `read_field()` masih bisa membaca dokumen lama
  (restore backup / DB produksi belum dimigrasi). Endpoint juga **tetap menerima** nama legacy dari
  klien lama.
- Mode baru `migrate_rename_yarn_fields.py --drop-legacy [--yes]` dengan **palang pengaman**
  (menolak jalan bila ada dokumen yang HANYA punya kunci legacy). Dijalankan di preview → 6 kunci
  dihapus, `--discover` bersih.
- Sisi FE: `lib/materialFields.js` (`WRITE_ALIASES = {}`) + `RahazaHPPModule.jsx` berhenti mengirim
  `default_yarn_cost_per_kg`.
- **Cara membalik** bila integrasi eksternal ternyata masih butuh: isi ulang `WRITE_ALIASES` di
  `core/material_fields.py` — **tanpa menyentuh satu pun file route**.

### 5. PERBAIKAN ALAT UJI — supaya gate JUJUR (bukan supaya hijau)
| Masalah | Perbaikan |
|---|---|
| `verify_acc123.py` membuat aset uji yang memicu jurnal, tapi jurnalnya tak pernah dihapus → 3 JE yatim membuat INV-GL-3 merah di sesi berikutnya | cleanup ikut menghapus `rahaza_journal_entries` + `_lines` bertanda `TEST-ACC` |
| `round6_verify.py` menghapus AR/AP invoice tapi **bukan jurnalnya** → 2 JE yatim setiap kali gate dijalankan | cleanup ikut menghapus jurnal turunan + penjaga baru `_count_orphan_ar_ap_je()` |
| `verify_concurrency.py` CC5 menguji endpoint reservasi material per-WO yang **sudah dipensiunkan FASE 4 (E10)** → FAIL sejak ≥ 2026-07-16 | 404/405 kini **SKIP dengan alasan eksplisit** (SKIP ≠ PASS) |
| `verify_cross_entity.py` melaporkan HIGH "orphan FK" untuk AR maklon — padahal `mk-client-demo-1` ADA di `dewi_maklon_clients` | relasi boleh punya beberapa koleksi induk sah → 0 temuan |
| `verify_fase66.py` §B masih menguji kontrak LAMA (alias wajib ditulis) | ditulis ulang ke kontrak FASE 11 + assertion baru "DB tidak menyimpan `yarn_*`" (48 → **56 PASS**) |
| `run_all_verifications.sh` skrip terakhir kena HTTP 429 | jeda antar skrip 12 → 25 detik |
| `mobile/eslint.config.js` mati bila dependensi Expo belum dipasang → "linter engine error" mematikan SELURUH gate lint | config menurun dengan anggun (try/catch) |

### 6. ⚠️ TESTING AGENT SALAH KLAIM LAGI (kejadian ke-3 berturut-turut)
`testing_agent_v3` iteration_174 melaporkan `"test_data_created": []` dan mengklaim data bersih,
padahal meninggalkan **3 aset `QA-FASE11` + 4 jurnal `asset_management`**. Akar masalahnya ketahuan
setelah saya baca skripnya: `cleanup_test_data()` memanggil `DELETE /api/assets/{id}` dan
`DELETE /api/rahaza/journal-entries/{id}` — **kedua endpoint itu TIDAK ADA**, jadi pembersihan gagal
diam-diam sementara laporan tetap mengklaim bersih. Semua artefak sudah saya hapus manual dan
skripnya (`backend_test_fase11.py`) saya perbaiki: bersih-bersih lewat Mongo + **verifikasi hitung ulang**.

Dua temuan lain dari agent yang setelah diperiksa **BUKAN bug produk**:
- "Production Control Tower: OVERDUE0, 0, Andon Alerts" → itu hasil scrape teks tanpa spasi; screenshot
  membuktikan kartu KPI ter-render benar, 0 console error.
- 10 uji query-param dilaporkan "Request failed or timed out" → jebakan pustaka `requests`:
  `Response.__bool__` == `Response.ok`, sehingga `if r:` bernilai **False tepat untuk respons 400/422**
  yang justru ingin diuji. Diperbaiki jadi `if r is not None:` → skripnya kini **45/45 PASS**.

### 7. BUKTI AKHIR
- `sweep_query_robustness.py` — **7.184 request · 0 error 500 · 0 error jaringan**
- `scripts/verify_fase11.py` (baru) — **108 PASS / 0 FAIL**
- 9 skrip regresi — **410 PASS / 0 FAIL** (naik dari 402 karena assertion bertambah)
- `backend_test_fase11.py` (dari testing agent, diperbaiki) — **45/45 PASS**
- `scripts/gate.sh` — **9/9 HIJAU** (sebelumnya 2 MERAH) → `memory/GATE_RECEIPT.md`
- `ruff --select F821,F811,F823` — All checks passed · `npx eslint .` — 587 file, **0 error**
- **Audit DB mandiri:** 0 aset uji, 0 jurnal QA, 0 jurnal yatim AR/AP; baseline aksesoris utuh
  (10 item · **Rp 9.667.750** · 8 bernilai / 2 belum · ACC-BTN-12 stok 5.020 HPP **200** — tidak bergeser).

### 8. YANG SENGAJA TIDAK DIKERJAKAN (pilihan user)
- Bukti email sungguhan (SMTP tetap kosong → `skipped_no_smtp` + notifikasi in-app).
- Drop koleksi `accessory_legacy` di DB produksi (di preview no-op).

## 2026-07-25 (lanjutan #3) — FASE 10 DIVERIFIKASI + 3 BUG NYATA DITEMUKAN & DIPERBAIKI

> Konteks: environment fresh (template kosong) → clone `https://github.com/naababnamana/da` → `rsync` ke
> `/app` (exclude `.env`) → `bash scripts/bootstrap.sh` → `yarn add @simplewebauthn/browser@13.3.0` →
> `yarn build`. **Kode FASE 10 SUDAH ada di repo, tapi dokumen (`plan.md`, CHANGELOG, HANDOFF) belum
> di-update** karena sesi sebelumnya berhenti tepat saat hendak memanggil `testing_agent_v3`.
> Tugas sesi ini: verifikasi menyeluruh, tuntaskan pengujian end-to-end, perbaiki temuan, rapikan dokumen.

### 0. RESTORE — 2 catatan penting
- **Repo yang benar `naababnamana/da`.** Snapshot repo lain (`gantengkaamananba/da`) berhenti SEBELUM
  FASE 10 — sempat dipakai lalu di-`rsync --delete` ulang setelah repo yang benar dibuka publik.
- **Kendala known-issue #1 terulang lagi** (ini ketiga kalinya): `bootstrap.sh` memakai
  `yarn install --frozen-lockfile` ⇒ `@simplewebauthn/browser` TIDAK terpasang ⇒ `yarn build` gagal.
  Obatnya tetap `cd /app/frontend && yarn add @simplewebauthn/browser@13.3.0`.
- **`plan.md` master (69 KB) SEMPAT TERTIMPA** oleh keluaran tool `plan` sesi sebelumnya (tinggal 9,5 KB).
  Sesi ini **memulihkannya** dari snapshot repo lama dan memindahkan rencana FASE 10 ke
  `docs/PLAN_FASE10_NEXT_ACTIONS.md` supaya keduanya selamat. **Pelajaran: jangan biarkan tool `plan`
  menimpa `plan.md` — SSOT rencana proyek ada di situ.**

### 1. BUG-1 (KRITIS) — pengeluaran aksesoris **HTTP 500** bila stok tersebar di >1 lokasi
- **Gejala:** `POST /api/acc/stock/issue` untuk `ACC-BTN-12` qty 100 → **500 Internal server error**.
  Jalur SSOT baru `POST /api/dewi/accessory-requests/{id}/deliver` — inti FASE 10-C — kena hal yang sama.
- **Akar masalah:** pembaca stok aksesoris **mengagregasi SEMUA lokasi**
  (`stock_service.onhand_map`), tetapi penulis **selalu memotong di SATU lokasi kanonik** (ZN-AKS).
  Item demo `ACC-BTN-12` menyimpan 5.000 pcs di `int-demo-loc-1` dan hanya 20 pcs di ZN-AKS ⇒ validasi
  "stok cukup" LOLOS (total 5.020) lalu `stock_service.issue` melempar `InsufficientStock` ⇒ 500.
  Asimetri ini sudah tertulis di docstring `accessory_stock.py` sejak FASE C tapi tidak pernah ditutup.
- **Kenapa lolos dari semua uji sebelumnya:** setiap skrip verifikasi membuat item BARU, yang stoknya
  otomatis mendarat di ZN-AKS. Hanya data warisan/put-away/seed demo yang memicunya — persis data yang
  dilihat user di layar.
- **FIX** `backend/core/accessory_stock.py`: fungsi baru **`issue_across_locations()`** — potong di lokasi
  preferensi (kanonik) DULU lalu baris berstok terbesar; baris warisan Skema-B (lokasi bersarang, tanpa
  `location_id` di level atas) dipotong lewat `stock_service.issue_row` by row-id. `add_stock(delta<0)`
  kini memanggilnya ⇒ **semua caller ikut sembuh sekaligus**: `/acc/stock/issue`, `/acc/stock/scrap`,
  SSOT `deliver`, dan `approve` opname. Kurang stok BENERAN tetap `InsufficientStock` → 400 yang ramah.
- **Bukti:** `scripts/repro_acc_multiloc_issue.py` (self-restoring) — sebelum fix HTTP 500, sesudah fix
  HTTP 201 & stok 5.020 → 4.920 + jurnal ter-posting. Diverifikasi juga lewat UI: Request Internal
  `INT-REQ-260725-008` qty 40 → stok `ACC-BTN-12` 5.030 → 4.990.

### 2. BUG-2 — `approve` opname DIAM-DIAM melewati baris yang gagal disesuaikan
- Baris yang `_add_stock`-nya gagal hanya di-`continue`: tidak masuk `adjustments_made`, tidak masuk
  `je_failed_items`, tidak muncul di UI ⇒ user melihat sesi **"Completed"** padahal sebagian selisih
  **tidak pernah diterapkan**. Bertolak belakang dengan semangat transparansi FASE G+.
- **FIX:** `summary`, response `approve`, dan serializer `_wh_session_to_acc` kini membawa
  **`stock_failed` + `stock_failed_items`** (kode, nama, delta, alasan). FE `StokOpnameTab` menampilkan
  baris merah "⛔ N item GAGAL disesuaikan — selisihnya tidak diterapkan" + detail di `title`, dan
  kotak peringatan setelah approve (stok-gagal ditaruh DI ATAS peringatan jurnal karena lebih parah).
- **Bukti:** `verify_phase_g_acc_opname.py` **42 → 45 PASS / 0 FAIL** (3 kegagalan itu memang gejala BUG-1).

### 3. BUG-3 — banner hasil aksi di panel otomasi valuasi HILANG seketika
- Klik **"Kirim rapor sekarang"** tanpa SMTP tidak memberi umpan balik apa pun (layar diam) — padahal
  backend sudah membalas `skipped_no_smtp` + pesan penjelas. **DUA penyebab bertumpuk:**
  1. `load()` di `AccessoryValuationAutomation.jsx` diawali `setErr('')` sehingga MENGHAPUS pesan yang
     baru saja di-set oleh aksi (aksi memang memanggil `load()` untuk menyegarkan data).
  2. Parent `AccessoryValuationTab.jsx` menampilkan **skeleton pada SETIAP refresh** ⇒ panel anak
     ter-**unmount** ⇒ seluruh state pesannya hilang.
- **FIX:** `load(keepFeedback)` + skeleton **hanya pada muat pertama** di KEDUA komponen.
  Sekarang banner `acc-val-auto-error` tampil & bertahan: *"SMTP belum dikonfigurasi. Rapor sudah dibuat
  & ringkasannya dikirim sebagai notifikasi dalam aplikasi; isi Pengaturan Notifikasi → Email (SMTP)…"*.

### 4. Kebersihan data & higiene uji (utang lama yang ditutup)
- **BARU** `scripts/cleanup_fase10_qa.py` (`--dry-run`/`--apply`) — mengembalikan domain aksesoris ke
  baseline demo: hapus artefak QA (permintaan, sesi opname, mutasi, ledger, jurnal, notifikasi, riwayat
  rapor, log scheduler, config provider uji) **dan memulihkan stok + HPP demo yang bergeser**.
  Sesi ini membersihkan **166 dokumen** + memulihkan 3 item.
- `verify_phase_g_acc_opname.py` dulu hanya MENCETAK "sesi QA untuk cleanup manual" ⇒ DB preview
  menumpuk **20 sesi OPNAME-000x**. Sekarang skripnya **membersihkan dirinya sendiri**.
- `verify_fase8plus.py` punya asersi kebersihan yang terlalu luas (`subtype='stock'` 1 jam terakhir)
  sehingga alarm SAH dari baseline demo dihitung sebagai kebocoran ⇒ FALSE POSITIVE. Kini di-scope ke
  material milik skrip itu sendiri.
- ⚠️ **`testing_agent_v3` iteration_173 kembali mengklaim data sudah dipulihkan, dan lagi-lagi tidak**:
  7 permintaan QA tertinggal, dan `ACC-BTN-12` "dipulihkan" dengan cara **MENERIMA 150 pcs** yang justru
  menggeser HPP rata-rata 200 → 218,31. **SELALU audit DB sendiri sesudah memanggil testing agent.**

### 5. BUKTI (semua dijalankan ulang SETELAH perbaikan)
`verify_fase10_digest_report` **59/59** · `verify_fase10_accessory_legacy` **44/44** ·
`verify_acc123` **62/62** · `verify_fase8` **48/48** · `verify_fase8plus` **24/24** ·
`verify_phase_g_acc_opname` **45/45** · `verify_fase9_legacy_drop` **24/24** · `verify_fase66` **48/48** ·
`verify_phase6_quarantine` **48/48** → **total 402 PASS / 0 FAIL**.
`testing_agent_v3` iteration_173: **0 critical bug, 0 minor issue**, ketiga bug di atas diverifikasi ulang
secara independen. Verifikasi UI manual (Playwright) oleh main agent: modal Ajukan/Tolak opname (validasi
inline + banner + status Rejected, **0 dialog native**), panel otomasi (kirim digest, simpan email
tambahan → chip penerima, kirim rapor → banner SMTP), Request Internal SSOT (Pending → Approved → Issued
+ stok berkurang), modal hapus aksesoris (Batal), Pusat Notifikasi (3 opsi `smtp_security`).
FE lint 0 error · `yarn build` Compiled successfully.

### 6. Status akhir grup `accessory_legacy`
`drop_legacy_collections_guided.py --audit` kini melaporkan grup **[SIAP]** (sebelumnya BELUM).
Checklist §3 `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` sudah dicentang seluruhnya + bukti.
Di DB preview kedua koleksi tidak ada ⇒ `--execute` no-op; manfaat nyatanya di DB produksi user.

## 2026-07-25 (lanjutan #2) — FASE 9 (alat drop legacy TERUJI) + 3 penyempurnaan FASE 8

> Permintaan user: (1) jalankan FASE 9 untuk grup `opname_v1` lengkap dengan arsip & verifikasi ulang,
> (2) ganti `prompt()` di tab peminjaman aksesoris deprecated dengan modal proper,
> (3) rapor valuasi aksesoris bisa diekspor ke Excel/PDF untuk lampiran laporan keuangan,
> (4) alarm ke Admin Gudang setiap ada item aksesoris bergerak tapi HPP masih 0.

### 1. FASE 9 — eksekusi + PEMBUKTIAN alat drop koleksi legacy
- **BARU** `scripts/verify_fase9_legacy_drop.py` = **24 PASS / 0 FAIL**. Kenapa perlu: di DB preview koleksi
  legacy memang TIDAK ADA ⇒ `--audit`/`--execute` hanya no-op sehingga tidak ada bukti alatnya bekerja.
  Skrip ini MENYUNTIK `wh_opname_sessions` (2 dok) + `wh_opname_items` (3 dok) lalu menguji siklus penuh:
  audit → dry-run (tidak menulis) → **arsip terverifikasi jumlahnya SEBELUM drop** → jurnal `legacy_drop_log`
  → `--logs` → **rollback (dokumen pulih 100%, isi identik)** → rollback kedua ditolak → drop ulang →
  pengaman grup BELUM SIAP (`accessory_legacy` menolak tanpa `--force`) → `--purge-archives` →
  regresi SSOT `wh_opname_sessions2` tak tersentuh & 3 endpoint tetap 200. Semua artefak dibersihkan.
- Eksekusi nyata `--group opname_v1 --execute` di DB ini: **no-op** (kedua koleksi tidak ada) — hasil
  didokumentasikan di panduan; nilai gunanya ada di DB produksi user.
- Tidak ada baris `create_index` untuk kedua koleksi itu di `server.py` ⇒ tidak ada risiko "lahir kembali".

### 2. Modal pengembalian pinjaman (ganti `prompt()`)
- `AccessoryModule.jsx::PeminjamanTab`: `prompt()`/`alert()` native diganti **modal seragam** dengan modal
  Scrap — pilihan **Kondisi barang** (Baik/Rusak/Hilang) + Catatan + validasi inline
  ("Catatan wajib diisi untuk kondisi rusak/hilang (untuk jejak audit).") + pesan sukses
  (`acc-loan-return-msg`) yang menyebut nomor pinjaman & kondisi. `data-testid` lengkap ⇒ bisa diuji otomatis.
- Verifikasi UI (Playwright, dengan 1 pinjaman tiruan lalu dibersihkan): modal terbuka (bukan dialog native),
  validasi kondisi Rusak tanpa catatan MENAHAN submit & modal tetap terbuka, submit dgn catatan →
  "Pinjaman LOAN-…-0001 ditandai kembali · kondisi Rusak. Stok aksesoris dipulihkan."

### 3. Rapor valuasi aksesoris — ekspor Excel & PDF
- **BARU** `backend/utils/accessory_valuation_export.py` (tanpa dependensi baru: openpyxl + reportlab sudah ada):
  header perusahaan, ringkasan, tabel valuasi per item (baris item belum dinilai DISOROT amber),
  tabel mutasi bernilai periode + nomor jurnal, catatan dampak HPP 0. Excel = 2 sheet, PDF = A4 landscape.
- **BARU** `GET /api/acc/valuation/export?format=xlsx|pdf&month=YYYY-MM`. Nilai persediaan = posisi TERKINI
  (saldo), `month` hanya memfilter tabel mutasi (arus) — dijelaskan juga di UI.
- FE tab Valuasi HPP: panel "Rapor valuasi" (pemilih bulan + tombol Excel & PDF + penjelasan) dgn unduhan blob.

### 4. Alarm "belum dinilai" (notifikasi proaktif)
- `core/accessory_valuation.py::notify_unvalued` — dipanggil dari receive/issue/scrap ketika HPP = 0.
  Penerima = role penanggung jawab NYATA (`superadmin/admin/owner/admin_gudang/admin_aksesoris/accounting`),
  lewat SSOT notifikasi (`create_notification` → koleksi `notifications`). Isi menyebut kode item, jumlah,
  dampak (jurnal tidak terbentuk) + langkah perbaikan, plus `source_url=#wh-accessory` untuk deep-link.
- **Anti-spam: maksimal 1 notifikasi per material per 24 jam.** Item yang SUDAH ber-HPP tidak memicu apa pun.
- Kegagalan notifikasi TIDAK PERNAH menggagalkan mutasi stok (dibungkus try/except + diuji).

### 5. BUKTI
- **BARU** `scripts/verify_fase8plus.py` = **24 PASS / 0 FAIL** (alarm: terkirim, isi & tautan benar, Admin
  Gudang termasuk penerima, anti-spam, item ber-HPP senyap, mutasi tetap sukses · rapor: xlsx/pdf 200,
  content-type & filename benar, isi Excel diperiksa dgn openpyxl, month invalid 400, format invalid 422,
  tanpa token 401).
- Regresi: `verify_fase8.py` **48 PASS** (ditambah pembersihan notifikasi), `verify_fase9_legacy_drop.py`
  **24 PASS**, `testing_agent_v3` iteration_170 **backend 100%, 0 critical bug**.
- Verifikasi UI manual: unduhan Excel & PDF nyata (`valuasi-aksesoris-202607.xlsx/.pdf`) + pesan sukses,
  modal pengembalian pinjaman (validasi + sukses).
- `yarn build` Compiled successfully; lint FE 0 error; ruff 0 issue pada file baru.
- **CATATAN**: `testing_agent_v3` melaporkan "data_changes: None" tetapi NYATANYA meninggalkan 3 material
  `ZZTEST-*` + 3 baris stok + 6 notifikasi + 2 JE. Semua sudah dibersihkan manual; DB kembali ke baseline
  (Rp 3.300.000 · 5 baris stok Skema A · 0 notifikasi `stock`). Jangan percaya klaim itu tanpa verifikasi.

### 6. SISA (jujur)
- Masih ada 1 `window.prompt()` di `AccessoryModule.jsx` untuk **alasan menolak opname** (tab Stok Opname,
  di luar lingkup permintaan user). Kandidat penggantian berikutnya dgn pola modal yang sama.
- Grup `accessory_legacy` tetap BELUM SIAP di-drop (prasyarat di panduan §3).


## 2026-07-25 (Session lanjutan — environment dari repo `hanababama/da`) — FASE 6.6 + FASE 8 TUNTAS & TERUJI

> Konteks: environment fresh (template kosong) → clone `https://github.com/hanababama/da` → `rsync` ke `/app`
> (exclude `.env`, `.git`, `node_modules`) → `bash /app/scripts/bootstrap.sh` → build static bundle.
> Keputusan user: lanjutkan **FASE 6.6** (rekonsiliasi baris stok skema lama A/B/C + rename internal `yarn_*`)
> dan **FASE 8** (valuasi HPP aksesoris + panduan drop koleksi legacy). Rencana penuh: `plan.md` §SESI AKTIF.

### 0. RESTORE — kendala & FIX DEFINITIF (perbarui catatan agent sebelumnya)
- `bootstrap.sh` memakai `yarn install --frozen-lockfile` ⇒ `@simplewebauthn/browser` TIDAK terpasang ⇒
  `yarn build` gagal (`Module not found` di `src/pages/AbsenPage.jsx`).
- **Catatan agent sebelumnya ("jalankan `yarn install --prefer-offline` sekali") TIDAK CUKUP** — sudah dicoba
  sesi ini dan paket tetap tidak terpasang. **Fix yang benar-benar bekerja:**
  `cd /app/frontend && yarn add @simplewebauthn/browser@13.3.0` → `yarn build` = *Compiled successfully* (0 warning).
- Baseline setelah restore: backend healthy 12s · seed 5 endpoint OK · login 6 akun HTTP 200 ·
  `scripts/verify_acc123.py` **62 PASS / 0 FAIL** (state repo utuh).

### 1. FASE 6.6-A — Rekonsiliasi baris stok skema lama A/B/C
Masalah: `rahaza_material_stock` historis ditulis 3 bentuk — **A** `{material_id, location_id, qty}` (kanonik),
**B** lokasi BERSARANG `location:{id}` + `total_qty` (domain aksesoris lama), **C** tanpa lokasi + `available_quantity`
(alur FG/CMT lama). Writer sudah satu pintu sejak FASE 2, tapi baris WARISAN di DB berjalan membuat layar
per-lokasi (Put-Away, Opname per-bin, peta gudang) kehilangan stok + baris kembar + `available` basi.
- **BARU** `backend/core/stock_reconcile.py` — deteksi 7 penyakit (`nested_location`, `missing_location`,
  `alias_drift`, `available_drift`, `duplicate_rows`, `negative_qty`, `orphan_material`), `scan()` read-only,
  `reconcile(dry_run)`, `rollback(log_id)`, `logs()`. Jurnal `wh_stock_schema_reconcile_log` menyimpan
  before/after per baris ⇒ rollback presisi. **TIDAK PERNAH mengubah total on-hand** (diverifikasi).
- `negative_qty` & `orphan_material` sengaja **LAPOR SAJA** (butuh Opname/Penyesuaian resmi — keputusan manusia).
- **BARU** `backend/routes/wms_stock_schema.py` (`/api/wms/stock-schema/health|reconcile|reconcile/rollback|logs`).
  RBAC: health = semua yang login; reconcile/rollback = admin/owner/admin_gudang (HR 403 pesan ramah).
- **BUG NYATA yang ketemu & difix saat uji**: `rahaza_material_stock` punya **UNIQUE index (material_id,
  location_id)**. Pola kembar NYATA = 1 baris kanonik + 1 baris warisan (lokasi nested ⇒ ter-index null).
  Saat baris warisan dinormalkan, `location_id`-nya jadi SAMA ⇒ urutan "tulis dulu lalu hapus" memicu
  `DuplicateKeyError`. **Fix**: eksekusi menghapus baris yang digabung LEBIH DULU, baru menulis hasil
  normalisasi; rollback dibalik urutannya (pulihkan baris ternormalisasi dulu, baru hidupkan baris terhapus).
- **BARU** `backend/migrations/migrate_reconcile_stock_schema.py` (`--dry-run`/`--execute`/`--rollback`/`--logs`).
- **BARU** FE `StockSchemaHealthModule.jsx` → modul `wh-stock-schema` + **tab "Kesehatan Skema"** di hub
  `wms-stock-hub`: KPI, kartu bentuk baris A/B/C, banner sehat/amber + daftar penyakit & penjelasannya,
  tombol Pratinjau → konfirmasi → Terapkan, tabel detail (paginasi 10/hal), riwayat + tombol Rollback.

### 2. FASE 6.6-B — Rename internal `yarn_*` → field netral (alias kompatibilitas)
Alasan: taksonomi resmi sudah netral (Bahan · Aksesoris · Produk Jadi) sejak FASE 1, tapi nama field masih
warisan pabrik benang ⇒ menyesatkan untuk kain/aksesoris. Ditunda sejak FASE 5 (5.4), sekarang dieksekusi.
- **BARU** `backend/core/material_fields.py` (SSOT): peta `FIELD_ALIASES` + `read_field` (fallback kanonik→legacy)
  + `mirror` / `mirror_from_body` / `with_aliases`, PLUS SSOT taksonomi tipe material (`TYPE_TO_CATEGORY`,
  `KGLIKE_TYPES`) yang sebelumnya disalin di 4 file.
- **BARU** `frontend/src/lib/materialFields.js` (pasangan FE: `readField`, `readNumber`, `mirrorField`, label ID).
- Peta rename (legacy TETAP ditulis sebagai alias ⇒ 0 breaking change):
  `yarn_type`→`composition` · `yarn_kg_per_pcs`→`material_kg_per_pcs` ·
  `default_yarn_cost_per_kg`→`default_material_cost_per_kg` · `total_yarn_kg_per_pcs`→`total_material_kg_per_pcs` ·
  `total_yarn_kg`→`total_material_kg` · `yarn_count`→`bulk_line_count`.
- Writer/reader di-mirror: `rahaza_inventory_materials.py` (create+update+list), `rahaza_bom.py` (enrich, matrix,
  preview), `rahaza_material_requirements.py` (totals + costing settings), `rahaza_hpp.py` (settings + compute),
  `rahaza_production.py` (model), `production_internal_adapter.py`, `marketing_catalog_items.py`,
  `marketing_catalog_backup.py`, `marketing_product_launches_routes.py`, `data_transfer.py` (template ekspor/impor),
  seeder `rahaza_setup.py` + `maklon_seed.py`.
- FE dialihkan ke nama kanonik + label Indonesia: `RahazaMaterialsModule` (field **Jenis/Komposisi**,
  `data-testid=mat-field-composition`), `bom/InlineMaterialPicker`, `RahazaModelsModule` (kolom
  **Bahan utama/pcs (kg)**), `RahazaBOMModuleV2`, `bom/VersionRail` ("N bahan", bukan "N benang"),
  `bom/RequirementsPreviewCard` (**Total bahan (kg)**), `RahazaHPPModule` (**Default Bahan/kg**),
  `RahazaMaterialRequirementsModule` (**Total Bahan (kg)**), `CatalogManagementModule`.
- **BARU** `backend/migrations/migrate_rename_yarn_fields.py` (`--discover`/`--dry-run`/`--execute`/`--rollback`).
  Dijalankan di DB preview: 5 dokumen `rahaza_materials` di-backfill `composition`; verifikasi bersih.

### 3. FASE 8 — Valuasi HPP Aksesoris
Masalah: HPP master aksesoris sudah ada (FASE G+) & opname sudah berjurnal (FASE G), TAPI mutasi harian
(terima/keluar/scrap) **tidak pernah dinilai** ⇒ nilai persediaan aksesoris ≠ buku besar, dan item ber-HPP 0
diam-diam membuat jurnal tidak terbentuk tanpa penjelasan.
- **BARU** `backend/core/accessory_valuation.py` — `resolve_unit_cost`, `moving_average` (WAC),
  `apply_receipt_cost` (update HPP master + riwayat `rahaza_material_cost_history`), `set_unit_cost` (koreksi
  manual + riwayat), `summary` (per item + per kategori + total + item belum dinilai), `cost_history`.
  Aturan aman: harga masuk ≤ 0 ⇒ HPP TIDAK diubah; stok lama ≤ 0 ⇒ HPP = harga masuk.
- **BARU** `backend/core/stock_rbac.py` — SSOT `DISPOSE_ROLES` / `SCRAP_ROLES` (dipindah dari
  `wms_quarantine.py`, sekarang dipakai bersama scrap aksesoris; komentar sejarah role-hantu dipertahankan).
- `dewi_accessories_stock.py`: `_log_movement` kini membawa `unit_cost` + `value` (+ `qty` bertanda supaya
  poster jurnal generik bisa memakainya); `/stock/receive` menerima `unit_cost`/`total_cost` → WAC + jurnal
  `inventory_receive`; `/stock/issue` bernilai + jurnal pemakaian; **`POST /stock/scrap` BARU**
  (RBAC ketat, wajib alasan, jurnal `inventory_adjust` reason=scrap ⇒ Dr Beban Scrap 6-4300 / Cr Persediaan).
  Semua posting **non-fatal & transparan**: gagal ⇒ `je.posted=false` + alasan (stok tetap tercatat).
- **BARU** `routes/rahaza_posting.py::post_accessory_issue` (mapping `inventory_issue`, idempoten
  `source_ref=accmv:<id>`) — pengeluaran aksesoris tidak lewat dokumen Material Issue, jadi butuh poster sendiri.
- **BARU** `routes/dewi_accessories_valuation.py` — `GET /api/acc/valuation`, `/valuation/movements`,
  `/valuation/cost-history`, `POST /valuation/set-cost` (RBAC = SCRAP_ROLES).
- `/api/acc/stock` + `/api/acc/dashboard` membawa `unit_cost`/`stock_value`/`valued` dan
  `total_stock_value`/`unvalued_items`.
- **BARU** FE `accessory/AccessoryValuationTab.jsx` + `accessory/AccessoryValuationLedger.jsx` → tab
  **"Valuasi HPP"** di Portal Aksesoris: 4 KPI, banner "item belum dinilai" + filter, tabel HPP/Nilai/Metode,
  modal **Set HPP** & **Scrap** (preview nilai write-off + validasi alasan), rekap per kategori,
  sub-tab **Mutasi Bernilai** (kolom Jurnal) + **Riwayat HPP**.
- `AccessoryModule.jsx`: modal Terima Stok dapat input **Harga satuan beli (opsional)** + pesan hasil
  (`acc-move-result`) yang menyebut perubahan HPP & status jurnal. **KPI "Dipinjam" (sisa domain lama, selalu 0
  sejak ACC-3 pindah ke Portal Aset) DIGANTI** menjadi **Nilai Persediaan** + **Belum Dinilai** — sekaligus
  menutup item bersih-bersih #4 di daftar "berikutnya" FASE 7.

### 4. FASE 8.8 — Panduan drop koleksi legacy
- **BARU** `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` — 6 prinsip keras (arsip dulu, nol konsumen sebagai
  SYARAT, hapus indeks di `server.py` agar koleksi tidak lahir kembali, 1 grup per sesi, diamkan 1 minggu),
  tabel 4 grup kandidat + status kesiapan, prasyarat grup `accessory_legacy` yang BELUM siap, checklist
  eksekusi, dan syarat menghapus alias field `yarn_*` di fase terpisah.
- **BARU** `backend/migrations/drop_legacy_collections_guided.py` — `--audit` (jumlah dokumen + hitung rujukan
  kode aktif per koleksi), `--dry-run`/`--execute` per grup (arsip `legacy_archive_<nama>_<ts>` + verifikasi
  jumlah SEBELUM drop), `--rollback <log_id>`, `--purge-archives`. Grup yang ditandai BELUM SIAP menolak jalan
  kecuali `--force`.

### 5. BUKTI PENGUJIAN
- **BARU** `scripts/verify_fase66.py` = **48 PASS / 0 FAIL** (isolated, self-clean): 7 penyakit terdeteksi,
  dry-run tidak menulis, eksekusi membenahi bentuk + menggabungkan kembar dgn **total on-hand TETAP**,
  report-only tidak diubah, idempoten, rollback presisi (termasuk memulihkan bentuk nested), RBAC HR 403.
- **BARU** `scripts/verify_fase8.py` = **48 PASS / 0 FAIL** (isolated, self-clean): WAC 1.000+2.000⇒1.500,
  jurnal terima/keluar/scrap **SEIMBANG Dr=Cr**, scrap men-debit akun beban 6-xxxx, validasi negatif,
  RBAC HR 403 (pesan ramah), koreksi HPP manual + riwayat, transparansi item tanpa HPP, KPI dashboard.
- Regresi: `verify_acc123.py` **62 PASS** · `verify_phase6_quarantine.py` **48 PASS** (artefak dibersihkan
  via `cleanup_test_f6.py --apply` + 1 sisa `rahaza_grn_inspections` TEST-F6 dihapus manual).
- `testing_agent_v3` iteration_169: **backend 100%**, frontend 100%, **0 critical bug**.
- **Verifikasi UI manual oleh main agent (Playwright, alur yang tidak dijalankan agent):** rekonsiliasi
  Pratinjau→Terapkan→banner sehat→Rollback (semua dari UI, pesan benar) · Set HPP 100→250 · validasi scrap
  tanpa alasan (pesan merah inline, modal tetap terbuka) · scrap 5 pcs ⇒ "nilai Rp 1.250 · jurnal JE-…-0015
  di-posting" · Terima 95 @400 ⇒ "HPP Rp 250 → Rp 325 (rata-rata bergerak) · jurnal di-posting" · kartu stok
  bernilai + riwayat HPP · form material menyimpan Komposisi & tampil di kolom Warna/Jenis · BOM matriks
  "Bahan /pcs 0.250 kg" + "1 bahan · 1 aksesoris" · HPP settings simpan-reload-kembalikan · sapu 14 modul
  Portal Gudang + 6 tab hub Stok & Akurasi = 0 crash / 0 "Pilih Portal" / 0 page error.
- Lint: FE **0 error** (npx eslint), ruff **0 issue** pada semua file baru sesi ini, `yarn build`
  *Compiled successfully* (0 warning). DB dikembalikan ke baseline (3 item aksesoris · Rp 3.300.000 ·
  5 baris stok semua Skema A sehat · costing settings 0).

### 6. CATATAN JUJUR / SISA
- Alias legacy `yarn_*` MASIH ditulis (by design, backward compat). Syarat menghapusnya ada di panduan §5.
- Grup `accessory_legacy` (`acc_loans`, `acc_internal_requests`) BELUM siap di-drop — prasyarat di panduan §3
  (tutup semua pinjaman aktif + hapus tab deprecated + hapus indeks di `server.py`).
- Tab deprecated `#accessories-loans` masih memakai `prompt()`/`alert()` untuk pengembalian pinjaman LAMA
  (0 data ⇒ jalur tak tereksekusi). Masih terbuka sebagai bersih-bersih berikutnya.
- Di DB preview semua koleksi legacy kandidat memang TIDAK ADA ⇒ skrip drop no-op; nilai gunanya ada di DB
  produksi user.


## 2026-07-25 (Session lanjutan — environment dari repo `cabanamama123/da`) — FASE 7: 3 gantungan AKSESORIS (ACC-1/2/3) TUNTAS & TERUJI

> Konteks: environment fresh (template kosong) → clone `https://github.com/cabanamama123/da` → `rsync` ke `/app`
> (exclude `.env`, `.git`, `node_modules`) → `bash /app/scripts/bootstrap.sh` → `yarn install --prefer-offline`
> (lockfile repo out-of-sync ⇒ `@simplewebauthn/browser` hilang ⇒ build FE gagal) → `bash /app/scripts/rebuild_frontend.sh`.
> Kode ACC-1/2/3 sudah ada dari sesi sebelumnya; sesi ini = VERIFIKASI + menutup lubang nyata + menyelesaikan uji UI
> yang sesi lalu terblokir. Detail lengkap: `plan.md` §FASE 7.

### 0. PELAJARAN PENTING (akar "bug" UI palsu)
- Temuan sesi lalu "deep-link `#asset-loans` mendarat di **Pilih Portal**" **BUKAN bug kode** — penyebabnya
  `frontend/build/` masih bundel LAMA (mode STATIC BUNDLE). Setelah `rebuild_frontend.sh`: logout → `#asset-loans`
  → login → mendarat tepat di tab Peminjaman. **Selalu rebuild sebelum menyimpulkan modul baru "tidak ter-route".**
- Temuan "GET /api/assets/loans 200 tanpa token" = **false positive** (dilaporkan 2 iterasi berturut-turut).
  `auth.verify_token` HANYA membaca header `Authorization`; tak ada fallback cookie/query/session. Dibuktikan 401
  pada 6 kombinasi (preview & localhost × curl polos / header kosong / `requests.get` tanpa session). Penyebab
  laporan: HTTP client penguji memakai session yang sudah menyimpan header Authorization dari langkah login.

### 1. ACC-3 — peminjaman: menutup lubang "masih bisa membuat pinjaman di domain salah"
- `routes/dewi_accessories_loans.py`: **`POST /api/acc/loans` → 410** dgn pesan arahan ke Manajemen Aset.
  `GET /api/acc/loans` & `PUT /api/acc/loans/{id}/return` TETAP hidup (pinjaman historis harus bisa ditutup).
  Alasan: tombol "Catat Peminjaman" di menu lama masih membuat pinjaman yang **mengurangi stok aksesoris** —
  yaitu persis bug yang ACC-3 seharusnya hapus.
- `AccessoryModule.jsx`: tombol `add-loan-btn` jadi jalan pintas "Catat Peminjaman di Manajemen Aset";
  form pembuatan + handler mati dihapus (**107 baris dead code**).
- `portalNav.js`: label seksi `REQUEST, PINJAM & PENGADAAN` → `REQUEST & PENGADAAN`.
- `LoansTab.jsx` + `KPICard.jsx`: KPI dapat `data-testid` (`asset-loan-kpi-active/-overdue/-returned/-available`
  + `-value`). `CreateLoanDialog.jsx`: validasi menyebut SEMUA field wajib yang kosong sekaligus
  ("Aset & Nama Peminjam wajib diisi.") alih-alih satu per satu.

### 2. ACC-2 — BUG RBAC + BUG DATA + UX banner
- **BUG RBAC (temuan `testing_agent` iteration_166, VALID):** `POST /api/rahaza/boms/relink-materials` memakai
  `_require_admin` modul BOM yang SENGAJA longgar (keputusan lama: master produk boleh di-CRUD SEMUA staff
  internal) ⇒ **HR bisa menjalankan perbaikan MASSAL** yang menulis ulang `material_id` di SELURUH BOM.
  Fix: guard baru `_require_bom_repair` + `BOM_REPAIR_ROLES` (admin/owner/manager_produksi/admin_produksi/
  supervisor_produksi/supervisor/rnd_staff). HR → 403 pesan ramah; `GET /boms/link-health` (audit read-only)
  tetap 200. Uji ini DITAMBAHKAN ke `scripts/verify_acc123.py`.
- **BUG DATA (temuan main agent):** `routes/rahaza_setup.py` & `routes/maklon_seed.py` menulis baris BOM dgn
  `material_id: None`, dan kode aksesoris demo (`ACC-BTN-12`, `ACC-LBL-01`, `ACC-DA-LBL`) **tidak pernah dibuat**
  di master material ⇒ `link-health` selamanya `healthy:false` DAN "Perbaiki Otomatis" tak bisa menolong (kode tak
  dikenal). Fix: kedua seeder memastikan master material ada LEBIH DULU lalu mengisi `material_id`; `rahaza_setup`
  juga self-heal BOM lama by-code; `scripts/bootstrap.sh` menjalankan `backend/scripts/link_demo_bom_materials.py`
  sebagai jaring pengaman DB lama. Terverifikasi: 3 BOM sengaja di-null-kan → re-seed → `healthy:true`.
- **UX `RahazaBOMModuleV2.jsx`:** banner `bom-link-health-banner` dulu **hilang total saat sehat** ⇒ user tak
  pernah dapat konfirmasi rantai BOM→kebutuhan→stok utuh. Sekarang selalu tampil: amber (ada baris lepas,
  tombol "Perbaiki Otomatis") / emerald ("Kopling BOM sehat — N baris (M aksesoris) di K BOM", tombol
  "Periksa Ulang"). Tambah kolom **Taut** di tabel viewer (`bom-viewer-mat-<idx>-linked/-unlinked`) agar status
  kopling terlihat tanpa masuk mode Edit. Kotak error editor: `data-testid=bom-form-error` + kontras diperbaiki
  (dulu `text-red-300` di atas latar terang ⇒ nyaris tak terbaca di tema terang).

### 3. ACC-1 — UX pesan hasil "Buat Permintaan"
- `ProductionPOModule.jsx`: hasil aksi tidak lagi `alert()` native (memblokir UI & automation) → pesan INLINE
  `data-testid=po-acc-req-message` (emerald sukses menyebut kode `INT-REQ-…`, merah untuk anti-dobel).
  Bug kecil yang ikut diperbaiki: refresh setelah sukses sempat MENGHAPUS pesan suksesnya sendiri
  (`loadAccReq` kini punya opsi `keepMessage`). Tombol Detail baris PO dapat `data-testid=po-detail-btn-<po_id>`.

### 4. Lintas-fitur — `SmartNativeSelect` akhirnya bisa diotomasi + lebih aksesibel
`components/ui/smart-native-select.jsx` bukan `<select>` native dan opsinya `<button>` tanpa penanda ⇒ SEMUA
dropdown custom di aplikasi tak bisa dikemudikan agent (sebab historis kenapa alur pinjam/kembalikan & beberapa
alur Fase 6 selalu dilaporkan "tidak bisa diotomasi"). Sekarang bila caller mengirim `data-testid="x"`:
`x` (root) · `x-trigger` (role=combobox, aria-expanded, data-value) · `x-list` (role=listbox) ·
`x-option-<value>` (role=option, aria-selected, data-value). Pola uji: klik `x-trigger` → klik `x-option-<value>`.

### 5. BONUS — 8 bug nyata lain (tersingkap setelah tooling lint dihidupkan kembali)
Gate pra-selesai menolak karena **ESLint mati total**: `ManagementToolsModule.jsx` punya karakter `>` mentah
di teks JSX ("Rak >90% Penuh") sehingga parser ESLint gagal (build CRA tetap jalan, jadi tak pernah terasa).
Setelah diperbaiki, lint langsung menyingkap **45 error nyata** di modul yang TIDAK tersentuh sesi ini.
Semua diperbaiki & diverifikasi di UI — lint frontend kini **0 error**:
1. **`HRPerformanceModule.jsx` MODUL MATI** — `cycleDialog`/`setCycleDialog` dipakai 12+ tempat tapi
   `useState`-nya tidak pernah dideklarasikan ⇒ ReferenceError saat render. (Terverifikasi: modul render,
   dialog "Cycle Penilaian Baru" terbuka.)
2. **`EmployeeExpenseModule.jsx` FORM KLAIM MATI** — konstanta `CATEGORIES` dihapus saat refactor Phase 4.5
   tapi pemakaiannya tidak ⇒ dialog "Klaim Baru" crash ⇒ klaim biaya tak bisa dibuat dari UI. Endpoint
   `GET /api/hr/expenses/categories` sudah ada tapi tak pernah dipanggil. Fix: ClaimForm memuat kategori
   COA + fallback. (Terverifikasi: dropdown terisi akun 6-3xxx.)
3. **`PurchaseOrderModule.jsx`** — `loadList()` tidak ada ⇒ setelah bulk import PO SUKSES user malah melihat
   toast "Gagal import PO" & daftar tak refresh. Fix: `fetchList()`.
4. **`CatalogManagementModule.jsx`** — 5 kunci objek duplikat di initial-state form (selalu ditimpa) dibersihkan.
5. **`eslint.config.js`** — globals jest/node untuk `setupTests.js` + ignore `_archive/**` (kode arsip).
6. **DEEP-LINK DEAD-END SISTEMIK ditutup di akar** — audit baru `scripts/audit_deeplink_portals.py` menemukan
   **121 dari 356** id `MODULE_REGISTRY` mendarat di "Pilih Portal" (mis. `#hr-performance`, `#fin-coa`,
   `#maklon-qc`, `#toko-orders`, `#wh-materials`). Ini bug yang sudah 3× ditambal manual per-id.
   Fix: lapis ke-3 `portalFromModulePrefix()` di `App.js` (`hr-*`→hr, `fin-*`→finance, `wh-*|wms-*`→warehouse, …)
   yang hanya jalan setelah pencarian nav gagal + tetap lewat `canAccessPortal`; 4 id tanpa prefix portal
   ditambahkan manual. Hasil: **0 dead-end**.
7. **`frontend/static_server.js`** — retry saat `EADDRINUSE` (dulu uncaughtException → restart-loop → preview
   502 beberapa detik setiap rebuild).

### 6. Bug tooling: ESLint mati bila dijalankan dari ROOT repo
`frontend/eslint.config.js` hanya berlaku dari dalam `frontend/`. Dari ROOT repo (dipakai gate/CI) ESLint v9
mati: "couldn't find an eslint.config.js" ⇒ **linter engine error**, gate lint gagal tanpa memeriksa kode.
Fix: `/app/eslint.config.js` baru yang MEMUAT config frontend + rebase glob ke `frontend/…` (tanpa duplikasi
aturan; resolusi modul tetap ke `frontend/node_modules`) + ignore root (`mobile/**` punya config expo sendiri,
`frontend/plugins/**`, `uploads/**`, `refs/**`, `backups/**`, `docs/**`, `_archive/**`) + blok Node CJS untuk
file config root. Hasil: `cd /app && npx eslint .` → **587 file, 0 error**.

### Bukti
- Isolated: `python /app/scripts/verify_acc123.py` → **62 PASS / 0 FAIL**.
- `testing_agent_v3` iteration_167 (ronde 2): **backend 100% (28/28)**, frontend 95%, **0 critical bug, 0 action item**.
- 3 alur UI yang tak dijalankan agent diverifikasi manual (Playwright) oleh main agent — semua LULUS:
  pinjam dari form (dropdown hanya aset siap; KPI 1→2 & 2→1), kembalikan kondisi Rusak (wajib catatan →
  aset `in_maintenance` + catatan maintenance otomatis), editor BOM menolak baris aksesoris lepas
  ('… Belum tertaut: baris 4 "QA Kancing Ngawur".'), dan pesan anti-dobel permintaan aksesoris.
- Fixture demo `TEST-AU` dikembalikan ke kondisi awal setelah pengujian (2 aset siap, 1 pinjaman TERLAMBAT,
  0 permintaan aksesoris, `link-health` healthy). Data `DEMO-*` tidak disentuh.


## 2026-07-25 (Session lanjutan — environment BARU dari repo `babakaana/da`) — FASE G+ : P0 fix ringkasan Opname Aksesoris + transparansi jurnal + harga satuan master

> Konteks: environment fresh (template kosong). Repo di-clone (`https://github.com/babakaana/da`) → `rsync` ke `/app` (exclude `.env`, `.git`, `node_modules`) → `bash /app/scripts/bootstrap.sh` (deps + build static bundle + seed + verifikasi login 6 akun) = OK.
> **Mode frontend WAJIB static bundle** (`frontend/package.json` → `"start": "node static_server.js"`); setelah ubah `frontend/src` jalankan `bash /app/scripts/rebuild_frontend.sh`. Container 1 CPU/2GB → dev server (`craco start`) menyebabkan pod restart loop. Lihat `memory/PREVIEW_STABLE_MODE.md`.

### 1. P0 BUG FIXED — ringkasan sesi Opname Aksesoris selalu "0"
- **Akar masalah:** `backend/routes/dewi_accessories_opname.py::_wh_session_to_acc` (serializer WH-session → bentuk API aksesoris) tidak memetakan field approval/finance. FE `AccessoryModule.StokOpnameTab` membaca `je_posted`, `total_variance_value`, `total_variance_items`, `approved_by`, `reject_reason` → semuanya `undefined` → UI menampilkan "0 jurnal keuangan · nilai selisih 0" walau backend sudah benar.
- **Fix:** serializer kini mengembalikan `raw_status`, `total_variance_items`, `total_variance_value`, `je_posted`, `je_failed`, `je_failed_items`, `adjustments_made`, `counted_by`, `submitted_by/at`, `approved_by/at`, `rejected_by/at`, `reject_reason`, `summary` (+ `completed_by/at` dipertahankan).

### 2. Transparansi posting jurnal (`je_failed`)
- `approve_opname` menghitung `je_failed` + `je_failed_items` (`{material_id, code, name, delta, reason}`) — penyebab tersering `Amount adjust = 0 (set unit_cost material)`. Dikembalikan di response approve & di serializer list/detail.
- FE `StokOpnameTab`: baris peringatan amber (`data-testid=opname-je-warning-<id>`) + detail pada `alert` saat approve. **Stok tetap disesuaikan**, hanya JE yang dilewati → sekarang eksplisit, tidak silent.

### 3. FASE G+ — harga satuan (`unit_cost`) di master aksesoris (akar masalah JE gagal)
- Master aksesoris sebelumnya TIDAK punya field harga sama sekali → nilai selisih opname selalu 0 → JE tak mungkin terbentuk.
- `backend/routes/dewi_accessories_items.py`: `create_item`/`update_item` menerima `unit_cost` (alias `hpp`); serializer mengembalikan `unit_cost` + `stock_value` (= qty × unit_cost).
- FE `AccessoryModule.MasterTab`: input **"Harga Satuan / HPP (Rp)"** (`data-testid=acc-unit-cost-input`) + kolom tabel **"Harga Satuan"** & **"Nilai Stok"**; item tanpa harga ditandai "belum diisi" (amber, tooltip menjelaskan dampak ke jurnal).

### 4. REGRESI FIXED — `stock_status` hilang pada serializer item aksesoris
- Setelah pemecahan monolit `dewi_accessories_full.py`, `_material_to_acc_item` di `dewi_accessories_items.py` berhenti mengirim `stock_status` → FE menampilkan badge **"Habis" untuk SEMUA item** (termasuk stok 1.820 pcs) dan kartu Aman/Rendah/Habis = 0.
- Fix: `stock_status` = `out` (qty≤0) / `low` (min_stock>0 & qty≤min_stock) / `ok`, sama dengan konvensi lama & `dewi_accessories_dashboard.py`.

### 5. Dead-code cleanup
- `_material_to_acc_item` duplikat & TAK TERPAKAI dihapus dari 6 file: `dewi_accessories_dashboard/loans/opname/purchase/requests/stock.py` (residu copy-paste saat monolit dipecah; SSOT serializer tinggal di `dewi_accessories_items.py`). Verified: 0 pemanggil, 0 import lintas modul, `py_compile` OK.

### Bukti
- Isolated: `/app/scripts/verify_phase_g_acc_opname.py` → **45 PASS / 0 FAIL** (start→count→submit→approve/reject, gate HR=403, stok tak berubah saat submit & reject, JE `inventory_adjust` Dr=Cr di `rahaza_journal_entries`, `je_failed` transparan, `unit_cost` create/update, nilai selisih 2×3.000=6.000, `stock_status` semua benar, `/complete` = alias submit deprecated).
- `testing_agent` iteration_163: **backend 100% (45/45), frontend 100%, 0 bug**.
- Screenshot: `#accessories-opname` → "Disetujui oleh Supervisor Produksi · 2 penyesuaian · 1 jurnal keuangan · nilai selisih Rp 2.500" + peringatan amber; "Ditolak: QA: hitungan meragukan". `#accessories-master-stock` → kolom Harga Satuan/Nilai Stok + badge status benar.
- CATATAN DATA: item `QA-*` & sesi `OPNAME-000x/001x` di DB preview adalah **artefak verifikasi** (DB fresh seed), boleh dibersihkan atas persetujuan user.


## 2026-07-21 (Session cont.) — Audit "sisa backlog" (T-1..T-5 & CMT Phase B/C) + doc hygiene

> User: "coba analisis kembali T-1..T-5 (mungkin by-design, cek logic); CMT Phase B/C harusnya sudah selesai; kalau dokumen menyesatkan update/arsipkan." Hasil: semua sudah dieksekusi & logika benar → dokumen distale-flag/di-update.

### Verifikasi T-1..T-5 (semua sudah dieksekusi, logika BENAR)
- **T-1 opname**: by-design, **bukan split-brain**. Material (`wms_opname2.py`) & aksesoris (`dewi_accessories_opname.py`) berbagi koleksi `wh_opname_sessions2` tapi dipartisi field `domain`: material query `{$or:[domain∄, domain≠accessory]}`, aksesoris query `{domain:"accessory"}`. Aksesoris snapshot `rahaza_materials type=accessory`, adjustment → SSOT stock + movement log. Konsisten.
- **T-2** `AccessoryRequestInbox.jsx`: `isRndMonitor = moduleId==='rnd-accessory-requests'` → read-only monitor (filter rnd_sample, aksi fulfillment disembunyikan). Benar.
- **T-3** `KREATORRequestModule.jsx`: `scope` dari `moduleId` + `isRnd = isRndScope || roleIsRnd`, `actor = currentUser||user` (fix bug laten tombol approve RnD). Benar.
- **T-4** `HRApprovalInboxModule.jsx`: cross-link ke `hr-attendance-hub` (kept by-design). **T-5**: label disambiguation ("Ruang Kerja Saya"/"Workspace Spreadsheet"). Benar.
- Keputusan tercatat di `IA_RESTRUCTURE_PROPOSAL.md §8.1`.

### Verifikasi CMT-flow Phase A/B/C — SUDAH SELESAI (runtime re-verified 2026-07-21)
- `GUIDELINE_CMT_FLOW.md §15`: Phase A (07-16), B (07-17), C (07-18) COMPLETED. Marker kode dikonfirmasi (`receiver_type`/`source_receipt_ids`, `close-short`/`closed_reason`/K5 410 gates, FE DAReceiveFromCMT/POClosure).
- **Re-run E2E hari ini**: `scripts/test_phase_b_e2e.py` → **ALL PASS**; `scripts/test_phase_c_e2e.py` → **ALL PASS (S7/S8/S8b/S9)**.

### Doc hygiene (dokumen menyesatkan → di-update, tidak dihapus)
- `BACKLOG_PLAN.md`: banner status atas = semua ITEM SELESAI (dokumen ditutup/arsip).
- `HANDOFF_NEXT_AGENT.md`: banner status atas men-supersede entri lama; tegaskan T-1..T-5 & CMT B/C sudah selesai (label "PERLU-KEPUTUSAN" lama = usang).
- `GUIDELINE_CMT_FLOW.md`: banner "✅ SELESAI & VERIFIED" di header §10 (Phase B) & §11 (Phase C).
- `IA_RESTRUCTURE_PROPOSAL.md`: banner RESOLVED di atas §7.2 (arahkan ke §8.1).

### Minor fix
- `UnifiedInventoryModule.jsx`: warning React "unique key prop" → key baris dibuat komposit unik (`id/material_id-category-ownership-location-idx`).


## 2026-07-21 (Session cont.) — BACKLOG_PLAN.md formal items 1/2/3.1/3.2 SELESAI

> Lanjutan "selesaikan semua backlog". Backlog formal (BACKLOG_PLAN.md) tuntas. Item incremental (CTA/pagination) & decision-gated (T-1..T-5, CMT Phase B/C) menyusul/ butuh keputusan user.

### ITEM 1 [P1] — CRUD Edit/Hapus Manajemen CMT — SELESAI
- Kode sudah jauh berkembang dari doc audit 2026-07-16 (PUT/DELETE partners & accounts sudah ada). Ditutup gap tersisa (grounded ke kode nyata, bukan doc):
  - `vendor_portal.py`: `PUT /partners/{id}` kini menangani `is_active` (reactivate, I-VP-5); `DELETE /partners/{id}` kini **soft-delete** default (guard I-VP-1 akun aktif / I-VP-2 job berjalan) + opsi `?hard=true` (guard referensial penuh).
  - Frontend `VendorAccountsAdminModule.jsx` PartnersTab: badge Aktif/Nonaktif + tombol toggle Power (nonaktifkan↔aktifkan) + hard-delete (Trash) sejajar pola AccountsTab. `data-testid`: partner-toggle/-edit/-delete/-status.
  - Verifikasi curl 8/8 skenario (guard aktif→400, soft-del→200, reactivate, hard-del guard→400, hard-del sukses).

### ITEM 2 [P2] — Format Angka Rupiah Global — bug parsing SELESAI
- **Root cause diperbaiki**: `marketing_import.py._convert_value` (parsing locale salah). 
- **SSOT baru** `backend/utils/money.py`: `parse_id_number` / `parse_id_int` / `format_idr` (locale ID: '.'=ribuan, ','=desimal; toleran currency/US/parentheses). 14/14 unit test PASS ("Rp 150.000"→150000, "1.234.567,89"→1234567.89, "150,5"→150.5, "(1.000)"→-1000, dll).
- Frontend `lib/format.js`: tambah counterpart parse `parseIDNumber`/`parseRupiah` (format sudah SSOT sebelumnya). Rollout ganti input finance per-modul = migrasi bertahap (sudah ada SSOT, tidak diubah massal demi keamanan).

### ITEM 3.1 [P2] — WS-G6 dead-code cleanup — SELESAI
- Hapus fungsi orphan `post_wip_to_fg_on_wo_complete` (`rahaza_posting.py`), ganti tombstone. Tak ada referensi di kode live (hanya `_archive` yg tak di-import). Jalur aktif = `post_wip_to_fg_on_job_complete`.
- Test baru `backend/tests/test_wip_to_fg_on_job_complete.py` (idempotency, Dr 1-1404 / Cr 1-330 balanced) — PASS.

### ITEM 3.2 [P3] — WS-F dokumentasi — SELESAI
- `/app/ARCHITECTURE.md` baru: Domain Registry (grounded ke 177 koleksi DB live), cross-domain posting flows F1–F5, bridge modules, anti-duplikat glossary, konvensi teknis. Cross-ref (tidak duplikat) `GUIDELINE_CMT_FLOW.md`.


## 2026-07-21 (Session cont.) — Maklon DP posting fix VERIFIED + posting-profile audit + role-accounts seed

> Env restored from fresh clone (JWT_SECRET set, deps installed, frontend static bundle rebuilt & served). Independent testing agent (iter#137) = **7/7 PASS**.

### BUG (class: posting to NON-POSTABLE account) — maklon_advance_payment — FIXED at 3 levels
- **Root cause**: `maklon_advance_payment` mapping credited `2-1300` "Hutang Pajak" which is a **non-postable header** (`is_group=True`) and debited `1-110` (Kas Kecil, wrong for a bank DP). Endpoint previously hardcoded `2-1300`.
- **Fix 1 (endpoint, already committed)** `routes/dewi_maklon_finance.py`: resolves accounts from the `maklon_advance_payment` profile, validates each is a postable leaf via `_postable()`, falls back to **Dr `1-131` (Bank) / Cr `2-140` (Uang Muka Diterima – Maklon)**.
- **Fix 2 (seed source)** `routes/rahaza_posting_profiles.py` `DEFAULT_PROFILES`: corrected `maklon_advance_payment` mapping to `1-131` / `2-140` so **fresh clones seed the correct postable accounts** (previously re-seeded the buggy `1-110`/`2-1300`).
- **Fix 3 (DB row)**: updated the already-seeded `rahaza_posting_profiles` row to `1-131`/`2-140`.
- **Verified**: DP posting → JE `posted`, balanced (Dr==Cr), Dr `1-131` / Cr `2-140`, no `2-1300`. AR-invoice regression returns clean 400 (not 500) for draft PO. Idempotent multi-DP OK.

### AUDIT — no other instance of this bug class
- Every account code in all 33 DB posting profiles (79 refs) + `DA_POSTING_PROFILES` (90 refs) + all hardcoded posting fallbacks in `routes/`/`services/` → confirmed **postable, active leaves**. Only false-positives are group headers inside the CoA-tree definition files (`rahaza_coa.py`, `coa_auto.py`, `data_transfer.py`) — by design.

### Minor (from testing) — RBAC role accounts seeded
- `scripts/seed_role_accounts.py` run → `{hr,finance,spv,gudang,maklon}@dewiaditya.id` / `Dewi@123` now login 200 (finance role = `accounting`). Full demo data seeded (rahaza sample, HR, maklon-full, marketing, seed-demo-full).


## 2026-07-02 (Session #17) — BACKLOG-A..E + RC-12 (keputusan produk: 1a, 2a, B/C/D/E ya, A=semua)

> Testing agent backend: **24/24 PASS**. Frontend testing di-skip atas instruksi user (sanity render mandiri: 5 hub OK tanpa Portal Error).

### RC-12 (1a) — `payroll_entries` phantom write DIHAPUS
- `marketing_livehost_analytics.py`: insert ke koleksi hantu `payroll_entries` (0 reader) dihapus; komisi/pembayaran host tetap dihitung & tampil di Livehost Analytics; notifikasi SSE reworded jujur ("Rekap difinalkan", bukan "dikirim ke Finance"); state machine shift (pending→calculated→synced_to_finance) dipertahankan.

### RC-12 (2a) — Orphan writes lain = AUDIT-TRAIL (didokumentasikan, TIDAK diubah)
- `wh_fg_movements` (opname2), `wh_rca_audit` (wms_audit), `rahaza_rework_close_log`, `dewi_universal_scans`, `cutting_outputs` (qc), `workspace_shares` → jejak audit sah, biarkan.
- `rahaza_maintenance_predictions` & `dewi_lms_attempts` → kandidat fitur pembaca di masa depan (keputusan 2a: tidak dibuat sekarang).
- `dewi_maklon_advance_payments`/`dewi_maklon_inventory` → dorman maklon (keputusan bisnis, biarkan).

### BACKLOG-B — `rahaza_shifts` KANONIK untuk modul HR Shifts
- `services/hr_shift_service.py` + `routes/hr_shifts.py` di-repoint dari `hr_shifts` (terisolasi) ke `rahaza_shifts` (coupling 10: attendance/APS/assignments) dgn **adapter dua-arah** `_to_hr_shape()`: shift_code←code, shift_name←name, effective_hours←working_hours, status←active(bool).
- Write menyimpan field kanonik + field HR ADDITIVE di dok yang sama; update me-mirror name/check_in_time/check_out_time/working_hours/active.
- **Guard penting**: `POST /seed-defaults` TIDAK lagi `delete_many({})` (dulu bisa MENGHAPUS shift kanonik yang dipakai absensi!) → idempotent by code.
- Verified: list = DEFAULT + OFF/S1/S2/S3 (+5 template bila di-seed, tanpa duplikat); CRUD test PASS; attendance regresi aman (94.9%).

### BACKLOG-C — Arsip backend CMT legacy
- 4 router dipindah ke `routes/_archive/`: `dewi_cmt.py`, `dewi_cmt_progress.py`, `dewi_cmt_seed.py`, `dewi_cmt_delivery_orders.py`; mount di server.py dihapus (komentar arsip).
- TETAP AKTIF: `dewi_cmt_lifecycle` (vendor portal — `cmt/vendor` dipakai VendorCMTPortalApp), `dewi_cmt_packing` (`/api/prod/cmt-receipts` dipakai ProductionDashboardOverview), `dewi_cmt_component_requests`.
- Verified: legacy 404 · phase7 `/api/dewi/reports/daily` 200 · lifecycle/packing 200 · startup bersih.

### BACKLOG-D — Onboarding kanonik ber-data
- Seed baru (blok 11b `production_seed_full.py` + insert langsung): 1 template `dewi_onboarding_templates` (DEFAULT_TASKS modul) + 3 checklists `dewi_onboarding_checklists` (1 completed, 2 active dgn progress). Modul `hr-onboarding` kini berisi.

### BACKLOG-E — Tailwind easing warnings (11×, 8 file) → 0
- `tailwind.config.js` `transitionTimingFunction`: `smooth-out` = cubic-bezier(0.16,1,0.3,1), `brand` = var(--ease-out); semua `ease-[...]` diganti `ease-smooth-out`/`ease-brand`. Dev-server 0 warning "is ambiguous".

### BACKLOG-A (SEMUA) — 15 modul → 5 HUB (T3.3/T3.4/T3.5/T3.6/T3.9)
- Komponen baru `erp/hubs/HubTabs.jsx` (generik; render hanya tab aktif; deep-link tab via sessionStorage `hub_tab_<hubId>`) + 5 hub:
  | Hub id | Isi tab | Menggantikan |
  |---|---|---|
  | `fin-journal-hub` | Jurnal Umum · Daftar Jurnal | fin-journal-entry, fin-journal-list |
  | `marketing-ai-hub` | Insights · Advanced · Content · Image | 4 modul marketing AI |
  | `hr-ai-hub` | Insights · Attrition · Skill Gap · Coaching · Actions | 5 modul HR AI |
  | `marketing-live-hub` | Live Sessions · Analytics · LiveHost | marketing-live, -live-analytics, -livehost |
  | `rnd-costing-hub` | Sample Costing · HPP Calculator | rnd-costing, rnd-hpp |
- `moduleRegistry.js`: 15 id lama → `makeRedirect(hub, tabKey)` (makeRedirect digeneralisasi menyimpan `hub_tab_<target>`); `portalNav.js`: 15 entri menu → 5; `App.js` `LEGACY_MODULE_TO_PORTAL` +16 mapping (deep-link id lama tetap bekerja; catatan: portal marketing = key `toko`).
- Sanity render (Playwright mandiri): 5 hub OK, redirect id lama OK, tab Analytics (RC-20) tanpa ErrorBoundary.

### RC-15 perluasan — Live Analytics projection
- `marketing_live_analytics.py` `_sessions_in_range` projection: `total_revenue←gmv`, `orders_count←total_orders`, `conversion_rate←cr_rate` (field lama tidak ada → semua endpoint analytics dulunya Rp 0). Verified: overview 90 hari = 18 sesi, Rp 190,9jt, 1806 orders.


## 2026-07-02 (Session #16) — EKSEKUSI PENUH SSOT MASTER REPAIR PLAN PART 1–4 (RC-01..RC-29)

> Urutan eksekusi: J.1 (RC-21 COA cascade) → semua fix seed [+SEED] → SATU re-seed → W-A..W-F → Wave I → Wave J. Backend testing agent: 27/29 PASS, 0 bug kritis. Dilewati (keputusan produk, jujur): RC-12/W-G orphan writes & BACKLOG-A..E.

### Fase A — Seed layer (satu re-seed setelah semua fix)
- **RC-21 (P0 fresh-deploy)**: fungsi baru `seed_coa_accounts(db)` di `rahaza_coa.py` (idempotent; SEED_TEMPLATE 4-digit + DA_COA_SEED 3-digit = 274 akun) → import `server.py:194` kini sukses; posting profiles 33 ikut ter-seed; cascade sembuh: re-seed production-full → **JE=51, journal_lines=108** (sebelumnya 0/0). `scripts/seed_expense_categories.py` → `rahaza_coa_accounts`.
- **RC-22 [+SEED]**: `production_seed_full.py` blok leave balances → schema kanonik `leave_type_id/allocated/used` (50 dok via lt_map, year 2026); reader `rahaza_leave_balances.py` diberi guard `.get()`. Endpoint 500→200.
- **RC-18 [+SEED]**: seed RnD kini menulis `dewi_rnd_sample_requests` (4, dengan style_id join by style_name, status map approved/submitted/draft) — bukan `dewi_rnd_samples` yatim; + masuk clear-list.
- **K1 [+SEED]**: tanggal `rahaza_overtime_requests` 2025-Q1 → periode seed 2026-05..07 via `_wd()`.
- **RC-06 [+LINKAGE]**: 6 akun login di-link `users.employee_id` → karyawan (admin→DA001, hr→DA003, finance→DA005, spv→DA007, gudang→DA015, maklon→DA023); `_get_my_employee` cek `employee_id` dulu. **16 endpoint 409 (K7) → 200.**

### W-A/W-B/W-D — Repoint misroute murni + absensi
- **RC-02** `dewi_executive_report.py`: `invoices`→`rahaza_ar_invoices` (issue_date/total/balance), expense→`rahaza_journal_lines` (account_type EXPENSE/COGS), `production_work_orders`→`rahaza_work_orders` (start_date/qty/completed_qty), `dewi_cmt_orders`→`dewi_maklon_pos` (po_date), `rahaza_qc_records`→`rahaza_qc_events` (checked/fail), attendance→events, `rahaza_overtime`→`rahaza_overtime_requests`, live fields gmv/total_orders + session_date string. Hasil Mei-2026: rev 80jt, exp 146jt, WO 8, att 94.9%, OT 4.5 jam, mkt 76jt (semua dulu 0).
- **RC-07** `dewi_management_tools.py`: users, rahaza_work_orders, rahaza_ar_invoices, events (izin/sakit), gmv/total_orders string-date; metrik okupansi rak DI-DROP jujur (wh_racks tak punya field okupansi).
- **RC-01** reader tersisa: `payroll_automation.py` (2 pipeline → events + **JOIN lembur nyata dari rahaza_overtime_requests per employee+periode**), `dewi_hr_ai.py` (status izin/sakit; is_late hanya bila field ada — jujur 0), `dashboard_routes.py`.
- **RC-10/RC-28b**: `employee_expense_gl_mapping.py` + `rahaza_admin.py:178` (plural) + `rahaza_budget.py` + `employee_expense_claims.py` → `rahaza_coa_accounts`/`rahaza_cash_accounts`.
- **RC-11**: variances→`rahaza_models` (code), control_tower→`rahaza_bundles`, phase7→`dewi_maklon_invoices`.
- **RC-14**: announcements→`rahaza_employees` ({id:...}, field name), unified_search→`rahaza_ar_invoices` (invoice_number/customer_name/issue_date), rahaza_shipments→`company_settings`.
- **RC-08**: cashflow AI → `rahaza_cash_movements` by direction (in/out 60 hari) — angka nyata masuk analisis LLM.

### W-C — GL Integrity (RC-05 + RC-13)
- 3 blok `rahaza_journals.insert_one` manual (expense disburse, travel advance, travel settlement) → **engine `_create_posted_je`** (validasi COA/saldo/periode, mirror journal_lines, source_module expense_claim/travel_advance/travel_settlement). Default akun benar: Dr 6-3500/6-3400/1-1610, Cr 1-1101; bank → `rahaza_cash_accounts` (gl_account_code||code). 
- **RC-13**: 3 notifikasi `dewi_notifications` → `notif_insert()` (koleksi kanonik `notifications`, meta.target_roles).

### W-E — Dashboard (RC-03 + RC-04, RC-DASH-DECISION dieksekusi)
- Attendance today → events distinct employee (cap 100%); OEE → reuse `_compute_oee` engine `rahaza_oee.py` (None jujur bila tak ada downtime data); pengiriman → `wh_delivery_notes` (pending=draft/issued; total=issued/received); output bulanan & weekly throughput → `rahaza_wip_events` event_type='output' by event_date; lead-time vendor → `warehouse_receiving` JOIN `rahaza_purchase_orders.po_date` by po_number; defect vendor → `rahaza_grn_inspections`; product completion & deadline dist → `rahaza_work_orders`. `/api/dashboard/analytics` hidup total (dulu mati semua).

### W-F — RC-09 AR-360
- Jalur standalone `rahaza_ar_payments` (seed-only, duplikat) DIHAPUS → pembayaran dari `rahaza_cash_movements` (category ar_payment/ar_receipt, ref match id/'ar:'+ref/invoice_number) — no double-count; embedded payments tetap.

### Wave I — RC-15/16/17
- **RC-15**: live/summary field gmv/total_orders/peak_viewers/cr_rate + guard None (500→200; 24 sesi, 258,5jt). engagement_rate tak punya SSOT → 0 jujur.
- **RC-16**: kol-leaderboard `marketing_live_sessions`→`marketing_creator_sessions`, group creator_id/creator_name, date STRING range; endpoint `/{kol_id}/detail` (bug pola sama) ikut diperbaiki. 0→5 kreator.
- **RC-17**: capacity `production_work_orders`→`rahaza_work_orders` (peta qty/wo_number/model_name/target_date||due_date + status rahaza); **akar lapis-2**: `_recent_daily_output` pakai `created_at` yang TIDAK ADA di wip_events → `event_date`. Utilization 7 hari data nyata.

### Wave J — RC-19/20/23/24/25/26/27/28/29
- **RC-19**: label-pdf `s['location']`→`location_id` + resolve label via `wh_positions` (single & batch) → 200.
- **RC-20 (FE)**: `LiveSessionAnalyticsDashboard.jsx` SelectItem value=""→"all" + filter logic (ErrorBoundary hilang).
- **RC-23**: normalisasi tz naive→UTC di export outstanding-advances (500→200); **FE 3 modul** (settlement/travel/claims) export `window.open`+toast-palsu → fetch-blob + toast jujur by response.ok.
- **RC-22 (FE)**: `HRLeaveBalancesModule` banner error nyata (loadError state) — tak lagi menelan 500 jadi empty-state menyesatkan.
- **RC-24**: bundles-summary `_id.get('pcode')` fallback '-' → 200.
- **RC-25**: acc dashboard → `dewi_accessory_requests` (request_type internal_issuance, pending=submitted/allocated); `acc_loans`/`acc_purchase_requests` TIDAK disentuh (self-consistent).
- **RC-26**: bank recon auto-match `gl_entries`→`rahaza_journal_entries` (status posted; amount=total_debit; desc=memo+je_number; flag is_matched/matched_txn_id additive ke JE).
- **RC-27**: portal KPI `dewi_kpi_submissions`→`da_kpi_submissions` (filter evaluatee_id+submitted; skor avg_score||section_score dinormalisasi ×20 bila skala 1-5; grade via `_grade()`; period=period_id). Hasil: score 80 grade B.
- **RC-28**: `services/ai_aggregates/finance_aggregates.py` (ar_invoices issue_date; payment_count→cash_movements in) + `production_aggregates.py` (rahaza_work_orders + peta field, output kompatibel); `workspace.py:496`→`dewi_procurement_requests`; `dewi_cmt_lifecycle.py`→`wh_cmt_dispatches` (by cmt_name; status dispatched/partially_returned).
- **RC-29**: mount ganda `dewi_portal_saya_hr_router` tanpa prefix DIHAPUS dari server.py — 12 path bare hilang; localhost:8001/dashboard → 404.

### Verifikasi
- Backend testing agent: **27/29 PASS** (2 sisanya isu script test/ingress, bukan bug). Semua crash 500 → 200; exec/dashboard/digest berisi angka nyata; 409 linkage hilang; regresi smoke lulus.
- Frontend: webpack compiled successfully (UI testing menunggu izin user).


## 2026-07-02 (Session #12) — Linting Cleanup (Phase A) + Cleanup Wave 3

### Phase A — Zero-lint compliance (Ruff backend + ESLint frontend)
- **Ruff 52 → 0**: auto-fix F401 (38 unused import) + F541 (5 f-string); manual E402×5 (`# noqa: E402` import emergentintegrations di 5 rahaza_auto_attendance_*), E712×2 (`== True`→`is True`), F841×2 (hapus blok data mati `kpi_actuals`/`tasks_data` sisa O1.3 di `production_seed_full.py`).
- **ESLint 13 → 0** (react-hooks/exhaustive-deps): auth headers dibungkus `useMemo` (Capacity, Executive, PayrollDashboard, LiveSessionAnalytics, MarketingWebhooks, RahazaARInvoices, RahazaPayrollRun, HRShiftManagement, ProcurementRequest); `PettyCashModule.fetchFunds` → functional `setActiveFund` (deps `[]`). Tidak ada perubahan logika bisnis/API.
- Verified: backend health 200, production build "Compiled successfully" 0 warning, smoke render AR (data nyata) + Kas Kecil (empty-state benar) tanpa infinite render.
- Pra-eksisting (ditunda): ~11 warning tailwind `ease-[...]` ambiguous (dev-server only, tak muncul di build).

### Wave 3 — Drop 3 koleksi 100% dead (Tier 1 CLEANUP_MASTER_PLAN)
- `rahaza_onboarding_checklists` (1, seed-only) — modul `hr-onboarding` baca KANONIK `dewi_onboarding_checklists` (`dewi_onboarding.py`); seed insert dinonaktifkan + drop.
- `accessory_inspections` + `accessory_defects` (0) — route DEPRECATED-NOOP (GET→[], POST→410, tak sentuh koleksi); index scaffolding di `server.py` dihapus + drop.
- DB 256→253; restart ×2 → tidak di-recreate (fix permanen); kanonik utuh.
- **testing_agent iteration_26**: Backend 100% (20/20 — login 6 role, RBAC, onboarding 200, accessory GET 200 []/POST 410, health). 0 critical bug.

### Wave 4 — Dedup menu (Tier 3, redirect reversibel)
- **Verifikasi coverage ketat**: dari 4 kandidat, hanya **T3.1 opname** yang benar-benar duplikat. T3.2 (approval-hub = agregator yang routing ke hr-inbox/approval-multilevel), T3.7 (kreator = komponen sama untuk 2 audiens portal), T3.8 (maklon-notifications = cross-portal reuse) → **SKIP** (bukan duplikat; menghapus akan merusak fungsi/akses).
- **T3.1 dieksekusi**: menu `wh-opname` ("Stok Opname", `/api/wms/legacy/opname` DEPRECATED) dihapus dari sidebar Gudang; kanonik `wms-opname-enhanced` (RESMI, `/api/wms/opname2` SSOT, superset: cycle count/scan/submit/approve/variance/PDF). `moduleRegistry`: `wh-opname` → `makeRedirect('wms-opname-enhanced')`; import `OpnameModule` di-comment (jaga 0 warning).
- Scan konfirmasi 0 menu id kembar intra-portal. Build "Compiled successfully" 0 warning.
- **testing_agent iteration_27**: Backend 100% (3/3 — health, /api/wms/opname2, /stats), code review 100%, 0 bug. Verifikasi visual: legacy menu hilang, RESMI ada & render sesi opname nyata.

### Wave T2.1 — Migrasi Pinjaman Legacy → Kasbon kanonik (Tier 2)
- **Migrasi data:** 3 record `rahaza_employee_loans` (PIN/2026/001-003, outstanding total Rp 26.166.668) → `dewi_kasbon_requests` (type=pinjaman, status=disbursed) via skrip idempoten `backend/migrations/t2_1_migrate_employee_loans_to_kasbon.py` (backup JSON di `/app/backups/`). Verified GL-safe (0 referensi jurnal). Koleksi legacy diarsip (tidak di-drop) → reversible.
- **Menu dedup:** `hr-employee-loans` ("Pinjaman Karyawan (Legacy)") dihapus dari sidebar HR; `moduleRegistry` → `makeRedirect('hr-kasbon')`; import EmployeeLoansModule di-comment.
- **BUG FIX (pra-eksisting, terekspos migrasi):** `GET /api/dewi/kasbon/stats` return 500 (data seed simpan `created_at` sebagai datetime, endpoint slice `[:7]`) → diperbaiki helper `_ym()` robust (str & datetime). Kini 200, `total_outstanding` Rp 26.166.668.
- **testing_agent iteration_28**: Backend 100% (53/53) — stats/requests/deductions benar, 0 bug. UI: menu Legacy hilang, 3 pinjaman tampil di modul kanonik, kartu outstanding benar. (2 catatan frontend = artefak otomasi Playwright, bukan bug.)



## 2026-06-08 (lanjutan 2) — P1 P2P Procurement full cycle + P2 Multi-user role (Iteration 22)

### P1 — P2P Procurement (PR→PO→GR→AP→bayar) end-to-end
- **E2E test penuh** `tests/test_p2p_full_cycle.py`: PR create→submit→approve×3→create-PO→PO submit→approve→create-GR→receive GR→AP invoice from GR→pembayaran→3-Way Match = `matched`. PASS.
- **3 bug nyata diperbaiki:**
  1. **Counter SSOT bentrok**: nomor GR (`gr_number`) & AP (`ap_invoice_{yymm}`) yang di-seed langsung bentrok dgn nomor yang dibuat app (unique index) → `create-gr`/AP 500. Fix: seed mensinkronkan `db.counters` (`$max` seq) setelah insert.
  2. **Propagasi qty GR→PO gagal untuk PO turunan PR** (item free-form tanpa `material_id`): `warehouse.py` hanya meneruskan item ber-`material_id`, dan `rahaza_po.update_po_received_qty` me-`it["material_id"]` (KeyError). Fix: teruskan & cocokkan via `po_item_id` (fallback `material_id`). PO kini jadi `fully_received`.
  3. **3-Way Match selalu "over"**: membandingkan total invoice (termasuk PPN 11%) vs nilai barang diterima (tanpa PPN). Fix `rahaza_ap_from_gr.py`: bandingkan **subtotal pra-pajak** (display tetap total termasuk pajak).
- **Seed data terhubung** (`production_seed_full.py` Section 53): 6 rantai PR→PO→GR→AP→bayar di berbagai tahap (PR menunggu approval, PO disetujui, GR diterima, AP belum bayar `sent`, AP lunas `paid`, AP `partial_paid`). Dashboard Procurement (PR), 3-Way Match, & AP Aging kini terisi data nyata yang nyambung.
- **AP Aging fix**: invoice belum bayar di-set status `sent` (bukan `approved`) agar muncul di `/api/rahaza/ap-aging` (filter sent/partial_paid). Outstanding ~Rp 18,1jt tampil.

### P2 — Multi-user role / portal separation
- **5 user role** di-seed idempoten (Section 54): hr/finance/spv/gudang/maklon @dewiaditya.id, password `Dewi@123` (pakai `hash_password` dari auth.py, upsert by email).
- **Backend `PORTAL_ACCESS`/`get_user_portals`/`check_portal_access`** (`shared.py`) ditulis ulang agar konsisten dgn frontend (id portal benar: toko/maklon/hr/assets/dll; SUPER_ROLES & ALL_ROLE_PORTALS). Login & `/auth/me` kini mengembalikan field `portals`.
- **Frontend deep-link guard**: modul bersama `portalAccess.js` (`canAccessPortal`). `App.js` menjaga akses di handleLogin, session-restore, hashchange, handleSelectPortal & handlePortalChange. `PortalSelector.jsx` pakai helper yang sama (satu sumber kebenaran). User tanpa akses yang membuka `?portal=...` lain → dialihkan ke Portal Selector (tanpa kebocoran konten).
- Tests: `tests/test_rbac_multiuser.py` (7 pass), `tests/test_p2p_full_cycle.py` (pass). testing_agent iteration_22: role separation 5/5, deep-link guard 3/3, P2P dashboards render.


## 2026-06-08 (lanjutan) — Portal GUDANG, MAKLON & MARKETING: audit + seed enrichment (Iteration 21)
Audit rigor lanjutan (Gudang → Maklon → Marketing): GET-sweep tiap endpoint, buka tiap modul, perbaiki tabel kosong / crash / "Rp 0" / nama klien kosong. Frontend 26/26 modul render tanpa crash (testing_agent iteration_21, 100% render). Periode dinamis April–Juni 2026.

### GUDANG/WMS — blok enrichment baru (production_seed_full.py "Section 50")
- **Bridge legacy** `/api/wms/legacy/*` baca `warehouse_locations/stock/movements/putaway/receiving` → di-seed: 8 lokasi bin, 19 stok (material+FG), put-away, 8 GRN (GR-00001..8, status received/accepted/draft/partial).
- **GRN QC / Supplier Scorecard**: `rahaza_grn_inspections` (7 inspeksi) dari GRN.
- **Stok & Pergerakan kanonik**: `rahaza_material_stock` (20) + `rahaza_material_movements` (37) → Movement Ledger terisi.
- **Struktur WMS Scanner**: `wh_buildings`(1)/`wh_zones`(3)/`wh_racks`(6)/`wh_positions`(36, barcode WH1-A-R01-S01-P01) sebagian occupied.
- **Fabric Roll Tracking** `wh_fabric_rolls` (12 roll + movements), **Dispatch CMT** `wh_cmt_dispatches` (5), **Surat Jalan** `wh_delivery_notes` (8), **Opname** `wh_opname_sessions2` (3).
- **Fulfillment**: FG stock `rahaza_material_stock` shape (ownership=cv_da, inventory_category=fg_internal, available_quantity) untuk tab Allocate; `marketing_orders` diberi `fulfillment_status` (via seed_orders_if_empty) → antrian Pending/Allocated/Picking/Packed/Dispatched terisi.
- **Retur Gudang** `wh_returns` (6, status Pending/Received/Inspected/Resolved).

### MAKLON — blok enrichment baru ("Section 51") + bugfix
- **BUG nama klien kosong**: seed isi `company_name` tapi app baca `name` → diperbaiki (clients diberi field `name`). Order Terbaru kini menampilkan PT. Maju Busana Indonesia / CV. Selaras Fashion / PT. Garmen Nusantara.
- **dewi_maklon_pos** (SSOT yang dibaca dashboard, sebelumnya seed nulis `dewi_maklon_orders`) → 6 PO realistis + buyer_catalog(6), dispatches(5), samples(6), invoices(3)+payments(3), qc_checks(12). Total Revenue & Nilai Order tidak lagi Rp 0.

### MARKETING — blok enrichment baru ("Section 52") + bugfix
- **BUG KOL Leaderboard 500**: `marketing_kol_ops.py` akses `creator['creator_code']`/`['name']` → KeyError. Diperbaiki pakai `.get()`. Seed KOL creators (Section 38) di-rewrite ke skema kanonik (creator_code, name, platforms, kpi_targets) + `marketing_creator_sessions` (45) → leaderboard render 5 creator.
- **BUG LiveHost kosong (salah nama collection)**: seed nulis `marketing_livehost_hosts` tapi API baca `marketing_livehosts`. Section 36 di-rewrite → `marketing_livehosts`(4) + `marketing_livehost_shifts`(48) untuk analytics host-performance.
- **marketing_platform_accounts**(5) + **marketing_account_targets**(5).
- **BUG Target Bulanan "Rp 0" actual**: `/targets/monthly-summary` baca `marketing_sales_data` (revenue_type=total) yang kosong → seed `marketing_sales_data` (135 baris, 5 akun × 3 bln × 9 hari). Actual kini Rp 231.385.713 (51,4%) + per-akun.

### Verifikasi
- testing_agent iteration_21: 26/26 modul render tanpa crash; 4 regresi (Maklon client name, KOL leaderboard 500, LiveHost collection, Fulfillment queue) FIXED & verified.
- Self-test screenshot: wh-stock, wh-receiving, maklon-dashboard, marketing-kol, fulfillment, marketing-targets semua terisi.


## 2026-06-08 (lanjutan) — Portal KEUANGAN & PRODUKSI: isi modul kosong + jurnal seimbang (Iteration 20)
Audit rigor app-wide: GET-sweep semua endpoint → temukan 63 modul "kosong" (200 tapi 0 baris) akibat mismatch nama collection seed↔API + domain belum di-seed.

### KEUANGAN — blok enrichment baru (production_seed_full.py "29b")
- **Daftar Jurnal kosong**: API baca `rahaza_journal_entries`, seed tulis `rahaza_journals` → dibuat generator `post_je()` (double-entry seimbang) + mirror `rahaza_journal_lines`. JE untuk: saldo awal/modal, AR (revenue routing per channel), AR payment, AP, payroll, beban operasional, penyusutan. 51 JE.
- **Anggaran**: API baca `rahaza_budgets`+`rahaza_budget_items`, seed tulis `rahaza_budget_entries` → seed header+item benar (3 anggaran).
- **Pusat Biaya**: tak di-seed → 6 cost center.
- **Pengeluaran**: `rahaza_expenses` kosong → 12 beban operasional + 30 cash movements (`rahaza_cash_movements`).
- **Saldo awal/Modal**: tambah JE modal disetor agar kas positif & Neraca realistis.
- **payroll_automation.py**: YTD filter pakai `period_from` (string), status finalized OR paid.
- Verified: Neraca Saldo SEIMBANG, Neraca (Balance Sheet) BALANCED (~Rp 807jt), Laba Rugi terisi.

### PRODUKSI — blok enrichment baru ("29c")
- Domain produksi sebelumnya data leftover (WO tanpa model/qty, material TEST junk).
- Seed: 5 Lini Produksi, 8 material realistis, 12 Work Order (anchor + model + qty + status), 45 Bundle, 100 Line Assignment (24 hari kerja), 500 WIP event (output/qc_pass/qc_fail → OEE), 28 QC event, 12 Material Issue, 10 Shift Handover.
- Verified: OEE dashboard, line-assignments, bundles, material issues semua terisi.

### Frontend fixes (response-shape & lint)
- HREmployeeModule efek di-refactor ke async-IIFE (hapus set-state-in-effect tanpa disable yang memecah CRA).
- ProductionDashboardOverview: `<span>` di `<option>` (pakai template literal), efek pakai setTimeout, empty catch diberi komentar.
- HR Edit dialog: tambah DialogDescription (a11y).

### Verifikasi (testing agent iteration 20 — RENDER BROWSER)
- SDM, Keuangan, Produksi: SEMUA PASS render frontend, no Portal Error, data terisi (bukan Rp 0). retest_needed=false.

### Sisa (belum dikerjakan)
- Portal GUDANG (WMS): GRN/receiving, fabric rolls, delivery notes, CMT dispatches, returns, opname masih kosong (domain kompleks).
- Portal MAKLON: seluruh modul CMT (partners, jobs, deliveries, invoices, QC, samples) kosong.
- Portal TOKO/MARKETING: products, variants, buyers, flashsales, pack-batches kosong.
- P2P Procurement (PR) kosong.


Context: User melaporkan banyak bug nyata saat navigasi manual (testing sebelumnya beri "sukses" palsu karena HANYA cek status API GET, tidak pernah render frontend / uji alur create). Semua di bawah ini DIVERIFIKASI di browser nyata.

### Akar masalah sistemik yang ditemukan & diperbaiki
1. **Frontend crash "X is not defined"** (kelas bug): komponen dipakai tanpa di-import.
   - `HREmployeeModule.jsx` (menu Data Karyawan) → `Tabs/TabsList/TabsTrigger/TabsContent` tidak di-import → "Portal Error: Tabs is not defined". FIXED.
   - `WMSModule.jsx` & `RahazaMaterialIssueModule.jsx` → `ScanLine` (lucide) tidak di-import. FIXED.
   - Dibuat script audit statis `/app/scripts/find_undefined_jsx.py` untuk menyapu kelas bug ini di seluruh codebase.
2. **Backend 500 saat Buat Announcement**: `created_by = current_user.get("employee_id")` = None (superadmin tak terhubung employee) melanggar `AnnouncementResponse`. Fix: fallback `employee_id|id|email|"system"` + field model jadi Optional. Verified HTTP 201.
3. **Frontend salah baca bentuk respons `{items}`** (kelas bug "data tidak sinkron"): API `/api/rahaza/employees` balas `{total,items,...}` tapi ~11 modul baca sebagai array / `.rows` → tabel kosong. Dinormalisasi baca `.items` di: HREmployee, RahazaEmployees, HRKPI, RahazaOvertime, HR360Feedback, UserManagement, RahazaPayrollProfiles, RahazaAutoAttendance, LKPDialog, RahazaLeave, RahazaLineAssignments, OperatorView.

### Seed (production_seed_full.py) — rebuild schema + anchoring tanggal
- **Employees**: ditulis ulang ke skema kanonik penuh (job_title, ktp_number 16-digit, npwp_number, tax_ptkp, bpjs_*_number, bank_account_number/holder, contract_type/dates, data personal & kontak darurat lengkap). Sebelumnya field salah (position/bpjs_kesehatan/npwp) → UI tampil kosong.
- **Payroll Profiles**: skema kanonik (pay_scheme=monthly, period_type, cutoff_config, base_rate, overtime_rate). Sebelumnya hanya `base_salary` → UI "Tarif Dasar Rp 0". Kini Tarif Dasar Rp 8.000.000 dst.
- **Anchoring tanggal DINAMIS**: helper `PERIOD/_sd/_sdt/_wd/_remap/_sd_ext` memetakan data deret-waktu ke 3 bulan terakhir s/d bulan berjalan (April–Juni 2026). Semua `_ds/_dt(2025,...)` diganti. Payroll runs dapat `period_from/period_to`. Dashboard "bulan ini/YTD" kini terisi.
- **Payroll dashboard YTD** (payroll_automation.py): filter pakai `period_from` (string) bukan `created_at` (Date vs string → 0 match), dan status `finalized` OR `paid`. Disbursed YTD kini Rp 356.367.000.

### Absensi Harian (RahazaAttendanceModule.jsx) — UX & validasi
- Auto-isi shift default + 8 jam saat status → "Hadir"; kosongkan jam/lembur saat tidak hadir.
- Validasi sebelum simpan: blok jika ada status "Hadir" tanpa shift/jam (+toast jelas).
- Tombol "Tandai Hadir & Simpan" auto-isi lalu simpan langsung. Grid menampilkan jam kerja 8.0 dari seed (sebelumnya 0).

### Verifikasi (browser nyata)
- Data Karyawan: 25 karyawan tampil lengkap (jabatan, kontrak PKWTT/PKWT, kontak), dialog Edit 5 tab + field Pajak/BPJS/Bank terisi, 0 Portal Error.
- Profil Gaji: Tarif Dasar Rp 8.000.000 dst (0 occurrence "Rp 0"), Tarif Lembur terisi.
- Payroll Dashboard: Disbursed YTD Rp 356jt, run April/Mei/Juni 2026 (paid), periode terisi.
- Seed: status success, 0 errors, periode "April 2026 — Juni 2026".


## 2026-06-08 — Phase 15d: KPI Final Score + Travel Settlement GL Posted

### Bug Fixes
- **KPI `kpi_final: null`**: Root cause ada 3 komponen yang None:
  - `da_kpi_perform` kosong → ditambahkan seed 25 perform docs (4 KPI items per karyawan, weighted score 0-100)
  - `absensi_score: null` → KPI periode tidak punya `period_from/period_to/working_days` → ditambahkan ke seed period
  - Kini `kpi_final` terisi untuk semua karyawan (contoh: DA001=84.91, grade=B) ✅
- **Travel settlement `pending_post: 24`**: Settlement di-seed ulang langsung sebagai `status: 'posted'` + insert JE ke `rahaza_journals`. Kini `pending_post: 0`, 8 settlement GL-posted ✅

### Data Added
- `da_kpi_perform`: 25 records (perform_score + 4 KPI items per karyawan)
- `rahaza_journals`: 8 JE baru untuk travel settlements (Dr Biaya Dinas / Cr Uang Muka)


### Bug Fixes
- **KPI calculate "Tidak ada karyawan"**: Ditambahkan `participant_employee_ids` (25 karyawan) ke `da_kpi_periods`
- **KPI calculate `KeyError: eval_type`**: Questions di seed sekarang memiliki field `eval_type`, `order`, `category_weight`
- **KPI calculate `KeyError: category_weight`**: Field `category_weight` ditambahkan ke semua questions dengan bobot benar (self/peer/supervisor)
- **KPI submissions status**: Ditambahkan `status: "submitted"` agar `_calc_attitude_score` bisa menemukan submission

### Data Added
- **Per Diem Rates**: 3 rate (dalam kota Rp100k/hari, luar kota Rp300k/hari, luar negeri Rp700k/hari)
- **Travel Requests**: 10 perjalanan dinas dari 6 karyawan (Jan-Mar 2025), berbagai status (completed/advance_paid/approved)
- **Travel Settlements**: 8 settlement completed dengan nominal aktual realistis (total Rp23.8M)
- **KPI Submissions**: Self + supervisor assessment per karyawan (50 submissions total)
- **KPI Results**: 25 hasil dengan attitude_score, perform_score, grade


### Bug Fixes
- **KPI period_id slash routing**: Format period_id diubah dari `KPI/2025/Q1` → `KPI-2025-Q1` (menghilangkan slash yang merusak URL path routing). Semua endpoint `/results/{period_id}`, `/calculate`, `/publish` kini bekerja.
- **Payslips employee_code filter**: `GET /api/rahaza/payslips` kini support query param `?employee_code=DA001` selain UUID. Field `employee_code: Optional[str]` ditambahkan ke `list_payslips` endpoint.
- **Seed re-run**: Status `success`, 0 errors dengan period_id baru


### Bug Fixes
- **Attendance mismatch**: Seed sekarang insert ke `rahaza_attendance_events` (yang dibaca API) + `rahaza_attendance` (untuk payroll). Total: 1600 records di kedua collection.
- **URL endpoint salah** di `RahazaPayrollAllowancesModule.jsx`: `/api/rahaza/master/employees` → `/api/rahaza/employees` (fix "body stream already read" error)
- **Employees response key** di Tunjangan Tetap: Tambah `d2.items` sebagai key prioritas pertama
- **Employee Loans**: Status `approved` → `active`, tambah field `loan_number`, `loan_amount`, `outstanding_balance`, `disbursement_date`
- **Payroll Dashboard**: Tambah field `total_net_pay` dan `finalized_at` ke payroll runs (dipakai oleh automation dashboard)

### Data Added
- **Org Structure**: 12 `dewi_org_units` (company → division → department) + 10 `dewi_org_positions`
- **KPI Assessment**: 1 periode (Q1 2025, status closed), 8 pertanyaan, 25 hasil assessment karyawan
- Seed sekarang berjalan **100% sukses (0 errors)** dengan semua 46 collection terisi


### Features Implemented
- **Export Excel Payroll** (`GET /api/rahaza/payroll-runs/{id}/export-excel`):
  - 3 sheet: Rekapitulasi (25 karyawan, format perusahaan), Slip Individual (per karyawan), Data Transfer Bank
  - Formatting: header berwarna navy, alternating rows, total row, tanda tangan
  - Tombol "Export Excel" (hijau) di list run dan di detail view
- **AR Invoice Channel Routing E2E VERIFIED**:
  - Test: Shopee invoice Rp 890.000 → auto-GL `JE-20250315-0001`
  - Debit: `1-220` Piutang Platform Online Shop ✅
  - Credit: `4-111` Penjualan – Shopee Grosirhijabsragen ✅ (balanced)
- **ESLint fix RahazaPayrollRunModule.jsx**: Refactor ke `useReducer + tick` pattern



### Features Implemented
- **Production Seed** (`POST /api/seed/production-full`): Master seed script 1600+ baris
  - 25 karyawan realistis (DA001–DA025) dengan profil lengkap
  - 1600 records absensi (3 bulan), 75 payslip, 3 payroll runs
  - 15 AR Invoice multi-channel (Shopee, TikTok, Tokopedia, Maklon)
  - 8 AP Invoice, 9 petty cash, 4 bank transfers, 42 budget entries
  - 15 fixed assets + 45 depreciation, 63 LMS enrollments, 30 KPI results
  - 24 live sessions, 4 ads campaigns, 5 KOL creators, 240 online orders
  - 4 maklon orders, 4 R&D samples, 10 tasks, 5 announcements
- **AR Invoice Channel Routing**: ESLint fix di `RahazaARInvoicesModule.jsx` dengan `useReducer` pattern


1. **CoA CV. Dewi Aditya di-import ke Database (177 akun)**:
   - `POST /api/rahaza/coa/seed-da` — seed 177 akun CoA format 3-digit (1-xxx)
   - Semua segmen: Aktiva Lancar (bank, kasbon, piutang, persediaan), Aktiva Tetap, Kewajiban (termasuk BPJS baru), Ekuitas, Pendapatan (per platform OS + Maklon), HPP, Biaya OS/Maklon/Produksi/GA
   - 3 akun baru yang sebelumnya missing: `2-122 Hutang BPJS Kesehatan`, `2-123 Hutang BPJS Ketenagakerjaan`, `5-231 Biaya Vendor CMT – Jahit`

2. **38 Posting Profiles diremap ke CoA DA**:
   - `POST /api/rahaza/posting-profiles/seed-da` — update 33 existing + insert 5 baru
   - Semua auto-jurnal kini menggunakan kode akun DA (1-110, 1-131, 2-120, dll.)
   - Profil baru: `ar_invoice_os`, `bpjs_ketenagakerjaan_payment`, `employee_loan_repayment_manual`, `variance_overproduction`, `variance_underproduction`

3. **Kasbon Auto-GL Posting** (`dewi_kasbon.py`):
   - `finance_disburse` → otomatis buat JE: Dr `1-120 Kasbon Karyawan` / Cr `1-131 Bank BCA`
   - `record_repayment` (manual) → Dr `1-131 Bank` / Cr `1-120 Kasbon`
   - `record_repayment` (payroll_deduction) → Dr `2-120 Hutang Gaji` / Cr `1-120 Kasbon`
   - `apply_payroll_deductions` → per karyawan, Dr `2-120` / Cr `1-120` otomatis
   - Graceful: jika CoA belum ada, error disimpan tanpa crash

### Coverage Auto-Jurnal (38/38 event types aktif):
- AR/AP Invoice, Payment, Credit Note → KLOP
- Payroll Finalize + Payment + PPh21 + BPJS (Kesehatan & Ketenagakerjaan) → KLOP
- Inventory (Receive, Issue, Adjust, Scrap, WIP→FG, COGS) → KLOP
- Fixed Assets (Acquisition, Disposal, Depreciation) → KLOP
- Bank (Transfer, Recon Charge/Interest/Fee) → KLOP
- Kas Kecil (Expense + Replenish) → KLOP
- Maklon (AR Invoice, DP, CMT AP) → KLOP
- Kasbon & Pinjaman (Cair, Angsuran Payroll, Angsuran Manual) → KLOP
- Variance Over/Under → KLOP



### Features Implemented
1. **Backend — dewi_kasbon.py (Lengkap)**:
   - `POST /api/dewi/kasbon/requests` — Staff ajukan kasbon/pinjaman + upload dokumen (base64)
   - `GET /api/dewi/kasbon/requests` & `/my-requests` — List all (HR/Finance) atau milik sendiri
   - `PATCH /api/dewi/kasbon/requests/{id}/hr-review` — HR approve/reject dengan catatan
   - `PATCH /api/dewi/kasbon/requests/{id}/disburse` — Finance cairkan + set tanggal mulai potong
   - `POST /api/dewi/kasbon/requests/{id}/repay` — Catat pembayaran manual/payroll
   - `GET /api/dewi/kasbon/stats` — Dashboard statistik (pending, aktif, outstanding)
   - Router terdaftar di `server.py` + DB indexes dibuat di startup
   - Bug fix: tambahkan `from fastapi import Request` + type annotation `request: Request` di 6 handler

2. **Backend — Payroll Auto-Deduction (rahaza_payroll_shared.py)**:
   - `_compute_payslip_for_employee` otomatis ambil kasbon/pinjaman aktif per karyawan per periode
   - Deducted dari `net_pay` saat payslip dibuat

3. **Frontend — KasbonStaffModule.jsx (Portal Saya)**:
   - Staff lihat pengajuan dengan tabs (Semua/Menunggu/Aktif/Selesai)
   - Form ajukan: pilih jenis (Kasbon/Pinjaman), jumlah, keperluan, cicilan (1-12x), upload dokumen
   - Progress bar pelunasan + riwayat pembayaran

4. **Frontend — HRKasbonModule.jsx (Portal SDM)**:
   - Statistik 4 kartu: Menunggu Review, Menunggu Cairkan, Outstanding, Bulan Ini
   - Review modal: tombol Setujui/Tolak + catatan HR
   - Tombol "Muat Demo" untuk seed data

5. **Frontend — FinanceKasbonModule.jsx (Portal Keuangan)**:
   - Tabs: Siap Cairkan / Aktif / Selesai / Semua
   - Modal pencairan: set tanggal cair + periode mulai potong gaji
   - Modal catat pembayaran: payroll_deduction atau manual

6. **Registrasi Navigasi**:
   - `moduleRegistry.js`: lazy imports + mapping `portal-kasbon`, `hr-kasbon`, `fin-kasbon`
   - `portalNav.js`: "Kasbon & Pinjaman" di Portal Saya (BARU), Portal SDM (BARU), Portal Keuangan (BARU)

## 2026-06-09 — Mock Email Notifications, E2E Hired→Onboarding, Template Deadline Edit (Iteration 16)

### Features Implemented
1. **Mock Email Notifications (ATS)**:
   - Backend: 6 template email otomatis tersimpan di `candidate.email_logs` saat stage berubah (Screening CV, Interview HR, Interview User, Offering, Hired, Rejected)
   - StageActionModal: tampil notice biru "Email notifikasi akan dikirim ke [email]" + badge MOCK sebelum konfirmasi
   - CandidateDetailModal: tab baru "Email" (dengan badge count) — tampil MOCK banner + riwayat email lengkap (subject, body, timestamp)

2. **Template Builder — Inline Edit Deadline & PIC**:
   - TemplateTaskRow: hover tampilkan ikon pensil untuk edit inline
   - Edit form: field "Deadline (Hari ke-)" + "PIC / Penanggung Jawab"
   - Perubahan disimpan bersama saat klik "Simpan Perubahan"

3. **E2E Verified**: Candidate → Hired (dengan job_id) → auto-create employee + onboarding checklist. `onboarding_checklist_id` tersimpan di candidate doc.


Context: User requested major improvements to Rekrutmen (ATS) and Onboarding modules.

### Features Implemented
1. **HRATSModule.jsx — Complete Rewrite (ATS)**:
   - Actionable pipeline kanban (7 stages: Lamaran Masuk → Hired/Rejected)
   - Stage transition modals: Screening CV (notes), Interview HR/User (schedule + interviewer + mode), Offering (salary + contract + start date), Hired (auto-onboarding), Rejected (reason)
   - CV upload: support base64 file upload (PDF max 5MB) + URL link
   - Interview scheduling + scoring (mark result, 1-100 score, pass/fail/hold)
   - Talent Pool toggle per candidate
   - Candidate detail with 5 tabs: Info, CV & Dokumen, Wawancara, Penawaran, Catatan
   - Auto-create employee + onboarding checklist on "Hired"
   - Analytics tab with pipeline breakdown chart
   - 12 ESLint errors fixed (empty catch blocks + unescaped entities)

2. **HROnboardingModule.jsx — Task-Based Checklist Enhancement**:
   - Per-employee onboarding checklists (created automatically when candidate is Hired)
   - Custom activities: AddTaskModal with **PIC/Penanggung Jawab** field + **Deadline (Tanggal)** date picker
   - Task deadline displayed per task item (shows red if overdue)
   - Template Builder: full CRUD with task editor (add/delete tasks by category + day + PIC)
   - Task completion with notes, undo completion
   - Status management: pause/resume checklist
   - 3 ESLint errors fixed

3. **Bug Fix — dewi_onboarding.py seed (MEDIUM)**:
   - Line 467: changed `{'status': 'aktif'}` → `{'active': True}` to match employee schema
   - Onboarding "Muat Demo" now correctly seeds sample checklists

## 2026-06-08 — HR Portal Bug Fixes (Iteration 14)
Context: User reported multiple HR portal bugs — tab navigation redirecting, body stream errors, failed announcements, payroll display inconsistency.

### Bugs Fixed
1. **Tab Navigation Redirect (CRITICAL)**: `PortalShell.jsx handleSectionPillClick` was navigating to `isHeader: true` items (non-module headers) as the first item when clicking section tabs. Modules like `recruitment-process-header` are not in `MODULE_REGISTRY`, causing DEFAULT_MODULE render. Fix: Skip `isHeader` items when finding first navigable module.
2. **Wrong localStorage key (HIGH)**: 5 modules used `localStorage.getItem('token')` instead of `'erp_token'` causing all API calls to send `Bearer null`. Fixed in: `AnnouncementModule.jsx`, `AnnouncementBoard.jsx`, `HRShiftManagementModule.jsx`, `MultiLevelApprovalModule.jsx`, `ProductionMaterialReturnsModule.jsx`.
3. **"body stream already read" in HRAssetModule (MEDIUM)**: React 18 StrictMode double-invocation causes concurrent same-URL fetch calls to return deduplicated Response objects. Fix: Added `cache: 'no-store'` to `asset` helper and refactored `useEffect` hooks to use async IIFE pattern (consistent with previous fixes in InventoryScrapModule.jsx).
4. **Announcements 403 for superadmin (CRITICAL)**: `routes/announcements.py` had 5 hardcoded role check lists missing `'superadmin'` role. All 5 checks now include `superadmin`.
5. **Payroll employee count wrong (MEDIUM)**: `payroll_automation.py` used `{'employment_status': 'active'}` filter but `rahaza_employees` collection uses `{'active': True}`. Fixed to be consistent with all other HR routes. Coverage now shows `1/1` correctly.

## 2026-06-07 — FULL all-portal deep test sweep (every module) + bug fixes
Context: User asked to test EVERY module across EVERY portal one-by-one, deeply, and fix all bugs in one run.

### Method
- Automated GET pre-screen across ALL 684 param-free GET endpoints: **0 server crashes** (only expected 503 for AI/WebPush).
- Deep backend flow + integration testing per portal via testing_agent (iterations 6–13).

### Per-portal results (backend, deep flow + integration)
- Finance (iter 6): 39/39 ✅  | Production (iter 7): 72/72 ✅
- Inventory = Warehouse+Accessories+Assets (iter 8): 54/55 ✅
- HR (iter 9): 55/55 ✅  | Maklon+Vendor+Client (iter 10): 43/43 ✅
- Marketing/Toko/LiveHost/KOL (iter 11): 75/75 ✅
- RnD (iter 12): ✅ after fix  | Management+Collaboration+Self (iter 13): 68/68 ✅

### Bugs found & FIXED in this sweep
1. **Frontend legacy paths (404)**: InventoryScrapModule.jsx & MaklonMaterialIssuePanel.jsx called
   `/api/rahaza/inventory/*` (404). Corrected to `/api/rahaza/{materials|material-stock|material-movements|material-adjust}`.
   (Also refactored their hooks to satisfy React-compiler lint: memoized headers, async-IIFE effects.)
2. **Marketing 500s (CRITICAL)**: `PlatformAccountCreate/Update` & `SalesDataEntry` Pydantic models in
   marketing_shared.py were stale vs the handlers → 500 on account creation & sales-data entry. Realigned models
   to the actual handler field contract. Verified 75/75.
3. **RnD HPP costing math**: `0 or default` silently overrode an explicit 0 for overhead_pct/margin_pct (and accessory qty).
   Added `_num()` None-aware coercion in dewi_rnd_hpp.py so explicit 0 is respected.
4. **GET /api/roles/audit 500**: audit docs had nested BSON ObjectId fields → JSON encode error. Enhanced the global
   `serialize_doc` (auth.py) to convert ObjectId→str recursively, and wrapped the response.
5. **Backup/Restore fully broken (404)**: admin_backup.py router prefix was `/admin/backup` (no `/api`) while the
   frontend calls `/api/admin/backup/*`. Fixed prefix to `/api/admin/backup`.

All fixes verified via curl + pytest regression suites (test_iteration_6..13). Backend lint gate clean; frontend compiles.


## 2026-06-07 — Finance flow/integration hardening + codebase lint cleanup
Context: User asked to ensure ALL Finance flows and integration relationships are bug-free (tasks a + b).

### Real bugs fixed
- **Posting Profiles startup auto-seed**: `server.py` imported a non-existent `seed_posting_profiles`.
  Added a reusable `seed_posting_profiles(db, user=None)` in `routes/rahaza_posting_profiles.py`
  (route `/seed` now delegates to it). Startup now seeds **33 profiles** (was silently failing → empty).
- **Route shadowing (2)**: `/leaves/balance` and `/finance/accruals/recurring-templates` were defined
  AFTER their `/{id}` param routes and were unreachable (always 404). Relocated literal routes ABOVE
  the parameterized ones in `rahaza_leave.py` and `rahaza_accruals.py`. Both now return 200.
- **Fixed Asset disposal NameError**: `dispose_asset` referenced `user` without binding it.
  Now `user = await require_auth(request)`.
- **Undefined names (F821)**: `warehouse.py` (`_uid/_now/date` → `new_id()/now()/now().date()`),
  `marketing_returns_routes.py` (`date`), `employee_travel_requests.py` (added `STATUS_LABELS`),
  `rahaza_fixed_assets.py` (`user`), `employee_travel_settlements.py` (unused `je_doc`).
- **Periods `ensure-year` 500**: wrapped `request.json()` in try/except so an empty body defaults
  to the current year instead of crashing.

### Hardening / cleanup (lint gate)
- Fixed ~25 potential ObjectId-serialization returns (added `{"_id": 0}` projections or
  `insert_one(dict(doc))` copies) across announcements, procurement, inventory, maklon adapter,
  predictive maintenance, shipments, fulfillment, qc, audit, leave balances, etc.
- Style fixes across backend: bare `except:` → `except Exception:`, multi-statement lines split,
  `== True` truthiness, ambiguous `l` → `lv`, unused vars / f-strings / redefinitions removed.

### Verification
- Frontend paths for the 5 "previously-missing" Finance modules CONFIRMED correct (the earlier
  "7 missing endpoints" were a test-script path mismatch / false alarm).
- testing_agent backend re-validation: **39/39 PASS (100%)**, 0 critical, report
  `/app/test_reports/iteration_6.json`, regression suite `/app/backend/tests/test_iteration_6_finance.py`.

## (earlier session) 2026-06-02 — see FINANCE_COMPREHENSIVE_TEST_REPORT.md
- LiveHost + Maklon portals → light mode; Announcement Board (Portal Selector) + HR CMS;
  Business-process docs; first comprehensive Finance test (iteration_5).


# ADDENDUM — FOTO DESAIN RnD + BANDINGKAN REVISI STYLE (2026-08-07)

**Permintaan owner:** staf RnD bisa mengunggah foto desain (supaya galeri di Cockpit Approval
Manajemen tidak kosong) dan manajemen bisa **membandingkan revisi style berdampingan** sebelum
memutuskan approve.

**Keputusan user (ask_human):** tombol unggah foto **hanya di form Tambah/Edit Style**; revisi
dicatat **otomatis** setiap style disimpan (revisi manual tetap ada); pembanding **2 kolom**
(field berubah disorot + foto berdampingan); dibuka dari **Portal RnD (tab Revisi)** *dan*
**dialog Detail Cockpit Manajemen**.

**Backend (`routes/dewi_rnd_styles.py`)**
- `POST /api/dewi/rnd/styles/{id}/images` — multipart `file` (maks 10MB, hanya `image/*`),
  simpan lewat `storage.put_object` → `/app/uploads`, daftarkan di `attachments` agar
  `GET /api/files/{path}?auth=<token>` bisa menyajikannya, lalu `$push` ke `styles.design_images`.
- `DELETE /api/dewi/rnd/styles/{id}/images/{img_id}` — lepas foto + soft-delete attachment.
- `update_style()` mencatat **revisi otomatis** (`source:'auto'`) ke `dewi_rnd_revisions` beserta
  `snapshot` (10 field terlacak + daftar foto + jumlah varian) dan `changed_fields`. Unggah/hapus
  foto juga membuat revisi bertipe foto → riwayat foto ikut terbandingkan.
- `GET /api/dewi/rnd/styles/{id}/revisions/compare?left=&right=` — dua sisi (id revisi atau
  `current`), `fields[]` dengan flag `changed`, `images.{left,right,added,removed}`, `available[]`
  untuk dropdown. Bawaan: dua revisi terakhir, atau revisi terakhir vs kondisi sekarang.
- `GET /api/dewi/rnd/approvals/pending` kini menyertakan `revisions_count` per style.

**Frontend**
- BARU `RnDRevisionCompare.jsx` (+ helper `authImageUrl` — semua `<img>` dari `/api/files/...`
  wajib memakai `?auth=<token>`; sebelumnya galeri cockpit bisa 401).
- `RnDStylesTab.jsx` — bagian "Foto / Sketsa Desain" di form: mode Tambah menampung file lalu
  mengunggah setelah style tercipta; mode Edit unggah/hapus langsung.
- `RnDRevisionsTab.jsx` — tombol "Bandingkan Revisi" (aktif bila satu style dipilih) + tombol
  "Bandingkan" per kartu revisi.
- `RnDPortalDashboard.jsx` — galeri detail pakai `authImageUrl` + tombol "Bandingkan Revisi".

**Bukti:** `scripts/poc_rnd_photo_compare.py` **28 PASS / 0 FAIL** (bersih setelah run) ·
testing_agent `iteration_19.json` frontend **100%**, 0 bug · `yarn build` sukses (static bundle
di-rebuild lewat `scripts/rebuild_frontend.sh`).

# ADDENDUM — TAHAP RnD LENGKAP · RAPOR MINGGUAN · AMBANG PERINGATAN (2026-08-07)

**Permintaan owner (3):** (1) kokpit manajemen menampilkan tahap Tech Pack & pembuat sample,
bukan hanya 4 langkah; (2) rapor keputusan RnD mingguan (disetujui / ditolak / menunggu terlalu
lama); (3) pengaturan berapa hari sebelum tenggat PO peringatan dikirim.

**Keputusan user (ask_human):** kolom **PIC / Pembuat Sample** ditambahkan di form Sample Request
RnD lalu tampil di kokpit · rapor dikirim **Senin 08:00 WIB** · **in-app dulu** (belum email) ·
ambang **PO dan piutang dipisah**, bawaan tetap 3 hari.

**Backend**
- `routes/dewi_rnd_design.py` — helper `rnd_lifecycle()` + `STAGE_ORDER` **7 tahap**
  (Draft → Menunggu Keputusan → Disetujui → Tech Pack → Pola & Marking → Sample → Naik Produksi).
  Setiap style menempati SATU tahap terjauh ⇒ jumlah tahap = jumlah style (funnel jujur).
  Endpoint `GET /api/dewi/rnd/lifecycle` (tahap + baris per style: varian, foto, revisi, tech pack
  versi/status, pola, sample + PIC, HPP, `next_action`). `funnel` di `/approvals/pending` sekarang
  memakai helper yang sama ⇒ satu sumber angka. Detail sample di kokpit menampilkan PIC.
- `services/rnd_decision_report.py` (BARU) — `build_rnd_decision_report()` /
  `send_rnd_decision_report()` (idempoten per pekan ISO, `force=True` untuk tombol manual) +
  `job_weekly_rnd_decision_report`. Endpoint `GET /api/dewi/rnd/reports/weekly-decisions` (pratinjau)
  dan `POST .../send` (Kirim sekarang).
- `utils/scheduler.py` — job `weekly_rnd_decision_report` cron Senin 08:00 Asia/Jakarta.
- `services/management_alerts.py` — `get_alert_config()` / `save_alert_config()` pada
  `dewi_mgmt_alert_config` (`po_warn_days`, `ar_warn_days`, `rnd_stale_days`; validasi 0..60).
  `scan_management_alerts()` memakai ambang PO & AR terpisah; `warn_days` tetap sebagai override.
- `routes/rahaza_reports.py` — `GET/PUT /api/rahaza/management/alert-config`; `GET /management/alerts`
  tanpa parameter kini memakai ambang tersimpan.
- `routes/dewi_rnd_samples.py` — field `sample_pic`.
- `routes/dewi_rnd_styles.py` — hapus style ikut menghapus revisinya (cegah revisi yatim).

**BUG PENTING YANG DIPERBAIKI** — `routes/notification_categories.py`: koleksi `notifications`
punya DUA konvensi penulis (lama: `target_user_ids`/`target_roles`; SSOT `notif_insert`: `user_id`
satu dokumen per penerima). Bel hanya membaca konvensi lama, sehingga **peringatan PO/piutang
(fitur sesi sebelumnya) dan rapor RnD tersimpan tapi tidak pernah muncul di bel**. `_fetch()`
sekarang juga mencocokkan `user_id`, dan `categorize()` membaca `meta.link_module` + `subtype`
(rapor RnD → kategori "RnD"). *Pelajaran: setiap penulis notifikasi baru harus diuji sampai
tampil di bel, bukan berhenti di penyimpanan DB.*

**Frontend**
- `RnDPortalDashboard.jsx` — funnel 7 tahap, kartu **Posisi Tiap Style** (tabel 9 kolom termasuk
  TECH PACK dan SAMPLE (PIC) + LANGKAH BERIKUTNYA), kartu **Rapor Keputusan Mingguan** (4 angka,
  daftar tertunda lama, tombol "Kirim sekarang").
- `RnDSamplesTab.jsx` — input **PIC / Pembuat Sample** + kolom tabel.
- `ManagementOverviewModule.jsx` — kartu peringatan selalu tampil + form **Ambang Peringatan**
  (PO & piutang, tersimpan di DB, dipakai penjadwal 07:00).

**Bukti:** `scripts/poc_rnd_stages_alerts.py` **50 PASS / 0 FAIL** ·
`scripts/poc_notif_bell_rnd.py` **11 PASS / 0 FAIL** · testing_agent `iteration_20.json` (92%,
1 bug HIGH) → diperbaiki → `iteration_21.json` **100%**.

**Catatan data:** koleksi `dewi_rnd_tech_packs` & `dewi_rnd_patterns` masih kosong, jadi tahap
Tech Pack/Pola wajar menampilkan 0 sampai staf RnD mengisinya (angka nyata, bukan dummy).

---

## 2026-08-10 — FASE 4: **REKAP MINGGUAN CMT** (tab kedua "Input Vendor CMT")

**Konteks pemulihan.** `/app` kembali berisi template kosong (pola yang sama seperti dua sesi
sebelumnya). Dipulihkan dalam **159 detik**: clone `github.com/kamaaajahbamama/da` → `rsync` (kecuali
`.git`, `.env`, `node_modules`) → `mongorestore --gzip --drop` dari `backups/auto_20260807_190000`
(**1218 dokumen**) → `bash scripts/bootstrap.sh` → `python3 scripts/seed_cmt_override_demo.py`
(3 vendor CMT demo). Backend healthy, bundle statis HTTP 200, 6 akun login 200.

**Titik terhenti sesi lalu:** todo "catat keputusan owner Rekap Mingguan di `plan.md`" sedang
BERJALAN saat sesi terputus ⇒ keputusannya **hilang** (hanya judul todo yang tersimpan). Karena angka
rekap = dasar **tagihan CMT**, definisinya TIDAK ditebak: owner ditanya ulang. Jawaban pertama memilih
dua opsi bertentangan pada 3 pertanyaan, jadi ditanya sekali lagi sampai tunggal. Hasilnya dicatat di
`plan.md` §4.1 sebelum satu baris kode ditulis.

### Backend

- **`core/cmt_daily_recap.py`** — `WEEK_DAYS`, `MAX_WEEK_DAYS`, `week_range()`, `build_week()`.
  `build_week()` **tidak punya satu pun query sendiri**: ia memanggil `build_recap()` untuk tiap hari
  dengan `ctx` bersama dari `prefetch_context()`, lalu hanya **meringkas**. Akibat yang disengaja:
  tab Mingguan **mustahil** berdebat dengan tab Harian — angkanya memang benda yang sama, bukan dua
  perhitungan yang "seharusnya" sama. Hari > hari ini diberi state `future`, tidak dihitung, dan
  `build_recap` **tidak dipanggil** untuk hari itu.
  Baris mingguan juga membawa `last_login_at`/`account_count` supaya **satu** fungsi pemilih vendor
  (`pickFromRecap`) bisa melayani kedua tab.
- **`utils/cmt_recap_export.py`** — `build_week_xlsx()` + `build_week_pdf()` (openpyxl + reportlab,
  **tanpa dependensi baru**). Menerima hasil `build_week()` apa adanya. Nama berkas
  `rekap-mingguan-cmt-<mulai>-<akhir>.<ext>`. Lambang kotak hari `future` sengaja **kosong**, bukan
  "-": hari yang belum terjadi bukan "tidak ada pekerjaan".
- **`routes/cmt_override_routes.py`** — `GET /api/cmt-override/weekly-recap` dan
  `GET /api/cmt-override/weekly-recap/export?format=xlsx|pdf`. `?date=` = hari **TERAKHIR** jendela
  (default hari ini WIB), `?days=` 1..31 (di luar itu **400**, bukan 500), `?include_inactive=`.
  RBAC memakai `_guard()` yang sama; header `X-CMT-Override-Vendor` **diabaikan** (pandangan lintas
  vendor milik staf). Payload membawa `remind_date` + `remind_pending` dari
  `pending_vendor_rows()` yang **sama** dengan tab Harian.

### Frontend

- **BARU** `cmt-override/recapDates.js` — helper tanggal **WIB** bersama (`isoToday`, `shiftDay`,
  `dayLabel`, `shortDate`, `daysBetween`). Sebelumnya helper ini disalin di dalam komponen; salinan
  itulah yang suatu hari akan berbeda dan membuat dua tab tidak setuju tentang "hari ini".
- **BARU** `cmt-override/CMTOverrideRecapPanel.jsx` — tab **Harian | Mingguan** dan **pemilik state
  tanggal**. Ini yang memungkinkan permintaan owner "klik kotak hari → buka Rekap Harian tanggal itu":
  kalau tiap tab menyimpan tanggalnya sendiri, klik kotak hari paling jauh hanya bisa membuka tab
  Harian pada "hari ini" — justru menyembunyikan hari yang sedang diselidiki.
- **BARU** `cmt-override/CMTOverrideWeeklyRecap.jsx` — 6 kartu ringkasan · kepala kolom hari memuat
  badge "N belum / aman" dari `per_day` backend (kelihatan HARI MANA yang paling bolong) dan **bisa
  diklik** · 7 kotak hari per vendor (5 keadaan: done/partial/pending/idle/**future**) · kolom
  **Terlambat** & **Belum beres** DIPISAH · hari tanpa setoran ("dari N hari kerja") · pcs
  setor/kirim · **sparkline SVG mentah** (bukan recharts: satu sparkline per baris, memasang komponen
  chart penuh di setiap baris memberati layar pagi tanpa menambah informasi) · streak + sebab
  putusnya · pencarian · filter "hanya yang bermasalah" · export Excel/PDF · reminder dengan
  **tanggal disebut** di panel konfirmasi.
- `CMTOverrideDailyRecap.jsx` — jadi **terkendali** (`day` + `onDayChange`), tetap punya state sendiri
  bila prop tidak diberikan; helper tanggal lokalnya dipindah ke `recapDates.js`.
- `CMTOverridePortalModule.jsx` — merender `CMTOverrideRecapPanel` (bukan `CMTOverrideDailyRecap`).

### Alat uji & gate

- `test_core_rekap_harian.py` — **102 → 169** pemeriksaan (§11–§15 baru). Pola lampau dibuat
  SUNGGUHAN lewat HTTP (setoran + kiriman bertanggal sama pada H-4 dan H-2) supaya "beres → tanpa
  pekerjaan → beres" bisa membuktikan **streak = 2** (hari tanpa pekerjaan NETRAL) secara
  deterministik. *Pelajaran yang ikut terdokumentasi: satu hari hanya benar-benar "beres" kalau
  setoran DAN kirimannya bertanggal sama — kalau hanya setoran, hari-hari SESUDAHNYA jadi merah
  ("pcs selesai belum dikirim"), dan itu memang benar menurut definisi harian.*
- `scripts/verify_rekap_harian.py` (INV-REKAP) — **22 → 30 kode**, baru **RK-20…RK-27**: rentang
  bergulir + validasi parameter · **konsistensi harian↔mingguan** (invarian termahal) · dua angka
  terlambat tetap terpisah · hari tanpa setoran tidak menghukum vendor tanpa job · aturan streak ·
  SSOT export mingguan termasuk **URUTAN** baris · RBAC + header override + hari `future` ·
  **kinerja** (mingguan tidak boleh lebih mahal daripada 7× harian ⇒ `prefetch_context` masih dipakai).
- `backend_test_fase4_mingguan.py` (buatan testing agent, **diperbaiki lalu DISIMPAN** — READ-ONLY,
  32 GET + 4 login, tidak menulis apa pun jadi tidak perlu bersih-bersih). **Dua cacat diperbaiki:**
  (a) tanggal MATI (`date=2026-08-08`, `future=2026-08-12`) ⇒ **rusak besok**; (b) uji
  `remind_pending` memakai tanggal yang di data demo NOL vendor merah ⇒ membandingkan himpunan kosong
  dengan himpunan kosong dan mencetak **"PASS (0 vendors)"** — pemeriksaan termahal di berkas itu
  sebenarnya tidak pernah memeriksa apa pun. Sekarang semua tanggal dihitung dari hari ini **WIB**,
  memakai jendela BERJALAN (benar-benar membandingkan 2 vendor), dan bila suatu hari himpunannya
  kosong skrip **mengatakannya terus terang** alih-alih mencetak PASS yang menenangkan.
  *(Bandingkan sesi lalu: berkas buatan testing agent DIHAPUS karena mengirim teguran sungguhan tanpa
  membersihkannya. Yang ini tidak menulis apa pun, jadi diperbaiki — bukan dibuang.)*

**Temuan pemulihan:** `prefetch_context()` ternyata **sudah ada** di commit terakhir sesi lalu (todo
"BE refactor `_prefetch()`" sudah selesai, yang kurang hanya BUKTI). Sekarang dijaga gate RK-27.

**Bukti:** POC **169/169** · INV-REKAP **30 OK / 0 FAIL** · `bash scripts/gate.sh` **18/18 PASS,
VERDICT HIJAU** · `bash scripts/rebuild_frontend.sh` OK (frontend HTTP 200) · testing_agent_v3
`iteration_39` backend **17/17**, frontend 100%, **0 bug / 0 action item** · verifikasi layar sendiri
(Playwright): tab berpindah, klik kotak `2026-08-08` → tab Harian pada **2026-08-08**, Excel & PDF
benar-benar terunduh, reminder terkirim ke 2 vendor untuk `2026-08-10` lalu klik kedua "Tidak ada yang
dikirim — 2 vendor sudah ditegur" · **UANG: tagihan CMT 2.435.000 → 2.435.000** · nol jejak data uji ·
state demo dipulihkan (SJ demo kembali `Sent`, **nol** reminder rekap sisa).

**Catatan untuk owner:** tombol reminder di tab Mingguan ADA (owner memilih "ada" pada ronde pertama
pertanyaan) dan menegur untuk **hari terakhir yang sudah berjalan**. Mudah dicabut kalau ternyata
hanya dikehendaki di tab Harian — hapus blok tombol + panel konfirmasi di
`CMTOverrideWeeklyRecap.jsx`; backend tidak perlu diubah.

---

## 2026-08-10 (lanjutan) — FASE 5: **`closed_at`** — rekap tanggal lampau berhenti menebak

**Backlog nomor 1 fase 4 ditutup.** Fase 4 meninggalkan satu kebohongan struktural yang ditulis
jujur sebagai catatan di layar: `production_jobs` tidak menyimpan **kapan** job ditutup, jadi
"job jalan pada tanggal X" dijawab dari **status SEKARANG**. Akibat nyatanya: job yang dibuka
**Senin**, tidak disetor Senin, lalu **ditutup Rabu** **HILANG** dari rekap hari Senin — padahal
hari itu vendor MEMANG punya pekerjaan yang tidak dikerjakan. **Kelalaian yang sudah terjadi
terhapus sendiri begitu job-nya ditutup.** Karena progress produksi adalah dasar **tagihan CMT**,
laporan yang memaafkan dirinya sendiri seperti itu tidak bisa dipakai memverifikasi apa pun —
bantahan vendor "saya tidak pernah bolong" tidak bisa diuji. Ini bukan sulit dihitung, tapi
**mustahil**: datanya memang tidak pernah disimpan.

### Backend

- **BARU `core/production_job_lifecycle.py`** — SSOT penutupan job.
  - `JOB_CLOSED_STATUSES` (`Completed`/`Closed`/`Cancelled`/`Canceled`/`Done`/`Finished`) +
    `is_closed_status()`. **Daftar ini tidak boleh disalin ke pemanggil** — salinan itulah yang
    suatu hari akan berbeda dari yang dipakai backend.
  - `close_job(db, job_id, *, status, when, extra)` — **satu-satunya penulis `closed_at`**.
    Idempoten, **tutup PERTAMA yang menang** (waktu tutup yang benar adalah yang pertama), tetapi
    stempel **perkiraan** hasil migrasi (`closed_at_estimated: True`) BOLEH digantikan pengamatan
    sungguhan — tebakan tidak boleh mengalahkan fakta. Sengaja **tidak** menerima `closed_at` dari
    body permintaan.
  - `was_open_at(job, moment)` — satu aturan "masih jalan saat itu", dipakai rekap harian **DAN**
    mingguan: belum lahir (`created_at >= moment`) ⇒ tidak jalan · punya `closed_at` ⇒ jalan bila
    `closed_at >= moment` · tanpa `closed_at`: status terbuka ⇒ jalan, status tertutup ⇒ dokumen
    **WARISAN** ⇒ `False` (**persis perilaku lama**, supaya yang memperbaikinya adalah migrasi,
    bukan tebakan diam-diam).
  - **Status yang TIDAK dikenal dianggap TERBUKA** — pilihan sadar karena dua arah salahnya tidak
    seimbang: menganggap tertutup padahal terbuka membuat pekerjaan nyata HILANG dari rekap ⇒
    progress tidak diisi ⇒ uang tidak bisa ditagih; menganggap terbuka padahal tertutup hanya
    membuat satu baris tampak merah dan langsung diselidiki orang.
- **DUA jalur penutup job disatukan** (keduanya sudah pernah berbeda perilaku):
  `routes/production_execution.py` auto-complete saat semua item mencapai `shipment_qty`, dan
  `routes/production_pos.py` **Quick Complete**. Keduanya kini memanggil `close_job()`. Kalau
  masing-masing menulis `closed_at` sendiri, suatu hari salah satunya lupa (atau menulis tipe
  berbeda) dan rekap tanggal lampau kembali bohong **tanpa ada yang tahu** — ini pelajaran langsung
  dari bug `received_at` fase 3.
- **BARU `migrations/add_closed_at_to_production_jobs.py`** — backfill job warisan. Waktu tutup
  sebenarnya tidak tersimpan di mana pun, jadi diperkirakan dari `updated_at` (kedua jalur penutup
  selalu menulisnya saat menutup, dan job tertutup hampir tidak pernah disentuh lagi); fallback
  `created_at`; **kalau keduanya tidak ada, dokumen DILEWATI dan dilaporkan** — lebih baik jujur
  tidak tahu daripada mengarang tanggal untuk laporan yang dipakai memverifikasi tagihan. Setiap
  hasil migrasi ditandai **`closed_at_estimated: True`** supaya auditor bisa membedakan stempel
  teramati dari perkiraan. Idempoten (dokumen yang sudah punya `closed_at` tidak disentuh).
- `core/cmt_daily_recap.py` — "job jalan" memakai `was_open_at()`; proyeksi job membawa `closed_at`
  + `closed_at_estimated`; melaporkan `legacy_jobs_without_closed_at`.
- `core/cmt_daily_recap.py` (lanjutan) — **`as_of_note` dipecah**: `as_of_note_base` (kalimat
  aturan) + **`legacy_note`** (kalimat AKSI: jumlah job warisan + perintah migrasinya).
  `as_of_note` tetap **utuh persis seperti sebelumnya** (base + " Catatan: " + legacy_note) karena
  berkas export dan pemanggil API lain membacanya sebagai satu kalimat. `build_week()`
  **MENGAMBIL** `legacy_note` dari rekap harian, tidak menyusunnya ulang — kalau ditulis dua kali,
  suatu hari kedua layar akan menyuruh menjalankan migrasi yang berbeda dan tidak ada yang tahu
  mana yang benar. Bentuk respons juga dijaga tetap pada cabang "tidak ada vendor" (layar tidak
  boleh harus menebak apakah sebuah field ada).

### Frontend

- `cmt-override/CMTOverrideDailyRecap.jsx` — peringatan **amber** `cmt-recap-legacy-jobs`
  (jumlah job warisan + perintah migrasi), dan baris info abu-abu kini memakai `as_of_note_base`
  sehingga kalimatnya **tidak kembar**. Dinaikkan dari abu-abu 11px di ujung paragraf karena
  **catatan yang tidak terbaca sama saja dengan tidak mengaku** — dan rekap yang diam soal batasnya
  sendiri akan dipercaya lebih daripada yang seharusnya.
- `cmt-override/CMTOverrideWeeklyRecap.jsx` — peringatan **amber** `cmt-week-legacy-jobs`.
  **Sebelum ini tab Mingguan tidak pernah menyebut keterbatasan itu sama sekali**, padahal jendela
  7 hari justru yang paling terpengaruh: satu job warisan bisa membuat beberapa kotak hari tampak
  lebih bersih daripada kenyataannya. Angka & kalimatnya diambil dari backend (tab ini tetap tidak
  menghitung apa pun sendiri).

### Alat uji & gate

- `test_core_rekap_harian.py` — **169 → 191** pemeriksaan. §17 `closed_at`: stempel ditulis SERVER
  sebagai tanggal BSON (bukan string browser), job yang ditutup hari ini tetap terhitung "job jalan"
  pada tanggal lampau lalu berhenti pada tanggal sesudahnya, suntikan `closed_at`/`status` dari klien
  diabaikan. §18 migrasi: rekap **mengaku** dulu ada job warisan (dan menyebut migrasinya), migrasi
  memperbaikinya (`0 → 1` job jalan pada tanggal lampau), stempelnya ditandai perkiraan dan **sama
  dengan `updated_at`** (bukan angka karangan), migrasi **idempoten**, dan rekap **mingguan otomatis
  ikut benar** karena ia hanya meringkas `build_recap`.
- `scripts/verify_rekap_harian.py` (INV-REKAP) — **30 → 34 kode**:
  - **RK-28** — job yang DITUTUP hari ini tetap terhitung "job jalan" pada tanggal SEBELUM
    penutupan dan tidak lagi pada tanggal SESUDAHNYA; `closed_at` bertipe tanggal & ditulis server.
    Sejarah job dibuat langsung di Mongo (hanya "kapan job lahir" yang dipalsukan) karena
    `created_at` ditulis server dan tidak bisa dibuat lampau lewat API — **penutupannya tetap lewat
    HTTP sungguhan**.
  - **RK-28b** — `closed_at`/`status` kiriman BROWSER diabaikan saat job dibuat.
  - **RK-29** — integritas **SELURUH DB**: nol job berstatus tertutup tanpa `closed_at`. Ini yang
    akan MERAH kalau suatu hari ada **jalur penutup KETIGA** yang tidak memakai `close_job()`.
    Daftar status penutup **diimpor** dari SSOT-nya, tidak disalin ke dalam gate.
  - **RK-30** — job WARISAN dilaporkan **apa adanya ke layar** harian DAN mingguan (jumlah +
    perintah migrasi), dan `as_of_note` (dibaca berkas export) dikunci = `as_of_note_base` +
    `legacy_note`. Diuji dengan **benar-benar melepas** stempel job uji (bukan hanya memeriksa
    "nol"), karena cabang "ada warisan" itulah yang dipakai pengguna sungguhan; stempelnya
    dipulihkan di `finally` supaya gate tidak menjadi sumber bug bagi RK-29 pada putaran berikutnya.
  - Docstring gate diperbarui: kelas masalah **11–14** (laporan yang memaafkan dirinya sendiri ·
    jalur tutup baru yang lupa menulis stempel · stempel dari browser · **ketidaktahuan yang
    disembunyikan**).

**Temuan pemulihan lingkungan — BUG SETUP YANG SUDAH 2 SESI BERULANG, akhirnya ditemukan akarnya
dan DIPERBAIKI.** Gejalanya: bootstrap mencetak `frontend deps sudah sesuai hash — skip`, lalu
`yarn build` MERAH `Module not found: '@simplewebauthn/browser'` (diimpor `src/pages/AbsenPage.jsx`)
dan ringkasan menutup dengan `build/ MISSING` — preview menyajikan bundle BASI tanpa ada yang sadar.
Session #25 mencatatnya sebagai "lockfile drift" dan menyembuhkannya dengan tangan; itu **bukan**
akarnya. Akar sebenarnya = **TIGA hal yang kebetulan bertemu**:
1. `.bootstrap_cache/fe.md5` **ikut ter-commit** ke repo (keadaan MESIN ikut bepergian sebagai kode);
2. `frontend/yarn.lock` **tidak ada di repo**, jadi `FE_HASH = md5(package.json + yarn.lock milik
   TEMPLATE platform)` — nilainya **reproducible persis sama setiap sesi**, sehingga marker yang
   ter-commit itu **selalu** "cocok";
3. `frontend/node_modules/` milik template platform **sudah ada** (isinya bukan dependensi aplikasi
   ini), sehingga syarat `[ -d node_modules ]` juga terpenuhi.

Ketiga syarat skip terpenuhi ⇒ **`yarn install` tidak pernah jalan**. Perbaikannya memakai pelajaran
yang sudah dipakai untuk backend: **marker cache hanya sah kalau dibuat DI MESIN INI**.
- `scripts/bootstrap.sh` — langkah **`1c-3`** baru: probe **KENYATAAN**, yaitu setiap `dependencies`
  di `package.json` harus benar-benar ada di `node_modules`; kalau tidak, marker **dibuang** dan
  `yarn install` **dipaksa**. Simetris dengan probe import backend `1c` yang sudah ada (dan yang
  memang bekerja — itulah kenapa backend tidak pernah kena masalah ini).
- `.gitignore` — `.bootstrap_cache/` diabaikan dan markernya di-`git rm --cached`. Ini juga
  mengeluarkan `.bootstrap_cache/admin_token.txt` (**JWT hidup**) dari repo.
- `frontend/yarn.lock` kini **di-commit** supaya instalasi reproducible untuk sesi berikutnya.
- **Diuji dua arah** (bukan diasumsikan): node_modules lengkap → `deps frontend terpasang (probe
  node_modules)`; paket dihapus + marker basi dipasang ulang → `deps frontend belum lengkap
  (1 paket hilang: @simplewebauthn/browser) → marker cache dibuang, yarn install dipaksa`.

**Bukti:** POC **191/191 LULUS** · INV-REKAP **34 OK / 0 FAIL** · `bash scripts/gate.sh`
**18/18 PASS, VERDICT HIJAU** · `bash scripts/gate.sh --full` **22/22 PASS, VERDICT HIJAU**
(18 gate inti + 4 alur produk HR — diperiksa ulang karena edit menyentuh jalur job produksi) ·
`bash scripts/rebuild_frontend.sh` OK (frontend HTTP **200**) · verifikasi VISUAL sendiri
(Playwright): banner amber job warisan tampil di tab **Harian** dan **Mingguan** tanpa kalimat
kembar dengan baris info abu-abu · **UANG: tagihan CMT 2.435.000 → 2.435.000** · nol jejak data uji
(`POCRK` / `__REKAPTEST__` / `__FASE5VIS__`) · nol job tertutup tanpa `closed_at` di DB akhir.

