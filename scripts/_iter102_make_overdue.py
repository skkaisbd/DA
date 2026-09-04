"""Buat PO internal + job dengan deadline LAMPAU supaya baris WO muncul di tab
Overdue Pusat Kendali (satu-satunya tempat baris WO dirender di UI)."""
import os
import random
from datetime import date

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36"
s = requests.Session()
s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
s.headers["Authorization"] = "Bearer " + s.post(
    f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}).json()["token"]

boms = s.get(f"{BASE}/api/rahaza/boms?per_page=50").json()
boms = boms if isinstance(boms, list) else boms.get("data") or boms.get("items")
bom = [b for b in boms if b.get("model_id") and b.get("size_id")][0]

payload = {
    "po_number": f"PO-INT-{date.today():%Y%m}-{random.randint(9900, 9989)}",
    "business_type": "internal",
    "customer_name": "TEST_ITER102 Overdue Buyer",
    "po_date": "2026-08-01",
    "deadline": "2026-08-20",
    "delivery_deadline": "2026-08-25",
    "notes": "TEST_ITER102 overdue untuk uji baris WO Pusat Kendali",
    "items": [{"model_id": bom["model_id"], "size_id": bom["size_id"], "qty": 15}],
}
r = s.post(f"{BASE}/api/production-pos", json=payload)
print("PO:", r.status_code, r.text[:200])
po = r.json()
print(s.post(f"{BASE}/api/production-pos/{po['id']}/status", json={"status": "Confirmed"}).status_code)
rj = s.post(f"{BASE}/api/production-jobs", json={"po_id": po["id"]})
print("JOB:", rj.status_code, rj.json().get("job_number"))
ct = s.get(f"{BASE}/api/prod/control-tower").json()
print("KPIs:", {k: ct["kpis"][k] for k in ("active_wos", "total_target_qty", "total_produced_qty", "overdue", "at_risk", "unknown_deadline")})
print("overdue_wos:", [(w["wo_number"], w["qty"]) for w in ct["overdue_wos"]])
