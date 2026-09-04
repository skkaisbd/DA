# Audit Modul Konversi Satuan — Fungsionalitas & Struktur Data

Tanggal: 2026-07-27
Metode: baca kode + query DB langsung + **uji fungsional live** ke API produksi
Ruang lingkup: `wms_units`, `rahaza_materials` (pack), seluruh titik masuk stok

---

## Kesimpulan singkat

**Struktur datanya BELUM mengakomodasi.** Fondasinya ada (`pack_unit`, `pack_size`,
`display_in_packs`) dan konsepnya benar, tapi:

1. **Ada 1 bug P0 yang merusak laporan keuangan** — harga tidak ikut dikonversi
   saat terima barang per kemasan. Sudah saya buktikan lewat uji live:
   nilai persediaan **membengkak 144×** dan **jurnal akuntansi ikut terposting salah**.
2. **Konversi hanya jalan di Portal Aksesoris**, dan bahkan di sana pun tidak
   lengkap. Portal Gudang & Cutting **nol konversi** padahal pakai koleksi
   material yang sama.
3. **Modul "Satuan & Konversi" kosong total** — koleksinya tidak ada di DB.
4. **91 aksesoris salah struktur**: satuan kemasan dijadikan satuan dasar
   (74 `rol`, 14 `pak`, 3 `lusin`) sehingga "stok 9 rol" tidak diketahui berapa meter.
5. Struktur sekarang **hanya sanggup 1 level kemasan dan 1 jenis kemasan** per item.

---

## BAGIAN 1 — BUG YANG DITEMUKAN

### BUG-1 (P0) · Harga tidak ikut dikonversi saat terima per kemasan
**Bukti uji live** (`POST /api/acc/stock/receive`):

```
Item uji : 1 pak = 144 pcs, satuan dasar pcs
Input    : qty 1, input_unit "pack", unit_cost 144.000  (harga 1 PAK)

Respons sistem:
  qty_received   : 144.0        ← qty BENAR dikonversi
  unit_cost      : 144000.0     ← SALAH, disimpan sebagai harga per PCS
  stock_value    : 20.736.000   ← seharusnya 144.000
  je             : {"posted": true, "je_number": "JE-20260727-0001"}
```

**Dampak berlapis:**
- Nilai persediaan **overstated 144×**
- HPP rata-rata bergerak (`moving_average`) master ikut rusak permanen
- **Jurnal akuntansi otomatis terposting** dengan angka salah → Neraca & Laba Rugi salah
- Makin sering terima barang, makin melenceng

**Letak** — `routes/dewi_accessories_stock.py` ±baris 220-232. Blok yang mengonversi
qty (`qty_in_base_unit = qty * pack_size`) tidak diikuti konversi harga.
Jalur `total_cost` justru benar (dibagi `qty_in_base_unit`), jadi perilakunya
tidak konsisten antar-jalur input.

**Perbaikan** — bila `input_unit == "pack"`, `unit_cost` harus dibagi `pack_size`,
dan label di UI harus jelas: "Harga per **pak**" vs "Harga per **pcs**".

> Catatan: data uji sudah saya hapus bersih (material, ledger stok, jurnal, dan
> baris jurnalnya). Tidak ada sisa di DB.

---

### BUG-2 (P0) · Konversi hanya ada di Portal Aksesoris, Portal Gudang nol

Semua pergerakan stok bermuara ke SSOT `core/stock_service.py` yang bekerja dalam
**satuan dasar** — itu sudah benar secara arsitektur. Masalahnya, konversi harus
dilakukan di setiap pintu masuk, dan hanya sebagian yang melakukannya:

| Titik masuk stok | File | Konversi kemasan |
|---|---|:--:|
| Aksesoris — Terima Barang | `dewi_accessories_stock.py` | ADA (harga salah) |
| Aksesoris — Scrap | `dewi_accessories_stock.py` | ADA |
| Aksesoris — Pemakaian | `core/accessory_issue.py` | ADA |
| Aksesoris — Purchase Request | `dewi_accessories_purchase.py` | ADA (harga salah) |
| **Aksesoris — Stok Opname** | `dewi_accessories_opname.py` | **TIDAK** |
| **Aksesoris — Peminjaman** | `dewi_accessories_loans.py` | **TIDAK** |
| **Aksesoris — Request Internal** | `dewi_accessories_requests.py` | **TIDAK** |
| **Gudang — Receiving** | `wms_receiving.py` | **TIDAK** |
| **Gudang — Purchase Order** | `warehouse.py` | **TIDAK** |
| **Gudang — Putaway** | `wms_putaway.py` | **TIDAK** |
| **Gudang — Stok Opname** | `wms_opname3.py` | **TIDAK** |
| **Gudang — Pengeluaran Material** | `rahaza_inventory_issues.py` | **TIDAK** |
| **Gudang — Warehouse Smart** | `dewi_warehouse_smart.py` | **TIDAK** |
| **Gudang — Stok manual** | `rahaza_inventory_stock.py` | **TIDAK** |
| **Cutting** | `cutting.py` | **TIDAK** (`pack_size` di-hardcode 1) |

Karena Aksesoris dan Gudang membaca **koleksi `rahaza_materials` yang sama**,
barang yang sama akan menghasilkan angka stok berbeda tergantung lewat pintu mana.

Kasus paling berbahaya: **Stok Opname**. Petugas menghitung fisik "3 pak", tapi
opname aksesoris tidak punya opsi pack → sistem menganggap "3 pcs" → stok yang
tadinya 432 pcs dipangkas jadi 3 pcs, **selisihnya langsung dijurnal sebagai kerugian**.

---

### BUG-3 (P1) · Modul "Satuan & Konversi" kosong — koleksinya tidak ada
Query DB: `wh_unit_master` dan `wh_unit_conversions` **TIDAK ADA** (terhapus saat wipe).
Akibatnya layar Gudang → *Satuan & Konversi* tampil kosong dan kalkulator error:

```
POST /api/wms/units/convert {"qty":1,"from_unit":"lusin","to_unit":"pcs"}
→ 404  "Unit 'lusin' tidak ditemukan"
```

Ada tombol Seed manual, tapi tidak ada yang tahu harus menekannya. Modul lain
(Cutting) memakai pola `ensure_*_indexes()` saat startup — pola yang sama belum
dipakai di sini.

Setelah saya jalankan seed: 22 satuan + 14 aturan terbuat, kalkulator jalan.
Saya biarkan terpasang karena ini master data standar.

---

### BUG-4 (P1) · Konversi satu arah — tidak ada kebalikan otomatis
```
1 lusin → pcs   = 12      OK
12 pcs  → lusin = ERROR   "Tidak ada aturan konversi pcs→lusin"
```
Seed mendefinisikan bolak-balik hanya untuk panjang & berat (cm↔m, kg↔gram),
tapi tidak untuk satuan hitung (lusin, kodi, gross, pair). Padahal `1/factor`
bisa dihitung otomatis.

---

### BUG-5 (P1) · Tidak ada konversi berantai (transitif)
```
gram → kg  = ada
kg   → ton = ada
gram → ton = ERROR
```
Sistem tidak menelusuri lewat satuan dasar.

---

### BUG-6 (P0 untuk kebutuhan Anda) · Kategori `pack` & `roll` tidak punya aturan sama sekali
Master satuan menyediakan `pak`, `bal`, `karton`, `sak`, `rol`, `gulung`, tapi
**nol aturan konversi** untuk semuanya:
```
1 pak → pcs = ERROR
1 rol → m   = ERROR
```

Dan ini **memang tidak bisa diselesaikan dengan aturan global** — persis seperti
yang Anda sebutkan. Buktinya dari data master Anda sendiri:

| Kode | Nama | Isi 1 kemasan |
|---|---|---|
| A47 | Kancing uk 32L 4L hitam **1 Bks 144 Pcs** | **144** pcs |
| A46 | Kancing uk 28L 4L marble **1 Bks 400 Pcs** | **400** pcs |
| A57 | Plastik Super 38*50 **1 PacK 70PCS** | **70** pcs |
| A3  | Lisban bungkus Putih **1 Meter ISI 63M** | **63** meter |
| A303 | Hanteg Daluna **1pcs ISI 190pcs** | **190** pcs |

Tiga "Bks/Pack" dengan isi 144, 400, dan 70. Aturan global `pak→pcs` **mustahil**.
Konversi wajib **per item** — dan itulah gunanya `pack_size`, yang saat ini
tidak dipakai satu pun.

---

### BUG-7 (P2) · `formula_expr` disebut tapi tidak ada
Docstring `wms_units.py` menjanjikan `formula_expr` untuk konversi non-linear
("roll → meter tergantung panjang roll per material"). Field ini **tidak ada** di
model `ConversionIn`, tidak disimpan, dan tidak dibaca `convert_qty`. Spesifikasi mati.

---

### BUG-8 (P2) · Estimasi biaya PR ikut salah
`dewi_accessories_purchase.py`: `total_estimated = qty_requested(sudah base) × estimated_price`.
Saat input per pack, `estimated_price` yang diisi user adalah harga per pack →
total estimasi membengkak sebesar `pack_size`. Bug yang sama polanya dengan BUG-1.

---

## BAGIAN 2 — APAKAH STRUKTUR DATA SUDAH MENGAKOMODASI?

### Yang sudah ada (dan sudah benar)
`rahaza_materials`:
```
unit             : satuan dasar penyimpanan  (pcs / m / kg / rol / pak / lusin)
pack_unit        : nama satuan kemasan       (pak / bal / karton / rol …)
pack_size        : isi 1 kemasan             (angka, per item)
display_in_packs : tampilkan stok dalam kemasan?
unit_cost        : harga satuan
```
Ledger stok (`core/stock_service`) menyimpan **satuan dasar** — ini keputusan
arsitektur yang tepat dan tidak perlu diubah.

### Kondisi data saat ini
```
total material                : 1.031
display_in_packs = true       :     0   ← fitur tidak dipakai sama sekali
pack_size > 1                 :     0
```

Distribusi satuan aksesoris:
```
pcs   232        rol   74  ← satuan kemasan dipakai sebagai satuan dasar
m      12        pak   14  ← idem
                 lusin   3  ← idem
```
**91 dari 335 aksesoris (27%)** memakai satuan kemasan sebagai satuan dasar.
"Stok 9 rol" tidak diketahui setara berapa meter → tidak bisa dipakai BOM,
tidak bisa dihitung HPP per pcs.

Kabar baiknya: informasinya **sudah ada tapi terkubur di nama item**
— 14 item punya pola eksplisit `ISI <n>`, 279 item mencantumkan satuan kemasan.
Ini bisa jadi bahan pengisian awal (dengan verifikasi Anda).

### Keterbatasan struktur (jawaban langsung: BELUM cukup)

| # | Keterbatasan | Contoh nyata yang gagal |
|---|---|---|
| 1 | **Hanya 1 level kemasan** | pcs → bks (144) → karton (12 bks). Tidak bisa. |
| 2 | **Hanya 1 jenis kemasan per item** | Supplier A jual per `pak`, supplier B per `lusin`. Tidak bisa. |
| 3 | **Tidak ada pemisahan satuan beli / simpan / pakai** | Beli `rol`, simpan `meter`, pakai `cm`. ERP standar punya `purchase_uom` / `stock_uom` / `consumption_uom`. Di sini hanya 1 `unit`. |
| 4 | **`unit_cost` tidak punya penanda "per satuan apa"** | Akar penyebab BUG-1. Tidak ada `cost_uom`. |
| 5 | **`pack_size` tidak berversi** | Kalau isi pak berubah 144 → 100, tampilan stok lama ikut berubah retroaktif (ledger aman karena base unit, tapi laporan "dalam pak" jadi salah). |
| 6 | **Konversi global tidak bisa di-override per item** | `wh_unit_conversions` tidak punya kolom `material_id`. |
| 7 | **Tidak ada pembulatan/kebijakan pecahan** | 1,5 pak = 216 pcs → boleh? Beli 250 pcs = 1,74 pak → dibulatkan ke mana? Tidak diatur. |
| 8 | **Riwayat pergerakan tidak menyimpan satuan input asli** | Ledger cuma simpan 144 pcs; tidak terekam bahwa user mengetik "1 pak". Audit trail hilang. |

---

## BAGIAN 3 — USULAN PERBAIKAN

### Tahap 1 — Hentikan pendarahan (P0, wajib duluan)
1. **Perbaiki BUG-1**: konversi harga saat `input_unit == "pack"`
   (`unit_cost ÷ pack_size`) di Terima Barang + Purchase Request.
   Label UI dibuat eksplisit: "Harga per pak" / "Harga per pcs".
2. **Audit jurnal lama**: cek apakah ada penerimaan sebelumnya yang terlanjur
   salah. (Saat ini DB bersih dari transaksi, jadi kemungkinan besar aman —
   tapi wajib dicek sebelum produksi.)
3. **Auto-seed satuan saat startup** (pola `ensure_unit_master()` seperti Cutting)
   supaya modul tidak pernah kosong lagi.

### Tahap 2 — Jadikan konversi berlaku menyeluruh (P0)
4. Buat **satu helper SSOT** `core/uom.py`:
   ```
   to_base(material, qty, input_unit)   → qty dalam satuan dasar
   from_base(material, qty, target)     → qty dalam satuan tampilan
   cost_to_base(material, cost, input_unit) → harga per satuan dasar
   ```
   Semua pintu masuk **wajib** lewat helper ini — bukan menghitung sendiri.
5. Pasang helper itu di **11 titik yang sekarang kosong** (Gudang Receiving, PO,
   Putaway, Opname, Pengeluaran Material, Warehouse Smart, Stok manual, Cutting,
   plus Opname/Peminjaman/Request aksesoris).
6. Setiap baris ledger menyimpan `input_qty` + `input_uom` + `factor_used`
   → audit trail utuh, dan bila `pack_size` berubah, riwayat tetap benar.

### Tahap 3 — Perkuat struktur (P1)
7. Ganti `pack_unit`/`pack_size` tunggal dengan **daftar kemasan**:
   ```
   uoms: [
     { uom: "pcs",  factor: 1,   is_base: true },
     { uom: "pak",  factor: 144, is_purchase_default: true, barcode: "..." },
     { uom: "ktn",  factor: 1728 }
   ]
   ```
   Menyelesaikan keterbatasan #1, #2, #3, #6 sekaligus. `pack_unit`/`pack_size`
   lama tetap dibaca sebagai fallback (tanpa migrasi paksa).
8. Tambah `cost_uom` pada material dan pada setiap baris transaksi.
9. Aturan konversi global: **kebalikan otomatis** (`1/factor`) + **penelusuran
   berantai** lewat satuan dasar (menutup BUG-4 & BUG-5).

### Tahap 4 — Rapikan data (P1, butuh Anda)
10. Layar **"Setup Konversi Kemasan"**: daftar 335 aksesoris + 143 kain, dengan
    kolom `isi per kemasan` yang **sudah diisi tebakan hasil parsing nama**
    (mis. A47 → 144 dari teks "1 Bks 144 Pcs"), status *belum diverifikasi*.
    Anda tinggal mengoreksi & mencentang. Tanpa layar ini, 478 item diisi manual
    satu per satu lewat form edit.
11. Tangani 91 item yang satuan dasarnya masih satuan kemasan
    (74 rol / 14 pak / 3 lusin) — perlu keputusan Anda per grup:
    tetap `rol` sebagai dasar, atau turunkan ke `meter`/`pcs`?

---

## BAGIAN 4 — Yang perlu Anda putuskan

1. **Perbaiki bug dulu (Tahap 1+2) atau langsung rombak struktur (Tahap 3)?**
   Saran saya: Tahap 1 & 2 dulu — bug harga & opname bisa merusak data nyata
   begitu operasional jalan.

2. **Satuan dasar untuk 91 item "rol/pak/lusin"** — mau diturunkan ke satuan
   terkecil (meter/pcs), atau tetap dihitung per rol/pak?

3. **Butuh multi-level kemasan (pcs → bks → karton)?** Kalau tidak, Tahap 3 bisa
   disederhanakan dan lebih cepat selesai.

4. **Layar Setup Konversi massal** — perlu dibuat, atau cukup isi manual lewat
   form edit material yang sudah ada?
