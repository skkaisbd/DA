# [NAMA MODUL] (`<moduleId>`) — Portal [Portal]
<!-- moduleId: <moduleId> | Status: 🟡 CODE-READ / ✅ VERIFIED | Skor rubrik: <NN>/100 | Standar: v3 DEEP (SAP-grade) | Update: YYYY-MM-DD | Manifest: ../_manifests/<moduleId>.manifest.json | Catatan QA/bug (terpisah): ../_qa/<moduleId>_bugs.md | Divalidasi: scripts/docgen/validate_module.py -->

<!--
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │  CARA PAKAI TEMPLATE INI (WAJIB, standar v3)                                  │
  │  1) Jalankan extractor DULU:                                                  │
  │       python3 scripts/docgen/extract_module.py --module-id <moduleId>         │
  │     -> manifest = "permukaan modul yang pasti" (komponen/endpoint/testid).    │
  │  2) Isi SETIAP section di bawah dari manifest + baca kode (grounded).         │
  │  3) DILARANG menulis bug di sini. Semua bug -> ../_qa/<moduleId>_bugs.md.      │
  │  4) Jalankan validator sampai LULUS (exit 0):                                 │
  │       python3 scripts/docgen/validate_module.py --module-id <moduleId>        │
  │  5) Baru boleh set Status/skor & update 00_INDEX.md. Bersihkan data uji (DB). │
  │  Semua penanda <<...>> HARUS dihapus/diisi. Placeholder tersisa = validator FAIL.│
  └─────────────────────────────────────────────────────────────────────────────┘
-->

> **Dokumen Training & Spesifikasi Uji — gaya SAP Functional/End-User.** Berlapis:
> - **BAGIAN A — PANDUAN PENGGUNA** (bahasa sehari-hari, klik-per-klik) → staf operasional.
> - **BAGIAN B — LAMPIRAN TEKNIS** (komponen, field, kontrak API, logic/state, RBAC, integrasi, pesan) → admin/QA/dev.
> - **BAGIAN C — SPESIFIKASI UJI** (skenario + test case dengan hasil **nyata** + troubleshooting).
> - **BAGIAN D — LAMPIRAN CONTOH & DETAIL UJI**.
>
> **Prinsip anti-halusinasi:** tiap pernyataan menunjuk sumber kode (`file:baris`); `Expected`=menurut kode, `Actual`=hasil eksekusi. **Bug tidak ditampilkan di sini** (lihat `../_qa/<moduleId>_bugs.md`).

## 0. METADATA MODUL
| Atribut | Nilai |
|---|---|
| **moduleId** | `<moduleId>` |
| **Nama tampilan** | <<Nama>> |
| **Portal** | <<Portal>> |
| **Tipe** | standalone / tab-hub / hub |
| **Path menu** | <<Portal → Section → Menu>> (`portalNav.js:<baris>`) |
| **Komponen induk** | `<<file.jsx>>` |
| **Registry** | `moduleRegistry.js:<baris>` |
| **Jumlah endpoint disentuh** | **<N> path unik** (<M> method-endpoint) — terverifikasi via `extract_module.py` |
| **Koleksi MongoDB** | <<daftar koleksi>> |

---

# BAGIAN A — PANDUAN PENGGUNA
## A1. Untuk apa modul ini? (konteks bisnis) — analogi sederhana + posisi di rantai proses.
## A2. Siapa yang memakai & apa haknya (ringkas). (rinci di B7)
## A3. Prasyarat (setup sekali di awal) — data master/modul yang harus ada + path BENAR.
## A4. Istilah (glossary).
## A5. Status & artinya (badge/enum + bisa diedit/dihapus?).
## A6. Anatomi layar (bagian-bagian yang terlihat).
## A7. Alur kerja end-to-end (```mermaid flowchart``` + narasi).
## A8. Panduan Tugas (klik-per-klik) — TIAP tugas: Tujuan · Prasyarat · Langkah bernomor · Hasil · Bila gagal.
## A9. Visual Keadaan Layar (per langkah) — mockup ASCII tiap tahap + ```mermaid stateDiagram-v2``` perpindahan tampilan.
## A10. Cara cepat membaca dokumen (untuk pemula).

---

# BAGIAN B — LAMPIRAN TEKNIS
## B1. Peta Komponen (Component Map) — ```mermaid``` + tabel SEMUA file komponen dari manifest (induk + anak). Wajib 100% cakupan.
## B2. Inventaris Elemen (exhaustive) — SETIAP elemen interaktif + `data-testid` + aksi + syarat tampil/enabled. Wajib memuat SEMUA testid manifest.
## B3. Kamus Field — Form (field | testid | tipe | wajib | default | validasi | sumber/F4 | contoh).
## B4. Kamus Field — Kolom Tabel.
## B5. Katalog Kontrak Endpoint — <N> path unik (<M> method-endpoint). TIAP endpoint: Method/Path/Request/Response/status code/RBAC/koleksi/`route.py:baris`. Wajib 100% cakupan manifest, 0 halusinasi.
## B6. State & Logika — B6.1 State Machine (```mermaid stateDiagram-v2```) · B6.2 rumus/perhitungan · B6.3 Logika & Trigger per fitur.
## B7. Matriks RBAC (role × aksi) — terverifikasi.
## B8. Peta Integrasi (lintas-modul & lintas-koleksi) — ```mermaid```.
## B9. Kamus Data (koleksi MongoDB terkait).
## B10. Katalog Pesan (Backend HTTP + Frontend UI) dengan `file:baris`.

---

# BAGIAN C — SPESIFIKASI UJI
## C1. Test Scenarios (naratif) — menutup semua fitur.
## C2. Backend — `python3 tests/<skrip>.py` → **X/X PASS** (login sekali; data uji dibersihkan). Tabel: ID|Skenario|Tipe|Expected|Actual|Verdict. 5 tipe: Happy/Edge/Negative/Permission/State.
## C3. UI — `testing_agent_v3` (report iterasi) — SEMUA panel & SEMUA status.
## C4. Catatan QA (internal) — pointer ke `../_qa/<moduleId>_bugs.md`. (JANGAN tulis bug di sini.)
## C5. Troubleshooting (gejala → sebab → solusi).
## C6. Lampiran — Bukti & Skor (skrip, report, kredensial, kondisi DB) + tabel Rubrik self-score.

---

# BAGIAN D — LAMPIRAN CONTOH, PAYLOAD & DETAIL UJI
## D1. Contoh Payload API (Request → Response NYATA).
## D2. Detail Test Case (Input → Expected → Actual) — cases kunci + tabel sisanya.
## D3. Sequence Diagrams (```mermaid sequenceDiagram```).
## D4. Contoh Skenario Bisnis Lengkap (worked example) — naratif realistis + bahasa awam (persona, langkah, termasuk revisi/error).
## D5. FAQ.
## D6. Batasan, Asumsi & Backlog Enhancement.
## D7. Changelog Dokumen (versi dokumen — BUKAN changelog bug).

<!-- END OF MODULE DOC: <moduleId> -->
