# Analisis Flow Pemesanan & Fulfillment — Portal Marketing ↔ Portal Lain
**Tanggal:** 2026-08-11 · **Metode:** telusur kode + uji endpoint NYATA + hitung data di DB.
**Tidak ada kode yang diubah oleh analisis ini.** Semua angka bisa diulang.

---

## RINGKASAN SATU HALAMAN

Rancangan alurnya **sudah benar dan lengkap** — dari pesanan pembeli sampai stok
turun dan COGS masuk buku, lewat Scan-Out gudang. Yang bermasalah bukan
rancangannya, tetapi **tiga hal**:

1. **Pintu masuk pesanan yang paling penting di operasi nyata (webhook marketplace)
   memakai jalur yang BERBEDA dan cacat** — pesanan masuk tanpa toko, tanpa tautan
   produk, tanpa reservasi stok, tanpa nomor order, dan nilai uangnya disimpan di
   field yang tidak dibaca ringkasan. Dibuktikan: begitu satu pesanan webhook masuk,
   gate `INV-MKTSCOPE` (MKS-1) langsung **MERAH**.
2. **Rantai hulu (produk jadi) belum tersambung** sehingga hari ini
   **tidak ada satu pun pesanan baru yang bisa dibuat**: 18/18 item katalog belum
   tertaut master FG ⇒ `POST /api/marketing/orders` membalas **400**.
3. **Layar menjanjikan stok yang tidak ada:** katalog menampilkan `in_stock` 60–120
   pcs padahal stok jual sebenarnya **0** (tidak ada satu baris FG di gudang).

---

## 1. TIGA JENIS "PEMESANAN" DI SISTEM INI (jangan tertukar)

| Konsep | Koleksi | Artinya | Pemilik proses |
|---|---|---|---|
| **Pesanan pembeli (online shop)** | `marketing_orders` | pembeli marketplace beli barang | Portal Marketing |
| **Order produksi** | `rahaza_orders` → work order → cutting → CMT | perintah MEMBUAT barang | Portal Produksi/Cutting |
| **Order pembelian** | `rahaza_purchase_orders` | beli kain/aksesoris ke supplier | Portal Pengadaan |

Analisis ini tentang **yang pertama**, dan bagaimana ia menyentuh dua yang lain.

---

## 2. DARI MANA DATA PESANAN MASUK — 4 PINTU, PERILAKUNYA BERBEDA

| # | Pintu masuk | Endpoint | `account_id` (toko) | Tautan katalog/FG | Reservasi stok | Nomor order | Field uang | Bisa difulfillment? |
|---|---|---|---|---|---|---|---|---|
| 1 | **Manual** (layar Order Terpadu) | `POST /api/marketing/orders` | ✅ wajib (`resolve_account`) | ✅ **wajib** — SKU tak dikenal ⇒ 400 | ✅ per baris, kurang ⇒ **409** | ✅ auto `MAN-…` | `revenue`, `total_payment` | ✅ ya |
| 2 | **Impor tanpa AI** (jenis "orders") | `data-import/…/commit` | ✅ `stamp_account` | ⚠️ dicoba via SKU; gagal ⇒ **disimpan + peringatan**, bukan ditolak | ❌ **sengaja tidak** (order lama sudah dikirim) | ✅ dari berkas | ✅ dihitung | ❌ `fulfillment_status='unallocated'` (di luar daftar status fulfillment) |
| 3 | **Webhook marketplace** | `POST /api/marketing/webhooks/{shopee\|tiktok\|tokopedia}` + `/manual` | ❌ **TIDAK ADA** | ❌ tidak ada | ❌ tidak ada | ❌ `order_id` = `null` | ❌ `total_amount` (bukan `revenue`/`total_payment`) | ❌ tidak |
| 4 | **Integrasi API marketplace** | `marketing/integrations/{platform}/test` | — | — | — | — | — | ❌ **belum ada penarik order** (kode: *"Placeholder test — pretend success … Phase 4 akan mengaktifkan real API"*) |

### Bukti pintu #3 (dijalankan hari ini, lalu dibersihkan)

```
POST /api/marketing/webhooks/manual  (payload Shopee: ordersn TELUSUR-WH-001,
                                      SKU DA-GMB-001, 2 pcs, total 196.000)
→ 200, order dibuat. Isi dokumennya:
     account_id      : TIDAK ADA
     catalog_item_id : TIDAK ADA
     order_id        : None            ← kolom pertama tabel Order Terpadu KOSONG
     revenue         : None            ← ringkasan menghitungnya Rp 0
     total_amount    : 196000          ← nilai aslinya "nyangkut" di field ini
     stok direservasi: TIDAK

Akibat yang bisa ditunjuk di layar:
  · GET /api/marketing/orders                    → muncul (61 baris)
  · GET /api/marketing/orders?account_id=<shopee> → HILANG (tidak berlingkup toko)
  · GET /api/marketing/orders/summary             → total_revenue TIDAK naik 196.000
  · python3 scripts/verify_marketing_scope.py     → MKS-1 MERAH
      "marketing_orders: 61 dokumen, 1 TANPA account_id"
```

Artinya: **pesanan yang datang otomatis dari marketplace tidak bisa dilihat per toko,
tidak masuk omzet, tidak memesan stok (risiko overselling), dan tidak bisa dikerjakan
gudang** — semuanya tanpa satu pun pesan error.

### Bukti data 60 pesanan demo yang ada sekarang

```
allocations terisi     : 0 / 60
items[] terisi         : 0 / 60
fulfillment_items      : 0 / 60
shipment_ref           : 0 / 60
tetapi fulfillment_status: dispatched 39 · packed_ready 4 · allocated 4 · picking 3
```

⇒ Status gudangnya **tidak punya isi**: 39 pesanan "sudah dikirim" tanpa satu baris
alokasi, tanpa surat jalan, tanpa mutasi stok. Data demo mengajarkan bentuk yang
salah — pelajaran yang sama seperti cacat F14 dulu (`account_id` kosong di seed).

---

## 3. FULFILLMENT — RANCANGANNYA BENAR, HARI INI MATI DI LANGKAH 0

### Alur yang dirancang (dan memang ada kodenya)

```
[MARKETING]                          [GUDANG]                        [KEUANGAN]
POST /marketing/orders
  └─ reservasi stok jual (K-8b/M10)
       └─ status 'packed' ────────>  ANTRIAN FULFILLMENT
                                     POST /fulfillment/…/allocate   (pilih baris FG
                                       dari rahaza_material_stock:
                                       ownership=cv_da,
                                       inventory_category=fg_internal)
                                     POST …/pick     → picking
                                     POST …/pack     → packed_ready
                                     POST …/dispatch → buat PENDING outbound_fg
                                                       (stok BELUM turun)
                                     ── SCAN-OUT gudang ──>
                                        stok FG turun  ───────────>  post_cogs_shipment
                                        order → 'dispatched'          Dr COGS material/
                                                                      labor/overhead
                                                                      Cr Persediaan FG
```

Pembatalan/retur pun sudah lewat SSOT `core/order_status.apply_status`
(reservasi dilepas; bulk-cancel tidak lagi membocorkan stok).

### Kondisi NYATA hari ini (diuji)

```
GET /api/fulfillment/queue               → 18 pesanan menunggu
GET /api/fulfillment/inventory/available → { "items": [], "total": 0 }   ← NOL
rahaza_material_stock                    → 12 baris: kain + aksesoris
   inventory_category='fg_internal'      → 0 baris                        ← NOL
marketing_catalog_items                  → 18 item, fg_material_id terisi: 0/18
   stock_quantity > 0                    → 18/18  (60–120 pcs, status "in_stock")

POST /api/marketing/orders  (item katalog sah, qty 1)
→ 400 "Item katalog 'DA-BBM-020' belum tertaut ke master FG —
       tautkan varian/FG-nya dulu di Katalog."
```

**Kesimpulan:** gudang punya antrian 18 pesanan tetapi **tidak ada barang yang bisa
dialokasikan**, dan **pesanan baru sama sekali tidak bisa dibuat**.

### Kenapa gudang FG kosong

Stok FG hanya lahir dari:
* `core/production_qty_ledger.post_fg_accepted` → dipanggil
  `routes/dewi_cmt_packing.py` (hasil jahit yang **lolos QC** saat packing),
  `routes/buyer_shipment.py`, `core/short_shipment.py` (jalur maklon);
* `routes/wms_receiving.py` (penerimaan barang bertipe `fg`).

Di basis data ini belum ada FG yang lolos QC (`dewi_cmt_jobs` 4 dokumen, belum ada
`qty_accepted`; `wh_receipts` 0). Lokasi `ZNA-FG` (Area Produk Jadi) **sudah ada**,
jadi yang kurang murni **transaksinya**, bukan masternya.

Layar Katalog sudah jujur: ada mode **"Ambil dari FG"**, tombol **Sinkron dari WMS**,
dan peringatan *"…alur order. Tautkan varian/FG-nya."* — jadi fiturnya ada,
**rantai hulunya** yang belum dijalankan.

### Cacat kebenaran stok di layar

`core/catalog_stock` (K-7a) menetapkan stok jual **dihitung LIVE**;
`stock_quantity` hanya **cache tampilan** + penanda `in_sync`. Tetapi untuk 18 item
demo, cache berisi angka seed (60–120) **tanpa dasar FG**, dan respons
`GET /catalogs/{id}/items` mengembalikan `sellable_qty: null`, `stock_in_sync: null`.
⇒ Layar berkata **"in_stock 120"**, kenyataannya **0 pcs bisa dijual**. Inilah yang
membuat staf/pembeli dijanjikan barang yang tidak ada.

---

## 4. HUBUNGAN KE PORTAL LAIN — YANG SUDAH ADA vs YANG BOLONG

```
                    ┌──────────────── PORTAL PRODUKSI / CUTTING / CMT ───────────────┐
                    │  rahaza_orders → work order → cutting → CMT jahit → QC        │
                    │        └─ packing (lolos QC) ──> post_fg_accepted()            │
                    └───────────────────────────┬───────────────────────────────────┘
                                                │ FG masuk ZNA-FG
                                                ▼
                    ┌──────────────── PORTAL GUDANG (WMS) ──────────────────────────┐
                    │ rahaza_material_stock (fg_internal)                            │
                    │  ├─ Fulfillment (alokasi/pick/pack/dispatch)                   │
                    │  ├─ Surat Jalan · Pick List · Scan-Out                         │
                    │  └─ Retur Fisik (wh_returns)                                   │
                    └───────┬───────────────────────────────┬───────────────────────┘
        tautan fg_material_id│                              │ scan-out
                             ▼                              ▼
   ┌──── PORTAL MARKETING ────────────────┐        ┌──── PORTAL KEUANGAN ───────────┐
   │ Katalog toko  ← stok jual (live)     │        │ COGS OTOMATIS (post_cogs_...)  │
   │ Order Terpadu → reservasi stok       │        │ PENDAPATAN: **MANUAL**         │
   │ Ulasan/Retur/Komplain ← order        │        │   (Keputusan #1; AR batch 410) │
   │ Live Selling → rincian produk (baru) │        │ Nota kredit retur: **0 dokumen**│
   └──────────────────────────────────────┘        └────────────────────────────────┘
```

### Yang SUDAH tersambung dengan benar
* Marketing → Gudang: antrian fulfillment, alokasi FG, dispatch wajib **Scan-Out**
  (stok tidak turun sebelum gudang mengonfirmasi) — pemisahan tugas yang sehat.
* Gudang → Keuangan: Scan-Out memicu **COGS** otomatis (idempoten).
* Marketing internal: ulasan/retur/komplain menempel pesanan nyata; retur bisa
  dijembatankan ke Retur Fisik gudang (`create-wh-return`, idempoten).
* Pembatalan/retur melepas reservasi stok lewat satu SSOT.

### Yang BOLONG (per portal)

| Sambungan | Kondisi | Akibat |
|---|---|---|
| **Marketplace → Marketing** (webhook) | jalur berbeda & cacat (§2) | pesanan otomatis jadi baris yatim; overselling; omzet Rp 0 |
| **Marketplace → Marketing** (API pull) | placeholder, belum ada penarik | "Integrasi API" memberi harapan palsu |
| **Produksi → Katalog toko** | 0/18 item tertaut FG | pesanan baru **mustahil** dibuat |
| **Katalog → Produksi** (permintaan produksi ulang) | **TIDAK ADA** | tidak ada sinyal "stok toko hampir habis" ke produksi; `marketing_alerts` hanya diskon kedaluwarsa, SLA komplain, peluncuran, konten — **tidak ada peringatan stok** |
| **Marketing → Keuangan** (pendapatan) | manual (jurnal), COGS otomatis | **asimetris**: biaya bisa masuk buku tanpa penjualannya ⇒ laba periode bisa timpang |
| **Retur → Keuangan** | nota kredit tidak pernah terbit (0 dokumen dari 15 retur approved/completed) | uang pembeli tidak pernah jadi kewajiban di buku |
| **Fulfillment → Aksesoris/Packing** | tidak ada konsumsi material packing (0 rujukan di `routes/fulfillment.py`) | biaya kemasan tidak pernah dibebankan ke pesanan |
| **COGS untuk barang tanpa Work Order** | `post_cogs_shipment` menjumlahkan HPP dari snapshot per `work_order_id` | FG tanpa WO ⇒ **COGS = 0** (barang keluar tanpa biaya tercatat) |

---

## 5. DAFTAR CACAT TERUKUR (urut dampak)

**P0 — uang / operasi berhenti**
1. **Webhook order tidak berlingkup toko & tidak tertaut** (§2). Bukti: MKS-1 merah,
   hilang dari filter toko, omzet tidak naik, stok tidak dipesan.
2. **Pesanan baru mustahil dibuat**: 18/18 item katalog tanpa `fg_material_id` ⇒ 400.
3. **Katalog menjanjikan stok yang tidak ada**: "in_stock 120" vs stok jual 0;
   `sellable_qty`/`stock_in_sync` tidak dikembalikan API item.
4. **Pendapatan tidak otomatis padahal COGS otomatis** ⇒ buku bisa timpang.

**P1 — layar membantah kenyataan**
5. 60 pesanan demo berstatus gudang **tanpa isi** (0 alokasi / 0 fulfillment_items /
   0 surat jalan) — termasuk 39 "dispatched".
6. `platform` masih **wajib dikirim** di `OrderCreateBody` padahal harus turunan akun
   (cacat sejenis yang baru diperbaiki di Ulasan & Retur).
7. Integrasi API marketplace masih placeholder tetapi tampil sebagai fitur.
8. Impor pesanan tidak memesan stok (benar untuk data historis) tetapi tidak ada
   penanda di layar bahwa pesanan itu **tidak akan** masuk antrian gudang.
9. Tidak ada peringatan stok katalog rendah → tidak ada pemicu produksi ulang.

---

## 6. USULAN URUTAN PERBAIKAN (belum dikerjakan — menunggu keputusan)

| Fase | Isi | Kenapa didahulukan |
|---|---|---|
| **1** | **Satukan jalur webhook ke SSOT pesanan manual**: kenali toko dari akun marketplace, tautkan SKU → item katalog → FG, reservasi stok, beri `order_id`, tulis `revenue`/`total_payment`. Tambah gate: pesanan tanpa `account_id`/nomor = MERAH. | Ini pintu pesanan NYATA. Selama cacat, setiap pesanan otomatis merusak laporan & stok. |
| **2** | **Kebenaran stok di layar**: kembalikan `sellable_qty` + `stock_in_sync` pada API item katalog; tampilkan "stok jual 0 — belum tertaut FG" alih-alih "in_stock 120". | Menghentikan janji palsu ke pembeli. |
| **3** | **Seed demo yang koheren**: buat FG lolos QC untuk item katalog demo (`post_fg_accepted`) ⇒ katalog tertaut ⇒ pesanan bisa dibuat ⇒ fulfillment bisa diuji end-to-end sampai COGS. | Membuat alurnya bisa DICOBA, dan demo mengajarkan bentuk yang benar. |
| **4** | Keputusan bisnis: pendapatan (jurnal manual vs AR otomatis) · **nota kredit retur** · biaya kemasan · COGS untuk FG tanpa WO. | Butuh keputusan owner, bukan kode. |
| **5** | Sinyal permintaan: peringatan stok katalog rendah → usulan order produksi. | Menutup lingkaran toko ↔ produksi. |

---

## 7. CARA MENGULANG BUKTI

```bash
# 1. stok FG & tautan katalog
python3 - <<'PY'
from pymongo import MongoClient
db=MongoClient('mongodb://localhost:27017')['test_database']
print('FG rows :', db.rahaza_material_stock.count_documents({'inventory_category':'fg_internal'}))
print('item katalog tertaut FG:', db.marketing_catalog_items.count_documents({'fg_material_id':{'$nin':[None,'']}}), '/', db.marketing_catalog_items.count_documents({}))
PY

# 2. pesanan baru ditolak
curl -s -X POST localhost:8001/api/marketing/orders -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"account_id":"<acc>","platform":"shopee","catalog_item_id":"<item>","quantity":1,"price_final":98000}'
# → 400 "belum tertaut ke master FG"

# 3. antrian gudang vs stok yang bisa dialokasikan
curl -s -H "Authorization: Bearer $TOKEN" localhost:8001/api/fulfillment/queue              | head -c 200
curl -s -H "Authorization: Bearer $TOKEN" localhost:8001/api/fulfillment/inventory/available

# 4. webhook membuat baris yatim (JANGAN lupa hapus sesudahnya)
curl -s -X POST localhost:8001/api/marketing/webhooks/manual -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"platform":"shopee","event_type":"order_status_push","payload":{"data":{"ordersn":"UJI-1","buyer_username":"x","status":"READY_TO_SHIP","total_amount":196000,"item_list":[{"item_sku":"DA-GMB-001","model_quantity_purchased":2,"model_discounted_price":98000}]}}}'
python3 backend/../scripts/verify_marketing_scope.py   # → MKS-1 MERAH
```
