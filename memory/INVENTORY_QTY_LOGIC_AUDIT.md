# AUDIT LOGIC QTY INVENTORY GUDANG — TEMUAN (2026-07-23)
Metode: baca core/stock_schema.py + semua writer/reader rahaza_material_stock + verifikasi LIVE (curl + DB).
Fokus: kebenaran qty stok (inbound/outbound/reserve/adjust/read).

## SKEMA QTY (core/stock_schema.py) — sudah didesain unified, tapi belum konsisten dipatuhi
- Kanonik: `qty` + `location_id` (flat). Alias: `total_qty`, `quantity` (mirror qty).
- `available_quantity = qty - reserved_quantity`. reserved alias: `reserved`.
- Helper: `inc_all_qty(d)` → {qty, total_qty, quantity} (⚠️ TIDAK termasuk available_quantity).
- Reader: read_qty/read_available/read_reserved (fallback chain).

## DUA "BENTUK" ROW FG YANG TIDAK MENYATU (akar masalah)
- **Schema A** `{material_id, location_id, qty}` — dibuat oleh: WMS scan-in (produksi internal), material issue RM, fg-issue. TANPA ownership/inventory_category/available_quantity.
- **Schema C** `{material_id, ownership, inventory_category, qty/total_qty/quantity, available_quantity, reserved_quantity}` (TANPA location_id) — dibuat oleh: CMT receive approve, seed; DIKONSUMSI oleh fulfillment (allocate/dispatch).

## BUG-INV-1 (CRITICAL) — FG produksi internal TIDAK BISA di-fulfill/kirim ke order marketing
- Scan-in FG produksi → Schema A (qty+location_id).
- `/api/fulfillment/inventory/available` query: `{ownership:'cv_da', inventory_category:'fg_internal', available_quantity>0}` → Schema A TIDAK cocok.
- BUKTI LIVE: `ZZTESTM01-HTM-M` (30 pcs, schema A) TIDAK muncul di fulfillment available; hanya 123-NVY-S/M (CMT, schema C) yang muncul.
- DAMPAK: FG diproduksi internal & diterima gudang, tapi tidak bisa dialokasikan/dikirim ke pesanan marketing. Fulfillment praktis hanya jalan untuk FG dari CMT/seed.
- File: routes/wms_receiving.py:450 (scan-in schema A), routes/fulfillment.py:197-220 (query schema C).

## BUG-INV-2 — Dua sistem reservasi terpisah; fulfillment abaikan reservasi manual
- Reservasi manual → collection `rahaza_fg_reservations` (rahaza_fg_matrix.py:380).
- Reservasi fulfillment → field `reserved_quantity` (fulfillment.py:216).
- FG matrix available = qty - (rahaza_fg_reservations + reserved_quantity) [gabung dua sumber].
- Fulfillment available = `available_quantity` = qty - reserved_quantity (ABAIKAN rahaza_fg_reservations).
- DAMPAK: FG yang direservasi manual masih bisa dialokasi fulfillment → over-allocation/potensi dobel-kirim. Angka "available" beda antara FG Matrix vs Fulfillment.

## BUG-INV-3 — FG issue vs Fulfillment beroperasi di row berbeda
- fg-issue (rahaza_inventory_fg.py:93) decrement `{material_id, location_id}` (schema A) — hanya `qty`.
- FG dari CMT/fulfillment = schema C (tanpa location_id) → fg-issue tak menemukannya; cek ketersediaan baca row schema A yang salah.
- DAMPAK: jalur pengeluaran FG tidak konsisten tergantung asal FG.

## BUG-INV-4 — available_quantity bisa desync (footgun inc_all_qty)
- inc_all_qty TIDAK update available_quantity; read_available baca available_quantity DULU.
- Bila row schema C di-inc qty via inc_all_qty saja (tanpa juga inc available_quantity), available jadi basi.
- Fix CMT (dewi_cmt_packing) SUDAH benar (inc available_quantity terpisah). Tapi pola ini rawan utk writer lain.
- Writer yang inc/dec hanya `qty` (bukan alias): material issue (rahaza_inventory_issues.py:179), fg-issue (rahaza_inventory_fg.py:95) → alias total_qty/quantity bisa basi bila row punya alias.

## BUG-INV-5 — Field min-stock tidak konsisten (alert bisa tidak menyala)
- Alert helper (rahaza_inventory_shared.py:78) baca HANYA `mat.get('min_stock')`.
- Reader material-stock (rahaza_inventory_stock.py) baca 3 field: min_stock_qty, min_stock_percentage, min_stock (legacy).
- Auto-create FG (fix CMT) set `min_stock_qty`. → Alert low-stock helper takkan lihat min_stock_qty → alert tidak nyala utk material tsb.

## READER — status
- FG Matrix (rahaza_fg_matrix.py): AGREGASI benar (sum semua row per material_id via read_qty) → TOTAL qty benar walau row terfragmentasi. ✅ (tapi available kena BUG-INV-2)
- material-stock list (rahaza_inventory_stock.py): tampilkan row MENTAH (tidak agregasi) → material terfragmentasi tampil sbg beberapa baris; baca `s.get('qty')` langsung (bukan read_qty).
- fulfillment available: query schema C saja (BUG-INV-1).

## STATUS DATA LIVE (saat audit)
- 3 row stok: 1 schema A (ZZTESTM01-HTM-M 30pcs, produksi internal), 2 schema C (123-NVY-S/M CMT).
- Belum ada material dengan 2 skema sekaligus (belum ada fragmentasi aktif), invariant available==qty-reserved OK (0 pelanggaran).
- Tapi bug bersifat ARSITEKTURAL → pasti muncul begitu FG internal perlu dikirim / satu material diterima dari 2 sumber.

## USULAN PERBAIKAN (BELUM dieksekusi — tunggu arahan)
1. (INV-1) Satukan bentuk row FG: saat scan-in FG (produksi internal) SET juga ownership='cv_da', inventory_category='fg_internal', available_quantity (=qty), reserved_quantity=0. ATAU ubah query fulfillment agar mengagregasi lintas skema (by material_id) & pakai read_available. Rekomendasi: normalisasi di 1 helper tulis-stok tunggal (single writer) yg dipakai SEMUA inbound.
2. (INV-2/3) Satukan reservasi: pilih SATU sumber (reserved_quantity field ATAU rahaza_fg_reservations), fulfillment & matrix pakai sumber sama.
3. (INV-4) Wajibkan semua writer via helper set_all_qty/inc_all_qty yang JUGA memelihara available_quantity, atau selalu hitung available = qty - reserved saat baca (jangan simpan available_quantity).
4. (INV-5) Seragamkan field min-stock (pakai min_stock_qty di semua tempat) + alert helper baca ketiganya.
5. Idealnya: buat modul `stock_service` tunggal (add/issue/reserve/release/move) yang dipakai SEMUA route → hilangkan split-brain.

## ═══ AUDIT 3 FLOW (barang masuk produksi / masuk purchase / semua keluar) — 2026-07-23 ═══

### FLOW 1 — MASUK DARI PRODUKSI (FG inbound) — 2 LANGKAH (pending → scan-in)
Pemicu: (a) production_execution.py POST /production-progress (job internal, per completed_quantity, cap kumulatif ≤ qty order) → create_fg_pending_inbound_for_variant; (b) rahaza_production.py packing event → sama.
Path: ensure_fg_material (FG code==SKU) → helper_create_pending_inbound_fg → wh_pending_movements(status=pending) → [SCAN-IN gudang /api/wms/pending/{id}/scan-in] → rahaza_material_stock SCHEMA A {material_id,location_id,qty} + rahaza_fg_movements + (opsional) put-away wh_positions.
Bug/risiko:
- Hasil = schema A → BUG-INV-1 (tidak bisa di-fulfill/kirim ke order marketing).
- DUA pemicu (progress + packing). Jika kedua sistem dipakai utk job sama → double pending inbound (double-count). Perlu dipastikan hanya satu jalur aktif per job.
- Butuh scan-in manual; kalau varian tak ter-resolusi → di-skip (FG receipt hilang, hanya warning).

### FLOW 2 — MASUK DARI PURCHASE (RM inbound) — 1 LANGKAH (legacy, langsung)
Pemicu: rahaza_po.py (PO approved) → Goods Receipt di warehouse.py (LEGACY "Penerimaan Barang") → _sync_to_material_stock → rahaza_material_stock SCHEMA A {material_id,location_id,qty} + update_po_received_qty.
GRN QC (rahaza_grn_qc.py): inspeksi received/accepted/rejected — TERPISAH, TIDAK menyentuh stok.
Bug/risiko:
- BUG-INV-8: QC accept/reject TIDAK ditegakkan ke stok. Legacy GR menambah qty received, bukan qty accepted → unit rejected bisa tetap terhitung stok (over-count). QC & stok jalan sendiri-sendiri.
- Inkonsisten dgn FLOW 1: purchase = 1 langkah via modul LEGACY (deprecated); produksi = 2 langkah via sistem BARU (scan-in). Dua mekanisme penerimaan berbeda.

### FLOW 3 — SEMUA TIPE KELUAR
1. Issue RM → produksi (rahaza_inventory_issues.py): dec {material_id,location_id, qty>=req} inc qty. ATOMIC race-safe. Schema A. ✅ BAGUS.
2. Dispatch FG → buyer (fulfillment allocate reserve + wms scan-out outbound_fg): schema C (available_quantity/reserved_quantity), dec by stock_id + release reserved. Hanya jalan utk FG schema C.
3. FG issue (rahaza_inventory_fg.py fg-issue): dec {material_id,location_id} qty (schema A) — BEDA row dari fulfillment (BUG-INV-3).
4. Dispatch material → CMT (wms scan-out outbound): dec {material_id,location_id}.
5. RETUR material produksi (production_material_returns.py /receive): **BUG-INV-6 (CRITICAL)** → inc field PHANTOM `qty_available`/`qty_on_hand` (BUKAN `qty` kanonik). read_qty tak baca field ini → material yang diretur TIDAK benar-benar kembali ke stok terpakai. Stok hilang. Key hanya {material_id} (tanpa location_id).
6. Opname adjustment (wms_opname.py DEPRECATED + wms_opname2 SSOT): +/- qty by {material_id,location_id}. Dua sistem opname (duplikat).
7. Legacy issue (warehouse.py): sync bridge ke schema A.
8. **BUG-INV-7 (HIGH/security):** POST /api/wms/stock/reset-all — require_auth TANPA role check → user mana pun bisa NOL-kan SEMUA stok. Selain itu hanya set qty=0, tidak nol-kan available_quantity (schema C tetap tampak ada stok → inkonsisten).

### RINGKASAN BUG BARU PASS INI
- BUG-INV-6 (CRITICAL): retur material pakai field salah (qty_available/qty_on_hand) → retur tak menambah stok.
- BUG-INV-7 (HIGH): reset-all tanpa role guard + tak nol-kan available_quantity.
- BUG-INV-8 (MEDIUM): GRN QC accept/reject tak ditegakkan ke stok (over-count risk).
- Konfirmasi: dual receiving (produksi 2-langkah baru vs purchase 1-langkah legacy), dual opname (deprecated vs opname2), double-trigger inbound produksi.


## ═══ AUDIT ANTI-PATTERN (grep sistematis 6 kategori) — 2026-07-23 (PASS 2) ═══
Metode: grep seluruh routes/utils/core + inspeksi file suspect + verifikasi mana yang aktif (server.py include_router).
Fokus: temukan POLA berulang "SSOT sudah dibenahi di jalur create, tapi consumer lama masih pakai lookup/format lama".

### 🔴 BUG-INV-9 (HIGH, CONFIRMED) — Shipment FG pakai lookup FG legacy `FG-{model}-{size}` (tanpa warna) → stok TIDAK turun
- File: routes/rahaza_shipments.py:342 → `code = f"FG-{m_doc['code']}-{s_doc['code']}"`.
- Alur: shipment approve → resolve FG dari rahaza_work_orders (hanya model_id+size_id, TANPA warna) → bangun kode legacy `FG-MODEL-SIZE` → cari `rahaza_materials.code == kode` → TIDAK KETEMU (FG kanonik = `{MODEL}-{WARNA}-{SIZE}` tanpa prefix) → `mat_doc None` → `continue` (SILENT SKIP).
- DAMPAK: pengiriman FG bisa selesai (COGS JE ke-post, AR invoice draft dibuat) TAPI pending outbound FG TIDAK dibuat → tidak ada Scan-Out → **stok FG tak pernah berkurang**. Kirim barang tapi stok tetap.
- Catatan tambahan: WO tidak punya dimensi warna → walau prefix `FG-` dihapus, lookup tetap gagal utk model multi-warna. Butuh resolve warna dari variant/po_item, bukan dari WO.
- Catatan: rahaza_shipments ditandai di server.py:617 sbg "superseded (legacy)" oleh delivery-order baru → mungkin route lama, TAPI masih terdaftar (include_router server.py:1235) → masih bisa dipakai.

### 🔴 BUG-INV-10 (HIGH, NEW) — Opname "resmi" (opname2) TIDAK menyentuh rahaza_material_stock
- File resmi UI: WMSOpnameEnhancedModule.jsx → `/api/wms/opname2` (routes/wms_opname2.py, prefix `/api/wms/opname2`).
- wms_opname2.py approve (baris 359-406): apply adjustment HANYA ke `wh_positions.qty` (baris 375-378). TIDAK ADA update ke `rahaza_material_stock` (dikonfirmasi: opname2 tidak muncul sama sekali di daftar writer rahaza_material_stock).
- Bandingkan: wms_opname.py LAMA (deprecated, prefix `/api/wms`) — finalize update KEDUANYA: wh_positions + rahaza_material_stock (baris 306-307, 368/375).
- DAMPAK: migrasi opname → opname2 (ditetapkan sbg SSOT/resmi) MENGHILANGKAN koreksi stok kanonik. Koreksi hasil stok-opname via modul resmi TIDAK PERNAH sampai ke `rahaza_material_stock` (yang dibaca FG Matrix, fulfillment, viewer stok, marketing catalog). Selisih fisik dihitung, disetujui, tapi stok "sebenarnya" tak berubah. → ini akar besar ketidakpercayaan qty.

### 🔴 BUG-INV-11 (CRITICAL, NEW, ARSITEKTURAL) — DUA ledger qty paralel: `rahaza_material_stock` (level material) vs `wh_positions.qty` (level bin) — tidak pernah direkonsiliasi
- Scan-in (wms_receiving.py:449 + 479) menambah KEDUANYA: rahaza_material_stock.qty DAN wh_positions.qty (bila posisi discan). Dua counter utk unit fisik yang SAMA.
- Scan-out (wms_receiving.py:566/582 + 605) mengurangi keduanya (bila posisi discan).
- TAPI mayoritas flow lain HANYA sentuh SATU sisi:
  - Fulfillment allocate/dispatch, fg-issue, material-issue, CMT receive, retur material, GR purchase → HANYA rahaza_material_stock.
  - Opname2 → HANYA wh_positions (BUG-INV-10).
- Tidak ada proses rekonsiliasi antara kedua ledger → DIJAMIN drift begitu ada operasi non-scan. wh_positions cepat basi (semua issue/fulfillment tak update posisi); rahaza_material_stock tak pernah dikoreksi opname resmi.
- DAMPAK: pertanyaan "berapa stok sebenarnya?" punya 2 jawaban berbeda (material-level vs bin-level) yang makin lama makin menyimpang. Inilah sumber utama "qty gudang tidak bisa dipercaya".

### 🟠 BUG-INV-12 (MEDIUM, NEW) — Reader keyed `location_id` (Schema A) tidak melihat stok Schema C (FG dari CMT/fulfillment)
- marketing_kol_ops.py:115/187/256, marketing_kol_portal.py:85/107, dewi_maklon.py:536, rahaza_inventory_stock.py:212/236 → query `{material_id, location_id}` (Schema A).
- FG dari CMT/fulfillment = Schema C (TANPA location_id) → reader ini balikin 0/tak ketemu → KOL/portal tampil stok 0 padahal FG ada. Keluarga masalah sama dgn BUG-INV-1/INV-3 (Schema A vs C tidak menyatu di reader).

### 🟡 BUG-INV-13 (LOW-MEDIUM, NEW) — Fallback SKU po_item drop warna
- File: routes/production_pos.py:481 → `sku_new = rv.sku or variant.sku or raw.sku or f"{model.code}-{msize.code}"` (fallback terakhir TANPA warna).
- Prioritas benar (rv.sku kanonik dipakai duluan), tapi fallback `{MODEL}-{SIZE}` melanggar identitas kanonik (warna wajib). Bila terpakai → po_item.sku tanpa warna → risiko mismatch saat resolve FG di penerimaan. Latent data-quality bug.

### 🟡 RESIDUAL (LOW) — dewi_cmt_packing.py:449 fallback `FG-{sku}`
- Sudah diperbaiki (helper _ensure_fg_for_cmt_line). Fallback `f"FG-{sku}"` HANYA jalan bila helper return None. Risiko rendah tapi jalur pembuatan orphan `FG-*` masih ada sbg fallback defensif.

### KONFIRMASI ULANG temuan lama pass ini
- BUG-INV-7 (reset-all): dikonfirmasi wms_receiving.py:786 → `require_auth` SAJA (tanpa role check) + hanya set `qty=0` (TIDAK total_qty/quantity/available_quantity/reserved_quantity) → row Schema C tetap tampak available.
- BUG-INV-5 (min-stock): dikonfirmasi rahaza_inventory_shared.py:78 baca hanya `min_stock`; total low-stock jumlahkan `r.get('qty')` mentah (bukan read_qty).
- Scan-in (wms_receiving.py:453) pakai raw `$inc:{qty}` (BUKAN inc_all_qty) → alias total_qty/quantity bisa basi (footgun BUG-INV-4).

### POLA WRITER STOK (fragmentasi key) — ringkasan
- Schema A flat `{material_id, location_id}` : shared _add_stock, scan-in/out, fg-issue, material-issue, warehouse GR, transfer.
- Schema B nested `{material_id, location.id}` + `location:{id,code}` : SEMUA writer aksesoris (dewi_accessories_*._add_stock:86). Reader aksesoris query `location.code`. → row aksesoris & row ERP flat bisa terpisah utk material sama.
- Schema C `{material_id, ownership, inventory_category}` (tanpa location_id) : CMT receive, fulfillment, seed.
- Tidak ada single-writer tunggal yang dipakai SEMUA. rahaza_inventory_shared._add_stock ada tapi hanya sebagian route pakai.

### DEAD CODE (tidak aktif — TIDAK di-include_router; harap dihapus utk hindari kebingungan, bukan bug live)
- routes/_archive/rahaza_multistage/rahaza_bundles_backup.py:630 & rahaza_bundles_rework.py:208 → `FG-{model}-{size}` (arsip, tidak dipakai).
- routes/dewi_accessories_full_backup.py → tidak di-include.
- routes/fg_matrix_seed.py → seed, tidak di-include (`FG-MAIN` = kode lokasi seed, bukan SKU FG).

### DESTRUCTIVE ENDPOINT lain (di luar inventory, catat utk review role-guard)
- delete_many({}) unconditional: dewi_onboarding.py:427-428, approval_multilevel.py:347, dewi_lms.py:404-406, dewi_recruitment.py:667-668, rahaza_coa.py:570, marketing_reports.py:479. Perlu dicek apakah cuma seed/reset admin & apakah ada role guard. (Bukan qty inventory, prioritas rendah utk task ini.)

### ═══ RINGKASAN PRIORITAS (untuk keputusan user — BELUM ADA FIX) ═══
CRITICAL:
- BUG-INV-11: dual ledger material_stock vs wh_positions (akar drift) — arsitektural, perlu keputusan strategi (single source of truth).
- BUG-INV-1: FG produksi internal (Schema A) tak terlihat fulfillment (Schema C).
- BUG-INV-6: retur material tulis field phantom (qty_available/qty_on_hand) → stok hilang.
HIGH:
- BUG-INV-9: shipment FG lookup legacy → stok tak turun saat kirim.
- BUG-INV-10: opname resmi (opname2) tak koreksi stok kanonik.
- BUG-INV-7: reset-all tanpa role guard + zero-out tak lengkap.
MEDIUM:
- BUG-INV-2/3: dua sistem reservasi + outbound key beda.
- BUG-INV-8: GRN QC accept/reject tak ditegakkan ke stok.
- BUG-INV-12: reader location_id tak lihat Schema C.
LOW:
- BUG-INV-4/5: alias/available desync & field min-stock; BUG-INV-13 fallback sku tanpa warna; residual FG- fallback CMT; dead code cleanup.

AKAR TUNGGAL yang menjelaskan hampir semua: **tidak ada satu "stock service" tunggal** — banyak writer/reader dgn skema key berbeda (A/B/C) + dua ledger (material_stock vs wh_positions) + refactor SSOT hanya menyentuh jalur create, consumer lama masih pakai format/lookup lama.
