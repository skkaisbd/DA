# AUDIT PORTAL GUDANG — TEMUAN (BACKLOG, BELUM DIPERBAIKI)
Tanggal: 2026-07-23 · Metode: baca kode (portalNav/moduleRegistry/komponen) + test render 19 modul + curl endpoint live.
Status: SEMUA MODUL LOAD tanpa crash/error-boundary. Masalah bersifat DUPLIKASI + LEGACY/SSOT DISCONNECT + beberapa bug fungsional.

## AKAR MASALAH
Ada DUA sistem gudang paralel yang hidup bersamaan:
- **LEGACY**: endpoint `/api/wms/legacy/*` & `/api/warehouse/*` → koleksi `warehouse_locations`, `warehouse_stock` (ditandai "deprecated" di backend).
- **SSOT/BARU**: `/api/wms/*` (buildings/zones/racks/positions/pending) + `/api/rahaza/*` (materials/material-stock/material-issues) → koleksi `rahaza_materials`, `rahaza_material_stock`, `wh_buildings/wh_zones/wh_racks/wh_positions`.
Banyak menu masih menunjuk ke modul LEGACY → data terpecah & duplikat.

Bukti data terpecah (live):
- Lokasi: LEGACY `wms/legacy/locations`=**25** vs BARU `wms/buildings`=1, `wms/zones`=1, `wms/racks`=1.
- Stok: LEGACY `wms/legacy/stock`=**0** vs SSOT `rahaza/material-stock`=**1 (30 pcs FG ZZTESTM01-HTM-M)**.
- Dashboard KPI legacy=0, receiving legacy=2, smart-reorder legacy=5.

## A. DUPLIKASI FUNGSI (menu ganda utk pekerjaan sama)
A1. **Buat/Setup Struktur Gudang — 2 tempat, DATA TERPISAH**
   - `wh-bin` "Lokasi Bin" (LocationsModule) → LEGACY `/api/wms/legacy/locations` (25 lokasi, model datar warehouse/zone/rack/bin).
   - `wms` "Scanner → Struktur Gudang" (StructureTab) → BARU `/api/wms/buildings|zones|racks` (hierarki, 1/1/1).
   → INI "membuat gudang ada 2 / pengaturan gudang ada 2".

A2. **Penerimaan Barang (Receiving) — 2 tempat**
   - `wh-receiving` "Penerimaan Barang" (ReceivingModule) → LEGACY `/api/wms/legacy/receiving` (2 receipt).
   - `wms` "Scanner → Receiving/Scan" → SSOT `/api/wms/pending/{id}/scan-in`. (FG produksi masuk lewat sini.)

A3. **Penyimpanan (Put-Away) — 2 tempat**
   - `wh-putaway` "Penyimpanan" (PutAwayModule) → LEGACY `/api/wms/legacy/putaway` + `/legacy/stock`(=0) → tampil "No stock available".
   - `wms` put-away saat scan-in (scan barcode posisi) → SSOT `wh_positions`.

A4. **Lihat Stok — 2 view dalam 1 hub (+ legacy)**
   - `wms-stock-hub` tab "Viewer Stok (Unified)" (UnifiedInventoryModule) → `/api/wms/stock/unified`.
   - `wms-stock-hub` tab "Stok & Pergerakan" (RahazaStockModule) → `/api/rahaza/material-stock`.
     (Keduanya baca `rahaza_material_stock` tapi endpoint & tampilan beda.)
   - `wh-putaway` legacy stock (0) = view stok ketiga (legacy).

A5. **Opname Stok — referensi berlapis (sebagian sudah di-dedup)**
   - `wms-stock-hub` tab "Opname Stok" (WMSOpnameEnhancedModule) = RESMI (`/api/wms/opname`).
   - `wms` tab "opname" → notice "sudah pindah" + tombol redirect (BERFUNGSI: `wms-opname-enhanced` terdaftar). Inkonsistensi UX ringan (mengarah ke modul standalone, bukan tab hub).
   - `wh-opname` (redirect ke wms-opname-enhanced, tak tampil di nav) + `accessories-opname` (domain aksesoris terpisah).

## B. LEGACY vs SSOT DISCONNECT
B1. **Dashboard Gudang (warehouse-dashboard)** mencampur LEGACY (`/wms/legacy/dashboard-kpi`=0, `/legacy/stock`=0, `/legacy/locations`=25) + SSOT (`/rahaza/materials`, `/wms/pending/summary`, `/wms/buildings`) → KPI tidak konsisten (sebagian nol padahal SSOT ada data).
B2. **Alert & Reorder (warehouse-smart)** → LEGACY `/api/warehouse/*` (alerts=0, smart-reorder=5). Perlu dipastikan sinkron dgn reorder SSOT (`/api/rahaza/materials/reorder-alerts`).
B3. **ReceivingModule** juga menulis stok ke sistem legacy saat "Confirm Received" (banner UI menyebut sync ke Inventory) — perlu dicek agar tidak double-count vs SSOT.

## C. BUG FUNGSIONAL SPESIFIK
C1. **Unified Viewer salah label**: FG (type=fg) tampil kategori "raw_material" + NAMA KOSONG. Akar: `/api/wms/stock/unified` baca `rahaza_material_stock` TANPA JOIN ke `rahaza_materials` → `setdefault('inventory_category','raw_material')` (unified_inventory.py:123). Data DB benar.
C2. **FG barcode label 404**: `/api/wms/fg/{id}/label-pdf` baca koleksi KOSONG `rahaza_fg_matrix` (0 docs) — bukan SSOT `rahaza_materials`. (wms_fg_labels.py:230)
C3. **Tidak ada tombol cetak barcode FG & Material di UI**: backend material `/api/wms/materials/{id}/label-pdf`=200 (jalan) & FG=404, tapi tak ada tombol di FG Inventory / Master Material. Hanya label RAK yang ada tombol (WMSModule Struktur Gudang).
C4. **Put-away ke rak belum teruji end-to-end**: butuh struktur (rak/bin) di sistem BARU. Ada 25 lokasi LEGACY tapi hanya 1 rak BARU → user bisa salah bikin di sistem legacy yg tak terpakai scan-in.

## D. CATATAN TAMBAHAN
- `wh-accessory-ops` (Operasi Aksesoris) = redirect ke Portal Aksesoris (sudah di-dedup, benar).
- FG master SSOT SEHAT: 19 FG kanonik `{MODEL}-{WARNA}-{SIZE}`, 0 legacy `FG-`.
- Alur produksi→scan-in→stok SSOT TERBUKTI jalan (RCV-00004, 30 pcs).

## USULAN ARAH (untuk dibahas, BELUM dieksekusi)
1. Tetapkan SSOT gudang = sistem BARU (`/api/wms/*` hierarki + `/api/rahaza/*`).
2. Pensiunkan modul LEGACY dari nav: `wh-receiving`, `wh-putaway`, `wh-bin` (atau rewire ke SSOT).
3. Satukan "Lihat Stok" jadi 1 view kanonik; perbaiki Unified Viewer (C1).
4. Perbaiki FG label (C2) + tambah tombol cetak barcode FG/Material (C3).
5. Bersihkan Dashboard Gudang (B1) agar 100% SSOT.
6. Migrasi/arsip 25 lokasi legacy bila perlu.

## FIX #1 — CMT Receive (Terima FG dari CMT) — SELESAI & TERVERIFIKASI (2026-07-23)
User report: "pengiriman cmt ke da, tidak bisa terima, hanya ada list tidak ada action".
Akar: endpoint approve `/api/prod/cmt-receipts/{id}/approve` posting FG stock ke id orphan `FG-{sku}` (format legacy, BUG-1 class) → terputus dari FG master SSOT (rahaza_materials code==SKU, id=UUID) → FG hasil terima tidak muncul di FG Inventory/stock.
Fix (routes/dewi_cmt_packing.py): tambah helper `_ensure_fg_for_cmt_line()` → resolve_variant(sku) → ensure_fg_material (SSOT); fallback get-or-create FG master code==SKU. Stock diposting ke material_id UUID asli + backfill material_name/code.
Verifikasi testing_agent iteration_149: backend 100% (8/8), frontend actions berfungsi. FG stock kini di UUID asli (bukan FG-*), FG master code==SKU dibuat, no orphan. Alur UI list→action→editor→submit→approve berfungsi & discoverable.
Catatan: da-cmt-receive UI SUDAH punya action ("Proses ▸"/"Lihat ▸" → editor → Submit/Approve) — bukan hilang; masalah utama adalah stok terima mendarat di tempat salah (kini diperbaiki).
