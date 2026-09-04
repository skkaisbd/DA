# LAPORAN REVIEW & AUDIT — CV. Dewi Aditya ERP
**Tanggal:** 2026-07-26 · **Lingkup:** IA (information architecture), wiring FE↔BE, dead code, duplikasi
**Metode:** pengukuran otomatis atas kode yang benar-benar berjalan (bukan sampling manual / asumsi).
Alat: `/app/data_import/audit.py`, `audit2.py`, `verify_wiring.py` + `openapi.json` runtime backend.
Bukti mentah: `/app/data_import/AUDIT_RAW.json`, `AUDIT_RAW2.json`, `AUDIT_DEAD_API.json`.

---

## 0. Skala sistem (baseline terukur)

| Dimensi | Angka |
|---|---|
| File route backend | 314 |
| Endpoint backend (OpenAPI runtime) | 2.123 |
| Komponen frontend `components/erp/**` | 297 |
| Koleksi MongoDB dipakai kode | 371 |
| Portal | 12 → **13** (setelah split Administrasi Sistem) |
| Pintu menu (nav) | 184 → **182** |
| moduleId di registry | 360 → **361** |

---

## 1. Wiring — **SEHAT (0 putus)**

Detektor menemukan 23 kandidat "FE memanggil endpoint yang tidak ada". Setelah verifikasi
baris-per-baris (`verify_wiring.py` + `grep`), **semuanya negatif palsu**:

- 18 kandidat = keterbatasan pencocokan pola path (`/api/x/${id}/${act}` vs `/api/x/{id}/act`).
- 5 kandidat = **komentar dokumentasi bug lama yang SUDAH diperbaiki**, mis.
  `ProductionDashboardModule.jsx:8` menulis "…memanggil `/api/production-monitoring-v2`
  yang tidak pernah ada" — teksnya komentar, bukan pemanggilan.

**Kesimpulan:** tidak ada menu yang meng-klik ke layar kosong, tidak ada tombol yang menembak
endpoint hantu. Guardrail `check_nav_map.py` (INV-NAV-01) juga **HIJAU**: 0 `NAV-GHOST`.

---

## 2. Duplikasi menu — **DITEMUKAN & DIPERBAIKI**

Pola cacat: satu komponen dipetakan ke banyak pintu, dibedakan hanya oleh `defaultTab`.
Akibatnya sidebar "menavigasi" sesuatu yang sebenarnya cuma tab di halaman yang sama.

| Portal | Pintu lama | Komponen sebenarnya | Tindakan |
|---|---|---|---|
| Manajemen Aset | `asset-dashboard`, `asset-list`, `asset-procurement`, `asset-loans` | **satu** `AssetManagementPortal` (beda tab) | Sidebar **dihapus**; jadi 1 pintu `asset-management`; id lama tetap hidup untuk deep-link |
| Aksesoris | `accessories-master-stock`, `-opname`, `-internal-request`, `-loans`, `-purchase` | **satu** `AccessoryModule` (beda tab) | 3 section → **1 section** (7 pintu) |

Juga ditemukan **9 pintu "redirect"** (`makeRedirect`) dan **21 pintu berbasis tab**
(`makeModuleWithTab`) — keduanya sah selama tidak menghasilkan dua pintu dengan isi identik
(dijaga guard `NAV-DUPTAB`).

---

## 3. Modul tanpa pintu (dead menu entry) — 187 → 56 benar-benar mati

Dari 360 moduleId di registry, **187 tidak muncul di menu manapun**. Setelah dicek silang ke
seluruh source frontend (hub tab, `makeRedirect`, `LEGACY_MODULE_TO_PORTAL`, command palette):

- **131** masih terjangkau (sengaja: id lama untuk deep-link / tab di dalam hub) → **AMAN**.
- **56** tidak dirujuk siapa pun selain baris registry-nya sendiri → **benar-benar mati**.

Contoh 56 yang mati: `prod-cutting`, `prod-wizard`, `prod-simple-input`, `prod-serial-engine`,
`toko-dashboard-legacy`, `toko-dashboard-classic`, `toko-orders`, `toko-packing`, `toko-pricing`,
`toko-shipping`, `marketing-kol`, `marketing-kol-leaderboard`, `marketing-ads`, `marketing-templates`,
`hr-kpi`, `hr-performance`, `hr-shift-management`, `hr-shift-scheduler`, `hr-payroll-dashboard`,
`maklon-orders`, `maklon-cmt`, `maklon-packing`, `mgmt-backup-restore`, `mgmt-integrations`,
`wh-fg`, `wh-accessory-master`, `wh-accessory-stock`, `wms-opname-scan`, `wms-opname-enhanced`, dst.

**Tindakan yang sudah diambil:** `mgmt-backup-restore` **dihidupkan** jadi pintu resmi di Portal
Administrasi Sistem (sekalian mengeluarkan tab "Backup" dari `ManagementSystemHub` supaya tidak
jadi satu-isi-dua-pintu). Sisanya masuk daftar bersih-bersih Fase 3 (lihat §6).

---

## 4. Dead code frontend — 14 berkas tidak pernah di-import

```
components/ModuleErrorBoundary.jsx
components/erp/ProductionMaterialReturnsModule.jsx
components/erp/ProductsModule.jsx
components/erp/SOPModal.jsx
components/erp/ThemeContext.jsx
components/erp/collaboration/communication/CommunicationTab.jsx
components/erp/collaboration/learning/LearningTab.jsx
components/erp/collaboration/shared/NotificationCenter.jsx
components/erp/collaboration/shared/UnifiedHeader.jsx
components/erp/collaboration/shared/UnifiedSidebar.jsx
components/erp/collaboration/shared/UniversalSearch.jsx
components/erp/collaboration/workspace/WorkspaceTab.jsx
hooks/useSimpleInputPresets.js
lib/tokoAdapter.js
```

Catatan: `ProductsModule.jsx` bahkan memuat pemanggilan `/api` telanjang (sisa kode lama).

---

## 5. Endpoint backend tanpa pemanggil UI — 167 endpoint / 116 keluarga

Setelah menormalkan pola `${var}` vs `{param}` (versi mentah pertama melaporkan 1.133 —
mayoritas negatif palsu karena FE menyusun URL lewat wrapper `${BACKEND_URL}/api/...${path}`),
angka sebenarnya **167 endpoint**. Klasifikasi:

| Kelas | Contoh | Sikap |
|---|---|---|
| Infrastruktur / dipakai non-UI | `/api/health`, `/api/metrics`, `/api/auth/me`, `/api/files/{path}` | **PERTAHANKAN** |
| Dipakai aplikasi lain (mobile / portal vendor / portal klien) | `/api/lms/student/*`, `/api/vendor/dashboard` | **PERTAHANKAN** |
| Legacy engine lama yang sudah digantikan | `/api/work-orders`, `/api/po-items`, `/api/po-accessories`, `/api/production-tracking`, `/api/distribusi-kerja`, `/api/garments`, `/api/accessory-shipments`, `/api/accessory-inspections`, `/api/buyer-shipment-*`, `/api/production-returns`, `/api/recalculate-jobs` | **KANDIDAT HAPUS** (Fase 3, butuh persetujuan) |
| Fitur ada di backend tapi belum ada UI-nya | `/api/rahaza/styles` (7), `/api/rahaza/payroll-settings` (3), `/api/rahaza/handover-templates` (3), `/api/wms/rack-alerts` (3), `/api/marketing/ai-content` (3), `/api/maklon/sla` (3), `/api/dewi/cmt-intake` (3), `/api/warehouse/smart-reorder` (2), `/api/rahaza/delegations` (2) | **BACKLOG** — perlu keputusan owner: bikin UI atau hapus |

Daftar lengkap: `/app/data_import/AUDIT_DEAD_API.json`.

---

## 6. Jawaban atas pertanyaan owner

### 6.1 "Pengeluaran Material di Portal Gudang — masih relevan? logikanya apa? harusnya nyambung ke Produksi"

**Masih relevan, dan sudah nyambung ke Produksi.** Bukti dari kode (bukan asumsi):

1. Saat **job produksi internal** dibuat, sistem otomatis membuat **draft Material Issue** dari
   BOM job tersebut — `backend/routes/production_internal_adapter.py` fungsi
   `_draft_mi_from_job()` + endpoint `POST /api/rahaza/material-issues/draft-from-job`
   (baris 223-332). Draft di-anchor ke `job_id`, dan **ditolak** bila job-nya maklon
   (material maklon datang dari klien lewat shipment, bukan dari gudang DA).
2. Alurnya: `draft → pending_approval → issued` (atau `rejected`) —
   `backend/routes/rahaza_inventory_issues.py`.
3. Saat **approve**, sistem memotong stok gudang lewat ledger kanonik dan mem-posting jurnal
   (`rahaza_posting.post_inventory_issue`).
4. Modul produksi kemudian membaca MI yang berstatus `issued` untuk menghitung pemakaian vs BOM
   (dasar Laporan Variance).

**Yang salah cuma penempatannya di menu**: dulu duduk di section "INVENTORI & STOK" (laci "lihat
stok"), padahal dia **arus keluar gudang menuju produksi**. Sudah dipindah ke section
**"OUTBOUND — PENGIRIMAN"** bersama Pick List, Surat Jalan, dan Kirim CMT.

> Dampak Portal Cutting (Fase 4): rantainya menjadi
> **Roll kain (Gudang) → Cutting → Kain Pola/Potongan (item master baru, stok Gudang) →
> Pengeluaran Material → Job Produksi / Kirim Material CMT.**
> Jadi Pengeluaran Material justru makin sentral: dia pintu resmi keluarnya potongan ke produksi.

### 6.2 "Portal Keuangan paling berantakan"

Penyebab konkret yang ditemukan:
- `PIUTANG AR` hanya 2 pintu, salah satunya (`Channel GL`) sebenarnya **pemetaan akun**, bukan piutang.
- `KAS & PEMBAYARAN` menumpuk **8 pintu** campur tiga urusan berbeda (kas fisik, bank, klaim/kasbon).
- `LAPORAN & BIAYA` mencampur **output** (laporan) dengan **master & perencanaan** (pusat biaya, HPP, anggaran, aset tetap).
- Prediksi Kas (AI) diletakkan di laci "pembayaran", padahal dia alat analisis.

Struktur baru mengikuti **siklus uang**, bukan nama modul:
`RINGKASAN & LAPORAN → PENJUALAN & PIUTANG → PENGADAAN & HUTANG → KAS, BANK & BIAYA →
AKUNTANSI & JURNAL → ANGGARAN & ASET`. Jumlah pintu **tetap 24** (tidak ada fitur hilang).

---

## 7. Perubahan IA yang sudah dieksekusi (Fase 2)

| Portal | Sebelum | Sesudah |
|---|---|---|
| **SDM** | 5 section / 24 pintu | **3 section** sesuai permintaan: `MANAJEMEN KARYAWAN` (8), `MANAJEMEN ORGANISASI` (8), `ANALITIK & LAPORAN` (8) — 24 pintu utuh |
| **Manajemen** | 3 section (termasuk Administrasi Sistem) | 2 section, **khusus eksekutif** |
| **Administrasi Sistem** | — | **PORTAL BARU**: `AKSES & AUDIT` (2), `SISTEM & DATA` (5). Akses: `super_admin` + `admin` |
| **Manajemen Aset** | 4 pintu (semua tab yang sama) | **1 pintu, sidebar dihapus** (`singleDoor`), nama dinormalisasi |
| **Aksesoris** | 3 section / 7 pintu | **1 section** / 7 pintu |
| **Keuangan** | 6 section acak | 6 section **berurut siklus uang** |
| **Gudang** | `Pengeluaran Material` di laci stok | dipindah ke laci **OUTBOUND** |

Guard baru **`NAV-SOLO`** ditambahkan ke `check_nav_map.py`: portal ber-flag `singleDoor`
wajib benar-benar 1 section × 1 pintu, supaya flag itu tidak bisa dipakai untuk
menyembunyikan pintu yang masih dibutuhkan. Hasil gate: **HIJAU, 0 pelanggaran**
(13 portal, 37 section, 182 pintu, 361 id registry).

---

## 8. Portal Cutting (FASE IA-4) — pemetaan database sebelum dibangun

Sebelum menulis satu baris kode, seluruh domain material/stok dipetakan agar tidak
terjadi duplikasi koleksi atau stok ganda:

| Kebutuhan | Koleksi yang SUDAH ADA (dipakai ulang) |
|---|---|
| Master material (kain, aksesoris, FG, potongan) | `rahaza_materials` — satu koleksi untuk semua tipe |
| Saldo stok per (material, lokasi) | `rahaza_material_stock` |
| Jejak audit mutasi stok | `rahaza_stock_ledger` (ditulis HANYA lewat `core/stock_service.py`) |
| Roll kain fisik | `wh_fabric_rolls` + `wh_fabric_roll_movements` |
| Pengeluaran material ke produksi | `rahaza_material_issues` |
| Lokasi gudang | `rahaza_locations` |

Koleksi BARU yang dibuat (dicek dulu tidak bentrok): `cutting_orders`, `cutting_progress`.
Koleksi lama `dewi_cutting_requests` / `dewi_cutting_batches` **tidak dipakai** — isinya
hanya seed demo, tanpa satu pun endpoint; ikut terhapus saat wipe.

Aturan yang dipatuhi:
1. Mutasi stok **hanya** lewat `core.stock_service.issue()` / `.add()` → alias
   (`qty/total_qty/quantity/available_quantity`) tetap sinkron & ledger selalu terisi.
2. Output potongan = dokumen baru di `rahaza_materials` (`is_cut_panel: true`,
   `type: fabric`, `unit: pcs`, `category: POTONGAN`, `source_material_id`), sehingga
   otomatis muncul di Master Item Gudang, dropdown BOM, dan Pengeluaran Material.
3. Kode potongan deterministik `CUT-<STYLE>-<WARNA>-<SIZE>`; bila sudah ada dipakai ulang
   (idempoten, tidak menambah master kembar).
4. HPP potongan = (kain terpakai × harga kain) ÷ potongan jadi, ditulis ke `unit_cost`
   master potongan saat cutting diselesaikan.
5. `cutting_orders` & `cutting_progress` dibuat saat startup (index) supaya **selalu
   ikut ter-backup** oleh `mongodump` walau masih kosong.

**Bukti alur berjalan** (`scripts/poc_cutting_flow.py`, semua langkah LULUS):
stok kain 100 → 83 kg; potongan 0 → 112 pcs; HPP potongan Rp 8.348,21
(= 17 kg × Rp 55.000 ÷ 112 pcs); potongan tampil di `/api/rahaza/materials`.

---

## 9. Bug SKALA yang baru ketahuan setelah data nyata dimuat

Setelah 1.031 master material + 730 baris stok nyata masuk:

| Temuan | Dampak | Perbaikan |
|---|---|---|
| Seluruh query master inventori memakai `.to_list(500)` | Data terpotong SENYAP: dropdown Material Issue kehilangan ±531 item, laporan low-stock salah hitung (730 baris stok dibaca 500) | `MASTER_FETCH_LIMIT = 20000` di `rahaza_inventory_shared.py`, dipakai di 16 titik |
| Badge tab "Bahan & Aksesoris" memakai `?limit=1` tanpa `page` | Endpoint mengabaikan `limit` di mode non-paginasi ⇒ badge menampilkan panjang array (mentok 500) | Pakai `?page=1&limit=1` + baca `pagination.total` |
| Badge "Produk Jadi" menghitung `/fg-issues` (TRANSAKSI) | Selalu 0 di database bersih meski master FG berisi 553 item | Hitung `/materials?type=fg` |


---

## 10. Hasil pengujian regresi (2 ronde `testing_agent_v3`)

### Ronde 1 — 1 bug NYATA ditemukan & diperbaiki
**QA-1 (HIGH):** input progres cutting gagal `400 Stok kain tidak cukup: tersedia 0.0`
padahal stok kain ada.
*Akar masalah:* stok disimpan **per (material, lokasi)**, sedangkan order cutting memakai
lokasi bawaan sistem — bukan gudang yang benar-benar memegang stok. Validasi `start`
memakai total lintas lokasi sehingga LOLOS, lalu `issue()` per-lokasi GAGAL.
*Perbaikan:*
- `/api/cutting/input-materials` kini mengembalikan `stock_locations[]` + `best_location_id`.
- Endpoint baru `/api/cutting/locations`.
- `create` memilih gudang berstok terbanyak bila user tidak memilih.
- `start` memvalidasi **per-lokasi** dan otomatis mengalihkan order ke gudang berstok
  (mengembalikan `notice`), atau menolak dengan pesan "kosong di semua gudang".
- Pesan error progres kini menyebut **sebaran stok per gudang**.
- Form UI: field **"Gudang Sumber Kain"** + checkbox *"Tampilkan hanya kain yang ada stoknya
  (54 dari 143)"* + peringatan kuning bila kain belum berstok.
*Bukti:* `scripts/poc_cutting_flow_v2.py` — 14/14 langkah LULUS (kain 28→26 kg, potongan 18 pcs,
kasus negatif ditolak dengan pesan benar).

### Ronde 2 — 3 temuan, **semuanya negatif palsu** (diverifikasi ulang dengan bukti)
| Laporan QA | Hasil verifikasi |
|---|---|
| "RBAC bocor: user HR melihat Portal Administrasi Sistem" | **Tidak bocor.** Kartu portal memang ditampilkan tapi TERKUNCI (ikon gembok, opacity 50%, badge "Tidak ada akses", klik tidak berfungsi) — pola yang sama dipakai semua portal lain. Deep-link `#mgmt-backup-restore` sebagai HR mendarat kembali di "Pilih Portal". Backend menolak: `/api/admin/backup/list` → **403**, `/api/users` → **403**. |
| "Tab Backup masih ada di Pengaturan Sistem" | **Sudah tidak ada.** Tab yang tersisa: Perusahaan · PDF: Kolom Tabel · PDF: Surat & TTD · API Keys. |
| "Badge 478 tidak tampil di tab Bahan & Aksesoris" | **Tampil.** Terbaca `Bahan & Aksesoris 481` dan `Produk Jadi 553`. |

Item yang tidak sempat diselesaikan QA karena timeout, diverifikasi manual: kasus negatif
cutting ✓, pintu "Komponen Kurang" ✓, dan 7 deep-link lama (`#asset-list`, `#asset-procurement`,
`#asset-loans`, `#accessories-loans`, `#wh-stock`, `#hr-attendance`, `#fin-journal-entry`) —
semuanya mendarat di modul yang benar ✓.

### Status akhir gate
- `check_nav_map.py` (INV-NAV-01): **HIJAU** — 14 portal, 38 section, 186 pintu, 364 id registry, 0 pelanggaran.
- Backup berisi **60 koleksi** termasuk `cutting_orders` & `cutting_progress` (DB bersih pasca-seed).
- Konsol browser: 0 error dari kode aplikasi.
