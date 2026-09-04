#!/usr/bin/env python3
"""
BACKEND TEST — RBAC CONSOLIDATION (2026-08-06)
Testing RBAC endpoints and fallback safe model.

CRITICAL: This test modifies admin_gudang role permissions temporarily.
It MUST restore the role to clean state (empty permissions) at the end.
"""
import sys
import requests
import time
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

# Test credentials (from /app/memory/test_credentials.md)
ADMIN_CRED = {"email": "admin@garment.com", "password": "Admin@123"}
GUDANG_CRED = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}

# Test counters
PASS_COUNT = 0
FAIL_COUNT = 0
FAILED_TESTS = []

# Store admin_gudang role_id for cleanup
ADMIN_GUDANG_ROLE_ID = None


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
    """Login and return auth headers + user data."""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            data = r.json()
            token = data.get("token")
            print(f"  ✅ Login successful for {email}")
            return {"Authorization": f"Bearer {token}"}, data.get("user", {})
        else:
            print(f"  ❌ Login failed for {email}: HTTP {r.status_code} - {r.text[:200]}")
            return None, None
    except Exception as e:
        print(f"  ❌ Login error for {email}: {str(e)}")
        return None, None


def restore_admin_gudang_permissions(admin_headers):
    """CRITICAL: Restore admin_gudang role to clean state (empty permissions)."""
    global ADMIN_GUDANG_ROLE_ID
    if not ADMIN_GUDANG_ROLE_ID:
        print("  ⚠️  admin_gudang role_id not found, skipping restore")
        return
    
    print(f"\n🔧 RESTORING admin_gudang role to clean state (empty permissions)...")
    try:
        r = requests.put(
            f"{BASE_URL}/api/roles/{ADMIN_GUDANG_ROLE_ID}",
            headers=admin_headers,
            json={"portals": [], "hidden_modules": [], "permissions": []},
            timeout=30
        )
        if r.status_code == 200:
            print(f"  ✅ admin_gudang role restored to clean state")
        else:
            print(f"  ❌ Failed to restore admin_gudang: HTTP {r.status_code}")
    except Exception as e:
        print(f"  ❌ Error restoring admin_gudang: {str(e)}")


def main():
    global FAIL_COUNT, ADMIN_GUDANG_ROLE_ID
    
    print("=" * 78)
    print("BACKEND API TESTING — RBAC CONSOLIDATION (2026-08-06)")
    print("=" * 78)
    print("⚠️  WARNING: This test will temporarily modify admin_gudang role permissions")
    print("⚠️  It will restore the role to clean state at the end")
    print("=" * 78)
    
    admin_headers = None
    gudang_headers = None
    
    try:
        # ═══════════════════════════════════════════════════════════════════════════
        # 1. AUTHENTICATION
        # ═══════════════════════════════════════════════════════════════════════════
        section("1. AUTHENTICATION")
        
        admin_headers, admin_user = login(ADMIN_CRED["email"], ADMIN_CRED["password"])
        if not admin_headers:
            print("\n❌ CRITICAL: Admin login failed. Cannot proceed.")
            return 1
        
        gudang_headers, gudang_user = login(GUDANG_CRED["email"], GUDANG_CRED["password"])
        if not gudang_headers:
            print("\n❌ CRITICAL: Gudang user login failed. Cannot proceed.")
            return 1
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 2. PERMISSION CATALOG
        # ═══════════════════════════════════════════════════════════════════════════
        section("2. PERMISSION CATALOG")
        
        # Test flat permissions
        try:
            r = requests.get(f"{BASE_URL}/api/permissions", headers=admin_headers, timeout=30)
            check(r.status_code == 200, "GET /api/permissions returns 200", f"status={r.status_code}")
            
            if r.status_code == 200:
                perms = r.json()
                check(isinstance(perms, list), "Permissions is a list")
                check(len(perms) == 129, f"Permissions count is 129", f"got {len(perms)}")
                
                if perms:
                    first = perms[0]
                    check("key" in first, "Permission has 'key' field")
                    check("action" in first, "Permission has 'action' field")
                    check("description" in first, "Permission has 'description' field")
                    check("module" in first, "Permission has 'module' field")
                    check("portal" in first, "Permission has 'portal' field")
        except Exception as e:
            check(False, "GET /api/permissions", f"Error: {str(e)}")
        
        # Test grouped permissions
        try:
            r = requests.get(f"{BASE_URL}/api/permissions?grouped=1", headers=admin_headers, timeout=30)
            check(r.status_code == 200, "GET /api/permissions?grouped=1 returns 200", f"status={r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                check("groups" in data, "Grouped response has 'groups' field")
                check("total" in data, "Grouped response has 'total' field")
                check(data.get("total") == 129, f"Total is 129", f"got {data.get('total')}")
                
                groups = data.get("groups", [])
                check(len(groups) == 13, f"Portal groups count is 13", f"got {len(groups)}")
                
                if groups:
                    first_group = groups[0]
                    check("portal" in first_group, "Group has 'portal' field")
                    check("portal_label" in first_group, "Group has 'portal_label' field")
                    check("modules" in first_group, "Group has 'modules' field")
        except Exception as e:
            check(False, "GET /api/permissions?grouped=1", f"Error: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 3. ROLES ENDPOINT
        # ═══════════════════════════════════════════════════════════════════════════
        section("3. ROLES ENDPOINT")
        
        try:
            r = requests.get(f"{BASE_URL}/api/roles", headers=admin_headers, timeout=30)
            check(r.status_code == 200, "GET /api/roles returns 200", f"status={r.status_code}")
            
            if r.status_code == 200:
                roles = r.json()
                check(isinstance(roles, list), "Roles is a list")
                print(f"    📊 Found {len(roles)} roles")
                
                if roles:
                    first = roles[0]
                    check("portals" in first, "Role has 'portals' field")
                    check("hidden_modules" in first, "Role has 'hidden_modules' field")
                    check("permission_keys" in first, "Role has 'permission_keys' field")
                    check("user_count" in first, "Role has 'user_count' field")
                    
                    # Find admin_gudang role
                    for role in roles:
                        if role.get("name") == "admin_gudang":
                            ADMIN_GUDANG_ROLE_ID = role.get("id")
                            print(f"    📌 Found admin_gudang role: {ADMIN_GUDANG_ROLE_ID}")
                            print(f"       Current permissions: {role.get('permission_keys', [])}")
                            print(f"       User count: {role.get('user_count', 0)}")
                            break
        except Exception as e:
            check(False, "GET /api/roles", f"Error: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 4. OLD ENDPOINTS MUST BE GONE (404/405)
        # ═══════════════════════════════════════════════════════════════════════════
        section("4. OLD ENDPOINTS MUST BE GONE")
        
        if ADMIN_GUDANG_ROLE_ID:
            # Test PUT /api/roles/{id}/permissions (should be 404/405)
            try:
                r = requests.put(
                    f"{BASE_URL}/api/roles/{ADMIN_GUDANG_ROLE_ID}/permissions",
                    headers=admin_headers,
                    json={"permissions": ["test.perm"]},
                    timeout=30
                )
                check(r.status_code in [404, 405], 
                      "PUT /api/roles/{id}/permissions returns 404/405", 
                      f"status={r.status_code}")
            except Exception as e:
                check(False, "PUT /api/roles/{id}/permissions", f"Error: {str(e)}")
            
            # Test POST /api/roles/matrix/bulk (should be 404/405)
            try:
                r = requests.post(
                    f"{BASE_URL}/api/roles/matrix/bulk",
                    headers=admin_headers,
                    json={"matrix": {}},
                    timeout=30
                )
                check(r.status_code in [404, 405], 
                      "POST /api/roles/matrix/bulk returns 404/405", 
                      f"status={r.status_code}")
            except Exception as e:
                check(False, "POST /api/roles/matrix/bulk", f"Error: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 5. ROLE CRUD OPERATIONS
        # ═══════════════════════════════════════════════════════════════════════════
        section("5. ROLE CRUD OPERATIONS")
        
        test_role_id = None
        
        # Create test role
        try:
            r = requests.post(
                f"{BASE_URL}/api/roles",
                headers=admin_headers,
                json={
                    "name": "qa_rbac_test",
                    "description": "Test role for RBAC testing",
                    "portals": ["warehouse"],
                    "hidden_modules": [],
                    "permissions": ["warehouse.view", "wh.receiving.view"]
                },
                timeout=30
            )
            check(r.status_code == 201, "POST /api/roles returns 201", f"status={r.status_code}")
            
            if r.status_code == 201:
                data = r.json()
                test_role_id = data.get("id")
                check(data.get("name") == "qa_rbac_test", "Created role has correct name")
                check("warehouse" in data.get("portals", []), "Created role has warehouse portal")
                check("warehouse.view" in data.get("permission_keys", []), "Created role has warehouse.view permission")
                print(f"    📌 Created test role: {test_role_id}")
        except Exception as e:
            check(False, "POST /api/roles", f"Error: {str(e)}")
        
        # Update test role
        if test_role_id:
            try:
                r = requests.put(
                    f"{BASE_URL}/api/roles/{test_role_id}",
                    headers=admin_headers,
                    json={
                        "description": "Updated test role",
                        "permissions": ["warehouse.view", "wh.receiving.view", "wh.putaway.manage"]
                    },
                    timeout=30
                )
                check(r.status_code == 200, "PUT /api/roles/{id} returns 200", f"status={r.status_code}")
                
                if r.status_code == 200:
                    data = r.json()
                    check(data.get("description") == "Updated test role", "Role description updated")
                    check("wh.putaway.manage" in data.get("permission_keys", []), "Role permissions updated")
            except Exception as e:
                check(False, "PUT /api/roles/{id}", f"Error: {str(e)}")
        
        # Test duplicate name rejection
        try:
            r = requests.post(
                f"{BASE_URL}/api/roles",
                headers=admin_headers,
                json={"name": "qa_rbac_test", "description": "Duplicate"},
                timeout=30
            )
            check(r.status_code == 400, "POST /api/roles rejects duplicate name", f"status={r.status_code}")
        except Exception as e:
            check(False, "POST /api/roles duplicate check", f"Error: {str(e)}")
        
        # Test invalid permission filtering
        if test_role_id:
            try:
                r = requests.put(
                    f"{BASE_URL}/api/roles/{test_role_id}",
                    headers=admin_headers,
                    json={"permissions": ["warehouse.view", "invalid.perm.key", "another.fake"]},
                    timeout=30
                )
                check(r.status_code == 200, "PUT /api/roles filters invalid permissions", f"status={r.status_code}")
                
                if r.status_code == 200:
                    data = r.json()
                    perms = data.get("permission_keys", [])
                    check("warehouse.view" in perms, "Valid permission kept")
                    check("invalid.perm.key" not in perms, "Invalid permission filtered out")
                    check("another.fake" not in perms, "Another invalid permission filtered out")
            except Exception as e:
                check(False, "PUT /api/roles invalid permission filter", f"Error: {str(e)}")
        
        # Delete test role (cleanup)
        if test_role_id:
            try:
                r = requests.delete(f"{BASE_URL}/api/roles/{test_role_id}", headers=admin_headers, timeout=30)
                check(r.status_code == 200, "DELETE /api/roles/{id} returns 200", f"status={r.status_code}")
            except Exception as e:
                check(False, "DELETE /api/roles/{id}", f"Error: {str(e)}")
        
        # Test delete system role (should fail)
        try:
            # Try to delete a system role (if any exists)
            r = requests.get(f"{BASE_URL}/api/roles", headers=admin_headers, timeout=30)
            if r.status_code == 200:
                roles = r.json()
                system_role = next((r for r in roles if r.get("is_system")), None)
                if system_role:
                    r = requests.delete(f"{BASE_URL}/api/roles/{system_role['id']}", headers=admin_headers, timeout=30)
                    check(r.status_code == 400, "DELETE system role returns 400", f"status={r.status_code}")
        except Exception as e:
            print(f"  ⚠️  Could not test system role deletion: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 6. ROLE AUDIT ENDPOINT
        # ═══════════════════════════════════════════════════════════════════════════
        section("6. ROLE AUDIT ENDPOINT")
        
        try:
            r = requests.get(f"{BASE_URL}/api/roles/audit", headers=admin_headers, timeout=30)
            check(r.status_code == 200, "GET /api/roles/audit returns 200 (not 500)", f"status={r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                check("items" in data, "Audit response has 'items' field")
                check("total" in data, "Audit response has 'total' field")
                print(f"    📊 Found {data.get('total', 0)} audit entries")
        except Exception as e:
            check(False, "GET /api/roles/audit", f"Error: {str(e)}")
        
        # Test with role_id filter
        if ADMIN_GUDANG_ROLE_ID:
            try:
                r = requests.get(
                    f"{BASE_URL}/api/roles/audit?role_id={ADMIN_GUDANG_ROLE_ID}",
                    headers=admin_headers,
                    timeout=30
                )
                check(r.status_code == 200, "GET /api/roles/audit?role_id=... returns 200", f"status={r.status_code}")
            except Exception as e:
                check(False, "GET /api/roles/audit with filter", f"Error: {str(e)}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 7. RBAC FALLBACK SAFE MODEL (MOST CRITICAL)
        # ═══════════════════════════════════════════════════════════════════════════
        section("7. RBAC FALLBACK SAFE MODEL (MOST CRITICAL)")
        
        if not ADMIN_GUDANG_ROLE_ID:
            print("  ⚠️  admin_gudang role not found, skipping fallback tests")
        else:
            # 7a. Test with EMPTY permissions (should use legacy fallback)
            print("\n  🔬 Test 7a: Empty permissions -> legacy fallback")
            try:
                # Ensure permissions are empty
                r = requests.put(
                    f"{BASE_URL}/api/roles/{ADMIN_GUDANG_ROLE_ID}",
                    headers=admin_headers,
                    json={"permissions": []},
                    timeout=30
                )
                if r.status_code == 200:
                    print("    ✓ Set admin_gudang permissions to empty")
                    
                    # Wait for cache to clear (TTL 20s + buffer)
                    print("    ⏳ Waiting 25 seconds for cache to clear...")
                    time.sleep(25)
                    
                    # Login again to get fresh token
                    print("    🔄 Logging in again with gudang user...")
                    gudang_headers, _ = login(GUDANG_CRED["email"], GUDANG_CRED["password"])
                    
                    if gudang_headers:
                        # Test cutting endpoint (should be 400, not 403)
                        r = requests.post(
                            f"{BASE_URL}/api/cutting/orders",
                            headers=gudang_headers,
                            json={},
                            timeout=30
                        )
                        check(r.status_code == 400, 
                              "POST /api/cutting/orders with empty role perms returns 400 (not 403)", 
                              f"status={r.status_code}")
                        
                        if r.status_code == 403:
                            print("    ⚠️  Got 403 instead of 400 - legacy fallback may not be working")
            except Exception as e:
                check(False, "Test 7a: Empty permissions fallback", f"Error: {str(e)}")
            
            # 7b. Test with LIMITED permissions (should enforce permissions)
            print("\n  🔬 Test 7b: Limited permissions -> enforce permissions")
            try:
                # Set only wh.putaway.manage permission
                r = requests.put(
                    f"{BASE_URL}/api/roles/{ADMIN_GUDANG_ROLE_ID}",
                    headers=admin_headers,
                    json={"permissions": ["wh.putaway.manage"]},
                    timeout=30
                )
                if r.status_code == 200:
                    print("    ✓ Set admin_gudang permissions to ['wh.putaway.manage']")
                    
                    # Wait for cache to clear
                    print("    ⏳ Waiting 25 seconds for cache to clear...")
                    time.sleep(25)
                    
                    # Login again
                    print("    🔄 Logging in again with gudang user...")
                    gudang_headers, _ = login(GUDANG_CRED["email"], GUDANG_CRED["password"])
                    
                    if gudang_headers:
                        # Test cutting endpoint (should be 403 now)
                        r = requests.post(
                            f"{BASE_URL}/api/cutting/orders",
                            headers=gudang_headers,
                            json={},
                            timeout=30
                        )
                        check(r.status_code == 403, 
                              "POST /api/cutting/orders with limited perms returns 403", 
                              f"status={r.status_code}")
                        
                        # Test putaway endpoint (should NOT be 403)
                        r = requests.post(
                            f"{BASE_URL}/api/wms/putaway/place",
                            headers=gudang_headers,
                            json={},
                            timeout=30
                        )
                        check(r.status_code in [400, 404, 422], 
                              "POST /api/wms/putaway/place with wh.putaway.manage returns 400/404/422 (not 403)", 
                              f"status={r.status_code}")
            except Exception as e:
                check(False, "Test 7b: Limited permissions enforcement", f"Error: {str(e)}")
            
            # 7c. CRITICAL: Restore admin_gudang to clean state
            print("\n  🔬 Test 7c: Restore admin_gudang to clean state")
            restore_admin_gudang_permissions(admin_headers)
            
            # Wait and verify restoration
            print("    ⏳ Waiting 25 seconds for cache to clear...")
            time.sleep(25)
            
            print("    🔄 Logging in again with gudang user...")
            gudang_headers, _ = login(GUDANG_CRED["email"], GUDANG_CRED["password"])
            
            if gudang_headers:
                # Test cutting endpoint again (should be 400, not 403)
                r = requests.post(
                    f"{BASE_URL}/api/cutting/orders",
                    headers=gudang_headers,
                    json={},
                    timeout=30
                )
                check(r.status_code == 400, 
                      "POST /api/cutting/orders after restore returns 400 (fallback restored)", 
                      f"status={r.status_code}")
        
        # ═══════════════════════════════════════════════════════════════════════════
        # 8. REGRESSION: CENTRALIZED GUARD ENDPOINTS
        # ═══════════════════════════════════════════════════════════════════════════
        section("8. REGRESSION: CENTRALIZED GUARD ENDPOINTS")
        
        endpoints_to_test = [
            ("GET", "/api/admin/doc-numbering"),
            ("GET", "/api/dewi/cmt-kejar"),
            ("GET", "/api/dewi/cmt-intake/cek-seri?seri=TEST"),
            ("GET", "/api/dewi/cmt-belanja/kapasitas"),
            ("GET", "/api/wms/putaway/pending"),
            ("GET", "/api/cutting/orders"),
        ]
        
        for method, endpoint in endpoints_to_test:
            try:
                if method == "GET":
                    r = requests.get(f"{BASE_URL}{endpoint}", headers=admin_headers, timeout=30)
                else:
                    r = requests.post(f"{BASE_URL}{endpoint}", headers=admin_headers, json={}, timeout=30)
                
                # We expect 200 or other success codes, not 500
                check(r.status_code < 500, 
                      f"{method} {endpoint} returns < 500 for admin", 
                      f"status={r.status_code}")
            except Exception as e:
                check(False, f"{method} {endpoint}", f"Error: {str(e)}")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        if admin_headers:
            restore_admin_gudang_permissions(admin_headers)
        return 1
    except Exception as e:
        print(f"\n\n❌ CRITICAL ERROR: {str(e)}")
        if admin_headers:
            restore_admin_gudang_permissions(admin_headers)
        return 1
    finally:
        # ═══════════════════════════════════════════════════════════════════════════
        # FINAL SUMMARY
        # ═══════════════════════════════════════════════════════════════════════════
        section("TEST SUMMARY")
        
        total = PASS_COUNT + FAIL_COUNT
        pass_pct = (PASS_COUNT / total * 100) if total > 0 else 0
        
        print(f"\n📊 Results: {PASS_COUNT}/{total} tests passed ({pass_pct:.1f}%)")
        print(f"   ✅ Passed: {PASS_COUNT}")
        print(f"   ❌ Failed: {FAIL_COUNT}")
        
        if FAILED_TESTS:
            print(f"\n❌ Failed tests:")
            for test in FAILED_TESTS:
                print(f"   • {test}")
        
        print("\n" + "=" * 78)
        
        return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
