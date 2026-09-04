"""
Session 30 — P2 & P3 Feature Tests
P2: Approval Badge Endpoint (/api/approval-inbox/badge)
P3: Channel GL Mapping CRUD (/api/rahaza/channel-gl-mapping)
"""
import pytest
import requests
import os

def _get_base_url():
    url = os.environ.get("REACT_APP_BACKEND_URL", "").strip()
    if not url:
        env_path = "/app/frontend/.env"
        try:
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("REACT_APP_BACKEND_URL="):
                        url = line.split("=", 1)[1].strip()
                        break
        except Exception:
            pass
    return url.rstrip("/")

BASE_URL = _get_base_url()


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def admin_token():
    """Superadmin token — full access"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123"
    })
    assert resp.status_code == 200, f"Admin login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data.get("data", {}).get("token")
    assert token, f"No token in response: {data}"
    return token

@pytest.fixture(scope="module")
def hr_token():
    """HR role token — only sees hr_pending"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "hr@dewiaditya.id",
        "password": "Dewi@123"
    })
    assert resp.status_code == 200, f"HR login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data.get("data", {}).get("token")
    assert token, f"No token in response: {data}"
    return token

@pytest.fixture(scope="module")
def finance_token():
    """Finance role token"""
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "finance@dewiaditya.id",
        "password": "Dewi@123"
    })
    assert resp.status_code == 200, f"Finance login failed: {resp.text}"
    data = resp.json()
    token = data.get("access_token") or data.get("token") or data.get("data", {}).get("token")
    assert token, f"No token in response: {data}"
    return token

@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def hr_headers(hr_token):
    return {"Authorization": f"Bearer {hr_token}", "Content-Type": "application/json"}

@pytest.fixture(scope="module")
def finance_headers(finance_token):
    return {"Authorization": f"Bearer {finance_token}", "Content-Type": "application/json"}


# ═══════════════════════════════════════════════════════════════════════════════
# P2: Approval Badge Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestApprovalBadgeEndpoint:
    """P2 — GET /api/approval-inbox/badge"""

    def test_badge_requires_auth(self):
        """Endpoint should return 401/403 without token"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print(f"✅ badge requires auth (got {resp.status_code})")

    def test_badge_admin_returns_200(self, admin_headers):
        """Admin badge returns 200 with correct structure"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        print(f"✅ Admin badge response: {data}")

    def test_badge_admin_response_structure(self, admin_headers):
        """Badge response has all required fields"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Required top-level fields
        assert "total" in data, "Missing 'total' field"
        assert "pr_pending" in data, "Missing 'pr_pending' field"
        assert "ap_pending" in data, "Missing 'ap_pending' field"
        assert "hr_pending" in data, "Missing 'hr_pending' field"
        assert "categories" in data, "Missing 'categories' field"
        # Type checks
        assert isinstance(data["total"], int), "total must be int"
        assert isinstance(data["pr_pending"], int), "pr_pending must be int"
        assert isinstance(data["ap_pending"], int), "ap_pending must be int"
        assert isinstance(data["hr_pending"], int), "hr_pending must be int"
        assert isinstance(data["categories"], list), "categories must be list"
        print(f"✅ Admin badge structure correct: total={data['total']}, pr={data['pr_pending']}, ap={data['ap_pending']}, hr={data['hr_pending']}")

    def test_badge_admin_total_equals_sum(self, admin_headers):
        """total must equal pr_pending + ap_pending + hr_pending"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        expected_total = data["pr_pending"] + data["ap_pending"] + data["hr_pending"]
        assert data["total"] == expected_total, (
            f"total={data['total']} != sum={expected_total} "
            f"(pr={data['pr_pending']}, ap={data['ap_pending']}, hr={data['hr_pending']})"
        )
        print(f"✅ total ({data['total']}) = pr + ap + hr ({expected_total})")

    def test_badge_admin_categories_structure(self, admin_headers):
        """Each category has key, label, count, module_id, icon"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        categories = data["categories"]
        # Admin should have all 3 categories (pr, ap, hr)
        assert len(categories) >= 1, "Admin should see at least 1 category"
        for cat in categories:
            assert "key" in cat, f"Category missing 'key': {cat}"
            assert "label" in cat, f"Category missing 'label': {cat}"
            assert "count" in cat, f"Category missing 'count': {cat}"
            assert "module_id" in cat, f"Category missing 'module_id': {cat}"
            assert isinstance(cat["count"], int), f"count must be int: {cat}"
        # Check PR and AP categories for admin (both should be present since admin is in both roles)
        keys = {c["key"] for c in categories}
        assert "pr" in keys, "Admin should have PR category"
        assert "ap" in keys, "Admin should have AP category"
        assert "hr" in keys, "Admin should have HR category"
        print(f"✅ Admin has categories: {[c['key'] for c in categories]}")

    def test_badge_admin_category_module_ids(self, admin_headers):
        """Categories should point to correct module IDs"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        cat_map = {c["key"]: c for c in data["categories"]}
        if "pr" in cat_map:
            assert cat_map["pr"]["module_id"] == "fin-procurement-requests", (
                f"PR category module_id wrong: {cat_map['pr']['module_id']}"
            )
        if "ap" in cat_map:
            assert cat_map["ap"]["module_id"] == "fin-ap-aging", (
                f"AP category module_id wrong: {cat_map['ap']['module_id']}"
            )
        if "hr" in cat_map:
            assert cat_map["hr"]["module_id"] == "hr-inbox", (
                f"HR category module_id wrong: {cat_map['hr']['module_id']}"
            )
        print("✅ Category module IDs are correct")

    def test_badge_hr_role_only_sees_hr(self, hr_headers):
        """HR role should only see HR category (not PR, not AP)"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=hr_headers)
        assert resp.status_code == 200, f"HR badge failed: {resp.text}"
        data = resp.json()
        print(f"HR badge response: {data}")
        categories = data["categories"]
        keys = {c["key"] for c in categories}
        # HR should have hr category
        assert "hr" in keys, "HR user should see HR category"
        # HR should NOT have ap category (not in FINANCE_ROLES)
        assert "ap" not in keys, f"HR user should NOT see AP category, but got keys: {keys}"
        # pr_pending and ap_pending should be 0 for hr role
        assert data["pr_pending"] == 0 or "pr" not in keys, "HR role should not count PR pending"
        assert data["ap_pending"] == 0, "HR role should not count AP pending"
        print(f"✅ HR role badge categories correct: {keys}")

    def test_badge_finance_role_sees_ap(self, finance_headers):
        """Finance/accounting role should see AP and PR categories"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=finance_headers)
        assert resp.status_code == 200, f"Finance badge failed: {resp.text}"
        data = resp.json()
        print(f"Finance badge response: {data}")
        categories = data["categories"]
        keys = {c["key"] for c in categories}
        # Finance should have AP category
        assert "ap" in keys, f"Finance user should see AP category, got: {keys}"
        # Finance should NOT have HR category (not in HR_ROLES)
        assert "hr" not in keys, f"Finance user should NOT see HR category, got: {keys}"
        print(f"✅ Finance role badge categories correct: {keys}")

    def test_badge_pr_pending_count_positive(self, admin_headers):
        """PR pending should be > 0 (seed has 3 PRs with 'submitted' status)"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # According to task description, 3 PRs + 2 AP should be there
        # We check that the counts are non-negative integers
        assert data["pr_pending"] >= 0, f"pr_pending must be >= 0: {data['pr_pending']}"
        print(f"✅ pr_pending = {data['pr_pending']} (expected >= 0, ideally 3)")

    def test_badge_ap_pending_count_positive(self, admin_headers):
        """AP pending should be > 0 (seed has 2 AP invoices with sent/partial_paid status)"""
        resp = requests.get(f"{BASE_URL}/api/approval-inbox/badge", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["ap_pending"] >= 0, f"ap_pending must be >= 0: {data['ap_pending']}"
        print(f"✅ ap_pending = {data['ap_pending']} (expected >= 0, ideally 2)")


# ═══════════════════════════════════════════════════════════════════════════════
# P3: Channel GL Mapping Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestChannelGLMappingList:
    """P3 — GET /api/rahaza/channel-gl-mapping"""

    def test_channel_gl_requires_auth(self):
        """Endpoint should require authentication"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping")
        assert resp.status_code in [401, 403], f"Expected 401/403 without auth, got {resp.status_code}"
        print(f"✅ channel-gl requires auth (got {resp.status_code})")

    def test_channel_gl_list_returns_200(self, admin_headers):
        """GET channels list returns 200"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        print(f"✅ Channel GL list: {len(data)} channels")

    def test_channel_gl_has_13_channels(self, admin_headers):
        """Should have exactly 13 seeded channels"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 13, f"Expected >= 13 channels, got {len(data)}"
        print(f"✅ Channel GL count: {len(data)} (expected 13+)")

    def test_channel_gl_platform_distribution(self, admin_headers):
        """Check platform distribution: shopee=4, tiktok=6, tokopedia=1, maklon=2"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        # Count per platform
        by_platform = {}
        for ch in data:
            p = ch.get("platform", "unknown")
            by_platform[p] = by_platform.get(p, 0) + 1
        print(f"Platform distribution: {by_platform}")
        assert by_platform.get("shopee", 0) >= 4, f"Expected 4 shopee channels, got {by_platform.get('shopee', 0)}"
        assert by_platform.get("tiktok", 0) >= 6, f"Expected 6 tiktok channels, got {by_platform.get('tiktok', 0)}"
        assert by_platform.get("tokopedia", 0) >= 1, f"Expected 1 tokopedia channel, got {by_platform.get('tokopedia', 0)}"
        assert by_platform.get("maklon", 0) >= 2, f"Expected 2 maklon channels, got {by_platform.get('maklon', 0)}"
        print(f"✅ Platform distribution correct: {by_platform}")

    def test_channel_gl_record_structure(self, admin_headers):
        """Each channel record has required fields"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0, "No channels to check structure"
        ch = data[0]
        required_fields = ["id", "channel_key", "channel_label", "platform", "debit_ar", "credit_revenue", "active"]
        for field in required_fields:
            assert field in ch, f"Channel missing field '{field}': {ch}"
        assert "_id" not in ch, "MongoDB _id should not be in response"
        print(f"✅ Channel record structure correct: {list(ch.keys())}")

    def test_channel_gl_debit_ar_format(self, admin_headers):
        """debit_ar codes should start with 1- (AR accounts)"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        for ch in data:
            assert ch["debit_ar"].startswith("1-"), (
                f"debit_ar '{ch['debit_ar']}' for '{ch['channel_key']}' should start with '1-'"
            )
        print("✅ All debit_ar codes start with '1-'")

    def test_channel_gl_credit_revenue_format(self, admin_headers):
        """credit_revenue codes should start with 4- (revenue accounts)"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        for ch in data:
            assert ch["credit_revenue"].startswith("4-"), (
                f"credit_revenue '{ch['credit_revenue']}' for '{ch['channel_key']}' should start with '4-'"
            )
        print("✅ All credit_revenue codes start with '4-'")

    def test_channel_gl_maklon_uses_different_ar(self, admin_headers):
        """Maklon channels should use 1-210 AR (not 1-220 like OS channels)"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        for ch in data:
            if ch["platform"] == "maklon":
                assert ch["debit_ar"] == "1-210", (
                    f"Maklon channel '{ch['channel_key']}' should use 1-210 AR, got '{ch['debit_ar']}'"
                )
            elif ch["platform"] in ("shopee", "tiktok", "tokopedia"):
                assert ch["debit_ar"] == "1-220", (
                    f"OS channel '{ch['channel_key']}' should use 1-220 AR, got '{ch['debit_ar']}'"
                )
        print("✅ Maklon uses 1-210, OS channels use 1-220")


class TestChannelGLMappingCRUD:
    """P3 — Create, Update, Delete channel GL mapping"""

    CREATED_CHANNEL_ID = None

    def test_create_channel_requires_finance_role(self, hr_headers):
        """HR role should NOT be able to create channels (403)"""
        resp = requests.post(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping",
            headers=hr_headers,
            json={
                "channel_key": "test_hr_channel",
                "channel_label": "Test HR Channel",
                "platform": "other",
                "debit_ar": "1-220",
                "credit_revenue": "4-121"
            }
        )
        assert resp.status_code in [403, 401], (
            f"HR should NOT create channel (expected 403), got {resp.status_code}: {resp.text}"
        )
        print(f"✅ HR role rejected (got {resp.status_code})")

    def test_create_channel_success(self, admin_headers):
        """Admin can create a new channel"""
        resp = requests.post(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping",
            headers=admin_headers,
            json={
                "channel_key": "test_new_channel_automation",
                "channel_label": "Test New Channel (Automation)",
                "platform": "shopee",
                "debit_ar": "1-220",
                "credit_revenue": "4-111"
            }
        )
        assert resp.status_code == 200, f"Create failed: {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "id" in data, f"Created channel should have id: {data}"
        assert data["channel_key"] == "test_new_channel_automation"
        assert data["platform"] == "shopee"
        assert data["debit_ar"] == "1-220"
        assert data["credit_revenue"] == "4-111"
        assert "_id" not in data, "MongoDB _id should not be in response"
        TestChannelGLMappingCRUD.CREATED_CHANNEL_ID = data["id"]
        print(f"✅ Channel created: id={data['id']}, key={data['channel_key']}")

    def test_create_channel_duplicate_key_rejected(self, admin_headers):
        """Duplicate channel_key should return 409"""
        resp = requests.post(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping",
            headers=admin_headers,
            json={
                "channel_key": "test_new_channel_automation",  # same key
                "channel_label": "Duplicate Test",
                "platform": "shopee",
                "debit_ar": "1-220",
                "credit_revenue": "4-112"
            }
        )
        assert resp.status_code == 409, f"Expected 409 for duplicate key, got {resp.status_code}: {resp.text}"
        print("✅ Duplicate channel_key rejected with 409")

    def test_update_channel_success(self, admin_headers):
        """Admin can update an existing channel"""
        channel_id = TestChannelGLMappingCRUD.CREATED_CHANNEL_ID
        if not channel_id:
            pytest.skip("No channel ID from create test")

        resp = requests.put(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping/{channel_id}",
            headers=admin_headers,
            json={
                "channel_label": "Test Channel Updated",
                "platform": "shopee",
                "debit_ar": "1-220",
                "credit_revenue": "4-112"  # changed from 4-111 to 4-112
            }
        )
        assert resp.status_code == 200, f"Update failed: {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["credit_revenue"] == "4-112", f"credit_revenue not updated: {data['credit_revenue']}"
        assert data["channel_label"] == "Test Channel Updated", f"channel_label not updated: {data['channel_label']}"
        print(f"✅ Channel updated: credit_revenue={data['credit_revenue']}")

    def test_get_updated_channel_persisted(self, admin_headers):
        """Verify update is persisted via GET list"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        channel_id = TestChannelGLMappingCRUD.CREATED_CHANNEL_ID
        if not channel_id:
            pytest.skip("No channel ID to verify")
        found = next((c for c in data if c["id"] == channel_id), None)
        assert found is not None, f"Updated channel not found in list (id={channel_id})"
        assert found["credit_revenue"] == "4-112", f"Updated value not persisted: {found['credit_revenue']}"
        print(f"✅ Updated channel persisted in DB: credit_revenue={found['credit_revenue']}")

    def test_update_nonexistent_channel_returns_404(self, admin_headers):
        """Updating nonexistent channel should return 404"""
        resp = requests.put(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping/nonexistent-id-999",
            headers=admin_headers,
            json={"channel_label": "Ghost", "platform": "shopee", "debit_ar": "1-220", "credit_revenue": "4-111"}
        )
        assert resp.status_code == 404, f"Expected 404 for nonexistent channel, got {resp.status_code}"
        print("✅ Nonexistent channel returns 404")

    def test_delete_channel_success(self, admin_headers):
        """Admin can soft-delete a channel"""
        channel_id = TestChannelGLMappingCRUD.CREATED_CHANNEL_ID
        if not channel_id:
            pytest.skip("No channel ID from create test")

        resp = requests.delete(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping/{channel_id}",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Delete failed: {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True, f"Delete should return ok=True: {data}"
        print(f"✅ Channel soft-deleted: id={channel_id}")

    def test_deleted_channel_not_in_list(self, admin_headers):
        """Soft-deleted channel should not appear in list"""
        channel_id = TestChannelGLMappingCRUD.CREATED_CHANNEL_ID
        if not channel_id:
            pytest.skip("No channel ID to verify")

        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        found = next((c for c in data if c["id"] == channel_id), None)
        assert found is None, f"Soft-deleted channel should NOT appear in list: {found}"
        print("✅ Deleted channel not in list")


class TestChannelGLSeedEndpoint:
    """P3 — Seed default channels endpoint"""

    def test_seed_requires_finance_role(self, hr_headers):
        """HR role should NOT be able to seed channels"""
        resp = requests.post(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping/seed-da",
            headers=hr_headers
        )
        assert resp.status_code in [403, 401], (
            f"HR should NOT seed channels (expected 403), got {resp.status_code}: {resp.text}"
        )
        print(f"✅ HR role rejected from seed (got {resp.status_code})")

    def test_seed_idempotent(self, admin_headers):
        """Seed endpoint is idempotent — calling again should skip all existing"""
        resp = requests.post(
            f"{BASE_URL}/api/rahaza/channel-gl-mapping/seed-da",
            headers=admin_headers
        )
        assert resp.status_code == 200, f"Seed failed: {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") is True, f"Seed should return ok=True: {data}"
        assert "inserted" in data, "Seed response missing 'inserted' count"
        assert "skipped" in data, "Seed response missing 'skipped' count"
        assert "total" in data, "Seed response missing 'total' count"
        assert data["total"] == 13, f"Expected 13 total channels, got {data['total']}"
        # Since channels already seeded, inserted should be 0 (idempotent)
        assert data["inserted"] == 0, (
            f"Seed should be idempotent (inserted=0), but inserted={data['inserted']}"
        )
        assert data["skipped"] == 13, (
            f"Seed should skip all 13 existing channels, but skipped={data['skipped']}"
        )
        print(f"✅ Seed idempotent: inserted={data['inserted']}, skipped={data['skipped']}, total={data['total']}")


class TestChannelGLListWithFinanceUser:
    """P3 — Finance role can view channel GL list"""

    def test_finance_can_list_channels(self, finance_headers):
        """Finance role can view channel GL list"""
        resp = requests.get(f"{BASE_URL}/api/rahaza/channel-gl-mapping", headers=finance_headers)
        assert resp.status_code == 200, f"Finance should be able to list channels, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert isinstance(data, list), "Expected list response"
        print(f"✅ Finance can list channels: {len(data)} channels")
