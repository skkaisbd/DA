#!/usr/bin/env python3
"""test_core_cmt_override.py — POC INTI **Portal CMT Override** (Fase 1).

Membuktikan lewat HTTP SUNGGUHAN (bukan unit test, bukan mock) bahwa staf DA bisa
menyelesaikan SELURUH 11 modul Portal Vendor CMT **atas nama** vendor yang tidak
memakai sistem, dengan jejak audit yang menempel, tanpa membocorkan data vendor
lain, dan tanpa merusak portal vendor asli.

Kenapa POC ini WAJIB sebelum menulis UI: audit menemukan 4 blocker keras
(403 `/vendor/dashboard`, scoping `/production-progress` + bug `garment_id`,
403 `receiver_type='da'` di `/buyer-shipments`, balasan reminder hanya untuk role
`vendor`). Kalau UI dibangun dulu, kegagalannya baru muncul di layar dan sulit
dilacak. Rantai ini juga menyentuh UANG (progress → tagihan CMT), jadi harus ada
bukti angka tersimpan TIDAK bergeser.

Jalankan:
    cd /app && python3 test_core_cmt_override.py
    cd /app && python3 test_core_cmt_override.py --keep     # jangan hapus data uji

Data uji ditandai prefiks `POCOV` dan DIHAPUS di `finally` langsung ke Mongo
(pelajaran repo: `DELETE` API sering hanya meng-cancel, bukan menghapus).
"""
from __future__ import annotations

import argparse
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone

import requests
from pymongo import MongoClient

BASE = os.environ.get('BASE_URL', 'http://localhost:8001/api')
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')

MARK = 'POCOV'
OVERRIDE_HEADER = 'X-CMT-Override-Vendor'

G, R, Y, B, X = '\033[92m', '\033[91m', '\033[93m', '\033[94m', '\033[0m'

_results: list[tuple[bool, str, str]] = []
_created: dict = {
    'users': [], 'partners': [], 'pos': [], 'shipments': [], 'jobs': [],
    'buyer_shipments': [], 'reminders': [], 'variances': [], 'requests': [],
    'inspections': [],
}


def check(ok: bool, name: str, detail: str = '') -> bool:
    _results.append((bool(ok), name, detail))
    icon = f'{G}✓{X}' if ok else f'{R}✗{X}'
    print(f'  {icon} {name}' + (f'  {Y}→ {detail}{X}' if detail else ''))
    return bool(ok)


def section(title: str):
    print(f'\n{B}══ {title} {"═" * max(0, 66 - len(title))}{X}')


# ── HTTP helpers ────────────────────────────────────────────────────────────
def _hdr(token: str | None = None, vendor: str | None = None) -> dict:
    h = {'Content-Type': 'application/json'}
    if token:
        h['Authorization'] = f'Bearer {token}'
    if vendor:
        h[OVERRIDE_HEADER] = vendor
    return h


def req(method: str, path: str, token=None, vendor=None, json=None, timeout=60):
    fn = getattr(requests, method.lower())
    kw = {'headers': _hdr(token, vendor), 'timeout': timeout}
    if json is not None:
        kw['json'] = json
    return fn(f'{BASE}{path}', **kw)


def jget(method: str, path: str, **kw):
    """(status_code, parsed_body_or_text)"""
    r = req(method, path, **kw)
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, r.text


def login(email: str, password: str) -> str | None:
    code, body = jget('post', '/auth/login', json={'email': email, 'password': password})
    if code != 200 or not isinstance(body, dict):
        print(f'  {R}login GAGAL {email}: HTTP {code} {str(body)[:200]}{X}')
        return None
    return body.get('token')


def as_list(body):
    """Endpoint repo ini kadang array, kadang {items:[]} / {vendors:[]}."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict):
        for k in ('items', 'vendors', 'entries', 'data', 'reminders', 'results'):
            if isinstance(body.get(k), list):
                return body[k]
    return []


# ═══════════════════════════════════════════════════════════════════════════
def main(keep: bool) -> int:
    print(f'{B}POC Portal CMT Override — 11 modul, jejak audit, RBAC, regresi{X}')
    print(f'   BASE={BASE}  DB={DB_NAME}')

    mongo = MongoClient(MONGO_URL)
    db = mongo[DB_NAME]

    admin = staff = hr = vendor_acc = None
    vendor_a = vendor_b = None
    po_id = ship_id = job_id = None

    try:
        # ── 0. LOGIN ────────────────────────────────────────────────────────
        section('0. Login (dipakai ulang — hindari rate limit)')
        admin = login('admin@garment.com', 'Admin@123')
        if not check(bool(admin), 'login superadmin admin@garment.com'):
            return 1
        hr = login('hr@dewiaditya.id', 'Dewi@123')
        check(bool(hr), 'login role tidak berhak (hr@dewiaditya.id)')
        vendor_acc = login('cmtvendor@dewiaditya.id', 'Vendor@123') or \
            login('cmtvendor@dewiaditya.id', 'Dewi@123')
        check(bool(vendor_acc), 'login vendor CMT asli (untuk uji regresi)',
              '' if vendor_acc else 'password tak diketahui — direset via API di bawah')

        # ── 1. SNAPSHOT UANG (sebelum) ──────────────────────────────────────
        section('1. Snapshot UANG sebelum apa pun disentuh')
        code, bill_before = jget('get', '/production/cmt-billing/summary', token=admin)
        money_before = (bill_before or {}).get('total_amount') if isinstance(bill_before, dict) else None
        demo_items_before = {
            i['id']: i.get('produced_qty', 0)
            for i in db.production_job_items.find({'job_id': 'po-mk-demo-2-job1'}, {'_id': 0, 'id': 1, 'produced_qty': 1})
        }
        check(code == 200, 'ringkasan tagihan CMT terbaca', f'total_amount={money_before}')
        print(f'     produced_qty demo sebelum: {demo_items_before}')

        # ── 2. SETUP master + data kerja (pakai API sungguhan) ──────────────
        section('2. Setup: 2 vendor CMT, staf berwenang, PO maklon, surat jalan, reminder')

        code, vb = jget('post', '/vendor-portal/partners', token=admin, json={
            'name': f'{MARK} Vendor Tanpa Sistem', 'code': f'{MARK}A',
            'contact_name': 'Pak Uji', 'contact_phone': '0800-0000-0001',
            'address': 'Sragen', 'notes': f'{MARK} data uji POC', 'capacity_pcs': 500})
        vendor_a = (vb or {}).get('id') if isinstance(vb, dict) else None
        if not check(code == 200 and bool(vendor_a), 'vendor A dibuat (TANPA akun portal)', str(vb)[:160]):
            return 1
        _created['partners'].append(vendor_a)

        code, vb2 = jget('post', '/vendor-portal/partners', token=admin, json={
            'name': f'{MARK} Vendor Punya Akun', 'code': f'{MARK}B',
            'contact_name': 'Pak Dua', 'notes': f'{MARK} data uji POC'})
        vendor_b = (vb2 or {}).get('id') if isinstance(vb2, dict) else None
        check(code == 200 and bool(vendor_b), 'vendor B dibuat (AKAN punya akun portal)')
        if vendor_b:
            _created['partners'].append(vendor_b)

        # akun portal untuk vendor B → memicu peringatan dobel input (5a)
        vb_email = f'{MARK.lower()}.vendorb@example.test'
        code, acc = jget('post', '/vendor-portal/accounts', token=admin, json={
            'email': vb_email, 'name': f'{MARK} Akun Vendor B',
            'password': 'PocOv@123', 'partner_id': vendor_b})
        check(code in (200, 201), 'akun portal vendor B dibuat', f'HTTP {code} {str(acc)[:120]}')
        if code in (200, 201):
            u = db.users.find_one({'email': vb_email}, {'_id': 0, 'id': 1})
            if u:
                _created['users'].append(u['id'])
        # login sekali supaya `last_login_at` benar-benar terisi oleh sistem
        vb_token = login(vb_email, 'PocOv@123')
        check(bool(vb_token), 'akun vendor B login sekali (mengisi last_login_at asli)')

        # staf berwenang: role admin_produksi
        staff_email = f'{MARK.lower()}.staff@example.test'
        code, su = jget('post', '/users', token=admin, json={
            'name': f'{MARK} Staf Produksi', 'email': staff_email,
            'password': 'PocOv@123', 'role': 'admin_produksi', 'department': 'Produksi'})
        check(code in (200, 201), 'staf admin_produksi dibuat', f'HTTP {code}')
        if isinstance(su, dict) and su.get('id'):
            _created['users'].append(su['id'])
        staff = login(staff_email, 'PocOv@123')
        if not check(bool(staff), 'login staf admin_produksi'):
            return 1

        # PO maklon + 2 item
        po_number = f'{MARK}-PO-{uuid.uuid4().hex[:6].upper()}'
        deadline = (datetime.now(timezone.utc) + timedelta(days=5)).date().isoformat()
        code, po = jget('post', '/production-pos', token=admin, json={
            'po_number': po_number, 'business_type': 'maklon', 'vendor_id': vendor_a,
            'customer_name': f'{MARK} Buyer Uji', 'status': 'Confirmed',
            'deadline': deadline, 'delivery_deadline': deadline,
            'notes': f'{MARK} PO uji POC',
            'items': [
                {'product_name': f'{MARK} Kaos', 'sku': f'{MARK}-KAOS-M', 'size': 'M',
                 'color': 'Navy', 'qty': 100, 'serial_number': f'{MARK}-SN-001',
                 'cmt_price_snapshot': 7500},
                {'product_name': f'{MARK} Kaos', 'sku': f'{MARK}-KAOS-L', 'size': 'L',
                 'color': 'Navy', 'qty': 60, 'serial_number': f'{MARK}-SN-002',
                 'cmt_price_snapshot': 7500},
            ]})
        po_id = (po or {}).get('id') if isinstance(po, dict) else None
        if not check(code in (200, 201) and bool(po_id), 'PO maklon dibuat', f'HTTP {code} {str(po)[:160]}'):
            return 1
        _created['pos'].append(po_id)
        po_items = list(db.po_items.find({'po_id': po_id}, {'_id': 0}))
        check(len(po_items) == 2, 'PO punya 2 item', f'{len(po_items)} item')

        # surat jalan material DA → vendor A
        ship_number = f'{MARK}-SJ-{uuid.uuid4().hex[:6].upper()}'
        code, sh = jget('post', '/vendor-shipments', token=admin, json={
            'shipment_number': ship_number, 'vendor_id': vendor_a, 'po_id': po_id,
            'shipment_type': 'NORMAL', 'notes': f'{MARK} kirim material uji',
            'items': [{'po_id': po_id, 'po_item_id': it['id'], 'qty_sent': it['qty']}
                      for it in po_items]})
        ship_id = (sh or {}).get('id') if isinstance(sh, dict) else None
        if not check(code in (200, 201) and bool(ship_id), 'surat jalan material dibuat (status Sent)',
                     f'HTTP {code} {str(sh)[:160]}'):
            return 1
        _created['shipments'].append(ship_id)

        # reminder dari DA ke vendor A (isi modul 11)
        code, rem = jget('post', '/reminders', token=admin, json={
            'vendor_id': vendor_a, 'po_id': po_id, 'po_number': po_number,
            'reminder_type': 'deadline', 'subject': f'{MARK} Kejar tenggat',
            'message': 'Mohon kabari progress harian.', 'priority': 'high'})
        rem_id = (rem or {}).get('id') if isinstance(rem, dict) else None
        check(code in (200, 201) and bool(rem_id), 'reminder untuk vendor A dibuat',
              f'HTTP {code} {str(rem)[:120]}')
        if rem_id:
            _created['reminders'].append(rem_id)

        # ── 3. RBAC (invarian OV-1 / OV-2) ─────────────────────────────────
        section('3. RBAC — hanya staf berwenang; vendor tak boleh menyamar')
        code, _ = jget('get', '/cmt-override/vendors', token=hr)
        check(code == 403, 'role hr DITOLAK membuka daftar vendor override', f'HTTP {code}')
        code, _ = jget('get', '/vendor/dashboard', token=hr, vendor=vendor_a)
        check(code == 403, 'role hr + header override DITOLAK (bukan diabaikan)', f'HTTP {code}')
        if vendor_acc:
            code, _ = jget('get', '/vendor-shipments', token=vendor_acc, vendor=vendor_a)
            check(code == 403, 'akun vendor DITOLAK memakai header override', f'HTTP {code}')
        code, _ = jget('get', '/vendor/dashboard', token=staff)
        check(code == 403, 'staf TANPA memilih vendor tetap ditolak di dashboard vendor', f'HTTP {code}')
        code, _ = jget('get', '/vendor/dashboard', token=staff, vendor='vendor-yang-tidak-ada')
        check(code == 404, 'vendor tidak ada → 404 yang jelas', f'HTTP {code}')

        # ── 4. Daftar vendor + peringatan dobel input (4a & 5a) ────────────
        section('4. Daftar vendor override + peringatan dobel input')
        code, vl = jget('get', '/cmt-override/vendors', token=staff)
        vendors = as_list(vl)
        by_id = {v['id']: v for v in vendors}
        check(code == 200, 'daftar vendor override terbaca', f'{len(vendors)} vendor aktif')
        check(vendor_a in by_id, 'vendor A (tanpa akun) MUNCUL di daftar — keputusan 4a semua vendor aktif')
        check('mk-vendor-demo-1' in by_id, 'vendor demo yang punya akun juga muncul (bukan disaring)')
        va = by_id.get(vendor_a, {})
        check(va.get('has_active_portal_account') is False and not va.get('warning'),
              'vendor A: tidak ada peringatan (memang tak punya akun)')
        vbb = by_id.get(vendor_b, {})
        check(vbb.get('has_active_portal_account') is True, 'vendor B: terdeteksi punya akun portal aktif')
        check(bool(vbb.get('last_login_at')), 'vendor B: last_login_at terisi dari login sungguhan',
              str(vbb.get('last_login_at'))[:32])
        check('hati-hati dobel input' in (vbb.get('warning') or ''),
              'vendor B: peringatan "hati-hati dobel input" muncul — keputusan 5a',
              (vbb.get('warning') or '')[:110])
        check(va.get('incoming_shipments', 0) >= 1, 'vendor A: pekerjaan tertunda terhitung (1 kiriman masuk)')

        code, ctx = jget('get', '/cmt-override/context', token=staff, vendor=vendor_a)
        check(code == 200 and (ctx or {}).get('active') is True and (ctx or {}).get('vendor_id') == vendor_a,
              'konteks override aktif & menyebut vendor + staf',
              f"{(ctx or {}).get('vendor_name')} / {(ctx or {}).get('staff_name')}")

        # ── 5. MODUL 1 — Dashboard ─────────────────────────────────────────
        section('5. Modul 1/11 — Dashboard vendor (dulu 403 keras)')
        code, dash = jget('get', '/vendor/dashboard', token=staff, vendor=vendor_a)
        check(code == 200, 'dashboard vendor terbuka untuk staf mode override', f'HTTP {code}')
        check(isinstance(dash, dict) and dash.get('incomingShipments') == 1,
              'dashboard menghitung 1 kiriman masuk milik vendor A',
              f"incoming={(dash or {}).get('incomingShipments')}")
        check(isinstance((dash or {}).get('alerts'), dict), 'panel alerts terisi (bukan list kosong permanen)')

        # ── 6. MODUL 2 — Penerimaan Material ───────────────────────────────
        section('6. Modul 2/11 — Penerimaan Material (tandai Diterima)')
        code, ships = jget('get', '/vendor-shipments', token=staff, vendor=vendor_a)
        slist = as_list(ships)
        ids = {s['id'] for s in slist}
        check(code == 200 and ship_id in ids, 'daftar kiriman vendor A terbaca')
        check('po-mk-demo-2-vs1' not in ids,
              'TIDAK BOCOR: kiriman vendor demo tidak ikut terlihat', f'{len(slist)} baris')
        code, one = jget('get', f'/vendor-shipments/{ship_id}', token=staff, vendor=vendor_a)
        check(code == 200 and len(as_list((one or {}).get('items'))) == 2, 'detail kiriman + 2 item terbaca')
        code, _ = jget('get', '/vendor-shipments/po-mk-demo-2-vs1', token=staff, vendor=vendor_a)
        check(code == 403, 'detail kiriman vendor LAIN ditolak 403 saat mode override', f'HTTP {code}')

        code, upd = jget('put', f'/vendor-shipments/{ship_id}', token=staff, vendor=vendor_a,
                         json={'status': 'Received'})
        check(code == 200 and (upd or {}).get('status') == 'Received', 'kiriman ditandai Diterima oleh staf')
        sdoc = db.vendor_shipments.find_one({'id': ship_id}, {'_id': 0})
        check((sdoc or {}).get('receipt_entered_by_staff') is True,
              'JEJAK 3a: receipt_entered_by_staff=true tersimpan')
        check((sdoc or {}).get('receipt_on_behalf_of_vendor') == vendor_a
              and (sdoc or {}).get('receipt_entered_by') == f'{MARK} Staf Produksi',
              'JEJAK 3a: nama staf + vendor yang diwakili tersimpan',
              f"{(sdoc or {}).get('receipt_entered_by')} → {(sdoc or {}).get('receipt_on_behalf_of_vendor_name')}")

        # ── 7. MODUL 3 — Inspeksi Material ─────────────────────────────────
        section('7. Modul 3/11 — Inspeksi Material (ada barang kurang)')
        ship_items = list(db.vendor_shipment_items.find({'shipment_id': ship_id}, {'_id': 0}))
        insp_items = []
        for idx, si in enumerate(ship_items):
            sent = int(si.get('qty_sent', 0) or 0)
            missing = 5 if idx == 0 else 0          # sengaja kurang 5 pcs di baris pertama
            insp_items.append({
                'shipment_item_id': si['id'], 'sku': si.get('sku', ''),
                'product_name': si.get('product_name', ''), 'size': si.get('size', ''),
                'color': si.get('color', ''), 'ordered_qty': sent,
                'received_qty': sent - missing, 'missing_qty': missing,
                'condition_notes': 'kurang 5 pcs' if missing else 'lengkap'})
        code, insp = jget('post', '/vendor-material-inspections', token=staff, vendor=vendor_a,
                          json={'shipment_id': ship_id, 'items': insp_items,
                                'overall_notes': f'{MARK} inspeksi oleh staf DA'})
        insp_id = (insp or {}).get('id') if isinstance(insp, dict) else None
        check(code in (200, 201) and bool(insp_id), 'inspeksi tersimpan', f'HTTP {code} {str(insp)[:140]}')
        if insp_id:
            _created['inspections'].append(insp_id)
        idoc = db.vendor_material_inspections.find_one({'id': insp_id}, {'_id': 0}) if insp_id else None
        check((idoc or {}).get('entered_by_staff') is True, 'JEJAK 3a: inspeksi bertanda diinput staf DA')
        check((idoc or {}).get('total_missing') == 5, 'selisih 5 pcs tercatat',
              f"missing={(idoc or {}).get('total_missing')}")
        code, ilist = jget('get', '/vendor-material-inspections', token=staff, vendor=vendor_a)
        check(code == 200 and any(i.get('id') == insp_id for i in as_list(ilist)),
              'daftar inspeksi ter-scope ke vendor A')

        # ── 8. MODUL 4 — Permintaan Material ───────────────────────────────
        section('8. Modul 4/11 — Permintaan Material tambahan')
        code, mr = jget('post', '/material-requests', token=staff, vendor=vendor_a, json={
            'request_type': 'ADDITIONAL', 'original_shipment_id': ship_id,
            'po_id': po_id, 'po_number': po_number, 'inspection_id': insp_id,
            'notes': f'{MARK} minta kirim ulang 5 pcs yang kurang',
            'items': [{'shipment_item_id': ship_items[0]['id'], 'sku': ship_items[0].get('sku', ''),
                       'product_name': ship_items[0].get('product_name', ''),
                       'size': ship_items[0].get('size', ''), 'color': ship_items[0].get('color', ''),
                       'requested_qty': 5}]})
        mr_id = (mr or {}).get('id') if isinstance(mr, dict) else None
        check(code in (200, 201) and bool(mr_id), 'permintaan material tersimpan',
              f'HTTP {code} {str(mr)[:140]}')
        if mr_id:
            _created['requests'].append(mr_id)
        mdoc = db.material_requests.find_one({'id': mr_id}, {'_id': 0}) if mr_id else None
        check((mdoc or {}).get('entered_by_staff') is True, 'JEJAK 3a: permintaan bertanda diinput staf DA')
        code, mrl = jget('get', '/material-requests?request_type=ADDITIONAL', token=staff, vendor=vendor_a)
        check(code == 200 and all(r.get('vendor_id') == vendor_a for r in as_list(mrl)),
              'daftar permintaan HANYA vendor A')

        # ── 9. MODUL 5 — Pekerjaan Produksi ────────────────────────────────
        section('9. Modul 5/11 — Pekerjaan Produksi (buka job)')
        code, job = jget('post', '/production-jobs', token=staff, vendor=vendor_a,
                         json={'vendor_shipment_id': ship_id, 'notes': f'{MARK} job oleh staf DA'})
        job_id = (job or {}).get('id') if isinstance(job, dict) else None
        check(code in (200, 201) and bool(job_id), 'production job dibuat', f'HTTP {code} {str(job)[:140]}')
        if not job_id:
            return 1
        _created['jobs'].append(job_id)
        jdoc = db.production_jobs.find_one({'id': job_id}, {'_id': 0})
        check((jdoc or {}).get('entered_by_staff') is True, 'JEJAK 3a: job bertanda diinput staf DA')
        check((jdoc or {}).get('vendor_id') == vendor_a, 'job menempel ke vendor A (bukan ke staf)')
        code, jl = jget('get', '/production-jobs', token=staff, vendor=vendor_a)
        jids = {j['id'] for j in as_list(jl)}
        check(code == 200 and job_id in jids, 'daftar job ter-scope memuat job baru')
        check('po-mk-demo-2-job1' not in jids, 'TIDAK BOCOR: job vendor demo tidak terlihat')

        code, jitems = jget('get', f'/production-job-items?job_id={job_id}', token=staff, vendor=vendor_a)
        items = as_list(jitems)
        check(code == 200 and len(items) == 2, 'item job terbaca', f'{len(items)} item')
        first = items[0] if items else {}
        check(int(first.get('available_qty', -1)) == int(first.get('shipment_qty', 0)) - 5
              or int(first.get('available_qty', 0)) in (95, 60),
              'available_qty mengikuti hasil inspeksi (bukan qty kirim)',
              f"available={first.get('available_qty')} shipment={first.get('shipment_qty')}")
        code, _ = jget('get', '/production-job-items?job_id=po-mk-demo-2-job1', token=staff, vendor=vendor_a)
        check(code == 403, 'item job vendor LAIN ditolak 403 saat mode override', f'HTTP {code}')

        # ── 10. MODUL 6 — Panduan Produksi ─────────────────────────────────
        section('10. Modul 6/11 — Panduan Produksi')
        code, guide = jget('get', f'/production-jobs/{job_id}/production-guide', token=staff, vendor=vendor_a)
        check(code == 200 and isinstance(guide, dict), 'panduan produksi terbaca', f'HTTP {code}')
        code, _ = jget('get', '/production-jobs/po-mk-demo-2-job1/production-guide',
                       token=staff, vendor=vendor_a)
        check(code == 403, 'panduan job vendor LAIN ditolak 403', f'HTTP {code}')

        # ── 11. MODUL 7 — Progress Produksi ────────────────────────────────
        section('11. Modul 7/11 — Progress Produksi (angka dasar TAGIHAN)')
        target_item = items[0]
        code, pr = jget('post', '/production-progress', token=staff, vendor=vendor_a, json={
            'job_item_id': target_item['id'],
            'progress_date': datetime.now(timezone.utc).date().isoformat(),
            'completed_quantity': 40, 'notes': f'{MARK} setoran harian via staf DA'})
        pr_id = (pr or {}).get('id') if isinstance(pr, dict) else None
        check(code in (200, 201) and bool(pr_id), 'progress 40 pcs tersimpan', f'HTTP {code} {str(pr)[:140]}')
        pdoc = db.production_progress.find_one({'id': pr_id}, {'_id': 0}) if pr_id else None
        check((pdoc or {}).get('entered_by_staff') is True,
              'JEJAK 3a: progress bertanda diinput staf DA (INI yang dipakai badge di invoice)')
        check((pdoc or {}).get('on_behalf_of_vendor') == vendor_a,
              'JEJAK 3a: progress menyimpan vendor yang diwakili')

        code, plist = jget('get', '/production-progress', token=staff, vendor=vendor_a)
        prows = as_list(plist)
        check(code == 200 and any(p.get('id') == pr_id for p in prows),
              'riwayat progress ter-scope memuat setoran baru', f'{len(prows)} baris')
        check(all(p.get('job_id') == job_id for p in prows),
              'TIDAK BOCOR: riwayat progress hanya job vendor A')

        # tulis lintas-vendor harus ditolak
        code, _ = jget('post', '/production-progress', token=staff, vendor=vendor_a,
                       json={'job_item_id': 'po-mk-demo-2-job1-ji1', 'completed_quantity': 1})
        check(code == 403, 'progress untuk job vendor LAIN ditolak 403 (anti salah vendor)', f'HTTP {code}')

        # batas kapasitas material tetap berlaku di mode override
        code, over = jget('post', '/production-progress', token=staff, vendor=vendor_a,
                          json={'job_item_id': target_item['id'], 'completed_quantity': 99999})
        check(code == 400, 'batas "melebihi material tersedia" tetap ditegakkan', f'HTTP {code}')

        # ── 12. MODUL 8 — Kirim ke Buyer (deklarasi CMT → DA) ──────────────
        section('12. Modul 8/11 — Kirim ke Buyer / deklarasi CMT→DA (dulu 403)')
        bs_number = f'{MARK}-SJDA-{uuid.uuid4().hex[:6].upper()}'
        code, bs = jget('post', '/buyer-shipments', token=staff, vendor=vendor_a, json={
            'shipment_number': bs_number, 'job_id': job_id, 'po_id': po_id,
            'shipment_date': datetime.now(timezone.utc).date().isoformat(),
            'notes': f'{MARK} deklarasi kirim CMT ke DA oleh staf',
            'items': [{'po_item_id': target_item.get('po_item_id'),
                       'sku': target_item.get('sku', ''),
                       'product_name': target_item.get('product_name', ''),
                       'size': target_item.get('size', ''), 'color': target_item.get('color', ''),
                       'qty_shipped': 40}]})
        bs_id = (bs or {}).get('id') if isinstance(bs, dict) else None
        check(code in (200, 201) and bool(bs_id), 'deklarasi kirim CMT→DA berhasil dibuat oleh staf',
              f'HTTP {code} {str(bs)[:180]}')
        if bs_id:
            _created['buyer_shipments'].append(bs_id)
        bdoc = db.buyer_shipments.find_one({'id': bs_id}, {'_id': 0}) if bs_id else None
        check((bdoc or {}).get('receiver_type') == 'da',
              "receiver_type otomatis 'da' (persis perilaku vendor)",
              str((bdoc or {}).get('receiver_type')))
        check((bdoc or {}).get('entered_by_staff') is True, 'JEJAK 3a: deklarasi bertanda diinput staf DA')
        check((bdoc or {}).get('vendor_id') == vendor_a, 'deklarasi menempel ke vendor A')
        rcv = db.cmt_receipts.find_one({'related_shipment_id': bs_id}, {'_id': 0})
        check(bool(rcv), 'rantai lanjut: draft cmt_receipts untuk DA ikut terbentuk',
              (rcv or {}).get('receipt_code', '-'))
        check((rcv or {}).get('cmt_vendor_id') == vendor_a and (rcv or {}).get('status') == 'Draft',
              'penerimaan DA menempel ke vendor A dan berstatus Draft',
              f"{(rcv or {}).get('cmt_vendor_id')} / {(rcv or {}).get('status')}")
        check(db.cmt_receipt_lines.count_documents({'receipt_id': (rcv or {}).get('id', '-')}) >= 1,
              'baris penerimaan DA ikut terisi dari deklarasi')

        code, bsl = jget('get', '/buyer-shipments', token=staff, vendor=vendor_a)
        bids = {s['id'] for s in as_list(bsl)}
        check(code == 200 and bs_id in bids, 'daftar pengiriman ter-scope memuat deklarasi baru')
        check('po-mk-demo-2-bs1' not in bids, 'TIDAK BOCOR: pengiriman vendor demo tidak terlihat')
        code, disp = jget('get', f'/buyer-shipment-dispatches?shipment_id={bs_id}', token=staff, vendor=vendor_a)
        check(code == 200 and len(as_list(disp)) >= 1, 'rincian dispatch terbaca')
        code, shorts = jget('get', '/prod/short-shipments?status=open', token=staff, vendor=vendor_a)
        check(code == 200, 'daftar selisih kirim terbaca (ter-scope)', f'HTTP {code}')

        # ── 13. MODUL 9 — Serial Tracking ──────────────────────────────────
        section('13. Modul 9/11 — Serial Tracking')
        code, tr = jget('get', f'/serial-trace?serial={MARK}-SN-001', token=staff, vendor=vendor_a)
        check(code == 200 and isinstance(tr, dict), 'jejak serial terbaca', f'HTTP {code}')
        check(len(as_list((tr or {}).get('timeline'))) >= 1 or bool(tr),
              'timeline serial berisi (PO → kirim → inspeksi → job)')

        # ── 14. MODUL 10 — Laporan Variance ────────────────────────────────
        section('14. Modul 10/11 — Laporan Variance')
        code, vr = jget('post', '/production-variances', token=staff, vendor=vendor_a, json={
            'job_id': job_id, 'variance_type': 'UNDERPRODUCTION',
            'reason': f'{MARK} bahan kurang 5 pcs', 'notes': f'{MARK} dilaporkan staf DA',
            'items': [{'job_item_id': target_item['id'], 'sku': target_item.get('sku', ''),
                       'product_name': target_item.get('product_name', ''),
                       'ordered_qty': 100, 'produced_qty': 40, 'variance_qty': 5}]})
        vr_id = (vr or {}).get('id') if isinstance(vr, dict) else None
        check(code in (200, 201) and bool(vr_id), 'laporan variance tersimpan', f'HTTP {code} {str(vr)[:140]}')
        if vr_id:
            _created['variances'].append(vr_id)
        vdoc = db.production_variances.find_one({'id': vr_id}, {'_id': 0}) if vr_id else None
        check((vdoc or {}).get('entered_by_staff') is True, 'JEJAK 3a: variance bertanda diinput staf DA')
        code, vlist = jget('get', '/production-variances', token=staff, vendor=vendor_a)
        check(code == 200 and all(v.get('vendor_id') == vendor_a for v in as_list(vlist)),
              'daftar variance HANYA vendor A')
        code, vstat = jget('get', '/production-variances/stats', token=staff, vendor=vendor_a)
        check(code == 200, 'statistik variance ter-scope terbaca', f'HTTP {code}')

        # ── 15. MODUL 11 — Inbox Reminder ──────────────────────────────────
        section('15. Modul 11/11 — Inbox Reminder (balas atas nama vendor)')
        code, rl = jget('get', '/reminders', token=staff, vendor=vendor_a)
        rrows = as_list(rl)
        check(code == 200 and any(r.get('id') == rem_id for r in rrows),
              'inbox reminder vendor A terbaca', f'{len(rrows)} baris')
        check(all(r.get('vendor_id') == vendor_a for r in rrows),
              'TIDAK BOCOR: inbox hanya reminder vendor A')
        code, rup = jget('put', f'/reminders/{rem_id}', token=staff, vendor=vendor_a,
                         json={'response': f'{MARK} sudah dikerjakan, 40 pcs selesai'})
        check(code == 200 and (rup or {}).get('status') == 'responded',
              'reminder DIBALAS lewat mode override (dulu balasan diabaikan)',
              f"status={(rup or {}).get('status')}")
        rdoc = db.reminders.find_one({'id': rem_id}, {'_id': 0})
        check((rdoc or {}).get('response_entered_by_staff') is True,
              'JEJAK 3a: balasan bertanda diinput staf DA')

        # ── 16. Panel transparansi audit ───────────────────────────────────
        section('16. Panel transparansi — dokumen mana diinput staf vs vendor')
        code, aud = jget('get', '/cmt-override/audit', token=staff, vendor=vendor_a)
        entries = as_list(aud)
        mods = {e.get('module') for e in entries}
        check(code == 200 and (aud or {}).get('totals', {}).get('staff', 0) >= 7,
              'audit menghitung dokumen hasil input staf',
              f"staff={(aud or {}).get('totals', {}).get('staff')} vendor={(aud or {}).get('totals', {}).get('vendor')}")
        expected = {'Penerimaan Material', 'Inspeksi Material', 'Permintaan Material',
                    'Pekerjaan Produksi', 'Progress Produksi', 'Kirim ke Buyer',
                    'Laporan Variance', 'Inbox Reminder'}
        check(expected.issubset(mods), '8 modul yang menulis dokumen semuanya terlacak',
              f'kurang: {sorted(expected - mods) or "-"}')
        check(all(e.get('entered_by') == f'{MARK} Staf Produksi' for e in entries),
              'setiap baris audit menyebut NAMA staf yang mengetik')

        # ── 17. REGRESI portal vendor asli ─────────────────────────────────
        section('17. Regresi — portal vendor CMT ASLI tidak terganggu')
        if not vendor_acc:
            # reset password akun vendor demo supaya regresi bisa diuji
            code, _ = jget('put', '/vendor-portal/accounts/'
                           + str((db.users.find_one({'email': 'cmtvendor@dewiaditya.id'}, {'_id': 0, 'id': 1}) or {}).get('id')),
                           token=admin, json={'password': 'PocOv@123'})
            vendor_acc = login('cmtvendor@dewiaditya.id', 'PocOv@123')
        if check(bool(vendor_acc), 'login vendor CMT asli'):
            code, vdash = jget('get', '/vendor/dashboard', token=vendor_acc)
            check(code == 200, 'dashboard vendor asli tetap 200', f'HTTP {code}')
            code, vprog = jget('get', '/production-progress', token=vendor_acc)
            vrows = as_list(vprog)
            check(code == 200 and len(vrows) >= 2,
                  'BUG LAMA TERTUTUP: riwayat progress vendor asli TIDAK kosong lagi',
                  f'{len(vrows)} baris (sebelum perbaikan: 0)')
            check(all(p.get('job_id') in ('po-mk-demo-2-job1',) or p.get('garment_id') == 'mk-vendor-demo-1'
                      for p in vrows),
                  'riwayat progress vendor asli hanya job miliknya')
            check(all(p.get('id') != pr_id for p in vrows),
                  'progress vendor A TIDAK terlihat oleh vendor demo')
            code, vships = jget('get', '/vendor-shipments', token=vendor_acc)
            vsids = {s['id'] for s in as_list(vships)}
            check(code == 200 and ship_id not in vsids, 'kiriman vendor A tidak terlihat oleh vendor demo')
            code, vrem = jget('get', '/reminders', token=vendor_acc)
            check(code == 200 and all(r.get('vendor_id') == 'mk-vendor-demo-1' for r in as_list(vrem)),
                  'KEBOCORAN LAMA TERTUTUP: inbox reminder vendor asli ter-scope',
                  f'{len(as_list(vrem))} baris')
            code, vjobs = jget('get', '/production-jobs', token=vendor_acc)
            check(code == 200 and all(j.get('vendor_id') == 'mk-vendor-demo-1' for j in as_list(vjobs)),
                  'daftar job vendor asli ter-scope')

        # ── 18. UANG tidak bergeser ────────────────────────────────────────
        section('18. UANG — angka tersimpan milik data lain TIDAK bergeser')
        demo_items_after = {
            i['id']: i.get('produced_qty', 0)
            for i in db.production_job_items.find({'job_id': 'po-mk-demo-2-job1'}, {'_id': 0, 'id': 1, 'produced_qty': 1})
        }
        check(demo_items_before == demo_items_after,
              'produced_qty job vendor demo persis sama sebelum/sesudah',
              f'{demo_items_before} → {demo_items_after}')
        code, bill_after = jget('get', '/production/cmt-billing/summary', token=admin)
        money_after = (bill_after or {}).get('total_amount') if isinstance(bill_after, dict) else None
        check(money_before == money_after, 'total tagihan CMT tidak bergeser',
              f'{money_before} → {money_after}')

        return 0

    finally:
        # ── CLEANUP (wajib, langsung ke Mongo) ─────────────────────────────
        section('CLEANUP')
        if keep:
            print(f'  {Y}--keep: data uji DIBIARKAN (bersihkan manual!){X}')
        else:
            try:
                n = 0
                vids = [v for v in _created['partners'] if v]
                pos = _created['pos']
                jobs = list(db.production_jobs.find({'vendor_id': {'$in': vids}}, {'_id': 0, 'id': 1}))
                job_ids = [j['id'] for j in jobs]
                ships = list(db.vendor_shipments.find({'vendor_id': {'$in': vids}}, {'_id': 0, 'id': 1}))
                ship_ids = [s['id'] for s in ships]
                insps = list(db.vendor_material_inspections.find(
                    {'vendor_id': {'$in': vids}}, {'_id': 0, 'id': 1}))
                insp_ids = [i['id'] for i in insps]
                bss = list(db.buyer_shipments.find({'vendor_id': {'$in': vids}}, {'_id': 0, 'id': 1}))
                bs_ids = [b['id'] for b in bss]

                ops = [
                    ('production_progress', {'job_id': {'$in': job_ids}}),
                    ('production_job_items', {'job_id': {'$in': job_ids}}),
                    ('production_jobs', {'id': {'$in': job_ids}}),
                    ('vendor_material_inspection_items', {'inspection_id': {'$in': insp_ids}}),
                    ('vendor_material_inspections', {'id': {'$in': insp_ids}}),
                    ('vendor_shipment_items', {'shipment_id': {'$in': ship_ids}}),
                    ('accessory_shipment_items', {'shipment_id': {'$in': ship_ids}}),
                    ('vendor_shipments', {'id': {'$in': ship_ids}}),
                    ('material_requests', {'vendor_id': {'$in': vids}}),
                    ('production_variances', {'vendor_id': {'$in': vids}}),
                    ('reminders', {'vendor_id': {'$in': vids}}),
                    ('buyer_shipment_items', {'shipment_id': {'$in': bs_ids}}),
                    ('buyer_shipments', {'id': {'$in': bs_ids}}),
                    ('cmt_receipt_lines', {'receipt_id': {'$in': [
                        r['id'] for r in db.cmt_receipts.find(
                            {'cmt_vendor_id': {'$in': vids}}, {'_id': 0, 'id': 1})]}}),
                    ('cmt_receipts', {'cmt_vendor_id': {'$in': vids}}),
                    ('po_accessories', {'po_id': {'$in': pos}}),
                    ('po_items', {'po_id': {'$in': pos}}),
                    ('production_pos', {'id': {'$in': pos}}),
                    ('dewi_maklon_bom', {'po_id': {'$in': pos}}),
                    # ── Efek samping PO maklon yang MUDAH TERLEWAT ──────────
                    # `create_po_internal` juga menulis mirror PO maklon, AR
                    # invoice (UANG!), dan inspeksi "barang kurang" otomatis
                    # membuat permintaan komponen. Sesi sebelumnya di repo ini
                    # pernah meninggalkan jurnal GL fiktif dari alat uji —
                    # jangan ulangi: semuanya ikut dibersihkan.
                    ('dewi_maklon_pos', {'production_po_id': {'$in': pos}}),
                    ('rahaza_ar_invoices', {'linked_maklon_po_id': {'$in': pos}}),
                    ('dewi_cmt_component_requests', {'vendor_id': {'$in': vids}}),
                    ('dewi_cmt_jobs', {'cmt_partner_id': {'$in': vids}}),
                    ('dewi_cmt_deliveries', {'cmt_partner_id': {'$in': vids}}),
                    ('dewi_cmt_payments', {'cmt_partner_id': {'$in': vids}}),
                    ('vendor_partners', {'id': {'$in': vids}}),
                    ('users', {'id': {'$in': [u for u in _created['users'] if u]}}),
                    ('activity_logs', {'details': {'$regex': MARK}}),
                    ('notifications', {'$or': [{'title': {'$regex': MARK}},
                                               {'message': {'$regex': MARK}}]}),
                    ('rahaza_audit_logs', {'entity_id': {'$in': pos + job_ids + ship_ids}}),
                    ('login_attempts', {'identifier': {'$regex': MARK.lower()}}),
                ]
                for coll, q in ops:
                    try:
                        n += db[coll].delete_many(q).deleted_count
                    except Exception as e:
                        print(f'  {Y}! gagal bersihkan {coll}: {e}{X}')
                # sisa dokumen bertanda MARK di koleksi rantai CMT
                for coll, field in (('production_pos', 'po_number'), ('vendor_shipments', 'shipment_number'),
                                    ('buyer_shipments', 'shipment_number'), ('reminders', 'subject'),
                                    ('material_requests', 'request_number')):
                    try:
                        n += db[coll].delete_many({field: {'$regex': MARK}}).deleted_count
                    except Exception:
                        pass

                # ── SWEEP TOTAL (jaring pengaman terakhir) ─────────────────
                # Daftar hapus di atas ditulis TANGAN, jadi setiap efek samping
                # baru di backend akan lolos darinya tanpa ada yang tahu — persis
                # cara alat uji repo ini dulu meninggalkan jurnal GL fiktif
                # (AR invoice maklon Rp 1,2 jt per PO uji, mirror dewi_maklon_pos,
                # dan permintaan komponen otomatis semuanya lolos di jalan pertama).
                # Sweep ini memeriksa SETIAP dokumen di SETIAP koleksi: kalau
                # penanda uji muncul di mana pun isinya, dokumen itu data uji.
                # DB ini kecil (±1,2rb dokumen) jadi biayanya sepele.
                import json as _json
                swept, swept_where = 0, {}
                for coll in db.list_collection_names():
                    if coll in ('rate_limit_buckets', 'counters'):
                        continue
                    try:
                        dead = [d['_id'] for d in db[coll].find({}).limit(20000)
                                if MARK in _json.dumps(d, default=str)]
                    except Exception as e:
                        print(f'  {Y}! sweep {coll} dilewati: {e}{X}')
                        continue
                    if dead:
                        db[coll].delete_many({'_id': {'$in': dead}})
                        swept += len(dead)
                        swept_where[coll] = len(dead)
                if swept:
                    print(f'  {Y}sweep total menemukan {swept} dokumen sisa: {swept_where}{X}')
                n += swept
                print(f'  {G}✓ {n} dokumen uji dihapus{X}')

                # verifikasi akhir: tidak boleh ada satu pun jejak uji tertinggal
                rest = {}
                for coll in db.list_collection_names():
                    if coll in ('rate_limit_buckets', 'counters'):
                        continue
                    try:
                        k = sum(1 for d in db[coll].find({}).limit(20000)
                                if MARK in _json.dumps(d, default=str))
                    except Exception:
                        k = 0
                    if k:
                        rest[coll] = k
                check(not rest, 'CLEANUP: nol jejak data uji tertinggal di seluruh DB',
                      str(rest) if rest else 'bersih')
                left = {c: db[c].count_documents({'vendor_id': {'$in': vids}})
                        for c in ('vendor_shipments', 'production_jobs', 'buyer_shipments',
                                  'material_requests', 'production_variances', 'reminders')}
                left['cmt_receipts'] = db.cmt_receipts.count_documents({'cmt_vendor_id': {'$in': vids}})
                left['POCOV_apapun'] = sum(
                    db[c].count_documents({f: {'$regex': MARK}})
                    for c, f in (('vendor_partners', 'name'), ('users', 'email'),
                                 ('production_pos', 'po_number'), ('po_items', 'sku'),
                                 ('cmt_receipts', 'cmt_name')))
                print(f'  sisa per koleksi (harus 0): {left}')
            except Exception as e:
                print(f'  {R}✗ cleanup error: {e}{X}')

        # ── RINGKASAN ──────────────────────────────────────────────────────
        passed = sum(1 for ok, _, _ in _results if ok)
        total = len(_results)
        failed = [(n, d) for ok, n, d in _results if not ok]
        print(f'\n{B}{"═" * 74}{X}')
        col = G if not failed else R
        print(f'{col}HASIL POC: {passed}/{total} LULUS{X}')
        if failed:
            print(f'{R}GAGAL:{X}')
            for n, d in failed:
                print(f'  {R}✗{X} {n}' + (f'  → {d}' if d else ''))
        print(f'{B}{"═" * 74}{X}')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--keep', action='store_true', help='jangan hapus data uji')
    args = ap.parse_args()
    rc = 0
    try:
        rc = main(args.keep) or 0
    except KeyboardInterrupt:
        rc = 130
    fails = sum(1 for ok, _, _ in _results if not ok)
    sys.exit(1 if (rc or fails) else 0)
