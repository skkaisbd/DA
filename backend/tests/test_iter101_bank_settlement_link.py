"""Iteration 101 — Tautan Mutasi Bank ↔ Pencairan Marketplace (F9).

Modules under test:
  routes/dewi_bank_reconciliation.py  → settlement-candidates, link-settlement, unmatch
  routes/marketing_settlements.py     → list summary bank_linked/unlinked, PUT/DELETE guards
"""
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

SID = "a6f8da0f-df8d-4318-b079-4251a402b42f"
T1 = "f72a28ff-c891-4c69-978c-caa3fa017d78"   # 2026-08-16 debit 8.500.000 (linked STL-TEST-001)
T2 = "2c435066-f92e-4354-924a-64c7d2cec279"   # 2026-08-17 debit 5.900.000 (unmatched)
T3 = "6844f1d6-ae1c-4122-9e7d-9185d25e48a9"   # 2026-08-18 credit 8.500.000
STL1_DOC = "49f6a7ca-2b1b-42a7-89b1-e782afee2215"   # STL-TEST-001
ACC_TIKTOK = "8a098933-42aa-497c-8140-7b2852d81268"

RECON = f"{BASE_URL}/api/finance/bank-recon/sessions/{SID}"
STL = f"{BASE_URL}/api/marketing/settlements"


@pytest.fixture(scope="session")
def H():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"no token: {r.text[:300]}")
    return {"Authorization": f"Bearer {tok}"}


def _txns(H):
    r = requests.get(f"{RECON}/transactions", headers=H, timeout=60)
    assert r.status_code == 200, r.text[:300]
    return {t["id"]: t for t in r.json()["items"]}


# ── 1. Pre-existing linked state ───────────────────────────────────────────
class TestExistingLinkState:
    def test_t1_matched_as_settlement(self, H):
        items = _txns(H)
        assert set([T1, T2, T3]).issubset(items.keys()), list(items.keys())
        t1 = items[T1]
        assert t1["is_matched"] is True
        assert t1.get("match_type") == "settlement"
        assert "STL-TEST-001" in (t1.get("match_ref") or ""), t1.get("match_ref")
        assert items[T2]["is_matched"] is False
        assert items[T3]["type"] == "credit"

    def test_settlement_doc_has_bank_fields(self, H):
        r = requests.get(f"{STL}/{STL1_DOC}", headers=H, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json().get("data") or r.json()
        assert d["bank_txn_id"] == T1
        assert d["bank_txn_date"] == "2026-08-16"
        assert d["bank_session_id"] == SID

    def test_list_summary_bank_counts(self, H):
        r = requests.get(STL, headers=H, timeout=60)
        assert r.status_code == 200, r.text[:300]
        s = r.json()["summary"]
        assert s["bank_linked_count"] == 1, s
        assert s["bank_unlinked_count"] == 3, s


# ── 2. Candidates endpoint ────────────────────────────────────────────────
class TestCandidates:
    def test_candidates_for_t2(self, H):
        r = requests.get(f"{RECON}/transactions/{T2}/settlement-candidates", headers=H, timeout=60)
        assert r.status_code == 200, r.text[:300]
        j = r.json()
        assert j["ok"] is True
        items = j["items"]
        assert items, "no candidates"
        for it in items:
            for k in ("settlement_id", "account_name", "net_payout", "amount_diff",
                      "amount_match", "days_apart", "linked_here"):
                assert k in it, f"missing {k} in {it}"
        assert "STL-TEST-001" not in [i["settlement_id"] for i in items]
        assert j["exact_count"] == 0, items
        keys = [(not i["amount_match"], i["days_apart"] if i["days_apart"] is not None else 9999,
                 abs(i["amount_diff"])) for i in items]
        assert keys == sorted(keys), keys

    def test_candidates_for_t1_includes_linked_here(self, H):
        r = requests.get(f"{RECON}/transactions/{T1}/settlement-candidates", headers=H, timeout=60)
        assert r.status_code == 200, r.text[:300]
        items = r.json()["items"]
        mine = [i for i in items if i["settlement_id"] == "STL-TEST-001"]
        assert mine, [i["settlement_id"] for i in items]
        assert mine[0]["linked_here"] is True
        assert mine[0]["amount_match"] is True

    def test_candidates_unknown_txn_404(self, H):
        r = requests.get(f"{RECON}/transactions/nope-xyz/settlement-candidates", headers=H, timeout=60)
        assert r.status_code == 404, r.status_code


# ── 3. link-settlement negative paths ─────────────────────────────────────
class TestLinkGuards:
    @pytest.fixture(scope="class")
    def stm_doc_id(self, H):
        r = requests.get(STL, headers=H, params={"search": "STM-2026"}, timeout=60)
        assert r.status_code == 200, r.text[:300]
        rows = r.json().get("data") or r.json().get("items") or []
        m = [x for x in rows if x.get("settlement_id", "").startswith("STM-2026-08-16")]
        assert m, rows
        return m[0]["id"]

    def test_amount_mismatch_400(self, H, stm_doc_id):
        r = requests.post(f"{RECON}/link-settlement", headers=H,
                          json={"txn_id": T2, "settlement_doc_id": stm_doc_id}, timeout=60)
        assert r.status_code == 400, r.text[:300]
        msg = r.json().get("detail", "")
        assert "Nominal berbeda" in msg, msg
        assert "selisih Rp 20.000" in msg, msg

    def test_credit_txn_400(self, H, stm_doc_id):
        r = requests.post(f"{RECON}/link-settlement", headers=H,
                          json={"txn_id": T3, "settlement_doc_id": stm_doc_id}, timeout=60)
        assert r.status_code == 400, r.text[:300]
        assert "uang MASUK" in r.json().get("detail", ""), r.text[:300]

    def test_already_matched_txn_409(self, H, stm_doc_id):
        r = requests.post(f"{RECON}/link-settlement", headers=H,
                          json={"txn_id": T1, "settlement_doc_id": stm_doc_id}, timeout=60)
        assert r.status_code == 409, r.text[:300]

    def test_unknown_txn_404(self, H, stm_doc_id):
        r = requests.post(f"{RECON}/link-settlement", headers=H,
                          json={"txn_id": "no-such-txn", "settlement_doc_id": stm_doc_id}, timeout=60)
        assert r.status_code == 404, r.status_code

    def test_unknown_settlement_404(self, H):
        r = requests.post(f"{RECON}/link-settlement", headers=H,
                          json={"txn_id": T2, "settlement_doc_id": "no-such-settlement"}, timeout=60)
        assert r.status_code == 404, r.status_code


# ── 4. Guards on the currently-linked STL-TEST-001 ────────────────────────
class TestLinkedSettlementLocks:
    def test_put_net_payout_blocked(self, H):
        cur = requests.get(f"{STL}/{STL1_DOC}", headers=H, timeout=60).json()
        d = cur.get("data") or cur
        body = {k: d.get(k) for k in (
            "account_id", "platform", "settlement_id", "settlement_date", "period_from",
            "period_to", "gross_sales", "refunds", "seller_discount", "shipping_subsidy",
            "platform_commission", "platform_service_fee", "affiliate_commission",
            "ads_deduction", "other_deductions", "adjustments", "net_payout", "notes",
            "other_deductions_note")}
        body["net_payout"] = 8400000
        r = requests.put(f"{STL}/{STL1_DOC}", headers=H, json=body, timeout=60)
        assert r.status_code == 400, r.text[:400]
        msg = r.json().get("detail", "")
        print(f"PUT guard message: {msg}")
        assert ("TERTAUT ke mutasi bank" in msg) or ("jurnal" in msg), msg

    def test_delete_blocked(self, H):
        r = requests.delete(f"{STL}/{STL1_DOC}", headers=H, timeout=60)
        assert r.status_code == 400, r.text[:400]
        print(f"DELETE guard message: {r.json().get('detail','')}")


# ── 5. Happy path: fresh settlement → link → guards → unmatch → delete ────
class TestHappyPath:
    @pytest.fixture(scope="class")
    def fresh(self, H):
        sid_code = f"STL-BANK-{int(time.time())}"
        payload = {
            "account_id": ACC_TIKTOK, "platform": "tiktokshop",
            "settlement_id": sid_code, "settlement_date": "2026-08-17",
            "gross_sales": 6000000, "platform_commission": 100000, "net_payout": 5900000,
        }
        r = requests.post(STL, headers=H, json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        doc = r.json().get("data") or r.json()
        assert doc["math_verified"] is True, doc
        yield doc
        # cleanup — best effort
        requests.post(f"{RECON}/unmatch", headers=H, json={"txn_id": T2}, timeout=60)
        requests.delete(f"{STL}/{doc['id']}", headers=H, timeout=60)

    def test_link_ok(self, H, fresh):
        before = requests.get(RECON, headers=H, timeout=60).json().get("matched_count")
        r = requests.post(f"{RECON}/link-settlement", headers=H,
                          json={"txn_id": T2, "settlement_doc_id": fresh["id"]}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        j = r.json()
        assert j["ok"] is True
        assert j["match_ref"] == f"Pencairan {fresh['settlement_id']} · tiktokshop", j
        assert fresh["settlement_id"] in j.get("message", ""), j
        # settlement doc updated
        d = requests.get(f"{STL}/{fresh['id']}", headers=H, timeout=60).json()
        d = d.get("data") or d
        assert d["bank_txn_id"] == T2
        assert d["bank_txn_date"] == "2026-08-17"
        # txn updated
        assert _txns(H)[T2]["is_matched"] is True
        after = requests.get(RECON, headers=H, timeout=60).json().get("matched_count")
        assert after == (before or 0) + 1, (before, after)

    def test_put_and_delete_blocked_while_linked(self, H, fresh):
        body = {k: fresh.get(k) for k in (
            "account_id", "platform", "settlement_id", "settlement_date",
            "gross_sales", "platform_commission", "net_payout")}
        body["net_payout"] = 5800000
        r = requests.put(f"{STL}/{fresh['id']}", headers=H, json=body, timeout=60)
        assert r.status_code == 400, r.text[:400]
        assert "TERTAUT" in r.json().get("detail", ""), r.text[:400]
        r2 = requests.delete(f"{STL}/{fresh['id']}", headers=H, timeout=60)
        assert r2.status_code == 400, r2.text[:400]
        assert "tertaut ke mutasi bank" in r2.json().get("detail", ""), r2.text[:400]

    def test_unmatch_releases_and_delete_succeeds(self, H, fresh):
        r = requests.post(f"{RECON}/unmatch", headers=H, json={"txn_id": T2}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = requests.get(f"{STL}/{fresh['id']}", headers=H, timeout=60).json()
        d = d.get("data") or d
        assert d.get("bank_txn_id") is None, d.get("bank_txn_id")
        assert _txns(H)[T2]["is_matched"] is False
        r2 = requests.delete(f"{STL}/{fresh['id']}", headers=H, timeout=60)
        assert r2.status_code in (200, 204), r2.text[:400]
        assert requests.get(f"{STL}/{fresh['id']}", headers=H, timeout=60).status_code == 404


# ── 6. Final state assertion: T1 must remain linked to STL-TEST-001 ───────
def test_zz_final_state(H):
    t1 = _txns(H)[T1]
    assert t1["is_matched"] is True and t1.get("match_type") == "settlement", t1
