# BUG_REGISTRY.md — Registri Bug (metodologi forensik Rahaza-Travel)

> Setiap bug: REPRO (empiris) → AKAR → FIX → VERIFIKASI (gate HIJAU). Diurutkan terbaru di atas.

## BUG-30 — Impor pesanan bisa masuk ke TOKO YANG SALAH tanpa satu pun peringatan (✅ DIPERBAIKI 2026-08-12)

**Verdikt:** TERBUKTI — terjadi nyata saat uji UI sesi ini, bukan skenario karangan.
**Repro:** Wizard Impor → jenis `marketplace_orders` → pilih **TikTok Daluna** (satu dari 5 toko
TikTok bernama mirip) → unggah `samples/TikTok_UntukDikirim_2026-07-19.xlsx` (gudang platform
'Outfit Boutique') → commit. HASIL: **559 pesanan · Rp 59.783.811 masuk ke TikTok Daluna**,
rekap harian turunan ikut terbentuk di toko itu, HTTP 200, dan tidak ada satu pun layar yang
membantah. Omzet satu toko muncul di toko lain dan tidak ada cara menemukannya selain
menghitung ulang dari berkas asal.
**Akar:** hanya ada `platform_guard` (kolom `Purchase Channel` vs `platform` toko). Untuk berkas
TikTok dan toko TikTok, penjaga itu **selalu lolos**, sehingga tidak ada apa pun yang
memeriksa **toko mana** di dalam platform yang sama. Padahal ekspor Seller Center membawa kolom
`Warehouse Name` yang isinya seragam untuk seluruh berkas, dan master toko sudah menyimpannya
sejak F0.7 (`platform_warehouse_name`) — bahkan `Field("warehouse_name_raw", …)` sudah bercatat
*"Dibandingkan dengan gudang platform di master toko"*, tetapi pembandingnya **tidak pernah ditulis**.
**Fix:** `SourceType.shop_guard` (`core/marketing_import_schema.py`) = `warehouse_name_raw` untuk
`marketplace_orders`; di `routes/marketing_data_import.py` (endpoint `upload`, SEBELUM sesi dibuat):
(a) gudang berkas ≠ `platform_warehouse_name` toko tujuan ⇒ **400** menyebut keduanya;
(b) toko tujuan belum mengisi gudang **dan** gudang itu terdaftar pada toko lain ⇒ **400 yang
menyebut nama + kode toko pemiliknya** beserta dua jalan keluar; (c) tidak ada pemilik ⇒ tetap
boleh, tetapi sesi membawa `shop_guard_hint` yang tampil sebagai banner di wizard. Berkas yang
ditolak langsung dibuang dari disk. Di layar: **strip tujuan impor** di setiap langkah +
**panel penolakan menetap** (dulu pesannya hilang bersama toast 5 detik).
**Verifikasi:** `scripts/_verify_f1_shop_guard.py` SG-1…SG-5 PASS · UI-1c PASS (unggah tertahan
di langkah 3, panel merah tetap tampil >15 detik) · `test_core_f1_f2_omzet.py` 59/59 PASS
(tidak ada regresi pada jalur toko yang benar) · `scripts/gate.sh` 21/21 HIJAU.

---

## BUG-31 — Pagar F2 (omzet turunan) bisa dilangkahi lewat jalur IMPOR (✅ DIPERBAIKI 2026-08-12)

**Verdikt:** TERBUKTI empiris (`scripts/_verify_f2_import_lock.py`, kontrak 1–3 MERAH sebelum fix).
**Repro:** impor 559 pesanan (rekap 2026-07-19 jadi `orders_auto`, `locked_source=true`,
Rp 4.213.092 / 45 pesanan) → Wizard Impor → jenis **`sales_daily`** → berkas CSV berisi
`2026-07-19, total, 1000000, 5` → mode "Perbarui yang lama" → commit **200**. HASIL: rekap
tanggal itu menjadi **Rp 1.000.000 / 5 pesanan**, `source='import'`, `locked_source=False`.
**Akar:** `POST /api/marketing/sales-data` (entri manual) menolak 409 untuk dokumen turunan,
tetapi jenis impor `sales_daily` menulis ke koleksi **yang sama** (`marketing_sales_data`)
dengan kunci alami yang sama `(account_id, date, revenue_type)` — dan blok dedupe di `commit()`
melakukan `$set` **seluruh dokumen** tanpa pernah memeriksa `is_derived(existing)`. Dengan mode
"lewati", barisnya dilewati diam-diam ("duplikat") sehingga staf tidak pernah tahu angkanya diabaikan.
**Fix:** `core/marketing_sales_shape.derived_safe_update()` + `derived_lock_message()` — dipakai
penulis mana pun. Grup `metrics`/`traffic`, field fulfillment turunan, dan field akar identitas
(`source`, `locked_source`, `derived_from`, …) **tidak pernah** ikut ditulis; sisanya (rating,
funnel, live, konten) tetap masuk, dan hanya nilai **berarti** (bukan 0) yang ditulis supaya
angka dari sumber lain tidak terhapus. Barisnya dilaporkan "sebagian disimpan"/"dilewati"
beserta alasan + jalan keluar. Pratinjau juga sudah memberi peringatan lewat
`_annotate_derived_daily()` — sebelum tombol simpan ditekan, bukan sesudah.
**Verifikasi:** `scripts/_verify_f2_import_lock.py` KONTRAK-1…5 PASS · `gate_marketing_ssot.py`
10/10 HIJAU (G3/G4 bentuk & kunci alami rekap harian) · `test_core_f1_f2_omzet.py` 59/59 PASS.

---

## BUG-32 — `<Toaster/>` shadcn tidak pernah dipasang: 57 modul BISU (✅ DIPERBAIKI 2026-08-12)

**Verdikt:** TERBUKTI dengan pembacaan kode + layar (toast wizard tidak pernah muncul).
**Repro:** buka Wizard Impor, unggah berkas ke toko yang salah ⇒ backend menolak 400, tetapi
layar **tidak menampilkan apa pun**: staf tetap di langkah 3 tanpa keterangan, lalu menekan
"Unggah & periksa" berulang kali.
**Akar:** `frontend/src/App.js` hanya memasang `Toaster` dari `components/ui/sonner`. Sementara
itu **57 modul** memanggil `useToast()` dari `hooks/use-toast` (implementasi shadcn berbasis
state) yang **wajib** punya `<Toaster/>` dari `components/ui/toaster` di pohon React. Karena
komponen itu tidak pernah dirender, seluruh `toast({...})` modul-modul tersebut masuk ke store
lalu tidak pernah ditampilkan — gagal **tanpa galat** di console, jadi tidak pernah terlihat.
**Fix:** pasang `<ShadcnToaster />` berdampingan dengan Sonner (viewport-nya beda sudut: sonner
kanan-atas, shadcn kanan-bawah pada sm+, jadi tidak bertumpuk). Selain itu, pesan penolakan yang
PENTING tidak lagi hanya mengandalkan toast: `import-upload-error`, `import-commit-error`, dan
`sd-save-error` **menetap di layar** sampai datanya diubah.
**Verifikasi:** testing agent iteration_49 — "Toaster component working (toast messages visible)" ·
UI-1c/UI-4 PASS (panel menetap + toast terlihat).

---

## BUG-6 … BUG-9 — SELISIH KIRIM CMT→DA & DA→BUYER ✅ SUDAH DIPERBAIKI (2026-08-01)

Keempat bug (A/B/E/F pada `memory/HANDOFF_SELISIH_CMT_BUYER.md`) diperbaiki sesuai keputusan owner
2026-08-01. Ringkas fix + bukti:

| Bug | Fix | Verifikasi |
|---|---|---|
| **BUG-6** selisih kirim tanpa identitas | koleksi `cmt_short_shipments` + field buku kuantitas `qty_claimed_by_vendor`/`qty_short_open`/`qty_short_resolved`; dokumen deklarasi dikoreksi ke qty diterima & sisa kirim vendor naik | `tests/scenario_selisih_ssot.py` A3a–A4b · INV-16/17 |
| **BUG-7** `PUT` baris setelah QC selesai diterima diam-diam | ditolak **409** + dua endpoint koreksi resmi (stok FG & buku kuantitas ikut, ada `koreksi_history`) | A5, B2a–B2d |
| **BUG-8** stok FG tidak berkurang saat kirim ke buyer | `qty_ledger.issue_fg` (SSOT stok) + `rahaza_fg_movements` OUT, idempoten, pre-check stok, pembalikan saat force-edit/hapus SJ; alat perbaikan data lama `scripts/repair_selisih_ssot.py` | C1a–C1b, edge 7a/8a · INV-18 |
| **BUG-9** selisih buyer tidak membuka kapasitas kirim ulang | SATU definisi kapasitas = qty efektif DITERIMA; plus dokumen `buyer_short_records` + stok FG dikembalikan | C2a–C3d |

Gate sesudah fix: `scripts/gate.sh` **13/13 HIJAU** · `verify_produksi_maklon_invariants.py
--audit-only` **6/6** · `recompute_qty_ledger.py --dry-run` bersih.

---


## BUG-9 — Selisih terima buyer tidak membuka kapasitas kirim ulang (✅ DIPERBAIKI 2026-08-01)

**Verdikt:** TERBUKTI empiris (`tests/scenario_q3_natural.py`).
**Repro:** kirim 100 pcs ke buyer → `PUT /api/buyer-shipment-items/{id}/received {"qty_received":95}`
→ coba kirim ulang 5 pcs → **400** "melebihi qty terima dari CMT (100) minus yg sudah didispatch (100).
Maksimal kirim: 0 pcs."
**Akar:** DUA pagar dengan definisi berbeda. `_validate_source_receipts_cap`
(`routes/buyer_shipment.py:135-138`) menghitung "sudah didispatch" dari **`qty_shipped`**, sementara
pagar produced-cap (`:652-654`) menyatakan cap memakai **qty diterima** ("shortfalls re-open capacity").
Pagar yang lebih ketat menang ⇒ selisih tidak pernah bisa dikirim ulang.
**Rencana fix:** satukan definisi → pakai qty efektif diterima (`qty_received` bila ada, else
`qty_shipped`). Detail: `memory/HANDOFF_SELISIH_CMT_BUYER.md` §7 P0-4.

---

## BUG-8 — Stok FG TIDAK berkurang saat barang dikirim ke buyer (✅ DIPERBAIKI 2026-08-01)

**Verdikt:** TERBUKTI empiris. Kirim 100 pcs ke buyer → stok FG SKU tetap **100 pcs**;
`rahaza_stock_ledger` hanya berisi `add … source=cmt_receipt`, `rahaza_fg_movements` hanya `IN`.
**Akar:** `create_buyer_shipment` (`routes/buyer_shipment.py:530`) hanya memposting **jurnal COGS**
(dan untuk `business_type='maklon'` COGS pun di-skip, `:743-755`); tidak ada `stock_service.issue`
untuk dispatch buyer di seluruh backend. Padahal FG masuk stok saat penerimaan CMT
(`core/production_qty_ledger.py:242`). Akibat: qty & nilai gudang FG menggelembung permanen.
**Rencana fix:** keluarkan stok FG (idempoten per `dispatch_seq`) + alat perbaikan data lama +
invarian INV-18. Detail: `memory/HANDOFF_SELISIH_CMT_BUYER.md` §7 P0-3.

---

## BUG-7 — Edit baris penerimaan CMT SETELAH QC selesai diterima diam-diam (✅ DIPERBAIKI 2026-08-01)

**Verdikt:** TERBUKTI empiris (`tests/scenario_owner_questions.py`, bagian Q1-b).
**Repro:** selesaikan QC penerimaan (lolos 90) → `PUT /api/prod/cmt-receipts/{id}/lines/{lid}`
`{"qty_actual":100}` → **HTTP 200**; baris jadi 100 **tetapi** `qty_accepted` tetap 90 dan stok FG
tetap 90 ⇒ angka bercabang tanpa peringatan (INV-14 pecah).
**Akar:** `update_line` (`routes/dewi_cmt_packing.py:466`) **tidak punya gerbang status** (bandingkan
`update_receipt` `:404` yang menolak bila status ≠ `Sedang QC`), dan `apply_receipt_result` idempoten
via `qty_ledger_applied_at` sehingga tidak pernah dihitung ulang. Tidak ada endpoint
`reopen`/`undo`/`koreksi` (sudah dipastikan tidak ada).
**Rencana fix:** tolak 409 setelah QC selesai + fitur "Koreksi Hasil QC" yang membalik stok &
menghitung ulang buku kuantitas (pakai `scripts/recompute_qty_ledger.py` sebagai mesinnya).
Detail: `memory/HANDOFF_SELISIH_CMT_BUYER.md` §7 P0-2.

---

## BUG-6 — "Selisih kirim" (barang tidak sampai) tidak punya identitas & dokumen tidak bisa dikoreksi (✅ DIPERBAIKI 2026-08-01)

**Aturan owner (2026-07-31):** kalau vendor mengklaim kirim 100 tapi yang benar-benar sampai 90,
maka **dokumen deklarasi WAJIB dikoreksi menjadi 90** dan **10 pcs tetap kewajiban vendor**
(harus dicari: lupa kirim/hilang) dengan **penyelesaian yang tercatat**. Ini BEDA dari kasus reject
(barang sampai tapi cacat) — untuk reject `produced_qty` memang tetap 100.
**Kondisi sekarang (terbukti):** `qty_declared` tetap 100 selamanya; selisih hanya angka turunan
(`declared − accepted − reject`) yang tidak punya field, tidak tampil di ringkasan PO / portal vendor,
tidak menaikkan sisa kirim vendor, dan tidak punya dokumen penyelesaian. `qty_shipped_by_cmt` bahkan
**tidak ada di whitelist** `update_line` (`routes/dewi_cmt_packing.py:472-479`) ⇒ klaim vendor tidak
bisa dikoreksi lewat API. Koreksi deklarasi di `buyer_shipment_items` (`:791`) TIDAK menular ke
baris penerimaan.
**Rencana fix:** field `qty_short_open/resolved`, endpoint koreksi deklarasi (merambat ke deklarasi
vendor), endpoint penyelesaian selisih, invarian INV-16/17, kolom UI "Belum sampai" + alarm.
Detail lengkap + kriteria terima: `memory/HANDOFF_SELISIH_CMT_BUYER.md` §1, §4, §7 P0-1.

---


## BUG-5 — Restore database lewat portal SELALU gagal (HTTP 500 pesan KOSONG) karena limit FD mongod 1024 (✅ DIPERBAIKI 2026-07-31)

**Verdikt:** TERBUKTI (curl + log mongod + reproduksi subprocess). Bug BARU.

**Repro (sebelum fix):**
```bash
curl -X POST localhost:8001/api/admin/backup/restore -H "Authorization: Bearer $TOKEN" \
     -H 'Content-Type: application/json' -d '{"backup_id":"<id>","confirm":true}'
# → {"status":500,"detail":"Restore error: 500: Restore failed: "}   ← sebab KOSONG
# Jalankan skrip yang sama manual → RC=0, 3.756 dokumen sukses (kadang), lalu gagal lagi.
```

**Akar (dua lapis):**
1. **Lingkungan** — supervisord menjalankan `mongod` dengan soft `RLIMIT_NOFILE` = **1024**
   (`/proc/<pid>/limits`). Restore 186 koleksi → WiredTiger `__posix_directory_sync` →
   `error 24 Too many open files` → `WT_PANIC: the process must exit and restart` →
   `Fatal assertion 50853` → **mongod abort**; `mongorestore` lalu melaporkan
   `connection closed unexpectedly by the other side: EOF` dan berhenti separuh jalan.
   Config supervisor READ-ONLY ⇒ harus dinaikkan runtime (`prlimit64`).
2. **Kode** — `scripts/restore.sh` memakai `mongorestore ... 2>&1` (stderr → stdout), sedangkan
   endpoint hanya membaca `result.stderr` (selalu kosong); lalu `except Exception` menangkap
   `HTTPException` yang baru saja dibuatnya sendiri → pesan jadi dobel-bungkus tanpa sebab.

**Fix:** `backend/utils/mongod_fdlimit.py` (penjaga limit: startup + APScheduler 5 menit +
pre-backup/pre-restore) · `scripts/ensure_mongod_fdlimit.sh` · `bootstrap.sh` langkah 1c ·
`routes/admin_backup.py` (diagnosa gabungan stdout+stderr → sebab+saran, ANSI dibuang, log
disimpan ke `/app/backups/<id>/restore_<ts>.log`, `except HTTPException: raise`) ·
`BackupRestoreModule.jsx` (panel Sebab/Saran/log di dialog, kontras aman tema terang & gelap).

**Verifikasi:** `tests/verify_backup_restore_fix.py` **15/15 PASS** · restore asli **3.756 dok /
0 gagal** · setelah `supervisorctl restart mongodb` limit 1024 dinaikkan otomatis ke 200.000 oleh
endpoint lalu restore sukses · panel error tampil di browser (Playwright) · login 6 akun HTTP 200.

---

---

## BUG-4 — `datetime` adalah SUBCLASS `date` → `/api/dewi/cmt/lifecycle` HTTP 500 POLOS (✅ DIPERBAIKI 2026-07-25, FASE 11)

**Verdikt:** TERBUKTI (curl + traceback backend + uji level-fungsi). **Bug BARU** — belum pernah tercatat.

**Repro (sebelum fix):** `GET /api/dewi/cmt/lifecycle` **tanpa parameter apa pun** → HTTP 500.
Traceback: `TypeError: can't compare datetime.datetime to datetime.date`
(`routes/dewi_cmt_lifecycle.py:95`), lalu setelah lapisan pertama diperbaiki muncul
`TypeError: 'datetime.datetime' object is not subscriptable` (`:124`).

**Akar:**
```python
def _parse_date(v):
    if isinstance(v, date):   # ← True JUGA untuk datetime (datetime turunan date)
        return v              #   objek datetime lolos apa adanya
```
Data nyata memicunya: `deadline_date` tersimpan sebagai string `'2026-07-23'` (→ `date`) sedangkan
`completed_at`/`updated_at` sebagai BSON `datetime`. Perbandingan campuran → TypeError.
Lapisan kedua: kode mengasumsikan semua kolom tanggal berupa string lalu memotongnya `[:10]` —
objek `datetime` tidak bisa di-slice.

**Fix:** cek `datetime` **sebelum** `date` dan selalu kembalikan `date` murni; tambah `_date_key()`
untuk kunci perbandingan seragam (`'YYYY-MM-DD'`) dipakai pada slicing & 2 `sorted(key=…)`.
Diterapkan pada **3 file berjebakan identik**: `routes/dewi_cmt_lifecycle.py`,
`routes/rahaza_ar_360.py`, `routes/production_control_tower.py`. Versi umum ada di
`utils/query_guards.to_date()` / `date_key()`.

**Catatan jujur:** `rahaza_ar_360.py` & `production_control_tower.py` **belum meledak di preview**
semata karena datanya masih kosong (`due_date` semuanya `None`) — di DB produksi jebakannya aktif.
Modul UI `cmt-lifecycle` saat ini redirect ke `vendor-admin`, jadi belum terpakai langsung dari layar.

**Verifikasi:** `scripts/verify_fase11.py` BAGIAN 1a (level fungsi, 18 assertion) + 1b (5 endpoint
lewat HTTP) — semuanya PASS. Endpoint kini 200 dengan data nyata (4 vendor).

---

## BUG-5 — kode akun modul Aset TIDAK ADA di CoA (✅ DIPERBAIKI 2026-07-25, FASE 11)

**Verdikt:** TERBUKTI (gate `verify_data_integrity` INV-GL-3 merah + inspeksi CoA). **Bug BARU.**

**Repro:** buat aset lewat `POST /api/assets` → jurnal yang lahir memakai `account_code` `"1500"` dan
`"1100"`. Cek CoA (264 akun, format bersegmen `1-2500`, `1-110`, `2-1100`): **tidak satu pun cocok**.
Disposal lebih parah — `1590`, `1500`, `1100`, `8100`, `6300`, semuanya tidak ada.

**Akar:** modul Aset menulis kode akun secara HARDCODE 4-digit dan **melewati** sistem
`rahaza_posting_profiles`, padahal profil `asset_acquisition`
(`debit_fixed_asset: 1-2500`, `credit_ap_clearing: 2-1100`) dan `asset_disposal` **sudah ada dan
kodenya sudah valid**. Semua 33 posting profile lain kodenya 100% valid — modul Aset satu-satunya
yang menyimpang.

**Dampak:** setiap pembelian & disposal aset menghasilkan jurnal ke **akun hantu** → tidak muncul di
Buku Besar / Neraca Saldo per akun, dan gate integritas merah terus sehingga temuan lain tenggelam.

**Fix:** modul baru `backend/routes/asset/_accounts.py` — `resolve_asset_accounts(db)` mengambil kode
dari posting profile (SSOT), memvalidasi ke CoA, memakai fallback yang dipastikan ada, dan mengambil
**nama akun langsung dari CoA**. Dipakai di `assets_core.py` (pembelian) dan `disposal.py` (2 jalur:
dispose langsung & approve request).

**Verifikasi:** pembelian → `1-2500 / 1-110`; disposal → `1-2501 / 1-2500 / 1-110 / 6-4200`,
seimbang (Dr 1.000.000 = Cr 1.000.000), **semua kode ada di CoA**.
`verify_data_integrity` kini **PASS 20 / FAIL 0**.

---

## BUG-R11-A — Query param tak tervalidasi → HTTP 500 (SISTEMIK) — ✅ DITUTUP TUNTAS (2026-07-25, FASE 11)

**Status sebelumnya:** 🔴 OPEN (DISCOVERY) sejak audit `memory/ROBUSTNESS_AUDIT.md`.

**Kenapa sempat dikira beres:** sesi sebelumnya menguji dengan **8 sampel endpoint**; 7 di antaranya
kebetulan yang sudah diperbaiki, jadi terlihat hijau padahal perbaikannya belum menyeluruh.

**Pembuktian menyeluruh:** alat baru `scripts/sweep_query_robustness.py` menyapu **SELURUH** GET
endpoint dari `/api/openapi.json` (898) × **8 varian query rusak** = **7.184 request** (read-only).

| | Sebelum | Sesudah |
|---|---|---|
| Request 5xx | **66** | **0** |
| Endpoint bermasalah | **51** | **0** |

**4 kelas akar masalah:** `LIMIT_NEG` (`to_list(length=-1)`), `INT_CAST` (`int()` manual tanpa
try/except), `DATE_PARSE` (`fromisoformat` tanpa guard), `MONTH_OOB` (`date(y, 99, 1)`).

**Fix:** helper baru `backend/utils/query_guards.py` + **46 endpoint di 36 file router**
(batas `Query(ge=…, le=…)` untuk parameter terdeklarasi, `q_int`/`q_date` untuk yang membaca
`request.query_params` sendiri, helper `_month_bounds()` menggantikan 5 salinan parsing bulan
di `marketing_livehost_analytics.py`).

**Catatan false positive:** 5 dari 51 "endpoint bermasalah" versi pertama ternyata sehat — endpoint
LLM (`/api/finance/ai-cashflow` ≈ 20 dtk) menahan slot koneksi saat sweep paralel sehingga tetangganya
time-out (`status=-1`). Diprobe serial: 200/404 dalam < 10 ms.

**Verifikasi:** `scripts/verify_fase11.py` BAGIAN 2 (45 kasus query rusak → semuanya 400/422),
BAGIAN 3 (endpoint LLM ditolak dalam 0,05 dtk — model tidak dipanggil), BAGIAN 4 (10 nilai sehat
tetap 200, tidak over-blocking). `backend_test_fase11.py` **45/45 PASS**.

**Benign (bukan bug):** `/api/push/vapid-public-key` → 503 "Web Push not configured" (by-design).

---

## BUG-R11-B / BUG-R11-SM-1 / BUG-R11-SM-2 / P3 ap-invoices — ✅ SUDAH SEHAT (dokumen sempat usang)

**Catatan FASE 11 (2026-07-25):** keempatnya masih ditandai 🔴/🟡 **OPEN** di registri ini, padahal
probe langsung (`scripts/probe_open_bugs.py`) membuktikan semuanya sudah diperbaiki di sesi-sesi
sebelumnya tanpa sempat dicatat:

| Bug | Probe | Hasil |
|---|---|---|
| BUG-R11-B | `GET /api/rahaza/material-stock` | **200** (sehat) |
| BUG-R11-SM-1 | `POST /api/dewi/rnd/patterns/<id-hantu>/approve` | **404** (benar, bukan 200 palsu) |
| BUG-R11-SM-2 | `POST /api/dewi/rnd/tech-packs/<id-hantu>/approve` | **404** (benar) |
| P3 | `POST /api/rahaza/ap-invoices` body kosong | **400** (ditolak) |

**Pelajaran:** registri bug WAJIB di-update saat bug ditutup. Bug yang sudah beres tapi tercatat OPEN
membuat sesi berikutnya membuang waktu — dan lebih berbahaya lagi, melatih orang mengabaikan status.

---

## BUG-FE-CONTRACT-1..3 + BUG-BE-500-1 — Kontrak FE↔BE (F1–F4) (P1) — ✅ DIPERBAIKI (2026-07-06)

**Verdikt:** TERBUKTI (curl + testing_agent_v3 iter_61 = 100%). Sebelumnya berstatus DISCOVERY (belum diperbaiki); sesi ini user minta perbaiki bug terdokumentasi → keempatnya di-fix.

**Repro (sebelum fix):**
- **F1** `GET /api/rahaza/finance/ap-invoices?status=sent` → **404** (FE `PurchaseDiscountModule.jsx:21,61`).
- **F2** `GET /api/rahaza/finance/ar-invoices/overdue-report` → **404** (FE `BadDebtWriteOffModule.jsx:29,50`).
- **F3** `GET/PUT /api/invoice-edit-requests[/{id}/approve|reject]` → **404** (FE `ApprovalModule.jsx`, modul live `fin-approval`). Router lama dihapus Session #11.16 Phase D.
- **F4** `GET /api/rahaza/material-stock` → **500** pada data tertentu (dipakai 4 modul stok).

**Akar:**
- **F1/F2** — FE memakai prefix salah `/api/rahaza/finance/...`; backend `rahaza_finance.py` ber-prefix `/api/rahaza` (route `/ap-invoices/*`, `/ar-invoices/*`) tanpa segmen `/finance`.
- **F3** — endpoint tak pernah di-restore setelah `routes/finance.py` dihapus, padahal modul `fin-approval` ("Persetujuan Invoice") masih terpasang di nav Portal Finance.
- **F4** — `list_stock()` akses `s["material_id"]`/`s["location_id"]` tanpa `.get()` (KeyError bila key hilang) + perbandingan `current_qty < min_stock_qty` bila nilai bertipe string (TypeError) → 500.

**Fix:**
1. **F1** `PurchaseDiscountModule.jsx` — 2 fetch: `/api/rahaza/finance/ap-invoices*` → `/api/rahaza/ap-invoices*`.
2. **F2** `BadDebtWriteOffModule.jsx` — 2 fetch: `/api/rahaza/finance/ar-invoices/*` → `/api/rahaza/ar-invoices/*`.
3. **F3** — router BARU `routes/invoice_edit_requests.py` (GET list, POST create, PUT `{id}/approve`, PUT `{id}/reject`). Approve menerapkan `after_snapshot` (whitelist: `notes`/`discount_amount`/`total`→recompute `balance`/`items`) ke invoice target (`rahaza_ar_invoices`/`rahaza_ap_invoices`) + audit ke `invoice_change_history`; approve/reject butuh role admin/superadmin (403 jika bukan). Registered di `server.py`. `ApprovalModule.jsx` juga membaca `data.detail` untuk pesan error.
4. **F4** — helper `_num()` (koersi float aman + guard NaN/inf → None) + `.get()` untuk material_id/location_id (filter None) di `rahaza_inventory_stock.py::list_stock`.

**Verifikasi:**
- curl: F1 `/api/rahaza/ap-invoices?status=sent`→200 (path lama→404); F2 `/ar-invoices/overdue-report?days=30`→200 (path lama→404); F4 `/material-stock`→200 (bahkan dgn doc malformed: min_stock string, qty string, key hilang); F3 full workflow create→approve (invoice target ter-update: notes/total/discount/balance benar), edge case approve non-Pending→400, approve/reject id hantu→404, reject tanpa notes→400.
- **testing_agent_v3 iter_61 = 100%** (backend 15/15 + frontend semua modul load tanpa 404, 0 regresi, 0 red-screen).
- DB pristine: semua artefak uji dibersihkan (0 residual).

**Pelajaran:** modul FE bisa "yatim" (masih di nav) setelah router backend dihapus saat deprecation — audit kontrak FE↔BE + restore/deprecate secara eksplisit. Endpoint list read wajib defensif terhadap data legacy bertipe salah.

---

## BUG-FE-AUTH-1 — Panel admin gagal (auth header hilang di frontend) (P1) — ✅ DIPERBAIKI

**Verdikt:** TERBUKTI (empiris; dilaporkan user via screenshot "Gagal fetch status" + curl 401/200 + verifikasi browser).

**Repro:** Buka **Portal Keuangan → Akuntansi & Laporan → Admin Setup (COA/Profiles)** (`Phase 7F`):
- Toast **"Gagal fetch status"** muncul; semua counter tampil **0** (COA 0, Posting Profiles 0) padahal DB berisi **COA=274, Posting Profiles=33**.
- `curl GET /api/rahaza/admin/accounting-status` **tanpa** `Authorization` → **HTTP 401**; **dengan** Bearer → **HTTP 200** (data benar).

**Akar:**
- `frontend/src/components/erp/AdminSetupPanelModule.jsx` memakai `fetch(..., { credentials: 'include' })` (cookie) **tanpa** header `Authorization: Bearer <token>`, padahal seluruh aplikasi (224 modul) memakai JWT Bearer dari `localStorage('erp_token')`. Endpoint backend `_require_super` menolak (401) → toast + fallback 0.
- Terdampak **4 fetch** di modul ini (`accounting-status`, `seed-coa`, `seed-posting-profiles`, `seed-all-accounting`) → panel sepenuhnya tak berfungsi (status + semua tombol seed).
- **Bug identik ditemukan** di `MarketingARBridgeModule.jsx` (Phase 7E) pada `POST /api/marketing/sales-data/generate-ar-batch` (curl no-auth→401, bearer→200).

**Fix:**
- Tambah helper `authHeaders()` = `{ Authorization: Bearer ${localStorage.getItem('erp_token')} }` dan ganti semua `credentials: 'include'` → `headers: authHeaders()` di kedua modul (pola standar aplikasi).

**Verifikasi:**
- Browser (login admin) → panel Admin Setup menampilkan **COA Ready 274 / Posting Profiles Ready 33**, **tanpa** toast "Gagal fetch status".
- Pola fetch di-browser: lama (`credentials:'include'`)→**401**, baru (Bearer)→**200**. Babel parse kedua file OK. DB tetap pristine (0 artefak).

**Pelajaran:** surface **admin-utility + integrasi FE↔BE** tidak tercakup uji "importance-weighted" (uang/stok/concurrency). Ini contoh konkret risiko *breadth* (~76%): endpoint hanya diuji reachability/no-5xx, bukan integrasi auth end-to-end.

---

## BUG-FE-CONTRACT-1..3 + BUG-BE-500-1 — Temuan audit kontrak FE↔BE (✅ DIPERBAIKI 2026-07-06 — lihat entri teratas)

**Verdikt:** TERBUKTI via static-match + runtime GET-probe + verifikasi grep backend. **✅ Sudah diperbaiki** (2026-07-06, testing_agent_v3 iter_61 = 100%). Detail fix ada di **entri teratas** registri ini. Detail discovery: `memory/FE_BE_CONTRACT_AUDIT.md`.

- **BUG-FE-CONTRACT-1** — `PurchaseDiscountModule.jsx:21,61` memanggil `/api/rahaza/finance/ap-invoices[/{id}/payment]`; backend sebenarnya `/api/rahaza/ap-invoices/*` (prefix `/api/rahaza`, tanpa `/finance`). Probe **404**. → modul gagal ambil AP & catat pembayaran.
- **BUG-FE-CONTRACT-2** — `BadDebtWriteOffModule.jsx:29,50` memanggil `/api/rahaza/finance/ar-invoices/{overdue-report, {id}/write-off-bad-debt}`; sebenarnya `/api/rahaza/ar-invoices/*`. Probe **404**. → laporan overdue & write-off gagal.
- **BUG-FE-CONTRACT-3** — `ApprovalModule.jsx:41,69,101` memanggil `/api/invoice-edit-requests[/{id}/approve|reject]` yang **tidak terdaftar** di backend (grep kosong; hanya komentar di `server.py`). Probe **404**. → modul Approval invoice-edit gagal.
- **BUG-BE-500-1** — `GET /api/rahaza/material-stock` (rahaza_inventory_stock.py) mengembalikan **HTTP 500 PLAIN** (bahkan tanpa query, dengan auth). Dipakai `RahazaStockModule`/`InventoryScrapModule`/`RahazaFGInventoryModule`/`MaklonMaterialIssuePanel` → endpoint efektif rusak. Prioritas tinggi. (harusnya 200/400, bukan 500).

**Rekomendasi:** F1–F2 = perbaiki path (hapus segmen `/finance`); F3 = implementasi endpoint backend atau nonaktifkan modul; F4 = tambah guard param/try-except agar 400 bukan 500.

---

## BUG-R11-A — Query param tak tervalidasi → HTTP 500 (SISTEMIK, ~43 GET endpoint) (✅ DITUTUP 2026-07-25 FASE 11 — lihat entri teratas; catatan discovery di bawah dipertahankan sebagai arsip)

**Verdikt:** TERBUKTI via robustness sweep (GET, read-only) + isolasi manual. **Belum diperbaiki**. Detail: `memory/ROBUSTNESS_AUDIT.md` (AUDIT 1).

- **Gejala:** ~43 list-endpoint mengembalikan **500** saat query malformed (`limit=-1`, `date_from=notadate`, `skip=zzz`, `year=abcd`), semestinya **400/422**.
- **Akar:** nilai query diteruskan tanpa validasi — mis. `limit` negatif ke Motor `.limit()/.to_list()`, atau `int()/date parse` tanpa `try/except`.
- **Contoh terverifikasi** (`limit=-1`→500): `/api/dewi/rnd/styles`, `/api/dewi/kasbon/requests`, `/api/hr/job-board/jobs`. Endpoint lain 500 oleh param berbeda (heterogen).
- **Dampak:** UX buruk + potensi kebocoran stack (mitigasi: sudah ada handler generik "Internal server error" tanpa detail). Bukan bug uang/state, tapi robustness breadth.
- **Rekomendasi:** codemod — pakai `Query(ge=..., le=...)` untuk limit/skip/page + `try/except` pada parsing tanggal → fallback 400. (Mirip pola perbaikan sistemik R-sebelumnya.)

**Catatan benign:** `/api/push/vapid-public-key` → 503 "Web Push not configured" = **by-design** (bukan bug).

**AUDIT 2 (peta gap):** **167 endpoint transisi status** teridentifikasi; baru ~7 diuji adversarial (cutting/finishing/QC/asset/reserve/AR-AP payment/stock adjust) di R6–R10. Sisanya belum diprobe transisi ilegal.

---

## BUG-R11-SM-1/2 — approve tanpa guard not-found (2 endpoint R&D) (✅ SUDAH SEHAT — diverifikasi 2026-07-25 FASE 11; arsip discovery)

**Verdikt:** TERBUKTI via state-machine adversarial sweep (probe ke ID hantu, read-only, 0 residual data bisnis). **Belum diperbaiki.** Detail: `memory/STATE_MACHINE_AUDIT.md`.

- **BUG-R11-SM-1** — `POST /api/dewi/rnd/patterns/{pattern_id}/approve` (`dewi_rnd_design.py:195`): `update_one({id},{$set})` tanpa `find_one`/`matched_count`/upsert → id tak-ada balas **200 palsu** (harusnya 404). Tak ada phantom-write.
- **BUG-R11-SM-2** — `POST /api/dewi/rnd/tech-packs/{tp_id}/approve` (`dewi_rnd_hpp.py:208`): pola sama, **200 palsu** untuk id tak-ada.
- Severity **rendah** (menyesatkan, bukan korupsi/uang). Inkonsisten dgn sibling yg sudah `find_one`→404.
- **Hasil sweep:** 163/166 endpoint transisi ber-`{param}` diprobe → **161 AMAN** (4xx), **0 crash 500**, **2 temuan** di atas. 3 endpoint tanpa `{param}` di-skip (butuh seed synthetic).

---

## BUG-AUTH-1 — Endpoint bisa diakses TANPA login (P0) — ✅ DIPERBAIKI

**Verdikt:** TERBUKTI (empiris; runtime sweep 666 GET + `verify_auth_coverage.py`).

**Repro:** `GET` tanpa header `Authorization` → **HTTP 200** (data terekspos) pada 8 endpoint:
```
/api/marketing/reviews/categories        /api/marketing/reviews/platforms
/api/marketing/returns/reasons           /api/marketing/discounts/types
/api/marketing/content-calendar/types    /api/marketing/content-calendar/platforms
/api/marketing/integration-settings/meta /api/procurement/request-types
```

**Akar:**
- 7 endpoint referensi marketing (enum/label dropdown) tak memanggil enforcer auth sama sekali.
- `dewi_procurement.py::get_request_types` membungkus `require_auth` dalam `try/except: pass`
  (sengaja "auth optional") → LOLOS statis (nama `require_auth` terdeteksi) tapi 200 di runtime
  (**false-negative** scanner).

**Fix (portal-based RBAC read-guard, pilihan user):**
- Tambah `await require_portal(request, ...)` (SSOT `routes/shared.py`) di 8 endpoint:
  marketing → portal `"toko"`; procurement → portal `"finance"/"assets"/"management"`.
- `require_portal` = `require_auth` (401 bila tanpa/invalid token) + cek akses portal (403 bila
  login tapi salah portal). SUPER_ROLES selalu lolos.

**Verifikasi:** 8/8 → **401 tanpa token, 200 dengan token superadmin** (tanpa regresi pada endpoint
sibling). `verify_auth_coverage.py` → **0 temuan** (dari HIGH 10 | MED 23). Runtime sweep 666 GET →
**0 kebocoran**. Testing agent backend: **39/39 PASS** (`test_reports/iteration_50.json`).

---

## FALSE-POSITIVE dicegah — INV-AUTH-01 (delegasi & dependency level-router)

**Verdikt:** FALSE-POSITIVE → scanner dikalibrasi (bukan menambal kode yang sudah aman).

1. **`/api/wms/legacy/*`** — bridge router; tiap handler memanggil handler `routes/warehouse.py`
   yang SEMUANYA `require_auth` (runtime → 401). Statis tampak "no-auth" karena delegasi antar-file.
   → di-whitelist `DELEGATED_AUTH_PREFIXES` + verifikasi runtime 401 (no-token) / 200 (token).
2. **`POST /api/rahaza/payroll-runs/{id}/retry-post`** (`retry_post_alias`) — router memasang
   `dependencies=[Depends(require_portal_dep("hr","finance"))]` (auth LEVEL-ROUTER) → semua endpoint
   tercakup, tapi scanner per-fungsi buta. → tambah deteksi `_router_has_auth_dep()` di
   `verify_auth_coverage.py`. Runtime → 401 (no-token) terkonfirmasi.
3. **`/api/tv/*`** & **`/api/push/vapid*`** — publik by-design (display lantai produksi read-only;
   kunci PUBLIK VAPID web-push). → di-whitelist `PUBLIC_PREFIXES`.

**Pelajaran:** gate WAJIB memahami delegasi lintas-modul + dependency level-router agar tak
menghasilkan "merah palsu"; dan CROSS-CHECK runtime menangkap "auth optional" yang lolos statis.

---

## BUG-1 — RC-5 Concurrency: penomoran dokumen balapan (P1) — ✅ DIPERBAIKI (jurnal)

**Verdikt:** TERBUKTI (empiris, `verify_concurrency.py`).

**Repro:** 5× `POST /api/rahaza/journals` paralel, tanggal sama, payload 2-baris seimbang →
**4 dari 5 = HTTP 500** (`E11000 duplicate key: je_number`). Single-thread happy-path selalu 200 →
inilah "green-but-broken".

**Akar:**
- `routes/rahaza_journals.py::_gen_je_number` memakai `count_documents(prefix)+1` (non-atomik).
  Dua request membaca count yang sama → menghasilkan `je_number` identik.
- Ada **unique index** `je_number` → balapan berubah jadi crash 500 (bukan duplikat diam).
- Melanggar SSOT: `da` sudah punya `utils/counters.next_counter` (atomic `$inc`) tapi tak dipakai.

**Fix (minimal + reversible):**
1. Helper baru `utils/counters.gen_prefixed_number(db, collection, field, prefix, width)` —
   atomic `$inc` via koleksi `counters` (SSOT) + **lazy max-init** (seed seq ke nomor tertinggi
   yang ada, agar tak bentrok dengan data count-based historis).
2. `_gen_je_number` kini memakai helper tsb.
3. Safety-net retry-on-`DuplicateKeyError` (regenerasi nomor) di sekitar `insert_one`.

**Verifikasi:** setelah fix, 5/5 = 200 dengan `je_number` unik. `verify_concurrency.py` → HIJAU.
Regresi data-integrity → tetap HIJAU.

**SISTEMIK (BUG-1b, P2) — ✅ DIPERBAIKI (2026-07-05):** pola `count_documents+1` sisa pada koleksi
bernomor NON-unique-indexed (silent duplicate-number risk) kini dimigrasi ke `gen_prefixed_number`
(atomic `$inc` + lazy max-init) di 10 titik aktif:
```
rahaza_fg_matrix.py (reservation_no)   warehouse.py (asset_code FA-)
dewi_cmt_packing.py (_seq → receipt_code)  dewi_accessories_opname.py (session_no OPNAME-)
dewi_accessories_loans.py (session_no OPNAME-)  finishing.py (batch_no FIN-)
rahaza_employee_loans.py (loan_number LOAN-)  qc.py (inspection_no QC- + rework batch_no FIN-…R)
rahaza_grn_qc.py (inspection_no INS-)  workspace.py (version_num → _next_version_num per-dokumen)
```
**Verifikasi empiris:** 8× POST paralel `/api/finishing/batches` → 8/8 200 nomor UNIK; 8× paralel
`/api/prod/cmt-receipts` → 8/8 201 `receipt_code` UNIK (lazy-init benar dari max historis). Gates:
`verify_concurrency.py` HIJAU, `verify_bughunt.py` 12/12, `verify_data_integrity.py` 20/20.
`dewi_accessories_full_backup.py` = file mati (tak di-import) → dilewati.

**LANJUTAN SWEEP (Session #29) — ✅ +17 titik lagi dimigrasi ke `gen_prefixed_number`:**
3 titik P1 (koleksi unique-indexed → risiko 500 E11000): `wms_cmt_dispatches.py` (dispatch_no),
`wms_delivery_notes.py` (sj_number), `dewi_maklon_samples.py` (sample_code), `dewi_procurement.py`
(`_gen_po_number_proc` → rahaza_purchase_orders.po_number unik). Sisa P2 (silent dup):
`wms_opname2.py` (session_no), `rahaza_bank_transfers.py` (ref_number), `rahaza_finance.py`
(`_gen_number`), `rahaza_inventory_fg.py` (issue_number FGI), `rahaza_shipments.py` (shipment_number),
`asset/_helpers.py` (asset_number AST), `dewi_accessory_requests.py` + `dewi_cmt_component_requests.py`
+ `dewi_kreator_requests.py` (request_code), `dewi_kasbon.py` (request_number), `dewi_procurement.py`
(`_gen_pr_number`), `marketing_returns_routes.py` (cn_number), `production_jobs.py` (job_number +
child), `production_material_returns.py` (ref_no).
Gate `verify_concurrency.py`: `_UNIQUE_NUMBERED` diperluas (+8 koleksi) → CC2 statik HIJAU.
Sweep tool `/tmp/sweep_numbering.py` → 0 titik user-facing tersisa (sisa = seed script idempoten +
false-positive kolom Excel/caption foto).

**LANJUTAN SWEEP-2 (Session #29b) — ✅ +6 titik varian `(await … count_documents(…)) + 1`** (regex awal
lolos karena paren pembungkus `(await …)`): `dewi_accessories_items.py` (code ACC- di `rahaza_materials`,
unique+guard 409 → dulu race 409/dup), `dewi_accessories_requests.py` (request_number INT-REQ-),
`dewi_accessories_purchase.py` (pr_number ACC-PR-), `dewi_accessories_loans.py` (loan_number LOAN- di
`acc_loans`), `dewi_wh_returns.py` (`_next_code` → return_code WH-RET-), `production_returns.py`
(return_number RTN-). Semua → `gen_prefixed_number`. **Verifikasi empiris:** 12× POST paralel
`/api/acc/items` → 12/12 201, code ACC-0001..0012 UNIK, 0×5xx, 0×409-race (dulu pasti bentrok).
Grep gabungan (kedua varian regex) → NONE tersisa di route aktif.

**Recipe migrasi (untuk sisa/masa depan):** ganti `cnt = count_documents(regex); f"{prefix}{cnt+1:0Nd}"` →
`await gen_prefixed_number(db, "<collection>", "<field>", prefix, N)` + bungkus insert dgn
retry-on-DuplicateKey bila field punya unique index. Uji dengan menambah target di
`verify_concurrency.py`.

---

## BUG-2 — Adversarial 5xx: crash pada input non-numerik (P1) — ✅ DIPERBAIKI

**Verdikt:** TERBUKTI (empiris, `verify_adversarial_5xx.py`).

**Repro & akar:**
| Endpoint | Payload | Sebelum | Akar |
|---|---|---|---|
| `POST /api/rahaza/journals` | `debit:"abc"` | 500 | `float("abc")` di `_validate_lines` |
| `POST /api/rahaza/journals` | `lines:"bukan-list"` | 500 | iterasi string → `str.get` AttributeError |
| `POST /api/rahaza/ar-invoices/{id}/payment` | `amount:"abc"` | 500 | `float(body["amount"])` tanpa guard |
| `POST /api/rahaza/ap-invoices/{id}/payment` | `amount:"abc"` | 500 | idem |

**Fix:**
- `_validate_lines`: `isinstance(lines, list)` + `all(isinstance(ln, dict))` + `try/except` di
  konversi `float(debit/credit)` → `HTTPException(400)`.
- `rahaza_finance.py`: helper `_to_amount()` (float aman → 400 bila non-numerik), dipakai di 3
  handler pembayaran (AR/AP).

**Verifikasi:** 10/10 kasus adversarial kini 2xx/4xx (0 crash 5xx). `verify_adversarial_5xx.py` → HIJAU.

**Catatan (P3, belum diperbaiki):** `POST /api/rahaza/ap-invoices` menerima body tanpa `items`
→ membuat invoice Rp 0 (HTTP 200). Bukan crash, tapi validasi bisnis kurang (harusnya 400).

---

## FALSE-POSITIVE dicegah — INV-MKL-1 (RC-7 basis pajak)

**Verdikt:** FALSE-POSITIVE (setelah verifikasi empiris) → invarian dikalibrasi.

Gate awal menandai 2 maklon PO `amount_paid (11.322.000) > total_value (10.200.000)`. Investigasi:
rasio tepat **1.11 = PPN 11%**; `dewi_maklon_invoices` mengonfirmasi subtotal 10.2jt + pajak 1.122jt
= total 11.322jt = `amount_paid`. Pembayaran **benar** relatif ke invoice. Invarian dikalibrasi
tax-aware (INV-MKL-1) + smell didokumentasikan sebagai WARN (INV-MKL-2). Pelajaran: **gate wajib
dikalibrasi ke realita domain agar tak menghasilkan "merah palsu".**
