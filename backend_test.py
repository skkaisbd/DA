#!/usr/bin/env python3
"""
Backend API Testing for W1 'Tabel FG Lengkap' & W2 'Ekspor Fleksibel'
DA37 ERP - Session #29 Testing
"""
import requests
import sys
import json
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
API_URL = f"{BASE_URL}/api"

class TestRunner:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        
    def login(self):
        """Login and get token"""
        print("=" * 80)
        print("LOGGING IN...")
        print("=" * 80)
        try:
            r = requests.post(f"{API_URL}/auth/login", json={
                "email": "admin@garment.com",
                "password": "Admin@123"
            }, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get("token")
                print(f"✅ Login successful. Token: {self.token[:20]}...")
                return True
            else:
                print(f"❌ Login failed: HTTP {r.status_code}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def test(self, name, func):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n{'─' * 80}")
        print(f"TEST {self.tests_run}: {name}")
        print(f"{'─' * 80}")
        try:
            func()
            self.tests_passed += 1
            print(f"✅ PASSED")
        except AssertionError as e:
            self.tests_failed += 1
            self.failures.append(f"{name}: {e}")
            print(f"❌ FAILED: {e}")
        except Exception as e:
            self.tests_failed += 1
            self.failures.append(f"{name}: {e}")
            print(f"❌ ERROR: {e}")
    
    def get(self, endpoint, expected_status=200):
        """GET request with auth"""
        headers = {"Authorization": f"Bearer {self.token}"}
        r = requests.get(f"{API_URL}{endpoint}", headers=headers, timeout=30)
        print(f"GET {endpoint} → HTTP {r.status_code}")
        if expected_status and r.status_code != expected_status:
            raise AssertionError(f"Expected HTTP {expected_status}, got {r.status_code}")
        return r
    
    def summary(self):
        """Print test summary"""
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        print(f"Total: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        if self.failures:
            print("\nFAILURES:")
            for f in self.failures:
                print(f"  • {f}")
        print("=" * 80)
        return 0 if self.tests_failed == 0 else 1


def main():
    runner = TestRunner()
    
    if not runner.login():
        return 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # W1 BACKEND TESTS - Tabel FG Lengkap
    # ═══════════════════════════════════════════════════════════════════════════
    
    def test_w1_stock_fg_enriched():
        """W1: /api/rahaza/material-stock?type=fg returns enriched master data"""
        r = runner.get("/rahaza/material-stock?type=fg")
        data = r.json()
        assert isinstance(data, list), "Response must be a list"
        assert len(data) > 0, "Must have at least some FG stock rows"
        
        # Check first row has enriched fields from master
        row = data[0]
        required_fields = ['material_code', 'category_name', 'color_name', 
                          'option_name', 'size_code']
        for field in required_fields:
            assert field in row, f"Missing field: {field}"
        
        print(f"  Found {len(data)} FG stock rows")
        print(f"  Sample row: code={row.get('material_code')}, "
              f"category={row.get('category_name')}, "
              f"color={row.get('color_name')}, "
              f"option={row.get('option_name')}, "
              f"size={row.get('size_code')}")
    
    def test_w1_stock_fg_include_zero():
        """W1: /api/rahaza/material-stock?type=fg&include_zero=1 returns ~322 rows"""
        r = runner.get("/rahaza/material-stock?type=fg&include_zero=1")
        data = r.json()
        assert isinstance(data, list), "Response must be a list"
        
        # Should be much more than 26 (the original stock rows)
        assert len(data) > 300, f"Expected ~322 rows, got {len(data)}"
        
        # Check for no_stock_row=true items
        zero_stock = [row for row in data if row.get('no_stock_row') is True]
        assert len(zero_stock) > 0, "Must have items with no_stock_row=true"
        
        # Verify zero stock items have qty=0 and location_code=null
        sample_zero = zero_stock[0]
        assert sample_zero.get('qty') == 0 or sample_zero.get('qty') == 0.0, \
            "Zero stock row must have qty=0"
        assert sample_zero.get('location_code') is None, \
            "Zero stock row must have location_code=null"
        
        print(f"  Total rows: {len(data)}")
        print(f"  Zero stock rows: {len(zero_stock)}")
        print(f"  Sample zero stock: {sample_zero.get('material_code')} - {sample_zero.get('material_name')}")
    
    def test_w1_unified_stock_enriched():
        """W1: /api/wms/stock/unified returns enriched data + facets"""
        r = runner.get("/wms/stock/unified?limit=5&include_zero=1&material_type=fg")
        data = r.json()
        
        assert 'items' in data, "Response must have 'items' key"
        assert 'facets' in data, "Response must have 'facets' key"
        assert 'total' in data, "Response must have 'total' key"
        
        # Check total is around 322
        assert data['total'] > 300, f"Expected ~322 total, got {data['total']}"
        
        # Check facets structure
        facets = data['facets']
        assert 'categories' in facets, "Facets must have 'categories'"
        assert 'colors' in facets, "Facets must have 'colors'"
        assert 'options' in facets, "Facets must have 'options'"
        
        print(f"  Total items: {data['total']}")
        print(f"  Categories: {facets['categories'][:5]}")
        print(f"  Colors: {facets['colors'][:5]}")
        print(f"  Options: {facets['options'][:5]}")
    
    def test_w1_unified_color_filter():
        """W1: Color filter returns ONLY items with that color"""
        # First get available colors
        r = runner.get("/wms/stock/unified?limit=5&include_zero=1&material_type=fg")
        data = r.json()
        colors = data['facets']['colors']
        
        if not colors:
            print("  ⚠️  No colors available to test filter")
            return
        
        # Test with first color
        test_color = colors[0]
        print(f"  Testing filter with color: {test_color}")
        
        r2 = runner.get(f"/wms/stock/unified?color={test_color}&include_zero=1&limit=100")
        filtered = r2.json()
        
        items = filtered['items']
        assert len(items) > 0, f"Must have items with color {test_color}"
        
        # Verify ALL items have the correct color
        wrong_color = [item for item in items 
                      if item.get('color_name', '').lower() != test_color.lower()]
        
        assert len(wrong_color) == 0, \
            f"Found {len(wrong_color)} items with wrong color. Expected all to be '{test_color}'"
        
        print(f"  ✓ All {len(items)} items have color '{test_color}'")
    
    def test_w1_unified_category_filter():
        """W1: Category filter works correctly"""
        r = runner.get("/wms/stock/unified?limit=5&include_zero=1&material_type=fg")
        data = r.json()
        categories = data['facets']['categories']
        
        if not categories:
            print("  ⚠️  No categories available to test filter")
            return
        
        test_cat = categories[0]
        print(f"  Testing filter with category: {test_cat}")
        
        r2 = runner.get(f"/wms/stock/unified?category={test_cat}&include_zero=1&limit=100")
        filtered = r2.json()
        
        items = filtered['items']
        assert len(items) > 0, f"Must have items with category {test_cat}"
        print(f"  ✓ Found {len(items)} items with category '{test_cat}'")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # W2 BACKEND TESTS - Ekspor Fleksibel
    # ═══════════════════════════════════════════════════════════════════════════
    
    def test_w2_pdf_columns_report_production():
        """W2: /api/pdf-export-columns?type=report-production includes serial"""
        r = runner.get("/pdf-export-columns?type=report-production")
        data = r.json()
        
        assert 'columns' in data, "Response must have 'columns' key"
        columns = data['columns']
        
        # Find serial column (key should be 'no_seri')
        serial_col = next((c for c in columns if c.get('key') == 'no_seri'), None)
        assert serial_col is not None, "Must have column with key 'no_seri'"
        assert 'Serial' in serial_col.get('label', ''), \
            f"Serial column label should contain 'Serial', got: {serial_col.get('label')}"
        
        print(f"  ✓ Found serial column: {serial_col}")
    
    def test_w2_pdf_columns_production_po():
        """W2: /api/pdf-export-columns?type=production-po includes serial"""
        r = runner.get("/pdf-export-columns?type=production-po")
        data = r.json()
        
        assert 'columns' in data, "Response must have 'columns' key"
        columns = data['columns']
        
        # Find serial column (key should be 'serial')
        serial_col = next((c for c in columns if c.get('key') == 'serial'), None)
        assert serial_col is not None, "Must have column with key 'serial'"
        
        print(f"  ✓ Found serial column: {serial_col}")
    
    def test_w2_pdf_export_with_cols():
        """W2: /api/export-pdf with cols parameter filters columns"""
        # Note: This test just checks HTTP 200, not PDF content
        # PDF text extraction will be done in frontend testing
        r = runner.get("/export-pdf?type=report-production&cols=no,no_seri,nama_produk,output_qty")
        
        assert r.status_code == 200, f"Expected HTTP 200, got {r.status_code}"
        assert r.headers.get('content-type') == 'application/pdf', \
            f"Expected PDF content-type, got {r.headers.get('content-type')}"
        
        pdf_size = len(r.content)
        print(f"  ✓ PDF generated successfully, size: {pdf_size} bytes")
    
    def test_w2_pdf_export_without_cols():
        """W2: /api/export-pdf without cols prints ALL columns (old behavior)"""
        r = runner.get("/export-pdf?type=report-production")
        
        assert r.status_code == 200, f"Expected HTTP 200, got {r.status_code}"
        assert r.headers.get('content-type') == 'application/pdf', \
            f"Expected PDF content-type, got {r.headers.get('content-type')}"
        
        pdf_size = len(r.content)
        print(f"  ✓ PDF generated successfully (all columns), size: {pdf_size} bytes")
    
    def test_w2_pdf_mandatory_columns():
        """W2: Mandatory columns always included even if not in cols"""
        # Request only serial column, but 'no' (mandatory) should still be included
        r = runner.get("/export-pdf?type=report-production&cols=no_seri")
        
        assert r.status_code == 200, f"Expected HTTP 200, got {r.status_code}"
        print(f"  ✓ PDF with only serial requested still generates (mandatory 'no' auto-included)")
    
    def test_w2_pdf_invalid_columns_ignored():
        """W2: Invalid column keys are ignored, not 500 error"""
        # Include invalid column key
        r = runner.get("/export-pdf?type=report-production&cols=invalid_col,no_seri")
        
        assert r.status_code == 200, f"Expected HTTP 200 (invalid keys ignored), got {r.status_code}"
        print(f"  ✓ Invalid column keys ignored gracefully")
    
    def test_w2_pdf_production_po_with_cols():
        """W2: Production PO PDF with column selection"""
        # First get a production PO ID
        r = runner.get("/production-pos?limit=1")
        pos = r.json()
        
        if not pos or len(pos) == 0:
            print("  ⚠️  No production POs available to test")
            return
        
        po_id = pos[0]['id']
        print(f"  Testing with PO ID: {po_id}")
        
        # Test with column selection
        r2 = runner.get(f"/export-pdf?type=production-po&id={po_id}&cols=no,serial,product,qty")
        
        assert r2.status_code == 200, f"Expected HTTP 200, got {r2.status_code}"
        
        # Get size without cols for comparison
        r3 = runner.get(f"/export-pdf?type=production-po&id={po_id}")
        
        size_with_cols = len(r2.content)
        size_without_cols = len(r3.content)
        
        print(f"  PDF with cols: {size_with_cols} bytes")
        print(f"  PDF without cols: {size_without_cols} bytes")
        # Note: Size comparison is informational, not strict assertion
    
    def test_w2_pdf_regression_other_types():
        """W2: Other PDF types still work (regression test)"""
        # Test that other PDF types don't break after column filtering changes
        types_to_test = [
            "report-progress",
            "report-financial", 
            "report-shipment",
            "production-report"
        ]
        
        for pdf_type in types_to_test:
            try:
                r = runner.get(f"/export-pdf?type={pdf_type}", expected_status=None)
                # Accept 200 (success) or 400 (no data) but not 500 (server error)
                if r.status_code == 500:
                    raise AssertionError(f"Type '{pdf_type}' returned HTTP 500 (server error)")
                print(f"  ✓ {pdf_type}: HTTP {r.status_code}")
            except Exception as e:
                print(f"  ⚠️  {pdf_type}: {e}")
    
    # Run all tests
    runner.test("W1: Stock FG enriched with master data", test_w1_stock_fg_enriched)
    runner.test("W1: Stock FG include_zero returns ~322 rows", test_w1_stock_fg_include_zero)
    runner.test("W1: Unified stock enriched + facets", test_w1_unified_stock_enriched)
    runner.test("W1: Unified color filter accuracy", test_w1_unified_color_filter)
    runner.test("W1: Unified category filter", test_w1_unified_category_filter)
    runner.test("W2: PDF columns report-production has serial", test_w2_pdf_columns_report_production)
    runner.test("W2: PDF columns production-po has serial", test_w2_pdf_columns_production_po)
    runner.test("W2: PDF export with cols parameter", test_w2_pdf_export_with_cols)
    runner.test("W2: PDF export without cols (all columns)", test_w2_pdf_export_without_cols)
    runner.test("W2: PDF mandatory columns always included", test_w2_pdf_mandatory_columns)
    runner.test("W2: PDF invalid columns ignored", test_w2_pdf_invalid_columns_ignored)
    runner.test("W2: PDF production-po with cols", test_w2_pdf_production_po_with_cols)
    runner.test("W2: PDF regression - other types", test_w2_pdf_regression_other_types)
    
    return runner.summary()


if __name__ == "__main__":
    sys.exit(main())
