"""Iteration 99 — Finance > Pencairan Marketplace:
   (1) POST /api/marketing/settlements/import/preview
   (2) GET  /api/marketing/settlements/by-account
"""
import os

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")

SHOPEE = "/app/samples/settlement_shopee_contoh.csv"
TIKTOK = "/app/samples/settlement_tiktok_contoh.xlsx"
ORDERS = "/app/samples/ekspor_A_pesanan_contoh.csv"

PREVIEW = f"{BASE_URL}/api/marketing/settlements/import/preview"
BYACC = f"{BASE_URL}/api/marketing/settlements/by-account"


@pytest.fixture(scope="session")
def admin_token():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"},
                      timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    return tok


@pytest.fixture(scope="session")
def H(admin_token):
    return {"Authorization": f"Bearer {admin_token}"}


# ── modul: import/preview ────────────────────────────────────────────────────
class TestImportPreviewShopee:
    def test_shopee_csv_preview(self, H):
        with open(SHOPEE, "rb") as f:
            r = requests.post(PREVIEW, headers=H,
                              files={"file": ("settlement_shopee_contoh.csv", f, "text/csv")},
                              timeout=90)
        assert r.status_code == 200, r.text[:600]
        d = r.json()
        assert d["ok"] is True
        assert d["row_count"] == 2
        assert d["platform_guess"] == "shopee"
        v = d["values"]
        assert v["gross_sales"] == 3000000
        assert v["refunds"] == 200000
        assert v["seller_discount"] == 170000
        assert v["platform_commission"] == 135000
        assert v["platform_service_fee"] == 45000
        assert v["affiliate_commission"] == 10000
        assert v["net_payout"] == 2440000
        assert d["settlement_date"] == "2026-08-15"
        assert d["period_from"] == "2026-08-02"
        assert d["period_to"] == "2026-08-05"
        assert d["unmapped_numeric_columns"] == ["Ongkos Kirim Dibayar Pembeli"]
        assert d["draft"]["expected_net_payout"] == 2440000
        # mapping must name source column per field
        for f_ in ("gross_sales", "refunds", "seller_discount", "platform_commission",
                   "platform_service_fee", "affiliate_commission", "net_payout"):
            assert d["mapping"].get(f_), f"mapping missing source column for {f_}"

    def test_preview_does_not_persist(self, H):
        before = requests.get(f"{BASE_URL}/api/marketing/settlements?page_size=1",
                              headers=H, timeout=60).json()["pagination"]["total"]
        with open(SHOPEE, "rb") as f:
            requests.post(PREVIEW, headers=H,
                          files={"file": ("settlement_shopee_contoh.csv", f, "text/csv")},
                          timeout=90)
        after = requests.get(f"{BASE_URL}/api/marketing/settlements?page_size=1",
                             headers=H, timeout=60).json()["pagination"]["total"]
        assert after == before, "preview inserted rows into settlements"


class TestImportPreviewTiktok:
    def test_tiktok_xlsx_preview(self, H):
        with open(TIKTOK, "rb") as f:
            r = requests.post(PREVIEW, headers=H,
                              files={"file": ("settlement_tiktok_contoh.xlsx", f,
                                              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
                              timeout=90)
        assert r.status_code == 200, r.text[:600]
        d = r.json()
        assert d["platform_guess"] == "tiktokshop"
        assert d["settlement_id"] == "STM-2026-08-16-01"
        v = d["values"]
        assert v["gross_sales"] == 7000000
        assert v["net_payout"] == 5920000
        assert v["adjustments"] == -70000
        assert v["affiliate_commission"] == 100000
        assert d["unmapped_numeric_columns"] == ["Shipping cost"]


class TestImportPreviewErrors:
    def test_order_export_rejected_400(self, H):
        with open(ORDERS, "rb") as f:
            r = requests.post(PREVIEW, headers=H,
                              files={"file": ("ekspor_A_pesanan_contoh.csv", f, "text/csv")},
                              timeout=90)
        assert r.status_code == 400, r.text[:600]
        assert "Tidak ada satu pun kolom uang" in r.json().get("detail", "")

    def test_pdf_extension_415(self, H):
        r = requests.post(PREVIEW, headers=H,
                          files={"file": ("laporan.pdf", b"%PDF-1.4 dummy", "application/pdf")},
                          timeout=60)
        assert r.status_code == 415, r.text[:300]

    def test_png_extension_415(self, H):
        r = requests.post(PREVIEW, headers=H,
                          files={"file": ("shot.png", b"\x89PNG\r\n\x1a\n", "image/png")},
                          timeout=60)
        assert r.status_code == 415, r.text[:300]

    def test_empty_file_400(self, H):
        r = requests.post(PREVIEW, headers=H,
                          files={"file": ("kosong.csv", b"", "text/csv")}, timeout=60)
        assert r.status_code == 400, r.text[:300]
        assert "kosong" in r.json().get("detail", "").lower()

    def test_no_token_401(self):
        with open(SHOPEE, "rb") as f:
            r = requests.post(PREVIEW,
                              files={"file": ("settlement_shopee_contoh.csv", f, "text/csv")},
                              timeout=60)
        assert r.status_code == 401, f"{r.status_code} {r.text[:300]}"

    def test_non_finance_user_403(self):
        r = requests.post(f"{BASE_URL}/api/auth/login",
                          json={"email": "hr@dewiaditya.id", "password": "Dewi@123"},
                          timeout=60)
        if r.status_code != 200:
            pytest.skip(f"hr@dewiaditya.id not usable ({r.status_code})")
        tok = r.json().get("access_token") or r.json().get("token")
        with open(SHOPEE, "rb") as f:
            r2 = requests.post(PREVIEW, headers={"Authorization": f"Bearer {tok}"},
                               files={"file": ("settlement_shopee_contoh.csv", f, "text/csv")},
                               timeout=60)
        assert r2.status_code == 403, f"{r2.status_code} {r2.text[:300]}"


# ── modul: by-account (Ringkasan Per Toko) ───────────────────────────────────
class TestByAccount:
    FIELDS = ("account_name", "platform", "count", "gross_sales", "net_payout",
              "total_deductions", "deduction_pct", "commission_pct", "ads_pct",
              "refund_pct", "unverified_count")

    def test_default_month(self, H):
        r = requests.get(BYACC, headers=H, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["ok"] is True
        assert d["month"] == "2026-08", f"expected latest month 2026-08, got {d['month']}"
        assert "2026-08" in d["months"] and "2026-07" in d["months"]
        assert d["months"] == sorted(d["months"], reverse=True)
        assert len(d["data"]) >= 1
        for row in d["data"]:
            for f_ in self.FIELDS:
                assert f_ in row, f"missing {f_}"
        assert isinstance(d["average_deduction_pct"], (int, float))

    def test_month_july(self, H):
        r = requests.get(BYACC, headers=H, params={"month": "2026-07"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["month"] == "2026-07"
        shopee = [x for x in d["data"] if x["account_name"] == "DA Official Shopee"]
        assert shopee, f"DA Official Shopee missing: {d['data']}"
        assert shopee[0]["count"] == 2
        assert shopee[0]["deduction_pct"] == 6

    def test_month_empty(self, H):
        r = requests.get(BYACC, headers=H, params={"month": "2026-01"}, timeout=60)
        assert r.status_code == 200
        assert r.json()["data"] == []

    def test_bad_month_400(self, H):
        r = requests.get(BYACC, headers=H, params={"month": "bad"}, timeout=60)
        assert r.status_code == 400, f"{r.status_code} {r.text[:300]}"

    def test_no_mongo_id_leak(self, H):
        r = requests.get(BYACC, headers=H, timeout=60)
        for row in r.json()["data"]:
            assert "_id" not in row
