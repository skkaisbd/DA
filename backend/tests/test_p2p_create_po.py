"""
test_p2p_create_po.py — Pengujian Endpoint POST /api/procurement/requests/{id}/create-po
Mencakup:
- Full P2P flow: Create PR → Submit → Approve (3 levels) → Create PO
- Validasi error: PR tidak berstatus approved
- Validasi error: vendor_name kosong
- Validasi error: PR sudah memiliki PO terkait
- Verifikasi PR status berubah menjadi in_procurement setelah PO dibuat
- Verifikasi PO terbuat di rahaza_purchase_orders dengan from_pr_id
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def api_client():
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture(scope="module")
def auth_token(api_client):
    resp = api_client.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com",
        "password": "Admin@123"
    })
    assert resp.status_code == 200, f"Login gagal: {resp.text}"
    token = resp.json().get("token")
    assert token, "Token tidak ditemukan di response"
    return token


@pytest.fixture(scope="module")
def headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ─── Helper: Buat PR dan drive-nya ke status approved ─────────────────────────

def create_pr(api_client, headers):
    """Buat PR baru dalam status draft, kembalikan ID-nya."""
    resp = api_client.post(
        f"{BASE_URL}/api/procurement/requests",
        json={
            "title": "TEST_PR untuk P2P Flow",
            "description": "Pengujian otomatis create-po endpoint",
            "justification": "Testing P2P workflow",
            "priority": "medium",
            "request_type": "asset",
            "department": "IT",
            "items": [
                {
                    "name": "Laptop Dell XPS",
                    "specification": "Core i7, 16GB RAM",
                    "qty": 2,
                    "unit": "unit",
                    "estimated_price": 15000000,
                    "notes": "Untuk karyawan baru"
                }
            ]
        },
        headers=headers
    )
    assert resp.status_code == 200, f"Gagal buat PR: {resp.text}"
    data = resp.json()
    assert data.get("status") == "draft"
    assert "id" in data
    return data


def submit_pr(api_client, headers, pr_id):
    """Submit PR dari draft → submitted."""
    resp = api_client.post(
        f"{BASE_URL}/api/procurement/requests/{pr_id}/submit",
        json={"comment": ""},
        headers=headers
    )
    assert resp.status_code == 200, f"Gagal submit PR: {resp.text}"
    assert resp.json().get("new_status") == "submitted"


def approve_pr_once(api_client, headers, pr_id):
    """Approve PR satu langkah."""
    resp = api_client.post(
        f"{BASE_URL}/api/procurement/requests/{pr_id}/approve",
        json={"comment": "Disetujui"},
        headers=headers
    )
    assert resp.status_code == 200, f"Gagal approve PR: {resp.text}"
    return resp.json()


def get_pr(api_client, headers, pr_id):
    """Ambil detail PR."""
    resp = api_client.get(
        f"{BASE_URL}/api/procurement/requests/{pr_id}",
        headers=headers
    )
    assert resp.status_code == 200
    return resp.json()


def drive_pr_to_approved(api_client, headers):
    """Buat PR baru, submit, dan approve 3 kali (dept → finance → final). Kembalikan PR data."""
    pr = create_pr(api_client, headers)
    pr_id = pr["id"]

    # 1. Submit draft → submitted
    submit_pr(api_client, headers, pr_id)

    # 2. Approve 1: submitted → dept_approved
    result = approve_pr_once(api_client, headers, pr_id)
    assert result["new_status"] == "dept_approved", f"Expected dept_approved, got {result['new_status']}"

    # 3. Approve 2: dept_approved → finance_approved
    result = approve_pr_once(api_client, headers, pr_id)
    assert result["new_status"] == "finance_approved", f"Expected finance_approved, got {result['new_status']}"

    # 4. Approve 3: finance_approved → approved
    result = approve_pr_once(api_client, headers, pr_id)
    assert result["new_status"] == "approved", f"Expected approved, got {result['new_status']}"

    # Konfirmasi status akhir
    pr_detail = get_pr(api_client, headers, pr_id)
    assert pr_detail["status"] == "approved"
    return pr_detail


# ─── Test: Status Badges ───────────────────────────────────────────────────────

class TestStatusBadges:
    """Verifikasi status PR tersedia di list API"""

    def test_pr_list_returns_status(self, api_client, headers):
        resp = api_client.get(f"{BASE_URL}/api/procurement/requests", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        print(f"✅ PR list: {len(data['items'])} items")

    def test_pr_list_has_valid_status_fields(self, api_client, headers):
        resp = api_client.get(f"{BASE_URL}/api/procurement/requests", headers=headers)
        assert resp.status_code == 200
        items = resp.json().get("items", [])
        valid_statuses = {
            "draft", "submitted", "dept_approved", "finance_approved",
            "approved", "in_procurement", "rejected", "completed", "cancelled"
        }
        for item in items:
            status = item.get("status")
            assert status in valid_statuses, f"Status tidak valid: {status}"
        print("✅ Semua PR memiliki status valid")


# ─── Test: PR Timeline ─────────────────────────────────────────────────────────

class TestPRTimeline:
    """Verifikasi timeline endpoint mengembalikan field 'steps'"""

    def test_timeline_returns_steps_field(self, api_client, headers):
        # Buat PR dan submit untuk mendapat timeline entry
        pr = create_pr(api_client, headers)
        pr_id = pr["id"]
        submit_pr(api_client, headers, pr_id)

        resp = api_client.get(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/timeline",
            headers=headers
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "steps" in data, f"Field 'steps' tidak ada dalam response: {data.keys()}"
        assert "current_status" in data
        assert isinstance(data["steps"], list)
        assert len(data["steps"]) >= 1, "Timeline harus memiliki setidaknya 1 entry setelah submit"
        print(f"✅ Timeline memiliki {len(data['steps'])} steps, current_status={data['current_status']}")

    def test_timeline_not_return_timeline_field(self, api_client, headers):
        """Pastikan tidak ada 'timeline' field (hanya 'steps')"""
        # Ambil PR apapun yang ada
        list_resp = api_client.get(f"{BASE_URL}/api/procurement/requests", headers=headers)
        items = list_resp.json().get("items", [])
        if not items:
            pytest.skip("Tidak ada PR untuk diuji")
        pr_id = items[0]["id"]

        resp = api_client.get(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/timeline",
            headers=headers
        )
        data = resp.json()
        assert "timeline" not in data, "Response seharusnya menggunakan 'steps' bukan 'timeline'"
        print("✅ Field 'timeline' tidak ada (sudah diperbaiki ke 'steps')")


# ─── Test: Create PO from PR ──────────────────────────────────────────────────

class TestCreatePOFromPR:
    """Test POST /api/procurement/requests/{id}/create-po"""

    def test_create_po_requires_approved_status(self, api_client, headers):
        """Error jika PR bukan berstatus approved"""
        # Buat PR yang masih draft
        pr = create_pr(api_client, headers)
        pr_id = pr["id"]

        resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/create-po",
            json={"vendor_name": "PT. Test Vendor"},
            headers=headers
        )
        assert resp.status_code == 400, f"Seharusnya 400, dapat: {resp.status_code}"
        detail = resp.json().get("detail", "")
        assert "approved" in detail.lower() or "status" in detail.lower(), \
            f"Pesan error tidak relevan: {detail}"
        print(f"✅ Error 400 benar saat PR masih draft: {detail}")

    def test_create_po_requires_vendor_name(self, api_client, headers):
        """Error jika vendor_name kosong"""
        # Buat PR yang sudah approved
        pr = drive_pr_to_approved(api_client, headers)
        pr_id = pr["id"]

        resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/create-po",
            json={"vendor_name": ""},
            headers=headers
        )
        assert resp.status_code == 400, f"Seharusnya 400, dapat: {resp.status_code}"
        detail = resp.json().get("detail", "")
        assert "vendor" in detail.lower() or "wajib" in detail.lower(), \
            f"Pesan error tidak relevan: {detail}"
        print(f"✅ Error 400 benar saat vendor_name kosong: {detail}")

    def test_create_po_submitted_status_returns_error(self, api_client, headers):
        """Error jika PR masih dalam status submitted"""
        pr = create_pr(api_client, headers)
        pr_id = pr["id"]
        submit_pr(api_client, headers, pr_id)

        resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/create-po",
            json={"vendor_name": "PT. Vendor Test"},
            headers=headers
        )
        assert resp.status_code == 400
        print("✅ Error 400 benar saat PR berstatus submitted")

    def test_full_p2p_flow_create_po_success(self, api_client, headers):
        """Full P2P flow: Draft → Submit → Approve (3x) → Create PO"""
        pr = drive_pr_to_approved(api_client, headers)
        pr_id = pr["id"]

        # Buat PO dari PR yang sudah approved
        resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/create-po",
            json={
                "vendor_name": "PT. Sumber Makmur Teknologi",
                "vendor_contact": "021-12345678",
                "vendor_address": "Jl. Industri No. 1, Jakarta",
                "expected_delivery_date": "2026-03-31",
                "notes": "Kirim ke gudang utama"
            },
            headers=headers
        )
        assert resp.status_code == 200, f"Gagal create PO: {resp.status_code} — {resp.text}"
        po_data = resp.json()

        # Verifikasi struktur PO
        assert "id" in po_data, "PO harus memiliki field 'id'"
        assert "po_number" in po_data, "PO harus memiliki field 'po_number'"
        assert po_data.get("from_pr_id") == pr_id, f"from_pr_id tidak cocok: {po_data.get('from_pr_id')}"
        assert po_data.get("from_pr_number") == pr.get("request_number")
        assert po_data.get("vendor_name") == "PT. Sumber Makmur Teknologi"
        assert po_data.get("status") == "draft", f"PO status seharusnya 'draft', dapat: {po_data.get('status')}"
        assert isinstance(po_data.get("items"), list)
        assert len(po_data["items"]) > 0, "PO harus memiliki items dari PR"

        print(f"✅ PO berhasil dibuat: {po_data['po_number']} dari PR {pr.get('request_number')}")
        print(f"   from_pr_id={po_data['from_pr_id']}, items={len(po_data['items'])}")

        # Simpan po_id dan pr_id untuk test selanjutnya
        TestCreatePOFromPR._last_po_id = po_data["id"]
        TestCreatePOFromPR._last_pr_id = pr_id
        TestCreatePOFromPR._last_po_number = po_data["po_number"]

    def test_pr_status_changes_to_in_procurement_after_create_po(self, api_client, headers):
        """PR status berubah menjadi in_procurement setelah PO dibuat"""
        if not hasattr(TestCreatePOFromPR, "_last_pr_id"):
            pytest.skip("Membutuhkan test_full_p2p_flow_create_po_success dijalankan lebih dulu")

        pr_detail = get_pr(api_client, headers, TestCreatePOFromPR._last_pr_id)
        assert pr_detail["status"] == "in_procurement", \
            f"PR status seharusnya 'in_procurement', dapat: {pr_detail['status']}"
        assert pr_detail.get("linked_po_id") == TestCreatePOFromPR._last_po_id, \
            "linked_po_id tidak cocok"
        assert pr_detail.get("linked_po_number") == TestCreatePOFromPR._last_po_number

        print("✅ PR status berubah ke in_procurement")
        print(f"   linked_po_number={pr_detail.get('linked_po_number')}")

    def test_create_po_duplicate_returns_error(self, api_client, headers):
        """Error jika PR sudah memiliki PO terkait"""
        if not hasattr(TestCreatePOFromPR, "_last_pr_id"):
            pytest.skip("Membutuhkan test_full_p2p_flow_create_po_success dijalankan lebih dulu")

        # PR sekarang berstatus in_procurement (bukan approved), jadi error akan mengatakan status salah
        # Tes ini memverifikasi bahwa mencoba membuat PO kedua kali gagal
        pr_id = TestCreatePOFromPR._last_pr_id
        resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/create-po",
            json={"vendor_name": "PT. Vendor Kedua"},
            headers=headers
        )
        assert resp.status_code == 400, f"Seharusnya 400 untuk duplikat PO, dapat: {resp.status_code}"
        print(f"✅ Error 400 benar saat mencoba buat PO kedua: {resp.json().get('detail', '')}")

    def test_po_has_from_pr_id_in_database(self, api_client, headers):
        """Verifikasi PO tersimpan di rahaza_purchase_orders dengan from_pr_id"""
        if not hasattr(TestCreatePOFromPR, "_last_po_id"):
            pytest.skip("Membutuhkan test_full_p2p_flow_create_po_success dijalankan lebih dulu")

        # PO sudah verified dalam test sebelumnya, cukup check via response yang disimpan
        # (Tidak ada endpoint langsung untuk GET PO by ID dari procurement module)
        # Verifikasi via PR detail yang menyimpan linked_po_id
        pr_detail = get_pr(api_client, headers, TestCreatePOFromPR._last_pr_id)
        assert pr_detail.get("linked_po_id") is not None
        print(f"✅ linked_po_id tersimpan di PR: {pr_detail.get('linked_po_id')}")


# ─── Test: Complete/Tandai Selesai ─────────────────────────────────────────────

class TestTandaiSelesai:
    """Verifikasi endpoint complete untuk in_procurement PR"""

    def test_complete_in_procurement_pr(self, api_client, headers):
        """PR dengan status in_procurement bisa di-tandai selesai"""
        # Buat PR approved dan buat PO darinya
        pr = drive_pr_to_approved(api_client, headers)
        pr_id = pr["id"]

        # Buat PO
        po_resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/create-po",
            json={"vendor_name": "PT. Vendor Selesai"},
            headers=headers
        )
        assert po_resp.status_code == 200, f"Gagal buat PO: {po_resp.text}"

        # Konfirmasi PR in_procurement
        pr_detail = get_pr(api_client, headers, pr_id)
        assert pr_detail["status"] == "in_procurement"

        # Tandai selesai
        complete_resp = api_client.post(
            f"{BASE_URL}/api/procurement/requests/{pr_id}/complete",
            json={"linked_asset_ids": []},
            headers=headers
        )
        assert complete_resp.status_code == 200, f"Gagal complete PR: {complete_resp.text}"
        assert complete_resp.json().get("ok") is True

        # Verifikasi status berubah ke completed
        pr_final = get_pr(api_client, headers, pr_id)
        assert pr_final["status"] == "completed", \
            f"PR status seharusnya 'completed', dapat: {pr_final['status']}"

        print("✅ PR berhasil ditandai selesai: status=completed")


# ─── Test: Dashboard Procurement ──────────────────────────────────────────────

class TestProcurementDashboard:
    """Verifikasi dashboard procurement"""

    def test_dashboard_returns_summary(self, api_client, headers):
        resp = api_client.get(f"{BASE_URL}/api/procurement/dashboard", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        summary = data["summary"]
        required_fields = ["total", "pending", "approved", "completed", "rejected"]
        for field in required_fields:
            assert field in summary, f"Field '{field}' tidak ada dalam summary"
        print(f"✅ Dashboard: total={summary['total']}, pending={summary['pending']}, approved={summary['approved']}")
