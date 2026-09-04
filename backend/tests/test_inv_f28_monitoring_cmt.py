"""INV-F28 — Monitoring CMT: potongan sesuai order + scope running/all +
buyer outstanding board + material-request replacement tracker.

Runs against the deployed preview URL from REACT_APP_BACKEND_URL.
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"
TARGET_PO = "PO-MKL-202608-9433"


@pytest.fixture(scope="module")
def token():
    time.sleep(1)
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text[:200]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"no token in login response: {r.json()}"
    return tok


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- BUG 1 — potongan hanya NORMAL ----------
def test_cmt_kejar_running_target_po_qty_sent_cmt_only_normal(H):
    r = requests.get(f"{API}/dewi/cmt-kejar", params={"scope": "running"},
                     headers=H, timeout=60)
    assert r.status_code == 200, r.text[:500]
    data = r.json()
    assert data.get("scope") == "running"
    rows = data.get("rows") or []
    target = next((x for x in rows if x.get("po_number") == TARGET_PO), None)
    assert target is not None, f"{TARGET_PO} missing in scope=running rows (count={len(rows)})"

    # required response shape
    for k in ("qty_sent_cmt", "qty_sent_extra", "qty_sent_extra_by_type",
              "qty_not_sent_cmt", "qty_shipped_buyer", "qty_shippable_buyer",
              "qty_outstanding_cmt", "qty_ordered"):
        assert k in target, f"missing field {k} in row"

    # HARD assertion from problem statement: order=100, qty_sent_cmt MUST be 100
    assert target["qty_ordered"] == 100, target
    assert target["qty_sent_cmt"] == 100, (
        f"qty_sent_cmt expected 100 (normal only), got {target['qty_sent_cmt']} — "
        f"row={target}")
    # extras should be reported separately (>=0 is enough; must exist as int)
    assert isinstance(target["qty_sent_extra"], int)
    assert isinstance(target["qty_sent_extra_by_type"], dict)

    # Sisa di CMT never exceeds sent-normal minus returned
    assert target["qty_outstanding_cmt"] == max(
        0, target["qty_sent_cmt"] - target["qty_returned"]
    )


# ---------- FEATURE 3 — scope=all includes Completed ----------
def test_cmt_kejar_scope_all_ge_running(H):
    r_run = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                         params={"scope": "running"}, headers=H, timeout=60).json()
    r_all = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                        params={"scope": "all"}, headers=H, timeout=60).json()
    assert r_run.get("scope") == "running"
    assert r_all.get("scope") == "all"
    assert "total_po" in r_run and "total_po" in r_all
    assert r_all["total_po"] >= r_run["total_po"]
    # required aggregate fields for the two new KPI cards
    for k in ("qty_not_sent_cmt", "qty_not_sent_draft",
              "qty_shipped_buyer", "qty_shippable_buyer",
              "qty_sent_extra", "qty_sent_cmt", "qty_ordered"):
        assert k in r_run, f"dashboard missing {k}"


# ---------- FEATURE 4 — buyer outstanding board endpoint ----------
def test_buyer_dispatch_outstanding_exists(H):
    r = requests.get(f"{API}/buyer-dispatch-outstanding", headers=H, timeout=60)
    # endpoint should exist (returns list or object)
    assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
    body = r.json()
    # accept list or dict with items
    if isinstance(body, dict):
        rows = body.get("rows") or body.get("items") or body.get("data") or []
    else:
        rows = body
    assert isinstance(rows, list)


# ---------- FEATURE 5 — material-requests REPLACEMENT tracker enrichment ----------
def test_material_requests_replacement_tracker_fields(H):
    r = requests.get(f"{API}/material-requests",
                     params={"request_type": "REPLACEMENT"}, headers=H, timeout=60)
    assert r.status_code == 200, r.text[:400]
    body = r.json()
    if isinstance(body, dict):
        rows = body.get("rows") or body.get("items") or body.get("data") or []
    else:
        rows = body
    assert isinstance(rows, list)
    # Zero rows is acceptable but if we have any Approved one, it must expose
    # child_shipment_number + child_shipment_status.
    approved = [x for x in rows if str(x.get("status") or "").lower() in
                ("approved", "disetujui")]
    for a in approved:
        assert "child_shipment_number" in a, f"row missing child_shipment_number: {a}"
        assert "child_shipment_status" in a


# ---------- FEATURE 5 — child shipment shape when one exists ----------
def test_child_shipment_shape_if_present(H):
    r = requests.get(f"{API}/vendor-shipments", headers=H, timeout=60)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    rows = body if isinstance(body, list) else (body.get("rows") or body.get("items") or [])
    parents = [s for s in rows if s.get("child_qty_total") is not None]
    # We don't require a child to exist; only assert shape when present.
    if not parents:
        pytest.skip("No parent shipment with child_qty_total in DB")

    # find any child shipment (has parent_shipment_id or shipment_type != NORMAL)
    children = [s for s in rows if s.get("parent_shipment_id") or
                (s.get("shipment_type") and str(s.get("shipment_type")).upper() != "NORMAL")]
    if not children:
        pytest.skip("No child shipments in DB")
    cid = children[0]["id"]
    rd = requests.get(f"{API}/vendor-shipments/{cid}", headers=H, timeout=60)
    assert rd.status_code == 200, rd.text[:200]
    detail = rd.json()
    assert detail.get("is_child_shipment") is True, f"child flag missing: {detail}"
    assert detail.get("po_accessories") == [], f"child po_accessories not empty: {detail.get('po_accessories')}"
    assert "material_request_number" in detail


# ---------- REGRESSION — dashboard endpoint returns 200 without scope ----------
def test_dashboard_no_scope_default(H):
    r = requests.get(f"{API}/dewi/cmt-kejar/dashboard", headers=H, timeout=60)
    assert r.status_code == 200
    d = r.json()
    assert d.get("scope") == "running"  # default
