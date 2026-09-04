"""
test_universal_scan.py — Backend tests for Universal Multi-Entity Scan endpoints.

Tests:
  1. GET /api/scan/history — Returns recent scans (auth required)
  2. POST /api/scan/resolve — Resolve code from body JSON
  3. GET /api/scan/{code} — Resolve code from URL path
  4. QR JSON payload parsing
  5. Scan history logging (found + not-found)
"""

import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    raise RuntimeError("REACT_APP_BACKEND_URL is not set")

PO_CODE = "PO-20260527-001"  # Known PO in DB
UNKNOWN_CODE = "UNKNOWN-CODE-99999999"


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def token():
    """Login and obtain auth token."""
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "admin@garment.com", "password": "Admin@123"},
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    t = r.json().get("token")
    assert t, "Token not returned"
    return t


@pytest.fixture(scope="module")
def headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─── 1. Auth guard tests ───────────────────────────────────────────────────────

class TestAuthGuard:
    """Endpoints should return 401 or 403 without auth."""

    def test_history_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/scan/history")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print("✅ GET /api/scan/history requires auth")

    def test_resolve_requires_auth(self):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE})
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print("✅ POST /api/scan/resolve requires auth")

    def test_get_code_requires_auth(self):
        r = requests.get(f"{BASE_URL}/api/scan/{PO_CODE}")
        assert r.status_code in (401, 403), f"Expected 401/403, got {r.status_code}"
        print("✅ GET /api/scan/{code} requires auth")


# ─── 2. POST /api/scan/resolve — found PO ─────────────────────────────────────

class TestResolvePO:
    """POST /api/scan/resolve with valid PO code."""

    def test_resolve_known_po_status_200(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        print("✅ POST /api/scan/resolve 200 for known PO")

    def test_resolve_known_po_found_true(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        assert data.get("found") is True, f"Expected found=True, got: {data}"
        print(f"✅ found=True for PO code {PO_CODE}")

    def test_resolve_known_po_entity_type(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        assert data.get("entity_type") == "purchase_order", f"Expected entity_type=purchase_order, got: {data.get('entity_type')}"
        print("✅ entity_type=purchase_order")

    def test_resolve_known_po_entity_number(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        assert data.get("entity_number") == PO_CODE, f"entity_number mismatch: {data.get('entity_number')}"
        print(f"✅ entity_number={data.get('entity_number')}")

    def test_resolve_known_po_display_name(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        assert data.get("display_name"), f"display_name is empty: {data}"
        assert "PO ke" in data.get("display_name", ""), f"display_name format wrong: {data.get('display_name')}"
        print(f"✅ display_name={data.get('display_name')}")

    def test_resolve_known_po_has_meta(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        meta = data.get("meta", {})
        assert isinstance(meta, dict), f"meta should be dict, got: {type(meta)}"
        assert len(meta) > 0, f"meta is empty: {data}"
        assert "Vendor" in meta, f"meta missing 'Vendor': {meta}"
        print(f"✅ meta={meta}")

    def test_resolve_known_po_has_quick_actions(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        qa = data.get("quick_actions", [])
        assert isinstance(qa, list) and len(qa) > 0, f"quick_actions missing or empty: {data}"
        assert any(a.get("id") == "view_po" for a in qa), f"No 'view_po' quick action: {qa}"
        print("✅ quick_actions has view_po")

    def test_resolve_known_po_has_scan_id(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)
        data = r.json()
        assert data.get("scan_id"), f"scan_id missing: {data}"
        print(f"✅ scan_id={data.get('scan_id')}")


# ─── 3. POST /api/scan/resolve — unknown code ────────────────────────────────

class TestResolveUnknown:
    """POST /api/scan/resolve with unknown code returns found=false."""

    def test_unknown_code_status_200(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": UNKNOWN_CODE}, headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        print("✅ POST /api/scan/resolve 200 for unknown code")

    def test_unknown_code_found_false(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": UNKNOWN_CODE}, headers=headers)
        data = r.json()
        assert data.get("found") is False, f"Expected found=False: {data}"
        print("✅ found=False for unknown code")

    def test_unknown_code_returns_raw_code(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": UNKNOWN_CODE}, headers=headers)
        data = r.json()
        assert data.get("raw_code") == UNKNOWN_CODE, f"raw_code mismatch: {data}"
        print(f"✅ raw_code={data.get('raw_code')}")

    def test_empty_code_returns_400(self, headers):
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": ""}, headers=headers)
        assert r.status_code == 400, f"Expected 400 for empty code, got {r.status_code}"
        print("✅ Empty code returns 400")


# ─── 4. GET /api/scan/{code} — URL-based resolve ─────────────────────────────

class TestGetCodeResolve:
    """GET /api/scan/{code} same behaviour as POST resolve."""

    def test_get_known_po_status_200(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/{PO_CODE}", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        print(f"✅ GET /api/scan/{PO_CODE} → 200")

    def test_get_known_po_found_true(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/{PO_CODE}", headers=headers)
        data = r.json()
        assert data.get("found") is True, f"Expected found=True: {data}"
        print(f"✅ GET found=True for {PO_CODE}")

    def test_get_known_po_entity_type(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/{PO_CODE}", headers=headers)
        data = r.json()
        assert data.get("entity_type") == "purchase_order", f"entity_type mismatch: {data}"
        print("✅ GET entity_type=purchase_order")

    def test_get_unknown_code(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/{UNKNOWN_CODE}", headers=headers)
        data = r.json()
        assert r.status_code == 200
        assert data.get("found") is False, f"Expected found=False: {data}"
        print("✅ GET unknown code → found=False")


# ─── 5. GET /api/scan/history — history endpoint ─────────────────────────────

class TestScanHistory:
    """GET /api/scan/history returns audit trail."""

    def test_history_returns_list(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/history", headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert isinstance(data, list), f"Expected list, got: {type(data)}"
        print(f"✅ GET /api/scan/history returns list ({len(data)} items)")

    def test_history_contains_found_scan(self, headers):
        """After resolving PO, history should have at least one found entry."""
        # First ensure we have scanned PO
        requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": PO_CODE}, headers=headers)

        r = requests.get(f"{BASE_URL}/api/scan/history", headers=headers)
        data = r.json()
        found_entries = [h for h in data if h.get("found") is True and h.get("entity_type") == "purchase_order"]
        assert len(found_entries) > 0, f"No found PO scan in history: {data[:3]}"
        print("✅ History has found PO scan entry")

    def test_history_contains_not_found_scan(self, headers):
        """After unknown code scan, history should have at least one not-found entry."""
        requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": UNKNOWN_CODE}, headers=headers)

        r = requests.get(f"{BASE_URL}/api/scan/history", headers=headers)
        data = r.json()
        not_found_entries = [h for h in data if h.get("found") is False]
        assert len(not_found_entries) > 0, f"No not-found scan in history: {data[:3]}"
        print("✅ History has not-found scan entry")

    def test_history_item_has_required_fields(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/history", headers=headers)
        data = r.json()
        assert len(data) > 0, "History is empty, cannot check fields"
        item = data[0]
        for field in ["id", "raw_code", "found", "scanned_at", "scanned_by"]:
            assert field in item, f"Missing field '{field}' in history item: {item}"
        print("✅ History item has all required fields: id, raw_code, found, scanned_at, scanned_by")

    def test_history_limit_param(self, headers):
        r = requests.get(f"{BASE_URL}/api/scan/history?limit=5", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) <= 5, f"Limit not respected: got {len(data)} items"
        print(f"✅ History limit param respected ({len(data)} items for limit=5)")

    def test_history_ordered_desc(self, headers):
        """History should be ordered by scanned_at descending."""
        r = requests.get(f"{BASE_URL}/api/scan/history?limit=10", headers=headers)
        data = r.json()
        if len(data) < 2:
            pytest.skip("Not enough history items to check order")
        timestamps = [h.get("scanned_at", "") for h in data]
        assert timestamps == sorted(timestamps, reverse=True), f"History not ordered descending: {timestamps[:3]}"
        print("✅ History ordered by scanned_at descending")


# ─── 6. QR JSON payload ───────────────────────────────────────────────────────

class TestQRJSONPayload:
    """POST /api/scan/resolve with embedded JSON QR code."""

    def test_json_qr_unknown_entity(self, headers):
        """Embedded JSON with unknown entity_type still returns found=false."""
        qr_json = '{"type": "unknown_type", "id": "some-id"}'
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": qr_json}, headers=headers)
        assert r.status_code == 200
        data = r.json()
        # Should try JSON parse but fallback to sequential resolvers
        # Result: either found or not-found but no 500 error
        assert "found" in data, f"Response missing 'found' field: {data}"
        print(f"✅ JSON QR with unknown type returns valid response: found={data.get('found')}")

    def test_json_qr_no_crash(self, headers):
        """Malformed JSON string should not cause 500."""
        r = requests.post(f"{BASE_URL}/api/scan/resolve", json={"code": "{invalid json"}, headers=headers)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "found" in data
        print("✅ Malformed JSON QR string handled gracefully")
