# Rancangan Multi-Satuan (Multi-UOM) Berjenjang

Tanggal: 2026-07-27
Dasar: `docs/AUDIT_KONVERSI_SATUAN.md` + `docs/MAP_UOM_IMPACT.md`
Keputusan owner: **rombak struktur dulu · multi-satuan (bukan konversi paksa) ·
kemasan berjenjang PERLU · tanpa layar setup massal · WAJIB memetakan semua flow
supaya tidak muncul bug baru**

Status: **RANCANGAN — menunggu persetujuan sebelum ditulis ke kode**

---

## 1. Skala dampak (hasil pemetaan otomatis)

`python3 scripts/map_uom_impact.py` → `docs/MAP_UOM_IMPACT.md`

| | Jumlah |
|---|---:|
| File backend tersentuh satuan/qty | **132** |
| File frontend tersentuh | **64** |
| Domain bisnis terdampak | **12** |
| Titik tulis stok (`stock_service.*`) | **52** |
| File backend yang sudah sadar kemasan | **6 dari 132** |

Per domain:

| Domain | File BE | File FE | Titik tulis stok | Sudah sadar pack |
|---|---:|---:|---:|---:|
| Gudang / WMS | 25 | 9 | 30 | 1 |
| Maklon / CMT | 18 | 9 | 2 | 0 |
| Aksesoris | 12 | 7 | 14 | 5 |
| Marketing | 12 | 0 | 0 | 0 |
| Produksi | 8 | 1 | 1 | 0 |
| Finance / HPP | 4 | 2 | 0 | 0 |
| RnD | 4 | 4 | 0 | 0 |
| Pengiriman | 4 | 4 | 1 | 0 |
| BOM / MRP | 2 | 1 | 0 | 0 |
| Pengadaan | 2 | 2 | 0 | 0 |
| Cutting | 1 | 2 | 2 | 2 |
| Lain-lain | 40 | 23 | 2 | 1 |

**Kesimpulan:** mengubah 52 titik tulis stok satu per satu = risiko regresi sangat
tinggi. Karena itu rancangan ini memakai pendekatan **satu pintu + opsional**,
bukan tebar perubahan.

---

## 2. Temuan yang MENGUNCI desain (kenapa tidak boleh sembarangan)

Saat memetakan hilir, ditemukan pola yang dipakai **5 modul berbeda**:

```python
# dewi_rnd_hpp.py · rahaza_hpp.py · rahaza_material_requirements.py
# production_internal_adapter.py · rahaza_posting.py
amount = qty × material.unit_cost
```

Semuanya **mengasumsikan**:
- `qty` sudah dalam satuan dasar
- `unit_cost` adalah harga **per satuan dasar**

Kalau semantik `unit_cost` diubah (mis. jadi "harga per satuan beli"), maka
**HPP RnD, HPP Produksi, MRP, adapter Produksi Internal, dan posting Jurnal
langsung salah semua** — persis "bug baru" yang Bapak/Ibu khawatirkan.

### Invarian baru yang WAJIB dijaga

| ID | Invarian | Sifat |
|---|---|---|
| **INV-UOM-1** | `rahaza_materials.unit_cost` **selalu** harga per **satuan dasar**. Satuan input hanya alat bantu entri; sistem selalu menyimpan hasil konversinya. | FAIL |
| **INV-UOM-2** | Semua qty di `rahaza_material_stock`, `rahaza_stock_ledger`, `rahaza_material_movements` **selalu** satuan dasar. | FAIL |
| **INV-UOM-3** | `uoms[0]` wajib `is_base=true` & `factor=1`; setiap `factor > 0`; `code` unik dalam satu material. | FAIL |
| **INV-UOM-4** | `unit` (lama) selalu sama dengan `base_uom` (baru). Keduanya di-mirror. | FAIL |
| **INV-UOM-5** | Mengedit daftar `uoms` **tidak boleh** mengubah angka stok yang sudah ada. Perubahan satuan dasar hanya lewat aksi khusus ber-audit. | FAIL |
| **INV-UOM-6** | `factor` selalu relatif ke **satuan dasar**, bukan ke induknya. | FAIL |

Akan ditegakkan guardrail baru `scripts/guardrails/verify_uom_integrity.py`.

---

## 3. Skema baru `rahaza_materials`

```jsonc
{
  // ── FIELD LAMA — TETAP ADA, jadi cermin (mirror) dari uoms ──────────────
  "unit": "pcs",              // = base_uom  (SSOT lama, tidak dihapus)
  "pack_unit": "bks",         // = uoms[1].code   → 6 file pack-aware tetap jalan
  "pack_size": 144,           // = uoms[1].factor → idem
  "display_in_packs": false,
  "unit_cost": 1000,          // TETAP per satuan dasar (INV-UOM-1)
  "min_stock": 0,             // TETAP dalam satuan dasar

  // ── FIELD BARU ──────────────────────────────────────────────────────────
  "base_uom": "pcs",
  "uoms": [
    { "code":"pcs", "name":"Pieces",  "factor":1,    "is_base":true, "level":0 },
    { "code":"bks", "name":"Bungkus", "factor":144,  "parent":"pcs", "level":1,
      "is_purchase_default":true, "barcode":"", "notes":"1 bks = 144 pcs" },
    { "code":"ktn", "name":"Karton",  "factor":1728, "parent":"bks", "level":2,
      "notes":"1 ktn = 12 bks" }
  ],
  "purchase_uom": "bks",      // default satuan saat beli / terima
  "issue_uom": "pcs",         // default satuan saat pakai / keluar
  "display_uom": "bks"        // default satuan saat ditampilkan di daftar
}
```

### Aturan penting

1. **`factor` selalu relatif ke satuan dasar** (INV-UOM-6).
   Saat mengisi form, user cukup mengetik *"1 karton = 12 bks"*; sistem yang
   menghitung `factor = 12 × 144 = 1728`. Ini mencegah kesalahan perkalian
   berantai yang lazim terjadi pada skema `parent-relative`.
   `parent` hanya untuk menggambar hierarki & UX input.

2. **Menjawab "double satuan"**: satu item boleh punya berapa pun satuan.
   Contoh `A1 Bisban warna hitam`:
   ```
   base = m  ·  uoms = [ {m,1}, {rol, 50} ]
   → stok tampil "450 m  (9 rol)"
   ```
   Tidak perlu memilih salah satu — keduanya tampil.

3. **Kemasan berjenjang** ditangani lewat `level` + `parent`. Kedalaman tidak
   dibatasi, tapi UI menampilkan maksimal 4 level agar tetap terbaca.

### Perubahan pada `rahaza_stock_ledger` (tambahan, tidak mengganti)
```jsonc
{ "...": "...",
  "input_qty":  1,      // apa yang diketik user
  "input_uom":  "bks",  // satuan yang dipilih user
  "uom_factor": 144     // faktor saat itu — dibekukan
}
```
`uom_factor` dibekukan supaya kalau isi bks berubah dari 144 → 100 di kemudian
hari, **riwayat lama tetap terbaca benar** (menutup keterbatasan #5 pada audit).

---

## 4. `core/uom.py` — satu-satunya sumber kebenaran konversi

Mengikuti pola yang sudah ada di proyek (`core/material_fields.py`):

```python
resolve_uoms(material)                  -> list[dict]   # + fallback otomatis
base_uom_of(material)                   -> str
factor_of(material, uom)                -> float
to_base(material, qty, uom=None)        -> float
from_base(material, qty, uom=None)      -> float
cost_to_base(material, cost, uom=None)  -> float        # menutup BUG-1
format_dual(material, qty_base)         -> "450 m (9 rol)"
validate_uoms(uoms)                     -> (ok, errors)
build_from_legacy(material)             -> list[dict]   # unit + pack_* → uoms
```

**Fallback berlapis pada `resolve_uoms`** (inilah kunci nol-regresi):
1. Ada `uoms` yang valid → pakai itu.
2. Tidak ada, tapi ada `pack_unit` + `pack_size > 1` → bangun 2 baris on-the-fly.
3. Tidak ada keduanya → 1 baris `{code: unit, factor: 1, is_base: true}`.

Artinya **1.031 material yang ada sekarang langsung bekerja tanpa dimigrasi**.

Padanan frontend: `frontend/src/lib/uom.js` dengan fungsi yang sama persis.

---

## 5. Strategi nol-regresi (4 lapis)

| Lapis | Mekanisme | Efek |
|---|---|---|
| **L0** | `resolve_uoms()` punya fallback | Material tanpa `uoms` tetap jalan |
| **L1** | `stock_service.*` menerima `input_uom=None` **opsional** | **52 pemanggil lama tidak disentuh** — tanpa argumen = perilaku lama persis |
| **L2** | `uoms` selalu di-mirror ke `pack_unit`/`pack_size` | 6 file yang sudah pack-aware tetap benar tanpa diubah |
| **L3** | Response API tetap memuat semua field lama | 64 file frontend tidak pecah |

Contoh L1:
```python
# Pemanggil lama — tidak berubah sama sekali
await stock_service.add(mid, loc, 144)

# Pemanggil baru — eksplisit
await stock_service.add(mid, loc, 1, input_uom="bks")   # → tersimpan 144
```

---

## 6. Menangani 91 item bersatuan kemasan (74 `rol`, 14 `pak`, 3 `lusin`)

**Bahaya yang harus dihindari:** `A1 Bisban` sekarang berstok **9** dengan
satuan `rol`. Kalau satuan dasarnya diubah jadi `m` begitu saja, angka 9 itu
mendadak dibaca sebagai **9 meter** (seharusnya 450 m). **Ini korupsi data.**

Karena itu perubahan satuan dasar **TIDAK** dilakukan otomatis saat migrasi.
Disediakan aksi khusus **"Ubah Satuan Dasar"** di form edit material yang:

1. Meminta satuan dasar baru + faktor (mis. `1 rol = 50 m`)
2. Menampilkan **pratinjau**: `stok 9 rol → 450 m`, `HPP 250.000/rol → 5.000/m`,
   `min_stock 2 rol → 100 m`
3. Setelah dikonfirmasi:
   - mengonversi **semua baris** `rahaza_material_stock` material tsb
   - mengonversi `unit_cost` (÷ faktor) dan `min_stock`
   - menulis 1 baris ledger `op: "uom_rebase"` berisi nilai sebelum/sesudah
   - menyusun ulang `uoms` (satuan lama tetap ada sebagai kemasan)
4. **Dapat dibatalkan** — karena ledger menyimpan faktor & nilai lama

Selama belum di-rebase, item tetap berfungsi seperti sekarang. Tidak ada paksaan.

---

## 7. Rencana bertahap

### F0 — Fondasi (nol perubahan perilaku)
- `core/uom.py` + `frontend/src/lib/uom.js`
- Guardrail `verify_uom_integrity.py` (INV-UOM-1..6) + daftar di `INVARIANTS.md`
- Skrip `migrate_material_uoms.py --dry|--execute` — membangun `uoms` dari
  `unit`+`pack_*` untuk 1.031 material. **Tidak menyentuh stok, tidak mengubah
  satuan dasar, idempotent.**
- **Verifikasi:** guardrail hijau · seluruh API material/stok mengembalikan angka
  identik sebelum-sesudah (uji banding otomatis).

### F1 — Editor multi-UOM di form yang sudah ada
- `RahazaMaterialsModule.jsx` (Master Material) & `AccessoryModule.jsx`:
  ganti blok "Item ini dijual/disimpan per kemasan" menjadi **tabel UOM**:
  tambah/hapus baris, pilih induk, isi "isi per induk", pratinjau hierarki
  `1 ktn = 12 bks = 1.728 pcs`, tandai default beli/pakai/tampil.
- Backend `PUT/POST` material: validasi `uoms` + mirror ke `pack_unit`/`pack_size`.
- **Verifikasi:** simpan material lama tanpa menyentuh UOM → dokumen tidak berubah.

### F2 — `stock_service` sadar satuan (opsional)
- Tambah `input_uom=None` pada `add`, `issue`, `adjust`, `move`, `reserve`,
  `release`, `issue_row`.
- Ledger menyimpan `input_qty`, `input_uom`, `uom_factor`.
- **Verifikasi:** semua pemanggil lama tetap lulus regresi (tanpa argumen baru).

### F3 — Pasang di titik input + perbaiki bug harga
- Gudang: Receiving · PO · Putaway · Opname · Pengeluaran Material · Warehouse Smart
- Aksesoris: Opname · Peminjaman · Request Internal *(Terima/Scrap/Pakai sudah ada)*
- Cutting: hapus hardcode `pack_size: 1`
- **BUG-1 & BUG-8**: `cost_to_base()` dipakai di Terima Barang & Purchase Request;
  label UI dibuat eksplisit "Harga per **bks**" / "per **pcs**"
- **Verifikasi:** ulangi skenario uji 1 bks = 144 pcs → nilai persediaan harus
  Rp144.000 (bukan Rp20.736.000) & jurnal benar.

### F4 — Perbaiki konversi global (BUG-3, 4, 5)
- Auto-seed satuan saat startup (pola `ensure_*` seperti Cutting)
- Kebalikan otomatis (`1/factor`) + penelusuran berantai lewat satuan dasar
- Buang `formula_expr` dari docstring (BUG-7) atau implementasikan

### F5 — Aksi "Ubah Satuan Dasar" (§6)
- Endpoint `POST /api/rahaza/materials/{id}/rebase-uom` + dialog pratinjau
- Dipakai owner sesuai kebutuhan untuk 91 item

---

## 8. Daftar periksa regresi per domain

Dijalankan setelah **setiap** fase, bukan hanya di akhir:

| Domain | Yang wajib dicek | Cara |
|---|---|---|
| Gudang / WMS | Stok tidak berubah angkanya; Receiving/Opname/Putaway/Issue normal | testing agent + banding snapshot stok |
| Aksesoris | Terima/Scrap/Pakai/Opname/Pinjam; nilai persediaan; jurnal | uji live + cek JE |
| Produksi | Material Issue → HPP WO | `amount = qty × unit_cost` harus identik |
| RnD | HPP kalkulator dari BOM | banding hasil sebelum-sesudah |
| Finance / HPP | Posting GL dari pergerakan stok | INV-GL invarian existing |
| BOM / MRP | Kebutuhan material teragregasi | angka tidak boleh bergeser |
| Cutting | roll → potongan, HPP potongan | `poc_cutting_flow_v2.py` |
| Maklon / CMT | 18 file tersentuh unit, 0 pack-aware | pastikan tidak ada yang pecah |
| Pengiriman | picklist & surat jalan | tampilan satuan |
| Marketing | 12 file menyentuh `unit` (kemungkinan besar satuan produk jadi) | smoke |

Ditambah guardrail existing yang harus tetap hijau:
`check_nav_map.py` · `verify_rbac_idor.py` · `verify_adversarial_5xx.py` ·
`health_check.py`, plus `verify_uom_integrity.py` yang baru.

---

## 9. Risiko & mitigasi

| Risiko | Dampak | Mitigasi |
|---|---|---|
| 52 titik tulis stok terlewat | stok salah senyap | `input_uom` opsional → yang belum diubah tetap benar (satuan dasar) |
| `unit_cost` berubah makna | HPP & GL 5 modul rusak | INV-UOM-1 + guardrail; `cost_uom` **tidak** disimpan sebagai pengubah makna, hanya alat entri |
| Satuan dasar diubah tanpa konversi stok | korupsi data | rebase hanya lewat aksi khusus + pratinjau + ledger + dapat dibatalkan |
| Faktor diubah setelah ada transaksi | riwayat salah baca | `uom_factor` dibekukan di setiap baris ledger |
| Frontend lama tidak kenal `uoms` | tampilan pecah | field lama tetap di-mirror (L2/L3) |
| Migrasi dijalankan dua kali | data ganda | skrip idempotent + `--dry` wajib dulu |

---

## 10. Yang perlu dikonfirmasi sebelum saya mulai

1. **Satuan dasar untuk item bersatuan kemasan** — saya BIARKAN apa adanya dulu
   (tidak di-rebase otomatis), dan Bapak/Ibu rebase sendiri per item lewat tombol
   saat sudah tahu "1 rol = berapa meter". Setuju?

2. **Urutan fase** — saya usul F0 → F1 → F2 → F3 → F4 → F5.
   F3 memuat perbaikan BUG-1 (harga). Kalau ingin BUG-1 diperbaiki lebih dulu
   karena berisiko finansial, saya bisa sisipkan sebagai F0.5.

3. **Kedalaman hierarki** — cukup 3 level (satuan dasar → bks → karton) atau
   perlu lebih dalam?

4. **`purchase_uom` / `issue_uom` / `display_uom`** — perlu ketiganya, atau cukup
   satu "satuan default" saja supaya form tidak terlalu ramai?

---

# STATUS PELAKSANAAN — 2026-07-27 (SELESAI F0.5 s/d F5)

| Fase | Isi | Status | Bukti |
|---|---|---|---|
| **F0.5** | Perbaikan BUG-1 (harga tidak dikonversi) & BUG-8 (estimasi PR) | **SELESAI** | 4 skenario uji live: 1 bks @144rb → nilai Rp144.000 (sebelumnya Rp20.736.000) |
| **F0** | `core/uom.py` + `frontend/src/lib/uom.js` | **SELESAI** | 8 uji unit BE + 9 uji unit FE, hasil identik |
| **F0** | Guardrail `verify_uom_integrity.py` + `INVARIANTS.md` §U | **SELESAI** | Self-test: 5 kelas pelanggaran sintetis terbukti MERAH → HIJAU setelah revert |
| **F0** | Migrasi 1.031 material | **SELESAI** | Hash snapshot stok/HPP **identik** sebelum-sesudah (`633a0b03704beb2f`); idempotent |
| **F1** | `UomEditor.jsx` 3 tingkat di Master Material & Aksesoris | **SELESAI** | UI: "1 ktn = 12 bks" → faktor 1.728 otomatis; validasi BE menolak 4 jenis input salah |
| **F2** | `stock_service` menerima `input_uom` opsional | **SELESAI** | 6 skenario: pemanggil lama tidak berubah, opname 3 bks → 432 pcs, jejak ledger lengkap |
| **F3** | Konversi di Opname aksesoris, Pengeluaran Material, Receiving Gudang, Cutting | **SELESAI** | `testing_agent_v3`: 44/44 uji lulus, 0 bug |
| **F4** | Konversi global: auto-seed, kebalikan, berantai | **SELESAI** | `pcs→lusin` kini jalan; `gram→ton` lewat kg; kemasan diberi pesan pengarah |
| **F5** | Aksi "Ubah Satuan Dasar" + pratinjau + audit | **SELESAI** | 9 rol → 450 m, HPP 250rb/rol → 5rb/m, **nilai persediaan tetap**, ledger `uom_rebase` |
| **Bonus** | Dropdown Unit disamakan dengan backend (6 → 22 satuan) | **SELESAI** | Bug lama: 136 material bersatuan `rol/pak/lusin/yard` tak bisa diedit tanpa merusak satuannya |

## Verifikasi akhir
```
verify_uom_integrity.py   HIJAU  (1.761 objek, 0 pelanggaran)
check_nav_map.py          HIJAU  (0 pelanggaran blok)
verify_rbac_idor.py       HIJAU  (694 diperiksa, 0 temuan)
testing_agent_v3          44/44 uji backend lulus, 0 bug kritis/UI
migrate_material_uoms.py  idempotent (jalankan lagi → 0 perubahan)
Baseline DB               1.031 material · 730 stok · 730 ledger · 0 jurnal — persis seperti sebelum pengerjaan
```

## Sisa pekerjaan (opsional, butuh input owner)
1. Isi konversi kemasan per item lewat form Master Material (478 item; informasi
   isinya sudah tercantum di nama, mis. `A47 … 1 Bks 144 Pcs`).
2. Rebase 91 item bersatuan kemasan (74 `rol`, 14 `pak`, 3 `lusin`) memakai
   tombol "Ubah satuan dasar" saat faktornya sudah diketahui.
3. Pemasangan `input_uom` di titik masuk stok yang tersisa (Putaway, Warehouse
   Smart, Opname Gudang, Peminjaman & Request aksesoris) — aman ditunda karena
   tanpa argumen tersebut perilakunya tetap benar (satuan dasar).
