# FASE 13 — HIGIENE DATA ALAT UJI (Test-Tooling Data Hygiene)

> **Sesi 2026-07-26** (environment di-clone dari repo `jjaakalamanaba/da`).
> Pemicu: **audit DB mandiri oleh user** menemukan `rahaza_costing_settings` tercemar
> nilai uji (`default_material_cost_per_kg=12345`, `default_accessory_cost_per_unit=77`)
> yang harus dipulihkan **MANUAL**, padahal `cleanup_fase10_qa.py --dry-run` melapor
> "(tidak ada drift)".
> Pilihan user: **"lanjutkan sesuai rekomendasi"** → koreksi baseline ke angka yang
> reproducible dari seeder, lalu tutup ketiga temuan di AKARNYA.

---

## 0. VERIFIKASI DULU (sebelum menyentuh kode)

| Yang diklaim dokumen | Hasil verifikasi nyata |
|---|---|
| `run_all_verifications.sh` = 443 PASS / 0 FAIL | **TERBUKTI** (443 PASS / 0 FAIL di environment segar) |
| `gate.sh` 9/9 HIJAU | **TERBUKTI** |
| ESLint root & `/app/mobile` rc=0 | **TERBUKTI** (0 error, 1285 warning kosmetik) |
| Baseline valuasi aksesoris **Rp 9.667.750 / qty 32.220** | **KELIRU** — environment segar menghasilkan **Rp 9.663.750 / qty 32.200** |
| `cleanup_fase10_qa.py --dry-run` = "data bersih" | **BUTA** terhadap `rahaza_costing_settings` |
| Regresi "SEMUA HIJAU" ⇒ tidak ada residu | **KELIRU** — total stok naik **+2** setiap run |

**Catatan penting:** container sesi ini BARU dan MongoDB-nya kosong total, jadi seluruh
angka di atas dihasilkan ulang dari `bootstrap.sh` (49 detik, 6 login HTTP 200) —
bukan dibaca dari dokumen.

---

## 1. TEMUAN 1 — kebocoran stok + JURNAL GL YATIM di `verify_phase_g_acc_opname.py`

### Bukti empiris (reproduksi di environment segar)
```
sebelum regresi : total_qty 32.950 · costing settings bersih (0/0)
sesudah regresi : total_qty 32.952  (+2)   ← "443 PASS / 0 FAIL SEMUA HIJAU"
cleanup dry-run : ACC-BTN-12 5.005 (+5) · ACC-LBL-01 3.997 (-3) · mutasi QA 2 (jurnal 2)
```
Signature ini **identik** dengan audit user (5.025 = 5.020+5 · 3.997 · 2 mutasi · 2 jurnal) —
membuktikan container user mengalami kebocoran yang sama.

### Akar 1 — approve opname dilakukan pada MATERIAL DEMO NYATA
Baris 99 skrip: *"hitung 2 baris: satu surplus (+5), satu minus (-3)"* mengambil
`lines[0]`/`lines[1]` dari snapshot sesi opname. Di DB ber-seed, dua baris pertama itu
selalu `ACC-BTN-12` & `ACC-LBL-01`. Approve opname **mengubah stok permanen + memposting
jurnal GL**. Log skrip: `count ACC-BTN-12 -> 5005.0 diff +5.0`.

### Akar 2 — `_cleanup()` memakai NAMA FIELD YANG TIDAK PERNAH ADA
```python
{"related_ref": {"$in": session_ids}}     # cocok 0 dokumen
```
`related_ref` hanyalah **nama parameter fungsi** `_log_movement()` di
`routes/dewi_accessories_opname.py:63`; yang TERSIMPAN adalah `reference_id` (baris 88)
dan `ref_id` (baris 89). Dibuktikan di DB:

| query | cocok |
|---|---|
| `{"related_ref": <session_id>}` | **0** |
| `{"reference_id": <session_id>}` | **2** |
| `{"ref.session_id": <session_id>}` (ledger) | **0** |

Karena `gl_je_id` dikumpulkan lewat predikat salah itu, `je_ids` selalu kosong ⇒
`rahaza_journal_lines` & `rahaza_journal_entries` **tidak ikut terhapus** ⇒ buku besar
keuangan menumpuk **jurnal yatim** yang menunjuk sesi opname yang sudah dihapus.

### Akar 3 — cleanup tidak jalan bila skrip gagal
Cleanup dipanggil di jalur sukses saja ⇒ exception / assert gagal / SIGTERM dari
`timeout 900` di runner ⇒ artefak + jurnal tertinggal.

### Yang dikerjakan
* Skrip kini memakai aksesoris uji **miliknya sendiri** (`QA-OPN-A`, `QA-OPN-B`) yang
  dibuat + diberi stok (`POST /api/acc/stock/receive` — `POST /api/acc/items` **mengabaikan**
  `stock_qty`) + harga, lalu dihapus tuntas. Material demo `ACC-*` **tidak pernah** disentuh.
  * Bonus: dulu item QA hanya di-seed bila jumlah aksesoris `< 2` — di DB ber-seed kondisi itu
    **never true**, jadi jalur "aman" itu sebenarnya kode mati.
* Assert baru: *"item uji QA TIDAK menyentuh material demo ACC-*"* → kebocoran serupa
  langsung merah, bukan diam-diam.
* `_cleanup()` pakai `reference_id`/`ref_id`; ledger dibereskan lewat `material_id`.
* `run()` dibungkus `try/finally` ⇒ cleanup **selalu** jalan.
* **Jaring pengaman** `_restore_non_qa_stock()`: bandingkan snapshot awal, pulihkan stok
  material NON-QA yang bergeser, dan buang baris `rahaza_stock_ledger` yang lahir selama run
  (ledger tidak menyimpan id sesi, jadi rentang waktu run adalah satu-satunya penanda aman).

---

## 2. TEMUAN 2 — pencemaran `rahaza_costing_settings` GLOBAL (yang user pulihkan manual)

Nilai `12345`/`77` yang user temukan adalah **milik `verify_fase12.py` sendiri**
(`DEF_KG=12345.0, DEF_ACC=77.0`). Ketiga skrip di bawah meng-PUT nilai uji ke dokumen
GLOBAL lalu memulihkannya **hanya di jalur sukses** — dan **tidak satu pun punya
`try/finally`** (0 kemunculan `finally:`):

| skrip | nilai uji yang bisa tertinggal |
|---|---|
| `verify_fase12.py` | `default_material_cost_per_kg=12345` · `default_accessory_cost_per_unit=77` |
| `verify_fase66.py` | `default_material_cost_per_kg=88000` |
| `verify_fase11.py` | `default_material_cost_per_kg=4321` |

Lebih buruk: run berikutnya menangkap nilai cemar itu sebagai `settings_before` lalu dengan
patuh "memulihkan" 12345/77 ⇒ **pencemaran jadi LENGKET selamanya**. Pola `if settings_before:`
juga **melewatkan pemulihan** bila dokumen semula belum ada (DB segar).

**Dampaknya bukan kosmetik.** Kedua field itu adalah *fallback harga* yang dipakai penghitung
HPP (`production_internal_adapter.compute_hpp_job` & `rahaza_hpp._compute_hpp` lewat
`core/material_fields.read_field`) ⇒ **harga pokok salah DIAM-DIAM, tanpa error** — kelas bug
yang sama dengan BUG-B/BUG-B2 yang baru ditutup FASE 12.

### Yang dikerjakan
`scripts/lib/qa_state_guard.py` — SSOT pelindung state global:
```python
async with preserve_costing_settings(db):
    ...            # bebas meng-PUT nilai uji
# keluar blok (normal ATAU exception) → dokumen kembali PERSIS seperti semula
```
* Pemulihan di `finally`, bukan "kalau semua lancar".
* Dokumen semula `None` ⇒ **dihapus**, bukan dibiarkan berisi nilai uji.
* Dipakai `verify_fase11/12/66` lewat perubahan **satu baris**
  (`async with httpx.AsyncClient(...) as c, preserve_costing_settings(db):`) sehingga
  seluruh blok terlindungi tanpa re-indentasi berisiko.

---

## 3. TEMUAN 3 — baseline "Rp 9.667.750" adalah RESIDU QA, dan `--apply` MENGARANG stok

Environment segar: `ACC-BTN-12 = 5.000`. Baseline dokumen: **5.020**.
Seluruh penulis stok dilacak — **tidak ada** yang pernah menulis lebih dari 5.000:

| penulis | nilai |
|---|---|
| `backend/scripts/link_demo_bom_materials.py:41` | **5000** |
| `backend/routes/rahaza_setup.py:260` | angka `6` = qty **baris BOM**, bukan stok |
| `backend/routes/maklon_seed.py` | tidak menyentuh `ACC-BTN-12` (grep kosong) |

Selisih 20 pcs = **4 run kebocoran × 5 pcs** (Temuan 1). `plan.md:115` sendiri mencatat
*"5.000 di `int-demo-loc-1` + 20 pcs"*. Residu itu lalu dipatok sebagai "angka sah" di
`cleanup_fase10_qa.py:48`.

**Akibatnya di setiap environment segar:**
1. `--dry-run` **selalu** melapor drift ⇒ tidak akan pernah bisa "bersih".
2. `--apply` **menyuntikkan persediaan fiktif**: bagian EKSEKUSI menghapus semua baris stok
   lalu `insert_one` dari baseline ⇒ menulis 5.020 padahal seeder hanya 5.000.
3. `tests/backend_test_fase12.py` hard-assert `9667750 (±100)` & `32220 (±10)` ⇒ **FAIL PASTI**
   (nyata −4.000 & −20).
4. Berkas uji yang sama juga mematok `BASE_URL` ke preview container lama
   (`https://da37-cmt-bridge.preview.emergentagent.com`) yang **sudah mati** ⇒ menguji host salah.

### Yang dikerjakan
* `scripts/lib/acc_baseline.py` — **SSOT tunggal**. Semua total **DITURUNKAN** dari tabel
  `STOCK_BASELINE × COST_BASELINE` (bukan angka yang diketik ulang), dengan `assert` sebagai
  jaring pengaman:
  ```
  TOTAL_QTY = 32.200 · TOTAL_VALUE = 9.663.750 · 8 bernilai / 2 belum dinilai · unvalued_qty 3.300
  ```
* `cleanup_fase10_qa.py` & `tests/backend_test_fase12.py` **mengimpor** SSOT itu ⇒ angka tidak
  bisa lagi menyimpang antar berkas.
* `BASE_URL` dibaca dari `frontend/.env` (`REACT_APP_BACKEND_URL`), fallback localhost,
  override lewat env `BASE_URL`.
* **Bagian 5 baru** di `cleanup_fase10_qa.py`: deteksi + pemulihan drift
  `rahaza_costing_settings` ⇒ audit manual user sekarang **OTOMATIS**.

---

## 4. SENTINEL — supaya tidak kambuh

`scripts/verify_fase13.py` (33 assert, terdaftar **terakhir** di `run_all_verifications.sh`):

| bagian | isi |
|---|---|
| A | SSOT baseline konsisten & `/api/acc/valuation` == SSOT |
| B | `preserve_costing_settings` benar-benar memulihkan **saat exception**, dan **menghapus** dokumen bila semula tidak ada; ketiga skrip verify memakai guard (cek statis) |
| C | **sentinel drift**: jalankan `verify_phase_g_acc_opname.py` lalu buktikan **NOL DRIFT** pada 9 metrik (stok total, stok per-material, mutasi, entri & baris jurnal, material, baris stok, sesi opname, ledger, costing settings) |
| D | tidak ada artefak `QA-*`/sesi `QA verify`, tidak ada **mutasi opname yatim**, tidak ada baris jurnal tanpa induk, dan `_cleanup()` memakai nama field yang benar — diperiksa lewat **AST** (literal string di dalam fungsi, docstring dibuang) supaya bukan sekadar cocok-kata |
| E | `cleanup_fase10_qa.py` memeriksa costing settings, memakai SSOT, dan `--dry-run` bersih di **dua** bagian |

### Sentinelnya sendiri DIUJI (guard yang belum pernah merah bukan guard)
Bug lama sengaja ditanam ulang (`t1, t2 = lines[0], lines[1]`) → sentinel **MERAH** di tiga
tempat sekaligus:
```
❌ C1 verify_phase_g_acc_opname.py exit 0   — rc=1
❌ C2 skrip itu sendiri 0 FAIL              — HASIL: 48 PASS / 1 FAIL
❌ C3 NOL DRIFT                             — {'stock_ledger': (0, 2)}
```
Sekaligus membuktikan jaring pengaman bekerja: `~ 34f8182e… stok 3997.0 → 4000.0 (koreksi +3)`.
Sesudah bug dikembalikan ke versi benar: **33 PASS / 0 FAIL**.

---

## 5. BUKTI

| Uji | Hasil |
|---|---|
| `scripts/verify_phase_g_acc_opname.py` | **49 PASS / 0 FAIL** (dulu 45) · cleanup **13 → 35** artefak |
| `scripts/verify_fase13.py` | **33 PASS / 0 FAIL** · terbukti MERAH saat bug ditanam ulang |
| Drift sesudah menjalankan skrip opname | **NOL** pada 9 metrik |
| `/api/acc/valuation` | `total_qty 32.200` · `total_value Rp 9.663.750` · 8 bernilai / 2 belum — **cocok SSOT** |
| `cleanup_fase10_qa.py --dry-run` | 0 mutasi QA · **(tidak ada drift)** stok/HPP **dan** costing settings |
| `run_all_verifications.sh` (11 skrip) | lihat §6 |
| `scripts/gate.sh` | lihat §6 |

---

## 6. STATUS AKHIR & SISA PEKERJAAN

### Hasil verifikasi akhir (environment segar, semua dijalankan ulang dari nol)

| Uji | Sebelum FASE 13 | **Sesudah FASE 13** |
|---|---|---|
| `scripts/run_all_verifications.sh` | 443 PASS / 0 FAIL (10 skrip) | **480 PASS / 0 FAIL (11 skrip) — SEMUA HIJAU** |
| `scripts/verify_phase_g_acc_opname.py` | 45 PASS · cleanup 13 artefak | **49 PASS / 0 FAIL · cleanup 35 artefak** |
| `scripts/verify_fase13.py` | (tidak ada) | **33 PASS / 0 FAIL** |
| `scripts/gate.sh` | 9/9 HIJAU | **SEMUA GATE HIJAU** (`memory/GATE_RECEIPT.md`) |
| **Drift sesudah regresi penuh + `gate.sh`** | **+2 qty · +2 mutasi · +2 jurnal GL yatim** | **NOL pada 9 metrik** |
| `cleanup_fase10_qa.py --dry-run` | "tidak ada drift" (padahal buta) | **bersih di bagian 4 DAN 5** |
| `/api/acc/valuation` | Rp 9.667.750 (tidak reproducible) | **Rp 9.663.750 · qty 32.200 — cocok SSOT** |
| ESLint root + `/app/mobile` | rc=0 | **rc=0 / rc=0 (0 error)** |

9 metrik yang dipantau sentinel: `total_qty` · stok per-material · `rahaza_material_movements` ·
`rahaza_journal_entries` · `rahaza_journal_lines` · `rahaza_materials` · `rahaza_material_stock` ·
`wh_opname_sessions2` · `rahaza_stock_ledger` — plus `rahaza_costing_settings`.

**Ini pertama kalinya regresi penuh repo ini tidak meninggalkan jejak apa pun di DB.**
Konsekuensi praktis: `cleanup_fase10_qa.py` tidak lagi dibutuhkan sebagai *plester* sesudah
setiap ronde uji — ia sekarang murni alat audit (dan `--dry-run`-nya sudah bisa dipercaya).

### Sisa pekerjaan (urutan yang direkomendasikan)
1. **Bukti verifikasi email SUNGGUHAN** via `aiosmtpd` lokal (lampiran Excel + PDF).
2. **Perluas Jest/RTL** ke `AccessoryValuationAutomation` + `StokOpnameTab`.
3. **Tech-debt advisory**: `numeric_bounds` MED 10 (field uang Pydantic tanpa `ge=`),
   `fe_be_contract` HIGH 9, `static_antipatterns` MED 263.
4. **Drop `accessory_legacy`** di DB PRODUKSI user (di preview no-op).
5. **Observasi tambahan (belum ditindak):** notifikasi "Harga satuan belum diisi" menumpuk
   **4 duplikat per item** untuk 2 item yang sengaja belum dinilai (8 dokumen). Kandidat
   idempotensi/dedup — bukan risiko finansial, jadi tidak diprioritaskan sesi ini.

