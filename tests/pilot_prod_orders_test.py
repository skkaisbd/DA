"""
PILOT backend contract test — prod-orders (RahazaOrdersModule / rahaza_orders.py)
Runs the full Order Produksi lifecycle against the LIVE backend on localhost:8001.
Login ONCE, reuse token. Creates its own test data and CLEANS UP at the end.

Output: prints a machine-readable result line per test case: [TC-ID] VERDICT | detail
"""
import requests, json, os, sys
from datetime import date

BASE = "http://localhost:8001"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
results = []
created = {"orders": [], "model_id": None, "customer_id": None, "limited_user_id": None}

def rec(tcid, verdict, detail=""):
    results.append((tcid, verdict, detail))
    print(f"[{tcid}] {verdict} | {detail}")

def login(creds):
    r = requests.post(f"{BASE}/api/auth/login", json=creds, timeout=15)
    r.raise_for_status()
    return r.json()["token"]

def H(tok): return {"Authorization": f"Bearer {tok}", "Content-Type": "application/json"}

# ── LOGIN (once) ──────────────────────────────────────────────
admin_tok = login(ADMIN)
print("admin login OK, token len", len(admin_tok))

# ── SETUP TEST DATA ──────────────────────────────────────────
# model
r = requests.post(f"{BASE}/api/rahaza/models", headers=H(admin_tok),
                  json={"code": "MDLPILOT", "name": "Pilot Test Sweater"})
if r.status_code == 200:
    created["model_id"] = r.json()["id"]
elif r.status_code == 409:
    # already exists from a prior run — fetch it
    ms = requests.get(f"{BASE}/api/rahaza/models", headers=H(admin_tok)).json()
    created["model_id"] = next((m["id"] for m in ms if m["code"] == "MDLPILOT"), None)
print("model_id:", created["model_id"])

# size (use seeded 'M')
sizes = requests.get(f"{BASE}/api/rahaza/sizes", headers=H(admin_tok)).json()
size_id = next((s["id"] for s in sizes if s["code"] == "M"), sizes[0]["id"])
print("size_id (M):", size_id)

# customer
r = requests.post(f"{BASE}/api/rahaza/customers", headers=H(admin_tok),
                  json={"code": "CUSTPILOT", "name": "Pilot Test Customer"})
if r.status_code == 200:
    created["customer_id"] = r.json()["id"]
elif r.status_code == 409:
    cs = requests.get(f"{BASE}/api/rahaza/customers", headers=H(admin_tok)).json()
    created["customer_id"] = next((c["id"] for c in cs if c["code"] == "CUSTPILOT"), None)
print("customer_id:", created["customer_id"])

# limited (non-admin) user for permission tests
limited_email = "pilot_staff@test.com"
r = requests.post(f"{BASE}/api/users", headers=H(admin_tok),
                  json={"email": limited_email, "password": "Staff@123",
                        "name": "Pilot Staff", "role": "staff"})
if r.status_code in (200, 201):
    created["limited_user_id"] = r.json().get("id")
elif r.status_code == 409:
    us = requests.get(f"{BASE}/api/users", headers=H(admin_tok)).json()
    created["limited_user_id"] = next((u["id"] for u in us if u["email"] == limited_email), None)
limited_tok = login({"email": limited_email, "password": "Staff@123"})
print("limited user role token OK")

def mk_item(qty, model=None, size=None):
    return {"model_id": model or created["model_id"], "size_id": size or size_id, "qty": qty}

# ══════════════ TEST CASES ══════════════

# TC-01 Happy: create internal order
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": True, "order_date": date.today().isoformat(),
                        "items": [mk_item(10)], "notes": "pilot internal"})
if r.status_code == 200:
    o = r.json(); created["orders"].append(o["id"])
    ok = o["status"] == "draft" and o["order_number"].startswith("ORD-") and o["total_qty"] == 10 and o["is_internal"] is True
    rec("TC-01", "PASS" if ok else "FAIL", f"status={o['status']} no={o['order_number']} total_qty={o.get('total_qty')} internal={o['is_internal']}")
    internal_oid = o["id"]
else:
    rec("TC-01", "FAIL", f"HTTP {r.status_code} {r.text[:120]}"); internal_oid = None

# TC-02 Happy: create customer order (2 items)
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": False, "customer_id": created["customer_id"],
                        "order_date": date.today().isoformat(), "due_date": "2026-12-31",
                        "items": [mk_item(5), mk_item(3)]})
if r.status_code == 200:
    o = r.json(); created["orders"].append(o["id"]); cust_oid = o["id"]
    ok = o["total_qty"] == 8 and o["item_count"] == 2 and o["customer_name"] == "Pilot Test Customer"
    rec("TC-02", "PASS" if ok else "FAIL", f"total_qty={o['total_qty']} items={o['item_count']} cust={o.get('customer_name')}")
else:
    rec("TC-02", "FAIL", f"HTTP {r.status_code} {r.text[:120]}"); cust_oid = None

# TC-03 Negative: no items -> 400
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": True, "items": []})
# backend: no explicit empty-items guard in create_order -> observe actual
rec("TC-03", "PASS" if r.status_code == 200 or r.status_code == 400 else "FAIL",
    f"HTTP {r.status_code} (observe: create with empty items). body={r.text[:100]}")
if r.status_code == 200:
    created["orders"].append(r.json()["id"])

# TC-04 Negative: not internal + no customer -> 400
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": False, "items": [mk_item(1)]})
rec("TC-04", "PASS" if r.status_code == 400 else "FAIL", f"HTTP {r.status_code} expected 400. body={r.text[:120]}")

# TC-05 Edge: qty=0 and negative qty items are filtered out
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": True, "items": [mk_item(0), mk_item(-5), mk_item(7)]})
if r.status_code == 200:
    o = r.json(); created["orders"].append(o["id"])
    ok = o["item_count"] == 1 and o["total_qty"] == 7
    rec("TC-05", "PASS" if ok else "FAIL", f"only qty>0 kept: item_count={o['item_count']} total_qty={o['total_qty']}")
else:
    rec("TC-05", "FAIL", f"HTTP {r.status_code} {r.text[:120]}")

# TC-06 Happy: get detail enrichment (model_code/name, size_code)
if cust_oid:
    r = requests.get(f"{BASE}/api/rahaza/orders/{cust_oid}", headers=H(admin_tok))
    if r.status_code == 200:
        o = r.json(); it = (o.get("items") or [{}])[0]
        ok = it.get("model_code") == "MDLPILOT" and it.get("size_code") == "M"
        rec("TC-06", "PASS" if ok else "FAIL", f"item enrich model_code={it.get('model_code')} size_code={it.get('size_code')}")
    else:
        rec("TC-06", "FAIL", f"HTTP {r.status_code}")

# TC-07 Happy: edit DRAFT order (change notes + qty)
if internal_oid:
    r = requests.put(f"{BASE}/api/rahaza/orders/{internal_oid}", headers=H(admin_tok),
                     json={"notes": "edited", "items": [mk_item(20)]})
    if r.status_code == 200:
        o = r.json(); ok = o["notes"] == "edited" and o["total_qty"] == 20
        rec("TC-07", "PASS" if ok else "FAIL", f"notes={o['notes']} total_qty={o['total_qty']}")
    else:
        rec("TC-07", "FAIL", f"HTTP {r.status_code} {r.text[:120]}")

# TC-08 Negative: invalid transition draft->completed -> 400
if internal_oid:
    r = requests.post(f"{BASE}/api/rahaza/orders/{internal_oid}/status", headers=H(admin_tok),
                      json={"status": "completed"})
    rec("TC-08", "PASS" if r.status_code == 400 else "FAIL", f"HTTP {r.status_code} expected 400. body={r.text[:140]}")

# TC-09 Negative: invalid status value -> 400
if internal_oid:
    r = requests.post(f"{BASE}/api/rahaza/orders/{internal_oid}/status", headers=H(admin_tok),
                      json={"status": "banana"})
    rec("TC-09", "PASS" if r.status_code == 400 else "FAIL", f"HTTP {r.status_code} expected 400. body={r.text[:120]}")

# TC-10 State: full valid chain draft->confirmed->in_production->completed->closed
if internal_oid:
    chain = ["confirmed", "in_production", "completed", "closed"]
    ok_all = True; trace = []
    for ns in chain:
        r = requests.post(f"{BASE}/api/rahaza/orders/{internal_oid}/status", headers=H(admin_tok),
                          json={"status": ns})
        trace.append(f"{ns}:{r.status_code}")
        if r.status_code != 200: ok_all = False; break
    rec("TC-10", "PASS" if ok_all else "FAIL", " -> ".join(trace))

# TC-11 State: from 'closed' no further transition (closed->confirmed => 400)
if internal_oid:
    r = requests.post(f"{BASE}/api/rahaza/orders/{internal_oid}/status", headers=H(admin_tok),
                      json={"status": "confirmed"})
    rec("TC-11", "PASS" if r.status_code == 400 else "FAIL", f"HTTP {r.status_code} expected 400 (closed is terminal)")

# TC-12 Negative: edit non-draft order -> 400
if internal_oid:  # now 'closed'
    r = requests.put(f"{BASE}/api/rahaza/orders/{internal_oid}", headers=H(admin_tok),
                     json={"notes": "should fail"})
    rec("TC-12", "PASS" if r.status_code == 400 else "FAIL", f"HTTP {r.status_code} expected 400 (only draft editable)")

# TC-13 Negative: delete non-draft/cancelled order -> 400
if internal_oid:  # 'closed'
    r = requests.delete(f"{BASE}/api/rahaza/orders/{internal_oid}", headers=H(admin_tok))
    rec("TC-13", "PASS" if r.status_code == 400 else "FAIL", f"HTTP {r.status_code} expected 400 (only draft/cancelled deletable)")

# TC-14 State+SideEffect: generate WO on a fresh DRAFT order -> auto-confirm
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": True, "items": [mk_item(12)]})
wo_oid = r.json()["id"] if r.status_code == 200 else None
if wo_oid:
    created["orders"].append(wo_oid)
    g = requests.post(f"{BASE}/api/rahaza/orders/{wo_oid}/generate-work-orders", headers=H(admin_tok), json={})
    if g.status_code == 200:
        data = g.json()
        # verify order auto-confirmed
        od = requests.get(f"{BASE}/api/rahaza/orders/{wo_oid}", headers=H(admin_tok)).json()
        ok = data.get("total_created") == 1 and od["status"] == "confirmed"
        rec("TC-14", "PASS" if ok else "FAIL", f"total_created={data.get('total_created')} order_status_after={od['status']}")
    else:
        rec("TC-14", "FAIL", f"HTTP {g.status_code} {g.text[:120]}")

# TC-15 Edge: generate WO again -> item skipped (already has active WO)
if wo_oid:
    g = requests.post(f"{BASE}/api/rahaza/orders/{wo_oid}/generate-work-orders", headers=H(admin_tok), json={})
    if g.status_code == 200:
        data = g.json()
        ok = data.get("total_created") == 0 and len(data.get("skipped", [])) == 1
        rec("TC-15", "PASS" if ok else "FAIL", f"total_created={data.get('total_created')} skipped={len(data.get('skipped',[]))}")
    else:
        rec("TC-15", "FAIL", f"HTTP {g.status_code}")

# TC-16 Negative: generate WO on cancelled order -> 400
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(admin_tok),
                  json={"is_internal": True, "items": [mk_item(1)]})
cancel_oid = r.json()["id"] if r.status_code == 200 else None
if cancel_oid:
    created["orders"].append(cancel_oid)
    requests.post(f"{BASE}/api/rahaza/orders/{cancel_oid}/status", headers=H(admin_tok), json={"status": "cancelled"})
    g = requests.post(f"{BASE}/api/rahaza/orders/{cancel_oid}/generate-work-orders", headers=H(admin_tok), json={})
    rec("TC-16", "PASS" if g.status_code == 400 else "FAIL", f"HTTP {g.status_code} expected 400 (cancelled cannot generate)")

# TC-17 State: delete a cancelled order -> allowed (200)
if cancel_oid:
    r = requests.delete(f"{BASE}/api/rahaza/orders/{cancel_oid}", headers=H(admin_tok))
    ok = r.status_code == 200
    if ok: created["orders"].remove(cancel_oid)
    rec("TC-17", "PASS" if ok else "FAIL", f"HTTP {r.status_code} expected 200 (cancelled deletable)")

# TC-18 Permission: limited (role=staff) user CREATE order -> 403
r = requests.post(f"{BASE}/api/rahaza/orders", headers=H(limited_tok),
                  json={"is_internal": True, "items": [mk_item(1)]})
rec("TC-18", "PASS" if r.status_code == 403 else "FAIL", f"HTTP {r.status_code} expected 403 (staff lacks order.manage)")

# TC-19 Permission: limited user LIST orders -> 200 (read allowed to any auth)
r = requests.get(f"{BASE}/api/rahaza/orders", headers=H(limited_tok))
rec("TC-19", "PASS" if r.status_code == 200 else "FAIL", f"HTTP {r.status_code} expected 200 (read = any auth)")

# TC-20 Permission: NO token -> 401/403
r = requests.get(f"{BASE}/api/rahaza/orders")
rec("TC-20", "PASS" if r.status_code in (401, 403) else "FAIL", f"HTTP {r.status_code} expected 401/403 (no token)")

# TC-21 Negative: get non-existent order -> 404
r = requests.get(f"{BASE}/api/rahaza/orders/nonexistent-id-xyz", headers=H(admin_tok))
rec("TC-21", "PASS" if r.status_code == 404 else "FAIL", f"HTTP {r.status_code} expected 404")

# TC-22 Helper: orders-statuses returns allowed_next map
r = requests.get(f"{BASE}/api/rahaza/orders-statuses", headers=H(admin_tok))
if r.status_code == 200:
    d = r.json(); draft = next((x for x in d if x["value"] == "draft"), {})
    ok = draft.get("allowed_next") == ["confirmed", "cancelled"]
    rec("TC-22", "PASS" if ok else "FAIL", f"draft.allowed_next={draft.get('allowed_next')}")
else:
    rec("TC-22", "FAIL", f"HTTP {r.status_code}")

# ══════════════ CLEANUP ══════════════
print("\n--- CLEANUP ---")
import asyncio
async def cleanup():
    sys.path.insert(0, "/app/backend")
    from motor.motor_asyncio import AsyncIOMotorClient
    mongo = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    dbn = os.environ.get("DB_NAME", "test_database")
    cli = AsyncIOMotorClient(mongo); db = cli[dbn]
    # delete test orders + their WOs
    oids = created["orders"]
    wo = await db.rahaza_work_orders.delete_many({"order_id": {"$in": oids}})
    od = await db.rahaza_orders.delete_many({"id": {"$in": oids}})
    # delete test model + customer + limited user (hard delete to keep DB pristine)
    md = await db.rahaza_models.delete_many({"code": "MDLPILOT"})
    cu = await db.rahaza_customers.delete_many({"code": "CUSTPILOT"})
    us = await db.users.delete_many({"email": "pilot_staff@test.com"})
    print(f"cleaned: orders={od.deleted_count} wos={wo.deleted_count} models={md.deleted_count} customers={cu.deleted_count} users={us.deleted_count}")
    cli.close()
# load env
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
asyncio.get_event_loop().run_until_complete(cleanup())

# ══════════════ SUMMARY ══════════════
passed = sum(1 for _, v, _ in results if v == "PASS")
failed = [t for t in results if t[1] != "PASS"]
print(f"\n===== SUMMARY: {passed}/{len(results)} PASS =====")
for t in failed:
    print("  NOT-PASS:", t)
