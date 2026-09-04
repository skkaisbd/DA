# AUTONOMOUS EXECUTION PLAN — CV. Dewi Aditya ERP (finalized with user)

> User goal: satu sistem BERSIH & bekerja. Buang total sisa legacy (PO lama, WO, Order Produksi lama, modul PO Maklon lama) dari UI → SATU alur engine. Master-data-driven. Surat Jalan Internal berbasis BOM. Lalu perbaikan data (A5/G4), AI, dsb. Diakhiri DEMO manual ala user + seed script production.
>
> Aturan: verifikasi kode dulu (file:line) sebelum ubah; JANGAN klaim aman tanpa telusur konsumen; tiap tahap → testing_agent + rebuild static; backup sebelum migrasi data.

## KEPUTUSAN USER (final)
- A2=c (dev/preview; tak ada PO native → aman hapus UI PO Maklon lama; `dewi_maklon_pos` tetap sbg mirror Finance tak-terlihat).
- Cleanup = HAPUS TOTAL dari UI, sisakan 1 alur engine.
- Master Data: Internal `rahaza_models`+`rahaza_boms` → Portal Produksi; Maklon `dewi_maklon_buyer_catalog` → Portal Maklon. TAK BOLEH tercampur.
- SJ Internal: baris auto dari BOM aktif (yarn_materials + accessory_materials) × qty job + aksesoris manual.
- AI (A1): tulis semua kode + wrapper sentral; pakai Emergent LLM key saat dev; desain agar mudah switch ke ANTHROPIC key user (ganti env).
- A3: backup koleksi sebelum A5 & G4.
- B1–B12: sesuai rekomendasi.

## FASE (urutan final)
### FASE P — Produksi+Maklon CLEAN FLOW (INTI, dahulukan)
- P1. Peta semua menu produksi & maklon (portalNav + moduleRegistry): tandai LIVE vs LEGACY vs REDIRECT.
- P2. HAPUS dari UI: Order Produksi lama (RahazaOrdersModule + tombol Generate WO 404), menu Work Order, modul PO Maklon lama, PO/menu duplikat. Sisakan 1 alur:
      Internal: RnD→promote Master(rahaza_models)→BOM→**PO Internal**→**Production Jobs**→**Input Progress**→**Kirim Material (SJ BOM)**→CMT Receipt/FG→**Dispatch ke Buyer**.
      Maklon: **Master Produk Maklon**→**PO Maklon (engine)**→Terima Material Klien→Jobs→Progress→Dispatch.
- P3. PO tarik Master Data yang BENAR (Internal↔rahaza_models+BOM; Maklon↔buyer_catalog). Verifikasi & fix.
- P4. Surat Jalan Internal BOM-driven (yarn+accessory×qty + manual accessories).
- P5. testing_agent + manual smoke tiap perubahan.

### FASE A5 — split-brain rahaza_material_stock (+backup) → skema kaya kanonik
### FASE WIRE — A3/A6/E outbound → pending-movement + scan-out (seragamkan tulis stok)
### FASE G4 — merge 11 COA duplikat (+backup, canonical=DA_COA_SEED)
### FASE AI — WS-C wrapper sentral (Emergent→switchable ke Claude) + WS-D Smart Import + WS-B ReportsHub/Executive AI/gear
### FASE G2/G3 — catalog fallback foto master + redesign kartu
### FASE A124 — verifikasi A1/A2/A4 WS-A (yarn/fabric taxonomy, roll sync, aksesori 2-step); fix bila aman
### FASE F — build memory: SKIP (informational)

### FINAL — DEMO MANUAL ALA USER + SEED SCRIPT PRODUCTION
- Input manual step-by-step seperti user nyata (browser), ~3 item per portal, dari master (RnD utk internal) → sampai kirim buyer / masuk FG. Temukan bug → fix langsung.
- Buat seed script lengkap, idempoten, siap dijalankan di production.

## SUDAH SELESAI (sesi sebelumnya)
- B3 (RnD dashboard status), G1 (promote foto→master), P0 (Input Progress job-item). 9/9 E2E + testing_agent + live.

## LOG
### FASE P1 — DONE
Peta menu: prod-orders(RahazaOrders,404 GenerateWO)=LEGACY; prod-pos(EnginePO all)=DUP/langgar-separasi; prod-pos-internal=LIVE internal; maklon-pos-engine=LIVE maklon; maklon-po(MaklonPOModule)=LAMA; maklon-po-360=baca mirror(OK keep); prod-work-orders=EngineJobs(LIVE).

### FASE P2 — DONE & VERIFIED (screenshot live)
- portalNav: hapus `prod-orders`, `prod-pos` (Produksi); hapus `maklon-po` "PO Maklon Lama" (Maklon).
- moduleRegistry redirects: prod-orders→prod-pos-internal; prod-pos→prod-pos-internal; maklon-po→maklon-pos-engine; maklon-orders→maklon-pos-engine. (semua path/deep-link/drilldown mendarat ke engine; komponen legacy tak terjangkau UI; backend router tetap utk modul lain).
- Verifikasi: sidebar Maklon TIDAK ada "PO Maklon Lama"; build OK.

### FASE P3 — DONE & VERIFIED (screenshot live)
- Internal PO: sudah benar (rahaza/models). Maklon PO: DIUBAH dari `/products` generik → **`/dewi/maklon/buyer-catalog`** (master produk maklon), di-scope per buyer.
- ProductionPOModule: +state catalogItems, +fetchCatalog(clientId), buyer onChange→fetchCatalog+reset item, addItem +catalog_item_id, updateItem +cabang catalog_item_id (auto product_name/sku=artikel/cmt+selling price), openEdit→fetchCatalog, JSX maklon item: "Produk (Buyer Catalog)" + "Artikel Buyer" (readonly) + hint warna/size.
- Backend production_pos.py: simpan `catalog_item_id` (FK buyer_catalog). Item schema backward-compatible → mirror→Finance aman.
- Verifikasi live: buyer CV Bumi → dropdown katalog (Jaket Sport Bumi v1/BUMI-JKT-01) → auto Artikel/SKU/Selling 180k/CMT 45k + hint. ✅

### FASE P4 — DONE & VERIFIED (screenshot live)
- Backend: `GET /api/production-jobs/{job_id}/bom-material-lines` — agregasi yarn_materials (kg) + accessory_materials (pcs/unit) dari BOM aktif per job item × qty; return {lines, missing_bom}. Read-only (tidak menulis stok).
- Frontend `WMSDeliveryNotesModule.jsx`: +state jobs/selectedJobId/bomLoading, +loadJobs (business_type=internal), +handleFillFromBOM (APPEND baris BOM ke item terisi, nomor ulang; qty otomatis = per unit × qty job dari backend), +UI section "Isi dari BOM (Job Internal)" (Select job + tombol Isi dari BOM) di Create Dialog, +reset selectedJobId saat dialog close/create sukses.
- Verifikasi live (screenshot): pilih JOB-PO-INT-DEMO-3 (100 pcs) → 2 baris: Benang Cotton 30s 25 kg + Label Woven DA 100 pcs. Toast sukses. curl 2 job (DEMO-3=25kg/100pcs, DEMO-2=50kg/200pcs) ✅ qty terkalikan benar. esbuild+rebuild static OK, HTTP 200.
- Keputusan user: perilaku APPEND (bukan replace); qty otomatis dikalikan qty job; verifikasi cukup screenshot, testing menyeluruh di akhir.

### FASE A5 — DONE & VERIFIED (unifikasi kode; DB kosong → tanpa migrasi data)
- Temuan: 3 skema dlm 1 koleksi rahaza_material_stock: A=`{location_id,qty}` (kanonik ERP), B=Aksesoris `{location:{id,code},total_qty}` (7 file aktif), C=FG `{quantity,available_quantity,reserved_quantity}` (cmt_packing/fulfillment/unified_inventory).
- Keputusan user: KANONIK=`qty`+`location_id`; `total_qty`/`quantity` = alias jumlah fisik (mirror), `available_quantity`=qty-reserved, `reserved_quantity` reservasi FG. UNIFIKASI PENUH sekarang.
- Backup: koleksi `rahaza_material_stock_backup_A5_<ts>` (2 dok).
- Baru: `core/stock_schema.py` (SSOT helper: read_qty/read_available/read_reserved + inc_all_qty/set_all_qty rantai fallback lintas-skema).
- Aksesoris (7 file: stock/items/requests/loans/opname/purchase/dashboard): `_add_stock` kini $inc inc_all_qty(delta) (qty+total_qty+quantity) + $setOnInsert id(UUID)+location_id datar+nested location; `_stock_qty`/`_all_accessory_stock` baca via read_qty (fallback). Import core.stock_schema.
- FG cmt_packing.approve: $inc {**inc_all_qty(qty),available_quantity} + insert tambah qty/total_qty. fulfillment: dispatch $inc {**inc_all_qty(-qty),reserved_quantity:-qty}; allocate baca read_available (fallback).
- Reader: rahaza_sprint22 (cek ketersediaan WO, 2 titik) → read_qty + projeksi qty/total_qty/quantity; rahaza_fg_matrix matrix → read_qty/read_reserved.
- Writer kanonik lain (sudah benar, tak diubah): warehouse._sync_to_material_stock, rahaza_inventory_shared/_fg, fg_matrix_seed, admin_helpers, dewi_maklon, wms_receiving, production_*, maklon_seed, unified_inventory.
- Verifikasi: /app/tests/verify_a5_stock_unify.py → 18/18 PASS (accessory write→qty selaras; cross-read $sum:$qty lihat aksesoris; FG receive/reserve/dispatch jaga qty; fallback legacy). Backend restart bersih.

### FASE G4 — DONE & VERIFIED (dedup COA + fix orphan posting)
- Temuan: startup Phase 7D auto-seed 2 chart (SEED_TEMPLATE 4-digit + DA_COA_SEED 3-digit) → 274 akun, 11 duplikat by-name. Posting engine merujuk kedua chart (39+39 kode). Keputusan user: minimal & aman, kanonik=DA 3-digit.
- Backup: rahaza_coa_accounts_backup_G4_<ts> (274), rahaza_posting_profiles_backup_G4_<ts> (33).
- rahaza_coa.py: +DUP_TEMPLATE_CODES (dihitung by-name SEED_TEMPLATE ∩ DA_COA_SEED). seed_coa_accounts & seed_template skip 11 kode duplikat; parent inference pakai template_codes terfilter (hindari orphan parent).
- Remap rujukan posting 4-digit→DA 3-digit: 1-1101→1-110 (Kas Kecil), 1-1403→1-330 (WIP), 4-2100→4-910 (Bunga Bank). File: rahaza_posting_profiles, rahaza_posting, employee_expense_claims, dewi_maklon_finance, rahaza_petty_cash (fungsional) + komentar exceptions/bank_recon/employee_loans.
- Bonus fix orphan pra-existing (posting profile → akun tak ada): 4-2000 (penalty income) & 5-9100 (variance income) → 4-920 (Pendapatan di Luar Usaha Lainnya). File: rahaza_posting_profiles, rahaza_posting, dewi_maklon_finance, exceptions.
- Cleanup DB: hapus+re-seed rahaza_coa_accounts (274→263) & rahaza_posting_profiles (re-seed 33) via restart Phase 7D.
- Verifikasi: COA 263 akun, 0 duplikat by-name; posting profiles 36 kode → 0 MISSING di COA; semua kode lama (1-1101/1-1403/4-2100/4-2000/5-9100) absen. Smoke test 9 endpoint (coa/tree/acc-stock/dashboard/fg-matrix/fulfillment/production-jobs/posting-profiles) semua 200. Backend log bersih.

### FASE DEMO END-TO-END + SEED PRODUKSI — DONE
- Walkthrough semua portal (login dulu -> deep-link ?portal=&module=): 9 modul kunci (RnD design-hub/dashboard, prod-work-orders/pos-internal, wms-delivery-notes, fulfillment, fin coa/journal, maklon buyer-catalog/pos-engine) SEMUA termuat, 0 error konsol, 0 blank, 0 error boundary.
- testing_agent iteration_102 melaporkan "CRITICAL deep-link hilang setelah login" -> DIINVESTIGASI & DEBUNK sbg FALSE POSITIVE (repro langsung: login lalu deep-link -> modul termuat penuh; bug pada metodologi login testing agent, bukan app).
- Re-run /app/tests/seed_demo_produksi_maklon.py (pakai engine asli): Internal 3 PO + Maklon 3 PO + Vendor + Finance, 7/7 dokumen PDF valid. = integration test A5 (stok terpotong benar: yarn 725, label 4700) & G4 (COA) TANPA regresi.
- Baru: /app/tests/seed_demo_rnd_wms.py (via API asli) — RnD 4 style (draft/pending_owner_review/promoted->Model DA-PL03/maklon) + 2 SJ-INTERNAL (P4 'Isi dari BOM', 1 issued), PDF OK.
- Orchestrator 1-perintah: /app/scripts/seed_demo_all.sh (produksi/maklon lalu RnD+WMS).
- Verifikasi UI screenshot: RnD dashboard 'Menunggu Review'=1 (fix B3 data nyata); Surat Jalan list 2 SJ-INTERNAL (issued+draft) render rapi.
- STATUS: Semua portal terisi data & sehat. Tidak ada bug live nyata ditemukan.
- DITUNDA (persetujuan user, setelah demo): WS-C/WS-D (AI wrapper terpusat + Smart Import), WS-E/A3/A6 (scan-out gudang wh_pending_movements).
