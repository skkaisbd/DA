# RnD ↔ Master Product ↔ Gudang ↔ Produksi Internal ↔ Marketing — SSOT Fix Plan

> Sesi 2026-07-22. Fokus: memastikan struktur data produk/varian benar & SSOT jelas
> lintas portal, memperbaiki bug/logic salah, tanpa duplikasi & regresi.
> DB saat clone: FRESH (hanya 5 sizes seed) → fix-forward, tanpa migrasi data legacy.

## Keputusan User (kanonik — JANGAN dilanggar)
1. **SKU/FG kanonik = `{MODEL}-{WARNA}-{SIZE}`** (uppercase, TANPA prefix "FG-"), dipakai SERAGAM
   di Produksi Internal → Gudang → Marketing. Pastikan tidak merusak flow produksi (auto-tambah qty).
2. **Selalu 3 bagian**: "All Size" → size code `ALLSIZE`; **warna WAJIB** dipilih.
3. **FG master dibuat KEDUANYA**: (a) otomatis saat generate varian (FG kosong, stok 0),
   (b) lazy saat output produksi masuk (tinggal menambah stok pada FG yg kodenya == SKU).
4. **Kerjakan semua** (BUG-1, BUG-2, GAP-3..GAP-6) berurutan.

## SSOT Kanonik (target)
```
RnD Style (dewi_rnd_styles) --promote--> rahaza_models (product header SSOT)
   + rahaza_colors (warna master) + rahaza_sizes (size master, + ALLSIZE/STANDAR/JUMBO)
   --> rahaza_model_variants (VARIAN SSOT: model×warna×size → SKU `{MODEL}-{WARNA}-{SIZE}`)
       --> FG rahaza_materials(type='fg', code == variant.sku) + rahaza_material_stock (stok fisik SSOT)
           --> marketing_catalog_items (Toko: variant_id→variant_sku→FG by code; stok & HPP tersinkron)
```
Satu-satunya tempat membangun SKU & membuat FG internal = `utils/variant_ssot.py`.

## Temuan (grounded di kode) yang diperbaiki
- **BUG-1 (KRITIS)** `rahaza_production.py:657` packing → FG `FG-{MODEL}-{SIZE}` (buang warna, prefix salah).
  Juga active job flow (`production_execution.py`) TIDAK membuat FG fisik sama sekali.
- **BUG-2 (TINGGI)** `production_internal_adapter.py:519` SKU `{MODEL}-{SIZE}` (buang warna).
- **GAP-3 (TINGGI)** RnD punya `dewi_rnd_variants` paralel; promote tidak bikin `rahaza_model_variants`/FG.
- **GAP-4 (TINGGI)** generate varian tidak bikin FG master (konvensi sku==fg code tak pernah terpenuhi).
- **GAP-5 (SEDANG)** sizes generik S/M/L/XL; DA butuh Standar/Jumbo/ALLSIZE. techpack POM hardcode.
- **GAP-6 (SEDANG)** promote tak bawa spec techpack (BOM/konstruksi/measurement/warna).

## Fase Implementasi
- **F0** `utils/variant_ssot.py`: `build_variant_sku`, `ensure_fg_material`, `create_fg_pending_inbound_for_variant`.
- **F1 (BUG-1/2)**: FG receipt per-varian (canonical SKU) di active job flow (progress → pending inbound → scan-in);
  perbaiki legacy packing path; PO-from-order SKU pakai warna.
- **F2 (GAP-4)**: generate/create varian → `ensure_fg_material` (FG kosong).
- **F3 (GAP-3)**: promote RnD → generate `rahaza_model_variants` + FG dari varian RnD; `dewi_rnd_variants` = draft.
- **F4 (GAP-5/6)**: size master + ALLSIZE/STANDAR/JUMBO; propagate spec techpack saat promote.
- **POC** `poc_variant_ssot.py`: uji rantai penuh via API; fix sampai hijau.
- **FE**: koherensi UI untuk flow yg berubah.
- **TEST**: testing_agent_v3 end-to-end.

## Prinsip Anti-Regresi
- Idempoten (create FG cek `code`; dedupe pending by source_id).
- Resolusi FG: coba canonical SKU dulu, fallback code lama (backward-compat baca).
- Tidak double-count: active job flow yang jadi jalur resmi FG receipt internal (legacy packing dibuat konsisten identitas saja).

## STATUS: SELESAI ✅ (2026-07-22)
- F0–F4 implemented. POC `poc_variant_ssot.py` = **17/17 PASS**.
- testing_agent_v3 (iteration_146) = **100% backend (25/25)**, tanpa regresi, tanpa critical bug.
- Bukti kunci:
  - GAP-4: generate varian → FG `type='fg'` code==SKU otomatis (+linkage eksplisit).
  - BUG-1: output produksi internal → WMS pending inbound per-varian → scan-in → stok FG (code==SKU dgn WARNA).
  - BUG-2: SKU po_item internal = {MODEL}-{WARNA}-{SIZE}.
  - GAP-3: promote RnD → rahaza_model_variants + FG kanonik dari varian RnD.
  - GAP-6: construction_notes techpack → rahaza_models.sop_steps (dibaca Panduan Produksi).
  - Marketing: item from-FG link by variant SKU + snapshot stok benar.
- FE: `ProductionPOModule.jsx` — item internal WAJIB pilih varian (warna+size) agar rantai FG aktif.
- Catatan: FG code lama `FG-{MODEL}-{SIZE}` sudah TIDAK dibuat lagi (legacy packing dirutekan ke helper SSOT).
- BELUM dikerjakan (track terpisah, techpack Excel): importer Excel V5, construction per-poin terstruktur di UI RnD,
  penggunaan bahan per-size + kombinasi, size-category matrix Standar/Jumbo penuh. Menunggu arahan user.

## TRACK TECHPACK EXCEL V5 — SELESAI ✅ (2026-07-22, sesi lanjutan)
Scope disetujui user: (a) Importer Excel V5, (b) Construction per-poin terstruktur, (c) Penggunaan Bahan per-size + kain kombinasi.
- **Parser** `utils/techpack_excel.py`: 19 produk, 0 error (handle warna `;`, material `&`, konsumsi + Kombinasi (koma/spasi),
  ukuran per-kategori dinamis, size dari kolom konsumsi). 
- **Importer** `routes/dewi_rnd_techpack_import.py` (didaftarkan di `dewi_rnd.py`):
  `POST /api/dewi/rnd/techpack/import/preview` (read-only) & `/import/commit` (upsert style+varian+techpack, idempotent by style_code).
  Warna → rahaza_colors master (kode unik anti-collision: POL/POL2/POL3).
- **Schema techpack diperluas** (`dewi_rnd_hpp.create_tech_pack` + generic PUT): `construction_points[]` (b),
  `fabrics[]` (main+combination) & `fabric_consumption[]` per-size (c), `size_columns[]` dinamis (STANDAR/JUMBO/ALLSIZE), `measurements:[{point,values:{cat:val}}]`.
- **Frontend** `RnDTechPackModule.jsx` (Tab "Tech Pack Manager"): tombol Import Excel (upload→preview tabel→commit+summary),
  tab Konstruksi (poin terstruktur, reorder), tab Bahan (fabrics + konsumsi per-size), tab Ukuran (kolom size dinamis),
  Detail expand menampilkan semua. Backward-compat measurements lama S/M/L.
- **Integrasi SSOT**: promote style hasil import → varian kanonik + FG + sop_steps (contoh JENIFER: 2 warna×3 size = 6 varian+FG, 9 SOP).
- **Bukti**: import 19 style/115 varian/19 techpack, 0 error. testing_agent_v3 iteration_147 = **100% (96/96)**, tanpa regresi.
- Uji: import preview/commit idempotent, CRUD field baru persist, promote chain, negative (file salah → 400).

## TRACK HPP OTOMATIS + POLA/MARKING + FIT INFO-ONLY — SELESAI ✅ (2026-07-23, sesi lanjutan)
Scope disetujui user "ya sesuai rekomendasi": (1) HPP otomatis dari fabric_consumption per-size, (3a) Pola & Marking tarik consumption, (2b) fit categories info-only.
- **Backend** `utils/fabric_costing.py` (baru): hitung kain/pcs = (panjang_cm/yield_pcs)/100, biaya = m/pcs × harga_material, per-size + weighted price.
- **Endpoint** `GET /api/dewi/rnd/hpp/fabric-estimate?style_id=...` (di dewi_rnd_hpp.py): return fabrics[] + sizes[] {meters_per_pcs, weighted_price_per_meter, fabric_cost_per_pcs}. HPP save simpan fabric_source='techpack' & fabric_size.
- **Frontend HPP** `RnDHPPCalculatorModule.jsx`: tombol "Hitung dari Techpack" → panel chips per-size → klik size isi fabric_usage & harga → kalkulator existing (tidak diubah) → badge "dari Techpack · <size>".
- **Frontend Pattern** `RnDPatternModule.jsx`: tombol "Tarik dari Techpack" → chips per-size → isi Penggunaan Kain/pcs + HPP Bahan/pcs.
- **Fit info-only** `techpack_excel.py` + importer simpan `fit_categories[]`; `RnDTechPackModule.jsx` tampil "Fit: STANDAR / JUMBO" di list + field edit dgn note "tidak mengubah SKU/varian". SKU tetap {MODEL}-{WARNA}-{SIZE}.
- **Bukti backend**: testing_agent_v3 iteration_148 = **100% (15/15)**. JENIFER M: 463/5=0.926m × Rp25.000 = Rp23.150; HPP persist fabric_source=techpack, hpp_total=45265, selling=64664.29. Fit tidak buat/ubah varian.
- **Bukti UI (screenshot, agent-verified)**: HPP "Hitung dari Techpack" chips (M/XL/XXL) + apply size + kalkulasi update; Pattern "Tarik dari Techpack" isi field; Techpack detail render Fit + 9 konstruksi + tabel per-size.
- **BUGFIX (UI, ditemukan saat validasi screenshot)**: `RnDTechPackModule.jsx` search crash `TypeError: (tp.version||"").toLowerCase is not a function` — `version` legacy numerik. Fix: coerce `String(...)` di filter (line 251) + `openEdit` (line 159) agar `form.version.trim()` aman. Frontend compiled OK.
- Catatan: env preview punya data test terakumulasi (JENIFER techpack versi berulang dari import test — by-design versioning is_latest; hanya 1 Latest). Tidak dihapus (user: pakai data yang ada).
