# Development Plan — DA ERP (Lanjutan 4 Next Action Items)

## 1) Objectives
- Memverifikasi klaim fitur FASE 8+/9 yang sudah “SELESAI & TERUJI” pada environment saat ini (DB fresh).
- Menutup 4 Next Action Items tanpa regresi:
  1) ganti `window.prompt()` terakhir (alasan tolak opname) → modal UX seragam + testable
  2) digest harian item HPP=0 (ringkasan) tanpa mematikan notifikasi per-item
  3) jadwal rapor valuasi bulanan via email (Excel+PDF) dengan SMTP config via UI + verifikasi pakai SMTP dummy
  4) siapkan & eksekusi drop `accessory_legacy` (acc_loans, acc_internal_requests) via migrasi terpandu + rollback

## 2) Implementation Steps (Phases)

### Phase 1 — Core POC (Integrasi Email + Scheduler + Attachment)
Fokus: ini bagian paling rawan (SMTP, attachment, cron). Jangan lanjut Phase 2 sebelum POC hijau.

**POC User Stories (min 5):**
1. Sebagai admin, saya bisa menjalankan job scheduler “kirim rapor” secara manual dan melihat hasilnya tercatat di run history.
2. Sebagai tim keuangan, saya menerima email rapor valuasi dengan 2 lampiran (XLSX+PDF) yang bisa dibuka.
3. Sebagai admin, saya bisa mengatur SMTP via UI dan men-test kirim email tanpa restart server.
4. Sebagai sistem, job rapor bulanan idempoten (tidak spam dobel untuk periode yang sama di hari yang sama).
5. Sebagai admin, jika SMTP belum valid, job tetap mencatat kegagalan yang bisa diinspeksi.

**Langkah:**
- Seed minimal data valuasi (materials type=accessory + stok + beberapa mutasi) agar export menghasilkan konten nyata.
- Tambah util pengiriman email ber-lampiran (backend `utils/email_sender.py`):
  - mode SMTP tanpa auth/TLS untuk dummy lokal (dev)
  - STARTTLS / SSL untuk produksi (config)
  - dukung attachment bytes (xlsx/pdf)
- Tambah config field di `ProviderConfigIn` + persistence:
  - `valuation_report_enabled` (bool)
  - `valuation_report_extra_emails` (list/string)
  - `smtp_use_tls` (bool), `smtp_use_ssl` (bool), `smtp_auth_required` (bool)
  - `smtp_test_email` sudah ada → pakai untuk test
- Buat job `monthly_valuation_report_email` di `backend/utils/scheduler.py` (JOB_REGISTRY):
  - Cron: tanggal 1, 06:00 Asia/Jakarta
  - periode = bulan sebelumnya
  - generate XLSX+PDF via `utils/accessory_valuation_export.py`
  - kirim ke: semua user role accounting/keuangan + extra recipients
  - simpan log terstruktur ke `acc_valuation_report_runs`
- Verifikasi end-to-end dengan SMTP dummy lokal (aiosmtpd/debug server) + bukti 2 attachment.
- Expose `run-now` via scheduler UI yang sudah ada (otomatis muncul di Notification Center).

### Phase 2 — V1 App Development (Implement 4 Next Action Items)

#### Phase 2A — FASE 0 Verifikasi Bring-up + Seed + Regresi Script
**User Stories:**
1. Sebagai QA, saya bisa menjalankan `verify_fase8.py` dan melihat semua PASS pada DB fresh yang sudah di-seed.
2. Sebagai QA, saya bisa menjalankan `verify_fase8plus.py` dan melihat export XLSX/PDF valid.
3. Sebagai QA, saya bisa menjalankan `verify_fase9_legacy_drop.py` dan melihat audit→dry-run→drop→rollback berjalan.
4. Sebagai admin, saya bisa login dengan kredensial seed dan melihat portal utama tidak error.
5. Sebagai user gudang, saya bisa membuka modul Aksesoris dan melihat tab Valuasi HPP menampilkan data.

**Langkah:**
- Jalankan `scripts/seed_acc_ui_demo.py` + seed valuasi minimal (bila belum tercakup) → pastikan ada item HPP=0 + mutasi.
- Jalankan `scripts/verify_fase8.py`, `scripts/verify_fase8plus.py`, `scripts/verify_fase9_legacy_drop.py` dan simpan hasil di `test_reports/`.

#### Phase 2B — Next Action #1: Prompt Terakhir (Tolak Opname) → Modal
**User Stories:**
1. Sebagai supervisor, saya bisa menolak opname dengan mengisi alasan di modal yang rapi.
2. Sebagai supervisor, saya tidak bisa submit penolakan tanpa alasan (validasi inline).
3. Sebagai QA, saya bisa mengotomasi penolakan opname via Playwright menggunakan `data-testid`.
4. Sebagai user, saya melihat feedback sukses/gagal tanpa `alert()`.
5. Sebagai admin, UX tab Opname konsisten (confirm/alert diganti modal yang seragam bila feasible tanpa scope creep).

**Langkah:**
- Ubah `rejectSession` di `frontend/src/components/erp/AccessoryModule.jsx`:
  - modal: textarea alasan + tombol batal/kirim
  - validasi inline “Alasan wajib diisi”
  - data-testid: `opname-reject-modal`, `opname-reject-reason`, `opname-reject-confirm`
- (Opsional terukur) ganti `window.confirm/alert` di Opname menjadi modal ringan berbasis state (tanpa refactor besar).
- Rebuild frontend via `bash /app/scripts/rebuild_frontend.sh`.

#### Phase 2C — Next Action #4: Ringkasan Alarm Harian (Digest)
**User Stories:**
1. Sebagai admin gudang, saya menerima 1 notifikasi ringkasan harian item HPP=0.
2. Sebagai admin, ringkasan memuat kode/nama/stok dan jumlah mutasi 24 jam terakhir.
3. Sebagai admin, notifikasi per-item tetap ada dan tidak spam (anti-spam 24 jam/material).
4. Sebagai admin, saya bisa menjalankan job digest “Run Now” dari UI Scheduler.
5. Sebagai admin, digest idempoten (maks 1×/hari) dan tercatat di run history.

**Langkah:**
- Tambah job `daily_unvalued_digest` di `backend/utils/scheduler.py`:
  - Cron 07:30 Asia/Jakarta
  - Query SSOT `rahaza_materials` type=accessory unit_cost=0 (atau field cost canonical) + stok
  - Hitung mutasi 24 jam terakhir dari `rahaza_material_movements`
  - Kirim 1 notifikasi per penerima role (UNVALUED_NOTIF_ROLES) dengan deep-link `#wh-accessory`
  - Simpan marker idempoten (mis. doc `dewi_scheduler_runs` meta tanggal)
- Tambah panel FE sederhana di tab Valuasi HPP: tombol “Kirim Digest Sekarang” (memanggil run-now) + preview list.

#### Phase 2D — Next Action #2: Jadwal Rapor Bulanan via Email
**User Stories:**
1. Sebagai keuangan, saya menerima rapor bulan lalu otomatis tanpa download manual.
2. Sebagai admin, saya bisa menambah recipient tambahan di UI.
3. Sebagai admin, saya bisa mematikan/menyalakan rapor otomatis.
4. Sebagai admin, saya bisa klik “Kirim sekarang” dari UI Valuasi.
5. Sebagai QA, saya bisa memverifikasi attachment XLSX+PDF terkirim via SMTP dummy.

**Langkah:**
- Reuse job dari Phase 1 (POC) → finalisasi:
  - idempoten per periode (YYYY-MM) + guard “sudah terkirim”
  - simpan riwayat ke `acc_valuation_report_runs`
- Tambah tombol FE “Kirim rapor bulan lalu sekarang” (call scheduler run-now) + tampilkan status terakhir.

### Phase 3 — Prasyarat Drop `accessory_legacy` (Migrasi + UI cleanup + Drop)
**User Stories:**
1. Sebagai admin, saya bisa menutup pinjaman legacy yang masih Active secara otomatis (audit trail lengkap).
2. Sebagai admin, saya bisa rollback migrasi penutupan jika salah.
3. Sebagai user, saya tidak lagi melihat menu/tab legacy yang menyesatkan.
4. Sebagai sistem, tidak ada kode aktif yang membaca `acc_internal_requests` / `acc_loans`.
5. Sebagai admin, saya bisa menjalankan drop terpandu + verifikasi arsip + rollback.

**Langkah:**
- Migrasi terpandu:
  - buat script baru (atau extend `drop_legacy_collections_guided.py`) untuk “close legacy loans”:
    - set status `closed_legacy` + returned_at + notes + audit log collection
    - rollback support
- Frontend cleanup:
  - lepas Tab “Peminjaman” dari nav Portal Aksesoris (atau ubah jadi redirect murni ke `asset-loans` tanpa fetch legacy)
  - hapus kartu KPI “Dipinjam” yang selalu 0 (lokasi sesuai dashboard module)
- Backend cleanup:
  - endpoint deprecated yang masih baca `acc_internal_requests` → 410
  - `_enrich_movement` stop baca `acc_internal_requests`
  - hapus `create_index` untuk legacy di startup
- Flip `GROUPS['accessory_legacy'].ready=True` lalu jalankan:
  - `--audit` → `--dry-run` → `--execute` → verifikasi arsip → `--rollback` (uji) → execute final
- Tambah `scripts/verify_fase10_accessory_legacy.py` (PASS/FAIL jelas).

### Phase 4 — Testing, Regression, Documentation
**User Stories:**
1. Sebagai QA, saya bisa menjalankan regresi backend+frontend tanpa failure.
2. Sebagai admin, semua job scheduler baru terlihat di UI dan bisa Run Now.
3. Sebagai keuangan, rapor export manual tetap jalan.
4. Sebagai gudang, notifikasi per-item & digest tidak mengganggu transaksi stok.
5. Sebagai maintainer, dokumen handoff menjelaskan konfigurasi  seed + cara rebuild.

**Langkah:**
- Jalankan: `testing_agent_v3` (E2E), `npx eslint .` (root), `ruff`, `yarn build`, verify scripts.
- Update dokumen: `plan.md`, `memory/CHANGELOG.md`, `HANDOFF.md`, guideline drop legacy.
- Bersihkan artefak seed/test (data bertag PREFIX/QA) sesuai pola skrip seed.

## 3) Next Actions (Immediate)
1. Seed baseline aksesoris + jalankan verify scripts Phase 0 (fase 2A).
2. Implement modal tolak opname (fase 2B) + rebuild + smoke test.
3. Bangun POC email attachment + SMTP dummy + job bulanan run-now (Phase 1).
4. Tambah job digest harian 07:30 (fase 2C) + run-now.
5. Eksekusi prasyarat + drop `accessory_legacy` (Phase 3).

## 4) Success Criteria
- Phase 0: `verify_fase8.py`, `verify_fase8plus.py`, `verify_fase9_legacy_drop.py` semua PASS pada environment ini.
- Prompt terakhir hilang: tidak ada `window.prompt()` untuk tolak opname; modal validasi inline + testid.
- Digest harian: job terdaftar, idempoten, kirim 1 ringkasan/hari + per-item notif tetap.
- Rapor bulanan: job 1st 06:00 WIB, kirim email ke role Keuangan + extra recipients, lampiran XLSX+PDF, tercatat di run log, bisa run-now.
- `accessory_legacy` siap & drop terpandu berhasil (audit/dry-run/execute/rollback) dan tidak ada consumer aktif.
- Regresi: E2E testing_agent_v3 lulus; lint FE 0 error; ruff OK; `yarn build` sukses.
