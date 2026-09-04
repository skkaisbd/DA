"""
E2E API-level POC test — Alur Rekrutmen & Onboarding (SDM/HRIS / CV. Dewi Aditya ATS).

Alur bisnis: Lamaran -> Seleksi -> Onboarding.

Happy path:
  login
  --- FASE 1: LAMARAN ----------------------------------------------------------
  -> buat lowongan (job)                          [POST /api/dewi/recruitment/jobs]
  -> kandidat melamar (stage=Lamaran Masuk)       [POST /api/dewi/recruitment/candidates]
  -> detail kandidat + job candidate_count        [GET  .../candidates/{id} & .../jobs/{id}]
  --- FASE 2: SELEKSI ----------------------------------------------------------
  -> pindah stage (Screening CV) + email mock     [PUT  .../candidates/{id}]
  -> jadwalkan interview + input hasil            [POST/PUT .../candidates/{id}/interviews...]
  -> lanjut Interview HR -> User -> Offering       [PUT  .../candidates/{id}]
  -> pipeline kanban                              [GET  .../pipeline]
  --- FASE 3: ONBOARDING (auto saat Hired) -------------------------------------
  -> set stage Hired -> auto buat employee + checklist onboarding
  -> ambil checklist (by employee_id)             [GET  /api/dewi/onboarding/checklists]
  -> tandai 1 task selesai -> progress naik        [PUT  .../onboarding/checklists/{id}/tasks/{task_id}]
  -> verifikasi employee & job.hired_count
Guards:
  -> lamar ke job tidak ada ditolak (404)
  -> get kandidat tidak ada (404)
Self-cleanup (hard): hapus job + kandidat + employee auto + checklist auto (DB pristine).
"""
import sys
import uuid
import requests

BASE = "http://localhost:8001"
S = requests.Session()
SFX = uuid.uuid4().hex[:6].upper()
st = {"job_id": None, "cand_id": None, "iv_id": None, "emp_id": None, "checklist_id": None}


def _mongo():
    url = db = None
    with open("/app/backend/.env") as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith("MONGO_URL="):
                url = ln.split("=", 1)[1].strip().strip('"').strip("'")
            elif ln.startswith("DB_NAME="):
                db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    from pymongo import MongoClient
    cli = MongoClient(url)
    return cli, cli[db or "test_database"]


def login():
    r = S.post(f"{BASE}/api/auth/login",
               json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}",
                      "Content-Type": "application/json"})
    print("PASS login")


def _put_stage(stage):
    r = S.put(f"{BASE}/api/dewi/recruitment/candidates/{st['cand_id']}",
              json={"stage": stage, "stage_note": f"E2E -> {stage}"})
    assert r.status_code == 200, f"stage->{stage} {r.status_code}: {r.text}"
    return r.json()["candidate"]


def main():
    login()

    # ═══════════ FASE 1 — LAMARAN ═════════════════════════════════════════════
    r = S.post(f"{BASE}/api/dewi/recruitment/jobs", json={
        "title": f"E2E QC Inspector {SFX}", "department": "Quality Control",
        "level": "Staff", "headcount": 1, "salary_min": 3000000, "salary_max": 4500000,
        "requirements": ["Teliti", "D3"], "status": "open",
    })
    assert r.status_code == 200 and r.json()["ok"], f"create job {r.status_code}: {r.text}"
    st["job_id"] = r.json()["job"]["job_id"]
    print(f"PASS buat lowongan job_id={st['job_id'][:8]} status=open")

    # Guard: lamar ke job tidak ada
    rg = S.post(f"{BASE}/api/dewi/recruitment/candidates",
                json={"job_id": "no-such-job", "name": "X"})
    assert rg.status_code == 404, f"expected 404 job-not-found got {rg.status_code}"
    print("PASS guard: lamar ke lowongan tidak ada ditolak (404)")

    r = S.post(f"{BASE}/api/dewi/recruitment/candidates", json={
        "job_id": st["job_id"], "job_title": f"E2E QC Inspector {SFX}",
        "name": f"E2E Pelamar {SFX}", "email": f"e2e.{SFX.lower()}@test.local",
        "phone": "0812", "education": "D3", "experience_years": 2, "source": "Jobstreet",
    })
    assert r.status_code == 200, f"add candidate {r.status_code}: {r.text}"
    cand = r.json()["candidate"]
    st["cand_id"] = cand["candidate_id"]
    assert cand["stage"] == "Lamaran Masuk" and len(cand["timeline"]) == 1, f"cand awal {cand}"
    print(f"PASS kandidat melamar cand_id={st['cand_id'][:8]} stage=Lamaran Masuk (timeline 1)")

    # Guard: get kandidat tidak ada
    rg = S.get(f"{BASE}/api/dewi/recruitment/candidates/no-such-cand")
    assert rg.status_code == 404, f"expected 404 got {rg.status_code}"
    print("PASS guard: get kandidat tidak ada ditolak (404)")

    r = S.get(f"{BASE}/api/dewi/recruitment/jobs/{st['job_id']}")
    assert r.status_code == 200 and r.json()["job"]["candidate_count"] == 1, f"job detail {r.text}"
    print("PASS job.candidate_count = 1 (setelah lamaran)")

    # ═══════════ FASE 2 — SELEKSI ═════════════════════════════════════════════
    c = _put_stage("Screening CV")
    assert c["stage"] == "Screening CV" and len(c["timeline"]) == 2, f"screening {c}"
    assert any(e["stage"] == "Screening CV" for e in c.get("email_logs", [])), "email mock Screening CV tidak tercatat"
    print("PASS seleksi: stage->Screening CV (timeline 2 + email mock terkirim)")

    r = S.post(f"{BASE}/api/dewi/recruitment/candidates/{st['cand_id']}/interviews", json={
        "type": "HR Interview", "interviewer": "HR Manager", "mode": "Video Call",
        "scheduled_at": "2026-07-10 10:00",
    })
    assert r.status_code == 200, f"add interview {r.status_code}: {r.text}"
    st["iv_id"] = r.json()["interview"]["interview_id"]
    r = S.put(f"{BASE}/api/dewi/recruitment/candidates/{st['cand_id']}/interviews/{st['iv_id']}",
              json={"status": "done", "result": "pass", "score": 85, "notes": "bagus"})
    assert r.status_code == 200, f"update interview {r.status_code}: {r.text}"
    print("PASS seleksi: interview dijadwalkan + hasil pass (score 85)")

    for stg in ("Interview HR", "Interview User", "Offering"):
        c = _put_stage(stg)
        assert c["stage"] == stg, f"stage {stg} {c}"
    print("PASS seleksi: stage lanjut Interview HR -> Interview User -> Offering")

    r = S.get(f"{BASE}/api/dewi/recruitment/pipeline", params={"job_id": st["job_id"]})
    assert r.status_code == 200, f"pipeline {r.status_code}: {r.text}"
    pipe = r.json()["pipeline"]
    assert pipe["Offering"]["count"] == 1, f"pipeline Offering count {pipe['Offering']}"
    print("PASS seleksi: pipeline kanban (Offering=1)")

    # ═══════════ FASE 3 — ONBOARDING (auto saat Hired) ═══════════════════════
    c = _put_stage("Hired")
    assert c["stage"] == "Hired", f"hired {c}"
    st["emp_id"] = c.get("employee_id")
    st["checklist_id"] = c.get("onboarding_checklist_id")
    assert st["emp_id"], "auto-create employee gagal (employee_id kosong)"
    assert st["checklist_id"], "auto-create onboarding checklist gagal (checklist_id kosong)"
    print(f"PASS Hired => auto employee={st['emp_id'][:8]} + checklist={st['checklist_id'][:8]}")

    # Verifikasi employee & job.hired_count via DB + API
    cli, db = _mongo()
    emp = db.rahaza_employees.find_one({"id": st["emp_id"]}, {"_id": 0})
    cli.close()
    assert emp and emp.get("from_candidate_id") == st["cand_id"], f"employee auto tidak sesuai: {emp}"
    print(f"PASS verifikasi employee auto (code={emp.get('employee_code')}, from_candidate_id cocok)")

    r = S.get(f"{BASE}/api/dewi/recruitment/jobs/{st['job_id']}")
    assert r.json()["job"]["hired_count"] == 1, f"hired_count {r.json()['job']}"
    print("PASS job.hired_count = 1")

    # Ambil checklist onboarding (by employee_id) + detail
    r = S.get(f"{BASE}/api/dewi/onboarding/checklists", params={"employee_id": st["emp_id"]})
    assert r.status_code == 200 and any(cl["checklist_id"] == st["checklist_id"] for cl in r.json()["checklists"]), \
        f"checklist by employee_id tidak ditemukan: {r.text[:300]}"
    r = S.get(f"{BASE}/api/dewi/onboarding/checklists/{st['checklist_id']}")
    assert r.status_code == 200, f"checklist detail {r.status_code}: {r.text}"
    cl = r.json()["checklist"]
    tasks = cl.get("tasks", [])
    assert len(tasks) >= 1, f"checklist tanpa task: {cl}"
    print(f"PASS onboarding: checklist ter-ambil ({len(tasks)} task, status={cl.get('status')})")

    # Tandai 1 task selesai -> progress naik
    tid = tasks[0]["task_id"]
    r = S.put(f"{BASE}/api/dewi/onboarding/checklists/{st['checklist_id']}/tasks/{tid}",
              json={"status": "done", "notes": "selesai E2E"})
    assert r.status_code == 200, f"update task {r.status_code}: {r.text}"
    cl2 = r.json()["checklist"]
    assert cl2["progress_pct"] > 0 and cl2["completed_tasks"] >= 1, f"progress tidak naik: {cl2}"
    _total = cl2.get("total_tasks") or len(cl2.get("tasks", []))
    print(f"PASS onboarding: 1 task selesai => progress {cl2['progress_pct']}% ({cl2['completed_tasks']}/{_total})")

    print("\n=== ALUR REKRUTMEN & ONBOARDING ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        n_j = db.dewi_recruitment_jobs.delete_many({"job_id": st["job_id"]}).deleted_count if st["job_id"] else 0
        n_c = db.dewi_recruitment_candidates.delete_many(
            {"candidate_id": st["cand_id"]}).deleted_count if st["cand_id"] else 0
        n_e = n_cl = 0
        if st["cand_id"]:
            n_e = db.rahaza_employees.delete_many({"from_candidate_id": st["cand_id"]}).deleted_count
            n_cl = db.dewi_onboarding_checklists.delete_many({"from_candidate_id": st["cand_id"]}).deleted_count
        if st["checklist_id"]:
            n_cl += db.dewi_onboarding_checklists.delete_many({"checklist_id": st["checklist_id"]}).deleted_count
        cli.close()
        print(f"CLEANUP: job={n_j} candidate={n_c} employee={n_e} checklist={n_cl} dihapus (DB pristine)")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
