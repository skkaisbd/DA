"""INV-F28 iteration 76 — verifies the ADDITIONAL seed data now exists in DB:
- PO-MKL-202608-9351 (main, 100 pcs, sisa kirim 90)
- REQ-RPL-1-PO-MKL-202608-9351 (Approved replacement) -> SJ child *-R1 (5 pcs)
- PO-MKL-202608-9196 status Completed 200 pcs (only in scope=all)
- PO-MKL-202608-9432 status Draft 50 pcs (counted in qty_not_sent_draft)
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"
MAIN_PO = "PO-MKL-202608-9351"
COMPLETED_PO = "PO-MKL-202608-9196"
DRAFT_PO = "PO-MKL-202608-9432"
REPL_REQ = "REQ-RPL-1-PO-MKL-202608-9351"
PARENT_SJ = "SJ-MTR-PO-MKL-202608-9351"
CHILD_SJ = "SJ-MTR-PO-MKL-202608-9351-R1"


@pytest.fixture(scope="module")
def H():
    time.sleep(2)
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


# ---------- scope=running vs scope=all differ by 200 pcs / 1 PO ----------
def test_scope_running_excludes_completed_po(H):
    r = requests.get(f"{API}/dewi/cmt-kejar", params={"scope": "running"},
                     headers=H, timeout=60).json()
    pos = [x.get("po_number") for x in (r.get("rows") or [])]
    assert MAIN_PO in pos
    assert COMPLETED_PO not in pos, f"Completed PO leaked into scope=running: {pos}"


def test_scope_all_includes_completed_po(H):
    r = requests.get(f"{API}/dewi/cmt-kejar", params={"scope": "all"},
                     headers=H, timeout=60).json()
    pos = [x.get("po_number") for x in (r.get("rows") or [])]
    assert COMPLETED_PO in pos, f"Completed PO missing from scope=all: {pos}"


def test_dashboard_scope_diff_is_200_pcs_and_1_po(H):
    run = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                       params={"scope": "running"}, headers=H, timeout=60).json()
    alls = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                        params={"scope": "all"}, headers=H, timeout=60).json()
    assert alls["total_po"] - run["total_po"] == 1, (run, alls)
    assert alls["qty_ordered"] - run["qty_ordered"] == 200, (run, alls)


# ---------- qty_not_sent_draft reflects DRAFT PO 50 pcs ----------
def test_dashboard_qty_not_sent_draft_reports_draft_po(H):
    run = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                       params={"scope": "running"}, headers=H, timeout=60).json()
    assert run.get("qty_not_sent_draft", 0) >= 50, (
        f"expected qty_not_sent_draft >= 50 (PO-MKL-202608-9432 Draft 50 pcs), got {run.get('qty_not_sent_draft')}")


# ---------- qty_sent_extra shows 5 (replacement) and by_type includes REPLACEMENT ----------
def test_dashboard_qty_sent_extra_has_replacement(H):
    run = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                       params={"scope": "running"}, headers=H, timeout=60).json()
    assert run.get("qty_sent_extra", 0) >= 5, run
    by = run.get("qty_sent_extra_by_type") or {}
    # accept case-insensitive REPLACEMENT key
    keys = {str(k).upper(): v for k, v in by.items()}
    assert keys.get("REPLACEMENT", 0) >= 5, by


# ---------- MAIN PO potongan = 100 (order), extras separated ----------
def test_main_po_potongan_only_normal(H):
    r = requests.get(f"{API}/dewi/cmt-kejar", params={"scope": "running"},
                     headers=H, timeout=60).json()
    tgt = next((x for x in r.get("rows", []) if x.get("po_number") == MAIN_PO), None)
    assert tgt is not None
    assert tgt["qty_ordered"] == 100
    # potongan (qty_sent_cmt) must not exceed order — replacement 5 must not add
    assert tgt["qty_sent_cmt"] <= 100, tgt
    assert tgt.get("qty_sent_extra", 0) >= 5, tgt


# ---------- Material request enrichment ----------
def test_material_request_replacement_enriched(H):
    r = requests.get(f"{API}/material-requests",
                     params={"request_type": "REPLACEMENT"}, headers=H, timeout=60).json()
    rows = r if isinstance(r, list) else (r.get("rows") or r.get("items") or [])
    tgt = next((x for x in rows if x.get("request_number") == REPL_REQ), None)
    assert tgt is not None, f"{REPL_REQ} missing"
    assert str(tgt.get("status")).lower() in ("approved", "disetujui")
    assert tgt.get("child_shipment_number") == CHILD_SJ, tgt
    assert "child_shipment_status" in tgt
    assert tgt.get("child_inspected") is False, tgt


# ---------- Parent shipment retains po_accessories AND has child_qty_total=5 ----------
def test_parent_shipment_has_child_qty_and_accessories(H):
    rs = requests.get(f"{API}/vendor-shipments", headers=H, timeout=60).json()
    rows = rs if isinstance(rs, list) else (rs.get("rows") or rs.get("items") or [])
    parent = next((s for s in rows if s.get("shipment_number") == PARENT_SJ), None)
    assert parent is not None
    pd = requests.get(f"{API}/vendor-shipments/{parent['id']}", headers=H, timeout=60).json()
    assert pd.get("child_qty_total") == 5, pd.get("child_qty_total")
    assert isinstance(pd.get("po_accessories") or [], list) and len(pd.get("po_accessories") or []) > 0, (
        "parent SJ MUST still expose po_accessories")


# ---------- Child shipment has po_accessories=[] and material_request_number ----------
def test_child_shipment_shape(H):
    rs = requests.get(f"{API}/vendor-shipments", headers=H, timeout=60).json()
    rows = rs if isinstance(rs, list) else (rs.get("rows") or rs.get("items") or [])
    child = next((s for s in rows if s.get("shipment_number") == CHILD_SJ), None)
    assert child is not None, f"{CHILD_SJ} missing"
    cd = requests.get(f"{API}/vendor-shipments/{child['id']}", headers=H, timeout=60).json()
    assert cd.get("is_child_shipment") is True, cd
    assert cd.get("po_accessories") == [], cd.get("po_accessories")
    assert cd.get("material_request_number") == REPL_REQ, cd.get("material_request_number")


# ---------- buyer outstanding board contains MAIN_PO with sisa kirim 90 ----------
def test_buyer_outstanding_board_has_main_po(H):
    r = requests.get(f"{API}/buyer-dispatch-outstanding", headers=H, timeout=60)
    assert r.status_code == 200, r.text[:200]
    body = r.json()
    rows = body if isinstance(body, list) else (body.get("rows") or body.get("items") or body.get("data") or [])
    row = next((x for x in rows if x.get("po_number") == MAIN_PO), None)
    assert row is not None, f"{MAIN_PO} missing on outstanding board"
    # sisa kirim ~ 90
    sisa = row.get("shippable") or row.get("qty_shippable_buyer") or row.get("sisa_bisa_kirim") or 0
    assert sisa >= 90, row
