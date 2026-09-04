---

# 🤝 HANDOFF (Session #38 — **COGS PENGIRIMAN MEMAKAI BIAYA BATCH NYATA** · pemulihan container) ✅

Rincian & bukti: `memory/CHANGELOG.md` entri **[#38]**, invarian **INV-F44** di
`memory/INVARIANTS.md`, langkah berikutnya di **`memory/HANDOFF_SESI_39.md`**.
Seluruh suite: `bash scripts/gate.sh --full` → **65 gate · VERDICT HIJAU**.

## ⚠️ HAL PERTAMA YANG HARUS AGEN BERIKUTNYA TAHU
1. **Baca `memory/HANDOFF_SESI_39.md`** — di situ ada urutan bring-up container (termasuk
   `seed_role_accounts.py` yang WAJIB, tanpa itu absen/cuti/payslip pasti MERAH) dan daftar
   pekerjaan berikutnya.
2. **Jurnal COGS punya DUA dasar dan keduanya sengaja terlihat.** `basis=fifo_batch` (biaya batch
   nyata dari gudang) vs `hpp_snapshot` (perkiraan HPP SPK). Jangan menyatukannya menjadi satu angka
   tanpa sumber, dan jangan menambah dasar ketiga di luar `_fifo_cogs_for_dispatch`.
3. **`uncosted_qty` bukan noise.** Pcs yang keluar tanpa lapisan biaya membuat COGS lebih rendah dari
   kenyataan. Ia WAJIB tetap terlihat di hasil jurnal dan di layar.
4. **17 gate merah sesudah restore container adalah DATA + ALAT UKUR, bukan regresi kode.** §2
   `HANDOFF_SESI_39.md` memuat perintah perbaikannya. Jangan membangun ulang kode yang sudah hijau.

---

# 🤝 HANDOFF (Session #34 — **BIAYA JAHIT MASUK HPP** · impor pintar · portal kreator hidup · host digaji bulanan) ✅

Rincian & bukti: `plan.md` (sesi #34), `memory/CHANGELOG.md` entri **[#34]**, gate baru **INV-F39**.
Seluruh suite: `bash scripts/gate.sh` → **62 gate · VERDICT HIJAU**.

## ⚠️ HAL PERTAMA YANG HARUS AGEN BERIKUTNYA TAHU
1. **Repo ini dipulihkan dari GitHub ke container baru pada sesi #34.** Yang WAJIB dilakukan kalau
   container terlihat kosong/rusak: (a) `mongorestore --gzip --drop --nsInclude='test_database.*'
   --dir=backups/<terbaru>`; (b) `pip install -r backend/requirements.txt`; (c) **`backend/.env`
   harus memuat `JWT_SECRET`** — tanpa itu backend menolak menyala (bukan bug, itu penjaga); (d)
   `cd frontend && yarn install`; (e) **`bash scripts/rebuild_frontend.sh`** — frontend disajikan
   dari **build statis** (`node static_server.js`), jadi perubahan file frontend TIDAK terlihat
   sampai di-build (±2 menit).
2. **HPP sekarang punya DUA arti dan keduanya sengaja terlihat.** `hpp` di master FG = angka yang
   dipakai layar; `hpp_source` menyebut asalnya: `fifo_batch` (biaya batch NYATA dari gudang) vs
   kalkulator BOM (perkiraan). Jangan "merapikan" ini menjadi satu angka tanpa sumber — pemilik
   justru meminta bisa membedakannya.
3. **Portal kreator TIDAK BOLEH menerima field biaya.** Filternya **daftar PUTIH**
   (`marketing_kol_portal.CREATOR_CATALOG_FIELDS`), bukan daftar hitam. Kalau menambah field katalog
   baru, ia tidak akan muncul di portal kreator sampai sengaja dimasukkan ke daftar putih — itu
   perilaku yang diinginkan.
4. **Deteksi jenis impor TIDAK memutuskan apa pun.** Ia hanya melaporkan peringkat + bukti; manusia
   tetap memilih. Jangan mengubahnya menjadi auto-switch — aturan proyek: AI tidak memilih tabel
   tujuan.

## ⚠️ PELAJARAN SESI #34 (jangan diulang)
1. **"Fitur ada" ≠ "fitur bisa dipakai".** Backend pencairan marketplace lengkap 539 baris sejak
   sesi #14 tetapi **nol layar** memanggilnya; pemilik wajar bertanya "di mana menunya". Setiap
   backend baru WAJIB punya pintu di `portalNav.js` + `moduleRegistry.js` di sesi yang sama.
2. **Penyemai data lama bisa melahirkan akun yang mustahil dipakai.** 3 kreator demo lahir tanpa
   `login_email`/hash ⇒ portal kreator terlihat "rusak" padahal kodenya benar. Penyemai sekarang
   MEMPERBAIKI dokumen lama, dan `memory/test_credentials.md` memuat kredensialnya.
3. **Dua validator untuk satu konsep = bug yang menunggu.** `routes/marketing_budget._valid_period`
   diperluas ke periode 7 hari, tetapi `core/marketing_cycle.valid_period` tidak ⇒
   `budget/summary` 500 dan layar menampilkan **Rp 0 tanpa pesan**. Kalau memperluas format sebuah
   kunci, cari SEMUA pembacanya (`grep -rn "valid_period\|%Y-%m"`).
4. **Ukur dengan berkas ASLI pemilik, bukan contoh buatan.** Menjalankan mesin impor pada 7 ekspor
   nyata langsung memperlihatkan pesanan Shopee hanya 14/50 kolom terpetakan — hal yang tidak akan
   pernah terlihat dari template sendiri. Berkasnya disimpan di `samples/marketplace_2026/`.
   Catatan: `retur refund shopee.xls` memang **hanya berisi header (0 baris data)** — penolakannya
   BENAR, bukan bug.
5. **Alat ukur & agen uji ikut meninggalkan sampah data.** Sesi ini membersihkan 1 riwayat harga
   yatim, 1 baris stok + 1 kartu stok + 1 `wh_returns` yang menunjuk material terhapus. Setelah
   menjalankan agen uji, JALANKAN `scripts/gate.sh` lagi — beberapa invarian keadaan-akhir
   (INV-F30/V15, INV-F31/R9) memang mendeteksi sampah semacam itu.

## Yang BELUM dikerjakan (baca `plan.md` bagian "PR berikutnya")
FIFO keluar **sudah dipasang** (`production_qty_ledger.issue_fg` memakan lapisan tertua; gate B3
mengikatnya). Yang tersisa & paling bernilai: **sambungkan `fg_cogs` (COGS FIFO per pengiriman) ke
jurnal COGS** — angkanya sudah tersimpan di baris pengiriman tetapi jurnalnya masih memakai dasar
biaya lama. Sisanya pekerjaan DATA (BOM kosong, 3 SKU SPK tanpa master) yang pemilik minta ditunda.

---

# 🤝 HANDOFF (Session #32 — **NILAI POTONGAN LAHIR SAAT DIPOTONG** · potongan yatim punya penjaga & pembersih) ✅

Rincian & bukti: `memory/PLAN_ARSIP_2026-08-23_SESI32_NILAI_POTONGAN.md` (plan sesi #32),
`memory/CHANGELOG.md` entri **[#32]**, gate baru **INV-F37**.
Seluruh suite: `bash scripts/gate.sh` → **55/55 PASS · VERDICT HIJAU** (diverifikasi ulang di
container BARU pada sesi #33 sebelum satu baris pun diubah).

> ⚠️ Sesi #32 **terputus tepat saat menulis dokumentasi**. Yang sudah tersimpan: seluruh KODE, gate
> INV-F37, `plan.md`, dan backup DB. Yang ditulis belakangan (sesi #33): entri CHANGELOG, bagian
> INVARIANTS INV-F37, dan HANDOFF ini. Kalau sebuah sesi berhenti mendadak, **periksa dulu apakah
> yang hilang hanya dokumentasi** — jangan membangun ulang kode yang sudah hijau.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **ALAT UKUR adalah sumber sampah data yang NYATA.** "Potongan yatim" yang pemilik temukan bukan
   lahir dari alur produk, tetapi dari gate INV-F24 yang menghapus master potongan memakai **REGEX
   KODE**. Pola kode berubah di sesi #30 (kode potongan kini diturunkan dari NAMA MODEL) ⇒ penjaganya
   berhenti bekerja **tanpa suara** dan menumpuk satu sampah tiap kali gate dijalankan. **Hapus lewat
   `id`, jangan lewat pola kode**, dan pasang invarian **KEADAAN AKHIR** (mis. "0 yatim") supaya
   kebocoran alat ukur sendiri ikut MERAH.
2. **Nilai harus berpindah saat BARANGNYA bergerak, bukan saat dokumennya ditutup.** Harga yang
   di-snapshot saat order dibuat sudah basi ketika kain benar-benar dipotong (terukur: Rp41.379
   hilang pada SATU order).
3. **Baca stok SEBELUM `stock_service.add`** kalau ingin rata-rata bergerak yang benar — kalau dibaca
   sesudahnya, qty yang baru masuk ikut menjadi penyebut dan HPP-nya salah tanpa terlihat.
4. **"Navigasi rusak" dari penguji belum tentu benar.** Penguji sesi #31 memakai module-id yang tidak
   ada (`rahaza-models`; yang benar `prod-models`). Tetapi penyelidikannya MENEMUKAN cacat nyata:
   hash URL tidak mengikuti layar ⇒ F5 melempar ke layar lain. **Periksa klaim penguji, jangan
   menolaknya mentah-mentah.**

## YANG SUDAH SIAP DIPAKAI
- **`core/cut_panel_value.py`** — `apply_progress_value()` (satu pintu nilai kain → nilai potongan,
  rata-rata bergerak lewat `core/accessory_valuation` + riwayat harga), `panel_onhand()`,
  `order_value_totals()`. Panggil ini dari alur mana pun yang memindahkan kain menjadi potongan.
- **`core/cut_panel_health.py`** — `scan()` · `cleanup()` (idempoten) · `remove_if_unused()`.
  Definisi keyatiman + BUKTI kelayakan hapus (stok, buku besar stok, kartu stok, rujukan
  BOM/MI/PR/PO/GR). **Alur baru yang membuat master turunan WAJIB memanggil `remove_if_unused`.**
- Endpoint **`GET /api/cutting/panels/health`** & **`POST /api/cutting/panels/cleanup`**, plus layar
  **Master Potongan** (`cutting-panels`) yang sudah punya kartu yatim + tombol *Bersihkan yang aman*.
- POC `test_core_potongan_nilai_dan_yatim.py` (**13/13**, `--keep` untuk menyisakan data periksa).
- **Backup DB `backups/auto_20260823_190000`** (2,4 MB · 230 koleksi · 6.414 dokumen · 335 material ·
  total stok material 33.633). Container ini TERBUKTI bisa datang dengan DB kosong — restore:
  `mongorestore --quiet --gzip --drop --nsInclude='test_database.*' --dir=/app/backups/auto_20260823_190000`

## SISA PEKERJAAN
1. **Daftar Belanja Mingguan** · 2. **Riwayat Harga Barang** · 3. **Isi Ambang Massal** — ketiganya
   dikerjakan sesi #33 (lihat `plan.md`). ⚠️ **UKUR DULU:** pengukuran sesi #33 membuktikan layar
   *Ambang Stok* (tab di `wh-master`) **sudah ada** sejak W3 — yang belum ada adalah jalan massal
   untuk 330 material yang tidak punya pemakaian 30 hari.
2. (kecil) **41 jenis dokumen** masih "Otomatis saja" di Penomoran Dokumen (pola menyambungkannya
   sudah terbukti — lihat HANDOFF sesi #18).

## CARA MENGUJI CEPAT (3 menit)
1. `admin@garment.com` / `Admin@123` → `window.location.hash='cutting-orders'` → reload.
2. Buka **Detail** order cutting berstatus *Berjalan* → isi **Kain terpakai** & **Potongan jadi**,
   centang gulungan → **Catat Progres**. Perhatikan toast *"Nilai kain keluar Rp … | HPP potongan
   Rp …/pcs"* dan dua kolom baru di Riwayat Progres.
3. Catat progres KEDUA sesudah harga kain berubah ⇒ kolom HPP potongan berbunyi *"… dari Rp …
   (rata-rata bergerak)"*.
4. `window.location.hash='cutting-panels'` → reload ⇒ kartu **Nilai Persediaan** & **Belum Bernilai**
   terisi; kalau ada sampah warisan, kartu **Potongan yatim** muncul + tombol **Bersihkan yang aman**.
5. Uji penjaga: `cancel` order cutting yang sudah *start* tetapi belum pernah progres ⇒ toast
   menyebut master potongannya ikut dibersihkan.

---
---


---

# 🤝 HANDOFF (Session #18 — **FASE G DITEGAKKAN**: setelan penomoran tidak lagi berbohong · D terbukti sudah selesai) ✅

Rincian & bukti: `plan.md` entri **SESI #18**, `memory/CHANGELOG.md` entri **[#18]**, gate baru
**INV-F25**. Seluruh suite: `bash scripts/gate.sh` → **43/43 PASS · 0 FAIL · 0 SKIP · HIJAU**.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **UKUR DULU sebelum membangun: ROADMAP bisa BASI.** Owner meminta "daftarkan Dashboard Marketing
   ke sidebar + sambungkan ke data hidup" — ternyata SUDAH selesai sesi #16 dan gate INV-F20 sudah
   hijau 8 invarian. Kalau langsung dikerjakan, satu sesi habis membangun ulang yang sudah jalan.
   **Sebelum menerima entri ROADMAP sebagai pekerjaan, jalankan gate/`grep` yang membuktikannya.**
2. **Setelan yang tidak ditegakkan lebih buruk daripada setelan yang tidak ada.** Layar Penomoran
   Dokumen menawarkan Otomatis/Manual untuk 49 jenis; hanya 2 yang menegakkannya. Owner memindah
   setelan, tersimpan rapi, tampil di layar — dan tidak terjadi apa pun. Kalau sebuah fitur baru
   hanya bisa dipasang di sebagian tempat, **buat sisanya MENGATAKANNYA** (badge "Otomatis saja")
   dan tolak di API, jangan biarkan tampak seolah berlaku.
3. **Menyembunyikan pilihan di layar TIDAK cukup.** API `PUT /api/admin/doc-numbering` tetap bisa
   dipanggil langsung, jadi penjagaannya harus ada di backend juga (di sini: mode ditolak untuk
   jenis tanpa `policy_enforced`, sementara FORMAT tetap boleh diubah).
4. **Satu koleksi+field bisa menampung DUA jenis dokumen.** `dewi_kasbon_requests.request_number`
   dipakai kasbon (KSB) DAN pinjaman (PIN). Tanpa kunci kedua, memindah kebijakan kasbon ikut
   memaksa pinjaman. Polanya sudah ada di repo: override `collection`/`field` (lihat
   `production_pos.po_number_maklon`).
5. **Kesalahan `search_replace` yang sama terulang lagi** (old_str berakhir newline, new_str tidak →
   dua baris kode menyambung). Terjadi 3× dalam dua sesi. **Selalu `python3 -m pyflakes <file>`
   sesudah menyentuh berkas Python.**

## YANG SUDAH SIAP DIPAKAI
- Gate **INV-F25** `scripts/verify_fase_g2_penomoran_ditegakkan.py` (7 invarian, self-cleaning) —
  terdaftar di `gate.sh` + daftar `skip_gate`.
- Komponen bersama `frontend/src/components/erp/docnum/DocNumberField.jsx`
  (+ `useDocNumberPolicy`, `docNumberPayload`) — pasang di form dokumen mana pun.
- `data/doc_number_registry.py` → penanda **`policy_enforced`** = sumber kebenaran "jenis mana yang
  modenya boleh diubah". Menambah jenis baru WAJIB: tandai + wire `issue_number` + pasang
  `<DocNumberField>` + daftarkan jalur tulisnya di `WRITE_PATHS` gate INV-F25 (G1 akan MERAH kalau
  hanya ditandai tanpa disambungkan — itu memang tujuannya).

## SISA PEKERJAAN
1. **41 jenis dokumen** masih "Otomatis saja" (pola menyambungkannya sudah terbukti, lihat di atas).
   Kandidat berikutnya yang sering dipakai: Surat Jalan Gudang, PR Pengadaan, Purchase Order,
   Jurnal Umum, Klaim Biaya Karyawan.
2. **F3/F4 (P1)** Rapikan 5 PDF tersering (SPP · Invoice · Slip Gaji · Picklist · SJ Vendor) ke pola
   `_pdf_data_table` (auto-wrap + penuh lebar halaman).

## CARA MENGUJI CEPAT (2 menit)
1. `admin@garment.com` / `Admin@123` → `window.location.hash='sys-doc-numbering'` → reload.
   Perhatikan: **8** jenis punya toggle Otomatis/Manual, **41** berbadge kuning **"Otomatis saja"**.
2. Set **Pengajuan Kasbon** → **Manual**. Lalu `window.location.hash='portal-kasbon'` → reload →
   **Ajukan** ⇒ kolom *"Nomor Pengajuan Kasbon * (manual)"* muncul dengan pola
   `KSB-{YYYY}{MM}-{SEQ:5}`. Isi nomor berpola bebas ⇒ DITOLAK dengan contoh yang benar.
   Klik tab **Pinjaman** ⇒ kolomnya berubah jadi terkunci (kebijakan PIN masih otomatis).
3. Kembalikan **Pengajuan Kasbon** ke **Otomatis** ⇒ kolom nomor terkunci & menampilkan nomor
   berikutnya (`KSB-202608-000xx`).

---
---

# 🤝 HANDOFF (Session #17 — **H-6b DITUTUP ⇒ FASE H 100%**: arus keluar Cutting berdokumen, stok tetap turun sekali) ✅

Sesi #17 melanjutkan #16 (H-7/H-8). Rincian & bukti: `plan.md` entri **SESI #17**,
`memory/CHANGELOG.md` entri **[#17]**, gate baru **INV-F24**.
Seluruh suite: `bash scripts/gate.sh` → **42/42 PASS · 0 FAIL · 0 SKIP · HIJAU**.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **Menambahkan dokumen turunan pada sebuah alur = MEWAJIBKAN semua alat uji alur itu ikut
   membersihkannya.** Gate INV-F22 membuat order+progres cutting lalu menghapusnya; ia dibuat
   SEBELUM H-6b, jadi dokumen "Pengeluaran Material" yang kini lahir dari progres itu TERTINGGAL
   YATIM dan menumpuk di layar Gudang **setiap kali gate dijalankan**. Sebelum menambah dokumen
   turunan, `grep` dulu siapa saja yang MENGHAPUS dokumen induknya. Sekarang dijaga **INV-F24 C14**
   dan bisa disapu `python3 scripts/cleanup_uji_h5_h6.py --apply` (menyapu berdasarkan BUKTI
   ke-yatiman — materialnya sudah terhapus, jadi tidak bisa dicari lewat awalan kode).
2. **Dokumen yang lahir berstatus `issued` membuka pintu belakang ke buku besar.** Semua penjaga
   MI lama memeriksa `status` (`draft`/`pending_approval`), jadi dokumen cutting otomatis lolos ke
   `POST /material-issues/{id}/post-to-gl` yang hanya mensyaratkan `status == 'issued'`. Satu klik
   admin = beban hantu (Dr WIP / Cr Persediaan) atas kain yang nilainya hanya BERPINDAH menjadi
   nilai potongan. Kalau menambah status/jalur baru, telusuri SEMUA endpoint yang menyaring
   berdasarkan status itu.
3. **Penjaga yang mengambil "elemen pertama di berkas" akan berbohong begitu ada elemen baru di
   atasnya.** `INV-F13._count_columns()` mengambil `<thead>` PERTAMA; sejak H-5/H-7 menambah tabel
   baru DI ATAS tabel utama, ia melaporkan "1 kolom" untuk tabel ber-11 kolom ⇒ merah tanpa satu pun
   cacat produk. Sekarang dianc*ar* ke `data-testid="<prefix>-table"`. **Anchor penjaga ke identitas,
   bukan ke urutan.**
4. **Jangan percaya "gate hijau di sesi lalu" sebagai bukti kode benar di container BARU.** Dua
   gate (INV-18 & INV-14) SELALU merah di container segar karena data DEMO, dan remedinya
   (`repair_selisih_ssot.py --apply --topup-fg`) hanya tertulis di HANDOFF lalu dijalankan MANUAL
   tiap sesi. Sekarang dipasang di `scripts/bootstrap.sh` bersama
   `scripts/seed_cmt_receipt_demo.py` (INV-F23 S8). **Kalau sebuah gate butuh langkah manual, itu
   milik bootstrap — bukan milik HANDOFF.**
5. **`search_replace` yang `old_str`-nya berakhir newline sementara `new_str` tidak akan MENYAMBUNG
   dua baris kode** (kejadian 2× sesi ini pada `rahaza_inventory_shared.py` & `cleanup_uji_h5_h6.py`;
   yang pertama menghasilkan `m_ids = ...    loc_ids = ...` dalam satu baris). Selalu
   `python3 -c "import ast;ast.parse(open(f).read())"` atau `python3 -m pyflakes <file>` sesudah
   menyentuh berkas Python — **`grep` bukan pemeriksa kode.**

## YANG SUDAH SIAP DIPAKAI SESI INI
- Gate **INV-F24** `scripts/verify_fase_h6b_cutting_issue.py` (**14 invarian**, self-cleaning) sudah
  terdaftar di `scripts/gate.sh` **dan** di daftar `skip_gate`.
- POC `test_core_h6b_cutting_mi.py` (**77/77**) — `--keep` untuk menyisakan data periksa di layar.
- `scripts/seed_cmt_receipt_demo.py` (`--cleanup` ikut merekalkulasi buku kuantitas job item —
  `create_receipt` menulis `$inc`, jadi menghapus dokumennya saja membuat INV-14 merah).
- `scripts/cleanup_uji_h5_h6.py` kini juga menyapu **dokumen `cutting_issue` YATIM**.
- `GET /api/rahaza/materials/{id}` (baru) — **HARUS tetap route TERAKHIR** di
  `routes/rahaza_inventory_materials.py`, karena `/materials/reorder-alerts` &
  `/materials/uom-options` adalah route LITERAL di berkas yang sama (dijaga C12 statik + C13 runtime).
- **Alat lint:** `ruff` **tidak** ada di `backend/requirements.txt` (ia alat pengembangan, bukan
  dependensi aplikasi — memasukkannya akan mengubah hash deps dan memaksa `pip install` ulang tiap
  bootstrap). Kalau butuh: `pip install -q ruff` lalu
  `python3 -m ruff check <file> --output-format=concise`. Gate resmi tetap memakai **pyflakes +
  oxlint** (`INV-LINT-01`), jadi temuan ruff bersifat laporan — kecuali berkas yang memang sudah
  dirapikan (H-7/H-8 kini 0 temuan; jangan biarkan naik lagi).

## SISA PEKERJAAN (urutan yang disarankan)
Fase H **tidak punya sisa**. Menurut `memory/ROADMAP.md`:
1. **D (P0)** Dashboard Marketing — komponennya ada tetapi tidak pernah didaftarkan di sidebar mana
   pun, dan angkanya belum dari data hidup.
2. **G (P1)** Penomoran dokumen **Auto/Manual per jenis dokumen** yang bisa diatur System Admin
   (SPP · CMT-RCV · SJ-RWK · Invoice · Kasbon).
3. **F3/F4 (P1)** Rapikan 5 PDF tersering (SPP · Invoice · Slip Gaji · Picklist · SJ Vendor) ke pola
   `_pdf_data_table`.

## CARA MENGUJI H-6b CEPAT (3 menit)
1. `admin@garment.com` / `Admin@123` → `window.location.hash='cutting-orders'` → reload.
2. Buka **Detail** order cutting berstatus *Berjalan* → isi **Kain terpakai** & **Potongan jadi**,
   centang salah satu **gulungan** → **Catat Progres**. Perhatikan toast: *"Dokumen Pengeluaran
   Material MI-… diterbitkan"*, dan kolom **"Dokumen keluar"** di Riwayat Progres terisi.
3. `window.location.hash='wh-material-issue'` → reload. Chip **Cutting (n)** → baris dokumen itu
   ada, kolom **Sumber** = badge *Cutting*, **Acuan** = nomor order cutting.
4. Klik ikon mata → panel cyan **"Dari Portal Cutting"** (gulungan `−qty (sisa n)` + alasan
   **"Tidak dijurnal"**). Perhatikan: **tidak ada** tombol Approve/Hapus untuk dokumen ini.
5. Uji keadaan data lama: hapus satu dokumen cutting di Mongo + `$unset material_issue_id` pada
   progresnya → buka `cutting-orders` → panel kuning **"… belum punya dokumen Pengeluaran
   Material"** muncul → tekan **Terbitkan dokumen** → panel hilang, stok TIDAK berubah.

---
---

# 🤝 HANDOFF (Session #16 — **H-7 + H-8 DITUTUP**: satu daftar surat jalan lintas sumber · empat pintu lama tak kosong) ✅

Sesi #16 melanjutkan #15 (H-5/H-6). Rincian & bukti: `plan.md` entri **SESI #16**,
`memory/CHANGELOG.md` entri **[#16]**, gate **INV-F23**.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **Route literal HARUS dideklarasikan sebelum route ber-parameter.** `GET /sources` diletakkan
   sebelum `GET /{sj_id}`; kalau tertukar, FastAPI menangkapnya sebagai `sj_id="sources"` dan
   endpoint baru akan 404 "Receipt/SJ not found" tanpa satu pun error di log.
2. **Helper bersama bisa menyimpan cacat halus untuk SEMUA dokumen.** `_pdf_data_table` memakai
   `leading` 9,5 pt untuk font 7,5 pt ⇒ tiap sel yang melipat tumpang tindih ±0,8 pt. Ditemukan
   hanya karena rekap baru diukur dengan pymupdf, bukan dilihat mata. Sekarang 10,8 pt.
3. **"Arahkan alias ke X" tidak selalu berarti X untuk semuanya.** `prod-cmt-packing` /
   `maklon-packing` mengerjakan PENERIMAAN FG (`cmt_receipts`), jadi diarahkan ke `da-cmt-receive`,
   bukan ke layar kirim material. Periksa koleksi yang dipakai modul sebelum mengarahkan pintu.
4. **Agregasi wajib dibuktikan READ-ONLY.** Gate INV-F23 S6 menghitung dokumen sebelum & sesudah
   memanggil daftar/rekap — lapisan "hanya menampilkan" mudah sekali berubah jadi penulis.

## SISA PEKERJAAN
- **H-6b** (satu-satunya sisa Fase H): Cutting menerbitkan dokumen **Material Issue**
  (`ref_type='cutting_issue'`) supaya seluruh arus keluar gudang tampil di satu daftar
  "Pengeluaran Material".
- Alat: `scripts/verify_fase_h7_h8_surat_jalan.py` (INV-F23), `scripts/verify_fase_h5_h6_roll.py`
  (INV-F22), `scripts/cleanup_uji_h5_h6.py` (sapu data uji, `--prefix` + `--apply`).

---

# 🤝 HANDOFF (Session #15 — **H-5 + H-6 DITUTUP**: gulungan kain lahir saat diterima, wajib ditunjuk saat dipotong) ✅

Titik berhenti sesi lalu = agent sedang MENAMBAH blok penerbitan roll di `routes/warehouse.py`
(`search_replace` berhasil) lalu memeriksa hasilnya dengan `grep`. Yang tidak terlihat di grep itu:
**importnya belum ada**. `python3 -m pyflakes backend/routes/warehouse.py` melaporkan 4 undefined
name (`fabric_rolls` ×2, `fabric_roll_engine`, `rolls_created`). Backend TETAP START, jadi
kerusakannya baru muncul saat orang menekan *Confirm Received* pada penerimaan kain → HTTP 500.
Rincian & bukti: `plan.md` entri **SESI #15**, `memory/CHANGELOG.md` entri **[#15]**.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **`grep` bukan pemeriksa kode.** Setelah menyisipkan pemanggilan modul baru, jalankan
   `python3 -m pyflakes <file>` — 4 baris rusak sesi lalu akan langsung terlihat. Nama global di
   Python dicari saat RUNTIME, jadi backend yang "hidup" bukan bukti kode itu jalan.
2. **Kontrak endpoint yang berubah bentuk wajib disapu pemanggilnya.** `GET /api/cutting/rolls`
   berubah dari ARRAY menjadi OBJEK `{items, roll_required, total_remaining, uom}`; layar
   `CuttingOrdersModule.jsx` (dua pemanggil) sudah diperbarui dan dibuat toleran terhadap kedua
   bentuk. Selalu `grep` pemanggil sebelum mengubah bentuk respons.
3. **Backend boleh membuang data layar diam-diam.** `create_receiving` tidak pernah menyimpan
   `item.rolls`, jadi sekeras apa pun layar dibuat, rincian gulungan tidak sampai ke DB. Kalau
   sebuah field baru diisi di layar, periksa jalur simpannya di backend baris demi baris.
4. **Uji yang memakai kode master tetap tidak bisa dijalankan dua kali.** Jalankan-ulang
   `test_core_h5_h6.py` sempat MERAH 2 kasus karena material `POC-KAIN-NOROLL` sudah punya
   gulungan dari jalankan sebelumnya (bukan bug produk). Kode material untuk kasus "belum punya X"
   sekarang di-stempel waktu.

## YANG SUDAH SIAP DIPAKAI SESI INI
- Gate baru **INV-F22** `scripts/verify_fase_h5_h6_roll.py` (15 invarian, self-cleaning) sudah
  terdaftar di `scripts/gate.sh` **dan** di daftar `skip_gate`.
- `scripts/cleanup_uji_h5_h6.py` — sapu data pembuktian (`POC-*`, `TEST-H5*`, `TEST-H6*`, `VFH5-*`)
  beserta gulungan/stok/ledger/GR/order cutting-nya (`--apply` untuk benar-benar menghapus).
- Sisa Fase H: **H-7** (Surat Jalan Gudang satu daftar cetak) · **H-8** (alias `cmt-progress`,
  `do-management`, `prod-cmt-packing`, `maklon-packing` → `prod-shipments-vendor`) ·
  **H-6b** (Cutting menerbitkan dokumen Material Issue `cutting_issue`).

---

# 🤝 HANDOFF (Session #11 — **F11 + F12 DITUTUP**: pratinjau impor per baris · berkas ekspor tidak boleh masuk toko yang salah) ✅

Titik berhenti sesi lalu = agent sedang MEMBACA `scripts/gate.sh` (baris 255–345) untuk mencari
tempat mendaftarkan gate berikutnya. Ternyata **F11 sudah selesai ditulis** (backend + layar +
penjaga) tetapi **penjaganya belum pernah dijalankan** dan **gate `INV-F11` belum terdaftar**.
Rincian & bukti: `plan.md` entri **SESI #11**, `memory/CHANGELOG.md` entri **[#11a]**.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **Fitur yang tidak punya entri gate = fitur yang boleh mati diam-diam.** Urutan wajib untuk
   setiap fitur: layar + `test_core_*` + **entri di `scripts/gate.sh`** (termasuk daftar
   `skip_gate`) + entri `plan.md`/`CHANGELOG.md`. Kalau salah satu hilang, sesi berikutnya akan
   menghabiskan waktu hanya untuk MENGUKUR apa yang sudah jadi.
2. **45 penjaga backend tidak bisa melihat "perubahan palsu".** Uji LAYAR menemukan
   `Waktu Pesanan Dibuat: 2026-08-05 10:15 → 2026-08-05 10:15` pada SETIAP baris (Mongo
   mengembalikan datetime **naive**, berkas menghasilkan datetime **ber-zona**; `aware == naive`
   selalu False). Akibat seriusnya: perubahan palsu memakan kuota `_DIFF_MAX` ⇒ perubahan NYATA
   terdorong ke "+N field lain". **Setiap pembanding "berubah/tidak" yang menyentuh waktu wajib
   lewat `_norm_dt()`.**
3. **Penjaga yang MENUDUH SALAH harus dipresisikan, bukan dilonggarkan.** Dua penjaga baru sesi
   ini sempat merah karena mencari testid yang dibuat DINAMIS (`import-plan-filter-${a.key}`).
4. **`testing_agent_v3` bisa gagal memilih `Select` Radix lalu menyimpulkan dari MEMBACA KODE.**
   Itu bukan bukti. Resep yang berhasil: klik trigger `[data-testid=…]`, tunggu 1,2 detik, iterasi
   `[role="option"]`, klik yang teksnya cocok. Skrip Playwright di tool screenshot berjalan di
   dalam fungsi **async** ⇒ **WAJIB `await`** (tanpa `await`, semua langkah "berhasil" tanpa
   pernah dijalankan).

## Yang berubah (file → alasan)
| File | Perubahan |
|---|---|
| `backend/routes/marketing_data_import.py` | **`_norm_dt()` BARU** dipakai `_same()` ⇒ perubahan palsu pada semua kolom waktu hilang; catatan jujur "tidak ada nilai yang berubah" akhirnya muncul |
| `test_core_f11_pratinjau_impor.py` | 36 → **47 penjaga**: `A-9`/`A-10` (janji layar + `total` dari server), `E-2b` (CSV memuat NILAI, bukan hanya judul), `F-1..F-6` (penyaring & halaman jujur), `B-12`/`B-13` (perubahan palsu & baris tanpa perubahan) |
| `scripts/gate.sh` | gate **INV-F11** (+ entri SKIP saat backend/auth mati) |
| `plan.md` · `memory/CHANGELOG.md` · `test_result.md` | entri sesi #11 |

## Cara menguji cepat (3 menit)
1. `admin@garment.com` / `Admin@123` → `window.location.hash='marketing-import'` → reload.
2. Jenis **"Pesanan Marketplace (ekspor Seller Center)"** → toko **Shopee** (mis. *Shopee Daluna* —
   berkas contoh berplatform Shopee; memilih toko TikTok akan DITOLAK, itu fitur) → Lanjut.
3. Unggah `samples/ekspor_A_pesanan_contoh.csv` → **Unggah & periksa** → **Lanjut** di pemetaan.
4. Langkah 5: panel **"Apa yang akan berubah kalau Simpan ditekan"** ⇒ chip «semua 4 · 4 baru»,
   tabel 5 kolom, tombol **Unduh rencana (CSV)**. Klik chip, cari `DEMO-A-1001` ⇒ 1 baris.
5. Simpan ⇒ ulangi alur yang sama ⇒ ganti **"Kalau baris sudah ada"** menjadi **Perbarui yang
   lama** ⇒ chip berubah jadi **4 diperbarui** dan kolom "yang berubah" TIDAK boleh memuat
   pasangan nilai yang sama (kalau muncul, `_norm_dt` rusak).
6. Bersihkan dengan tombol **"Batalkan impor"** di Riwayat impor (jangan hapus di Mongo).

## ✅ FASE 2 SESI INI JUGA SELESAI — **F12: berkas ekspor tidak boleh masuk toko yang salah**

Diukur atas 22 jenis data: penjaga toko yang ada (`platform_guard` + `shop_guard`) ternyata
hanya menempel pada **satu** jenis (`marketplace_orders`). **Ekspor B/C** dan **20 jenis lain**
sama sekali tidak punya sidik toko ⇒ berkas toko A bisa MASUK ke toko B tanpa satu pun galat,
dan untuk Ekspor B/C jawabannya hanya "3 baris ditolak: belum pernah diimpor" (benar, tetapi
menyembunyikan sebabnya ⇒ staf memilih jenis "Pesanan Marketplace" supaya "mau masuk" ⇒
pesanan HANTU).

Yang dipakai: **BUKTI, bukan dugaan** — `SourceType.identity` (nomor pesanan/komplain/URL
konten yang sudah tercatat pada toko LAIN) + `content_sha256` (berkas ber-isi sama persis yang
sudah disimpan ke toko lain). Jenis yang isinya MEMANG tanpa penanda toko terdaftar di
**`NO_IDENTITY_REASON` beserta alasannya** — memaksa semua jenis punya identity akan MENUDUH
SALAH (mis. statistik toko Shopee hanya berisi tanggal + kanal).

* `python3 test_core_f12_sidik_toko.py` → **28/28** (sabotase ⇒ 7 gagal, `B-7` menerima **200**).
* `bash scripts/gate.sh` → **30/30 HIJAU** (gate baru **INV-F12**).
* Layar: panel MERAH (mayoritas ⇒ Simpan MATI) + panel KUNING (minoritas/berkas identik ⇒
  tetap boleh disimpan). Terbukti lewat Playwright, 0 page error.

### ⚠️ PELAJARAN LINGKUNGAN YANG MAHAL (sesi ini)
Dua `search_replace` **paralel pada berkas yang SAMA** (`scripts/gate.sh`) melahirkan korupsi
**SENYAP**: entri gate F12 hilang + 44 baris terakhir terduplikasi setengah jalan
(`ODUK — payslip karyawan"…`). `bash` menyembunyikannya karena `exit $OVERALL` jalan sebelum
sampahnya terbaca ⇒ gate melapor "29/29 HIJAU" padahal gate ke-30 tidak pernah ada.
**Selalu `bash -n scripts/gate.sh` sesudah menyentuhnya, dan JANGAN pernah dua edit paralel
pada satu berkas.**

## BERIKUTNYA (urutan yang disarankan)
1. **Fase 3 — konsolidasi layar non-marketing** (Produksi/Gudang/Keuangan) memakai pola tabel
   F10 (`scripts/_audit_ui_tables_v2.py` untuk mengukur ulang).
2. **F9 Settlement** masih menunggu berkas Pencairan ASLI owner; kalau tetap dikerjakan, WAJIB
   tanpa menebak format (pemetaan kolom oleh staf + label "pemetaan belum diverifikasi").
3. **Rapikan 3 toko DEMO** (`SHOPEE-OFFICIAL`, `SHOPEE-RESELLER`, `TIKTOK-STORE`): tidak muncul
   di pemilih toko layar karena `MarketingAccountSelect` menyaring `status=active` sementara
   dokumen DEMO tidak punya field itu. Akibatnya uji LAYAR tidak bisa memakai toko DEMO.

---

# 🤝 HANDOFF (Session #10 — **F6 DITUTUP TUNTAS**: lingkup toko per pemakai sampai ke kartu ringkasan) ✅

Sesi #9 menulis kode F6 dan layar Jejak Perubahan, tetapi hanya BACKEND-nya yang pernah diuji. Uji
LAYAR sesi ini menemukan kebocoran yang 50 tes backend tidak bisa melihat: kartu **"Marketing
Overview"** memanggil 6 ringkasan yang tak pernah masuk daftar penjaga F6 ⇒ staf **tanpa toko**
membaca **omzet Rp 57,6 jt, 559 pesanan, 9 akun**. Rincian & bukti: `plan.md` entri **SESI #10**,
`memory/CHANGELOG.md` entri **[#10a]**.

## ⚠️ PELAJARAN YANG JANGAN DIULANG
1. **Tes backend yang hanya menguji endpoint YANG DIDAFTAR akan selalu ketinggalan.** Karena itu
   sekarang ada **`B2-SWEEP`** di `test_core_f6_rbac_scope.py`: ia MENEMUKAN sendiri setiap
   `@router.get` di `backend/routes/marketing_*.py` dan menguji dengan dua token (staf tanpa toko vs
   admin). Endpoint baru yang lupa discope ⇒ gate MERAH tanpa perlu diingat siapa pun.
2. **Endpoint acuan/konfigurasi yang SAH sama** harus terdaftar di `SCOPE_EXEMPT` **beserta
   alasannya** (dijaga `B2-DAFTAR`). Pengecualian tanpa alasan = aturan yang hilang.
3. **Menutup kebocoran melahirkan cacat kedua:** angka 0 tanpa penjelasan. Pakai
   `NoStoreScopeNotice` (panel MENETAP) untuk setiap layar marketing baru.
4. **Penjaga yang "sama-besar ⇒ bocor" itu naif.** Bukti lingkup yang sah = keadaan **nol toko**
   (pas `B0`). Jangan melonggarkan penjaga; tambahkan keadaan yang tidak bisa ditafsir dua arti.

## Yang berubah (file → alasan)
| File | Perubahan |
|---|---|
| `test_core_f6_rbac_scope.py` | 51 → **100 penjaga**: pas `B0` (staf 0 toko), `B2-SWEEP` 109 endpoint + `SCOPE_EXEMPT` beralasan, `C-18/19` alasan angka, `C-20` kebisingan jejak, `D-9..D-12` |
| 13 berkas `backend/routes/marketing_*.py` | 24 endpoint DAFTAR/RINGKAS memakai `_scope.scope_filter` / `visible_account_ids` / `visible_accounts` |
| `routes/marketing_targets.py` · `marketing_budget.py` | `reason` opsional ⇒ masuk `marketing_change_log` |
| `routes/marketing_change_log.py` | `_diff` membuang perubahan `kosong → kosong` |
| `marketing/NoStoreScopeNotice.jsx` (BARU) · `MarketingOverviewDashboard.jsx` · `MarketingChangeLogModule.jsx` · `pickers/MarketingPickers.jsx` | nol yang menjelaskan diri + `NaN` → `—` |
| `CycleView.jsx` · `AccountTargetsModule.jsx` · `BudgetAllocationTab.jsx` | kolom **Alasan perubahan** (opsional) |
| `scripts/seed_marketing_change_log_demo.py` (BARU) + `scripts/bootstrap.sh` | environment segar punya 16 baris jejak (2 pelaku · 6 kewenangan) & staf demo pemegang toko |
| `memory/test_credentials.md` | akun `stafnia@` (2 toko, salah satunya BERDATA) & `stafrio@` |

## Cara menguji cepat (2 menit)
1. `admin@garment.com` / `Admin@123` → `window.location.hash='marketing-change-log'` → reload ⇒
   16 baris dengan **nilai lama → baru** + alasan; centang "Hanya perubahan kewenangan" ⇒ 6 baris.
2. `staffmkt@dewiaditya.id` / `Dewi@123` → `hash='marketing-reports'` ⇒ semua kartu **0** +
   panel kuning "Belum ada toko yang di-assign kepada Anda … minta **SPV Marketing**".
3. `stafnia@dewiaditya.id` / `Dewi@123` → `hash='marketing-reports'` ⇒ angka TOKONYA muncul
   (dia memegang TikTok Outfit Boutique yang berdata) dan panel kuning TIDAK muncul.
4. Admin → `hash='marketing-targets'` → tab **Siklus Bulan Ini** → tombol **Target** ⇒ ada kolom
   **"Alasan perubahan (opsional, masuk jejak)"**; simpan lalu cari alasannya di Jejak Perubahan.

## BERIKUTNYA (urutan yang disarankan)
1. **F10 — konsolidasi layar marketing**: `python3 scripts/_audit_ui_tables_v2.py` masih menandai
   beberapa modul **KARTU-SAJA**; ubah jadi tabel nyata (cari/sort/paginasi/CSV) lalu ukur ulang.
2. **Kualitas impor**: pratinjau "apa yang akan berubah" **per baris** sebelum commit.
3. **F9 Settlement tetap TIDAK boleh dimulai** sampai berkas Pencairan/Settlement ASLI dari owner ada.

---

# 🤝 HANDOFF (Session #8b — **F8 SELESAI**: Assign Toko · Ingat Pemetaan · Scorecard Kreator) ✅

Ketiga fitur yang diminta user **sudah ada rintisannya sebelum sesi ini**; yang dikerjakan adalah
melengkapi hal-hal yang membuatnya bisa dipercaya + menutup **satu cacat nyata**. Detail & bukti:
`plan.md` entri **SESI 2026-08-14 (#8b)**.

## ⚠️ CACAT YANG DITUTUP (jangan diulang)
`test_core_f7_kpi_impor.py` dulu membersihkan `marketing_change_log` **per `account_id`**. Toko
ujinya adalah **toko shopee aktif pertama = toko NYATA**, jadi setiap `bash scripts/gate.sh`
memusnahkan seluruh riwayat “siapa memegang toko ini”. **ATURAN: gate hanya boleh menghapus dokumen
BERTANDA gate.** Dijaga penjaga statik `A-2e` di `test_core_f8_assign_ingat_scorecard.py`.

## Yang berubah (file → alasan)
| File | Perubahan |
|---|---|
| `backend/routes/marketing_account_assign.py` | `reason` WAJIB (≥4 huruf, 400 + contoh) · `GET /by-staff` · `GET /history` (global, paginasi) · staf NONAKTIF ditandai + `warnings[]` · `unassigned_count`/`stale_count` |
| `backend/routes/marketing_data_import.py` | `format_memory` di respons unggah · pemetaan tersimpan divalidasi terhadap skema (`dropped[]`) · `GET /formats` · `DELETE /formats/{fingerprint}` |
| `backend/routes/marketing_targets.py` | `GET /creator/{id}/detail` (konten/pesanan/sesi + total yang wajib sama dengan scorecard) + catatan **PERLU KEPUTUSAN** status `returned` |
| `frontend/.../AccountAssignView.jsx` | 3 tampilan (Per Toko/Per Staf/Riwayat), cari+filter+paginasi, Simpan terkunci tanpa alasan, panel akibat MENETAP |
| `frontend/.../DataImportWizard.jsx` | panel “Pemetaan DIINGAT” + “Lupakan pemetaan ini” + dialog daftar format (juga dari langkah 3) |
| `frontend/.../CreatorScorecardView.jsx` | dialog rincian (4 kartu + 3 tab), paginasi, pencarian, unduh CSV, CTA target |
| `backend/scripts/seed_marketing_creator_demo.py` | seeder demo kreator/konten/sesi/target (idempoten) + dipanggil `scripts/bootstrap.sh` |
| `test_core_f8_assign_ingat_scorecard.py` · `scripts/gate.sh` | 34 penjaga baru + gate **INV-MKTOPS** |

## Cara menguji cepat
1. `admin@garment.com` / `Admin@123` → `window.location.hash='marketing-accounts'` → reload → tab
   **Assign Staf**: 3 tampilan; klik “Atur staf” ⇒ **Simpan terkunci** sampai alasan diisi; sesudah
   disimpan muncul panel akibat MENETAP; tab **Riwayat** memuat barisnya.
2. `hash='marketing-import'` → jenis **Ekspor B & C** → toko Shopee Official Store DEMO → langkah 3
   ada tautan “Lihat / lupakan pemetaan yang diingat” → unggah
   `samples/ekspor_B_status_dikirim_contoh.csv` ⇒ panel **“Pemetaan ini DIINGAT …”** (kalau belum
   muncul: commit sekali, lalu unggah berkas yang sama).
3. `hash='marketing-content-calendar'` → tab **Scorecard Kreator** → tombol **“Lihat asalnya”** ⇒
   dialog rincian (Konten/Pesanan/Sesi). Kreator **Sinta Affiliate** sengaja tanpa target.

## PEKERJAAN TERSISA (jujur)
1. **PERLU KEPUTUSAN PEMILIK:** pesanan berstatus **`returned` masih dihitung sebagai omzet**
   (`core/marketing_cycle.EXCLUDED_FOR_REVENUE = ('cancelled',)`). Mengubahnya menyentuh F2+F5+F7.4
   sekaligus ⇒ wajib kartu kerja sendiri + gate, bukan tambalan satu layar.
2. Berkas **Ekspor B & C ASLI** masih dibutuhkan untuk melepas label “pemetaan perlu diperiksa”.
3. `scripts/seed_marketing_demo.py` (seeder LAMA) menulis `peak_viewers` tanpa `viewers` ⇒ kolom
   “Penonton” 0 untuk datanya. Rapikan bila seeder itu dipakai lagi.
4. **JANGAN** edit `search_replace` paralel pada FILE yang sama. Setiap perubahan `frontend/src`
   **wajib** `bash scripts/rebuild_frontend.sh` (preview memakai bundel statis).

---

---

> ⚡ **SETUP CEPAT (BACA DULU):** `/app` datang sebagai template kosong. Ikuti `/app/AGENT_QUICKSTART.md`:
> `rsync` clone repo → `/app` (**--exclude='.env'**, jangan timpa env platform) lalu
> `EMERGENT_LLM_KEY=sk-... bash /app/scripts/bootstrap.sh`.
> **Catatan dari sesi #8:** pod bisa **restart di tengah `yarn build`** — akibatnya seed TIDAK jalan
> dan DB kosong (`marketing_platform_accounts` = 0) padahal login admin sukses. Cek cepat:
> `mongo count` untuk `rahaza_employees`; kalau 0 ⇒ jalankan `bash scripts/bootstrap.sh --skip-deps`
> (idempoten, ~41 detik, deps & build tidak diulang).

# 🤝 HANDOFF (Session #8 — **F3 SELESAI**: Ekspor B/C + “Batalkan impor” yang menepati janji) ✅

**Sesi sebelumnya berhenti DI TENGAH EDIT LAYAR.** `DataImportWizard.jsx` sudah memuat JSX penolong
pemetaan, tetapi `sampleFor()` dan `unmappedCols` **belum pernah didefinisikan** ⇒ langkah
“Pemetaan kolom” **pasti crash** (ReferenceError). Itu ditutup lebih dulu, lalu seluruh sisa kartu
F3 (F3.D … F3.K) diselesaikan. Rincian lengkap + bukti: `plan.md` entri **SESI 2026-08-14 (#8)**.

## Yang berubah (file → alasan)
| File | Perubahan |
|---|---|
| `frontend/src/components/erp/marketing/DataImportWizard.jsx` | `sampleFor`/`unmappedCols`/`requiredHints`/`pendingSuggestions`; panel field WAJIB dengan tombol **“pakai kolom «X» (98%)”**; layar HASIL khusus `update_only`; Riwayat: kolom **Diperbarui**, tombol **“Batalkan & pulihkan”**, dialog **pratinjau pembatalan** + dialog **Laporan pemulihan** (menetap) |
| `backend/core/marketing_import_engine.py` | `auto_map()` mencatat pilihan mesin sebagai **usulan #1** (`_cand_list`) — usulan tidak hilang saat staf melepas kolom |
| `backend/routes/marketing_data_import.py` | `_commit_message()` (kalimat hasil yang menyebut arti angka) + respons commit `update_only` & `undo_count` |
| `test_core_f3_fulfillment.py` | +3 penjaga `F3-M8/M9/M10` ⇒ **55/55 PASS** (dibuktikan MERAH saat fitur dilepas: 53/55) |
| `scripts/gate.sh` | gate baru **INV-MKTFULFILL** (+ entri SKIP saat backend mati) |
| `memory/SSOT_KONTRAK_DATA_2026-08-12.md` | §PEMULIHAN IMPOR — kontrak koleksi `marketing_data_import_undo` |
| `samples/ekspor_{A,B,C}_*.csv` | berkas contoh siap-pakai untuk staf & agen uji |

## Cara menguji cepat (2 menit, tanpa menebak)
1. Login `admin@garment.com` / `Admin@123` → `window.location.hash='marketing-import'` → reload.
2. Kartu **“Pesanan Marketplace (ekspor Seller Center)”** → toko **Shopee Official Store DEMO** →
   unggah `samples/ekspor_A_pesanan_contoh.csv` → commit (4 pesanan masuk).
3. Kartu **“Status Pengiriman / Pembatalan (Ekspor B & C)”** → toko yang sama →
   unggah `samples/ekspor_B_status_dikirim_contoh.csv`.
   * Langkah 4: kolom **“Contoh isi”** harus terisi. Set “Order Status” ⇒ *— tidak dipakai —* ⇒
     panel merah + tombol **“pakai kolom «Order Status» (98%)”** dan “Lihat pratinjau” **terkunci**.
   * Commit ⇒ **Diperbarui 2 · Ditolak 1 · Baris masuk 0** (0 diberi keterangan) · **Bisa dipulihkan 2**.
4. **Riwayat impor** → tombol **“Batalkan & pulihkan”** ⇒ dialog menyebut **2 pesanan** ⇒ konfirmasi ⇒
   **Laporan pemulihan** terbuka; baris riwayat berubah menjadi *dibatalkan* + tombol
   **“Laporan pemulihan”** (bisa dibuka lagi kapan pun).
5. `samples/ekspor_C_batal_retur_contoh.csv` untuk menguji kejujuran terminal: pesanan yang jadi
   **batal/retur** hanya field-nya yang dipulihkan (status TIDAK dihidupkan — reservasi stok sudah
   dilepas), dan laporannya **menyebut nomor pesanannya**.

## PEKERJAAN TERSISA (jujur)
1. **Label “pemetaan perlu diperiksa” pada Ekspor B/C belum boleh dilepas** — pemetaannya disusun
   dari bentuk Ekspor A. Butuh **berkas Ekspor B & C ASLI dari owner** untuk verifikasi.
2. (selesai) `mapping_unverified` kini berganti kalimat di layar HASIL: “Hasil di atas memakai
   pemetaan yang BELUM diverifikasi” + jalan keluarnya.
3. Sisa 3 tugas user sesi #7: Impor KPI Shopee **sudah ada**; periksa kelengkapan **layar Assign Toko (SPV)**
   dan **Scorecard Kreator**.
4. **JANGAN** edit `search_replace` paralel pada FILE yang sama (race). Setiap perubahan
   `frontend/src` **wajib** `bash scripts/rebuild_frontend.sh` (preview memakai bundel statis).

---

# 🤝 HANDOFF (Sesi 2026-08-13 #6 — F4 diverifikasi + **F5 SIKLUS SELESAI**) ✅ TERVERIFIKASI

> **BACA URUT**: file ini → `/app/plan.md` (entri sesi paling atas) → `/app/test_result.md` (blok
> paling bawah) → `/app/memory/CHANGELOG.md` (entri teratas). Handoff sesi lama ada di bawah (arsip).

## PERMINTAAN USER & HASIL
*"lanjutkan development dari repo ini … titik berhenti di search_replace moduleRegistry (F4.4) lalu
rebuild. **verifikasi**, jika memori di container ini besar mungkin jangan dengan static build —
keputusan saya serahkan pada anda."*

**Jawaban yang diukur, bukan ditebak:** `cpu.max = 100000 100000` (**kuota 1 core**) ·
`memory.max = **2 GiB**` (angka 62 GiB dari `free -h` itu memori HOST). ⇒ **STATIC BUNDLE
DIPERTAHANKAN.** Dev server CRA (567 berkas) membuat health probe platform gagal ⇒ pod restart
berulang ⇒ preview tak pernah menyala. Tiap ubah `frontend/src`: `bash scripts/rebuild_frontend.sh`.

F4 **terbukti 6/6** (36/36 core + 21 kolom & pengalih di layar + redirect `toko-products`), lalu
**F5 dikerjakan tuntas**: satu layar siklus target → anggaran → omzet, realisasi anggaran OTOMATIS,
kunci periode (423), dan peringatan.

## 4 HAL YANG WAJIB DIINGAT
1. **`core/marketing_cycle.py` adalah SATU-SATUNYA rumus angka siklus.** Layar Marketing, layar
   Manajemen, notifikasi, dan CSV memakai fungsi yang sama. Kalau menambah pembaca baru, JANGAN
   menghitung ulang target/capaian/anggaran di tempat lain — itu cara paling cepat melahirkan
   "tiga kesimpulan untuk satu bulan" yang baru saja ditutup.
2. **Realisasi anggaran otomatis TIDAK PERNAH ditulis** ke `marketing_spend_entries`. Ia dihitung
   saat dibaca dan membawa `evidence`. Menuliskannya = dobel-hitung begitu staf mencatat manual.
   Kategori `komisi` BARU; daftar kanoniknya `_cycle.CATEGORIES` (jangan bikin daftar kedua).
3. **`marketing_orders` menampung DUA bentuk dokumen** (impor Seller Center vs input manual). Uang
   pesanan WAJIB dibaca lewat `core/marketing_daily_rollup.order_revenue_product / order_amount_of /
   order_revenue_gross / order_seller_discount / item_qty / item_revenue`. Membaca `revenue_product`
   langsung akan memberi **Rp 0** untuk pesanan yang diinput staf — cacat yang baru ditutup sesi ini.
4. **Kunci periode memakai HTTP 423** (bukan 403) dan dipasang di 5 jalur tulis termasuk commit
   impor. Kalau menambah jalur tulis baru yang menyentuh bulan tertentu, panggil
   `_cycle.assert_period_open(db, account_id, period_atau_tanggal, action='…')` SEBELUM menulis.

## BUKTI
- `python3 test_core_f5_siklus.py` → **58/58 PASS** (559 pesanan · omzet produk Rp 59.783.811 ·
  order amount Rp 62.805.113 · diskon auto Rp 48.020.983 tanpa entri manual · 423 di 5 jalur ·
  flag · overview = Σ baris · marjin menjoin HPP katalog).
- `python3 scripts/verify_marketing_cycle.py` (**gate baru INV-MKTCYCLE**) → **31/31 HIJAU**;
  CYC-3 membuktikan kunci dengan pelanggaran sintetis, CYC-8 membuktikan rantai
  pesanan manual → rekap harian → siklus (termasuk omzet kembali turun saat pesanan dihapus).
- `bash scripts/gate.sh` **22/22 VERDICT HIJAU** · `gate_marketing_ssot` 10/10 ·
  `verify_marketing_scope` 32/32 · `check_nav_map` HIJAU (guard **NAV-ALIAS** baru).
- `test_core_f4_katalog.py` 36/36 · `test_core_f1_f2_omzet.py` **59/59** (tidak ada regresi).
- testing agent **iter_53** (F5①②③) & **iter_55** (F5④⑤⑥⑦⑧ + F4①②) — **10/10 PASS**, 0 bug.
  Angka Portal Marketing & Portal Manajemen terbukti **identik** untuk bulan yang sama.

## BERIKUTNYA (urutan yang disarankan)
1. **F6 — RBAC per toko + jejak perubahan.** `marketing_change_log` sudah LAHIR di F5 (kunci periode,
   target, anggaran); yang belum: `visible_account_ids(db, user)` + `assert_account_visible()` di
   ~30 endpoint daftar/ringkas, 4 role baru, dan **layar** "siapa mengubah target bulan lalu".
   Catatan: `core/marketing_account_scope.py` yang ada menjaga lingkup **data**, bukan **visibilitas
   per pemakai** — jangan tertukar.
2. **F7 — Konten & Content Creator** (field pemilik konten/link terbit/KPI + jenis impor
   `content_performance` + laporan performa kreator).
3. **F10 — konsolidasi**: `_audit_ui_tables_v2.py` (kini sudah jujur soal komponen anak) masih
   menandai beberapa modul marketing KARTU-SAJA; `TokoProductCatalogModule.jsx` sudah boleh DIHAPUS
   karena redirect F4.4 terbukti bekerja.
**Menunggu berkas owner:** BD-1 (Ekspor B/C) · BD-2 (Settlement, F9 tidak boleh dimulai) ·
BD-3 (`shop_kpi`) · BD-4 (Shopee Orders) · BD-5 (koreksi 9 toko).

## MENJALANKAN CEPAT DI ENVIRONMENT BARU
```bash
cd /tmp && rm -rf da && git clone --depth 1 <repo> da && \
  rsync -a --exclude='.env' --exclude='.git' --exclude='node_modules' /tmp/da/ /app/
EMERGENT_LLM_KEY=sk-emergent-... bash /app/scripts/bootstrap.sh
cd /app/backend && python3 scripts/seed_marketing_real_accounts.py --apply
cd /app && python3 scripts/seed_internal_variants.py && python3 scripts/seed_katalog_order_demo.py
cd /app && python3 scripts/seed_marketing_cycle_demo.py     # data demo layar Siklus (F5)
```

---


# 🤝 HANDOFF (Sesi 2026-08-11 #3 — F0.7 **LAYAR** Manajemen Akun Toko) ✅ TERVERIFIKASI

> **BACA URUT**: file ini → `/app/plan.md` (entri sesi paling atas) → `/app/test_result.md` (blok
> paling bawah) → `/app/memory/CHANGELOG.md` (entri teratas). Handoff sesi lama ada di bawah (arsip).

## PERMINTAAN USER & HASIL
*"Backend F0.7 selesai. Sekarang UI-nya (Manajemen Akun) supaya field baru bisa diisi & dilihat."*
`frontend/src/components/erp/AccountManagementModule.jsx` **ditulis ulang**: **Tabel (default) 16 kolom
+ toggle Kartu + paginasi 10/hal**, form buat/edit mengisi **semua** field F0.7 lewat dropdown COA
(`kode · nama`), PIC kini bisa diisi **sejak pembuatan**, badge/aksi BD-5 "perlu ditinjau".

## 3 HAL YANG WAJIB DIINGAT
1. **Akun COA piutang per toko itu OTOMATIS.** `POST /api/marketing/accounts` memanggil
   `ensure_subledger_for_entity(db,'channel',…)` ⇒ akun `1-220-<KODE>` ("Piutang Channel — <toko>")
   dibuat & kodenya ditulis ke `ar_account_code`. **Skrip seed yang menulis langsung ke DB melewati
   jalur ini** — itu sebabnya 9 toko nyata dulu tidak punya akun buku besar sendiri. Sudah diperbaiki:
   `backend/scripts/backfill_marketing_channel_subledger.py --apply` (idempoten) + `seed_marketing_real_accounts.py`
   kini memanggilnya sendiri. **Kalau menambah jalur pembuatan toko baru, panggil helper itu.**
2. **Validasi COA harus soal PERAN, bukan sekadar "kode ada".** Bug nyata yang ditutup sesi ini:
   `9-000 BIAYA UMUM & ADMINISTRASI` (akun **grup beban**) lolos jadi "rekening pencairan" karena
   validasi lama hanya `find_one({'code': …})`. Sekarang `_validate_coa_role()` memakai
   `flags.is_sales/is_cash/is_bank/is_ar` + `is_group` + `active` (dengan mode longgar berbasis `type`
   bila bagan akun belum punya `flags`). **Pola yang sama layak dipakai di F9 (settlement) nanti.**
3. **Frontend = STATIC BUNDLE.** Setiap ubah `frontend/src` → `bash /app/scripts/rebuild_frontend.sh`
   (build ±3 menit; preview tetap menyajikan bundel lama sementara). Modul ini dibuka lewat
   `?portal=toko&module=marketing-accounts`.

## BUKTI
- `python3 scripts/test_core_f07_accounts_ui.py` → **57 PASS / 0 GAGAL** (HTTP nyata + verifikasi DB:
  subledger anak `1-220`, tautan `flags.subledger_entity_id`, 400 untuk COA palsu/grup/kontra/basis ngawur).
- `bash scripts/gate.sh` **21/21 HIJAU** · `gate_marketing_ssot.py` **10/10 HIJAU** ·
  `verify_marketing_scope.py` **32 PASS/0 FAIL** · `_audit_ui_tables_v2.py` modul ini `th=16`, `toggle=true`,
  **keluar dari daftar KARTU-SAJA**.
- testing agent iterasi **45 & 46** (backend 9/9 + UI baca/tampilan) **plus** verifikasi Playwright oleh
  main agent untuk alur TULIS lewat layar: buat akun (toast memuat `1-220-MAIN-QA-01`), edit (4-124/1-131/
  gudang/shop id/status tersimpan), kode duplikat ⇒ toast error & dialog tetap terbuka, arsip ⇒ Nonaktif.
  Semua akun uji sudah dibersihkan; DB kembali **12 akun** (9 toko nyata + 3 demo).

## BERIKUTNYA (F0 belum selesai)
F0.1–F0.6: registry koleksi + `gate_marketing_ssot` diperluas · rekap harian **turunan** dari pesanan ·
hapus total 2 mesin impor lama + 3 berkas UI-nya · migrasi dokumen datar · indeks unik.
**BD-5 masih terbuka:** owner perlu mengoreksi nama/username/PIC/rekening 9 toko (badge "perlu ditinjau"
di layar; tombol centang menutup penanda itu).

---


# 🤝 HANDOFF (Session #28 — F12 perbandingan Rekap Mingguan CMT + F13 satu master vendor CMT) ✅ TERVERIFIKASI

> **BACA URUT**: file ini → `/app/plan.md` (bagian **5) Status Penyelesaian**) → `/app/test_result.md`
> (bagian akhir) → `/app/memory/CHANGELOG.md` → `/app/DOCS_INDEX.md`. Handoff sesi lama ada di bawah (arsip).

## APA YANG SELESAI SESI INI (Phase 3 dari plan.md: F12 + F13)

### F12 — Rekap Mingguan CMT: perbandingan antar-pekan
- Penjadwal **16:00 WIB** reminder Rekap Harian sudah ada sebelumnya (`utils/scheduler.py` →
  `job_cmt_daily_recap_reminder`, idempoten lewat SSOT `send_recap_reminders`).
- **BARU di `core/cmt_daily_recap.py`**: `movers` (papan "vendor yang bergerak") +
  `_vendor_direction()` + `_vendor_compare_basis()`. **Peringkatnya diputuskan di backend**, bukan di
  browser — kalau layar mengurutkan sendiri, export Excel/PDF akan menunjuk vendor "terburuk" yang
  BERBEDA di rapat yang sama.
- **Keputusan kejujuran yang WAJIB dipertahankan**: vendor yang tidak punya pekerjaan di salah satu
  pekan **TIDAK diperingkat** (`direction='incomparable'` + `incomparable_reason`). Kalau ikut
  diperingkat, vendor yang pekan lalu tidak DIBERI order selalu tampil "paling membaik" dan yang
  pekan ini tidak diberi order tampil "paling memburuk" ⇒ memuji/menuduh vendor atas keputusan order
  KITA. Gate **RK-35** menjaga ini.
- **Frontend `CMTOverrideWeeklyRecap.jsx`**: kartu delta · papan memburuk/membaik (baris bisa DIKLIK
  → membuka vendor) · kolom tabel **"vs pekan lalu"** · filter **"Hanya yang memburuk"** (ikut lepas
  otomatis saat tombol perbandingan dimatikan).
- **BUG DIPERBAIKI**: `load(end)` sesudah kirim reminder tidak meneruskan `compare` ⇒ panel yang
  sedang dibuka HILANG sendiri tepat setelah staf menekan tombol.
- **Lampiran ikut membawa perbandingan**: `/weekly-recap/export?compare=true` (Excel dapat lembar
  **"Perbandingan"**). Legenda layar berbunyi "Excel/PDF isinya sama dengan layar ini", dan yang
  dibawa ke rapat justru lampirannya.
- Gate **INV-REKAP 34 → 40 kode**: **RK-31** (compare tidak menggeser angka jendela berjalan) ·
  **RK-32** (jendela pembanding bersebelahan & sama panjang) · **RK-33** (delta = now−prev, arah
  warna dari backend) · **RK-34** (per-vendor sejajar dengan baris tabel) · **RK-35** (papan
  peringkat jujur) · **RK-36** (lampiran membawa perbandingan + biaya ≤ ~2,6× satu jendela).
  **Pola dua pekan DIBUAT SENDIRI oleh gate**, jadi RK-35 tidak bisa lulus dengan papan kosong.
- **BUG GATE DIPERBAIKI (penting)**: **RK-18** dulu memindai SEMUA reminder `daily_recap`
  bertanggal hari ini tanpa memandang vendornya. Artinya sejak penjadwal 16:00 WIB ada,
  `bash scripts/gate.sh` akan **MERAH setiap hari** sesudah jam 16:00 — dan gate yang merah karena
  sebab palsu adalah gate yang mulai diabaikan. Kini lingkupnya vendor uji + jejak `MARK`.
- **Data demo BARU**: `python3 scripts/seed_cmt_weekly_compare_demo.py` (idempoten, `--cleanup`):
  WCMBK CV Sinar Membaik (MEMBAIK) · WCMBR CV Surya Memburuk (MEMBURUK) · WCSTB CV Tetap Stabil
  (SAMA) · WCBRU CV Baru Masuk (TIDAK DIPERINGKAT).

### F13 — cleanup risiko lama
- **F13.1 kegagalan senyap jalur stok/uang.** Audit AST seluruh backend: dari 417 handler "tampak
  senyap", hanya **22** benar-benar membungkus I/O di jalur stok/uang; **8** yang berisiko nyata
  diberi log terstruktur (perilaku tetap NON-BLOCKING). Yang paling berbahaya:
  `core/production_qty_ledger.py` — lokasi KARANTINA gagal dibaca ⇒ dulu `qloc=None` diam-diam
  sehingga **stok karantina (reject) ikut dipakai memenuhi pengeluaran FG**. Sisanya: penomoran
  pembayaran CMT & nota kredit maklon jatuh ke nomor acak di luar urutan counters · posting jurnal
  kasbon gagal tanpa jejak · mesin persetujuan SSOT gagal ⇒ badge dashboard beda aturan dari inbox ·
  pembagi potongan LWOP diam-diam 22 hari · config tenggang CMT · alarm HPP-0 & digest aksesoris.
  Handler yang TIDAK diubah memang sah: body request opsional · retry `DuplicateKeyError` RC-5 ·
  `InsufficientStock` yang sudah dilaporkan ke pemanggil · helper konversi angka.
- **F13.2 satu master vendor pembayaran CMT.** Keadaan awal DIUKUR: `vendor_partners`=5,
  `dewi_cmt_partners`=4, **irisan id = 0**. Akibat nyata: halaman vendor Portal CMT menampilkan
  **outstanding Rp 0** padahal hutang jasa jahitnya ada · filter "per vendor" di layar Invoice
  MEMBUANG baris · bukti "diinput staf DA" menguap.
  **BARU `backend/core/cmt_vendor_master.py`** = SSOT penerjemah id (`alias_ids`, `payment_filter`,
  `canonical_id`, `canonical_map` versi batch 2-query). **Semua pembaca & penulis pembayaran CMT
  WAJIB lewat sini** — kalau menambah pembaca baru, JANGAN menulis `{'cmt_partner_id': vid}` lagi.
  `vendor_id` sekarang SELALU id `vendor_partners`; `cmt_partner_id` hanya cerminan kompatibilitas.
  Migrasi `scripts/migrate_unify_cmt_vendor_master.py` DIJALANKAN (irisan **0 → 9/9**) dan kini
  DIPASANG di `scripts/bootstrap.sh` supaya environment segar tidak melahirkan gate MERAH.
- **Frontend (kesenjangan ditutup)**: backend sudah bisa `?partner_id=` tapi layar Invoice tidak
  punya jalan memakainya. Ditambah dropdown **filter per Vendor CMT** + endpoint baru
  `GET /api/production/cmt-billing/vendors` (dikelompokkan per **ID** hasil SSOT, **bukan** per
  `cmt_name` — mengelompokkan per nama akan membelah hutang satu vendor jadi dua baris begitu
  ejaannya beda) + tombol Reset filter. Filter vendor & status digabung lewat `$and` supaya tidak
  saling menimpa.
- Gate: **INV-CMTVEN-1…4** di `verify_data_integrity.py` (scan SELURUH DB) + **OV-16** di
  `verify_cmt_override.py` (**pelanggaran sintetis DUA ARAH**). OV-16 sudah **DIBUKTIKAN MERAH**
  saat perbaikannya dilepas sementara ⇒ gate ini bukan hiasan.

## BUKTI (dijalankan, bukan dikutip)
- `bash scripts/gate.sh` → **20/20 PASS, VERDICT HIJAU**.
- `python3 scripts/verify_rekap_harian.py` → **40 OK / 0 FAIL**.
- `python3 scripts/verify_cmt_override.py` → **20 PASS / 0 FAIL**.
- `python3 scripts/verify_data_integrity.py` → **24 PASS / 0 FAIL**.
- `testing_agent_v3` iteration 41 (backend) **9/9 PASS** · iteration 42 (frontend) semua yang
  dijalankan LULUS, termasuk uji KRITIS "angka kartu delta == kartu ringkasan" (244==244, 16==16).
- Sisa uji layar yang di-block timeout sesi agent DITUTUP sendiri lewat Playwright dan LULUS
  (geser jendela dengan perbandingan menyala · pencarian+perbandingan · pelepasan filter otomatis ·
  vendor+status bersamaan di Invoice · dialog detail · klik kotak hari → tab Harian tanggal itu ·
  export xlsx+pdf terunduh saat compare menyala).
- Jejak data uji sesudah semuanya: `__REKAPTEST__` / `__CMTOVTEST__` / `POCRK` = **BERSIH**.

## JEBAKAN YANG HARUS DIINGAT AGENT BERIKUTNYA
1. **Frontend = STATIC BUNDLE** (`static_server.js`), BUKAN dev server. Sesudah mengubah
   `frontend/src` WAJIB `bash scripts/rebuild_frontend.sh`. JANGAN `yarn start`/`craco start`.
2. **`SmartNativeSelect` bukan `<select>` native.** Pola uji: klik `<testid>-trigger` lalu
   `<testid>-option-<value>`.
3. **Rate-limit login 10/60 detik** — login SEKALI, reuse sesi.
4. Laporan agent pernah menyebut modul `prod-cmt-billing` "navigation timeout". **TIDAK TERBUKTI**:
   diukur ulang modulnya memuat dalam **0,8 detik**. Itu batas tunggu skrip agent, bukan aplikasi.
5. Belum ada gate yang mencegah `except: pass` **BARU** masuk ke `routes/`/`core/`/`services/`
   (kandidat pekerjaan berikutnya — lihat `plan.md` bagian 6).

---

# 🤝 HANDOFF (Session #26 — FASE 5 `closed_at`: rekap tanggal lampau berhenti menebak) ✅ TERVERIFIKASI

> **BACA URUT**: file ini → `/app/plan.md` (bagian **FASE 5**, paling bawah) → `/app/memory/CHANGELOG.md`
> (entri paling bawah) → `/app/memory/PRD.md` → `/app/DOCS_INDEX.md`. Handoff sesi lama ada di bawah (arsip).

## APA YANG SELESAI SESI INI
- **Masalah yang ditutup:** rekap CMT menjawab "job jalan pada tanggal X" dari **status SEKARANG**
  ⇒ job yang dibuka Senin & **ditutup Rabu** HILANG dari rekap Senin ⇒ **kelalaian yang sudah
  terjadi terhapus sendiri**. Progress = dasar **tagihan CMT**, jadi laporan itu tidak bisa dipakai
  memverifikasi bantahan vendor.
- **BARU `backend/core/production_job_lifecycle.py`** = SSOT penutupan job:
  `JOB_CLOSED_STATUSES` · `close_job()` (**satu-satunya penulis `closed_at`**, idempoten, tutup
  pertama menang) · `was_open_at()` (dipakai rekap harian **dan** mingguan) ·
  `needs_closed_at_backfill()`.
- **DUA jalur penutup job WAJIB lewat `close_job()`**: auto-complete `routes/production_execution.py`
  (~baris 1063) + Quick Complete `routes/production_pos.py` (~baris 1198). **Kalau menambah jalur
  penutup KETIGA, pakai `close_job()`** — gate **RK-29** memeriksa SELURUH DB dan akan MERAH.
- **BARU `backend/migrations/add_closed_at_to_production_jobs.py`** — backfill job warisan dari
  `updated_at` (fallback `created_at`), ditandai `closed_at_estimated: True`; tanpa penanda waktu
  apa pun → **DILEWATI & dilaporkan**, tidak dikarang. Idempoten.
- **Kejujuran sampai ke layar**: `as_of_note` dipecah jadi `as_of_note_base` + **`legacy_note`**
  (`as_of_note` tetap utuh persis untuk export/API lama). FE menaikkannya jadi **peringatan amber**
  `cmt-recap-legacy-jobs` (Harian) & `cmt-week-legacy-jobs` (Mingguan). Sebelum ini tab **Mingguan
  tidak pernah menyebut** keterbatasan itu sama sekali.
- **Gate INV-REKAP 30 → 34 kode**: **RK-28** (tanggal sebelum penutupan tetap terhitung, sesudahnya
  tidak) · **RK-28b** (`closed_at`/`status` kiriman browser diabaikan) · **RK-29** (nol job tertutup
  tanpa `closed_at` di seluruh DB) · **RK-30** (job warisan diakui di layar harian+mingguan &
  `as_of_note` = base + legacy_note). Jumlah gate di `gate.sh` tetap **18**.

## BUKTI (dijalankan, bukan dikutip)
```
python3 test_core_rekap_harian.py       → 191/191 LULUS
python3 scripts/verify_rekap_harian.py  → INV-REKAP 34 OK / 0 FAIL
bash scripts/gate.sh                    → 18/18 PASS · VERDICT HIJAU
bash scripts/gate.sh --full             → 22/22 PASS · VERDICT HIJAU
bash scripts/rebuild_frontend.sh        → build OK, frontend HTTP 200
UANG: tagihan CMT 2.435.000 → 2.435.000 (tidak bergeser) · nol jejak data uji
```

## ATURAN KERAS YANG BARU (jangan dilanggar)
1. **JANGAN menulis `closed_at` langsung** di route mana pun. Satu penulis: `close_job()`.
2. **JANGAN menerima `closed_at` (atau `status` penutup) dari body permintaan** — itu persis cara
   bug `received_at` dulu masuk sebagai STRING dari jam komputer staf.
3. **JANGAN menyalin daftar status penutup.** Impor `JOB_CLOSED_STATUSES`; salinan itulah yang
   suatu hari akan berbeda dari yang dipakai backend.
4. **JANGAN menebak waktu tutup job warisan** dalam kode aplikasi. Yang menebak hanya migrasi, dan
   ia WAJIB menandainya `closed_at_estimated: True`.
5. **JANGAN menghapus peringatan job warisan dari layar.** Laporan yang menyembunyikan
   ketidaktahuannya sendiri lebih berbahaya daripada yang mengakuinya — RK-30 menjaganya.

## JEBAKAN LINGKUNGAN (menghabiskan waktu kalau tidak tahu)
- `/app` datang **kosong**. Pulihkan: clone repo → `rsync` (kecuali `.env`/`.git`/`node_modules`) →
  `mongorestore --gzip --drop --dir=backups/auto_20260807_190000` (**198 koleksi**) →
  `EMERGENT_LLM_KEY=… bash scripts/bootstrap.sh` → `python3 scripts/seed_cmt_override_demo.py`.
- **DULU: `yarn install` DILEWATI diam-diam pada clone baru** ⇒ `@simplewebauthn/browser@13.3.0`
  (dipakai `src/pages/AbsenPage.jsx`) tidak terpasang ⇒ `yarn build` MERAH `Module not found` ⇒
  bootstrap menutup dengan `build/ MISSING` dan preview menyajikan bundle BASI.
  **AKAR MASALAHNYA sudah ditemukan & DIPERBAIKI sesi ini** (sudah menghabiskan 2 sesi: #25 & #26):
  `.bootstrap_cache/fe.md5` **ikut ter-commit**, `frontend/yarn.lock` **tidak ada di repo**
  (jadi `FE_HASH` = md5(package.json + yarn.lock milik TEMPLATE) → nilainya sama persis setiap
  sesi ⇒ marker selalu "cocok"), dan `node_modules/` milik template platform sudah ada ⇒ ketiga
  syarat skip terpenuhi. Perbaikannya: **probe kenyataan** `1c-3` di `scripts/bootstrap.sh`
  (setiap `dependencies` package.json harus benar-benar ada di `node_modules`; kalau tidak, marker
  dibuang dan `yarn install` dipaksa — simetris dengan probe import backend `1c`),
  `.bootstrap_cache/` masuk **`.gitignore`** (keadaan mesin berhenti ikut bepergian, termasuk
  `admin_token.txt` yang berisi JWT hidup), dan **`frontend/yarn.lock` kini di-commit** supaya
  instalasi reproducible. Sudah diuji dua arah: node_modules lengkap → lewat; paket dihapus +
  marker basi dipasang → terdeteksi (`1 paket hilang: @simplewebauthn/browser`) dan marker dibuang.
  Kalau suatu hari gejalanya kembali: `cd /app/frontend && yarn install --prefer-offline` lalu
  `bash scripts/rebuild_frontend.sh`.
- Master vendor CMT = **`vendor_partners`** (bukan `dewi_cmt_vendors`). Login `/api/auth/login`
  mengembalikan field **`token`** (bukan `access_token`); rate-limit **10×/60 dtk**.
- Frontend = **static bundle**; setiap perubahan `frontend/src` WAJIB
  `bash scripts/rebuild_frontend.sh` atau perubahan TIDAK tampak di preview.

## BACKLOG TERBUKA (jujur — bukan regresi)
1. Rekap belum punya **jadwal otomatis** (teguran 16.00 WIB). `utils/scheduler.py` sudah ada dan
   endpoint remind sudah idempoten — tinggal didaftarkan.
2. Mingguan belum punya **perbandingan antar-pekan**; `?date=` sudah bisa menggeser jendela.
3. **`was_open_at()` belum dipakai di luar rekap CMT.** Layar lain yang masih bertanya "job jalan?"
   dari status sekarang bisa ikut memakainya.
4. Backlog lama masih berlaku: badge **Invoice CMT** belum diverifikasi VISUAL · `dewi_cmt_payments`
   memakai DUA master CMT · warna baris BOM belum dibatasi ke `dewi_rnd_materials.colors[]` ·
   `except Exception: pass` di 6 titik jalur stok/uang.

---


> 🟢 **2026-08-10 (fase 4) — BACA `plan.md` bagian "FASE 4" DULU.** Sesi terakhir menambahkan
> **REKAP MINGGUAN CMT** sebagai **tab kedua** di pintu "Input Vendor CMT" (tab Harian tetap yang
> pertama tampil): 7 hari BERGULIR, satu kotak per hari per vendor, klik kotak → tab Harian pada
> tanggal itu, sparkline pcs, streak, export Excel/PDF, tombol reminder untuk satu tanggal jelas.
> Gate `INV-REKAP` naik **22 → 30 kode** (baru: RK-20…RK-27); jumlah gate tetap **18**.
> Yang WAJIB diketahui sebelum menyentuh area ini:
>   1. **`build_week()` TIDAK BOLEH menghitung sendiri.** Ia memanggil `build_recap()` untuk tiap
>      hari dengan `ctx` bersama dari `prefetch_context()`, lalu hanya MERINGKAS. Kalau suatu hari ada
>      yang "mengoptimalkannya" dengan agregasi sendiri, tab Mingguan dan tab Harian akan mulai
>      berbeda pada kasus pinggir — dan itu angka yang jadi dasar tagihan CMT. Dijaga gate **RK-21**.
>   2. **`prefetch_context()` wajib tetap dipakai ulang.** Ia ada supaya 7 hari tidak membaca data
>      master 7×. Dijaga gate **RK-27** (mingguan tidak boleh lebih mahal daripada 7× harian) —
>      tanpa gate itu, refactor berikutnya akan menghapusnya dan tidak ada yang sadar karena data
>      demo terlalu kecil untuk terasa.
>   3. **Dua angka "terlambat" WAJIB tetap terpisah** (keputusan owner): `days_late` = hari yang ada
>      pekerjaan menunggu tapi NOL bukti; `days_unfinished` = itu + hari yang sudah diisi tapi masih
>      ada sisa. Meleburnya menghapus dasar keputusan "vendor mana yang ditegur". Gate **RK-22**.
>   4. **"Hari tanpa setoran" hanya dihitung saat vendor MEMANG punya job jalan**, dan **hari yang
>      belum terjadi** diberi state `future` dan tidak dihitung ke angka mana pun. Menghukum vendor
>      yang tidak diberi pekerjaan (atau untuk hari yang belum datang) = angka bohong. Gate RK-23/RK-26.
>   5. **Streak**: mundur dari hari terakhir yang sudah berjalan, **putus** pada hari `pending` ATAU
>      `partial`; hari `idle` **NETRAL** (tidak memutus, tidak menambah). Gate **RK-24**.
>   6. **Tanggal dipegang induk** (`CMTOverrideRecapPanel.jsx`), dan `CMTOverrideDailyRecap` sekarang
>      **terkendali** (`day` + `onDayChange`). Kalau tiap tab memegang tanggalnya sendiri lagi, klik
>      kotak hari tidak akan bisa memindahkan tab Harian ke tanggal itu. Helper tanggal WIB ada di
>      `cmt-override/recapDates.js` — JANGAN menyalinnya lagi ke dalam komponen.
>   7. `backend_test_fase4_mingguan.py` = suite READ-ONLY 17 uji (aman dijalankan kapan saja, tidak
>      menulis apa pun). Tanggalnya **dinamis** — jangan menyematkan tanggal mati lagi; versi pertama
>      begitu dan membuat satu pemeriksaan "lulus kosong" (membandingkan dua himpunan kosong).

> 🟢 **2026-08-08 (lanjutan) — BACA `plan.md` DULU.** Sesi terakhir menambahkan **REKAP HARIAN CMT**
> di dalam pintu "Input Vendor CMT": satu layar checklist per tugas berisi vendor mana yang belum
> diisi hari ini, chip ✗ bisa diklik langsung ke modulnya, plus navigasi tanggal, export Excel/PDF,
> dan tombol kirim reminder. Gate naik jadi **18** (baru: `INV-REKAP` = `scripts/verify_rekap_harian.py`).
> Yang WAJIB diketahui sebelum menyentuh area ini:
>   1. **SSOT hitungannya SATU berkas**: `backend/core/cmt_daily_recap.py`. Layar, export Excel/PDF,
>      dan sasaran tombol reminder memakai `build_recap()` yang sama. JANGAN menghitung ulang di
>      endpoint/berkas lain — itu cara termudah membuat Excel dan layar berdebat.
>   2. **`received_at` diisi SERVER** (`routes/vendor_shipment.py`, transisi `Sent → Received`).
>      Dulu hanya browser yang menulisnya sebagai STRING ⇒ query rentang tanggal tidak pernah cocok.
>      Jangan "merapikan" server agar percaya kiriman browser lagi — gate `INV-REKAP` RK-6 akan MERAH.
>   3. **Reminder rekap dikecualikan dari hitungan `waiting` pada tanggalnya sendiri**
>      (`reminder_type='daily_recap'` + `recap_date`). Kalau pengecualian ini dihapus, vendor
>      mustahil hijau dan tombol reminder jadi jebakan.
>   4. Kolom "menunggu" untuk tanggal LAMPAU dihitung per **akhir hari itu** (memakai stempel waktu
>      peristiwa), bukan kondisi sekarang. Satu-satunya perkiraan yang tersisa: job yang ditutup
>      setelah tanggal itu tidak lagi terhitung "job jalan" (`production_jobs` tidak menyimpan
>      kapan job ditutup) — sudah ditampilkan sebagai catatan di layar.
>   5. `production_progress` TIDAK punya `vendor_id` (menempel ke `job_id`). Menyaringnya dengan
>      `vendor_id` = NOL selamanya.
>   6. Batas hari WAJIB `utils.waktu.wib_day_bounds_utc` (jam container UTC).
>   7. Frontend = STATIC BUNDLE ⇒ setiap perubahan `frontend/src` WAJIB
>      `bash scripts/rebuild_frontend.sh` (±70 detik). Jangan `yarn start`.

> 🟢 **2026-08-08 — BACA `plan.md` DULU.** Sesi terakhir menyelesaikan **Portal CMT Override
> ("Input Vendor CMT")**: staf DA bisa mengisi 11 modul portal vendor CMT ATAS NAMA vendor yang
> tidak memakai sistem, dengan badge "diinput staf DA" di layar monitoring/invoice.
> Gate naik jadi **17** (baru: `INV-CMTOV` = `scripts/verify_cmt_override.py`).
> Jebakan lingkungan BARU yang wajib diketahui:
>   1. Sidebar hanya menampilkan pintu **section AKTIF** — pintu di section kedua TIDAK terlihat
>      sampai pil section diklik. Taruh pintu penting di section pertama.
>   2. Deep-link modul butuh **KEDUA** parameter: `/?portal=<p>&module=<m>`.
>   3. Beberapa aksi vendor memakai **`window.confirm()` native** (mis. "Konfirmasi Terima") ⇒
>      skrip Playwright wajib `page.on("dialog", lambda d: d.accept())`.
>   4. Setelah inspeksi material, modal "Ajukan Permintaan Material Tambahan" terbuka OTOMATIS
>      dan memblokir klik lain.
>   5. Password `cmtvendor@dewiaditya.id` = `Dewi@123` (bukan `Vendor@123`).
>   6. **Gate repo sendiri pernah membocorkan UANG PALSU**: `verify_produksi_maklon_invariants.py`
>      meninggalkan AR invoice maklon yatim tiap dijalankan (terakumulasi Rp 15.120.000 / 14 dok).
>      Sudah diperbaiki + dibersihkan. Kalau menulis alat uji: bersihkan TURUNAN
>      (`rahaza_ar_invoices`, `dewi_maklon_pos`, `dewi_cmt_component_requests`, `cmt_receipts`)
>      dan lakukan sweep seluruh koleksi, jangan andalkan daftar-hapus manual.
>   7. Backlog terbuka: badge di layar **Invoice CMT** belum diverifikasi VISUAL (baru tampil
>      setelah AP matang, yaitu setelah DA menyelesaikan QC di "Terima FG dari CMT").

> 🚨 **2026-07-31 — DOKUMEN INI SUDAH DILENGKAPI:** untuk alur **selisih kirim CMT→DA** dan
> **selisih terima DA→buyer** (Portal Produksi/Maklon/Vendor CMT), pakai
> **`memory/HANDOFF_SELISIH_CMT_BUYER.md`** — di sana ada hasil uji empiris (angka nyata),
> peta kode `file:line`, 7 gap (A–G), rancangan perbaikan siap eksekusi, dan jebakan environment.
> Jangan menelusuri ulang alur tersebut dari nol.


# ✅ STATUS TERKINI 2026-07-26 (lanjutan #3) — FASE 21: PEMANGKASAN ALAT + 3 BUG NYATA

> **BACA INI DULU — men-supersede SEMUA entri di bawah.**
> ⚠️ **PERINTAH LAMA SUDAH TIDAK ADA.** `scripts/guard.sh` dan
> `scripts/run_all_verifications.sh` **DIHAPUS**. Semua contoh perintah di
> bagian-bagian di bawah (FASE 20 ke belakang) **usang** — 52 skrip yang
> dirujuknya sudah tidak ada.

## Perintah verifikasi sekarang — HANYA SATU
```
bash scripts/gate.sh            # 12 gate, ~37 detik  → memory/GATE_RECEIPT.md
bash scripts/gate.sh --full     # + alur produk HR (absen/cuti/payslip/lembur)
```

## Kenapa dipangkas (keputusan user, dan alasannya benar)
Repo ini punya **12 gate + 54 skrip alat (~16.000 baris)**. Ongkosnya nyata:
`run_all_verifications.sh` butuh **>20 menit**, dan **penjaganya sendiri menjadi
sumber bug** berulang kali:

| Penjaga | Bug di penjaganya |
|---|---|
| `verify_fe_be_contract` | `_seg_match()` simetris ⇒ 48 temuan tersembunyi; `fe_calls()` membaca komentar ⇒ merah palsu |
| `audit_duplication.py` | membaca **DOCSTRING** `saga.py` sebagai penulis DB ⇒ `payroll_runs`/`payslips` dituduh duplikat padahal koleksinya tak ada |
| `verify_phase_g_acc_opname.py` | membocorkan stok + jurnal GL yatim tiap dijalankan |
| `cleanup_*_qa.py` | mencocokkan **teks penanda** ⇒ selalu satu alat di belakang; melaporkan "tidak ada drift" untuk drift yang nyata |
| `bughunt_hris_flow.py` | docstring bilang "cleans up after itself" — **keliru**, `DELETE` hanya meng-*cancel*; 1 lembur fiktif bertanggal **2028-09-01** tertinggal di DB |
| `INV-META-01` | penjaga yang menjaga penjaga — nol nilai bagi pengguna |
| `INV-QUALITY-01` | polisi "kualitas AI" — nol nilai bagi pengguna |

**52 skrip / 13.327 baris DIHAPUS.** Kriterianya satu pertanyaan: *"kalau
pemeriksaan ini hilang, apakah UANG, DATA, KEAMANAN, atau ALUR PRODUK bisa rusak
tanpa ada yang tahu?"* Kalau tidak → dibuang.

**Yang DIPERTAHANKAN (15 skrip):** `verify_data_integrity` · `lib/acc_baseline` ·
`verify_state_machine` · `verify_concurrency` · `round6_verify` ·
`guardrails/verify_rbac_idor` · `guardrails/verify_adversarial_5xx` ·
`health_check` · `guardrails/verify_unreachable_code` ·
`preflight/verify_fe_be_contract` · `guardrails/check_nav_map` ·
`guardrails/verify_platform_lint_engine` · `verify_fase16_absen` ·
`verify_fase17_cuti` · `verify_fase18_payslip` · `bughunt_hris_flow`.

## `_archive/` DIHAPUS TOTAL (90 berkas / 46.672 baris)
`frontend/src/components/erp/_archive/` (48 berkas) dan `backend/routes/_archive/`
(42 berkas). Dibuktikan aman sebelum dihapus: nol import dari kode hidup (semua
rujukan hanya komentar), dan **jumlah route backend tetap 1651 identik** setelah
restart. `yarn build` Compiled successfully.
**Efek samping bagus:** temuan `fe_be_contract` turun **123 → 49** (74 di antaranya
memang cuma kebisingan dari folder arsip).

## 3 BUG NYATA yang ditutup sesi ini
1. **Gate lint platform memblokir penyerahan sesi** (inilah yang membuat FASE 20
   tidak bisa memanggil `finish`). Akarnya BUKAN yang tertulis di dokumen lama.
   Yang benar, dari membaca kode platform:
   `engine_success = oxlint_success AND import_success`, dan yang gagal adalah
   **Import Validation**: 35 import relatif YATIM di `_archive/**` (akibat FASE 20
   memindahkan modul tanpa memperbarui import-nya) + `setupTests.js` mengimpor
   `@testing-library/jest-dom` yang tak ada di `package.json` **dan** tak
   terpasang. Karena semua temuan oxlint tersaring allowlist, `blocking=0`, dan
   kombinasi `blocking==0 AND NOT engine_success` melempar "engine error".
   → 35 import diperbaiki (lalu foldernya dihapus total), 3 devDependency test
   dipasang, dijaga `INV-LINT-01` (bukti-merah **11/11**).
   **⚠️ KOREKSI DOKUMEN:** RCA di FASE 12 (`mobile/eslint.config.js`) dan FASE 14
   (symlink `eslint-formatter-unix`) **KELIRU** — platform memakai `--config` &
   `--format` PATH ABSOLUT, jadi config repo tak pernah dipakai gate. Iterasi
   pertama FASE 21 juga keliru (memperbaiki arm **ESLint**, padahal gate memakai
   arm **oxlint**).
2. **14 fungsi duplikat MATI di modul absen** (306 baris) di 5 berkas
   `rahaza_auto_attendance_*`. **3 di antaranya masih memuat kebijakan LAMA** yang
   FASE 16 sengaja hapus: `geofence not_verified = LOLOS` dan `wajah error =
   LOLOS`. Tidak terjangkau (dibuktikan via AST: nol pemanggil), jadi bukan bug
   aktif — tapi ranjau, karena namanya `_determine_approval` dan duduk di berkas
   clock-in biometrik. Dihapus + 21 baris impor/konstanta yatim. Absen tetap
   **48 PASS / 0 FAIL**, route absen tetap 42.
3. **Alat uji menaruh data palsu di DB.** `bughunt_hris_flow.py` sekarang
   menghapus jejaknya **di `finally`** langsung ke Mongo (bukan mengandalkan
   `DELETE` yang cuma meng-cancel). Terbukti: 8/8 PASS lalu
   `rahaza_overtime_requests = 0`.

## Bukti (dijalankan ulang sesi ini, bukan dikutip)
`gate.sh` **12/12 PASS · 37 detik** · absen **48/0** · cuti **35/0** · payslip
**25/0** · alur lembur live **8/8** · Import Validation frontend+backend
**bersih** · `yarn build` **Compiled successfully** · route backend **1651**
(tak berubah) · baseline aksesoris **Rp 9.663.750** · Buku Besar seimbang
(Dr = Cr 6.729.375) · **nol drift**.

## BERIKUTNYA (belum dikerjakan — masalah PRODUK, bukan alat)
1. **`except Exception: pass` — 17 titik, 6 di jalur stok & uang**
   (`core/stock_service.py:334`, `core/quarantine.py` ×3,
   `core/accessory_stock.py:46`, `core/stock_reconcile.py:198`). Mutasi stok bisa
   gagal **tanpa log, tanpa error** ⇒ angka salah tanpa jejak. **Prioritas 1.**
2. **44 titik penomoran `count_documents()+1`** ⇒ dua user simpan bersamaan →
   **nomor dokumen KEMBAR** (SJ/PO/invoice). SSOT `utils/counters.py` sudah ada,
   44 titik ini belum ikut.
3. **27 titik datetime naive** ⇒ batas hari laporan/absen bisa bergeser.
4. **Nol test Jest di `frontend/`** — klaim dokumen lama "perluas Jest/RTL" salah
   premis; tidak ada yang bisa diperluas. `setupTests.js` sudah siap dipakai.
5. `RahazaOrdersModule` + 17 modul lain terdeteksi tak terjangkau dari UI —
   belum diputuskan arsip/hidupkan.
6. `mobile/` = scaffold Expo 389 baris tanpa fitur ERP; dependensinya tak pernah
   dipasang. Sudah 3× jadi sumber kegagalan alat. `mobile/tsconfig.json` kini
   `extends` salinan **verbatim** `expo@54.0.35/tsconfig.base.json` yang
   di-commit, supaya bisa di-resolve tanpa node_modules.
7. SMTP sungguhan (`skipped_no_smtp`) untuk verifikasi email berlampiran.

---


# ✅ STATUS TERKINI 2026-07-26 (lanjutan #2) — FASE 20 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap: **`docs/PLAN_FASE20.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Melanjutkan titik berhenti sesi lalu**: penelusuran *"the 7 genuinely broken FE calls"*
   dari temuan advisory `fe_be_contract`. Environment dibangun ulang dari nol via
   `bootstrap.sh` (58 detik, 6 login HTTP 200, baseline aksesoris **Rp 9.663.750** —
   cocok dengan dokumen, jadi angka itu sekarang TERBUKTI reproducible).
2. **Temuan advisory itu BUKAN tech-debt.** Setelah 92 WARN ditriase satu per satu:
   **8 bug produk NYATA** (fitur mati diam-diam) + **2 false positive** + sisanya
   archive/artefak. Rinciannya di `docs/PLAN_FASE20.md` §2.
3. **Gate-nya sendiri menyembunyikan sebagian bug itu** — 4 blindspot ditutup.
   Setelah `_seg_match()` dibuat asimetris: **92 → 140 temuan** (48 sebelumnya tak terlihat).
4. **Satu KELAS BUG BARU ditemukan & dijaga** (`INV-DEADCODE-01`): "handler tergabung".
5. **`fe_be_contract` sekarang: REAL_404 = 0** (dari 11) dan `DEADCODE = 0` (dari 16).

## ⚠️ KOREKSI KLAIM DOKUMEN
| Klaim di serah-terima lama | Kenyataan |
|---|---|
| `fe_be_contract` **HIGH 9** | **Label usang.** Gate versi sekarang melaporkan `WARN`, `0 HIGH`. Angka "9" = jumlah temuan nyata SETELAH triase, bukan severity |
| Temuan `fe_be_contract` = "tech-debt advisory, tidak mem-blok" | **Berbahaya.** Di dalamnya ada 8 fitur mati (lihat §2 PLAN_FASE20) |
| `dewi_assets.py` bersintaks rusak (dari log sesi lalu) | **KELIRU** — `py_compile` bersih; itu artefak render alat `view_file` |
| `numeric_bounds` MED 10 | sekarang **MED 1** |
| `static_antipatterns` MED 263 | sekarang **MED 253** (3 modul CMT mati diarsip) |

## 8 bug nyata yang ditutup (ringkas)
| Panggilan FE lama | Jadi | Dampak sebelumnya |
|---|---|---|
| `/api/rahaza/master/employees` (**4 titik**) | `/api/rahaza/employees` + baca `.items` | dropdown karyawan **selalu kosong** di AI Actions, HR Aset, WMS Pick List |
| `/api/finance/coa` | `/api/rahaza/coa/accounts` + parse array | mapping GL biaya karyawan **tak bisa dibuat** (dropdown akun kosong) |
| `/api/rahaza/overtime-requests` (**GET + POST**) | `/api/rahaza/overtime` + baca `.overtime` | kartu "Lembur Saya" kosong **dan setiap pengajuan lembur gagal** |
| `/api/rahaza/payroll-runs/{id}/export` | endpoint dipulihkan (dulu **kode mati**) + `downloadWithAuth` | tombol "Download CSV" payroll **mati total** |
| `/api/rahaza/payroll-runs/{id}/payslips/{sid}/adjust` | endpoint **dibuat** + header run disinkronkan | penyesuaian manual payslip **hilang tanpa error**; kolom "Adj" selalu 0 |
| `/api/collab/link-preview` | `/api/collab/search/link-preview` | pratinjau tautan kolaborasi selalu gagal |
| `/api/dewi/assets/by-code/{code}` | `/api/assets/scan-by-number/{n}` | **scan QR aset mati** (dan menembak domain yang salah) |
| `/api/rahaza/orders/{id}/generate-work-orders` | **tombol dihapus** | engine `rahaza_work_orders` sengaja dipensiunkan FASE 4 — jangan dihidupkan ulang |

> **`PUT /payslips/{pid}` yang SUDAH ADA juga diperbaiki**: ia mengubah angka slip tanpa
> menyinkronkan header run, padahal `post_payroll_run()` menyusun **jurnal GL dari header**
> ⇒ jurnal saat finalize nyata-nyata salah. Sekarang ada SSOT `_payslip_totals()` +
> `_recompute_run_totals()` di `rahaza_payroll_shared.py`.

## 🔴 2 TEMUAN TAMBAHAN — keduanya hanya muncul saat DIVERIFIKASI LEWAT UI/DB

### (a) Mismatch FIELD-level: semua kolom uang payslip menampilkan **Rp 0**
Gate kontrak hanya memeriksa **path**, jadi ini lolos total. Saat detail payroll run dibuka,
seluruh kolom uang per karyawan **Rp 0** padahal total run benar. FE membaca skema payslip
LAMA, backend menulis yang BARU:

| FE membaca | Backend menulis |
|---|---|
| `base_salary` | `earnings_total` |
| `transport_allowance` · `meal_allowance` · `production_bonus` | `allowances[]` + `allowance_total` |
| `overtime_pay` | `overtime_amount` |
| `total_deductions` | `deductions_total` |
| `net_salary` | `net_pay` |

Diperbaiki di 3 berkas — dua di antaranya **layar milik karyawan sendiri**:
`RahazaPayrollRunModule.jsx` (kolom `Transport`/`Bonus Prod.` dihapus karena backend tak
memisahkannya; ditambah `Bruto`), `PortalSayaPayslip.jsx` (fitur FASE 18),
`SelfServicePortal.jsx`. Nama lama tetap dipakai sebagai **fallback** (`modern ?? legacy`)
karena backend pun begitu.
**Diverifikasi BUKAN bug:** `RahazaHRReportsModule.jsx` — endpoint
`hr/reports/payroll-summary` memang menghasilkan `total_deductions`/`net_salary`.
Dijaga oleh **C7** (statik) + **C8** (runtime).

### (b) Drift yang ditinggalkan ALAT UJI — termasuk **jurnal GL POSTED fiktif**
Testing agent melaporkan *"All test data cleaned up successfully"*. **Keliru.** Tertinggal:
`PR-20260726-001` **FINALIZED** (`DELETE /payroll-runs/{id}` hanya izinkan `draft` ⇒ gagal
dalam diam), **jurnal `JE-20260728-0001` status POSTED Dr Rp 45.031.214** + 3 baris mirror,
dan 1 request lembur pending. Buku Besar & Neraca Saldo diturunkan dari
`rahaza_journal_lines` ⇒ **uang fiktif masuk laporan keuangan**.

Ditutup dengan **`scripts/cleanup_fase20_qa.py`** (`--dry-run`/`--apply`, idempoten,
bagian 4 khusus **jurnal GL yatim**). Bukti:
```
SEBELUM : journal_entries 9 · journal_lines 19 · total debit 51.760.589
SESUDAH : journal_entries 8 · journal_lines 16 · total debit  6.729.375
selisih = 45.031.214 (tepat jurnal fiktifnya) · Dr == Cr tetap seimbang · 24 dokumen dihapus
```
**JALANKAN `python3 scripts/cleanup_fase20_qa.py --dry-run` setiap selesai sesi pengujian.**

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash    scripts/run_all_verifications.sh        # 12 skrip (termasuk verify_fase20.py)
python3 scripts/verify_fase20.py                # 105 PASS / 0 FAIL (sentinel kontrak FE↔BE)
bash    scripts/_prove_fase20_sentinel_red.sh   # 4/4 bug → sentinel MERAH, lalu hijau lagi
python3 scripts/triage_fe_dead_calls.py         # WAJIB "REAL_404    : 0"
python3 scripts/guardrails/verify_unreachable_code.py   # INV-DEADCODE-01 (blocking)
python3 scripts/cleanup_fase20_qa.py --dry-run  # WAJIB "TOTAL akan dihapus: 0 dokumen"
bash    scripts/gate.sh                         # 10/10 HIJAU → memory/GATE_RECEIPT.md
python3 scripts/lib/acc_baseline.py             # WAJIB TOTAL = 9.663.750
```

## ⚠️ 10 PELAJARAN WAJIB (tambahan; yang lama di bawah tetap berlaku)
1. **"Tech-debt advisory" bisa menyembunyikan bug produk.** Triase sekali — jangan diwarisi
   sebagai angka di dokumen serah-terima.
2. **Guard yang menghasilkan false positive permanen = guard yang akan diabaikan.**
   Memperbaiki blindspot-nya sama pentingnya dengan memperbaiki bugnya.
3. **Menguji helper ≠ menguji pemakaiannya.** Proof merah iterasi pertama hanya 2/4:
   assert-nya memanggil `websocket_shapes()`/`_strip_js_comments()` langsung, bukan
   memeriksa bahwa GATE memakainya. A3b/A4b lahir dari kegagalan itu.
4. **Jangan buat endpoint hanya karena FE memanggilnya.** Cek dulu: engine-nya sengaja
   dipensiunkan? FE-nya menembak domain yang salah? Keduanya "selesai" dengan endpoint
   baru — dan keduanya salah.
5. **Memperbaiki URL saja sering belum memperbaiki fitur.** Samakan juga **bentuk balasan**
   dengan yang dibaca FE, kalau tidak hasilnya "200 OK tapi tabel kosong".
6. **Kalau angka payslip berubah, header run WAJIB ikut** — jurnal GL dibaca dari header.
7. **Komentar yang menyebut path lama bisa membuat gate merah palsu.** Yang diperbaiki
   guard-nya (`fe_calls()` mengabaikan komentar), bukan komentarnya yang dihapus.
8. **Gate kontrak path-level TIDAK melihat mismatch FIELD-level.** Bug "semua kolom uang
   Rp 0" hanya muncul saat layarnya benar-benar DIBUKA. Verifikasi lewat UI bukan formalitas.
9. **Jangan percaya klaim "test data cleaned up" — hitung dokumennya.** `DELETE` yang
   menolak status non-draft **gagal dalam diam**, dan jurnal GL POSTED yang tertinggal
   adalah drift termahal karena menyusup ke laporan keuangan.
10. **Assert yang bergantung data ambient akan "lewat" diam-diam di environment bersih.**
    Buat data ujimu sendiri, lalu hapus di `finally`.

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong; sistem membalas `skipped_no_smtp` +
   notifikasi in-app (perilaku benar). Bukti lampiran Excel+PDF: jalankan `aiosmtpd` lokal.
2. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
3. **Tech-debt advisory sisa** (tidak mem-blok gate): `fe_be_contract` WARN 123
   (**sudah ditriase — semuanya archive/artefak/dinamis, REAL_404 = 0**) ·
   `static_antipatterns` MED 253 · `effort_quality` HIGH 1
   (`backend/poc_variant_ssot.py:26` — URL Mongo literal di skrip POC, bukan kode produksi).
4. **Drop `accessory_legacy` di DB PRODUKSI user** — di preview no-op.
5. **46 temuan `DYNAMIC`** di `triage_fe_dead_calls.py` sudah diperiksa manual & benign
   (adapter `${path}`/`${qs}` + komposisi aksi `${action}`). Kalau mau NOL WARN, jalannya
   adalah membuat CHECK B mengerti wrapper adapter — bukan menghapus temuannya.

---

# (ARSIP) STATUS TERKINI 2026-07-26 (lanjutan) — FASE 13 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap: **`docs/PLAN_FASE13.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Environment dibangun ulang dari nol** (container baru, MongoDB KOSONG total) via
   `bootstrap.sh` — 49 detik, backend health OK, static bundle HTTP 200, 6 login HTTP 200.
   Semua angka di bawah dihasilkan ulang dari seeder, **bukan dikutip dari dokumen**.
2. **Verifikasi dulu, baru kerja** — 3 klaim TERBUKTI (443 PASS/0 FAIL · gate 9/9 · ESLint rc=0),
   **3 klaim KELIRU** (lihat §angka baseline di bawah).
3. **3 bug tooling NYATA ditutup di akarnya** — semuanya satu penyakit: *alat uji merusak data
   yang seharusnya ia lindungi*.
4. **Regresi penuh sekarang TIDAK MENINGGALKAN DRIFT SAMA SEKALI** (pertama kali) —
   sebelumnya tiap run membocorkan +5/-3 pcs stok + 2 mutasi + 2 jurnal GL yatim.

## ⚠️ ANGKA BASELINE BERUBAH — "Rp 9.667.750" ITU RESIDU QA, JANGAN DIPAKAI LAGI
| | LAMA (residu) | **BENAR (reproducible dari seeder)** |
|---|---|---|
| `ACC-BTN-12` | 5.020 | **5.000** |
| total qty valuasi | 32.220 | **32.200** |
| nilai persediaan | Rp 9.667.750 | **Rp 9.663.750** |
| total on-hand (health) | 32.970 | **32.950** |

Selisih 20 pcs = **4 run kebocoran × 5 pcs** dari `verify_phase_g_acc_opname.py`.
SSOT tunggal sekarang: **`scripts/lib/acc_baseline.py`** (semua total DITURUNKAN dari tabel
`STOCK_BASELINE × COST_BASELINE`, ada `assert` pengaman). `cleanup_fase10_qa.py` dan
`tests/backend_test_fase12.py` **mengimpor** dari situ — angka tidak bisa lagi menyimpang.
Tetap: 10 item · 8 bernilai / 2 sengaja belum dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN`) ·
peta gudang bersih (hanya `ZNA-AKSESORIS` + `ZNA-KAIN`) · `health.affected_rows = 0`.

## 3 bug tooling yang diperbaiki
1. **Kebocoran stok + jurnal GL yatim** (`verify_phase_g_acc_opname.py`) — approve opname
   dijalankan pada material demo NYATA, dan `_cleanup()` memakai field `related_ref` yang
   **tidak pernah tersimpan** (backend menyimpan `reference_id`/`ref_id`) sehingga jurnal GL
   tak pernah terhapus. Kini skrip memakai aksesoris uji sendiri (`QA-OPN-*`), `try/finally`,
   dan jaring pengaman pemulihan stok + ledger. **49 PASS/0 FAIL**, artefak 13 → 35.
2. **Pencemaran `rahaza_costing_settings` global** (`verify_fase11/12/66.py`) — nilai uji
   (12345/77, 88000, 4321) tertinggal permanen bila ada exception/timeout, lalu jadi LENGKET.
   Ditutup dengan SSOT `scripts/lib/qa_state_guard.py` → `preserve_costing_settings(db)`
   (pemulihan di `finally`; dokumen yang semula tidak ada akan DIHAPUS).
3. **Titik buta alat audit** — `cleanup_fase10_qa.py` tidak pernah memeriksa
   `rahaza_costing_settings` (itu sebabnya audit user harus manual). Sekarang ada **bagian 5**
   deteksi + pemulihan. Bonus: `tests/backend_test_fase12.py` dulu mematok `BASE_URL` ke
   preview container lama yang **sudah mati** → kini dibaca dari `frontend/.env`.

## Sentinel baru — supaya tidak kambuh
**`scripts/verify_fase13.py`** (33 assert, terdaftar TERAKHIR di `run_all_verifications.sh`):
menjalankan skrip terawan lalu **membuktikan NOL DRIFT** pada 9 metrik, menguji guard
**saat exception**, mendeteksi mutasi/jurnal yatim, dan memeriksa nama field lewat **AST**.
**Sentinelnya sendiri sudah diuji MERAH** dengan menanam ulang bug lamanya.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash    scripts/run_all_verifications.sh     # 11 skrip → 480 PASS / 0 FAIL
python3 scripts/verify_fase13.py             # 33 PASS / 0 FAIL (sentinel drift)
python3 scripts/cleanup_fase10_qa.py --dry-run   # WAJIB "(tidak ada drift)" di bagian 4 DAN 5
bash    scripts/gate.sh                      # SEMUA HIJAU → memory/GATE_RECEIPT.md
python3 scripts/lib/acc_baseline.py          # cetak SSOT baseline + totalnya
```

## ⚠️ 6 PELAJARAN WAJIB (tambahan; yang lama di bawah tetap berlaku)
1. **Alat uji = sumber tech-debt data yang paling sering terlewat.** Tiga sesi mengejar "data
   kotor" padahal penyebabnya skrip verify-nya sendiri. Perbaiki PENULISNYA, bukan datanya.
2. **Angka baseline yang tidak reproducible dari seeder adalah RESIDU.** Kalau `--dry-run`
   selalu merah di environment segar, curigai baselinenya — bukan datanya.
3. **Alat "cleanup" yang menulis angka bisa MENGARANG data.** Restore-by-insert dengan baseline
   salah = menyuntikkan persediaan fiktif beserta nilai rupiahnya.
4. **Nama field Mongo wajib diverifikasi terhadap PENULISNYA.** `related_ref` terlihat benar
   (ada di signature backend) tapi tersimpan sebagai `reference_id`. Query yang cocok 0 dokumen
   gagal DIAM-DIAM — cek `count_documents()` sebelum percaya sebuah cleanup.
5. **Pemulihan state global adalah tugas `finally`, bukan "kalau semua lancar".**
6. **Guard yang belum pernah terlihat MERAH bukan guard.** Tanam ulang bugnya untuk membuktikan.

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong; sistem membalas `skipped_no_smtp` +
   notifikasi in-app (perilaku benar). Bukti lampiran Excel+PDF: jalankan `aiosmtpd` lokal.
2. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
3. **Tech-debt advisory** (tidak mem-blok gate): `fe_be_contract` HIGH 9 ·
   `static_antipatterns` MED 263 · `numeric_bounds` MED 10.
4. **Drop `accessory_legacy` di DB PRODUKSI user** — di preview no-op.
5. **Observasi kecil (belum ditindak):** notifikasi "Harga satuan belum diisi" menumpuk
   **4 duplikat per item** untuk 2 item yang sengaja belum dinilai (8 dokumen). Kandidat dedup;
   bukan risiko finansial.

---

# (ARSIP) STATUS TERKINI 2026-07-26 — FASE 12 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap: **`docs/PLAN_FASE12.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Verifikasi dulu, baru kerja** — dan **4 dari 5 klaim dokumen ternyata keliru**:
   suite regresi sebenarnya **401 PASS / 9 FAIL** (bukan 410/0) · `bootstrap.sh` tidak pernah
   menyeed baseline valuasi aksesoris (8 FAIL palsu) · alias `yarn_*` masih bocor lewat seeder ·
   `scripts/migrate_stock_locations_to_wh.py` yang disebut backlog **tidak pernah ada** ·
   ESLint mati total kalau dijalankan dari `/app/mobile`.
2. **4 bug nyata diperbaiki**: BUG-A (seeder menulis alias legacy), BUG-B (HPP job internal
   memakai harga bahan **0** diam-diam), BUG-B2 (material `kain`/`benang`/`interlining` tanpa
   `unit_cost` dapat fallback harga **aksesoris**), BUG-C (linter engine mati).
3. **Backlog #3 (rekonsiliasi lokasi stok) TUNTAS** — bukan dengan skrip sekali pakai, tapi
   penyakit ke-8 **`unmapped_location`** di alat "Kesehatan Skema Stok" yang sudah punya
   pratinjau → terapkan → **rollback presisi** + UI.
4. **Akar penyebabnya ditutup**: seeder demo (`maklon_seed.py`) & `link_demo_bom_materials.py`
   tidak lagi menaruh stok di lokasi pseudo `GDG-UTAMA-DEMO`; `cleanup_fase10_qa.py` baseline-nya
   ikut diperbarui (kalau tidak, `--apply` justru MEMBATALKAN rekonsiliasi).
5. **Higiene alat uji**: `bootstrap.sh` kini menyeed baseline valuasi aksesoris;
   `run_all_verifications.sh` otomatis membersihkan artefak `verify_phase6_quarantine`
   (penyebab run ke-2 selalu merah palsu) dan menjalankan `verify_fase12.py`.

## ⚠️ 5 PELAJARAN WAJIB (tambahan dari sesi ini; yang lama di bawah tetap berlaku)
1. **Uji ulang SEMUA angka di dokumen serah-terima.** Empat dari lima klaim keliru sesi ini.
2. **"Merah" belum tentu regresi produk** — bisa **pencemaran data antar-skrip uji**.
   `verify_phase6_quarantine` meninggalkan `TEST-F6-KAIN` sehingga run ke-2 menghitung stok
   DUA KALI. Kalau sebuah gate hanya merah pada run kedua, curigai kebersihan datanya dulu.
3. **Rekonsiliasi otomatis TIDAK boleh menyentuh baris yang butuh keputusan manusia.**
   Memindah + menggabungkan baris ber-qty **negatif** akan diam-diam mengurangi stok zona tujuan
   dan menghilangkan selisih dari radar. Baris yatim juga tak punya kategori ⇒ zona tujuan tak
   bisa ditentukan. Keduanya sengaja dikecualikan (dan tidak dihitung `fixable`).
4. **Kalau memindahkan lokasi stok, PERBARUI JUGA skrip baseline/cleanup.**
   `cleanup_fase10_qa.py --apply` sempat siap mengembalikan stok ke lokasi liar.
5. **Seeder = sumber tech-debt data.** Backlog "rekonsiliasi lokasi" selalu kembali karena
   SEEDER-nya yang salah menaruh stok, bukan karena datanya. Perbaiki penulisnya, bukan datanya.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash    scripts/run_all_verifications.sh     # 10 skrip → 443 PASS / 0 FAIL (auto-cleanup F6)
python3 scripts/verify_fase12.py             # 31 PASS / 0 FAIL (self-cleaning)
python3 scripts/sweep_query_robustness.py    # 7.184 request → 0 error 500
bash    scripts/gate.sh                      # 9/9 HIJAU → memory/GATE_RECEIPT.md
python3 scripts/cleanup_fase10_qa.py --dry-run   # harus "(tidak ada drift)"
```
**Baseline data demo aksesoris (WAJIB tetap seperti ini):** 10 item · nilai persediaan
**Rp 9.667.750** · 8 bernilai / 2 belum dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN` sengaja HPP 0) ·
`ACC-BTN-12` stok **5.020 di ZNA-AKSESORIS** (bukan lagi terbelah ke `int-demo-loc-1`) HPP **200**.
**Peta gudang bersih:** hanya `ZNA-AKSESORIS` + `ZNA-KAIN` yang menyimpan stok; `health` → `affected_rows = 0`.

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong; sistem membalas `skipped_no_smtp` +
   notifikasi in-app (perilaku benar). Untuk bukti lampiran Excel+PDF: jalankan `aiosmtpd` atau
   isi kredensial nyata lewat UI.
2. **Drop `accessory_legacy` di DB PRODUKSI user** — di preview no-op.
3. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
4. **Tech-debt advisory** (tidak mem-blok gate): `fe_be_contract` HIGH 9 ·
   `static_antipatterns` MED 263 · `effort_quality` HIGH 1 · `numeric_bounds` MED 10.

---

# (ARSIP) STATUS 2026-07-25 (lanjutan #4) — FASE 11 TUNTAS & TERUJI
> **BACA INI DULU — men-supersede semua entri di bawah.**
> Rencana + bukti lengkap FASE 11: **`docs/PLAN_FASE11.md`** · Riwayat: `memory/CHANGELOG.md` (entri teratas).

## Ringkas apa yang terjadi sesi ini
1. **Verifikasi dulu, baru kerja.** Klaim FASE 10 (402 PASS / 0 FAIL) diuji ulang dari nol → **TERBUKTI**.
2. **BUG-R11-A ditutup TUNTAS** — dulu hanya diuji 8 sampel; kini disapu **7.184 request**
   (898 GET endpoint × 8 varian query rusak). **66 → 0 error 500**, 51 → 0 endpoint bermasalah.
   46 endpoint di 36 file router diperbaiki + helper baru `backend/utils/query_guards.py`.
3. **BUG-4 (BARU)** — `datetime` adalah SUBCLASS `date`; `GET /api/dewi/cmt/lifecycle` balas **500 pada
   request POLOS**. Diperbaiki di 3 file berjebakan sama.
4. **BUG-5 (BARU)** — jurnal modul Aset memakai kode akun hardcode yang **tidak ada di CoA**
   (`1500`/`1100`/`1590`/`8100`/`6300` vs CoA berformat `1-2500`/`1-110`). Kini diambil dari
   `rahaza_posting_profiles` lewat `routes/asset/_accounts.py`.
5. **Alias legacy `yarn_*` DIHENTIKAN penulisannya** (permintaan user) — fallback BACA tetap dijaga.
6. **gate.sh HIJAU 9/9** untuk pertama kalinya sejak 2026-07-16 (dulu 2 MERAH).

## ⚠️ 7 PELAJARAN WAJIB DIINGAT AGENT BERIKUTNYA
1. **JANGAN percaya laporan `testing_agent_v3` soal kebersihan data.** Ini kejadian **ke-3 berturut-turut**
   (iter 170, 173, dan sekarang **174**). Iter 174 melapor `"test_data_created": []` padahal meninggalkan
   3 aset + 4 jurnal. Penyebabnya: skripnya memanggil `DELETE /api/assets/{id}` dan
   `DELETE /api/rahaza/journal-entries/{id}` yang **TIDAK ADA**, jadi gagal diam-diam.
   **SELALU audit DB sendiri sesudahnya.**
2. **JANGAN uji robustness pakai sampel.** Sesi lalu menyimpulkan R11-A beres dari 8 sampel (7 di antaranya
   kebetulan sudah sembuh). Pakai `python3 scripts/sweep_query_robustness.py` — sapu semuanya.
3. **`datetime` adalah SUBCLASS `date` di Python.** `isinstance(v, date)` True untuk `datetime`.
   Selalu cek `datetime` DULU. Pakai `utils/query_guards.to_date()` / `date_key()`.
4. **Endpoint LLM merusak hasil sweep paralel.** `/api/finance/ai-cashflow` ≈ 20 detik → tetangganya
   ikut time-out dan terlihat "rusak". 5 dari 51 temuan awal ternyata false positive. **Probe ulang SERIAL.**
5. **Jebakan pustaka `requests`:** `Response.__bool__` == `Response.ok`. `if r:` bernilai **False untuk
   respons 400/422** — persis yang ingin diuji pada uji robustness. Pakai `if r is not None:`.
6. **Frontend = STATIC BUNDLE.** Setelah mengubah `frontend/src` WAJIB
   `bash /app/scripts/rebuild_frontend.sh` (atau `yarn build`) lalu `supervisorctl restart frontend`.
7. **JANGAN biarkan tool `plan` menimpa `plan.md`.** SSOT rencana proyek ada di situ (~79 KB).
   Rencana per-fase ditaruh di `docs/PLAN_FASE<N>.md`.

## ✅ Masalah setup lama yang SUDAH ditutup di akar (FASE 11)
- **`bootstrap.sh` + `@simplewebauthn/browser` (3 sesi berturut-turut gagal).** Akarnya:
  `yarn install --frozen-lockfile` GAGAL bila `frontend/yarn.lock` tidak ada di repo — dan memang
  belum pernah ter-commit. `bootstrap.sh` kini memakai frozen HANYA bila lockfile ada, dan jatuh
  otomatis ke `yarn install` biasa bila gagal. `frontend/yarn.lock` juga sudah ikut di-commit.
- **ESLint mati total ("linter engine error").** `mobile/eslint.config.js` melempar MODULE_NOT_FOUND
  bila dependensi Expo belum dipasang (memang tidak pernah dipasang di container ini) sehingga
  SELURUH gate lint mati. Config kini menurun dengan anggun.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
bash   scripts/run_all_verifications.sh          # 9 skrip regresi → 410 PASS / 0 FAIL
python3 scripts/verify_fase11.py                  # 108 PASS / 0 FAIL
python3 scripts/sweep_query_robustness.py         # 7.184 request → 0 error 500
python3 backend_test_fase11.py                    # 45/45 PASS (self-cleaning + verifikasi)
bash   scripts/gate.sh                            # 9/9 HIJAU → memory/GATE_RECEIPT.md
python3 scripts/cleanup_test_f6.py --apply        # bersihkan artefak F6
python3 scripts/cleanup_fase10_qa.py --apply      # kembalikan stok/HPP demo ke baseline
```
**Baseline data demo aksesoris (WAJIB tetap seperti ini):** 10 item · nilai persediaan
**Rp 9.667.750** · 8 bernilai / 2 belum dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN` sengaja HPP 0) ·
`ACC-BTN-12` stok **5.020** (5.000 di `int-demo-loc-1` + 20 di ZN-AKS) HPP **200**.
Seeder: `scripts/seed_acc_valuation_baseline.py` (idempoten, `--cleanup`).

## BERIKUTNYA (belum dikerjakan)
1. **Verifikasi email SUNGGUHAN** — user memilih "lewati dulu" sesi ini. SMTP masih kosong; sistem
   membalas `skipped_no_smtp` + notifikasi in-app (perilaku benar). Untuk bukti lampiran Excel+PDF
   benar terkirim: jalankan SMTP dummy (`aiosmtpd`) atau isi kredensial nyata lewat UI.
2. **Drop `accessory_legacy` di DB PRODUKSI user** — user memilih "lewati". Di preview no-op.
3. **Rekonsiliasi lokasi stok aksesoris** — `ACC-BTN-12`/`ACC-LBL-01`/`ACC-DA-LBL` masih menyimpan stok
   di `int-demo-loc-1`, bukan zona kanonik ZN-AKS. Aman (BUG-1 sudah diperbaiki) tapi peta gudang
   masih berantakan. Alat: `scripts/migrate_stock_locations_to_wh.py`.
4. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
5. **Tech-debt advisory** (tidak mem-blok gate, sudah lama): `fe_be_contract` HIGH 9 ·
   `static_antipatterns` MED 263 · `effort_quality` HIGH 1 (`poc_variant_ssot.py` pakai literal
   `mongodb://`) · `numeric_bounds` MED 10 (field uang Pydantic tanpa `ge=`, mis. `dewi_cmt_permak.py`).

---

# (ARSIP) STATUS 2026-07-25 (lanjutan #3) — FASE 10 TUNTAS, TERUJI & TERDOKUMENTASI
> **BACA INI DULU — men-supersede semua entri di bawah.**

> **Sesi 2026-07-25 lanjutan #3 (environment dari repo `naababnamana/da`).** Sesi sebelumnya sudah
> MENULIS kode FASE 10 tapi berhenti tepat sebelum `testing_agent_v3`, sehingga dokumen belum di-update.
> Sesi ini: verifikasi penuh → **temukan & perbaiki 3 bug nyata** → E2E testing agent → bersih-bersih data
> → rapikan dokumen. Baca `plan.md` §SESI AKTIF (lanjutan #3) + `memory/CHANGELOG.md` entri teratas.

## FASE 10 — 4 Next Action Items (SELESAI)
1. **Prompt Terakhir** — `window.prompt()`/`window.confirm()` TERAKHIR di modul Aksesoris DIGANTI
   `OpnameActionModal` (kind: submit/cancel/approve/reject) + modal hapus aksesoris. Testid dinamis
   `opname-<kind>-modal|-confirm|-cancel|-reason|-error`. **0 dialog native tersisa di modul ini.**
2. **Jadwal Rapor** — `services/accessory_valuation_mailer.py` + `utils/email_sender.py`:
   `GET/PUT /api/acc/valuation/report-schedule`, `POST .../send-now`. Job `monthly_valuation_report_email`
   tanggal 1 pukul 06:00 WIB, lampiran Excel+PDF, idempoten per periode. SMTP diisi lewat UI
   (`smtp_security` = starttls|ssl|none). Tanpa SMTP → `skipped_no_smtp` (HTTP 200) + notifikasi in-app.
3. **Prasyarat Drop Aksesoris** — grup `accessory_legacy` kini **[SIAP]** di
   `drop_legacy_collections_guided.py --audit`: endpoint `/api/acc/internal-requests/*` & `/api/acc/loans/*`
   → **410**, pemotongan stok diangkat ke `core/accessory_issue.py` dan dipakai SSOT `deliver`,
   tab "Peminjaman" dilepas, pinjaman lama ditutup via `migrations/close_legacy_acc_loans.py`.
4. **Ringkasan Alarm Harian** — `GET/POST /api/acc/valuation/unvalued-digest[/send]` + job
   `daily_unvalued_digest` 07:30 WIB. **Notifikasi per-item TETAP jalan** (pilihan user), digest = tambahan.
   Panel UI: tab **Valuasi HPP** → `acc-val-automation` (digest + jadwal rapor + riwayat kirim).

## ⚠️ 5 PELAJARAN WAJIB DIINGAT AGENT BERIKUTNYA
1. **Restore repo:** `bootstrap.sh` (`yarn install --frozen-lockfile`) TIDAK memasang
   `@simplewebauthn/browser` (sudah terjadi 3 sesi berturut-turut). Yang bekerja:
   `cd /app/frontend && yarn add @simplewebauthn/browser@13.3.0` lalu `yarn build`.
2. **Frontend = STATIC BUNDLE.** Setelah mengubah `frontend/src` WAJIB
   `bash /app/scripts/rebuild_frontend.sh` (atau `yarn build`), kalau tidak perubahan TIDAK terlihat.
3. **JANGAN biarkan tool `plan` menimpa `plan.md`.** Sesi lalu `plan.md` master (69 KB, SSOT rencana
   proyek) tertimpa jadi 9,5 KB. Sudah dipulihkan; rencana FASE 10 dipindah ke
   `docs/PLAN_FASE10_NEXT_ACTIONS.md`.
4. **SELALU audit DB sendiri sesudah `testing_agent_v3`.** iteration_170 DAN iteration_173 sama-sama
   mengklaim "data dipulihkan" padahal meninggalkan artefak; iteration_173 bahkan "memulihkan" stok
   dengan cara MENERIMA barang sehingga HPP rata-rata bergeser. Alat: `scripts/cleanup_fase10_qa.py`.
5. **Stok aksesoris DIBACA lintas lokasi tapi (dulu) DITULIS di satu lokasi.** Kalau menambah alur
   pengeluaran aksesoris baru, pakai `core/accessory_stock.add_stock` / `issue_across_locations`,
   JANGAN memanggil `stock_service.issue(material, LOKASI_KANONIK, qty)` langsung.

## 3 BUG NYATA yang ditemukan & diperbaiki sesi ini
- **BUG-1 (kritis)** — pengeluaran aksesoris **HTTP 500** bila stok tersebar di >1 lokasi (data warisan /
  put-away / seed demo). Lolos dari semua uji sebelumnya karena skrip uji selalu membuat item BARU yang
  stoknya mendarat di lokasi kanonik. Fix: `core/accessory_stock.issue_across_locations()`.
  Repro: `python3 scripts/repro_acc_multiloc_issue.py` (self-restoring).
- **BUG-2** — `approve` opname DIAM-DIAM melewati baris yang gagal disesuaikan (sesi tampak "Completed"
  padahal selisih tidak diterapkan). Fix: `stock_failed` + `stock_failed_items` di backend & UI.
- **BUG-3** — banner hasil aksi di panel otomasi valuasi hilang seketika (klik "Kirim rapor sekarang"
  tanpa SMTP = layar diam). Fix: `load(keepFeedback)` + skeleton hanya pada muat pertama di
  `AccessoryValuationAutomation.jsx` DAN `AccessoryValuationTab.jsx`.

## Verifikasi cepat state (jalankan BERURUTAN — rate limit login 10 req/60 detik)
```
python3 scripts/verify_fase10_digest_report.py       # 59 PASS
python3 scripts/verify_fase10_accessory_legacy.py    # 44 PASS
python3 scripts/verify_acc123.py                     # 62 PASS
python3 scripts/verify_fase8.py                      # 48 PASS
python3 scripts/verify_fase8plus.py                  # 24 PASS
python3 scripts/verify_phase_g_acc_opname.py         # 45 PASS (self-clean)
python3 scripts/verify_fase9_legacy_drop.py          # 24 PASS
python3 scripts/verify_fase66.py                     # 48 PASS
python3 scripts/verify_phase6_quarantine.py          # 48 PASS  → lalu cleanup_test_f6.py --apply
python3 scripts/cleanup_fase10_qa.py --dry-run       # cek drift data demo setelah semua uji
```
**Baseline data demo aksesoris:** 10 item · nilai persediaan **Rp 9.667.750** · 8 bernilai / 2 belum
dinilai (`DEMO-ACC-ELS-25`, `DEMO-ACC-SNP-BTN` sengaja ber-HPP 0 untuk memicu alarm & digest).
Seeder: `scripts/seed_acc_valuation_baseline.py` (idempoten, `--cleanup`).

## BERIKUTNYA (menunggu keputusan user)
1. **Verifikasi email SUNGGUHAN** — SMTP masih kosong (sesuai pilihan user: diisi lewat UI). Untuk bukti
   lampiran Excel+PDF benar terkirim, jalankan SMTP dummy lokal (`aiosmtpd`) atau isi kredensial nyata.
2. **Eksekusi drop `accessory_legacy` di DB PRODUKSI user** (di preview no-op karena koleksinya absen).
3. **Hapus alias legacy `yarn_*`** setelah syarat panduan §5 terpenuhi.
4. **Rekonsiliasi lokasi stok aksesoris** — `ACC-BTN-12/ACC-LBL-01/ACC-DA-LBL` masih menyimpan stok di
   `int-demo-loc-1` (bukan zona kanonik ZN-AKS). Sekarang AMAN berkat BUG-1 fix, tapi memindahkannya
   lewat `scripts/migrate_stock_locations_to_wh.py` akan merapikan peta gudang.
5. Perluas Jest/RTL ke `AccessoryValuationAutomation` + `StokOpnameTab`.

---

# ✅ STATUS TERKINI 2026-07-25 — FASE 6.6 + FASE 8 SELESAI (men-supersede semua entri di bawah)

> **Sesi 2026-07-25 (environment dari repo `hanababama/da`): FASE 6.6 (rekonsiliasi skema stok A/B/C + rename
> internal `yarn_*`) dan FASE 8 (valuasi HPP aksesoris + panduan drop koleksi legacy) SELESAI & TERUJI.**
> Baca `plan.md` §SESI AKTIF + `memory/CHANGELOG.md` entri teratas + `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md`.
>
> **Ringkas:**
> - **FASE 6.6-A** — `core/stock_reconcile.py` + `routes/wms_stock_schema.py` + modul FE **"Kesehatan Skema Stok"**
>   (`wh-stock-schema`, juga tab di hub `wms-stock-hub`): deteksi 7 penyakit skema, pratinjau → terapkan → rollback
>   presisi lewat jurnal `wh_stock_schema_reconcile_log`. TIDAK pernah mengubah total on-hand.
> - **FASE 6.6-B** — SSOT `core/material_fields.py` + `frontend/src/lib/materialFields.js`: `yarn_type`→`composition`,
>   `yarn_kg_per_pcs`→`material_kg_per_pcs`, `default_yarn_cost_per_kg`→`default_material_cost_per_kg`,
>   `total_yarn_kg_per_pcs`→`total_material_kg_per_pcs`, `total_yarn_kg`→`total_material_kg`,
>   `yarn_count`→`bulk_line_count`. **Alias legacy TETAP ditulis** (0 breaking change) + migrasi backfill.
> - **FASE 8** — `core/accessory_valuation.py` (moving average), penerimaan/pengeluaran/**scrap (endpoint BARU)**
>   aksesoris kini BERNILAI + berjurnal, `routes/dewi_accessories_valuation.py`, tab FE **"Valuasi HPP"**.
>   KPI "Dipinjam" diganti "Nilai Persediaan" + "Belum Dinilai".
> - **FASE 8.8** — `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` + `migrations/drop_legacy_collections_guided.py`
>   (`--audit`/`--dry-run`/`--execute`/`--rollback`/`--purge-archives`, arsip sebelum drop).
>
> ### ⚠️ 3 PELAJARAN WAJIB DIINGAT
> 1. **Restore repo:** `bootstrap.sh` (`yarn install --frozen-lockfile`) TIDAK memasang
>    `@simplewebauthn/browser`, dan `yarn install --prefer-offline` **JUGA TIDAK CUKUP** (sudah dicoba).
>    Yang bekerja: `cd /app/frontend && yarn add @simplewebauthn/browser@13.3.0` lalu `yarn build`.
> 2. **Frontend = STATIC BUNDLE.** Modul/route BARU "tidak ketemu" atau mendarat di "Pilih Portal" ⇒ 99%
>    `frontend/build/` masih bundel LAMA. Jalankan `bash /app/scripts/rebuild_frontend.sh` DULU.
> 3. **`rahaza_material_stock` punya UNIQUE index (material_id, location_id).** Setiap skrip/route yang
>    memindahkan atau menormalkan baris stok WAJIB menghapus/menggabungkan dulu sebelum menulis, kalau tidak
>    akan kena `DuplicateKeyError` (ini bug nyata yang ketemu & difix di FASE 6.6-A).
>
> **Verifikasi cepat state:** `python3 scripts/verify_fase66.py` (48 PASS) · `python3 scripts/verify_fase8.py`
> (48 PASS) · `python3 scripts/verify_acc123.py` (62 PASS) · `python3 scripts/verify_phase6_quarantine.py`
> (48 PASS, lalu `python3 scripts/cleanup_test_f6.py --apply`).
> **INGAT rate limit login 10 req/60 detik** — jangan jalankan semua skrip berbarengan.
>
> **LANJUTAN #2 (2026-07-25) — juga SELESAI:**
> - **FASE 9**: alat drop legacy TERBUKTI lewat `scripts/verify_fase9_legacy_drop.py` (24 PASS — siklus penuh
>   arsip → drop → rollback → purge dgn data tiruan). Eksekusi grup `opname_v1` di DB ini = no-op (koleksi absen).
> - **Modal pengembalian pinjaman** menggantikan `prompt()` di tab peminjaman deprecated.
> - **Rapor valuasi Excel & PDF**: `GET /api/acc/valuation/export?format=xlsx|pdf&month=YYYY-MM`
>   (`utils/accessory_valuation_export.py`) + panel unduhan di tab Valuasi HPP.
> - **Alarm "belum dinilai"**: `core/accessory_valuation.py::notify_unvalued` dipanggil dari
>   receive/issue/scrap saat HPP 0 → notifikasi ke Admin Gudang dkk, anti-spam 1×/24 jam, non-blocking.
> - Bukti tambahan: `scripts/verify_fase8plus.py` **24 PASS** · testing_agent_v3 iteration_170 backend 100%.
> - ⚠️ **PELAJARAN**: iteration_170 melaporkan "data_changes: None" tapi meninggalkan 3 material `ZZTEST-*`,
>   3 baris stok, 6 notifikasi, 2 JE. SELALU cek DB sendiri setelah memanggil testing agent.
>
> **Berikutnya (menunggu keputusan user):** ganti `window.prompt()` terakhir (alasan menolak opname di tab
> Stok Opname) · prasyarat grup `accessory_legacy` sebelum di-drop (panduan §3) · hapus alias `yarn_*`
> (panduan §5) · perluas Jest/RTL ke modul baru.

---

# ✅ STATUS TERKINI 2026-07-25 (BACA INI DULU — men-supersede semua entri handoff historis di bawah)

> **Sesi 2026-07-25 (environment dari repo `cabanamama123/da`): FASE 7 — 3 gantungan AKSESORIS
> (ACC-1 / ACC-2 / ACC-3) SELESAI & TERUJI.** Baca `plan.md` §FASE 7 + `memory/CHANGELOG.md` entri teratas.
>
> **Ringkas:** ACC-3 peminjaman pindah ke domain ASET (`#asset-loans`; `POST /api/acc/loans` ditutup 410,
> GET & return tetap hidup) · ACC-2 `material_id` wajib untuk baris aksesoris BOM + `link-health` +
> `relink-materials` (RBAC diperketat: HR 403) + seeder tak lagi melahirkan BOM "lepas" · ACC-1 kebutuhan
> aksesoris PO membawa `material_id` + tombol "Buat Permintaan" ke SSOT `dewi_accessory_requests`.
> Bukti: `scripts/verify_acc123.py` **62 PASS / 0 FAIL**, `testing_agent_v3` iteration_167 backend **100%**,
> 0 critical bug; 3 alur UI sisa diverifikasi manual (Playwright) oleh main agent.
>
> ### ⚠️ 2 PELAJARAN YANG WAJIB DIINGAT AGENT BERIKUTNYA
> 1. **Frontend = STATIC BUNDLE.** Kalau modul/route BARU "tidak ketemu" atau deep-link mendarat di
>    **"Pilih Portal"**, 99% penyebabnya `frontend/build/` masih bundel LAMA. Jalankan
>    `bash /app/scripts/rebuild_frontend.sh` DULU sebelum menyimpulkan itu bug kode.
>    (Temuan "P1 deep-link rusak" di iteration_2 ternyata ini, bukan bug.)
> 2. **Restore repo:** `bootstrap.sh` memakai `yarn install --frozen-lockfile` yang GAGAL karena lockfile
>    repo out-of-sync ⇒ `@simplewebauthn/browser` tak terpasang ⇒ `yarn build` gagal. Jalankan
>    `cd /app/frontend && yarn install --prefer-offline` sekali, lalu rebuild.
>
> **Berikutnya (menunggu keputusan user):** FASE 6.6 rekonsiliasi baris stok skema lama A/B/C + rename
> internal `yarn_*` · FASE 8 valuasi HPP aksesoris + panduan drop koleksi legacy · bersih-bersih sisa
> domain lama aksesoris (KPI "Dipinjam" di dashboard, `prompt()` di tab peminjaman deprecated).

---

# STATUS 2026-07-21 (arsip)

> Sesi 2026-07-21: environment dipulihkan dari fresh clone + **audit "sisa backlog" selesai**. Ringkas:
>
> **1. Backlog formal (`BACKLOG_PLAN.md` ITEM 1/2/3.1/3.2) — SELESAI & TESTED.** Lihat banner status di `BACKLOG_PLAN.md` + `memory/CHANGELOG.md` (2026-07-21).
>
> **2. Kandidat dedup pintu T-1..T-5 — SUDAH DIPUTUSKAN & DIEKSEKUSI (bukan lagi "PERLU-KEPUTUSAN").** Verifikasi kode 2026-07-21:
>   - T-1 Opname material vs aksesoris = **by-design, logic BENAR** (satu koleksi `wh_opname_sessions2` dipartisi field `domain`; sisi material `$ne:"accessory"`, sisi aksesoris `=="accessory"`; stok ke SSOT `rahaza_material_stock`). Bukan split-brain.
>   - T-2/T-3 = scope-per-`moduleId` sudah diimplementasi (`AccessoryRequestInbox.jsx`, `KREATORRequestModule.jsx`), termasuk fix bug laten tombol approve RnD.
>   - T-4/T-5 = by-design + cross-link/label disambiguation, sudah diterapkan.
>   - Keputusan & bukti lengkap: `IA_RESTRUCTURE_PROPOSAL.md` §8.1. **Entri "PERLU-KEPUTUSAN T-1..T-5" di handoff lama di bawah = USANG.**
>
> **3. CMT-flow Phase A/B/C — SUDAH SELESAI & runtime-verified (bukan pekerjaan tersisa).** Change Log `memory/GUIDELINE_CMT_FLOW.md` §15: Phase A (2026-07-16), B (07-17), C (07-18). Re-run E2E 2026-07-21: `scripts/test_phase_b_e2e.py` ✅ ALL PASS, `scripts/test_phase_c_e2e.py` ✅ ALL PASS.
>
> **4. Rollout opsional (incremental):** OnwardCTA (22 modul terpasang) & paginasi tabel = tetap incremental/opsional; user memilih SKIP untuk sekarang.
>
> Tidak ada item backlog terbuka yang butuh keputusan user saat ini. Entri handoff di bawah dipertahankan sebagai **arsip historis**.

---


> ⚡ **SETUP CEPAT (BACA DULU):** untuk clone+setup dari 0, ikuti `/app/AGENT_QUICKSTART.md` → clone shallow + `EMERGENT_LLM_KEY=sk-... bash /app/scripts/bootstrap.sh` (idempoten, deps paralel+cache, seed idempoten; ~10 dtk pertama, ~7 dtk berikutnya). Jangan setup manual berurutan lagi.

# 🤝 HANDOFF (Session #26 lanjutan — RC-FLOW-UX-11 UI TESTED ✅ 100% + Bug-fix StrictMode)

> **UI Testing:** `auto_frontend_testing_agent` iter#68 = **6/6 PASS** setelah bug-fix.
> **Bug ditemukan & di-fix mid-test:** React 18 StrictMode invoke `useState` initializer 2x di dev-mode → side-effect `sessionStorage.removeItem` di initializer menyebabkan call #2 dapat null → default salah `complaints`. **Fix:** initializer sekarang PURE (baca saja), `removeItem` dipindah ke `useEffect(() => {...}, [])`. File: `MarketingAfterSalesHub.jsx` line 178-197.
> **Poles 11e (terminologi) & 11f (Log merge) SELESAI.** Semua RC-FLOW-UX-11a…11f closed.

---

# 🤝 HANDOFF (Session #26 — RC-FLOW-UX-11 Alur After-Sales/Retur DIEKSEKUSI ✅)

> **Keputusan user 8 Jul 2026:** 11a=B · 11c=B · 11d=A. Sudah diimplementasikan & tested (deep_testing_backend_v2 = **9/9 PASS**, 0 regresi). Detail: lihat "STATUS UPDATE — RC-FLOW-UX-11" di `FLOW_UX_AUDIT.md`.

**Ringkas yang berubah:**
- **Backend** — `marketing_returns_routes.py`: endpoint baru `POST /api/marketing/returns/{id}/create-wh-return` (idempoten, link 2-arah ke `wh_returns`) + `complete_return` upgrade dgn `warning` soft-guard. `dewi_wh_returns.py`: `resolve_return` callback update `marketing_returns.wh_return_status='Resolved'` bila punya `source_marketing_return_id` (non-blocking).
- **Frontend** — `ReturnsRefundsModule.jsx`: tombol "Buat Retur Fisik di Gudang" + banner ⚠️ 24-jam soft-warning + link "Buka di Gudang →". `WHReturnsModule.jsx`: `<OnwardCTA>` di detail Resolved (cross-portal ke `marketing-after-sales`). `moduleRegistry.js` + `App.js LEGACY_MODULE_TO_PORTAL`: 4 pintu legacy retur/komplain di-redirect ke `marketing-after-sales` tab. `MarketingAfterSalesHub.jsx`: baca `hub_tab_marketing-after-sales` untuk deep-link tab. `portalNav.js`: `wh-returns` label → "Retur Fisik (Gudang)".

**Belum dikerjakan (non-blocker):** RC-FLOW-UX-11e (poles terminologi), 11f (Log Penyelesaian merge `wh_returns` Resolved). Frontend UI test belum dijalankan (menunggu izin user).

---

# 🤝 HANDOFF (Session #26 — Audit Alur 11 After-Sales/Retur & Refund SELESAI ✅)

> **UPDATE:** `FLOW_UX_AUDIT.md` ditambah section baru **ALUR 11 — Retur Pelanggan → Refund → Koreksi Stok** (Toko→Gudang±Keuangan), termasuk tabel ringkasan verdict baris #11, 6 kartu RC-FLOW-UX-11a…11f (grounded ke `backend/routes/marketing_returns_routes.py` + `backend/routes/dewi_wh_returns.py` + `MarketingAfterSalesHub.jsx` + `WHReturnsModule.jsx`), update kandidat CTA berikutnya, dan update kesimpulan §9.2 (+1 blocker teknis: 2 sistem retur paralel `marketing_returns` vs `dewi_wh_returns` tanpa jembatan; `marketing.complete` tak restock).
>
> **PERLU-KEPUTUSAN USER sebelum eksekusi 11a/11c/11d** (menyentuh skema data + IA). CTA onward 11b bisa langsung dipasang (fondasi RC-FLOW-UX-CORE sudah siap).

---

# 🤝 HANDOFF (Session #25 lanjutan — RC-FLOW-UX-CORE `onNavigate` SELESAI) ✅

> Status: **fondasi navigasi onward siap untuk SEMUA modul + 2 CTA baru + 1 CTA lama** (testing iter#40 = 100%). Baca `FLOW_UX_AUDIT.md` (bagian "STATUS UPDATE — RC-FLOW-UX-CORE") untuk detail & kandidat CTA berikutnya.

## RC-FLOW-UX-CORE — yang sudah jadi
- `onNavigate(moduleId, params)` di-pass App.js ke tiap modul (PortalShell & collaboration branch) + diteruskan lewat hub (`{...props}` → `HubTabs {...rest}` → tab). SEMUA modul & tab-hub menerimanya.
- **App.js `handleNavigate` (baris ~433)** = navigasi onward penuh: cross-portal switch (pindah `selectedPortal` bila target di portal lain yg accessible), hub-tab deep target (`{tab}`→`sessionStorage.hub_tab_<hubId>`), guard modul invalid, forward `deepLinkParams`, scroll-to-top.
- **`components/erp/OnwardCTA.jsx`** = bar "Langkah Berikutnya" reusable. Pakai: `<OnwardCTA onNavigate={onNavigate} title="…" actions={[{ module:'<id>', label:'…', icon, primary, hint }]} />`.
- CTA aktif: `marketing-orders`→`fulfillment` (CROSS-PORTAL Toko→Gudang, `onward-fulfillment`), `maklon-po-360`→`maklon-billing` (`onward-maklon-billing`), `wh-purchase-orders`→`wh-receiving` (existing, buat GR).

## Menambah CTA onward (incremental, mudah)
1. Modul terima prop `onNavigate` (top-level otomatis; sub-komponen: teruskan).
2. `import OnwardCTA from './OnwardCTA'` (atau `../OnwardCTA`).
3. `<OnwardCTA onNavigate={onNavigate} actions={[{ module:'<target-id>', label:'…', icon: Ikon, primary:true }]} />` setelah header/hasil.
4. Cross-portal ditangani otomatis oleh `handleNavigate`. `module` harus id valid di `MODULE_REGISTRY`.
- **Kandidat berikut**: Alur 3 (WO→`prod-cutting`), Alur 6 (payroll→`fin-journal-*`), Alur 2 (GRN→`wh-putaway`/`wh-stock-hub`), Alur 7/8 (order→retur/komplain), Alur 9 (RnD sample approved→`rnd-techpack`/`maklon-po`).

## Catatan
- Hash URL TIDAK berubah saat klik CTA (navigasi berbasis React state) — normal, bukan bug.
- Non-kritis pre-existing: warning `<span> in <option>` di WarehouseDashboard (console-only, tak pengaruh fungsi).

---



# 🤝 HANDOFF (Session #25 — lanjut PAGINASI RC-UI-03, +45 modul) ✅ TERVERIFIKASI

> **BACA URUT**: file ini → `/app/plan.md` (Session #25 di atas) → `/app/DOCS_INDEX.md` → `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` (BAGIAN 7 = standar paginasi) → `/app/memory/FINAL_REPAIR_LOG.md` (entri RC-UI-03 Session #25 di bawah). Handoff sesi lama di bawah (arsip).

## SESSION #25 — SELESAI & TERVERIFIKASI (testing iter#39)
- **Env di-setup ulang** dari clone `argentinavsfrench/da` → /app (env preserved). Setup: `bash /app/scripts/bootstrap.sh` (backend healthy, seed OK, 6 login 200). **CATATAN**: `yarn install --frozen-lockfile` GAGAL (lockfile drift) → jalankan `cd /app/frontend && yarn install --prefer-offline` sekali, lalu `supervisorctl restart frontend`. Setelah itu `compiled successfully`.
- **RC-UI-03 paginasi +45 modul** (kumulatif ~56 pakai `ui/pagination-lite.jsx`). Batch 1 (28 single-table), Batch 2 (8 multi-tabel→list utama), Batch 3 (9). Daftar lengkap: `plan.md`/`FINAL_REPAIR_LOG.md` Session #25.
- **Alat (regen kapan pun)**: `/tmp/paginate_inject.py` (injector aman: anchor SATU `VAR.map`, hook di return TOP-LEVEL min-indent, PaginationLite setelah `</table>`), `/tmp/find_clean_tables.py` (kandidat single-table), `/tmp/inspect_tables.py` (identifikasi list utama modul multi-tabel).
- **Verified**: `hr-employees` (40) FULL 10/hal + Prev/Next (Hal x/4), `hr-attendance-hub`→Absensi Harian (40), `maklon-qc` (12), `marketing-sales` (135). ≤10 baris → label "Menampilkan a–b dari N"; 0 baris → PaginationLite `null` (by-design). 0 crash / 0 React error.

## PEKERJAAN PAGINASI TERSISA (incremental, JUJUR — ~84 modul raw-table)
1. **Modul MULTI-TAB** (tiap tab = list terpisah, butuh hook + `paged` NAMA-BEDA per tabel; injector single-hook TIDAK cukup — kerjakan manual): RahazaFGInventory (items/issues/movements), HROrgChart (units/positions), CMT stacked (deliveries/payments selain jobs), MaklonPO360/AccessoryModule/Phase7Reporting/RahazaHPP/RahazaHRReports (4–6 tabel), HRKPI, RnDTechPack.
2. **SKIP (sudah paginasi)**: yang pakai `<DataTable`/`DataTableV2`/`MasterDataCRUD` (auto 10/hal) atau punya own `[page,setPage]`/server skip+LIMIT+total (WMSModule, BudgetModule, FixedAssets, UnifiedInventory, ReportsModule, MarketingWebhooks, marketing dashboards, RahazaMaterials, RahazaOrders/Stock/ARInvoices/WorkOrders).
3. **EXEMPT**: laporan akuntansi utuh (GL/TB/PnL/BS/Aging), grid editable, matriks (FGStockMatrixView), form/dialog import-preview.

## ATURAN KERAS PAGINASI (dari bug yang ditemui — WAJIB dipatuhi)
- Hook `useClientPagination` HARUS di TOP-LEVEL komponen (indent terkecil), **sebelum SEMUA early-return** (`if(loading/empty) return`), **tak boleh** di dalam callback `.map()`.
- Bila `<table>` di cabang ternary `... : ( <table/> )` → bungkus `<>...</>` saat menambah PaginationLite (adjacent-JSX).
- **JANGAN** paginasi ulang modul yang sudah server-paginate/own-page (cek `skip`/`LIMIT`/`loadMore`/`[page,setPage]`).
- **JANGAN edit parallel search_replace di FILE yang SAMA** (race). `EmployeeLoansModule.jsx` = dead (skip).

---



# 🤝 HANDOFF UNTUK AGENT BERIKUTNYA (Session #24 — item 1 paginasi + item 2 RC-FLOW/tab-audit/FLOW-UX)

> **BACA URUT**: file ini → `/app/DOCS_INDEX.md` → `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` → `/app/IA_RESTRUCTURE_PROPOSAL.md` (§7 = audit tab §9.1 baru) → `/app/FLOW_UX_AUDIT.md` (baru, §9.2) → `/app/memory/FINAL_REPAIR_LOG.md` (Session #24 di bawah). Handoff sesi lama di bawah (arsip).

## SESSION #24 — SELESAI & TERVERIFIKASI (lanjut item 1 & 2)
- **Env setup ulang** dari clone `da71` → /app (env preserved): backend/.env + JWT_SECRET(gen)+EMERGENT_LLM_KEY; deps (pip+yarn); seed OK (`production-full`+`rahaza/seed-demo`); services RUNNING; health ok; 6 akun login 200.
- **ITEM 1 — RC-UI-03 paginasi (testing iter#38: 100%)** ✅: +7 modul custom pakai `ui/pagination-lite.jsx` @10/hal → RahazaJournalListModule (fin-journal-hub "Daftar Jurnal"), RahazaOvertimeModule (hr-overtime), RahazaAttendanceApprovalModule (hr-attendance-hub "Approval Absen"), RahazaDowntimeModule (prod-downtime), InventoryScrapModule (wms-stock-hub "Penyesuaian"), SupplierScorecardModule (wh-supplier-scorecard), ProductionMaterialReturnsModule (prod-material-returns). Verified: journal 10/hal + Prev/Next; scrap "1–10 dari 26". Total cakupan ~53 modul 10/hal.
- **ITEM 2 §9.1 — audit level-TAB** ✅ → `IA_RESTRUCTURE_PROPOSAL.md` BAGIAN 7 (skrip `/tmp/tab_audit.py`). 0 duplikat fungsional wajib-fix baru; 5 kandidat = **PERLU-KEPUTUSAN** (T-1 opname material vs aksesoris; T-2 AccessoryRequestInbox 3-menu; T-3 KREATORRequest 2-menu; T-4 approval absen 2-pintu (by-design); T-5 self-service payslip/cuti 2-portal).
- **ITEM 2 §5 — RC-FLOW write-flow+RBAC (testing iter#36→#37: 95.2%, 20/21)** ✅: **2 BUG RBAC NYATA ditemukan+fix+verified**:
  - **RC-FLOW-expense-1**: `employee_expense_claims.py` disburse cek role `'finance'` padahal role Finance kanonik = **`accounting`** → finance ditolak. Fix: tambah `accounting/staff_keuangan/hr_manager`. (finance disburse kini 200)
  - **RC-FLOW-production-1**: `rahaza_work_orders.py` `_require_admin` hanya `superadmin/admin` → SEMUA role produksi tak bisa kelola WO (koleksi `role_permissions` KOSONG). Fix: tambah `admin_produksi/supervisor_produksi/supervisor`. (spv create WO kini 200)
  - **PENTING sistemik**: `role_permissions` KOSONG → semua custom-role bergantung cek role-string hardcode per-endpoint. Bila menambah role ke portal, cek endpoint izinkan role-string-nya.
- **ITEM 2 §9.2 — FLOW_UX_AUDIT.md** ✅ (baru): audit 10 alur kritis. 0 blocker teknis (semua write-flow LULUS). Akar gesekan UX: (1) **hanya 2 file** punya CTA onward (`window.location.hash=`) → halaman hasil tak menautkan langkah berikut; (2) beberapa lompat-portal tanpa jembatan; (3) pintu duplikat (cuti/expense/opname/payslip). Usulan fondasi **RC-FLOW-UX-CORE**: teruskan `onNavigate` ke semua modul.

## PEKERJAAN TERSISA (opsional, incremental — JUJUR)
1. **RC-UI-03 paginasi** ke ~110 list-custom sisanya (mayoritas multi-komponen/multi-tabel: CMT*, Maklon*, HRKPI, WMSModule, marketing dashboards). Skrip target: `/tmp/find_custom_tables.py` (regen kapan pun). EXEMPT: laporan akuntansi utuh (GL/TB/PnL/BS/Aging) + grid editable.
2. **RC-FLOW-UX fixes** (butuh persetujuan user, §8.3): mulai dari **RC-FLOW-UX-CORE** (prop `onNavigate` ke modul) → buka CTA onward di semua alur. Lalu de-duplikasi pintu (cuti/expense/opname) = PERLU-KEPUTUSAN.
3. **§9.1 kandidat PERLU-KEPUTUSAN** (T-1..T-5) — tanyakan user sebelum eksekusi (menyentuh IA lintas-portal / SSOT backend).
4. Minor pra-ada: `UnifiedInventoryModule` console warning "unique key prop" (LOW, tidak crash).

## CATATAN CEPAT
- Semua data = SEED. Re-seed (admin): `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo`. Login admin@garment.com/Admin@123 (rate-limit 10/60dtk). 5 akun RBAC: hr/finance/spv/gudang/maklon @dewiaditya.id / `Dewi@123`. Navigasi: login → `window.location.hash='<id>'` → reload; hub → klik tab.
- **JANGAN edit parallel search_replace di FILE yang SAMA** (race → fragment `<>` bisa tak ter-apply). Edit sekuensial per file.
- `EmployeeLoansModule.jsx` = dead (di-comment di registry, tak di-import) — jangan hitung/sentuh.

---



> **BACA URUT**: file ini → `/app/DOCS_INDEX.md` → `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` → `/app/IA_RESTRUCTURE_PROPOSAL.md` → `/app/memory/FINAL_REPAIR_LOG.md`. Handoff Session #22 ada di bawah (arsip).

## SESSION #23 — SELESAI & TERVERIFIKASI (user setuju SEMUA)
- **Env di-setup ulang** dari clone repo `da70`: `.env` backend + `JWT_SECRET`(generated)+`EMERGENT_LLM_KEY`; deps terpasang; seed OK; services RUNNING.
- **PHASE A (RC-IA-warehouse-1/2/3) ✅** (testing iter#31: BE 100%, FE 95%): `wms-stock-hub` 4-tab (Opsi A); UnifiedInventory read-only + jalur adjust RESMI `rahaza/material-adjust` (per-lokasi+GL); `get_locations` union `warehouse_locations`+`wh_positions`(=44) + `create_putaway` dual-lookup; nav warehouse W-2 (6 seksi) + W-4 rename.
- **PHASE B (5 hub anti-overwhelm) ✅** (testing iter#33: 100%, 17/17 redirect): `prod-exec-hub`, `hr-expense-hub`, `hr-attendance-hub`, `fin-acctg-adjust-hub`, `rnd-design-hub`. BUG redirect id-lama difix via `LEGACY_MODULE_TO_PORTAL` (App.js) — **PENTING: setiap id lama yang dikonsolidasi ke hub WAJIB ditambah ke LEGACY_MODULE_TO_PORTAL** biar deep-link resolve portal.
- **PHASE C (PART5 UI) ✅** (testing iter#34): RC-UI-01 tema 100% (9/9) — 66 file (~582 kelas) via converter aman `/tmp/theme_fix.py` (skip dark:/text-white/by-design/_archive/eksternal + gradient netral); RC-UI-02 render 100% (12/12); RC-UI-03 komponen `ui/pagination-lite.jsx` (+hook).
- **PHASE D (RC-UI-02 render review) ✅** (testing iter#35, 100%): sweep 235 modul → 234/235 OK; ditemukan+difix BUG `MasterDataCRUD` tak unwrap respons paginasi `{items:[]}` → crash `rows.filter/filtered.slice`. Fix root (unwrap) + guard di `DataTable`/`DataTableV2`/adapter. `prod-employees` tampil 40 baris 10/hal.
- **PHASE E (RC-UI-03 lanjut) ✅**: `pagination-lite` di 3 modul custom (Buyers, WMSDeliveryNotes, CatalogManagement). Total ~36 modul paginasi 10/hal (DataTable ~23 + MasterDataCRUD ~10 + pagination-lite 3).

## PEKERJAAN TERSISA (opsional, incremental)
1. **RC-UI-03 rollout paginasi** ke list-CUSTOM sisanya (kompleks; multi-tabel) pakai `ui/pagination-lite.jsx` — banyak sudah tercakup DataTable/MasterDataCRUD.
2. **RC-FLOW** write-flow+RBAC (BAGIAN 5 PART5); §9.1 deteksi level-TAB (management/self/collaboration); §9.2 `FLOW_UX_AUDIT.md` (audit 10 alur bisnis inti end-to-end).
3. Opsi lanjut IA proposal (W-3 aksesoris 1-pintu dsb) bila user minta.

---


# 🤝 HANDOFF UNTUK AGENT BERIKUTNYA (2026-07-02, Session #22)

> **BACA URUT**: 1) file ini → 2) `/app/DOCS_INDEX.md` → 3) `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` (rencana kerja AKTIF) → 4) `/app/IA_RESTRUCTURE_PROPOSAL.md` (temuan+usulan menunggu keputusan user) → 5) `/app/memory/FINAL_REPAIR_LOG.md` (laporan per modul).

## STATUS SISTEM
- Backend/data SSOT: RC-01..RC-29 + BACKLOG-A..E SELESAI (sweep 930 GET = 0 crash). Detail: `/app/memory/CHANGELOG.md`. **JANGAN kerjakan ulang.**
- Sudah fixed & verified testing agent: duplikat menu Aset (defaultTab), duplikat tab "Stok Opname" di WMS Scanner, theme-sync LiveSessionAnalyticsDashboard, bug RC-20/22/23.
- Semua data = SEED, boleh hilang. Re-seed: `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo` (admin). Login: admin@garment.com / Admin@123 (rate-limit 10/60dtk). Navigasi modul: login → `window.location.hash='<id>'` → reload.

## PEKERJAAN TERSISA (urutan disarankan)
1. **MENUNGGU KEPUTUSAN USER** — `IA_RESTRUCTURE_PROPOSAL.md` Bagian 4 + pertanyaan akhir Session #22 (fix RC-IA-warehouse-2&3? 5 hub anti-overwhelm? stock-hub 1A? W-2/3/4?). Tanya user dulu bila belum dijawab.
2. **RC-IA-warehouse-2 🔴** (menu GRN/PutAway/Lokasi pakai `api/wms/legacy/*` — dual-door terbalik) & **RC-IA-warehouse-3 🔴** (3 pintu adjust stok, 3 endpoint beda) — instruksi fix eksplisit di proposal BAGIAN 5. WAJIB STOP-VERIFY koleksi tulis backend dulu.
3. **PART 5** (semua metode eksplisit di dokumennya): RC-UI-01 theme (112 file sisa, inventaris BAGIAN 3, contoh acuan = LiveSessionAnalyticsDashboard) · RC-UI-03 paginasi 10/hal · RC-UI-02 render 309 modul · §9.1 deteksi level-TAB portal management/self/collaboration (7 portal lain SUDAH — hasil BAGIAN 6 proposal) · §9.2 audit 10 flow kritis → buat `/app/FLOW_UX_AUDIT.md` · RC-FLOW write-flow+RBAC (BAGIAN 5 PART5).
4. Konsolidasi hub anti-overwhelm (setelah user setuju) — pakai pola terbukti: `erp/hubs/HubTabs.jsx` + `makeRedirect(hub, tabKey)` + update portalNav + `LEGACY_MODULE_TO_PORTAL` di App.js (ingat: portal marketing = key `toko`).

## ATURAN KERAS
- Ikuti PART 5 PERSIS (tabel konversi, resep per-file, template laporan). Bug report user → WAJIB verifikasi via testing agent sebelum klaim fixed.
- 1 file = 1 unit selesai (fix→lint→compile→visual→laporan ke FINAL_REPAIR_LOG.md).
- JANGAN sentuh `_archive/`, jangan re-fix yang ada di CHANGELOG, jangan ubah .env/port, backend hanya via kartu RC yang tertulis.
- Update `plan.md` (entri sesi baru di ATAS) + FINAL_REPAIR_LOG setiap selesai.
