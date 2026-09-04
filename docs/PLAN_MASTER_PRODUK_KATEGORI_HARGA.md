# 📐 RENCANA — MASTER KATEGORI PRODUK · HPP · HARGA JUAL (Master Produk Internal DA)

> Dibuat 2026-08-10 (Session #26) atas permintaan owner. **Status: RENCANA — belum dieksekusi.**
> Owner minta: *"fokus analisis dulu dan planing perbaikan termasuk semua endpoint api yang
> terpengaruh, saya rasa ini menyebabkan banyak error karena ada beberapa error logic"*.
>
> Baca dulu: `memory/AUDIT_MASTER_PRODUK_INTERNAL.md` (inventaris 33 field + 34 endpoint).
> Bukti: `python3 scripts/_prove_master_produk_logic_gaps.py` → **9/9 klaim TERBUKTI**
> (dijalankan sungguhan lewat HTTP, sisa jejak data uji **0**).

---

## 0) PERMINTAAN OWNER (verbatim, jangan ditafsir ulang tanpa konfirmasi)

1. *"yang ingin saya tambahkan adalah bisa jadi category tapi maknanya adalah misal **vest, rok,
   jacket**, dll … ini ingin saya jadikan menjadi **master model** lalu bukan hanya input value
   bebas — yang nanti ini **jadi SKU otomatis** juga."*
2. *"**harga jual & HPP** juga apakah belum ada? lalu jika tidak ada bagaimana bisa di marketing
   produksi dll berjalan? bukankah ini bisa menjadi **cacat logic**?"*
3. Kegunaan: *"untuk **filter & grouping** dan juga sebagai SKU, akan kepakai banyak di
   **marketing catalog product DA**."*
4. Produk hasil promosi R&D: **"Ya — isi otomatis dari data style R&D."**
5. Bug kode kembar: **"Ya, perbaiki sekarang + tambah gate supaya tidak balik lagi."**
6. Field mati: **"Justru hidupkan — tampilkan di layar; semuanya."**

---

## 1) JAWABAN LANGSUNG: "harga jual & HPP belum ada?"

**Bukan belum ada — ada, tapi separuh jalan.** Ini yang membuatnya terasa seperti cacat logika:

| Angka | Ada di mana | Masalahnya |
|---|---|---|
| **HPP rencana** | `dewi_rnd_hpp` (kalkulator R&D) → dipropagasi ke `rahaza_models.hpp` → FG `hpp` → `marketing_catalog_items.hpp` (`hpp_source: 'rnd'`) | **HANYA ada kalau produk lahir dari style R&D.** Produk yang dibuat manual di Master Produk **tidak punya HPP sama sekali**, dan **tidak ada kolom untuk mengisinya** |
| **HPP aktual** | `compute_hpp_job()` per job produksi (bahan dari MI job + upah) → `rahaza_hpp_snapshots` → posting WIP→FG | ✅ Sehat. **Produksi TIDAK bergantung pada HPP master** — jadi produksi tetap jalan |
| **Harga jual** | **HANYA** di item katalog marketing: `harga_jual` (+`harga_coret`, `harga_original`), diisi MANUAL per katalog/platform | **Tidak ada harga jual resmi di level produk.** Satu produk di 5 platform = 5 kali isi tangan, tidak ada yang bisa dibandingkan. `rahaza_models.retail_price` ADA tapi **hanya ditulis seeder & tidak pernah dibaca** (field mati) |

**Kesimpulan:** yang rusak bukan "tidak ada HPP", tapi **tidak ada sumber HPP & harga jual untuk
produk non-R&D**, padahal katalog marketing menghitung margin dari `hpp`. Terbukti: produk manual →
`FG.hpp = 0` → margin katalog mustahil dihitung (bukti **P1a/P1b**).

---

## 2) TEMUAN TERBUKTI (semua diuji, bukan dugaan)

| Kode | Temuan | Bukti |
|---|---|---|
| **P1a** | Produk manual lahir tanpa `hpp` & tanpa harga jual; form Master Produk tidak punya kolomnya | kunci tersimpan hanya 13, tanpa `hpp`/`retail_price` |
| **P1b** | FG dari produk manual lahir `hpp = 0` ⇒ margin katalog marketing mustahil | `FG.hpp = 0.0` |
| **P2a/P2b** | `category` **disalin** ke FG saat FG dibuat, dan **TIDAK PERNAH diperbarui**. Ubah kategori di master → FG & katalog tetap kategori LAMA selamanya | master `Vest` vs `FG 'Rok Lipit Sekolah'` |
| **P3** | `category` **teks bebas** — server menerima nilai di luar dropdown | tersimpan `'Rok Lipit Sekolah'` |
| **P4a/P4b** | `weight_gram` **DIBACA** `ensure_fg_material()` dari model tetapi **tidak pernah ditulis** ⇒ berat FG selalu 0 | `FG.weight_gram = 0.0` |
| **P5** | SKU = `{MODEL}-{WARNA}-{SIZE}` — kategori **tidak** ikut | `ZZPROVE-MP-PTH-S` |
| **T1** 🔴 | **Kode produk bisa kembar**: form manual menulis `active: True`, promosi R&D menulis `status: 'active'` (tanpa `active`); index unik `code` memakai `partialFilterExpression {active: true}` ⇒ produk promosi di luar index, dan pengecekan duplikat API memakai filter yang sama | `POST /api/rahaza/models` kode sama → **HTTP 200** (harusnya 409) ⇒ 2 master berkode sama; `GET /api/dashboard` hitung 1, `GET /api/rahaza/models` hitung 2 |
| **T2** | **4 kosakata kategori** yang tidak pernah bertemu: Master Produk `['Sweater','Cardigan','Vest','Polo','Other']` · Maklon Buyer Catalog `['Dress','Blouse','Rok','Celana','Set/Setelan','Baju Anak','Hijab','Aksesoris',…]` · Maklon AI Quote `['kaos','kemeja','hijab','celana','outerwear','general']` · seeder backend `'Sweater Rajut'` (tidak ada di daftar mana pun) | grep 4 berkas |
| **T3** | Katalog marketing: kategori adalah **input teks bebas** (`CatalogManagementModule.jsx:1225`), prefill dari FG ⇒ staf bisa menimpanya dengan apa saja ⇒ grouping tidak bisa dipercaya | — |
| **T4** | `rahaza_materials.category` **bermakna ganda**: untuk bahan = `Benang/Kancing/Zipper/Label/…`; untuk dokumen FG = kategori PRODUK (disalin dari model). Satu field, dua kamus | distinct DB |

**Kenapa ini "menyebabkan banyak error" seperti dugaan owner:** kategori dipakai untuk
**filter & grouping** di katalog marketing, tapi nilainya (a) tidak divalidasi, (b) tidak seragam
antar modul, (c) **basi** setelah diubah, dan (d) hidup di field yang juga dipakai kategori bahan.
Empat sebab berbeda yang semuanya bermuara pada satu gejala: *"angka/daftar di katalog tidak cocok
dengan master"*.

---

## 3) ⚠️ KEPUTUSAN YANG DIBUTUHKAN OWNER SEBELUM EKSEKUSI

### K-1 — Kategori masuk SKU: **PILIH SATU** (ini keputusan termahal)

SKU sekarang `{MODEL}-{WARNA}-{SIZE}` dan **dipakai sebagai identitas fisik**: `code` FG
(`rahaza_materials`), index **unik** `sku`, barcode, SKU katalog marketing, stok gudang, dan
gate **INV-RND-3** mengunci urutannya.

| Opsi | Cara | Akibat |
|---|---|---|
| **A (disarankan)** | Kategori punya **`sku_prefix`** (mis. `VST`). Saat membuat produk, `code` model **dibuat otomatis** `VST-0001` (counter atomik `utils/counters`). SKU tetap `{MODEL}-{WARNA}-{SIZE}` ⇒ hasilnya `VST-0001-NVY-M` — **kategori sudah kelihatan di SKU** | ✅ Nol migrasi SKU · nol perubahan format · gate INV-RND tetap hijau · grouping tetap lewat `category_id` |
| **B** | Tambah segmen kategori: `{KATEGORI}-{MODEL}-{WARNA}-{SIZE}` **hanya untuk produk baru** | ⚠️ Dua format hidup bersamaan; SKU lama tak bisa dibedakan dari yang baru tanpa melihat master |
| **C** | Ubah format + **migrasi SEMUA** SKU/FG code/barcode/SKU katalog | 🔴 Menyentuh stok & uang: FG code berubah ⇒ riwayat stok, GL, pesanan marketplace, barcode cetak. Butuh downtime + verifikasi berlapis |

> **Rekomendasi saya: A.** Owner ingin "jadi SKU otomatis" — opsi A memenuhinya tanpa
> menyentuh identitas barang yang sudah beredar.

### K-2 — Daftar kategori awal
Owner menyebut **vest, rok, jacket**. Mohon lengkapi (dengan kode/prefix SKU). Usulan awal —
**tolong koreksi**:

| Nama | Kode/prefix | | Nama | Kode/prefix |
|---|---|---|---|---|
| Sweater | SWT | | Rok | RSK |
| Cardigan | CRD | | Celana | CLN |
| Vest | VST | | Dress | DRS |
| Jacket | JKT | | Blouse | BLS |
| Polo | PLO | | Kemeja | KMJ |
| Kaos / T-Shirt | KAO | | Set/Setelan | SET |
| Hoodie | HDI | | Lainnya | OTH |

### K-3 — Harga jual: di level mana yang **resmi**?
- **a (disarankan)** `retail_price` di **master produk** = harga jual RESMI; katalog marketing
  memakainya sebagai **nilai awal** dan boleh menimpanya per platform (selisihnya ditampilkan).
- **b** Harga jual tetap **hanya** per katalog (seperti sekarang), master hanya menyimpan HPP.
- **c** Harga jual per **varian/SKU** (beda harga per size/warna).

### K-4 — Kategori Maklon (`dewi_maklon_buyer_catalog`) ikut disatukan?
- **a** Tidak — katalog maklon milik buyer, kosakatanya beda (aman, disarankan).
- **b** Ya — satu master kategori untuk internal **dan** maklon.

### K-5 — Kategori LAMA yang sudah tersimpan tapi di luar master
- **a (disarankan)** Migrasi memetakan yang cocok, sisanya **dibuatkan entri master otomatis**
  (ditandai `created_from: 'migrasi'`) — nol data hilang.
- **b** Paksa ke "Lainnya" (data asli hilang).

---

## 4) RANCANGAN (setelah K-1..K-5 dijawab)

### 4.1 Koleksi BARU `rahaza_product_categories`
`id · code (unik) · name · sku_prefix · order_seq · active · description · created_at · updated_at`
+ `created_from` (untuk entri hasil migrasi).

### 4.2 Field BARU/DIHIDUPKAN di `rahaza_models`

| Field | Isi | Kenapa |
|---|---|---|
| `category_id` | tautan ke master kategori (**kebenaran**) | filter/grouping yang tidak bisa salah tulis |
| `category_code`, `category_name` | denormalisasi untuk tampilan | hindari join di 34 pintu |
| `category` | **tetap** disinkronkan (= `category_name`) | 34 endpoint + FG + katalog sudah membacanya; jangan dipatahkan |
| `base_hpp` ♻️ | HPP dasar **manual** (dipakai bila tidak ada HPP R&D) | menutup P1a/P1b |
| `retail_price` ♻️ | harga jual resmi (jika K-3a) | menutup "harga jual tidak punya master" |
| `weight_gram` 🆕 | berat satuan (gram) | `ensure_fg_material()` **sudah** membacanya (P4) |
| `hpp`, `hpp_updated_at` ♻️ | ditampilkan di layar + sumbernya (`rnd`/`manual`) | owner minta dihidupkan |
| `techpack` ♻️ | ringkasan spesifikasi ditampilkan (read-only) | owner minta dihidupkan |
| `active` | **WAJIB** ditulis SEMUA penulis | menutup T1 |

### 4.3 Aturan yang dibuat EKSPLISIT (supaya tidak jadi tebakan berikutnya)
1. **Kategori divalidasi di server.** `category_id` tidak dikenal / tidak aktif ⇒ **400**, bukan
   diterima diam-diam (P3).
2. **Satu penulis stempel kategori**: helper `core/product_master.apply_category(doc, cat)` dipakai
   ketiga penulis (manual, promosi R&D, seeder) — pelajaran `close_job()` di FASE 5.
3. **Perubahan kategori DIPROPAGASI** ke FG + item katalog (pola `_propagate_hpp` yang sudah
   terbukti), menutup P2b. Propagasi hanya menyentuh dokumen yang tertaut `model_id`.
4. **Urutan resolusi HPP** (satu tempat): `model.hpp` (R&D) → `model.base_hpp` (manual) → `0`,
   dan **sumbernya ikut dilaporkan** (`hpp_source`) supaya layar tidak menampilkan angka tanpa asal.
5. **`weight_gram`** ikut dipropagasi ke FG seperti kategori.
6. **`active`** ditulis semua penulis; `status` **berhenti dipakai** sebagai penanda hidup/mati
   (tetap dibaca untuk dokumen lama).

---

## 5) SEMUA ENDPOINT & BERKAS YANG TERPENGARUH

### 5.1 BARU (4 endpoint)
| Endpoint | Guna |
|---|---|
| `GET /api/rahaza/product-categories` | daftar kategori (dipakai semua dropdown) |
| `POST /api/rahaza/product-categories` | tambah kategori |
| `PUT /api/rahaza/product-categories/{cid}` | ubah nama/prefix/urutan |
| `DELETE /api/rahaza/product-categories/{cid}` | non-aktifkan — **ditolak 409 bila masih dipakai produk** |

### 5.2 BACKEND yang DIUBAH

| Berkas · endpoint | Perubahan | Untuk |
|---|---|---|
| `routes/rahaza_production.py` · `POST /api/rahaza/models` | validasi `category_id`; isi denormalisasi; terima `base_hpp`/`retail_price`/`weight_gram`; **auto-generate `code`** dari `sku_prefix` (K-1A); cek duplikat **tanpa** bergantung `active` | K-1, P1, P3, P4, T1 |
| `routes/rahaza_production.py` · `PUT /api/rahaza/models/{mid}` | validasi kategori + **propagasi** kategori/berat/HPP ke FG & katalog | P2b |
| `routes/rahaza_production.py` · `DELETE /api/rahaza/models/{mid}` | tetap soft-delete, pastikan `active` konsisten | T1 |
| `routes/dewi_rnd_styles.py` · `POST /api/dewi/rnd/styles/{id}/promote-to-production` | map kategori style R&D → `category_id`; **tulis `active: True`**; isi `base_hpp`/`retail_price`/`weight_gram` dari R&D bila ada | owner #4, T1 |
| `utils/variant_ssot.py` · `_variant_linkage()` / `ensure_fg_material()` | bawa `category_id`/`category_code`; `hpp` pakai urutan resolusi baru; `weight_gram` benar-benar terisi | P1b, P2a, P4b |
| `routes/rahaza_variants.py` · `POST /models/{id}/variants/generate`, `POST /variants` | ikut lewat linkage (tanpa perubahan logika sendiri) | konsistensi |
| `routes/marketing_catalog_items.py` · `POST/PUT /api/marketing/catalogs/{cid}/items` | kategori diambil dari FG (`category_id`), **berhenti** menerima teks bebas; `harga_jual` default dari `retail_price` (K-3a) | T3, K-3 |
| `routes/marketing_catalog_items.py` · `GET …/items` | filter `category_id` (bukan `$regex` teks) | owner #3 |
| `routes/marketing_catalog_items.py` · `_resolve_rnd_hpp()` | tambah fallback `base_hpp` + `hpp_source: 'manual'` | P1b |
| `routes/dewi_rnd_hpp.py` · `_propagate_hpp()` | tetap; ditambah propagasi `retail_price` bila K-3a | K-3 |
| `routes/dashboard_routes.py` · `GET /api/dashboard` | hitungan produk berhenti bergantung `active: True` semata | T1 |
| `routes/rahaza_setup.py` · `POST /api/rahaza/setup/seed-sample` | lookup model tidak bergantung `active: True` | T1 |
| `routes/rahaza_admin_helpers.py` · `_seed_master_data()` | pakai master kategori + tulis `active` | T1, T2 |
| `server.py` (`create_indexes`) | index unik `rahaza_product_categories.code`; tinjau ulang `partialFilterExpression` pada `rahaza_models.code` | T1 |
| **BARU** `core/product_master.py` | SSOT: `apply_category()`, `resolve_hpp()`, `propagate_master_changes()` | aturan 2,3,4 |

### 5.3 FRONTEND yang DIUBAH
| Berkas | Perubahan |
|---|---|
| **BARU** `RahazaProductCategoriesModule.jsx` | CRUD master kategori + tab baru di `prod-master-product-hub` |
| `RahazaModelsModule.jsx` | **hapus `CATEGORIES` hardcode** → dropdown dari API; kolom & form baru: HPP dasar, harga jual, berat (gram); tampilkan `hpp` + `hpp_updated_at` + sumbernya + ringkasan `techpack`; filter/grouping per kategori |
| `CatalogManagementModule.jsx` | kategori jadi **dropdown/read-only dari FG** (hapus input bebas, T3); tampilkan HPP + sumbernya + margin; harga jual terisi awal dari master |
| `hubs/ProductionMasterProductHub.jsx` | tambah tab "Kategori Produk" |
| `MaklonBuyerCatalogModule.jsx` | **hanya jika K-4b** |

### 5.4 MIGRASI (idempoten, dry-run dulu — pola FASE 5)
| Skrip | Isi |
|---|---|
| `backend/migrations/seed_product_categories.py` | isi master kategori dari keputusan K-2 |
| `backend/migrations/backfill_model_category_id.py` | petakan `category` teks → `category_id`; nilai tak dikenal → buat entri master (`created_from='migrasi'`, K-5a); laporkan yang kosong, **jangan menebak** |
| `backend/migrations/normalize_model_active.py` | `active` diisi dari `status`/keberadaan dokumen (menutup T1); laporkan **kode kembar yang sudah ada** — WAJIB diselesaikan manusia, bukan otomatis |
| `backend/migrations/backfill_fg_from_model.py` | segarkan `category*`/`weight_gram`/`hpp` FG & katalog dari master (menyembuhkan data basi P2b) |

### 5.5 GATE BARU `INV-PRODUK` (`scripts/verify_master_produk.py`) — owner #5
| Kode | Invarian |
|---|---|
| PR-1 | `POST /api/rahaza/models` dengan `code` yang sudah ada ⇒ **409**, termasuk bila dokumen lama hanya punya `status` |
| PR-2 | **Nol** dokumen `rahaza_models` tanpa `active` (semua penulis menulisnya) |
| PR-3 | **Nol** `code` kembar di seluruh koleksi |
| PR-4 | `category_id` tak dikenal/non-aktif ⇒ **400** (bukan diterima) |
| PR-5 | Ubah kategori master ⇒ FG **dan** item katalog tertaut ikut berubah (P2b tidak boleh kembali) |
| PR-6 | Produk tanpa HPP R&D tetapi punya `base_hpp` ⇒ katalog memakainya, `hpp_source='manual'` |
| PR-7 | `weight_gram` master benar-benar sampai ke FG |
| PR-8 | Kategori yang masih dipakai produk **tidak bisa** dinonaktifkan (409) |
| PR-9 | `GET /api/dashboard` menghitung produk hasil promosi R&D (T1 tidak boleh kembali) |
| PR-10 | Format SKU tetap `{MODEL}-{WARNA}-{SIZE}` (K-1A) ⇒ INV-RND-3 tetap hijau |

---

## 6) URUTAN EKSEKUSI (tiap fase diakhiri gate + testing agent)

| Fase | Isi | Kenapa urutannya begini |
|---|---|---|
| **F0** | POC `test_core_master_produk.py`: master kategori → produk → varian → FG → katalog, buktikan kategori & HPP & berat mengalir dan **berubah saat master diubah** | Rantainya 5 lapis; kalau tidak dibuktikan lebih dulu, kegagalan baru terlihat di layar marketing |
| **F1** | **T1 (kode kembar)** + `normalize_model_active` + gate PR-1..PR-3, PR-9 | Bug uang/data yang sudah TERBUKTI; jangan menambah field di atas fondasi yang bocor |
| **F2** | Master kategori (koleksi + 4 endpoint + layar) + seed K-2 | Fondasi kategori |
| **F3** | `category_id` di model + validasi + **propagasi** + backfill + PR-4/PR-5 | Menutup P2b/P3 |
| **F4** | Kode otomatis dari `sku_prefix` (K-1A) + PR-10 | Permintaan "jadi SKU otomatis" |
| **F5** | HPP dasar + harga jual + berat + hidupkan field mati di layar + PR-6/PR-7 | Menutup P1/P4 & permintaan #6 |
| **F6** | Katalog marketing: dropdown kategori, filter `category_id`, HPP+sumber, margin | Tempat kategori "paling kepakai" |

---

## 7) RISIKO & YANG **TIDAK** DIKERJAKAN

* **Risiko terbesar** = mengubah format SKU (opsi K-1B/C). Menyentuh identitas fisik barang: FG
  code, barcode, stok, GL, pesanan marketplace. Karena itu K-1A yang disarankan.
* **Propagasi bisa "menghidupkan" data lama**: `backfill_fg_from_model` akan mengubah kategori FG
  yang selama ini basi. Itu memang tujuannya, tetapi **laporan lama yang di-grup per kategori bisa
  bergeser**. Harus dijalankan `--dry-run` dulu dan hasilnya ditunjukkan ke owner.
* **TIDAK dikerjakan tanpa permintaan**: menyatukan kategori Maklon (K-4), harga per varian (K-3c),
  mengubah `rahaza_materials.category` bermakna ganda (T4 — dicatat, perbaikannya terpisah karena
  menyentuh modul Bahan), dan menyentuh `products`/`product_variants` yang **DEPRECATED**.
* **UANG tidak boleh bergeser**: fase HPP/harga jual hanya menambah *sumber* angka baru untuk produk
  yang tadinya 0. Nilai HPP R&D yang sudah ada **tidak boleh berubah** — akan dijaga PR-6 + gate
  `round6_verify`/`verify_data_integrity` yang sudah ada.

---
---

# BAGIAN 8 — HUBUNGAN **MASTER DATA ↔ KATALOG MARKETING** (penelusuran lanjutan, 2026-08-10)

> Permintaan owner: *"telusuri lebih lanjut hubungan master data dengan catalog marketing, apakah
> ada cacat logikanya, bagaimana seharusnya bekerja, dan apakah ada gap saat ini — lalu tampung di
> plan."*
>
> Semua angka di bawah **dihitung dari data nyata di DB ini**, bukan dugaan.
>
> **Alat bukti (READ-ONLY — nol dokumen disentuh, aman dijalankan kapan pun):**
> ```bash
> python3 scripts/_prove_catalog_master_gaps.py     # → 10/10 klaim TERBUKTI
> ```

## 8.1 Bagaimana rantainya SEHARUSNYA bekerja

```
rahaza_models            → identitas PRODUK      (kode, nama, kategori, berat, HPP, harga jual resmi)
   └─ rahaza_model_variants → identitas JUAL terkecil = SKU (model × warna × size)
        └─ rahaza_materials(type='fg') → identitas STOK (1 SKU = 1 FG, code == sku)
             └─ rahaza_material_stock  → jumlah fisik per lokasi (+ reserved)
                  └─ marketing_catalog_items → PENYAJIAN per platform
                       └─ marketing_orders   → penjualan
                            └─ fulfillment   → alokasi/reservasi → pick → pack → kirim
```

**Prinsip yang seharusnya dipegang:**

1. **Katalog adalah PENYAJIAN, bukan sumber kebenaran.** Yang boleh dimiliki katalog sendiri hanya
   hal yang memang milik platform: harga platform, URL, foto promosi, deskripsi jualan, tag.
   Identitas (SKU, nama, kategori, berat) dan angka (HPP, stok) **milik master**.
2. **Satu definisi "stok yang bisa dijual"** dipakai SEMUA pintu: `tersedia = on-hand − reserved`
   pada lokasi yang boleh dijual. Kalau ada dua rumus, dua tombol akan menjawab beda dan tidak ada
   yang tahu mana yang benar.
3. **Kalau angka master disalin ke katalog (untuk kecepatan), salinan itu WAJIB punya penyegar
   otomatis** — atau layarnya wajib menandai "basi". Salinan tanpa penyegar = laporan yang
   berbohong dengan sopan.
4. **Order menyimpan TAUTAN ke barang** (`variant_id`/`fg_material_id`) pada saat dibuat, bukan
   dicocokkan ulang oleh manusia saat pengiriman.
5. **Barang yang dihentikan tidak boleh bisa dijual.** Menonaktifkan produk/varian harus terasa
   sampai ke katalog.

## 8.2 GAP yang ADA SEKARANG (semua dibuktikan)

### 🔴 M1 — "Stok katalog" punya **TIGA** definisi berbeda

| Pintu | Rumusnya | Lokasi | Reserved dikurangi? |
|---|---|---|---|
| `POST /api/marketing/catalogs/{cid}/items/from-fg` (saat item dibuat) | `qty` mentah | **HANYA 1** lokasi "default" = `rahaza_locations.find_one({'active': True})` | ❌ |
| `PUT /api/marketing/catalogs/{cid}/items/{id}/sync-fg-stock` | `on-hand − reserved` | **semua** lokasi | ✅ |
| `POST /api/marketing/catalogs/{cid}/sync-from-wms` (massal) | `qty` mentah | **semua** lokasi | ❌ |

**Bukti (dihitung dari 14 material yang punya stok di DB ini):**

> ⚠️ **Kejujuran data:** DB hasil restore ini **belum punya stok FG maupun item katalog**
> (`marketing_catalog_items` = 0, FG dengan stok = 0). Angka di bawah dihitung dengan
> **rumus yang sama persis** seperti ketiga endpoint itu, diterapkan pada baris
> `rahaza_material_stock` yang MEMANG ADA (aksesoris/benang). Jalur kodenya identik untuk FG —
> `rahaza_material_stock` tidak membedakan tipe material. Jadi yang dibuktikan di sini adalah
> **rumusnya berbeda**, bukan "kerugian yang sudah terjadi pada produk tertentu".

```
material            A: create(1 lokasi)   B: sync-fg-stock   C: sync-from-wms
ACC-BTN-12                         0.00            4999.00            5000.00
TEST-Q6-KAIN                       0.00             277.00             300.00
TEST-Q6-BTN                        0.00            4750.00            5000.00
… (14 dari 14 material BERBEDA antar-jalur)
```

### 🔴 M2 — Item katalog baru **selalu lahir stok 0**
"Lokasi default" = lokasi aktif **pertama** yang ditemukan (di DB ini: *Gedung Produksi*) — dan
lokasi itu tidak menyimpan stok jual. Terbukti: kolom A = **0.00 untuk SEMUA 14 material**.
Akibatnya produk baru tampak **habis** di katalog sampai ada staf menekan sync ⇒ kehilangan
penjualan tanpa ada pesan error.

### 🔴 M3 — `sync-from-wms` mengabaikan `reserved_quantity` ⇒ **OVERSELLING**
Stok katalog di-set lebih besar daripada yang benar-benar tersedia (contoh di atas: 5000 vs 4999,
300 vs 277, 5000 vs 4750). Barang yang sudah dipesan orang lain ikut ditawarkan lagi.

### 🟠 M4 — `sync-from-wms` melanggar SSOT skema stok
`core/stock_schema.py` menyatakan tegas: *"Semua READER jumlah fisik pakai `read_qty()`"* karena
koleksi `rahaza_material_stock` punya **3 skema historis** (`qty` / `total_qty` / `quantity`).
`sync-from-wms` membaca `s.get('qty', 0)` **langsung**. Saat ini semua 17 dokumen punya `qty`
(aman), tetapi satu writer yang lupa mirror `qty` akan membuat stok katalog **0 tanpa error**.

### 🟠 M5 — `sync-from-wms` melewati item yang tertaut lewat VARIAN
Filternya `{'material_id': {'$exists': True, '$ne': None}}`. Item yang ditautkan lewat
`variant_id`/`variant_sku` (jalur Fase 3b) **dilewati diam-diam** — kode sendiri menuliskannya:
*"Item tanpa material_id tidak terpengaruh"*. Staf menekan "Sinkron dari WMS", laporannya sukses,
tetapi sebagian item tidak ikut.

### 🔴 M6 — **Tidak ada sinkronisasi otomatis sama sekali**
* `utils/scheduler.py` → **nol** pekerjaan sinkron katalog.
* **Nol** berkas di `routes/wms_*.py` / `routes/rahaza_inventory*.py` / `core/` yang menyentuh
  `marketing_catalog_items`.

Artinya: barang masuk/keluar gudang **tidak pernah** mengubah stok katalog. Katalog basi sampai
ada manusia yang ingat menekan tombol. Ini akar M1–M3 menjadi kerugian nyata.

### 🟠 M7 — Snapshot master lain **tidak punya penyegar**
Yang punya penyegar hanya **HPP** (`refresh-hpp` + propagasi R&D) dan **stok** (manual). Sedangkan
`name`, `category`, `weight_gram`, `variant_info`, `images` **disalin sekali** saat item dibuat dan
tidak pernah diperbarui. Kategori sudah dibuktikan basi selamanya (**P2b**).

### 🟠 M8 — Produk yang **dihentikan tetap bisa dijual**
* `POST /items/from-fg` hanya memeriksa `type == 'fg'` — **tidak** memeriksa model/FG masih aktif.
* Menonaktifkan model (`DELETE /api/rahaza/models/{mid}`) atau varian **tidak menyentuh** item
  katalog (nol guard). Katalog tetap menawarkan barang yang sudah dihentikan.
* Bandingkan: jalur manual `POST /items` **sudah benar** (memvalidasi `model_id` & `variant_id`
  harus aktif). Jadi dua pintu masuk ke koleksi yang sama punya standar berbeda.

### 🔴 M9 — **Order marketing tidak tertaut ke master**
`marketing_orders` menyimpan `sku_id` sebagai **teks bebas** + `product_name` + `variation`, tanpa
`catalog_item_id`, `fg_material_id`, atau `variant_id`, dan **tanpa validasi** ke master.
Akibatnya `POST /api/fulfillment/orders/{id}/allocate` **mewajibkan manusia memilih
`material_id`** ("manual select dari rahaza_material_stock") ⇒ tautan order → barang dibuat ulang
dengan tangan setiap pesanan; salah pilih = stok salah turun.

### 🟠 M10 — Order **tidak memesan stok** saat dibuat
Reservasi baru terjadi di `allocate`. Jendela antara "pesanan masuk" dan "dialokasikan" membuat
stok yang sama bisa dijual dua kali.

### ⚠️ M11 — Sinkron ke marketplace **MOCK**
`routes/marketing_toko_sync_routes.py` → `_mock_sync_provider()` mengembalikan angka **acak**
(`mock: True`). `POST /api/marketing/toko-sync/{account_key}/sync` **tidak pernah** benar-benar
mengirim stok/harga ke Shopee/Tokopedia/TikTok. Ini **memang disengaja & berlabel**, tetapi harus
diketahui: memperbaiki M1–M6 membuat stok internal benar, **bukan** stok di marketplace.

## 8.3 KEPUTUSAN TAMBAHAN YANG DIBUTUHKAN OWNER

### K-6 — Lokasi mana yang stoknya "boleh dijual"?
Sekarang jawabannya berbeda-beda per pintu (1 lokasi / semua lokasi). Pilih satu:
- **a (disarankan)** Semua lokasi **kecuali** yang ditandai karantina/blokir — sudah ada field
  `blocked` & `quarantine` di `rahaza_material_stock`.
- **b** Hanya lokasi bertanda "gudang jual" (perlu field baru `sellable` di master lokasi).
- **c** Satu lokasi tunggal yang dipilih per katalog.

### K-7 — Stok katalog: hitung LIVE atau snapshot + penyegar otomatis?
- **a (disarankan)** **Hitung live** saat katalog dibaca (`available` dari FG), `stock_quantity`
  tetap disimpan hanya sebagai cache tampilan + penanda `in_sync`. Mustahil basi.
- **b** Tetap snapshot, tetapi tambahkan **hook** di setiap pergerakan stok FG + jadwal berkala.
- **c** Tetap manual seperti sekarang (tidak disarankan — ini akar M1–M6).

### K-8 — Order menyimpan tautan master?
- **a (disarankan)** `POST /api/marketing/orders` **wajib** membawa `catalog_item_id` (atau
  `variant_id`), server mengisi `fg_material_id` otomatis, dan `sku_id` yang tidak dikenal
  **ditolak 400**. Pesanan lama tetap dibaca (tautan opsional untuk dokumen lama).
- **b** Tautan opsional (hanya diisi bila ada) — memperbaiki sebagian, tanpa memaksa.
- **c** Biarkan; fulfillment tetap mencocokkan manual.

### K-9 — Produk dihentikan tetapi masih ada di katalog
- **a (disarankan)** Item katalog otomatis **dinonaktifkan** + staf diberi tahu (daftar terdampak).
- **b** Tetap aktif, hanya diberi badge "produk dihentikan".
- **c** Blokir penonaktifan produk selama masih dipakai katalog aktif (409).

## 8.4 TAMBAHAN ENDPOINT & BERKAS TERPENGARUH (di luar §5)

| Berkas · endpoint | Perubahan | Menutup |
|---|---|---|
| **BARU** `core/catalog_stock.py` | SSOT **satu** rumus stok jual (`sellable_stock(db, link)`) memakai `read_qty`/`read_reserved` + aturan K-6 | M1, M3, M4 |
| `routes/marketing_catalog_items.py` · `POST /{cid}/items/from-fg` | pakai SSOT stok (bukan 1 lokasi); tolak FG milik model non-aktif; simpan `variant_id` bila FG punya varian | M1, M2, M8 |
| `routes/marketing_catalog_items.py` · `PUT …/sync-fg-stock` | pakai SSOT yang sama | M1 |
| `routes/marketing_catalog_stock.py` · `POST /{cid}/sync-from-wms` | pakai SSOT; **ikutkan** item bertaut varian; kurangi reserved | M1, M3, M4, M5 |
| `routes/marketing_catalog_items.py` · `GET /{cid}/items` | sertakan `available` LIVE + `in_sync` (K-7a) | M6, M7 |
| **BARU** `POST /api/marketing/catalogs/{cid}/refresh-from-master` | segarkan `name`/`category*`/`weight_gram`/`variant_info` dari master (pasangan `refresh-hpp` yang sudah ada) | M7 |
| `core/product_master.propagate_master_changes()` (§4) | diperluas: kategori **dan** nama/berat ikut turun ke FG + katalog | M7, P2b |
| `routes/rahaza_production.py` · `DELETE /models/{mid}` · `routes/rahaza_variants.py` · `DELETE /variants/{vid}` | terapkan keputusan K-9 (nonaktifkan item katalog / tolak 409) | M8 |
| `routes/marketing_orders_routes.py` · `POST /api/marketing/orders` | terima & validasi `catalog_item_id`/`variant_id`; isi `fg_material_id`; `sku_id` tak dikenal → 400 (K-8a) | M9 |
| `routes/fulfillment.py` · `POST /orders/{id}/allocate` | **usulkan otomatis** `material_id` dari tautan order (manusia hanya mengonfirmasi) | M9 |
| `routes/marketing_orders_routes.py` · `PATCH /{order_id}/status` | reservasi stok saat order dikonfirmasi (K-8a) | M10 |
| `utils/scheduler.py` | (bila K-7b) jadwal sinkron stok katalog | M6 |
| FE `CatalogManagementModule.jsx` | tampilkan `available` LIVE + badge "stok basi/tidak tertaut"; tombol "Segarkan dari Master" | M1, M6, M7 |
| FE `MarketingOrders*.jsx` | pilih produk dari katalog (bukan ketik SKU bebas) | M9 |

## 8.5 GATE `INV-KATALOG` (usulan — pasangan `INV-PRODUK`)

| Kode | Invarian |
|---|---|
| KT-1 | **Satu rumus stok**: `from-fg`, `sync-fg-stock`, dan `sync-from-wms` menghasilkan angka **identik** untuk item yang sama |
| KT-2 | Item baru dari FG lahir dengan stok = stok jual sebenarnya (bukan 0) |
| KT-3 | Stok katalog **tidak boleh** > (`on-hand − reserved`) ⇒ overselling mustahil |
| KT-4 | Semua pembaca stok memakai `read_qty()`/`read_reserved()` (nol pembaca `qty` mentah) |
| KT-5 | `sync-from-wms` menyentuh **semua** item tertaut (termasuk yang lewat `variant_sku`) — nol item dilewati diam-diam |
| KT-6 | Ubah nama/kategori/berat di master ⇒ item katalog ikut berubah |
| KT-7 | FG dari model **non-aktif** tidak bisa ditambahkan ke katalog (400) |
| KT-8 | Menonaktifkan model/varian ⇒ item katalog mengikuti keputusan K-9 |
| KT-9 | `POST /api/marketing/orders` dengan SKU tak dikenal ⇒ **400**; order sah wajib punya tautan master |
| KT-10 | Nol item katalog **yatim** (menunjuk FG/varian yang sudah tidak ada) |

## 8.6 URUTAN EKSEKUSI TAMBAHAN

| Fase | Isi | Kenapa di sini |
|---|---|---|
| **F7** | `core/catalog_stock.py` (SSOT stok jual) + rapikan 3 pintu + KT-1..KT-5 | Overselling & stok 0 = kerugian uang langsung; paling mahal kalau dibiarkan |
| **F8** | Propagasi master → katalog (nama/kategori/berat) + `refresh-from-master` + KT-6..KT-8 | Menyambung F3/F5 (kategori & berat) sampai ke layar marketing |
| **F9** | Tautan order → master + reservasi saat konfirmasi + KT-9/KT-10 | Paling banyak menyentuh alur orang (butuh perubahan cara input) ⇒ paling akhir |

> **Catatan jujur:** F7–F9 menyentuh **stok dan uang**. Setiap fase wajib: POC isolasi dulu →
> gate `INV-KATALOG` → `verify_data_integrity` + `round6_verify` tetap hijau → testing agent.
> M11 (sinkron marketplace MOCK) **tidak** diperbaiki di sini — itu integrasi eksternal terpisah
> dan butuh kredensial marketplace dari owner.

