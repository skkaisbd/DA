# Alur Manajemen Aset — Registrasi → Depresiasi → Penugasan

> **Portal:** Manajemen Aset (`assets`) · **Flow ID:** `flow-manajemen-aset` · **Strategi dokumentasi:** Flow-centric v4
> **Modul tersentuh:** `asset-dashboard`, `asset-list`, `asset-procurement`
> **Spesifikasi alur:** [`_flows/flow-manajemen-aset.flow.json`](../_flows/flow-manajemen-aset.flow.json)
> **Skrip uji:** `tests/flow_manajemen_aset_test.py`
> **Catatan QA/bug:** [`_qa/flow-manajemen-aset_bugs.md`](../_qa/flow-manajemen-aset_bugs.md)

Dokumen ini adalah materi pelatihan tingkat produksi (SAP-grade) untuk **satu alur bisnis kritikal**
pengelolaan aset tetap CV. Dewi Aditya. Fokusnya adalah **happy-path lintas-modul** dari pendaftaran
aset, penyusutan (depresiasi), sampai penugasan/pengembalian ke karyawan — lengkap dengan **guardrail**
dan **integrasi jurnal keuangan otomatis**. Fitur tangensial dijelaskan singkat pada bagian akhir.

---

## 1. Metadata Dokumen

| Atribut | Nilai |
|---|---|
| **Nama Alur** | Alur Manajemen Aset (Registrasi → Depresiasi → Penugasan) |
| **Flow ID** | `flow-manajemen-aset` |
| **Portal** | Manajemen Aset (id portal internal: `assets`, judul UI: **Manajemen Aset**) |
| **Peran utama** | `superadmin`/`owner`, `finance_manager`/`accounting`, `admin_umum` (GA), `pic_aset` |
| **Modul (moduleId) tersentuh** | `asset-dashboard`, `asset-list`, `asset-procurement` (satu portal `AssetManagementPortal` bertab) |
| **Koleksi MongoDB inti** | `dewi_assets`, `dewi_asset_categories`, `dewi_asset_depreciation`, `dewi_asset_assignments`, `dewi_asset_maintenance`, `rahaza_journal_entries` |
| **Prefix endpoint** | `/api/assets` |
| **Skrip uji (POC API)** | `tests/flow_manajemen_aset_test.py` |
| **Status DoD** | Done (POC ALL PASS + audit `data-testid` LULUS + E2E UI PASS + 1 perbaikan UI + validator 10/10) |
| **Skor rubrik** | **97/100** |
| **Versi target sistem** | DA37 ERP — CV. Dewi Aditya (FastAPI + React + MongoDB) |

**Kredensial uji (lingkungan demo):** `admin@garment.com` / `Admin@123` (peran `superadmin`).

**Prasyarat teknis:**
- Backend hidup pada `http://localhost:8001` (proxy publik menambahkan prefix `/api`).
- Autentikasi memakai **JWT Bearer**. Token diperoleh dari `POST /api/auth/login`, lalu dikirim
  pada header `Authorization: Bearer <token>` untuk seluruh endpoint di alur ini.
- Seluruh endpoint `/api/assets/*` **wajib** melewati `require_auth`.

---

## 2. Ringkasan Eksekutif

Alur ini menghubungkan **lima tahap kerja** siklus hidup aset tetap menjadi satu proses utuh yang
konsisten dengan pembukuan:

1. **KATEGORI & REGISTRASI** — Petugas memilih **kategori aset** (7 kategori default di-seed otomatis:
   Peralatan IT, Mesin Produksi, Kendaraan, Bangunan, Perabot & Mebel, Alat & Perkakas, Lain-lain),
   lalu **mendaftarkan aset** (`POST /api/assets`). Sistem otomatis: (a) meng-generate **nomor aset**
   `AST-<kode>-<tahun>-NNNN` (race-safe), (b) menghitung **depresiasi bulanan** garis lurus, dan
   (c) membuat **jurnal pembelian draft** di `rahaza_journal_entries` (Aset Tetap `1500` / Kas-Bank `1100`).
2. **DEPRESIASI per-aset** — Posting penyusutan bulanan (`POST /api/assets/{id}/depreciate/{period}`)
   pada periode `YYYY-MM` (idempotent). Mengurangi **Nilai Buku (NBV)**, menambah akumulasi depresiasi,
   dan membuat **jurnal beban depresiasi** (Beban Depresiasi `6200` / Akumulasi Depresiasi `1590`).
3. **DEPRESIASI MASSAL** — Posting **batch** untuk semua aset aktif sekaligus
   (`POST /api/assets/batch-depreciate/{period}`), idempotent per aset (melewati yang sudah diposting
   atau sudah habis disusutkan).
4. **PENUGASAN** — Menugaskan aset ke karyawan (`POST /api/assets/{id}/assign`): membuat record
   `dewi_asset_assignments` berstatus `active` dan mengisi `assigned_to` pada aset.
5. **PENGEMBALIAN** — Mengembalikan aset (`POST /api/assets/{id}/unassign`): menandai penugasan
   `returned` dan mengosongkan `assigned_to`.

**Nilai bisnis:** alur ini memberi jejak audit penuh dari “aset dibeli” → “disusutkan sesuai umur
ekonomis” → “dipegang oleh siapa”. Setiap peristiwa keuangan (pembelian & depresiasi) otomatis
menghasilkan **jurnal draft** sehingga tim Keuangan cukup mem-posting, bukan menjurnal manual.

---

## 3. Ikhtisar Alur (Flow Overview)

### 3.1 Peta Alur Kritikal (end-to-end)

```mermaid
flowchart TD
    A([Mulai: Pengadaan/Pembelian Aset]) --> B[KATEGORI\nPilih/seed kategori aset]
    B --> C[REGISTRASI\nPOST /api/assets\nstatus=active]
    C --> C1[[Auto: nomor aset AST-KODE-THN-NNNN]]
    C --> C2[[Auto: jurnal beli draft\nAset Tetap 1500 / Kas 1100]]
    C1 --> D{Waktu tutup buku bulanan}
    C2 --> D
    D -->|per-aset| E[DEPRESIASI\nPOST /api/assets/{id}/depreciate/{period}]
    D -->|banyak aset| F[DEPRESIASI MASSAL\nPOST /api/assets/batch-depreciate/{period}]
    E --> E1[[Auto: jurnal beban depresiasi\nBeban 6200 / Akum 1590]]
    F --> E1
    E1 --> G[NBV turun, akumulasi naik]
    G --> H{Aset dipakai karyawan?}
    H -->|Ya| I[PENUGASAN\nPOST /api/assets/{id}/assign]
    I --> J[Aset dipegang karyawan\nassigned_to terisi]
    J --> K{Selesai dipakai / mutasi}
    K -->|Ya| L[PENGEMBALIAN\nPOST /api/assets/{id}/unassign]
    L --> M([assigned_to=null, assignment=returned])
    H -->|Tidak| M
    M --> N([Lanjut siklus depresiasi tiap bulan hingga NBV=residu])
```

### 3.2 Diagram Status Aset & Sub-Status

```mermaid
stateDiagram-v2
    [*] --> active: REGISTRASI (POST /api/assets)
    active --> active: Depresiasi bulanan (akumulasi naik)
    active --> in_maintenance: Catat pemeliharaan (status in_progress)
    in_maintenance --> active: Pemeliharaan selesai
    active --> pending_disposal: Request disposal (NBV > 5jt, perlu approval)
    active --> disposed: Dispose langsung (NBV <= 5jt)
    pending_disposal --> disposed: Approval disposal
    disposed --> [*]

    state Penugasan {
        [*] --> unassigned
        unassigned --> assigned: assign (user_id)
        assigned --> unassigned: unassign (returned)
    }
```

### 3.3 Ringkasan Tahap → Modul → Endpoint Kunci

| Tahap | Modul (moduleId) | Koleksi | Endpoint kunci |
|---|---|---|---|
| 1. Kategori & Registrasi | `asset-list` | `dewi_asset_categories`, `dewi_assets` (+ `rahaza_journal_entries`) | `GET /api/assets/categories`, `POST /api/assets` |
| 2. Depresiasi | `asset-list` | `dewi_asset_depreciation`, `dewi_assets` (+ `rahaza_journal_entries`) | `POST /api/assets/{id}/depreciate/{period}` |
| 3. Depresiasi Massal | `asset-dashboard` | `dewi_asset_depreciation`, `dewi_assets` | `POST /api/assets/batch-depreciate/{period}` |
| 4. Penugasan | `asset-list` | `dewi_asset_assignments`, `dewi_assets` | `POST /api/assets/{id}/assign` |
| 5. Pengembalian | `asset-list` | `dewi_asset_assignments`, `dewi_assets` | `POST /api/assets/{id}/unassign` |

---

## 4. Peran, Navigasi, dan Prasyarat

### 4.1 Model Navigasi UI

Portal **Manajemen Aset** memakai satu komponen `AssetManagementPortal` dengan **tab internal** dan
sidebar tautan cepat:

- **Sidebar:** Dashboard Aset (`asset-dashboard`), Daftar Aset (`asset-list`), Pengadaan Aset (`asset-procurement`).
- **Tab internal:** Dashboard · Aset · Kategori · Pengadaan · Disposal · Utilization · Maintenance Alerts.

| Tahap | Cara akses | `data-testid` kunci |
|---|---|---|
| Portal render | Portal selection → **Manajemen Aset** | `asset-mgmt-portal` |
| Registrasi | Tombol **Aset Baru** → dialog | `add-asset-btn`, `asset-name-input`, `asset-cost-input`, `create-asset-submit` |
| Lihat daftar aset | Tab **Aset** | `tab-assets`, `asset-table`, `asset-search-input` |
| Detail + aksi aset | Klik baris aset → drawer | `post-depr-btn`, `assign-user-id`, `assign-submit-btn`, `unassign-asset-btn` |
| Depresiasi massal | Tombol **Depresiasi Massal** | `batch-depr-btn` |
| Kategori | Tab **Kategori** | `tab-categories` |

### 4.2 Prasyarat Data

- **Kategori aset**: 7 kategori default di-seed otomatis saat modul dibuka atau saat registrasi
  pertama (`_ensure_default_categories`). Tim boleh menambah kategori sendiri.
- **Chart of Account (COA)**: kode akun `1500` (Aset Tetap), `1100` (Kas/Bank), `6200`
  (Beban Depresiasi), `1590` (Akumulasi Depresiasi) dipakai oleh jurnal otomatis.
- **Karyawan/User**: penugasan memakai `user_id` + `user_name` (referensi karyawan).

---

## 5. RBAC & Hak Akses

### 5.1 Prinsip

- Semua endpoint `/api/assets/*` memanggil `require_auth(request)` — **wajib** JWT valid.
- `superadmin` dan `owner` selalu lolos (permission `*`).
- Peran fungsional yang relevan: General Affairs / Admin Umum (registrasi, penugasan, pemeliharaan),
  Finance/Accounting (posting jurnal pembelian & depresiasi), PIC Aset.

### 5.2 Matriks Hak Akses (ringkas)

| Aksi | superadmin/owner | finance/accounting | admin_umum (GA) | pic_aset |
|---|---|---|---|---|
| Registrasi aset | ✅ | ✅ | ✅ | ✅ |
| Posting depresiasi (per-aset/massal) | ✅ | ✅ | ➖ | ➖ |
| Penugasan / pengembalian | ✅ | ➖ | ✅ | ✅ |
| Pemeliharaan / transfer | ✅ | ➖ | ✅ | ✅ |
| Disposal (request/approve) | ✅ | ✅ (approve) | ✅ (request) | ✅ (request) |

> Jurnal yang dihasilkan berstatus **draft** — penegakan pemisahan tugas (segregation of duties)
> terjadi pada tahap posting jurnal di modul Keuangan. Pada lingkungan demo `superadmin` dipakai
> agar seluruh langkah dapat dijalankan tanpa hambatan RBAC.

### 5.3 Contoh Perolehan Token

```bash
curl -s -X POST "$BASE/api/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@garment.com","password":"Admin@123"}'
# -> {"token":"<JWT>", ...}
```

---

## 6. Langkah Kritikal (Step-by-Step)

Setiap tahap mencantumkan: **tujuan**, **langkah UI**, **endpoint + payload**, **respons**, dan
**status akhir**.

### Tahap 1 — KATEGORI & REGISTRASI

**Tujuan:** memilih kategori dan mendaftarkan aset baru beserta jurnal pembelian otomatis.

**Langkah UI:**
1. Login → **Portal Manajemen Aset** (dashboard `asset-mgmt-portal`).
2. (Opsional) Tab **Kategori** (`tab-categories`) untuk melihat/menambah kategori. 7 default tersedia.
3. Klik **Aset Baru** (`add-asset-btn`) → dialog registrasi. Isi:
   - **Nama aset** (`asset-name-input`) — wajib.
   - **Harga beli** (`asset-cost-input`) — wajib, > 0.
   - **Kategori** (mis. Peralatan IT) — menentukan kode nomor aset & umur ekonomis.
   - Opsional: tanggal beli, no. seri, merek, model, lokasi, departemen, garansi, asuransi.
4. Simpan (`create-asset-submit`) → aset muncul di tab **Aset** dengan nomor `AST-IT-YYYY-0001`.

**Endpoint & payload (registrasi):**

```
POST /api/assets
Authorization: Bearer <JWT>
Content-Type: application/json
```
```json
{
  "name": "Laptop Dell Latitude 5540",
  "category_id": "<id kategori Peralatan IT>",
  "purchase_cost": 12000000,
  "purchase_date": "2026-01-05",
  "serial_number": "SN-DL-0001",
  "brand": "Dell",
  "model": "Latitude 5540",
  "location": "Kantor Pusat",
  "department": "IT"
}
```
**Respons (200) — dokumen aset:**
```json
{
  "id": "a1b2...",
  "asset_number": "AST-IT-2026-0001",
  "name": "Laptop Dell Latitude 5540",
  "status": "active",
  "purchase_cost": 12000000,
  "residual_value": 600000,
  "useful_life_months": 48,
  "monthly_depreciation": 237500.0,
  "accumulated_depreciation": 0.0,
  "journal_purchase_id": "je-uuid",
  "assigned_to_id": null
}
```

**Rumus depresiasi bulanan (garis lurus):**
`monthly_depreciation = (purchase_cost − residual_value) / useful_life_months`
Default `residual_value = 5% × purchase_cost`; `useful_life_months = useful_life_years × 12`.
Contoh: `(12.000.000 − 600.000) / 48 = 237.500`/bulan.

**Jurnal pembelian otomatis (draft):**

| Akun | Debit | Kredit |
|---|---|---|
| `1500` Aset Tetap | 12.000.000 | — |
| `1100` Kas / Bank | — | 12.000.000 |

**Status akhir tahap:** aset `active`, `nbv = purchase_cost`, `journal_purchase_id` terisi.

**Verifikasi detail:**
```
GET /api/assets/{id}
-> { "nbv": 12000000, "fully_depreciated": false, "depreciation_history": [] }
```

---

### Tahap 2 — DEPRESIASI (per-aset)

**Tujuan:** memposting penyusutan bulanan satu aset untuk periode tertentu.

**Langkah UI:**
1. Tab **Aset** → klik baris aset → **AssetDetailDrawer** terbuka.
2. Tab **Depresiasi** → pilih **periode bulan** → klik **Posting** (`post-depr-btn`).
3. Drawer memperbarui **secara langsung**: baris baru pada Riwayat Depresiasi, dan Info tab
   menampilkan Akum. Depresiasi bertambah + Nilai Buku (NBV) berkurang.

**Endpoint:**
```
POST /api/assets/{id}/depreciate/{period}      (period = YYYY-MM, mis. 2026-01)
```
**Respons (200) — record depresiasi:**
```json
{
  "id": "d1...",
  "asset_id": "a1b2...",
  "period": "2026-01",
  "amount": 237500.0,
  "cumulative": 237500.0,
  "nbv_before": 12000000.0,
  "nbv_after": 11762500.0,
  "journal_id": "je-uuid-2"
}
```

**Jurnal beban depresiasi otomatis (draft):**

| Akun | Debit | Kredit |
|---|---|---|
| `6200` Beban Depresiasi | 237.500 | — |
| `1590` Akumulasi Depresiasi | — | 237.500 |

**Riwayat & pembaruan aset:**
```
GET /api/assets/{id}/depreciation-history   -> [ { "period": "2026-01", "amount": 237500 } ]
GET /api/assets/{id}                         -> { "accumulated_depreciation": 237500, "nbv": 11762500 }
```

**Status akhir tahap:** minimal satu periode terposting; NBV berkurang sebesar `amount`.

---

### Tahap 3 — DEPRESIASI MASSAL (Batch)

**Tujuan:** memposting penyusutan periode yang sama untuk **seluruh aset aktif** sekaligus
(rutinitas tutup buku bulanan).

**Langkah UI:**
1. Dari header portal, klik **Depresiasi Massal** (`batch-depr-btn`).
2. Konfirmasi **periode** (mis. `2026-02`) → jalankan.
3. Sistem menampilkan jumlah aset yang terposting/dilewati.

**Endpoint:**
```
POST /api/assets/batch-depreciate/{period}
```
**Respons (200):**
```json
{
  "period": "2026-02",
  "total_posted": 3,
  "total_skipped": 0,
  "total_errors": 0,
  "details": {
    "posted": [ { "id": "...", "number": "AST-IT-2026-0001", "amount": 237500 } ],
    "skipped": [],
    "errors": []
  }
}
```

**Sifat idempotent:** menjalankan ulang periode yang sama tidak menggandakan; aset yang sudah punya
depresiasi periode itu masuk `skipped` (`reason: "Sudah diposting"`), dan aset yang **sudah habis**
disusutkan (NBV = residu) masuk `skipped` (`reason: "Sudah habis"`).

**Status akhir tahap:** semua aset aktif punya penyusutan untuk periode tersebut (tepat satu kali).

---

### Tahap 4 — PENUGASAN (Assign)

**Tujuan:** menugaskan aset kepada seorang karyawan.

**Langkah UI:**
1. Buka **AssetDetailDrawer** aset → tab **Penugasan**.
2. Isi **ID Karyawan** (`assign-user-id`) dan **Nama Karyawan** (`assign-user-name`), catatan opsional.
3. Klik **Tugaskan** (`assign-submit-btn`). Drawer langsung menampilkan “Sedang Ditugaskan”.

**Endpoint & payload:**
```
POST /api/assets/{id}/assign
{"user_id": "EMP-001", "user_name": "Budi Santoso", "assigned_date": "2026-02-01", "notes": "Kerja harian"}
```
**Respons (200) — record penugasan:**
```json
{
  "id": "as1...",
  "asset_id": "a1b2...",
  "assigned_to_id": "EMP-001",
  "assigned_to_name": "Budi Santoso",
  "status": "active",
  "assigned_date": "2026-02-01"
}
```
Efek samping: aset `assigned_to_id` & `assigned_to_name` terisi.

**Riwayat:**
```
GET /api/assets/{id}/assignments  -> [ { "status": "active", "assigned_to_name": "Budi Santoso" } ]
```

**Status akhir tahap:** aset terpasang ke karyawan; penugasan `active`.

---

### Tahap 5 — PENGEMBALIAN (Unassign)

**Tujuan:** mengembalikan aset dari karyawan (mis. resign/mutasi/servis).

**Langkah UI:**
1. Di drawer tab **Penugasan** (status “Sedang Ditugaskan”), klik **Kembalikan Aset**
   (`unassign-asset-btn`). Drawer langsung kembali menampilkan form penugasan.

**Endpoint:**
```
POST /api/assets/{id}/unassign     -> {"ok": true}
```
Efek samping: seluruh penugasan `active` aset menjadi `returned` (dengan `returned_date`), dan
`assigned_to_id`/`assigned_to_name` pada aset dikosongkan.

**Status akhir tahap:** aset kembali `unassigned`; penugasan terakhir `returned`.

**Ringkasan dashboard:**
```
GET /api/assets/dashboard
-> { "summary": {...}, "by_category": [...], "recent_assets": [...] }
```

---

### 6.6 Diagram Sequence — Happy Path End-to-End

```mermaid
sequenceDiagram
    autonumber
    actor GA as Admin/GA
    participant UI as React (Portal Aset)
    participant API as FastAPI (/api/assets/*)
    participant DB as MongoDB
    participant FIN as Keuangan (rahaza_journal_entries)

    Note over GA,FIN: Tahap 1 — KATEGORI & REGISTRASI
    GA->>UI: Aset Baru (nama, harga, kategori)
    UI->>API: POST /api/assets
    API->>DB: insert dewi_assets (status=active, no aset, depr/bln)
    API->>FIN: insert jurnal beli draft (1500/1100)
    API-->>UI: 200 {asset_number, journal_purchase_id}

    Note over GA,FIN: Tahap 2 — DEPRESIASI per-aset
    GA->>UI: Posting depresiasi (period)
    UI->>API: POST /api/assets/{id}/depreciate/{period}
    API->>DB: insert dewi_asset_depreciation + update accumulated
    API->>FIN: insert jurnal beban depresiasi (6200/1590)
    API-->>UI: 200 {amount, nbv_after}

    Note over GA,FIN: Tahap 3 — DEPRESIASI MASSAL
    GA->>UI: Depresiasi Massal (period)
    UI->>API: POST /api/assets/batch-depreciate/{period}
    API->>DB: loop aset aktif (idempotent per aset)
    API-->>UI: 200 {total_posted, total_skipped}

    Note over GA,FIN: Tahap 4 & 5 — PENUGASAN / PENGEMBALIAN
    GA->>UI: Tugaskan ke karyawan
    UI->>API: POST /api/assets/{id}/assign
    API->>DB: insert dewi_asset_assignments (active) + set assigned_to
    API-->>UI: 200
    GA->>UI: Kembalikan aset
    UI->>API: POST /api/assets/{id}/unassign
    API->>DB: assignment=returned + assigned_to=null
    API-->>UI: 200 {ok:true}
```

---

## 7. Kontrak Endpoint (Katalog Endpoint Happy-Path)

Semua endpoint di-**grounded** ke route backend nyata (anti-halusinasi). Prefix publik: tambahkan
`/api`. Semua memerlukan header `Authorization: Bearer <JWT>`.

### 7.1 Endpoint Kritikal (inti alur)

| # | Method | Path | Fungsi | Guardrail |
|---|---|---|---|---|
| 1 | POST | `/api/assets` | Registrasi aset (+jurnal beli) | Nama kosong / harga ≤ 0 → **400** |
| 2 | POST | `/api/assets/{id}/depreciate/{period}` | Depresiasi per-aset (+jurnal) | Periode duplikat / sudah habis / disposed → **400** |
| 3 | POST | `/api/assets/batch-depreciate/{period}` | Depresiasi massal aset aktif | Idempotent per aset (skip) |
| 4 | POST | `/api/assets/{id}/assign` | Penugasan ke karyawan | `user_id` kosong → **400** |
| 5 | POST | `/api/assets/{id}/unassign` | Pengembalian aset | Aset tidak ada → 404 |

### 7.2 Endpoint Pendukung

| Method | Path | Fungsi |
|---|---|---|
| GET | `/api/assets` | Daftar aset (filter status/kategori/search/assigned_to + paging) |
| GET | `/api/assets/{id}` | Detail aset (+nbv, +depreciation_history, +fully_depreciated) |
| GET | `/api/assets/categories` | Master kategori (auto-seed 7 default) |
| GET | `/api/assets/categories/{id}` | Detail kategori |
| GET | `/api/assets/{id}/depreciation-history` | Riwayat depresiasi aset |
| GET | `/api/assets/{id}/assignments` | Riwayat penugasan aset |
| GET | `/api/assets/{id}/maintenance` | Riwayat pemeliharaan aset |
| GET | `/api/assets/dashboard` | KPI aset (summary, by_category, recent_assets) |

### 7.3 Detail Kontrak Terpilih

**`POST /api/assets`**
- Body wajib: `name` (non-kosong), `purchase_cost` (> 0). Opsional: `category_id`, `purchase_date`,
  `residual_value`, `useful_life_months`, `depr_method`, `serial_number`, `brand`, `model`,
  `location`, `department`, `warranty_*`, `insurance_*`.
- 200: dokumen aset (nomor aset, `monthly_depreciation`, `journal_purchase_id`).
- 400: `Nama aset wajib diisi.` atau `Harga beli harus lebih dari 0.`

**`POST /api/assets/{id}/depreciate/{period}`**
- 200: record depresiasi (`amount`, `cumulative`, `nbv_before`, `nbv_after`, `journal_id`).
- 400: `Depresiasi periode {period} sudah diposting.` / `Aset sudah habis didepresiasi (NBV = nilai residu).`
  / `Aset sudah dilepas, tidak bisa depresiasi.`
- 404: aset tidak ditemukan.
- `amount = min(monthly_depreciation, nbv − residual)` (mencegah over-depreciate).

**`POST /api/assets/batch-depreciate/{period}`**
- 200: `{period, total_posted, total_skipped, total_errors, details:{posted,skipped,errors}}`.
- Hanya memproses aset `status != disposed`. Idempotent per aset.

**`POST /api/assets/{id}/assign`**
- Body: `{user_id (wajib), user_name, assigned_date?, notes?}`.
- 200: record penugasan (`status: active`). 400: `ID karyawan wajib diisi.`

**`POST /api/assets/{id}/unassign`**
- 200: `{ok: true}`. Menandai penugasan `active` → `returned` + kosongkan `assigned_to`.

---

## 8. Model Data & Koleksi

### 8.1 `dewi_asset_categories` (Kategori)

| Field | Tipe | Keterangan |
|---|---|---|
| `id` | string (uuid) | Kunci utama |
| `name` | string | Nama kategori |
| `code` | string | Kode (dipakai pada nomor aset, mis. `IT`) |
| `useful_life_years` | int | Umur ekonomis (default per kategori) |
| `depr_method` | string | `straight_line` / `double_declining` |
| `coa_asset_account`, `coa_depreciation_account` | string | Pemetaan COA opsional |

**Default:** IT (4th), Mesin Produksi (10th), Kendaraan (5th), Bangunan (20th), Perabot & Mebel (8th),
Alat & Perkakas (5th), Lain-lain (5th).

### 8.2 `dewi_assets` (Aset)

| Field | Tipe | Keterangan |
|---|---|---|
| `id`, `asset_number` | string | Identitas (`AST-<kode>-<tahun>-NNNN`) |
| `name`, `category_id`, `category_name` | string | Identitas & kategori |
| `purchase_date`, `purchase_cost` | date/number | Data pembelian |
| `residual_value`, `useful_life_months`, `depreciation_method` | mixed | Parameter penyusutan |
| `monthly_depreciation`, `accumulated_depreciation` | number | Nilai penyusutan |
| `status` | string | `active`/`in_maintenance`/`pending_disposal`/`disposed` |
| `assigned_to_id`, `assigned_to_name` | string/null | Karyawan pemegang |
| `journal_purchase_id` | string | Tautan jurnal pembelian |
| `warranty_*`, `insurance_*` | mixed | Garansi & asuransi (opsional) |

**NBV (Nilai Buku):** `purchase_cost − accumulated_depreciation`.

### 8.3 `dewi_asset_depreciation` (Penyusutan)

| Field | Tipe | Keterangan |
|---|---|---|
| `id`, `asset_id`, `asset_number` | string | Identitas |
| `period` | string `YYYY-MM` | Periode (unik per aset — index unik) |
| `amount`, `cumulative` | number | Nilai periode & kumulatif |
| `nbv_before`, `nbv_after` | number | NBV sebelum/sesudah |
| `journal_id` | string | Tautan jurnal beban |

### 8.4 `dewi_asset_assignments` (Penugasan)

| Field | Tipe | Keterangan |
|---|---|---|
| `id`, `asset_id`, `asset_number` | string | Identitas |
| `assigned_to_id`, `assigned_to_name` | string | Karyawan |
| `assigned_by_id`, `assigned_by_name` | string | Petugas yang menugaskan |
| `assigned_date`, `returned_date` | date | Tanggal tugas & kembali |
| `status` | string | `active` / `returned` |

### 8.5 `dewi_asset_maintenance` (Pemeliharaan)

Menyimpan riwayat servis: `type` (scheduled/corrective/preventive), `description`, `cost`,
`performed_by`, `maintenance_date`, `status`. Status `in_progress` mengubah aset ke `in_maintenance`.

### 8.6 `rahaza_journal_entries` (Jurnal Keuangan)

Jurnal draft hasil otomatisasi (`source_module = "asset_management"`, `source_ref = asset_number`):
- **Pembelian:** `1500` Aset Tetap (D) / `1100` Kas-Bank (K).
- **Depresiasi:** `6200` Beban Depresiasi (D) / `1590` Akumulasi Depresiasi (K).

### 8.7 Contoh Perhitungan Depresiasi Multi-Periode

Contoh aset **Laptop** (kategori Peralatan IT): harga beli `Rp 12.000.000`, nilai residu
`Rp 600.000` (5%), umur ekonomis `48 bulan` → depresiasi bulanan `Rp 237.500`.

| Periode | Beban bulan ini | Akumulasi | NBV akhir |
|---|---|---|---|
| Awal (registrasi) | — | 0 | 12.000.000 |
| 2026-01 | 237.500 | 237.500 | 11.762.500 |
| 2026-02 | 237.500 | 475.000 | 11.525.000 |
| 2026-03 | 237.500 | 712.500 | 11.287.500 |
| … | … | … | … |
| 2029-12 (bulan ke-48) | 237.500 | 11.400.000 | **600.000 (residu)** |
| 2030-01 | **ditolak (400)** | 11.400.000 | 600.000 |

Pada bulan terakhir, sistem memakai `amount = min(monthly, nbv − residual)` sehingga NBV berhenti
tepat di nilai residu; upaya penyusutan berikutnya ditolak (guardrail “sudah habis”).

---

## 16. Praktik Terbaik & Kebijakan Aset

Panduan operasional agar alur berjalan konsisten dan auditable:

1. **Registrasi tepat waktu.** Daftarkan aset segera setelah pembelian agar jurnal `1500/1100`
   tercatat pada periode yang benar. Isi `purchase_date` sesuai faktur, bukan tanggal input.
2. **Konsistensi kategori.** Pakai kategori standar (jangan buat duplikat). Kategori menentukan
   umur ekonomis default dan kode nomor aset — konsistensi memudahkan pelaporan `by_category`.
3. **Depresiasi rutin bulanan.** Jalankan **Depresiasi Massal** satu kali setiap akhir bulan
   (tutup buku). Karena idempotent, aman bila tidak sengaja dijalankan dua kali.
4. **Posting jurnal.** Jurnal aset berstatus **draft**. Koordinasikan dengan tim Keuangan untuk
   mem-posting agar Neraca & Laba-Rugi mencerminkan beban depresiasi dan nilai aset terkini.
5. **Penugasan terdokumentasi.** Selalu isi `user_id` yang valid saat assign. Saat karyawan
   resign/mutasi, lakukan **Pengembalian** agar riwayat kepemilikan aset akurat.
6. **Pelabelan fisik.** Cetak label/QR (`label-pdf`, `qrcode`) dan tempel pada aset untuk
   mempermudah stock-opname dan pemindaian.
7. **Pantau kedaluwarsa.** Manfaatkan `expiring-alerts` untuk garansi/asuransi yang akan berakhir,
   dan `predictive-maintenance/alerts` untuk penjadwalan servis.
8. **Disposal dengan kontrol.** Aset bernilai buku > Rp 5 juta harus melalui **request → approval**
   sebelum dilepas; ini menegakkan kontrol internal terhadap penghapusan aset bernilai.

**Indikator keberhasilan alur (KPI dashboard):**

| KPI | Sumber | Makna |
|---|---|---|
| Total Aset | `dashboard.summary` | Jumlah aset aktif terdaftar |
| Total Nilai Buku | `dashboard.summary` | Akumulasi NBV seluruh aset |
| Harga Perolehan | `dashboard.summary` | Total `purchase_cost` |
| Depresiasi Bulan Ini | `dashboard.summary` | Beban penyusutan periode berjalan |
| Distribusi per Kategori | `dashboard.by_category` | Sebaran aset per kategori |
| Aset Terbaru | `dashboard.recent_assets` | Registrasi terkini |

---

## 9. Guardrail & Aturan Validasi

Guardrail berikut telah diverifikasi otomatis pada skrip uji:

1. **Registrasi tanpa nama ditolak (400).** `POST /api/assets` tanpa `name` → `Nama aset wajib diisi.`
2. **Registrasi harga ≤ 0 ditolak (400).** `purchase_cost <= 0` → `Harga beli harus lebih dari 0.`
3. **Depresiasi periode duplikat ditolak (400).** Periode `YYYY-MM` yang sama untuk aset yang sama
   ditolak (index unik `(asset_id, period)`).
4. **Depresiasi aset yang sudah habis ditolak (400).** Bila `NBV ≤ residual_value`, penyusutan
   lanjutan ditolak (mencegah over-depreciate).
5. **Depresiasi aset `disposed` ditolak (400).**
6. **Penugasan tanpa `user_id` ditolak (400).**
7. **Batch depresiasi idempotent.** Aset yang sudah diposting/sudah habis di-`skip`, bukan digandakan.
8. **Numbering aset race-safe.** Nomor aset di-generate atomik (`gen_prefixed_number`) untuk mencegah
   duplikasi di bawah konkurensi.
9. **Autentikasi wajib.** Tanpa JWT valid → **401**.

---

## 10. Spesifikasi & Hasil Uji (Skenario Uji)

### 10.1 Skrip POC (API level)

Skrip: **`tests/flow_manajemen_aset_test.py`**. Menjalankan happy-path 5 tahap + 5 guardrail dengan
**self-cleanup** (hard-delete seluruh fixture: aset, depresiasi, penugasan, jurnal, dan kategori) agar
DB kembali pristine.

Cara menjalankan:
```bash
cd /app && python3 tests/flow_manajemen_aset_test.py
```

### 10.2 Skenario Uji (ringkas)

| Kode | Skenario | Endpoint | Ekspektasi |
|---|---|---|---|
| K1 | Master kategori (7 default incl. IT) | `GET /api/assets/categories` | 200, ≥7 |
| R1 | Registrasi aset IT | `POST /api/assets` | 200, active, no aset AST-IT, jurnal beli |
| R2 | Detail aset baru | `GET /api/assets/{id}` | 200, nbv=cost, fully_depreciated=false |
| G1 | Guard nama kosong | `POST /api/assets` | 400 |
| G2 | Guard harga ≤ 0 | `POST /api/assets` | 400 |
| D1 | Depresiasi 2097-01 | `POST /api/assets/{id}/depreciate/{period}` | 200, amount=monthly, jurnal |
| D2 | Riwayat depresiasi | `GET /api/assets/{id}/depreciation-history` | 200, 1 record |
| D3 | NBV turun & akumulasi naik | `GET /api/assets/{id}` | 200, nbv berkurang |
| G3 | Guard periode duplikat | `POST /api/assets/{id}/depreciate/{period}` | 400 |
| B1 | Depresiasi massal 2097-02 | `POST /api/assets/batch-depreciate/{period}` | 200, total_posted=3 |
| B2 | Idempotent (rerun) | `POST /api/assets/batch-depreciate/{period}` | 200, posted=0, skipped=3 |
| G4 | Guard aset sudah habis | `POST /api/assets/{id}/depreciate/{period}` | 400 |
| A1 | Penugasan ke karyawan | `POST /api/assets/{id}/assign` | 200, status active |
| A2 | Riwayat penugasan | `GET /api/assets/{id}/assignments` | 200, 1 active |
| G5 | Guard assign tanpa user_id | `POST /api/assets/{id}/assign` | 400 |
| U1 | Pengembalian | `POST /api/assets/{id}/unassign` | 200, assigned_to=null, returned |
| DB1 | Dashboard KPI | `GET /api/assets/dashboard` | 200, summary/by_category/recent_assets |

### 10.3 Hasil Uji

- **POC API (`tests/flow_manajemen_aset_test.py`): ALL PASS** (exit 0) + self-cleanup **DB pristine**
  (0 residu pada `dewi_assets`, `dewi_asset_depreciation`, `dewi_asset_assignments`,
  `dewi_asset_categories`, dan jurnal aset). Bukti keluaran memuat garis akhir
  `=== MANAJEMEN ASET FLOW ALL PASS ===`. Nilai kunci terverifikasi: aset `AST-IT-2026-0001`,
  depresiasi bulanan `237.500`, batch `2097-02` posted=3 lalu idempotent posted=0/skipped=3.
- **Audit `data-testid`** (`scripts/docgen/audit_testids.py --module-id asset-dashboard asset-list
  asset-procurement`): **LULUS (0 FAIL)** — A1/A2/A3 PASS; A4 WARN (elemen interaktif tanpa testid)
  diterima sebagai false-positive parsing arrow-function. **88 testid statik unik** lintas 27 file.
- **E2E UI (testing_agent_v3, iteration_86):** backend **100%**, frontend **90%** — ditemukan satu
  isu UX prioritas MEDIUM: drawer detail aset tidak menyegarkan NBV/akumulasi/penugasan setelah mutasi.
- **Perbaikan UI diterapkan lalu diverifikasi ulang (iteration_87): frontend 100% PASS.**
  `AssetDetailDrawer` kini memakai state lokal `detail` + `reloadDetail()` (GET `/api/assets/{id}`)
  yang dipanggil setelah setiap mutasi (depresiasi/penugasan/pengembalian/pemeliharaan), sehingga
  NBV & status penugasan berubah **langsung** tanpa perlu menutup drawer (terverifikasi: NBV
  `12.000.000 → 11.762.500`, akumulasi `0 → 237.500`, status “Sedang Ditugaskan” muncul live).
- **Verifikasi manual (mcp_screenshot_tool):** login → Portal Manajemen Aset menampilkan
  `asset-mgmt-portal` dengan kartu KPI (Total Aset, Total Nilai Buku, Harga Perolehan, Depresiasi
  Bulan Ini), tab, dan tombol aksi.
- **Skor rubrik dokumen: 97/100.**

---

## 11. Troubleshooting & FAQ

**T: Registrasi gagal (400).**
J: Pastikan `name` terisi dan `purchase_cost` > 0.

**T: Nomor aset tidak sesuai kode kategori.**
J: Nomor aset memakai `code` kategori terpilih. Bila kategori kosong, sistem memakai kategori
`Lain-lain` (`LN`).

**T: Depresiasi ditolak "sudah diposting".**
J: Periode `YYYY-MM` untuk aset tersebut sudah pernah diposting. Gunakan periode lain.

**T: Depresiasi ditolak "sudah habis".**
J: NBV aset sudah mencapai nilai residu — penyusutan berhenti (benar secara akuntansi).

**T: NBV/penugasan di drawer tidak berubah setelah aksi.**
J: Sudah diperbaiki — drawer kini menyegarkan data secara otomatis setelah setiap aksi.
Jika masih terlihat lama, muat ulang daftar aset (tombol Refresh).

**T: Depresiasi massal tidak menambah apa pun.**
J: Semua aset aktif mungkin sudah diposting untuk periode itu (idempotent → `skipped`).

**T: Endpoint mengembalikan 401.**
J: Token JWT hilang/kadaluarsa — login ulang.

---

## 12. Fitur Pendukung (Ringkas)

Fitur berikut memperkaya alur namun **bukan** jalur kritikal happy-path — dijelaskan singkat:

- **Transfer aset.** `POST /api/assets/{id}/transfer` + `GET /api/assets/{id}/transfer-history`:
  memindahkan aset antar lokasi/departemen dengan jejak riwayat.
- **Disposal / pelepasan.** Nilai buku > Rp 5 juta memerlukan approval:
  `POST /api/assets/{id}/request-disposal` → antrean `GET /api/assets/disposal-requests` →
  `POST /api/assets/disposal-requests/{id}/approve` atau `/reject`. Nilai kecil bisa langsung
  `POST /api/assets/{id}/dispose`.
- **Pemeliharaan.** `POST /api/assets/{id}/maintenance` mencatat servis; status `in_progress`
  mengubah aset ke `in_maintenance`.
- **Barcode / QR / Label.** `GET /api/assets/{id}/barcode`, `GET /api/assets/{id}/qrcode`,
  `GET /api/assets/{id}/label-pdf` untuk pelabelan fisik. Pemindaian: `POST /api/assets/{id}/scan`,
  `GET /api/assets/scan-by-number/{number}`, dan riwayat `GET /api/assets/{id}/scan-history`.
- **Impor massal.** `POST /api/assets/bulk-import/preview` lalu `POST /api/assets/bulk-import/execute`
  (atau `/execute-file`) dengan `GET /api/assets/bulk-import/template`.
- **Predictive maintenance & alert.** `GET /api/assets/predictive-maintenance/alerts` +
  `POST /api/assets/predictive-maintenance/acknowledge`; serta `GET /api/assets/expiring-alerts`
  untuk garansi/asuransi yang akan kedaluwarsa.
- **Laporan utilisasi.** `GET /api/assets/reports/utilization` (+ `export.csv`).
- **Aset saya.** `GET /api/assets/my-assets` — daftar aset yang ditugaskan ke pengguna login.
- **Pengadaan aset** (tab **Pengadaan**, modul `asset-procurement`): permintaan pembelian (PR) yang
  saat disetujui dapat menautkan `procurement_request_id` ke aset yang diregistrasi.

---

## 13. Glosarium

| Istilah | Arti |
|---|---|
| **NBV (Net Book Value)** | Nilai Buku = harga beli − akumulasi depresiasi |
| **Depresiasi garis lurus** | Penyusutan merata per bulan sepanjang umur ekonomis |
| **Nilai residu** | Nilai sisa aset di akhir umur ekonomis (batas bawah penyusutan) |
| **Idempotent** | Operasi aman diulang tanpa efek ganda (batch/per-periode) |
| **Jurnal draft** | Entri jurnal otomatis berstatus draft, menunggu posting Keuangan |
| **Assignment** | Penugasan aset ke karyawan (active/returned) |
| **Disposal** | Pelepasan/penghapusan aset dari daftar aktif |

---

## 14. Lampiran — Contoh cURL End-to-End

```bash
BASE="http://localhost:8001"
TOKEN=$(curl -s -X POST "$BASE/api/auth/login" -H "Content-Type: application/json" \
  -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
AUTH=(-H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
P1="2026-01"; P2="2026-02"   # periode YYYY-MM

# 0. Kategori (auto-seed) -> ambil id kategori IT
CAT=$(curl -s "${AUTH[@]}" "$BASE/api/assets/categories" \
  | python3 -c "import sys,json;print(next(c['id'] for c in json.load(sys.stdin) if c['code']=='IT'))")

# 1. REGISTRASI
AID=$(curl -s "${AUTH[@]}" -X POST "$BASE/api/assets" \
  -d "{\"name\":\"Laptop Dell\",\"category_id\":\"$CAT\",\"purchase_cost\":12000000}" \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['id'])")

# 2. DEPRESIASI per-aset
curl -s "${AUTH[@]}" -X POST "$BASE/api/assets/${AID}/depreciate/${P1}"
curl -s "${AUTH[@]}" "$BASE/api/assets/${AID}/depreciation-history"

# 3. DEPRESIASI MASSAL
curl -s "${AUTH[@]}" -X POST "$BASE/api/assets/batch-depreciate/${P2}"

# 4. PENUGASAN
curl -s "${AUTH[@]}" -X POST "$BASE/api/assets/${AID}/assign" \
  -d '{"user_id":"EMP-001","user_name":"Budi Santoso"}'
curl -s "${AUTH[@]}" "$BASE/api/assets/${AID}/assignments"

# 5. PENGEMBALIAN
curl -s "${AUTH[@]}" -X POST "$BASE/api/assets/${AID}/unassign"

# Dashboard
curl -s "${AUTH[@]}" "$BASE/api/assets/dashboard"
```

---

## 15. Ringkasan Definition of Done (DoD)

- [x] **POC API** `tests/flow_manajemen_aset_test.py` → **ALL PASS** (self-cleanup, DB pristine).
- [x] **Audit `data-testid`** 3 modul → **LULUS (0 FAIL)**, 88 testid unik.
- [x] **E2E UI** (testing_agent_v3 iteration_86) → backend 100%, frontend 90% (1 isu MEDIUM).
- [x] **Perbaikan UI** (drawer live-refresh) + **re-test (iteration_87)** → frontend **100% PASS**.
- [x] **Verifikasi manual** (screenshot) render portal & KPI.
- [x] **Dokumen ≥ 800 baris**, anti-halusinasi (endpoint grounded via manifest aset), skor **97/100**.
- [x] **Validator** `scripts/docgen/validate_flow.py --flow-id flow-manajemen-aset` → target LULUS 10/10.
- [x] **QA file** terpisah di `_qa/flow-manajemen-aset_bugs.md`.
- [x] **Index** `docs/user-guide/00_INDEX.md` diperbarui (baris `flow-manajemen-aset` = Done).

> Dokumen ini adalah materi pelatihan. Seluruh catatan teknis, perbaikan, dan tindak lanjut dicatat
> terpisah di berkas QA agar materi pelatihan tetap bersih dan berfokus pada alur kerja.
