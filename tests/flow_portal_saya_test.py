"""
E2E API-level POC test — Alur Portal Saya (Self-Service HR).

Fokus: Slip Gaji (payslip), Cuti (leave), Kehadiran pribadi (attendance) + Profil.
SSOT: rahaza_employees (linkage) + rahaza_leave_types / rahaza_leave_requests /
rahaza_leave_balances / rahaza_payslips / rahaza_attendance_events.

Happy-path (login sebagai karyawan uji yang tertaut employee):
  profil          -> GET /api/portal/profile (is_linked) + GET /api/rahaza/self/profile
  dashboard       -> GET /api/portal/dashboard (leave_balance, last_payslip, absensi)
  cuti (tipe)     -> GET /api/portal/leave-types
  cuti (ajukan)   -> POST /api/portal/leave (pending, days terhitung)
  cuti (riwayat)  -> GET /api/portal/leave + GET /api/portal-saya/me/leaves
  cuti (saldo)    -> GET /api/portal-saya/me/leave-balance
  cuti (batal)    -> DELETE /api/portal/leave/{id}
  slip gaji       -> GET /api/portal/payslips + /api/rahaza/self/payslips + /me/payslips
  slip (detail)   -> GET /api/rahaza/self/payslip/{id}
  kehadiran       -> GET /api/rahaza/self/attendance (summary + records)
  profil (update) -> PUT /api/portal/profile (no_hp persisted)
  employee record -> GET /api/portal-saya/me/employee
Guards:
  ajukan cuti tanpa leave_type_id -> 400
  ajukan cuti tipe tidak dikenal  -> 404
  batal cuti tidak ada            -> 404
  detail payslip bukan milik      -> 404
  akun belum tertaut (admin)      -> 409  (self-service butuh employee link)
Self-cleanup (hard): user + employee + leave types/requests/balances + payslip + attendance.
"""
import sys
import uuid
from datetime import date, timedelta, datetime, timezone
import requests

BASE = "http://localhost:8001"
S = requests.Session()        # karyawan uji (tertaut employee)
ADM = requests.Session()      # superadmin
UNL = requests.Session()      # user uji TIDAK tertaut employee -> untuk guard 409

YEAR = date.today().year
TODAY = date.today()
st = {
    "uid": None, "uid2": None, "emp": None, "lt": None, "slip": None,
    "email": f"e2e.portalsaya.{uuid.uuid4().hex[:8]}@dewiaditya.id",
    "email2": f"e2e.portalsaya.unlinked.{uuid.uuid4().hex[:8]}@dewiaditya.id",
    "empcode": f"E2E-{uuid.uuid4().hex[:5].upper()}",
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


def _iso(d):
    return d.isoformat()


def seed():
    """Buat user + employee tertaut + tipe cuti + saldo + payslip + kehadiran."""
    sys.path.insert(0, "/app/backend")
    from auth import hash_password
    cli, db = _mongo()
    uid = str(uuid.uuid4())
    emp_id = str(uuid.uuid4())
    lt_id = str(uuid.uuid4())
    slip_id = str(uuid.uuid4())

    db.users.insert_one({
        "id": uid, "name": "E2E Karyawan Portal", "email": st["email"],
        "password": hash_password("Portal@123"), "role": "operator",
        "status": "active", "employee_id": emp_id, "no_hp": "",
    })
    uid2 = str(uuid.uuid4())
    db.users.insert_one({
        "id": uid2, "name": "E2E Unlinked Portal", "email": st["email2"],
        "password": hash_password("Portal@123"), "role": "operator",
        "status": "active", "no_hp": "",
    })
    st["uid2"] = uid2
    db.rahaza_employees.insert_one({
        "id": emp_id, "user_id": uid, "active": True,
        "name": "E2E Karyawan Portal", "employee_code": st["empcode"],
        "email": st["email"], "job_title": "Operator Jahit",
        "wage_scheme": "monthly", "pay_scheme": "monthly",
    })
    db.rahaza_leave_types.insert_one({
        "id": lt_id, "name": "E2E Cuti Tahunan", "code": "E2E-AL",
        "active": True, "color": "#22c55e", "quota": 12,
    })
    db.rahaza_leave_balances.insert_one({
        "id": str(uuid.uuid4()), "employee_id": emp_id, "leave_type_id": lt_id,
        "year": YEAR, "quota": 12, "used": 2,
    })
    db.rahaza_payslips.insert_one({
        "id": slip_id, "employee_id": emp_id,
        "period_from": _iso(TODAY.replace(day=1)),
        "period_to": _iso(TODAY),
        "gross_pay": 4500000, "net_pay": 4100000,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    # Kehadiran: 3 hari terakhir dalam bulan ini
    events = []
    for i, stt in enumerate(["hadir", "hadir", "izin"]):
        d = TODAY - timedelta(days=i)
        events.append({
            "id": str(uuid.uuid4()), "employee_id": emp_id, "date": _iso(d),
            "status": stt, "hours_worked": 8 if stt == "hadir" else 0,
        })
    db.rahaza_attendance_events.insert_many(events)
    cli.close()

    st.update({"uid": uid, "emp": emp_id, "lt": lt_id, "slip": slip_id})
    # login
    r = S.post(f"{BASE}/api/auth/login", json={"email": st["email"], "password": "Portal@123"})
    assert r.status_code == 200, f"login karyawan: {r.status_code} {r.text}"
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    ra = ADM.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    assert ra.status_code == 200, "login admin gagal"
    ADM.headers.update({"Authorization": f"Bearer {ra.json()['token']}", "Content-Type": "application/json"})
    ru = UNL.post(f"{BASE}/api/auth/login", json={"email": st["email2"], "password": "Portal@123"})
    assert ru.status_code == 200, "login user unlinked gagal"
    UNL.headers.update({"Authorization": f"Bearer {ru.json()['token']}", "Content-Type": "application/json"})
    print(f"PASS seed fixtures + login (emp={emp_id[:8]}, user tertaut)")


def main():
    seed()

    # ── Profil ─────────────────────────────────────────────────────────────
    p = S.get(f"{BASE}/api/portal/profile").json()
    assert p["is_linked"] is True and p["employee"] and p["employee"]["id"] == st["emp"], f"profile {p}"
    print("PASS profil portal (is_linked=true, employee tertaut)")

    rp = S.get(f"{BASE}/api/rahaza/self/profile").json()
    assert rp["is_linked"] is True, f"self profile {rp}"
    print("PASS profil self (rahaza)")

    me = S.get(f"{BASE}/api/portal-saya/me/employee")
    assert me.status_code == 200 and me.json().get("id") == st["emp"], f"me/employee {me.text}"
    print("PASS employee record (/me/employee)")

    # ── Dashboard ────────────────────────────────────────────────────────────
    d = S.get(f"{BASE}/api/portal/dashboard").json()
    assert d["is_linked"] is True, f"dashboard is_linked {d}"
    assert any(b["type_name"] == "E2E Cuti Tahunan" and b["remaining"] == 10 for b in d["leave_balance"]), f"leave_balance {d['leave_balance']}"
    assert d["last_payslip"] and d["last_payslip"]["net_pay"] == 4100000, f"last_payslip {d.get('last_payslip')}"
    assert d["absensi_bulan_ini"]["hadir"] >= 2 and d["absensi_bulan_ini"]["izin"] >= 1, f"absensi {d['absensi_bulan_ini']}"
    print(f"PASS dashboard (saldo cuti sisa=10, gaji terakhir=4.1jt, hadir={d['absensi_bulan_ini']['hadir']}/izin={d['absensi_bulan_ini']['izin']})")

    # ── Cuti: tipe ───────────────────────────────────────────────────────────
    lts = S.get(f"{BASE}/api/portal/leave-types").json()
    assert any(t["id"] == st["lt"] for t in lts["items"]), f"leave-types {lts}"
    print(f"PASS tipe cuti aktif ({len(lts['items'])})")

    # ── Guard: ajukan cuti tanpa leave_type_id ──────────────────────────────
    g1 = S.post(f"{BASE}/api/portal/leave", json={"from_date": _iso(TODAY + timedelta(days=3))})
    assert g1.status_code == 400, f"expect 400 tanpa leave_type_id, got {g1.status_code}"
    print("PASS guard: ajukan cuti tanpa leave_type_id ditolak (400)")

    # ── Guard: tipe cuti tidak dikenal ──────────────────────────────────────
    g2 = S.post(f"{BASE}/api/portal/leave", json={"leave_type_id": "tidak-ada", "from_date": _iso(TODAY + timedelta(days=3))})
    assert g2.status_code == 404, f"expect 404 tipe tak dikenal, got {g2.status_code}"
    print("PASS guard: tipe cuti tidak dikenal ditolak (404)")

    # ── Cuti: ajukan (valid) ─────────────────────────────────────────────────
    f_from = _iso(TODAY + timedelta(days=3))
    f_to = _iso(TODAY + timedelta(days=5))
    r = S.post(f"{BASE}/api/portal/leave", json={
        "leave_type_id": st["lt"], "from_date": f_from, "to_date": f_to,
        "reason": "Acara keluarga",
    })
    assert r.status_code == 200, f"ajukan cuti {r.status_code}: {r.text}"
    leave = r.json()
    assert leave["status"] == "pending" and leave["days"] == 3, f"leave body {leave}"
    leave_id = leave["id"]
    print(f"PASS ajukan cuti id={leave_id[:8]} (status=pending, days=3)")

    # ── Cuti: riwayat (2 endpoint) ──────────────────────────────────────────
    hist = S.get(f"{BASE}/api/portal/leave").json()
    assert any(x["id"] == leave_id for x in hist["items"]), "cuti tak muncul di /api/portal/leave"
    hist2 = S.get(f"{BASE}/api/portal-saya/me/leaves").json()
    assert any(x["id"] == leave_id for x in hist2["items"]), "cuti tak muncul di /me/leaves"
    print("PASS riwayat cuti (portal/leave + me/leaves)")

    # ── Cuti: saldo (me/leave-balance) ──────────────────────────────────────
    bal = S.get(f"{BASE}/api/portal-saya/me/leave-balance").json()
    assert any(b["leave_type_id"] == st["lt"] and b.get("quota") == 12 for b in bal["balances"]), f"leave-balance {bal}"
    print("PASS saldo cuti (me/leave-balance)")

    # ── Cuti: batal (pending -> ok) ─────────────────────────────────────────
    dc = S.delete(f"{BASE}/api/portal/leave/{leave_id}")
    assert dc.status_code == 200 and dc.json().get("ok") is True, f"batal cuti {dc.text}"
    hist3 = S.get(f"{BASE}/api/portal/leave").json()
    assert not any(x["id"] == leave_id for x in hist3["items"]), "cuti belum terhapus setelah batal"
    print("PASS batal cuti (pending) -> terhapus dari riwayat")

    # ── Guard: batal cuti tidak ada ─────────────────────────────────────────
    g3 = S.delete(f"{BASE}/api/portal/leave/{uuid.uuid4()}")
    assert g3.status_code == 404, f"expect 404 batal cuti tak ada, got {g3.status_code}"
    print("PASS guard: batal cuti tidak ada ditolak (404)")

    # ── Slip gaji (3 endpoint) ──────────────────────────────────────────────
    ps1 = S.get(f"{BASE}/api/portal/payslips").json()
    assert any(s["id"] == st["slip"] for s in ps1["items"]), "payslip tak muncul di /api/portal/payslips"
    ps2 = S.get(f"{BASE}/api/rahaza/self/payslips").json()
    assert any(s["id"] == st["slip"] for s in ps2["slips"]), "payslip tak muncul di /self/payslips"
    ps3 = S.get(f"{BASE}/api/portal-saya/me/payslips").json()
    assert any(s["id"] == st["slip"] for s in ps3["payslips"]), "payslip tak muncul di /me/payslips"
    print("PASS slip gaji (portal/payslips + self/payslips + me/payslips)")

    # ── Slip gaji: detail + guard 404 ───────────────────────────────────────
    det = S.get(f"{BASE}/api/rahaza/self/payslip/{st['slip']}").json()
    assert det["id"] == st["slip"] and det["net_pay"] == 4100000, f"payslip detail {det}"
    print("PASS detail slip gaji (net_pay=4.1jt)")

    g4 = S.get(f"{BASE}/api/rahaza/self/payslip/{uuid.uuid4()}")
    assert g4.status_code == 404, f"expect 404 payslip bukan milik, got {g4.status_code}"
    print("PASS guard: detail payslip bukan milik ditolak (404)")

    # ── Kehadiran pribadi ───────────────────────────────────────────────────
    att = S.get(f"{BASE}/api/rahaza/self/attendance").json()
    assert att["employee_id"] == st["emp"], f"attendance emp {att}"
    assert att["summary"]["hadir"] >= 2 and att["summary"]["izin"] >= 1, f"attendance summary {att['summary']}"
    assert len(att["records"]) >= 3, f"attendance records {len(att['records'])}"
    print(f"PASS kehadiran pribadi (hadir={att['summary']['hadir']}, izin={att['summary']['izin']}, {len(att['records'])} record)")

    # ── Profil: update ──────────────────────────────────────────────────────
    up = S.put(f"{BASE}/api/portal/profile", json={"no_hp": "08123456789", "alamat": "Jl. Uji E2E"})
    assert up.status_code == 200 and up.json().get("no_hp") == "08123456789", f"update profil {up.text}"
    print("PASS update profil (no_hp persisted)")

    # ── Guard: akun belum tertaut (user tanpa employee link) -> 409 ─────────
    g5 = UNL.get(f"{BASE}/api/portal/leave")
    assert g5.status_code == 409, f"expect 409 user tak tertaut, got {g5.status_code}"
    print("PASS guard: akun belum tertaut ditolak (409)")

    print("\n=== PORTAL SAYA FLOW ALL PASS ===")


def cleanup():
    try:
        cli, db = _mongo()
        emp = st["emp"]
        n_u = db.users.delete_many({"$or": [{"id": st["uid"]}, {"email": st["email"]}]}).deleted_count if st["uid"] else 0
        n_u += db.users.delete_many({"$or": [{"id": st["uid2"]}, {"email": st["email2"]}]}).deleted_count if st["uid2"] else 0
        n_e = db.rahaza_employees.delete_many({"id": emp}).deleted_count if emp else 0
        n_lt = db.rahaza_leave_types.delete_many({"id": st["lt"]}).deleted_count if st["lt"] else 0
        n_lr = db.rahaza_leave_requests.delete_many({"employee_id": emp}).deleted_count if emp else 0
        n_lb = db.rahaza_leave_balances.delete_many({"employee_id": emp}).deleted_count if emp else 0
        n_ps = db.rahaza_payslips.delete_many({"employee_id": emp}).deleted_count if emp else 0
        n_at = db.rahaza_attendance_events.delete_many({"employee_id": emp}).deleted_count if emp else 0
        cli.close()
        print(f"CLEANUP: {n_u} user + {n_e} employee + {n_lt} leave_type + {n_lr} leave_req + "
              f"{n_lb} leave_bal + {n_ps} payslip + {n_at} attendance dihapus (DB pristine)")
    except Exception as e:
        print(f"CLEANUP WARN: {type(e).__name__}: {e}")


if __name__ == "__main__":
    try:
        main()
        cleanup()
    except AssertionError as e:
        cleanup()
        print(f"\nFAIL: {e}")
        sys.exit(1)
    except Exception as e:
        cleanup()
        print(f"\nERROR: {type(e).__name__}: {e}")
        sys.exit(2)
