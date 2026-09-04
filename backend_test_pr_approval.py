#!/usr/bin/env python3
"""
Backend API Testing for Procurement Approval Chain
CV. Dewi Aditya ERP - Procurement Request Approval Workflow

Tests the complete approval chain with proper role-based access control,
separation of duties, and value-based approval depth.
"""
import requests
import sys
from datetime import datetime

# Use public endpoint
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"

class PRApprovalTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.created_prs = []
        
    def login(self, email, password):
        """Login and cache token"""
        if email in self.tokens:
            return self.tokens[email]
            
        print(f"\n🔐 Login: {email}")
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"email": email, "password": password},
                timeout=30
            )
            if response.status_code == 200:
                token = response.json()["token"]
                self.tokens[email] = token
                print(f"✅ Login berhasil")
                return token
            else:
                print(f"❌ Login gagal: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Login error: {str(e)}")
            return None
    
    def run_test(self, name, method, endpoint, expected_status, data=None, token=None, email=None, password="Dewi@123"):
        """Run a single API test"""
        self.tests_run += 1
        print(f"\n🔍 Test {self.tests_run}: {name}")
        
        try:
            # Get token if email provided
            if email and not token:
                token = self.login(email, password)
                if not token:
                    print(f"❌ GAGAL - Tidak bisa login")
                    return False, {}
            
            url = f"{self.base_url}{endpoint}"
            headers = {'Content-Type': 'application/json'}
            if token:
                headers['Authorization'] = f'Bearer {token}'
            
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            else:
                print(f"❌ GAGAL - Method tidak didukung: {method}")
                return False, {}
            
            success = response.status_code == expected_status
            result = response.json() if response.status_code in [200, 201] else {}
            
            if success:
                self.tests_passed += 1
                print(f"✅ PASS - Status: {response.status_code}")
                return True, result
            else:
                print(f"❌ GAGAL - Expected {expected_status}, got {response.status_code}")
                if response.status_code >= 400:
                    try:
                        error_detail = response.json().get('detail', response.text[:200])
                        print(f"   Error: {error_detail}")
                    except Exception:  # noqa: S110
                        print(f"   Response: {response.text[:200]}")
                return False, result
                
        except Exception as e:
            print(f"❌ GAGAL - Error: {str(e)}")
            return False, {}
    
    def create_pr(self, email, title, dept, qty, price):
        """Create a PR and return its ID"""
        token = self.login(email, "Dewi@123")
        data = {
            "title": title,
            "description": "Test PR untuk approval chain",
            "justification": "Testing approval workflow",
            "priority": "medium",
            "request_type": "consumable",
            "department": dept,
            "items": [{
                "name": "Test Item",
                "specification": "Test spec",
                "qty": qty,
                "uom": "pcs",
                "estimated_price": price
            }]
        }
        
        success, result = self.run_test(
            f"Buat PR: {title}",
            "POST",
            "/api/procurement/requests",
            200,
            data=data,
            token=token
        )
        
        if success and result.get('id'):
            pr_id = result['id']
            self.created_prs.append(pr_id)
            print(f"   PR ID: {pr_id}, Nilai: Rp {qty * price:,.0f}".replace(",", "."))
            return pr_id, result
        return None, {}
    
    def submit_pr(self, pr_id, email):
        """Submit PR for approval"""
        token = self.login(email, "Dewi@123")
        success, result = self.run_test(
            f"Submit PR {pr_id[:8]}",
            "POST",
            f"/api/procurement/requests/{pr_id}/submit",
            200,
            data={},
            token=token
        )
        return success, result
    
    def approve_pr(self, pr_id, email, comment="OK"):
        """Approve PR"""
        token = self.login(email, "Dewi@123")
        success, result = self.run_test(
            f"Approve PR {pr_id[:8]} oleh {email}",
            "POST",
            f"/api/procurement/requests/{pr_id}/approve",
            200,
            data={"comment": comment},
            token=token
        )
        return success, result
    
    def reject_pr(self, pr_id, email, reason):
        """Reject PR"""
        token = self.login(email, "Dewi@123")
        success, result = self.run_test(
            f"Reject PR {pr_id[:8]} oleh {email}",
            "POST",
            f"/api/procurement/requests/{pr_id}/reject",
            200,
            data={"reason": reason},
            token=token
        )
        return success, result
    
    def get_inbox(self, email):
        """Get approval inbox"""
        token = self.login(email, "Dewi@123")
        success, result = self.run_test(
            f"Get inbox untuk {email}",
            "GET",
            "/api/procurement/inbox",
            200,
            token=token
        )
        if success:
            items = result if isinstance(result, list) else result.get('items', [])
            print(f"   Inbox items: {len(items)}")
            return success, items
        return False, []
    
    def get_pr_detail(self, pr_id, email):
        """Get PR detail"""
        token = self.login(email, "Dewi@123")
        success, result = self.run_test(
            f"Get PR detail {pr_id[:8]}",
            "GET",
            f"/api/procurement/requests/{pr_id}",
            200,
            token=token
        )
        return success, result
    
    def cleanup(self):
        """Clean up created PRs"""
        print(f"\n🧹 Cleanup: Menghapus {len(self.created_prs)} PR test...")
        admin_token = self.login("admin@garment.com", "Admin@123")
        
        for pr_id in self.created_prs:
            try:
                requests.delete(
                    f"{self.base_url}/api/procurement/requests/{pr_id}",
                    headers={'Authorization': f'Bearer {admin_token}'},
                    timeout=10
                )
            except Exception:  # noqa: S110
                pass
        print(f"✅ Cleanup selesai")

def main():
    tester = PRApprovalTester()
    
    print("=" * 80)
    print("BACKEND API TESTING - PROCUREMENT APPROVAL CHAIN")
    print("CV. Dewi Aditya ERP")
    print("=" * 80)
    
    try:
        # ===== SECTION 1: BASIC API HEALTH =====
        print("\n" + "=" * 80)
        print("SECTION 1: BASIC API HEALTH")
        print("=" * 80)
        
        # Test 1: Health check
        tester.run_test(
            "Health check",
            "GET",
            "/api/health",
            200
        )
        
        # Test 2: Login admin
        admin_token = tester.login("admin@garment.com", "Admin@123")
        if not admin_token:
            print("\n❌ CRITICAL: Admin login gagal, stop testing")
            return 1
        
        # Test 3: Get alert config (threshold settings)
        tester.run_test(
            "Get alert config (PR thresholds)",
            "GET",
            "/api/rahaza/management/alert-config",
            200,
            email="admin@garment.com",
            password="Admin@123"
        )
        
        # ===== SECTION 2: APPROVAL CHAIN DEPTH (VALUE-BASED) =====
        print("\n" + "=" * 80)
        print("SECTION 2: APPROVAL CHAIN DEPTH (VALUE-BASED)")
        print("=" * 80)
        
        # Test 4: Create small PR (1 stage)
        pr_small_id, pr_small = tester.create_pr(
            "hr@dewiaditya.id",
            "TEST PR Kecil (1 tahap)",
            "Gudang",
            10,
            50000  # Rp 500,000 total
        )
        
        if pr_small_id:
            # Test 5: Submit small PR
            success, result = tester.submit_pr(pr_small_id, "hr@dewiaditya.id")
            if success:
                chain = result.get('approval_chain', [])
                print(f"   Approval chain: {chain}")
                if chain == ['dept']:
                    print(f"   ✅ Correct: 1 stage for small value")
                else:
                    print(f"   ❌ Expected ['dept'], got {chain}")
        
        # Test 6: Create medium PR (2 stages)
        pr_medium_id, pr_medium = tester.create_pr(
            "hr@dewiaditya.id",
            "TEST PR Menengah (2 tahap)",
            "Gudang",
            10,
            500000  # Rp 5,000,000 total
        )
        
        if pr_medium_id:
            # Test 7: Submit medium PR
            success, result = tester.submit_pr(pr_medium_id, "hr@dewiaditya.id")
            if success:
                chain = result.get('approval_chain', [])
                print(f"   Approval chain: {chain}")
                if chain == ['dept', 'finance']:
                    print(f"   ✅ Correct: 2 stages for medium value")
                else:
                    print(f"   ❌ Expected ['dept', 'finance'], got {chain}")
        
        # Test 8: Create large PR (3 stages)
        pr_large_id, pr_large = tester.create_pr(
            "hr@dewiaditya.id",
            "TEST PR Besar (3 tahap)",
            "Gudang",
            10,
            5000000  # Rp 50,000,000 total
        )
        
        if pr_large_id:
            # Test 9: Submit large PR
            success, result = tester.submit_pr(pr_large_id, "hr@dewiaditya.id")
            if success:
                chain = result.get('approval_chain', [])
                print(f"   Approval chain: {chain}")
                if chain == ['dept', 'finance', 'final']:
                    print(f"   ✅ Correct: 3 stages for large value")
                else:
                    print(f"   ❌ Expected ['dept', 'finance', 'final'], got {chain}")
        
        # ===== SECTION 3: INBOX & ROLE MAPPING (CRITICAL BUG FIX) =====
        print("\n" + "=" * 80)
        print("SECTION 3: INBOX & ROLE MAPPING (CRITICAL BUG FIX)")
        print("=" * 80)
        
        # Test 10: Gudang inbox (should see dept stage PRs)
        success, gudang_inbox = tester.get_inbox("gudang@dewiaditya.id")
        if success:
            pr_ids = [item['id'] for item in gudang_inbox]
            if pr_small_id in pr_ids and pr_medium_id in pr_ids and pr_large_id in pr_ids:
                print(f"   ✅ Gudang melihat semua PR tahap departemen")
            else:
                print(f"   ⚠️  Gudang inbox: {len(pr_ids)} items")
            
            # Check can_approve flag
            can_approve_count = sum(1 for item in gudang_inbox if item.get('can_approve'))
            print(f"   can_approve items: {can_approve_count}/{len(gudang_inbox)}")
            if can_approve_count == len(gudang_inbox):
                print(f"   ✅ Semua item di inbox punya can_approve=true")
        
        # Test 11: Finance inbox (should be empty before dept approval)
        success, finance_inbox = tester.get_inbox("finance@dewiaditya.id")
        if success:
            print(f"   Finance inbox (before dept approval): {len(finance_inbox)} items")
            if len(finance_inbox) == 0:
                print(f"   ✅ Finance inbox kosong sebelum dept approval (correct)")
        
        # Test 12: HR inbox (not an approver, should be empty)
        success, hr_inbox = tester.get_inbox("hr@dewiaditya.id")
        if success:
            print(f"   HR inbox: {len(hr_inbox)} items")
            if len(hr_inbox) == 0:
                print(f"   ✅ HR (bukan approver) inbox kosong (correct)")
        
        # ===== SECTION 4: SEPARATION OF DUTIES (SoD) =====
        print("\n" + "=" * 80)
        print("SECTION 4: SEPARATION OF DUTIES (SoD)")
        print("=" * 80)
        
        # Test 13: Self-approval should fail
        if pr_large_id:
            tester.run_test(
                "Self-approval (should fail)",
                "POST",
                f"/api/procurement/requests/{pr_large_id}/approve",
                403,
                data={"comment": "test"},
                email="hr@dewiaditya.id"
            )
        
        # Test 14: Wrong stage approver should fail
        if pr_large_id:
            tester.run_test(
                "Finance approve dept stage (should fail)",
                "POST",
                f"/api/procurement/requests/{pr_large_id}/approve",
                403,
                data={"comment": "test"},
                email="finance@dewiaditya.id"
            )
        
        # Test 15: Correct dept approver should succeed
        if pr_large_id:
            success, result = tester.approve_pr(pr_large_id, "gudang@dewiaditya.id", "OK dept")
            if success:
                new_status = result.get('new_status')
                print(f"   New status: {new_status}")
                if new_status == 'dept_approved':
                    print(f"   ✅ PR moved to dept_approved")
        
        # Test 16: Finance inbox should now have the PR (CRITICAL BUG FIX TEST)
        success, finance_inbox = tester.get_inbox("finance@dewiaditya.id")
        if success:
            pr_ids = [item['id'] for item in finance_inbox]
            print(f"   Finance inbox (after dept approval): {len(finance_inbox)} items")
            if pr_large_id in pr_ids:
                print(f"   ✅ CRITICAL: Finance (role accounting) melihat PR tahap keuangan")
                
                # Check can_approve flag
                pr_item = next((item for item in finance_inbox if item['id'] == pr_large_id), None)
                if pr_item and pr_item.get('can_approve'):
                    print(f"   ✅ CRITICAL: can_approve=true untuk finance")
                else:
                    print(f"   ❌ CRITICAL: can_approve tidak true untuk finance")
            else:
                print(f"   ❌ CRITICAL: Finance tidak melihat PR tahap keuangan")
        
        # Test 17: Double-stage approval should fail
        if pr_large_id:
            tester.run_test(
                "Gudang approve finance stage (double-stage, should fail)",
                "POST",
                f"/api/procurement/requests/{pr_large_id}/approve",
                403,
                data={"comment": "test"},
                email="gudang@dewiaditya.id"
            )
        
        # Test 18: Finance approve should succeed
        if pr_large_id:
            success, result = tester.approve_pr(pr_large_id, "finance@dewiaditya.id", "OK finance")
            if success:
                new_status = result.get('new_status')
                print(f"   New status: {new_status}")
                if new_status == 'finance_approved':
                    print(f"   ✅ PR moved to finance_approved")
        
        # Test 19: Director inbox should now have the PR
        success, director_inbox = tester.get_inbox("direktur@dewiaditya.id")
        if success:
            pr_ids = [item['id'] for item in director_inbox]
            print(f"   Director inbox: {len(director_inbox)} items")
            if pr_large_id in pr_ids:
                print(f"   ✅ Director melihat PR tahap final")
        
        # Test 20: Director approve should complete the PR
        if pr_large_id:
            success, result = tester.approve_pr(pr_large_id, "direktur@dewiaditya.id", "OK final")
            if success:
                new_status = result.get('new_status')
                print(f"   New status: {new_status}")
                if new_status == 'approved':
                    print(f"   ✅ PR fully approved (3 stages complete)")
        
        # ===== SECTION 5: REJECTION WORKFLOW =====
        print("\n" + "=" * 80)
        print("SECTION 5: REJECTION WORKFLOW")
        print("=" * 80)
        
        # Test 21: Create PR for rejection test
        pr_reject_id, _ = tester.create_pr(
            "hr@dewiaditya.id",
            "TEST PR untuk Rejection",
            "Gudang",
            5,
            100000
        )
        
        if pr_reject_id:
            tester.submit_pr(pr_reject_id, "hr@dewiaditya.id")
            
            # Test 22: Reject without reason should fail
            tester.run_test(
                "Reject tanpa alasan (should fail)",
                "POST",
                f"/api/procurement/requests/{pr_reject_id}/reject",
                400,
                data={"reason": "   "},
                email="gudang@dewiaditya.id"
            )
            
            # Test 23: Reject with reason should succeed
            success, result = tester.reject_pr(
                pr_reject_id,
                "gudang@dewiaditya.id",
                "Stok masih cukup"
            )
            if success:
                print(f"   ✅ PR rejected with reason")
        
        # ===== SECTION 6: BADGE COUNT =====
        print("\n" + "=" * 80)
        print("SECTION 6: BADGE COUNT")
        print("=" * 80)
        
        # Test 24: Get badge count
        success, badge = tester.run_test(
            "Get approval badge",
            "GET",
            "/api/approval-inbox/badge",
            200,
            email="finance@dewiaditya.id"
        )
        
        if success:
            pr_pending = badge.get('pr_pending', 0)
            print(f"   Badge pr_pending: {pr_pending}")
            
            # Get inbox count
            success2, inbox = tester.get_inbox("finance@dewiaditya.id")
            if success2:
                inbox_count = len(inbox)
                print(f"   Inbox count: {inbox_count}")
                if pr_pending == inbox_count:
                    print(f"   ✅ Badge count matches inbox count")
                else:
                    print(f"   ❌ Badge count mismatch: badge={pr_pending}, inbox={inbox_count}")
        
        # ===== SECTION 7: PR DETAIL FLAGS =====
        print("\n" + "=" * 80)
        print("SECTION 7: PR DETAIL FLAGS")
        print("=" * 80)
        
        # Test 25: Get PR detail with approval flags
        if pr_medium_id:
            success, pr_detail = tester.get_pr_detail(pr_medium_id, "gudang@dewiaditya.id")
            if success:
                print(f"   Status: {pr_detail.get('status')}")
                print(f"   can_approve: {pr_detail.get('can_approve')}")
                print(f"   can_reject: {pr_detail.get('can_reject')}")
                print(f"   chain: {pr_detail.get('chain')}")
                print(f"   stage_label: {pr_detail.get('stage_label')}")
                
                if pr_detail.get('can_approve') and pr_detail.get('can_reject'):
                    print(f"   ✅ Approval flags present")
                
                if pr_detail.get('chain'):
                    print(f"   ✅ Chain data present")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  Testing interrupted by user")
    except Exception as e:
        print(f"\n\n❌ CRITICAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        tester.cleanup()
    
    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Total tests: {tester.tests_run}")
    print(f"Passed: {tester.tests_passed}")
    print(f"Failed: {tester.tests_run - tester.tests_passed}")
    print(f"Success rate: {(tester.tests_passed / tester.tests_run * 100):.1f}%")
    
    if tester.tests_passed == tester.tests_run:
        print("\n✅ ALL TESTS PASSED")
        return 0
    else:
        print(f"\n⚠️  {tester.tests_run - tester.tests_passed} TESTS FAILED")
        return 1

if __name__ == "__main__":
    sys.exit(main())
