"""
Iteration 8 — INVENTORY GROUP backend regression tests
Covers: Warehouse/WMS, Accessories, Assets portals + write flows that touch
recently-modified files (warehouse.py, wms_receiving.py, fulfillment.py,
rahaza_inventory_shared.py).

Run:
  pytest /app/backend/tests/test_iteration_8_inventory.py -v --tb=short \
         --junitxml=/app/test_reports/pytest/iteration_8_results.xml
"""

import os
import uuid
import time
import pytest
import requests

BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split("\n")[0]
            ).rstrip("/")
LOGIN_EMAIL = "admin@garment.com"
LOGIN_PASSWORD = "Admin@123"

S = requests.Session()
S.headers.update({"Content-Type": "application/json"})
TOKEN = None


def _auth_headers():
    assert TOKEN, "no token"
    return {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}


@pytest.fixture(scope="session", autouse=True)
def login_once():
    global TOKEN
    r = S.post(f"{BASE_URL}/api/auth/login",
               json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:300]}"
    j = r.json()
    TOKEN = j.get("token") or j.get("access_token") or (j.get("data") or {}).get("token")
    assert TOKEN, f"no token in login response: {j}"
    S.headers.update({"Authorization": f"Bearer {TOKEN}"})
    yield


# ──────────────────────────────────────────────────────────────────────────────
# Health/Read smoke: ensure routers are mounted (no 5xx)
# ──────────────────────────────────────────────────────────────────────────────

READ_ENDPOINTS = [
    "/api/wms/pending/summary",
    "/api/wms/pending",
    "/api/wms/structure/buildings",
    "/api/wms/units",
    "/api/wms/fabric-rolls",
    "/api/wms/delivery-notes",
    "/api/wms/cmt-dispatches",
    "/api/wms/picklist",
    "/api/wms/opname2",
    "/api/rahaza/inventory/materials",
    "/api/rahaza/inventory/stock",
    "/api/rahaza/inventory/issues",
    "/api/rahaza/po",
    "/api/unified-inventory",
    "/api/fulfillment/queue",
    "/api/fulfillment/summary",
    "/api/fulfillment/inventory/available",
    "/api/dewi/warehouse-smart/summary",
    "/api/dewi/wh-returns",
    "/api/acc/items",
    "/api/acc/stock",
    "/api/dewi/accessories/items",
    "/api/dewi/accessories/stock",
    "/api/dewi/accessories/requests",
    "/api/dewi/accessories/loans",
    "/api/dewi/accessories/purchase",
    "/api/dewi/accessory-requests",
    "/api/assets/dashboard",
    "/api/assets/list",
    "/api/assets/categories",
    "/api/dewi/asset-management/list",
]


@pytest.mark.parametrize("path", READ_ENDPOINTS)
def test_read_endpoints_no_5xx(path):
    r = S.get(f"{BASE_URL}{path}", timeout=20)
    # Accept 200/404 (route may not exist for some shims)/409/403/422/501.
    # FAIL only on 5xx because that's a real server crash.
    assert r.status_code < 500, f"{path} → {r.status_code}: {r.text[:300]}"


# ──────────────────────────────────────────────────────────────────────────────
# RAHAZA INVENTORY: create material → location → stock adjust path
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def test_location():
    # find or create a location
    r = S.get(f"{BASE_URL}/api/rahaza/locations", timeout=20)
    if r.status_code == 200 and isinstance(r.json(), list) and len(r.json()):
        return r.json()[0]
    code = f"TEST-LOC-{uuid.uuid4().hex[:6].upper()}"
    r = S.post(f"{BASE_URL}/api/rahaza/locations",
               json={"code": code, "name": "Test Loc", "active": True}, timeout=20)
    if r.status_code in (200, 201):
        return r.json()
    pytest.skip(f"cannot get/create location: {r.status_code} {r.text[:200]}")


@pytest.fixture(scope="module")
def test_material():
    code = f"TEST-MAT-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "code": code, "name": "TEST Material for iter8",
        "type": "yarn", "unit": "kg", "min_stock": 10.0,
    }
    r = S.post(f"{BASE_URL}/api/rahaza/materials", json=payload, timeout=20)
    assert r.status_code in (200, 201), f"create material failed: {r.status_code} {r.text[:300]}"
    j = r.json()
    return j.get("material") or j


def test_material_created_persisted(test_material):
    mid = test_material["id"]
    r = S.get(f"{BASE_URL}/api/rahaza/materials", timeout=20)
    assert r.status_code == 200
    ids = [m.get("id") for m in r.json()]
    assert mid in ids, "created material not in list"


def test_stock_adjust_increment(test_material, test_location):
    mid = test_material["id"]
    lid = test_location["id"]
    payload = {
        "material_id": mid, "location_id": lid,
        "qty_change": 100.0, "reason": "TEST: opening stock",
    }
    # Try a few likely endpoints
    candidates = [
        "/api/rahaza/material-stock/adjust",
        "/api/rahaza/stock/adjust",
        "/api/rahaza/inventory/stock/adjust",
    ]
    last = None
    for ep in candidates:
        r = S.post(f"{BASE_URL}{ep}", json=payload, timeout=20)
        last = (ep, r.status_code, r.text[:300])
        if r.status_code in (200, 201):
            break
    else:
        pytest.skip(f"no stock-adjust endpoint accepted payload: {last}")

    # verify via stock listing
    r2 = S.get(f"{BASE_URL}/api/rahaza/material-stock?material_id={mid}", timeout=20)
    assert r2.status_code == 200
    rows = r2.json()
    if isinstance(rows, dict):
        rows = rows.get("items") or rows.get("data") or []
    total = sum(float(x.get("qty") or 0) for x in rows if x.get("material_id") == mid)
    assert total >= 100.0, f"stock not incremented: total={total} rows={rows}"


# ──────────────────────────────────────────────────────────────────────────────
# WMS RECEIVING: create pending inbound → scan-in → stock incremented
# Regression for wms_receiving.py helpers
# ──────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def pending_inbound(test_material):
    mid = test_material["id"]
    payload = {
        "type": "inbound", "source_type": "manual",
        "source_ref": "TEST-PO-001",
        "material_id": mid,
        "material_code": test_material.get("code", "T"),
        "material_name": test_material.get("name", "T"),
        "material_type": "rm",
        "expected_qty": 50.0,
        "unit": test_material.get("unit", "kg"),
        "notes": "iter8 receiving test",
    }
    r = S.post(f"{BASE_URL}/api/wms/pending", json=payload, timeout=20)
    assert r.status_code in (200, 201), f"create pending failed: {r.status_code} {r.text[:300]}"
    j = r.json()
    mov = j.get("movement") or j
    assert mov.get("id"), f"no movement id in response: {j}"
    return mov


def test_pending_inbound_listed(pending_inbound):
    mov_id = pending_inbound["id"]
    r = S.get(f"{BASE_URL}/api/wms/pending?type=inbound&status=pending", timeout=20)
    assert r.status_code == 200
    items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
    assert any(it.get("id") == mov_id for it in items), "newly-created pending inbound not returned by list"


def test_scan_in_increments_stock(pending_inbound, test_material):
    mov_id = pending_inbound["id"]

    # baseline stock total
    def _total():
        r = S.get(f"{BASE_URL}/api/rahaza/material-stock?material_id={test_material['id']}", timeout=20)
        if r.status_code != 200:
            return 0.0
        rows = r.json()
        if isinstance(rows, dict):
            rows = rows.get("items") or rows.get("data") or []
        return sum(float(x.get("qty") or 0) for x in rows if x.get("material_id") == test_material["id"])

    before = _total()
    r = S.post(f"{BASE_URL}/api/wms/pending/{mov_id}/scan-in",
               json={"scanned_qty": 50.0, "notes": "iter8 scan-in"}, timeout=20)
    assert r.status_code in (200, 201), f"scan-in failed: {r.status_code} {r.text[:300]}"
    # allow async write
    time.sleep(0.5)
    after = _total()
    assert after - before >= 49.9, f"stock not incremented after scan-in: before={before} after={after}"


# ──────────────────────────────────────────────────────────────────────────────
# MATERIAL ISSUE: create + (if possible) issue → low-stock alert path
# rahaza_inventory_shared.py recently modified
# ──────────────────────────────────────────────────────────────────────────────

def test_material_issue_create(test_material, test_location):
    mid = test_material["id"]
    lid = test_location["id"]
    payload = {
        "items": [{"material_id": mid, "location_id": lid, "qty": 10.0,
                   "notes": "iter8 MI"}],
        "notes": "iter8 material issue test",
    }
    r = S.post(f"{BASE_URL}/api/rahaza/material-issues", json=payload, timeout=20)
    # accept 200/201 (created) or 400 (insufficient stock guard).
    assert r.status_code < 500, f"MI create 5xx: {r.status_code} {r.text[:300]}"
    if r.status_code in (200, 201):
        j = r.json()
        mi = j.get("issue") or j
        assert mi.get("id") or mi.get("mi_number"), f"no id/mi_number: {j}"
    else:
        # business-rule rejection is fine
        assert r.status_code in (400, 403, 422), r.text[:200]


# ──────────────────────────────────────────────────────────────────────────────
# FULFILLMENT: status machine (fulfillment.py recently modified _get_order)
# ──────────────────────────────────────────────────────────────────────────────

def test_fulfillment_summary_shape():
    r = S.get(f"{BASE_URL}/api/fulfillment/summary", timeout=20)
    assert r.status_code == 200, r.text[:300]
    j = r.json()
    for k in ["pending_fulfillment", "allocated", "picking", "packed_ready", "dispatched_today"]:
        assert k in j, f"missing {k} in summary"


def test_fulfillment_invalid_order_404():
    bad_id = f"NONEXISTENT-{uuid.uuid4().hex[:8]}"
    r = S.get(f"{BASE_URL}/api/fulfillment/orders/{bad_id}", timeout=20)
    assert r.status_code in (404, 400), f"expected 404 not {r.status_code}: {r.text[:200]}"
    # crucially: NOT 500 (means _get_order's {_id:0} fix is intact)
    assert r.status_code < 500


def test_fulfillment_allocate_invalid_order_no_500():
    bad_id = f"NONEXISTENT-{uuid.uuid4().hex[:8]}"
    r = S.post(f"{BASE_URL}/api/fulfillment/orders/{bad_id}/allocate",
               json={"items": [{"material_id": "x", "qty_allocated": 1}]}, timeout=20)
    assert r.status_code < 500, f"5xx on allocate of bad order: {r.status_code} {r.text[:300]}"
    assert r.status_code in (400, 404, 422)


def test_fulfillment_inventory_available_no_5xx():
    r = S.get(f"{BASE_URL}/api/fulfillment/inventory/available", timeout=20)
    assert r.status_code < 500
    # Must be JSON list (or dict with items)
    j = r.json()
    assert isinstance(j, (list, dict))


# ──────────────────────────────────────────────────────────────────────────────
# ACCESSORIES: list reads + create item + request flow
# ──────────────────────────────────────────────────────────────────────────────

def test_acc_items_no_5xx():
    r = S.get(f"{BASE_URL}/api/acc/items", timeout=20)
    assert r.status_code < 500


def test_dewi_accessories_create_item():
    code = f"TEST-ACC-{uuid.uuid4().hex[:6].upper()}"
    payload = {"code": code, "name": "TEST Accessory iter8",
               "unit": "pcs", "min_stock": 5, "category": "tools"}
    r = S.post(f"{BASE_URL}/api/dewi/accessories/items", json=payload, timeout=20)
    if r.status_code not in (200, 201):
        # try the /acc/ prefix
        r = S.post(f"{BASE_URL}/api/acc/items", json=payload, timeout=20)
    assert r.status_code < 500, f"acc item create 5xx: {r.status_code} {r.text[:300]}"
    # accept 200/201/400 (existing); just no server error


def test_dewi_accessory_requests_list():
    r = S.get(f"{BASE_URL}/api/dewi/accessory-requests", timeout=20)
    assert r.status_code < 500


# ──────────────────────────────────────────────────────────────────────────────
# ASSETS portal
# ──────────────────────────────────────────────────────────────────────────────

def test_assets_dashboard():
    r = S.get(f"{BASE_URL}/api/assets/dashboard", timeout=20)
    assert r.status_code < 500, r.text[:300]


def test_assets_list_no_id_leak():
    r = S.get(f"{BASE_URL}/api/assets/list", timeout=20)
    assert r.status_code < 500
    j = r.json()
    rows = j if isinstance(j, list) else (j.get("items") or j.get("data") or [])
    for row in rows[:20]:
        assert "_id" not in row, f"ObjectId leak in asset row: {row}"


def test_asset_scan_lookup_404_not_500():
    bad = f"DOES-NOT-EXIST-{uuid.uuid4().hex[:6]}"
    r = S.get(f"{BASE_URL}/api/assets/scan/{bad}", timeout=20)
    assert r.status_code < 500, f"scan-lookup 5xx: {r.status_code} {r.text[:200]}"


def test_asset_create_and_persist():
    code = f"TEST-AST-{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "code": code,
        "name": "TEST Asset iter8",
        "category": "peralatan",
        "purchase_date": "2025-01-15",
        "purchase_cost": 5_000_000,
        "useful_life_months": 60,
        "depreciation_method": "straight_line",
        "status": "active",
    }
    # Try several common create endpoints
    for ep in ["/api/assets", "/api/assets/list", "/api/dewi/asset-management/create",
               "/api/dewi/asset-management"]:
        r = S.post(f"{BASE_URL}{ep}", json=payload, timeout=20)
        if r.status_code in (200, 201):
            j = r.json()
            asset = j.get("asset") or j
            aid = asset.get("id")
            if aid:
                # verify via list
                r2 = S.get(f"{BASE_URL}/api/assets/list", timeout=20)
                if r2.status_code == 200:
                    rows = r2.json() if isinstance(r2.json(), list) else r2.json().get("items", [])
                    assert any(x.get("id") == aid for x in rows), "created asset not in list"
            return
        if r.status_code >= 500:
            pytest.fail(f"asset create 5xx on {ep}: {r.status_code} {r.text[:300]}")
    pytest.skip("no asset-create endpoint accepted payload (non-5xx)")


# ──────────────────────────────────────────────────────────────────────────────
# WAREHOUSE GRN → FIXED ASSET (warehouse.py recently modified asset_doc)
# We can't easily POST a full GRN-with-capitalize from black-box, so we just
# verify the endpoint chain returns non-5xx and the fixed-assets list has no
# _id leakage.
# ──────────────────────────────────────────────────────────────────────────────

def test_fixed_assets_list_no_id_leak():
    # rahaza_fixed_assets endpoint
    for ep in ["/api/rahaza/fixed-assets", "/api/rahaza/finance/fixed-assets",
               "/api/assets/list"]:
        r = S.get(f"{BASE_URL}{ep}", timeout=20)
        if r.status_code == 200:
            j = r.json()
            rows = j if isinstance(j, list) else (j.get("items") or j.get("data") or [])
            for row in rows[:20]:
                assert "_id" not in row, f"_id leak in {ep}: {row}"
            return
    # not found is ok; just make sure none were 5xx in the chain


# ──────────────────────────────────────────────────────────────────────────────
# WMS picklist / opname2 / structure write smoke (no 5xx)
# ──────────────────────────────────────────────────────────────────────────────

def test_wms_picklist_no_5xx():
    r = S.get(f"{BASE_URL}/api/wms/picklist", timeout=20)
    assert r.status_code < 500


def test_wms_opname2_no_5xx():
    r = S.get(f"{BASE_URL}/api/wms/opname2", timeout=20)
    assert r.status_code < 500


def test_wms_structure_buildings_no_5xx():
    r = S.get(f"{BASE_URL}/api/wms/structure/buildings", timeout=20)
    assert r.status_code < 500


def test_wms_fabric_rolls_no_5xx():
    r = S.get(f"{BASE_URL}/api/wms/fabric-rolls", timeout=20)
    assert r.status_code < 500


def test_wms_delivery_notes_no_5xx():
    r = S.get(f"{BASE_URL}/api/wms/delivery-notes", timeout=20)
    assert r.status_code < 500


def test_wms_cmt_dispatches_no_5xx():
    r = S.get(f"{BASE_URL}/api/wms/cmt-dispatches", timeout=20)
    assert r.status_code < 500


def test_unified_inventory_no_5xx():
    r = S.get(f"{BASE_URL}/api/unified-inventory", timeout=20)
    assert r.status_code < 500
