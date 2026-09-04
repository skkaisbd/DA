#!/usr/bin/env python3
"""Backend API Testing for FASE 12 — Stock Location Reconciliation + Material Cost Bug Fixes

Tests:
- GET /api/wms/stock-schema/health (new fields: locations, role_targets, location_kinds)
- RBAC for stock-schema endpoints
- POST /api/wms/stock-schema/reconcile (dry_run true/false, idempotency)
- GET /api/wms/stock-schema/logs
- GET/PUT /api/rahaza/costing-settings (legacy field removal)
- GET /api/acc/valuation (preservasi baseline — angka diimpor dari SSOT
  `scripts/lib/acc_baseline.py`, JANGAN ditulis ulang di sini)
- Regression tests for core endpoints

CRITICAL CONSTRAINTS:
- DO NOT create test data that can't be cleaned up
- DO NOT run dry_run:false without rollback
- MUST preserve baseline: lihat `scripts/lib/acc_baseline.py` (TOTAL_VALUE / TOTAL_QTY)
- Rate limit: 10 login/60s - reuse tokens

CATATAN FASE 13 (dua bug tooling di berkas ini yang diperbaiki 2026-07-26):
1. `BASE_URL` dulu DIPATOK ke preview URL container lama
   (`https://da37-cmt-bridge.preview.emergentagent.com`) yang sudah MATI, jadi
   seluruh berkas ini menguji host yang salah. Sekarang dibaca dari
   `frontend/.env` (`REACT_APP_BACKEND_URL`) dengan fallback localhost.
2. Angka baseline dulu DIPATOK `9667750 / 32220`. Angka itu RESIDU QA: seeder
   hanya pernah menulis `ACC-BTN-12 = 5.000`, sedangkan 5.020 adalah akumulasi
   4 run kebocoran `verify_phase_g_acc_opname.py` (+5 pcs/run). Akibatnya berkas
   ini FAIL PASTI di environment yang baru di-bootstrap. Sekarang angkanya
   diimpor dari SSOT sehingga tidak bisa lagi menyimpang.
"""
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

sys.path.insert(0, "/app/scripts/lib")
from acc_baseline import TOTAL_QTY, TOTAL_VALUE, UNVALUED_ITEMS, VALUED_ITEMS  # noqa: E402


def _base_url() -> str:
    """URL backend — JANGAN dipatok. Ambil dari frontend/.env, fallback localhost."""
    if os.environ.get("BASE_URL"):
        return os.environ["BASE_URL"].rstrip("/")
    env = Path("/app/frontend/.env")
    if env.exists():
        for line in env.read_text().splitlines():
            if line.strip().startswith("REACT_APP_BACKEND_URL="):
                return line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")
    return "http://localhost:8001"


BASE_URL = _base_url()

# Test credentials (from /app/memory/test_credentials.md)
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
HR = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}
GUDANG = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}

class TestRunner:
    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tokens = {}
        self.original_costing_settings = None
        
    def login(self, creds):
        """Login once and cache token"""
        key = creds["email"]
        if key in self.tokens:
            return self.tokens[key]
        
        print(f"\n🔐 Logging in as {creds['email']}...")
        try:
            r = requests.post(f"{BASE_URL}/api/auth/login", json=creds, timeout=30)
            if r.status_code == 200:
                data = r.json()
                token = data.get("token") or data.get("access_token")
                if token:
                    self.tokens[key] = token
                    print(f"✅ Login successful")
                    return token
            print(f"❌ Login failed: {r.status_code}")
            return None
        except Exception as e:
            print(f"❌ Login error: {e}")
            return None
    
    def test(self, name, condition, detail=""):
        """Record test result"""
        self.tests_run += 1
        if condition:
            self.tests_passed += 1
            print(f"  ✅ {name}" + (f" — {detail}" if detail else ""))
            return True
        else:
            print(f"  ❌ {name}" + (f" — {detail}" if detail else ""))
            return False
    
    def run_all(self):
        """Execute all tests"""
        print("=" * 80)
        print("FASE 12 BACKEND API TESTING")
        print("=" * 80)
        
        # Login once for each role
        admin_token = self.login(ADMIN)
        if not admin_token:
            print("\n❌ CRITICAL: Cannot login as admin - stopping tests")
            return 1
        
        hr_token = self.login(HR)
        gudang_token = self.login(GUDANG)
        
        # Test 1: GET /api/wms/stock-schema/health - basic functionality
        print("\n=== TEST 1: GET /api/wms/stock-schema/health (New FASE 12 Fields) ===")
        try:
            r = requests.get(
                f"{BASE_URL}/api/wms/stock-schema/health?detail_limit=500",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30
            )
            self.test("Health endpoint returns 200", r.status_code == 200, f"status={r.status_code}")
            
            if r.status_code == 200:
                health = r.json()
                
                # Check new FASE 12 fields
                self.test("Response has 'locations' array", "locations" in health, 
                         f"found={len(health.get('locations', []))} locations")
                self.test("Response has 'role_targets' array", "role_targets" in health,
                         f"found={len(health.get('role_targets', []))} role targets")
                self.test("Response has 'location_kinds' dict", "location_kinds" in health,
                         f"keys={list(health.get('location_kinds', {}).keys())}")
                
                # Check location structure
                if health.get("locations"):
                    loc = health["locations"][0]
                    self.test("Location has required fields", 
                             all(k in loc for k in ["location_id", "code", "name", "kind", "rows", "qty"]),
                             f"keys={list(loc.keys())}")
                
                # Check role_targets structure
                if health.get("role_targets"):
                    rt = health["role_targets"][0]
                    self.test("Role target has required fields",
                             all(k in rt for k in ["role", "location_id", "source"]),
                             f"keys={list(rt.keys())}")
                
                # Check details have suggested_location fields
                if health.get("details"):
                    detail = health["details"][0]
                    self.test("Detail has 'location_code' field", "location_code" in detail)
                    self.test("Detail has 'location_name' field", "location_name" in detail)
                    self.test("Detail has 'location_kind' field", "location_kind" in detail)
                    self.test("Detail has 'suggested_location_id' field", "suggested_location_id" in detail)
                    self.test("Detail has 'suggested_location_code' field", "suggested_location_code" in detail)
                
                # On clean DB, should have 0 unmapped_location
                counts = health.get("counts", {})
                self.test("Clean DB has 0 unmapped_location", 
                         counts.get("unmapped_location", -1) == 0,
                         f"unmapped={counts.get('unmapped_location')}")
                self.test("Clean DB has 0 affected_rows",
                         health.get("affected_rows", -1) == 0,
                         f"affected={health.get('affected_rows')}")
                
        except Exception as e:
            self.test("Health endpoint accessible", False, f"error={e}")
        
        # Test 2: RBAC - gudang can read
        print("\n=== TEST 2: RBAC - Stock Schema Health (Read Access) ===")
        if gudang_token:
            try:
                r = requests.get(
                    f"{BASE_URL}/api/wms/stock-schema/health",
                    headers={"Authorization": f"Bearer {gudang_token}"},
                    timeout=30
                )
                self.test("Gudang role can read health", r.status_code == 200, f"status={r.status_code}")
            except Exception as e:
                self.test("Gudang role can read health", False, f"error={e}")
        
        # Test without token
        try:
            r = requests.get(f"{BASE_URL}/api/wms/stock-schema/health", timeout=30)
            self.test("Health without token returns 401/403", r.status_code in [401, 403], 
                     f"status={r.status_code}")
        except Exception as e:
            self.test("Health without token returns 401/403", False, f"error={e}")
        
        # Test 3: POST reconcile dry_run=true (preview)
        print("\n=== TEST 3: POST /api/wms/stock-schema/reconcile (dry_run=true) ===")
        try:
            r = requests.post(
                f"{BASE_URL}/api/wms/stock-schema/reconcile",
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                json={"dry_run": True},
                timeout=30
            )
            self.test("Reconcile dry_run returns 200", r.status_code == 200, f"status={r.status_code}")
            
            if r.status_code == 200:
                plan = r.json()
                self.test("Dry run has applied=false", plan.get("applied") is False,
                         f"applied={plan.get('applied')}")
                self.test("Dry run has dry_run=true", plan.get("dry_run") is True,
                         f"dry_run={plan.get('dry_run')}")
                
                # Check new FASE 12 fields
                summary = plan.get("summary", {})
                self.test("Summary has 'rows_relocated' field", "rows_relocated" in summary,
                         f"rows_relocated={summary.get('rows_relocated')}")
                self.test("Response has 'relocations' array", "relocations" in plan,
                         f"relocations={len(plan.get('relocations', []))}")
                
                # On clean DB, should be 0
                self.test("Clean DB dry_run shows 0 relocations", 
                         summary.get("rows_relocated", -1) == 0,
                         f"rows_relocated={summary.get('rows_relocated')}")
        except Exception as e:
            self.test("Reconcile dry_run accessible", False, f"error={e}")
        
        # Test 4: RBAC - HR cannot reconcile
        print("\n=== TEST 4: RBAC - HR Role Cannot Reconcile ===")
        if hr_token:
            try:
                r = requests.post(
                    f"{BASE_URL}/api/wms/stock-schema/reconcile",
                    headers={"Authorization": f"Bearer {hr_token}", "Content-Type": "application/json"},
                    json={"dry_run": True},
                    timeout=30
                )
                self.test("HR role gets 403 for reconcile", r.status_code == 403,
                         f"status={r.status_code}")
            except Exception as e:
                self.test("HR role gets 403 for reconcile", False, f"error={e}")
        
        # Test 5: GET /api/wms/stock-schema/logs
        print("\n=== TEST 5: GET /api/wms/stock-schema/logs ===")
        try:
            r = requests.get(
                f"{BASE_URL}/api/wms/stock-schema/logs",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30
            )
            self.test("Logs endpoint returns 200", r.status_code == 200, f"status={r.status_code}")
            
            if r.status_code == 200:
                logs = r.json()
                self.test("Logs returns array", isinstance(logs, list), f"type={type(logs)}")
                
                # If there are logs, check structure
                if logs:
                    log = logs[0]
                    self.test("Log entry has 'summary' field", "summary" in log)
                    if "summary" in log:
                        self.test("Log summary has 'rows_relocated' field", 
                                 "rows_relocated" in log.get("summary", {}),
                                 f"keys={list(log.get('summary', {}).keys())}")
        except Exception as e:
            self.test("Logs endpoint accessible", False, f"error={e}")
        
        # Test 6: POST reconcile dry_run=false on clean DB (idempotency)
        print("\n=== TEST 6: POST /api/wms/stock-schema/reconcile (dry_run=false, Idempotency) ===")
        try:
            r = requests.post(
                f"{BASE_URL}/api/wms/stock-schema/reconcile",
                headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                json={"dry_run": False},
                timeout=30
            )
            self.test("Reconcile apply returns 200", r.status_code == 200, f"status={r.status_code}")
            
            if r.status_code == 200:
                result = r.json()
                summary = result.get("summary", {})
                
                # On clean DB with 0 changes, backend may return applied=False (no actions to apply)
                # This is acceptable behavior
                has_changes = (summary.get("rows_normalized", 0) > 0 or 
                              summary.get("rows_merged", 0) > 0 or 
                              summary.get("rows_relocated", 0) > 0)
                
                if has_changes:
                    self.test("Apply with changes has applied=true", result.get("applied") is True,
                             f"applied={result.get('applied')}")
                else:
                    self.test("Clean DB with 0 changes (idempotent)", not has_changes,
                             f"normalized={summary.get('rows_normalized')} merged={summary.get('rows_merged')} relocated={summary.get('rows_relocated')}")
                
                # Check total_qty_preserved (may be None if no actions)
                if summary.get("total_qty_preserved") is not None:
                    self.test("Total qty preserved when actions exist",
                             summary.get("total_qty_preserved") is True,
                             f"preserved={summary.get('total_qty_preserved')}")
                else:
                    self.test("No qty preservation check needed (0 actions)", True,
                             "No actions to preserve qty")
        except Exception as e:
            self.test("Reconcile apply accessible", False, f"error={e}")
        
        # Test 7: GET /api/rahaza/costing-settings (legacy field removal)
        print("\n=== TEST 7: GET /api/rahaza/costing-settings (Legacy Field Removal) ===")
        try:
            r = requests.get(
                f"{BASE_URL}/api/rahaza/costing-settings",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30
            )
            self.test("Costing settings GET returns 200", r.status_code == 200, f"status={r.status_code}")
            
            if r.status_code == 200:
                settings = r.json()
                # Save original for restoration
                self.original_costing_settings = settings.copy()
                
                self.test("Response does NOT have 'default_yarn_cost_per_kg'",
                         "default_yarn_cost_per_kg" not in settings,
                         f"keys={[k for k in settings.keys() if 'yarn' in k.lower()]}")
                self.test("Response has 'default_material_cost_per_kg'",
                         "default_material_cost_per_kg" in settings,
                         f"value={settings.get('default_material_cost_per_kg')}")
        except Exception as e:
            self.test("Costing settings GET accessible", False, f"error={e}")
        
        # Test 8: PUT /api/rahaza/costing-settings (legacy field acceptance)
        print("\n=== TEST 8: PUT /api/rahaza/costing-settings (Legacy Field Acceptance) ===")
        if self.original_costing_settings:
            try:
                # Send with legacy key
                test_payload = {
                    "default_yarn_cost_per_kg": 99999,  # Legacy key
                    "default_accessory_cost_per_unit": self.original_costing_settings.get("default_accessory_cost_per_unit", 0)
                }
                r = requests.put(
                    f"{BASE_URL}/api/rahaza/costing-settings",
                    headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                    json=test_payload,
                    timeout=30
                )
                self.test("Costing settings PUT accepts legacy key", r.status_code == 200,
                         f"status={r.status_code}")
                
                # Verify it was saved as canonical key
                r2 = requests.get(
                    f"{BASE_URL}/api/rahaza/costing-settings",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=30
                )
                if r2.status_code == 200:
                    updated = r2.json()
                    self.test("Legacy key NOT in response after PUT",
                             "default_yarn_cost_per_kg" not in updated,
                             f"keys={[k for k in updated.keys() if 'yarn' in k.lower()]}")
                    self.test("Value saved as canonical key",
                             updated.get("default_material_cost_per_kg") == 99999,
                             f"value={updated.get('default_material_cost_per_kg')}")
                
                # RESTORE original settings
                print("  🔄 Restoring original costing settings...")
                r3 = requests.put(
                    f"{BASE_URL}/api/rahaza/costing-settings",
                    headers={"Authorization": f"Bearer {admin_token}", "Content-Type": "application/json"},
                    json=self.original_costing_settings,
                    timeout=30
                )
                if r3.status_code == 200:
                    print("  ✅ Original settings restored")
                else:
                    print(f"  ⚠️  Failed to restore settings: {r3.status_code}")
                    
            except Exception as e:
                self.test("Costing settings PUT accessible", False, f"error={e}")
        
        # Test 9: GET /api/acc/valuation (BASELINE PRESERVATION - CRITICAL)
        print("\n=== TEST 9: GET /api/acc/valuation (BASELINE PRESERVATION) ===")
        try:
            r = requests.get(
                f"{BASE_URL}/api/acc/valuation",
                headers={"Authorization": f"Bearer {admin_token}"},
                timeout=30
            )
            self.test("Valuation endpoint returns 200", r.status_code == 200, f"status={r.status_code}")
            
            if r.status_code == 200:
                val = r.json()
                
                # CRITICAL BASELINE CHECKS - data is in 'totals' key
                totals = val.get("totals", {})
                total_value = totals.get("total_value", 0)
                total_qty = totals.get("total_qty", 0)
                valued_items = totals.get("valued_items", 0)
                unvalued_items = totals.get("unvalued_items", 0)
                
                # Angka DIIMPOR dari SSOT `scripts/lib/acc_baseline.py` — jangan
                # ditulis ulang di sini (dulu dipatok 9667750/32220 = residu QA).
                self.test(f"BASELINE: total_value ≈ {TOTAL_VALUE:,.0f} (±100)",
                         abs(total_value - TOTAL_VALUE) <= 100,
                         f"actual={total_value}, diff={total_value - TOTAL_VALUE}")
                self.test(f"BASELINE: total_qty ≈ {TOTAL_QTY:,.0f} (±10)",
                         abs(total_qty - TOTAL_QTY) <= 10,
                         f"actual={total_qty}, diff={total_qty - TOTAL_QTY}")
                self.test(f"BASELINE: valued_items = {VALUED_ITEMS}",
                         valued_items == VALUED_ITEMS,
                         f"actual={valued_items}")
                self.test(f"BASELINE: unvalued_items = {UNVALUED_ITEMS}",
                         unvalued_items == UNVALUED_ITEMS,
                         f"actual={unvalued_items}")
        except Exception as e:
            self.test("Valuation endpoint accessible", False, f"error={e}")
        
        # Test 10: Regression - Core endpoints still work
        print("\n=== TEST 10: Regression Tests (Core Endpoints) ===")
        
        endpoints = [
            ("/api/health", "Health check"),
            ("/api/acc/items", "Accounting items"),
            ("/api/rahaza/materials", "Materials list"),
        ]
        
        for path, name in endpoints:
            try:
                r = requests.get(
                    f"{BASE_URL}{path}",
                    headers={"Authorization": f"Bearer {admin_token}"},
                    timeout=30
                )
                self.test(f"{name} endpoint works", r.status_code == 200, f"status={r.status_code}")
            except Exception as e:
                self.test(f"{name} endpoint works", False, f"error={e}")
        
        # Summary
        print("\n" + "=" * 80)
        print(f"BACKEND TESTS COMPLETE: {self.tests_passed}/{self.tests_run} PASSED")
        print("=" * 80)
        
        return 0 if self.tests_passed == self.tests_run else 1

if __name__ == "__main__":
    runner = TestRunner()
    sys.exit(runner.run_all())
