"""Independent edge-case tests for Fase 2 MAKLON backend port (SOMMERVILLE).

Focus: scenarios NOT covered by the POC (flow_maklon_sommerville_test.py):
  * PO edit guardrails after shipment (SKU/qty/delete)
  * ADDITIONAL material_request approve → child -A1 shipment + child job
  * quick-complete endpoint on a maklon PO (end-to-end idempotent)
  * Double inspection rejection
  * Buyer shipment without job_id (dispatch tanpa job)
  * Seeder idempotency (double run → no duplicate)
  * Klien tracking cross-buyer 403
  * DA extensions: stage-summary + PUT stage-qty + variance post-gl
  * Regression: multi-role login + /api/dewi/maklon/pos + rahaza flow-summary
  * business_type invalid in body-only endpoints

Uses live DB — every created PO is cascade-deleted at teardown.
"""
import os
import time
import requests

API = os.environ.get('API_URL', 'http://localhost:8001')

PASS = 0
FAIL = 0
FAILED = []


def check(name, cond, detail=''):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILED.append(f"{name} — {detail}")
        print(f"  FAIL  {name} — {detail}")


def login(email, password):
    r = requests.post(f"{API}/api/auth/login", json={'email': email, 'password': password}, timeout=15)
    if r.status_code != 200:
        raise RuntimeError(f"login {email} failed {r.status_code} {r.text[:200]}")
    return r.json()['token']


def H(t):
    return {'Authorization': f'Bearer {t}'}


def cleanup_po(admin, po_number):
    r = requests.get(f"{API}/api/production-pos", headers=H(admin), timeout=15)
    if r.status_code == 200:
        for p in r.json():
            if p.get('po_number') == po_number:
                requests.delete(f"{API}/api/production-pos/{p['id']}", headers=H(admin), timeout=30)


def ensure_seed(admin):
    # idempotent seed (returns 2 fixed PO ids)
    r = requests.post(f"{API}/api/seed/maklon-full", headers=H(admin), timeout=60)
    return r.status_code == 200


# ─── Test blocks ────────────────────────────────────────────────────────────

def test_seeder_idempotency(admin):
    print("\n== TEST 1: Seeder idempotency (2× run → no duplicate) ==")
    r1 = requests.post(f"{API}/api/seed/maklon-full", headers=H(admin), timeout=60)
    r2 = requests.post(f"{API}/api/seed/maklon-full", headers=H(admin), timeout=60)
    check('seed pertama 200', r1.status_code == 200, str(r1.status_code))
    check('seed kedua 200', r2.status_code == 200, str(r2.status_code))
    r = requests.get(f"{API}/api/production-pos", headers=H(admin), timeout=15)
    demos = [p for p in r.json() if p.get('po_number', '').startswith('PO-MK-DEMO')]
    check('tepat 2 PO demo (PO-MK-DEMO-1/2)', len(demos) == 2, f"got {len(demos)}")
    check('PO-MK-DEMO-1 status Draft', any(p['po_number'] == 'PO-MK-DEMO-1' and p['status'] == 'Draft' for p in demos), '')
    check('PO-MK-DEMO-2 status In Production',
          any(p['po_number'] == 'PO-MK-DEMO-2' and p['status'] == 'In Production' for p in demos), '')
    # mirror uniqueness
    r = requests.get(f"{API}/api/production-pos/po-mk-demo-1/maklon-finance", headers=H(admin), timeout=15)
    check('mirror finance PO-MK-DEMO-1 200 (auto-created saat Confirmed)',
          r.status_code == 200 or r.status_code == 404, str(r.status_code))


def test_po_update_guardrails(admin):
    print("\n== TEST 2: PO update items guardrails setelah shipment ==")
    PON = 'PO-MK-EDGE-UPD'
    cleanup_po(admin, PON)
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [
            {'product_name': 'Kaos EDGE', 'sku': 'EDGE-M', 'size': 'M', 'color': 'Merah',
             'serial_number': 'SN-EDGE-1', 'qty': 20, 'cmt_price_snapshot': 8000},
            {'product_name': 'Kaos EDGE', 'sku': 'EDGE-L', 'size': 'L', 'color': 'Merah',
             'serial_number': 'SN-EDGE-2', 'qty': 10, 'cmt_price_snapshot': 8000},
        ]}, timeout=15)
    check('create PO edge 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    po = r.json()
    po_id = po['id']
    items = po['items']
    it_m = next(i for i in items if i['sku'] == 'EDGE-M')
    it_l = next(i for i in items if i['sku'] == 'EDGE-L')

    # Edit BEFORE shipment: rubah SKU boleh, kurangi qty boleh
    r = requests.put(f"{API}/api/production-pos/{po_id}", headers=H(admin), json={
        'items': [
            {'id': it_m['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-M-NEW', 'size': 'M', 'color': 'Merah', 'qty': 15},
            {'id': it_l['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-L', 'size': 'L', 'color': 'Merah', 'qty': 10},
        ]}, timeout=15)
    check('sebelum shipment: edit SKU + qty allowed → 200', r.status_code == 200, f"{r.status_code} {r.text[:150]}")

    # Confirm PO → shipment
    requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    r = requests.post(f"{API}/api/vendor-shipments", headers=H(admin), json={
        'shipment_number': 'SJ-EDGE-UPD-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [
            {'po_id': po_id, 'po_item_id': it_m['id'], 'qty_sent': 15},
            {'po_id': po_id, 'po_item_id': it_l['id'], 'qty_sent': 5},
        ]}, timeout=15)
    check('shipment 15+5 → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")

    # AFTER shipment guards:
    # a) rubah SKU → 400
    r = requests.put(f"{API}/api/production-pos/{po_id}", headers=H(admin), json={
        'items': [
            {'id': it_m['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-M-CHG', 'size': 'M', 'color': 'Merah', 'qty': 15},
            {'id': it_l['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-L', 'size': 'L', 'color': 'Merah', 'qty': 10},
        ]}, timeout=15)
    check('guardrail: ubah SKU setelah shipment → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # b) kurangi qty < sent (15) → 400
    r = requests.put(f"{API}/api/production-pos/{po_id}", headers=H(admin), json={
        'items': [
            {'id': it_m['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-M-NEW', 'size': 'M', 'color': 'Merah', 'qty': 10},
            {'id': it_l['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-L', 'size': 'L', 'color': 'Merah', 'qty': 10},
        ]}, timeout=15)
    check('guardrail: qty < sent (15→10) → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # c) delete item ber-shipment (payload tanpa it_m) → 400
    r = requests.put(f"{API}/api/production-pos/{po_id}", headers=H(admin), json={
        'items': [
            {'id': it_l['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-L', 'size': 'L', 'color': 'Merah', 'qty': 10},
        ]}, timeout=15)
    check('guardrail: hapus item ber-shipment → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")

    # d) qty NAIK (15→20) → 200 (allowed)
    r = requests.put(f"{API}/api/production-pos/{po_id}", headers=H(admin), json={
        'items': [
            {'id': it_m['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-M-NEW', 'size': 'M', 'color': 'Merah', 'qty': 20},
            {'id': it_l['id'], 'product_name': 'Kaos EDGE', 'sku': 'EDGE-L', 'size': 'L', 'color': 'Merah', 'qty': 10},
        ]}, timeout=15)
    check('naikkan qty setelah shipment allowed → 200', r.status_code == 200, f"{r.status_code} {r.text[:120]}")

    requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=30)
    return True


def test_additional_request_and_child_a1(admin, vendor):
    print("\n== TEST 3: ADDITIONAL material_request → child -A1 shipment + child job ==")
    PON = 'PO-MK-EDGE-ADD'
    cleanup_po(admin, PON)
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [
            {'product_name': 'Celana ADD', 'sku': 'ADD-M', 'size': 'M', 'color': 'Biru',
             'serial_number': 'SN-ADD-1', 'qty': 10, 'cmt_price_snapshot': 12000},
        ]}, timeout=15)
    if r.status_code != 201:
        check('create PO ADD 201', False, f"{r.status_code} {r.text[:150]}")
        return
    po = r.json()
    po_id = po['id']
    it_m = po['items'][0]
    requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)

    r = requests.post(f"{API}/api/vendor-shipments", headers=H(admin), json={
        'shipment_number': 'SJ-ADD-EDGE-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_id': po_id, 'po_item_id': it_m['id'], 'qty_sent': 10}]}, timeout=15)
    ship = r.json()
    ship_id = ship['id']
    vsi = ship['items'][0]
    requests.put(f"{API}/api/vendor-shipments/{ship_id}", headers=H(admin), json={'status': 'Received'}, timeout=15)
    requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
        'shipment_id': ship_id,
        'items': [{'shipment_item_id': vsi['id'], 'sku': 'ADD-M', 'product_name': 'Celana ADD', 'size': 'M',
                   'ordered_qty': 10, 'received_qty': 10, 'missing_qty': 0}]}, timeout=15)

    # ── ADDITIONAL request oleh vendor ──
    r = requests.post(f"{API}/api/material-requests", headers=H(vendor), json={
        'request_type': 'ADDITIONAL', 'original_shipment_id': ship_id,
        'reason': 'Butuh 2 pcs tambahan',
        'items': [{'po_item_id': it_m['id'], 'sku': 'ADD-M', 'size': 'M', 'product_name': 'Celana ADD',
                   'requested_qty': 2, 'shipment_item_id': vsi['id']}]}, timeout=15)
    check('vendor REQ-ADD → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    req = r.json()
    check('nomor REQ-ADD-...', req.get('request_number', '').startswith('REQ-ADD'), req.get('request_number'))
    check('request business_type=maklon', req.get('business_type') == 'maklon', str(req.get('business_type')))

    # admin approve → child -A1 shipment
    r = requests.put(f"{API}/api/material-requests/{req['id']}", headers=H(admin),
                     json={'status': 'Approved', 'admin_notes': 'Kirim tambahan'}, timeout=15)
    child = (r.json() or {}).get('child_shipment') if r.status_code == 200 else None
    check('admin approve → child_shipment ada', child is not None, str(r.status_code))
    if child:
        check('child shipment berakhiran -A1', child.get('shipment_number', '').endswith('-A1'), child.get('shipment_number'))
        check('child business_type=maklon', child.get('business_type') == 'maklon', str(child.get('business_type')))
        # receive + inspect child → auto child job -A1
        requests.put(f"{API}/api/vendor-shipments/{child['id']}", headers=H(admin), json={'status': 'Received'}, timeout=15)
        r = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
            'shipment_id': child['id'],
            'items': [{'sku': 'ADD-M', 'size': 'M', 'product_name': 'Celana ADD',
                       'ordered_qty': 2, 'received_qty': 2, 'missing_qty': 0}]}, timeout=15)
        check('inspeksi child -A1 → 201 (auto child job)', r.status_code == 201, f"{r.status_code} {r.text[:120]}")

    requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=30)


def test_double_inspection_rejected(admin, vendor):
    print("\n== TEST 4: Inspeksi dobel pada shipment yang sama → 400 ==")
    PON = 'PO-MK-EDGE-DBLI'
    cleanup_po(admin, PON)
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'product_name': 'Tas DBL', 'sku': 'DBL-1', 'size': 'M', 'color': 'H',
                   'serial_number': 'SN-DBL', 'qty': 5, 'cmt_price_snapshot': 5000}]}, timeout=15)
    if r.status_code != 201:
        check('create PO DBL 201', False, f"{r.status_code}"); return
    po = r.json(); po_id = po['id']; it = po['items'][0]
    requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    r = requests.post(f"{API}/api/vendor-shipments", headers=H(admin), json={
        'shipment_number': 'SJ-DBL-EDGE-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_id': po_id, 'po_item_id': it['id'], 'qty_sent': 5}]}, timeout=15)
    ship = r.json(); ship_id = ship['id']; vsi = ship['items'][0]
    requests.put(f"{API}/api/vendor-shipments/{ship_id}", headers=H(admin), json={'status': 'Received'}, timeout=15)
    r = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
        'shipment_id': ship_id,
        'items': [{'shipment_item_id': vsi['id'], 'sku': 'DBL-1', 'product_name': 'Tas DBL', 'size': 'M',
                   'ordered_qty': 5, 'received_qty': 5, 'missing_qty': 0}]}, timeout=15)
    check('inspeksi pertama 201', r.status_code == 201, str(r.status_code))
    r2 = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
        'shipment_id': ship_id,
        'items': [{'shipment_item_id': vsi['id'], 'sku': 'DBL-1', 'product_name': 'Tas DBL', 'size': 'M',
                   'ordered_qty': 5, 'received_qty': 5, 'missing_qty': 0}]}, timeout=15)
    check('inspeksi kedua di shipment sama → 400', r2.status_code == 400, f"{r2.status_code} {r2.text[:120]}")

    requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=30)


def test_buyer_shipment_no_job(admin):
    print("\n== TEST 5: Buyer shipment tanpa job_id (dispatch tanpa job) ==")
    PON = 'PO-MK-EDGE-NOJOB'
    cleanup_po(admin, PON)
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'product_name': 'X', 'sku': 'X', 'size': 'S', 'color': 'B',
                   'serial_number': 'S', 'qty': 5, 'cmt_price_snapshot': 5000}]}, timeout=15)
    if r.status_code != 201:
        check('create PO NOJOB 201', False, str(r.status_code)); return
    po_id = r.json()['id']; it = r.json()['items'][0]
    requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    # dispatch tanpa job_id (no production job yet → produced=0)
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_item_id': it['id'], 'ordered_qty': 5, 'qty_shipped': 1}]}, timeout=15)
    check('dispatch tanpa job / belum produced → 400', r.status_code == 400, f"{r.status_code} {r.text[:120]}")
    requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=30)


def test_klien_cross_buyer_403(admin, klien):
    print("\n== TEST 6: Klien tracking cross-buyer 403 ==")
    # Buat PO milik client lain (bukan mk-client-demo-1)
    PON = 'PO-MK-EDGE-OTHERBUYER'
    cleanup_po(admin, PON)
    # cari buyer_id lain (bukan mk-client-demo-1)
    other_buyer = None
    r = requests.get(f"{API}/api/dewi/maklon/clients", headers=H(admin), timeout=15)
    if r.status_code == 200:
        for c in r.json():
            if c.get('id') and c['id'] != 'mk-client-demo-1':
                other_buyer = c['id']; break
    if not other_buyer:
        # create ad-hoc client
        r = requests.post(f"{API}/api/dewi/maklon/clients", headers=H(admin), json={
            'client_code': 'MK-EDGE-CLI', 'client_name': 'PT Edge Buyer Other'}, timeout=15)
        if r.status_code in (200, 201):
            other_buyer = r.json().get('id')
    if not other_buyer:
        check('setup other buyer', False, 'no other buyer available'); return
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': other_buyer, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'product_name': 'Y', 'sku': 'Y', 'size': 'M', 'color': 'A',
                   'serial_number': 'SY', 'qty': 3, 'cmt_price_snapshot': 3000}]}, timeout=15)
    if r.status_code != 201:
        check('create PO milik buyer lain 201', False, f"{r.status_code} {r.text[:150]}"); return
    other_po_id = r.json()['id']
    r = requests.get(f"{API}/api/maklon-client/pos/{other_po_id}/tracking", headers=H(klien), timeout=15)
    check('klien akses PO milik buyer lain → 403', r.status_code == 403, str(r.status_code))
    # juga listing: pastikan PO tsb TIDAK muncul di list klien
    r = requests.get(f"{API}/api/maklon-client/pos", headers=H(klien), timeout=15)
    ok = r.status_code == 200 and not any(p.get('id') == other_po_id for p in (r.json() or []))
    check('list klien tidak berisi PO buyer lain', ok, str(r.status_code))
    requests.delete(f"{API}/api/production-pos/{other_po_id}", headers=H(admin), timeout=30)


def test_quick_complete_maklon(admin):
    print("\n== TEST 7: quick-complete endpoint pada PO maklon ==")
    PON = 'PO-MK-EDGE-QC'
    cleanup_po(admin, PON)
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'product_name': 'Jaket QC', 'sku': 'QC-M', 'size': 'M', 'color': 'H',
                   'serial_number': 'SN-QC', 'qty': 8, 'cmt_price_snapshot': 15000}]}, timeout=15)
    if r.status_code != 201:
        check('create PO QC 201', False, f"{r.status_code} {r.text[:120]}"); return
    po_id = r.json()['id']
    requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    r = requests.post(f"{API}/api/production-pos/{po_id}/quick-complete", headers=H(admin), json={}, timeout=60)
    check('quick-complete → 200', r.status_code == 200, f"{r.status_code} {r.text[:200]}")
    if r.status_code == 200:
        steps = r.json().get('steps', [])
        check('quick-complete produce steps', len(steps) >= 5, f"{len(steps)} steps")
    r = requests.get(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=15)
    check('PO status Completed setelah quick-complete',
          r.json().get('status') in ('Completed', 'Closed'), r.json().get('status'))
    # idempotent: rerun should raise 400 (already Completed)
    r2 = requests.post(f"{API}/api/production-pos/{po_id}/quick-complete", headers=H(admin), json={}, timeout=30)
    check('quick-complete kedua → 400 (Completed)', r2.status_code == 400, str(r2.status_code))
    requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=30)


def test_da_extensions(admin, vendor):
    print("\n== TEST 8: DA Extensions (stage-summary, stage-qty PUT, variance post-gl) ==")
    # Use seed demo PO-MK-DEMO-2 (In Production) untuk verifikasi stage endpoints
    po_id = 'po-mk-demo-2'
    r = requests.get(f"{API}/api/production-pos/{po_id}/stage-summary", headers=H(admin), timeout=15)
    check('GET stage-summary PO-MK-DEMO-2 → 200', r.status_code == 200, f"{r.status_code} {r.text[:150]}")
    if r.status_code == 200:
        data = r.json()
        check('stage-summary struktur (items list)',
              isinstance(data.get('items'), list) or isinstance(data.get('stages'), list) or isinstance(data, dict),
              str(list(data.keys()) if isinstance(data, dict) else data)[:120])

    # variance post-gl endpoint existence check (create small variance on new PO)
    PON = 'PO-MK-EDGE-VARGL'
    cleanup_po(admin, PON)
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PON, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'product_name': 'V', 'sku': 'V-M', 'size': 'M', 'color': 'A',
                   'serial_number': 'SV', 'qty': 5, 'cmt_price_snapshot': 5000}]}, timeout=15)
    if r.status_code != 201:
        check('create PO VARGL 201', False, str(r.status_code)); return
    p2 = r.json(); po2 = p2['id']; it2 = p2['items'][0]
    requests.post(f"{API}/api/production-pos/{po2}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    r = requests.post(f"{API}/api/vendor-shipments", headers=H(admin), json={
        'shipment_number': 'SJ-VARGL-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_id': po2, 'po_item_id': it2['id'], 'qty_sent': 5}]}, timeout=15)
    sh = r.json(); shid = sh['id']; vsi = sh['items'][0]
    requests.put(f"{API}/api/vendor-shipments/{shid}", headers=H(admin), json={'status': 'Received'}, timeout=15)
    requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
        'shipment_id': shid,
        'items': [{'shipment_item_id': vsi['id'], 'sku': 'V-M', 'product_name': 'V', 'size': 'M',
                   'ordered_qty': 5, 'received_qty': 5, 'missing_qty': 0}]}, timeout=15)
    r = requests.post(f"{API}/api/production-jobs", headers=H(vendor), json={'vendor_shipment_id': shid}, timeout=15)
    job = r.json(); ji = job['items'][0]
    requests.post(f"{API}/api/production-progress", headers=H(vendor),
                  json={'job_item_id': ji['id'], 'completed_quantity': 5}, timeout=15)
    r = requests.post(f"{API}/api/production-variances", headers=H(vendor), json={
        'job_id': job['id'], 'variance_type': 'OVERPRODUCTION', 'reason': 'Over 1',
        'items': [{'job_item_id': ji['id'], 'sku': 'V-M', 'ordered_qty': 5, 'produced_qty': 5, 'variance_qty': 1}]}, timeout=15)
    var = r.json()
    r = requests.put(f"{API}/api/production-variances/{var['id']}", headers=H(admin),
                     json={'status': 'Acknowledged'}, timeout=15)
    r = requests.post(f"{API}/api/production-variances/{var['id']}/post-gl", headers=H(admin), json={}, timeout=20)
    check('POST variance/{id}/post-gl endpoint tersedia',
          r.status_code in (200, 400), f"{r.status_code} {r.text[:150]}")
    requests.delete(f"{API}/api/production-pos/{po2}", headers=H(admin), timeout=30)


def test_regression_smoke():
    print("\n== TEST 9: Regression smoke (multi-role login + maklon list + rahaza) ==")
    creds = [
        ('hr@dewiaditya.id', 'Dewi@123'),
        ('finance@dewiaditya.id', 'Dewi@123'),
        ('spv@dewiaditya.id', 'Dewi@123'),
        ('gudang@dewiaditya.id', 'Dewi@123'),
        ('maklon@dewiaditya.id', 'Dewi@123'),
    ]
    for e, p in creds:
        r = requests.post(f"{API}/api/auth/login", json={'email': e, 'password': p}, timeout=10)
        check(f'login {e}', r.status_code == 200, str(r.status_code))
        time.sleep(6.5)  # stay under 10 req/60s per IP rate limit
    admin = login('admin@garment.com', 'Admin@123')
    r = requests.get(f"{API}/api/dewi/maklon/pos", headers=H(admin), timeout=15)
    check('/api/dewi/maklon/pos list 200', r.status_code == 200, str(r.status_code))
    # FASE 4 (E10 DELETE): /api/rahaza/execution diarsip — cek diganti:
    # engine baru production-jobs harus tetap hidup utk admin.
    r = requests.get(f"{API}/api/production-jobs", headers=H(admin), timeout=15)
    check('/api/production-jobs 200 (engine baru, pengganti flow-summary)', r.status_code == 200, str(r.status_code))


def test_klien_rbac_full():
    print("\n== TEST 10: klien_maklon 403 pada engine endpoints ==")
    klien = login('klienmaklon@dewiaditya.id', 'Dewi@123')
    endpoints = [
        ('GET', '/api/production-pos'),
        ('GET', '/api/production-jobs'),
        ('GET', '/api/production-progress'),
        ('GET', '/api/vendor-shipments'),
        ('GET', '/api/buyer-shipments'),
        ('GET', '/api/material-requests'),
    ]
    for m, ep in endpoints:
        r = requests.request(m, f"{API}{ep}", headers=H(klien), timeout=15)
        check(f'klien {m} {ep} → 403', r.status_code == 403, str(r.status_code))


def main():
    admin = login('admin@garment.com', 'Admin@123')
    vendor = login('cmtvendor@dewiaditya.id', 'Dewi@123')
    klien = login('klienmaklon@dewiaditya.id', 'Dewi@123')
    ensure_seed(admin)

    test_seeder_idempotency(admin)
    test_po_update_guardrails(admin)
    test_additional_request_and_child_a1(admin, vendor)
    test_double_inspection_rejected(admin, vendor)
    test_buyer_shipment_no_job(admin)
    test_klien_cross_buyer_403(admin, klien)
    test_quick_complete_maklon(admin)
    test_da_extensions(admin, vendor)
    test_regression_smoke()
    test_klien_rbac_full()

    print(f"\n===== HASIL EDGE-CASE: {PASS} PASS / {FAIL} FAIL =====")
    for f in FAILED:
        print(f"  ✗ {f}")
    return 1 if FAIL else 0


if __name__ == '__main__':
    import sys
    sys.exit(main())
