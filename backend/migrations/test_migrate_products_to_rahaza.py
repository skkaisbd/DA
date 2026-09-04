"""Self-test for migrate_products_to_rahaza.py against a SCRATCH DB.
Seeds sample legacy products/product_variants, runs the migration in a scratch
DB, and asserts correctness + idempotency. Does NOT touch the real DB.
"""
import asyncio, os, sys, subprocess, uuid
from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorClient

MONGO = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
SCRATCH = "migration_selftest_db"


def now():
    return datetime.now(timezone.utc)


async def seed(db):
    await db.products.delete_many({})
    await db.product_variants.delete_many({})
    await db.rahaza_models.delete_many({})
    await db.rahaza_model_variants.delete_many({})
    await db.rahaza_colors.delete_many({})
    await db.rahaza_sizes.delete_many({})

    # sizes master (like live seed)
    for i, code in enumerate(["S", "M", "L", "XL", "XXL"], start=1):
        await db.rahaza_sizes.insert_one({"id": str(uuid.uuid4()), "code": code, "name": code,
                                          "order_seq": i, "active": True, "created_at": now(), "updated_at": now()})
    # a couple of standard colors already present (to test REUSE-by-name)
    await db.rahaza_colors.insert_one({"id": str(uuid.uuid4()), "code": "NVY", "name": "Navy",
                                       "hex": "#1E3A5F", "order_seq": 4, "active": True,
                                       "created_at": now(), "updated_at": now()})

    p1 = str(uuid.uuid4()); p2 = str(uuid.uuid4())
    await db.products.insert_one({"id": p1, "product_code": "swtr-01", "product_name": "Basic Sweater",
                                  "cmt_price": 25000, "selling_price": 90000, "status": "active", "created_at": now()})
    await db.products.insert_one({"id": p2, "product_code": "", "product_name": "Hoodie Zip",
                                  "cmt_price": 40000, "selling_price": 150000, "status": "inactive", "created_at": now()})
    # variants
    await db.product_variants.insert_one({"id": str(uuid.uuid4()), "product_id": p1, "size": "M",
                                          "color": "Navy", "sku": "", "created_at": now()})   # reuse NVY, derive sku
    await db.product_variants.insert_one({"id": str(uuid.uuid4()), "product_id": p1, "size": "L",
                                          "color": "Teal Custom", "sku": "SWTR-01-TEA-L", "created_at": now()})  # new color, explicit sku
    await db.product_variants.insert_one({"id": str(uuid.uuid4()), "product_id": p2, "size": "XXXL",
                                          "color": "Navy", "sku": "", "created_at": now()})   # new size XXXL, reuse NVY
    return p1, p2


def run_migration(execute=False):
    env = dict(os.environ, DB_NAME=SCRATCH)
    cmd = [sys.executable, "/app/backend/migrations/migrate_products_to_rahaza.py"]
    if execute:
        cmd.append("--execute")
    r = subprocess.run(cmd, env=env, capture_output=True, text=True)
    return r.stdout + r.stderr


async def main():
    client = AsyncIOMotorClient(MONGO)
    db = client[SCRATCH]
    ok = True
    try:
        await seed(db)
        print("--- DRY-RUN ---")
        print(run_migration(execute=False))
        # dry-run must NOT write
        assert await db.rahaza_models.count_documents({}) == 0, "dry-run wrote models!"
        assert await db.rahaza_model_variants.count_documents({}) == 0, "dry-run wrote variants!"

        print("--- EXECUTE #1 ---")
        print(run_migration(execute=True))
        m = await db.rahaza_models.count_documents({})
        v = await db.rahaza_model_variants.count_documents({})
        c = await db.rahaza_colors.count_documents({})
        s = await db.rahaza_sizes.count_documents({})
        print(f"after execute: models={m} variants={v} colors={c} sizes={s}")
        assert m == 2, f"expected 2 models, got {m}"
        assert v == 3, f"expected 3 variants, got {v}"
        assert c == 2, f"expected 2 colors (Navy reused + Teal Custom created), got {c}"
        assert s == 6, f"expected 6 sizes (5 + XXXL), got {s}"

        # verify SKU derivation + color reuse
        nvy_var = await db.rahaza_model_variants.find_one({"model_code": "SWTR-01", "size_code": "M"})
        assert nvy_var and nvy_var["sku"] == "SWTR-01-NVY-M", f"bad derived sku: {nvy_var and nvy_var.get('sku')}"
        assert nvy_var["color_code"] == "NVY", "Navy color not reused (should map to existing NVY)"
        teal_var = await db.rahaza_model_variants.find_one({"sku": "SWTR-01-TEA-L"})
        assert teal_var and teal_var["color_name"] == "Teal Custom", "explicit SKU/new color failed"
        hoodie = await db.rahaza_models.find_one({"name": "Hoodie Zip"})
        assert hoodie and hoodie["active"] is False, "inactive product should map active=False"
        xxxl = await db.rahaza_sizes.find_one({"code": "XXXL"})
        assert xxxl, "new size XXXL not created"

        print("--- EXECUTE #2 (idempotency) ---")
        out2 = run_migration(execute=True)
        print(out2)
        m2 = await db.rahaza_models.count_documents({})
        v2 = await db.rahaza_model_variants.count_documents({})
        c2 = await db.rahaza_colors.count_documents({})
        s2 = await db.rahaza_sizes.count_documents({})
        assert (m2, v2, c2, s2) == (m, v, c, s), f"NOT idempotent: {(m2,v2,c2,s2)} != {(m,v,c,s)}"
        assert "created:    0" in out2, "idempotent re-run should create 0"
        print("\n✅ ALL ASSERTIONS PASSED — migration logic correct + idempotent")
    except AssertionError as e:
        ok = False
        print(f"\n❌ ASSERTION FAILED: {e}")
    finally:
        await client.drop_database(SCRATCH)
        print(f"(scratch db '{SCRATCH}' dropped)")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    asyncio.run(main())
