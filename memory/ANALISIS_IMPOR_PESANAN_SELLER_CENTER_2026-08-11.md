# Analisis — Alur Pesanan Berbasis IMPOR EXCEL Seller Center (bukan integrasi API)

**Tanggal:** 2026-08-11 · **Sumber fakta:** berkas nyata milik owner
`Untuk Dikirim pesanan-2026-07-19-14_05.xlsx` (TikTok Shop, sheet `OrderSKUList`)
+ telusur kode. **Belum ada kode yang diubah.**

---

## 1. KEPUTUSAN ARAH DARI OWNER (dasar analisis ini)

| Hal | Keputusan |
|---|---|
| Integrasi API marketplace | **DIBATALKAN** — tidak bisa dilakukan |
| Sumber data pesanan | **Ekspor Excel dari Seller Center** (impor manual) |
| Sumber data pengiriman | **Ekspor Excel kedua** (yang sudah dikirim) |
| Siapa memegang Seller Center | Marketing (kelola pesanan) **dan** Gudang (fulfillment) — dua akses terpisah |
| Peran sistem ini | **INPUT + MONITORING**: pesanan mana yang sudah diurus, mana belum. Bukan pengganti Seller Center |
| Fulfillment fisik | Tetap dikerjakan **di Seller Center oleh Gudang** |

Konsekuensi langsung: sistem **tidak** perlu mencetak label, tidak perlu resi
sendiri, tidak perlu memesan stok untuk menahan penjualan. Yang wajib benar
adalah **daftar kerja** dan **bukti sudah/belum dikirim**.

---

## 2. APA YANG BENAR-BENAR ADA DI BERKAS EKSPOR (terukur)

**Bentuk berkas**
* 1 sheet `OrderSKUList`, **65 kolom**
* **Baris 1 = header, BARIS 2 = deskripsi kolom** (bukan data!), data mulai **baris 3**
* **601 baris data** = **559 Order ID** (36 pesanan punya >1 baris) ⇒ **1 baris = 1 SKU dalam 1 pesanan**
* Periode `Created Time` 04/07/2026 → 19/07/2026 · format `dd/mm/yyyy hh:mm:ss` (**teks**)

**Isi yang relevan**

| Fakta | Angka | Artinya untuk sistem |
|---|---|---|
| `Order Status` | `Perlu dikirim` 601/601 | berkas ini = **daftar kerja** (belum dikirim) |
| `Order Substatus` | `Menunggu pengambilan` 597 · `Menunggu pengiriman` 4 | tahap detail bisa dipakai monitoring |
| `Shipped Time` / `Delivered Time` | **0/601 terisi** | berkas ini **tidak bisa** jadi bukti kirim ⇒ **butuh ekspor ke-2** (benar sesuai rencana owner) |
| `Tracking ID` | 597/601 sudah ada | resi sudah terbit di tahap ini (RTS sudah diklik) |
| **`Seller SKU`** | **0/601 terisi (KOSONG SEMUA)** | ⚠️ **pencocokan ke katalog lewat SKU MUSTAHIL** |
| `SKU ID` (id platform) | 601/601, **83 SKU unik** | satu-satunya kunci produk yang stabil |
| `Product Name` + `Variation` | terisi | kunci bantu (rawan berubah) |
| `Normal or Pre-order` | **Pre-order 514 (85%)** · Normal 87 | mayoritas **barang belum ada** saat pesanan masuk |
| `Payment Method` | **Bayar di tempat (COD) 493 (82%)** · transfer 37 · QRIS 24 · PayLater 20 | uang **belum diterima** saat kirim |
| `Order Channel` | **LIVE 418 (70%)** · Videos 99 · Product cards 84 | atribusi live selling **tersedia dari ekspor** |
| `Creator Handle` | 515/601 | atribusi kreator/KOL **tersedia dari ekspor** |
| `Order Amount` | Rp **62.805.113** (559 pesanan) | ⚠️ nilai **per pesanan, DIULANG di setiap baris** |
| `SKU Subtotal After Discount` | Rp **59.783.811** (601 baris) | nilai **per baris** — ini yang boleh dijumlah |
| Data pembeli | `Recipient` `L***`, `Phone` `(+62)856***`, `Detail Address` `*****`, `Districts`/`Villages` `*****`, `Zipcode` kosong | **PII disamarkan platform** ⇒ sistem tidak mungkin (dan tidak perlu) mencetak label |
| `Warehouse Name` | `Outfit Boutique` 601/601 | penanda toko/gudang dari ekspor |
| Kurir | `J&T Express` 596 · JNE 1 · kosong 4 | |
| `Weight(kg)` | 601/601 | bisa dipakai analisis ongkir |

**Kesiapan mesin impor yang sudah ada (diuji):**
`parse_date('16/07/2026 18:18:10')` ✅ · `parse_number('62.805.113')` → 62805113 ✅ ·
`parse_number('Rp 59.783.811')` ✅ — jadi pembacaan tanggal & rupiah **sudah aman**.

---

## 3. TIGA RISIKO YANG WAJIB DITUTUP SEBELUM BARIS PERTAMA MASUK

### R1. `Seller SKU` kosong ⇒ butuh **kamus SKU platform → item katalog**
Rancangan impor yang ada mencocokkan produk lewat **SKU**. Dengan ekspor ini
pencocokan itu **selalu gagal** (0/601). Yang tersedia hanya `SKU ID` platform
(83 unik) + nama produk + variasi.

**Usul:** koleksi pemetaan sekali-pakai-selamanya
`marketing_platform_sku_map`: `(account_id, platform, platform_sku_id)` →
`catalog_item_id`. Impor pertama menampilkan daftar SKU ID yang **belum dikenal**
(83 baris, sekali kerja), staf memetakannya, impor berikutnya otomatis.
Tanpa ini, laporan "produk apa yang laku" akan memakai nama teks bebas dan
terpecah — cacat yang baru saja kita tutup di modul lain.

### R2. `Order Amount` diulang per baris ⇒ **omzet bisa dobel**
36 pesanan multi-baris. Menjumlahkan `Order Amount` per baris ⇒ 36 pesanan
dihitung dua kali. **Aturan wajib:** nilai pesanan diambil **satu kali per
Order ID**; yang dijumlah per baris hanya `SKU Subtotal After Discount`.

### R3. 85% Pre-order + 82% COD ⇒ **jangan pakai reservasi stok**
Alur order manual yang ada **menolak (409)** bila stok jual kurang. Kalau ekspor
ini dimasukkan lewat jalur itu, **±85% baris akan ditolak** karena barangnya
memang belum dibuat. Untuk model impor-monitoring:
* **jangan** memesan/mengurangi stok;
* tandai `Pre-order` sebagai **kebutuhan produksi** (ini justru sinyal yang
  hari ini tidak ada: toko → produksi);
* COD berarti uang **belum** diterima ⇒ pengakuan pendapatan menunggu pencairan
  platform (bahan keputusan Finance, lihat §6).

---

## 4. RANCANGAN: DUA IMPOR, SATU DAFTAR KERJA

```
SELLER CENTER (TikTok/Shopee)
   │
   ├── Ekspor A: "Perlu Dikirim"  ──► IMPOR A (Marketing)
   │        601 baris / 559 order      → daftar kerja: PERLU DIKIRIM
   │
   └── Ekspor B: "Dikirim/Selesai" ──► IMPOR B (Gudang)
            berisi Shipped Time,          → tandai: SUDAH DIKIRIM (+tanggal, resi)
            Delivered Time, Tracking ID
                                     │
                     ┌───────────────┴───────────────┐
                     │  MONITORING (nilai tambah)    │
                     │  · belum dikirim > N hari      │
                     │  · pre-order menumpuk per SKU  │
                     │  · ada di A tapi tak pernah    │
                     │    muncul di B (bocor)         │
                     │  · dibatalkan sesudah RTS      │
                     └────────────────────────────────┘
```

**Kunci pencocokan (harus tunggal & jelas)**

| Tingkat | Kunci | Alasan |
|---|---|---|
| Pesanan | `(account_id, platform, Order ID)` | Order ID unik per platform |
| Baris pesanan | `(Order ID, SKU ID, Variation)` | `Seller SKU` kosong; 36 pesanan multi-baris |
| Impor B → data lama | `Order ID` (utama) · `Tracking ID` (cadangan) | resi sudah ada sejak tahap "perlu dikirim" |

**Status monitoring yang diusulkan** (sederhana, cukup 4):
`perlu_dikirim` → `sudah_dikirim` → `terkirim` · plus `dibatalkan/retur`.
Semua **berasal dari ekspor**, tidak diketik manual ⇒ tidak ada dua versi kebenaran.

**Sifat impor yang wajib:**
* **Idempoten**: impor berkas yang sama dua kali **tidak** menggandakan (kunci di atas)
* **Update, bukan sisip** untuk baris yang sudah ada (status/waktu/resi diperbarui)
* **Riwayat + rollback** per sesi impor (mekanismenya **sudah ada** di F17)
* **Lewatkan baris ke-2** (deskripsi kolom) secara otomatis
* Simpan **`Order Channel`** & **`Creator Handle`** ⇒ bonus: omzet live & kontribusi
  kreator langsung terisi dari ekspor, tanpa input manual

---

## 5. DAMPAK KE YANG SUDAH ADA (apa dipakai, apa dimatikan)

| Komponen | Nasib | Alasan |
|---|---|---|
| `core/marketing_import_schema.py` + `marketing_import_engine.py` + wizard 6 langkah | **DIPAKAI, diperluas** | mesin impor tanpa AI, pembacaan tanggal/rupiah, template, riwayat, rollback sudah terbukti |
| Jenis impor `orders` yang ada | **diganti/ditambah** jenis baru `marketplace_orders` (per baris SKU) + `marketplace_shipments` | kolom & aturannya beda jauh dari jenis `orders` sekarang |
| Webhook marketplace (`/api/marketing/webhooks/*`) | **dimatikan eksplisit** (410 + pesan), bukan dibiarkan | jalur ini membuat pesanan tanpa toko/nomor/uang (terbukti: gate MKS-1 merah). Kalau dibiarkan hidup, satu kiriman uji saja merusak laporan |
| "Integrasi API" (kredensial + test) | **disembunyikan/ditandai tidak dipakai** | masih *placeholder*; memberi harapan palsu |
| `POST /api/marketing/orders` (manual) + reservasi stok | **tetap ada** untuk pesanan manual/luar marketplace, **tidak dipakai** jalur impor | 85% pre-order akan ditolak (R3) |
| Modul `fulfillment` internal (alokasi FG, pick, pack, scan-out, COGS) | **di luar lingkup** model ini | gudang fulfill di Seller Center; alokasi FG internal hanya relevan bila kelak stok dikelola di sistem |
| Katalog toko | **dipakai sebagai master produk** (tujuan pemetaan SKU ID) | supaya laporan per produk tidak pakai teks bebas |

---

## 6. PERTANYAAN KEPUTUSAN (perlu jawaban owner sebelum dibangun)

1. **Ekspor B** — laporan mana yang dipakai gudang: ekspor dengan status
   *Dikirim*/*Selesai* dari menu yang sama (kolomnya identik, hanya
   `Shipped Time`/`Delivered Time` terisi), atau laporan lain? **Kalau boleh,
   kirim 1 contoh berkasnya** supaya pemetaannya pasti, bukan dugaan.
2. **Stok** — apakah sistem sama sekali tidak mengurus stok (murni monitoring),
   atau nanti tetap ingin tahu "sisa stok toko"? (menentukan perlu/tidaknya
   pemetaan ke FG gudang)
3. **Pre-order (85%)** — mau dijadikan **daftar kebutuhan produksi** otomatis
   (per SKU per tanggal) atau cukup ditampilkan sebagai penanda?
4. **Uang** — dengan COD 82%, pendapatan diakui saat *kirim*, saat *terkirim*,
   atau saat *dana cair dari platform*? (menentukan angka mana yang dipakai
   laporan: `Order Amount` vs `SKU Subtotal After Discount`)
5. **Multi-toko** — apakah setiap ekspor selalu satu toko (di berkas ini
   `Warehouse Name = Outfit Boutique`)? Toko dipilih di wizard, atau dibaca dari
   kolom itu?
6. **Retur/pembatalan** — apakah ada ekspor terpisah untuk itu, atau cukup
   terbaca dari perubahan status di ekspor berikutnya?

---

## 7. PERKIRAAN PEKERJAAN (bila disetujui)

| Fase | Isi | Bukti selesai |
|---|---|---|
| 1 | Jenis impor `marketplace_orders` (65 kolom, lewati baris deskripsi, kunci per baris SKU, idempoten, update-bukan-dobel) + kamus `platform_sku_id → item katalog` (layar pemetaan sekali kerja untuk 83 SKU) | impor berkas asli 601 baris → 559 pesanan, jalankan 2× tidak menggandakan |
| 2 | Jenis impor `marketplace_shipments` + layar **Monitoring Pesanan** (perlu dikirim / sudah dikirim / bocor / pre-order menumpuk) | impor B menandai n pesanan terkirim; sisa "belum diurus" tampil dengan umur hari |
| 3 | Matikan eksplisit webhook + tandai Integrasi API tidak dipakai + gate baru "pesanan tanpa toko/nomor = merah" | gate hijau, jalur cacat tidak bisa dipakai lagi |
| 4 | Bonus dari kolom yang sudah ada: omzet per **Order Channel LIVE** & kontribusi **Creator Handle** otomatis | laporan live & KOL terisi tanpa input manual |

---

## 8. CATATAN TEKNIS SINGKAT UNTUK PELAKSANA

* Header di baris 1, **skip baris 2**, data dari baris 3.
* `Order Amount` per **pesanan** (jangan dijumlah per baris) · `SKU Subtotal
  After Discount` per **baris**.
* Waktu berformat `dd/mm/yyyy hh:mm:ss` **teks** → `parse_date()` sudah menangani.
* `Seller SKU` bisa kosong total → **jangan** dijadikan kolom wajib.
* PII pembeli sudah disamarkan platform → jangan rancang fitur yang butuh alamat
  lengkap.
* Nama kolom bisa berbeda antar platform (Shopee ≠ TikTok) → sinonim header
  ditaruh di `core/marketing_import_schema.py`, bukan di layar.
