"""E2E API-level test for Cutting Flow: Request -> Approve -> Batch -> Eksekusi (status) -> Hasil."""
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

def create_request():
    body = {"product_model_name": "E2E Blouse Katun", "product_category": "Blouse",
            "qty_requested": 200, "colors": ["Putih", "Navy"], "priority": "normal", "notes": "E2E cutting request"}
    r = S.post(f"{BASE}/api/dewi/cutting/requests", json=body)
    assert r.status_code == 200, f"request create {r.status_code}: {r.text}"
    req = r.json()
    st["req_id"] = req["id"]
    assert req["status"] == "pending_approval", f"expected pending_approval got {req['status']}"
    print(f"PASS request {req['request_code']} status=pending_approval")

def approve_request():
    r = S.put(f"{BASE}/api/dewi/cutting/requests/{st['req_id']}/approve")
    assert r.status_code == 200, f"request approve {r.status_code}: {r.text}"
    assert r.json().get("status") == "approved", f"got {r.json().get('status')}"
    print("PASS request approved")

def create_batch():
    body = {"product_model_name": "E2E Blouse Katun", "product_category": "Blouse",
            "total_cut_pcs": 200, "qty_per_color": [{"color": "Putih", "qty": 100}, {"color": "Navy", "qty": 100}],
            "fabric_rolls_used": [{"roll_code": "ROLL-01", "fabric_name": "Katun", "qty_m": 120}],
            "request_id": st["req_id"], "cutting_date": date.today().isoformat(),
            "operator_name": "E2E Operator", "notes": "E2E batch"}
    r = S.post(f"{BASE}/api/dewi/cutting/batches", json=body)
    assert r.status_code == 200, f"batch create {r.status_code}: {r.text}"
    b = r.json()
    st["batch_id"] = b["id"]
    assert b["status"] == "in_cutting", f"expected in_cutting got {b['status']}"
    print(f"PASS batch {b['batch_code']} status=in_cutting total_cut=200")

def execute_batch():
    r = S.put(f"{BASE}/api/dewi/cutting/batches/{st['batch_id']}/status", json={"status": "cut_done"})
    assert r.status_code == 200, f"batch status {r.status_code}: {r.text}"
    print("PASS batch status=cut_done (eksekusi/hasil potong)")

def guard_backward():
    r = S.put(f"{BASE}/api/dewi/cutting/batches/{st['batch_id']}/status", json={"status": "in_cutting"})
    assert r.status_code >= 400, f"expected reject backward transition got {r.status_code}"
    print("PASS guard forward-only transition (mundur ditolak)")

def check_summary():
    r = S.get(f"{BASE}/api/dewi/cutting/summary")
    assert r.status_code == 200, f"summary {r.status_code}: {r.text}"
    print("PASS cutting summary 200")

def main():
    login(); create_request(); approve_request(); create_batch(); execute_batch(); guard_backward(); check_summary()
    print("\n=== CUTTING FLOW ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
