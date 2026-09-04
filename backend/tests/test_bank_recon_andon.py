"""
Tests for Bank Reconciliation (Finance) + Andon WebSocket (Production).
"""
import os
import json
import asyncio
import uuid
import pytest
import requests
import websockets

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
WS_BASE = BASE_URL.replace("https://", "wss://").replace("http://", "ws://")

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"Login failed: {r.status_code} {r.text[:200]}")
    data = r.json()
    tok = data.get("token") or data.get("access_token")
    assert tok, f"No token in login response: {data}"
    return tok


@pytest.fixture(scope="module")
def client(token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    return s


# ═══════════════════════════════════════════════════════════════════
# BANK RECONCILIATION
# ═══════════════════════════════════════════════════════════════════
class TestBankReconSummary:
    def test_summary_shape(self, client):
        r = client.get(f"{BASE_URL}/api/finance/bank-recon/summary", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ["total_sessions", "draft", "in_progress", "approved", "total_unmatched", "recent"]:
            assert k in d, f"missing key {k}"
        assert isinstance(d["recent"], list)


class TestBankReconSessions:
    @pytest.fixture(scope="class")
    def session_info(self, client):
        period = "2026-05"
        account_no = f"TEST{uuid.uuid4().hex[:8]}"
        payload = {
            "period": period,
            "bank_name": "BCA TEST",
            "account_no": account_no,
            "account_name": "TEST_CV Dewi",
            "opening_balance": 0,
            "closing_balance": 1000000,
            "notes": "TEST session",
        }
        r = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["period"] == period
        assert d["account_no"] == account_no
        assert d["status"] == "draft"
        assert "id" in d
        yield d
        # Cleanup
        try:
            client.delete(f"{BASE_URL}/api/finance/bank-recon/sessions/{d['id']}", timeout=15)
        except Exception:
            pass

    def test_list_sessions_pagination_shape(self, client):
        r = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions?skip=0&limit=5", timeout=15)
        assert r.status_code == 200
        d = r.json()
        for k in ["total", "skip", "limit", "has_more", "items"]:
            assert k in d, f"missing pagination key {k}"
        assert d["skip"] == 0
        assert d["limit"] == 5
        assert isinstance(d["items"], list)

    def test_invalid_period_format(self, client):
        r = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions", json={"period": "2026-5", "bank_name": "BCA"}, timeout=15)
        assert r.status_code == 400

    def test_missing_bank_name(self, client):
        r = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions", json={"period": "2026-05", "bank_name": ""}, timeout=15)
        assert r.status_code == 400

    def test_duplicate_session_conflict(self, client, session_info):
        # Re-submit same period+account -> 409
        payload = {
            "period": session_info["period"],
            "bank_name": "BCA TEST",
            "account_no": session_info["account_no"],
        }
        r = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions", json=payload, timeout=15)
        assert r.status_code == 409, r.text

    def test_get_session_with_gl(self, client, session_info):
        r = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{session_info['id']}", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["id"] == session_info["id"]
        assert "gl_entries" in d
        assert isinstance(d["gl_entries"], list)

    def test_add_txn_and_recalc(self, client, session_info):
        sid = session_info["id"]
        txn = {"txn_date": "2026-05-15", "description": "TEST txn", "amount": 150000, "type": "debit"}
        r = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions", json=txn, timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["amount"] == 150000
        assert d["is_matched"] is False
        txn_id = d["id"]

        # verify session recalculated
        gs = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}", timeout=15).json()
        assert gs["total_bank_txns"] >= 1
        assert gs["unmatched_count"] >= 1

        # list transactions pagination shape + matched filter
        lr = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions?matched=false&skip=0&limit=10", timeout=15)
        assert lr.status_code == 200
        ld = lr.json()
        for k in ["total", "skip", "limit", "has_more", "items"]:
            assert k in ld
        assert any(t["id"] == txn_id for t in ld["items"])

    def test_import_bulk(self, client, session_info):
        sid = session_info["id"]
        payload = {
            "transactions": [
                {"txn_date": "2026-05-10", "description": "Bulk 1", "amount": 50000, "type": "debit"},
                {"txn_date": "2026-05-11", "description": "Bulk 2", "amount": 25000, "type": "credit"},
            ]
        }
        r = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/import-bulk", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        assert r.json()["imported"] == 2

    def test_match_unmatch_and_approve_blocked(self, client, session_info):
        sid = session_info["id"]
        # Get one unmatched txn
        lr = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/transactions?matched=false&limit=50", timeout=15).json()
        assert len(lr["items"]) > 0
        txn_id = lr["items"][0]["id"]

        # Match
        mr = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/match",
                         json={"txn_id": txn_id, "gl_entry_id": "fake-gl-001", "gl_ref": "TEST-REF"}, timeout=15)
        assert mr.status_code == 200

        gs = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}", timeout=15).json()
        assert gs["matched_count"] >= 1

        # Approve should fail while unmatched > 0
        if gs["unmatched_count"] > 0:
            ar = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/approve", timeout=15)
            assert ar.status_code == 400, ar.text

        # Unmatch
        ur = client.post(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}/unmatch", json={"txn_id": txn_id}, timeout=15)
        assert ur.status_code == 200
        gs2 = client.get(f"{BASE_URL}/api/finance/bank-recon/sessions/{sid}", timeout=15).json()
        assert gs2["matched_count"] == gs["matched_count"] - 1

    def test_gl_entries_endpoint(self, client):
        r = client.get(f"{BASE_URL}/api/finance/bank-recon/gl-entries?period=2026-05", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert d["period"] == "2026-05"
        assert "items" in d
        # invalid period
        r2 = client.get(f"{BASE_URL}/api/finance/bank-recon/gl-entries?period=bad", timeout=15)
        assert r2.status_code == 400


# ═══════════════════════════════════════════════════════════════════
# ANDON WEBSOCKET
# ═══════════════════════════════════════════════════════════════════
class TestAndonWebSocket:
    def test_ws_no_token_rejected(self):
        async def run():
            url = f"{WS_BASE}/api/rahaza/andon/ws"
            try:
                async with websockets.connect(url, open_timeout=10) as ws:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=3)
                    except Exception:
                        msg = None
                    return "connected_no_close", msg
            except Exception as e:
                return "closed", str(e)
        result, _ = asyncio.get_event_loop().run_until_complete(run()) if False else asyncio.run(run())
        assert result == "closed", f"Should have been rejected without token, got {result}"

    def test_ws_invalid_token_rejected(self):
        async def run():
            url = f"{WS_BASE}/api/rahaza/andon/ws?token=invalidtoken123"
            try:
                async with websockets.connect(url, open_timeout=10) as ws:
                    try:
                        await asyncio.wait_for(ws.recv(), timeout=3)
                        return "received"
                    except Exception:
                        return "no_msg"
            except Exception:
                return "closed"
        result = asyncio.run(run())
        assert result == "closed", f"Invalid token should be rejected, got {result}"

    def test_ws_valid_token_connect_and_broadcast(self, token, client):
        """Connect with valid token, receive init, trigger create andon, receive broadcast."""
        async def run():
            url = f"{WS_BASE}/api/rahaza/andon/ws?token={token}"
            async with websockets.connect(url, open_timeout=15) as ws:
                init_raw = await asyncio.wait_for(ws.recv(), timeout=10)
                init_msg = json.loads(init_raw)
                assert init_msg.get("type") == "init", f"Expected init, got {init_msg}"
                assert "data" in init_msg

                # Trigger event via REST API in a thread (requests is sync)
                loop = asyncio.get_event_loop()
                def _create():
                    return client.post(f"{BASE_URL}/api/rahaza/andon",
                                       json={"type": "help", "message": "TEST WS broadcast"}, timeout=15)
                resp = await loop.run_in_executor(None, _create)
                assert resp.status_code == 200, resp.text
                event_id = resp.json()["id"]

                # Read messages, skip pings until andon_update arrives
                got_update = False
                deadline = asyncio.get_event_loop().time() + 15
                while asyncio.get_event_loop().time() < deadline:
                    try:
                        raw = await asyncio.wait_for(ws.recv(), timeout=5)
                        m = json.loads(raw)
                        if m.get("type") == "andon_update" and m.get("data", {}).get("event_id") == event_id:
                            got_update = True
                            break
                    except asyncio.TimeoutError:
                        continue
                assert got_update, "Did not receive andon_update broadcast"

                # Cancel this event (and receive broadcast)
                def _cancel():
                    return client.post(f"{BASE_URL}/api/rahaza/andon/{event_id}/cancel", timeout=15)
                cresp = await loop.run_in_executor(None, _cancel)
                assert cresp.status_code == 200
                return event_id

        event_id = asyncio.run(run())
        assert event_id
