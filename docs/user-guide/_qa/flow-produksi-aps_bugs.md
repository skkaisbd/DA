# QA / Bug Register — Flow Penjadwalan APS (`flow-produksi-aps`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, validator flow LULUS 10/10).

## Ringkasan
- **Status:** CLEAN untuk happy-path — Preview→Commit→Monitoring(+Rollback) terverifikasi via `tests/flow_produksi_aps_test.py`.
- **Posting terverifikasi:**
  - Preview: run `preview` + proposal (WO qty 100 → line cap 200/hari, `scheduled=1`), **tanpa** menulis WO/assignment.
  - Commit: `rahaza_work_orders` target dates ter-set + 1 draft `rahaza_line_assignments` (`source='aps'`, `aps_run_id`) aktif; run `committed`.
  - Gantt: bar WO tampil di line + KPI (`total_wo`, `load_avg_pct`).
  - Reschedule (PATCH): tanggal WO ter-update.
  - Rollback: target date WO kembali (None seperti sebelum commit) + assignment `active=false`; run `rolled_back`.
  - SMV: override (1.5) set → get (source override) → delete (fallback derived).
- **Guardrail terverifikasi (5):** preview `to<from` (400), commit run-tidak-ada (404), commit run committed (400),
  rollback run non-committed (400), reschedule `end<start` (400).
- **DB pristine:** seed fixture ber-suffix unik + hard-cleanup (process/line/model/WO/run/assignment/smv).

## Temuan / Observasi
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| APS-01 | MED | Engine scheduler mengambil **SEMUA** WO berstatus `draft`/`released` secara global (filter status saja, bukan per-proses), sehingga `commit` dapat mengubah tanggal WO lain yang tidak dimaksud. POC mengisolasi dengan DB tanpa WO lain + fixture unik + rollback. Rekomendasi UX: tampilkan jelas daftar WO yang akan terpengaruh sebelum commit (dialog sudah menampilkan `proposals`/`unassigned`, pastikan planner meninjau). | NOTED (by design MVP) |
| APS-02 | LOW | `reschedule` memakai verb **PATCH** (`/api/rahaza/aps/wo/{wo_id}/reschedule`), bukan PUT. Pastikan klien memakai PATCH. | NOTED |
| APS-03 | LOW | `rollback` me-restore `target_start_date`/`target_end_date` WO dari `snapshots.before`, namun assignment hanya di-nonaktifkan (`active=false`, `rolled_back_by_run_id`) — tidak dihapus. Residu dokumen inactive bertambah seiring rollback (bukan bug fungsional). | NOTED |
| APS-04 | INFO | Kapasitas harian = `capacity_per_hour × 8` (shift 8 jam MVP); kalender/shift nyata direncanakan fase lanjutan. SMV bersifat informational pada MVP (tidak mengubah alokasi qty). | NOTED |
| APS-05 | INFO | WO tanpa target date diberi window sintetis 2 hari di Gantt (`is_synthetic_range=true`) untuk visualisasi; bukan jadwal riil. | NOTED |
| APS-06 | INFO | Modul `prod-aps-gantt` adalah redirect ke `production-dashboard` tab `schedule` (komponen `APSGanttModule` + `APSAutoScheduleDialog`). | NOTED |

## Bukti Uji
- `python3 tests/flow_produksi_aps_test.py` → **ALUR PENJADWALAN APS ALL PASS**
  (18 assertion PASS: seed → preview(scheduled=1) → commit(WO+assign) → gantt/runs/detail → reschedule → rollback(restore) → SMV; 5 guard 400/404; DB pristine).
- `python3 scripts/docgen/validate_flow.py --flow-id flow-produksi-aps` → **LULUS 10/10**.
- Grounding endpoint diverifikasi (F3): seluruh `/api/rahaza/aps/*` ter-*grounded* ke `rahaza_aps_scheduler.py` & `rahaza_aps.py`.
