"""
Create test marketing order for Fulfillment testing
"""
import sys
sys.path.insert(0, '/app/backend')

from database import get_db
from datetime import datetime, timezone, date
import uuid
import asyncio

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)

async def create_test_marketing_order():
    """Create a test marketing order with fulfillment_status=pending_fulfillment"""
    db = get_db()
    
    order_id = f"MKT-TEST-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    
    order = {
        "id": _uid(),
        "order_id": order_id,
        "customer_name": "Test Customer Fulfillment",
        "customer_email": "customer@test.com",
        "customer_phone": "08123456789",
        "city": "Jakarta",
        "address": "Jl. Test No. 123, Jakarta Selatan",
        "product_name": "Kemeja Biru L",
        "quantity": 50,
        "price": 150000,
        "total": 7500000,
        "courier": "JNE",
        "fulfillment_status": "pending_fulfillment",
        "order_date": date.today().isoformat(),
        "created_at": _now(),
        "updated_at": _now(),
        "status": "packed",  # Marketing order status (packed = ready for fulfillment)
        "notes": "Test order for Phase 6 Fulfillment testing"
    }
    
    await db.marketing_orders.insert_one(dict(order))
    print(f"✅ Created marketing order: {order_id}")
    print(f"   ID: {order['id']}")
    print(f"   Customer: {order['customer_name']}")
    print(f"   Product: {order['product_name']}")
    print(f"   Quantity: {order['quantity']} pcs")
    print(f"   Fulfillment Status: {order['fulfillment_status']}")
    
    return order

if __name__ == "__main__":
    order = asyncio.run(create_test_marketing_order())
