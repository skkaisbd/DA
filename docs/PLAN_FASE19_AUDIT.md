# PLAN FASE 19 — AUDIT-1..4 (endpoint sweep 0 temuan + wiring FE↔BE jujur)

## 1) Objectives

- Menuntaskan titik terhenti: **Phase 5: AUDIT-1..4** dari repo `kakamananababa/da`.
- Mengubah alat audit menjadi **jujur (ground truth)** lalu memperbaiki temuan sampai:
  - `python3 scripts/audit_endpoint_sweep.py` → **0 findings** (dengan allowlist resmi).
  - `bash scripts/gate.sh` + `bash scripts/run_all_verifications.sh` → **hijau**.
- Menutup risiko latent 500 (karantina) dengan fix + backfill + sentinel yang **pernah merah**.

## 2) Implementation Steps

### Phase 1 — Core POC (isolasi) untuk integrasi yang paling failure-prone
**Core workflow**: (a) webhook marketplace harus **fail-closed** via HMAC, (b) Web Push harus punya VAPID keypair nyata, (c) karantina summary tahan data korup.

**User stories (POC)**
1. Sebagai ops, saya bisa menjalankan skrip POC yang membuktikan webhook menolak signature salah dan menerima yang benar.
2. Sebagai ops, saya bisa menjalankan skrip POC yang memastikan `/api/push/vapid-public-key` mengembalikan 200 saat VAPID dikonfigurasi.
3. Sebagai gudang, saya tidak pernah melihat 500 di ringkasan karantina walau data reject_reasons tidak rapi.
4. Sebagai maintainer, saya punya sentinel yang bisa dibuat merah dengan menanam ulang bug.
5. Sebagai maintainer, POC tidak mencemari DB (prefix artefak + cleanup di `finally`).

**Steps**
- Buat `scripts/verify_fase19_poc_integrations.py`:
  - Generate payload minimal + signature salah/benar untuk 3 webhook.
  - Assert `401` untuk missing/invalid signature; `200` untuk valid.
  - Jika VAPID belum ada: generate keypair dan assert endpoint 200.
- Websearch singkat best-practice:
  - HMAC webhook verification (constant-time compare, raw body signing, replay protection optional).
  - VAPID keypair generation + pywebpush.

### Phase 2 — V1 App Development (AUDIT-2 FIRST: sweep 0 findings)

**User stories (AUDIT-2)**
1. Sebagai ops, saya bisa scrape `/api/metrics` tanpa token dan hanya mendapat agregat aman (tanpa PII).
2. Sebagai security, webhook marketplace menolak request palsu dengan pesan error yang jelas dan kode status konsisten.
3. Sebagai marketing ops, event webhook yang valid tetap tersimpan dengan metadata verifikasi untuk audit.
4. Sebagai user, saya bisa mengaktifkan push notification di browser dan melakukan “test push”.
5. Sebagai maintainer, endpoint sweep menampilkan 0 findings tanpa menyembunyikan bug.

**Steps (AUDIT-2)**
- **Public allowlist resmi**
  - Tambahkan `/api/metrics` ke SSOT allowlist yang dipakai bersama:
    - `scripts/audit_endpoint_sweep.py` (PUBLIC regex/allowlist)
    - `scripts/guardrails/verify_auth_coverage.py` (PUBLIC_ALLOWLIST)
  - Sertakan **reason string** per path (mis. `metrics: aggregate counts only`).
  - Tambah verifikasi: `/api/metrics` tidak mengandung field sensitif (email/name/raw docs).

- **Webhook HMAC (fail-closed)**
  - Implement verifikasi signature berbasis **raw request body** untuk:
    - Tokopedia header `x-tokopedia-hmac-signature`
    - Shopee header `x-shopee-signature`
    - TikTok (tentukan header yang dipakai di codebase; jika belum ada, gunakan standar `x-tiktok-signature` + dokumentasikan)
  - Secrets di `backend/.env`:
    - `TOKOPEDIA_WEBHOOK_SECRET`, `SHOPEE_WEBHOOK_SECRET`, `TIKTOK_WEBHOOK_SECRET`
  - Jika secret tidak diset → **401 (fail-closed)**.
  - Simpan metadata: `signature_present`, `signature_valid`, `verified_at`, `sig_algo`.

- **VAPID real keypair + dependensi**
  - Tambahkan `pywebpush` + generator VAPID (pilih library yang tersedia; fallback gunakan `cryptography` untuk generate keypair sesuai spec).
  - Tambah skrip `scripts/gen_vapid_keys.py` (idempotent): generate & tulis ke `backend/.env` bila belum ada.
  - Update `scripts/bootstrap.sh` agar memanggil generator (hanya jika key kosong).
  - Perbaiki FE: halaman/setting untuk enable/disable push + state “belum dikonfigurasi” yang jelas.

- **Karantina latent 500 (reject_reasons)**
  - Buat SSOT helper `backend/utils/reject_reasons.py::normalize_reject_reasons(x, qty_default)`.
  - Terapkan di write boundary:
    - `routes/rahaza_grn_qc.py` saat menyimpan `line['reject_reasons']`.
    - setiap jalur yang memanggil `quarantine.quarantine_in(reject_reasons=...)`.
  - Defensive read: `core/quarantine.py.summary()` harus toleran terhadap list of strings/dict campur.
  - Migration/backfill: `backend/migrations/backfill_quarantine_reject_reasons.py` untuk merapikan dokumen existing.

- Jalankan ulang `python3 scripts/audit_endpoint_sweep.py` sampai **0 findings**.

### Phase 3 — AUDIT-1 + AUDIT-3: alat audit jujur + wiring FE↔BE

**User stories (AUDIT-1/3)**
1. Sebagai maintainer, audit duplikasi endpoint tidak menghasilkan false positive karena prefix/include router.
2. Sebagai maintainer, audit bisa membedakan “name collision” vs “copy-paste SSOT yang berbahaya”.
3. Sebagai maintainer, laporan FE↔BE tidak memfitnah modul FE yang tidak reachable.
4. Sebagai dev, call string template literal FE terdeteksi utuh (tidak terpotong).
5. Sebagai PM, tab audit menunjukkan tab yang benar-benar broken dan dapat diperbaiki bertahap.

**Steps (AUDIT-1: duplication audit truth)**
- D2 endpoint kembar:
  - Ubah `scripts/audit_duplication.py` agar memakai `scripts/lib/route_table.runtime_route_table()` sebagai sumber kebenaran.
  - Fix false-positive docstring: abaikan `@router.*("/x")` yang berada di docstring / triple-quoted string.
- Koreksi kontradiksi “first vs last wins”:
  - Tambah micro-test `scripts/probe_fastapi_duplicate_route_semantics.py` yang membuktikan route mana yang menang.
  - Update docstring `scripts/lib/route_table.py` + `audit_duplication.py` agar konsisten dengan bukti.
- D1 duplicate functions:
  - Ubah scoring: HIGH hanya jika **body hash berbeda** dan modulnya berpotensi SSOT sama (auth/approval/finance guards).
  - Demote “summary” lintas domain menjadi INFO.
- Konsolidasi duplikasi SSOT yang nyata:
  - Hapus/shim `require_auth` bayangan di `routes/rahaza_notifications.py` agar selalu impor dari `auth.py`.
  - Konsolidasikan guard `_require_fin/_require_hr/_require_approver/_require_hr_admin` ke satu modul utils (dipakai semua route).
  - Konsolidasikan `cascade_delete_po` ke 1 implementasi (shim untuk backward import).
  - `_determine_approval` & `_log_movement`: jadikan helper SSOT (1 file) lalu impor.

**Steps (AUDIT-3: FE↔BE wiring + tab audit)**
- Perbaiki ekstraksi FE call:
  - Update regex di `audit_duplication.py` untuk template literals (termasuk `(`, `)`), dan normalisasi `${...}`.
  - Tambah filter “reachable modules”: parse `frontend/src/components/erp/moduleRegistry.js` untuk modul yang benar-benar di-load; abaikan file yang di-comment/redirect.
- Jalankan `python3 scripts/tab_audit.py` dan perbaiki tab yang reachable tapi broken.
- Archive/relocate modul FE yang sudah tidak dipakai (contoh: CMTManagementModule) supaya tidak mengotori audit.

### Phase 4 — AUDIT-4: Sentinel, verifikasi, dan testing agent

**User stories (AUDIT-4)**
1. Sebagai maintainer, saya bisa menjalankan 1 skrip verifikasi fase audit yang mengunci regresi.
2. Sebagai maintainer, sentinel bisa dibuat merah bila bug lama ditanam ulang.
3. Sebagai QA, `run_all_verifications.sh` tetap 0 drift dan tidak mencemari data.
4. Sebagai user HR/gudang, modul lama tetap berjalan setelah refactor audit.
5. Sebagai ops, gate hijau adalah bukti, bukan klaim dokumen.

**Steps**
- Buat `scripts/verify_fase19_audit.py` (daftarkan TERAKHIR di `scripts/run_all_verifications.sh`):
  - Assert endpoint sweep findings == 0.
  - Assert webhook invalid signature => 401.
  - Assert VAPID endpoint 200 & format key valid.
  - Tanam ulang data reject_reasons corrupt (prefix `TEST-F19-*`) → pastikan summary tetap 200.
  - Mode `--prove-red`: sementara disable normalizer → pastikan sentinel merah (lalu revert).
- Jalankan:
  - `bash scripts/run_all_verifications.sh`
  - `bash scripts/gate.sh`
  - `python3 scripts/audit_endpoint_sweep.py`
- Panggil `testing_agent_v3` untuk E2E (backend+frontend) berdasarkan `test_result.md`.
- Update dokumen: tambah header sesi aktif di `plan.md`, update `HANDOFF_NEXT_AGENT.md`, `memory/CHANGELOG.md`.

## 3) Next Actions (immediate)
1. Implement SSOT allowlist publik (tambah `/api/metrics` + reason) dan re-run sweep.
2. Implement HMAC verification di `backend/routes/marketing_webhooks.py` + env secrets + POC script.
3. Implement VAPID key generation + add dependencies + FE setting minimal + endpoint 200.
4. Fix latent quarantine 500: normalize reject_reasons (GRN QC) + defensive summary + backfill migration.
5. Fix audit_duplication D2: switch to `runtime_route_table()` + add proof script for duplicate route semantics.

## 4) Success Criteria
- `python3 scripts/audit_endpoint_sweep.py` → **AUTH-OPEN 0, SRV-5XX 0, WRITE-NOAUTH 0** (metrics tetap public via allowlist resmi).
- Webhook endpoints menolak request tanpa/invalid signature (401) dan menerima yang valid (200) sambil menyimpan metadata verifikasi.
- `/api/push/vapid-public-key` → 200; subscribe + test push bisa dieksekusi (minimal dev path) dan FE menampilkan state konfigurasi.
- `/api/wms/quarantine/summary` tidak pernah 500 walau reject_reasons korup; migration/backfill tersedia.
- `python3 scripts/audit_duplication.py` tidak lagi memunculkan D2 false-positive; semantik duplikat route terdokumentasi berdasarkan bukti.
- `bash scripts/run_all_verifications.sh` + `bash scripts/gate.sh` hijau; `scripts/verify_fase19_audit.py` terdaftar terakhir dan sudah proven-red.
