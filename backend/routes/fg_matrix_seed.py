"""
FG Matrix Demo Seeder
=====================
Seeds demo FG materials + stock so the Matrix view has visualizable data.
Idempotent: only inserts if no FG materials exist.

Endpoint: POST /api/rahaza/fg-matrix/seed-demo
"""
from database import get_db
from datetime import datetime, timezone
import uuid


def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)


async def seed_fg_matrix_demo():
    """Create sample FG materials + stock for matrix view demo."""
    db = get_db()
    
    existing = await db.rahaza_materials.count_documents({"type": "fg", "code": {"$regex": "^DEMO-"}})
    if existing > 0:
        return {"status": "already_seeded", "existing_count": existing}
    
    # Ensure a default location exists
    default_loc = await db.rahaza_locations.find_one({"active": True}, {"_id": 0})
    if not default_loc:
        default_loc = {
            "id": _uid(), "code": "FG-MAIN", "name": "FG Warehouse Main",
            "active": True, "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_locations.insert_one(default_loc)
    loc_id = default_loc["id"]
    
    # Demo data: 3 models × multiple colors × multiple sizes
    demo_data = [
        # Model: TSHIRT
        ("DEMO-TSHIRT-BLACK-S", "T-Shirt Casual Black S", 45),
        ("DEMO-TSHIRT-BLACK-M", "T-Shirt Casual Black M", 78),
        ("DEMO-TSHIRT-BLACK-L", "T-Shirt Casual Black L", 32),
        ("DEMO-TSHIRT-BLACK-XL", "T-Shirt Casual Black XL", 18),
        ("DEMO-TSHIRT-WHITE-S", "T-Shirt Casual White S", 60),
        ("DEMO-TSHIRT-WHITE-M", "T-Shirt Casual White M", 95),
        ("DEMO-TSHIRT-WHITE-L", "T-Shirt Casual White L", 41),
        ("DEMO-TSHIRT-WHITE-XL", "T-Shirt Casual White XL", 22),
        ("DEMO-TSHIRT-NAVY-S", "T-Shirt Casual Navy S", 0),
        ("DEMO-TSHIRT-NAVY-M", "T-Shirt Casual Navy M", 12),
        ("DEMO-TSHIRT-NAVY-L", "T-Shirt Casual Navy L", 8),
        ("DEMO-TSHIRT-RED-M", "T-Shirt Casual Red M", 25),
        ("DEMO-TSHIRT-RED-L", "T-Shirt Casual Red L", 30),
        # Model: HOODIE
        ("DEMO-HOODIE-BLACK-M", "Hoodie Premium Black M", 35),
        ("DEMO-HOODIE-BLACK-L", "Hoodie Premium Black L", 28),
        ("DEMO-HOODIE-BLACK-XL", "Hoodie Premium Black XL", 15),
        ("DEMO-HOODIE-GRAY-M", "Hoodie Premium Gray M", 42),
        ("DEMO-HOODIE-GRAY-L", "Hoodie Premium Gray L", 38),
        ("DEMO-HOODIE-GRAY-XL", "Hoodie Premium Gray XL", 20),
        ("DEMO-HOODIE-NAVY-L", "Hoodie Premium Navy L", 0),
        ("DEMO-HOODIE-NAVY-XL", "Hoodie Premium Navy XL", 5),
        # Model: POLO
        ("DEMO-POLO-WHITE-S", "Polo Shirt White S", 25),
        ("DEMO-POLO-WHITE-M", "Polo Shirt White M", 48),
        ("DEMO-POLO-WHITE-L", "Polo Shirt White L", 35),
        ("DEMO-POLO-BLACK-M", "Polo Shirt Black M", 32),
        ("DEMO-POLO-BLACK-L", "Polo Shirt Black L", 28),
        ("DEMO-POLO-NAVY-S", "Polo Shirt Navy S", 18),
        ("DEMO-POLO-NAVY-M", "Polo Shirt Navy M", 26),
        ("DEMO-POLO-NAVY-L", "Polo Shirt Navy L", 22),
    ]
    
    inserted_materials = 0
    inserted_stocks = 0
    
    for code, name, qty in demo_data:
        # Insert material
        mat = {
            "id": _uid(), "code": code, "name": name,
            "type": "fg", "unit": "pcs",
            "color": "", "notes": "Demo data — seeded for FG Matrix view",
            "min_stock": 0, "reorder_point": 10,
            "active": True,
            "created_at": _now(), "updated_at": _now(),
        }
        await db.rahaza_materials.insert_one(mat)
        inserted_materials += 1
        
        # Insert stock if qty > 0
        if qty > 0:
            await db.rahaza_material_stock.insert_one({
                "id": _uid(),
                "material_id": mat["id"],
                "location_id": loc_id,
                "qty": float(qty),
                "reserved": 0,
                "unit": "pcs",
                "created_at": _now(),
                "updated_at": _now(),
            })
            inserted_stocks += 1
    
    return {
        "status": "seeded",
        "materials_inserted": inserted_materials,
        "stock_records_inserted": inserted_stocks,
        "location_id": loc_id,
    }
