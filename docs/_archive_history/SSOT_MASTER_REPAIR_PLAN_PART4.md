# 🔧 SSOT MASTER REPAIR PLAN — PART 4
## Full-Scope Sweep: 954 GET Endpoint · Klasifikasi Menyeluruh 47/216/15 · 5 Crash 500 · Cascade COA Fresh-Deploy

> **Status:** RENCANA + BUKTI EMPIRIS TERVERIFIKASI. **BELUM ada perubahan kode runtime** (konvensi Part 1–3).
> **Melanjutkan:** `SSOT_MASTER_REPAIR_PLAN.md` (RC-01…07 + Golden Rules + Registry inti) · `PART2` (RC-08…14 + Roadmap W-A..H + Appendix) · `PART3` (RC-15…18 Marketing/RnD/WMS + aturan klasifikasi).
> **Repair Card baru:** **RC-19 … RC-29** (+ Koreksi K7–K13 + Dormant/False-Positive Registry tambahan + Roadmap **Wave J**).
> **WAJIB baca Part 1 dulu** (Golden Rules & SSOT Registry inti TIDAK diulang di sini — dokumen ini hanya DELTA).
> **Tanggal forensik:** 2026-07-02 · fresh deploy ke-3 dari repo `da` → baseline **identik** Part 3 (bukti reprodusibilitas §0.3).

---

# BAGIAN 0 — KONTEKS, METODOLOGI, CAKUPAN & BATAS KEJUJURAN

### 0.1 Apa yang BELUM dicakup Part 1–3 (alasan Part 4 ada)
Part 1–2 = jalur uang & operasi inti (deep-dive per-file). Part 3 = 3 domain (Marketing/RnD/WMS, 189 GET). Keduanya **sampling terarah**. Part 4 menutup sisanya dengan **sweep menyeluruh**:
1. **SEMUA operasi GET di openapi** (1663 path → 958 GET op → **954 diuji = 99.6%**; 4 sisanya butuh path-param yang tak dapat diresolusi).
2. **Klasifikasi SEMUA koleksi kosong** (421 koleksi kosong yang disentuh kode → dipilah dead-read/dormant/orphan via analisis reader–writer full-codebase, bukan tebakan).
3. **Crash 500 nyata** yang belum pernah terdokumentasi (5 endpoint) + **1 crash render FE** + **2 kegagalan senyap UX** (toast sukses palsu, empty-state menyesatkan).
4. **Bug fresh-deploy paling kritis** yang tak terlihat di sesi-sesi sebelumnya karena DB lama masih berisi: **RC-21 cascade COA**.

### 0.2 Metodologi (identik 5-dimensi Part 1, dieksekusi via 3 STEP)
- **STEP B** — uji param-GET 3 domain + write-flow: **B1** (detail endpoint dgn ID nyata dari DB) + **B2** (write-flow RnD: create→verify→cleanup; HANYA 2 flow — lihat batas §0.4).
- **STEP C** — verifikasi render UI nyata via Playwright deep-link `#<module-id>` (login → set hash → reload; metode terbukti setelah navigasi-by-label gagal 9/10).
- **STEP D** — sweep 954 GET sebagai superadmin + klasifikasi reader–writer seluruh codebase (`migrations/d_full_scope_forensics.py` + `migrations/d2_phantom_classifier.py`, keduanya **permanen** & read-only).

**Distribusi hasil STEP D (954 GET):**
`OK_DATA=465 · OK_EMPTY=237 · 500=5 · 502=1 · 503=1 · 404=116 · 401=24 · 409=16 · 403=7 · 422=22 · 400=10 · NO_ID=49 · TIMEOUT=1`

**Klasifikasi koleksi kosong (`d2_phantom_classifier.py`):** populated=143 · **READ-ONLY-EMPTY=47** (kandidat dead-read/misroute) · **SELF-CONSISTENT-EMPTY=216** (dormant — **JANGAN repoint**) · **WRITE-ONLY=15** (orphan write).

### 0.3 Baseline seed (fresh deploy ke-3 — REPRODUSIBEL)
Prosedur identik Part 3: `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo` (sebagai superadmin). Hasil **identik**:

| Koleksi | Count | Koleksi | Count |
|---|---|---|---|
| users | 6 | marketing_live_sessions | 24 |
| rahaza_employees | 40 (25+15 demo) | marketing_creator_sessions | 45 |
| rahaza_work_orders | 25 | dewi_toko_orders | 240 |
| rahaza_bundles | 47 (`current_process_code` **0/47**) | dewi_rnd_samples / _sample_requests | 4 / **0** |
| rahaza_material_stock | 29 (**29/29 `location_id`, 0 `location`**) | rahaza_leave_balances | 25 (**25/25 schema LAMA**) |
| **rahaza_coa_accounts** | **0** ⚠ | **rahaza_posting_profiles** | **0** ⚠ |
| **rahaza_journal_entries / _lines** | **0 / 0** ⚠ | da_kpi_submissions | 50 |
| rahaza_attendance | 1650 | rahaza_attendance_events | **1680** (divergen! lihat K11) |

> ⚠ Tiga sel bertanda = **RC-21** (cascade COA) — tereproduksi **3× fresh deploy berturut-turut**, bukan insiden.

### 0.4 Batas kejujuran metodologi (spt Appendix E Part 2)
1. **Write-flow hanya 2** (B2, domain RnD). POST/PUT/DELETE lain (± 700 op) TIDAK diuji — bug jalur tulis di luar temuan ini masih mungkin ada.
2. **404 = 116 endpoint**: mayoritas graceful not-found (resolver ID lintas koleksi / flow dormant tanpa data). TIDAK ditelusuri 1-per-1 — bila menyentuh modulnya, verifikasi ulang per Golden Rule 1.
3. **NO_ID = 49**: path-param tak dapat diresolusi dari DB (koleksi sumber kosong) — tak teruji.
4. Klasifikasi reader–writer berbasis pola statis `db.<coll>.<op>` — `update_one` terhitung "write" padahal **tanpa insert koleksi selamanya kosong** (kasus nyata: `gl_entries`, lihat RC-26). Anti-false-positive sudah diterapkan manual pada semua RC di dokumen ini.
5. Uji dilakukan sebagai **superadmin** (arahan user: role lain di-skip) — perilaku RBAC role lain di luar cakupan.

---

# BAGIAN 0.5 — KOREKSI & RESOLUSI EMPIRIS ATAS PART 1–3 (K7…K13)

> Melanjutkan penomoran K1–K6 (Part 1 BAGIAN 0.5). WAJIB dibaca sebelum mengeksekusi RC Part 1–3 mana pun.

### K7 — K4/RC-06 scope EXPANSION: linkage user↔karyawan memblok 16 endpoint (bukan hanya payslips/leaves)
STEP D membuktikan **16 endpoint** mengembalikan 409 "Akun belum terhubung ke data karyawan" pada **5 keluarga route**: `portal-saya/*` · `/api/portal/*` · `rahaza/self/*` · `rahaza/leave-balances/my` · `dewi/kpi/my/*`. Fix `[+LINKAGE]` RC-06 (Part 1 K4) otomatis membuka SEMUA-nya — kerjakan SEKALI di linkage, **jangan** per-endpoint. RC-27 di dokumen ini juga double-blocked oleh linkage yang sama.

### K8 — RC-13 nuansa: `services/notification_service.py` = DEAD SERVICE
Grep seluruh backend: **0 importer**. Service ini baca+tulis `dewi_notifications` tapi **tak pernah dipanggil siapa pun**. RC-13 (write-only `dewi_notifications` dari expense/travel) **tetap valid**; tambahan: saat eksekusi RC-13, file service ini kandidat arsip (bukan diperbaiki).

### K9 — RC-12 tambahan & false-positive saga
- `dewi_toko_products` / `dewi_toko_returns` / `dewi_toko_reviews` = **seed-orphan** (ditulis HANYA `dewi_demo_seed`, 0 reader aplikasi).
- `payslips` / `payroll_runs` di `utils/saga.py` = **FALSE-POSITIVE** (hanya docstring contoh; step payroll nyata `rahaza_payroll_runs.py:136-147` sudah pakai koleksi `rahaza_*` benar). Coret dari daftar kecurigaan.

### K10 — RC-08 STOP-VERIFY (Part 2) TERJAWAB
`bank_recon_sessions` / `bank_recon_txns` = **SELF-CONSISTENT** (insert nyata `dewi_bank_reconciliation.py:107`) → **dormant, JANGAN repoint** (jawaban untuk baris ⚠ STOP-VERIFY RC-08 item 108,113). Phantom sesungguhnya di bank recon adalah `gl_entries` → diangkat jadi **RC-26**.

### K11 — 🆕 Divergensi split-brain RC-01 kini TERJADI NYATA (bukan lagi "laten")
Baseline sesi ini: `rahaza_attendance` = **1650** vs `rahaza_attendance_events` = **1680**. Penyebab: `rahaza_hr_seed`/seed-demo menulis 30 absensi **hanya ke `_events`**. Prediksi staleness K1 Part 1 ("besok/nanti akan divergen") **terbukti secara empiris hari ini juga** — memperkuat urgensi RC-01/W-B: reader payroll/dashboard yang masih baca `rahaza_attendance` sudah kehilangan 30 record.

### K12 — Klasifikasi menyeluruh (pengganti "~110 phantom sisanya" di Appendix E Part 2)
Seluruh koleksi-kosong kini terklasifikasi: **47** READ-ONLY-EMPTY (mayoritas sudah tercakup RC Part 1–3; yang BARU diangkat jadi RC-25…28) · **216** SELF-CONSISTENT-EMPTY (dormant — daftar per domain di BAGIAN 3) · **15** WRITE-ONLY (orphan; delta baru vs RC-12 dicatat di BAGIAN 4). Tidak ada lagi "sisa yang belum ditelusuri" dalam kategori read-phantom.

### K13 — 404 (116 endpoint) = keterbatasan metodologi, bukan daftar bug
Mayoritas graceful not-found (ID resolver lintas koleksi / flow dormant). Dicatat jujur; JANGAN dianggap sehat 100% — verifikasi ulang saat menyentuh modul terkait.

---

# BAGIAN 1 — SSOT REGISTRY TAMBAHAN (delta Part 4 — jangan duplikasi tabel Part 1/3)

| Konsep | ✅ SSOT KANONIK (count) | ❌ Yang dipakai kode (salah) | Field kunci / catatan schema NYATA |
|---|---|---|---|
| KPI submissions | `da_kpi_submissions` (50) | `dewi_kpi_submissions` (MISSING) | **DUA varian skor**: seed → `avg_score`+`employee_id`; app-flow (`dewi_kpi_results.py:78-103`) → `section_score`+`evaluatee_id` (TANPA `employee_id`/`avg_score`). TIDAK ADA `final_score`/`grade`/`period_label`. Filter aman = `evaluatee_id`; period = `period_id` ("KPI-2025-Q1"); grade = derive via `_grade()` `dewi_kpi_shared.py:70` |
| Saldo cuti | `rahaza_leave_balances` (25) — **schema BARU** = `leave_type_id`/`allocated`/`used` | (koleksi benar, **schema drift**) | DB saat ini 25/25 **schema LAMA** (`cuti_tahunan_total/used`, `cuti_sakit_*`, TANPA `leave_type_id`) hasil `production_seed_full.py:718`. Schema baru ditulis `rahaza_hr_seed.py:418-422`. `rahaza_leave_types`=5 tersedia. Lihat RC-22 |
| GL untuk bank recon | `rahaza_journal_entries` (+`rahaza_journal_lines`) | `gl_entries` (0 insert di SELURUH kode) | `gl_entries` = phantom baca+tulis (RC-26). Bukti internal: file yang sama sudah benar baca `rahaza_journal_entries` di `:127` |
| Request aksesoris internal | `dewi_accessory_requests` (`request_type='internal_issuance'`) | `acc_internal_requests` (DEPRECATED per TD-009) | Flow kanonik FE menulis ke `dewi_accessory_requests`; `acc_internal_requests` hanya dipakai file deprecated. Lihat RC-25 |
| Lokasi stok material | `rahaza_material_stock`.`location_id` → resolve nama via `wh_positions` (36) | field `location` (0/29 dok) | Keys nyata: `id, location_id, material_id, qty, unit, updated_at`. Lihat RC-19 |
| COA + Posting Profiles (fresh deploy) | `rahaza_coa_accounts` + `rahaza_posting_profiles` — WAJIB terisi via auto-seed startup | import fungsi yang tak ada → keduanya 0 | Lihat RC-21 (kartu paling kritis dokumen ini) |
| Agregat finance utk AI | `rahaza_ar_invoices` (15) · `rahaza_ar_payments` (10) / `rahaza_cash_movements` (32) | `rahaza_invoices`, `rahaza_payments` | `services/ai_aggregates/finance_aggregates.py` — lihat RC-28 |
| GL-mapping counter admin | `employee_expense_gl_mappings` (plural; CRUD self-consistent) | `employee_expense_gl_mapping` (singular) | `rahaza_admin.py:178` — lihat RC-28 |
| Procurement utk workspace-import | `dewi_procurement_requests` (6) | `procurement_requests` | `workspace.py:496` — lihat RC-28 |
| Dispatch CMT (perluasan RC-14) | `wh_cmt_dispatches` (5) | `wms_cmt_dispatches` | `dewi_cmt_lifecycle.py:124,125,214,313` — CMT legacy, lihat RC-28 + BACKLOG-C |

---

# BAGIAN 2 — REPAIR CARDS (RC-19 … RC-29)

Format identik Part 1: `Prioritas | Dampak | File:baris | AKAR | PETA FIELD | LANGKAH | VERIFIKASI | ROLLBACK | RISIKO | DO-NOT`.

---

## 🔴 RC-21 — KRITIS FRESH-DEPLOY: Auto-seed COA & Posting Profiles GAGAL TOTAL → cascade GL lumpuh
> **Kerjakan PERTAMA (Wave J.1).** Memblok RC-05/RC-10 (Part 1–2) dan SEMUA laporan GL pada deploy baru.
- **Prioritas:** P0. **Dampak:** `rahaza_coa_accounts=0` **DAN** `rahaza_posting_profiles=0` pada SETIAP fresh deploy → seed JE dilewati → `rahaza_journal_entries=0`, `rahaza_journal_lines=0` → Buku Besar, Laba Rugi, Neraca, semua laporan GL **kosong total**; posting engine (`rahaza_posting.py`) tak bisa memvalidasi akun.
- **Bukti (D1/D2, tereproduksi 3× fresh deploy):**
  - Log startup: `Phase 7D auto-seed: cannot import name 'seed_coa_accounts' from 'routes.rahaza_coa'`.
  - `server.py:194-196` → `from routes.rahaza_coa import seed_coa_accounts` — **fungsi itu TIDAK ADA**. Yang ada di `rahaza_coa.py`: handler route `seed_template` (`:300` = `POST /api/rahaza/coa/seed`) dan `seed_da_coa` (`:545` = `POST /api/rahaza/coa/seed-da`) — keduanya butuh `request: Request`, bukan callable `(db)`.
  - ImportError → **seluruh blok try startup gugur** → auto-seed **posting profiles ikut dilewati** (kode di bawahnya dalam blok yang sama).
  - **CASCADE:** `production_seed_full.py:1267` membangun `coa_map` dari COA kosong → blok seed JE di-skip → GL kosong.
  - Terkait: `scripts/seed_expense_categories.py:120` menulis kategori/akun 6-3xxx ke **phantom `rahaza_coa`** (kanonik = `rahaza_coa_accounts`) — script seed pendukung pun salah koleksi.
- **AKAR MASALAH:** refactor sebelumnya mengubah/menghapus fungsi `seed_coa_accounts` tanpa memperbarui pemanggil startup; tak ada test fresh-deploy yang menangkapnya (DB dev lama selalu sudah berisi COA).
- **LANGKAH:**
  1. Di `rahaza_coa.py`: **ekstrak** isi logic seed dari handler `seed_da_coa` menjadi fungsi murni `async def seed_coa_accounts(db) -> int` (tanpa `Request`); handler existing memanggil fungsi ini (hindari duplikasi kode).
  2. Pastikan auto-seed **posting profiles** juga callable `(db)` dan dipanggil SETELAH COA sukses (cek kode Phase 7D `server.py` sekitar `:194-210`).
  3. `server.py`: import fungsi baru; restart backend → log harus tampil "COA auto-seeded ... accounts" TANPA warning.
  4. Perbaiki `scripts/seed_expense_categories.py:120` → tulis ke `rahaza_coa_accounts`.
  5. **Re-run** `POST /api/seed/production-full` agar `coa_map` terisi → JE/lines terbentuk.
- **VERIFIKASI:** `rahaza_coa_accounts` ≥ 97 · `rahaza_posting_profiles` = 33 · `rahaza_journal_entries` > 0 · `rahaza_journal_lines` > 0 · `GET /api/rahaza/reports/*` (Buku Besar/LR) berisi angka · log startup bersih.
- **ROLLBACK:** revert `server.py` + `rahaza_coa.py` (fungsi baru additive, aman).
- **RISIKO:** Sedang — re-seed production-full menghapus+menulis ulang banyak koleksi (by design seed); jalankan saat tidak ada pekerjaan lain.
- **DO-NOT:** JANGAN panggil handler route dengan `Request` palsu · JANGAN `insert_one` JE manual (Golden Rule 4 Part 1) · JANGAN seed COA via mongosh langsung (lewat fungsi agar konsisten dgn template).

---

## 🔴 RC-22 — `GET /api/rahaza/leave-balances` 500 (dua seeder, dua schema) + FE empty-state MENYESATKAN
- **Prioritas:** P0 (crash + risiko korupsi data campuran). **Dampak:** modul `hr-leave-balances` tak bisa menampilkan saldo cuti; UI menyesatkan user untuk menimpa data.
- **Bukti (D1/D2/D3, render terverifikasi screenshot):**
  - Backend 500: KeyError `'leave_type_id'` di `rahaza_leave_balances.py:119` (`lt_ids = list({d["leave_type_id"] ...})`).
  - **DUA seeder → SATU koleksi, schema BEDA:** `production_seed_full.py:718` schema LAMA (`cuti_tahunan_total/used`, `cuti_sakit_*`, TANPA `leave_type_id`; 25/25 dok di DB) vs `rahaza_hr_seed.py:418-422` schema BARU (`leave_type_id`/`allocated`/`used`). `rahaza_leave_types`=5 tersedia.
  - **FE menelan 500** → tampil empty-state: *"Belum ada saldo cuti untuk tahun 2026 · 0 karyawan · Klik Alokasi Tahunan"*. **BAHAYA:** klik "Alokasi Tahunan" akan menulis dok schema-baru → koleksi berisi **campuran 2 schema**.
- **AKAR:** seed produksi tidak pernah diselaraskan saat modul leave-balances direfactor ke schema `leave_type_id`.
- **PETA FIELD (migrasi schema lama→baru):** `cuti_tahunan_total→allocated` + `leave_type_id=<id "Cuti Tahunan">` · `cuti_tahunan_used→used` · `cuti_sakit_*` → dok terpisah dgn `leave_type_id=<id "Cuti Sakit">` (1 dok lama = 2 dok baru).
- **LANGKAH:** (1) ⚠ **STOP-VERIFY**: cek `rahaza_leave_types` `distinct('name','id')` untuk mapping ID; cek apakah `rahaza_hr_seed` dipanggil di dalam production-full atau endpoint terpisah. (2) Selaraskan `production_seed_full.py:718` ke schema baru (atau hapus blok itu dan andalkan `rahaza_hr_seed`/alokasi UI — pilih SATU sumber). (3) Guard reader: `d.get("leave_type_id")` + skip/log dok non-conform (jangan 500 karena data lama). (4) FE: tampilkan error nyata saat non-200 (bukan empty-state). (5) Re-seed → verifikasi.
- **VERIFIKASI:** `GET /api/rahaza/leave-balances` → 200 + 25 karyawan × tipe cuti dgn join nama leave type; FE menampilkan tabel saldo; klik "Alokasi Tahunan" pada data bersih tidak menduplikasi.
- **ROLLBACK:** revert seed + reader; data campuran (bila terlanjur) bersihkan by `year`+`$exists leave_type_id`.
- **RISIKO:** Sedang (menyentuh seed + kemungkinan data existing). **DO-NOT:** JANGAN biarkan 2 schema koeksis · JANGAN migrasi dok lama tanpa mapping leave_type eksplisit · JANGAN perbaiki hanya FE (backend tetap 500).

---

## 🟠 RC-23 — `GET /api/hr/expenses/outstanding-advances/export` 500 (naive vs aware datetime) + toast sukses PALSU
- **Prioritas:** P1. **Dampak:** Export CSV outstanding advances selalu gagal; user TIDAK TAHU karena FE menampilkan toast sukses (kegagalan senyap — terverifikasi screenshot).
- **Bukti (D1/D2/D3):** handler export `employee_travel_settlements.py:368`; `:379` sort by `advance_paid_at`; `:391-396` `advance_paid_at` di DB = **string date-only** `"2026-05-06"` → `fromisoformat` → datetime **NAIVE** → `datetime.now(timezone.utc) - naive` → `TypeError` (±`:395-401`). Sibling `GET /outstanding-advances` (`:723`) TIDAK crash (tak menghitung selisih hari). FE `hr-travel-settlement`: klik "Export CSV" → toast *"Export dimulai. File akan terdownload."* padahal backend 500.
- **LANGKAH:** (1) normalisasi tz setelah parse: `if dt.tzinfo is None: dt = dt.replace(tzinfo=timezone.utc)` (juga tangani date-only tanpa jam). (2) FE: cek `response.ok` SEBELUM toast sukses; tampilkan toast error bila gagal (pola download-blob).
- **VERIFIKASI:** endpoint → 200 + CSV berisi baris advance; FE toast sukses hanya saat 200, toast error saat 500 (uji dgn mematikan sementara — opsional).
- **ROLLBACK:** revert 1 blok parse + 1 handler FE. **RISIKO:** Rendah.
- **DO-NOT:** JANGAN mengubah format data `advance_paid_at` di DB (writer lain memakai string date) — fix di reader.

---

## 🔴 RC-20 — FE CRASH modul `marketing-live-analytics` (ErrorBoundary "Portal Error")
- **Prioritas:** P1 (modul mati total bagi user; render terverifikasi screenshot). **Dampak:** `LiveSessionAnalyticsDashboard.jsx` crash saat mount.
- **AKAR (D2/D3):** `LiveSessionAnalyticsDashboard.jsx:142` `<SelectItem value="">Semua Platform</SelectItem>` — Radix UI Select **melempar error** untuk `value=""` → ErrorBoundary menampilkan "Portal Error" + pesan Select.Item persis.
- **LANGKAH:** (1) ganti `value="all"`; (2) sesuaikan logic filter platform: `platform === 'all' → tanpa filter`; (3) sweep file yang sama utk `SelectItem value=""` lain.
- **VERIFIKASI:** deep-link `#marketing-live-analytics` → dashboard render tanpa ErrorBoundary; filter "Semua Platform" bekerja.
- **ROLLBACK:** revert 1 file. **RISIKO:** Rendah.
- **DO-NOT:** JANGAN membungkus dgn try/catch untuk menyembunyikan (fix akarnya) · perhatikan endpoint summary yang dipanggil modul ini mungkin masih RC-15 (Part 3) — dua bug independen, dua fix.

---

## 🔴 RC-19 — WMS Material Label PDF crash 500 (`s['location']` KeyError)
- **Prioritas:** P1. **Dampak:** `GET /api/wms/materials/{id}/label-pdf` → 500; cetak label material gagal total.
- **AKAR (D1/D2):** `routes/wms_material_labels.py:187` dan `:268` → `next((s['location'] for s in ...))` — SSOT `rahaza_material_stock` **tidak punya** field `location` (29/29 dok: `id, location_id, material_id, qty, unit, updated_at`).
- **PETA FIELD:** `location` → `location_id` → resolve nama posisi via `wh_positions` (36 dok) by `location_id`, fallback `'-'`.
- **LANGKAH:** (1) `s.get('location_id')` di kedua baris; (2) lookup batch `wh_positions` → tampilkan `code`/`name` posisi di label; (3) fallback `'-'` bila tak ada stok/posisi.
- **VERIFIKASI:** endpoint → 200 (bytes PDF) untuk material ber-stok DAN tanpa-stok; label menampilkan nama lokasi nyata.
- **ROLLBACK:** revert file tunggal. **RISIKO:** Rendah.
- **DO-NOT:** JANGAN menambah field `location` (denormalisasi) ke `rahaza_material_stock` · JANGAN ubah writer stok.

---

## 🟠 RC-25 — Accessories Dashboard misroute laten (`acc_internal_requests` deprecated)
- **Prioritas:** P2 (laten — dashboard render normal, KPI pending=0 selamanya utk flow kanonik; render terverifikasi testing agent iteration_30).
- **AKAR (D2):** `dewi_accessories_dashboard.py:120,:180` baca `acc_internal_requests` (DEPRECATED per TD-009) — flow kanonik (FE aktif) menulis **`dewi_accessory_requests`** dgn `request_type='internal_issuance'`. Laten: user buat request via flow kanonik → "Request Pending" tetap 0.
- **⚠ ANTI-FALSE-POSITIVE (2 lapis):**
  1. Classifier menandai `acc_internal_requests` "self-consistent" karena file deprecated `dewi_accessories_requests.py` masih baca+tulis — tapi flow AKTIF tidak lewat sana → bagi dashboard tetap misroute.
  2. `acc_loans` & `acc_purchase_requests` di dashboard **KONSISTEN** dgn modul loans/purchase yang self-consistent (insert nyata `dewi_accessories_loans.py:206`, `dewi_accessories_purchase.py:208`) → **JANGAN repoint dua itu** — hanya internal-requests yang misroute.
- **LANGKAH:** (1) ⚠ **STOP-VERIFY**: `distinct('status')` & `distinct('request_type')` di `dewi_accessory_requests` (peta nilai status `'Pending'` vs kanonik). (2) Repoint `:120`/`:180` → `dewi_accessory_requests` + filter `request_type='internal_issuance'` + status map. (3) Housekeeping opsional TERPISAH: arsipkan `dewi_accessories_requests.py` (deprecated).
- **VERIFIKASI:** buat 1 internal request via UI kanonik → KPI "Request Pending" naik 0→1.
- **ROLLBACK:** revert 2 baris. **RISIKO:** Rendah-sedang (peta status).
- **DO-NOT:** JANGAN sentuh `acc_loans`/`acc_purchase_requests` · JANGAN repoint modul deprecated itu sendiri.

---

## 🔴 RC-26 — Bank Recon auto-match baca+TULIS phantom `gl_entries` (resolusi STOP-VERIFY RC-08)
- **Prioritas:** P1. **Dampak:** fitur auto-match rekonsiliasi bank **tak pernah berjalan** — selalu early-return "Tidak ada data untuk dicocokkan".
- **AKAR (D2):** `dewi_bank_reconciliation.py:604` `db.gl_entries.find(...)` dan `:670` `db.gl_entries.update_one(...)` — **TIDAK ADA insert ke `gl_entries` di seluruh kode** → koleksi selamanya kosong → `:606` early-return. Ironi: file yang sama **sudah benar** baca `rahaza_journal_entries` di `:127`.
- **⚠ ANTI-FALSE-POSITIVE:** classifier menandai `gl_entries` "self-consistent" karena `update_one` terhitung write — **update tanpa insert = koleksi tak akan pernah terisi** → tetap phantom (lihat §0.4 poin 4).
- **Resolusi RC-08 Part 2 (K10):** `bank_recon_sessions`/`bank_recon_txns` = SELF-CONSISTENT (insert `:107`) → dormant, JANGAN repoint.
- **LANGKAH:** (1) ⚠ **STOP-VERIFY**: baca struktur `gl_q` (`:600-604`) — field apa yang di-query (date/amount/description?) lalu petakan ke schema `rahaza_journal_entries` (`je_number,date,status,lines[]`) / `rahaza_journal_lines` (per-baris amount). (2) Repoint `:604` ke SSOT + peta field. (3) `:670` MENULIS status match ke sisi GL — **rekomendasi: simpan hasil match di `bank_recon_txns` sendiri** (field `matched_je_id`), JANGAN mutasi dokumen JE (hindari field liar di SSOT GL); bila product butuh flag di JE, tambah `is_matched` via keputusan eksplisit.
- **VERIFIKASI:** setelah RC-21 (JE terisi) → buat sesi recon + upload txns → auto-match mengembalikan kandidat (bukan early-return).
- **ROLLBACK:** revert file tunggal. **RISIKO:** Sedang (menyentuh alur tulis status match).
- **DO-NOT:** JANGAN repoint `bank_recon_sessions`/`txns` · JANGAN tulis field liar ke `rahaza_journal_entries` tanpa keputusan · **dependensi: kerjakan SETELAH RC-21** (tanpa JE, match tetap kosong).

---

## 🟠 RC-27 — Portal Saya HR: KPI baca phantom `dewi_kpi_submissions` → SSOT `da_kpi_submissions` ✅ STOP-VERIFY RESOLVED
- **Prioritas:** P2 (double-blocked K4/K7 linkage). **Dampak:** kartu KPI di `GET /api/portal/dashboard` selalu null.
- **AKAR (D2):** `dewi_portal_saya_hr.py:167` (handler `GET /dashboard` mulai `:93`) baca `dewi_kpi_submissions` (MISSING; twin: `da_kpi_submissions`=50) dgn proyeksi `final_score,grade,period_label` — TIGA-TIGANYA tak ada di SSOT.
- **✅ STOP-VERIFY RESOLVED (sesi ini):**
  - Schema SSOT `da_kpi_submissions`: `answers, avg_score, created_at, employee_code, employee_id, employee_name, eval_type, evaluatee_id, evaluator_id, id, period_id, status, submission_id, submission_type, submitted_at, submitted_by, submitted_by_name`.
  - **DUA varian skor**: dok seed → `avg_score` + `employee_id`; dok app-flow (`dewi_kpi_results.py:78-103`) → `section_score` + `evaluatee_id` **tanpa** `employee_id`/`avg_score`.
  - `dewi_portal_saya_backup.py:194` (pembaca phantom yang sama) → **TIDAK di-mount** (0 referensi; `dewi_portal_saya.py:13` hanya mount `_hr` & `_workspace`) → dead file, **JANGAN edit**, kandidat arsip.
- **PETA FIELD:** koleksi → `da_kpi_submissions` · filter `{"employee_id": emp_id}` → `{"evaluatee_id": emp_id}` (ada di KEDUA varian) · `final_score` → `doc.get("avg_score") or doc.get("section_score") or 0` · `grade` → derive via `_grade(score)` (`dewi_kpi_shared.py:70`) · `period_label` → `period_id` · sort `created_at` tetap (ada di kedua varian) · tambah filter `status='submitted'` (hindari draft).
- **VERIFIKASI:** setelah K4 linkage tersedia → `GET /api/portal/dashboard` → `kpi_score={score>0, grade∈A..E, period="KPI-..."}`. Sebelum linkage: uji unit dgn emp_id nyata dari `da_kpi_submissions`.
- **ROLLBACK:** revert blok `:165-176`. **RISIKO:** Rendah.
- **DO-NOT:** JANGAN edit `dewi_portal_saya_backup.py` · JANGAN pakai `employee_id` sbg filter (app-flow tak menulisnya) · ingat hasil tetap null sampai K4 linkage selesai — jangan klaim beres dari 200 saja.

---

## 🟡 RC-28 — Cluster misc phantom BARU (pola RC-14 Part 2)
- **Prioritas:** P2. Satu kartu, 5 item independen (masing-masing 1-baris fix + verifikasi count):

| File:baris | ❌ Baca | ✅ SSOT (count) | Dampak & catatan |
|---|---|---|---|
| `services/ai_aggregates/finance_aggregates.py:28,82,154,164` | `rahaza_invoices` | `rahaza_ar_invoices` (15) | agregat finance utk fitur AI selalu 0. Peta field cek `total/balance/status` |
| `services/ai_aggregates/finance_aggregates.py:182` | `rahaza_payments` | ⚠ STOP-VERIFY: `rahaza_ar_payments` (10) ATAU `rahaza_cash_movements` (32, `direction:'in'`) — pilih sesuai definisi "payment count" yang dimaksud agregat | idem |
| `rahaza_admin.py:178` | `employee_expense_gl_mapping` (singular) | `employee_expense_gl_mappings` (plural; CRUD self-consistent di `employee_expense_gl_mapping.py`) | counter admin salah; perluasan RC-10 |
| `workspace.py:496` (dalam `POST /api/workspace/documents/import-from-module` `:426`) | `procurement_requests` | `dewi_procurement_requests` (6) | import PR ke workspace selalu kosong; cek peta field `title/status/created_at` |
| `dewi_cmt_lifecycle.py:124,125,214,313` | `wms_cmt_dispatches` | `wh_cmt_dispatches` (5) | perluasan RC-14. CMT legacy — **pertimbangkan BACKLOG-C (arsip) SEBELUM repoint**; jika modul akan diarsip, repoint = kerja sia-sia |
- **VERIFIKASI per item:** endpoint pemakai mengembalikan count = count DB SSOT. **RISIKO:** Rendah. **DO-NOT:** untuk `finance_aggregates:182` JANGAN pilih koleksi tanpa STOP-VERIFY definisi.

---

## 🟡 RC-24 — `GET /api/rahaza/work-orders/{id}/bundles-summary` 500 (tanpa consumer FE)
- **Prioritas:** P2 (LOW — 0 consumer FE, tapi crash nyata di API publik).
- **AKAR (D1/D2):** `rahaza_bundles_mgmt.py:352` `r["_id"]["pcode"]` KeyError — Mongo `$group` **menghilangkan key yang missing** dari `_id`; `current_process_code` ada di **0/47** bundle (seed tak mengisi). Mount: via orchestrator `routes/rahaza_bundles.py` → yang live = `_mgmt.py`. `rahaza_bundles_backup.py:337` duplikat kode sama tapi **TIDAK di-mount** (jangan edit).
- **LANGKAH:** `r["_id"].get("pcode")`/`.get("pid")` + fallback `'-'` ATAU `$ifNull` di pipeline group. Opsional [+SEED]: isi `current_process_code` di seed bundle.
- **VERIFIKASI:** endpoint → 200 dgn grouping "-" untuk bundle tanpa proses. **ROLLBACK:** revert 1 baris. **RISIKO:** Rendah. **DO-NOT:** jangan edit file `_backup`.

---

## 🟡 RC-29 — Router Portal-Saya-HR di-mount DUA KALI (12 endpoint bare tanpa `/api`)
- **Prioritas:** P2 (housekeeping). **Dampak:** 12 path bare (`/dashboard`, `/leave`, `/leave-types`, `/leave/{id}`, `/notifications`, `/notifications/{id}/read`, `/overtime`, `/payslips`, `/profile`, `/profile/photo`, `/training`, `/training/{id}/certificate`) muncul di openapi; tak terjangkau ingress (hanya `/api/*` ke backend) → noise + risiko akses lokal tanpa prefix.
- **AKAR (D2):** `server.py:1676` `app.include_router(dewi_portal_saya_hr_router)` **tanpa prefix**; mount BENAR sudah ada via `dewi_portal_saya.py:13` (nested `/api/portal/*`).
- **LANGKAH:** hapus mount `server.py:1676` + import `:1673` bila tak dipakai lagi; restart; cek openapi path berkurang 12 dan `/api/portal/dashboard` tetap 200.
- **VERIFIKASI:** `curl localhost:8001/dashboard` → 404 · `/api/portal/dashboard` → 200/409 (sesuai linkage). **ROLLBACK:** kembalikan 2 baris. **RISIKO:** Rendah. **DO-NOT:** JANGAN hapus mount yang di `dewi_portal_saya.py`.

---

# BAGIAN 3 — DORMANT REGISTRY TAMBAHAN (dari 216 SELF-CONSISTENT-EMPTY — JANGAN repoint)

> Aturan tetap (Part 3 BAGIAN 0.4): self-consistent + kosong = **jujur-kosong**. Repoint = MERUSAK siklus CRUD. Daftar lengkap 216 regenerate via `d2_phantom_classifier.py`; di bawah = kluster per domain **yang BELUM tercatat di Part 2 (RC-12/BACKLOG) & Part 3 (BAGIAN 3)**:

| Domain / kluster | Koleksi (contoh) | File self-consistent | Catatan |
|---|---|---|---|
| **Assets (DA & Dewi)** | `da_assets`, `da_asset_assignments`, `dewi_assets`, `dewi_asset_*` (8 koleksi: depreciation/disposal/maintenance/scans/transfers/pm_ack) | `assets_core`, `assignments`, `depreciation_batch/per`, `disposal`, `transfer`, `scan_label` | **BEDA fitur** dari `rahaza_fixed_assets` (15, berisi). Dua subsistem asset dorman + 1 aktif — kandidat keputusan produk konsolidasi, BUKAN misroute |
| **Communication** | `comm_channels`, `comm_conversations`, `comm_messages`, `comm_read_receipts` | `channels`, `conversations`, `messages_actions`, `unread_search` | runtime/event-driven; kosong = belum ada percakapan |
| **CMT legacy penuh** | `dewi_cmt_jobs/partners/deliveries/payments/delivery_orders/progress_reports/component_requests`, `cmt_receipts`, `cmt_receipt_lines` | `dewi_cmt*`, `dewi_cmt_packing` | selaras BACKLOG-C (arsip bertahap) — JANGAN repoint, putuskan arsip |
| **HRIS Performance (paralel baru)** | `dewi_perf_cycles/kpis/assignments/reviews` | `dewi_hris_performance` | subsistem performance TERPISAH dari `da_kpi_*` (50 dok, aktif) dan `hris_*` (dead-read Part 1). 3 generasi KPI: 1 aktif, 2 dorman — kandidat konsolidasi produk |
| **Recruitment / Job board** | `dewi_recruitment_jobs/candidates`, `rahaza_job_postings`, `rahaza_job_applications` | `dewi_recruitment`, `dewi_job_board` | belum dipakai |
| **LMS lanjutan** | `dewi_lms_materials/progress/quizzes/submissions` | `dewi_lms`, `lms_student`, `dewi_lms_quiz` | dorman (attempts = write-only, sudah RC-12) |
| **Approval chains** | `approval_chains`, `approval_requests` | `approval_multilevel.py:136` (CRUD) | **[+SEED] gap**: fresh deploy = 0 chains padahal PRD klaim 11 → butuh seed config, BUKAN misroute |
| **Portal workspace** | `portal_todos/notes/reminders/quick_links/calendar_events` | `dewi_portal_saya_workspace` | terisi saat user memakai portal |
| **Bank recon sesi** | `bank_recon_sessions`, `bank_recon_txns` | `dewi_bank_reconciliation:107` | resolusi K10 — dorman menunggu upload; phantom-nya `gl_entries` (RC-26) |
| **Petty cash / fixed assets sub** | `rahaza_petty_cash_funds/txns`, `rahaza_depr_schedules` | `rahaza_petty_cash`, `rahaza_fixed_assets` | menunggu transaksi |
| **Maklon sub** | `dewi_maklon_material_issues`, `dewi_maklon_material_receive`, `dewi_maklon_bom*` | `dewi_maklon.py:613` dkk | insert nyata ada — dorman (konfirmasi §4.5 handoff sesi lalu) |
| **Legacy production family** | `production_jobs/job_items/pos/progress/returns/variances`, `work_orders`, `vendor_shipments/jobs/partners`, `qc_inspections`, `garments`, `products`, `buyers` | `production_*`, `vendor_portal`, `qc`, `master_data` | subsistem produksi LAMA (pra-rahaza). Self-consistent tapi tak di-nav utama — kandidat BACKLOG arsip besar; beberapa readers-nya sudah tercatat RC-04/RC-14 |
| **Auto-attendance infra** | `rahaza_webauthn_*`, `rahaza_zkteco_devices`, `rahaza_office_locations` | `rahaza_auto_attendance_*` | terisi saat device/enrol nyata |
| **Marketing advanced-AI** | `marketing_ab_experiments`, `marketing_churn_scores`, `marketing_dynamic_pricing_*` | `marketing_advanced_ai_routes` | dorman menunggu pemakaian fitur AI |

---

# BAGIAN 4 — FALSE-POSITIVE REGISTRY TAMBAHAN (JANGAN sentuh)

| Item | Kategori | Alasan (bukti) |
|---|---|---|
| `vendor-portal/*` & `cmt/vendor/*` → 403 (7 endpoint) | Auth-scoped | Butuh JWT role **vendor**; superadmin ditolak by design |
| `GET /api/push/vapid-public-key` → 503 | Config-missing jujur | VAPID key tidak dikonfigurasi; error eksplisit, bukan bug kode |
| `GET /api/notifications/stream` → TIMEOUT | By design | SSE stream memang tidak pernah "selesai" |
| `GET /api/finance/ai-cashflow` → 502 **TRANSIEN** | Budget LLM sesaat | "Budget has been exceeded" (Emergent LLM key); retry → 200 + analisis nyata. Rekomendasi opsional: retry/backoff + graceful degrade, BUKAN bug SSOT |
| `payslips`/`payroll_runs` writer `utils/saga.py` | Docstring | K9 — hanya contoh di docstring, bukan kode |
| `invoice_adjustments`, `payments`, `invoices`, `buyer_shipments`, `vendor_material_inspections` (writer/rw `cascade_delete`) | Artefak helper | `cascade_delete.py` = helper hapus-berantai legacy; "write" = delete ops. Bukan alur data |
| `marketing_kol_campaigns` | Sudah tercatat | Appendix A Part 2 (dibungkus try/except, hasil dibuang) |
| `dewi_scheduler_runs`, `login_attempts`, `attachments`, `client_login_attempts` | Runtime-empty normal | Sudah tercatat Appendix A Part 2 — dikonfirmasi ulang STEP D |
| Modul Assets kosong ≠ bug `rahaza_fixed_assets` | Fitur beda | `rahaza_fixed_assets` (15) aktif; `da_assets`/`dewi_assets` dorman (BAGIAN 3) |
| 116 endpoint 404 | Metodologi | K13 — graceful not-found; bukan daftar bug |
| Console `ws://localhost:443/ws` error di FE dev | Artefak env | WebSocket WDS dev-server; abaikan |

---

# BAGIAN 5 — ROADMAP **WAVE J** (integrasi dgn Wave A–H Part 2 & Wave I Part 3)

| Gel | Isi | Prio | Risiko | Prasyarat / dependency | Uji kunci |
|---|---|---|---|---|---|
| **J.1** | **RC-21** cascade COA + posting profiles + re-seed JE | P0 | Sedang | — (KERJAKAN PERTAMA; **prasyarat RC-05/RC-10 Part 1–2, RC-26, dan semua laporan GL**) | COA≥97, PP=33, JE>0, log startup bersih, LR/Buku Besar berisi |
| **J.2** | **RC-22** leave-balances (seed+reader+FE) + **RC-23** export tz + FE toast | P0/P1 | Sedang | STOP-VERIFY mapping leave_types | 2 endpoint 200 + FE jujur (tabel saldo; toast error saat gagal) |
| **J.3** | **RC-20** SelectItem FE + **RC-19** label PDF | P1 | Rendah | — | render `#marketing-live-analytics` tanpa ErrorBoundary; label-pdf 200 |
| **J.4** | **RC-26** bank recon (setelah J.1) + **RC-25** accessories + **RC-27** KPI portal + **RC-28** (5 item) | P1/P2 | Sedang | J.1 (RC-26) · K4 linkage utk hasil nyata RC-27 · STOP-VERIFY per kartu | angka = count DB; auto-match jalan; KPI pending naik |
| **J.5** | **RC-24** bundles-summary + **RC-29** double-mount (housekeeping) | P2 | Rendah | — | endpoint 200; openapi -12 path |

**Dependency lintas-Part (penting):**
- **J.1 memblok**: RC-05/RC-10 (W-C Part 2 — GL engine butuh COA), RC-02 expense-agg (W-D), RC-26 (J.4). → Jika Wave C Part 2 belum dieksekusi, **jalankan J.1 SEBELUM W-C**.
- **RC-27 & 16 endpoint 409 (K7)**: hasil nyata menunggu RC-06 `[+LINKAGE]` (W-A Part 2). Repoint boleh duluan, klaim beres TIDAK.
- **RC-28 item CMT** (`dewi_cmt_lifecycle`): keputusan BACKLOG-C (arsip) dulu — jangan repoint modul yang akan diarsip.
- Wave J **independen** dari Wave I (Part 3) kecuali catatan RC-20 (modul yang sama tersentuh RC-15 di backend — koordinasikan bila dikerjakan bersamaan).

**Definition of Done:** identik BAGIAN 6 Part 2 (endpoint 200 + angka = count DB + render UI + `testing_agent` hijau + CHANGELOG). Tambahan khusus Part 4: untuk RC-21 **WAJIB uji fresh-deploy** (drop DB → restart → seed → verifikasi log auto-seed) karena bug ini hanya muncul pada deploy baru; untuk kartu ber-STOP-VERIFY, jalankan verifikasi dulu dan tempel hasilnya di CHANGELOG.

---

# APPENDIX F — BUKTI EMPIRIS PART 4 (baseline "BEFORE", 2026-07-02)

### F.1 — 5 crash 500 (reproduksi)
| Endpoint | Root cause | RC |
|---|---|---|
| `GET /api/marketing/live/summary` | field mismatch + `round(None)` | RC-15 (Part 3 — belum difix) |
| `GET /api/rahaza/leave-balances` | KeyError `leave_type_id` (2 schema) | RC-22 |
| `GET /api/hr/expenses/outstanding-advances/export` | naive vs aware datetime | RC-23 |
| `GET /api/rahaza/work-orders/{id}/bundles-summary` | `$group` menghilangkan key missing | RC-24 |
| `GET /api/wms/materials/{id}/label-pdf` | KeyError `location` | RC-19 |

### F.2 — Status verifikasi render (STEP C, deep-link `#<module-id>`)
| Modul (id) | Status render | Bukti |
|---|---|---|
| `accessories-dashboard` | ✅ render, KPI nol, tanpa crash (laten RC-25) | testing agent iteration_30 |
| `hr-leave-balances` | ⚠️ **empty-state MENYESATKAN** (500 ditelan) | screenshot |
| `hr-travel-settlement` | ⚠️ Export CSV → **toast sukses palsu**, backend 500 | screenshot |
| `fin-bank-recon` | ✅ graceful empty (dorman; auto-match tetap mati — RC-26) | screenshot |
| `marketing-live-analytics` | ❌ **ErrorBoundary "Portal Error"** (RC-20) | screenshot |
| `marketing-live` | ⚠️ KPI semua 0 (summary 500 ditelan) TAPI tabel sesi tampil | screenshot |
| `prod-capacity-planning` | ⚠️ WO Aktif 0, utilisasi 0% (RC-17 Part 3) | screenshot |
| `rnd-samples` | ⚠️ "Belum ada sample request" (RC-18 Part 3) | screenshot |
| `marketing-kol` | ✅ **SEHAT + DATA NYATA** — 5 creator, revenue Rp 23,5–38,6 jt/creator (endpoint `marketing_kol_ops.py` yang benar) | screenshot sesi ini |
| `marketing-kol-leaderboard` | ⚠️ **graceful-empty MENYESATKAN** — semua KPI 0 + CTA "Input data sesi live di modul Live Session" padahal `marketing_creator_sessions`=45 (konfirmasi render RC-16 Part 3) | screenshot sesi ini |

> Catatan navigasi testing: navigasi by label teks gagal 9/10; **metode terbukti = login → `window.location.hash='<module-id>'` → reload**.

### F.3 — Angka global STEP D per domain (954 GET, 47 dtk)
`accessories 18 · approval 13 · assets 27 · communication 25 · core_p1p2 209 · finance_ext 84 · hr_talent 110 · maklon_cmt 84 · marketing_p3 124 · procurement 43 · production_ext 95 · rnd_p3 31 · toko 4 · wms_p3 86 · other 1` — 500 tersebar: finance_ext=1 (RC-23) · hr_talent=1 (RC-22) · marketing_p3=1 (RC-15) · production_ext=1 (RC-24) · wms_p3=1 (RC-19).

---

# APPENDIX G — PERINTAH VERIFIKASI (read-only, regenerate kapan saja)

```bash
# 0) health + token (rate-limit login 10/60 dtk!)
curl -s http://localhost:8001/api/health
curl -s -X POST http://localhost:8001/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@garment.com","password":"Admin@123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])" > /tmp/admin_token.txt

# 1) regenerate seluruh bukti STEP D (±47 dtk) + klasifikasi 47/216/15
curl -s http://localhost:8001/api/openapi.json -o /tmp/openapi.json     # 1663 path (BUKAN /openapi.json)
cd /app/backend && python3 migrations/d_full_scope_forensics.py | tail -40
python3 migrations/d2_phantom_classifier.py | head -60                  # full: tanpa head

# 2) reproduksi 5 crash 500 (F.1) — pakai TOKEN
T=$(cat /tmp/admin_token.txt)
curl -s -o /dev/null -w "%{http_code} " -H "Authorization: Bearer $T" http://localhost:8001/api/rahaza/leave-balances
curl -s -o /dev/null -w "%{http_code} " -H "Authorization: Bearer $T" http://localhost:8001/api/hr/expenses/outstanding-advances/export
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $T" http://localhost:8001/api/marketing/live/summary
# label-pdf & bundles-summary butuh {id}: ambil dari db.rahaza_materials / db.rahaza_work_orders

# 3) bukti cascade RC-21 (fresh deploy)
grep -i "seed_coa_accounts\|Phase 7D" /var/log/supervisor/backend.err.log | tail -3
python3 - <<'PY'
from dotenv import load_dotenv; load_dotenv('/app/backend/.env')
import os; from pymongo import MongoClient
db=MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
for c in ['rahaza_coa_accounts','rahaza_posting_profiles','rahaza_journal_entries','rahaza_journal_lines',
          'rahaza_leave_balances','da_kpi_submissions','rahaza_material_stock','gl_entries']:
    print(c, db[c].count_documents({}))
print('leave_balances schema-baru:', db.rahaza_leave_balances.count_documents({'leave_type_id':{'$exists':True}}))
print('divergensi K11:', db.rahaza_attendance.count_documents({}), 'vs', db.rahaza_attendance_events.count_documents({}))
PY

# 4) render check (metode deep-link): login UI → window.location.hash='marketing-live-analytics' → reload
```

---

### RINGKASAN EKSEKUTIF PART 4
- **11 Repair Card baru (RC-19…29)**: 1 kritis fresh-deploy (**RC-21** — cascade COA melumpuhkan seluruh GL & memblok RC-05/RC-10), 4 crash 500 backend, 1 crash render FE, 2 kegagalan senyap UX (toast palsu, empty-state menyesatkan), 3 kluster misroute, 1 housekeeping mount ganda.
- **7 koreksi (K7–K13)** atas Part 1–3, termasuk: linkage memblok **16 endpoint** (bukan 2), divergensi split-brain absensi **sudah terjadi nyata** (1650 vs 1680), STOP-VERIFY RC-08 terjawab.
- **Cakupan tuntas**: 954/958 GET (99.6%) + klasifikasi SEMUA koleksi kosong (47 dead-read / 216 dormant / 15 orphan) — tidak ada lagi "sisa belum ditelusuri" di kategori read-phantom. Batas jujur: write-flow hanya 2, 404×116 tak ditelusuri per-item.
- **Urutan eksekusi: J.1 (RC-21) PERTAMA** — dampak terbesar, membuka blokade GL lintas-Part.

> *Dokumen ini adalah RENCANA + BUKTI. BELUM ada perubahan kode runtime. Eksekusi menunggu persetujuan user (konvensi Part 1–3). Semua klaim reprodusibel via Appendix G — zero assumption.*
