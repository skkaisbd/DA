"""Seed data untuk uji FRONTEND iterasi 103: satu PO internal produced=10 BELUM dikirim."""
import json
import os
import random
from datetime import date, timedelta

import requests
from dotenv import dotenv_values

env = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or env["REACT_APP_BACKEND_URL"]).rstrip("/")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"

s = requests.Session()
s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
r = s.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60)
r.raise_for_status()
s.headers["Authorization"] = f"Bearer {r.json().get('token') or r.json()['access_token']}"


def L(b):
    return b if isinstance(b, list) else (b.get("data") or b.get("items") or [])


bom = [b for b in L(s.get(f"{BASE}/api/rahaza/boms?per_page=100").json())
       if b.get("model_id") and b.get("size_id") and b.get("is_active") is not False][0]
po_number = f"PO-INT-{date.today():%Y%m}-{random.randint(9000, 9899)}"
po = s.post(f"{BASE}/api/production-pos", json={
    "po_number": po_number, "business_type": "internal",
    "customer_name": "TEST_ITER103 FE Buyer", "po_date": date.today().isoformat(),
    "deadline": (date.today() + timedelta(days=20)).isoformat(),
    "delivery_deadline": (date.today() + timedelta(days=25)).isoformat(),
    "notes": "TEST_ITER103 seed frontend",
    "items": [{"model_id": bom["model_id"], "size_id": bom["size_id"], "qty": 25}]}, timeout=120).json()
s.post(f"{BASE}/api/production-pos/{po['id']}/status", json={"status": "Confirmed"}, timeout=60)
job = s.post(f"{BASE}/api/production-jobs", json={"po_id": po["id"]}, timeout=180).json()
mi = s.post(f"{BASE}/api/rahaza/material-issues/draft-from-job", json={"job_id": job["id"]}, timeout=120).json()
loc = L(s.get(f"{BASE}/api/rahaza/locations").json())[0]["id"]
items = [{**it, "location_id": loc} for it in mi["items"]]
s.put(f"{BASE}/api/rahaza/material-issues/{mi['id']}", json={"items": items}, timeout=60)
for it in items:
    s.post(f"{BASE}/api/rahaza/material-receive",
           json={"material_id": it["material_id"], "location_id": loc,
                 "qty": float(it.get("qty_required") or 0) + 10, "unit_cost": 10000,
                 "notes": "TEST_ITER103 top-up"}, timeout=120)
s.post(f"{BASE}/api/rahaza/material-issues/{mi['id']}/submit", json={}, timeout=60)
s.post(f"{BASE}/api/rahaza/material-issues/{mi['id']}/approve", json={}, timeout=180)
emps = L(s.get(f"{BASE}/api/rahaza/employees?per_page=50").json())
procs = [p for p in L(s.get(f"{BASE}/api/rahaza/processes?per_page=50").json()) if p.get("active") is not False]
sew = next((p for p in procs if any(w in f"{p.get('process_type') or ''} {p.get('name') or ''}".lower()
                                    for w in ("jahit", "sew"))), procs[0])
pr = s.post(f"{BASE}/api/production-progress", json={
    "job_id": job["id"], "job_item_id": job["items"][0]["id"], "completed_quantity": 10,
    "operator_id": emps[0]["id"], "process_id": sew["id"], "notes": "TEST_ITER103 FE"}, timeout=180)
cap = s.get(f"{BASE}/api/buyer-dispatch-capacity?po_item_ids={po['items'][0]['id']}&with_fg_stock=1").json()
print(json.dumps({"po_id": po["id"], "po_number": po["po_number"], "progress": pr.status_code,
                  "capacity": cap.get("items", [{}])[0]}, indent=1))
