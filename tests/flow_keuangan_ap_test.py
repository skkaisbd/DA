"""E2E API-level test for AP/Hutang Flow: Bill -> Send/Verify -> Payment (auto GL posting)."""
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

def ensure_cash():
    body = {"code": "E2E-AP-BANK", "name": "E2E Bank AP", "type": "bank", "opening_balance": 50000000}
    r = S.post(f"{BASE}/api/rahaza/cash-accounts", json=body)
    if r.status_code == 409:
        cs = S.get(f"{BASE}/api/rahaza/cash-accounts").json()
        rows = cs if isinstance(cs, list) else cs.get("data", cs.get("accounts", []))
        st["account_id"] = next(c["id"] for c in rows if c.get("code") == "E2E-AP-BANK")
    else:
        assert r.status_code == 200, f"cash acct {r.status_code}: {r.text}"
        st["account_id"] = r.json()["id"]
    print(f"PASS cash-account E2E-AP-BANK ({st['account_id'][:8]})")

def create_bill():
    body = {
        "vendor_name": "E2E Supplier Kain",
        "vendor_code": "E2E-SUP",
        "issue_date": date.today().isoformat(),
        "due_date": date.today().isoformat(),
        "items": [{"description": "E2E Kain Katun", "qty": 100, "price": 50000, "unit": "m"}],
        "tax_pct": 0, "notes": "E2E AP bill",
    }
    r = S.post(f"{BASE}/api/rahaza/ap-invoices", json=body)
    assert r.status_code == 200, f"AP create {r.status_code}: {r.text}"
    inv = r.json()
    st["iid"] = inv["id"]
    st["total"] = inv["total"]
    assert inv["status"] == "draft" and inv["total"] == 5000000, f"unexpected {inv['status']}/{inv['total']}"
    print(f"PASS AP bill {inv['invoice_number']} total={inv['total']} status=draft")

def send_bill():
    r = S.post(f"{BASE}/api/rahaza/ap-invoices/{st['iid']}/send", json={})
    assert r.status_code == 200, f"send {r.status_code}: {r.text}"
    out = r.json()
    assert out.get("status") == "sent", f"expected sent got {out.get('status')}"
    pr = out.get("_posting_result")
    print(f"PASS AP sent status=sent gl_posted={'yes' if out.get('gl_je_id') else 'pending'} posting_ok={pr.get('ok') if isinstance(pr,dict) else pr}")

def pay_bill():
    body = {"amount": st["total"], "account_id": st["account_id"], "date": date.today().isoformat(), "notes": "Pelunasan AP E2E"}
    r = S.post(f"{BASE}/api/rahaza/ap-invoices/{st['iid']}/payment", json=body)
    assert r.status_code == 200, f"payment {r.status_code}: {r.text}"
    out = r.json()
    assert out["status"] == "paid", f"expected paid got {out['status']}"
    assert out["balance"] == 0, f"expected balance 0 got {out['balance']}"
    pr = out.get("_posting_result", {})
    print(f"PASS AP payment status=paid balance=0 gl_posting_ok={pr.get('ok') if isinstance(pr,dict) else pr}")

def check_aging():
    r = S.get(f"{BASE}/api/rahaza/ap-aging")
    assert r.status_code == 200, f"aging {r.status_code}: {r.text}"
    print("PASS AP aging report 200")

def main():
    login(); ensure_cash(); create_bill(); send_bill(); pay_bill(); check_aging()
    print("\n=== AP FLOW ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
