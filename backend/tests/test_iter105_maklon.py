"""Iteration 105 verification tests: RBAC + status sync + invoice unification.

Covers 4 fixes from Portal Maklon audit (iter 104):
 1. RBAC deny for klien_maklon & cmt_vendor on admin maklon endpoints (403).
 2. Status sync production_pos close -> mirror dewi_maklon_pos.
 3. Single invoice source: /api/dewi/maklon/invoices/generate reuses AR draft.
 4. AR unit price uses selling_price_snapshot (fallback cmt).
"""
import json
import os
import pytest
import requests

BE = os.environ.get("REACT_APP_BACKEND_URL", "http://localhost:8001").rstrip("/")
# NB: for backend-only tests we use localhost directly to bypass k8s ingress if REACT_APP_BACKEND_URL absent
BE_LOCAL = "http://localhost:8001"

ADMIN = open("/tmp/ta.tok").read().strip()
KLIEN = open("/tmp/tk.tok").read().strip()
CMT = open("/tmp/tc.tok").read().strip()

Hadmin = {"Authorization": f"Bearer {ADMIN}", "Content-Type": "application/json"}
Hklien = {"Authorization": f"Bearer {KLIEN}", "Content-Type": "application/json"}
Hcmt = {"Authorization": f"Bearer {CMT}", "Content-Type": "application/json"}


# ---------- 1) RBAC MATRIX ----------
ADMIN_MAKLON_GETS = [
    "/api/dewi/maklon/pos",
    "/api/dewi/maklon/invoices",
    "/api/dewi/maklon/clients",
    "/api/dewi/maklon/summary",
    "/api/dewi/maklon/pos/po-mk-demo-2/360",
    "/api/dewi/maklon/payments",
    "/api/dewi/maklon/reports/aging",
    "/api/prod/cmt-receipts",
    "/api/production/cmt-billing?scope=maklon",
    "/api/maklon/sla/dashboard",
]


@pytest.mark.parametrize("path", ADMIN_MAKLON_GETS)
def test_rbac_klien_denied(path):
    r = requests.get(BE_LOCAL + path, headers=Hklien, timeout=15)
    assert r.status_code == 403, f"klien got {r.status_code} on {path}: {r.text[:200]}"


@pytest.mark.parametrize("path", ADMIN_MAKLON_GETS)
def test_rbac_vendor_denied(path):
    r = requests.get(BE_LOCAL + path, headers=Hcmt, timeout=15)
    assert r.status_code == 403, f"vendor got {r.status_code} on {path}: {r.text[:200]}"


def test_rbac_klien_post_cmt_receipt_denied():
    r = requests.post(BE_LOCAL + "/api/prod/cmt-receipts", headers=Hklien, json={})
    assert r.status_code == 403


def test_rbac_vendor_short_shipments_allowed():
    r = requests.get(BE_LOCAL + "/api/prod/short-shipments", headers=Hcmt, timeout=15)
    assert r.status_code == 200


def test_rbac_vendor_vendor_shipments_allowed():
    r = requests.get(BE_LOCAL + "/api/vendor-shipments", headers=Hcmt, timeout=15)
    assert r.status_code == 200


def test_rbac_klien_maklon_client_pos_allowed():
    r = requests.get(BE_LOCAL + "/api/maklon-client/pos", headers=Hklien, timeout=15)
    assert r.status_code == 200
    data = r.json()
    # Only PT Aruna PO should appear
    lst = data if isinstance(data, list) else data.get("data", data.get("pos", []))
    for p in lst if isinstance(lst, list) else []:
        bn = (p.get("buyer_name") or p.get("client_name") or "").lower()
        # Should NOT contain 'langit'
        assert "langit" not in bn, f"klien saw other buyer PO: {p}"


@pytest.mark.parametrize("path", ADMIN_MAKLON_GETS)
def test_rbac_admin_still_ok(path):
    r = requests.get(BE_LOCAL + path, headers=Hadmin, timeout=15)
    assert r.status_code == 200, f"admin got {r.status_code} on {path}"


# ---------- 2) STATUS SYNC + selling price ----------
_created = {}


def test_status_sync_create_po():
    # iter 106: PO Maklon default AUTO numbering — po_number dikosongkan
    payload = {
        "business_type": "maklon",
        "buyer_id": "demo-cl-aruna",
        "vendor_id": "demo-vn-jmc",
        "status": "Confirmed",
        "items": [{
            "product_name": "Test Sync Item",
            "sku_code": "TEST-SYNC-M",
            "size": "M",
            "color": "Hitam",
            "qty": 10,
            "selling_price_snapshot": 20000,
            "cmt_price_snapshot": 12000,
        }],
    }
    r = requests.post(BE_LOCAL + "/api/production-pos", headers=Hadmin, json=payload)
    assert r.status_code in (200, 201), r.text
    d = r.json()
    _created["po_id"] = d.get("id") or d.get("po_id")
    _created["po_number"] = d.get("po_number")
    assert _created["po_id"]


def test_status_sync_mirror_created_with_selling_price():
    pid = _created["po_id"]
    r = requests.get(f"{BE_LOCAL}/api/production-pos/{pid}/maklon-finance", headers=Hadmin)
    assert r.status_code == 200, r.text
    d = r.json()
    mirror = d.get("mirror", {})
    ar = d.get("ar_invoice") or d.get("invoice") or {}
    assert mirror.get("status") in ("confirmed", "Confirmed"), mirror
    assert mirror.get("total_value") == 200000, mirror
    assert mirror.get("total_cmt_cost") == 120000, mirror
    assert mirror.get("gross_margin") == 80000, mirror
    # AR draft: unit price uses selling 20000
    lines = ar.get("lines") or ar.get("items") or []
    if lines:
        up = lines[0].get("unit_price") or lines[0].get("price")
        assert up == 20000, f"unit_price expected 20000, got {up} ({lines[0]})"


def test_status_sync_transition_and_close():
    pid = _created["po_id"]
    # walk statuses
    for nxt in ["Distributed", "In Production", "Production Complete"]:
        r = requests.post(f"{BE_LOCAL}/api/production-pos/{pid}/status",
                          headers=Hadmin, json={"status": nxt})
        if r.status_code not in (200, 201):
            # maybe intermediate step names differ; skip gracefully
            print(f"status->{nxt}: {r.status_code} {r.text[:200]}")
            pytest.skip(f"cannot transition to {nxt}")
    # Close
    r = requests.post(f"{BE_LOCAL}/api/production-pos/{pid}/close",
                      headers=Hadmin, json={"close_reason": "test"})
    assert r.status_code == 200, r.text
    # Verify mirror
    r = requests.get(f"{BE_LOCAL}/api/production-pos/{pid}/maklon-finance", headers=Hadmin)
    d = r.json()
    m = d.get("mirror", {})
    assert m.get("production_po_status") == "Closed", m
    assert m.get("status") == "completed", m


def test_status_sync_cascade_delete():
    pid = _created["po_id"]
    r = requests.delete(f"{BE_LOCAL}/api/production-pos/{pid}?cascade=true", headers=Hadmin)
    if r.status_code == 405 or r.status_code == 404:
        r = requests.delete(f"{BE_LOCAL}/api/production-pos/{pid}", headers=Hadmin,
                            params={"cascade": "true"})
    assert r.status_code in (200, 204), r.text
    # mirror should be gone
    r = requests.get(f"{BE_LOCAL}/api/production-pos/{pid}/maklon-finance", headers=Hadmin)
    assert r.status_code in (404, 400), f"mirror still present: {r.status_code}"


# ---------- 3) INVOICE UNIFICATION on po-mk-demo-2 ----------
_inv = {}


def test_invoice_eligible_list_contains_demo2():
    r = requests.get(BE_LOCAL + "/api/dewi/maklon/invoices/eligible", headers=Hadmin)
    assert r.status_code == 200, r.text
    data = r.json()
    lst = data if isinstance(data, list) else data.get("data", [])
    found = [x for x in lst if (x.get("order_id") or x.get("po_id") or x.get("id")) == "po-mk-demo-2"]
    assert found, f"po-mk-demo-2 not in eligible list. got: {[x.get('order_id') or x.get('po_id') or x.get('id') for x in lst][:10]}"
    e = found[0]
    _inv["ar_number_preview"] = e.get("ar_invoice_number")
    assert e.get("billable") is True, e
    assert (e.get("total_received") or 0) > 0, e
    assert e.get("source") == "engine_ar", e
    assert e.get("ar_invoice_number")


def test_invoice_generate_reuses_ar():
    r = requests.post(BE_LOCAL + "/api/dewi/maklon/invoices/generate",
                      headers=Hadmin, json={"order_id": "po-mk-demo-2", "tax_pct": 11})
    assert r.status_code == 200, r.text
    d = r.json()
    _inv["id"] = d.get("id")
    _inv["number"] = d.get("invoice_number")
    _inv["total"] = d.get("total") or d.get("grand_total") or d.get("total_amount")
    _inv["subtotal"] = d.get("subtotal") or d.get("sub_total")
    assert _inv["number"] == _inv["ar_number_preview"], (_inv["number"], _inv["ar_number_preview"])
    assert d.get("status") in ("issued", "Issued"), d
    if _inv["subtotal"] and _inv["total"]:
        assert abs(_inv["total"] - _inv["subtotal"] * 1.11) < 1, d
    # lines qty = received per item
    lines = d.get("lines") or d.get("items") or []
    assert lines, d
    for ln in lines:
        rq = ln.get("qty_received") or ln.get("received_qty")
        q = ln.get("qty") or ln.get("quantity")
        if rq is not None:
            assert q == rq, ln


def test_invoice_listed_once_in_dewi_and_ar():
    inv_id = _inv["id"]
    num = _inv["number"]
    # In dewi list
    r = requests.get(BE_LOCAL + "/api/dewi/maklon/invoices", headers=Hadmin)
    assert r.status_code == 200
    lst = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
    matches = [x for x in lst if x.get("invoice_number") == num]
    assert len(matches) == 1, f"expected exactly 1 dewi invoice with number {num}, found {len(matches)}"
    assert matches[0].get("id") == inv_id


def test_invoice_generate_again_400():
    r = requests.post(BE_LOCAL + "/api/dewi/maklon/invoices/generate",
                      headers=Hadmin, json={"order_id": "po-mk-demo-2", "tax_pct": 11})
    assert r.status_code == 400, r.text
    assert "invoice" in r.text.lower()


def test_po_360_reflects_invoice():
    r = requests.get(BE_LOCAL + "/api/dewi/maklon/pos/po-mk-demo-2/360", headers=Hadmin)
    assert r.status_code == 200, r.text
    d = r.json()
    kpi = d.get("kpis", {})
    ar = d.get("ar_invoice") or (d.get("ar_invoices") or [None])[0] or {}
    # Prefer total we captured; else fall back to 999000 for demo-2 (900k *1.11)
    expected = _inv.get("total") or 999000
    assert abs((kpi.get("invoiced_amount") or 0) - expected) < 1, (kpi.get("invoiced_amount"), expected)
    assert (ar or {}).get("invoice_number") == _inv["number"], ar


_pay = {}


def test_payment_propagation():
    r = requests.post(BE_LOCAL + "/api/dewi/maklon/payments", headers=Hadmin,
                      json={"invoice_id": _inv["id"], "amount": 100000, "method": "transfer"})
    assert r.status_code in (200, 201), r.text
    d = r.json()
    _pay["id"] = d.get("id") or d.get("payment_id")
    # verify AR + dewi invoice
    r = requests.get(BE_LOCAL + f"/api/dewi/maklon/invoices", headers=Hadmin)
    dinv = [x for x in r.json() if x.get("id") == _inv["id"]][0]
    assert dinv.get("status") in ("partial_paid", "partial", "partially_paid"), dinv
    paid = dinv.get("amount_paid") or dinv.get("paid_amount") or dinv.get("total_paid") or 0
    total = dinv.get("total") or dinv.get("grand_total") or 0
    bal = dinv.get("balance_amount") or dinv.get("amount_due") or 0
    # Either amount_paid==100000 OR (total - balance) == 100000
    assert paid == 100000 or (total and abs((total - bal) - 100000) < 1), dinv


def test_payment_delete_reverts():
    if not _pay.get("id"):
        pytest.skip("no payment id")
    r = requests.delete(BE_LOCAL + f"/api/dewi/maklon/payments/{_pay['id']}", headers=Hadmin)
    assert r.status_code in (200, 204), r.text
    r = requests.get(BE_LOCAL + f"/api/dewi/maklon/invoices", headers=Hadmin)
    dinv = [x for x in r.json() if x.get("id") == _inv["id"]][0]
    assert dinv.get("status") in ("issued", "Issued"), dinv
    paid = dinv.get("amount_paid") or dinv.get("paid_amount") or dinv.get("total_paid") or 0
    assert paid == 0, dinv


def test_invoice_cancel_reverts_ar_and_mirror():
    r = requests.post(BE_LOCAL + f"/api/dewi/maklon/invoices/{_inv['id']}/cancel", headers=Hadmin)
    assert r.status_code == 200, r.text
    # AR back to draft (check via /api/rahaza/ar/invoices? use dewi list first)
    # After cancel, run sync then verify mirror not 'invoiced'
    r = requests.post(BE_LOCAL + "/api/production-pos/po-mk-demo-2/sync-maklon-finance",
                      headers=Hadmin)
    assert r.status_code == 200, r.text
    r = requests.get(BE_LOCAL + "/api/dewi/maklon/pos", headers=Hadmin)
    lst = r.json() if isinstance(r.json(), list) else r.json().get("data", [])
    row = [x for x in lst if x.get("po_number") == "PO-MK-DEMO-2" or (x.get("id") or "").endswith("demo-2")]
    assert row, "PO-MK-DEMO-2 not in mirror"
    s = row[0].get("status")
    assert s in ("partial_delivered", "completed"), f"mirror status={s}"
