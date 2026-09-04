"""
Migration script untuk upgrade existing BOMs ke multi-version structure.

Menambahkan field:
- version: int (default 1)
- is_active: bool (default true)

Jalankan sekali saja setelah deploy update BOM.
"""
import asyncio
import sys
sys.path.insert(0, '/app/backend')
from database import get_db
from datetime import datetime, timezone

async def migrate_bom_versions():
    db = get_db()
    
    # Find all existing BOMs without version field
    boms_without_version = await db.rahaza_boms.find(
        {"version": {"$exists": False}},
        {"_id": 0}
    ).to_list(None)
    
    print(f"Found {len(boms_without_version)} BOMs to migrate...")
    
    updated_count = 0
    for bom in boms_without_version:
        # Update dengan version=1 dan is_active=true
        await db.rahaza_boms.update_one(
            {"id": bom["id"]},
            {"$set": {
                "version": 1,
                "is_active": True,
                "updated_at": datetime.now(timezone.utc)
            }}
        )
        updated_count += 1
    
    print(f"✅ Migration complete! Updated {updated_count} BOMs.")
    print("All existing BOMs now have version=1 and is_active=true")

if __name__ == "__main__":
    asyncio.run(migrate_bom_versions())
