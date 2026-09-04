"""Seed demo utk konfirmasi visual FASE G (submitted accessory opname session).
  python seed_confirm.py seed   -> material aksesoris + stok 50 + sesi submitted (count 45, variance -5)
  python seed_confirm.py clean  -> hapus semua artefak DEMO-CONFIRM
"""
import asyncio, os, sys, uuid
from pathlib import Path
import httpx
from dotenv import load_dotenv
sys.path.insert(0, str(Path(__file__).resolve().parent))
load_dotenv(Path(__file__).resolve().parent / ".env")
from motor.motor_asyncio import AsyncIOMotorClient
from core import stock_service
from core.accessory_stock import get_accessory_location_id

BASE = "http://localhost:8001"
MARK = "DEMO-CONFIRM-"

async def seed():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = client[os.environ.get("DB_NAME","test_database")]
    sfx = uuid.uuid4().hex[:5].upper(); mat = f"{MARK}{sfx}"
    loc = await get_accessory_location_id(db)
    await db.rahaza_materials.insert_one({"id":mat,"code":f"KNC-{sfx}","name":f"Kancing Logam {sfx}","type":"accessory","active":True,"unit":"pcs","unit_cost":2000,"reorder_point":0})
    await stock_service.add(mat, loc, 50, ref={"source":"demo_confirm"}, actor={"email":"seed"}, db=db)
    async with httpx.AsyncClient(timeout=30) as h:
        tok = (await h.post(f"{BASE}/api/auth/login", json={"email":"admin@garment.com","password":"Admin@123"})).json()["token"]
        hd = {"Authorization": f"Bearer {tok}"}
        sid = (await h.post(f"{BASE}/api/acc/opname", headers=hd, json={"notes":"DEMO-CONFIRM approval"})).json()["id"]
        await h.put(f"{BASE}/api/acc/opname/{sid}/count", headers=hd, json={"acc_id":mat,"counted_qty":45})
        await h.post(f"{BASE}/api/acc/opname/{sid}/submit", headers=hd)
    print("seeded session:", sid, "material:", mat)
    client.close()

async def clean():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"]); db = client[os.environ.get("DB_NAME","test_database")]
    mats = [m["id"] async for m in db.rahaza_materials.find({"id":{"$regex":f"^{MARK}"}},{"id":1})]
    for mid in mats:
        await db.rahaza_material_stock.delete_many({"material_id":mid})
        await db.rahaza_stock_ledger.delete_many({"material_id":mid})
        mv_ids = [m["id"] async for m in db.rahaza_material_movements.find({"material_id":mid},{"id":1})]
        for x in mv_ids:
            await db.rahaza_journal_entries.delete_many({"source_ref":f"mvadj:{x}"})
            await db.rahaza_journal_lines.delete_many({"source_ref":f"mvadj:{x}"})
        await db.rahaza_material_movements.delete_many({"material_id":mid})
    await db.rahaza_materials.delete_many({"id":{"$regex":f"^{MARK}"}})
    await db.wh_opname_sessions2.delete_many({"notes":"DEMO-CONFIRM approval"})
    print("cleaned DEMO-CONFIRM; materials removed:", len(mats))
    client.close()

if __name__ == "__main__":
    asyncio.run(seed() if sys.argv[1]=="seed" else clean())
