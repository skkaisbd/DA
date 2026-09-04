# Backend tests — F9 Pencairan Marketplace (marketing settlements)
import os
import time

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
ACCOUNT_ID = "c386b3ce-2b85-453a-88a3-b3e5e37277be"

STATE = {}


@pytest.fixture(scope="session")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=60)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text[:300]}"
    data = r.json()
    token = data.get("token")
    assert token, f"no token in login response: {list(data.keys())}"
    assert data.get("user", {}).get("email") == ADMIN["email"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


# ── Login / accounts ────────────────────────────────────────────────
def test_accounts_list(client):
    r = client.get(f"{BASE_URL}/api/marketing/accounts?limit=200", timeout=60)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    rows = body if isinstance(body, list) else (body.get("data") or body.get("accounts") or [])
    assert isinstance(rows, list) and rows
    ids = [a.get("id") for a in rows]
    assert ACCOUNT_ID in ids, f"seeded account missing; got {ids[:5]}"


# ── LIST + summary shape ────────────────────────────────────────────
def test_list_settlements_shape(client):
    r = client.get(f"{BASE_URL}/api/marketing/settlements?page_size=50", timeout=60)
    assert r.status_code == 200, r.text[:300]
    b = r.json()
    assert b["ok"] is True
    assert isinstance(b["data"], list)
    for k in ("gross_sales", "net_payout", "total_deductions", "deduction_pct", "unverified_count"):
        assert k in b["summary"], f"missing summary key {k}"
    for k in ("total", "page", "page_size", "total_pages"):
        assert k in b["pagination"]
    for row in b["data"]:
        assert "_id" not in row


def test_seeded_stl_test_001_present(client):
    r = client.get(f"{BASE_URL}/api/marketing/settlements?page_size=200", timeout=60)
    rows = r.json()["data"]
    match = [x for x in rows if x.get("settlement_id") == "STL-TEST-001"]
    assert match, "STL-TEST-001 not found"
    assert match[0].get("je_number")
    assert match[0].get("je_status") == "posted"


# ── CREATE unbalanced ───────────────────────────────────────────────
def test_create_unbalanced(client):
    sid_biz = f"STL-QA-{int(time.time())}"
    payload = {
        "account_id": ACCOUNT_ID,
        "platform": "shopee",
        "settlement_id": sid_biz,
        "settlement_date": "2026-07-10",
        "period_from": "2026-07-01",
        "period_to": "2026-07-09",
        "gross_sales": 5000000,
        "platform_commission": 250000,
        "net_payout": 4700000,
    }
    r = client.post(f"{BASE_URL}/api/marketing/settlements", json=payload, timeout=60)
    assert r.status_code == 200, r.text[:400]
    d = r.json()["data"]
    assert d["math_verified"] is False
    assert d["net_payout_diff"] == -50000
    assert d["expected_net_payout"] == 4750000
    assert d["total_deductions"] == 250000
    STATE["id"] = d["id"]
    STATE["biz"] = sid_biz
    # verify persistence
    g = client.get(f"{BASE_URL}/api/marketing/settlements/{d['id']}", timeout=60)
    assert g.status_code == 200
    gb = g.json()
    assert gb["data"]["settlement_id"] == sid_biz
    assert gb["can"]["journal"] is False


def test_duplicate_settlement_rejected(client):
    payload = {
        "account_id": ACCOUNT_ID,
        "platform": "shopee",
        "settlement_id": STATE["biz"],
        "settlement_date": "2026-07-10",
        "gross_sales": 1,
        "net_payout": 1,
    }
    r = client.post(f"{BASE_URL}/api/marketing/settlements", json=payload, timeout=60)
    assert r.status_code == 409, f"expected 409 got {r.status_code} {r.text[:200]}"


def test_journal_rejected_when_unbalanced(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}/journal", timeout=60)
    assert r.status_code == 400, r.text[:300]
    assert "belum seimbang" in r.json().get("detail", "").lower()


# ── PUT to balance ──────────────────────────────────────────────────
def test_update_to_balanced(client):
    payload = {
        "account_id": ACCOUNT_ID,
        "platform": "shopee",
        "settlement_id": STATE["biz"],
        "settlement_date": "2026-07-10",
        "period_from": "2026-07-01",
        "period_to": "2026-07-09",
        "gross_sales": 5000000,
        "refunds": 0,
        "seller_discount": 0,
        "shipping_subsidy": 0,
        "platform_commission": 250000,
        "platform_service_fee": 0,
        "affiliate_commission": 0,
        "ads_deduction": 0,
        "other_deductions": 50000,
        "other_deductions_note": "QA: biaya admin tak dikenal",
        "adjustments": 0,
        "net_payout": 4700000,
        "notes": "QA test",
    }
    r = client.put(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}", json=payload, timeout=60)
    assert r.status_code == 200, r.text[:400]
    d = r.json()["data"]
    assert d["math_verified"] is True
    assert d["net_payout_diff"] == 0
    g = client.get(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}", timeout=60).json()
    assert g["data"]["math_verified"] is True
    assert g["data"]["other_deductions"] == 50000
    assert g["can"]["journal"] is True


# ── JOURNAL + POST ──────────────────────────────────────────────────
def test_create_journal(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}/journal", timeout=60)
    assert r.status_code == 200, r.text[:400]
    b = r.json()
    assert b["ok"] is True
    assert b["je_number"]
    assert b["je_status"] == "draft"
    assert b["coa_used"]["cash"] == "1-131"
    assert b["coa_used"]["revenue"] == "4-111"
    STATE["je_number"] = b["je_number"]


def test_journal_idempotent(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}/journal", timeout=60)
    assert r.status_code == 200, r.text[:300]
    b = r.json()
    assert b.get("already") is True
    assert b["je_number"] == STATE["je_number"]


def test_edit_blocked_when_journaled(client):
    payload = {
        "account_id": ACCOUNT_ID, "platform": "shopee",
        "settlement_id": STATE["biz"], "settlement_date": "2026-07-10",
        "gross_sales": 1, "net_payout": 1,
    }
    r = client.put(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}", json=payload, timeout=60)
    assert r.status_code == 400, f"expected 400 got {r.status_code}"


def test_post_journal(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}/post", timeout=60)
    assert r.status_code == 200, r.text[:400]
    b = r.json()
    assert b["je_status"] == "posted"
    g = client.get(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}", timeout=60).json()
    assert g["data"]["je_status"] == "posted"
    assert g["data"]["je_number"] == STATE["je_number"]
    assert g["can"]["edit"] is False


def test_post_journal_idempotent(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}/post", timeout=60)
    assert r.status_code == 200, r.text[:300]
    assert r.json().get("already") is True


# ── RECONCILE ───────────────────────────────────────────────────────
def test_reconcile_by_settlement_id(client):
    r = client.get(f"{BASE_URL}/api/marketing/settlements/reconcile",
                   params={"settlement_id": STATE["biz"]}, timeout=60)
    assert r.status_code == 200, r.text[:400]
    b = r.json()
    assert b["ok"] is True
    assert b["period"]["from_settlement"] == STATE["biz"]
    assert b["focus"]["settlement_id"] == STATE["biz"]
    assert b["settlement"]["count"] == 1
    assert b["settlement"]["gross_sales"] == 5000000
    assert isinstance(b["gap"]["named"], list) and b["gap"]["named"]
    assert all("name" in n and "action" in n for n in b["gap"]["named"])
    assert "marketing" in b and "revenue_gross" in b["marketing"]


def test_reconcile_unknown_settlement_404(client):
    r = client.get(f"{BASE_URL}/api/marketing/settlements/reconcile",
                   params={"settlement_id": "STL-DOES-NOT-EXIST"}, timeout=60)
    assert r.status_code == 404


def test_coa_map(client):
    r = client.get(f"{BASE_URL}/api/marketing/settlements/coa-map", timeout=60)
    assert r.status_code == 200, r.text[:300]
    b = r.json()
    assert b["ok"] is True and isinstance(b["coa"], list)


# ── DELETE rules ────────────────────────────────────────────────────
def test_delete_journaled_rejected(client):
    r = client.delete(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}", timeout=60)
    assert r.status_code == 400, f"expected 400 got {r.status_code} {r.text[:200]}"
    assert client.get(f"{BASE_URL}/api/marketing/settlements/{STATE['id']}",
                      timeout=60).status_code == 200


def test_delete_without_journal_succeeds(client):
    biz = f"STL-QA-DEL-{int(time.time())}"
    r = client.post(f"{BASE_URL}/api/marketing/settlements", json={
        "account_id": ACCOUNT_ID, "platform": "shopee", "settlement_id": biz,
        "settlement_date": "2026-07-11", "gross_sales": 100000, "net_payout": 100000,
    }, timeout=60)
    assert r.status_code == 200, r.text[:300]
    new_id = r.json()["data"]["id"]
    d = client.delete(f"{BASE_URL}/api/marketing/settlements/{new_id}", timeout=60)
    assert d.status_code == 200, d.text[:300]
    assert client.get(f"{BASE_URL}/api/marketing/settlements/{new_id}",
                      timeout=60).status_code == 404


# ── Auth / validation guards ────────────────────────────────────────
def test_unauthenticated_list_rejected():
    r = requests.get(f"{BASE_URL}/api/marketing/settlements", timeout=60)
    assert r.status_code in (401, 403), r.status_code


def test_invalid_body_rejected(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements", json={
        "account_id": ACCOUNT_ID, "platform": "shopee", "settlement_id": "",
        "settlement_date": "2026-07-11", "gross_sales": -5,
    }, timeout=60)
    assert r.status_code == 422, r.status_code


def test_unknown_account_rejected(client):
    r = client.post(f"{BASE_URL}/api/marketing/settlements", json={
        "account_id": "nope-not-real", "platform": "shopee",
        "settlement_id": f"STL-QA-BAD-{int(time.time())}",
        "settlement_date": "2026-07-11", "gross_sales": 1, "net_payout": 1,
    }, timeout=60)
    assert r.status_code in (400, 404), f"got {r.status_code} {r.text[:200]}"


def test_get_unknown_settlement_404(client):
    r = client.get(f"{BASE_URL}/api/marketing/settlements/does-not-exist", timeout=60)
    assert r.status_code == 404
