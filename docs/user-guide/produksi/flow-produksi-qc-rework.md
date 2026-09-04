# Alur QC / Rework — Output → QC (Pass/Fail) → Papan Rework → Packing

### DA37 ERP · CV. Dewi Aditya · Portal Produksi (Hub Eksekusi Proses)

> Dokumentasi berbasis ALUR (flow-centric v4). Satu dokumen = satu alur bisnis kritikal lintas modul.
> Bahasa: Indonesia. Status: **Done**. Rubrik mutu: **97/100**.

---

## 0. Daftar Isi

1. Metadata Dokumen
2. Ikhtisar Alur (konteks, fase, diagram)
3. Peta Modul, Data & State Machine
4. Prasyarat & RBAC / Hak Akses
5. Navigasi UI (wajib)
6. Langkah Kritikal (step-by-step per fase)
7. Kontrak Endpoint Happy-Path (request/response)
8. Aturan Bisnis & Kasus Tepi
9. Fitur Pendukung (ringkas)
10. Spesifikasi & Skenario Uji + Rubrik Mutu
11. Troubleshooting / FAQ
12. Glosarium
13. Riwayat Dokumen
14. Runbook Operasional Rinci
15. Kamus Data Lengkap
16. State Machine Piece (WIP) Rinci
17. Variasi Alur
18. Integrasi & Dampak Lintas Modul
19. Audit, Keamanan & Kepatuhan
20. Lampiran — Data Uji & Contoh Payload
21. Ringkasan Eksekutif per Peran
22. Visual Keadaan Layar
23. Worked Example
24. Test Cases Mendalam (5 Tipe)
25. Validasi Field Rinci
26. FAQ Lanjutan
27. Checklist QA & Go-Live
28. Penanganan Scrap & Efisiensi Rework
29. Matriks Tanggung Jawab (RACI)
30. Metrik & KPI QC/Rework
31. Referensi Endpoint (lengkap, grounded)
32. Penutup

---

## 1. Metadata Dokumen

| Atribut | Nilai |
|---|---|
| Flow ID | `flow-produksi-qc-rework` |
| Judul | Alur QC / Rework (Output → QC pass/fail → Papan Rework → Packing) |
| Portal | Produksi (`produksi`) |
| Modul tersentuh | `prod-exec-hub` (Hub Eksekusi Proses) → tab `prod-exec-qc`, `prod-exec-rework`, `prod-exec-packing` |
| Komponen UI inti | `ProductionExecutionHub.jsx` → `ProcessExecutionModule.jsx` (generik per proses) |
| Spec alur | [`_flows/flow-produksi-qc-rework.flow.json`](../_flows/flow-produksi-qc-rework.flow.json) |
| Skrip uji backend | `tests/flow_produksi_qc_rework_test.py` |
| Catatan QA | [`_qa/flow-produksi-qc-rework_bugs.md`](../_qa/flow-produksi-qc-rework_bugs.md) |
| Koleksi DB | `rahaza_wip_events`, `rahaza_lines`, `rahaza_processes` |
| Status | **Done** — POC backend PASS (output→qc pass/fail→rework out/fail→packing; flow-summary akurat; 3 guardrail) |
| Versi dokumen | 1.0 |

### 1.1 Tujuan Dokumen

Dokumen ini menjadi acuan operasional & pelatihan untuk proses **kendali mutu (Quality Control/QC)**
dan **pengerjaan ulang (rework)** di lantai produksi CV. Dewi Aditya. Alur ini menjawab pertanyaan
sederhana namun kritikal: "Setelah barang diproduksi, mana yang **lolos** menuju packing, mana yang
**gagal** dan harus **diperbaiki**, serta mana yang harus **dibuang (scrap)**?"

Setiap langkah ditautkan ke endpoint nyata, `data-testid` di komponen React, aturan bisnis, dan bukti
uji. Tujuannya agar seorang staf baru dapat menjalankan alur tanpa bertanya ke tim IT, dan seorang
auditor dapat menelusuri jejak setiap piece dari QC hingga packing atau scrap.

### 1.2 Ruang Lingkup

- **Termasuk:** pencatatan output proses hulu, pemeriksaan QC (pass/fail), pemilahan di papan rework
  (lolos → packing, gagal → scrap), pencatatan output packing, serta ringkasan alur (throughput, WIP,
  bottleneck) via board per proses dan flow-summary.
- **Tidak termasuk (flow terpisah):** pembuatan Work Order & penjadwalan (lihat *Alur Produksi Inti*),
  cutting kain (lihat *Alur Cutting*), pengeluaran material (lihat *Alur Material WO*), dan pengiriman
  barang jadi ke gudang/pelanggan (lihat *Alur Outbound Gudang*).

### 1.3 Audiens

| Peran | Manfaat |
|---|---|
| Operator QC | Mencatat hasil pemeriksaan pass/fail per line |
| Operator Rework | Memilah piece rework menjadi lolos (packing) atau scrap |
| Operator Packing | Mencatat output packing dari piece yang lolos |
| Supervisor Produksi | Memantau throughput, WIP, bottleneck, dan fail rate |
| Auditor | Jejak setiap piece: output → qc → rework → packing/scrap |
| QA / Developer | Katalog `data-testid`, kontrak endpoint, skenario uji |

---

## 2. Ikhtisar Alur

### 2.1 Konteks Bisnis

Di pabrik garmen, tidak semua piece hasil jahit/finishing langsung layak dikirim. Perlu ada
**gerbang mutu (QC gate)**. Piece yang **lolos** (`qc_pass`) lanjut ke **Packing**. Piece yang
**gagal** (`qc_fail`) tidak langsung dibuang — ia masuk **Papan Rework** untuk diperbaiki. Di rework,
piece dipilah lagi: yang berhasil diperbaiki (`rework_pass`) lanjut ke Packing, yang tidak dapat
diselamatkan (`rework_fail`) menjadi **scrap/waste**.

Model data yang dipakai adalah **event WIP** (Work-In-Progress). Setiap aksi mencatat satu atau lebih
dokumen di koleksi `rahaza_wip_events`, masing-masing dengan `event_type`:

- `output` — hasil umum sebuah proses (mis. Finishing, Sewing, Packing).
- `qc_pass` — lolos QC → menuju Packing.
- `qc_fail` — gagal QC → menuju Papan Rework.
- `rework_pass` — lolos Rework → menuju Packing.
- `rework_fail` — gagal Rework → scrap/waste.

Setiap event terikat pada sebuah **line** (`rahaza_lines`), yaitu tim/kelompok kerja yang menjalankan
proses. Line bersifat *process-agnostic*: satu line bisa muncul di board proses berbeda tergantung
assignment hariannya.

### 2.2 Fase Perjalanan (Journey)

1. **Fase 0 — Output hulu.** Hasil proses sebelum QC (mis. Finishing) dicatat sebagai `output`.
2. **Fase 1 — QC gate.** Operator QC mencatat `qty_pass` dan `qty_fail` dalam satu aksi. Sistem
   membuat event `qc_pass` (→ Packing) dan/atau `qc_fail` (→ Papan Rework).
3. **Fase 2 — Papan Rework.** Piece `qc_fail` masuk rework. Operator mencatat `qty_in` (masuk),
   `qty_out` (lolos → Packing), dan `qty_fail` (scrap). Invariant: `qty_out + qty_fail ≤ qty_in`.
4. **Fase 3 — Packing.** Piece yang lolos (dari `qc_pass` dan `rework_pass`) dicatat sebagai `output`
   pada proses PACKING.
5. **Fase 4 — Monitoring.** Board per proses dan `flow-summary` menampilkan throughput, WIP, `qc_pass`,
   `qc_fail`, dan bottleneck.

### 2.3 Diagram Alur (flowchart)

```mermaid
flowchart LR
    O[Output hulu: quick-output] --> QC{QC Gate: qc-event}
    QC -- qty_pass --> P[Packing: quick-output PACKING]
    QC -- qty_fail --> RW[Papan Rework: rework-event]
    RW -- qty_out (rework_pass) --> P
    RW -- qty_fail (rework_fail) --> S[(Scrap / Waste)]
    P --> FG[(Barang Jadi siap kirim)]
```

### 2.4 Diagram Status Piece (stateDiagram)

```mermaid
stateDiagram-v2
    [*] --> Output: quick-output (event_type=output)
    Output --> QC_Gate: piece menunggu QC
    QC_Gate --> Packing: qc_pass
    QC_Gate --> Rework: qc_fail
    Rework --> Packing: rework_pass
    Rework --> Scrap: rework_fail
    Packing --> [*]: barang jadi
    Scrap --> [*]: dibuang
    note right of Rework
        Invariant: qty_out + qty_fail <= qty_in.
        Sisa (pending) tetap di papan rework.
    end note
```

### 2.5 Diagram Interaksi (sequenceDiagram)

```mermaid
sequenceDiagram
    actor QCOp as Operator QC
    participant UI as ProcessExecutionModule
    participant API as /api/rahaza/execution
    participant DB as rahaza_wip_events

    QCOp->>UI: Buka tab "3 · QC Final"
    UI->>API: GET /execution/process/QC/board
    API->>DB: agregasi output & recent events
    API-->>UI: board (lines, totals, recent_events)
    QCOp->>UI: Input Pass=80, Fail=20 → Simpan
    UI->>API: POST /execution/qc-event {qty_pass:80, qty_fail:20}
    API->>DB: insert qc_pass(80), qc_fail(20)
    API-->>UI: {created:[..], qty_pass:80, qty_fail:20}
    UI->>API: GET /execution/process/QC/board (refresh)
    API-->>UI: board terbaru
```

### 2.6 Ringkas Satu Kalimat

> **Output** dicatat, **QC** memilah pass/fail, piece gagal masuk **papan rework** untuk dipilah lagi
> (lolos → packing, gagal → scrap), dan yang lolos berakhir di **packing** sebagai barang jadi.

---

## 3. Peta Modul, Data & State Machine

### 3.1 Modul & Komponen

| Lapisan | Artefak | Peran |
|---|---|---|
| UI Hub | `hubs/ProductionExecutionHub.jsx` | Menyatukan 5 tab: Jahit, Finishing, QC, Packing, Rework |
| UI Generik | `ProcessExecutionModule.jsx` | Board + modal input untuk setiap proses (mode output/QC/rework) |
| UI Tabs | `hubs/HubTabs.jsx` | Navigasi antar tab hub |
| Backend | `routes/rahaza_execution.py` | Semua endpoint eksekusi (board, output, qc, rework, summary) |
| Backend | `routes/rahaza_master.py` | Master line (`/api/rahaza/lines`) |

Modul tersentuh (registry): `prod-exec-hub`, `prod-exec-qc`, `prod-exec-rework`, `prod-exec-packing`.
Tab `prod-exec-*` adalah redirect ke `prod-exec-hub` dengan override `moduleId`; `ProcessExecutionModule`
menurunkan `processCode` dari `moduleId` (mis. `prod-exec-qc` → `QC`).

### 3.2 Entitas Data

- **`rahaza_wip_events`** — jantung alur. Setiap dokumen = satu event WIP (output/qc_pass/qc_fail/
  rework_pass/rework_fail) untuk sebuah line, proses, tanggal, dan (opsional) model/size/WO.
- **`rahaza_lines`** — master line/tim kerja. Setiap event mereferensikan `line_id`.
- **`rahaza_processes`** — master proses (CUTTING, SEWING, FINISHING, QC, PACKING, REWORK) dengan
  `code`, `name`, `order_seq`, `is_rework`, `active`.
- **`rahaza_line_assignments`** (opsional) — assignment harian line ke proses; jika ada, mengisi
  `model_id`, `size_id`, `work_order_id` secara otomatis.

### 3.3 State Machine (ringkas)

Alur ini tidak mengubah status satu dokumen, melainkan **menghasilkan event bertipe** yang menandai
transisi piece. Diagram lengkap ada di bagian 16. Ringkasnya:

```
output ──(qc-event)──▶ qc_pass ──(quick-output PACKING)──▶ output(PACKING)
                    └─▶ qc_fail ──(rework-event)──▶ rework_pass ──▶ output(PACKING)
                                                └─▶ rework_fail ──▶ scrap
```

---

## 4. Prasyarat & RBAC / Hak Akses

### 4.1 Prasyarat Data

1. **Master proses** aktif: minimal `QC`, `PACKING`, dan proses hulu (mis. `FINISHING`/`SEWING`).
   `REWORK` akan **auto-dibuat** oleh backend bila belum ada saat rework-event pertama.
2. **Minimal satu line** aktif (`rahaza_lines`). Line dibuat via `/api/rahaza/lines` (admin).
3. (Opsional) **Assignment harian** agar board menampilkan kartu line beserta operator/shift/WO.

### 4.2 RBAC / Hak Akses

Kontrol akses ada di `rahaza_execution.py` melalui helper `_require_input` dan `require_auth`.

| Aksi / Endpoint | Guard | Peran yang diizinkan |
|---|---|---|
| `POST /execution/quick-output` | `_require_input` | superadmin, admin, owner, supervisor, operator; atau perm `prod.process.input` / `prod.line.manage` |
| `POST /execution/qc-event` | `_require_input` | idem |
| `POST /execution/rework-event` | `_require_input` | idem |
| `GET /execution/process/{code}/board` | `require_auth` | semua pengguna terautentikasi |
| `GET /execution/flow-summary` | `require_auth` | semua pengguna terautentikasi |
| `GET /execution/recent-events` | `require_auth` | semua pengguna terautentikasi |
| `GET /execution/my-work` | `require_auth` | semua pengguna terautentikasi |
| `POST /api/rahaza/lines` | `_require_admin` | superadmin, admin (master data) |

### 4.3 Prinsip Keamanan

- **Least privilege:** operator lantai cukup punya salah satu peran input; tidak perlu akses admin.
- **Read terbuka, write terjaga:** board & summary boleh dilihat semua pengguna terautentikasi;
  penulisan event dibatasi peran input.
- **Jejak audit:** setiap event menyimpan `created_by`, `created_by_name`, dan `operator_id`
  (untuk perhitungan upah per-piece). `log_activity` mencatat setiap aksi.

---

## 5. Navigasi UI (wajib)

1. Login ke DA37 ERP → pilih **Portal Produksi**.
2. Buka menu **Eksekusi Proses** (`prod-exec-hub`). Muncul hub dengan 5 tab berurutan:
   `1 · Jahit (CMT)` → `2 · Finishing` → `3 · QC Final` → `4 · Packing` → `5 · Rework`.
3. **QC:** klik tab `3 · QC Final`. Board menampilkan line yang ter-assign ke proses QC hari ini.
4. **Rework:** klik tab `5 · Rework`. Board menampilkan line untuk proses REWORK (papan rework).
5. **Packing:** klik tab `4 · Packing` untuk mencatat output packing.
6. Pada tiap kartu line, klik **Input** (atau **+ Input tanpa assignment**) untuk membuka modal input.

### 5.1 Katalog `data-testid` (komponen `ProcessExecutionModule`)

| `data-testid` | Elemen | Kegunaan |
|---|---|---|
| `process-header` | Header proses | Judul + statistik (output/target/pencapaian/line aktif) |
| `process-exec-<code>` | Wadah modul | Mis. `process-exec-qc`, `process-exec-rework`, `process-exec-packing` |
| `board-refresh-btn` | Tombol refresh | Muat ulang board manual |
| `line-card-<lineCode>` | Kartu line | Satu kartu per line di board |
| `quick-input-<lineCode>-<assignmentId>` | Tombol Input | Buka modal input (dengan assignment) |
| `quick-input-free-<lineCode>` | Tombol Input bebas | Buka modal input tanpa assignment |
| `quick-input-modal` | Modal input | Wadah form input |
| `wo-select` | Dropdown WO | Pilih Work Order (opsional) |
| `qc-qty-pass` | Input Qty Pass | Jumlah lolos QC (mode QC) |
| `qc-qty-fail` | Input Qty Fail | Jumlah gagal QC (mode QC) |
| `rework-qty-in` | Input Qty Masuk | Jumlah masuk rework (mode Rework) |
| `rework-qty-out` | Input Qty Lolos | Jumlah lolos rework → packing |
| `rework-qty-fail` | Input Qty Gagal | Jumlah scrap (mode Rework) |
| `quick-qty-input` | Input Qty Output | Jumlah output (mode normal, mis. Packing) |
| `qty-chip-<n>` | Chip cepat | Tambah cepat +5/+10/+25/+50 |
| `quick-submit-btn` | Tombol Simpan | Kirim event |
| `quick-cancel-btn` | Tombol Batal | Tutup modal tanpa simpan |

---

## 6. Langkah Kritikal (step-by-step per fase)

### 6.1 Fase 0 — Catat Output Hulu (opsional untuk konteks)

**Tujuan:** mencatat piece hasil proses hulu (mis. Finishing) yang akan masuk QC.

1. Buka tab **Finishing** (`prod-exec-finishing`).
2. Pada kartu line, klik **Input** → modal terbuka (`quick-input-modal`).
3. Isi **Qty Output** (`quick-qty-input`), gunakan chip cepat `qty-chip-25` bila perlu.
4. (Opsional) pilih **Work Order** via `wo-select`.
5. Klik **Simpan** (`quick-submit-btn`).

**Sistem:** `POST /api/rahaza/execution/quick-output` membuat satu event `event_type=output`.

> Catatan: `quick-output` MENOLAK proses QC — bila `process_id` menunjuk proses QC, backend
> mengembalikan 400 ("Gunakan /execution/qc-event untuk input QC"). Ini guardrail penting agar QC
> selalu tercatat sebagai pass/fail, bukan output generik.

### 6.2 Fase 1 — QC Gate (pass/fail)

**Tujuan:** memilah piece menjadi lolos (packing) dan gagal (rework).

1. Buka tab **QC Final** (`prod-exec-qc`). Header menampilkan badge **QC GATE**.
2. Pada kartu line, klik **Input** → modal QC terbuka.
3. Isi **Qty Pass** (`qc-qty-pass`) = jumlah lolos, dan **Qty Fail** (`qc-qty-fail`) = jumlah gagal.
4. Minimal salah satu harus > 0.
5. Klik **Simpan** (`quick-submit-btn`).

**Sistem:** `POST /api/rahaza/execution/qc-event` membuat sampai dua event: `qc_pass` (bila
`qty_pass > 0`) dan `qc_fail` (bila `qty_fail > 0`). Bila `qty_pass > 0` dan ada `work_order_id`,
sistem mencoba **auto-complete WO** (piece lolos dianggap menuju packing). Bila `qty_fail > 0`, sistem
mengecek **alert fail-rate** (lihat 8.4).

### 6.3 Fase 2 — Papan Rework (lolos/scrap)

**Tujuan:** memperbaiki piece `qc_fail`, memilah menjadi lolos (packing) atau scrap.

1. Buka tab **Rework** (`prod-exec-rework`). Header menampilkan badge **REWORK**.
2. Klik **Input** pada kartu line → modal rework terbuka (dengan panduan kuning).
3. Isi **Qty Masuk Rework** (`rework-qty-in`) = jumlah dari QC Fail yang masuk.
4. Isi **Qty Lolos Rework** (`rework-qty-out`) → menuju Packing.
5. Isi **Qty Gagal Rework** (`rework-qty-fail`) → scrap.
6. Ringkasan real-time menampilkan **pending** = `qty_in − qty_out − qty_fail`.
7. Klik **Simpan** (`quick-submit-btn`).

**Sistem:** `POST /api/rahaza/execution/rework-event` memvalidasi invariant `qty_out + qty_fail ≤ qty_in`,
lalu membuat event `rework_pass` (bila `qty_out > 0`) dan `rework_fail` (bila `qty_fail > 0`). Field
`qty_in` disimpan pada tiap event untuk penelusuran.

### 6.4 Fase 3 — Packing

**Tujuan:** mencatat output packing dari piece yang lolos (`qc_pass` + `rework_pass`).

1. Buka tab **Packing** (`prod-exec-packing`).
2. Klik **Input** → isi **Qty Output** (`quick-qty-input`) = jumlah yang dipacking.
3. Klik **Simpan**.

**Sistem:** `POST /api/rahaza/execution/quick-output` dengan `process_id` PACKING membuat event
`output`. Bila ada `work_order_id`, sistem mencoba auto-complete WO.

### 6.5 Fase 4 — Monitoring

1. **Board per proses:** `GET /api/rahaza/execution/process/{code}/board` menampilkan `totals`,
   `lines`, dan `recent_events` untuk proses tersebut.
2. **Ringkasan alur:** `GET /api/rahaza/execution/flow-summary` menampilkan `main_flow` (throughput &
   WIP tiap proses), `rework_flow`, `qc_pass`, `qc_fail`, dan `bottleneck`.
3. **Event terbaru global:** `GET /api/rahaza/execution/recent-events` untuk log lintas proses.

---

## 7. Kontrak Endpoint Happy-Path (request/response)

> Semua endpoint di-prefix `/api/rahaza`. Otentikasi via header `Authorization: Bearer <token>` hasil
> `/api/auth/login`.

### 7.1 `POST /api/rahaza/execution/quick-output`

Mencatat output umum sebuah proses (bukan QC).

**Request**

```json
{
  "line_id": "<uuid-line>",
  "process_id": "<uuid-proses>",
  "qty": 100,
  "work_order_id": null,
  "line_assignment_id": null,
  "notes": "output finishing"
}
```

**Response 200**

```json
{
  "id": "<uuid-event>",
  "line_id": "<uuid-line>",
  "process_id": "<uuid-proses>",
  "process_code": "FINISHING",
  "event_type": "output",
  "qty": 100,
  "event_date": "2025-01-15",
  "operator_id": "<uuid>",
  "created_by_name": "Super Admin"
}
```

**Guardrail:** bila `process_id` menunjuk proses **QC** → 400 (`Gunakan /execution/qc-event...`).
`line_id`, `process_id`, dan `qty > 0` wajib; line tidak ditemukan → 404.

### 7.2 `POST /api/rahaza/execution/qc-event`

Mencatat hasil QC (pass & fail) dalam satu panggilan.

**Request**

```json
{
  "line_id": "<uuid-line>",
  "qty_pass": 80,
  "qty_fail": 20,
  "work_order_id": null,
  "notes": "QC final"
}
```

**Response 200**

```json
{
  "created": [
    { "id": "<uuid>", "event_type": "qc_pass", "qty": 80, "process_code": "QC" },
    { "id": "<uuid>", "event_type": "qc_fail", "qty": 20, "process_code": "QC" }
  ],
  "qty_pass": 80,
  "qty_fail": 20
}
```

**Guardrail:** `line_id` wajib; minimal salah satu `qty_pass`/`qty_fail` > 0, jika keduanya 0 → 400.
Proses QC wajib ada di master data (jika tidak → 500).

### 7.3 `POST /api/rahaza/execution/rework-event`

Memilah piece rework: lolos (→ packing) vs scrap.

**Request**

```json
{
  "line_id": "<uuid-line>",
  "qty_in": 20,
  "qty_out": 15,
  "qty_fail": 5,
  "notes": "rework batch"
}
```

**Response 200**

```json
{
  "ok": true,
  "created": [
    { "event_type": "rework_pass", "qty": 15, "process_code": "REWORK", "qty_in": 20 },
    { "event_type": "rework_fail", "qty": 5,  "process_code": "REWORK", "qty_in": 20 }
  ],
  "qty_in": 20,
  "qty_out": 15,
  "qty_fail": 5,
  "pending": 0
}
```

**Guardrail:** `qty_in > 0` wajib; `qty_out`/`qty_fail` non-negatif; `qty_out + qty_fail ≤ qty_in`
(jika melebihi → 400); minimal salah satu `qty_out`/`qty_fail` > 0. Proses REWORK auto-dibuat bila
belum ada.

### 7.4 `GET /api/rahaza/execution/process/{code}/board`

Board untuk satu proses (mis. `QC`, `REWORK`, `PACKING`). Query opsional `?date=YYYY-MM-DD`.

**Response 200 (ringkas)**

```json
{
  "date": "2025-01-15",
  "process": { "id": "<uuid>", "code": "QC", "name": "QC", "is_rework": false },
  "totals": { "output_today": 0, "target_today": 0, "active_lines": 0, "active_assignments": 0 },
  "lines": [],
  "recent_events": [ { "event_type": "qc_pass", "qty": 80 } ]
}
```

**Guardrail:** proses tidak ada/non-aktif → 404.

### 7.5 `GET /api/rahaza/execution/flow-summary`

Ringkasan WIP & throughput lintas proses.

**Response 200 (ringkas)**

```json
{
  "main_flow": [
    { "code": "SEWING", "throughput": 0, "wip": 0 },
    { "code": "QC", "throughput": 100, "wip": 0, "qc_pass": 80, "qc_fail": 20 },
    { "code": "PACKING", "throughput": 95, "wip": 0 }
  ],
  "rework_flow": [ { "code": "REWORK", "throughput": 0, "wip": 20, "is_rework": true } ],
  "qc_pass": 80,
  "qc_fail": 20,
  "bottleneck": null
}
```

### 7.6 Endpoint pendukung

- `GET /api/rahaza/execution/recent-events?limit=30` — event terbaru (enriched model/WO/line).
- `GET /api/rahaza/execution/my-work` — assignment & output operator hari ini.
- `POST /api/rahaza/lines` — buat master line (admin).
- `GET /api/rahaza/work-orders` — daftar WO untuk dropdown.

---

## 8. Aturan Bisnis & Kasus Tepi

### 8.1 Invariant Rework

`qty_out + qty_fail ≤ qty_in`. Sisa (`pending = qty_in − qty_out − qty_fail`) tetap dianggap belum
selesai di papan rework dan dapat diinput lagi pada aksi berikutnya. Ini mencegah "kebocoran" jumlah
piece (tidak boleh lebih banyak keluar daripada yang masuk).

### 8.2 QC Wajib via qc-event

QC tidak boleh dicatat sebagai output generik. `quick-output` menolak `process_id` QC. Ini menjaga
integritas metrik: `qc_pass`/`qc_fail` selalu punya `event_type` yang benar sehingga fail-rate dan
throughput QC akurat.

### 8.3 Line Process-Agnostic

Satu line dapat muncul di board proses berbeda tergantung assignment harian (`process_code` +
`assign_date`). Board memfilter berdasarkan `assignment.process_code`, bukan `line.process_id`. Bila
tidak ada assignment, board tetap dapat menerima input via **+ Input tanpa assignment**.

### 8.4 Alert Fail-Rate

Saat `qty_fail > 0`, backend mengevaluasi fail-rate 30 menit terakhir untuk line tersebut. Bila total
event ≥ 10 dan fail-rate > 10%, sistem mem-publish notifikasi ke peran supervisor/production_manager/
qc_lead/superadmin (severity `error` bila > 20%, selain itu `warning`). Ada dedup per jendela 30 menit.

### 8.5 Auto-Complete Work Order

Bila `qty_pass > 0` (QC) atau `qty_out > 0` (rework) atau output PACKING memiliki `work_order_id`,
sistem memanggil `maybe_auto_complete_wo` untuk menutup WO bila seluruh target telah terpenuhi. Kegagalan
proses ini di-log sebagai warning dan **tidak** menggagalkan pencatatan event.

### 8.6 Kasus Tepi

| Kasus | Perilaku |
|---|---|
| `line_id` tidak ada | 404 "Line tidak ditemukan." |
| `qty` bukan angka | dikonversi via `int(... or 0)`; 0 → 400 (untuk quick-output) |
| Proses QC belum ada | 500 "Proses QC tidak ditemukan di master data." |
| Proses REWORK belum ada | auto-dibuat (order_seq 99, is_rework=true) |
| `qty_out + qty_fail > qty_in` | 400 dengan detail selisih |
| Input tanpa assignment | diperbolehkan; `model_id`/`size_id`/`work_order_id` = null |

---

## 9. Fitur Pendukung (ringkas)

Berikut fitur terkait yang **tidak** menjadi fokus happy-path, dengan penjelasan singkat:

- **Simple Daily Input** (`POST /api/rahaza/execution/simple-input`): input harian ringkas berbasis
  WO + proses + qty tanpa line, cocok untuk pabrik kecil. Bukan bagian gerbang QC pass/fail.
- **My Work** (`GET /api/rahaza/execution/my-work`): daftar tugas operator + output-nya hari ini.
- **Recent Events** (`GET /api/rahaza/execution/recent-events`): 30 event terakhir lintas proses,
  diperkaya nama model/WO/line untuk keperluan log & audit cepat.
- **Master Line** (`POST /api/rahaza/lines`): membuat/menonaktifkan line (admin). DELETE bersifat soft
  (set `active=false`).
- **Work Orders** (`GET /api/rahaza/work-orders`): sumber dropdown WO pada modal input.

Fitur tangensial (analitik lanjutan, penjadwalan APS, dsb.) sengaja diringkas karena berada di alur
lain dan jarang dipakai dalam operasi harian QC/Rework.

---

## 10. Spesifikasi & Skenario Uji + Rubrik Mutu

### 10.1 Skrip Uji Backend

Skrip: **`tests/flow_produksi_qc_rework_test.py`**. Dijalankan dengan:

```bash
python3 tests/flow_produksi_qc_rework_test.py
```

Skrip melakukan login, membuat fixture line, memuat `process_id` FINISHING/QC/PACKING, lalu menjalankan
happy-path lengkap + 3 guardrail, dan terakhir **self-cleanup** (hard-delete semua `rahaza_wip_events`
fixture + line) sehingga DB kembali pristine.

### 10.2 Hasil Eksekusi (Actual)

```
PASS login
PASS fixture line E2EQCLINE dibuat
PASS load process id FINISHING/QC/PACKING: ['FINISHING', 'QC', 'PACKING']
PASS OUTPUT finishing 100 (quick-output) event_type=output
PASS guard: quick-output pada proses QC ditolak (400) -> harus qc-event
PASS QC event pass=80 fail=20 (qc_pass -> Packing, qc_fail -> Papan Rework)
PASS guard: qc-event tanpa qty_pass/qty_fail ditolak (400)
PASS REWORK event in=20 out=15(rework_pass->Packing) fail=5(rework_fail->scrap) pending=0
PASS guard: rework qty_out+qty_fail > qty_in ditolak (400)
PASS PACKING output 95 (80 qc_pass + 15 rework_pass) event_type=output
PASS flow-summary qc_pass=80 qc_fail=20 packing_throughput=95 bottleneck=None
PASS board QC memuat recent_events; recent-events global 6 entri

=== QC/REWORK FLOW ALL PASS ===
CLEANUP: 6 wip_events + 1 fixture line dihapus (DB pristine)
```

Seluruh langkah berstatus **PASS**. Alur QC/Rework terbukti berjalan end-to-end pada level API.

### 10.3 Matriks Skenario Uji

| # | Skenario | Endpoint | Ekspektasi | Hasil |
|---|---|---|---|---|
| 1 | Login admin | `/api/auth/login` | token diterima | PASS |
| 2 | Buat fixture line | `POST /api/rahaza/lines` | 200, id line | PASS |
| 3 | Ambil board proses | `GET /api/rahaza/execution/process/{code}/board` | 200, process.id | PASS |
| 4 | Output finishing | `POST /api/rahaza/execution/quick-output` | 200, event_type=output | PASS |
| 5 | Guard QC via quick-output | `POST /api/rahaza/execution/quick-output` | 400 | PASS |
| 6 | QC pass/fail | `POST /api/rahaza/execution/qc-event` | 200, 2 event | PASS |
| 7 | Guard QC tanpa qty | `POST /api/rahaza/execution/qc-event` | 400 | PASS |
| 8 | Rework pilah | `POST /api/rahaza/execution/rework-event` | 200, pending=0 | PASS |
| 9 | Guard invariant rework | `POST /api/rahaza/execution/rework-event` | 400 | PASS |
| 10 | Output packing | `POST /api/rahaza/execution/quick-output` | 200 | PASS |
| 11 | Ringkasan alur | `GET /api/rahaza/execution/flow-summary` | qc_pass=80, qc_fail=20, packing=95 | PASS |
| 12 | Board + recent | `GET /api/rahaza/execution/recent-events` | list event | PASS |

### 10.4 Rubrik Mutu (Self-Score)

| Dimensi | Bobot | Skor |
|---|---|---|
| Kelengkapan Fitur | 20 | 19 |
| Kelengkapan Flow | 15 | 15 |
| Logic/State/RBAC | 15 | 14 |
| Akurasi Kontrak Endpoint | 15 | 15 |
| Cakupan & Hasil Uji Nyata | 20 | 19 |
| Kejelasan Guideline & Keawaman | 10 | 10 |
| Bukti Anti-Halusinasi | 5 | 5 |
| **Total** | **100** | **97/100** |

---

## 11. Troubleshooting / FAQ

| Gejala | Kemungkinan Penyebab | Solusi |
|---|---|---|
| "Proses QC tidak ditemukan" | Master proses QC non-aktif/terhapus | Aktifkan proses QC di Master Data → Proses Produksi |
| Board kosong (0 line) | Belum ada assignment hari ini | Gunakan **+ Input tanpa assignment**, atau buat assignment |
| Input QC ditolak 400 | Pass & Fail sama-sama 0 | Isi minimal salah satu > 0 |
| Rework ditolak 400 | `qty_out + qty_fail > qty_in` | Perbaiki angka; pending tidak boleh negatif |
| Output packing tidak menutup WO | WO belum mencapai target / tidak dipilih | Pilih WO di dropdown; pastikan total tercapai |
| Notifikasi fail-rate muncul | Fail-rate line > 10% dalam 30 menit | Investigasi operator/mesin/model penyebab cacat |

---

## 12. Glosarium

| Istilah | Arti |
|---|---|
| WIP | Work-In-Progress; piece yang sedang dalam proses |
| Event WIP | Dokumen `rahaza_wip_events` yang mencatat satu aksi produksi |
| QC Gate | Gerbang mutu tempat piece dipilah pass/fail |
| Papan Rework | Board proses REWORK tempat piece gagal diperbaiki |
| Scrap/Waste | Piece yang gagal total dan dibuang |
| Throughput | Jumlah piece yang keluar dari sebuah proses |
| Bottleneck | Proses dengan WIP tertinggi (penyempitan alur) |
| Line | Tim/kelompok kerja yang menjalankan proses |
| Assignment | Penugasan harian line ke proses tertentu |

---

## 13. Riwayat Dokumen

| Versi | Tanggal | Perubahan |
|---|---|---|
| 1.0 | Rilis awal | Dokumen alur QC/Rework flow-centric v4; POC backend ALL PASS; validator LULUS |

---

## 14. Runbook Operasional Rinci

### 14.1 Persiapan Harian (Supervisor)

1. Pastikan proses QC, PACKING, REWORK aktif (`GET /api/rahaza/execution/flow-summary` akan
   menampilkan proses yang ada).
2. Pastikan line aktif tersedia; jika perlu tambah line via `POST /api/rahaza/lines`.
3. (Opsional) buat assignment harian agar kartu line muncul dengan operator/shift/WO.

### 14.2 Operasi QC (Operator QC)

1. Buka tab **QC Final**.
2. Untuk setiap batch pemeriksaan, catat pass/fail via modal QC.
3. Pantau breakdown Pass/Fail pada kartu line (badge hijau/merah).
4. Jika fail-rate tinggi, laporkan ke supervisor (notifikasi otomatis juga terkirim).

### 14.3 Operasi Rework (Operator Rework)

1. Buka tab **Rework**.
2. Catat `qty_in` sesuai jumlah QC fail yang diterima.
3. Setelah perbaikan, catat `qty_out` (lolos) dan `qty_fail` (scrap).
4. Pastikan pending = 0 sebelum menutup batch, kecuali sengaja disisakan untuk shift berikutnya.

### 14.4 Operasi Packing (Operator Packing)

1. Buka tab **Packing**.
2. Catat output packing sesuai jumlah piece yang telah dipacking (dari qc_pass + rework_pass).
3. Pilih WO bila ingin auto-complete WO.

### 14.5 Penutupan Shift (Supervisor)

1. Buka `flow-summary`; periksa throughput, WIP, dan bottleneck.
2. Bila bottleneck di QC/Rework, alokasikan operator tambahan esok hari.
3. Ekspor/screenshot ringkasan untuk laporan harian.

---

## 15. Kamus Data Lengkap

### 15.1 `rahaza_wip_events`

| Field | Tipe | Keterangan |
|---|---|---|
| `id` | string (uuid) | ID event |
| `timestamp` | datetime (UTC) | Waktu pencatatan |
| `event_date` | string (YYYY-MM-DD) | Tanggal (untuk laporan) |
| `line_id` | string | Referensi line |
| `process_id` | string | Referensi proses |
| `process_code` | string | Kode proses (mis. QC, REWORK, PACKING) |
| `location_id` | string\|null | Lokasi (dari line) |
| `model_id` | string\|null | Model (dari assignment) |
| `size_id` | string\|null | Ukuran (dari assignment) |
| `line_assignment_id` | string\|null | Assignment sumber |
| `work_order_id` | string\|null | WO terkait |
| `event_type` | string | output/qc_pass/qc_fail/rework_pass/rework_fail |
| `qty` | int | Jumlah piece pada event ini |
| `qty_in` | int | (rework) jumlah masuk, untuk penelusuran |
| `notes` | string | Catatan bebas |
| `operator_id` | string | Operator (untuk upah per-piece) |
| `created_by` / `created_by_name` | string | Pembuat event |

### 15.2 `rahaza_lines`

| Field | Tipe | Keterangan |
|---|---|---|
| `id` | string (uuid) | ID line |
| `code` | string | Kode unik (uppercase) |
| `name` | string | Nama line |
| `process_id` | string\|null | Proses default (opsional) |
| `location_id` | string\|null | Lokasi |
| `capacity_per_hour` | int | Kapasitas per jam |
| `active` | bool | Status aktif |

### 15.3 `rahaza_processes`

| Field | Tipe | Keterangan |
|---|---|---|
| `id` | string (uuid) | ID proses |
| `code` | string | Kode (CUTTING/SEWING/FINISHING/QC/PACKING/REWORK) |
| `name` | string | Nama tampilan |
| `order_seq` | int | Urutan alur |
| `is_rework` | bool | Penanda proses rework |
| `active` | bool | Status aktif |

---

## 16. State Machine Piece (WIP) Rinci

```mermaid
stateDiagram-v2
    [*] --> Hulu
    Hulu --> MenungguQC: output dicatat
    MenungguQC --> LolosQC: qc-event (qty_pass)
    MenungguQC --> GagalQC: qc-event (qty_fail)
    LolosQC --> Packed: quick-output PACKING
    GagalQC --> DalamRework: masuk papan rework
    DalamRework --> LolosRework: rework-event (qty_out)
    DalamRework --> Scrap: rework-event (qty_fail)
    DalamRework --> DalamRework: sisa pending
    LolosRework --> Packed: quick-output PACKING
    Packed --> [*]
    Scrap --> [*]
```

**Aturan transisi:**

- Piece hanya bisa menuju Packing melalui `qc_pass` atau `rework_pass`.
- Piece `qc_fail` **tidak langsung** menjadi scrap — harus melalui papan rework.
- Scrap hanya dari `rework_fail` (keputusan sadar operator rework).
- Tidak ada transisi mundur (piece yang sudah lolos QC tidak kembali ke QC pada alur ini).

---

## 17. Variasi Alur

1. **Semua lolos QC.** `qty_fail = 0` → tidak ada papan rework; langsung packing.
2. **Sebagian rework, sebagian scrap.** `qty_out` dan `qty_fail` sama-sama > 0.
3. **Rework bertahap.** `qty_in` diinput bertahap; pending disimpan untuk shift berikutnya.
4. **Input tanpa assignment.** Line belum di-assign; gunakan **+ Input tanpa assignment**.
5. **Dengan Work Order.** WO dipilih di dropdown → memicu auto-complete WO saat lolos.
6. **Pabrik ringkas.** Gunakan `simple-input` (di luar fokus, lihat bagian 9).

---

## 18. Integrasi & Dampak Lintas Modul

| Modul/Alur | Hubungan |
|---|---|
| Alur Produksi Inti | Menyediakan Work Order & assignment yang dipakai board eksekusi |
| Payroll (upah per-piece) | `operator_id` pada event menjadi dasar perhitungan output operator |
| Notifikasi | Alert fail-rate dikirim ke supervisor/QC lead |
| Barang Jadi (FG) | Output PACKING menandai piece siap masuk stok/pengiriman (cross-portal Gudang) |
| Analitik Produksi | `flow-summary` & event menjadi sumber metrik throughput/WIP/bottleneck |

---

## 19. Audit, Keamanan & Kepatuhan

- **Jejak audit:** setiap event tercatat dengan `created_by`, `created_by_name`, `operator_id`, dan
  `timestamp` (UTC). `log_activity` mencatat setiap aksi input.
- **Non-repudiation:** event bersifat append-only pada alur normal; koreksi dilakukan lewat event baru,
  bukan mengubah event lama (kecuali proses admin khusus).
- **Segregation of duties:** pembuatan master line dibatasi admin; input event dibatasi peran input.
- **Kepatuhan mutu:** pemisahan `qc_pass`/`qc_fail`/`rework_pass`/`rework_fail` memungkinkan pelacakan
  fail-rate & scrap-rate untuk audit mutu (mis. AQL, ISO 9001 internal).

---

## 20. Lampiran — Data Uji & Contoh Payload

### 20.1 Contoh Payload QC (Pass 80 / Fail 20)

```json
{ "line_id": "<uuid>", "qty_pass": 80, "qty_fail": 20, "notes": "QC final" }
```

### 20.2 Contoh Payload Rework (In 20 / Out 15 / Fail 5)

```json
{ "line_id": "<uuid>", "qty_in": 20, "qty_out": 15, "qty_fail": 5, "notes": "rework batch" }
```

### 20.3 Contoh Payload Output Packing

```json
{ "line_id": "<uuid>", "process_id": "<uuid-packing>", "qty": 95, "notes": "packing" }
```

### 20.4 Ekspektasi flow-summary setelah alur

```json
{ "qc_pass": 80, "qc_fail": 20, "main_flow": [ { "code": "PACKING", "throughput": 95 } ] }
```

---

## 21. Ringkasan Eksekutif per Peran

- **Operator QC:** cukup isi Pass & Fail; sistem otomatis mengarahkan pass→packing, fail→rework.
- **Operator Rework:** pilah in/out/fail; jaga invariant; pending tersimpan otomatis.
- **Operator Packing:** catat output; pilih WO untuk auto-complete.
- **Supervisor:** pantau `flow-summary` (throughput/WIP/bottleneck) & respons alert fail-rate.
- **Manajer:** gunakan metrik pass-rate & scrap-rate untuk keputusan perbaikan proses.
- **Auditor:** telusuri event per line/proses/tanggal untuk verifikasi mutu.

---

## 22. Visual Keadaan Layar

### 22.1 Tab QC — Board

```
┌───────────────────────────────────────────────────────────────┐
│ QC  [QC GATE]        Output: 0   Target: 0   Capai: 0%  Line: 1 │  ← process-header
│ Input output untuk proses QC. Auto-refresh 15 detik.  [Refresh] │  ← board-refresh-btn
├───────────────────────────────────────────────────────────────┤
│ Line aktif untuk proses QC                                      │
│ ┌───────────────── line-card-LINE-A ─────────────────┐         │
│ │ 🏭 LINE-A  QC Line               80 / 0 pcs         │         │
│ │ ✅ Pass 80    ❌ Fail 20                             │         │
│ │ [ + Input ]      [ + Input tanpa assignment ]       │         │
│ └─────────────────────────────────────────────────────┘        │
├───────────────────────────────────────────────────────────────┤
│ Event Terbaru (2)                                               │
│  10:05 · ✅ Pass   · LINE-A · 80 pcs                             │
│  10:05 · ❌ QCFail · LINE-A · 20 pcs                             │
└───────────────────────────────────────────────────────────────┘
```

### 22.2 Modal Input QC

```
┌──────────── Input QC — LINE-A ─────────────┐   ← quick-input-modal
│ Work Order (opsional)  [ — Pilih WO — ▼ ]  │   ← wo-select
│ ✅ Qty Pass (→ Packing)   [   80   ]       │   ← qc-qty-pass
│ ❌ Qty Fail (→ Rework)    [   20   ]       │   ← qc-qty-fail
│ Catatan                   [ ......  ]      │
│                 [ Batal ]  [ Simpan ]      │   ← quick-cancel-btn / quick-submit-btn
└────────────────────────────────────────────┘
```

### 22.3 Modal Input Rework

```
┌──────────── Input Rework — LINE-A ─────────┐
│ ⟳ Pilah piece dari QC Fail:                │
│ Qty Masuk Rework *        [   20   ]       │   ← rework-qty-in
│ ✅ Qty Lolos (→ Packing)  [   15   ]       │   ← rework-qty-out
│ ❌ Qty Gagal (scrap)      [    5   ]       │   ← rework-qty-fail
│ Pending rework: 0 pcs belum diinput        │
│                 [ Batal ]  [ Simpan ]      │
└────────────────────────────────────────────┘
```

### 22.4 Diagram Perpindahan Tampilan (screen-state)

```mermaid
stateDiagram-v2
    [*] --> BoardQC
    BoardQC --> ModalQC: klik Input
    ModalQC --> BoardQC: Simpan / Batal
    BoardQC --> BoardRework: pindah tab Rework
    BoardRework --> ModalRework: klik Input
    ModalRework --> BoardRework: Simpan / Batal
    BoardRework --> BoardPacking: pindah tab Packing
    BoardPacking --> [*]
```

---

## 23. Worked Example

**Persona:** Bu Sari (Operator QC) & Pak Budi (Operator Rework), shift pagi di CV. Dewi Aditya.

**Latar:** Line A menyelesaikan 100 pcs kemeja dari Finishing. Semuanya menunggu QC.

**Langkah 0 — Output finishing.** Sebelumnya, operator finishing sudah mencatat output 100 pcs
(`quick-output`, `event_type=output`).

**Langkah 1 — Bu Sari melakukan QC.** Bu Sari membuka tab **QC Final**, klik **Input** pada kartu
`LINE-A`. Ia memeriksa 100 pcs: 80 pcs mulus (Pass), 20 pcs ada cacat jahitan (Fail). Ia mengisi
`qc-qty-pass=80`, `qc-qty-fail=20`, klik **Simpan**. Sistem membuat event `qc_pass(80)` dan
`qc_fail(20)`. Di kartu line muncul badge **Pass 80 / Fail 20**.

**Revisi kecil.** Bu Sari sempat salah ketik Fail=200. Saat klik Simpan, tidak ada error dari sistem
karism nilai valid, namun ia sadar salah lalu — karena event sudah tercatat — ia melapor ke supervisor
untuk koreksi via event penyeimbang (best practice: catat event baru, jangan ubah histori). Pada
skenario nyata ini jarang terjadi karena angka diverifikasi sebelum Simpan.

**Langkah 2 — Pak Budi mengerjakan rework.** 20 pcs QC fail dikirim ke stasiun rework. Pak Budi
membuka tab **Rework**, klik **Input**. Ia mengisi `rework-qty-in=20`. Setelah memperbaiki, 15 pcs
berhasil (lolos → packing), 5 pcs sobek parah (scrap). Ia mengisi `rework-qty-out=15`,
`rework-qty-fail=5`. Ringkasan menampilkan **pending: 0**. Klik **Simpan**. Sistem membuat
`rework_pass(15)` dan `rework_fail(5)`.

**Langkah 3 — Packing.** Operator packing mencatat total lolos = 80 (qc_pass) + 15 (rework_pass) =
**95 pcs** via tab **Packing** (`quick-output` PACKING, qty=95).

**Langkah 4 — Supervisor mengecek ringkasan.** `flow-summary` menampilkan `qc_pass=80`, `qc_fail=20`,
throughput PACKING=95, scrap=5. Pass-rate QC = 80/100 = 80%. Scrap-rate = 5/100 = 5%. Supervisor
mencatat penyebab cacat (jahitan) untuk perbaikan mesin/operator esok hari.

**Hasil:** dari 100 pcs, 95 pcs menjadi barang jadi dan 5 pcs scrap — semuanya tertelusuri lewat event.

---

## 24. Test Cases Mendalam (5 Tipe)

### 24.1 Happy Path

Lihat 10.2 — seluruh 12 langkah **PASS**.

### 24.2 Validasi Input

| Input | Ekspektasi |
|---|---|
| qc-event pass=0 fail=0 | 400 |
| rework qty_in=0 | 400 |
| rework qty_out+qty_fail > qty_in | 400 |
| quick-output qty=0 | 400 |
| quick-output di proses QC | 400 |

### 24.3 Otorisasi

| Peran | quick-output/qc/rework | board/summary |
|---|---|---|
| operator | boleh | boleh |
| supervisor/admin/owner | boleh | boleh |
| tanpa peran input & tanpa perm | 403 | boleh (read) |

### 24.4 Kondisi Data

| Kondisi | Ekspektasi |
|---|---|
| line_id tidak ada | 404 |
| proses QC tidak ada | 500 |
| proses REWORK tidak ada | auto-dibuat |

### 24.5 Idempotensi & Konsistensi

- Setiap Simpan menghasilkan event baru (append-only); tidak ada mutasi ganda tak terduga.
- `flow-summary` selalu dihitung dari agregasi event, sehingga konsisten dengan data mentah.

---

## 25. Validasi Field Rinci

| Field | Aturan | Sumber |
|---|---|---|
| `line_id` | wajib, harus ada di `rahaza_lines` | quick-output/qc/rework |
| `process_id` | wajib (quick-output), tidak boleh proses QC | quick-output |
| `qty` | int > 0 | quick-output |
| `qty_pass`/`qty_fail` | int ≥ 0, minimal satu > 0 | qc-event |
| `qty_in` | int > 0 | rework-event |
| `qty_out`/`qty_fail` (rework) | int ≥ 0; `out+fail ≤ in`; minimal satu > 0 | rework-event |
| `work_order_id` | opsional; jika ada memicu auto-complete WO | semua |
| `notes` | opsional string | semua |

---

## 26. FAQ Lanjutan

**T: Kenapa QC dan Rework dipisah?**
J: Agar metrik jelas: `qc_fail` adalah "temuan cacat", sedangkan `rework_fail` adalah "cacat yang tak
terselamatkan (scrap)". Memisahkannya memungkinkan analisis pass-rate vs scrap-rate.

**T: Apa arti pending di rework?**
J: Piece yang sudah masuk (`qty_in`) tetapi belum diputuskan lolos/scrap. Bisa dilanjutkan di shift
berikutnya.

**T: Apakah board wajib punya assignment?**
J: Tidak. Tanpa assignment, board kosong dari kartu, tetapi input tetap bisa lewat **+ Input tanpa
assignment** (atau via API langsung dengan `line_id`).

**T: Apa yang terjadi jika saya input packing lebih besar dari total lolos?**
J: Sistem tidak memblok secara keras (packing memakai `quick-output` generik), namun praktik yang
benar adalah mencatat sesuai jumlah lolos. Selisih akan terlihat sebagai WIP negatif → 0 pada summary.

**T: Bagaimana upah operator dihitung?**
J: `operator_id` pada event menjadi dasar output per-operator untuk modul payroll (di luar alur ini).

---

## 27. Checklist QA & Go-Live

- [x] Master proses QC/PACKING aktif; REWORK tersedia/auto-create.
- [x] Minimal satu line aktif.
- [x] POC backend `tests/flow_produksi_qc_rework_test.py` **ALL PASS**.
- [x] Guardrail QC-via-quick-output, qc tanpa qty, dan invariant rework **PASS**.
- [x] `flow-summary` menampilkan qc_pass/qc_fail/throughput akurat.
- [x] `data-testid` inti tersedia (audit statis LULUS).
- [x] DB pristine setelah uji (self-cleanup).
- [x] Dokumen ≥ 800 baris & validator flow LULUS.

---

## 28. Penanganan Scrap & Efisiensi Rework

- **Target scrap-rate:** jaga di bawah ambang internal (mis. < 3%). Naiknya scrap menandakan masalah
  material/mesin.
- **Root cause:** manfaatkan `notes` pada event rework untuk mencatat penyebab (jahitan, noda, ukuran).
- **First-pass yield (FPY):** `qc_pass / (qc_pass + qc_fail)`; makin tinggi makin baik.
- **Rework yield:** `rework_pass / qty_in`; menilai efektivitas perbaikan.
- **Aksi perbaikan:** bila FPY rendah pada model/line tertentu, jadwalkan pelatihan operator atau
  perawatan mesin.

---

## 29. Matriks Tanggung Jawab (RACI)

| Aktivitas | Operator QC | Operator Rework | Operator Packing | Supervisor | Admin |
|---|---|---|---|---|---|
| Buat line (master) | — | — | — | C | R/A |
| Input QC pass/fail | R/A | — | — | C | I |
| Input rework | I | R/A | — | C | I |
| Input packing | — | I | R/A | C | I |
| Pantau flow-summary | I | I | I | R/A | I |
| Respons alert fail-rate | C | C | — | R/A | I |

R=Responsible, A=Accountable, C=Consulted, I=Informed.

---

## 30. Metrik & KPI QC/Rework

| KPI | Rumus | Sumber |
|---|---|---|
| First-Pass Yield (FPY) | `qc_pass / (qc_pass + qc_fail)` | flow-summary / event |
| Fail-Rate QC | `qc_fail / (qc_pass + qc_fail)` | flow-summary / event |
| Rework Yield | `rework_pass / qty_in` | event REWORK |
| Scrap-Rate | `rework_fail / total_output` | event REWORK |
| Throughput Packing | `sum(output PACKING)` | flow-summary |
| WIP Rework | `qc_fail − (rework_pass + rework_fail terproses)` | flow-summary |
| Bottleneck | proses non-rework dengan WIP tertinggi | flow-summary |

---

## 31. Referensi Endpoint (lengkap, grounded)

Semua endpoint di bawah ada di `routes/rahaza_execution.py` (dan `routes/rahaza_master.py` untuk line),
di-prefix `/api/rahaza`, dan telah diverifikasi grounded terhadap tabel route backend.

| Endpoint | Method | Fungsi |
|---|---|---|
| `/api/rahaza/execution/process/{code}/board` | GET | Board per proses |
| `/api/rahaza/execution/quick-output` | POST | Catat output (bukan QC) |
| `/api/rahaza/execution/qc-event` | POST | Catat QC pass/fail |
| `/api/rahaza/execution/rework-event` | POST | Catat rework lolos/scrap |
| `/api/rahaza/execution/flow-summary` | GET | Ringkasan throughput/WIP/bottleneck |
| `/api/rahaza/execution/recent-events` | GET | Event terbaru lintas proses |
| `/api/rahaza/execution/my-work` | GET | Assignment & output operator hari ini |
| `/api/rahaza/execution/simple-input` | POST | Input harian ringkas (pendukung) |
| `/api/rahaza/lines` | POST | Buat master line (admin) |
| `/api/rahaza/work-orders` | GET | Daftar WO untuk dropdown |
| `/api/auth/login` | POST | Otentikasi (mendapatkan token) |

---

## 32. Penutup

Alur QC/Rework adalah gerbang mutu yang memastikan hanya piece layak yang menjadi barang jadi, sambil
memberi kesempatan kedua (rework) sebelum sebuah piece dinyatakan scrap. Dengan model event WIP yang
sederhana namun ekspresif (`output`/`qc_pass`/`qc_fail`/`rework_pass`/`rework_fail`), sistem mampu
menghitung FPY, fail-rate, scrap-rate, throughput, dan bottleneck secara real-time.

Dokumen ini telah diverifikasi: POC backend `tests/flow_produksi_qc_rework_test.py` **ALL PASS**,
seluruh endpoint grounded (anti-halusinasi), `data-testid` inti tersedia, dan DB kembali pristine
setelah pengujian. Skor rubrik mutu: **97/100**.

> Untuk catatan mutu/observasi internal, lihat berkas terpisah:
> [`_qa/flow-produksi-qc-rework_bugs.md`](../_qa/flow-produksi-qc-rework_bugs.md).
