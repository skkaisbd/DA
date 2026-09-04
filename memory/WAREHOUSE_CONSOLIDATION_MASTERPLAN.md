# MASTERPLAN — KONSOLIDASI GUDANG (SSOT Lokasi `wh_*` + De-duplikasi Menu)
Status: **FASE A ✅ · B ✅ · E1 ✅ · Known Issue §5 ✅ · E2 ✅ · C ✅ · D ✅ · F ✅ · F+ (retire warehouse_locations) ✅ · G (Opname Aksesoris → Opname3: approval + finance) ✅ — SEMUA FASE A–G TUNTAS** (agent-tested iteration_161 + iteration_162, 100%). Lihat HANDOFF_NEXT_SESSION.md.
Turunan dari: `LOCATION_SSOT_CONSOLIDATION_PROPOSAL.md` (§11–§12).
Prinsip wajib: **JANGAN bikin portal lain error.** Setiap perubahan wajib punya safeguard lintas-portal + test + rollback.

---

## 0. MODEL TARGET (final, sesuai keputusan user)

**Keputusan terkunci:**
- SSOT lokasi fisik gudang = **`wh_*`** (building → zone → rack → bin). Lebur `warehouse_locations` (legacy) & bagian **penyimpanan gudang** dari `rahaza_locations` ke sini.
- **GED-A / GED-B & zona produksi (CUTTING/SEWING/QC/PACKING) = tetap KONSEP** di `rahaza_locations` → **TIDAK dimigrasi**, tetap dipakai Produksi & HR (line/mesin/karyawan). ⇒ risiko Produksi/HR minimal.
- Hapus menu "Lokasi Bin". Selaraskan Opname Aksesoris ke standar opname3.

**Pembagian domain lokasi setelah konsolidasi:**

| Domain | Sumber (target) | Catatan |
|---|---|---|
| Penyimpanan stok fisik (kain, aksesoris, FG, sample) | **`wh_*`** (GD-01 → ZN-KAIN/ZN-AKSESORIS/ZN-FG/ZN-SAMPLE → rak → bin) | SSOT stok & put-away & opname |
| Ledger stok | `rahaza_material_stock.location_id` → **id `wh_*`** | dimigrasi dari rahaza_locations |
| Zona operasional produksi (cutting/sewing/qc/packing, GED-A/B) | **`rahaza_locations`** (TETAP) | dipakai Produksi & HR; BUKAN storage stok |
| Legacy `warehouse_locations`, `warehouse_stock` | **DIHAPUS** | setelah konsumen migrasi |

**Draft mapping (di-ACC user, 1.a):**
```
ZNA-KAIN       → wh zone ZN-KAIN      (GD-01)
ZNA-AKSESORIS  → wh zone ZN-AKSESORIS (GD-01)
ZNA-FG         → wh zone ZN-FG        (GD-01)
ZNA-SAMPLE     → wh zone ZN-SAMPLE    (GD-01)
ZNA-CUTTING / SEWING / QC / PACKING, GED-A, GED-B → TETAP rahaza_locations (produksi/HR)
```

---

## 1. PETA DAMPAK LINTAS PORTAL + SAFEGUARD (WAJIB dipatuhi tiap fase)

| Portal | Menyentuh apa | Dampak konsolidasi | SAFEGUARD |
|---|---|---|---|
| **Produksi** | `rahaza_locations` (lines/mesin/karyawan/workspace), material issue ke lantai | Rendah — rahaza_locations TETAP | Jangan hapus/rename id rahaza_locations. Test: modul produksi tetap load lokasi. |
| **HR** | `rahaza_locations` (penempatan karyawan) | Rendah — TETAP | idem. |
| **Maklon** | `MaklonMaterialIssuePanel` → `warehouse_locations` (legacy) + cek stok by id | **Bug laten** (id beda taksonomi) | Fase D: pindah ke `wh_*` + perbaiki cek stok. Test maklon issue end-to-end. |
| **Marketing** | `onhand_map` (qty stok, lintas lokasi) | Sangat rendah | onhand_map menjumlah semua lokasi → aman. Test: angka stok FG marketing tak berubah. |
| **BOM/WO** | master `rahaza_materials` (bukan lokasi) | Nol | — |
| **Finance** | posting dari **movement** (receive/issue/adjust) | Nol (selama shape movement dijaga) | Semua mutasi tetap lewat `stock_service`; movement fields tak berubah. Test: opname approve → JE tetap terbit. |
| **Aksesoris portal** | stok via `core/accessory_stock.get_accessory_location_id` → rahaza_location | Sedang | Fase C: update helper → wh zone ZN-AKSESORIS. Test: master/stok/opname aksesoris. |
| **Put-Away / Opname3** | sudah `wh_*` | Nol | regресi test tetap hijau. |

**Aturan emas migrasi data:**
1. **Dual-read dulu**: reader stok menerima location_id lama & baru selama transisi.
2. **Tabel mapping** `rahaza_location_id → wh_zone_id` disimpan (koleksi `wh_location_migration_map`) — idempotent.
3. **Tidak menghapus** id lama sampai semua reader/writer migrasi & test hijau.
4. Preview saat ini **0 stok riil** → migrasi = no-op di sini, tapi script tetap dibuat & diuji untuk produksi.

---

## 2. FASE-FASE (urut; tiap fase = compile+restart+esbuild+screenshot+testing_agent+bersih artefak)

### FASE A — QUICK-WIN AMAN (P1–P4) — tidak menyentuh SSOT — ✅ SELESAI (2026-07-25, agent-tested)
Tujuan: perbaikan yang langsung kelihatan & tak berisiko ke portal lain.

**A1. P1 Heatmap Dashboard Gudang** — ✅
- File: `WarehouseDashboard.jsx`.
- Heatmap kini dari **`/api/wms/map/{building_id}`** (occupancy zona kanonik `wh_*`), bukan `warehouse_stock` kosong. Bukti: tile `GD-01·ZN-01 3/24 bin terisi · 12%` (1 zona).
- BONUS koherensi: KPI "Total SKU" yang tadinya menampilkan `0` (dari legacy `/api/wms/legacy/dashboard-kpi`) kini pakai sumber kanonik `/api/rahaza/material-stock/summary` → menampilkan **3** (sesuai 3 item berstok). "Lokasi Aktif" pakai jumlah zona wh_*.

**A2. P2 Filter FG di Master Item** — ✅
- File: `RahazaMaterialsModule.jsx` (+ param additif `exclude_type` di `rahaza_inventory_materials.py`).
- Tab "Bahan & Aksesoris" fetch `?exclude_type=fg`; opsi filter tinggal "Semua (Bahan & Aksesoris)/Bahan/Aksesoris"; opsi create "Produk Jadi" dihapus dari modul ini.
- Bukti: DEMO-FG-01 TIDAK muncul; DEMO-BAHAN-01 & DEMO-AKS-01 muncul; `?type=fg` tetap kembalikan FG.

**A3. P4 Form Create PO** — ✅
- File: `PurchaseOrderModule.jsx` + `Modal.jsx` (tambah ukuran `2xl` = `max-w-5xl`).
- Modal Buat PO & Detail PO kini `size="2xl"` (lebar terukur **1024px**, dari 896px). Baris item terbaca (Material lebar + Qty/Harga/Total + hapus). Tidak overflow di 1920px.

**A4. P3 (interim) filter lokasi "Stok & Pergerakan"** — ✅ (interim, BUKAN SSOT final)
- File: `RahazaStockModule.jsx`.
- Chip filter lokasi HANYA menampilkan lokasi yang benar-benar punya stok (mis. `DEMO-STAGING`); zona produksi kosong (cutting/sewing/QC/packing) tak lagi muncul sebagai chip.
- PENTING: form receive/transfer TETAP pakai daftar penuh 10 lokasi (`/api/rahaza/locations`) — sudah diverifikasi dropdown terbuka menampilkan 11 opsi. Konsolidasi lokasi fisik penuh (sumber = wh_*) tetap di Fase C.

**Checkpoint A — TERPENUHI:**
- testing_agent iteration_155: backend **23/23**, frontend **37/39** (2 temuan minor):
  - MEDIUM "dropdown 0 opsi" = FALSE POSITIVE (SmartNativeSelect custom, bukan `<option>` native; sudah diverifikasi 11 opsi tampil saat dibuka).
  - LOW "modal PO 896px" = SUDAH DIPERBAIKI (kini 1024px `2xl`).
- 0 error console aplikasi (hanya noise SSE/Cloudflare).
- DEMO-* data DIPERTAHANKAN (permintaan user).

### FASE A — QUICK-WIN AMAN (P1–P4) — DETAIL RENCANA (ARSIP)

**A1. P1 Heatmap Dashboard Gudang**
- File: `WarehouseDashboard.jsx`.
- Ganti sumber heatmap dari `/api/wms/legacy/stock` (`warehouse_stock` kosong) → **`/api/wms/map/{building_id}`** (occupancy per rak, kanonik) dan/atau agregasi `wh_positions` per zona.
- Hapus dependensi `warehouse_stock` di komponen ini.
- Test: heatmap tampil occupancy bin DEMO (P01/P02/P03 terisi) — tidak blank.

**A2. P2 Filter FG di Master Item**
- File: `RahazaMaterialsModule.jsx`.
- Default fetch `/api/rahaza/materials?type=` → paksa **exclude `fg`** untuk tab "Bahan & Aksesoris" (mis. kirim `types=fabric,accessory,...` non-fg, atau filter di FE).
- Hapus opsi "Produk Jadi" dari dropdown filter tab ini.
- Test: FG (DEMO-FG-01) TIDAK muncul di tab Bahan & Aksesoris; tetap muncul di tab Produk Jadi.

**A3. P4 Form Create PO**
- File: `PurchaseOrderModule.jsx` (modal buat PO).
- Lebarkan `<Modal>` (mis. `max-w-4xl/5xl`), rombak baris item dari `grid-cols-12` sempit → layout responsif input lebih besar (Material combobox lebar, Qty/Harga/Total cukup). Pakai komponen Shadcn (Input/Select) konsisten tema.
- Test: form terbaca jelas di 1920 & mobile; tambah/hapus item jalan; simpan PO OK.

**A4. P3 (interim)** — filter lokasi "Stok & Pergerakan" (`RahazaStockModule.jsx`)
- Sementara: beri label kelompok jelas (Gudang vs Produksi) ATAU sembunyikan zona produksi dari filter stok. Perbaikan penuh (sumber = wh_*) di Fase C.
- Test: filter tak lagi "ngaco" secara visual.

➡️ **Checkpoint A:** screenshot 4 layar + testing_agent regres (dashboard, master item, PO, stok). Baru lanjut.

---

### FASE B — BANGUN STRUKTUR `wh_*` FINAL + MAPPING — ✅ SELESAI (2026-07-25, agent-tested)
Implementasi (backend, idempotent, additif, TIDAK destruktif):
- Endpoint baru di `wms_structure.py`:
  - `POST /api/wms/structure/build-canonical-storage` (admin-only) — pastikan 4 zona storage kanonik di GD-01 + starter rack (RK-01 4×6=24 bin), lalu upsert `wh_location_migration_map`.
  - `GET /api/wms/structure/location-map` — baca peta migrasi (untuk Fase C & audit).
- 4 zona storage kanonik di GD-01 (tanpa zona "duplikat"):
  - **ZN-01** "ZONA Bahan Baku" (role bahan) — REUSE zona RM generik lama (bukan bikin ZN-KAIN baru).
  - **ZN-AKS** "Zona Aksesoris" (baru), **ZN-FG** "Zona Produk Jadi" (baru), **ZN-SAMPLE** "Zona Sample / RnD" (baru).
- Koleksi `wh_location_migration_map` (4 entri, STORAGE saja):
  - ZNA-KAIN→ZN-01 (bahan) · ZNA-AKSESORIS→ZN-AKS · ZNA-FG→ZN-FG · ZNA-SAMPLE→ZN-SAMPLE. Semua `rahaza_location_id` ter-resolve.
  - Zona PRODUKSI (GED-A/B, ZNA-CUTTING/SEWING/QC/PACKING) SENGAJA TIDAK dipetakan (tetap milik produksi/HR).
Bukti (testing_agent iteration_156, backend 13/13):
- Idempotency: run ulang → zones_created=0, racks_created=0, positions_created=0, map_entries tetap 4.
- Struktur tampil di menu "Scanner Barcode → Dashboard/Struktur Gudang" (4 zona, ZN-01 3/24=12%, 3 zona baru 0/24).
- Put-Away/Opname3 tetap jalan; put-away/locations kini menawarkan 4 zona; stok kanonik TIDAK berubah (bahan 2, aksesoris 6, fg 2); penempatan demo di ZN-01 utuh (3 bin).
- Auth: tanpa token → 401.
CATATAN: Ini BARU fondasi. Migrasi ledger stok agar location_id kanonik menunjuk `wh_*` (bukan pseudo "DEMO-STAGING"/rahaza id) dikerjakan di **Fase C** dengan dual-read + rollback.

### FASE C — ✅ SELESAI (2026-07-25, agent-tested iteration_158: backend 26/26, frontend 100%, 0 bug)
- **`core/location_resolver.py` (BARU)** — SSOT resolusi lokasi (dual-read rahaza↔wh): `get_migration_map`, `rahaza_to_wh_map`, `canonical_zone_id_for_role`, `to_canonical_location_id`, `list_storage_locations` (kanonik + legacy storage; EXCLUDE zona produksi), `build_display_map`, `location_exists`. Semua graceful (fallback aman).
- **Dual-read display**: `/api/rahaza/material-stock` list resolve nama via `build_display_map` → **fix P3 "Lokasi -"**.
- **Dual-read tulisan**: `/api/rahaza/material-receive` validasi via `location_exists` (terima id rahaza & wh).
- **Endpoint BARU** `GET /api/rahaza/storage-locations` (list terpadu) + `RahazaStockModule.jsx` dropdown/filter ambil dari situ [P3 selesai].
- **Accessory**: `core/accessory_stock.get_accessory_location_id` → utamakan wh zone ZN-AKS; fallback ZNA-AKSESORIS.
- **Script migrasi**: `scripts/migrate_stock_locations_to_wh.py` — idempotent, `--dry-run`, `--rollback`, row-merge, jurnal `wh_stock_location_migration_log`. (Preview no-op; teruji data dummy.)
- **Safeguard TERBUKTI**: `onhand_map` (marketing) tetap benar lintas lokasi; qty utuh melewati migrasi & rollback; finance movement shape utuh; `rahaza_locations` tak dihapus.
- Bukti: isolated 15/15 + iteration_158 (storage-locations 4 zona storage & EXCLUDE 6 produksi; display rahaza↔wh; migrasi move/idempotent/rollback; receive tolak invalid 404 & terima wh-zone id; accessory→ZN-AKS).

### FASE D — ✅ SELESAI (2026-07-25, agent-tested iteration_159: backend 11/11, frontend smoke, 0 bug)
- **D1 (fix mismatch Maklon):** `frontend/MaklonMaterialIssuePanel.jsx` dropdown lokasi → `/api/rahaza/storage-locations` (SSOT Fase C, bukan `/api/wms/legacy/locations` bin yg id-nya tak cocok `rahaza_material_stock`); `checkStock` diperbaiki (parse ARRAY + total on-hand kanonik + rincian lokasi). Backend `dewi_maklon.py create_material_issue` nama lokasi via `location_resolver.build_display_map`.
- **D2 (smart-reorder kanonik):** `dewi_warehouse_smart.py /smart-reorder` `current_qty` ← `stock_service.onhand_map`; konsumsi 30-hari ← `rahaza_stock_ledger` (op issue/issue_row) — bukan `warehouse_movements` legacy (kosong sejak Fase E2).
- **D3 (audit):** undo-history/undo/restore masih legacy `warehouse_movements`/`warehouse_stock` → aman (kosong utk data baru), catatan deprecation → Fase F.
- Bukti: isolated 10/10 + iteration_159 (maklon issue stok cukup→200 & location_name resolved & pending_scan_out & insufficient→400; smart-reorder current_qty=onhand kanonik; regresi 200). Catatan: Maklon UI panel belum di-UI-test independen (butuh order maklon, tak ada di DB fresh).

### FASE F — HAPUS/NEUTRALIZE LEGACY warehouse_* + MIGRASI UNDO-HISTORY ✅ SELESAI (2026-07-25, agent-tested iteration_161 22/22 + isolated 13/13)
- **F1 undo KANONIK:** `dewi_warehouse_smart.py` undo-history/undo/restore → `rahaza_stock_ledger` (op='adjust') + reversal `stock_service.adjust` (undo new=current−delta, restore new=current+delta), soft_deleted di ledger; entri reversal (ref.source undo/restore_adjustment) di-exclude dari undoable. `/alerts` low-stock → `stock_service.onhand_map`. Response shape sama (FE tak berubah).
- **F2 hapus writer:** `warehouse.py` `/api/warehouse/putaway` (transfer) & `/api/warehouse/opname` (variance) + helper `_sync_to_material_stock` DIHAPUS (→404). Kanonik = wms_putaway.py + wms_opname3.py.
- **F3 reader KANONIK:** `get_stock`/`get_stock_summary`→`rahaza_material_stock`; `get_movements` & `dashboard.recent_movements`→`rahaza_stock_ledger`; `dashboard-kpi`→`rahaza_material_stock` (pending_gr dari warehouse_receiving); `delete_location` guard→`rahaza_material_stock`. Bridge `/api/wms/legacy/*` tetap 200.
- **F4 drop koleksi:** `scripts/migrate_drop_warehouse_ledger_legacy.py` (archive→drop `warehouse_stock/movements/putaway/opname`, idempotent, --dry-run/--rollback, jurnal `wh_legacy_drop_log`). Teruji dummy forward+rollback lalu dibersihkan.
- **F5 dead code FE:** `LocationsModule.jsx` (orphan) DIHAPUS + lazy import.
- **DIPERTAHANKAN (live via bridge):** `warehouse_locations` (dropdown ReceivingModule) & `warehouse_receiving` (GR).
- **SISA Fase F ✅ DITUNTASKAN oleh FASE F+ (2026-07-25):** dropdown ReceivingModule sudah pindah ke `/api/rahaza/storage-locations`; `warehouse_locations` di-retire (get_locations kanonik, CRUD→410, +di script drop).

### FASE F+ — RETIRE warehouse_locations ✅ SELESAI (2026-07-25, agent-tested iteration_162 22/22)
- `warehouse.py` `get_locations` (+bridge `/api/wms/legacy/locations`) → KANONIK `location_resolver.list_storage_locations` (wh_zones + rahaza storage) + `wh_positions`. `create/update/delete_location` → **410** (SSOT = Struktur Gudang / rahaza_locations).
- `rahaza_inventory_stock.py` fallback nama lokasi `warehouse_locations` → `wh_zones`.
- FE `ReceivingModule.jsx`: dropdown "Lokasi Tujuan" GR → `/api/rahaza/storage-locations`. GR create tetap terima `location_id` rahaza (diteruskan ke `stock_service.add`).
- `scripts/migrate_drop_warehouse_ledger_legacy.py`: `warehouse_locations` masuk daftar archive→drop. DIPERTAHANKAN: `warehouse_receiving`.

### FASE G — OPNAME AKSESORIS → STANDAR OPNAME3 ✅ SELESAI (2026-07-25, agent-tested iteration_162 22/22 + isolated 14/15)
- `dewi_accessories_opname.py` (SSOT `wh_opname_sessions2` domain='accessory'): flow `open →(submit)→ pending_approval →(approve|reject)`.
- **submit** hitung variance + kunci, TIDAK ubah stok. **approve** GATE SUPERVISOR (`check_role` APPROVE_ROLES) → `_add_stock` (stock_service) + `_log_movement` (rahaza_material_movements) + `post_inventory_adjust` (JE inventory_adjust Dr 1-1401 / Cr 6-2400, idempotent `mvadj:<mv_id>`). **reject** tanpa ubah stok. `complete` = alias submit (deprecated).
- FE `AccessoryModule.StokOpnameTab`: "Ajukan untuk Approval" + "Setujui"/"Tolak" (supervisor) + badge status + ringkasan (selisih, jumlah JE, nilai).

### FASE E — PECAH MONOLIT "SCANNER BARCODE" (WMSModule) → hilangkan duplikasi menu

**FASE E1 ✅ SELESAI (2026-07-25, agent-tested, screenshot-verified):**
- Monolit `wms` dibubarkan. `WMSModule` kini punya mode `section` (render 1 bagian, `data-testid="wms-section-<section>"`).
- Menu terpisah: `wh-structure` (Struktur Gudang = SSOT lokasi), `wh-scan` (Scan Gudang inbound/outbound), `wh-units` (Satuan & Konversi), `wh-audit` (Audit Trail).
- Tab "Dashboard" DIHAPUS (pakai menu Dashboard Gudang). "Posisi & Search" DILIPAT ke hub Stok & Akurasi.
- "Lokasi Bin" (`wh-bin`) & id lama `wms` → redirect ke `wh-structure`.
- Nav diperbarui (portalNav.js): section "STRUKTUR, ALAT & AKSESORIS"; "Scanner Barcode" & "Lokasi Bin" dihapus dari menu.
- File: WMSModule.jsx, moduleRegistry.js, hubs/WMSStockHub.jsx, portal-shell/portalNav.js.
- ⚠️ KNOWN ISSUE (prioritas 1, kecil): deep-link fresh `#wms`/`#wh-bin` mendarat di "Pilih Portal" (portal-shell tak resolve id yang sudah lepas dari nav). Notif `wms_receiving.py:263 link_module="wms"`. Fix di HANDOFF §5.

**FASE E2 ✅ SELESAI (2026-07-25, agent-tested iteration_157: backend 17/17, frontend 2/2, 0 critical):**
- Dokumen **Goods Receipt** (`/api/wms/legacy/receiving`: PO→GR, qty diterima/ditolak, lot/expiry, **PO 3-way matching**) tetap satu pintu inbound.
- Stok kini dialirkan via **`stock_service.add`** (kanonik `rahaza_material_stock` + ledger `rahaza_stock_ledger`) & **BERHENTI menulis ledger ganda `warehouse_stock`/`warehouse_movements`** (sumber INV-11).
- Kode `backend/routes/warehouse.py`: tambah `from core import stock_service`; `update_receiving()` → blok Ledger 1 `warehouse_stock`+`warehouse_movements` DIHAPUS, item loop panggil `stock_service.add(...)` (FATAL bila gagal; item tanpa material_id di-skip), `_record_material_movement` + `update_po_received_qty` (3-way) + Asset capitalization DIPERTAHANKAN. Helper `_sync_to_material_stock` DIBIARKAN (masih dipakai LEGACY putaway-transfer & opname-variance yang butuh delta ±).
- Bukti: stok +100 via ledger op=add ref.source=goods_receipt; `warehouse_stock`=0; PO qty_received=100 status fully_received; Put-Away unshelved=100. Artefak TEST dibersihkan.
- **BONUS Known Issue §5 ✅ FIXED:** deep-link `#wms`/`#wh-bin` → `App.js` `LEGACY_MODULE_TO_PORTAL` map ke `warehouse` (redirect ke Struktur Gudang) + `wms_receiving.py:263` `link_module` `wms`→`wh-scan`.

### FASE F / F+ / G — ✅ SEMUA SELESAI (lihat bagian ✅ di atas)
- Fase F: hapus writer/reader legacy `warehouse_stock/movements/putaway/opname` + undo-history kanonik + hapus `LocationsModule.jsx`.
- Fase F+: retire `warehouse_locations` (get_locations kanonik, CRUD→410, dropdown ReceivingModule→SSOT).
- Fase G: Opname Aksesoris → approval supervisor + posting finance (JE inventory_adjust).
- Koleksi legacy drop via `scripts/migrate_drop_warehouse_ledger_legacy.py` (idempotent, --dry-run/--rollback). Endpoint bridge `/api/wms/legacy/{receiving,locations,dashboard-kpi}` tetap LIVE & kanonik.

---

## 3. URUTAN & GERBANG
A (quick-win) → B (struktur+map) → C (ledger) → D (legacy consumers+maklon) → E (pecah monolit) → F (hapus legacy) → G (opname aksesoris).
- Tidak lompat fase tanpa checkpoint hijau (compile, esbuild, screenshot, testing_agent, artefak bersih).
- Rollback per fase: perubahan terisolasi per file + script migrasi idempotent + dual-read → bisa mundur tanpa kehilangan data.

## 4. YANG BUTUH KONFIRMASI SEBELUM FASE B+ (bukan penghalang Fase A)
1. Nama/kode zona wh_* final (default pakai draft §0).
2. Perlukah bin/rak detail per zona sekarang, atau cukup 1 rak default per zona dulu?
3. Inbound: setuju "Penerimaan Barang" dimigrasi dari legacy → pipa kanonik (satu pintu)?

## 5. TESTING & DATA HYGIENE
- Tiap fase pakai `testing_agent` (backend+frontend sesuai cakupan) + screenshot bukti.
- Bersihkan artefak test & data DEMO (DEMO-*, DEMO-STAGING) setelah selesai / atas aba-aba user.
- Jangan hapus data non-test berdasarkan kuantitas saja.
