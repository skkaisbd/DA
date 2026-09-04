"""Backend E2E for the 5 Produksi/Maklon bugs (INV-F27)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com").rstrip("/")

ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASS = "Admin@123"
CMT_EMAIL = "cmtvendor@dewiaditya.id"
CMT_PASS = "Dewi@123"


def _login(email, password):
    time.sleep(2)
    r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:200]}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="module")
def admin_token():
    return _login(ADMIN_EMAIL, ADMIN_PASS)


@pytest.fixture(scope="module")
def cmt_token():
    return _login(CMT_EMAIL, CMT_PASS)


@pytest.fixture(scope="module")
def admin_headers(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture(scope="module")
def cmt_headers(cmt_token):
    return {"Authorization": f"Bearer {cmt_token}"}


# ---------- Helper: find our test scenario PO ----------
@pytest.fixture(scope="module")
def scenario(admin_headers):
    """Locate the latest PO-MKL created by scripts/verify_fase_e ..."""
    r = requests.get(f"{BASE_URL}/api/dewi/maklon/pos", headers=admin_headers, timeout=30)
    assert r.status_code == 200, r.text[:200]
    pos = r.json()
    if isinstance(pos, dict):
        pos = pos.get("items") or pos.get("data") or []
    # pick a maklon PO with 100 order, ideally the newest that has receipts with reject remain
    for po in sorted(pos, key=lambda x: x.get("created_at", ""), reverse=True):
        po_num = po.get("po_number") or ""
        if "PO-MKL-" not in po_num:
            continue
        po_id = po.get("id") or po.get("_id")
        # find receipts
        rr = requests.get(f"{BASE_URL}/api/prod/cmt-receipts?po_id={po_id}", headers=admin_headers, timeout=30)
        if rr.status_code != 200:
            continue
        receipts = rr.json()
        if isinstance(receipts, dict):
            receipts = receipts.get("items") or receipts.get("data") or []
        for rc in receipts:
            for line in rc.get("lines", []) or []:
                reject_remain = (line.get("reject_qty") or line.get("qty_reject") or 0) - (line.get("qty_reworked_ok") or 0) - (line.get("qty_scrap") or 0)
                if reject_remain > 0:
                    return {
                        "po": po,
                        "po_id": po_id,
                        "po_number": po_num,
                        "po_item_id": (po.get("items") or [{}])[0].get("item_id") or (po.get("items") or [{}])[0].get("id"),
                        "receipt_id": rc.get("id") or rc.get("_id"),
                        "receipt_line_id": line.get("id"),
                        "reject_remain": reject_remain,
                    }
    pytest.skip("no maklon PO with reject remain found — run scripts/verify_fase_e_kapasitas_kirim.py --scenario-only first")


# =====================================================
# BUG 1 — Permak auto-link ke reject line
# =====================================================
class TestBug1PermakAutoLink:
    def test_create_permak_without_receipt_line_auto_links(self, admin_headers, scenario):
        payload = {
            "po_id": scenario["po_id"],
            "po_item_id": scenario["po_item_id"],
            "qty": 3,
            "source": "reject",
            "permak_type": "permak_sendiri",
        }
        r = requests.post(f"{BASE_URL}/api/dewi/cmt-permak", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code in (200, 201), f"{r.status_code} {r.text[:300]}"
        data = r.json()
        # backend may split into 1..N permak docs; find at least one with source_receipt_line_id filled
        docs = data if isinstance(data, list) else data.get("permaks") or [data]
        assert docs, f"no permak docs returned: {data}"
        for d in docs:
            assert d.get("source_receipt_line_id"), f"missing source_receipt_line_id: {d}"
            assert d.get("source_link_auto") is True, f"source_link_auto should be True: {d}"
        # keep for next test
        pytest.permak_docs = docs

    def test_finish_permak_updates_reworked_ok(self, admin_headers, scenario):
        docs = getattr(pytest, "permak_docs", [])
        assert docs, "prev test did not create permak"
        # capture reworked_ok before
        def _reworked_ok():
            rr = requests.get(f"{BASE_URL}/api/prod/cmt-receipts?po_id={scenario['po_id']}", headers=admin_headers, timeout=30)
            receipts = rr.json()
            if isinstance(receipts, dict):
                receipts = receipts.get("items") or receipts.get("data") or []
            for rc in receipts:
                if (rc.get("id") or rc.get("_id")) == scenario["receipt_id"]:
                    for line in rc.get("lines", []) or []:
                        if line.get("id") == scenario["receipt_line_id"]:
                            return line.get("qty_reworked_ok") or 0
            return 0

        before = _reworked_ok()
        total_fixed = 0
        for d in docs:
            pid = d.get("id") or d.get("_id")
            q = d.get("qty") or d.get("qty_permak") or 0
            r = requests.post(
                f"{BASE_URL}/api/dewi/cmt-permak/{pid}/status",
                headers=admin_headers,
                json={"status": "selesai_berhasil", "qty_fixed": q, "qty_scrap": 0},
                timeout=30,
            )
            assert r.status_code in (200, 201), f"finish permak {pid}: {r.status_code} {r.text[:300]}"
            total_fixed += q
        time.sleep(1)
        after = _reworked_ok()
        assert after >= before + total_fixed, f"reworked_ok did not increase: before={before} after={after} added={total_fixed}"

    def test_dispatch_capacity_shows_reworked(self, admin_headers, scenario):
        r = requests.get(
            f"{BASE_URL}/api/buyer-dispatch-capacity?receipt_ids={scenario['receipt_id']}",
            headers=admin_headers,
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:200]}"
        d = r.json()
        # Should have reworked_ok / shippable fields somewhere
        payload = str(d).lower()
        assert "rework" in payload or "shippable" in payload or "reworked" in payload, f"capacity missing rework fields: {d}"

    def test_permak_over_reject_remain_rejected_400(self, admin_headers, scenario):
        payload = {
            "po_id": scenario["po_id"],
            "po_item_id": scenario["po_item_id"],
            "qty": 999999,
            "source": "reject",
            "permak_type": "permak_sendiri",
        }
        r = requests.post(f"{BASE_URL}/api/dewi/cmt-permak", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:300]}"


# =====================================================
# BUG 2 — Dispatch lanjutan (same SJ, dispatch_seq +1)
# =====================================================
class TestBug2ContinueDispatch:
    def test_create_initial_and_continue(self, admin_headers, scenario):
        # 1) create fresh buyer shipment with qty=5 from receipt
        payload1 = {
            "receiver_type": "buyer",
            "source_receipt_ids": [scenario["receipt_id"]],
            "po_ids": [scenario["po_id"]],
            "items": [
                {
                    "po_id": scenario["po_id"],
                    "po_item_id": scenario["po_item_id"],
                    "receipt_id": scenario["receipt_id"],
                    "qty_shipped": 5,
                }
            ],
        }
        r1 = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=admin_headers, json=payload1, timeout=30)
        assert r1.status_code in (200, 201), f"create SJ: {r1.status_code} {r1.text[:400]}"
        d1 = r1.json()
        sj_id = d1.get("id") or d1.get("_id")
        sj_number = d1.get("shipment_number")
        assert sj_id and sj_number, f"missing id/number: {d1}"
        assert (d1.get("dispatch_seq") or 1) == 1
        assert d1.get("is_new") in (True, None)

        # 2) continue dispatch on SAME SJ
        payload2 = dict(payload1)
        payload2["shipment_id"] = sj_id
        payload2["items"] = [dict(payload1["items"][0], qty_shipped=3)]
        r2 = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=admin_headers, json=payload2, timeout=30)
        assert r2.status_code in (200, 201), f"continue: {r2.status_code} {r2.text[:400]}"
        d2 = r2.json()
        assert (d2.get("id") or d2.get("_id")) == sj_id, f"id changed: {d2}"
        assert d2.get("shipment_number") == sj_number, f"number changed: {d2}"
        assert d2.get("dispatch_seq") == 2, f"expected dispatch_seq=2: {d2}"
        assert d2.get("is_new") is False, f"is_new should be False: {d2}"
        pytest.sj_id = sj_id
        pytest.sj_number = sj_number

    def test_continue_over_remaining_rejected_400(self, admin_headers, scenario):
        sj_id = getattr(pytest, "sj_id", None)
        assert sj_id, "no SJ from previous test"
        payload = {
            "shipment_id": sj_id,
            "receiver_type": "buyer",
            "source_receipt_ids": [scenario["receipt_id"]],
            "po_ids": [scenario["po_id"]],
            "items": [{
                "po_id": scenario["po_id"],
                "po_item_id": scenario["po_item_id"],
                "receipt_id": scenario["receipt_id"],
                "qty_shipped": 999999,
            }],
        }
        r = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:300]}"

    def test_continue_unknown_shipment_id_404(self, admin_headers, scenario):
        payload = {
            "shipment_id": "does-not-exist-xyz-000",
            "receiver_type": "buyer",
            "source_receipt_ids": [scenario["receipt_id"]],
            "po_ids": [scenario["po_id"]],
            "items": [{
                "po_id": scenario["po_id"],
                "po_item_id": scenario["po_item_id"],
                "receipt_id": scenario["receipt_id"],
                "qty_shipped": 1,
            }],
        }
        r = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=admin_headers, json=payload, timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:300]}"


# =====================================================
# BUG 3 — BOM aksesoris preview (read-only, no write)
# =====================================================
class TestBug3BomAccessoriesPreview:
    def test_preview_returns_accessories(self, admin_headers):
        # get a catalog item that has an active BOM template
        r = requests.get(f"{BASE_URL}/api/dewi/maklon/bom-templates", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        tpls = r.json()
        if isinstance(tpls, dict):
            tpls = tpls.get("items") or tpls.get("data") or []
        active = [t for t in tpls if t.get("is_active", True)]
        if not active:
            pytest.skip("no active BOM template")
        # find catalog_item_id from template
        catalog_item_id = None
        for t in active:
            catalog_item_id = t.get("catalog_item_id") or t.get("buyer_catalog_item_id") or t.get("buyer_catalog_id")
            if catalog_item_id:
                break
        if not catalog_item_id:
            pytest.skip("template has no catalog_item_id linkage")
        payload = {"items": [{"catalog_item_id": catalog_item_id, "qty": 100}]}
        r = requests.post(
            f"{BASE_URL}/api/dewi/maklon/bom-templates/preview-accessories",
            headers=admin_headers,
            json=payload,
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        assert "accessories" in d, f"missing accessories: {d}"
        assert isinstance(d["accessories"], list)
        assert d.get("total_pcs") == 100 or "total_pcs" in d


# =====================================================
# BUG 4 — Vendor CMT can list material-requests type=REPLACEMENT
# =====================================================
class TestBug4VendorReplacementList:
    def test_material_requests_replacement_filter(self, cmt_headers):
        r = requests.get(
            f"{BASE_URL}/api/material-requests?request_type=REPLACEMENT",
            headers=cmt_headers,
            timeout=30,
        )
        assert r.status_code == 200, f"{r.status_code} {r.text[:300]}"
        d = r.json()
        items = d if isinstance(d, list) else d.get("items") or d.get("data") or []
        # filter must be honored: if not empty, each must be REPLACEMENT
        for it in items:
            rt = (it.get("request_type") or "").upper()
            assert rt == "REPLACEMENT", f"non-REPLACEMENT leaked: {it.get('request_type')}"


# =====================================================
# BUG 5 — Child shipment (parent_shipment_id) has no PO accessories
# =====================================================
class TestBug5ChildShipmentNoAccessories:
    def test_child_shipment_no_po_accessories(self, admin_headers):
        # list all vendor shipments and find one with parent_shipment_id (child)
        r = requests.get(f"{BASE_URL}/api/vendor-shipments", headers=admin_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        d = r.json()
        items = d if isinstance(d, list) else d.get("items") or d.get("data") or []
        child = next(
            (x for x in items if x.get("parent_shipment_id") or x.get("is_child_shipment") or (x.get("shipment_kind") or "").upper() in ("REPLACEMENT","ADDITIONAL","REWORK")),
            None,
        )
        if not child:
            pytest.skip("no child (REPLACEMENT/ADDITIONAL/REWORK) vendor shipment exists in DB")
        # list-view assertion
        assert (child.get("po_accessories_count") or 0) == 0, f"child po_accessories_count>0: {child}"
        # detail
        cid = child.get("id") or child.get("_id")
        rd = requests.get(f"{BASE_URL}/api/vendor-shipments/{cid}", headers=admin_headers, timeout=30)
        assert rd.status_code == 200, rd.text[:200]
        det = rd.json()
        assert det.get("po_accessories", []) == [], f"child has po_accessories: {det.get('po_accessories')}"
        assert det.get("accessories_scope") == "own", f"accessories_scope wrong: {det.get('accessories_scope')}"
        assert det.get("is_child_shipment") is True, f"is_child_shipment not True: {det.get('is_child_shipment')}"

    def test_parent_still_carries_po_accessories(self, admin_headers):
        r = requests.get(f"{BASE_URL}/api/vendor-shipments", headers=admin_headers, timeout=30)
        d = r.json()
        items = d if isinstance(d, list) else d.get("items") or d.get("data") or []
        parents = [x for x in items if not x.get("parent_shipment_id") and not x.get("is_child_shipment")]
        if not parents:
            pytest.skip("no parent shipments")
        # at least one parent should have po_accessories_count>=0 (non-null field present)
        seen_field = any(("po_accessories_count" in x) for x in parents)
        assert seen_field, "po_accessories_count field missing on parent list rows"


# =====================================================
# REGRESSION — new buyer shipment still gets fresh number & seq=1
# =====================================================
class TestRegressionNewShipment:
    def test_new_shipment_seq1(self, admin_headers, scenario):
        payload = {
            "receiver_type": "buyer",
            "source_receipt_ids": [scenario["receipt_id"]],
            "po_ids": [scenario["po_id"]],
            "items": [{
                "po_id": scenario["po_id"],
                "po_item_id": scenario["po_item_id"],
                "receipt_id": scenario["receipt_id"],
                "qty_shipped": 1,
            }],
        }
        r = requests.post(f"{BASE_URL}/api/buyer-shipments", headers=admin_headers, json=payload, timeout=30)
        # may be rejected if capacity exhausted; accept 200/201 or 400 with clean message
        if r.status_code in (200, 201):
            d = r.json()
            assert d.get("dispatch_seq") == 1
            assert d.get("is_new") in (True, None)
            assert d.get("shipment_number")
        else:
            assert r.status_code == 400, f"unexpected {r.status_code}: {r.text[:200]}"
