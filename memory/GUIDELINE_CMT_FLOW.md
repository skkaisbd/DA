# 📘 CMT FLOW — DEVELOPMENT GUIDELINE (MASTER)
### CV. Dewi Aditya ERP — Produksi & Maklon (Vendor-CMT Flow)

> **Versi:** 1.0.0  •  **Dibuat:** 2026-07-16
> **Owner file ini:** setiap AI-agent atau engineer yang menyentuh domain Produksi/Maklon/CMT wajib
> membaca dokumen ini **utuh** sebelum menulis 1 baris kode.
>
> **Anti-halusinasi.** Setiap klaim di dokumen ini berjangkar ke `file:line` di codebase yang
> di-clone dari repo `github.com/kubusdrive1-jpg/DA`. Kalau menemukan diskrepansi antara dokumen
> ini dan kode, **jangan patch kode agar cocok dengan dokumen**; sebaliknya, catat diskrepansi
> di bagian *Change Log* (bagian §15) dan verifikasi ke user sebelum bergerak.
>
> **Anti-slop.** Setelah edit apa pun pada file yang di-cover dokumen ini, wajib:
> 1. `python3 /app/scripts/meta/effort_gate.py --strict` → GRADE ≥ B.
> 2. Panggil `testing_agent_v3` untuk skenario end-to-end di bagian §11.
> 3. Update *Change Log* di bawah dengan `[YYYY-MM-DD] <initial> <ringkas>`.

---

## Daftar Isi
1. [Cara pakai dokumen ini](#1-cara-pakai-dokumen-ini)
2. [Problem statement dari user](#2-problem-statement-dari-user)
3. [Golden Rules — anti-halusinasi & anti-slop](#3-golden-rules)
4. [SSOT Registry (Collection Map)](#4-ssot-registry-collection-map)
5. [Domain Flow — kanonik 4-titik variance](#5-domain-flow-kanonik-4-titik-variance)
6. [API Endpoint Map (per SSOT)](#6-api-endpoint-map)
7. [Frontend Module Map](#7-frontend-module-map)
8. [Deprecated / Do-Not-Touch List](#8-deprecated--do-not-touch-list)
9. [Phase A — Bug Additional Shipment (RCA + Fix)](#9-phase-a--bug-additional-shipment)
10. [Phase B — Restructure CMT → DA → Buyer](#10-phase-b--restructure-cmt--da--buyer)
11. [Phase C — PO Closure Rules](#11-phase-c--po-closure-rules)
12. [Testing Contract (verifikasi per phase)](#12-testing-contract)
13. [Cross-Session Handoff Protocol](#13-cross-session-handoff-protocol)
14. [Glossary](#14-glossary)
15. [Change Log](#15-change-log)

---

## 1. Cara pakai dokumen ini

### 1.1 Fresh-agent bootstrap (baca dulu sebelum coding)

Jalankan urutan ini di awal sesi:

```bash
# (a) baca dokumen ini utuh
cat /app/memory/GUIDELINE_CMT_FLOW.md | less

# (b) baca preview-stable-mode (pod 2 GB/1 CPU) — WAJIB
cat /app/memory/PREVIEW_STABLE_MODE.md

# (c) baca credentials
cat /app/memory/test_credentials.md

# (d) baca hasil analisis E2 (QC & Retur AS-IS vs TO-BE)
cat /app/memory/PRODUKSI_E2_QC_RETUR.md

# (e) baca Maklon dual-flow (Engine vs Legacy)
cat /app/memory/MAKLON_PO_DUAL_FLOW_MAPPING.md

# (f) status current
git -C /app log --oneline -20
```

### 1.2 Definisi selesai per phase

Phase dianggap **selesai** hanya kalau:
- [ ] Semua acceptance-criteria di bagian phase ✅
- [ ] `effort_gate.py --strict` GRADE ≥ B
- [ ] `testing_agent_v3` menghasilkan `test_reports/iteration_{n}.json` dengan **0 issue high/medium**
- [ ] Cataloging di `§15 Change Log`

### 1.3 Bila sub-agent report kontradiktif dengan dokumen ini

Presedensi:
1. **Bukti runtime** (log backend, `curl` output, screenshot preview) — highest.
2. **Kode nyata** di file yang disebut dokumen ini.
3. **Dokumen ini**.
4. Dokumen `PRODUKSI_E*` (analitis, sebagian AS-IS pre-refactor).
5. Asumsi AI-agent — **lowest, jangan pernah dipakai untuk decision**.

---

## 2. Problem statement dari user

*(direkam verbatim dari user chat 2026-07-16 — jangan diparafrase)*

> Saya ingin fokus dulu ke inti problem jangan kemana mana. Saya lebih concern fokus membahas
> case bagaimana jika terjadinya bahan kurang dari buyer (ini sudah ada fiturnya namun ternyata
> masih ada bug ketika inspeksi barang kurang dari inspeksi vendor cmt dan request pengiriman
> tambahan dan approve lalu langsung diterima maka ketika dilanjutkan ke jobs production
> **hanya bisa update progress barang yang di inspeksi pertama, pengiriman tambahan tidak
> di proses**.
>
> Lalu case berikutnya bagaimana jika overstate dari vendor mengirim ke da. Untuk case sekarang
> vendor masih mengirim langsung ke buyer dan **ini salah harusnya kirim ke da baru da kirim
> ke buyer** ini perlu di revisi dulu.
>
> Apakah dispatch ke da cmt buat statement pengiriman dan di da ada statement penerimaan yang
> didalamnya ada pengiriman kurang atau tidak diterima (jika reject atau cacat) lalu dari sini
> langsung revisi barang yang diterima (qty berkurang dan otomatis penyesuaian juga dengan
> progress di vendor dll karena ada tracker juga). Lalu selanjutnya dispatch da ke buyer (saat
> ini di erp hanya mirror dispatch buyer dari vendor cmt, berarti ini salah melainkan di vendor
> cmt ubah jadi dispatch ke da dan da dispatch ke buyer dengan source data barang yang aktual
> terima setelah lewat pengecekan dari pengiriman cmt).
>
> Selanjutnya baru layer terakhir validasi dari buyer yang diterima sudah sesuai atau belum
> bisa saja report kurang atau ada cacat yang otomatis ini kembali lagi merubah qty po dan
> final po tertutupnya bagaimana apakah 100% fulfill atau <100 fullfil karena deadline selesai
> atau bahan cacat tidak bisa dikirim lagi dari buyer dll.

### 2.1 Keputusan resmi user (2026-07-16)

| # | Topik | Keputusan |
|---|---|---|
| K1 | Buyer confirm penerimaan | **DA yang isi** (buyer belum bisa dipaksa pakai sistem) |
| K2 | Aksesoris hilang di CMT | Sistem **hanya flag** (via `material_requests` + `condition_notes`). Kesalahan DA vs CMT ditelusuri manual, adjust di AR/AP oleh Finance |
| K3 | Kain buyer kurang | Mekanisme kirim ulang dari buyer via ADDITIONAL shipment sudah ada — **cukup fix Bug Phase A** |
| K4 | Variance tolerance | **Skip dulu** — fokus logic flow |
| K5 | Model QC | **Simple** — bukan multi-stage. Cek FG dari CMT saat receive, cacat = reject. Buang `dewi_maklon_qc_checks` stage-based dan buang `material_defect_reports` sebagai gate produksi |

### 2.2 Ruang lingkup dokumen ini

**IN scope:** Vendor Material In → Production Job → CMT Ship Back to DA → DA Ship to Buyer → PO Closure.

**OUT of scope:** HR, Payroll, LMS, Assets, KPI, Marketing after-sales returns online (R3), rahaza internal accounting core, AI/LLM features. Jangan sentuh ini tanpa persetujuan user.

---

## 3. Golden Rules

### G1 — **Satu SSOT per domain**. Jangan bikin collection duplikat.
Kalau butuh field baru, **tambahkan ke collection SSOT existing** (lihat §4). Kalau butuh
"pandangan berbeda" atas data yang sama, buat **projection / aggregation endpoint**, jangan
duplikat collection.

### G2 — **Zero write ke collection yang di §8 Deprecated List**.
Kalau melihat kode existing yang menulis ke collection deprecated, **jangan otomatis migrasi**;
buat catatan di §15 Change Log dulu, konfirmasi ke user apakah aman untuk cabut.

### G3 — **`business_type` adalah discriminator, bukan collection separator**.
`production_pos.business_type` bernilai `"internal"` atau `"maklon"`. Jangan bikin `internal_pos`
atau `maklon_pos` collection baru. Sudah cukup filter query dengan
`{'business_type': 'internal'}` atau `{'business_type': {'$ne': 'internal'}}`.

### G4 — **Semua endpoint baru harus prefix `/api`**, dan register di `server.py`.
Cek: `grep -n "include_router" /app/backend/server.py`. Kalau bikin router baru, ikuti pola:
```python
router = APIRouter(prefix="/api", tags=["<domain>"])
```

### G5 — **Semua endpoint tulis harus punya guard RBAC**.
Gunakan helper di `routes/production_rbac.py`:
- `require_auth`, `deny_klien`, `check_role(user, PROD_ADMIN_ROLES)`, `is_vendor(user)`,
  `vendor_identity(user)`, `require_write_actor`.
- Endpoint DA-only (mis. `buyer_shipments` di Phase B) → `check_role(user, PROD_ADMIN_ROLES) and not is_vendor(user)`.

### G6 — **State machine di-enforce sebagai daftar transisi legal**.
Contoh yang sudah benar di `vendor_shipment.py:265-273`:
```python
if body['status'] != cur and not (cur == 'Sent' and body['status'] == 'Received'):
    raise HTTPException(400, "Transisi status ilegal ...")
```
Setiap phase yang menambah status baru → tambahkan ke daftar transisi legal di endpoint update-nya.

### G7 — **Uang & qty selalu integer/Decimal, tidak pernah float**.
- Qty (`pcs`, `yard`) → `int(x or 0)` sebelum simpan.
- Currency → `Decimal("...")` dari `decimal`; jangan pakai float.
- Konversi datetime → `parse_date()` dari `core.helpers`, jangan `datetime.strptime` ad-hoc.

### G8 — **Jangan mockup di production code**.
Guardrail `scripts/guardrails/verify_effort_quality.py` deteksi `TODO/FIXME/mock/dummy/placeholder`
di file berubah. Ini blok merge di `--strict` mode.

### G9 — **Tulisan Bahasa Indonesia untuk pesan error user-facing**.
Contoh yg sudah benar: `raise HTTPException(400, 'Qty dikirim melebihi sisa qty ke vendor')`.
Sistem messages ke user pakai Bahasa Indonesia; log internal boleh English.

### G10 — **Migrasi data = script sekali-jalan di `/app/backend/scripts/migrations/`**.
Setiap migrasi harus **idempotent** (aman dijalankan berkali-kali), print counter, dan tercatat
di §15 Change Log. **JANGAN** letakkan migrasi di startup event handler (tidak observable).

---

## 4. SSOT Registry (Collection Map)

Bagian ini adalah **kontrak keras**. Setiap collection di sini punya:
- **SSOT owner**: file yang berhak *tulis*.
- **Reader-only**: file yang boleh *baca*.
- **Purpose**: kalimat pendek.
- **Key fields**: field kritikal (bukan schema lengkap).
- **Related**: relasi FK.

### 4.1 PO (Purchase Order) — SSOT `production_pos` + `po_items` + `po_accessories`

| Collection | Purpose | SSOT owner | Key fields |
|---|---|---|---|
| `production_pos` | Header PO. Discriminator `business_type` = `"internal"` \| `"maklon"` | `routes/production_pos.py` | `id`, `po_number`, `business_type`, `customer_name` (buyer utk maklon), `vendor_id`, `status`, `deadline`, `delivery_deadline`, (§ Phase C add) `closed_reason`, `closed_at`, `qty_short`, `qty_short_pct` |
| `po_items` | Baris item PO (SKU × color × size × qty × harga) | `routes/production_pos.py` | `id`, `po_id`, `sku`, `product_name`, `serial_number`, `size`, `color`, `qty`, `unit_price` |
| `po_accessories` | Aksesoris yang DA sediakan | `routes/production_pos.py` | `id`, `po_id`, `accessory_id`, `accessory_name`, `qty`, `unit` |

**Reader-only untuk `production_pos`:**
`buyer_shipment.py`, `dewi_production_reports.py`, `exceptions.py`, `maklon_client_tracking.py`,
`maklon_seed.py` (seed script), `master_data.py`, `operations_excel.py`, `operations_import.py`,
`operations_pdf.py`, `operations_reports.py`, `operations_serials.py`, `production_execution.py`,
`production_internal_adapter.py`, `production_maklon_bridge.py`, `production_stage_tracking.py`,
`rahaza_hpp.py`, `vendor_shipment.py`.

**Status enum yang sudah eksis** (jangan ubah tanpa migrasi):
`Draft` → `Distributed` → `In Production` → `Completed` → `Closed`
Ditambah di Phase C: transisi `In Production` → `Closed Short` (status baru, lihat §11).

**⚠️ HINDARI collection `dewi_maklon_pos`** untuk pekerjaan baru. Itu Dunia B (legacy). Bridge
`production_maklon_bridge.py` mirror `production_pos` ke `dewi_maklon_pos` untuk keperluan finance
AR/AP legacy. Lihat §8.

---

### 4.2 Vendor Material In (kirim material DA→CMT + inspeksi CMT)

| Collection | Purpose | SSOT owner | Key fields |
|---|---|---|---|
| `vendor_shipments` | Header shipment DA→CMT (kain buyer + aksesoris DA) | `routes/vendor_shipment.py` | `id`, `shipment_number`, `vendor_id`, `po_id`, `shipment_date`, `shipment_type` (`NORMAL`\|`ADDITIONAL`\|`REPLACEMENT`), `parent_shipment_id`, `status` (`Sent`\|`Received`), `inspection_status` (`Inspected`) |
| `vendor_shipment_items` | Baris item shipment (kain per PO item) | `routes/vendor_shipment.py` | `id`, `shipment_id`, `po_item_id`, `qty_sent`, `sku`, `size`, `color`, `serial_number`, `shipment_type` |
| `accessory_shipment_items` | Baris aksesoris di shipment (dari `po_accessories`) | `routes/vendor_shipment.py` | `id`, `shipment_id`, `accessory_id`, `qty` |
| `vendor_material_inspections` | Header hasil inspeksi CMT | `routes/vendor_shipment.py` | `id`, `shipment_id` (**UNIQUE**), `total_received`, `total_missing`, `total_acc_received`, `total_acc_missing`, `status` (`Submitted`) |
| `vendor_material_inspection_items` | Detail inspeksi per item, `item_type` = `"material"` \| `"accessory"` | `routes/vendor_shipment.py` | `id`, `inspection_id`, `shipment_item_id`, `item_type`, `sku`, `size`, `color`, `ordered_qty`, `received_qty`, `missing_qty`, `condition_notes` |

**Invariants:**
- **I-VS-1**: satu `shipment_id` di `vendor_material_inspections` UNIK — tidak boleh ganda (enforce di `vendor_shipment.py:363`).
- **I-VS-2**: `vendor_material_inspection_items.received_qty ≤ vendor_shipment_items.qty_sent`
  (soft; belum di-enforce di DB level, sebaiknya ditambah di Phase A fix).
- **I-VS-3**: `shipment.status='Received'` implies inspeksi valid dijalankan. Di Phase A fix,
  submit inspeksi otomatis promote `status='Sent' → 'Received'`.
- **I-VS-4**: `shipment_type='ADDITIONAL'|'REPLACEMENT'` → `parent_shipment_id` WAJIB non-null.
  Enforce di endpoint POST `/vendor-shipments`.

---

### 4.3 Material Requests (auto-created dari inspeksi kekurangan)

| Collection | Purpose | SSOT owner | Key fields |
|---|---|---|---|
| `material_requests` | Request pengiriman tambahan/pengganti dari CMT ke DA | `routes/vendor_shipment.py` (auto-create) + `routes/exceptions.py` (manage) | `id`, `request_number`, `po_id`, `vendor_id`, `request_type` (`ADDITIONAL`\|`REPLACEMENT`), `category` (`material`\|`accessories`), `original_shipment_id`, `reason`, `status` (`Pending`\|`Approved`\|`Rejected`\|`Fulfilled`), `items[]`, `total_requested_qty` |

**Alur otomatis** (§`vendor_shipment.py:454-482`):
- Inspeksi shipment dengan `accessory_items[].missing_qty > 0` → auto-create `material_requests`
  `request_type='ADDITIONAL'`, `category='accessories'`.
- Inspeksi shipment dengan `items[].missing_qty > 0` (material/kain) → **saat ini TIDAK auto-create**
  (dikomentari di baris 484-488, business rule: user must submit via modal).

---

### 4.4 Production Jobs & Progress (eksekusi di sisi vendor CMT)

| Collection | Purpose | SSOT owner | Key fields |
|---|---|---|---|
| `production_jobs` | Job produksi 1:1 dengan shipment yg sudah di-inspeksi. Bisa punya child (dari ADDITIONAL/REPLACEMENT) | `routes/vendor_shipment.py` (auto-create), `routes/production_execution.py` (manual create + admin ops), `routes/production_internal_adapter.py` (internal-flow) | `id`, `job_number`, `parent_job_id`, `parent_job_number`, `vendor_shipment_id` (**UNIQUE**), `po_id`, `business_type`, `status` (`In Progress`\|`Completed`), `shipment_type` |
| `production_job_items` | Baris item job (yg bisa di-progress) | Sama dengan atas | `id`, `job_id`, `po_item_id`, `vendor_shipment_item_id`, `available_qty` (= `received_qty` inspeksi), `shipment_qty` (= `qty_sent`), `produced_qty`, `ordered_qty` |
| `production_progress` | Ledger progress harian per job_item | `routes/production_execution.py` | `id`, `job_id`, `job_item_id`, `progress_date`, `completed_quantity`, `notes`, `recorded_by` |

**Invariants:**
- **I-PJ-1**: `production_jobs.vendor_shipment_id` UNIK (`production_execution.py:177`).
- **I-PJ-2**: `Σproduction_progress.completed_quantity ≤ production_job_items.available_qty − Σmaterial_defect_reports.defect_qty` (I-1 SOMMERVILLE, `production_execution.py:422-455`).
  **⚠️ Phase C planned change (K5):** buang `material_defect_reports` sebagai gate — ganti dengan
  `Σprogress ≤ available_qty` saja. Migrasi: drop query line 425-427.
- **I-PJ-3**: setiap ADDITIONAL/REPLACEMENT shipment yang sudah di-inspeksi HARUS punya
  `production_job` child. **⚠️ Phase A adalah fix untuk invariant ini yang saat ini bocor.**

---

### 4.5 CMT → DA Receipt (FG kembali ke DA)

| Collection | Purpose | SSOT owner | Key fields (existing) | Key fields (Phase B additions) |
|---|---|---|---|---|
| `cmt_receipts` | Header receipt DA saat terima FG dari CMT | `routes/dewi_cmt_packing.py` | `id`, `receipt_number`, `vendor_id`, `po_id`, `status` (`Draft`\|`Submitted`\|`Approved`\|`Rejected`), `received_date`, `received_by` | **Phase B**: `cmt_shipment_id` (link ke declaration CMT), `total_shipped_by_cmt`, `total_actual`, `total_rejected`, `variance_reason`, `defect_photos[]` |
| `cmt_receipt_lines` | Baris receipt per SKU | Sama | `id`, `receipt_id`, `job_item_id`, `sku`, `size`, `color`, `qty_actual` | **Phase B**: `qty_shipped_by_cmt`, `reject_qty`, `reject_reason` |

**Alur approve** (`dewi_cmt_packing.py:252-332`):
- `status='Submitted'` → validasi → post per line `qty_actual` ke `rahaza_material_stock`
  (owner `cv_da`, category `fg_internal`, material_id `FG-<sku>`) + audit `rahaza_fg_movements`.
- `status='Approved'`.

**Invariants (Phase B target):**
- **I-CR-1**: `Σcmt_receipt_lines.qty_actual + Σcmt_receipt_lines.reject_qty ≤ Σcmt_shipments.qty_shipped_by_cmt` (variance = shortage/loss di transit, di-flag).
- **I-CR-2**: approve `cmt_receipts` menaikkan `da_fg_stock` untuk business_type=maklon
  (tidak untuk COGS internal — itu domain Rahaza F1). Lihat §10 Phase B detail.

---

### 4.6 DA → Buyer Shipment

| Collection | Purpose | SSOT owner | Key fields (existing) | Key fields (Phase B changes) |
|---|---|---|---|---|
| `buyer_shipments` | Header dispatch DA→buyer. **Phase B:** hanya role DA-admin yang bisa create (bukan vendor CMT lagi) | `routes/buyer_shipment.py` | `id`, `shipment_number`, `po_id`, `vendor_id` (**Phase B: deprecated / set null**), `shipment_date`, `status` | **Phase B**: `source_receipt_ids[]` (link ke `cmt_receipts` yang jadi sumber FG), `created_by_da` (bool, always true) |
| `buyer_shipment_items` | Baris item dispatch | `routes/buyer_shipment.py` | `id`, `shipment_id`, `po_item_id`, `job_item_id`, `qty_shipped`, `qty_received`, `received_by`, `received_at`, `received_history[]`, `serial_number` | (tidak berubah) |

**Existing invariant** (`buyer_shipment.py:377-430`, endpoint `GET /buyer-receipt-variance`):
- Variance report per PO: `Shipped vs Received vs Variance` dengan drill-down.
- `qty_received` null → dianggap = `qty_shipped` (effective received).
- `qty_received` non-null → dipakai untuk billing AR (per bridge finance).

**Phase B change (role gate):**
Endpoint `POST /buyer-shipments` di `buyer_shipment.py:130` harus:
```python
if is_vendor(user):
    raise HTTPException(403, 'Vendor CMT tidak boleh membuat buyer shipment langsung. '
                              'Buat CMT receipt dulu; buyer shipment dibuat oleh DA admin.')
```

---

### 4.7 QC / Defect (KEPUTUSAN K5: simplified)

**⚠️ Kondisi TARGET setelah K5 diaplikasikan** (belum eksekusi):

| Collection | Purpose | Nasib | Action |
|---|---|---|---|
| `vendor_material_inspections` | Cek kain/aksesoris masuk ke CMT dari buyer/DA | **KEEP** — 1 titik inspeksi resmi | Tidak berubah |
| `cmt_receipts` + `cmt_receipt_lines` | Cek FG dari CMT balik ke DA (satu-satunya QC output) | **KEEP** & **UPGRADE** (§10 Phase B: tambah `reject_qty`, `reject_reason`, `defect_photos[]`) | Extend |
| `material_defect_reports` | Defect on-the-fly saat produksi (potong kapasitas via I-1) | **BUANG sebagai gate** — biarkan collection ada untuk backward compat, tapi jangan tulis lagi | Deprecate |
| `dewi_maklon_qc_checks` | QC stage-based per proses | **BUANG** — legacy Q4 (E2 QC-1=A dgn keputusan K5 baru) | Deprecate |
| `rahaza_qc_events` | QC bundle multi-stage Rahaza internal | **BUANG** — E2 D1/D5 kompleks-rapuh | Deprecate |
| `qc_inspections` | Generic QC (Q2) | Sudah dead code (router tidak di-include di server.py) | No-op |
| `rahaza_grn_inspections` | AQL gudang (Q3) | **KEEP** — domain gudang, di luar scope kita | Tidak sentuh |

**Migrasi K5:** di Phase B (§10) sekaligus.

---

### 4.8 Retur (RET-1: A = island untuk internal)

**Keputusan E2 RET-1:** untuk Produksi internal, retur pelanggan sudah ditangani `marketing_returns`
(after-sales online). `production_returns` **tidak** diaktifkan untuk B2B internal.

Untuk flow Maklon-B2B kita ini:
- **Buyer complain qty received < qty_shipped** → adjust `buyer_shipment_items.qty_received`
  via endpoint yang sudah ada. TIDAK bikin `production_returns` baru.
- **Buyer complain cacat setelah delivery** → out of scope Phase A/B. Kalau muncul kebutuhan,
  buka diskusi baru.

---

### 4.9 Bridge Finance (untuk Maklon business_type)

| Collection | Purpose | SSOT owner | Interaksi |
|---|---|---|---|
| `dewi_maklon_pos` | Mirror PO Maklon untuk keperluan bridge finance legacy | `routes/production_maklon_bridge.py` (mirror-writer) + `routes/dewi_maklon_pos.py` (legacy CRUD) | Reader-only dari sisi kita — jangan tulis. Trigger `sync_po_to_maklon_finance()` saat `production_pos.status='Confirmed'` |
| `dewi_maklon_finance` | Draft AR Invoice, DP tracking, AP settlement CMT | `routes/dewi_maklon_finance.py` | Update di:<br>- PO confirm → draft AR<br>- Buyer dispatch → mature AR (qty_shipped)<br>- Buyer receipt variance → adjust AR (qty_received)<br>- CMT receipt approve → mature AP (qty_actual to CMT) |

**⚠️ Peringatan G2:** jangan tulis langsung ke `dewi_maklon_finance` dari route yang bukan
`dewi_maklon_finance.py` atau `production_maklon_bridge.py`. Kalau butuh trigger AR/AP, panggil
helper di bridge.

---

## 5. Domain Flow — kanonik 4-titik variance

Peta 4-titik yang **wajib** dibayangkan setiap kali menulis kode di domain ini:

```
      ┌── STREAM A: KAIN (owner: buyer)
      │
   BUYER ──kirim kain──▶ DA warehouse ──transit──▶ CMT VENDOR ──produksi──▶ ...
                                                        ▲
      ┌── STREAM B: AKSESORIS (owner: DA)              │
      │                                                 │
      DA warehouse ────kirim aksesoris─────────────────┘
                                                        │
                                                        ▼
                              CMT produksi (jahit + finishing)
                                                        │
                                        ┌───────────────┴───────────────┐
                                        ▼                               ▼
                              CMT ship ke DA                   (bukan langsung buyer!)
                                        │
                                        ▼
                              DA terima + cek FG
                                        │
                                        ▼
                              DA ship ke BUYER
                                        │
                                        ▼
                              DA record buyer receipt
```

### 5.1 Empat titik variance (T1–T4)

| Titik | Dari → Ke | Dokumen "kirim" (declaration) | Dokumen "terima" (verification) | Field variance |
|---|---|---|---|---|
| **T1** | Buyer/DA → CMT | `vendor_shipments` (di-create DA) | `vendor_material_inspections` (di-create CMT) | `ordered_qty` vs `received_qty` vs `missing_qty` |
| **T2** | CMT produksi (in-house) | `production_job_items.produced_qty` (running total dari `production_progress`) | (Phase C K5 baru): `Σprogress ≤ available_qty` (buang defect gate) | `available_qty − produced_qty` = sisa material |
| **T3** | CMT → DA | **Phase B**: `cmt_shipments` (BARU, di-create CMT) atau reuse `buyer_shipments` sender=vendor (existing, akan dideprekasi) | `cmt_receipts` + `cmt_receipt_lines` (di-create DA) | `qty_shipped_by_cmt` vs `qty_actual` vs `reject_qty` |
| **T4** | DA → Buyer | `buyer_shipments` (di-create DA, **Phase B**: role gate exclude vendor) | `buyer_shipment_items.qty_received` (di-set DA admin atas nama buyer, per K1) | `qty_shipped` vs `qty_received` |

### 5.2 Aliran state PO yang diinginkan

```
Draft
  │ POST /production-pos (create dengan po_items + po_accessories)
  ▼
Distributed
  │ POST /vendor-shipments (kirim material T1)
  ▼
In Production
  │ POST /production-progress (loop produksi T2)
  ▼
Production Complete (opsional; muncul kalau Σprogress ≥ Σavailable_qty)
  │ POST /cmt-receipts + approve (T3, FG masuk DA)
  ▼
Ready to Ship (opsional; kalau Σcmt_receipts.qty_actual ≥ threshold)
  │ POST /buyer-shipments + set qty_received (T4)
  ▼
Completed (Σbuyer_shipment_items.qty_received ≥ Σpo_items.qty)
   ATAU
Closed Short (di-set manual oleh DA admin dgn closed_reason enum, lihat §11 Phase C)
```

### 5.3 Effect matrix (variance → downstream)

Tabel wajib dibaca sebelum ubah field apa pun di 4 dokumen kirim/terima:

| Sumber variance | Field yg berubah | Efek downstream |
|---|---|---|
| T1: `missing_qty > 0` (kain buyer kurang) | `vendor_material_inspection_items.missing_qty` | 1. `production_job_items.available_qty` capped at `received_qty` (bukan `qty_sent`). 2. UI: user create ADDITIONAL shipment referencing parent. 3. Setelah ADDITIONAL diinspeksi (Phase A fix) → child `production_job` + `production_job_items` dibuat. |
| T1: `missing_qty > 0` (aksesoris DA kurang) | `vendor_material_inspection_items.missing_qty` (item_type=accessory) | 1. Auto-create `material_requests` REQ-ACC (existing). 2. DA fulfill via ADDITIONAL shipment (kategori aksesoris). |
| T2: (K5 target) `Σprogress ≤ available_qty` | `production_job_items.produced_qty` | Idle di sini — tidak ada auto-flag. Kalau CMT rusak barang saat produksi, ketauannya di T3. |
| T3: `reject_qty > 0` | `cmt_receipt_lines.reject_qty` + `reject_reason` | 1. `da_fg_stock` bertambah hanya sebanyak `qty_actual`. 2. AP CMT ke `dewi_maklon_finance` di-adjust: bayar CMT hanya utk `qty_actual`, `reject_qty` di-flag utk keputusan Finance (potong tagihan atau proses klaim). 3. TIDAK auto-create job produksi ulang; kalau perlu, DA create ADDITIONAL shipment baru manual. |
| T3: `qty_actual < qty_shipped_by_cmt` (shortage transit, tanpa reject fisik) | `cmt_receipt_lines.qty_actual` + `variance_reason` | Sama seperti reject: flag AP + minta Finance settle. **JANGAN** auto-turunkan `production_progress` — CMT tetap "produksi" segitu; variance ini kerugian transit. |
| T4: `qty_received < qty_shipped` | `buyer_shipment_items.qty_received` (via PUT `/buyer-shipment-items/{id}/received`) | 1. AR invoice pakai `qty_received` (existing bridge). 2. Kalau invoice sudah issued, draft credit note (Phase C add). 3. PO Amendment untuk potong qty resmi (Phase C add). |
| T4: buyer report cacat (jarang, K1 semua DA admin isi) | Reason di `received_history` | Sama seperti `qty_received < qty_shipped` — treatment via credit note / PO short-close. |

---

## 6. API Endpoint Map (per SSOT)

**PENTING**: setiap endpoint di daftar ini adalah *canonical*. Endpoint baru **HARUS**
dipertimbangkan dulu apakah bisa reuse yang ada.

### 6.1 PO (SSOT `production_pos`)

Berkas: `/app/backend/routes/production_pos.py`

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/production-pos` | 75 | List PO (filter `business_type`, `status`, `vendor_id`) |
| GET | `/api/production-pos/{po_id}` | 174 | Detail PO |
| POST | `/api/production-pos` | 194 | Create PO |
| POST | `/api/production-pos/{po_id}/close` | 284 | Close PO **(Phase C: extend dengan close_reason enum)** |
| PUT | `/api/production-pos/{po_id}` | 307 | Update header |
| DELETE | `/api/production-pos/{po_id}` | 498 | Delete PO (guard superadmin) |
| GET | `/api/po-items` | 511 | List po_items |
| GET | `/api/po-items-produced` | 538 | Aggregate produced per po_item |
| PUT | `/api/po-items/{item_id}` | 593 | Update po_item |
| DELETE | `/api/po-items/{item_id}` | 604 | Delete po_item |
| POST | `/api/production-pos/{po_id}/quick-complete` | 614 | Wizard complete |
| POST | `/api/production-pos/{po_id}/status` | 882 | Ganti status manual |
| GET | `/api/production-pos/{po_id}/quantity-summary` | 917 | Ringkasan qty per state |
| GET | `/api/po-accessories` | 991 | List aksesoris PO |
| POST | `/api/po-accessories` | 1001 | Assign aksesoris ke PO |
| DELETE | `/api/po-accessories/{acc_id}` | 1030 | Delete PO accessory |

### 6.2 Vendor Material In (SSOT `vendor_shipments`, `vendor_material_inspections`)

Berkas: `/app/backend/routes/vendor_shipment.py`

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/vendor-shipments` | 24 | List (batch child count, items, po_accessories_count) |
| GET | `/api/vendor-shipments/{sid}` | 103 | Detail (+child_shipments + po_accessories) |
| POST | `/api/vendor-shipments` | 151 | Create shipment (dgn over-ship guard NORMAL di 177-205) |
| PUT | `/api/vendor-shipments/{sid}` | 256 | Update — state machine Sent → Received (265-273) |
| DELETE | `/api/vendor-shipments/{sid}` | 278 | Cascade delete + jobs + progress (superadmin) |
| GET | `/api/vendor-material-inspections` | 311 | List inspeksi |
| POST | `/api/vendor-material-inspections` | 348 | Submit inspeksi (**target Phase A fix di 414**) |

### 6.3 Production Jobs & Progress (SSOT `production_jobs`, `production_progress`)

Berkas: `/app/backend/routes/production_execution.py`

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/production-jobs` | 23 | List parent jobs + inline child_jobs summary |
| GET | `/api/production-jobs/{jid}` | 132 | Detail job + items + child_jobs |
| POST | `/api/production-jobs` | 157 | Create manual (branch internal via adapter di 166-168) |
| DELETE | `/api/production-jobs/{jid}` | 245 | Cascade delete (superadmin) |
| GET | `/api/production-jobs/{job_id}/bom-material-lines` | 325 | Material breakdown |
| GET | `/api/production-progress` | 398 | List progress (filter work_order_id) |
| POST | `/api/production-progress` | 409 | Record progress (**gate I-1 di 422-455 — target K5 remove**) |
| GET | `/api/distribusi-kerja` | 512 | Hierarki PO → shipment → job (aggregation heavy) |

### 6.4 Exceptions / Material Requests / Defect (SSOT `material_requests`, `material_defect_reports`, `production_variances`)

Berkas: `/app/backend/routes/exceptions.py`

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/material-requests` | 40 | List |
| POST | `/api/material-requests` | 64 | Create manual |
| PUT | `/api/material-requests/{req_id}` | 157 | Approve/Reject/Fulfill |
| GET | `/api/material-defect-reports` | 270 | List **(K5 target: readonly; jangan tulis lagi)** |
| POST | `/api/material-defect-reports` | 292 | Create **(K5 target: DEPRECATE — return 410 Gone)** |
| GET | `/api/production-returns` | 337 | List (RET-1=A → tidak dipakai untuk internal) |
| POST | `/api/production-returns` | 388 | Create — konfirmasi ke user sebelum dipakai |
| POST | `/api/production-variances` | 495 | Post variance (mostly financial) |

### 6.5 CMT Receipt (SSOT `cmt_receipts`, `cmt_receipt_lines`) — **T3**

Berkas: `/app/backend/routes/dewi_cmt_packing.py`

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/cmt-receipts/summary` | 56 | Ringkasan |
| GET | `/api/cmt-receipts` | 93 | List |
| POST | `/api/cmt-receipts` | 115 | Create header (Phase B: tambah `cmt_shipment_id`) |
| GET | `/api/cmt-receipts/{receipt_id}` | 141 | Detail |
| PUT | `/api/cmt-receipts/{receipt_id}` | 152 | Update header |
| POST | `/api/cmt-receipts/{receipt_id}/lines` | 174 | Add line (Phase B: tambah `qty_shipped_by_cmt`, `reject_qty`, `reject_reason`) |
| PUT | `/api/cmt-receipts/{receipt_id}/lines/{line_id}` | 202 | Update line |
| DELETE | `/api/cmt-receipts/{receipt_id}/lines/{line_id}` | 215 | Delete line |
| POST | `/api/cmt-receipts/{receipt_id}/submit` | 227 | Submit → status Submitted |
| POST | `/api/cmt-receipts/{receipt_id}/approve` | 252 | Approve → posting FG stock + AP mature |
| POST | `/api/cmt-receipts/{receipt_id}/reject` | 338 | Reject (superadmin) |

### 6.6 Buyer Shipment (SSOT `buyer_shipments`, `buyer_shipment_items`) — **T4**

Berkas: `/app/backend/routes/buyer_shipment.py`

| Method | Path | Line | Purpose |
|---|---|---|---|
| GET | `/api/buyer-shipments` | 25 | List |
| GET | `/api/buyer-shipments/{bsid}` | 92 | Detail |
| POST | `/api/buyer-shipments` | 130 | Create dispatch **(Phase B: role gate: deny_vendor)** |
| PUT | `/api/buyer-shipments/{bsid}` | 236 | Update header |
| DELETE | `/api/buyer-shipments/{bsid}` | 251 | Delete |
| PUT | `/api/buyer-shipment-items/{item_id}` | 263 | Force-edit line (admin) |
| PUT | `/api/buyer-shipment-items/{item_id}/received` | 334 | Set qty_received (admin only per K1, dgn `received_history` audit) |
| GET | `/api/buyer-receipt-variance` | 377 | Report Shipped vs Received per PO |
| GET | `/api/buyer-shipment-dispatches` | 431 | Aggregate dispatches per PO |

---

## 7. Frontend Module Map

### 7.1 Registry file

**Berkas:** `/app/frontend/src/components/erp/moduleRegistry.js`

**Kunci penting:**
- `prod-pos-internal` → `EnginePOModule` dgn `businessType='internal'` (line 618).
- `maklon-pos-engine` → `EnginePOModule` dgn `businessType='maklon'` (line 619).
- `prod-progress` → `EngineProgressModule` (line 620).
- `prod-shipments-vendor` → `EngineVendorShipmentModule` (line 623) — kirim material DA→CMT.
- `prod-shipments-buyer` → `EngineBuyerShipmentModule` (line 622) — dispatch DA→buyer.
- `prod-cmt-packing` → `makeRedirect('wms-cmt-dispatches')` (line 126) — legacy, jangan sentuh.
- Semua `prod-exec-*` (cutting/sewing/finishing/qc/rework/packing/rajut/linking/steam/washer/sontek)
  → `makeRedirect('prod-progress')` — E10 FASE 4 sudah dikubur.

### 7.2 Canonical UI files (yang ADA)

Berkas: `/app/frontend/src/components/erp/engine/`

| File | Domain | Ownership |
|---|---|---|
| `ProductionPOModule.jsx` | PO CRUD (internal & maklon by businessType prop) | KEEP |
| `ProductionProgressModule.jsx` | Progress internal | KEEP |
| `VendorShipmentModule.jsx` | Kirim material DA→CMT (admin DA view) | KEEP |
| `VendorMaterialInspection.jsx` | Form inspeksi (dijalankan CMT vendor) | KEEP — **fokus review Phase A** |
| `VendorProductionJobs.jsx` | List jobs (vendor CMT view) | KEEP |
| `VendorProgress.jsx` | Input progress produksi (vendor CMT view) | KEEP — **user-facing bug Phase A** |
| `VendorReceiving.jsx` | Vendor tandai shipment "Received" | KEEP |
| `VendorDefectReports.jsx` | Vendor input defect | **K5: DEPRECATE** setelah phase B |
| `VendorBuyerShipments.jsx` | Vendor create buyer_shipments **(Phase B: hapus/redirect)** | **Phase B: DELETE** |
| `BuyerShipmentModule.jsx` | DA create buyer_shipments (Phase B: satu-satunya jalur) | KEEP |
| `BuyerReceiptVarianceReport.jsx` | Report T4 variance | KEEP |
| `MaterialDefectReportsModule.jsx` | Legacy defect report list | **K5: DEPRECATE** setelah phase B |
| `ProductionReturnModule.jsx` | RET-1=A: tidak aktif untuk internal | Tetap ada, tidak wire ke portal |
| `OverproductionModule.jsx` | Handle produced > available | Review di Phase C |

### 7.3 File yang HARUS ditambah (Phase B/C)

| File baru | Path | Fungsi |
|---|---|---|
| `DAReceiveFromCMTModule.jsx` | `.../engine/DAReceiveFromCMTModule.jsx` | UI DA-admin buka `cmt_shipments` yang di-declare CMT → isi `cmt_receipts` (qty_actual, reject_qty, defect photos) |
| `CMTShipmentModule.jsx` | `.../engine/CMTShipmentModule.jsx` | UI vendor CMT: declare pengiriman FG ke DA (replaces VendorBuyerShipments.jsx) |
| `POClosureModule.jsx` | `.../engine/POClosureModule.jsx` | UI Phase C: close PO 100% atau short dgn reason enum |

---

## 8. Deprecated / Do-Not-Touch List

### 8.1 Collections yang JANGAN ditulis (readonly untuk backward compat)

| Collection | Alasan | Aksi ke depan |
|---|---|---|
| `rahaza_qc_events` | Q1 bundle multi-stage kompleks-rapuh (E2 D1/D5, K5) | Freeze; hapus di sprint pembersihan berikutnya |
| `dewi_maklon_qc_checks` | Q4 stage-based, konflik dengan K5 simple-check | Freeze; UI di-hide, endpoint tetap up sampai ada migrasi |
| `material_defect_reports` | K5: bukan gate produksi lagi | Endpoint POST → return `410 Gone` di Phase B |
| `qc_inspections` | Dead code (router tidak di-include) | Ignore |
| `dewi_cmt_jobs`, `dewi_cmt_progress`, `dewi_cmt_deliveries`, `dewi_cmt_partners`, `dewi_cmt_delivery_orders`, `dewi_cmt_payments`, `dewi_cmt_progress_reports` | Dunia B legacy sudah kosong per E10 | Jangan tulis; UI-nya sudah redirect ke engine |
| `dewi_maklon_pos` (native writer, bukan bridge mirror) | Dunia B legacy | Hanya boleh ditulis oleh `production_maklon_bridge.py` sebagai mirror |
| `work_orders` | Legacy pre-engine | Ignore untuk pekerjaan baru |
| `production_returns` | RET-1=A, tidak aktif untuk internal | Konfirmasi user sebelum aktifkan |
| `marketing_returns`, `wh_returns`, `dewi_toko_returns`, `dewi_returns` | Domain marketing/toko | Out of scope, jangan sentuh |
| `rahaza_grn_inspections` | Domain gudang, di luar scope | Read-only |

### 8.2 Route files yang JANGAN diedit tanpa persetujuan

| File | Alasan | Owner sekarang |
|---|---|---|
| `routes/dewi_maklon_pos.py` | Dunia B legacy, satu2nya user-view masih dashboard lama | Tidak sentuh |
| `routes/dewi_maklon_finance.py` | Finance AR/AP shared dengan bridge | Panggil helper, jangan modifikasi |
| `routes/dewi_cmt_lifecycle.py` | Legacy, tapi ada report yg masih dipakai | Konfirmasi user |
| `routes/rahaza_*.py` (F1 accounting, HR, payroll, etc.) | Domain terpisah | Out of scope |
| `routes/warehouse.py` | REMOVED per Session 25 (comment di server.py line 1194); pakai `wms_legacy_router` | Ignore |

### 8.3 Frontend modules yang legacy

`/app/frontend/src/components/erp/CMTProgressModule.jsx` — deleted dari registry, tetap ada di
disk, jangan revive tanpa persetujuan user.

---

## 9. Phase A — Bug Additional Shipment

### 9.1 Problem statement (dari user, verbatim)

> Ketika inspeksi barang kurang dari inspeksi vendor cmt dan request pengiriman tambahan dan
> approve lalu langsung diterima maka ketika dilanjutkan ke jobs production hanya bisa update
> progress barang yang di inspeksi pertama, pengiriman tambahan tidak di proses.

### 9.2 RCA (Root Cause Analysis) — grounded

**File pelaku:** `/app/backend/routes/vendor_shipment.py`

**Baris 414:**
```python
if shipment.get('parent_shipment_id') and shipment.get('status') == 'Received':
```

Guard `shipment.status == 'Received'` menyebabkan bug: nilai `status` dibaca di baris 361
(`shipment = await db.vendor_shipments.find_one(...)`) — merefleksikan state DB **sebelum**
endpoint POST inspeksi ini dieksekusi.

Kalau frontend jalankan urutan:
1. POST `/api/vendor-shipments` (status='Sent' default, baris 220)
2. POST `/api/vendor-material-inspections` **(status masih 'Sent')** ← BUG di sini
3. PUT `/api/vendor-shipments/{id}` `{status: 'Received'}`

Maka pada langkah 2, guard baris 414 fail → **child_job TIDAK DIBUAT**. Setelah langkah 3
(status='Received') tidak ada trigger apapun yang retro-create child_job.

**Konfirmasi tidak bisa retry**: `vendor_shipment.py:363`:
```python
existing = await db.vendor_material_inspections.find_one({'shipment_id': body['shipment_id']})
if existing: raise HTTPException(400, 'Inspeksi untuk shipment ini sudah dilakukan')
```

**Efek di frontend** (`VendorProgress.jsx:38`): `setChildJobs(job?.child_jobs || [])` mengambil dari
field `child_jobs` yang dihasilkan `production_execution.py:72-124` via query
`parent_job_id={'$in': job_ids}`. Kalau `production_jobs` untuk additional shipment tidak
pernah di-insert → array kosong → dropdown "Child Jobs" tidak muncul → tidak ada tombol
"Input" untuk item-item shipment tambahan. **Persis simptom user.**

### 9.3 Fix design

#### Fix A1 — Buang guard `status='Received'` dan promote otomatis

**Rasional:** submitting inspeksi = implicit acknowledgment bahwa barang secara fisik sudah
ada di tangan CMT. Guard `status='Received'` cuma race condition tanpa nilai bisnis.

**Perubahan `vendor_shipment.py:414`:**

**BEFORE:**
```python
# Auto-create child job for additional/replacement shipment
if shipment.get('parent_shipment_id') and shipment.get('status') == 'Received':
    parent_job = await db.production_jobs.find_one(...)
    ...
```

**AFTER:**
```python
# Auto-create child job for additional/replacement shipment.
# Inspection is an implicit receipt-acknowledgment: promote status if not yet 'Received'.
if shipment.get('parent_shipment_id'):
    if shipment.get('status') != 'Received':
        await db.vendor_shipments.update_one(
            {'id': shipment['id']},
            {'$set': {'status': 'Received', 'received_at': now(), 'updated_at': now()}}
        )
        shipment['status'] = 'Received'
    parent_job = await db.production_jobs.find_one(...)
    ...
```

#### Fix A2 — Retro-safe hook di update_vendor_shipment

**Rasional:** untuk data yang sudah rusak sebelum fix ini (inspection sudah submit dgn status='Sent'
lalu status berubah ke 'Received') — begitu admin PUT status='Received' lagi, sistem self-heal.

**Perubahan `vendor_shipment.py:256-276`** (endpoint PUT `/vendor-shipments/{sid}`):

Tambahkan sebelum `return`:
```python
# Retro-safety net: bila shipment ADDITIONAL/REPLACEMENT baru dijadikan 'Received' padahal
# inspeksinya sudah selesai duluan (bug pre-fix), buat child_job sekarang (self-heal).
if body.get('status') == 'Received':
    ship = await db.vendor_shipments.find_one({'id': sid})
    if (ship and ship.get('parent_shipment_id')
        and not await db.production_jobs.find_one({'vendor_shipment_id': sid})):
        insp = await db.vendor_material_inspections.find_one({'shipment_id': sid})
        if insp:
            insp_items = await db.vendor_material_inspection_items.find(
                {'inspection_id': insp['id']}
            ).to_list(None)
            await _create_child_job_from_inspection(db, ship, insp, insp_items, user)
```

#### Fix A3 — Extract helper `_create_child_job_from_inspection`

Refactor: pindahkan blok `create_inspection:415-453` (auto-create child job) ke fungsi module-level:

```python
async def _create_child_job_from_inspection(db, shipment: dict, inspection: dict,
                                             inspection_items: list, user: dict) -> str | None:
    """Auto-create production_job (dan items) untuk shipment ADDITIONAL/REPLACEMENT.
    Returns child_job_id, atau None kalau parent job belum ada (skip idempotent)."""
    parent_job = await db.production_jobs.find_one(
        {'vendor_shipment_id': shipment['parent_shipment_id']}
    )
    already_exists = await db.production_jobs.find_one(
        {'vendor_shipment_id': shipment['id']}
    )
    total_received = sum(int(i.get('received_qty', 0) or 0)
                         for i in inspection_items if i.get('item_type') != 'accessory')
    if not parent_job or already_exists or total_received <= 0:
        return None
    # ... (isi persis seperti baris 418-453 lama)
    return child_job_id
```

Panggil dari 2 tempat:
1. `create_inspection` (setelah insert inspection_items).
2. `update_vendor_shipment` (retro-safety).

### 9.4 Migrasi one-shot self-heal

**File:** `/app/backend/scripts/migrations/2026_07_16_phase_a_self_heal_child_jobs.py`

**Fungsi:** cari semua shipments yang:
- `parent_shipment_id` non-null
- `inspection_status == 'Inspected'`
- tidak ada `production_jobs` dengan `vendor_shipment_id == shipment.id`

Untuk tiap match, jalankan `_create_child_job_from_inspection`. Print counter.

**Sifat:** idempotent, aman dijalankan berkali-kali.

### 9.5 Acceptance Criteria Phase A

- [ ] Bug repro-able: buat additional shipment, POST inspection tanpa PUT status='Received', verifikasi child_job **tidak** dibuat (baseline before fix).
- [ ] Setelah Fix A1: POST inspection additional shipment (status='Sent') → child_job otomatis dibuat + shipment status naik ke 'Received'.
- [ ] Setelah Fix A2: shipment yang sudah rusak sebelumnya (inspection submit dgn status='Sent') → PUT status='Received' → child_job otomatis dibuat.
- [ ] `VendorProgress.jsx` dropdown "Child Jobs" muncul untuk parent job yang punya additional shipment ter-inspect.
- [ ] User bisa input progress ke child_job_items.
- [ ] Migrasi `2026_07_16_phase_a_self_heal_child_jobs.py` jalan bersih, print counter, dan re-run tidak double-insert.
- [ ] `testing_agent_v3` semua PASS untuk skenario di §12.1.

### 9.6 File yang di-touch di Phase A

| File | Perubahan |
|---|---|
| `/app/backend/routes/vendor_shipment.py` | Fix A1 (baris ~414), Fix A2 (baris ~275), Fix A3 (extract helper baru di module scope) |
| `/app/backend/scripts/migrations/2026_07_16_phase_a_self_heal_child_jobs.py` | Baru |
| `/app/memory/GUIDELINE_CMT_FLOW.md` | Update §15 Change Log |
| `test_reports/iteration_{N}.json` | Output testing_agent_v3 |

**Tidak sentuh:** frontend, collection lain, endpoint lain.

---

## 10. Phase B — Restructure CMT → DA → Buyer

> ## ✅ STATUS: PHASE B **SELESAI & VERIFIED** (2026-07-17 D6; re-verified runtime 2026-07-21).
> Teks di bawah ini adalah **spesifikasi asli** (bahasa "target/akan"); pembaca JANGAN menganggapnya pending.
> Bukti: §15 Change Log + `scripts/test_phase_b_e2e.py` → **ALL PASS** (re-run 2026-07-21).
> Marker kode: `buyer_shipment.py` (`receiver_type`, `source_receipt_ids[]`), `production_maklon_bridge.mature_ap_from_cmt_receipt`, FE `engine/DAReceiveFromCMTModule.jsx`.


### 10.1 Problem statement (dari user)

> Saat ini di erp hanya mirror dispatch buyer dari vendor cmt, berarti ini salah melainkan di
> vendor cmt ubah jadi dispatch ke da dan da dispatch ke buyer dengan source data barang yang
> aktual terima setelah lewat pengecekan dari pengiriman cmt.

### 10.2 Kondisi AS-IS (grounded)

Dari `buyer_shipment.py:130-234` (endpoint `POST /buyer-shipments`):
- **Tidak ada `deny_vendor` guard**. Vendor CMT bisa create `buyer_shipments` langsung.
- `vendor_id` field diisi dari vendor login → shipment tercatat sebagai "from vendor CMT to buyer".
- DA tidak punya langkah "terima FG dari CMT dulu"; DA hanya ada `PUT /buyer-shipment-items/{id}/received`
  untuk set qty_received buyer (T4).

**Efek**: T3 (CMT → DA) tidak eksplisit. FG "seolah" langsung dari CMT ke buyer, DA hanya mirror.

### 10.3 Kondisi TO-BE

Terpisah menjadi 3 dokumen dengan owner berbeda:

| Dokumen | Sender | Receiver | Purpose |
|---|---|---|---|
| `cmt_shipments` (BARU, atau reuse `buyer_shipments` dengan `receiver_type='da'` sebagai transisi) | CMT vendor | DA | Deklarasi CMT: "saya kirim X pcs ke DA" |
| `cmt_receipts` (existing, upgrade fields) | DA | (audit) | Penerimaan DA: "diterima Y pcs, ditolak Z pcs, alasan W" |
| `buyer_shipments` (existing, guard vendor deny) | DA | Buyer | Dispatch DA→buyer, source data = FG hasil `cmt_receipts.qty_actual` |

**Keputusan implementasi collection T3 CMT-side:**

**Opsi 1 (rekomendasi): reuse `buyer_shipments` dengan field baru `receiver_type`.**

Rasional: banyak logic frontend (fulfillment, invoice) sudah pakai `buyer_shipments`. Bikin
collection baru = duplikasi. Cukup tambah field `receiver_type` = `'da'` atau `'buyer'`.
- `receiver_type='da'` → sender CMT, target DA (T3 declaration)
- `receiver_type='buyer'` → sender DA, target buyer (T4 dispatch)
- Endpoint POST `/buyer-shipments` route berdasarkan role: kalau `is_vendor(user)` → force
  `receiver_type='da'` + auto-create draft `cmt_receipts` untuk DA proses.

**Opsi 2: collection baru `cmt_shipments`.**

Rasional: pemisahan lebih bersih semantik, tapi butuh migrasi data existing (semua
`buyer_shipments` sender=vendor harus dipindah). Risiko lebih tinggi.

**Rekomendasi: Opsi 1** — konfirmasi ke user sebelum eksekusi Phase B.

### 10.4 Field changes

#### 10.4.1 `buyer_shipments` (transisi Opsi 1)

Tambah field:
- `receiver_type` (string, default `'buyer'` untuk backward compat)
- `related_cmt_receipt_id` (nullable) — kalau `receiver_type='da'`, link ke draft `cmt_receipts`.

#### 10.4.2 `cmt_receipts` (upgrade)

Tambah field:
- `related_shipment_id` (string) — link ke `buyer_shipments` dengan `receiver_type='da'`.
- `total_shipped_by_cmt` (int) — sum `cmt_receipt_lines.qty_shipped_by_cmt`.
- `total_actual` (int) — sum `cmt_receipt_lines.qty_actual` (already implicit).
- `total_rejected` (int) — sum `cmt_receipt_lines.reject_qty`.
- `variance_reason` (string) — free text alasan variance.
- `defect_photos` (array of string URLs).

#### 10.4.3 `cmt_receipt_lines` (upgrade)

Tambah field:
- `qty_shipped_by_cmt` (int) — dari `buyer_shipment_items.qty_shipped` yang di-link.
- `reject_qty` (int, default 0).
- `reject_reason` (string).
- `photos` (array of string).

### 10.5 Endpoint changes

#### 10.5.1 POST `/buyer-shipments` (buyer_shipment.py:130) — role gate

```python
# Existing:
if is_vendor(user):
    # (transisi Opsi 1)
    body['receiver_type'] = 'da'
    # Auto-create draft cmt_receipts akan trigger di background hook
    # (implementation: create cmt_receipts + lines saat buyer_shipment terinsert dengan
    #  receiver_type='da')
else:
    if body.get('receiver_type', 'buyer') == 'da':
        raise HTTPException(403, 'Hanya vendor CMT yang boleh receiver_type=da')
    body['receiver_type'] = 'buyer'
    # DA harus reference source cmt_receipts (Phase B strict)
    if not body.get('source_receipt_ids'):
        raise HTTPException(400, 'Buyer shipment dari DA wajib source_receipt_ids[]')
```

#### 10.5.2 POST `/cmt-receipts` (dewi_cmt_packing.py:115) — tambah link

Terima field `related_shipment_id` (dari `buyer_shipments` sender=vendor). Kalau ada, populate
`cmt_receipt_lines` otomatis dari `buyer_shipment_items` (qty_shipped_by_cmt = `qty_shipped`).

#### 10.5.3 POST `/cmt-receipts/{id}/approve` (dewi_cmt_packing.py:252) — extend AP hook

Setelah post FG stock:
- Panggil bridge `production_maklon_bridge.mature_ap_from_cmt_receipt(receipt)`.
- Bridge hitung `payable_amount = Σqty_actual × cmt_rate` (`reject_qty` tidak dibayar).
- Update `dewi_maklon_finance` AP entry: from Draft → Matured dengan amount di atas.
- Flag `variance_reason` untuk manual review Finance.

### 10.6 Frontend changes

| Perubahan | File |
|---|---|
| Redirect `VendorBuyerShipments.jsx` ke inform-view "Deklarasi Pengiriman ke DA" (bukan langsung buyer) | `.../engine/VendorBuyerShipments.jsx` (rename atau kompatibilitas) |
| Buat `DAReceiveFromCMTModule.jsx` — list `cmt_receipts` status Draft/Submitted → open form isi `qty_actual`, `reject_qty`, `reject_reason`, upload photos | Baru |
| `BuyerShipmentModule.jsx` (DA-only) — enforce pilih source `cmt_receipts` yang sudah Approved sebagai source | Update existing |
| Registry: `moduleRegistry.js` tambah entry `da-cmt-receive` → `DAReceiveFromCMTModule` | Update |

### 10.7 Migrasi Phase B (opsional per keputusan user)

**Skenario retro-fill:** data existing `buyer_shipments` di mana `vendor_id` != DA (i.e., sender
vendor CMT) → set `receiver_type='da'`, dan **auto-generate `cmt_receipts` Draft** untuk masing2.

**Sifat:** idempotent, bisa di-skip kalau user prefer clean-cut baru.

### 10.8 Acceptance Criteria Phase B

- [ ] `POST /buyer-shipments` dengan user vendor → force `receiver_type='da'` dan auto-create `cmt_receipts` Draft.
- [ ] `POST /buyer-shipments` dengan user DA + `receiver_type='buyer'` + `source_receipt_ids=[]` → HTTP 400.
- [ ] `POST /buyer-shipments` dengan user DA + `receiver_type='buyer'` + valid `source_receipt_ids` → sukses.
- [ ] `cmt_receipts.approve` → post FG stock + mature AP `dewi_maklon_finance` dgn amount berdasarkan `qty_actual`.
- [ ] UI DA punya menu "Terima FG dari CMT" (`DAReceiveFromCMTModule`) — muncul list receipts pending, bisa input `qty_actual`, `reject_qty`, upload photos.
- [ ] Buyer shipment yg dibuat DA source = `cmt_receipts.qty_actual` (jumlah maksimum tidak melebihi).
- [ ] Effect matrix §5.3 baris T3 terverifikasi runtime.
- [ ] `testing_agent_v3` PASS skenario §12.2.

### 10.9 File yang di-touch di Phase B

| File | Perubahan |
|---|---|
| `/app/backend/routes/buyer_shipment.py` | Role gate + receiver_type + auto-create cmt_receipts hook |
| `/app/backend/routes/dewi_cmt_packing.py` | Field upgrade + link related_shipment_id + AP mature hook |
| `/app/backend/routes/production_maklon_bridge.py` | Helper `mature_ap_from_cmt_receipt` |
| `/app/frontend/src/components/erp/engine/DAReceiveFromCMTModule.jsx` | Baru |
| `/app/frontend/src/components/erp/engine/BuyerShipmentModule.jsx` | Enforce source_receipt_ids |
| `/app/frontend/src/components/erp/engine/VendorBuyerShipments.jsx` | Redirect / info-only |
| `/app/frontend/src/components/erp/moduleRegistry.js` | Tambah `da-cmt-receive` |
| Migrasi Phase B (opsional) | `/app/backend/scripts/migrations/2026_XX_XX_phase_b_backfill_cmt_receipts.py` |

---

## 11. Phase C — PO Closure Rules

> ## ✅ STATUS: PHASE C **SELESAI & VERIFIED** (2026-07-18 E2c; re-verified runtime 2026-07-21).
> Teks di bawah ini adalah **spesifikasi asli** (bahasa "target/planned"); JANGAN dianggap pending.
> Bukti: §15 Change Log + `scripts/test_phase_c_e2e.py` → **ALL PASS** (S7/S8/S8b/S9, re-run 2026-07-21).
> Marker kode: `production_pos.py` (status "Closed Short", `POST /production-pos/{id}/close-short`, `closed_reason` enum, `qty_short`), K5 gate 410 di `exceptions.py` + `dewi_maklon_qc.py`, FE `engine/POClosureModule.jsx`.


### 11.1 Problem statement (dari user)

> Final po tertutupnya bagaimana apakah 100% fulfill atau <100 fullfil karena deadline selesai
> atau bahan cacat tidak bisa dikirim lagi dari buyer dll.

### 11.2 Rule

**Auto-close 100%:**
```
Σbuyer_shipment_items.qty_received (WHERE po_item_id in po.items) ≥ Σpo_items.qty
```
Trigger: setiap kali `PUT /buyer-shipment-items/{id}/received` di-invoke, hitung ulang; kalau
match → auto-transition `production_pos.status = 'Completed'`, `closed_at = now()`, `closed_reason = 'full_fulfillment'`.

**Manual close short:**
Endpoint baru `POST /api/production-pos/{po_id}/close-short` dengan body:
```json
{
  "closed_reason": "deadline_expired" | "buyer_material_shortage" | "cmt_quality_reject_final" | "mutual_agreement",
  "notes": "..."
}
```

Effect:
- `production_pos.status = 'Closed Short'` (status baru).
- `production_pos.closed_reason = ...`, `closed_at = now()`.
- `production_pos.qty_short = Σpo_items.qty - Σbuyer_shipment_items.qty_received`.
- `production_pos.qty_short_pct = qty_short / Σpo_items.qty × 100`.
- Trigger `production_maklon_bridge.finalize_ar_on_short_close(po)`:
  - Kalau AR sudah issued dgn qty_shipped, generate **credit note** untuk `qty_short - qty_already_credited`.
  - Kalau AR belum issued, invoice pakai `qty_received` (bukan qty_ordered).

### 11.3 State machine PO — additions

Tambah transisi legal:
- `In Production` → `Closed Short`
- `Ready to Close` (already exists) → `Closed Short`

Ubah endpoint `PUT /production-pos/{po_id}` untuk include transisi ini di daftar legal.

### 11.4 UI

`POClosureModule.jsx` baru:
- Tampilkan panel di PO detail: `Σqty_ordered`, `Σqty_shipped`, `Σqty_received`, `qty_short_pct`.
- Button "Close Short" muncul kalau `status in ['In Production', 'Ready to Close']` dan `qty_short > 0`.
- Modal minta pilih `closed_reason` dari enum + textarea notes.

### 11.5 Acceptance Criteria Phase C

- [ ] PUT `qty_received` yang membuat `Σ ≥ Σqty_ordered` → PO status jadi `Completed` otomatis.
- [ ] POST `/close-short` dgn reason valid → status `Closed Short`, credit note draft (kalau perlu).
- [ ] Credit note draft muncul di `dewi_maklon_finance` list.
- [ ] `Σqty_short + Σqty_received = Σqty_ordered` (invariant).
- [ ] `testing_agent_v3` PASS skenario §12.3.

### 11.6 K5 cleanup (paralel di Phase C)

- Endpoint `POST /material-defect-reports` → return `HTTPException(410, 'Endpoint di-deprekasi per K5')`.
- Field `material_defect_reports.defect_qty` di gate produksi (`production_execution.py:422-455`) → hapus, ganti dengan `Σprogress ≤ available_qty`.
- Frontend `MaterialDefectReportsModule.jsx` + `VendorDefectReports.jsx` → hide dari menu (registry redirect ke `prod-progress`).
- `dewi_maklon_qc_checks` writes → return 410; UI hide.

---

## 12. Testing Contract

### 12.1 Skenario Phase A (`testing_agent_v3`)

**Prekondisi:**
- Login sebagai `admin@garment.com` / `Admin@123`.
- Login vendor `hr@dewiaditya.id` (bukan CMT vendor, pakai admin utk trigger) — atau seed vendor CMT.

**Skenario 1: Additional shipment auto-child-job (positive)**
1. POST `/api/production-pos` (business_type=maklon, 1 po_item qty=100).
2. POST `/api/vendor-shipments` (shipment_type=NORMAL, qty_sent=100).
3. PUT `/api/vendor-shipments/{id}` status=Received.
4. POST `/api/vendor-material-inspections` items[0]={received_qty:80, missing_qty:20}.
5. Verifikasi: `production_jobs` (parent) dibuat + `production_job_items.available_qty=80`.
6. POST `/api/vendor-shipments` (shipment_type=ADDITIONAL, parent_shipment_id=<step2 id>, qty_sent=20).
7. **JANGAN** PUT status=Received.
8. POST `/api/vendor-material-inspections` items[0]={received_qty:20, missing_qty:0}.
9. **VERIFIKASI**: (a) child `production_jobs` dibuat dgn `parent_job_id` non-null, (b) `production_job_items` dibuat dgn `available_qty=20`, (c) additional shipment `status='Received'` (auto-promoted).
10. POST `/api/production-progress` `job_item_id=<child_item_id>` `completed_quantity=20` → sukses.

**Skenario 2: Retro self-heal (via update status)**
1. Setup: langsung insert doc `vendor_shipments` parent+additional dgn status='Sent' (via mongoshell atau seed), submit inspection tanpa fix — child_job tidak muncul (baseline).
2. Aplikasikan Fix A1+A2.
3. PUT `/api/vendor-shipments/{additional_id}` status='Received'.
4. **VERIFIKASI**: child_job muncul via retro-safety hook.

**Skenario 3: Idempotent migrasi**
1. Jalankan migrasi 2× berturut-turut.
2. Verifikasi tidak ada duplikat `production_jobs` untuk shipment yang sama.

### 12.2 Skenario Phase B (`testing_agent_v3`)

**Skenario 4: Vendor tidak bisa dispatch langsung ke buyer**
1. Login vendor.
2. POST `/api/buyer-shipments` `{receiver_type: 'buyer', ...}` → HTTP 403 atau force `receiver_type='da'`.

**Skenario 5: CMT ship → DA receive → DA ship buyer**
1. Vendor POST `/api/buyer-shipments` `{receiver_type:'da', qty_shipped:100, ...}`.
2. Auto-create `cmt_receipts` Draft.
3. DA POST `/api/cmt-receipts/{id}/lines` isi `qty_actual=95, reject_qty=5, reject_reason='rusak jahitan'`.
4. DA POST `/api/cmt-receipts/{id}/submit` → status Submitted.
5. DA POST `/api/cmt-receipts/{id}/approve` → status Approved + FG stock naik 95 + AP entry di `dewi_maklon_finance` dgn amount = 95 × cmt_rate.
6. DA POST `/api/buyer-shipments` `{receiver_type:'buyer', source_receipt_ids:[<step5 id>], qty_shipped:95, ...}` → sukses.
7. POST `/api/buyer-shipments` `{qty_shipped: 100, source_receipt_ids:[<step5 id>], ...}` → HTTP 400 (melebihi source).

**Skenario 6: `reject_qty` tidak boleh mengurangi `production_job_items.produced_qty`**
1. Buat progress `produced_qty=100`.
2. Buat receipt dgn `qty_actual=95, reject_qty=5`.
3. Verifikasi `production_job_items.produced_qty` tetap 100 (variance transit adalah kerugian, bukan koreksi produksi).

### 12.3 Skenario Phase C (`testing_agent_v3`)

**Skenario 7: Auto-close 100%**
1. PO qty=100.
2. Ship + receive full 100.
3. Verifikasi status jadi `Completed`, `closed_reason='full_fulfillment'`.

**Skenario 8: Close short**
1. PO qty=100.
2. Ship 80, receive 80.
3. POST `/api/production-pos/{po_id}/close-short` `{closed_reason:'deadline_expired'}`.
4. Verifikasi: status `Closed Short`, `qty_short=20`, credit note draft (kalau AR sudah issued).

**Skenario 9: K5 cleanup verify**
1. POST `/api/material-defect-reports` → HTTP 410.
2. POST `/api/production-progress` dgn `completed_quantity` yang bikin `Σ > available_qty` → HTTP 400 dgn message BARU (tidak nyebut defect).
3. `Σprogress` boleh sampai `available_qty` tanpa cek defect_report.

### 12.4 Cara panggil testing_agent_v3

```
testing_agent_v3(task="""
{
  "original_problem_statement_and_user_choices_inputs": "<< paste §2 dari GUIDELINE_CMT_FLOW.md >>",
  "features_or_bugs_to_test": ["<< paste §12.1 skenario 1-3 untuk Phase A >>"],
  "files_of_reference": [
    "/app/backend/routes/vendor_shipment.py",
    "/app/backend/routes/production_execution.py",
    "/app/frontend/src/components/erp/engine/VendorProgress.jsx",
    "/app/memory/GUIDELINE_CMT_FLOW.md"
  ],
  "required_credentials": ["admin@garment.com / Admin@123 (superadmin)"],
  "testing_type": "backend only untuk Phase A; both untuk Phase B/C",
  "agent_to_agent_context_note": {
    "description": "Fresh continuation. Baca /app/memory/GUIDELINE_CMT_FLOW.md §9 (Phase A) atau §10/§11 (Phase B/C) sebelum tulis test. Bug spesifik ada di §9.2 RCA. Verifikasi dgn test_reports/iteration_{n}.json."
  },
  "mocked_api": {"has_mocked_apis": false, "mocked_apis_list": []}
}
""")
```

---

## 13. Cross-Session Handoff Protocol

### 13.1 Sebelum finish sesi

- [ ] Update `§15 Change Log` di dokumen ini.
- [ ] Update `/app/plan.md` (jika ada) dengan status phase.
- [ ] Jalankan `python3 /app/scripts/meta/effort_gate.py --strict` — grade minimal B.
- [ ] Snapshot `git log --oneline -20` ke bawah §15.
- [ ] Kalau ada bug/limitation belum kelar → tulis di §15 dengan tag `KNOWN LIMITATION` dan file path yang bermasalah.

### 13.2 Awal sesi baru (fresh agent)

Wajib jalankan **berurutan**:

```bash
# 1. Konteks env
cat /app/memory/PREVIEW_STABLE_MODE.md
cat /app/memory/test_credentials.md

# 2. Konteks domain
cat /app/memory/GUIDELINE_CMT_FLOW.md   # ← dokumen ini

# 3. Status
supervisorctl status
curl -s http://localhost:8001/api/health

# 4. Baca Change Log terakhir (di bawah)
grep -A 10 "^## 15" /app/memory/GUIDELINE_CMT_FLOW.md | tail -30
```

### 13.3 Kalau menemukan diskrepansi dokumen vs kode

1. **Jangan patch salah satu blind**. Buka issue di §15 Change Log dengan format:
   ```
   [DISCREPANCY <YYYY-MM-DD>] <ringkas>
     Dokumen §X.Y bilang: <text>
     Kode <file:line> bilang: <text>
     Impact: <apa yg break kalau salah>
     Verifikasi ke user: <ya/tidak>
   ```
2. Konfirmasi ke user sebelum bergerak.

---

## 14. Glossary

| Istilah | Definisi |
|---|---|
| **BOM** | Bill of Materials — daftar material per produk |
| **CMT** | Cut Make Trim — vendor tukang jahit eksternal |
| **DA** | CV. Dewi Aditya (perusahaan) |
| **Engine** | ENGINE = pipeline SOMMERVILLE (production_pos → production_jobs → production_progress), kanonik |
| **Dunia B** | Legacy dewi_maklon (native PO); status quo, freeze |
| **FG** | Finished Goods — barang jadi |
| **I-1, I-3, dst.** | Invariant matematis (produced ≤ available, dst.) |
| **K1–K5** | Keputusan resmi user 2026-07-16 (§2.1) |
| **T1–T4** | 4 titik variance (§5.1) |
| **PO** | Purchase Order — order dari buyer |
| **Q1–Q6** | 5+1 sistem QC paralel yang diidentifikasi di analisis E2 |
| **R1–R4** | 3+1 sistem retur paralel |
| **RET-1** | Keputusan retur di E2: A = island (tidak aktifkan `production_returns` untuk internal) |
| **QC-1, QC-2** | Keputusan QC di E2: buang stage-based & bundle multi-stage |
| **SSOT** | Single Source of Truth — collection kanonik untuk domain tertentu |
| **T1 = Vendor Material In** | kirim material buyer→CMT (via DA transit) & aksesoris DA→CMT |
| **T2 = Production Execution** | proses jahit di CMT (progress harian) |
| **T3 = CMT ship back** | FG dari CMT ke DA (`cmt_receipts`) |
| **T4 = DA ship out** | Dispatch DA ke buyer (`buyer_shipments`) |
| **WMS** | Warehouse Management System — modul gudang |
| **WO** | Work Order — legacy, digantikan `production_jobs` |

---

## 15. Change Log

Format entri:
```
[YYYY-MM-DD INITIAL] <one-line summary>
  - <bullet detail>
  - <bullet detail>
  Files: <path[:line]>, <path[:line]>
  Verification: <curl / testing_agent iteration_{n}.json / effort_gate grade>
```

### Log

```
[2026-07-16 E2] GUIDELINE dokumen ini dibuat (v1.0.0).
  - Grounding: forensik kode dilakukan atas seluruh /app/backend/routes (297 file aktif + 38 arsip).
  - Sumber referensi: PRODUKSI_E2_QC_RETUR.md, MAKLON_PO_DUAL_FLOW_MAPPING.md,
    BUSINESS_PROCESS_PRODUKSI_MAKLON.md, moduleRegistry.js, server.py (90+ router registrasi).
  - Belum ada perubahan kode. Phase A/B/C masih proposal, menunggu konfirmasi user
    (§9.5, §10.8, §11.5 acceptance criteria).
  Files: /app/memory/GUIDELINE_CMT_FLOW.md (baru)
  Verification: effort_gate.py --strict = GRADE A (0 file berubah selain dokumen).

[2026-07-16 E2] Phase A COMPLETED — Bug Additional Shipment fixed & verified.
  - Repro empiris via /app/backend/scripts/verify_phase_a.py --expect buggy → confirmed
    bug reproducible (child_jobs=0, status stuck at Sent) → --expect fixed after
    patch → PASS (child_jobs=1, status auto-promoted).
  - Fix A1 applied at vendor_shipment.py:513-530 — drop guard `status=='Received'`,
    auto-promote status to 'Received' when inspection submitted for ADDITIONAL/REPLACEMENT.
  - Fix A2 applied at vendor_shipment.py:275-292 — retro-safety hook in
    update_vendor_shipment self-heals broken pre-fix data when PUT status=Received.
  - Fix A3 applied at vendor_shipment.py:330-408 — extract helper
    _create_child_job_from_inspection as module-level function (reusable by both
    create_inspection and update_vendor_shipment, and by migration script).
  - Migration /app/backend/scripts/migrations/2026_07_16_phase_a_self_heal_child_jobs.py
    — idempotent, verified via 3x run (dry-run + real + re-run with created=0).
  - testing_agent_v3 report: /app/test_reports/iteration_110.json — success 96%
    (25/26 tests), all 6 Phase A acceptance criteria PASS. One minor issue = test
    script's Scenario 5 accessory KeyError (test-script bug, not production).
  - Effort gate: GRADE B (L2/L3/L4/L5 hijau; L1 GATE_RECEIPT MERAH karena stale
    receipt sesi sebelumnya — bukan indikasi kualitas kerja Phase A).
  - KNOWN LIMITATION dari log 2026-07-16 (repro belum runtime): CLOSED.
  Files:
    - /app/backend/routes/vendor_shipment.py (modified: 3 blocks total ~140 lines added,
      Fix A1 replaces 40-line inline block with 15-line delegation to helper;
      Fix A2 adds 18-line retro-hook; Fix A3 adds 78-line helper at module top)
    - /app/backend/scripts/verify_phase_a.py (new; 244 lines; CLI verifier for repro
      + fix-check, supports --expect buggy|fixed)
    - /app/backend/scripts/migrations/2026_07_16_phase_a_self_heal_child_jobs.py
      (new; 173 lines; idempotent one-shot heal for pre-fix broken data)
    - /app/backend/backend_test_phase_a.py (new by testing_agent_v3; 32 KB integration test)
    - /app/test_reports/iteration_110.json (new; test agent report)
  Verification (runtime evidence):
    - verify_phase_a.py --expect buggy (pre-fix) → child_jobs=0, status=Sent, exit 0
    - verify_phase_a.py --expect fixed (post-fix) → child_jobs=1, status=Received,
      progress input SUKSES, exit 0
    - migration run 1: candidates=1, created=1, promoted_status=1, exit 0
    - migration run 2: candidates=1, created=0, skipped_already_exists=1, exit 0
    - testing_agent_v3: 96% pass, 0 critical bugs, 0 medium issues

[2026-07-17 D6] Phase B COMPLETED — CMT -> DA -> Buyer restructure verified.
  - buyer_shipments gained receiver_type ('da'|'buyer'); vendor POST forced to 'da'
    (auto-creates draft cmt_receipt); admin/DA dispatch requires source_receipt_ids
    (400 'source_receipt_ids' before the M-1 minimal-qty guard).
  - New DA UI DAReceiveFromCMTModule.jsx (qty_actual + reject_qty + photos);
    AP hook production_maklon_bridge.mature_ap_from_cmt_receipt().
  - Verification: scripts/test_phase_b_e2e.py 9/9 PASS (self-seeding, idempotent);
    testing_agent_v3 backend 47/47, frontend 100%.
  Files: routes/buyer_shipment.py, routes/production_maklon_bridge.py,
    frontend .../DAReceiveFromCMTModule.jsx, portalNav.js, moduleRegistry.js

[2026-07-18 E2c] Phase C COMPLETED & VERIFIED — PO Closure Rules + K5 cleanup.
  - AUTO-CLOSE: PUT /buyer-shipment-items/{id}/received recomputes fulfillment; when
    Σreceived >= Σordered -> status 'Completed', closed_reason 'full_fulfillment'
    (PUT response carries po_auto_close.closed=true).
  - CLOSE-SHORT: POST /production-pos/{id}/close-short {closed_reason,notes} -> 'Closed
    Short' + qty_short + qty_short_pct. Reasons enum = deadline_expired /
    buyer_material_shortage / cmt_quality_reject_final / mutual_agreement (invalid=400).
    Allowed from In Production/Production Complete/Variance Review/Return Review/Ready to
    Close (Draft=400, no-shortfall=400). Finance: draft AR shrunk to qty_received; issued
    AR -> DRAFT credit note in dewi_maklon_credit_notes = Σ(short×cmt_rate).
    GET /production-pos/{id}/fulfillment + GET /production-pos/{id}/credit-notes added.
  - K5: POST /material-defect-reports -> 410; POST /dewi/maklon/qc -> 410; production
    capacity gate = Σprogress <= available_qty (defect subtraction removed; error text no
    longer mentions 'defect'/'cacat'). Frontend nav redirects: prod-defects/prod-defect-
    codes -> prod-progress, maklon-qc -> maklon-dashboard (modules hidden from menus).
  - New FE module POClosureModule.jsx ('Tutup PO (Closure)', po-closure) in Portal
    Produksi (EKSEKUSI & PENGIRIMAN) and Portal Maklon (VENDOR CMT).
  - Verification: scripts/test_phase_c_e2e.py 4/4 PASS (S7/S8/S8b/S9);
    testing_agent_v3 iteration_phase_c.json -> backend 100% (13/13), frontend ~100%,
    0 critical/UI/integration/design bugs. All §11.5 + §11.6 acceptance criteria PASS.
  Files: routes/production_pos.py (close-short/fulfillment/credit-notes + statuses),
    routes/production_maklon_bridge.py (compute_po_fulfillment, finalize_ar_on_short_close,
    auto-close hook), routes/exceptions.py (material-defect-reports 410),
    routes/dewi_maklon_qc.py (410), routes/production_execution.py (capacity gate),
    frontend .../engine/POClosureModule.jsx, portalNav.js, moduleRegistry.js
```

```
[2026-08-08] E2  PORTAL CMT OVERRIDE — staf DA mengisi 11 modul portal vendor ATAS NAMA vendor CMT
  Keputusan owner: 1a semua 11 modul · 2b role admin/superadmin/admin_produksi/
    supervisor_produksi/ppic · 3a jejak "diinput staf DA" tercatat DAN kelihatan ·
    4a semua vendor aktif di master CMT · 5a vendor ber-akun aktif tetap boleh + diperingatkan.
  SSOT BARU: backend/core/cmt_override.py — header `X-CMT-Override-Vendor`.
    resolve_override() = validasi role + vendor (403 eksplisit untuk role tak berhak DAN untuk
    akun vendor yang mencoba menyamar; 404 vendor tak ada; 400 vendor non-aktif).
    stamp() = entered_by* + on_behalf_of_vendor* (dokumen NON-override tidak ditambahi field).
    apply_scope() / effective_vendor_id() = satu pintu scoping baca & tulis.
  11 komponen engine/Vendor*.jsx DIPAKAI ULANG apa adanya (scoping di backend) ⇒ layar override
    mustahil menampilkan angka berbeda dari yang vendor lihat.
  4 BLOCKER ditutup: GET /api/vendor/dashboard (403 keras utk non-vendor) ·
    GET /api/production-progress (tanpa filter vendor untuk staf) ·
    buyer_shipment._resolve_receiver_type (403 utk receiver_type='da' dari staf) ·
    PUT /api/reminders/{id} (balasan hanya untuk role 'vendor').
  2 BUG PRE-EXISTING ditutup: (a) riwayat progress portal vendor SELALU KOSONG — filter memakai
    `garment_id` yang TIDAK PERNAH ditulis pada jalur `job_item_id` (0 dari 4 dokumen punya field
    itu); (b) inbox reminder BOCOR ke semua vendor — scoping `role=='vendor'` padahal role portal
    CMT adalah `cmt_vendor`, dan balasan reminder vendor CMT selalu diabaikan.
  Jejak audit di 8 write path: vendor_shipments (prefiks `receipt_`), vendor_material_inspections,
    material_requests, production_jobs, production_progress, buyer_shipments,
    production_variances, reminders (prefiks `response_`).
  Badge "diinput staf DA": bahannya dihitung di _enrich_jobs (SSOT bersama /production-jobs &
    /production-tracking), production_cmt_billing._staff_entry_map, dan /prod/cmt-receipts.
    Terpasang di Tracking/Monitoring Produksi, Invoice CMT, Terima FG dari CMT.
  UANG PALSU: verify_produksi_maklon_invariants.py membocorkan 2 AR invoice maklon YATIM tiap
    dijalankan (dihapus lewat `notes` berisi penanda uji, padahal catatan AR ditulis jembatan
    maklon). Terakumulasi Rp 15.120.000 / 14 dokumen — kebocoran ditutup, dokumen dibersihkan.
  Gate BARU: INV-CMTOV = scripts/verify_cmt_override.py (19 invarian) → dipasang di gate.sh (17).
  Bukti: POC test_core_cmt_override.py 96/96 · INV-CMTOV 19/19 · gate.sh 17/17 HIJAU ·
    check_nav_map HIJAU · UI klik-penuh 11/11 user story · drift 0 ·
    total tagihan CMT tidak bergeser (2.435.000 → 2.435.000).
  Files: backend/core/cmt_override.py (BARU), backend/routes/cmt_override_routes.py (BARU),
    routes/{dashboard_routes,production_execution,vendor_shipment,exceptions,buyer_shipment,
    operations_reminders,auth_routes,dewi_cmt_packing,production_cmt_billing,shared}.py,
    frontend .../CMTOverridePortalModule.jsx (BARU), engine/StaffEntryBadge.jsx (BARU),
    lib/api.js, portal-shell/{portalNav.js,Sidebar.jsx}, portalAccess.js, moduleRegistry.js,
    engine/{ProductionMonitoringModule,DAReceiveFromCMTModule}.jsx, ProductionCMTBillingModule.jsx,
    scripts/{seed_cmt_override_demo,verify_cmt_override}.py, scripts/gate.sh
```

---

**End of GUIDELINE_CMT_FLOW.md**
