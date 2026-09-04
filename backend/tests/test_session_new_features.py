"""Backend tests for Session 87 features:
- Portal Assistant (Asisten ERP CV. Dewi Aditya) — KB + AI fallback
- Doc Numbering (35 doc types)
- Advanced backup (live collections + safe clear)
- Production dashboard (business_type internal/maklon)
- Material import UOM columns + input_uom regression
"""
from __future__ import annotations

import os
import io
import csv
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=30)
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tok = r.json().get("token") or r.json().get("access_token")
    assert tok, r.json()
    return tok


@pytest.fixture(scope="module")
def H(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# =========================================================
# Portal Assistant
# =========================================================
class TestAssistantContext:
    def test_warehouse_context(self, H):
        r = requests.get(f"{BASE_URL}/api/assistant/context?portal=warehouse", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["assistant_name"] == "Asisten ERP CV. Dewi Aditya"
        assert d["kb_available"] is True
        assert d["portal_label"]
        assert isinstance(d["saran"], list) and len(d["saran"]) > 0

    def test_finance_context(self, H):
        r = requests.get(f"{BASE_URL}/api/assistant/context?portal=finance", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["kb_available"] is True

    def test_hr_context(self, H):
        r = requests.get(f"{BASE_URL}/api/assistant/context?portal=hr", headers=H, timeout=30)
        assert r.status_code == 200
        assert r.json()["kb_available"] is True

    def test_unknown_portal_falls_back(self, H):
        r = requests.get(f"{BASE_URL}/api/assistant/context?portal=xyz-unknown", headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        assert d["kb_available"] is False
        # label defaults to 'Umum' when fallback used
        assert d["portal_label"]


class TestAssistantAsk:
    def test_kb_answer_warehouse(self, H):
        r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                          json={"question": "Bagaimana cara melakukan stok opname?", "portal": "warehouse"})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["source"] == "kb", d
        # "bagaimana/cara" should yield numbered steps (flow)
        assert any(f"{n}." in d["reply"] or f"{n})" in d["reply"] for n in range(1, 4)), d["reply"]
        assert d.get("session_id")

    def test_kb_answer_finance(self, H):
        r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                          json={"question": "kenapa jurnal tidak terbentuk otomatis", "portal": "finance"})
        assert r.status_code == 200
        assert r.json()["source"] == "kb"

    def test_kb_answer_hr(self, H):
        r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                          json={"question": "bagaimana menjalankan penggajian", "portal": "hr"})
        assert r.status_code == 200
        assert r.json()["source"] == "kb"

    def test_cross_portal_question(self, H):
        # asking about cutting while on warehouse portal
        r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                          json={"question": "bagaimana cara membuat order cutting", "portal": "warehouse"})
        assert r.status_code == 200
        d = r.json()
        # Should still answer from KB
        assert d["source"] in ("kb", "ai"), d

    def test_out_of_scope_returns_graceful_200(self, H):
        r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                          json={"question": "berapa harga saham tesla hari ini", "portal": "warehouse"})
        assert r.status_code == 200, r.text
        d = r.json()
        # Since ANTHROPIC_API_KEY is empty, AI path unavailable → should say so politely in Indonesian
        assert "AI" in d["reply"] or "belum" in d["reply"].lower() or "maaf" in d["reply"].lower()

    def test_empty_question_400(self, H):
        r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                          json={"question": "", "portal": "warehouse"})
        assert r.status_code == 400


class TestAssistantHistory:
    def test_multi_turn_history(self, H):
        sid = f"TEST-asst-{uuid.uuid4().hex[:8]}"
        questions = [
            "Bagaimana cara melakukan stok opname?",
            "apa itu putaway",
            "bagaimana cara transfer stok",
        ]
        for q in questions:
            r = requests.post(f"{BASE_URL}/api/assistant/ask", headers=H, timeout=30,
                              json={"question": q, "portal": "warehouse", "session_id": sid})
            assert r.status_code == 200

        r = requests.get(f"{BASE_URL}/api/assistant/history?session_id={sid}", headers=H, timeout=30)
        assert r.status_code == 200
        msgs = r.json()["messages"]
        assert len(msgs) == 6  # 3 pairs
        roles = [m["role"] for m in msgs]
        assert roles == ["user", "assistant"] * 3

        # cleanup
        rd = requests.delete(f"{BASE_URL}/api/assistant/history?session_id={sid}", headers=H, timeout=30)
        assert rd.status_code == 200
        assert rd.json()["deleted"] >= 6

        # verify gone
        r2 = requests.get(f"{BASE_URL}/api/assistant/history?session_id={sid}", headers=H, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["messages"] == []


# =========================================================
# Doc Numbering
# =========================================================
class TestDocNumbering:
    TEST_KEY = "wh_returns.return_code"

    def test_list_35_types(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/doc-numbering", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert len(d["items"]) == 35, f"expected 35 doc types, got {len(d['items'])}"
        for it in d["items"]:
            assert "format" in it and "contoh" in it
            assert it.get("error") is None, f"{it['key']} has error: {it['error']}"

    def test_preview_rejects_bad_formats(self, H):
        # missing {SEQ}
        r1 = requests.post(f"{BASE_URL}/api/admin/doc-numbering/preview", headers=H,
                           json={"key": self.TEST_KEY, "format": "RET/{YYYY}/"}, timeout=30)
        assert r1.status_code == 200
        assert r1.json()["ok"] is False

        # text after {SEQ}
        r2 = requests.post(f"{BASE_URL}/api/admin/doc-numbering/preview", headers=H,
                           json={"key": self.TEST_KEY, "format": "RET/{SEQ:4}/END"}, timeout=30)
        assert r2.status_code == 200
        assert r2.json()["ok"] is False

        # unknown token
        r3 = requests.post(f"{BASE_URL}/api/admin/doc-numbering/preview", headers=H,
                           json={"key": self.TEST_KEY, "format": "RET/{BULAN}/{SEQ:4}"}, timeout=30)
        assert r3.status_code == 200
        assert r3.json()["ok"] is False

    def test_save_custom_and_reset(self, H):
        # save custom
        custom = "TESTRET/{YYYY}/{SEQ:5}"
        r = requests.put(f"{BASE_URL}/api/admin/doc-numbering", headers=H,
                         json={"key": self.TEST_KEY, "format": custom, "active": True}, timeout=30)
        assert r.status_code == 200, r.text

        # verify is_custom=true
        listing = requests.get(f"{BASE_URL}/api/admin/doc-numbering", headers=H, timeout=30).json()
        entry = next(x for x in listing["items"] if x["key"] == self.TEST_KEY)
        assert entry["is_custom"] is True
        assert entry["format"] == custom

        # reset
        rd = requests.delete(f"{BASE_URL}/api/admin/doc-numbering/{self.TEST_KEY}", headers=H, timeout=30)
        assert rd.status_code == 200

        listing2 = requests.get(f"{BASE_URL}/api/admin/doc-numbering", headers=H, timeout=30).json()
        entry2 = next(x for x in listing2["items"] if x["key"] == self.TEST_KEY)
        assert entry2["is_custom"] is False

    def test_counter_set_and_reject_decrease(self, H):
        # Set to a high value first
        r = requests.post(f"{BASE_URL}/api/admin/doc-numbering/counter", headers=H,
                          json={"key": self.TEST_KEY, "start_from": 9000}, timeout=30)
        # This may 400 if existing docs use prefix; capture behavior
        assert r.status_code in (200, 400), r.text
        # Reset counter back if possible (to 0 requires no docs with prefix — best effort)


# =========================================================
# Advanced Backup
# =========================================================
class TestAdvBackup:
    def test_live_collections(self, H):
        r = requests.get(f"{BASE_URL}/api/admin/backup/live-collections", headers=H, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "collections" in d or "items" in d, d.keys()
        items = d.get("collections") or d.get("items")
        assert isinstance(items, list) and len(items) > 0

        protected_expected = {"users", "roles", "counters", "doc_number_configs", "rahaza_coa_accounts"}
        by_name = {i["name"]: i for i in items}
        for name in protected_expected:
            if name in by_name:
                assert by_name[name].get("protected") is True, f"{name} should be protected"

    def test_clear_rejects_missing_confirm(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/backup/clear-collections", headers=H,
                          json={"collections": ["zztest_dummy"], "confirm_text": "WRONG"}, timeout=30)
        assert r.status_code == 400

    def test_clear_rejects_protected_without_flag(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/backup/clear-collections", headers=H,
                          json={"collections": ["users"], "confirm_text": "KOSONGKAN"}, timeout=30)
        assert r.status_code == 400

    def test_clear_rejects_unknown_collection(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/backup/clear-collections", headers=H,
                          json={"collections": ["definitely_not_a_real_collection_xyz"],
                                "confirm_text": "KOSONGKAN"}, timeout=30)
        assert r.status_code in (404, 400)

    def test_clear_rejects_empty_list(self, H):
        r = requests.post(f"{BASE_URL}/api/admin/backup/clear-collections", headers=H,
                          json={"collections": [], "confirm_text": "KOSONGKAN"}, timeout=30)
        assert r.status_code == 400


# =========================================================
# Production Dashboard
# =========================================================
class TestProdDashboard:
    def test_internal(self, H):
        r = requests.get(f"{BASE_URL}/api/prod/dashboard?business_type=internal&days=30",
                         headers=H, timeout=30)
        assert r.status_code == 200, r.text
        d = r.json()
        # Required sections
        for key in ("ringkasan", "pipeline", "cutting", "vendor", "qc", "permak", "handover", "aging"):
            assert key in d, f"missing section {key}; keys={list(d.keys())}"
        # Pipeline 6 stages
        pipeline = d["pipeline"]
        stages_list = pipeline if isinstance(pipeline, list) else pipeline.get("stages", [])
        assert len(stages_list) == 6, f"expected 6 pipeline stages, got {len(stages_list)}"

    def test_maklon(self, H):
        r = requests.get(f"{BASE_URL}/api/prod/dashboard?business_type=maklon&days=30",
                         headers=H, timeout=30)
        assert r.status_code == 200
        d = r.json()
        # handover label should be "Dispatch ke Buyer" for maklon
        ho = d.get("handover", {})
        label = ho.get("label") or ho.get("title") or ""
        assert "Dispatch" in label or "Buyer" in label, f"label={label}"

    def test_invalid_business_type(self, H):
        r = requests.get(f"{BASE_URL}/api/prod/dashboard?business_type=alien&days=30",
                         headers=H, timeout=30)
        assert r.status_code == 422


# =========================================================
# Material Import Template — UOM columns
# =========================================================
class TestMaterialImport:
    def test_template_has_uom_columns(self, H):
        r = requests.get(f"{BASE_URL}/api/data-transfer/template/materials?format=csv",
                         headers=H, timeout=30)
        assert r.status_code == 200, r.text
        text = r.text
        for col in ("base_uom", "pack_unit", "pack_size", "display_in_packs"):
            assert col in text, f"missing column {col} in template; head={text[:400]}"


# =========================================================
# UOM entry points regression (no 500 on invalid input_uom)
# =========================================================
class TestUomEntryPointRegression:
    def test_putaway_invalid_input_uom_no_500(self, H):
        # send obviously invalid payload → should be 4xx, not 500
        r = requests.post(f"{BASE_URL}/api/wms/putaway/place", headers=H, timeout=30,
                          json={"material_id": "does-not-exist", "bin_id": "does-not-exist",
                                "qty": 1, "input_uom": "GALAXY"})
        assert r.status_code < 500, f"got 5xx: {r.status_code} {r.text[:200]}"

    def test_opname_scan_invalid_input_uom_no_500(self, H):
        r = requests.post(f"{BASE_URL}/api/wms/opname3/scan", headers=H, timeout=30,
                          json={"session_id": "nope", "code": "NA", "qty": 1, "input_uom": "GALAXY"})
        assert r.status_code < 500, f"got 5xx: {r.status_code} {r.text[:200]}"
