"""
POC / E2E API test — Flow SDM/Manajemen: KPI & OKR
==================================================
flow_id: flow-sdm-kpi-okr

Membuktikan happy-path + guardrail siklus manajemen kinerja:
  A. PERIODE KPI  : buat periode (draft) -> open (auto peer-assignment); status machine
  B. PENILAIAN    : bank soal 360, input Perform (single+bulk), form submission (guard),
                    fixture Attitude (self 360), Absensi otomatis
  C. REVIEW       : hitung KPI Final (Perform 60% + Attitude 20% + Absensi 20%, grade A-E),
                    lihat hasil, publish (completion<80 warning -> force finalize)
  D. OKR (Mgmt)   : Objective + Key Results (progress otomatis on_track/at_risk), dashboard
  + RBAC          : role non-HR (admin_gudang) ditolak 403 pada KPI & OKR.

Menjalankan:
    python3 tests/flow_sdm_kpi_okr_test.py

Self-cleanup: periode/perform/submission/results/badges + usul kenaikan gaji + soal POC +
objective/KR OKR yang dibuat skrip ini dihapus di blok finally. Data SEED tidak disentuh.
"""
import os
import sys
import uuid
import requests
from datetime import datetime, timezone

BASE = os.environ.get("POC_BASE_URL", "http://localhost:8001")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

TAG = uuid.uuid4().hex[:8]
S = requests.Session()    # admin (superadmin, HR-capable)
G = requests.Session()    # gudang (admin_gudang, non-HR)

st = {"passes": 0, "period_id": None, "period2_id": None,
      "emp1": None, "emp2": None, "q_ids": [], "obj_ids": []}


def ok(msg):
    st["passes"] += 1
    print(f"PASS {msg}")


def _db():
    from pymongo import MongoClient
    return MongoClient(MONGO_URL)[DB_NAME]


def _h(sess, tok):
    sess.headers.update({"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})


def logins():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status(); _h(S, r.json()["token"])
    r = G.post(f"{BASE}/api/auth/login", json={"email": "gudang@dewiaditya.id", "password": "Dewi@123"})
    r.raise_for_status(); _h(G, r.json()["token"])
    ok("login admin (HR-capable) + gudang (non-HR admin_gudang)")


def setup_employees():
    db = _db()
    emps = list(db.rahaza_employees.find({"active": True}, {"_id": 0, "id": 1, "name": 1}).limit(2))
    assert len(emps) >= 2, "butuh >=2 karyawan aktif di seed"
    st["emp1"] = emps[0]["id"]; st["emp2"] = emps[1]["id"]
    ok(f"setup: peserta emp1={emps[0]['name']} emp2={emps[1]['name']}")


# ── A. PERIODE ───────────────────────────────────────────────────────────────
def period_flow():
    body = {"name": f"KPI POC {TAG}", "period_from": "2026-01-01", "period_to": "2026-01-31",
            "working_days": 26, "participant_employee_ids": [st["emp1"], st["emp2"]]}
    r = S.post(f"{BASE}/api/dewi/kpi/periods", json=body)
    assert r.status_code == 200, f"create period {r.status_code}: {r.text}"
    p = r.json()["period"]; st["period_id"] = p["period_id"]
    assert p["status"] == "draft", p
    ok(f"periode: dibuat (draft) period={p['period_id'][:8]} peserta=2")

    # Guard: nama kosong -> 400
    r = S.post(f"{BASE}/api/dewi/kpi/periods", json={"name": ""})
    assert r.status_code == 400, f"expected 400 nama kosong, got {r.status_code}"
    ok("periode GUARD: nama kosong ditolak (400)")

    # Guard: transisi invalid draft->closed -> 400
    r = S.put(f"{BASE}/api/dewi/kpi/periods/{st['period_id']}", json={"status": "closed"})
    assert r.status_code == 400, f"expected 400 transisi invalid, got {r.status_code}: {r.text}"
    ok("periode GUARD: transisi draft->closed ditolak (400)")

    # GET list + detail
    r = S.get(f"{BASE}/api/dewi/kpi/periods")
    assert r.status_code == 200 and any(x["period_id"] == st["period_id"] for x in r.json()["periods"]), r.text
    r = S.get(f"{BASE}/api/dewi/kpi/periods/{st['period_id']}")
    assert r.status_code == 200, r.text
    ok("periode: list & detail OK")

    # Open (auto peer-assignment)
    r = S.put(f"{BASE}/api/dewi/kpi/periods/{st['period_id']}",
              json={"status": "open", "participant_employee_ids": [st["emp1"], st["emp2"]]})
    assert r.status_code == 200 and r.json()["period"]["status"] == "open", r.text
    ok("periode: transisi draft->open (auto peer-assignment)")

    # RBAC: gudang create -> 403
    r = G.post(f"{BASE}/api/dewi/kpi/periods", json={"name": "x"})
    assert r.status_code == 403, f"expected 403 non-HR, got {r.status_code}"
    ok("periode RBAC: role non-HR (admin_gudang) ditolak (403)")


# ── B. BANK SOAL + PENILAIAN ─────────────────────────────────────────────────
def questions_and_scoring():
    r = S.post(f"{BASE}/api/dewi/kpi/questions/seed-defaults", json={})
    assert r.status_code == 200, f"seed-defaults {r.status_code}: {r.text}"
    ok("bank soal: seed-defaults OK (idempoten)")

    # Guard: eval_type invalid -> 400
    r = S.post(f"{BASE}/api/dewi/kpi/questions", json={"eval_type": "invalid", "category": "c", "question_text": "q"})
    assert r.status_code == 400, f"expected 400 eval_type, got {r.status_code}"
    ok("bank soal GUARD: eval_type invalid ditolak (400)")

    r = S.get(f"{BASE}/api/dewi/kpi/questions", params={"eval_type": "self"})
    assert r.status_code == 200, r.text
    ok(f"bank soal: list self questions (n={len(r.json()['questions'])})")

    # Buat 2 soal self POC (untuk fixture attitude)
    for i in (1, 2):
        r = S.post(f"{BASE}/api/dewi/kpi/questions", json={
            "eval_type": "self", "category": f"POC Self {TAG}", "category_weight": 0.10,
            "question_text": f"Pernyataan POC {TAG} #{i}", "order": 90 + i})
        assert r.status_code == 200, r.text
        st["q_ids"].append(r.json()["question"]["question_id"])
    ok("bank soal: 2 soal self POC dibuat (fixture attitude)")

    # Perform (items mode) -> weighted 90
    r = S.put(f"{BASE}/api/dewi/kpi/perform/{st['period_id']}/{st['emp1']}",
              json={"items": [{"score": 90, "weight": 1}, {"score": 90, "weight": 1}], "notes": "POC"})
    assert r.status_code == 200 and r.json()["perform"]["perform_score"] == 90.0, r.text
    ok("penilaian: Perform emp1 (items mode) = 90.0")

    # Perform (bulk)
    r = S.post(f"{BASE}/api/dewi/kpi/perform/{st['period_id']}/bulk",
               json={"scores": [{"employee_id": st["emp1"], "perform_score": 90, "notes": "bulk POC"}]})
    assert r.status_code == 200 and r.json()["saved"] == 1, r.text
    ok("penilaian: Perform bulk saved=1")

    # Guard: submissions dengan skor di luar rentang 1-5 -> 400
    r = S.post(f"{BASE}/api/dewi/kpi/submissions",
               json={"period_id": st["period_id"], "eval_type": "self", "evaluatee_id": st["emp1"],
                     "answers": [{"question_id": st["q_ids"][0], "score": 9}]})
    assert r.status_code == 400, f"expected 400 skor di luar 1-5, got {r.status_code}: {r.text}"
    ok("penilaian GUARD: submission skor di luar rentang 1-5 ditolak (400)")

    r = S.get(f"{BASE}/api/dewi/kpi/perform/{st['period_id']}")
    assert r.status_code == 200 and any(x["employee_id"] == st["emp1"] for x in r.json()["perform_scores"]), r.text
    ok("penilaian: list Perform periode OK")

    # Fixture Attitude: submission self (submitted) untuk emp1 -> attitude 100
    db = _db()
    now = datetime.now(timezone.utc)
    db.da_kpi_submissions.insert_one({
        "submission_id": str(uuid.uuid4()), "period_id": st["period_id"],
        "eval_type": "self", "evaluator_id": st["emp1"], "evaluatee_id": st["emp1"],
        "answers": [{"question_id": q, "score": 5} for q in st["q_ids"]],
        "status": "submitted", "is_anonymous": False,
        "created_at": now, "updated_at": now, "submitted_at": now,
    })
    ok("penilaian: fixture Attitude self (skor 5) tersimpan")


# ── C. REVIEW (hitung + publish) ─────────────────────────────────────────────
def review_flow():
    # Guard: calculate pada periode tanpa peserta -> 400
    r = S.post(f"{BASE}/api/dewi/kpi/periods", json={"name": f"KPI Kosong {TAG}"})
    st["period2_id"] = r.json()["period"]["period_id"]
    r = S.post(f"{BASE}/api/dewi/kpi/results/{st['period2_id']}/calculate", json={})
    assert r.status_code == 400, f"expected 400 no participant, got {r.status_code}"
    ok("review GUARD: calculate periode tanpa peserta ditolak (400)")
    # delete periode kosong (draft) via API
    r = S.delete(f"{BASE}/api/dewi/kpi/periods/{st['period2_id']}")
    assert r.status_code == 200, r.text
    st["period2_id"] = None
    ok("review: hapus periode draft kosong (200)")

    # Calculate P1
    r = S.post(f"{BASE}/api/dewi/kpi/results/{st['period_id']}/calculate", json={})
    assert r.status_code == 200 and r.json()["calculated"] == 2, r.text
    res = {x["employee_id"]: x for x in r.json()["results"]}
    r1 = res[st["emp1"]]
    assert r1["perform_score"] == 90.0 and r1["attitude_score"] == 100.0 and r1["absensi_score"] == 100.0, r1
    assert r1["kpi_final"] == 94.0 and r1["grade"] == "A", f"expected KPI 94 grade A: {r1}"
    assert res[st["emp2"]]["kpi_final"] is None, "emp2 harus None (data belum lengkap)"
    ok(f"review: KPI Final emp1 = 94.0 (Perform90*0.6 + Att100*0.2 + Abs100*0.2) grade A")

    r = S.get(f"{BASE}/api/dewi/kpi/results/{st['period_id']}")
    assert r.status_code == 200 and len(r.json()["results"]) == 2, r.text
    ok("review: list hasil periode (2 hasil)")

    # Publish tanpa force -> warning completion 50% (1/2 final)
    r = S.post(f"{BASE}/api/dewi/kpi/results/{st['period_id']}/publish", json={})
    assert r.status_code == 200 and r.json().get("ok") is False and r.json().get("warning") is True, r.text
    assert r.json()["completion_pct"] == 50.0, r.json()
    ok("review GUARD: publish completion<80% -> warning (50%)")

    # Publish force -> finalized
    r = S.post(f"{BASE}/api/dewi/kpi/results/{st['period_id']}/publish", json={"force": True})
    assert r.status_code == 200 and r.json().get("ok") is True and r.json()["published"] >= 1, r.text
    ok(f"review: publish force -> published={r.json()['published']} (badges/raise dihitung)")

    r = S.get(f"{BASE}/api/dewi/kpi/periods/{st['period_id']}")
    assert r.status_code == 200 and r.json()["period"]["status"] == "finalized", r.text
    ok("review: periode berstatus finalized setelah publish")


# ── D. OKR (Manajemen) ───────────────────────────────────────────────────────
def okr_flow():
    r = S.post(f"{BASE}/api/management/okr/objectives", json={
        "title": f"Tingkatkan OTIF {TAG}", "period": "2026-Q1", "department": "Manajemen",
        "priority": "high", "key_results": [
            {"title": "OTIF ke 95%", "metric_type": "percentage", "target_value": 95, "current_value": 66.5, "unit": "%"}
        ]})
    assert r.status_code == 200 and r.json()["success"], f"create objective {r.status_code}: {r.text}"
    obj = r.json()["data"]; st["obj_ids"].append(obj["id"])
    assert obj["progress"] == 70.0 and obj["health"] == "on_track", f"progress/health salah: {obj}"
    ok(f"OKR: Objective + KR dibuat, progress=70% health=on_track")

    r = S.get(f"{BASE}/api/management/okr/objectives")
    assert r.status_code == 200 and any(o["id"] == obj["id"] for o in r.json()["data"]), r.text
    ok("OKR: list objectives OK")

    # Tambah KR kedua (progress rendah) -> objective jadi at_risk
    r = S.post(f"{BASE}/api/management/okr/objectives/{obj['id']}/key-results",
               json={"title": "Kurangi komplain", "metric_type": "number", "target_value": 100, "current_value": 20})
    assert r.status_code == 200, r.text
    kr2 = r.json()["data"]
    r = S.get(f"{BASE}/api/management/okr/objectives/{obj['id']}")
    assert r.status_code == 200 and r.json()["data"]["progress"] == 45.0 and r.json()["data"]["health"] == "at_risk", r.json()["data"]
    ok("OKR: tambah KR -> progress avg 45% health=at_risk")

    # Update KR2 current -> 100 (progress naik): avg(70, 100) = 85.0
    r = S.patch(f"{BASE}/api/management/okr/key-results/{kr2['id']}", json={"current_value": 100})
    assert r.status_code == 200, r.text
    r = S.get(f"{BASE}/api/management/okr/objectives/{obj['id']}")
    assert r.json()["data"]["progress"] == 85.0, r.json()["data"]
    ok("OKR: update KR current -> progress 85.0% (avg KR1 70% + KR2 100%)")

    r = S.get(f"{BASE}/api/management/okr/dashboard")
    assert r.status_code == 200 and r.json()["data"]["total_objectives"] >= 1, r.text
    ok(f"OKR: dashboard OKR health (total_objectives={r.json()['data']['total_objectives']})")

    # RBAC: gudang create objective -> 403
    r = G.post(f"{BASE}/api/management/okr/objectives", json={"title": "x", "period": "2026-Q1"})
    assert r.status_code == 403, f"expected 403 non-mgmt, got {r.status_code}"
    ok("OKR RBAC: role non-Manajemen ditolak (403)")


def cleanup():
    try:
        db = _db()
    except Exception as e:  # pragma: no cover
        print(f"WARN cleanup skip (pymongo): {e}")
        return
    pids = [p for p in [st["period_id"], st["period2_id"]] if p]
    for pid in pids:
        db.da_kpi_periods.delete_many({"period_id": pid})
        db.da_kpi_perform.delete_many({"period_id": pid})
        db.da_kpi_submissions.delete_many({"period_id": pid})
        db.da_kpi_results.delete_many({"period_id": pid})
        db.da_kpi_badges.delete_many({"period_id": pid})
        db.rahaza_salary_adjustments.delete_many({"kpi_period_id": pid})
    if st["q_ids"]:
        db.da_kpi_questions.delete_many({"question_id": {"$in": st["q_ids"]}})
    for oid in st["obj_ids"]:
        db.rahaza_okr_objectives.delete_many({"id": oid})
        db.rahaza_okr_key_results.delete_many({"objective_id": oid})
    print("CLEANUP: periode/perform/submission/results/badges + usul-gaji + soal POC + OKR dihapus — SEED utuh.")


def main():
    try:
        logins()
        setup_employees()
        period_flow()
        questions_and_scoring()
        review_flow()
        okr_flow()
        print(f"\n=== KPI/OKR FLOW: ALL PASS ({st['passes']} assertions) ===")
    finally:
        cleanup()


if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        sys.exit(2)
