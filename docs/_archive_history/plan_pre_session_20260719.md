# plan.md — Garment ERP (Static Frontend) — MASTER DEV PLAN A–H + P0 Demo Seed

> **Env constraint (WAJIB):** Frontend **tidak boleh** jalan via CRA dev server (1 CPU / 2GB). Setelah perubahan apa pun di `frontend/src/**` **WAJIB** jalankan:
> `bash /app/scripts/rebuild_frontend.sh` lalu tunggu selesai (static bundle).
>
> **Ops constraint:** kerjakan & uji di **Preview** dulu. Promote ke Production hanya setelah user verifikasi.

---
---

---
---

## ✅ SESSION STATUS UPDATE (2026-07-18 — FRESH CLONE `da1807262` RESTORED + PHASE D VERIFIED)
> Fresh shallow clone from `github.com/pandekomangyogaswastika-dot/da1807262` restored into `/app`
> (env preserved: MONGO_URL / REACT_APP_BACKEND_URL untouched; added JWT_SECRET + EMERGENT_LLM_KEY;
> frontend GENERATE_SOURCEMAP=false + DISABLE_ESLINT_PLUGIN=true).
>
> **Bring-up done:** pip deps OK; `yarn install --prefer-offline` (frozen-lockfile drift → non-frozen,
> installs `@simplewebauthn/browser@^13.3.0` needed by `pages/AbsenPage.jsx`); static bundle rebuilt
> (`rebuild_frontend.sh`, HTTP 200); backend healthy; seeded `production-full` + `rahaza/seed-demo` +
> `maklon-full`; role accounts via `scripts/seed_role_accounts.py`. All 6 logins → HTTP 200.
>
> **LAST DEVELOPMENT VERIFIED — Phase D (Consolidated Buyer Shipment, multi-PO surat jalan):**
> - Frontend "per-PO breakdown" block (the checkpoint edit) confirmed present in
>   `BuyerShipmentModule.jsx` (data-testid `detail-per-po`, renders only when >1 distinct po_number).
> - Backend fully implemented: `_resolve_po_context` (po_ids, single-buyer guard), consolidated create,
>   per-item po_id/po_number, migration `2026_07_18_phase_d_backfill_buyer_item_po_id.py` (idempotent, 0 backfill).
> - `scripts/test_phase_d_e2e.py` → **ALL 4 scenarios PASS** (D1 1 SJ across 3 POs; D2/D3 independent
>   per-PO auto-close within one consolidated SJ; D4 mixed-buyer guard → 400).
> - Buyer Shipment module renders live in preview (login + module screenshot verified).
>
> **NEXT:** awaiting user direction on what to continue building.

## ✅ SESSION CONT (2026-07-18 — Phase D FRONTEND consolidated CREATE verified + ordered_qty polish)
> User asked to (1) continue Phase D — make the frontend "Konsolidasi multi-PO" CREATE UI work
> (was only proven via API), and (2) run full regression.
>
> **Finding:** the consolidated CREATE UI was ALREADY implemented in `BuyerShipmentModule.jsx`
> (toggle `consolidate-toggle`, `cons-buyer-select`, cross-PO receipt picker, per-PO item rows,
> consolidated submit branch). Verified END-TO-END in browser (Portal Maklon → "Dispatch Buyer CMT"):
> pick buyer → check 2 cross-PO Approved receipts → per-PO rows auto-built (cap = qty_actual) →
> Simpan → new consolidated SJ (po_id null, po_ids=[2], SJ-BYR-…) created; detail shows the
> "Rincian per PO" breakdown block.
>
> **BUG FIXED (display):** consolidated SJ showed "Total Order 0 / progress 0%" (per-item "Qty Order 0")
> because the consolidated create payload omits `ordered_qty` per line. Fix (backend, display-only,
> `ordered_qty` is NOT used in fulfillment/auto-close):
>   - `routes/buyer_shipment.py` create: `ordered_qty` falls back to origin `po_items.qty` when payload omits it.
>   - Migration `2026_07_18_phase_d_backfill_buyer_item_po_id.py`: added Section 3 backfilling
>     `ordered_qty` (0→po_item.qty) for existing items (idempotent). Ran: 11 items backfilled.
>   - Verified: new consolidated SJ total_ordered=Σ po_item qty, progress % correct; Phase D E2E still 4/4 PASS.
> **Helper:** `scripts/seed_phase_d_ui_demo.py [buyer] [--force]` seeds a clean multi-PO buyer with
> Approved un-dispatched receipts for exercising the UI. Test buyer: "PT Konsolidasi UITest".
>
> **NEXT:** testing_agent_v3 comprehensive (Phase D consolidated UI + full regression).

## ✅ REAL-USER TEST + INTERNAL VERIFY + CHECKBOX FIX (2026-07-18)
> User: test "purely like real user input" so errors at each click/action are detected; focus Portal Produksi (internal).
> - Confirmed Phase D is business-type AGNOSTIC → also works in Portal PRODUKSI ("Dispatch ke Buyer"). Seeded
>   internal scenario via `seed_phase_d_ui_demo.py "<buyer>" --biz internal` (internal POs need model_id+size_id — D3 rule).
> - testing_agent_v3 iter_115: Portal Produksi nav sweep 12/12 menus PASS (0 console/network errors); flagged consolidated
>   receipt-checkbox "not registering".
> - **BUG FIXED (frontend):** receipt checkbox `onChange` was async (awaited line-fetch BEFORE updating selection) →
>   checkbox stayed unchecked until fetch resolved (perceived dead click / double-click un-toggle; broke automation).
>   Fix in `BuyerShipmentModule.jsx`: `buildConsItems` pure helper + `toggleConsReceipt` now updates selection
>   OPTIMISTICALLY (synchronous) then fetches lines & rebuilds rows. Rebuilt static bundle.
> - testing_agent_v3 iter_116: **100%** — optimistic checkbox registers <300ms, internal consolidated CREATE end-to-end
>   (SJ-BYR-202607-0006), detail per-PO breakdown + Total Order 180 + 100% + received-summary-strip, single-PO regression
>   + 8/8 nav re-sweep all PASS.

## ✅ TESTED & VERIFIED (2026-07-18 — testing_agent_v3 iteration_114)
> Backend **100% (19/19)**, Frontend **100%** — 0 critical / 0 UI / 0 integration / 0 design bugs.
> Verified: consolidated CREATE UI end-to-end (toggle→buyer→cross-PO receipts→per-PO rows→Simpan→
> new SJ-BYR); detail shows per-PO breakdown + Total Order 180 (not 0) + 100% + "Fully Shipped";
> single-PO regression PASS; all 6 (+cmtvendor) logins 200; no frontend crashes. Phase D DONE.


## ✅ SESSION STATUS UPDATE (2026-07-18 — Phase C RESTORED, RE-VERIFIED & COMPREHENSIVELY TESTED — COMPLETE)
> **testing_agent_v3 (iteration_phase_c.json): Backend 100% (13/13), Frontend ~100% (renders + Close Short
> modal + K5 menu cleanup in Portal Produksi & Maklon & Vendor). ZERO critical/UI/integration/design bugs.**
> The single "partial" note was a test-harness navigation timeout on Portal Maklon; the Maklon nav cleanup
> (VENDOR CMT has 'Tutup PO (Closure)'; no 'QC & Reject'; no 'Laporan Defect') is code-verified in portalNav.js.
> **Phase A + B + C are all COMPLETE & VERIFIED. Awaiting user direction (promote to Production / next backlog).**

### (below) prior in-progress note, now superseded:
## ✅ SESSION STATUS UPDATE (2026-07-18 — Phase C RESTORED & BACKEND RE-VERIFIED)
> Fresh clone from repo `da180726` restored into `/app` (env preserved: MONGO_URL / REACT_APP_BACKEND_URL
> untouched; added JWT_SECRET + EMERGENT_LLM_KEY; frontend GENERATE_SOURCEMAP=false + DISABLE_ESLINT_PLUGIN=true).
> Deps satisfied (pip + yarn), backend healthy (`/api/health` ok), frontend static bundle rebuilt (HTTP 200),
> data seeded (`/api/seed/maklon-full` + `/api/dewi/seed-demo-full`).
>
> **Phase C code was already implemented in the repo and is now independently RE-VERIFIED on this container:**
> - Backend E2E `scripts/test_phase_c_e2e.py` → **4/4 scenarios PASS** (7 auto-close, 8 close-short AR-draft,
>   8b close-short + credit note draft, 9 K5 cleanup 410s + progress gate w/o defect mention).
> - Endpoints present: `POST /production-pos/{id}/close-short`, `GET /production-pos/{id}/fulfillment`,
>   `GET /production-pos/{id}/credit-notes`; 410 on `POST /material-defect-reports` & `POST /dewi/maklon/qc`.
> - Frontend `POClosureModule.jsx` present + registered; portalNav has `po-closure` ("Tutup PO (Closure)")
>   in Portal Produksi & Portal Maklon.
>
> **NEXT (paused checkpoint resumed):** run comprehensive `testing_agent_v3` for Phase C (backend + frontend
> regression), then fix any issues. This supersedes the stale "Phase C ⏳ MENUNGGU KONFIRMASI USER" note below.

---


## ✅ SESSION STATUS UPDATE (2026-07-17 — Phase B TESTING COMPLETE & VERIFIED)
> Fresh clone from repo `DA6565` brought up on this container (pip + yarn install, JWT_SECRET added,
> frontend static bundle rebuilt). Backend healthy, preview serving HTTP 200.
>
> **Phase B (CMT → DA → Buyer) is COMPLETE and independently re-verified:**
> - Backend E2E `scripts/test_phase_b_e2e.py` → **9/9 PASS** (now self-seeding = idempotent, re-runs clean).
> - Testing agent full regression → **backend 47/47 PASS, 0 critical bugs**; frontend components 100%.
> - Frontend manually verified via screenshots: admin *Portal Produksi → "Terima FG dari CMT"* (header +
>   blue Phase B banner + Draft/Submitted/Approved/Rejected tabs) and vendor *"Deklarasi Pengiriman ke DA"*
>   (green Phase B banner + "Deklarasi Kirim ke DA" button + SJ-CMT-DA shipment naming).
> - Small robustness fix in `routes/buyer_shipment.py`: the `source_receipt_ids` required-check now fires
>   BEFORE the generic M-1 "minimal 1 pcs" guard, so DA dispatch without source receipts always returns the
>   deterministic 400 `'source_receipt_ids'` error (GUIDELINE §12.2 scenario 4c) regardless of items[].
>
> Next: awaiting user direction (e.g., promote to Production, or start next backlog item).

---

## 🚨 SESSION CMT-FLOW (2026-07-16 — CURRENT PRIORITY, supersedes Master-Product-Refactor task list)

> **PRIORITAS TERTINGGI USER SAAT INI.**
> Sumber kebenaran: **`/app/memory/GUIDELINE_CMT_FLOW.md`** (WAJIB dibaca fresh agent).
>
> Domain: Produksi + Maklon vendor-CMT flow (T1..T4 variance handling).
> Bug utama: additional shipment tidak masuk ke jobs production (RCA di §9.2 dokumen guideline).
> Restructure: CMT saat ini langsung ship ke buyer — harus CMT → DA → Buyer.

### Phase A — Bug fix additional shipment (✅ SELESAI 2026-07-16)
- **RCA grounded** di `vendor_shipment.py:414` (guard `status='Received'` race condition).
- **Fix APPLIED**: A1 buang guard + auto-promote status, A2 retro-hook di update, A3 extract helper.
- **Repro empiris**: `verify_phase_a.py --expect buggy` → confirmed bug; `--expect fixed` → confirmed fix.
- **Migrasi**: `/app/backend/scripts/migrations/2026_07_16_phase_a_self_heal_child_jobs.py` — idempotent 3x verified.
- **Test**: `testing_agent_v3` iteration_110.json = **96% (25/26)**, 0 critical, 0 medium.
- **Acceptance**: 6/7 criteria PASS (ac4 frontend deferred ke Phase B/C).
- **Change Log**: `/app/memory/GUIDELINE_CMT_FLOW.md` §15.

### Phase B — Restructure CMT → DA → Buyer (⏳ MENUNGGU KONFIRMASI USER)
- **Model transisi**: reuse `buyer_shipments` + field `receiver_type` (`'da'` | `'buyer'`), auto-create draft `cmt_receipts` saat vendor create receiver_type='da'.
- **Role gate**: `POST /buyer-shipments` deny vendor kalau receiver_type='buyer'.
- **UI baru**: `DAReceiveFromCMTModule.jsx` (DA-admin isi qty_actual + reject_qty + photos).
- **AP hook**: `production_maklon_bridge.mature_ap_from_cmt_receipt()`.
- **Test**: `testing_agent_v3` skenario §12.2.

### Phase C — PO closure + K5 cleanup (⏳ MENUNGGU KONFIRMASI USER)
- Auto-close 100%: `Σqty_received ≥ Σqty_ordered` → status=Completed.
- Manual close short: enum `deadline_expired` | `buyer_material_shortage` | `cmt_quality_reject_final` | `mutual_agreement` + credit note draft.
- K5 cleanup: buang `material_defect_reports` sebagai gate produksi, buang `dewi_maklon_qc_checks` stage-based (return 410).
- **Test**: `testing_agent_v3` skenario §12.3.

### File referensi (WAJIB baca di awal sesi berikutnya)
1. `/app/memory/PREVIEW_STABLE_MODE.md` — env constraint 2GB/1CPU.
2. `/app/memory/test_credentials.md` — akun admin/role.
3. `/app/memory/GUIDELINE_CMT_FLOW.md` — SSOT map + phase spec + testing contract.
4. `/app/memory/PRODUKSI_E2_QC_RETUR.md` — konteks QC/return decisions (K5 di guideline sudah rangkum).
5. `/app/memory/MAKLON_PO_DUAL_FLOW_MAPPING.md` — Engine vs Legacy Dunia B.

### Status kode saat ini
- **BELUM ADA PATCH.** Semua Phase A/B/C masih proposal — menunggu jawab user atas 5 pertanyaan konfirmasi di chat 2026-07-16.
- Guideline lengkap sudah ditulis, grounded ke line-number kode nyata.
- Effort gate: GRADE A.

### Task pending untuk fresh agent sesi berikutnya
1. Baca `GUIDELINE_CMT_FLOW.md` utuh.
2. Cek user sudah konfirmasi 5 pertanyaan (lihat pesan chat terakhir agent sebelumnya) — kalau ya, mulai Phase A. Kalau belum, tanya lagi.
3. Reproduksi Bug A empiris via curl SEBELUM patch (KNOWN LIMITATION di §15 guideline).
4. Patch → migrasi → testing_agent_v3 → update Change Log di guideline.



## 🧩 SESSION MASTER-PRODUCT-REFACTOR (2026-07-16) — Varian/SKU + Material/BOM Generalisasi ⏳ ACTIVE

> **Sumber kebenaran:** `/app/PROPOSAL_MASTER_PRODUCT.md` (disetujui user).
> **Keputusan user terbaru (klarifikasi sesi ini):**
> - Urutan: **Fase 1 → 2 → 3 → 4** (Rupiah & CRUD CMT ditunda sampai Master Product 100%).
> - Warna: **master DINAMIS** (`rahaza_colors`, bisa tambah/hapus via UI) — di-seed palet standar techpack. (revisi dari proposal poin #2 yang statis)
> - Format SKU: `KODE-WARNA-SIZE` memakai **kode/singkatan warna** (mis. `RZ001-MRH-L`).
> - Minimalisir input manual: pakai dropdown/selector.

### Fase 1 — Material & BOM Generalisasi ✅ DONE (backend + FE, rebuilt)
- Backend: `rahaza_material_categories` master configurable (seed 7 kategori) + field `category`/`category_name` di `rahaza_materials`.
- BOM: `rahaza_bom.py` dukung `color` (BOM per-varian; `color=""` = umum) + `category` di item materials.
- DB index: `rahaza_boms` → `model_size_color_active_unique` (server.py).
- Frontend: `RahazaMaterialsModule.jsx` (dropdown kategori), `RahazaBOMModuleV2.jsx` (passthrough category dari master + field color di payload). **Rebuilt OK (HTTP 200).**

### Fase 2 — Varian & SKU ✅ DONE & VERIFIED
- Master baru: `rahaza_colors` (DINAMIS, CRUD) `{id, code, name, hex, active}`; seed 15 warna palet techpack (lazy).
- Master baru: `rahaza_model_variants` `{id, model_id, size_id, size_code, color_id, color_code, color_name, sku UNIQUE, active}`.
- SKU auto: `{model.code}-{color_code}-{size_code}` (mis. `DA-PL03-HTM-L`), unik via index (partial active).
- Generator matriks varian (pilih warna × size → SKU otomatis, idempoten).
- PO Internal: item pilih `rahaza_variant_id` (atau alias `variant_sku`) → size/color/sku/color_code TERISI OTOMATIS (create & edit). Input bebas size/warna/sku jadi read-only utk internal.
- Backend baru: `routes/rahaza_variants.py` (colors + variants + generator). Index di server.py.
- FE: tab **Varian** + **Warna** di `RahazaModelsAndBOMModule` (`RahazaVariantsModule.jsx`, `RahazaColorsModule.jsx`). PO picker di `ProductionPOModule.jsx`.
- **Verifikasi:** testing_agent iteration_108 (backend 20/21, 0 bug kritis) + curl (alias variant_sku, edit flow) + screenshot UI (tab Varian/Warna, PO varian picker). Rebuilt OK.

### Fase 3 — Maklon & Marketing selaras varian ✅ DONE & VERIFIED
- **Maklon** (`dewi_maklon_buyer_catalog`): embedded `variants[]` ber-SKU. Generator dari `color_options × size_options` → SKU `{artikel_code}-{color_code}-{size_code}` (color_code cocok ke palet `rahaza_colors` mis Hitam→HTM/Navy→NVY, else 3 huruf). `buyer_ref_code` manual per-varian. Idempoten. Endpoint: `POST .../variants/generate`, `PUT .../variants/{id}`.
- **Marketing/Toko** (`marketing_catalog_items`): tambah `variant_id` FK → `rahaza_model_variants`. Auto-isi `variant_sku`, `model_id`, `variant_info` ("Warna: X, Size: Y"). Berlaku di create & update.
- FE: tab **Varian** di `MaklonBuyerCatalogDetailDialog`; picker "Tautkan Varian Produksi" di `CatalogManagementModule` (Marketing) & `TokoProductCatalogModule` (Toko).
- **Verifikasi:** testing_agent iteration_109 (backend 14/15, 0 kritis) + screenshot UI (tab Varian Maklon, picker Marketing). Data uji dibersihkan.

### Fase 4 — Migrasi caller/laporan + legacy ✅ DONE
- BOM **color-aware** di semua caller: `_active_bom(model,size,color)` (adapter), `production_execution.py`, dan `operations_pdf._aggregate_bom_for_po` (sudah color-aware sebelumnya). Prioritas: BOM spesifik-warna → BOM umum (color kosong) → BOM apa pun (last resort). Tanpa regresi (semua BOM saat ini color="").
- Legacy `products`/`product_variants`: TIDAK di-drop (keamanan data), sudah tidak dipakai alur internal (SSOT = `rahaza_model_variants`).
- **Master Product Refactor (Fase 1→4) SELESAI 100%.**

### Backlog ditunda (siap dikerjakan berikutnya)
- [P1] CRUD Edit/Hapus di Manajemen CMT (`VendorAccountsAdminModule.jsx`).
- [P2] Format angka Rupiah global (parsing `Rp 150.000` → 150000).

---


## 🤖 SESSION WS-B (2026-07-15) — AI Workstream (c → a → d → b) ✅ DONE & VERIFIED

User: "kerjakan semuanya satu per satu" (audit AI, Executive AI, Admin gear, ReportsHub). LLM = EMERGENT_LLM_KEY (Claude via wrapper).

### (c) Audit & Sentralisasi AI ✅
- **Root gap ditemukan & diperbaiki:** `services/ai/llm_client.py::call_claude` dulu memanggil `emergentintegrations.LlmChat` LANGSUNG (tak tercatat, tanpa budget, model hardcoded). Kini mendelegasikan ke shim `ai_llm` → `ai_cost_tracker.tracked_llm_call`. Semua text-LLM (smart-import `ai_json`, shim `ai_llm`, dan `services.ai`) kini terpusat: **tercatat di Monitor AI + kena budget + tier konsisten**. Terverifikasi: `daily-summary` kini muncul di usage log.
- Fix label model keliru di UI: `GPT-5.1`/`GPT-4o` → `Claude AI` (AIBusinessDashboard, CashFlowAI, AccountHealthDashboard).

### (a) Executive AI ✅
- Backend baru: `GET /api/reports/executive/ai-narrative` (reuse KPI /summary, tier **executive/Opus**, cache 1h, `refresh=true`). Feature label `executive-narrative`.
- Frontend: tab **"Analisis AI"** di `ExecutiveReportModule` (Portal Keuangan) + renderer `MarkdownLite` + tombol Generate/Regenerate + empty/loading state.

### (d) Admin Gear — Setting AI ✅
- `ai_cost_tracker`: setting DB-driven (`ai_config` doc id=global) → `get_ai_settings()` (cache 20s) + `_feature_disabled()` (match prefix). `_check_budget` & `tracked_llm_call` kini pakai budget DB + master switch + toggle fitur.
- Backend: `GET/PUT /api/ai/usage/settings` (PUT: superadmin/admin/owner). 12 grup fitur.
- Frontend: tab **"Pengaturan"** di `AIUsageMonitorModule` (Manajemen › Strategi & Approval › Monitor AI): master switch, budget (harian/bulanan/per-fitur), tier default, 12 toggle fitur, Simpan/Reset.
- **Bug fix penting:** `db = db or get_db()` → `db = db if db is not None else get_db()` (Motor melarang bool(db)).

### (b) ReportsHub ✅
- Modul baru `ReportsHubModule` (`reports-hub`) = **Pusat Laporan**: katalog 13 laporan lintas divisi (badge domain + badge AI), search + filter domain, klik kartu → `onNavigate` (App.handleNavigate switch portal otomatis). Nav item ditambah di Manajemen › Ringkasan Eksekutif.

### Verifikasi ✅
- `testing_agent` iteration_104: **Backend 100% (31/31)**; Frontend Executive AI penuh. Monitor AI & ReportsHub diverifikasi manual via screenshot (harness agent gagal navigasi portal Manajemen — bukan bug produk).

---


## 🔥 SESSION P0-URGENT (2026-07-15) — Fix Crash Shipment + Identifier Internal/Maklon ✅ DONE & VERIFIED

**Konteks:** User melaporkan crash `ReferenceError: businessType is not defined` di halaman **"Kirim Material CMT"** & **"Dispatch Buyer CMT"** (Portal Maklon), plus minta identifier + filter Internal vs Maklon di list portal produksi.

### Root cause & fix (P0-A) ✅
- `VendorShipmentModule.jsx`: komponen dalam `ShipmentList` memakai `businessType` tapi **tidak menerima prop-nya** (agen sebelumnya hanya menambah `businessType={businessType}` di call-site, lupa destructure). **Fix:** tambah `businessType = null` ke parameter `ShipmentList`.
- `BuyerShipmentModule.jsx`: sudah benar (businessType di scope komponen). Crash-nya karena bundle belum di-rebuild → di-rebuild ulang.

### Temuan penting (menjawab pertanyaan user "apakah data tergabung?") ✅
- `App.js` mengirim `portalId={selectedPortal}` ke tiap modul. `portalId` = `production` → `businessType='internal'`; `maklon` → `'maklon'`.
- Backend `vendor-shipments` & `buyer-shipments` memfilter `?business_type=...`. **Kesimpulan: data SUDAH terpisah per portal — TIDAK tergabung.** (Terbukti: portal Produksi list kosong, portal Maklon berisi 2 shipment maklon.)

### Identifier (P0-B) ✅
- Komponen reusable baru: `frontend/src/components/erp/engine/BusinessTypeBadge.jsx` (`BizBadge`, `BizFilter`, `matchBiz`).
- **Badge Internal/Maklon selalu tampil** per baris di Vendor & Buyer Shipment + **scope indicator** di header ("Menampilkan data Produksi Internal/Maklon (CMT)").
- Badge identifier ditambahkan juga di kolom **PO Produksi** (`ProductionPOModule`).
- Filter Semua/Internal/Maklon tersedia secara defensif (hanya render bila data tergabung; saat ini tidak, karena sudah per-portal).

### Verifikasi ✅
- Manual screenshot: Kirim Material CMT (Maklon), Dispatch Buyer CMT (Maklon), Kirim Material Vendor (Produksi/Internal) → **semua load tanpa crash**, badge + scope tampil benar.
- `testing_agent` (iteration_103): **NO ReferenceError**, 4 halaman load OK, tidak ada error JS console. Frontend 100%.

### Catatan untuk user
- Filter Internal/Maklon dalam satu portal tidak diperlukan karena data sudah otomatis terpisah per portal. Bila user ingin **satu halaman gabungan yang bisa difilter**, bisa dibuatkan terpisah (opsional).

---


## 🧾 SESSION PDF-REFACTOR (2026-07-16) — SPP + Surat Jalan + BOM Internal ✅ DONE & VERIFIED

**Konteks:** PDF SPP & Surat Jalan mengalami layout kurang rapi (teks tumpang tindih, kolom tidak konsisten) dan SPP Internal butuh tampilan BOM (kebutuhan bahan baku). User memilih:
- **1.a:** BOM ditambahkan ke SPP Internal
- **3.a:** Maklon format sama seperti Internal tetapi **tanpa BOM**

### Implementasi utama ✅
**File:** `/app/backend/routes/operations_pdf.py`
- Refactor generator PDF:
  - `type=production-po` (SPP)
  - `type=vendor-shipment` (Surat Jalan material ke vendor)

#### SPP (production-po) ✅
- Menggunakan kop branded + layout konsisten:
  - Header: `_pdf_header_branded(...)`
  - Tabel data: `_pdf_data_table(...)` (kolom proporsional, anti overlap)
  - Baris **TOTAL**
  - Blok tanda tangan configurable: `_pdf_signature_block(...)`
  - Footer branded: `_pdf_footer_branded(...)`
- Judul menampilkan scope bisnis:
  - `SURAT PERINTAH PRODUKSI (SPP) — INTERNAL` atau `— MAKLON`
  - Scope ditentukan dari `production_pos.business_type`

#### BOM untuk SPP Internal saja ✅
- Section **"Kebutuhan Material (BOM)"** hanya muncul bila:
  - `po.get('business_type') != 'maklon'`
- `_aggregate_bom_for_po()` di-rewrite:
  - Agregasi kebutuhan dari `rahaza_boms` (aktif) × qty item PO:
    - `yarn_materials.qty_kg` (per pcs) × `po_items.qty`
    - `accessory_materials.qty` (per pcs) × `po_items.qty`
  - Kategori material diresolusi dari master `rahaza_materials.type` dan dipetakan ke label general:
    - `_MATERIAL_TYPE_LABEL = { yarn: Benang, fabric: Kain, accessory: Aksesoris, fg: Barang Jadi, packaging: Packaging }`
    - **Bukan hardcode** "Kain/Benang" lagi.
  - Qty diformat gaya Indonesia via `_fmt_qty_id` (ribuan '.', desimal ',').

#### Surat Jalan Vendor (vendor-shipment) ✅
- Tabel item dikonversi ke `_pdf_data_table(...)`:
  - kolom proporsional
  - `Qty Kirim` rata-kanan
  - baris **TOTAL**

### Default signature settings untuk SPP ✅
**File:** `/app/backend/utils/pdf_common.py`
- Menambahkan entry `"production-po"` ke `SUPPORTED_PDF_DOCS`:
  - default signatures: **Dibuat oleh / Disetujui oleh / Pelaksana**

### Verifikasi ✅
- `testing_agent` iteration_105: **Backend 100% (12/12)**
  - SPP Internal: PDF valid, ada BOM, kategori material teresolusi (contoh data demo: Benang & Aksesoris), TOTAL ada
  - SPP Maklon: PDF valid, **tanpa BOM**, TOTAL ada
  - Surat Jalan: PDF valid, TOTAL ada
  - Error handling: 400 (missing id), 404 (id tidak ditemukan)
  - Regresi tidak rusak: `vendor-inspection`, `buyer-shipment`, `production-report`, `report-production`

### Status & Next Gate
- **STATUS:** DONE & VERIFIED (backend)
- **Menunggu review user** sebelum lanjut ke P1 (format Rupiah global) dan konversi PDF lain ke format branded.

---


## 🧪 SESSION AUDIT-PO (2026-07-16) — Dropdown kosong saat buat PO (Produksi & Maklon) ✅ FIXED & VERIFIED via UI nyata

**Konteks:** User melaporkan di **PRODUCTION**: saat pembuatan PO (Portal Produksi & Portal Maklon), dropdown Vendor/CMT kosong → menghambat core business flow (assign vendor untuk kirim material).

### Root cause & fix ✅

#### 1) Vendor dropdown memakai endpoint admin-only → 403 untuk user non-admin ✅
- **Masalah:** `ProductionPOModule.fetchVendors()` memakai `GET /api/vendor-portal/partners` yang di-guard admin (`_require_admin`). Untuk user produksi non-admin, request bisa 403 → dropdown kosong.
- **Fix (frontend):** `fetchVendors()` dialihkan ke `GET /api/garments` (require_auth saja; SSOT `vendor_partners`).
- **Fix (UI flow):** Dropdown Vendor/CMT kini tampil di **Internal & Maklon** (hapus gate `!isInternal`). `fetchVendors()` dipanggil juga untuk Internal.

#### 2) `/api/garments` salah menilai vendor UI-created sebagai inactive ✅
- **Masalah:** `routes/master_data.py::GET /garments` hanya mengenali `active` atau `status`, tidak mengenali `is_active` (field yang dipakai vendor yang dibuat via UI Kelola Vendor CMT). Akibatnya vendor dianggap inactive dan hilang.
- **Fix (backend):** Normalisasi status kini mengenali `active` / `is_active` / `status`, default aktif bila tidak ada penanda.

#### 3) Accessories dropdown memakai endpoint deprecated dan filter yang salah ✅
- **Masalah:** `fetchAccessories()` memakai `GET /api/accessories` (DEPRECATED & kosong) + filter `status === 'active'`.
- **Fix (frontend):** `fetchAccessories()` memakai SSOT `GET /api/acc/items?type=accessory` (berbasis `rahaza_materials type=accessory`) + filter `active !== false`.

### Audit hasil (bukan bug) ✅
- Buyers dropdown (Maklon): `fetchBuyers()` sudah melakukan normalisasi `name/code → buyer_name/buyer_code` → **OK**.
- Models/Sizes dropdown (Internal): endpoint Rahaza models/sizes → **OK**.
- `products` state ternyata **dead code** (tidak ada dropdown produk langsung) → bukan bug user-facing.
- Buyer catalog Maklon: hanya terisi untuk buyer tertentu (mis. **Bumi**) → **keterbatasan DATA demo**, bukan bug kode.

### Tech-debt (di luar alur PO, dicatat) ⚠️
- `GET /api/acc/internal-requests` (0 data) — perlu peninjauan apakah modul masih dipakai/harus di-deprecate.
- `GET /api/rahaza/shipments` masih jalan sebagai shim — perlu roadmap migrasi bila masih digunakan oleh modul WMS.

### Verifikasi ✅
- Frontend rebuild statik dilakukan (beberapa kali) via `bash /app/scripts/rebuild_frontend.sh`.
- Uji UI nyata via screenshot automation (login inject + deep-link):
  - **Portal Produksi/Internal:** Vendor dropdown terisi (JMC/RPK), Aksesoris dropdown terisi (Label Woven DA), form item tampil.
  - **Portal Maklon:** Buyer dropdown terisi (Bumi/Aruna/Langit), Vendor dropdown terisi.
- `testing_agent` iteration_107 melaporkan "session lost" setelah klik portal → **FALSE ALARM harness**. Dibuktikan bisa load modul PO normal (screenshot).

### Catatan deployment
- **Perbaikan ini dibuat di PREVIEW.** Karena issue terjadi di **PRODUCTION**, user perlu **redeploy** agar fix masuk ke production.

### File yang berubah
- Backend: `/app/backend/routes/master_data.py`
- Frontend: `/app/frontend/src/components/erp/engine/ProductionPOModule.jsx`
- Frontend (additive): `/app/frontend/src/components/erp/engine/SearchableSelect.jsx` (dukungan `data-testid` untuk test)

---


Konteks: repo `hahagabavca/da` sudah hidup penuh. Wave-1 sudah selesai sebelumnya (B3 status counting, G1 image mapping, H/C2 ProductionProgress live jobs). Fokus sesi lanjutan ini menuntaskan backlog paling kritis, termasuk AI wrapper & outbound scan-out flow.

### 1) P4 — Surat Jalan Internal BOM-driven (Frontend Wiring) ✅
**Tujuan bisnis:** Surat Jalan Internal otomatis terisi material berdasarkan BOM aktif (kain/yarn + aksesoris) × qty job.

**Backend (sudah ada):**
- `GET /api/production-jobs/{job_id}/bom-material-lines`

**Frontend (DONE):** `frontend/src/components/erp/WMSDeliveryNotesModule.jsx`
- Section “Isi dari BOM (Job Internal)”
- APPEND lines (keputusan user)

**Verifikasi:** build statik OK.

---

### 2) A5 — Split-brain schema `rahaza_material_stock` (Unifikasi penuh) ✅
**Keputusan user:** kanonik = **`qty` + `location_id`** (datar). Alias `total_qty`/`quantity` mirrored.

**Implementasi (DONE):**
- SSOT helper: `backend/core/stock_schema.py` (`read_qty/read_available/read_reserved`, `inc_all_qty/set_all_qty`)
- Writer dual-write di berbagai modul

**Verifikasi:** `/app/tests/verify_a5_stock_unify.py` → **18/18 PASS** (juga PASS setelah WS-E).

---

### 3) G4 — COA double-seed duplikat + orphan posting refs ✅
**Keputusan user:** kanonik = **DA_COA_SEED (3-digit)**.

**Hasil:** COA **263 akun**, 0 duplikat; posting profiles resolve.

---

### 4) WS-C — Central AI wrapper + cost tracking ✅
**Implementasi:**
- `backend/ai_cost_tracker.py` (ai_complete/ai_json, budget check, usage log)
- Shim `backend/ai_llm.py`
- Migrasi 21 file ke tier Claude (opus/sonnet/haiku)

---

### 5) WS-D — Smart Import redesign (structured output) ✅
**Implementasi:**
- `universal_import.py` → `ai_json`
- `marketing_import.py` `_llm_column_mapping` → `ai_json` + normalisasi + fallback heuristik

**Verifikasi:**
- HTTP flow: upload → analyze (LLM) → preview OK
- Cost tracking tercatat di `rahaza_ai_usage_logs`

⚠️ **Catatan bug pre-existing:** parsing angka format Indonesia di import (`"Rp 150.000"` terbaca `150.0`) → ditangani di backlog Format Angka (lihat bagian Next).

---

### 6) WS-E — Outbound physical goods → `wh_pending_movements` + Scan-Out ✅ (DONE & VERIFIED)
**Tujuan bisnis:** stok fisik hanya berubah saat gudang melakukan scan-out/scan-in.

**Implementasi (DONE):**
- `wms_receiving.py`
  - `scan_out` diupgrade:
    - Fulfillment FG: potong stok by `stock_id` + lepas `reserved_quantity` (A5-consistent)
    - Default: potong stok by material+lokasi aktif via `inc_all_qty`
    - Hook finalizer best-effort untuk sumber fulfillment
- `fulfillment.py`
  - Dispatch buyer: **dispatch → buat pending outbound_fg**, order → `awaiting_scanout` (stok belum turun)
  - `finalize_fulfillment_dispatch`: saat semua pending confirmed → posting COGS + simpan shipment + order → `dispatched` (idempotent)
- `wms_delivery_notes.py`
  - `issue_sj` untuk **SJ-INTERNAL**: buat pending outbound_rm best-effort (resolve `material_code` → `rahaza_materials`), yang gagal resolve tetap dokumen saja
- `wms_cmt_dispatches.py`
  - execute dispatch: buat SJ-CMT + pending outbound_rm per line best-effort
- Frontend: `FulfillmentModule.jsx`
  - Tambah status `awaiting_scanout` + update teks dialog/toast
  - Static rebuild

**Verifikasi:**
- `/app/tests/verify_wse_outbound.py` → **26/26 PASS**
- Regresi A5 → ALL PASS

---


## ✅ STATUS — Master Plan A–H (konteks repo garment) — Progress terkini

### Selesai
- **WS-B3**: RnD Dashboard status counting fix ✅
- **WS-G1**: Design image mapping saat style promotion ✅
- **WS-H (C2)**: `ProductionProgressModule` migrasi ke live `production_jobs` ✅
- **WS-H (P2)**: UI navigation cleanup ✅
- **WS-H (P3)**: Maklon PO strictly pull dari `dewi_maklon_buyer_catalog` ✅
- **P4**: SJ Internal BOM-driven ✅
- **A5**: unifikasi schema stok ✅
- **G4**: dedup COA ✅
- **WS-C**: AI wrapper terpusat ✅
- **WS-D**: Smart Import structured output ✅
- **WS-E**: wiring outbound scan-out ✅
- **P0-URGENT**: fix crash shipment + isolasi Internal/Maklon ✅
- **PDF-REFACTOR**: SPP + Surat Jalan + BOM Internal ✅
- **AUDIT-PO**: vendor  accessories dropdown (core create PO flow) ✅

### Masih pending / next backlog (berdasarkan keputusan user terbaru)
- **H-C1**: Nonaktifkan/redirect tombol Generate WO (hapus legacy `work_orders` flow)
- **H-C3**: Maklon PO konsolidasi penuh (perlu final verifikasi UI — apakah user masih melihat PO lama & PO baru berdampingan?)
- **H-C4**: Dispatch SSOT engine penuh (refactor besar)
- **WS-G6**: Wire `post_wip_to_fg_on_wo_complete` ke auto-complete job produksi (jalur AD-3)
- **PDF (P1)**: Branded format untuk `vendor-inspection` dan `material-request` (lihat Phase 7a)
- **Format Angka App-wide (P1)**: standardisasi parsing/format nominal (lihat Phase 7b)
- **WS-F**: build memory / dokumentasi (low priority)
- **P0 Demo**: demo manual 3 item/portal + seed script produksi

---


## 🎯 P0 END GOAL — Demo Manual via UI + Seed Script Produksi

### Context
User meminta experience seperti user nyata: input manual 3 item per portal lewat UI untuk memastikan alur produksi berjalan end-to-end, lalu menulis seed script yang robust.

### Target Outcome
1. Demo UI 3 item per portal.
2. Bug P0 diperbaiki on sight.
3. Seed script produksi idempotent + dokumen printable.

---


## 2) Implementation Steps (phased, updated sesuai keputusan user)

### Phase 1 — Stabilize Core Engine ✅
DONE (Wave-1 + P2/P3/P4 + A5 + G4 + WS-C/WS-D/WS-E + P0-URGENT + PDF-REFACTOR + AUDIT-PO).

### Phase 2 — WS-B (PRIORITAS 1): ReportsHub + Executive AI + Admin Gear ✅
**Keputusan user:** kerjakan lengkap.

Status: DONE & VERIFIED (lihat session WS-B).

### Phase 3 — H-C1: Hapus legacy `work_orders` entrypoint ⏳
**Keputusan user:** nonaktifkan tombol Generate WO + redirect ke model job-item.

Langkah:
1. Audit FE `RahazaOrdersModule.jsx` tombol Generate WO.
2. Implement:
   - hide/remove tombol
   - redirect CTA ke flow produksi berbasis `production_jobs`/job-items.
3. Pastikan tidak ada endpoint `/api/work-orders` yang jadi SSOT.
4. Rebuild frontend.

### Phase 4 — H-C3: Maklon PO konsolidasi penuh ⏳
**Temuan kode:** UI nav sudah menunjukkan hanya `maklon-pos-engine` + `maklon-po-360`; `maklon-po` redirect.

Langkah:
1. Konfirmasi real UI: apakah ada menu PO lama & baru berdampingan.
2. Jika benar tidak ada dual UI:
   - cleanup dead code: `MaklonPOModule.jsx` (native CRUD lama) dan shim legacy yang tak dipakai.
   - pastikan SSOT tetap `dewi_maklon_pos` dan master artikel dari `dewi_maklon_buyer_catalog`.

### Phase 5 — H-C4: Dispatch SSOT engine penuh ⏳
**Keputusan user:** refactor besar.

Langkah (high-level):
1. Definisikan SSOT dispatch: entity apa (shipment/delivery_note/pending movements) yang jadi sumber kebenaran.
2. Refactor rute dispatch supaya semua outbound menghasilkan `wh_pending_movements` + status state machine yang konsisten.
3. Pastikan integrasi Finance (posting) terikat ke event scan-out/confirm.
4. Uji E2E + migrasi data bila perlu.

### Phase 6 — WS-G6: Wire WIP→FG posting pada WO/job completion ⏳
**Keputusan user:** wire ke auto-complete job produksi.

Langkah:
1. Cari titik auto-complete job (AD-3) yang stabil.
2. Panggil posting WIP→FG secara idempotent (cek existing JE).
3. Uji dengan seed demo job completion.

### Phase 7a — PDF Branded Lanjutan (P1) ⏳
**Dikerjakan setelah user review PDF-REFACTOR.**

Target:
- Konversi PDF **"Laporan Inspeksi Material"** (`type=vendor-inspection`) dan **"Surat Permohonan Material"** (`type=material-request`) agar konsisten:
  - `_pdf_header_branded`
  - `_pdf_data_table`
  - `_pdf_signature_block` (configurable via `pdf_document_settings`)
  - `_pdf_footer_branded`

Catatan:
- Saat ini `vendor-inspection` dan `material-request` masih memakai generator lama (campuran) dan menjadi target P1.

### Phase 7b — Format Angka App-wide (Parsing + Input) (P1) ⏳
**Dikerjakan setelah user review PDF-REFACTOR.**

**Keputusan user:** perbaiki semua kasus nominal/harga/amount walau tanpa prefix Rp.

Cakupan terdeteksi:
- ~276 komponen punya input numerik/harga/amount.
- ~214 file melakukan format angka/currency secara ad-hoc.

Pendekatan (bertahap, minim risiko):
1. Buat util terpusat `frontend/src/lib/formatNumber.js`:
   - `parseNumericId(str)` (menangani `Rp`, spasi, ribuan `.`, desimal `,`, negatif, angka tanpa Rp)
   - `formatCurrencyId(number)` / `formatNumberId(number)`
2. Buat komponen reusable `CurrencyInput` (controlled):
   - tetap simpan value numerik di state, tampilan terformat
   - opsi showPrefixRp (default off untuk kolom non-Rp)
3. Rollout prioritas:
   - Smart Import `_convert_value` (backend) untuk parsing angka Indonesia
   - Finance/COA/Journal/Invoice/HPP/PO/Price fields
4. Tambah test parsing (python + JS unit) untuk kasus real: `150.000`, `150,000`, `Rp150.000`, `1.234.567,89`, dsb.

### Phase 8 — P0 Manual Demo + Seed script ⏳
Setelah Phase 3–7 cukup stabil, jalankan demo 3 item/portal dan finalize seed script.

---


## 3) Next Actions (immediate)
1. **User redeploy ke PRODUCTION** untuk menerapkan fix AUDIT-PO (vendor  accessories dropdown). 
2. **User review untuk PDF-REFACTOR (SPP + Surat Jalan + BOM Internal).**
3. Setelah user OK: lanjut **Phase 7a** (branded vendor-inspection & material-request).
4. Setelah itu: lanjut **Phase 7b** (format angka Rupiah global).
5. Baru lanjut H-C1 → H-C3 cleanup → H-C4.

---


## 4) Success Criteria (updated)
- **WS-B**: ReportsHub muncul, executive summary jalan via AI wrapper, admin gear berfungsi, biaya AI tercatat.
- **PDF-REFACTOR**: SPP & Surat Jalan rapi (anti overlap), BOM tampil hanya untuk Internal, Maklon tanpa BOM, signature configurable.
- **AUDIT-PO**: saat buat PO (Internal & Maklon), dropdown Vendor/CMT dan Aksesoris **terisi** untuk semua role yang relevan (tidak admin-only).
- **PDF (P1)**: `vendor-inspection` dan `material-request` konsisten dengan branded format (header/table/signature/footer).
- **H-C1**: tidak ada lagi jalur pembuatan WO legacy dari UI; user diarahkan ke job-item engine.
- **H-C3**: tidak ada dual UI Maklon PO; SSOT `dewi_maklon_pos`, master artikel `dewi_maklon_buyer_catalog`.
- **H-C4**: dispatch SSOT konsisten (state machine), semua outbound tercermin di pending movements + scan-out.
- **Format Angka**: semua input nominal/harga/amount konsisten; import parsing angka Indonesia benar.
- Semua perubahan diuji di Preview; siap dipromosikan ke Production oleh user.
