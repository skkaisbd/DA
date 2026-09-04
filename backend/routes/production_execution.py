"""Production Execution domain: Production Jobs (+ items), Production Progress,
Distribusi Kerja, Work Orders, Recalculate Jobs.

Moved out of server.py during Backend Refactor Phase 6
(see /app/BACKEND_REFACTOR_PLAN.md). Pure move — behavior is byte-for-byte
identical to the original definitions in server.py. HIGH risk phase per the
plan (progress recompute logic is the most complex in the system) — every
line below is an exact cut-paste from server.py, no logic was altered.
"""
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
import logging
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from routes.production_rbac import (PROD_ADMIN_ROLES, PROD_VENDOR_ROLES,
    is_vendor, vendor_identity, deny_klien, require_write_actor,
    resolve_vendor_doc, resolve_buyer_name)
from core.helpers import new_id, now, parse_date
from core.pagination import LEGACY_DEFAULT_CAP, _paginate_params, _paginated_envelope, _sort_params
from routes.rahaza_bom import get_bom_materials, _is_kglike
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar
from utils.variant_ssot import resolve_variant, create_fg_pending_inbound_for_variant

router = APIRouter(prefix="/api", tags=["production-execution"])
logger = logging.getLogger(__name__)

# ─── PRODUCTION JOBS ─────────────────────────────────────────────────────────
async def _enrich_jobs(db, jobs: list) -> list:
    """Perkaya daftar production job (parent) dengan agregat item + child job.

    Diekstrak dari `get_jobs` (FASE IA-1, 2026-07-26) supaya endpoint baru
    `GET /api/production-tracking` memakai SATU sumber perhitungan yang sama —
    bukan menyalin ulang logikanya (pelajaran repo: dua penghitung = dua angka
    yang cepat menyimpang). Isi fungsi = cut-paste, logika TIDAK diubah.
    """
    job_ids = [j['id'] for j in jobs]
    if job_ids:
        all_child_jobs = await db.production_jobs.find({'parent_job_id': {'$in': job_ids}}, {'_id': 0}).to_list(None)
        child_ids = [c['id'] for c in all_child_jobs]
        owner_ids = job_ids + child_ids
        all_job_items = await db.production_job_items.find({'job_id': {'$in': owner_ids}}, {'_id': 0}).to_list(None)
    else:
        all_child_jobs, all_job_items = [], []

    children_by_parent = {}
    for c in all_child_jobs:
        children_by_parent.setdefault(c.get('parent_job_id'), []).append(c)
    items_by_job = {}
    for it in all_job_items:
        items_by_job.setdefault(it['job_id'], []).append(it)

    # Aggregate buyer shipped qty per job_item_id in one pipeline
    # ── PISAHKAN dua jenis pengiriman (audit 2026-08-01) ─────────────────────
    # `buyer_shipment_items` menampung DUA hal berbeda: deklarasi kirim vendor CMT
    # → DA (`receiver_type='da'`) dan dispatch DA → buyer (`receiver_type='buyer'`).
    # Dulu keduanya dijumlahkan menjadi satu angka, sehingga begitu DA mengirim ke
    # buyer, "sisa kirim" vendor ikut habis (padahal urusannya vendor→DA) dan
    # "total dikirim ke buyer" ikut menghitung deklarasi vendor.
    all_job_item_ids = [i['id'] for i in all_job_items]
    if all_job_item_ids:
        _da_ship_ids = await db.buyer_shipments.distinct('id', {'receiver_type': 'da'})
        buyer_agg = await db.buyer_shipment_items.aggregate([
            {'$match': {'job_item_id': {'$in': all_job_item_ids},
                        'shipment_id': {'$nin': _da_ship_ids}}},
            {'$group': {'_id': '$job_item_id', 'qty': {'$sum': '$qty_shipped'},
                        'recv': {'$sum': {'$ifNull': ['$qty_received', '$qty_shipped']}}}},
        ]).to_list(None)
        decl_agg = await db.buyer_shipment_items.aggregate([
            {'$match': {'job_item_id': {'$in': all_job_item_ids},
                        'shipment_id': {'$in': _da_ship_ids}}},
            {'$group': {'_id': '$job_item_id', 'qty': {'$sum': '$qty_shipped'},
                        'recv': {'$sum': {'$ifNull': ['$qty_received', '$qty_shipped']}}}},
        ]).to_list(None)
    else:
        buyer_agg, decl_agg = [], []
    buyer_by_item = {b['_id']: b['qty'] for b in buyer_agg}
    recv_by_item = {b['_id']: b['recv'] for b in buyer_agg}
    decl_by_item = {b['_id']: b['qty'] for b in decl_agg}
    decl_recv_by_item = {b['_id']: b['recv'] for b in decl_agg}

    # ── Portal CMT Override (keputusan owner 3a) ─────────────────────────────
    # Tagihan CMT dihitung dari progress. Kalau progress-nya diketik STAF DA atas
    # nama vendor (karena vendor tidak memakai sistem), itu harus KELIHATAN di
    # layar monitoring & invoice — bukan hanya tersimpan diam-diam di database.
    # Diagregasi di sini karena `_enrich_jobs` adalah SSOT yang dipakai BERSAMA
    # oleh `GET /production-jobs` dan `GET /production-tracking`, jadi kedua layar
    # mustahil menampilkan angka yang berbeda.
    owner_ids_for_prog = job_ids + [c['id'] for c in all_child_jobs]
    if owner_ids_for_prog:
        prog_agg = await db.production_progress.aggregate([
            {'$match': {'job_id': {'$in': owner_ids_for_prog}}},
            {'$group': {'_id': {'job': '$job_id',
                                'staff': {'$eq': [{'$ifNull': ['$entered_by_staff', False]}, True]}},
                        'n': {'$sum': 1},
                        'qty': {'$sum': {'$ifNull': ['$completed_quantity', 0]}},
                        'who': {'$addToSet': '$entered_by'}}},
        ]).to_list(None)
    else:
        prog_agg = []
    staff_prog: dict = {}
    for row in prog_agg:
        jid = row['_id']['job']
        bucket = staff_prog.setdefault(jid, {'staff_n': 0, 'staff_qty': 0,
                                             'vendor_n': 0, 'vendor_qty': 0, 'who': set()})
        if row['_id']['staff']:
            bucket['staff_n'] += row['n']
            bucket['staff_qty'] += row['qty'] or 0
            bucket['who'].update(w for w in (row.get('who') or []) if w)
        else:
            bucket['vendor_n'] += row['n']
            bucket['vendor_qty'] += row['qty'] or 0

    result = []
    for j in jobs:
        items = items_by_job.get(j['id'], [])
        child_jobs = children_by_parent.get(j['id'], [])
        total_ordered = sum(i.get('ordered_qty', 0) for i in items)
        total_available = sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in items)
        total_produced = sum(i.get('produced_qty', 0) for i in items)
        all_jobitem_ids = [i['id'] for i in items]
        for child in child_jobs:
            ci = items_by_job.get(child['id'], [])
            total_available += sum(i.get('available_qty', i.get('shipment_qty', 0)) for i in ci)
            total_produced += sum(i.get('produced_qty', 0) for i in ci)
            all_jobitem_ids.extend([ci_item['id'] for ci_item in ci])

        total_shipped_to_buyer = sum(buyer_by_item.get(iid, 0) for iid in all_jobitem_ids)
        total_received_to_buyer = sum(recv_by_item.get(iid, 0) for iid in all_jobitem_ids)
        # deklarasi kirim vendor → DA (dan qty yang BENAR-BENAR diterima DA)
        total_declared_to_da = sum(decl_by_item.get(iid, 0) for iid in all_jobitem_ids)
        total_received_by_da = sum(decl_recv_by_item.get(iid, 0) for iid in all_jobitem_ids)
        # SISA KIRIM: bila job ini memakai deklarasi CMT→DA, sisa kirim vendor
        # dihitung dari qty yang DITERIMA DA (aturan owner: selisih kirim membuka
        # kembali kapasitas kirim). Job lama tanpa deklarasi tetap memakai qty buyer.
        if total_declared_to_da > 0:
            remaining_to_ship = max(0, total_produced - total_received_by_da)
        else:
            remaining_to_ship = max(0, total_produced - total_received_to_buyer)
        serial_numbers = list({i.get('serial_number', '') for i in items if i.get('serial_number')})
        # ── FASE 1: agregat buku kuantitas QC per job (parent + child) ──────────
        from core import production_qty_ledger as _qled
        _all_items = list(items)
        for child in child_jobs:
            _all_items.extend(items_by_job.get(child['id'], []))
        qc = {k: 0 for k in ('qty_declared', 'qty_accepted', 'qty_reject',
                             'qty_rework_open', 'qty_repaired', 'qty_scrap',
                             'qty_claimed_by_vendor', 'qty_short_open', 'qty_short_resolved')}
        for it in _all_items:
            v = _qled.ledger_view(it)
            for k in qc:
                qc[k] += v[k]
        qc['qty_reject_undecided'] = max(
            0, qc['qty_reject'] - qc['qty_rework_open'] - qc['qty_repaired'] - qc['qty_scrap'])
        qc['reject_rate_pct'] = round(qc['qty_reject'] / total_produced * 100, 1) if total_produced else 0.0
        # ── ringkasan "diinput staf DA" per job (parent + child) ─────────────
        _sp = {'staff_n': 0, 'staff_qty': 0, 'vendor_n': 0, 'vendor_qty': 0, 'who': set()}
        for _jid in [j['id']] + [c['id'] for c in child_jobs]:
            b = staff_prog.get(_jid)
            if not b:
                continue
            _sp['staff_n'] += b['staff_n']; _sp['staff_qty'] += b['staff_qty']
            _sp['vendor_n'] += b['vendor_n']; _sp['vendor_qty'] += b['vendor_qty']
            _sp['who'].update(b['who'])
        if _sp['staff_n'] and _sp['vendor_n']:
            _src = 'mixed'
        elif _sp['staff_n']:
            _src = 'staff'
        elif _sp['vendor_n']:
            _src = 'vendor'
        else:
            _src = 'none'
        result.append({**serialize_doc(j), 'item_count': len(items),
                       'total_ordered': total_ordered, 'total_available': total_available,
                       'total_produced': total_produced, 'total_shipped_to_buyer': total_shipped_to_buyer,
                       'total_received_to_buyer': total_received_to_buyer,
                       'total_declared_to_da': total_declared_to_da,
                       'total_received_by_da': total_received_by_da,
                       'remaining_to_ship': remaining_to_ship,
                       'total_short_open': qc['qty_short_open'],
                       'total_claimed_by_vendor': qc['qty_claimed_by_vendor'],
                       'progress_pct': round((total_produced / total_available * 100) if total_available > 0 else 0),
                       'total_accepted': qc['qty_accepted'], 'total_reject': qc['qty_reject'],
                       'total_rework_open': qc['qty_rework_open'],
                       'total_repaired': qc['qty_repaired'], 'total_scrap': qc['qty_scrap'],
                       'reject_rate_pct': qc['reject_rate_pct'], 'qc_ledger': qc,
                       'serial_numbers': serial_numbers, 'child_job_count': len(child_jobs),
                       # keputusan 3a — dipakai badge "diinput staf DA" di layar
                       # Monitoring/Tracking Produksi & Invoice CMT.
                       'progress_entry_source': _src,
                       'staff_entered_progress_count': _sp['staff_n'],
                       'staff_entered_progress_qty': _sp['staff_qty'],
                       'vendor_entered_progress_count': _sp['vendor_n'],
                       'staff_entered_by': sorted(_sp['who']),
                       'job_entered_by_staff': j.get('entered_by_staff') is True,
                       'job_entered_by': j.get('entered_by', ''),
                       'child_jobs': [{'id': c['id'], 'job_number': c.get('job_number'),
                                       'status': c.get('status'),
                                       'shipment_type': c.get('shipment_type')} for c in child_jobs]})
    return result


@router.get("/production-jobs")
async def get_jobs(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    filt = {}
    # Portal CMT Override: satu pintu scoping (vendor → tokennya; staf override →
    # vendor yang diwakili; staf biasa → ?vendor_id seperti sebelumnya).
    from core.cmt_override import apply_scope
    await apply_scope(request, user, db, filt, param_vendor_id=sp.get('vendor_id'))
    if sp.get('status'): filt['status'] = sp['status']
    # FASE 5: filter business_type utk UI (maklon | internal)
    if sp.get('business_type') == 'internal':
        filt['business_type'] = 'internal'
    elif sp.get('business_type') == 'maklon':
        filt['business_type'] = {'$ne': 'internal'}
    include_children = sp.get('include_children') == 'true'
    if not include_children:
        filt['parent_job_id'] = {'$in': [None, '', False]}
    search = sp.get('search')
    if search:
        filt['$or'] = [
            {'job_number': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'vendor_name': {'$regex': search, '$options': 'i'}},
        ]

    # Pagination (Phase 10A) — applied to parent jobs
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'job_number', 'status', 'vendor_name'})
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    total = await db.production_jobs.count_documents(filt) if wants else None
    jobs = await db.production_jobs.find(filt, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)

    # Also include jobs where parent_job_id doesn't exist (legacy data without the field)
    if not include_children:
        extra_filt = {**{k: v for k, v in filt.items() if k != 'parent_job_id'},
                      'parent_job_id': {'$exists': False}}
        extra_limit = limit - len(jobs) if wants else LEGACY_DEFAULT_CAP
        if extra_limit > 0:
            extra = await db.production_jobs.find(extra_filt, {'_id': 0}).sort(sort).limit(extra_limit).to_list(extra_limit)
            existing_ids = {j['id'] for j in jobs}
            for e in extra:
                if e['id'] not in existing_ids:
                    jobs.append(e)

    # ── Phase 10B: agregasi item + child job (SSOT: _enrich_jobs) ──
    result = await _enrich_jobs(db, jobs)

    if wants:
        return _paginated_envelope(result, total, page, per_page)
    return result


@router.get("/production-tracking")
async def production_tracking(request: Request):
    """Tracking Produksi — progres Production Jobs dikelompokkan per vendor/pelaksana.

    Menggantikan `/api/production-monitoring-v2` yang **tidak pernah ada** di backend
    (modul FE memanggil path itu ⇒ 404 ⇒ layar selalu kosong TANPA pesan error).
    Ditemukan saat audit IA 2026-07-26; lihat docs/PROPOSAL_IA_PRODUKSI.md §3 cacat A.

    Query:
      business_type = internal | maklon   (WAJIB dipakai UI supaya data 2 domain terpisah)
      vendor_id     = filter satu vendor (opsional)

    Bentuk balasan = array vendor (kontrak dibaca `engine/ProductionMonitoringModule.jsx`).
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params

    filt = {}
    if is_vendor(user):
        filt['vendor_id'] = vendor_identity(user)
    elif sp.get('vendor_id'):
        filt['vendor_id'] = sp['vendor_id']
    bt = sp.get('business_type')
    if bt == 'internal':
        filt['business_type'] = 'internal'
    elif bt == 'maklon':
        filt['business_type'] = {'$ne': 'internal'}

    jobs = await db.production_jobs.find(filt, {'_id': 0}).sort('created_at', -1).to_list(LEGACY_DEFAULT_CAP)
    parents = [j for j in jobs if not j.get('parent_job_id')]
    enriched = await _enrich_jobs(db, parents)

    # Deadline fallback: job → PO (banyak job internal tak menyimpan deadline sendiri)
    po_ids = list({j.get('po_id') for j in enriched if j.get('po_id')})
    pos = await db.production_pos.find({'id': {'$in': po_ids}}, {'_id': 0, 'id': 1, 'deadline': 1,
                                                                'delivery_deadline': 1}).to_list(None) if po_ids else []
    po_deadline = {p['id']: (p.get('deadline') or p.get('delivery_deadline')) for p in pos}

    today = datetime.now(timezone.utc).date()

    def _as_date(v):
        try:
            if isinstance(v, datetime):
                return v.date()
            if isinstance(v, str) and v:
                return datetime.fromisoformat(v.replace('Z', '+00:00')).date()
        except Exception as e:  # noqa: BLE001
            logger.debug(f'[production-tracking] deadline tak terbaca ({v!r}): {e}')
        return None

    groups = {}
    for j in enriched:
        vid = j.get('vendor_id') or 'internal'
        g = groups.setdefault(vid, {
            'vendor_id': vid,
            'vendor_code': '',
            'vendor_name': j.get('vendor_name') or 'Produksi Internal',
            'location': '',
            'total_jobs': 0, 'total_qty': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0,
            # FASE 1: angka QC ikut diagregasi supaya Monitoring Produksi menampilkan
            # "produced 100, reject 10" — dulu reject tidak pernah muncul di layar ini.
            'total_accepted': 0, 'total_reject': 0, 'total_rework_open': 0,
            'total_repaired': 0, 'total_scrap': 0,
            # keputusan 3a — berapa pcs progress vendor ini yang DIKETIK staf DA
            'staff_entered_progress_qty': 0, 'staff_entered_progress_count': 0,
            'vendor_entered_progress_count': 0, 'staff_entered_by': [],
            'jobs_by_status': {'in_progress': 0, 'completed': 0},
            'jobs': [],
            '_overdue': 0, '_at_risk': 0,
        })
        deadline = j.get('deadline') or j.get('delivery_deadline') or po_deadline.get(j.get('po_id'))
        d = _as_date(deadline)
        status = (j.get('status') or '')
        done = status.lower() in ('completed', 'selesai', 'closed')
        if done:
            g['jobs_by_status']['completed'] += 1
        else:
            g['jobs_by_status']['in_progress'] += 1
        if d and not done:
            if d < today:
                g['_overdue'] += 1
            elif (d - today).days <= 3 and (j.get('progress_pct') or 0) < 80:
                g['_at_risk'] += 1

        g['total_jobs'] += 1
        g['total_qty'] += j.get('total_available') or j.get('total_ordered') or 0
        g['total_produced'] += j.get('total_produced') or 0
        g['total_shipped_to_buyer'] += j.get('total_shipped_to_buyer') or 0
        for _k in ('total_accepted', 'total_reject', 'total_rework_open',
                   'total_repaired', 'total_scrap'):
            g[_k] += j.get(_k) or 0
        for _k in ('staff_entered_progress_qty', 'staff_entered_progress_count',
                   'vendor_entered_progress_count'):
            g[_k] += j.get(_k) or 0
        g['staff_entered_by'] = sorted(set(g['staff_entered_by']) | set(j.get('staff_entered_by') or []))
        g['jobs'].append({
            'id': j.get('id'),
            'job_number': j.get('job_number'),
            'po_number': j.get('po_number'),
            'serial_numbers': j.get('serial_numbers') or [],
            'deadline': deadline,
            'total_available': j.get('total_available') or 0,
            'ordered_qty': j.get('total_ordered') or 0,
            'produced_qty': j.get('total_produced') or 0,
            'shipped_qty': j.get('total_shipped_to_buyer') or 0,
            'accepted_qty': j.get('total_accepted') or 0,
            'reject_qty': j.get('total_reject') or 0,
            'rework_open_qty': j.get('total_rework_open') or 0,
            'reject_rate_pct': j.get('reject_rate_pct') or 0,
            'status': j.get('status'),
            'progress_entry_source': j.get('progress_entry_source') or 'none',
            'staff_entered_progress_qty': j.get('staff_entered_progress_qty') or 0,
            'staff_entered_by': j.get('staff_entered_by') or [],
            'job_entered_by_staff': j.get('job_entered_by_staff') is True,
            'child_jobs': j.get('child_jobs') or [],
        })

    # Lengkapi kode/lokasi vendor dari master (garments → vendor_partners)
    out = []
    for vid, g in groups.items():
        if vid != 'internal':
            vdoc = await resolve_vendor_doc(db, vid)
            if vdoc:
                g['vendor_code'] = vdoc.get('garment_code') or vdoc.get('code') or ''
                g['vendor_name'] = vdoc.get('garment_name') or vdoc.get('name') or g['vendor_name']
                g['location'] = vdoc.get('location') or vdoc.get('city') or vdoc.get('address') or ''
        g['progress_pct'] = round((g['total_produced'] / g['total_qty'] * 100)) if g['total_qty'] > 0 else 0
        g['reject_rate_pct'] = round(g['total_reject'] / g['total_produced'] * 100, 1) if g['total_produced'] else 0.0
        g['performance'] = 'Overdue' if g.pop('_overdue') > 0 else ('At Risk' if g.pop('_at_risk') > 0 else 'On Track')
        g.pop('_overdue', None)
        g.pop('_at_risk', None)
        # keputusan owner 3a — satu kata untuk layar: angka vendor ini diketik
        # staf DA ('staff'), diisi vendor sendiri ('vendor'), campuran ('mixed'),
        # atau belum ada setoran ('none'). Dihitung di sini supaya badge di
        # Monitoring Produksi tidak perlu menjumlahkan ulang per baris job.
        _sn = int(g.get('staff_entered_progress_count') or 0)
        _vn = int(g.get('vendor_entered_progress_count') or 0)
        g['progress_entry_source'] = ('mixed' if (_sn and _vn) else
                                      'staff' if _sn else 'vendor' if _vn else 'none')
        out.append(g)

    # ── FASE 3 (keluhan #2 owner: "tracking produksi tidak 1 SSOT dengan maklon,
    # salah ambil collection, harusnya dari PO") ───────────────────────────────
    # Dulu layar ini HANYA mengelompokkan `production_jobs`. Akibatnya PO yang
    # SUDAH dibuat tetapi belum dikirimi material ke CMT (belum punya job)
    # TIDAK PERNAH terlihat — padahal itu justru PO yang perlu ditindak.
    # Sekarang: PO tanpa job ikut muncul sebagai baris "Menunggu kirim material"
    # dengan angka 0, jadi tracking benar-benar berbasis PO.
    po_filt: dict = {}
    if bt == 'internal':
        po_filt['business_type'] = 'internal'
    elif bt == 'maklon':
        po_filt['business_type'] = {'$ne': 'internal'}
    if filt.get('vendor_id'):
        po_filt['vendor_id'] = filt['vendor_id']
    po_filt['status'] = {'$nin': ['Cancelled', 'cancelled']}
    all_pos = await db.production_pos.find(po_filt, {'_id': 0}).to_list(LEGACY_DEFAULT_CAP)
    po_with_job = {j.get('po_id') for j in jobs if j.get('po_id')}
    pending_pos = [p for p in all_pos if p['id'] not in po_with_job]
    if pending_pos:
        pend_ids = [p['id'] for p in pending_pos]
        pend_items = await db.po_items.find({'po_id': {'$in': pend_ids}},
                                            {'_id': 0, 'po_id': 1, 'qty': 1}).to_list(None)
        qty_by_po: dict = {}
        for it in pend_items:
            qty_by_po[it['po_id']] = qty_by_po.get(it['po_id'], 0) + int(it.get('qty') or 0)
        by_vendor: dict = {}
        for p in pending_pos:
            vid = p.get('vendor_id') or 'internal'
            by_vendor.setdefault(vid, []).append(p)
        existing = {g['vendor_id']: g for g in out}
        for vid, plist in by_vendor.items():
            g = existing.get(vid)
            if not g:
                vname = plist[0].get('vendor_name') or ('Produksi Internal' if vid == 'internal' else '')
                if vid != 'internal':
                    vdoc = await resolve_vendor_doc(db, vid)
                    if vdoc:
                        vname = vdoc.get('garment_name') or vdoc.get('name') or vname
                g = {'vendor_id': vid, 'vendor_code': '', 'vendor_name': vname or '(vendor belum diisi)',
                     'location': '', 'total_jobs': 0, 'total_qty': 0, 'total_produced': 0,
                     'total_shipped_to_buyer': 0, 'total_accepted': 0, 'total_reject': 0,
                     'total_rework_open': 0, 'total_repaired': 0, 'total_scrap': 0,
                     'staff_entered_progress_qty': 0, 'staff_entered_progress_count': 0,
                     'vendor_entered_progress_count': 0, 'staff_entered_by': [],
                     'progress_entry_source': 'none',
                     'jobs_by_status': {'in_progress': 0, 'completed': 0}, 'jobs': [],
                     'progress_pct': 0, 'reject_rate_pct': 0.0, 'performance': 'On Track'}
                out.append(g)
                existing[vid] = g
            for p in plist:
                q = qty_by_po.get(p['id'], 0)
                g['total_qty'] += q
                g['jobs'].append({
                    'id': None, 'job_number': '(belum ada job)',
                    'po_id': p['id'], 'po_number': p.get('po_number'),
                    'serial_numbers': [], 'deadline': p.get('deadline') or p.get('delivery_deadline'),
                    'total_available': 0, 'ordered_qty': q, 'produced_qty': 0, 'shipped_qty': 0,
                    'accepted_qty': 0, 'reject_qty': 0, 'rework_open_qty': 0, 'reject_rate_pct': 0,
                    'status': 'Menunggu kirim material', 'awaiting_material': True,
                    'child_jobs': [],
                })
            g['progress_pct'] = round((g['total_produced'] / g['total_qty'] * 100)) if g['total_qty'] > 0 else 0

    out.sort(key=lambda v: (-v['total_jobs'], -len(v.get('jobs') or []), v['vendor_name']))
    return serialize_doc(out)

@router.get("/production-jobs/{jid}")
async def get_job(jid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    job = await db.production_jobs.find_one({'id': jid}, {'_id': 0})
    if not job: raise HTTPException(404, 'Not found')
    items = await db.production_job_items.find({'job_id': jid}, {'_id': 0}).to_list(None)
    # ── 10E: batch defect reports for all items in 1 query ──
    item_ids = [it['id'] for it in items]
    all_defects = await db.material_defect_reports.find({'job_item_id': {'$in': item_ids}}).to_list(None) if item_ids else []
    defect_by_item: dict = {}
    for d in all_defects: defect_by_item.setdefault(d.get('job_item_id'), []).append(d)
    enriched_items = []
    from core import production_qty_ledger as _qled
    for item in items:
        defects = defect_by_item.get(item['id'], [])
        total_defect = sum(d.get('defect_qty', 0) for d in defects)
        effective_available = max(0, (item.get('available_qty', item.get('shipment_qty', 0))) - total_defect)
        # buku kuantitas (termasuk SELISIH KIRIM: qty_short_open / claimed) supaya
        # portal vendor & DA melihat angka yang sama dari SATU sumber.
        enriched_items.append({**serialize_doc(item), **_qled.ledger_view(item),
                               'total_defect_qty': total_defect,
                               'effective_available_qty': effective_available})
    child_jobs = await db.production_jobs.find({'parent_job_id': jid}, {'_id': 0}).to_list(None)
    result = serialize_doc(job)
    result['items'] = enriched_items
    result['child_jobs'] = serialize_doc(child_jobs)
    return result

@router.get("/production-jobs/{jid}/production-guide")
async def get_job_production_guide(jid: str, request: Request):
    """Panduan Produksi (SOP + video + gambar referensi) untuk artikel pada job ini.

    RELATION FIX: sebelumnya Panduan Produksi vendor hanya membaca `rahaza_models`
    (internal). Buyer-catalog SOP (Maklon) di `dewi_maklon_buyer_catalog` tidak pernah
    dibaca (write-only). Endpoint ini me-resolve SOP dari sumber yang BENAR:
      - Maklon  → dewi_maklon_buyer_catalog (via catalog_item_id)
      - Internal→ rahaza_models (via model_id)
    Resolusi: job_items (field relasi yang sudah dipropagasi) → fallback po_items PO ini.
    Scoped: vendor CMT hanya boleh melihat panduan untuk job miliknya.
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    job = await db.production_jobs.find_one({'id': jid}, {'_id': 0})
    if not job:
        raise HTTPException(404, 'Pekerjaan tidak ditemukan')
    if is_vendor(user) and job.get('vendor_id') != vendor_identity(user):
        raise HTTPException(403, 'Bukan pekerjaan milik vendor ini')
    # Mode override (staf DA atas nama vendor) ikut di-scope.
    from core.cmt_override import resolve_override
    _ov = await resolve_override(request, user, db)
    if _ov and job.get('vendor_id') != _ov['vendor_id']:
        raise HTTPException(403, f"Bukan pekerjaan milik {_ov['vendor_name']}")

    # 1) Kumpulkan referensi artikel dari job_items (field relasi hasil propagasi)
    job_items = await db.production_job_items.find({'job_id': jid}, {'_id': 0}).to_list(None)
    catalog_ids, model_ids, poi_ids = set(), set(), set()
    for ji in job_items:
        if ji.get('catalog_item_id'): catalog_ids.add(ji['catalog_item_id'])
        if ji.get('model_id'): model_ids.add(ji['model_id'])
        if ji.get('po_item_id'): poi_ids.add(ji['po_item_id'])

    # 2) Fallback: resolve via po_items (job lama sebelum propagasi, atau data seed)
    if not catalog_ids and not model_ids:
        po_items = []
        if poi_ids:
            po_items = await db.po_items.find({'id': {'$in': list(poi_ids)}}, {'_id': 0}).to_list(None)
        if not po_items and job.get('po_id'):
            po_items = await db.po_items.find({'po_id': job['po_id']}, {'_id': 0}).to_list(None)
        for it in po_items:
            if it.get('catalog_item_id'): catalog_ids.add(it['catalog_item_id'])
            if it.get('model_id'): model_ids.add(it['model_id'])

    guides = []
    for cid in catalog_ids:
        cat = await db.dewi_maklon_buyer_catalog.find_one({'id': cid}, {'_id': 0})
        if cat:
            guides.append({
                'source_type': 'buyer_catalog',
                'code': cat.get('artikel_code', ''),
                'name': cat.get('product_name', ''),
                'description': cat.get('description', ''),
                'image_paths': [],
                'hero_image_url': cat.get('hero_image_url', ''),
                'sop_steps': list(cat.get('sop_steps') or []),
                'reference_videos': list(cat.get('reference_videos') or []),
                'reference_images': list(cat.get('reference_images') or []),
                'sop_updated_at': cat.get('sop_updated_at'),
                'sop_updated_by': cat.get('sop_updated_by', ''),
            })
    for mid in model_ids:
        mdl = await db.rahaza_models.find_one({'id': mid}, {'_id': 0})
        if mdl:
            guides.append({
                'source_type': 'rahaza_model',
                'code': mdl.get('code', ''),
                'name': mdl.get('name', ''),
                'description': mdl.get('description', ''),
                'image_paths': list(mdl.get('image_paths') or []),
                'hero_image_url': '',
                'sop_steps': list(mdl.get('sop_steps') or []),
                'reference_videos': list(mdl.get('reference_videos') or []),
                'reference_images': list(mdl.get('reference_images') or []),
                'sop_updated_at': mdl.get('sop_updated_at'),
                'sop_updated_by': mdl.get('sop_updated_by', ''),
            })

    has_guide = len(guides) > 0
    has_content = any(
        (g.get('sop_steps') or g.get('reference_videos') or g.get('reference_images')
         or g.get('image_paths') or g.get('hero_image_url'))
        for g in guides
    )
    if not has_guide:
        msg = ('Belum ada artikel master (Katalog Buyer / Model) yang tertaut ke pekerjaan ini. '
               'Hubungi admin/PPIC untuk melengkapi.')
    elif not has_content:
        msg = ('Artikel sudah tertaut, namun Panduan Produksi (SOP) belum diisi. '
               'Isi di Katalog Buyer → Panduan Produksi (Maklon) atau Master Produk (Internal).')
    else:
        msg = ''
    return serialize_doc({
        'has_guide': has_guide,
        'has_content': has_content,
        'business_type': job.get('business_type', 'maklon'),
        'job_number': job.get('job_number', ''),
        'guides': guides,
        'message': msg,
    })


@router.post("/production-jobs")
async def create_job(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    # ── Fase 3: job INTERNAL dibuat langsung dari PO (tanpa vendor shipment).
    # Jalur shipment→inspeksi khusus maklon/CMT.
    if body.get('po_id') and not body.get('vendor_shipment_id'):
        from routes.production_internal_adapter import create_internal_job
        return await create_internal_job(db, body, user)
    from core.cmt_override import effective_vendor_id, resolve_override, stamp as ov_stamp
    _ov = await resolve_override(request, user, db)
    vendor_id = await effective_vendor_id(request, user, db, body.get('vendor_id'))
    if not vendor_id: raise HTTPException(400, 'vendor_id diperlukan')
    shipment = await db.vendor_shipments.find_one({'id': body.get('vendor_shipment_id')})
    if not shipment: raise HTTPException(404, 'Shipment tidak ditemukan')
    if shipment.get('status') != 'Received': raise HTTPException(400, 'Shipment belum dikonfirmasi diterima.')
    if shipment.get('vendor_id') != vendor_id: raise HTTPException(403, 'Shipment ini bukan milik vendor Anda')
    if shipment.get('inspection_status') != 'Inspected':
        raise HTTPException(400, f"Inspeksi material belum selesai.")
    existing = await db.production_jobs.find_one({'vendor_shipment_id': body['vendor_shipment_id']})
    if existing: raise HTTPException(400, f"Production Job sudah ada ({existing.get('job_number')})")
    parent_job_id = None
    parent_job_number = None
    if shipment.get('parent_shipment_id'):
        parent_job = await db.production_jobs.find_one({'vendor_shipment_id': shipment['parent_shipment_id']})
        if parent_job:
            parent_job_id = parent_job['id']
            parent_job_number = parent_job.get('job_number')
    ship_items = await db.vendor_shipment_items.find({'shipment_id': body['vendor_shipment_id']}).to_list(None)
    po_id = body.get('po_id') or (ship_items[0].get('po_id') if ship_items else None)
    po = await db.production_pos.find_one({'id': po_id}) if po_id else None
    job_id = new_id()
    if parent_job_number:
        # ── RC-5 (2026-08-07) ────────────────────────────────────────────────
        # Nomor job ANAK dulu memakai `count_documents({parent_job_id}) + 1`.
        # Dua pengiriman tambahan/rework yang masuk bersamaan membaca hitungan
        # yang SAMA lalu menghasilkan nomor job KEMBAR (mis. dua "JOB-0007-R1"),
        # sehingga catatan produksi dua kiriman berbeda saling tertukar.
        # Sekarang urutannya dari counter atomik per JOB INDUK.
        from utils.counters import next_counter
        suffix = 'A' if shipment.get('shipment_type') == 'ADDITIONAL' else 'R'
        child_seq = await next_counter(
            db, f"autonum:production_jobs:child:{parent_job_id}:{suffix}",
            namespace='autonum')
        job_number = f"{parent_job_number}-{suffix}{child_seq}"
    else:
        # RC-5 fix: atomic race-safe numbering (was count_documents()+1 → nomor
        # job kembar saat dua job dibuat bersamaan, dan nomor DIPAKAI ULANG
        # setelah job dihapus).
        from utils.counters import gen_prefixed_number
        job_number = await gen_prefixed_number(db, 'production_jobs', 'job_number',
                                               'JOB-', 4)
    job = {
        'id': job_id, 'job_number': job_number,
        'parent_job_id': parent_job_id, 'parent_job_number': parent_job_number,
        'vendor_id': vendor_id, 'vendor_name': shipment.get('vendor_name', ''),
        'po_id': po_id, 'po_number': (po or {}).get('po_number', ''),
        'customer_name': (po or {}).get('customer_name', ''),
        'vendor_shipment_id': body['vendor_shipment_id'],
        'shipment_number': shipment.get('shipment_number'),
        'shipment_type': shipment.get('shipment_type', 'NORMAL'),
        'business_type': (po or {}).get('business_type', shipment.get('business_type', 'internal')),
        'deadline': (po or {}).get('deadline'), 'delivery_deadline': (po or {}).get('delivery_deadline'),
        'status': 'In Progress', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now(),
        # keputusan 3a — jejak "diinput staf DA" (kosong bila bukan mode override)
        **ov_stamp(_ov),
    }
    await db.production_jobs.insert_one(job)
    inspection = await db.vendor_material_inspections.find_one({'shipment_id': body['vendor_shipment_id']})
    inserted_items = []
    for si in ship_items:
        po_item = await db.po_items.find_one({'id': si.get('po_item_id')}) if si.get('po_item_id') else None
        available_qty = si.get('qty_sent', 0)
        if inspection:
            insp_item = await db.vendor_material_inspection_items.find_one({'inspection_id': inspection['id'], 'shipment_item_id': si['id']})
            if not insp_item:
                insp_item = await db.vendor_material_inspection_items.find_one({'inspection_id': inspection['id'], 'sku': si.get('sku', ''), 'size': si.get('size', ''), 'color': si.get('color', '')})
            if insp_item:
                available_qty = insp_item.get('received_qty', si.get('qty_sent', 0))
        ji = {
            'id': new_id(), 'job_id': job_id, 'job_number': job_number,
            'po_item_id': si.get('po_item_id'),
            'vendor_shipment_item_id': si['id'],
            'product_name': si.get('product_name', ''), 'sku': si.get('sku', ''),
            'size': si.get('size', ''), 'color': si.get('color', ''),
            # [RELATION FIX] carry master-data links forward so downstream consumers
            # (Panduan Produksi/SOP resolver, finance, reports) can resolve the article/variant.
            'catalog_item_id': (po_item or {}).get('catalog_item_id'),   # maklon → dewi_maklon_buyer_catalog
            'maklon_variant_id': (po_item or {}).get('maklon_variant_id'),
            'model_id': (po_item or {}).get('model_id'),                 # internal → rahaza_models
            'rahaza_variant_id': (po_item or {}).get('rahaza_variant_id'),
            # [DISPLAY FIX] carry buyer's article code + short color code so the
            # vendor/production job views can show them (previously stored on
            # po_items only → never surfaced to who actually produces).
            'buyer_ref_code': (po_item or {}).get('buyer_ref_code', ''),
            'color_code': (po_item or {}).get('color_code', si.get('color_code', '')),
            'serial_number': (po_item or {}).get('serial_number', si.get('serial_number', '')),
            'ordered_qty': (po_item or {}).get('qty', si.get('qty_sent', 0)),
            'shipment_qty': si.get('qty_sent', 0), 'available_qty': available_qty,
            'produced_qty': 0, 'created_at': now()
        }
        await db.production_job_items.insert_one(ji)
        inserted_items.append(ji)
    if po_id:
        current_po = await db.production_pos.find_one({'id': po_id})
        if current_po and current_po.get('status') not in ['Completed', 'Closed']:
            await db.production_pos.update_one({'id': po_id}, {'$set': {'status': 'In Production', 'updated_at': now()}})
    await log_activity(user['id'], user['name'], 'Create', 'Production Job', f"Created job {job_number}")
    result = serialize_doc(job)
    result['items'] = serialize_doc(inserted_items)
    return JSONResponse(result, status_code=201)

@router.delete("/production-jobs/{jid}")
async def delete_job(jid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.production_jobs.find_one({'id': jid})
    if not doc: raise HTTPException(404, 'Not found')
    child_jobs = await db.production_jobs.find({'parent_job_id': jid}).to_list(None)
    for cj in child_jobs:
        await db.production_job_items.delete_many({'job_id': cj['id']})
        await db.production_progress.delete_many({'job_id': cj['id']})
        await db.production_jobs.delete_one({'id': cj['id']})
    await db.production_job_items.delete_many({'job_id': jid})
    await db.production_progress.delete_many({'job_id': jid})
    await db.production_jobs.delete_one({'id': jid})
    await log_activity(user['id'], user['name'], 'Delete', 'Production Job', f"Deleted job: {doc.get('job_number')}")
    return {'success': True}

# ─── PRODUCTION JOB ITEMS ────────────────────────────────────────────────────
@router.get("/production-job-items")
async def get_job_items(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    job_id = request.query_params.get('job_id')
    if not job_id: raise HTTPException(400, 'job_id required')
    # Scoping: vendor & staf mode override hanya boleh membaca job miliknya/vendor
    # yang diwakili — supaya layar override tidak pernah menampilkan job vendor lain.
    from core.cmt_override import resolve_override
    _ov = await resolve_override(request, user, db)
    if is_vendor(user) or _ov:
        _want = vendor_identity(user) if is_vendor(user) else _ov['vendor_id']
        _jdoc = await db.production_jobs.find_one({'id': job_id}, {'_id': 0, 'vendor_id': 1})
        if not _jdoc or _jdoc.get('vendor_id') != _want:
            raise HTTPException(403, 'Pekerjaan ini bukan milik vendor tersebut')
    items = await db.production_job_items.find({'job_id': job_id}, {'_id': 0}).to_list(None)
    child_jobs = await db.production_jobs.find({'parent_job_id': job_id}).to_list(None)
    child_job_ids = [c['id'] for c in child_jobs]
    # ── 10E: batch child items, progress history, buyer items ──
    all_child_items = await db.production_job_items.find({'job_id': {'$in': child_job_ids}}).to_list(None) if child_job_ids else []
    child_items_by_poi: dict = {}
    for c in all_child_items:
        key = c.get('po_item_id') or c['id']
        child_items_by_poi.setdefault(key, []).append(c)
    all_item_ids = [it['id'] for it in items]
    all_progress = await db.production_progress.find({'job_item_id': {'$in': all_item_ids}}, {'_id': 0}).sort('progress_date', -1).to_list(None) if all_item_ids else []
    progress_by_item: dict = {}
    for p in all_progress: progress_by_item.setdefault(p.get('job_item_id'), []).append(p)
    all_po_item_ids = [it['po_item_id'] for it in items if it.get('po_item_id')]
    all_child_item_ids = [c['id'] for c in all_child_items]
    buyer_q = {}
    if all_po_item_ids:
        buyer_q = {'po_item_id': {'$in': all_po_item_ids}}
    elif all_child_item_ids or all_item_ids:
        buyer_q = {'job_item_id': {'$in': list({*all_item_ids, *all_child_item_ids})}}
    all_buyer = await db.buyer_shipment_items.find(buyer_q).to_list(None) if buyer_q else []
    # pisahkan deklarasi vendor→DA dari dispatch DA→buyer (lihat catatan di atas)
    _da_ship_ids = set(await db.buyer_shipments.distinct('id', {'receiver_type': 'da'}))
    buyer_by_poi: dict = {}
    buyer_by_ji: dict = {}
    recv_by_poi: dict = {}
    recv_by_ji: dict = {}
    decl_by_poi: dict = {}
    decl_by_ji: dict = {}
    decl_recv_by_poi: dict = {}
    decl_recv_by_ji: dict = {}
    for b in all_buyer:
        eff = b['qty_received'] if b.get('qty_received') is not None else b.get('qty_shipped', 0)
        is_decl = b.get('shipment_id') in _da_ship_ids
        qty_map, recv_map = ((decl_by_poi, decl_recv_by_poi) if is_decl else (buyer_by_poi, recv_by_poi))
        qty_map_ji, recv_map_ji = ((decl_by_ji, decl_recv_by_ji) if is_decl else (buyer_by_ji, recv_by_ji))
        if b.get('po_item_id'):
            qty_map[b['po_item_id']] = qty_map.get(b['po_item_id'], 0) + b.get('qty_shipped', 0)
            recv_map[b['po_item_id']] = recv_map.get(b['po_item_id'], 0) + eff
        if b.get('job_item_id'):
            qty_map_ji[b['job_item_id']] = qty_map_ji.get(b['job_item_id'], 0) + b.get('qty_shipped', 0)
            recv_map_ji[b['job_item_id']] = recv_map_ji.get(b['job_item_id'], 0) + eff
    result = []
    from core import production_qty_ledger as _qled
    for item in items:
        progress = progress_by_item.get(item['id'], [])
        key = item.get('po_item_id') or item['id']
        child_items = child_items_by_poi.get(key, [])
        child_produced = sum(ci.get('produced_qty', 0) for ci in child_items)
        total_produced = (item.get('produced_qty', 0)) + child_produced
        all_job_item_ids = [item['id']] + [ci['id'] for ci in child_items]
        if item.get('po_item_id'):
            shipped = buyer_by_poi.get(item['po_item_id'], 0)
            received = recv_by_poi.get(item['po_item_id'], 0)
            declared_da = decl_by_poi.get(item['po_item_id'], 0)
            received_da = decl_recv_by_poi.get(item['po_item_id'], 0)
        else:
            shipped = sum(buyer_by_ji.get(jid2, 0) for jid2 in all_job_item_ids)
            received = sum(recv_by_ji.get(jid2, 0) for jid2 in all_job_item_ids)
            declared_da = sum(decl_by_ji.get(jid2, 0) for jid2 in all_job_item_ids)
            received_da = sum(decl_recv_by_ji.get(jid2, 0) for jid2 in all_job_item_ids)
        # SISA KIRIM vendor: dihitung dari qty yang DITERIMA DA bila item ini
        # memakai deklarasi CMT→DA (selisih kirim membuka kapasitas kirim ulang).
        remaining_to_ship = max(0, total_produced - (received_da if declared_da > 0 else received))
        # ── FASE 1: buku kuantitas QC ikut disajikan. `produced_qty` TIDAK pernah
        # dikurangi reject (kebijakan owner: "dikirim 100 reject 10 → tetap 100"),
        # tetapi accepted/reject/rework/scrap tampil eksplisit di sisi vendor & DA.
        led = _qled.ledger_view(item)
        for ci in child_items:
            cl = _qled.ledger_view(ci)
            for k in ('qty_declared', 'qty_accepted', 'qty_reject',
                      'qty_rework_open', 'qty_repaired', 'qty_scrap',
                      'qty_claimed_by_vendor', 'qty_short_open', 'qty_short_resolved'):
                led[k] += cl[k]
        led['qty_reject_undecided'] = max(
            0, led['qty_reject'] - led['qty_rework_open'] - led['qty_repaired'] - led['qty_scrap'])
        led['reject_rate_pct'] = round(led['qty_reject'] / total_produced * 100, 1) if total_produced else 0.0
        result.append({**serialize_doc(item), 'progress_history': serialize_doc(progress),
                       'shipped_to_buyer': shipped, 'received_to_buyer': received,
                       'declared_to_da': declared_da, 'received_by_da': received_da,
                       'remaining_to_ship': remaining_to_ship,
                       'qty_short_open': led['qty_short_open'],
                       'qty_claimed_by_vendor': led['qty_claimed_by_vendor'],
                       'child_produced_qty': child_produced, 'total_produced_qty': total_produced,
                       'qty_declared': led['qty_declared'], 'qty_accepted': led['qty_accepted'],
                       'qty_reject': led['qty_reject'], 'qty_rework_open': led['qty_rework_open'],
                       'qty_repaired': led['qty_repaired'], 'qty_scrap': led['qty_scrap'],
                       'qty_reject_undecided': led['qty_reject_undecided'],
                       'reject_rate_pct': led['reject_rate_pct'],
                       'qc_ledger': led})
    return result

@router.get("/production-jobs/{job_id}/bom-material-lines")
async def get_job_bom_material_lines(job_id: str, request: Request):
    """FASE P4: Baris material Surat Jalan Internal dari BOM aktif (yarn + accessory) x qty tiap job item.
    Dipakai untuk auto-isi 'lines' Surat Jalan (SJ-CMT) job produksi internal. Read-only (tidak menulis stok)."""
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    job = await db.production_jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(404, 'Job tidak ditemukan')
    items = await db.production_job_items.find({'job_id': job_id}, {'_id': 0}).to_list(None)
    agg: dict = {}          # (name.lower(), unit) -> {description, qty, unit, remarks}
    uom_notices: list = []  # peringatan satuan (mis. satuan BOM tak bisa dikonversi)
    missing: list = []      # job item tanpa BOM aktif
    size_cache: dict = {}
    for it in items:
        model_id = it.get('model_id')
        size_str = (it.get('size') or '').strip()
        qty = float(it.get('available_qty') or it.get('shipment_qty') or it.get('qty') or 0)
        if not model_id or qty <= 0:
            continue
        # resolve size string -> size_id
        size_id = size_cache.get(size_str) if size_str in size_cache else None
        if size_str and size_str not in size_cache:
            sz = await db.rahaza_sizes.find_one(
                {'$or': [{'code': size_str}, {'code': size_str.upper()}, {'name': size_str}]}, {'_id': 0})
            size_id = sz['id'] if sz else None
            size_cache[size_str] = size_id
        bom = None
        color_str = (it.get('color') or '').strip()
        if size_id:
            if color_str:  # Fase 4: prefer BOM spesifik-warna
                bom = await db.rahaza_boms.find_one(
                    {'model_id': model_id, 'size_id': size_id, 'color': color_str,
                     'is_active': True, 'active': True}, {'_id': 0})
            if not bom:  # BOM umum (warna kosong)
                bom = await db.rahaza_boms.find_one(
                    {'model_id': model_id, 'size_id': size_id,
                     'color': {'$in': ['', None]}, 'is_active': True, 'active': True}, {'_id': 0})
            if not bom:  # BOM apa pun utk model+size (BOM lama tanpa field color)
                bom = await db.rahaza_boms.find_one(
                    {'model_id': model_id, 'size_id': size_id, 'is_active': True, 'active': True}, {'_id': 0})
        if not bom:  # fallback: BOM aktif apa pun utk model ini
            bom = await db.rahaza_boms.find_one(
                {'model_id': model_id, 'is_active': True, 'active': True}, {'_id': 0})
        if not bom:
            missing.append({'model_id': model_id, 'size': size_str, 'sku': it.get('sku')})
            continue
        # 2026-08-02 · SATUAN: baris Surat Jalan dicetak dalam SATUAN DASAR
        # material (yang juga satuan stok), satuan input BOM ditulis di remark
        # supaya jejaknya tetap terlihat.
        bom_mats, uom_warn = await bom_uom.ensure_uom(db, bom)
        for w in uom_warn:
            if w not in uom_notices:
                uom_notices.append(w)
        for m in bom_mats:
            per = bom_uom.qty_base_of(m)
            if per <= 0 or not m.get('name'):
                continue
            unit = bom_uom.base_unit_of(m) or ('kg' if _is_kglike(m) else 'pcs')
            k = (m['name'].lower(), unit)
            default_remark = 'Kain/Benang' if _is_kglike({**m, 'unit': unit}) else 'Aksesoris'
            remark = (m.get('code') or m.get('category_name') or default_remark)
            if m.get('uom_status') in ('uom', 'global', 'fabric'):
                remark = f"{remark} · BOM {bom_uom.norm_unit(m.get('unit'))}→{unit}"
            row = agg.setdefault(k, {'description': m['name'], 'qty': 0.0, 'unit': unit,
                                     'remarks': remark})
            row['qty'] += per * qty
    lines = []
    for i, row in enumerate(agg.values()):
        row['qty'] = round(row['qty'], 3)
        lines.append({'line_no': i + 1, **row})
    return {'job_id': job_id, 'job_number': job.get('job_number'),
            'business_type': job.get('business_type'), 'lines': lines,
            'missing_bom': missing, 'uom_notices': uom_notices}


# ─── PRODUCTION PROGRESS ─────────────────────────────────────────────────────
@router.get("/production-progress")
async def get_progress(request: Request):
    """Riwayat setoran progress produksi.

    ── BUG NYATA yang ditutup (2026-08-08) ──────────────────────────────────
    Filter vendornya dulu `query['garment_id'] = vendor_identity(user)`, padahal
    progress jalur `job_item_id` (satu-satunya jalur yang dipakai portal vendor
    CMT lewat VendorProgress.jsx) **tidak pernah menulis field `garment_id`**.
    Terbukti di DB: nol dokumen `production_progress` punya `garment_id`.
    Akibatnya panel "Riwayat Progress" di portal vendor SELALU KOSONG — vendor
    tidak bisa memeriksa setorannya sendiri, padahal angka itulah dasar tagihan.

    Sekarang vendor di-resolusi lewat `production_jobs.vendor_id` (SSOT), dengan
    `garment_id` tetap diikutkan sebagai jalur legacy (progress work_order lama).
    """
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    query = {}
    sp = request.query_params
    if sp.get('work_order_id'): query['work_order_id'] = sp['work_order_id']
    if sp.get('job_id'): query['job_id'] = sp['job_id']
    if sp.get('job_item_id'): query['job_item_id'] = sp['job_item_id']

    from core.cmt_override import resolve_override
    _ov = await resolve_override(request, user, db)
    if is_vendor(user):
        vid = vendor_identity(user)
    elif _ov:
        vid = _ov['vendor_id']
    else:
        vid = sp.get('vendor_id') or None
    if vid:
        job_ids = await db.production_jobs.distinct('id', {'vendor_id': vid})
        query['$or'] = [{'job_id': {'$in': job_ids}}, {'garment_id': vid}]
    return serialize_doc(await db.production_progress.find(query, {'_id': 0}).sort('progress_date', -1).to_list(None))

@router.post("/production-progress")
async def create_progress(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    require_write_actor(user, check_role)
    db = get_db()
    body = await request.json()
    # Portal CMT Override — staf DA mengisi progress ATAS NAMA vendor CMT.
    # Jejaknya WAJIB menempel di dokumen (keputusan owner 3a): angka inilah dasar
    # tagihan CMT, jadi harus bisa ditelusuri "dari vendor" vs "dari staf".
    from core.cmt_override import resolve_override, stamp as ov_stamp
    _ov = await resolve_override(request, user, db)
    if body.get('job_item_id'):
        job_item = await db.production_job_items.find_one({'id': body['job_item_id']})
        if not job_item: raise HTTPException(404, 'Job item tidak ditemukan')
        qty_today = int(body.get('completed_quantity', 0) or 0)
        if qty_today <= 0: raise HTTPException(400, 'Jumlah produksi harus lebih dari 0')

        # ─── K5 (Phase C): capacity gate on AVAILABLE MATERIAL only ──────────
        # Defect reports are no longer a production gate (material_defect_reports
        # deprecated per K5). FG defects are caught downstream at DA CMT-receipt
        # inspection (Phase B: qty_actual + reject_qty). Cap = Σprogress ≤ available_qty.
        effective_max = max(0, int(job_item.get('available_qty', job_item.get('shipment_qty', 0)) or 0))

        job_doc = await db.production_jobs.find_one({'id': job_item.get('job_id')}, {'_id': 0}) or {}
        # Mode override: job WAJIB milik vendor yang sedang diwakili (anti salah vendor).
        if _ov and job_doc.get('vendor_id') != _ov['vendor_id']:
            raise HTTPException(
                403,
                f"Pekerjaan ini bukan milik {_ov['vendor_name']}. "
                'Pilih vendor yang benar di Portal CMT Override.')
        # ── Fase 3 (GDG-2): progress internal digate penyerahan material gudang ──
        if job_doc.get('business_type') == 'internal':
            issued_mi = await db.rahaza_material_issues.find_one(
                {'job_id': job_item.get('job_id'), 'status': 'issued'}, {'_id': 0, 'id': 1})
            if not issued_mi:
                raise HTTPException(400,
                    'Material belum diserahkan gudang (Material Issue belum berstatus issued) — '
                    'progress produksi internal ditolak (GDG-2)')
        # ── Fase 3 (HR-1): optional operator+process → validasi dulu, mirror setelah insert ──
        _wip_ctx = None
        if body.get('operator_id') or body.get('process_id'):
            if job_doc.get('business_type') != 'internal':
                raise HTTPException(400, 'operator_id/process_id hanya untuk job internal (payroll pcs internal)')
            if not (body.get('operator_id') and body.get('process_id')):
                raise HTTPException(400, 'operator_id dan process_id harus dikirim bersama')
            from routes.production_internal_adapter import resolve_operator_process
            _wip_ctx = await resolve_operator_process(db, body['operator_id'], body['process_id'])
        new_total = (job_item.get('produced_qty', 0)) + qty_today
        if new_total > effective_max:
            raise HTTPException(400,
                f"Total produksi ({new_total} pcs) melebihi material tersedia ({effective_max} pcs).")
        progress = {
            'id': new_id(), 'job_id': job_item.get('job_id'), 'job_item_id': body['job_item_id'],
            'sku': job_item.get('sku', ''), 'product_name': job_item.get('product_name', ''),
            'size': job_item.get('size', ''), 'color': job_item.get('color', ''),
            'progress_date': parse_date(body.get('progress_date')) or now(),
            'completed_quantity': qty_today, 'notes': body.get('notes', ''),
            'recorded_by': user['name'], 'created_at': now(),
            **ov_stamp(_ov),
        }
        await db.production_progress.insert_one(progress)
        await db.production_job_items.update_one({'id': body['job_item_id']}, {'$set': {'produced_qty': new_total, 'updated_at': now()}})
        # ── SSOT (BUG-1): internal production output → per-variant FG receipt ──
        # Resolve the canonical variant (color+size) from the job item and create a
        # WMS pending-inbound so warehouse scan-in adds physical FG stock keyed by
        # the canonical SKU (rahaza_materials.code == {MODEL}-{COLOR}-{SIZE}).
        if job_doc.get('business_type') == 'internal' and qty_today > 0:
            try:
                _variant = await resolve_variant(
                    db,
                    variant_id=job_item.get('rahaza_variant_id'),
                    sku=job_item.get('sku'),
                )
                if _variant:
                    await create_fg_pending_inbound_for_variant(
                        db, _variant, qty_today,
                        source_type='production_internal',
                        source_id=progress['id'],
                        source_ref=job_item.get('job_number') or job_item.get('job_id') or '',
                        user=user,
                        notes=f"Output produksi internal {qty_today} pcs (job {job_item.get('job_number', '')}) — scan-in gudang",
                    )
                else:
                    import logging as _lg
                    _lg.getLogger(__name__).warning(
                        'FG receipt dilewati: varian tidak ter-resolusi utk job_item %s (sku=%s). '
                        'Pastikan item PO internal memilih varian (warna+size).',
                        body.get('job_item_id'), job_item.get('sku'))
            except Exception:
                import logging as _lg
                _lg.getLogger(__name__).exception('FG pending-inbound (progress internal) gagal')
        all_items = await db.production_job_items.find({'job_id': job_item['job_id']}).to_list(None)
        all_done = all(
            (new_total if i['id'] == body['job_item_id'] else i.get('produced_qty', 0)) >= i.get('shipment_qty', 0)
            for i in all_items
        )
        if _wip_ctx is not None:
            from routes.production_internal_adapter import insert_wip_mirror
            await insert_wip_mirror(db, job_doc, job_item, qty_today, _wip_ctx, user, progress_id=progress['id'])
        _completed_hook = None
        if all_done:
            # Stempel `closed_at` ditulis SERVER lewat SATU penulis
            # (`core.production_job_lifecycle.close_job`) — tanpa itu rekap tanggal
            # LAMPAU tidak bisa tahu job ini masih jalan pada hari itu, dan
            # kelalaian yang sudah terjadi terhapus sendiri begitu job ditutup.
            from core.production_job_lifecycle import close_job
            await close_job(db, job_item['job_id'])
            # ── Fase 3 (AD-3): job internal Completed → HPP snapshot + posting WIP→FG ──
            if job_doc.get('business_type') == 'internal':
                try:
                    from routes.production_internal_adapter import on_job_completed_internal
                    _completed_hook = await on_job_completed_internal(db, {**job_doc, 'status': 'Completed'}, user)
                except Exception:
                    import logging; logging.getLogger(__name__).exception(
                        'Hook job-completed internal gagal utk job %s', job_item.get('job_id'))
        await log_activity(user['id'], user['name'], 'Create', 'Production Progress', f"Progress {job_item.get('sku')}: +{qty_today}")
        result = serialize_doc(progress)
        result['new_total'] = new_total
        if _completed_hook is not None:
            result['job_completed_hook'] = serialize_doc(_completed_hook)
        return JSONResponse(result, status_code=201)
    # Legacy: work_order_id
    wo = await db.work_orders.find_one({'id': body.get('work_order_id')})
    if not wo: raise HTTPException(404, 'Work order tidak ditemukan')
    progress = {
        'id': new_id(), 'work_order_id': body['work_order_id'],
        'distribution_code': wo.get('distribution_code'),
        'garment_id': wo.get('garment_id'), 'garment_name': wo.get('garment_name'),
        'po_id': wo.get('po_id'), 'po_number': wo.get('po_number'),
        'progress_date': parse_date(body.get('progress_date')) or now(),
        'completed_quantity': int(body.get('completed_quantity', 0)),
        'notes': body.get('notes', ''), 'recorded_by': user['name'], 'created_at': now()
    }
    await db.production_progress.insert_one(progress)
    all_prog = await db.production_progress.find({'work_order_id': body['work_order_id']}).to_list(None)
    total_completed = sum(p.get('completed_quantity', 0) for p in all_prog)
    new_status = 'Completed' if total_completed >= wo.get('quantity', 0) else 'In Progress'
    await db.work_orders.update_one({'id': body['work_order_id']}, {'$set': {'completed_quantity': total_completed, 'status': new_status, 'updated_at': now()}})
    await db.production_pos.update_one({'id': wo.get('po_id')}, {'$set': {'status': 'In Production', 'updated_at': now()}})
    return JSONResponse(serialize_doc(progress), status_code=201)

# ─── DISTRIBUSI KERJA ────────────────────────────────────────────────────────
@router.get("/distribusi-kerja")
async def distribusi_kerja(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    # Get all POs (or filtered by vendor)
    po_query = {}
    if sp.get('vendor_id'): po_query['vendor_id'] = sp['vendor_id']
    if sp.get('po_id'): po_query['id'] = sp['po_id']
    # FASE IA-1 (2026-07-26) — PEMISAHAN DATA per domain. Sebelum ini `po_query = {}`
    # sehingga Portal Produksi ikut menampilkan PO MAKLON (bug B di
    # docs/PROPOSAL_IA_PRODUKSI.md). Pola filter mengikuti production_pos.py:102-107.
    bt = sp.get('business_type')
    if bt == 'internal':
        po_query['business_type'] = 'internal'
    elif bt == 'maklon':
        po_query['business_type'] = {'$ne': 'internal'}
    pos = await db.production_pos.find(po_query, {'_id': 0}).sort('created_at', -1).to_list(None)
    if not pos: return {'hierarchy': [], 'flat': [], 'invalid_records': []}

    # ─── 10B-rem: batch every dependency in one shot ───
    po_ids = [po['id'] for po in pos]
    all_po_items = await db.po_items.find({'po_id': {'$in': po_ids}}).to_list(None)
    po_item_ids = [pi['id'] for pi in all_po_items]
    items_by_po = {}
    for pi in all_po_items:
        items_by_po.setdefault(pi.get('po_id'), []).append(pi)

    # qty_sent per po_item (single aggregation)
    sent_agg = await db.vendor_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_sent'}}},
    ]).to_list(None) if po_item_ids else []
    sent_by_poitem = {a['_id']: a['qty'] for a in sent_agg}

    # produced_qty per po_item
    prod_agg = await db.production_job_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$produced_qty'}}},
    ]).to_list(None) if po_item_ids else []
    prod_by_poitem = {a['_id']: a['qty'] for a in prod_agg}

    # shipped_to_buyer per po_item
    buyer_agg = await db.buyer_shipment_items.aggregate([
        {'$match': {'po_item_id': {'$in': po_item_ids}}},
        {'$group': {'_id': '$po_item_id', 'qty': {'$sum': '$qty_shipped'}}},
    ]).to_list(None) if po_item_ids else []
    buyer_by_poitem = {a['_id']: a['qty'] for a in buyer_agg}

    # received_qty: join shipment_items -> inspections -> inspection_items
    # Step 1 — pull all shipment items for these po_items
    all_ship_items = await db.vendor_shipment_items.find(
        {'po_item_id': {'$in': po_item_ids}}, {'_id': 0}
    ).to_list(None) if po_item_ids else []
    ship_ids = list({si.get('shipment_id') for si in all_ship_items if si.get('shipment_id')})
    # Step 2 — find inspections for those shipments in 1 query
    inspections = await db.vendor_material_inspections.find(
        {'shipment_id': {'$in': ship_ids}}, {'_id': 0, 'id': 1, 'shipment_id': 1}
    ).to_list(None) if ship_ids else []
    insp_id_by_ship = {i['shipment_id']: i['id'] for i in inspections}
    insp_ids = list(insp_id_by_ship.values())
    # Step 3 — fetch all inspection items keyed by shipment_item_id
    insp_items = await db.vendor_material_inspection_items.find(
        {'inspection_id': {'$in': insp_ids}}, {'_id': 0, 'shipment_item_id': 1, 'received_qty': 1}
    ).to_list(None) if insp_ids else []
    received_by_shipitem = {ii['shipment_item_id']: ii.get('received_qty', 0) for ii in insp_items if ii.get('shipment_item_id')}
    # Step 4 — sum received_qty per po_item via shipment_item linkage
    received_by_poitem = {}
    for si in all_ship_items:
        poi = si.get('po_item_id')
        if not poi: continue
        received_by_poitem[poi] = received_by_poitem.get(poi, 0) + received_by_shipitem.get(si.get('id'), 0)

    flat_rows = []
    for po in pos:
        for pi in items_by_po.get(po['id'], []):
            poi = pi['id']
            ordered_qty = pi.get('qty', 0)
            produced_qty = prod_by_poitem.get(poi, 0)
            progress_pct = round((produced_qty / ordered_qty * 100) if ordered_qty > 0 else 0)
            flat_rows.append({
                'id': poi, 'po_item_id': poi,
                'vendor_id': po.get('vendor_id'), 'vendor_name': po.get('vendor_name', ''),
                'po_id': po['id'], 'po_number': po.get('po_number', ''),
                'po_date': serialize_doc(po.get('created_at')),
                'customer_name': po.get('customer_name', ''),
                'serial_number': pi.get('serial_number', ''),
                'product_name': pi.get('product_name', ''), 'sku': pi.get('sku', ''),
                'size': pi.get('size', ''), 'color': pi.get('color', ''),
                'ordered_qty': ordered_qty,
                'shipment_qty': sent_by_poitem.get(poi, 0),
                'received_qty': received_by_poitem.get(poi, 0),
                'produced_qty': produced_qty,
                'shipped_to_buyer_qty': buyer_by_poitem.get(poi, 0),
                'progress_pct': progress_pct,
            })
    # Build hierarchy
    vendor_map = {}
    for row in flat_rows:
        vid = row.get('vendor_id')
        if vid not in vendor_map:
            vendor_map[vid] = {'vendor_id': vid, 'vendor_name': row.get('vendor_name'),
                               'total_ordered': 0, 'total_received': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0, 'pos': {}}
        vm = vendor_map[vid]
        vm['total_ordered'] += row.get('ordered_qty', 0)
        vm['total_received'] += row.get('received_qty', 0)
        vm['total_produced'] += row.get('produced_qty', 0)
        vm['total_shipped_to_buyer'] += row.get('shipped_to_buyer_qty', 0)
        po_key = row.get('po_id', 'unknown')
        if po_key not in vm['pos']:
            vm['pos'][po_key] = {'po_id': row.get('po_id'), 'po_number': row.get('po_number'),
                                  'customer_name': row.get('customer_name'),
                                  'total_ordered': 0, 'total_received': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0, 'serials': {}}
        pm = vm['pos'][po_key]
        pm['total_ordered'] += row.get('ordered_qty', 0)
        pm['total_received'] += row.get('received_qty', 0)
        pm['total_produced'] += row.get('produced_qty', 0)
        pm['total_shipped_to_buyer'] += row.get('shipped_to_buyer_qty', 0)
        sn = row.get('serial_number', '__no_serial__')
        if sn not in pm['serials']:
            pm['serials'][sn] = {'serial_number': row.get('serial_number', ''),
                                  'total_ordered': 0, 'total_received': 0, 'total_produced': 0, 'total_shipped_to_buyer': 0, 'skus': []}
        sm = pm['serials'][sn]
        sm['total_ordered'] += row.get('ordered_qty', 0)
        sm['total_received'] += row.get('received_qty', 0)
        sm['total_produced'] += row.get('produced_qty', 0)
        sm['total_shipped_to_buyer'] += row.get('shipped_to_buyer_qty', 0)
        sm['skus'].append(row)
    hierarchy = []
    for vm in vendor_map.values():
        vm['progress_pct'] = round((vm['total_produced'] / vm['total_ordered'] * 100) if vm['total_ordered'] > 0 else 0)
        pos_list = []
        for pm in vm['pos'].values():
            pm['progress_pct'] = round((pm['total_produced'] / pm['total_ordered'] * 100) if pm['total_ordered'] > 0 else 0)
            serials_list = []
            for sm in pm['serials'].values():
                sm['progress_pct'] = round((sm['total_produced'] / sm['total_ordered'] * 100) if sm['total_ordered'] > 0 else 0)
                serials_list.append(sm)
            pm['serials'] = serials_list
            pos_list.append(pm)
        vm['pos'] = pos_list
        hierarchy.append(vm)
    return {'hierarchy': hierarchy, 'flat': flat_rows, 'invalid_records': []}

# ─── WORK ORDERS ─────────────────────────────────────────────────────────────
@router.get("/work-orders")
async def get_work_orders(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    sp = request.query_params
    query = {}
    if sp.get('po_id'): query['po_id'] = sp['po_id']
    if sp.get('garment_id'): query['garment_id'] = sp['garment_id']
    if sp.get('status'): query['status'] = sp['status']
    if is_vendor(user): query['garment_id'] = vendor_identity(user)
    search = sp.get('search')
    if search:
        query['$or'] = [
            {'distribution_code': {'$regex': search, '$options': 'i'}},
            {'po_number': {'$regex': search, '$options': 'i'}},
            {'garment_name': {'$regex': search, '$options': 'i'}},
        ]
    # Pagination (Phase 10A)
    page, per_page, skip, wants = _paginate_params(sp)
    sort = _sort_params(sp, 'created_at', 'desc',
                        allowed={'created_at', 'distribution_code', 'po_number',
                                 'garment_name', 'status'})
    total = await db.work_orders.count_documents(query) if wants else None
    limit = per_page if wants else LEGACY_DEFAULT_CAP
    docs = await db.work_orders.find(query, {'_id': 0}).sort(sort).skip(skip if wants else 0).limit(limit).to_list(limit)
    if wants:
        return _paginated_envelope(serialize_doc(docs), total, page, per_page)
    return serialize_doc(docs)

@router.post("/work-orders")
async def create_work_order(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    po = await db.production_pos.find_one({'id': body.get('po_id')})
    if not po: raise HTTPException(404, 'PO not found')
    garment = await db.garments.find_one({'id': body.get('garment_id')})
    if not garment: raise HTTPException(404, 'Garment not found')
    wo = {
        'id': new_id(), 'distribution_code': f"WO-{po.get('po_number')}-{garment.get('garment_code')}",
        'po_id': body['po_id'], 'po_number': po.get('po_number'),
        'customer_name': po.get('customer_name'),
        'garment_id': body['garment_id'], 'garment_name': garment.get('garment_name'),
        'garment_code': garment.get('garment_code'),
        'quantity': int(body.get('quantity', 0)), 'completed_quantity': 0,
        'status': 'Waiting', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now()
    }
    await db.work_orders.insert_one(wo)
    await db.production_pos.update_one({'id': body['po_id']}, {'$set': {'status': 'Distributed', 'updated_at': now()}})
    return JSONResponse(serialize_doc(wo), status_code=201)

@router.delete("/work-orders/{woid}")
async def delete_work_order(woid: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if (user.get('role') or '').lower() != 'superadmin': raise HTTPException(403, 'Forbidden')
    db = get_db()
    doc = await db.work_orders.find_one({'id': woid})
    if not doc: raise HTTPException(404, 'Not found')
    await db.production_progress.delete_many({'work_order_id': woid})
    await db.work_orders.delete_one({'id': woid})
    return {'success': True}

# ─── RECALCULATE JOBS ────────────────────────────────────────────────────────
@router.post("/recalculate-jobs")
async def recalculate_jobs(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, PROD_ADMIN_ROLES): raise HTTPException(403, 'Forbidden')
    db = get_db()
    fixed = 0
    # First: backfill po_item_id on child shipment items that are missing it
    orphan_items = await db.vendor_shipment_items.find({'$or': [{'po_item_id': None}, {'po_item_id': ''}, {'po_item_id': {'$exists': False}}]}).to_list(None)
    for oi in orphan_items:
        ship = await db.vendor_shipments.find_one({'id': oi.get('shipment_id')})
        if not ship or not ship.get('parent_shipment_id'):
            continue
        # Find matching item in parent shipment by sku+size+color
        parent_items = await db.vendor_shipment_items.find({'shipment_id': ship['parent_shipment_id']}).to_list(None)
        for pi in parent_items:
            if pi.get('sku') == oi.get('sku') and pi.get('size', '') == oi.get('size', '') and pi.get('color', '') == oi.get('color', ''):
                if pi.get('po_item_id'):
                    await db.vendor_shipment_items.update_one({'id': oi['id']}, {'$set': {
                        'po_item_id': pi['po_item_id'], 'po_id': pi.get('po_id', ''),
                        'po_number': pi.get('po_number', ''), 'serial_number': pi.get('serial_number', ''),
                    }})
                    break
        # If still no match, try grandparent
        if not pi.get('po_item_id'):
            gp_ship = await db.vendor_shipments.find_one({'id': ship['parent_shipment_id']})
            if gp_ship and gp_ship.get('parent_shipment_id'):
                gp_items = await db.vendor_shipment_items.find({'shipment_id': gp_ship['parent_shipment_id']}).to_list(None)
                for gpi in gp_items:
                    if gpi.get('sku') == oi.get('sku') and gpi.get('size', '') == oi.get('size', '') and gpi.get('color', '') == oi.get('color', ''):
                        if gpi.get('po_item_id'):
                            await db.vendor_shipment_items.update_one({'id': oi['id']}, {'$set': {
                                'po_item_id': gpi['po_item_id'], 'po_id': gpi.get('po_id', ''),
                                'po_number': gpi.get('po_number', ''), 'serial_number': gpi.get('serial_number', ''),
                            }})
                            break
    # Now recalculate job items
    all_jobs = await db.production_jobs.find({}).to_list(None)
    for job in all_jobs:
        job_items = await db.production_job_items.find({'job_id': job['id']}).to_list(None)
        for ji in job_items:
            po_item_id = ji.get('po_item_id')
            if not po_item_id:
                continue
            # Aggregate received qty across ALL shipments (parent + children) for this po_item
            all_ship_items = await db.vendor_shipment_items.find({'po_item_id': po_item_id}).to_list(None)
            total_received = 0
            total_defect = 0
            for si in all_ship_items:
                insp = await db.vendor_material_inspections.find_one({'shipment_id': si.get('shipment_id')})
                if insp:
                    insp_item = await db.vendor_material_inspection_items.find_one({
                        'inspection_id': insp['id'], 'shipment_item_id': si['id']})
                    if insp_item:
                        total_received += insp_item.get('received_qty', 0)
                        total_defect += insp_item.get('defect_qty', 0)
            new_avail = max(0, total_received - total_defect)
            sn = ji.get('serial_number', '')
            if not sn and po_item_id:
                poi = await db.po_items.find_one({'id': po_item_id})
                sn = (poi or {}).get('serial_number', '')
            await db.production_job_items.update_one({'id': ji['id']}, {'$set': {
                'available_qty': new_avail, 'serial_number': sn,
                'total_received_qty': total_received, 'updated_at': now()
            }})
            fixed += 1
    return {'success': True, 'items_updated': fixed, 'jobs_processed': len(all_jobs), 'orphans_fixed': len(orphan_items)}
