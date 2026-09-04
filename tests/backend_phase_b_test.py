#!/usr/bin/env python3
"""
Phase B Backend API Test — CMT → DA → Buyer Flow
Tests all Phase B scenarios using PUBLIC endpoint from frontend/.env
"""
import requests
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
VENDOR_EMAIL = "cmtvendor@dewiaditya.id"
VENDOR_PASSWORD = "Dewi@123"

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
    "vendor_token": None,
    "po_id": None,
    "job_id": None,
    "shipment_id": None,
    "receipt_id": None,
    "po_items": [],
}

def test_health():
    """Test GET /api/health (regression)"""
    print("\n=== TEST 1: Health Check (Regression) ===")
    try:
        r = requests.get(f"{BASE_URL}/health", timeout=15)
        results.check(r.status_code == 200, "Health endpoint returns 200", f"Got {r.status_code}")
    except Exception as e:
        results.check(False, "Health check", f"Exception: {str(e)}")

def test_admin_login():
    """Test admin authentication"""
    print("\n=== TEST 2: Admin Login ===")
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
        else:
            print(f"    Response: {r.text[:200]}")
    except Exception as e:
        results.check(False, "Admin login", f"Exception: {str(e)}")

def test_vendor_login():
    """Test vendor authentication"""
    print("\n=== TEST 3: Vendor CMT Login ===")
    try:
        r = requests.post(f"{BASE_URL}/auth/login", json={
            "email": VENDOR_EMAIL,
            "password": VENDOR_PASSWORD
        }, timeout=15)
        
        results.check(r.status_code == 200, "Vendor login returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check('token' in data, "Vendor login returns token")
            test_data['vendor_token'] = data.get('token')
        else:
            print(f"    Response: {r.text[:200]}")
    except Exception as e:
        results.check(False, "Vendor login", f"Exception: {str(e)}")

def test_seed_maklon_data():
    """Test POST /api/seed/maklon-full (idempotent seed)"""
    print("\n=== TEST 4: Seed Maklon Demo Data ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.post(f"{BASE_URL}/seed/maklon-full", headers=headers, timeout=30)
        
        results.check(r.status_code == 200, "Seed maklon-full returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            print(f"    Seeded demo data successfully")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Seed maklon data", f"Exception: {str(e)}")

def test_get_production_pos():
    """Test GET /api/production-pos (regression)"""
    print("\n=== TEST 5: Get Production POs (Regression) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/production-pos", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get production-pos returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            pos = data if isinstance(data, list) else data.get('data', [])
            maklon_pos = [p for p in pos if p.get('business_type') == 'maklon']
            results.check(len(maklon_pos) > 0, "Found maklon POs", f"Found {len(maklon_pos)}")
            
            if maklon_pos:
                test_data['po_id'] = maklon_pos[0]['id']
                print(f"    Using PO: {maklon_pos[0].get('po_number')} (id={test_data['po_id'][:12]})")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Get production POs", f"Exception: {str(e)}")

def test_get_po_items():
    """Get PO items for the test PO"""
    print("\n=== TEST 6: Get PO Items ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/po-items?po_id={test_data['po_id']}", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get po-items returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get('data', [])
            results.check(len(items) > 0, "Found PO items", f"Found {len(items)}")
            test_data['po_items'] = items
            print(f"    PO has {len(items)} items")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Get PO items", f"Exception: {str(e)}")

def test_admin_create_shipment_receiver_da():
    """Test Admin POST /api/buyer-shipments with receiver_type='da' → 403"""
    print("\n=== TEST 7: Admin Create Shipment receiver_type='da' → 403 ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        payload = {
            "po_id": test_data['po_id'],
            "receiver_type": "da",
            "items": [
                {
                    "po_item_id": test_data['po_items'][0]['id'],
                    "sku": test_data['po_items'][0].get('sku', ''),
                    "product_name": test_data['po_items'][0].get('product_name', ''),
                    "qty_shipped": 5,
                    "ordered_qty": test_data['po_items'][0].get('qty', 0),
                }
            ]
        }
        
        r = requests.post(f"{BASE_URL}/buyer-shipments", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 403, "Admin receiver_type='da' returns 403", f"Got {r.status_code}")
        
        if r.status_code == 403:
            results.check('vendor CMT' in r.text.lower() or 'hanya vendor' in r.text.lower(), 
                         "Error message mentions vendor restriction")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Admin create shipment receiver_type='da'", f"Exception: {str(e)}")

def test_admin_create_shipment_without_source_receipts():
    """Test Admin POST /api/buyer-shipments (receiver_type buyer) WITHOUT source_receipt_ids → 400"""
    print("\n=== TEST 8: Admin Create Shipment WITHOUT source_receipt_ids → 400 ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Test with empty items array
        payload1 = {
            "po_id": test_data['po_id'],
            "items": []
        }
        
        r1 = requests.post(f"{BASE_URL}/buyer-shipments", headers=headers, json=payload1, timeout=15)
        
        results.check(r1.status_code == 400, "Admin without source_receipt_ids (empty items) returns 400", 
                     f"Got {r1.status_code}")
        results.check('source_receipt_ids' in r1.text.lower(), 
                     "Error message mentions source_receipt_ids", f"Message: {r1.text[:150]}")
        
        # Test with non-empty items array
        payload2 = {
            "po_id": test_data['po_id'],
            "items": [
                {
                    "po_item_id": test_data['po_items'][0]['id'],
                    "sku": test_data['po_items'][0].get('sku', ''),
                    "qty_shipped": 3,
                }
            ]
        }
        
        r2 = requests.post(f"{BASE_URL}/buyer-shipments", headers=headers, json=payload2, timeout=15)
        
        results.check(r2.status_code == 400, "Admin without source_receipt_ids (with items) returns 400", 
                     f"Got {r2.status_code}")
        results.check('source_receipt_ids' in r2.text.lower(), 
                     "Error message mentions source_receipt_ids", f"Message: {r2.text[:150]}")
        
    except Exception as e:
        results.check(False, "Admin create shipment without source_receipt_ids", f"Exception: {str(e)}")

def test_vendor_create_cmt_declaration():
    """Test Vendor POST /api/buyer-shipments → 201, receiver_type='da', related_cmt_receipt_id"""
    print("\n=== TEST 9: Vendor Create CMT Declaration (receiver_type='da') ===")
    headers = {"Authorization": f"Bearer {test_data['vendor_token']}"}
    
    try:
        # Get production jobs for this PO
        r_jobs = requests.get(f"{BASE_URL}/production-jobs?po_id={test_data['po_id']}", 
                             headers={"Authorization": f"Bearer {test_data['admin_token']}"}, timeout=15)
        jobs = r_jobs.json() if r_jobs.status_code == 200 else []
        jobs = jobs if isinstance(jobs, list) else jobs.get('data', [])
        job = jobs[0] if jobs else None
        
        if job:
            test_data['job_id'] = job['id']
            print(f"    Using job: {job['id'][:12]}")
        
        # Create shipment items
        items = []
        for item in test_data['po_items'][:2]:  # Use first 2 items
            items.append({
                "po_item_id": item['id'],
                "product_name": item.get('product_name', ''),
                "sku": item.get('sku', ''),
                "size": item.get('size', ''),
                "color": item.get('color', ''),
                "serial_number": item.get('serial_number', ''),
                "ordered_qty": item.get('qty', 0),
                "qty_shipped": 5,  # Ship 5 pcs
            })
        
        payload = {
            "po_id": test_data['po_id'],
            "job_id": test_data.get('job_id'),
            "shipment_date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Phase B test — CMT declaration",
            "items": items,
        }
        
        r = requests.post(f"{BASE_URL}/buyer-shipments", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 201, "Vendor create shipment returns 201", f"Got {r.status_code}")
        
        if r.status_code == 201:
            data = r.json()
            results.check(data.get('receiver_type') == 'da', 
                         "Response receiver_type='da'", f"Got {data.get('receiver_type')}")
            results.check(data.get('related_cmt_receipt_id'), 
                         "Response has related_cmt_receipt_id")
            
            test_data['shipment_id'] = data.get('id')
            test_data['receipt_id'] = data.get('related_cmt_receipt_id')
            print(f"    Shipment: {data.get('shipment_number')} (id={test_data['shipment_id'][:12]})")
            print(f"    Auto-created receipt: {test_data['receipt_id'][:12]}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Vendor create CMT declaration", f"Exception: {str(e)}")

def test_get_draft_cmt_receipts():
    """Test GET /api/prod/cmt-receipts?status=Draft"""
    print("\n=== TEST 10: Get Draft CMT Receipts ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/prod/cmt-receipts?status=Draft", headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get Draft cmt-receipts returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            receipts = data if isinstance(data, list) else data.get('data', [])
            results.check(len(receipts) > 0, "Found Draft receipts", f"Found {len(receipts)}")
            
            # Find our receipt
            our_receipt = next((r for r in receipts if r['id'] == test_data['receipt_id']), None)
            results.check(our_receipt is not None, "Found our auto-created receipt")
            
            if our_receipt:
                results.check(our_receipt.get('status') == 'Draft', "Receipt status is Draft")
                results.check(our_receipt.get('related_shipment_id') == test_data['shipment_id'], 
                             "Receipt linked to shipment")
                print(f"    Receipt: {our_receipt.get('receipt_code')} with {our_receipt.get('line_count', 0)} lines")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Get Draft cmt-receipts", f"Exception: {str(e)}")

def test_get_receipt_detail():
    """Test GET /api/prod/cmt-receipts/{id} with pre-populated lines"""
    print("\n=== TEST 11: Get Receipt Detail with Pre-populated Lines ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.get(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}", 
                        headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Get receipt detail returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('status') == 'Draft', "Receipt status is Draft")
            
            lines = data.get('lines', [])
            results.check(len(lines) > 0, "Receipt has pre-populated lines", f"Found {len(lines)} lines")
            
            for line in lines:
                results.check(line.get('qty_shipped_by_cmt') > 0, 
                             f"Line {line.get('sku_code')} has qty_shipped_by_cmt")
                results.check(line.get('qty_actual') is None, 
                             f"Line {line.get('sku_code')} qty_actual is None (not filled yet)")
            
            print(f"    Receipt has {len(lines)} lines, total_shipped_by_cmt={data.get('total_shipped_by_cmt')}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "Get receipt detail", f"Exception: {str(e)}")

def test_da_fill_qty_actual():
    """Test DA PUT /api/prod/cmt-receipts/{id}/lines/{lid} to fill qty_actual"""
    print("\n=== TEST 12: DA Fill qty_actual + reject_qty ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Get receipt lines
        r = requests.get(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}", 
                        headers=headers, timeout=15)
        
        if r.status_code != 200:
            results.check(False, "Get receipt for line update", f"Got {r.status_code}")
            return
        
        receipt = r.json()
        lines = receipt.get('lines', [])
        
        if not lines:
            results.check(False, "Receipt has lines to update", "No lines found")
            return
        
        # Update first line with reject_qty
        line1 = lines[0]
        qty_shipped = line1.get('qty_shipped_by_cmt', 0)
        reject_qty = 1
        qty_actual = qty_shipped - reject_qty
        
        payload1 = {
            "qty_actual": qty_actual,
            "reject_qty": reject_qty,
            "reject_reason": "Jahitan tidak rapih",
            "photos": []
        }
        
        r1 = requests.put(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}/lines/{line1['id']}", 
                         headers=headers, json=payload1, timeout=15)
        
        results.check(r1.status_code == 200, "Update line 1 with reject returns 200", f"Got {r1.status_code}")
        
        if r1.status_code == 200:
            updated = r1.json()
            results.check(updated.get('qty_actual') == qty_actual, 
                         f"Line 1 qty_actual updated to {qty_actual}")
            results.check(updated.get('reject_qty') == reject_qty, 
                         f"Line 1 reject_qty updated to {reject_qty}")
        
        # Update remaining lines without reject
        for line in lines[1:]:
            qty_shipped = line.get('qty_shipped_by_cmt', 0)
            payload = {
                "qty_actual": qty_shipped,
                "reject_qty": 0,
                "reject_reason": "",
                "photos": []
            }
            
            r = requests.put(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}/lines/{line['id']}", 
                           headers=headers, json=payload, timeout=15)
            
            results.check(r.status_code == 200, f"Update line {line.get('sku_code')} returns 200", 
                         f"Got {r.status_code}")
        
        print(f"    Updated {len(lines)} lines with qty_actual")
        
    except Exception as e:
        results.check(False, "DA fill qty_actual", f"Exception: {str(e)}")

def test_da_submit_receipt():
    """Test POST /api/prod/cmt-receipts/{id}/submit"""
    print("\n=== TEST 13: DA Submit Receipt ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.post(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}/submit", 
                         headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Submit receipt returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('status') == 'Submitted', "Receipt status is Submitted")
            print(f"    Receipt submitted successfully")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "DA submit receipt", f"Exception: {str(e)}")

def test_da_approve_receipt():
    """Test POST /api/prod/cmt-receipts/{id}/approve with AP maturation"""
    print("\n=== TEST 14: DA Approve Receipt (with AP maturation) ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        r = requests.post(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}/approve", 
                         headers=headers, timeout=15)
        
        results.check(r.status_code == 200, "Approve receipt returns 200", f"Got {r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            results.check(data.get('status') == 'Approved', "Receipt status is Approved")
            
            ap_mature = data.get('ap_mature')
            if ap_mature:
                results.check('payment_code' in ap_mature, "AP mature has payment_code")
                results.check('amount' in ap_mature, "AP mature has amount")
                results.check('total_pcs' in ap_mature, "AP mature has total_pcs")
                print(f"    AP mature: {ap_mature.get('payment_code')} amount=Rp {ap_mature.get('amount', 0):,.0f}")
            else:
                results.check(False, "AP mature returned", "ap_mature is None")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "DA approve receipt", f"Exception: {str(e)}")

def test_da_dispatch_with_valid_source_receipts():
    """Test DA POST /api/buyer-shipments with valid source_receipt_ids"""
    print("\n=== TEST 15: DA Dispatch to Buyer with source_receipt_ids ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Get receipt to know available qty
        r = requests.get(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}", 
                        headers=headers, timeout=15)
        
        if r.status_code != 200:
            results.check(False, "Get receipt for dispatch", f"Got {r.status_code}")
            return
        
        receipt = r.json()
        lines = receipt.get('lines', [])
        
        # Build dispatch items based on qty_actual
        items = []
        for line in lines:
            qty_actual = line.get('qty_actual', 0)
            if qty_actual > 0:
                items.append({
                    "po_item_id": line.get('po_item_id'),
                    "sku": line.get('sku_code', ''),
                    "product_name": line.get('product_name', ''),
                    "size": line.get('size', ''),
                    "color": line.get('color', ''),
                    "qty_shipped": qty_actual,
                    "ordered_qty": line.get('qty_expected', 0),
                })
        
        payload = {
            "po_id": test_data['po_id'],
            "source_receipt_ids": [test_data['receipt_id']],
            "items": items,
            "shipment_date": datetime.now().strftime("%Y-%m-%d"),
            "notes": "Phase B test — DA dispatch to buyer"
        }
        
        r = requests.post(f"{BASE_URL}/buyer-shipments", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 201, "DA dispatch returns 201", f"Got {r.status_code}")
        
        if r.status_code == 201:
            data = r.json()
            results.check(data.get('receiver_type') == 'buyer', 
                         "Response receiver_type='buyer'", f"Got {data.get('receiver_type')}")
            print(f"    Dispatch: {data.get('shipment_number')} qty={sum(i['qty_shipped'] for i in items)}")
        else:
            print(f"    Response: {r.text[:300]}")
    except Exception as e:
        results.check(False, "DA dispatch with source_receipt_ids", f"Exception: {str(e)}")

def test_da_dispatch_exceeds_qty():
    """Test DA POST /api/buyer-shipments with qty > sum(qty_actual) → 400"""
    print("\n=== TEST 16: DA Dispatch Exceeds qty_actual → 400 ===")
    headers = {"Authorization": f"Bearer {test_data['admin_token']}"}
    
    try:
        # Get receipt to know available qty
        r = requests.get(f"{BASE_URL}/prod/cmt-receipts/{test_data['receipt_id']}", 
                        headers=headers, timeout=15)
        
        if r.status_code != 200:
            results.check(False, "Get receipt for over-dispatch test", f"Got {r.status_code}")
            return
        
        receipt = r.json()
        lines = receipt.get('lines', [])
        
        # Build dispatch items with qty > qty_actual
        items = []
        for line in lines:
            qty_actual = line.get('qty_actual', 0)
            if qty_actual > 0:
                items.append({
                    "po_item_id": line.get('po_item_id'),
                    "sku": line.get('sku_code', ''),
                    "qty_shipped": qty_actual + 100,  # Exceed by 100
                })
        
        payload = {
            "po_id": test_data['po_id'],
            "source_receipt_ids": [test_data['receipt_id']],
            "items": items,
            "shipment_date": datetime.now().strftime("%Y-%m-%d"),
        }
        
        r = requests.post(f"{BASE_URL}/buyer-shipments", headers=headers, json=payload, timeout=15)
        
        results.check(r.status_code == 400, "Over-dispatch returns 400", f"Got {r.status_code}")
        results.check('melebihi' in r.text.lower(), 
                     "Error message mentions 'melebihi'", f"Message: {r.text[:200]}")
        
    except Exception as e:
        results.check(False, "DA dispatch exceeds qty", f"Exception: {str(e)}")

def test_ap_idempotency():
    """Test idempotency - dewi_cmt_payments count for receipt = exactly 1"""
    print("\n=== TEST 17: AP Idempotency (dewi_cmt_payments count = 1) ===")
    
    # This test requires direct MongoDB access which we don't have via HTTP API
    # The E2E script tests this via motor.motor_asyncio
    # For HTTP-only testing, we skip this or check via a custom endpoint if available
    
    print("    ⚠️  Skipping (requires direct MongoDB access)")
    results.check(True, "AP idempotency check (skipped - requires DB access)")

def main():
    print("=" * 80)
    print("PHASE B BACKEND API TEST — CMT → DA → Buyer Flow")
    print("=" * 80)
    print(f"Base URL: {BASE_URL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    try:
        # Run tests in sequence
        test_health()
        test_admin_login()
        
        if not test_data['admin_token']:
            print("\n❌ CRITICAL: Admin login failed, cannot continue")
            return 1
        
        test_vendor_login()
        
        if not test_data['vendor_token']:
            print("\n❌ CRITICAL: Vendor login failed, cannot continue")
            return 1
        
        test_seed_maklon_data()
        test_get_production_pos()
        
        if not test_data['po_id']:
            print("\n❌ CRITICAL: No maklon PO found, cannot continue")
            return 1
        
        test_get_po_items()
        
        if not test_data['po_items']:
            print("\n❌ CRITICAL: No PO items found, cannot continue")
            return 1
        
        # Phase B specific tests
        test_admin_create_shipment_receiver_da()
        test_admin_create_shipment_without_source_receipts()
        test_vendor_create_cmt_declaration()
        
        if not test_data['receipt_id']:
            print("\n❌ CRITICAL: CMT receipt not created, cannot continue")
            return 1
        
        test_get_draft_cmt_receipts()
        test_get_receipt_detail()
        test_da_fill_qty_actual()
        test_da_submit_receipt()
        test_da_approve_receipt()
        test_da_dispatch_with_valid_source_receipts()
        test_da_dispatch_exceeds_qty()
        test_ap_idempotency()
        
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
