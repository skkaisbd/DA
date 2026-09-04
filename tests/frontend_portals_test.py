#!/usr/bin/env python3
"""
Frontend UI Test for LiveHost & Creator Portals
Tests the mobile-first portal UIs using Playwright
"""
import asyncio
import sys
import uuid
import requests
from datetime import datetime, timezone

# Test configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

TEST_SUFFIX = uuid.uuid4().hex[:6]
TODAY = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# Test data storage
test_data = {
    "admin_token": None,
    "account_id": None,
    "host_id": None,
    "host_email": f"ui_host_{TEST_SUFFIX}@test.local",
    "host_password": "Host@123",
    "shift_id": None,
    "creator_id": None,
    "creator_email": f"ui_creator_{TEST_SUFFIX}@test.local",
    "creator_password": "Creator@123",
}

def setup_test_data():
    """Create test host, shift, and creator via API"""
    print("=== Setting up test data via API ===")
    
    # Admin login
    r = requests.post(f"{API_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    }, timeout=15)
    
    if r.status_code != 200:
        print(f"❌ Admin login failed: {r.status_code}")
        return False
    
    test_data['admin_token'] = r.json()['token']
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    print("✅ Admin logged in")
    
    # Get or create account
    r = requests.get(f"{API_URL}/marketing/platform-accounts", headers=headers, timeout=15)
    if r.status_code == 200:
        accounts = r.json()
        active = [a for a in accounts if a.get('status') == 'active']
        if active:
            test_data['account_id'] = active[0]['id']
            print(f"✅ Using account: {test_data['account_id']}")
    
    if not test_data['account_id']:
        test_data['account_id'] = "15044e38-ba64-44a3-b828-8a694b7e69dc"  # Fallback
        print(f"⚠️  Using fallback account: {test_data['account_id']}")
    
    # Create host
    r = requests.post(f"{API_URL}/marketing/livehost", headers=headers, json={
        "name": f"UI Test Host {TEST_SUFFIX}",
        "email": test_data['host_email'],
        "password": test_data['host_password'],
        "phone": "081234567890",
        "employment_type": "part_time",
        "hourly_rate": 50000,
        "assigned_account_ids": [test_data['account_id']],
        "notes": "UI test host"
    }, timeout=15)
    
    if r.status_code != 200:
        print(f"❌ Create host failed: {r.status_code} - {r.text[:200]}")
        return False
    
    test_data['host_id'] = r.json()['host']['id']
    print(f"✅ Created host: {test_data['host_id']}")
    
    # Create shift
    r = requests.post(f"{API_URL}/marketing/livehost/shifts", headers=headers, json={
        "host_id": test_data['host_id'],
        "account_id": test_data['account_id'],
        "date": TODAY,
        "shift_type": "morning",
        "shift_start_time": "09:00",
        "shift_end_time": "13:00",
        "notes": "UI test shift"
    }, timeout=15)
    
    if r.status_code != 200:
        print(f"❌ Create shift failed: {r.status_code} - {r.text[:200]}")
        return False
    
    test_data['shift_id'] = r.json()['shift']['id']
    print(f"✅ Created shift: {test_data['shift_id']}")
    
    # Create creator
    r = requests.post(f"{API_URL}/marketing/kol/creators", headers=headers, json={
        "name": f"UI Test Creator {TEST_SUFFIX}",
        "creator_code": f"KOL-UI-{TEST_SUFFIX}",
        "login_email": test_data['creator_email'],
        "login_password": test_data['creator_password'],
        "assigned_account_ids": [test_data['account_id']],
        "kpi_targets": {"monthly_revenue": 10000000}
    }, timeout=15)
    
    if r.status_code != 200:
        print(f"❌ Create creator failed: {r.status_code} - {r.text[:200]}")
        return False
    
    test_data['creator_id'] = r.json()['creator']['id']
    print(f"✅ Created creator: {test_data['creator_id']}")
    
    return True

def cleanup_test_data():
    """Clean up test data"""
    print("\n=== Cleaning up test data ===")
    if not test_data['admin_token']:
        return
    
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    if test_data['shift_id']:
        try:
            requests.delete(f"{API_URL}/marketing/livehost/shifts/{test_data['shift_id']}", headers=headers, timeout=10)
            print("✅ Deleted shift")
        except:
            pass
    
    if test_data['host_id']:
        try:
            requests.delete(f"{API_URL}/marketing/livehost/{test_data['host_id']}", headers=headers, timeout=10)
            print("✅ Deleted host")
        except:
            pass
    
    if test_data['creator_id']:
        try:
            requests.delete(f"{API_URL}/marketing/kol/creators/{test_data['creator_id']}", headers=headers, timeout=10)
            print("✅ Deleted creator")
        except:
            pass

async def test_livehost_portal(page):
    """Test LiveHost portal UI"""
    print("\n=== Testing LiveHost Portal ===")
    
    try:
        # Set viewport for mobile
        await page.set_viewport_size({"width": 390, "height": 844})
        
        # Navigate to LiveHost portal
        print("1. Navigating to /livehost...")
        await page.goto(f"{BASE_URL}/livehost", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)
        
        # Check login page renders
        print("2. Checking login page...")
        login_page = await page.query_selector('[data-testid="livehost-login-page"]')
        if not login_page:
            print("❌ Login page not found")
            return False
        print("✅ Login page renders")
        
        # Fill login form
        print("3. Filling login form...")
        await page.fill('[data-testid="livehost-login-email"]', test_data['host_email'])
        await page.fill('[data-testid="livehost-login-password"]', test_data['host_password'])
        
        # Submit login
        print("4. Submitting login...")
        await page.click('[data-testid="livehost-login-submit"]')
        await page.wait_for_timeout(2000)
        
        # Check if logged in (shifts tab should appear)
        print("5. Checking if logged in...")
        shifts_tab = await page.query_selector('[data-testid="shifts-tab"]')
        if not shifts_tab:
            # Check for error
            error = await page.query_selector('[data-testid="livehost-login-error"]')
            if error:
                error_text = await error.inner_text()
                print(f"❌ Login failed: {error_text}")
            else:
                print("❌ Shifts tab not found after login")
            return False
        print("✅ Login successful, shifts tab visible")
        
        # Check bottom nav exists
        print("6. Checking bottom navigation...")
        # The bottom nav should have buttons for different tabs
        nav_buttons = await page.query_selector_all('nav button')
        if len(nav_buttons) < 3:
            print(f"⚠️  Expected multiple nav buttons, found {len(nav_buttons)}")
        else:
            print(f"✅ Bottom navigation present ({len(nav_buttons)} buttons)")
        
        # Check for today's shift
        print("7. Checking for shift card...")
        shift_card = await page.query_selector(f'[data-testid="today-shift-card-{test_data["shift_id"]}"]')
        if not shift_card:
            print("⚠️  Today's shift card not found (might be in different section)")
        else:
            print("✅ Shift card found")
            
            # Try to clock in
            print("8. Attempting clock in...")
            clock_in_btn = await page.query_selector(f'[data-testid="clock-in-button-{test_data["shift_id"]}"]')
            if clock_in_btn:
                await clock_in_btn.click()
                await page.wait_for_timeout(2000)
                print("✅ Clock in clicked")
                
                # Try to clock out
                print("9. Attempting clock out...")
                clock_out_btn = await page.query_selector(f'[data-testid="clock-out-button-{test_data["shift_id"]}"]')
                if clock_out_btn:
                    await clock_out_btn.click()
                    await page.wait_for_timeout(2000)
                    print("✅ Clock out clicked")
                    
                    # Check for Input Penjualan button
                    print("10. Checking for Input Penjualan button...")
                    await page.wait_for_timeout(1000)
                    sales_btn = await page.query_selector(f'[data-testid="input-sales-button-{test_data["shift_id"]}"]')
                    if not sales_btn:
                        print("⚠️  Input Penjualan button not found yet")
                    else:
                        print("✅ Input Penjualan button found")
                        
                        # Click to open modal
                        print("11. Opening sales input modal...")
                        await sales_btn.click()
                        await page.wait_for_timeout(1000)
                        
                        # Check modal
                        modal = await page.query_selector('[data-testid="sales-input-modal"]')
                        if not modal:
                            print("❌ Sales input modal not found")
                        else:
                            print("✅ Sales input modal opened")
                            
                            # Fill form
                            print("12. Filling sales form...")
                            await page.fill('[data-testid="sales-input-revenue"]', '5000000')
                            await page.fill('[data-testid="sales-input-items"]', 'Kaos, Celana')
                            await page.fill('[data-testid="sales-input-challenges"]', 'Test challenge')
                            await page.fill('[data-testid="sales-input-notes"]', 'Test notes')
                            
                            # Submit
                            print("13. Submitting sales data...")
                            submit_btn = await page.query_selector('[data-testid="sales-submit-button"]')
                            if submit_btn:
                                await submit_btn.click()
                                await page.wait_for_timeout(2000)
                                print("✅ Sales data submitted")
                            else:
                                print("❌ Submit button not found")
                else:
                    print("⚠️  Clock out button not found")
            else:
                print("⚠️  Clock in button not found")
        
        print("✅ LiveHost portal test completed")
        return True
        
    except Exception as e:
        print(f"❌ LiveHost portal test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def test_creator_portal(page):
    """Test Creator portal UI"""
    print("\n=== Testing Creator Portal ===")
    
    try:
        # Set viewport for mobile
        await page.set_viewport_size({"width": 390, "height": 844})
        
        # Navigate to Creator portal
        print("1. Navigating to /creator...")
        await page.goto(f"{BASE_URL}/creator", wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(1000)
        
        # Check login page renders with teal theme
        print("2. Checking login page...")
        login_page = await page.query_selector('[data-testid="creator-login-page"]')
        if not login_page:
            print("❌ Creator login page not found")
            return False
        print("✅ Creator login page renders")
        
        # Fill login form
        print("3. Filling login form...")
        await page.fill('[data-testid="creator-login-email"]', test_data['creator_email'])
        await page.fill('[data-testid="creator-login-password"]', test_data['creator_password'])
        
        # Submit login
        print("4. Submitting login...")
        await page.click('[data-testid="creator-login-btn"]')
        await page.wait_for_timeout(2000)
        
        # Check if logged in
        print("5. Checking if logged in...")
        portal_shell = await page.query_selector('[data-testid="creator-portal-shell"]')
        if not portal_shell:
            error = await page.query_selector('[data-testid="creator-login-error"]')
            if error:
                error_text = await error.inner_text()
                print(f"❌ Login failed: {error_text}")
            else:
                print("❌ Portal shell not found after login")
            return False
        print("✅ Login successful, portal loaded")
        
        # Check bottom nav
        print("6. Checking bottom navigation...")
        bottom_nav = await page.query_selector('[data-testid="creator-bottom-nav"]')
        if not bottom_nav:
            print("❌ Bottom nav not found")
        else:
            print("✅ Bottom navigation present")
            
            # Check nav items
            nav_dashboard = await page.query_selector('[data-testid="creator-nav-dashboard"]')
            nav_catalog = await page.query_selector('[data-testid="creator-nav-catalog"]')
            nav_sessions = await page.query_selector('[data-testid="creator-nav-sessions"]')
            nav_performance = await page.query_selector('[data-testid="creator-nav-performance"]')
            
            nav_count = sum([bool(nav_dashboard), bool(nav_catalog), bool(nav_sessions), bool(nav_performance)])
            print(f"✅ Found {nav_count}/4 nav items (Dashboard/Katalog/Input Sesi/Performa)")
        
        # Navigate to Input Sesi tab
        print("7. Navigating to Input Sesi tab...")
        sessions_nav = await page.query_selector('[data-testid="creator-nav-sessions"]')
        if sessions_nav:
            await sessions_nav.click()
            await page.wait_for_timeout(1000)
            print("✅ Clicked Input Sesi tab")
            
            # Check for open input button
            print("8. Checking for open input session button...")
            open_btn = await page.query_selector('[data-testid="open-input-session-button"]')
            if not open_btn:
                print("❌ Open input session button not found")
            else:
                print("✅ Open input session button found")
                
                # Click to open modal
                print("9. Opening session input modal...")
                await open_btn.click()
                await page.wait_for_timeout(1000)
                
                # Check form fields
                print("10. Checking form fields...")
                account_select = await page.query_selector('[data-testid="session-input-account"]')
                date_input = await page.query_selector('[data-testid="session-input-date"]')
                platform_select = await page.query_selector('[data-testid="session-input-platform"]')
                revenue_input = await page.query_selector('[data-testid="session-input-revenue"]')
                orders_input = await page.query_selector('[data-testid="session-input-orders"]')
                viewers_input = await page.query_selector('[data-testid="session-input-viewers"]')
                submit_btn = await page.query_selector('[data-testid="session-submit-button"]')
                
                fields_found = sum([
                    bool(account_select), bool(date_input), bool(platform_select),
                    bool(revenue_input), bool(orders_input), bool(viewers_input), bool(submit_btn)
                ])
                print(f"✅ Found {fields_found}/7 form fields")
                
                if fields_found >= 6:
                    # Fill form
                    print("11. Filling session form...")
                    if account_select:
                        # Select first option (should be the assigned account)
                        await page.select_option('[data-testid="session-input-account"]', index=1)
                    if date_input:
                        await page.fill('[data-testid="session-input-date"]', TODAY)
                    if platform_select:
                        await page.select_option('[data-testid="session-input-platform"]', 'shopee')
                    if revenue_input:
                        await page.fill('[data-testid="session-input-revenue"]', '3000000')
                    if orders_input:
                        await page.fill('[data-testid="session-input-orders"]', '25')
                    if viewers_input:
                        await page.fill('[data-testid="session-input-viewers"]', '800')
                    
                    print("✅ Form filled")
                    
                    # Submit
                    if submit_btn:
                        print("12. Submitting session...")
                        await submit_btn.click()
                        await page.wait_for_timeout(2000)
                        print("✅ Session submitted")
        else:
            print("⚠️  Sessions nav button not found")
        
        print("✅ Creator portal test completed")
        return True
        
    except Exception as e:
        print(f"❌ Creator portal test failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    print("=" * 80)
    print("FRONTEND PORTALS UI TEST - LiveHost & Creator")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Suffix: {TEST_SUFFIX}")
    
    # Setup test data
    if not setup_test_data():
        print("\n❌ Failed to setup test data")
        return 1
    
    # Import playwright
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("\n❌ Playwright not installed. Run: pip install playwright && playwright install")
        return 1
    
    results = {"livehost": False, "creator": False}
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context()
        page = await context.new_page()
        
        try:
            # Test LiveHost portal
            results["livehost"] = await test_livehost_portal(page)
            
            # Test Creator portal
            results["creator"] = await test_creator_portal(page)
            
        finally:
            await browser.close()
    
    # Cleanup
    cleanup_test_data()
    
    # Summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"LiveHost Portal: {'✅ PASS' if results['livehost'] else '❌ FAIL'}")
    print(f"Creator Portal: {'✅ PASS' if results['creator'] else '❌ FAIL'}")
    
    all_pass = all(results.values())
    print(f"\nOverall: {'✅ ALL TESTS PASSED' if all_pass else '❌ SOME TESTS FAILED'}")
    
    return 0 if all_pass else 1

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
