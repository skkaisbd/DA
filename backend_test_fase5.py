#!/usr/bin/env python3
"""
Backend test for FASE 5 - closed_at feature
Tests all new API fields and backend functionality
"""
import os
import sys
import requests
from datetime import datetime, timedelta, timezone

# Get backend URL from environment
BACKEND_URL = os.environ.get('REACT_APP_BACKEND_URL', 'http://localhost:8001')
if not BACKEND_URL.startswith('http'):
    BACKEND_URL = f'https://{BACKEND_URL}'
API_BASE = f'{BACKEND_URL}/api'

print(f"Testing backend at: {API_BASE}")

# Test credentials
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
HR_EMAIL = "hr@dewiaditya.id"
HR_PASSWORD = "Dewi@123"

def login(email, password):
    """Login and get token"""
    try:
        resp = requests.post(f'{API_BASE}/auth/login', 
                            json={'email': email, 'password': password},
                            timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get('token')  # Note: uses 'token', not 'access_token'
        print(f"Login failed: {resp.status_code}")
        return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def test_daily_recap_new_fields(token):
    """Test 1: Daily recap has new fields"""
    print("\n=== Test 1: Daily Recap New Fields ===")
    try:
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(f'{API_BASE}/cmt-override/daily-recap', 
                           headers=headers, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAIL: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        
        # Check for new fields
        has_legacy_count = 'legacy_jobs_without_closed_at' in data
        has_legacy_note = 'legacy_note' in data
        has_as_of_note_base = 'as_of_note_base' in data
        has_as_of_note = 'as_of_note' in data
        
        if not all([has_legacy_count, has_legacy_note, has_as_of_note_base, has_as_of_note]):
            print(f"❌ FAIL: Missing fields")
            print(f"  legacy_jobs_without_closed_at: {has_legacy_count}")
            print(f"  legacy_note: {has_legacy_note}")
            print(f"  as_of_note_base: {has_as_of_note_base}")
            print(f"  as_of_note: {has_as_of_note}")
            return False
        
        # Check field types
        legacy_count = data.get('legacy_jobs_without_closed_at')
        if not isinstance(legacy_count, int):
            print(f"❌ FAIL: legacy_jobs_without_closed_at is not int: {type(legacy_count)}")
            return False
        
        print(f"✅ PASS: All new fields present")
        print(f"  legacy_jobs_without_closed_at: {legacy_count}")
        print(f"  legacy_note: '{data.get('legacy_note')}'")
        print(f"  as_of_note_base length: {len(data.get('as_of_note_base', ''))}")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_weekly_recap_new_fields(token):
    """Test 2: Weekly recap has new fields"""
    print("\n=== Test 2: Weekly Recap New Fields ===")
    try:
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(f'{API_BASE}/cmt-override/weekly-recap', 
                           headers=headers, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAIL: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        
        # Check for new fields
        has_legacy_count = 'legacy_jobs_without_closed_at' in data
        has_legacy_note = 'legacy_note' in data
        
        if not all([has_legacy_count, has_legacy_note]):
            print(f"❌ FAIL: Missing fields")
            print(f"  legacy_jobs_without_closed_at: {has_legacy_count}")
            print(f"  legacy_note: {has_legacy_note}")
            return False
        
        legacy_count = data.get('legacy_jobs_without_closed_at')
        if not isinstance(legacy_count, int):
            print(f"❌ FAIL: legacy_jobs_without_closed_at is not int")
            return False
        
        print(f"✅ PASS: All new fields present")
        print(f"  legacy_jobs_without_closed_at: {legacy_count}")
        print(f"  legacy_note: '{data.get('legacy_note')}'")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_as_of_note_composition(token):
    """Test 3: as_of_note composition is correct"""
    print("\n=== Test 3: as_of_note Composition ===")
    try:
        headers = {'Authorization': f'Bearer {token}'}
        resp = requests.get(f'{API_BASE}/cmt-override/daily-recap', 
                           headers=headers, timeout=30)
        
        if resp.status_code != 200:
            print(f"❌ FAIL: HTTP {resp.status_code}")
            return False
        
        data = resp.json()
        as_of_note = data.get('as_of_note', '')
        as_of_note_base = data.get('as_of_note_base', '')
        legacy_note = data.get('legacy_note', '')
        
        # Check composition rule
        if legacy_note:
            expected = f"{as_of_note_base} Catatan: {legacy_note}"
        else:
            expected = as_of_note_base
        
        if as_of_note != expected:
            print(f"❌ FAIL: as_of_note composition incorrect")
            print(f"  Expected: {expected[:100]}...")
            print(f"  Got: {as_of_note[:100]}...")
            return False
        
        print(f"✅ PASS: as_of_note composition correct")
        print(f"  legacy_note empty: {not legacy_note}")
        print(f"  Composition rule verified")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_rbac_daily_recap(hr_token):
    """Test 4: RBAC - unauthorized role gets 403"""
    print("\n=== Test 4: RBAC Daily Recap ===")
    try:
        headers = {'Authorization': f'Bearer {hr_token}'} if hr_token else {}
        
        # Test daily-recap
        resp1 = requests.get(f'{API_BASE}/cmt-override/daily-recap', 
                            headers=headers, timeout=30)
        
        # Test export
        resp2 = requests.get(f'{API_BASE}/cmt-override/daily-recap/export?format=xlsx', 
                            headers=headers, timeout=30)
        
        # Test without token
        resp3 = requests.get(f'{API_BASE}/cmt-override/daily-recap', timeout=30)
        
        if resp1.status_code != 403:
            print(f"❌ FAIL: daily-recap should be 403, got {resp1.status_code}")
            return False
        
        if resp2.status_code != 403:
            print(f"❌ FAIL: export should be 403, got {resp2.status_code}")
            return False
        
        if resp3.status_code not in [401, 403]:
            print(f"❌ FAIL: no token should be 401/403, got {resp3.status_code}")
            return False
        
        print(f"✅ PASS: RBAC working correctly")
        print(f"  HR role: 403")
        print(f"  Export: 403")
        print(f"  No token: {resp3.status_code}")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_rbac_weekly_recap(hr_token):
    """Test 5: RBAC - weekly recap unauthorized"""
    print("\n=== Test 5: RBAC Weekly Recap ===")
    try:
        headers = {'Authorization': f'Bearer {hr_token}'} if hr_token else {}
        
        # Test weekly-recap
        resp1 = requests.get(f'{API_BASE}/cmt-override/weekly-recap', 
                            headers=headers, timeout=30)
        
        # Test export
        resp2 = requests.get(f'{API_BASE}/cmt-override/weekly-recap/export?format=xlsx', 
                            headers=headers, timeout=30)
        
        # Test without token
        resp3 = requests.get(f'{API_BASE}/cmt-override/weekly-recap', timeout=30)
        
        if resp1.status_code != 403:
            print(f"❌ FAIL: weekly-recap should be 403, got {resp1.status_code}")
            return False
        
        if resp2.status_code != 403:
            print(f"❌ FAIL: export should be 403, got {resp2.status_code}")
            return False
        
        if resp3.status_code not in [401, 403]:
            print(f"❌ FAIL: no token should be 401/403, got {resp3.status_code}")
            return False
        
        print(f"✅ PASS: RBAC working correctly")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_exports_valid(token):
    """Test 6: Export files are valid"""
    print("\n=== Test 6: Export Files Valid ===")
    try:
        headers = {'Authorization': f'Bearer {token}'}
        
        # Test daily XLSX
        resp1 = requests.get(f'{API_BASE}/cmt-override/daily-recap/export?format=xlsx', 
                            headers=headers, timeout=30)
        
        # Test daily PDF
        resp2 = requests.get(f'{API_BASE}/cmt-override/daily-recap/export?format=pdf', 
                            headers=headers, timeout=30)
        
        # Test weekly XLSX
        resp3 = requests.get(f'{API_BASE}/cmt-override/weekly-recap/export?format=xlsx', 
                            headers=headers, timeout=30)
        
        # Test weekly PDF
        resp4 = requests.get(f'{API_BASE}/cmt-override/weekly-recap/export?format=pdf', 
                            headers=headers, timeout=30)
        
        results = []
        
        # Check daily XLSX
        if resp1.status_code == 200 and resp1.content[:2] == b'PK':
            results.append(('Daily XLSX', True, len(resp1.content)))
        else:
            results.append(('Daily XLSX', False, resp1.status_code))
        
        # Check daily PDF
        if resp2.status_code == 200 and resp2.content[:5] == b'%PDF-':
            results.append(('Daily PDF', True, len(resp2.content)))
        else:
            results.append(('Daily PDF', False, resp2.status_code))
        
        # Check weekly XLSX
        if resp3.status_code == 200 and resp3.content[:2] == b'PK':
            results.append(('Weekly XLSX', True, len(resp3.content)))
        else:
            results.append(('Weekly XLSX', False, resp3.status_code))
        
        # Check weekly PDF
        if resp4.status_code == 200 and resp4.content[:5] == b'%PDF-':
            results.append(('Weekly PDF', True, len(resp4.content)))
        else:
            results.append(('Weekly PDF', False, resp4.status_code))
        
        all_pass = all(r[1] for r in results)
        
        for name, passed, info in results:
            status = "✅" if passed else "❌"
            print(f"  {status} {name}: {info if passed else f'HTTP {info}'}")
        
        if all_pass:
            print(f"✅ PASS: All exports valid")
        else:
            print(f"❌ FAIL: Some exports failed")
        
        return all_pass
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def test_db_integrity():
    """Test 7: DB integrity - no closed jobs without closed_at"""
    print("\n=== Test 7: DB Integrity ===")
    try:
        from pymongo import MongoClient
        
        MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        DB_NAME = os.environ.get('DB_NAME', 'test_database')
        
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        
        # Check for closed jobs without closed_at
        closed_statuses = ['Completed', 'Closed', 'Cancelled', 'Canceled', 'Done', 'Finished']
        orphan_count = db.production_jobs.count_documents({
            'status': {'$in': closed_statuses},
            '$or': [{'closed_at': {'$exists': False}}, {'closed_at': None}]
        })
        
        if orphan_count > 0:
            print(f"❌ FAIL: Found {orphan_count} closed jobs without closed_at")
            return False
        
        print(f"✅ PASS: No closed jobs without closed_at")
        print(f"  Orphan count: {orphan_count}")
        return True
        
    except Exception as e:
        print(f"❌ FAIL: {e}")
        return False

def main():
    print("=" * 70)
    print("FASE 5 Backend Testing - closed_at Feature")
    print("=" * 70)
    
    # Login
    print("\n=== Login ===")
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        print("❌ CRITICAL: Admin login failed")
        return 1
    print(f"✅ Admin logged in")
    
    hr_token = login(HR_EMAIL, HR_PASSWORD)
    if not hr_token:
        print("⚠️  WARNING: HR login failed (will skip RBAC tests)")
    else:
        print(f"✅ HR logged in")
    
    # Run tests
    results = []
    
    results.append(('Daily Recap New Fields', test_daily_recap_new_fields(admin_token)))
    results.append(('Weekly Recap New Fields', test_weekly_recap_new_fields(admin_token)))
    results.append(('as_of_note Composition', test_as_of_note_composition(admin_token)))
    
    if hr_token:
        results.append(('RBAC Daily Recap', test_rbac_daily_recap(hr_token)))
        results.append(('RBAC Weekly Recap', test_rbac_weekly_recap(hr_token)))
    
    results.append(('Export Files Valid', test_exports_valid(admin_token)))
    results.append(('DB Integrity', test_db_integrity()))
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed ({passed*100//total}%)")
    
    if passed == total:
        print("\n🎉 All tests passed!")
        return 0
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return 1

if __name__ == '__main__':
    sys.exit(main())
