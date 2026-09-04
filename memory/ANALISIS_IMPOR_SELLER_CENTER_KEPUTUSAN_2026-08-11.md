# Analisis Keputusan — Impor Excel Seller Center (Ekspor A + Ekspor B)

**Tanggal:** 2026-08-11 · **Sesi:** analisis saja, **TIDAK ADA KODE APLIKASI YANG DIUBAH**
**Sumber fakta:** berkas nyata owner `Untuk Dikirim pesanan-2026-07-19-14_05.xlsx`
(TikTok Shop, sheet `OrderSKUList`, 65 kolom, 601 baris data) + **menjalankan kode
impor yang ada** pada berkas itu + membaca isi database.

**Cara mengulangi seluruh bukti di dokumen ini:**
```bash
cd /app && python3 scripts/_analyze_seller_center_export.py          # isi berkas per kolom
cd /app && python3 scripts/_analyze_seller_center_money_keys.py      # uang & kunci produk
cd /app/backend && python3 /app/scripts/_prove_import_decisions.py   # 5 keputusan
cd /app/backend && python3 /app/scripts/_prove_import_orders_result.py  # hasil impor nyata
```
Keempat skrip **read-only**: tidak menulis ke MongoDB, tidak menyentuh berkas aplikasi.

---

## 0. KEPUTUSAN OWNER (sesi ini) DAN STATUSNYA SETELAH DIUJI

| # | Keputusan owner | Status setelah diuji |
|---|---|---|
| 1 | Ekspor B = menu yang sama, filter *Dikirim/Selesai* — **tapi mungkin format terpisah**; minta bantuan: bisa tanpa AI? kalau tidak, bagaimana dengan AI? | **Terjawab penuh** — lihat §2. Jawaban: **tanpa AI bisa dan harus jadi jalur utama**; AI **tidak bisa dipakai hari ini** (alasan teknis konkret) dan tetap tidak dibutuhkan |
| 2 | **Tetap kurangi stok gudang saat impor bukti kirim** | **Bisa, waktunya tepat, tapi hari ini MUSTAHIL** — 4 mata rantai kosong semua. Lihat §3 (ada 1 konsekuensi pembukuan yang harus Anda putuskan) |
| 3 | Pre-order → **abaikan dulu** | Diterima. Tetap **disimpan sebagai kolom** (gratis, 1 kolom) supaya nanti tidak perlu impor ulang. Lihat §3.4 |
| 4 | **Hanya laporan omzet marketing**, tanpa jurnal keuangan otomatis | Diterima — **tapi angka mana** belum ditentukan, dan pilihan yang salah menggeser laporan **16,8%**. Lihat §4 |
| 5 | Toko & retur — **belum dipilih**, minta dipastikan dulu | **Ada jawaban berbukti** untuk keduanya. Lihat §5 |

---

## 1. TEMUAN YANG MEMBATALKAN KESIMPULAN SESI LALU

Sesi lalu saya menulis: *"mesin impor tanpa AI … sudah cocok"*. **Itu salah, dan saya
membuktikannya salah dengan menjalankannya.**

Berkas asli dimasukkan ke jenis impor `orders` yang ada sekarang, lewat fungsi yang
sama yang dipakai wizard (`marketing_import_engine.build_rows`):

```
baris dikirim ke mesin : 602   (601 data + 1 baris deskripsi kolom)
baris LOLOS validasi   : 0
baris BERGALAT         : 602
```

**Nol dari 602.** Rinciannya:

| Jumlah | Galat | Penyebab pasti |
|---|---|---|
| 601× | `Status Pesanan: 'Perlu dikirim' tidak dikenali` | enum sistem hanya `new/paid/packed/shipped/delivered/completed/cancelled/returned` |
| 596× | `Kurir: 'J&T Express' tidak dikenali` | enum kurir hanya `jnt/spx/sicepat/jne/…` — tidak ada kamus `"J&T Express" → jnt` |
| 1× | baris ke-2 (deskripsi kolom) masuk sebagai "pesanan" | endpoint `POST /upload` **tidak punya** opsi lewati-baris |

Dan yang lebih penting dari galat: **pemetaan kolomnya sendiri hanya 10 dari 65.**

```
metode      : exact 6 · synonym 2 · fuzzy 2 · suggest 15 · none 40
terpetakan  : 10/65
field wajib belum terpetakan : []      ⇒ mapping_report bilang "ready: True"
```

55 kolom dibuang, **termasuk SEMUA kolom uang**. Hasil nyatanya:

```
revenue         terisi 0 · jumlah Rp 0
total_payment   terisi 0 · jumlah Rp 0
price_final     terisi 0 · jumlah Rp 0
```
> Berkas bernilai **Rp 62.805.113** → jenis impor `orders` hari ini menghasilkan omzet **Rp 0**.

Kolom penting lain yang dibuang: `Order Amount`, `SKU Subtotal After Discount`,
`Tracking ID`, `Shipped Time`, `Delivered Time`, `Cancelled Time`,
`Cancelation/Return Type`, `Order Refund Amount`, `Sku Quantity of return`,
`Normal or Pre-order`, `Order Substatus`, `Warehouse Name`, `Purchase Channel`,
`Order Channel`, `Creator Handle`, `Package ID`, `Province`, `Regency and City`,
`Paid Time`, `RTS Time`.

**Satu kabar baik:** mesinnya **gagal dengan aman**, bukan diam-diam merusak.
`commit` menolak baris bergalat satu per satu (`rejected += 1`) dan menolak commit
kalau kolom wajib belum terpetakan. Jadi tidak ada risiko "data sampah masuk tanpa
ada yang sadar" — yang ada adalah **impor tidak bisa dipakai sama sekali**.

**Kesimpulan §1:** yang sudah benar adalah **mesinnya** (baca berkas, kamus header,
konversi tanggal/rupiah, pratinjau, riwayat, rollback, gagal-aman). Yang belum ada
adalah **jenis impornya** untuk bentuk data ini. Itu pekerjaan menulis daftar
(kolom + kamus nilai + kunci), bukan pekerjaan AI.

---

## 2. JAWABAN Q1 — "BISA TANPA AI? KALAU TIDAK, BAGAIMANA DENGAN AI?"

### 2.1 Kenapa tanpa AI BISA — dan terbukti tahan saat nama kolom berubah

Mesin memetakan header dengan 4 tingkat berjenjang, ambangnya **tetap** (bukan tebakan):

```
exact 1.00 · synonym 0.98 · fuzzy dipakai OTOMATIS ≥ 0.86
                         · fuzzy hanya DIUSULKAN ≥ 0.68 · di bawah itu tidak dipetakan
```

Saya uji ketahanannya dengan mengganti nama kolom, memakai jenis `orders` yang ada:

| Skenario header | Terpetakan | Siap commit? | Field yang hilang |
|---|---|---|---|
| Asli TikTok (65 kolom) | 10/65 | ya | — |
| **Diterjemahkan gaya Shopee-ID** (`No. Pesanan`, `Waktu Pesanan Dibuat`, `Total Pembayaran`, `No. Resi`, `Jasa Kirim`, …) | **14/65 (naik)** | ya | `payment_method` |
| Ekspor B (kolom `Shipped/Delivered` terisi) | 10/65 | ya | — |
| Rename ringan (`Order Id`, `Create Time`, `Qty`, `Tracking Number`) | 11/65 | ya | — |
| **Nama internal platform** (`ord_no`, `ts_created`, `amt_pay`, `awb`, `lgt`) | **3/65** | **TIDAK** | 7 field inti |

Dua hal yang dibuktikan tabel ini:

1. **Header berbahasa manusia — Indonesia maupun Inggris — aman.** Ganti nama
   sekalipun ke gaya Shopee, pemetaan justru **membaik** (kamus sinonimnya memang
   ditulis dari ekspor Shopee/TikTok/Tokopedia). Jadi kekhawatiran Anda
   *"Ekspor B mungkin format terpisah"* **tidak berbahaya**, selama header masih
   kata-kata yang dibaca manusia.
2. **Kalau benar-benar asing, sistem BERHENTI, bukan menebak.** `ready: False` ⇒
   `commit` ditolak dengan pesan kolom wajib mana yang belum terpetakan. Sekali
   dipetakan manual, **simpan sebagai Template** (`/import-templates` sudah ada) ⇒
   impor berikutnya otomatis. Sekali kerja, bukan tiap bulan.

### 2.2 Kenapa AI TIDAK bisa dipakai hari ini (bukan pendapat — hasil uji)

Saya coba panggil AI-nya:

```
panggilan AI GAGAL: AIError: ANTHROPIC_API_KEY belum dikonfigurasi
```

Penyebabnya ada di kode, dan **disengaja**: `backend/ai_cost_tracker.py:288-289`

```python
# 2026-07-27: hanya kunci Anthropic yang sah. Pemanggil lama masih meneruskan
# EMERGENT_LLM_KEY secara eksplisit — abaikan dan pakai kunci Claude resmi.
api_key = api_key if str(api_key or "").startswith("sk-ant-") else ANTHROPIC_API_KEY
```

Seluruh AI aplikasi ini sudah dipindah ke Claude (`claude-opus-4-8` /
`claude-sonnet-5` / `claude-haiku-4-5`) dan **sengaja mengabaikan** kunci LLM
platform. Artinya: **semua tombol AI mati sampai owner memasang `ANTHROPIC_API_KEY`
sendiri** (berbayar, tagihan ke Anda). Bukan hanya impor — semua fitur AI.

### 2.3 Kalau AI dinyalakan nanti, ia BOLEH melakukan apa

Ada dua "AI" berbeda di kode. Perbedaannya penting:

| | **AI importer lama** `routes/marketing_import.py` | **AI-assist** `POST /data-import/sessions/{id}/ai-assist` |
|---|---|---|
| Isi | 10 field: `date, revenue, orders, quantity, aov, gmv, conversion_rate, rating, product_name, sku` | mengusulkan field untuk kolom yang **belum** terpetakan |
| Perilaku | **agregasi `by_date`** — menjumlah revenue per TANGGAL | tidak menulis apa pun; hanya usulan |
| Untuk berkas ini | **BERBAHAYA** | **Aman** |

Bukti "berbahaya" — heuristik importer AI lama pada 65 kolom asli:

```
Order ID              → orders          (nomor pesanan dijadikan JUMLAH order)
Order Status          → orders
Order Substatus       → orders
Normal or Pre-order   → orders
Order Amount          → revenue
SKU Subtotal Before   → revenue         ← 4 kolom uang berbeda menumpuk di 1 field
SKU Subtotal After    → revenue
Order Refund Amount   → revenue
Item Insurance        → product_name    ← kolom uang jadi nama produk
```
Ditambah agregasi `by_date`: 601 baris pesanan diringkas jadi beberapa baris tanggal
⇒ **Order ID, resi, SKU, kurir, kreator, kota HILANG semua.** Importer itu memang
dibuat untuk rekap harian, bukan untuk daftar pesanan. **Jangan dipakai untuk berkas ini.**

Sedangkan AI-assist di wizard tanpa-AI sudah dikurung dengan benar (diperiksa
langsung di kodenya, keempatnya `True`):

* hanya menyentuh kolom **belum** terpetakan
* **tidak pernah** menimpa hasil `exact`/`synonym`/manual
* hasilnya **usulan**, wajib disetujui manusia
* kalau AI gagal ⇒ pemetaan manual tetap jalan

### ✅ Rekomendasi Q1
1. **Jalur utama = TANPA AI.** Kamus header + template tersimpan. Ini yang dibangun.
2. **AI = tombol opsional** (AI-assist yang sudah ada), hanya untuk header yang
   benar-benar tak dikenal, hasilnya usulan.
3. **Jangan** pakai `routes/marketing_import.py` untuk pesanan marketplace.
   Sebaiknya jenis file ini **dilarang** masuk ke sana supaya tidak ada staf yang
   salah pintu.
4. Keputusan Anda yang diperlukan: **mau memasang `ANTHROPIC_API_KEY` atau tidak.**
   Kalau tidak — rencana ini **tetap jalan 100%**; yang mati hanya tombol AI opsional.
5. **Tetap kirim 1 contoh Ekspor B.** Bukan karena tanpa contoh tidak bisa, tapi supaya
   kamus nilai (`Dikirim`, `Selesai`, `Dibatalkan`, `Pengembalian`, dst.) ditulis dari
   teks asli, bukan dugaan saya. Kamus nilai inilah penyebab 601 galat di §1.

---

## 3. JAWABAN Q2 — "KURANGI STOK GUDANG SAAT IMPOR BUKTI KIRIM"

### 3.1 Waktunya sudah tepat
Memotong stok saat **bukti kirim** (Ekspor B) adalah pilihan yang benar, dan
menghindari jebakan yang saya khawatirkan sesi lalu: 85% pesanan adalah **Pre-order**
(barang belum dibuat saat pesanan masuk). Kalau stok dipotong/direservasi saat
**Ekspor A**, ±514 dari 603 pcs akan ditolak karena barangnya memang belum ada.
Saat Ekspor B, barang sudah jadi dan sudah keluar ⇒ **pemotongan itu jujur**.

### 3.2 Tapi hari ini MUSTAHIL — 4 mata rantai, keempatnya kosong

Agar 1 pcs bisa dipotong, rantai ini harus utuh:

```
SKU platform (TikTok)  →  item katalog toko  →  fg_material_id  →  baris stok FG di lokasi
```

Keadaan database **sekarang** (dan sama di backup `auto_20260810_190000`):

| Mata rantai | Keadaan | Angka |
|---|---|---|
| Kamus SKU platform → item katalog | **tidak ada** (tidak ada field/koleksinya) | 0 |
| Item katalog toko | **kosong** | 0 katalog · 0 item · 0 akun toko |
| Master material bertipe produk jadi (FG) | **tidak ada satu pun** | 0 dari 12 material |
| Baris stok FG di gudang | **tidak ada** | 0 baris (12 baris stok yang ada = benang/kancing/label/zipper, 32.950 unit) |

Kebutuhan dari **satu** berkas ini: **83 SKU platform, 603 pcs** (514 pcs Pre-order).

> **0 dari 603 pcs bisa dipotong hari ini.** Kalau pemotongan stok dipaksa
> dinyalakan, hasilnya salah satu dari tiga, dan ketiganya buruk:
> **(i)** 601 baris gagal semua ⇒ bukti kirim tidak pernah tercatat;
> **(ii)** stok jadi **MINUS** ⇒ laporan stok mustahil dipercaya;
> **(iii)** pemotongan diam-diam dilewati ⇒ pesanan bertanda "sudah dikirim"
> padahal stok tidak bergerak — **ini yang paling berbahaya**, karena kelihatan berhasil.

**Aturan yang tidak bisa dilanggar: stok tidak boleh KELUAR sebelum pernah MASUK.**
Di sistem ini FG hanya lahir dari (a) packing produksi/maklon yang lolos QC, atau
(b) penerimaan gudang (WMS receiving). Data produksi ada (3 `production_jobs`,
4 `dewi_cmt_jobs`, 2 `dewi_cmt_deliveries`) tetapi **belum menghasilkan satu baris FG
pun**. Jadi pekerjaan §3 bukan "tambah fitur potong stok", melainkan
**menyambung hulunya lebih dulu**.

### 3.3 Konsekuensi pembukuan yang harus Anda putuskan

Anda memilih **tanpa jurnal otomatis** untuk penjualan (Q4). Tapi memotong stok
**bukan** peristiwa netral bagi buku: nilai persediaan turun.

Di kode sekarang, penurunan stok + **COGS otomatis** hanya terjadi di satu jalur:
`/api/fulfillment/…/dispatch` → Scan-Out gudang → `finalize_fulfillment_dispatch()`
→ `stock_service` + `post_cogs_shipment()` (idempoten). Jalur itu mengandaikan
alokasi FG → picking → packing → scan-out **di dalam sistem** — padahal gudang Anda
fulfill **di Seller Center**, jadi jalur itu tidak akan pernah dilalui.

Maka ada 3 pilihan, harus dipilih **sebelum** dibangun:

| Pilihan | Stok | Buku | Akibat |
|---|---|---|---|
| **A** (saya sarankan) | turun saat Impor B | **COGS otomatis** per sesi impor, idempoten | stok & buku sejalan; penjualan tetap manual sesuai Q4 |
| **B** | turun saat Impor B | tanpa jurnal apa pun | persediaan di buku **tidak turun** padahal barang keluar ⇒ laba tampak besar, aset tampak besar |
| **C** | tidak turun (monitoring saja) | tidak ada | paling cepat & paling jujur untuk versi pertama; stok dinyalakan di fase berikutnya |

Catatan tambahan: HPP/COGS di sistem ini dihitung dari snapshot HPP per Work Order.
**FG tanpa Work Order ⇒ COGS = 0** — jadi pilihan A masih butuh HPP terisi di master FG,
kalau tidak jurnalnya bernilai nol (jurnal ada, angkanya kosong).

### 3.4 Pre-order — "abaikan dulu" (Q3), tapi 1 kolom tetap disimpan
`Normal or Pre-order` disimpan apa adanya sebagai kolom (nol biaya). **Tidak ada**
layar, tidak ada sinyal ke Produksi di versi ini. Kalau nanti Anda mau daftar
kebutuhan produksi, datanya sudah ada — tidak perlu impor ulang 601 baris.

### ✅ Rekomendasi Q2 — **dua langkah, jangan satu**
* **Langkah 1 (sekarang):** Impor A + Impor B **tanpa** potong stok (pilihan C).
  Pesanan, status, bukti kirim, monitoring, omzet — semuanya jalan dan bisa dipakai
  besok. Di layar dipasang penanda jujur: *"stok tidak dipotong dari impor ini"*.
* **Langkah 2 (setelah rantainya utuh):** nyalakan potong stok dengan pilihan **A**.
  Syarat nyala, semuanya terukur dan bisa dijadikan gate:
  1. master FG ada + `hpp` terisi;
  2. item katalog toko tertaut `fg_material_id`;
  3. kamus 83 SKU platform → item katalog terisi;
  4. FG pernah masuk gudang (dari packing QC atau penerimaan) ⇒ ada baris stok FG.
  Selama salah satu belum terpenuhi, sakelarnya **tidak boleh** bisa dinyalakan.

Ini bukan penundaan tanpa alasan: dengan 0/4 rantai, "potong stok" hari ini
menghasilkan salah satu dari tiga akibat buruk di §3.2 — bukan fitur.

---

## 4. JAWABAN Q4 — OMZET MARKETING: ANGKA MANA, DAN CARA MENGHINDARI DOBEL

### 4.1 `Order Amount` BUKAN omzet penjual — ini terbukti dari berkasnya sendiri

Saya rekonstruksi rumusnya, dan **pas untuk 521 dari 559 pesanan** (selisih total
hanya Rp 26.614 = 0,04%):

```
Order Amount = SKU Subtotal After Discount
             + Shipping Fee After Discount
             + Buyer Service Fee
             + Handling Fee
             − Payment platform discount
```

| Komponen (1× per pesanan) | Nilai |
|---|---|
| **Order Amount** — yang dibayar **pembeli** | **Rp 62.805.113** |
| SKU Subtotal After Discount — omzet **produk** (jumlah per baris) | **Rp 59.783.811** |
| Shipping Fee After Discount — ongkir dibayar pembeli | Rp 1.744.000 |
| Buyer Service Fee | Rp 679.789 |
| Handling Fee | Rp 609.460 |
| Payment platform discount (pengurang) | −Rp 38.561 |

⇒ Memakai `Order Amount` sebagai "omzet marketing" membuat laporan **Rp 3.021.302
(5,1%) lebih tinggi**, karena ikut menghitung **ongkir dan biaya layanan yang bukan
pendapatan penjual**.

### 4.2 Bahaya kedua: dobel karena 1 baris = 1 SKU

`Order Amount` **diulang di setiap baris** pesanan yang sama.

| Kolom | Dijumlah **per baris** | Dijumlah **1× per Order ID** | Selisih |
|---|---|---|---|
| Order Amount | Rp 73.377.237 | **Rp 62.805.113** | **+Rp 10.572.124 (16,8%)** |
| SKU Subtotal After Discount | **Rp 59.783.811** | Rp 55.640.853 | −Rp 4.142.958 (kurang 6,9%) |

36 pesanan punya lebih dari 1 baris (601 baris, 559 pesanan, satu pesanan sampai 4 baris).

**Aturan wajib, dua-duanya sekaligus:**
* `Order Amount`, ongkir, biaya layanan → **ambil sekali per Order ID**
* `SKU Subtotal After Discount`, `Quantity` → **boleh dijumlah per baris**

Melanggar arah pertama ⇒ omzet naik 16,8%. Melanggar arah kedua ⇒ omzet turun 6,9%.

### 4.3 Bahaya ketiga: kunci dedupe yang ada sekarang MENGHILANGKAN data
Jenis `orders` memakai dedupe `(account_id, order_id)` — itu berarti *1 pesanan = 1 baris*.
Contoh nyata dari berkas Anda, Order `585052724093224248`:

```
SKU 1736470663036306470  qty 1  Rp 88.310  POLKA BLACK, M
SKU 1736486378273604646  qty 1  Rp 88.309  POLKA WHITE, M
```
Dengan dedupe sekarang **hanya 1 dari 2 baris bertahan** ⇒ item lain **HILANG**
(bukan dobel — hilang). Kunci yang benar: **`(account_id, platform, Order ID, SKU ID)`**.

### ✅ Rekomendasi Q4
* **Omzet marketing = `SKU Subtotal After Discount`** (dijumlah per baris) —
  Rp 59.783.811 untuk berkas ini. Itu pendapatan produk penjual.
* Simpan juga **`Order Amount` per pesanan** (Rp 62.805.113) di tingkat **pesanan**,
  diberi label jelas *"Dibayar Pembeli (termasuk ongkir & biaya layanan)"*.
  Dua angka, dua label, tidak dicampur — supaya tidak ada dua versi kebenaran.
* Ongkir & biaya layanan disimpan **1× per pesanan**, tidak dijumlah per baris.
* **Tanpa jurnal otomatis** (sesuai keputusan Anda). Layarnya diberi catatan
  *"laporan marketing — bukan angka pembukuan"* supaya tidak dipakai untuk pajak.
* Kalau Anda mau membandingkan dengan **uang yang benar-benar cair**, itu ada di
  laporan **settlement/penghasilan** platform (bukan di ekspor ini). Bisa jadi
  jenis impor ke-3 kalau nanti dibutuhkan — jangan dipaksa dari berkas ini.

---

## 5. JAWABAN Q5 — TOKO & RETUR (yang belum Anda pilih)

### 5.1 Toko — jangan dibaca dari kolom, tapi kolomnya dipakai sebagai PEMERIKSA

Kandidat penanda toko di berkas, dan apa sebenarnya isinya:

| Kolom | Terisi | Unik | Nilai | Apa artinya sebenarnya |
|---|---|---|---|---|
| `Warehouse Name` | 601/601 | **1** | `Outfit Boutique` | nama **gudang** yang diatur penjual di Seller Center — bukan nama toko |
| `Purchase Channel` | 601/601 | 1 | `TikTok` | **platform** |
| `Fulfillment Type` | 601/601 | 1 | `Fulfillment by seller` | dikirim penjual sendiri |
| `Seller Note` | 0/601 | 0 | kosong | tidak bisa dipakai |

`Warehouse Name` **tidak layak jadi sumber identitas toko**: satu toko bisa punya
beberapa gudang, dan dua toko berbeda bisa memberi nama gudang yang sama. Kalau
identitas toko dibaca dari kolom itu, salah nama gudang di Seller Center = pesanan
masuk ke toko yang salah, tanpa galat.

**Pilihan yang disarankan = 5c (gabungan, bukan a atau b):**
1. **Toko dipilih di wizard** (wajib) — inilah sumber kebenaran `account_id`, sama
   seperti 16 jenis impor lain (`account_scope="required"` sudah jadi aturan
   sistem, dan gate `INV-MKTSCOPE`/MKS-1 memerahkan dokumen tanpa `account_id`).
2. **Sistem MEMERIKSA, lalu memperingatkan:**
   * `Purchase Channel` (`TikTok`) ≠ platform toko yang dipilih ⇒ **tolak** (ini
     pasti salah berkas);
   * `Warehouse Name` berbeda dari yang pernah terlihat untuk toko itu ⇒
     **peringatan** di pratinjau, bukan penolakan;
   * `Warehouse Name` > 1 nilai dalam satu berkas ⇒ **peringatan** ("berkas ini
     mungkin gabungan beberapa gudang").
3. `Warehouse Name` & `Purchase Channel` tetap **disimpan per baris** sebagai jejak audit.

Dengan begitu satu berkas = satu toko (**dipilih manusia**), dan salah unggah
tertangkap **sebelum** commit.

### 5.2 Retur/batal — TIDAK perlu jenis impor terpisah

Ini temuan yang menyelesaikan pertanyaan Anda: **kolom retur & batal sudah ADA di
skema 65 kolom yang sama**, hanya kosong di ekspor "Perlu Dikirim":

| Kolom | Ada? | Terisi di ekspor A |
|---|---|---|
| `Cancelation/Return Type` | **ADA** | 0/601 |
| `Cancelled Time` | **ADA** | 0/601 |
| `Cancel By` | **ADA** | 0/601 |
| `Cancel Reason` | **ADA** | 0/601 |
| `Order Refund Amount` | **ADA** | 0/601 |
| `Sku Quantity of return` | **ADA** | 601/601 (semua bernilai 0) |
| `Shipped Time` | **ADA** | 0/601 |
| `Delivered Time` | **ADA** | 0/601 |

Artinya ekspor **"Perlu Dikirim"**, **"Dikirim/Selesai"**, dan **"Batal/Retur"**
berasal dari menu yang sama ⇒ **65 kolom identik**. Yang membedakan hanya
**kolom mana yang terisi**.

⇒ **Jawaban 5-retur = a**, dan lebih kuat dari itu: **satu peta kolom melayani ketiganya.**
Bukan 3 jenis impor dengan 3 kamus — **1 kamus kolom, 1 kamus nilai status**.

Bukti tahapan yang tersedia per pesanan (dasar layar monitoring "sudah diurus atau belum"):

| Kolom waktu | Ekspor A | Dari mana |
|---|---|---|
| `Created Time` | 601/601 | Ekspor A |
| `Paid Time` | 108/601 | Ekspor A (rendah karena 82% COD — uang belum masuk) |
| `RTS Time` | 597/601 | Ekspor A (resi sudah terbit) |
| `Shipped Time` | **0/601** | **hanya Ekspor B** |
| `Delivered Time` | **0/601** | **hanya Ekspor B** |
| `Cancelled Time` | **0/601** | hanya ekspor batal/retur |

⇒ Rencana Anda (butuh ekspor kedua sebagai bukti kirim) **benar dan tidak bisa
dihindari**: Ekspor A memang tidak memuat bukti kirim.

---

## 6. KUNCI PRODUK — `SKU ID` satu-satunya yang boleh jadi kunci

| Fakta | Angka | Akibat |
|---|---|---|
| `Seller SKU` terisi | **0/601** | pencocokan lewat SKU penjual **mustahil** |
| `SKU ID` platform terisi | 601/601, **83 unik** | satu-satunya kunci yang stabil |
| `SKU ID` dengan >1 `Product Name` | **0** | nama tidak berubah… |
| `SKU ID` dengan >1 `Variation` | **19** | …tapi **teks variasi berubah** (mis. ditambahi `(SMOOK)`) |
| `SKU ID` dengan >1 harga satuan | 0 | harga konsisten per SKU |
| Pasangan (Nama, Variasi) unik | 79 | lebih sedikit dari 83 SKU ⇒ 4 SKU akan hilang |
| **(Nama, Variasi) yang menunjuk >1 `SKU ID`** | **23** | **kalau cocokkan pakai nama, 23 pasang SKU berbeda akan DILEBUR jadi satu** |

Contoh nyata — nama & variasi identik, SKU ID berbeda (produk yang sama didaftarkan
dua kali di TikTok):
```
… POLKA BLACK, M (LD 110 CM), PAKAI …  ⇒ ['1736470663036306470', '1736486378273997862']
… POLKA WHITE, XXL (LD 130 CM), TANP…  ⇒ ['1736470663036109862', '1736486378273801254']
```

**Kesimpulan:** kamus **`platform_sku_id` → `catalog_item_id`** wajib, dan harus
**banyak-ke-satu** (beberapa SKU platform boleh menunjuk satu item katalog).
Ukuran pekerjaannya kecil: **83 SKU, 8 produk induk**.

| pcs | Omzet produk | Jml SKU | Produk induk |
|---|---|---|---|
| 409 | Rp 38.136.478 | 53 | Jennifer Blouse Polkadot |
| 73 | Rp 12.327.848 | 6 | RACHEL ONESET |
| 65 | Rp 5.081.303 | 8 | Victoria Top Blouse |
| 30 | Rp 2.647.465 | 6 | ONA DRESS |
| 13 | Rp 983.700 | 3 | BIEL TOP |
| 4 | Rp 425.516 | 3 | AISAR DRESS |
| 2 | Rp 152.508 | 2 | RASHA BLOUSE |
| 7 | Rp 28.993 | 2 | JEPIT JEDAI |

Layar pemetaan dikelompokkan per produk induk (8 kelompok) ⇒ pekerjaan sekali,
±15 menit, bukan 83 baris satu-satu.

---

## 7. NILAI TAMBAH GRATIS — sudah ada di ekspor, tidak perlu input manual

| Kolom | Terisi | Bisa langsung jadi |
|---|---|---|
| `Order Channel` | 601/601 — **LIVE 418 (70%)** · Videos 99 · Product cards 84 | omzet **live selling** otomatis (nyambung ke modul Live Selling) |
| `Creator Handle` | 515/601 — **31 kreator** (`iori.oliviara` 289 baris = 48%) | kontribusi **KOL/kreator** otomatis |
| `Province` / `Regency and City` | 601/601 — **47 provinsi, 324 kota** (TIDAK disamarkan) | sebaran penjualan per wilayah |
| `Payment Method` | 601/601 — COD 493 (82%) · Transfer 37 · QRIS 24 · PayLater 20 | risiko COD per wilayah/produk |
| `Weight(kg)` | 601/601 | analisis ongkir |

Omzet produk per channel (dihitung dari berkas ini, bukan perkiraan):

| Order Channel | Omzet produk | Porsi |
|---|---|---|
| **LIVE** | **Rp 42.364.407** | **70,9%** |
| Videos | Rp 9.590.333 | 16,0% |
| Product cards | Rp 7.829.071 | 13,1% |

Kontribusi kreator (top 5 dari 31 handle): `iori.oliviara` Rp 26.942.611 ·
`vivin.ir1994` Rp 10.936.791 · `mimayshop25` Rp 4.654.191 · `daarraaa__` Rp 3.307.274 ·
`tiaaoktvv` Rp 1.323.055. Semua ini angka yang selama ini diketik manual.

**Catatan privasi:** `Recipient` (`L***`), `Phone #` (`(+62)856***`), `Detail Address`,
`Districts`, `Villages` **sudah disamarkan platform**; `Zipcode` kosong 601/601.
Sistem ini **tidak bisa dan tidak perlu** mencetak label kirim — sejalan dengan
lingkup "input + monitoring".

---

## 8. RANCANGAN YANG DISARANKAN (untuk dibangun setelah Anda setuju)

### 8.1 Bentuk: 2 jenis impor, 1 kamus kolom, 1 kamus nilai

```
SELLER CENTER (satu menu ekspor, 65 kolom sama)
  │
  ├─ Ekspor A "Perlu Dikirim"   ──► IMPOR A  (Marketing)  → daftar kerja
  ├─ Ekspor B "Dikirim/Selesai" ──► IMPOR B  (Gudang)     → bukti kirim (+Shipped/Delivered)
  └─ Ekspor C "Batal/Retur"     ──► IMPOR B  (jenis sama) → batal/retur (+Cancel*/Refund)
                                        │
                             ┌──────────┴──────────┐
                             │  MONITORING          │
                             │  · belum dikirim > N hari
                             │  · ada di A, tak pernah muncul di B  (bocor)
                             │  · dibatalkan sesudah resi terbit
                             │  · omzet: produk vs dibayar pembeli
                             │  · LIVE vs Video vs Product card · per kreator · per wilayah
                             └──────────────────────┘
```

Impor B & C **satu jenis** (`marketplace_fulfillment`) karena kolomnya identik —
yang membedakan hanya kolom yang terisi.

### 8.2 Kunci (harus tunggal, ini yang bikin idempoten)

| Tingkat | Kunci | Alasan |
|---|---|---|
| Baris pesanan | **`(account_id, platform, order_id, platform_sku_id)`** | 1 baris = 1 SKU; 36 pesanan multi-SKU |
| Pesanan (nilai uang, ongkir, biaya) | `(account_id, platform, order_id)` — **ditulis 1×** | mencegah dobel 16,8% |
| Impor B/C → data lama | `order_id` (utama) · `Tracking ID` (cadangan, 597/601 terisi) | resi sudah ada sejak tahap "perlu dikirim" |
| Produk | `platform_sku_id` → `catalog_item_id` (**banyak-ke-satu**) | `Seller SKU` kosong 601/601 |

### 8.3 Yang harus ditambahkan ke mesin (semuanya deterministik, tanpa AI)

1. **Lewati baris deskripsi** — opsi `header_row` / `skip_rows` di `POST /upload`
   (sekarang tidak ada) **atau** deteksi otomatis: baris yang seluruh selnya berupa
   kalimat penjelas. Tanpa ini, baris ke-2 selalu masuk sebagai pesanan palsu.
2. **Kamus NILAI (bukan hanya kamus header)** — ini akar 601+596 galat:
   * status: `Perlu dikirim`, `Menunggu pengambilan`, `Menunggu pengiriman`,
     `Dikirim`, `Selesai`, `Dibatalkan`, `Pengembalian`, … → status kanonik.
     `core/order_status.EXTERNAL_STATUS_MAP` **hanya berisi istilah Inggris**
     (`shipped`, `completed`, `cancelled`, `ready_to_ship`, …); saya uji 8 istilah
     Indonesia yang benar-benar dipakai TikTok (`Perlu dikirim`, `Menunggu pengambilan`,
     `Menunggu pengiriman`, `Dikirim`, `Selesai`, `Dibatalkan`, `Pengembalian`,
     `Sedang dikirim`) → **kedelapannya mengembalikan `None`**.
   * kurir: `J&T Express` → `jnt`, `JNE Express Standard ID` → `jne`, dst.
   * Nilai yang **tidak** ada di kamus ⇒ ditolak dengan pesan jelas + tercatat di
     `errors.csv`, **jangan pernah ditebak**.
3. **Kolom uang per-pesanan vs per-baris dipisah tegas** (§4.2) — di skema, bukan di layar.
4. **Simpan mentahnya**: `platform_status`, `platform_substatus`, `Warehouse Name`,
   `Purchase Channel` untuk audit.
5. **Template tersimpan** untuk Ekspor B/C ⇒ pemetaan sekali kerja.

### 8.4 Fase kerja & bukti selesai

| Fase | Isi | Bukti selesai (terukur) |
|---|---|---|
| **1** | Jenis `marketplace_orders` (65 kolom, lewati baris deskripsi, kamus nilai status/kurir, kunci per baris SKU) + layar kamus 83 SKU → item katalog | impor berkas asli: **601 baris → 559 pesanan + 601 baris SKU, 0 ditolak**; jalankan 2× → **tidak ada tambahan**; omzet produk **Rp 59.783.811**, dibayar pembeli **Rp 62.805.113** |
| **2** | Jenis `marketplace_fulfillment` (Ekspor B & C) + layar **Monitoring Pesanan** (belum dikirim + umur hari · bocor · batal sesudah resi) | impor B menandai n pesanan `sudah_dikirim` dengan `Shipped Time`; sisa "belum diurus" tampil dengan umur hari; rollback memulihkan keadaan sebelumnya |
| **3** | Matikan jalur cacat: webhook marketplace → **410** + pesan; "Integrasi API" ditandai tidak dipakai; berkas pesanan **dilarang** masuk importer AI lama; gate baru *"pesanan tanpa toko/nomor = MERAH"* | gate hijau; percobaan kirim webhook ditolak 410 |
| **4** | Bonus dari kolom yang sudah ada: omzet **LIVE**, kontribusi **kreator**, sebaran **wilayah** | angka terisi otomatis dari impor, tanpa input manual |
| **5** *(bersyarat)* | **Potong stok** saat Impor B (pilihan **A** §3.3) | hanya boleh menyala kalau 4 prasyarat di **Rekomendasi Q2 → Langkah 2** terpenuhi; dibuktikan dengan gate |

---

## 9. YANG MASIH HARUS ANDA PUTUSKAN (3 hal, sisanya sudah jelas)

1. **Potong stok — Langkah 1 dulu (monitoring saja), atau tunggu sampai rantai FG utuh?**
   Saya sarankan **Langkah 1 dulu** (Rekomendasi Q2 §3): pesanan & bukti kirim bisa dipakai besok,
   potong stok dinyalakan setelah master FG + kamus SKU + stok FG ada.
2. **Kalau potong stok nanti nyala: COGS otomatis (A) atau tanpa jurnal (B)?**
   Saya sarankan **A** — kalau tidak, persediaan di buku tidak pernah turun.
3. **`ANTHROPIC_API_KEY` dipasang atau tidak?** Tidak dipasang pun rencana ini
   jalan 100%; yang mati hanya tombol AI opsional (§2.2).

**Dan satu permintaan:** **1 contoh Ekspor B** (dan Ekspor C kalau ada). Bukan untuk
menentukan bisa/tidak — tapi supaya **kamus nilai status ditulis dari teks asli**.
Kamus nilai inilah penyebab 601 galat di §1, dan satu-satunya bagian yang tidak
boleh saya duga.

---

## 10. RINGKASAN SATU HALAMAN

* Mesin impor **tanpa AI sudah benar dan gagal-aman**; yang belum ada adalah
  **jenis impor** untuk bentuk data ini. Dibuktikan: berkas asli lewat jenis
  `orders` = **0 dari 602 baris lolos**, omzet **Rp 0** dari Rp 62.805.113.
* **Tanpa AI cukup**, bahkan saat header berubah bahasa (uji: 10/65 → 14/65 saat
  diterjemahkan gaya Shopee). Header benar-benar asing ⇒ sistem **berhenti**, tidak menebak.
* **AI mati hari ini** (`ANTHROPIC_API_KEY` belum ada; kunci LLM platform sengaja
  diabaikan sejak 2026-07-27) — dan importer AI yang lama **akan merusak** berkas ini
  (4 kolom uang menumpuk di 1 field, agregasi per tanggal).
* **Potong stok saat bukti kirim: waktunya tepat, tapi 0 dari 603 pcs bisa dipotong
  hari ini** (0 master FG · 0 baris stok FG · 0 item katalog · tidak ada kamus SKU).
  Dipaksa ⇒ semua gagal, atau stok minus, atau (terburuk) "terkirim" tanpa stok bergerak.
* **Omzet: pakai `SKU Subtotal After Discount` (Rp 59.783.811)**, bukan `Order Amount`
  (Rp 62.805.113 — termasuk ongkir & biaya layanan). Salah cara jumlah ⇒ **+16,8%**.
* **Kunci produk = `SKU ID` platform** (`Seller SKU` kosong 601/601). Nama tidak boleh
  jadi kunci: **23 pasangan nama+variasi menunjuk SKU berbeda**. Kamus: 83 SKU, 8 produk induk.
* **Toko = dipilih di wizard**, `Warehouse Name`/`Purchase Channel` jadi **pemeriksa**.
* **Retur/batal = ekspor dari menu yang sama** — kolomnya sudah ada. **1 peta kolom
  untuk 3 ekspor**, bukan 3 jenis impor.
* **Gratis dari ekspor:** omzet LIVE (70% pesanan), 31 kreator, 47 provinsi/324 kota.

**Tidak ada kode aplikasi yang diubah dalam sesi ini.** Yang ditambahkan hanya 4 skrip
bukti read-only di `scripts/_analyze_*` & `scripts/_prove_*` (mengikuti konvensi
`_prove_catalog_master_gaps.py` yang sudah ada) dan berkas contoh di `samples/`.
