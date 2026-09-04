"""E2E API-level test for Multi-Channel Sales Flow (Toko): Account -> Sales -> AR Invoice."""
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

def create_account():
    body = {"account_code": "E2E-SHOPEE-01", "account_name": "E2E Shopee Store", "platform": "shopee", "group": "other"}
    r = S.post(f"{BASE}/api/marketing/accounts", json=body)
    if r.status_code == 400 and "already exists" in r.text:
        accs = S.get(f"{BASE}/api/marketing/accounts").json()
        rows = accs.get("accounts", accs) if isinstance(accs, dict) else accs
        st["account_id"] = next(a["id"] for a in rows if a["account_code"] == "E2E-SHOPEE-01")
    else:
        assert r.status_code == 200, f"account create {r.status_code}: {r.text}"
        st["account_id"] = r.json()["account"]["id"]
    print(f"PASS account E2E-SHOPEE-01 ({st['account_id'][:8]})")

def create_sales():
    today = date.today().isoformat()
    st["date"] = today
    body = {"account_id": st["account_id"], "date": today, "revenue_type": "total", "revenue": 5000000, "orders": 25}
    r = S.post(f"{BASE}/api/marketing/sales-data", json=body)
    if r.status_code == 400 and "already exists" in r.text:
        print("INFO sales data already exists for today (ok)")
    else:
        assert r.status_code == 200, f"sales create {r.status_code}: {r.text}"
        print(f"PASS sales-data {today} revenue=5,000,000 orders=25")

def generate_ar():
    today = st["date"]
    body = {"date_from": today, "date_to": today, "revenue_type": "total", "grouping": "daily", "account_id": st["account_id"]}
    r = S.post(f"{BASE}/api/marketing/sales-data/generate-ar-batch", json=body)
    assert r.status_code == 200, f"ar batch {r.status_code}: {r.text}"
    resp = r.json()
    invs = resp.get("invoices", [])
    print(f"PASS generate-ar-batch -> {len(invs)} invoice(s). msg={resp.get('message','')[:80]}")
    st["invoices"] = invs

def main():
    login(); create_account(); create_sales(); generate_ar()
    print("\n=== MULTICHANNEL SALES ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
