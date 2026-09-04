"""
Migration: Add pack_unit, pack_size, display_in_packs to existing materials
Run: python3 /app/backend/migrations/add_pack_fields_to_materials.py
"""
import asyncio
import sys
sys.path.insert(0, '/app/backend')

from database import get_db
from datetime import datetime, timezone

async def migrate():
    db = get_db()  # get_db() returns db directly, not awaitable
    
    print("🔄 Starting migration: Add pack fields to rahaza_materials...")
    
    # Count materials without pack fields
    count_without = await db.rahaza_materials.count_documents({
        "$or": [
            {"pack_size": {"$exists": False}},
            {"pack_unit": {"$exists": False}},
            {"display_in_packs": {"$exists": False}},
        ]
    })
    
    print(f"📊 Found {count_without} materials without pack fields")
    
    if count_without == 0:
        print("✅ All materials already have pack fields. Migration not needed.")
        return
    
    # Update all materials without pack fields
    result = await db.rahaza_materials.update_many(
        {
            "$or": [
                {"pack_size": {"$exists": False}},
                {"pack_unit": {"$exists": False}},
                {"display_in_packs": {"$exists": False}},
            ]
        },
        {
            "$set": {
                "pack_size": 1,  # Default: 1 pack = 1 base unit (backward compatible)
                "pack_unit": "pack",
                "display_in_packs": False,  # Default: show in base unit
                "migration_updated_at": datetime.now(timezone.utc),
            }
        }
    )
    
    print("✅ Migration complete!")
    print(f"   - Matched: {result.matched_count}")
    print(f"   - Modified: {result.modified_count}")
    print("\n📝 Note: All existing materials now have pack_size=1 (backward compatible)")
    print("   Users can update individual items with custom pack sizes via UI.")

if __name__ == "__main__":
    asyncio.run(migrate())
