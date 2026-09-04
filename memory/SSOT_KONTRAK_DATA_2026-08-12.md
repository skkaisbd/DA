# SSOT — KONTRAK DATA MARKETING & KATALOG (wajib dipatuhi semua agent)

**Fungsi dokumen:** menghentikan kelas cacat yang paling sering terjadi di repo ini —
*"koleksi yang salah, field yang salah, fitur berdiri sendiri"*. Setiap fase di
`RENCANA_EKSEKUSI_MASTER_2026-08-12.md` **wajib** memakai nama koleksi & field dari sini.
Menambah field/koleksi **tanpa memperbarui dokumen ini = pelanggaran** (gate merah).

---

## 0. SEMBILAN ATURAN YANG TIDAK BISA DINEGOSIASI

1. **Satu koleksi = satu konsep.** Dilarang membuat koleksi baru bila konsepnya sudah ada.
   Daftar sah = `core/collection_registry.py` (dibuat F0). Menyentuh koleksi di luar daftar ⇒ gate merah.
2. **Setiap dokumen marketing WAJIB punya `account_id`** hasil `core.marketing_account_scope.stamp_account()`.
   `account_name`/`platform` **selalu turunan** (untuk tampilan), **tidak pernah** dipakai sebagai kunci/filter.
3. **Uang per-pesanan ditulis 1× di header pesanan; uang per-SKU di `items[]`.** Dilarang
   menjumlahkan field per-pesanan dari baris SKU.
4. **`marketing_sales_data` adalah TURUNAN** (kecuali platform tanpa ekspor). Bentuk dokumennya
   hanya boleh dibuat oleh `core/marketing_sales_shape.py::build_daily_doc()`; hanya boleh
   ditulis lewat `core/marketing_daily_rollup.py::recompute_daily()` (impor/pesanan) atau
   entri manual yang memakai builder yang sama.
5. **Stok jual katalog** hanya boleh dari `core/catalog_stock.py`. Dilarang membaca
   `rahaza_material_stock.qty` mentah (pakai `core/stock_schema.read_qty/read_reserved`).
6. **HPP** hanya dari master (`rahaza_models.hpp` → `base_hpp` → 0) lewat `core/product_master.py`;
   katalog **menyimpan salinan + `hpp_source`**, tidak pernah menghitung sendiri.
7. **Marketing tidak pernah menulis jurnal/AR.** Satu-satunya pemicu jurnal marketplace =
   `marketing_settlements` (F9) → **DRAFT** JE lewat `routes/rahaza_posting.py`.
8. **Setiap endpoint daftar** menerima `account_id` **dan** menyaring dengan
   `visible_account_ids(user)` (F6). Tanpa itu, RBAC per toko tidak ada artinya.
9. **Idempoten.** Semua impor punya kunci dedupe tertulis; jalan 2× ⇒ jumlah dokumen sama.

---

## 1. `marketing_platform_accounts` — MASTER TOKO (akar semua lingkup)

| Field | Tipe | Status | Aturan |
|---|---|---|---|
| `id` | uuid | ADA | kunci yang dipakai semua koleksi lain (`account_id`) |
| `account_code` | str | ADA | unik, huruf besar (mis. `TIKTOK-OUTFIT`) |
| `account_name` | str | ADA | tampilan saja |
| `username` | str | ADA | username toko di platform |
| `platform` | enum | ADA | `shopee` \| `tiktok` \| `tokopedia` \| `lazada` \| `blibli` \| `instagram` \| `website` |
| `group` | str | ADA | `official_store` \| `reseller` \| … |
| `status` | enum | ADA | `active` \| `paused` \| `closed` |
| `pic_id` | uuid→users | ADA (tidak ditegakkan) | **F6**: PIC utama toko |
| `assigned_staff[]` | uuid[] | ADA (tidak ditegakkan) | **F6**: staf lain yang boleh akses |
| `health_score` | num | ADA | turunan |
| `credentials{}` `import_config{}` | obj | ADA | — |
| **`platform_warehouse_name`** | str | **BARU F1** | nama gudang di ekspor platform (mis. `Outfit Boutique`) — dipakai memverifikasi berkas impor milik toko yang benar |
| **`platform_shop_id`** | str | **BARU F1** | id toko di platform (bila ada di ekspor) |
| **`coa_revenue_code`** | str→COA | **BARU F0** | mis. `4-122` (TikTok Outfit Boutique) |
| **`coa_cash_code`** | str→COA | **BARU F0** | rekening penerima pencairan (mis. `1-131`, `1-154`) |
| **`coa_receivable_code`** | str→COA | **BARU F0** | default `1-220` Piutang Platform Online Shop |
| **`revenue_basis`** | enum | **BARU F2** | `produk_setelah_diskon` (default) \| `order_amount` — dasar Target toko ini |

**Toko nyata (dari COA, wajib di-seed F0):** `4-111` Shopee Grosirhijabsragen · `4-112` Shopee Daluna ·
`4-113` Shopee Moen · `4-114` Shopee Lain-lain · `4-121` TikTok Daluna · `4-122` TikTok Outfit Boutique ·
`4-123` TikTok Style by Moen · `4-124` TikTok Fatimahijab · `4-125` TikTok Dezza Kids · `4-131` Tokopedia.

---

## 2. `marketing_orders` — **1 DOKUMEN = 1 PESANAN** (bukan 1 baris SKU)

> **Keputusan arsitektur (F1).** Ekspor memberi 1 baris per SKU (601 baris → 559 pesanan).
> Importir **mengelompokkan per `order_id`** menjadi 1 dokumen ber-`items[]`.
> Alasan: 41 pembaca yang sudah ada menghitung `$sum: 1` sebagai jumlah pesanan dan
> `$sum: '$total_payment'` sebagai omzet. Menyimpan 1 dokumen per baris SKU akan membuat
> **semua** pembaca itu salah (D05). Dengan header+`items[]`, pembaca lama menjadi **benar**
> tanpa diubah, dan analisis per-SKU memakai `$unwind: '$items'`.

### 2.1 Kunci & indeks
| Tingkat | Kunci | Indeks |
|---|---|---|
| Pesanan | `(account_id, platform, order_id)` | **unique** (BARU F1) |
| Baris SKU | `items[].platform_sku_id` (+ `items[].line_no`) | — (terbukti unik di berkas nyata) |
| Bantu | `account_id`, `order_date`, `status`, `fulfillment_status`, `items.platform_sku_id` | biasa |

### 2.2 Header — identitas & tautan
`id` · `order_id` · `platform` · `account_id` · `account_name`(turunan) · `platform_shop_id?` ·
`purchase_channel` (`TikTok`/`Shopee`/…) · `order_channel` (`LIVE`\|`Videos`\|`Product cards`\|`Search`\|`Ads`\|`Affiliate`\|`Campaign`\|`other`) ·
`creator_handle` · `creator_id?`(dipetakan ke `marketing_kol_creators`) · `is_preorder` (bool) ·
`warehouse_name_raw` · `fulfillment_type`

### 2.3 Header — UANG (ditulis **1×**, dari kolom per-pesanan)
| Field | Sumber ekspor TikTok | Catatan |
|---|---|---|
| `order_amount` | `Order Amount` | yang dibayar pembeli (termasuk ongkir) |
| `shipping_fee_after_discount` | `Shipping Fee After Discount` | |
| `original_shipping_fee` | `Original Shipping Fee` | |
| `shipping_fee_seller_discount` | `Shipping Fee Seller Discount` | subsidi ongkir penjual |
| `shipping_fee_platform_discount` | `Shipping Fee Platform Discount` | |
| `buyer_service_fee` `handling_fee` `shipping_insurance` `item_insurance` | idem | biaya yang ditanggung pembeli |
| `order_refund_amount` | `Order Refund Amount` | |
| `payment_platform_discount` | `Payment platform discount` | |
| **`revenue_product`** | Σ `items[].sku_subtotal_after_discount` | **omzet produk** (default dasar Target) |
| **`revenue_gross`** | Σ `items[].sku_subtotal_before_discount` | harga coret |
| **`seller_discount_total`** | Σ `items[].sku_seller_discount` | **realisasi kategori anggaran `diskon`** |
| **`platform_discount_total`** | Σ `items[].sku_platform_discount` | ditanggung platform |
| `revenue` | = `revenue_product` | **kompatibilitas** pembaca lama |
| `total_payment` | = `order_amount` | **kompatibilitas** pembaca lama (tidak lagi dobel) |
| `quantity` | Σ `items[].quantity` | |
| `platform_fee` | *tidak ada di ekspor A* | **selalu `null` + `fee_known: false`** — diisi hanya oleh Settlement (F9) |

### 2.4 Header — status & waktu
`status` (kanonik: `new`\|`paid`\|`packed`\|`shipped`\|`delivered`\|`completed`\|`cancelled`\|`returned`) ·
`status_raw` (teks asli platform, mis. `Perlu dikirim`) · `substatus_raw` · `return_type_raw` ·
`fulfillment_status` (`unallocated`\|`pending_fulfillment`\|`allocated`\|`shipped`\|`done`) ·
`order_date`(=Created Time) · `paid_at` · `rts_at` · `shipped_at` · `delivered_at` · `cancelled_at` ·
`cancel_by` · `cancel_reason`

**Kamus status (F1, wajib tertulis, bukan tebakan):**
`Perlu dikirim`→`paid` · `Menunggu pengambilan`/`Menunggu pengiriman`→substatus saja ·
`Dikirim`/`Sedang dikirim`→`shipped` · `Selesai`→`completed` · `Dibatalkan`→`cancelled` ·
`Pengembalian/Refund`→`returned`. Nilai tak dikenal ⇒ **baris ditolak dengan pesan yang menyebut nilai aslinya** (tidak pernah dipaksa jadi `new`).

**Kamus kurir:** `J&T Express`→`jnt` · `JNE Express Standard ID`→`jne` · `SPX`/`Shopee Express`→`spx` ·
`SiCepat`→`sicepat` · `AnterAja`→`anteraja` · `Ninja`→`ninja` · `Grab`→`grab` · `GoSend`→`gojek` ·
kosong→`lainnya` (+ `courier_raw` selalu disimpan).

### 2.5 Header — pembeli & pengiriman
`customer_name` · `customer_phone` · `buyer_username` · `province` · `city` · `district` · `village` ·
`zipcode` · `address_detail` · `tracking_number` · `courier` · `courier_raw` · `delivery_option` ·
`package_id` · `weight_kg` · `payment_method` · `buyer_message` · `seller_note`

### 2.6 `items[]` — satu elemen = satu SKU platform
`line_no` · `platform_sku_id` (kunci) · `seller_sku` · `product_name_raw` · `variation_raw` ·
`product_category_raw` · `quantity` · `qty_returned` · `sku_unit_original_price` ·
`sku_subtotal_before_discount` · `sku_platform_discount` · `sku_seller_discount` ·
`sku_subtotal_after_discount` · `is_preorder` ·
**tautan master:** `catalog_item_id` · `fg_material_id` · `variant_id` · `model_id` · `master_link_source`
(`sku_map`\|`sku_exact`\|`name_match`\|`unlinked`) · `hpp_snapshot` (dari katalog saat impor, untuk marjin)

### 2.7 Jejak impor
`_import_session_id` · `_import_source_type` · `import_batch_id` · `raw_row_ids[]` ·
`created_at/by` · `updated_at/by`

---

## 3. `marketing_sales_data` — REKAP HARIAN (TURUNAN)

**Kunci unik:** `(account_id, date, revenue_type)` — `date` = `"YYYY-MM-DD"` (string), `revenue_type` ∈ `total`\|`live`.
**Satu-satunya pembuat bentuk:** `core/marketing_sales_shape.py::build_daily_doc()`.

```
{ id, account_id, account_code, platform, date, revenue_type,
  metrics: { revenue,                 # = basis toko (revenue_product ATAU revenue_order_amount)
             revenue_product,         # Σ items.sku_subtotal_after_discount
             revenue_order_amount,    # Σ order_amount (per pesanan)
             gross_before_discount, seller_discount, platform_discount,
             orders, units, buyers, aov, gmv, conversion_rate },
  funnel:  { uv, pv, product_clicks, ctr, atc_visitors, atc_units,
             cart_to_order_cr, order_to_paid_cr },              # F8 (impor KPI / form mingguan)
  buyers_mix: { new_buyers, returning_buyers, sales_new, sales_returning },   # F8
  traffic: { live, video, ads, affiliate, campaign, organic, product_card, search, other },  # F1/F8
  fulfillment: { fulfillment_rate, cancellation_rate, return_rate, late_shipment_rate,
                 processing_hours, cancelled_orders, cancelled_value,
                 returned_orders, returned_value },
  customer_satisfaction: { rating, review_count, response_rate, response_time_hours },
  live_metrics: { viewers, unique_viewers, avg_viewers, peak_viewers, watch_time_avg_sec,
                  likes, shares, comments, new_followers, live_sessions },
  content_metrics: { video_views, video_completion_rate, saves, gmv_per_video },   # F7
  revenue_basis, source, locked_source, kpi_source,
  import_history_id, _import_session_id, created_at/by, updated_at/by }
```

`source` ∈ `orders_auto` (F2, dari `marketing_orders`) · `livehost_creator_auto` (sudah ada) ·
`manual` (platform tanpa ekspor) · `import_kpi` (F8, hanya mengisi `funnel/buyers_mix/traffic/…`).
`locked_source=true` ⇒ entri manual ke grup `metrics` **ditolak 409** dengan pesan
"angka ini diturunkan dari pesanan; ubah pesanannya".
**Semua grup selalu ADA (objek kosong bila belum ada data) — pembaca dilarang mengindeks langsung.**

---

## 4. `marketing_catalog_items` — KATALOG PER TOKO

### 4.1 Status penayangan (BARU F4)
| Field | Tipe | Diisi oleh | Aturan |
|---|---|---|---|
| `publish_state` | enum | **manusia** | `draft` \| `published` \| `rejected` \| `archived` |
| `platform_url` | str | manusia | **bukti tayang** — wajib bila `publish_state='published'` |
| `published_at` | dt | sistem | saat `publish_state` → `published` |
| `rejected_reason` | str | manusia | wajib bila `rejected` |
| `is_preorder` | bool | manusia / data | `true` bila dijual pre-order |
| **`catalog_status`** | enum | **TURUNAN, tidak pernah diketik** | lihat tabel di bawah |

**Tabel turunan `catalog_status` (satu-satunya rumus, di `core/catalog_status.py`):**
| Urutan | Syarat | Hasil |
|---|---|---|
| 1 | `publish_state='archived'` atau `is_active=false` | `NONAKTIF` |
| 2 | `publish_state='rejected'` | `DITOLAK` |
| 3 | `publish_state='draft'` | `DRAFT` |
| 4 | `published` **dan** `is_preorder=true` | `PRE_ORDER` |
| 5 | `published` **dan** `available > 0` | `ACTIVE` |
| 6 | `published` **dan** `available <= 0` | `HABIS` |

`available` = **selalu** `core/catalog_stock.item_sellable()` (semua lokasi kecuali karantina/blokir, minus reserved).

### 4.2 Foto (BARU F4)
| Field | Isi | Sumber |
|---|---|---|
| `master_images[]` | `{url, caption, from: 'rnd_style'\|'model'}` | **turunan** dari `rahaza_models.image_paths` (asalnya `dewi_rnd_styles.design_images`). Disalin saat `from-fg` **dan** saat `refresh-from-master`. **Baca-saja di layar katalog.** |
| `images[]` | url[] | **foto versi marketplace** yang diunggah marketing (endpoint yang sudah ada: `POST /{catalog_id}/items/{item_id}/photos`) |
| `photos[]` | url[] | alias legacy — tetap ditulis ganda (sudah ada) |
| `primary_image` | str | turunan: `images[0]` bila ada, jika tidak `master_images[0].url` |

### 4.3 Pemetaan SKU platform (BARU F1 — **tanpa koleksi baru**)
`platform_sku_ids[]` = `{platform, platform_sku_id, seller_sku, first_seen, last_seen, mapped_by}`
pada dokumen item. Indeks: `platform_sku_ids.platform_sku_id` (+ unik per `(account_id, platform, platform_sku_id)` lewat pemeriksaan aplikasi).
83 SKU platform pada berkas nyata dipetakan ke item katalog lewat layar pemetaan (F1).

### 4.4 Field yang SUDAH ADA (jangan dibuat ulang)
identitas: `id, catalog_id, account_id, platform, sku, name, description, variant_info, unit, tags[]` ·
master: `fg_material_id, material_id(legacy), fg_code, fg_name, fg_color, model_id, variant_id, variant_sku, source, category_id, category_code, category_name, category, weight_gram` ·
harga: `harga_jual, price, harga_coret, harga_original, original_price, platform_price, retail_price_master, price_delta_vs_master` ·
HPP/marjin: `hpp, hpp_source, hpp_updated_at, margin, margin_pct` ·
stok: `stock_quantity`(cache), `stock_alert_threshold, stock_status, stock_source, stock_in_sync, fg_onhand, fg_reserved, fg_available, fg_excluded_onhand, last_stock_sync` ·
turunan saat dibaca: `available, in_sync, link_type, stock_live_status, needs_attention, attention_reason` ·
lain: `is_active, created_at/by, updated_at`

---

## 5. `marketing_budgets` + `marketing_spend_entries` — ANGGARAN PER TOKO/BULAN

**Kunci:** `(account_id, period)` dengan `period = "YYYY-MM"`.
**Kategori (BARU: +`komisi`):** `ads` · `sample` · `diskon` · `livehost` · `kol` · **`komisi`**
(komisi afiliasi/kreator). *Gratis ongkir TIDAK dibuat kategori (keputusan owner).*

| Kategori | Rencana | Realisasi (F5) | Sumber realisasi |
|---|---|---|---|
| `ads` | diketik | **OTOMATIS** | Σ `marketing_ads_data.spend` (account_id, bulan) |
| `diskon` | diketik | **OTOMATIS** | Σ `marketing_orders.seller_discount_total` (+ `shipping_fee_seller_discount`) |
| `komisi` | diketik | **OTOMATIS** | komisi kreator (`marketing_kol_creators` cost config × omzet kreator) |
| `livehost` | diketik | OTOMATIS (sudah ada) | Σ `marketing_livehost_shifts.total_pay` status `calculated` |
| `kol` | diketik | OTOMATIS (sudah ada) | fixed_fee + %komisi × omzet sesi kreator |
| `sample` | diketik | **MANUAL** (tetap) | `marketing_spend_entries` (tidak ada di ekspor mana pun) |

Realisasi otomatis **tidak** menulis `marketing_spend_entries` (agar tidak dobel); ia dihitung saat
dibaca dan dilaporkan dengan `source: 'auto'` + `evidence_ref` (mis. jumlah pesanan yang dijumlah).
`marketing_spend_entries` tetap **hanya** untuk pengeluaran manual.

---

## 6. `marketing_account_targets` / `marketing_creator_targets` — TARGET BULANAN

**Kunci:** `(account_id, year, month)` / `(creator_id, year, month)` — **unique (BARU F5)**.
Field ADA: `revenue_target, orders_target, health_score_target, notes, updated_by/at`.
**BARU F5:** `units_target`, `aov_target`, `content_target` (jumlah konten), `basis`
(salinan `revenue_basis` saat target ditetapkan — supaya pencapaian tidak berubah makna
kalau basis diganti kemudian), `set_by_role`, `locked` (turunan dari `marketing_period_locks`).

---

## 7. `marketing_content_calendar` — RENCANA + REALISASI KONTEN (F7)

ADA: `id, account_id, account_name, platform, date, content_type, title, description, cta, post_time, reference_link, status`
**BARU:** `creator_id` → `marketing_kol_creators.id` · `creator_name`(turunan) · `assignee_user_id?` ·
`catalog_item_id?` / `sku?` · `brief` · `hook` · `published_url` · `published_at` ·
`platform_post_id` · `kpi{views, likes, comments, shares, saves, watch_time_avg_sec, ctr, orders, gmv, gpm}` ·
`kpi_updated_at` · `kpi_source` (`manual`\|`import`) · `_import_session_id`
**Status kanonik:** `draft` → `scheduled` → `posted` → `cancelled`. `published_url` **wajib** bila `posted`.
**Kunci dedupe impor KPI:** `(account_id, published_url)` bila ada, jika tidak `(account_id, date, title)`.

---

## 8. `marketing_settlements` — PENCAIRAN (KOLEKSI BARU, F9) — satu-satunya pemicu jurnal

**Kunci unik:** `(platform, account_id, settlement_id)`.
```
{ id, account_id, platform, settlement_id, settlement_date, period_from, period_to,
  currency: 'IDR',
  gross_sales, refunds, seller_discount, shipping_subsidy,
  platform_commission, platform_service_fee, affiliate_commission, ads_deduction,
  other_deductions, adjustments,
  net_payout,                      # yang benar-benar cair
  bank_account_ref, payout_status, # pending | paid
  matched_orders[],                # order_id yang ikut di settlement ini (bila laporan memberi)
  je_id, je_status,                # draft | posted (diisi F9)
  raw{},                           # baris asli untuk audit
  _import_session_id, created_at/by, updated_at/by }
```
**Jurnal (DRAFT, profil posting baru `marketplace_settlement`):**
```
Dr  coa_cash_code (mis. 1-131 / 1-154)          net_payout
Dr  4-141 Potongan Platform (Fee Shopee/TikTok) platform_commission + platform_service_fee
Dr  6-400 Biaya Admin & Platform OS             other_deductions
Dr  6-110/6-112 Biaya Iklan (per platform)      ads_deduction
Dr  4-140 Retur Penjualan Online Shop           refunds
Dr  6-210 Biaya Ongkir Penjualan (Subsidi)      shipping_subsidy
  Cr  1-220 Piutang Platform Online Shop        (total sisi debit)
```
Status awal **`draft`** → Finance menekan `POST /api/rahaza/journals/{je_id}/post`.
Idempoten lewat `source_module='marketplace_settlement'`, `source_ref=settlement_id`
(`routes/rahaza_posting.py::_find_existing_je`).

---

## 9. `marketing_period_locks` — KUNCI PERIODE (KOLEKSI BARU, F5/F6)

**Kunci unik:** `(account_id, period)`. `{ status: 'open'|'closed', closed_by, closed_at, reopened_by, reopened_at, reason, history[] }`
Penjaga wajib dipasang di: `POST /api/marketing/targets`, `PUT /api/marketing/budget`,
`POST /api/marketing/budget/spend`, entri/ubah `marketing_sales_data` manual, commit impor
yang menyentuh tanggal dalam periode terkunci ⇒ **HTTP 423** (bukan 403 — periode terkunci ≠ tidak punya izin),
kecuali role pembuka (`owner`, `spv_marketing`).

## 10. `marketing_change_log` — JEJAK NILAI LAMA (KOLEKSI BARU, F6)
`{ id, entity: 'target'|'budget'|'sales_daily'|'catalog_item'|'settlement', entity_id, account_id, period?, field, old_value, new_value, actor_id, actor_name, actor_role, at, reason? }`

---

## 11. KOLEKSI YANG **DIHAPUS** (F0.6 — keputusan owner: hapus total, data lama diabaikan)

| Koleksi | Alasan | Tindakan F0.6 |
|---|---|---|
| `marketing_import_sessions` | milik mesin AI lama (`universal_import.py`) yang dihapus | **drop** |
| `marketing_import_uploads` | milik `marketing_import.py` yang dihapus | **drop** |
| `marketing_import_templates` | template mesin lama — digantikan `marketing_data_import_formats` | **drop** |
| `marketing_import_history` | riwayat mesin lama | **drop** |
| `marketing_import_*` (sisa apa pun) | koleksi karangan dari jenis tak dikenal | **drop** |
| `marketing_discount_campaigns` | tujuan SALAH; yang benar `marketing_discounts` | **drop** |
| `marketing_sample_shipments` | tujuan SALAH; yang benar `marketing_samples` | **drop** |

Ketujuhnya masuk `DEPRECATED` di `core/collection_registry.py` ⇒ gate MERAH bila kode baru
menyentuhnya. **Satu-satunya koleksi sesi impor yang sah:** `marketing_data_import_sessions`.

### 11b. `marketing_data_import_formats` — SIDIK FORMAT (KOLEKSI BARU, F1)
Menjawab kekhawatiran owner *"hasil export itu bisa banyak formatnya"* **tanpa** bergantung AI.
**Kunci unik:** `(source_type, fingerprint)`.
```
{ id, source_type, fingerprint,          # sha1 daftar header yang dinormalkan
  platform, label,                       # mis. "TikTok Seller Center — Untuk Dikirim (65 kolom)"
  headers[],                             # header asli apa adanya
  mapping[],                             # {column, field, method} hasil konfirmasi manusia
  created_by, created_at, use_count, last_used_at }
```
Alur: fingerprint **dikenal** ⇒ pemetaan langsung dipakai, wizard lompat ke pratinjau ·
fingerprint **baru** ⇒ pemetaan kamus+fuzzy ditampilkan untuk **dikonfirmasi**, lalu disimpan
sebagai format baru. Tombol AI (`/sessions/{id}/ai-assist`) hanya mengusulkan kolom **sisa**
dan tidak pernah menimpa hasil `exact`/`synonym`/`manual`.

## 11c. Koleksi yang **tetap terpisah secara sadar** (bukan duplikasi)
| Koleksi | Kenapa tidak digabung |
|---|---|
| `rahaza_budgets` vs `marketing_budgets` | `rahaza_budgets` = anggaran **perusahaan** (Finance); `marketing_budgets` = anggaran **per toko/bulan** (performa). F5 hanya **membandingkan**, tidak menyalin |
| `rahaza_periods` vs `marketing_period_locks` | kunci periode **keuangan** vs kunci periode **marketing per toko** — hak dan konsekuensinya berbeda |
| `rahaza_orders` vs `marketing_orders` | pesanan **buyer/maklon** vs pesanan **marketplace** |

---

## 12. PETA JENIS IMPOR (SATU pintu: `/api/marketing/data-import`)

| Jenis (`source_type`) | Koleksi tujuan | Lingkup | Kunci dedupe | Status |
|---|---|---|---|---|
| `sales_daily` | `marketing_sales_data` | toko wajib | `account_id,date,revenue_type` | ADA — **bentuk diperbaiki F0** |
| `orders` | `marketing_orders` | toko wajib | `account_id,order_id` | ADA — **digantikan `marketplace_orders`** (F1), disimpan sebagai alias |
| **`marketplace_orders`** | `marketing_orders` | toko wajib | `account_id,platform,order_id` | **BARU F1** (Ekspor A, 65 kolom, header+`items[]`) |
| **`marketplace_fulfillment`** | `marketing_orders` (update) | toko wajib | `account_id,platform,order_id` | **BARU F3** (Ekspor B & C) |
| **`shop_kpi`** | `marketing_sales_data` (grup non-`metrics`) | toko wajib | `account_id,date,revenue_type='total'` | **BARU F8** |
| **`content_performance`** | `marketing_content_calendar` | toko wajib | `account_id,published_url` \| `account_id,date,title` | **BARU F7** |
| **`marketplace_settlement`** | `marketing_settlements` | toko wajib | `platform,account_id,settlement_id` | **BARU F9** |
| `ads` | `marketing_ads_data` | toko wajib | `account_id,date,campaign_name` | ADA |
| `live_sessions` | `marketing_live_sessions` | toko + host | `account_id,session_date,title` | ADA |
| `live_session_products` | `marketing_live_session_products` | toko + sesi | `session_id,catalog_item_id` | ADA |
| `livehost_shifts` | `marketing_livehost_shifts` | toko + host | `account_id,host_id,date,shift_start_time` | ADA |
| `catalog_items` | `marketing_catalog_items` | toko + katalog | `catalog_id,sku` | ADA — **+foto/status F4** |
| `content_calendar` | `marketing_content_calendar` | toko wajib | `account_id,date,title` | ADA |
| `discounts` | `marketing_discounts` | toko wajib | `account_id,name,start_date` | ADA |
| `product_launches` | `marketing_product_launches` | toko wajib | `account_id,product_name,launch_date` | ADA |
| `samples` | `marketing_samples` | toko + kreator | `account_id,date,username,product` | ADA |
| `kol_creators` | `marketing_kol_creators` | opsional | `creator_code` | ADA |
| `returns` | `marketing_returns` | toko wajib | `account_id,order_id,product` | ADA |
| `reviews` | `marketing_reviews` | toko wajib | (lihat schema) | ADA |
| `complaints` | `marketing_complaints` | toko wajib | (lihat schema) | ADA |
| `account_health` | `marketing_account_health` | toko wajib | `account_id,snapshot_date` | ADA |

**Aturan tambahan F1:** setiap jenis impor menyimpan `format_fingerprint` (hash daftar header yang
dinormalkan) di `marketing_data_import_formats` (§11b). Berkas dengan fingerprint yang sudah
dikenal ⇒ pemetaan **langsung dipakai tanpa AI**. Fingerprint baru ⇒ pemetaan kamus + fuzzy
ditampilkan untuk dikonfirmasi; sisa kolom tak terpetakan boleh dibantu tombol AI (opsional).

**Koleksi yang dibaca tapi tidak pernah ditulis (harus dituntaskan F10):**
`marketing_kol_campaigns` — dibaca `routes/dewi_executive_report.py:247` (`count_documents`)
padahal **tidak ada satu pun penulis** ⇒ laporan eksekutif selalu melaporkan 0 kampanye KOL.
Pilihan F10: sambungkan ke sumber nyata (`marketing_content_calendar` / `marketing_kol_creators`)
**atau** hapus metriknya. Dilarang "memperbaiki" dengan membuat koleksi baru.

---

## §KPI PLATFORM — `marketing_platform_kpi_daily` (F7.2, ditambahkan 2026-08-13)

**Kenapa koleksi baru, bukan `marketing_sales_data`.** Ekspor KPI Seller Center memakai definisi
angka milik platform (`Pesanan Dibuat` / `Pesanan Siap Dikirim` / `Pesanan Dibayar`, termasuk pesanan
yang nanti batal), sedangkan omzet SSOT toko adalah **turunan pesanan** (§F2). Menyimpan keduanya di
satu koleksi berarti cepat atau lambat ada layar yang menjumlahkannya ⇒ satu penjualan dihitung dua
kali. Pemisahan koleksi membuat aturan itu **struktural**, bukan sekadar niat.

| field | tipe | keterangan |
|---|---|---|
| `id` | uuid | kunci internal |
| `account_id`, `account_code`, `account_name`, `platform` | str | dicap `scope.stamp_account` |
| `date` | str `YYYY-MM-DD` | tanggal KPI (bukan rentang — rentang ditolak penormal) |
| `channel` | enum `shop` \| `live` \| `video` | `shop` sudah MENCAKUP live+video ⇒ dilarang dijumlah |
| `source` | str | `shopee_shop_stats` \| `shopee_live_1d` \| `shopee_live_overview` \| `shopee_video_overview` |
| `gmv_created` / `gmv_ready` / `gmv_paid` | money | penjualan per basis pesanan platform |
| `orders_created` / `orders_ready` / `orders_paid` | int | jumlah pesanan per basis |
| `visitors`, `product_clicks`, `product_views`, `buyers`, `products_sold`, `add_to_cart` | int | trafik & konversi |
| `viewers`, `active_viewers`, `effective_viewers`, `peak_viewers`, `views` | int | penonton konten |
| `avg_watch_seconds`, `live_minutes` | num | durasi teks ekspor (`10j50m8d`, `00:01:19`) → angka |
| `live_sessions`, `videos_with_product`, `completion_rate` | int/pct | volume & kualitas konten |
| `likes`, `shares`, `comments`, `new_followers` | int | interaksi |
| `gmv_product_page` / `gmv_live` / `gmv_video` / `gmv_affiliate` / `gmv_ads` | money | kontribusi kanal (hanya diisi untuk ekspor 1 hari) |
| `conversion_rate`, `ctr` | pct | apa adanya dari platform |
| `aov`, `conversion_rate_calc`, `gmv_per_view`, `engagement`, `engagement_rate` | num | **dihitung sistem**, tidak diketik |
| `revenue_basis` | const `platform_kpi` | penanda wajib |
| `is_platform_kpi` | bool `true` | penanda wajib |
| `not_sales_ssot_note` | str | kalimat larangan menjumlah, ikut tersimpan di dokumen |

* **Dedupe:** `(account_id, date, channel)` — impor ulang ekspor tanggal sama ⇒ **update**, karena
  angka platform memang berubah H+1 (pesanan batal).
* **Pembaca:** `GET /api/marketing/platform-kpi` & `/summary` (RBAC per toko F6).
* **Dilarang:** menulis koleksi ini dari layar entri manual, dan menjumlahkannya dengan
  `marketing_sales_data` / `marketing_orders`.

## §IKLAN — tambahan field laporan CPC Shopee pada `marketing_ads_data` (F7.2)

Laporan iklan Shopee bersifat **per kampanye untuk satu periode**, bukan per tanggal.

| field | keterangan |
|---|---|
| `date` | **string** `YYYY-MM-DD` = awal periode (dipakai realisasi anggaran bulanan F5) |
| `period_start`, `period_end`, `period_days`, `spend_per_day_avg` | rentang laporan apa adanya |
| `spend`, `revenue`, `direct_revenue`, `impressions`, `clicks`, `conversions`, `products_sold` | angka platform |
| `ctr`, `cpc`, `cpa`, `roas` | **dihitung sistem** dari spend/klik/konversi/omzet |
| `ctr_platform`, `acos`, `roas_platform`, `direct_roas_platform` | angka platform apa adanya (pembanding) |
| `source_report` = `shopee_ads_cpc` | penanda asal, dipakai pagar tumpang-tindih |

* **Dedupe:** `(account_id, campaign_name, period_start, period_end)`.
* **Pagar:** periode yang **menyeberang bulan ditolak penormal**; periode yang **beririsan** dengan
  laporan yang sudah ada ditolak **409** saat commit (anti dobel hitung biaya iklan).

## §KPI PER KONTEN — tambahan pada `marketing_content_calendar` (F7.2)

Impor `content_performance` memakai **`published_url` sebagai kunci** (`account_id + published_url`).
Saat link sudah ada, impor **hanya menempelkan** `kpi`, `kpi_derived`, `kpi_source='import'`,
`kpi_updated_at`, `published_url`, `status='posted'` (+ `creator_id` bila konten belum punya pemilik).
Judul, tanggal rencana, dan jenis konten **tidak pernah ditimpa** — itu pekerjaan staf, bukan berkas.

## §ASSIGN TOKO — `marketing_platform_accounts.assigned_staff` (F6.4)

* Ditulis HANYA lewat `POST /api/marketing/account-assign/{account_id}` oleh peran
  `owner/admin/superadmin/spv_marketing/manager_marketing`.
* Isinya hanya `users.id` dengan peran berlingkup toko (`staff_marketing`, `pic_toko`, `host_live`,
  `cs_staff`). Peran yang sudah melihat semua toko ⇒ **400** (assign tanpa arti).
* Setiap perubahan menulis `marketing_change_log` (`entity=marketing_platform_accounts`,
  `action=assign_staff`) berisi `before.assigned_staff`, `after.assigned_staff`, `added`, `removed`,
  pelaku + peran + alasan. Riwayat dibaca `GET /api/marketing/account-assign/{id}/history`.

## §PEMULIHAN IMPOR — `marketing_data_import_undo` (KOLEKSI, F3, ditambahkan 2026-08-14)

**Tujuan:** membuat tombol *“Batalkan impor”* menepati janjinya pada impor yang **hanya
memperbarui** (`SourceType.update_only` — Ekspor B “Dikirim/Selesai” & Ekspor C
“Batal/Pengembalian”). Impor jenis itu **tidak membuat baris**, jadi rollback gaya lama
(“hapus `committed_ids`”) melaporkan *0 baris dihapus* sambil membiarkan **seluruh**
perubahan status pesanan di tempatnya.

| field | tipe | aturan |
|---|---|---|
| `id` | uuid | kunci baris jejak |
| `session_id` | uuid | sesi impor yang membuat perubahan (kunci pembatalan) |
| `collection` | str | koleksi tujuan (selalu `marketing_orders` untuk F3) |
| `doc_id` | uuid | dokumen yang diubah |
| `order_ref` | str | No. Pesanan — **wajib**, dipakai laporan agar bisa ditindaklanjuti manusia |
| `account_id` | uuid | lingkup toko (aturan #2) |
| `status_before` | str | status pesanan **sebelum** berkas ini diproses |
| `before` | dict | nilai lama field susulan + cap waktu + efek samping |
| `items_qty_before` | list\|null | `[{platform_sku_id, qty_returned}]` — hanya bila berkas menyentuh retur per SKU |
| `qty_returned_total_before` | number\|null | total retur lama (sepasang dengan di atas) |
| `created_at` / `restored_at` | datetime\|null | `restored_at=null` ⇒ jejak **belum** dipakai (idempoten) |

**Aturan keras (semuanya dijaga `test_core_f3_fulfillment.py`, gate `INV-MKTFULFILL`):**

1. **Idempoten.** Membatalkan dua kali tidak boleh memulihkan dua kali: hanya baris
   `restored_at=null` yang diproses, dan pembatalan kedua dijawab **400 “sudah dibatalkan”**
   (bukan “belum di-commit” — pesan itu menyesatkan tepat saat staf paling butuh kejelasan).
2. **`_NEVER_RESTORE`** — `reserved_rows`/`reserved_qty`/`stock_reserved` dsb **tidak pernah**
   dipulihkan. Memulihkannya = menjanjikan barang yang sama ke dua pembeli.
3. **`_TERMINAL_KEEP`** — pesanan yang berkasnya jadikan `cancelled`/`returned` **tidak
   dihidupkan lagi statusnya**; hanya field susulannya dipulihkan, dan laporannya **menyebut
   nomor pesanan + langkah manualnya**. Aturan ini sama dengan
   `core/order_status.check_transition` (jangan dilonggarkan di satu sisi saja).
4. **Angka pemulihan disimpan di sesi impor** (`restored_count`, `restore_status_count`,
   `restore_fields_only`, `restore_missing`, `restore_notes`) supaya **Riwayat Impor** bisa
   membacanya lagi besok — bukan hanya sekali lewat toast 5 detik.
   Dibaca layar lewat `GET /api/marketing/data-import/sessions/{id}/undo-report`.
5. **Kunci periode berlaku juga di sini.** Berkas Ekspor B/C tidak punya kolom tanggal
   pesanan, jadi periodenya diambil dari **bulan pesanan tujuan**; commit ke bulan tertutup
   ⇒ **423** dan **tidak ada perubahan separuh jalan**.

### Field sesi impor yang WAJIB dibaca layar (F3.D/F3.F)
`updated_count` (baris lama yang diubah), `undo_count` (jejak pemulihan tersimpan),
`rejected_count`, `committed_count`. Untuk `update_only`, **`committed_count`/`inserted`
selalu 0 secara sengaja** — layar wajib menjelaskannya (`_commit_message()` di
`routes/marketing_data_import.py`), kalau tidak staf menyimpulkan impor gagal lalu
mengunggah ulang Ekspor A — dan justru itu yang membekukan status pesanan lama.

## §INGATAN PEMETAAN IMPOR — `marketing_data_import_formats` (F1 · dilengkapi F8 2026-08-14)

**Tujuan:** berkas rutin harian langsung siap tanpa memetakan ulang kolom. Kunci ingatan =
**sidik susunan kolom** (`eng.format_fingerprint(headers)`, SHA1 dari nama kolom yang dinormalkan).

| field | aturan |
|---|---|
| `source_type` + `fingerprint` | **kunci gabungan** (satu jenis impor bisa punya banyak susunan kolom) |
| `headers` | susunan kolom apa adanya (untuk ditampilkan ke staf) |
| `mapping` | pemetaan yang **PERNAH DIKONFIRMASI MANUSIA** saat commit |
| `use_count`, `last_used_at`, `last_used_by` | dipakai layar untuk MENJELASKAN asal pemetaan |
| `platform`, `created_at`, `created_by` | jejak |

**Aturan keras (dijaga `test_core_f8_assign_ingat_scorecard.py`, gate `INV-MKTOPS`):**

1. **Tidak boleh senyap.** Bila ingatan dipakai, respons unggah WAJIB membawa `format_memory`
   (`use_count`, `last_used_by`, `last_used_at`, `dropped[]`) dan layar wajib menyebutnya. Pemetaan
   yang dipakai ulang tanpa penjelasan = kesalahan yang sama diulang setiap hari sambil tampak
   “otomatis benar”.
2. **Harus bisa DILUPAKAN.** `DELETE /api/marketing/data-import/formats/{fingerprint}?source_type=`
   Tanpa ini, satu kesalahan yang pernah di-commit terpasang otomatis selamanya.
3. **Pemetaan BASI dibuang.** Entri yang menunjuk field yang sudah tidak ada di
   `SourceType.input_fields` **tidak boleh dipakai**: kolomnya dipetakan ulang `auto_map()` dan
   pembuangannya dilaporkan di `format_memory.dropped`.
4. **Kolom baru tidak hilang.** Kolom berkas yang tidak ada di ingatan tetap memakai hasil mesin.
5. **Ingatan belajar dari koreksi.** Commit menulis ulang (`upsert`) `mapping` dari sesi — jadi
   perbaikan staf hari ini yang dipakai besok.

## §ASSIGN TOKO — jejak `marketing_change_log` (F6.4 · dilengkapi F8 2026-08-14)

* `reason` **WAJIB** (≥4 huruf) pada `POST /api/marketing/account-assign/{account_id}` ⇒ 400.
  Alasan itulah satu-satunya yang menjawab “kenapa akses toko saya dicabut?” enam bulan kemudian.
* **GATE TIDAK BOLEH MEMUSNAHKAN JEJAK.** Skrip uji/gate hanya boleh menghapus dokumen
  `marketing_change_log` **miliknya sendiri** (bertanda; mis. penanda pada `reason`). Menghapus
  per `account_id` = menghapus bukti milik toko nyata. Dijaga penjaga statik `A-2e`.
* Staf berakun **NONAKTIF** boleh di-assign tetapi WAJIB dilaporkan lewat `warnings[]`, dan toko
  yang seluruh pemegangnya nonaktif dihitung **belum terpegang** (`stale_count`).

## §RINCIAN SCORECARD KREATOR — `GET /api/marketing/targets/creator/{id}/detail` (F7.4b)

* Total di rincian **WAJIB sama persis** dengan baris `/creator/scorecard` untuk kreator+bulan+toko
  yang sama: memakai `EXCLUDED_FOR_REVENUE` dan `marketing_daily_rollup.order_revenue_product()`
  yang SAMA (bukan hitungan kedua).
* **Tiga sumber uang tetap TERPISAH**; respons dilarang memuat angka gabungan
  (`total_revenue`/`grand_total`/dsb).
* Pesanan yang dikecualikan **tetap ditampilkan** dengan `counted:false` + `why_not_counted`.
* **PERLU KEPUTUSAN PEMILIK:** `EXCLUDED_FOR_REVENUE = ('cancelled',)` ⇒ pesanan **`returned` ikut
  dihitung** sebagai omzet. Selama belum diputuskan, rincian WAJIB memuat catatan
  “PERLU KEPUTUSAN PEMILIK …” beserta jumlah & nilainya (jangan diubah sepihak: menyentuh F2 & F5).
