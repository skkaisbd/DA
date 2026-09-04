# Proposal Perombakan Master Product, Varian/SKU, BOM & Material
CV Dewi Aditya ERP — Portal Produksi (Internal), Maklon, Marketing/Toko

Status: DRAFT untuk persetujuan user. Belum diimplementasikan.

---

## 1. AS-IS (kondisi sekarang) — hasil audit

### 1.1 Tiga "master product" terpisah & tidak konsisten

| Domain | Collection | Isi | Varian/SKU | Masalah |
|---|---|---|---|---|
| Produksi Internal | `rahaza_models` | header model (code, name, category, `yarn_kg_per_pcs`, bundle) | TIDAK ada master varian. SKU = `code-size` dibuat saat PO, warna & SKU **ketik bebas** | yarn-centric; SKU tidak masukkan warna → bentrok; input bebas rawan salah |
| Maklon | `dewi_maklon_buyer_catalog` | artikel per-buyer (harga cmt/jual, `color_options[]`, `size_options[]`) | Hanya **list opsi**, bukan varian ber-SKU | tidak ada SKU per varian; artikel tak bisa lintas buyer |
| Marketing/Toko | `marketing_catalog_items` | item jual online (sku, `variant_info` teks, `model_id` FK, stock) | 1 item = 1 SKU, tapi varian = teks bebas (`"Warna: Merah, Size: L"`) | varian tidak terstruktur; tak terhubung ke varian produksi |
| Legacy | `products` + `product_variants` | (KOSONG, tidak dipakai) | `product_variants` punya struktur SKU/size/color yang benar | mati/tidak dipakai |

### 1.2 Size & Warna
- `rahaza_sizes`: master GLOBAL (S/M/L/XL/XXL). OK.
- Warna: TIDAK ada master. Diketik bebas per item PO.

### 1.3 Material & BOM (yarn-centric)
- `rahaza_materials`: field `type` = `yarn|accessory`, plus `yarn_type`. **TIDAK ada field `category`.**
- `rahaza_boms`: `yarn_materials[]` + `accessory_materials[]` per (model_id, size_id). **Struktur yarn-centric.**

### 1.4 Pemakai collection (dampak perubahan — "ada banyak")
- **Produksi**: rahaza_production, production_pos, production_internal_adapter, rahaza_bom, rahaza_hpp, rahaza_reports, rahaza_sprint22, rahaza_sop, dewi_production_reports, operations_pdf.
- **Maklon**: dewi_maklon_buyer_catalog, dewi_maklon_pos, dewi_maklon_bom_templates, dewi_maklon_samples, production_pos.
- **Marketing/Toko**: marketing_catalog_items, marketing_catalog_mgmt, marketing_catalog_stock, marketing_toko_dashboard, _toko_adapter, dewi_rnd_hpp.
- **Material/WMS/Accessories**: dewi_accessories_*, rahaza_inventory_*, wms_*, warehouse, universal_scan, stock_service, fg_matrix_seed.
- **Frontend**: ProductionPOModule, RahazaModelsModule, RahazaBOMModuleV2, InlineMaterialPicker, RahazaMaterialsModule, AccessoryModule, MaklonBuyerCatalog*, MaklonPOModule, CatalogManagementModule, TokoProductCatalogModule, FGProductPickerDialog.

---

## 2. TO-BE (desain target)

### 2.1 Layer VARIAN + SKU unik (inti perbaikan)

**Prinsip:** Product = header (model/artikel). Varian = kombinasi **Warna × Size**, masing-masing punya **SKU unik**.

**Master baru:**
- `rahaza_colors` — master warna: `{id, code, name, hex, active}` (code dipakai di SKU).
- `rahaza_model_variants` — varian produk internal:
  `{id, model_id, size_id, size_code, color_id, color_name, color_code, sku(UNIQUE), barcode?, active}`
  - SKU otomatis: `{model.code}-{color_code}-{size_code}` (mis. `JKT-HD-BLK-M`). Dijaga unik via index.
  - Saat buat/edit model → user pilih daftar Warna & Size → sistem generate matriks varian + SKU otomatis.

**Perubahan PO:**
- Item PO Internal cukup pilih **1 Varian** (dropdown) → `size/color/sku` terisi otomatis dari master (HAPUS input bebas Size/Warna/SKU).

### 2.2 Generalisasi kategori Product (bukan sweater-only)
- Master `rahaza_product_categories`: Kaos, Kemeja, Polo, Jaket, Hoodie, Sweater, Celana, Rok, Dress, dll (configurable).
- `rahaza_models`: hapus/patch `yarn_kg_per_pcs` → satukan jadi atribut umum; pertahankan `fabric_type` (dari jalur RnD) sebagai standar. Samakan 2 jalur pembuatan (form manual & RnD) agar field seragam.

### 2.3 Material + Category (master) & BOM fabric-centric
- `rahaza_materials`: TAMBAH field **`category`** (master) — mis. Kain/Fabric, Benang, Aksesoris, Packaging, Benang Jahit, Interlining, dll. `type` tetap sebagai grup tinggi (fabric|yarn|accessory|packaging|other) + `category` sub-klasifikasi bebas dari master `rahaza_material_categories`.
- `rahaza_boms`: GANTI `yarn_materials[]`+`accessory_materials[]` → **`materials[]`** generik:
  `[{material_id, code, name, category, qty, unit}]` (dikelompokkan tampil per category). Menghapus hardcode yarn.
- Kompatibilitas: helper baca BOM (PDF, explode aksesoris, HPP) diarahkan ke `materials[]` (+ fallback baca struktur lama saat migrasi).

### 2.4 Maklon & Marketing selaras varian
- Maklon `dewi_maklon_buyer_catalog`: dari `color_options[]/size_options[]` → generate `variants[]` (embbeded) atau collection `dewi_maklon_catalog_variants` dengan `sku` per (artikel × warna × size).
- Marketing `marketing_catalog_items`: tambah `variant_id` (FK ke varian internal) agar stok Toko ↔ FG/varian produksi nyambung; `variant_info` teks dipertahankan utk display.

---

## 3. Migrasi data (aman, tanpa hapus data lama)
1. **Colors**: seed dari warna distinct yang pernah dipakai di `po_items.color`.
2. **Variants**: untuk tiap model, generate varian dari kombinasi size×color yang pernah dipakai (dari `po_items`), assign SKU. Model tanpa histori → user generate manual dari matriks.
3. **Materials.category**: default dari `type` (yarn→"Benang", accessory→"Aksesoris"); tambah kategori "Kain/Fabric".
4. **BOM**: konversi `yarn_materials`+`accessory_materials` → `materials[]` (set category sesuai asal). Simpan struktur lama sbagai `_legacy` sampai verifikasi.

---

## 4. Dampak & file yang berubah (ringkas)
- Backend: rahaza_production, rahaza_bom, rahaza_inventory_materials, production_pos, production_internal_adapter, operations_pdf, dewi_maklon_buyer_catalog, marketing_catalog_items, rahaza_hpp, reports.
- Frontend: RahazaModelsModule (+tab Varian), RahazaBOMModuleV2/InlineMaterialPicker, RahazaMaterialsModule (+category), ProductionPOModule (varian picker), MaklonBuyerCatalog*, CatalogManagementModule.
- Master baru: colors, model_variants, product_categories, material_categories.

---

## 5. Rencana bertahap (usulan)
- **Fase 1 — Material & BOM generalisasi**: tambah `category` (material) + kategori master; BOM `materials[]`; update BOM UI, PDF, HPP, explode aksesoris. (fondasi)
- **Fase 2 — Varian/SKU**: master colors + model_variants + generator SKU; tab Varian di RahazaModelsModule; PO Internal pakai varian picker.
- **Fase 3 — Maklon & Marketing**: varian katalog Maklon; link `variant_id` Marketing/Toko ↔ FG.
- **Fase 4 — Migrasi caller & laporan + bersihkan legacy** (products/product_variants).

Tiap fase: implement → uji (backend + UI nyata) → rebuild frontend → lapor.

---

## 6. KEPUTUSAN FINAL USER (disetujui)
1. **SKU varian** = `KODE-WARNA-SIZE` (mis. `JKT-HD-BLK-M`), dijaga unik.
   - Maklon menyimpan **2 kode**: `artikel_code` (kode kita, boleh otomatis) + `buyer_ref_code` (kode dari buyer, **tetap MANUAL**, tidak diubah sistem).
2. **Warna**: TANPA master collection. Pakai **palet warna standar (gaya techpack)** — konstanta {name, code, hex} yang dipilih dari dropdown (minimalisir input custom). Boleh ada opsi "Lainnya" seperlunya.
3. **Kategori material**: master `rahaza_material_categories` yang **configurable (bisa ditambah)**. Seed awal: Kain/Fabric, Benang, Aksesoris, Packaging, Benang Jahit, Interlining, Lainnya.
4. **BOM per Varian penuh** = key (model_id, size_id, **warna**). Kebutuhan kain bisa beda per warna.
5. **Urutan**: Fase 1 → 2 → 3 → 4.

### Catatan penyesuaian karena BOM per-varian
- BOM key jadi (model_id, size_id, color). `color` boleh kosong = berlaku untuk semua warna (fallback), spesifik menang atas umum.
- Palet warna dipakai konsisten di: matriks varian (Fase 2) & pemilihan warna BOM (Fase 1/2).
