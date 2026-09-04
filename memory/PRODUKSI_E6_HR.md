# E6 — HR : Operator, Piece-Rate Payroll, Shift, KPI (AS-IS vs TO-BE)
> Handoff §E6. GROUNDED: `rahaza_payroll_*.py`, `rahaza_attendance*.py`, `hr_shifts.py`,
> `dewi_kpi_*.py`. STATUS: ANALISIS.

## 0. TEMUAN INTI (risiko adopsi)
**Piece-rate payroll di-anchor ke `rahaza_wip_events` (per-operator, per-process output).** Bila D1
menghapus mesin rahaza multi-stage → **payroll skema `pcs` kehilangan sumber output**, karena
SOMMERVILLE `production_progress` mencatat output di level **JOB** (`recorded_by`=nama), TANPA
`operator_id`/`process_id`.

## 1. PAYROLL — AS-IS (`rahaza_payroll_profiles.py` / `rahaza_payroll_runs.py`)
| Aspek | Detail | Grounding |
|---|---|---|
| Skema gaji | **`monthly` \| `daily` \| `pcs` (piece-rate)** | profiles scheme |
| Komponen | basic + transport/meal allowance + overtime − BPJS(kes/jht/jp) − PPh21 − LWOP proration | `:196-373`, payslips `days_hadir` |
| Sumber kehadiran | `rahaza_attendance_events` (status hadir, hours_worked, overtime_hours) + `rahaza_overtime_requests` (approved) | `:203-228` |
| Proration LWOP | working_days per periode (fallback 22 hari) | `:348-373` |
| **Piece-rate (`pcs`)** | **sum `rahaza_wip_events`** {operator_id, event_type='output', process_id, qty} per periode → per-process breakdown | `:232-250` ⚠️ **anchor rahaza multi-stage** |
| GL bridge | `post_payroll_run` (payroll_finalize) + `post_payroll_payment` + `void_payroll_payment` | runs `:200,297,342` |

## 2. ATTENDANCE — AS-IS
- SSOT: `rahaza_attendance_events` (108× akses). 
- Jalur auto-capture: `rahaza_auto_attendance*` (config, selfie, webauthn, **zkteco** mesin fingerprint),
  approvals (`rahaza_auto_attendance_approvals`).
- Dipakai payroll (days_hadir, jam, lembur) + KPI (skor absensi).

## 3. SHIFT — AS-IS
- `rahaza_shifts` (29×) + `hr_shifts.py` + `dewi_shift_scheduler.py` + `marketing_livehost_shifts.py` (khusus livehost).
- Field shift dinormalisasi (Sesi #24 fix: `shift_type`, `shift_start_time`).

## 4. KPI — AS-IS (`dewi_kpi_*`)
- Periode: `da_kpi_periods`. Penilaian: `perform` items dgn **weight** → section score + attitude score +
  **absensi score** (dari attendance). Leaderboard + gamification + reports + questions.
- **Bukan** output produksi langsung; appraisal berbasis periode + bobot (mirip OKR/penilaian karya).

## 5. OPERATOR / LINE ASSIGNMENT — AS-IS
- Ada di mesin **rahaza multi-stage**: `rahaza_aps` (advanced planning/scheduling), `rahaza_andon`,
  line assignment per proses. → bagian yang D1 usulkan DIBUANG.
- SOMMERVILLE: TIDAK ada assignment operator per proses; job = milik **vendor** (bukan operator internal).

## 6. TO-BE — HR dalam ekosistem
| Aspek | PRODUKSI INTERNAL (TO-BE) | MAKLON |
|---|---|---|
| Upah utama | **monthly/daily** (BPJS/PPh21) — matang, GL-bridged → PERTAHANKAN | operator internal N/A (jasa vendor) |
| Piece-rate | butuh **capture output per-operator** — SOMMERVILLE job-level tak cukup | biaya CMT per pcs = di **vendor** (cmt_price), bukan payroll internal |
| Attendance/Shift/KPI | tetap (lintas-portal HR, tak tergantung mesin produksi) | tetap |
| Operator assignment | hilang bila rahaza multi-stage dibuang | N/A |

## 7. DECISION POINTS
### ✅ HR-1 (DIPUTUSKAN user: **CAMPURAN** — borongan + bulanan)
Operator internal ADA yang borongan (per-pcs) & ADA yang bulanan → **piece-rate WAJIB dipertahankan**.
Implikasi (dikerjakan di adapter, lihat `PRODUKSI_E10_ADAPTER_MIGRASI.md`):
- rahaza multi-stage engine BOLEH dibuang, **TAPI capture output per-operator/proses TIDAK boleh hilang**.
- Perlu tetap ada sumber output per-operator utk skema `pcs`. Kandidat desain (dibahas di E10):
  **(i)** pertahankan `rahaza_wip_events` sebagai *log output ringan* (operator_id, process_id, qty) yang
  ditulis dari layar progress produksi baru; ATAU **(ii)** perkaya `production_progress` dgn
  `operator_id`+`process_id`+qty. Payroll `scheme='pcs'` tetap menjumlahkan sumber ini per periode.
- Skema `monthly`/`daily` tidak berubah (sudah matang, BPJS/PPh21).

### HR-2 (info) — KPI/attendance/shift AMAN
Tidak tergantung mesin produksi (rahaza/SOMMERVILLE) → tak terpengaruh adopsi. Tetap.

## 8. INVARIAN
- Payroll idempotent (finalize→pay→void via posting).
- days_hadir & jam dari `rahaza_attendance_events` (satu SSOT).
- Piece-rate: Σqty output per operator = dasar upah (jika HR-1=B).

---
*E6 selesai. Lanjut E7 (Aset + peminjaman aset).*
