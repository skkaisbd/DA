"""
POC: Maklon Orders Consolidation (P1.B)

Membuktikan flow konsolidasi `dewi_maklon_orders` → `dewi_maklon_pos`:
  1. Buat legacy order via DB insert (simulasi data lama)
  2. Run migration script
  3. Verifikasi PO baru ada di dewi_maklon_pos dengan data benar
  4. Verifikasi adapter po_to_legacy_order() menghasilkan shape backward-compatible
  5. Verifikasi find_maklon_record() berhasil resolve baik by old id maupun po_number

Usage:
    cd /app/backend && python migrations/poc_maklon_consolidation.py
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402
from routes._maklon_adapter import (  # noqa: E402
    order_to_po_create_payload, po_to_legacy_order, find_maklon_record,
)

MONGO_URL = os.environ["MONGO_URL"]
DB_NAME = os.environ.get("DB_NAME", "garment_erp")

RUN = uuid.uuid4().hex[:6].upper()


async def main() -> int:
    print(f"=== POC Maklon Consolidation (run={RUN}) ===")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    results = []

    # Cleanup any prior POC residue
    await db.dewi_maklon_orders.delete_many({"order_code": {"$regex": f"^POC-MKLO-{RUN}"}})
    await db.dewi_maklon_pos.delete_many({"po_number": {"$regex": f"^POC-MKLO-{RUN}"}})

    # Ensure a sample client exists
    sample_client = await db.dewi_maklon_clients.find_one({"code": "POC-CLIENT"})
    if not sample_client:
        client_id = str(uuid.uuid4())
        await db.dewi_maklon_clients.insert_one({
            "id": client_id, "code": "POC-CLIENT",
            "name": "POC Maklon Client",
            "pic_name": "Test PIC", "pic_phone": "08123",
            "contract_type": "per_order", "status": "active",
            "rating": 4.5, "created_at": datetime.now(timezone.utc),
            "updated_at": datetime.now(timezone.utc),
        })
    else:
        client_id = sample_client["id"]
    print(f"[OK] Sample client id: {client_id}")

    # US1: Seed 2 legacy orders
    order1_id = str(uuid.uuid4())
    order2_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    legacy_orders = [
        {
            "id": order1_id, "order_code": f"POC-MKLO-{RUN}-001",
            "client_id": client_id, "client_name": "POC Maklon Client",
            "product_name": "Dress Wanita POC", "product_category": "Baju Wanita",
            "qty_ordered": 100,
            "qty_per_size": [
                {"size": "M", "qty": 40},
                {"size": "L", "qty": 60},
            ],
            "colors": ["Hitam", "Navy"],
            "price_per_pcs": 65000.0, "total_value": 6500000.0,
            "order_date": "2026-05-01", "deadline_date": "2026-06-01",
            "status": "confirmed", "progress_percentage": 5,
            "fabric_provided_by": "client", "linked_wo_ids": [],
            "stage_qty": {}, "sync_mode": "manual",
            "notes": "POC legacy order #1",
            "created_at": now, "updated_at": now, "created_by": "poc",
        },
        {
            "id": order2_id, "order_code": f"POC-MKLO-{RUN}-002",
            "client_id": client_id, "client_name": "POC Maklon Client",
            "product_name": "Kemeja Pria POC", "product_category": "Baju Pria",
            "qty_ordered": 50, "qty_per_size": [], "colors": ["Putih"],
            "price_per_pcs": 75000.0, "total_value": 3750000.0,
            "order_date": "2026-05-10", "deadline_date": "2026-06-15",
            "status": "cutting", "progress_percentage": 30,
            "fabric_provided_by": "cv_da", "linked_wo_ids": ["WO-TEST-001"],
            "stage_qty": {"cutting_output": 25}, "sync_mode": "wo",
            "notes": "POC legacy order #2",
            "created_at": now, "updated_at": now, "created_by": "poc",
        },
    ]
    await db.dewi_maklon_orders.insert_many(legacy_orders)
    results.append(("US1: Seed 2 legacy orders", True, f"order1={order1_id}, order2={order2_id}"))
    print("[PASS] US1: Seeded 2 legacy orders")

    # US2: Convert order1 via adapter
    payload = order_to_po_create_payload(legacy_orders[0])
    assert payload["id"] == order1_id, "US2 FAILED: id mismatch"
    assert payload["po_number"] == f"POC-MKLO-{RUN}-001"
    assert payload["total_qty"] == 100
    assert payload["total_value"] == 6500000.0
    assert len(payload["items"]) == 2, f"US2 FAILED: expected 2 items (1 per size), got {len(payload['items'])}"
    assert payload["status"] == "confirmed"
    assert payload["migrated_from"] == "dewi_maklon_orders"
    results.append(("US2: order_to_po_create_payload() with qty_per_size", True,
                    f"po_number={payload['po_number']}, items={len(payload['items'])}"))
    print("[PASS] US2: adapter converts order with qty_per_size to multi-item PO")

    # US3: Convert order2 via adapter (no qty_per_size, single item)
    payload2 = order_to_po_create_payload(legacy_orders[1])
    assert payload2["id"] == order2_id
    assert payload2["total_qty"] == 50
    assert len(payload2["items"]) == 1
    assert payload2["items"][0]["qty"] == 50
    assert payload2["status"] == "in_production"  # legacy 'cutting' → PO 'in_production'
    assert payload2["items"][0]["wo_id"] == "WO-TEST-001"
    results.append(("US3: order_to_po_create_payload() without qty_per_size", True,
                    f"items={len(payload2['items'])}, wo_id mapped"))
    print("[PASS] US3: adapter handles single-item order with linked_wo_ids")

    # US4: Insert both POs to dewi_maklon_pos
    for pl in (payload, payload2):
        await db.dewi_maklon_pos.update_one({"id": pl["id"]}, {"$set": pl}, upsert=True)
    pos_count = await db.dewi_maklon_pos.count_documents({
        "migrated_from": "dewi_maklon_orders",
        "po_number": {"$regex": f"^POC-MKLO-{RUN}"},
    })
    assert pos_count == 2, f"US4 FAILED: expected 2 POs, got {pos_count}"
    results.append(("US4: Insert 2 POs to dewi_maklon_pos", True, f"pos_count={pos_count}"))
    print("[PASS] US4: 2 POs inserted to dewi_maklon_pos")

    # US5: po_to_legacy_order() reverse conversion (for client portal back-compat)
    inserted_po1 = await db.dewi_maklon_pos.find_one({"id": order1_id})
    legacy_view = po_to_legacy_order(inserted_po1)
    assert legacy_view["id"] == order1_id
    assert legacy_view["order_code"] == f"POC-MKLO-{RUN}-001"
    assert legacy_view["qty_ordered"] == 100
    assert legacy_view["status"] == "confirmed"
    assert legacy_view["_source"] == "dewi_maklon_pos"
    assert len(legacy_view["qty_per_size"]) == 2
    results.append(("US5: po_to_legacy_order() round-trip", True,
                    f"qty_ordered={legacy_view['qty_ordered']}, qty_per_size_count={len(legacy_view['qty_per_size'])}"))
    print("[PASS] US5: adapter round-trip preserves data shape")

    # US6: find_maklon_record() resolves by id (from both collections)
    record1 = await find_maklon_record(db, order1_id)
    assert record1 is not None, "US6 FAILED: not found by id"
    assert record1["_collection"] == "dewi_maklon_pos", f"Expected pos, got {record1['_collection']}"
    # Search by po_number
    record2 = await find_maklon_record(db, f"POC-MKLO-{RUN}-002")
    assert record2 is not None, "US6 FAILED: not found by po_number"
    assert record2["_collection"] == "dewi_maklon_pos"
    results.append(("US6: find_maklon_record() resolves id + po_number", True,
                    "both resolved from dewi_maklon_pos"))
    print("[PASS] US6: find_maklon_record() resolves from both id & po_number")

    # Cleanup
    await db.dewi_maklon_orders.delete_many({"order_code": {"$regex": f"^POC-MKLO-{RUN}"}})
    await db.dewi_maklon_pos.delete_many({"po_number": {"$regex": f"^POC-MKLO-{RUN}"}})
    print("\n[CLEANUP] Removed POC residue")

    print("\n=== POC RESULTS ===")
    for name, ok, info in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name} ({info})")
    all_pass = all(ok for _, ok, _ in results)
    print()
    if all_pass:
        print("POC MAKLON CONSOLIDATION: SUCCESS")
        return 0
    print("POC MAKLON CONSOLIDATION: FAILED")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
