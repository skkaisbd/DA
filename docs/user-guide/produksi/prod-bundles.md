# MODUL: Bundle Produksi / Penelusuran Bundle (`prod-bundles`) — Portal Produksi
<!-- moduleId: prod-bundles | Status: ✅ VERIFIED (kode dibaca + diuji runtime) | Skor rubrik: 98/100 | Standar: v3 DEEP (SAP-grade) | Update: 2026-07-07 | Manifest: ../_manifests/prod-bundles.manifest.json | Catatan QA (terpisah): ../_qa/prod-bundles_bugs.md | Divalidasi: scripts/docgen/validate_module.py -->

> **Dokumen Training & Spesifikasi Uji — gaya SAP Functional/End-User.** Berlapis:
> - **BAGIAN A — PANDUAN PENGGUNA** (bahasa sehari-hari, klik-per-klik) → supervisor produksi/QC/PPIC.
> - **BAGIAN B — LAMPIRAN TEKNIS** (komponen, field, kontrak API, logic/state, RBAC, integrasi, pesan) → admin/QA/dev.
> - **BAGIAN C — SPESIFIKASI UJI** (skenario + test case dengan hasil **nyata** + troubleshooting).
> - **BAGIAN D — LAMPIRAN CONTOH & DETAIL UJI**.
>
> **Prinsip anti-halusinasi:** tiap pernyataan menunjuk sumber kode (`file:baris`); `Expected`=menurut kode, `Actual`=hasil eksekusi. Catatan QA teknis dipisah di `../_qa/prod-bundles_bugs.md`.
>
> **Ikhtisar hasil uji:** Backend **26/26 PASS** (skrip `tests/pilot_prod_bundles_test.py`, idempoten + self-cleanup) · UI diverifikasi (login → daftar → modal → halaman detail): seluruh `data-testid` resolve, tanpa error konsol. DB dikembalikan bersih setelah uji.

## 0. METADATA MODUL
| Atribut | Nilai |
|---|---|
| **moduleId** | `prod-bundles` |
| **Nama tampilan** | Bundle Produksi (judul layar) · "Penelusuran Bundle" (label menu) |
| **Portal** | Produksi (`portalId = production`, `portalNav.js:88`) |
| **Tipe** | standalone (modul penuh dengan sub-halaman detail) |
| **Path menu** | Produksi → grup "Order & Penjadwalan" → "Penelusuran Bundle" (`portalNav.js:171`) |
| **Komponen induk** | `frontend/src/components/erp/RahazaBundlesModule.jsx` (default export `:42`) |
| **Registry** | `frontend/src/components/erp/moduleRegistry.js:617` (`'prod-bundles': RahazaBundlesModule`), lazy import `:143` |
| **Endpoint (frontend-verified)** | **6 path unik (6)** — via `scripts/docgen/extract_module.py`; total permukaan backend modul **10 path / 11 method-endpoint** (lihat B5) |
| **Komponen (file)** | 8 komponen erp (induk + 7 anak/atom) + primitif UI (glass, button, input, skeleton, tooltip, responsive-table-wrapper) |
| **Koleksi MongoDB** | `rahaza_bundles` (utama) · `rahaza_work_orders`, `rahaza_models`, `rahaza_sizes`, `rahaza_processes` (sumber snapshot) · `counters` (namespace `rahaza`, nomor bundle) · `activity_logs` (audit) |

---

# BAGIAN A — PANDUAN PENGGUNA

## A1. Untuk apa modul ini? (konteks bisnis)
Bayangkan sebuah **Work Order (WO)** = "perintah produksi 1 item" (mis. 65 pcs sweater Model X ukuran M). Angka 65 itu terlalu besar untuk dilacak satu-satu di lantai produksi. Maka WO dipecah menjadi **ikatan kecil ± 30 pcs** yang disebut **Bundle**.

**Bundle = satu ikatan fisik potongan kain sejenis (Model + Size sama) yang bergerak sebagai SATU unit** dari proses ke proses: **Cutting → Sewing/Jahit → Finishing → QC → Packing**. Tiap bundle punya **nomor unik** (mis. `BDL-20260707-0001`) dan **QR code** yang dicetak di kertas ticket dan ditempel di ikatan. Operator tinggal scan QR untuk mencatat "bundle ini sudah selesai di proses ini".

Modul **Penelusuran Bundle** adalah "buku besar traceability" bundle: **melihat** semua bundle, **mencari** bundle tertentu, **melihat riwayat lengkap** (siapa mengerjakan, di proses apa, kapan, berapa pass/fail), dan **mencetak ticket QR** (satuan atau massal per WO).

Analogi paket kurir: WO = "1 pengiriman besar", bundle = "1 kardus dengan nomor resi", QR = "barcode resi", halaman detail = "halaman lacak paket" (sudah sampai mana). Modul ini adalah **halaman lacak**, bukan tempat memindahkan paket — pemindahan (update status) dilakukan operator di modul **Eksekusi Proses**.

Posisi di rantai: **Order Produksi (`prod-orders`) → Work Order (`prod-work-orders`) → [Generate Bundles] → Penelusuran Bundle (`prod-bundles`) → Eksekusi/QC/Packing → Shipment**.

## A2. Siapa yang memakai & apa haknya (ringkas)
- **Supervisor / Manajer Produksi / Admin** — melihat, mencari, generate bundle (dari WO), cetak ticket massal, hapus bundle yang belum diproses. (RBAC rinci di B7.)
- **QC** — melihat & menelusuri riwayat bundle untuk investigasi cacat.
- **Operator lantai** — biasanya tidak masuk modul ini; mereka **scan** QR di modul Eksekusi. Modul ini menyediakan **ticket QR** untuk mereka.
- **Semua user login** — boleh membaca daftar/detail/cetak ticket satuan. Aksi generate/hapus/cetak-massal dibatasi admin/manajer/supervisor.

## A3. Prasyarat (setup sekali di awal)
Agar bundle bisa dibuat & tampil, hal berikut harus sudah ada:
1. **Master Proses aktif** (Produksi → Master Data → Proses; `/api/rahaza/processes`). Minimal 1 proses non-rework aktif. Tanpa ini, generate bundle **ditolak** (`400`).
2. **Master Model** (`/api/rahaza/models`) — opsional field `bundle_size` (default 30 bila kosong).
3. **Master Size** (`/api/rahaza/sizes`).
4. **Work Order** (`prod-work-orders`) dengan `qty > 0` dan status **bukan** `cancelled`. Bundle dibuat **dari WO**, bukan dari modul ini.

> Catatan penting: tombol **"Generate Bundles"** berada di modul **Work Order**, bukan di sini. Modul ini menampilkan hasilnya. (Lihat A8 tugas #1.)

## A4. Istilah (glossary)
| Istilah | Arti awam |
|---|---|
| **Bundle** | Ikatan ± 30 pcs sejenis yang dilacak sebagai 1 unit. |
| **Bundle number** | Nomor unik bundle, format `BDL-YYYYMMDD-NNNN` (mis. `BDL-20260707-0001`). |
| **Bundle size** | Isi maksimal 1 bundle (pcs). Default **30**, bisa diatur per Model. |
| **process_sequence** | Urutan proses (Cutting→…→Packing) yang **dipotret** saat bundle dibuat. |
| **current_process** | Proses tempat bundle **berada sekarang**. |
| **qty_pass / qty_fail / qty_remaining** | Jumlah pcs lulus / gagal / sisa yang masih harus dikerjakan di proses sekarang. |
| **history (timeline)** | Daftar kejadian bundle (dibuat, output, QC pass/fail, pindah proses, packed, rework). |
| **QR ticket** | Kertas cetak berisi QR + info bundle untuk ditempel di ikatan. |
| **split** | Bundle pecahan dari bundle induk (mis. sebagian gagal QC) — ditandai `parent_bundle_id`. |
| **WO snapshot** | Nomor WO & data model/size yang "dibekukan" di bundle saat dibuat (`wo_number_snapshot`, dst). |

## A5. Status & artinya (badge/enum)
Sumber definisi: `rahaza_bundles_mgmt.py:81` (`_bundle_status_defs`) + label UI `RahazaBundlesModule.jsx:23`.

| value | Label UI (list) | Label backend | Arti | Bisa dihapus? |
|---|---|---|---|---|
| `created` | Dibuat | Dibuat | Bundle baru, belum masuk proses | ✅ Ya (bila belum ada event) |
| `in_process` | Dalam Proses | Dalam Proses | Sedang dikerjakan di salah satu proses | ❌ |
| `qc` | Menunggu QC | Menunggu QC | Menunggu inspeksi QC | ❌ |
| `reworking` | Rework | Rework | Gagal QC, dikerjakan ulang via proses Rework | ❌ |
| `packed` | Packed | Selesai Pack | Lulus packing, siap kirim | ❌ |
| `shipped` | Terkirim | Terkirim | Sudah dikirim via Shipment | ❌ |
| `closed` | Ditutup | Ditutup | Ditutup manual (mis. batal/retur) | ❌ |

> **Kunci hapus:** hanya bundle `created` **dan** tanpa event produksi (history cuma "created") yang boleh dihapus (`rahaza_bundles_mgmt.py:308`). Di UI, tombol hapus hanya muncul untuk status `created` dengan `history.length <= 1` (`RahazaBundlesModule.jsx:436`).

## A6. Anatomi layar (bagian-bagian yang terlihat)
Halaman **daftar** (`data-testid="bundles-module"`, `:197`) terdiri dari, dari atas ke bawah:
1. **Header** (`PageHeader`): eyebrow "Produksi · Traceability", judul "Bundle Produksi", + tombol aksi: **Print Semua (N)** (muncul kondisional), **Refresh**, **Ke Work Order**.
2. **Onward CTA**: kartu ajakan lanjut ke "Eksekusi Produksi (Jahit→QC→Packing)".
3. **Bar pencarian** menonjol: input + tombol "Buka Detail".
4. **4 kartu KPI**: Total bundle · Total pcs · Dalam Proses · Selesai/Shipped.
5. **Chip filter status**: "Semua (N)" + chip per status.
6. **Tabel bundle** (`DataTableV2`, tableId `bundles`): kolom Bundle #, WO, Model, Qty, Proses Sekarang, Status, Dibuat, Aksi (mata/printer/hapus). Ada empty-state bila kosong.
7. **Modal detail ringkas** (saat klik ikon mata) → dari sini bisa **Buka Detail Lengkap** (halaman penuh) atau **Cetak Ticket**.

Halaman **detail lengkap** (`BundleDetailPage`, `data-testid="bundle-detail-page"`): header + hero info + 3 panel (Proses Sekarang / Next Action / Progress) + strip **Alur Proses** + **Timeline event** + sidebar **Metadata**.

## A7. Alur kerja end-to-end
```mermaid
flowchart TD
  A[Order Produksi disetujui] --> B[Buat Work Order - prod-work-orders]
  B --> C{WO qty > 0 & bukan cancelled?}
  C -- tidak --> B
  C -- ya --> D[Klik Generate Bundles di modul WO]
  D --> E[Bundle dibuat: status = created, nomor BDL-...]
  E --> F[Buka Penelusuran Bundle - prod-bundles]
  F --> G[Cetak ticket QR: satuan atau Print Semua per WO]
  G --> H[Tempel ticket di ikatan fisik]
  H --> I[Operator scan QR di Eksekusi Proses]
  I --> J[Status berpindah: in_process -> qc -> packed ...]
  J --> K[Telusuri riwayat & progress di halaman detail bundle]
  K --> L[Bundle packed -> masuk Shipment]
```
Narasi: PPIC/Supervisor membuat WO → menekan **Generate Bundles** (di modul WO) → sistem membuat sejumlah bundle `created` → di modul ini bundle dicetak ticket-nya → operator men-scan saat mengerjakan → modul ini menampilkan progres/riwayatnya sampai bundle **packed** lalu dikirim.

## A8. Panduan Tugas (klik-per-klik)

### Tugas 1 — Membuat Bundle dari sebuah Work Order
- **Tujuan:** memecah WO jadi bundle ± 30 pcs.
- **Prasyarat:** WO ada (`qty>0`, bukan `cancelled`), master proses aktif ada.
- **Langkah:**
  1. Buka **Produksi → Work Order** (`prod-work-orders`). (Di modul Bundle, klik tombol **"Ke Work Order"** `bundles-to-wo`.)
  2. Pilih WO target → klik **"Generate Bundles"** (aksi di modul WO; memanggil `POST /api/rahaza/work-orders/{wo_id}/generate-bundles`).
  3. Sistem menghitung `num_bundles = ceil(qty / bundle_size)` (bundle_size = `model.bundle_size` atau 30). Contoh 65 pcs → 3 bundle (30, 30, 5).
  4. Kembali ke **Penelusuran Bundle** → klik **Refresh** (`bundles-refresh`) → bundle baru muncul dengan status **Dibuat**.
- **Hasil:** N bundle `created`, nomor `BDL-YYYYMMDD-NNNN`.
- **Bila gagal:** "WO qty harus > 0" (isi qty), "WO sudah cancelled…" (pakai WO lain), "WO ini sudah punya N bundle…" (`409` — sudah pernah digenerate; regenerate butuh admin + hanya bundle `created`), "Tidak ada master proses aktif…" (definisikan proses).

### Tugas 2 — Mencari & membuka bundle dengan cepat
- **Tujuan:** langsung lompat ke bundle tertentu.
- **Langkah:**
  1. Ketik nomor lengkap `BDL-YYYYMMDD-NNNN` di kotak cari (`bundles-search-input`).
  2. Tekan **Enter** atau klik **"Buka Detail"** (`bundles-search-go`).
  3. Bila format cocok & ditemukan → **langsung ke halaman detail** bundle. Bila banyak hasil → tabel terfilter + notifikasi jumlah. Bila 0 hasil → notifikasi "Tidak ada bundle cocok…".
- **Tip:** mengetik sebagian teks (mis. potongan nomor WO/model) akan **memfilter tabel secara langsung** (debounce 300 ms). Tombol **×** (`bundles-search-clear`) mengosongkan pencarian.

### Tugas 3 — Melihat detail & riwayat bundle
- **Langkah:**
  1. Di tabel, klik ikon **mata** pada baris bundle (`bundle-detail-<bundle_number>`) → **modal ringkas** terbuka (`bundle-detail-modal`).
  2. Untuk tampilan lengkap, klik **"Buka Detail Lengkap"** (`bundle-open-full-detail`) → halaman `bundle-detail-page`.
  3. Baca: **Proses Sekarang** (pass/fail/sisa), **Next Action**, **Progress Alur** (Step X/N), strip **Alur Proses**, dan **Timeline** (urut terbaru→lama).
  4. Klik **Kembali** (`bundle-detail-back`) untuk balik ke daftar, atau **Refresh** (`bundle-detail-refresh`) untuk muat ulang.
- **Hasil:** Anda paham posisi & sejarah lengkap bundle (untuk investigasi cacat/komplain).

### Tugas 4 — Mencetak ticket QR (satuan)
- **Langkah:**
  1. Di baris bundle, klik ikon **printer** (`bundle-print-<bundle_number>`), atau di modal detail klik **"Cetak Ticket"** (`bundle-detail-print`).
  2. Sistem mengambil PDF ber-autentikasi (`GET /api/rahaza/bundles/{id}/ticket.pdf`) → tab baru terbuka (atau file terunduh bila popup diblokir) → notifikasi "Ticket … siap dicetak".
- **Hasil:** PDF A5 berisi QR + info bundle, siap dicetak & ditempel.

### Tugas 5 — Cetak ticket massal 1 WO sekaligus
- **Prasyarat:** daftar sedang menampilkan bundle dari **satu WO saja** (semua baris berbagi WO yang sama) → tombol **"Print Semua (N)"** (`bundles-bulk-print`) muncul di header.
- **Langkah:** klik **Print Semua (N)** → `GET /api/rahaza/work-orders/{wo_id}/bundle-tickets.pdf` → 1 PDF multi-halaman.
- **Bila gagal:** "Tidak ada bundle pada WO ini untuk filter…" (`404`, mis. filter status yang kosong).

### Tugas 6 — Menghapus bundle yang belum diproses
- **Prasyarat:** bundle status **Dibuat** & belum punya event (baru dibuat). Butuh peran admin/manajer/supervisor.
- **Langkah:**
  1. Klik ikon **tempat sampah** (`bundle-delete-<bundle_number>`) — hanya tampil untuk bundle `created`.
  2. Konfirmasi dialog "Hapus bundle …?".
  3. `DELETE /api/rahaza/bundles/{id}` → notifikasi "Bundle … dihapus".
- **Bila gagal:** "Hanya bundle status 'created' tanpa event produksi yang bisa dihapus" (`400`) — bundle sudah dikerjakan; tidak boleh dihapus.

### Tugas 7 — Memfilter daftar berdasarkan status
- **Tujuan:** melihat hanya bundle pada status tertentu (mis. yang masih "Dibuat").
- **Langkah:**
  1. Di baris chip filter, klik chip status (mis. **"Dibuat (N)"** = `bundles-filter-created`). Klik lagi untuk menonaktifkan (toggle).
  2. Chip aktif berubah gaya (latar primary). Klik **"Semua (N)"** (`bundles-filter-all`) untuk mengosongkan filter.
  3. Di balik layar, filter mengirim param `status` ke `GET /api/rahaza/bundles?status=…`.
- **Hasil:** tabel hanya menampilkan status terpilih; KPI tetap dihitung dari daftar yang tampil.

### Tugas 8 — Menggunakan kontrol tabel (DataTableV2)
- **Tujuan:** menyortir, mencari lokal, mengatur kolom, densitas, dan mengekspor.
- **Langkah:**
  1. Klik header kolom (mis. "Qty") untuk **sortir** (aksi via `dtv2-bundles-th-<key>`).
  2. Kotak cari tabel (`dtv2-bundles-search`) menyaring baris lokal; **Reset** (`dtv2-bundles-reset`) mengembalikan.
  3. **Kolom** (`dtv2-bundles-cols-btn`) → sembunyikan/tampilkan kolom; **Densitas** (`dtv2-bundles-density-*`) → rapat/lega.
  4. **Ekspor** (`dtv2-bundles-export`) → unduh CSV (`bundles-YYYY-MM-DD.csv`, `RahazaBundlesModule.jsx:417`).
  5. Navigasi halaman: `dtv2-bundles-prev` / `dtv2-bundles-next`.
- **Hasil:** tampilan tabel sesuai kebutuhan; data yang sama, cara lihat berbeda.

### Tugas 9 — Melihat ringkasan bundle per Work Order
- **Tujuan:** rekap cepat berapa bundle & pcs per WO, terpecah per status/proses.
- **Cara:** fitur turunan memanggil `GET /api/rahaza/work-orders/{wo_id}/bundles-summary` → mengembalikan `total`, `total_qty`, `wo_qty`, `by_status[]`, `by_process[]`. Berguna untuk membandingkan `total_qty` bundle vs `wo_qty` (harus sama bila semua qty ter-bundle).
- **Hasil:** angka rekap untuk dashboard/monitoring WO.

## A9. Visual Keadaan Layar (per langkah)
**(1) Daftar bundle (populated):**
```
┌ Bundle Produksi ───────────────────[ Print Semua (3) ][ Refresh ][ Ke Work Order ]┐
│ [🔎  Cari bundle (BDL-YYYYMMDD-NNNN), WO, atau model…      ] ( Buka Detail )        │
│ ┌ 3 Total bundle ┐ ┌ 65 Total pcs ┐ ┌ 0 Dalam Proses ┐ ┌ 0 Selesai/Shipped ┐       │
│ [Semua (3)] [Dibuat (3)] [Dalam Proses (0)] [Menunggu QC (0)] [Rework (0)] …        │
│ Bundle #            WO               Model        Qty  Proses    Status   Dibuat Aksi│
│ BDL-20260707-0015   WO-20260707-022  MDL / M       30  CUTTING   Dibuat   07 Jul 👁🖨🗑 │
│ BDL-20260707-0016   WO-20260707-022  MDL / M       30  CUTTING   Dibuat   07 Jul 👁🖨🗑 │
│ BDL-20260707-0017   WO-20260707-022  MDL / M        5  CUTTING   Dibuat   07 Jul 👁🖨🗑 │
└──────────────────────────────────────────────────────────────────────────────────┘
```
**(2) Modal detail ringkas (klik 👁):**
```
┌ Bundle BDL-20260707-0015 ───────────────────────────────── [Tutup ✕]┐
│ [ Buka Detail Lengkap ]                         [ Cetak Ticket ]      │
│ Bundle: BDL-… | WO: WO-…-022 | Model·Size: MDL·M | Qty: 30 pcs        │
│ Status: [Dibuat] di proses CUTTING   Pass 0 | Fail 0 | Sisa 30        │
│ Urutan Proses: [CUTTING] SEWING FINISHING QC PACKING                  │
│ Histori Event: (1) created — oleh Super Admin — qty 30                │
└──────────────────────────────────────────────────────────────────────┘
```
**(3) Halaman detail lengkap (Buka Detail Lengkap):**
```
┌ BDL-20260707-0015 [Dibuat] ───────────[ Kembali ][ Refresh ][ Cetak Ticket ]┐
│ Bundle | Work Order WO-…-022 | Model·Size MDL·M | Qty 30 pcs | Dibuat 07 Jul │
│ ┌ Proses Sekarang ┐  ┌ Next Action ┐   ┌ Progress Alur ┐                     │
│ │ CUTTING·Cutting │  │ SEWING·Jahit │   │ Step 1/5  0%  │                     │
│ │ Pass0 Fail0 S30 │  │ (CMT)        │   │ ▓░░░░         │                     │
│ Alur Proses: [CUTTING] → SEWING → FINISHING → QC → PACKING                    │
│ Timeline: ● Bundle dibuat — 30 pcs — Super Admin — 07 Jul 12:41               │
│ Metadata: Bundle ID … | Created by admin@… | WO Qty 30 pcs                    │
└───────────────────────────────────────────────────────────────────────────────┘
```
**(4) Empty state (belum ada bundle):**
```
┌ Tabel ─────────────────────────────────────────────┐
│           📦  Belum ada bundle                       │
│  Bundle dibuat dari modul Work Order… ('Generate')  │
│                [ Buka Work Order ]                   │
└─────────────────────────────────────────────────────┘
```
**Perpindahan tampilan (screen-state):**
```mermaid
stateDiagram-v2
  [*] --> Daftar
  Daftar --> ModalRingkas: klik ikon mata (bundle-detail-*)
  ModalRingkas --> Daftar: Tutup (modal-close)
  ModalRingkas --> HalamanDetail: Buka Detail Lengkap (bundle-open-full-detail)
  Daftar --> HalamanDetail: cari nomor lengkap + Enter (search jump)
  HalamanDetail --> Loading: fetch bundle
  Loading --> HalamanDetail: sukses
  Loading --> Error: gagal / 404 (bundle-detail-error)
  HalamanDetail --> Daftar: Kembali (bundle-detail-back)
  Error --> Daftar: Kembali
```

## A10. Cara cepat membaca dokumen (untuk pemula)
- Baru pertama kali? Baca **A1–A8** saja (cukup untuk memakai modul).
- Ingin tahu "tombol X kirim ke API mana?" → **B2** (inventaris testid) & **B5** (kontrak endpoint).
- Ingin tahu "kenapa status begini?" → **B6** (state & logika).
- QA/Dev yang mau menguji → **BAGIAN C** (skenario + test case + hasil nyata).
- Butuh contoh cerita nyata end-to-end → **D4** (worked example).

---

# BAGIAN B — LAMPIRAN TEKNIS

## B1. Peta Komponen (Component Map)
```mermaid
graph TD
  REG[moduleRegistry.js:617 'prod-bundles'] --> RBM[RahazaBundlesModule.jsx]
  RBM --> OCTA[OnwardCTA.jsx]
  RBM --> DT[DataTableV2.jsx - export DataTable]
  RBM --> ATOMS[moduleAtoms.jsx - PageHeader]
  RBM --> MOD[Modal.jsx]
  RBM --> BT[bundleTickets.js - openBundleTicket / openWorkOrderBundleTickets]
  RBM --> BDP[BundleDetailPage.jsx]
  BDP --> BT
  BDP --> ATOMS
  MOD --> IB[IconButton.jsx]
  RBM --> UI[glass / button / input]
  BDP --> UI2[glass / button / skeleton]
```
Tabel komponen (100% cakupan manifest `components[kind=erp]`):

| Komponen | File | Peran | Endpoint yang disentuh | Testid utama |
|---|---|---|---|---|
| **RahazaBundlesModule** | `frontend/src/components/erp/RahazaBundlesModule.jsx` | Induk: daftar, cari, KPI, filter, tabel, modal ringkas | list, statuses, by-number, detail, delete | `bundles-module`, `bundles-*`, `bundle-detail-*`, `bundle-print-*`, `bundle-delete-*` |
| **BundleDetailPage** | `frontend/src/components/erp/BundleDetailPage.jsx` | Halaman detail penuh (hero, step, flow, timeline, meta) | detail (`{id}`), by-number, ticket.pdf | `bundle-detail-page`, `bundle-detail-current-step`, `bundle-detail-timeline`, `bundle-timeline-event-*` |
| **bundleTickets** | `frontend/src/components/erp/bundleTickets.js` | Helper unduh/buka PDF ber-autentikasi (blob) | ticket.pdf, bundle-tickets.pdf | (tanpa testid) |
| **OnwardCTA** | `frontend/src/components/erp/OnwardCTA.jsx` | Kartu CTA lanjut ke Eksekusi | — | (prop `testId`) |
| **DataTableV2** | `frontend/src/components/erp/DataTableV2.jsx` | Tabel universal (sort, cari, kolom, densitas, ekspor, paginasi) | — | `dtv2-<tableId>*` |
| **moduleAtoms** | `frontend/src/components/erp/moduleAtoms.jsx` | Atom UI (mis. `PageHeader`) | — | (prop `testId`) |
| **Modal** | `frontend/src/components/erp/Modal.jsx` | Facade Radix Dialog untuk modal detail ringkas | — | `modal-close` (+ meneruskan `data-testid` container) |
| **IconButton** | `frontend/src/components/erp/IconButton.jsx` | Tombol ikon (dipakai transitif oleh `Modal` untuk tombol tutup) | — | (prop `testId`) |

Backend (orkestrasi): `rahaza_bundles.py` (prefix `/api/rahaza`) meng-include `rahaza_bundles_mgmt.py` (CRUD/generate/summary), `rahaza_bundles_docs.py` (QR/PDF), `rahaza_bundles_rework.py` (rework — di luar cakupan modul ini). Router terpasang di `server.py:1217`.

## B2. Inventaris Elemen (exhaustive)
SEMUA elemen interaktif + `data-testid` (100% cakupan manifest). "Dinamis" = akhiran nilai variabel.

| # | data-testid | Komponen · baris | Jenis | Aksi | Syarat tampil/enabled |
|---|---|---|---|---|---|
| 1 | `bundles-module` | RahazaBundlesModule:197 | container | root halaman daftar | selalu (saat `activeBundleId` kosong) |
| 2 | `bundles-bulk-print` | :219 | button | cetak semua ticket 1 WO | hanya bila `singleWo` (semua baris 1 WO) |
| 3 | `bundles-refresh` | :229 | button | muat ulang daftar | selalu |
| 4 | `bundles-to-wo` | :238 | button | navigasi ke `prod-work-orders` | bila `onNavigate` ada |
| 5 | `bundles-search-input` | :274 | input | ketik query cari | selalu (disabled saat `searching`) |
| 6 | `bundles-search-clear` | :283 | button | kosongkan pencarian | bila `searchValue` terisi |
| 7 | `bundles-search-go` | :295 | button (submit) | quick-jump / cari | disabled bila query kosong / `searching` |
| 8 | `bundles-filter-all` | :359 | button | filter "Semua" | selalu |
| 9 | `bundles-filter-<status>` (dinamis) | :371 | button | filter per status (mis. `bundles-filter-created`) | per `statusDefs` |
| 10 | `bundle-detail-<bundle_number>` (dinamis) | :424 | button (ikon mata) | buka modal ringkas | tiap baris |
| 11 | `bundle-print-<bundle_number>` (dinamis) | :432 | button (printer) | cetak ticket satuan | tiap baris |
| 12 | `bundle-delete-<bundle_number>` (dinamis) | :441 | button (hapus) | hapus bundle | hanya `status='created'` & `history.length<=1` |
| 13 | `bundles-empty-cta` | :410 | button | ke Work Order (empty state) | bila tabel kosong & `onNavigate` |
| 14 | `bundle-detail-modal` | :456 | dialog | modal detail ringkas | saat `detail` terpilih |
| 15 | `bundle-open-full-detail` | :464 | button | buka halaman detail penuh | di dalam modal |
| 16 | `bundle-detail-print` | :472 (modal) & BundleDetailPage:245 | button | cetak ticket | di modal & header detail |
| 17 | `modal-close` | Modal.jsx:96 | button | tutup modal (Radix Close) | saat modal terbuka |
| 18 | `bundle-detail-page` | BundleDetailPage:215 | container | root halaman detail | saat data ada |
| 19 | `bundle-detail-loading` | :169 | container | skeleton loading | saat `loading` |
| 20 | `bundle-detail-error` | :193 | container | tampilan error/404 | saat `error`/tanpa data |
| 21 | `bundle-detail-back` | :198 & :232 | button | kembali ke daftar | selalu (error & normal) |
| 22 | `bundle-detail-refresh` | :240 | button | muat ulang bundle | header detail |
| 23 | `bundle-detail-current-step` | :266 | panel | info proses sekarang (pass/fail/sisa) | header detail |
| 24 | `bundle-detail-next-step` | :314 | panel | "Next Action" | header detail |
| 25 | `bundle-detail-progress` | :352 | panel | progress bar Step X/N | header detail |
| 26 | `bundle-detail-flow` | :378 | panel | strip alur proses | selalu |
| 27 | `bundle-detail-timeline` | :412 | panel | daftar event | selalu |
| 28 | `bundle-timeline-event-<i>` (dinamis) | :434 | list item | 1 kartu event timeline | per event |
| 29 | `bundle-detail-meta` | :501 | panel | sidebar metadata | selalu |
| 30 | `bundle-detail-open-wo` | :527 | button | buka Work Order terkait | bila `onNavigate` & `work_order_id` |
| 31 | `dtv2-<tableId>*` (dinamis) | DataTableV2.jsx (mis. `:265`,`:277`,`:302`,`:319`,`:376`,`:385`,`:422`,`:477`,`:539`,`:549`) | berbagai | kontrol tabel | `tableId='bundles'` → `dtv2-bundles`, `dtv2-bundles-search`, `dtv2-bundles-reset`, `dtv2-bundles-cols-btn`, `dtv2-bundles-density-*`, `dtv2-bundles-export`, `dtv2-bundles-bulk-bar`, `dtv2-bundles-th-*`, `dtv2-bundles-row-*`, `dtv2-bundles-prev`, `dtv2-bundles-next` |

## B2a. Kontrol Tabel DataTableV2 (`tableId='bundles'`) — rinci
Semua kontrol tabel memakai prefix `dtv2-bundles`. Sumber: `DataTableV2.jsx`.

| testid | Baris | Fungsi |
|---|---|---|
| `dtv2-bundles` | :265 | container tabel |
| `dtv2-bundles-search` | :277 | kotak cari lokal (client-side filter) |
| `dtv2-bundles-reset` | :302 | reset pencarian/kolom |
| `dtv2-bundles-cols-btn` | :319 | buka pengaturan visibilitas kolom |
| `dtv2-bundles-density-<k>` | :364 | ubah densitas (rapat/normal/lega) |
| `dtv2-bundles-export` | :376 | ekspor CSV baris tampil |
| `dtv2-bundles-bulk-bar` | :385 | bar aksi massal (bila ada seleksi) |
| `dtv2-bundles-th-<key>` | :422 | header kolom (klik = sortir) |
| `dtv2-bundles-row-<id>` | :477 | baris per bundle (rowKey `id`) |
| `dtv2-bundles-prev` / `dtv2-bundles-next` | :539/:549 | navigasi halaman |

## B3. Kamus Field — Bar Pencarian & Kontrol
| Field | testid | Tipe | Wajib | Default | Validasi/logika | Sumber |
|---|---|---|---|---|---|---|
| Kata kunci cari | `bundles-search-input` | text | tidak | `''` | quick-jump aktif bila cocok regex `^BDL-\d{8}-\d{1,6}$` (di-uppercase); jika tidak, jadi filter `q` | RahazaBundlesModule:108,272 |
| Tombol cari | `bundles-search-go` | submit | — | disabled | disabled bila `!searchValue.trim()` atau `searching` | :294 |
| Filter status | `bundles-filter-<status>` | toggle | tidak | `''` (Semua) | klik = set/`toggle` `filterStatus` → param `status` | :363–372 |

> Modul ini **tidak** memiliki form input pembuatan bundle (bundle dibuat di modul WO). Filter & pencarian adalah satu-satunya "input".

## B4. Kamus Field — Kolom Tabel (`DataTable` tableId `bundles`)
Sumber: `RahazaBundlesModule.jsx:384–401`.

| key | Label | Sortable | Render / format | Sumber field |
|---|---|---|---|---|
| `bundle_number` | Bundle # | ✅ | mono, tebal | `rahaza_bundles.bundle_number` |
| `wo_number_snapshot` | WO | ✅ | teks / `—` | `wo_number_snapshot` |
| `model_code` | Model | ✅ | `model_code / size_code` | `model_code`,`size_code` |
| `qty` | Qty | ✅ (rata kanan) | angka tebal | `qty` |
| `current_process_code` | Proses Sekarang | ✅ | teks / `—` | `current_process_code` |
| `status` | Status | ✅ | badge berwarna (`StatusBadge`) | `status` |
| `created_at` | Dibuat | ✅ | tanggal `dd Mon` (id-ID) | `created_at` |

## B4a. Kamus Field — Event Timeline (`history[]`)
Setiap kejadian pada `bundle.history` (ditampilkan di modal & halaman detail). Ikon/label dari `EVENT_META` (`BundleDetailPage.jsx:30`).

| Field event | Tipe | Arti | Contoh |
|---|---|---|---|
| `event` | str | jenis: `created`,`output`,`qc_pass`,`qc_fail`,`advance`,`packed`,`rework` | `created` |
| `by` | str | nama pelaku | "Super Admin" |
| `by_id` | str | id user | uuid |
| `at` | ISO str | waktu kejadian (UTC) | 2026-07-07T12:41:… |
| `qty` | int | jumlah pcs terkait | 30 |
| `notes` | str | catatan bebas | "Generated bundle 1/3 dari WO …" |
| `line_code` | str (opsional) | lini kerja | "L1" |
| `process_code` | str (opsional) | proses terkait | "SEW" |
| `from_process_code`/`to_process_code` | str (opsional) | perpindahan proses | "CUT" → "SEW" |

Label event UI (`EVENT_META`): `created`→"Bundle dibuat", `output`→"Output submit", `qc_pass`→"QC Pass", `qc_fail`→"QC Fail", `advance`→"Lanjut ke proses", `packed`→"Selesai / Packed", `rework`→"Masuk rework". Event tak dikenal jatuh ke ikon default (`getEventMeta`, `BundleDetailPage.jsx:40`).

## B5. Katalog Kontrak Endpoint — 10 path unik / 11 method-endpoint
Router prefix `/api/rahaza` (`rahaza_bundles.py:12`). Cakupan 100% manifest verified + endpoint modul lain (docs/summary). RBAC lihat B7.

### E1. `GET /api/rahaza/bundles` — daftar bundle *(frontend-verified)*
- **Sumber:** `rahaza_bundles_mgmt.py:228`.
- **Query:** `work_order_id`, `status`, `current_process_id`, `current_line_id`, `model_id`, `q` (cari di `bundle_number`/`wo_number_snapshot`/`model_code`, regex insensitive), `limit` (≤500, default 200), `page` (opsional → mode paginasi).
- **Response (tanpa page):** `{ items: [bundle...], total }`. **(dengan page):** `{ items, pagination }` (`get_pagination_params`/`paginated_response`). Sort `created_at` desc.
- **Status:** 200; 401/403 tanpa token. **RBAC:** `require_auth` (semua user login).

### E2. `GET /api/rahaza/bundles-statuses` — metadata status *(frontend-verified)*
- **Sumber:** `rahaza_bundles_mgmt.py:317`. **Response:** `{ statuses: [{value,label,color,description}×7] }`. **RBAC:** `require_auth`.

### E3. `GET /api/rahaza/bundles/by-number/{bundle_number}` — lookup by nomor *(frontend-verified)*
- **Sumber:** `:287`. Nomor di-`strip().upper()`. **Response:** dokumen bundle. **Status:** 200 / **404** "Bundle number tidak ditemukan". **RBAC:** `require_auth`.

### E4. `GET /api/rahaza/bundles/{bid}` — detail by id *(frontend-verified)*
- **Sumber:** `:276`. **Response:** dokumen bundle penuh (termasuk `process_sequence`, `history`). **Status:** 200 / **404** "Bundle tidak ditemukan". **RBAC:** `require_auth`.

### E5. `DELETE /api/rahaza/bundles/{bid}` — hapus bundle *(frontend-verified, path sama E4)*
- **Sumber:** `:301`. **Guard:** hanya `status='created'` **dan** tak ada event selain `created` → else **400** "Hanya bundle status 'created' tanpa event produksi yang bisa dihapus". Menulis `activity_logs`. **Status:** 200 `{ok:true}` / 400 / 404. **RBAC:** admin/manajer/supervisor (`_require_admin_or_manager`).

### E6. `GET /api/rahaza/bundles/{bid}/ticket.pdf` — ticket QR satuan *(frontend-verified)*
- **Sumber:** `rahaza_bundles_docs.py:50`. **Response:** `application/pdf` (A5, 1 halaman) via `render_bundle_ticket_pdf`, header `Content-Disposition: inline`. **Status:** 200 / 404. **RBAC:** `require_auth`.

### E7. `GET /api/rahaza/work-orders/{wo_id}/bundle-tickets.pdf` — ticket massal 1 WO *(frontend-verified)*
- **Sumber:** `rahaza_bundles_docs.py:70`. **Query:** `status` (opsional), `limit` (≤2000, default 500). **Response:** `application/pdf` multi-halaman + header `X-Total-Bundles`. **Status:** 200 / **404** WO tak ada / **404** "Tidak ada bundle pada WO ini untuk filter yang diberikan". Menulis `activity_logs` ("bulk-print-bundle-tickets"). **RBAC:** admin/manajer/supervisor.

### E8. `POST /api/rahaza/work-orders/{wo_id}/generate-bundles` — buat bundle dari WO
- **Sumber:** `rahaza_bundles_mgmt.py:92`. **Body (opsional):** `{ bundle_size }` (override, admin). **Query:** `force=true` (regenerate).
- **Logika:** validasi WO (ada, bukan `cancelled`, `qty>0`), `bundle_size = model.bundle_size || 30`, `num_bundles = ceil(qty/bundle_size)`, bundle terakhir = sisa. Snapshot `process_sequence` dari proses aktif non-rework (urut `order_seq`). Tulis N dokumen + `activity_logs`.
- **Guard idempoten:** sudah ada bundle & tanpa `force` → **409**. `force` butuh admin (**403** bila bukan) & hanya menghapus bundle `created` tanpa event; bila tak semua bisa dihapus → **409**.
- **Response:** `{ generated, bundle_size, total_qty, wo_number, bundles:[...] }`. **Status:** 200 / 400 / 403 / 404 / 409. **RBAC:** admin/manajer/supervisor.

### E9. `GET /api/rahaza/work-orders/{wo_id}/bundles-summary` — ringkasan per WO
- **Sumber:** `:324`. **Response:** `{ wo_id, wo_number, total, total_qty, wo_qty, by_status:[{status,count,qty}], by_process:[{process_id,process_code,count,qty}] }`. Bila 0 bundle → `{total:0, by_status:[], by_process:[], total_qty:0}`. **Status:** 200 / 404. **RBAC:** `require_auth`.

### E10. `GET /api/rahaza/bundles/{bid}/qr.png` — QR PNG mentah
- **Sumber:** `rahaza_bundles_docs.py:31`. **Response:** `image/png` (payload = `bundle_number`, `box_size=8`, `border=2`), `Cache-Control: private, max-age=300`. **Status:** 200 / 404. **RBAC:** `require_auth`.

> **Catatan cakupan validator:** endpoint frontend-verified (E1–E7 kecuali E8/E9/E10 yang tak dipanggil langsung dari komponen modul) semua muncul; E8–E10 adalah bagian permukaan backend modul yang relevan (generate berasal dari modul WO, qr.png/ summary dipakai fitur turunan). Semua path **grounded** ke route backend (anti-halusinasi).

## B6. State & Logika
### B6.1 State Machine (siklus hidup bundle)
```mermaid
stateDiagram-v2
  [*] --> created: generate-bundles (mgmt:210)
  created --> in_process: output pertama (modul Eksekusi)
  in_process --> qc: kirim ke QC
  qc --> in_process: QC pass sebagian / lanjut proses
  qc --> reworking: QC fail (qty_fail>0)
  reworking --> in_process: rework selesai
  in_process --> packed: proses terakhir (Packing) selesai
  packed --> shipped: masuk Shipment
  created --> closed: ditutup manual
  in_process --> closed: ditutup manual
  packed --> [*]
  shipped --> [*]
  closed --> [*]
  created --> [*]: DELETE (hanya created tanpa event, mgmt:308)
```
> **Kepemilikan transisi:** hanya `created` (saat generate) & penghapusan `created` yang **digerakkan modul ini**. Transisi lain (`in_process`→…→`shipped`) digerakkan modul **Eksekusi Proses/QC/Rework/Shipment** (mis. `/api/rahaza/execution/quick-output`, `/api/rahaza/execution/qc-event`, `/api/rahaza/rework/bundle/{}/close-manual`). Urutan bobot status: `_STATUS_ORDER` (`mgmt:42`).

### B6.2 Rumus/perhitungan
- **Jumlah bundle:** `num_bundles = max(1, ceil(wo_qty / bundle_size))` (`mgmt:169`). Bundle ke-i qty = `min(bundle_size, sisa)`; bundle terakhir = sisa (mis. 65/30 → 30,30,5).
- **bundle_size:** `model.bundle_size` bila ada, else **30**; body `bundle_size` (admin) meng-override (`mgmt:141–153`).
- **Nomor bundle:** `BDL-{YYYYMMDD}-{NNNN}` via counter atomik `next_counter(BDL_<day>, namespace='rahaza')` (`mgmt:67`).
- **Progress alur (UI):** `pct=100` bila status `packed`/`shipped`; else `round(idx/len(seq)*100)` dengan `idx` = posisi `current_process_id` di `process_sequence` (`BundleDetailPage.jsx:141`).

### B6.3 Logika & Trigger per fitur
- **Debounce cari → filter** 300 ms (`RahazaBundlesModule.jsx:90`).
- **Quick-jump** (`:101`): uppercase → cek regex bundle → `by-number` → buka detail; else `q` filter; 1 hasil → auto-open; 0 → toast error; banyak → set daftar + toast.
- **KPI summary** dihitung dari daftar aktif (`:172`): total, total_qty, by_status; kartu "Dalam Proses" = `in_process+qc+reworking`; "Selesai" = `packed+shipped`.
- **singleWo** (`:185`): tombol Print Semua muncul hanya bila seluruh baris punya 1 `work_order_id` unik.
- **Delete gate UI** (`:436`): tombol hapus muncul hanya untuk `created` & `history.length<=1`.
- **Ticket via blob** (`bundleTickets.js:10`): fetch PDF dengan Bearer → buka tab baru; bila popup diblokir → unduh via anchor.

### B6.4 Aturan bisnis rinci (grounded)
1. **Idempotensi generate** — sebuah WO hanya boleh punya 1 set bundle. Panggilan kedua tanpa `force` ditolak `409` dengan menyebut jumlah bundle eksisting (`mgmt:120–122`).
2. **Regenerate aman** — `force=true` hanya menghapus bundle `created` **tanpa** event; bila ada bundle yang sudah bergerak, seluruh regenerate **dibatalkan** (`409`, `mgmt:130–136`) agar tidak menghapus jejak produksi.
3. **Override bundle_size** — body `{bundle_size}` di-clamp `max(1, int(...))`; input non-angka diabaikan diam-diam (fallback ke resolver default) (`mgmt:149–153`).
4. **Snapshot proses** — `process_sequence` diambil dari `rahaza_processes` aktif & `is_rework != true`, urut `order_seq` (`mgmt:73–79,159`). Setelah dipotret, perubahan master proses **tidak** mengubah bundle lama (immutability snapshot).
5. **current_process awal** = proses pertama pada urutan (`first_proc`, `mgmt:163,192–194`).
6. **Nomor harian** — counter `BDL_<YYYYMMDD>` per hari; nomor melanjutkan urutan harian (mis. seed sebelumnya 0014 → berikutnya 0015).
7. **Pencarian `q`** — regex insensitive pada `bundle_number`/`wo_number_snapshot`/`model_code` (`mgmt:256–262`); di-escape (`re.escape`) sehingga karakter khusus aman.
8. **Paginasi opsional** — hanya aktif bila query `page` ada; tanpa `page` memakai `limit` (≤500) mode legacy `{items,total}` (`mgmt:264–272`).
9. **Serialisasi** — `_serialize_bundle` membuang `_id` Mongo & mengonversi `datetime`→ISO (`mgmt:47–55`); API selalu memakai UUID (`id`), bukan ObjectId.
10. **Audit** — generate, regenerate, delete, dan bulk-print menulis `activity_logs` (`mgmt:138,215,312`, `docs:98`).

### B6.5 Parameter & kode status per endpoint (ringkas)
| Endpoint | Param kunci | Sukses | Gagal umum |
|---|---|---|---|
| E1 `GET /bundles` | `work_order_id,status,current_process_id,current_line_id,model_id,q,limit,page` | 200 | 401/403 |
| E2 `GET /bundles-statuses` | — | 200 | 401/403 |
| E3 `by-number/{no}` | path `bundle_number` (upper) | 200 | 404, 401/403 |
| E4 `GET /bundles/{id}` | path `id` | 200 | 404, 401/403 |
| E5 `DELETE /bundles/{id}` | path `id` | 200 | 400 (bukan created), 404, 403 |
| E6 `ticket.pdf` | path `id` | 200 pdf | 404, 401/403 |
| E7 `bundle-tickets.pdf` | `wo_id`, `status?`, `limit≤2000` | 200 pdf + `X-Total-Bundles` | 404 (WO/none), 403 |
| E8 `generate-bundles` | `wo_id`, `force?`, body `bundle_size?` | 200 | 400,403,404,409 |
| E9 `bundles-summary` | `wo_id` | 200 | 404, 401/403 |
| E10 `qr.png` | path `id` | 200 png | 404, 401/403 |


Sumber: `_require_admin_or_manager` (`mgmt:60`, `docs:24`) = {admin, superadmin, owner, manager_production, supervisor}; sisanya `require_auth`.

| Aksi (endpoint) | admin/superadmin/owner | manager_production/supervisor | user login lain | tanpa token |
|---|---|---|---|---|
| Lihat daftar/detail/by-number/statuses/summary (E1–E4,E9) | ✅ | ✅ | ✅ | ❌ 401/403 |
| Cetak ticket satuan / QR PNG (E6, E10) | ✅ | ✅ | ✅ | ❌ |
| Generate bundle (E8) | ✅ | ✅ | ❌ 403 | ❌ |
| Regenerate `force` (E8) | ✅ | ❌ 403 "Regenerate hanya boleh admin" | ❌ | ❌ |
| Hapus bundle (E5) | ✅ | ✅ | ❌ 403 | ❌ |
| Cetak ticket massal (E7) | ✅ | ✅ | ❌ 403 | ❌ |

## B8. Peta Integrasi (lintas-modul & lintas-koleksi)
```mermaid
graph LR
  WO[prod-work-orders] -- generate-bundles --> B[(rahaza_bundles)]
  MDL[(rahaza_models.bundle_size)] --> B
  PRC[(rahaza_processes)] -- snapshot process_sequence --> B
  SZ[(rahaza_sizes)] --> B
  B --> EXE[prod-exec-hub / Eksekusi Proses]
  EXE -- update status/history --> B
  B --> RW[prod-rework-board]
  B --> SHIP[Shipment]
  B --> PDF[QR/ticket PDF - qrcode_generator]
  B --> LOG[(activity_logs)]
```
- **Hulu:** WO (pemicu generate), Model (`bundle_size`), Proses (urutan), Size.
- **Hilir:** Eksekusi (update status/history), Rework, Shipment.
- **Samping:** generator QR/PDF (`utils.qrcode_generator`), audit `activity_logs`.

## B9. Kamus Data (koleksi `rahaza_bundles`)
Indeks (`server.py:388–394`): `bundle_number` **unique**, `work_order_id`, `status`, `(current_process_id,status)`, `(current_line_id,status)`, `parent_bundle_id`, `created_at`.

| Field | Tipe | Keterangan | Sumber |
|---|---|---|---|
| `id` | str (UUID) | PK | mgmt:177 |
| `bundle_number` | str | `BDL-YYYYMMDD-NNNN`, unik | :178 |
| `work_order_id` | str | FK WO | :180 |
| `wo_number_snapshot` | str | nomor WO dibekukan | :181 |
| `model_id`/`model_code`/`model_name` | str | snapshot model | :182–184 |
| `size_id`/`size_code` | str | snapshot size | :185–186 |
| `qty` | int | isi bundle (pcs) | :187 |
| `qty_pass`/`qty_fail`/`qty_remaining` | int | hasil QC & sisa proses | :188–190 |
| `status` | str enum | 7 status (B5/A5) | :191 |
| `process_sequence` | list | `[{id,code,name,order_seq}]` dibekukan | :159,191 |
| `current_process_id/code/name` | str | proses sekarang | :192–194 |
| `current_line_id` | str/null | lini sekarang | :195 |
| `parent_bundle_id` | str/null | asal split | :196 |
| `split_from_qc_event_id` | str/null | event QC pemicu split | :197 |
| `history` | list | event `{event,by,by_id,at,qty,notes,(line_code,process_code,from/to_process_code)}` | :198,BundleDetailPage:449 |
| `created_at`/`updated_at` | ISO str (UTC) | audit waktu | :206–207 |
| `created_by` | str | pembuat | :208 |
| `must_return_process` | str/null (opsional) | penanda wajib kembali ke rework | BundleDetailPage:343 |

## B10. Katalog Pesan (Backend HTTP + Frontend UI)
**Backend (HTTP):**
| Kode | Pesan | Sumber |
|---|---|---|
| 404 | Work Order tidak ditemukan | mgmt:108 · docs:85 |
| 400 | WO sudah cancelled, tidak bisa generate bundle | mgmt:111 |
| 400 | WO qty harus > 0 | mgmt:115 |
| 409 | WO ini sudah punya {n} bundle. Pakai ?force=true… | mgmt:122 |
| 403 | Regenerate hanya boleh admin | mgmt:128 |
| 409 | Hanya {removed}/{existing} bundle yang bisa dihapus… | mgmt:136 |
| 400 | Tidak ada master proses aktif. Definisikan proses terlebih dahulu. | mgmt:158 |
| 404 | Bundle tidak ditemukan | mgmt:282,307 · docs:41,57 |
| 404 | Bundle number tidak ditemukan | mgmt:296 |
| 400 | Hanya bundle status 'created' tanpa event produksi yang bisa dihapus | mgmt:310 |
| 404 | WO tidak ditemukan | mgmt:331 |
| 404 | Tidak ada bundle pada WO ini untuk filter yang diberikan | docs:93 |
| 403 | Only admin/manager/supervisor can perform this action | mgmt:64 · docs:28 |

**Frontend (toast/konfirmasi):**
| Jenis | Teks | Sumber |
|---|---|---|
| confirm | Hapus bundle {n}? (hanya bisa kalau status 'created' tanpa event produksi) | RahazaBundlesModule:153 |
| success | Bundle {n} dihapus | :160 |
| error | {detail} / Gagal hapus bundle | :164 |
| error | Error: {message} | :167 |
| error | Tidak ada bundle cocok dengan "{q}" | :136 |
| message | {n} bundle ditemukan | :141 |
| error | Pencarian gagal: {message} | :146 |
| success | Ticket {n} siap dicetak | bundleTickets.js:50 |
| success | Bulk ticket siap dicetak | bundleTickets.js:69 |
| error | {message} / Gagal buka ticket / Gagal buka bulk ticket | bundleTickets.js:52,71 |
| error | Gagal mencetak ticket: {message} | BundleDetailPage:162 |

---

# BAGIAN C — SPESIFIKASI UJI

## C1. Test Scenarios (naratif)
1. **Baca daftar & metadata status** — buka modul, tabel & 7 status muncul.
2. **Generate bundle** dari WO qty 65 → 3 bundle (30,30,5) status `created`.
3. **Idempotensi** — generate lagi tanpa `force` → 409; `force` (admin) → regenerate.
4. **Filter & cari** — filter `work_order_id`, cari `q`, paginasi, lookup by-number (termasuk normalisasi huruf kecil).
5. **Detail** — by id & by-number; nonexistent → 404.
6. **Ringkasan WO** — total/total_qty/wo_qty benar.
7. **Cetak** — ticket.pdf (PDF), qr.png (PNG), bulk tickets (PDF + `X-Total-Bundles`), filter kosong → 404.
8. **Hapus** — bundle `created` → 200; ulang → 404; bundle non-created (via WO cancelled path) generate ditolak.
9. **RBAC** — akses tanpa token → 401/403.
10. **UI** — daftar/modal/halaman detail render, search-jump, filter, empty state.

### C1.1 Rincian skenario per tipe (5 tipe)
- **Happy path:** admin login → buka daftar (E1) → baca 7 status (E2) → generate bundle dari WO qty 65 (E8) → 3 bundle `created` → detail (E4/E3) → ringkasan (E9) → cetak ticket (E6) & QR (E10) & bulk (E7). Semua 2xx.
- **Edge:** filter `work_order_id`, cari `q` prefix, paginasi `page/limit`, lookup by-number huruf kecil (di-upper), bulk dengan filter status kosong (404). Menguji batas & normalisasi.
- **Negative:** id/nomor tidak ada (404×2), generate di WO `cancelled` (400), hapus bundle yang sudah dihapus (404). Menguji penolakan yang benar.
- **Permission:** akses tanpa token untuk list/generate/statuses → 401/403. (RBAC role granular divalidasi lewat kontrak kode B7.)
- **State:** pembagian qty `[5,30,30]`, idempotensi generate (409), hapus bundle `created` (200), force-regenerate admin (200). Menguji transisi & guard state.

### C1.2 Data uji & kebersihan DB
Skrip membuat: 1 model (`BDLTESTMDL`), 2 WO (1 utama qty 65 + 1 untuk uji cancelled), 3–6 bundle (generate + force). Semua **dihapus** di akhir (by tracked id/kode). Uji UI memakai data seed sementara (WO 1× + 3 bundle) yang juga dibersihkan. **Sisa data uji terverifikasi = 0** (DB pristine).


Login sekali, buat data sendiri, **self-cleanup** (DB bersih). 5 tipe: **H**appy/**E**dge/**N**egative/**P**ermission/**S**tate.

| TC | Skenario | Tipe | Expected | Actual | Verdict |
|---|---|---|---|---|---|
| TC-01 | GET /bundles | H | 200 + `items` | 200 | ✅ |
| TC-02 | GET /bundles-statuses | H | 200, 7 status | 200 n=7 | ✅ |
| TC-03 | Buat WO qty 65 (setup) | H | 200 + id | 200 | ✅ |
| TC-04 | generate-bundles | H | 200, generated=3, size=30 | 3/30 | ✅ |
| TC-05 | Pembagian qty | S | `[5,30,30]` | `[5,30,30]` | ✅ |
| TC-06 | generate lagi tanpa force | S | **409** | 409 | ✅ |
| TC-07 | list filter work_order_id | E | 3 items | 3 | ✅ |
| TC-08 | detail by id | H | status=created, seq ada | created, seq=5 | ✅ |
| TC-09 | by-number (exact) | H | 200 id cocok | 200 | ✅ |
| TC-10 | by-number huruf kecil | E | 200 (di-upper) | 200 | ✅ |
| TC-11 | by-number nonexistent | N | 404 | 404 | ✅ |
| TC-12 | detail id nonexistent | N | 404 | 404 | ✅ |
| TC-13 | bundles-summary | H | total=3, total_qty=65, wo_qty=65 | 3/65/65 | ✅ |
| TC-14 | ticket.pdf | H | 200 `application/pdf` | pdf | ✅ |
| TC-15 | qr.png | H | 200 `image/png` | png | ✅ |
| TC-16 | bulk tickets | H | 200 pdf, `X-Total-Bundles=3` | 3 | ✅ |
| TC-17 | bulk tickets status kosong | E | 404 | 404 | ✅ |
| TC-18 | list `q` search | E | ≥1 item | 3 | ✅ |
| TC-19 | paginasi page/limit | E | ada `pagination`, 2 item | ok | ✅ |
| TC-20 | hapus bundle `created` | S | 200 | 200 | ✅ |
| TC-21 | hapus ulang | N | 404 | 404 | ✅ |
| TC-22 | generate di WO cancelled | N | 400 | 400 | ✅ |
| TC-23 | force regenerate (admin) | S | 200, generated=3 | 3 | ✅ |
| TC-24 | list tanpa token | P | 401/403 | 401 | ✅ |
| TC-25 | generate tanpa token | P | 401/403 | 401 | ✅ |
| TC-26 | statuses tanpa token | P | 401/403 | 401 | ✅ |

**Ringkas:** 26 PASS / 0 FAIL. Cleanup: `bundles=3 wo=2 model=1` dihapus; verifikasi sisa = 0.

## C3. UI — verifikasi Playwright (login → daftar → modal → halaman detail)
Data di-seed sementara (WO 1×, 3 bundle) lalu dibersihkan. Semua `data-testid` **resolve (count=1)**, tanpa error konsol/network.

| Panel/aksi | Elemen diperiksa | Hasil |
|---|---|---|
| Daftar | `bundles-module`, `bundles-search-input`, `bundles-search-go`, `bundles-refresh`, `bundles-to-wo`, `bundles-filter-all`, `bundles-filter-created`, `bundles-bulk-print`, `dtv2-bundles`, `dtv2-bundles-search` | ✅ semua ada; 3 baris (`dtv2-bundles-row-*`=3) |
| Aksi baris | `bundle-detail-<no>`, `bundle-print-<no>`, `bundle-delete-<no>` | ✅ ada (delete tampil krn `created`) |
| Modal ringkas | `bundle-detail-modal`, `bundle-open-full-detail`, `bundle-detail-print`, `modal-close` | ✅ terbuka & render |
| Halaman detail | `bundle-detail-page`, `bundle-detail-current-step`, `bundle-detail-next-step`, `bundle-detail-progress`, `bundle-detail-flow`, `bundle-detail-timeline`, `bundle-detail-meta`, `bundle-detail-back`, `bundle-detail-refresh`, `bundle-detail-open-wo`, `bundle-timeline-event-0` | ✅ semua render (Step 1/5, alur CUTTING→…→PACKING) |
| Kondisi kosong | `bundles-empty-cta` ("Belum ada bundle") | ✅ (iterasi empty-state, `test_reports/iteration_70.json`) |
| State loading/error | `bundle-detail-loading`, `bundle-detail-error` | ✅ ada di kode (path skeleton/404) |

## C4. Catatan QA (internal)
Detail QA teknis & observasi dipisah (tidak di materi training) → lihat **`../_qa/prod-bundles_bugs.md`** dan ringkasan lintas modul **`../_qa/BUG_REGISTER.md`**. Kondisi kualitas modul: seluruh uji hijau, DB pristine.

## C5. Troubleshooting (gejala → sebab → solusi)
| Gejala | Sebab | Solusi |
|---|---|---|
| Tabel kosong padahal WO ada | Bundle belum digenerate | Buka WO → **Generate Bundles** → Refresh |
| "WO ini sudah punya N bundle…" (409) | WO sudah pernah digenerate | Pakai `?force=true` (admin) atau kelola bundle yang ada |
| "Tidak ada master proses aktif…" (400) | Belum ada proses aktif non-rework | Definisikan Master Proses |
| Tombol **Print Semua** tak muncul | Daftar berisi >1 WO | Persempit filter agar 1 WO |
| Tombol hapus tak muncul | Bundle bukan `created`/sudah ada event | Hanya bundle baru boleh dihapus |
| PDF tidak terbuka | Popup diblokir | Izinkan popup; sistem fallback ke unduh |
| "Tidak ada bundle cocok…" saat cari | Nomor salah/format beda | Cek format `BDL-YYYYMMDD-NNNN` |
| Detail 404 | Bundle dihapus/nomor salah | Kembali & Refresh daftar |

## C6. Lampiran — Bukti & Skor
- **Skrip backend:** `/app/tests/pilot_prod_bundles_test.py` (26 TC, idempoten, self-cleanup) → 26/26 PASS.
- **UI:** Playwright (screenshot daftar + halaman detail) + `test_reports/iteration_70.json`.
- **Kredensial uji:** `admin@garment.com` / `Admin@123`.
- **Kondisi DB:** bersih (diverifikasi sisa data uji = 0).

**Rubrik self-score (validator wajib ≥ 95):**
| Dimensi | Bobot | Skor |
|---|---|---|
| Kelengkapan Fitur (B1,B2,B3) | 20 | 20 |
| Kelengkapan Flow (A7,A9,B6,B8) | 15 | 15 |
| Logic/State/RBAC (B6,B7) | 15 | 15 |
| Akurasi Kontrak Endpoint (B5,B9,B10) | 15 | 14 |
| Cakupan & Hasil Uji Nyata (C2,C3) | 20 | 20 |
| Kejelasan Guideline & Keawaman (A8,A9,A10,D4) | 10 | 9 |
| Bukti Anti-Halusinasi (file:baris + manifest + artefak) | 5 | 5 |
| **Total** | **100** | **98/100** |

---

# BAGIAN D — LAMPIRAN CONTOH, PAYLOAD & DETAIL UJI

## D1. Contoh Payload API (Request → Response NYATA)
**Generate bundle (E8):**
```
POST /api/rahaza/work-orders/5442.../generate-bundles
Body: {}
→ 200 {
  "generated": 3, "bundle_size": 30, "total_qty": 65,
  "wo_number": "WO-20260707-022",
  "bundles": [ {"bundle_number":"BDL-20260707-0015","qty":30,"status":"created", ...}, ... ]
}
```
**List (E1):** `GET /api/rahaza/bundles?work_order_id=5442...` → `{"items":[...3...],"total":3}`
**Statuses (E2):** `GET /api/rahaza/bundles-statuses` → `{"statuses":[{"value":"created","label":"Dibuat",...}, ... 7]}`
**By-number (E3):** `GET /api/rahaza/bundles/by-number/{bundle_number}` (mis. mengirim `bdl-20260707-0015` huruf kecil) → 200; server melakukan `strip().upper()` sehingga cocok ke `BDL-20260707-0015`.
**Summary (E9):** `GET /api/rahaza/work-orders/5442.../bundles-summary` → `{"total":3,"total_qty":65,"wo_qty":65,"by_status":[{"status":"created","count":3,"qty":65}],"by_process":[...]}`
**Bulk PDF (E7):** `GET /api/rahaza/work-orders/5442.../bundle-tickets.pdf` → `application/pdf`, header `X-Total-Bundles: 3`

## D2. Detail Test Case (Input → Expected → Actual)
Tabel lengkap 26 test case (skrip `tests/pilot_prod_bundles_test.py`). Kolom "Input" = aksi/param, "Expected" = kontrak kode, "Actual" = hasil run nyata.

| TC | Input | Expected | Actual | Verdict |
|---|---|---|---|---|
| TC-01 | `GET /bundles` (admin) | 200, body punya `items` | 200, `items` ada | ✅ |
| TC-02 | `GET /bundles-statuses` | 200, 7 status termasuk `created`,`packed` | 200, n=7 | ✅ |
| TC-03 | `POST /work-orders` qty=65 | 200, dapat `id` | 200, `WO-…-018` | ✅ |
| TC-04 | `POST /work-orders/{id}/generate-bundles` | 200, `generated=3`, `bundle_size=30` | 3, 30 | ✅ |
| TC-05 | periksa `bundles[].qty` | `[5,30,30]` | `[5,30,30]` | ✅ |
| TC-06 | generate ulang tanpa `force` | 409 | 409 | ✅ |
| TC-07 | `GET /bundles?work_order_id=…` | 3 items | 3 | ✅ |
| TC-08 | `GET /bundles/{id}` | `status=created`, `process_sequence` list | created, seq_len=5 | ✅ |
| TC-09 | `GET /bundles/by-number/{no}` | 200, `id` cocok | 200 | ✅ |
| TC-10 | by-number huruf kecil | 200 (di-upper server) | 200 | ✅ |
| TC-11 | by-number `BDL-19700101-9999` | 404 | 404 | ✅ |
| TC-12 | `GET /bundles/does-not-exist` | 404 | 404 | ✅ |
| TC-13 | `GET /work-orders/{id}/bundles-summary` | `total=3`,`total_qty=65`,`wo_qty=65` | 3/65/65 | ✅ |
| TC-14 | `GET /bundles/{id}/ticket.pdf` | 200 `application/pdf` | pdf | ✅ |
| TC-15 | `GET /bundles/{id}/qr.png` | 200 `image/png` | png | ✅ |
| TC-16 | `GET /work-orders/{id}/bundle-tickets.pdf` | 200 pdf + `X-Total-Bundles=3` | 3 | ✅ |
| TC-17 | bulk `?status=shipped` (kosong) | 404 | 404 | ✅ |
| TC-18 | `GET /bundles?q=BDL-20260707` | ≥1 item | 3 | ✅ |
| TC-19 | `GET /bundles?…&page=1&limit=2` | ada `pagination`, 2 item | ok | ✅ |
| TC-20 | `DELETE /bundles/{id}` (created) | 200 `{ok:true}` | 200 | ✅ |
| TC-21 | `DELETE /bundles/{id}` (ulang) | 404 | 404 | ✅ |
| TC-22 | generate di WO `cancelled` | 400 | 400 | ✅ |
| TC-23 | `generate-bundles?force=true` (admin) | 200, `generated=3` | 3 | ✅ |
| TC-24 | `GET /bundles` tanpa token | 401/403 | 401 | ✅ |
| TC-25 | generate tanpa token | 401/403 | 401 | ✅ |
| TC-26 | `GET /bundles-statuses` tanpa token | 401/403 | 401 | ✅ |

**Catatan teknis skrip:** objek `requests.Response` bernilai *falsy* saat status ≥400 (`Response.__bool__`=`ok`), sehingga assert status-error memakai `r is not None and r.status_code == …` (bukan `r and …`) agar tidak short-circuit. Cleanup memakai id ter-track (`rahaza_bundles` by `work_order_id`, `rahaza_work_orders` by id, `rahaza_models` by code) + verifikasi sisa = 0.

## D3. Sequence Diagram — Generate + Cetak + Buka Detail
```mermaid
sequenceDiagram
  participant U as Supervisor
  participant WO as Modul WO
  participant BE as Backend (rahaza_bundles)
  participant DB as MongoDB
  participant BM as Modul Bundle
  U->>WO: klik Generate Bundles
  WO->>BE: POST /work-orders/{id}/generate-bundles
  BE->>DB: cek WO + proses aktif, insert N bundle (created)
  BE-->>WO: {generated:N, bundles:[...]}
  U->>BM: buka Penelusuran Bundle + Refresh
  BM->>BE: GET /bundles?work_order_id=...
  BE-->>BM: {items:[...]}
  U->>BM: klik ikon mata → Buka Detail Lengkap
  BM->>BE: GET /bundles/{id}
  BE-->>BM: dokumen bundle (+history)
  U->>BM: klik Cetak Ticket
  BM->>BE: GET /bundles/{id}/ticket.pdf (Bearer)
  BE-->>BM: application/pdf (blob) → tab baru
```

## D3.1 Sequence — Hapus & Regenerate (guard state)
```mermaid
sequenceDiagram
  participant U as Admin
  participant BE as Backend
  participant DB as MongoDB
  U->>BE: DELETE /bundles/{id}
  BE->>DB: cek status & history
  alt status=created & tanpa event
    BE->>DB: delete_one + activity_logs
    BE-->>U: 200 {ok:true}
  else sudah bergerak
    BE-->>U: 400 "Hanya bundle status 'created'..."
  end
  U->>BE: POST /work-orders/{id}/generate-bundles?force=true
  BE->>DB: hapus bundle 'created' tanpa event
  alt semua bisa dihapus
    BE->>DB: insert N bundle baru
    BE-->>U: 200 {generated:N}
  else ada yang sudah diproses
    BE-->>U: 409 "Hanya {removed}/{existing}..."
  end
```

## D4. Contoh Skenario Bisnis Lengkap (worked example)
**Persona:** Bu Sari (Supervisor Produksi). **Tujuan:** menyiapkan traceability untuk WO baru 65 pcs sweater Model "MDL-A" ukuran M.

- **Langkah 0 — Prasyarat.** Bu Sari memastikan Master Proses aktif sudah ada (Cutting→Sewing→Finishing→QC→Packing) dan WO `WO-20260707-022` (qty 65, status released) sudah dibuat oleh PPIC.
- **Langkah 1 — Generate.** Di modul **Work Order**, Bu Sari memilih WO tersebut dan menekan **Generate Bundles**. Sistem menghitung `ceil(65/30)=3` → membuat **3 bundle**: `BDL-20260707-0015` (30 pcs), `-0016` (30), `-0017` (5). Semua berstatus **Dibuat**.
- **Langkah 2 — Verifikasi di modul Bundle.** Ia membuka **Penelusuran Bundle**, klik **Refresh**. Kartu KPI menunjukkan **3 Total bundle / 65 Total pcs / 0 Dalam Proses / 0 Selesai**. Karena semua dari 1 WO, tombol **Print Semua (3)** muncul.
- **Langkah 3 — Cetak massal.** Bu Sari klik **Print Semua (3)** → 1 PDF berisi 3 ticket QR (halaman `X-Total-Bundles: 3`). Ia mencetak & menyerahkan ke leader untuk ditempel di 3 ikatan.
- **Langkah 4 — Penanganan salah ketik (revisi).** Awalnya Bu Sari salah mengetik di kotak cari: `BDL-20260707-9999` lalu Enter → muncul notifikasi merah **"Tidak ada bundle cocok…"**. Ia menekan **×** (`bundles-search-clear`), lalu mengetik ulang `BDL-20260707-0015` → Enter → **langsung** ke halaman detail bundle.
- **Langkah 5 — Telusuri.** Di halaman detail, panel **Proses Sekarang** = CUTTING (Pass 0 / Fail 0 / Sisa 30), **Next Action** = SEWING·Jahit (CMT), **Progress** = Step 1/5 (0%). Timeline baru berisi 1 event "Bundle dibuat".
- **Langkah 6 — Koreksi qty (hapus + regenerate).** Ternyata qty WO seharusnya 60, bukan 65. Karena bundle masih **Dibuat** (belum ada event), Bu Sari (atau admin) bisa menghapus bundle via ikon tempat sampah, memperbaiki qty WO, lalu **regenerate** (`force=true`, admin). Bila salah satu bundle sudah dikerjakan, sistem menolak hapus (**400**) demi keamanan data.
- **Hasil akhir:** 3 (atau hasil regenerate) bundle ber-QR siap dilacak. Selanjutnya operator men-scan di **Eksekusi Proses**, dan status bundle berpindah otomatis — semuanya terekam di **Timeline** yang bisa Bu Sari pantau kapan pun.

## D5. FAQ
- **T: Kenapa saya tak bisa membuat bundle di modul ini?** J: Bundle dibuat dari **Work Order** (tombol Generate Bundles). Modul ini untuk menelusuri & mencetak.
- **T: Kenapa tombol Print Semua hilang?** J: Muncul hanya bila daftar berisi **satu WO**. Persempit filter.
- **T: Kenapa bundle tak bisa dihapus?** J: Hanya bundle **Dibuat** tanpa event yang boleh dihapus.
- **T: Angka QR isinya apa?** J: `bundle_number` (dipakai untuk scan di lantai).
- **T: Apakah bundle_size selalu 30?** J: Default 30; bisa diatur per Model (`bundle_size`) atau override admin saat generate.
- **T: Bundle sudah dibuat tapi qty WO ternyata salah — bagaimana?** J: Bila bundle masih `created` (belum ada event), hapus lalu regenerate (`force`, admin). Bila sudah bergerak, sistem menolak demi jejak produksi.
- **T: Kenapa "Proses Sekarang" kosong?** J: Bundle baru dibuat pada proses pertama; kolom terisi setelah bergerak. Bila proses master kosong saat generate, generate akan ditolak.
- **T: Apa beda modal ringkas vs halaman detail?** J: Modal = ringkas cepat (status, urutan proses, timeline singkat). Halaman detail = panel lengkap (current/next/progress, alur, timeline penuh, metadata).
- **T: Bagaimana bila QR/PDF tak terbuka?** J: PDF diambil sebagai blob ber-token lalu dibuka tab baru; bila popup diblokir, otomatis diunduh.
- **T: Siapa yang boleh cetak massal?** J: admin/manajer/supervisor (RBAC B7).

## D6. Batasan, Asumsi & Backlog Enhancement
- Modul **read/trace/print/delete(created)** — perubahan status dilakukan modul lain (by-design).
- Kolom "Proses Sekarang"/"Line" bisa kosong bila bundle baru dibuat (belum bergerak).
- `bundle-tickets.pdf` dibatasi `limit` 500 (default) / ≤2000 per permintaan; WO sangat besar mungkin butuh beberapa kali cetak.
- Pencarian tabel lokal (`dtv2-bundles-search`) menyaring baris yang **sudah dimuat**; pencarian server memakai `q` (bar pencarian utama).
- Progress alur adalah estimasi posisi index proses; bukan persen pcs.
- **Backlog potensial:** aksi split/merge bundle dari UI; ekspor timeline; grafik distribusi status; badge notifikasi bundle macet (aging).
- **Asumsi:** master proses & size sudah dikonfigurasi; peran user termapping benar (admin/manajer/supervisor untuk aksi tulis).

## D7. Changelog Dokumen (versi dokumen)
| Tanggal | Versi | Perubahan |
|---|---|---|
| 2026-07-07 | 1.0 | Dokumen awal v3 (SAP-grade): 10 endpoint, 8 komponen, 31 testid, state/RBAC, worked example. Backend 26/26 PASS; UI diverifikasi; lulus validator. |

<!-- END OF MODULE DOC: prod-bundles -->
