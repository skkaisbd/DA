# PRD — CV. Dewi Aditya ERP

## Overview
Integrated ERP (React + FastAPI + MongoDB) for a garment business covering Online Shop,
Maklon (contract manufacturing), Production (Cutting · CMT · QC · Packing), HR/SDM,
Warehouse (WMS), Marketing/KOL, and a full Finance/Accounting suite (37 modules).
UI language: **Indonesian**. Theme: global light mode (ThemeProvider + CSS variables).

## Architecture
- **Backend**: FastAPI. Entry `server.py` registers modular routers from `/app/backend/routes/`.
  All API routes prefixed with `/api`. Auth: JWT via `auth.py` (`require_auth`).
  DB: MongoDB via `motor` (`database.get_db()`). Docs use UUID string `id` + `{"_id": 0}` projections.
- **Frontend**: React + Shadcn/UI + Tailwind. Core routing in `App.js`. Multi-portal shell at
  `components/erp/PortalSelector.jsx`; module registry `components/erp/moduleRegistry.js`;
  nav in `components/erp/portal-shell/portalNav.js`.

## Personas
- Super Admin (admin@garment.com) — full access.
- Finance/Accounting staff, HR staff, Production operators, Maklon clients, LiveHost/KOL creators, Vendors.

## Marketing — SIKLUS TARGET · ANGGARAN · OMZET (F5, 2026-08-13)
Satu bulan kerja marketing dibaca dari **satu** sumber angka (`backend/core/marketing_cycle.py`):
- `GET /api/marketing/cycle/summary?account_id=&period=YYYY-MM` — target · omzet (2 angka: produk &
  order amount) · anggaran rencana/realisasi per kategori · marjin + **cakupan HPP** · ROI/ROAS ·
  flag peringatan · catatan kejujuran data.
- `GET /api/marketing/cycle/overview?period=` — semua toko + total + papan "perlu perhatian"
  (**peringkat & total dihitung backend**, bukan di browser, supaya export tidak pernah berbeda dari
  layar).
- Omzet **dibaca** dari rekap harian turunan (F2) — tidak dihitung ulang, supaya override SPV ikut
  terpakai dan tidak lahir angka omzet keempat.
- **Realisasi anggaran otomatis + bukti** (`diskon`, `ads`, `komisi`, `kol`, `livehost`): dihitung
  saat dibaca, **tidak** ditulis ke `marketing_spend_entries` (anti dobel-hitung). Kategori kanonik:
  `core.marketing_cycle.CATEGORIES`.
- **Kunci periode** (`marketing_period_locks`, `GET/POST /api/marketing/periods/lock`): jalur tulis
  yang menyentuh bulan tertutup menjawab **HTTP 423** (target · anggaran · belanja · rekap harian ·
  commit impor). Setiap tulis/buka tercatat di `marketing_change_log`.
- **Aturan uang pesanan:** `marketing_orders` menampung dua bentuk dokumen (impor Seller Center vs
  input manual). Semua pembaca WAJIB memakai pembaca defensif di
  `core.marketing_daily_rollup` (`order_revenue_product`, `order_amount_of`, `order_revenue_gross`,
  `order_seller_discount`, `item_qty`, `item_revenue`).
- Layar: Portal Marketing → **Target & Budget → tab "Siklus Bulan Ini"**; Portal Manajemen →
  **Siklus Marketing** (`mgmt-marketing-cycle`) — komponen yang SAMA lewat prop `scope`.
- Gate: `scripts/verify_marketing_cycle.py` (**INV-MKTCYCLE**, 31 kode) di `scripts/gate.sh`.

## Core Finance integration chains (validated)
- Journal → post to GL → Trial Balance (balanced) / GL / P&L / Balance Sheet / Cash Flow → void/reverse.
- AR invoice → payment → cash movement + GL. AP invoice → approval → payment → GL.
- P2P: PR → PO → GRN/3-way-match → AP invoice → payment.
- Fixed Assets: register → depreciation (per + batch) → disposal → GL (via Posting Profiles).
- Accruals → post → reverse → recurring-templates. Budget → items → variance. Periods → close/lock.
- Posting Profiles (33 event_type→GL mappings) drive auto-GL posting across events.

## Kontrak API — aturan yang WAJIB diikuti (ditetapkan FASE 11, 2026-07-25)
- **Query param WAJIB tervalidasi.** Parameter yang dideklarasikan harus memakai batas
  `Query(..., ge=…, le=…)`; yang dibaca manual dari `request.query_params` harus lewat
  `backend/utils/query_guards.py` (`q_int`, `q_date`, `q_year_month`, `q_period`, …).
  **Input sampah = HTTP 400/422, TIDAK PERNAH 500.** Gate: `scripts/sweep_query_robustness.py`
  (sapu seluruh GET endpoint × 8 varian query rusak; harus 0 error 5xx).
- **Tanggal dari Mongo harus dinormalkan.** `datetime` adalah SUBCLASS `date` di Python, jadi
  `isinstance(v, date)` juga True untuk `datetime`. Selalu pakai `to_date()` / `date_key()` dari
  `utils/query_guards.py`; jangan memotong string tanggal dengan `[:10]` tanpa normalisasi.
- **Kode akun jurnal HARUS berasal dari `rahaza_posting_profiles`,** bukan hardcode. CoA proyek ini
  berformat bersegmen (`1-2500`, `2-1100`), bukan 4-digit. Gate: `verify_data_integrity` INV-GL-3.
- **Nama field material memakai nama KANONIK saja** (`composition`, `material_kg_per_pcs`,
  `default_material_cost_per_kg`, `total_material_kg_per_pcs`, `total_material_kg`,
  `bulk_line_count`). Alias legacy `yarn_*` **tidak ditulis lagi** sejak FASE 11; endpoint masih
  MENERIMA nama legacy sebagai input dan `read_field()` masih bisa MEMBACA dokumen lama.
- **Setiap skrip uji WAJIB membersihkan artefaknya lalu MENGHITUNG ULANG untuk membuktikannya** —
  termasuk dokumen turunan (mis. jurnal yang lahir otomatis dari pembuatan aset/invoice).

## Modul lintas-portal yang wajib diketahui (sejak 2026-07)

- **Satuan & konversi (multi-UOM)** — SSOT `backend/core/uom.py`. Stok & HPP SELALU disimpan
  dalam satuan dasar; kemasan (pak/karton/rol) adalah faktor pengali. Titik masuk stok menerima
  field opsional `input_uom`. Mengganti satuan dasar item berstok HANYA lewat endpoint rebase
  (`POST /api/rahaza/materials/{id}/rebase-uom`) supaya qty & HPP ikut dikonversi.
  Guardrail: `scripts/guardrails/verify_uom_integrity.py`.
- **Penomoran dokumen** — SATU generator race-safe `utils/counters.gen_prefixed_number`, kini
  membaca format owner dari koleksi `doc_number_configs` (layar `sys-doc-numbering`).
  Katalog jenis dokumen: `backend/data/doc_number_registry.py`. Format rusak selalu jatuh
  ke bawaan kode — penomoran tidak boleh memblokir transaksi. JANGAN membuat generator kedua.
- **Asisten ERP CV. Dewi Aditya** — jawab dari basis pengetahuan statis
  `backend/data/portal_kb/*.json` lebih dulu (gratis); AI hanya cadangan. Menambah pengetahuan
  = menyunting JSON, bukan menulis kode.
- **Semua panggilan LLM** lewat `ai_cost_tracker.tracked_llm_call` → Anthropic SDK resmi dengan
  `ANTHROPIC_API_KEY`. Dilarang memanggil SDK LLM langsung dari route.

## Status — Juli 2026
**Healthy & stable.** COA 177 akun + 38 posting profiles (semuanya remapped ke CoA DA).
Auto-jurnal coverage 100%: 38 event types aktif (AR/AP/Payroll/Inventory/FA/Bank/Kasbon/Maklon/Variance).
Production seed 100% sukses (0 errors). Periode dinamis (3 bulan terakhir s/d bulan berjalan).
**Audit portal selesai (HR, Finance, Produksi, Gudang, Maklon, Marketing)** — semua modul render
tanpa crash & tabel terisi (testing_agent iteration_20 & 21).
- Gudang/WMS: lokasi, stok+ledger, GRN+inspeksi, fabric rolls, CMT dispatch, surat jalan, opname,
  fulfillment (queue+allocate), retur — semua ber-data (Section 50 seed).
- Maklon: dashboard, PO (dewi_maklon_pos SSOT), sample, invoice+payment, QC, dispatch, klien, catalog.
- Marketing: KOL+Leaderboard (fix 500), LiveHost (fix collection), Target Bulanan (actual dari
  marketing_sales_data), Unified Orders, sales harian.
Regression suite: `/app/backend/tests/` — test_iteration_21 (25), test_p2p_full_cycle (E2E PR→PO→GR→AP→bayar→3-way matched), test_rbac_multiuser (role/portal separation), test_p2p_create_po (13). Semua pass.
**P2P Procurement** full cycle end-to-end OK (3 bug diperbaiki: counter bentrok, propagasi qty GR→PO untuk PO turunan PR via po_item_id, basis pajak 3-way match). Data terhubung ter-seed; dashboard PR/3-Way Match/AP Aging terisi.
**Multi-user RBAC**: 5 role user (hr/accounting/supervisor_produksi/admin_gudang/admin_maklon), portal terpisah; deep-link guard aktif. Lihat test_credentials.md.
**P2 — Approval Badge (TopBar)** [NEW — iteration_23]: Badge clipboard di TopBar menampilkan jumlah item yang perlu tindakan (PR submitted + AP sent/partial_paid + HR pending) berdasarkan peran. Endpoint `GET /api/approval-inbox/badge`. Klik dropdown + navigasi ke modul relevan. Semua role (admin/finance/hr/gudang) menampilkan kategori sesuai aksesnya.
**P3 — Channel GL Mapping UI** [NEW — iteration_23]: Modul 'Channel → Akun GL' di Finance portal (Piutang AR). Menampilkan 13 channel (Shopee 4, TikTok 6, Tokopedia 1, Maklon 2) dengan kode + nama akun Dr/Cr. Filter per platform, edit inline, seed default button. Endpoint CRUD `/api/rahaza/channel-gl-mapping`. Nama akun diambil dari COA `/api/rahaza/coa/accounts`.
**P1 — AI Modules (Cash Flow Prediction + HR Attrition)** [NEW — iteration_24]: EMERGENT_LLM_KEY ditambahkan ke .env. `dewi_cashflow_ai.py` difix (`UserMessage(text=)` + model `gpt-5.1`). HR Attrition batch dikurangi menjadi 10 employees untuk mencegah proxy timeout. SSE auth LiveHost difix (`payload['host_id']` bukan `['sub']`). Semua AI modules berjalan via `gpt-5.1`.
**LiveHost Portal (/livehost)** [NEW — iteration_24]: 4 hosts (ayu/dian/sinta/rani @dewiaditya.id) sekarang punya `password_hash` + `status:active`. Login JWT difix (`_create_livehost_token` signature). Shift field names dinormalisasi (`shift_name→shift_type`, `scheduled_start→shift_start_time`). Notifikasi difix (KeyError: shift_type). Password: `Host@123`.
See CHANGELOG.md for dated changes and ROADMAP.md for backlog.

## Key credentials
See `/app/memory/test_credentials.md` (admin@garment.com / Admin@123).


## Session log — Lanjutan repo `akakducudhsn/DA` (2026-09-02): Pencairan Marketplace VERIFIED
- Repo di-clone ke /app; `.env` backend ditambah `JWT_SECRET` (wajib — `auth.py` menolak start tanpa ini).
- Modul `fin-marketplace-settlement` (`components/erp/finance/FinanceSettlementModule.jsx`, nav
  Finance > KAS, BANK & BIAYA > Pencairan Marketplace) diverifikasi end-to-end (iteration_98: 21/21
  backend + seluruh alur UI lulus): catat → selisih tampil live → jurnal ditolak bila belum seimbang →
  koreksi → jurnal draf memakai COA milik toko (`coa_cash_code`/`coa_revenue_code`) → posting → rekonsiliasi.
- Data uji: toko `DA Official Shopee` (SHP-DA, 1-131 / 4-111), settlement `STL-TEST-001` → `JE-20260815-0001` posted.
- Catatan: PUT `/api/marketing/settlements/{id}` butuh body lengkap (`SettlementIn`), bukan partial — UI sudah sesuai.
- **Penyimpanan unggahan dipindah ke Emergent Object Storage** (`backend/object_storage.py`, prefix `da-erp/`,
  butuh `EMERGENT_LLM_KEY` di `.env`): foto katalog, foto portal klien, dokumen cuti, berkas sesi impor
  marketing. URL publik tetap `/api/uploads/<path>` (route baru di `server.py`, fallback ke berkas lama di
  `/app/uploads`). Staging unggah backup/restore pindah ke direktori temp sistem. Diverifikasi: upload dokumen
  cuti → tersimpan → dilayani kembali 200 image/jpeg.
- Backlog berikutnya: tautan mutasi bank (fin-bank-recon) → pencairan, filter periode/bulan di daftar pencairan.

### 2026-09-02 (lanjutan) — Impor laporan pencairan + Ringkasan per toko
- `POST /api/marketing/settlements/import/preview` (multipart, finance-only): baca CSV/XLSX laporan
  Penghasilan Shopee / Settlement TikTok → `values` per field F9 + `mapping` (kolom sumber) +
  `unmapped_numeric_columns` + tanggal/periode/settlement_id + `platform_guess`. **Tidak menyimpan
  apa pun** — hanya mengisi form; staf memeriksa lalu Simpan (patuh BD-2: pemetaan terlihat, bukan ditebak
  diam-diam). Parser: `backend/core/settlement_import.py` (kata kunci per field, prioritas afiliasi > komisi,
  potongan dibaca sebagai nilai absolut; `adjustments` boleh minus). Contoh berkas:
  `samples/settlement_shopee_contoh.csv`, `samples/settlement_tiktok_contoh.xlsx`.
- `GET /api/marketing/settlements/by-account?month=YYYY-MM`: per toko — jumlah, bruto, cair, % potongan
  total / komisi / iklan / refund, belum seimbang; `months` tersedia; default bulan terakhir yang ada data.
- UI (`FinanceSettlementModule`): tombol **Impor laporan** (`fin-settlement-import`), panel hasil baca
  (`SettlementImportPanel.jsx`), kartu **Potongan per toko** dengan navigasi bulan (`SettlementByStoreCards.jsx`).
  Toko dipilih ULANG tiap impor dari `platform_guess` (bug iterasi 99: impor kedua mewarisi toko impor pertama);
  Simpan ditolak bila platform laporan ≠ platform toko yang dipilih.
- PENTING: frontend di env ini dilayani sebagai bundel statis (`static_server.js`) — setelah ubah `frontend/src`
  WAJIB `bash /app/scripts/rebuild_frontend.sh` (lihat `memory/PREVIEW_STABLE_MODE.md`).

### 2026-09-02 (lanjutan 2) — Ingat pemetaan kolom · Filter periode · IA Keuangan v3
- **Ingat pemetaan** (`marketing_settlement_import_maps`, kunci `(account_id, fingerprint)`; fingerprint = sha1
  seluruh header ternormalisasi): `POST/GET /api/marketing/settlements/import/mapping`, `DELETE .../mapping/{id}`.
  `import/preview` menerima form `account_id` → bila ada peta tersimpan, `mapping_source: saved`; respons juga
  memuat `column_totals` + `numeric_columns` + `headers` supaya editor di layar menghitung ulang dengan rumus yang
  sama (`compute_values` ⇄ `computeValues`). UI: tabel kolom → field (select), badge "pemetaan tersimpan ✓" /
  "tebakan otomatis — periksa"; pemetaan disimpan otomatis saat pencairan hasil impor DISIMPAN.
- **Filter periode** daftar pencairan: bulan (YYYY-MM) ATAU rentang tanggal (memakai `date_from/date_to` yang
  sudah ada); kartu per toko mengikuti bulan yang dipilih.
- **IA Keuangan v3** (`portalNav.js`, disetujui pemilik): RINGKASAN & LAPORAN · PENJUALAN & PENERIMAAN (Pencairan
  Marketplace, Aging Piutang, Peta Akun Channel) · KAS & BANK (+Prediksi Kas) · PENGELUARAN & KARYAWAN (Pengeluaran
  & Klaim, Kasbon & Pinjaman, Penyelesaian Perjalanan Dinas) · AKUNTANSI (Jurnal, Penyesuaian Akhir Periode,
  Persetujuan Perubahan Invoice, Master Akuntansi) · ANGGARAN, BIAYA & ASET. `FinanceDashboard` akses cepat
  diselaraskan ke 6 grup yang sama. Guard INV-NAV-01 hijau. Diuji iteration_100 (8/8 backend + UI lulus).

### 2026-09-02 (lanjutan 3) — Tautan Mutasi Bank ↔ Pencairan Marketplace
- `routes/dewi_bank_reconciliation.py`: `GET /api/finance/bank-recon/sessions/{sid}/transactions/{txn}/settlement-candidates`
  (urut: nominal sama → tanggal terdekat; pencairan yang sudah tertaut ke mutasi lain disembunyikan) dan
  `POST .../link-settlement {txn_id, settlement_doc_id}` — hanya baris **debit** (uang masuk), nominal harus sama
  (toleransi Rp1; selisih ⇒ 400 "koreksi Nominal dicairkan dulu"), 409 bila salah satu sudah tertaut. Menulis
  `bank_recon_txns.match_type='settlement'` + `marketing_settlements.bank_txn_id/bank_session_id/bank_txn_date`.
  `unmatch` melepas dua arah.
- `marketing_settlements.py`: PUT menolak perubahan `net_payout` bila tertaut bank; DELETE menolak bila tertaut;
  summary daftar memuat `bank_linked_count`/`bank_unlinked_count`.
- UI: tombol hijau (Banknote) per baris mutasi di Rekonsiliasi Bank → `SettlementLinkPicker.jsx`; badge
  "pencairan marketplace" pada baris matched; kolom Dicairkan di Pencairan Marketplace menampilkan
  "mutasi <tanggal>" / "belum tertaut bank"; tombol hapus hilang bila tertaut. Diuji iteration_101 (17/17 + UI).
- Data uji: sesi rekon 2026-08 BCA 1-131 (a6f8da0f…) dengan 3 mutasi; T1 tertaut ke STL-TEST-001.

### 2026-09-03 — Audit Portal Produksi iterasi 103: dispatch PO INTERNAL ke buyer + rekonsiliasi angka
- **Blocker iter-102 tertutup**: PO `business_type='internal'` kini bisa dikirim ke buyer. `core/dispatch_capacity.py`
  menambah sumber `internal_produced` (Σ `production_job_items.produced_qty` untuk PO internal; `source='internal'`) →
  `shippable = lolos QC + permak + hasil produksi internal − dikirim`. `POST /api/buyer-shipments` melewati kewajiban
  `source_receipt_ids` bila SEMUA PO di surat jalan internal (`internal_dispatch`); pagar C-1 (qty ≤ produced) & stok FG
  gudang tetap berlaku. PO maklon tidak berubah (tanpa receipt → 400).
- `buyer_shipment_items.job_item_id` kini diisi otomatis dari `production_job_items` (lookup `po_item_id`, pilih yang
  produced terbesar) supaya agregasi "dikirim/diterima" per job di `/api/production-tracking` & Pusat Kendali terisi.
  Backfill dokumen lama: `scripts/backfill_buyer_shipment_job_item.py`.
- `compute_po_fulfillment` PO internal: `basis='produced'`, `total_produced`, `total_fulfilled=max(received, produced)`,
  `qty_short = ordered − fulfilled`. close-short mengembalikan `qty_produced/qty_fulfilled/basis`.
  `quantity-summary` PO internal: `received_qty/available_qty` dari `production_job_items.available_qty`.
- Pusat Kendali: `all_active_wos` + tab **Semua WO** + KPI **Tanpa Deadline** (Active WOs = on_track+at_risk+overdue+unknown).
- `stage-summary`: tahap dikenali dari `process_type` lalu nama (`STAGE_KEYWORDS`), bukan posisi urutan; respons memuat
  `by_process[]`; event pada proses Rework/Revisi TIDAK dihitung sewing_output.
- `seed-sample` idempoten memberi pesan eksplisit "PO Internal demo sudah ada". Production Jobs: kartu status berlabel per SKU.
- UI Serah Terima FG: PO internal → panel `internal-dispatch-info` (tanpa pemilih CMT Receipt), kolom "Diproduksi",
  badge "BELUM PRODUKSI"; tab Kekurangan Kirim kolom "Siap Kirim" berlabel sumber (produksi/QC). `data-testid`
  pemilih PO: `buyer-shipment-po-select`.
- Keputusan produk: daftar Kekurangan Kirim hanya memuat item yang sudah punya barang (produced/diterima > 0) atau sudah
  pernah dikirim — PO internal yang belum berproduksi tidak dimasukkan.
- `NotificationBell` → `/api/notifications/categorized` diverifikasi 200 (temuan skrip kontrak = false positive).
- Diuji iteration_103: backend 13/13 + iter102 12/12 (termasuk test_11 buyer shipment yang dulu gagal), UI F1–F4 + regresi 8 modul.

### 2026-09-03 (lanjutan) — AUDIT PORTAL MAKLON iterasi 104 (read-only, atas permintaan pemilik: lapor dulu)
- Environment dari repo `pandeyoga/DA030926`: `.env` backend +JWT_SECRET/EMERGENT_LLM_KEY, backup mongodump
  di repo ternyata kosong → data demo dibuat via `tests/seed_demo_produksi_maklon.py` (idempoten, engine asli).
- 15 temuan (M-01..M-15) + usulan perbaikan: `memory/AUDIT_PORTAL_MAKLON_2026-09-03.md`. Ringkas: P0 RBAC
  bocor lintas klien di `/api/dewi/maklon/*` & klien bisa tulis CMT receipt; P1 mirror finance tidak sinkron saat
  close, dua sistem invoice bertabrakan (nomor kembar, tautan AR tertimpa), AP vendor = harga klien (margin 0),
  kapasitas kirim menghitung receipt on_qc; P2 Detail PO 360 baca koleksi legacy (Dikirim 0), 4 label status
  untuk satu PO, Dashboard revenue = nilai PO; P3 endpoint legacy `dewi_maklon_pos` masih hidup, suite uji basi.
- Testing agent iteration_104: 24 menu Portal Maklon render tanpa crash/console error; RBAC probe mengonfirmasi bocor.
- BELUM ADA PERBAIKAN KODE — menunggu persetujuan pemilik atas daftar temuan.

## Session log — Fase 2 FIX: State machine enforcement + verifikasi RBAC live (Feb 2026)
Temuan verifikasi independen user: PO Draft bisa langsung Closed via /status (200).
- **Keputusan: BUG-FIX (kategori C-1..M-3), bukan port** — referensi sommerville-adopt sendiri hanya
  memvalidasi keanggotaan PO_STATUSES tanpa cek urutan (transition_po_status & close_po unguarded).
  Matrix mengikuti PRODUKSI_TOBE_FLOW_FINAL: Draft→Confirmed→Distributed→In Production→Production
  Complete→(Variance Review ↔ Return Review, opsional/skippable)→Ready to Close→Closed.
  `PO_STATUS_TRANSITIONS` + `PO_CLOSABLE_STATUSES` di production_pos.py; transisi non-adjacent → 400.
  close_po hanya sah dari status pasca-produksi (Production Complete/Variance Review/Return Review/
  Ready to Close); Closed→Closed ditolak.
- **Audit endpoint status lain (hasil per endpoint)**:
  · PUT /vendor-shipments/{id} — SEBELUMNYA bebas $set → kini hanya Sent→Received (nilai lain/mundur 400).
  · PUT /buyer-shipments/{id} — ship_status manual DITOLAK 400 (dikelola otomatis engine dispatch).
  · PUT /material-requests/{id} — keputusan hanya dari Pending (Approved/Rejected); ubah keputusan → 400;
    generic update tidak lagi bisa menyentuh field status (dicegah duplikasi/flip tanpa efek samping).
  · PUT /production-returns/{id} — status forward-only sesuai STATUS_OPTIONS referensi:
    Repair Needed→In Repair→Completed→Shipped Back; mundur/nilai asing → 400.
  · PUT /production-variances/{id} — matrix Reported→(Acknowledged|Resolved)→Resolved; mundur → 400.
  · production_jobs — TIDAK ada endpoint status manual (auto In Progress→Completed via progress) → aman.
  · PUT /buyer-shipment-items/{id}/received — sudah ter-guard qty (I-2/received-based) → aman.
  · Inspeksi dobel — sudah 400 (verified sebelumnya) → aman.
- **RBAC live verified**: cmtvendor@dewiaditya.id (cmt_vendor) → GET vendor-shipments/jobs 200 scoped
  vendor sendiri; POST/DELETE/status production-pos → 403. Lockout login_attempts direset.
  maklon@dewiaditya.id = admin_maklon (BUKAN cmt_vendor) — test_credentials.md diperjelas.
- **Testing**: POC 78/78 PASS (71 + 7 kasus state machine baru), edges 45/45, maklon inti 17/17.

## Session log — Fase 2: Maklon Backend Port identik SOMMERVILLE (Feb 2026)
GREEN LIGHT diberikan; keputusan diratifikasi: F-1 port dari sommerville-adopt (canonical),
F-2 Option A production_pos+business_type='maklon' (satu engine), F-3 semua default AD/VP.
- **Engine SOMMERVILLE diport** (backend-only): `routes/production_pos.py`, `vendor_shipment.py`,
  `production_execution.py`, `exceptions.py`, `buyer_shipment.py` + `core/` + `cascade_delete.py` —
  identik reference, dengan: business_type propagation (PO→shipment→job→dispatch→request→defect→retur→variance,
  fix D4/GDG-1), RBAC-1=B remap (`routes/production_rbac.py`: admin→admin/admin_maklon; vendor→vendor/cmt_vendor
  via vendor_id|cmt_vendor_id; klien_maklon di-deny dari semua endpoint engine), master resolve DA
  (garments|vendor_partners, buyers|dewi_maklon_clients), invariants I-1/I-2/I-3/I-5 + fixes C-1..M-3 +
  received-based caps (phases 17-19) terbawa. Serial endpoints tetap di operations_serials.py (tidak diduplikasi).
- **Bridge finance (FIN-2)**: `routes/production_maklon_bridge.py` — mirror dewi_maklon_pos (id=po_id) +
  Draft AR rahaza_ar_invoices otomatis saat PO maklon Confirmed (hook di create/transisi/quick-complete);
  post-ar dewi_maklon_finance → JE GL terbukti jalan. Cascade delete membersihkan mirror+draft AR.
- **Klien tracking**: `routes/maklon_client_tracking.py` — GET /api/maklon-client/pos + /pos/{id}/tracking
  (progress per item + dispatch bertahap), scoped buyer_id.
- **Seeder AD-4**: POST /api/seed/maklon-full (fresh re-seed, idempoten).
- **Dipertahankan dari DA**: variance post-gl/retry-posting (merged ke exceptions.py),
  stage-qty/stage-summary (`routes/production_stage_tracking.py`, dipakai RahazaOrdersModule aktif).
- **Router lama diarsip**: routes/_archive/pre_sommerville/ (production_po, production(+jobs/progress/
  returns/variances/work_orders), backup).
- **Testing**: POC `tests/flow_maklon_sommerville_test.py` 71/71 PASS (happy path penuh, I-1/I-3/C-1 guards,
  variance OVER/UNDER, RBAC, E11 REQ-RPL→child shipment -R1→child job, finance JE). Regression 10 flow suites
  PASS (maklon inti/cmt/client-portal, produksi inti/material-wo/qc-rework*, keuangan AR/jurnal, gudang outbound,
  aksesoris). *qc-rework test diperbaiki: assertion global → delta (endpoint flow-summary tanpa window tanggal,
  pre-existing, bukan regresi port).
- **NEXT**: FE Maklon (batch build sesuai PREVIEW_STABLE_MODE) → Fase 3 Produksi internal + adapters E10 →
  Fase 4 hapus rahaza multi-stage (D1-D5) → Fase 5 bridges + full test. Lalu: analisis flow bisnis Portal
  Marketing (fase analisis terpisah, sudah diminta user).

## Session log — Discovery & Code Review (Feb 2026, fresh environment)
- Environment re-setup from scratch: /app hanya berisi template → cloned `sadkasdlsha/da` ke /app;
  reference repo `msajsjfaskf/sommerville-adopt` di-clone ke `/app/refs/sommerville-adopt` (reference only, TIDAK di-serve/build).
- Env recreated (gitignored): backend/.env (JWT_SECRET generated, EMERGENT_LLM_KEY="" — AI modules 503, deferred),
  frontend/.env (REACT_APP_BACKEND_URL preserved + GENERATE_SOURCEMAP=false + DISABLE_ESLINT_PLUGIN=true).
- PREVIEW_STABLE_MODE dipatuhi: FE = static bundle (rebuild_frontend.sh, build OK 56s), NO dev server.
- Verified: backend+mongo+static FE RUNNING; login admin + 5 role accounts 200; `GET /api/openapi.json` 200;
  seed `production-full` + `rahaza/seed-demo` sukses; login page renders (screenshot).
- `memory/test_credentials.md` hilang (gitignored) → dibuat ulang.
- Discovery report A–F delivered (semua dokumen acuan Sommerville adoption + E1–E11 dibaca; gap analysis disusun).
- NEXT: eksekusi adopsi menunggu lampu hijau user — Fase 2 (Maklon identik SOMMERVILLE) → Fase 3 (Produksi internal + adapters E10)
  → Fase 4 (hapus rahaza multi-stage D1–D5) → Fase 5 (bridges + full test). Backend-first, batch FE build, UI testing di akhir (strategi 2GB).

## Session log — FASE 3: Produksi Internal + adapters E10 (Feb 2026) — SELESAI, ALL PASS
- **Engine sama, business_type="internal"**: PO internal via `production_pos.py` + adapter
  `routes/production_internal_adapter.py` (D3 model_id FK wajib → rahaza_models; ACC-1=A po_accessories
  auto-explode dari BOM; GDG-2=A MI draft-from-job → gudang konfirmasi → stok SSOT rahaza_material_stock;
  HR-1 progress optional operator_id+process_id → mirror rahaza_wip_events shape payroll (employee_id,
  event_type=complete, qty_done, rate_per_pcs, event_date) → payroll per-pcs existing TETAP jalan;
  AD-2 overhead rate×produced; AD-3 job Completed → HPP snapshot per job (anchor job_id) + JE WIP→FG;
  FIN-1/E10 COGS per dispatch buyer shipment; MKT-1=B from-order→PO internal; MKT-2 catalog model_id FK).
- **Fix posting hooks (rahaza_posting.py)**: `post_wip_to_fg_on_job_complete` & `post_cogs_on_buyer_dispatch`
  disesuaikan ke pola engine existing — mapping keys `debit_fg_inventory`/`credit_wip`
  (profile wip_to_fg_on_wo_complete) dan `debit_cogs_material/labor/overhead`+`credit_fg_inventory`
  (profile cogs_shipment, split per komponen HPP snapshot job, qty/qty_completed), lines pakai
  `account_code`, signature positional `_create_posted_je(db, je_date, memo, source_module, source_ref,
  lines, user)`. TIDAK ada engine/profile posting baru.
- **KEPUTUSAN (data fix, didokumentasikan sesuai arahan user)**: profile existing
  `cogs_shipment.debit_cogs_overhead` di DB menunjuk `5-3000` "HPP Overhead Pabrik" yang di CoA aktif
  adalah HEADER (is_group, punya anak 5-3100..5-3400) → non-postable. Diubah via update data ke `5-250`
  "Biaya Overhead Pabrik (BOP)" (postable) — nilai IDENTIK dengan `DA_POSTING_PROFILES` di kode
  (rahaza_posting_profiles.py L513). Catatan laten: `DEFAULT_PROFILES` seed masih berisi 5-3000,
  hanya berlaku jika DB kosong di-seed ulang dari template default.
- **Fix script POC (bukan produk)**: `tests/flow_internal_sommerville_test.py` bukti payroll dibaca via
  `GET /api/rahaza/payroll-runs/{id}` (response POST create = header run saja, by design existing);
  cleanup payslips per run_id ditambahkan.
- **JE evidence (POC)**: WIP→FG job internal → Dr 1-1404 FG / Cr 1-1403 WIP, nilai = Σ JE material issue
  (basis MI, fallback HPP snapshot), source_module=production_job, source_ref=wip_fg_job:{job_id}, idempoten.
  COGS dispatch → Dr 5-1000 (material) + Dr 5-2000 (labor) + Dr 5-250 (overhead) / Cr 1-1404 FG,
  source_module=buyer_dispatch, source_ref=cogs_job:{shipment_id}:seq{n}, idempoten per dispatch seq.
- **Testing**: POC `tests/flow_internal_sommerville_test.py` **41/41 PASS** (D3 FK, ACC-1, allowed_next
  Draft=['Confirmed'], GDG-2 gate+stok, HR-1 mirror+payroll pcs 10×500=5.000, AD-3 WIP→FG, COGS 2 dispatch
  idempoten per seq, MKT-1/MKT-2, state machine internal Draft→Closed→400). Regression penuh PASS:
  maklon sommerville 78/78, maklon edges 45/45, maklon_inti 17/17, cmt_vendor ALL, client_portal 29 ALL,
  alur_produksi_inti 18/18, qc_rework ALL, keuangan jurnal/AR/AP ALL, kas_bank 30 ALL, sdm_payroll ALL.
  (Catatan test env: login rate-limit 10 req/60s per IP → antar-suite perlu jeda.)
- **FE Fase 3 BELUM dibuild** (sesuai scope backend-only). NEXT: FE Produksi Internal (batch build sesuai
  PREVIEW_STABLE_MODE) → Fase 4 hapus rahaza multi-stage (D1-D5) → Fase 5 bridges + full test.

## Session log — FASE 4: Hapus engine rahaza multi-stage / D1-D5 (Feb 2026) — backend only
- **Router diarsip → `routes/_archive/rahaza_multistage/` (23 file)**: rahaza_work_orders,
  rahaza_bundles(+mgmt/docs/rework/backup), rahaza_execution, rahaza_andon, rahaza_aps(+scheduler),
  rahaza_qc_v2 (qc_events+defect_codes, QC-2=BUANG), rahaza_oee, rahaza_line_monitoring
  (+services/line_monitoring_service.py), rahaza_tv, rahaza_rework, rahaza_lkp, rahaza_wizard,
  rahaza_backlog, rahaza_material_reservation (per-WO), dewi_cutting, qc.py & finishing.py
  (engine template lama, dead D5, 0 pemanggil FE). Total 139 endpoint dihapus dari openapi.
- **server.py**: import+include router arsip dicabut; create_index koleksi DELETE dihapus
  (lines, line_assignments, WO, bundles, andon, qc_events, defect_codes, reservations, lkp, cutting);
  wip_events & material_issues re-index `job_id`; **fix laten index**: rahaza_hpp_snapshots unique
  work_order_id (non-partial, bentrok null utk snapshot per-job) → partial unique job_id + partial
  unique work_order_id; /api/metrics hitung production_pos+production_jobs (bukan WO).
- **Bedah file KEEP**: dewi_maklon._sync_wo_status → no-op stub; dashboard_routes avg_oee=None
  (OEE engine gone); rahaza_alerts hapus Andon SLA check; rahaza_inventory_issues hapus endpoint
  `POST /material-issues/draft-from-wo` (diganti draft-from-job Fase 3); rahaza_hpp hapus
  `GET/POST /hpp/work-order/{wo_id}(/snapshot)` (HPP per job di production_internal_adapter).
- **Hardening**: (a) post-gl variance body kosong → 404/400, BUKAN 500 (terverifikasi curl);
  (b) seed DEFAULT_PROFILES cogs_shipment.debit_cogs_overhead 5-3000 (header) → 5-250 (BOP).
- **Data drop (SETELAH mongodump ke /app/backups/fase4_20260713/, reversible, README ada)**:
  rahaza_work_orders(25), rahaza_bundles(45), rahaza_qc_events(27), rahaza_defect_codes(8),
  rahaza_andon_events(0)+settings(1), rahaza_lines(12), rahaza_line_assignments(100),
  rahaza_material_reservations(0), rahaza_lkp(0), dewi_cutting_requests(0)+batches(0).
  Dibiarkan (KEEP/REPURPOSE): material_stock/materials/issues, wip_events, hpp_snapshots,
  costing_settings, processes, machines, shifts, payroll/attendance, wms_*, finance, variances.
- **Referensi pasif yg dibiarkan (baca koleksi dropped → hasil kosong, tidak error)**: dashboards/
  reports/analytics_ai/ai_aggregates, production_stage_tracking, universal_scan (branch WO/bundle),
  production_control_tower, shift_handover, rahaza_shipments/hpp maklon-order lama, seeder lama
  (production_seed_full/demo_seed masih tulis koleksi lama JIKA dipanggil — akan diganti fresh
  re-seed final Fase 5).
- **Test lama diarsip → tests/_archive/**: flow_alur_produksi_inti, flow_produksi_qc_rework,
  flow_produksi_cutting, flow_produksi_aps. GAP COVERAGE: QC/defect kini via material_defect_reports
  (tercakup suite maklon: inspeksi, defect, retur, rework); cutting/aps/andon TIDAK punya padanan
  di engine baru (by design E10 — multi-stage dibuang). flow_maklon_edges_test diupdate: cek
  flow-summary (engine lama) → cek /api/production-jobs.
- **FE terdampak (29 komponen, INPUT FASE 5 — belum disentuh)**: lihat daftar di laporan Fase 4
  (RahazaWorkOrdersModule, RahazaBundlesModule, BundleReworkBoard/ScannerModal/DetailPage,
  ProcessExecutionModule, QuickInputPanel, SimpleDailyInputModule, OperatorView, AndonPanel/Board,
  APSGantt/AutoScheduleDialog, RahazaFPY/Pareto/DefectCodes, OeeDashboard/RahazaOEE,
  LineMonitoringModule, ShopFloorTV, ReworkAnalytics, LKPDialog, ProductionWizardModule,
  RahazaBacklogModule, RahazaMaterialReservationModule, CuttingProcessModule, DOManagementModule,
  RahazaHPPModule (hpp/work-order), RahazaMaterialIssueModule (draft-from-wo),
  RahazaBulkMIModule, RahazaLineAssignmentsModule, bundleTickets.js).
- **Follow-up temuan testing agent (iteration_95, minor)**: penulis aktif terakhir koleksi WO =
  dewi_maklon_pos.py (confirm insert WO legacy + cancel update WO) → dimatikan; wo_number tetap
  digenerate sebagai nomor tracking item (kompat response `work_orders_created` & FE). Test
  flow_maklon_inti_test TC-06 diupdate (verifikasi wo_number tracking + WO collection TIDAK dibuat)
  → 17/17 PASS; koleksi rahaza_work_orders terverifikasi GONE pasca run. Penulis tersisa hanya
  SEEDER lama (rahaza_demo_seed/rahaza_admin_seed/production_seed_full — manual, diganti fresh
  re-seed final Fase 5) + reads pasif (tidak menciptakan koleksi).
- **Regression Fase 4 (16 suite, ALL PASS)**: internal 41, sommerville 78, edges 45 (1 check
  diupdate ke engine baru), maklon_inti 17, cmt_vendor 17, client_portal 29, payroll ALL
  (26 slips + JE finalize/payment; fix bug test pre-existing: parsing key `items` GET employees),
  gudang inbound 16 / outbound 9 / opname 14, keuangan jurnal 11 / AR 7 / AP 7 / kas-bank 30,
  material_wo 11, aksesoris 21. Verifikasi independen testing agent (iteration_95): 100% —
  openapi 17/17 pola arsip bersih + 9/9 KEEP hadir + 4/4 curl + 164/164 flow tests.

## FASE 5 (FINAL) — SELESAI (2026-07-13)
- **Backend**: bridges selesai + fresh re-seed FINAL (AD-4) via POST /api/seed/maklon-full
  (idempoten): maklon PO-MK-DEMO-1/2 + internal PO-INT-DEMO-1/2/3 + master DA-TS01/BOM/stok/
  operator borongan. test_credentials.md diupdate. Seeder lama diarsip (410).
- **Frontend (1 batch, 1x rebuild via scripts/rebuild_frontend.sh)**: UI Portal Produksi & Maklon
  di shell DA (moduleRegistry), tombol aksi status dinamis dari allowed_next
  (ProductionPOModule.jsx L824-841, data-testid po-action-{status}), VendorCMTEnginePortal.jsx
  (/vendor-cmt, login scoped cmt_vendor → VendorPortalApp 11 menu), ClientMaklonPortal.jsx
  (/klien-maklon, tracking read-only klien_maklon), 29 komponen mati Fase 4 + 81 redirect mati
  moduleRegistry dibersihkan.
- **Regression pasca re-seed**: internal 41/41 + maklon 78/78 PASS (flow_internal_sommerville_test,
  flow_maklon_sommerville_test).
- **UI E2E penuh (iteration_96)**: 5 skenario PASS — (1) admin create PO internal + allowed_next
  live Draft→Confirmed→Distributed; (2) portal maklon list/detail; (3) vendor CMT scoped
  (negative login reject + 4 modul render); (4) klien read-only (0 tombol mutasi); (5) sweep
  20 menu (13 produksi + 7 maklon) 0 blank/0 fatal console error/0 module-not-found.
- **Fix minor pasca-E2E (backend-only, tanpa rebuild)**: /api/vendor/dashboard 403 utk cmt_vendor —
  guard legacy role 'vendor' → is_vendor()/vendor_identity() dari production_rbac.py
  (dashboard_routes.py L392). Verified: dashboard vendor tampil metrics, 0 console error.
- **By-design (backlog P2)**: detail modal PO maklon tidak embed info job (JOB-*) — job dikelola
  via modul 'Production Jobs' terpisah di sidebar. Opsional: panel job di detail PO.
- **Data demo pristine**: 5 PO demo persis; artefak uji PO-MK-TEST-VERIFY-1 dihapus (cascade).

## FIX: Akses Absen Geo dari Portal Saya (2026-07-13)
- Laporan user: "tidak ada tombol/menu absen di portal saya" → KASUS A (gap discoverability,
  bukan fitur hilang). Fitur absen geo LENGKAP dan hidup di route /absen (AbsenPage.jsx:
  selfie+geolocation+AI, WebAuthn, login mandiri; BE rahaza_attendance.py clock-in/out +
  geofence Haversine vs rahaza_office_locations, suite selfie/webauthn/zkteco terdaftar).
  Jalur lama self-service (OperatorView) diarsip Fase 5 tanpa pengganti akses di portal.
- Fix minimal: tombol "Absen Sekarang" (data-testid=absen-now-btn) di kartu profil
  SelfServicePortal.jsx (Portal Saya / self-dashboard) → window.location /absen.
- Catatan insiden: frontend/build/ ditemukan HILANG (tersapu proses eksternal pasca
  git squash/Save-to-GitHub) → dipulihkan bersamaan 1x rebuild fix ini.
- Verified E2E: /absen login hr@ → status hari ini tampil; Portal Saya → tombol muncul →
  klik → /absen. 0 fatal console error.

## Session log — FASE 6.6 + FASE 8 (2026-07-25, environment dari repo `hanababama/da`)

**Konteks**: user meminta melanjutkan development dari repo GitHub `hanababama/da` dengan verifikasi + menjalankan
guideline. Environment dipulihkan (clone → rsync → `bootstrap.sh` → build static bundle), baseline diverifikasi
(`verify_acc123.py` 62 PASS), lalu dua fase dikerjakan sesuai pilihan user.

### FASE 6.6-A — Rekonsiliasi baris stok skema lama A/B/C
- **Kenapa**: `rahaza_material_stock` historis punya 3 bentuk baris — A (kanonik `location_id`+`qty`),
  B (lokasi BERSARANG + `total_qty`, domain aksesoris lama), C (tanpa lokasi + `available_quantity`, alur FG/CMT).
  Writer sudah satu pintu sejak FASE 2, tapi baris warisan membuat layar per-lokasi kehilangan stok, memunculkan
  baris kembar, dan `available_quantity` basi (risiko over-allocation).
- **Apa**: `core/stock_reconcile.py` (7 detektor + scan/reconcile/rollback/logs, jurnal
  `wh_stock_schema_reconcile_log`), `routes/wms_stock_schema.py` (`/api/wms/stock-schema/*`),
  `migrations/migrate_reconcile_stock_schema.py`, FE `StockSchemaHealthModule.jsx`
  (modul `wh-stock-schema` + tab "Kesehatan Skema" di hub `wms-stock-hub`).
- **Jaminan**: total on-hand TIDAK berubah; `negative_qty` & `orphan_material` hanya dilaporkan (butuh
  Opname/Penyesuaian resmi); setiap eksekusi bisa di-rollback presisi.
- **Bug nyata**: UNIQUE index (material_id, location_id) ⇒ urutan operasi harus hapus-dulu-lalu-tulis.

### FASE 6.6-B — Rename internal `yarn_*` → field netral (alias kompatibilitas)
- SSOT `core/material_fields.py` + `frontend/src/lib/materialFields.js`. Kanonik baru: `composition`,
  `material_kg_per_pcs`, `default_material_cost_per_kg`, `total_material_kg_per_pcs`, `total_material_kg`,
  `bulk_line_count`. **Alias legacy tetap ditulis** ⇒ dok DB lama, laporan, dan integrasi tidak pecah.
- 13 file backend + 9 file frontend dialihkan; migrasi backfill `migrate_rename_yarn_fields.py`
  (`--discover`/`--execute`/`--rollback`). Label UI Indonesia: "Jenis/Komposisi", "Bahan utama/pcs (kg)",
  "Total bahan (kg)", "Default Bahan/kg", "N bahan" (bukan "N benang").

### FASE 8 — Valuasi HPP Aksesoris
- `core/accessory_valuation.py`: moving average (WAC) saat penerimaan, koreksi HPP manual, ringkasan valuasi,
  riwayat HPP (`rahaza_material_cost_history`).
- Mutasi aksesoris kini BERNILAI + berjurnal: terima → `inventory_receive`; keluar → `post_accessory_issue`
  (Dr WIP / Cr Persediaan); **scrap (endpoint BARU `POST /api/acc/stock/scrap`)** → `inventory_adjust`
  reason=scrap (Dr Beban Scrap 6-4300 / Cr Persediaan). Posting non-fatal & transparan (`je.posted` + alasan).
- `routes/dewi_accessories_valuation.py` (`/api/acc/valuation*`), KPI dashboard `total_stock_value` +
  `unvalued_items`, FE tab "Valuasi HPP" (+ ledger mutasi bernilai & riwayat HPP), input harga di modal Terima.
- `core/stock_rbac.py` menjadi SSOT role operasi stok (dipakai karantina + scrap aksesoris).

### FASE 8.8 — Panduan drop koleksi legacy
- `memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` (prinsip, 4 grup kandidat + status, prasyarat, checklist) +
  `migrations/drop_legacy_collections_guided.py` (audit → dry-run → arsip → drop → rollback → purge).

### Bukti
`verify_fase66.py` 48/48 · `verify_fase8.py` 48/48 · `verify_acc123.py` 62/62 ·
`verify_phase6_quarantine.py` 48/48 · testing_agent_v3 iteration_169 backend 100% & 0 critical ·
verifikasi UI manual Playwright untuk semua alur tulis (rekonsiliasi, Set HPP, Scrap, Terima bernilai) ·
FE lint 0 error · ruff 0 issue (file baru) · `yarn build` Compiled successfully · DB kembali ke baseline.

### FASE 10 — Otomasi Valuasi Aksesoris + Penutupan Domain Legacy (2026-07-25, lanjutan #3)
**1. Ringkasan alarm harian "belum dinilai".** `GET /api/acc/valuation/unvalued-digest` (pratinjau) +
`POST .../send` + job `daily_unvalued_digest` **07:30 WIB**: SATU notifikasi berisi SELURUH aksesoris
ber-HPP 0 (kode, nama, stok, jumlah mutasi 24 jam) ke role penanggung jawab, idempoten 1×/hari.
Notifikasi **per-item tetap jalan** (anti-spam 1×/24 jam per material) — digest adalah TAMBAHAN, bukan
pengganti (pilihan user).

**2. Rapor valuasi bulanan otomatis via email.** `services/accessory_valuation_mailer.py` +
`utils/email_sender.py` (smtplib bawaan, tanpa dependensi baru). Job `monthly_valuation_report_email`
**tanggal 1 pukul 06:00 WIB**: rapor periode bulan lalu, lampiran **Excel + PDF**, penerima = role
keuangan/accounting + `valuation_report_extra_emails`. Idempoten per periode (kecuali tombol "Kirim
sekarang"). Riwayat di `acc_valuation_report_runs`. **SMTP dikonfigurasi lewat UI** (Pusat Notifikasi →
Konfigurasi Provider: host/port/user/`smtp_security` starttls|ssl|none). Bila SMTP belum diisi, rapor
TETAP dibuat dan ringkasannya dikirim sebagai notifikasi in-app dengan status `skipped_no_smtp` —
tidak pernah gagal senyap. UI: tab **Valuasi HPP** → panel `acc-val-automation`.

**3. Prasyarat drop `accessory_legacy` TUNTAS.** `acc_internal_requests` & `acc_loans` sudah tidak punya
jalur tulis/baca aktif: endpoint `/api/acc/internal-requests/*` dan `/api/acc/loans/*` → **410**;
logika pemotongan stok diangkat ke `core/accessory_issue.py` (`check_availability` + `issue_accessory`)
dan dipakai `POST /api/dewi/accessory-requests/{id}/deliver` (validasi semua baris dulu, idempoten,
"stok tidak cukup" → 400); tab "Peminjaman" dilepas dari UI; pinjaman lama ditutup otomatis via
`migrations/close_legacy_acc_loans.py` (stok dikembalikan, bisa rollback); KPI dashboard `active_loans`
→ `ready_to_deliver`. Grup kini **[SIAP]** di `drop_legacy_collections_guided.py --audit`.

**4. Modal menggantikan dialog native TERAKHIR.** `OpnameActionModal` (submit/cancel/approve/reject)
dengan validasi inline "Alasan wajib diisi…" + modal hapus aksesoris. **Tidak ada lagi
`window.prompt`/`confirm`/`alert` di modul Aksesoris.**

**5. Perbaikan integritas stok (BUG-1, kritis).** `core/accessory_stock.issue_across_locations()`:
pengeluaran aksesoris kini memotong **lintas lokasi** (lokasi kanonik dulu, lalu baris terbesar; baris
warisan lokasi-bersarang lewat `issue_row`). Sebelumnya pembaca mengagregasi semua lokasi tetapi penulis
hanya satu lokasi ⇒ **HTTP 500** untuk item yang stoknya duduk di lokasi lain (data warisan/put-away/seed
demo). Ikut memperbaiki `/acc/stock/issue`, `/scrap`, SSOT `deliver`, dan `approve` opname.

**6. Transparansi opname (BUG-2).** `approve` kini melaporkan `stock_failed` + `stock_failed_items`
(sebelumnya baris gagal di-`continue` diam-diam sehingga sesi tampak "Completed" padahal selisihnya tidak
pernah diterapkan). UI menampilkan baris merah beserta detail penyebabnya.

**Bukti:** 402 PASS / 0 FAIL pada 9 skrip verifikasi · `testing_agent_v3` iteration_173 0 critical/0 minor ·
verifikasi UI manual Playwright untuk seluruh alur tulis · FE lint 0 error · `yarn build` sukses ·
DB kembali ke baseline demo (10 item · Rp 9.667.750 · 8 bernilai / 2 belum dinilai).

---

# ADDENDUM — FASE IA (2026-07-26): Restrukturisasi IA, Portal Cutting, Seed Data Nyata

## Peta Portal (14)
| Portal | id | Catatan |
|---|---|---|
| Manajemen | `management` | **Khusus eksekutif** — 2 section (Ringkasan Eksekutif, Strategi & Approval) |
| **Administrasi Sistem** | `sysadmin` | **BARU** — split dari Manajemen. Akses: `super_admin` + `admin` saja. 2 section: Akses & Audit, Sistem & Data (termasuk pintu **Backup Data**) |
| Produksi | `production` | tidak berubah |
| **Cutting** | `cutting` | **BARU** — roll kain ➜ kain pola (potongan). 3 pintu: Dashboard, Order Cutting, Master Potongan |
| Gudang | `warehouse` | `wh-material-issue` dipindah ke section OUTBOUND |
| Aksesoris | `accessories` | 3 section ➜ **1 section** (7 pintu) |
| Keuangan | `finance` | disusun ulang mengikuti **siklus uang** (6 section, 24 pintu utuh) |
| SDM / HRIS | `hr` | **3 section**: Manajemen Karyawan (8) · Manajemen Organisasi (8) · Analitik & Laporan (8) |
| Maklon | `maklon` | +pintu **Komponen Kurang** (`cmt-component-requests`) yang sebelumnya tak punya menu |
| Marketing | `toko` | tidak berubah |
| RnD | `rnd` | tidak berubah |
| Manajemen Aset | `assets` | **`singleDoor: true`** — sidebar & pill disembunyikan, navigasi via tab modul |
| Kolaborasi | `collaboration` | tidak berubah |
| Portal Saya | `self` | tidak berubah |

## Aturan IA yang WAJIB dipatuhi (dijaga `scripts/guardrails/check_nav_map.py`)
- Navigasi **datar 2 tingkat**: Section → Pintu (guard `NAV-FLAT`).
- Section: **≥2 pintu** (`NAV-SINGLE`) dan **≤8 pintu** (`NAV-MAX`).
- Label pintu: tanpa tanda kurung, ≤3 kata, bukan HURUF BESAR semua (`NAV-LABEL`).
- Satu isi tidak boleh punya dua pintu di portal yang sama (`NAV-DUPTAB`).
- Semua id menu wajib ada di `moduleRegistry.js` (`NAV-GHOST`).
- **BARU `NAV-SOLO`**: portal ber-flag `singleDoor: true` wajib benar-benar 1 section × 1 pintu.
- moduleId lama TIDAK dihapus saat menu dirombak → deep-link (`/#<id>`) tetap hidup lewat
  `moduleRegistry.js` + `App.js LEGACY_MODULE_TO_PORTAL` + heuristik prefix.

## Modul Cutting (`/api/cutting/*`, `backend/routes/cutting.py`)
State: `draft → in_progress → completed` (`cancel` hanya bila belum ada progres).
- Koleksi: `cutting_orders`, `cutting_progress` (indeks dibuat saat startup agar SELALU ter-backup).
- Mutasi stok **hanya** lewat SSOT `core/stock_service.py` (`issue` kain, `add` potongan)
  → `rahaza_material_stock` + `rahaza_stock_ledger` tetap satu kebenaran.
- Output potongan = dokumen `rahaza_materials` baru: `is_cut_panel: true`, `type: fabric`,
  `unit: pcs`, `category: POTONGAN`, `source_material_id`, kode `CUT-<STYLE>-<WARNA>-<SIZE>` (idempoten).
- **Stok disimpan per (material, lokasi)** — order cutting WAJIB memakai gudang yang benar-benar
  memegang stok. `/input-materials` mengembalikan `stock_locations` + `best_location_id`;
  `start` memvalidasi per-lokasi dan mengalihkan order ke gudang berstok bila perlu.
- HPP potongan = (kain terpakai × harga kain) ÷ potongan jadi, ditulis ke `unit_cost` saat complete.
- Bukti alur: `scripts/poc_cutting_flow.py` & `scripts/poc_cutting_flow_v2.py` (keduanya LULUS).

## Data
- Seed demo lama **dihapus total**. Master data nyata dari 7 Excel owner di-seed lewat
  `scripts/seed_da_master_from_excel.py [--wipe] [--no-stock]`.
- Isi: 25 karyawan (+akun login, payroll profile, tunjangan), 6 lokasi kerja, 7 unit organisasi,
  18 posisi, 143 kain, 335 aksesoris, 553 barang jadi, 55 model produk (+spek), 19 style techpack,
  58 vendor CMT, 8 akun marketplace + target.
- **Transaksi sengaja kosong.** Saldo awal stok ditandai `saldo_awal` di ledger.
- Batas ambil dokumen master: `MASTER_FETCH_LIMIT = 20000` (dulu `.to_list(500)` memotong data senyap).

---

# ADDENDUM 2 — Notifikasi Berkategori, RBAC, Light Mode (2026-07-27)

## Light mode = default
`ThemeProvider defaultTheme="light"` + `getSystemTheme()` selalu `'light'`.
**Akar masalah "kartu tanpa background":** di light mode `--card-surface` dulu
`rgba(255,255,255,0.82)` di atas latar terang ⇒ kontras kartu↔latar ~nol.
Sekarang: `--card-surface: #FFFFFF` (solid), `--glass-border: rgba(15,23,42,0.14)`,
`--shadow-card` diperkuat (hairline 1px + soft shadow). Perbaikan di level TOKEN
sehingga berlaku untuk seluruh GlassCard/GlassPanel/tabel di semua portal.

## Notifikasi berkategori (`backend/routes/notification_categories.py`)
- Kategori = **portal sumber** (11: Gudang, Produksi, Cutting, Maklon, Keuangan,
  SDM, Marketing, Aksesoris, Aset, RnD, Sistem). Diturunkan saat baca dari
  `link_module` (prefix) → `type` ⇒ **notifikasi lama tidak perlu migrasi**.
- Bel = ringkas (hitungan per kategori + 3 terbaru) → tombol **Lihat Semua**
  membuka popup **Pusat Notifikasi** (filter kategori, tandai dibaca, lompat modul).
- `notif_category_config`: matriks **kategori × role** (pintu admin `#sys-notif-config`
  di Portal Administrasi Sistem). Default diturunkan dari `PORTAL_ACCESS`
  supaya tidak ada sumber kebenaran RBAC kedua. SUPER_ROLES selalu menerima semua.
- `notif_user_prefs`: user boleh **membisukan** kategori untuk dirinya sendiri,
  tapi tidak bisa membuka kategori yang ditutup admin.
- Endpoint: `/api/notifications/{categories,categorized,category-config,my-category-prefs}`.

## RBAC di-wiring ulang (FE `portalAccess.js` ⇄ BE `routes/shared.py`, identik)
- `rnd_staff` & `marketing_kol` **dicabut** dari portal `management` (kini khusus eksekutif).
- Portal `cutting` & `sysadmin` ditambahkan di kedua sisi; `sysadmin` = SUPER_ROLES saja.
- `admin_gudang` ditambahkan ke `assets` (dia yang memegang alat/aset fisik).
- Terverifikasi: user role `hr` hanya bisa membuka SDM + Portal Saya + Kolaborasi;
  11 portal lain terkunci; endpoint admin menolak dengan 403.

## Standar UI Light Mode — Tabel, Kartu & Tombol (2026-07-27)
Keluhan owner: di light mode tabel "tidak punya background kartu" (baris menyatu
dengan latar), tombol memakai warna mentah, dan teks abu terlalu pudar.

**Keputusan produk:**
- Setiap tabel WAJIB berdiri di atas permukaan kartu solid (`--card-surface`,
  putih di light mode) dengan hairline `--glass-border`, radius `--radius-lg`,
  dan `--shadow-card`.
- Tombol aksi utama WAJIB memakai token `hsl(var(--primary))` +
  `hsl(var(--primary-foreground))` — dilarang memakai `bg-blue-500` dkk.
- Badge/status TETAP memakai warna semantik, tapi versi soft (pastel + teks
  gelap) supaya sinyalnya terbaca.
- Kartu KPI memakai komponen `StatCard` (putih + aksen tipis di kiri), bukan
  blok pastel penuh.
- Dark & Classic mode tidak boleh terpengaruh: semua aturan baru di-scope
  `html.light`.

**Implementasi:** `frontend/src/components/ui/data-card.jsx` (DataCard,
DataCardHeader, DataTableShell, StatCard, EmptyRow) + baseline CSS global di
`frontend/src/index.css`. Detail lengkap & cara regenerasi ada di
`memory/HANDOFF_UI_TABEL.md`.

---

# ADDENDUM 3 — Impor Data Produksi Internal & Maklon dari Excel owner (2026-07-31)

**Sumber:** `data_import/DATA_PRODUKSI_MAKLOON_SPLIT_3.xlsx` (5 sheet). User minta impor
data produksi **internal (INVOICE DA)** & **maklon (INVOICE AE)**, cek kesesuaian dulu,
master lain boleh dibuat. Keputusan user: No PO→PO, No Invoice→serial(SN); snapshot (tanpa
rincian tiap setor, "sudah di tahap kirim ke DA"); auto-create master yang belum ada (CMT +
produk), CMT kosong→placeholder; dashboard Kejar CMT TIDAK diubah (fokus maklon); fokus 2 sheet.

**Pemetaan ke koleksi kanonik (dibaca `services/cmt_kejar.py` + `cmt_intake.py`):**
- `No PO` (PO-DA-xxx/PO-AE-xxx) → `production_pos.po_number`; `business_type` internal|maklon.
- `No Invoice` → `po_items.serial_number` (1 PO = banyak SN, sesuai dukungan SN sistem).
- `Jml Order` → `po_items.qty` = `vendor_shipment_items.qty_sent` (potongan dikirim ke CMT).
- `Total Disetor`→`cmt_receipt_lines.qty_shipped_by_cmt`; `Diterima Bersih`→`qty_actual`;
  `Reject Potongan`→`reject_qty`. `cmt_receipts.status='Approved'` (snapshot, `kali_setor`=1/PO).
- Nilai monitoring asli Excel disimpan utuh di `po_items.excel_*` (total_disetor, reject,
  retur_penjahit, diterima_bersih, sisa_potongan, kali_setor, status, alert, deadline, tgl_kirim).
- `Nama CMT` → `vendor_partners` (vendor_id PO + shipment + receipt). `Koh Tri (SnBM)` dibuat
  di `dewi_maklon_clients` sebagai buyer maklon; internal customer_name="DA Group (Internal)".

**Importer:** `scripts/import_produksi_maklon_from_excel.py` — **idempoten** (semua dok bertanda
`import_source='excel_produksi_maklon_v1'`, dibersihkan lebih dulu saat re-run; master yang
dibuat import juga bertanda & hanya itu yang dibersihkan — seed asli tidak disentuh).
**Insert langsung** ke koleksi kanonik → TIDAK memicu efek samping finance (draft AR maklon),
BOM explode internal, atau posting FG-stock. Re-run aman.

**Hasil impor (terverifikasi):** production_pos **89** (internal 53 + maklon 36), po_items **321**,
vendor_shipments 81 (+292 item +81 inspeksi), cmt_receipts 55 (+156 line).
Master auto-create: vendor_partners **+2** (P Aan, P Suratno) & sinkron status 14 + placeholder
`(Belum Ditentukan)`; rahaza_models **+13** (SKU produk belum ada di master); 1 klien maklon.

**Cek kesesuaian (compatibility):** struktur sistem SUDAH SESUAI. Master CMT sebelumnya sudah ada
(58 `vendor_partners`, cocok dgn sheet "daftar CMT"). SKU 44/57 match master lama; 13 dibuat baru.
Sheet **"produk sedang PO" DILEWATI** (100% redundan dgn Internal+Maklon → cegah PO ganda).
"produk buyer" (potongan masuk) invoice 100% overlap → info intake tercermin lewat vendor_shipments.

**Verifikasi:** service `owner_dashboard`/`compute_po_kejar` cocok angka Excel (spot PO-AE-002:
ordered 936 / disetor 935 / bersih 930 / sisa 1); API e2e `GET /api/production-pos`,
`/api/dewi/cmt-kejar/dashboard`, `/api/dewi/cmt-intake/batches` 200; UI **Monitoring CMT** render
(Potongan ke CMT 11.956 · Disetor 6.011 · Sisa 5.945 · 24 TELAT). Static bundle di-rebuild.
**Catatan:** tab "Cek Seri" menandai 7 seri "dobel" — WAJAR karena 1 No Invoice memang tersebar di
beberapa baris warna/ukuran (peringatan read-only, bukan error). Ongkos jahit = 0 (rate tak ada di Excel).

# ADDENDUM — SELISIH KIRIM (SHORT SHIPMENT) CMT→DA & DA→BUYER (2026-08-01)

## Aturan bisnis (ditetapkan owner 2026-08-01)
DUA kasus yang HARUS dibedakan:
* **REJECT** — barang SAMPAI tapi cacat → `produced_qty` vendor tetap, barang masuk karantina QC,
  lalu permak (sendiri / retur CMT). *(sudah ada sejak FASE 1)*
* **SELISIH KIRIM** — barang **TIDAK SAMPAI**. Vendor klaim kirim 100, DA terima 90:
  1. **dokumen = kenyataan** → deklarasi/penerimaan dikoreksi menjadi 90 (klaim asli disimpan terpisah);
  2. 10 pcs = **kewajiban pengirim** (`open`, TANPA batas waktu) → **sisa kirim vendor NAIK 10** supaya
     bisa dikirim ulang; selisih tertutup OTOMATIS saat kiriman ulang selesai QC;
  3. **bukan** klaim finansial otomatis. Keputusan tanggungan (CMT / DA) hanya bila barang dinyatakan
     HILANG — di sisi buyer keputusan itu diambil saat PO ditutup;
  4. koreksi boleh **sepihak Admin DA** + **notifikasi vendor** (tidak ada proses sanggahan).

## Model data
| Koleksi / field | Arti |
|---|---|
| `cmt_short_shipments` (`SEL-CMT-xxxxx`) | dokumen selisih kirim vendor CMT → DA (`open`/`resolved`/`cancelled`, `resolution`, `history`) |
| `buyer_short_records` (`SEL-BYR-xxxxx`) | dokumen selisih kirim DA → buyer (+ `finance_decision`, `stock_returned_at`, `stock_writeoff_at`) |
| `cmt_receipt_lines.qty_claimed_by_cmt` | KLAIM vendor (dokumen asli) |
| `cmt_receipt_lines.qty_shipped_by_cmt` | qty yang BENAR-BENAR sampai (dokumen resmi setelah QC) |
| `cmt_receipt_lines.qty_short` / `short_status` | selisih baris + statusnya |
| `production_job_items.qty_claimed_by_vendor` | Σ klaim vendor |
| `production_job_items.qty_declared` | Σ yang benar-benar sampai (**bukan** klaim) |
| `production_job_items.qty_short_open` / `qty_short_resolved` | kewajiban vendor yang belum / sudah selesai |
| `buyer_shipment_items.qty_claimed_original` | klaim awal sebelum dikoreksi ke qty diterima buyer |
| `buyer_shipment_items.fg_issued_at` / `fg_issued_qty` | penanda idempotensi mutasi stok FG keluar |

## Endpoint
* `POST /api/prod/cmt-receipts/{id}/lines/{lid}/koreksi-hasil-qc` — koreksi qty lolos QC (stok FG ikut).
* `POST /api/prod/cmt-receipts/{id}/lines/{lid}/koreksi-deklarasi` — koreksi klaim vendor (+ rambatan + notifikasi).
* `GET /api/prod/short-shipments` · `POST /api/prod/short-shipments/{id}/resolve`
  (`dikirim_ulang` | `hilang_tanggungan_vendor` | `hilang_tanggungan_da` | `salah_input_dikoreksi`).
* `GET /api/buyer-shorts` · `POST /api/buyer-shorts/{id}/resolve`
  (`dikirim_ulang` | `tanggungan_cmt` | `tanggungan_da` | `dibatalkan`).
* `PUT /api/prod/cmt-receipts/{id}/lines/{lid}` → **409** setelah QC selesai (wajib pakai koreksi resmi).
* `POST /api/production-pos/{id}/close-short` → kini SAH juga dari status `Completed`.

## Invarian & alat
`INV-16` klaim = sampai + selisih terdokumentasi · `INV-17` tidak ada selisih tanpa dokumen ·
`INV-18` tiap dispatch buyer mengurangi stok FG.
Alat: `tests/scenario_selisih_ssot.py` (acceptance 43 cek) · `tests/backend_test_selisih_edge_cases.py` ·
`scripts/repair_selisih_ssot.py --dry-run|--apply` (perbaikan data lama) ·
`scripts/verify_produksi_maklon_invariants.py --audit-only` (audit data nyata tanpa membuat data uji).


---

# SATUAN (UoM) DI TITIK MASUK/KELUAR STOK — 2026-08-05

## Masalah yang diselesaikan
Operator lapangan menghitung barang dalam satuan fisik yang mereka pegang (per **box / rol / pak /
gram / yard**), sementara sistem menyimpan stok dalam **satuan dasar** (INV-UOM-2). Backend sudah
menerima satuan sejak Juli, tetapi LAYARNYA belum punya pemilih satuan sehingga satu-satunya cara
adalah mengetik angka dalam satuan dasar — sumber salah hitung (mis. "3 pak" tercatat 3 pcs).

## Perilaku sekarang
| Layar | Endpoint | Field satuan |
|---|---|---|
| Gudang → Scan Gudang (Scan In) | `POST /api/wms/pending/{id}/scan-in` | `input_uom` |
| Gudang → Penyimpanan (Put-away) | `POST /api/wms/putaway/place` | `input_uom` |
| Gudang → Opname Scan | `POST /api/wms/opname3/scan` | `input_uom` |
| Gudang → Pengeluaran Material | `POST/PUT /api/rahaza/material-issues` | `items[].qty_uom` |
| Aksesoris → Master & Stok (terima/keluarkan) | `POST /api/acc/stock/{receive,issue}` | `input_unit` (base \| pack \| kode satuan) |
| Aksesoris → Stok Opname | `PUT /api/acc/opname/{id}/count` | `counted_uom` |
| Cutting → Input Progres | `POST /api/cutting/orders/{id}/progress` | `input_uom` |

* Daftar satuan yang ditawarkan layar = **kemampuan server**, dari satu endpoint:
  `GET /api/rahaza/materials/uom-options?material_ids=a,b,c`
  (kemasan master + satuan sedimensi global + kain m⇄kg via gramasi & lebar; alias ganda disembunyikan).
* Konversi dieksekusi SATU helper: `core/bom_uom.factor_to_base(material, unit)`; jejaknya
  (`input_qty`, `input_uom`, `uom_factor`, `uom_source`) dibekukan di baris ledger.
* Layar SELALU menampilkan pratinjau ("2 rol → 50 kg") sebelum disimpan, dan peringatan bila satuan
  belum punya faktor. Tanpa memilih satuan, perilakunya sama seperti sebelumnya (satuan dasar).
* Satuan yang tidak bisa dikonversi ditolak **400** dengan pesan yang mengarahkan ke Master Material —
  tidak pernah diam-diam dihitung 1:1 pada jalur stok.
* Komponen UI: `frontend/src/components/erp/uom/UomPicker.jsx` + `frontend/src/hooks/useUomOptions.js`.
* Uji: `tests/flow_uom_entry_points_ui_test.py` (38 cek) · `scripts/poc_uom_entry_points.py` (11 cek).
* Data demo: `scripts/seed_uom_ui_demo.py` (`--cleanup` untuk membuang).

# PENOMORAN DOKUMEN — TAHAP 2 (2026-08-05)
Owner mengatur format nomor di **Portal Administrasi Sistem → Penomoran Dokumen** (`45 jenis`).
Token: `{YYYY} {YY} {MM} {DD} {SEQ:n}` + token khusus per jenis (`{TIPE}`, `{KLIEN}`, `{PREFIX}`,
`{STYLE}/{WARNA}/{SIZE}`). Satu-satunya generator tetap `utils.counters.gen_prefixed_number`
(race-safe lewat koleksi `counters`, lazy-init dari nomor tertinggi yang sudah ada).
* Tahap 2 memindahkan 11 penghasil nomor manual: PO pembelian · GR penerimaan · AP dari GR ·
  klaim biaya karyawan · perjalanan dinas · penyelesaian dinas · PO maklon · pengiriman maklon ·
  invoice maklon manual · invoice maklon otomatis (AR) · job vendor.
* `config_key=` dipakai bila dua jenis nomor menumpang satu koleksi+field
  (`rahaza_ar_invoices.invoice_number`: AR Finance vs invoice maklon).
* Perubahan format hanya berlaku untuk dokumen BARU. Menurunkan nomor urut ditolak bila sudah ada
  dokumen memakai awalan yang sama (mencegah nomor kembar — INV-CNT-1).
* Uji: `tests/flow_doc_numbering_phase2_test.py` (19 cek, termasuk 25 permintaan bersamaan → unik).

# DASHBOARD MAKLON — ALUR PRODUKSI (2026-08-05)
Portal Maklon → Monitoring Progress → **Alur Produksi** (`#maklon-alur-produksi`) menampilkan
perjalanan barang maklon dari `GET /api/prod/dashboard?business_type=maklon`:
Rencana PO → Cutting → Di Vendor CMT → Terima & QC → Permak → **Dispatch ke Buyer**, plus KPI
(PO berjalan, di vendor, menunggu periksa, tingkat cacat) dan pemilih periode 7/30/90 hari.
Komponennya SAMA dengan Portal Produksi (`ProductionDashboardOverview`, beda `businessType`) sehingga
tidak ada dua sumber angka.

# ADDENDUM — RBAC SATU TEMPAT (2026-08-06)

**Masalah owner:** ada DUA tempat mengatur akses (dialog "Edit Role" + "Matriks Role & Permission"),
membingungkan; matriksnya terlalu besar untuk dikonfigurasi.

**Keadaan sekarang (SSOT tunggal):**
* **Katalog izin**: `backend/data/permission_catalog.py` — 129 izin, tersusun portal → modul → izin,
  tiap izin bermetadata `action` (`view/input/manage/approve/run/export`).
  `GET /api/permissions` (datar) · `GET /api/permissions?grouped=1` (bersarang).
* **Satu layar konfigurasi**: `frontend/src/components/erp/RoleManagementModule.jsx`
  ("Peran & Hak Akses", master–detail 5 bagian). `RoleMatrixModule.jsx` DIHAPUS.
  Hub Kontrol Akses: **Pengguna | Peran & Hak Akses** (2 tab).
* **Satu jalur simpan**: `POST /api/roles` & `PUT /api/roles/{id}` (name, description, portals,
  hidden_modules, permissions). `PUT /api/roles/{id}/permissions` dan `POST /api/roles/matrix/bulk`
  DIHAPUS.
* **Satu mesin penegakan**: `backend/routes/shared.py` → `has_perm` / `can_act` / `require_perm` /
  `require_perm_dep`, model **FALLBACK AMAN**:
  super role atau `*` → izin yang diminta → (bila izin peran masih kosong) daftar role legacy
  / `legacy_any=True` → selain itu 403. **Konsekuensi disengaja:** begitu owner mencentang izin,
  daftar izin itulah yang berlaku untuk peran tersebut.
* Cache izin proses TTL 20 detik + `auth.bump_rbac_cache()` saat peran/pengguna berubah.
* Titik aksi/approval yang sudah dipusatkan: MI approve, Cutting, CMT (intake/belanja/kejar/permak),
  Penomoran Dokumen, approval Opname Gudang, approval ubah Invoice, Inbox Approval SDM, Put-away.
  Sisa penjaga hardcode (±80 berkas) tetap jalan dan dimigrasi bertahap.
* Rincian: `memory/RBAC_KONSOLIDASI_2026-08-06.md`.

## Sesi 2026-08-07 (RnD: foto desain, banding revisi, tahap lengkap, rapor mingguan,
ambang peringatan) — rinciannya dipindah ke `memory/CHANGELOG.md` agar PRD tetap ringkas.

## Sesi 2026-08-07 lanjutan #3 — R&D: warna multi, ukuran bebas, Tech Pack, HPP hybrid

Lingkup dari `memory/PROPOSAL_RND_WARNA_UKURAN_TECHPACK_HPP.md` (F1–F4, **selesai semua**).
Rincian pengerjaan & bukti: `plan.md` + entri teratas `memory/CHANGELOG.md`.

### Aturan produk yang sekarang berlaku (yang perlu diingat lintas sesi)

* **Warna R&D = master `rahaza_colors`.** Tidak ada lagi warna teks bebas di R&D. Layar R&D
  memakai proxy `GET/POST /api/dewi/rnd/color-options`; warna baru ditulis **ke master itu**
  sehingga langsung dipakai produksi/gudang/marketing (tidak perlu pindah menu).
* **SKU varian R&D = `{STYLE}-{COLOR_CODE}-{SIZE}`** lewat `utils/variant_ssot.build_variant_sku()`
  — sama urutannya dengan SKU FG. SKU lama TIDAK ditulis ulang otomatis; ada laporan
  `GET /api/dewi/rnd/variants/sku-audit` + perbaiki per baris `POST /variants/{id}/fix-sku`.
* **Satu varian = satu warna** (fan-out). `POST /api/dewi/rnd/variants/bulk` membuat N dokumen
  dari satu input. **Varian kembar (style+warna) DITOLAK 409.**
* **Field warna pada `dewi_rnd_variants`:** `color_id` (FK master) · `color_code` = **KODE**
  (`NVY`) · `color_hex` = **HEX**. Dokumen lama yang menyimpan hex di `color_code` tetap dibaca.
* **Ukuran R&D BEBAS, per style** — `dewi_rnd_styles.size_list` (boleh `"All Size"`, `"28/30"`).
  SATU daftar dipakai modal Varian **dan** Tech Pack. `base_size` dipilih dari daftar,
  `size_range` **dihitung**. Kebijakan **B1**: dipadankan otomatis ke `rahaza_sizes` bila nama
  sama (`size_map[].size_id` = petunjuk), sisanya ditandai **"belum dipadankan"**.
* **SATU pintu pemadanan ukuran: `utils/variant_ssot.resolve_master_size()`** (2026-08-08).
  Dipakai **bersama** oleh `build_size_map()` (layar) DAN `promote_rnd_variants_to_master()`
  (promosi ke produksi). Urutannya: petunjuk `size_map` (keputusan manusia) **menang** → kode →
  nama → `rahaza_sizes.aliases[]` → alias baku lapangan (`SIZE_ALIAS_GROUPS`: `2XL⇄XXL`,
  `3XL⇄XXXL`, `All Size⇄Free Size`, …) → (opsional) buat baru.
  ⚠️ **JANGAN pernah** memberi salah satu sisi aturan pemadanannya sendiri lagi. Dulu begitu,
  akibatnya layar bilang `'All Size'` "sudah dipadankan → ALLSIZE" sementara promosi tetap
  membuat ukuran master **kembar** `'ALL SIZE'`, dan `'28/30'` jadi kode master bergaris-miring
  yang bocor ke SKU FG (`STYLE-NVY-28/30`). Dibuktikan `scripts/poc_rnd_size_promotion.py`.
* **Kode master ukuran SELALU alfanumerik** (`norm_size_key()` di `ensure_size`) — spasi/garis
  miring tidak boleh pernah masuk kode karena kode itu dipakai menyusun SKU. `name` menyimpan
  tulisan aslinya.
* **Layar "Padankan Ukuran"** (`GET/POST /api/dewi/rnd/size-mapping{,/apply,/auto}`) — tempat
  manusia memutuskan padanan yang tidak bisa ditebak mesin. Ringkasannya membaca **DUA sumber**:
  `dewi_rnd_styles.size_list` DAN `dewi_rnd_variants.sizes` — yang kedua wajib karena importir
  Excel menulis label yang tidak ada di `size_list` mana pun (mis. `ONESET`, `TOP`), dan
  label itulah yang benar-benar dipromosikan ke produksi. Layar ini **TIDAK PERNAH** mengubah
  `size_list` (B1 tetap: ukuran teks bebas); ia hanya menambah `size_id` di `size_map` dan
  `aliases[]` di master. Dijaga gate INV-RND2 (SM-1..SM-8).
* **PO produksi internal mewajibkan `size_id` sah** (`production_internal_adapter.validate_internal_item`
  → 400). Karena itu promosi mengembalikan `sizes_created[]` supaya penambahan master ukuran
  tidak terjadi diam-diam, dan pengguna diarahkan ke layar Padankan Ukuran.
* **Master warna & ukuran di-seed dari PINTU TERBAWAH.** `ensure_color()` menyemai palet
  `DEFAULT_COLORS` bila `rahaza_colors` kosong. ⚠️ **JANGAN** memindahkan penyemaian ini balik ke
  endpoint daftar saja: pemanggil lain (importir Excel, promosi varian) akan membuat warna
  sampah `{code:'NVY', name:'NVY', hex:'#CCCCCC'}` lebih dulu, koleksi jadi tidak-kosong, dan
  palet asli tidak pernah ter-seed lagi. Tetap **hanya bila KOSONG** supaya warna yang sengaja
  dihapus tidak dihidupkan kembali. Dijaga gate INV-COLOR.
* **Tech Pack `size_columns` = `[{col_id,label}]`.** `measurements[].values` dikunci **`col_id`**,
  bukan nama kolom. **Mengganti nama kolom tidak boleh menghilangkan nilai** — dijaga gate
  INV-RND-1/2, dengan `values_legacy` + `orphan_values` + `measurements_stats
  {values_in,values_out,orphans}` sebagai bukti. Jangan pernah kembali mengunci nilai dengan
  nama kolom.
* **Baris BOM Tech Pack tanpa tautan master WAJIB kelihatan** (`master_linked=false` +
  `bom_unlinked_count` + latar merah di layar): baris itu tidak punya harga & faktor konversi
  satuan, jadi HPP-nya salah. Jangan pernah menyembunyikan penanda ini.
* **HPP: sumber biaya PER BARIS** (`dewi_rnd_hpp.cost_lines[]`, `source ∈ master|techpack|manual`).
  `total = Σ SEMUA baris` ⇒ master + custom boleh bercampur. Kebijakan **D1**: override harga
  master **boleh** tapi `override_reason` **WAJIB** (backend 400 bila kosong), `unit_cost_master`
  disimpan sebagai snapshot untuk `GET /hpp-calculator/{id}/stale-check`.
* **Kompatibilitas mundur HPP dijaga keras:** field `use_bom` **tetap disimpan**; dokumen lama
  dibaca sebagai "semua Techpack" / "semua Manual" oleh `legacy_cost_lines()` **tanpa** menghitung
  ulang `hpp_total` tersimpan. Logika harga per baris dipakai bersama (`_cost_one_line`) supaya
  angka lama tidak mungkin bergeser. Ada gate untuk ini (INV-RND-7).
* **Ongkos CMT** boleh diambil dari master `dewi_maklon_buyer_catalog.default_cmt_price` lewat
  `GET /api/dewi/rnd/hpp-calculator/cmt-suggestions` (tetap boleh diketik manual).
* **Peringatan "harga master sudah berubah" ada di DAFTAR HPP** (2026-08-08), bukan hanya di form.
  `GET /api/dewi/rnd/hpp-calculator` menambah `stale_count`, `stale_delta_total`,
  `stale_checked_lines`, `stale_lines[]` (`?with_stale=false` untuk mematikan). Definisi "basi"
  ada di **satu** fungsi `_stale_lines_for_doc()` yang dipakai bersama dengan `/stale-check`,
  supaya daftar & form tidak mungkin menjawab berbeda (dijaga ST-3).
  ⚠️ **UANG:** peringatan ini murni BACA — `hpp_total`, `direct_cost`, dan `cost_lines[].line_cost`
  dikembalikan apa adanya. Baris `manual` dan dokumen HPP lama tidak pernah ditandai.
  Dijaga ST-4 (membandingkan angka sebelum vs sesudah harga master diubah).
  Performa: `_cost_one_line(…, cache)` memoisasi **hanya** pencarian master material —
  jangan pernah memasukkan qty/satuan ke kunci memo, dan jangan memoisasi hasil aritmetikanya.
* **Seeder R&D** `POST /api/dewi/rnd/seed?reset=true` membuat 7 style + `size_list` (sengaja
  bercampur: persis master, butuh alias, dan benar-benar baru) + 13 varian nyata + 2 HPP
  (hybrid & gaya lama) memakai `compute_cost_lines`/`_calculate_hpp` yang sama dengan endpoint
  sungguhan. Tanpa ini, layar Varian / Padankan Ukuran / HPP KOSONG di DB bersih.

### Gate baru
`scripts/verify_rnd_invariants.py` → di `gate.sh` sebagai **"DATA/UANG — R&D: ukuran tech pack,
SKU SSOT, HPP hybrid (INV-RND)"** (11 invarian, membersihkan datanya sendiri).
`scripts/verify_color_palette_seed.py` → **"DATA — SSOT warna: palet master bebas warna sampah
(INV-COLOR)"** (6 invarian, jalan di **DB SEMENTARA** — tidak menyentuh data aplikasi).
`scripts/verify_rnd_size_mapping_stale.py` → **"DATA/UANG — R&D: padankan ukuran + harga master
basi (INV-RND2)"** (13 invarian: SM-1..SM-8 + ST-1..ST-5). Gate total: **16**.
Alat bantu: `scripts/verify_rnd_f1_f4.py` (39 pemeriksaan setara user story) ·
`scripts/poc_rnd_size_promotion.py` (POC "sebelum vs sesudah", jangan dihapus) ·
`scripts/cleanup_rnd_test_data.py` (punya `--dry`).


## Sesi 2026-08-08 (lanjutan) — REKAP HARIAN CMT ("vendor mana yang belum diisi hari ini")

**Kebutuhan produk.** Setelah pintu "Input Vendor CMT" ada, staf tetap tidak punya cara mengetahui
vendor mana yang belum dikerjakan hari itu. Dengan puluhan vendor CMT, satu yang terlewat = progress
hari itu tidak masuk, dan karena **tagihan CMT dihitung dari progress produksi**, uangnya tidak bisa
ditagih/diverifikasi.

**Bentuk yang dipilih owner: CHECKLIST PER TUGAS.** Satu baris per vendor, lima kolom pekerjaan
harian (Terima Material · Inspeksi Material · Progress Produksi · Kirim ke DA/Buyer · Balas
Reminder). Empat status per sel — dan status keempat itu penting:

| Status | Arti | Kenapa ada |
|---|---|---|
| `done` ✓ | ada pengisian pada tanggal itu, tidak ada sisa | — |
| `partial` ✓+ | ada pengisian, TAPI masih ada sisa | supaya rekap tidak mengaku "beres" saat masih ada surat jalan / pcs menganggur |
| `pending` ✗ | ada pekerjaan menunggu, belum ada pengisian | inilah yang dicari staf |
| `none` — | memang tidak ada pekerjaan jenis itu | supaya "—" tidak tertukar dengan "belum" |

**Aturan yang WAJIB dipatuhi kalau area ini disentuh lagi:**
1. **SSOT satu berkas** `backend/core/cmt_daily_recap.py`. Layar, export Excel/PDF, dan sasaran
   tombol reminder memakai `build_recap()` yang SAMA. Jangan menghitung ulang di tempat lain.
2. **Batas hari WIB** (`utils.waktu.wib_day_bounds_utc`). Jam container UTC; memakai `datetime.now()`
   polos membuat rekap "hari ini" menampilkan hari kemarin selama 00:00–07:00 WIB.
3. **`production_progress` tidak punya `vendor_id`** — vendor diresolusi lewat `production_jobs`.
4. **`received_at` diisi SERVER** pada transisi `Sent → Received` (`routes/vendor_shipment.py`).
5. **Reminder `reminder_type='daily_recap'` + `recap_date`** dikecualikan dari hitungan `waiting`
   pada tanggalnya sendiri (idempotensi + anti abadi-merah).
6. Kolom "menunggu" untuk tanggal lampau dihitung **per akhir hari itu** memakai stempel waktu
   peristiwa, bukan kondisi sekarang.

**Endpoint baru:** `GET /api/cmt-override/daily-recap` · `POST /api/cmt-override/daily-recap/remind`
· `GET /api/cmt-override/daily-recap/export?format=xlsx|pdf`.

**Invarian & alat:** gate **INV-REKAP** (`scripts/verify_rekap_harian.py`, 19 kode invarian) —
terdaftar di `scripts/gate.sh` sehingga ikut dijalankan setiap sesi; POC `test_core_rekap_harian.py`.

**Bukti:** POC 102/102 · INV-REKAP 22/22 · `gate.sh` 18/18 HIJAU · testing agent iteration_38 0 bug ·
UI klik-penuh 10/10 user story · tagihan CMT 2.435.000 → 2.435.000.


## Sesi 2026-08-10 (fase 4) — REKAP MINGGUAN CMT ("siapa yang belakangan ini sering bolong")

**Kebutuhan produk.** Rekap Harian menjawab "siapa yang belum diisi HARI INI" — cukup untuk mengejar
pekerjaan hari itu, tapi tidak bisa menjawab pertanyaan yang dibawa ke rapat: **"vendor mana yang
BELAKANGAN INI sering bolong?"** Satu hari merah bisa kebetulan (vendor libur, listrik mati); tujuh
hari berturut-turut merah adalah masalah — dan karena tagihan CMT dihitung dari progress produksi,
masalah itu berujung ke uang yang tidak bisa ditagih.

**Bentuk: TAB KEDUA di pintu yang sama, bukan pintu baru.** Tab **Harian | Mingguan** di dalam "Input
Vendor CMT"; Harian tetap tampil pertama (itu yang dibuka staf tiap pagi). Pintu baru = satu tempat
lagi yang harus diingat, dan rekap yang terpisah dari jalan pengisiannya hanya jadi laporan.

### Keputusan owner (dikonfirmasi 2026-08-10)

| # | Pertanyaan | Keputusan |
|---|---|---|
| 1 | Batas pekan | **7 hari terakhir BERGULIR** (`akhir−6 … akhir`), bukan Senin–Minggu ISO. Versi ISO membuat setiap Senin pagi menampilkan pekan yang baru berumur satu hari — tidak bisa dipakai memutuskan |
| 2 | Arti "hari terlambat" | **DUA angka terpisah, tidak ada yang dibuang**: `days_late` = hari `pending` (ada pekerjaan menunggu, NOL bukti) → dipakai mengurutkan; `days_unfinished` = `pending` + `partial` (masih ada sisa) |
| 3 | Kolom baris vendor | 7 kotak hari · Terlambat · Belum beres · Hari tanpa setoran · pcs disetor · pcs dikirim · sparkline tren pcs · streak |
| 4 | Streak | Rentetan beruntun **paling akhir** (mundur dari hari terakhir yang sudah berjalan); **putus** pada hari `pending` **ATAU** `partial` |
| 5 | Tombol tab Mingguan | Export Excel + PDF · klik kotak hari → tab Harian tanggal itu · **plus** tombol reminder untuk **satu tanggal jelas** (hari terakhir yang sudah berjalan) |

### Tiga aturan turunan yang ditulis EKSPLISIT (supaya bukan tebakan orang berikutnya)

1. **"Hari tanpa setoran"** hanya dihitung pada hari vendor **memang punya job jalan**
   (`progress.state != 'none'`) tetapi `progress.done_today == 0`. Vendor yang tidak diberi pekerjaan
   TIDAK boleh dihukum — itu angka bohong yang membuat peringkat vendor terburuk jadi karangan.
2. **Hari `idle` NETRAL bagi streak**: tidak memutus (vendor tidak salah apa-apa) tetapi juga tidak
   menambah (tidak ada prestasi). Hanya `done` yang menambah.
3. **Hari di masa depan** (> hari ini WIB) diberi state `future`, tidak dihitung ke angka mana pun,
   dan `build_recap` tidak dipanggil untuk hari itu (hemat ±10 query per hari yang belum terjadi).

**Aturan arsitektur yang WAJIB dipatuhi kalau area ini disentuh lagi:**
1. **`build_week()` hanya MERINGKAS `build_recap()`** — tidak punya satu pun query sendiri. Semua
   aturan sulit (batas WIB, definisi "terisi", pengecualian reminder rekap, resolusi vendor
   `production_progress`) otomatis ikut tanpa disalin ulang, dan tab Mingguan mustahil berbeda dari
   tab Harian untuk tanggal yang sama.
2. **`prefetch_context()` dipakai ulang** untuk ketujuh hari (data master dibaca SEKALI).
3. **Sasaran reminder mingguan = `pending_vendor_rows()` yang sama** dengan tab Harian ⇒ dua tombol
   tidak akan pernah memilih vendor berbeda untuk tanggal yang sama.
4. **Pemilik state tanggal = `CMTOverrideRecapPanel.jsx`**; `CMTOverrideDailyRecap` terkendali
   (`day` + `onDayChange`). Tanpa ini, klik kotak hari tidak bisa memindahkan tab Harian.

**Endpoint baru:** `GET /api/cmt-override/weekly-recap?date=&days=&include_inactive=` ·
`GET /api/cmt-override/weekly-recap/export?format=xlsx|pdf&date=&days=`.
`date` = hari **TERAKHIR** jendela (default hari ini WIB); `days` 1..31 (default 7), di luar itu 400.

**Invarian & alat:** gate **INV-REKAP** diperluas ke **30 kode** (baru **RK-20…RK-27**: rentang
bergulir & validasi parameter · konsistensi harian↔mingguan · dua angka terlambat tetap terpisah ·
hari tanpa setoran tidak menghukum · aturan streak · SSOT export mingguan termasuk URUTAN baris ·
RBAC + header override diabaikan + hari future · kinerja `prefetch_context`). POC
`test_core_rekap_harian.py` naik 102 → **169** pemeriksaan. Suite read-only tambahan:
`backend_test_fase4_mingguan.py` (17 uji, tanggal dinamis).

**Bukti:** POC 169/169 · INV-REKAP 30/30 · `gate.sh` 18/18 HIJAU · testing agent iteration_39
backend 17/17 + frontend 100% + 0 bug · UI klik-penuh 11/11 user story · tagihan CMT
2.435.000 → 2.435.000 · nol jejak data uji · state demo dipulihkan (SJ demo kembali `Sent`,
nol reminder rekap sisa).

---

### FASE 5 (2026-08-10, lanjutan) — `closed_at`: rekap tanggal lampau berhenti menebak

**Masalah (backlog nomor 1 fase 4).** Rekap Harian/Mingguan CMT menjawab "apa yang MENUNGGU pada
akhir tanggal X". Untuk kolom **Progress Produksi**, "menunggu" = ada **job yang sedang jalan** —
dan sebelum fase ini pertanyaan itu dijawab dari **status SEKARANG**. Akibatnya job yang dibuka
Senin, tidak disetor Senin, lalu **ditutup Rabu** HILANG dari rekap Senin: **kelalaian yang sudah
terjadi terhapus sendiri begitu job-nya ditutup**. Progress produksi adalah dasar **tagihan CMT**,
jadi laporan seperti itu tidak bisa dipakai memverifikasi bantahan vendor.

**Solusi.** `production_jobs` menyimpan **`closed_at`** yang ditulis **SERVER** lewat SATU penulis:
`backend/core/production_job_lifecycle.close_job()`. Aturan "masih jalan pada saat itu" juga hanya
ada di satu tempat: `was_open_at(job, moment)`, dipakai rekap harian **dan** mingguan.

**Aturan arsitektur yang WAJIB dipatuhi kalau area ini disentuh lagi:**
1. **Satu penulis `closed_at`.** Ada DUA jalur penutup job (auto-complete
   `routes/production_execution.py` + Quick Complete `routes/production_pos.py`); keduanya memanggil
   `close_job()`. Jalur penutup baru WAJIB ikut — gate **RK-29** memeriksa seluruh DB.
2. **`closed_at` (dan status penutup) TIDAK boleh diterima dari body permintaan** — itu persis cara
   bug `received_at` dulu masuk sebagai STRING dari jam komputer staf.
3. **`JOB_CLOSED_STATUSES` diimpor, tidak disalin.** Salinan itulah yang suatu hari akan berbeda.
4. **Status tak dikenal dianggap TERBUKA** (pilihan sadar: pekerjaan yang hilang dari rekap
   memakan uang; baris merah palsu hanya memakan satu penyelidikan).
5. **Job warisan tidak ditebak dalam kode aplikasi** — hanya migrasi yang menebak, dan ia menandai
   hasilnya `closed_at_estimated: True`. `close_job()` boleh mengganti perkiraan dengan pengamatan;
   stempel teramati **tidak pernah** ditimpa.
6. **Peringatan job warisan tidak boleh dihapus dari layar** (RK-30). Laporan yang menyembunyikan
   ketidaktahuannya sendiri lebih berbahaya daripada laporan yang mengakuinya.

**Migrasi:** `python3 backend/migrations/add_closed_at_to_production_jobs.py [--report|--execute]`
— backfill dari `updated_at` (fallback `created_at`), idempoten, dokumen tanpa penanda waktu apa pun
DILEWATI dan dilaporkan (tidak dikarang).

**Field API baru** pada `GET /api/cmt-override/daily-recap` & `weekly-recap`:
`legacy_jobs_without_closed_at` (int) · `legacy_note` (kalimat aksi) · `as_of_note_base` (harian).
`as_of_note` tetap **utuh** = `as_of_note_base` + `" Catatan: "` + `legacy_note` karena berkas
export membacanya sebagai satu kalimat — dikunci oleh RK-30.

**Frontend:** peringatan amber `cmt-recap-legacy-jobs` (tab Harian) & `cmt-week-legacy-jobs`
(tab Mingguan). Sebelum ini tab Mingguan tidak pernah menyebut keterbatasan itu sama sekali.

**Invarian & alat:** gate **INV-REKAP** diperluas ke **34 kode** (baru **RK-28** tanggal sebelum
penutupan tetap terhitung & sesudahnya tidak · **RK-28b** suntikan klien diabaikan · **RK-29** nol
job tertutup tanpa `closed_at` di seluruh DB · **RK-30** job warisan diakui di layar harian+mingguan
dan komposisi `as_of_note` dikunci). POC `test_core_rekap_harian.py` naik 169 → **191** pemeriksaan.

**Bukti:** POC 191/191 · INV-REKAP 34/34 · `gate.sh` **18/18 HIJAU** · `gate.sh --full`
**22/22 HIJAU** · verifikasi visual kedua tab (Playwright) · tagihan CMT 2.435.000 → 2.435.000 ·
nol jejak data uji · nol job tertutup tanpa `closed_at` di DB akhir.


---

## 2026-08-11 (lanjutan #2) — Portal Marketing F18#3: Rincian Produk per Sesi Live

**Kebutuhan bisnis:** sesudah live selesai, pertanyaan pertama pemilik toko adalah
"tadi barang mana yang paling laku?" — jawabannya menentukan apa yang dibawakan di
sesi berikutnya dan berapa yang disiapkan gudang. Aplikasi belum bisa menjawabnya:
endpoint `live/analytics/product-performance` membaca `products[]` yang **tidak
punya satu pun jalan pengisian** (CRUD, impor, dan seed sama-sama tidak menulisnya),
dan parameter `account_id`-nya **diterima tapi tidak dipakai** sehingga filter toko
di layar tidak berpengaruh.

**Yang dibangun:**
- SSOT `backend/core/marketing_live_products.py` + koleksi
  `marketing_live_session_products` (1 baris = 1 produk pada 1 sesi live).
  Aturan yang ditegakkan server: produk wajib item katalog **toko sesi itu** ·
  satu produk sekali per sesi (**indeks unik DB**) · jumlah rincian tidak boleh
  melebihi omzet sesi (toleransi 2% — mencegah omzet dihitung dua kali) ·
  `revenue > 0` dengan `0` unit ditolak · `units_sold = 0` sah ("dibawakan tapi
  tidak terjual") · harga rata-rata/HPP/margin dihitung server.
- 6 endpoint sub-resource `/api/marketing/live/sessions/{id}/products*` termasuk
  **`sync-session-totals`** (aksi eksplisit "samakan total sesi", bukan efek
  samping — total sesi biasanya berasal dari laporan resmi marketplace).
- `products[]` diterima pada CRUD sesi (satu form satu simpan); hapus sesi ⇒
  rincian ikut terhapus; daftar sesi membawa ringkasan `products_detail`.
- Impor tanpa AI jenis data ke-16 `live_session_products` dengan konteks
  **`live_session`** (sesi dipilih di wizard, bukan dicocokkan dari judul berkas).
- Layar: editor + dialog **Rincian**, kolom **Rincian Produk** di tabel Live
  Sessions, tab **Produk Terlaris** (+ kolom Toko & filter toko) di Analytics,
  pemilih sesi live di wizard Impor Data.

**Bugfix menyertai:** Ulasan & Retur menyimpan `platform: null` pada setiap baris
baru (model dibuat opsional tanpa mengganti sumbernya) ⇒ sekarang `account_id`
WAJIB dan `account_name`/`platform` selalu turunan master.

**Invarian & bukti:** gate **INV-MKTSCOPE** 28 → **32 kode** (MKS-24 lingkup toko
rincian · MKS-25 baris yatim · MKS-26 produk dobel · MKS-27 rincian melebihi omzet
sesi; MKS-25 & MKS-27 dibuktikan MERAH dengan pelanggaran sintetis). POC
`test_core_live_session_products.py` **71/71** · `gate.sh` **21/21 HIJAU** ·
interaksi layar diverifikasi langsung (simpan rincian, samakan total sesi,
over-alokasi ditolak & pesannya tampil, catat sesi + rincian satu simpan).

**Ditunda (butuh keputusan proses bisnis):** nota kredit retur & jembatan AR
otomatis — lihat `memory/BISNIS_PROSES_F18_NOTA_KREDIT_DAN_AR_BATCH.md`.

---

## SESI 2026-08-12 — FINALISASI ANALISIS + KEPUTUSAN OWNER (dasar rencana F0–F10)

**Tidak ada kode fitur yang ditulis pada sesi ini.** Yang dihasilkan: verifikasi ulang seluruh
analisis sebelumnya terhadap sistem yang **benar-benar berjalan** (DB di-restore dari
`backups/auto_20260810_190000`, berkas TikTok asli 601 baris), lalu sintesis menjadi rencana
eksekusi yang terukur.

**Dokumen resmi (urutan baca):**
1. `memory/RENCANA_EKSEKUSI_MASTER_2026-08-12.md` — rencana F0–F10, aturan anti-halusinasi,
   tugas per berkas, angka bukti per fase, user stories, risiko.
2. `memory/SSOT_KONTRAK_DATA_2026-08-12.md` — kontrak data: 9 aturan wajib, field kanonik
   `marketing_orders` (header + `items[]`), `marketing_sales_data` (bersarang lengkap),
   katalog (status turunan + foto), anggaran (6 kategori), 3 koleksi baru yang sah.
3. `memory/VERIFIKASI_2026-08-12.md` — D01–D22 (cacat terbukti) + daftar **SUDAH BERES**
   (M1–M5 katalog, Marketing→AR dimatikan, SSOT lingkup toko, jalur impor tanpa AI) ⇒
   melindungi dari pengerjaan ulang.
4. `memory/REGISTRY_KOLEKSI_MARKETING.md` — 49 koleksi marketing + penulis/pembaca (hasil mesin).
5. Harness baru (READ-ONLY): `scripts/_forensic_ssot_v3.py`, `scripts/_audit_ui_tables_v2.py`.
   ⚠️ `scripts/_prove_catalog_master_gaps.py` **basi & label terbalik — jangan dipakai sebagai gate.**

**Keputusan owner yang mengikat (K1–K17):** dua angka omzet ditampilkan (`revenue_product`
Rp 59.783.811 & `revenue_order_amount` Rp 62.805.113 pada berkas uji) dengan `revenue_basis`
per toko sebagai dasar Target · rekap harian **diturunkan** dari pesanan impor (manual hanya
untuk platform tanpa ekspor) · impor **utamakan tanpa AI** + `format_fingerprint`, AI hanya
pembantu · **Pencairan/Settlement** satu-satunya pemicu Finance dan hanya **jurnal DRAFT** yang
di-approve Finance · Target/Anggaran diset di **dua portal** (Manajemen & Marketing) · kategori
anggaran **+`komisi`** (gratis ongkir tidak) · status katalog 6 tingkat termasuk **DITOLAK**,
"sudah tayang" ditandai staf + **wajib link marketplace** · foto master RnD **dibawa** ke
katalog + marketing tetap unggah foto marketplace · **satu** modul katalog dengan 2 tampilan ·
konten dapat pemilik + link video terbit + KPI · laporan **+Mingguan** (PDF & Excel) · KPI funnel
lewat **dua jalur** (impor & form mingguan) · RBAC `spv_marketing`/`staff_marketing`/
`content_creator`/`host_live` dengan lingkup toko ditegakkan · **hapus total jalur impor AI lama +
mesin impor sales lama** (2 berkas route + 3 berkas UI, 7 koleksi legacy di-drop; data & riwayat
lama diabaikan sesuai keputusan owner) sehingga `data-import` jadi satu-satunya pintu ·
ambang alert kuning 80% / merah 100% + kunci periode (pembuka: `owner`/`spv_marketing`) ·
potong stok saat impor **belum** dinyalakan (monitoring dulu).

**Prinsip permanen yang ditegaskan ulang:** `marketing_orders` / `marketing_sales_data`
**tidak pernah** menulis jurnal atau AR. Angka marketing selalu diberi label
**"sebelum potongan platform"** karena komisi platform tidak ada di ekspor pesanan.



## Portal Gudang — pintu yang hidup (Fase H, 2026-08-16)
Aturan tetap yang lahir dari sesi ini (jangan dilanggar tanpa keputusan owner baru):

- **SEMUA arus keluar gudang punya DOKUMEN di satu daftar (H-6b, 2026-08-17).** Empat pintu keluar —
  MI manual · BOM job produksi internal · Kirim Material CMT · **Cutting** — semuanya menerbitkan
  dokumen `rahaza_material_issues`, dan layar "Pengeluaran Material" bisa disaring per sumber
  (`?source=`, rekap `/material-issues/sources`). Aturan yang TIDAK boleh dilanggar:
  · Dokumen Cutting (`ref_type='cutting_issue'`, `source='cutting'`) **lahir berstatus `issued`** dan
    **TIDAK memotong stok** — stok & sisa gulungan sudah dipotong Portal Cutting saat progres
    dilaporkan (`stock_moved_by='cutting'`). Meng-approve/issue ulang = kain berkurang DUA KALI.
  · Dokumen Cutting **TIDAK dijurnal** (`gl_posted=False` + `gl_skip_reason`): cutting bukan
    pemakaian, nilai kain BERPINDAH menjadi nilai potongan (HPP potongan diisi saat order
    `complete`) dan potongan masih tercatat sebagai persediaan. `post-to-gl` MENOLAK dokumen ini.
    Koreksi nilai lewat Penyesuaian Stok.
  · **Satu laporan progres = satu dokumen** (idempoten: `cutting_progress_id` + indeks unik sparse).
    Progres tanpa dokumen WAJIB kelihatan (`GET /api/cutting/issue-docs/missing`) dan bisa
    diterbitkan retroaktif (`POST /api/cutting/issue-docs/backfill`) tanpa menyentuh stok.
  · Alat uji apa pun yang menghapus order/progres cutting **WAJIB** ikut menghapus dokumen MI-nya
    (kalau tidak, dokumen yatim menumpuk di layar Gudang). Dijaga gate **INV-F24** (14 invarian).
- **Pengeluaran Material (MI) = arus keluar gudang ke produksi.** Pembuatnya **admin gudang** dan
  **supervisor produksi** (`_require_mi_editor`: `inv.material_issue.manage` / `inventory.manage` /
  `warehouse.manage`). **Penyetujunya orang lain** (`_require_mi_approver`) — approval-lah yang
  memotong stok + memposting jurnal. Pembuat ≠ penyetuju, disengaja.
  Dua jalur buat: dari **BOM job produksi internal** (qty dihitung, tidak diketik) dan **manual
  dari master** (material wajib dari master; barang jadi tidak boleh keluar sebagai bahan).
  Pintunya ada di **Portal Gudang → Outbound** dan **Portal Produksi → Produksi Internal**
  (supervisor produksi tidak punya akses Portal Gudang).
- **Buat Barcode (`wh-barcode`)** — satu menu, dua tab (Bahan & Aksesoris · Barang Jadi).
  Nilai barcode **selalu kode master**; kode di luar master ditolak, bukan dicetak. Sumber jumlah
  label: manual per item atau **otomatis dari PO produksi** (qty label = qty PO). Batas 500
  lembar/cetak, 200/baris. Setiap cetak tercatat di `wh_barcode_print_jobs`.
  Gambar label hanya boleh dari SSOT `backend/core/label_render.py` — jumlah kolom/baris DIHITUNG
  dari ukuran halaman, jangan pernah dihardcode (dulu kolom ketiga tercetak di luar A4).
  SSOT barang jadi = `rahaza_materials` (`type='fg'`); `rahaza_fg_matrix` kosong dan hanya dibaca
  sebagai lapis pertama untuk data lama.
- **Menu yang koleksinya nol dilepas dari sidebar, id-nya tetap di `moduleRegistry`** supaya
  bookmark/deep-link lama tidak mati: `wh-scan`, `wms-cmt-dispatches`. Satu pekerjaan = satu pintu;
  pengiriman material ke CMT hanya lewat `prod-shipments-vendor`.
- **Modul yang muncul di lebih dari satu portal** wajib diselesaikan `App.js:findPortalForModule()`
  dengan penyaringan `canAccessPortal` (ada 14 modul seperti ini). Memilih portal pertama menurut
  urutan deklarasi membuang pemakai ke portal yang tidak ia punyai tanpa pesan. Dijaga gate INV-F19.

## Produksi/Maklon — aturan yang DIPUTUSKAN PEMILIK (2026-06-18, sesi #20)
- **Permak (rework) selalu punya induk.** Permak reject tidak boleh berdiri sendiri: dokumen yang
  dibuat dari form manual ditautkan server ke baris penerimaan CMT yang masih punya sisa reject
  (FIFO). Alasannya bisnis: pagar "sisa bisa kirim" dan pelepasan stok FG dari karantina keduanya
  membaca baris penerimaan — permak tanpa tautan = barang sudah bagus tetapi MUSTAHIL dikirim.
  Qty permak tidak boleh melebihi sisa reject baris itu.
- **Satu PO = satu surat jalan buyer yang progresnya naik.** Pengiriman bertahap DILANJUTKAN pada
  surat jalan yang sama (`shipment_id` ⇒ `dispatch_seq` +1, nomor tidak berubah). Membuat surat jalan
  baru untuk sisa kiriman dianggap cacat karena tidak ada satu pun dokumen yang mencapai 100%.
  Pagar kapasitas tidak pernah dilonggarkan oleh lanjutan: batas tetap "lolos QC + hasil permak −
  yang sudah dikirim", dihitung per `po_item` melintasi SEMUA surat jalan.
- **Aksesoris BOM tidak diketik ulang.** Form buat PO maklon menampilkan kebutuhan aksesoris dari BOM
  Template katalog buyer sebagai daftar READ-ONLY (pratinjau) — pemakai hanya mengetik aksesoris
  DI LUAR BOM. Pratinjau dan penulisan `po_accessories` wajib memakai satu mesin.
- **Vendor CMT boleh mengajukan material PENGGANTI sendiri** (bahan cacat/kurang saat inspeksi),
  bukan hanya TAMBAHAN; jenis permintaan ditentukan tab yang aktif, tidak dihardcode.
- **Kiriman anak hanya membawa isinya sendiri.** Surat jalan pengganti/tambahan/permak TIDAK membawa
  daftar aksesoris PO, supaya form inspeksi vendor tidak memunculkan aksesoris yang tak pernah
  dikirim dan tidak melahirkan permintaan aksesoris palsu.
- Dijaga gate **INV-F27** (`scripts/verify_permak_dispatch_aksesoris.py`).

## Monitoring CMT — aturan yang DIPUTUSKAN PEMILIK (2026-06-18, sesi #21)
- **Potongan ke CMT = SESUAI ORDER.** Hanya kiriman NORMAL yang dihitung. Kiriman PENGGANTI/TAMBAHAN
  (surat jalan anak) TIDAK boleh menambah potongan karena ia bukan bagian dari order — tetapi juga
  tidak boleh disembunyikan: dilaporkan terpisah (`qty_sent_extra` + rincian per jenis).
- **Belum dikirim ke CMT** = Σ(qty order − terkirim NORMAL) pada sudut pandang aktif; PO **Draft**
  otomatis terhitung penuh (potongannya masih di gudang) dan ditampilkan sebagai sub-angka.
- **Sudah dikirim ke buyer** dibaca dari SSOT `core/dispatch_capacity` — sama dengan pagar dispatch,
  supaya angka kartu tidak pernah bisa berbeda dari yang diizinkan sistem saat mengirim.
- **PO berjalan** = Draft · Confirmed · Distributed · In Production. PO Completed/Closed/Cancelled
  dibuang dari sudut pandang default; pemakai bisa pindah ke "Semua PO" lewat chip.
- **Papan Sisa Kirim** = satu baris per PO yang masih punya sisa, dengan jalan keluarnya langsung:
  lanjutkan surat jalan yang belum 100% (nomor tetap) atau buat yang pertama.
- **Rantai pengganti wajib terlacak**: permintaan → SJ pengganti → diterima vendor → diinspeksi,
  terlihat di layar vendor MAUPUN admin, dan dua arah (SJ anak menunjuk permintaannya).
- Dijaga gate **INV-F28** (`scripts/verify_monitoring_cmt_potongan.py`).

## Monitoring CMT — 12 kartu & keseimbangan (2026-06-18, sesi #22)
- Kartu WAJIB berurut sesuai alur proses (order → gudang → CMT → setor → QC → permak/scrap → siap
  kirim → terkirim → biaya) dan diberi nomor di layar; pemakai harus bisa membaca ke bawah tanpa
  membandingkan angka dari tahap yang berbeda.
- Angka kartu WAJIB seimbang dan dibuktikan di layar lewat 5 identitas (lihat CHANGELOG #22).
  Identitas yang pecah HARUS menyebut nomor PO penyebabnya — dijaga gate INV-F28 (F28-7b).
- 'Scrap/Hilang' = qty yang benar-benar hilang atau permak gagal (bukan biaya). Biaya jahit & biaya
  permak digabung dalam satu kartu tetapi angkanya tetap dipisah.
- Sisa bisa kirim SELALU per PO/per item (lolos QC + permak berhasil − terkirim); tidak boleh
  dijelaskan sebagai "disetor − terkirim" karena dua angka itu bisa berasal dari PO berbeda.

## Surat Jalan CMT → DA — aturan yang DIPUTUSKAN PEMILIK (2026-08-21, sesi #29c, W5)
- Surat jalan untuk barang jadi yang dikirim vendor **CMT → gudang DA** dicetak dari **baris
  penerimaan** di layar "Terima FG dari CMT" (satu penerimaan = satu surat jalan).
- **Satu dokumen, dua versi cetak.** Kolom hasil QC (`Qty Terima`, `Qty Reject`) adalah PILIHAN,
  bukan jenis dokumen kedua. Default yang tercentang hanya **versi kirim murni** (No · Serial · SKU ·
  Produk · Size · Warna · Qty Kirim). Boleh dicetak **kapan saja**, termasuk sebelum QC selesai —
  dengan catatan di dokumen bahwa angka QC masih bisa berubah.
- **Nomor punya seri sendiri** `SJ-CMT/{YYYY}/{MM}/{SEQ:4}`, diatur di Administrasi Sistem →
  Penomoran Dokumen, dan **IDEMPOTEN per penerimaan**: cetak ulang memakai nomor yang sama (arsip
  fisik harus bisa dicocokkan). No. SJ dari vendor tetap ditampilkan sebagai acuan.
- Kop & tanda tangan WAJIB mengikuti konfigurasi PDF yang sudah ada (Pengirim = vendor CMT,
  Pemeriksa QC, Penerima = Gudang DA). Nomor seri barang di-resolve dari master (`po_items` /
  `buyer_shipment_items`) karena baris penerimaan tidak menyimpannya.
- Dijaga gate **INV-F33** (`scripts/verify_surat_jalan_cmt.py`).

## Ambang & Alert Stok — aturan yang DIPUTUSKAN PEMILIK (2026-08-21, sesi #29c, W3)
- **SATU definisi "stok rendah"** untuk seluruh sistem (`core/stock_thresholds.py`): ambang dibaca
  `min_stock_qty` → `min_stock` (legacy) → `min_stock_percentage`; `reorder_point` = titik pesan
  ulang (peringatan kuning), pelanggaran ambang minimum = kritis (merah). Stok SELALU on-hand
  kanonik (`stock_service.onhand_map`), bukan `SUM($qty)`.
- Pembaca yang WAJIB memakai definisi itu: layar Alert & Reorder, notifikasi/bel, dashboard
  low-stock & reorder-alerts, serta rumus usulan smart-reorder. Tidak boleh ada definisi keempat.
- **Ambang diisi di Master Item → tab "Ambang Stok"**, bisa massal, dengan **usulan dari pemakaian
  NYATA 30 hari** (`avg pakai/hari × lead time`, titik pesan ulang + penyangga 20%). Material tanpa
  pemakaian **tidak diberi usulan** — sistem tidak menebak.
- **Layar wajib jujur**: bila ambang belum diisi, layar Alert & Reorder TIDAK boleh berkata "semua
  normal"; ia harus menyebut berapa material yang belum berambang dan mengarahkan pengisiannya.
- Dijaga gate **INV-F34** (`scripts/verify_alert_stok_hidup.py`).

## Satuan Gulungan · Style Potongan · Harga Satuan — aturan pemilik (2026-08-21, sesi #30)
- **Satuan gulungan kain = satuan aslinya.** Yard tetap yard, rol tetap rol, kg tetap kg. Sistem
  TIDAK boleh memaksa apa pun menjadi meter. Konversi ke meter hanya boleh tampil sebagai **info
  tambahan** ("97,50 yard ≈ 89,15 m"). Nama field warisan `length_m`/`remaining_m` BUKAN penanda
  satuan — satu-satunya sumber satuan adalah `uom` (lihat `core/fabric_roll_engine.with_display_uom`).
- **Pengeluaran gulungan wajib memakai satuan gulungan itu sendiri** (satuan lain ditolak 400).
- **Style/produk pada order cutting WAJIB dari Master Produk** (`rahaza_models` + varian), karena BOM
  disimpan per model+size dan produksi harus tahu potongan ini milik produk yang mana. Ketikan bebas
  tidak diterima, tetapi dialog cutting menyediakan tombol **"Model Baru"** untuk style yang belum
  terdaftar.
- **Harga satuan (HPP) TIDAK diketik di Master Item.** Harga terbentuk otomatis sebagai
  **rata-rata bergerak dari harga pembelian** (PO → Penerimaan Barang), untuk kain maupun aksesoris.
  Master Item hanya boleh mengisi **harga awal** saat barang pertama kali didaftarkan (barang lama
  tanpa pembelian, ditandai `cost_method="opening"`). Koreksi manual hanya lewat **Valuasi HPP**
  (bernilai audit).
- Dijaga gate **INV-F35** (`scripts/verify_uom_roll_dan_style_master.py`).

## HPP BATCH (FIFO) · BIAYA JAHIT SPK · IMPOR PINTAR · PORTAL LUAR — aturan pemilik (2026-08-23, sesi #34)
- **Biaya jahit DIINPUT di SPK, per SKU per pcs.** Staf mengetik tarif; sistem yang mengalikan qty
  (total baris + total SPK). Tersimpan di `po_items.cmt_price_snapshot` (SSOT lama) + jejak
  `cmt_price_set_by/at`. Layar: **Biaya Jahit** (`prod-sewing-cost`). Usulan tarif hanya boleh dari
  data nyata (SPK sebelumnya / master partner CMT), **tidak boleh angka karangan**.
- **HPP barang jadi = FIFO per batch.** Lapisan lahir di SATU pintu
  (`core/production_qty_ledger.post_fg_accepted`) saat FG lolos QC masuk gudang; isinya bahan (BOM) +
  jahit (SPK) + permak + upah internal, plus `gaps[]` untuk komponen yang belum diketahui (tidak
  pernah ditebak). **Angka yang dipakai layar = rata-rata TERTIMBANG lapisan yang masih bersisa**
  (`hpp_fifo_avg`), didampingi `hpp_last_batch`. `hpp_source` wajib menyebut `fifo_batch` (biaya
  nyata) vs kalkulator BOM (perkiraan) — dua arti ini sengaja dibedakan.
- **Portal luar (Kreator/KOL & Live Host) TIDAK BOLEH melihat biaya.** Hanya harga jual & stok.
  Penyaringnya **daftar PUTIH** field (`marketing_kol_portal.CREATOR_CATALOG_FIELDS`), bukan daftar
  hitam. Katalog kreator dibaca dari SSOT `marketing_catalog_items` (bukan koleksi terpisah).
- **Kreator punya 3 tipe**: `new` (belum berakun portal, datanya diinput staf marketing), `kontrak`,
  `continue`. Hanya kontrak & continue dapat **insentif**: Rp per pcs dan/atau bonus target,
  dikonfigurasi per kreator, **periode default 3 bulan**. **Pcs terjual diinput STAF MARKETING**.
  Tutup periode ⇒ hitungan kembali 0 (periode baru mulai BESOK) tanpa menghapus entri lama.
- **Live host digaji BULANAN lewat payroll HR**, bukan per sesi. Nominal dibaca dari
  `rahaza_payroll_profiles.base_rate` via `livehost.employee_id` (`core/livehost_salary.py`). Upah
  per-sesi dinolkan (`legacy_pay` menyimpan nilai lama); **log aktivitas live tetap disimpan** untuk KPI.
- **Periode anggaran marketing = 7 hari (default)**, kunci `YYYY-MM-DD` (tanggal mulai); mode
  **1 bulan** (`YYYY-MM`) tetap sah dan bisa dipilih di `/api/marketing/budget/period-settings`.
  Semua pembaca periode WAJIB menerima kedua bentuk (`core/marketing_cycle.valid_period`).
- **Impor data marketplace**: manusia tetap MEMILIH jenis data; sistem hanya **melaporkan** platform
  (dari sidik kolom berkas), peringkat kecocokan jenis, dan peringatan bila pilihan kemungkinan salah
  — beserta bukti jumlah kolom. Layar pemetaan **mengacu kolom TEMPLATE sistem** (satu baris per
  kolom sistem, pilih kolom berkas pengisinya) dan wajib menampilkan **viewer 10 baris isi berkas**.
- **Pencairan marketplace**: portal Marketing **hanya melihat**; input & jurnal milik Finance.
- Dijaga gate **INV-F39** (`scripts/verify_biaya_jahit_hpp_batch_impor_pintar.py`).

## Sesi 2026-08-24 (#35) — KPI KONTEN PER KONTEN + RAPOR KREATOR MINGGUAN

Aturan produk yang sekarang berlaku (wajib diingat lintas sesi):
* **KPI konten dibaca dari SATU layar** (Portal Marketing → Kalender Konten → tab "Performa
  Konten") dengan 5 sudut pandang: **per konten** (`GET /performance/contents`) · per kreator ·
  per jenis · per toko · per platform (`GET /performance?group_by=`). Rekap kelompok dan daftar
  per-konten WAJIB memberi total views yang sama (dijaga INV-F40 A6).
* **KPI konten diisi MANUAL** oleh staf marketing lewat `POST /content-calendar/{id}/kpi`
  (dialog `ContentKpiDialog`). **Tanpa `published_url` → 400.** Angka turunan (engagement,
  eng. rate, CVR, GMV/view, AOV) selalu dihitung SERVER; jangan pernah menyimpan hasil ketikan.
* **Baris tanpa KPI tidak boleh disembunyikan** — itu daftar kerja. Filter `kpi_state`.
* **Rapor kreator = 7 hari BERGULIR** (`core/creator_weekly_report.build_report`). Nominal
  insentif **DIBACA** dari `routes.marketing_kol_incentive._summary` — JANGAN pernah menghitung
  ulang insentif di rapor (dua angka rupiah = dua kebenaran). GMV KPI platform dan omzet pesanan
  (`marketing_orders.creator_id`) tetap DUA kolom, tidak pernah dijumlah.
* **Pengiriman rapor idempoten per (kreator, pekan)**; SMTP kosong ⇒ `skipped_no_smtp` (rapor tetap
  tersimpan & terbaca kreator), tanpa email portal ⇒ `no_email`. WhatsApp sengaja tidak dipakai
  (penyedia berbayar).
* **Portal kreator tetap bebas HPP/margin** — termasuk di rapor mingguan (`my-weekly-report`).
* ⚠️ **Daftar id hasil penyaringan lingkup toko: `[]` berarti TIDAK ADA yang boleh dilihat, bukan
  "semua".** `if ids:` pernah membuat staf tanpa lingkup toko melihat seluruh kreator (ditangkap
  INV-F6RBAC B2-SWEEP). Pakai `ids is not None`.
* Gate: `scripts/verify_kpi_konten_rapor_mingguan.py` (**INV-F40**, 17 invarian) di `gate.sh`.
  Total gate: **63**.
* **Audit #35b (2026-08-24):** jalur TULIS wajib berpagar lingkup toko juga — jangan pernah
  menganggap "layar bacanya sudah disaring" cukup. Masukan KPI dijaga batas kewajaran
  (tidak negatif · CTR 0–100 · engagement ≤ 3× views · engagement tanpa views ditolak), field
  yang tidak dikirim TIDAK ditimpa nol, daftar terpotong WAJIB mengaku, layar kosong karena
  kewenangan WAJIB berbeda bunyinya dari kosong karena data, dan pekan masa depan tidak boleh
  bisa dibuka. Semua dijaga INV-F40 (24 invarian).

## Sesi 2026-08-24 (#36) — IMPOR MASTER DATA (migrasi)

* Master WAJIB (urut): lokasi → karyawan(+payroll) → warna → ukuran → proses → kain/benang →
  **aksesoris** → model → barang jadi(SKU) → **BOM** → vendor/klien → akun toko → katalog jual →
  KOL → livehost. Template: `data_import/TEMPLATE_MASTER_DA.xlsx`
  (`scripts/master_template_generate.py`), importir: `scripts/import_master_template.py`.
* **Aksesoris punya master sendiri dan IKUT BOM** — kancing/label/hangtag bagian nyata HPP.
* Importir: **dry-run bawaan**, `--apply` dua tahap (validasi penuh dulu ⇒ tidak ada impor
  separuh), idempoten via kode, tidak menghapus data lama, referensi silang dalam satu berkas
  dikenali, setiap dokumen ditandai `import_batch`.
* **TIDAK lewat Excel**: password portal kreator/livehost, saldo awal (stok/piutang/kas),
  CoA (sudah terpasang).
* ⚠️ **Penomoran dokumen**: penyemai/impor yang menulis dokumen bernomor langsung TIDAK menaikkan
  pencacah ⇒ dulu memicu 500 `E11000`. `gen_prefixed_number()` sekarang menyembuhkan diri
  (deteksi tabrakan → dorong pencacah ke max nyata → ulang). Jangan pernah membuat generator
  nomor kedua.
* Gate: INV-F41 (22 invarian). Total gate: **64**.

## Sesi 2026-08-24 (#36b) — AUDIT PERMINTAAN AWAL + keputusan untuk sesi #37

Hasil audit (bukti angka, bukan klaim):
* **RnD logikanya BENAR** — diuji e2e: style→varian→approve→promote menghasilkan SKU kanonik
  `MODEL-WARNA-UKURAN`, FG tertaut model/ukuran/warna, `rahaza_model_variants` terbentuk,
  `rnd_style_id` terbaca viewer. Idempoten, kode kembar ditolak 409. Yang kosong hanya DATA
  (styles 0, BOM 2, seed usang) — pemilik menyatakan itu tidak masalah.
* Viewer RnD mengembalikan kunci **`data`** (bukan `rows`).
* Sudah benar: biaya jahit SPK · anggaran 7 hari · impor pintar · portal KOL tanpa HPP ·
  livehost bulanan · KPI konten. Belum: **pencairan (tidak ada form)** & **margin katalog**.
* HPP Rp 0 di 318 FG karena `po_items` tidak tertaut master (7/7 tanpa `material_id`) dan BOM
  hampir kosong — akibat seed usang, bukan rumus salah.

Keputusan pemilik untuk sesi #37 (detail: `memory/HANDOFF_SESI_37.md`):
1. Form pencairan **di Portal Finance**; Marketing baca-saja.
2. Pencairan dicocokkan ke omzet periode + **selisih disebut**, dan **membuat jurnal** kas masuk +
   potongan platform. ⚠️ **OMZET TIDAK PERNAH MASUK GL — hanya pencairan.**
   ⚠️ Jurnal WAJIB memakai **COA milik akun toko** (`marketing_accounts`: `coa_cash_code`,
   `coa_revenue_code`, `coa_receivable_code`), bukan peta COA global di `marketing_settlements.py`.
3. Sinkron RnD → katalog marketing tetap **manual** (tidak diubah).
4. **Margin dihitung otomatis**; bila HPP tidak diketahui tampilkan "belum bisa diukur", bukan 0%.
5. Impor **22 jenis → ±6 kelompok** (jenis lama tetap diterima, hanya disembunyikan/deprecated).
6. 6 kolom harga katalog **by design** untuk pencatatan RnD — jangan disatukan.


## Sesi 2026-08-26 (#38) — COGS PENGIRIMAN MEMAKAI BIAYA BATCH NYATA + PEMULIHAN CONTAINER

* **Satu angka rupiah, satu kebenaran.** Jurnal COGS pengiriman buyer sekarang memakai **biaya batch
  FIFO yang benar-benar keluar** (`fg_cogs` di baris pengiriman), bukan snapshot HPP per SPK.
  Urutan dasar: `fifo_batch` → `hpp_snapshot`; dasarnya **selalu disebut** di hasil (`basis`) dan di
  memo jurnal. Tanpa keduanya ⇒ TIDAK ada jurnal (bukan Rp 0 karangan).
* Nilainya dipecah ke akun **bahan · upah (jahit+permak+internal) · overhead** dari `breakdown`
  lapisan, diskala supaya Σ komponen == `fg_cogs`. Lapisan tanpa rincian masuk BAHAN + disebut di
  `gaps[]`. `uncosted_qty` (keluar tanpa lapisan biaya) **wajib dilaporkan**, tidak pernah ditutup.
* Pintu layar: kolom **HPP Batch (FIFO)** + total per dispatch di Riwayat Dispatch
  (*Serah Terima FG → Buyer Shipment*). Baris lama tampil **"—"**, bukan Rp 0.
* Gate **INV-F44** (10 invarian, stok-netral) termasuk J10 yang menempuh pintu nyata
  (lapisan masuk → stok masuk → dikirim → jurnal). Total gate: **65**.
* ⚠️ **Penjaga "sudah ter-seed" jangan berambang 1.** Satu karyawan sisa penyemai lain membuat
  `bootstrap.sh` melewati seluruh seed HR ⇒ 5 akun peran tanpa `employee_id` ⇒ absen/cuti/payslip
  35 kegagalan. Ambang sekarang ≥5.
* ⚠️ **Penyemai wajib menyaring lewat NAMA/identitas nyata, bukan KODE.**
  `seed_internal_variants.py` melahirkan warna kembar (BLK vs HTM) + 165 varian bayangan.
* ⚠️ **Alat ukur bisa salah tanpa kodenya salah.** 6 dari 17 gate merah adalah gate yang memaku id
  vendor, memilih data yang tidak layak uji (kreator tipe `new`, katalog tanpa tautan FG), atau
  mengukur tumpang tindih PDF lintas halaman. Periksa klaim gate — tanpa melunakkan invariannya.
* `memory/test_credentials.md` diisi lengkap (11 akun internal + 2 portal luar + catatan rate-limit).

## Sesi 2026-08-26 (#40) — AUDIT PORTAL MARKETING (tanpa perbaikan, atas permintaan pemilik)
Hasil lengkap: `memory/TEMUAN_AUDIT_MARKETING_SESI40.md`.
* 12 gate marketing **HIJAU**; alur impor (deteksi → unggah → pratinjau → commit → UNDO) diuji
  ujung-ke-ujung dengan 7 berkas ASLI pemilik + Ekspor B/C sintetis: **46 pemeriksaan OK**.
  Jalur `update_only` + rollback (perbaikan sesi #38/#39) TERBUKTI bekerja.
* **Temuan P0**: layar "Impor Data" langkah 1 kosong tanpa kata kunci (`setGroupKey` &
  pemilih 6 kelompok tidak pernah dirender) dan **deteksi otomatis jenis/platform sesi #34 tidak
  punya pintu di layar** (`/detect` & `/source-groups` tidak dipanggil frontend sama sekali).
* **Temuan P1 (uang/data)**: pencairan uji `SET-TEST-001` + jurnal POSTED `JE-20260820-0001`
  (Rp 10,1 jt) dan 559 pesanan uji TikTok Outfit Boutique tertinggal di data nyata.
* **Dikerjakan sesudah persetujuan pemilik (hari yang sama):** langkah 1 wizard impor dipulihkan
  (6 kartu kelompok + panel **deteksi otomatis** yang membaca berkas lalu mengusulkan jenis beserta
  buktinya), pencairan uji `SET-TEST-001` + jurnal POSTED-nya **di-void & dihapus**, dan 559 pesanan
  uji **di-rollback** (rekap harian turunan ikut nol). Gate baru **INV-F45** (27 invarian) di
  `gate.sh` menjaganya. Sisa temuan: T-5 (dua verifier ad-hoc perlu dibuat idempoten).
* Aturan baru: **pencairan yang jurnalnya sudah VOID tidak lagi terkunci** — `_je_still_binding()`
  di `routes/marketing_settlements.py` adalah SATU tempat aturan itu ditulis (dipakai PUT, DELETE,
  dan `can.edit/journal` di layar detail).

## Session log — Iter 106 (2026-09-04, lanjutan repo `ajjshsbsgdg/DA`): Portal Maklon Fix #3 cancel-path + LOW items
Konteks: iterasi 105 memverifikasi Fix #1 (RBAC), #2 (status sync), #4 (AR selling price); Fix #3 (satu sumber invoice) TERBLOKIR — cancel meninggalkan dokumen `dewi_maklon_invoices` ber-status `cancelled` dgn id/nomor SAMA dgn AR ⇒ generate ulang 500 `DuplicateKeyError invoice_number`.
Dikerjakan:
- `routes/dewi_maklon_billing.py::cancel_invoice`: untuk invoice `source=engine_ar` → AR dikembalikan ke `draft` (amount_paid 0, amount_due = total, issued_at/issued_by null), cermin dewi + payments DIHAPUS (bukan `cancelled`), mirror `dewi_maklon_pos` di-sync ulang (status kembali partial_delivered/completed). GL sudah posted → 400 tetap.
- `_generate_from_engine_ar`: idempoten — hapus sisa doc `cancelled` yang memakai id/nomor AR lalu `replace_one(upsert)`; AR `issued` YATIM (tanpa doc aktif, belum bayar, belum GL) boleh diterbitkan ulang (self-heal DB lama).
- `data/doc_number_registry.py`: `production_pos.po_number_maklon` default_mode `manual` → `auto` (PO-MKL-{YYYY}{MM}-{SEQ:4}). FE `ProductionPOModule` sudah membaca kebijakan via `/doc-number-policy`, jadi kolom nomor otomatis disembunyikan.
- `tests/test_iter105_maklon.py`: PO test tanpa `po_number` (auto), endpoint 360 memakai `po-mk-demo-2` (po-mk-demo-3 tidak ada di seed bootstrap). 46/46 PASS.
- Konfirmasi LOW #4: `po-mk-demo-2` = PT Aruna Activewear pada seed `/api/seed/maklon-full` (CV Bumi Sportwear di iter 105 adalah sisa DB lama).
- `memory/test_credentials.md` diisi (admin, 5 role, klienmaklon, cmtvendor).
Verifikasi curl: generate → id/nomor = AR (INV-MKL-2026-0001), qty 60 (received, bukan 100), total 799.200 = 720.000×1,11; payment 100k → AR amount_paid 100k & dewi partial_paid; delete payment → issued; cancel → AR draft, 0 dewi doc, mirror partial_delivered; regenerate → 200 id/nomor sama; cancel lagi bersih.
- Iter 106 testing agent: 64/64 backend PASS (test_iter105 46 + test_iter106 18), UI/portal regression bersih. Tindak lanjut LOW: `GET /api/doc-number-policy?key=dewi_maklon_invoices.invoice_number` kini mengisi {PREFIX} dari config `maklon_invoice_prefix` (pratinjau "INV-MKL-2026-000x", bukan "PRE-2026-0001"). Sisa LOW belum dikerjakan: input login portal klien (/klien-maklon) belum punya data-testid.

## Session log — Iter 107 (2026-09-04): AUDIT Portal Finance & Akunting (temuan saja, tanpa eksekusi)
- Laporan: `memory/AUDIT_FINANCE_AKUNTING_2026-09-04.md` — 6 CRITICAL, 10 HIGH, 9 MED, 5 LOW + daftar yang terbukti aman + urutan perbaikan.
- Alat audit ulang: `backend/scripts/audit_finance_integrity.py` (read-only) & `backend/scripts/audit_finance_live.py` (transaksi uji + cleanup).
- Temuan utama: subledger AR/AP dibuka di akun anak & ditutup di kontrol (C-01); AP-dari-GR ke 6-2200 Listrik & Air + AP dobel (C-02); biaya jahit CMT dobel & FG negatif (C-03); Neraca tak seimbang krn tipe CURRENT_ASSET/OTHER (C-04); profil asset_disposal salah akun (C-05); pendapatan/pembayaran maklon tidak ke GL (C-06).
- DB dikembalikan bersih (8 JE seed, po-mk-demo-2 partial_delivered, AR draft).

## Session log — Iter 108 (2026-09-04): EKSEKUSI 4 perbaikan audit finance (C-01, C-02, C-04/C-05/H-04, C-06)
Keputusan pemilik: (1) skema akun **4-digit kanonik**, legacy 3-digit neraca yang belum pernah dipakai jurnal **dinonaktifkan** (tidak dihapus); (2) GRNI = akun baru **`2-1150 Hutang Belum Ditagih (GRNI)`** di bawah `2-1000`.
- **COA kanonik** (`rahaza_coa.py`): akun baru 2-1150 GRNI, 1-1303 Piutang Platform OS, 1-1304 Piutang COD, 2-1700 Uang Muka Diterima Maklon, 6-2900 Beban Umum & Lain-lain, 5-3500 Overhead Pabrik Umum; `1-1320` tipe ASSET; `7-0000` OTHER_INCOME; pengecualian G4 (11 akun 4-digit tak di-seed) DICABUT. `LEGACY_CODE_MAP` (3-digit→4-digit) + `migrate_coa_canonical()` (idempoten, dijalankan saat startup & `POST /api/rahaza/coa/migrate-canonical`): normalisasi tipe, perbaiki parent, nonaktifkan 66 akun legacy 1-/2-/3-xxx yang tak terpakai (yang dipakai jurnal/cash account hanya diberi flag `legacy_used_in_journal`), remap `rahaza_channel_gl_mapping` & parent Auto-COA channel (1-220→1-1303). Akun P&L DA 3-digit (4-1xx channel, 5-231/7-120 CMT, 8/9-xxx) TETAP aktif (bukan duplikat).
- **Posting profiles** (`rahaza_posting_profiles.py`): DEFAULT_PROFILES semua 4-digit; `PROFILE_CODE_FIXES` + `upgrade_posting_profiles()` (idempoten, startup): asset_disposal → 1-2500/1-2501; inventory_receive.credit_ap_clearing → 2-1150; ap_invoice.debit_grni=2-1150, debit_expense_default 6-2200→6-2900; ar_invoice.debit_sales_discount → 4-1300; credit_note.debit_revenue → 4-1200; default kas AR/AP/expense/kasbon → bank 1-1201; `/seed-da` profil → **410**.
- **Posting engine** (`rahaza_posting.py`): SEMUA fallback kode akun hard-code dihapus (mapping kosong = error "belum lengkap"). C-01: `post_ar_invoice`/`post_ap_invoice` menyimpan `gl_ar_account_code`/`gl_ap_account_code`; `post_ar_payment`, `post_credit_note`, `post_bad_debt_writeoff`, `post_ap_payment` memakai `_ar_account_for_invoice/_ap_account_for_invoice` (kolom tersimpan → jurnal penerbitan → kontrol). CN tanpa invoice asal → resolusi subledger customer/channel yang sama dgn penerbitan.
- **Maklon → GL otomatis** (`dewi_maklon_finance.py`, `dewi_maklon_billing.py`): generate invoice (engine AR & legacy) → `post_maklon_ar_invoice` (nilai & tanggal = AR final; tolak AR draft; void+re-post bila nilai berubah); `POST /payments` (+`cash_account_id` opsional) → `post_maklon_payment` (Dr bank cash account / Cr akun AR penerbitan + `rahaza_cash_movements` + saldo kas); `DELETE /payments/{id}` → void JE + hapus mutasi kas; `cancel` → void JE penerbitan, AR draft (bukan lagi ditolak "sudah GL"). `post-ar` manual → 400 bila AR draft. UI PaymentDialog: select "Rekening Kas/Bank Penerima" (`pay-cash-account-select`).
- **GRNI** (`warehouse.py`, `rahaza_ap_from_gr.py`): GR status `received` kini memposting `Dr 1-1401 / Cr 2-1150` per baris (qty × unit_price) — sebelumnya GR tidak pernah ke GL; AP-dari-GR `gl_debit_code=2-1150` → `Dr 2-1150 / Cr 2-1100` (bukan 6-2200); fallback `unit_price` utk GR manual (bug total AP 0).
- **Neraca** (`rahaza_fin_reports.py`): `_bs_type()` memetakan tipe legacy/tak dikenal, akun nonaktif bersaldo tetap ikut, `type_warnings` di respons.
- Hard-code lain: `dewi_kasbon` (kunci role kanonik), `marketing_accounts` default 1-1201/1-1303, `asset/_accounts.py` FALLBACK cash 1-1201 & ap_clearing 2-1150, `employee_expense_claims` kredit default dari profil `expense`, `channel_gl_mapping` 1-1303/1-1301, `coa_auto` parent channel 1-1303.
- Uji: `backend/scripts/verify_finance_fixes.py` (uji nyata end-to-end, cleanup sendiri) — FAILED:[]; testing agent iterasi 107: backend 100%. `audit_finance_integrity.py`: 0 profil akun invalid.
- BELUM (backlog audit): C-03 HPP jahit dobel/kapitalisasi WIP, H-01 unifikasi skema AR, H-02 payroll komponen, H-03 alur bayar CMT, H-05/H-06 kas & rekon bank, H-07 pendapatan PO internal, H-08 periode wajib, M-xx.

## Session log — Iter 108b (2026-09-04): Bayar Vendor CMT (H-03) · Satu Aging Piutang (H-01) · HPP Jahit Sekali (C-03)
- **Bayar CMT** (`dewi_maklon_finance.py`, hanya "pay" tanpa approve — keputusan owner): `POST /api/dewi/maklon/finance/cmt-payments/{id}/pay {cash_account_id, amount?, payment_date, reference_no}` → AP CMT auto-post bila belum, JE `ap_payment` Dr AP (akun sama dgn AP invoice via `gl_ap_account_code`) / Cr bank cash account, `rahaza_cash_movements` out, doc `dewi_cmt_disbursements`, status tagihan `partial_paid|paid`, tolak overpay/lunas. `GET …/disbursements`, `POST …/disbursements/{did}/void` (void JE, kembalikan kas & status). `production_cmt_billing._enrich` → `paid_amount/outstanding_amount`. UI `ProductionCMTBillingModule` panel "Pembayaran ke Vendor" (`cmt-pay-open/-cash-account/-amount/-submit`, daftar + Void).
- **Aging tunggal** (`rahaza_ar_canonical.py` baru): `canon()` (total_amount/amount_paid/amount_due ⇄ total/paid_amount/balance, sent→issued, customer_name⇄client_name, `source` internal|maklon), `migrate_ar_canonical()` startup idempoten, `compute_ar_aging(source)`. `/api/rahaza/ar-aging[?source=]` & `/api/dewi/maklon/reports/aging` membaca fungsi yang sama. `rahaza_finance` AR: create/payment/write-off dual-write kanonik, `send` → status `issued`, filter menerima `issued`. `dewi_maklon_billing._recalc_invoice` menulis cermin lama.
- **HPP absorption**: profil `cmt_ap_invoice.debit_cmt_wip_internal=1-1403` (PO internal → WIP; maklon tetap 7-120; `PROFILE_CODE_FIXES` upgrade DB). `post_wip_to_fg_on_job_complete` nilai = Σ `fg_cost_layers.batch.po_id` (bahan+jahit `cmt_price_snapshot`+permak+internal+overhead; layer ditandai `gl_job_id`), fallback MI+jahit, lalu HPP snapshot. `cmt_price_snapshot` di PO/SPK tidak diubah (hanya dibaca). Catatan: sisa WIP = selisih bahan BOM vs MI aktual + overhead yang belum di-accrue (belum ada jurnal variansi WIP).
- Uji: `scripts/verify_iter108.py` PASS; testing agent iterasi 108 lulus semua (backend + UI CMT Billing termuat).

## Session log — Iter 109 (2026-09-04): PEMULIHAN container dari GitHub `sjsidubdjd/da` + regresi ulang iterasi 108b
- Bring-up: rsync repo → /app (`.env` dipertahankan + `JWT_SECRET` ditambah), `pip install -r requirements.txt`, `yarn install` (lockfile diperbarui), `mongorestore backups/auto_20260902_190000`, `bash scripts/rebuild_frontend.sh` (build statis).
- Regresi permanen baru: `backend/tests/test_iter108_finance.py` (11 uji: bayar CMT parsial/lunas/tolak/void + AP CMT → 1-1403; aging tunggal internal+maklon + `/dewi/maklon/reports/aging`; WIP→FG Σ fg_cost_layers + already_posted; posting profile 1-1403/7-120; neraca balanced). Jalankan serial `-n 0`. Testing agent iterasi 109: backend 11/11 + 7/7, UI CMT Billing bayar Rp1.000 → JE → Void OK, layar Aging Piutang (fin-ar-360) total = API. 0 console error.
- Catatan data: backup berisi AR maklon `INV-MKL-2026-0003` draft vs mirror `INV-MKL-2026-0001` issued (warisan pra-H-01); uji melakukan cancel + `sync-maklon-finance` sebelum generate.
- Commit lokal `2a8aeb4` (di atas `564618d`). Push ke GitHub belum dilakukan (butuh kredensial / fitur Save to GitHub).
- Backlog berikutnya (dari audit finance iter 107): H-02 payroll komponen, H-05/H-06 kas & rekonsiliasi bank, H-07 pendapatan PO internal, H-08 periode wajib, jurnal variansi WIP.
