# E4 — FLOW GUDANG (WMS) : AS-IS vs TO-BE
> Handoff §E4. GROUNDED: `routes/rahaza_inventory_*.py`, `wms_*.py`, `wms_cmt_dispatches.py`,
> `wms_delivery_notes.py`, `wms_opname*.py`, `dewi_cmt_packing.py`. STATUS: ANALISIS.

## 0. SSOT INVENTORY = `rahaza_material_stock` (110× akses)
Satu koleksi menyimpan **RM + FG + aksesoris** dgn dimensi:
- `ownership`: **`cv_da`** (milik DA) | `maklon_client` (milik klien) — kunci pemisah Produksi vs Maklon.
- `inventory_category`: `raw_material` | `fg_internal` | `accessory` | (maklon: material klien).
- `maklon_client_id`: null utk internal; terisi utk stok milik klien.
- `location`, `quantity`, `available_quantity`, `reserved_quantity`, `unit`.
> Keputusan RC-IA-warehouse (Sesi #23): **UnifiedInventory = read-only**; adjust RESMI via
> `rahaza/material-adjust` (per-lokasi + GL). Locations = union `warehouse_locations`(15×) + `wh_positions`(41×) = 44.

## 1. FLOW GUDANG — AS-IS (grounded)
| Flow | Route / Endpoint | Collection | State / Efek |
|---|---|---|---|
| **GRN (terima material supplier)** | `wms_receiving.py`, `rahaza_grn_qc.py` | `rahaza_grn`, `rahaza_grn_inspections` | terima → AQL inspect → stock-in `rahaza_material_stock` (+GL `inventory_receive`) |
| **Material Issue → Produksi** | `rahaza_inventory_issues.py` `/material-issues` | `rahaza_material_issues` | draft (`draft-from-wo`) → submit → **approve** (deduct stock + GL `inventory_issue` Dr WIP/Cr RM) → reject (`:144-306`) |
| **Retur material sisa → Gudang** | `production_material_returns.py` | `production_material_returns` | draft → submitted → approved → **received** (stock-in balik) |
| **FG receiving (dari CMT)** | `dewi_cmt_packing.py` `/cmt-receipts/{id}/approve` | `cmt_receipts`→`rahaza_material_stock`(fg_internal) + `rahaza_fg_movements` | Submitted → Approved → FG-in (ownership cv_da) |
| **Opname (stock count)** | `wms_opname.py`, `wms_opname2.py` | opname sessions + adjustments | count → selisih → adjust (+GL `inventory_adjust`) |
| **Surat Jalan** | `wms_delivery_notes.py` | `wh_delivery_notes` | SJ-CMT (ke vendor), SJ-BYR (ke customer/fulfillment) |
| **CMT Dispatch (kirim ke vendor jahit)** | `wms_cmt_dispatches.py` `/api/wms/cmt-dispatches` | `wh_cmt_dispatches` | draft → **dispatch** (auto SJ-CMT) → return-line → partially/fully_returned → cancelled (`:117-295`) |
| **Fabric rolls / labels / picklist** | `wms_fabric_rolls.py`, `wms_*_labels.py`, `wms_picklist.py` | rolls, labels, picklists | tracking granular |

### Material Issue detail (`rahaza_inventory_issues.py`)
- `draft-from-wo` (`:51`) = generate issue draft dari BOM `rahaza_work_orders` → **anchor ke rahaza WO**.
- approve (`:217`) = deduct `rahaza_material_stock` + JE `inventory_issue` (Dr WIP 1-1403 / Cr RM 1-1401).

### CMT Dispatch detail (`wms_cmt_dispatches.py:117-152`)
Field: id, dispatch_no, **wo_id, wo_number** (→ ref `rahaza_work_orders`), cmt_name, cmt_address,
delivery_date, status, sj_id/sj_number, lines[{material, qty, qty_returned, qty_outstanding}], notes.
- **❌ D4 TERKONFIRMASI**: TIDAK ADA field `business_type`/`ownership`/`owner`. Pemilik (internal vs maklon)
  hanya bisa DITEBAK dari `wo_id`→`rahaza_work_orders.source` (flag rapuh D2). → **wajib fix di TO-BE**.

## 2. TO-BE — Bridge Gudang ↔ Produksi/Maklon
| Edge | PRODUKSI INTERNAL | MAKLON |
|---|---|---|
| Material asal | **Gudang DA** (`rahaza_material_stock` ownership `cv_da`) → issue deduct stok | **KLIEN** (ownership `maklon_client`, `maklon_client_id`) → TIDAK deduct stok milik DA |
| Trigger issue | dari `production_jobs` (TO-BE, bukan `rahaza_work_orders`) — **adapter** `draft-from-job` | material klien diterima (SOMMERVILLE `vendor_material_inspections`) |
| FG hasil | FG-in `rahaza_material_stock` (fg_internal) → fulfillment/penjualan | **dispatch balik ke klien** (surat jalan) — BUKAN inventory DA |
| CMT dispatch | `wh_cmt_dispatches` + **owner `business_type=internal`** | `wh_cmt_dispatches` + **owner `business_type=maklon`** (fix D4) |
| Retur material sisa | `production_material_returns` → stock-in (tetap) | retur ke klien (bukan stok DA) |
| Opname | `rahaza_material_stock` per ownership/lokasi (tetap) | opname material klien terpisah (ownership `maklon_client`) |

### Perubahan anchor kritikal (sinkron D1/D2)
- `material-issues/draft-from-wo` → butuh varian **`draft-from-job`** (key `production_jobs`) bila
  Produksi internal pindah ke model SOMMERVILLE. (terkait FIN-1 di E3: WIP costing).
- `wh_cmt_dispatches.wo_id` → jadikan generik `ref_type`(internal_job|maklon_order)+`ref_id`+`business_type`.

## 3. RISIKO & DECISION POINTS
### GDG-1 (D4 fix — LOW effort, WAJIB) 
Tambah `business_type` (internal|maklon) + `ownership` eksplisit di `wh_cmt_dispatches` &
turunkan konsisten ke `wh_delivery_notes`. Menghilangkan tebakan owner via WO flag.

### ⚠️ GDG-2 (PERLU KEPUTUSAN) — anchor material issue
Bila Produksi internal adopsi `production_jobs` (bukan `rahaza_work_orders`):
- **Opsi A** — buat adapter `draft-from-job` + WIP costing di-key production_jobs (selaras FIN-1 Opsi A).
- **Opsi B** — Produksi internal TETAP pakai `rahaza_work_orders` HANYA sebagai "shell costing" internal,
  sementara flow progress pakai SOMMERVILLE. (hybrid — lebih rumit, TIDAK disarankan; melanggar semangat D1.)
- **Rekomendasi A** (bersih; hapus rahaza WO sepenuhnya).

### GDG-3 (info) — FG unifikasi sudah benar
`cmt_receipts approve` sudah redirect FG ke `rahaza_material_stock` (fg_internal, cv_da) — Phase 2 fix.
`rahaza_fg_inventory` legacy (3× saja) → boleh dibiarkan / dibersihkan (bukan blocker).

## 4. INVARIAN GUDANG (jaga)
- Stock issue tak boleh > available_quantity (cek saat approve).
- FG-in hanya dari receipt Approved (Q5).
- Opname adjust = selisih tercatat + GL (audit).
- Ownership: material klien (maklon) TIDAK boleh tercampur nilai persediaan DA (COGS).

## 5. KEPUTUSAN yang perlu user (dikumpulkan)
- **GDG-1**: setujui tambah `business_type` owner di CMT dispatch/surat jalan (fix D4)? [rek: ya]
- **GDG-2**: material issue Produksi internal → anchor ke `production_jobs` (A) atau tetap rahaza WO (B)? [rek A, selaras FIN-1]

---
*E4 selesai. Lanjut E5 (Marketing catalog↔demand↔fulfillment).*
