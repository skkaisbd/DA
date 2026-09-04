# Catatan kerja agen — jangan diulangi

## 2026-08-08 · Seed "lazy, hanya bila kosong" WAJIB dipasang di pintu TERBAWAH, bukan di endpoint daftar
`rahaza_colors` di-seed lazy hanya bila koleksinya kosong, tapi penyemaiannya dulu cuma ada di
`GET /api/rahaza/colors` dan `GET /api/dewi/rnd/color-options`. Pintu lain
(`utils.variant_ssot.ensure_color()` — dipakai importir Excel & promosi varian R&D → master)
tidak menyemai, jadi pemanggil pertama membuat warna **sampah** `{code:'NVY', name:'NVY',
hex:'#CCCCCC'}`. Koleksi jadi tidak-kosong ⇒ **palet asli tidak pernah ter-seed lagi**, dan
`'Navy'` belakangan dibuat sebagai kode KEDUA (`NAV`) ⇒ satu warna dua kode ⇒ deteksi varian
kembar lolos & SKU pecah. Gate `INV-RND-4` MERAH di DB bootstrap bersih karena ini.

Aturan: kalau ada seeder "hanya bila kosong", pasang di **fungsi get-or-create terbawah** yang
dipakai semua penulis — bukan di endpoint pembaca. Dan tetap pertahankan syarat "hanya bila
KOSONG" supaya data yang sengaja dihapus pengguna tidak dihidupkan kembali (uji ini eksplisit:
`INV-COLOR-6`).

## 2026-08-08 · JANGAN memanggil handler FastAPI langsung dari Python — nilai default `Query()` ikut terbawa
`size_mapping_auto` memanggil `size_mapping_overview(style_id=…, user=user)` sedangkan
tanda tangannya `limit: int = Query(500, ge=1, le=2000)`. Di luar request FastAPI, `limit`
berisi **objek `Query`**, bukan `int`, sehingga `.to_list(limit)` (motor) pecah — dan hanya
kelihatan saat endpoint `/auto` dipakai, tidak saat `/size-mapping` dipakai.

Aturan: taruh logikanya di **fungsi biasa** (`_overview(db, style_id, limit)`), lalu handler
hanya membungkusnya. Handler dipakai HTTP, fungsi biasa dipakai kode lain.

## 2026-08-08 · Dua sisi yang harus sepakat WAJIB memakai satu fungsi resolusi
Layar memakai `build_size_map()` (punya aturan pemadanan sendiri), promosi ke produksi memakai
`ensure_size(code=<label mentah>)`. Hasilnya: layar menampilkan `'All Size'` **"sudah
dipadankan → ALLSIZE"** sementara promosi tetap membuat ukuran master kembar `'ALL SIZE'`, dan
`'28/30'` menjadi kode master bergaris-miring yang bocor ke SKU FG (`STYLE-NVY-28/30`).

Aturan: kalau UI menjanjikan sesuatu tentang data, **jalur tulis harus memakai fungsi yang sama
persis** dengan yang dipakai UI untuk menjanjikannya. Sekarang keduanya memakai
`utils.variant_ssot.resolve_master_size()`. Bonus: kode master selalu dibersihkan jadi
alfanumerik (`norm_size_key`) supaya spasi/garis miring tidak pernah bocor ke SKU.

## 2026-08-08 · Layar "perbaiki data" harus membaca SEMUA sumber data, bukan cuma yang rapi
Draf pertama layar Padankan Ukuran hanya membaca `dewi_rnd_styles.size_list`. Padahal yang
benar-benar dipromosikan ke produksi adalah `dewi_rnd_variants.sizes`, dan importir Excel
menulis label yang **tidak ada di `size_list` mana pun** — terbukti: `ONESET` dan `TOP` (dari
115 varian impor) tidak akan pernah muncul di layar, jadi style hasil impor tetap mentok di PO
walau layarnya bilang "semua sudah dipadankan". Sekarang ringkasan membaca kedua sumber dan
menandai asalnya (`from_size_list` / `from_variants`).

## 2026-08-08 · POC dulu, fitur kemudian — POC menyelamatkan fitur ini dari jadi hiasan
`scripts/poc_rnd_size_promotion.py` ditulis SEBELUM fiturnya, memakai API sungguhan, dan
membuktikan 3 kerusakan (master ukuran kembar, satu ukuran dua kode, SKU FG kotor) + 1 temuan
tak terduga: berkas `dewi_rnd_size_mapping.py` sisa sesi lalu **tidak pernah di-import** di
`routes/dewi_rnd.py` ⇒ semua endpoint-nya HTTP 404. Tanpa POC, layarnya akan selesai dibuat dan
tampak jalan, tapi promosi tetap mencemari master. Simpan POC-nya (jangan dihapus) — ia jadi
bukti "sebelum vs sesudah" yang bisa dijalankan ulang siapa pun.

## 2026-08-08 · Clone segar: `yarn install` bisa DI-SKIP karena marker cache ikut tersalin
`scripts/bootstrap.sh` melewati `yarn install` bila `node_modules` ADA dan
`.bootstrap_cache/fe.md5` cocok — tetapi marker itu **ikut tersalin dari repo**, sedangkan
`node_modules` yang ada adalah bawaan template (belum berisi paket khas repo ini). Gejalanya
bukan error install melainkan **`yarn build` gagal**: `Module not found: Can't resolve
'@simplewebauthn/browser'`. Jalan keluar: `cd /app/frontend && yarn install` lalu
`bash scripts/rebuild_frontend.sh`.

## 2026-08-08 · Testing agent bisa "menghabiskan" data uji sebelum menguji UI-nya
iteration_36 menjalankan pengujian backend lebih dulu, termasuk
`POST /size-mapping/auto` yang memadankan SELURUH label. Saat lanjut ke UI, tabelnya sudah
kosong (keadaan all-clear) sehingga alur klik — padankan per baris, dropdown, pilih massal,
sekali-klik, dan peringatan saat "buat baru" dimatikan — **tidak pernah tersentuh**, padahal
laporannya "frontend 100%". Aturan: untuk fitur yang **mengubah** daftar kerja, minta agent
menguji UI LEBIH DULU (atau seed ulang di antara tahap), dan periksa sendiri daftar
`passed_tests`-nya — cocokkan dengan alur yang benar-benar Anda minta.


## 2026-08-05 · JANGAN kirim beberapa `search_replace` untuk FILE YANG SAMA dalam satu batch paralel
Gejala: tool melaporkan "Edit was successful" untuk semua panggilan, tetapi hanya
SEBAGIAN perubahan benar-benar ada di file (write terakhir menimpa hasil write
sebelumnya). Efek samping yang sempat terjadi:
- `rahaza_inventory_materials.py`: patch `gsm`/`width_cm` pada POST hilang (hanya PUT yang ada)
  → 9 assertion uji gagal padahal kodenya "sudah ditulis".
- `RnDMaterialsTab.jsx`: patch `openEdit` hilang + sisa potongan `);}` di akhir file
  → parsing error eslint.

Aturan: edit paralel hanya untuk file BERBEDA. Untuk beberapa perubahan pada satu file:
lakukan berurutan, atau tulis ulang file dengan `create_file overwrite=true`.
Selalu verifikasi dengan `grep -n` setelah batch edit.

## 2026-08-05 · Cakupan konversi satuan: `core.uom` ≠ `core.bom_uom`
`core/uom.py::factor_of` HANYA tahu kemasan resmi material (`uoms`/`pack_*`). Satuan sedimensi
global (gram↔kg, cm↔m, lusin↔pcs) dan kain m⇄kg (via gsm & lebar) hanya dikenal `core/bom_uom.py`.
Akibatnya titik masuk stok yang memakai `factor_of` menolak "gram"/"yard" padahal BOM & Costing
sudah lama bisa mengonversinya — dan dropdown satuan di layar akan menawarkan satuan yang server
tolak. Sejak sesi ini pakai **`core.bom_uom.factor_to_base(material, unit)`** (satu helper, melempar
`UomError` bila benar-benar tak bisa dikonversi) untuk SEMUA jalur stok, dan bangun dropdown dari
`GET /api/rahaza/materials/uom-options` supaya daftar di layar = kemampuan server.

## 2026-08-05 · `gen_prefixed_number` memakai kunci konfigurasi `<koleksi>.<field>`
Dua jenis dokumen yang menumpang SATU koleksi+field (mis. `rahaza_ar_invoices.invoice_number`
dipakai AR Finance `AR-…` DAN invoice maklon otomatis `INV-MKL-…`) akan saling menimpa formatnya.
Pakai parameter **`config_key=`** + entri registry dengan `collection`/`field` eksplisit
(`data/doc_number_registry.py::target_of`). Jangan membuat generator kedua.

## 2026-08-05 · Seeder demo membuat dokumen dispatch tanpa mutasi stok FG
`tests/seed_demo_produksi_maklon.py` menulis `buyer_shipments`/`buyer_shipment_items` LANGSUNG ke DB,
jadi INV-18 ("setiap dispatch sudah mengurangi stok FG") selalu MERAH di container segar. Penutupnya:
`scripts/repair_selisih_ssot.py --apply --topup-fg` (sudah dipanggil `seed_demo_all.sh`).
`--topup-fg` HANYA untuk data demo — pada data nyata owner, stok kurang = ada QC/dokumen yang belum
diselesaikan dan harus diperiksa manusia.

## 2026-08-07 · Uji UI: dropdown aplikasi ini BUKAN `<select>` native
`components/ui/smart-native-select.jsx` menggantikan hampir semua `<select>`. Playwright
`select_option()` gagal dengan *"Element is not a `<select>` element"*, dan
`page.eval_on_selector_all('[data-testid="X"] option')` mengembalikan **0** opsi — sehingga alur
UI apa pun yang memakai dropdown akan terlihat "tidak bisa diuji". Ini yang membuat testing agent
iteration_35 tidak menyelesaikan satu pun alur R&D.
Pola yang BENAR:
```
await page.click('[data-testid="X-trigger"]')
await page.click('[data-testid="X-list"] >> text=Navy (NVY)')   # atau X-option-<value>
```
Bila opsi ≥ 8 ada kotak cari `[data-testid="select-search-input"]` untuk memfilter dulu.

## 2026-08-07 · Awalan `data-testid` yang bertumpuk membuat selector palsu
`tp-size-col-del-0` ikut tertangkap oleh selector `[data-testid^="tp-size-col-"]`, sehingga
daftar label kolom terbaca `['S','','M','','L','']` (nilai tombol hapus ikut masuk) dan
`cols.index('XL')` menunjuk indeks yang salah. Jangan membuat testid tombol sebagai *awalan
diperpanjang* dari testid field-nya — pakai kata lain (`tp-size-coldel-0`), atau saring dengan
`input[data-testid^="..."]`.

## 2026-08-07 · Kalau klien boleh mengirim balik "nilai cadangan", normalizer WAJIB menerimanya
`utils/rnd_techpack.normalize_measurements()` versi pertama hanya membaca `values` /
`values_legacy` / baris pipih — `orphan_values` (nilai kolom ukuran yang sudah dihapus) yang
dikirim balik frontend **dibuang**. Efeknya berbahaya dan senyap: nilainya bertahan pada satu
penyimpanan, lalu HILANG pada penyimpanan berikutnya. Ditemukan oleh gate INV-RND-2, bukan oleh
mata. Aturan: setiap field "cadangan/riwayat" yang dikirim ke klien harus ikut dibaca kembali
saat menyimpan, dan jumlah nilai sebelum/sesudah harus dihitung (`values_in`/`values_out`)
supaya gate bisa membuktikannya.

## 2026-08-07 · Field yang sama bisa berarti dua hal di dua layar (`color_code`)
SSOT (`utils/variant_ssot.py`) memakai `color_code` = **KODE** warna master (`NVY`), tetapi layar
R&D lama menulis **HEX** ke field yang sama (`color_code: '#ffffff'`). Karena
`promote_rnd_variants_to_master()` meneruskan nilai itu sebagai `code`, master warna yang dipakai
produksi & gudang bisa terisi kode sampah `#1B2A5B`. Sebelum memakai ulang sebuah field lintas
modul, periksa APA yang benar-benar ditulis layarnya — jangan percaya namanya. Penutupnya:
tulis dua field eksplisit (`color_code` KODE + `color_hex` HEX) dan tolak hex sebagai kode.

## 2026-08-07 · Data uji harus punya kunci yang benar-benar unik antar-run
`scripts/verify_rnd_f1_f4.py` memakai kode warna `VT` + 2 digit terakhir epoch ⇒ bentrok pada
run berikutnya ⇒ `POST /color-options` kena 409 dan SELURUH rangkaian F1 gagal berantai
(terlihat sebagai "34/39" yang membingungkan). Pakai UUID pendek, dan sediakan skrip pembersih
(`scripts/cleanup_rnd_test_data.py`, punya `--dry`) supaya data uji tidak menumpuk di DB demo.

## 2026-08-07 · `dewi_rnd_variants.sizes` punya DUA bentuk di database yang sama
Importir Excel (`routes/dewi_rnd_techpack_import.py`) menulis `sizes` sebagai daftar **STRING**
(`['S','M','L']`); layar Varian menulis daftar **DICT** (`[{size, sku, qty_plan}]`).
`utils/variant_ssot.promote_rnd_variants_to_master` sudah lama menangani keduanya, jadi tidak ada
yang sadar. Pembaca baru yang mengasumsikan dict akan **500 pada data sungguhan** (terjadi di
`sku-audit`), dan filter frontend `s.qty_plan > 0 || s.sku` membuat 115 varian hasil impor
**tidak menampilkan ukuran sama sekali**. Pakai helper `size_rows()` (BE) /
`sizeRows()` (FE). Pelajaran umum: **uji fitur baru terhadap data hasil importir, bukan hanya
data yang dibuat lewat UI/endpoint** — endpoint menormalkan input, importir tidak.

## 2026-08-07 · Importir yang menulis LANGSUNG ke DB melewati semua normalizer endpoint
`dewi_rnd_techpack_import.py` memakai `insert_one` sendiri, bukan `POST /tech-packs`. Setiap
aturan bentuk data baru (di sini: `size_columns` ber-`col_id`) harus ditambahkan **di dua tempat**.
Saat membuat normalizer, `grep` dulu semua penulis koleksi itu
(`grep -rn "dewi_rnd_tech_packs.insert\|update_one" backend/`).
