# SINTESIS TEMUAN INVENTORY + PROPOSAL PERBAIKAN + KONDISI TARGET
Tanggal: 2026-07-23 · Status: PROPOSAL (belum dieksekusi, menunggu approval user)
Sumber: INVENTORY_QTY_LOGIC_AUDIT.md (PASS 1 & 2) + WAREHOUSE_AUDIT_FINDINGS.md

═══════════════════════════════════════════════════════════════════
## 1. AKAR MASALAH TUNGGAL (kenapa qty gudang tidak bisa dipercaya)
═══════════════════════════════════════════════════════════════════
Sistem TIDAK punya satu "sumber kebenaran stok". Yang ada:
- 3 BENTUK BARIS stok berbeda di koleksi yang sama (rahaza_material_stock):
  A (flat: material_id+location_id+qty), B (nested aksesoris: location.id+total_qty),
  C (FG: ownership+inventory_category+available_quantity).
- 2 LEDGER kuantitas paralel: rahaza_material_stock (level material) vs wh_positions.qty (level bin/rak).
- Banyak writer & reader independen; refactor SSOT hanya menyentuh jalur BUAT, sementara
  consumer lama masih pakai format/lookup lama.

Akibat pola ini: setiap kali barang bergerak lewat jalur yang "beda skema", angka stok
pecah menjadi beberapa versi yang tidak saling tahu. Total kadang terlihat benar (FG Matrix
menjumlah semua baris), tapi operasional (jual, kirim, alokasi, koreksi) melihat angka lain.

═══════════════════════════════════════════════════════════════════
## 2. PENYAKIT → AKIBAT DI SISTEM → PERBAIKAN → SETELAH DIPERBAIKI
═══════════════════════════════════════════════════════════════════

### PENYAKIT #1 — Dua ledger stok tidak pernah direkonsiliasi (BUG-INV-11) [CRITICAL/AKAR]
AKIBAT: "Stok level material" (dibaca FG Matrix, fulfillment, katalog, marketing) dan
"stok level rak" (dibaca opname & struktur gudang) menyimpang makin jauh. Pertanyaan
"berapa stok sebenarnya?" punya 2 jawaban berbeda. Semua issue/fulfillment/retur hanya
update material-level; opname resmi hanya update bin-level.
PERBAIKAN: Tetapkan rahaza_material_stock sebagai SATU sumber kebenaran on-hand. wh_positions
jadi TURUNAN (detail penempatan fisik), bukan ledger independen. Semua mutasi stok wajib lewat
1 modul `stock_service` (add/issue/reserve/release/move/adjust) yang meng-update material-level;
posisi rak di-update sebagai detail dari operasi yang sama.
SETELAH: Satu angka on-hand yang konsisten di seluruh modul. Rak hanya memberi info "di mana",
bukan "berapa" yang berbeda.

### PENYAKIT #2 — FG produksi internal tak bisa dijual/dikirim (BUG-INV-1) [CRITICAL]
AKIBAT: FG hasil produksi sendiri masuk stok (Schema A) TAPI tidak muncul di layar fulfillment
(yang mencari Schema C). Praktis: hanya FG dari CMT/seed yang bisa dialokasikan & dikirim ke
pesanan marketing. FG bikinan sendiri "terjebak" di gudang.
PERBAIKAN: Saat FG masuk (scan-in produksi) set atribut lengkap (ownership=cv_da,
inventory_category=fg_internal, available_quantity=qty, reserved_quantity=0) via stock_service;
ATAU ubah fulfillment agar mengagregasi lintas-skema per material_id + pakai read_available.
SETELAH: Semua FG (produksi internal maupun CMT) muncul & bisa dialokasikan/dikirim seragam.

### PENYAKIT #3 — Retur material menulis field "hantu" (BUG-INV-6) [CRITICAL]
AKIBAT: Sisa bahan yang dikembalikan dari produksi di-catat ke qty_available/qty_on_hand
(field yang tidak dibaca siapa pun). Reader kanonik baca `qty` → stok retur seakan HILANG.
Bahan yang sebenarnya kembali tidak bisa dipakai lagi di sistem.
PERBAIKAN: Retur pakai stock_service.add() → tambah `qty` kanonik + alias, dengan key konsisten
(material_id + location_id).
SETELAH: Bahan retur langsung kembali terhitung sebagai stok siap pakai.

### PENYAKIT #4 — Kirim FG tak menurunkan stok (BUG-INV-9) [HIGH]
AKIBAT: Saat approve pengiriman (rahaza_shipments), sistem mencari FG dengan kode legacy
`FG-{model}-{size}` (tanpa warna). Kode itu tak pernah ada di master kanonik → pencarian gagal
→ `continue` diam → pending outbound tidak dibuat → tidak ada scan-out → STOK FG TIDAK TURUN
walau barang sudah dikirim & invoice/COGS sudah tercatat. (Tambahan: WO tak simpan warna, jadi
resolusi FG harus ambil warna dari variant/po_item, bukan dari WO.)
PERBAIKAN: Ganti lookup ke SKU kanonik {MODEL}-{WARNA}-{SIZE} via helper resolve_variant/
ensure_fg; jika tak ketemu → ERROR eksplisit (bukan skip diam). Ambil warna dari sumber yang benar.
SETELAH: Setiap pengiriman FG otomatis membuat outbound & menurunkan stok; tidak ada lagi
"kirim tapi stok tetap".

### PENYAKIT #5 — Opname resmi tak mengoreksi stok kanonik (BUG-INV-10) [HIGH]
AKIBAT: Modul stok-opname yang dipakai UI (opname2) hanya membetulkan qty di rak (wh_positions),
TIDAK menyentuh rahaza_material_stock. Selisih fisik dihitung & disetujui, tapi angka stok
"sebenarnya" (yang dibaca penjualan/fulfillment) tak berubah. Opname jadi sia-sia untuk stok jual.
PERBAIKAN: opname2 approve → panggil stock_service.adjust() agar koreksi masuk ke material-level;
posisi rak ikut ter-update sebagai detail (selaras Penyakit #1).
SETELAH: Hasil stock opname langsung memperbaiki angka stok yang dipakai seluruh sistem.

### PENYAKIT #6 — Reset-all berbahaya & tak bersih (BUG-INV-7) [HIGH]
AKIBAT: Endpoint reset semua stok bisa dipanggil user login BIASA (tanpa cek role) → siapa pun
bisa nol-kan seluruh stok. Selain itu hanya set qty=0, tidak nol-kan available_quantity →
baris Schema C tetap "terlihat ada stok" setelah reset (inkonsisten).
PERBAIKAN: Batasi ke role admin/owner + konfirmasi eksplisit; reset nol-kan SEMUA alias qty &
available/reserved via set_all_qty. Idealnya jadi aksi audit-logged khusus admin.
SETELAH: Reset hanya bisa oleh admin, terkonfirmasi, dan benar-benar bersih & konsisten.

### PENYAKIT #7 — Dua sistem reservasi + jalur keluar beda key (BUG-INV-2/3) [MEDIUM]
AKIBAT: Reservasi manual (koleksi rahaza_fg_reservations) tidak dilihat fulfillment (yang pakai
field reserved_quantity) → FG yang sudah "dipesan" manual masih bisa dialokasi lagi →
over-alokasi/dobel-janji. "Available" beda antara FG Matrix vs Fulfillment. Jalur keluar FG
(fg-issue Schema A vs fulfillment Schema C) tak konsisten tergantung asal FG.
PERBAIKAN: Satu model reservasi (pilih reserved_quantity pada baris stok), semua modul baca/tulis
sumber sama via stock_service.reserve/release; outbound selalu lewat service yang sama.
SETELAH: Satu angka "available" yang sama di mana-mana; tidak ada dobel-alokasi.

### PENYAKIT #8 — QC penerimaan tak menegakkan stok (BUG-INV-8) [MEDIUM]
AKIBAT: Stok bertambah sebesar jumlah DITERIMA; hasil QC (accepted/rejected) dicatat terpisah &
tidak mengurangi stok. Unit yang REJECT tetap terhitung sebagai stok layak pakai → over-count →
bisa terpakai/terjual padahal cacat.
PERBAIKAN: Stok bertambah hanya sebesar qty ACCEPTED (atau tandai qty rejected sebagai kategori
terpisah/quarantine yang tidak available). Sinkronkan GRN QC → stock_service.
SETELAH: Hanya barang lolos QC yang terhitung stok; barang reject terkarantina, tak terjual.

### PENYAKIT #9 — Reader keyed location_id tak lihat Schema C (BUG-INV-12) [MEDIUM]
AKIBAT: Layar KOL/portal/maklon membaca stok dgn key {material_id, location_id} → FG Schema C
(dari CMT/fulfillment, tanpa location_id) tampil 0 padahal ada. Salah tampil "habis".
PERBAIKAN: Semua reader FG pakai helper agregasi per material_id + read_qty/read_available
(sudah dipakai FG Matrix & katalog). Hindari query per-key mentah.
SETELAH: Semua layar menampilkan stok yang sama & benar, apa pun asal FG.

### PENYAKIT #10 — Footgun alias & field tidak seragam (BUG-INV-4/5, INV-13, residual) [LOW]
AKIBAT: Sebagian writer inc `qty` mentah (alias total_qty/quantity basi); available_quantity bisa
basi; alert min-stock hanya baca `min_stock` (tak nyala utk material set `min_stock_qty`);
fallback SKU tanpa warna (production_pos) & fallback FG- (CMT) masih tersisa.
PERBAIKAN: Semua writer wajib inc_all_qty/set_all_qty; hitung available = qty - reserved saat baca;
seragamkan field min-stock; buang fallback tanpa-warna & FG-.
SETELAH: Konsistensi angka & alert; tidak ada lagi format identitas non-kanonik.

═══════════════════════════════════════════════════════════════════
## 3. INTI SOLUSI: SATU "STOCK SERVICE" (mengunci semua penyakit di atas)
═══════════════════════════════════════════════════════════════════
Buat 1 modul backend `core/stock_service.py` sebagai SATU-SATUNYA pintu mutasi stok:
- add(material_id, location, qty, meta)        → inbound (produksi, purchase-accepted, retur)
- issue(material_id, location, qty)            → outbound (ke produksi, dispatch, manual)
- reserve(material_id, qty, ref) / release()   → satu model reservasi
- move(from, to, qty)                          → transfer antar lokasi/rak
- adjust(material_id, location, counted_qty)   → opname
Aturan internal service:
- Selalu tulis skema kanonik (qty + alias via set/inc_all_qty) + available_quantity terpelihara.
- Selalu keyed konsisten; FG selalu bawa ownership/inventory_category.
- Update wh_positions sebagai DETAIL (bukan ledger terpisah).
- Semua route memanggil service ini; TIDAK ADA lagi update_one langsung ke rahaza_material_stock
  yang tersebar.
Manfaat: menutup INV-1,2,3,4,6,9,10,11,12 sekaligus karena semua lewat satu jalur konsisten.

═══════════════════════════════════════════════════════════════════
## 4. URUTAN EKSEKUSI YANG DISARANKAN (bertahap, aman)
═══════════════════════════════════════════════════════════════════
FASE 0 — Perbaikan cepat berisiko rendah (quick wins, tidak ubah arsitektur):
  - INV-7 role guard reset-all + zero-out lengkap.
  - INV-5 seragamkan field min-stock.
  - INV-9 ganti lookup FG legacy → SKU kanonik + error eksplisit.
  - INV-6 retur pakai qty kanonik.
FASE 1 — Bangun stock_service (single writer) + unit test, tanpa mengubah route dulu.
FASE 2 — Rewire route inbound/outbound/opname/reservasi ke stock_service satu per satu
  (INV-1,2,3,4,10,11,12), tiap langkah diuji testing_agent.
FASE 3 — Rekonsiliasi data lama (migrasi baris A/B/C jadi kanonik; samakan wh_positions).
FASE 4 — INV-8 (QC→stok) + bersih-bersih dead code + hapus modul/menu legacy gudang.
Catatan: setiap fase yang menyentuh perilaku stok WAJIB lewat testing_agent sebelum diklaim beres.

═══════════════════════════════════════════════════════════════════
## 5. KONDISI TARGET ("TO-BE") SETELAH SEMUA DIPERBAIKI
═══════════════════════════════════════════════════════════════════
- SATU angka on-hand per material, konsisten di FG Matrix, fulfillment, katalog, marketing,
  KOL/portal, opname, dan viewer stok.
- FG produksi internal & FG CMT diperlakukan sama: bisa dialokasikan, direservasi, dikirim.
- Setiap pengiriman FG otomatis menurunkan stok; tidak ada "kirim tapi stok tetap".
- Stock opname langsung membetulkan stok yang dipakai penjualan.
- Retur bahan langsung kembali jadi stok siap pakai; barang QC-reject terkarantina (tidak terjual).
- Satu model reservasi → "available" seragam, tanpa dobel-alokasi.
- Reset stok hanya untuk admin, terkonfirmasi, audit-logged, dan bersih.
- Semua identitas FG kanonik {MODEL}-{WARNA}-{SIZE}; tidak ada lagi FG-/tanpa-warna.
- wh_positions = detail lokasi fisik (di rak mana), bukan sumber angka yang bersaing.
- Semua mutasi stok lewat 1 stock_service → mudah diaudit, sulit pecah lagi.
