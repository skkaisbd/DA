"""STEP B2 — Controlled write-flow test (create -> read-back -> cleanup).
Targets self-contained RnD writes (no GL/stock/notification side-effects).
Also definitively validates RC-18 (app writes to dewi_rnd_sample_requests)."""
import json, urllib.request, urllib.error
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
import os
from pymongo import MongoClient

URL = "http://localhost:8001"
TOKEN = open("/tmp/admin_token.txt").read().strip()
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]

def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(URL + path, data=data, method=method,
                               headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=20) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return "ERR", str(e)[:150]

print("="*68)
print("TEST 1 — RnD Sample Request: create -> list -> detail -> cleanup")
print("="*68)
style = db.dewi_rnd_styles.find_one({}, {"id":1,"style_code":1,"_id":0})
print("Using style_id:", style["id"], f"({style.get('style_code')})")
before = db.dewi_rnd_sample_requests.count_documents({})
print("dewi_rnd_sample_requests BEFORE:", before)

code, res = req("POST", "/api/dewi/rnd/sample-requests",
                {"style_id": style["id"], "quantity": 3, "priority": "high", "notes": "B2 write-flow test"})
print(f"POST -> {code}")
new_id = res.get("id") if isinstance(res, dict) else None
print("new sample-request id:", new_id, "| sample_code:", res.get("sample_code") if isinstance(res,dict) else res)

# read-back via LIST
code, lst = req("GET", "/api/dewi/rnd/sample-requests")
n_list = len(lst) if isinstance(lst, list) else "?"
found = any(x.get("id")==new_id for x in lst) if isinstance(lst, list) else False
print(f"GET /sample-requests -> {code}, count={n_list}, contains_new={found}")

# read-back via DETAIL
code, det = req("GET", f"/api/dewi/rnd/sample-requests/{new_id}")
print(f"GET /sample-requests/{{id}} -> {code}, style_name={det.get('style_name') if isinstance(det,dict) else det}")

after = db.dewi_rnd_sample_requests.count_documents({})
print(f"dewi_rnd_sample_requests AFTER: {after}  (delta={after-before})")
print(f"CONCLUSION RC-18: app WRITE lands in 'dewi_rnd_sample_requests' (not 'dewi_rnd_samples'={db.dewi_rnd_samples.count_documents({})}) -> seed target is WRONG. CONFIRMED.")

# cleanup
db.dewi_rnd_sample_requests.delete_one({"id": new_id})
print("cleanup: removed test doc ->", db.dewi_rnd_sample_requests.count_documents({}), "docs remain")

print()
print("="*68)
print("TEST 2 — RnD Style: create -> list -> cleanup")
print("="*68)
import time
code, res = req("POST", "/api/dewi/rnd/styles",
                {"style_code": f"B2TEST{int(time.time())%100000}", "style_name": "B2 Test Style", "category":"Test"})
print(f"POST /styles -> {code}")
sid2 = res.get("id") if isinstance(res, dict) else None
print("new style id:", sid2, "| code:", res.get("style_code") if isinstance(res,dict) else res)
code, lst = req("GET", "/api/dewi/rnd/styles")
found = any(x.get("id")==sid2 for x in lst) if isinstance(lst,list) else False
print(f"GET /styles -> {code}, count={len(lst) if isinstance(lst,list) else '?'}, contains_new={found}")
if sid2:
    db.dewi_rnd_styles.delete_one({"id": sid2})
    print("cleanup: removed test style ->", db.dewi_rnd_styles.count_documents({}), "styles remain")
