"""
Comprehensive backend test for Fase 5 Material Requirements (MRP-lite) feature.
Tests all scenarios from the review request using PUBLIC endpoint.
"""
import requests
import sys

# Use PUBLIC endpoint from frontend .env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
API_PREFIX = "/api"

# Test credentials
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# Seed data IDs
PO_ID = "po-int-demo-1"
MODEL_ID = "int-demo-model-1"
SIZE_ID = "a3539e1f-06dc-4462-b5e9-9e6958a5e8ce"  # Size L

class TestResults:
    def __init__(self):
        self.total = 0
        self.passed = 0
        self.failed = 0
        self.errors = []
    
    def add_pass(self, test_name):
        self.total += 1
        self.passed += 1
        print(f"✅ PASS: {test_name}")
    
    def add_fail(self, test_name, reason):
        self.total += 1
        self.failed += 1
        error_msg = f"❌ FAIL: {test_name} - {reason}"
        print(error_msg)
        self.errors.append(error_msg)
    
    def summary(self):
        print("\n" + "="*60)
        print(f"TEST SUMMARY: {self.passed}/{self.total} passed")
        if self.failed > 0:
            print(f"\n{self.failed} FAILED TESTS:")
            for error in self.errors:
                print(f"  {error}")
        print("="*60)
        return self.failed == 0

def get_token():
    """Login and get auth token"""
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        if response.status_code == 200:
            return response.json().get("token")
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text[:200]}")
            return None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def test_po_mode(token, results):
    """Test PO mode with po-int-demo-1"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            headers=headers,
            json={"po_id": PO_ID},
            timeout=30
        )
        
        if response.status_code != 200:
            results.add_fail("PO mode - status code", f"Expected 200, got {response.status_code}: {response.text[:200]}")
            return
        
        data = response.json()
        
        # Check source
        if data.get("source") != "po":
            results.add_fail("PO mode - source", f"Expected 'po', got '{data.get('source')}'")
            return
        
        # Check PO number
        po_number = data.get("po", {}).get("po_number")
        if po_number != "PO-INT-DEMO-1":
            results.add_fail("PO mode - PO number", f"Expected 'PO-INT-DEMO-1', got '{po_number}'")
            return
        
        # Check aggregated materials
        aggregated = data.get("aggregated", [])
        if len(aggregated) < 1:
            results.add_fail("PO mode - aggregated materials", f"Expected >=1 material, got {len(aggregated)}")
            return
        
        # Check totals
        totals = data.get("totals", {})
        # FASE 11: nama kanonik `total_material_kg` (alias legacy `total_yarn_kg` sudah
        # tidak ditulis lagi — fallback dipertahankan agar tes lama tetap jalan di DB lama).
        total_yarn_kg = totals.get("total_material_kg", totals.get("total_yarn_kg", 0))
        grand_qty_pcs = totals.get("grand_qty_pcs", 0)
        
        # Verify yarn quantity (should be around 50 kg for qty 200)
        if total_yarn_kg < 40 or total_yarn_kg > 60:
            results.add_fail("PO mode - yarn quantity", f"Expected ~50 kg, got {total_yarn_kg}")
            return
        
        # Verify total production quantity
        if grand_qty_pcs != 200:
            results.add_fail("PO mode - total qty", f"Expected 200 pcs, got {grand_qty_pcs}")
            return
        
        results.add_pass("PO mode - basic flow")
        
    except Exception as e:
        results.add_fail("PO mode - exception", str(e))

def test_manual_mode(token, results):
    """Test manual lines mode with rounding and stock inclusion"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            headers=headers,
            json={
                "lines": [
                    {
                        "model_id": MODEL_ID,
                        "size_id": SIZE_ID,
                        "qty_pcs": 100
                    }
                ],
                "rounding": "ceil",
                "include_stock": True
            },
            timeout=30
        )
        
        if response.status_code != 200:
            results.add_fail("Manual mode - status code", f"Expected 200, got {response.status_code}: {response.text[:200]}")
            return
        
        data = response.json()
        
        # Check source
        if data.get("source") != "lines":
            results.add_fail("Manual mode - source", f"Expected 'lines', got '{data.get('source')}'")
            return
        
        # Check lines resolved
        totals = data.get("totals", {})
        lines_resolved_count = totals.get("lines_resolved_count", 0)
        if lines_resolved_count != 1:
            results.add_fail("Manual mode - lines resolved", f"Expected 1, got {lines_resolved_count}")
            return
        
        # Check aggregated computed
        aggregated = data.get("aggregated", [])
        if len(aggregated) < 1:
            results.add_fail("Manual mode - aggregated", f"Expected >=1 material, got {len(aggregated)}")
            return
        
        results.add_pass("Manual mode - basic flow")
        
    except Exception as e:
        results.add_fail("Manual mode - exception", str(e))

def test_cross_line_aggregation(token, results):
    """Test that same material from multiple lines is summed, not duplicated"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            headers=headers,
            json={
                "lines": [
                    {
                        "model_id": MODEL_ID,
                        "size_id": SIZE_ID,
                        "qty_pcs": 100
                    },
                    {
                        "model_id": MODEL_ID,
                        "size_id": SIZE_ID,
                        "qty_pcs": 100
                    }
                ]
            },
            timeout=30
        )
        
        if response.status_code != 200:
            results.add_fail("Cross-line aggregation - status code", f"Expected 200, got {response.status_code}")
            return
        
        data = response.json()
        aggregated = data.get("aggregated", [])
        
        # Find Benang Cotton material
        benang_materials = [m for m in aggregated if "Benang" in m.get("name", "") or "Cotton" in m.get("name", "")]
        
        if len(benang_materials) == 0:
            results.add_fail("Cross-line aggregation - no benang found", "Expected Benang Cotton material")
            return
        
        # Check that materials are aggregated (should have total for 200 pcs, not separate entries)
        # For 200 pcs at 0.25 kg/pcs = 50 kg total
        benang = benang_materials[0]
        total_required = benang.get("total_required", 0)
        
        # Should be around 50 kg (0.25 * 200)
        if total_required < 40 or total_required > 60:
            results.add_fail("Cross-line aggregation - total", f"Expected ~50 kg for 200 pcs, got {total_required}")
            return
        
        results.add_pass("Cross-line aggregation - materials summed correctly")
        
    except Exception as e:
        results.add_fail("Cross-line aggregation - exception", str(e))

def test_validation_empty_body(token, results):
    """Test validation: empty body should return 400"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            headers=headers,
            json={},
            timeout=30
        )
        
        if response.status_code == 400:
            results.add_pass("Validation - empty body returns 400")
        else:
            results.add_fail("Validation - empty body", f"Expected 400, got {response.status_code}")
        
    except Exception as e:
        results.add_fail("Validation - empty body exception", str(e))

def test_validation_nonexistent_po(token, results):
    """Test validation: nonexistent PO should return 404"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            headers=headers,
            json={"po_id": "nonexistent-po-id-12345"},
            timeout=30
        )
        
        if response.status_code == 404:
            results.add_pass("Validation - nonexistent PO returns 404")
        else:
            results.add_fail("Validation - nonexistent PO", f"Expected 404, got {response.status_code}")
        
    except Exception as e:
        results.add_fail("Validation - nonexistent PO exception", str(e))

def test_validation_no_bom(token, results):
    """Test validation: line with size that has no BOM should be in lines_without_bom"""
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            headers=headers,
            json={
                "lines": [
                    {
                        "model_id": MODEL_ID,
                        "size_id": "nonexistent-size-id-12345",
                        "qty_pcs": 50
                    }
                ]
            },
            timeout=30
        )
        
        if response.status_code != 200:
            results.add_fail("Validation - no BOM status", f"Expected 200, got {response.status_code}")
            return
        
        data = response.json()
        lines_without_bom = data.get("lines_without_bom", [])
        
        if len(lines_without_bom) > 0:
            results.add_pass("Validation - line without BOM handled correctly")
        else:
            results.add_fail("Validation - no BOM", "Expected line in lines_without_bom")
        
    except Exception as e:
        results.add_fail("Validation - no BOM exception", str(e))

def test_auth_unauthorized(results):
    """Test auth: request without Authorization header should return 401/403"""
    try:
        response = requests.post(
            f"{BASE_URL}{API_PREFIX}/rahaza/material-requirements",
            json={"po_id": PO_ID},
            timeout=30
        )
        
        if response.status_code in [401, 403]:
            results.add_pass("Auth - unauthorized request returns 401/403")
        else:
            results.add_fail("Auth - unauthorized", f"Expected 401/403, got {response.status_code}")
        
    except Exception as e:
        results.add_fail("Auth - unauthorized exception", str(e))

def main():
    print("="*60)
    print("FASE 5 MATERIAL REQUIREMENTS (MRP-lite) - BACKEND TEST")
    print(f"Testing against: {BASE_URL}")
    print("="*60 + "\n")
    
    results = TestResults()
    
    # Get auth token
    print("🔐 Logging in...")
    token = get_token()
    if not token:
        print("❌ Failed to get auth token. Aborting tests.")
        return 1
    print(f"✅ Logged in successfully\n")
    
    # Run tests
    print("Running backend tests...\n")
    
    test_po_mode(token, results)
    test_manual_mode(token, results)
    test_cross_line_aggregation(token, results)
    test_validation_empty_body(token, results)
    test_validation_nonexistent_po(token, results)
    test_validation_no_bom(token, results)
    test_auth_unauthorized(results)
    
    # Print summary
    success = results.summary()
    
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
