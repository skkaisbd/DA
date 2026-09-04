"""
E2E API-level POC test — Alur QC / Rework (Eksekusi Lantai / prod-exec-hub).

Model: setiap piece mengalir per LINE melalui proses. Hasil hulu dicatat OUTPUT,
di QC dipilah pass/fail; qc_fail masuk PAPAN REWORK; di rework dipilah lanjut/scrap;
yang lolos (qc_pass + rework_pass) menuju PACKING.

Happy path:
  login
  -> buat fixture line                                    [POST /api/rahaza/lines]
  -> ambil process_id FINISHING/QC/PACKING                [GET  /api/rahaza/execution/process/{code}/board]
  -> OUTPUT finishing (quick-output)                      [POST /api/rahaza/execution/quick-output]
  -> QC event pass=80 fail=20                             [POST /api/rahaza/execution/qc-event]
  -> REWORK event in=20 out=15 fail=5                     [POST /api/rahaza/execution/rework-event]
  -> PACKING output=95 (quick-output PACKING)             [POST /api/rahaza/execution/quick-output]
  -> flow-summary: qc_pass=80, qc_fail=20, packing=95     [GET  /api/rahaza/execution/flow-summary]
  -> board QC + recent-events                             [GET  .../board, /api/rahaza/execution/recent-events]
Guards:
  -> quick-output pada proses QC ditolak (400) -> harus qc-event
  -> qc-event tanpa qty_pass/qty_fail ditolak (400)
  -> rework-event qty_out+qty_fail > qty_in ditolak (400)
Self-cleanup (hard): hapus semua rahaza_wip_events (line_id fixture) + fixture line.
"""
import os
import sys
import requests

BASE = "http://localhost:8001"
S = requests.Session()
st = {"line_id": None, "proc": {}}


# ── util: baca MONGO_URL dari backend/.env untuk hard-cleanup ──────────────────
def _mongo_cfg():
    url = db = None
    try:
        with open("/app/backend/.env") as f:
            for ln in f:
                ln = ln.strip()
                if ln.startswith("MONGO_URL="):
                    url = ln.split("=", 1)[1].strip().strip('"').strip("'")
                elif ln.startswith("DB_NAME="):
                    db = ln.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return url, (db or "test_database")


def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login")


def create_fixture_line():
    body = {"code": "E2EQCLINE", "name": "E2E QC/Rework Line", "capacity_per_hour": 50, "notes": "E2E fixture"}
    r = S.post(f"{BASE}/api/rahaza/lines", json=body)
    assert r.status_code == 200, f"create line {r.status_code}: {r.text}"
    st["line_id"] = r.json()["id"]
    print(f"PASS fixture line {body['code']} dibuat")


def load_process_ids():
    for code in ["FINISHING", "QC", "PACKING"]:
        r = S.get(f"{BASE}/api/rahaza/execution/process/{code}/board")
        assert r.status_code == 200, f"board {code} {r.status_code}: {r.text}"
        st["proc"][code] = r.json()["process"]["id"]
    print(f"PASS load process id FINISHING/QC/PACKING: {list(st['proc'].keys())}")


def output_finishing():
    r = S.post(f"{BASE}/api/rahaza/execution/quick-output",
               json={"line_id": st["line_id"], "process_id": st["proc"]["FINISHING"], "qty": 100,
                     "notes": "E2E output finishing"})
    assert r.status_code == 200, f"quick-output finishing {r.status_code}: {r.text}"
    assert r.json().get("event_type") == "output", f"expected output got {r.json().get('event_type')}"
    print("PASS OUTPUT finishing 100 (quick-output) event_type=output")


def guard_qc_via_quick_output():
    r = S.post(f"{BASE}/api/rahaza/execution/quick-output",
               json={"line_id": st["line_id"], "process_id": st["proc"]["QC"], "qty": 10})
    assert r.status_code >= 400, f"expected reject quick-output@QC got {r.status_code}"
    print("PASS guard: quick-output pada proses QC ditolak (400) -> harus qc-event")


def qc_event():
    r = S.post(f"{BASE}/api/rahaza/execution/qc-event",
               json={"line_id": st["line_id"], "qty_pass": 80, "qty_fail": 20, "notes": "E2E QC"})
    assert r.status_code == 200, f"qc-event {r.status_code}: {r.text}"
    j = r.json()
    assert j["qty_pass"] == 80 and j["qty_fail"] == 20 and len(j["created"]) == 2, f"qc-event body {j}"
    print("PASS QC event pass=80 fail=20 (qc_pass -> Packing, qc_fail -> Papan Rework)")


def guard_qc_no_qty():
    r = S.post(f"{BASE}/api/rahaza/execution/qc-event",
               json={"line_id": st["line_id"], "qty_pass": 0, "qty_fail": 0})
    assert r.status_code >= 400, f"expected reject qc-event tanpa qty got {r.status_code}"
    print("PASS guard: qc-event tanpa qty_pass/qty_fail ditolak (400)")


def rework_event():
    r = S.post(f"{BASE}/api/rahaza/execution/rework-event",
               json={"line_id": st["line_id"], "qty_in": 20, "qty_out": 15, "qty_fail": 5, "notes": "E2E rework"})
    assert r.status_code == 200, f"rework-event {r.status_code}: {r.text}"
    j = r.json()
    assert j["ok"] and j["qty_out"] == 15 and j["qty_fail"] == 5 and j["pending"] == 0, f"rework body {j}"
    print("PASS REWORK event in=20 out=15(rework_pass->Packing) fail=5(rework_fail->scrap) pending=0")


def guard_rework_invariant():
    r = S.post(f"{BASE}/api/rahaza/execution/rework-event",
               json={"line_id": st["line_id"], "qty_in": 10, "qty_out": 8, "qty_fail": 5})
    assert r.status_code >= 400, f"expected reject rework invariant got {r.status_code}"
    print("PASS guard: rework qty_out+qty_fail > qty_in ditolak (400)")


def packing_output():
    r = S.post(f"{BASE}/api/rahaza/execution/quick-output",
               json={"line_id": st["line_id"], "process_id": st["proc"]["PACKING"], "qty": 95,
                     "notes": "E2E packing (80 qc_pass + 15 rework_pass)"})
    assert r.status_code == 200, f"quick-output packing {r.status_code}: {r.text}"
    print("PASS PACKING output 95 (80 qc_pass + 15 rework_pass) event_type=output")


def snapshot_flow_summary():
    """Baseline global flow-summary — endpoint agregasi SELURUH rahaza_wip_events
    (tanpa window tanggal), sehingga DB ber-seed membuat angka absolut tidak
    deterministik. Test membandingkan DELTA terhadap baseline ini."""
    r = S.get(f"{BASE}/api/rahaza/execution/flow-summary")
    assert r.status_code == 200, f"flow-summary baseline {r.status_code}: {r.text}"
    j = r.json()
    packing = next((p for p in j["main_flow"] if p["code"] == "PACKING"), None)
    st["base_qc_pass"] = j["qc_pass"]
    st["base_qc_fail"] = j["qc_fail"]
    st["base_packing"] = packing["throughput"] if packing else 0


def check_flow_summary():
    r = S.get(f"{BASE}/api/rahaza/execution/flow-summary")
    assert r.status_code == 200, f"flow-summary {r.status_code}: {r.text}"
    j = r.json()
    d_pass = j["qc_pass"] - st["base_qc_pass"]
    d_fail = j["qc_fail"] - st["base_qc_fail"]
    assert d_pass == 80 and d_fail == 20, f"flow-summary qc delta {d_pass}/{d_fail}"
    packing = next((p for p in j["main_flow"] if p["code"] == "PACKING"), None)
    d_pack = (packing["throughput"] if packing else 0) - st["base_packing"]
    assert packing and d_pack == 95, f"packing throughput delta {d_pack} ({packing})"
    print(f"PASS flow-summary delta qc_pass=+80 qc_fail=+20 packing_throughput=+95 bottleneck={j.get('bottleneck')}")


def check_board_and_recent():
    r = S.get(f"{BASE}/api/rahaza/execution/process/QC/board")
    assert r.status_code == 200 and r.json()["process"]["code"] == "QC", f"QC board {r.status_code}"
    assert len(r.json()["recent_events"]) >= 1, "QC board recent_events kosong"
    r2 = S.get(f"{BASE}/api/rahaza/execution/recent-events?limit=10")
    assert r2.status_code == 200 and isinstance(r2.json(), list), f"recent-events {r2.status_code}"
    print(f"PASS board QC memuat recent_events; recent-events global {len(r2.json())} entri")


def main():
    login()
    snapshot_flow_summary()
    create_fixture_line()
    load_process_ids()
    output_finishing()
    guard_qc_via_quick_output()
    qc_event()
    guard_qc_no_qty()
    rework_event()
    guard_rework_invariant()
    packing_output()
    check_flow_summary()
    check_board_and_recent()
    print("\n=== QC/REWORK FLOW ALL PASS ===")


def cleanup():
    n_ev = 0
    line_id = st.get("line_id")
    if not line_id:
        print("CLEANUP: tidak ada fixture untuk dibersihkan")
        return
    url, dbn = _mongo_cfg()
    if not url:
        print("CLEANUP WARN: MONGO_URL tidak terbaca, lewati hard-clean")
        return
    try:
        from pymongo import MongoClient
        cli = MongoClient(url)
        db = cli[dbn]
        res = db.rahaza_wip_events.delete_many({"line_id": line_id})
        n_ev = res.deleted_count
        db.rahaza_lines.delete_one({"id": line_id})
        cli.close()
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")
        return
    print(f"CLEANUP: {n_ev} wip_events + 1 fixture line dihapus (DB pristine)")


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
