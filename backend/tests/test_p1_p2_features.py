"""
P1/P2 Features Backend API Tests
- Portal Saya: Photo upload (POST /api/portal/profile/photo)
- Bank Reconciliation: CSV import (POST /api/finance/bank-recon/sessions/{id}/import-csv)
- Bank Reconciliation: Auto-match (POST /api/finance/bank-recon/sessions/{id}/auto-match)
"""
import pytest
import requests
import os
import io

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://da37-cmt-bridge.preview.emergentagent.com').rstrip('/')

@pytest.fixture(scope="module")
def auth_headers():
    resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "admin@garment.com", "password": "Admin@123"
    })
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json().get("token") or resp.json().get("access_token")
    assert token, "No token returned"
    return {"Authorization": f"Bearer {token}"}


# ── PORTAL SAYA: PHOTO UPLOAD ────────────────────────────────────────

class TestPortalPhotoUpload:
    """Test POST /api/portal/profile/photo endpoint"""
    
    def test_photo_upload_missing_file_returns_422(self, auth_headers):
        """Missing file should return 422 (correct behavior)"""
        r = requests.post(f"{BASE_URL}/api/portal/profile/photo", headers=auth_headers)
        assert r.status_code == 422, f"Expected 422 for missing file, got {r.status_code}: {r.text}"
        print("✓ Photo upload without file returns 422 (correct)")
    
    def test_photo_upload_with_valid_image(self, auth_headers):
        """Upload a valid image file"""
        # Create a minimal valid PNG (1x1 pixel)
        png_data = (
            b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01'
            b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
        )
        files = {'file': ('test_photo.png', io.BytesIO(png_data), 'image/png')}
        r = requests.post(f"{BASE_URL}/api/portal/profile/photo", 
                         headers=auth_headers, files=files)
        assert r.status_code == 200, f"Photo upload failed: {r.status_code} - {r.text}"
        data = r.json()
        assert "foto_url" in data, "Response should contain foto_url"
        assert "message" in data, "Response should contain message"
        print(f"✓ Photo upload successful: {data.get('foto_url')}")
    
    def test_photo_upload_non_image_returns_400(self, auth_headers):
        """Non-image file should return 400"""
        files = {'file': ('test.txt', io.BytesIO(b'not an image'), 'text/plain')}
        r = requests.post(f"{BASE_URL}/api/portal/profile/photo", 
                         headers=auth_headers, files=files)
        assert r.status_code == 400, f"Expected 400 for non-image, got {r.status_code}"
        print("✓ Non-image file rejected with 400")


# ── BANK RECONCILIATION: SESSION & CSV IMPORT ────────────────────────

class TestBankReconciliation:
    """Test Bank Reconciliation endpoints"""
    session_id = None
    
    def test_get_sessions_list(self, auth_headers):
        """GET /api/finance/bank-recon/sessions"""
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/sessions", headers=auth_headers)
        assert r.status_code == 200, f"Failed to get sessions: {r.text}"
        data = r.json()
        assert "items" in data
        assert "total" in data
        print(f"✓ Bank recon sessions list: {data['total']} sessions")
    
    def test_get_summary(self, auth_headers):
        """GET /api/finance/bank-recon/summary"""
        r = requests.get(f"{BASE_URL}/api/finance/bank-recon/summary", headers=auth_headers)
        assert r.status_code == 200, f"Failed to get summary: {r.text}"
        data = r.json()
        assert "total_sessions" in data
        print(f"✓ Bank recon summary: {data['total_sessions']} total sessions")
    
    def test_create_session(self, auth_headers):
        """POST /api/finance/bank-recon/sessions - Create new session"""
        r = requests.post(f"{BASE_URL}/api/finance/bank-recon/sessions", 
                         headers={**auth_headers, "Content-Type": "application/json"},
                         json={
                             "period": "2026-05",
                             "bank_name": "BCA Test",
                             "account_no": "1234567890",
                             "account_name": "PT Test",
                             "opening_balance": 10000000,
                             "closing_balance": 12000000,
                             "notes": "Test session for P1/P2"
                         })
        assert r.status_code == 200, f"Failed to create session: {r.status_code} - {r.text}"
        data = r.json()
        assert "id" in data
        assert data["bank_name"] == "BCA Test"
        TestBankReconciliation.session_id = data["id"]
        print(f"✓ Bank recon session created: {data['id']}")
    
    def test_csv_import_missing_file_returns_422(self, auth_headers):
        """POST /api/finance/bank-recon/sessions/{id}/import-csv without file"""
        assert TestBankReconciliation.session_id, "Session not created"
        r = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/{TestBankReconciliation.session_id}/import-csv",
            headers=auth_headers
        )
        assert r.status_code == 422, f"Expected 422 for missing file, got {r.status_code}: {r.text}"
        print("✓ CSV import without file returns 422 (correct)")
    
    def test_csv_import_with_valid_file(self, auth_headers):
        """POST /api/finance/bank-recon/sessions/{id}/import-csv with valid CSV"""
        assert TestBankReconciliation.session_id, "Session not created"
        
        # Create a valid CSV file
        csv_content = """Tanggal,Keterangan,Debit,Kredit,Referensi
2026-05-01,Transfer dari Client A,5000000,,TRF001
2026-05-03,Bayar Supplier,,2000000,INV002
2026-05-05,Penjualan Produk,3500000,,TRF003
"""
        files = {'file': ('bank_statement.csv', io.BytesIO(csv_content.encode('utf-8')), 'text/csv')}
        r = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/{TestBankReconciliation.session_id}/import-csv",
            headers=auth_headers,
            files=files
        )
        assert r.status_code == 200, f"CSV import failed: {r.status_code} - {r.text}"
        data = r.json()
        assert "imported" in data
        assert data["imported"] > 0, "Should import at least 1 transaction"
        print(f"✓ CSV import successful: {data['imported']} transactions imported")
    
    def test_auto_match_endpoint(self, auth_headers):
        """POST /api/finance/bank-recon/sessions/{id}/auto-match"""
        assert TestBankReconciliation.session_id, "Session not created"
        r = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/{TestBankReconciliation.session_id}/auto-match",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={}
        )
        assert r.status_code == 200, f"Auto-match failed: {r.status_code} - {r.text}"
        data = r.json()
        assert "matched" in data
        assert "attempted" in data
        assert "message" in data
        print(f"✓ Auto-match completed: {data['matched']} matched out of {data['attempted']}")
    
    def test_auto_match_nonexistent_session_returns_404(self, auth_headers):
        """POST /api/finance/bank-recon/sessions/test-id/auto-match with invalid ID"""
        r = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/nonexistent-session-id/auto-match",
            headers={**auth_headers, "Content-Type": "application/json"},
            json={}
        )
        assert r.status_code == 404, f"Expected 404 for non-existent session, got {r.status_code}"
        print("✓ Auto-match with invalid session ID returns 404 (correct)")
    
    def test_csv_import_nonexistent_session_returns_404(self, auth_headers):
        """POST /api/finance/bank-recon/sessions/test-id/import-csv with invalid ID"""
        csv_content = "Tanggal,Keterangan,Debit\n2026-05-01,Test,1000000\n"
        files = {'file': ('test.csv', io.BytesIO(csv_content.encode('utf-8')), 'text/csv')}
        r = requests.post(
            f"{BASE_URL}/api/finance/bank-recon/sessions/nonexistent-session-id/import-csv",
            headers=auth_headers,
            files=files
        )
        assert r.status_code == 404, f"Expected 404 for non-existent session, got {r.status_code}"
        print("✓ CSV import with invalid session ID returns 404 (correct)")
    
    def test_get_session_transactions(self, auth_headers):
        """GET /api/finance/bank-recon/sessions/{id}/transactions"""
        assert TestBankReconciliation.session_id, "Session not created"
        r = requests.get(
            f"{BASE_URL}/api/finance/bank-recon/sessions/{TestBankReconciliation.session_id}/transactions",
            headers=auth_headers
        )
        assert r.status_code == 200, f"Failed to get transactions: {r.text}"
        data = r.json()
        assert "items" in data
        assert "total" in data
        print(f"✓ Session transactions: {data['total']} transactions")
    
    def test_cleanup_delete_session(self, auth_headers):
        """DELETE /api/finance/bank-recon/sessions/{id} - Cleanup"""
        if TestBankReconciliation.session_id:
            r = requests.delete(
                f"{BASE_URL}/api/finance/bank-recon/sessions/{TestBankReconciliation.session_id}",
                headers=auth_headers
            )
            assert r.status_code == 200, f"Failed to delete session: {r.text}"
            print("✓ Test session deleted (cleanup)")
