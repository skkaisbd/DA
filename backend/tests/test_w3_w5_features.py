"""Backend API tests for W5 (Surat Jalan CMT) and W3 (Stock Thresholds/Alert Stok)."""
import os
import io
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://da37-cmt-bridge.preview.emergentagent.com').rstrip('/')

RECEIPT_ID = "2a3f4a50-ca98-4b31-ac03-cdcc0f7cef7c"
RECEIPT_CODE = "CMT-RCV-00001"


@pytest.fixture(scope="module")
def token():
    r = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"
    }, timeout=30)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text[:200]}"
    return r.json().get("access_token") or r.json().get("token")


@pytest.fixture(scope="module")
def auth_headers(token):
    return {"Authorization": f"Bearer {token}"}


# ---------------- W5 tests ----------------

class TestW5SuratJalanCMT:
    def test_pdf_missing_id_returns_400(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/export-pdf",
                         params={"type": "cmt-delivery-note"},
                         headers=auth_headers, timeout=30)
        assert r.status_code == 400, f"expected 400 got {r.status_code}: {r.text[:200]}"

    def test_pdf_unknown_id_returns_404(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/export-pdf",
                         params={"type": "cmt-delivery-note", "id": "karangan-123"},
                         headers=auth_headers, timeout=30)
        assert r.status_code == 404, f"expected 404 got {r.status_code}: {r.text[:200]}"

    def test_pdf_no_auth(self):
        r = requests.get(f"{BASE_URL}/api/export-pdf",
                         params={"type": "cmt-delivery-note", "id": RECEIPT_ID},
                         timeout=30)
        assert r.status_code in (401, 403), f"expected 401/403 got {r.status_code}"

    def test_pdf_valid_default_cols(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/export-pdf",
                         params={"type": "cmt-delivery-note", "id": RECEIPT_ID},
                         headers=auth_headers, timeout=60)
        assert r.status_code == 200, f"got {r.status_code}: {r.text[:300]}"
        ct = r.headers.get("content-type", "")
        assert "application/pdf" in ct, f"content-type={ct}"
        assert r.content.startswith(b"%PDF"), "not a PDF"
        assert len(r.content) > 500

    def test_pdf_narrow_cols(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/export-pdf",
                         params={"type": "cmt-delivery-note", "id": RECEIPT_ID,
                                 "cols": "serial,sku,product"},
                         headers=auth_headers, timeout=60)
        assert r.status_code == 200
        assert "application/pdf" in r.headers.get("content-type", "")
        assert r.content.startswith(b"%PDF")

    def test_pdf_number_idempotent(self, auth_headers):
        # print twice, expect same SJ-CMT number in PDF text
        r1 = requests.get(f"{BASE_URL}/api/export-pdf",
                          params={"type": "cmt-delivery-note", "id": RECEIPT_ID},
                          headers=auth_headers, timeout=60)
        r2 = requests.get(f"{BASE_URL}/api/export-pdf",
                          params={"type": "cmt-delivery-note", "id": RECEIPT_ID},
                          headers=auth_headers, timeout=60)
        assert r1.status_code == 200 and r2.status_code == 200
        try:
            import fitz
        except Exception:
            pytest.skip("pymupdf not installed")
        def extract_num(content):
            doc = fitz.open(stream=content, filetype="pdf")
            txt = "".join(p.get_text() for p in doc)
            doc.close()
            import re
            m = re.search(r"SJ-CMT/\d{4}/\d{2}/\d{4}", txt)
            return m.group(0) if m else None
        n1, n2 = extract_num(r1.content), extract_num(r2.content)
        assert n1 is not None, "SJ-CMT number not found in PDF1"
        assert n1 == n2, f"idempotency broken: {n1} vs {n2}"

    def test_doc_numbering_registry_has_series(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/admin/doc-numbering",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        # look for cmt_delivery_notes.dn_number key
        # payload may be list or dict
        text = str(data)
        assert "cmt_delivery_notes" in text and "dn_number" in text, \
            f"missing series in doc-numbering payload"


# ---------------- W3 tests ----------------

class TestW3StockThresholds:
    def test_list_thresholds(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rahaza/stock-thresholds",
                         params={"limit": 5}, headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        assert "items" in data and "summary" in data
        assert isinstance(data["items"], list)

    def test_summary(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/rahaza/stock-thresholds/summary",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200
        s = r.json()
        for k in ("with_threshold", "missing_threshold"):
            assert k in s, f"missing key {k}: {s}"

    def test_bulk_no_items_400(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/rahaza/stock-thresholds/bulk",
                          json={}, headers=auth_headers, timeout=30)
        assert r.status_code == 400, f"got {r.status_code}: {r.text[:200]}"

    def test_bulk_negative_min_400(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/rahaza/stock-thresholds/bulk",
                          json={"items": [{"material_id": "ACC-BTN-12",
                                            "min_stock_qty": -5}]},
                          headers=auth_headers, timeout=30)
        assert r.status_code == 400, f"got {r.status_code}: {r.text[:200]}"

    def test_bulk_unknown_material_404(self, auth_headers):
        r = requests.post(f"{BASE_URL}/api/rahaza/stock-thresholds/bulk",
                          json={"items": [{"material_id": "DOES-NOT-EXIST-XYZ",
                                            "min_stock_qty": 10}]},
                          headers=auth_headers, timeout=30)
        assert r.status_code == 404, f"got {r.status_code}: {r.text[:200]}"

    def test_warehouse_alerts_metadata(self, auth_headers):
        r = requests.get(f"{BASE_URL}/api/warehouse/alerts",
                         headers=auth_headers, timeout=30)
        assert r.status_code == 200, r.text[:200]
        data = r.json()
        # expect materials_missing_threshold in some part
        assert "materials_missing_threshold" in str(data), \
            f"metadata missing: {str(data)[:300]}"
