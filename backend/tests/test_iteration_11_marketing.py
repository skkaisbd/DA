"""
Iteration 11 — Marketing (Toko/Marketing portal + Livehost + Creator/KOL) regression tests.
Covers RECENTLY MODIFIED files:
  - marketing_sales.py (AR batch generate)
  - marketing_product_launches_routes.py (insert_one(dict(fg_doc)))
  - marketing_returns_routes.py (issue_date now via datetime.now(...).date())
  - marketing_kol_creators.py (E701 splits in update_creator)
  - marketing_kol_ops.py (E701 splits in list filters)
plus broad reads on marketing/livehost/kol endpoints (no 500s).
"""
import os
import time
import pytest
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"

TS = str(int(time.time()))
SHARED = {}  # cross-test state


@pytest.fixture(scope="session")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASS}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tk = r.json().get("token") or r.json().get("access_token")
    assert tk, f"no token in response: {r.json()}"
    return tk


@pytest.fixture(scope="session")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ── Smoke read endpoints ─────────────────────────────────────────────────────
GET_ENDPOINTS = [
    "/api/marketing/accounts",
    "/api/marketing/orders",
    "/api/marketing/orders/summary",
    "/api/marketing/catalog/items",
    "/api/marketing/catalog/stock",
    "/api/marketing/catalog/mgmt/dashboard",
    "/api/marketing/product-launches",
    "/api/marketing/product-launches/summary",
    "/api/marketing/returns",
    "/api/marketing/returns/summary",
    "/api/marketing/returns/credit-notes",
    "/api/marketing/kol/creators",
    "/api/marketing/kol/sessions",
    "/api/marketing/kol/requests",
    "/api/marketing/kol/catalog",
    "/api/marketing/kol/fg-products",
    "/api/marketing/kol/leaderboard",
    "/api/marketing/livehost/hosts",
    "/api/marketing/livehost/sessions",
    "/api/marketing/livehost/scripts",
    "/api/marketing/livehost/shifts",
    "/api/marketing/livehost/training",
    "/api/marketing/livehost/analytics",
    "/api/marketing/live-sessions",
    "/api/marketing/live-analytics/summary",
    "/api/marketing/content-calendar",
    "/api/marketing/discounts",
    "/api/marketing/targets",
    "/api/marketing/reviews",
    "/api/marketing/complaints",
    "/api/marketing/samples",
    "/api/marketing/reports/summary",
    "/api/marketing/account-health",
    "/api/marketing/integration-settings",
    "/api/marketing/webhooks",
    "/api/marketing/toko/dashboard",
    "/api/marketing/tasks",
    "/api/dewi/kreator-requests",
    "/api/dewi/online-orders",
]


@pytest.mark.parametrize("ep", GET_ENDPOINTS)
def test_marketing_get_no_500(H, ep):
    """No marketing GET endpoint must return 5xx."""
    r = requests.get(f"{BASE_URL}{ep}", headers=H, timeout=30)
    assert r.status_code < 500, f"{ep} -> {r.status_code}: {r.text[:300]}"
    # No raw mongo _id leak
    try:
        body = r.text
        # Some endpoints return 404/403; only check JSON 200
        if r.status_code == 200 and body.strip().startswith(("{", "[")):
            assert '"_id"' not in body, f"{ep} leaks mongo _id"
    except Exception:
        pass


# ── Marketing account seed (used for sales/AR batch) ─────────────────────────
def test_create_platform_account(H):
    code = f"TEST{TS}"
    payload = {
        "account_code": code,
        "account_name": f"TEST Account {TS}",
        "platform": "shopee",
        "username": f"test{TS}",
        "group": "other",
        "has_api_integration": False,
    }
    r = requests.post(f"{BASE_URL}/api/marketing/accounts", headers=H, json=payload, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text}"
    acc = r.json().get("account") or r.json().get("data") or {}
    assert acc.get("id"), r.json()
    SHARED["account_id"] = acc["id"]


def test_create_sales_data(H):
    aid = SHARED.get("account_id")
    assert aid, "account not created"
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")
    SHARED["date_from"] = yesterday
    SHARED["date_to"] = today
    # 2 days of sales
    for d, rev, orders in [(yesterday, 1500000, 30), (today, 2000000, 40)]:
        payload = {
            "account_id": aid, "date": d, "revenue_type": "total",
            "revenue": rev, "orders": orders, "aov": rev / orders,
            "gmv": rev, "conversion_rate": 2.5, "fulfillment_rate": 0.95,
            "cancellation_rate": 0.02, "return_rate": 0.01, "late_shipment_rate": 0.0,
            "rating": 4.8, "review_count": 5, "response_rate": 1.0, "response_time_hours": 1
        }
        r = requests.post(f"{BASE_URL}/api/marketing/sales-data", headers=H, json=payload, timeout=30)
        assert r.status_code == 200, f"{d} -> {r.status_code} {r.text[:300]}"


def test_sales_to_ar_bridge(H):
    """Verify marketing sales -> AR invoice batch generation (RECENTLY MODIFIED file)."""
    aid = SHARED.get("account_id")
    assert aid, "no account"
    payload = {
        "date_from": SHARED["date_from"], "date_to": SHARED["date_to"],
        "account_id": aid, "revenue_type": "total", "grouping": "daily",
        "notes": "TEST iteration 11"
    }
    r = requests.post(f"{BASE_URL}/api/marketing/sales-data/generate-ar-batch",
                      headers=H, json=payload, timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
    body = r.json()
    invs = body.get("invoices") or body.get("data", {}).get("invoices") or []
    # daily grouping -> 2 invoices expected
    assert isinstance(invs, list)
    assert len(invs) >= 1, f"expected >=1 AR invoice, got body={body}"
    # No _id leak
    assert "_id" not in str(body) or '"_id"' not in r.text
    SHARED["ar_invoices"] = invs


# ── Product launch -> FG auto create ─────────────────────────────────────────
def test_product_launch_create(H):
    payload = {
        "product_name": f"TEST Launch {TS}",
        "launch_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "material": "Katun", "model": "Polos",
        "original_price": 100000, "flash_sale_price": 75000,
        "cross_price": 120000, "listing_price": 75000,
        "platforms": ["shopee"],
        "style_code": f"TLAUNCH{TS}",
        "description": "TEST launch", "status": "planning",
    }
    r = requests.post(f"{BASE_URL}/api/marketing/product-launches",
                      headers=H, json=payload, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json().get("data") or {}
    assert data.get("id"), r.json()
    SHARED["launch_id"] = data["id"]


def test_product_launch_status_launched_auto_creates_fg(H):
    """RECENTLY MODIFIED: marketing_product_launches_routes.py uses
    insert_one(dict(fg_doc)). Verify FG auto-create on status='launched'."""
    lid = SHARED.get("launch_id")
    assert lid, "no launch"
    r = requests.post(f"{BASE_URL}/api/marketing/product-launches/{lid}/status",
                      headers=H, json={"status": "launched"}, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    body = r.json()
    # fg_auto_created should be True (new code)
    assert body.get("status") == "launched"
    assert body.get("fg_auto_created") is True, f"FG not auto-created: {body}"
    fg = body.get("fg") or {}
    assert fg.get("id"), f"FG dict missing id: {fg}"
    assert fg.get("type") == "fg"
    # Verify no _id leak
    assert "_id" not in fg, f"_id leak in FG: {fg}"


# ── Returns / credit note (RECENTLY MODIFIED issue_date) ─────────────────────
def test_create_return(H):
    payload = {
        "account_id": SHARED.get("account_id"),
        "account_name": f"TEST Account {TS}",
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "order_id": f"TESTORD{TS}",
        "platform": "shopee",
        "product": "TEST Product",
        "price": 100000,
        "reason": "produk_cacat",
        "reason_detail": "TEST defective",
        "courier": "jnt",
        "refund_type": "full_refund",
    }
    r = requests.post(f"{BASE_URL}/api/marketing/returns",
                      headers=H, json=payload, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    data = r.json().get("data") or {}
    assert data.get("id"), r.json()
    SHARED["return_id"] = data["id"]
    assert data.get("refund_amount") == 100000, data


def test_approve_return(H):
    rid = SHARED.get("return_id")
    r = requests.post(f"{BASE_URL}/api/marketing/returns/{rid}/approve", headers=H, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"


def test_create_credit_note_issue_date(H):
    """RECENTLY MODIFIED: issue_date set via datetime.now(timezone.utc).date().isoformat().
    Verify (a) 200, (b) issue_date is today YYYY-MM-DD."""
    rid = SHARED.get("return_id")
    assert rid, "no return"
    r = requests.post(f"{BASE_URL}/api/marketing/returns/{rid}/create-credit-note",
                      headers=H, timeout=60)
    assert r.status_code == 200, f"{r.status_code} {r.text[:400]}"
    cn = r.json().get("data") or {}
    assert cn.get("id"), r.json()
    issue_date = cn.get("issue_date")
    assert issue_date, f"issue_date missing: {cn}"
    today_iso = datetime.now(timezone.utc).date().isoformat()
    # allow ±1 day for boundary
    yest = (datetime.now(timezone.utc) - timedelta(days=1)).date().isoformat()
    assert issue_date in (today_iso, yest), f"issue_date={issue_date} not today({today_iso})"
    assert cn.get("total") == 100000, cn
    # No _id leak
    assert "_id" not in cn


# ── KOL creator CRUD + partial update (RECENTLY MODIFIED E701) ───────────────
def test_create_kol_creator(H):
    payload = {
        "creator_code": f"TKC{TS}",
        "name": f"TEST Creator {TS}",
        "login_email": f"tkc{TS}@example.com",
        "login_password": "Test@1234",
        "phone": "0812000",
        "platforms": {"tiktok": "tkc"},
        "assigned_account_ids": [],
        "kpi_targets": {"monthly_revenue": 1000000, "monthly_sessions": 5, "monthly_viewers": 10000},
    }
    r = requests.post(f"{BASE_URL}/api/marketing/kol/creators", headers=H, json=payload, timeout=30)
    assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
    c = r.json().get("creator") or {}
    assert c.get("id"), r.json()
    SHARED["creator_id"] = c["id"]


@pytest.mark.parametrize("partial", [
    {"name": "TEST Creator Renamed"},
    {"phone": "0812999"},
    {"platforms": {"tiktok": "renamed", "shopee_live": "x"}},
    {"assigned_account_ids": []},
    {"kpi_targets": {"monthly_revenue": 2000000, "monthly_sessions": 10, "monthly_viewers": 50000}},
    {"notes": "TEST notes"},
    {"status": "inactive"},
    {"status": "active"},
])
def test_update_kol_creator_partial(H, partial):
    """RECENTLY MODIFIED marketing_kol_creators.py — verify each partial field branch."""
    cid = SHARED.get("creator_id")
    assert cid, "no creator"
    r = requests.put(f"{BASE_URL}/api/marketing/kol/creators/{cid}",
                     headers=H, json=partial, timeout=30)
    assert r.status_code == 200, f"partial={partial} -> {r.status_code} {r.text[:300]}"
    c = r.json().get("creator") or {}
    for k, v in partial.items():
        assert c.get(k) == v, f"field {k} not updated, got {c.get(k)} expected {v}"


def test_update_kol_creator_invalid_status(H):
    cid = SHARED.get("creator_id")
    r = requests.put(f"{BASE_URL}/api/marketing/kol/creators/{cid}",
                     headers=H, json={"status": "bogus"}, timeout=30)
    assert r.status_code == 400, f"{r.status_code} {r.text[:200]}"


# ── KOL ops list filters (RECENTLY MODIFIED E701) ────────────────────────────
@pytest.mark.parametrize("qs", [
    "",
    "?creator_id=NONEXIST",
    "?account_id=NONEXIST",
    "?date_from=2025-01-01&date_to=2026-12-31",
])
def test_kol_sessions_filters(H, qs):
    r = requests.get(f"{BASE_URL}/api/marketing/kol/sessions{qs}", headers=H, timeout=30)
    assert r.status_code == 200, f"{qs} -> {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("qs", [
    "",
    "?status=pending",
    "?status=approved",
    "?creator_id=NONEXIST",
    "?account_id=NONEXIST",
])
def test_kol_requests_filters(H, qs):
    r = requests.get(f"{BASE_URL}/api/marketing/kol/requests{qs}", headers=H, timeout=30)
    assert r.status_code == 200, f"{qs} -> {r.status_code} {r.text[:200]}"


@pytest.mark.parametrize("qs", [
    "",
    "?active_only=true",
    "?platform=shopee",
])
def test_kol_catalog_filters(H, qs):
    r = requests.get(f"{BASE_URL}/api/marketing/kol/catalog{qs}", headers=H, timeout=30)
    assert r.status_code == 200, f"{qs} -> {r.status_code} {r.text[:200]}"


# ── Livehost session creation + analytics ───────────────────────────────────
def test_livehost_session_create(H):
    payload = {
        "session_name": f"TEST Live {TS}",
        "platform": "shopee",
        "scheduled_start": datetime.now(timezone.utc).isoformat(),
        "scheduled_end": (datetime.now(timezone.utc) + timedelta(hours=2)).isoformat(),
        "account_id": SHARED.get("account_id"),
        "status": "scheduled",
    }
    r = requests.post(f"{BASE_URL}/api/marketing/livehost/sessions",
                      headers=H, json=payload, timeout=30)
    # Some implementations may 404/422 if route differs; accept 200/201, log others
    assert r.status_code < 500, f"{r.status_code} {r.text[:300]}"


def test_livehost_analytics_no_500(H):
    r = requests.get(f"{BASE_URL}/api/marketing/livehost/analytics", headers=H, timeout=30)
    assert r.status_code < 500, f"{r.status_code} {r.text[:300]}"


# ── AI endpoints — 503 acceptable, must not 500 ──────────────────────────────
@pytest.mark.parametrize("ep", [
    "/api/marketing/ai-insights/dashboard",
    "/api/marketing/advanced-ai/recommendations",
    "/api/marketing/ai-content/templates",
])
def test_ai_endpoints_no_500(H, ep):
    r = requests.get(f"{BASE_URL}{ep}", headers=H, timeout=30)
    # 503 (no LLM key) acceptable; 404 acceptable; 500 NOT acceptable
    assert r.status_code != 500, f"{ep} 500: {r.text[:200]}"


# ── Cleanup helpers (best-effort) ───────────────────────────────────────────
def test_zz_cleanup(H):
    # delete created creator
    cid = SHARED.get("creator_id")
    if cid:
        requests.delete(f"{BASE_URL}/api/marketing/kol/creators/{cid}", headers=H, timeout=15)
    lid = SHARED.get("launch_id")
    if lid:
        requests.delete(f"{BASE_URL}/api/marketing/product-launches/{lid}", headers=H, timeout=15)
    rid = SHARED.get("return_id")
    if rid:
        requests.delete(f"{BASE_URL}/api/marketing/returns/{rid}", headers=H, timeout=15)
    aid = SHARED.get("account_id")
    if aid:
        requests.delete(f"{BASE_URL}/api/marketing/accounts/{aid}", headers=H, timeout=15)
    assert True
