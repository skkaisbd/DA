# FASE 12 — Rekonsiliasi Peta Lokasi Stok + 3 Bug Alias/HPP

> **Sesi 2026-07-26** (environment dipulihkan dari repo `jajanamakamana/da`).
> Pilihan user: **(A)** perbaiki BUG-A + BUG-B & jadikan seed baseline valuasi bagian
> `bootstrap.sh`, lalu **(C)** rekonsiliasi lokasi stok aksesoris.
> Bukti: `scripts/verify_fase12.py` **31 PASS / 0 FAIL** ·
> `scripts/run_all_verifications.sh` **443 PASS / 0 FAIL (SEMUA HIJAU)** ·
> `scripts/gate.sh` **9/9 HIJAU** · valuasi aksesoris kembali **PERSIS Rp 9.667.750**.

---

## 0. VERIFIKASI DULU (sebelum menyentuh kode)

| Yang diklaim dokumen | Hasil verifikasi nyata |
|---|---|
| `run_all_verifications.sh` = 410 PASS / 0 FAIL | **401 PASS / 9 FAIL** |
| `bootstrap.sh` menyiapkan semua data uji | **TIDAK** — baseline valuasi aksesoris tak pernah di-seed ⇒ 8 FAIL PALSU |
| Alias `yarn_*` sudah berhenti ditulis (FASE 11) | **BOCOR** — seeder maklon masih menulisnya |
| `scripts/migrate_stock_locations_to_wh.py` (alat backlog #3) | **TIDAK PERNAH ADA** di repo |
| ESLint hidup | **MATI** dari `/app/mobile` (exit 2 ⇒ dibaca "linter engine error") |

**Pelajaran:** angka pada dokumen serah-terima harus selalu diuji ulang dari nol.
Empat dari lima klaim di atas keliru.

---

## 1. BUG-A — seeder menulis alias legacy `default_yarn_cost_per_kg`

* **Gejala:** `verify_fase66.py` B8 merah: `rahaza_costing_settings.default_yarn_cost_per_kg = 1 dok`.
* **Akar:** `routes/maklon_seed.py` menulis kunci legacy secara **harfiah**
  (`'default_yarn_cost_per_kg': 0`), tidak lewat SSOT `material_fields.mirror()`.
  Jadi kontrak FASE 11 ("alias tidak ditulis lagi") dilanggar **di setiap DB baru**.
* **Fix:** `**material_fields.mirror('default_material_cost_per_kg', 0)`.
  Kalau suatu hari alias perlu dihidupkan lagi, cukup isi `WRITE_ALIASES` — nol perubahan route.
* **DB dibersihkan:** `migrations/migrate_rename_yarn_fields.py --execute` lalu `--drop-legacy --yes`
  ⇒ `--discover` bersih.
* **Sweep menyeluruh (bukan sampel):** seluruh `backend/**.py`, `frontend/src/**` dan `scripts/**`
  dipindai untuk 6 nama legacy. Sisa temuan hanya komentar, variabel lokal, dan jalur
  "terima legacy lalu buang" yang memang disengaja. `_archive/` diabaikan.

## 2. BUG-B — HPP job internal diam-diam memakai harga bahan 0

* **Gejala:** tidak ada error. HPP job internal hanya "kelihatan murah".
* **Akar:** `routes/production_internal_adapter.py::compute_hpp_job` membaca
  `settings.get('default_yarn_cost_per_kg')` **langsung**. Sejak FASE 11 alias itu tidak
  ditulis lagi ⇒ nilainya selalu `None` ⇒ fallback harga bahan jatuh ke **0**.
* **Fix:** `material_fields.read_field(settings, 'default_material_cost_per_kg', 0)`
  (rantai baca kanonik → legacy, aman untuk DB lama).

## 3. BUG-B2 (BARU, ditemukan saat memperbaiki BUG-B) — fallback salah kategori

* Dua penghitung HPP memakai daftar tipe yang **lebih sempit** dari taksonomi resmi:
  * `routes/rahaza_hpp.py` → `type == "yarn"` saja;
  * `routes/production_internal_adapter.py` → `type in ("yarn","fabric")`.
* Akibatnya material `kain` / `benang` / `interlining` tanpa `unit_cost` diberi
  **fallback harga AKSESORIS (per unit)**, bukan harga bahan (per kg) ⇒ HPP salah tanpa error.
* **Fix:** SSOT baru `core/material_fields.is_kglike_material(doc)` (menerima dokumen master
  `type` maupun baris BOM `material_type`, dan menghormati satuan `kg`) dipakai kedua penghitung.

## 4. BUG-C — linter engine mati dari `/app/mobile`

* `mobile/eslint.config.js` fallback-nya `[{ ignores: ['**/*'] }]` ⇒ `npx eslint .` keluar
  **exit code 2** ("all of the files matching the glob pattern '.' are ignored") — dibaca tool
  platform sebagai **linter engine error**, bukan lint error.
* **Fix:** fallback tetap melint berkas JS biasa (tanpa aturan ⇒ selalu 0 problem) dan hanya
  mengabaikan TS/TSX yang butuh parser Expo. Sekarang `mobile` rc=0, root rc=0
  (0 error, 1285 warning kosmetik — baseline lama).

## 5. FASE 12 UTAMA — penyakit ke-8 `unmapped_location` (backlog #3)

### Masalahnya apa
`ACC-BTN-12` / `ACC-LBL-01` / `ACC-DA-LBL` (dan 2 baris bahan) menyimpan stok di
`int-demo-loc-1` = `GDG-UTAMA-DEMO`. Lokasi itu **bukan zona penyimpanan**:
`location_resolver.list_storage_locations()` hanya memuat `STORAGE_RAHAZA_CODES`
(`ZNA-KAIN`/`ZNA-AKSESORIS`/`ZNA-FG`/`ZNA-SAMPLE`), sehingga stok di sana **tidak pernah muncul**
di Put-Away, Opname per-bin, maupun dropdown lokasi. Totalnya benar, petanya menyesatkan.
Ini juga pemicu BUG-1 FASE 10 (pengeluaran aksesoris HTTP 500 saat stok tersebar).

### AKAR yang ditutup (bukan sekadar dirapikan sekali)
| Penulis | Dulu | Sekarang |
|---|---|---|
| `routes/maklon_seed.py` | stok demo & pemotongan MI ke `int-demo-loc-1` | `_storage_zone_for()` → zona kanonik per kategori material |
| `backend/scripts/link_demo_bom_materials.py` | `DEMO_LOC = "int-demo-loc-1"` | `zone_for(mtype)` via SSOT; pseudo-lokasi hanya jaring pengaman terakhir |
| `scripts/cleanup_fase10_qa.py` | `STOCK_BASELINE` mematok `int-demo-loc-1` | `__ACC__` (zona aksesoris kanonik) — kalau tidak diperbarui, `--apply` justru **membatalkan** rekonsiliasi |

### Alat yang dipakai — memperluas yang sudah ada, bukan skrip sekali pakai
Backlog menyebut `scripts/migrate_stock_locations_to_wh.py`; skrip itu **tidak pernah ada**.
Daripada membuat skrip sekali-jalan, kemampuannya ditanam ke alat yang sudah punya
pratinjau → terapkan → **rollback presisi** + UI: modul **Kesehatan Skema Stok**
(`wh-stock-schema`, endpoint `/api/wms/stock-schema/*`).

* **`core/location_resolver.storage_location_index(db)`** — SSOT klasifikasi lokasi:
  * `storage` — zona penyimpanan resmi (kanonik `wh_*` atau legacy `ZNA-*`), termasuk bin di dalamnya;
  * `exempt` — lantai produksi (`ZNA-CUTTING/SEWING/QC/PACKING`) & karantina QC ⇒
    **tidak pernah dipindah otomatis** (barang di sana memang belum/tidak di rak);
  * `unmapped` — bukan zona penyimpanan mana pun (gudang demo warisan, gedung konsep,
    atau id lokasi yang sudah dihapus).
  Plus `classify_location()` dan `describe_location()`.
* **`core/stock_reconcile`** — penyakit ke-8 `unmapped_location`: pindahkan baris ke zona kanonik
  sesuai kategori material, lalu langkah "gabung kembar" yang sudah ada menyatukan bila baris
  tujuan sudah eksis (urutan hapus-dulu-baru-tulis tetap dipakai supaya tidak kena
  `DuplicateKeyError` pada unique index `(material_id, location_id)`).
* **PENGAMAN penting** (ditemukan karena `verify_fase66.py` jadi merah — bukti gate itu bekerja):
  baris **qty negatif** dan **material yatim** TIDAK ikut dipindah. Memindah + menggabungkan baris
  negatif akan **diam-diam mengurangi** stok zona tujuan sehingga selisih yang seharusnya diputuskan
  manusia hilang dari radar; baris yatim tidak punya kategori ⇒ zona tujuan tak bisa ditentukan.
  Keduanya juga tidak dihitung sebagai `unmapped_location` supaya `fixable_issues` bisa mencapai nol.

### UI (`StockSchemaHealthModule.jsx`)
* Kartu **"Peta lokasi stok"**: tiap lokasi + badge status (Zona penyimpanan / Produksi-Karantina /
  Bukan zona penyimpanan) + jumlah baris + total qty, dan chip zona tujuan per kategori.
* Kolom baru **"Usulan zona"** di tabel detail (`→ ZNA-AKSESORIS`).
* Kartu rencana menampilkan **"Baris dipindah zona"** + daftar `DARI → KE · qty`.
* Riwayat rekonsiliasi mendapat kolom **"Dipindah"**.

### Hasil eksekusi pada data nyata
```
5 baris dipindah · 1 baris kembar digabung
GDG-UTAMA-DEMO → ZNA-KAIN       450 · 300
GDG-UTAMA-DEMO → ZNA-AKSESORIS  1.800 · 5.000 · 3.997
total on-hand 33.020 → 33.020 (total_qty_preserved = true)
```
Sesudahnya: `affected_rows = 0`, hanya `ZNA-AKSESORIS` + `ZNA-KAIN` yang menyimpan stok,
valuasi aksesoris **Rp 9.667.750** (8 bernilai / 2 belum dinilai) — persis baseline dokumen.

## 6. HIGIENE ALAT UJI (dua bug tooling nyata)

1. **`bootstrap.sh` tidak menyeed baseline valuasi aksesoris** ⇒ `verify_fase10_digest_report.py`
   selalu 8 FAIL palsu di environment segar. Sekarang bootstrap menjalankan
   `scripts/seed_acc_valuation_baseline.py` (idempoten).
2. **`run_all_verifications.sh` tidak membersihkan artefak `verify_phase6_quarantine.py`** ⇒
   jalanan KEDUA menghitung stok dua kali ("stok storage turun jadi 78 — 146.0") dan tampak regresi.
   Sekarang ada peta `POST_CLEANUP` yang otomatis menjalankan `cleanup_test_f6.py --apply`.
   `verify_fase12.py` juga ditambahkan ke daftar.
3. Dua tes usang diperbaiki: `backend/tests/test_material_requirements.py` dan
   `backend/test_mrp_fase5.py` masih mengharapkan alias `total_yarn_kg` yang sudah tidak ditulis.

## 7. BUKTI

| Uji | Hasil |
|---|---|
| `scripts/verify_fase12.py` | **31 PASS / 0 FAIL** |
| `scripts/run_all_verifications.sh` (10 skrip) | **443 PASS / 0 FAIL — SEMUA HIJAU** |
| `scripts/gate.sh` | **9/9 HIJAU** (`memory/GATE_RECEIPT.md`) |
| `scripts/sweep_query_robustness.py` | 0 error 500 |
| ESLint root & `/app/mobile` | rc=0 / rc=0 |
| Audit DB mandiri | 0 artefak uji tersisa · valuasi Rp 9.667.750 · peta gudang bersih |
| Verifikasi UI (Playwright) | peta lokasi, usulan zona, rencana perpindahan, riwayat "Dipindah" |

## 8. SISA PEKERJAAN (tidak dikerjakan sesi ini — pilihan user)

1. Bukti verifikasi email SUNGGUHAN (SMTP masih kosong; pakai `aiosmtpd` atau kredensial nyata).
2. Drop koleksi `accessory_legacy` di DB produksi (di preview no-op).
3. Perluas Jest/RTL ke `AccessoryValuationAutomation` + `StokOpnameTab`.
4. Tech-debt advisory (tidak mem-blok gate): `fe_be_contract` HIGH 9 · `static_antipatterns` MED 263 ·
   `effort_quality` HIGH 1 · `numeric_bounds` MED 10.
