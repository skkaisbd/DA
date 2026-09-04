# QA / Bug Register — Flow Kehadiran/Absensi (`flow-sdm-kehadiran`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, validator flow LULUS 10/10).

## Ringkasan
- **Status:** CLEAN (setelah perbaikan 1 bug HIGH) — happy-path (clock-in → clock-out → rekap → feed payroll) terverifikasi via `tests/flow_sdm_kehadiran_test.py`.
- **Guardrail terverifikasi (3):** double clock-in (400), clock-out tanpa clock-in (400), double clock-out (400).
- **Geofence:** clock-in `in_range` (di kantor) & `out_of_range` (di luar radius, tetap tercatat/advisory) terverifikasi.
- **DB pristine:** hard-cleanup attendance_events + employee + office fixture.

## Temuan
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| ABS-01 | **HIGH** | `POST /api/rahaza/attendance/clock-out` mengembalikan **500** `TypeError: can't subtract offset-naive and offset-aware datetimes`. Root cause: `_calc_hours()` mengurangkan `clock_in` (naive datetime dari MongoDB) dengan `_now()` (timezone-aware UTC). Dampak: **clock-out rusak total** untuk semua karyawan. **FIX:** normalisasi kedua datetime ke UTC-aware sebelum pengurangan di `rahaza_attendance.py::_calc_hours`. Verified via POC (clock-out kini 200, hours_worked terhitung). | **FIXED** |
| ABS-02 | LOW | Endpoint kehadiran memakai guard `require_auth` (tanpa role-check granular di level API); pembatasan mengandalkan Portal SDM & UI. Rekomendasi kebijakan operasional didokumentasikan di bagian RBAC. | NOTED |
| ABS-03 | INFO | Geofence bersifat advisory: clock-in di luar radius tetap tercatat (`out_of_range`) agar tidak menghambat operasi (GPS meleset/tugas luar). By design. | NOTED |
| ABS-04 | INFO | Self-service clock-in/out berada di komponen `OperatorView` (dirender App.js untuk peran operator), bukan module registry. Testid: `operator-clock-in-btn`, `operator-clock-out-btn`. Grid supervisor di `hr-attendance-hub` (tab manual). | NOTED |
| ABS-05 | INFO | `hours_worked=0.0` pada POC wajar karena clock-in/out berjarak beberapa detik; yang dibuktikan adalah perbaikan galat (tidak lagi 500) & jalur perhitungan. | NOTED |
| ABS-06 | **HIGH** | Bulk save absensi (grid supervisor, tombol "Simpan Semua"/"Tandai Hadir & Simpan") **gagal** (toast "Gagal menyimpan absensi"). Root cause: **contract mismatch** — frontend `RahazaAttendanceModule.saveAll` mengirim `{ date, entries: [...] }` (key `entries`), sedangkan backend `bulk_attendance` membaca `body.get("rows")` → `rows` kosong → 400 "rows kosong". Dampak: input kehadiran massal supervisor **rusak total**. **FIX:** backend menerima `rows` maupun `entries` + menerapkan `date` top-level ke baris tanpa date. Verified via curl (200 saved:1) & UI (toast "Absensi ... berhasil disimpan (1 karyawan)"). | **FIXED** |

## Perubahan Kode (fix ABS-06)
- File: `backend/routes/rahaza_attendance.py`, fungsi `bulk_attendance`.
- Sebelum: `rows = body.get("rows", [])`.
- Sesudah: `rows = body.get("rows") or body.get("entries") or []`; `default_date = body.get("date") or _today_iso()`; setiap row tanpa `date` diisi `default_date`.

## Perubahan Kode (fix ABS-01)
- File: `backend/routes/rahaza_attendance.py`, fungsi `_calc_hours`.
- Sebelum: `diff = (cout - cin).total_seconds()/3600` (galat bila salah satu naive).
- Sesudah: bila `cin.tzinfo is None` → `cin = cin.replace(tzinfo=timezone.utc)`; idem `cout`; lalu hitung.

## Bukti Uji
- `python3 tests/flow_sdm_kehadiran_test.py` → **KEHADIRAN/ABSENSI FLOW ALL PASS**
  (clock-in in_range → clock-out hours_worked → rekap days_hadir=1 → grid/list/my-today/dashboard → clock-in out_of_range; 3 guardrail 400; DB pristine).
- `python3 scripts/docgen/validate_flow.py --flow-id flow-sdm-kehadiran` → **LULUS 10/10**.
- `python3 scripts/docgen/audit_testids.py --module-id hr-attendance-hub` → **LULUS (0 FAIL)**; audit file OperatorView+RahazaAttendanceModule → **0 FAIL (24 testid)**.
- **E2E UI (Playwright, Portal SDM → Kehadiran, Shift & Cuti → Absensi Harian):** Dashboard SDM menampilkan Total Karyawan Aktif=1 & KPI kehadiran (data nyata); grid absensi memuat karyawan; **"Tandai Hadir & Simpan"** → toast "Absensi 2026-07-08 berhasil disimpan (1 karyawan)" (setelah fix ABS-06). **Tidak ada logout**. Data E2E dibersihkan (DB pristine). Catatan: self-service clock-in/out (OperatorView) butuh peran operator; diverifikasi pada level backend POC.
