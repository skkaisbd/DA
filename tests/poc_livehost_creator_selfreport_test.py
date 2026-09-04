#!/usr/bin/env python3
"""
POC — LiveHost & Creator self-report sales + sinkron ke Sales Marketing (Phase 6).

Menguji perbaikan schema drift + fitur baru:
  A) Create LiveHost (Bug A)          -> POST /marketing/livehost
  B) Create Shift (ShiftCreate fix)   -> POST /marketing/livehost/shifts
  C) Host login + clock in/out (ClockInOut fix) -> /portal/*
  D) Host record performance (ShiftPerformanceRecord fix) -> /shifts/{id}/performance
  E) Sync ke marketing_sales_data (revenue_type='live')
  F) Creator self-report session      -> POST /creator-portal/sessions
  G) Agregasi live sales = shift + session

Self-clean. Exit 0 = PASS.
"""
import os, sys, uuid, requests
sys.path.insert(0, "/app/backend"); os.chdir("/app/backend")
from pymongo import MongoClient
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]
BASE = "http://localhost:8001/api"
PASS = FAIL = 0
SUF = uuid.uuid4().hex[:6]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")
ACCOUNT_ID = f"poc-acc-{SUF}"  # throwaway account (deterministic aggregation)

created = {"host_email": f"poc_host_{SUF}@test.local", "creator_email": f"poc_creator_{SUF}@test.local",
           "host_id": None, "shift_id": None, "creator_id": None}


def setup_account():
    db.marketing_platform_accounts.insert_one({
        "id": ACCOUNT_ID, "account_code": f"POC-{SUF}", "account_name": f"POC Account {SUF}",
        "platform": "shopee", "status": "active", "_poc": True})


def ck(c, m):
    global PASS, FAIL
    if c: PASS += 1; print(f"  ✅ {m}")
    else: FAIL += 1; print(f"  ❌ {m}")


def admin_token():
    r = requests.post(f"{BASE}/auth/login", json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=15)
    return r.json()["token"]


def main():
    setup_account()
    A = admin_token(); H = {"Authorization": f"Bearer {A}"}

    print("\n== A: Create LiveHost (Bug A) ==")
    r = requests.post(f"{BASE}/marketing/livehost", headers=H, json={
        "name": f"POC Host {SUF}", "email": created["host_email"], "password": "Host@123",
        "phone": "0811", "employment_type": "part_time", "hourly_rate": 50000,
        "assigned_account_ids": [ACCOUNT_ID], "notes": "poc"}, timeout=15)
    ck(r.status_code == 200, f"create host HTTP {r.status_code} ({r.text[:120] if r.status_code!=200 else 'ok'})")
    if r.status_code == 200:
        created["host_id"] = r.json()["host"]["id"]

    print("\n== B: Create Shift (ShiftCreate fix) ==")
    r = requests.post(f"{BASE}/marketing/livehost/shifts", headers=H, json={
        "host_id": created["host_id"], "account_id": ACCOUNT_ID, "date": TODAY,
        "shift_type": "morning", "shift_start_time": "09:00", "shift_end_time": "13:00",
        "notes": "poc shift"}, timeout=15)
    ck(r.status_code == 200, f"create shift HTTP {r.status_code} ({r.text[:120] if r.status_code!=200 else 'ok'})")
    sh = db.marketing_livehost_shifts.find_one({"host_id": created["host_id"], "date": TODAY})
    created["shift_id"] = sh["id"] if sh else None
    ck(bool(created["shift_id"]), "shift tersimpan di DB")

    print("\n== C: Host login + clock in/out (ClockInOut fix) ==")
    r = requests.post(f"{BASE}/marketing/livehost/portal/auth/login",
                      json={"email": created["host_email"], "password": "Host@123"}, timeout=15)
    ck(r.status_code == 200, f"host login HTTP {r.status_code}")
    HT = {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else {}
    r = requests.post(f"{BASE}/marketing/livehost/portal/clock", headers=HT,
                      json={"shift_id": created["shift_id"], "action": "clock_in"}, timeout=15)
    ck(r.status_code == 200, f"clock_in HTTP {r.status_code} ({r.text[:100] if r.status_code!=200 else 'ok'})")
    r = requests.post(f"{BASE}/marketing/livehost/portal/clock", headers=HT,
                      json={"shift_id": created["shift_id"], "action": "clock_out"}, timeout=15)
    ck(r.status_code == 200, f"clock_out HTTP {r.status_code} ({r.text[:100] if r.status_code!=200 else 'ok'})")

    print("\n== D: Host record performance (ShiftPerformanceRecord fix) ==")
    r = requests.post(f"{BASE}/marketing/livehost/shifts/{created['shift_id']}/performance", headers=HT, json={
        "shift_id": created["shift_id"], "platform": "shopee", "viewers": 1200, "peak_viewers": 300,
        "revenue": 5000000, "orders": 40, "items_promoted": ["Kaos", "Celana"],
        "challenges_faced": "sinyal drop", "notes": "sesi lancar"}, timeout=15)
    ck(r.status_code == 200, f"record performance (host) HTTP {r.status_code} ({r.text[:140] if r.status_code!=200 else 'ok'})")

    print("\n== E: Sync ke Sales Marketing (revenue_type='live') ==")
    sd = db.marketing_sales_data.find_one({"account_id": ACCOUNT_ID, "date": TODAY, "revenue_type": "live"})
    ck(bool(sd), "marketing_sales_data 'live' entry dibuat")
    if sd:
        ck(sd["metrics"]["revenue"] == 5000000, f"revenue live = {sd['metrics']['revenue']} (expect 5,000,000)")
        ck(sd["metrics"]["orders"] == 40, f"orders live = {sd['metrics']['orders']} (expect 40)")
        ck(sd["source"] == "livehost_creator_auto", "source = livehost_creator_auto")

    print("\n== F: Creator self-report session ==")
    r = requests.post(f"{BASE}/marketing/kol/creators", headers=H, json={
        "name": f"POC Creator {SUF}", "creator_code": f"KOL-POC-{SUF}",
        "login_email": created["creator_email"], "login_password": "Creator@123",
        "assigned_account_ids": [ACCOUNT_ID], "kpi_targets": {"monthly_revenue": 10000000}}, timeout=15)
    ck(r.status_code == 200, f"create creator HTTP {r.status_code} ({r.text[:140] if r.status_code!=200 else 'ok'})")
    cr = db.marketing_kol_creators.find_one({"login_email": created["creator_email"]})
    created["creator_id"] = cr["id"] if cr else None
    r = requests.post(f"{BASE}/marketing/creator-portal/auth/login",
                      json={"email": created["creator_email"], "password": "Creator@123"}, timeout=15)
    ck(r.status_code == 200, f"creator login HTTP {r.status_code}")
    CT = {"Authorization": f"Bearer {r.json()['token']}"} if r.status_code == 200 else {}
    r = requests.post(f"{BASE}/marketing/creator-portal/sessions", headers=CT, json={
        "account_id": ACCOUNT_ID, "date": TODAY, "platform": "shopee",
        "session_name": "Live Sore POC", "viewers": 800, "peak_viewers": 150,
        "revenue": 3000000, "orders": 25, "items_promoted": ["Jaket"], "notes": "poc creator"}, timeout=15)
    ck(r.status_code == 200, f"creator self-report session HTTP {r.status_code} ({r.text[:140] if r.status_code!=200 else 'ok'})")

    print("\n== G: Agregasi live = shift + session ==")
    sd = db.marketing_sales_data.find_one({"account_id": ACCOUNT_ID, "date": TODAY, "revenue_type": "live"})
    ck(sd and sd["metrics"]["revenue"] == 8000000, f"revenue live agregat = {sd['metrics']['revenue'] if sd else None} (expect 8,000,000)")
    ck(sd and sd["metrics"]["orders"] == 65, f"orders live agregat = {sd['metrics']['orders'] if sd else None} (expect 65)")
    r = requests.get(f"{BASE}/marketing/creator-portal/my-sessions", headers=CT, timeout=15)
    ck(r.status_code == 200 and any(s.get("revenue") == 3000000 for s in r.json()), "my-sessions berisi sesi baru")
    r = requests.get(f"{BASE}/marketing/creator-portal/my-performance", headers=CT, timeout=15)
    ck(r.status_code == 200 and r.json()["summary"]["total_revenue"] == 3000000, "my-performance total_revenue = 3,000,000")


def cleanup():
    if created["shift_id"]:
        db.marketing_livehost_shifts.delete_many({"id": created["shift_id"]})
    db.marketing_livehosts.delete_many({"email": created["host_email"]})
    db.marketing_creator_sessions.delete_many({"creator_id": created["creator_id"]})
    db.marketing_kol_creators.delete_many({"login_email": created["creator_email"]})
    db.marketing_sales_data.delete_many({"account_id": ACCOUNT_ID})
    db.marketing_platform_accounts.delete_many({"id": ACCOUNT_ID})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); FAIL += 1
    finally:
        cleanup()
    print(f"\n==== RESULT: {PASS} PASS / {FAIL} FAIL ====")
    sys.exit(0 if FAIL == 0 else 1)
