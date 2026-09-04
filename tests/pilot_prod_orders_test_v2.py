"""
PILOT v2 backend deep-contract test — prod-orders (Order Produksi)
Covers ALL 14 endpoints touched by the screen (module + child components):
  Module: /orders (GET,POST), /orders/{id} (GET,PUT,DELETE), /orders/{id}/status,
          /orders/{id}/generate-work-orders, /customers, /models, /sizes, /orders-statuses
  Children: /audit-logs (AuditHistoryDrawer), /production-pos/{id}/stage-summary & /stage-qty (POStageTrackingPanel)
Includes BUG-003 fix verification (stage endpoints must work for Rahaza orders).
Login ONCE, reuse token. Creates own test data + CLEANS UP.
"""
import requests, os, sys
from datetime import date

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
results = []
created = {"orders": []}

def rec(tcid, verdict, detail=""):
    results.append((tcid, verdict, detail)); print(f"[{tcid}] {verdict} | {detail}")
def login(c):
    r = requests.post(f"{BASE}/api/auth/login", json=c, timeout=15); r.raise_for_status(); return r.json()["token"]
def H(t): return {"Authorization": f"Bearer {t}", "Content-Type": "application/json"}

admin = login(ADMIN); print("admin login OK")

# setup
def post(path, tok, body): return requests.post(f"{BASE}{path}", headers=H(tok), json=body)
mid = post("/api/rahaza/models", admin, {"code":"V2MDL","name":"V2 Model"})
model_id = mid.json()["id"] if mid.status_code==200 else next(m["id"] for m in requests.get(f"{BASE}/api/rahaza/models",headers=H(admin)).json() if m["code"]=="V2MDL")
size_id = next(s["id"] for s in requests.get(f"{BASE}/api/rahaza/sizes",headers=H(admin)).json() if s["code"]=="M")
cid = post("/api/rahaza/customers", admin, {"code":"V2CUST","name":"V2 Customer"})
customer_id = cid.json()["id"] if cid.status_code==200 else next(c["id"] for c in requests.get(f"{BASE}/api/rahaza/customers",headers=H(admin)).json() if c["code"]=="V2CUST")
lu = post("/api/users", admin, {"email":"v2staff@test.com","password":"Staff@123","name":"V2 Staff","role":"staff"})
staff = login({"email":"v2staff@test.com","password":"Staff@123"})
def item(q, m=None, s=None): return {"model_id": m or model_id, "size_id": s or size_id, "qty": q}

# ---- support-data endpoints ----
for tc, path in [("TC-S1","/api/rahaza/customers"),("TC-S2","/api/rahaza/models"),("TC-S3","/api/rahaza/sizes"),("TC-S4","/api/rahaza/orders-statuses")]:
    r = requests.get(f"{BASE}{path}", headers=H(admin)); rec(tc, "PASS" if r.status_code==200 else "FAIL", f"{path} HTTP {r.status_code} count={len(r.json()) if r.status_code==200 else '-'}")

# ---- CRUD + validation ----
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item(10)],"notes":"v2 internal"})
o1 = r.json() if r.status_code==200 else {}
if o1: created["orders"].append(o1["id"])
rec("TC-01","PASS" if r.status_code==200 and o1.get("status")=="draft" and o1.get("total_qty")==10 else "FAIL", f"internal draft total_qty={o1.get('total_qty')} no={o1.get('order_number')}")

r = post("/api/rahaza/orders", admin, {"is_internal":False,"customer_id":customer_id,"due_date":"2026-12-31","items":[item(5),item(3)]})
o2 = r.json() if r.status_code==200 else {}
if o2: created["orders"].append(o2["id"])
rec("TC-02","PASS" if r.status_code==200 and o2.get("total_qty")==8 and o2.get("item_count")==2 else "FAIL", f"customer order total_qty={o2.get('total_qty')} items={o2.get('item_count')}")

r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[]})
if r.status_code==200: created["orders"].append(r.json()["id"])
rec("TC-03","BUG" if r.status_code==200 else ("PASS" if r.status_code==400 else "FAIL"), f"empty items -> HTTP {r.status_code} (400=fixed, 200=BUG-001)")

r = post("/api/rahaza/orders", admin, {"is_internal":False,"items":[item(1)]})
rec("TC-04","PASS" if r.status_code==400 else "FAIL", f"no customer -> HTTP {r.status_code} (exp 400)")

r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item(0),item(-5),item(7)]})
o5 = r.json() if r.status_code==200 else {}
if o5: created["orders"].append(o5["id"])
rec("TC-05","PASS" if o5.get("item_count")==1 and o5.get("total_qty")==7 else "FAIL", f"qty<=0 filtered item_count={o5.get('item_count')}")

r = requests.get(f"{BASE}/api/rahaza/orders/{o2.get('id')}", headers=H(admin)) if o2 else None
it = (r.json().get("items") or [{}])[0] if r and r.status_code==200 else {}
rec("TC-06","PASS" if it.get("model_code")=="V2MDL" and it.get("size_code")=="M" else "FAIL", f"detail enrich model_code={it.get('model_code')} size_code={it.get('size_code')}")

r = requests.put(f"{BASE}/api/rahaza/orders/{o1['id']}", headers=H(admin), json={"notes":"edited","items":[item(20)]}) if o1 else None
oe = r.json() if r and r.status_code==200 else {}
rec("TC-07","PASS" if oe.get("total_qty")==20 and oe.get("notes")=="edited" else "FAIL", f"edit draft total_qty={oe.get('total_qty')}")

# ---- state machine ----
r = post(f"/api/rahaza/orders/{o1['id']}/status", admin, {"status":"completed"})
rec("TC-08","PASS" if r.status_code==400 else "FAIL", f"draft->completed HTTP {r.status_code} (exp 400)")
r = post(f"/api/rahaza/orders/{o1['id']}/status", admin, {"status":"banana"})
rec("TC-09","PASS" if r.status_code==400 else "FAIL", f"invalid status HTTP {r.status_code} (exp 400)")
trace=[]; okall=True
for ns in ["confirmed","in_production","completed","closed"]:
    rr = post(f"/api/rahaza/orders/{o1['id']}/status", admin, {"status":ns}); trace.append(f"{ns}:{rr.status_code}")
    if rr.status_code!=200: okall=False; break
rec("TC-10","PASS" if okall else "FAIL"," -> ".join(trace))
r = post(f"/api/rahaza/orders/{o1['id']}/status", admin, {"status":"confirmed"})
rec("TC-11","PASS" if r.status_code==400 else "FAIL", f"closed terminal HTTP {r.status_code}")
r = requests.put(f"{BASE}/api/rahaza/orders/{o1['id']}", headers=H(admin), json={"notes":"x"})
rec("TC-12","PASS" if r.status_code==400 else "FAIL", f"edit non-draft HTTP {r.status_code}")
r = requests.delete(f"{BASE}/api/rahaza/orders/{o1['id']}", headers=H(admin))
rec("TC-13","PASS" if r.status_code==400 else "FAIL", f"delete closed HTTP {r.status_code}")

# ---- generate WO ----
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item(12)]}); wo_o = r.json()["id"]; created["orders"].append(wo_o)
g = post(f"/api/rahaza/orders/{wo_o}/generate-work-orders", admin, {})
od = requests.get(f"{BASE}/api/rahaza/orders/{wo_o}", headers=H(admin)).json()
rec("TC-14","PASS" if g.json().get("total_created")==1 and od["status"]=="confirmed" else "FAIL", f"gen WO total_created={g.json().get('total_created')} auto_status={od['status']}")
g = post(f"/api/rahaza/orders/{wo_o}/generate-work-orders", admin, {})
rec("TC-15","PASS" if g.json().get("total_created")==0 and len(g.json().get("skipped",[]))==1 else "FAIL", f"gen again skipped={len(g.json().get('skipped',[]))}")
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item(1)]}); cxo=r.json()["id"]; created["orders"].append(cxo)
post(f"/api/rahaza/orders/{cxo}/status", admin, {"status":"cancelled"})
g = post(f"/api/rahaza/orders/{cxo}/generate-work-orders", admin, {})
rec("TC-16","PASS" if g.status_code==400 else "FAIL", f"gen WO cancelled HTTP {g.status_code}")
r = requests.delete(f"{BASE}/api/rahaza/orders/{cxo}", headers=H(admin))
if r.status_code==200: created["orders"].remove(cxo)
rec("TC-17","PASS" if r.status_code==200 else "FAIL", f"delete cancelled HTTP {r.status_code}")

# ---- permission ----
r = post("/api/rahaza/orders", staff, {"is_internal":True,"items":[item(1)]})
rec("TC-18","PASS" if r.status_code==403 else "FAIL", f"staff create HTTP {r.status_code} (exp 403)")
r = requests.get(f"{BASE}/api/rahaza/orders", headers=H(staff))
rec("TC-19","PASS" if r.status_code==200 else "FAIL", f"staff list HTTP {r.status_code} (exp 200)")
r = requests.get(f"{BASE}/api/rahaza/orders")
rec("TC-20","PASS" if r.status_code in (401,403) else "FAIL", f"no token HTTP {r.status_code}")
r = requests.get(f"{BASE}/api/rahaza/orders/does-not-exist", headers=H(admin))
rec("TC-21","PASS" if r.status_code==404 else "FAIL", f"missing order HTTP {r.status_code}")

# ---- AUDIT LOGS (child: AuditHistoryDrawer) ----
# NOTE: query o1 (di-transisi MANUAL via /status) -> punya audit create + status_change.
# (Order yang di-auto-confirm via generate-WO TIDAK menulis audit — lihat OBS-004 di dokumen.)
r = requests.get(f"{BASE}/api/audit-logs?entity_type=rahaza_order&entity_id={o1['id']}&limit=100", headers=H(admin))
logs = r.json().get("items", []) if r.status_code==200 else []
actions = {l.get("action") for l in logs}
rec("TC-23","PASS" if r.status_code==200 and "create" in actions and "status_change" in actions else "FAIL",
    f"audit-logs HTTP {r.status_code} actions={sorted(actions)}")
r = requests.get(f"{BASE}/api/audit-logs?entity_type=rahaza_order&entity_id={wo_o}")
rec("TC-24","PASS" if r.status_code in (401,403) else "FAIL", f"audit-logs no token HTTP {r.status_code}")

# ---- STAGE TRACKING (child: POStageTrackingPanel) — BUG-003 fix ----
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item(30)]}); st_o=r.json()["id"]; created["orders"].append(st_o)
post(f"/api/rahaza/orders/{st_o}/status", admin, {"status":"confirmed"})
post(f"/api/rahaza/orders/{st_o}/status", admin, {"status":"in_production"})
r = requests.get(f"{BASE}/api/production-pos/{st_o}/stage-summary", headers=H(admin))
s = r.json() if r.status_code==200 else {}
rec("TC-25","PASS" if r.status_code==200 and s.get("qty_ordered")==30 else "FAIL",
    f"[BUG-003] stage-summary rahaza HTTP {r.status_code} qty_ordered={s.get('qty_ordered')}")
r = requests.put(f"{BASE}/api/production-pos/{st_o}/stage-qty", headers=H(admin), json={"stage":"cutting","qty_in":30,"qty_out":28})
rec("TC-26","PASS" if r.status_code==200 else "FAIL", f"[BUG-003] stage-qty rahaza HTTP {r.status_code}")
r = requests.get(f"{BASE}/api/production-pos/{st_o}/stage-summary", headers=H(admin))
s = r.json() if r.status_code==200 else {}
rec("TC-27","PASS" if s.get("stage_qty",{}).get("cutting_output")==28 and s.get("progress_pct",0)>0 else "FAIL",
    f"stage-qty reflected cutting_output={s.get('stage_qty',{}).get('cutting_output')} progress={s.get('progress_pct')}")
r = requests.put(f"{BASE}/api/production-pos/{st_o}/stage-qty", headers=H(admin), json={"stage":"banana"})
rec("TC-28","PASS" if r.status_code==400 else "FAIL", f"invalid stage HTTP {r.status_code} (exp 400)")
r = requests.get(f"{BASE}/api/production-pos/nonexistent/stage-summary", headers=H(admin))
rec("TC-29","PASS" if r.status_code==404 else "FAIL", f"stage-summary missing id HTTP {r.status_code} (exp 404)")

# ---- edge: tipe data & role produksi nyata ----
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item("abc")]})
rec("TC-30","PASS" if r.status_code==400 else "FAIL", f"[BUG-002] qty non-numerik HTTP {r.status_code} (exp 400, dulu 500)")
# 2026-08-07 — EKSPEKTASI TC-30b DIKOREKSI (dulu: `item_count==1 and total_qty==9`).
# Uji lama mengabadikan perilaku SALAH: baris qty "abc" dibuang DIAM-DIAM dan order
# tetap tersimpan 200. Artinya permintaan pelanggan hilang tanpa pesan apa pun —
# order tercatat kurang, produksi kurang, tagihan kurang. Sekarang baris yang sudah
# DIISI tetapi qty-nya bukan angka HARUS ditolak 400 dengan menyebut nomor barisnya
# (baris template yang benar-benar kosong tetap dilewati). Lihat `_clean_items()`
# di `backend/routes/rahaza_orders.py`.
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item("abc"),item(9)]})
o30 = r.json() if r.status_code==200 else {}
if o30: created["orders"].append(o30["id"])
rec("TC-30b","PASS" if r.status_code==400 else "FAIL", f"[BUG-002] mixed qty -> DITOLAK 400 (bukan dibuang diam-diam): HTTP {r.status_code}")
r = post("/api/rahaza/orders", admin, {"is_internal":True,"due_date":"BUKAN-TANGGAL","items":[item(2)]})
if r.status_code==200: created["orders"].append(r.json()["id"])
rec("TC-31","PASS" if r.status_code==400 else "FAIL", f"[OBS-007 fixed] due_date invalid HTTP {r.status_code} (exp 400)")
post("/api/users", admin, {"email":"v2spv@test.com","password":"Spv@123","name":"V2 Spv","role":"supervisor_produksi"})
spv = login({"email":"v2spv@test.com","password":"Spv@123"})
r = post("/api/rahaza/orders", spv, {"is_internal":True,"items":[item(1)]})
rec("TC-32","PASS" if r.status_code==403 else "FAIL", f"[OBS-006] supervisor_produksi create HTTP {r.status_code} (exp 403)")
r = requests.get(f"{BASE}/api/rahaza/orders", headers=H(spv))
rec("TC-33","PASS" if r.status_code==200 else "FAIL", f"[OBS-006] supervisor_produksi list HTTP {r.status_code} (exp 200)")

# OBS-004: auto-confirm via generate WO tercatat di audit
r = post("/api/rahaza/orders", admin, {"is_internal":True,"items":[item(4)]}); a4=r.json()["id"]; created["orders"].append(a4)
post(f"/api/rahaza/orders/{a4}/generate-work-orders", admin, {})
r = requests.get(f"{BASE}/api/audit-logs?entity_type=rahaza_order&entity_id={a4}&limit=50", headers=H(admin))
acts=[i["action"] for i in r.json().get("items",[])]
rec("TC-34","PASS" if "status_change" in acts else "FAIL", f"[OBS-004 fixed] audit after generate WO actions={acts}")

# ---- helper statuses ----
r = requests.get(f"{BASE}/api/rahaza/orders-statuses", headers=H(admin))
draft = next((x for x in r.json() if x["value"]=="draft"), {})
rec("TC-22","PASS" if draft.get("allowed_next")==["confirmed","cancelled"] else "FAIL", f"draft.allowed_next={draft.get('allowed_next')}")

# ---- CLEANUP ----
print("\n--- CLEANUP ---")
import asyncio
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from motor.motor_asyncio import AsyncIOMotorClient
async def cleanup():
    cli = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = cli[os.environ.get("DB_NAME","test_database")]
    allo = await db.rahaza_orders.find({}, {"id":1,"_id":0}).to_list(1000); ids=[x["id"] for x in allo]
    wo = await db.rahaza_work_orders.delete_many({"order_id":{"$in":ids}})
    od = await db.rahaza_orders.delete_many({})
    md = await db.rahaza_models.delete_many({"code":"V2MDL"})
    cu = await db.rahaza_customers.delete_many({"code":"V2CUST"})
    us = await db.users.delete_many({"email": {"$in": ["v2staff@test.com", "v2spv@test.com"]}})
    al = await db.rahaza_audit_logs.delete_many({"entity_id":{"$in":ids}})
    print(f"cleaned orders={od.deleted_count} wos={wo.deleted_count} models={md.deleted_count} customers={cu.deleted_count} users={us.deleted_count} audit={al.deleted_count}")
    cli.close()
asyncio.get_event_loop().run_until_complete(cleanup())

passed = sum(1 for _,v,_ in results if v=="PASS")
bugs = [t for t in results if t[1]=="BUG"]
failed = [t for t in results if t[1]=="FAIL"]
print(f"\n===== SUMMARY: {passed} PASS, {len(bugs)} BUG, {len(failed)} FAIL of {len(results)} =====")
for t in bugs+failed: print("  ", t)
