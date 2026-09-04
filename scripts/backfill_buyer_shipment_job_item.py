"""Isi job_item_id pada buyer_shipment_items yang kosong (dispatch berbasis po_item) — iterasi 103."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), '..', 'backend', '.env'))
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402


async def main():
    db = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    n = 0
    async for it in db.buyer_shipment_items.find(
            {'job_item_id': None, 'po_item_id': {'$ne': None}}, {'_id': 0, 'id': 1, 'po_item_id': 1}):
        jis = await db.production_job_items.find(
            {'po_item_id': it['po_item_id']}, {'_id': 0, 'id': 1, 'job_id': 1, 'produced_qty': 1}).to_list(None)
        if not jis:
            continue
        best = max(jis, key=lambda j: int(j.get('produced_qty') or 0))
        await db.buyer_shipment_items.update_one(
            {'id': it['id']}, {'$set': {'job_item_id': best['id'], 'job_id': best.get('job_id')}})
        n += 1
    print('backfilled', n)


asyncio.run(main())
