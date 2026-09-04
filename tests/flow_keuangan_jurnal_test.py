"""E2E API-level test for Jurnal & Akuntansi Flow: COA -> Journal (post) -> Reports (neraca/laba-rugi)."""
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

def seed_coa():
    r = S.post(f"{BASE}/api/rahaza/coa/seed", json={})
    assert r.status_code == 200, f"coa seed {r.status_code}: {r.text}"
    print(f"PASS COA seed {r.json()}")

def pick_accounts():
    r = S.get(f"{BASE}/api/rahaza/coa/accounts")
    assert r.status_code == 200, f"coa list {r.status_code}: {r.text}"
    d = r.json()
    rows = d if isinstance(d, list) else d.get("data", d.get("accounts", []))
    leaf = [r for r in rows if not r.get("is_group")]
    codes = {r.get("code") for r in leaf}
    # pick two known leaf asset accounts (cash transfer entry - always balanced & valid)
    st["dr"] = "1-1101" if "1-1101" in codes else leaf[0]["code"]
    st["cr"] = "1-1201" if "1-1201" in codes else leaf[1]["code"]
    print(f"PASS pick accounts DR={st['dr']} CR={st['cr']} (leaf={len(leaf)})")

def create_journal_posted():
    body = {
        "date": date.today().isoformat(),
        "memo": "E2E Jurnal setoran kas ke bank",
        "source_module": "manual",
        "source_ref": "E2E-JE-001",
        "post": True,
        "lines": [
            {"account_code": st["dr"], "debit": 1000000, "credit": 0},
            {"account_code": st["cr"], "debit": 0, "credit": 1000000},
        ],
    }
    r = S.post(f"{BASE}/api/rahaza/journals", json=body)
    assert r.status_code == 200, f"journal create {r.status_code}: {r.text}"
    je = r.json()
    st["je_id"] = je["id"]
    assert je["status"] == "posted", f"expected posted got {je['status']}"
    assert je["total_debit"] == je["total_credit"] == 1000000, f"unbalanced {je['total_debit']}/{je['total_credit']}"
    print(f"PASS journal {je['je_number']} status=posted balanced=1.000.000")

def verify_get():
    r = S.get(f"{BASE}/api/rahaza/journals/{st['je_id']}")
    assert r.status_code == 200, f"journal get {r.status_code}: {r.text}"
    print(f"PASS journal detail retrieved status={r.json().get('status')}")

def reject_unbalanced():
    body = {"date": date.today().isoformat(), "memo": "E2E unbalanced", "post": False,
            "lines": [{"account_code": st["dr"], "debit": 500000, "credit": 0},
                      {"account_code": st["cr"], "debit": 0, "credit": 400000}]}
    r = S.post(f"{BASE}/api/rahaza/journals", json=body)
    assert r.status_code >= 400, f"expected reject unbalanced got {r.status_code}"
    print("PASS unbalanced journal rejected (guard)")

def check_reports():
    for name, path in [("trial-balance", "trial-balance"), ("balance-sheet", "balance-sheet"),
                       ("profit-loss", "profit-loss")]:
        r = S.get(f"{BASE}/api/rahaza/finance/reports/{path}")
        assert r.status_code == 200, f"{name} {r.status_code}: {r.text}"
        print(f"PASS report {name} 200")
    # general-ledger requires account_code query param
    r = S.get(f"{BASE}/api/rahaza/finance/reports/general-ledger", params={"account_code": st["dr"]})
    assert r.status_code == 200, f"general-ledger {r.status_code}: {r.text}"
    print("PASS report general-ledger 200")

def main():
    login(); seed_coa(); pick_accounts(); create_journal_posted(); verify_get(); reject_unbalanced(); check_reports()
    print("\n=== JURNAL FLOW ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
