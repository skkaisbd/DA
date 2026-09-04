#!/usr/bin/env python3
"""Debug CYC-8e: manual order -> marketing_sales_data rollup."""
import os, sys, json, requests
sys.path.insert(0, '/app/backend')
from pymongo import MongoClient
from dotenv import load_dotenv
load_dotenv('/app/backend/.env')
db = MongoClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
BASE = 'http://localhost:8001'
tok = requests.post(f'{BASE}/api/auth/login', json={'email': 'admin@garment.com', 'password': 'Admin@123'}, timeout=30).json()['token']
H = {'Authorization': f'Bearer {tok}', 'Content-Type': 'application/json'}

from core import marketing_cycle as _cycle
item = db.marketing_catalog_items.find_one({'hpp': {'$gt': 0}, '$or': [{'price': {'$gt': 0}}, {'harga_jual': {'$gt': 0}}]}, {'_id': 0})
cat = db.marketing_catalogs.find_one({'id': item.get('catalog_id')}, {'_id': 0}) or {}
aid = cat.get('account_id')
harga = float(item.get('price') or item.get('harga_jual') or 0)
today = _cycle.today_wib().strftime('%Y-%m-%d')
print('account_id', aid, 'harga', harga, 'today', today)
print('account doc:', json.dumps(db.marketing_platform_accounts.find_one({'id': aid}, {'_id': 0, 'account_code': 1, 'account_name': 1, 'status': 1}), default=str))
before = db.marketing_sales_data.find_one({'account_id': aid, 'date': today, 'revenue_type': 'total'}, {'_id': 0})
print('BEFORE sales_data:', json.dumps(before, default=str)[:400])

payload = {'account_id': aid, 'platform': cat.get('platform') or 'manual',
           'customer_name': 'DBG CYC8E', 'catalog_item_id': item['id'], 'reserve_stock': False,
           'items': [{'sku_code': item.get('sku') or 'UJI', 'product_name': item.get('name') or 'uji',
                      'qty': 1, 'price': harga, 'catalog_item_id': item['id']}],
           'quantity': 1, 'price_final': harga, 'total_payment': harga, 'note': 'dbg'}
r = requests.post(f'{BASE}/api/marketing/orders', headers=H, json=payload, timeout=90)
print('POST', r.status_code)
oid = ((r.json() or {}).get('order') or r.json() or {}).get('id')
doc = db.marketing_orders.find_one({'id': oid}, {'_id': 0}) or {}
print('ORDER keys of interest:', json.dumps({k: doc.get(k) for k in
      ('id', 'order_id', 'account_id', 'order_date', 'status', 'order_status', 'revenue_product',
       'order_amount', 'revenue_gross', 'seller_discount_total', 'source', 'platform')}, default=str))
after = db.marketing_sales_data.find_one({'account_id': aid, 'date': today, 'revenue_type': 'total'}, {'_id': 0})
print('AFTER sales_data:', json.dumps(after, default=str)[:600])
allrows = list(db.marketing_sales_data.find({'account_id': aid, 'date': today}, {'_id': 0}))
print('ALL rows today:', len(allrows), json.dumps(allrows, default=str)[:800])

# run rollup manually to see what it computes
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from core import marketing_daily_rollup as _rollup
async def main():
    adb = AsyncIOMotorClient(os.environ['MONGO_URL'])[os.environ['DB_NAME']]
    print('order_date_key ->', _rollup.order_date_key(doc.get('order_date')))
    try:
        res = await _rollup.recompute_for_orders(adb, [oid], actor='dbg')
        print('recompute_for_orders result:', json.dumps(res, default=str)[:600])
    except Exception as e:
        import traceback; traceback.print_exc()
asyncio.run(main())
after2 = db.marketing_sales_data.find_one({'account_id': aid, 'date': today, 'revenue_type': 'total'}, {'_id': 0})
print('AFTER2 sales_data:', json.dumps(after2, default=str)[:600])

if oid:
    d = requests.delete(f'{BASE}/api/marketing/orders/{oid}', headers=H, timeout=60)
    print('cleanup delete', d.status_code)
