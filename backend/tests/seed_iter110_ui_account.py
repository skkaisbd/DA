"""Seed a fresh cash account for iteration 110 frontend UI test."""
import os
import uuid

import requests
from dotenv import dotenv_values

fe = dotenv_values("/app/frontend/.env")
BASE = (os.environ.get("REACT_APP_BACKEND_URL") or fe.get("REACT_APP_BACKEND_URL")).rstrip("/")
tok = requests.post(f"{BASE}/api/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60).json()["token"]
H = {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}
sfx = uuid.uuid4().hex[:4].upper()
r = requests.post(f"{BASE}/api/rahaza/cash-accounts", headers=H, timeout=60, json={
    "code": f"UI-{sfx}", "name": f"UI Recon {sfx}", "type": "bank", "gl_account_code": "1-1201", "opening_balance": 0})
print(r.status_code, r.json().get("name"), r.json().get("id"))
