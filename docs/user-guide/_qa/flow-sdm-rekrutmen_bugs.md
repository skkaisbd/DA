# QA / Bug Register — Flow Rekrutmen & Onboarding (`flow-sdm-rekrutmen`)

> Catatan QA terpisah dari materi training. Status alur: **Done** (POC backend ALL PASS, validator flow LULUS 10/10).

## Ringkasan
- **Status:** CLEAN untuk happy-path — Lamaran→Seleksi→Onboarding terverifikasi via `tests/flow_sdm_rekrutmen_test.py`.
- **Posting terverifikasi:**
  - Lamaran: lowongan `open` + kandidat `Lamaran Masuk` (timeline 1); `job.candidate_count=1`.
  - Seleksi: stage Screening CV→Interview HR→Interview User→Offering (timeline & `email_logs` mock bertambah), interview pass score 85, pipeline Offering=1.
  - Onboarding (auto saat Hired): `rahaza_employees` (kode `EMP-EP-2607-001`, `from_candidate_id` cocok) + `dewi_onboarding_checklists` (4 task) terbentuk; `job.hired_count=1`; 1 task done → progress 25%.
- **Guardrail terverifikasi (2):** lamar ke lowongan tidak ada (404), get kandidat tidak ada (404).
- **DB pristine:** hard-cleanup job + candidate + employee auto + checklist auto.

## Temuan / Observasi
| ID | Severity | Deskripsi | Status |
|---|---|---|---|
| REC-01 | LOW | Checklist onboarding yang dibuat OTOMATIS oleh `dewi_recruitment.py` (saat Hired) tidak menyetel `total_tasks`/`completed_tasks`/`progress_pct` saat insert (berbeda dgn `POST /api/dewi/onboarding/checklists` yang lengkap) dan memakai `started_at`+`due_day`, sedangkan modul onboarding memakai `start_date`+`due_date`. Akibatnya: (i) sebelum ada update task, field progres tidak ada; (ii) list `GET /checklists` yang sort by `start_date` dapat menaruh checklist auto di ujung. `update_task` tetap menghitung progres benar (menambahkan `progress_pct`/`completed_tasks`, namun `total_tasks` tidak diisi). Rekomendasi: seragamkan skema saat auto-create (isi `total_tasks`/`completed_tasks`/`progress_pct`/`start_date`). | NOTED (tidak memblokir happy-path) |
| REC-02 | INFO | Notifikasi email tiap tahap bersifat **MOCK** — disimpan di `candidate.email_logs` dengan `status='mock_sent'`, belum terkirim ke provider email nyata. Siap dihubungkan ke SMTP/provider. | NOTED |
| REC-03 | INFO | Auto-create employee mengambil `contract_type`/`start_date`/`salary` dari `candidate.offer` bila ada; bila kosong default `PKWT`/0. Set `offer` sebelum Hired untuk data kontrak lengkap. | NOTED |
| REC-04 | INFO | `DELETE /api/dewi/recruitment/jobs/{job_id}` melakukan cascade menghapus seluruh kandidat lowongan tsb. Hati-hati saat menghapus lowongan berjalan. | NOTED |
| REC-05 | INFO | Auto-provisioning idempoten: bila kandidat sudah punya `employee_id`, Hired ulang tidak membuat karyawan ganda. | NOTED |

## Bukti Uji
- `python3 tests/flow_sdm_rekrutmen_test.py` → **ALUR REKRUTMEN & ONBOARDING ALL PASS**
  (15 assertion PASS: job → guard 404 → candidate → guard 404 → count → Screening CV(email) → interview pass → Offering → pipeline → Hired(auto employee+checklist) → hired_count → checklist → task done 25%; DB pristine).
- `python3 scripts/docgen/validate_flow.py --flow-id flow-sdm-rekrutmen` → **LULUS 10/10**.
- Grounding endpoint diverifikasi (F3): seluruh `/api/dewi/recruitment/*` & `/api/dewi/onboarding/*` ter-*grounded* ke `dewi_recruitment.py` & `dewi_onboarding.py`.
