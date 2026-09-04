# Phase D — Konsolidasi Surat Jalan Buyer (Multi-PO) — PROPOSAL (DISKUSI, BELUM EKSEKUSI)

> Status: **PROPOSAL / MENUNGGU PERSETUJUAN USER.** Belum ada 1 baris kode diubah.
> Sumber kebenaran alur: `memory/GUIDELINE_CMT_FLOW.md` (Phase B/C). Dokumen ini = Phase D.
> Keputusan user (2026-07-18): (1) TIDAK perlu order-buyer induk — konsolidasi di level SJ, PO
> tetap independen. (2) DA pilih bebas beberapa cmt_receipts Approved lintas-PO milik 1 buyer → 1 SJ.
> (3) Auto-close tetap PER PO (independen). (4) Aktual diterima buyer dicatat PER BARIS (per po_item).

---

## 1. Business case (dari user)

- Buyer memesan mis. **10.000 pcs**.
- DA memecah menjadi **10 PO** ke **10 CMT**, masing-masing **1.000 pcs** (independen).
- CMT boleh **partial shipment** ke DA (mis. 500 dari 1.000, belum full-produce). Tiap kiriman
  CMT→DA punya SJ referensi PO. → **SUDAH diakomodir** (Phase B, `receiver_type='da'`).
- Setelah qty terkumpul di DA, DA mengirim ke buyer dengan **1 surat jalan** (tidak per-PO
  satu-satu). SJ ini bisa **gabungan beberapa PO**, tapi tiap qty harus tetap **menyalur ke
  fulfillment PO asalnya** (karena memengaruhi progress & auto-close per PO).

---

## 2. Analisis kondisi saat ini (AS-IS) — grounded

### 2.1 Yang SUDAH benar
| Aspek | Bukti kode |
|---|---|
| CMT→DA partial + SJ per-PO | `buyer_shipment.py:377` create, `receiver_type` dipaksa `da` utk vendor (`_resolve_receiver_type` :47), auto-create `cmt_receipts` Draft (`_auto_create_cmt_receipt_from_shipment` :161) |
| 2 titik aktual diterima | **DA-side**: `cmt_receipt_lines.qty_actual` + `reject_qty` (diisi DA saat inspeksi). **Buyer-side**: `buyer_shipment_items.qty_received` via `PUT /buyer-shipment-items/{id}/received` (:673) |
| Cap dispatch per po_item ≤ diterima dari CMT | create loop :465-511 (pakai `qty_actual` receipt saat `source_receipt_ids` ada) |
| List/detail agregasi per po_item | GET list :314-333 & detail :346-374 sudah group by `po_item_id` (grouping-agnostic utk DISPLAY) |

### 2.2 Yang MEMBLOKIR konsolidasi multi-PO (GAP)
| # | Masalah | Lokasi | Dampak |
|---|---|---|---|
| G1 | Header `buyer_shipments` menyimpan **`po_id` TUNGGAL** | create :424, header field | 1 SJ hanya "milik" 1 PO |
| G2 | Fulfillment/auto-close cari shipment via **header `po_id`** | `_buyer_shipment_ids_for_po` (`production_maklon_bridge.py:393` → `{'po_id': po_id}`) | Item dari PO lain di SJ yg sama TIDAK terhitung ke fulfillment PO tsb → progress salah |
| G3 | `buyer_shipment_items` TIDAK simpan `po_id` (hanya `po_item_id`) | create insert :519-533 | Tidak bisa scan fulfillment berbasis item lintas-PO |
| G4 | Auto-close ambil PO dari **header shipment** | PUT received :717-721 (`ship.po_id`) | Utk SJ gabungan, hanya PO header yg dicek auto-close |
| G5 | Validasi `source_receipt_ids` **berbasis SKU** | `_validate_source_receipts_cap` :103-152 | SKU bisa bentrok antar-PO → cap salah saat multi-PO |
| G6 | UI dispatch = **single-PO** (pilih 1 PO → receipt PO itu saja) | `frontend/.../engine/BuyerShipmentModule.jsx:76-97,482-540` | Tidak bisa pilih receipt lintas-PO |

**Kesimpulan:** memaksa multi-PO ke skema sekarang akan **merusak progress** PO non-header (G2/G3/G4).

---

## 3. Desain usulan (TO-BE) — minimal-invasif, per-PO logic tetap utuh

Prinsip: **fulfillment & auto-close di-key MURNI ke `po_item_id`/`po_id` di level ITEM**, bukan
header. Header `po_id` jadi opsional; SJ bebas berisi item lintas-PO milik 1 buyer.

### 3.1 Perubahan data model
**`buyer_shipments` (header):**
- `po_id` → tetap ada tapi **opsional** (diisi hanya bila SJ single-PO; `null` bila konsolidasi).
- **BARU** `po_ids: [str]` = daftar PO unik yg diwakili SJ (utk display/filter).
- `customer_name` = buyer (WAJIB sama utk semua item; kalau beda → 400).
- `shipment_number` prefix tetap `SJ-BYR-` (untuk multi-PO pakai timestamp/urutan, bukan po_number).

**`buyer_shipment_items` (line):**
- **BARU** `po_id` (denormalisasi dari `po_item` → `po_items.po_id`). **Kunci fulfillment baru.**
- **BARU** `po_number` (denormalisasi, display).
- Field lain (`po_item_id`, `job_item_id`, `qty_shipped`, `qty_received`, ...) tetap.

### 3.2 Perubahan backend
1. **`_buyer_shipment_ids_for_po` (KUNCI, minimal)** → cari shipment via **item**:
   `buyer_shipment_items` where `po_id == po_id` (ATAU `po_item_id ∈ po.items`) → distinct
   `shipment_id` → filter parent shipment `receiver_type='buyer'`.
   **Backward-compat**: UNION dengan cara lama (`buyer_shipments.po_id == po_id`) supaya SJ lama
   yg belum di-backfill tetap terhitung. → `compute_po_fulfillment` otomatis benar tanpa diubah.
2. **`create_buyer_shipment` (POST)** — mode konsolidasi:
   - Terima `items[]` yg tiap baris punya `po_item_id`; resolve `po_id`+`po_number` per item.
   - Header: `po_id=null` bila >1 PO; `po_ids=[distinct]`; `customer_name` di-assert sama (else 400).
   - `source_receipt_ids[]` boleh lintas-PO.
   - Path single-PO (legacy body `po_id`) tetap didukung → 0 regresi.
3. **Validasi cap: SKU-based → `po_item_id`-based** (`_validate_source_receipts_cap`):
   per `po_item_id`, Σ`qty_actual` dari receipt-lines yg `po_item_id` cocok − yg sudah didispatch
   utk po_item itu. (Loop C-1 di create :465-511 sudah po_item-aware; tinggal selaraskan.)
4. **`PUT /buyer-shipment-items/{id}/received`** — resolve PO dari **item** (`item.po_id`, fallback
   `po_item_id→po_items.po_id`), jalankan `try_auto_close_po_on_full` utk PO itu (per baris).
5. **COGS internal** (`post_cogs_on_buyer_dispatch`) — utk SJ konsolidasi, **group items by po_id**
   lalu posting per-PO. Path single-PO tetap. (Kasus maklon: COGS-on-dispatch memang di-skip.)
6. **AR/credit note** (`finalize_ar_on_short_close`) — sudah per-PO (`po['id']`), tidak berubah.

### 3.3 Migrasi data (idempoten, aman)
`backend/scripts/migrations/2026_07_18_phase_d_backfill_buyer_item_po_id.py`:
- Utk tiap `buyer_shipment_items` tanpa `po_id`: resolve dari `po_items` (via `po_item_id`) →
  set `po_id` + `po_number`.
- Backfill header `po_ids[]` dari distinct item.po_id.
- Dry-run + real + re-run (created=0). Tidak menghapus/menimpa data yg sudah ada.

### 3.4 Perubahan frontend (`BuyerShipmentModule.jsx`)
Tambah **mode "Konsolidasi (multi-PO)"** (mode single-PO tetap tersedia utk internal):
1. Pilih **Buyer/Customer** (dropdown buyer yg punya receipt Approved).
2. Tampilkan **semua cmt_receipts Approved buyer itu, dikelompokkan per PO** (badge `po_number`).
3. Centang receipt (lintas-PO) → auto-build baris per `po_item` dgn cap = `qty_actual − sudah dispatch`.
4. Input `qty_shipped` per baris → submit **1 SJ**. Tiap baris tampilkan **badge PO asal**.
5. Detail SJ: item dikelompokkan per `po_number` biar jelas asal-usulnya.

### 3.5 Kontrak API (ringkas)
- `POST /api/buyer-shipments` (DA): body boleh `po_id` (single, legacy) **atau** tanpa `po_id`
  dgn `items[].po_item_id` lintas-PO + `source_receipt_ids[]` lintas-PO. Response: header +
  `po_ids[]` + items (dgn `po_id`/`po_number`).
- Tidak ada endpoint baru wajib; opsional `GET /api/cmt-receipts?status=Approved&customer=<buyer>`
  sudah bisa difilter di FE dari list Approved.

---

## 4. Invariant yang tetap dijaga
- Per PO: `Σqty_short + Σqty_received = Σqty_ordered`.
- Auto-close **per PO independen** (SJ gabungan tidak menutup PO lain sebelum PO itu 100%).
- Cap dispatch per `po_item` ≤ qty diterima DA dari CMT (`qty_actual`).
- SJ konsolidasi hanya untuk **1 buyer** (assert `customer_name` seragam).

## 5. Edge cases & risiko
- **Buyer beda dalam 1 SJ** → ditolak 400 (guard).
- **Backward-compat**: SJ/PO lama (single-PO, item tanpa po_id) → migrasi backfill + UNION query.
- **COGS internal multi-PO** → posting per-PO (perlu tes; risiko akuntansi bila salah key).
- **Reject di DA** sudah tercermin di `qty_actual` (bukan di leg buyer) → tidak berubah.
- **Partial per PO**: SJ boleh berisi 500 dari PO-A + 500 dari PO-B; masing-masing PO progress-nya
  naik terpisah; auto-close menyala hanya saat PO tsb capai 100%.

## 6. Rencana test (testing_agent_v3 + E2E)
`scripts/test_phase_d_e2e.py` (baru): 3 maklon PO buyer sama → CMT declare+DA receive per PO →
DA buat **1 SJ konsolidasi** (item dari 3 PO) → set qty_received per baris → assert:
- fulfillment tiap PO benar (independen),
- tiap PO auto-close saat capai 100% (bukan saat SJ "selesai"),
- close-short salah satu PO tetap jalan (finance per PO),
- regresi Phase B/C tetap hijau (single-PO path).

## 7. Estimasi file tersentuh
- Backend: `routes/buyer_shipment.py` (create, received, validasi), `routes/production_maklon_bridge.py`
  (`_buyer_shipment_ids_for_po` UNION), `routes/rahaza_posting.py` (COGS per-PO group), migrasi (baru), E2E (baru).
- Frontend: `engine/BuyerShipmentModule.jsx` (mode konsolidasi + detail per-PO).
- Docs: file ini + `GUIDELINE_CMT_FLOW.md` §15 changelog + `plan.md`.

## 8. Yang TIDAK dikerjakan (out of scope, sesuai keputusan)
- Entitas "Order Buyer induk" (grouping level buyer) — DITOLAK user; PO tetap independen.
- Perubahan leg CMT→DA (sudah benar).
