"""E2E API-level test for Material WO Flow: Reservasi (MI) -> Pengeluaran (issue) -> Retur.

Stok RM di-seed langsung ke koleksi rahaza_material_stock (tidak ada API stock-in di router ini).
"""
import os, requests, sys
from datetime import datetime, timezone
from pymongo import MongoClient

BASE = "http://localhost:8001"
S = requests.Session()
st = {}
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

def login():
    r = S.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"})
    r.raise_for_status()
    S.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    print("PASS login")

def _get_or_create(path, body, code_key="code"):
    r = S.post(f"{BASE}{path}", json=body)
    if r.status_code == 409:
        d = S.get(f"{BASE}{path}").json()
        rows = d if isinstance(d, list) else d.get("data", d.get("items", []))
        return next(x for x in rows if x.get(code_key) == body[code_key])
    assert r.status_code == 200, f"{path} {r.status_code}: {r.text}"
    return r.json()

def setup_master():
    mat = _get_or_create("/api/rahaza/materials", {"code": "E2E-MWO-FAB", "name": "E2E Kain WO", "type": "yarn", "unit": "kg", "min_stock": 0})
    st["material_id"] = mat["id"]
    # set unit_cost so inventory-issue auto-JE (Dr WIP / Cr Persediaan) posts with real value
    S.put(f"{BASE}/api/rahaza/materials/{st['material_id']}", json={"unit_cost": 50000})
    loc = _get_or_create("/api/rahaza/locations", {"code": "E2E-LOC", "name": "E2E Gudang WO"})
    st["location_id"] = loc["id"]
    print(f"PASS master material={st['material_id'][:8]} (unit_cost=50000) location={st['location_id'][:8]}")

def seed_stock():
    cli = MongoClient(MONGO_URL)
    db = cli[DB_NAME]
    db.rahaza_material_stock.update_one(
        {"material_id": st["material_id"], "location_id": st["location_id"]},
        {"$set": {"material_id": st["material_id"], "location_id": st["location_id"], "qty": 500.0,
                  "updated_at": datetime.now(timezone.utc)}},
        upsert=True,
    )
    cli.close()
    print("PASS seed stock qty=500 kg @ E2E-LOC")

def create_mi():
    body = {"items": [{"material_id": st["material_id"], "qty_required": 100, "location_id": st["location_id"], "unit": "kg"}],
            "notes": "E2E reservasi material WO"}
    r = S.post(f"{BASE}/api/rahaza/material-issues", json=body)
    assert r.status_code == 200, f"MI create {r.status_code}: {r.text}"
    mi = r.json()
    st["mid"] = mi["id"]
    assert mi["status"] == "draft", f"expected draft got {mi['status']}"
    print(f"PASS MI {mi['mi_number']} status=draft (reservasi 100 kg)")

def submit_mi():
    r = S.post(f"{BASE}/api/rahaza/material-issues/{st['mid']}/submit", json={})
    assert r.status_code == 200, f"MI submit {r.status_code}: {r.text}"
    assert r.json().get("status") == "pending_approval", f"got {r.json().get('status')}"
    print("PASS MI submit status=pending_approval")

def approve_mi():
    r = S.post(f"{BASE}/api/rahaza/material-issues/{st['mid']}/approve", json={})
    assert r.status_code == 200, f"MI approve {r.status_code}: {r.text}"
    out = r.json()
    assert out.get("status") == "issued", f"expected issued got {out.get('status')}"
    pr = out.get("_posting_result")
    print(f"PASS MI approve status=issued (pengeluaran stok) posting_ok={pr.get('ok') if isinstance(pr,dict) else pr}")

def create_return():
    body = {"work_order_id": "", "return_reason": "sisa_produksi", "notes": "E2E retur sisa",
            "items": [{"material_id": st["material_id"], "material_code": "E2E-MWO-FAB", "material_name": "E2E Kain WO",
                       "qty_returned": 20, "unit": "kg", "reason": "sisa_produksi", "condition": "good"}]}
    r = S.post(f"{BASE}/api/production/material-returns", json=body)
    assert r.status_code == 200, f"return create {r.status_code}: {r.text}"
    data = r.json().get("data") or r.json()
    st["return_id"] = data.get("id")
    print(f"PASS material-return created id={st['return_id']} qty=20")

def submit_return():
    r = S.post(f"{BASE}/api/production/material-returns/{st['return_id']}/submit", json={})
    assert r.status_code == 200, f"return submit {r.status_code}: {r.text}"
    print("PASS material-return submit")

def approve_return():
    r = S.post(f"{BASE}/api/production/material-returns/{st['return_id']}/approve", json={})
    assert r.status_code == 200, f"return approve {r.status_code}: {r.text}"
    print("PASS material-return approve")

def receive_return():
    r = S.post(f"{BASE}/api/production/material-returns/{st['return_id']}/receive", json={})
    assert r.status_code == 200, f"return receive {r.status_code}: {r.text}"
    print("PASS material-return receive (stok bertambah kembali)")

def main():
    login(); setup_master(); seed_stock(); create_mi(); submit_mi(); approve_mi()
    create_return(); submit_return(); approve_return(); receive_return()
    print("\n=== MATERIAL WO FLOW ALL PASS ===")

if __name__ == "__main__":
    try:
        main()
    except AssertionError as e:
        print(f"\nFAIL: {e}"); sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}"); sys.exit(2)
