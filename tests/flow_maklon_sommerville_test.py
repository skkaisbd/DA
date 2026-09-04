"""POC Fase 2 — Maklon Backend Port (identik SOMMERVILLE).

Menguji seluruh acceptance criteria via API (localhost:8001):
  AC-1 happy path penuh, AC-2 edge cases (I-1/I-3/C-1/transisi ilegal),
  AC-3 variance OVER/UNDER, AC-4 RBAC (cmt_vendor & klien_maklon),
  AC-5 finance adapter (mirror dewi_maklon_pos + post-ar ke GL).

Prasyarat: POST /api/seed/maklon-full sudah dijalankan (master + user demo).
Self-cleanup: PO uji dihapus via cascade delete + residu variance/mirror via pymongo.
"""
import os
import sys
import requests

API = os.environ.get('API_URL', 'http://localhost:8001')
PO_NUMBER = 'PO-MK-POC-001'

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
    assert r.status_code == 200, f"login {email} failed: {r.status_code} {r.text[:200]}"
    return r.json()['token']


def H(tok):
    return {'Authorization': f'Bearer {tok}'}


def main():
    print("== Login (admin, cmt_vendor, klien_maklon) ==")
    admin = login('admin@garment.com', 'Admin@123')
    vendor = login('cmtvendor@dewiaditya.id', 'Dewi@123')
    klien = login('klienmaklon@dewiaditya.id', 'Dewi@123')
    check('login 3 aktor', True)

    # cleanup leftover from previous run
    r = requests.get(f"{API}/api/production-pos", headers=H(admin), params={'search': PO_NUMBER}, timeout=15)
    for po in (r.json() if r.status_code == 200 else []):
        if po.get('po_number') == PO_NUMBER:
            requests.delete(f"{API}/api/production-pos/{po['id']}", headers=H(admin), timeout=15)

    # ── AC-1.1 Create PO maklon (master resolve DA: dewi_maklon_clients + vendor_partners) ──
    print("== AC-1: Happy path ==")
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': PO_NUMBER, 'business_type': 'maklon',
        'buyer_id': 'mk-client-demo-1', 'vendor_id': 'mk-vendor-demo-1',
        'items': [
            {'product_name': 'Kemeja POC', 'sku': 'POC-M', 'size': 'M', 'color': 'Hitam',
             'serial_number': 'SN-POC-A', 'qty': 100, 'cmt_price_snapshot': 10000},
            {'product_name': 'Kemeja POC', 'sku': 'POC-L', 'size': 'L', 'color': 'Hitam',
             'serial_number': 'SN-POC-B', 'qty': 50, 'cmt_price_snapshot': 10000},
        ],
    }, timeout=15)
    check('create PO maklon 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    po = r.json()
    po_id = po['id']
    check('business_type=maklon tersimpan', po.get('business_type') == 'maklon', str(po.get('business_type')))
    check('buyer resolve dari dewi_maklon_clients', po.get('customer_name') == 'PT Aruna Activewear', po.get('customer_name'))
    check('vendor resolve dari vendor_partners', po.get('vendor_name') == 'CV Jahit Mitra CMT', po.get('vendor_name'))
    items = po['items']
    it_m = next(i for i in items if i['sku'] == 'POC-M')
    it_l = next(i for i in items if i['sku'] == 'POC-L')

    # business_type invalid ditolak
    r = requests.post(f"{API}/api/production-pos", headers=H(admin), json={
        'po_number': 'PO-MK-POC-BAD', 'business_type': 'tokoonline', 'items': []}, timeout=15)
    check('business_type invalid → 400', r.status_code == 400, str(r.status_code))

    # PO accessories
    r = requests.post(f"{API}/api/po-accessories", headers=H(admin), json={
        'po_id': po_id, 'items': [{'accessory_name': 'Kancing POC', 'accessory_code': 'KCG-POC',
                                   'qty_needed': 300, 'unit': 'pcs'}]}, timeout=15)
    check('add po_accessories 201', r.status_code == 201, str(r.status_code))

    # AC-2 State machine PO (DA bug-fix): lompatan ilegal ditolak saat Draft
    r = requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Closed'}, timeout=15)
    check('AC-2 state machine: Draft → Closed → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'In Production'}, timeout=15)
    check('AC-2 state machine: Draft → In Production (lompat) → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-pos/{po_id}/close", headers=H(admin), json={'close_reason': 'test'}, timeout=15)
    check('AC-2 close manual saat Draft → 400', r.status_code == 400, str(r.status_code))

    # AC-1.2 Confirm → mirror finance + Draft AR otomatis (hook)
    r = requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Confirmed'}, timeout=15)
    check('transisi Draft→Confirmed', r.status_code == 200 and r.json().get('status') == 'Confirmed', f"{r.status_code}")
    r = requests.get(f"{API}/api/production-pos/{po_id}/maklon-finance", headers=H(admin), timeout=15)
    check('AC-5a mirror dewi_maklon_pos terbentuk otomatis', r.status_code == 200, f"{r.status_code} {r.text[:150]}")
    fin = r.json() if r.status_code == 200 else {}
    ar_inv = (fin.get('ar_invoice') or {})
    check('AC-5b Draft AR Invoice otomatis (total 1.5jt)', ar_inv.get('status') == 'draft' and ar_inv.get('total_amount') == 1500000.0,
          f"{ar_inv.get('status')} {ar_inv.get('total_amount')}")

    # transisi ilegal
    r = requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(admin), json={'status': 'Terkirim'}, timeout=15)
    check('AC-2 transisi status ilegal → 400', r.status_code == 400, str(r.status_code))

    # AC-1.3 Vendor shipment NORMAL
    r = requests.post(f"{API}/api/vendor-shipments", headers=H(admin), json={
        'shipment_number': 'SJ-POC-001', 'vendor_id': 'mk-vendor-demo-1',
        'items': [
            {'po_id': po_id, 'po_item_id': it_m['id'], 'qty_sent': 100},
            {'po_id': po_id, 'po_item_id': it_l['id'], 'qty_sent': 50},
        ]}, timeout=15)
    check('create vendor shipment 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    ship = r.json()
    ship_id = ship['id']
    check('shipment business_type=maklon (GDG-1/D4 owner)', ship.get('business_type') == 'maklon', str(ship.get('business_type')))

    # Phase 8.5 guard: NORMAL over-ship
    r = requests.post(f"{API}/api/vendor-shipments", headers=H(admin), json={
        'shipment_number': 'SJ-POC-002', 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_id': po_id, 'po_item_id': it_m['id'], 'qty_sent': 1}]}, timeout=15)
    check('AC-2 NORMAL shipment melebihi sisa → 400', r.status_code == 400, str(r.status_code))

    # AC-2: job sebelum shipment Received → 400
    r = requests.post(f"{API}/api/production-jobs", headers=H(vendor), json={'vendor_shipment_id': ship_id}, timeout=15)
    check('AC-2 job sebelum Received → 400', r.status_code == 400, str(r.status_code))

    # Terima shipment
    r = requests.put(f"{API}/api/vendor-shipments/{ship_id}", headers=H(admin), json={'status': 'Received'}, timeout=15)
    check('shipment → Received', r.status_code == 200, str(r.status_code))
    r = requests.put(f"{API}/api/vendor-shipments/{ship_id}", headers=H(admin), json={'status': 'Sent'}, timeout=15)
    check('AC-2 shipment Received → Sent (mundur) → 400', r.status_code == 400, str(r.status_code))

    # AC-2: job sebelum inspeksi → 400
    r = requests.post(f"{API}/api/production-jobs", headers=H(vendor), json={'vendor_shipment_id': ship_id}, timeout=15)
    check('AC-2 job sebelum inspeksi → 400', r.status_code == 400, str(r.status_code))

    # AC-1.4 Inspeksi oleh VENDOR (missing 5 di item L)
    ship_items = ship['items']
    vsi_m = next(s for s in ship_items if s['sku'] == 'POC-M')
    vsi_l = next(s for s in ship_items if s['sku'] == 'POC-L')
    r = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
        'shipment_id': ship_id,
        'items': [
            {'shipment_item_id': vsi_m['id'], 'sku': 'POC-M', 'product_name': 'Kemeja POC', 'size': 'M',
             'ordered_qty': 100, 'received_qty': 100, 'missing_qty': 0},
            {'shipment_item_id': vsi_l['id'], 'sku': 'POC-L', 'product_name': 'Kemeja POC', 'size': 'L',
             'ordered_qty': 50, 'received_qty': 45, 'missing_qty': 5},
        ],
        'accessory_items': [
            {'accessory_name': 'Kancing POC', 'accessory_code': 'KCG-POC', 'unit': 'pcs',
             'ordered_qty': 300, 'received_qty': 290, 'missing_qty': 10},
        ]}, timeout=15)
    check('inspeksi oleh vendor 201 (received 145, missing 5)', r.status_code == 201, f"{r.status_code} {r.text[:200]}")

    # auto REQ-ACC utk aksesoris missing
    r = requests.get(f"{API}/api/material-requests", headers=H(admin), params={'vendor_id': 'mk-vendor-demo-1'}, timeout=15)
    reqs = [q for q in r.json() if q.get('po_id') == po_id and q.get('category') == 'accessories']
    check('auto material request REQ-ACC (aksesoris missing)', len(reqs) == 1 and reqs[0]['request_number'].startswith('REQ-ACC'),
          str([q.get('request_number') for q in reqs]))

    # AC-1.5 Vendor membuat production job
    r = requests.post(f"{API}/api/production-jobs", headers=H(vendor), json={'vendor_shipment_id': ship_id}, timeout=15)
    check('vendor create job 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    job = r.json()
    job_id = job['id']
    check('job business_type=maklon', job.get('business_type') == 'maklon', str(job.get('business_type')))
    ji_m = next(j for j in job['items'] if j['sku'] == 'POC-M')
    ji_l = next(j for j in job['items'] if j['sku'] == 'POC-L')
    check('available_qty ikut inspeksi (100/45)', ji_m['available_qty'] == 100 and ji_l['available_qty'] == 45,
          f"{ji_m['available_qty']}/{ji_l['available_qty']}")
    r = requests.get(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=15)
    check('PO status → In Production', r.json().get('status') == 'In Production', r.json().get('status'))

    # AC-2 I-1: progress melebihi available
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': ji_m['id'], 'completed_quantity': 101}, timeout=15)
    check('AC-2 I-1 progress 101 > available 100 → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': ji_m['id'], 'completed_quantity': 60}, timeout=15)
    check('progress item M +60 → 201', r.status_code == 201, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': ji_m['id'], 'completed_quantity': 50}, timeout=15)
    check('AC-2 I-1 kumulatif 60+50 > 100 → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': ji_m['id'], 'completed_quantity': 40}, timeout=15)
    check('progress item M +40 (total 100) → 201', r.status_code == 201, str(r.status_code))

    # Defect report (vendor) memotong kapasitas item L (I-1 defect-adjusted / H-3)
    r = requests.post(f"{API}/api/material-defect-reports", headers=H(vendor), json={
        'job_item_id': ji_l['id'], 'po_id': po_id, 'po_item_id': it_l['id'],
        'defect_qty': 5, 'defect_type': 'Material Cacat', 'description': 'Kain sobek POC'}, timeout=15)
    check('defect report 5 pcs oleh vendor → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    check('defect business_type=maklon', r.json().get('business_type') == 'maklon', str(r.json().get('business_type')))
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': ji_l['id'], 'completed_quantity': 45}, timeout=15)
    check('AC-2 I-1 defect: 45 > usable 40 → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': ji_l['id'], 'completed_quantity': 40}, timeout=15)
    check('progress item L +40 (usable penuh) → 201', r.status_code == 201, str(r.status_code))

    # AC-1.6 Buyer shipment (dispatch bertahap) + C-1 cap
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_item_id': it_m['id'], 'job_item_id': ji_m['id'], 'ordered_qty': 100, 'qty_shipped': 70}]}, timeout=15)
    check('dispatch #1 (70 pcs) → 201', r.status_code == 201, f"{r.status_code} {r.text[:200]}")
    bs = r.json()
    bs_id = bs['id']
    check('buyer shipment business_type=maklon', bs.get('business_type') == 'maklon', str(bs.get('business_type')))
    check('dispatch_seq = 1', bs.get('dispatch_seq') == 1, str(bs.get('dispatch_seq')))
    d1_item_id = bs['items'][0]['id']
    r = requests.put(f"{API}/api/buyer-shipments/{bs_id}", headers=H(admin), json={'ship_status': 'Shipped'}, timeout=15)
    check('AC-2 ship_status manual → 400 (dikelola engine)', r.status_code == 400, str(r.status_code))

    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_item_id': it_m['id'], 'job_item_id': ji_m['id'], 'ordered_qty': 100, 'qty_shipped': 40}]}, timeout=15)
    check('AC-2 C-1 ship 70+40 > produced 100 → 400', r.status_code == 400, str(r.status_code))

    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_item_id': it_m['id'], 'job_item_id': ji_m['id'], 'ordered_qty': 100, 'qty_shipped': 30},
                  {'po_item_id': it_l['id'], 'job_item_id': ji_l['id'], 'ordered_qty': 50, 'qty_shipped': 40}]}, timeout=15)
    check('dispatch #2 (30+40) → 200 (dispatch_seq 2)', r.status_code == 200 and r.json().get('dispatch_seq') == 2,
          f"{r.status_code} seq={r.json().get('dispatch_seq') if r.status_code == 200 else '-'}")

    # Phase 17-19 received-based cap: kekurangan diterima membuka kapasitas re-ship
    r = requests.put(f"{API}/api/buyer-shipment-items/{d1_item_id}/received", headers=H(admin),
                     json={'qty_received': 60, 'reason': 'Kurang 10 saat diterima klien'}, timeout=15)
    check('set qty_received 60 (variance 10) → 200', r.status_code == 200 and r.json().get('variance') == 10,
          f"{r.status_code}")
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_item_id': it_m['id'], 'job_item_id': ji_m['id'], 'ordered_qty': 100, 'qty_shipped': 10}]}, timeout=15)
    check('re-ship 10 pcs shortfall (received-based cap) → 200', r.status_code == 200, f"{r.status_code} {r.text[:150]}")
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(admin), json={
        'po_id': po_id, 'job_id': job_id, 'vendor_id': 'mk-vendor-demo-1',
        'items': [{'po_item_id': it_m['id'], 'job_item_id': ji_m['id'], 'ordered_qty': 100, 'qty_shipped': 1}]}, timeout=15)
    check('AC-2 ship 1 pcs lagi melebihi cap → 400', r.status_code == 400, str(r.status_code))

    # AC-3 Variance OVER/UNDER = fitur, bukan error
    print("== AC-3: Variance ==")
    r = requests.post(f"{API}/api/production-variances", headers=H(vendor), json={
        'job_id': job_id, 'variance_type': 'UNDERPRODUCTION', 'reason': 'Bahan cacat 5 + missing 5',
        'items': [{'job_item_id': ji_l['id'], 'sku': 'POC-L', 'ordered_qty': 50, 'produced_qty': 40, 'variance_qty': 10}]}, timeout=15)
    check('variance UNDER oleh vendor → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    var_under = r.json()
    check('variance business_type=maklon', var_under.get('business_type') == 'maklon', str(var_under.get('business_type')))
    r = requests.post(f"{API}/api/production-variances", headers=H(vendor), json={
        'job_id': job_id, 'variance_type': 'OVERPRODUCTION', 'reason': 'Simulasi over',
        'items': [{'job_item_id': ji_m['id'], 'sku': 'POC-M', 'ordered_qty': 100, 'produced_qty': 100, 'variance_qty': 2}]}, timeout=15)
    check('variance OVER oleh vendor → 201', r.status_code == 201, str(r.status_code))
    r = requests.put(f"{API}/api/production-variances/{var_under['id']}", headers=H(admin),
                     json={'status': 'Acknowledged', 'admin_notes': 'OK'}, timeout=15)
    check('admin acknowledge variance → 200', r.status_code == 200, str(r.status_code))
    r = requests.put(f"{API}/api/production-variances/{var_under['id']}", headers=H(admin),
                     json={'status': 'Reported'}, timeout=15)
    check('AC-2 variance Acknowledged → Reported (mundur) → 400', r.status_code == 400, str(r.status_code))

    # AC-2 I-3: retur melebihi shipped-returned
    print("== Returns (I-3) ==")
    r = requests.post(f"{API}/api/production-returns", headers=H(admin), json={
        'reference_po_id': po_id,
        'items': [{'po_item_id': it_m['id'], 'sku': 'POC-M', 'return_qty': 200, 'defect_type': 'Jahitan'}]}, timeout=15)
    check('AC-2 I-3 retur 200 > shipped → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-returns", headers=H(admin), json={
        'reference_po_id': po_id,
        'items': [{'po_item_id': it_m['id'], 'sku': 'POC-M', 'return_qty': 20, 'defect_type': 'Jahitan'}]}, timeout=15)
    check('retur 20 pcs → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    check('retur business_type=maklon', r.json().get('business_type') == 'maklon', str(r.json().get('business_type')))

    # E11: material request REPLACEMENT oleh vendor → admin approve → child shipment -R1 → child job
    print("== E11: Material request REPLACEMENT + child job ==")
    r = requests.post(f"{API}/api/material-requests", headers=H(vendor), json={
        'request_type': 'REPLACEMENT', 'original_shipment_id': ship_id,
        'reason': 'Ganti 5 pcs kain cacat',
        'items': [{'po_item_id': it_l['id'], 'sku': 'POC-L', 'size': 'L', 'product_name': 'Kemeja POC',
                   'requested_qty': 5, 'shipment_item_id': vsi_l['id']}]}, timeout=15)
    check('vendor REQ-RPL → 201', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    rpl = r.json()
    check('nomor REQ-RPL-...', rpl.get('request_number', '').startswith('REQ-RPL-'), rpl.get('request_number'))
    check('request business_type=maklon', rpl.get('business_type') == 'maklon', str(rpl.get('business_type')))

    r = requests.put(f"{API}/api/material-requests/{rpl['id']}", headers=H(vendor), json={'status': 'Approved'}, timeout=15)
    check('AC-4 vendor approve request sendiri → 403', r.status_code == 403, str(r.status_code))
    r = requests.put(f"{API}/api/material-requests/{rpl['id']}", headers=H(admin),
                     json={'status': 'Approved', 'admin_notes': 'Kirim pengganti'}, timeout=15)
    check('admin approve REQ-RPL → child shipment', r.status_code == 200 and r.json().get('child_shipment'), str(r.status_code))
    child_ship = r.json()['child_shipment']
    check('child shipment -R1 + business_type maklon',
          child_ship.get('shipment_number', '').endswith('-R1') and child_ship.get('business_type') == 'maklon',
          f"{child_ship.get('shipment_number')} {child_ship.get('business_type')}")

    r = requests.put(f"{API}/api/material-requests/{rpl['id']}", headers=H(admin),
                     json={'status': 'Rejected', 'admin_notes': 'coba ubah'}, timeout=15)
    check('AC-2 ubah keputusan Approved → Rejected → 400', r.status_code == 400, str(r.status_code))
    r = requests.put(f"{API}/api/vendor-shipments/{child_ship['id']}", headers=H(admin), json={'status': 'Received'}, timeout=15)
    check('child shipment → Received', r.status_code == 200, str(r.status_code))
    r = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vendor), json={
        'shipment_id': child_ship['id'],
        'items': [{'sku': 'POC-L', 'size': 'L', 'product_name': 'Kemeja POC',
                   'ordered_qty': 5, 'received_qty': 5, 'missing_qty': 0}]}, timeout=15)
    check('inspeksi child shipment → auto child job', r.status_code == 201, f"{r.status_code} {r.text[:150]}")
    r = requests.get(f"{API}/api/production-jobs/{job_id}", headers=H(admin), timeout=15)
    child_jobs = r.json().get('child_jobs', [])
    check('child job -R1 terbentuk (business_type maklon)',
          len(child_jobs) == 1 and child_jobs[0].get('job_number', '').endswith('-R1')
          and child_jobs[0].get('business_type') == 'maklon',
          str([(c.get('job_number'), c.get('business_type')) for c in child_jobs]))

    # progress di child job (I-1 juga berlaku)
    r = requests.get(f"{API}/api/production-jobs/{child_jobs[0]['id']}", headers=H(vendor), timeout=15)
    cji = r.json()['items'][0]
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': cji['id'], 'completed_quantity': 6}, timeout=15)
    check('AC-2 I-1 child job progress 6 > available 5 → 400', r.status_code == 400, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(vendor),
                      json={'job_item_id': cji['id'], 'completed_quantity': 5}, timeout=15)
    check('progress child job +5 → 201 (total item L = 45)', r.status_code == 201, str(r.status_code))

    # AC-4 RBAC
    print("== AC-4: RBAC ==")
    r = requests.post(f"{API}/api/production-pos", headers=H(vendor), json={'po_number': 'X', 'business_type': 'maklon'}, timeout=15)
    check('cmt_vendor create PO → 403', r.status_code == 403, str(r.status_code))
    r = requests.post(f"{API}/api/production-pos/{po_id}/status", headers=H(vendor), json={'status': 'Closed'}, timeout=15)
    check('cmt_vendor transisi status PO → 403', r.status_code == 403, str(r.status_code))
    r = requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(vendor), timeout=15)
    check('cmt_vendor delete PO → 403', r.status_code == 403, str(r.status_code))
    r = requests.get(f"{API}/api/production-jobs", headers=H(vendor), timeout=15)
    jobs_v = r.json()
    check('cmt_vendor lihat jobs milik sendiri saja',
          r.status_code == 200 and all(j.get('vendor_id') == 'mk-vendor-demo-1' for j in jobs_v) and len(jobs_v) >= 1,
          f"{r.status_code} n={len(jobs_v) if isinstance(jobs_v, list) else '-'}")

    r = requests.get(f"{API}/api/production-pos", headers=H(klien), timeout=15)
    check('klien_maklon GET /production-pos → 403 (deny)', r.status_code == 403, str(r.status_code))
    r = requests.post(f"{API}/api/production-progress", headers=H(klien), json={'job_item_id': ji_m['id'], 'completed_quantity': 1}, timeout=15)
    check('klien_maklon tulis progress → 403', r.status_code == 403, str(r.status_code))

    # Klien tracking read-only
    r = requests.get(f"{API}/api/maklon-client/pos", headers=H(klien), timeout=15)
    my_pos = r.json() if r.status_code == 200 else []
    poc_row = next((p for p in my_pos if p['po_number'] == PO_NUMBER), None)
    check('klien lihat PO miliknya di /maklon-client/pos', poc_row is not None, f"{r.status_code} n={len(my_pos)}")
    check('progress_pct terhitung', poc_row and poc_row.get('total_produced') == 145 and poc_row.get('total_ordered') == 150,
          str(poc_row and (poc_row.get('total_produced'), poc_row.get('total_ordered'))))
    r = requests.get(f"{API}/api/maklon-client/pos/{po_id}/tracking", headers=H(klien), timeout=15)
    trk = r.json() if r.status_code == 200 else {}
    check('klien tracking detail: 3 dispatch', len(trk.get('dispatches', [])) == 3, str(len(trk.get('dispatches', []))))
    r = requests.get(f"{API}/api/maklon-client/pos/po-mk-demo-2/tracking", headers=H(klien), timeout=15)
    check('klien tracking PO demo lain miliknya → 200', r.status_code == 200, str(r.status_code))

    # AC-5 Finance adapter end-to-end: post AR ke GL via modul finance existing
    print("== AC-5: Finance adapter → GL ==")
    r = requests.post(f"{API}/api/dewi/maklon/finance/pos/{po_id}/post-ar", headers=H(admin), timeout=20)
    resp = r.json() if r.status_code == 200 else {}
    ok_post = r.status_code == 200 and (resp.get('status') == 'posted' or resp.get('already_posted'))
    check('post-ar via dewi_maklon_finance → JE GL terbentuk', ok_post, f"{r.status_code} {r.text[:200]}")
    je_id = resp.get('je_id')
    if ok_post:
        check('JE number ada', bool(resp.get('je_number')), str(resp)[:120])

    # PO quantity summary (I-5 over/under terekspos, bukan error)
    r = requests.get(f"{API}/api/production-pos/{po_id}/quantity-summary", headers=H(admin), timeout=15)
    tot = r.json().get('totals', {}) if r.status_code == 200 else {}
    check('quantity-summary: produced 145, shipped 150, returned 20, underproduction 5',
          tot.get('produced') == 145 and tot.get('shipped') == 150 and tot.get('returned') == 20
          and tot.get('underproduction') == 5,
          str(tot))

    # ── Cleanup (DB pristine) ──
    print("== Cleanup ==")
    r = requests.delete(f"{API}/api/production-pos/{po_id}", headers=H(admin), timeout=30)
    check('cascade delete PO uji (superadmin)', r.status_code == 200, str(r.status_code))
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
        env = dotenv_values('/app/backend/.env')
        mdb = MongoClient(env['MONGO_URL'].strip('"'))[env['DB_NAME'].strip('"')]
        mdb.production_variances.delete_many({'po_id': po_id})
        mdb.dewi_maklon_pos.delete_many({'id': po_id})
        mdb.rahaza_ar_invoices.delete_many({'linked_maklon_po_id': po_id})
        if je_id:
            mdb.rahaza_journal_entries.delete_many({'id': je_id})
        print('  residu variance/mirror/AR dibersihkan')
    except Exception as e:
        print(f'  WARN cleanup residu: {e}')

    print(f"\n===== HASIL: {PASS} PASS / {FAIL} FAIL =====")
    for f_ in FAILED:
        print(f"  ✗ {f_}")
    sys.exit(1 if FAIL else 0)


if __name__ == '__main__':
    main()
