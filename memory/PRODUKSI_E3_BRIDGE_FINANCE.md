# E3 — BRIDGE FINANCE (Produksi/Maklon → GL) : AS-IS vs TO-BE
> Handoff §E3. GROUNDED: `/app/backend/routes/rahaza_posting.py`, `rahaza_posting_profiles.py`,
> `dewi_maklon_finance.py`, `production_variances.py`. STATUS: ANALISIS (belum eksekusi).

## 0. TEMUAN INTI (paling penting utk keputusan adopsi)
**Engine auto-jurnal DA (`rahaza_posting.py`, 24 fungsi `post_*`) di-anchor ke model `rahaza_*`, BUKAN
`production_*` SOMMERVILLE.** Konsekuensi: bila D1 menghapus `rahaza_work_orders`, rantai costing
**WIP→FG→COGS akan PUTUS** kecuali dibuatkan adapter ke model `production_jobs`/`buyer_shipments`.
- `post_wip_to_fg_on_wo_complete` (`:900`) → butuh `rahaza_work_orders` + `rahaza_material_issues` + `rahaza_hpp_snapshots`.
- `post_cogs_shipment` (`:830`) → butuh `rahaza_hpp_snapshots` (per `work_order_id`) + `rahaza_shipments`.
- `post_production_variance` (`:990`) → **SUDAH** pakai koleksi SOMMERVILLE `production_variances` ✅ (satu-satunya yg sudah nyambung).

## 1. DUA SISTEM INVOICE (AS-IS) — sumber kebingungan Finance
| Sistem | Collection | Dipakai | GL |
|---|---|---|---|
| SOMMERVILLE `invoices` | `invoices` (INV-VND/INV-BYR, category VENDOR/BUYER, cmt/selling snapshot) | model outsource-vendor (belum di-bridge GL di DA) | tak auto-jurnal di DA |
| DA AR (rahaza) | `rahaza_ar_invoices` | penjualan internal + AR maklon | `post_ar_invoice` (`:231`) Dr AR / Cr Revenue (+PPN, +discount, +per-channel routing) |
| DA Maklon finance | `dewi_maklon_pos`, `dewi_maklon_advance_payments`, `dewi_cmt_payments` | AR JASA maklon + DP + AP CMT | `post-ar` → `credit_revenue_maklon`; `cmt-payments/post-ap` → `cmt_ap_invoice` |
> **Implikasi**: `invoices` SOMMERVILLE (2-harga) belum tersambung GL DA. Kalau Maklon port identik
> SOMMERVILLE, `invoices` maklon perlu **bridge baru** ATAU tetap pakai `dewi_maklon_*` (yg sudah ada GL).

## 2. PETA BRIDGE GL PRODUKSI/MAKLON (AS-IS, grounded)
| Event | Fungsi | Source collection | Jurnal (Dr / Cr) | Anchor |
|---|---|---|---|---|
| Material issue → WIP | `post_inventory_issue` (`:709`) | `rahaza_material_issues` | Dr WIP 1-1403 / Cr Inventory RM 1-1401 | **rahaza** |
| WO selesai → FG | `post_wip_to_fg_on_wo_complete` (`:900`) | `rahaza_work_orders`(+MI+HPP) | Dr FG 1-1404 / Cr WIP 1-1403 | **rahaza** |
| Shipment → COGS | `post_cogs_shipment` (`:830`) | `rahaza_shipments` + `rahaza_hpp_snapshots` | Dr COGS Material/Labor/OH / Cr FG 1-1404 | **rahaza** |
| Variance over | `post_production_variance` (`:990`) | **`production_variances`** ✅ | Dr FG 1-1404 / Cr Variance Income 5-9100 | **SOMMERVILLE** |
| Variance under | idem | `production_variances` ✅ | Dr Variance Loss 6-4100 / Cr WIP 1-1403 | **SOMMERVILLE** |
| AR jual internal | `post_ar_invoice` (`:231`) | `rahaza_ar_invoices` | Dr AR / Cr Revenue (+PPN, +disc, per-channel) | DA |
| AR jasa maklon | `dewi_maklon_finance.post-ar` | `dewi_maklon_pos`→`rahaza_ar_invoices` | Dr AR / Cr **Revenue Maklon** | DA |
| DP maklon | `advance-payment` (`:237`) | `dewi_maklon_advance_payments` | (DP diterima) | DA |
| AP CMT (bayar vendor jahit) | `cmt-payments/post-ap` | `dewi_cmt_payments` | `cmt_ap_invoice` / `debit_cmt_expense` | DA |
| AR payment | `post_ar_payment` (`:300`) | `rahaza_ar_invoices` + cash movement | Dr Kas / Cr AR | DA |

**Posting profiles (event_type)** relevan: `cogs_shipment`, `wip_to_fg_on_wo_complete`,
`variance_overproduction`, `variance_underproduction`, `ar_invoice`, `credit_revenue_maklon`,
`cmt_ap_invoice`, `inventory_issue`, `inventory_receive`, `inventory_adjust`. Idempotent via
`source_ref` + `_find_existing_je`.

## 3. PERBEDAAN COSTING PRODUKSI vs MAKLON (TO-BE)
| Aspek | PRODUKSI INTERNAL | MAKLON |
|---|---|---|
| Nilai persediaan | HPP penuh (material+labor+OH) → WIP→FG→COGS | **tak ada inventory** (material milik klien) |
| Pendapatan | AR penjualan (selling_price) | AR **jasa** (cmt rate/pcs) + DP |
| Beban | COGS saat terjual | beban CMT (bayar vendor jahit) |
| Variance→GL | ya (over/under) | (opsional; jasa) |

## 4. RISIKO & TO-BE (inti keputusan)
### RISIKO F-1 (HIGH) — Hapus rahaza engine memutus WIP/FG/COGS
`post_wip_to_fg_on_wo_complete` & `post_cogs_shipment` di-key ke `rahaza_work_orders`/`rahaza_hpp_snapshots`/
`rahaza_shipments`/`rahaza_material_issues`. Model SOMMERVILLE (`production_jobs`/`buyer_shipments`) TAK
punya konsep WIP/HPP/COGS.

**Pilihan TO-BE (✅ DIPUTUSKAN user: FIN-1 = A):**
- **Opsi A [DIPILIH]** — Costing penuh dipertahankan (adapter): buat HPP snapshot di-key ke `production_jobs`
  (bukan `rahaza_work_orders`); trigger WIP→FG saat `production_jobs` Completed; trigger COGS saat
  fulfillment FG (buyer_shipment / dispatch marketing). Adapter dirinci di `PRODUKSI_E10_ADAPTER_MIGRASI.md`.
- ~~Opsi B — costing sederhana/periodik~~ (tidak dipilih).
- **Konsekuensi:** akuntansi persediaan real-time dipertahankan; semua fungsi `post_*` di-repoint dari
  koleksi rahaza → `production_jobs`/HPP-baru, TANPA mengganti engine finance DA.

### RISIKO F-2 (MEDIUM) — Dua sistem invoice
`invoices` (SOMMERVILLE) belum ter-bridge GL. Untuk **Maklon identik**:
- **Opsi A** — port `invoices` SOMMERVILLE + BUAT bridge GL baru (`credit_revenue_maklon` via `invoices`).
- **Opsi B** — pertahankan `dewi_maklon_finance` (sudah punya AR/DP/AP + GL) & hanya port PO/job/shipment
  SOMMERVILLE. (rekomendasi B — jangan duplikasi finance yg sudah jalan.)  → **DECISION FIN-2**

### AMAN
- Variance→GL sudah nyambung ke `production_variances` (SOMMERVILLE) → **tak perlu diubah** saat adopsi.
- AR/AP/Payment engine (`rahaza_posting`) portabel — cukup ganti *source* record.

## 5. KEPUTUSAN yang perlu user (dikumpulkan)
- **FIN-1**: Costing Produksi internal → A (adapter WIP/FG/COGS ke production_jobs) atau B (sederhana)?
- **FIN-2**: ✅ **LOCKED = B (arahan user)** — Invoice/Finance Maklon TETAP `dewi_maklon_finance` (DA).
  **SOMMERVILLE finance flow TIDAK di-clone** (jangan port `invoices`/`payments` monolit SOMMERVILLE).
  DA finance (`rahaza_posting.py`, 38 profiles) = SSOT tunggal.
- Catatan: apapun pilihannya, **jaga idempotensi** `source_ref` & posting profiles (jangan duplikasi JE).
- Konsekuensi FIN-2 LOCKED: `invoices`(SOMMERVILLE 2-harga) **TIDAK diadopsi**. Produksi internal & Maklon
  keduanya pakai jalur AR DA (`rahaza_ar_invoices` + `dewi_maklon_finance`). FIN-1 (adapter costing) tetap
  DIKERJAKAN DI DALAM engine finance DA, bukan finance SOMMERVILLE.

---
*E3 selesai. Lanjut E4 (Gudang).*
