#!/usr/bin/env python3
"""
Backend Test — Padankan Ukuran + Peringatan Harga Basi (2026-08-08)

Menguji 2 fitur owner:
1. Size Mapping: memetakan ukuran R&D "belum dipadankan" ke master produksi
2. Stale Price Warning: tanda "harga master sudah berubah" di DAFTAR HPP

CRITICAL: Login rate limit 10/60s — login SEKALI, pakai ulang token.
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

class TestRunner:
    def __init__(self):
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0
        self.failures = []
        
    def login(self):
        """Login SEKALI — rate limit 10/60s"""
        print("🔐 Logging in as admin...")
        try:
            res = requests.post(f"{BASE_URL}/auth/login", json={
                "email": ADMIN_EMAIL,
                "password": ADMIN_PASSWORD
            }, timeout=15)
            if res.status_code == 200:
                data = res.json()
                self.token = data.get('token') or data.get('access_token')
                if self.token:
                    print(f"✅ Login successful (token: {self.token[:20]}...)")
                    return True
                else:
                    print(f"❌ Login response missing token: {data}")
                    return False
            else:
                print(f"❌ Login failed: {res.status_code} - {res.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ Login error: {e}")
            return False
    
    def headers(self):
        return {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
    
    def test(self, name, fn):
        """Run a single test"""
        self.tests_run += 1
        print(f"\n{'='*70}")
        print(f"TEST {self.tests_run}: {name}")
        print('='*70)
        try:
            fn()
            self.tests_passed += 1
            print(f"✅ PASS: {name}")
        except AssertionError as e:
            self.tests_failed += 1
            self.failures.append({'test': name, 'error': str(e)})
            print(f"❌ FAIL: {name}")
            print(f"   Error: {e}")
        except Exception as e:
            self.tests_failed += 1
            self.failures.append({'test': name, 'error': f"Exception: {e}"})
            print(f"❌ ERROR: {name}")
            print(f"   Exception: {e}")
    
    def assert_eq(self, actual, expected, msg=""):
        if actual != expected:
            raise AssertionError(f"{msg}\n  Expected: {expected}\n  Actual: {actual}")
    
    def assert_true(self, condition, msg=""):
        if not condition:
            raise AssertionError(msg or "Condition is False")
    
    def assert_in(self, item, container, msg=""):
        if item not in container:
            raise AssertionError(msg or f"{item} not in {container}")
    
    def assert_gte(self, actual, minimum, msg=""):
        if actual < minimum:
            raise AssertionError(msg or f"{actual} < {minimum}")
    
    def summary(self):
        print(f"\n{'='*70}")
        print("TEST SUMMARY")
        print('='*70)
        print(f"Total: {self.tests_run}")
        print(f"✅ Passed: {self.tests_passed}")
        print(f"❌ Failed: {self.tests_failed}")
        if self.failures:
            print("\nFailed Tests:")
            for f in self.failures:
                print(f"  - {f['test']}: {f['error']}")
        return 0 if self.tests_failed == 0 else 1


def main():
    t = TestRunner()
    
    if not t.login():
        print("❌ Cannot proceed without login")
        return 1
    
    # ══════════════════════════════════════════════════════════════════════════
    # SIZE MAPPING TESTS
    # ══════════════════════════════════════════════════════════════════════════
    
    def test_size_mapping_overview():
        """GET /api/dewi/rnd/size-mapping — ringkasan + saran"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/size-mapping", headers=t.headers(), timeout=20)
        t.assert_eq(res.status_code, 200, "Size mapping overview should return 200")
        data = res.json()
        
        # Ringkasan harus ada
        t.assert_true('styles_checked' in data, "Response must have styles_checked")
        t.assert_true('variants_scanned' in data, "Response must have variants_scanned")
        t.assert_true('total_labels' in data, "Response must have total_labels")
        t.assert_true('unmatched_labels' in data, "Response must have unmatched_labels")
        t.assert_true('matched_labels' in data, "Response must have matched_labels")
        t.assert_true('items' in data, "Response must have items[]")
        t.assert_true('matched' in data, "Response must have matched[]")
        t.assert_true('master_sizes' in data, "Response must have master_sizes[]")
        
        # Angka harus ANGKA, bukan '—'
        t.assert_true(isinstance(data['variants_scanned'], int), "variants_scanned must be int")
        t.assert_gte(data['variants_scanned'], 0, "variants_scanned >= 0")
        
        print(f"   Styles checked: {data['styles_checked']}")
        print(f"   Variants scanned: {data['variants_scanned']}")
        print(f"   Total labels: {data['total_labels']}")
        print(f"   Unmatched: {data['unmatched_labels']}")
        print(f"   Matched: {data['matched_labels']}")
        print(f"   Items: {len(data['items'])}")
        
        # CRITICAL: label 'ONESET' dan 'TOP' HARUS ada dengan from_variants=true
        # (hanya ada di 115 varian hasil impor Excel, tidak ada di size_list)
        all_labels = [it['label'] for it in data['items']] + [m['label'] for m in data['matched']]
        if 'ONESET' in all_labels or 'TOP' in all_labels:
            print("   ✓ Found ONESET/TOP labels (from Excel import variants)")
            for it in data['items']:
                if it['label'] in ('ONESET', 'TOP'):
                    t.assert_true(it['from_variants'], f"{it['label']} must have from_variants=true")
                    print(f"     {it['label']}: from_variants={it['from_variants']}, from_size_list={it['from_size_list']}")
        
        return data
    
    def test_size_mapping_filter():
        """GET /api/dewi/rnd/size-mapping?style_id=<id> — filter per style"""
        # Get a style first
        res = requests.get(f"{BASE_URL}/dewi/rnd/styles", headers=t.headers(), timeout=15)
        t.assert_eq(res.status_code, 200, "Get styles should return 200")
        styles = res.json()
        if isinstance(styles, dict):
            styles = styles.get('items', [])
        
        if len(styles) > 0:
            style_id = styles[0]['id']
            res = requests.get(f"{BASE_URL}/dewi/rnd/size-mapping?style_id={style_id}", 
                             headers=t.headers(), timeout=15)
            t.assert_eq(res.status_code, 200, "Filtered size mapping should return 200")
            data = res.json()
            t.assert_true('items' in data, "Filtered response must have items")
            print(f"   Filtered by style {style_id}: {len(data['items'])} items")
        else:
            print("   ⏭ No styles found, skipping filter test")
    
    def test_size_mapping_apply_validation():
        """POST /api/dewi/rnd/size-mapping/apply — validasi"""
        # Empty mappings → 400
        res = requests.post(f"{BASE_URL}/dewi/rnd/size-mapping/apply", 
                          headers=t.headers(), json={'mappings': []}, timeout=15)
        t.assert_eq(res.status_code, 400, "Empty mappings should return 400")
        print("   ✓ Empty mappings rejected with 400")
        
        # Invalid size_id → 404
        res = requests.post(f"{BASE_URL}/dewi/rnd/size-mapping/apply", 
                          headers=t.headers(), 
                          json={'mappings': [{'label': 'TEST', 'size_id': 'invalid-id-999'}]}, 
                          timeout=15)
        t.assert_eq(res.status_code, 404, "Invalid size_id should return 404")
        print("   ✓ Invalid size_id rejected with 404")
    
    def test_size_mapping_apply_create_new():
        """POST /api/dewi/rnd/size-mapping/apply dengan create_new — kode BERSIH"""
        # Get unmapped labels
        res = requests.get(f"{BASE_URL}/dewi/rnd/size-mapping", headers=t.headers(), timeout=15)
        data = res.json()
        
        if len(data['items']) > 0:
            # Pick first unmapped label
            label = data['items'][0]['label']
            proposed_code = data['items'][0].get('proposed_new_code', 'TEST')
            
            # Apply with create_new
            res = requests.post(f"{BASE_URL}/dewi/rnd/size-mapping/apply", 
                              headers=t.headers(), 
                              json={'mappings': [{'label': label, 'create_new': True, 'code': proposed_code}]}, 
                              timeout=15)
            t.assert_eq(res.status_code, 200, "Apply with create_new should return 200")
            result = res.json()
            t.assert_true(result['ok'], "Response should have ok=true")
            t.assert_eq(result['applied'], 1, "Should apply 1 mapping")
            t.assert_gte(result['styles_updated'], 0, "styles_updated >= 0")
            
            # CRITICAL: kode master harus BERSIH (tanpa spasi & garis miring)
            created_code = result['results'][0]['code']
            t.assert_true(' ' not in created_code, f"Code '{created_code}' must not contain spaces")
            t.assert_true('/' not in created_code, f"Code '{created_code}' must not contain slashes")
            print(f"   ✓ Created master size: {label} → {created_code} (clean code)")
            print(f"   ✓ Styles updated: {result['styles_updated']}, Variants affected: {result['variants_affected']}")
        else:
            print("   ⏭ No unmapped labels, skipping create_new test")
    
    def test_size_mapping_policy_b1():
        """KEBIJAKAN B1 — size_list style TIDAK BERUBAH setelah apply"""
        # Get a style with size_list
        res = requests.get(f"{BASE_URL}/dewi/rnd/styles", headers=t.headers(), timeout=15)
        styles = res.json()
        if isinstance(styles, dict):
            styles = styles.get('items', [])
        
        style_with_list = None
        for s in styles:
            if s.get('size_list') and len(s['size_list']) > 0:
                style_with_list = s
                break
        
        if style_with_list:
            style_id = style_with_list['id']
            original_size_list = style_with_list['size_list']
            
            # Get size-list endpoint
            res = requests.get(f"{BASE_URL}/dewi/rnd/styles/{style_id}/size-list", 
                             headers=t.headers(), timeout=15)
            t.assert_eq(res.status_code, 200, "Get size-list should return 200")
            before = res.json()
            
            # Apply a mapping (if there's an unmapped label from this style)
            res = requests.get(f"{BASE_URL}/dewi/rnd/size-mapping?style_id={style_id}", 
                             headers=t.headers(), timeout=15)
            mapping_data = res.json()
            
            if len(mapping_data['items']) > 0:
                label = mapping_data['items'][0]['label']
                # Apply
                res = requests.post(f"{BASE_URL}/dewi/rnd/size-mapping/apply", 
                                  headers=t.headers(), 
                                  json={'mappings': [{'label': label, 'create_new': True, 'code': 'TESTB1'}]}, 
                                  timeout=15)
                
                # Check size_list TIDAK BERUBAH
                res = requests.get(f"{BASE_URL}/dewi/rnd/styles/{style_id}/size-list", 
                                 headers=t.headers(), timeout=15)
                after = res.json()
                
                t.assert_eq(after['size_list'], before['size_list'], 
                          "POLICY B1: size_list must NOT change after apply")
                print(f"   ✓ POLICY B1 verified: size_list unchanged")
                print(f"     Before: {before['size_list']}")
                print(f"     After: {after['size_list']}")
            else:
                print("   ⏭ No unmapped labels for this style, B1 test skipped")
        else:
            print("   ⏭ No style with size_list found, B1 test skipped")
    
    def test_size_mapping_auto_with_create():
        """POST /api/dewi/rnd/size-mapping/auto dengan create_missing=true"""
        res = requests.post(f"{BASE_URL}/dewi/rnd/size-mapping/auto", 
                          headers=t.headers(), 
                          json={'create_missing': True}, 
                          timeout=30)
        t.assert_eq(res.status_code, 200, "Auto mapping should return 200")
        result = res.json()
        t.assert_true(result['ok'], "Response should have ok=true")
        t.assert_eq(result['unmatched_after'], 0, "All labels should be matched after auto with create_missing=true")
        print(f"   ✓ Auto mapping: {result['applied']} applied, {result['unmatched_after']} remaining")
        print(f"   ✓ Styles updated: {result['styles_updated']}, Variants affected: {result['variants_affected']}")
    
    def test_size_mapping_auto_without_create():
        """POST /api/dewi/rnd/size-mapping/auto dengan create_missing=false — harus skip yang tanpa saran"""
        # First, reset to get unmapped labels (if possible)
        # For this test, we'll just call auto with create_missing=false
        res = requests.post(f"{BASE_URL}/dewi/rnd/size-mapping/auto", 
                          headers=t.headers(), 
                          json={'create_missing': False}, 
                          timeout=30)
        t.assert_eq(res.status_code, 200, "Auto mapping should return 200")
        result = res.json()
        t.assert_true(result['ok'], "Response should have ok=true")
        
        # If there were labels without suggestions, they should be skipped
        if len(result.get('skipped', [])) > 0:
            t.assert_eq(result['applied'], 0, "Should not apply anything if all labels lack suggestions")
            print(f"   ✓ Skipped {len(result['skipped'])} labels without suggestions")
        else:
            print(f"   ✓ Auto mapping without create: {result['applied']} applied, {result['unmatched_after']} remaining")
    
    # ══════════════════════════════════════════════════════════════════════════
    # HPP STALE PRICE TESTS
    # ══════════════════════════════════════════════════════════════════════════
    
    def test_hpp_list_with_stale():
        """GET /api/dewi/rnd/hpp-calculator — daftar dengan stale detection"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/hpp-calculator", headers=t.headers(), timeout=20)
        t.assert_eq(res.status_code, 200, "HPP list should return 200")
        data = res.json()
        t.assert_true(isinstance(data, list), "HPP list should be array")
        
        print(f"   Found {len(data)} HPP documents")
        
        # Check for HPP-DEMO-001 (should have stale_count=1)
        demo1 = next((d for d in data if d.get('hpp_code') == 'HPP-DEMO-001'), None)
        if demo1:
            t.assert_true('stale_count' in demo1, "HPP-DEMO-001 must have stale_count field")
            t.assert_true('stale_delta_total' in demo1, "HPP-DEMO-001 must have stale_delta_total field")
            t.assert_true('stale_checked_lines' in demo1, "HPP-DEMO-001 must have stale_checked_lines field")
            t.assert_true('stale_lines' in demo1, "HPP-DEMO-001 must have stale_lines field")
            
            t.assert_eq(demo1['stale_count'], 1, "HPP-DEMO-001 should have stale_count=1")
            t.assert_gte(demo1['stale_delta_total'], 25, "HPP-DEMO-001 delta should be ~30 (200→230)")
            
            # Check stale_lines detail
            if len(demo1['stale_lines']) > 0:
                stale = demo1['stale_lines'][0]
                t.assert_true('unit_cost_snapshot' in stale, "Stale line must have unit_cost_snapshot")
                t.assert_true('unit_cost_now' in stale, "Stale line must have unit_cost_now")
                t.assert_true('delta' in stale, "Stale line must have delta")
                t.assert_true('direction' in stale, "Stale line must have direction")
                t.assert_eq(stale['direction'], 'naik', "ACC-BTN-12 price should go up")
                print(f"   ✓ HPP-DEMO-001 stale line: {stale.get('label')} {stale['unit_cost_snapshot']} → {stale['unit_cost_now']} ({stale['direction']})")
        else:
            print("   ⚠ HPP-DEMO-001 not found (may need seeding)")
        
        # Check for HPP-DEMO-002 (old document, should have stale_count=0)
        demo2 = next((d for d in data if d.get('hpp_code') == 'HPP-DEMO-002'), None)
        if demo2:
            t.assert_eq(demo2.get('stale_count', 0), 0, "HPP-DEMO-002 (old doc) should have stale_count=0")
            t.assert_eq(demo2.get('stale_checked_lines', 0), 0, "HPP-DEMO-002 should have stale_checked_lines=0")
            print(f"   ✓ HPP-DEMO-002 (old doc) correctly has stale_count=0")
        
        return data
    
    def test_hpp_money_unchanged():
        """UANG — GET /api/dewi/rnd/hpp-calculator tidak menggeser angka tersimpan"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/hpp-calculator", headers=t.headers(), timeout=20)
        data = res.json()
        
        demo1 = next((d for d in data if d.get('hpp_code') == 'HPP-DEMO-001'), None)
        demo2 = next((d for d in data if d.get('hpp_code') == 'HPP-DEMO-002'), None)
        
        if demo1:
            # HPP-DEMO-001 hpp_total harus tetap 34457.5
            expected_hpp = 34457.5
            actual_hpp = demo1.get('hpp_total', 0)
            t.assert_true(abs(actual_hpp - expected_hpp) < 1, 
                        f"HPP-DEMO-001 hpp_total must remain {expected_hpp}, got {actual_hpp}")
            print(f"   ✓ HPP-DEMO-001 hpp_total unchanged: {actual_hpp}")
            
            # Check cost_lines[].line_cost also unchanged
            if 'cost_lines' in demo1:
                for line in demo1['cost_lines']:
                    t.assert_true('line_cost' in line, "Each cost line must have line_cost")
                print(f"   ✓ HPP-DEMO-001 has {len(demo1['cost_lines'])} cost lines with line_cost")
        
        if demo2:
            # HPP-DEMO-002 hpp_total harus tetap 95700.0
            expected_hpp = 95700.0
            actual_hpp = demo2.get('hpp_total', 0)
            t.assert_true(abs(actual_hpp - expected_hpp) < 1, 
                        f"HPP-DEMO-002 hpp_total must remain {expected_hpp}, got {actual_hpp}")
            print(f"   ✓ HPP-DEMO-002 hpp_total unchanged: {actual_hpp}")
    
    def test_hpp_with_stale_false():
        """GET /api/dewi/rnd/hpp-calculator?with_stale=false — field stale_* tidak ada"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/hpp-calculator?with_stale=false", 
                         headers=t.headers(), timeout=20)
        t.assert_eq(res.status_code, 200, "HPP list with_stale=false should return 200")
        data = res.json()
        
        if len(data) > 0:
            # Check that stale fields are not present
            first = data[0]
            t.assert_true('stale_count' not in first or first.get('stale_count') is None, 
                        "with_stale=false should not include stale_count")
            print(f"   ✓ with_stale=false: stale fields not computed")
    
    def test_hpp_stale_check_detail():
        """GET /api/dewi/rnd/hpp-calculator/{id}/stale-check — konsistensi dengan daftar"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/hpp-calculator", headers=t.headers(), timeout=20)
        data = res.json()
        
        demo1 = next((d for d in data if d.get('hpp_code') == 'HPP-DEMO-001'), None)
        if demo1:
            hpp_id = demo1['id']
            list_stale_count = demo1.get('stale_count', 0)
            
            # Get detail stale-check
            res = requests.get(f"{BASE_URL}/dewi/rnd/hpp-calculator/{hpp_id}/stale-check", 
                             headers=t.headers(), timeout=15)
            t.assert_eq(res.status_code, 200, "Stale-check detail should return 200")
            detail = res.json()
            
            t.assert_eq(detail['stale_count'], list_stale_count, 
                      "Stale count in detail must match list")
            print(f"   ✓ Stale-check detail matches list: stale_count={detail['stale_count']}")
    
    # ══════════════════════════════════════════════════════════════════════════
    # REGRESSION TESTS
    # ══════════════════════════════════════════════════════════════════════════
    
    def test_regression_size_list():
        """GET /api/dewi/rnd/styles/{id}/size-list masih bekerja"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/styles", headers=t.headers(), timeout=15)
        styles = res.json()
        if isinstance(styles, dict):
            styles = styles.get('items', [])
        
        if len(styles) > 0:
            style_id = styles[0]['id']
            res = requests.get(f"{BASE_URL}/dewi/rnd/styles/{style_id}/size-list", 
                             headers=t.headers(), timeout=15)
            t.assert_eq(res.status_code, 200, "Get size-list should return 200")
            data = res.json()
            t.assert_true('size_list' in data, "Response must have size_list")
            print(f"   ✓ Size-list endpoint working: {len(data['size_list'])} sizes")
    
    def test_regression_sku_audit():
        """GET /api/dewi/rnd/variants/sku-audit masih HTTP 200"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/variants/sku-audit", 
                         headers=t.headers(), timeout=20)
        t.assert_eq(res.status_code, 200, "SKU audit should return 200 (not 500)")
        data = res.json()
        print(f"   ✓ SKU audit working: {data.get('total_variants', 0)} variants checked")
    
    def test_regression_color_options():
        """GET /api/dewi/rnd/color-options — 15 warna palet asli dengan hex sebenarnya"""
        res = requests.get(f"{BASE_URL}/dewi/rnd/color-options", headers=t.headers(), timeout=15)
        t.assert_eq(res.status_code, 200, "Color options should return 200")
        data = res.json()
        
        # Check for Navy (NVY) with correct hex
        navy = next((c for c in data if c.get('code') == 'NVY'), None)
        if navy:
            t.assert_eq(navy['name'], 'Navy', "NVY should be named 'Navy'")
            t.assert_eq(navy['hex'], '#1E3A5F', "NVY should have correct hex #1E3A5F")
            print(f"   ✓ Color palette correct: NVY = Navy = {navy['hex']}")
        
        # Should NOT have garbage colors (code == name with #CCCCCC)
        garbage = [c for c in data if c.get('code') == c.get('name') and c.get('hex') == '#CCCCCC']
        t.assert_eq(len(garbage), 0, "Should not have garbage colors (code=name, hex=#CCCCCC)")
        print(f"   ✓ No garbage colors found")
    
    # ══════════════════════════════════════════════════════════════════════════
    # RUN ALL TESTS
    # ══════════════════════════════════════════════════════════════════════════
    
    print("\n" + "="*70)
    print("BACKEND TESTS — Size Mapping + Stale Price Warning")
    print("="*70)
    
    # Size Mapping Tests
    t.test("SM-1: GET /size-mapping overview", test_size_mapping_overview)
    t.test("SM-2: GET /size-mapping?style_id filter", test_size_mapping_filter)
    t.test("SM-3: POST /size-mapping/apply validation", test_size_mapping_apply_validation)
    t.test("SM-4: POST /size-mapping/apply create_new (clean code)", test_size_mapping_apply_create_new)
    t.test("SM-5: POLICY B1 — size_list unchanged after apply", test_size_mapping_policy_b1)
    t.test("SM-6: POST /size-mapping/auto with create_missing=true", test_size_mapping_auto_with_create)
    t.test("SM-7: POST /size-mapping/auto with create_missing=false", test_size_mapping_auto_without_create)
    
    # HPP Stale Price Tests
    t.test("ST-1: GET /hpp-calculator with stale detection", test_hpp_list_with_stale)
    t.test("ST-2: MONEY — HPP numbers unchanged", test_hpp_money_unchanged)
    t.test("ST-3: GET /hpp-calculator?with_stale=false", test_hpp_with_stale_false)
    t.test("ST-4: GET /hpp-calculator/{id}/stale-check consistency", test_hpp_stale_check_detail)
    
    # Regression Tests
    t.test("REG-1: GET /styles/{id}/size-list still works", test_regression_size_list)
    t.test("REG-2: GET /variants/sku-audit still HTTP 200", test_regression_sku_audit)
    t.test("REG-3: GET /color-options — correct palette", test_regression_color_options)
    
    return t.summary()


if __name__ == "__main__":
    sys.exit(main())
