> 🚨 **MULAI DARI SINI (2026-07-31):** `memory/HANDOFF_SELISIH_CMT_BUYER.md` — penelusuran tuntas
> alur **selisih kirim CMT→DA** & **selisih terima DA→buyer** (Portal Produksi/Maklon/Vendor CMT):
> aturan bisnis owner, hasil uji empiris berangka, peta kode `file:line`, 7 gap (A–G) + rancangan
> perbaikan siap eksekusi, jebakan environment, dan skrip reproduksi. Bug terkait: BUG-6…BUG-9 di
> `memory/BUG_REGISTRY.md`.


# 📑 DOCS INDEX — SATU-SATUNYA PETA DOKUMEN (baca ini PERTAMA)

> **MENUNGGU KEPUTUSAN USER:** `/app/IA_RESTRUCTURE_PROPOSAL.md` (usulan perombakan menu warehouse dkk — BAGIAN 4).

> Dibuat 2026-07-02 (Session #20, pembersihan dokumen). Dokumen di luar daftar AKTIF = sudah diarsipkan agar tidak menyesatkan.

## ✅ DOKUMEN AKTIF (truth — gunakan ini)
| Dokumen | Fungsi |
|---|---|
| `/app/HANDOFF_NEXT_AGENT.md` | 🔴 **BACA PERTAMA SETIAP SESI** — status terkini + pelajaran wajib (uji ulang SEMUA angka dokumen; "merah" bisa berarti pencemaran data antar-skrip uji; rekonsiliasi otomatis jangan sentuh baris yang butuh keputusan manusia; perbaiki SEEDER-nya bukan datanya; frontend = static bundle) |
| `/app/docs/PLAN_FASE12.md` | **FASE 12 (2026-07-26)** — penyakit ke-8 `unmapped_location` (rekonsiliasi PETA LOKASI stok, backlog #3 TUNTAS) · BUG-A alias seeder · BUG-B/B2 fallback HPP salah · BUG-C linter engine mati · higiene alat uji (bootstrap seed baseline + auto-cleanup F6) |
| `/app/docs/PLAN_FASE11.md` | **FASE 11 (2026-07-25)** — BUG-R11-A ditutup tuntas (46 endpoint · sweep 7.184 req → 0 error 500) · BUG-4 `datetime`/`date` · BUG-5 kode akun aset · alias `yarn_*` dihentikan · 4 alat uji diperbaiki |
| `/app/AGENT_QUICKSTART.md` | ⚡ **SETUP CEPAT** — clone shallow + `bash /app/scripts/bootstrap.sh` (env+deps paralel+seed, idempoten ~10dtk). BACA PERTAMA saat setup mesin. |
| `/app/SSOT_MASTER_REPAIR_PLAN_PART5.md` | **RENCANA KERJA AKTIF** (final repair): RC-UI-01 theme 113 file · RC-UI-02 render 309 modul · RC-UI-03 paginasi 10 baris · RC-IA-01 audit IA/menu · RC-FLOW write-flow+RBAC. Ikuti PERSIS |
| `/app/FLOW_UX_AUDIT.md` | Audit UX 11 alur bisnis kritis (§9.2) — kartu RC-FLOW-UX + usulan (Session #24, #86) |
| `/app/docs/SESSION_MERGE_RECAP.md` | **Recap unifikasi merge 6 repo paralel (2026-07-08)** — apa yang di-merge, bug fix terbawa, cara verifikasi (13 POC + 13 validator + E2E it_88) |
| `/app/docs/user-guide/00_INDEX.md` | Registry dokumen flow-centric v4 — **28 flow Done** |
| `/app/plan.md` | Tracker status per sesi (**FASE 4 & FASE 5 diletakkan di BAWAH** — lihat penunjuk di baris 3 berkas itu) |
| **GATE — SATU PERINTAH VERIFIKASI** | `bash scripts/gate.sh` (**18 gate**, ~60 dtk) · `bash scripts/gate.sh --full` (**22**, + 4 alur produk HR). Receipt otomatis: `memory/GATE_RECEIPT.md` (**SKIP bukan PASS**). Gate rekap CMT = `scripts/verify_rekap_harian.py` (**INV-REKAP, 34 kode**; **RK-28 · RK-28b · RK-29 · RK-30** = fase 5 `closed_at`). SSOT penutupan job: `backend/core/production_job_lifecycle.py` (**satu-satunya** penulis `closed_at`); backfill job warisan: `backend/migrations/add_closed_at_to_production_jobs.py` |
| `/app/memory/AUDIT_MASTER_PRODUK_INTERNAL.md` | **INVENTARIS FIELD Master Produk Internal DA** (33 field `rahaza_models` + varian/size/warna/BOM) & pemetaannya ke **34 endpoint**; berisi 10 temuan TERBUKTI (kode produk bisa kembar, kategori basi, HPP 0 untuk produk manual, field mati). Alat: `scripts/audit_master_produk_internal.py` · bukti: `scripts/_prove_master_produk_logic_gaps.py` (9/9) · data: `memory/AUDIT_MASTER_PRODUK_FIELDS.json` |
| `/app/docs/PLAN_MASTER_PRODUK_KATEGORI_HARGA.md` | **RENCANA AKTIF (menunggu keputusan owner K-1…K-9)** — **BAGIAN 1–7:** master kategori produk (vest/rok/jacket) · kategori masuk SKU · HPP dasar & harga jual di master · bug kode kembar + gate `INV-PRODUK`. **BAGIAN 8:** hubungan **master ↔ katalog marketing** — 11 gap (stok punya 3 rumus, item baru lahir stok 0, overselling, nol sinkron otomatis, order tak tertaut master) + gate `INV-KATALOG` + fase F7–F9. Memuat daftar LENGKAP endpoint & berkas terpengaruh |
| **BUKTI (jalankan ulang kapan pun)** | `python3 scripts/audit_master_produk_internal.py` (inventaris field→endpoint) · `python3 scripts/_prove_master_produk_logic_gaps.py` (**9/9**, bersih-bersih sendiri) · `python3 scripts/_prove_catalog_master_gaps.py` (**10/10**, READ-ONLY) |
| `/app/test_result.md` | Protokol testing + data testing agent (JANGAN edit bagian protokol) |
| `/app/memory/CHANGELOG.md` | Riwayat perbaikan detail (Session #16–17 = eksekusi RC-01..RC-29 + backlog) |
| `/app/memory/FINAL_REPAIR_LOG.md` | Laporan per-modul PART 5 (append di sini) |
| `/app/memory/test_credentials.md` | Kredensial uji (admin + 6 role, termasuk `packing@` utk uji negatif scrap) + catatan rate limit & module id |
| **ALAT UJI BARU (FASE 11)** | `scripts/sweep_query_robustness.py` (sapu SEMUA GET × 8 varian query rusak, read-only) · `scripts/verify_fase11.py` (gate regresi 108 assertion) · `scripts/map_broken_endpoints.py` (petakan hasil sweep → file+baris) · `scripts/run_all_verifications.sh` (9 skrip regresi berurutan) · `backend_test_fase11.py` (45 uji, self-cleaning) |
| `/app/memory/GUIDELINE_DROP_LEGACY_COLLECTIONS.md` | **PANDUAN drop koleksi legacy** (FASE 8.8): prinsip keras, 4 grup kandidat + status kesiapan, prasyarat, checklist eksekusi, syarat hapus alias field `yarn_*`. Alat: `backend/migrations/drop_legacy_collections_guided.py` |
| `/app/memory/PRD.md`, `BUSINESS_PROCESS_PRODUKSI_MAKLON.md`, `SYSTEM_FLOW_DIAGRAM.md`, `ROADMAP.md` | Referensi produk/bisnis |
| `/app/memory/ENGINEERING_GUARDRAILS.md`, `/app/AGENT_DEVELOPMENT_RULES.md`, `/app/design_guidelines.md` | Aturan teknik & desain |

## 📦 ARSIP (`/app/docs/_archive_history/` — 28 file, JANGAN dipakai sebagai rencana kerja)
- `SSOT_MASTER_REPAIR_PLAN(.md, _PART2..4)` — **SUDAH DIEKSEKUSI SEMUA** (RC-01..RC-29, Session #16–17). Masih berguna HANYA sebagai referensi **SSOT Registry** (nama koleksi kanonik + peta field): Part 1 BAGIAN 1, Part 3 BAGIAN 1, Part 4 BAGIAN 1.
- `FORENSIC_00..12 + MASTER_REPORT`, `SSOT_FORENSIC_RAW.json` — audit historis (superseded).
- `HANDOFF_PART4_FORENSIC.md`, `CLEANUP_MASTER_PLAN.md`, `NEXT_AGENT_INSTRUCTIONS.md`, `API_MAPPING_PHASE_B.md`, `MATRIKS_PORTAL_PRODUKSI_VS_MAKLON.md` — selesai/kedaluwarsa.
- `backend_test*.py`, `FINANCE_*` — artefak uji lama.

## ⚡ STATUS SISTEM SINGKAT (per 2026-07-02)
- Aliran data/SSOT: RC-01..RC-29 + BACKLOG-A..E tuntas; sweep 930 GET = 0 crash; 15 menu → 5 hub; 4 router CMT legacy diarsip.
- Sisa pekerjaan = **hanya** yang ada di PART 5 (UI theme/paginasi, render review, IA restructure, flow+RBAC coverage).
- Semua data = seed (boleh reset): `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo` sebagai admin.

## Tambahan 2026-07-25 (FASE 7 — ACC-1/2/3)
| Dokumen / alat | Isi |
|---|---|
| `plan.md` §FASE 7 | Eksekusi ACC-1/2/3 + 8 bug bonus + bukti pengujian (BACA INI dulu untuk konteks terbaru) |
| `memory/CHANGELOG.md` (entri teratas) | Ringkas perubahan sesi + akar masalah tiap bug |
| `memory/PRODUKSI_E9_AKSESORIS.md` | Banner status: ACC-1/2/3 sudah dieksekusi (bukan lagi rencana) |
| `scripts/verify_acc123.py` | Verifikasi terisolasi ACC-1/2/3 (62 PASS/0 FAIL), self-clean |
| `scripts/seed_acc_ui_demo.py` | Seed data uji UI ACC-1/2/3 lewat ALUR NYATA (`--cleanup` untuk bersihkan) |
| `scripts/audit_deeplink_portals.py` | **BARU** — audit module id yang deep-link-nya dead-end "Pilih Portal" |
| `memory/PREVIEW_STABLE_MODE.md` | WAJIB dibaca: frontend = static bundle, rebuild setelah ubah `frontend/src` |
