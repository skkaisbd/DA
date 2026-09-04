# Analisis Backlog Data Excel — 2026-07-27

Sumber: 7 file di `/app/data_import/`, dibandingkan dengan isi DB saat ini.
Menjawab backlog di `docs/BACKLOG_FROM_EXCEL.md`.

---

## Ringkasan eksekutif

| # | Item backlog | Temuan | Bisa dikerjakan? |
|---|--------------|--------|------------------|
| A | **Harga kain** | **Tidak ada sama sekali di Excel mana pun** | Tidak dari Excel — butuh input owner |
| B | Harga aksesoris (92 item kosong) | Ada di sheet pembelian, tapi berupa transaksi + satuan beda | Sebagian (perlu konversi satuan) |
| C | SPEK PRODUK → BOM resmi | Data lengkap, API BOM sudah siap, `rahaza_boms` masih 0 | Ya, ±85–90% otomatis |
| D | Memo → roll kain fisik | 84 rol, lebar 135cm, berat tertulis vs pengecekan | Ya, butuh 1 konfirmasi |
| E | Marketing (12 sheet) | Transaksi harian — sengaja dilewati | Sesuai keputusan owner |
| F | Aksesoris `Sheet1` | **Bukan aksesoris** — katalog produk dagang hijab (1.454 baris) | Perlu keputusan ulang |

---

## A. Harga Kain — TIDAK ADA DI EXCEL

Sudah discan seluruh 7 file untuk kata kunci `harga / price / Rp / nilai / biaya / ongkos`:

```
aksesoris_pemakaian.xlsx  → Harga, HARGA PEMBELIAN, HARGA POKOK/ECER/GROSIR
dashboard_marketing.xlsx  → OMZET (Rp), CPC (Rp), NILAI RETUR
hr_erp.xlsx               → Rate / Base (Rp)
sistem_cmt.xlsx           → Ongkos Jahit/pcs, Ongkos/pcs (Rp), Biaya Permak
stock_kain.xlsx           → (tidak ada satu pun)
```

`stock_kain.xlsx` isinya **kartu stok harian** per warna: kolom
`BAHAN / KAIN | WARNA | SATUAN | #PO1 | #PO2` lalu blok `Awal / In / Out / Akhir`
untuk tiap tanggal (1 Apr – 21 Jul 2026). **Nol kolom harga.**

**Kondisi DB sekarang**

| type | jumlah | punya `unit_cost` > 0 |
|------|-------:|----------------------:|
| fabric | 143 | **0** |
| accessory | 335 | 243 |
| fg | 553 | 0 |

**Dampak:** HPP produksi & nilai persediaan kain = Rp 0. Portal Cutting menghitung
HPP potongan dari `unit_cost` kain → hasilnya juga 0.

**Opsi**
1. **Template impor massal** — saya generate Excel/CSV berisi 143 baris kain
   (kode, nama, grup, warna, satuan, kolom `harga_per_kg` kosong). Owner isi,
   lalu diimpor lewat tombol Impor di Master Material. → paling cepat & akurat.
2. **Isi per-grup** — 10 grup kain saja (KNIT SET 24"/31", RAYON TWILL, CONDRU,
   POLOLINEN, SHAKILLA, HORNET, SPANDEX RAYON, KNIT SALUR FNSH 135,
   RAYON TWILL MOTIF), harga diturunkan ke semua warna di grup itu. → 10 angka saja.
3. **Biarkan 0**, harga terbentuk sendiri saat Penerimaan Barang / PO ke depan
   (moving average). → tidak ada kerja sekarang, tapi HPP baru akurat setelah
   ada transaksi pembelian.

---

## B. Harga Aksesoris — 92 dari 335 masih kosong

Contoh yang kosong: `A5 Label merk Hitam`, `A6 Label merk premium pink`,
`A8 Hangtag Dewasa`, `A9 Hangtag Anak`, `A10 Plastik OPP Ziplock`,
`A18 Karet Uk 0,5 cm`, `A99 Benang Obras Navy`, dst.

Sumber yang tersedia: sheet `DA`, `SNBM`, `02` di `aksesoris_pemakaian.xlsx`
— berisi **transaksi pembelian**:

```
TANGGAL PEMBELIAN | BARU/RESTOCK | NAMA PRODUK | JENIS | STOK MASUK | SATUAN | HARGA PEMBELIAN | HARGA TOTAL
2026-03-30        | BARU         | JEAN ALPHA 20/2 |    | 2          | LUSIN  | 144.000         | 288.000
2026-03-30        | BARU         | RIT LIP 7"      | RESLETING | 3   | BKS    | 53.000          | 159.000
```

**Kendala:** nama bebas (bukan kode A1/A47), dan satuannya LUSIN/BKS/ROLL
sedangkan master pakai Pcs/Meter/Gram/Roll. Perlu tabel konversi
(1 LUSIN = 12 Pcs; 1 BKS = ? Pcs; 1 ROLL = ? Meter) yang **hanya owner yang tahu**.

Perkiraan realistis: ±30–50 dari 92 bisa ditambal otomatis, sisanya manual.

---

## C. SPEK PRODUK (57 SKU) → BOM Resmi

### Yang sudah ada
- Tersimpan sebagai `rahaza_models.spec` untuk 55 model:
  `{construction, component_count, fabrics[], accessories[{name, qty_per_pcs, unit}]}`
- API BOM **lengkap** di `/api/rahaza/boms` (versioning per model+size+color,
  activate, copy-to-sizes, preview requirements).
- `rahaza_sizes` sudah ada 8 baris (S, M, L, XL, XXL, All Size, Standar, Jumbo).
- `rahaza_boms` = **0 dokumen**.

### Uji kelayakan pencocokan otomatis (aksesoris)
70 nama unik dari 245 baris spek, dicocokkan ke 335 master aksesoris memakai
matcher berbasis token + sinonim (`hanteg/hanteng → hangtag`, `lisban → lis ban`, dll):

| Bucket | Jumlah | Contoh |
|--------|-------:|--------|
| Otomatis (skor ≥ 0,75) | **42 / 70** | `Label DA` → `[A54] Label DA 1 Roll` · `Kancing 18L` → `[A202] Kancing uk 18L 2L warna` · `Label Pink (premium)` → `[A6] Label merk premium pink` |
| Perlu review (0,5–0,75) | 6 | `Kancing Emas Absreak 28L` → `[A276] Kancing Bungkus 28L` |
| Manual (< 0,5) | 22 | Hampir semuanya keluarga **Karet**: `Karet ban 4cm (L=54cm)`, `Karet pinggang 2cm (LP 40cm)` |

Yang gagal itu polanya seragam — angka dalam kurung (panjang karet per size)
membajak skor. Dengan **2 aturan domain** (`Karet <n>cm → Karet Uk <n> cm`,
`Size <X> → Label size <X>`) perkiraannya naik ke **±85–90% otomatis**.

### Hambatan nyata yang harus diputuskan

1. **"Kain keras" belum ada di master.** Dipakai 22× (`Kain keras (kerah)` 10×,
   `Kain Keras` 7×, `Kain Keras Daun` 5×) tapi pencarian `kain keras` di
   335 master aksesoris → **0 hasil**. Harus dibuat item master baru.

2. **Nama kain di spek ≠ master kain.** 21 nama unik, hanya ~6 punya padanan:

   | Nama di SPEK | Grup master | Status |
   |---|---|---|
   | Knit 24 / Knit 31 | KNIT SET 24" / 31" | cocok |
   | Rayon twill | RAYON TWILL | cocok |
   | Polo Linen | POLOLINEN | cocok |
   | Coundru | CONDRU | cocok (typo) |
   | Rib Salur | KNIT SALUR FNSH 135 | perlu konfirmasi |
   | Knit 20 | — | sheet ada, master kosong |
   | **Poly Micro Motif** (13×) | — | **tidak ada di master** |
   | Micro Motif / Micro Polos / Snowy Motif | — | **tidak ada di master** |
   | Rib Boston 2x1 / Automan Setting 77 | — | **tidak ada di master** |
   | Rayon / Knit Polos | — | **tidak ada di master** |

   Grup master yang tak terpakai: HORNET, SHAKILLA, SPANDEX RAYON, RAYON TWILL MOTIF.

3. **Kain di BOM harus level grup, bukan per-warna.** 13 dari 21 nama kain
   ditulis "*(sesuai warna order)*". Master kain kita 1 dokumen = 1 grup × 1 warna
   (mis. `RIB KNIT SETTING 24" — AVOCADO (SAGE)`). Jadi baris BOM kain sebaiknya
   menyimpan **grup + placeholder warna**, warna final ditentukan saat WO/order.

4. **Kuantitas kain per pcs tidak ada.** Spek hanya menyebut nama bahan, tidak ada
   `kg/pcs`. `material_kg_per_pcs` di master model = 0 untuk semua 55 model.
   Tanpa ini BOM kain tidak bisa menghitung kebutuhan.

### Bonus yang bisa langsung dipanen
- **Ongkos Jahit/pcs** terisi di **29 dari 57** SKU (Rp5.500–Rp10.000, rata-rata Rp7.493).
  Saat ini `cmt_cost_per_pcs` baru terisi **13 dari 55** model (dari sheet GALERI PRODUK).
  → bisa dilengkapi tanpa pemetaan apa pun.
- **Size** bisa diturunkan dari nama produk untuk **33 dari 57** SKU
  (L 12, XL 9, M 6, S 3, XXL 2, All Size 1); 24 sisanya pakai `STD`.
- `Jumlah Komponen Potongan` hanya terisi **1 baris** → tidak berguna untuk Cutting.

---

## D. Memo → Roll Kain Fisik (`wh_fabric_rolls`)

Isi sheet `Memo` (stock_kain.xlsx):

| Lot | Jml rol | Warna | Berat tertulis (g) | Berat pengecekan (g) | Selisih | Lebar |
|-----|--------:|-------|-------------------:|---------------------:|--------:|-------|
| 1 | 12 | Denim | 29.521 | 28.410 | −3,8% | 135 cm |
| 2 | 12 | Hitam | 29.166 | 28.410 | −2,6% | 135 cm |
| 3 | 12 | Dusty | 29.156 | 28.240 | −3,1% | 135 cm |
| 4 | 24 | Magenta | 59.775 | 57.200 | −4,3% | 135 cm |
| 5 | 24 | Hitam | 59.972 | 57.565 | −4,0% | 135 cm |
| **Total** | **84 rol** | | **207.590 g** | **199.825 g** | **−3,7%** | |

Berat per rol ±2,3–2,6 kg. Lebar 135 cm → **kemungkinan besar grup
`KNIT SALUR FNSH 135`**, tapi warna Denim/Dusty/Magenta perlu dicek ada tidaknya
di grup tersebut.

Catatan: koleksi `wh_fabric_rolls` **belum ada** di DB (modul UI "Roll Kain"
sudah jalan tapi kosong). Selisih tertulis vs pengecekan bagus dipakai sebagai
catatan QC/klaim supplier.

---

## E. Marketing (12 sheet transaksi)

Tetap tidak diimpor sesuai keputusan owner (mulai dari bersih). Yang perlu
dicatat: sheet `KOMPETITOR` (punya kolom HARGA) dan `PROGRAM BULANAN` sifatnya
lebih ke **master/referensi**, bukan transaksi harian — bisa dipertimbangkan
terpisah kalau owner mau.

---

## F. Aksesoris `Sheet1` — ternyata bukan aksesoris

1.454 baris dengan struktur:

```
TANGGAL MASUK | TANGGAL DATA | BARU/RESTOCK | KODE | NAMA PRODUK | NAMA NOTA |
JENIS | MERK | SUPPLIER | STOK MASUK | HARGA POKOK | HARGA ECER | HARGA GROSIR
HJBB00001 | INSTAN ANAK | AURA KIDS | HIJAB | UNA HIJAB | 440 | 5.500 | 9.000 | 8.000
KSKI00001 | KAOS KAKI ANTI SLIP PANJANG | | KAOS KAKI | MUSLIMAH | 7 | 7.500 | 11.000 | 10.500
```

Ini **katalog produk dagang** (hijab, kaos kaki) — lini bisnis retail, lengkap
dengan supplier dan 3 tingkat harga. Sebelumnya diabaikan karena dikira sheet
sampah. Perlu keputusan ulang: masukkan sebagai master produk dagang atau tetap
diabaikan.

---

## Usulan urutan pengerjaan (kalau disetujui)

| Prioritas | Pekerjaan | Estimasi | Prasyarat |
|---|---|---|---|
| 1 | Lengkapi `cmt_cost_per_pcs` 13 → 29 model dari SPEK PRODUK | kecil | tidak ada |
| 2 | Buat item master "Kain keras" (kerah/daun) + kain yang hilang | kecil | daftar dari owner |
| 3 | Generator BOM otomatis + layar review pemetaan nama→kode | sedang | keputusan #C1–C4 |
| 4 | Seed 84 roll kain dari Memo | kecil | konfirmasi grup kain |
| 5 | Template impor harga kain (143 baris / 10 grup) | kecil | owner isi harga |
| 6 | Tambal 92 harga aksesoris dari sheet pembelian | sedang | tabel konversi satuan |
