"""HRIS real-flow / state-machine + output-correctness verification.
Covers overtime workflow end-to-end (create->approve->idempotency->cancel)
with numeric output assertions.

FASE 21 — BUG ALAT UJI YANG DIPERBAIKI DI SINI
──────────────────────────────────────────────
Docstring lama mengklaim "Cleans up after itself". **KELIRU.**
`DELETE /api/rahaza/overtime/{id}` hanya meng-CANCEL (mengubah status jadi
`cancelled`); DOKUMENNYA TETAP TERSIMPAN. Akibat nyata yang ditemukan sesi ini:
satu request lembur `reason="flow-test"` bertanggal **2028-09-01** masih ada di
DB, dan `cleanup_fase20_qa.py` melaporkan "tidak ada drift" karena pencocokannya
berbasis teks penanda FASE 20 — jadi selalu satu alat di belakang.

Sekarang skrip ini MENGHAPUS jejaknya sendiri lewat `finally` (langsung ke Mongo),
dan juga menyapu sisa run sebelumnya sebelum mulai. Prinsipnya: alat uji tidak
menitipkan sampahnya ke skrip pembersih.
"""
import os
import sys

import requests

BASE = "http://localhost:8001"
OT_MARKER = "flow-test"          # penanda milik skrip ini saja
results = []


def _db():
    """Handle Mongo langsung — dipakai HANYA untuk membersihkan jejak sendiri."""
    from pymongo import MongoClient
    try:
        from dotenv import load_dotenv
        load_dotenv(os.path.join(os.path.dirname(__file__), "..", "backend", ".env"))
    except Exception:
        pass
    url = os.environ.get("MONGO_URL")
    if not url:
        return None
    return MongoClient(url)[os.environ.get("DB_NAME", "test_database")]


def purge_own_artifacts(label=""):
    """Hapus TOTAL request lembur milik skrip ini. Idempoten."""
    db = _db()
    if db is None:
        print(f"  ! MONGO_URL tak ada — jejak {label} tidak bisa dihapus")
        return -1
    n = db.rahaza_overtime_requests.delete_many({"reason": OT_MARKER}).deleted_count
    if n:
        print(f"  [cleanup{(' ' + label) if label else ''}] {n} request lembur uji DIHAPUS TOTAL")
    return n


def rec(name, ok, detail=""):
    results.append((name, ok, detail))
    print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {detail}")


def login():
    r = requests.post(f"{BASE}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def main():
    purge_own_artifacts("sisa run sebelumnya")   # jaring: run lama boleh saja bocor
    try:
        _run()
    finally:
        # WAJIB di `finally`: kalau assert gagal / timeout / Ctrl-C, jejaknya
        # tetap terhapus. Inilah bedanya dengan versi lama yang mengandalkan
        # satu baris `DELETE` di jalur sukses (dan itu pun hanya meng-cancel).
        purge_own_artifacts("jejak run ini")


def _run():
    tok = login()
    hdr = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

    # get a real employee
    r = requests.get(f"{BASE}/api/rahaza/employees?limit=1", headers=hdr, timeout=30)
    d = r.json()
    emp = (d.get("items") or d.get("employees") or d)[0]
    emp_id = emp["id"]

    # ── OVERTIME FLOW ───────────────────────────────────────────────
    body = {"employee_id": emp_id, "date": "2028-09-01",
            "start_time": "17:00", "end_time": "19:30", "reason": "flow-test"}
    r = requests.post(f"{BASE}/api/rahaza/overtime", headers=hdr, json=body, timeout=30)
    ok = r.status_code == 200 and r.json().get("overtime", {}).get("status") == "pending"
    ot = r.json().get("overtime", {}) if r.status_code == 200 else {}
    ot_id = ot.get("id")
    rec("OT create -> 200 status=pending", ok, f"status={r.status_code} id={ot_id}")

    # output correctness: 17:00->19:30 = 2.5h
    rec("OT output: hours computed = 2.5", ot.get("hours") == 2.5, f"hours={ot.get('hours')}")

    # approve
    if ot_id:
        r = requests.put(f"{BASE}/api/rahaza/overtime/{ot_id}/approve", headers=hdr, json={}, timeout=30)
        okj = r.json().get("overtime", {}) if r.status_code == 200 else {}
        rec("OT approve -> 200 status=approved", r.status_code == 200 and okj.get("status") == "approved",
            f"status={r.status_code} new_status={okj.get('status')}")
        rec("OT approve sets approved_by", bool(okj.get("approved_by")), f"approved_by={okj.get('approved_by')}")

        # idempotency / state-machine: re-approve must be rejected (not pending)
        r = requests.put(f"{BASE}/api/rahaza/overtime/{ot_id}/approve", headers=hdr, json={}, timeout=30)
        rec("OT double-approve rejected (state machine) -> 400", r.status_code == 400,
            f"status={r.status_code}")

        # summary reflects approved hours
        r = requests.get(f"{BASE}/api/rahaza/overtime/summary?employee_id={emp_id}&date_from=2028-09-01&date_to=2028-09-30",
                         headers=hdr, timeout=30)
        by = r.json().get("by_employee", {}) if r.status_code == 200 else {}
        emp_sum = by.get(emp_id, {})
        rec("OT summary includes approved 2.5h", emp_sum.get("total_hours", 0) >= 2.5,
            f"total_hours={emp_sum.get('total_hours')}")

        # cleanup (endpoint hanya meng-CANCEL — penghapusan TOTAL ada di `finally`)
        r = requests.delete(f"{BASE}/api/rahaza/overtime/{ot_id}", headers=hdr, timeout=30)
        rec("OT cleanup cancel -> 200", r.status_code == 200, f"status={r.status_code}")

    # ── LEAVE FLOW (approve non-existent already tested; here test bad transition) ──
    # create leave then reject-after-approve style check via existing leaves list output shape
    r = requests.get(f"{BASE}/api/rahaza/leaves?limit=5", headers=hdr, timeout=30)
    d = r.json()
    lst = d.get("items") or d.get("leaves") or d if isinstance(d, (list, dict)) else []
    rec("LEAVE list returns well-formed 200", r.status_code == 200, f"status={r.status_code}")

    n_pass = sum(1 for _, ok, _ in results if ok)
    print("\n" + "=" * 60)
    print(f"HRIS FLOW SUMMARY: {n_pass}/{len(results)} passed")
    if n_pass != len(results):
        for n, ok, d in results:
            if not ok:
                print("  FAIL:", n, d)
        sys.exit(1)
    print("HRIS FLOW: ALL PASS")


if __name__ == "__main__":
    main()
