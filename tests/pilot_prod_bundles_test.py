"""
PILOT backend deep-contract test — prod-bundles (Bundle Produksi / Penelusuran Bundle)
Covers: list/filter/search/pagination, statuses metadata, generate (idempotent 409 + force),
detail by-id + by-number (normalization), WO bundles-summary, ticket.pdf, qr.png,
bulk bundle-tickets.pdf (+status filter), delete guard, RBAC (no-token).

Login ONCE, reuse token. Creates own test data + CLEANS UP by tracked ids (DB pristine).
5 test types tagged: [H]appy, [E]dge, [N]egative, [P]ermission, [S]tate.
"""
import requests, os, sys

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
results = []
created = {"wo": [], "model": []}

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
mid = POST("/api/rahaza/models", admin, {"code": "BDLTESTMDL", "name": "Bundle Test Model"})
if mid.status_code == 200:
    model_id = mid.json()["id"]; created["model"].append("BDLTESTMDL")
else:
    model_id = next(m["id"] for m in GET("/api/rahaza/models", admin).json() if m["code"] == "BDLTESTMDL")
size_id = next(s["id"] for s in GET("/api/rahaza/sizes", admin).json() if s["code"] == "M")

# ---- reads / statuses ----
r = GET("/api/rahaza/bundles", admin)
rec("TC-01", "PASS" if r.status_code == 200 and "items" in r.json() else "FAIL",
    f"[H] list bundles HTTP {r.status_code}")

r = GET("/api/rahaza/bundles-statuses", admin)
sts = r.json().get("statuses", []) if r.status_code == 200 else []
vals = [s.get("value") for s in sts]
rec("TC-02", "PASS" if r.status_code == 200 and "created" in vals and "packed" in vals and len(sts) == 7 else "FAIL",
    f"[H] statuses HTTP {r.status_code} n={len(sts)} values={vals}")

# ---- create WO (draft) qty 65 => ceil(65/30)=3 bundles ----
r = POST("/api/rahaza/work-orders", admin, {"model_id": model_id, "size_id": size_id, "qty": 65, "priority": "normal"})
wo = r.json() if r.status_code == 200 else {}
if wo.get("id"): created["wo"].append(wo["id"])
wid = wo.get("id")
rec("TC-03", "PASS" if r.status_code == 200 and wid else "FAIL",
    f"[H] setup WO qty=65 HTTP {r.status_code} no={wo.get('wo_number')}")

# ---- generate bundles (default size 30 => 3 bundles: 30,30,5) ----
r = POST(f"/api/rahaza/work-orders/{wid}/generate-bundles", admin, {}) if wid else None
g1 = r.json() if r and r.status_code == 200 else {}
rec("TC-04", "PASS" if r and r.status_code == 200 and g1.get("generated") == 3 and g1.get("bundle_size") == 30 else "FAIL",
    f"[H] generate-bundles HTTP {getattr(r,'status_code',None)} generated={g1.get('generated')} size={g1.get('bundle_size')}")

# last bundle qty should be remainder (5)
qtys = sorted([b.get("qty") for b in g1.get("bundles", [])])
rec("TC-05", "PASS" if qtys == [5, 30, 30] else "FAIL",
    f"[S] bundle split qtys={qtys} (exp [5,30,30])")

# ---- idempotent guard: generate again no force -> 409 ----
r = POST(f"/api/rahaza/work-orders/{wid}/generate-bundles", admin, {}) if wid else None
rec("TC-06", "PASS" if r is not None and r.status_code == 409 else "FAIL",
    f"[S] regenerate no force -> HTTP {getattr(r,'status_code',None)} (exp 409)")

# ---- list filtered by work_order_id ----
r = GET(f"/api/rahaza/bundles?work_order_id={wid}", admin) if wid else None
items = r.json().get("items", []) if r and r.status_code == 200 else []
rec("TC-07", "PASS" if r and r.status_code == 200 and len(items) == 3 else "FAIL",
    f"[E] list filter work_order_id -> {len(items)} items (exp 3)")

b0 = items[0] if items else {}
bid = b0.get("id"); bnum = b0.get("bundle_number")

# ---- detail by id ----
r = GET(f"/api/rahaza/bundles/{bid}", admin) if bid else None
det = r.json() if r and r.status_code == 200 else {}
rec("TC-08", "PASS" if det.get("bundle_number") == bnum and isinstance(det.get("process_sequence"), list) and det.get("status") == "created" else "FAIL",
    f"[H] detail by id status={det.get('status')} seq_len={len(det.get('process_sequence') or [])}")

# ---- detail by number (exact) ----
r = GET(f"/api/rahaza/bundles/by-number/{bnum}", admin) if bnum else None
rec("TC-09", "PASS" if r and r.status_code == 200 and r.json().get("id") == bid else "FAIL",
    f"[H] by-number exact HTTP {getattr(r,'status_code',None)}")

# ---- by-number lowercase normalization (server uppercases) ----
r = GET(f"/api/rahaza/bundles/by-number/{bnum.lower()}", admin) if bnum else None
rec("TC-10", "PASS" if r and r.status_code == 200 and r.json().get("id") == bid else "FAIL",
    f"[E] by-number lowercase normalization HTTP {getattr(r,'status_code',None)}")

# ---- by-number nonexistent -> 404 ----
r = GET("/api/rahaza/bundles/by-number/BDL-19700101-9999", admin)
rec("TC-11", "PASS" if r.status_code == 404 else "FAIL", f"[N] by-number nonexistent -> HTTP {r.status_code} (exp 404)")

# ---- detail nonexistent id -> 404 ----
r = GET("/api/rahaza/bundles/does-not-exist-uuid", admin)
rec("TC-12", "PASS" if r.status_code == 404 else "FAIL", f"[N] detail nonexistent -> HTTP {r.status_code} (exp 404)")

# ---- WO bundles-summary ----
r = GET(f"/api/rahaza/work-orders/{wid}/bundles-summary", admin) if wid else None
summ = r.json() if r and r.status_code == 200 else {}
rec("TC-13", "PASS" if r and r.status_code == 200 and summ.get("total") == 3 and summ.get("total_qty") == 65 and summ.get("wo_qty") == 65 else "FAIL",
    f"[H] bundles-summary total={summ.get('total')} total_qty={summ.get('total_qty')} wo_qty={summ.get('wo_qty')}")

# ---- ticket.pdf ----
r = GET(f"/api/rahaza/bundles/{bid}/ticket.pdf", admin) if bid else None
ct = r.headers.get("content-type", "") if r else ""
rec("TC-14", "PASS" if r and r.status_code == 200 and "application/pdf" in ct else "FAIL",
    f"[H] ticket.pdf HTTP {getattr(r,'status_code',None)} ct={ct}")

# ---- qr.png ----
r = GET(f"/api/rahaza/bundles/{bid}/qr.png", admin) if bid else None
ct = r.headers.get("content-type", "") if r else ""
rec("TC-15", "PASS" if r and r.status_code == 200 and "image/png" in ct else "FAIL",
    f"[H] qr.png HTTP {getattr(r,'status_code',None)} ct={ct}")

# ---- bulk bundle-tickets.pdf ----
r = GET(f"/api/rahaza/work-orders/{wid}/bundle-tickets.pdf", admin) if wid else None
ct = r.headers.get("content-type", "") if r else ""
xtot = r.headers.get("X-Total-Bundles") if r else None
rec("TC-16", "PASS" if r and r.status_code == 200 and "application/pdf" in ct and xtot == "3" else "FAIL",
    f"[H] bulk tickets HTTP {getattr(r,'status_code',None)} ct={ct} X-Total-Bundles={xtot}")

# ---- bulk tickets with status filter that yields none -> 404 ----
r = GET(f"/api/rahaza/work-orders/{wid}/bundle-tickets.pdf?status=shipped", admin) if wid else None
rec("TC-17", "PASS" if r is not None and r.status_code == 404 else "FAIL",
    f"[E] bulk tickets status=shipped (none) -> HTTP {getattr(r,'status_code',None)} (exp 404)")

# ---- list q search by bundle_number prefix ----
prefix = (bnum or "")[:12]
r = GET(f"/api/rahaza/bundles?q={prefix}", admin) if prefix else None
its = r.json().get("items", []) if r and r.status_code == 200 else []
rec("TC-18", "PASS" if r and r.status_code == 200 and len(its) >= 1 else "FAIL",
    f"[E] q search '{prefix}' -> {len(its)} items")

# ---- pagination shape ----
r = GET(f"/api/rahaza/bundles?work_order_id={wid}&page=1&limit=2", admin) if wid else None
pj = r.json() if r and r.status_code == 200 else {}
rec("TC-19", "PASS" if r and r.status_code == 200 and "pagination" in pj and len(pj.get("items", [])) == 2 else "FAIL",
    f"[E] pagination page=1 limit=2 -> items={len(pj.get('items', []))} has_pagination={'pagination' in pj}")

# ---- delete created bundle -> 200 ----
r = DELETE(f"/api/rahaza/bundles/{bid}", admin) if bid else None
rec("TC-20", "PASS" if r and r.status_code == 200 else "FAIL", f"[S] delete created bundle -> HTTP {getattr(r,'status_code',None)}")

# ---- delete same again -> 404 ----
r = DELETE(f"/api/rahaza/bundles/{bid}", admin) if bid else None
rec("TC-21", "PASS" if r is not None and r.status_code == 404 else "FAIL", f"[N] delete already-deleted -> HTTP {getattr(r,'status_code',None)} (exp 404)")

# ---- generate on cancelled WO -> 400 ----
r = POST("/api/rahaza/work-orders", admin, {"model_id": model_id, "size_id": size_id, "qty": 10})
w2 = r.json() if r.status_code == 200 else {}
if w2.get("id"): created["wo"].append(w2["id"])
POST(f"/api/rahaza/work-orders/{w2.get('id')}/status", admin, {"status": "cancelled"}) if w2.get("id") else None
r = POST(f"/api/rahaza/work-orders/{w2.get('id')}/generate-bundles", admin, {}) if w2.get("id") else None
rec("TC-22", "PASS" if r is not None and r.status_code == 400 else "FAIL",
    f"[N] generate on cancelled WO -> HTTP {getattr(r,'status_code',None)} (exp 400)")

# ---- force regenerate as admin (deletes remaining created, regenerates) -> 200 ----
r = POST(f"/api/rahaza/work-orders/{wid}/generate-bundles?force=true", admin, {}) if wid else None
gf = r.json() if r and r.status_code == 200 else {}
rec("TC-23", "PASS" if r and r.status_code == 200 and gf.get("generated") == 3 else "FAIL",
    f"[S] force regenerate -> HTTP {getattr(r,'status_code',None)} generated={gf.get('generated')}")

# ---- RBAC: read/list without token -> 401/403 ----
r = requests.get(f"{BASE}/api/rahaza/bundles")
rec("TC-24", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] list no token -> HTTP {r.status_code} (exp 401/403)")

# ---- RBAC: generate without token -> 401/403 ----
r = requests.post(f"{BASE}/api/rahaza/work-orders/{wid}/generate-bundles", json={})
rec("TC-25", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] generate no token -> HTTP {r.status_code} (exp 401/403)")

# ---- RBAC: statuses without token -> 401/403 ----
r = requests.get(f"{BASE}/api/rahaza/bundles-statuses")
rec("TC-26", "PASS" if r.status_code in (401, 403) else "FAIL", f"[P] statuses no token -> HTTP {r.status_code} (exp 401/403)")

# ---- CLEANUP (by tracked ids) ----
print("\n--- CLEANUP ---")
import asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
async def cleanup():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ.get("DB_NAME", "test_database")]
    wids = created["wo"]
    c_bd = await db.rahaza_bundles.delete_many({"work_order_id": {"$in": wids}})
    c_wo = await db.rahaza_work_orders.delete_many({"id": {"$in": wids}})
    c_rs = await db.rahaza_material_reservations.delete_many({"work_order_id": {"$in": wids}})
    c_wp = await db.rahaza_wip_events.delete_many({"work_order_id": {"$in": wids}})
    c_md = await db.rahaza_models.delete_many({"code": {"$in": created["model"]}})
    print(f"cleaned bundles={c_bd.deleted_count} wo={c_wo.deleted_count} rsv={c_rs.deleted_count} "
          f"wip={c_wp.deleted_count} model={c_md.deleted_count}")
    cli.close()
asyncio.get_event_loop().run_until_complete(cleanup())

passed = sum(1 for _, v, _ in results if v == "PASS")
info = [t for t in results if t[1] == "INFO"]
failed = [t for t in results if t[1] == "FAIL"]
print(f"\n===== SUMMARY: {passed} PASS, {len(info)} INFO, {len(failed)} FAIL of {len(results)} =====")
for t in info + failed: print("  ", t)
sys.exit(1 if failed else 0)
