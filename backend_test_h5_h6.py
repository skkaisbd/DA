#!/usr/bin/env python3
"""
Backend API Test for FASE H-5 & H-6 (Fabric Roll Tracking)
Tests all endpoints mentioned in the review request for session 2026-08-16 (#15)
"""
import requests
import sys
import os
from datetime import datetime

# Use public URL for testing
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://da37-cmt-bridge.preview.emergentagent.com")
API_BASE = f"{BASE_URL}/api"

# Test credentials
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class TestRunner:
    def __init__(self):
        self.token = None
        self.passed = 0
        self.failed = 0
        self.test_data = {}
        
    def login(self):
        """Login and get token"""
        print(f"\n{Colors.BLUE}=== Logging in ==={Colors.END}")
        r = requests.post(f"{API_BASE}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        if r.status_code != 200:
            print(f"{Colors.RED}✗ Login failed: {r.status_code} {r.text[:200]}{Colors.END}")
            sys.exit(1)
        self.token = r.json()["token"]
        print(f"{Colors.GREEN}✓ Login successful{Colors.END}")
        
    def headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }
    
    def test(self, name, condition, detail=""):
        """Record test result"""
        if condition:
            self.passed += 1
            print(f"{Colors.GREEN}✓{Colors.END} {name}" + (f" — {detail}" if detail else ""))
        else:
            self.failed += 1
            print(f"{Colors.RED}✗ {name}{Colors.END}" + (f" — {detail}" if detail else ""))
        return condition
    
    def section(self, title):
        """Print section header"""
        print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{title}{Colors.END}")
        print(f"{Colors.BOLD}{Colors.BLUE}{'='*70}{Colors.END}")
    
    def ensure_material(self, code, name, unit, mtype):
        """Ensure material exists (idempotent)"""
        r = requests.get(f"{API_BASE}/rahaza/materials?limit=5000&search={code}", headers=self.headers())
        if r.status_code == 200:
            items = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            for m in items:
                if m.get("code", "").upper() == code.upper():
                    return m
        # Create new
        r = requests.post(f"{API_BASE}/rahaza/materials", headers=self.headers(), json={
            "code": code, "name": name, "unit": unit, "type": mtype,
            "color": "Navy", "unit_cost": 50000, "notes": "Test H-5/H-6"
        })
        if r.status_code in (200, 201):
            return r.json().get("material") or r.json()
        raise Exception(f"Failed to create material: {r.status_code} {r.text[:200]}")
    
    def get_location(self):
        """Get first active location"""
        r = requests.get(f"{API_BASE}/rahaza/storage-locations", headers=self.headers())
        if r.status_code == 200:
            locs = r.json() if isinstance(r.json(), list) else r.json().get("items", [])
            if locs:
                return locs[0]
        raise Exception("No storage location found")
    
    def test_backend_a(self):
        """BACKEND A: GR with rolls → rolls_created, stock increases, wh_fabric_rolls created"""
        self.section("BACKEND A: GR with rolls creates fabric rolls automatically")
        
        # Setup
        mat = self.ensure_material("TEST-H5-KAIN-A", "Test Fabric A (H5)", "kg", "fabric")
        loc = self.get_location()
        
        # Get initial stock
        r = requests.get(f"{API_BASE}/rahaza/materials/{mat['id']}/stock", headers=self.headers())
        initial_stock = r.json().get("total_qty", 0) if r.status_code == 200 else 0
        
        # Create GR with rolls
        gr_data = {
            "source_type": "supplier",
            "supplier_name": "Test Supplier H5",
            "location_id": loc["id"],
            "location_name": loc.get("name", ""),
            "notes": "Test H-5 Backend A",
            "items": [{
                "product_name": mat["name"],
                "sku": mat["code"],
                "material_id": mat["id"],
                "expected_qty": 150,
                "received_qty": 150,
                "rejected_qty": 0,
                "unit": "kg",
                "unit_price": 50000,
                "inspection_status": "passed",
                "rolls": [
                    {"qty": 50, "color_lot": "LOT-A", "notes": "Roll 1"},
                    {"qty": 50, "color_lot": "LOT-A", "notes": "Roll 2"},
                    {"qty": 50, "color_lot": "LOT-A", "notes": "Roll 3"}
                ]
            }]
        }
        
        r = requests.post(f"{API_BASE}/wms/legacy/receiving", headers=self.headers(), json=gr_data)
        self.test("Create GR draft", r.status_code in (200, 201), f"HTTP {r.status_code}")
        if r.status_code not in (200, 201):
            print(f"  Error: {r.text[:300]}")
            return
        
        gr = r.json()
        self.test_data["gr_a"] = gr
        self.test("GR has 3 rolls in draft", len(gr.get("items", [{}])[0].get("rolls", [])) == 3)
        
        # Confirm GR
        r = requests.put(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", 
                        headers=self.headers(), json={"status": "received"})
        self.test("Confirm GR (status=received)", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code != 200:
            print(f"  Error: {r.text[:300]}")
            return
        
        result = r.json()
        rolls_created = result.get("rolls_created", [])
        self.test("Response has rolls_created field", "rolls_created" in result)
        self.test("3 rolls created", len(rolls_created) == 3, f"Got {len(rolls_created)}")
        self.test("All roll numbers match pattern RL-YYYYMM-####", 
                 all(len(r.split("-")) == 3 and r.startswith("RL-") for r in rolls_created),
                 f"Sample: {rolls_created[0] if rolls_created else 'none'}")
        
        # Check stock increased
        r = requests.get(f"{API_BASE}/rahaza/materials/{mat['id']}/stock", headers=self.headers())
        if r.status_code == 200:
            new_stock = r.json().get("total_qty", 0)
            self.test("Stock increased by 150 kg", abs(new_stock - initial_stock - 150) < 0.01,
                     f"{initial_stock} → {new_stock}")
        
        # Check wh_fabric_rolls created (via GET /api/wms/fabric-rolls)
        if rolls_created:
            r = requests.get(f"{API_BASE}/wms/fabric-rolls?material_id={mat['id']}", headers=self.headers())
            if r.status_code == 200:
                items = r.json().get("items", [])
                self.test("wh_fabric_rolls documents created", len(items) >= 3, f"Found {len(items)} rolls")
                if items:
                    roll = items[0]
                    self.test("Roll has correct fields", 
                             all(k in roll for k in ["roll_no", "uom", "remaining_kg", "status"]),
                             f"Sample: {roll.get('roll_no')}")
                    self.test("Roll status is in_stock", roll.get("status") == "in_stock")
                    self.test("Roll remaining_kg = 50", abs(roll.get("remaining_kg", 0) - 50) < 0.01)
    
    def test_backend_b(self):
        """BACKEND B: Roll qty mismatch → 400, no stock change, status stays draft"""
        self.section("BACKEND B: Roll qty mismatch validation")
        
        mat = self.ensure_material("TEST-H5-KAIN-B", "Test Fabric B (H5)", "kg", "fabric")
        loc = self.get_location()
        
        # Get initial stock
        r = requests.get(f"{API_BASE}/rahaza/materials/{mat['id']}/stock", headers=self.headers())
        initial_stock = r.json().get("total_qty", 0) if r.status_code == 200 else 0
        
        # Create GR with mismatched rolls (3x30 = 90, but received_qty = 100)
        gr_data = {
            "source_type": "supplier",
            "supplier_name": "Test Supplier H5",
            "location_id": loc["id"],
            "location_name": loc.get("name", ""),
            "items": [{
                "product_name": mat["name"],
                "sku": mat["code"],
                "material_id": mat["id"],
                "expected_qty": 100,
                "received_qty": 100,
                "rejected_qty": 0,
                "unit": "kg",
                "unit_price": 50000,
                "inspection_status": "passed",
                "rolls": [
                    {"qty": 30, "color_lot": "LOT-B"},
                    {"qty": 30, "color_lot": "LOT-B"},
                    {"qty": 30, "color_lot": "LOT-B"}
                ]
            }]
        }
        
        r = requests.post(f"{API_BASE}/wms/legacy/receiving", headers=self.headers(), json=gr_data)
        if r.status_code not in (200, 201):
            print(f"  Failed to create GR: {r.status_code}")
            return
        gr = r.json()
        
        # Try to confirm with mismatch
        r = requests.put(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", 
                        headers=self.headers(), json={"status": "received"})
        self.test("Confirm with mismatch returns 400", r.status_code == 400, f"HTTP {r.status_code}")
        msg = r.text.lower()
        self.test("Error message mentions mismatch/selisih", "selisih" in msg or "mismatch" in msg or "90" in msg,
                 f"Message: {r.text[:150]}")
        
        # Check stock didn't change
        r = requests.get(f"{API_BASE}/rahaza/materials/{mat['id']}/stock", headers=self.headers())
        if r.status_code == 200:
            new_stock = r.json().get("total_qty", 0)
            self.test("Stock unchanged", abs(new_stock - initial_stock) < 0.01, f"Still {new_stock}")
        
        # Check GR status still draft
        r = requests.get(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", headers=self.headers())
        if r.status_code == 200:
            status = r.json().get("status")
            self.test("GR status still draft", status == "draft", f"Status: {status}")
    
    def test_backend_c(self):
        """BACKEND C: Non-fabric material with rolls → 400"""
        self.section("BACKEND C: Non-fabric material (pcs) with rolls rejected")
        
        mat = self.ensure_material("TEST-H5-BTN-C", "Test Button C (H5)", "pcs", "accessory")
        loc = self.get_location()
        
        gr_data = {
            "source_type": "supplier",
            "supplier_name": "Test Supplier H5",
            "location_id": loc["id"],
            "location_name": loc.get("name", ""),
            "items": [{
                "product_name": mat["name"],
                "sku": mat["code"],
                "material_id": mat["id"],
                "expected_qty": 500,
                "received_qty": 500,
                "rejected_qty": 0,
                "unit": "pcs",
                "unit_price": 250,
                "inspection_status": "passed",
                "rolls": [
                    {"qty": 250},
                    {"qty": 250}
                ]
            }]
        }
        
        r = requests.post(f"{API_BASE}/wms/legacy/receiving", headers=self.headers(), json=gr_data)
        if r.status_code not in (200, 201):
            return
        gr = r.json()
        
        r = requests.put(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", 
                        headers=self.headers(), json={"status": "received"})
        self.test("Confirm pcs material with rolls returns 400", r.status_code == 400, f"HTTP {r.status_code}")
        msg = r.text.lower()
        self.test("Error mentions unit/gulungan", "pcs" in msg and "gulungan" in msg, f"Message: {r.text[:150]}")
    
    def test_backend_d(self):
        """BACKEND D: GR fabric WITHOUT rolls → 200 with rolls_pending"""
        self.section("BACKEND D: GR fabric WITHOUT rolls → rolls_pending")
        
        mat = self.ensure_material("TEST-H5-KAIN-D", "Test Fabric D (H5)", "kg", "fabric")
        loc = self.get_location()
        
        gr_data = {
            "source_type": "supplier",
            "supplier_name": "Test Supplier H5",
            "location_id": loc["id"],
            "location_name": loc.get("name", ""),
            "items": [{
                "product_name": mat["name"],
                "sku": mat["code"],
                "material_id": mat["id"],
                "expected_qty": 50,
                "received_qty": 50,
                "rejected_qty": 0,
                "unit": "kg",
                "unit_price": 50000,
                "inspection_status": "passed"
                # NO rolls array
            }]
        }
        
        r = requests.post(f"{API_BASE}/wms/legacy/receiving", headers=self.headers(), json=gr_data)
        if r.status_code not in (200, 201):
            return
        gr = r.json()
        self.test_data["gr_d"] = gr
        
        r = requests.put(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", 
                        headers=self.headers(), json={"status": "received"})
        self.test("Confirm without rolls returns 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            result = r.json()
            rolls_pending = result.get("rolls_pending", [])
            self.test("Response has rolls_pending", "rolls_pending" in result)
            self.test("rolls_pending contains the fabric item", len(rolls_pending) >= 1,
                     f"Found {len(rolls_pending)} pending items")
    
    def test_backend_e(self):
        """BACKEND E: GET /api/wms/fabric-rolls/number-policy"""
        self.section("BACKEND E: Roll number policy")
        
        r = requests.get(f"{API_BASE}/wms/fabric-rolls/number-policy", headers=self.headers())
        self.test("GET number-policy returns 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            policy = r.json()
            self.test("mode is 'auto'", policy.get("mode") == "auto", f"mode={policy.get('mode')}")
            fmt = policy.get("format", "")
            self.test("format contains RL-{YYYY}{MM}-{SEQ:4}", 
                     "RL-" in fmt and "YYYY" in fmt and "MM" in fmt,
                     f"format={fmt}")
            next_num = policy.get("next_number", "")
            self.test("next_number matches pattern RL-YYYYMM-####",
                     len(next_num.split("-")) == 3 and next_num.startswith("RL-"),
                     f"next_number={next_num}")
    
    def test_backend_f(self):
        """BACKEND F: POST /api/wms/fabric-rolls with/without roll_no"""
        self.section("BACKEND F: Manual roll creation (auto numbering)")
        
        mat = self.ensure_material("TEST-H5-KAIN-F", "Test Fabric F (H5)", "m", "fabric")
        
        # Without roll_no → should get auto number
        r = requests.post(f"{API_BASE}/wms/fabric-rolls", headers=self.headers(), json={
            "material_id": mat["id"],
            "material_code": mat["code"],
            "material_name": mat["name"],
            "uom": "meter",
            "length_m": 25,
            "weight_kg": 0,
            "notes": "Test auto numbering"
        })
        self.test("Create roll without roll_no returns 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            roll = r.json().get("roll", {})
            roll_no = roll.get("roll_no", "")
            self.test("Auto-generated roll_no matches pattern", 
                     roll_no.startswith("RL-") and len(roll_no.split("-")) == 3,
                     f"roll_no={roll_no}")
        
        # With roll_no → should get 400
        r = requests.post(f"{API_BASE}/wms/fabric-rolls", headers=self.headers(), json={
            "roll_no": "RL-MANUAL-001",
            "material_id": mat["id"],
            "material_code": mat["code"],
            "material_name": mat["name"],
            "uom": "meter",
            "length_m": 25,
            "weight_kg": 0
        })
        self.test("Create roll with manual roll_no returns 400", r.status_code == 400, f"HTTP {r.status_code}")
        if r.status_code == 400:
            msg = r.text.lower()
            self.test("Error mentions auto/otomatis", "otomatis" in msg or "auto" in msg,
                     f"Message: {r.text[:150]}")
    
    def test_backend_g(self):
        """BACKEND G: GET /api/wms/fabric-rolls/missing-from-receipts"""
        self.section("BACKEND G: List receipts missing rolls")
        
        r = requests.get(f"{API_BASE}/wms/fabric-rolls/missing-from-receipts?limit=100", headers=self.headers())
        self.test("GET missing-from-receipts returns 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            self.test("Response has items array", isinstance(items, list))
            # Should include the GR from test_backend_d
            if "gr_d" in self.test_data:
                gr_d = self.test_data["gr_d"]
                found = any(item.get("receipt_id") == gr_d["id"] for item in items)
                self.test("List includes GR without rolls from test D", found,
                         f"Found {len(items)} pending items")
    
    def test_backend_h(self):
        """BACKEND H: POST /api/wms/fabric-rolls/issue-from-receipt"""
        self.section("BACKEND H: Issue rolls retroactively")
        
        if "gr_d" not in self.test_data:
            print(f"{Colors.YELLOW}  Skipping (no GR from test D){Colors.END}")
            return
        
        gr_d = self.test_data["gr_d"]
        item_id = gr_d.get("items", [{}])[0].get("id")
        
        # Issue rolls
        r = requests.post(f"{API_BASE}/wms/fabric-rolls/issue-from-receipt", headers=self.headers(), json={
            "receipt_id": gr_d["id"],
            "item_id": item_id,
            "lines": [
                {"qty": 25, "color_lot": "LOT-D"},
                {"qty": 25, "color_lot": "LOT-D"}
            ]
        })
        self.test("Issue rolls from receipt returns 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            result = r.json()
            roll_numbers = result.get("roll_numbers", [])
            self.test("2 roll numbers returned", len(roll_numbers) == 2, f"Got {len(roll_numbers)}")
            self.test("Roll numbers match pattern", 
                     all(r.startswith("RL-") for r in roll_numbers),
                     f"Sample: {roll_numbers[0] if roll_numbers else 'none'}")
        
        # Try again → should get 409
        r = requests.post(f"{API_BASE}/wms/fabric-rolls/issue-from-receipt", headers=self.headers(), json={
            "receipt_id": gr_d["id"],
            "item_id": item_id,
            "lines": [{"qty": 25}, {"qty": 25}]
        })
        self.test("Second issue attempt returns 409 (idempotent)", r.status_code == 409, f"HTTP {r.status_code}")
        
        # Wrong qty → should get 400
        mat = self.ensure_material("TEST-H5-KAIN-H", "Test Fabric H (H5)", "kg", "fabric")
        loc = self.get_location()
        gr_data = {
            "source_type": "supplier",
            "supplier_name": "Test Supplier H5",
            "location_id": loc["id"],
            "location_name": loc.get("name", ""),
            "items": [{
                "product_name": mat["name"],
                "sku": mat["code"],
                "material_id": mat["id"],
                "expected_qty": 100,
                "received_qty": 100,
                "rejected_qty": 0,
                "unit": "kg",
                "unit_price": 50000,
                "inspection_status": "passed"
            }]
        }
        r = requests.post(f"{API_BASE}/wms/legacy/receiving", headers=self.headers(), json=gr_data)
        if r.status_code in (200, 201):
            gr = r.json()
            r = requests.put(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", 
                            headers=self.headers(), json={"status": "received"})
            if r.status_code == 200:
                item_id_h = gr.get("items", [{}])[0].get("id")
                r = requests.post(f"{API_BASE}/wms/fabric-rolls/issue-from-receipt", headers=self.headers(), json={
                    "receipt_id": gr["id"],
                    "item_id": item_id_h,
                    "lines": [{"qty": 40}, {"qty": 40}]  # 80 != 100
                })
                self.test("Issue with wrong qty returns 400", r.status_code == 400, f"HTTP {r.status_code}")
    
    def test_backend_i(self):
        """BACKEND I (H-6): POST /api/cutting/orders for fabric with/without rolls"""
        self.section("BACKEND I (H-6): Cutting orders require rolls")
        
        # Material WITH rolls (from test A)
        if "gr_a" in self.test_data:
            gr_a = self.test_data["gr_a"]
            mat_id = gr_a.get("items", [{}])[0].get("material_id")
            loc = self.get_location()
            
            r = requests.post(f"{API_BASE}/cutting/orders", headers=self.headers(), json={
                "input_material_id": mat_id,
                "planned_input_qty": 50,
                "planned_output_qty": 100,
                "style_name": "Test Style H6",
                "location_id": loc["id"]
            })
            self.test("Create cutting order for fabric WITH rolls returns 200", 
                     r.status_code in (200, 201), f"HTTP {r.status_code}")
            if r.status_code in (200, 201):
                order = r.json()
                self.test_data["cutting_order"] = order
                self.test("Order has roll_required=true", order.get("roll_required") is True,
                         f"roll_required={order.get('roll_required')}")
        
        # Material WITHOUT rolls
        mat_no_roll = self.ensure_material(f"TEST-H6-NOROLL-{datetime.now():%H%M%S}", 
                                           "Test Fabric No Roll (H6)", "kg", "fabric")
        loc = self.get_location()
        
        # Create GR without rolls
        gr_data = {
            "source_type": "supplier",
            "supplier_name": "Test Supplier H6",
            "location_id": loc["id"],
            "location_name": loc.get("name", ""),
            "items": [{
                "product_name": mat_no_roll["name"],
                "sku": mat_no_roll["code"],
                "material_id": mat_no_roll["id"],
                "expected_qty": 50,
                "received_qty": 50,
                "rejected_qty": 0,
                "unit": "kg",
                "unit_price": 50000,
                "inspection_status": "passed"
            }]
        }
        r = requests.post(f"{API_BASE}/wms/legacy/receiving", headers=self.headers(), json=gr_data)
        if r.status_code in (200, 201):
            gr = r.json()
            r = requests.put(f"{API_BASE}/wms/legacy/receiving/{gr['id']}", 
                            headers=self.headers(), json={"status": "received"})
            if r.status_code == 200:
                # Try to create cutting order
                r = requests.post(f"{API_BASE}/cutting/orders", headers=self.headers(), json={
                    "input_material_id": mat_no_roll["id"],
                    "planned_input_qty": 10,
                    "planned_output_qty": 20,
                    "style_name": "Test Style No Roll",
                    "location_id": loc["id"]
                })
                self.test("Create cutting order for fabric WITHOUT rolls returns 400",
                         r.status_code == 400, f"HTTP {r.status_code}")
                if r.status_code == 400:
                    msg = r.text.lower()
                    self.test("Error mentions way out (penerimaan/roll kain)",
                             "penerimaan" in msg or "roll kain" in msg or "rincian roll" in msg,
                             f"Message: {r.text[:200]}")
    
    def test_backend_j(self):
        """BACKEND J (H-6): POST /api/cutting/orders/{id}/progress with/without roll_ids"""
        self.section("BACKEND J (H-6): Cutting progress requires roll selection")
        
        if "cutting_order" not in self.test_data:
            print(f"{Colors.YELLOW}  Skipping (no cutting order from test I){Colors.END}")
            return
        
        order = self.test_data["cutting_order"]
        
        # Start order first
        r = requests.post(f"{API_BASE}/cutting/orders/{order['id']}/start", headers=self.headers())
        if r.status_code != 200:
            print(f"  Failed to start order: {r.status_code}")
            return
        
        # Get available rolls
        mat_id = order.get("input_material_id")
        r = requests.get(f"{API_BASE}/cutting/rolls?material_id={mat_id}", headers=self.headers())
        if r.status_code != 200:
            print(f"  Failed to get rolls: {r.status_code}")
            return
        
        rolls_data = r.json()
        rolls = rolls_data.get("items", [])
        
        # Try progress WITHOUT roll_ids
        r = requests.post(f"{API_BASE}/cutting/orders/{order['id']}/progress", headers=self.headers(), json={
            "input_consumed": 30,
            "output_qty": 60
        })
        self.test("Progress without roll_ids returns 400", r.status_code == 400, f"HTTP {r.status_code}")
        if r.status_code == 400:
            msg = r.text.lower()
            self.test("Error mentions rolls/gulungan", "gulungan" in msg or "roll" in msg,
                     f"Message: {r.text[:200]}")
        
        # Try progress WITH insufficient rolls
        if rolls:
            r = requests.post(f"{API_BASE}/cutting/orders/{order['id']}/progress", headers=self.headers(), json={
                "input_consumed": 100,  # More than one roll
                "output_qty": 200,
                "roll_ids": [rolls[0]["id"]]  # Only one roll
            })
            self.test("Progress with insufficient rolls returns 400", r.status_code == 400, f"HTTP {r.status_code}")
        
        # Try progress WITH correct rolls
        if rolls:
            r = requests.post(f"{API_BASE}/cutting/orders/{order['id']}/progress", headers=self.headers(), json={
                "input_consumed": 30,
                "output_qty": 60,
                "roll_ids": [rolls[0]["id"]]
            })
            self.test("Progress with roll_ids returns 200", r.status_code == 200, f"HTTP {r.status_code}")
            if r.status_code == 200:
                result = r.json()
                last_progress = result.get("last_progress", {})
                roll_consumption = last_progress.get("roll_consumption", [])
                self.test("Response has roll_consumption", len(roll_consumption) > 0,
                         f"Consumed {len(roll_consumption)} rolls")
                if roll_consumption:
                    self.test("Roll consumption has qty and remaining_after",
                             "qty" in roll_consumption[0] and "remaining_after" in roll_consumption[0])
    
    def test_backend_k(self):
        """BACKEND K: GET /api/cutting/rolls returns object (not array)"""
        self.section("BACKEND K: GET /api/cutting/rolls returns object")
        
        if "gr_a" not in self.test_data:
            print(f"{Colors.YELLOW}  Skipping (no material from test A){Colors.END}")
            return
        
        gr_a = self.test_data["gr_a"]
        mat_id = gr_a.get("items", [{}])[0].get("material_id")
        
        r = requests.get(f"{API_BASE}/cutting/rolls?material_id={mat_id}", headers=self.headers())
        self.test("GET /api/cutting/rolls returns 200", r.status_code == 200, f"HTTP {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            self.test("Response is object (not array)", isinstance(data, dict), f"Type: {type(data)}")
            self.test("Object has 'items' field", "items" in data)
            self.test("Object has 'total' field", "total" in data)
            self.test("Object has 'roll_required' field", "roll_required" in data)
            self.test("Object has 'total_remaining' field", "total_remaining" in data)
            self.test("Object has 'uom' field", "uom" in data)
            if "items" in data:
                self.test("items is array", isinstance(data["items"], list))
    
    def run_all(self):
        """Run all tests"""
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        print(f"{Colors.BOLD}Backend API Test for FASE H-5 & H-6{Colors.END}")
        print(f"{Colors.BOLD}Testing against: {BASE_URL}{Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}")
        
        self.login()
        
        # Run tests in order
        self.test_backend_a()
        self.test_backend_b()
        self.test_backend_c()
        self.test_backend_d()
        self.test_backend_e()
        self.test_backend_f()
        self.test_backend_g()
        self.test_backend_h()
        self.test_backend_i()
        self.test_backend_j()
        self.test_backend_k()
        
        # Summary
        print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
        total = self.passed + self.failed
        pct = (self.passed / total * 100) if total > 0 else 0
        color = Colors.GREEN if pct >= 90 else Colors.YELLOW if pct >= 70 else Colors.RED
        print(f"{Colors.BOLD}RESULTS: {color}{self.passed}/{total} PASSED ({pct:.1f}%){Colors.END}")
        print(f"{Colors.BOLD}{'='*70}{Colors.END}")
        
        return 0 if self.failed == 0 else 1

if __name__ == "__main__":
    runner = TestRunner()
    sys.exit(runner.run_all())
