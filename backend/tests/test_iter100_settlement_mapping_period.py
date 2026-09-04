"""Iteration 100 — Finance > Pencairan Marketplace:
   (1) import/preview mapping_source auto|saved (+ fingerprint, column_totals)
   (2) POST/GET/DELETE import/mapping (per toko + sidik header)
   (3) GET /api/marketing/settlements?date_from&date_to (filter periode)
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
PREVIEW = f"{BASE_URL}/api/marketing/settlements/import/preview"
MAPPING = f"{BASE_URL}/api/marketing/settlements/import/mapping"
LIST = f"{BASE_URL}/api/marketing/settlements"

ACC_SHOPEE = "c386b3ce-2b85-453a-88a3-b3e5e37277be"
ACC_TIKTOK = "8a098933-42aa-497c-8140-7b2852d81268"


@pytest.fixture(scope="session")
def H():
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": "admin@garment.com", "password": "Admin@123"},
                      timeout=60)
    if r.status_code != 200:
        pytest.fail(f"admin login failed {r.status_code}: {r.text[:300]}")
    tok = r.json().get("access_token") or r.json().get("token")
    if not tok:
        pytest.fail(f"no token in login response: {r.text[:300]}")
    return {"Authorization": f"Bearer {tok}"}


def _preview(H=None, account_id=None):
    files = {"file": ("settlement_shopee_contoh.csv", open(SHOPEE, "rb"), "text/csv")}
    data = {"account_id": account_id} if account_id else None
    return requests.post(PREVIEW, headers=H or {}, files=files, data=data, timeout=90)


@pytest.fixture(scope="module")
def created_map_ids():
    return []


@pytest.fixture(scope="module", autouse=True)
def cleanup(H, created_map_ids):
    yield
    # CLEAN UP — hapus semua pemetaan yang dibuat tes ini
    r = requests.get(MAPPING, headers=H, params={"account_id": ACC_SHOPEE}, timeout=60)
    ids = set(created_map_ids)
    if r.status_code == 200:
        ids |= {row["id"] for row in r.json().get("data", [])}
    for mid in ids:
        requests.delete(f"{MAPPING}/{mid}", headers=H, timeout=60)


# NOTE: satu kelas saja — pytest.ini memakai xdist loadscope (grup per kelas);
# kelas terpisah akan dijalankan paralel dan fixture cleanup saling menghapus.
class TestIter100SettlementMappingPeriod:
    # ── modul: import/preview — tebakan otomatis ─────────────────────────────
    def test_preview_auto_shape(self, H):
        r = _preview(H, ACC_SHOPEE)
        assert r.status_code == 200, r.text[:600]
        d = r.json()
        assert d["mapping_source"] == "auto"
        assert isinstance(d["fingerprint"], str) and len(d["fingerprint"]) == 16
        int(d["fingerprint"], 16)  # hex
        assert len(d["headers"]) == 13, d["headers"]
        assert len(d["numeric_columns"]) == 9, d["numeric_columns"]
        ct = d["column_totals"]
        assert ct["Ongkos Kirim Dibayar Pembeli"] == 27000
        assert ct["Harga Asli Produk"] == 3000000
        assert d["unmapped_numeric_columns"] == ["Ongkos Kirim Dibayar Pembeli"]
        assert d["saved_mapping"] is None


    # ── modul: import/mapping — simpan/ambil/hapus ───────────────────────────
    def test_save_then_upsert_then_saved_preview(self, H, created_map_ids):
        p = _preview(H, ACC_SHOPEE).json()
        fp = p["fingerprint"]
        mapping = dict(p["mapping"])
        mapping["shipping_subsidy"] = ["Ongkos Kirim Dibayar Pembeli"]
        body = {"account_id": ACC_SHOPEE, "headers": p["headers"], "mapping": mapping,
                "meta_columns": p["meta_columns"], "filename": "settlement_shopee_contoh.csv"}
        r = requests.post(MAPPING, headers=H, json=body, timeout=60)
        assert r.status_code == 200, r.text[:600]
        d = r.json()
        assert d["ok"] is True and d["created"] is True
        assert d["data"]["fingerprint"] == fp
        assert "_id" not in d["data"]
        created_map_ids.append(d["data"]["id"])

        # upsert — posting ulang tidak membuat dokumen baru
        r2 = requests.post(MAPPING, headers=H, json=body, timeout=60)
        assert r2.status_code == 200, r2.text[:400]
        assert r2.json()["created"] is False
        assert r2.json()["data"]["id"] == d["data"]["id"]

        # GET list
        rl = requests.get(MAPPING, headers=H, params={"account_id": ACC_SHOPEE}, timeout=60)
        assert rl.status_code == 200
        rows = rl.json()["data"]
        assert any(x["id"] == d["data"]["id"] and x["fingerprint"] == fp for x in rows)

        # preview lagi → mapping_source saved
        s = _preview(H, ACC_SHOPEE).json()
        assert s["mapping_source"] == "saved"
        assert s["values"]["shipping_subsidy"] == 27000
        assert s["unmapped_numeric_columns"] == []
        assert s["saved_mapping"]["id"] == d["data"]["id"]
        assert s["draft"]["expected_net_payout"] == 2467000

        # toko LAIN → tetap auto (pemetaan per toko)
        o = _preview(H, ACC_TIKTOK).json()
        assert o["mapping_source"] == "auto"
        # tanpa account_id → auto
        n = _preview(H).json()
        assert n["mapping_source"] == "auto"

        # DELETE → ok, lalu 404
        rd = requests.delete(f"{MAPPING}/{d['data']['id']}", headers=H, timeout=60)
        assert rd.status_code == 200, rd.text[:300]
        rd2 = requests.delete(f"{MAPPING}/{d['data']['id']}", headers=H, timeout=60)
        assert rd2.status_code == 404, rd2.text[:300]

    def test_empty_mapping_400(self, H):
        r = requests.post(MAPPING, headers=H, json={
            "account_id": ACC_SHOPEE, "headers": ["A", "B"], "mapping": {}}, timeout=60)
        assert r.status_code == 400, r.text[:300]

    def test_unknown_account_4xx(self, H):
        r = requests.post(MAPPING, headers=H, json={
            "account_id": "does-not-exist", "headers": ["A"],
            "mapping": {"gross_sales": ["A"]}}, timeout=60)
        assert 400 <= r.status_code < 500, f"{r.status_code} {r.text[:300]}"

    def test_no_token_unauthorized(self):
        r = requests.post(MAPPING, json={"account_id": ACC_SHOPEE, "headers": ["A"],
                                         "mapping": {"gross_sales": ["A"]}}, timeout=60)
        assert r.status_code in (401, 403), r.status_code
        rd = requests.delete(f"{MAPPING}/whatever", timeout=60)
        assert rd.status_code in (401, 403), rd.status_code
        rp = _preview(None, ACC_SHOPEE)
        assert rp.status_code in (401, 403), rp.status_code


    # ── modul: list settlements — filter periode ─────────────────────────────
    def test_july_range(self, H):
        r = requests.get(LIST, headers=H,
                         params={"date_from": "2026-07-01", "date_to": "2026-07-31"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert len(d["data"]) == 2, [x["settlement_id"] for x in d["data"]]
        assert all(x["settlement_date"].startswith("2026-07") for x in d["data"])
        assert d["summary"]["net_payout"] == 9400000
        assert d["pagination"]["total"] == 2

    def test_august_range(self, H):
        r = requests.get(LIST, headers=H,
                         params={"date_from": "2026-08-01", "date_to": "2026-08-31"}, timeout=60)
        assert r.status_code == 200, r.text[:400]
        ids = sorted(x["settlement_id"] for x in r.json()["data"])
        assert "STL-TEST-001" in ids and "STM-2026-08-16-01" in ids, ids

    def test_empty_range(self, H):
        r = requests.get(LIST, headers=H,
                         params={"date_from": "2026-01-01", "date_to": "2026-01-31"}, timeout=60)
        assert r.status_code == 200
        assert r.json()["data"] == []
        assert r.json()["summary"]["net_payout"] == 0
