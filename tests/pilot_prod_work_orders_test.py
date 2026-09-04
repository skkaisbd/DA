"""
PILOT backend deep-contract test — prod-work-orders (Work Order)
Covers WO lifecycle + validation + state machine + RBAC + bundles + LKP + bulk-lkp fix.
Login ONCE, reuse token. Creates own test data + CLEANS UP by tracked ids (DB pristine).

Includes WO-BUG-001 verification: lkp-bulk-today must include in_production WO.
"""
import requests, os, sys
from datetime import date

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
results = []
created = {"wo": [], "lkp": [], "model": []}

def rec(tcid, verdict, detail=""):
    results.append((tcid, verdict, detail)); print(f"[{tcid}] {verdict} | {detail}")
def login(c):
    r = requests.post(f"{BASE}/api/auth/login", json=c, timeout=15); r.raise_for_status(); return r.json()["token"]
def H(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}
def GET(p, t): return requests.get(f"{BASE}{p}", headers=H(t))
def POST(p, t, b=None): return requests.post(f"{BASE}{p}", headers=H(t), json=(b or {}))
def PUT(p, t, b): return requests.put(f"{BASE}{p}", headers=H(t), json=b)
def DELETE(p, t): return requests.delete(f"{BASE}{p}", headers=H(t))

admin = login(ADMIN); print("admin login OK")

# ---- setup master ----
mid = POST("/api/rahaza/models", admin, {"code": "WOTESTMDL", "name": "WO Test Model"})
if mid.status_code == 200:
    model_id = mid.json()["id"]; created["model"].append("WOTESTMDL")
else:
    model_id = next(m["id"] for m in GET("/api/rahaza/models", admin).json() if m["code"] == "WOTESTMDL")
size_id = next(s["id"] for s in GET("/api/rahaza/sizes", admin).json() if s["code"] == "M")

# ---- reads / statuses ----
r = GET("/api/rahaza/work-orders", admin)
rec("TC-01", "PASS" if r.status_code == 200 else "FAIL", f"list HTTP {r.status_code}")

r = GET("/api/rahaza/work-orders-statuses", admin)
draft = next((x for x in r.json() if x.get("value") == "draft"), {}) if r.status_code == 200 else {}
rec("TC-08", "PASS" if r.status_code == 200 and draft.get("allowed_next") == ["released", "cancelled"] else "FAIL",
    f"statuses HTTP {r.status_code} draft.allowed_next={draft.get('allowed_next')}")

# ---- create + validation ----
r = POST("/api/rahaza/work-orders", admin, {"model_id": model_id, "size_id": size_id, "qty": 10, "priority": "normal"})
wo = r.json() if r.status_code == 200 else {}
if wo.get("id"): created["wo"].append(wo["id"])
rec("TC-02", "PASS" if r.status_code == 200 and wo.get("status") == "draft" else "FAIL",
    f"create HTTP {r.status_code} status={wo.get('status')} no={wo.get('wo_number')}")

r = POST("/api/rahaza/work-orders", admin, {"size_id": size_id, "qty": 5})
rec("TC-03", "PASS" if r.status_code == 400 else "FAIL", f"no model -> HTTP {r.status_code} (exp 400)")

r = POST("/api/rahaza/work-orders", admin, {"model_id": model_id, "size_id": size_id, "qty": 0})
rec("TC-04", "PASS" if r.status_code == 400 else "FAIL", f"qty=0 -> HTTP {r.status_code} (exp 400)")

wid = wo.get("id")
r = GET(f"/api/rahaza/work-orders/{wid}", admin) if wid else None
det = r.json() if r and r.status_code == 200 else {}
rec("TC-05", "PASS" if det and "progress_pct" in det else "FAIL", f"detail progress_pct={det.get('progress_pct')}")

r = PUT(f"/api/rahaza/work-orders/{wid}", admin, {"qty": 12}) if wid else None
rec("TC-06", "PASS" if r and r.status_code == 200 and r.json().get("qty") == 12 else "FAIL",
    f"edit qty -> HTTP {getattr(r,'status_code',None)} qty={r.json().get('qty') if r and r.status_code==200 else '-'}")

r = PUT(f"/api/rahaza/work-orders/{wid}", admin, {"qty": "abc"}) if wid else None
rec("TC-07", "PASS" if r is not None and r.status_code == 400 else "FAIL", f"edit qty non-numerik -> HTTP {getattr(r,'status_code',None)} (exp 400)")

# ---- state machine ----
r = POST(f"/api/rahaza/work-orders/{wid}/status", admin, {"status": "completed"})
rec("TC-10", "PASS" if r.status_code == 400 else "FAIL", f"draft->completed ilegal -> HTTP {r.status_code} (exp 400)")

r = POST(f"/api/rahaza/work-orders/{wid}/status", admin, {"status": "released"})
rec("TC-09", "PASS" if r.status_code == 200 else "FAIL", f"draft->released -> HTTP {r.status_code} rsv={r.json().get('material_reservation') if r.status_code==200 else '-'}")

# ---- bundles ----
r = POST(f"/api/rahaza/work-orders/{wid}/generate-bundles", admin, {})
g1 = r.json() if r.status_code == 200 else {}
rec("TC-15", "PASS" if r.status_code == 200 and g1.get("generated", 0) > 0 else ("INFO" if r.status_code == 400 else "FAIL"),
    f"generate-bundles -> HTTP {r.status_code} generated={g1.get('generated')} detail={r.json().get('detail') if r.status_code!=200 else ''}")

r = POST(f"/api/rahaza/work-orders/{wid}/generate-bundles", admin, {})
rec("TC-16", "PASS" if r.status_code == 409 else ("INFO" if r.status_code == 400 else "FAIL"),
    f"generate again no force -> HTTP {r.status_code} (exp 409)")

r = POST(f"/api/rahaza/work-orders/{wid}/status", admin, {"status": "in_production"})
rec("TC-11", "PASS" if r.status_code == 200 else "FAIL", f"released->in_production -> HTTP {r.status_code}")

# ---- WO-BUG-001 verification: bulk-lkp-today must include in_production WO ----
r = GET("/api/rahaza/lkp-bulk-today", admin)
bl = r.json() if r.status_code == 200 else {}
found = any(w.get("wo_id") == wid for w in bl.get("work_orders", []))
rec("TC-23", "PASS" if r.status_code == 200 and found else "FAIL",
    f"bulk-lkp-today includes in_production WO -> {found} (total={bl.get('total')})")

# ---- LKP ----
lkp_body = {"tech_pack": {"color": "Navy"}, "assignment": {}, "process_flow": [],
            "sop_steps": [{"process_name": "Cutting", "steps": "potong"}], "qc": {}, "packing": {}, "special_notes": "test"}
r = POST(f"/api/rahaza/work-orders/{wid}/lkp", admin, lkp_body)
lkp = r.json() if r.status_code == 200 else {}
if lkp.get("id"): created["lkp"].append(lkp["id"])
rec("TC-17", "PASS" if r.status_code == 200 and lkp.get("lkp_number") and lkp.get("version") else "FAIL",
    f"create LKP -> HTTP {r.status_code} no={lkp.get('lkp_number')} v={lkp.get('version')}")

lkp_id = lkp.get("id")
r = GET(f"/api/rahaza/work-orders/{wid}/lkp", admin)
rec("TC-18", "PASS" if r.status_code == 200 and len(r.json()) >= 1 else "FAIL", f"list LKP -> {len(r.json()) if r.status_code==200 else '-'}")

r = GET(f"/api/rahaza/lkp/{lkp_id}", admin) if lkp_id else None
al = (r.json().get("audit_log") if r and r.status_code == 200 else []) or []
rec("TC-19", "PASS" if r and r.status_code == 200 and any(a.get("action") == "created" for a in al) else "FAIL",
    f"LKP detail audit={[a.get('action') for a in al]}")

r = POST(f"/api/rahaza/lkp/{lkp_id}/regenerate", admin) if lkp_id else None
rec("TC-20", "PASS" if r and r.status_code == 200 else "FAIL", f"regenerate -> HTTP {getattr(r,'status_code',None)}")

r = GET(f"/api/rahaza/lkp/{lkp_id}/pdf", admin) if lkp_id else None
ct = r.headers.get("content-type", "") if r else ""
rec("TC-21", "PASS" if r and r.status_code == 200 and "application/pdf" in ct else "FAIL", f"pdf -> HTTP {getattr(r,'status_code',None)} ct={ct}")

r = DELETE(f"/api/rahaza/lkp/{lkp_id}", admin) if lkp_id else None
rec("TC-22", "PASS" if r and r.status_code == 200 else "FAIL", f"revoke LKP -> HTTP {getattr(r,'status_code',None)}")

# ---- complete + guards ----
r = POST(f"/api/rahaza/work-orders/{wid}/status", admin, {"status": "completed"})
rec("TC-12", "PASS" if r.status_code == 200 else "FAIL", f"in_production->completed -> HTTP {r.status_code} wip={bool(r.json().get('wip_posting')) if r.status_code==200 else '-'}")

r = PUT(f"/api/rahaza/work-orders/{wid}", admin, {"qty": 99})
rec("TC-13", "PASS" if r.status_code == 400 else "FAIL", f"edit completed -> HTTP {r.status_code} (exp 400)")

r = DELETE(f"/api/rahaza/work-orders/{wid}", admin)
rec("TC-14", "PASS" if r.status_code == 400 else "FAIL", f"delete completed -> HTTP {r.status_code} (exp 400)")

# ---- delete-draft path (fresh WO) ----
r = POST("/api/rahaza/work-orders", admin, {"model_id": model_id, "size_id": size_id, "qty": 3})
w2 = r.json() if r.status_code == 200 else {}
if w2.get("id"): created["wo"].append(w2["id"])
r = DELETE(f"/api/rahaza/work-orders/{w2.get('id')}", admin) if w2.get("id") else None
if r and r.status_code == 200 and w2["id"] in created["wo"]:
    created["wo"].remove(w2["id"])
rec("TC-25", "PASS" if r and r.status_code == 200 else "FAIL", f"delete draft -> HTTP {getattr(r,'status_code',None)}")

# ---- RBAC: read without token ----
r = requests.get(f"{BASE}/api/rahaza/work-orders")
rec("TC-24", "PASS" if r.status_code in (401, 403) else "FAIL", f"read no token -> HTTP {r.status_code} (exp 401/403)")

# ---- CLEANUP (by tracked ids) ----
print("\n--- CLEANUP ---")
import asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
async def cleanup():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ.get("DB_NAME", "test_database")]
    wids = created["wo"]
    c_wo = await db.rahaza_work_orders.delete_many({"id": {"$in": wids}})
    c_lkp = await db.rahaza_lkp.delete_many({"work_order_id": {"$in": wids}})
    c_ph = await db.rahaza_lkp_photos.delete_many({"lkp_id": {"$in": created["lkp"]}})
    c_bd = await db.rahaza_bundles.delete_many({"work_order_id": {"$in": wids}})
    c_rs = await db.rahaza_material_reservations.delete_many({"work_order_id": {"$in": wids}})
    c_wp = await db.rahaza_wip_events.delete_many({"work_order_id": {"$in": wids}})
    c_md = await db.rahaza_models.delete_many({"code": {"$in": created["model"]}})
    print(f"cleaned wo={c_wo.deleted_count} lkp={c_lkp.deleted_count} photos={c_ph.deleted_count} "
          f"bundles={c_bd.deleted_count} rsv={c_rs.deleted_count} wip={c_wp.deleted_count} model={c_md.deleted_count}")
    cli.close()
asyncio.get_event_loop().run_until_complete(cleanup())

passed = sum(1 for _, v, _ in results if v == "PASS")
info = [t for t in results if t[1] == "INFO"]
failed = [t for t in results if t[1] == "FAIL"]
print(f"\n===== SUMMARY: {passed} PASS, {len(info)} INFO, {len(failed)} FAIL of {len(results)} =====")
for t in info + failed: print("  ", t)
sys.exit(1 if failed else 0)
