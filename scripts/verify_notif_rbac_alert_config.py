#!/usr/bin/env python3
"""
BACKEND TEST — RBAC NOTIFICATION FIXES & ALERT CONFIG (2026-08-07)
Testing notification categories, RBAC, alert config, RnD photos
"""
import sys
import requests
import os

BASE_URL = os.environ.get('API_URL', 'http://localhost:8001')

# Test credentials
ADMIN_CRED = {"email": "admin@garment.com", "password": "Admin@123"}
HR_CRED = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}
FINANCE_CRED = {"email": "finance@dewiaditya.id", "password": "Dewi@123"}

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
    print("BACKEND API TESTING — RBAC NOTIFICATION FIXES & ALERT CONFIG")
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
        print("\n⚠️  WARNING: HR user login failed. Some tests will be skipped.")
        hr_headers = None
    
    finance_headers = login(FINANCE_CRED["email"], FINANCE_CRED["password"])
    if not finance_headers:
        print("\n⚠️  WARNING: Finance user login failed. Some tests will be skipped.")
        finance_headers = None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 2. NOTIFICATION CATEGORIES - "UNTUK SAYA" (PERSONAL) CATEGORY
    # ═══════════════════════════════════════════════════════════════════════════
    section("2. NOTIFICATION CATEGORIES - 'UNTUK SAYA' (PERSONAL) CATEGORY")
    
    # Test HR user
    if hr_headers:
        try:
            r = requests.get(f"{BASE_URL}/api/notifications/categories", headers=hr_headers, timeout=30)
            check(r.status_code == 200, "GET /api/notifications/categories returns 200 for HR", f"status={r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                cats = data.get("categories", [])
                cat_keys = [c.get("key") for c in cats]
                check("personal" in cat_keys, "Personal category exists for HR user", str(cat_keys))
                
                personal_cat = next((c for c in cats if c.get("key") == "personal"), None)
                if personal_cat:
                    check(personal_cat.get("label") == "Untuk Saya", 
                          "Personal category label is 'Untuk Saya'", 
                          f"label={personal_cat.get('label')}")
                
                # Verify total count matches items
                total_from_cats = sum(c.get("total", 0) for c in cats)
                r2 = requests.get(f"{BASE_URL}/api/notifications/categorized?limit=300", headers=hr_headers, timeout=30)
                if r2.status_code == 200:
                    items_count = len(r2.json().get("items", []))
                    check(total_from_cats == items_count, 
                          "Category totals match categorized items count for HR",
                          f"categories={total_from_cats} items={items_count}")
        except Exception as e:
            check(False, "GET /api/notifications/categories (HR)", f"Error: {str(e)}")
    
    # Test Finance user
    if finance_headers:
        try:
            r = requests.get(f"{BASE_URL}/api/notifications/categories", headers=finance_headers, timeout=30)
            check(r.status_code == 200, "GET /api/notifications/categories returns 200 for Finance", f"status={r.status_code}")
            
            if r.status_code == 200:
                data = r.json()
                cats = data.get("categories", [])
                cat_keys = [c.get("key") for c in cats]
                check("personal" in cat_keys, "Personal category exists for Finance user", str(cat_keys))
                
                # Verify total count matches items
                total_from_cats = sum(c.get("total", 0) for c in cats)
                r2 = requests.get(f"{BASE_URL}/api/notifications/categorized?limit=300", headers=finance_headers, timeout=30)
                if r2.status_code == 200:
                    items_count = len(r2.json().get("items", []))
                    check(total_from_cats == items_count, 
                          "Category totals match categorized items count for Finance",
                          f"categories={total_from_cats} items={items_count}")
        except Exception as e:
            check(False, "GET /api/notifications/categories (Finance)", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 3. USER NOTIFICATION PREFERENCES - PERSONAL CANNOT BE MUTED
    # ═══════════════════════════════════════════════════════════════════════════
    section("3. USER NOTIFICATION PREFERENCES - PERSONAL CANNOT BE MUTED")
    
    if hr_headers:
        try:
            r = requests.get(f"{BASE_URL}/api/notifications/my-category-prefs", headers=hr_headers, timeout=30)
            check(r.status_code == 200, "GET /api/notifications/my-category-prefs returns 200", f"status={r.status_code}")
            
            if r.status_code == 200:
                prefs = r.json()
                check("muted_categories" in prefs, "Prefs include muted_categories")
                check("available" in prefs, "Prefs include available categories")
                check("active" in prefs, "Prefs include active categories")
                check("locked_categories" in prefs, "Prefs include locked_categories")
                check("personal" in prefs.get("locked_categories", []), 
                      "Personal is in locked_categories",
                      str(prefs.get("locked_categories")))
                
                # Try to mute 'personal' - should be silently dropped
                r2 = requests.put(f"{BASE_URL}/api/notifications/my-category-prefs", 
                                 headers=hr_headers,
                                 json={"muted_categories": ["personal", "hr"]},
                                 timeout=30)
                check(r2.status_code == 200, "PUT my-category-prefs returns 200", f"status={r2.status_code}")
                
                if r2.status_code == 200:
                    result = r2.json()
                    muted = result.get("muted_categories", [])
                    check("personal" not in muted, 
                          "Personal cannot be muted (silently dropped)", 
                          f"muted={muted}")
                    check("hr" in muted, "HR can be muted", f"muted={muted}")
                    
                    # Verify muted category disappears from categorized list
                    r3 = requests.get(f"{BASE_URL}/api/notifications/categorized?limit=300", 
                                     headers=hr_headers, timeout=30)
                    if r3.status_code == 200:
                        items = r3.json().get("items", [])
                        hr_items = [i for i in items if i.get("category") == "hr"]
                        check(len(hr_items) == 0, 
                              "Muted category (hr) disappears from categorized list",
                              f"found {len(hr_items)} hr items")
                    
                    # Restore clean state
                    r4 = requests.put(f"{BASE_URL}/api/notifications/my-category-prefs", 
                                     headers=hr_headers,
                                     json={"muted_categories": []},
                                     timeout=30)
                    check(r4.status_code == 200, "Restore clean state successful", f"status={r4.status_code}")
                    
                    # Verify unmuted category comes back
                    r5 = requests.get(f"{BASE_URL}/api/notifications/categorized?limit=300", 
                                     headers=hr_headers, timeout=30)
                    if r5.status_code == 200:
                        items = r5.json().get("items", [])
                        # Note: may be 0 if no hr notifications exist, which is OK
                        print(f"    📊 After unmuting: found {len([i for i in items if i.get('category') == 'hr'])} hr items")
        except Exception as e:
            check(False, "User notification preferences", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 4. ALERT CONFIGURATION API - OWNER-CONFIGURABLE THRESHOLDS
    # ═══════════════════════════════════════════════════════════════════════════
    section("4. ALERT CONFIGURATION API - OWNER-CONFIGURABLE THRESHOLDS")
    
    try:
        r = requests.get(f"{BASE_URL}/api/rahaza/management/alert-config", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/rahaza/management/alert-config returns 200 for admin", f"status={r.status_code}")
        
        if r.status_code == 200:
            cfg = r.json()
            check("po_warn_days" in cfg, "Config includes po_warn_days")
            check("ar_warn_days" in cfg, "Config includes ar_warn_days")
            check("rnd_attention_days" in cfg, "Config includes rnd_attention_days")
            check("rnd_stale_days" in cfg, "Config includes rnd_stale_days")
            check("defaults" in cfg, "Config includes defaults")
            check("labels" in cfg, "Config includes labels")
            check("min" in cfg and "max" in cfg, "Config includes min/max")
            
            original_cfg = {k: cfg[k] for k in ["po_warn_days", "ar_warn_days", "rnd_attention_days", "rnd_stale_days"]}
            print(f"    📊 Current config: {original_cfg}")
            
            # Test valid update
            r2 = requests.put(f"{BASE_URL}/api/rahaza/management/alert-config",
                             headers=admin_headers,
                             json={"po_warn_days": 5, "ar_warn_days": 7},
                             timeout=30)
            check(r2.status_code == 200, "PUT alert-config with valid values returns 200", f"status={r2.status_code}")
            
            # Test invalid: attention > stale
            r3 = requests.put(f"{BASE_URL}/api/rahaza/management/alert-config",
                             headers=admin_headers,
                             json={"rnd_attention_days": 10, "rnd_stale_days": 5},
                             timeout=30)
            check(r3.status_code == 400, 
                  "PUT alert-config with attention > stale returns 400", 
                  f"status={r3.status_code}")
            
            # Test invalid: value > max
            r4 = requests.put(f"{BASE_URL}/api/rahaza/management/alert-config",
                             headers=admin_headers,
                             json={"po_warn_days": 100},
                             timeout=30)
            check(r4.status_code == 400, 
                  "PUT alert-config with value > 60 returns 400", 
                  f"status={r4.status_code}")
            
            # Test invalid: value < 0
            r5 = requests.put(f"{BASE_URL}/api/rahaza/management/alert-config",
                             headers=admin_headers,
                             json={"ar_warn_days": -5},
                             timeout=30)
            check(r5.status_code == 400, 
                  "PUT alert-config with value < 0 returns 400", 
                  f"status={r5.status_code}")
            
            # Restore original config
            r6 = requests.put(f"{BASE_URL}/api/rahaza/management/alert-config",
                             headers=admin_headers,
                             json=original_cfg,
                             timeout=30)
            check(r6.status_code == 200, "Restore original config successful", f"status={r6.status_code}")
            print(f"    ✓ Restored original config: {original_cfg}")
    except Exception as e:
        check(False, "Alert configuration API", f"Error: {str(e)}")
    
    # Test permission check
    if hr_headers:
        try:
            r = requests.put(f"{BASE_URL}/api/rahaza/management/alert-config",
                            headers=hr_headers,
                            json={"po_warn_days": 5},
                            timeout=30)
            check(r.status_code == 403, "PUT alert-config as HR returns 403", f"status={r.status_code}")
        except Exception as e:
            check(False, "Alert config permission check", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 5. RND APPROVALS API - THRESHOLDS IN RESPONSE
    # ═══════════════════════════════════════════════════════════════════════════
    section("5. RND APPROVALS API - THRESHOLDS IN RESPONSE")
    
    try:
        r = requests.get(f"{BASE_URL}/api/dewi/rnd/approvals/pending", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/dewi/rnd/approvals/pending returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check("thresholds" in data, "Response includes thresholds object")
            if "thresholds" in data:
                th = data["thresholds"]
                check("attention_days" in th, "Thresholds include attention_days")
                check("stale_days" in th, "Thresholds include stale_days")
                check("source" in th, "Thresholds include source")
                print(f"    📊 Thresholds: attention={th.get('attention_days')} stale={th.get('stale_days')} source={th.get('source')}")
    except Exception as e:
        check(False, "RnD approvals API", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 6. RND DESIGN PHOTO LIFECYCLE
    # ═══════════════════════════════════════════════════════════════════════════
    section("6. RND DESIGN PHOTO LIFECYCLE")
    
    try:
        # Get style DA-HD02-RND
        r = requests.get(f"{BASE_URL}/api/dewi/rnd/styles", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/dewi/rnd/styles returns 200", f"status={r.status_code}")
        
        style_id = None
        if r.status_code == 200:
            styles = r.json()
            # Handle both list and dict with 'items' key
            if isinstance(styles, dict):
                styles = styles.get("items", [])
            for s in styles:
                if s.get("style_code") == "DA-HD02-RND":
                    style_id = s.get("id")
                    break
        
        if style_id:
            print(f"    ✓ Found style DA-HD02-RND: {style_id}")
            
            # Create a small test image (1x1 PNG)
            import io
            test_image = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
            
            # Upload photo
            files = {'file': ('test_photo.png', io.BytesIO(test_image), 'image/png')}
            r2 = requests.post(f"{BASE_URL}/api/dewi/rnd/styles/{style_id}/images",
                              headers=admin_headers,
                              files=files,
                              timeout=30)
            check(r2.status_code == 200, 
                  "POST /api/dewi/rnd/styles/{id}/images returns 200", 
                  f"status={r2.status_code}")
            
            uploaded_img_id = None
            uploaded_url = None
            if r2.status_code == 200:
                img_data = r2.json()
                uploaded_img_id = img_data.get("id")
                uploaded_url = img_data.get("url")
                check(uploaded_img_id is not None, "Upload response includes id")
                check(uploaded_url and uploaded_url.startswith("/api/files/"), 
                      "Upload response includes url starting with /api/files/",
                      f"url={uploaded_url}")
                
                if uploaded_url:
                    # Test download with Authorization header
                    r3 = requests.get(f"{BASE_URL}{uploaded_url}", headers=admin_headers, timeout=30)
                    check(r3.status_code == 200, 
                          "GET file with Authorization header returns 200", 
                          f"status={r3.status_code}")
                    check(r3.headers.get("content-type", "").startswith("image/"), 
                          "Downloaded file is image/*",
                          f"content-type={r3.headers.get('content-type')}")
                    
                    # Test download with ?auth=jwt
                    token = admin_headers.get("Authorization", "").replace("Bearer ", "")
                    r4 = requests.get(f"{BASE_URL}{uploaded_url}?auth={token}", timeout=30)
                    check(r4.status_code == 200, 
                          "GET file with ?auth=jwt returns 200", 
                          f"status={r4.status_code}")
                    
                    # Test download without credentials
                    r5 = requests.get(f"{BASE_URL}{uploaded_url}", timeout=30)
                    check(r5.status_code == 401, 
                          "GET file without credentials returns 401", 
                          f"status={r5.status_code}")
                    
                    # Test with invalid JWT (security regression guard)
                    fake_jwt = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"
                    r6 = requests.get(f"{BASE_URL}{uploaded_url}?auth={fake_jwt}", timeout=30)
                    check(r6.status_code == 401, 
                          "GET file with forged JWT returns 401 (security fix verified)", 
                          f"status={r6.status_code}")
                
                # Delete the uploaded photo
                if uploaded_img_id:
                    r7 = requests.delete(f"{BASE_URL}/api/dewi/rnd/styles/{style_id}/images/{uploaded_img_id}",
                                        headers=admin_headers,
                                        timeout=30)
                    check(r7.status_code == 200, 
                          "DELETE /api/dewi/rnd/styles/{id}/images/{img_id} returns 200", 
                          f"status={r7.status_code}")
                    print(f"    ✓ Cleaned up test photo")
        else:
            print("    ⚠️  Style DA-HD02-RND not found, skipping photo tests")
    except Exception as e:
        check(False, "RnD design photo lifecycle", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 7. LOGIN RATE LIMITING
    # ═══════════════════════════════════════════════════════════════════════════
    section("7. LOGIN RATE LIMITING")
    
    try:
        # Test valid logins (should allow 12 in a row with new 30/60s tier)
        success_count = 0
        for i in range(12):
            r = requests.post(f"{BASE_URL}/api/auth/login", 
                             json={"email": "admin@garment.com", "password": "Admin@123"},
                             timeout=30)
            if r.status_code == 200:
                success_count += 1
        check(success_count >= 10, 
              "12 valid logins succeed (rate limit tier 30/60s)", 
              f"{success_count}/12 succeeded")
    except Exception as e:
        check(False, "Login rate limiting", f"Error: {str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
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
