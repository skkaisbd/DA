"""
verify_b3_g1.py — E2E verification for WAVE-1 fixes (no mock; real API + DB).
  B3: RnD dashboard counts real statuses (pending_owner_review / approved_for_launch / promoted).
  G1: promote-to-production maps style.design_images[] -> rahaza_models.image_paths[].
Cleans up its own test rows afterward (keeps DB empty per user choice).
"""
import os, sys, time, requests
from pathlib import Path
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
BASE = "http://localhost:8001"
MONGO_URL = os.environ["MONGO_URL"]; DB_NAME = os.environ.get("DB_NAME", "garment_erp")
db = MongoClient(MONGO_URL)[DB_NAME]

CODE = f"TESTB3G1-{int(time.time())}"
IMGS = ["uploads/rnd_test_a.jpg", "uploads/rnd_test_b.jpg"]
results = []
def chk(name, cond, extra=""):
    results.append((name, cond, extra)); print(("PASS" if cond else "FAIL"), "-", name, extra)

def main():
    # login
    r = requests.post(f"{BASE}/api/auth/login", json={"email":"admin@garment.com","password":"Admin@123"}, timeout=15)
    tok = r.json()["token"]; H = {"Authorization": f"Bearer {tok}"}

    # baseline dashboard
    d0 = requests.get(f"{BASE}/api/dewi/rnd/dashboard", headers=H, timeout=15).json()["kpi"]
    chk("dashboard exposes new keys", all(k in d0 for k in ("review_styles","approved_styles","promoted_styles")), str({k:d0.get(k) for k in ("review_styles","approved_styles","promoted_styles")}))
    base_review = d0["review_styles"]; base_promoted = d0["promoted_styles"]

    # create style (internal)
    r = requests.post(f"{BASE}/api/dewi/rnd/styles", headers=H, json={"style_code":CODE,"style_name":"Test B3G1","rnd_type":"internal_product","category":"Kaos"}, timeout=15)
    chk("create style 200", r.status_code==200, f"HTTP {r.status_code}")
    sid = r.json()["id"]

    # set design_images via PUT
    requests.put(f"{BASE}/api/dewi/rnd/styles/{sid}", headers=H, json={"design_images":IMGS}, timeout=15)

    # submit for review -> pending_owner_review
    r = requests.post(f"{BASE}/api/dewi/rnd/styles/{sid}/submit-for-review", headers=H, json={}, timeout=15)
    chk("submit-for-review -> pending", r.json().get("status")=="pending_owner_review", r.json().get("status",""))

    # dashboard: review_styles (pending) should increment
    d1 = requests.get(f"{BASE}/api/dewi/rnd/dashboard", headers=H, timeout=15).json()["kpi"]
    chk("B3: review_styles counts pending_owner_review", d1["review_styles"]==base_review+1, f"{base_review}->{d1['review_styles']}")

    # owner approve -> approved_for_launch
    r = requests.post(f"{BASE}/api/dewi/rnd/styles/{sid}/owner-approve", headers=H, json={}, timeout=15)
    chk("owner-approve -> approved_for_launch", r.json().get("status")=="approved_for_launch", r.json().get("status",""))
    d2 = requests.get(f"{BASE}/api/dewi/rnd/dashboard", headers=H, timeout=15).json()["kpi"]
    chk("B3: approved_styles increments", d2["approved_styles"]>=1, f"approved={d2['approved_styles']}")

    # promote -> creates rahaza_model
    r = requests.post(f"{BASE}/api/dewi/rnd/styles/{sid}/promote-to-production", headers=H, json={}, timeout=15)
    chk("promote 200", r.status_code==200, f"HTTP {r.status_code} {r.text[:120]}")
    model_id = r.json().get("model_id")

    # G1: verify model.image_paths == design_images (DB direct)
    model = db.rahaza_models.find_one({"id": model_id}) or {}
    chk("G1: model has image_paths from design_images", model.get("image_paths")==IMGS, f"got={model.get('image_paths')}")

    # B3: promoted_styles increments
    d3 = requests.get(f"{BASE}/api/dewi/rnd/dashboard", headers=H, timeout=15).json()["kpi"]
    chk("B3: promoted_styles increments", d3["promoted_styles"]==base_promoted+1, f"{base_promoted}->{d3['promoted_styles']}")

    # CLEANUP (keep DB empty)
    db.dewi_rnd_styles.delete_one({"id": sid})
    if model_id: db.rahaza_models.delete_one({"id": model_id})
    print("\n[cleanup] removed test style + model")

    passed = sum(1 for _,c,_ in results if c); total=len(results)
    print(f"\n==== {passed}/{total} PASSED ====")
    sys.exit(0 if passed==total else 1)

if __name__ == "__main__":
    main()
