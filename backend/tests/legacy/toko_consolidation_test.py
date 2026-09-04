"""
Backend Testing: P1.D Toko Consolidation + P1.A Accessory Cleanup
Tests all /api/dewi/toko/* and /api/acc/* endpoints to verify SSOT routing.
"""
import requests
import sys
from datetime import datetime
from pymongo import MongoClient

BASE_URL = "https://da37-cmt-bridge.preview.emergentagent.com"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"

# MongoDB connection
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "dewi_aditya_erp"

class TokoBackendTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.token = None
        self.tests_run = 0
        self.tests_passed = 0
        self.test_data = {}
        
        # MongoDB client
        self.mongo_client = MongoClient(MONGO_URL)
        self.db = self.mongo_client[DB_NAME]
        
    def log(self, msg, level="INFO"):
        """Log with timestamp"""
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] {level}: {msg}")
        
    def test(self, name, method, endpoint, expected_status, data=None, verify_fn=None):
        """Run a single API test"""
        url = f"{self.base_url}{endpoint}"
        headers = {'Content-Type': 'application/json'}
        if self.token:
            headers['Authorization'] = f'Bearer {self.token}'
        
        self.tests_run += 1
        self.log(f"Testing {name}...")
        
        try:
            if method == 'GET':
                response = requests.get(url, headers=headers, timeout=15)
            elif method == 'POST':
                response = requests.post(url, json=data, headers=headers, timeout=15)
            elif method == 'PUT':
                response = requests.put(url, json=data, headers=headers, timeout=15)
            elif method == 'DELETE':
                response = requests.delete(url, headers=headers, timeout=15)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            success = response.status_code == expected_status
            
            if success:
                self.tests_passed += 1
                self.log(f"✅ PASS - {name} (status: {response.status_code})", "PASS")
                
                # Run additional verification if provided
                if verify_fn:
                    try:
                        verify_fn(response)
                    except AssertionError as e:
                        self.log(f"❌ Verification failed: {e}", "FAIL")
                        self.tests_passed -= 1
                        return False, {}
                
                return True, response.json() if response.text else {}
            else:
                self.log(f"❌ FAIL - {name} (expected {expected_status}, got {response.status_code})", "FAIL")
                self.log(f"   Response: {response.text[:200]}", "DEBUG")
                return False, {}
                
        except Exception as e:
            self.log(f"❌ FAIL - {name} (error: {str(e)})", "FAIL")
            return False, {}
    
    def verify_collection_dropped(self, collection_name):
        """Verify a collection is empty (dropped or unused)"""
        collections = self.db.list_collection_names()
        if collection_name in collections:
            count = self.db[collection_name].count_documents({})
            if count > 0:
                raise AssertionError(f"Collection {collection_name} should be empty but has {count} documents!")
            self.log(f"✓ Collection {collection_name} is empty (unused)", "VERIFY")
        else:
            self.log(f"✓ Collection {collection_name} is dropped", "VERIFY")
    
    def verify_collection_exists(self, collection_name):
        """Verify a collection exists"""
        collections = self.db.list_collection_names()
        if collection_name not in collections:
            raise AssertionError(f"Collection {collection_name} should exist but is missing!")
        self.log(f"✓ Collection {collection_name} exists", "VERIFY")
    
    def verify_document_in_collection(self, collection_name, query, expected_fields=None):
        """Verify a document exists in a collection with expected fields"""
        doc = self.db[collection_name].find_one(query, {"_id": 0})
        if not doc:
            raise AssertionError(f"Document not found in {collection_name} with query {query}")
        
        if expected_fields:
            for field, expected_value in expected_fields.items():
                actual_value = doc.get(field)
                if actual_value != expected_value:
                    raise AssertionError(
                        f"Field {field} mismatch in {collection_name}: "
                        f"expected {expected_value}, got {actual_value}"
                    )
        
        self.log(f"✓ Document verified in {collection_name}", "VERIFY")
        return doc
    
    def run_all_tests(self):
        """Run all test suites"""
        self.log("=" * 60)
        self.log("BACKEND TESTING: P1.D Toko Consolidation + P1.A Accessory")
        self.log("=" * 60)
        
        # Login
        self.log("\n--- Authentication ---")
        success, resp = self.test(
            "Login",
            "POST",
            "/api/auth/login",
            200,
            data={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if not success:
            self.log("❌ Login failed, cannot continue", "FATAL")
            return False
        
        self.token = resp.get('token')
        self.log(f"✓ Logged in as {ADMIN_EMAIL}")
        
        # P1.D Verification: Check dropped collections
        self.log("\n--- P1.D: Verify Dropped Collections ---")
        try:
            self.verify_collection_dropped("dewi_toko_products")
            self.verify_collection_dropped("dewi_toko_channels")
            self.verify_collection_dropped("dewi_toko_channel_syncs")
            self.verify_collection_dropped("dewi_toko_orders")
            self.verify_collection_dropped("dewi_toko_returns")
            self.verify_collection_dropped("dewi_toko_reviews")
            self.verify_collection_dropped("acc_items")
            self.verify_collection_dropped("acc_stock_movements")
            self.log("✅ All legacy collections dropped successfully")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Verify SSOT collections exist
        self.log("\n--- Verify SSOT Collections Exist ---")
        try:
            self.verify_collection_exists("marketing_catalog_items")
            self.verify_collection_exists("marketing_platform_accounts")
            self.verify_collection_exists("marketing_stock_syncs")
            self.verify_collection_exists("marketing_orders")
            self.verify_collection_exists("marketing_returns")
            self.verify_collection_exists("marketing_reviews")
            self.verify_collection_exists("rahaza_materials")
            self.verify_collection_exists("rahaza_material_movements")
            self.verify_collection_exists("rahaza_material_stock")
            self.log("✅ All SSOT collections exist")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Test Products
        self.log("\n--- Testing Products (marketing_catalog_items) ---")
        
        # List products
        success, resp = self.test(
            "GET /api/dewi/toko/products",
            "GET",
            "/api/dewi/toko/products",
            200
        )
        if not success:
            return False
        
        # Create product
        test_sku = f"TEST-{datetime.now().strftime('%H%M%S')}"
        success, resp = self.test(
            "POST /api/dewi/toko/products",
            "POST",
            "/api/dewi/toko/products",
            200,
            data={
                "sku_code": test_sku,
                "name": "Test Product for Consolidation",
                "category": "Test",
                "base_price": 100000,
                "cost_price": 50000,
                "stock_total": 10,
                "status": "active"
            }
        )
        if not success:
            return False
        
        product_id = resp.get('id')
        self.test_data['product_id'] = product_id
        
        # Verify product in marketing_catalog_items
        try:
            doc = self.verify_document_in_collection(
                "marketing_catalog_items",
                {"id": product_id},
                {"sku_code": test_sku.upper(), "_legacy_toko": True}
            )
            self.log(f"✓ Product written to marketing_catalog_items with catalog_id: {doc.get('catalog_id', 'N/A')[:8]}...")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Get single product
        success, resp = self.test(
            f"GET /api/dewi/toko/products/{product_id}",
            "GET",
            f"/api/dewi/toko/products/{product_id}",
            200
        )
        if not success:
            return False
        
        # Update product
        success, resp = self.test(
            f"PUT /api/dewi/toko/products/{product_id}",
            "PUT",
            f"/api/dewi/toko/products/{product_id}",
            200,
            data={"name": "Test Product UPDATED", "stock_total": 20}
        )
        if not success:
            return False
        
        # Verify update in DB
        try:
            self.verify_document_in_collection(
                "marketing_catalog_items",
                {"id": product_id},
                {"stock_total": 20}
            )
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Delete product
        success, resp = self.test(
            f"DELETE /api/dewi/toko/products/{product_id}",
            "DELETE",
            f"/api/dewi/toko/products/{product_id}",
            200
        )
        if not success:
            return False
        
        # Test Channels
        self.log("\n--- Testing Channels (marketing_platform_accounts) ---")
        
        # List channels (auto-seed)
        success, resp = self.test(
            "GET /api/dewi/toko/channels",
            "GET",
            "/api/dewi/toko/channels",
            200
        )
        if not success:
            return False
        
        channels = resp
        if len(channels) < 4:
            self.log(f"❌ Expected at least 4 channels, got {len(channels)}", "FAIL")
            return False
        
        # Verify channels in marketing_platform_accounts
        try:
            count = self.db.marketing_platform_accounts.count_documents({"_legacy_toko": True})
            if count < 4:
                raise AssertionError(f"Expected at least 4 channels in marketing_platform_accounts, got {count}")
            self.log(f"✓ {count} channels in marketing_platform_accounts")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Update channel
        success, resp = self.test(
            "PUT /api/dewi/toko/channels/shopee",
            "PUT",
            "/api/dewi/toko/channels/shopee",
            200,
            data={"enabled": True, "fee_pct": 2.5}
        )
        if not success:
            return False
        
        # Verify update in DB
        try:
            self.verify_document_in_collection(
                "marketing_platform_accounts",
                {"code": "shopee", "_legacy_toko": True},
                {"enabled": True, "fee_pct": 2.5}
            )
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Sync channel
        success, resp = self.test(
            "POST /api/dewi/toko/channels/shopee/sync",
            "POST",
            "/api/dewi/toko/channels/shopee/sync",
            200
        )
        if not success:
            return False
        
        # Verify sync log in marketing_stock_syncs
        try:
            doc = self.db.marketing_stock_syncs.find_one(
                {"channel_code": "shopee", "_legacy_toko": True},
                sort=[("created_at", -1)]
            )
            if not doc:
                raise AssertionError("Sync log not found in marketing_stock_syncs")
            self.log(f"✓ Sync log created in marketing_stock_syncs (status: {doc.get('status')})")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Get sync history
        success, resp = self.test(
            "GET /api/dewi/toko/channels/shopee/sync-history",
            "GET",
            "/api/dewi/toko/channels/shopee/sync-history",
            200
        )
        if not success:
            return False
        
        # Test Orders
        self.log("\n--- Testing Orders (marketing_orders) ---")
        
        # Create order
        order_ref = f"TEST-ORD-{datetime.now().strftime('%H%M%S')}"
        success, resp = self.test(
            "POST /api/dewi/toko/orders",
            "POST",
            "/api/dewi/toko/orders",
            201,
            data={
                "channel_code": "shopee",
                "order_ref": order_ref,
                "customer_name": "Test Customer",
                "customer_city": "Jakarta",
                "items": [{"sku_code": "TEST-SKU", "qty": 1, "price": 100000}],
                "total_amount": 100000,
                "fee_amount": 2500
            }
        )
        if not success:
            return False
        
        order_id = resp.get('id')
        self.test_data['order_id'] = order_id
        
        # Verify order in marketing_orders
        try:
            doc = self.verify_document_in_collection(
                "marketing_orders",
                {"id": order_id},
                {"_legacy_toko": True, "status": "new", "total_payment": 100000.0}
            )
            self.log(f"✓ Order written to marketing_orders (order_id: {doc.get('order_id')})")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # List orders
        success, resp = self.test(
            "GET /api/dewi/toko/orders",
            "GET",
            "/api/dewi/toko/orders",
            200
        )
        if not success:
            return False
        
        # Get single order
        success, resp = self.test(
            f"GET /api/dewi/toko/orders/{order_id}",
            "GET",
            f"/api/dewi/toko/orders/{order_id}",
            200
        )
        if not success:
            return False
        
        # Update order status to packed
        success, resp = self.test(
            f"POST /api/dewi/toko/orders/{order_id}/status (packed)",
            "POST",
            f"/api/dewi/toko/orders/{order_id}/status",
            200,
            data={"status": "packed"}
        )
        if not success:
            return False
        
        # Verify packed_date is set in marketing_orders
        try:
            doc = self.db.marketing_orders.find_one({"id": order_id})
            if not doc:
                raise AssertionError("Order not found in marketing_orders")
            if doc.get("status") != "packed":
                raise AssertionError(f"Order status should be 'packed', got '{doc.get('status')}'")
            if not doc.get("packed_date"):
                raise AssertionError("packed_date should be set but is None")
            self.log("✓ Order status updated to 'packed' with packed_date set")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Update order status to shipped
        success, resp = self.test(
            f"POST /api/dewi/toko/orders/{order_id}/status (shipped)",
            "POST",
            f"/api/dewi/toko/orders/{order_id}/status",
            200,
            data={"status": "shipped", "tracking_number": "JNT123456", "courier": "J&T"}
        )
        if not success:
            return False
        
        # Verify shipped status and tracking
        try:
            doc = self.db.marketing_orders.find_one({"id": order_id})
            if doc.get("status") != "shipped":
                raise AssertionError(f"Order status should be 'shipped', got '{doc.get('status')}'")
            if doc.get("tracking_number") != "JNT123456":
                raise AssertionError(f"tracking_number should be 'JNT123456', got '{doc.get('tracking_number')}'")
            self.log("✓ Order status updated to 'shipped' with tracking_number")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Test Returns
        self.log("\n--- Testing Returns (marketing_returns) ---")
        
        # Create return
        success, resp = self.test(
            "POST /api/dewi/toko/returns",
            "POST",
            "/api/dewi/toko/returns",
            201,
            data={
                "order_id": order_id,
                "customer_name": "Test Customer",
                "channel_code": "shopee",
                "reason": "Product defect",
                "estimated_value": 50000
            }
        )
        if not success:
            return False
        
        return_id = resp.get('id')
        self.test_data['return_id'] = return_id
        
        # Verify return in marketing_returns
        try:
            self.verify_document_in_collection(
                "marketing_returns",
                {"id": return_id},
                {"_legacy_toko": True, "status": "new"}
            )
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # List returns
        success, resp = self.test(
            "GET /api/dewi/toko/returns",
            "GET",
            "/api/dewi/toko/returns",
            200
        )
        if not success:
            return False
        
        # Make decision on return
        success, resp = self.test(
            f"POST /api/dewi/toko/returns/{return_id}/decision",
            "POST",
            f"/api/dewi/toko/returns/{return_id}/decision",
            200,
            data={
                "decision": "refund",
                "decision_notes": "Approved for refund"
            }
        )
        if not success:
            return False
        
        # Verify decision in DB
        try:
            doc = self.db.marketing_returns.find_one({"id": return_id})
            if doc.get("decision") != "refund":
                raise AssertionError(f"Decision should be 'refund', got '{doc.get('decision')}'")
            self.log("✓ Return decision updated to 'refund'")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Test Reviews
        self.log("\n--- Testing Reviews (marketing_reviews) ---")
        
        # Create review
        success, resp = self.test(
            "POST /api/dewi/toko/reviews",
            "POST",
            "/api/dewi/toko/reviews",
            201,  # API returns 201 for creation
            data={
                "channel_code": "shopee",
                "order_ref": order_ref,
                "customer_name": "Test Customer",
                "rating": 5,
                "review_text": "Great product!"
            }
        )
        if not success:
            return False
        
        review_id = resp.get('id')
        self.test_data['review_id'] = review_id
        
        # Verify review in marketing_reviews
        try:
            self.verify_document_in_collection(
                "marketing_reviews",
                {"id": review_id},
                {"_legacy_toko": True, "rating": 5, "status": "unread"}
            )
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # List reviews
        success, resp = self.test(
            "GET /api/dewi/toko/reviews",
            "GET",
            "/api/dewi/toko/reviews",
            200
        )
        if not success:
            return False
        
        # Respond to review
        success, resp = self.test(
            f"PUT /api/dewi/toko/reviews/{review_id}/respond",
            "PUT",
            f"/api/dewi/toko/reviews/{review_id}/respond",
            200,
            data={"response_text": "Thank you for your feedback!"}
        )
        if not success:
            return False
        
        # Verify response in DB
        try:
            doc = self.db.marketing_reviews.find_one({"id": review_id})
            if doc.get("status") != "responded":
                raise AssertionError(f"Review status should be 'responded', got '{doc.get('status')}'")
            if not doc.get("response_text"):
                raise AssertionError("response_text should be set")
            self.log("✓ Review responded with status 'responded'")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Test Accessory Module (P1.A)
        self.log("\n--- Testing Accessory Module (P1.A via rahaza_materials) ---")
        
        # List accessories
        success, resp = self.test(
            "GET /api/acc/items",
            "GET",
            "/api/acc/items",
            200
        )
        if not success:
            return False
        
        initial_count = len(resp)
        self.log(f"✓ Found {initial_count} accessories")
        
        # Create accessory
        acc_code = f"TEST-ACC-{datetime.now().strftime('%H%M%S')}"
        success, resp = self.test(
            "POST /api/acc/items",
            "POST",
            "/api/acc/items",
            201,
            data={
                "code": acc_code,
                "name": "Test Accessory",
                "category": "Test",
                "unit": "pcs",
                "min_stock": 5
            }
        )
        if not success:
            return False
        
        acc_id = resp.get('id')
        self.test_data['acc_id'] = acc_id
        
        # Verify accessory in rahaza_materials
        try:
            self.verify_document_in_collection(
                "rahaza_materials",
                {"id": acc_id},
                {"type": "accessory", "code": acc_code.upper()}
            )
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Receive stock
        success, resp = self.test(
            "POST /api/acc/stock/receive",
            "POST",
            "/api/acc/stock/receive",
            201,
            data={
                "acc_id": acc_id,
                "qty": 10,
                "notes": "Initial stock"
            }
        )
        if not success:
            return False
        
        # Verify stock in rahaza_material_stock
        try:
            doc = self.db.rahaza_material_stock.find_one({"material_id": acc_id})
            if not doc:
                raise AssertionError("Stock record not found in rahaza_material_stock")
            if doc.get("qty") != 10.0:
                raise AssertionError(f"Stock qty should be 10.0, got {doc.get('qty')}")
            self.log("✓ Stock received and recorded in rahaza_material_stock")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Verify movement in rahaza_material_movements
        try:
            doc = self.db.rahaza_material_movements.find_one(
                {"material_id": acc_id, "type": "receive"},
                sort=[("created_at", -1)]
            )
            if not doc:
                raise AssertionError("Movement record not found in rahaza_material_movements")
            if doc.get("domain") != "accessory":
                raise AssertionError(f"Movement domain should be 'accessory', got '{doc.get('domain')}'")
            self.log("✓ Movement recorded in rahaza_material_movements")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Issue stock
        success, resp = self.test(
            "POST /api/acc/stock/issue",
            "POST",
            "/api/acc/stock/issue",
            201,
            data={
                "acc_id": acc_id,
                "qty": 3,
                "notes": "Test issue"
            }
        )
        if not success:
            return False
        
        # Verify stock decreased
        try:
            doc = self.db.rahaza_material_stock.find_one({"material_id": acc_id})
            if doc.get("qty") != 7.0:
                raise AssertionError(f"Stock qty should be 7.0 after issue, got {doc.get('qty')}")
            self.log("✓ Stock issued and decreased to 7.0")
        except AssertionError as e:
            self.log(f"❌ {e}", "FAIL")
            return False
        
        # Get stock movements
        success, resp = self.test(
            "GET /api/acc/stock/movements",
            "GET",
            "/api/acc/stock/movements",
            200
        )
        if not success:
            return False
        
        return True
    
    def print_summary(self):
        """Print test summary"""
        self.log("\n" + "=" * 60)
        self.log("TEST SUMMARY")
        self.log("=" * 60)
        self.log(f"Total Tests: {self.tests_run}")
        self.log(f"Passed: {self.tests_passed}")
        self.log(f"Failed: {self.tests_run - self.tests_passed}")
        
        success_rate = (self.tests_passed / self.tests_run * 100) if self.tests_run > 0 else 0
        self.log(f"Success Rate: {success_rate:.1f}%")
        
        if self.tests_passed == self.tests_run:
            self.log("\n✅ ALL TESTS PASSED!", "SUCCESS")
            return 0
        else:
            self.log(f"\n❌ {self.tests_run - self.tests_passed} TEST(S) FAILED", "FAIL")
            return 1

def main():
    tester = TokoBackendTester()
    
    try:
        tester.run_all_tests()
        return tester.print_summary()
    except KeyboardInterrupt:
        tester.log("\n\nTests interrupted by user", "WARN")
        return 1
    except Exception as e:
        tester.log(f"\n\nFatal error: {e}", "FATAL")
        import traceback
        traceback.print_exc()
        return 1
    finally:
        # Cleanup
        if tester.mongo_client:
            tester.mongo_client.close()

if __name__ == "__main__":
    sys.exit(main())
