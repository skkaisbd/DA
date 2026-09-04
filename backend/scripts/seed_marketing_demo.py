"""
Seed Marketing Demo Data
========================
Populate marketing portal with realistic demo data for:
- Platform accounts (Shopee, TikTok, Tokopedia, Instagram, Lazada)
- Daily sales data (last 30 days, per platform)
- Marketing orders
- KOL creators
- Catalog items
- Monthly targets

Usage: python -m backend.scripts.seed_marketing_demo
       OR cd /app/backend && python scripts/seed_marketing_demo.py
"""
import asyncio
import sys
import os
import uuid
import random
from datetime import datetime, timezone, timedelta

# Ensure backend module is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_db


def utc_now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or utc_now()).isoformat()


PLATFORMS_SEED = [
    {
        "account_code": "SHP-001",
        "account_name": "Dewi Aditya Official - Shopee",
        "platform": "shopee",
        "platform_url": "https://shopee.co.id/dewiaditya",
        "pic_name": "Sari Marketing",
        "pic_email": "sari@dewiaditya.id",
        "status": "active",
        "follower_count": 12500,
        "rating": 4.8,
        "monthly_target": 50000000,
    },
    {
        "account_code": "TT-001",
        "account_name": "Dewi Aditya - TikTok Shop",
        "platform": "tiktok",
        "platform_url": "https://tiktok.com/@dewiaditya.official",
        "pic_name": "Rina Marketing",
        "pic_email": "rina@dewiaditya.id",
        "status": "active",
        "follower_count": 25800,
        "rating": 4.7,
        "monthly_target": 75000000,
    },
    {
        "account_code": "TKP-001",
        "account_name": "Dewi Aditya Official Store - Tokopedia",
        "platform": "tokopedia",
        "platform_url": "https://tokopedia.com/dewiaditya",
        "pic_name": "Dewi Marketing",
        "pic_email": "dewi.m@dewiaditya.id",
        "status": "active",
        "follower_count": 8900,
        "rating": 4.9,
        "monthly_target": 40000000,
    },
    {
        "account_code": "IG-001",
        "account_name": "@dewiaditya.id - Instagram",
        "platform": "instagram",
        "platform_url": "https://instagram.com/dewiaditya.id",
        "pic_name": "Putri Content",
        "pic_email": "putri@dewiaditya.id",
        "status": "active",
        "follower_count": 45200,
        "rating": 0,
        "monthly_target": 30000000,
    },
    {
        "account_code": "LZ-001",
        "account_name": "Dewi Aditya - Lazada",
        "platform": "lazada",
        "platform_url": "https://lazada.co.id/shop/dewi-aditya",
        "pic_name": "Sari Marketing",
        "pic_email": "sari@dewiaditya.id",
        "status": "active",
        "follower_count": 5600,
        "rating": 4.6,
        "monthly_target": 25000000,
    },
]


CATALOG_SEED = [
    {"sku": "DA-DRESS-001", "name": "Floral Maxi Dress", "category": "Dress",   "color": "Pink",   "size": "M", "price": 285000, "cost": 95000},
    {"sku": "DA-DRESS-002", "name": "Casual Wrap Dress",  "category": "Dress",   "color": "Black",  "size": "L", "price": 225000, "cost": 78000},
    {"sku": "DA-BLUSE-001", "name": "Office Blouse",      "category": "Blouse",  "color": "White",  "size": "S", "price": 175000, "cost": 60000},
    {"sku": "DA-BLUSE-002", "name": "Silk Blouse Premium","category": "Blouse",  "color": "Beige",  "size": "M", "price": 320000, "cost": 110000},
    {"sku": "DA-PANTS-001", "name": "High-Waist Trousers","category": "Pants",   "color": "Black",  "size": "M", "price": 245000, "cost": 85000},
    {"sku": "DA-SKIRT-001", "name": "A-Line Mini Skirt",  "category": "Skirt",   "color": "Navy",   "size": "S", "price": 195000, "cost": 68000},
    {"sku": "DA-KAOS-001",  "name": "Basic Tee",          "category": "T-Shirt", "color": "White",  "size": "All","price": 125000, "cost": 38000},
    {"sku": "DA-KAOS-002",  "name": "Graphic Tee",        "category": "T-Shirt", "color": "Black",  "size": "All","price": 145000, "cost": 45000},
    {"sku": "DA-OUTER-001", "name": "Denim Jacket",       "category": "Outer",   "color": "Blue",   "size": "M", "price": 385000, "cost": 145000},
    {"sku": "DA-HIJAB-001", "name": "Plain Hijab Silk",   "category": "Hijab",   "color": "Maroon", "size": "All","price": 95000, "cost": 28000},
]


KOL_SEED = [
    {"name": "Bella Anggraini",   "handle": "@bellaanggrn",        "platform": "tiktok",   "followers": 125000, "category": "Fashion",  "rate_card": 2500000, "tier": "Macro"},
    {"name": "Dinda Salsabila",   "handle": "@dindasalsa_id",      "platform": "instagram","followers": 89000,  "category": "Lifestyle","rate_card": 1800000, "tier": "Macro"},
    {"name": "Putri Ramadhani",   "handle": "@putri.r",            "platform": "tiktok",   "followers": 45000,  "category": "Fashion",  "rate_card": 800000,  "tier": "Mid"},
    {"name": "Sari Wulandari",    "handle": "@sariwulan",          "platform": "instagram","followers": 32000,  "category": "Fashion",  "rate_card": 650000,  "tier": "Mid"},
    {"name": "Rina Permatasari",  "handle": "@rinaperm",           "platform": "tiktok",   "followers": 18000,  "category": "Fashion",  "rate_card": 350000,  "tier": "Micro"},
    {"name": "Maya Kusumawati",   "handle": "@mayakusuma_outfit",  "platform": "instagram","followers": 12500,  "category": "Lifestyle","rate_card": 250000,  "tier": "Micro"},
]


async def seed_platform_accounts(db):
    print("Seeding platform accounts...")
    inserted = 0
    for p in PLATFORMS_SEED:
        exists = await db.marketing_platform_accounts.find_one({"account_code": p["account_code"]})
        if exists:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            **p,
            "created_at": iso(),
            "updated_at": iso(),
        }
        await db.marketing_platform_accounts.insert_one(doc)
        inserted += 1
    print(f"  Inserted {inserted} platform accounts (skipped {len(PLATFORMS_SEED) - inserted} existing)")


async def seed_catalog(db):
    print("Seeding catalog items...")
    inserted = 0
    for c in CATALOG_SEED:
        exists = await db.marketing_catalog_items.find_one({"sku": c["sku"]})
        if exists:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            **c,
            "status": "active",
            "stock_qty": random.randint(20, 200),
            "created_at": iso(),
            "updated_at": iso(),
        }
        await db.marketing_catalog_items.insert_one(doc)
        inserted += 1
    print(f"  Inserted {inserted} catalog items (skipped {len(CATALOG_SEED) - inserted} existing)")


async def seed_kol_creators(db):
    print("Seeding KOL creators...")
    # Assign creators to real accounts + set a demo cost_config (editable).
    accounts = await db.marketing_platform_accounts.find({}, {"_id": 0, "id": 1, "account_code": 1}).to_list(None)
    acc_ids = [a["id"] for a in accounts]
    # varied demo schemes (config is editable by user later)
    cost_schemes = [
        {"fee_type": "both",       "fixed_fee": 1500000, "commission_pct": 8},
        {"fee_type": "commission", "fixed_fee": 0,       "commission_pct": 10},
        {"fee_type": "fixed",      "fixed_fee": 800000,  "commission_pct": 0},
        {"fee_type": "both",       "fixed_fee": 500000,  "commission_pct": 5},
        {"fee_type": "commission", "fixed_fee": 0,       "commission_pct": 7},
        {"fee_type": "fixed",      "fixed_fee": 250000,  "commission_pct": 0},
    ]
    inserted, updated = 0, 0
    for idx, k in enumerate(KOL_SEED):
        assigned = [acc_ids[idx % len(acc_ids)]] if acc_ids else []
        # also give macro creators a second account
        if acc_ids and k.get("tier") == "Macro" and len(acc_ids) > 1:
            assigned.append(acc_ids[(idx + 1) % len(acc_ids)])
        exists = await db.marketing_kol_creators.find_one({"handle": k["handle"]})
        if exists:
            # backfill assignment + cost_config for existing demo creators
            await db.marketing_kol_creators.update_one(
                {"handle": k["handle"]},
                {"$set": {
                    "assigned_account_ids": list(dict.fromkeys(assigned)),
                    "creator_code": exists.get("creator_code") or f"KOL-{idx+1:03d}",
                    "cost_config": exists.get("cost_config") or cost_schemes[idx % len(cost_schemes)],
                    "updated_at": iso(),
                }},
            )
            updated += 1
            continue
        doc = {
            "id": str(uuid.uuid4()),
            **k,
            "creator_code": f"KOL-{idx+1:03d}",
            "assigned_account_ids": list(dict.fromkeys(assigned)),
            "cost_config": cost_schemes[idx % len(cost_schemes)],
            "status": "active",
            "engagement_rate": round(random.uniform(2.5, 7.5), 2),
            "total_collabs": random.randint(2, 25),
            "created_at": iso(),
            "updated_at": iso(),
        }
        await db.marketing_kol_creators.insert_one(doc)
        inserted += 1
    print(f"  Inserted {inserted} KOL creators, updated {updated} (assign+cost_config)")


async def seed_creator_sessions(db):
    """Seed live-selling sessions per creator (last ~60 days) for KOL commission/ROI."""
    print("Seeding creator sessions...")
    creators = await db.marketing_kol_creators.find(
        {"assigned_account_ids": {"$exists": True, "$ne": []}}, {"_id": 0}
    ).to_list(None)
    inserted = 0
    today = utc_now().date()
    for c in creators:
        acc_id = c["assigned_account_ids"][0]
        # 6 sessions spread over ~60 days (covers current + previous month)
        for i in range(6):
            date = today - timedelta(days=i * 10 + random.randint(0, 4))
            date_str = date.isoformat()
            exists = await db.marketing_creator_sessions.find_one(
                {"creator_id": c["id"], "date": date_str}
            )
            if exists:
                continue
            revenue = random.randint(2000000, 12000000)
            await db.marketing_creator_sessions.insert_one({
                "id": str(uuid.uuid4()),
                "creator_id": c["id"],
                "creator_name": c.get("name", ""),
                "creator_code": c.get("creator_code", ""),
                "account_id": acc_id,
                "date": date_str,
                "session_name": f"Live {c.get('name','')} {date_str}",
                "revenue": revenue,
                "orders": random.randint(10, 60),
                "peak_viewers": random.randint(200, 3000),
                "created_at": iso(),
            })
            inserted += 1
    print(f"  Inserted {inserted} creator sessions")


async def seed_sales_data(db):
    """Seed last 30 days of daily sales data per platform."""
    print("Seeding daily sales data (last 30 days)...")
    accounts = await db.marketing_platform_accounts.find({}, {"_id": 0}).to_list(None)
    if not accounts:
        print("  No accounts found — skipping sales seed")
        return

    inserted = 0
    today = utc_now().date()
    for day_offset in range(30):
        date = today - timedelta(days=day_offset)
        date_str = date.isoformat()
        for acc in accounts:
            exists = await db.marketing_sales_data.find_one({
                "account_id": acc["id"],
                "date": date_str,
            })
            if exists:
                continue

            # Realistic daily sales pattern with some variance
            base = acc.get("monthly_target", 30000000) / 30
            variance = random.uniform(0.4, 1.6)
            gross_sales = int(base * variance)
            net_sales = int(gross_sales * 0.92)  # 8% platform fee
            orders_count = max(1, int(gross_sales / random.randint(150000, 350000)))

            doc = {
                "id": str(uuid.uuid4()),
                "account_id": acc["id"],
                "account_code": acc["account_code"],
                "platform": acc["platform"],
                "date": date_str,
                "gross_sales": gross_sales,
                "net_sales": net_sales,
                "platform_fee": gross_sales - net_sales,
                "orders_count": orders_count,
                "items_sold": orders_count * random.randint(1, 3),
                "visitors": orders_count * random.randint(15, 45),
                "conversion_rate": round((1 / random.randint(15, 45)) * 100, 2),
                "submitted_by": acc.get("pic_email", "system"),
                "created_at": iso(),
            }
            await db.marketing_sales_data.insert_one(doc)
            inserted += 1
    print(f"  Inserted {inserted} daily sales records")


async def seed_targets(db):
    """Seed monthly targets for current month."""
    print("Seeding monthly targets...")
    accounts = await db.marketing_platform_accounts.find({}, {"_id": 0}).to_list(None)
    if not accounts:
        print("  No accounts found — skipping targets seed")
        return

    inserted = 0
    now = utc_now()
    period = f"{now.year}-{now.month:02d}"
    for acc in accounts:
        exists = await db.marketing_targets.find_one({
            "account_id": acc["id"],
            "period": period,
        })
        if exists:
            continue
        doc = {
            "id": str(uuid.uuid4()),
            "account_id": acc["id"],
            "account_code": acc["account_code"],
            "platform": acc["platform"],
            "period": period,
            "target_revenue": acc.get("monthly_target", 30000000),
            "target_orders": int(acc.get("monthly_target", 30000000) / 250000),
            "target_new_followers": random.randint(500, 2500),
            "set_by": "Admin",
            "created_at": iso(),
        }
        await db.marketing_targets.insert_one(doc)
        inserted += 1
    print(f"  Inserted {inserted} monthly targets")


async def seed_orders(db):
    """Seed sample marketing orders for last 7 days."""
    print("Seeding sample marketing orders (last 7 days)...")
    accounts = await db.marketing_platform_accounts.find({}, {"_id": 0}).to_list(None)
    catalog = await db.marketing_catalog_items.find({}, {"_id": 0}).to_list(None)
    if not accounts or not catalog:
        print("  No accounts or catalog found — skipping orders seed")
        return

    inserted = 0
    statuses = ["pending", "processing", "shipped", "completed", "completed", "completed"]
    today = utc_now()
    for _ in range(50):
        acc = random.choice(accounts)
        item = random.choice(catalog)
        qty = random.randint(1, 4)
        order_date = today - timedelta(days=random.randint(0, 7), hours=random.randint(0, 23))
        doc = {
            "id": str(uuid.uuid4()),
            "order_number": f"ORD-{order_date.strftime('%Y%m%d')}-{random.randint(1000, 9999)}",
            "account_id": acc["id"],
            "platform": acc["platform"],
            "customer_name": random.choice(["Sari W.", "Rina P.", "Maya K.", "Dewi A.", "Putri S.", "Anita L.", "Lia M.", "Eka R."]),
            "items": [{
                "sku": item["sku"],
                "name": item["name"],
                "qty": qty,
                "unit_price": item["price"],
                "subtotal": item["price"] * qty,
            }],
            "total_amount": item["price"] * qty,
            "shipping_fee": random.randint(15000, 30000),
            "status": random.choice(statuses),
            "order_date": iso(order_date),
            "created_at": iso(order_date),
        }
        await db.marketing_orders.insert_one(doc)
        inserted += 1
    print(f"  Inserted {inserted} marketing orders")


async def main():
    print("=" * 60)
    print("MARKETING DEMO DATA SEEDING")
    print("=" * 60)
    db = get_db()
    
    await seed_platform_accounts(db)
    await seed_catalog(db)
    await seed_kol_creators(db)
    await seed_creator_sessions(db)
    await seed_sales_data(db)
    await seed_targets(db)
    await seed_orders(db)
    
    print("\n" + "=" * 60)
    print("SEEDING COMPLETE")
    print("=" * 60)
    
    # Summary
    cols = [
        "marketing_platform_accounts",
        "marketing_catalog_items",
        "marketing_kol_creators",
        "marketing_creator_sessions",
        "marketing_sales_data",
        "marketing_targets",
        "marketing_orders",
    ]
    print("\nFinal counts:")
    for c in cols:
        cnt = await db[c].count_documents({})
        print(f"  {c}: {cnt}")


if __name__ == "__main__":
    asyncio.run(main())
