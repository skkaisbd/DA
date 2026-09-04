# PROPOSAL PERBAIKAN R&D — Warna Multi, Ukuran Customizeable, Tech Pack, HPP Hybrid

> ## ✅ STATUS: **SUDAH DIEKSEKUSI SELURUHNYA (F1–F4)** — 2026-08-07 (lanjutan #3)
>
> Owner menjawab **"jalankan rekomendasi"**, jadi semua pertanyaan terbuka di **§7** diambil
> sesuai rekomendasi agent dan **tidak perlu ditanyakan lagi**:
>
> | §7 | Keputusan final |
> |---|---|
> | 1. Pemadanan ukuran | **B1** — bebas + padan otomatis bila nama sama, sisanya ditandai "belum dipadankan" |
> | 2. Override harga master | **D1** — boleh, **alasan WAJIB**, tercatat |
> | 3. Urutan fase | **F1 → F2 → F3 → F4** (sesuai usulan §6) |
> | 4. Tech Pack | **UI dan data**, keduanya (C1–C5) |
> | 5. Warna material R&D | **ikut di F1** |
>
> **Bukti:** `bash scripts/gate.sh` **14/14 HIJAU** (termasuk gate baru **INV-RND**) ·
> `scripts/verify_rnd_f1_f4.py` **39/39** · `scripts/verify_rnd_invariants.py` **9/9** ·
> verifikasi UI lewat browser **25/25**.
> **Rincian pengerjaan:** `plan.md` dan entri teratas `memory/CHANGELOG.md`.
>
> Dokumen ini **dipertahankan sebagai catatan analisis & alasan keputusan** — semua bukti
> `file:line` di bawah menggambarkan kondisi **SEBELUM** perbaikan, jadi jangan dipakai sebagai
> gambaran kode saat ini. Satu jebakan tambahan yang ditemukan **saat eksekusi** dan TIDAK ada di
> dokumen ini: layar R&D lama menulis **HEX** ke field `color_code`, padahal SSOT memakainya
> sebagai **KODE** warna — akibatnya `promote_rnd_variants_to_master()` bisa membuat warna master
> berkode `#1B2A5B`. Sudah ditutup (`color_code` = KODE, `color_hex` = HEX).

---

## 0) Keputusan owner yang sudah pasti

| # | Permintaan | Keputusan owner |
|---|---|---|
| 1 | Warna bahan bisa lebih dari satu | **Modal "Tambah Varian" (Gambar 1) harus bisa menyimpan LEBIH DARI SATU warna** dalam sekali input |
| 2 | Sumber warna | **Pilih dari master `rahaza_colors` DAN bisa menambah warna baru langsung dari layar R&D** — supaya tidak bolak-balik antar menu |
| 3 | Ukuran customizeable | **Tetap bebas per techpack/style; TIDAK dikunci ke master `rahaza_sizes`** |
| 4 | Edit HPP dari master + custom | Perlu; bentuk detail & kebijakan override **masih menunggu keputusan** (lihat §7) |
| 5 | Urutan pengerjaan | **Masih menunggu keputusan** (usulan saya di §6) |

---

## 1) Akar masalah: R&D adalah PULAU yang terpisah dari master data

ERP ini sudah punya SSOT warna & ukuran yang dipakai produksi, gudang, dan marketing.
R&D **tidak pernah** menyentuhnya:

| Master yang sudah ada | Endpoint | Dipakai R&D? |
|---|---|---|
| `rahaza_colors` `{id, code, name, hex, order_seq, active}` | `GET/POST/PUT/DELETE /api/rahaza/colors` (`rahaza_variants.py:85-153`) | ❌ tidak pernah |
| `rahaza_sizes` | `GET/POST/PUT/DELETE /api/rahaza/sizes` (`rahaza_production.py:346-395`) | ❌ tidak pernah |
| `rahaza_model_variants` = model × warna × ukuran → SKU kanonik | `utils/variant_ssot.py` | ❌ tidak pernah |
| `rahaza_materials` (punya field `color`) | `rahaza_inventory_materials.py:166` | hanya lewat `material_id` di BOM |

**Akibat yang bisa diukur:** PO produksi internal **MENOLAK** item yang `size_id`-nya tidak sah
(`production_internal_adapter.py:53-56` → HTTP 400), sedangkan R&D menyimpan ukuran sebagai
**teks bebas**. Jadi hasil kerja R&D tidak bisa mengalir ke produksi tanpa entri ulang manual.

---

## 2) Temuan per permintaan (dengan bukti `file:line`)

### 2.1 Warna — bukan "hanya satu", melainkan **campur aduk & sebagian tidak ada**

| Tempat | Kondisi sekarang | Bukti |
|---|---|---|
| Material R&D | **TIDAK ADA field warna sama sekali** | `dewi_rnd_materials.py:242-255` |
| Form material R&D (UI) | tidak ada input warna | `RnDMaterialsTab.jsx:16-23` |
| Baris kain Tech Pack | `{ name, role }` — tanpa warna | `RnDTechPackModule.jsx:27` |
| Baris BOM Tech Pack | `{ material, spec, qty, unit, supplier }` — tanpa warna | `RnDTechPackModule.jsx:25` |
| Varian produk (Gambar 1) | **satu** `color` + `color_code`, **teks bebas**, bukan FK master | `dewi_rnd_design.py:113-114` · `RnDVariantModule.jsx:32` |

### 2.2 Ukuran — 8 ukuran DI-HARDCODE, tidak bisa diubah dari layar

| Tempat | Kondisi sekarang | Bukti |
|---|---|---|
| Modal Tambah Varian (Gambar 1) | `DEFAULT_SIZES = ['XS','S','M','L','XL','XXL','2XL','3XL']` **hardcode**, dan **tidak ada tombol tambah/hapus ukuran** | `RnDVariantModule.jsx:22`, `:288` (hanya `.map`, tanpa `addSize`/`removeSize`) |
| Tech Pack — kolom ukuran | `size_columns` **sudah bisa** tambah/hapus bebas ✅ | `RnDTechPackModule.jsx:150-152` |
| Tech Pack — `base_size` / `size_range` | teks bebas `'M'` / `'S-XL'`, **tumpang tindih** dengan `size_columns` | `dewi_rnd_hpp.py:502-503` |
| Tech Pack — `fabric_consumption.size` | teks bebas, **tidak terikat** `size_columns` | `RnDTechPackModule.jsx:28` |

### 2.3 Tech Pack — datanya sudah kaya, tapi ada **4 sambungan longgar**

Model sudah lengkap (`fabrics[]`, `fabric_consumption[]`, `construction_points[]`,
`size_columns[]`, `measurements[]`, `fit_categories[]`, `bom_items[]`) dan UI punya 5 tab
(info · konstruksi · bahan · bom · measurements). Yang bermasalah:

1. **Dua sumber kebenaran per baris BOM.** Ada Input teks `material` **dan** dropdown master
   `material_id` berdampingan (`RnDTechPackModule.jsx:744-749`). Kalau isinya berbeda,
   `resolve_master_material` menebak lewat **nama**. Baris yang tidak tertaut master
   **tidak punya harga & faktor konversi satuan** ⇒ HPP-nya salah tanpa peringatan di layar.
2. **`fabric_consumption.size` bisa menyimpang** dari `size_columns` (dua daftar ukuran berbeda
   dalam satu dokumen).
3. **`measurements.values` dikunci oleh STRING nama kolom.** Ganti nama kolom (mis. `XL` → `EXTRA L`)
   ⇒ seluruh nilai measurement kolom itu **jadi yatim tanpa peringatan**.
   Bukti bentuk: `{point, values:{col:val}}` (`RnDTechPackModule.jsx:47`, `:156`).
4. **Tidak ada dimensi warna** di Tech Pack ⇒ tidak bisa menyatakan "gaya ini 3 colorway".

### 2.4 HPP — dua mode yang **SALING MENGUNCI** (ini akar keluhan owner)

`dewi_rnd_hpp.py:45-50`:

```
use_bom = True   →  material_cost = 100% dari BOM Tech Pack × harga master
                    input manual fabric_usage & accessories_cost DIABAIKAN (acc_total = 0.0)
use_bom = False  →  100% manual; accessories_cost = [{name, unit_cost, qty}] teks bebas,
                    TANPA tautan master sama sekali
```

Jadi **tidak ada jalan tengah**: mustahil sebagian baris dari master dan sebagian custom —
tepat seperti yang owner minta. Tambahan: `cmt_cost_per_pcs`, `cutting_cost_per_pcs`,
`packaging_cost_per_pcs` semuanya angka manual tanpa sumber master
(padahal `dewi_maklon_buyer_catalog.default_cmt_price` **sudah ada** dan bisa dipakai).

### 2.5 BONUS — 2 bug yang ketemu saat analisis (bukan diminta, tapi harus dilaporkan)

1. **Urutan SKU R&D TERBALIK dari SSOT ERP.**
   * SSOT: `build_variant_sku()` = `{MODEL}-{COLOR}-{SIZE}` (`utils/variant_ssot.py:32-35`)
   * R&D: `autoGenSKU()` = `` `${style_code}-${size}-${colorAbbrev}` `` = **`{STYLE}-{SIZE}-{COLOR}`**
     (`RnDVariantModule.jsx:112-118`)
   Selain urutannya tertukar, R&D memakai **3 huruf pertama NAMA warna**, bukan **kode warna**
   master. Akibatnya SKU hasil R&D **tidak akan pernah cocok** dengan SKU FG di gudang/produksi
   ⇒ stok & penjualan tidak bisa ditelusuri balik ke varian R&D.
2. **Tidak ada penjagaan varian kembar.** `handleSave` hanya memeriksa style & nama warna terisi
   (`RnDVariantModule.jsx:123-136`); backend `create_variant` juga tidak memeriksa apa pun
   (`dewi_rnd_design.py:106-124`). Dua varian dengan style+warna SAMA bisa dibuat diam-diam.

---

## 3) Usulan perbaikan

### A. Warna: satu kali input, banyak warna — **tanpa mengubah bentuk data**

Ada dua cara. Saya **merekomendasikan Cara 1**.

**Cara 1 — FAN-OUT (rekomendasi).** Modal menerima N warna; saat disimpan, backend membuat
**N dokumen varian** (satu per warna), masing-masing dengan `sizes[]` + SKU-nya sendiri.

* ✅ Bentuk data **TIDAK berubah** ⇒ **nol migrasi**, semua pembaca lama tetap jalan
* ✅ Butirannya (grain) **sama dengan SSOT** `rahaza_model_variants` (warna × ukuran) ⇒ nanti mudah
  disambungkan ke produksi
* ✅ Persis UX yang diminta: isi banyak warna sekaligus, tidak bolak-balik

**Cara 2 — BERSARANG.** Satu dokumen varian memuat `colors:[{name, code, hex, sizes:[...]}]`.
* ❌ Mengubah butiran data ⇒ **wajib migrasi**, semua pembaca lama harus disesuaikan
* ❌ Menjauh dari SSOT ERP ⇒ menambah utang baru
* → **tidak disarankan**

**Bentuk UI baru pada modal "Tambah Varian":**

```
Style Produk *   [ -- Pilih Style -- ▾ ]

Warna  (bisa lebih dari satu)                       [+ Tambah Warna]
┌──────────────────────────────────────────────────────────────────┐
│ ▾ Navy Blue   (NVY)  ■#1B2A5B                          [🗑]      │  ← dari master
│ ▾ Black       (BLK)  ■#000000                          [🗑]      │  ← dari master
│ ▾ + Warna baru…  → Nama [_______] Kode [___] ■[picker]  [Simpan ke Master] │
└──────────────────────────────────────────────────────────────────┘

Ukuran & SKU                    [Auto-generate SKU]   [+ Tambah Ukuran]
        │ NVY              │ BLK
Ukuran  │ SKU      Qty     │ SKU      Qty          [🗑 hapus ukuran]
XS      │ …-NVY-XS  0      │ …-BLK-XS  0            [🗑]
S       │ …-NVY-S   0      │ …-BLK-S   0            [🗑]
```

* Dropdown warna diisi dari **`GET /api/rahaza/colors`** (master yang sudah ada)
* Baris **"+ Warna baru…"** menulis ke master lewat **`POST /api/rahaza/colors`** lalu langsung
  terpilih ⇒ **tidak bolak-balik menu** (keputusan owner #2)
* Matriks **warna × ukuran** untuk SKU & Qty Plan
* `autoGenSKU` **diperbaiki** memakai `utils/variant_ssot.build_variant_sku()` ⇒
  `{STYLE}-{COLOR_CODE}-{SIZE}` (memperbaiki bug §2.5.1)
* Simpan menolak warna kembar dalam satu style, dengan pesan yang jelas (memperbaiki bug §2.5.2)

**Warna pada MATERIAL R&D** (permintaan "warna bahan"): tambah `colors: []` pada
`dewi_rnd_materials` — daftar warna yang tersedia untuk bahan itu (mis. Fleece → Navy/Black/Grey),
memakai master yang sama. Baris kain Tech Pack lalu bisa memilih **warna yang memang tersedia**
untuk bahan tersebut.

### B. Ukuran customizeable (sesuai keputusan #3: tetap bebas, tanpa master)

* `DEFAULT_SIZES` **dikeluarkan dari komponen**; daftar ukuran menjadi **data**, bukan kode
* Disimpan per style: `dewi_rnd_styles.size_list = ['XS','S','M',…]` (bebas, boleh apa saja:
  `"All Size"`, `"28/30"`, `"3XL"`)
* Modal Varian & Tech Pack **membaca daftar yang sama** ⇒ satu style, satu daftar ukuran
  (menutup penyimpangan §2.3.2)
* Tombol **[+ Tambah Ukuran]** dan **[🗑]** di modal, plus **ubah nama** ukuran
* `base_size` = **dipilih dari** `size_list` (bukan diketik); `size_range` **dihitung otomatis**
  dari `size_list` ⇒ menghapus tumpang tindih §2.2

> ⚠️ **KONSEKUENSI yang wajib saya sampaikan.** Karena owner memilih ukuran **bebas** (opsi b),
> ukuran R&D tetap **string** sementara PO produksi mewajibkan `size_id` yang sah
> (`production_internal_adapter.py:53-56`). Artinya saat gaya ini masuk produksi, ukuran **masih
> harus dipadankan manual**. Dua pilihan untuk meredam, keduanya TIDAK memaksa master:
> * **B1 (usul saya):** simpan `size_list` sebagai teks bebas, TAPI saat menyimpan, sistem
>   mencocokkan otomatis ke `rahaza_sizes` bila namanya sama, dan menyimpan `size_id` sebagai
>   **petunjuk opsional**. Yang tidak ketemu diberi tanda "belum dipadankan" — bisa dibiarkan.
>   Biaya: nol untuk pengguna; manfaat: alur ke produksi tidak mentok.
> * **B2:** benar-benar bebas tanpa pemadanan apa pun. Konsekuensinya entri ulang di produksi
>   tetap ada.
> Mohon pilih **B1** atau **B2** (§7).

### C. Tech Pack — tutup 4 sambungan longgar

| # | Perbaikan | Kenapa perlu |
|---|---|---|
| C1 | Baris BOM: dropdown master jadi **utama**; teks bebas menjadi cadangan yang **diberi badge peringatan** ("tanpa master ⇒ harga & konversi satuan tidak dihitung") | Hilangkan dua sumber kebenaran; ketidaktepatan HPP jadi **kelihatan**, tidak diam-diam |
| C2 | `fabric_consumption.size` → **dropdown** dari `size_list` | Tidak bisa menyimpang lagi |
| C3 | `measurements` dikunci `col_id` stabil, nama kolom jadi label terpisah | Ganti nama kolom **tidak lagi** membuat data yatim. Perlu migrasi pemetaan kunci lama |
| C4 | Tambah `colorways: []` (rujuk master warna) pada Tech Pack | Satu gaya bisa punya beberapa colorway resmi |
| C5 | Tambah kolom **warna** pada baris kain (`fabrics[]`) & baris BOM | Melengkapi permintaan "warna bahan" |

**Sisi UI Tech Pack:** tab `bahan` dan `bom` dirapikan menjadi tabel yang lebih rapat dengan
kolom warna + badge status tautan master, dan tab `measurements` memakai kolom dari `size_list`
(satu sumber). *Catatan: owner belum menyebut bagian UI spesifik yang paling mengganggu — bila ada,
sebutkan agar itu yang dibenahi lebih dulu (§7).*

### D. HPP hybrid — **sumber per BARIS**, bukan per dokumen

Ganti saklar global `use_bom` (mati/hidup) menjadi **pilihan sumber di setiap baris biaya**:

```
Baris biaya          Sumber        Referensi              Harga     Dipakai
─────────────────────────────────────────────────────────────────────────────
Kain Fleece Navy     [Master ▾]    FAB-FLC-NVY (master)   85.000    85.000
Kancing Metal        [Techpack ▾]  dari BOM v3            250       250
Label woven custom   [Manual ▾]    —                      1.200     1.200   ← custom field
Jasa CMT             [Master ▾]    Katalog buyer ARN-HD   18.000    18.000
Bordir khusus        [Manual ▾]    —                      3.500     3.500   ← custom field
```

* `total = Σ semua baris`, **apa pun sumbernya** ⇒ master + custom bisa **bercampur**
  (inilah permintaan owner)
* Sumber `Master` menyimpan `material_id` + **snapshot** `unit_cost_master`, sehingga saat harga
  master berubah sistem bisa memberi tahu "harga master sudah berubah, perbarui?"
* Sumber `Techpack` menarik dari BOM Tech Pack terbaru (perilaku yang **sudah benar** hari ini,
  dipertahankan)
* Sumber `Manual` = custom field bebas (nama + harga sendiri)
* `cmt_cost` bisa menarik dari `dewi_maklon_buyer_catalog.default_cmt_price` (master yang sudah ada)
* **Kompatibilitas mundur:** field `use_bom` **tetap disimpan**; dokumen HPP lama dibaca sebagai
  "semua baris bersumber Techpack" (bila `use_bom=true`) atau "semua Manual" (bila `false`).
  Tidak ada data lama yang rusak.
* Pola ini **bukan hal baru** di repo — baris BOM Tech Pack sudah memakai
  "dropdown master + input bebas" (`RnDTechPackModule.jsx:744-749`), jadi konsisten.

**Override harga master** — kebijakan masih menunggu keputusan owner, lihat §7 (D1/D2/D3).

---

## 4) Ringkasan perubahan data (semuanya ADITIF — tidak ada field dibuang)

| Koleksi | Field baru | Migrasi |
|---|---|---|
| `dewi_rnd_materials` | `colors: [{color_id, code, name, hex}]` | tidak perlu (default `[]`) |
| `dewi_rnd_styles` | `size_list: [str]` (+ `size_map` bila B1) | tidak perlu (fallback ke 8 ukuran lama) |
| `dewi_rnd_variants` | `color_id` (rujuk master) | tidak perlu — `color`/`color_code` lama tetap dibaca |
| `dewi_rnd_tech_packs` | `colorways: []`, warna pada `fabrics[]`/`bom_items[]`, `measurements[].values` berkunci `col_id`, `size_columns[]` → `[{col_id,label}]` | **PERLU** untuk `measurements` (idempoten, memetakan kunci lama) |
| `dewi_rnd_hpp` | `cost_lines: [{label, source, material_id, unit_cost_master, unit_cost_used, qty, unit, override, override_reason}]` | tidak perlu — dokumen lama dipetakan dari `use_bom` |

**API baru/berubah** (semua tetap ber-prefix `/api`):
* `GET /api/dewi/rnd/color-options` — proxy tipis ke master `rahaza_colors` (biar layar R&D
  tidak perlu tahu detail master)
* `POST /api/dewi/rnd/variants/bulk` — fan-out N warna × M ukuran dalam satu transaksi
* `GET/PUT /api/dewi/rnd/styles/{id}/size-list` — daftar ukuran per style
* `POST /api/dewi/rnd/hpp-calculator/preview` — sudah ada, diperluas untuk `cost_lines`

---

## 5) Risiko & cara meredam

| Risiko | Peredam |
|---|---|
| Migrasi `measurements` bisa menghilangkan nilai | Skrip **idempoten**, hanya menambah `col_id`, `values` lama **dipertahankan** sebagai `values_legacy` sampai diverifikasi; gate baru memastikan jumlah nilai sebelum = sesudah |
| SKU R&D lama (`STYLE-SIZE-COLOR`) sudah tersebar | SKU lama **TIDAK diubah otomatis**. Disediakan laporan "SKU tidak sesuai SSOT" + tombol perbaiki per baris, supaya owner memutuskan |
| Bundle frontend harus di-rebuild | `bash scripts/rebuild_frontend.sh` setelah tiap fase (wajib, mode static bundle) |
| Perubahan HPP menyentuh angka uang | Setiap fase ditutup `bash scripts/gate.sh` (13 gate, termasuk invarian UANG) + testing agent |

---

## 6) Usulan urutan pengerjaan (owner belum memutuskan — §7)

| Fase | Isi | Kenapa urutan ini |
|---|---|---|
| **F1** | **Warna multi + master inline** (§A) + perbaikan SKU & varian kembar (§2.5) | Ini yang owner tunjuk langsung di Gambar 1; fan-out = nol migrasi ⇒ hasil cepat & aman |
| **F2** | **Ukuran customizeable** (§B) | Fondasi; dipakai Tech Pack **dan** modal Varian |
| **F3** | **Tech Pack** (§C) | Butuh `size_list` dari F2 sudah ada |
| **F4** | **HPP hybrid** (§D) | Paling akhir karena membaca hasil F1–F3 (warna, ukuran, BOM tertaut master) |

Setiap fase: implementasi → `gate.sh` → testing agent → rebuild bundle → lapor.
Bila owner ingin **HPP dulu**, bisa — tapi HPP akan dikerjakan dua kali sebagian
(karena baris biaya perlu tahu warna & ukuran), jadi total waktunya lebih panjang.

---

## 7) Yang masih perlu keputusan owner

1. **Pemadanan ukuran** → **B1** (padankan otomatis ke master bila nama sama, sisanya ditandai
   "belum dipadankan", tetap bebas) atau **B2** (bebas total, tanpa pemadanan)?
   *Usul saya: B1 — gratis bagi pengguna, dan menyelamatkan alur R&D → produksi.*
2. **Override harga master di HPP:**
   * **D1** boleh override + **wajib alasan**, tercatat *(usul saya — nego harga itu nyata, tapi harus berjejak)*
   * **D2** tidak boleh override (harga wajib ikut master)
   * **D3** boleh override tanpa alasan
3. **Urutan fase** → pakai usulan **F1→F2→F3→F4**, atau HPP dulu?
4. **Tech Pack:** bagian mana yang paling mengganggu saat dipakai sehari-hari — **UI**-nya
   (tata letak/alur input) atau **data**-nya (field kurang/salah)? Sebutkan bagian spesifiknya
   supaya itu yang dibenahi lebih dulu di F3.
5. **Warna pada material R&D** (§A akhir): perlu sekalian di F1, atau cukup warna varian dulu?

---

## 8) Kriteria selesai (per fase)

* **F1** — satu kali "Tambah Varian" bisa menghasilkan N warna × M ukuran; warna dipilih dari master
  dan warna baru bisa ditambahkan tanpa keluar dari layar R&D; SKU mengikuti
  `build_variant_sku()`; warna kembar dalam satu style ditolak dengan pesan jelas.
* **F2** — daftar ukuran bisa ditambah/diubah/dihapus dari layar dan **tersimpan per style**;
  Tech Pack & modal Varian memakai daftar yang **sama**; `base_size` dipilih dari daftar dan
  `size_range` terhitung otomatis.
* **F3** — baris BOM tanpa tautan master **kelihatan** (badge peringatan);
  `fabric_consumption.size` tidak bisa menyimpang; mengganti nama kolom ukuran **tidak**
  menghilangkan nilai measurement (dibuktikan oleh gate baru).
* **F4** — satu HPP bisa memuat baris `Master` + `Techpack` + `Manual` **sekaligus** dan totalnya
  benar; dokumen HPP lama tetap terbaca dan angkanya tidak berubah.
* **Semua fase** — `bash scripts/gate.sh` **13/13 HIJAU** + testing agent tanpa bug kritis.
