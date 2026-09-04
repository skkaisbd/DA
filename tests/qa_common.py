#!/usr/bin/env python3
"""QA deep-probe helpers: self-login (rate-limit aware), assertion recorder.
Shared by qa_probe_*.py. Focus: OUTPUT CORRECTNESS, not just HTTP status."""
import requests, time, sys

BASE = "http://localhost:8001"

def login(email="admin@garment.com", password="Admin@123", retries=6):
    for i in range(retries):
        try:
            r = requests.post(f"{BASE}/api/auth/login",
                              json={"email": email, "password": password}, timeout=20)
            if r.status_code == 200 and r.json().get("token"):
                return r.json()["token"]
            # rate-limited -> wait
            if r.status_code == 429 or "rate" in r.text.lower():
                time.sleep(7); continue
        except Exception as e:
            time.sleep(3)
    raise RuntimeError(f"login failed after {retries} tries: {r.status_code} {r.text[:120]}")

class Probe:
    def __init__(self, token):
        self.h = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self.results = []
    def rec(self, name, ok, detail=""):
        self.results.append((ok, name, detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {name} :: {detail}")
    def g(self, p, **k): return requests.get(BASE+p, headers=self.h, timeout=30, **k)
    def p(self, p, b=None): return requests.post(BASE+p, headers=self.h, json=(b or {}), timeout=30)
    def put(self, p, b=None): return requests.put(BASE+p, headers=self.h, json=(b or {}), timeout=30)
    def d(self, p): return requests.delete(BASE+p, headers=self.h, timeout=30)
    def summary(self, label):
        fails = [r for r in self.results if not r[0]]
        print("="*70)
        print(f"{label}: {len(self.results)-len(fails)}/{len(self.results)} PASS, {len(fails)} FAIL")
        for ok,n,dd in fails: print(f"   FAIL: {n} :: {dd}")
        return len(fails)
