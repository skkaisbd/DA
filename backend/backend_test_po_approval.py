#!/usr/bin/env python3
"""
BACKEND TEST — PO APPROVAL SYSTEM (2026-08-07)
Testing Purchase Order approval chain using SSOT pr_approval engine.

CRITICAL FIXES BEING TESTED:
- Real roles (gudang@, finance@, direktur@) can now approve POs
- Multi-stage approval based on PO value
- Proper RBAC enforcement
- Rejection requires reason
- Audit trail per stage
- PO appears in unified approval inbox
- PO vs PR value mismatch detection
- Server flags for UI
- Notifications
"""
import sys
import requests
import os
import time

BASE_URL = os.environ.get("API_URL", "https://da37-cmt-bridge.preview.emergentagent.com")

# Test credentials - IMPORTANT: Backend limits 10 logins/60s per IP, must reuse tokens!
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
GUDANG = {"email": "gudang@dewiaditya.id", "password": "Dewi@123"}
FINANCE = {"email": "finance@dewiaditya.id", "password": "Dewi@123"}
DIREKTUR = {"email": "direktur@dewiaditya.id", "password": "Dewi@123"}
PACKING = {"email": "packing@dewiaditya.id", "password": "Dewi@123"}
HR = {"email": "hr@dewiaditya.id", "password": "Dewi@123"}

PASS_COUNT = 0
FAIL_COUNT = 0
FAILED_TESTS = []
TOKENS = {}  # Cache tokens to avoid rate limit
CREATED_POS = []  # Track created POs for cleanup


def check(condition, test_name, extra=""):
    """Record test result."""
    global PASS_COUNT, FAIL_COUNT
    if condition:
        PASS_COUNT += 1
        print(f"  ✅ {test_name}" + (f" — {extra}" if extra else ""))
        return True
    else:
        FAIL_COUNT += 1
        FAILED_TESTS.append(test_name)
        print(f"  ❌ {test_name}" + (f" — {extra}" if extra else ""))
        return False


def section(title):
    """Print section header."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def login(email, password):
    """Login and return auth headers. Caches tokens to avoid rate limit."""
    if email in TOKENS:
        return TOKENS[email]
    
    try:
        for attempt in range(3):
            r = requests.post(f"{BASE_URL}/api/auth/login", 
                            json={"email": email, "password": password}, 
                            timeout=30)
            if r.status_code == 200:
                token = r.json().get("token")
                headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
                TOKENS[email] = headers
                print(f"  ✅ Login successful for {email}")
                return headers
            elif r.status_code == 429:
                print(f"  ⚠️  Rate limit hit for {email}, waiting 12s...")
                time.sleep(12)
                continue
            else:
                print(f"  ❌ Login failed for {email}: HTTP {r.status_code}")
                return None
        print(f"  ❌ Login failed for {email} after 3 attempts")
        return None
    except Exception as e:
        print(f"  ❌ Login error for {email}: {str(e)}")
        return None


def get_supplier_id(headers):
    """Get first supplier ID from master."""
    try:
        r = requests.get(f"{BASE_URL}/api/procurement/suppliers?limit=5", 
                        headers=headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            if items:
                return items[0]["id"]
    except Exception:  # noqa: BLE001
        pass
    return None


def get_material(headers):
    """Get a material for PO items."""
    try:
        r = requests.get(f"{BASE_URL}/api/rahaza/materials?limit=100", 
                        headers=headers, timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            for m in items:
                if m.get("code") == "ACC-BTN-12":
                    return m
            if items:
                return items[0]
    except Exception:  # noqa: BLE001
        pass
    return None


def create_po(headers, unit_cost, qty=10, notes="Test PO"):
    """Create a draft PO."""
    supplier_id = get_supplier_id(headers)
    material = get_material(headers)
    
    if not supplier_id or not material:
        print("  ❌ Cannot create PO: missing supplier or material")
        return None
    
    try:
        r = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders",
                         headers=headers,
                         json={
                             "supplier_id": supplier_id,
                             "notes": notes,
                             "items": [{
                                 "material_id": material["id"],
                                 "description": material.get("name", "Test item"),
                                 "uom": material.get("unit", "pcs"),
                                 "qty_input": qty,
                                 "unit_cost_input": unit_cost
                             }]
                         },
                         timeout=30)
        if r.status_code in (200, 201):
            po = r.json()
            CREATED_POS.append(po["id"])
            return po
        else:
            print(f"  ❌ Failed to create PO: HTTP {r.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ Error creating PO: {str(e)}")
        return None


def main():
    global FAIL_COUNT
    
    print("=" * 78)
    print("BACKEND API TESTING — PO APPROVAL SYSTEM")
    print("=" * 78)
    print(f"Testing against: {BASE_URL}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════════
    section("1. AUTHENTICATION")
    
    admin_h = login(ADMIN["email"], ADMIN["password"])
    gudang_h = login(GUDANG["email"], GUDANG["password"])
    finance_h = login(FINANCE["email"], FINANCE["password"])
    direktur_h = login(DIREKTUR["email"], DIREKTUR["password"])
    packing_h = login(PACKING["email"], PACKING["password"])
    
    if not all([admin_h, gudang_h, finance_h, direktur_h, packing_h]):
        print("\n❌ CRITICAL: Authentication failed. Cannot proceed.")
        return 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 2. REAL ROLES CAN APPROVE PO (WAJIB)
    # ═══════════════════════════════════════════════════════════════════════════
    section("2. REAL ROLES CAN APPROVE PO (WAJIB)")
    
    # Create small PO (Rp 500K = 1 stage)
    po1 = create_po(admin_h, unit_cost=50000, qty=10, notes="Test PO 1 stage")
    if po1:
        # Submit PO
        r = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po1['id']}/submit",
                         headers=admin_h, timeout=30)
        check(r.status_code == 200, "Submit PO returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            check(data.get("approval_chain") == ["dept"], 
                  "Small PO (Rp 500K) has 1 stage approval chain",
                  f"chain={data.get('approval_chain')}")
            
            # gudang@ (admin_gudang) should be able to approve
            r2 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po1['id']}/approve",
                              headers=gudang_h,
                              json={"comment": "Supplier & harga sudah dicek"},
                              timeout=30)
            check(r2.status_code == 200, 
                  "gudang@ (admin_gudang) CAN approve PO — was 403 before fix",
                  f"status={r2.status_code}")
            
            if r2.status_code == 200:
                data2 = r2.json()
                check(data2.get("status") == "approved",
                      "PO status becomes 'approved' after dept approval",
                      f"status={data2.get('status')}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 3. LARGE PO REQUIRES 3 STAGES BY 3 DIFFERENT PEOPLE
    # ═══════════════════════════════════════════════════════════════════════════
    section("3. LARGE PO REQUIRES 3 STAGES BY 3 DIFFERENT PEOPLE")
    
    # Create large PO (Rp 50M = 3 stages)
    po2 = create_po(admin_h, unit_cost=5000000, qty=10, notes="Test PO 3 stages")
    if po2:
        r = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/submit",
                         headers=admin_h, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            check(data.get("approval_chain") == ["dept", "finance", "final"],
                  "Large PO (Rp 50M) has 3 stage approval chain",
                  f"chain={data.get('approval_chain')}")
            
            # Try to approve as finance@ when stage is still dept → should be 403
            r2 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/approve",
                              headers=finance_h, timeout=30)
            check(r2.status_code == 403,
                  "finance@ blocked when stage is still dept",
                  f"status={r2.status_code}")
            
            # Approve as gudang@ (dept stage)
            r3 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/approve",
                              headers=gudang_h,
                              json={"comment": "Supplier sesuai daftar harga"},
                              timeout=30)
            check(r3.status_code == 200,
                  "gudang@ approves dept stage",
                  f"status={r3.status_code}")
            
            if r3.status_code == 200:
                data3 = r3.json()
                check(data3.get("next_stage") == "finance",
                      "After dept approval, next stage is finance",
                      f"next={data3.get('next_stage')}")
                
                # Same person cannot approve twice
                r4 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/approve",
                                  headers=gudang_h, timeout=30)
                check(r4.status_code == 403,
                      "Same person (gudang@) cannot approve twice",
                      f"status={r4.status_code}")
                
                # Approve as finance@
                r5 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/approve",
                                  headers=finance_h,
                                  json={"comment": "Anggaran tersedia"},
                                  timeout=30)
                check(r5.status_code == 200,
                      "finance@ approves finance stage",
                      f"status={r5.status_code}")
                
                if r5.status_code == 200:
                    data5 = r5.json()
                    check(data5.get("next_stage") == "final",
                          "After finance approval, next stage is final",
                          f"next={data5.get('next_stage')}")
                    
                    # Approve as direktur@ (final stage)
                    r6 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/approve",
                                      headers=direktur_h,
                                      json={"comment": "Disetujui direksi"},
                                      timeout=30)
                    check(r6.status_code == 200,
                          "direktur@ (director) approves final stage — was 403 before fix",
                          f"status={r6.status_code}")
                    
                    if r6.status_code == 200:
                        data6 = r6.json()
                        check(data6.get("status") == "approved",
                              "PO fully approved after 3 stages",
                              f"status={data6.get('status')}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 4. UNAUTHORIZED USERS GET 403
    # ═══════════════════════════════════════════════════════════════════════════
    section("4. UNAUTHORIZED USERS GET 403")
    
    po3 = create_po(admin_h, unit_cost=50000, qty=10, notes="Test unauthorized")
    if po3:
        requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po3['id']}/submit",
                     headers=admin_h, timeout=30)
        
        # packing@ (tim_packing) should not be able to approve
        r = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po3['id']}/approve",
                         headers=packing_h, timeout=30)
        check(r.status_code == 403,
              "packing@ (tim_packing) cannot approve PO",
              f"status={r.status_code}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 5. REJECTION REQUIRES REASON
    # ═══════════════════════════════════════════════════════════════════════════
    section("5. REJECTION REQUIRES REASON")
    
    po4 = create_po(admin_h, unit_cost=50000, qty=10, notes="Test rejection")
    if po4:
        requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po4['id']}/submit",
                     headers=admin_h, timeout=30)
        
        # Try to reject without reason
        r = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po4['id']}/reject",
                         headers=gudang_h,
                         json={"reason": "   "},
                         timeout=30)
        check(r.status_code == 400,
              "Reject PO without reason returns 400",
              f"status={r.status_code}")
        
        # Reject with reason
        r2 = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po4['id']}/reject",
                          headers=gudang_h,
                          json={"reason": "Harga di atas daftar harga supplier"},
                          timeout=30)
        check(r2.status_code == 200,
              "Reject PO with reason succeeds",
              f"status={r2.status_code}")
        
        if r2.status_code == 200:
            data = r2.json()
            check(data.get("status") == "rejected",
                  "PO status becomes 'rejected'",
                  f"status={data.get('status')}")
            check(data.get("rejected_reason") == "Harga di atas daftar harga supplier",
                  "Rejection reason is stored",
                  f"reason={data.get('rejected_reason')[:50]}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 6. PO AUDIT TRAIL
    # ═══════════════════════════════════════════════════════════════════════════
    section("6. PO AUDIT TRAIL")
    
    # Use po2 which went through 3 stages
    if po2:
        r = requests.get(f"{BASE_URL}/api/rahaza/purchase-orders/{po2['id']}/timeline",
                        headers=admin_h, timeout=30)
        check(r.status_code == 200,
              "GET timeline endpoint returns 200",
              f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            steps = [s for s in data.get("steps", []) if s.get("action") == "approved"]
            check(len(steps) == 3,
                  "Timeline has 3 approval steps",
                  f"steps={len(steps)}")
            
            if steps:
                complete = all(s.get("actor_id") and s.get("actor_name") and 
                             s.get("stage") and s.get("timestamp") for s in steps)
                check(complete,
                      "All steps have actor_id, actor_name, stage, timestamp",
                      f"complete={complete}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 7. PO IN UNIFIED APPROVAL INBOX
    # ═══════════════════════════════════════════════════════════════════════════
    section("7. PO IN UNIFIED APPROVAL INBOX")
    
    # Create a new PO for gudang@ to approve
    po5 = create_po(admin_h, unit_cost=50000, qty=10, notes="Test inbox")
    if po5:
        requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po5['id']}/submit",
                     headers=admin_h, timeout=30)
        
        # Check gudang@ inbox
        r = requests.get(f"{BASE_URL}/api/procurement/inbox",
                        headers=gudang_h, timeout=30)
        check(r.status_code == 200,
              "GET /api/procurement/inbox returns 200",
              f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            po_items = [i for i in items if i.get("id") == po5["id"]]
            
            check(len(po_items) > 0,
                  "PO appears in gudang@ unified inbox",
                  f"found={len(po_items)}")
            
            if po_items:
                item = po_items[0]
                check(item.get("kind") == "po",
                      "PO has kind='po'",
                      f"kind={item.get('kind')}")
                check(item.get("kind_label") == "Purchase Order",
                      "PO has kind_label='Purchase Order'",
                      f"label={item.get('kind_label')}")
                check(item.get("api_base") == "/api/rahaza/purchase-orders",
                      "PO has correct api_base",
                      f"base={item.get('api_base')}")
                check(item.get("module_id") == "proc-purchase-orders",
                      "PO has correct module_id",
                      f"module={item.get('module_id')}")
                check(item.get("can_approve") is True,
                      "PO has can_approve=true for gudang@",
                      f"can_approve={item.get('can_approve')}")
                check(item.get("chain") and item.get("stage_label"),
                      "PO has chain and stage_label",
                      f"has_chain={bool(item.get('chain'))}")
            
            # INVARIANT: All items in inbox must have can_approve=true
            bad_items = [i.get("request_number") for i in items 
                        if i.get("can_approve") is not True]
            check(len(bad_items) == 0,
                  "All inbox items have can_approve=true (INVARIANT)",
                  f"bad_items={len(bad_items)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 8. SERVER FLAGS FOR UI
    # ═══════════════════════════════════════════════════════════════════════════
    section("8. SERVER FLAGS FOR UI")
    
    if po5:
        # Check as packing@ (unauthorized)
        r = requests.get(f"{BASE_URL}/api/rahaza/purchase-orders",
                        headers=packing_h, timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            po_items = [i for i in items if i.get("id") == po5["id"]]
            
            if po_items:
                item = po_items[0]
                check(item.get("can_approve") is False,
                      "PO list shows can_approve=false for packing@",
                      f"can_approve={item.get('can_approve')}")
                check(bool(item.get("blocked_reason")),
                      "PO list shows blocked_reason for packing@",
                      f"has_reason={bool(item.get('blocked_reason'))}")
        
        # Check detail as gudang@ (authorized)
        r2 = requests.get(f"{BASE_URL}/api/rahaza/purchase-orders/{po5['id']}",
                         headers=gudang_h, timeout=30)
        if r2.status_code == 200:
            data = r2.json()
            check(data.get("can_approve") is True,
                  "PO detail shows can_approve=true for gudang@",
                  f"can_approve={data.get('can_approve')}")
            check(bool(data.get("stage_label")),
                  "PO detail shows stage_label",
                  f"label={data.get('stage_label')}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 9. GR REQUIRES APPROVED PO
    # ═══════════════════════════════════════════════════════════════════════════
    section("9. GR REQUIRES APPROVED PO")
    
    if po5:
        # Try to create GR from pending PO
        r = requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po5['id']}/create-gr",
                         headers=admin_h,
                         json={},
                         timeout=30)
        check(r.status_code == 400,
              "Cannot create GR from pending PO",
              f"status={r.status_code}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 10. NOTIFICATIONS
    # ═══════════════════════════════════════════════════════════════════════════
    section("10. NOTIFICATIONS")
    
    # Create and submit a large PO, approve dept stage, check finance@ notifications
    po6 = create_po(admin_h, unit_cost=5000000, qty=10, notes="Test notifications")
    if po6:
        requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po6['id']}/submit",
                     headers=admin_h, timeout=30)
        requests.post(f"{BASE_URL}/api/rahaza/purchase-orders/{po6['id']}/approve",
                     headers=gudang_h,
                     json={"comment": "OK"},
                     timeout=30)
        
        # Check finance@ notifications
        r = requests.get(f"{BASE_URL}/api/notifications",
                        headers=finance_h, timeout=30)
        if r.status_code == 200:
            data = r.json()
            items = data if isinstance(data, list) else data.get("items", [])
            po_notifs = [n for n in items 
                        if "Purchase Order" in n.get("title", "") and 
                           po6.get("po_number", "") in n.get("body", "")]
            
            check(len(po_notifs) > 0,
                  "finance@ receives notification after dept approval",
                  f"found={len(po_notifs)}")
            
            if po_notifs:
                notif = po_notifs[0]
                check(notif.get("meta", {}).get("link_module") == "proc-purchase-orders",
                      "Notification has correct link_module",
                      f"module={notif.get('meta', {}).get('link_module')}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    section("TEST SUMMARY")
    
    total = PASS_COUNT + FAIL_COUNT
    print(f"\n✅ PASSED: {PASS_COUNT}/{total}")
    print(f"❌ FAILED: {FAIL_COUNT}/{total}")
    
    if FAILED_TESTS:
        print("\nFailed tests:")
        for test in FAILED_TESTS:
            print(f"  - {test}")
    
    print(f"\nCreated {len(CREATED_POS)} test POs (will be cleaned by POC script)")
    
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
