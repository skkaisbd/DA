"""
POC — Fase 3b: Marketing/Toko link variant_id ↔ Finished Goods stock (SKU bridge).

Decisions (user-approved):
  1a) Bridge by SKU: rahaza_model_variants.sku == rahaza_materials.code (type='fg')
      -> qty from rahaza_material_stock.
  2b) Auto-override: catalog item stock_quantity := FG available (onhand - reserved) on sync.
  3a) Reservation out of scope (handled by fulfillment).

Fixtures (master data) inserted directly via Mongo; the FEATURE endpoints are exercised
via real HTTP:
  - POST /api/marketing/catalogs/{cid}/items         (create item w/ variant_id -> stores variant_sku)
  - GET  /api/marketing/catalogs/{cid}/items/{id}/fg-stock   (peek live FG stock)
  - PUT  /api/marketing/catalogs/{cid}/items/{id}/sync-fg-stock  (single auto-override sync)
  - POST /api/marketing/catalogs/{cid}/sync-from-wms  (bulk sync incl. variant items)
"""
import asyncio
import os
import sys
import uuid
from datetime import datetime, timezone

import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE = "http://localhost:8001/api"
ADMIN = {"email": "admin@garment.com", "password": "Admin@123"}
MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DBN = os.environ.get("DB_NAME", "test_database")

MODEL_ID = "poc3b-model-1"
MODEL_CODE = "POC-TS"
VARIANT_ID = "poc3b-variant-1"
VARIANT_SKU = "POC-TS-BLK-M"
FG_ID = "poc3b-fg-1"
ACC_ID = "poc3b-acc-1"
CAT_ID = "poc3b-cat-1"

passed, failed = [], []
def ok(m): passed.append(m); print(f"  [PASS] {m}")
def bad(m): failed.append(m); print(f"  [FAIL] {m}")
def now(): return datetime.now(timezone.utc)


async def seed_fixtures(reserved=20.0, onhand=120.0):
    c = AsyncIOMotorClient(MONGO)
    db = c[DBN]
    # Model (internal master product)
    await db.rahaza_models.update_one({"id": MODEL_ID}, {"$set": {
        "id": MODEL_ID, "code": MODEL_CODE, "name": "POC Kaos Toko", "active": True,
        "created_at": now(),
    }}, upsert=True)
    # Internal variant with a fixed SKU
    await db.rahaza_model_variants.update_one({"id": VARIANT_ID}, {"$set": {
        "id": VARIANT_ID, "model_id": MODEL_ID, "sku": VARIANT_SKU,
        "size_id": "poc3b-sz-m", "color_id": "poc3b-cl-blk",
        "color_name": "Black", "color_code": "BLK", "size_code": "M",
        "active": True, "created_at": now(),
    }}, upsert=True)
    # FG material whose CODE matches the variant SKU (the bridge)
    await db.rahaza_materials.update_one({"id": FG_ID}, {"$set": {
        "id": FG_ID, "code": VARIANT_SKU, "sku": VARIANT_SKU, "name": "FG POC Kaos Black M",
        "type": "fg", "active": True, "created_at": now(),
    }}, upsert=True)
    # FG physical stock (SSOT skema stok): onhand + reserved
    await db.rahaza_material_stock.delete_many({"material_id": FG_ID})
    await db.rahaza_material_stock.insert_one({
        "id": str(uuid.uuid4()), "material_id": FG_ID, "location_id": "poc3b-loc-1",
        "qty": onhand, "reserved_quantity": reserved, "updated_at": now(),
    })
    # Marketing account + catalog (fixtures)
    await db.marketing_platform_accounts.update_one({"id": ACC_ID}, {"$set": {
        "id": ACC_ID, "account_code": "POC-SHOP", "account_name": "POC Shop",
        "platform": "shopee", "active": True, "created_at": now(),
    }}, upsert=True)
    await db.marketing_catalogs.update_one({"id": CAT_ID}, {"$set": {
        "id": CAT_ID, "account_id": ACC_ID, "platform": "shopee", "name": "Katalog POC 3b",
        "is_active": True, "created_at": now(),
    }}, upsert=True)
    # clean prior items
    await db.marketing_catalog_items.delete_many({"catalog_id": CAT_ID})
    c.close()


async def set_fg_stock(onhand, reserved):
    c = AsyncIOMotorClient(MONGO)
    db = c[DBN]
    await db.rahaza_material_stock.update_one(
        {"material_id": FG_ID},
        {"$set": {"qty": onhand, "reserved_quantity": reserved, "updated_at": now()}},
    )
    c.close()


def login():
    r = requests.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    r.raise_for_status()
    return r.json()["token"]


def main():
    asyncio.run(seed_fixtures(reserved=20.0, onhand=120.0))
    tok = login()
    H = {"Authorization": f"Bearer {tok}"}
    ok("admin login + fixtures seeded (onhand=120, reserved=20 -> available=100)")

    # 1. Create catalog item linked to variant_id (distinct item sku to prove bridge uses variant_sku)
    r = requests.post(f"{BASE}/marketing/catalogs/{CAT_ID}/items", headers=H, json={
        "sku": "TOKO-KAOS-BLK-M", "name": "Kaos Toko Hitam M", "price": 95000,
        "variant_id": VARIANT_ID, "stock_quantity": 0,
    }, timeout=30)
    if r.status_code in (200, 201):
        item = r.json().get("item", {})
        item_id = item.get("id")
        if item.get("variant_id") == VARIANT_ID and item.get("variant_sku") == VARIANT_SKU:
            ok(f"item created w/ variant_id link, variant_sku='{item.get('variant_sku')}'")
        else:
            bad(f"item variant fields wrong: variant_id={item.get('variant_id')} variant_sku={item.get('variant_sku')}")
    else:
        bad(f"create item failed {r.status_code}: {r.text[:200]}")
        print("\nSUMMARY: aborted")
        return 1

    # 2. Peek FG stock (no mutation)
    r = requests.get(f"{BASE}/marketing/catalogs/{CAT_ID}/items/{item_id}/fg-stock", headers=H, timeout=30)
    if r.status_code == 200:
        g = r.json()
        if g["found"] and g["link_type"] == "variant_sku" and g["onhand"] == 120 and g["reserved"] == 20 and g["available"] == 100:
            ok(f"peek fg-stock: onhand=120 reserved=20 available=100 (link_type=variant_sku)")
        else:
            bad(f"peek fg-stock wrong: {g}")
        if g.get("catalog_stock_quantity") == 0 and g.get("in_sync") is False:
            ok("peek shows item currently NOT in sync (catalog stock=0)")
        else:
            bad(f"peek in_sync/catalog stock unexpected: {g.get('catalog_stock_quantity')} in_sync={g.get('in_sync')}")
    else:
        bad(f"peek fg-stock failed {r.status_code}: {r.text[:200]}")

    # 3. Single sync (auto-override) -> stock should become available=100
    r = requests.put(f"{BASE}/marketing/catalogs/{CAT_ID}/items/{item_id}/sync-fg-stock", headers=H, timeout=30)
    if r.status_code == 200:
        s = r.json()
        if s["stock_quantity"] == 100 and s["link_type"] == "variant_sku" and s["fg_available"] == 100:
            ok("single sync-fg-stock: stock_quantity auto-overridden to 100 (available)")
        else:
            bad(f"single sync wrong: {s}")
    else:
        bad(f"single sync failed {r.status_code}: {r.text[:200]}")

    # 4. Change FG stock, then BULK sync-from-wms should update variant item
    asyncio.run(set_fg_stock(onhand=80.0, reserved=0.0))
    r = requests.post(f"{BASE}/marketing/catalogs/{CAT_ID}/sync-from-wms", headers=H, timeout=60)
    if r.status_code == 200:
        b = r.json()
        if b.get("synced_variant", 0) >= 1:
            ok(f"bulk sync-from-wms processed variant item (synced_variant={b.get('synced_variant')})")
        else:
            bad(f"bulk sync did NOT process variant item: {b}")
    else:
        bad(f"bulk sync failed {r.status_code}: {r.text[:200]}")

    # verify item stock now 80
    r = requests.get(f"{BASE}/marketing/catalogs/{CAT_ID}/items/{item_id}/fg-stock", headers=H, timeout=30)
    if r.status_code == 200:
        g = r.json()
        if g["available"] == 80 and g["catalog_stock_quantity"] == 80 and g["in_sync"] is True:
            ok("after bulk sync: item stock=80 and in_sync=true")
        else:
            bad(f"post-bulk state wrong: available={g.get('available')} catalog={g.get('catalog_stock_quantity')} in_sync={g.get('in_sync')}")
    else:
        bad(f"final peek failed {r.status_code}")

    # 5. Negative: item with variant_sku but NO FG master -> sync should 404 gracefully
    #    (create a variant+item whose SKU has no FG material)
    async def _seed_orphan():
        c = AsyncIOMotorClient(MONGO); db = c[DBN]
        await db.rahaza_model_variants.update_one({"id": "poc3b-variant-orphan"}, {"$set": {
            "id": "poc3b-variant-orphan", "model_id": MODEL_ID, "sku": "POC-TS-NOFG-XL",
            "size_id": "poc3b-sz-xl", "color_id": "poc3b-cl-nofg",
            "color_name": "NoFG", "color_code": "NOFG", "size_code": "XL", "active": True, "created_at": now(),
        }}, upsert=True)
        c.close()
    asyncio.run(_seed_orphan())
    r = requests.post(f"{BASE}/marketing/catalogs/{CAT_ID}/items", headers=H, json={
        "sku": "TOKO-ORPHAN", "name": "Kaos Tanpa FG", "price": 50000,
        "variant_id": "poc3b-variant-orphan", "stock_quantity": 0,
    }, timeout=30)
    orphan_id = r.json().get("item", {}).get("id") if r.status_code in (200, 201) else None
    if orphan_id:
        r2 = requests.put(f"{BASE}/marketing/catalogs/{CAT_ID}/items/{orphan_id}/sync-fg-stock", headers=H, timeout=30)
        if r2.status_code == 404:
            ok("orphan variant (no FG master) -> sync returns 404 gracefully")
        else:
            bad(f"orphan sync should 404, got {r2.status_code}: {r2.text[:150]}")
    else:
        bad("could not create orphan item for negative test")

    print("\n================= SUMMARY =================")
    print(f"PASSED: {len(passed)}  FAILED: {len(failed)}")
    for f in failed:
        print(f"  FAIL: {f}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
