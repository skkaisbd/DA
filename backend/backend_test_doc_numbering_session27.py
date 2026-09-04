#!/usr/bin/env python3
"""
BACKEND TEST — DOCUMENT NUMBERING SESSION #27 (FASE G)
Testing document numbering enforcement for 3 document types + catalog + legacy endpoint + fabric rolls.
"""
import sys
import requests
import os
import time

# Public URL for testing
BASE_URL = os.environ.get("API_URL", "https://da37-cmt-bridge.preview.emergentagent.com")

# Test credentials
ADMIN_CRED = {"email": "admin@garment.com", "password": "Admin@123"}

# Test counters
PASS_COUNT = 0
FAIL_COUNT = 0
FAILED_TESTS = []

# Track created documents for cleanup
CREATED_DOCS = {
    "expense_claims": [],
    "kreator_requests": [],
    "acc_purchase_requests": []
}

# Track original modes for restoration
ORIGINAL_MODES = {}


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
    """Login and return auth headers."""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        if r.status_code == 200:
            token = r.json().get("token")
            print(f"  ✅ Login successful for {email}")
            return {"Authorization": f"Bearer {token}"}
        else:
            print(f"  ❌ Login failed for {email}: HTTP {r.status_code}")
            return None
    except Exception as e:
        print(f"  ❌ Login error for {email}: {str(e)}")
        return None


def get_doc_numbering_mode(headers, key):
    """Get current mode for a document type."""
    try:
        r = requests.get(f"{BASE_URL}/api/admin/doc-numbering", headers=headers, timeout=30)
        if r.status_code == 200:
            catalog = r.json().get("catalog", [])
            for entry in catalog:
                if entry.get("key") == key:
                    return entry.get("mode")
        return None
    except Exception as e:
        print(f"  ⚠️  Error getting mode for {key}: {str(e)}")
        return None


def set_doc_numbering_mode(headers, key, mode):
    """Set mode for a document type."""
    try:
        r = requests.put(
            f"{BASE_URL}/api/admin/doc-numbering",
            headers=headers,
            json={"key": key, "mode": mode},
            timeout=30
        )
        return r.status_code == 200
    except Exception as e:
        print(f"  ⚠️  Error setting mode for {key}: {str(e)}")
        return False


def cleanup_test_docs(headers):
    """Clean up test documents."""
    print("\n" + "=" * 78)
    print("CLEANUP — Deleting test documents")
    print("=" * 78)
    
    # Expense claims
    for claim_id in CREATED_DOCS["expense_claims"]:
        try:
            r = requests.delete(f"{BASE_URL}/api/hr/expenses/claims/{claim_id}", headers=headers, timeout=30)
            if r.status_code in [200, 204]:
                print(f"  ✅ Deleted expense claim {claim_id}")
            else:
                print(f"  ⚠️  Could not delete expense claim {claim_id}: HTTP {r.status_code}")
        except Exception as e:
            print(f"  ⚠️  Error deleting expense claim {claim_id}: {str(e)}")
    
    # Note: Kreator requests and acc purchase requests may not have DELETE endpoints
    # Just report what was created
    if CREATED_DOCS["kreator_requests"]:
        print(f"  ℹ️  Created kreator requests (no DELETE endpoint): {CREATED_DOCS['kreator_requests']}")
    if CREATED_DOCS["acc_purchase_requests"]:
        print(f"  ℹ️  Created acc purchase requests (no DELETE endpoint): {CREATED_DOCS['acc_purchase_requests']}")


def restore_modes(headers):
    """Restore original modes."""
    print("\n" + "=" * 78)
    print("CLEANUP — Restoring original modes")
    print("=" * 78)
    
    for key, original_mode in ORIGINAL_MODES.items():
        if set_doc_numbering_mode(headers, key, original_mode):
            print(f"  ✅ Restored {key} to {original_mode}")
        else:
            print(f"  ⚠️  Could not restore {key} to {original_mode}")


def main():
    global FAIL_COUNT
    
    print("=" * 78)
    print("BACKEND API TESTING — DOCUMENT NUMBERING SESSION #27 (FASE G)")
    print("=" * 78)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 1. AUTHENTICATION
    # ═══════════════════════════════════════════════════════════════════════════
    section("1. AUTHENTICATION")
    
    admin_headers = login(ADMIN_CRED["email"], ADMIN_CRED["password"])
    if not admin_headers:
        print("\n❌ CRITICAL: Admin login failed. Cannot proceed.")
        return 1
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 2. DOCUMENT NUMBERING CATALOG
    # ═══════════════════════════════════════════════════════════════════════════
    section("2. DOCUMENT NUMBERING CATALOG")
    
    try:
        r = requests.get(f"{BASE_URL}/api/admin/doc-numbering", headers=admin_headers, timeout=30)
        check(r.status_code == 200, "GET /api/admin/doc-numbering returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            catalog = data.get("items", [])  # API returns 'items' not 'catalog'
            
            check(len(catalog) == 51, "Catalog has 51 document types", f"found={len(catalog)}")
            
            # Count by status
            enforced = [e for e in catalog if e.get("policy_enforced")]
            always_auto = [e for e in catalog if e.get("auto_only")]
            pending = [e for e in catalog if e.get("pending_enforce")]
            
            check(len(enforced) == 27, "27 types are enforced", f"found={len(enforced)}")
            check(len(always_auto) == 23, "23 types are always-auto", f"found={len(always_auto)}")
            check(len(pending) == 1, "1 type is pending", f"found={len(pending)}")
            
            # Check that always-auto types have reasons
            always_auto_with_reason = [e for e in always_auto if e.get("alasan_otomatis")]
            check(
                len(always_auto_with_reason) == len(always_auto),
                "All always-auto types have reasons",
                f"with_reason={len(always_auto_with_reason)}/{len(always_auto)}"
            )
            
            # Check specific types we'll test
            expense_claims = next((e for e in catalog if e["key"] == "rahaza_expense_claims.claim_number"), None)
            check(expense_claims is not None, "Expense Claims in catalog")
            if expense_claims:
                check(expense_claims.get("policy_enforced"), "Expense Claims is enforced")
            
            kreator_requests = next((e for e in catalog if e["key"] == "dewi_kreator_requests.request_code"), None)
            check(kreator_requests is not None, "Kreator Requests in catalog")
            if kreator_requests:
                check(kreator_requests.get("policy_enforced"), "Kreator Requests is enforced")
            
            acc_pr = next((e for e in catalog if e["key"] == "acc_purchase_requests.pr_number"), None)
            check(acc_pr is not None, "Accessory Purchase Requests in catalog")
            if acc_pr:
                check(acc_pr.get("policy_enforced"), "Accessory Purchase Requests is enforced")
    
    except Exception as e:
        check(False, "GET /api/admin/doc-numbering", f"error={str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 3. MODE CHANGE VALIDATION
    # ═══════════════════════════════════════════════════════════════════════════
    section("3. MODE CHANGE VALIDATION")
    
    # Test changing mode for enforced type (should succeed)
    try:
        r = requests.put(
            f"{BASE_URL}/api/admin/doc-numbering",
            headers=admin_headers,
            json={"key": "rahaza_expense_claims.claim_number", "mode": "auto"},
            timeout=30
        )
        check(r.status_code == 200, "Can change mode for enforced type", f"status={r.status_code}")
    except Exception as e:
        check(False, "Change mode for enforced type", f"error={str(e)}")
    
    # Test changing mode for always-auto type (should fail with 400)
    try:
        r = requests.put(
            f"{BASE_URL}/api/admin/doc-numbering",
            headers=admin_headers,
            json={"key": "rahaza_credit_notes.cn_number", "mode": "manual"},
            timeout=30
        )
        check(
            r.status_code == 400,
            "Cannot change mode for always-auto type",
            f"status={r.status_code}"
        )
        if r.status_code == 400:
            error_msg = r.json().get("detail", "")
            check(
                "selalu bernomor otomatis" in error_msg.lower() or "always" in error_msg.lower(),
                "Error message mentions always-auto",
                f"msg={error_msg[:50]}"
            )
    except Exception as e:
        check(False, "Reject mode change for always-auto type", f"error={str(e)}")
    
    # Test changing format (should succeed even for always-auto)
    try:
        r = requests.put(
            f"{BASE_URL}/api/admin/doc-numbering",
            headers=admin_headers,
            json={"key": "rahaza_credit_notes.cn_number", "format": "CN-{YYYY}{MM}{DD}-{SEQ:3}"},
            timeout=30
        )
        check(r.status_code == 200, "Can change format for always-auto type", f"status={r.status_code}")
    except Exception as e:
        check(False, "Change format for always-auto type", f"error={str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 4. EXPENSE CLAIMS ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    section("4. EXPENSE CLAIMS ENFORCEMENT")
    
    expense_key = "rahaza_expense_claims.claim_number"
    
    # Save original mode
    original_mode = get_doc_numbering_mode(admin_headers, expense_key)
    if original_mode:
        ORIGINAL_MODES[expense_key] = original_mode
        print(f"  ℹ️  Original mode for Expense Claims: {original_mode}")
    
    # Test AUTO mode
    print("\n  --- Testing AUTO mode ---")
    set_doc_numbering_mode(admin_headers, expense_key, "auto")
    
    # Auto + number typed → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses/claims",
            headers=admin_headers,
            json={
                "claim_number": "EC-202608-9999",
                "title": "Test Claim Auto Reject",
                "items": [{"date": "2026-08-19", "category": "transport", "amount": 50000}]
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Auto mode rejects typed number",
            f"status={r.status_code}"
        )
        if r.status_code == 400:
            error_msg = r.json().get("detail", "")
            check(
                "tidak boleh diketik" in error_msg.lower() or "otomatis" in error_msg.lower(),
                "Error mentions auto mode",
                f"msg={error_msg[:80]}"
            )
    except Exception as e:
        check(False, "Auto mode rejects typed number", f"error={str(e)}")
    
    # Auto without number → 201/200 & follows format
    try:
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses/claims",
            headers=admin_headers,
            json={
                "title": "Test Claim Auto Success",
                "items": [{"date": "2026-08-19", "category": "transport", "amount": 50000}]
            },
            timeout=30
        )
        check(
            r.status_code in [200, 201],
            "Auto mode creates with auto number",
            f"status={r.status_code}"
        )
        if r.status_code in [200, 201]:
            claim_data = r.json()
            claim_number = claim_data.get("claim_number")
            claim_id = claim_data.get("id") or claim_data.get("_id")
            
            check(claim_number is not None, "Auto number is generated", f"number={claim_number}")
            if claim_number:
                # Check format EC-YYYYMM-####
                import re
                pattern = r"^EC-\d{6}-\d{4}$"
                check(
                    re.match(pattern, claim_number) is not None,
                    "Auto number follows format",
                    f"number={claim_number}"
                )
            
            if claim_id:
                CREATED_DOCS["expense_claims"].append(claim_id)
    except Exception as e:
        check(False, "Auto mode creates with auto number", f"error={str(e)}")
    
    # Test MANUAL mode
    print("\n  --- Testing MANUAL mode ---")
    set_doc_numbering_mode(admin_headers, expense_key, "manual")
    time.sleep(0.5)  # Brief pause for mode change to take effect
    
    # Manual without number → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses/claims",
            headers=admin_headers,
            json={
                "title": "Test Claim Manual No Number",
                "items": [{"date": "2026-08-19", "category": "transport", "amount": 50000}]
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Manual mode requires number",
            f"status={r.status_code}"
        )
        if r.status_code == 400:
            error_msg = r.json().get("detail", "")
            check(
                "wajib diisi" in error_msg.lower() or "required" in error_msg.lower(),
                "Error mentions required",
                f"msg={error_msg[:80]}"
            )
    except Exception as e:
        check(False, "Manual mode requires number", f"error={str(e)}")
    
    # Manual with wrong pattern → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses/claims",
            headers=admin_headers,
            json={
                "claim_number": "BEBAS/9",
                "title": "Test Claim Manual Wrong Pattern",
                "items": [{"date": "2026-08-19", "category": "transport", "amount": 50000}]
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Manual mode rejects wrong pattern",
            f"status={r.status_code}"
        )
        if r.status_code == 400:
            error_msg = r.json().get("detail", "")
            check(
                "tidak mengikuti pola" in error_msg.lower() or "pattern" in error_msg.lower(),
                "Error mentions pattern",
                f"msg={error_msg[:80]}"
            )
    except Exception as e:
        check(False, "Manual mode rejects wrong pattern", f"error={str(e)}")
    
    # Manual with correct pattern → 200/201
    test_number = f"EC-202608-{9900 + int(time.time()) % 100:04d}"
    try:
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses/claims",
            headers=admin_headers,
            json={
                "claim_number": test_number,
                "title": "Test Claim Manual Success",
                "items": [{"date": "2026-08-19", "category": "transport", "amount": 50000}]
            },
            timeout=30
        )
        check(
            r.status_code in [200, 201],
            "Manual mode accepts correct pattern",
            f"status={r.status_code}"
        )
        if r.status_code in [200, 201]:
            claim_data = r.json()
            claim_id = claim_data.get("id") or claim_data.get("_id")
            if claim_id:
                CREATED_DOCS["expense_claims"].append(claim_id)
    except Exception as e:
        check(False, "Manual mode accepts correct pattern", f"error={str(e)}")
    
    # Duplicate number → 409
    try:
        r = requests.post(
            f"{BASE_URL}/api/hr/expenses/claims",
            headers=admin_headers,
            json={
                "claim_number": test_number,
                "title": "Test Claim Duplicate",
                "items": [{"date": "2026-08-19", "category": "transport", "amount": 50000}]
            },
            timeout=30
        )
        check(
            r.status_code == 409,
            "Duplicate number rejected",
            f"status={r.status_code}"
        )
    except Exception as e:
        check(False, "Duplicate number rejected", f"error={str(e)}")
    
    # Restore to auto
    set_doc_numbering_mode(admin_headers, expense_key, "auto")
    print("  ℹ️  Restored Expense Claims to AUTO mode")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 5. KREATOR REQUESTS ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    section("5. KREATOR REQUESTS ENFORCEMENT")
    
    kreator_key = "dewi_kreator_requests.request_code"
    
    # Save original mode
    original_mode = get_doc_numbering_mode(admin_headers, kreator_key)
    if original_mode:
        ORIGINAL_MODES[kreator_key] = original_mode
        print(f"  ℹ️  Original mode for Kreator Requests: {original_mode}")
    
    # Test AUTO mode
    print("\n  --- Testing AUTO mode ---")
    set_doc_numbering_mode(admin_headers, kreator_key, "auto")
    
    # Auto + number typed → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/dewi/kreator-requests",
            headers=admin_headers,
            json={
                "request_code": "REQ-KR-260819-999",
                "kreator_name": "Test Kreator",
                "kreator_type": "tiktok_video",
                "product_concept": "Test concept"
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Kreator auto mode rejects typed number",
            f"status={r.status_code}"
        )
    except Exception as e:
        check(False, "Kreator auto mode rejects typed number", f"error={str(e)}")
    
    # Auto without number → 201/200
    try:
        r = requests.post(
            f"{BASE_URL}/api/dewi/kreator-requests",
            headers=admin_headers,
            json={
                "kreator_name": "Test Kreator Auto",
                "kreator_type": "tiktok_video",
                "product_concept": "Test concept auto"
            },
            timeout=30
        )
        check(
            r.status_code in [200, 201],
            "Kreator auto mode creates with auto number",
            f"status={r.status_code}"
        )
        if r.status_code in [200, 201]:
            req_data = r.json()
            request_code = req_data.get("request_code")
            req_id = req_data.get("id") or req_data.get("_id")
            
            check(request_code is not None, "Kreator auto number generated", f"code={request_code}")
            if request_code:
                # Check format REQ-KR-YYMMDD-###
                import re
                pattern = r"^REQ-KR-\d{6}-\d{3}$"
                check(
                    re.match(pattern, request_code) is not None,
                    "Kreator auto number follows format",
                    f"code={request_code}"
                )
            
            if req_id:
                CREATED_DOCS["kreator_requests"].append(req_id)
    except Exception as e:
        check(False, "Kreator auto mode creates with auto number", f"error={str(e)}")
    
    # Test MANUAL mode
    print("\n  --- Testing MANUAL mode ---")
    set_doc_numbering_mode(admin_headers, kreator_key, "manual")
    time.sleep(0.5)
    
    # Manual without number → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/dewi/kreator-requests",
            headers=admin_headers,
            json={
                "kreator_name": "Test Kreator Manual No Number",
                "kreator_type": "tiktok_video",
                "product_concept": "Test concept"
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Kreator manual mode requires number",
            f"status={r.status_code}"
        )
    except Exception as e:
        check(False, "Kreator manual mode requires number", f"error={str(e)}")
    
    # Manual with correct pattern → 200/201
    test_kreator_code = f"REQ-KR-260819-{900 + int(time.time()) % 100:03d}"
    try:
        r = requests.post(
            f"{BASE_URL}/api/dewi/kreator-requests",
            headers=admin_headers,
            json={
                "request_code": test_kreator_code,
                "kreator_name": "Test Kreator Manual Success",
                "kreator_type": "tiktok_video",
                "product_concept": "Test concept manual"
            },
            timeout=30
        )
        check(
            r.status_code in [200, 201],
            "Kreator manual mode accepts correct pattern",
            f"status={r.status_code}"
        )
        if r.status_code in [200, 201]:
            req_data = r.json()
            req_id = req_data.get("id") or req_data.get("_id")
            if req_id:
                CREATED_DOCS["kreator_requests"].append(req_id)
    except Exception as e:
        check(False, "Kreator manual mode accepts correct pattern", f"error={str(e)}")
    
    # Restore to auto
    set_doc_numbering_mode(admin_headers, kreator_key, "auto")
    print("  ℹ️  Restored Kreator Requests to AUTO mode")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 6. ACCESSORY PURCHASE REQUESTS ENFORCEMENT
    # ═══════════════════════════════════════════════════════════════════════════
    section("6. ACCESSORY PURCHASE REQUESTS ENFORCEMENT")
    
    acc_pr_key = "acc_purchase_requests.pr_number"
    
    # Save original mode
    original_mode = get_doc_numbering_mode(admin_headers, acc_pr_key)
    if original_mode:
        ORIGINAL_MODES[acc_pr_key] = original_mode
        print(f"  ℹ️  Original mode for Acc Purchase Requests: {original_mode}")
    
    # Test AUTO mode
    print("\n  --- Testing AUTO mode ---")
    set_doc_numbering_mode(admin_headers, acc_pr_key, "auto")
    
    # Auto + number typed → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/acc/purchase-requests",
            headers=admin_headers,
            json={
                "pr_number": "ACC-PR-9999",
                "items": [{"material_code": "TEST-001", "qty": 10}]
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Acc PR auto mode rejects typed number",
            f"status={r.status_code}"
        )
    except Exception as e:
        check(False, "Acc PR auto mode rejects typed number", f"error={str(e)}")
    
    # Auto without number → 201/200
    try:
        r = requests.post(
            f"{BASE_URL}/api/acc/purchase-requests",
            headers=admin_headers,
            json={
                "items": [{"material_code": "TEST-001", "qty": 10}]
            },
            timeout=30
        )
        check(
            r.status_code in [200, 201],
            "Acc PR auto mode creates with auto number",
            f"status={r.status_code}"
        )
        if r.status_code in [200, 201]:
            pr_data = r.json()
            pr_number = pr_data.get("pr_number")
            pr_id = pr_data.get("id") or pr_data.get("_id")
            
            check(pr_number is not None, "Acc PR auto number generated", f"number={pr_number}")
            if pr_number:
                # Check format ACC-PR-####
                import re
                pattern = r"^ACC-PR-\d{4}$"
                check(
                    re.match(pattern, pr_number) is not None,
                    "Acc PR auto number follows format",
                    f"number={pr_number}"
                )
            
            if pr_id:
                CREATED_DOCS["acc_purchase_requests"].append(pr_id)
    except Exception as e:
        check(False, "Acc PR auto mode creates with auto number", f"error={str(e)}")
    
    # Test MANUAL mode
    print("\n  --- Testing MANUAL mode ---")
    set_doc_numbering_mode(admin_headers, acc_pr_key, "manual")
    time.sleep(0.5)
    
    # Manual without number → 400
    try:
        r = requests.post(
            f"{BASE_URL}/api/acc/purchase-requests",
            headers=admin_headers,
            json={
                "items": [{"material_code": "TEST-001", "qty": 10}]
            },
            timeout=30
        )
        check(
            r.status_code == 400,
            "Acc PR manual mode requires number",
            f"status={r.status_code}"
        )
    except Exception as e:
        check(False, "Acc PR manual mode requires number", f"error={str(e)}")
    
    # Manual with correct pattern → 200/201
    test_pr_number = f"ACC-PR-{9900 + int(time.time()) % 100:04d}"
    try:
        r = requests.post(
            f"{BASE_URL}/api/acc/purchase-requests",
            headers=admin_headers,
            json={
                "pr_number": test_pr_number,
                "items": [{"material_code": "TEST-001", "qty": 10}]
            },
            timeout=30
        )
        check(
            r.status_code in [200, 201],
            "Acc PR manual mode accepts correct pattern",
            f"status={r.status_code}"
        )
        if r.status_code in [200, 201]:
            pr_data = r.json()
            pr_id = pr_data.get("id") or pr_data.get("_id")
            if pr_id:
                CREATED_DOCS["acc_purchase_requests"].append(pr_id)
    except Exception as e:
        check(False, "Acc PR manual mode accepts correct pattern", f"error={str(e)}")
    
    # Restore to auto
    set_doc_numbering_mode(admin_headers, acc_pr_key, "auto")
    print("  ℹ️  Restored Acc Purchase Requests to AUTO mode")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 7. LEGACY LOAN ENDPOINT (HTTP 410)
    # ═══════════════════════════════════════════════════════════════════════════
    section("7. LEGACY LOAN ENDPOINT (HTTP 410)")
    
    try:
        r = requests.post(
            f"{BASE_URL}/api/rahaza/hr/employee-loans/disburse",
            headers=admin_headers,
            json={"employee_id": "test", "amount": 1000000},
            timeout=30
        )
        check(
            r.status_code == 410,
            "Legacy loan endpoint returns 410",
            f"status={r.status_code}"
        )
        if r.status_code == 410:
            error_msg = r.json().get("detail", "")
            check(
                ("kasbon" in error_msg.lower() and "pinjaman" in error_msg.lower()) or
                "archived" in error_msg.lower() or "deprecated" in error_msg.lower(),
                "Error message mentions Kasbon & Pinjaman or archived",
                f"msg={error_msg[:100]}"
            )
    except Exception as e:
        check(False, "Legacy loan endpoint returns 410", f"error={str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 8. FABRIC ROLLS SEEDER
    # ═══════════════════════════════════════════════════════════════════════════
    section("8. FABRIC ROLLS SEEDER")
    
    try:
        r = requests.get(
            f"{BASE_URL}/api/wms/fabric-rolls?limit=200",
            headers=admin_headers,
            timeout=30
        )
        check(r.status_code == 200, "GET /api/wms/fabric-rolls returns 200", f"status={r.status_code}")
        
        if r.status_code == 200:
            data = r.json()
            rolls = data.get("items", []) or data.get("rolls", [])
            
            # Find DEMO rolls
            demo_rolls = [r for r in rolls if "DEMO" in str(r.get("notes", "")).upper()]
            check(
                len(demo_rolls) >= 4,
                "At least 4 DEMO rolls exist",
                f"found={len(demo_rolls)}"
            )
            
            # Check pattern RL-YYYYMM-####
            import re
            pattern = r"^RL-\d{6}-\d{4}$"
            correct_pattern_count = 0
            for roll in demo_rolls[:4]:  # Check first 4
                roll_no = roll.get("roll_no", "")
                if re.match(pattern, roll_no):
                    correct_pattern_count += 1
            
            check(
                correct_pattern_count >= 4,
                "DEMO rolls follow RL-YYYYMM-#### pattern",
                f"correct={correct_pattern_count}/4"
            )
            
            # Ensure NOT DEMO-RL-000x pattern
            old_pattern_count = sum(1 for r in demo_rolls if r.get("roll_no", "").startswith("DEMO-RL-"))
            check(
                old_pattern_count == 0,
                "No rolls with old DEMO-RL-000x pattern",
                f"old_pattern={old_pattern_count}"
            )
    
    except Exception as e:
        check(False, "GET /api/wms/fabric-rolls", f"error={str(e)}")
    
    # ═══════════════════════════════════════════════════════════════════════════
    # CLEANUP
    # ═══════════════════════════════════════════════════════════════════════════
    cleanup_test_docs(admin_headers)
    restore_modes(admin_headers)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ═══════════════════════════════════════════════════════════════════════════
    print("\n" + "=" * 78)
    print("TEST SUMMARY")
    print("=" * 78)
    print(f"  ✅ PASSED: {PASS_COUNT}")
    print(f"  ❌ FAILED: {FAIL_COUNT}")
    
    if FAILED_TESTS:
        print("\nFailed tests:")
        for test in FAILED_TESTS:
            print(f"  - {test}")
    
    return 0 if FAIL_COUNT == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
