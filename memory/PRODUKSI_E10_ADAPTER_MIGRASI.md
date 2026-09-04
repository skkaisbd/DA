# E10 — DESAIN ADAPTER & MIGRASI (rahaza WO → production_jobs)
> Analisis lanjutan (pasca keputusan user: FIN-1=A, HR-1=CAMPURAN, GDG-2=A, QC-2=BUANG).
> GROUNDED: `rahaza_hpp.py:85-222`, `rahaza_posting.py`, `rahaza_inventory_issues.py`,
> `rahaza_work_orders.py:539`, `fulfillment.py:404`. STATUS: ANALISIS (belum eksekusi).

## 0. TUJUAN
Buang **mesin produksi multi-stage rahaza** (D1/D5) & adopsi flow **production_jobs** SOMMERVILLE,
TANPA merusak: **(FIN-1=A)** costing WIP→FG→COGS, **(HR-1=CAMPURAN)** piece-rate per-operator,
**(GDG-2=A)** material issue. Caranya: **RE-ANCHOR** semua dari `work_order_id` → `job_id`.

## 1. TEMUAN KUNCI (menyederhanakan migrasi)
**`labor_cost` HPP == UPAH BORONGAN — SATU SUMBER.** `rahaza_hpp.py:118-157`:
- labor = Σ `rahaza_wip_events`(event_type=`output`, per `operator_id`,`process_id`) × rate.
- rate = `rahaza_payroll_profiles.pcs_process_rates[process_id]` (atau base_rate; fallback
  `rahaza_costing_settings.labor_rate_fallback_per_pcs`).
→ **Menyimpan `rahaza_wip_events` (output) otomatis memenuhi HR-1 (borongan) DAN FIN-1 (labor cost).**
→ Yang dibuang cukup **eksekusi multi-stage** (bundles/andon/aps/routing/qc_events), BUKAN pencatatan output.

Komposisi HPP (per WO sekarang → per job nanti):
| Komponen | Sumber (AS-IS) | Re-anchor (TO-BE) |
|---|---|---|
| material_cost | `rahaza_material_issues`(work_order_id, issued) × `rahaza_materials.unit_cost` | issues(**job_id**) |
| labor_cost | `rahaza_wip_events`(work_order_id, output) × pcs rate | wip_events(**job_id**) |
| overhead_cost | `overhead_rate_per_pcs` × qty_completed(WO) | × Σ `production_job_items.produced_qty` |
| hpp_unit | total_cost / qty_completed | total_cost / produced total job |
| settings | `rahaza_costing_settings` (yarn/acc/overhead/labor fallback) | **TETAP** |

## 2. ADAPTER — TABEL RE-ANCHOR (field key)
| Collection | Field AS-IS | Field TO-BE | Catatan |
|---|---|---|---|
| `rahaza_material_issues` | `work_order_id` | `job_id` (+ `po_id`) | endpoint `draft-from-wo` → **`draft-from-job`** (GDG-2=A) |
| `rahaza_wip_events` | `work_order_id` | `job_id` | field lain TETAP (operator_id, process_id, process_code, event_type=`output`, qty) |
| `rahaza_hpp_snapshots` | `work_order_id` | `job_id` | `_compute_hpp(job_id)`; upsert key `job_id` |
| costing settings/rates | — | — | `rahaza_costing_settings`, `rahaza_payroll_profiles.pcs_process_rates` **TETAP** |

## 3. LAYAR PROGRESS BARU (internal) — jembatan output↔piece-rate
SOMMERVILLE `production_progress` = 1 `completed_quantity` per `job_item`/hari (`recorded_by`=nama).
Untuk internal borongan, layar progress **diperkaya opsional**:
- Input: job_item, qty, **`operator_id`** (opsional), **`process_id`** (opsional, dari master proses ringan).
- Efek: (i) tulis `production_progress` (SOMMERVILLE, update produced_qty, guard I-1); **DAN**
  (ii) mirror `rahaza_wip_events{event_type:'output', job_id, operator_id, process_id, qty}` bila operator diisi.
- Operator **bulanan**: cukup catat progress (tanpa operator_id) → tak menambah wip_events (gaji dari attendance).
- Operator **borongan**: isi operator_id+process_id → wip_events terisi → HPP labor & payroll pcs terpenuhi.
→ Memenuhi **HR-1=CAMPURAN** dalam satu layar, tanpa mesin multi-stage.

## 4. RE-MAP TRIGGER JURNAL (engine finance DA TETAP)
| Event | Trigger AS-IS | Trigger TO-BE | Fungsi (tak berubah) |
|---|---|---|---|
| Material issue → WIP | approve `rahaza_material_issues` (`:296`) | sama, source job | `post_inventory_issue` |
| WIP → FG | `rahaza_work_orders` complete (`:539`) | **`production_jobs` → Completed** | `post_wip_to_fg_on_wo_complete` (rename param wo→job) |
| COGS | fulfillment dispatch (`fulfillment.py:404`) / `rahaza_shipments` | fulfillment (tetap) / **`buyer_shipments`** | `post_cogs_shipment` (baca HPP by job_id) |
| Variance | `production_variances` (SOMMERVILLE) ✅ | **tak berubah** | `post_production_variance` |
| Payroll pcs | payroll run baca `rahaza_wip_events` | sama (job_id) | E6 |
> Semua fungsi `post_*` DIPERTAHANKAN; hanya *lookup key* HPP/issue di-ganti ke `job_id`. Idempotensi
> `source_ref` tetap (mis. `cogs:{shipment_id}`, `wip_fg:{job_id}`).

## 5. MIGRASI: KEEP / REPURPOSE / DELETE
### ✅ KEEP (dipertahankan apa adanya)
`rahaza_material_stock`, `rahaza_materials`, `rahaza_costing_settings`, `rahaza_payroll_*`
(profiles+runs+payslips, incl `pcs_process_rates`), `rahaza_attendance_*`, `production_variances`,
`rahaza_ar_invoices`/`dewi_maklon_finance` (finance DA), `wms_*` (gudang), fulfillment.
### ♻️ REPURPOSE (re-anchor job_id)
`rahaza_material_issues`, `rahaza_wip_events` (jadi **output log ringan**), `rahaza_hpp_snapshots`,
master proses → sederhanakan jadi **`rahaza_processes`** (lookup kode/nama proses utk tag borongan; TANPA routing).
### ❌ DELETE (mesin multi-stage + D5)
`rahaza_work_orders` (setelah costing repoint), `rahaza_bundles*`, `rahaza_execution` (scan bundle),
`rahaza_andon`, `rahaza_aps` (line balancing/scheduler), `rahaza_qc_events`+`rahaza_defect_codes`
(QC-2=BUANG; QC via `material_defect_reports` SOMMERVILLE), routing/line-OEE per-line, dead code (D5).
> ⚠️ Cek dependensi sebelum hapus: dashboard throughput (`dashboard_routes.py:171,327`) & `dewi_maklon.py:519`
> membaca `rahaza_wip_events` (SSOT output nyata) — AMAN karena wip_events DIPERTAHANKAN (hanya re-anchor).

## 6. DATA MIGRATION (lingkungan dev)
- Data = hasil seed (`/api/seed/production-full`). Rekomendasi: **fresh re-seed** dgn seeder baru berbasis
  `production_jobs` (bukan migrasi in-place rahaza WO). Tak ada data produksi riil yang hilang (dev).
- Seeder baru harus mengisi: production_pos→jobs→job_items→progress(+wip_events borongan)→hpp_snapshot→
  buyer_shipment, agar Finance/HR/Dashboard tetap punya data uji.

## 7. INVARIAN (wajib dijaga saat adapter)
- I-1: produced ≤ available − Σdefect (progress guard SOMMERVILLE).
- HPP: labor_cost(job) == Σ upah pcs operator(job) (satu sumber wip_events) → jangan double-count.
- Idempotensi JE (source_ref by job_id/shipment_id).
- Bulanan vs borongan: wip_events HANYA utk borongan (operator_id terisi); jangan paksa semua progress buat wip_events.
- Ownership: maklon (material klien) TIDAK masuk HPP/COGS DA.

## 8. MICRO-DECISIONS (rendah risiko; default diusulkan)
- **AD-1** Master proses ringan `rahaza_processes` (kode: CUT/SEW/FIN/QC/PACK) utk tag borongan? [default: YA]
- **AD-2** Overhead pakai Σ produced job (bukan qty order) → lebih akurat. [default: YA]
- **AD-3** WIP→FG di-trigger saat job Completed atau saat FG diterima gudang (cmt_receipt)? [default: job Completed;
  utk internal FG masuk stok saat job selesai]. (Maklon: FG milik klien → tak masuk WIP/FG DA.)
- **AD-4** Fresh re-seed (bukan migrasi in-place). [default: YA]

## 9. RINGKAS
Migrasi **feasible & bersih**: costing+piece-rate share `rahaza_wip_events` → cukup **re-anchor job_id** +
layar progress diperkaya operator/proses (opsional). Engine finance DA & payroll TAK diganti. Yang dibuang =
eksekusi multi-stage (bundles/andon/aps/routing/qc_events) + dead code. Efek ke Dashboard AMAN (wip_events tetap).

---
*E10 selesai. Kandidat lanjut: E11 (peta endpoint & komponen Portal Vendor utk scoping port).*
