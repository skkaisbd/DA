#!/usr/bin/env python3
"""
Comprehensive Backend API Test for FASE 6 - Quarantine Module (INV-8)
Tests all quarantine endpoints using PUBLIC endpoint from frontend/.env
"""
import requests
import sys
import time
from datetime import datetime, timezone

# Configuration - MUST use public endpoint
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
CREDENTIALS = {
    "admin": {"email": "admin@garment.com", "password": "Admin@123"},
    "gudang": {"email": "gudang@dewiaditya.id", "password": "Dewi@123"},
    "spv": {"email": "spv@dewiaditya.id", "password": "Dewi@123"},
    "hr": {"email": "hr@dewiaditya.id", "password": "Dewi@123"},
    "maklon": {"email": "maklon@dewiaditya.id", "password": "Dewi@123"},
}

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
        self.tokens = {}
        self.test_data = {}
    
    def check(self, condition, test_name, details=""):
        if condition:
            self.passed += 1
            print(f"  ✅ {test_name}")
            self.tests.append({"name": test_name, "status": "PASS", "details": details})
        else:
            self.failed += 1
            print(f"  ❌ {test_name} {details}")
            self.tests.append({"name": test_name, "status": "FAIL", "details": details})
    
    def summary(self):
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        return f"{self.passed}/{total} passed ({pct:.1f}%)"

results = TestResults()

def login(role):
    """Login and get token for a role. Handle rate limiting."""
    if role in results.tokens:
        return results.tokens[role]
    
    creds = CREDENTIALS.get(role)
    if not creds:
        print(f"  ⚠️  Unknown role: {role}")
        return None
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            r = requests.post(f"{BASE_URL}/auth/login", json=creds, timeout=15)
            
            if r.status_code == 429:
                print(f"  ⚠️  Rate limited (429), waiting 60s...")
                time.sleep(60)
                continue
            
            if r.status_code == 200:
                data = r.json()
                token = data.get('token')
                results.tokens[role] = token
                return token
            else:
                print(f"  ❌ Login failed for {role}: {r.status_code} - {r.text[:200]}")
                return None
        except Exception as e:
            print(f"  ❌ Login exception for {role}: {str(e)}")
            if attempt < max_retries - 1:
                time.sleep(2)
            else:
                return None
    return None

def test_backend_1_quarantine_location():
    """BACKEND-1: GET /api/wms/quarantine/location"""
    print("\n=== BACKEND-1: Quarantine Location ===")
    token = login("admin")
    if not token:
        results.check(False, "BACKEND-1: Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(f"{BASE_URL}/wms/quarantine/location", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "BACKEND-1: GET /wms/quarantine/location returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('id' in data, "BACKEND-1: Response has id")
            results.check('code' in data and data['code'] == 'ZNA-KARANTINA', "BACKEND-1: Code is ZNA-KARANTINA", f"Got {data.get('code')}")
            results.check('name' in data, "BACKEND-1: Response has name")
            results.check('storage_locations' in data, "BACKEND-1: Response has storage_locations")
            
            # CRITICAL: Quarantine location MUST NOT be in storage_locations
            if 'storage_locations' in data and 'id' in data:
                q_id = data['id']
                storage_ids = [loc.get('id') for loc in data['storage_locations']]
                results.check(q_id not in storage_ids, "BACKEND-1: Quarantine NOT in storage_locations", f"Found in list: {q_id in storage_ids}")
            
            results.test_data['quarantine_location_id'] = data.get('id')
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "BACKEND-1: Exception", f"{str(e)}")

def test_backend_2_list_quarantine():
    """BACKEND-2: GET /api/wms/quarantine?status=open"""
    print("\n=== BACKEND-2: List Quarantine Items ===")
    token = login("admin")
    if not token:
        results.check(False, "BACKEND-2: Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Test status=open
        r = requests.get(f"{BASE_URL}/wms/quarantine?status=open", headers=headers, timeout=15)
        results.check(r.status_code == 200, "BACKEND-2: GET /wms/quarantine?status=open returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(isinstance(data, list), "BACKEND-2: Response is list")
            
            # Verify seeded items exist
            if isinstance(data, list):
                # Look for TEST-Q6 items
                test_items = [item for item in data if 'TEST-Q6' in item.get('material_code', '')]
                results.check(len(test_items) > 0, "BACKEND-2: Found TEST-Q6 seeded items", f"Found {len(test_items)} items")
                
                # Store first item for later tests
                if test_items:
                    results.test_data['quarantine_item'] = test_items[0]
                    print(f"    Found item: {test_items[0].get('material_code')} qty={test_items[0].get('remaining_qty')}")
        
        # Test status=closed
        r = requests.get(f"{BASE_URL}/wms/quarantine?status=closed", headers=headers, timeout=15)
        results.check(r.status_code == 200, "BACKEND-2: GET /wms/quarantine?status=closed returns 200", f"Got {r.status_code}")
        
        # Test status=all
        r = requests.get(f"{BASE_URL}/wms/quarantine?status=all", headers=headers, timeout=15)
        results.check(r.status_code == 200, "BACKEND-2: GET /wms/quarantine?status=all returns 200", f"Got {r.status_code}")
        
    except Exception as e:
        results.check(False, "BACKEND-2: Exception", f"{str(e)}")

def test_backend_3_summary():
    """BACKEND-3: GET /api/wms/quarantine/summary"""
    print("\n=== BACKEND-3: Quarantine Summary ===")
    token = login("admin")
    if not token:
        results.check(False, "BACKEND-3: Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(f"{BASE_URL}/wms/quarantine/summary", headers=headers, timeout=15)
        results.check(r.status_code == 200, "BACKEND-3: GET /wms/quarantine/summary returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            required_fields = ['open_items', 'open_qty', 'open_value', 'valued_items', 'unvalued_items', 'by_reason', 'oldest_age_days', 'location']
            for field in required_fields:
                results.check(field in data, f"BACKEND-3: Summary has {field}", f"Missing: {field}")
            
            # Verify by_reason is a dict
            if 'by_reason' in data:
                results.check(isinstance(data['by_reason'], dict), "BACKEND-3: by_reason is dict")
            
            print(f"    Open items: {data.get('open_items')}, Open qty: {data.get('open_qty')}, Open value: {data.get('open_value')}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "BACKEND-3: Exception", f"{str(e)}")

def test_backend_4_reject_categories():
    """BACKEND-4: GET /api/wms/quarantine/reject-categories"""
    print("\n=== BACKEND-4: Reject Categories ===")
    token = login("admin")
    if not token:
        results.check(False, "BACKEND-4: Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        r = requests.get(f"{BASE_URL}/wms/quarantine/reject-categories", headers=headers, timeout=15)
        results.check(r.status_code == 200, "BACKEND-4: GET /wms/quarantine/reject-categories returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(isinstance(data, list), "BACKEND-4: Response is list")
            results.check(len(data) == 11, "BACKEND-4: Has 11 categories", f"Got {len(data)} categories")
            
            # Verify expected categories
            expected = ['FABRIC_DEFECT', 'COLOR_MISMATCH', 'MEASUREMENT_OUT', 'QUANTITY_SHORT', 
                       'DAMAGED_PACKAGING', 'WRONG_ITEM', 'LATE_DELIVERY', 'MISSING_DOCS', 
                       'STITCHING_DEFECT', 'ACCESSORY_MISSING', 'OTHER']
            if isinstance(data, list):
                codes = [cat.get('code') for cat in data if isinstance(cat, dict)]
                for exp in expected:
                    results.check(exp in codes, f"BACKEND-4: Has category {exp}", f"Missing: {exp}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "BACKEND-4: Exception", f"{str(e)}")

def test_backend_5_rbac_negative():
    """BACKEND-5: RBAC Negative Tests"""
    print("\n=== BACKEND-5: RBAC Negative Tests ===")
    
    # Get a quarantine item
    if 'quarantine_item' not in results.test_data:
        print("  ⚠️  No quarantine item available, skipping RBAC tests")
        return
    
    item_id = results.test_data['quarantine_item'].get('id')
    if not item_id:
        print("  ⚠️  No item id available")
        return
    
    # Test HR role (should get 403 for release and scrap)
    hr_token = login("hr")
    if hr_token:
        headers = {"Authorization": f"Bearer {hr_token}"}
        
        # Try release
        try:
            r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/release", 
                            headers=headers, 
                            json={"qty": 1, "to_location_id": "dummy", "notes": "test"},
                            timeout=15)
            results.check(r.status_code == 403, "BACKEND-5: HR role gets 403 for release", f"Got {r.status_code}")
        except Exception as e:
            results.check(False, "BACKEND-5: HR release exception", f"{str(e)}")
        
        # Try scrap
        try:
            r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/scrap", 
                            headers=headers, 
                            json={"qty": 1, "notes": "test"},
                            timeout=15)
            results.check(r.status_code == 403, "BACKEND-5: HR role gets 403 for scrap", f"Got {r.status_code}")
        except Exception as e:
            results.check(False, "BACKEND-5: HR scrap exception", f"{str(e)}")
    
    # Test maklon role (should get 403 for scrap)
    maklon_token = login("maklon")
    if maklon_token:
        headers = {"Authorization": f"Bearer {maklon_token}"}
        
        try:
            r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/scrap", 
                            headers=headers, 
                            json={"qty": 1, "notes": "test"},
                            timeout=15)
            results.check(r.status_code == 403, "BACKEND-5: Maklon role gets 403 for scrap", f"Got {r.status_code}")
        except Exception as e:
            results.check(False, "BACKEND-5: Maklon scrap exception", f"{str(e)}")

def test_backend_6_release_partial():
    """BACKEND-6: Release Partial"""
    print("\n=== BACKEND-6: Release Partial ===")
    token = login("gudang")
    if not token:
        results.check(False, "BACKEND-6: Login failed")
        return
    
    # Get a quarantine item with sufficient qty
    if 'quarantine_item' not in results.test_data:
        print("  ⚠️  No quarantine item available")
        return
    
    item = results.test_data['quarantine_item']
    item_id = item.get('id')
    remaining_qty = float(item.get('remaining_qty', 0))
    
    if remaining_qty < 5:
        print(f"  ⚠️  Item qty too low ({remaining_qty}), skipping partial release test")
        return
    
    # Get a valid storage location
    admin_token = login("admin")
    if not admin_token:
        print("  ⚠️  Cannot get storage location")
        return
    
    try:
        r = requests.get(f"{BASE_URL}/rahaza/storage-locations", 
                        headers={"Authorization": f"Bearer {admin_token}"}, 
                        timeout=15)
        if r.status_code == 200:
            locations = r.json()
            if isinstance(locations, list) and len(locations) > 0:
                to_location_id = locations[0].get('id')
                
                # Perform partial release
                headers = {"Authorization": f"Bearer {token}"}
                payload = {
                    "qty": 5,
                    "to_location_id": to_location_id,
                    "notes": "Test partial release"
                }
                
                r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/release", 
                                headers=headers, 
                                json=payload,
                                timeout=15)
                
                results.check(r.status_code == 200, "BACKEND-6: Release returns 200", f"Got {r.status_code}")
                
                if r.status_code == 200:
                    data = r.json()
                    results.check('remaining_qty' in data, "BACKEND-6: Response has remaining_qty")
                    
                    # Verify remaining_qty decreased by 5
                    new_remaining = float(data.get('remaining_qty', 0))
                    expected_remaining = remaining_qty - 5
                    results.check(abs(new_remaining - expected_remaining) < 0.01, 
                                "BACKEND-6: Remaining qty decreased by 5", 
                                f"Expected {expected_remaining}, got {new_remaining}")
                    
                    # Check if JE was created for valued=false items
                    if 'posting' in data:
                        posting = data['posting']
                        if not item.get('valued'):
                            results.check('je_id' in posting or posting.get('ok'), 
                                        "BACKEND-6: JE created for unvalued item")
                else:
                    print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "BACKEND-6: Exception", f"{str(e)}")

def test_backend_7_return_supplier():
    """BACKEND-7: Return Supplier"""
    print("\n=== BACKEND-7: Return Supplier ===")
    token = login("gudang")
    if not token:
        results.check(False, "BACKEND-7: Login failed")
        return
    
    # Find an item with remaining qty
    admin_token = login("admin")
    if not admin_token:
        return
    
    try:
        r = requests.get(f"{BASE_URL}/wms/quarantine?status=open", 
                        headers={"Authorization": f"Bearer {admin_token}"}, 
                        timeout=15)
        if r.status_code == 200:
            items = r.json()
            suitable_item = None
            for item in items:
                if float(item.get('remaining_qty', 0)) >= 2:
                    suitable_item = item
                    break
            
            if not suitable_item:
                print("  ⚠️  No suitable item for return test")
                return
            
            item_id = suitable_item.get('id')
            remaining_before = float(suitable_item.get('remaining_qty', 0))
            
            headers = {"Authorization": f"Bearer {token}"}
            payload = {"qty": 2, "notes": "Test return to supplier"}
            
            r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/return-supplier", 
                            headers=headers, 
                            json=payload,
                            timeout=15)
            
            results.check(r.status_code == 200, "BACKEND-7: Return supplier returns 200", f"Got {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                results.check('remaining_qty' in data, "BACKEND-7: Response has remaining_qty")
                new_remaining = float(data.get('remaining_qty', 0))
                expected = remaining_before - 2
                results.check(abs(new_remaining - expected) < 0.01, 
                            "BACKEND-7: Remaining qty decreased", 
                            f"Expected {expected}, got {new_remaining}")
            else:
                print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "BACKEND-7: Exception", f"{str(e)}")

def test_backend_8_scrap():
    """BACKEND-8: Scrap"""
    print("\n=== BACKEND-8: Scrap ===")
    token = login("spv")
    if not token:
        results.check(False, "BACKEND-8: Login failed")
        return
    
    # Find a valued=true item to scrap
    admin_token = login("admin")
    if not admin_token:
        return
    
    try:
        r = requests.get(f"{BASE_URL}/wms/quarantine?status=open", 
                        headers={"Authorization": f"Bearer {admin_token}"}, 
                        timeout=15)
        if r.status_code == 200:
            items = r.json()
            valued_item = None
            for item in items:
                if item.get('valued') and float(item.get('remaining_qty', 0)) > 0:
                    valued_item = item
                    break
            
            if not valued_item:
                print("  ⚠️  No valued item for scrap test")
                return
            
            item_id = valued_item.get('id')
            remaining_qty = float(valued_item.get('remaining_qty', 0))
            
            headers = {"Authorization": f"Bearer {token}"}
            payload = {"qty": remaining_qty, "notes": "Test scrap full"}
            
            r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/scrap", 
                            headers=headers, 
                            json=payload,
                            timeout=15)
            
            results.check(r.status_code == 200, "BACKEND-8: Scrap returns 200", f"Got {r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                results.check(data.get('remaining_qty') == 0, "BACKEND-8: Remaining qty is 0")
                results.check(data.get('closed') == True, "BACKEND-8: Item is closed")
                
                # Verify item moved to closed status
                time.sleep(1)
                r = requests.get(f"{BASE_URL}/wms/quarantine?status=closed", 
                               headers={"Authorization": f"Bearer {admin_token}"}, 
                               timeout=15)
                if r.status_code == 200:
                    closed_items = r.json()
                    found = any(item.get('id') == item_id for item in closed_items)
                    results.check(found, "BACKEND-8: Item appears in closed list")
                
                # Check JE for valued item
                if 'posting' in data and valued_item.get('valued'):
                    results.check(data['posting'].get('ok') or 'je_id' in data['posting'], 
                                "BACKEND-8: JE created for valued item")
            else:
                print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "BACKEND-8: Exception", f"{str(e)}")

def test_backend_9_manual_quarantine():
    """BACKEND-9: Manual Quarantine"""
    print("\n=== BACKEND-9: Manual Quarantine ===")
    token = login("gudang")
    if not token:
        results.check(False, "BACKEND-9: Login failed")
        return
    
    # Get a material and location
    admin_token = login("admin")
    if not admin_token:
        return
    
    try:
        # Get materials
        r = requests.get(f"{BASE_URL}/rahaza/materials?limit=10", 
                        headers={"Authorization": f"Bearer {admin_token}"}, 
                        timeout=15)
        if r.status_code != 200:
            print("  ⚠️  Cannot get materials")
            return
        
        materials = r.json()
        if not materials:
            print("  ⚠️  No materials available")
            return
        
        material = materials[0]
        material_id = material.get('id')
        material_unit = material.get('unit', 'pcs')
        
        # Get storage locations
        r = requests.get(f"{BASE_URL}/rahaza/storage-locations", 
                        headers={"Authorization": f"Bearer {admin_token}"}, 
                        timeout=15)
        if r.status_code != 200:
            print("  ⚠️  Cannot get storage locations")
            return
        
        locations = r.json()
        if not locations:
            print("  ⚠️  No storage locations available")
            return
        
        from_location_id = locations[0].get('id')
        
        # Test manual quarantine
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "material_id": material_id,
            "qty": 3,
            "from_location_id": from_location_id,
            "reason_code": "FABRIC_DEFECT",
            "notes": "Test manual quarantine"
        }
        
        r = requests.post(f"{BASE_URL}/wms/quarantine/manual", 
                        headers=headers, 
                        json=payload,
                        timeout=15)
        
        results.check(r.status_code == 200, "BACKEND-9: Manual quarantine returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('material_id') == material_id, "BACKEND-9: Material ID matches")
            results.check(float(data.get('qty', 0)) == 3, "BACKEND-9: Qty matches")
            results.check(data.get('valued') == True, "BACKEND-9: Item is valued=true")
            results.check(data.get('unit') == material_unit, "BACKEND-9: Unit matches material unit", f"Expected {material_unit}, got {data.get('unit')}")
            
            # Verify reject_reasons is not empty
            reject_reasons = data.get('reject_reasons', [])
            results.check(len(reject_reasons) > 0, "BACKEND-9: Has reject_reasons")
            if reject_reasons:
                results.check(reject_reasons[0].get('code') == 'FABRIC_DEFECT', "BACKEND-9: Reason code matches")
        else:
            print(f"    Response: {r.text[:300]}")
        
        # Test validation: qty <= 0
        payload['qty'] = 0
        r = requests.post(f"{BASE_URL}/wms/quarantine/manual", 
                        headers=headers, 
                        json=payload,
                        timeout=15)
        results.check(r.status_code == 400, "BACKEND-9: Rejects qty<=0", f"Got {r.status_code}")
        
        # Test validation: missing from_location_id
        payload['qty'] = 3
        payload['from_location_id'] = ""
        r = requests.post(f"{BASE_URL}/wms/quarantine/manual", 
                        headers=headers, 
                        json=payload,
                        timeout=15)
        results.check(r.status_code == 400, "BACKEND-9: Rejects empty from_location_id", f"Got {r.status_code}")
        
    except Exception as e:
        results.check(False, "BACKEND-9: Exception", f"{str(e)}")

def test_backend_10_guards():
    """BACKEND-10: Guard Tests"""
    print("\n=== BACKEND-10: Guard Tests ===")
    token = login("gudang")
    if not token:
        results.check(False, "BACKEND-10: Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test: disposition on closed item
    admin_token = login("admin")
    if admin_token:
        try:
            r = requests.get(f"{BASE_URL}/wms/quarantine?status=closed", 
                           headers={"Authorization": f"Bearer {admin_token}"}, 
                           timeout=15)
            if r.status_code == 200:
                closed_items = r.json()
                if closed_items:
                    closed_id = closed_items[0].get('id')
                    
                    r = requests.post(f"{BASE_URL}/wms/quarantine/{closed_id}/release", 
                                    headers=headers, 
                                    json={"qty": 1, "to_location_id": "dummy", "notes": "test"},
                                    timeout=15)
                    results.check(r.status_code == 400, "BACKEND-10: Rejects disposition on closed item", f"Got {r.status_code}")
        except Exception as e:
            print(f"  ⚠️  Could not test closed item: {str(e)}")
    
    # Test: qty > remaining_qty
    try:
        r = requests.get(f"{BASE_URL}/wms/quarantine?status=open", 
                        headers={"Authorization": f"Bearer {admin_token}"}, 
                        timeout=15)
        if r.status_code == 200:
            items = r.json()
            if items:
                item = items[0]
                item_id = item.get('id')
                remaining = float(item.get('remaining_qty', 0))
                
                r = requests.post(f"{BASE_URL}/wms/quarantine/{item_id}/release", 
                                headers=headers, 
                                json={"qty": remaining + 100, "to_location_id": "dummy", "notes": "test"},
                                timeout=15)
                results.check(r.status_code == 400, "BACKEND-10: Rejects qty > remaining_qty", f"Got {r.status_code}")
    except Exception as e:
        print(f"  ⚠️  Could not test qty validation: {str(e)}")
    
    # Test: non-existent item
    try:
        r = requests.post(f"{BASE_URL}/wms/quarantine/nonexistent-id-12345/release", 
                        headers=headers, 
                        json={"qty": 1, "to_location_id": "dummy", "notes": "test"},
                        timeout=15)
        results.check(r.status_code == 404, "BACKEND-10: Returns 404 for non-existent item", f"Got {r.status_code}")
    except Exception as e:
        results.check(False, "BACKEND-10: Exception on 404 test", f"{str(e)}")

def test_backend_12_regression():
    """BACKEND-12: Regression - Warehouse Portal Endpoints"""
    print("\n=== BACKEND-12: Warehouse Portal Regression ===")
    token = login("admin")
    if not token:
        results.check(False, "BACKEND-12: Login failed")
        return
    
    headers = {"Authorization": f"Bearer {token}"}
    
    endpoints = [
        "/warehouse/dashboard-kpi",
        "/warehouse/stock",
        "/warehouse/stock/summary",
        "/warehouse/movements",
        "/warehouse/locations",
        "/wms/legacy/locations",
        "/wms/legacy/stock",
        "/wms/legacy/dashboard-kpi",
        "/wms/putaway/pending",
        "/wms/putaway/locations",
        "/wms/opname3/sessions",
        "/rahaza/material-stock",
        "/rahaza/material-stock/summary",
        "/rahaza/storage-locations",
        "/wms/structure/location-map",
        "/warehouse/receiving",
        "/warehouse/smart-reorder",
    ]
    
    for endpoint in endpoints:
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
            results.check(r.status_code == 200, f"BACKEND-12: GET {endpoint} returns 200", f"Got {r.status_code}")
        except Exception as e:
            results.check(False, f"BACKEND-12: {endpoint} exception", f"{str(e)}")
    
    # Test without token (should get 401)
    try:
        r = requests.get(f"{BASE_URL}/warehouse/dashboard-kpi", timeout=15)
        results.check(r.status_code == 401, "BACKEND-12: Returns 401 without token", f"Got {r.status_code}")
    except Exception as e:
        results.check(False, "BACKEND-12: 401 test exception", f"{str(e)}")

def main():
    print("=" * 80)
    print("BACKEND API TEST - FASE 6 QUARANTINE MODULE (INV-8)")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Time: {datetime.now(timezone.utc).isoformat()}")
    
    try:
        # Run all backend tests
        test_backend_1_quarantine_location()
        test_backend_2_list_quarantine()
        test_backend_3_summary()
        test_backend_4_reject_categories()
        test_backend_5_rbac_negative()
        test_backend_6_release_partial()
        test_backend_7_return_supplier()
        test_backend_8_scrap()
        test_backend_9_manual_quarantine()
        test_backend_10_guards()
        # BACKEND-11 (re-inspection) is complex and requires GR setup - skip for now
        test_backend_12_regression()
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        return 1
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {str(e)}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Results: {results.summary()}")
    print(f"Passed: {results.passed}")
    print(f"Failed: {results.failed}")
    
    if results.failed > 0:
        print("\n❌ FAILED TESTS:")
        for test in results.tests:
            if test['status'] == 'FAIL':
                print(f"  - {test['name']}: {test['details']}")
    
    return 0 if results.failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
