# QA / Catatan Bug — Alur CMT Vendor / Sub-contract (`flow-maklon-cmt-vendor`)

> Materi training (`docs/user-guide/maklon/flow-maklon-cmt-vendor.md`) sengaja **bebas** tag bug.
> Seluruh temuan & tindak lanjut dicatat **di sini** (terpisah dari materi pelatihan).

Tanggal: 2026-07 · Status flow: **Done** (POC ALL PASS + E2E UI PASS + validator 10/10).

---

## CVN-FIX-001 — [HIGH] Frontend dispatch memakai kontrak backend obsolete (HTTP 422)

- **Komponen:** `frontend/src/components/erp/WMSCMTDispatchesModule.jsx` (moduleId `wms-cmt-dispatches`).
- **Gejala:** Membuat CMT dispatch dari UI **selalu gagal**. Backend mengembalikan
  `HTTP 422 Unprocessable Entity` dengan pesan `cmt_name Field required`.
- **Akar masalah:** Modul lama dibangun untuk kontrak **single-material** yang sudah usang:
  - payload create memakai `cmt_partner_name`, `material_name`, `qty_sent`, `material_code`,
    `expected_return_date` — sedangkan backend `routes/wms_cmt_dispatches.py` (model saat ini)
    mewajibkan `cmt_name` + array `lines[]` (multi-baris: `material_code`, `material_name`, `qty`,
    `unit`, dst).
  - field tampilan lama (`dispatch_number`, `qty_sent`, `qty_returned`) & status lama (`pending`,
    `received`, `partial_return`, `completed`) tidak sesuai model baru (`dispatch_no`, `lines[]`,
    status `draft/dispatched/partially_returned/fully_returned/cancelled`).
- **Bukti:** `curl -X POST /api/wms/cmt-dispatches` dengan payload lama → `422`
  (`{"loc":["body","cmt_name"],"msg":"Field required"}`).
- **Perbaikan:** Rebuild total `WMSCMTDispatchesModule.jsx` menjadi **hub SSOT 2-seksi**:
  1. **Kirim ke Vendor (Dispatch)** selaras kontrak baru: create draft (`cmt_name` + `lines[]`),
     eksekusi (`/dispatch`, menampilkan `sj_number`), retur (`/return-line`), batal (`/cancel`),
     detail (`/{id}`), filter status baru.
  2. **Terima Hasil Jadi (Receipt + QC)** memanfaatkan endpoint `/api/prod/cmt-receipts...` yang
     kontraknya sudah benar (create → add line → set `qty_actual` → submit → approve/reject, posting
     FG). Logika sejalan dengan modul lama `CMTPackingModule.jsx` (yang tetap benar), kini disatukan
     ke hub SSOT sesuai keputusan konsolidasi O1.2 (`prod-cmt-packing` → redirect `wms-cmt-dispatches`).
- **Verifikasi:** `POST /api/wms/cmt-dispatches` (payload baru) → `200`. E2E UI: create dispatch →
  toast `Dispatch CMD/2026/07/0003 dibuat (draft)`; eksekusi → SJ terbit; receipt create → hitung
  QC=95 → submit → approve → toast `Disetujui — stok FG diposting`. testing_agent_v3 iteration_84:
  **backend 21/21, frontend 29/29, 0 bug**.
- **Severity:** HIGH (blokir E2E) → **RESOLVED**.

---

## CVN-OBS-001 — [LOW] Fitur bergantung model lama ikut dihapus saat rebuild

- **Panel "AI Smart Recommendations"** pada modul lama memakai input `cmt_partner_id` (konsep
  partner-id yang tidak lagi dihasilkan oleh model dispatch berbasis `cmt_name`). Panel ini
  **dihapus** dari hub baru agar tidak menyesatkan. Endpoint AI
  (`/api/wms/ai/cmt-dispatches/smart-recommendations`) tetap ada di backend bila ingin dipakai
  kembali dengan kontrak yang sesuai.
- **Dampak:** tidak memengaruhi alur inti (dispatch + receipt). Dicatat sebagai observasi.
- **Status:** by-design (LOW, tidak memblok).

---

## CVN-OBS-002 — [LOW] Auditor `data-testid` A4 (WARN) karena parsing arrow-function

- `scripts/docgen/audit_testids.py --module-id wms-cmt-dispatches` → **LULUS (0 FAIL)**; A1/A2/A3
  PASS. A4 (WARN) melaporkan 44 elemen "tanpa testid".
- **Analisis:** false-positive heuristik. Scanner mencari `>` terdekat setelah tag; pada handler
  `onClick={() => …}` karakter `>` dari `=>` dianggap penutup tag sehingga `data-testid` yang berada
  setelahnya tak terbaca. Faktanya seluruh elemen kritikal **memiliki** `data-testid` (78 testid
  statik unik) dan telah terbukti dapat diseleksi pada E2E (testing_agent_v3 29/29 PASS).
- **Status:** WARN diterima (konsisten dengan flow-flow sebelumnya), tidak memblok.

---

## Cleanup DB

Fixture uji (POC self-cleanup + pembersihan E2E UI/testing agent) dihapus dari koleksi:
`wh_cmt_dispatches`, `wh_delivery_notes`, `cmt_receipts`, `cmt_receipt_lines`,
`rahaza_material_stock`, `rahaza_fg_movements`. Pola yang dibersihkan mencakup `E2E CMT Vendor`,
`E2E UI CMT Vendor`, `E2ECMTSKU`, `E2EUISKU`. DB dikonfirmasi **pristine** setelah alur selesai.
