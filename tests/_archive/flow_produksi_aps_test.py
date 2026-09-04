"""
E2E API-level POC test — Alur Penjadwalan APS (Portal Produksi / PT Rahaza).

Alur bisnis: Preview schedule -> Commit -> Monitoring (+ Rollback).

Fixtures (di-seed langsung ke Mongo, ditandai unik & di-hard-cleanup):
  - 1 process (final, non-rework) + 1 line (kapasitas) + 1 model + 1 work order (released).

Happy path:
  login (planner)
  --- FASE 1: PREVIEW ----------------------------------------------------------
  -> POST /api/rahaza/aps/auto-schedule/preview  -> run 'preview' + proposal (WO ter-jadwal ke line)
  --- FASE 2: COMMIT -----------------------------------------------------------
  -> POST /api/rahaza/aps/auto-schedule/commit    -> WO target dates ter-set + line_assignments (draft/aps)
  --- FASE 3: MONITORING -------------------------------------------------------
  -> GET  /api/rahaza/aps/gantt                    -> bars + kpis (WO tampil di line)
  -> GET  /api/rahaza/aps/auto-schedule/runs       -> histori run + kpis
  -> GET  /api/rahaza/aps/auto-schedule/runs/{id}  -> detail run committed
  -> GET  /api/rahaza/aps/wo/{wo_id}               -> detail WO + progress breakdown + risk
  -> PATCH /api/rahaza/aps/wo/{wo_id}/reschedule   -> reschedule manual
  --- ROLLBACK -----------------------------------------------------------------
  -> POST /api/rahaza/aps/auto-schedule/rollback   -> WO dates dikembalikan + assignment non-aktif
  --- SMV (pendukung) ----------------------------------------------------------
  -> PUT/GET/DELETE /api/rahaza/aps/smv[/override]

Guards:
  -> preview rentang tanggal to<from ditolak (400)
  -> commit run tidak ada ditolak (404)
  -> commit run yang sudah committed ditolak (400)
  -> rollback run yang sudah rolled_back ditolak (400)
  -> reschedule end<start ditolak (400)

Self-cleanup (hard): hapus process/line/model/WO + run + assignments (aps_run_id) + smv_cache uji.
"""
import sys
import uuid
from datetime import datetime, timezone, date, timedelta
import requests

BASE = "http://localhost:8001"
S = requests.Session()

SFX = uuid.uuid4().hex[:6].upper()
IDS = {
    "process_id": str(uuid.uuid4()),
    "line_id": str(uuid.uuid4()),
    "model_id": str(uuid.uuid4()),
    "wo_id": str(uuid.uuid4()),
    "run_id": None,
}


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
    print("PASS login (planner=superadmin)")


def seed():
    cli, db = _mongo()
    now = datetime.now(timezone.utc)
    db.rahaza_processes.insert_one({
        "id": IDS["process_id"], "code": f"E2E-APS-PROC-{SFX}", "name": "E2E APS Final Proc",
        "order_seq": 999, "is_rework": False, "active": True, "created_at": now,
    })
    db.rahaza_lines.insert_one({
        "id": IDS["line_id"], "code": f"E2E-APS-LINE-{SFX}", "name": "E2E APS Line",
        "process_id": IDS["process_id"], "capacity_per_hour": 25, "active": True, "created_at": now,
    })
    db.rahaza_models.insert_one({
        "id": IDS["model_id"], "code": f"E2E-APS-MODEL-{SFX}", "name": "E2E APS Model",
        "active": True, "created_at": now,
    })
    db.rahaza_work_orders.insert_one({
        "id": IDS["wo_id"], "wo_number": f"E2E-APS-WO-{SFX}", "status": "released",
        "qty": 100, "completed_qty": 0, "priority": "normal",
        "model_id": IDS["model_id"], "size_id": None,
        "target_start_date": None, "target_end_date": None, "created_at": now,
    })
    cli.close()
    print(f"SEED: process/line/model/WO uji (SFX={SFX}) dibuat")


def main():
    login()
    seed()

    frm = date.today().isoformat()
    to = (date.today() + timedelta(days=14)).isoformat()

    # Guard: preview to<from
    rg = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/preview",
                json={"from": to, "to": frm, "process_id": IDS["process_id"]})
    assert rg.status_code == 400, f"expected 400 to<from got {rg.status_code}: {rg.text}"
    print("PASS guard: preview rentang to<from ditolak (400)")

    # ═══════════ FASE 1 — PREVIEW ═════════════════════════════════════════════
    r = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/preview",
               json={"from": frm, "to": to, "process_id": IDS["process_id"]})
    assert r.status_code == 200, f"preview {r.status_code}: {r.text}"
    run = r.json()
    IDS["run_id"] = run["id"]
    assert run["status"] == "preview", f"run status {run}"
    prop = run["proposal"]
    mine = [p for p in prop["proposals"] if p["wo_id"] == IDS["wo_id"]]
    assert mine, f"WO uji tidak terjadwal di proposal: {prop['proposals']}"
    assert mine[0]["line_id"] == IDS["line_id"], f"WO tidak ke line uji: {mine[0]}"
    assert prop["kpis"]["scheduled"] >= 1, f"kpis {prop['kpis']}"
    print(f"PASS preview run={IDS['run_id'][:8]} status=preview "
          f"(scheduled={prop['kpis']['scheduled']}, WO->line uji, start={mine[0]['start_date']})")

    # ═══════════ FASE 2 — COMMIT ══════════════════════════════════════════════
    # Guard: commit run tidak ada
    rg = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/commit", json={"run_id": "no-such-run"})
    assert rg.status_code == 404, f"expected 404 got {rg.status_code}"
    print("PASS guard: commit run tidak ada ditolak (404)")

    r = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/commit", json={"run_id": IDS["run_id"]})
    assert r.status_code == 200, f"commit {r.status_code}: {r.text}"
    cm = r.json()
    assert cm["ok"] and cm["applied_wo_count"] >= 1 and cm["created_assignment_count"] >= 1, f"commit result {cm}"
    assert cm["run"]["status"] == "committed", f"run status {cm['run']['status']}"
    print(f"PASS commit => WO ter-update ({cm['applied_wo_count']}) + assignment dibuat "
          f"({cm['created_assignment_count']}), run=committed")

    # Verifikasi WO target dates ter-set + assignment aktif (DB)
    cli, db = _mongo()
    wo = db.rahaza_work_orders.find_one({"id": IDS["wo_id"]}, {"_id": 0})
    assert wo["target_start_date"] and wo["target_end_date"], f"WO dates belum ter-set: {wo}"
    n_assign = db.rahaza_line_assignments.count_documents(
        {"aps_run_id": IDS["run_id"], "active": True, "source": "aps"})
    cli.close()
    assert n_assign >= 1, "assignment aps aktif tidak tercatat"
    print(f"PASS verifikasi DB: WO target dates ter-set + {n_assign} assignment aps aktif")

    # Guard: commit ulang (run sudah committed)
    rg = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/commit", json={"run_id": IDS["run_id"]})
    assert rg.status_code == 400, f"expected 400 re-commit got {rg.status_code}"
    print("PASS guard: commit run yang sudah committed ditolak (400)")

    # ═══════════ FASE 3 — MONITORING ═════════════════════════════════════════
    r = S.get(f"{BASE}/api/rahaza/aps/gantt",
              params={"from": frm, "to": to, "process_id": IDS["process_id"]})
    assert r.status_code == 200, f"gantt {r.status_code}: {r.text}"
    g = r.json()
    bar = next((b for b in g["bars"] if b["wo_id"] == IDS["wo_id"]), None)
    assert bar and bar["line_id"] == IDS["line_id"], f"bar WO uji tidak ada di gantt: {g['bars']}"
    assert "kpis" in g and "load_avg_pct" in g["kpis"], f"gantt kpis {g.get('kpis')}"
    print(f"PASS monitoring gantt: bar WO uji tampil di line (risk={bar['risk']}, "
          f"total_wo={g['kpis']['total_wo']}, load_avg={g['kpis']['load_avg_pct']}%)")

    r = S.get(f"{BASE}/api/rahaza/aps/auto-schedule/runs", params={"limit": 20})
    assert r.status_code == 200, f"runs {r.status_code}: {r.text}"
    assert any(x["id"] == IDS["run_id"] for x in r.json()), "run uji tidak ada di histori"
    print("PASS monitoring histori runs: run uji tercantum + kpis")

    r = S.get(f"{BASE}/api/rahaza/aps/auto-schedule/runs/{IDS['run_id']}")
    assert r.status_code == 200 and r.json()["status"] == "committed", f"run detail {r.status_code}: {r.text}"
    print("PASS monitoring detail run: status=committed")

    r = S.get(f"{BASE}/api/rahaza/aps/wo/{IDS['wo_id']}")
    assert r.status_code == 200, f"wo detail {r.status_code}: {r.text}"
    wod = r.json()
    assert wod["work_order"]["id"] == IDS["wo_id"] and "progress_breakdown" in wod and "risk" in wod, f"wo detail {wod}"
    print(f"PASS monitoring detail WO: progress={wod['work_order']['progress_pct']}% risk={wod['risk']}")

    # Reschedule manual + guard
    ns = (date.today() + timedelta(days=2)).isoformat()
    ne = (date.today() + timedelta(days=6)).isoformat()
    rg = S.patch(f"{BASE}/api/rahaza/aps/wo/{IDS['wo_id']}/reschedule",
                 json={"target_start_date": ne, "target_end_date": ns})
    assert rg.status_code == 400, f"expected 400 end<start got {rg.status_code}"
    print("PASS guard: reschedule end<start ditolak (400)")

    r = S.patch(f"{BASE}/api/rahaza/aps/wo/{IDS['wo_id']}/reschedule",
                json={"target_start_date": ns, "target_end_date": ne})
    assert r.status_code == 200 and r.json()["work_order"]["target_start_date"] == ns, f"reschedule {r.status_code}: {r.text}"
    print("PASS monitoring reschedule manual WO (PATCH) => tanggal ter-update")

    # ═══════════ ROLLBACK ═════════════════════════════════════════════════════
    r = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/rollback", json={"run_id": IDS["run_id"]})
    assert r.status_code == 200, f"rollback {r.status_code}: {r.text}"
    rb = r.json()
    assert rb["ok"] and rb["restored_wo_count"] >= 1 and rb["deactivated_assignments_count"] >= 1, f"rollback {rb}"
    print(f"PASS rollback => WO dikembalikan ({rb['restored_wo_count']}) + "
          f"assignment non-aktif ({rb['deactivated_assignments_count']}), run=rolled_back")

    # Verifikasi restore (WO dates kembali None seperti sebelum commit) + assignment inactive
    cli, db = _mongo()
    wo2 = db.rahaza_work_orders.find_one({"id": IDS["wo_id"]}, {"_id": 0})
    n_active = db.rahaza_line_assignments.count_documents({"aps_run_id": IDS["run_id"], "active": True})
    cli.close()
    assert wo2["target_start_date"] is None and wo2["target_end_date"] is None, f"WO dates tidak ter-restore: {wo2}"
    assert n_active == 0, f"masih ada assignment aktif setelah rollback: {n_active}"
    print("PASS verifikasi rollback: WO dates ter-restore (None) + 0 assignment aktif")

    # Guard: rollback ulang (run sudah rolled_back)
    rg = S.post(f"{BASE}/api/rahaza/aps/auto-schedule/rollback", json={"run_id": IDS["run_id"]})
    assert rg.status_code == 400, f"expected 400 re-rollback got {rg.status_code}"
    print("PASS guard: rollback run yang sudah rolled_back ditolak (400)")

    # ═══════════ SMV (pendukung) ══════════════════════════════════════════════
    r = S.put(f"{BASE}/api/rahaza/aps/smv/override",
              json={"model_id": IDS["model_id"], "process_id": IDS["process_id"], "smv_minutes_per_unit": 1.5})
    assert r.status_code == 200 and r.json()["source"] == "override", f"smv override {r.status_code}: {r.text}"
    r = S.get(f"{BASE}/api/rahaza/aps/smv",
              params={"model_id": IDS["model_id"], "process_id": IDS["process_id"]})
    assert r.status_code == 200 and r.json()["source"] == "override" and r.json()["smv_minutes_per_unit"] == 1.5, \
        f"smv get {r.status_code}: {r.text}"
    r = S.delete(f"{BASE}/api/rahaza/aps/smv/override",
                 json={"model_id": IDS["model_id"], "process_id": IDS["process_id"]})
    assert r.status_code == 200 and r.json()["deleted"] >= 1, f"smv delete {r.status_code}: {r.text}"
    print("PASS SMV override set -> get (override 1.5) -> delete (fallback derived)")

    print("\n=== ALUR PENJADWALAN APS ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        n_p = db.rahaza_processes.delete_many({"id": IDS["process_id"]}).deleted_count
        n_l = db.rahaza_lines.delete_many({"id": IDS["line_id"]}).deleted_count
        n_m = db.rahaza_models.delete_many({"id": IDS["model_id"]}).deleted_count
        n_w = db.rahaza_work_orders.delete_many({"id": IDS["wo_id"]}).deleted_count
        n_r = db.rahaza_aps_schedule_runs.delete_many(
            {"id": IDS["run_id"]}).deleted_count if IDS["run_id"] else 0
        n_a = db.rahaza_line_assignments.delete_many(
            {"aps_run_id": IDS["run_id"]}).deleted_count if IDS["run_id"] else 0
        n_s = db.rahaza_smv_cache.delete_many({"model_id": IDS["model_id"]}).deleted_count
        cli.close()
        print(f"CLEANUP: proc={n_p} line={n_l} model={n_m} wo={n_w} run={n_r} "
              f"assign={n_a} smv={n_s} dihapus (DB pristine)")
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
