# QA / Catatan Bug — Alur Marketing / KOL (`flow-marketing-kol`)

> Materi training (`docs/user-guide/marketing/flow-marketing-kol.md`) sengaja **bebas** tag bug.
> Seluruh observasi & tindak lanjut dicatat **di sini** (terpisah dari materi pelatihan).

Tanggal: 2026-07 · Status flow: **Done** (POC ALL PASS + audit testid LULUS + E2E UI PASS + validator 10/10).

---

## MKL-OBS-001 — [INFO] Modul Komplain tidak punya endpoint create manual

- **Komponen:** `backend/routes/marketing_complaints_routes.py` (prefix `/api/marketing/complaints`).
- **Karakteristik:** Tidak ada `POST ""` untuk membuat komplain dari UI. Komplain berasal dari
  **impor/webhook/seed** (`marketing_import`, `marketing_webhooks`, dan `seed_complaints_if_empty`).
  Endpoint yang tersedia: `GET` (list), `GET /{id}`, `PATCH /{id}/status`, `POST /{id}/notes`,
  `POST /{id}/ai-classify`, `GET /summary`.
- **Dampak pada uji:** POC (`tests/flow_marketing_kol_test.py`) menyisipkan **fixture komplain
  langsung** ke koleksi `marketing_complaints` (mem-mimik impor/seed), lalu menguji transisi status,
  catatan (`notes`), dan SLA via API. Fixture dihapus pada self-cleanup.
- **Status:** by-design (INFO, bukan cacat). Didokumentasikan agar penguji berikutnya tidak mencari
  tombol “Tambah Komplain” untuk create murni.

---

## MKL-OBS-002 — [LOW] Auditor `data-testid` A4 (WARN) — false-positive parsing arrow-function

- `scripts/docgen/audit_testids.py --module-id marketing-content-calendar marketing-product-launches
  marketing-reviews marketing-complaints` → **LULUS (0 FAIL)**; A1/A2/A3 PASS. A4 (WARN) melaporkan
  ~100 elemen interaktif "tanpa testid".
- **Analisis:** konsisten dengan flow-flow sebelumnya. Scanner mencari `>` terdekat setelah tag;
  pada handler `onClick={() => …}`, karakter `>` dari `=>` dianggap penutup tag sehingga
  `data-testid` yang berada setelahnya tidak terbaca. Elemen kritikal utama tetap memiliki testid.
- **Root testid dashboard yang tersedia:** `content-calendar-dashboard`, `product-launch-dashboard`,
  `rating-review-module`, `complaints-dashboard` (plus `btn-add-content`, `btn-add-launch`,
  `content-account-select`, `review-account-select`, `note-textarea`, `search-complaints`).
- **Status:** WARN diterima (tidak memblok). Terbukti dapat diseleksi pada E2E (testing_agent_v3
  iteration_85 PASS 100%).

---

## MKL-OBS-003 — [INFO] Auto-seed demo saat modul dibuka

- Modul Konten/Launch/Review/Komplain memanggil `seed_*_if_empty()` pada `GET summary`/`list` — bila
  koleksi kosong, sistem menyisipkan data demo (mis. 30 konten, 8 launch, 40 ulasan, 40 komplain).
- **Dampak:** membuka modul di UI dapat memunculkan data demo (bukan residu uji). POC hanya membuat
  dan menghapus **fixture bertag `E2E-KOL`** sehingga tidak mengganggu data demo/nyata.
- **Status:** by-design (INFO).

---

## Cleanup DB

Fixture uji (POC self-cleanup + pembersihan pasca E2E) dihapus dari koleksi:
`marketing_content_calendar`, `marketing_product_launches`, `rahaza_materials` (FG `E2E-KOL-CAMP`),
`marketing_reviews`, `marketing_complaints`. Pola yang dibersihkan: prefix `E2E-KOL`, `KOMP-E2E-KOL`,
kode FG `E2E-KOL-CAMP`, dan judul/produk berawalan `E2E`. DB dikonfirmasi **pristine** (0 residu)
setelah alur selesai.
