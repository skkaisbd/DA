# Proposal Pengembangan — Menutup Backlog Data Excel

Tanggal: 2026-07-27
Dasar: `docs/ANALISIS_BACKLOG_EXCEL.md`
Status: **USULAN — menunggu persetujuan owner**

---

## 0. Prinsip yang saya pegang

1. **Jangan bangun yang sudah ada.** Hasil audit: 3 dari 6 masalah ternyata sudah
   punya infrastruktur lengkap di sistem. Yang kurang cuma *datanya*, bukan fiturnya.
2. **Data master jangan ditebak.** Kalau angkanya tidak ada di Excel (harga kain,
   kg kain per pcs), sistem tidak boleh mengarang. Lebih baik kosong + jelas
   penyebabnya, daripada HPP salah tapi kelihatan "ada isinya".
3. **Pemetaan nama bebas harus bisa diaudit.** Setiap hasil pencocokan otomatis
   wajib bisa dilihat, dikoreksi, dan disimpan — bukan black box sekali jalan.
4. **Semua skrip idempotent.** Boleh dijalankan berulang tanpa menggandakan data.

---

## 1. Temuan penting: 3 masalah TIDAK butuh fitur baru

Audit infrastruktur yang sudah terpasang:

| Kebutuhan | Sudah ada? | Bukti |
|---|---|---|
| Impor/ekspor harga material massal | **SUDAH** | `/api/data-transfer/{registry,template,export,import}` + komponen `ImportExportToolbar` sudah terpasang di layar Master Material (tombol Ekspor/Impor). Mode **dry-run → commit** sudah jalan. Kolom `unit_cost` sudah terdaftar sebagai kolom importable. |
| Editor BOM per model+size+warna | **SUDAH** | `RahazaBOMModuleV2.jsx` (956 baris): versioning, aktivasi versi, salin ke size lain, picker material dari master, preview kebutuhan. API `/api/rahaza/boms` lengkap. |
| Layar & API roll kain | **SUDAH** | `WMSFabricRollsModule.jsx` + endpoint roll. Koleksi `wh_fabric_rolls` masih kosong. |

**Artinya:** pekerjaan saya bukan "bikin fitur", tapi **menyiapkan & memasukkan data**
plus **satu alat bantu pemetaan** yang memang belum ada.

---

## 2. Paket Kerja yang Diusulkan

### WP-1 — Lengkapi Ongkos Jahit (`cmt_cost_per_pcs`)
**Masalah** — SPEK PRODUK punya kolom `Ongkos Jahit/pcs` terisi di 29 dari 57 SKU
(Rp5.500–Rp10.000). Di sistem, `cmt_cost_per_pcs` baru terisi 13 dari 55 model
(hanya yang dari sheet GALERI PRODUK).

**Yang dibangun**
- Skrip baru `scripts/backfill_cmt_cost_from_spek.py` — baca SPEK PRODUK, cocokkan
  ke model lewat kolom `SKU` (bukan nama bebas → **pencocokan pasti, bukan fuzzy**),
  isi `cmt_cost_per_pcs` bila masih 0.
- Mode `--dry` untuk pratinjau sebelum tulis.

**Output terukur** — model dengan ongkos jahit: **13 → ±29 dari 55**.
**Risiko** — nyaris nol. Kunci pencocokan adalah kode SKU yang persis sama.
**Perlu keputusan owner?** Tidak.

---

### WP-2 — Lengkapi Master Material yang Hilang
**Masalah** — SPEK PRODUK menyebut bahan/aksesoris yang belum ada di master:
- `Kain keras` dipakai **22×** (kerah 10×, polos 7×, daun 5×) → **0 hasil** di 335 master aksesoris.
- 8 nama kain tidak ada padanannya: `Poly Micro Motif` (13×), `Micro Motif`,
  `Micro Polos`, `Snowy Motif`, `Rib Boston 2x1`, `Automan Setting 77`, `Rayon`,
  `Knit Polos`, `Knit 20`.

Tanpa ini, BOM akan bolong di baris-baris yang justru paling sering dipakai.

**Yang dibangun**
- Skrip `scripts/seed_missing_materials_from_spek.py` yang membuat item master baru:
  - Aksesoris interlining: `Kain keras (kerah)`, `Kain keras (daun)`, `Kain keras`
    → `type: accessory`, kategori interlining, `unit: meter`, `unit_cost: 0`.
  - Kain: dibuat sebagai **grup kain tanpa warna** (`color: null`,
    `is_group_placeholder: true`) supaya bisa dirujuk BOM tapi tidak mengotori
    laporan stok per-warna.
- Semua item baru diberi tanda `source: "SPEK PRODUK — perlu verifikasi"` agar
  mudah difilter dan dirapikan owner.

**Output terukur** — ±3 aksesoris + ±9 grup kain baru; nama kain di spek yang
punya padanan naik dari ~6/21 → **21/21**.
**Risiko** — sedang. Kalau ternyata nama-nama itu sebenarnya alias dari kain yang
sudah ada (mis. "Poly Micro Motif" = salah satu grup existing), akan muncul duplikat.
**Mitigasi** — semua bertanda `perlu verifikasi` + skrip `--dry` + bisa dihapus massal.
**Perlu keputusan owner?** **YA** — pertanyaan #3 (buat otomatis vs petakan manual dulu).

---

### WP-3 — Generator BOM + Layar Review Pemetaan  ← paket terbesar
**Masalah** — 57 SKU × rata-rata 4,3 aksesoris = 245 baris BOM harus dipetakan dari
nama bebas ke kode master. `rahaza_boms` masih 0.

**Yang dibangun**

**(a) Mesin pencocokan** — `backend/core/spek_matcher.py`
- Normalisasi + kamus sinonim domain: `hanteg/hanteng/hantag → hangtag`,
  `lisban → lis ban`, `absreak → abstrak`, `labal → label`, buang kata sampah
  (`sesuai`, `warna`, `ketentuan`, `uk`).
- Bobot token: angka & satuan (`18L`, `4cm`, `0,3`) dinilai 2× lebih penting
  daripada kata biasa.
- **2 aturan domain** yang menyelamatkan 22 kasus gagal:
  - `Karet <n>cm (...)` → abaikan isi kurung, cocokkan ke `Karet Uk <n> cm`
  - `Size <X>` / `Label Size <X>` → `Label size <X> putih rajut`
- Skor akhir → 3 bucket: **auto (≥0,75)** · **review (0,5–0,75)** · **manual (<0,5)**.

Hasil uji pada data nyata: **42/70 auto** sekarang, diperkirakan **±60/70 (85%)**
setelah 2 aturan domain ditambahkan.

**(b) Tabel pemetaan tersimpan** — koleksi baru `spek_material_mappings`
```
{ id, source_name, source_type: fabric|accessory,
  material_id, material_code, material_name,
  confidence: float, status: auto|confirmed|manual|skipped,
  confirmed_by, confirmed_at }
```
Sekali dikonfirmasi owner, pemetaan **dipakai selamanya** — impor SPEK berikutnya
tidak perlu diulang dari nol.

**(c) API baru** — `backend/routes/spek_bom.py`, prefix `/api/spek`
| Method | Path | Fungsi |
|---|---|---|
| GET | `/mappings` | daftar pemetaan + skor + bucket |
| POST | `/mappings/rebuild` | jalankan ulang matcher (tidak menimpa yang `confirmed`) |
| PUT | `/mappings/{id}` | owner mengoreksi/mengonfirmasi 1 baris |
| POST | `/bom/preview` | pratinjau BOM yang akan dibuat (tanpa menulis) |
| POST | `/bom/generate` | buat `rahaza_boms` v1 `is_active=true` per model+size |

**(d) Layar baru** — `SpekBomMappingModule.jsx`, pintu menu
`prod-spek-mapping` di Portal Produksi → seksi Master Data
- Tabel 3 tab: **Otomatis · Perlu Review · Manual** dengan badge skor.
- Tiap baris: nama dari Excel → dropdown pencarian master (pakai
  `InlineMaterialPicker` yang sudah ada) → tombol Konfirmasi / Lewati.
- Tombol **Pratinjau BOM** (menampilkan berapa BOM & berapa baris akan dibuat)
  lalu **Generate BOM**.
- Guardrail `check_nav_map.py` tetap hijau (pintu baru didaftarkan resmi).

**(e) Aturan pembentukan BOM**
- `size_id` diturunkan dari nama produk (33/57 terdeteksi: L 12, XL 9, M 6, S 3,
  XXL 2, All Size 1); sisanya → `STD`.
- Baris aksesoris: `qty` = `Aks<n> Qty/baju`, `unit` = `Aks<n> Sat`.
- Baris kain: `material_type: fabric`, **`qty: 0`** + catatan
  *"kg/pcs belum tersedia — isi setelah trial cutting"*, `color: null`
  (karena 13 dari 21 kain ditulis "sesuai warna order").
- Versi 1, `is_active: true`, `notes: "Auto-generate dari SPEK PRODUK <tanggal>"`.

**Output terukur** — `rahaza_boms` 0 → **±55 BOM aktif**, ±245 baris aksesoris
langsung bisa di-explode jadi kebutuhan material per WO.
**Risiko** — pemetaan salah. **Mitigasi** — tidak ada BOM yang dibuat sebelum owner
menekan Generate; semua baris `manual` ditandai jelas; BOM punya versioning
sehingga salah pun bisa dibuat versi baru tanpa kehilangan riwayat.
**Perlu keputusan owner?** **YA** — pertanyaan #2 (aksesoris saja vs lengkap dengan
placeholder kain).

---

### WP-4 — Seed 84 Roll Kain dari Sheet Memo
**Masalah** — koleksi `wh_fabric_rolls` kosong; modul Roll Kain tampil "Belum ada data".

**Data yang tersedia**

| Lot | Rol | Warna | Tertulis | Pengecekan | Susut |
|---|---:|---|---:|---:|---:|
| 1 | 12 | Denim | 29.521 g | 28.410 g | −3,8% |
| 2 | 12 | Hitam | 29.166 g | 28.410 g | −2,6% |
| 3 | 12 | Dusty | 29.156 g | 28.240 g | −3,1% |
| 4 | 24 | Magenta | 59.775 g | 57.200 g | −4,3% |
| 5 | 24 | Hitam | 59.972 g | 57.565 g | −4,0% |
| | **84** | | **207.590 g** | **199.825 g** | **−3,7%** |

**Yang dibangun**
- Skrip `scripts/seed_fabric_rolls_from_memo.py`:
  - 84 dokumen roll: `roll_no` (`RL-<warna>-<nn>`), `material_id` (grup kain
    hasil konfirmasi owner), `color`, `width_cm: 135`,
    `weight_kg_written` (tertulis), `weight_kg_actual` (pengecekan),
    `variance_pct`, `status: in_stock`, `qc_status: pending`.
  - **Berat yang dipakai untuk stok = hasil pengecekan** (angka aktual), bukan
    tertulis — supaya stok sistem = fisik.
  - Selisih disimpan sebagai catatan QC → dasar klaim ke supplier.
- Tidak menyentuh ledger stok (`rahaza_material_stock`) kecuali diminta, supaya
  saldo awal yang sudah diseed tidak dobel.

**Output terukur** — 84 roll fisik terlacak + laporan susut 7,77 kg.
**Risiko** — rendah, tapi **grup kainnya belum pasti**. Lebar 135 cm mengarah ke
`KNIT SALUR FNSH 135`, namun warna Denim/Dusty/Magenta perlu dicocokkan.
**Perlu keputusan owner?** **YA** — pertanyaan #4.

---

### WP-5 — Harga Kain: template + panduan (BUKAN fitur baru)
**Masalah** — 143 kain `unit_cost = 0`; angkanya **tidak ada di Excel mana pun**.

**Yang dibangun** — sangat kecil, karena impor massal sudah ada:
- Tambah **filter tipe** pada ekspor material: `/api/data-transfer/export/materials?type=fabric`
  → owner mengunduh 143 baris kain saja, bukan 1.031 baris campur.
- Skrip `scripts/apply_fabric_price_by_group.py` untuk **opsi B** (owner cukup
  memberi 10 angka per grup kain, sistem menurunkannya ke semua warna di grup itu).
- Halaman panduan singkat di `docs/user-guide/`.

**Output terukur** — kain dengan harga: 0 → 143 (setelah owner mengisi).
Begitu terisi: HPP produksi, nilai persediaan kain, dan HPP potongan Cutting
langsung hidup.
**Risiko** — nol (owner yang mengisi angkanya).
**Perlu keputusan owner?** **YA** — pertanyaan #1 (per-item, per-grup, atau tunda).

---

### WP-6 — Tambal 92 Harga Aksesoris (opsional, prioritas terakhir)
**Masalah** — 92 dari 335 aksesoris belum berharga.

**Kendala yang jujur:** sumbernya sheet pembelian (`DA`, `SNBM`, `02`) yang
satuannya **LUSIN / BKS / ROLL**, sedangkan master pakai **Pcs / Meter / Gram**.
Konversi (`1 BKS = ? pcs`, `1 ROLL = ? meter`) **hanya owner yang tahu**, dan
berbeda per jenis barang.

**Yang dibangun**
- Skrip `scripts/backfill_accessory_price.py` + tabel konversi
  `config/unit_conversion.yml` yang diisi owner.
- Harga diambil dari **pembelian terakhir** per nama (bukan rata-rata), disimpan
  dengan `price_source: "pembelian <tanggal>"` supaya jejaknya jelas.

**Output terukur** — perkiraan realistis **30–50 dari 92** tertambal otomatis.
**Risiko** — sedang (nama bebas + konversi satuan).
**Perlu keputusan owner?** **YA** — tabel konversi satuan.

---

## 3. Yang SENGAJA TIDAK saya usulkan

| Tidak dikerjakan | Alasan |
|---|---|
| Menebak harga kain dari rata-rata pasar | Akan membuat HPP & nilai persediaan salah tapi terlihat valid. Lebih berbahaya daripada Rp 0. |
| Mengisi `kg kain per pcs` dengan asumsi | Tidak ada satu pun angka pemakaian kain per pcs di 7 file. Harus dari trial cutting nyata. |
| Impor 12 sheet transaksi Marketing | Keputusan owner: mulai dari bersih. Tidak diubah. |
| Impor `Jumlah Komponen Potongan` ke Portal Cutting | Hanya **1 dari 57** baris yang terisi — tidak layak jadi master. |
| Impor `Sheet1` (1.454 produk hijab) | Ini **lini bisnis retail terpisah**, bukan garment produksi. Butuh keputusan strategis dulu, bukan sekadar impor data. |

---

## 4. Urutan & Ketergantungan

```
Tanpa perlu keputusan:
  WP-1  Ongkos jahit ──────────────► bisa jalan sekarang

Butuh 1 keputusan singkat:
  WP-4  Roll kain (grup kain?) ────► 84 roll terisi
  WP-5  Harga kain (per-item/grup?)► HPP hidup

Butuh keputusan + paling besar:
  WP-2  Master hilang ─┐
                       ├──────────► WP-3  BOM + layar pemetaan
  (keputusan #2, #3) ──┘

Opsional, terakhir:
  WP-6  Harga aksesoris (butuh tabel konversi satuan)
```

**Saran urutan:** WP-1 → WP-4 → WP-2 → WP-3 → WP-5 → WP-6.
Alasan: WP-1 & WP-4 memberi hasil nyata segera tanpa risiko, sambil menunggu
keputusan untuk WP-2/WP-3 yang lebih berat.

---

## 5. Ringkasan Dampak

| Metrik | Sekarang | Setelah semua WP |
|---|---:|---:|
| BOM aktif | 0 | ±55 |
| Baris BOM aksesoris siap explode | 0 | ±245 |
| Model dengan ongkos jahit | 13 / 55 | ±29 / 55 |
| Roll kain fisik terlacak | 0 | 84 |
| Kain berharga | 0 / 143 | 143 / 143 * |
| Aksesoris berharga | 243 / 335 | ±280–293 / 335 |
| Nama kain di spek yang punya padanan | ~6 / 21 | 21 / 21 |

\* tergantung owner mengisi angkanya.

---

## 6. Cara Verifikasi (yang akan saya jalankan)

1. Setiap skrip punya mode `--dry` — hasilnya saya tunjukkan **sebelum** menulis ke DB.
2. `python3 scripts/guardrails/check_nav_map.py` wajib tetap HIJAU setelah pintu
   menu `prod-spek-mapping` ditambahkan.
3. `testing_agent_v3` untuk API `/api/spek/*` + layar pemetaan + regresi BOM lama.
4. Bukti fungsional: buat 1 Work Order dari model ber-BOM → kebutuhan aksesoris
   ter-explode otomatis → tampil di Pengeluaran Material Gudang.
5. Backup DB sebelum WP-2 & WP-3 (keduanya menulis master baru).

---

## 7. Yang saya butuhkan dari owner

Cukup 5 jawaban (sudah saya kirim terpisah):

1. **Harga kain** → per-item (143 baris) / per-grup (10 angka) / tunda
2. **BOM** → aksesoris saja / tunggu kain lengkap / lengkap dengan placeholder kain
3. **Nama tanpa padanan** → buat otomatis / petakan manual dulu / lewati
4. **84 roll Memo** → grup `KNIT SALUR FNSH 135` / grup lain / lewati
5. **Sheet1 (produk hijab)** → impor sebagai produk dagang / abaikan / bahas nanti

Begitu jawabannya masuk, saya mulai dari WP-1 (tidak perlu menunggu apa pun).
