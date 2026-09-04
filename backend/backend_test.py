#!/usr/bin/env python3
"""
BACKEND TEST — NOTIFICATION CATEGORIES & RBAC (2026-07-27)
Testing notification category endpoints and RBAC verification.
"""
import sys
import requests

import os

# URL bisa dioverride: API_URL=http://localhost:8001 python3 backend/backend_test.py
# (dulu URL preview dipatok di kode sehingga berkas ini mati begitu preview berubah)
BASE_URL = os.environ.get("API_URL", "http://localhost:8001")

# Test credentials
ADMIN_CRED = {"email": "admin@garment.com", "password": "Admin@123"}
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
    """Login and return auth headers."""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            token = r.json().get("token")
            print(f"  ✅ Login successful for {email}")
            return {"Authorization": f"Bearer {token}"}
        else:
            print(f"  ❌ Login failed for {email}: HTTP {r.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ Login error for {email}: {str(e)}")
        return None


def main():
    global FAIL_COUNT
    
    print("=" * 78)
    print("BACKEND API TESTING — NOTIFICATION CATEGORIES & RBAC")
    print("=" * 78)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════════
    section("1. AUTHENTICATION")
    
    admin_headers = login(ADMIN_CRED["email"], ADMIN_CRED["password"])
    if not admin_headers:
        print("\n❌ CRITICAL: Admin login failed. Cannot proceed.")
        return 1
    
    hr_headers = login(HR_CRED["email"], HR_CRED["password"])
    if not hr_headers:
        print("\n❌ CRITICAL: HR user login failed. Cannot proceed.")
        return 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 2. NOTIFICATION CATEGORIES ENDPOINT (Admin)
    # ═══════════════════════════════════════════════════════════════════════════
    section("2. NOTIFICATION CATEGORIES ENDPOINT (Admin)")
    
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/categories", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/notifications/categories returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("categories" in data, "Response contains 'categories' field")
            check("total_unread" in data, "Response contains 'total_unread' field")
            check("total" in data, "Response contains 'total' field")
            check("latest" in data, "Response contains 'latest' field")
            
            if "categories" in data:
                cats = data["categories"]
                check(isinstance(cats, list), "Categories is a list")
                print(f"    📊 Found {len(cats)} categories")
                
                # Check for expected categories
                cat_keys = [c.get("key") for c in cats]
                expected = ["warehouse", "production", "cutting", "maklon", "finance", "hr", "toko", "accessories", "assets", "rnd", "sysadmin"]
                for exp in expected:
                    if exp in cat_keys:
                        print(f"    ✓ Category '{exp}' present")
    except Exception as e:
        check(False, "GET /api/notifications/categories", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 3. NOTIFICATION CATEGORIZED ENDPOINT (Admin)
    # ═══════════════════════════════════════════════════════════════════════════
    section("3. NOTIFICATION CATEGORIZED ENDPOINT (Admin)")
    
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/categorized", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/notifications/categorized returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("items" in data, "Response contains 'items' field")
            check("count" in data, "Response contains 'count' field")
            check("allowed_categories" in data, "Response contains 'allowed_categories' field")
            
            if "items" in data:
                items = data["items"]
                print(f"    📊 Found {len(items)} notifications")
                
                # Check if items have category field
                if items:
                    first = items[0]
                    check("category" in first, "Notification item has 'category' field")
                    check("category_label" in first, "Notification item has 'category_label' field")
    except Exception as e:
        check(False, "GET /api/notifications/categorized", f"Error: {str(e)}")
    
    # Test with category filter
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/categorized?category=hr", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/notifications/categorized?category=hr returns 200", f"status={r.status_code}")
    except Exception as e:
        check(False, "GET /api/notifications/categorized with filter", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 4. NOTIFICATION CATEGORY CONFIG (Admin Only)
    # ═══════════════════════════════════════════════════════════════════════════
    section("4. NOTIFICATION CATEGORY CONFIG (Admin Only)")
    
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/category-config", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/notifications/category-config returns 200 (admin)", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("categories" in data, "Config response contains 'categories' field")
            check("roles" in data, "Config response contains 'roles' field")
            check("matrix" in data, "Config response contains 'matrix' field")
            
            if "matrix" in data:
                matrix = data["matrix"]
                print(f"    📊 Matrix has {len(matrix)} roles configured")
    except Exception as e:
        check(False, "GET /api/notifications/category-config (admin)", f"Error: {str(e)}")
    
    # Test that HR user CANNOT access config
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/category-config", headers=hr_headers, timeout=30)
        check(r.status_code == 403, "GET /api/notifications/category-config returns 403 (hr user)", f"status={r.status_code}")
    except Exception as e:
        check(False, "GET /api/notifications/category-config (hr user)", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 5. SAVE NOTIFICATION CATEGORY CONFIG (Admin)
    # ═══════════════════════════════════════════════════════════════════════════
    section("5. SAVE NOTIFICATION CATEGORY CONFIG (Admin)")
    
    try:
        # First get current config
        r = requests.get(f"{BASE_URL}/api/notifications/category-config", headers=admin_headers, timeout=30)
        if r.status_code == 200:
            current_matrix = r.json().get("matrix", {})
            
            # Modify matrix slightly (toggle one category for admin_gudang if exists)
            test_matrix = dict(current_matrix)
            if "admin_gudang" in test_matrix:
                current_cats = set(test_matrix["admin_gudang"])
                if "warehouse" in current_cats:
                    current_cats.remove("warehouse")
                else:
                    current_cats.add("warehouse")
                test_matrix["admin_gudang"] = sorted(list(current_cats))
            
            # Save modified config
            r = requests.put(
                f"{BASE_URL}/api/notifications/category-config",
                headers=admin_headers,
                json={"matrix": test_matrix},
                timeout=30
            )
            check(r.status_code == 200, "PUT /api/notifications/category-config returns 200", f"status={r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                check("ok" in data and data["ok"], "Save response contains 'ok: true'")
                check("matrix" in data, "Save response contains updated 'matrix'")
            
            # Restore original config
            r = requests.put(
                f"{BASE_URL}/api/notifications/category-config",
                headers=admin_headers,
                json={"matrix": current_matrix},
                timeout=30
            )
            check(r.status_code == 200, "Restore original config successful", f"status={r.status_code}")
    except Exception as e:
        check(False, "PUT /api/notifications/category-config", f"Error: {str(e)}")
    
    # Test that HR user CANNOT save config
    try:
        r = requests.put(
            f"{BASE_URL}/api/notifications/category-config",
            headers=hr_headers,
            json={"matrix": {}},
            timeout=30
        )
        check(r.status_code == 403, "PUT /api/notifications/category-config returns 403 (hr user)", f"status={r.status_code}")
    except Exception as e:
        check(False, "PUT /api/notifications/category-config (hr user)", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 6. USER CATEGORY PREFERENCES
    # ═══════════════════════════════════════════════════════════════════════════
    section("6. USER CATEGORY PREFERENCES")
    
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/my-category-prefs", headers=hr_headers, timeout=30)
        check(r.status_code == 200, "GET /api/notifications/my-category-prefs returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("muted_categories" in data, "Prefs response contains 'muted_categories' field")
            check("available" in data, "Prefs response contains 'available' field")
            check("categories" in data, "Prefs response contains 'categories' field")
    except Exception as e:
        check(False, "GET /api/notifications/my-category-prefs", f"Error: {str(e)}")
    
    # Test saving preferences
    try:
        r = requests.put(
            f"{BASE_URL}/api/notifications/my-category-prefs",
            headers=hr_headers,
            json={"muted_categories": ["warehouse"]},
            timeout=30
        )
        check(r.status_code == 200, "PUT /api/notifications/my-category-prefs returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("ok" in data and data["ok"], "Save prefs response contains 'ok: true'")
            check("muted_categories" in data, "Save prefs response contains 'muted_categories'")
        
        # Clear preferences
        r = requests.put(
            f"{BASE_URL}/api/notifications/my-category-prefs",
            headers=hr_headers,
            json={"muted_categories": []},
            timeout=30
        )
        check(r.status_code == 200, "Clear muted categories successful", f"status={r.status_code}")
    except Exception as e:
        check(False, "PUT /api/notifications/my-category-prefs", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 7. RBAC - HR USER PORTAL ACCESS
    # ═══════════════════════════════════════════════════════════════════════════
    section("7. RBAC - HR USER PORTAL ACCESS")
    
    # HR user should be able to access notification categories
    try:
        r = requests.get(f"{BASE_URL}/api/notifications/categories", headers=hr_headers, timeout=30)
        check(r.status_code == 200, "HR user can access /api/notifications/categories", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            cats = data.get("categories", [])
            cat_keys = [c.get("key") for c in cats]
            
            # HR user should have access to HR category
            check("hr" in cat_keys, "HR user has access to 'hr' category")
            
            # HR user should NOT have access to all categories (not superadmin)
            check(len(cat_keys) < 11, "HR user does not have access to all categories", f"has {len(cat_keys)} categories")
    except Exception as e:
        check(False, "HR user notification categories access", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("TEST SUMMARY")
    print("=" * 78)
    print(f"✅ Passed: {PASS_COUNT}")
    print(f"❌ Failed: {FAIL_COUNT}")
    
    if FAILED_TESTS:
        print("\nFailed tests:")
        for test in FAILED_TESTS:
            print(f"  • {test}")
    
    print("=" * 78)
    
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
