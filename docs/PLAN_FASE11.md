# FASE 11 — ROBUSTNESS & KEBERSIHAN KONTRAK DATA

> **Status:** ✅ SELESAI & TERUJI — 2026-07-25 (sesi lanjutan #4)
> **Prasyarat:** FASE 10 tuntas (lihat `docs/PLAN_FASE10_NEXT_ACTIONS.md` + `HANDOFF_NEXT_AGENT.md`).
> **Ringkasan sesi:** verifikasi ulang klaim FASE 10 (TERBUKTI), lalu menutup BUG-R11-A sampai
> tuntas dan menemukan **2 bug baru yang belum pernah tercatat siapa pun** (BUG-4 & BUG-5).

---

## 0. VERIFIKASI KLAIM SESI SEBELUMNYA (dilakukan lebih dulu)

Sebelum menulis kode apa pun, klaim FASE 10 diuji ulang dari nol pada environment yang
dipulihkan penuh dari repo `yogadevelopment02-bit/da`:

| Yang diklaim sesi lalu | Hasil verifikasi saya |
|---|---|
| 402 PASS / 0 FAIL pada 9 skrip regresi | ✅ **TERBUKTI** — angka identik |
| login 6 akun HTTP 200 | ✅ TERBUKTI |
| backend healthy + static bundle + seed | ✅ TERBUKTI (setelah rebuild environment) |

**Temuan dokumentasi:** `memory/BUG_REGISTRY.md` masih menandai **BUG-R11-B**, **BUG-R11-SM-1**,
**BUG-R11-SM-2**, dan **P3 ap-invoices** sebagai 🔴/🟡 **OPEN**, padahal probe langsung
(`scripts/probe_open_bugs.py`) menunjukkan keempatnya **sudah sehat**. Dokumen **usang**, bukan
bug. Registry sudah diperbarui.

---

## 1. BUG-R11-A — DITUTUP TUNTAS (bukan lagi sampel)

### Kenapa sesi lalu mengira sudah beres
Sesi sebelumnya menguji dengan **8 sampel endpoint**; 7 di antaranya kebetulan yang sudah
diperbaiki, jadi terlihat hijau. Padahal perbaikan sistemiknya belum menyentuh semua endpoint.

### Cara membuktikan secara jujur
Alat baru **`scripts/sweep_query_robustness.py`** menyapu **SELURUH** GET endpoint dari
`/api/openapi.json` (898 endpoint) × **8 varian query rusak** = **7.184 request**, read-only.

| Varian | Contoh | Kelas akar masalah |
|---|---|---|
| `limit_neg` | `?limit=-1` | `to_list(length=-1)` → "length must be non-negative" |
| `limit_str` | `?limit=abc` | `int()` manual tanpa try/except |
| `skip_str` | `?skip=zzz` | idem |
| `page_neg` | `?page=-5` | offset negatif |
| `year_str` | `?year=abcd` | idem |
| `month_oob` | `?month=99` | `date(y, 99, 1)` → "month must be in 1..12" |
| `date_bad` | `?date_from=notadate` | `fromisoformat` tanpa guard |
| `limit_huge` | `?limit=999999999999` | batas atas tak dibatasi |

### Hasil

| | Sebelum | Sesudah |
|---|---|---|
| Request 5xx | **66** | **0** |
| Endpoint bermasalah | **51** | **0** |
| 4xx (ditolak rapi) | 2.471 | 2.536 |
| 503 by-design (`/api/push/vapid-public-key`) | dihitung bug | dikenali benign, dilaporkan terpisah |

**Catatan kejujuran:** dari 51 "endpoint bermasalah" versi pertama, **5 di antaranya adalah
false positive** — endpoint LLM (`/api/finance/ai-cashflow` ≈ 20 detik) menahan slot koneksi saat
sweep paralel sehingga tetangganya time-out (`status=-1`). Diprobe satu per satu, semuanya
200/404 dalam < 10 ms. Endpoint LLM kini masuk `SKIP_SUBSTRINGS` **dan** diuji SERIAL di
`verify_fase11.py` BAGIAN 3 (memastikan validasi menolak **sebelum** model dipanggil — terbukti
ditolak dalam 0,05 detik, jadi tidak ada biaya LLM yang terbuang).

### Perbaikan
* **Helper baru `backend/utils/query_guards.py`** — `q_int`, `q_float`, `q_bool`, `q_date`,
  `q_year_month`, `q_period`, `to_date`, `date_key`. Semua melempar `HTTPException(400)` dengan
  pesan berbahasa Indonesia yang menyebut nama parameter + nilai yang ditolak.
* **46 endpoint di 36 file router** diperbaiki:
  * parameter yang **dideklarasikan** → diberi batas `Query(..., ge=…, le=…)` (FastAPI balas 422 rapi);
  * endpoint yang membaca `request.query_params` sendiri → memakai `q_int`/`q_date`;
  * `marketing_livehost_analytics.py` → helper `_month_bounds()` menggantikan **5 salinan**
    `month.split('-')` + `calendar.monthrange(int(...))` yang tak terjaga.
* Bonus: `marketing_reports.py` **export-pdf** ikut diperbaiki walau sweep melewatinya
  (pola `/export` di-skip) — bug yang sama, ditemukan lewat pembacaan kode.

---

## 2. BUG-4 (BARU) — `datetime` adalah SUBCLASS `date`

**Gejala:** `GET /api/dewi/cmt/lifecycle` membalas **HTTP 500 pada request POLOS**, tanpa
parameter apa pun. Belum pernah tercatat di dokumen mana pun.

**Akar:**
```python
def _parse_date(v):
    if isinstance(v, date):   # ← True JUGA untuk datetime!
        return v              #   objek datetime lolos apa adanya
    return date.fromisoformat(str(v)[:10])
```
Di Python `datetime` **turunan** dari `date`. Dokumen Mongo menyimpan `deadline_date` sebagai
string `'2026-07-23'` (→ `date`) tetapi `updated_at` sebagai BSON datetime (→ `datetime`).
Perbandingan `datetime <= date` melempar `TypeError` → 500.

Setelah lapisan pertama diperbaiki, muncul lapisan kedua dari keluarga yang sama:
`(j.get('completed_at') or j.get('updated_at') or '')[:10]` — **datetime tidak bisa di-slice**
(`TypeError: 'datetime.datetime' object is not subscriptable`).

**Perbaikan:**
* `to_date()` / `_parse_date()` — cek `datetime` **sebelum** `date`, selalu kembalikan `date` murni.
* `_date_key()` baru — kunci perbandingan seragam `'YYYY-MM-DD'` untuk str/date/datetime, dipakai
  di semua tempat yang dulu memotong string dan di 2 `sorted(key=…)` yang bisa membandingkan
  tipe campuran.
* Diterapkan di **3 file** yang punya jebakan identik:
  `routes/dewi_cmt_lifecycle.py`, `routes/rahaza_ar_360.py`, `routes/production_control_tower.py`.

**Kejujuran soal dampak:** dua file terakhir **belum meledak di preview** semata-mata karena
datanya masih kosong (`rahaza_ar_invoices.due_date` semuanya `None`). Di DB produksi yang datanya
nyata, jebakan itu aktif. Modul UI `cmt-lifecycle` sendiri saat ini **redirect** ke `vendor-admin`,
jadi endpoint-nya belum terpakai langsung dari layar — tetapi endpoint-nya hidup dan balas 500.

---

## 3. BUG-5 (BARU) — kode akun modul Aset tidak ada di CoA

**Gejala:** gate `verify_data_integrity` **INV-GL-3 MERAH**: baris jurnal memakai `account_code`
yang tidak ada di Chart of Accounts.

**Akar:** modul Aset menulis kode akun **hardcode 4-digit** — `"1500"`, `"1100"`, `"1590"`,
`"8100"`, `"6300"` — padahal CoA proyek ini memakai format bersegmen (`"1-2500"`, `"1-110"`,
`"2-1100"`, …). **Tidak satu pun** dari kode itu ada di 264 akun CoA. Modul Aset juga satu-satunya
yang **melewati** sistem `rahaza_posting_profiles`, padahal profil `asset_acquisition` dan
`asset_disposal` **sudah ada dan kodenya sudah valid**.

**Dampak nyata:** setiap pembelian & disposal aset menghasilkan jurnal yang menunjuk **akun hantu**
— tidak muncul di Buku Besar/Neraca Saldo per akun, dan gate integritas merah terus sehingga
temuan lain ikut tenggelam.

**Perbaikan:** modul baru `backend/routes/asset/_accounts.py` — `resolve_asset_accounts(db)`
mengambil kode dari posting profile (SSOT), memvalidasinya terhadap CoA, memakai fallback yang
sudah dipastikan ada, dan mengambil **nama akun langsung dari CoA**. Dipakai di
`assets_core.py` (pembelian) dan `disposal.py` (2 jalur: dispose langsung & approve request).

**Bukti:**
```
Pembelian  JE  1-2500 Inventaris Kantor            Dr 1.000.000
               1-110  Kas Kecil                              Cr 1.000.000
Disposal   JE  1-2501 Akum. Penyusutan Inventaris  Dr         0
               1-2500 Inventaris Kantor                       Cr 1.000.000
               1-110  Kas Kecil                    Dr   300.000
               6-4200 Kerugian Penjualan Aset Tetap Dr  700.000
           → seimbang (Dr 1.000.000 = Cr 1.000.000), SEMUA kode ada di CoA
```

---

## 4. FASE 11.C — ALIAS LEGACY `yarn_*` DIHENTIKAN (permintaan user)

Prasyarat `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` §5 diperiksa satu per satu:

1. **Penulisan alias terpusat?** ✅ semua write lewat `material_fields.mirror()` /
   `mirror_from_body()` / `with_aliases()`. Kemunculan `yarn_` lain di route ternyata hanya
   **nama variabel lokal**, komentar, atau kunci sub-dokumen BOM legacy (`yarn_materials`) yang
   merupakan konsep berbeda.
2. **Semua pembacaan lewat helper?** ✅ `read_field()` (BE) / `readField()` (FE).
3. **Data siap?** ✅ `migrate_rename_yarn_fields.py` melaporkan **0 dokumen** perlu backfill.

**Yang dilakukan:**
* `WRITE_ALIASES = {}` → `mirror()` hanya menulis nama kanonik.
* `with_aliases()` berubah arti: mengangkat nilai legacy → kanonik, lalu **membuang** kunci legacy
  dari response.
* `LEGACY_READ_ALIASES` **DIPERTAHANKAN** → `read_field()` masih bisa membaca dokumen lama
  (restore backup / DB produksi yang belum dimigrasi). Ini jaring pengaman, bukan setengah jalan.
* Endpoint **tetap MENERIMA** nama legacy dari klien lama (kompatibilitas masuk).
* Mode baru `migrate_rename_yarn_fields.py --drop-legacy [--yes]` dengan **palang pengaman**:
  menolak jalan bila masih ada dokumen yang HANYA punya kunci legacy. Dijalankan di preview →
  6 kunci dihapus, `--discover` kini bersih.
* Sisi frontend: `lib/materialFields.js` (`WRITE_ALIASES = {}`) + `RahazaHPPModule.jsx` berhenti
  mengirim `default_yarn_cost_per_kg`.

**Cara membalik (bila integrasi eksternal Anda ternyata masih butuh):** cukup isi ulang
`WRITE_ALIASES` di `core/material_fields.py` — **tidak perlu menyentuh satu pun file route**.

---

## 5. PERBAIKAN ALAT UJI (bukan produk) — supaya gate jujur

| Masalah | Perbaikan |
|---|---|
| `verify_acc123.py` membuat aset uji yang **memicu jurnal**, tapi jurnalnya tak pernah dihapus → 3 JE yatim membuat INV-GL-3 merah di sesi berikutnya | cleanup kini ikut menghapus `rahaza_journal_entries` + `rahaza_journal_lines` bertanda `TEST-ACC` |
| `verify_concurrency.py` CC5 menguji endpoint **reservasi material per-WO** yang sudah DIPENSIUNKAN di FASE 4 (E10) — router diarsip, indeks dihapus, koleksi tidak ada, modul FE diarsip. Dilaporkan **FAIL** sejak ≥ 2026-07-16 | 404/405 kini **SKIP dengan alasan eksplisit** (SKIP ≠ PASS) |
| `verify_cross_entity.py` melaporkan HIGH "orphan FK" untuk AR invoice maklon — padahal `mk-client-demo-1` **ada** di `dewi_maklon_clients`, hanya bukan di `rahaza_customers` | relasi kini boleh punya **beberapa koleksi induk** yang sah → 0 temuan |
| `verify_fase66.py` §B masih menguji kontrak LAMA (alias wajib ditulis) | ditulis ulang ke **kontrak FASE 11** + 1 assertion baru: DB tidak menyimpan kunci `yarn_*` lagi (48 → 56 PASS) |
| `run_all_verifications.sh` skrip terakhir kena HTTP 429 (rate limit login 10/60 dtk) | jeda antar skrip 12 → 25 detik |
| `mobile/eslint.config.js` mati total bila dependensi Expo belum dipasang → "linter engine error" mematikan SELURUH gate lint | config menurun dengan anggun (try/catch) |

---

## 6. BUKTI AKHIR

| Gate | Hasil |
|---|---|
| `scripts/sweep_query_robustness.py` | **7.184 request · 0 error 500 · 0 error jaringan** |
| `scripts/verify_fase11.py` (baru) | **108 PASS / 0 FAIL** |
| 9 skrip regresi (`run_all_verifications.sh`) | **410 PASS / 0 FAIL** |
| `scripts/gate.sh` | **9/9 HIJAU** (sebelumnya 2 MERAH) — `memory/GATE_RECEIPT.md` |
| `ruff check backend --select F821,F811,F823` | All checks passed |
| `npx eslint .` (root & frontend) | 587 file, **0 error** |

---

## 7. YANG SENGAJA TIDAK DIKERJAKAN (atas pilihan user)

* **Bukti email sungguhan** — user memilih *"Lewati dulu"*. SMTP tetap kosong; sistem membalas
  `skipped_no_smtp` + notifikasi in-app (perilaku benar, bukan bug). Belum ada bukti lampiran
  Excel+PDF benar terkirim.
* **Drop koleksi `accessory_legacy` di DB produksi** — user memilih *"Lewati"*. Di preview no-op
  (koleksinya memang tidak ada).

## 8. SISA PEKERJAAN (untuk sesi berikutnya)

1. Rekonsiliasi lokasi stok aksesoris `int-demo-loc-1` → zona kanonik `ZN-AKS`
   (`scripts/migrate_stock_locations_to_wh.py`). Aman sejak BUG-1 diperbaiki, tapi peta gudang
   masih berantakan.
2. Perluas Jest/RTL ke `AccessoryValuationAutomation` + `StokOpnameTab`.
3. Advisory tech-debt yang masih terbuka (tidak mem-blok gate, sudah lama ada):
   `fe_be_contract` HIGH 9 · `static_antipatterns` MED 263 · `effort_quality` MED 16 + HIGH 1
   (`poc_variant_ssot.py` memakai literal `mongodb://`) · `numeric_bounds` MED 10 (field uang
   Pydantic tanpa `ge=`, mis. `dewi_cmt_permak.py`).
4. Verifikasi email sungguhan (SMTP dummy atau kredensial nyata) bila sewaktu-waktu dibutuhkan.
