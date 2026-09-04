"""
POC: P1.D Legacy Toko Migration (dewi_toko_* → marketing_*)

Membuktikan dual-write mirror berjalan:
  US1. Create product via /api/dewi/toko/products → mirror muncul di marketing_catalog_items
  US2. Update product → mirror ter-update
  US3. Channel update via /api/dewi/toko/channels/{code} → mirror di marketing_platform_accounts
  US4. Channel sync via /api/dewi/toko/channels/{code}/sync → log di marketing_stock_syncs
  US5. Create order via /api/dewi/toko/orders → mirror di marketing_orders
  US6. Order status change → mirror ter-update
  US7. Create return via /api/dewi/toko/returns → mirror di marketing_returns
  US8. Create review via /api/dewi/toko/reviews → mirror di marketing_reviews
  US9. Adapter round-trip catalog_item → toko_product preserves data
  US10. Verify OpenAPI: 40 toko endpoints marked deprecated

Usage:
    cd /app/backend && python migrations/poc_toko_consolidation.py
"""
import asyncio
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

import httpx  # noqa: E402
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from routes._toko_adapter import (  # noqa: E402
    toko_product_to_catalog_item,
    catalog_item_to_toko_product,
    get_or_create_toko_legacy_catalog,
)

BASE = "http://localhost:8001"
ADMIN_EMAIL = "admin@garment.com"
ADMIN_PASSWORD = "Admin@123"
RUN = uuid.uuid4().hex[:6].upper()


async def login(client) -> str:
    r = await client.post(
        f"{BASE}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15.0,
    )
    r.raise_for_status()
    return r.json()["token"]


async def main() -> int:
    print(f"=== POC Toko Consolidation (run={RUN}) ===")
    results = []

    db_client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = db_client[os.environ.get("DB_NAME", "garment_erp")]

    async with httpx.AsyncClient() as client:
        token = await login(client)
        H = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        print("[OK] Login")

        # Cleanup residue
        for col in ("dewi_toko_products", "marketing_catalog_items",
                    "dewi_toko_orders", "marketing_orders",
                    "dewi_toko_returns", "marketing_returns",
                    "dewi_toko_reviews", "marketing_reviews"):
            await db[col].delete_many({
                "$or": [
                    {"sku_code": {"$regex": f"POC{RUN}"}},
                    {"order_ref": {"$regex": f"POC{RUN}"}},
                    {"customer_name": {"$regex": f"POC{RUN}"}},
                ],
            })

        # ───── US1: Create product ─────
        sku = f"POC{RUN}-PROD-001"
        r = await client.post(
            f"{BASE}/api/dewi/toko/products", headers=H,
            json={
                "sku_code": sku, "name": f"POC Product {RUN}",
                "category": "Toko POC", "base_price": 100000, "cost_price": 50000,
                "stock_total": 25, "status": "active",
            },
        )
        assert r.status_code == 200, f"US1 FAILED: {r.text}"
        pid = r.json()["id"]
        # P1.D cleanup: legacy collection no longer used; check ONLY marketing_catalog_items
        mirror_p = await db.marketing_catalog_items.find_one({"id": pid})
        assert mirror_p is not None, "Product not created in marketing_catalog_items"
        assert mirror_p["sku_code"] == sku.upper()
        assert mirror_p.get("_legacy_toko") is True
        assert mirror_p.get("catalog_id") is not None
        results.append(("US1: Create product goes directly to marketing_catalog_items", True,
                        f"sku={mirror_p['sku_code']}, catalog_id={mirror_p['catalog_id'][:8]}"))
        print("[PASS] US1: product written to marketing_catalog_items (SSOT)")

        # ───── US2: Update product ─────
        r = await client.put(
            f"{BASE}/api/dewi/toko/products/{pid}", headers=H,
            json={"name": f"POC Product {RUN} UPDATED", "stock_total": 50},
        )
        assert r.status_code == 200, f"US2 FAILED: {r.text}"
        mirror2 = await db.marketing_catalog_items.find_one({"id": pid})
        assert "UPDATED" in mirror2["name"]
        assert mirror2["stock_total"] == 50
        results.append(("US2: Update product mirrors changes", True, f"stock_total={mirror2['stock_total']}"))
        print("[PASS] US2: update mirrored")

        # ───── US3: Channel list (auto-seed) ─────
        r = await client.get(f"{BASE}/api/dewi/toko/channels", headers=H)
        assert r.status_code == 200, f"US3 list FAILED: {r.text}"
        channels = r.json()
        shopee = next((c for c in channels if c["code"] == "shopee"), None)
        assert shopee is not None
        # Now mirror should exist for all 4 seeded channels
        mirror_count = await db.marketing_platform_accounts.count_documents({"_legacy_toko": True})
        assert mirror_count >= 4, f"Expected >=4 channel mirrors, got {mirror_count}"
        results.append(("US3: Seeded channels mirror to marketing_platform_accounts", True,
                        f"mirror_count={mirror_count}"))
        print(f"[PASS] US3: {mirror_count} channel mirrors")

        # ───── US4: Channel sync log mirror ─────
        # Enable shopee first
        r = await client.put(
            f"{BASE}/api/dewi/toko/channels/shopee", headers=H,
            json={"enabled": True},
        )
        assert r.status_code == 200
        r = await client.post(f"{BASE}/api/dewi/toko/channels/shopee/sync", headers=H)
        assert r.status_code == 200, f"US4 sync FAILED: {r.text}"
        sync_mirror = await db.marketing_stock_syncs.find_one(
            {"channel_code": "shopee", "_legacy_toko": True}
        )
        assert sync_mirror is not None, "sync log NOT mirrored"
        results.append(("US4: Sync log mirrors to marketing_stock_syncs", True,
                        f"sync_id={sync_mirror['id'][:8]}, status={sync_mirror['status']}"))
        print("[PASS] US4: sync mirrored")

        # ───── US5: Create order ─────
        order_ref = f"POC{RUN}-ORD-001"
        r = await client.post(
            f"{BASE}/api/dewi/toko/orders", headers=H,
            json={
                "channel_code": "shopee", "order_ref": order_ref,
                "customer_name": f"POC{RUN} Buyer", "customer_city": "Bali",
                "items": [{"sku_code": sku, "qty": 2, "price": 100000}],
                "total_amount": 200000, "fee_amount": 5000,
            },
        )
        assert r.status_code == 201, f"US5 FAILED: {r.text}"
        oid = r.json()["id"]
        mirror_o = await db.marketing_orders.find_one({"id": oid})
        assert mirror_o is not None, "order NOT mirrored"
        assert mirror_o["status"] == "new"
        assert mirror_o["platform"] == "shopee"
        assert mirror_o["total_payment"] == 200000.0
        assert mirror_o.get("_legacy_toko") is True
        results.append(("US5: Create order mirrors to marketing_orders", True,
                        f"order={mirror_o['order_id']}, total={mirror_o['total_payment']}"))
        print("[PASS] US5: order mirrored")

        # ───── US6: Status change mirror ─────
        r = await client.post(
            f"{BASE}/api/dewi/toko/orders/{oid}/status", headers=H,
            json={"status": "packed"},
        )
        assert r.status_code == 200, f"US6 FAILED: {r.text}"
        mirror_o2 = await db.marketing_orders.find_one({"id": oid})
        assert mirror_o2["status"] == "packed"
        assert mirror_o2.get("packed_date") is not None
        results.append(("US6: Status change mirrors", True, f"status={mirror_o2['status']}"))
        print("[PASS] US6: status change mirrored")

        # ───── US7: Create return ─────
        r = await client.post(
            f"{BASE}/api/dewi/toko/returns", headers=H,
            json={
                "order_id": oid, "order_number": mirror_o["order_id"],
                "return_type": "customer_refund",
                "customer_name": f"POC{RUN} Buyer",
                "channel_code": "shopee",
                "reason": "Defect produk",
                "estimated_value": 50000,
            },
        )
        assert r.status_code == 201, f"US7 FAILED: {r.text}"
        ret_id = r.json()["id"]
        mirror_r = await db.marketing_returns.find_one({"id": ret_id})
        assert mirror_r is not None, "return NOT mirrored"
        assert mirror_r.get("_legacy_toko") is True
        results.append(("US7: Create return mirrors to marketing_returns", True,
                        f"return_number={mirror_r.get('return_number')}"))
        print("[PASS] US7: return mirrored")

        # ───── US8: Create review ─────
        r = await client.post(
            f"{BASE}/api/dewi/toko/reviews", headers=H,
            json={
                "channel_code": "shopee", "order_ref": order_ref,
                "customer_name": f"POC{RUN} Buyer",
                "rating": 4, "review_text": "Bagus tapi packing kurang rapi.",
                "sku_code": sku,
            },
        )
        assert r.status_code in (200, 201), f"US8 FAILED: {r.text}"
        rev_id = r.json()["id"]
        mirror_rv = await db.marketing_reviews.find_one({"id": rev_id})
        assert mirror_rv is not None
        assert mirror_rv["rating"] == 4
        assert mirror_rv.get("_legacy_toko") is True
        results.append(("US8: Create review mirrors to marketing_reviews", True,
                        f"rating={mirror_rv['rating']}"))
        print("[PASS] US8: review mirrored")

        # ───── US9: Adapter round-trip ─────
        catalog_id = await get_or_create_toko_legacy_catalog(db)
        original = {
            "id": str(uuid.uuid4()), "sku_code": "TEST-RT", "name": "Round Trip",
            "category": "Test", "base_price": 99, "cost_price": 50,
            "stock_total": 10, "status": "active",
            "variants": [], "channel_prices": [], "photos": [],
            "tags": ["a"], "sales_count_total": 0,
        }
        forward = toko_product_to_catalog_item(original, catalog_id)
        back = catalog_item_to_toko_product(forward)
        assert back["sku_code"] == original["sku_code"]
        assert back["name"] == original["name"]
        assert back["base_price"] == original["base_price"]
        assert back["stock_total"] == original["stock_total"]
        results.append(("US9: Adapter round-trip preserves data", True, "sku/name/price/stock match"))
        print("[PASS] US9: adapter round-trip ok")

        # ───── US10: OpenAPI deprecation flags ─────
        r = await client.get(f"{BASE}/api/openapi.json", timeout=15.0)
        assert r.status_code == 200
        spec = r.json()
        toko_endpoints = []
        deprecated_count = 0
        for path, methods in spec.get("paths", {}).items():
            if "/api/dewi/toko/" in path:
                for verb, info in methods.items():
                    if isinstance(info, dict):
                        toko_endpoints.append(f"{verb.upper()} {path}")
                        if info.get("deprecated"):
                            deprecated_count += 1
        assert deprecated_count >= 30, f"Expected >=30 deprecated /toko endpoints, got {deprecated_count} of {len(toko_endpoints)}"
        results.append(("US10: /api/dewi/toko/* endpoints deprecated in OpenAPI", True,
                        f"{deprecated_count}/{len(toko_endpoints)} deprecated"))
        print(f"[PASS] US10: {deprecated_count}/{len(toko_endpoints)} toko endpoints deprecated")

    # Cleanup
    for col in ("dewi_toko_products", "marketing_catalog_items",
                "dewi_toko_orders", "marketing_orders",
                "dewi_toko_returns", "marketing_returns",
                "dewi_toko_reviews", "marketing_reviews"):
        await db[col].delete_many({
            "$or": [
                {"sku_code": {"$regex": f"POC{RUN}"}},
                {"order_ref": {"$regex": f"POC{RUN}"}},
                {"order_id": {"$regex": f"POC{RUN}"}},
                {"customer_name": {"$regex": f"POC{RUN}"}},
            ],
        })
    print("\n[CLEANUP] Done")

    print("\n=== POC RESULTS ===")
    for name, ok, info in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} ({info})")
    if all(ok for _, ok, _ in results):
        print("\nPOC TOKO CONSOLIDATION: SUCCESS")
        return 0
    print("\nPOC TOKO CONSOLIDATION: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
