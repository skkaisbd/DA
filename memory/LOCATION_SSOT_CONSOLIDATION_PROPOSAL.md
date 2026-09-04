# PROPOSAL KONSOLIDASI SSOT LOKASI & DE-DUPLIKASI GUDANG
Status: **PROPOSAL — belum dieksekusi. Menunggu persetujuan user.**
Tanggal: 2026-07 (Fase 6 kandidat)
Konteks: DA37 ERP (CV. Dewi Aditya). Lanjutan dari WAREHOUSE_AUDIT_FINDINGS & INVENTORY_QTY_LOGIC_AUDIT.

> Semua temuan di bawah sudah diverifikasi langsung ke kode + database + endpoint (read-only). Tidak ada kode yang diubah untuk menyusun dokumen ini.

> **UPDATE (keputusan user + re-analisis menyeluruh) — lihat §11 & §12 di bawah.**
> Keputusan user terkunci: **SSOT lokasi = Struktur Gudang (`wh_*`), LEBUR SEMUA ke satu** (bukan 2-level); hapus menu "Lokasi Bin"; selaraskan Opname Aksesoris ke standar opname3; mapping zona → draft dibuat agent.
> User juga menunjuk duplikasi yang SEBELUMNYA TERLEWAT: Inbound/Outbound ada di nav-atas DAN di dalam Scanner Barcode. Re-analisis lengkap = §11.

---

## 1. RINGKASAN EKSEKUTIF

Sistem punya **3 taksonomi lokasi** + **2 sumber stok** + **beberapa pintu UI yang tumpang tindih**. Ini penyebab tunggal dari 3 gejala yang user laporkan:

- **P1** Heatmap Dashboard Gudang blank → membaca sumber stok LEGACY yang kosong.
- **P3** Filter lokasi "Stok & Pergerakan" menampilkan zona produksi (GED-A/B, ZNA-*) yang tidak nyambung dengan struktur gudang fisik (GD-01/ZN-01/RK-01).
- **P5** Menu "Lokasi Bin" (Alat & Aksesoris) duplikat dengan "Struktur Gudang" (Scanner Barcode), plus ada manajer lokasi ketiga (`prod-locations`).

**Verdict Portal Aksesoris:** sebagian besar **MIRROR** (master & stok pakai SSOT yang sama `rahaza_materials`/`rahaza_material_stock`), BUKAN duplikat data. Tapi punya **opname sendiri** (auto-adjust, tanpa gate finance) + workflow request/loan/PR khusus. (Detail §5.)

**Arah usulan (ringkas):**
1. Pertahankan `rahaza_locations` sebagai **SSOT lokasi operasional (zona/area)** — sudah terpakai luas di produksi, HR, material issue, ledger stok. Tidak boleh dihapus.
2. Pertahankan `wh_*` (building→zone→rack→bin) sebagai **dimensi bin fisik** untuk Put-Away/Opname, tapi **DITAUTKAN** ke `rahaza_locations` (tiap zona fisik mapping ke satu rahaza_location).
3. **Deprecate & migrasi** `warehouse_locations` (legacy, 1 baris) + hapus menu "Lokasi Bin" → satu pintu struktur gudang saja.
4. Perbaiki heatmap (P1) agar baca stok kanonik.
5. Satukan penamaan/filter lokasi (P3) supaya konsisten.

---

## 2. TEMUAN — BUKTI

### 2.1 Tiga taksonomi lokasi (koleksi DB)

| Koleksi | Isi (contoh) | Sifat | Endpoint |
|---|---|---|---|
| `rahaza_locations` (10) | GED-A, GED-B, ZNA-CUTTING/SEWING/QC/PACKING/KAIN/AKSESORIS/FG/SAMPLE | **Zona/area operasional** (produksi + gudang) | `/api/rahaza/locations` |
| `wh_buildings`(1)/`wh_zones`(1)/`wh_racks`(1)/`wh_positions`(24) | GD-01 → ZN-01 → RK-01 → 24 bin | **Struktur fisik hierarkis (bin)** | `/api/wms/buildings|zones|racks|positions` (wms_structure.py) |
| `warehouse_locations` (1) | GD-01 GUDANG UTAMA | **Legacy datar** (sisa lama) | `/api/wms/legacy/locations` |

### 2.2 Dua sumber stok

| Koleksi | Isi | Dipakai |
|---|---|---|
| `rahaza_material_stock` (kanonik) | qty per {material_id, location_id→`rahaza_locations`} | SSOT stok riil, stock_service, put-away, opname3, marketing, produksi |
| `warehouse_stock` (legacy) | **0 baris / tidak ada** | HANYA heatmap dashboard (`/api/wms/legacy/stock`) → itu sebabnya blank |

### 2.3 Bin fisik (wh_positions) ≠ ledger stok (rahaza_material_stock)
- Stok qty disimpan di `rahaza_material_stock` (keyed ke `rahaza_locations`).
- Penempatan bin fisik disimpan di `wh_positions` (keyed ke `wh_*`).
- **Keduanya tidak saling tertaut** → tidak ada mapping "bin RK-01-S01-P01 ada di rahaza_location mana".

---

## 3. PETA PEMAKAIAN LINTAS PORTAL (IMPACT MAP)

### 3.1 `rahaza_locations` (zona operasional) — PALING DALAM TERTANAM
Konsumen (frontend):
- Gudang: `RahazaLocationsModule` (manajer `prod-locations`), `RahazaStockModule` (filter Stok & Pergerakan — P3), `RahazaMaterialIssueModule`
- **Produksi**: `ProductionDashboardOverview`, `RahazaLinesModule`, `ProductionWorkspaceMaster`, `RahazaMachinesModule`
- **HR**: `RahazaHRReportsModule`, `HREmployeeModule`, `RahazaEmployeesModule` (karyawan/mesin/line ditempatkan per lokasi)
- `MasterDataCRUD`
- Ledger stok kanonik `rahaza_material_stock.location_id` → id `rahaza_locations`
- Stok aksesoris (`core/accessory_stock.get_accessory_location_id`) → `rahaza_locations`

➡️ **Kesimpulan:** `rahaza_locations` = SSOT lokasi operasional lintas Produksi + HR + Stok. **Wajib dipertahankan.**

### 3.2 `wh_*` (bin fisik)
Konsumen: `PutAwayModule`, `WMSOpnameScanModule` (opname3), `WMSModule` (tab Struktur Gudang), `RahazaMaterialIssueModule` (konteks), `WarehouseDashboard` (buildings/pending/occupancy).
➡️ Dimensi fisik untuk put-away/opname. Dipertahankan, tapi perlu ditautkan ke §3.1.

### 3.3 `warehouse_locations` (legacy) — KANDIDAT DIHAPUS
Konsumen: `LocationsModule` (menu "Lokasi Bin"), `ReceivingModule`, `WarehouseDashboard` (nama lokasi heatmap), **`MaklonMaterialIssuePanel`**.
➡️ Hanya 1 baris data. Tumpang tindih dengan §3.1/§3.2. **Kandidat deprecate + migrasi konsumen.**

### 3.4 Dampak Finance / Marketing / BOM / Maklon
- **Finance** (`rahaza_posting.py`): posting jurnal mengikuti **movement stok** (receive/issue/adjust), bukan taksonomi lokasi. Konsolidasi lokasi **tidak mengubah** posting selama shape movement dijaga. (Terverifikasi di walkthrough opname: JE dibuat dari movement adjust.)
- **Marketing** (`marketing_kol_ops`, `product_launches`, `catalog`): pakai `onhand_map` (qty stok), bukan lokasi. Dampak rendah.
- **BOM/WO** (`bom/InlineMaterialPicker`): pakai master `rahaza_materials`, bukan lokasi. Dampak rendah.
- **Maklon** (`MaklonMaterialIssuePanel`): ⚠️ **BUG LATEN** — memilih `location_id` dari `warehouse_locations` (legacy), lalu cek stok via `/api/rahaza/material-stock?location_id=...` yang keyed ke `rahaza_locations`. **Id beda taksonomi → stok bisa selalu "tidak ketemu".** Harus dimigrasi ke `rahaza_locations`.

---

## 4. KLASIFIKASI DUPLIKASI

| Item | Status | Aksi usulan |
|---|---|---|
| `warehouse_locations` + `LocationsModule` ("Lokasi Bin") | **Duplikat legacy sejati** | Deprecate + migrasi konsumen → hapus menu |
| `warehouse_stock` (sumber heatmap) | **Mati / kosong** | Ganti sumber heatmap ke stok kanonik |
| `rahaza_locations` vs `wh_*` | **Dua dimensi sah tapi tak tertaut** | Tautkan (mapping zona↔fisik), bukan hapus |
| Menu `prod-locations` (RahazaLocationsModule) vs Struktur Gudang | **Tumpang tindih pengelolaan lokasi** | Perjelas peran: `prod-locations` = zona operasional; Struktur Gudang = bin fisik; jangan dua-duanya "bikin gudang" |

---

## 5. VERDICT PORTAL AKSESORIS (mirror vs duplikat)

Diverifikasi: `AccessoryModule` → API `/api/acc/*` (`dewi_accessories_*`).

- **Master Aksesoris** (`/api/acc/items`): header modul literal "SSOT: rahaza_materials"; query `{type:'accessory', active:true}` pada `rahaza_materials`. ➡️ **MIRROR**, bukan master duplikat.
- **Stok Aksesoris** (`/api/acc/stock/*`): pakai `core/accessory_stock` → `rahaza_material_stock` (kanonik) + `rahaza_material_movements`. ➡️ **MIRROR** stok kanonik.
- **Request Internal / Peminjaman / Purchase Request** (`acc_internal_requests`, `acc_loans`, `acc_purchase_requests`): fitur domain khusus aksesoris. ➡️ **BUKAN duplikat** (tidak ada padanan di gudang).
- **Opname Aksesoris** (`/api/acc/opname`): pakai koleksi lama `wh_opname_sessions`, **auto-adjust langsung** stok saat finalize (tanpa gate supervisor & tanpa posting finance). ➡️ ⚠️ **Governance beda** dengan Opname WMS baru (opname3: scan → submit → approve supervisor → rekonsiliasi + jurnal finance). Bukan duplikat data, tapi **standar kontrol tidak konsisten**.

➡️ **Kesimpulan:** Portal Aksesoris = **portal view/domain di atas SSOT yang sama** (aman, bukan bikin data tandingan) — KECUALI mekanisme opname-nya yang berdiri sendiri & lebih longgar. Rekomendasi: biarkan portal (mirror sah), tapi **selaraskan opname aksesoris** dengan standar opname3 (atau minimal lewat stock_service + finance) di fase terpisah.

Catatan menu ganda aksesoris (sudah sebagian di-dedup sebelumnya): `wh-accessory-ops` → redirect ke `accessories-master-stock`; `wh-accessory-master/stock` = alias ke modul materials/stock kanonik; `warehouse-accessory-requests` = komponen sama dengan `accessories-inbox`. Aman.

---

## 6. ARSITEKTUR TARGET (usulan)

```
DIMENSI LOKASI (2 level, tertaut):

  Level 1 — ZONA/AREA OPERASIONAL  = rahaza_locations   (SSOT akunting & operasional)
            (produksi, HR, ledger stok rahaza_material_stock)
                    ▲
                    │ (setiap zona fisik menunjuk 1 rahaza_location)
  Level 2 — STRUKTUR FISIK/BIN      = wh_buildings→wh_zones→wh_racks→wh_positions
            (put-away, opname fisik)   wh_zones.rahaza_location_id  ← FIELD BARU (mapping)

STOK (1 sumber): rahaza_material_stock (kanonik, via stock_service)
  - hapus ketergantungan ke warehouse_stock (legacy).

LEGACY DIHAPUS: warehouse_locations + LocationsModule ("Lokasi Bin").
```

Prinsip:
- **Satu sumber stok**: `rahaza_material_stock`. Semua pembaca (dashboard/heatmap) ikut sini.
- **Satu SSOT zona**: `rahaza_locations`. `wh_zones` menautkan diri ke sana lewat field baru `rahaza_location_id` (nullable dulu → wajib setelah migrasi).
- **Satu pintu kelola gudang fisik**: tab "Struktur Gudang" (wh_*). Menu "Lokasi Bin" (legacy) dihapus.

---

## 7. RENCANA DE-DUPLIKASI MENU (frontend)

| Menu sekarang | Nasib | Alasan |
|---|---|---|
| Alat & Aksesoris → **Lokasi Bin** (`wh-bin`/LocationsModule) | **HAPUS** (redirect ke Struktur Gudang selama transisi) | Duplikat legacy `warehouse_locations` |
| Scanner Barcode → tab **Struktur Gudang** (wh_*) | **JADIKAN SATU-SATUNYA** pintu bin fisik | Kanonik |
| `prod-locations` (RahazaLocationsModule) | **PERTAHANKAN**, perjelas label = "Zona/Area Operasional" | SSOT zona (produksi/HR) |
| Dashboard Gudang → Heatmap | **PERBAIKI sumber** ke stok kanonik | P1 |
| Stok & Pergerakan → filter lokasi | **PERBAIKI** agar konsisten (lihat §8 Fase C) | P3 |

---

## 8. RENCANA MIGRASI BERTAHAP (low-risk, compat-first)

**Fase A — Quick fix heatmap (P1)** *(kecil, aman)*
- Ubah heatmap Dashboard Gudang: agregasi `rahaza_material_stock` per `location_id` → nama dari `rahaza_locations` (dan/atau occupancy `wh_positions`). Hentikan baca `warehouse_stock`.
- Test: dashboard tampil stok DEMO/real; tidak blank.

**Fase B — Tautkan wh_zones ↔ rahaza_locations** *(sedang)*
- Tambah field `rahaza_location_id` di `wh_zones` (nullable). UI Struktur Gudang: saat buat/edit zona, pilih rahaza_location.
- Backfill: petakan ZN-01 → salah satu rahaza_location (mis. ZNA-KAIN/ZNA-FG sesuai peruntukan) — **butuh keputusan user** mapping-nya.
- Test: put-away/opname tetap jalan; zona fisik punya referensi zona operasional.

**Fase C — Satukan filter & penamaan lokasi (P3)** *(sedang)*
- Filter "Stok & Pergerakan": tampilkan lokasi dari SSOT `rahaza_locations` **dengan label jelas** (mis. kelompok "Gudang" vs "Produksi"), atau filter bertingkat zona→bin bila stok sudah ditautkan ke bin. Hilangkan kesan "zona ngaco".
- Test: filter cocok dengan realita gudang user.

**Fase D — Migrasi konsumen `warehouse_locations` → hapus legacy (P5)** *(sedang, hati-hati)*
- Migrasi `ReceivingModule`, `MaklonMaterialIssuePanel` (⚠️ sekalian benahi bug laten §3.4), `WarehouseDashboard` (nama lokasi) → `rahaza_locations` (atau wh_* sesuai konteks).
- Hapus menu "Lokasi Bin" (redirect dulu 1 rilis), hapus `LocationsModule.jsx`, hapus endpoint `/api/wms/legacy/locations` **hanya setelah** semua konsumen migrasi (mengikuti pola Fase 5 sebelumnya).
- Test: receiving, maklon issue, dashboard tetap jalan; tidak ada 404.

**Fase E — (opsional, terpisah) Selaraskan Opname Aksesoris**
- Alihkan `/api/acc/opname` finalize agar lewat `stock_service.adjust` + posting finance (atau reuse pola opname3), supaya governance konsisten.

Setiap fase: `py_compile` + restart + esbuild + screenshot + `testing_agent` + bersihkan artefak. Tidak lompat fase tanpa hijau.

---

## 9. RISIKO & PENGAMAN

- **rahaza_locations dipakai Produksi & HR** → JANGAN hapus/rename id. Hanya tambah tautan dari wh_zones. (Risiko tinggi bila salah.)
- **Bug laten Maklon** → perbaiki saat Fase D, jangan sampai memperparah.
- **Legacy endpoint** → ikuti pola Fase 5: migrasi konsumen dulu, hapus belakangan; jangan hapus wholesale.
- **Finance** → jaga shape movement (receive/issue/adjust) agar posting tidak berubah.
- **Mapping ZN-01 → rahaza_location** butuh keputusan bisnis user (fisik vs operasional). Jangan tebak.

---

## 10. KEPUTUSAN TERBUKA UNTUK USER

1. Setuju arah 2-level lokasi (rahaza_locations = zona SSOT, wh_* = bin fisik yang ditautkan)? atau mau semua dilebur ke satu?
2. Mapping zona fisik ZN-01 ↔ rahaza_location mana? (perlu daftar dari user)
3. Boleh hapus menu "Lokasi Bin" (legacy) setelah konsumen dimigrasi?
4. Opname Aksesoris: selaraskan ke standar opname3 (approval+finance) atau biarkan auto-adjust?
5. Urutan eksekusi: mulai Fase A (heatmap quick-win) dulu, atau kerjakan sesuai prioritas Anda?

---

## 11. RE-ANALISIS DUPLIKASI MENYELURUH (yang sebelumnya terlewat)

User menunjuk (dengan benar) bahwa duplikasi TIDAK hanya lokasi. Sumber utamanya: **"Scanner Barcode" (WMSModule) adalah MONOLIT LAMA** yang tab-tabnya menduplikasi menu-menu dedicated yang lebih baru. Plus ada **split legacy vs kanonik** di jalur inbound.

### 11.1 Penjelasan Inbound/Outbound (jawaban pertanyaan user)

Ada DUA lapisan, dan itu sumber kebingungan:

- **Nav-atas "Inbound — Penerimaan" & "Outbound — Pengiriman"** = lapisan **DOKUMEN/workflow bisnis**
  (Purchase Order, Penerimaan Barang, Fulfillment, Pick List, Surat Jalan, Kirim CMT, Retur).
  Modul kanonik menaruh "expected movement" ke koleksi **`wh_pending_movements`** (type: `inbound` / `outbound_rm` / `outbound_fg`).

- **Scanner Barcode → tab "Receiving / Scan" → (Inbound FG / Outbound Bahan / Outbound FG)** = lapisan **EKSEKUSI FISIK (scan-gun)**
  yang membaca `wh_pending_movements` lalu `POST /api/wms/pending/{id}/scan-in` (nambah stok) atau `/scan-out` (kurangi stok) + update bin. (backend: `wms_receiving.py`, prefix `/api/wms`).

➡️ Jadi bedanya: **nav-atas = bikin dokumen/rencana movement; Scanner Barcode = konfirmasi fisik movement itu.** Bukan duplikat identik — tapi **tercecer & membingungkan** karena lapisan eksekusi disembunyikan sebagai tab di grup "Alat & Aksesoris".

⚠️ **Masalah nyata (duplikasi sejati):** menu **"Penerimaan Barang" (`wh-receiving` → ReceivingModule) memakai `/api/wms/legacy/receiving` (LEGACY)**, TERPISAH dari pipa penerimaan kanonik (`wh_pending_movements` + scan-in). → **dua sistem inbound yang tidak nyambung** (pola sama dengan lokasi & stok).

### 11.2 MATRIKS DUPLIKASI (fungsi → semua pintu → sumber data → verdict)

| Fungsi | Pintu-pintu yang ada | Sumber data | Verdict |
|---|---|---|---|
| **Dashboard gudang** | (a) menu **Dashboard Gudang** (`warehouse-dashboard`); (b) Scanner Barcode → tab **Dashboard** | (a) legacy `warehouse_stock`/kpi + wms; (b) `/api/wms/pending/summary` + occupancy | **Duplikat** (2 dashboard beda sumber) |
| **Struktur/lokasi gudang** | (a) Scanner Barcode → **Struktur Gudang** (`wh_*`); (b) menu **Lokasi Bin** (`warehouse_locations` legacy); (c) menu `prod-locations` (`rahaza_locations`) | 3 taksonomi | **Triple duplikat** → SSOT = `wh_*` (keputusan user) |
| **Inbound / penerimaan** | (a) menu **Penerimaan Barang** (`/api/wms/legacy/receiving` LEGACY); (b) Scanner Barcode → Receiving/Scan **Inbound FG** (`wh_pending_movements` scan-in kanonik) | 2 sistem | **Duplikat + split legacy** |
| **Outbound / pengeluaran** | (a) menu **Pengeluaran Material** (`/api/rahaza/material-issues`); (b) menu **Fulfillment**; (c) Scanner Barcode → **Outbound Bahan/FG** (pending scan-out) | dokumen vs eksekusi | **Lapisan tercecer** (bukan duplikat murni, tapi membingungkan) |
| **Put-Away** | menu **Penyimpanan** (`wh-putaway`, kanonik) | `wh_*` + `rahaza_material_stock` | ✅ Bersih (Fase 3A) |
| **Opname** | (a) Stok & Akurasi → **Opname Stok** (`opname3`, approval+finance); (b) Aksesoris → **Stok Opname** (`/api/acc/opname`, auto-adjust) | canonical vs acc | **2 mekanisme, governance beda** (user pilih selaraskan) |
| **Lihat stok/posisi** | (a) **Stok & Akurasi** (`RahazaStockModule`); (b) Scanner Barcode → **Posisi & Search**; (c) Dashboard | kanonik | **Duplikat tampilan** |
| **Master item** | (a) **Master Item** (`rahaza_materials`); (b) Aksesoris → **Master Aksesoris** (mirror `rahaza_materials` type=accessory) | SSOT sama | **Mirror (OK)** + bug filter FG (P2) |
| **Satuan & Konversi** | Scanner Barcode → tab **Satuan & Konversi** | `wms_units` | Unik (pindahkan ke menu sendiri saat monolit dipecah) |
| **Audit Trail** | Scanner Barcode → tab **Audit Trail** | `wms_audit` | Unik |

### 11.3 Akar struktural
**Scanner Barcode (WMSModule) = monolit WMS lama.** Modul-modul dedicated (Put-Away, Opname) sudah diekstrak keluar; sisa tab (Dashboard, Struktur Gudang, Receiving/Scan, Posisi) masih menduplikasi menu dedicated. Ditambah jalur inbound "Penerimaan Barang" masih legacy.

---

## 12. KEPUTUSAN USER (TERKUNCI) & ARAH REVISI

Keputusan user (sesi ini):
1. **SSOT lokasi = `wh_*` (Struktur Gudang). Lebur semua** (`rahaza_locations` & `warehouse_locations` → migrasi ke `wh_*`). *(revisi dari §6 yang tadinya 2-level)*
2. Mapping zona: **agent buat draft** (lihat §12.1).
3. **Hapus menu "Lokasi Bin"** (setelah konsumen migrasi).
4. **Opname Aksesoris diselaraskan** ke standar opname3 (approval + finance).

### 12.1 Draft mapping zona (untuk direview user) — karena wh_* jadi SSOT
Struktur fisik saat ini cuma: GD-01 → ZN-01 → RK-01 → 24 bin. `rahaza_locations` punya 10 zona operasional. Usulan: bangun struktur `wh_*` yang mencakup zona operasional sebagai **zona di dalam gedung**, contoh draft:

```
GD-01 GUDANG UTAMA
  ├─ ZN-KAIN        (≈ ZNA-KAIN)        → rak/bin kain
  ├─ ZN-AKSESORIS   (≈ ZNA-AKSESORIS)   → rak/bin aksesoris
  ├─ ZN-FG          (≈ ZNA-FG)          → rak/bin produk jadi
  ├─ ZN-SAMPLE      (≈ ZNA-SAMPLE)
GED-A / GED-B (gedung produksi) → dipetakan sbg building terpisah bila perlu:
  ├─ ZN-CUTTING, ZN-SEWING, ZN-QC, ZN-PACKING  (area produksi)
```
⚠️ Catatan: zona produksi (cutting/sewing/QC/packing) dipakai Produksi & HR untuk penempatan line/mesin/karyawan — kalau `rahaza_locations` dilebur ke `wh_*`, **semua referensi id di Produksi & HR harus dimigrasi** (risiko tinggi, harus mapping id lama→baru, tidak boleh hilang). Ini bagian tersulit & butuh persetujuan mapping final dari user.

### 12.2 Revisi rencana eksekusi (menggantikan §8 utk arah "lebur ke wh_*")
- **Fase A (aman):** Fix heatmap (P1) baca stok kanonik + Fix filter (P3) + Fix filter FG di Master Item (P2) + perbesar form PO (P4). *(quick-win, tak sentuh SSOT)*
- **Fase B:** Bangun struktur `wh_*` final (buildings/zones sesuai draft §12.1, hasil approve user) + tabel mapping `rahaza_location_id → wh_zone_id`.
- **Fase C:** Migrasi ledger stok `rahaza_material_stock.location_id` + movement → id `wh_*`; alihkan pembaca stok.
- **Fase D:** Migrasi Produksi + HR + material issue + maklon (fix bug laten) dari `rahaza_locations`/`warehouse_locations` → `wh_*`.
- **Fase E:** Pecah monolit **Scanner Barcode**: Struktur Gudang jadi menu tunggal; Receiving/Scan menyatu ke Penerimaan/Pengeluaran (dan migrasi "Penerimaan Barang" dari legacy → kanonik pending); hapus tab Dashboard & Posisi (pakai menu dedicated); Satuan & Audit dipindah ke menu sendiri.
- **Fase F:** Hapus menu "Lokasi Bin" + endpoint legacy locations/receiving/stock (setelah konsumen 0).
- **Fase G:** Selaraskan Opname Aksesoris → stock_service + finance (atau reuse opname3).
- Tiap fase: compile + restart + esbuild + screenshot + testing_agent + bersihkan artefak.

### 12.3 Keputusan terbuka yang MASIH perlu dari user
1. Setujui **draft mapping zona §12.1**? (atau beri daftar zona/bin final versi Anda)
2. `GED-A`/`GED-B` (gedung produksi) — jadikan **building `wh_*` terpisah** atau tetap konsep "zona produksi" saja? (memengaruhi migrasi Produksi/HR)
3. Urutan: mulai **Fase A (quick-win P1–P4)** dulu sambil saya siapkan mapping, atau tahan semua sampai mapping zona final?
