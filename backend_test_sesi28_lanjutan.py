#!/usr/bin/env python3
"""
Backend API Testing - Sesi #28 LANJUTAN (iteration_80)
FOCUS: Verify backend guards for GR qty=0 and location_id empty
Test data: PO-20260819-003 (approved, 50 pcs Label Woven DA, sisa 50)
"""
import requests
import sys
import json
from datetime import datetime

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_CREDS = {"email": "admin@garment.com", "password": "Admin@123"}

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def log(msg, status="INFO"):
    color = Colors.GREEN if status == "PASS" else Colors.RED if status == "FAIL" else Colors.YELLOW if status == "WARN" else Colors.BLUE
    print(f"{color}[{status}]{Colors.RESET} {msg}")

def login():
    """Login and get token (rate limit 10/60s - reuse token)"""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS, timeout=30)
        if r.status_code != 200:
            log(f"Login failed: HTTP {r.status_code}", "FAIL")
            sys.exit(1)
        data = r.json()
        token = data.get("token")
        if not token:
            log(f"Login response missing 'token' field", "FAIL")
            sys.exit(1)
        log("Login successful (admin@garment.com)", "PASS")
        return token
    except Exception as e:
        log(f"Login exception: {e}", "FAIL")
        sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
# WAJIB #7 — Backend Guards (qty=0 and location_id empty)
# ══════════════════════════════════════════════════════════════════════════════

def test_find_po_20260819_003(token):
    """Find PO-20260819-003 (approved, 50 pcs Label Woven DA, sisa 50)"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/api/rahaza/purchase-orders", headers=headers, timeout=30)
        
        if r.status_code != 200:
            log(f"GET /api/rahaza/purchase-orders HTTP {r.status_code}", "FAIL")
            return None
        
        pos = r.json()
        target_po = None
        for po in pos:
            if po.get("po_number") == "PO-20260819-003":
                target_po = po
                break
        
        if not target_po:
            log("PO-20260819-003 not found", "FAIL")
            return None
        
        status = target_po.get("status")
        items = target_po.get("items", [])
        item_count = len(items)
        
        # Find Label Woven DA item
        label_woven_item = None
        for item in items:
            if "Label Woven DA" in item.get("material_name", ""):
                label_woven_item = item
                break
        
        if not label_woven_item:
            log(f"PO-20260819-003 found but no 'Label Woven DA' item", "FAIL")
            return None
        
        qty_ordered = label_woven_item.get("qty_ordered", 0)
        qty_received = label_woven_item.get("qty_received", 0)
        remaining = qty_ordered - qty_received
        
        log(f"Found PO-20260819-003: status={status}, items={item_count}, Label Woven DA: {qty_ordered} ordered, {qty_received} received, {remaining} remaining", "PASS")
        return target_po
    except Exception as e:
        log(f"test_find_po_20260819_003 exception: {e}", "FAIL")
        return None

def test_create_gr_from_po_003(token, po_id):
    """Create GR from PO-20260819-003 (will have received_qty=0 initially)"""
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        r = requests.post(
            f"{BASE_URL}/api/rahaza/purchase-orders/{po_id}/create-gr",
            headers=headers,
            json={},
            timeout=30
        )
        
        if r.status_code != 200:
            log(f"POST /api/rahaza/purchase-orders/{po_id}/create-gr HTTP {r.status_code}: {r.text[:200]}", "FAIL")
            return None
        
        gr = r.json()
        receipt_number = gr.get("receipt_number")
        items = gr.get("items", [])
        status = gr.get("status")
        
        # Verify GR was created with received_qty=0.0 (correct initial state)
        all_zero = all(float(item.get("received_qty", -1)) == 0.0 for item in items)
        if not all_zero:
            log(f"GR {receipt_number}: items should have received_qty=0.0 initially", "FAIL")
            return None
        
        log(f"Created GR {receipt_number} from PO-20260819-003: status={status}, {len(items)} items, all received_qty=0.0 (correct)", "PASS")
        return gr
    except Exception as e:
        log(f"test_create_gr_from_po_003 exception: {e}", "FAIL")
        return None

def test_backend_guard_qty_zero(token, receipt_id, items):
    """WAJIB #7a: Backend MUST reject qty=0 with HTTP 400"""
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Prepare items with received_qty=0 (should be rejected)
        items_zero = []
        for item in items:
            items_zero.append({
                **item,
                "received_qty": 0.0,
                "rejected_qty": 0.0
            })
        
        r = requests.put(
            f"{BASE_URL}/api/wms/legacy/receiving/{receipt_id}",
            headers=headers,
            json={
                "status": "received",
                "items": items_zero
            },
            timeout=30
        )
        
        if r.status_code == 400:
            error_msg = r.json().get("detail", "")
            if "Qty diterima masih 0" in error_msg:
                log(f"Backend guard qty=0 WORKING: HTTP 400 with message '{error_msg[:80]}...'", "PASS")
                return True
            else:
                log(f"Backend guard qty=0: HTTP 400 but wrong message: {error_msg}", "FAIL")
                return False
        else:
            log(f"Backend guard qty=0 FAILED: expected HTTP 400, got {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"test_backend_guard_qty_zero exception: {e}", "FAIL")
        return False

def test_backend_guard_location_empty(token, receipt_id, items):
    """WAJIB #7b: Backend MUST reject empty location_id with HTTP 400"""
    try:
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        
        # Prepare items with qty > 0 but no location
        items_with_qty = []
        for item in items[:1]:  # Just first item
            items_with_qty.append({
                **item,
                "received_qty": float(item.get("expected_qty", 10)),
                "rejected_qty": 0.0
            })
        
        r = requests.put(
            f"{BASE_URL}/api/wms/legacy/receiving/{receipt_id}",
            headers=headers,
            json={
                "status": "received",
                "items": items_with_qty,
                "location_id": ""  # empty location (should be rejected)
            },
            timeout=30
        )
        
        if r.status_code == 400:
            error_msg = r.json().get("detail", "")
            if "Lokasi tujuan belum dipilih" in error_msg or "location" in error_msg.lower():
                log(f"Backend guard location_id empty WORKING: HTTP 400 with message '{error_msg[:80]}...'", "PASS")
                return True
            else:
                log(f"Backend guard location_id: HTTP 400 but wrong message: {error_msg}", "FAIL")
                return False
        else:
            log(f"Backend guard location_id FAILED: expected HTTP 400, got {r.status_code}", "FAIL")
            return False
    except Exception as e:
        log(f"test_backend_guard_location_empty exception: {e}", "FAIL")
        return False

def test_cleanup_draft_gr(token, receipt_id):
    """Clean up: Delete the draft GR we created for testing"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.delete(
            f"{BASE_URL}/api/wms/legacy/receiving/{receipt_id}",
            headers=headers,
            timeout=30
        )
        
        if r.status_code == 200:
            log(f"Cleanup: Deleted draft GR {receipt_id}", "PASS")
            return True
        else:
            log(f"Cleanup: Failed to delete GR {receipt_id}: HTTP {r.status_code}", "WARN")
            return False
    except Exception as e:
        log(f"test_cleanup_draft_gr exception: {e}", "WARN")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# WAJIB #9 — Audit Tools (sync-audit and sku-bridge health)
# ══════════════════════════════════════════════════════════════════════════════

def test_sync_audit_report(token):
    """WAJIB #9a: GET /api/sync-audit/report must be HIJAU with CRITICAL=0 and HIGH=0"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/api/sync-audit/report", headers=headers, timeout=30)
        
        if r.status_code != 200:
            log(f"GET /api/sync-audit/report HTTP {r.status_code}", "FAIL")
            return False
        
        data = r.json()
        verdict = data.get("verdict", "").upper()
        critical = data.get("critical_count", 0)
        high = data.get("high_count", 0)
        
        if verdict == "HIJAU" and critical == 0 and high == 0:
            log(f"Sync audit report: verdict={verdict}, CRITICAL={critical}, HIGH={high} ✓", "PASS")
            return True
        else:
            log(f"Sync audit report: verdict={verdict}, CRITICAL={critical}, HIGH={high} (expected HIJAU/0/0)", "FAIL")
            return False
    except Exception as e:
        log(f"test_sync_audit_report exception: {e}", "FAIL")
        return False

def test_sku_bridge_health(token):
    """WAJIB #9b: GET /api/sku-bridge/health must have lines_linked_pct=100 and queue_blocked=0"""
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/api/sku-bridge/health", headers=headers, timeout=30)
        
        if r.status_code != 200:
            log(f"GET /api/sku-bridge/health HTTP {r.status_code}", "FAIL")
            return False
        
        data = r.json()
        lines_linked_pct = data.get("lines_linked_pct", 0)
        queue_blocked = data.get("queue_blocked", 0)
        
        if lines_linked_pct == 100 and queue_blocked == 0:
            log(f"SKU bridge health: lines_linked_pct={lines_linked_pct}%, queue_blocked={queue_blocked} ✓", "PASS")
            return True
        else:
            log(f"SKU bridge health: lines_linked_pct={lines_linked_pct}%, queue_blocked={queue_blocked} (expected 100/0)", "FAIL")
            return False
    except Exception as e:
        log(f"test_sku_bridge_health exception: {e}", "FAIL")
        return False

# ══════════════════════════════════════════════════════════════════════════════
# Main Test Runner
# ══════════════════════════════════════════════════════════════════════════════

def main():
    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}Backend API Testing - Sesi #28 LANJUTAN (iteration_80){Colors.RESET}")
    print(f"{Colors.BOLD}FOCUS: Backend guards (qty=0, location_id empty) + Audit tools{Colors.RESET}")
    print(f"{Colors.BOLD}Test data: PO-20260819-003 (approved, 50 pcs Label Woven DA){Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    
    token = login()
    
    results = {
        "total": 0,
        "passed": 0,
        "failed": 0
    }
    
    # ── WAJIB #7: Backend Guards ─────────────────────────────────────────────
    print(f"\n{Colors.BOLD}{'─'*80}{Colors.RESET}")
    print(f"{Colors.BOLD}WAJIB #7: Backend Guards (qty=0 and location_id empty){Colors.RESET}")
    print(f"{Colors.BOLD}{'─'*80}{Colors.RESET}\n")
    
    # Test 1: Find PO-20260819-003
    results["total"] += 1
    po = test_find_po_20260819_003(token)
    if po:
        results["passed"] += 1
        po_id = po.get("id")
        
        # Test 2: Create GR from PO-20260819-003
        results["total"] += 1
        gr = test_create_gr_from_po_003(token, po_id)
        if gr:
            results["passed"] += 1
            receipt_id = gr.get("id")
            items = gr.get("items", [])
            
            # Test 3: Backend guard qty=0
            results["total"] += 1
            if test_backend_guard_qty_zero(token, receipt_id, items):
                results["passed"] += 1
            else:
                results["failed"] += 1
            
            # Test 4: Backend guard location_id empty
            results["total"] += 1
            if test_backend_guard_location_empty(token, receipt_id, items):
                results["passed"] += 1
            else:
                results["failed"] += 1
            
            # Cleanup: Delete draft GR
            test_cleanup_draft_gr(token, receipt_id)
        else:
            results["failed"] += 1
    else:
        results["failed"] += 1
    
    # ── WAJIB #9: Audit Tools ────────────────────────────────────────────────
    print(f"\n{Colors.BOLD}{'─'*80}{Colors.RESET}")
    print(f"{Colors.BOLD}WAJIB #9: Audit Tools (sync-audit and sku-bridge){Colors.RESET}")
    print(f"{Colors.BOLD}{'─'*80}{Colors.RESET}\n")
    
    # Test 5: Sync audit report
    results["total"] += 1
    if test_sync_audit_report(token):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # Test 6: SKU bridge health
    results["total"] += 1
    if test_sku_bridge_health(token):
        results["passed"] += 1
    else:
        results["failed"] += 1
    
    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"Total Tests:  {results['total']}")
    print(f"{Colors.GREEN}Passed:       {results['passed']}{Colors.RESET}")
    print(f"{Colors.RED}Failed:       {results['failed']}{Colors.RESET}")
    
    success_rate = (results['passed'] / results['total'] * 100) if results['total'] > 0 else 0
    print(f"\nSuccess Rate: {success_rate:.1f}%")
    print(f"{Colors.BOLD}{'='*80}{Colors.RESET}\n")
    
    return 0 if results['failed'] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
