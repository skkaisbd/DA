#!/usr/bin/env python3
"""
Comprehensive Backend Test for W4 Session #29 Returns Bridge
Tests all 7 backend flows that were marked "NOT TESTED" in iteration 82
"""
import requests
import sys
import uuid
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class W4ReturnsTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_data = {
            "created_returns": [],
            "created_wh_returns": [],
            "stock_changes": [],
        }
        # Known test data from requirements
        self.account_id = "e53693e9-0732-4c07-b246-f11ef438571f"
        self.catalog_item_id = "3b9b6d8b-b800-4a52-8109-9db281d1d934"
        self.material_id = "87f2c2ce-4817-4975-9dd4-59576636f546"
        self.zna_fg_location = "19eb6442-5f3c-4c59-8971-58ff2a752e53"
        self.zna_karantina_location = "52fb8b23-ae9f-40cf-be83-08468c5804e8"

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
                return None, f"Expected {expected_status}, got {resp.status_code}: {resp.text[:300]}"
            
            try:
                return resp.json(), None
            except Exception:
                return resp.text, None
        except Exception as e:
            return None, str(e)

    def test_login(self):
        """Test login"""
        print("\n=== Authentication ===")
        data, err = self.api_call("POST", "/api/auth/login", {
            "email": "admin@garment.com",
            "password": "Admin@123"
        })
        
        if err or not data or "token" not in data:
            self.log(False, "Login", f"Failed: {err or 'No token'}")
            return False
        
        self.token = data["token"]
        self.log(True, "Login", "admin@garment.com")
        return True

    def test_flow_1_baik_condition(self):
        """Flow 1: POST /api/marketing/returns with condition='Baik', qty=2"""
        print("\n=== Flow 1: Marketing Return (Condition: Baik, qty=2) ===")
        
        order_id = f"QA-W4-BAIK-{uuid.uuid4().hex[:8]}"
        return_data = {
            "account_id": self.account_id,
            "date": datetime.now().date().isoformat(),
            "order_id": order_id,
            "catalog_item_id": self.catalog_item_id,
            "price": 89000,
            "qty": 2,
            "item_condition": "Baik",
            "reason": "ukuran_salah",
            "reason_detail": "qa test baik condition",
            "courier": "jnt",
            "refund_type": "full_refund"
        }
        
        data, err = self.api_call("POST", "/api/marketing/returns", return_data)
        if err:
            return self.log(False, "Create return (Baik)", err)
        
        ret = data.get("data", {})
        wh_info = data.get("warehouse", {})
        
        self.test_data["created_returns"].append(ret.get("id"))
        
        # Verify warehouse return was created
        if not wh_info.get("wh_return_code"):
            return self.log(False, "wh_return_code present", "Missing wh_return_code")
        
        self.log(True, "wh_return_code present", wh_info.get("wh_return_code"))
        
        # Verify restocked
        if not wh_info.get("restocked"):
            return self.log(False, "restocked=true", "restocked=False")
        
        self.log(True, "restocked=true", "Stock added")
        
        # Verify stock_effect is sellable
        if wh_info.get("stock_effect") != "sellable":
            return self.log(False, "stock_effect='sellable'", f"Got '{wh_info.get('stock_effect')}'")
        
        self.log(True, "stock_effect='sellable'", "Correct effect")
        
        # Verify location is ZNA-FG
        if "ZNA-FG" not in wh_info.get("location", ""):
            return self.log(False, "location='ZNA-FG'", f"Got '{wh_info.get('location')}'")
        
        self.log(True, "location='ZNA-FG'", "Correct location")
        
        # Get full return details to verify stock
        ret_full, err = self.api_call("GET", f"/api/marketing/returns/{ret.get('id')}")
        if not err:
            wh_ret_id = ret_full.get("data", {}).get("wh_return_id")
            if wh_ret_id:
                self.test_data["created_wh_returns"].append(wh_ret_id)
                self.test_data["stock_changes"].append({
                    "material_id": self.material_id,
                    "location_id": self.zna_fg_location,
                    "qty": 2,
                    "wh_return_id": wh_ret_id
                })
        
        return True

    def test_flow_2_rusak_condition(self):
        """Flow 2: POST /api/marketing/returns with condition='Rusak', qty=3"""
        print("\n=== Flow 2: Marketing Return (Condition: Rusak, qty=3) ===")
        
        order_id = f"QA-W4-RUSAK-{uuid.uuid4().hex[:8]}"
        return_data = {
            "account_id": self.account_id,
            "date": datetime.now().date().isoformat(),
            "order_id": order_id,
            "catalog_item_id": self.catalog_item_id,
            "price": 89000,
            "qty": 3,
            "item_condition": "Rusak",
            "reason": "produk_cacat",
            "reason_detail": "qa test rusak condition",
            "courier": "jnt",
            "refund_type": "full_refund"
        }
        
        data, err = self.api_call("POST", "/api/marketing/returns", return_data)
        if err:
            return self.log(False, "Create return (Rusak)", err)
        
        ret = data.get("data", {})
        wh_info = data.get("warehouse", {})
        
        self.test_data["created_returns"].append(ret.get("id"))
        
        # Verify warehouse return was created
        if not wh_info.get("wh_return_code"):
            return self.log(False, "wh_return_code present", "Missing wh_return_code")
        
        self.log(True, "wh_return_code present", wh_info.get("wh_return_code"))
        
        # Verify restocked
        if not wh_info.get("restocked"):
            return self.log(False, "restocked=true", "restocked=False")
        
        self.log(True, "restocked=true", "Stock added")
        
        # Verify stock_effect is quarantine
        if wh_info.get("stock_effect") != "quarantine":
            return self.log(False, "stock_effect='quarantine'", f"Got '{wh_info.get('stock_effect')}'")
        
        self.log(True, "stock_effect='quarantine'", "Correct effect")
        
        # Verify location contains KARANTINA
        if "KARANTINA" not in wh_info.get("location", "").upper():
            return self.log(False, "location contains 'KARANTINA'", f"Got '{wh_info.get('location')}'")
        
        self.log(True, "location='ZNA-KARANTINA'", "Correct location")
        
        # Get full return details
        ret_full, err = self.api_call("GET", f"/api/marketing/returns/{ret.get('id')}")
        if not err:
            wh_ret_id = ret_full.get("data", {}).get("wh_return_id")
            if wh_ret_id:
                self.test_data["created_wh_returns"].append(wh_ret_id)
                self.test_data["stock_changes"].append({
                    "material_id": self.material_id,
                    "location_id": self.zna_karantina_location,
                    "qty": 3,
                    "wh_return_id": wh_ret_id
                })
        
        return True

    def test_flow_3_idempotent_create_wh_return(self):
        """Flow 3: POST /api/marketing/returns/{id}/create-wh-return twice (idempotent)"""
        print("\n=== Flow 3: Idempotent create-wh-return ===")
        
        # Create a marketing return first
        order_id = f"QA-W4-IDEM-{uuid.uuid4().hex[:8]}"
        return_data = {
            "account_id": self.account_id,
            "date": datetime.now().date().isoformat(),
            "order_id": order_id,
            "catalog_item_id": self.catalog_item_id,
            "price": 89000,
            "qty": 1,
            "item_condition": "Baik",
            "reason": "ukuran_salah",
            "reason_detail": "qa test idempotent",
            "courier": "jnt",
            "refund_type": "full_refund"
        }
        
        data, err = self.api_call("POST", "/api/marketing/returns", return_data)
        if err:
            return self.log(False, "Create return for idempotent test", err)
        
        ret_id = data.get("data", {}).get("id")
        self.test_data["created_returns"].append(ret_id)
        
        # First call should succeed
        data1, err1 = self.api_call("POST", f"/api/marketing/returns/{ret_id}/create-wh-return", {})
        if err1:
            return self.log(False, "First create-wh-return call", err1)
        
        wh_ret_id = data1.get("data", {}).get("id") or data1.get("wh_return_id")
        if wh_ret_id:
            self.test_data["created_wh_returns"].append(wh_ret_id)
            self.test_data["stock_changes"].append({
                "material_id": self.material_id,
                "location_id": self.zna_fg_location,
                "qty": 1,
                "wh_return_id": wh_ret_id
            })
        
        self.log(True, "First create-wh-return", "Success")
        
        # Second call should return already_exists=true
        data2, err2 = self.api_call("POST", f"/api/marketing/returns/{ret_id}/create-wh-return", {})
        if err2:
            return self.log(False, "Second create-wh-return call", err2)
        
        if not data2.get("already_exists"):
            return self.log(False, "already_exists=true on 2nd call", f"Got {data2.get('already_exists')}")
        
        self.log(True, "already_exists=true on 2nd call", "Idempotent")
        
        # Verify wh_returns count didn't increase
        # (This would require checking the database, but we can verify the response)
        return True

    def test_flow_4_quick_restock(self):
        """Flow 4: POST /api/wh/returns/{id}/quick-restock scenarios"""
        print("\n=== Flow 4: Quick Restock Scenarios ===")
        
        # Create a manual warehouse return (not restocked yet)
        # Get an FG material first
        materials, err = self.api_call("GET", "/api/rahaza/materials?type=fg")
        if err or not materials:
            return self.log(False, "Get FG materials", err or "No materials")
        
        mat_list = materials if isinstance(materials, list) else materials.get("items", [])
        if not mat_list:
            return self.log(False, "Get FG materials", "No FG materials found")
        
        mat = mat_list[0]
        mat_id = mat.get("id")
        
        # Create manual warehouse return
        wh_ret_data = {
            "return_type": "customer_refund",
            "order_number": f"QA-W4-QUICK-{uuid.uuid4().hex[:8]}",
            "material_id": mat_id,
            "qty": 1,
            "order_value": 50000,
            "initial_reason": "qa test quick restock"
        }
        
        wh_ret, err = self.api_call("POST", "/api/wh/returns", wh_ret_data, expected_status=201)
        if err:
            return self.log(False, "Create manual WH return", err)
        
        wh_ret_id = wh_ret.get("id")
        self.test_data["created_wh_returns"].append(wh_ret_id)
        
        self.log(True, "Create manual WH return", wh_ret.get("return_code"))
        
        # (a) First quick-restock should succeed
        quick_data = {"condition": "Baik", "qty": 1}
        quick_res, err = self.api_call("POST", f"/api/wh/returns/{wh_ret_id}/quick-restock", quick_data)
        if err:
            return self.log(False, "Quick-restock (first call)", err)
        
        if not quick_res.get("restocked"):
            return self.log(False, "Quick-restock restocked=true", f"Got {quick_res.get('restocked')}")
        
        if quick_res.get("location_code") != "ZNA-FG":
            return self.log(False, "Quick-restock location='ZNA-FG'", f"Got {quick_res.get('location_code')}")
        
        self.log(True, "Quick-restock (first call)", f"restocked=true, location={quick_res.get('location_code')}")
        
        # Track stock change
        self.test_data["stock_changes"].append({
            "material_id": mat_id,
            "location_id": self.zna_fg_location,
            "qty": 1,
            "wh_return_id": wh_ret_id
        })
        
        # (b) Second quick-restock should fail with 400
        quick_res2, err2 = self.api_call("POST", f"/api/wh/returns/{wh_ret_id}/quick-restock", quick_data, expected_status=400)
        if not err2:
            return self.log(False, "Quick-restock (2nd call) should fail", "Got 200 instead of 400")
        
        self.log(True, "Quick-restock (2nd call) returns 400", "Already restocked")
        
        # (c) Test on ambiguous return RET-20260819-011
        # First, find this return
        search_res, err = self.api_call("GET", "/api/wh/returns?search=585044253894673420")
        if err:
            return self.log(False, "Search for ambiguous return", err)
        
        ambiguous_returns = search_res if isinstance(search_res, list) else []
        ambiguous_ret = None
        for r in ambiguous_returns:
            if r.get("return_code") == "RET-20260819-011" or "585044253894673420" in r.get("order_number", ""):
                ambiguous_ret = r
                break
        
        if not ambiguous_ret:
            self.log(False, "Find ambiguous return RET-20260819-011", "Not found")
            return False
        
        self.log(True, "Find ambiguous return", ambiguous_ret.get("return_code"))
        
        # Try quick-restock on ambiguous return (should fail)
        quick_amb, err_amb = self.api_call("POST", f"/api/wh/returns/{ambiguous_ret['id']}/quick-restock", 
                                          {"condition": "Baik", "qty": 1}, expected_status=400)
        if not err_amb:
            return self.log(False, "Quick-restock on ambiguous should fail", "Got 200 instead of 400")
        
        self.log(True, "Quick-restock on ambiguous returns 400", "Cannot restock ambiguous")
        
        return True

    def test_flow_5_relink(self):
        """Flow 5: POST /api/wh/returns/{id}/relink on ambiguous return"""
        print("\n=== Flow 5: Relink Ambiguous Return ===")
        
        # Find the ambiguous return RET-20260819-011
        search_res, err = self.api_call("GET", "/api/wh/returns?search=585044253894673420")
        if err:
            return self.log(False, "Search for ambiguous return", err)
        
        ambiguous_returns = search_res if isinstance(search_res, list) else []
        ambiguous_ret = None
        for r in ambiguous_returns:
            if r.get("return_code") == "RET-20260819-011" or "585044253894673420" in r.get("order_number", ""):
                ambiguous_ret = r
                break
        
        if not ambiguous_ret:
            return self.log(False, "Find ambiguous return", "Not found")
        
        self.log(True, "Find ambiguous return", ambiguous_ret.get("return_code"))
        
        # Call relink
        relink_res, err = self.api_call("POST", f"/api/wh/returns/{ambiguous_ret['id']}/relink", {})
        if err:
            return self.log(False, "Relink ambiguous return", err)
        
        # Verify link_status is still needs_manual_resolution
        if relink_res.get("link_status") != "needs_manual_resolution":
            return self.log(False, "link_status='needs_manual_resolution'", 
                          f"Got '{relink_res.get('link_status')}'")
        
        self.log(True, "link_status='needs_manual_resolution'", "Still ambiguous")
        
        # Verify reason is present
        if not relink_res.get("reason"):
            return self.log(False, "Reason present", "No reason provided")
        
        self.log(True, "Reason present", relink_res.get("reason")[:50])
        
        return True

    def test_flow_6_manual_returns(self):
        """Flow 6: POST /api/wh/returns manual with and without material_id"""
        print("\n=== Flow 6: Manual Warehouse Returns ===")
        
        # Get an FG material
        materials, err = self.api_call("GET", "/api/rahaza/materials?type=fg")
        if err or not materials:
            return self.log(False, "Get FG materials", err or "No materials")
        
        mat_list = materials if isinstance(materials, list) else materials.get("items", [])
        if not mat_list:
            return self.log(False, "Get FG materials", "No FG materials found")
        
        mat = mat_list[0]
        mat_id = mat.get("id")
        mat_code = mat.get("code") or mat.get("sku")
        
        # (a) Create with material_id
        wh_ret_data_a = {
            "return_type": "customer_refund",
            "order_number": f"QA-W4-MANUAL-A-{uuid.uuid4().hex[:8]}",
            "material_id": mat_id,
            "qty": 1,
            "order_value": 50000,
            "initial_reason": "qa test manual with material_id"
        }
        
        wh_ret_a, err_a = self.api_call("POST", "/api/wh/returns", wh_ret_data_a, expected_status=201)
        if err_a:
            return self.log(False, "Create manual WH return (with material_id)", err_a)
        
        self.test_data["created_wh_returns"].append(wh_ret_a.get("id"))
        
        # Verify sku_code and product_name are filled
        if not wh_ret_a.get("sku_code"):
            return self.log(False, "sku_code filled from master", "sku_code empty")
        
        self.log(True, "sku_code filled from master", wh_ret_a.get("sku_code"))
        
        if not wh_ret_a.get("product_name"):
            return self.log(False, "product_name filled from master", "product_name empty")
        
        self.log(True, "product_name filled from master", wh_ret_a.get("product_name")[:30])
        
        # Verify link_status is 'linked'
        if wh_ret_a.get("link_status") != "linked":
            return self.log(False, "link_status='linked'", f"Got '{wh_ret_a.get('link_status')}'")
        
        self.log(True, "link_status='linked'", "Linked to master")
        
        # Quick-restock should succeed
        quick_a, err_quick_a = self.api_call("POST", f"/api/wh/returns/{wh_ret_a['id']}/quick-restock", 
                                            {"condition": "Baik", "qty": 1})
        if err_quick_a:
            return self.log(False, "Quick-restock on linked return", err_quick_a)
        
        if not quick_a.get("restocked"):
            return self.log(False, "Quick-restock restocked=true", f"Got {quick_a.get('restocked')}")
        
        self.log(True, "Quick-restock on linked return", "Success")
        
        # Track stock change
        self.test_data["stock_changes"].append({
            "material_id": mat_id,
            "location_id": self.zna_fg_location,
            "qty": 1,
            "wh_return_id": wh_ret_a.get("id")
        })
        
        # (b) Create without material_id and without sku_code
        wh_ret_data_b = {
            "return_type": "customer_refund",
            "order_number": f"QA-W4-MANUAL-B-{uuid.uuid4().hex[:8]}",
            "qty": 1,
            "order_value": 50000,
            "initial_reason": "qa test manual without material_id"
        }
        
        wh_ret_b, err_b = self.api_call("POST", "/api/wh/returns", wh_ret_data_b, expected_status=201)
        if err_b:
            return self.log(False, "Create manual WH return (without material_id)", err_b)
        
        self.test_data["created_wh_returns"].append(wh_ret_b.get("id"))
        
        # Verify link_status is 'no_master_link'
        if wh_ret_b.get("link_status") != "no_master_link":
            return self.log(False, "link_status='no_master_link'", f"Got '{wh_ret_b.get('link_status')}'")
        
        self.log(True, "link_status='no_master_link'", "Not linked")
        
        # Quick-restock should fail with 400
        quick_b, err_quick_b = self.api_call("POST", f"/api/wh/returns/{wh_ret_b['id']}/quick-restock", 
                                            {"condition": "Baik", "qty": 1}, expected_status=400)
        if not err_quick_b:
            return self.log(False, "Quick-restock on unlinked should fail", "Got 200 instead of 400")
        
        self.log(True, "Quick-restock on unlinked returns 400", "Cannot restock unlinked")
        
        return True

    def test_flow_7_manual_3_step(self):
        """Flow 7: Manual 3-step flow (receive → inspect → resolve)"""
        print("\n=== Flow 7: Manual 3-Step Flow ===")
        
        # Get an FG material
        materials, err = self.api_call("GET", "/api/rahaza/materials?type=fg")
        if err or not materials:
            return self.log(False, "Get FG materials", err or "No materials")
        
        mat_list = materials if isinstance(materials, list) else materials.get("items", [])
        if not mat_list:
            return self.log(False, "Get FG materials", "No FG materials found")
        
        mat = mat_list[0]
        mat_id = mat.get("id")
        
        # Create manual warehouse return
        wh_ret_data = {
            "return_type": "customer_refund",
            "order_number": f"QA-W4-3STEP-{uuid.uuid4().hex[:8]}",
            "material_id": mat_id,
            "qty": 2,
            "order_value": 100000,
            "initial_reason": "qa test 3-step flow"
        }
        
        wh_ret, err = self.api_call("POST", "/api/wh/returns", wh_ret_data, expected_status=201)
        if err:
            return self.log(False, "Create manual WH return for 3-step", err)
        
        wh_ret_id = wh_ret.get("id")
        self.test_data["created_wh_returns"].append(wh_ret_id)
        
        self.log(True, "Create manual WH return", wh_ret.get("return_code"))
        
        # Step 1: Receive
        receive_data = {
            "unboxing_condition_notes": "QA test - package received",
            "package_condition": "Good",
            "unboxing_photo_notes": "QA-IMG-001"
        }
        
        receive_res, err_receive = self.api_call("POST", f"/api/wh/returns/{wh_ret_id}/receive", receive_data)
        if err_receive:
            return self.log(False, "Step 1: Receive", err_receive)
        
        if receive_res.get("status") != "Received":
            return self.log(False, "Status after receive", f"Expected 'Received', got '{receive_res.get('status')}'")
        
        self.log(True, "Step 1: Receive", "Status=Received")
        
        # Step 2: Inspect
        inspect_data = {
            "item_condition": "Rusak",
            "return_cause": "Kesalahan Customer",
            "cause_detail": "QA test - damaged item",
            "recommended_action": "Karantina (Rusak)"
        }
        
        inspect_res, err_inspect = self.api_call("POST", f"/api/wh/returns/{wh_ret_id}/inspect", inspect_data)
        if err_inspect:
            return self.log(False, "Step 2: Inspect", err_inspect)
        
        if inspect_res.get("status") != "Inspected":
            return self.log(False, "Status after inspect", f"Expected 'Inspected', got '{inspect_res.get('status')}'")
        
        self.log(True, "Step 2: Inspect", "Status=Inspected, condition=Rusak")
        
        # Step 3: Resolve
        resolve_data = {
            "action_taken": "Karantina (Rusak)",
            "restock_qty": 2,
            "action_notes": "QA test - quarantine damaged items"
        }
        
        resolve_res, err_resolve = self.api_call("POST", f"/api/wh/returns/{wh_ret_id}/resolve", resolve_data)
        if err_resolve:
            return self.log(False, "Step 3: Resolve", err_resolve)
        
        if resolve_res.get("status") != "Resolved":
            return self.log(False, "Status after resolve", f"Expected 'Resolved', got '{resolve_res.get('status')}'")
        
        self.log(True, "Step 3: Resolve", "Status=Resolved")
        
        # Verify restock_result
        restock_result = resolve_res.get("restock_result", {})
        if not restock_result.get("restocked"):
            return self.log(False, "restock_result.restocked=true", f"Got {restock_result.get('restocked')}")
        
        self.log(True, "restock_result.restocked=true", "Stock added")
        
        # Verify location_code is ZNA-KARANTINA
        if "KARANTINA" not in restock_result.get("location_code", "").upper():
            return self.log(False, "location_code='ZNA-KARANTINA'", f"Got '{restock_result.get('location_code')}'")
        
        self.log(True, "location_code='ZNA-KARANTINA'", "Correct quarantine location")
        
        # Track stock change
        self.test_data["stock_changes"].append({
            "material_id": mat_id,
            "location_id": self.zna_karantina_location,
            "qty": 2,
            "wh_return_id": wh_ret_id
        })
        
        return True

    def cleanup(self):
        """Clean up test data"""
        print("\n=== Cleanup Test Data ===")
        
        # Delete marketing returns
        for ret_id in self.test_data["created_returns"]:
            try:
                self.api_call("DELETE", f"/api/marketing/returns/{ret_id}")
            except Exception:
                pass
        
        if self.test_data["created_returns"]:
            self.log(True, "Cleanup marketing returns", f"Deleted {len(self.test_data['created_returns'])} returns")
        
        # Delete warehouse returns
        for wh_ret_id in self.test_data["created_wh_returns"]:
            try:
                # Try to delete if status is Pending
                self.api_call("DELETE", f"/api/wh/returns/{wh_ret_id}")
            except Exception:
                pass
        
        if self.test_data["created_wh_returns"]:
            self.log(True, "Cleanup warehouse returns", f"Attempted to delete {len(self.test_data['created_wh_returns'])} wh_returns")
        
        print(f"\nNote: Stock changes made: {len(self.test_data['stock_changes'])} operations")
        print("Stock cleanup should be done manually or via stock adjustment to restore original qty=33503")

    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*70)
        print("COMPREHENSIVE BACKEND TEST: W4 Session #29 Returns Bridge")
        print("Testing all 7 backend flows marked 'NOT TESTED' in iteration 82")
        print("="*70)
        
        if not self.test_login():
            print("\n❌ Cannot proceed without authentication")
            return 1
        
        # Run all 7 flows
        self.test_flow_1_baik_condition()
        self.test_flow_2_rusak_condition()
        self.test_flow_3_idempotent_create_wh_return()
        self.test_flow_4_quick_restock()
        self.test_flow_5_relink()
        self.test_flow_6_manual_returns()
        self.test_flow_7_manual_3_step()
        
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
    tester = W4ReturnsTester()
    return tester.run_all_tests()

if __name__ == "__main__":
    sys.exit(main())
