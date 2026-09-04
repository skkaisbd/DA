#!/usr/bin/env python3
"""
Backend test for Returns Bridge (W4 Session #29)
Tests the connection between Marketing returns and Warehouse returns with automatic restocking.
"""
import requests
import sys
import uuid
from datetime import datetime

# Public endpoint from frontend/.env
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class ReturnsBridgeTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_data = {
            "marketing_return_ids": [],
            "wh_return_ids": [],
            "material_id": None,
            "catalog_item_id": None,
        }

    def log(self, status, test_name, detail=""):
        """Log test result"""
        self.tests_run += 1
        symbol = "✓" if status else "✗"
        color = "\033[92m" if status else "\033[91m"
        reset = "\033[0m"
        if status:
            self.tests_passed += 1
        print(f"  {color}{symbol}{reset} {test_name}" + (f" · {detail}" if detail else ""))
        return status

    def api_call(self, method, endpoint, data=None, expected_status=200):
        """Make API call and return response"""
        url = f"{self.base_url}{endpoint}"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        
        try:
            if method == "GET":
                resp = requests.get(url, headers=headers, timeout=30)
            elif method == "POST":
                resp = requests.post(url, headers=headers, json=data, timeout=30)
            elif method == "PUT":
                resp = requests.put(url, headers=headers, json=data, timeout=30)
            elif method == "DELETE":
                resp = requests.delete(url, headers=headers, timeout=30)
            else:
                return None, f"Unknown method: {method}"
            
            if resp.status_code != expected_status:
                return None, f"Expected {expected_status}, got {resp.status_code}: {resp.text[:200]}"
            
            try:
                return resp.json(), None
            except Exception:
                return resp.text, None
        except Exception as e:
            return None, str(e)

    def test_login(self):
        """Test login with admin credentials"""
        print("\n=== Authentication ===")
        data, err = self.api_call("POST", "/api/auth/login", {
            "email": "admin@garment.com",
            "password": "Admin@123"
        })
        
        if err or not data or "token" not in data:
            self.log(False, "Login", f"Failed: {err or 'No token in response'}")
            return False
        
        self.token = data["token"]
        self.log(True, "Login", "Successfully authenticated as admin@garment.com")
        return True

    def test_marketing_gap(self):
        """Test GET /api/wh/returns/marketing-gap"""
        print("\n=== Test Marketing Gap Endpoint ===")
        data, err = self.api_call("GET", "/api/wh/returns/marketing-gap")
        
        if err:
            return self.log(False, "GET /api/wh/returns/marketing-gap", err)
        
        required_fields = ["marketing_returns_total", "already_bridged", "pending_bridge", 
                          "wh_returns_total", "restocked", "needs_link"]
        missing = [f for f in required_fields if f not in data]
        
        if missing:
            return self.log(False, "Marketing gap response", f"Missing fields: {missing}")
        
        # Store initial state
        self.test_data["initial_gap"] = data
        return self.log(True, "GET /api/wh/returns/marketing-gap", 
                       f"mkt_total={data['marketing_returns_total']}, wh_total={data['wh_returns_total']}, "
                       f"pending={data['pending_bridge']}, restocked={data['restocked']}")

    def test_sync_dry_run(self):
        """Test POST /api/wh/returns/sync-marketing with dry_run=true"""
        print("\n=== Test Sync Dry Run (No Writes) ===")
        
        # Get current counts
        gap_before, err = self.api_call("GET", "/api/wh/returns/marketing-gap")
        if err:
            return self.log(False, "Get gap before dry run", err)
        
        wh_count_before = gap_before["wh_returns_total"]
        
        # Run dry run
        data, err = self.api_call("POST", "/api/wh/returns/sync-marketing", {"dry_run": True})
        if err:
            return self.log(False, "POST /api/wh/returns/sync-marketing (dry_run)", err)
        
        # Check counts after
        gap_after, err = self.api_call("GET", "/api/wh/returns/marketing-gap")
        if err:
            return self.log(False, "Get gap after dry run", err)
        
        wh_count_after = gap_after["wh_returns_total"]
        
        if wh_count_after != wh_count_before:
            return self.log(False, "Dry run should not write", 
                          f"wh_returns changed from {wh_count_before} to {wh_count_after}")
        
        return self.log(True, "POST /api/wh/returns/sync-marketing (dry_run=true)", 
                       f"No writes: wh_returns={wh_count_before}")

    def test_sync_apply_idempotent(self):
        """Test POST /api/wh/returns/sync-marketing (apply) - should be idempotent"""
        print("\n=== Test Sync Apply (Idempotent) ===")
        
        data, err = self.api_call("POST", "/api/wh/returns/sync-marketing", {})
        if err:
            return self.log(False, "POST /api/wh/returns/sync-marketing (apply)", err)
        
        result = data.get("data", {})
        
        # Should be idempotent - created=0, already=22 (or similar)
        if result.get("created", 0) > 0:
            return self.log(False, "Sync should be idempotent", 
                          f"created={result.get('created')} (expected 0)")
        
        return self.log(True, "POST /api/wh/returns/sync-marketing (apply)", 
                       f"Idempotent: created={result.get('created')}, already={result.get('already')}, "
                       f"restocked={result.get('restocked')}")

    def setup_test_material(self):
        """Get a valid FG material and catalog item for testing"""
        print("\n=== Setup Test Data ===")
        
        # Get FG materials
        data, err = self.api_call("GET", "/api/rahaza/materials?type=fg")
        if err or not data:
            self.log(False, "Get FG materials", err or "No materials found")
            return False
        
        materials = data if isinstance(data, list) else data.get("items", [])
        if not materials:
            self.log(False, "Get FG materials", "No FG materials in database")
            return False
        
        # Find a material with catalog item
        for mat in materials[:10]:  # Check first 10
            mat_id = mat.get("id")
            if not mat_id:
                continue
            
            # Check if this material has a catalog item
            cat_data, cat_err = self.api_call("GET", f"/api/marketing/catalog/items?fg_material_id={mat_id}")
            if not cat_err and cat_data:
                items = cat_data.get("items", []) if isinstance(cat_data, dict) else cat_data
                if items and len(items) > 0:
                    self.test_data["material_id"] = mat_id
                    self.test_data["catalog_item_id"] = items[0].get("id")
                    self.test_data["material_code"] = mat.get("code") or mat.get("sku")
                    self.log(True, "Setup test material", 
                            f"material_id={mat_id[:8]}..., code={self.test_data['material_code']}")
                    return True
        
        self.log(False, "Setup test material", "No FG material with catalog item found")
        return False

    def test_create_return_baik(self):
        """Test POST /api/marketing/returns with condition='Baik'"""
        print("\n=== Test Create Return (Condition: Baik) ===")
        
        if not self.test_data.get("catalog_item_id"):
            return self.log(False, "Create return (Baik)", "No catalog item available")
        
        # Get a marketing account
        acc_data, err = self.api_call("GET", "/api/marketing/accounts")
        if err or not acc_data:
            return self.log(False, "Get marketing account", err or "No accounts")
        
        accounts = acc_data if isinstance(acc_data, list) else acc_data.get("accounts", [])
        if not accounts:
            return self.log(False, "Get marketing account", "No active accounts")
        
        account = accounts[0]
        
        # Create return with condition Baik
        return_data = {
            "account_id": account.get("id"),
            "date": datetime.now().date().isoformat(),
            "order_id": f"TEST-{uuid.uuid4().hex[:8]}",
            "catalog_item_id": self.test_data["catalog_item_id"],
            "price": 100000,
            "qty": 2,
            "item_condition": "Baik",
            "reason": "produk_cacat",
            "reason_detail": "Test return - condition Baik",
            "courier": "jnt",
            "refund_type": "full_refund"
        }
        
        data, err = self.api_call("POST", "/api/marketing/returns", return_data, expected_status=200)
        if err:
            return self.log(False, "POST /api/marketing/returns (Baik)", err)
        
        ret = data.get("data", {})
        wh_info = data.get("warehouse", {})
        
        self.test_data["marketing_return_ids"].append(ret.get("id"))
        
        # Verify warehouse return was created
        if not wh_info.get("wh_return_code"):
            return self.log(False, "Warehouse return creation", "No wh_return_code in response")
        
        # Verify restocked
        if not wh_info.get("restocked"):
            return self.log(False, "Auto restock (Baik)", "restocked=False")
        
        # Verify stock effect is sellable
        if wh_info.get("stock_effect") != "sellable":
            return self.log(False, "Stock effect (Baik)", f"Expected 'sellable', got '{wh_info.get('stock_effect')}'")
        
        # Verify location is ZNA-FG
        if "ZNA-FG" not in wh_info.get("location", ""):
            return self.log(False, "Location (Baik)", f"Expected ZNA-FG, got '{wh_info.get('location')}'")
        
        return self.log(True, "POST /api/marketing/returns (condition='Baik')", 
                       f"wh_return={wh_info.get('wh_return_code')}, restocked=True, "
                       f"stock_effect=sellable, location={wh_info.get('location')}")

    def test_create_return_rusak(self):
        """Test POST /api/marketing/returns with condition='Rusak'"""
        print("\n=== Test Create Return (Condition: Rusak) ===")
        
        if not self.test_data.get("catalog_item_id"):
            return self.log(False, "Create return (Rusak)", "No catalog item available")
        
        # Get a marketing account
        acc_data, err = self.api_call("GET", "/api/marketing/accounts")
        if err or not acc_data:
            return self.log(False, "Get marketing account", err or "No accounts")
        
        accounts = acc_data if isinstance(acc_data, list) else acc_data.get("accounts", [])
        if not accounts:
            return self.log(False, "Get marketing account", "No active accounts")
        
        account = accounts[0]
        
        # Create return with condition Rusak
        return_data = {
            "account_id": account.get("id"),
            "date": datetime.now().date().isoformat(),
            "order_id": f"TEST-{uuid.uuid4().hex[:8]}",
            "catalog_item_id": self.test_data["catalog_item_id"],
            "price": 100000,
            "qty": 3,
            "item_condition": "Rusak",
            "reason": "produk_cacat",
            "reason_detail": "Test return - condition Rusak",
            "courier": "jnt",
            "refund_type": "full_refund"
        }
        
        data, err = self.api_call("POST", "/api/marketing/returns", return_data, expected_status=200)
        if err:
            return self.log(False, "POST /api/marketing/returns (Rusak)", err)
        
        ret = data.get("data", {})
        wh_info = data.get("warehouse", {})
        
        self.test_data["marketing_return_ids"].append(ret.get("id"))
        
        # Verify warehouse return was created
        if not wh_info.get("wh_return_code"):
            return self.log(False, "Warehouse return creation (Rusak)", "No wh_return_code in response")
        
        # Verify restocked
        if not wh_info.get("restocked"):
            return self.log(False, "Auto restock (Rusak)", "restocked=False")
        
        # Verify stock effect is quarantine
        if wh_info.get("stock_effect") != "quarantine":
            return self.log(False, "Stock effect (Rusak)", f"Expected 'quarantine', got '{wh_info.get('stock_effect')}'")
        
        # Verify location is ZNA-KARANTINA
        if "KARANTINA" not in wh_info.get("location", "").upper():
            return self.log(False, "Location (Rusak)", f"Expected KARANTINA, got '{wh_info.get('location')}'")
        
        return self.log(True, "POST /api/marketing/returns (condition='Rusak')", 
                       f"wh_return={wh_info.get('wh_return_code')}, restocked=True, "
                       f"stock_effect=quarantine, location={wh_info.get('location')}")

    def test_filters(self):
        """Test GET /api/wh/returns with various filters"""
        print("\n=== Test Warehouse Returns Filters ===")
        
        # Test source=marketing filter
        data, err = self.api_call("GET", "/api/wh/returns?source=marketing")
        if err:
            return self.log(False, "GET /api/wh/returns?source=marketing", err)
        
        returns = data if isinstance(data, list) else []
        if not returns:
            self.log(False, "Filter source=marketing", "No returns from marketing found")
        else:
            self.log(True, "GET /api/wh/returns?source=marketing", f"Found {len(returns)} returns")
        
        # Test restocked=0 filter
        data, err = self.api_call("GET", "/api/wh/returns?restocked=0")
        if err:
            return self.log(False, "GET /api/wh/returns?restocked=0", err)
        
        returns = data if isinstance(data, list) else []
        self.log(True, "GET /api/wh/returns?restocked=0", f"Found {len(returns)} not restocked")
        
        # Test link_status=needs_link filter
        data, err = self.api_call("GET", "/api/wh/returns?link_status=needs_link")
        if err:
            return self.log(False, "GET /api/wh/returns?link_status=needs_link", err)
        
        returns = data if isinstance(data, list) else []
        self.log(True, "GET /api/wh/returns?link_status=needs_link", f"Found {len(returns)} needing link")
        
        return True

    def cleanup(self):
        """Clean up test data"""
        print("\n=== Cleanup Test Data ===")
        
        # Delete test marketing returns
        for ret_id in self.test_data["marketing_return_ids"]:
            self.api_call("DELETE", f"/api/marketing/returns/{ret_id}")
        
        if self.test_data["marketing_return_ids"]:
            self.log(True, "Cleanup", f"Deleted {len(self.test_data['marketing_return_ids'])} test returns")

    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("BACKEND TEST: Returns Bridge (W4 Session #29)")
        print("="*70)
        
        if not self.test_login():
            print("\n❌ Cannot proceed without authentication")
            return 1
        
        # Run tests
        self.test_marketing_gap()
        self.test_sync_dry_run()
        self.test_sync_apply_idempotent()
        
        if self.setup_test_material():
            self.test_create_return_baik()
            self.test_create_return_rusak()
        
        self.test_filters()
        
        # Cleanup
        self.cleanup()
        
        # Print summary
        print("\n" + "="*70)
        print(f"RESULTS: {self.tests_passed}/{self.tests_run} tests passed")
        print("="*70)
        
        if self.tests_passed == self.tests_run:
            print("\n✅ ALL TESTS PASSED")
            return 0
        else:
            print(f"\n❌ {self.tests_run - self.tests_passed} TESTS FAILED")
            return 1

def main():
    tester = ReturnsBridgeTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
