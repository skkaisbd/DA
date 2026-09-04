# 🧾 AUDIT — MASTER DATA PRODUK INTERNAL DA

> Dibuat 2026-08-10 (Session #26) **sebelum** menambah field baru, atas permintaan owner:
> *"field apa saja yang ada di masterdata DA dan field ini dipakai ke API endpoint apa saja"*.
>
> **Alat (jalankan ulang kapan pun — jangan percaya angka dokumen ini kalau kode sudah berubah):**
> ```bash
> python3 scripts/audit_master_produk_internal.py                       # semua koleksi
> python3 scripts/audit_master_produk_internal.py --collection rahaza_models
> python3 scripts/audit_master_produk_internal.py --field bundle_size    # rincian 1 field
> python3 scripts/audit_master_produk_internal.py --json memory/AUDIT_MASTER_PRODUK_FIELDS.json
> ```
> Data mentah: `memory/AUDIT_MASTER_PRODUK_FIELDS.json`.

---

## 0) KENAPA JAWABANNYA TIDAK BOLEH DIAMBIL DARI DATABASE

Saat audit ini dibuat, `rahaza_models` di DB hanya punya **9 kunci**, padahal **kode menulis 33**.
Kalau daftar field diambil dari DB, 24 field yang sudah ada di kode akan tampak "tidak ada" —
lalu field baru ditambahkan di atas peta yang salah. Sebaliknya, dokumen WARISAN bisa punya kunci
yang penulisannya sudah dihentikan (alias `yarn_*`, FASE 11). Jadi setiap field di bawah ditandai
sumbernya: **KODE** (ditulis kode, belum tentu ada di DB) · **DB-saja** (ada di dokumen, tidak
ditulis kode lagi = warisan) · **KEDUANYA**.

---

## 1) PETA KOLEKSI — mana yang SSOT, mana yang sudah mati

| Koleksi | Peran | Status |
|---|---|---|
| **`rahaza_models`** | **MASTER PRODUK INTERNAL** (model/artikel) | ✅ **SSOT** |
| **`rahaza_model_variants`** | **VARIAN = SKU** per (model × warna × size) | ✅ SSOT |
| `rahaza_sizes` | sumbu **SIZE** | ✅ SSOT |
| `rahaza_colors` | sumbu **WARNA** (palet master) | ✅ SSOT |
| `rahaza_boms` | **BOM/resep bahan** per (model × size × color) | ✅ SSOT |
| `rahaza_materials` (`type='fg'`) | **FG** hasil turunan varian (stok & HPP) | ✅ SSOT (dibuat otomatis) |
| `products` · `product_variants` | master produk **LEGACY** | 🔴 **DEPRECATED** |
| `dewi_maklon_buyer_catalog` | katalog produk **MAKLON** (milik buyer) | ✅ SSOT — jalur berbeda |

**`/api/products/*` dan `/api/product-variants/*` sudah DEPRECATED** (`routes/master_data.py:255`
mencetak peringatan deprecation saat start). Diverifikasi: **frontend sudah tidak memanggilnya**
sama sekali. **Jangan menambah field ke sana** — tidak akan pernah terlihat pengguna.

Layar-nya: Portal Produksi → **Master Produk** (`prod-master-product-hub`) → tab **"Produk & BOM"**
(`RahazaModelsAndBOMModule` → `RahazaModelsModule`).

---

## 2) `rahaza_models` — 33 field, dikelompokkan menurut SIAPA yang menulisnya

### 2a. Ditulis form MANUAL — `POST /api/rahaza/models` (dan `PUT /api/rahaza/models/{mid}`)

| Field | Ada di form UI? | Dibaca oleh |
|---|---|---|
| `code` | ✅ `model-form-code` | 14 titik baca (kunci pencarian di mana-mana) |
| `name` | ✅ `model-form-name` | 8 titik |
| `category` | ✅ `model-form-category` (dropdown) | tampil di tabel; tidak dipakai logika |
| `bundle_size` | ✅ `model-form-bundle-size` (default **30**) | **tidak ada pembaca di luar master** ⚠️ |
| `material_kg_per_pcs` | ✅ (label "Bahan utama/pcs (kg)") | **tidak ada pembaca** ⚠️ — BOM menghitung `total_material_kg_per_pcs` sendiri |
| `description` | ✅ `model-form-description` | tampil saja |
| `active` | ⛔ (otomatis `True`) | **7 titik filter** — lihat §5 TEMUAN-1 |
| `sop_steps[]` | via dialog Panduan Produksi | panduan produksi job & vendor |
| `reference_videos[]` | via dialog Panduan Produksi | panduan produksi |
| `reference_images[]` | via dialog Panduan Produksi | panduan produksi |
| `created_at` / `updated_at` | ⛔ | urut & jejak |

### 2b. Ditulis PROMOSI R&D — `POST /api/dewi/rnd/styles/{style_id}/promote-to-production`

Field **tambahan** yang TIDAK pernah dibuat jalur manual:

| Field | Isi | Ada di form UI? | Dibaca oleh |
|---|---|---|---|
| `status: 'active'` | ⚠️ **bukan** `active` | ⛔ | — (lihat TEMUAN-1) |
| `fabric_type` | dari style R&D | ⛔ | 2 berkas FE |
| `rnd_style_id` / `rnd_style_code` | tautan ke style R&D | ⛔ | `rnd_style_id` dibaca propagasi HPP |
| `image_paths[]` | foto desain R&D | (tampil) | panduan produksi, PDF operasi |
| `techpack{}` | snapshot spec (bom_items, measurements, stitch_type, seam_allowance_mm, size_range, base_size) | ⛔ | **tidak ada pembaca** ⚠️ |
| `sop_updated_at` / `sop_updated_by` | jejak SOP | ⛔ | tampil di dialog SOP |
| `created_by` / `created_by_name` | jejak | ⛔ | — |

### 2c. Ditulis jalur lain

| Field | Penulis | Dibaca? |
|---|---|---|
| `image_paths[]` | `POST` / `DELETE /api/rahaza/models/{mid}/images` | ✅ panduan produksi + PDF |
| `sop_steps[].image_path` | `POST /api/rahaza/models/{mid}/sop-image` | ✅ |
| `hpp`, `hpp_updated_at` | propagasi HPP R&D (`_propagate_hpp`, dipicu `POST/PUT /api/dewi/rnd/hpp-calculator`) | `hpp` dipakai katalog marketing; `hpp_updated_at` **tidak dibaca** |
| `base_hpp`, `retail_price` | **hanya** seeder `_seed_master_data` (`rahaza_admin_helpers.py:216`) | 🔴 **NOL pembaca, NOL layar** = field mati |
| `active: False` | `DELETE /api/rahaza/models/{mid}` (soft-delete) | ✅ |
| `style_code`, `style_name`, `design_images` | jalur R&D lain / seeder | tampil di layar R&D, bukan master produk |

### 2d. 34 endpoint NYATA yang menyentuh `rahaza_models`

**Master (CRUD):** `GET/POST /api/rahaza/models` · `PUT/DELETE /api/rahaza/models/{mid}` ·
`POST/DELETE /api/rahaza/models/{mid}/images` · `PUT /api/rahaza/models/{mid}/sop` ·
`POST /api/rahaza/models/{mid}/sop-image`

**Turunan produk:** `GET/POST /api/rahaza/models/{model_id}/variants*` · `POST /api/rahaza/variants` ·
`DELETE /api/rahaza/colors/{cid}` · `GET /api/rahaza/models/{model_id}/bom` · `POST /api/rahaza/boms` ·
`GET /api/rahaza/bom-uom-audit` · `POST /api/rahaza/material-requirements` · `POST /api/rahaza/sop`

**Konsumen lintas modul:** `GET /api/dashboard` · `GET /api/production-jobs/{jid}/production-guide` ·
`GET /api/vendor-portal/my-jobs/{job_id}/production-guide` · `POST/PUT /api/vendor-portal/jobs*` ·
`GET /api/rahaza/orders/{oid}` · `GET /api/rahaza/supervisor/line-balance` ·
`GET /api/dewi/reports/production/po/{po_id}/export.{csv,xlsx}` ·
`POST/PUT /api/marketing/catalogs/{catalog_id}/items*` · `POST /api/production-variances/{vid}/post-gl` ·
`POST /api/analytics/ai/qc/rca` · `POST /api/rahaza/shipments/{sid}/status` ·
`POST /api/rahaza/setup/seed-sample` · `POST /api/dewi/rnd/styles/{style_id}/promote-to-production`

> Artinya: **satu field baru di `rahaza_models` berpotensi terlihat di 34 pintu.** Itu kekuatan
> (sekali tulis, dipakai di mana-mana) sekaligus alasan kenapa penambahan field harus disengaja.

---

## 3) `rahaza_model_variants` (SKU) — 22 field

`id` · `model_id` · `model_code` · `model_name` · `size_id` · `size_code` · `color_id` ·
`color_code` · `color_name` · `color_hex` · **`sku`** · `barcode` · `notes` · `active` ·
`created_at` · `updated_at`.

* SKU dibentuk `_make_sku(model.code, color.code, size.code)` — **urutan `{STYLE}-{COLOR}-{SIZE}`
  adalah SSOT** (gate INV-RND menjaganya; pernah terbalik dan membuat SKU R&D tak pernah cocok SKU FG).
* Index unik: **`sku`** dan **(`model_id`,`size_id`,`color_id`)** ⇒ kombinasi tidak bisa kembar.
* Tiap varian otomatis melahirkan **FG** (`rahaza_materials type='fg'`, `code == sku`) lewat
  `ensure_fg_material()`.
* Endpoint: `GET /api/rahaza/variants` · `GET /api/rahaza/models/{model_id}/variants` ·
  `POST /api/rahaza/models/{model_id}/variants/generate` (matriks warna × size, idempoten) ·
  `POST /api/rahaza/variants` · `PUT/DELETE /api/rahaza/variants/{vid}`.

## 4) Sumbu & resep

| Koleksi | Field | Catatan |
|---|---|---|
| `rahaza_sizes` | `code` `name` `order_seq` `active` `aliases[]` `rnd_size_mapping` `created_from*` | `aliases`/`rnd_size_mapping`/`created_from*` **LAYAR 0** (khusus alat Padankan Ukuran) |
| `rahaza_colors` | `code` `name` `hex` `order_seq` `active` `created_from` | palet 15 warna dijaga gate **INV-COLOR** |
| `rahaza_boms` | `model_id` `size_id` `color` `version` `materials[]` (`material_id` `qty` `unit` `material_type` `category_name`) `active` `is_active` `notes` | **`active` ≠ `is_active`**: `active` = belum dihapus, `is_active` = versi yang berlaku. Sengaja, tapi mudah tertukar |

---

## 5) TEMUAN — dibuktikan, bukan dugaan

> **Semua klaim di bagian ini bisa dijalankan ulang:**
> `python3 scripts/_prove_master_produk_logic_gaps.py` → **9/9 TERBUKTI**, sisa jejak data uji **0**.
> Rencana perbaikannya: **`docs/PLAN_MASTER_PRODUK_KATEGORI_HARGA.md`**.

| Kode | Temuan | Bukti ringkas |
|---|---|---|
| **P1a** | Produk **manual** lahir tanpa `hpp` & tanpa harga jual — dan form Master Produk tidak punya kolomnya | 13 kunci tersimpan, tanpa `hpp`/`retail_price` |
| **P1b** | FG dari produk manual lahir `hpp = 0` ⇒ **margin katalog marketing mustahil dihitung** | `FG.hpp = 0.0` |
| **P2a/P2b** | `category` **disalin** ke FG saat FG dibuat dan **TIDAK PERNAH diperbarui** ⇒ ubah kategori di master, FG & katalog tetap nilai LAMA selamanya | master `Vest` vs `FG 'Rok Lipit Sekolah'` |
| **P3** | `category` **teks bebas** — server menerima nilai di luar dropdown | tersimpan `'Rok Lipit Sekolah'` |
| **P4a/P4b** | `weight_gram` **DIBACA** `ensure_fg_material()` dari model tetapi **tidak pernah ditulis** siapa pun ⇒ berat FG selalu 0 | `FG.weight_gram = 0.0` |
| **P5** | SKU = `{MODEL}-{WARNA}-{SIZE}`; kategori **tidak** ikut di SKU | `ZZPROVE-MP-PTH-S` |
| **T2** | **4 kosakata kategori** yang tidak pernah bertemu (Master Produk · Maklon Buyer Catalog · Maklon AI Quote · seeder `'Sweater Rajut'`) | 4 berkas |
| **T3** | Katalog marketing: kategori = **input teks bebas** (`CatalogManagementModule.jsx:1225`) ⇒ grouping tak bisa dipercaya | — |
| **T4** | `rahaza_materials.category` **bermakna ganda**: bahan = `Benang/Kancing/Zipper/…`, dokumen FG = kategori PRODUK | distinct DB |

### 🔴 TEMUAN-1 — `active` vs `status`: dua penulis master tidak sepakat ⇒ **KODE PRODUK BISA KEMBAR**

* `POST /api/rahaza/models` menulis **`active: True`** (tanpa `status`).
* `POST /api/dewi/rnd/styles/{id}/promote-to-production` menulis **`status: 'active'`** (tanpa `active`).
* Index unik `rahaza_models.code` memakai **`partialFilterExpression: {active: True}`**
  (`server.py:370`) ⇒ dokumen hasil promosi **tidak masuk index** ⇒ kode kembar lolos.
* Pemeriksaan duplikat di API juga memakai `find_one({code, active: True})`
  (`rahaza_production.py:100`) ⇒ ikut tidak melihatnya.

**Bukti empiris (dijalankan, lalu dibersihkan — sisa jejak 0):**

```
DB sementara: dua dokumen active:True  + code kembar -> DITOLAK (DuplicateKeyError)  = index bekerja
DB sementara: dua dokumen TANPA active + code kembar -> DITERIMA                     << lubangnya
DB aplikasi : model "hasil promote" (status:active, tanpa active) + POST /api/rahaza/models
              dengan code SAMA          -> HTTP 200 (seharusnya 409) ⇒ 2 master berkode sama
              count active:True = 1  (yang dilihat GET /api/dashboard)
              count semua      = 2  (yang dilihat GET /api/rahaza/models)
```

**Akibat lanjutan:** `GET /api/dashboard` (`'garments'`/`'products'` = `count({active: True})`)
**tidak menghitung** produk hasil promosi R&D, dan `POST /api/rahaza/setup/seed-sample`
(`{code, active: True}`) tidak menemukannya.

### 🟠 TEMUAN-2 — field mati (ditulis, tidak pernah dibaca, tidak pernah tampil)
`base_hpp`, `retail_price` (hanya dari seeder), `hpp_updated_at`, `techpack{}` (snapshot besar,
nol pembaca), `bundle_size` & `material_kg_per_pcs` (ada di form, nol pembaca di luar master).
Sebelum menambah field baru, ini contoh nyata biaya "field yang tidak punya konsumen".

### 🟠 TEMUAN-3 — dua penulis, dua kumpulan field
Produk **manual** tidak punya `fabric_type`/`techpack`/`image_paths`; produk **hasil promosi**
tidak punya `material_kg_per_pcs`/`bundle_size`/`reference_videos`. Layar & laporan harus selalu
memakai fallback, dan tidak ada satu tempat pun yang mendefinisikan "bentuk sah master produk".

### 🟡 TEMUAN-4 — dua nama untuk satu makna
`rahaza_boms.active` vs `is_active` (sengaja berbeda makna, tetapi namanya nyaris sama);
`rahaza_models.hpp` vs `base_hpp` (yang kedua mati).

---

## 6) ATURAN SEBELUM MENAMBAH FIELD BARU (dipakai sesi berikutnya)

1. **Tentukan pembacanya DULU.** Kalau tidak ada endpoint/layar yang akan membacanya, jangan
   ditambahkan — lihat TEMUAN-2.
2. **Tulis di KEDUA penulis** (`POST /api/rahaza/models` **dan**
   `promote-to-production`), atau sadari bahwa produk hasil promosi tidak akan punya field itu.
3. **Nama snake_case huruf kecil**, hindari kembar dengan `active`/`is_active`/`status`.
4. **Tampilkan di form** `RahazaModelsModule.jsx` (`DEFAULT_FORM` + input + kolom tabel) —
   field backend tanpa layar = fitur mati.
5. **Dokumen lama tidak punya field itu** ⇒ semua pembaca WAJIB punya default; jangan pakai
   `{'field': X}` sebagai filter tanpa `$exists`/`$ne`.
6. **Jalankan ulang** `scripts/audit_master_produk_internal.py` sesudahnya dan pastikan kolom
   LAYAR-nya tidak 0.
