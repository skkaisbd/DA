"""
vendor_portal_e2e_scenarios.py — Verifikasi PORTAL VENDOR CMT end-to-end (seperti user).
3 skenario dari SET MASTER DATA → COMPLETE, mencatat INPUT/OUTPUT/EXPECTED.

Aktor:
  - admin@garment.com (DA / admin produksi)  — buat master, PO, dispatch, terima setoran, kirim buyer
  - vendor (cmt_vendor, dibuat per-skenario)  — inspeksi, buat job, progress, deklarasi setoran ke DA
  - klienmaklon@dewiaditya.id (klien)         — cek RBAC read-only

Prasyarat: POST /api/seed/maklon-full sudah dijalankan (master client mk-client-demo-1).
Self-clean di akhir. Jalankan: python3 tests/vendor_portal_e2e_scenarios.py
"""
import os, sys, json, requests
from datetime import datetime

API = os.environ.get('API_URL', 'http://localhost:8001')
VENDOR_PW = 'Vendor@123'
LOG = []          # list of dict steps for documentation
RESULT = {'pass': 0, 'fail': 0, 'failed': []}


def rec(scenario, step, method, path, req, resp_code, resp_body, expected, ok):
    """Catat 1 langkah untuk dokumentasi + hitung pass/fail."""
    LOG.append({
        'scenario': scenario, 'step': step, 'action': f'{method} {path}',
        'input': req, 'output_code': resp_code,
        'output': resp_body if isinstance(resp_body, (dict, list)) else str(resp_body)[:300],
        'expected': expected, 'status': 'PASS' if ok else 'FAIL',
    })
    if ok:
        RESULT['pass'] += 1
        print(f"  PASS [{scenario}] {step}")
    else:
        RESULT['fail'] += 1
        RESULT['failed'].append(f"[{scenario}] {step} — got {resp_code}: {str(resp_body)[:160]}")
        print(f"  FAIL [{scenario}] {step} — got {resp_code}: {str(resp_body)[:160]}")


def login(email, pw):
    r = requests.post(f"{API}/api/auth/login", json={'email': email, 'password': pw}, timeout=20)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text[:150]}"
    return r.json()['token']


def H(t):
    return {'Authorization': f'Bearer {t}'}


def _body(r):
    try:
        return r.json()
    except Exception:
        return r.text[:300]


class Ctx:
    def __init__(self, admin, klien):
        self.admin = admin
        self.klien = klien


def setup_master(ctx, scenario, partner_name, code, email):
    """M1 create partner + M2 create vendor account + login vendor."""
    # pre-clean: hapus akun (by email) dulu, lalu partner (by code) agar bisa re-run
    r = requests.get(f"{API}/api/vendor-portal/accounts", headers=H(ctx.admin), timeout=15)
    for a in (r.json() if r.status_code == 200 else []):
        if a.get('email') == email:
            requests.delete(f"{API}/api/vendor-portal/accounts/{a['id']}?hard=true", headers=H(ctx.admin), timeout=15)
    r = requests.get(f"{API}/api/vendor-portal/partners", headers=H(ctx.admin), timeout=15)
    for p in (r.json() if r.status_code == 200 else []):
        if p.get('code') == code:
            requests.delete(f"{API}/api/vendor-portal/partners/{p['id']}?hard=true", headers=H(ctx.admin), timeout=15)

    body = {'name': partner_name, 'code': code, 'contact_name': 'PIC ' + code,
            'contact_phone': '0812-0000-0001', 'address': 'Solo', 'capacity_pcs': 500}
    r = requests.post(f"{API}/api/vendor-portal/partners", headers=H(ctx.admin), json=body, timeout=15)
    ok = r.status_code in (200, 201)
    rec(scenario, 'M1 Buat Vendor Partner (master)', 'POST', '/api/vendor-portal/partners', body,
        r.status_code, _body(r), '201/200 + partner tersimpan', ok)
    partner = _body(r)
    partner_id = partner.get('id')

    acc = {'email': email, 'name': partner_name + ' (User)', 'password': VENDOR_PW, 'partner_id': partner_id}
    r = requests.post(f"{API}/api/vendor-portal/accounts", headers=H(ctx.admin), json={**acc, 'password': VENDOR_PW}, timeout=15)
    ok = r.status_code in (200, 201)
    rec(scenario, 'M2 Buat Akun Login Vendor (master)', 'POST', '/api/vendor-portal/accounts',
        {**acc, 'password': '***'}, r.status_code, _body(r), '201/200 + akun cmt_vendor terhubung partner', ok)

    vtok = login(email, VENDOR_PW)
    rec(scenario, 'M3 Login Portal Vendor', 'POST', '/api/auth/login', {'email': email, 'password': '***'},
        200, {'ok': True}, 'vendor bisa login (role cmt_vendor)', bool(vtok))
    return partner_id, vtok


def make_po(ctx, scenario, po_number, vendor_id, items):
    # Pre-clean: hapus PO lama dgn po_number sama agar script idempoten (bisa re-run).
    r = requests.get(f"{API}/api/production-pos", headers=H(ctx.admin), params={'search': po_number}, timeout=15)
    for old in (r.json() if r.status_code == 200 else []):
        if old.get('po_number') == po_number:
            requests.delete(f"{API}/api/production-pos/{old['id']}", headers=H(ctx.admin), timeout=30)
    body = {'po_number': po_number, 'business_type': 'maklon',
            'buyer_id': 'mk-client-demo-1', 'vendor_id': vendor_id, 'items': items}
    r = requests.post(f"{API}/api/production-pos", headers=H(ctx.admin), json=body, timeout=20)
    ok = r.status_code == 201
    rec(scenario, 'O1 Buat PO Maklon', 'POST', '/api/production-pos', body,
        r.status_code, _body(r), '201 + business_type=maklon', ok)
    po = _body(r)
    # Confirm
    r = requests.post(f"{API}/api/production-pos/{po['id']}/status", headers=H(ctx.admin),
                      json={'status': 'Confirmed'}, timeout=15)
    rec(scenario, 'O2 Konfirmasi PO (Draft→Confirmed)', 'POST', f"/api/production-pos/{po['id']}/status",
        {'status': 'Confirmed'}, r.status_code, _body(r), '200 status=Confirmed',
        r.status_code == 200 and _body(r).get('status') == 'Confirmed')
    return po


def dispatch(ctx, scenario, po, ship_no, vendor_id, lines):
    body = {'shipment_number': ship_no, 'vendor_id': vendor_id, 'items': lines}
    r = requests.post(f"{API}/api/vendor-shipments", headers=H(ctx.admin), json=body, timeout=20)
    ok = r.status_code == 201
    rec(scenario, 'D1 DA Dispatch Potongan ke CMT', 'POST', '/api/vendor-shipments', body,
        r.status_code, _body(r), '201 shipment Sent', ok)
    ship = _body(r)
    r = requests.put(f"{API}/api/vendor-shipments/{ship['id']}", headers=H(ctx.admin),
                     json={'status': 'Received'}, timeout=15)
    rec(scenario, 'D2 Tandai Shipment Received', 'PUT', f"/api/vendor-shipments/{ship['id']}",
        {'status': 'Received'}, r.status_code, _body(r), '200 status=Received', r.status_code == 200)
    return ship


def find_receipt(ctx, related_shipment_id, po_id):
    r = requests.get(f"{API}/api/prod/cmt-receipts", headers=H(ctx.admin), timeout=15)
    data = _body(r)
    rows = data if isinstance(data, list) else data.get('items', data.get('data', []))
    for x in rows:
        if x.get('related_shipment_id') == related_shipment_id:
            return x
    for x in rows:
        if x.get('po_id') == po_id and x.get('status') == 'Draft':
            return x
    return None


# ════════════════════════════════════════════════════════════════════════════
def scenario1(ctx):
    S = 'Skenario-1 HAPPY PATH'
    print(f"\n== {S} ==")
    vid, vtok = setup_master(ctx, S, 'CMT Alpha Jaya', 'CMT-ALP', 'alpha.cmt@dewi.test')
    po = make_po(ctx, S, 'PO-VP-S1', vid, [
        {'product_name': 'Hoodie Alpha', 'sku': 'ALP-M', 'size': 'M', 'color': 'Navy',
         'serial_number': 'SN-VP-S1-A', 'qty': 100, 'cmt_price_snapshot': 12000},
    ])
    it = po['items'][0]
    ship = dispatch(ctx, S, po, 'SJ-VP-S1', vid, [{'po_id': po['id'], 'po_item_id': it['id'], 'qty_sent': 100}])
    vsi = ship['items'][0]

    # V1 inspect (all accepted)
    body = {'shipment_id': ship['id'], 'items': [
        {'shipment_item_id': vsi['id'], 'sku': 'ALP-M', 'product_name': 'Hoodie Alpha', 'size': 'M',
         'ordered_qty': 100, 'received_qty': 100, 'missing_qty': 0}]}
    r = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vtok), json=body, timeout=20)
    rec(S, 'V1 Vendor Inspeksi Material (100 diterima)', 'POST', '/api/vendor-material-inspections',
        body, r.status_code, _body(r), '201 received 100 missing 0', r.status_code == 201)

    # V2 create job
    r = requests.post(f"{API}/api/production-jobs", headers=H(vtok), json={'vendor_shipment_id': ship['id']}, timeout=20)
    ok = r.status_code == 201
    rec(S, 'V2 Vendor Buat Job Produksi', 'POST', '/api/production-jobs', {'vendor_shipment_id': ship['id']},
        r.status_code, _body(r), '201 + item available_qty=100', ok and _body(r)['items'][0]['available_qty'] == 100)
    job = _body(r)
    ji = job['items'][0]

    # V3 progress 100 → job done
    r = requests.post(f"{API}/api/production-progress", headers=H(vtok),
                      json={'job_item_id': ji['id'], 'completed_quantity': 100}, timeout=20)
    rec(S, 'V3 Vendor Lapor Progress 100 (selesai)', 'POST', '/api/production-progress',
        {'job_item_id': ji['id'], 'completed_quantity': 100}, r.status_code, _body(r),
        '201 progress tercatat', r.status_code == 201)

    # V4 declare setoran ke DA (receiver_type=da) → auto cmt_receipt
    body = {'po_id': po['id'], 'job_id': job['id'], 'receiver_type': 'da',
            'items': [{'po_item_id': it['id'], 'job_item_id': ji['id'], 'ordered_qty': 100, 'qty_shipped': 100}]}
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(vtok), json=body, timeout=20)
    ok = r.status_code in (200, 201)
    rec(S, 'V4 Vendor Deklarasi Setoran ke DA', 'POST', '/api/buyer-shipments', body,
        r.status_code, _body(r), '201 receiver_type=da + auto cmt_receipt Draft', ok)
    da_ship = _body(r)

    # A1 DA find + fill + submit + approve receipt
    rcpt = find_receipt(ctx, da_ship.get('id'), po['id'])
    rec(S, 'A1 DA Temukan CMT Receipt (auto)', 'GET', '/api/prod/cmt-receipts', {'related_shipment_id': da_ship.get('id')},
        200 if rcpt else 404, rcpt or {}, 'receipt Draft auto-terbentuk', bool(rcpt))
    if rcpt:
        r = requests.get(f"{API}/api/prod/cmt-receipts/{rcpt['id']}", headers=H(ctx.admin), timeout=15)
        det = _body(r)
        lines = det.get('lines', det.get('items', []))
        line = lines[0]
        r = requests.put(f"{API}/api/prod/cmt-receipts/{rcpt['id']}/lines/{line['id']}", headers=H(ctx.admin),
                         json={'qty_actual': 100, 'reject_qty': 0}, timeout=15)
        rec(S, 'A2 DA Isi Qty Aktual (100 lolos, 0 reject)', 'PUT', f"/api/prod/cmt-receipts/{rcpt['id']}/lines/{line['id']}",
            {'qty_actual': 100, 'reject_qty': 0}, r.status_code, _body(r), '200 qty_actual=100', r.status_code == 200)
        r = requests.post(f"{API}/api/prod/cmt-receipts/{rcpt['id']}/submit", headers=H(ctx.admin), timeout=15)
        rec(S, 'A3 DA Submit Receipt', 'POST', f"/api/prod/cmt-receipts/{rcpt['id']}/submit", {},
            r.status_code, _body(r), '200 status=Submitted', r.status_code == 200)
        r = requests.post(f"{API}/api/prod/cmt-receipts/{rcpt['id']}/approve", headers=H(ctx.admin), timeout=20)
        rec(S, 'A4 DA Approve Receipt (FG masuk)', 'POST', f"/api/prod/cmt-receipts/{rcpt['id']}/approve", {},
            r.status_code, _body(r), '200 status=Approved', r.status_code == 200 and _body(r).get('status') == 'Approved')

        # A5 DA ship to buyer (receiver_type=buyer + source_receipt_ids)
        body = {'po_id': po['id'], 'vendor_id': vid, 'receiver_type': 'buyer', 'source_receipt_ids': [rcpt['id']],
                'items': [{'po_item_id': it['id'], 'ordered_qty': 100, 'qty_shipped': 100}]}
        r = requests.post(f"{API}/api/buyer-shipments", headers=H(ctx.admin), json=body, timeout=20)
        rec(S, 'A5 DA Kirim ke Buyer (COMPLETE)', 'POST', '/api/buyer-shipments', body,
            r.status_code, _body(r), '201/200 buyer shipment dari receipt approved', r.status_code in (200, 201))

    # Verify final PO summary
    r = requests.get(f"{API}/api/production-pos/{po['id']}/quantity-summary", headers=H(ctx.admin), timeout=15)
    tot = _body(r).get('totals', {}) if r.status_code == 200 else {}
    rec(S, 'X1 Ringkasan PO (produced=100)', 'GET', f"/api/production-pos/{po['id']}/quantity-summary", {},
        r.status_code, tot, 'produced=100', tot.get('produced') == 100)
    return po['id'], vid, 'alpha.cmt@dewi.test', 'CMT-ALP'


# ════════════════════════════════════════════════════════════════════════════
def scenario2(ctx):
    S = 'Skenario-2 REJECT & VARIANCE'
    print(f"\n== {S} ==")
    vid, vtok = setup_master(ctx, S, 'CMT Beta Karya', 'CMT-BET', 'beta.cmt@dewi.test')
    po = make_po(ctx, S, 'PO-VP-S2', vid, [
        {'product_name': 'Polo Beta', 'sku': 'BET-M', 'size': 'M', 'color': 'Merah',
         'serial_number': 'SN-VP-S2-A', 'qty': 100, 'cmt_price_snapshot': 15000}])
    it = po['items'][0]
    ship = dispatch(ctx, S, po, 'SJ-VP-S2', vid, [{'po_id': po['id'], 'po_item_id': it['id'], 'qty_sent': 100}])
    vsi = ship['items'][0]

    # V1 inspect with 5 missing
    body = {'shipment_id': ship['id'], 'items': [
        {'shipment_item_id': vsi['id'], 'sku': 'BET-M', 'product_name': 'Polo Beta', 'size': 'M',
         'ordered_qty': 100, 'received_qty': 95, 'missing_qty': 5}]}
    r = requests.post(f"{API}/api/vendor-material-inspections", headers=H(vtok), json=body, timeout=20)
    rec(S, 'V1 Vendor Inspeksi (95 diterima, 5 KURANG)', 'POST', '/api/vendor-material-inspections', body,
        r.status_code, _body(r), '201 received 95 missing 5', r.status_code == 201)

    r = requests.post(f"{API}/api/production-jobs", headers=H(vtok), json={'vendor_shipment_id': ship['id']}, timeout=20)
    job = _body(r)
    ji = job['items'][0]
    rec(S, 'V2 Vendor Buat Job (available=95 ikut inspeksi)', 'POST', '/api/production-jobs',
        {'vendor_shipment_id': ship['id']}, r.status_code, {'available_qty': ji.get('available_qty')},
        '201 available_qty=95', r.status_code == 201 and ji.get('available_qty') == 95)

    r = requests.post(f"{API}/api/production-progress", headers=H(vtok),
                      json={'job_item_id': ji['id'], 'completed_quantity': 95}, timeout=20)
    rec(S, 'V3 Vendor Progress 95', 'POST', '/api/production-progress',
        {'job_item_id': ji['id'], 'completed_quantity': 95}, r.status_code, _body(r), '201', r.status_code == 201)

    body = {'po_id': po['id'], 'job_id': job['id'], 'receiver_type': 'da',
            'items': [{'po_item_id': it['id'], 'job_item_id': ji['id'], 'ordered_qty': 100, 'qty_shipped': 95}]}
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(vtok), json=body, timeout=20)
    rec(S, 'V4 Vendor Deklarasi Setoran 95', 'POST', '/api/buyer-shipments', body,
        r.status_code, _body(r), '201 receiver_type=da', r.status_code in (200, 201))
    da_ship = _body(r)

    # V5 variance UNDERPRODUCTION
    body = {'job_id': job['id'], 'variance_type': 'UNDERPRODUCTION', 'reason': 'Bahan kurang 5',
            'items': [{'job_item_id': ji['id'], 'sku': 'BET-M', 'ordered_qty': 100, 'produced_qty': 95, 'variance_qty': 5}]}
    r = requests.post(f"{API}/api/production-variances", headers=H(vtok), json=body, timeout=20)
    rec(S, 'V5 Vendor Lapor Variance UNDER (5)', 'POST', '/api/production-variances', body,
        r.status_code, _body(r), '201 variance tercatat', r.status_code == 201)

    # A: receipt with 7 reject → pass 88/95
    rcpt = find_receipt(ctx, da_ship.get('id'), po['id'])
    rec(S, 'A1 DA Temukan Receipt', 'GET', '/api/prod/cmt-receipts', {}, 200 if rcpt else 404, rcpt or {},
        'auto receipt Draft', bool(rcpt))
    if rcpt:
        det = _body(requests.get(f"{API}/api/prod/cmt-receipts/{rcpt['id']}", headers=H(ctx.admin), timeout=15))
        line = det.get('lines', det.get('items', []))[0]
        r = requests.put(f"{API}/api/prod/cmt-receipts/{rcpt['id']}/lines/{line['id']}", headers=H(ctx.admin),
                         json={'qty_actual': 88, 'reject_qty': 7, 'reject_reason': 'Jahitan cacat'}, timeout=15)
        rec(S, 'A2 DA Isi Aktual (88 lolos, 7 REJECT)', 'PUT', f".../lines/{line['id']}",
            {'qty_actual': 88, 'reject_qty': 7}, r.status_code, _body(r), '200', r.status_code == 200)
        requests.post(f"{API}/api/prod/cmt-receipts/{rcpt['id']}/submit", headers=H(ctx.admin), timeout=15)
        r = requests.post(f"{API}/api/prod/cmt-receipts/{rcpt['id']}/approve", headers=H(ctx.admin), timeout=20)
        rec(S, 'A3 DA Approve (reject tercatat)', 'POST', f".../approve", {}, r.status_code, _body(r),
            '200 Approved total_rejected=7', r.status_code == 200)
        # verify pass rate via receipt summary
        det2 = _body(requests.get(f"{API}/api/prod/cmt-receipts/{rcpt['id']}", headers=H(ctx.admin), timeout=15))
        ta, tr = det2.get('total_actual'), det2.get('total_rejected')
        rec(S, 'X1 QC: total_actual=88 total_rejected=7', 'GET', f"/api/prod/cmt-receipts/{rcpt['id']}", {},
            200, {'total_actual': ta, 'total_rejected': tr}, 'actual 88 reject 7', ta == 88 and tr == 7)
    return po['id'], vid, 'beta.cmt@dewi.test', 'CMT-BET'


# ════════════════════════════════════════════════════════════════════════════
def scenario3(ctx, alpha_vid):
    S = 'Skenario-3 VALIDASI & KEAMANAN'
    print(f"\n== {S} ==")
    vid, vtok = setup_master(ctx, S, 'CMT Gamma Sentosa', 'CMT-GAM', 'gamma.cmt@dewi.test')
    po = make_po(ctx, S, 'PO-VP-S3', vid, [
        {'product_name': 'Kaos Gamma', 'sku': 'GAM-M', 'size': 'M', 'color': 'Putih',
         'serial_number': 'SN-VP-S3-A', 'qty': 50, 'cmt_price_snapshot': 9000}])
    it = po['items'][0]
    ship = dispatch(ctx, S, po, 'SJ-VP-S3', vid, [{'po_id': po['id'], 'po_item_id': it['id'], 'qty_sent': 50}])
    vsi = ship['items'][0]
    requests.post(f"{API}/api/vendor-material-inspections", headers=H(vtok), json={'shipment_id': ship['id'], 'items': [
        {'shipment_item_id': vsi['id'], 'sku': 'GAM-M', 'product_name': 'Kaos Gamma', 'size': 'M',
         'ordered_qty': 50, 'received_qty': 50, 'missing_qty': 0}]}, timeout=20)
    job = _body(requests.post(f"{API}/api/production-jobs", headers=H(vtok), json={'vendor_shipment_id': ship['id']}, timeout=20))
    ji = job['items'][0]

    # C1 progress over available
    r = requests.post(f"{API}/api/production-progress", headers=H(vtok),
                      json={'job_item_id': ji['id'], 'completed_quantity': 51}, timeout=15)
    rec(S, 'C1 Progress 51 > tersedia 50 → DITOLAK', 'POST', '/api/production-progress',
        {'job_item_id': ji['id'], 'completed_quantity': 51}, r.status_code, _body(r), '400 ditolak', r.status_code == 400)

    # C2 valid progress
    r = requests.post(f"{API}/api/production-progress", headers=H(vtok),
                      json={'job_item_id': ji['id'], 'completed_quantity': 50}, timeout=15)
    rec(S, 'C2 Progress 50 (pas) → OK', 'POST', '/api/production-progress',
        {'job_item_id': ji['id'], 'completed_quantity': 50}, r.status_code, _body(r), '201', r.status_code == 201)

    # C3 vendor create PO → 403
    r = requests.post(f"{API}/api/production-pos", headers=H(vtok), json={'po_number': 'X-HACK', 'business_type': 'maklon'}, timeout=15)
    rec(S, 'C3 Vendor buat PO → DITOLAK (RBAC)', 'POST', '/api/production-pos', {'po_number': 'X-HACK'},
        r.status_code, _body(r), '403', r.status_code == 403)

    # C4 vendor delete PO → 403
    r = requests.delete(f"{API}/api/production-pos/{po['id']}", headers=H(vtok), timeout=15)
    rec(S, 'C4 Vendor hapus PO → DITOLAK (RBAC)', 'DELETE', f"/api/production-pos/{po['id']}", {},
        r.status_code, _body(r), '403', r.status_code == 403)

    # C5 klien read production-pos → 403
    r = requests.get(f"{API}/api/production-pos", headers=H(ctx.klien), timeout=15)
    rec(S, 'C5 Klien akses /production-pos → DITOLAK', 'GET', '/api/production-pos', {},
        r.status_code, _body(r) if r.status_code != 200 else '[...]', '403', r.status_code == 403)

    # C6 DA buyer shipment tanpa source_receipt_ids → 400
    r = requests.post(f"{API}/api/buyer-shipments", headers=H(ctx.admin), json={
        'po_id': po['id'], 'vendor_id': vid, 'receiver_type': 'buyer',
        'items': [{'po_item_id': it['id'], 'ordered_qty': 50, 'qty_shipped': 10}]}, timeout=15)
    rec(S, 'C6 DA kirim buyer tanpa source_receipt_ids → DITOLAK', 'POST', '/api/buyer-shipments',
        {'receiver_type': 'buyer', 'source_receipt_ids': 'MISSING'}, r.status_code, _body(r),
        '400 wajib source_receipt_ids', r.status_code == 400)

    # C7 cross-vendor scope: gamma tidak melihat job vendor lain
    r = requests.get(f"{API}/api/production-jobs", headers=H(vtok), timeout=15)
    jobs_v = _body(r)
    only_own = isinstance(jobs_v, list) and all(j.get('vendor_id') == vid for j in jobs_v)
    rec(S, 'C7 Vendor Gamma hanya lihat job sendiri (scope)', 'GET', '/api/production-jobs', {},
        r.status_code, {'count': len(jobs_v) if isinstance(jobs_v, list) else '?', 'all_own': only_own},
        f'semua job vendor_id={vid}', r.status_code == 200 and only_own)

    # C8 cek-seri duplicate: buat PO ke-2 pakai serial sama
    po2 = make_po(ctx, S, 'PO-VP-S3B', vid, [
        {'product_name': 'Kaos Gamma Dobel', 'sku': 'GAM-L', 'size': 'L', 'color': 'Putih',
         'serial_number': 'SN-VP-S3-A', 'qty': 20, 'cmt_price_snapshot': 9000}])
    r = requests.get(f"{API}/api/dewi/cmt-intake/cek-seri?scope=maklon", headers=H(ctx.admin), timeout=15)
    ceks = _body(r)
    dup_found = any(d.get('serial') == 'SN-VP-S3-A' for d in ceks.get('duplicates', []))
    rec(S, 'C8 Cek-Seri deteksi SN-VP-S3-A dobel', 'GET', '/api/dewi/cmt-intake/cek-seri?scope=maklon', {},
        r.status_code, {'duplicate_count': ceks.get('duplicate_count'), 'found_SN-VP-S3-A': dup_found},
        'terdeteksi dobel', r.status_code == 200 and dup_found)

    # C9 serial-lookup live warning
    r = requests.get(f"{API}/api/dewi/cmt-intake/serial-lookup?serial=SN-VP-S3-A&scope=all", headers=H(ctx.admin), timeout=15)
    lk = _body(r)
    rec(S, 'C9 Serial-lookup SN-VP-S3-A exists=true', 'GET', '/api/dewi/cmt-intake/serial-lookup', {'serial': 'SN-VP-S3-A'},
        r.status_code, {'exists': lk.get('exists'), 'usages': len(lk.get('usages', []))},
        'exists=true (≥2 pakai)', r.status_code == 200 and lk.get('exists') and len(lk.get('usages', [])) >= 2)

    return [po['id'], po2['id']], vid, 'gamma.cmt@dewi.test', 'CMT-GAM'


def cleanup(ctx, po_ids, emails, codes):
    print("\n== Cleanup ==")
    for pid in po_ids:
        requests.delete(f"{API}/api/production-pos/{pid}", headers=H(ctx.admin), timeout=30)
    # delete accounts (hard) FIRST, then partners (hard) — urutan integritas referensial
    r = requests.get(f"{API}/api/vendor-portal/accounts", headers=H(ctx.admin), timeout=15)
    for a in (r.json() if r.status_code == 200 else []):
        if a.get('email') in emails:
            requests.delete(f"{API}/api/vendor-portal/accounts/{a['id']}?hard=true", headers=H(ctx.admin), timeout=15)
    r = requests.get(f"{API}/api/vendor-portal/partners", headers=H(ctx.admin), timeout=15)
    for p in (r.json() if r.status_code == 200 else []):
        if p.get('code') in codes:
            requests.delete(f"{API}/api/vendor-portal/partners/{p['id']}?hard=true", headers=H(ctx.admin), timeout=15)
    # residue
    try:
        from pymongo import MongoClient
        from dotenv import dotenv_values
        env = dotenv_values('/app/backend/.env')
        mdb = MongoClient(env['MONGO_URL'].strip('"'))[env['DB_NAME'].strip('"')]
        for pid in po_ids:
            mdb.production_variances.delete_many({'po_id': pid})
            mdb.dewi_maklon_pos.delete_many({'id': pid})
            mdb.rahaza_ar_invoices.delete_many({'linked_maklon_po_id': pid})
        print("  residu dibersihkan")
    except Exception as e:
        print(f"  WARN cleanup residu: {e}")


def main():
    admin = login('admin@garment.com', 'Admin@123')
    klien = login('klienmaklon@dewiaditya.id', 'Dewi@123')
    ctx = Ctx(admin, klien)

    po_ids, emails, codes = [], [], []
    p1, v1, e1, c1 = scenario1(ctx); po_ids.append(p1); emails.append(e1); codes.append(c1)
    p2, v2, e2, c2 = scenario2(ctx); po_ids.append(p2); emails.append(e2); codes.append(c2)
    p3s, v3, e3, c3 = scenario3(ctx, v1); po_ids += p3s; emails.append(e3); codes.append(c3)

    # write documentation JSON
    with open('/app/tests/vendor_portal_e2e_log.json', 'w') as f:
        json.dump({'generated_at': datetime.utcnow().isoformat(), 'result': RESULT, 'steps': LOG}, f, indent=2, default=str)

    cleanup(ctx, po_ids, emails, codes)

    print(f"\n===== HASIL: {RESULT['pass']} PASS / {RESULT['fail']} FAIL =====")
    for f_ in RESULT['failed']:
        print(f"  x {f_}")
    print("Log dokumentasi: /app/tests/vendor_portal_e2e_log.json")
    sys.exit(1 if RESULT['fail'] else 0)


if __name__ == '__main__':
    main()
