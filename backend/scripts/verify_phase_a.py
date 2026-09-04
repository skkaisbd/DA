"""Bug A reproduction — Additional shipment tidak masuk ke jobs production.

Script ini bekerja atas seed `/api/seed/maklon-full` (idempoten).
Runbook:
    python3 /app/backend/scripts/repro_phase_a.py
Behavior:
- BASELINE (before Fix A1+A2): asserts child_job TIDAK DIBUAT karena guard
  `shipment.status == 'Received'` di vendor_shipment.py:414 fail (status masih 'Sent').
- AFTER-FIX: asserts child_job DIBUAT + shipment status di-auto-promote ke 'Received'.

Script mengembalikan exit code:
- 0 kalau bug **masih bug** (baseline expected), atau kalau bug **sudah kelar** (target after-fix).
  Argumen `--expect fixed` vs `--expect buggy` (default buggy) untuk memilih ekspektasi.
"""
import argparse
import asyncio
import logging
import os
import sys
from motor.motor_asyncio import AsyncIOMotorClient
import httpx

logging.basicConfig(level=logging.INFO, format='%(message)s')
log = logging.getLogger('repro.phase_a')

BASE = os.environ.get('API_BASE', 'http://localhost:8001')
ADMIN_EMAIL = 'admin@garment.com'
ADMIN_PWD = 'Admin@123'
VENDOR_ID = 'mk-vendor-demo-1'  # dari maklon_seed.py
PO_ID = 'po-mk-demo-1'          # Draft PO — bersih untuk skenario baru
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


def _die(msg: str, code: int = 1):
    log.error(f'  ✗ FAIL: {msg}')
    sys.exit(code)


async def main(expect: str):
    log.info(f'[repro_phase_a] BASE={BASE}  MONGO_URL={MONGO_URL}  expect={expect}')
    log.info('')
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        # 1. Login
        r = await client.post('/api/auth/login',
                              json={'email': ADMIN_EMAIL, 'password': ADMIN_PWD})
        r.raise_for_status()
        token = r.json()['token']
        hdr = {'Authorization': f'Bearer {token}'}
        log.info(f'  ✓ Login admin ok (token len={len(token)})')

        # 2. Ambil po_items dari PO Draft po-mk-demo-1
        r = await client.get(f'/api/production-pos/{PO_ID}', headers=hdr)
        r.raise_for_status()
        po_detail = r.json()
        po_items = po_detail.get('items', [])
        if len(po_items) < 1:
            _die(f'PO {PO_ID} tidak punya po_items — re-run /api/seed/maklon-full')
        po_item = po_items[0]
        log.info(f'  ✓ PO {po_detail["po_number"]} punya {len(po_items)} item')
        log.info(f'    Ambil item[0]: id={po_item["id"]}  qty_ordered={po_item.get("qty")}  sku={po_item.get("sku")}')

        # 3. Clean state — hapus semua shipment sebelumnya untuk PO ini (idempotent)
        mongo = AsyncIOMotorClient(MONGO_URL)
        db = mongo[DB_NAME]
        # Hapus shipments untuk PO ini dan cascade
        prev = await db.vendor_shipments.find({'po_id': PO_ID}).to_list(None)
        for s in prev:
            insps = await db.vendor_material_inspections.find({'shipment_id': s['id']}).to_list(None)
            for i in insps:
                await db.vendor_material_inspection_items.delete_many({'inspection_id': i['id']})
            await db.vendor_material_inspections.delete_many({'shipment_id': s['id']})
            jobs = await db.production_jobs.find({'vendor_shipment_id': s['id']}).to_list(None)
            for j in jobs:
                await db.production_job_items.delete_many({'job_id': j['id']})
                await db.production_progress.delete_many({'job_id': j['id']})
            await db.production_jobs.delete_many({'vendor_shipment_id': s['id']})
            await db.vendor_shipment_items.delete_many({'shipment_id': s['id']})
        await db.vendor_shipments.delete_many({'po_id': PO_ID})
        await db.material_requests.delete_many({'po_id': PO_ID})
        log.info(f'  ✓ Clean prior shipments/inspections/jobs ({len(prev)} shipments removed)')

        # 4. PARENT shipment — NORMAL, kirim 100 pcs
        parent_ship_number = 'SHIP-REPRO-PARENT'
        # Ensure ordered qty is enough; use whatever qty PO item has
        qty_parent = min(int(po_item.get('qty', 100)), 100)
        r = await client.post('/api/vendor-shipments', headers=hdr, json={
            'shipment_number': parent_ship_number,
            'vendor_id': VENDOR_ID,
            'po_id': PO_ID,
            'shipment_type': 'NORMAL',
            'items': [{
                'po_id': PO_ID,
                'po_item_id': po_item['id'],
                'po_number': po_detail['po_number'],
                'qty_sent': qty_parent,
                'sku': po_item.get('sku', ''),
                'size': po_item.get('size', ''),
                'color': po_item.get('color', ''),
                'product_name': po_item.get('product_name', ''),
            }]
        })
        if r.status_code >= 400:
            _die(f'POST parent shipment gagal: {r.status_code} {r.text[:400]}')
        parent_ship = r.json()
        parent_ship_id = parent_ship['id']
        log.info(f'  ✓ Parent shipment created: {parent_ship_number} id={parent_ship_id} qty={qty_parent}')

        # 5. Mark parent Received
        r = await client.put(f'/api/vendor-shipments/{parent_ship_id}', headers=hdr,
                             json={'status': 'Received'})
        if r.status_code >= 400:
            _die(f'PUT parent Received gagal: {r.status_code} {r.text[:400]}')
        log.info('  ✓ Parent shipment marked Received')

        # 6. Inspect parent — assume 80 diterima, 20 missing
        parent_item = parent_ship['items'][0]
        r = await client.post('/api/vendor-material-inspections', headers=hdr, json={
            'shipment_id': parent_ship_id,
            'vendor_id': VENDOR_ID,
            'items': [{
                'shipment_item_id': parent_item['id'],
                'sku': parent_item.get('sku', ''),
                'size': parent_item.get('size', ''),
                'color': parent_item.get('color', ''),
                'ordered_qty': qty_parent,
                'received_qty': 80,
                'missing_qty': 20,
                'condition_notes': 'baseline repro',
            }],
            'accessory_items': [],
        })
        if r.status_code >= 400:
            _die(f'Parent inspection gagal: {r.status_code} {r.text[:400]}')
        log.info('  ✓ Parent inspection submitted (received=80, missing=20)')

        # 7. Create parent production_job manually (vendor CMT view — via API)
        # NOTE: parent must be a proper 'production_job' before we can measure "child auto-create"
        # We call POST /production-jobs with vendor_shipment_id
        r = await client.post('/api/production-jobs', headers=hdr, json={
            'vendor_shipment_id': parent_ship_id,
            'vendor_id': VENDOR_ID,
            'po_id': PO_ID,
        })
        if r.status_code >= 400:
            _die(f'POST parent job gagal: {r.status_code} {r.text[:400]}')
        parent_job = r.json()
        parent_job_id = parent_job['id']
        log.info(f'  ✓ Parent production_job created: {parent_job["job_number"]}')

        # 8. Now the REAL test — ADDITIONAL shipment (20 pcs replacement)
        add_ship_number = 'SHIP-REPRO-ADDITIONAL'
        r = await client.post('/api/vendor-shipments', headers=hdr, json={
            'shipment_number': add_ship_number,
            'vendor_id': VENDOR_ID,
            'po_id': PO_ID,
            'shipment_type': 'ADDITIONAL',
            'parent_shipment_id': parent_ship_id,
            'items': [{
                'po_id': PO_ID,
                'po_item_id': po_item['id'],
                'po_number': po_detail['po_number'],
                'qty_sent': 20,
                'sku': po_item.get('sku', ''),
                'size': po_item.get('size', ''),
                'color': po_item.get('color', ''),
                'product_name': po_item.get('product_name', ''),
            }]
        })
        if r.status_code >= 400:
            _die(f'POST additional shipment gagal: {r.status_code} {r.text[:400]}')
        add_ship = r.json()
        add_ship_id = add_ship['id']
        log.info(f'  ✓ Additional shipment created: {add_ship_number} id={add_ship_id} status={add_ship["status"]}')
        assert add_ship['status'] == 'Sent', f"Expected default 'Sent', got {add_ship['status']}"

        # 9. **CRITICAL** — inspect ADDITIONAL shipment WITHOUT setting Received first.
        # This is the exact user-reported reproduction path.
        add_item = add_ship['items'][0]
        r = await client.post('/api/vendor-material-inspections', headers=hdr, json={
            'shipment_id': add_ship_id,
            'vendor_id': VENDOR_ID,
            'items': [{
                'shipment_item_id': add_item['id'],
                'sku': add_item.get('sku', ''),
                'size': add_item.get('size', ''),
                'color': add_item.get('color', ''),
                'ordered_qty': 20,
                'received_qty': 20,
                'missing_qty': 0,
                'condition_notes': 'top-up',
            }],
            'accessory_items': [],
        })
        if r.status_code >= 400:
            _die(f'ADDITIONAL inspection gagal: {r.status_code} {r.text[:400]}')
        log.info('  ✓ ADDITIONAL inspection submitted (shipment status was Sent, not Received)')

        # 10. Assertion — did a child production_job get created?
        child_jobs = await db.production_jobs.find({
            'vendor_shipment_id': add_ship_id
        }).to_list(None)
        # Also read fresh shipment status
        fresh_add_ship = await db.vendor_shipments.find_one({'id': add_ship_id})
        add_status_after = fresh_add_ship.get('status') if fresh_add_ship else '<missing>'

        log.info('')
        log.info('  ─── RESULT ─────────────────────────────────────────')
        log.info(f'  child_jobs count for additional shipment = {len(child_jobs)}')
        log.info(f'  additional shipment.status after inspect = {add_status_after!r}')
        log.info('  ─────────────────────────────────────────────────────')
        log.info('')

        if expect == 'buggy':
            # Bug baseline: expect NO child_job and status stuck at Sent
            if len(child_jobs) == 0 and add_status_after == 'Sent':
                log.info('  ✓ BUG REPRODUCED (baseline): child_job NOT created + shipment stuck at Sent.')
                log.info('    → Confirms vendor_shipment.py:414 guard is the culprit.')
                mongo.close()
                sys.exit(0)
            else:
                log.info('  ✗ UNEXPECTED: bug not reproduced.')
                log.info('    (either fix already applied, or seed data drift; investigate).')
                mongo.close()
                sys.exit(2)
        else:  # 'fixed'
            if len(child_jobs) == 1 and add_status_after == 'Received':
                cj = child_jobs[0]
                # verify child_job has proper links & production_job_items
                ji_count = await db.production_job_items.count_documents({'job_id': cj['id']})
                if cj.get('parent_job_id') != parent_job_id:
                    _die(f"child_job.parent_job_id mismatch: got {cj.get('parent_job_id')}, want {parent_job_id}")
                if ji_count < 1:
                    _die(f"child_job {cj['job_number']} punya 0 production_job_items (harusnya >=1)")
                # test end-to-end: input progress ke child job_item
                child_items = await db.production_job_items.find({'job_id': cj['id']}).to_list(None)
                first_ji = child_items[0]
                r = await client.post('/api/production-progress', headers=hdr, json={
                    'job_id': cj['id'],
                    'job_item_id': first_ji['id'],
                    'completed_quantity': 5,
                    'progress_date': None,
                    'notes': 'repro fix verify',
                })
                if r.status_code >= 400:
                    _die(f'progress input pada child_job gagal: {r.status_code} {r.text[:400]}')
                log.info('  ✓ FIX VERIFIED:')
                log.info(f'    - child_job {cj["job_number"]} created with parent_job_id={parent_job_id[:8]}...')
                log.info(f'    - production_job_items count = {ji_count}')
                log.info('    - additional shipment status auto-promoted to Received')
                log.info('    - progress input pada child_job_items SUKSES (qty=5)')
                mongo.close()
                sys.exit(0)
            else:
                log.info(f'  ✗ FIX NOT WORKING: child_job count={len(child_jobs)} status={add_status_after!r}')
                mongo.close()
                sys.exit(3)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--expect', choices=['buggy', 'fixed'], default='buggy',
                    help='Ekspektasi hasil (default buggy = pre-fix baseline)')
    args = ap.parse_args()
    asyncio.run(main(args.expect))
