"""
test_p2p_full_cycle.py — End-to-end P2P Procurement cycle via API.
Drives the FULL chain as admin:
  PR create → submit → approve x3 → create-PO → PO submit → PO approve
  → create-GR → receive GR → AP invoice from GR → AP payment → 3-way match.

Run: REACT_APP_BACKEND_URL=<url> python -m pytest tests/test_p2p_full_cycle.py -q
"""
import os
import time
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def s():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.text[:200]}"
    sess = requests.Session()
    sess.headers.update({"Authorization": f"Bearer {r.json()['token']}", "Content-Type": "application/json"})
    return sess


def test_full_p2p_cycle(s):
    tag = str(int(time.time()))
    # 1. Create PR (single item for clean material matching)
    pr_payload = {
        "title": f"E2E Test PR {tag}",
        "description": "Pengujian siklus P2P penuh",
        "request_type": "consumable",
        "department": "Produksi",
        "priority": "high",
        "justification": "Automated e2e test",
        "items": [{"name": "Kain Katun Test", "specification": "30s combed", "qty": 100,
                    "unit": "meter", "estimated_price": 25000}],
    }
    r = s.post(f"{API}/procurement/requests", json=pr_payload, timeout=30)
    assert r.status_code in (200, 201), f"create PR: {r.status_code} {r.text[:200]}"
    pr = r.json()
    pr_id = pr["id"]
    assert pr["status"] == "draft"

    # 2. Submit
    r = s.post(f"{API}/procurement/requests/{pr_id}/submit", json={}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["new_status"] == "submitted"

    # 3. Approve x3 (submitted → dept_approved → finance_approved → approved)
    for expected in ("dept_approved", "finance_approved", "approved"):
        r = s.post(f"{API}/procurement/requests/{pr_id}/approve", json={"comment": "ok"}, timeout=30)
        assert r.status_code == 200, f"approve->{expected}: {r.text[:200]}"
        assert r.json()["new_status"] == expected

    # 4. Create PO from approved PR
    r = s.post(f"{API}/procurement/requests/{pr_id}/create-po",
               json={"vendor_name": "CV. Kain Nusantara", "expected_delivery_date": "2026-06-30"}, timeout=30)
    assert r.status_code in (200, 201), f"create-po: {r.text[:200]}"
    po = r.json()
    po_id = po["id"]
    assert po["status"] == "draft"
    assert po.get("from_pr_id") == pr_id

    # 5. Submit + approve PO
    r = s.post(f"{API}/rahaza/purchase-orders/{po_id}/submit", json={}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["status"] == "pending_approval"
    r = s.post(f"{API}/rahaza/purchase-orders/{po_id}/approve", json={}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["status"] == "approved"

    # 6. Create GR (draft) from PO
    r = s.post(f"{API}/rahaza/purchase-orders/{po_id}/create-gr", json={"notes": "e2e GR"}, timeout=30)
    assert r.status_code in (200, 201), f"create-gr: {r.text[:200]}"
    gr = r.json()
    gr_id = gr["id"]
    assert gr["po_id"] == po_id
    assert gr["status"] == "draft"
    gr_items = gr["items"]
    assert len(gr_items) >= 1

    # 7. Receive the GR (fill received_qty, flip status to received) via legacy bridge
    recv_items = []
    for it in gr_items:
        recv_items.append({**it, "received_qty": it["expected_qty"], "rejected_qty": 0})
    r = s.put(f"{API}/wms/legacy/receiving/{gr_id}", json={"status": "received", "items": recv_items}, timeout=30)
    assert r.status_code == 200, f"receive GR: {r.text[:200]}"

    # PO should now be fully_received
    r = s.get(f"{API}/rahaza/purchase-orders/{po_id}", timeout=30)
    assert r.status_code == 200
    assert r.json()["status"] in ("fully_received", "partially_received"), r.json().get("status")

    # 8. GR should be available for invoice
    r = s.get(f"{API}/rahaza/grs/available-for-invoice", params={"po_id": po_id}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    avail = r.json().get("items", [])
    assert any(g["id"] == gr_id for g in avail), "GR not available for invoice"

    # 9. Create AP invoice from GR
    r = s.post(f"{API}/rahaza/ap-invoices/from-gr",
               json={"gr_ids": [gr_id], "tax_pct": 11, "payment_terms": "net_30"}, timeout=30)
    assert r.status_code in (200, 201), f"ap-from-gr: {r.text[:200]}"
    ap = r.json()
    ap_id = ap["id"]
    assert po_id in (ap.get("po_ids") or [])
    assert ap["total"] > 0

    # 10. Record full payment
    r = s.post(f"{API}/rahaza/ap-invoices/{ap_id}/payment",
               json={"amount": ap["total"], "notes": "e2e full payment"}, timeout=30)
    assert r.status_code == 200, f"ap payment: {r.text[:200]}"
    assert r.json()["status"] == "paid"

    # 11. 3-way match dashboard shows this PO as matched
    r = s.get(f"{API}/rahaza/3way-match", timeout=30)
    assert r.status_code == 200, r.text[:200]
    rows = r.json().get("rows", [])
    row = next((x for x in rows if x["po_id"] == po_id), None)
    assert row is not None, "PO not in 3-way match dashboard"
    assert row["invoice_count"] >= 1
    assert row["match_status"] == "matched", f"expected matched, got {row['match_status']}"
    assert row["total_paid"] > 0
