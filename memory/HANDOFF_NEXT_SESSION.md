# HANDOFF — CV. Dewi Aditya ERP

## 0-TERBARU-5. SESI 2026-08-21 #30 — SATUAN GULUNGAN · STYLE DARI MASTER · HARGA DARI PEMBELIAN ✅ TUNTAS

Keluhan pemilik: (1) "purchasing yard tapi tracking roll jadi meter … jangan dipaksakan meter";
(2) "cutting harusnya nama produk/style dari master data supaya BOM & produksi jelas"; (3) "harga
satuan jangan dari master data, ambil dari pengadaan/pembelian otomatis generate harga rata-rata".

### Yang WAJIB diingat (jangan diulangi)
- **`length_m`/`remaining_m` adalah NAMA WARISAN, bukan satuan.** Isinya mengikuti `uom` (bisa yard/
  rol). Satu-satunya jalan baca: `core/fabric_roll_engine.with_display_uom()` →
  `uom`/`qty_total`/`qty_remaining` + info `qty_*_m`. Jangan pernah menulis "(m)" mati di layar.
- `ROLL_UOM` **tidak lagi** memetakan `rol`/`gulung` → `meter`. Ember penyimpanan ditentukan
  `WEIGHT_UOMS` supaya dokumen lama tetap terbaca di ember yang sama.
- Pengeluaran gulungan **wajib** satuan gulungan itu (satuan lain → 400).
- **Order cutting wajib `model_id`** dari `rahaza_models` (+ `variant_id` opsional milik model itu).
  `style_name`/`style_sku`/warna/size DITURUNKAN dari master; `PUT` menolak `style_name`.
  Dua gate lama (`verify_fase_h5_h6_roll.py`, `verify_fase_h6b_cutting_issue.py`) sudah disesuaikan
  memakai helper `any_model_id(token)`.
- **Harga satuan lahir dari pembelian**: GR (`routes/warehouse.py`, dipakai juga oleh bridge
  `/api/wms/legacy/receiving`) memanggil `core/accessory_valuation.apply_receipt_cost` dengan harga
  PO; `qty_before` HARUS dibaca sebelum `stock_service.add`. `PUT /api/rahaza/materials` mengabaikan
  `unit_cost` dan selalu membalas `harga_satuan_catatan`. `POST` masih menerima harga awal
  (`cost_method="opening"`). Koreksi manual hanya lewat Valuasi HPP.

### Gate & bukti
- Gate baru **INV-F35** `scripts/verify_uom_roll_dan_style_master.py` (10 invarian, memulihkan data
  sendiri). `bash scripts/gate.sh` → **53 gate VERDICT HIJAU**.
- Penguji independen: `test_reports/iteration_86.json` (menemukan bug HIGH dialog Detail Roll kosong
  — `handleView` salah bentuk state, sudah diperbaiki) dan **`iteration_87.json` HIJAU 100%**
  (rata-rata bergerak terbukti: 100@10.000 → 10.000; +100@20.000 → **15.000**).
- Regresi rata-rata bergerak: `backend/tests/test_iter87_moving_average_hpp.py` (5 test, self-cleanup).

### SISA (urutan berikutnya)
- **Simpan Preset Ekspor (P2)** · **Rekap Retur (P3)** (masih dari sesi #29).
- Pemilik belum mengisi ambang stok apa pun (334 material) — layar & usulannya sudah siap.
- Pertimbangan lanjut: tampilkan BOM model di dialog cutting supaya "Rencana Pemakaian Kain" tidak
  ditebak manual (sudah ditawarkan, pemilik belum menjawab).


## 0-TERBARU-4. SESI 2026-08-21 #29c — W5 (SURAT JALAN CMT → DA) & W3 (ALERT STOK) ✅ TUNTAS

### W5 — Surat Jalan CMT → DA
- Jenis dokumen `cmt-delivery-note` di `data/pdf_doc_registry` (10 kolom; **No & Qty Kirim wajib**,
  kolom hasil QC = PILIHAN), landscape, TTD bawaan Pengirim(CMT)/Pemeriksa QC/Penerima(Gudang DA).
- SSOT **`core/cmt_delivery_note.py`**: `ensure_number()` **idempoten per penerimaan** (cetak ulang
  = nomor sama, `print_count` bertambah) + `build_lines()` yang me-resolve **serial** dari
  `po_items`/`buyer_shipment_items` (baris penerimaan TIDAK menyimpan serial — jangan lupa ini).
- Seri nomor `cmt_delivery_notes.dn_number` = `SJ-CMT/{YYYY}/{MM}/{SEQ:4}` (auto_only, terdaftar di
  Penomoran Dokumen) + masuk daftar index unik `utils/counters.UNIQUE_NUMBERED_FIELDS`.
- Endpoint: `GET /api/export-pdf?type=cmt-delivery-note&id=<receipt_id>[&cols=...]` (400 tanpa id,
  404 id karangan). Layar: tombol **Surat Jalan** per baris `DAReceiveFromCMTModule.jsx`
  (`data-testid=receipt-surat-jalan-<kode>`) → `PdfColumnPicker` dengan prop baru **`defaultKeys`**.
- Default tercentang = versi kirim murni (7 dari 10 kolom). Boleh dicetak walau QC belum selesai.

### W3 — Alert stok hidup
- SSOT **`core/stock_thresholds.py`** = satu definisi "rendah" (ambang `min_stock_qty` → `min_stock`
  legacy → `min_stock_percentage`; `reorder_point` = titik pesan ulang; stok on-hand KANONIK).
  Dipakai: `/api/warehouse/alerts`, `rahaza_alerts.check_low_stock`, `/materials?low_stock=true`,
  `/materials/reorder-alerts`, `/warehouse/smart-reorder`. **Jangan bikin definisi keempat.**
- Endpoint baru `GET /api/rahaza/stock-thresholds`, `/summary`, `POST /stock-thresholds/bulk`
  (`routes/rahaza_inventory_thresholds.py`).
- Layar baru **Ambang Stok** = tab ke-3 Master Item (`StockThresholdsModule.jsx`,
  `data-testid=tab-thresholds`): input min & titik pesan ulang, usulan dari pemakaian nyata 30 hari
  (tanpa pemakaian ⇒ TIDAK diberi usulan), "Pakai semua usulan", simpan massal.
- Layar Alert & Reorder kini JUJUR: menyebut berapa material belum berambang + tautan
  `#wh-master=thresholds` (kontrak `hub_tab_<id>`). **Catatan navigasi:** id modul Alert & Reorder
  adalah **`warehouse-smart`**, BUKAN `wh-smart`.
- Keadaan data saat serah-terima: **333 material, 0 berambang** (pemilik yang memutuskan angkanya;
  layar & usulannya sudah siap).

### Gate
- Gate baru **INV-F33** `scripts/verify_surat_jalan_cmt.py` (10 invarian) dan **INV-F34**
  `scripts/verify_alert_stok_hidup.py` (9 invarian) — keduanya memulihkan data hidup sendiri.
- `bash scripts/gate.sh` → **VERDICT HIJAU 52 gate**. Penguji layar independen: 13/13 API pass,
  alur UI penuh lolos (laporan: `test_reports/iteration_85.json`).

### SISA (urutan pemilik berikutnya)
- **Simpan Preset Ekspor (P2)**: simpan kombinasi kolom favorit sebagai preset bernama.
- **Rekap Retur (P3)**: analisa alasan retur terbanyak per produk.
- Pemilih kolom bisa dipasang ke dokumen lain (Invoice Maklon, Pengiriman Vendor) dengan pola sama.
- Pemilik belum mengisi ambang stok apa pun — bila ia minta bantuan, gunakan tombol
  "Pakai semua usulan" (hanya 4 material yang punya pemakaian 30 hari terakhir di DB ini).


## 0-TERBARU-2. SESI 2026-08-20 #29b — W1 (TABEL STOK) & W2 (EKSPOR KOLOM) ✅ TUNTAS

### W1 — Tabel stok lengkap & bisa disamakan dengan Master Item
- `GET /api/rahaza/material-stock` dan `GET /api/wms/stock/unified` kini mengirim identitas MASTER:
  `material_code`, `category_name`, `color_name`, `option_name`, `size_code`, satuan, lokasi
  (kode+nama). **Jangan pernah** menghitung ulang warna/opsi dari string SKU — sumbernya master.
- Parameter baru: `include_zero=1` (barang master tanpa baris stok ikut tampil, `no_stock_row:true`)
  dan filter `category` · `color` · `option` · `material_type` (+ `facets` untuk isi dropdown).
- Layar: `UnifiedInventoryModule.jsx` & `RahazaStockModule.jsx` — kolom **Kategori · Warna · Opsi**,
  filternya, saklar **"tampilkan juga yang stoknya 0"**, dan **UUID `material_id` dibuang** dari
  tabel/dialog/**ekspor CSV** (header ekspor kini "Kode Barang").
- Angka bukti: **26 baris stok FG → 322 baris** saat saklar dinyalakan (296 barang belum punya stok).
  Inilah akar keluhan "tabel FG tidak sinkron" — bukan duplikasi data.

### W2 — Ekspor fleksibel: pemakai memilih kolom saat mencetak (fokus Maklon & Produksi)
- Backend: `/api/export-pdf?...&cols=no,serial,product,qty` = pilihan **sekali cetak** (menang atas
  template & konfigurasi bernama, tidak mengubah setelan global). Kunci divalidasi ke SSOT
  `data/pdf_doc_registry`; kolom **wajib** selalu ikut; kunci karangan diabaikan (bukan 500).
- **Bug lama ditutup**: `_filter_columns` ganda dihapus dari `routes/operations_pdf.py` ⇒ memakai
  konfigurasi kolom pada laporan produksi tidak lagi **500 "list index out of range"**.
- Frontend: komponen baru **`components/erp/pdf/PdfColumnPicker.jsx`** (dialog "Kolom PDF": daftar
  kolom dari katalog, kolom wajib terkunci, pilihan diingat per jenis dokumen) — terpasang di
  **Laporan Produksi/Maklon** (`ReportsModule`) dan **SPP Produksi/Maklon** (`ProductionPOModule`).
- Bukti dari layar: pilih No·Serial·Produk·Qty → PDF terunduh berisi TEPAT 4 kolom itu (nomor seri
  `SN-MK1-A` tercetak), kolom Vendor/Warna/HPP/SKU/Size hilang, kop surat utuh.

### Gate
- Gate baru **INV-F32** `scripts/verify_tabel_stok_dan_ekspor_kolom.py` (11 invarian, **read-only**)
  + terdaftar di `scripts/gate.sh`. `bash scripts/gate.sh` → **VERDICT HIJAU 50 gate**.

### SISA (urutan pemilik)
- **W3 — Hidupkan Alert Stok**: ambang `min_stock_qty`/`reorder_point` diisi dari **Master Item**
  (333/333 masih 0), alert tampil di `#wh-smart` + badge dashboard, lalu **buktikan alert berbunyi**.
  Catatan: kolom "MIN STOK" pada tabel stok sekarang sudah membaca `min_stock_qty` — begitu ambangnya
  diisi, statusnya (OK/Low) langsung ikut hidup.
- Menyusul: pemilih kolom bisa dipasang ke dokumen lain (Surat Jalan, Invoice Maklon, Pengiriman
  Vendor) dengan pola yang sama — `PdfColumnPicker` + `cols=`; backend-nya sudah universal.


## 0-TERBARU. SESI 2026-08-19 #29 — W4 "SAMBUNGKAN RETUR" ✅ TUNTAS (retur pembeli → gudang → stok)

**Keputusan pemilik yang dipakai** (dijawab di awal sesi):
- Retur pembeli dari Marketing **OTOMATIS** membuat pekerjaan Retur Fisik di Gudang **dan otomatis
  restock** saat retur dibuat (bukan menunggu verifikasi manual).
- Ada **pilihan kondisi barang**: **Baik** → stok masuk `ZNA-FG` (ikut stok jual) · **Rusak** → stok
  masuk `ZNA-KARANTINA` (dikecualikan dari stok jual oleh K-6a ⇒ tidak bisa terjual).
- Ekspor fleksibel (W2) nanti **fokus Maklon & Produksi**. Alert stok (W3): ambang diisi di
  **Master Item** + alert di menu Alert & Reorder + badge dashboard.

### Akar masalah yang TERUKUR sebelum diperbaiki
- `marketing_returns` = **30** dokumen retur pembeli NYATA · `wh_returns` = **0** ⇒ layar Retur Fisik
  kosong selamanya.
- Jembatan lama: manual, hanya status approved/completed, dan mengirim `sku_code=""` + `qty=1`.
- `POST /api/wh/returns/{id}/resolve` "Restock ke Gudang" menulis ke **`rahaza_fg_inventory`
  (koleksi MATI, 0 dokumen)** dengan `sku_code` kosong ⇒ **stok tidak pernah bertambah, 0 ledger**.

### Yang dikerjakan
1. **SSOT baru `backend/core/returns_bridge.py`** — resolusi identitas barang tanpa menebak
   (`catalog_item_id` → `sku` → `marketing_orders.items[].fg_material_id`), `ensure_wh_return`
   idempoten, `auto_process` (Received→Inspected→Resolved otomatis + timeline), `restock` lewat
   **`core/stock_service.add`** dengan penjaga atomik `restocked`, `sync_all` (backfill), dan
   `refresh_catalog_cache` (stok jual katalog ikut disegarkan).
2. **Marketing** (`routes/marketing_returns_routes.py`): `POST /api/marketing/returns` menerima
   `item_condition` + `qty` lalu memicu jembatan otomatis; `approve` sebagai jaring pengaman;
   `reject` memberi PERINGATAN bila stok sudah bertambah; endpoint baru
   `POST /api/marketing/returns/sync-to-warehouse`; jembatan manual lama kini memakai SSOT (boleh
   status `pending`).
3. **Gudang** (`routes/dewi_wh_returns.py`): jalur stok mati DIBUANG; `resolve` memakai SSOT + aksi
   baru **"Karantina (Rusak)"**; endpoint baru `GET /returns/marketing-gap`,
   `POST /returns/sync-marketing`, `POST /returns/{id}/quick-restock`, `POST /returns/{id}/relink`;
   `POST /returns` (catat manual) kini menautkan ke MASTER (`material_id`) — INV-F14.
4. **Layar**: `WHReturnsModule.jsx` (spanduk angka jembatan, tombol *Tarik Retur dari Marketing*,
   kolom **Asal** & **Efek Stok**, aksi cepat *Terima & Restock* dengan pilihan Baik/Rusak, blok
   *Tautan Master Barang & Stok*, tombol *tautkan ulang*), `ReturnsRefundsModule.jsx` (pemilih
   **Kondisi Barang** + **Qty**, penjelasan efek stok, tombol *Kirim ke Gudang & Masukkan Stok*),
   `masters/MasterSelects.jsx` (**FGMaterialSelect** baru).
5. **Gate baru INV-F31** `scripts/verify_jembatan_retur_marketing_gudang.py` (15 invarian,
   self-cleaning) + terdaftar di `scripts/gate.sh`.

### Bukti angka (sebelum → sesudah)
| Ukuran | Sebelum | Sesudah |
|---|---|---|
| `wh_returns` | **0** | **22** (21 sudah restock) |
| Retur pembeli tanpa pekerjaan gudang | 22/22 | **0/22** |
| Baris ledger stok dari retur | **0** | **21** |
| Total stok `rahaza_material_stock` | 33.482 | **33.503** (+21 pcs retur benar-benar masuk) |
| Retur ambigu (pesanan multi-baris) | tidak terlihat | **1** ditandai `needs_manual_resolution`, stok TIDAK ditebak |

`bash scripts/gate.sh` → **VERDICT HIJAU** (49 gate, termasuk INV-F31 15 invarian). Testing agent
iterasi 82 & 83 dijalankan; 2 "temuan backend" ternyata **false positive** (harness uji mereka
menganggap HTTP 400 yang benar sebagai kegagalan) dan 1 "temuan CRITICAL" (kondisi Rusak jadi Baik)
terbukti **kesalahan otomasi** — diverifikasi ulang lewat DOM: kondisi *Rusak* + qty 2 ⇒ baris gudang
berbunyi **"+2 karantina"** dan layar Marketing menyatakan **"Efek stok: +2 karantina
(ZNA-KARANTINA)"**. Seluruh data uji dibersihkan (stok kembali 33.503).

### SISA untuk sesi berikutnya (urutan pemilik)
- **W1 — Tabel FG lengkap**: kolom Kategori/Warna/Opsi + filter, buang `material_id` (cek juga ekspor
  CSV), saklar "tampilkan stok 0". Sumber data SUDAH ada di dokumen FG (`category_name`,
  `color_name`, `option_name`).
- **W2 — Ekspor fleksibel** (fokus **Maklon & Produksi**, nomor serial produksi WAJIB jadi pilihan;
  jaga INV-F17 & INV-F26).
- **W3 — Hidupkan Alert Stok**: ambang `min_stock_qty`/`reorder_point` diisi di **Master Item**
  (333/333 masih 0), alert di `#wh-smart` + badge dashboard, lalu BUKTIKAN alert berbunyi.
- Catatan: 1 retur ambigu (`RET-20260819-011`, pesanan `585044253894673420` 2 baris) menunggu pemilik
  memilih produknya di retur Marketing → lalu tekan *tautkan ulang* & *Terima & Restock*.


## 0-BARU. SESI 2026-08-19 #28 — IDENTITAS BARANG + BUG FATAL PENERIMAAN BARANG ✅ TUNTAS

**Environment dipulihkan** dari `github.com/akskxuyd/DA`:
`git clone --depth 1` → `rsync -a --exclude='.env' --exclude='.git' --exclude='node_modules' /tmp/DA/ /app/`
→ `EMERGENT_LLM_KEY=... bash /app/scripts/bootstrap.sh` (**60 detik**, backend health OK, frontend
static bundle 200, 6 akun login HTTP 200). **Frontend WAJIB mode static bundle** — setelah mengubah
`frontend/src` jalankan `bash /app/scripts/rebuild_frontend.sh` lalu
`sudo supervisorctl restart frontend` (±60 detik, TIDAK ada hot reload).

### Yang diselesaikan sesi ini
1. **Verifikasi todo list sesi #20** yang ditanyakan pemilik — SEMUA terbukti sudah selesai
   (INV-F29 hijau 19 invarian, gate.sh hijau 47 gate). Tidak ada yang perlu dikerjakan ulang.
2. **Sisa masalah sesungguhnya ditutup**: jembatan SKU ada tapi tidak terpakai —
   **0/601 → 601/601** baris pesanan tertaut, **553 pesanan** antrean gudang jadi siap,
   `sync-audit` **MERAH skor 0 → HIJAU skor 79**. Lewat fitur baru **Onboarding Produk per PRODUK**
   (8 keputusan, bukan 83) + **dimensi ke-3 varian "Opsi"**.
3. **BUG FATAL pemilik ditutup**: Penerimaan Barang (GR) dari PO — qty diterima selalu 0 karena
   **kolomnya tidak ada** di modal Detail. Sekarang bisa diisi, plus pemilih Lokasi Tujuan, dan
   penjaga 400 di API (qty 0 & lokasi kosong).
4. **2 kebocoran `gate.sh` ditutup** — alat ukur dulu menggerus 10 pcs aksesoris nyata per run dan
   meninggalkan kartu stok yatim + rujukan stok rusak.

### YANG WAJIB DIKETAHUI SEBELUM MENYENTUH IDENTITAS BARANG
1. **SSOT-nya `backend/core/variant_identity.py`.** Jangan menambah kamus warna/ukuran/opsi di tempat
   lain. `sku_bridge.parse_variation` (2 dimensi) masih ada untuk kompatibilitas — **jangan dipakai
   untuk keputusan baru**, ia yang dulu menabrakkan 63 SKU.
2. **Nuansa warna TIDAK boleh digabung.** `COLOR_TRANSLATE` hanya memuat sinonim BAHASA
   (white=Putih). `Butter Yellow` bukan `Kuning`, `Polka Black` bukan `Hitam`. Warna yang belum ada
   **disalin apa adanya** (menyalin ≠ menebak) dan pemilik melihatnya di pratinjau lebih dulu.
3. **JANGAN pakai pencocokan substring warna.** Gate V2b menolaknya secara statik.
4. **Kode ketidakhadiran tidak masuk SKU**: opsi `NA` & warna `TDI` dilewati `make_sku`. Ini yang
   menjaga 330 SKU varian lama tidak berubah. Kalau ini dilanggar, SKU/FG/katalog lama ikut berubah.
5. **Index unik varian sekarang 4 sumbu** (`model_size_color_option_unique`). Index lama 3 sumbu
   sudah DILEPAS — ia menolak varian ber-opsi berbeda.
6. **Nama model tidak boleh diketik di layar** (gate INV-F14). Ia diturunkan `propose_model_name`
   dan hanya ditampilkan; pemilik MENUNJUK model master lewat pemilih bila produknya sudah ada.
7. **Onboarding punya rollback**: `POST /api/variant-onboarding/rollback` (admin) hanya menghapus
   dokumen ber-`created_via='variant_onboarding'`. Dipakai POC & gate supaya bisa diulang.

### YANG WAJIB DIKETAHUI SEBELUM MENYENTUH PENERIMAAN BARANG (GR)
1. GR dari PO **memang** lahir `received_qty=0.0` — itu benar (barang belum dihitung). Yang salah
   dulu adalah tidak adanya kolom untuk mengisinya. Jangan "memperbaiki" dengan mengisi otomatis:
   gunakan tombol **"Terima semua sesuai PO"** supaya pengisian tetap tindakan sadar pemilik.
2. `PUT /api/wms/legacy/receiving/{id}` sekarang **MENOLAK 400** bila (a) total received+rejected = 0,
   (b) `location_id` kosong. Skrip/gate yang mengkonfirmasi GR **wajib** mengirim `location_id`.
3. Jalur konfirmasi memetakan `reject_reason` (UI) → `reject_reasons[]` (kontrak karantina). Kalau
   menambah field reject baru, petakan di KEDUA jalur (`handleCreate` dan `handleStatusChange`).

### ATURAN ALAT UKUR (baru, jangan dilanggar)
Setiap gate/skrip uji yang **memotong stok** atau **membuat master turunan** wajib:
mengembalikan stok yang dipotong (pakai angka yang persis dipotong), dan menghapus **stok + kartu
stok** milik dokumen turunannya — bukan hanya masternya. Rujukan kartu stok tersimpan **bersarang**
(`ref.ref_id`), bukan `ref_id` di tingkat atas. Invarian **INV-F30 V15** menjaga ini.

### Keadaan data preview saat serah-terima
- 8 model produk nyata sudah lahir (`BLS-0001` Jennifer Blouse 40 varian, `SET-0001`, `BLS-0002`,
  `DRS-0001`, `BLS-0003`, `AKS-0003`, `DRS-0002`, `BLS-0004`) · 83 pemetaan SKU · 70 varian baru.
- **GR-00006 DIBIARKAN berstatus `draft`** (dari PO-20260819-003, 50 pcs) agar pemilik bisa mencoba
  sendiri alur Penerimaan Barang yang baru. Hapus bila tidak diperlukan.
- **GR-00001 DIBIARKAN** (`received_qty=0`, status `received`) sebagai JEJAK bug lama sebelum
  perbaikan. Bukan regresi.
- `LEGACY-NOLINK-001` & `DEMO-*` adalah fixture yang SENGAJA ada — jangan dihapus. Audit
  melaporkannya sebagai **INFO B3d**, bukan cacat.
- Stok `ACC-DA-LBL` = 1900 (baseline 1800 + 100 diterima) setelah 40 pcs yang tergerus gate
  dipulihkan.

### Bukti yang bisa diulang
```bash
python3 test_core_sku_identity.py                          # POC: 22 lulus / 0 gagal
python3 scripts/verify_identitas_varian_3dimensi.py        # INV-F30: HIJAU 23 invarian
bash scripts/gate.sh                                       # VERDICT HIJAU, 48 gate
curl -s -H "Authorization: Bearer $TOKEN" .../api/sync-audit/report   # HIJAU skor 79
```

### Belum dikerjakan (kandidat sesi berikutnya)
- **P1** Kode Supplier masih `policy_pending` (satu-satunya sisa Fase G) — menunggu keputusan pemilik:
  berpola `SUP-0001` atau bebas mengikuti identitas supplier.
- **P1** F3/F4: rapikan 5 PDF tersering (SPP · Invoice · Slip Gaji · Picklist · SJ Vendor) ke pola
  `_pdf_data_table`.
- **P2** 240 varian demo lama belum masuk katalog jual · 310 varian belum punya baris stok.
- **P2** `production_job_items.material_id` & `po_items.material_id` kosong (temuan audit E2).
- **P2** Sisa INV-F28: pelacak SJ pengganti belum menampilkan HASIL inspeksi (berapa pcs lolos/cacat).
- **Fitur AI** tetap seperti sebelumnya (bukan lingkup sesi ini).

---

## HANDOFF LAMA — Konsolidasi Gudang DA37 (CV. Dewi Aditya)
_Terakhir diperbarui: **2026-07-26 (sesi lanjutan #6 — FASE IA Portal Produksi TUNTAS**, environment dipulihkan dari repo `fajajnababaja/da`). Dokumen ini untuk agent sesi berikutnya. BACA SAMPAI HABIS SEBELUM MENGUBAH APA PUN. Bagian **0-BARU** di bawah = keadaan TERKINI._

---

## 0-BARU. SESI 2026-07-26 #6 — FASE IA PORTAL PRODUKSI ✅ TUNTAS (A · B1 · B2 · B3 · C · C2 · D · E · E2)

**Environment dipulihkan** dari `github.com/fajajnababaja/da`:
`git clone` → `rsync -a --exclude node_modules --exclude .git --exclude .env <clone>/ /app/` →
`cd /app/frontend && yarn install` (JANGAN `--frozen-lockfile`) → `pip install -r backend/requirements.txt` →
tambahkan **`JWT_SECRET`** & **`EMERGENT_LLM_KEY`** ke `backend/.env` (backend tidak start tanpa JWT_SECRET) →
`sudo supervisorctl restart backend` → `bash scripts/seed_demo_all.sh` → `cd frontend && yarn build` +
`sudo supervisorctl restart frontend` (**mode static bundle, TIDAK ada hot reload**).

**Titik berhenti sesi sebelumnya:** Fase A–C selesai (commit `d97fe65`); C2 masih jalan; D/E/E2 belum.

**Hasil sesi ini** (detail + bukti: `docs/PROPOSAL_IA_PRODUKSI.md` §5, ringkas: `plan.md` blok "SESI 2026-07-26 (lanjutan #6)"):
- **C2** bundle dibangun ulang; Portal Produksi terbukti 4 section datar (Master Data · Produksi Internal · Monitoring Progress · Keuangan & Analitik), 20 pintu.
- **D** 5 guard baru di `scripts/guardrails/check_nav_map.py`: `NAV-FLAT`, `NAV-MAX(>8)`, `NAV-LABEL`, `NAV-DUPTAB`, `NAV-DEADCALL` + pustaka baru `scripts/lib/fe_static.py`.
  · **Gate ini menjalankan self-test sintetis SETIAP run** — kalau ada guard yang diam, gate MERAH (`NAV-GUARD-DEAD`). Jalankan manual: `python3 scripts/guardrails/check_nav_map.py --selftest`.
  · `NAV-DEADCALL` memakai **OpenAPI runtime + AST**; kalau backend mati temuannya turun jadi WARN.
- **D2** 5 pelanggaran nyata diperbaiki → **Portal Keuangan sekarang 6 section DATAR** (dulu 3 section bergrup 3 tingkat), label tanpa tanda kurung (`Retur Fisik`, `PIUTANG AR`, `PENGADAAN P2P`).
- **Pintu Invoice (Tagihan CMT)** diisi lewat alur nyata: `python3 scripts/seed_demo_cmt_billing_internal.py` (idempoten, sudah dipanggil `scripts/seed_demo_all.sh`) → PO-INT-DEMO-4 → 2 penerimaan CMT → PAY-CMT-00001 (Rp 1.200.000, **belum posting**) & PAY-CMT-00002 (Rp 975.000, **posted** JE ke akun 5-231).
- **3 bug nyata lain ditutup** (lihat §5.2 proposal): akun biaya CMT salah (`6-2200` = *Listrik & Air Kantor*!) → `5-231` internal / `7-120` maklon + `backend/migrations/fix_cmt_ap_posting_profile.py`; total header `cmt_receipts` tak dihitung saat POST `/lines` (semua tagihan ber-flag varian palsu) + `backend/migrations/backfill_cmt_receipt_totals.py`; job internal tak mewarisi pelaksana CMT dari PO.
- **Verifikasi:** `gate.sh` **12/12 HIJAU** · `testing_agent_v3` iteration_179 backend 19/19 & 0 critical · `tests/verify_ia_c_backend_fixes.py` **8/8** (self-cleaning) · audit drift: 0 artefak uji tersisa · baseline aksesoris SSOT Rp 9.663.750 utuh.

**Yang PERLU diketahui sebelum menyentuh nav portal lain:**
1. Guard baru **memblokir** section bergrup (3 tingkat), section >8 pintu, label bertanda kurung/lebih dari 3 kata bermakna/HURUF BESAR SEMUA, pintu yang isinya sama dengan tab pintu lain, dan pintu yang komponennya memanggil endpoint tak ada. Rancang nav baru dengan aturan ini sejak awal.
2. Portal berikutnya sesuai usulan proposal: **Keuangan → Gudang+Aksesoris → SDM → Marketing → Manajemen** (Keuangan baru "diratakan", belum dirancang ulang isinya).
3. Data demo pintu Invoice dipakai sebagai baseline: **jangan** posting AP PAY-CMT-00001 lalu meninggalkannya — kalau perlu diuji, kembalikan (hapus JE + kosongkan `gl_je_id/gl_je_number/gl_posted_at`) atau jalankan ulang seeder di DB bersih.
4. `DEMO-ACC-*` (baseline aksesoris) **tidak punya seeder** di repo — di environment baru materialnya memang tidak ada. Bukan regresi.

---

## 0-PRA-BARU. SESI 2026-07-25 #3 — FASE 6 (KARANTINA QC / INV-8) ✅ TUNTAS TERMASUK STEP 6.5
**Environment dipulihkan** dari fresh clone `jaananbaba/da` → `rsync -a --exclude='.git' --exclude='.env' --exclude='node_modules' /tmp/<clone>/ /app/` → `EMERGENT_LLM_KEY=... bash /app/scripts/bootstrap.sh` (105s, OK). **Frontend WAJIB mode static bundle** — setelah ubah `frontend/src` jalankan `bash /app/scripts/rebuild_frontend.sh` (±2 menit, TIDAK ada hot reload).

**2 kendala restore yang WAJIB diketahui agent berikutnya:**
1. `yarn install --frozen-lockfile` (dipakai `bootstrap.sh`) **GAGAL** karena `frontend/yarn.lock` di repo out-of-sync → `@simplewebauthn/browser` tak terpasang → **build FE gagal**. Solusi: `cd /app/frontend && yarn install` (tanpa frozen).
2. Repo **tidak punya `frontend/eslint.config.js`** padahal `eslint@9` mewajibkan flat config → `npx eslint` selalu mati. **Sudah dibuat** di sesi ini (0 error / 47 warning lama). Jangan dihapus.
3. ⚠️ Proses build background bisa **mati** kalau sesi tool-nya terputus, dan CRA sudah menghapus isi `build/` di awal → preview jadi kosong. Kalau itu terjadi: jalankan ulang build lalu `sudo supervisorctl restart frontend`.

**FASE 6 SELESAI & TERVERIFIKASI** (detail lengkap + daftar bug di `/app/plan.md` → bagian "6.5 — HASIL PENGUJIAN & PERBAIKAN"):
- `scripts/verify_phase6_quarantine.py` = **48 PASS / 0 FAIL**; testing agent iteration_164 (backend 66/68) + iteration_165 (backend 15/15 = 100%); verifikasi UI manual main agent untuk SEMUA alur aksi; regresi nav Portal Gudang **22/22 modul bersih**.
- **7 bug nyata diperbaiki**, yang terpenting:
  - **P1 `App.js::handleLogin` mengabaikan deep-link `#module`** → semua bookmark modul mendarat di "Pilih Portal" setelah login (regresi fitur deep-link Session #11.14). SUDAH DIFIX.
  - **P2 RBAC karantina pakai nama role HANTU** (`gudang`, `staff_gudang`, `warehouse`, `keuangan`, dll. tidak ada di master role 21 entri; `check_role` = exact match) → role gudang NYATA (`spv_packing`, `tim_packing`, `admin_aksesoris`) selalu 403. SUDAH DISELARASKAN dengan master role + `PORTAL_ACCESS['warehouse']`.
  - **P2 `POST /quarantine/manual` memaksa `unit='pcs'`** (kain 'm' tampil 'pcs') + mengabaikan `reject_reasons[]`. SUDAH DIFIX.
- **Akun baru:** `packing@dewiaditya.id` / `Dewi@123` (role `tim_packing`) = fixture RBAC negatif (boleh Lepas/Retur, DILARANG Scrap). Lihat `memory/test_credentials.md`.
- **Data uji:** `scripts/seed_quarantine_ui_demo.py` (+ `--cleanup`) membuat data lewat ALUR NYATA. DB sudah dikembalikan ke baseline bersih (0 karantina / 0 GR / 0 JE / 0 baris JE / 0 ledger).

**KEPUTUSAN USER (2026-07-25 #3) untuk urutan kerja berikutnya:**
1. **3 gantungan AKSESORIS** dari `memory/PRODUKSI_E9_AKSESORIS.md`: **ACC-3** (pindahkan menu "Peminjaman" dari domain Aksesoris → domain Aset), **ACC-2** (wajibkan `material_id` pada aksesoris BOM), **ACC-1** (auto-generate kebutuhan aksesoris dari BOM saat PO produksi dibuat).
2. Lalu **Step 6.6** (rekonsiliasi baris stok skema lama A/B/C + rename internal `yarn_*` → field netral dengan alias kompatibilitas).
3. Push GitHub: **TIDAK** (preview only, default).

---

## 0-PRA. SESI 2026-07-25 #2 — FASE G+ (P0 fix) ✅ SELESAI & TESTED
- **Environment:** fresh clone repo `babakaana/da` → `rsync -a --exclude='.env' --exclude='.git' --exclude='node_modules' /tmp/<clone>/ /app/` → `EMERGENT_LLM_KEY=... bash /app/scripts/bootstrap.sh` (deps + build + seed + verifikasi login 6 akun) = OK. **Frontend WAJIB mode static bundle** (`package.json start = node static_server.js`; ubah `frontend/src` → `bash /app/scripts/rebuild_frontend.sh`; TIDAK ada hot reload). Baca `memory/PREVIEW_STABLE_MODE.md`.
- **P0 FIXED:** `dewi_accessories_opname.py::_wh_session_to_acc` tak memetakan field ringkasan → UI list Opname Aksesoris selalu "0 jurnal keuangan / nilai selisih 0". Serializer kini mengirim `total_variance_items/value`, `je_posted`, `je_failed(+items)`, `adjustments_made`, `approved_by/at`, `submitted_by/at`, `rejected_by/at`, `reject_reason`, `raw_status`, `summary`.
- **FASE G+ (penutup Fase G):** (1) transparansi `je_failed` di approve + peringatan amber di FE; (2) **harga satuan `unit_cost` di master aksesoris** (create/update/list + kolom "Harga Satuan"/"Nilai Stok" + form) — akar masalah JE selisih tak terbentuk; (3) **regresi `stock_status`** pada serializer item aksesoris di-fix (dulu semua item tampil badge "Habis"); (4) dead-code `_material_to_acc_item` duplikat dihapus dari 6 file router aksesoris.
- **Bukti:** `/app/scripts/verify_phase_g_acc_opname.py` **45/45 PASS**; `testing_agent` iteration_163 backend 100% + frontend 100%, 0 bug; screenshot `#accessories-opname` & `#accessories-master-stock`.
- **Artefak QA di DB preview:** item `QA-PRICE-1/QA-BTN-1/QA-ZIP-1` + sesi `OPNAME-000x..001x` (Completed/Rejected/Cancelled). Aman dihapus bila user setuju.
- **Opsi lanjutan (menunggu keputusan user):** (a) purge artefak QA; (b) **FASE 6** (INV-8 QC→stok: hanya qty accepted masuk stok, reject → quarantine; rekonsiliasi baris lama A/B/C; rename internal `yarn_*`); (c) eksekusi `scripts/migrate_drop_warehouse_ledger_legacy.py` di DB produksi user (di preview: koleksi legacy sudah tidak ada → no-op); (d) fitur/area baru sesuai kebutuhan user.

---

## 0. TL;DR (baca ini dulu)
- Proyek: merapikan sistem gudang/inventory ERP agar **1 model lokasi, 1 kebenaran stok, tanpa menu/alur ganda**.
- Sesi ini menyelesaikan: **Fase D** — (D1) **fix mismatch Maklon** (`MaklonMaterialIssuePanel`: dropdown lokasi → `/api/rahaza/storage-locations`, `checkStock` diperbaiki; backend loc-name via `location_resolver`); (D2) **smart-reorder kanonik** (`/api/warehouse/smart-reorder`: on-hand via `stock_service.onhand_map`, konsumsi dari `rahaza_stock_ledger`); (D3) audit undo-history → catatan Fase F. **Agent-tested (iteration_159: backend 11/11, frontend smoke, 0 bug).**
- Sebelumnya (sesi yg sama): **Known Issue §5** ✅ + **Fase E2** ✅ (iteration_157) + **Fase C** ✅ (iteration_158).
- **STATUS: SEMUA FASE KONSOLIDASI GUDANG A–G TUNTAS ✅** (agent-tested iteration_161 + iteration_162, 100%). Tidak ada fase konsolidasi tersisa. Opsi lanjutan (bila diminta user): (a) eksekusi `scripts/migrate_drop_warehouse_ledger_legacy.py` di DB produksi (arsip dulu) utk benar-benar drop koleksi legacy; (b) fitur baru sesuai kebutuhan user.
- **Fase G ✅ SELESAI (2026-07-25):** Opname Aksesoris (`dewi_accessories_opname.py`) → standar Opname3. Flow `open →(submit)→ pending_approval →(approve|reject)`. approve = GATE SUPERVISOR (`check_role`) → `_add_stock` kanonik + `_log_movement` + `post_inventory_adjust` (JE inventory_adjust Dr 1-1401/Cr 6-2400). FE `AccessoryModule.StokOpnameTab`: Ajukan + Setujui/Tolak + badge/ringkasan. isolated 14/15 + agent iteration_162 22/22.
- **Fase F+ ✅ SELESAI (2026-07-25):** retire `warehouse_locations` — `get_locations` KANONIK (list_storage_locations + wh_positions), CRUD location → 410, dropdown ReceivingModule → `/api/rahaza/storage-locations`, script drop +`warehouse_locations`. DIPERTAHANKAN: `warehouse_receiving` (GR).
- **Fase F ✅ SELESAI (2026-07-25, sesi lanjutan, agent-tested iteration_161 22/22 + isolated undo 13/13):** (F1) undo-history/undo/restore `dewi_warehouse_smart.py` KANONIK — baca `rahaza_stock_ledger` (op='adjust') + reversal `stock_service.adjust` (undo new=current−delta, restore new=current+delta), stop baca `warehouse_movements`/tulis `rahaza_materials.total_qty`; `/alerts` low-stock pakai `onhand_map`. (F2) hapus writer legacy `warehouse.py` `/putaway` & `/opname` + helper `_sync_to_material_stock` (→404). (F3) reader legacy (`get_stock`/summary/`get_movements`/`dashboard`/`dashboard-kpi`) → KANONIK `rahaza_material_stock`+`rahaza_stock_ledger`; `delete_location` guard kanonik; bridge `/api/wms/legacy/*` tetap 200. (F4) `scripts/migrate_drop_warehouse_ledger_legacy.py` archive→drop `warehouse_stock/movements/putaway/opname` (idempotent, --dry-run/--rollback). (F5) hapus dead code FE `LocationsModule.jsx`. **DIPERTAHANKAN: `warehouse_locations` (dropdown ReceivingModule) & `warehouse_receiving` (GR).**
- Sebelumnya sudah beres: **Fase A** (quick win UI), **Fase B** (struktur gudang kanonik + peta migrasi), **Fase E1** (bongkar monolit "Scanner Barcode").
- **PENTING (lingkungan baru):** repo di-clone ke environment fresh. `backend/.env` repo di-gitignore, jadi **JWT_SECRET & EMERGENT_LLM_KEY ditambahkan manual** ke `/app/backend/.env` (server tak mau start tanpa JWT_SECRET). **DB fresh/kosong** — seed awal: superadmin, COA 263 akun, roles, company_settings, + `rahaza_locations` (GED-A/B, ZNA-KAIN/AKSESORIS/FG/SAMPLE/CUTTING/SEWING/QC/PACKING). Struktur kanonik `wh_*` BELUM ada (jalankan `POST /api/wms/structure/build-canonical-storage` setelah buat gedung, bila mau aktifkan zona kanonik). Buat data uji sendiri (prefix TEST-/QA-) & bersihkan.
- Semua yang sudah dikerjakan sifatnya **shipped + agent-tested, BELUM user-confirmed**.

---

## 1. ATURAN WAJIB (JANGAN DILANGGAR — kepercayaan user pernah rusak karena kelalaian)
1. **JANGAN menebak.** Verifikasi dengan bukti (curl/screenshot/testing agent). Jangan bilang "beres" kalau belum dibuktikan.
2. **JANGAN hapus data bisnis** hanya karena qty 0/kecil. Hanya hapus artefak test/DEMO yang jelas & bila diminta.
3. **DEMO-* data DIPERTAHANKAN** (permintaan user, untuk latihan). Jangan purge kecuali user minta.
4. **JANGAN push ke GitHub.** Deploy = di luar scope (user yang deploy). Preview only.
5. **JANGAN ubah** `REACT_APP_BACKEND_URL` (frontend/.env) & `MONGO_URL` (backend/.env).
6. Semua route backend prefix `/api`. Kelola service via **supervisorctl** (jangan jalankan server manual). Pakai **yarn**, bukan npm.
7. **Stok = lewat `stock_service`** (satu pintu): `add/issue/reserve/release/move/adjust`. Jangan sebar `update_one` langsung ke `rahaza_material_stock`.
8. **`rahaza_locations` ≠ `wh_*`.** Produksi/HR (GED-A/B, cutting/sewing/QC/packing) tetap di `rahaza_locations`. Jangan konflasikan/hapus.
9. UUID untuk id, datetime `timezone.utc`.
10. Untuk defect besar: jalankan **testing agent** setelah implementasi, perbaiki semua bug sebelum menyatakan selesai. Testing agent TIDAK auto-bersih artefak — inspeksi DB/file setelahnya.

---

## 2. STATUS FASE (peta besar)
- **FASE 1–5** (refactor inventory + cleanup legacy WMS) ✅ SELESAI (lihat `plan.md`).
- **Konsolidasi Gudang (Masterplan A–G)** — lihat `/app/memory/WAREHOUSE_CONSOLIDATION_MASTERPLAN.md`:
  - **A** ✅ quick win UI (heatmap kanonik, exclude FG, modal PO lebar, filter lokasi interim).
  - **B** ✅ struktur `wh_*` final + `wh_location_migration_map`.
  - **E1** ✅ bongkar monolit "Scanner Barcode" jadi menu terpisah + fold "Posisi & Search" ke hub Stok.
  - **Known Issue §5** ✅ FIXED (2026-07-25) — deep-link `#wms`/`#wh-bin` sekarang resolve portal Gudang → redirect ke Struktur Gudang. Lihat §5.
  - **E2** ✅ SELESAI (2026-07-25, agent-tested iteration_157) — inbound GR via `stock_service.add`, stop ledger ganda `warehouse_stock`. Lihat §6.
  - **C** ✅ SELESAI (2026-07-25, agent-tested iteration_158) — satukan model lokasi (dual-read rahaza↔wh), fix P3, skrip migrasi ledger→wh_* (idempotent+rollback), accessory canonical, endpoint `/api/rahaza/storage-locations`. Lihat §6b.
  - **D** ✅ SELESAI (2026-07-25, agent-tested iteration_159) — fix mismatch Maklon (dropdown→storage-locations + checkStock; backend loc-name via resolver) + smart-reorder kanonik (onhand_map + rahaza_stock_ledger). Lihat §6c.
  - **F** ✅ **SELESAI (2026-07-25)** — undo-history/undo/restore KANONIK + hapus writer legacy putaway/opname + reader legacy kanonik + script drop `warehouse_stock/movements/putaway/opname` + hapus dead code FE `LocationsModule.jsx`. Lihat §7.
  - **F+** ✅ **SELESAI (2026-07-25)** — retire `warehouse_locations`: `get_locations` kanonik, CRUD location → 410, dropdown ReceivingModule → `/api/rahaza/storage-locations`. Lihat §7.
  - **G** ✅ **SELESAI (2026-07-25)** — Opname Aksesoris → standar Opname3 (submit → approve[+finance JE]/reject, gate supervisor). Lihat §7.
- Urutan aman: F setelah C & D (✅). Lakukan audit konsumen legacy sebelum hapus.

---

## 3. YANG DIKERJAKAN SESI INI (detail + file + bukti)

### FASE A (UI quick win) ✅ — testing_agent iteration_155 (backend 23/23, frontend 37/39; 2 minor sudah beres)
- `frontend/src/components/erp/WarehouseDashboard.jsx` — heatmap dari sumber kanonik `/api/wms/map/{building_id}`; KPI "Total SKU" kini dari `/api/rahaza/material-stock/summary` (0→3).
- `backend/routes/rahaza_inventory_materials.py` — tambah param **`exclude_type`** (aditif) di list materials.
- `frontend/src/components/erp/RahazaMaterialsModule.jsx` — "Bahan & Aksesoris" fetch `?exclude_type=fg`; opsi/create "Produk Jadi" dihapus dari modul ini.
- `frontend/src/components/erp/PurchaseOrderModule.jsx` + `frontend/src/components/erp/Modal.jsx` — tambah ukuran modal `2xl` (max-w-5xl=1024px); modal Buat/Detail PO dilebarkan; baris item terbaca.
- `frontend/src/components/erp/RahazaStockModule.jsx` — chip filter lokasi hanya lokasi berstok (interim). **Form receive/transfer TETAP daftar lokasi penuh** (jangan diubah — belum migrasi lokasi).

### FASE B (struktur kanonik + peta migrasi) ✅ — testing_agent iteration_156 (backend 13/13)
- `backend/routes/wms_structure.py` — endpoint baru (idempotent, **admin-only**):
  - `POST /api/wms/structure/build-canonical-storage` → pastikan 4 zona storage di GD-01 + starter rack, lalu upsert `wh_location_migration_map`.
  - `GET /api/wms/structure/location-map` → baca peta.
- Hasil: GD-01 punya **4 zona tanpa duplikat**: `ZN-01` (Bahan/Kain — REUSE zona lama), `ZN-AKS`, `ZN-FG`, `ZN-SAMPLE` (masing-masing 1 rak 24 bin).
- Koleksi baru `wh_location_migration_map` (4 entri): `ZNA-KAIN→ZN-01`, `ZNA-AKSESORIS→ZN-AKS`, `ZNA-FG→ZN-FG`, `ZNA-SAMPLE→ZN-SAMPLE`. **Zona produksi TIDAK dipetakan.**
- Idempotent (run ulang tak menambah). Stok kanonik & penempatan DEMO tidak berubah.

### FASE E1 (bongkar monolit "Scanner Barcode") ✅ — sudah diverifikasi screenshot, 0 error console
- `frontend/src/components/erp/WMSModule.jsx`:
  - Komponen utama sekarang terima prop **`section`**. Bila diberi, render **satu bagian saja** (tanpa tab-bar, header sendiri). `data-testid="wms-section-<section>"`.
  - Tab "Dashboard" (duplikat Dashboard Gudang) **dihapus** dari monolit.
  - `PositionsTab` diberi **named export** (`export function PositionsTab`) untuk dipakai hub.
- `frontend/src/components/erp/moduleRegistry.js`:
  - Menu terpisah baru: `wh-structure`=section 'structure', `wh-units`='units', `wh-scan`='receiving', `wh-audit`='audit' (via `withProps(WMSModule,{section})`).
  - `wh-bin` (Lokasi Bin legacy) → `makeRedirect('wh-structure')`.
  - `wms` (id lama) → `makeRedirect('wh-structure')`.
- `frontend/src/components/erp/hubs/WMSStockHub.jsx` — tab baru **"Posisi & Search"** (lazy import `PositionsTab`) → fold dari monolit.
- `frontend/src/components/erp/portal-shell/portalNav.js` — section "ALAT & AKSESORIS" diganti "STRUKTUR, ALAT & AKSESORIS": item `Struktur Gudang / Scan Gudang / Satuan & Konversi / Audit Trail / Roll Kain / Operasi Aksesoris / Inbox Aksesoris`. **"Scanner Barcode" & "Lokasi Bin" dihapus dari nav.**
- Verifikasi screenshot: menu baru render bersih; "Struktur Gudang" tampilkan GD-01 (4 zona/4 rak); "Scan Gudang" tampil; tab "Posisi & Search" di hub Stok berfungsi (Smart Search).

---

## 4. CARA KERJA CEPAT (biar tidak salah)
- **Login test (Superadmin):** `admin@garment.com` / `Admin@123`. Login endpoint balikin field **`token`** (BUKAN `access_token`).
- **Navigasi frontend = hash based:** `https://<preview>/#<module-id>`. Modul dgn tab: `#<id>` lalu klik tab (HubTabs pakai sessionStorage `hub_tab_<hubId>`).
- **Module id penting:** `warehouse-dashboard`, `wh-bahan-aksesoris` (Master Item), `wh-purchase-orders`, `wh-stock`→hub `wms-stock-hub`, `wh-structure`, `wh-scan`, `wh-units`, `wh-audit`, `wh-receiving` (Penerimaan Barang/GR), `wh-putaway`.
- **Cek compile frontend (JANGAN npm):** `cd /app/frontend && npx esbuild src/components/erp/<File>.jsx --loader:.js=jsx --bundle --outfile=/dev/null --external:react --external:axios --external:lucide-react --external:sonner --external:@/* --external:react-*` (warning ⚠️ bundle pihak-ketiga = normal).
- **Cek compile backend:** `cd /app/backend && python -m py_compile routes/<file>.py` lalu `sudo supervisorctl restart backend`.
- **Screenshot:** viewport `{"width":1920,"height":800}`, quality=20, full_page=False, `wait_until="load"` (JANGAN networkidle).
- **Testing agent:** hasil di `/app/test_reports/iteration_<n>.json`. Report terbaru: **156**.
- **DB:** MongoDB via `MONGO_URL`. Koleksi kunci: `rahaza_material_stock` (stok kanonik), `rahaza_stock_ledger`, `wh_buildings/wh_zones/wh_racks/wh_positions`, `wh_placement_movements`, `wh_pending_movements`, `wh_location_migration_map` (baru), `warehouse_stock`+`warehouse_locations`+`warehouse_receiving` (legacy), `rahaza_locations` (produksi/HR).

---

## 5. KNOWN ISSUE §5 — ✅ SELESAI (2026-07-25, agent-tested iteration_157)
**Gejala (dulu):** deep-link browser langsung ke `#wms` atau `#wh-bin` mendarat di halaman **"Pilih Portal"**, bukan redirect ke Struktur Gudang.
**Akar masalah:** `findPortalForModule()` di `frontend/src/App.js` tak bisa resolve portal untuk id yang sudah dilepas dari `portalNav.js` (E1) → deep-link fresh jatuh ke "Pilih Portal".
**FIX yang diterapkan:**
- (a) `frontend/src/App.js` — tambah `'wms': 'warehouse'` & `'wh-bin': 'warehouse'` ke `LEGACY_MODULE_TO_PORTAL` → `findPortalForModule` resolve portal Gudang → app set portal+module → `MODULE_REGISTRY['wms'/'wh-bin']` = `makeRedirect('wh-structure')` menyala → mendarat di Struktur Gudang.
- (b) `backend/routes/wms_receiving.py:263` — notifikasi rak kritis `link_module="wms"` → `"wh-scan"` (target natural Scan Gudang).
**Verifikasi (lulus):** login → goto `#wms` & `#wh-bin` → `[data-testid="wms-section-structure"]` hadir, teks "Pilih Portal" TIDAK muncul.

---

## 6. FASE E2 — ✅ SELESAI (2026-07-25, agent-tested iteration_157: backend 17/17, frontend 2/2, 0 critical)
**Keputusan user (terpenuhi):** dokumen **Goods Receipt** tetap satu-satunya pintu inbound (PO→GR, qty diterima/ditolak, lot/expiry, **PO 3-way matching**), TAPI: (1) stok dialirkan lewat `stock_service.add(...)` (kanonik + ledger `rahaza_stock_ledger`), (2) BERHENTI menulis ledger ganda `warehouse_stock`.

**Yang diubah — `backend/routes/warehouse.py`:**
- Tambah import top: `from core import stock_service`.
- `update_receiving()` transisi status→`received`:
  - **Ledger 1 `warehouse_stock` + `warehouse_movements` DIHAPUS** (blok lama ~b393-428, termasuk batch-prefetch `ws_lookup`). Ini sumber duplikasi INV-11.
  - Item loop kini panggil **`stock_service.add(material_id, loc_id, net_qty, meta={inventory_category,unit,material_name,material_code,location_code}, ref={source:'goods_receipt', ref_type, ref_id, ref_number, lot_number, expiry_date}, actor={id,name,email}, db=db)`**. **FATAL** bila gagal (exception naik → baris `db.warehouse_receiving.update_one(status=received)` tak tercapai → tidak ada GR "received" tanpa stok; user bisa retry). Item tanpa `material_id` → warning + skip (tidak tulis ledger bayangan).
  - **`_record_material_movement`** (movement kanonik `rahaza_material_movements`) DIPERTAHANKAN (non-fatal).
  - **`update_po_received_qty`** (3-way matching) & **Asset capitalization** DIPERTAHANKAN apa adanya.
- **Helper `_sync_to_material_stock` TIDAK diubah** — masih dipakai endpoint LEGACY `/api/warehouse/putaway` transfer (~b660-661, delta ±) & `/api/warehouse/opname` variance (~b809, delta ±) yang butuh delta negatif (tak cocok `stock_service.add` yg tolak qty≤0). Legacy itu urusan Fase C/D/F.

**Bukti test (lulus):** stok kanonik `rahaza_material_stock` +100 (available=100); `rahaza_stock_ledger` 1 baris op=add ref.source=goods_receipt; `warehouse_stock` row=0; `warehouse_movements` GR row=0; PO qty_received=100 status fully_received; Put-Away `GET /api/wms/putaway/pending` unshelved=100. Artefak TEST dibersihkan.

---

## 6b. FASE C — ✅ SELESAI (2026-07-25, agent-tested iteration_158: backend 26/26, frontend 100%, 0 bug)
**Tujuan:** satukan model lokasi (dual-read `rahaza_locations` LAMA ↔ `wh_zones` BARU) tanpa mematahkan portal manapun; fix P3 "Lokasi -"; siapkan migrasi ledger→wh_*.
**Yang diubah:**
- **`backend/core/location_resolver.py` (BARU)** — SSOT resolusi lokasi: `get_migration_map`, `rahaza_to_wh_map`, `canonical_zone_id_for_role(role)`, `to_canonical_location_id(id)`, `list_storage_locations()` (zona kanonik `wh_*` + legacy storage belum-termap; EXCLUDE zona produksi via `STORAGE_RAHAZA_CODES`), `build_display_map(ids)` (nama lintas `wh_zones`/`wh_positions`/`wh_buildings`/`rahaza_locations`), `location_exists(id)`. Semua **graceful** (fallback aman bila `wh_*` belum ada).
- **`routes/rahaza_inventory_stock.py`** — `/material-stock` list nama lokasi via `build_display_map` (dual-read display → fix P3); `/material-receive` validasi via `location_exists` (terima id rahaza & wh); endpoint BARU `GET /api/rahaza/storage-locations` (list terpadu untuk dropdown/filter).
- **`core/accessory_stock.get_accessory_location_id`** — utamakan zona kanonik `wh_*` 'aksesoris' (ZN-AKS); fallback `rahaza_locations` ZNA-AKSESORIS.
- **`scripts/migrate_stock_locations_to_wh.py` (BARU)** — geser `rahaza_material_stock.location_id` rahaza-storage → wh_zone. Idempotent, `--dry-run`, `--rollback`, row-merge saat kolisi, jurnal `wh_stock_location_migration_log`. (Preview DB kosong → no-op; teruji data dummy.)
- **`frontend/RahazaStockModule.jsx`** — dropdown & filter ambil dari `/api/rahaza/storage-locations`; kolom "Lokasi" pakai nama hasil resolve backend.
**AMAN:** agregasi stok (`onhand_map` dkk.) lintas-lokasi → Marketing/BOM/Produksi/Finance TIDAK berubah. `rahaza_locations` tidak dihapus/rename. Endpoint legacy tak disentuh (Fase F).
**Bukti:** isolated 15/15 + iteration_158 (storage-locations 4 zona storage & EXCLUDE 6 zona produksi; dual-read display "Area Kain (Lt.2)" ↔ "GD-01 · Zona Bahan / Kain"; migrasi move/idempotent/rollback qty utuh; receive tolak invalid 404 & terima wh-zone id; accessory → ZN-AKS). Artefak TEST dibersihkan.

---

## 6c. FASE D — ✅ SELESAI (2026-07-25, agent-tested iteration_159: backend 11/11, frontend smoke, 0 bug)
**Tujuan:** migrasi konsumen legacy ke SSOT lokasi/stok; utama fix mismatch Maklon.
- **D1 (fix mismatch Maklon):**
  - `frontend/MaklonMaterialIssuePanel.jsx` — dropdown lokasi: `/api/wms/legacy/locations` (bin/wh_positions; id TAK cocok `rahaza_material_stock` → cek stok SELALU 0) → **`/api/rahaza/storage-locations`** (SSOT Fase C). `checkStock` diperbaiki: dulu set `stockInfo`=ARRAY lalu baca `stockInfo.qty` (selalu undefined). Sekarang ambil `/material-stock?material_id=`, hitung total on-hand lintas lokasi (samakan dgn validasi backend `stock_service.get_onhand`) + rincian di lokasi terpilih. Label opsi `{code} · {name}`.
  - `backend/routes/dewi_maklon.py create_material_issue` — nama lokasi via `location_resolver.build_display_map` (lintas skema; fallback wh_racks). Validasi stok TETAP kanonik. Stok TIDAK turun di sini (buat pending outbound_rm → Scan-Out WMS).
- **D2 (smart-reorder kanonik):** `dewi_warehouse_smart.py /smart-reorder` — `current_qty` dari `stock_service.onhand_map` (bukan `mat.total_qty` → dulu selalu 0); konsumsi 30-hari dari `rahaza_stock_ledger` (op issue/issue_row, delta<0) via agregasi (bukan `warehouse_movements` kosong sejak Fase E2).
- **D3 (audit):** undo-history/undo/restore `dewi_warehouse_smart.py` masih legacy `warehouse_movements`/`warehouse_stock` → efektif KOSONG utk data baru (aman), diberi catatan deprecation → Fase F.
**Bukti:** isolated 10/10 + iteration_159 (maklon issue stok cukup→200, location_name "Area Kain (Lt.2)", pending_scan_out, insufficient→400; smart-reorder current_qty=onhand kanonik(75); regresi endpoint gudang 200; frontend stock-hub render). Artefak TEST dibersihkan.
**Catatan:** Maklon UI panel butuh order maklon (tak ada di DB fresh & tak ada API create sederhana) → D1 diverifikasi via backend isolated + babel-compile; UI panel belum di-UI-test independen.

---

## 7. SISA MASTERPLAN (ringkas, untuk konteks)
- **Fase C:** ✅ SELESAI (lihat §6b).
- **Fase D:** ✅ SELESAI (lihat §6c).
- **Fase F (✅ SELESAI 2026-07-25):** undo-history/undo/restore → KANONIK (`rahaza_stock_ledger` op='adjust' + reversal `stock_service.adjust`); writer legacy `/api/warehouse/putaway` & `/opname` DIHAPUS (→404); reader legacy → KANONIK; `scripts/migrate_drop_warehouse_ledger_legacy.py` (archive→drop `warehouse_stock/movements/putaway/opname`).
- **Fase F+ (✅ SELESAI 2026-07-25):** retire `warehouse_locations` — `get_locations`(+bridge) baca KANONIK `location_resolver.list_storage_locations` + `wh_positions`; `create/update/delete_location` → 410; dropdown lokasi ReceivingModule → `/api/rahaza/storage-locations`; fallback nama `rahaza_inventory_stock` → `wh_zones`; script drop +`warehouse_locations`. **DIPERTAHANKAN:** `warehouse_receiving` (GR).
- **Fase G (✅ SELESAI 2026-07-25):** Opname Aksesoris (`dewi_accessories_opname.py`, SSOT `wh_opname_sessions2` domain='accessory') → standar Opname3. `open →(submit)→ pending_approval →(approve|reject)`. approve = GATE SUPERVISOR (`check_role` APPROVE_ROLES) → `_add_stock` (stock_service) + `_log_movement` (rahaza_material_movements) + `post_inventory_adjust` (JE inventory_adjust Dr 1-1401/Cr 6-2400, idempotent `mvadj:<mv_id>`). reject tanpa ubah stok. `complete` = alias submit (deprecated). FE `AccessoryModule.StokOpnameTab`: Ajukan + Setujui/Tolak + badge/ringkasan. Bukti: isolated 14/15 + agent iteration_162 22/22.

---

## 8. DEAD-ENDS / JANGAN DIULANG
1. SKU FG kanonik = `{MODEL}-{WARNA}-{SIZE}`. JANGAN `FG-{MODEL}-{SIZE}` / `{MODEL}-{SIZE}` (kehilangan warna wajib).
2. `dewi_rnd_variants` = draft, BUKAN identitas stok operasional.
3. Fit = Techpack saja, BUKAN dimensi SKU.
4. Put-Away JANGAN dari `/api/wms/legacy/stock` (kosong). Opname JANGAN cuma dari `wh_positions` — harus rekonsiliasi stok kanonik dari delta snapshot bin (jaga stok unshelved).
5. JANGAN hapus semua `/api/wms/legacy/*`. Yang hidup: `/locations`, `/receiving`, `/stock`, `/dashboard-kpi`.
6. JANGAN hapus/gabung paksa `rahaza_locations` ke `wh_*`. GED-A/GED-B = konsep, bukan gedung `wh_*`.
7. JANGAN hapus `warehouse_locations`/"Lokasi Bin" sampai semua konsumen migrasi (Fase F).
8. Auth: 403 dari urllib bisa palsu (Cloudflare). Pakai curl/browser. Login balikin `token`.
9. Error bundle penuh `ecij`/react-data-grid = perilaku bundle pihak-ketiga, BUKAN error kode kita. Cek dgn esbuild transform per file.
10. Screenshot JANGAN `networkidle` (koneksi persisten → timeout walau UI jalan). Pakai `load`+selector.
11. `GlassInput` tak punya `forwardRef` — untuk fokus pakai query DOM by testid.
12. Testing agent TIDAK auto-bersih artefak/test-file — hapus manual (mis. `backend_test_*.py`).

---

## 9. REFERENSI DOKUMEN
- `/app/plan.md` — status global + ringkas semua fase (source of truth).
- `/app/memory/WAREHOUSE_CONSOLIDATION_MASTERPLAN.md` — rencana detail A–G + status.
- `/app/memory/LOCATION_SSOT_CONSOLIDATION_PROPOSAL.md` — analisis lokasi + addendum duplikasi/inbound-outbound.
- `/app/memory/WAREHOUSE_AUDIT_FINDINGS.md`, `/app/memory/INVENTORY_QTY_LOGIC_AUDIT.md` — temuan audit.
- Test terbaru: `/app/test_reports/iteration_156.json`.

---

## 10. LANGKAH PERTAMA UNTUK AGENT BERIKUTNYA
1. Baca dokumen ini + `plan.md` + masterplan.
2. **Bootstrap lingkungan bila fresh:** pastikan `/app/backend/.env` punya `JWT_SECRET` & `EMERGENT_LLM_KEY` (repo .env di-gitignore). Backend tak start tanpa JWT_SECRET. DB fresh → seed otomatis (superadmin admin@garment.com/Admin@123, COA, roles, rahaza_locations). Buat data uji sendiri (TEST-/QA-*) & bersihkan. Testing agent TIDAK auto-hapus file test → hapus manual (`backend_test_*.py`).
3. Konfirmasi ke user: lanjut **Fase F** (audit konsumen legacy → migrasi → hapus `warehouse_*` + Lokasi Bin) atau **Fase G** (Opname Aksesoris → Opname3). Lihat §7. Gunakan `core/location_resolver` + `stock_service` yg sudah ada.
4. Kerjakan bertahap (audit dulu, dual-read aman) → testing agent → bersihkan artefak → update `plan.md`+masterplan+handoff.
5. Laporkan transparan sebagai "shipped + agent-tested, menunggu konfirmasi user".


---

# 📋 PERINTAH KERJA SESI BERIKUTNYA — 4 permintaan pemilik (2026-08-19, akhir sesi #28)

> **KOREKSI PENTING DARI PEMILIK:** kata **"usang" BUKAN berarti dimatikan** — pemilik ingin fitur itu
> **DIHIDUPKAN KEMBALI dan DISESUAIKAN agar berfungsi.** Jangan pernah menghapus/menonaktifkan
> `Alert & Reorder`, `Retur Fisik`, atau `Restock Gudang`. Pemilik minta **SEMUA** dikerjakan.

Analisis akar masalahnya SUDAH SELESAI di sesi #28 (angka di bawah terukur, jangan diukur ulang dari nol).

## W1 — Tabel FG lengkap: kategori + warna + filter, buang kolom id
**Fakta terukur:** `Stok & Akurasi` (`#wh-stock`) menampilkan **daftar BARIS STOK**, bukan daftar master
item. Hanya **12 dari 321** material FG punya baris stok ⇒ layar terlihat "tidak sinkron" dengan
Master Item Produk (321). **Bukan duplikasi**: 320 varian ↔ 321 FG, 320 di antaranya membawa
`variant_id` (pemetaan 1:1). Satu FG tanpa varian = `ARN-HD-NVY-M` (lahir dari penerimaan CMT, temuan
audit C2).
**Kerjakan:**
1. Tambah kolom **Kategori** & **Warna** pada tabel stok + **filter** untuk keduanya. Sumbernya SUDAH
   ADA di dokumen FG (`_variant_linkage` menulis `category_name`, `color`/`color_name`, dan sejak
   sesi #28 juga `option_code`/`option_name`) — jangan menghitung ulang dari string SKU.
2. Tambah kolom **Opsi** (dimensi ke-3 sesi #28) supaya `-KRT`/`-NOK`/`-SMK` terbaca.
3. **Buang `material_id` dari tampilan** (pemilik: "material id seharusnya tidak perlu ada di table
   ini"). Periksa KETIGA mode tampilan (tabel/kartu/kompak) **dan berkas ekspor CSV** — kolom id bisa
   muncul di ekspor walau tidak di tabel.
4. Beri saklar **"tampilkan juga yang stoknya 0"** supaya daftar bisa disamakan dengan master item
   (inilah penyebab sebenarnya keluhan "tidak sinkron").

## W2 — Ekspor: semua koleksi bisa diekspor + pemakai memilih kolom
**Keluhan pemilik:** "PDF masih belum lengkap ... untuk produksi ada data no serial namun di pdf tidak
ada pilihannya, jadi saya ingin semua data collection bisa di export juga dan bisa di pilih user".
**Kerjakan:** satu pintu ekspor generik (PDF + CSV/Excel) dengan **pemilih kolom** yang membaca
kolom yang benar-benar ada pada koleksinya. Nomor serial produksi WAJIB masuk daftar pilihan
(lihat `routes/operations_serials.py`). Ikuti pola `_pdf_data_table` (auto-wrap + penuh lebar halaman)
supaya gate **INV-F17** (0 tumpang tindih) & **INV-F26** (kop/logo/TTD) tetap hijau.

## W3 — HIDUPKAN KEMBALI `Alert & Reorder` (`#wh-smart`)
**Fakta TERUKUR (2026-08-19):** layarnya hidup dan tidak error, tetapi MUSTAHIL berbunyi karena
ambangnya tidak pernah terisi — dari **333 material, 333 (100%) `min_stock_qty` kosong/0** dan
**0 material punya `reorder_point` > 0**. Itulah sebabnya layar selalu berkata "Semua sistem normal /
Tidak ada alert" dan kolom "MIN STOK" semuanya `—`. Fiturnya tidak usang; **ambangnya belum pernah
diisi siapa pun.**
**Kerjakan:** (a) beri layar/kolom untuk mengisi `min_stock` & `reorder_point` per material (dari
master, bukan ketikan bebas); (b) usulkan otomatis dari pemakaian nyata (`rahaza_stock_ledger`);
(c) buktikan alert benar-benar MUNCUL dengan data nyata. Jangan matikan fiturnya.

## W4 — HIDUPKAN KEMBALI `Retur Fisik` & `Restock Gudang` + sambungkan ke Marketing
**Keluhan pemilik:** keduanya "tidak terkoneksi/berhubungan ke portal marketing".
**AKAR MASALAH SUDAH TERBUKTI (2026-08-19) — dugaan pemilik BENAR:** dua semesta yang tidak pernah
bertemu. `marketing_returns` = **30 dokumen** (retur pembeli yang NYATA, + 6 pesanan bertanda retur
senilai Rp 2.222.282 dari INV-RETUR sesi #22), sementara `production_returns` = **0** dan
`production_return_items` = **0**. Jadi Marketing mencatat 30 retur dan layar **Retur Fisik gudang
KOSONG SELAMANYA** — bukan karena fiturnya usang, tetapi karena **tidak ada satu pun jembatan** dari
`marketing_returns` ke koleksi retur produksi/gudang.
**Kerjakan:** bangun jembatannya (satu arah, idempoten, lewat SSOT — pola yang sama dengan
`core/sku_bridge`). Sambungkan: retur pembeli dari Marketing HARUS memunculkan
pekerjaan di Retur Fisik, dan barang yang lolos pemeriksaan HARUS bisa **restock** kembali lewat
`stock_service` (satu pintu) + item katalog jual ikut disegarkan.

## ATURAN YANG TETAP BERLAKU
- Frontend **static bundle**: `bash scripts/rebuild_frontend.sh` + `supervisorctl restart frontend`.
- Stok HANYA lewat `core/stock_service`. Form wajib pakai Master (gate **INV-F14**).
- Setiap gate/skrip uji yang memotong stok WAJIB mengembalikannya + menghapus **stok & kartu stok**
  dokumen turunannya (rujukan tersimpan bersarang di `ref.ref_id`) — gate **INV-F30 V15**.
- Selesai hanya sah bila `bash scripts/gate.sh` **VERDICT HIJAU** + testing agent bersih.
- Preview-only, jangan push GitHub. Pemilik perlu **deploy ulang** agar perbaikan masuk produksi.


## 🔢 URUTAN EKSEKUSI YANG DIPILIH PEMILIK (2026-08-19, penutup sesi #28)
Pemilik menyebut keempatnya dengan urutan ini — **kerjakan berurutan, satu tuntas baru lanjut**:
1. **W4 — Sambungkan Retur** (PALING DULU): retur pembeli dari Marketing otomatis muncul di
   Retur Fisik gudang **dan bisa masuk stok lagi**. Akar masalah sudah terbukti:
   `marketing_returns` = 30 dokumen vs `production_returns` = 0 ⇒ jembatannya tidak ada.
   Jalur masuk stok WAJIB lewat `core/stock_service` (satu pintu), dan item katalog jual ikut
   disegarkan supaya stok jual tidak berbohong.
2. **W1 — Tabel FG Lengkap**: kategori + warna + **opsi** di tabel stok, buang kolom `material_id`
   (cek juga ekspor CSV), beri filter, plus saklar "tampilkan yang stoknya 0".
3. **W2 — Ekspor Fleksibel**: pemakai memilih kolom yang tercetak; nomor serial produksi WAJIB ada
   di daftar pilihan. Jaga INV-F17 & INV-F26 tetap hijau.
4. **W3 — Hidupkan Alert Stok**: isi ambang `min_stock_qty` / `reorder_point` (333/333 masih kosong),
   usulkan otomatis dari pemakaian nyata, lalu **buktikan alert benar-benar berbunyi**.

**JANGAN dikerjakan paralel keempatnya.** Setiap butir ditutup dengan: `bash scripts/gate.sh`
VERDICT HIJAU + testing agent bersih + bukti angka sebelum/sesudah.
