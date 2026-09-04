# 🤝 HANDOFF — Sesi Forensik SSOT PART 4 (SELESAI SEMUA — STEP E DITUNTASKAN SESSION #15)

> ✅ **UPDATE 2026-07-02 (Session #15): STEP E SELESAI — dokumen final ada di `/app/SSOT_MASTER_REPAIR_PLAN_PART4.md`.** 2 render tersisa + STOP-VERIFY RC-27 juga tuntas (lihat plan.md Session #15). Handoff di bawah dipertahankan sebagai arsip bukti.

> **Untuk agent berikutnya.** Sesi ini melanjutkan audit forensik menuju `SSOT_MASTER_REPAIR_PLAN_PART4.md`.
> **Status: SEMUA INVESTIGASI (B, C, D) SELESAI + BUKTI TERKUNCI. Dokumen PART4 BELUM DITULIS (STEP E).**
> **Konvensi tetap: BELUM ADA perubahan kode runtime. Semua read-only.** Hanya 2 script forensik baru ditambahkan di `/app/backend/migrations/`.
> Arahan user: role lain di-skip (superadmin saja); kerjakan b,c,d; untuk (e) dokumen JANGAN redundant dgn Part 1 & 2; **kualitas minimal = SSOT_MASTER_REPAIR_PLAN.md (Part 1), harus lebih sempurna.**

---

## 1. STATE ENVIRONMENT (setup ulang dari nol — environment sebelumnya ter-reset)

- Repo `https://github.com/gantenggantengserigalavsharimau/da` di-clone → rsync ke `/app` (exclude `.git`, `node_modules`, `.env`).
- `/app/backend/.env`: `MONGO_URL`, `DB_NAME=test_database`, `CORS_ORIGINS`, **`JWT_SECRET` + `EMERGENT_LLM_KEY` sudah ditambahkan** (lihat file). ⚠️ Pernah rusak karena append tanpa newline — sudah diperbaiki, formatnya sekarang benar per baris.
- Deps terinstall (pip `-r requirements.txt` + `emergentintegrations`; `yarn install`).
- **Seed dijalankan ulang persis prosedur Part 3:** `POST /api/seed/production-full` + `POST /api/rahaza/seed-demo` → baseline **identik Part 3** (24 live session, 45 creator session, 240 toko order, 25 WO, `dewi_rnd_samples=4` vs `sample_requests=0`, `rahaza_coa_accounts=0`).
- Backend + frontend **RUNNING**, health OK, login OK (`admin@garment.com` / `Admin@123`).
- Catatan operasional: rate-limit login 10/60 dtk; token disimpan `/tmp/admin_token.txt` (ephemeral — regenerate jika hilang/expired); openapi ada di `/api/openapi.json` (BUKAN `/openapi.json`); frontend compile ~2-3 menit; **deep-link modul BEKERJA**: login → buka `http://localhost:3000/#<module-id>` → reload.

## 2. ARTEFAK & SCRIPT (cara regenerate bukti)

| Artefak | Lokasi | Cara regenerate |
|---|---|---|
| Token admin | `/tmp/admin_token.txt` | login curl → simpan token |
| OpenAPI (1663 path) | `/tmp/openapi.json` | `curl localhost:8001/api/openapi.json -o /tmp/openapi.json` |
| **STEP D hasil test 954 GET** | `/tmp/d_results.json` + log ringkas | `cd /app/backend && python3 migrations/d_full_scope_forensics.py` (35 dtk) **[SCRIPT BARU, PERMANEN]** |
| **Klasifikasi phantom (47/216/15)** | `/tmp/d2_phantom_report.json` | `python3 migrations/d2_phantom_classifier.py` **[SCRIPT BARU, PERMANEN]** |
| Scanner full-codebase | `/tmp/scanner_full.log` | `python3 migrations/ssot_forensic_scanner.py` |
| B1 (param-GET 3 domain) | `/tmp/b1_results.json` | `python3 migrations/b1_test_detail_endpoints.py` |
| B2 (write-flow RnD) | stdout | `python3 migrations/b2_write_flow_test.py` (create→verify→cleanup, aman) |
| Screenshot render | `/tmp/shot_*.png` (ephemeral) | Playwright deep-link `#<module-id>` |
| Report testing agent | `/app/test_reports/iteration_30_forensic_audit.json` | — |

**Angka STEP D (954 GET diuji, 99.6% dari 958 GET op):** OK_DATA=465 · OK_EMPTY=237 · 500=5 · 502=1 · 503=1 · 404=116 · 401=24 · 409=16 · 403=7 · 422=22 · 400=10 · NO_ID=49 · TIMEOUT=1.

---

## 3. TEMUAN BARU TERVERIFIKASI (kandidat RC-19..RC-29 utk PART 4) — semua dengan bukti D1..D5

### 🔴 RC-19 — WMS Material Label PDF crash 500
- `GET /api/wms/materials/{id}/label-pdf` → 500. Akar: `routes/wms_material_labels.py:187` dan `:268` pakai `s['location']` (KeyError) — SSOT `rahaza_material_stock` fieldnya **`location_id`** (29/29 dok tanpa `location`).
- Fix rencana: `.get('location')` + resolve nama lokasi via `wh_positions` by `location_id`, fallback `'-'`.

### 🔴 RC-20 — FE crash modul `marketing-live-analytics` (TERVERIFIKASI RENDER)
- `LiveSessionAnalyticsDashboard.jsx:142` `<SelectItem value="">` → Radix melarang string kosong → **ErrorBoundary "Portal Error"** (screenshot dikonfirmasi, pesan error persis tampil di UI).
- Fix rencana: `value="all"` + sesuaikan logic filter platform.

### 🔴 RC-21 — **KRITIS FRESH-DEPLOY**: Auto-seed COA & Posting Profiles GAGAL total (cascade GL lumpuh)
- `server.py:194-196` import `seed_coa_accounts` dari `routes.rahaza_coa` — **fungsi itu TIDAK ADA** (yang ada: handler route `seed_template` :300 = `POST /api/rahaza/coa/seed`, `seed_da_coa` :545 = `POST /seed-da`; keduanya butuh `request: Request`, bukan callable `(db)`).
- Exception → **seluruh blok try gugur** → `rahaza_coa_accounts=0` **DAN** `rahaza_posting_profiles=0` (auto-seed posting profiles ikut dilewati, ini LEBIH DALAM dari catatan sesi lalu).
- **CASCADE**: `production_seed_full.py:1267` bangun `coa_map` dari COA kosong → seed JE dilewati → `rahaza_journal_entries=0`, `rahaza_journal_lines=0` → SEMUA laporan GL kosong; **RC-05/RC-10 Part 1-2 terblokir**. Bukti log: `Phase 7D auto-seed: cannot import name 'seed_coa_accounts'`.
- Terkait: `scripts/seed_expense_categories.py:120` menulis kategori/akun 6-3xxx ke **phantom `rahaza_coa`** (kanonik `rahaza_coa_accounts`) — script seed pun salah koleksi.
- Fix rencana: ekstrak logic seed jadi fungsi `seed_coa_accounts(db)` + `seed posting profiles` callable; atau panggil `POST /api/rahaza/coa/seed-da` di startup dgn cara benar; lalu re-seed + re-run production-full agar JE terisi.

### 🔴 RC-22 — `GET /api/rahaza/leave-balances` 500 (seed schema drift) + UI MENYESATKAN (TERVERIFIKASI RENDER)
- Akar: KeyError `'leave_type_id'` di `rahaza_leave_balances.py:119` (`lt_ids = list({d["leave_type_id"] ...})`).
- **DUA seeder menulis schema BEDA ke koleksi sama**: `production_seed_full.py:718` schema LAMA (`cuti_tahunan_total/used`, `cuti_sakit_*`, TANPA `leave_type_id` — 25/25 dok) vs `rahaza_hr_seed.py:418-422` schema BARU (`leave_type_id`/`allocated`/`used`). `rahaza_leave_types`=5 (ada).
- **FE `HRLeaveBalancesModule` (id `hr-leave-balances`) MENELAN 500 → tampil empty-state menyesatkan**: "Belum ada saldo cuti untuk tahun 2026 · 0 karyawan · Klik Alokasi Tahunan" (screenshot). Bahaya: user klik "Alokasi Tahunan" → data campur 2 schema.
- Fix rencana: selaraskan seed production_full ke schema baru (atau hapus blok :718) + guard `.get()` di reader + FE tampilkan error nyata.

### 🟠 RC-23 — `GET /api/hr/expenses/outstanding-advances/export` 500 (naive vs aware datetime) + FALSE-SUCCESS TOAST (TERVERIFIKASI RENDER)
- Akar: `employee_travel_settlements.py:368` handler export; `advance_paid_at` di DB = **string date-only "2026-05-06"** → `fromisoformat` → datetime NAIVE → `datetime.now(timezone.utc) - naive` → TypeError (baris ~395-401).
- Sibling `GET /outstanding-advances` (:723) TIDAK crash (tak menghitung selisih hari).
- **FE `hr-travel-settlement`: klik "Export CSV" → toast SUKSES "Export dimulai. File akan terdownload."** padahal backend 500 → kegagalan senyap (screenshot). Fix: normalisasi tz (`replace(tzinfo=utc)` bila naive) + FE handle error download.

### 🟡 RC-24 — `GET /api/rahaza/work-orders/{id}/bundles-summary` 500 (tanpa consumer FE)
- Akar: `rahaza_bundles_mgmt.py:352` `r["_id"]["pcode"]` KeyError — Mongo `$group` **menghilangkan field yang missing** dari `_id`; `current_process_code` ada di **0/48** bundle (seed tak mengisinya).
- Mount: via orchestrator `routes/rahaza_bundles.py` → yang live = `_mgmt.py`; `rahaza_bundles_backup.py:337` duplikat kode sama tapi TIDAK di-mount.
- **Tidak ada consumer FE** (grep `bundles-summary` di frontend = kosong) → prioritas LOW, tapi crash nyata. Fix: `.get()` / `$ifNull`.

### 🟠 RC-25 — Accessories Dashboard misroute laten (TERVERIFIKASI RENDER oleh testing agent iteration_30)
- `dewi_accessories_dashboard.py:120,:180` baca `acc_internal_requests` (phantom; DEPRECATED per TD-009) — flow kanonik menulis **`dewi_accessory_requests`** (`request_type='internal_issuance'`). Laten: user buat request via flow kanonik → dashboard "Request Pending" tetap 0 selamanya.
- ⚠️ ANTI-FALSE-POSITIVE: `acc_loans` & `acc_purchase_requests` di dashboard **KONSISTEN** dgn modul loans/purchase yang SELF-CONSISTENT (insert nyata di `dewi_accessories_loans.py:206`, `dewi_accessories_purchase.py:208`) → **JANGAN repoint dua itu**, hanya internal-requests yang misroute.
- Render: dashboard tampil normal, KPI nol (items=4, pending=0, loans=0, PR=0), tanpa crash.

### 🔴 RC-26 — Bank Recon auto-match baca+tulis phantom `gl_entries` (MENJAWAB STOP-VERIFY RC-08 Part 2)
- `dewi_bank_reconciliation.py:604` `db.gl_entries.find(...)` dan `:670` `db.gl_entries.update_one(...)` — **TIDAK ADA insert ke `gl_entries` di seluruh kode** → auto-match SELALU early-return "Tidak ada data untuk dicocokkan" (±:606).
- Ironi: file yang sama sudah benar baca `rahaza_journal_entries` di `:127`. SSOT = `rahaza_journal_entries` (+field `is_matched` perlu peta/penyesuaian — repoint hati-hati karena :670 juga MENULIS status match ke sisi GL).
- **RESOLUSI STOP-VERIFY RC-08 Part 2**: `bank_recon_sessions`/`bank_recon_txns` = **SELF-CONSISTENT** (insert `:107`) → dormant, JANGAN repoint. Render `fin-bank-recon` = graceful empty (screenshot).

### 🟠 RC-27 — Portal Saya HR: KPI baca phantom `dewi_kpi_submissions`, SSOT = `da_kpi_submissions`(50)
- `dewi_portal_saya_hr.py:167` (dalam handler `GET /dashboard`, mulai `:93`) baca `dewi_kpi_submissions` (MISSING) — kanonik **`da_kpi_submissions`** (50 dok; ditulis `dewi_kpi_perform.py` + seed). Juga `dewi_portal_saya_backup.py:194` (cek dulu apakah file backup di-mount).
- Double-blocked oleh K4 (linkage user↔karyawan). ⚠️ STOP-VERIFY peta field (`final_score`/`grade`/`period_label` vs schema `da_kpi_submissions`) sebelum repoint.

### 🟡 RC-28 — Cluster misc phantom BARU (pola RC-14 Part 2)
| File:baris | ❌ Baca | ✅ SSOT | Dampak |
|---|---|---|---|
| `services/ai_aggregates/finance_aggregates.py:28,82,154,164` | `rahaza_invoices` | `rahaza_ar_invoices`(15) | agregat finance utk AI = 0 |
| `services/ai_aggregates/finance_aggregates.py:182` | `rahaza_payments` | `rahaza_ar_payments`(10)/`rahaza_cash_movements`(32) | idem |
| `rahaza_admin.py:178` | `employee_expense_gl_mapping` (singular) | `employee_expense_gl_mappings` (plural, CRUD self-consistent di `employee_expense_gl_mapping.py`) | counter admin salah; perluasan RC-10 |
| `workspace.py:496` (dalam `POST /api/workspace/documents/import-from-module` :426) | `procurement_requests` | `dewi_procurement_requests`(6) | import PR ke workspace selalu kosong |
| `dewi_cmt_lifecycle.py` | `wms_cmt_dispatches` | `wh_cmt_dispatches`(5) | perluasan RC-14 (CMT legacy — pertimbangkan BACKLOG-C arsip) |

### 🟡 RC-29 — Router Portal-Saya-HR di-mount DUA KALI (12 endpoint bare tanpa `/api`)
- `server.py:1676` `app.include_router(dewi_portal_saya_hr_router)` **tanpa prefix** → 12 path bare: `/dashboard`, `/leave`, `/leave-types`, `/leave/{id}`, `/notifications`, `/notifications/{id}/read`, `/overtime`, `/payslips`, `/profile`, `/profile/photo`, `/training`, `/training/{id}/certificate`.
- Mount BENAR sudah ada via `dewi_portal_saya.py:13` (nested `/api/portal/*`). Path bare tak terjangkau ingress (hanya `/api/*` di-route ke backend) → noise openapi + risiko akses lokal. Fix: hapus mount ganda `server.py:1676` (+ import `:1673` bila tak dipakai lagi).

---

## 4. KOREKSI / NILAI TAMBAH ATAS PART 1–3 (WAJIB masuk PART 4 — bagian "Koreksi Empiris")

1. **K4/RC-06 scope EXPANSION**: linkage user↔karyawan memblok **16 endpoint** (409) di 5 keluarga route: `portal-saya/*`, `/api/portal/*`, `rahaza/self/*`, `rahaza/leave-balances/my`, `dewi/kpi/my/*` — bukan hanya payslips/leaves spt dicatat Part 1.
2. **RC-13 nuansa**: `services/notification_service.py` = **DEAD SERVICE** (0 importer di seluruh backend; dia baca+tulis `dewi_notifications` tapi tak pernah dipanggil). RC-13 tetap valid.
3. **RC-12 tambahan**: `dewi_toko_products/returns/reviews` = **seed-orphan** (ditulis `dewi_demo_seed`, 0 reader app). `payslips`/`payroll_runs` di `utils/saga.py` = **FALSE-POSITIVE** (hanya docstring contoh; step nyata `rahaza_payroll_runs.py:136-147` pakai koleksi `rahaza_*` benar).
4. **RC-08 STOP-VERIFY TERJAWAB** (lihat RC-26 di atas).
5. **False-positive registry TAMBAHAN**: vendor-portal & cmt/vendor 403 (auth-scoped role vendor, benar) · `/api/push/vapid-public-key` 503 (config-missing jujur) · `/api/notifications/stream` timeout (SSE by design) · `/api/finance/ai-cashflow` 502 **TRANSIEN** ("Budget has been exceeded" — budget Emergent LLM key sesaat; retry → 200 + analisis nyata; bukan bug kode; rekomendasi: retry/backoff + graceful degrade) · `approval_chains`/`approval_requests` SELF-CONSISTENT (CRUD `approval_multilevel.py:136`; fresh deploy = 0 chains padahal PRD klaim 11 → gap **[+SEED]** config, bukan misroute) · `dewi_maklon_material_issues` SELF-CONSISTENT dormant (insert `dewi_maklon.py:613`) · modul Assets (`da_assets`/`dewi_assets`) SELF-CONSISTENT dormant — BEDA fitur dari `rahaza_fixed_assets`(15).
6. **Klasifikasi menyeluruh** (`d2_phantom_classifier.py`): 47 koleksi READ-ONLY-EMPTY (dead-read/misroute — mayoritas sudah tercakup RC Part 1-3, yang BARU sudah diangkat jadi RC-25..28), **216 SELF-CONSISTENT-EMPTY (dormant — JANGAN repoint)**, 15 WRITE-ONLY (orphan).
7. **404 (116)**: mayoritas graceful not-found (ID resolver lintas koleksi / flow dormant) — catat sebagai keterbatasan metodologi (jujur, spt Appendix E Part 2).

## 5. STATUS VERIFIKASI RENDER (STEP C-ext)

| Modul (id) | Status render | Bukti |
|---|---|---|
| `accessories-dashboard` | ✅ render, KPI nol, tanpa crash | testing agent iteration_30 (satu-satunya yang berhasil dinav) |
| `hr-leave-balances` | ⚠️ **empty-state MENYESATKAN** (500 ditelan) | screenshot Playwright |
| `hr-travel-settlement` | ⚠️ Export CSV → **toast sukses palsu**, backend 500 | screenshot |
| `fin-bank-recon` | ✅ graceful empty | screenshot |
| `marketing-live-analytics` | ❌ **ErrorBoundary "Portal Error"** + pesan Select.Item persis | screenshot |
| `marketing-live` | ⚠️ KPI semua 0 (summary 500 ditelan) TAPI tabel sesi TAMPIL (endpoint list OK) | screenshot |
| `prod-capacity-planning` | ⚠️ WO Aktif 0, utilisasi 0%, "Belum ada data output" (RC-17) | screenshot |
| `rnd-samples` | ⚠️ "Belum ada sample request" (RC-18) | screenshot |
| `marketing-kol`, `marketing-kol-leaderboard` | 🟡 halaman termuat, **state data belum terekam tuntas** (teks terpotong) — **PR utk agent berikutnya** | — |

Catatan navigasi utk testing: testing agent gagal nav 9/10 via label teks; **solusi terbukti: deep-link `#<module-id>` + reload**. Console noise: `ws://localhost:443/ws` WebSocket error = artefak environment (WDS), abaikan.

## 6. YANG BELUM DIKERJAKAN (urutan disarankan)

1. **(Utama) STEP E — tulis `/app/SSOT_MASTER_REPAIR_PLAN_PART4.md`**, kualitas ≥ Part 1, non-redundant:
   - Struktur disarankan: BAGIAN 0 konteks+metodologi+cakupan (954/958 GET=99.6%, write hanya 2 flow B2 — jujur) → BAGIAN 0.5 Koreksi/Resolusi atas Part 1-3 (isi §4 handoff ini) → BAGIAN 1 SSOT registry tambahan (leave_balances 2-schema, da_kpi_submissions, gl_entries→rahaza_journal_entries, dewi_accessory_requests, dll) → BAGIAN 2 RC-19..RC-29 (format kartu Part 1: Prioritas/Dampak/file:baris/AKAR/peta field/LANGKAH/VERIFIKASI/ROLLBACK/RISIKO/DO-NOT) → BAGIAN 3 Dormant registry tambahan (dari 216 self-consistent, per domain baru) → BAGIAN 4 False-positive registry tambahan → BAGIAN 5 Roadmap **Wave J** (usul: J.1 = RC-21 COA cascade [prasyarat RC-05/RC-10, dampak terbesar]; J.2 = RC-22+RC-23 [crash + UX menyesatkan]; J.3 = RC-20+RC-19; J.4 = RC-25/26/27/28; J.5 = RC-24+RC-29 housekeeping) → APPENDIX bukti empiris (tabel §3+§5 handoff) + perintah verifikasi (script §2).
2. Lengkapi 2 render yang belum tuntas (`marketing-kol`, `marketing-kol-leaderboard`) via deep-link.
3. STOP-VERIFY kecil sebelum RC-27 final: peta field `da_kpi_submissions` + cek mount `dewi_portal_saya_backup.py`.
4. Update `/app/plan.md` (entry sesi sudah ditambahkan — lengkapi saat PART4 selesai).
5. **JANGAN eksekusi perbaikan apa pun** sampai user menyetujui dokumen (konvensi Part 1-3). Setelah disetujui, mulai dari RC-21 (COA) karena memblok paling banyak.

## 7. KREDENSIAL & PERINTAH CEPAT

```bash
# health + login
curl -s http://localhost:8001/api/health
TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/login -H 'Content-Type: application/json' \
  -d '{"email":"admin@garment.com","password":"Admin@123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo "$TOKEN" > /tmp/admin_token.txt

# regenerate seluruh bukti STEP D (35 detik)
curl -s http://localhost:8001/api/openapi.json -o /tmp/openapi.json
cd /app/backend && python3 migrations/d_full_scope_forensics.py | tail -40
python3 migrations/d2_phantom_classifier.py | head -60

# reproduksi 5 crash 500
# /api/marketing/live/summary (RC-15) · /api/rahaza/leave-balances (RC-22)
# /api/hr/expenses/outstanding-advances/export (RC-23)
# /api/rahaza/work-orders/{wo_id}/bundles-summary (RC-24) · /api/wms/materials/{id}/label-pdf (RC-19)
```

*Dibuat 2026-07-02 oleh sesi forensik Part 4 (investigasi selesai, dokumen belum). Semua klaim di atas berbasis bukti empiris yang bisa direproduksi dengan perintah §2/§7 — zero assumption.*
