# Analisis Siklus TARGET · OMZET · ANGGARAN — Kondisi Sekarang (AS-IS) vs Rencana (TO-BE)

**Tanggal:** 2026-08-11 · **Sesi:** analisis & verifikasi saja — **TIDAK ADA KODE APLIKASI YANG DIUBAH**
**Cara kerja:** menjalankan fungsi produksi yang sebenarnya + memanggil endpoint yang hidup +
memindai kode, **bukan** membaca dokumen lama.

**Cara mengulangi bukti:**
```bash
cd /app/backend && python3 /app/scripts/_prove_sales_cycle.py      # siklus target/omzet/anggaran
cd /app/backend && python3 /app/scripts/_prove_import_decisions.py # keputusan impor (sesi sebelumnya)
cd /app && python3 scripts/_analyze_seller_center_money_keys.py    # angka uang di ekspor
```

---

## 1. JAWABAN SINGKAT

| | **TARGET** | **OMZET** | **ANGGARAN** |
|---|---|---|---|
| Satuan waktu | **BULANAN** (`year`+`month`) | **HARIAN** (per akun per tanggal) | **BULANAN** (`period=YYYY-MM`) |
| Satuan objek | per **toko** + per **kreator** | per **toko** (rekap) *dan* per **pesanan** (2 dunia terpisah) | per **toko** × **5 kategori** (ads·kol·livehost·sample·diskon) |
| Diisi bagaimana | **diketik manual**, upsert | **4 pintu berbeda** menulis ke koleksi yang sama | rencana diketik manual · realisasi 3 manual + 2 otomatis |
| Koleksi | `marketing_account_targets`, `marketing_creator_targets` | `marketing_sales_data` (rekap) · `marketing_orders` (pesanan) | `marketing_budgets`, `marketing_spend_entries` |
| Realisasi dibaca dari | **hanya** `marketing_sales_data` (`revenue_type='total'`) | — | ROI dibaca dari `marketing_sales_data` |
| Terhubung ke yang lain? | **TIDAK** ke anggaran, **TIDAK** ke pesanan | rekap ⇄ pesanan **tidak pernah dibandingkan** | **PULAU** — hanya 1 berkas kode yang menyentuhnya; **tidak pernah masuk buku keuangan** |
| Kewenangan | siapa pun yang login | siapa pun yang login | siapa pun yang login |
| Kunci periode | **tidak ada** | **tidak ada** | **tidak ada** |
| Peringatan otomatis | **tidak ada** ("target ketinggalan" tidak pernah diberitahukan) | ada laporan kepatuhan input harian | **tidak ada** ("anggaran kelewat" tidak pernah diberitahukan) |

**Inti masalahnya satu kalimat:** ketiganya **ada dan lengkap di layar**, tetapi **tidak
tersambung menjadi satu siklus** — target tidak tahu anggaran, anggaran tidak tahu target,
dan omzet punya **dua dunia** (rekap harian vs pesanan) yang tidak pernah didamaikan.

---

## 2. AS-IS — SIKLUS YANG BERJALAN SEKARANG

### 2.1 Peta besar (yang benar-benar ada di kode)

```
┌──────────── TARGET (bulanan, diketik) ────────────┐
│ marketing_account_targets  ← AccountTargetsModule │
│   revenue_target · orders_target · health_target  │
│ marketing_creator_targets  ← KOLCreatorModule     │
│   revenue · sessions · viewers                    │
└──────────────────┬────────────────────────────────┘
                   │ dibandingkan dengan…
                   ▼
┌──────────── OMZET — DUNIA 1: REKAP HARIAN ─────────────────────────────┐
│ marketing_sales_data  (kunci: akun + tanggal + revenue_type)           │
│  ditulis oleh 4 PINTU:                                                 │
│   1. ketik manual        POST /api/marketing/sales-data                │
│   2. importer AI lama    routes/marketing_import.py (agregasi by_date) │
│   3. sinkron LIVE        marketing_live_sales_sync (revenue_type=live) │
│   4. aksi tugas          marketing_tasks.py:424  (submit_form)         │
│   5. wizard TANPA AI     jenis 'sales_daily'  ← BENTUK DOKUMEN BEDA (D1)│
│  dibaca oleh: Target · Dashboard · Laporan Harian/Bulanan ·            │
│               ROI Anggaran · Health Score                              │
└────────────────────────────────────────────────────────────────────────┘
        ╳  tidak pernah dibandingkan / didamaikan  ╳
┌──────────── OMZET — DUNIA 2: PER PESANAN ──────────────────────────────┐
│ marketing_orders                                                       │
│  ditulis oleh: order manual · impor jenis 'orders' · webhook (cacat)   │
│  dibaca oleh : Sales Performance (Σ total_payment) · Fulfillment ·     │
│                Retur · Ulasan · laporan eksekutif                     │
│  TIDAK dibaca oleh: Target · Dashboard Marketing · ROI Anggaran        │
└────────────────────────────────────────────────────────────────────────┘

┌──────────── ANGGARAN (bulanan, 5 kategori) ────────────────────────────┐
│ RENCANA  marketing_budgets       ← BudgetAllocationTab (ketik)         │
│ REALISASI:                                                             │
│   ads      → KETIK MANUAL  (marketing_spend_entries)                   │
│   sample   → KETIK MANUAL                                              │
│   diskon   → KETIK MANUAL                                              │
│   livehost → OTOMATIS  Σ total_pay shift 'calculated'                  │
│   kol      → DIHITUNG  fixed_fee + %komisi × revenue sesi kreator      │
│ ROI = (sales − spend) / spend × 100      ← 'sales' dari DUNIA 1        │
│ TIDAK menyentuh: target · pesanan · jurnal keuangan · anggaran perusahaan│
└────────────────────────────────────────────────────────────────────────┘
```

### 2.2 Irama waktu & layar (siapa melakukan apa, kapan)

| Kapan | Pekerjaan | Layar | Endpoint | Sifat |
|---|---|---|---|---|
| **Harian** | Isi rekap omzet per toko (total & live) | `SalesDataEntryModule` | `POST /api/marketing/sales-data` | **manual**, 1 baris/toko/hari/jenis |
| Harian | Cek toko mana yang **belum** setor angka | `DailyReportModule` | `GET /api/marketing/reports/daily` | otomatis (kepatuhan input) |
| Harian (otomatis) | Rekap LIVE dihitung ulang dari shift host & sesi kreator | — | `sync_live_sales_to_marketing()` | **otomatis, idempoten** — dipicu saat shift/sesi disimpan |
| Kapan saja | Catat belanja iklan/sample/diskon | `BudgetAllocationTab` | `POST /api/marketing/budget/spend` | **manual** |
| **Bulanan (awal)** | Tetapkan target per toko & per kreator | `AccountTargetsModule`, `KOLCreatorModule` | `POST /api/marketing/targets` | **manual**, upsert |
| Bulanan (awal) | Tetapkan anggaran 5 kategori per toko | `BudgetAllocationTab` | `PUT /api/marketing/budget` | **manual**, upsert |
| Bulanan (akhir) | Target vs aktual | `AccountTargetsModule` / `MonthlyReportModule` | `GET /api/marketing/targets/monthly-summary` | otomatis dari DUNIA 1 |
| Bulanan (akhir) | Anggaran vs belanja + ROI | `BudgetAllocationTab` | `GET /api/marketing/budget/summary` | otomatis |
| — | Omzet per pesanan / per produk | `SalesPerformanceDashboard` | `GET /api/marketing/performance/overview` | otomatis dari DUNIA 2 |

**Bukti endpoint hidup** (dipanggil dengan token admin, data sekarang masih kosong):

```
GET /api/marketing/targets/monthly-summary?year=2026&month=8  → 200  rev_target 0 · rev_actual 0 · 3 toko
GET /api/marketing/budget/summary?account_id=…&period=2026-08  → 200  5 kategori, semua 0, roi_pct 0
GET /api/marketing/dashboard/overview                          → 200  total_revenue 0 · total_revenue_live 0
GET /api/marketing/performance/overview                        → 200  total_revenue 0 · total_orders 0
```

Keadaan data: **3 toko** terdaftar; `marketing_sales_data` **0** · `marketing_orders` **0** ·
target **0** · anggaran **0** · belanja **0** · sesi kreator **0** · shift host **0**.
⇒ Siklus ini **belum pernah dijalankan dengan data nyata**; semua temuan di bawah berasal
dari **kode**, bukan dari tebakan atas data.

---

## 3. CACAT TERUKUR PADA SIKLUS AS-IS

### D1 — 🔴 Omzet yang DIIMPOR tidak terhitung di target, dan **merobohkan dashboard**

Wizard impor tanpa-AI punya jenis **`sales_daily` → `marketing_sales_data`** (aktif, muncul
di daftar 16 jenis). Tetapi `_finish()` untuk `sales_daily`
(`routes/marketing_data_import.py:616-618`) hanya menghitung AOV — ia **tidak membungkus
nilai ke `metrics{}`**. Kata `metrics` **tidak ada sama sekali** di berkas itu.

Saya jalankan jalur impor sebenarnya untuk 1 baris Rp 12.500.000, lalu menerapkan
**ekspresi pembacaan yang persis dipakai tiap layar**:

| Layar (baris kode) | Dari **IMPOR** | Dari **INPUT MANUAL** |
|---|---|---|
| Target vs Aktual (`marketing_targets.py:153`, `reports.py:190/330`) | **Rp 0** | Rp 12.500.000 |
| Dashboard Marketing (`marketing_dashboard.py:62` — `sale["metrics"]`, indeks langsung) | **`KeyError 'metrics'` ⇒ HTTP 500** | Rp 12.500.000 |
| ROI Anggaran (`marketing_budget.py:_sales_revenue`, punya fallback) | Rp 12.500.000 | Rp 12.500.000 |
| Health Score (`marketing_shared.py`) | **0** | Rp 12.500.000 |

Dokumen hasil impor: `['aov','date','orders','rating','revenue','revenue_type']` — **tanpa `metrics`**.
Dokumen hasil manual: `[... 'metrics' ...]`.

**Dan skor kesehatan toko ikut roboh.** Rumus `_recalculate_health_score`
(`marketing_shared.py:175-232`) mengambil `metrics.revenue`, `metrics.orders`,
`metrics.conversion_rate`, `fulfillment{}`, `customer_satisfaction{}`, `live_metrics{}` —
**semua kelompok itu tidak ada** pada dokumen hasil impor. Saya hitung dengan rumus yang
sama untuk 8 hari data:

| 8 hari data | Health Score | Rincian |
|---|---|---|
| dari **IMPOR** | **15 / 100** | sales 0 · fulfillment 0 · satisfaction 0 · engagement 5 · compliance 10 |
| dari **INPUT MANUAL** | **89 / 100** | sales 25 · fulfillment 24,6 · satisfaction 23,9 · engagement 5 · compliance 10 |

Toko yang sama, angka yang sama besarnya — **skor 15 vs 89**, semata karena bentuk
dokumennya. Skor ini juga dipakai sebagai salah satu target bulanan
(`health_score_target`), jadi cacat ini merusak **tiga** angka target sekaligus:
omzet, jumlah order, dan kesehatan akun.

⇒ **Satu angka, tiga hasil berbeda, satu layar mati, satu skor roboh.** Semuanya bisa
terjadi hari ini, lewat tombol yang sudah ada di UI (jenis `sales_daily` aktif di daftar
16 jenis impor).

### D2 — 🔴 Omzet punya DUA dunia yang tidak pernah didamaikan
`marketing_sales_data` (rekap) dan `marketing_orders` (pesanan) **tidak ada satu layar pun**
yang membandingkannya. Target & Dashboard hanya melihat rekap; Sales Performance hanya
melihat pesanan. Kalau keduanya terisi dengan cara berbeda, dua layar akan menunjukkan
omzet berbeda untuk bulan yang sama — **dan tidak ada yang menyalakan lampu merah**.

### D3 — 🟠 Sales Performance menjumlah `total_payment` **per baris** dan memfilter dengan **nama toko**
`marketing_sales_performance_routes.py:82-88`:
```python
{"$group": {"_id": None, "total_revenue": {"$sum": "$total_payment"}, ...}}
match_stage["account_name"] = acc["account_name"]      # teks, bukan account_id
```
Dua akibat:
1. `total_payment` adalah **"yang dibayar pembeli"** (harga×qty + ongkir − diskon). Pada
   ekspor TikTok nilai itu **diulang di setiap baris SKU** ⇒ menjumlahkan per baris
   menggandakan 36 pesanan multi-SKU: **+16,8% = Rp 10.572.124** pada berkas nyata Anda.
2. Filter memakai **teks nama toko**. Ganti nama toko di master ⇒ seluruh riwayat lama
   berhenti terhitung, **tanpa galat apa pun**.

### D4 — 🔴 TARGET dan ANGGARAN tidak saling mengenal (8 pemeriksaan, 8× TIDAK)

| Pertanyaan | Jawaban |
|---|---|
| Layar Anggaran membaca target? | **TIDAK** |
| Layar Target membaca anggaran? | **TIDAK** |
| Pencapaian target membaca pesanan? | **TIDAK** |
| ROI anggaran membaca pesanan? | **TIDAK** |
| Belanja marketing masuk jurnal keuangan? | **TIDAK** |
| Anggaran marketing dibanding anggaran perusahaan (`rahaza_budgets`)? | **TIDAK** |
| Kategori `diskon` diambil dari modul Diskon? | **TIDAK** |
| Kategori `ads` diambil dari modul Ads (`marketing_ads_data.spend`)? | **TIDAK** |

Akibat praktis: tidak ada satu layar pun yang bisa menjawab
**"target Rp X, anggaran Rp Y, sudah terpakai Rp Z, omzet baru Rp W"** — angkanya harus
disalin manual dari 3 layar berbeda.

### D5 — 🔴 Anggaran & belanja marketing adalah **PULAU**
`marketing_budgets` dan `marketing_spend_entries` **hanya disentuh oleh 1 berkas kode**
(`routes/marketing_budget.py`). Tidak ada modul keuangan yang membacanya.
⇒ Belanja iklan/sample/diskon **tidak pernah menjadi biaya di buku**. Sama untuk
`marketing_creator_targets` (pulau juga).

### D6 — 🟠 Angka "ROI" bukan profitabilitas
`roi_pct = (sales − spend) / spend × 100` dengan `sales` = **omzet**, bukan laba kotor.
**HPP/COGS tidak pernah ikut.** Untuk toko yang diskonnya besar, angka ini bisa terlihat
sangat sehat padahal marjinnya tipis. Nama "ROI" di layar menjanjikan lebih dari yang dihitung.

### D7 — 🔴 Biaya marketing TERBESAR justru tidak ada di modul Anggaran
Dari berkas nyata Anda (aritmetikanya **tutup sempurna, selisih Rp 0**):

```
SKU Subtotal Before Discount (harga coret)      Rp 109.179.000
 − SKU Seller Discount   (DITANGGUNG PENJUAL)   Rp  48.020.983   ← 44,0% dari harga coret
 − SKU Platform Discount (ditanggung platform)  Rp   1.374.206
 = SKU Subtotal After Discount (omzet produk)   Rp  59.783.811
```

**Diskon yang Anda tanggung sendiri = Rp 48.020.983 dalam 2 minggu = 80,3% dari omzet bersih
produk.** Di modul Anggaran, kategori `diskon` **kosong dan harus diketik manual** — jadi
pengeluaran promosi terbesar Anda adalah satu-satunya yang tidak pernah tercatat otomatis,
padahal **angkanya sudah ada di ekspor Seller Center**.

### D8 — 🟠 Tidak ada peringatan "target ketinggalan" / "anggaran kelewat"
`routes/marketing_alerts.py` hanya punya **4** jenis: `expiring_discount`, `sla_breach`,
`upcoming_launch`, `content_today`. Penjadwal (`APScheduler`) hanya menjalankan
`scan_overdue_invoices` (08:00) dan `retry_queued_imports` (5 menit).
⇒ Target dan anggaran hanya diketahui **kalau ada orang membuka layarnya**.

### D9 — 🟠 Tanpa kewenangan & tanpa kunci periode
Target, anggaran, dan omzet harian: **`require_auth` saja** — tidak ada pemeriksaan peran.
Tidak ada `locked`/`closed`/`period_close` di ketiga berkas.
⇒ **Siapa pun yang bisa login dapat mengubah target atau anggaran bulan yang sudah lewat**,
dan nilai lamanya **tertimpa tanpa jejak** (hanya `updated_by`/`updated_at` yang tersisa).

### D10 — 🟠 Kontribusi kreator hanya dari input manual
Pencapaian target kreator dihitung dari `marketing_creator_sessions` (**diketik** per sesi:
revenue, viewers, orders). Padahal ekspor Seller Center sudah memuat `Creator Handle`
(**515/601 baris, 31 kreator**) dengan omzet per pesanan — data yang lebih tepercaya dan
gratis, tapi tidak dipakai oleh siklus target kreator.

### D11 — 🟠 Empat–lima pintu menulis satu koleksi omzet
`marketing_sales_data` ditulis oleh: input manual · importer AI lama · sinkron LIVE ·
**aksi tugas** (`marketing_tasks.py:424`) · wizard tanpa-AI. Kunci uniknya
(akun, tanggal, revenue_type) dijaga dengan **pemeriksaan duplikat manual di tiap pintu**
(HTTP 400/409), bukan indeks unik. Satu pintu baru yang lupa memeriksa ⇒ omzet dobel.

### D12 — 🟠 Potongan platform tidak ada di ekspor pesanan
Ekspor 65 kolom **tidak memuat komisi platform / biaya affiliate** (hanya biaya yang
dibayar **pembeli**: ongkir, `Buyer Service Fee`, `Handling Fee`). ⇒ "omzet bersih yang
benar-benar cair" **tidak bisa** dihitung dari ekspor ini; itu ada di laporan
**settlement/penghasilan** platform. Setiap laporan omzet dari impor harus diberi label
**"sebelum potongan platform"**, kalau tidak Anda akan mengira uangnya lebih besar.

---

## 4. TO-BE — SIKLUS SETELAH PROPOSAL IMPOR DIJALANKAN

### 4.1 Satu prinsip yang menyelesaikan sebagian besar cacat di atas

> **Pesanan hasil impor menjadi SATU-SATUNYA sumber omzet. Rekap harian tidak lagi
> diketik — ia DITURUNKAN dari pesanan, dihitung ulang (bukan ditambah), dan idempoten.**

Polanya **sudah terbukti ada di kode ini**: `marketing_live_sales_sync.py` melakukan
persis itu untuk omzet LIVE (recompute per (akun, tanggal), lalu `upsert`, aman dipanggil
berulang). Yang perlu dilakukan adalah **memakai pola yang sama** untuk turunan dari
pesanan — bukan menciptakan mekanisme baru.

Dengan itu: Target, Dashboard, Health Score, Laporan Harian/Bulanan, dan ROI Anggaran
**semuanya ikut benar tanpa diubah satu per satu**, karena semuanya sudah membaca
`marketing_sales_data`. Yang wajib dibereskan hanya **bentuk dokumennya** (D1: harus
`metrics{}`).

### 4.2 Peta TO-BE

```
EKSPOR A "Perlu Dikirim"  ─┐
EKSPOR B "Dikirim/Selesai" ─┼─► IMPOR (wizard tanpa AI, idempoten, rollback)
EKSPOR C "Batal/Retur"    ─┘         │
                                     ▼
                         marketing_orders  (1 baris = 1 SKU dalam 1 pesanan)
                         kunci: akun + platform + order_id + platform_sku_id
                                     │
        ┌────────────────────────────┼─────────────────────────────┬────────────────────┐
        ▼                            ▼                             ▼                    ▼
  TURUNAN OMZET               MONITORING KERJA              TURUNAN ANGGARAN      TURUNAN ATRIBUSI
  (recompute, idempoten)      (nilai tambah baru)           (realisasi otomatis)  (otomatis)
  marketing_sales_data        · belum dikirim > N hari       · diskon penjual      · omzet LIVE
   revenue_type='total'       · ada di A tak muncul di B       Rp 48.020.983       · kontribusi
   metrics{revenue,orders,…}  · batal sesudah resi terbit      (kategori 'diskon')   kreator (31)
        │                                                    · (ads tetap manual /  · sebaran wilayah
        ▼                                                       dari modul Ads)       (47 prov/324 kota)
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │ TARGET vs AKTUAL (harian berjalan, bukan hanya akhir bulan)                 │
  │ ANGGARAN vs BELANJA + marjin (bukan hanya omzet)                            │
  │ SATU layar: target · anggaran · terpakai · omzet · sisa hari                │
  └─────────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Angka mana dipakai untuk apa (dari kolom ekspor yang nyata)

| Kebutuhan | Kolom ekspor | Aturan penjumlahan | Nilai pada berkas Anda |
|---|---|---|---|
| **Omzet** (target & ROI) | `SKU Subtotal After Discount` | **per BARIS** | **Rp 59.783.811** |
| Jumlah pesanan (target `orders`) | `Order ID` | **distinct**, bukan jumlah baris | **559** (bukan 601) |
| Jumlah pcs | `Quantity` | per baris | 603 |
| "Dibayar pembeli" (label terpisah) | `Order Amount` | **1× per Order ID** | Rp 62.805.113 |
| **Realisasi anggaran `diskon`** | `SKU Seller Discount` | per BARIS | **Rp 48.020.983** |
| Ongkir dibayar pembeli | `Shipping Fee After Discount` | 1× per Order ID | Rp 1.744.000 |
| Omzet LIVE | `Order Channel = LIVE` × omzet | per baris | Rp 42.364.407 (70,9%) |
| Kontribusi kreator | `Creator Handle` × omzet | per baris | 31 kreator; top `iori.oliviara` Rp 26.942.611 |
| Sebaran wilayah | `Province`, `Regency and City` | per baris | 47 provinsi · 324 kota |
| **TIDAK ADA di ekspor** | komisi platform / biaya affiliate | — | harus dari laporan settlement |

**Pagar wajib (kalau dilanggar, laporan salah):**
* `Order Amount`, ongkir, `Buyer Service Fee`, `Handling Fee` → **1× per Order ID**
  (dijumlah per baris ⇒ **+16,8%**)
* `SKU Subtotal After Discount`, `SKU Seller Discount`, `Quantity` → **per baris**
  (diambil 1× per pesanan ⇒ **−6,9%**)

### 4.4 Tiga tabrakan yang harus diputuskan SEBELUM dibangun

**T1 — Siapa pemilik omzet LIVE?**
`sync_live_sales_to_marketing()` sudah **menghitung ulang** `(akun, tanggal, revenue_type='live')`
dari shift host + sesi kreator, lalu `upsert`. Kalau impor **juga** menulis kunci yang sama
dari `Order Channel=LIVE`, keduanya akan **saling menimpa** — yang terakhir jalan menang, dan
angkanya berubah-ubah tanpa sebab yang terlihat. Harus dipilih satu:
* **(a)** impor jadi pemilik `revenue_type='live'` (angka platform = kebenaran), sinkron
  host/kreator berhenti menulisnya dan hanya dipakai untuk **biaya** (livehost/kol) — **saya sarankan ini**;
* **(b)** tetap dari shift/sesi (yang dilaporkan tim), impor menulis ke **jenis ketiga**
  (`revenue_type='live_platform'`) supaya bisa dibandingkan, bukan bertabrakan.

**T2 — Kontribusi kreator: dari ekspor atau dari sesi yang diketik?**
Target kreator sekarang membaca `marketing_creator_sessions` (diketik). Ekspor memberi
atribusi per pesanan (515/601 baris). Kalau keduanya hidup, ada dua versi kontribusi kreator
— dan **biaya komisi KOL dihitung dari salah satunya** (`_creator_cost` × revenue sesi), jadi
memilih yang salah berarti **membayar komisi dari angka yang salah**.

**T3 — Omzet: sebelum atau sesudah potongan platform?**
Ekspor tidak memuat komisi platform (D12). Pilihan:
* **(a)** semua laporan omzet diberi label **"sebelum potongan platform"** (paling cepat, jujur);
* **(b)** tambah jenis impor ke-4 untuk laporan **settlement**, sehingga ada "omzet kotor"
  dan "uang cair" berdampingan.

### 4.5 Irama TO-BE (yang berubah, yang tetap)

| Kapan | AS-IS | TO-BE |
|---|---|---|
| Harian | staf **mengetik** rekap omzet per toko | **impor 1 berkas** ⇒ rekap terbentuk sendiri (recompute) |
| Harian | — | **monitoring**: pesanan belum diurus + umur hari |
| Harian/mingguan | — | **impor Ekspor B** ⇒ bukti kirim + "bocor" (ada di A, tak pernah di B) |
| Bulanan (awal) | target diketik · anggaran diketik | **tetap diketik** (ini memang keputusan manusia) — tapi disarankan **satu layar** target+anggaran, dan **dikunci** setelah disetujui |
| Bulanan (jalan) | tidak ada yang tahu posisi | **target vs aktual harian berjalan** + peringatan "ketinggalan/kelewat" |
| Bulanan (akhir) | angka disalin dari 3 layar | satu layar: target · anggaran · terpakai · omzet · marjin |
| Anggaran `diskon` | diketik manual | **otomatis dari ekspor** (Rp 48.020.983 pada berkas Anda) |
| Anggaran `ads` | diketik manual | **dari modul Ads** (`marketing_ads_data.spend`, sudah bisa diimpor) — cukup disambungkan |
| Anggaran `livehost`/`kol` | sudah otomatis | tetap otomatis |
| Anggaran `sample` | diketik manual | tetap manual (memang tidak ada di ekspor) |
| Pembukuan | belanja marketing tidak masuk buku | **keputusan Anda** — sesuai Keputusan #4 (tanpa jurnal otomatis), tetap di luar buku; kalau kelak diinginkan, ini yang disambungkan |

### 4.6 Apa yang TIDAK berubah (supaya harapannya benar)
* **Target tetap diketik manusia.** Tidak ada gunanya menebak target dari data.
* **Anggaran rencana tetap diketik manusia.** Yang otomatis adalah **realisasinya**.
* **Biaya `sample` tetap manual** — tidak ada di ekspor mana pun.
* **Komisi platform tetap tidak diketahui** sampai laporan settlement diimpor (T3).
* **Pembukuan tetap manual** sesuai keputusan Anda; siklus ini adalah laporan **marketing**,
  bukan laporan keuangan — dan layarnya harus mengatakan itu.

---

## 5. YANG PERLU ANDA PUTUSKAN

1. **T1 — pemilik omzet LIVE**: impor (saran) atau shift/sesi?
2. **T2 — kontribusi kreator**: dari ekspor (saran) atau dari sesi yang diketik? (ini juga
   menentukan dasar hitung **komisi KOL**)
3. **T3 — omzet sebelum/sesudah potongan platform**: label saja (saran) atau tambah impor settlement?
4. **Kunci periode**: setelah bulan ditutup, target/anggaran/omzet **dikunci**? Siapa yang
   boleh membukanya kembali? (sekarang siapa pun bisa mengubah bulan lalu tanpa jejak)
5. **Kewenangan**: siapa boleh **menetapkan** target & anggaran (mis. hanya
   superadmin/manajer), dan siapa hanya boleh **melihat**?
6. **Ambang peringatan**: "target ketinggalan" pada berapa persen? "anggaran kelewat" pada
   berapa persen? (mis. peringatan di 80%, merah di 100%)

---

## 6. FASE KERJA YANG DISARANKAN (bila disetujui)

| Fase | Isi | Bukti selesai (terukur) |
|---|---|---|
| **0** | **Perbaiki D1** — `sales_daily` menulis `metrics{}` + `fulfillment{}` + `customer_satisfaction{}` + `live_metrics{}` (bentuk yang sama dengan input manual) + migrasi dokumen lama | impor 1 baris Rp 12.500.000 ⇒ Target **Rp 12.500.000** · Dashboard **200 (bukan 500)** · ROI **Rp 12.500.000** · Health **89 (bukan 15)**. Gate baru: dokumen `marketing_sales_data` tanpa `metrics` = **MERAH** |
| **1** | Jenis impor `marketplace_orders` (65 kolom, kamus nilai status/kurir, kunci per baris SKU, lewati baris deskripsi) + kamus 83 SKU platform | 601 baris ⇒ 559 pesanan, 0 ditolak; jalankan 2× tidak menggandakan; omzet produk **Rp 59.783.811** |
| **2** | **Turunan rekap harian dari pesanan** (recompute + upsert, pola `marketing_live_sales_sync`) | rekap harian terbentuk tanpa diketik; Target/Dashboard/ROI menunjukkan **angka yang sama**; hapus 1 pesanan ⇒ rekap ikut turun (idempoten) |
| **3** | Jenis `marketplace_fulfillment` (Ekspor B & C) + layar Monitoring Pesanan | pesanan tertandai `sudah_dikirim` dari `Shipped Time`; daftar "bocor" muncul |
| **4** | **Satu layar siklus**: target · anggaran · terpakai · omzet · marjin · sisa hari + peringatan ketinggalan/kelewat | satu permintaan API mengembalikan kelima angka untuk (toko, bulan); peringatan muncul di ambang yang Anda tetapkan |
| **5** | Realisasi anggaran otomatis: `diskon` dari `SKU Seller Discount`, `ads` dari `marketing_ads_data.spend` | kategori `diskon` terisi **Rp 48.020.983** tanpa diketik; `ads` terisi dari modul Ads |
| **6** | Kunci periode + kewenangan (RBAC) + jejak perubahan target/anggaran | bulan tertutup menolak perubahan (403) kecuali peran yang berwenang; setiap perubahan punya riwayat nilai lama |
| **7** *(bersyarat)* | Marjin sebenarnya (ROI pakai laba kotor) | butuh HPP di master FG — bergantung pada rantai FG di analisis sebelumnya |

Fase **0** sengaja ditaruh paling depan: ia **satu perbaikan kecil** yang membuat lima layar
sekaligus jujur, dan tanpa itu Fase 2 akan menuang data ke bentuk yang salah.

---

## 7. RINGKASAN SATU HALAMAN

* **Target** = bulanan, per toko & per kreator, **diketik**, realisasinya **hanya** dari
  rekap harian `marketing_sales_data (revenue_type='total')`.
* **Omzet** = punya **DUA DUNIA**: rekap harian (5 pintu penulis) dan per pesanan
  (`marketing_orders`). **Tidak ada layar yang mendamaikannya.**
* **Anggaran** = bulanan, 5 kategori; `livehost` & `kol` otomatis, `ads`/`sample`/`diskon`
  **diketik**; ROI memakai **omzet** (bukan laba); dan seluruh anggaran+belanja adalah
  **pulau** yang tidak pernah masuk buku maupun dibanding anggaran perusahaan.
* **Cacat paling berbahaya (D1):** omzet yang **diimpor** membuat pencapaian target
  **Rp 0**, Health Score **15/100 (bukan 89/100)**, dan Dashboard Marketing **HTTP 500** —
  sementara ROI anggaran justru benar. Satu angka, tiga hasil. Penyebabnya satu blok kode
  yang tidak membungkus nilai ke `metrics{}`.
* **Biaya marketing terbesar Anda tidak ada di modul Anggaran:** diskon yang ditanggung
  penjual **Rp 48.020.983 / 2 minggu = 44,0% dari harga coret = 80,3% dari omzet bersih**
  — padahal angkanya **sudah ada** di ekspor Seller Center.
* **TO-BE:** pesanan hasil impor jadi **satu sumber omzet**; rekap harian **diturunkan**
  (recompute, idempoten — pola yang sudah terbukti di `marketing_live_sales_sync`); target
  jadi **berjalan harian**; realisasi `diskon` & `ads` jadi otomatis; target & anggaran
  **tetap diketik** manusia tapi **dikunci** setelah disetujui.
* **Tidak ada kode aplikasi yang diubah.** Tambahan sesi ini hanya
  `scripts/_prove_sales_cycle.py` (read-only) dan dokumen ini.
