"""
E2E API-level POC test — Alur Kehadiran / Absensi (SDM/HRIS).

Happy path:
  login
  -> seed 2 employee + 1 office location (geofence)               [API + DB]
  -> clock-in emp1 (dengan lat/lng = kantor => in_range)          [POST /api/rahaza/attendance/clock-in]
  -> clock-out emp1 (hitung hours_worked)                          [POST /api/rahaza/attendance/clock-out]
  -> rekap summary per karyawan (feed payroll)                     [GET  /api/rahaza/attendance/summary]
  -> grid harian, list, my-today, hr dashboard                     [GET  ...]
  -> clock-in emp2 (lat/lng jauh => out_of_range, tetap tercatat)  [POST /api/rahaza/attendance/clock-in]
Guards:
  -> clock-in dua kali ditolak (400 "Sudah clock-in")
  -> clock-out tanpa clock-in ditolak (400 "Belum clock-in")
  -> clock-out dua kali ditolak (400 "Sudah clock-out")
Self-cleanup (hard): hapus attendance_events + employee + office fixture.
"""
import sys
import uuid
import requests

BASE = "http://localhost:8001"
S = requests.Session()
OFFICE_LAT, OFFICE_LNG = -6.200000, 106.816666
st = {"emps": [], "office_id": None}


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
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login")


def create_emp(code, name):
    r = S.post(f"{BASE}/api/rahaza/employees",
               json={"employee_code": code, "name": name, "job_title": "Operator",
                     "wage_scheme": "bulanan", "base_rate": 4000000})
    assert r.status_code == 200, f"create emp {code}: {r.status_code} {r.text}"
    eid = r.json()["id"]
    st["emps"].append(eid)
    return eid


def seed_fixtures():
    cli, db = _mongo()
    db.rahaza_office_locations.delete_many({"name": "E2E Office"})
    oid = str(uuid.uuid4())
    db.rahaza_office_locations.insert_one({
        "id": oid, "name": "E2E Office", "lat": OFFICE_LAT, "lng": OFFICE_LNG,
        "geofence_radius_m": 300, "is_primary": True,
    })
    cli.close()
    st["office_id"] = oid
    print("PASS seed office location (geofence 300m, primary)")


def main():
    login()
    seed_fixtures()
    emp1 = create_emp("E2EEMP1", "E2E Karyawan Satu")
    emp2 = create_emp("E2EEMP2", "E2E Karyawan Dua")
    print("PASS seed 2 employee fixture")

    # ── Fase 1: clock-in emp1 (in_range) ─────────────────────────────────────
    r = S.post(f"{BASE}/api/rahaza/attendance/clock-in",
               json={"employee_id": emp1, "lat": OFFICE_LAT, "lng": OFFICE_LNG})
    assert r.status_code == 200, f"clock-in {r.status_code}: {r.text}"
    ci = r.json()
    assert ci.get("clock_in") and ci.get("status") == "hadir", f"clock-in body {ci}"
    assert (ci.get("clock_in_geo") or {}).get("status") == "in_range", f"geo {ci.get('clock_in_geo')}"
    print("PASS clock-in emp1 status=hadir geo=in_range")

    # ── Guard: clock-in dua kali ─────────────────────────────────────────────
    rg = S.post(f"{BASE}/api/rahaza/attendance/clock-in", json={"employee_id": emp1})
    assert rg.status_code >= 400, f"expected reject double clock-in got {rg.status_code}"
    print("PASS guard: clock-in dua kali ditolak (400)")

    # ── Guard: clock-out tanpa clock-in (emp2) ───────────────────────────────
    rg = S.post(f"{BASE}/api/rahaza/attendance/clock-out", json={"employee_id": emp2})
    assert rg.status_code >= 400, f"expected reject clock-out tanpa clock-in got {rg.status_code}"
    print("PASS guard: clock-out tanpa clock-in ditolak (400)")

    # ── Fase 2: clock-out emp1 ───────────────────────────────────────────────
    r = S.post(f"{BASE}/api/rahaza/attendance/clock-out", json={"employee_id": emp1})
    assert r.status_code == 200, f"clock-out {r.status_code}: {r.text}"
    co = r.json()
    assert co.get("clock_out") and co.get("hours_worked") is not None, f"clock-out body {co}"
    print(f"PASS clock-out emp1 hours_worked={co.get('hours_worked')}")

    # ── Guard: clock-out dua kali ────────────────────────────────────────────
    rg = S.post(f"{BASE}/api/rahaza/attendance/clock-out", json={"employee_id": emp1})
    assert rg.status_code >= 400, f"expected reject double clock-out got {rg.status_code}"
    print("PASS guard: clock-out dua kali ditolak (400)")

    # ── Fase 3: rekap summary (feed payroll) ─────────────────────────────────
    r = S.get(f"{BASE}/api/rahaza/attendance/summary", params={"employee_id": emp1})
    assert r.status_code == 200, f"summary {r.status_code}: {r.text}"
    summ = r.json()
    row = next((x for x in summ if x["employee_id"] == emp1), None)
    assert row and row["days_hadir"] == 1, f"summary row {row}"
    print(f"PASS rekap summary emp1: days_hadir=1 total_hours={row['total_hours']} (feed payroll)")

    # ── Fase 4: my-today / grid / list / dashboard ───────────────────────────
    mt = S.get(f"{BASE}/api/rahaza/attendance/my-today", params={"employee_id": emp1}).json()
    assert mt["has_clock_in"] and mt["has_clock_out"], f"my-today {mt}"
    print("PASS my-today emp1: has_clock_in & has_clock_out")

    grid = S.get(f"{BASE}/api/rahaza/attendance/grid").json()
    assert any(x["employee_id"] == emp1 for x in grid["rows"]), "grid tidak memuat emp1"
    print("PASS grid harian memuat emp1")

    lst = S.get(f"{BASE}/api/rahaza/attendance", params={"employee_id": emp1}).json()
    assert lst["total"] >= 1, "list attendance kosong"
    print(f"PASS list attendance emp1 total={lst['total']}")

    assert S.get(f"{BASE}/api/rahaza/hr/dashboard").status_code == 200, "hr dashboard gagal"
    print("PASS hr/dashboard 200")

    # ── Fase 5: clock-in emp2 out_of_range (geofence advisory) ───────────────
    r = S.post(f"{BASE}/api/rahaza/attendance/clock-in",
               json={"employee_id": emp2, "lat": -6.300000, "lng": 106.900000})
    assert r.status_code == 200, f"clock-in emp2 {r.status_code}: {r.text}"
    assert (r.json().get("clock_in_geo") or {}).get("status") == "out_of_range", "emp2 geo bukan out_of_range"
    print("PASS clock-in emp2 geo=out_of_range (tetap tercatat, geofence advisory)")

    print("\n=== KEHADIRAN/ABSENSI FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        n_a = db.rahaza_attendance_events.delete_many({"employee_id": {"$in": st["emps"]}}).deleted_count
        n_e = db.rahaza_employees.delete_many({"$or": [
            {"id": {"$in": st["emps"]}}, {"employee_code": {"$in": ["E2EEMP1", "E2EEMP2"]}}
        ]}).deleted_count
        n_o = db.rahaza_office_locations.delete_many({"name": "E2E Office"}).deleted_count
        cli.close()
        print(f"CLEANUP: {n_a} attendance + {n_e} employee + {n_o} office dihapus (DB pristine)")
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
