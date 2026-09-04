# QA / Catatan Bug — Alur Kolaborasi Internal (`flow-kolaborasi`)

> Materi training (`docs/user-guide/kolaborasi/flow-kolaborasi.md`) sengaja **bebas** tag bug.
> Seluruh temuan, observasi, dan tindak lanjut dicatat **di sini** (terpisah dari materi pelatihan).

Tanggal: 2026-07 · Status flow: **Done** (POC ALL PASS + audit testid LULUS + E2E UI PASS + validator 10/10).

---

## Ringkasan

Alur Kolaborasi Internal (Communication Hub + Announcement Board) **tidak menemukan bug
blocker**. Seluruh happy-path dan 7 guardrail lulus pada POC backend
(`tests/flow_kolaborasi_test.py`, exit 0, ALL PASS) dengan self-cleanup sehingga DB
kembali **pristine**. Dua catatan observasi bersifat non-blok didokumentasikan di bawah.

---

## KLB-OBS-001 — [LOW] Auditor `data-testid` A4 (WARN) karena parsing arrow-function

- **Alat:** `python3 scripts/docgen/audit_testids.py --file <CommunicationHubPortal + communication-hub/*.jsx + CollaborationPortal>`
  → **LULUS (0 FAIL)**; A1 (duplikat lintas-file) PASS, A2 (duplikat dalam-file) PASS,
  A3 (prop-forwarding) PASS. A4 (WARN) melaporkan 39 elemen "tanpa testid".
- **Analisis:** false-positive heuristik. Scanner mencari `>` terdekat setelah tag; pada
  handler `onClick={() => …}` karakter `>` dari `=>` dianggap penutup tag, sehingga atribut
  `data-testid` yang berada setelahnya tidak terbaca. Faktanya 33 `data-testid` statik unik
  tersedia (mis. `comm-channel-list`, `channel-message-input`, `send-message-btn`,
  `create-channel-btn`, `new-dm-btn`) dan elemen kritikal dapat diseleksi pada E2E.
- **Status:** WARN diterima (konsisten dengan CVN-OBS-002 pada flow-flow sebelumnya), tidak memblok.

---

## KLB-OBS-002 — [LOW] moduleId collaboration/collab-communication memakai inline `lazy()`

- **Konteks:** Di `frontend/src/components/erp/moduleRegistry.js`, entri
  `'collaboration'` dan `'collab-communication'` didaftarkan dengan inline
  `lazy(() => import('./CollaborationPortal'))` / `lazy(() => import('./CommunicationHubPortal'))`,
  bukan pola `const X = lazy(...)` seperti mayoritas modul lain.
- **Dampak:** `scripts/docgen/extract_module.py` (dipakai `audit_testids.py --module-id`)
  tidak dapat meresolusi file komponen otomatis (crawl gagal). Audit dijalankan via
  `--file` eksplisit terhadap portal utama + subkomponen `communication-hub/*` — hasilnya LULUS.
- **Rekomendasi (opsional, bukan blocker):** normalisasi ke pola `const CommunicationHubPortal = lazy(...)`
  agar toolchain audit dapat meng-crawl otomatis. Tidak diubah pada sesi ini untuk menjaga cakupan minimal.
- **Status:** by-design/observasi (LOW), tidak memblok E2E maupun runtime.

---

## Cleanup DB

Fixture uji (POC self-cleanup) dihapus dari koleksi: `comm_channels`, `comm_messages`,
`comm_conversations`, `comm_read_receipts`, `announcements`, dan user uji (`users`).
Pola yang dibersihkan: channel `E2E Kolaborasi Channel`, pengumuman `E2E Kolaborasi *`,
user `e2e.kolab.*@dewiaditya.id`, plus seluruh pesan/percakapan/receipt yang tertaut.
DB dikonfirmasi **pristine** (comm_channels=0, comm_messages=0, comm_conversations=0,
comm_read_receipts=0, announcements=0, users=1 [hanya superadmin]) setelah alur selesai.
