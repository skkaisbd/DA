# plan.md — Sesi #32 (2026-08-23) — DA37 ERP

> Permintaan pemilik sesi ini (verbatim, dari jawaban klarifikasi):
> 1. **Tutup DoD sesi #31** — "jalankan penguji independen (backend + frontend) untuk layar HPP per
>    Potong & kartu BOM di dialog Cutting, perbaiki semua temuan, lalu dokumentasi + backup DB baru".
> 2. **Perbaiki dua cacat "material potongan"** yang pemilik temukan sendiri lewat mongosh:
>    **(a)** "Material potongan jadi yatim (order cutting/kain sumber hilang) → perlu penjaga +
>    pembersih"; **(b)** "Harga/HPP potongan = 0".
> 3. Fitur backlog lain (Daftar Belanja Mingguan · Riwayat Harga Barang · Isi Ambang Massal):
>    **"selesaikan dulu"** ⇒ ditunda ke sesi berikutnya.

---

## 0) BRING-UP LINGKUNGAN BARU — ✅ SELESAI

Container ini datang **kosong**: `/app` hanya berisi template platform dan **database sama sekali
kosong** (0 koleksi). Yang dilakukan:

- Repo `github.com/dajajbs/DA` di-clone lalu di-`rsync` ke `/app` (kecuali `.env`, `.git`,
  `node_modules`) — `MONGO_URL` & `REACT_APP_BACKEND_URL` **tidak** disentuh.
- `bash scripts/bootstrap.sh` (dengan `EMERGENT_LLM_KEY`) → env dilengkapi (`JWT_SECRET` baru),
  deps terpasang, bundle statis disajikan, login 6 akun **HTTP 200**.
- **DB dipulihkan** dari `backups/auto_20260819_190000` (`mongorestore --gzip`): **227 koleksi ·
  5.744 dokumen · 333 material · 15 akun · total stok 33.503** (angka yang sama seperti catatan
  sesi #30/#31).
  ⚠️ **Data 23 Agustus (sesi #31) HILANG** bersama container lama — hanya KODEnya yang lengkap.
  Itulah kenapa order `CUT-2026-0018` & kain `VFH6B-KAIN-155927` yang pemilik lihat tidak ada lagi.
- Salinan referensi repo disimpan di `/root/DA_ref` (bertahan antar restart) untuk memulihkan
  berkas yang tertimpa.
- **Baseline terbukti:** `bash scripts/gate.sh` → **VERDICT HIJAU, 54 gate** sebelum satu baris pun
  diubah (termasuk INV-F36 milik sesi #31).

---

## Fase A — Menutup DoD sesi #31 (penguji independen + perbaikan) — ✅ SELESAI

### Yang diuji penguji independen
- `test_reports/iteration_88.json` — 20 tes backend `/api/costing/*` & `/api/cutting/bom-requirement`
  LULUS, tetapi 4 dari 6 user story **tidak benar-benar dijalankan di layar** (tombol Terapkan tidak
  diklik, model tidak pernah dipilih sehingga kartu BOM tidak pernah muncul). **Tidak diterima**
  (`memory/ANTI_UNDERDELIVERY_PROTOCOL.md`).
- `test_reports/iteration_89.json` — pengujian ulang dengan interaksi nyata: 4 lulus penuh, dan
  melaporkan "navigasi hash RUSAK". **Diperiksa main agent: navigasi TIDAK rusak** — penguji
  memakai module-id yang tidak ada (`rahaza-models`; yang benar `prod-models`). Namun
  penyelidikan itu **menemukan cacat nyata** (lihat di bawah).
- **Main agent membuktikan sendiri 6 user story di browser** (bukti kutipan DOM ada di
  `memory/CHANGELOG.md` entri #32).

### Temuan yang diperbaiki
1. **Alamat URL tidak mengikuti layar** (`frontend/src/App.js`). Klik "Perbaiki" di layar HPP per
   Potong memindahkan pemakai ke Katalog Marketing tetapi alamat tetap `#fin-hpp-produk` ⇒ tekan F5
   melempar kembali ke layar sebelumnya, tautan yang dibagikan salah, dan penguji menyimpulkan
   "navigasi rusak". Sekarang `handleNavigate`, klik sidebar, pindah portal, kembali ke pemilih
   portal, dan logout semuanya menyinkronkan hash (`syncModuleHash`).
2. **Sel margin hanya bertanda "—"** untuk produk tanpa harga jual ⇒ alasannya hanya terbaca kalau
   kursor didiamkan. Sekarang tertulis **"harga jual belum ada"**.
3. **Teks peringatan deviasi BOM menyambung** (`"25 kg— pastikan"`) — spasi JSX hilang. Diperbaiki.
4. **Daftar ukuran di kartu BOM tidak menandai mana yang sudah ber-BOM** ⇒ admin cutting memilih
   buta. Sekarang opsinya berbunyi `ALLSIZE · ada BOM`.

---

## Fase B — POC INTI (isolasi) — ✅ SELESAI (13/13 PASS)

Berkas: `test_core_potongan_nilai_dan_yatim.py` (satu skrip, self-cleaning, `--keep` opsional).
Angka dihitung tangan LEBIH DAHULU:

| Uji | Hasil |
|---|---|
| T1 | harga kain lahir dari penerimaan: 200 m @25.000 ⇒ 25.000/m; kain tanpa harga tetap **0** |
| T2 | `start` melahirkan master potongan yang menunjuk **order + kain** asalnya, nilai masih 0 |
| T3 | progres 10 m ⇒ 20 pcs: nilai kain keluar 300.000 ⇒ HPP potongan **15.000/pcs** |
| T4 | beli lagi 100 m @42.000 (stok 190) ⇒ harga kain **34.137,931/m** (rata-rata bergerak) |
| T5 | progres 10 m ⇒ 10 pcs: HPP potongan **21.379,310/pcs** (RATA-RATA, bukan ditimpa 34.137,93) |
| T6 | kekekalan nilai: Σ nilai kain keluar **641.379,31** == nilai stok potongan 30×21.379,31 |
| T7 | complete: nilai order **641.379,31** ⇒ 21.379,31/pcs; master **tidak** ditimpa |
| T8 | kain tanpa harga ⇒ potongan `value_status='unvalued'` + alasan & jalan keluarnya |
| T9 | `cancel` sesudah `start` **membuang** master potongan yang belum pernah bergerak |
| T10 | potongan yatim (order dihapus) terdeteksi `order_missing`, dibersihkan, **idempoten** |
| T11 | yatim yang MASIH BERSTOK **tidak** dihapus — alasannya disebut (stok tak jadi hantu) |
| T12 | daftar Master Potongan mengirim nilai + asal + status + penanda yatim |
| BERSIH | stok total kembali **33.503** (alat ukur tidak mengotori data) |

**Cacat lama yang terukur oleh POC:** `complete` dulu menghitung **Rp600.000** (harga kain
di-snapshot saat order dibuat) padahal nilai sebenarnya **Rp641.379,31** ⇒ **Rp41.379 hilang**
tanpa jejak pada satu order saja.

---

## Fase C — Implementasi penuh — ✅ SELESAI

### Backend
- **SSOT baru `core/cut_panel_value.py`** — satu pintu `apply_progress_value()` dipanggil tiap
  laporan progres cutting: `nilai kain keluar = qty × unit_cost kain SAAT ITU`,
  `HPP masuk/pcs = nilai / pcs jadi`, lalu **rata-rata bergerak** ke master potongan memakai SSOT
  `core/accessory_valuation` (+ riwayat harga). `panel_onhand()` dibaca **sebelum**
  `stock_service.add` (kalau sesudah, qty masuk ikut jadi penyebut). Kain belum bernilai ⇒
  `value_status='unvalued'` + `notify_unvalued` ke Admin Gudang. `order_value_totals()` = Σ nilai
  progres, dipakai `complete`.
- **SSOT baru `core/cut_panel_health.py`** — definisi "potongan yatim" (`order_missing`,
  `source_missing`, `source_inactive`, `source_unknown`), bukti kelayakan hapus (stok, buku besar
  stok, kartu stok, rujukan BOM/MI/PR/PO/GR), `scan()`, `cleanup()` (idempoten), dan penjaga alur
  `remove_if_unused()`.
- `routes/cutting.py`: master potongan menyimpan **`cutting_order_id`/`cutting_order_number`/
  `created_from`** (bukti kepemilikan) + `value_status`; `add_progress` memindahkan nilai & menyimpan
  jejaknya di `cutting_progress` (`fabric_unit_cost`, `value_out`, `panel_unit_cost_before/after`);
  `complete` memakai Σ nilai progres dan **tidak** menimpa master (kecuali order lama yang masternya
  masih 0 — diisi sekali, sumber `cutting_complete_backfill`); `cancel` & `delete` memanggil penjaga;
  `GET /output-materials` mengirim nilai+asal+status+penanda yatim; endpoint baru
  **`GET /api/cutting/panels/health`** & **`POST /api/cutting/panels/cleanup`**.

### Frontend
- **Layar Master Potongan** (`cutting-panels`) dirombak: 4 kartu ringkasan (termasuk **Nilai
  Persediaan** & **Belum Bernilai**), tabel **10 kolom** (Order Cutting · Nilai · Status Nilai +
  penanda **yatim** per baris), dan **kartu "Potongan yatim"** berisi alasan per baris, kolom "Bisa
  dibersihkan?", serta tombol **Bersihkan yang aman (n)** dengan konfirmasi dua langkah.
- **Order Cutting**: Riwayat Progres dapat dua kolom baru **"Nilai kain keluar"** & **"HPP
  potongan"** (menyebut "dari Rp… rata-rata bergerak"), toast nilai berpindah, dan peringatan
  bertahan-lama bila kain belum bernilai.

### Alat ukur yang MEMBOCORKAN data — diperbaiki
- `scripts/verify_fase_h6b_cutting_issue.py` (gate INV-F24) menghapus master potongan memakai
  **regex kode** `^(VFH6B-|CUT-GATE-F24)`; sejak sesi #30 kode potongan diturunkan dari NAMA MODEL
  (`CUT-JEPIT-JEDAI-…`) ⇒ regex tak pernah cocok ⇒ **satu master sampah menumpuk setiap kali gate
  dijalankan**. Inilah "potongan yatim" yang pemilik lihat. Sekarang dihapus lewat **`id`**.
- `scripts/verify_uom_roll_dan_style_master.py` membersihkan progres cutting dengan nama field yang
  salah (`order_id`, seharusnya `cutting_order_id`).

---

## Fase D — Gate, uji, dokumentasi — ✅ SELESAI

- Gate baru **INV-F37** `scripts/verify_potongan_nilai_dan_yatim.py` (**12 invarian**,
  self-cleaning) — C12 memeriksa **KEADAAN AKHIR: 0 potongan yatim** sesudah bersih-bersih, jadi
  kebocoran alat ukur mana pun otomatis MERAH. Terdaftar di `scripts/gate.sh` (+ daftar `skip_gate`).
- `bash scripts/gate.sh` → **VERDICT HIJAU 55 gate** (54 baseline + INV-F37).
- Penguji independen sesi #32 memverifikasi layar Master Potongan + pembersihan yatim (1 master
  warisan benar-benar terhapus lewat tombol di layar).
- **Main agent membuktikan alur ujung-ke-ujung di browser** (kutipan DOM):
  progres 10 m ⇒ 20 pcs → *"Nilai kain keluar Rp 250.000 · Rp 25.000/m | HPP potongan Rp
  12.500/pcs"*; progres 5 m ⇒ 5 pcs → *"Rp 125.000 | Rp 15.000/pcs dari Rp 12.500 (rata-rata
  bergerak)"*; Master Potongan → *"25 pcs · Rp 15.000 · Rp 375.000 · bernilai"*; `cancel` →
  *"Master potongan CUT-JEPIT-JEDAI-NAVY-XL ikut dibersihkan karena belum pernah dipakai"*.
- Dokumentasi: berkas ini · `memory/CHANGELOG.md` **[#32]** · `memory/INVARIANTS.md` **INV-F37** ·
  `HANDOFF_NEXT_AGENT.md` · `memory/test_credentials.md`.
- **Backup DB baru** ke `/app/backups` (WAJIB: dbPath Mongo di luar `/app`, container ini terbukti
  bisa datang dengan DB kosong).

---

## User stories yang harus lulus (sesi ini)

1. Admin cutting mencatat progres potong → **nilai kain yang keluar langsung menjadi HPP potongan**,
   dan angkanya kelihatan di Riwayat Progres. ✅
2. Potong lagi dengan harga kain yang sudah berubah → HPP potongan menjadi **rata-rata bergerak**,
   angka lama tidak terhapus. ✅
3. Pemilik membuka **Master Potongan** → melihat **nilai persediaan potongan** (bukan cuma pcs),
   asal (kain + nomor order), dan status nilainya. ✅
4. Kain yang belum punya harga → layar **mengatakan** potongannya belum bernilai + jalan keluarnya
   (bukan diam-diam Rp0). ✅
5. Pemilik melihat **daftar potongan yatim** + alasannya, menekan **Bersihkan yang aman**, dan
   sampahnya benar-benar hilang. ✅
6. Potongan yatim yang **masih berstok** tidak bisa dihapus, dan layar menyebut alasannya. ✅
7. Membatalkan order cutting yang sudah dimulai **tidak** meninggalkan master potongan sampah. ✅

## Definition of Done sesi ini

- [x] Penguji independen sesi #31 dijalankan + SEMUA temuannya diperbaiki
- [x] POC 13/13 PASS & self-cleaning (stok kembali 33.503)
- [x] Backend + Frontend kedua cacat selesai & terhubung (tidak ada fitur backend tanpa layar)
- [x] Gate INV-F37 12/12 PASS + `gate.sh` VERDICT HIJAU 55 gate
- [x] Alur ujung-ke-ujung dibuktikan di layar (bukan hanya API)
- [x] Dokumentasi diperbarui
- [x] Backup DB baru di `/app/backups`
- [x] Data uji dibersihkan (`python3 scripts/seed_uji_potongan_nilai.py --cleanup`)

## Sisa pekerjaan untuk sesi berikutnya (pilihan pemilik)

1. **Daftar Belanja Mingguan** — usul pembelian mingguan dari kebutuhan produksi vs stok & ambang.
2. **Riwayat Harga Barang** — layar riwayat `rahaza_material_cost_history` (sudah terisi tiap
   pembelian & tiap potong) per material: grafik/tabel perubahan harga rata-rata.
3. **Isi Ambang Massal** — isi `min_stock`/reorder point untuk 334 material sekaligus.
4. (kecil) 41 jenis dokumen masih "Otomatis saja" di Penomoran Dokumen — pola menyambungkannya
   sudah terbukti (lihat HANDOFF sesi #18).
