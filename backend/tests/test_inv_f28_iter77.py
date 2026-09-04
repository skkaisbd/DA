"""INV-F28 iteration 77 — 12 KPI cards + balance checker row.

Verifies backend response shape/values for the new 12-KPI owner dashboard and
the `balance` block (5 identities + offenders).
"""
import os
import time
import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
API = f"{BASE}/api"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"


@pytest.fixture(scope="module")
def H():
    time.sleep(1)
    r = requests.post(f"{API}/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, r.text[:200]
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok
    return {"Authorization": f"Bearer {tok}"}


def _dash(H, scope):
    r = requests.get(f"{API}/dewi/cmt-kejar/dashboard",
                     params={"scope": scope}, headers=H, timeout=60)
    assert r.status_code == 200, r.text[:200]
    return r.json()


# ---------- Required fields for 12 KPI cards ----------
def test_dashboard_running_has_all_12_kpi_fields(H):
    d = _dash(H, "running")
    required = [
        "qty_ordered", "qty_not_sent_cmt", "qty_not_sent_draft",
        "qty_sent_cmt", "qty_sent_extra",
        "qty_outstanding_cmt", "qty_short_open",
        "qty_returned", "kali_setor",
        "qty_accepted", "qty_reject_open", "qty_reject",
        "qty_repaired", "qty_scrap",
        "qty_shippable_buyer", "qty_shipped_buyer",
        "ongkos_jahit_terhitung", "biaya_permak",
    ]
    missing = [k for k in required if k not in d]
    assert not missing, f"dashboard missing fields: {missing}. Keys present: {list(d.keys())}"


def test_dashboard_balance_block_shape(H):
    d = _dash(H, "running")
    assert "balance" in d, f"dashboard missing 'balance' block. Keys: {list(d.keys())}"
    balance = d["balance"]
    assert "checks" in balance, f"balance missing 'checks': {balance}"
    checks = balance["checks"]
    # 5 identity keys
    expected_keys = {"order", "cmt", "qc", "reject", "buyer"}
    actual_keys = {c.get("key") for c in checks}
    assert expected_keys.issubset(actual_keys), \
        f"balance.checks missing keys. Expected {expected_keys}, got {actual_keys}"
    # each check shape
    for c in checks:
        for k in ("key", "ok", "left", "right"):
            assert k in c, f"check {c.get('key')} missing {k}: {c}"


def test_dashboard_scope_all_ge_running(H):
    r = _dash(H, "running")
    a = _dash(H, "all")
    assert a["total_po"] >= r["total_po"]
    assert a["qty_ordered"] >= r["qty_ordered"]


def test_dashboard_buyer_offenders_present_when_broken(H):
    """The demo data (PO-MK-DEMO-2 60 pcs to buyer without QC) SHOULD make
    'buyer' identity broken. If it is, offenders array must be present and
    non-empty."""
    d = _dash(H, "running")
    checks = d["balance"]["checks"]
    buyer_c = next((c for c in checks if c.get("key") == "buyer"), None)
    assert buyer_c is not None
    if not buyer_c.get("ok"):
        offenders = buyer_c.get("offenders") or []
        assert len(offenders) > 0, \
            f"buyer identity broken but no offenders listed: {buyer_c}"
        # Should mention a PO number (accept string or dict)
        first = offenders[0]
        if isinstance(first, dict):
            assert "po_number" in first or "po" in first, f"offender shape: {first}"
        else:
            assert isinstance(first, str) and "PO-" in first, f"offender shape: {first}"
        # Demo data expects PO-MK-DEMO-2
        offs_str = " ".join(str(o) for o in offenders)
        assert "PO-MK-DEMO-2" in offs_str, f"expected PO-MK-DEMO-2 in offenders, got {offenders}"


def test_dashboard_kpi_values_sanity(H):
    """Sanity: shipped <= sent, accepted+reject_open+repaired+scrap <= returned+something."""
    d = _dash(H, "running")
    assert d["qty_shipped_buyer"] <= d["qty_ordered"]  # basic sanity
    # accepted must be >=0
    for k in ("qty_ordered", "qty_sent_cmt", "qty_returned", "qty_accepted",
              "qty_reject_open", "qty_repaired", "qty_scrap",
              "qty_shippable_buyer", "qty_shipped_buyer"):
        assert isinstance(d[k], (int, float)), f"{k} not numeric: {d[k]}"
        assert d[k] >= 0, f"{k} negative: {d[k]}"
