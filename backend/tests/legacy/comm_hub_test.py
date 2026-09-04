"""
Session #10 Communication Hub Backend Regression Test
Testing refactored communication module after splitting 1141 LOC monolith into 8 sub-modules.

SPECIAL FOCUS: PUT /api/comm/channels/{id} BUG FIX
- Original monolith had update logic orphaned outside the function (silent no-op)
- Refactor fixes this: PUT must now update name/description/type AND persist to MongoDB

Tests all 27+ communication endpoints:
- Channels CRUD + archive/unarchive
- Channel members management
- Channel messages + file upload
- DM conversations
- Thread replies with @mentions
- Message actions (reactions, edit, delete, pin/unpin)
- Unread tracking, read receipts, search
- Online users
"""
import requests
import sys
import json
import time
from datetime import datetime

# Configuration
BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"


class CommHubTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.admin_user = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []
        
        # Test data IDs (created during tests)
        self.test_channel_id = None
        self.test_private_channel_id = None
        self.test_message_id = None
        self.test_dm_other_uid = None
        self.test_thread_root_id = None

    def log(self, message, level="INFO"):
        """Log test messages"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")

    def run_test(self, name, method, endpoint, expected_status, data=None, verify_fn=None, files=None):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        if not files:
            headers['Content-Type'] = 'application/json'

        self.tests_run += 1
        self.log(f"Test #{self.tests_run}: {name}")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=30)
            elif method == 'POST':
                if files:
                    response = requests.post(url, files=files, headers={k: v for k, v in headers.items() if k != 'Content-Type'}, timeout=30)
                else:
                    response = requests.post(url, json=data, headers=headers, timeout=30)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=30)
            elif method == 'PATCH':
                response = requests.patch(url, json=data, headers=headers, timeout=30)
            elif method == 'DELETE':
                response = requests.delete(url, json=data, headers=headers, timeout=30)
            else:
                raise ValueError(f"Unsupported method: {method}")

            success = response.status_code == expected_status
            
            if success:
                # Additional verification if provided
                if verify_fn:
                    try:
                        response_data = response.json() if response.text else {}
                        verify_result = verify_fn(response_data)
                        if not verify_result:
                            success = False
                            self.log("  ❌ FAILED - Verification failed", "ERROR")
                            self.test_results.append({
                                "test": name,
                                "status": "FAILED",
                                "reason": "Verification failed",
                                "endpoint": endpoint
                            })
                            return False, {}
                    except Exception as e:
                        success = False
                        self.log(f"  ❌ FAILED - Verification error: {str(e)}", "ERROR")
                        self.test_results.append({
                            "test": name,
                            "status": "FAILED",
                            "reason": f"Verification error: {str(e)}",
                            "endpoint": endpoint
                        })
                        return False, {}
            
            if success:
                self.tests_passed += 1
                self.log(f"  ✅ PASSED - Status: {response.status_code}")
                self.test_results.append({
                    "test": name,
                    "status": "PASSED",
                    "endpoint": endpoint
                })
            else:
                self.log(f"  ❌ FAILED - Expected {expected_status}, got {response.status_code}", "ERROR")
                try:
                    error_detail = response.json()
                    self.log(f"     Response: {json.dumps(error_detail, indent=2)}", "ERROR")
                except Exception:
                    self.log(f"     Response: {response.text[:200]}", "ERROR")
                self.test_results.append({
                    "test": name,
                    "status": "FAILED",
                    "reason": f"Expected {expected_status}, got {response.status_code}",
                    "endpoint": endpoint,
                    "response": response.text[:500] if response.text else ""
                })

            return success, response.json() if response.text and success else {}

        except Exception as e:
            self.log(f"  ❌ FAILED - Error: {str(e)}", "ERROR")
            self.test_results.append({
                "test": name,
                "status": "FAILED",
                "reason": f"Exception: {str(e)}",
                "endpoint": endpoint
            })
            return False, {}

    def test_login(self):
        """Test login and get token"""
        self.log("=" * 80)
        self.log("AUTHENTICATION")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Admin Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        
        if success and 'token' in response:
            self.token = response['token']
            self.admin_user = response.get('user', {})
            self.log(f"  Token obtained: {self.token[:20]}...")
            self.log(f"  User ID: {self.admin_user.get('id')}")
            return True
        
        self.log("  ❌ Login failed, cannot proceed with tests", "ERROR")
        return False

    # ========== CHANNELS CRUD ==========
    
    def test_create_channel(self):
        """Test POST /api/comm/channels (create public channel)"""
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: CHANNELS CRUD")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Create Public Channel",
            "POST",
            "/api/comm/channels",
            200,
            data={
                "name": "Test Channel Session10",
                "description": "Testing refactored comm module",
                "type": "public",
                "members": [self.admin_user['id']]
            },
            verify_fn=lambda r: 'id' in r and r.get('name') == "Test Channel Session10"
        )
        
        if success:
            self.test_channel_id = response['id']
            self.log(f"  Created channel ID: {self.test_channel_id}")
        
        return success

    def test_create_private_channel(self):
        """Test POST /api/comm/channels (create private channel)"""
        success, response = self.run_test(
            "Create Private Channel",
            "POST",
            "/api/comm/channels",
            200,
            data={
                "name": "Private Test Channel",
                "description": "Private channel for testing",
                "type": "private",
                "members": [self.admin_user['id']]
            },
            verify_fn=lambda r: 'id' in r and r.get('type') == "private"
        )
        
        if success:
            self.test_private_channel_id = response['id']
            self.log(f"  Created private channel ID: {self.test_private_channel_id}")
        
        return success

    def test_list_channels(self):
        """Test GET /api/comm/channels"""
        success, response = self.run_test(
            "List Channels (include_archived=false)",
            "GET",
            "/api/comm/channels?include_archived=false",
            200,
            verify_fn=lambda r: isinstance(r, list) and len(r) >= 1
        )
        
        if success:
            self.log(f"  Found {len(response)} channels")
        
        return success

    def test_get_channel_detail(self):
        """Test GET /api/comm/channels/{channel_id}"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Get Channel Detail",
            "GET",
            f"/api/comm/channels/{self.test_channel_id}",
            200,
            verify_fn=lambda r: r.get('id') == self.test_channel_id
        )
        
        return success

    def test_update_channel_bug_fix(self):
        """Test PUT /api/comm/channels/{channel_id} — THE BUG FIX
        
        CRITICAL: This endpoint was BROKEN in the original monolith.
        The update/persist/return logic was orphaned outside the function.
        After refactor, it MUST:
        1. Update the channel's name/description/type in MongoDB
        2. Return the UPDATED channel dict (not None)
        3. Persist changes (verified by re-fetching)
        """
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        self.log("\n" + "=" * 80)
        self.log("🔥 CRITICAL BUG FIX TEST: PUT /api/comm/channels/{id}")
        self.log("=" * 80)
        
        # Step 1: Update the channel
        new_name = "Updated Channel Name Session10"
        new_description = "Updated description to verify bug fix"
        
        success, response = self.run_test(
            "Update Channel (BUG FIX: must persist and return updated doc)",
            "PUT",
            f"/api/comm/channels/{self.test_channel_id}",
            200,
            data={
                "name": new_name,
                "description": new_description,
                "type": "private"
            },
            verify_fn=lambda r: (
                r.get('name') == new_name and
                r.get('description') == new_description and
                r.get('type') == "private"
            )
        )
        
        if not success:
            self.log("  ❌ CRITICAL: PUT endpoint failed to return updated doc", "ERROR")
            return False
        
        self.log(f"  ✅ PUT returned updated doc with name: {response.get('name')}")
        
        # Step 2: Re-fetch the channel to verify persistence
        time.sleep(0.5)  # Small delay to ensure DB write completes
        
        success2, response2 = self.run_test(
            "Re-fetch Channel (verify persistence of PUT update)",
            "GET",
            f"/api/comm/channels/{self.test_channel_id}",
            200,
            verify_fn=lambda r: (
                r.get('name') == new_name and
                r.get('description') == new_description and
                r.get('type') == "private"
            )
        )
        
        if success2:
            self.log(f"  ✅ PERSISTENCE VERIFIED: Channel name is '{response2.get('name')}'")
            self.log("  ✅ BUG FIX CONFIRMED: PUT now correctly updates and persists")
        else:
            self.log("  ❌ CRITICAL: PUT did not persist to MongoDB (bug still exists!)", "ERROR")
        
        return success and success2

    def test_archive_channel(self):
        """Test PATCH /api/comm/channels/{channel_id}/archive"""
        if not self.test_private_channel_id:
            self.log("  ⚠️  SKIPPED - No private channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Archive Channel",
            "PATCH",
            f"/api/comm/channels/{self.test_private_channel_id}/archive",
            200,
            verify_fn=lambda r: r.get('ok') and r.get('archived')
        )
        
        return success

    def test_unarchive_channel(self):
        """Test PATCH /api/comm/channels/{channel_id}/unarchive"""
        if not self.test_private_channel_id:
            self.log("  ⚠️  SKIPPED - No private channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Unarchive Channel",
            "PATCH",
            f"/api/comm/channels/{self.test_private_channel_id}/unarchive",
            200,
            verify_fn=lambda r: r.get('ok') and not r.get('archived')
        )
        
        return success

    # ========== CHANNEL MEMBERS ==========
    
    def test_get_channel_members(self):
        """Test GET /api/comm/channels/{channel_id}/members"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: CHANNEL MEMBERS")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Get Channel Members",
            "GET",
            f"/api/comm/channels/{self.test_channel_id}/members",
            200,
            verify_fn=lambda r: 'members' in r and isinstance(r['members'], list)
        )
        
        if success:
            self.log(f"  Found {len(response['members'])} members")
            # Store a member ID for DM testing (if there's more than admin)
            for member in response['members']:
                if member['id'] != self.admin_user['id']:
                    self.test_dm_other_uid = member['id']
                    break
        
        return success

    def test_add_channel_members(self):
        """Test POST /api/comm/channels/{channel_id}/members"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        # Get another user to add (if exists)
        success_users, users = self.run_test(
            "Get Users List (to find member to add)",
            "GET",
            "/api/users",
            200
        )
        
        if not success_users or not users:
            self.log("  ⚠️  SKIPPED - No other users available to add", "WARN")
            return True
        
        # Find a user that's not admin
        other_user = None
        for u in users:
            if u['id'] != self.admin_user['id']:
                other_user = u
                break
        
        if not other_user:
            self.log("  ⚠️  SKIPPED - No other users available to add", "WARN")
            return True
        
        self.test_dm_other_uid = other_user['id']  # Store for DM tests
        
        success, response = self.run_test(
            "Add Channel Members",
            "POST",
            f"/api/comm/channels/{self.test_channel_id}/members",
            200,
            data={"member_ids": [other_user['id']]},
            verify_fn=lambda r: r.get('ok')
        )
        
        return success

    def test_remove_channel_member(self):
        """Test DELETE /api/comm/channels/{channel_id}/members/{uid}"""
        if not self.test_channel_id or not self.test_dm_other_uid:
            self.log("  ⚠️  SKIPPED - No channel or member ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Remove Channel Member",
            "DELETE",
            f"/api/comm/channels/{self.test_channel_id}/members/{self.test_dm_other_uid}",
            200,
            verify_fn=lambda r: r.get('ok')
        )
        
        return success

    # ========== CHANNEL MESSAGES ==========
    
    def test_send_channel_message(self):
        """Test POST /api/comm/channels/{channel_id}/messages"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: CHANNEL MESSAGES")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Send Channel Message",
            "POST",
            f"/api/comm/channels/{self.test_channel_id}/messages",
            200,
            data={
                "content": "Test message from Session #10 refactor test",
                "message_type": "text"
            },
            verify_fn=lambda r: 'id' in r and r.get('content') == "Test message from Session #10 refactor test"
        )
        
        if success:
            self.test_message_id = response['id']
            self.test_thread_root_id = response['id']  # Use for thread tests
            self.log(f"  Created message ID: {self.test_message_id}")
        
        return success

    def test_send_channel_message_with_mention(self):
        """Test POST /api/comm/channels/{channel_id}/messages with @mention"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Send Channel Message with @mention",
            "POST",
            f"/api/comm/channels/{self.test_channel_id}/messages",
            200,
            data={
                "content": f"Test @mention to @{self.admin_user.get('name', 'Admin')}",
                "message_type": "text"
            },
            verify_fn=lambda r: 'id' in r
        )
        
        return success

    def test_get_channel_messages(self):
        """Test GET /api/comm/channels/{channel_id}/messages"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Get Channel Messages",
            "GET",
            f"/api/comm/channels/{self.test_channel_id}/messages?limit=50",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        
        if success:
            self.log(f"  Found {len(response)} messages")
        
        return success

    def test_upload_file(self):
        """Test POST /api/comm/channels/{channel_id}/upload"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        # Create a small test file
        test_file_content = b"Test file content for Session #10"
        
        success, response = self.run_test(
            "Upload File to Channel",
            "POST",
            f"/api/comm/channels/{self.test_channel_id}/upload",
            200,
            files={'file': ('test.txt', test_file_content, 'text/plain')},
            verify_fn=lambda r: 'file_url' in r and 'file_name' in r
        )
        
        return success

    # ========== DM CONVERSATIONS ==========
    
    def test_list_conversations(self):
        """Test GET /api/comm/conversations"""
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: DM CONVERSATIONS")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "List DM Conversations",
            "GET",
            "/api/comm/conversations",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        
        if success:
            self.log(f"  Found {len(response)} conversations")
        
        return success

    def test_send_dm(self):
        """Test POST /api/comm/conversations/{other_uid}/messages"""
        if not self.test_dm_other_uid:
            self.log("  ⚠️  SKIPPED - No other user ID available for DM", "WARN")
            return True
        
        success, response = self.run_test(
            "Send DM Message",
            "POST",
            f"/api/comm/conversations/{self.test_dm_other_uid}/messages",
            200,
            data={
                "content": "Test DM from Session #10 refactor test",
                "message_type": "text"
            },
            verify_fn=lambda r: 'id' in r and r.get('content') == "Test DM from Session #10 refactor test"
        )
        
        return success

    def test_get_dm_messages(self):
        """Test GET /api/comm/conversations/{other_uid}/messages"""
        if not self.test_dm_other_uid:
            self.log("  ⚠️  SKIPPED - No other user ID available for DM", "WARN")
            return True
        
        success, response = self.run_test(
            "Get DM Messages",
            "GET",
            f"/api/comm/conversations/{self.test_dm_other_uid}/messages?limit=50",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        
        if success:
            self.log(f"  Found {len(response)} DM messages")
        
        return success

    # ========== THREADS ==========
    
    def test_get_thread(self):
        """Test GET /api/comm/messages/{root_id}/thread"""
        if not self.test_thread_root_id:
            self.log("  ⚠️  SKIPPED - No thread root ID available", "WARN")
            return True
        
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: THREADS")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Get Thread",
            "GET",
            f"/api/comm/messages/{self.test_thread_root_id}/thread",
            200,
            verify_fn=lambda r: 'root' in r and 'replies' in r
        )
        
        if success:
            self.log(f"  Thread has {len(response['replies'])} replies")
        
        return success

    def test_post_thread_reply(self):
        """Test POST /api/comm/messages/{root_id}/thread/reply"""
        if not self.test_thread_root_id:
            self.log("  ⚠️  SKIPPED - No thread root ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Post Thread Reply",
            "POST",
            f"/api/comm/messages/{self.test_thread_root_id}/thread/reply",
            200,
            data={
                "content": "Test thread reply from Session #10",
                "message_type": "text"
            },
            verify_fn=lambda r: 'id' in r and r.get('thread_root_id') == self.test_thread_root_id
        )
        
        return success

    def test_post_thread_reply_with_mention(self):
        """Test POST /api/comm/messages/{root_id}/thread/reply with @mention"""
        if not self.test_thread_root_id:
            self.log("  ⚠️  SKIPPED - No thread root ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Post Thread Reply with @mention",
            "POST",
            f"/api/comm/messages/{self.test_thread_root_id}/thread/reply",
            200,
            data={
                "content": f"Thread reply with @{self.admin_user.get('name', 'Admin')}",
                "message_type": "text"
            },
            verify_fn=lambda r: 'id' in r
        )
        
        return success

    # ========== MESSAGE ACTIONS ==========
    
    def test_toggle_reaction(self):
        """Test POST /api/comm/messages/{msg_id}/reaction"""
        if not self.test_message_id:
            self.log("  ⚠️  SKIPPED - No message ID available", "WARN")
            return True
        
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: MESSAGE ACTIONS")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Toggle Reaction (add 👍)",
            "POST",
            f"/api/comm/messages/{self.test_message_id}/reaction",
            200,
            data={"emoji": "👍"},
            verify_fn=lambda r: r.get('ok') and 'reactions' in r
        )
        
        return success

    def test_edit_message(self):
        """Test PATCH /api/comm/messages/{msg_id}"""
        if not self.test_message_id:
            self.log("  ⚠️  SKIPPED - No message ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Edit Message",
            "PATCH",
            f"/api/comm/messages/{self.test_message_id}",
            200,
            data={"content": "Edited message content from Session #10"},
            verify_fn=lambda r: r.get('content') == "Edited message content from Session #10" and r.get('edited')
        )
        
        return success

    def test_pin_message(self):
        """Test POST /api/comm/messages/{msg_id}/pin"""
        if not self.test_message_id:
            self.log("  ⚠️  SKIPPED - No message ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Pin Message",
            "POST",
            f"/api/comm/messages/{self.test_message_id}/pin",
            200,
            verify_fn=lambda r: r.get('ok')
        )
        
        return success

    def test_get_pinned_messages(self):
        """Test GET /api/comm/channels/{ch_id}/pinned"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Get Pinned Messages",
            "GET",
            f"/api/comm/channels/{self.test_channel_id}/pinned",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        
        if success:
            self.log(f"  Found {len(response)} pinned messages")
        
        return success

    def test_unpin_message(self):
        """Test DELETE /api/comm/messages/{msg_id}/pin"""
        if not self.test_message_id:
            self.log("  ⚠️  SKIPPED - No message ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Unpin Message",
            "DELETE",
            f"/api/comm/messages/{self.test_message_id}/pin",
            200,
            verify_fn=lambda r: r.get('ok')
        )
        
        return success

    def test_delete_message(self):
        """Test DELETE /api/comm/messages/{msg_id}"""
        if not self.test_message_id:
            self.log("  ⚠️  SKIPPED - No message ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Delete Message",
            "DELETE",
            f"/api/comm/messages/{self.test_message_id}",
            200,
            verify_fn=lambda r: r.get('ok') and r.get('deleted')
        )
        
        return success

    # ========== UNREAD & SEARCH ==========
    
    def test_get_unread_counts(self):
        """Test GET /api/comm/unread"""
        self.log("\n" + "=" * 80)
        self.log("TEST GROUP: UNREAD & SEARCH")
        self.log("=" * 80)
        
        success, response = self.run_test(
            "Get Unread Counts",
            "GET",
            "/api/comm/unread",
            200,
            verify_fn=lambda r: 'channels' in r and 'dms' in r
        )
        
        return success

    def test_mark_as_read(self):
        """Test POST /api/comm/read/{ref_id}"""
        if not self.test_channel_id:
            self.log("  ⚠️  SKIPPED - No channel ID available", "WARN")
            return True
        
        success, response = self.run_test(
            "Mark Channel as Read",
            "POST",
            f"/api/comm/read/{self.test_channel_id}",
            200,
            verify_fn=lambda r: r.get('ok')
        )
        
        return success

    def test_search_messages(self):
        """Test GET /api/comm/search"""
        success, response = self.run_test(
            "Search Messages",
            "GET",
            "/api/comm/search?q=test&limit=20",
            200,
            verify_fn=lambda r: isinstance(r, list)
        )
        
        if success:
            self.log(f"  Found {len(response)} messages matching 'test'")
        
        return success

    def test_get_online_users(self):
        """Test GET /api/comm/online-users"""
        success, response = self.run_test(
            "Get Online Users",
            "GET",
            "/api/comm/online-users",
            200,
            verify_fn=lambda r: 'online_user_ids' in r and isinstance(r['online_user_ids'], list)
        )
        
        if success:
            self.log(f"  Found {len(response['online_user_ids'])} online users")
        
        return success

    # ========== SUMMARY ==========
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 80)
        self.log("TEST SUMMARY")
        self.log("=" * 80)
        
        passed = sum(1 for r in self.test_results if r['status'] == 'PASSED')
        failed = sum(1 for r in self.test_results if r['status'] == 'FAILED')
        
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {passed} ✅")
        self.log(f"Failed: {failed} ❌")
        self.log(f"Success Rate: {(passed/self.tests_run*100):.1f}%")
        
        if failed > 0:
            self.log("\nFailed Tests:")
            for r in self.test_results:
                if r['status'] == 'FAILED':
                    self.log(f"  ❌ {r['test']}")
                    self.log(f"     Endpoint: {r['endpoint']}")
                    if 'reason' in r:
                        self.log(f"     Reason: {r['reason']}")
        
        return passed, failed

    def run_all_tests(self):
        """Run all communication hub tests"""
        self.log("=" * 80)
        self.log("SESSION #10 COMMUNICATION HUB BACKEND REGRESSION TEST")
        self.log("Testing refactored communication module (1141 LOC → 8 sub-modules)")
        self.log("=" * 80)
        
        # Authentication
        if not self.test_login():
            return 1
        
        # Run all tests in order (some depend on previous tests)
        self.test_create_channel()
        self.test_create_private_channel()
        self.test_list_channels()
        self.test_get_channel_detail()
        self.test_update_channel_bug_fix()  # 🔥 CRITICAL BUG FIX TEST
        self.test_archive_channel()
        self.test_unarchive_channel()
        
        self.test_get_channel_members()
        self.test_add_channel_members()
        self.test_remove_channel_member()
        
        self.test_send_channel_message()
        self.test_send_channel_message_with_mention()
        self.test_get_channel_messages()
        self.test_upload_file()
        
        self.test_list_conversations()
        self.test_send_dm()
        self.test_get_dm_messages()
        
        self.test_get_thread()
        self.test_post_thread_reply()
        self.test_post_thread_reply_with_mention()
        
        self.test_toggle_reaction()
        self.test_edit_message()
        self.test_pin_message()
        self.test_get_pinned_messages()
        self.test_unpin_message()
        self.test_delete_message()
        
        self.test_get_unread_counts()
        self.test_mark_as_read()
        self.test_search_messages()
        self.test_get_online_users()
        
        # Print summary
        passed, failed = self.print_summary()
        
        return 0 if failed == 0 else 1


def main():
    tester = CommHubTester()
    return tester.run_all_tests()


if __name__ == "__main__":
    sys.exit(main())
