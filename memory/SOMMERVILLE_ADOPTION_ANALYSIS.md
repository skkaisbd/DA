# SOMMERVILLE-FINAL → DA : Analisa Adopsi Flow Produksi

> Dibuat saat user minta adopsi flow produksi dari repo
> `pandekomangyogaswastika-dot/SOMMERVILLE-FINAL` ke DA.
> Tujuan: ganti Portal Produksi DA yang buggy dengan flow SOMMERVILLE yang lebih bersih.
> STATUS: ANALISA SAJA (belum eksekusi). User akan refactor SOMMERVILLE dulu.

## TEMUAN KUNCI (paling penting)
**DA adalah FORK dari SOMMERVILLE.** Bukan codebase asing.
Bukti:
- Stack sama persis: FastAPI + React + Mongo + Shadcn/craco + emergentintegrations.
- Role auth sama: `superadmin/admin/vendor/buyer` (DA menambah `cmt_vendor` + custom roles).
- Endpoint produksi SAMA PERSIS: `/production-pos`, `/po-items`, `/po-accessories`,
  `/production-jobs`, `/production-job-items`, `/production-progress`,
  `/production-variances`, `/production-returns`, `/buyer-shipments`, `/vendor-shipments`,
  `/vendor-material-inspections`, `/material-requests`, `/production-monitoring-v2`,
  `/po-items-produced`.
- Koleksi produksi SAMA: `production_pos, po_items, po_accessories, production_jobs,
  production_job_items, production_progress, production_variances, production_returns,
  buyer_shipments, vendor_shipments, vendor_material_inspections, material_requests`.

## AKAR MASALAH PORTAL PRODUKSI DA (kenapa buggy tak selesai-selesai)
DA punya **DUA model produksi paralel**:
1. **`production_*` (warisan SOMMERVILLE)** — PO→job→progress→shipment→variance→invoice.
   Sederhana, terbukti. **Backend-nya MASIH ADA** di DA (`routes/production_po.py`,
   `production_jobs.py`, `production_progress.py`, `production_variances.py`,
   `production_returns.py`), tapi **UI-nya sudah diarsip** (`components/erp/_archive/`).
2. **`rahaza_*` (bikinan DA)** — work-order berbasis bundle, multi-stage
   (cutting/CMT/QC/packing), WIP→GL Finance. **Kompleks & buggy.** UI Produksi DA
   sekarang (`prod-*`) dibangun di atas model INI (`RahazaWorkOrdersModule`,
   `ProcessExecutionModule`, `RahazaHPPModule`, `RahazaMaterialIssueModule`, dll).

→ Portal Produksi DA sekarang = UI kompleks di atas `rahaza_*` yang buggy.
→ Rencana user (adopsi SOMMERVILLE) = **kembali ke model `production_*` yang bersih**.
  Ini masuk akal & rendah-risiko karena backend-nya sudah ada di DA.

## SOMMERVILLE — RINGKAS
- ERP garment fokus manufaktur outsource ke vendor. 3 portal: **Admin, Vendor, Buyer**.
- Backend: `server.py` monolit **6.267 baris** + route kecil (buyer_portal, file_storage,
  pdf_exports, smart_import, websocket, data_management). **153 endpoint** `@api.*`.
- Frontend: **~55 komponen flat** di `components/erp/`, App.js **324 baris**
  (routing berbasis state + switch by role). Modul inti:
  ProductionPOModule, ProductionProgressModule, ProductionMonitoringModule,
  ProductionReturnModule, OverproductionModule (variance), Vendor/BuyerShipmentModule,
  InvoiceModule/PaymentModule/ManualInvoiceModule, VendorPortalApp, BuyerPortalApp,
  + Vendor* (Dashboard, Jobs, Progress, Receiving, MaterialRequests, MaterialInspection,
  DefectReports, VarianceReport, SerialTracking, ReminderInbox).

## FLOW / STATE MACHINE SOMMERVILLE
1. Admin buat **Production PO** (`production_pos`) + `po_items` + `po_accessories`.
2. Admin kirim material ke vendor → **vendor_shipments** (+items).
3. Vendor **terima & inspeksi** material/aksesoris (`vendor_material_inspections`);
   kalau kurang → auto **material_requests** (REQ-RPL-…).
4. Vendor produksi → **production_jobs**+items → catat **production_progress**
   (`produced_qty`, defect). Overproduction/underproduction = fitur SENGAJA
   (dicatat via **production_variances**).
5. Vendor kirim FG ke buyer → **buyer_shipments** (+items/dispatches).
6. Buyer terima; bisa retur → **production_returns**.
7. Admin invoice → **invoices** + **payments** (+adjustments/edit-requests).
Invarian penting (dari PRODUCTION_FLOW_AUDIT.md): I-1 produced ≤ available−defect;
I-2 shipped ≤ produced; I-3 return ≤ shipped−returned; I-5 produced vs ordered BEBAS.

## PETA INTEGRASI DENGAN PORTAL LAIN DA (kekhawatiran utama user)
### Aman (namespace cocok, satu keturunan)
- Semua koleksi `production_*`, `po_*`, `*_shipments`, `*_shipment_items`,
  `vendor_material_inspections`, `material_requests` → cocok dgn kontrak FE.

### Perlu jembatan/rekonsiliasi (extension DA yang SOMMERVILLE tak punya)
- **Finance GL**: DA menambah `POST /production-variances/{vid}/post-gl` +
  `/retry-posting` → post ke `rahaza_journal_entries`. Kalau adopsi variance
  SOMMERVILLE, **pertahankan/pasang ulang** bridge ini bila mau auto-jurnal.
- **rahaza_work_orders / HPP / WIP**: dipakai HR (labor) & Finance (WIP costing).
  Model SOMMERVILLE tak punya. Keputusan: buang (jadi island) atau bikin adapter.
- **Gudang (WMS)**: DA pakai `rahaza_materials/material_stock/issues`. SOMMERVILLE
  pakai model material sendiri (vendor_shipments+material_requests). Perlu adapter
  bila mau stok Produksi memotong stok Gudang.

### TABRAKAN koleksi generik (WAJIB hati-hati saat merge)
`users, roles, role_permissions, permissions` (auth DA beda: portal-based RBAC +
admin@garment.com/dewiaditya.id), `company_settings, attachments, activity_logs,
reminders, products, product_variants, garments, buyers, accessories`.
→ JANGAN timpa buta koleksi ini. Petakan role vendor/buyer SOMMERVILLE ke RBAC DA,
atau pertahankan auth DA & adaptasi modul SOMMERVILLE ke situ.

## STRATEGI ADOPSI (opsi)
- **Opsi 1 — Island bersih (tercepat, risiko rendah ke portal lain):**
  Pasang flow produksi SOMMERVILLE sebagai subsistem mandiri (pakai backend
  `production_*` DA yg sudah ada + FE SOMMERVILLE), jalan di atas auth DA. Belum
  auto-feed Finance/Gudang/HR — bridge dibangun belakangan sesuai kebutuhan.
- **Opsi 2 — Terintegrasi penuh:** Opsi 1 + pasang ulang bridge GL (variance→jurnal),
  material→Gudang, labor→HR. Lebih banyak kerja, tapi "nyambung".
- **Opsi 3 — Referensi desain:** ambil ide/alur SOMMERVILLE, re-implement di atas
  model DA. (Paling lama; tidak disarankan karena DA sudah punya backend `production_*`.)

Rekomendasi: **Opsi 1 dulu → lalu Opsi 2 bertahap.** Selaras dgn rencana user
refactor SOMMERVILLE dulu (pecah monolit + samakan auth/portal shell).

## FRONTEND ADOPTION — catatan
SOMMERVILLE FE = 55 komponen flat + Sidebar + App.js state-based (bukan portal shell DA).
DA FE = portal shell + `moduleRegistry.js` (80 id) + `onNavigate`. Adopsi FE = kerjaan
terbesar: re-home modul SOMMERVILLE ke portal shell DA ATAU mount sebagai sub-app
Produksi mandiri. Backend jauh lebih mudah (endpoint sudah ada di DA).

## PETA MENYELURUH SISTEM (whole-system map) — grounded ke kode

### Fakta arsitektur KUNCI (temuan baru)
`rahaza_work_orders` = **MESIN PRODUKSI TERPADU** untuk internal & maklon.
- Field `source` = "internal" | "maklon"; `model_id`, `order_id`, `maklon_order_id`, `bom_id`.
- source="maklon" → pakai *snapshot* produk (produk klien tak ada di master DA); skip lookup model.
→ Produksi & Maklon = PORTAL terpisah (model bisnis/finance/counterparty beda) TAPI
  BERBAGI mesin eksekusi produksi yang sama + lantai + Vendor CMT.

### MASTER DATA BACKBONE
- **RnD**: `dewi_rnd_styles` (desain) + `dewi_rnd_sample_requests` (sample; punya `model_id`/
  `style_id` utk internal ATAU `client_id` utk maklon). RnD melayani KEDUA portal.
- **Product Master (internal)**: `rahaza_models` (artikel/style) + `rahaza_boms` (BOM) +
  `rahaza_model_process_sop` (routing/SAM) + `rahaza_sizes`.
- **Maklon BOM**: `dewi_maklon_bom` / `dewi_maklon_bom_templates` (spesifik klien) + snapshot.

### DEMAND → WORK ORDER
- Marketing/Sales: `marketing_orders` (marketplace/KOL/livehost), `dewi_toko_orders` (online
  shop), `rahaza_orders` (sales internal). Maklon: `dewi_maklon_pos` (PO klien).
- Semua bermuara ke `rahaza_work_orders` (source internal/maklon).

### EKSEKUSI (mesin bersama)
Cutting → Sewing/CMT (lini internal ATAU **Vendor CMT**) → Finishing → QC → Packing → FG.
**ZONA CMT/VENDOR BERSAMA (penting):** internal (CMT External saat kapasitas kurang) DAN
maklon (subcontract) sama-sama kirim ke vendor. Koleksi: `vendor_shipments`, `dewi_cmt_*`
(lifecycle/packing/component_requests), `wh_cmt_dispatches`, role `cmt_vendor`, `dewi_cmt_payments`.

### HILIR
- Internal: FG → Gudang (`rahaza_fg_inventory`) → Fulfillment → kirim → Marketing (penjualan) →
  Finance: inventory→COGS→AR penjualan.
- Maklon: FG → dispatch ke KLIEN (surat jalan) → Finance: AR jasa (`rahaza_ar_invoices`/
  `dewi_maklon_invoices`) + DP.

### CROSS-CUTTING
- **Gudang**: material issue/return, FG receiving, CMT dispatch, opname.
- **Finance**: auto-jurnal (WIP/material/FG/AR/payroll) via 38 posting profiles.
- **HR**: operator assignment, absensi, shift, payroll piece-rate, KPI.

### IMPLIKASI ADOPSI SOMMERVILLE (KEPUTUSAN BESAR)
1. SOMMERVILLE = model "brand punya material → outsource ke VENDOR → kirim ke BUYER",
   pakai `production_pos`/`production_jobs`/`vendor_shipments`/`buyer_shipments` = MESIN
   PRODUKSI TERPISAH (bukan `rahaza_work_orders`).
2. Master produk SOMMERVILLE = `products`/`garments`/`product_variants` — SEDERHANA, **terputus**
   dari `rahaza_models`/RnD/Marketing/BOM DA.
3. **RISIKO INTI**: adopsi SOMMERVILLE apa adanya = memperkenalkan MESIN PRODUKSI KETIGA +
   MASTER PRODUK FORK → memutus rantai RnD→Model→Marketing & mesin WO terpadu.
   Pilihan rekonsiliasi:
   a. Petakan produksi SOMMERVILLE agar rujuk `rahaza_models` (+ RnD + demand marketing) — jaga rantai.
   b. Terima sebagai island utk flow CMT-vendor saja, lalu bridge ke Finance/Gudang.
4. **Maklon tetap terpisah** (material milik klien + pendapatan jasa) — SOMMERVILLE tak bisa
   merepresentasikan ini. Jangan digabung.
