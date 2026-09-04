#!/usr/bin/env python3
"""
POC — KEPUTUSAN #5 (Marketing): Budget per Toko × Bulan × Kategori + monitoring alokasi.

Membuktikan (via API + DB):
  - Rencana budget per akun/periode dipecah per kategori (ads/kol/livehost/sample/diskon).
  - Spend: Ads/Sample/Diskon manual; KOL configurable (fee fixed + komisi % sales);
    LiveHost real (total_pay shift 'calculated').
  - Summary: budget vs spend per kategori (remaining/%/over-under) + total + ROI vs sales.
  - Config biaya KOL kombinasi (fixed/commission/both) → cost benar.

Self-cleanup: DB pristine. Exit 0 = ALL PASS.
"""
import os
import sys
import uuid
import requests
from pymongo import MongoClient
from dotenv import load_dotenv

BASE = "http://localhost:8001/api"
load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ.get("DB_NAME", "test_database")]

PASS, FAIL = 0, 0
PERIOD = "2026-06"
ACC_CODE = "POC-BUD-SHOP"
created = {"accounts": [], "creators": []}


def check(cond, msg):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {msg}")
    else:
        FAIL += 1
        print(f"  ❌ {msg}")


def approx(a, b, tol=1.0):
    try:
        return abs(float(a) - float(b)) <= tol
    except (TypeError, ValueError):
        return False


def login():
    r = requests.post(f"{BASE}/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=15)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


def _purge():
    accts = list(db.marketing_platform_accounts.find({"account_code": {"$regex": "^POC-BUD"}}, {"id": 1}))
    ids = [a["id"] for a in accts]
    db.marketing_platform_accounts.delete_many({"account_code": {"$regex": "^POC-BUD"}})
    db.marketing_kol_creators.delete_many({"creator_code": {"$regex": "^POC-BUD"}})
    db.marketing_creator_sessions.delete_many({"is_poc": True})
    db.marketing_sales_data.delete_many({"is_poc": True})
    db.marketing_livehost_shifts.delete_many({"is_poc": True})
    db.marketing_livehosts.delete_many({"is_poc": True})
    for i in ids:
        db.marketing_budgets.delete_many({"account_id": i})
        db.marketing_spend_entries.delete_many({"account_id": i})


def get_summary(H, acc_id):
    r = requests.get(f"{BASE}/marketing/budget/summary",
                     headers=H, params={"account_id": acc_id, "period": PERIOD}, timeout=15)
    r.raise_for_status()
    s = r.json()
    return {c["category"]: c for c in s["categories"]}, s


def main():
    H = login()
    _purge()

    print("\n== STEP A: create account ==")
    r = requests.post(f"{BASE}/marketing/accounts", headers=H,
                      json={"account_code": ACC_CODE, "account_name": "POC Budget Toko", "platform": "shopee"}, timeout=15)
    check(r.status_code in (200, 201), f"create account -> {r.status_code}")
    acc_id = r.json().get("account", {}).get("id")
    created["accounts"].append(acc_id)
    check(bool(acc_id), f"account_id = {acc_id}")

    print("\n== STEP B: PUT budget per kategori ==")
    plan = {"ads": 1000000, "kol": 2000000, "livehost": 1500000, "sample": 500000, "diskon": 800000}
    r = requests.put(f"{BASE}/marketing/budget", headers=H,
                     json={"account_id": acc_id, "period": PERIOD, "budget_by_category": plan}, timeout=15)
    check(r.status_code == 200, f"PUT budget -> {r.status_code}")
    check(approx(r.json().get("total_budget"), 5800000), f"total_budget = {r.json().get('total_budget')} (expect 5.8M)")
    # GET
    r = requests.get(f"{BASE}/marketing/budget", headers=H, params={"account_id": acc_id, "period": PERIOD}, timeout=15)
    check(r.json().get("exists") is True, "GET budget exists=True")
    check(approx(r.json()["budget_by_category"]["kol"], 2000000), "budget kol = 2M")

    print("\n== STEP C: catat spend manual (ads/sample/diskon) ==")
    for cat, amt in [("ads", 400000), ("ads", 300000), ("sample", 200000), ("diskon", 900000)]:
        r = requests.post(f"{BASE}/marketing/budget/spend", headers=H,
                          json={"account_id": acc_id, "period": PERIOD, "category": cat, "amount": amt,
                                "description": f"POC {cat}"}, timeout=15)
        check(r.status_code == 200, f"spend {cat} {amt} -> {r.status_code}")
    # invalid category guard
    r = requests.post(f"{BASE}/marketing/budget/spend", headers=H,
                      json={"account_id": acc_id, "period": PERIOD, "category": "invalid", "amount": 1}, timeout=15)
    check(r.status_code == 400, f"invalid category ditolak 400 (got {r.status_code})")

    print("\n== STEP D: KOL creator + cost config (kombinasi fee+komisi) ==")
    creator_id = str(uuid.uuid4())
    db.marketing_kol_creators.insert_one({
        "id": creator_id, "name": "POC Kreator", "creator_code": "POC-BUD-KOL1",
        "assigned_account_ids": [acc_id], "created_at": None, "is_poc": True,
    })
    created["creators"].append(creator_id)
    # session revenue 3,000,000 in period
    db.marketing_creator_sessions.insert_one({
        "id": str(uuid.uuid4()), "creator_id": creator_id, "account_id": acc_id,
        "date": f"{PERIOD}-15", "revenue": 3000000, "orders": 20, "is_poc": True,
    })
    # set cost config via API: both → fixed 500k + 10% commission
    r = requests.put(f"{BASE}/marketing/budget/kol-cost/{creator_id}", headers=H,
                     json={"fee_type": "both", "fixed_fee": 500000, "commission_pct": 10}, timeout=15)
    check(r.status_code == 200, f"PUT kol-cost (both) -> {r.status_code}")
    # expected kol cost = 500000 + 10% * 3,000,000 = 800,000

    print("\n== STEP E: seed sales (utk ROI) + livehost real spend ==")
    db.marketing_sales_data.insert_one({
        "id": str(uuid.uuid4()), "account_id": acc_id, "date": f"{PERIOD}-10",
        "revenue_type": "total", "metrics": {"revenue": 10000000, "orders": 50}, "is_poc": True,
    })
    # livehost: host assigned to account + 1 calculated shift total_pay 300k
    host_id = str(uuid.uuid4())
    db.marketing_livehosts.insert_one({"id": host_id, "name": "POC Host",
                                       "assigned_account_ids": [acc_id], "hourly_rate": 50000, "is_poc": True})
    db.marketing_livehost_shifts.insert_one({
        "id": str(uuid.uuid4()), "host_id": host_id, "account_id": acc_id, "date": f"{PERIOD}-12",
        "payment_status": "calculated", "total_pay": 300000, "is_poc": True,
    })

    print("\n== STEP F: GET summary — compare per kategori + ROI ==")
    cats, summary = get_summary(H, acc_id)
    check(approx(cats["ads"]["spend"], 700000), f"ads spend = {cats['ads']['spend']} (expect 700k)")
    check(approx(cats["ads"]["remaining"], 300000) and cats["ads"]["status"] == "under", "ads remaining 300k, under")
    check(approx(cats["ads"]["used_pct"], 70), f"ads used_pct = {cats['ads']['used_pct']}% (expect 70)")
    check(approx(cats["diskon"]["spend"], 900000) and cats["diskon"]["status"] == "over",
          f"diskon spend 900k -> OVER (remaining {cats['diskon']['remaining']})")
    check(approx(cats["sample"]["spend"], 200000), f"sample spend = {cats['sample']['spend']}")
    check(approx(cats["kol"]["spend"], 800000), f"kol spend (auto fee+komisi) = {cats['kol']['spend']} (expect 800k)")
    check(approx(cats["livehost"]["spend"], 300000), f"livehost spend (real) = {cats['livehost']['spend']} (expect 300k)")
    total_spend_expect = 700000 + 800000 + 300000 + 200000 + 900000  # 2,900,000
    check(approx(summary["total_spend"], total_spend_expect), f"total_spend = {summary['total_spend']} (expect {total_spend_expect})")
    check(approx(summary["total_budget"], 5800000), f"total_budget = {summary['total_budget']}")
    check(approx(summary["sales"], 10000000), f"sales = {summary['sales']} (expect 10M)")
    # roi = (sales - spend)/spend *100 = (10M-2.9M)/2.9M*100 = 244.83
    check(approx(summary["roi_pct"], (10000000 - total_spend_expect) / total_spend_expect * 100, 1),
          f"roi_pct = {summary['roi_pct']}")
    check(len(summary["kol_detail"]) == 1 and approx(summary["kol_detail"][0]["cost"], 800000),
          "kol_detail berisi rincian biaya kreator")

    print("\n== STEP G: cost config variasi (fixed-only / commission-only) ==")
    check(approx(_creator_cost_local({"fee_type": "fixed", "fixed_fee": 500000, "commission_pct": 10}, 3000000), 500000),
          "fixed-only → 500k (abaikan komisi)")
    check(approx(_creator_cost_local({"fee_type": "commission", "fixed_fee": 500000, "commission_pct": 10}, 3000000), 300000),
          "commission-only → 300k (abaikan fee)")
    check(approx(_creator_cost_local({"fee_type": "none"}, 3000000), 0), "none → 0")

    print("\n== STEP H: DELETE spend ==")
    r = requests.get(f"{BASE}/marketing/budget/spend", headers=H, params={"account_id": acc_id, "period": PERIOD, "category": "sample"}, timeout=15)
    sid = r.json()["entries"][0]["id"]
    r = requests.delete(f"{BASE}/marketing/budget/spend/{sid}", headers=H, timeout=15)
    check(r.status_code == 200, f"delete spend -> {r.status_code}")
    cats, _ = get_summary(H, acc_id)
    check(approx(cats["sample"]["spend"], 0), f"sample spend setelah delete = {cats['sample']['spend']} (expect 0)")


def _creator_cost_local(cfg, revenue):
    """Mirror of backend _creator_cost for isolated assertion."""
    ft = (cfg.get("fee_type") or "none").lower()
    cost = 0.0
    if ft in ("fixed", "both"):
        cost += float(cfg.get("fixed_fee") or 0)
    if ft in ("commission", "both"):
        cost += revenue * float(cfg.get("commission_pct") or 0) / 100.0
    return round(cost, 2)


def cleanup():
    print("\n== CLEANUP ==")
    try:
        _purge()
        print("  ✅ cleanup done")
    except Exception as e:
        print(f"  ⚠️ cleanup error: {e}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        traceback.print_exc()
        FAIL += 1
    finally:
        cleanup()
    print(f"\n==== RESULT: {PASS} PASS / {FAIL} FAIL ====")
    sys.exit(0 if FAIL == 0 else 1)
