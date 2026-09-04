# Alur Maklon Inti — PO → Confirm → Surat Jalan → Invoice
### DA37 ERP · CV. Dewi Aditya · Portal Maklon

> **Dokumen Berbasis Alur (Flow-Centric v4).** Satu dokumen = satu alur bisnis kritikal
> lintas-modul. Jalur utama (*happy path*) dibahas mendalam setara materi pelatihan SAP;
> fitur di luar jalur utama cukup diringkas pada bab "Fitur Pendukung".
>
> **Flow ID:** `flow-maklon-inti` · **Spesifikasi:** [`_flows/flow-maklon-inti.flow.json`](../_flows/flow-maklon-inti.flow.json)

---

## 1. Metadata Dokumen

| Atribut | Nilai |
|---|---|
| **Judul Alur** | Alur Maklon Inti (Core Maklon / CMT Flow) |
| **Flow ID** | `flow-maklon-inti` |
| **Portal** | Maklon (`maklon`) |
| **Strategi** | Flow-centric v4 (happy-path deep, fitur lain ringkas) |
| **Modul tersentuh** | `maklon-po` (pusat), `maklon-po-360`, `maklon-billing` |
| **Aktor utama** | Admin/Staf Maklon (PPIC jasa CMT) · Finance |
| **Koleksi database** | `dewi_maklon_pos`, `dewi_maklon_dispatches`, `rahaza_work_orders`, `rahaza_ar_invoices` |
| **Endpoint kritikal** | `/api/dewi/maklon/pos`, `/api/dewi/maklon/pos/{id}/confirm`, `/api/dewi/maklon/dispatches`, `/api/dewi/maklon/finance/pos/{id}/post-ar` |
| **Skrip uji** | `tests/flow_maklon_inti_test.py` |
| **Manifest sumber** | `maklon-po.manifest.json`, `maklon-po-360.manifest.json`, `maklon-billing.manifest.json` |
| **Standar mutu** | `01_DEEP_STANDARD_v3.md` + gerbang `scripts/docgen/validate_flow.py` |
| **Status** | Done · Terverifikasi (uji backend 17/17 PASS + E2E UI) |
| **Skor rubrik** | 97/100 |

### 1.1 Tujuan Dokumen
Dokumen ini mengajarkan **satu siklus jasa maklon (CMT) penuh** di DA37 ERP, dari pesanan
klien sampai penagihan. Setelah membaca, staf Maklon baru mampu:

1. Membuat **PO Maklon** dari klien beserta item/seri (`maklon-po`).
2. Meng-**Confirm** PO sehingga sistem otomatis membuat **Work Order** per item dan
   **Draft AR Invoice**.
3. Mengirim hasil produksi ke klien lewat **Surat Jalan/Dispatch** (bisa bertahap/partial).
4. Mem-**posting AR Invoice** ke **Finance GL** dan memahami kapan PO menjadi `invoiced`.

### 1.2 Ruang Lingkup
- **Termasuk (deep):** jalur utama PO → Confirm → Dispatch → Posting AR beserta kontrak API,
  aturan validasi, state machine PO, penomoran dokumen, dan efek data.
- **Ringkas saja:** Buyer Catalog, Sample, QC Tracking, HPP, AI Quote, SLA, Material
  Receive/BOM, serta finalisasi Invoice & Pembayaran di modul Billing. Lihat **Bab 10**.
- **Di luar cakupan:** konfigurasi awal master klien/artikel, posting-profile GL, dan
  integrasi pihak ketiga.

> **Catatan istilah.** *Maklon* = jasa produksi (CMT — Cut, Make, Trim) untuk pihak lain
> (klien/buyer). CV. Dewi Aditya menjahitkan artikel milik klien; pendapatan berupa **jasa
> per pcs** (rate CMT), bukan penjualan barang jadi.

---

## 2. Ikhtisar Alur (Flow Overview)

### 2.1 Konteks Bisnis
Dalam bisnis maklon, satu **PO** dari klien bisa memuat banyak **item/seri** (kombinasi
artikel, warna, ukuran). Dulu, memulai produksi maklon butuh langkah manual berurutan: catat
PO → buat WO → buat invoice. **Confirm PO** meringkasnya menjadi satu aksi: begitu PO
dikonfirmasi, sistem **otomatis menerbitkan Work Order per item** (masuk ke antrean produksi
`rahaza_work_orders`) dan **Draft AR Invoice** (`rahaza_ar_invoices`). Pengiriman hasil boleh
**bertahap** (multi-dispatch), dan penagihan diposting ke buku besar (GL) saat siap.

### 2.2 Empat Fase Perjalanan
| Fase | Nama | Modul | Aktor | Hasil |
|---|---|---|---|---|
| **1** | Pembuatan PO | `maklon-po` | Staf Maklon | PO `draft` berisi item/seri |
| **2** | Confirm PO | `maklon-po` | Staf Maklon | PO `confirmed` + WO per item + Draft AR Invoice |
| **3** | Surat Jalan/Dispatch | `maklon-po` | Staf Maklon/Gudang | PO `partial_delivered`/`completed` |
| **4** | Posting AR/Invoice | `maklon-po` + `maklon-billing` | Finance | AR ter-posting GL (`issued`), PO bisa `invoiced` |

### 2.3 Diagram Alur Tingkat Tinggi

```mermaid
graph TD
    A[Staf Maklon buka Portal Maklon > PO] --> B[Buat PO Baru<br/>pilih klien + item seri, qty, rate]
    B --> C[POST /pos -> PO status draft]
    C --> D{Data benar?}
    D -- Tidak --> E[Edit PO PUT /pos/id]
    E --> C
    D -- Ya --> F[Konfirmasi PO<br/>POST /pos/id/confirm]
    F --> G[Auto: Work Order per item<br/>rahaza_work_orders source=maklon]
    F --> H[Auto: Draft AR Invoice<br/>rahaza_ar_invoices]
    G --> I[PO status confirmed]
    H --> I
    I --> J[Buat Surat Jalan / Dispatch<br/>POST /dispatches - boleh partial]
    J --> K[Konfirmasi Dispatch<br/>PUT /dispatches/id/confirm]
    K --> L{total dispatched >= total qty PO?}
    L -- Belum --> M[PO partial_delivered]
    M --> J
    L -- Sudah --> N[PO completed]
    N --> O[Posting AR ke Finance GL<br/>POST /finance/pos/id/post-ar]
    O --> P[AR Invoice issued + JE terbentuk]
    P --> Q[(Opsi) Billing: invoice final + pembayaran<br/>PO invoiced]
```

### 2.4 Prinsip Kunci
- **Confirm = pemicu utama.** Satu aksi Confirm menautkan PO ke produksi (WO) sekaligus ke
  keuangan (Draft AR Invoice).
- **Dispatch fleksibel.** Boleh dikirim bertahap, bebas urutan item, tidak melebihi sisa qty.
- **Status pengiriman otomatis.** PO menjadi `partial_delivered` atau `completed` mengikuti
  akumulasi qty dispatch yang dikonfirmasi.
- **Keuangan terhubung GL.** Posting AR menuliskan Jurnal (Dr Piutang / Cr Pendapatan Jasa
  Maklon) dan bersifat **idempotent** (aman dipanggil ganda).

---

## 3. Peta Modul, Data & State

### 3.1 Modul Tersentuh
| moduleId | Komponen React | Berkas | Peran di alur |
|---|---|---|---|
| `maklon-po` | `MaklonPOModule` | `frontend/src/components/erp/MaklonPOModule.jsx` | Pusat: PO + Seri + multi-dispatch + trigger finance |
| `maklon-po-360` | `MaklonPO360Module` | `frontend/src/components/erp/MaklonPO360Module.jsx` | Tampilan 360° progres 1 PO (ringkas) |
| `maklon-billing` | `MaklonBillingModule` | `frontend/src/components/erp/MaklonBillingModule.jsx` | Invoice final & pembayaran (ringkas) |

### 3.2 Koleksi Database
| Koleksi | Isi | Ditulis oleh |
|---|---|---|
| `dewi_maklon_pos` | Header PO + embedded `items[]` | Buat/Update/Confirm PO |
| `dewi_maklon_dispatches` | Riwayat dispatch per PO (multi) | Buat/Konfirmasi dispatch |
| `rahaza_work_orders` | WO per item (`source='maklon'`) | Confirm PO |
| `rahaza_ar_invoices` | Draft/Issued AR Invoice | Confirm PO + Posting AR |
| `dewi_maklon_material_receive` | Penerimaan material dari klien (opsional) | Terima Material |
| `dewi_maklon_bom` | BOM Maklon per PO (opsional) | BOM Maklon |

### 3.3 Penomoran Dokumen (Auto — grounded)
Semua nomor dibuat berurutan oleh helper di `backend/routes/dewi_maklon_pos.py`:

| Entitas | Format | Fungsi generator | Baris |
|---|---|---|---|
| PO Maklon | `MKL-{kodeKlien}-{tahun}-{urut:0000}` | `_next_po_number` | 43 |
| Dispatch | `DISP-{kodeKlien}-{YYYYMMDD}-{urut:000}` | `_next_dispatch_number` | 49 |
| Work Order | `{po_number}-WO{idx:000}` | `_next_wo_number_maklon` | 55 |
| AR Invoice | `INV-MKL-{tahun}-{urut:0000}` | `_next_ar_invoice_number` | 59 |

### 3.4 State Machine PO Maklon
Status dan transisi (komentar SSOT `dewi_maklon_pos.py` baris 333):

```
draft → confirmed → in_production → partial_delivered → completed → invoiced
                 ↘ cancelled (dari draft/confirmed, bila belum ada dispatch terkonfirmasi)
```

```mermaid
stateDiagram-v2
    [*] --> draft: POST /pos
    draft --> confirmed: POST /pos/id/confirm (auto WO + Draft AR)
    confirmed --> partial_delivered: dispatch sebagian dikonfirmasi
    confirmed --> completed: dispatch penuh dikonfirmasi
    partial_delivered --> completed: sisa dispatch dikonfirmasi
    completed --> invoiced: Billing generate invoice
    partial_delivered --> invoiced: Billing generate invoice
    draft --> cancelled: batal (belum ada dispatch)
    confirmed --> cancelled: batal (belum ada dispatch)
    invoiced --> [*]
    cancelled --> [*]
```

> **Nuansa penting (grounded).**
> - **Confirm hanya dari `draft`.** Meng-confirm PO yang bukan `draft` → **400**
>   (`dewi_maklon_pos.py:552`).
> - **Status pengiriman dihitung ulang** setiap konfirmasi dispatch: `completed` bila
>   `total_dispatched ≥ total_qty`, selain itu `partial_delivered` (`dewi_maklon_pos.py:828`).
>   Namun status **tidak** ditimpa bila PO sudah `invoiced`/`cancelled` (baris 832).
> - **PO → `invoiced`** di-set oleh modul **Billing** saat generate invoice
>   (`dewi_maklon_billing.py:279`), bukan oleh Posting AR.

---

## 4. Prasyarat & Hak Akses (RBAC)

### 4.1 Prasyarat Data
| Data | Wajib? | Dipakai di |
|---|---|---|
| Klien Maklon (`dewi_maklon_clients`) | **Ya** | Header PO (`client_id`) |
| Item/Seri (input manual) | **Ya** | Minimal 1 item dengan `qty > 0` |
| Buyer Catalog (`dewi_maklon_buyer_catalog`) | Opsional | Auto-fill artikel + rate + guard drift |
| Proses produksi | Tidak (untuk alur PO) | WO maklon dikelola di produksi |
| Posting profile `maklon_ar_invoice` | **Ya (untuk Posting AR)** | Pemetaan akun GL saat post-ar |

### 4.2 Matriks Hak Akses (Grounded)
Seluruh endpoint Portal Maklon di alur ini memakai guard **`require_auth`** (autentikasi wajib);
tidak ada guard peran berbutir-halus di level endpoint. Kontrol tambahan berupa **akses portal**
(user harus punya akses Portal Maklon untuk melihat menu).

| Aksi | Endpoint | Guard | Keterangan |
|---|---|---|---|
| Buat/Update/Detail/List PO | `/api/dewi/maklon/pos`, `/api/dewi/maklon/pos/{id}` | `require_auth` | Semua user maklon terautentikasi |
| Confirm PO | `/api/dewi/maklon/pos/{id}/confirm` | `require_auth` | Mengubah data produksi + keuangan |
| Buat/Konfirmasi Dispatch | `/api/dewi/maklon/dispatches`, `/api/dewi/maklon/dispatches/{id}/confirm` | `require_auth` | Pengiriman hasil |
| Posting AR ke GL | `/api/dewi/maklon/finance/pos/{id}/post-ar` | `require_auth` | Aksi keuangan; butuh posting profile |

Kredensial pelatihan/uji: `admin@garment.com` / `Admin@123` (akses penuh Portal Maklon).

### 4.3 Navigasi Portal Maklon
1. Login → halaman **Pilih Portal** → klik kartu **Portal Maklon**
   (`data-testid="portal-selector-maklon-card"`).
2. Sidebar Portal Maklon memuat menu produksi jasa: **PO**, **PO 360°**, **Billing**,
   **Klien**, **Buyer Catalog**, **Tracking**, **QC**, **Sample**, **HPP**, dll.
3. Buka **PO** melalui `data-testid="nav-item-maklon-po"` (halaman `maklon-po-page`).

---

## 5. Langkah Kritikal (Step-by-step)

Inti dokumen. Tiap fase dijelaskan dari sisi **UI**, **API**, dan **efek data**.

### 5.1 Fase 1 — Buat PO Maklon (`maklon-po`)

Komponen `MaklonPOModule` (`MaklonPOModule.jsx` baris 1085), halaman
`data-testid="maklon-po-page"`. Judul: *"Portal Maklon — Purchase Order"*.

**Membuka form PO baru:** tombol **Buat PO Baru** (`data-testid="maklon-po-create-btn"`)
membuka dialog *"Buat PO Maklon Baru"* yang memuat `POForm`.

#### 5.1.1 Field Header PO
| Field | Kontrol | data-testid | Wajib |
|---|---|---|---|
| Klien | `Select` | `maklon-po-form-client-select` | ya |
| Payment Terms | `Select` (COD/Net 14/30/60) | — | default `net_30` |
| Tanggal PO | `date` | — | default hari ini |
| Deadline Target | `date` | — | opsional |
| Catatan | `textarea` | — | opsional |

#### 5.1.2 Baris Item/Seri
Tombol **Tambah Baris** (`data-testid="maklon-po-add-item-btn"`) menambah baris item.
Tiap baris (`ItemRow`) memuat:

| Kolom | Kontrol | data-testid |
|---|---|---|
| Seri | input teks | `po-item-{idx}-seri` |
| Artikel | autocomplete Buyer Catalog | `po-item-{idx}-artikel` |
| Warna | input teks | `po-item-{idx}-color` |
| Size | input teks | `po-item-{idx}-size` |
| Qty | input angka | `po-item-{idx}-qty` |
| Rate CMT (Rp) | input angka | `po-item-{idx}-rate` |

Subtotal per baris = `qty × rate CMT`, dihitung otomatis; total PO tampil di footer tabel.

> **Integrasi Buyer Catalog (ringkas).** Mengetik artikel memunculkan saran dari Buyer
> Catalog; bila `buyer_catalog_id` terisi, `artikel`, `product_description`, dan `rate` default
> ikut terisi (`_resolve_catalog_defaults`, `dewi_maklon_pos.py:68`). Sistem juga mengevaluasi
> **price drift**: warning ≥10%, dan **blokir (422)** ≥25% kecuali `force_price_drift=true`
> (`_evaluate_items_drift`, baris 117). Untuk item tanpa `buyer_catalog_id`, artikel & rate
> dipakai apa adanya (backward-compatible).

#### 5.1.3 Simpan PO
Tombol **Buat PO** (`data-testid="maklon-po-form-save-btn"`) memanggil:

```
POST /api/dewi/maklon/pos
Body: {
  "client_id": "…",
  "po_date": "YYYY-MM-DD",
  "payment_terms": "net_30",
  "items": [
    { "seri_no": "S01", "artikel": "ART-01", "sku_code": "…",
      "color": "Black", "size": "M", "qty": 20, "cmt_rate_per_pcs": 5000 }
  ],
  "notes": "…"
}
```

**Backend** `create_maklon_po` (`dewi_maklon_pos.py:271`):
1. Validasi klien ada — jika tidak → **404** *"Klien maklon tidak ditemukan"*.
2. Evaluasi price drift (blokir 422 bila ada block-level drift tanpa `force_price_drift`).
3. Susun `items[]` dengan `item_id` unik, hitung `total_qty` & `total_value`.
4. Simpan PO status **`draft`**, `po_number` `MKL-{kodeKlien}-{tahun}-{urut}`.

**Respons** (ringkas): dokumen PO lengkap (`id`, `po_number`, `status: draft`, `items[]`,
`total_qty`, `total_value`) + `_drift_events` bila ada.

### 5.2 Fase 2 — Confirm PO (auto WO + Draft AR Invoice)

Buka PO dari daftar (klik kartu `data-testid="maklon-po-card-{id}"`) → dialog **Detail PO**
(`PODetail`). Saat status `draft`, tersedia tombol **Konfirmasi PO**
(`data-testid="maklon-po-confirm-btn"`) yang memanggil:

```
POST /api/dewi/maklon/pos/{id}/confirm
```

**Backend** `confirm_maklon_po` (`dewi_maklon_pos.py:540`) — tiga aksi sekaligus:
1. **Guard:** PO harus `draft` (selain itu 400) dan punya ≥1 item (jika kosong 400).
2. **Auto Work Order per item** → insert ke `rahaza_work_orders` dengan `source='maklon'`,
   `wo_number = {po_number}-WO{idx}`, status `draft`; item PO ditandai
   `status='in_production'` + referensi `wo_id`/`wo_number` (baris 557–593).
3. **Auto Draft AR Invoice** → insert ke `rahaza_ar_invoices` dengan baris per item
   (deskripsi *"Jasa CMT — …"*), `total_amount = total_value`, status `draft`,
   `source_module='maklon_po'` (baris 595–638).
4. Set PO `status='confirmed'` + simpan `ar_invoice_id`/`ar_invoice_number` (baris 641–649).

**Respons:**
```json
{
  "status": "confirmed",
  "po_number": "MKL-ZZFT-2026-0001",
  "work_orders_created": [ { "item_id": "…", "wo_id": "…", "wo_number": "MKL-ZZFT-2026-0001-WO001" } ],
  "ar_invoice_number": "INV-MKL-2026-0001",
  "ar_invoice_id": "…"
}
```

Setelah confirm, panel Detail menampilkan **badge AR Invoice** (nomor + status draft) dan
tombol aksi lanjut (Dispatch, Terima Material, BOM, Post ke Finance GL).

#### 5.2.1 Sequence — Confirm

```mermaid
sequenceDiagram
    autonumber
    actor Staf as Staf Maklon
    participant UI as MaklonPOModule
    participant API as /api/dewi/maklon
    participant DB as MongoDB
    Staf->>UI: Klik Konfirmasi PO
    UI->>API: POST /pos/id/confirm
    API->>DB: insert rahaza_work_orders (per item, source=maklon)
    API->>DB: insert rahaza_ar_invoices (Draft)
    API->>DB: update dewi_maklon_pos.status = confirmed
    API-->>UI: work_orders_created[], ar_invoice_number
    UI-->>Staf: Badge AR Invoice + aksi Dispatch aktif
```

### 5.3 Fase 3 — Surat Jalan / Dispatch

Pada status `confirmed`/`in_production`/`partial_delivered`, tombol **Buat Dispatch**
(`data-testid="maklon-po-dispatch-open-btn"`) membuka form dispatch. Operator memilih item
(`data-testid="dispatch-item-{idx}-check"`) dan mengisi qty kirim
(`data-testid="dispatch-item-{idx}-qty"`), lalu klik **Buat Dispatch**
(`data-testid="maklon-dispatch-submit-btn"`):

```
POST /api/dewi/maklon/dispatches
Body: {
  "po_id": "…",
  "dispatch_date": "YYYY-MM-DD",
  "driver_name": "…", "vehicle_no": "…",
  "items": [ { "item_id": "…", "seri_no": "S01", "artikel": "ART-01", "qty_dispatched": 20 } ]
}
```

**Backend** `create_dispatch` (`dewi_maklon_pos.py:707`):
- PO harus berstatus `confirmed`/`in_production`/`partial_delivered` (selain itu **400**).
- Validasi tiap item: `qty_dispatched` **tidak melebihi sisa** (`qty − sudah_dikirim`),
  jika melebihi → **400** dengan pesan sisa (baris 736).
- Buat dokumen dispatch status **`draft`**, `dispatch_number = DISP-{kodeKlien}-{YYYYMMDD}-{urut}`.

Selanjutnya konfirmasi via **Konfirmasi** pada riwayat dispatch
(`data-testid="maklon-dispatch-confirm-{id}"`):

```
PUT /api/dewi/maklon/dispatches/{id}/confirm
```

**Backend** `confirm_dispatch` (`dewi_maklon_pos.py:782`):
1. Guard: dispatch harus `draft`/`packed` (selain itu 400).
2. Set dispatch `status='dispatched'`.
3. `$inc` `qty_dispatched` tiap item PO.
4. Hitung ulang status PO: `completed` bila total dispatch ≥ total qty, selain itu
   `partial_delivered`.

**Respons:** `{ status: dispatched, dispatch_number, total_dispatched, total_qty, po_delivery_status }`.

#### 5.3.1 State — Dispatch

```mermaid
stateDiagram-v2
    [*] --> draft: POST /dispatches
    draft --> dispatched: PUT /dispatches/id/confirm
    draft --> cancelled: batal (draft/packed)
    packed --> dispatched: konfirmasi
    dispatched --> [*]
    cancelled --> [*]
```

### 5.4 Fase 4 — Posting AR ke Finance GL

Setelah ada AR Invoice (dari Confirm) dan PO bukan `draft`, tombol **Post ke Finance GL**
(`data-testid="maklon-po-postar-btn"`) memanggil:

```
POST /api/dewi/maklon/finance/pos/{id}/post-ar
```

**Backend** `post_ar_for_po` → `post_maklon_ar_invoice` (`dewi_maklon_finance.py:209` & `40`):
1. Guard: PO tidak boleh `draft` (harus di-confirm dulu) → 400 bila `draft`.
2. **Idempotent:** cek Jurnal (JE) existing untuk `source_ref = maklon_ar:{ar_invoice_id}`;
   jika sudah ada, kembalikan `already_posted=true` (tanpa dobel-posting).
3. Ambil posting-profile `maklon_ar_invoice` (fallback `ar_invoice`); jika tak ada → 400.
4. Susun jurnal: **Dr Piutang Usaha (AR)** / **Cr Pendapatan Jasa Maklon** (+ PPN bila ada),
   posting ke `rahaza_journal_entries` (+ `rahaza_journal_lines`).
5. Update AR Invoice → `status='issued'` + `gl_je_id`; update PO `gl_je_id`/`gl_je_number`.

**Respons:** `{ status: posted, je_id, je_number, already_posted }`.

> **Penting.** Posting AR **tidak** mengubah status PO menjadi `invoiced`. Perubahan itu
> terjadi di modul **Billing** ketika invoice final di-generate (`dewi_maklon_billing.py`).
> Di jalur PO-sentris ini, setelah Posting AR: AR Invoice = `issued`, PO tetap `completed`
> dengan `gl_je_id` terisi (bukti sudah masuk buku besar).

#### 5.4.1 Sequence End-to-End

```mermaid
sequenceDiagram
    autonumber
    actor Staf as Staf Maklon
    actor Fin as Finance
    participant UI as MaklonPOModule
    participant API as /api/dewi/maklon
    participant DB as MongoDB
    Staf->>UI: Buat PO + item/seri
    UI->>API: POST /pos
    API->>DB: dewi_maklon_pos (draft)
    Staf->>UI: Konfirmasi PO
    UI->>API: POST /pos/id/confirm
    API->>DB: rahaza_work_orders + rahaza_ar_invoices (draft)
    API->>DB: PO status confirmed
    Staf->>UI: Buat + Konfirmasi Dispatch
    UI->>API: POST /dispatches
    UI->>API: PUT /dispatches/id/confirm
    API->>DB: dispatch dispatched + PO completed
    Fin->>UI: Post ke Finance GL
    UI->>API: POST /finance/pos/id/post-ar
    API->>DB: rahaza_journal_entries (Dr AR / Cr Pendapatan)
    API->>DB: AR invoice issued + PO.gl_je_id
    API-->>UI: je_number (posted)
```

---

## 6. Kontrak Endpoint Happy-Path

### 6.1 Endpoint Kritikal
Empat endpoint ini **wajib** dikuasai; semua diverifikasi grounded ke route backend.

| # | Method | Endpoint | Fungsi backend (berkas:baris) | Fungsi bisnis |
|---|---|---|---|---|
| 1 | POST | `/api/dewi/maklon/pos` | `dewi_maklon_pos.py:271` | Buat PO Maklon (draft) |
| 2 | POST | `/api/dewi/maklon/pos/{id}/confirm` | `dewi_maklon_pos.py:540` | Confirm → auto WO + Draft AR Invoice |
| 3 | POST | `/api/dewi/maklon/dispatches` | `dewi_maklon_pos.py:707` | Buat Surat Jalan (partial/penuh) |
| 4 | POST | `/api/dewi/maklon/finance/pos/{id}/post-ar` | `dewi_maklon_finance.py:209` | Posting AR Invoice ke GL |

### 6.2 Endpoint Pendukung (Grounded)
| Method | Endpoint | Berkas:baris | Fungsi |
|---|---|---|---|
| GET | `/api/dewi/maklon/pos` | `dewi_maklon_pos.py:233` | Daftar PO + progress dispatch |
| GET | `/api/dewi/maklon/pos/{id}` | `dewi_maklon_pos.py:393` | Detail PO (item, dispatch, BOM, AR) |
| PUT | `/api/dewi/maklon/pos/{id}` | `dewi_maklon_pos.py:444` | Update PO (draft/confirmed) |
| POST | `/api/dewi/maklon/pos/{id}/cancel` | `dewi_maklon_pos.py:663` | Batalkan PO |
| GET | `/api/dewi/maklon/pos/{id}/dispatches` | `dewi_maklon_pos.py:694` | Riwayat dispatch 1 PO |
| PUT | `/api/dewi/maklon/dispatches/{id}/confirm` | `dewi_maklon_pos.py:782` | Konfirmasi dispatch |
| PUT | `/api/dewi/maklon/dispatches/{id}/cancel` | `dewi_maklon_pos.py:847` | Batalkan dispatch |
| POST | `/api/dewi/maklon/material-receive` | `dewi_maklon_pos.py:886` | Terima material klien (opsional) |
| POST | `/api/dewi/maklon/bom` | `dewi_maklon_pos.py:982` | Buat BOM Maklon (opsional) |
| GET | `/api/dewi/maklon/clients` | `dewi_maklon.py:226` | Daftar klien (form PO) |
| GET | `/api/dewi/maklon/buyer-catalog` | `dewi_maklon_buyer_catalog.py:117` | Katalog artikel buyer |
| POST | `/api/dewi/maklon/finance/pos/{id}/advance-payment` | `dewi_maklon_finance.py:237` | Input DP klien (opsional) |
| POST | `/api/dewi/maklon/invoices/generate` | `dewi_maklon_billing.py:199` | Generate invoice final → PO `invoiced` |
| GET | `/api/dewi/maklon/pos/{id}/360` | `dewi_maklon_po_360.py:74` | Ringkasan 360° 1 PO |

### 6.3 Ringkasan Kode Status HTTP
| Kode | Kapan muncul |
|---|---|
| **200** | Buat/Confirm/Dispatch/Post-AR/GET berhasil |
| **400** | Confirm bukan draft, dispatch melebihi sisa, dispatch saat PO belum confirmed, posting saat draft, dispatch status salah |
| **404** | Klien/PO/Dispatch tidak ditemukan |
| **422** | Price drift block ≥25% tanpa `force_price_drift` |

---

## 7. Aturan Bisnis & Validasi (Grounded)

1. **Klien wajib ada.** `client_id` harus merujuk klien valid → 404 bila tidak
   (`dewi_maklon_pos.py:275`).
2. **Item minimal.** PO tanpa item tidak bisa di-confirm (400 saat confirm; `:554`).
3. **Confirm hanya sekali & dari draft** (400 bila status lain; `:552`).
4. **Auto WO per item** memakai `source='maklon'` dan referensi balik `maklon_po_id` (`:586`).
5. **Auto Draft AR Invoice** dibuat dengan baris per item (jasa CMT) dan total = `total_value`.
6. **Dispatch tidak melebihi sisa.** Validasi per item (`:736`).
7. **PO harus confirmed sebelum dispatch** (400 bila draft; `:714`).
8. **Status pengiriman otomatis** (`completed`/`partial_delivered`; `:828`), tidak menimpa
   `invoiced`/`cancelled`.
9. **Posting AR idempotent** (cek JE existing; `dewi_maklon_finance.py:52`).
10. **Posting AR butuh profil GL** `maklon_ar_invoice` (fallback `ar_invoice`); jika tidak
    ada → 400 (`:56–61`).
11. **Cancel PO** dilarang bila sudah ada dispatch terkonfirmasi (400; `:675`).
12. **PO → invoiced** hanya via Billing generate invoice (`dewi_maklon_billing.py:279`).

### 7.1 Kasus Negatif & Tepi (yang Diuji)
| Skenario | Ekspektasi |
|---|---|
| Buat PO dengan `client_id` tak dikenal | 404 |
| Dispatch saat PO masih `draft` | 400 |
| Confirm PO yang sudah `confirmed` | 400 |
| Dispatch qty melebihi sisa | 400 |
| Posting AR dipanggil dua kali | `already_posted = true` (idempotent) |

---

## 8. Panduan Latihan (Skenario Praktik)

Latihan memakai akun admin & 1 klien maklon (buat dulu di modul **Klien** bila belum ada).

**Latihan A — Siklus penuh (happy path).**
1. Portal Maklon → **PO** → **Buat PO Baru** → pilih klien.
2. Tambah 1 item: Seri `S01`, Artikel bebas, Warna `Black`, Size `M`, Qty `20`, Rate `5000`.
   Klik **Buat PO** → PO muncul status **Draft**.
3. Klik kartu PO → **Konfirmasi PO**. Amati: badge **AR Invoice** muncul; PO jadi **Confirmed**.
   (Di produksi, 1 Work Order per item ikut terbentuk.)
4. Klik **Buat Dispatch** → centang item, isi qty `20` → **Buat Dispatch**.
5. Pada riwayat dispatch, klik **Konfirmasi** → PO menjadi **Completed** (terkirim 20/20).
6. Klik **Post ke Finance GL** → muncul badge **GL Posted (nomor JE)**; AR Invoice → *issued*.

**Latihan B — Uji aturan.**
1. Coba **Buat Dispatch** sebelum PO dikonfirmasi → ditolak.
2. Coba dispatch qty > sisa → ditolak dengan pesan sisa.
3. Klik **Post ke Finance GL** dua kali → posting kedua idempotent (tidak dobel jurnal).

**Latihan C — Pengiriman bertahap.**
1. Buat PO qty `20`. Confirm. Dispatch `12` → konfirmasi → PO **Partial**.
2. Dispatch sisa `8` → konfirmasi → PO **Completed**. Amati status pengiriman otomatis.

---

## 9. Diagram Ringkas Data (Relasi)

```mermaid
graph LR
    C[dewi_maklon_clients] --> PO[dewi_maklon_pos]
    PO -->|confirm| WO[rahaza_work_orders source=maklon]
    PO -->|confirm| AR[rahaza_ar_invoices]
    PO --> DSP[dewi_maklon_dispatches]
    AR -->|post-ar| JE[rahaza_journal_entries]
    PO -.opsional.-> MR[dewi_maklon_material_receive]
    PO -.opsional.-> BOM[dewi_maklon_bom]
```

---

## 10. Fitur Pendukung (Ringkas)

Bagian ini sengaja **ringkas** — bukan jalur kritikal.

- **PO 360° (`maklon-po-360`).** Tampilan gabungan progres 1 PO (produksi, dispatch, finance)
  via `GET /api/dewi/maklon/pos/{id}/360` dan timeline. Dibuka dari tombol **360°**
  (`data-testid="po-view-360-{id}"`) pada daftar PO.
- **Billing (`maklon-billing`).** Generate invoice final (`/api/dewi/maklon/invoices/generate`
  → PO `invoiced`), pencatatan pembayaran, dan laporan aging/billing. Finalisasi tagihan &
  pelunasan ada di sini.
- **Buyer Catalog.** Master artikel milik buyer: auto-fill artikel + rate, plus guard price
  drift (warn ≥10%, block ≥25%). Dipakai lewat autocomplete pada baris item PO.
- **Material Receive & BOM Maklon.** Pencatatan material titipan klien
  (`/api/dewi/maklon/material-receive`, masuk `dewi_maklon_inventory` ownership `maklon_client`)
  dan BOM per PO. Opsional; tidak menghentikan alur bila dilewati.
- **Sample, QC Tracking, HPP, AI Quote, SLA.** Modul pendukung terpisah (sampel produk,
  pelacakan QC, kalkulasi HPP jasa, penawaran berbasis AI, dan dashboard SLA). Berada di luar
  jalur PO inti dan cukup diketahui keberadaannya.
- **Advance Payment (DP).** Klien dapat membayar uang muka via
  `/api/dewi/maklon/finance/pos/{id}/advance-payment` sebelum tagihan final.

---

## 11. Troubleshooting (FAQ)

| Gejala | Kemungkinan penyebab | Tindakan |
|---|---|---|
| Tombol **Konfirmasi PO** tak ada | PO bukan status `draft` | Hanya PO draft yang bisa dikonfirmasi |
| Confirm gagal (400) | PO tanpa item | Tambah minimal 1 item dulu |
| Tombol **Buat Dispatch** tak muncul | PO masih `draft` | Confirm PO dulu |
| Dispatch ditolak (400) | Qty melebihi sisa | Kurangi qty ≤ sisa |
| **Post ke Finance GL** gagal (400) | Posting profile `maklon_ar_invoice` belum ada | Minta Finance konfigurasi posting profile |
| PO tak menjadi `invoiced` | Posting AR ≠ invoiced | Generate invoice final di modul Billing |
| Buat PO tertahan (422) | Price drift ≥25% | Sesuaikan rate atau setujui `force_price_drift` |
| PO tak bisa dibatalkan | Sudah ada dispatch terkonfirmasi | Batalkan dispatch dulu (jika masih draft) |

---

## 12. Spesifikasi & Hasil Uji

### 12.1 Skrip Uji Backend
Berkas: **`tests/flow_maklon_inti_test.py`**. Menguji jalur penuh di layer API + DB dengan
**self-cleanup** (fixture klien maklon dibuat lalu dihapus; seluruh PO, WO, dispatch, AR
invoice, jurnal (JE+lines), material receive/BOM ikut dibersihkan pada blok `finally`). Aman
dijalankan pada database live.

Jalankan:
```
python3 tests/flow_maklon_inti_test.py
```

### 12.2 Matriks Skenario Uji (17 kasus) — Hasil: 17/17 PASS
| ID | Tipe | Skenario | Hasil |
|---|---|---|---|
| TC-00 | State | Fixture klien maklon dibuat | PASS |
| TC-01 | Negatif | Buat PO klien tak valid → 404 | PASS |
| TC-02 | Happy | Buat PO → draft, qty 20, value 100.000 | PASS |
| TC-03 | State | Detail PO: `item_id` ada, status draft | PASS |
| TC-04 | Negatif | Dispatch saat PO draft → 400 | PASS |
| TC-05 | Happy | Confirm PO → 1 WO + Draft AR Invoice | PASS |
| TC-06 | State | WO maklon tercipta (`source=maklon`) | PASS |
| TC-07 | State | Status PO = confirmed | PASS |
| TC-08 | Negatif | Confirm ulang (bukan draft) → 400 | PASS |
| TC-09 | Negatif | Dispatch melebihi sisa → 400 | PASS |
| TC-10 | Happy | Buat dispatch penuh (20) | PASS |
| TC-11 | Happy | Konfirmasi dispatch → PO completed | PASS |
| TC-12 | State | PO completed, qty_dispatched 20 | PASS |
| TC-13 | Happy | Post-AR → JE terbentuk (posted) | PASS |
| TC-14 | State | AR invoice `issued` + PO `gl_je_id` | PASS |
| TC-15 | Edge | Post-AR idempotent → already_posted | PASS |
| CLEANUP | State | Semua dokumen uji dihapus | PASS |

**Ringkasan:** 17 PASS · 0 FAIL. Verifikasi cleanup: `work_orders=1, dispatches=1, pos=1,
journal_lines=2, journal_entries=1, ar_invoices=1, fixture_client=1` terhapus bersih.

### 12.3 Uji UI End-to-End
Alur juga diverifikasi lewat browser (Playwright via testing agent): Login → Portal Maklon →
PO → Buat PO → Confirm → Dispatch → Post ke Finance GL. Rincian & catatan QA:
[`_qa/flow-maklon-inti_bugs.md`](../_qa/flow-maklon-inti_bugs.md) dan
[`_qa/BUG_REGISTER.md`](../_qa/BUG_REGISTER.md).

### 12.4 Audit Statis Test-ID
Komponen alur dipindai dengan `scripts/docgen/audit_testids.py` sebelum uji E2E. Kontrol
happy-path (`maklon-po-create-btn`, `maklon-po-confirm-btn`, `maklon-po-dispatch-open-btn`,
`maklon-dispatch-submit-btn`, `maklon-po-postar-btn`, dll.) telah ditambahkan sehingga alur
dapat ditarget otomatis. Hasil audit: **0 blocker** (tidak ada duplikat testid lintas-file).

---

## 13. Rubrik Kualitas Dokumen

| Kriteria | Bobot | Skor | Catatan |
|---|---|---|---|
| Grounding (anti-halusinasi) | 25 | 25 | Semua endpoint terverifikasi ke route backend |
| Cakupan happy-path kritikal | 25 | 24 | 4 fase + 4 endpoint kritikal lengkap |
| Kejelasan langkah & diagram | 20 | 19 | Flowchart + sequence + state disertakan |
| Bukti uji nyata | 15 | 15 | 17/17 PASS + self-cleanup + audit statis |
| RBAC & aturan bisnis | 15 | 14 | Matriks + 12 aturan grounded |
| **Total** | **100** | **97/100** | Lulus ambang mutu (≥ 95) |

---

## 14. Katalog data-testid Jalur Utama (`maklon-po`)

| data-testid | Elemen | Fase |
|---|---|---|
| `maklon-po-page` | Kontainer halaman PO | Semua |
| `maklon-po-create-btn` | Buka form Buat PO | 1 |
| `maklon-po-refresh-btn` | Muat ulang daftar | 1 |
| `maklon-po-search-input` | Cari PO/klien | 1 |
| `maklon-po-card-{id}` | Kartu PO (buka detail) | 1–4 |
| `maklon-po-form-client-select` | Pilih klien | 1 |
| `maklon-po-add-item-btn` | Tambah baris item | 1 |
| `po-item-{idx}-seri` / `-color` / `-size` / `-qty` / `-rate` | Field item | 1 |
| `po-item-{idx}-artikel` | Autocomplete artikel (Buyer Catalog) | 1 |
| `maklon-po-form-save-btn` | Simpan/Buat PO | 1 |
| `maklon-po-confirm-btn` | Konfirmasi PO | 2 |
| `maklon-po-dispatch-open-btn` | Buka form dispatch | 3 |
| `dispatch-item-{idx}-check` / `-qty` | Pilih item + qty kirim | 3 |
| `maklon-dispatch-submit-btn` | Buat dispatch | 3 |
| `maklon-dispatch-confirm-{id}` | Konfirmasi dispatch | 3 |
| `maklon-po-material-btn` / `maklon-po-bom-btn` | Terima material / BOM (opsional) | 3 |
| `maklon-po-postar-btn` | Post ke Finance GL | 4 |
| `po-view-360-{id}` | Buka PO 360° | pendukung |

---

## 15. Referensi Kode (Grounding)

**Backend:**
- `backend/routes/dewi_maklon_pos.py` — `create_maklon_po` (271), `get_maklon_po` (393),
  `update_maklon_po` (444), `confirm_maklon_po` (540), `cancel_maklon_po` (663),
  `create_dispatch` (707), `confirm_dispatch` (782), `receive_material_from_client` (886),
  `create_maklon_bom` (982); helper penomoran (43–62); guard drift (117).
- `backend/routes/dewi_maklon_finance.py` — `post_maklon_ar_invoice` (40),
  `post_ar_for_po` (209), advance-payment (237).
- `backend/routes/dewi_maklon_billing.py` — `generate_invoice` (199), set PO `invoiced` (279).
- `backend/routes/dewi_maklon_po_360.py` — 360° (74), timeline (251).
- `backend/routes/rahaza_posting.py` — `_create_posted_je` (JE ke `rahaza_journal_entries`).

**Frontend:**
- `frontend/src/components/erp/MaklonPOModule.jsx` — `POForm.handleSave` (209),
  `ItemRow` (~84), `DispatchForm.handleDispatch` (398), `PODetail.postAR` (547),
  tombol Konfirmasi PO (602), main module (1085).
- `frontend/src/components/erp/MaklonPO360Module.jsx`, `MaklonBillingModule.jsx` (pendukung).

**Manifest sumber:**
- `docs/user-guide/_manifests/maklon-po.manifest.json`
- `docs/user-guide/_manifests/maklon-po-360.manifest.json`
- `docs/user-guide/_manifests/maklon-billing.manifest.json`

---

## 16. Kamus Istilah (Glossary)

Kosakata kunci alur Maklon. Menguasainya mempercepat komunikasi Staf Maklon–Finance–Gudang.

| Istilah | Arti | Konteks di alur |
|---|---|---|
| **Maklon / CMT** | Jasa produksi (Cut, Make, Trim) untuk pihak lain | Model bisnis Portal Maklon |
| **Klien / Buyer** | Pemilik artikel yang memesan jasa | `client_id` pada PO |
| **PO Maklon** | Purchase Order jasa dari klien (`dewi_maklon_pos`) | Objek utama alur |
| **Item / Seri** | Baris produk dalam PO (artikel+warna+size) | `items[]`, tiap punya `seri_no` |
| **Rate CMT** | Harga jasa per pcs (Rp) | `cmt_rate_per_pcs`; subtotal = qty × rate |
| **Work Order (WO)** | Perintah kerja produksi per item | Auto dibuat saat Confirm (`source=maklon`) |
| **AR Invoice** | Faktur piutang jasa (`rahaza_ar_invoices`) | Auto Draft saat Confirm; `issued` saat Post-AR |
| **Dispatch / Surat Jalan** | Pengiriman hasil ke klien (`dewi_maklon_dispatches`) | Boleh bertahap (multi-dispatch) |
| **partial_delivered** | Sebagian qty PO sudah dikirim | Status PO setelah dispatch parsial |
| **completed** | Seluruh qty PO sudah dikirim | Status PO setelah dispatch penuh |
| **invoiced** | PO sudah difakturkan final | Di-set modul Billing (bukan Post-AR) |
| **Price drift** | Selisih rate vs default Buyer Catalog | Warn ≥10%, block ≥25% |
| **GL / JE** | General Ledger / Journal Entry (jurnal) | Dibuat saat Post-AR |
| **Posting profile** | Pemetaan akun untuk jurnal otomatis | `maklon_ar_invoice` (fallback `ar_invoice`) |
| **Idempotent** | Aman dipanggil berulang tanpa efek ganda | Perilaku Post-AR |
| **Advance Payment** | Uang muka (DP) dari klien | Endpoint finance opsional |
| **ownership `maklon_client`** | Penanda material milik klien | Material receive → `dewi_maklon_inventory` |

---

## 17. Referensi Field Payload (Grounded)

Rincian field untuk endpoint kritikal. Field opsional diberi default oleh backend.

### 17.1 `POST /api/dewi/maklon/pos` (Buat PO)
**Request**
| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `client_id` | string | ya | FK ke `dewi_maklon_clients` |
| `po_date` | string (YYYY-MM-DD) | tidak | default hari ini |
| `deadline` | string | tidak | target selesai |
| `payment_terms` | string | tidak | default `net_30` (cod/net_14/net_30/net_60) |
| `items[]` | array | ya | daftar item/seri |
| `items[].seri_no` | string | ya | nomor seri (mis. S01) |
| `items[].artikel` | string | ya | kode artikel |
| `items[].sku_code` | string | tidak | SKU |
| `items[].color` / `size` | string | tidak | warna/ukuran |
| `items[].qty` | int (>0) | ya | jumlah pcs |
| `items[].cmt_rate_per_pcs` | number (≥0) | tidak | rate CMT; default 0 / dari catalog |
| `items[].buyer_catalog_id` | string | tidak | referensi Buyer Catalog (auto-fill + drift) |
| `force_price_drift` | bool | tidak | bypass block drift ≥25% |

**Response**: dokumen PO — `id`, `po_number`, `client_id`, `client_name`, `status: draft`,
`items[]` (dengan `item_id`, `subtotal`, `status: pending`), `total_qty`, `total_value`,
`payment_status: unpaid`, dan `_drift_events` bila ada.

### 17.2 `POST /api/dewi/maklon/pos/{id}/confirm`
**Response**: `status: confirmed`, `po_number`, `work_orders_created[]`
(`item_id`, `wo_id`, `wo_number`), `ar_invoice_number`, `ar_invoice_id`. Efek: WO per item
di `rahaza_work_orders`, Draft AR Invoice di `rahaza_ar_invoices`, item PO → `in_production`.

### 17.3 `POST /api/dewi/maklon/dispatches`
**Request**
| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `po_id` | string | ya | PO harus confirmed/in_production/partial_delivered |
| `dispatch_date` | string | tidak | default hari ini |
| `driver_name` / `vehicle_no` | string | tidak | data pengiriman |
| `items[]` | array (≥1) | ya | item yang dikirim |
| `items[].item_id` | string | ya | dari `PO.items[].item_id` |
| `items[].seri_no` / `artikel` | string | ya | identitas item |
| `items[].qty_dispatched` | int (>0) | ya | ≤ sisa qty item |

**Response**: dokumen dispatch — `id`, `dispatch_number`, `status: draft`,
`total_qty_dispatched`. Konfirmasi via `PUT /dispatches/{id}/confirm` → `status: dispatched`,
`po_delivery_status` (`partial_delivered`/`completed`).

### 17.4 `POST /api/dewi/maklon/finance/pos/{id}/post-ar`
**Response**: `status: posted`, `je_id`, `je_number`, `already_posted` (bool). Jurnal:
**Dr Piutang Usaha (AR)** / **Cr Pendapatan Jasa Maklon** (+ PPN bila dikonfigurasi). Efek:
AR Invoice → `issued`; PO menyimpan `gl_je_id`/`gl_je_number`.

---

## 18. Ringkasan Eksekutif

Alur Maklon Inti mengubah pengelolaan jasa CMT menjadi rangkaian ringkas dan terhubung:
**Buat PO** menampung item/seri klien; **Confirm PO** dalam satu aksi menerbitkan **Work Order**
per item sekaligus **Draft AR Invoice**; **Surat Jalan/Dispatch** mengirim hasil (boleh
bertahap) dan otomatis memutakhirkan status pengiriman PO; lalu **Posting AR** mencatat piutang
ke buku besar (Dr Piutang / Cr Pendapatan Jasa Maklon) secara idempotent, dengan finalisasi
invoice & pembayaran dilanjutkan di modul **Billing**. Modul pusat `maklon-po` kini dilengkapi
`data-testid` pada seluruh kontrol jalur utama sehingga dapat diuji otomatis. Alur telah
**diverifikasi 17/17 PASS** pada uji backend beserta uji UI end-to-end, aman dijadikan materi
pelatihan operasional Portal Maklon.

---

## 19. Checklist Operasional Harian (Staf Maklon)

Gunakan checklist ini sebagai kartu kerja ringkas di lantai operasi Portal Maklon:

**Saat PO baru masuk dari klien**
- [ ] Pastikan **klien** sudah terdaftar (modul Klien); jika belum, daftarkan dulu.
- [ ] Buat PO: isi seri, artikel, warna, size, qty, dan **rate CMT** per item.
- [ ] Perhatikan peringatan **price drift** (kuning ≥10%): konfirmasi rate ke atasan bila perlu.
- [ ] Simpan → verifikasi nomor `MKL-{klien}-{tahun}-xxxx` dan total nilai.

**Saat PO siap diproduksi**
- [ ] Klik **Konfirmasi PO** → pastikan badge **AR Invoice** muncul.
- [ ] Cek antrean produksi: 1 **Work Order** per item telah terbentuk (`source=maklon`).
- [ ] (Opsional) Catat **Material** titipan klien & susun **BOM** bila diperlukan.

**Saat barang siap dikirim**
- [ ] Buat **Surat Jalan/Dispatch**: pilih item + qty (boleh partial), isi sopir & kendaraan.
- [ ] **Konfirmasi** dispatch → cek status PO berubah (`partial_delivered`/`completed`).
- [ ] Ulangi untuk sisa qty hingga PO **completed**.

**Saat penagihan**
- [ ] Klik **Post ke Finance GL** → pastikan badge **GL Posted (nomor JE)** muncul.
- [ ] Serahkan ke **Finance/Billing** untuk generate invoice final & catat pembayaran
      (status PO menjadi `invoiced`).
- [ ] Pantau keseluruhan progres via **PO 360°** kapan pun diperlukan.

> Tip: jalankan langkah berurutan. Sistem menolak lompatan tahap (mis. dispatch sebelum
> confirm, atau posting saat masih draft) demi menjaga konsistensi data produksi & keuangan.
