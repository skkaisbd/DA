"""
Iteration 12 — RND Portal backend regression (CV. Dewi Aditya ERP)

Modules covered:
  - Auth
  - RnD Dashboard / Analytics / Overview
  - Styles CRUD + design selection workflow (submit → owner-approve/reject → promote)
  - Variants
  - Sample Requests (CRUD + lifecycle: draft → submitted → approved/rejected)
  - Revisions
  - Materials
  - Sample Costing
  - Patterns
  - Tech Packs (+approve)
  - HPP Calculator (CRUD + math validation + preview)
  - Accessory Requests (lifecycle: draft → submitted → allocated → delivered)
  - Kreator Requests (lifecycle: draft → submitted → approved_by_rnd → sample_ready → delivered)

Notes:
  - admin user is super-admin (no role-based 403 expected on these endpoints).
  - AI endpoints not covered (none in RnD; 503 acceptable elsewhere).
  - Test data is TEST_-prefixed where applicable; cleanup is best-effort.
"""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"
RND = f"{BASE_URL}/api/dewi/rnd"
ACC_URL = f"{BASE_URL}/api/dewi/accessory-requests"
KRE_URL = f"{BASE_URL}/api/dewi/kreator-requests"

# ── shared state for create→read flow tests ──────────────────────────────────
state = {}


# ── fixtures ─────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def token():
    r = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASS},
        timeout=30,
    )
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:300]}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, f"No token in response: {r.text[:300]}"
    return tok


@pytest.fixture(scope="session")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ─────────────────────────────────────────────────────────────────────────────
# 1) DASHBOARD / OVERVIEW / ANALYTICS
# ─────────────────────────────────────────────────────────────────────────────
class TestRndDashboard:
    def test_dashboard(self, H):
        r = requests.get(f"{RND}/dashboard", headers=H, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert "kpi" in data
        assert "total_styles" in data["kpi"]

    def test_analytics(self, H):
        r = requests.get(f"{RND}/analytics", headers=H, timeout=30)
        assert r.status_code == 200, r.text[:300]


# ─────────────────────────────────────────────────────────────────────────────
# 2) STYLES — CRUD + workflow
# ─────────────────────────────────────────────────────────────────────────────
class TestRndStyles:
    def test_list_styles(self, H):
        r = requests.get(f"{RND}/styles", headers=H, timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_create_style(self, H):
        code = f"TEST-STY-{int(time.time())}"
        payload = {
            "style_code": code,
            "style_name": "TEST Style RnD",
            "category": "shirt",
            "rnd_type": "internal_product",
        }
        r = requests.post(f"{RND}/styles", headers=H, json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        data = r.json()
        assert data["style_code"] == code.upper()
        state["style_id"] = data["id"]
        state["style_code"] = data["style_code"]
        state["style_name"] = data["style_name"]

    def test_get_style(self, H):
        sid = state["style_id"]
        r = requests.get(f"{RND}/styles/{sid}", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == sid

    def test_update_style(self, H):
        sid = state["style_id"]
        r = requests.put(f"{RND}/styles/{sid}", headers=H,
                         json={"description": "updated desc"}, timeout=30)
        assert r.status_code == 200
        assert r.json().get("description") == "updated desc"

    def test_submit_for_review(self, H):
        sid = state["style_id"]
        r = requests.post(f"{RND}/styles/{sid}/submit-for-review",
                          headers=H, json={"notes": "ready"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "pending_owner_review"

    def test_pending_review_list(self, H):
        r = requests.get(f"{RND}/styles/pending-review", headers=H, timeout=30)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert state["style_id"] in ids

    def test_owner_approve(self, H):
        sid = state["style_id"]
        r = requests.post(f"{RND}/styles/{sid}/owner-approve",
                          headers=H, json={"notes": "ok"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "approved_for_launch"

    def test_promote_to_production(self, H):
        sid = state["style_id"]
        r = requests.post(f"{RND}/styles/{sid}/promote-to-production",
                          headers=H, json={}, timeout=30)
        assert r.status_code == 200, r.text[:300]
        assert r.json().get("status") == "promoted"


# ─────────────────────────────────────────────────────────────────────────────
# 3) VARIANTS
# ─────────────────────────────────────────────────────────────────────────────
class TestRndVariants:
    def test_list(self, H):
        r = requests.get(f"{RND}/variants", headers=H, timeout=30)
        assert r.status_code == 200

    def test_create_variant(self, H):
        payload = {
            "style_id": state.get("style_id", ""),
            "style_code": state.get("style_code", ""),
            "color": "TEST_RED",
            "sizes": ["S", "M", "L"],
        }
        r = requests.post(f"{RND}/variants", headers=H, json=payload, timeout=30)
        assert r.status_code == 200
        state["variant_id"] = r.json()["id"]

    def test_update_variant(self, H):
        vid = state["variant_id"]
        r = requests.put(f"{RND}/variants/{vid}", headers=H,
                         json={"notes": "updated"}, timeout=30)
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 4) SAMPLE REQUESTS + lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class TestRndSamples:
    def test_list(self, H):
        r = requests.get(f"{RND}/sample-requests", headers=H, timeout=30)
        assert r.status_code == 200

    def test_create_sample(self, H):
        payload = {"style_id": state["style_id"], "quantity": 2, "notes": "TEST sample"}
        r = requests.post(f"{RND}/sample-requests", headers=H, json=payload, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["style_id"] == state["style_id"]
        state["sample_id"] = d["id"]

    def test_update_sample(self, H):
        sid = state["sample_id"]
        r = requests.put(f"{RND}/sample-requests/{sid}", headers=H,
                         json={"quantity": 3}, timeout=30)
        assert r.status_code == 200
        assert r.json()["quantity"] == 3

    def test_submit_sample(self, H):
        sid = state["sample_id"]
        r = requests.post(f"{RND}/sample-requests/{sid}/submit",
                          headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "submitted"

    def test_approve_sample(self, H):
        sid = state["sample_id"]
        r = requests.post(f"{RND}/sample-requests/{sid}/approve",
                          headers=H, json={"notes": "ok"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "approved"

    def test_create_second_sample_and_reject(self, H):
        payload = {"style_id": state["style_id"], "quantity": 1}
        r = requests.post(f"{RND}/sample-requests", headers=H, json=payload, timeout=30)
        assert r.status_code == 200
        sid2 = r.json()["id"]
        r = requests.post(f"{RND}/sample-requests/{sid2}/submit", headers=H, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{RND}/sample-requests/{sid2}/reject",
                          headers=H, json={"notes": "test reject"}, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "rejected"
        state["sample_id_rejected"] = sid2


# ─────────────────────────────────────────────────────────────────────────────
# 5) REVISIONS
# ─────────────────────────────────────────────────────────────────────────────
class TestRndRevisions:
    def test_list(self, H):
        r = requests.get(f"{RND}/revisions", headers=H, timeout=30)
        assert r.status_code == 200

    def test_create_revision(self, H):
        r = requests.post(f"{RND}/revisions", headers=H,
                          json={"style_id": state["style_id"],
                                "changes_summary": "TEST rev",
                                "reason": "test"},
                          timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["style_id"] == state["style_id"]
        assert d["revision_number"] == 1
        state["revision_id"] = d["id"]

    def test_revision_increments(self, H):
        r = requests.post(f"{RND}/revisions", headers=H,
                          json={"style_id": state["style_id"], "reason": "test2"},
                          timeout=30)
        assert r.status_code == 200
        assert r.json()["revision_number"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# 6) MATERIALS + SAMPLE COSTING
# ─────────────────────────────────────────────────────────────────────────────
class TestRndMaterials:
    def test_list(self, H):
        r = requests.get(f"{RND}/materials", headers=H, timeout=30)
        assert r.status_code == 200

    def test_create_material(self, H):
        code = f"TEST-MAT-{int(time.time())}"
        r = requests.post(f"{RND}/materials", headers=H, json={
            "material_code": code,
            "material_name": "TEST Fabric",
            "category": "fabric",
            "price_per_meter": 25000,
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        state["material_id"] = r.json()["id"]

    def test_get_material(self, H):
        r = requests.get(f"{RND}/materials/{state['material_id']}", headers=H, timeout=30)
        assert r.status_code == 200

    def test_update_material(self, H):
        r = requests.put(f"{RND}/materials/{state['material_id']}", headers=H,
                         json={"notes": "updated"}, timeout=30)
        assert r.status_code == 200

    def test_sample_costing_list(self, H):
        r = requests.get(f"{RND}/sample-costing", headers=H, timeout=30)
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 7) PATTERNS
# ─────────────────────────────────────────────────────────────────────────────
class TestRndPatterns:
    def test_list(self, H):
        r = requests.get(f"{RND}/patterns", headers=H, timeout=30)
        assert r.status_code == 200

    def test_create_pattern(self, H):
        r = requests.post(f"{RND}/patterns", headers=H, json={
            "pattern_code": f"TEST-PAT-{int(time.time())}",
            "style_id": state["style_id"],
            "style_code": state["style_code"],
            "size_range": "S-XL",
            "total_pieces": 10,
            "fabric_usage_per_pcs": 1.2,
            "efficiency_pct": 85,
        }, timeout=30)
        assert r.status_code == 200
        state["pattern_id"] = r.json()["id"]

    def test_update_pattern(self, H):
        r = requests.put(f"{RND}/patterns/{state['pattern_id']}", headers=H,
                         json={"notes": "updated"}, timeout=30)
        assert r.status_code == 200

    def test_approve_pattern(self, H):
        r = requests.post(f"{RND}/patterns/{state['pattern_id']}/approve",
                          headers=H, timeout=30)
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 8) TECH PACK
# ─────────────────────────────────────────────────────────────────────────────
class TestRndTechPack:
    def test_list(self, H):
        r = requests.get(f"{RND}/tech-packs", headers=H, timeout=30)
        assert r.status_code == 200

    def test_create_tech_pack(self, H):
        r = requests.post(f"{RND}/tech-packs", headers=H, json={
            "style_id": state["style_id"],
            "style_code": state["style_code"],
            "style_name": state["style_name"],
            "version": "v1",
            "title": "TEST TP",
            "bom_items": [{"material_code": "M1", "qty": 1, "unit": "m"}],
        }, timeout=30)
        assert r.status_code == 200
        state["tp_id"] = r.json()["id"]

    def test_get_tp(self, H):
        r = requests.get(f"{RND}/tech-packs/{state['tp_id']}", headers=H, timeout=30)
        assert r.status_code == 200

    def test_update_tp(self, H):
        r = requests.put(f"{RND}/tech-packs/{state['tp_id']}", headers=H,
                         json={"description": "TEST"}, timeout=30)
        assert r.status_code == 200

    def test_approve_tp(self, H):
        r = requests.post(f"{RND}/tech-packs/{state['tp_id']}/approve",
                          headers=H, timeout=30)
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 9) HPP CALCULATOR — CRUD + math
# ─────────────────────────────────────────────────────────────────────────────
class TestRndHPP:
    def test_list(self, H):
        r = requests.get(f"{RND}/hpp-calculator", headers=H, timeout=30)
        assert r.status_code == 200

    def test_preview_math(self, H):
        # fabric_cost = 1.2 * 50000 = 60000
        # acc_total = 1*2000 + 5*500 = 4500
        # direct = 60000 + 4500 + 10000 + 5000 + 2000 = 81500
        # overhead = 81500 * 0.10 = 8150
        # hpp_total = 89650
        # selling_price = 89650 / 0.70 = 128071.4285 ≈ 128071.43
        body = {
            "fabric_usage_per_pcs": 1.2,
            "fabric_price_per_meter": 50000,
            "accessories_cost": [
                {"unit_cost": 2000, "qty": 1},
                {"unit_cost": 500,  "qty": 5},
            ],
            "cmt_cost_per_pcs": 10000,
            "cutting_cost_per_pcs": 5000,
            "packaging_cost_per_pcs": 2000,
            "overhead_pct": 10,
            "margin_pct": 30,
        }
        r = requests.post(f"{RND}/hpp-calculator/preview", headers=H, json=body, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert abs(d["fabric_cost"] - 60000) < 0.5
        assert abs(d["accessories_total"] - 4500) < 0.5
        assert abs(d["direct_cost"] - 81500) < 0.5
        assert abs(d["overhead_value"] - 8150) < 0.5
        assert abs(d["hpp_total"] - 89650) < 0.5
        assert abs(d["selling_price_proposal"] - 128071.43) < 0.5

    def test_create_hpp(self, H):
        body = {
            "style_id": state["style_id"],
            "style_code": state["style_code"],
            "style_name": state["style_name"],
            "fabric_usage_per_pcs": 1,
            "fabric_price_per_meter": 30000,
            "cmt_cost_per_pcs": 10000,
            "overhead_pct": 10,
            "margin_pct": 30,
        }
        r = requests.post(f"{RND}/hpp-calculator", headers=H, json=body, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # direct = 30000 + 10000 = 40000; overhead = 4000; hpp = 44000; sell = 44000/0.7 = 62857.14
        assert abs(d["hpp_total"] - 44000) < 0.5
        assert abs(d["selling_price_proposal"] - 62857.14) < 0.5
        state["hpp_id"] = d["id"]

    def test_update_hpp(self, H):
        body = {
            "fabric_usage_per_pcs": 2,
            "fabric_price_per_meter": 30000,
            "overhead_pct": 0,
            "margin_pct": 50,
        }
        r = requests.put(f"{RND}/hpp-calculator/{state['hpp_id']}", headers=H, json=body, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # direct = 60000; overhead = 0; hpp = 60000; sell = 60000/0.5 = 120000
        assert abs(d["hpp_total"] - 60000) < 0.5
        assert abs(d["selling_price_proposal"] - 120000) < 0.5


# ─────────────────────────────────────────────────────────────────────────────
# 10) ACCESSORY REQUESTS — lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class TestAccessoryRequests:
    def test_list(self, H):
        r = requests.get(ACC_URL, headers=H, timeout=30)
        assert r.status_code == 200

    def test_create(self, H):
        r = requests.post(ACC_URL, headers=H, json={
            "request_type": "rnd_sample",
            "style_id": state["style_id"],
            "style_code": state["style_code"],
            "items": [
                {"material_code": "BTN-01", "material_name": "Button", "qty": 10, "unit": "pcs"},
            ],
            "notes": "TEST accessory request",
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["request_type"] == "rnd_sample"
        assert d["status"] == "draft"
        state["acc_id"] = d["id"]

    def test_lifecycle(self, H):
        aid = state["acc_id"]
        r = requests.post(f"{ACC_URL}/{aid}/submit", headers=H, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{ACC_URL}/{aid}/allocate", headers=H, json={"notes": "ok"}, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{ACC_URL}/{aid}/deliver", headers=H, json={"notes": "done"}, timeout=30)
        assert r.status_code == 200
        # verify final state
        r = requests.get(f"{ACC_URL}/{aid}", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "delivered"

    def test_create_no_items_400(self, H):
        r = requests.post(ACC_URL, headers=H, json={"items": []}, timeout=30)
        assert r.status_code == 400

    def test_stats_summary(self, H):
        r = requests.get(f"{ACC_URL}/stats/summary", headers=H, timeout=30)
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 11) KREATOR REQUESTS — lifecycle
# ─────────────────────────────────────────────────────────────────────────────
class TestKreatorRequests:
    def test_list(self, H):
        r = requests.get(KRE_URL, headers=H, timeout=30)
        assert r.status_code == 200

    def test_create(self, H):
        r = requests.post(KRE_URL, headers=H, json={
            "kreator_name": "TEST Kreator A",
            "kreator_type": "live_streaming",
            "product_concept": "TEST blouse for live streaming",
            "sample_qty": 2,
            "sample_colors": ["red", "blue"],
        }, timeout=30)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        assert d["status"] == "draft"
        state["kre_id"] = d["id"]

    def test_invalid_kreator_type(self, H):
        r = requests.post(KRE_URL, headers=H, json={
            "kreator_name": "TEST X",
            "kreator_type": "podcast",
            "product_concept": "x",
        }, timeout=30)
        assert r.status_code == 400

    def test_lifecycle(self, H):
        kid = state["kre_id"]
        r = requests.post(f"{KRE_URL}/{kid}/submit", headers=H, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{KRE_URL}/{kid}/approve-by-rnd", headers=H,
                          json={"style_id": state["style_id"],
                                "style_code": state["style_code"]},
                          timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{KRE_URL}/{kid}/mark-sample-ready", headers=H, timeout=30)
        assert r.status_code == 200
        r = requests.post(f"{KRE_URL}/{kid}/mark-delivered", headers=H, timeout=30)
        assert r.status_code == 200
        r = requests.get(f"{KRE_URL}/{kid}", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["status"] == "delivered"

    def test_stats_summary(self, H):
        r = requests.get(f"{KRE_URL}/stats/summary", headers=H, timeout=30)
        assert r.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# 12) CLEANUP (best-effort, runs last alphabetically by class name)
# ─────────────────────────────────────────────────────────────────────────────
class TestZCleanup:
    def test_cleanup(self, H):
        # delete created resources
        for path, key in [
            (f"{RND}/variants/{state.get('variant_id')}", "variant_id"),
            (f"{RND}/sample-requests/{state.get('sample_id_rejected')}", "sample_id_rejected"),
            (f"{RND}/sample-requests/{state.get('sample_id')}", "sample_id"),
            (f"{RND}/revisions/{state.get('revision_id')}", "revision_id"),
            (f"{RND}/materials/{state.get('material_id')}", "material_id"),
            (f"{RND}/patterns/{state.get('pattern_id')}", "pattern_id"),
            (f"{RND}/tech-packs/{state.get('tp_id')}", "tp_id"),
            (f"{RND}/hpp-calculator/{state.get('hpp_id')}", "hpp_id"),
            (f"{ACC_URL}/{state.get('acc_id')}", "acc_id"),
            (f"{KRE_URL}/{state.get('kre_id')}", "kre_id"),
            (f"{RND}/styles/{state.get('style_id')}", "style_id"),
        ]:
            if state.get(key):
                try:
                    requests.delete(path, headers=H, timeout=15)
                except Exception:
                    pass
        assert True
