"""Sesi #40 — audit Portal Marketing.

Cakupan:
  * modul marketing_data_import : GET /source-groups, GET /source-types, POST /detect
  * modul marketing_settlements : lifecycle jurnal + _je_still_binding (void ⇒ boleh edit/hapus)
"""
import os
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
base_url = os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")
if not base_url:
    raise RuntimeError("REACT_APP_BACKEND_URL missing")
BASE_URL = base_url.rstrip("/")
SAMPLES = Path("/app/samples/marketplace_2026")


def _login(email, password):
    r = requests.post(f"{BASE_URL}/api/auth/login",
                      json={"email": email, "password": password}, timeout=60)
    if r.status_code != 200:
        pytest.fail(f"login {email} -> {r.status_code}: {r.text[:300]}")
    d = r.json()
    tok = d.get("token") or d.get("access_token") or (d.get("data") or {}).get("token")
    assert tok, f"no token in login response: {d}"
    return tok


@pytest.fixture(scope="session")
def admin_h():
    return {"Authorization": f"Bearer {_login('admin@garment.com', 'Admin@123')}"}


@pytest.fixture(scope="session")
def fin_h():
    return {"Authorization": f"Bearer {_login('finance@dewiaditya.id', 'Dewi@123')}"}


# ───────────────────────── modul: marketing_data_import ─────────────────────
class TestImportGroups:
    def test_source_groups_6_kelompok_22_jenis(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/marketing/data-import/source-groups",
                         headers=admin_h, timeout=60)
        assert r.status_code == 200, r.text[:300]
        d = r.json()
        groups = d["groups"]
        keys = [g["key"] for g in groups]
        assert len(groups) == 6, keys
        for k in ["pesanan_penjualan", "iklan", "konten", "live",
                  "after_sales", "katalog_lain"]:
            assert k in keys, f"kelompok {k} hilang: {keys}"
        # 22 jenis TOTAL di katalog; 1 di antaranya deprecated/hidden -> total_types=21
        assert d["total_types"] + d["hidden_types"] == 22, (d["total_types"], d["hidden_types"])
        for g in groups:
            assert g["type_count"] > 0
            assert g.get("label")

    def test_source_types_count(self, admin_h):
        r = requests.get(f"{BASE_URL}/api/marketing/data-import/source-types",
                         headers=admin_h, timeout=60)
        assert r.status_code == 200
        types = r.json()["source_types"]
        assert len(types) >= 22
        assert all("group_key" in t for t in types)
        assert any(t["key"] == "marketplace_orders" for t in types)


class TestDetect:
    def test_detect_shopee_orders(self, admin_h):
        f = SAMPLES / "order_pesanan_shopee.xlsx"
        assert f.exists()
        with f.open("rb") as fh:
            r = requests.post(f"{BASE_URL}/api/marketing/data-import/detect",
                              headers=admin_h, files={"file": (f.name, fh)}, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["row_count"] == 154, d["row_count"]
        assert (d["platform"] or {}).get("platform", "").lower() == "shopee", d["platform"]
        rank = d["ranking"]
        assert rank, "ranking kosong"
        best = d["best"]
        assert (best or {}).get("source_type") == "marketplace_orders", best
        # bukti ikut serta
        assert "matched_columns" in rank[0] or "score" in rank[0], rank[0]
        assert d["matching_accounts"], "tidak ada toko shopee yang cocok"
        assert len(d["raw_preview"]) > 0

    def test_detect_empty_file_flagged(self, admin_h):
        f = SAMPLES / "retur_refund_shopee.xls"
        assert f.exists()
        with f.open("rb") as fh:
            r = requests.post(f"{BASE_URL}/api/marketing/data-import/detect",
                              headers=admin_h, files={"file": (f.name, fh)}, timeout=120)
        assert r.status_code == 200, r.text[:400]
        d = r.json()
        assert d["row_count"] == 0, d["row_count"]
        assert len(d["headers"]) > 0, "header seharusnya terbaca meski tanpa baris"

    def test_detect_rejects_bad_extension(self, admin_h):
        r = requests.post(f"{BASE_URL}/api/marketing/data-import/detect",
                          headers=admin_h,
                          files={"file": ("x.pdf", b"%PDF-1.4")}, timeout=60)
        assert r.status_code == 400, r.status_code

    def test_detect_requires_auth(self):
        f = SAMPLES / "ads_shopee.csv"
        with f.open("rb") as fh:
            r = requests.post(f"{BASE_URL}/api/marketing/data-import/detect",
                              files={"file": (f.name, fh)}, timeout=60)
        assert r.status_code in (401, 403), r.status_code


# ───────────────────────── modul: marketing_settlements ─────────────────────
@pytest.fixture(scope="class")
def shopee_account(fin_h):
    r = requests.get(f"{BASE_URL}/api/marketing/accounts", headers=fin_h,
                     params={"status": "active"}, timeout=60)
    assert r.status_code == 200, r.text[:300]
    body = r.json()
    rows = body if isinstance(body, list) else body.get("accounts") or body.get("data") or []
    cand = [a for a in rows if str(a.get("platform", "")).lower() == "shopee"]
    assert cand, f"tidak ada akun shopee aktif: {[a.get('account_name') for a in rows]}"
    return cand[0]


class TestSettlementVoidUnlock:
    created = []

    def test_lifecycle_void_unlocks_edit_and_delete(self, fin_h, shopee_account):
        sid_ext = f"SET-QA-{uuid.uuid4().hex[:6].upper()}"
        payload = {
            "account_id": shopee_account["id"],
            "platform": shopee_account.get("platform") or "shopee",
            "settlement_id": sid_ext,
            "settlement_date": "2026-06-30",
            "gross_sales": 10_000_000,
            "platform_commission": 500_000,
            "net_payout": 9_500_000,
            "notes": "TEST_QA sesi40",
        }
        r = requests.post(f"{BASE_URL}/api/marketing/settlements", headers=fin_h,
                          json=payload, timeout=60)
        assert r.status_code in (200, 201), r.text[:400]
        doc = r.json().get("data") or r.json()
        sid = doc["id"]
        self.created.append(sid)
        assert doc["settlement_id"] == sid_ext
        assert float(doc["gross_sales"]) == 10_000_000
        assert float(doc["net_payout"]) == 9_500_000

        # dedupe: settlement_id sama harus ditolak
        r = requests.post(f"{BASE_URL}/api/marketing/settlements", headers=fin_h,
                          json=payload, timeout=60)
        assert r.status_code in (400, 409), f"dedupe gagal: {r.status_code} {r.text[:200]}"

        # jurnal draft
        r = requests.post(f"{BASE_URL}/api/marketing/settlements/{sid}/journal",
                          headers=fin_h, timeout=90)
        assert r.status_code == 200, r.text[:400]
        g = requests.get(f"{BASE_URL}/api/marketing/settlements/{sid}",
                         headers=fin_h, timeout=60).json()
        det = g.get("data") or g
        je_id = det.get("je_id")
        assert je_id, f"je_id kosong setelah /journal: {det}"

        # posting
        r = requests.post(f"{BASE_URL}/api/marketing/settlements/{sid}/post",
                          headers=fin_h, timeout=90)
        assert r.status_code == 200, r.text[:400]

        # terkunci
        r = requests.put(f"{BASE_URL}/api/marketing/settlements/{sid}", headers=fin_h,
                         json={**payload, "gross_sales": 11_000_000,
                               "net_payout": 10_500_000}, timeout=60)
        assert r.status_code == 400, f"PUT harus 400 saat jurnal aktif, dapat {r.status_code}"
        r = requests.delete(f"{BASE_URL}/api/marketing/settlements/{sid}",
                            headers=fin_h, timeout=60)
        assert r.status_code == 400, f"DELETE harus 400 saat jurnal aktif, dapat {r.status_code}"

        d = requests.get(f"{BASE_URL}/api/marketing/settlements/{sid}",
                         headers=fin_h, timeout=60).json()
        can = d.get("can") or {}
        assert can.get("edit") is False, can

        # void jurnalnya
        r = requests.post(f"{BASE_URL}/api/rahaza/journals/{je_id}/void", headers=fin_h,
                          json={"reason": "TEST_QA sesi40"}, timeout=90)
        assert r.status_code == 200, r.text[:400]

        # sekarang boleh diubah
        r = requests.put(f"{BASE_URL}/api/marketing/settlements/{sid}", headers=fin_h,
                         json={**payload, "gross_sales": 11_000_000,
                               "net_payout": 10_500_000}, timeout=60)
        assert r.status_code == 200, f"PUT setelah void harus 200: {r.status_code} {r.text[:300]}"

        d = requests.get(f"{BASE_URL}/api/marketing/settlements/{sid}",
                         headers=fin_h, timeout=60).json()
        det = d.get("data") or d
        assert det.get("je_id") is None, f"je_id harus null setelah void+edit: {det.get('je_id')}"
        assert (d.get("can") or {}).get("edit") is True, d.get("can")
        assert float(det["gross_sales"]) == 11_000_000

        # dan boleh dihapus
        r = requests.delete(f"{BASE_URL}/api/marketing/settlements/{sid}",
                            headers=fin_h, timeout=60)
        assert r.status_code == 200, f"DELETE setelah void harus 200: {r.status_code}"
        self.created.remove(sid)
        g = requests.get(f"{BASE_URL}/api/marketing/settlements/{sid}",
                         headers=fin_h, timeout=60)
        assert g.status_code == 404, g.status_code

    def test_list_kosong_setelah_pembersihan(self, fin_h):
        r = requests.get(f"{BASE_URL}/api/marketing/settlements", headers=fin_h, timeout=60)
        assert r.status_code == 200, r.text[:300]
        b = r.json()
        rows = b if isinstance(b, list) else b.get("data") or b.get("settlements") or []
        leftovers = [x.get("settlement_id") for x in rows]
        assert "SET-TEST-001" not in leftovers, leftovers
        assert not [x for x in leftovers if str(x).startswith("SET-QA-")], leftovers

    @pytest.fixture(scope="class", autouse=True)
    def _cleanup(self, fin_h):
        yield
        for sid in list(self.created):
            g = requests.get(f"{BASE_URL}/api/marketing/settlements/{sid}",
                             headers=fin_h, timeout=60)
            if g.status_code == 200:
                det = g.json().get("data") or g.json()
                je_id = det.get("je_id")
                if je_id:
                    requests.post(f"{BASE_URL}/api/rahaza/journals/{je_id}/void",
                                  headers=fin_h, json={"reason": "TEST_QA cleanup"},
                                  timeout=60)
            requests.delete(f"{BASE_URL}/api/marketing/settlements/{sid}",
                            headers=fin_h, timeout=60)
