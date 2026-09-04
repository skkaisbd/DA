"""
Seed COA dengan Expense Categories untuk EEM (Employee Expense Management)
One-time script untuk populate expense accounts (6-3xxx series)

Run: python -m scripts.seed_expense_categories
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017/rahaza_erp')

EXPENSE_CATEGORIES = [
    {
        "code": "6-3400",
        "name": "Biaya Perjalanan Dinas",
        "name_en": "Travel Expenses",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "General travel and business trip expenses",
        "notes": "Default/fallback untuk expense yang tidak di-kategorisasi"
    },
    {
        "code": "6-3410",
        "name": "Biaya Transportasi",
        "name_en": "Transportation Expenses",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Taxi, fuel, parking, toll, public transport"
    },
    {
        "code": "6-3420",
        "name": "Biaya Akomodasi",
        "name_en": "Accommodation Expenses",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Hotel, lodging, guest house"
    },
    {
        "code": "6-3430",
        "name": "Biaya Konsumsi",
        "name_en": "Meal & Beverage Expenses",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Meals, snacks, beverages during business activities"
    },
    {
        "code": "6-3440",
        "name": "Biaya Representasi",
        "name_en": "Entertainment & Representation",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Client entertainment, business meals, gifts"
    },
    {
        "code": "6-3450",
        "name": "Biaya Komunikasi",
        "name_en": "Communication Expenses",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Phone, internet, mobile data for business"
    },
    {
        "code": "6-3460",
        "name": "Biaya ATK & Perlengkapan",
        "name_en": "Office Supplies",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Stationery, office supplies, small equipment"
    },
    {
        "code": "6-3470",
        "name": "Biaya Parkir & Tol",
        "name_en": "Parking & Toll",
        "type": "expense",
        "category": "operational_expense",
        "parent": "6-3000",
        "level": 2,
        "is_active": True,
        "description": "Parking fees and highway tolls"
    },
]

async def seed_expense_categories():
    print("🌱 Seeding COA with Expense Categories...")
    client = AsyncIOMotorClient(MONGO_URL)
    db = client.get_default_database()
    
    inserted = 0
    skipped = 0
    
    for cat in EXPENSE_CATEGORIES:
        # Check if already exists
        existing = await db.rahaza_coa_accounts.find_one({'code': cat['code']})
        if existing:
            print(f"   ⏭️  Skip {cat['code']} (already exists)")
            skipped += 1
        else:
            await db.rahaza_coa_accounts.insert_one(cat)
            print(f"   ✅ Added {cat['code']} - {cat['name']}")
            inserted += 1
    
    print(f"\n✨ Done! Inserted: {inserted}, Skipped: {skipped}")
    client.close()

if __name__ == '__main__':
    asyncio.run(seed_expense_categories())
