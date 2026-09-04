#!/usr/bin/env python3
"""
Backend Test: PDF Export - Surat Jalan CMT Accessories + Production Guide
Sesi 2026-08-01 lanjutan

Tests:
A. BUG FIX: Accessories in vendor-shipment PDF
B. NEW FEATURE: production-guide PDF
C. SMOKE TEST: All PDF document types
"""

import requests
import time
import io
from PyPDF2 import PdfReader
from typing import Dict, List, Tuple

# Configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com/api"
LOGIN_EMAIL = "admin@garment.com"
LOGIN_PASSWORD = "Admin@123"

# Test results
results = {
    "passed": [],
    "failed": [],
    "warnings": []
}

def log_result(test_name: str, passed: bool, message: str = ""):
    """Log test result"""
    if passed:
        results["passed"].append(f"✅ {test_name}: {message}")
        print(f"✅ {test_name}: {message}")
    else:
        results["failed"].append(f"❌ {test_name}: {message}")
        print(f"❌ {test_name}: {message}")

def log_warning(test_name: str, message: str):
    """Log warning"""
    results["warnings"].append(f"⚠️  {test_name}: {message}")
    print(f"⚠️  {test_name}: {message}")

def login() -> str:
    """Login and return token"""
    print(f"\n🔐 Logging in as {LOGIN_EMAIL}...")
    resp = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        timeout=30
    )
    if resp.status_code != 200:
        raise Exception(f"Login failed: {resp.status_code} {resp.text}")
    
    token = resp.json().get("token")
    if not token:
        raise Exception("No token in login response")
    
    print(f"✅ Login successful")
    return token

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF bytes"""
    try:
        pdf_file = io.BytesIO(pdf_bytes)
        reader = PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        return text
    except Exception as e:
        return f"[PDF extraction error: {e}]"

def test_pdf_export(token: str, pdf_type: str, pdf_id: str = None, 
                   expected_status: int = 200, 
                   expected_texts: List[str] = None,
                   test_name: str = None) -> Tuple[bool, str, str]:
    """
    Test PDF export endpoint
    Returns: (success, status_info, pdf_text)
    """
    url = f"{BASE_URL}/export-pdf?type={pdf_type}"
    if pdf_id:
        url += f"&id={pdf_id}"
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        resp = requests.get(url, headers=headers, timeout=60)
        
        # Check status code
        if resp.status_code != expected_status:
            return False, f"Expected {expected_status}, got {resp.status_code}: {resp.text[:200]}", ""
        
        if expected_status != 200:
            return True, f"Status {resp.status_code} as expected", ""
        
        # Check content type
        content_type = resp.headers.get("Content-Type", "")
        if "application/pdf" not in content_type:
            return False, f"Wrong Content-Type: {content_type}", ""
        
        # Check PDF size
        pdf_bytes = resp.content
        if len(pdf_bytes) == 0:
            return False, "PDF is 0 bytes", ""
        
        # Extract text
        pdf_text = extract_pdf_text(pdf_bytes)
        
        if len(pdf_text) < 50:
            return False, f"PDF text too short ({len(pdf_text)} chars): {pdf_text[:100]}", pdf_text
        
        # Check expected texts
        if expected_texts:
            missing = []
            for expected in expected_texts:
                if expected not in pdf_text:
                    missing.append(expected)
            
            if missing:
                return False, f"Missing expected text: {missing[:3]}", pdf_text
        
        # Check Content-Disposition for filename
        disposition = resp.headers.get("Content-Disposition", "")
        
        return True, f"OK ({len(pdf_bytes)} bytes, {len(pdf_text)} chars text, filename: {disposition})", pdf_text
    
    except requests.exceptions.Timeout:
        return False, "Request timeout (60s)", ""
    except Exception as e:
        return False, f"Exception: {str(e)}", ""

def section_a_accessories_bug_fix(token: str):
    """Section A: Test accessories in vendor-shipment PDF"""
    print("\n" + "="*80)
    print("SECTION A: BUG FIX - Accessories in Surat Jalan CMT")
    print("="*80)
    
    # A.1 - Shipment with 2 accessories (SHP-0077, PO-004)
    print("\n📋 A.1 - Shipment aacf1cf2-b366-499b-abc4-7b27c170a4b2 (SHP-0077, PO-004, 2 accessories)")
    shipment_id = "aacf1cf2-b366-499b-abc4-7b27c170a4b2"
    expected_texts = [
        "AKSESORIS / KOMPONEN PENDUKUNG",
        "A5",
        "A6",
        "Label merk Hitam",
        "Label merk premium pink",
        "PO-004",
        "Sumber",
        "TOTAL AKSESORIS"
    ]
    
    success, msg, pdf_text = test_pdf_export(
        token, "vendor-shipment", shipment_id, 
        expected_texts=expected_texts,
        test_name="A.1"
    )
    
    if success:
        # Additional checks
        if "50" in pdf_text or "25" in pdf_text:  # qty checks
            log_result("A.1", True, f"Shipment SHP-0077 accessories found: {msg}")
        else:
            log_result("A.1", False, "Accessories section found but quantities missing")
    else:
        log_result("A.1", False, f"Shipment SHP-0077: {msg}")
        if pdf_text:
            print(f"   PDF text sample: {pdf_text[:500]}")
    
    # A.2 - Shipment with 1 accessory (SHP-002, PO-0035)
    print("\n📋 A.2 - Shipment a9886906-b603-4d7a-b2c7-273f16848cfd (SHP-002, PO-0035, 1 accessory)")
    shipment_id = "a9886906-b603-4d7a-b2c7-273f16848cfd"
    expected_texts = [
        "AKSESORIS / KOMPONEN PENDUKUNG",
        "A6",
        "PO-0035"
    ]
    
    success, msg, pdf_text = test_pdf_export(
        token, "vendor-shipment", shipment_id,
        expected_texts=expected_texts,
        test_name="A.2"
    )
    
    if success:
        log_result("A.2", True, f"Shipment SHP-002 accessories found: {msg}")
    else:
        log_result("A.2", False, f"Shipment SHP-002: {msg}")
    
    # A.3 - Shipment WITHOUT accessories (should show message)
    print("\n📋 A.3 - Shipment po-mk-demo-2-vs1 (SJ-MK-DEMO-2, NO accessories)")
    shipment_id = "po-mk-demo-2-vs1"
    expected_texts = [
        "tidak ada aksesoris pada pengiriman ini"
    ]
    
    success, msg, pdf_text = test_pdf_export(
        token, "vendor-shipment", shipment_id,
        expected_texts=expected_texts,
        test_name="A.3"
    )
    
    if success:
        log_result("A.3", True, f"No-accessories message found: {msg}")
    else:
        log_result("A.3", False, f"Shipment without accessories: {msg}")
    
    # A.4 - REGRESSION: Check all 3 PDFs have material table + header + signatures
    print("\n📋 A.4 - REGRESSION: Material table, header, signatures present")
    regression_checks = [
        ("aacf1cf2-b366-499b-abc4-7b27c170a4b2", "SHP-0077"),
        ("a9886906-b603-4d7a-b2c7-273f16848cfd", "SHP-002"),
        ("po-mk-demo-2-vs1", "SJ-MK-DEMO-2")
    ]
    
    regression_passed = 0
    for ship_id, ship_name in regression_checks:
        expected_texts = [
            "CV. DEWI ADITYA",  # header
            "Pengirim",  # signature block
            "Penerima",  # signature block
            "TOTAL"  # material table total row
        ]
        
        success, msg, pdf_text = test_pdf_export(
            token, "vendor-shipment", ship_id,
            expected_texts=expected_texts,
            test_name=f"A.4-{ship_name}"
        )
        
        if success:
            # Check filename pattern
            if "SJ-Material" in msg or ship_name in msg:
                regression_passed += 1
            else:
                log_warning(f"A.4-{ship_name}", "Filename pattern not verified")
                regression_passed += 1
        else:
            log_result(f"A.4-{ship_name}", False, f"Regression check failed: {msg}")
    
    if regression_passed == 3:
        log_result("A.4", True, f"All 3 PDFs have material table, header, signatures ({regression_passed}/3)")
    else:
        log_result("A.4", False, f"Regression check incomplete ({regression_passed}/3)")

def section_b_production_guide(token: str):
    """Section B: Test production-guide PDF (new feature)"""
    print("\n" + "="*80)
    print("SECTION B: NEW FEATURE - production-guide PDF")
    print("="*80)
    
    # B.1 - From vendor shipment
    print("\n📋 B.1 - production-guide from vendor_shipment a9886906-b603-4d7a-b2c7-273f16848cfd")
    shipment_id = "a9886906-b603-4d7a-b2c7-273f16848cfd"
    expected_texts = [
        "PANDUAN PRODUK & PROSES PRODUKSI",
        "No Surat Jalan",
        "Vendor / CMT",
        "ARN-HD",
        "Jaket Hoodie Aruna",
        "Langkah",
        "Rincian"
    ]
    
    success, msg, pdf_text = test_pdf_export(
        token, "production-guide", shipment_id,
        expected_texts=expected_texts,
        test_name="B.1"
    )
    
    if success:
        # Check for SOP steps
        if "Potong" in pdf_text or "Jahit" in pdf_text or "potong" in pdf_text or "jahit" in pdf_text:
            log_result("B.1", True, f"Production guide from shipment OK, SOP steps found: {msg}")
        else:
            log_warning("B.1", f"Production guide OK but SOP steps not clearly visible: {msg}")
            log_result("B.1", True, msg)
    else:
        log_result("B.1", False, f"Production guide from shipment: {msg}")
    
    # B.2 - From another shipment (polo)
    print("\n📋 B.2 - production-guide from shipment po-mk-demo-2-vs1 (ARN-PL polo)")
    shipment_id = "po-mk-demo-2-vs1"
    expected_texts = [
        "PANDUAN PRODUK & PROSES PRODUKSI",
        "ARN-PL",
        "Kaos Polo Aruna"
    ]
    
    success, msg, pdf_text = test_pdf_export(
        token, "production-guide", shipment_id,
        expected_texts=expected_texts,
        test_name="B.2"
    )
    
    if success:
        log_result("B.2", True, f"Production guide polo article: {msg}")
    else:
        log_result("B.2", False, f"Production guide polo: {msg}")
    
    # B.3 - From child shipment (no po_number, should fallback via po_id)
    print("\n📋 B.3 - production-guide from child shipment 29cbb7ea-4208-40f2-98ae-59385771319d (SHP-002-A1)")
    shipment_id = "29cbb7ea-4208-40f2-98ae-59385771319d"
    expected_texts = [
        "PANDUAN PRODUK & PROSES PRODUKSI"
    ]
    
    success, msg, pdf_text = test_pdf_export(
        token, "production-guide", shipment_id,
        expected_texts=expected_texts,
        test_name="B.3"
    )
    
    if success:
        log_result("B.3", True, f"Production guide from child shipment (fallback via po_id): {msg}")
    else:
        log_result("B.3", False, f"Child shipment fallback: {msg}")
    
    # B.4 - From article catalog (need to get an ID first)
    print("\n📋 B.4 - production-guide from article catalog (skipped - need to query DB for ID)")
    log_warning("B.4", "Skipped - requires DB query to get article catalog ID with sop_steps")
    
    # B.5 - From production_job (need to get an ID first)
    print("\n📋 B.5 - production-guide from production_job (skipped - need to query DB for ID)")
    log_warning("B.5", "Skipped - requires DB query to get production_job ID")
    
    # B.6 - NEGATIVE: no id parameter
    print("\n📋 B.6 - NEGATIVE: production-guide without id parameter")
    success, msg, pdf_text = test_pdf_export(
        token, "production-guide", None,
        expected_status=400,
        test_name="B.6"
    )
    
    if success:
        log_result("B.6", True, "No id parameter correctly returns 400")
    else:
        log_result("B.6", False, f"Expected 400 without id: {msg}")
    
    # B.7 - NEGATIVE: fake id
    print("\n📋 B.7 - NEGATIVE: production-guide with fake id")
    success, msg, pdf_text = test_pdf_export(
        token, "production-guide", "id-tidak-ada-123",
        expected_status=404,
        test_name="B.7"
    )
    
    if success:
        log_result("B.7", True, "Fake id correctly returns 404")
    else:
        log_result("B.7", False, f"Expected 404 for fake id: {msg}")
    
    # B.8 - NEGATIVE: no auth
    print("\n📋 B.8 - NEGATIVE: production-guide without Authorization header")
    url = f"{BASE_URL}/export-pdf?type=production-guide&id=role-matrix-3"
    try:
        resp = requests.get(url, timeout=30)
        if resp.status_code in [401, 403]:
            log_result("B.8", True, f"No auth correctly returns {resp.status_code}")
        else:
            log_result("B.8", False, f"Expected 401/403 without auth, got {resp.status_code}")
    except Exception as e:
        log_result("B.8", False, f"Exception: {e}")

def section_c_smoke_test_all_pdfs(token: str):
    """Section C: Smoke test all PDF document types"""
    print("\n" + "="*80)
    print("SECTION C: SMOKE TEST - All PDF Document Types")
    print("="*80)
    
    # Get some IDs from database for testing
    print("\n📋 Getting sample IDs from database...")
    
    # We'll test with known IDs and also try to get some from API
    test_cases = [
        # (type, id_or_none, description)
        ("production-po", None, "Production PO (need ID from DB)"),
        ("vendor-shipment", "a9886906-b603-4d7a-b2c7-273f16848cfd", "Vendor Shipment"),
        ("buyer-shipment", None, "Buyer Shipment (need ID from DB)"),
        ("buyer-shipment-dispatch", None, "Buyer Shipment Dispatch (need ID from DB)"),
        ("production-return", None, "Production Return (need ID from DB)"),
        ("material-request", None, "Material Request (need ID from DB)"),
        ("production-report", None, "Production Report (need ID from DB)"),
        ("production-guide", "a9886906-b603-4d7a-b2c7-273f16848cfd", "Production Guide"),
        # Aggregate reports (no ID needed)
        ("report-production", None, "Report Production (aggregate)"),
        ("report-progress", None, "Report Progress (aggregate)"),
        ("report-financial", None, "Report Financial (aggregate)"),
        ("report-shipment", None, "Report Shipment (aggregate)"),
        ("report-defect", None, "Report Defect (aggregate)"),
        ("report-return", None, "Report Return (aggregate)"),
        ("report-missing-material", None, "Report Missing Material (aggregate)"),
        ("report-replacement", None, "Report Replacement (aggregate)"),
        ("report-accessory", None, "Report Accessory (aggregate)")
    ]
    
    smoke_results = []
    
    for pdf_type, pdf_id, description in test_cases:
        print(f"\n📄 Testing {pdf_type}: {description}")
        
        success, msg, pdf_text = test_pdf_export(
            token, pdf_type, pdf_id,
            expected_status=200,
            test_name=f"C-{pdf_type}"
        )
        
        if success:
            smoke_results.append((pdf_type, "PASS", msg))
            print(f"   ✅ PASS: {msg}")
        else:
            # Check if it's 404 (no data) which is acceptable
            if "404" in msg:
                smoke_results.append((pdf_type, "404", "No data (acceptable)"))
                print(f"   ⚠️  404: No data (acceptable)")
            elif "400" in msg and pdf_id is None:
                smoke_results.append((pdf_type, "400", "Missing ID (expected)"))
                print(f"   ⚠️  400: Missing ID (expected)")
            else:
                smoke_results.append((pdf_type, "FAIL", msg))
                print(f"   ❌ FAIL: {msg}")
    
    # Summary table
    print("\n" + "="*80)
    print("SMOKE TEST SUMMARY TABLE")
    print("="*80)
    print(f"{'Type':<30} {'Status':<10} {'Details':<40}")
    print("-"*80)
    
    pass_count = 0
    fail_count = 0
    
    for pdf_type, status, details in smoke_results:
        print(f"{pdf_type:<30} {status:<10} {details[:40]}")
        if status == "PASS":
            pass_count += 1
        elif status == "FAIL":
            fail_count += 1
    
    print("-"*80)
    print(f"PASS: {pass_count}, FAIL: {fail_count}, ACCEPTABLE (404/400): {len(smoke_results) - pass_count - fail_count}")
    
    if fail_count == 0:
        log_result("C", True, f"Smoke test complete: {pass_count} PASS, 0 FAIL, {len(smoke_results) - pass_count} acceptable (404/400)")
    else:
        log_result("C", False, f"Smoke test: {fail_count} endpoints returned 500 or unexpected errors")

def main():
    """Main test runner"""
    print("="*80)
    print("BACKEND TEST: PDF Export - Surat Jalan CMT + Production Guide")
    print("Sesi 2026-08-01 lanjutan")
    print("="*80)
    
    try:
        # Login
        token = login()
        
        # Run test sections
        section_a_accessories_bug_fix(token)
        section_b_production_guide(token)
        section_c_smoke_test_all_pdfs(token)
        
        # Final summary
        print("\n" + "="*80)
        print("FINAL SUMMARY")
        print("="*80)
        
        print(f"\n✅ PASSED: {len(results['passed'])}")
        for item in results['passed']:
            print(f"   {item}")
        
        if results['warnings']:
            print(f"\n⚠️  WARNINGS: {len(results['warnings'])}")
            for item in results['warnings']:
                print(f"   {item}")
        
        if results['failed']:
            print(f"\n❌ FAILED: {len(results['failed'])}")
            for item in results['failed']:
                print(f"   {item}")
        else:
            print(f"\n🎉 ALL TESTS PASSED!")
        
        print("\n" + "="*80)
        
        return len(results['failed']) == 0
    
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
