# AUDIT PORTAL MARKETING — temuan terukur (bukan dugaan)

> Sesi: lanjutan sesudah F1–F13. Fokus: **portal Marketing** (`portal id = toko`, 21 pintu).
> Semua angka di bawah **hasil menjalankan**, bukan kutipan. Harness yang dipakai:
> - `scripts/audit_marketing_portal.py`   — endpoint hantu · lintas domain · endpoint tanpa layar · koleksi
> - `scripts/audit_marketing_fields.py`   — lingkup toko · teks bebas vs select · field mati · input hantu
> - `scripts/audit_marketing_integrity.py`— integritas rujukan pada data nyata di DB
> - `scripts/audit_marketing_runtime.py`  — panggil semua GET marketing sungguhan

Ringkas harness (jalan 2026-08-11):
```
audit_marketing_portal   : layar=69  path FE=179  route BE=1760
                           hantu=1  lintas_domain=2  tanpa_layar=63  koleksi_hilang=17
audit_marketing_fields   : tanpa_lingkup=30  teks_bebas=57  input_hantu=8
audit_marketing_runtime  : GET OK=98  GAGAL=20 (401 portal luar & 422 query wajib)  SKIP=23
audit_marketing_integrity: 9 rujukan cacat
```

---

## 1) CACAT PALING MERUSAK — data marketing tidak berlingkup TOKO

Aturan bisnis owner: **setiap data marketing milik satu toko/akun**. Tanpa `account_id`,
filter "per toko" mustahil dan laporan per akun pasti meleset.

| Pintu | Koleksi | `account_id` di model tulis | Data nyata di DB |
|---|---|---|---|
| Order Terpadu | `marketing_orders` | ✗ hanya `account_name` (teks) | **60/60 `account_id` KOSONG** |
| Kirim Sample | `marketing_samples` | ✗ tidak ada field-nya | **35/35 KOSONG** |
| Iklan / Ads | `marketing_ads_data` | ✗ **tidak ada CRUD sama sekali** | **25/25 KOSONG** |
| Live Selling | `marketing_live_sessions` | ✗ **tidak ada CRUD sama sekali** | **18/18 KOSONG** (+ `host_id` & `creator_id` juga kosong) |
| Peluncuran Produk | `marketing_product_launches` | hanya `target_account_ids[]` | **8/8 KOSONG** |
| Kampanye Diskon | `marketing_discounts` | ✓ ada | **10/10 KOSONG** (seed demo tidak mengisi) |
| Kalender Konten | `marketing_content_calendar` | ✓ ada | **30/30 KOSONG** (seed demo tidak mengisi) |
| Rating & Ulasan | `marketing_reviews` | ✓ | ✓ 40/40 benar |
| Retur | `marketing_returns` | ✓ | ✓ 30/30 benar |
| Komplain | `marketing_complaints` | ✓ | ✓ 40/40 benar |
| Kesehatan Akun | `marketing_account_health` | ✓ | ✓ 30/30 benar |

**Akibat nyata yang bisa ditunjuk:** buka *Order Terpadu* → filter akun → daftar kosong,
padahal 60 order ada. Buka *Live Selling* → tidak ada tombol menambah sesi; angka yang tampil
tak bisa ditelusuri ke host mana pun. Buka *Iklan* → tidak ada cara memasukkan biaya iklan;
angka ROAS berasal dari data demo yang tak bisa diperbarui.

## 2) RUJUKAN YATIM (menunjuk baris yang tidak ada)

```
marketing_orders.sku_id      → marketing_catalog_items.sku   yatim 60/60  (DA-CKW-005, DA-BBM-020, …)
marketing_returns.order_id   → marketing_orders.order_id      yatim 30/30  (ORD-569868, ORD-314947, …)
marketing_complaints.order_id                                 kosong 40/40
marketing_samples.creator_id → marketing_kol_creators.id      kosong 35/35
marketing_live_sessions.host_id / creator_id                  kosong 18/18
```

## 3) FORM: TEKS BEBAS yang seharusnya SELECT ke master (57 field)

Contoh paling jelas — `SampleIn` (`backend/routes/marketing_samples_routes.py:108`):

| Field | Sekarang | Seharusnya |
|---|---|---|
| `username` | teks bebas | pilih dari `marketing_kol_creators` / `marketing_livehosts` (yang di-assign ke toko itu) |
| `product` | teks bebas | pilih item `marketing_catalog_items` milik katalog toko itu |
| `size` | teks bebas | dari master varian ukuran |
| `color` | teks bebas | dari master warna |
| `hpp` | **diketik manual** | diturunkan dari `marketing_catalog_items.hpp` |
| `account_id` | **tidak ada** | wajib — pilih toko dulu |

Pola yang sama di: `ReviewIn.product/.category` · `ReturnIn.product` · `LaunchIn.product_name/.material/.model`
· `OrderCreateBody.product_name/.account_name` · `ContentEntryIn.account_name` · `DiscountIn.account_name`
· `CatalogItemCreate.sku/.category`.

Catatan penting: beberapa layar SUDAH benar (mis. `ContentCalendarModule.jsx:546` sudah
`Select account_id` + auto-isi `account_name`/`platform`), jadi masalahnya **tidak seragam** —
inilah yang membuat staf tidak percaya: pintu sebelah berlaku aturan berbeda.

## 4) IMPORT DATA — dua mesin, satu mati, yang hidup 100% bergantung AI

- **`backend/routes/marketing_import.py` (983 baris) TIDAK DIPANGGIL layar mana pun.**
  Endpoint `/import/upload`, `/analyze`, `/mapping`, `/preview`, `/execute`, `/history`,
  `/apply-template` semuanya menganggur (audit bagian C).
- **`backend/routes/universal_import.py`** yang dipakai layar `ImportCenterModule`:
  - `POST /sessions` → `_process_session_async` → `_ai_detect_schema` **wajib AI**;
    lalu `_ai_normalize_rows` **wajib AI per batch baris**. Kalau AI gagal:
    status `queued` → `failed`, seluruh impor mati (`universal_import.py:406-425`).
  - **Tidak ada pilihan jenis data** — `source_type` DITEBAK AI.
  - **Tidak ada pilihan toko/akun**, tidak ada pilihan host/kreator (`create_import_session`
    hanya menerima `file` + `brand_context`).
  - **Tidak ada template unduhan**.
  - `commit_session` menulis mentah `**committed_data` **tanpa validasi & tanpa `account_id`**
    (`universal_import.py:787-797`) ⇒ baris hasil impor tidak muncul di layar yang difilter.
  - **KOLEKSI TUJUAN SALAH** (`universal_import.py:763-778`):
    | `source_type` | ditulis ke | seharusnya |
    |---|---|---|
    | `discount_campaign` | `marketing_discount_campaigns` | **`marketing_discounts`** |
    | `sample_shipping` | `marketing_sample_shipments` | **`marketing_samples`** |
    | tak dikenal | `marketing_import_<type>` (koleksi sampah) | ditolak dengan pesan jelas |

## 5) LUBANG LAYAR — 63 endpoint marketing tanpa satu pun pemakai

Yang berdampak langsung ke pekerjaan staf:
- **Nota kredit retur** 4 endpoint (`returns/credit-notes*`, `returns/{id}/create-credit-note`) — tak ada layar ⇒ retur berhenti di "disetujui", uang tidak pernah dikembalikan di buku.
- **Live analytics**: `platform-breakdown`, `product-performance`, `performance-trend` — tak ada layar.
- **Ads**: `ads/performance-trend` — tak ada layar.
- **LiveHost**: `shifts/calendar`, `training/progress`, `sop/download` — tak ada layar.
- **Akun**: `sync`, `sync-history`, `recalculate-health`, `legacy-config` — tak ada layar.
- **Dasbor**: `dashboard/toko-overview`, `tasks-stats` — tak ada layar.
- **Daftar acuan** `content-calendar/platforms` & `discounts/types` tak dipakai ⇒ layar
  **menyalin sendiri** daftar platform/jenis diskon (`ContentCalendarModule` & `DiscountCampaignModule`)
  ⇒ begitu backend menambah platform, layar tidak tahu.

## 6) LINTAS DOMAIN (perlu penalaran, belum tentu salah)

- `CatalogManagementModule.jsx:88` → `GET /api/rahaza/product-categories` — **SAH**: kategori produk
  memang master milik RnD/produksi, katalog toko hanya memakai.
- `CatalogManagementModule.jsx:1295` & `TokoProductCatalogModule.jsx:383` → `GET /api/rahaza/variants`
  — **SAH** dengan syarat: varian yang ditarik harus disaring per model produk, bukan seluruh DB.

## 7) INPUT HANTU (diterima endpoint, tidak pernah ditulis)

`POST /api/marketing/sales-data/generate-ar-batch` menerima 8 field
(`date_from,date_to,account_id,platform,revenue_type,grouping,customer_id,notes`) dan **tidak memakai
satu pun** — memang jembatan Sales→AR sengaja dimatikan (keputusan owner 1.a). Endpoint-nya masih
terdaftar dan masih menerima permintaan ⇒ sebaiknya dijadikan penolakan yang jelas (410/404 + pesan),
bukan endpoint yang "berhasil" tanpa efek.

---

## Urutan perbaikan yang diusulkan (alasan, bukan selera)

1. **F14 — SSOT lingkup toko.** Satu penerjemah `account_id` untuk SELURUH marketing +
   migrasi data lama + gate. Tanpa ini, semua perbaikan form di atasnya tetap menghasilkan
   baris yang tidak bisa difilter.
2. **F15 — Form pakai master (select), bukan teks bebas.** Termasuk pemilih item katalog
   (produk/SKU/ukuran/warna/HPP ikut terisi) dan pemilih kreator/host **yang di-assign ke toko itu**.
3. **F16 — Tutup CRUD yang tidak ada:** Ads, Live Session (+ performa host & sales), Order manual.
4. **F17 — Impor tanpa AI.** Pilih jenis data → pilih toko (→ pilih host/kreator bila relevan) →
   unduh template → auto-map heuristik (exact → sinonim → fuzzy) → mapping manual → pratinjau
   validasi → commit ke koleksi BENAR dengan `account_id` → rollback. AI jadi **tombol bantuan opsional**.
5. **F18 — Tutup lubang layar** yang berdampak uang & operasi (nota kredit retur, kalender shift,
   analitik live/ads, daftar acuan dari backend).
