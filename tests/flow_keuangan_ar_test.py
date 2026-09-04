"""E2E API-level test for AR/Piutang Flow: Invoice -> Send -> Payment (auto GL posting)."""
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

def ensure_customer():
    body = {"code": "E2E-AR-CUST", "name": "E2E AR Customer", "payment_terms": "net_30"}
    r = S.post(f"{BASE}/api/rahaza/customers", json=body)
    if r.status_code == 409:
        cs = S.get(f"{BASE}/api/rahaza/customers").json()
        rows = cs if isinstance(cs, list) else cs.get("data", cs.get("customers", []))
        st["customer_id"] = next(c["id"] for c in rows if c.get("code") == "E2E-AR-CUST")
    else:
        assert r.status_code == 200, f"customer {r.status_code}: {r.text}"
        st["customer_id"] = r.json()["id"]
    print(f"PASS customer E2E-AR-CUST ({st['customer_id'][:8]})")

def ensure_cash():
    body = {"code": "E2E-CASH", "name": "E2E Kas Operasional", "type": "cash", "opening_balance": 0}
    r = S.post(f"{BASE}/api/rahaza/cash-accounts", json=body)
    if r.status_code == 409:
        cs = S.get(f"{BASE}/api/rahaza/cash-accounts").json()
        rows = cs if isinstance(cs, list) else cs.get("data", cs.get("accounts", []))
        st["account_id"] = next(c["id"] for c in rows if c.get("code") == "E2E-CASH")
    else:
        assert r.status_code == 200, f"cash acct {r.status_code}: {r.text}"
        st["account_id"] = r.json()["id"]
    print(f"PASS cash-account E2E-CASH ({st['account_id'][:8]})")

def create_invoice():
    body = {
        "customer_id": st["customer_id"],
        "issue_date": date.today().isoformat(),
        "due_date": date.today().isoformat(),
        "items": [{"description": "E2E Produk Jadi", "qty": 10, "price": 100000, "unit": "pcs"}],
        "tax_pct": 0, "notes": "E2E AR invoice",
    }
    r = S.post(f"{BASE}/api/rahaza/ar-invoices", json=body)
    assert r.status_code == 200, f"invoice create {r.status_code}: {r.text}"
    inv = r.json()
    st["iid"] = inv["id"]
    st["total"] = inv["total"]
    assert inv["status"] == "draft" and inv["total"] == 1000000, f"unexpected {inv['status']}/{inv['total']}"
    print(f"PASS invoice {inv['invoice_number']} total={inv['total']} status=draft")

def send_invoice():
    r = S.post(f"{BASE}/api/rahaza/ar-invoices/{st['iid']}/send", json={})
    assert r.status_code == 200, f"send {r.status_code}: {r.text}"
    out = r.json()
    pr = out.get("_posting_result")
    print(f"PASS invoice sent status={out.get('status')} gl_posted={'yes' if out.get('gl_je_id') else 'pending'} posting={pr}")

def pay_invoice():
    body = {"amount": st["total"], "account_id": st["account_id"], "date": date.today().isoformat(), "notes": "Pelunasan E2E"}
    r = S.post(f"{BASE}/api/rahaza/ar-invoices/{st['iid']}/payment", json=body)
    assert r.status_code == 200, f"payment {r.status_code}: {r.text}"
    out = r.json()
    assert out["status"] == "paid", f"expected paid got {out['status']}"
    assert out["balance"] == 0, f"expected balance 0 got {out['balance']}"
    pr = out.get("_posting_result", {})
    print(f"PASS payment recorded status=paid balance=0 gl_posting_ok={pr.get('ok') if isinstance(pr,dict) else pr}")

def main():
    login(); ensure_customer(); ensure_cash(); create_invoice(); send_invoice(); pay_invoice()
    print("\n=== AR FLOW ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
