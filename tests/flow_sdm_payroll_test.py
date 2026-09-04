"""E2E API-level test for Payroll Flow: Employee+Profile -> Run -> Finalize(JE) -> Pay(JE)."""
import requests, sys
from datetime import date

BASE = "http://localhost:8001"
S = requests.Session()
st = {}

def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login")

def ensure_employee():
    body = {"employee_code": "E2E-EMP-01", "name": "E2E Karyawan Satu", "job_title": "Operator",
            "department": "Produksi", "contract_type": "PKWTT", "wage_scheme": "monthly"}
    r = S.post(f"{BASE}/api/rahaza/employees", json=body)
    if r.status_code == 409:
        es = S.get(f"{BASE}/api/rahaza/employees").json()
        rows = es if isinstance(es, list) else es.get("items", es.get("data", es.get("employees", [])))
        st["emp_id"] = next(e["id"] for e in rows if e.get("employee_code") == "E2E-EMP-01")
    else:
        assert r.status_code == 200, f"employee {r.status_code}: {r.text}"
        st["emp_id"] = r.json()["id"]
    print(f"PASS employee E2E-EMP-01 ({st['emp_id'][:8]})")

def ensure_profile():
    body = {"employee_id": st["emp_id"], "pay_scheme": "monthly", "period_type": "monthly", "base_rate": 5000000}
    r = S.post(f"{BASE}/api/rahaza/payroll-profiles", json=body)
    assert r.status_code == 200, f"profile {r.status_code}: {r.text}"
    print(f"PASS payroll-profile base_rate=5,000,000 pay_scheme=monthly")

def create_run():
    today = date.today()
    pfrom = today.replace(day=1).isoformat()
    pto = today.isoformat()
    st["pfrom"], st["pto"] = pfrom, pto
    r = S.post(f"{BASE}/api/rahaza/payroll-runs", json={"period_from": pfrom, "period_to": pto, "notes": "E2E payroll"})
    assert r.status_code == 200, f"run create {r.status_code}: {r.text}"
    run = r.json()
    st["run_id"] = run["id"]
    assert run["status"] == "draft", f"expected draft got {run['status']}"
    assert run["total_employees"] >= 1, f"expected >=1 payslip got {run['total_employees']}"
    print(f"PASS run {run['run_number']} status=draft employees={run['total_employees']} net={run['total_net']}")

def finalize_run():
    r = S.post(f"{BASE}/api/rahaza/payroll-runs/{st['run_id']}/finalize", json={})
    assert r.status_code == 200, f"finalize {r.status_code}: {r.text}"
    out = r.json()
    assert out["status"] == "finalized", f"expected finalized got {out['status']}"
    pr = out.get("_posting_result", {})
    print(f"PASS run finalized. payroll JE posting_ok={pr.get('ok') if isinstance(pr,dict) else pr} je={pr.get('je_number') if isinstance(pr,dict) else ''}")

def pay_run():
    body = {"payment_date": date.today().isoformat(), "bank_account_code": "1-1201", "payment_method": "bank_transfer", "notes": "E2E pay"}
    r = S.post(f"{BASE}/api/rahaza/payroll-runs/{st['run_id']}/pay", json=body)
    assert r.status_code == 200, f"pay {r.status_code}: {r.text}"
    out = r.json()
    pr = out.get("_payment_result", {})
    print(f"PASS run paid. payment_status={out.get('payment_status')} payment JE ok={pr.get('ok') if isinstance(pr,dict) else pr} je={out.get('payment_gl_je_number')}")
    assert out.get("payment_status") == "paid", f"expected paid got {out.get('payment_status')}"

def main():
    login(); ensure_employee(); ensure_profile(); create_run(); finalize_run(); pay_run()
    print("\n=== PAYROLL FLOW ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
