#!/usr/bin/env python3
"""Backend API tests for F6/F9 — Catalog & Order Management (K-8a/K-8b).

Tests the full chain: catalog search → order creation → multi-line reservation → cancellation.
"""
import os
import sys
import requests
from datetime import datetime

BASE = os.environ.get('REACT_APP_BACKEND_URL', 'https://da37-cmt-bridge.preview.emergentagent.com')

class TestRunner:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.token = None
        self.test_order_ids = []

    def login(self):
        """Login as admin and get token."""
        print("\n🔐 Logging in...")
        r = requests.post(f'{BASE}/api/auth/login', json={
            'email': 'admin@garment.com',
            'password': 'Admin@123'
        }, timeout=30)
        if r.status_code != 200:
            print(f"❌ Login failed: HTTP {r.status_code}")
            sys.exit(1)
        self.token = r.json().get('token')
        if not self.token:
            print("❌ No token in login response")
            sys.exit(1)
        print(f"✅ Logged in successfully")

    def headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }

    def test(self, name, fn):
        """Run a single test."""
        print(f"\n🔍 {name}")
        try:
            fn()
            self.passed += 1
            print(f"  ✅ PASS")
        except AssertionError as e:
            self.failed += 1
            print(f"  ❌ FAIL: {e}")
        except Exception as e:
            self.failed += 1
            print(f"  ❌ ERROR: {e}")

    def cleanup(self):
        """Delete test orders created during testing."""
        if not self.test_order_ids:
            return
        print(f"\n🧹 Cleaning up {len(self.test_order_ids)} test orders...")
        for oid in self.test_order_ids:
            try:
                r = requests.delete(f'{BASE}/api/marketing/orders/{oid}', headers=self.headers(), timeout=30)
                if r.status_code in (200, 404):
                    print(f"  ✓ Deleted {oid[:8]}")
            except Exception as e:
                print(f"  ! Failed to delete {oid[:8]}: {e}")

    def summary(self):
        """Print test summary."""
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        print(f"\n{'='*60}")
        print(f"📊 Test Summary: {self.passed}/{total} passed ({pct:.1f}%)")
        print(f"{'='*60}")
        return 0 if self.failed == 0 else 1


def main():
    t = TestRunner()
    t.login()

    # ── F9b — Catalog Item Search (product picker for orders) ────────────────
    def test_catalog_search_basic():
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?limit=20', headers=t.headers(), timeout=30)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}"
        d = r.json()
        assert 'items' in d, "Missing 'items' in response"
        assert 'counts' in d, "Missing 'counts' in response"
        assert d['counts']['sellable'] >= 8, f"Expected ≥8 sellable, got {d['counts']['sellable']}"
        assert d['counts']['blocked'] >= 3, f"Expected ≥3 blocked, got {d['counts']['blocked']}"
        print(f"    → {d['counts']['sellable']} sellable, {d['counts']['blocked']} blocked")

    def test_catalog_search_fields():
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?limit=5', headers=t.headers(), timeout=30)
        d = r.json()
        item = d['items'][0] if d['items'] else {}
        required = ['catalog_item_id', 'sku', 'name', 'available', 'sellable', 'block_reason',
                    'harga_jual', 'hpp', 'margin', 'fg_onhand', 'fg_reserved', 'category_code']
        for f in required:
            assert f in item, f"Missing field '{f}' in item"
        print(f"    → All required fields present")

    def test_catalog_search_blocked_items():
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?limit=50', headers=t.headers(), timeout=30)
        d = r.json()
        blocked = [i for i in d['items'] if not i['sellable']]
        assert len(blocked) >= 3, f"Expected ≥3 blocked items, got {len(blocked)}"
        # Check CLN-0001-HTM-L (0 stock)
        cln_l = next((i for i in blocked if 'CLN-0001-HTM-L' in i['sku']), None)
        assert cln_l is not None, "CLN-0001-HTM-L not found in blocked items"
        assert 'Stok jual habis' in cln_l['block_reason'], f"Wrong block reason: {cln_l['block_reason']}"
        # Check LEGACY-NOLINK-001 (no master link)
        legacy = next((i for i in blocked if 'LEGACY-NOLINK-001' in i['sku']), None)
        assert legacy is not None, "LEGACY-NOLINK-001 not found in blocked items"
        assert 'Belum tertaut' in legacy['block_reason'], f"Wrong block reason: {legacy['block_reason']}"
        print(f"    → Blocked items have correct reasons")

    def test_catalog_search_filter():
        # Search by name
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?q=hoodie&limit=20', headers=t.headers(), timeout=30)
        d = r.json()
        assert len(d['items']) >= 4, f"Expected ≥4 hoodie items, got {len(d['items'])}"
        assert all('hoodie' in i['name'].lower() for i in d['items']), "Non-hoodie items in results"
        # Filter only sellable
        r2 = requests.get(f'{BASE}/api/marketing/catalog-items/search?only_sellable=true&limit=50', headers=t.headers(), timeout=30)
        d2 = r2.json()
        assert all(i['sellable'] for i in d2['items']), "Non-sellable items in only_sellable=true results"
        print(f"    → Search & filter working")

    t.test("F9b-1: Catalog search returns items with counts", test_catalog_search_basic)
    t.test("F9b-2: Catalog search has all required fields", test_catalog_search_fields)
    t.test("F9b-3: Blocked items have correct reasons", test_catalog_search_blocked_items)
    t.test("F9b-4: Search & filter work correctly", test_catalog_search_filter)

    # ── F9/K-8a — Order Creation (requires catalog_item_id) ──────────────────
    def test_order_create_single_product():
        # Get a sellable product
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?only_sellable=true&limit=1', headers=t.headers(), timeout=30)
        item = r.json()['items'][0]
        
        # Create order
        r2 = requests.post(f'{BASE}/api/marketing/orders', headers=t.headers(), json={
            'platform': 'manual',
            'customer_name': 'Test Customer Single',
            'items': [{
                'catalog_item_id': item['catalog_item_id'],
                'qty': 2,
                'price': item['harga_jual']
            }]
        }, timeout=30)
        assert r2.status_code == 201, f"Expected 201, got {r2.status_code}: {r2.text}"
        d = r2.json()
        assert d['reserved_qty'] == 2.0, f"Expected reserved_qty=2, got {d['reserved_qty']}"
        assert d['linked_line_count'] == 1, f"Expected linked_line_count=1, got {d['linked_line_count']}"
        t.test_order_ids.append(d['id'])
        print(f"    → Order {d['order_id']} created, 2 pcs reserved")

    def test_order_create_multi_product():
        # Get 2 different sellable products
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?only_sellable=true&limit=10', headers=t.headers(), timeout=30)
        items = r.json()['items'][:2]
        assert len(items) == 2, "Need at least 2 sellable products"
        
        # Create order with 2 products
        r2 = requests.post(f'{BASE}/api/marketing/orders', headers=t.headers(), json={
            'platform': 'manual',
            'customer_name': 'Test Customer Multi',
            'items': [
                {'catalog_item_id': items[0]['catalog_item_id'], 'qty': 3, 'price': items[0]['harga_jual']},
                {'catalog_item_id': items[1]['catalog_item_id'], 'qty': 2, 'price': items[1]['harga_jual']}
            ]
        }, timeout=30)
        assert r2.status_code == 201, f"Expected 201, got {r2.status_code}: {r2.text}"
        d = r2.json()
        assert d['reserved_qty'] == 5.0, f"Expected reserved_qty=5, got {d['reserved_qty']}"
        assert d['linked_line_count'] == 2, f"Expected linked_line_count=2, got {d['linked_line_count']}"
        assert d['multi_line_linked'] is True, "Expected multi_line_linked=true"
        # Check each line has reservation
        assert len(d['items']) == 2, f"Expected 2 items, got {len(d['items'])}"
        for i, line in enumerate(d['items']):
            assert line['fg_material_id'], f"Line {i} missing fg_material_id"
            assert line['reserved_qty'] > 0, f"Line {i} not reserved"
        t.test_order_ids.append(d['id'])
        print(f"    → Order {d['order_id']} created, 2 products, 5 pcs total reserved")

    def test_order_reject_unknown_sku():
        # Try to create order with unknown SKU (should fail 400)
        r = requests.post(f'{BASE}/api/marketing/orders', headers=t.headers(), json={
            'platform': 'manual',
            'customer_name': 'Test Customer Bad SKU',
            'items': [{'sku_code': 'UNKNOWN-SKU-999', 'qty': 1, 'price': 100000}]
        }, timeout=30)
        assert r.status_code == 400, f"Expected 400 for unknown SKU, got {r.status_code}"
        assert 'tidak dikenal' in r.text.lower() or 'pilih produk' in r.text.lower(), f"Wrong error message: {r.text}"
        print(f"    → Unknown SKU correctly rejected with 400")

    def test_order_reject_insufficient_stock():
        # Get a product with known stock
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?only_sellable=true&limit=1', headers=t.headers(), timeout=30)
        item = r.json()['items'][0]
        avail = item['available']
        
        # Try to order more than available
        r2 = requests.post(f'{BASE}/api/marketing/orders', headers=t.headers(), json={
            'platform': 'manual',
            'customer_name': 'Test Customer Oversell',
            'items': [{'catalog_item_id': item['catalog_item_id'], 'qty': int(avail) + 100, 'price': item['harga_jual']}]
        }, timeout=30)
        assert r2.status_code == 409, f"Expected 409 for insufficient stock, got {r2.status_code}"
        assert 'tidak cukup' in r2.text.lower() or 'tersedia' in r2.text.lower(), f"Wrong error message: {r2.text}"
        print(f"    → Insufficient stock correctly rejected with 409")

    t.test("F9-1: Create order with single product", test_order_create_single_product)
    t.test("F9-2: Create order with 2 products (K-8b multi-line)", test_order_create_multi_product)
    t.test("F9-3: Reject order with unknown SKU (400)", test_order_reject_unknown_sku)
    t.test("F9-4: Reject order with insufficient stock (409)", test_order_reject_insufficient_stock)

    # ── Order Cancellation (releases reservations) ───────────────────────────
    def test_order_cancel_releases_stock():
        # Create order
        r = requests.get(f'{BASE}/api/marketing/catalog-items/search?only_sellable=true&limit=1', headers=t.headers(), timeout=30)
        item = r.json()['items'][0]
        stock_before = item['available']
        
        r2 = requests.post(f'{BASE}/api/marketing/orders', headers=t.headers(), json={
            'platform': 'manual',
            'customer_name': 'Test Customer Cancel',
            'items': [{'catalog_item_id': item['catalog_item_id'], 'qty': 1, 'price': item['harga_jual']}]
        }, timeout=30)
        order_id = r2.json()['id']
        t.test_order_ids.append(order_id)
        
        # Cancel order
        r3 = requests.patch(f'{BASE}/api/marketing/orders/{order_id}/status', headers=t.headers(), json={
            'status': 'cancelled'
        }, timeout=30)
        assert r3.status_code == 200, f"Expected 200, got {r3.status_code}"
        d = r3.json()
        assert d['reservation_released'] >= 1.0, f"Expected reservation_released≥1, got {d['reservation_released']}"
        
        # Check stock returned
        r4 = requests.get(f'{BASE}/api/marketing/catalog-items/search?limit=50', headers=t.headers(), timeout=30)
        item_after = next((i for i in r4.json()['items'] if i['catalog_item_id'] == item['catalog_item_id']), None)
        assert item_after is not None, "Item not found after cancel"
        assert item_after['available'] >= stock_before, f"Stock not returned: {stock_before} → {item_after['available']}"
        print(f"    → Stock returned after cancel: {stock_before} → {item_after['available']}")

    t.test("F9-5: Cancel order releases stock reservation", test_order_cancel_releases_stock)

    # ── Cleanup & Summary ─────────────────────────────────────────────────────
    t.cleanup()
    return t.summary()


if __name__ == '__main__':
    sys.exit(main())
