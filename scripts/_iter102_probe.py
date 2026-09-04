import json
import os

import requests
from dotenv import dotenv_values

BASE = (os.environ.get("REACT_APP_BACKEND_URL") or dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"]).rstrip("/")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/125 Safari/537.36"
s = requests.Session()
s.headers.update({"Content-Type": "application/json", "User-Agent": UA})
s.headers["Authorization"] = "Bearer " + s.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}).json()["token"]

PO = os.environ.get("PO_ID", "f658f192-91b1-4fb6-b17d-e6ef67c1aea9")

r = s.get(f"{BASE}/api/production-tracking")
d = r.json()
print("TRACKING type:", type(d), "keys:", list(d)[:10] if isinstance(d, dict) else len(d))
print(json.dumps(d, default=str)[:2500])
print("=" * 60)
r = s.get(f"{BASE}/api/production-pos/{PO}/quantity-summary")
print("QTY-SUMMARY", r.status_code, json.dumps(r.json(), default=str)[:2000])
print("=" * 60)
r = s.get(f"{BASE}/api/buyer-dispatch-outstanding")
print("DISPATCH-OUTSTANDING", r.status_code, json.dumps(r.json(), default=str)[:1500])
print("=" * 60)
r = s.get(f"{BASE}/api/buyer-dispatch-capacity?po_id={PO}")
print("DISPATCH-CAPACITY", r.status_code, json.dumps(r.json(), default=str)[:1500])
