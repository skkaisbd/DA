"""Sesi #34 — backend tests: biaya jahit SPK, budget period, impor pintar,
portal kreator, insentif KOL, livehost gaji bulanan, RnD product viewer.
"""
import os
import re
import uuid
from datetime import date
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

SAMPLES = Path("/app/samples/marketplace_2026")
SHOPEE_ACCOUNT_ID = "e53693e9-0732-4c07-b246-f11ef438571f"


def _rows(body):
    """Normalize list/dict-wrapped API responses to a list."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ("data", "items", "rows", "products", "hosts", "creators", "requests"):
            v = body.get(k)
            if isinstance(v, list):
                return v
    return []


def _num(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0



# ── fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def admin_creds():
    p = Path("/app/memory/test_credentials.md")
    if not p.exists():
        pytest.skip("missing test_credentials.md")
    txt = p.read_text(encoding="utf-8")
    m = re.search(r"`(admin@garment\.com)`\s*\|\s*`([^`]+)`", txt)
    if not m:
        pytest.skip("admin creds not found")
    return {"email": m.group(1), "password": m.group(2)}


@pytest.fixture(scope="session")
def client(admin_creds):
    s = requests.Session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=admin_creds, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


# ── 1. BIAYA JAHIT SPK ──────────────────────────────────────────────────────
class TestSewingCost:
    def test_list_pos(self, client):
        r = client.get(f"{BASE_URL}/api/production/sewing-cost/pos", timeout=90)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["ok"] is True
        assert isinstance(d["data"], list) and len(d["data"]) > 0, "no SPK returned"
        row = d["data"][0]
        for k in ("po_id", "po_number", "qty_total", "sewing_total", "complete"):
            assert k in row

    def test_po_detail_and_put_rate(self, client):
        lst = client.get(f"{BASE_URL}/api/production/sewing-cost/pos?limit=50", timeout=90).json()["data"]
        target = next((p for p in lst if p["item_count"] > 0), None)
        assert target, "no SPK with items"
        po_id = target["po_id"]
        det = client.get(f"{BASE_URL}/api/production/sewing-cost/pos/{po_id}", timeout=90)
        assert det.status_code == 200, det.text[:300]
        d = det.json()
        items = d["items"]
        assert len(items) > 0
        it = items[0]
        assert "suggestion" in it and "hpp_preview" in it
        old_rate = it["rate_per_pcs"]
        hpp_before = it["hpp_preview"]["unit_cost"]
        missing_before = d["totals"]["items_missing_rate"]

        new_rate = 7500.0
        put = client.put(f"{BASE_URL}/api/production/sewing-cost/pos/{po_id}",
                         json={"items": [{"po_item_id": it["po_item_id"], "rate_per_pcs": new_rate}],
                               "apply_same_sku": True, "notes": "TEST_session34"}, timeout=90)
        assert put.status_code == 200, put.text[:300]
        assert put.json()["updated"] == 1

        d2 = client.get(f"{BASE_URL}/api/production/sewing-cost/pos/{po_id}", timeout=90).json()
        it2 = next(x for x in d2["items"] if x["po_item_id"] == it["po_item_id"])
        assert it2["rate_per_pcs"] == new_rate, "rate not persisted"
        assert it2["line_total"] == pytest.approx(new_rate * it2["qty"], rel=1e-3), "line_total != rate*qty"
        assert it2["hpp_preview"]["sewing_cost"] == pytest.approx(new_rate, rel=1e-3)
        assert it2["hpp_preview"]["unit_cost"] > hpp_before or old_rate >= new_rate, \
            "HPP/pcs did not increase with sewing rate"
        assert d2["totals"]["items_missing_rate"] <= missing_before
        # restore
        client.put(f"{BASE_URL}/api/production/sewing-cost/pos/{po_id}",
                   json={"items": [{"po_item_id": it["po_item_id"], "rate_per_pcs": old_rate}],
                         "apply_same_sku": False}, timeout=90)

    def test_po_detail_404(self, client):
        r = client.get(f"{BASE_URL}/api/production/sewing-cost/pos/NOPE-xyz", timeout=60)
        assert r.status_code == 404


# ── 2. BUDGET PERIOD SETTINGS ───────────────────────────────────────────────
class TestBudgetPeriod:
    def test_weekly_default_and_switch(self, client):
        r = client.get(f"{BASE_URL}/api/marketing/budget/period-settings", timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json().get("settings") or r.json()
        assert d.get("period_mode") == "weekly", f"expected weekly, got {d.get('period_mode')}"
        assert d.get("period_days") == 7
        cr = d.get("current_range") or {}
        assert cr.get("start") and cr.get("end")
        assert d.get("current_period")

        up = client.put(f"{BASE_URL}/api/marketing/budget/period-settings",
                        json={"period_mode": "monthly"}, timeout=60)
        assert up.status_code == 200, up.text[:300]
        r2 = client.get(f"{BASE_URL}/api/marketing/budget/period-settings", timeout=60).json()
        d2 = r2.get("settings") or r2
        assert d2.get("period_mode") == "monthly"
        # revert
        client.put(f"{BASE_URL}/api/marketing/budget/period-settings",
                   json={"period_mode": "weekly"}, timeout=60)
        r3 = client.get(f"{BASE_URL}/api/marketing/budget/period-settings", timeout=60).json()
        d3 = r3.get("settings") or r3
        assert d3.get("period_mode") == "weekly"


class TestBudgetSummaryWeekly:
    """Regresi sesi #34: layar Budget mode 7 hari memakai period=YYYY-MM-DD."""

    def test_summary_accepts_weekly_period(self, client):
        accs = client.get(f"{BASE_URL}/api/marketing/budget/period-settings", timeout=60).json()
        settings = accs.get("settings") or accs
        period = (settings.get("current_range") or {}).get("start") or settings.get("current_period")
        acc_id = SHOPEE_ACCOUNT_ID
        r = client.get(f"{BASE_URL}/api/marketing/budget/summary",
                       params={"account_id": acc_id, "period": period}, timeout=90)
        assert r.status_code == 200, (
            f"weekly period '{period}' breaks /api/marketing/budget/summary: "
            f"{r.status_code} {r.text[:200]}")

    def test_summary_monthly_period_ok(self, client):
        r = client.get(f"{BASE_URL}/api/marketing/budget/summary",
                       params={"account_id": SHOPEE_ACCOUNT_ID, "period": "2026-08"}, timeout=90)
        assert r.status_code == 200, r.text[:200]


# ── 3. IMPOR PINTAR — DETECT ────────────────────────────────────────────────
DETECT_CASES = [
    ("order_pesanan_shopee.xlsx", "shopee", "marketplace_orders"),
    ("pesanan_tiktok.xlsx", "tiktok", "marketplace_orders"),
    ("retur_refund_tiktok.xlsx", "tiktok", "returns"),
    ("ads_tiktok.xlsx", "tiktok", "ads"),
    ("ads_shopee.csv", "shopee", "shopee_ads_cpc"),
]


class TestSmartDetect:
    @pytest.mark.parametrize("fname,platform,stype", DETECT_CASES)
    def test_detect(self, client, fname, platform, stype):
        path = SAMPLES / fname
        assert path.exists(), f"missing sample {path}"
        with path.open("rb") as fh:
            r = client.post(f"{BASE_URL}/api/marketing/data-import/detect",
                            files={"file": (fname, fh)}, timeout=180)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        got_plat = (d.get("platform") or {}).get("platform")
        best = (d.get("best") or {}).get("source_type")
        assert got_plat == platform, f"{fname}: platform {got_plat} != {platform}"
        assert best == stype, f"{fname}: best {best} != {stype} (ranking={[x.get('source_type') for x in (d.get('ranking') or [])][:4]})"
        assert len(d.get("raw_preview") or []) > 0, "raw_preview empty"
        if platform:
            assert isinstance(d.get("matching_accounts"), list)

    def test_detect_shopee_matching_accounts(self, client):
        path = SAMPLES / "order_pesanan_shopee.xlsx"
        with path.open("rb") as fh:
            d = client.post(f"{BASE_URL}/api/marketing/data-import/detect",
                            files={"file": (path.name, fh)}, timeout=180).json()
        assert len(d["matching_accounts"]) > 0, "no matching shopee accounts"
        assert all("shopee" in str(a.get("platform", "")).lower() for a in d["matching_accounts"])
        assert len(d["raw_preview"]) == 10


# ── 4. IMPOR PINTAR — TYPE MISMATCH ─────────────────────────────────────────
class TestTypeMismatch:
    def test_wrong_source_type_warns(self, client):
        path = SAMPLES / "order_pesanan_shopee.xlsx"
        with path.open("rb") as fh:
            r = client.post(f"{BASE_URL}/api/marketing/data-import/upload",
                            files={"file": (path.name, fh)},
                            data={"source_type": "sales_daily", "account_id": SHOPEE_ACCOUNT_ID},
                            timeout=240)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        sess = d.get("session") or d
        det = sess.get("detection") or {}
        assert det, "session.detection missing"
        tm = det.get("type_mismatch")
        assert tm, "type_mismatch not raised for wrong source_type"
        msg = tm if isinstance(tm, str) else str(tm)
        assert "Pesanan Marketplace" in msg, f"suggestion text missing: {msg[:200]}"
        assert len(sess.get("raw_preview") or []) == 10, "raw_preview should have 10 rows"

    def test_header_only_file_rejected(self, client):
        path = SAMPLES / "retur_refund_shopee.xls"
        with path.open("rb") as fh:
            r = client.post(f"{BASE_URL}/api/marketing/data-import/upload",
                            files={"file": (path.name, fh)},
                            data={"source_type": "returns", "account_id": SHOPEE_ACCOUNT_ID},
                            timeout=180)
        assert r.status_code == 400, f"expected 400, got {r.status_code}: {r.text[:200]}"
        assert "baris data" in r.text


# ── 5. IMPOR REGRESI — TIKTOK ORDERS UPLOAD + COMMIT ────────────────────────
class TestImportRegression:
    def test_tiktok_orders_upload_preview_commit(self, client):
        path = SAMPLES / "pesanan_tiktok.xlsx"
        tiktok_acc = None
        with path.open("rb") as fh:
            det = client.post(f"{BASE_URL}/api/marketing/data-import/detect",
                              files={"file": (path.name, fh)}, timeout=180).json()
        if det.get("matching_accounts"):
            tiktok_acc = det["matching_accounts"][0]["id"]
        assert tiktok_acc, "no tiktok account available"
        with path.open("rb") as fh:
            up = client.post(f"{BASE_URL}/api/marketing/data-import/upload",
                             files={"file": (path.name, fh)},
                             data={"source_type": "marketplace_orders", "account_id": tiktok_acc},
                             timeout=300)
        assert up.status_code == 200, up.text[:400]
        sess = up.json().get("session") or up.json()
        sid = sess.get("session_id") or sess.get("id")
        assert sid, f"no session id: {str(sess)[:200]}"
        plan = client.get(f"{BASE_URL}/api/marketing/data-import/sessions/{sid}/plan", timeout=300)
        assert plan.status_code == 200, plan.text[:300]
        com = client.post(f"{BASE_URL}/api/marketing/data-import/sessions/{sid}/commit",
                          json={}, timeout=600)
        assert com.status_code == 200, com.text[:400]
        cd = com.json()
        assert cd.get("ok") is not False, str(cd)[:300]


# ── 6. PORTAL KREATOR ───────────────────────────────────────────────────────
class TestCreatorPortal:
    def test_login_and_catalog_no_hpp(self):
        s = requests.Session()
        r = s.post(f"{BASE_URL}/api/marketing/creator-portal/auth/login",
                   json={"email": "kre-demo-01@creator.demo", "password": "Dewi@123"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        tok = r.json().get("access_token") or r.json().get("token")
        assert tok, r.text[:300]
        s.headers.update({"Authorization": f"Bearer {tok}"})

        cat = s.get(f"{BASE_URL}/api/marketing/creator-portal/catalog", timeout=90)
        assert cat.status_code == 200, cat.text[:300]
        items = _rows(cat.json())
        assert isinstance(items, list) and len(items) > 0, "catalog empty"
        banned = ("hpp", "hpp_fifo_avg", "margin", "cost")
        leaked = set()
        for it in items:
            for k in it:
                if any(b == k.lower() or b in k.lower() for b in banned):
                    leaked.add(k)
        assert not leaked, f"HPP/margin fields leaked to creator catalog: {leaked}"
        assert any("price" in k.lower() for k in items[0]), "no selling price field"

    def test_creator_item_request(self):
        s = requests.Session()
        lg = s.post(f"{BASE_URL}/api/marketing/creator-portal/auth/login",
                    json={"email": "kre-demo-01@creator.demo", "password": "Dewi@123"},
                    timeout=60).json()
        tok = lg.get("access_token") or lg.get("token")
        s.headers.update({"Authorization": f"Bearer {tok}"})
        items = _rows(s.get(f"{BASE_URL}/api/marketing/creator-portal/catalog", timeout=90).json())
        item = items[0]
        payload = {"account_id": item.get("account_id"),
                   "catalog_item_id": item.get("id"),
                   "quantity_requested": 1,
                   "purpose": "content", "notes": "TEST_session34 request"}
        r = s.post(f"{BASE_URL}/api/marketing/creator-portal/requests", json=payload, timeout=90)
        assert r.status_code in (200, 201), f"{r.status_code}: {r.text[:300]}"
        mine = s.get(f"{BASE_URL}/api/marketing/creator-portal/my-requests", timeout=60)
        assert mine.status_code == 200
        assert len(_rows(mine.json())) > 0


# ── 7. MARKETING: BUAT KREATOR + PORTAL ACCOUNT ─────────────────────────────
class TestCreatorAdmin:
    def test_create_new_type_then_portal_account_login(self, client):
        code = f"TEST-S34-{uuid.uuid4().hex[:6].upper()}"
        payload = {"creator_code": code, "name": "TEST_S34 Kreator New",
                   "creator_type": "new", "domicile": "Bandung", "phone": "0800000000"}
        r = client.post(f"{BASE_URL}/api/marketing/kol/creators", json=payload, timeout=90)
        assert r.status_code in (200, 201), f"create new-type creator: {r.status_code} {r.text[:300]}"
        d = r.json()
        cid = (d.get("creator") or d.get("data") or d).get("id")
        assert cid
        try:
            got = client.get(f"{BASE_URL}/api/marketing/kol/creators/{cid}", timeout=60).json()
            g = got.get("creator") or got.get("data") or got
            assert g.get("creator_type") == "new"
            assert g.get("domicile") == "Bandung", f"domicile not persisted: {g.get('domicile')}"

            creds = {"login_email": f"test_s34_{uuid.uuid4().hex[:6]}@creator.demo",
                     "login_password": "Dewi@123"}
            pa = client.post(f"{BASE_URL}/api/marketing/kol/creators/{cid}/portal-account",
                             json=creds, timeout=90)
            assert pa.status_code in (200, 201), f"{pa.status_code}: {pa.text[:300]}"
            lg = requests.post(f"{BASE_URL}/api/marketing/creator-portal/auth/login",
                               json={"email": creds["login_email"],
                                     "password": creds["login_password"]}, timeout=60)
            assert lg.status_code == 200, f"login with new portal creds failed: {lg.text[:300]}"
        finally:
            client.delete(f"{BASE_URL}/api/marketing/kol/creators/{cid}", timeout=60)

    def test_creator_type_invalid_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/marketing/kol/creators",
                        json={"creator_code": f"TEST-S34-{uuid.uuid4().hex[:6].upper()}",
                              "name": "TEST_S34 bad type", "creator_type": "zzz"}, timeout=60)
        assert r.status_code in (400, 422), r.status_code

    def test_email_without_password_rejected(self, client):
        r = client.post(f"{BASE_URL}/api/marketing/kol/creators",
                        json={"creator_code": f"TEST-S34-{uuid.uuid4().hex[:6].upper()}",
                              "name": "TEST_S34 no pass", "creator_type": "kontrak",
                              "login_email": f"nopass_{uuid.uuid4().hex[:6]}@creator.demo"},
                        timeout=60)
        assert r.status_code in (400, 422), f"expected reject, got {r.status_code}"


# ── 8. INSENTIF KREATOR ─────────────────────────────────────────────────────
class TestIncentive:
    def test_incentive_flow(self, client):
        rows = _rows(client.get(f"{BASE_URL}/api/marketing/kol/creators?limit=100", timeout=90).json())
        cre = next((c for c in rows if (c.get("creator_type") or "new") != "new"), None)
        assert cre, "no non-new creator to test incentive"
        cid = cre["id"]
        cfg = {"mode": "both", "rate_per_pcs": 2000, "target_pcs": 100,
               "bonus_amount": 500000, "period_months": 3,
               "period_start": date.today().replace(day=1).isoformat()}
        r = client.put(f"{BASE_URL}/api/marketing/kol/creators/{cid}/incentive", json=cfg, timeout=90)
        assert r.status_code == 200, r.text[:300]
        base_pcs = r.json().get("pcs_sold", 0)

        today = date.today().isoformat()
        for _ in range(2):
            e = client.post(f"{BASE_URL}/api/marketing/kol/creators/{cid}/incentive/entries",
                            json={"date": today, "pcs": 60, "note": "TEST_S34"}, timeout=90)
            assert e.status_code in (200, 201), e.text[:300]
        got = client.get(f"{BASE_URL}/api/marketing/kol/creators/{cid}/incentive", timeout=90).json()
        assert got["pcs_sold"] == base_pcs + 120, f"pcs_sold={got['pcs_sold']} base={base_pcs}"
        assert got["per_pcs_amount"] == pytest.approx((base_pcs + 120) * 2000)
        assert got["target_hit"] is True
        assert got["bonus_amount"] == 500000
        assert got["total_incentive"] == pytest.approx(got["per_pcs_amount"] + 500000)

        cp = client.post(f"{BASE_URL}/api/marketing/kol/creators/{cid}/incentive/close-period", timeout=90)
        assert cp.status_code == 200, cp.text[:300]
        after = client.get(f"{BASE_URL}/api/marketing/kol/creators/{cid}/incentive", timeout=90).json()
        assert after["pcs_sold"] == 0, f"close-period did not reset counters: {after['pcs_sold']}"
        assert after["total_incentive"] == 0

    def test_overview(self, client):
        r = client.get(f"{BASE_URL}/api/marketing/kol/creators-incentive-overview", timeout=90)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(_rows(r.json()), list)


# ── 9. LIVEHOST GAJI BULANAN ────────────────────────────────────────────────
class TestLivehostMonthly:
    def test_calculate_monthly(self, client):
        r = client.post(f"{BASE_URL}/api/marketing/livehost/payment/calculate?month=2026-08", timeout=180)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d.get("pay_mode") == "monthly_salary", f"pay_mode={d.get('pay_mode')}"
        hosts = d.get("hosts") or d.get("data") or []
        assert isinstance(hosts, list)
        assert "unlinked_hosts" in d
        for h in hosts:
            assert "monthly_salary_hr" in h, f"missing monthly_salary_hr: {list(h)[:12]}"
        shifts = d.get("shifts") or []
        for s in shifts:
            assert _num(s.get("total_pay")) == 0, "per-session pay still computed"
            assert s.get("payment_status") == "monthly_salary"


# ── 10. RND PRODUCT VIEWER ──────────────────────────────────────────────────
class TestRndProductViewer:
    def test_list_and_detail(self, client):
        r = client.get(f"{BASE_URL}/api/rnd/product-viewer", timeout=180)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        rows = d.get("data") or d.get("products") or []
        assert isinstance(rows, list) and len(rows) > 0, "no RnD products"
        kpi = d.get("kpi") or d.get("summary") or {}
        assert kpi, "no KPI block in /api/rnd/product-viewer"
        mid = rows[0].get("material_id") or rows[0].get("id")
        assert mid
        det = client.get(f"{BASE_URL}/api/rnd/product-viewer/{mid}", timeout=120)
        assert det.status_code == 200, det.text[:300]
        dd = det.json()
        assert dd.get("ok") is not False
        assert "_id" not in str(dd)[:2000] or '"_id"' not in str(dd)

    def test_detail_404(self, client):
        r = client.get(f"{BASE_URL}/api/rnd/product-viewer/NOPE-xyz", timeout=60)
        assert r.status_code == 404


# ── 11. MARKETING SETTLEMENTS (read-only screen data) ───────────────────────
class TestSettlements:
    def test_list(self, client):
        r = client.get(f"{BASE_URL}/api/marketing/settlements", timeout=120)
        assert r.status_code == 200, r.text[:300]
        assert isinstance(_rows(r.json()), list)
