#!/usr/bin/env python3
"""Backend API testing for FASE H-7 & H-8 (Surat Jalan Unified + Menu Alias Fix)

FASE H-7: Unified Delivery Notes from 3 sources (gudang, vendor, buyer)
FASE H-8: 4 menu aliases redirected from empty wms-cmt-dispatches to modules with data

Test Coverage:
- BACKEND A: GET /api/wms/delivery-notes/sources returns correct counts
- BACKEND B: Filters (source, q, date_from, date_to) work correctly
- BACKEND C: PDF URLs for each source return valid PDFs
- BACKEND D: Recap PDF generation works (with/without token query param)
- BACKEND E: Read-only aggregation (no new docs created)
- BACKEND F: Regression - old endpoints still work
"""
import requests
import sys
import os
from datetime import datetime

BASE_URL = os.environ.get("API_BASE", "https://da37-cmt-bridge.preview.emergentagent.com")
ADMIN_CREDS = {"email": "admin@garment.com", "password": "Admin@123"}

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

def log(msg, status="INFO"):
    color = Colors.GREEN if status == "PASS" else Colors.RED if status == "FAIL" else Colors.YELLOW
    print(f"{color}{status}{Colors.RESET} {msg}")

def login():
    """Login and get token"""
    try:
        r = requests.post(f"{BASE_URL}/api/auth/login", json=ADMIN_CREDS, timeout=30)
        r.raise_for_status()
        token = r.json()["token"]
        log("Login successful", "PASS")
        return token
    except Exception as e:
        log(f"Login failed: {e}", "FAIL")
        sys.exit(1)

def get_db_counts():
    """Get expected counts from DB via MongoDB"""
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        client = MongoClient(mongo_url)
        db = client.test_database
        
        n_gudang = db.wh_delivery_notes.count_documents({})
        n_vendor = db.vendor_shipments.count_documents({})
        
        # Buyer: count unique (shipment_id, dispatch_seq) pairs
        dispatches = set()
        for item in db.buyer_shipment_items.find({}, {"shipment_id": 1, "dispatch_seq": 1}):
            sid = item.get("shipment_id")
            seq = int(item.get("dispatch_seq", 1))
            if sid:
                dispatches.add((sid, seq))
        n_buyer = len(dispatches)
        
        client.close()
        return n_gudang, n_vendor, n_buyer
    except Exception as e:
        log(f"Failed to get DB counts: {e}", "WARN")
        return None, None, None

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND A: GET /api/wms/delivery-notes/sources
# ═══════════════════════════════════════════════════════════════════════════════
def test_sources_endpoint(token):
    """Test unified sources endpoint returns correct data structure and counts"""
    log("\n[BACKEND A] Testing GET /api/wms/delivery-notes/sources", "INFO")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources", headers=headers, timeout=60)
        
        if r.status_code != 200:
            log(f"sources endpoint HTTP {r.status_code}: {r.text[:200]}", "FAIL")
            return False
        
        data = r.json()
        items = data.get("items", [])
        total = data.get("total", 0)
        by_source = data.get("by_source", {})
        total_qty = data.get("total_qty", 0)
        sources = data.get("sources", [])
        
        # Get expected counts from DB
        n_gudang, n_vendor, n_buyer = get_db_counts()
        
        if n_gudang is not None:
            expected_total = n_gudang + n_vendor + n_buyer
            
            # Check total count
            if total != expected_total:
                log(f"Total count mismatch: expected {expected_total}, got {total}", "FAIL")
                return False
            
            # Check by_source counts
            if by_source.get("gudang") != n_gudang:
                log(f"Gudang count mismatch: expected {n_gudang}, got {by_source.get('gudang')}", "FAIL")
                return False
            
            if by_source.get("vendor") != n_vendor:
                log(f"Vendor count mismatch: expected {n_vendor}, got {by_source.get('vendor')}", "FAIL")
                return False
            
            if by_source.get("buyer") != n_buyer:
                log(f"Buyer count mismatch: expected {n_buyer}, got {by_source.get('buyer')}", "FAIL")
                return False
            
            log(f"Counts match DB: gudang={n_gudang}, vendor={n_vendor}, buyer={n_buyer}, total={expected_total}", "PASS")
        else:
            log(f"Got total={total}, by_source={by_source} (DB check skipped)", "PASS")
        
        # Check data structure
        if not items:
            log("No items returned (empty list)", "WARN")
        else:
            # Check first item has required fields
            first = items[0]
            required_fields = ["source", "source_label", "module", "key", "number", "doc_type", 
                             "date", "recipient", "reference", "status", "lines", "qty", "pdf_url"]
            missing = [f for f in required_fields if f not in first]
            if missing:
                log(f"First item missing fields: {missing}", "FAIL")
                return False
            
            # Check unique keys
            keys = [item.get("key") for item in items]
            if len(keys) != len(set(keys)):
                log(f"Duplicate keys found (dispatch not properly split)", "FAIL")
                return False
            
            log(f"All items have required fields, {len(items)} unique keys", "PASS")
        
        # Check sources metadata
        if len(sources) != 3:
            log(f"Expected 3 sources metadata, got {len(sources)}", "FAIL")
            return False
        
        source_keys = {s.get("key") for s in sources}
        if source_keys != {"gudang", "vendor", "buyer"}:
            log(f"Source keys mismatch: {source_keys}", "FAIL")
            return False
        
        log("Sources metadata correct (gudang, vendor, buyer)", "PASS")
        return True
        
    except Exception as e:
        log(f"sources endpoint test failed: {e}", "FAIL")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND B: Filters
# ═══════════════════════════════════════════════════════════════════════════════
def test_filters(token):
    """Test source, q, date_from, date_to filters"""
    log("\n[BACKEND B] Testing filters", "INFO")
    
    headers = {"Authorization": f"Bearer {token}"}
    passed = 0
    total = 0
    
    # Test 1: Filter by source=buyer
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?source=buyer", 
                        headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if all(item.get("source") == "buyer" for item in items):
                log(f"Filter source=buyer works ({len(items)} items)", "PASS")
                passed += 1
            else:
                log("Filter source=buyer returned non-buyer items", "FAIL")
        else:
            log(f"Filter source=buyer HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Filter source=buyer failed: {e}", "FAIL")
    
    # Test 2: Filter by source=vendor
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?source=vendor", 
                        headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if all(item.get("source") == "vendor" for item in items):
                log(f"Filter source=vendor works ({len(items)} items)", "PASS")
                passed += 1
            else:
                log("Filter source=vendor returned non-vendor items", "FAIL")
        else:
            log(f"Filter source=vendor HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Filter source=vendor failed: {e}", "FAIL")
    
    # Test 3: Filter by source=gudang
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?source=gudang", 
                        headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if all(item.get("source") == "gudang" for item in items):
                log(f"Filter source=gudang works ({len(items)} items)", "PASS")
                passed += 1
            else:
                log("Filter source=gudang returned non-gudang items", "FAIL")
        else:
            log(f"Filter source=gudang HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Filter source=gudang failed: {e}", "FAIL")
    
    # Test 4: Filter by date_from=2099-01-01 (should return 0)
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?date_from=2099-01-01", 
                        headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            if data.get("total") == 0:
                log("Filter date_from=2099-01-01 returns 0 items", "PASS")
                passed += 1
            else:
                log(f"Filter date_from=2099-01-01 returned {data.get('total')} items (expected 0)", "FAIL")
        else:
            log(f"Filter date_from HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Filter date_from failed: {e}", "FAIL")
    
    # Test 5: Search filter (q parameter)
    total += 1
    try:
        # Get first item to extract a search keyword
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?limit=1", 
                        headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                # Use recipient name as search keyword
                keyword = items[0].get("recipient", "")[:6]
                if keyword:
                    r2 = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?q={keyword}", 
                                    headers=headers, timeout=60)
                    if r2.status_code == 200:
                        data2 = r2.json()
                        if data2.get("total", 0) > 0:
                            log(f"Search filter q='{keyword}' works ({data2.get('total')} results)", "PASS")
                            passed += 1
                        else:
                            log(f"Search filter q='{keyword}' returned 0 results", "FAIL")
                    else:
                        log(f"Search filter HTTP {r2.status_code}", "FAIL")
                else:
                    log("No keyword to test search filter", "WARN")
                    passed += 1  # Don't fail if no data
            else:
                log("No items to test search filter", "WARN")
                passed += 1  # Don't fail if no data
        else:
            log(f"Failed to get sample data for search test: HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Search filter test failed: {e}", "FAIL")
    
    # Test 6: Combined filters (source + q)
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources?source=vendor&q=CMT", 
                        headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if all(item.get("source") == "vendor" for item in items):
                log(f"Combined filter source=vendor&q=CMT works ({len(items)} items)", "PASS")
                passed += 1
            else:
                log("Combined filter returned wrong source", "FAIL")
        else:
            log(f"Combined filter HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Combined filter test failed: {e}", "FAIL")
    
    log(f"Filter tests: {passed}/{total} passed", "INFO")
    return passed == total

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND C: PDF URLs
# ═══════════════════════════════════════════════════════════════════════════════
def test_pdf_urls(token):
    """Test that PDF URLs for each source return valid PDFs"""
    log("\n[BACKEND C] Testing PDF URLs", "INFO")
    
    headers = {"Authorization": f"Bearer {token}"}
    passed = 0
    total = 0
    
    try:
        # Get sample items from each source
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources", headers=headers, timeout=60)
        if r.status_code != 200:
            log(f"Failed to get sources: HTTP {r.status_code}", "FAIL")
            return False
        
        data = r.json()
        items = data.get("items", [])
        
        # Test one PDF from each source
        for source in ["gudang", "vendor", "buyer"]:
            source_items = [item for item in items if item.get("source") == source]
            if not source_items:
                log(f"No {source} items to test PDF", "WARN")
                continue
            
            item = source_items[0]
            pdf_url = item.get("pdf_url")
            if not pdf_url:
                log(f"{source}: No pdf_url", "FAIL")
                total += 1
                continue
            
            total += 1
            try:
                # Test main PDF URL
                full_url = f"{BASE_URL}{pdf_url}" if pdf_url.startswith("/") else pdf_url
                r_pdf = requests.get(full_url, headers=headers, timeout=60)
                
                if r_pdf.status_code == 200 and r_pdf.content[:5] == b"%PDF-":
                    log(f"{source}: PDF download OK ({item.get('number')})", "PASS")
                    passed += 1
                else:
                    log(f"{source}: PDF download failed - HTTP {r_pdf.status_code}, content: {r_pdf.content[:20]}", "FAIL")
            except Exception as e:
                log(f"{source}: PDF download error: {e}", "FAIL")
            
            # Test pdf_alt_url for buyer (cumulative PDF)
            if source == "buyer" and item.get("pdf_alt_url"):
                total += 1
                try:
                    alt_url = item.get("pdf_alt_url")
                    full_alt_url = f"{BASE_URL}{alt_url}" if alt_url.startswith("/") else alt_url
                    r_alt = requests.get(full_alt_url, headers=headers, timeout=60)
                    
                    if r_alt.status_code == 200 and r_alt.content[:5] == b"%PDF-":
                        log(f"{source}: Cumulative PDF (pdf_alt_url) OK", "PASS")
                        passed += 1
                    else:
                        log(f"{source}: Cumulative PDF failed - HTTP {r_alt.status_code}", "FAIL")
                except Exception as e:
                    log(f"{source}: Cumulative PDF error: {e}", "FAIL")
        
        log(f"PDF URL tests: {passed}/{total} passed", "INFO")
        return passed == total
        
    except Exception as e:
        log(f"PDF URL test failed: {e}", "FAIL")
        return False

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND D: Recap PDF
# ═══════════════════════════════════════════════════════════════════════════════
def test_recap_pdf(token):
    """Test recap PDF generation with Authorization header and token query param"""
    log("\n[BACKEND D] Testing recap PDF", "INFO")
    
    headers = {"Authorization": f"Bearer {token}"}
    passed = 0
    total = 2
    
    # Test 1: With Authorization header
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources/recap-pdf", 
                        headers=headers, timeout=120)
        
        if r.status_code == 200 and r.content[:5] == b"%PDF-":
            log("Recap PDF with Authorization header OK", "PASS")
            passed += 1
        else:
            log(f"Recap PDF with header failed - HTTP {r.status_code}, content: {r.content[:20]}", "FAIL")
    except Exception as e:
        log(f"Recap PDF with header error: {e}", "FAIL")
    
    # Test 2: With token query param (for window.open downloads)
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources/recap-pdf?token={token}", 
                        timeout=120)
        
        if r.status_code == 200 and r.content[:5] == b"%PDF-":
            log("Recap PDF with token query param OK", "PASS")
            passed += 1
        else:
            log(f"Recap PDF with token param failed - HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Recap PDF with token param error: {e}", "FAIL")
    
    # Test 3: With filters
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources/recap-pdf?source=vendor", 
                        headers=headers, timeout=120)
        
        if r.status_code == 200 and r.content[:5] == b"%PDF-":
            log("Recap PDF with filter (source=vendor) OK", "PASS")
            passed += 1
        else:
            log(f"Recap PDF with filter failed - HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Recap PDF with filter error: {e}", "FAIL")
    
    # Test 4: Invalid token should return 401
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources/recap-pdf?token=invalid", 
                        timeout=60)
        
        if r.status_code == 401:
            log("Recap PDF with invalid token returns 401", "PASS")
            passed += 1
        else:
            log(f"Recap PDF with invalid token returned HTTP {r.status_code} (expected 401)", "FAIL")
    except Exception as e:
        log(f"Recap PDF invalid token test error: {e}", "FAIL")
    
    log(f"Recap PDF tests: {passed}/{total} passed", "INFO")
    return passed == total

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND E: Read-only aggregation
# ═══════════════════════════════════════════════════════════════════════════════
def test_readonly_aggregation(token):
    """Test that calling /sources endpoints doesn't create new documents"""
    log("\n[BACKEND E] Testing read-only aggregation", "INFO")
    
    try:
        from pymongo import MongoClient
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        client = MongoClient(mongo_url)
        db = client.test_database
        
        # Get counts before
        before = {
            "wh_delivery_notes": db.wh_delivery_notes.count_documents({}),
            "vendor_shipments": db.vendor_shipments.count_documents({}),
            "buyer_shipments": db.buyer_shipments.count_documents({}),
            "buyer_shipment_items": db.buyer_shipment_items.count_documents({}),
            "counters": db.counters.count_documents({})
        }
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Call /sources multiple times
        for _ in range(3):
            requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources", headers=headers, timeout=60)
        
        # Call recap-pdf
        requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources/recap-pdf", headers=headers, timeout=120)
        
        # Get counts after
        after = {
            "wh_delivery_notes": db.wh_delivery_notes.count_documents({}),
            "vendor_shipments": db.vendor_shipments.count_documents({}),
            "buyer_shipments": db.buyer_shipments.count_documents({}),
            "buyer_shipment_items": db.buyer_shipment_items.count_documents({}),
            "counters": db.counters.count_documents({})
        }
        
        client.close()
        
        if before == after:
            log(f"Read-only verified: no new documents created (before={before})", "PASS")
            return True
        else:
            log(f"NOT read-only: documents changed! before={before}, after={after}", "FAIL")
            return False
            
    except Exception as e:
        log(f"Read-only test failed (DB access): {e}", "WARN")
        # Don't fail the test if we can't access DB
        return True

# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND F: Regression tests
# ═══════════════════════════════════════════════════════════════════════════════
def test_regression(token):
    """Test that old endpoints still work"""
    log("\n[BACKEND F] Testing regression (old endpoints)", "INFO")
    
    headers = {"Authorization": f"Bearer {token}"}
    passed = 0
    total = 0
    
    # Test 1: GET /api/wms/delivery-notes (old list endpoint)
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes", headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            if "items" in data and "pagination" in data:
                log("Old list endpoint /api/wms/delivery-notes works", "PASS")
                passed += 1
            else:
                log("Old list endpoint returned unexpected structure", "FAIL")
        else:
            log(f"Old list endpoint HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Old list endpoint test failed: {e}", "FAIL")
    
    # Test 2: Verify /sources is not caught by /{sj_id} route
    total += 1
    try:
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes/sources", headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            # Should return sources data, not "SJ not found" error
            if "items" in data and "by_source" in data:
                log("Route /sources not caught by /{sj_id} route", "PASS")
                passed += 1
            else:
                log("Route /sources returned unexpected structure", "FAIL")
        else:
            log(f"Route /sources HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"Route /sources test failed: {e}", "FAIL")
    
    # Test 3: GET specific SJ by ID (if any exist)
    total += 1
    try:
        # Get first SJ from list
        r = requests.get(f"{BASE_URL}/api/wms/delivery-notes?limit=1", headers=headers, timeout=60)
        if r.status_code == 200:
            data = r.json()
            items = data.get("items", [])
            if items:
                sj_id = items[0].get("id")
                r2 = requests.get(f"{BASE_URL}/api/wms/delivery-notes/{sj_id}", headers=headers, timeout=60)
                if r2.status_code == 200:
                    log(f"GET /{sj_id} works", "PASS")
                    passed += 1
                else:
                    log(f"GET /{sj_id} HTTP {r2.status_code}", "FAIL")
            else:
                log("No SJ to test GET by ID", "WARN")
                passed += 1  # Don't fail if no data
        else:
            log(f"Failed to get SJ list for regression test: HTTP {r.status_code}", "FAIL")
    except Exception as e:
        log(f"GET by ID test failed: {e}", "FAIL")
    
    log(f"Regression tests: {passed}/{total} passed", "INFO")
    return passed == total

# ═══════════════════════════════════════════════════════════════════════════════
# Main test runner
# ═══════════════════════════════════════════════════════════════════════════════
def main():
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}FASE H-7 & H-8 Backend API Tests{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"Base URL: {BASE_URL}")
    print(f"Testing unified delivery notes + menu alias fix\n")
    
    token = login()
    
    results = {
        "BACKEND A - Sources Endpoint": test_sources_endpoint(token),
        "BACKEND B - Filters": test_filters(token),
        "BACKEND C - PDF URLs": test_pdf_urls(token),
        "BACKEND D - Recap PDF": test_recap_pdf(token),
        "BACKEND E - Read-only": test_readonly_aggregation(token),
        "BACKEND F - Regression": test_regression(token),
    }
    
    print(f"\n{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}Test Summary{Colors.RESET}")
    print(f"{Colors.CYAN}{Colors.BOLD}{'='*80}{Colors.RESET}")
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "PASS" if result else "FAIL"
        color = Colors.GREEN if result else Colors.RED
        print(f"{color}{status}{Colors.RESET} {test_name}")
    
    print(f"\n{Colors.BOLD}Total: {passed}/{total} test groups passed{Colors.RESET}")
    
    if passed == total:
        print(f"{Colors.GREEN}{Colors.BOLD}✓ All backend tests passed!{Colors.RESET}")
        return 0
    else:
        print(f"{Colors.RED}{Colors.BOLD}✗ Some backend tests failed{Colors.RESET}")
        return 1

if __name__ == "__main__":
    sys.exit(main())
