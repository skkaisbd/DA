# FLOW TO-BE FINAL — Produksi Internal & Maklon (hasil analisis E1–E11)
> Sintesis semua keputusan terkunci. Mode ANALISIS (belum eksekusi). Dua jalur DIPISAH (tak ada WO terpadu).
> Legenda: 【GL】=jurnal otomatis (engine finance DA), 【guard】=invarian, [DA+]=adapter/integrasi DA.

═══════════════════════════════════════════════════════════════════
## A. PRODUKSI INTERNAL — FLOW TO-BE (end-to-end)
═══════════════════════════════════════════════════════════════════
Master single-source, costing penuh (FIN-1=A), upah campuran (HR-1), demand→PO via onward CTA (MKT-1=B).

**1. RnD → Master**  `rahaza_models` + `rahaza_boms`
   - RnD kunci Model + BOM (kain + `accessory_materials[]` dgn `material_id` wajib [ACC-2]).
   - SATU sumber master (tak ada master multi-origin / D3).

**2. Marketing → Katalog → Demand**  `marketing_catalog_items`(+`model_id` [MKT-2]) → `marketing_orders`
   - Etalase per akun toko (harga jual). Order online masuk sebagai demand.

**3. Demand → PO Produksi**  onward CTA "Buat PO Produksi" → `production_pos` (+`po_items` 2-harga, +`po_accessories`)
   - `po_accessories` **auto-explode dari BOM × qty** [ACC-1=A].
   - 【guard】 harga: `selling_price_snapshot` (jual) & `cmt_price_snapshot` (tak dipakai internal).

**4. Perencanaan → Job**  `production_jobs` (internal) + `production_job_items`
   - Job = run produksi internal (bukan vendor). `available_qty` awal = qty PO/material tersedia.

**5. Issue Material dari GUDANG**  `draft-from-JOB` [GDG-2=A] → `rahaza_material_issues`(job_id)
   - Deduct `rahaza_material_stock` (ownership `cv_da`). 【GL】 `post_inventory_issue`: Dr WIP 1-1403 / Cr RM 1-1401.
   - Aksesoris habis-pakai: BOM→request→issue dari unified stock (peminjaman alat = domain ASET [E7]).

**6. Eksekusi / Progress**  layar progress baru → `production_progress`
   - 【guard I-1】 produced ≤ available − Σdefect.
   - Operator **bulanan**: catat qty saja. Operator **borongan**: isi `operator_id`+`process_id` →
     mirror `rahaza_wip_events{event_type:'output', job_id, qty}` (dasar HPP labor & upah pcs).
   - Cacat → `material_defect_reports` (potong kapasitas). **QC via defect** — mesin QC multi-stage
     (`rahaza_qc_events`) + Pareto/FPY **DIBUANG** [QC-2].

**7. Job Selesai → WIP→FG**  `production_jobs`→Completed  [AD-3]
   - 【GL】 `post_wip_to_fg_on_wo_complete`(re-key job_id): Dr FG 1-1404 / Cr WIP 1-1403.
   - HPP snapshot/job = material(issues) + labor(wip_events×pcs rate) + overhead(rate×Σproduced) [E10].
   - FG masuk `rahaza_material_stock` (fg_internal, cv_da).

**8. Variance over/under**  `production_variances` → 【GL】 `post_production_variance` (sudah nyambung SOMMERVILLE)
   - OVER: Dr FG 1-1404 / Cr Variance Income 5-9100 · UNDER: Dr Variance Loss 6-4100 / Cr WIP 1-1403.

**9. Fulfillment (kirim ke pelanggan)**  `fulfillment` allocate FG → pick → pack → dispatch
   - Sumber FG: `rahaza_material_stock`(cv_da/fg_internal). 【GL】 `post_cogs_shipment`(HPP by job): Dr COGS / Cr FG.

**10. AR Penjualan**  `rahaza_ar_invoices` → 【GL】 `post_ar_invoice` (Dr AR / Cr Revenue, +PPN/disc, per-channel) → payment.

**11. Retur Pelanggan**  → **after-sales R3** (`marketing_returns`↔`wh_returns`↔`credit_notes`) [RET-1=A]
   - `production_returns` SOMMERVILLE **TIDAK diaktifkan** untuk internal.

**12. Payroll**  `rahaza_payroll_runs` → 【GL】 finalize/payment
   - Bulanan/harian: dari `rahaza_attendance_events` (BPJS/PPh21). Borongan: Σ `rahaza_wip_events`(pcs rate) [HR-1].

═══════════════════════════════════════════════════════════════════
## B. MAKLON — FLOW TO-BE (identik SOMMERVILLE; kecuali Finance & UI = DA)
═══════════════════════════════════════════════════════════════════
Field+collection produksi PERSIS SOMMERVILLE. Material milik KLIEN. Finance = `dewi_maklon_finance` (FIN-2=B).

**1. Klien + Spesifikasi → PO Maklon**  `dewi_maklon_pos` / `production_pos`(maklon)  (+`po_accessories` spek klien)

**2. Material dari KLIEN → Kirim ke Vendor Jahit**  `vendor_shipments`(+items), owner `business_type=maklon` [GDG-1]
   - Ownership stok = `maklon_client` (tak masuk nilai persediaan/COGS DA).

**3. Vendor Terima & Inspeksi**  `vendor_material_inspections`(+items): received/missing → `available_qty` job-item
   - Aksesoris/material kurang → `material_requests` (REQ-ACC / REQ-ADD / REQ-RPL, kebijakan Phase 16).

**4. Job → Progress**  `production_jobs` + `production_job_items` → `production_progress` **by job-item** [VP-1]
   - 【guard I-1】 produced ≤ available − Σdefect. Child job utk ADDITIONAL/REPLACEMENT.
   - **QC = `dewi_maklon_qc_checks`** (stage/reject-rate/alert) — dipertahankan [QC-1=B]. Defect → `material_defect_reports`.

**5. Kirim FG → BALIK ke KLIEN**  `buyer_shipments`(+items, `dispatch_seq`) / delivery-order
   - 【guard C-1】 Σ shipped ≤ Σ produced. FG **milik klien** → BUKAN FG inventory DA, BUKAN COGS DA.

**6. Variance**  `production_variances` (over/under) — laporan; costing jasa (bukan HPP persediaan).

**7. FINANCE Maklon (DA)**  `dewi_maklon_finance`  [FIN-2=B, TAK clone finance SOMMERVILLE]
   - AR **jasa**: 【GL】 `credit_revenue_maklon`. DP: `dewi_maklon_advance_payments`. AP CMT (bayar vendor jahit):
     【GL】 `cmt_ap_invoice`/`debit_cmt_expense`.

**8. Portal VENDOR/CMT** (role `cmt_vendor`, UI komponen DA) [E11]
   - my-jobs · receiving+inspection(GAP) · material-requests · progress(job-item) · buyer-shipments/DO ·
     defect-reports(GAP) · variance(GAP) · serial-tracking · (reminder = skip [VP-2]).

═══════════════════════════════════════════════════════════════════
## C. INTEGRASI LINTAS-PORTAL (edge TO-BE)
═══════════════════════════════════════════════════════════════════
| Edge | Internal | Maklon |
|---|---|---|
| Master | RnD→BOM→`rahaza_models` | snapshot dari model/spek klien |
| Material | Gudang DA (`rahaza_material_stock` cv_da) | Klien (`maklon_client`) |
| FG | masuk stok DA → fulfillment | balik ke klien (SJ) |
| Finance | AR jual + WIP/FG/COGS + variance (engine DA) | AR jasa + DP + AP CMT (`dewi_maklon_finance`) |
| HR | payroll bulanan+borongan (wip_events) | biaya jahit = AP vendor |
| Aksesoris | BOM→request→issue (unified stock) | spek klien / material klien |
| Aset | mesin=aset→depresiasi (prio rendah) | — |
| RBAC | admin_produksi/operator (+remap) | admin_maklon + cmt_vendor + klien_maklon(view) |

═══════════════════════════════════════════════════════════════════
## D. YANG DIBUANG (pendekatan keras, D1/D5)
═══════════════════════════════════════════════════════════════════
- Mesin produksi **multi-stage rahaza**: `rahaza_work_orders`(setelah costing repoint), `rahaza_bundles*`,
  `rahaza_execution`, `rahaza_andon`, `rahaza_aps` (routing/line-balance), `rahaza_qc_events`+`rahaza_defect_codes`.
- WO terpadu ber-flag `source` (D2), CMT dispatch tanpa owner (D4→ditambah `business_type`), dead code (D5).
- Finance SOMMERVILLE (`invoices`/`payments`), auth/user/role SOMMERVILLE, UI shell SOMMERVILLE, buyer-portal.
**DIPERTAHANKAN (repurpose):** `rahaza_wip_events` (output log borongan), `rahaza_hpp_snapshots`,
`rahaza_material_issues` (re-anchor job_id), `rahaza_material_stock`, payroll/attendance, finance DA, WMS.

═══════════════════════════════════════════════════════════════════
## E. INVARIAN GLOBAL (wajib dijaga)
═══════════════════════════════════════════════════════════════════
- I-1 produced ≤ available − Σdefect · I-2 Σshipped ≤ Σproduced · I-3 Σreturn ≤ Σshipped−Σreturned.
- HPP labor(job) == Σ upah pcs operator(job) — satu sumber `rahaza_wip_events` (jangan double-count).
- Idempotensi 【GL】 via `source_ref` (job_id/shipment_id).
- Maklon: material/FG milik klien TIDAK masuk persediaan/COGS DA (ownership `maklon_client`).
- Produksi & Maklon TERPISAH (tak ada WO terpadu).

---
*Ringkasan TO-BE final. Detail per-area: E1–E11 + adapter E10 + scoping E11. Siap eksekusi setelah lampu hijau.*
