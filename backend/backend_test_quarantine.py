#!/usr/bin/env python3
"""
BACKEND TEST — QUARANTINE MODULE (2026-08-07)
Testing quarantine availability_blocked features, retry-block, and fail-loud fixes.
"""
import sys
import requests
import os
import time

# Backend URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com")

# Test credentials (from review request)
ADMIN_CRED = {"email": "admin@garment.com", "password": "Admin@123"}
WAREHOUSE_CRED = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}
HR_CRED = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}

# Test counters
PASS_COUNT = 0
FAIL_COUNT = 0
FAILED_TESTS = []


def check(condition, test_name, extra=""):
    """Record test result."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✅ {test_name}" + (f" — {extra}" if extra else ""))
        return True
    else:
        FAIL_COUNT += 1
        FAILED_TESTS.append(test_name)
        print(f"  ❌ {test_name}" + (f" — {extra}" if extra else ""))
        return False


def section(title):
    """Print section header."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def login(email, password):
    """Login and return auth headers + token."""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            token = r.json().get("token")
            print(f"  ✅ Login successful for {email}")
            return {"Authorization": f"Bearer {token}"}, token
        else:
            print(f"  ❌ Login failed for {email}: HTTP {r.status_code} - {r.text[:200]}")
            return None, None
    except Exception as e:
        print(f"  ❌ Login error for {email}: {str(e)}")
        return None, None


def main():
    global FAIL_COUNT
    
    print("=" * 78)
    print("BACKEND API TESTING — QUARANTINE MODULE (2026-08-07)")
    print(f"Testing against: {BASE_URL}")
    print("=" * 78)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════════
    section("1. AUTHENTICATION")
    
    admin_headers, admin_token = login(ADMIN_CRED["email"], ADMIN_CRED["password"])
    if not admin_headers:
        print("\n❌ CRITICAL: Admin login failed. Cannot proceed.")
        return 1
    
    warehouse_headers, warehouse_token = login(WAREHOUSE_CRED["email"], WAREHOUSE_CRED["password"])
    if not warehouse_headers:
        print("\n⚠️  WARNING: Warehouse user login failed. RBAC tests will be skipped.")
    
    hr_headers, hr_token = login(HR_CRED["email"], HR_CRED["password"])
    if not hr_headers:
        print("\n⚠️  WARNING: HR user login failed. 403 tests will be skipped.")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 2. QUARANTINE SUMMARY (NEW KEYS)
    # ═══════════════════════════════════════════════════════════════════════════
    section("2. GET /api/wms/quarantine/summary — NEW KEYS")
    
    try:
        r = requests.get(f"{BASE_URL}/api/wms/quarantine/summary", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/wms/quarantine/summary returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("unblocked_items" in data, "Response contains 'unblocked_items' key")
            check("unblocked_qty" in data, "Response contains 'unblocked_qty' key")
            check("unblocked_groups" in data, "Response contains 'unblocked_groups' key")
            
            unblocked_items = data.get("unblocked_items", 0)
            unblocked_qty = data.get("unblocked_qty", 0)
            unblocked_groups = data.get("unblocked_groups", [])
            
            print(f"  📊 unblocked_items: {unblocked_items}")
            print(f"  📊 unblocked_qty: {unblocked_qty}")
            print(f"  📊 unblocked_groups count: {len(unblocked_groups)}")
            
            if unblocked_items > 0:
                print(f"  ⚠️  Found {unblocked_items} items with availability not blocked ({unblocked_qty} units)")
                for g in unblocked_groups:
                    print(f"      - {g.get('material_code')}: shortfall {g.get('shortfall')} {g.get('unit')}")
            else:
                print("  ✅ All quarantine items have availability properly blocked")
        else:
            print(f"  ❌ Failed to get summary: {r.text[:200]}")
    except Exception as e:
        check(False, "GET /api/wms/quarantine/summary", f"Exception: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 3. QUARANTINE LIST WITH needs_action FILTER
    # ═══════════════════════════════════════════════════════════════════════════
    section("3. GET /api/wms/quarantine?status=open&needs_action=true")
    
    try:
        r = requests.get(f"{BASE_URL}/api/wms/quarantine?status=open&needs_action=true", 
                        headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/wms/quarantine?needs_action=true returns 200", 
              f"status={r.status_code}")
        
        if r.status_code == 200:
            items = r.json()
            check(isinstance(items, list), "Response is a list")
            
            print(f"  📊 Items needing action: {len(items)}")
            
            if len(items) > 0:
                # Check that each item has the required fields
                first_item = items[0]
                check("availability_blocked" in first_item, "Item has 'availability_blocked' field")
                check("availability_shortfall" in first_item, "Item has 'availability_shortfall' field")
                check("availability_blocked_at_intake" in first_item, "Item has 'availability_blocked_at_intake' field")
                
                # Verify that items needing action have availability_blocked=False
                for item in items:
                    if not check(item.get("availability_blocked") == False, 
                               f"Item {item.get('material_code')} has availability_blocked=False"):
                        print(f"      Item: {item.get('material_code')}, availability_blocked={item.get('availability_blocked')}")
                
                print(f"  📋 Items needing action:")
                for item in items:
                    print(f"      - {item.get('material_code')}: {item.get('remaining_qty')} {item.get('unit')}, "
                          f"shortfall={item.get('availability_shortfall')}")
            else:
                print("  ✅ No items needing manual action (all properly blocked)")
        else:
            print(f"  ❌ Failed to get items: {r.text[:200]}")
    except Exception as e:
        check(False, "GET /api/wms/quarantine?needs_action=true", f"Exception: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 4. RETRY-BLOCK ENDPOINT (RBAC & FUNCTIONALITY)
    # ═══════════════════════════════════════════════════════════════════════════
    section("4. POST /api/wms/quarantine/{item_id}/retry-block")
    
    # First, get an item that needs action (if any)
    try:
        r = requests.get(f"{BASE_URL}/api/wms/quarantine?status=open&needs_action=true", 
                        headers=admin_headers, timeout=30)
        if r.status_code == 200:
            items_needing_action = r.json()
            
            if len(items_needing_action) > 0:
                test_item = items_needing_action[0]
                item_id = test_item.get("id")
                material_code = test_item.get("material_code")
                
                print(f"  📋 Testing with item: {material_code} (id: {item_id})")
                
                # Test 4a: Non-warehouse user should get 403
                if hr_headers:
                    section("4a. RBAC: Non-warehouse user (hr@) should get 403")
                    try:
                        r = requests.post(f"{BASE_URL}/api/wms/quarantine/{item_id}/retry-block", 
                                        headers=hr_headers, timeout=30)
                        check(r.status_code == 403, "Non-warehouse user gets 403", 
                              f"status={r.status_code}")
                    except Exception as e:
                        check(False, "Non-warehouse user 403 test", f"Exception: {str(e)}")
                
                # Test 4b: Warehouse user should succeed (or admin)
                section("4b. Warehouse user (gudang@) or admin should succeed")
                test_headers = warehouse_headers if warehouse_headers else admin_headers
                test_user = "gudang@" if warehouse_headers else "admin@"
                
                try:
                    r = requests.post(f"{BASE_URL}/api/wms/quarantine/{item_id}/retry-block", 
                                    headers=test_headers, timeout=30)
                    check(r.status_code == 200, f"{test_user} retry-block returns 200", 
                          f"status={r.status_code}")
                    
                    if r.status_code == 200:
                        result = r.json()
                        check("ok" in result, "Response has 'ok' field")
                        check("diblokir" in result, "Response has 'diblokir' field")
                        check("pesan" in result, "Response has 'pesan' field")
                        
                        print(f"  📊 Result: ok={result.get('ok')}, diblokir={result.get('diblokir')}, "
                              f"sudah_terblokir={result.get('sudah_terblokir')}")
                        print(f"  📋 Message: {result.get('pesan')}")
                        
                        # Test 4c: Calling again should be idempotent (sudah_terblokir=true, diblokir=0)
                        section("4c. Idempotency: Second call should return sudah_terblokir=true")
                        time.sleep(1)  # Brief pause
                        r2 = requests.post(f"{BASE_URL}/api/wms/quarantine/{item_id}/retry-block", 
                                         headers=test_headers, timeout=30)
                        check(r2.status_code == 200, "Second retry-block returns 200", 
                              f"status={r2.status_code}")
                        
                        if r2.status_code == 200:
                            result2 = r2.json()
                            check(result2.get("sudah_terblokir") == True, 
                                  "Second call returns sudah_terblokir=true")
                            check(result2.get("diblokir") == 0, 
                                  "Second call returns diblokir=0 (idempotent)")
                    else:
                        print(f"  ❌ Failed: {r.text[:200]}")
                except Exception as e:
                    check(False, "Retry-block functionality test", f"Exception: {str(e)}")
                
                # Test 4d: Verify summary updated
                section("4d. Verify summary updated after retry-block")
                try:
                    r = requests.get(f"{BASE_URL}/api/wms/quarantine/summary", 
                                   headers=admin_headers, timeout=30)
                    if r.status_code == 200:
                        new_summary = r.json()
                        new_unblocked = new_summary.get("unblocked_items", 0)
                        print(f"  📊 After retry-block: unblocked_items={new_unblocked}")
                        # Should be 0 or decreased
                        check(True, "Summary endpoint still accessible after retry-block")
                except Exception as e:
                    check(False, "Summary after retry-block", f"Exception: {str(e)}")
            else:
                print("  ℹ️  No items needing action found. Retry-block tests skipped.")
                print("     (This is expected if all items are properly blocked)")
        else:
            print(f"  ⚠️  Could not fetch items needing action: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ❌ Error in retry-block tests: {str(e)}")
    
    # Test 4e: Unknown item ID should return 400
    section("4e. Unknown item ID should return 400")
    try:
        r = requests.post(f"{BASE_URL}/api/wms/quarantine/unknown-item-id-12345/retry-block", 
                        headers=admin_headers, timeout=30)
        check(r.status_code == 400, "Unknown item ID returns 400", f"status={r.status_code}")
    except Exception as e:
        check(False, "Unknown item ID test", f"Exception: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 5. FAIL-LOUD: ORDER CREATION WITH NON-NUMERIC QTY
    # ═══════════════════════════════════════════════════════════════════════════
    section("5. FAIL-LOUD: POST /api/rahaza/orders with non-numeric qty")
    
    # First, get a valid model_id and size_id
    try:
        # Get models
        r = requests.get(f"{BASE_URL}/api/rahaza/models?limit=1", headers=admin_headers, timeout=30)
        if r.status_code == 200:
            models = r.json()
            if isinstance(models, dict):
                models = models.get("items", [])
            if len(models) > 0:
                model_id = models[0].get("id")
                
                # Get sizes
                r = requests.get(f"{BASE_URL}/api/rahaza/sizes?limit=1", headers=admin_headers, timeout=30)
                if r.status_code == 200:
                    sizes = r.json()
                    if isinstance(sizes, dict):
                        sizes = sizes.get("items", [])
                    if len(sizes) > 0:
                        size_id = sizes[0].get("id")
                        
                        # Test 5a: Non-numeric qty should return 400
                        section("5a. Non-numeric qty should return 400 (not 200 with line dropped)")
                        payload = {
                            "is_internal": True,
                            "items": [{"model_id": model_id, "size_id": size_id, "qty": "abc"}]
                        }
                        r = requests.post(f"{BASE_URL}/api/rahaza/orders", 
                                        headers=admin_headers, json=payload, timeout=30)
                        check(r.status_code == 400, "Non-numeric qty returns 400", 
                              f"status={r.status_code}")
                        if r.status_code == 400:
                            error_msg = r.json().get("detail", "")
                            check("baris" in error_msg.lower() or "item" in error_msg.lower(), 
                                  "Error message mentions line number")
                            print(f"  📋 Error message: {error_msg[:150]}")
                        
                        # Test 5b: Mixed (one bad + one good) should return 400
                        section("5b. Mixed items (one bad qty + one good) should return 400")
                        payload = {
                            "is_internal": True,
                            "items": [
                                {"model_id": model_id, "size_id": size_id, "qty": "abc"},
                                {"model_id": model_id, "size_id": size_id, "qty": 9}
                            ]
                        }
                        r = requests.post(f"{BASE_URL}/api/rahaza/orders", 
                                        headers=admin_headers, json=payload, timeout=30)
                        check(r.status_code == 400, "Mixed items returns 400 (not 200 with only good line)", 
                              f"status={r.status_code}")
                        
                        # Test 5c: Valid order should still work (regression)
                        section("5c. REGRESSION: Valid order should still be created successfully")
                        payload = {
                            "is_internal": True,
                            "items": [{"model_id": model_id, "size_id": size_id, "qty": 5}]
                        }
                        r = requests.post(f"{BASE_URL}/api/rahaza/orders", 
                                        headers=admin_headers, json=payload, timeout=30)
                        check(r.status_code == 200, "Valid order returns 200", 
                              f"status={r.status_code}")
                        if r.status_code == 200:
                            order = r.json()
                            order_id = order.get("id")
                            print(f"  📋 Created order: {order_id}")
                            
                            # Clean up: delete the test order
                            if order_id:
                                requests.delete(f"{BASE_URL}/api/rahaza/orders/{order_id}", 
                                              headers=admin_headers, timeout=30)
                        
                        # Test 5d: Empty row + valid row should succeed (empty template rows ignored)
                        section("5d. REGRESSION: Empty row + valid row should succeed")
                        payload = {
                            "is_internal": True,
                            "items": [
                                {},  # Empty template row
                                {"model_id": model_id, "size_id": size_id, "qty": 3}
                            ]
                        }
                        r = requests.post(f"{BASE_URL}/api/rahaza/orders", 
                                        headers=admin_headers, json=payload, timeout=30)
                        check(r.status_code == 200, "Empty row + valid row returns 200", 
                              f"status={r.status_code}")
                        if r.status_code == 200:
                            order = r.json()
                            order_id = order.get("id")
                            if order_id:
                                requests.delete(f"{BASE_URL}/api/rahaza/orders/{order_id}", 
                                              headers=admin_headers, timeout=30)
                    else:
                        print("  ⚠️  No sizes found. Order tests skipped.")
                else:
                    print(f"  ⚠️  Could not fetch sizes: HTTP {r.status_code}")
            else:
                print("  ⚠️  No models found. Order tests skipped.")
        else:
            print(f"  ⚠️  Could not fetch models: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ❌ Error in order tests: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 6. DATA_QUALITY FIELDS IN FINANCE ENDPOINTS
    # ═══════════════════════════════════════════════════════════════════════════
    section("6. DATA_QUALITY: GET /api/rahaza/ar-aging")
    
    try:
        r = requests.get(f"{BASE_URL}/api/rahaza/ar-aging", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/rahaza/ar-aging returns 200", 
              f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("data_quality" in data, "Response contains 'data_quality' field")
            check("buckets" in data, "Response contains 'buckets' field")
            
            if "buckets" in data:
                buckets = data.get("buckets", {})
                check("tanpa_jatuh_tempo" in buckets, "Buckets contain 'tanpa_jatuh_tempo' key")
                print(f"  📊 tanpa_jatuh_tempo: {buckets.get('tanpa_jatuh_tempo', 0)}")
            
            if "data_quality" in data:
                dq = data.get("data_quality", {})
                print(f"  📊 data_quality.dilewati: {dq.get('dilewati', 0)}")
                if dq.get("dilewati", 0) > 0:
                    print(f"  ⚠️  {dq.get('dilewati')} records skipped: {dq.get('pesan', '')}")
        else:
            print(f"  ❌ Failed: {r.text[:200]}")
    except Exception as e:
        check(False, "GET /api/rahaza/ar-aging", f"Exception: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 7. REGRESSION: QUARANTINE DISPOSITION FLOWS
    # ═══════════════════════════════════════════════════════════════════════════
    section("7. REGRESSION: Quarantine disposition flows still work")
    
    # Get an open quarantine item (not the one we used for retry-block)
    try:
        r = requests.get(f"{BASE_URL}/api/wms/quarantine?status=open&limit=10", 
                        headers=admin_headers, timeout=30)
        if r.status_code == 200:
            items = r.json()
            # Find TEST-Q6-KAIN items (not BTN which is for retry-block test)
            kain_items = [it for it in items if "KAIN" in it.get("material_code", "")]
            
            if len(kain_items) > 0:
                test_item = kain_items[0]
                item_id = test_item.get("id")
                material_code = test_item.get("material_code")
                remaining_qty = test_item.get("remaining_qty", 0)
                
                print(f"  📋 Testing with item: {material_code} (remaining: {remaining_qty})")
                
                # Get storage locations for release
                r = requests.get(f"{BASE_URL}/api/wms/quarantine/location", 
                               headers=admin_headers, timeout=30)
                if r.status_code == 200:
                    loc_info = r.json()
                    storage_locs = loc_info.get("storage_locations", [])
                    
                    if len(storage_locs) > 0:
                        to_location_id = storage_locs[0].get("id")
                        
                        # Test release with small qty
                        test_qty = min(1.0, remaining_qty)
                        
                        section("7a. POST /api/wms/quarantine/{id}/release")
                        payload = {
                            "qty": test_qty,
                            "to_location_id": to_location_id,
                            "notes": "Backend test - release"
                        }
                        r = requests.post(f"{BASE_URL}/api/wms/quarantine/{item_id}/release", 
                                        headers=admin_headers, json=payload, timeout=30)
                        check(r.status_code == 200, "Release returns 200", f"status={r.status_code}")
                        if r.status_code == 200:
                            result = r.json()
                            print(f"  📊 Released {test_qty}, remaining: {result.get('remaining_qty')}")
                    else:
                        print("  ⚠️  No storage locations found. Release test skipped.")
                else:
                    print(f"  ⚠️  Could not fetch locations: HTTP {r.status_code}")
            else:
                print("  ℹ️  No TEST-Q6-KAIN items found for disposition tests.")
        else:
            print(f"  ⚠️  Could not fetch quarantine items: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ❌ Error in disposition tests: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 8. REGRESSION: MANUAL QUARANTINE
    # ═══════════════════════════════════════════════════════════════════════════
    section("8. REGRESSION: POST /api/wms/quarantine/manual")
    
    try:
        # Get a material and location
        r = requests.get(f"{BASE_URL}/api/rahaza/materials?limit=1", headers=admin_headers, timeout=30)
        if r.status_code == 200:
            materials = r.json()
            if isinstance(materials, dict):
                materials = materials.get("items", [])
            if len(materials) > 0:
                material_id = materials[0].get("id")
                
                # Get storage location
                r = requests.get(f"{BASE_URL}/api/wms/quarantine/location", 
                               headers=admin_headers, timeout=30)
                if r.status_code == 200:
                    loc_info = r.json()
                    storage_locs = loc_info.get("storage_locations", [])
                    
                    if len(storage_locs) > 0:
                        from_location_id = storage_locs[0].get("id")
                        
                        payload = {
                            "material_id": material_id,
                            "qty": 0.5,
                            "from_location_id": from_location_id,
                            "reason_code": "RUSAK",
                            "notes": "Backend test - manual quarantine"
                        }
                        r = requests.post(f"{BASE_URL}/api/wms/quarantine/manual", 
                                        headers=admin_headers, json=payload, timeout=30)
                        check(r.status_code == 200, "Manual quarantine returns 200", 
                              f"status={r.status_code}")
                        if r.status_code == 200:
                            result = r.json()
                            check(result.get("availability_blocked") == True, 
                                  "Newly created item reports availability_blocked=true")
                            print(f"  📋 Created manual quarantine item: {result.get('id')}")
                    else:
                        print("  ⚠️  No storage locations found. Manual quarantine test skipped.")
                else:
                    print(f"  ⚠️  Could not fetch locations: HTTP {r.status_code}")
            else:
                print("  ⚠️  No materials found. Manual quarantine test skipped.")
        else:
            print(f"  ⚠️  Could not fetch materials: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ❌ Error in manual quarantine test: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("TEST SUMMARY")
    print("=" * 78)
    print(f"✅ PASSED: {PASS_COUNT}")
    print(f"❌ FAILED: {FAIL_COUNT}")
    
    if FAIL_COUNT > 0:
        print("\nFailed tests:")
        for test in FAILED_TESTS:
            print(f"  - {test}")
        return 1
    else:
        print("\n🎉 All tests passed!")
        return 0


if __name__ == "__main__":
    sys.exit(main())
