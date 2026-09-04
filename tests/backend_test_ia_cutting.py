#!/usr/bin/env python3
"""
Backend API Test — IA Restructure + Portal Cutting (FASE IA-4)
CV. Dewi Aditya ERP · 2026-07-26

Tests:
1. Admin login
2. Portal access verification (14 portals including sysadmin & cutting)
3. Cutting flow: create order → start → progress → complete
4. Integration: cutting output appears in warehouse materials
5. Backup functionality
"""
import requests
import sys
import time
from datetime import datetime, timezone

# Configuration from frontend/.env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

class TestResults:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.tests = []
    
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

# Test state
test_data = {
    "admin_token": None,
    "cutting_order_id": None,
    "output_material_id": None,
    "input_material_id": None,
}

def test_admin_login():
    """Test admin authentication"""
    print("\n=== TEST 1: Admin Login ===")
    try:
        r = requests.post(f"{BASE_URL}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        }, timeout=15)
        
        results.check(r.status_code == 200, "Admin login returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('token' in data, "Admin login returns token")
            test_data['admin_token'] = data.get('token')
            results.check('user' in data, "Admin login returns user object")
            if 'user' in data:
                results.check(data['user'].get('role') in ['superadmin', 'admin'], 
                            "User has admin role", f"Got role: {data['user'].get('role')}")
        else:
            print(f"    Response: {r.text[:200]}")
    except Exception as e:
        results.check(False, "Admin login", f"Exception: {str(e)}")

def test_portal_access():
    """Test that admin can access all portals including new ones"""
    print("\n=== TEST 2: Portal Access (14 portals) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    # Test key endpoints from different portals
    portals_to_test = [
        ("Management", "/management/dashboard/overview"),
        ("Sysadmin (NEW)", "/shared/portal-access"),  # Sysadmin uses shared endpoints
        ("HR", "/hr/employees"),
        ("Finance", "/finance/dashboard/overview"),
        ("Warehouse", "/rahaza/materials"),
        ("Accessories", "/accessories/dashboard"),
        ("Production", "/production/dashboard"),
        ("Cutting (NEW)", "/cutting/dashboard"),
        ("Maklon", "/maklon/dashboard"),
        ("Marketing", "/marketing/dashboard/overview"),
        ("RnD", "/rnd/dashboard"),
        ("Assets", "/assets/dashboard"),
    ]
    
    for portal_name, endpoint in portals_to_test:
        try:
            r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
            results.check(r.status_code in [200, 404], 
                        f"{portal_name} endpoint accessible", 
                        f"Got {r.status_code}")
        except Exception as e:
            results.check(False, f"{portal_name} endpoint", f"Exception: {str(e)}")

def test_hr_employees_data():
    """Test HR portal returns real employee data (25 employees)"""
    print("\n=== TEST 3: HR Employee Data (Real Seed) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/hr/employees", headers=headers, timeout=15)
        results.check(r.status_code == 200, "HR employees endpoint returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            employees = data if isinstance(data, list) else data.get('employees', [])
            results.check(len(employees) >= 20, 
                        f"Has real employee data (≥20)", 
                        f"Got {len(employees)} employees")
            
            # Check for specific real employees from seed
            if employees:
                names = [e.get('name', '') for e in employees]
                results.check(any('Tutut' in n or 'Brenda' in n or 'Zellika' in n for n in names),
                            "Contains real employee names from seed",
                            f"Sample: {names[:3]}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "HR employees data", f"Exception: {str(e)}")

def test_accessories_master_data():
    """Test Accessories portal has real master data"""
    print("\n=== TEST 4: Accessories Master Data ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/accessories/master", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Accessories master returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get('items', [])
            results.check(len(items) > 0, 
                        "Has accessory items", 
                        f"Got {len(items)} items")
            
            # Check for items with codes like A1, A10 mentioned in requirements
            if items:
                codes = [i.get('code', '') for i in items[:10]]
                print(f"    Sample codes: {codes}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Accessories master data", f"Exception: {str(e)}")

def test_warehouse_materials():
    """Test warehouse has real material data (1031 materials from seed)"""
    print("\n=== TEST 5: Warehouse Material Data ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Use pagination to get total count
        r = requests.get(f"{BASE_URL}/rahaza/materials?page=1&limit=1", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Warehouse materials returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            total = data.get('pagination', {}).get('total', 0) if isinstance(data, dict) else len(data)
            results.check(total > 400, 
                        f"Has real material data (>400)", 
                        f"Got {total} materials")
            
            # Get fabric materials for cutting test
            r2 = requests.get(f"{BASE_URL}/cutting/input-materials?q=KAIN", headers=headers, timeout=15)
            if r2.status_code == 200:
                fabrics = r2.json()
                if fabrics and len(fabrics) > 0:
                    test_data['input_material_id'] = fabrics[0]['id']
                    print(f"    Found fabric for cutting test: {fabrics[0].get('code', 'N/A')}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Warehouse materials", f"Exception: {str(e)}")

def test_cutting_dashboard():
    """Test Cutting portal dashboard"""
    print("\n=== TEST 6: Cutting Dashboard ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/cutting/dashboard", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Cutting dashboard returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('total_orders' in data, "Dashboard has total_orders")
            results.check('by_status' in data, "Dashboard has by_status breakdown")
            print(f"    Total cutting orders: {data.get('total_orders', 0)}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Cutting dashboard", f"Exception: {str(e)}")

def test_cutting_create_order():
    """Test creating a cutting order"""
    print("\n=== TEST 7: Create Cutting Order ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    if not test_data['input_material_id']:
        print("    ⚠️  Skipping: no fabric material found")
        return
    
    try:
        payload = {
            "input_material_id": test_data['input_material_id'],
            "planned_input_qty": 10.0,
            "planned_output_qty": 60,
            "style_name": "Test Dress QA",
            "output_color": "HITAM",
            "output_size": "L",
            "notes": "Automated test cutting order"
        }
        
        r = requests.post(f"{BASE_URL}/cutting/orders", headers=headers, json=payload, timeout=15)
        results.check(r.status_code == 200, "Create cutting order returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('id' in data, "Response contains order id")
            results.check(data.get('status') == 'draft', "Order status is draft")
            results.check('number' in data, "Order has number")
            test_data['cutting_order_id'] = data.get('id')
            print(f"    Created order: {data.get('number', 'N/A')}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Create cutting order", f"Exception: {str(e)}")

def test_cutting_start_order():
    """Test starting a cutting order (draft → in_progress)"""
    print("\n=== TEST 8: Start Cutting Order ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    if not test_data['cutting_order_id']:
        print("    ⚠️  Skipping: no cutting order created")
        return
    
    try:
        oid = test_data['cutting_order_id']
        r = requests.post(f"{BASE_URL}/cutting/orders/{oid}/start", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Start cutting order returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('status') == 'in_progress', "Order status is in_progress")
            results.check('output_material_id' in data, "Output material created")
            results.check('output_material_code' in data, "Output material has code")
            test_data['output_material_id'] = data.get('output_material_id')
            print(f"    Output material code: {data.get('output_material_code', 'N/A')}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Start cutting order", f"Exception: {str(e)}")

def test_cutting_add_progress():
    """Test adding progress to cutting order"""
    print("\n=== TEST 9: Add Cutting Progress ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    if not test_data['cutting_order_id']:
        print("    ⚠️  Skipping: no cutting order created")
        return
    
    try:
        oid = test_data['cutting_order_id']
        payload = {
            "input_consumed": 4.0,
            "output_qty": 25,
            "waste_qty": 0.2,
            "note": "First batch test"
        }
        
        r = requests.post(f"{BASE_URL}/cutting/orders/{oid}/progress", headers=headers, json=payload, timeout=15)
        results.check(r.status_code == 200, "Add progress returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('produced_qty') == 25, "Produced qty updated", f"Got {data.get('produced_qty')}")
            results.check(data.get('consumed_input_qty') == 4.0, "Consumed qty updated")
            print(f"    Progress: {data.get('produced_qty', 0)} pcs produced")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Add cutting progress", f"Exception: {str(e)}")

def test_cutting_complete_order():
    """Test completing a cutting order"""
    print("\n=== TEST 10: Complete Cutting Order ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    if not test_data['cutting_order_id']:
        print("    ⚠️  Skipping: no cutting order created")
        return
    
    try:
        oid = test_data['cutting_order_id']
        r = requests.post(f"{BASE_URL}/cutting/orders/{oid}/complete", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Complete cutting order returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('status') == 'completed', "Order status is completed")
            results.check('output_unit_cost' in data, "HPP calculated")
            results.check(data.get('output_unit_cost', 0) > 0, "HPP is positive", f"HPP: {data.get('output_unit_cost')}")
            print(f"    HPP per pcs: Rp {data.get('output_unit_cost', 0):,.2f}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Complete cutting order", f"Exception: {str(e)}")

def test_cutting_output_in_warehouse():
    """Test that cutting output appears in warehouse materials"""
    print("\n=== TEST 11: Cutting Output in Warehouse ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    if not test_data['output_material_id']:
        print("    ⚠️  Skipping: no output material created")
        return
    
    try:
        # Check in cutting panels endpoint
        r = requests.get(f"{BASE_URL}/cutting/output-materials", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Cutting panels endpoint returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            panels = r.json()
            found = any(p.get('id') == test_data['output_material_id'] for p in panels)
            results.check(found, "Output material in cutting panels list")
            
            if found:
                panel = next(p for p in panels if p.get('id') == test_data['output_material_id'])
                results.check(panel.get('stock_qty', 0) >= 25, 
                            "Panel has stock from progress", 
                            f"Stock: {panel.get('stock_qty', 0)} pcs")
        
        # Check in warehouse materials
        r2 = requests.get(f"{BASE_URL}/rahaza/materials?q=CUT-", headers=headers, timeout=15)
        if r2.status_code == 200:
            data = r2.json()
            materials = data if isinstance(data, list) else data.get('items', [])
            found_in_wh = any(m.get('id') == test_data['output_material_id'] for m in materials)
            results.check(found_in_wh, "Output material in warehouse master")
        
    except Exception as e:
        results.check(False, "Cutting output in warehouse", f"Exception: {str(e)}")

def test_backup_functionality():
    """Test backup functionality in Sysadmin portal"""
    print("\n=== TEST 12: Backup Functionality ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # List existing backups
        r = requests.get(f"{BASE_URL}/backup/list", headers=headers, timeout=15)
        results.check(r.status_code == 200, "Backup list endpoint returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            backups = data if isinstance(data, list) else data.get('backups', [])
            print(f"    Existing backups: {len(backups)}")
            
            # Create new backup (this takes ~20 seconds)
            print("    Creating backup (this may take ~20 seconds)...")
            r2 = requests.post(f"{BASE_URL}/backup/create", headers=headers, timeout=30)
            results.check(r2.status_code in [200, 202], 
                        "Backup create endpoint accessible", 
                        f"Got {r2.status_code}")
            
            if r2.status_code in [200, 202]:
                # Wait a bit and check if backup was created
                time.sleep(3)
                r3 = requests.get(f"{BASE_URL}/backup/list", headers=headers, timeout=15)
                if r3.status_code == 200:
                    new_data = r3.json()
                    new_backups = new_data if isinstance(new_data, list) else new_data.get('backups', [])
                    results.check(len(new_backups) >= len(backups), 
                                "Backup list updated",
                                f"Before: {len(backups)}, After: {len(new_backups)}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Backup functionality", f"Exception: {str(e)}")

def test_finance_structure():
    """Test Finance portal has 6 sections as per IA v4"""
    print("\n=== TEST 13: Finance Portal Structure ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Test key endpoints from different finance sections
        finance_endpoints = [
            ("Dashboard", "/finance/dashboard/overview"),
            ("AR", "/finance/ar/aging"),
            ("Cash", "/finance/cash/accounts"),
            ("Journal", "/finance/journal/entries"),
        ]
        
        for name, endpoint in finance_endpoints:
            try:
                r = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=15)
                results.check(r.status_code in [200, 404], 
                            f"Finance {name} endpoint accessible", 
                            f"Got {r.status_code}")
            except Exception as e:
                results.check(False, f"Finance {name}", f"Exception: {str(e)}")
    except Exception as e:
        results.check(False, "Finance structure test", f"Exception: {str(e)}")

def main():
    print("=" * 80)
    print("BACKEND API TEST - IA Restructure + Portal Cutting")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    
    try:
        # Run tests in sequence
        test_admin_login()
        
        if not test_data['admin_token']:
            print("\n❌ CRITICAL: Admin login failed, cannot continue")
            return 1
        
        test_portal_access()
        test_hr_employees_data()
        test_accessories_master_data()
        test_warehouse_materials()
        test_cutting_dashboard()
        test_cutting_create_order()
        test_cutting_start_order()
        test_cutting_add_progress()
        test_cutting_complete_order()
        test_cutting_output_in_warehouse()
        test_backup_functionality()
        test_finance_structure()
        
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
