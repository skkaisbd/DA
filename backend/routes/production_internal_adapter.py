"""Fase 3 — Adapter Produksi Internal (same base SOMMERVILLE + adapters E10).

Keputusan terkunci yang diimplementasikan di sini:
  D3    : PO internal merujuk rahaza_models + rahaza_sizes (FK wajib per item).
  ACC-1 : po_accessories auto-explode dari BOM aktif (rahaza_boms) per model+size.
  GDG-2 : Material Issue DRAFT tergenerate dari job → gudang tinggal submit/approve
          lewat workflow rahaza_inventory existing (stok SSOT rahaza_material_stock).
  HR-1  : progress optional operator_id+process_id → mirror rahaza_wip_events
          bentuk payroll-pcs (event_type='complete', qty_done, rate_per_pcs)
          sehingga payroll existing tetap berjalan tanpa perubahan.
  FIN-1/E10 : HPP snapshot ter-anchor job_id (material dari MI job, labor dari
          wip mirror job, overhead AD-2 = rate × Σproduced). AD-3: WIP→FG saat
          job Completed. COGS saat fulfillment (dispatch buyer shipment) —
          semua posting via rahaza_posting existing.
  MKT-1=B : onward CTA rahaza_orders → PO internal (POST /production-pos/from-order/{id}).

Job internal dibuat langsung dari PO (tanpa vendor_shipment/inspeksi — jalur itu
khusus maklon/CMT). Kapasitas produksi internal digate oleh MI status 'issued'.
"""
import logging
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from database import get_db
from auth import require_auth, check_role, log_activity, serialize_doc
from core.helpers import new_id, now
from routes.production_rbac import PROD_ADMIN_ROLES, deny_klien
from routes.rahaza_bom import get_bom_materials, _is_kglike
from core import bom_uom  # 2026-08-02: konversi satuan baris BOM → satuan dasar
from core import material_fields  # FASE 6.6-B: SSOT nama field + alias legacy yarn_*

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["production-internal-adapter"])

MI_DRAFT_ROLES = ['admin', 'admin_gudang', 'admin_produksi', 'supervisor_produksi']
HPP_ROLES = ['admin', 'accounting', 'admin_produksi']
FROM_ORDER_ROLES = ['admin', 'marketing', 'admin_marketing', 'admin_produksi']


# ═══════════════════════════════ D3: validasi master ══════════════════════════

async def validate_internal_item(db, raw: dict):
    """PO internal: setiap item WAJIB model_id (rahaza_models) + size_id (rahaza_sizes).
    Return (model, size) atau raise 400."""
    model_id = raw.get('model_id')
    size_id = raw.get('size_id')
    label = raw.get('sku') or raw.get('product_name') or model_id or '?'
    if not model_id:
        raise HTTPException(400, f"PO internal: item '{label}' wajib model_id (rujuk rahaza_models — D3)")
    model = await db.rahaza_models.find_one({'id': model_id, 'active': {'$ne': False}}, {'_id': 0})
    if not model:
        raise HTTPException(400, f"PO internal: model_id '{model_id}' tidak valid (rahaza_models)")
    if not size_id:
        raise HTTPException(400, f"PO internal: item '{label}' wajib size_id (rujuk rahaza_sizes)")
    size = await db.rahaza_sizes.find_one({'id': size_id, 'active': {'$ne': False}}, {'_id': 0})
    if not size:
        raise HTTPException(400, f"PO internal: size_id '{size_id}' tidak valid (rahaza_sizes)")
    return model, size


async def _active_bom(db, model_id, size_id, color=None):
    """Fase 4: color-aware BOM resolution. Prioritas: BOM spesifik-warna → BOM umum
    (color kosong) → BOM apa pun utk model+size (last resort)."""
    base = {'model_id': model_id, 'size_id': size_id, 'is_active': True, 'active': {'$ne': False}}
    color = (color or '').strip()
    if color:
        specific = await db.rahaza_boms.find_one({**base, 'color': color}, {'_id': 0})
        if specific:
            return specific
    general = await db.rahaza_boms.find_one(
        {**base, '$or': [{'color': ''}, {'color': {'$exists': False}}, {'color': None}]}, {'_id': 0})
    if general:
        return general
    return await db.rahaza_boms.find_one(base, {'_id': 0})


# ═══════════════════════════════ ACC-1: BOM explode ══════════════════════════

async def explode_po_accessories_from_bom(db, po_id: str) -> dict:
    """Regenerate baris po_accessories bersumber BOM (source='bom_auto').
    Baris manual (tanpa source='bom_auto') tidak disentuh. Idempoten.

    ACC-1 (dilengkapi 2026-07-25): baris hasil explode sekarang MEMBAWA
    `accessory_id` = `material_id` dari baris BOM. Sebelumnya field itu selalu
    `None`, sehingga kebutuhan aksesoris tidak bisa dihubungkan ke stok kanonik
    (`rahaza_material_stock`) — rantai BOM → kebutuhan → issue terputus dan qty
    kebutuhan hanya jadi teks. Agregasi juga dikunci per `material_id` bila ada
    (fallback code+nama) supaya dua baris BOM yang menunjuk material sama tidak
    terpecah gara-gara beda ejaan nama.
    """
    po_items = await db.po_items.find({'po_id': po_id}, {'_id': 0}).to_list(None)
    agg = {}          # key → {'qty', 'material_id', 'code', 'name', 'unit'}
    warnings = []
    unlinked_names = []
    for it in po_items:
        if not it.get('model_id') or not it.get('size_id'):
            continue
        bom = await _active_bom(db, it['model_id'], it['size_id'], it.get('color'))
        if not bom:
            warnings.append(f"BOM aktif tidak ditemukan utk model {it.get('sku') or it['model_id']} size {it.get('size','')}")
            continue
        qty_pcs = int(it.get('qty', 0) or 0)
        # 2026-08-02 · SATUAN: pakai qty SATUAN DASAR (mis. baris "1 lusin" → 12 pcs),
        # karena `po_accessories.qty_needed` dibandingkan dengan stok satuan dasar.
        bom_mats, uom_warn = await bom_uom.ensure_uom(db, bom)
        for w in uom_warn:
            if w not in warnings:
                warnings.append(w)
        for m in bom_mats:
            # Kain/benang (kg-like) → Material Issue gudang, BUKAN po_accessories.
            if _is_kglike({**m, 'unit': bom_uom.base_unit_of(m)}):
                continue
            mid = m.get('material_id') or None
            code = (m.get('code') or '').upper()
            name = m.get('name') or ''
            unit = bom_uom.base_unit_of(m)
            key = ('id', mid) if mid else ('code', code, name, unit)
            slot = agg.setdefault(key, {'qty': 0.0, 'material_id': mid, 'code': code,
                                        'name': name, 'unit': unit,
                                        'unit_input': m.get('unit'),
                                        'uom_status': m.get('uom_status')})
            slot['qty'] += bom_uom.qty_base_of(m) * qty_pcs
            # lengkapi metadata bila baris pertama kebetulan minim data
            slot['code'] = slot['code'] or code
            slot['name'] = slot['name'] or name
            if not mid and name and name not in unlinked_names:
                unlinked_names.append(name)

    await db.po_accessories.delete_many({'po_id': po_id, 'source': 'bom_auto'})
    rows = []
    for slot in agg.values():
        row = {
            'id': new_id(), 'po_id': po_id,
            'accessory_id': slot['material_id'],          # ACC-1: kopling ke master material
            'accessory_name': slot['name'], 'accessory_code': slot['code'],
            'qty_needed': round(slot['qty'], 3), 'unit': slot['unit'],
            'notes': 'Auto-explode dari BOM (ACC-1)', 'source': 'bom_auto',
            'unlinked': slot['material_id'] is None,
            'created_at': now(),
        }
        await db.po_accessories.insert_one(row)
        rows.append(row)
    if unlinked_names:
        warnings.append(
            "Baris BOM berikut belum tertaut ke master material sehingga stoknya tidak bisa dicek: "
            + ", ".join(unlinked_names[:10])
            + ". Perbaiki di modul BOM (pilih material dari master / tombol 'Perbaiki Otomatis').")
    return {'rows': len(rows), 'warnings': warnings,
            'linked_rows': sum(1 for r in rows if r['accessory_id']),
            'unlinked_rows': sum(1 for r in rows if not r['accessory_id'])}


# ═══════════════════════ Job internal (tanpa vendor shipment) ════════════════

async def create_internal_job(db, body: dict, user: dict):
    """Job produksi internal langsung dari PO internal (Confirmed/Distributed)."""
    po = await db.production_pos.find_one({'id': body['po_id']}, {'_id': 0})
    if not po:
        raise HTTPException(404, 'PO tidak ditemukan')
    if po.get('business_type') != 'internal':
        raise HTTPException(400, 'Job tanpa vendor shipment hanya untuk PO internal. PO maklon lewat alur shipment→inspeksi.')
    if po.get('status') not in ('Confirmed', 'Distributed'):
        raise HTTPException(400, f"PO internal berstatus '{po.get('status')}' — job hanya bisa dibuat dari Confirmed/Distributed")
    existing = await db.production_jobs.find_one({'po_id': po['id'], 'parent_job_id': None})
    if existing:
        raise HTTPException(400, f"Job untuk PO ini sudah ada: {existing.get('job_number')}")
    po_items = await db.po_items.find({'po_id': po['id']}, {'_id': 0}).to_list(None)
    if not po_items:
        raise HTTPException(400, 'PO tidak punya item')

    job_id = new_id()
    # FASE IA-C (2026-07-26): PO internal BOLEH dijahitkan ke mitra CMT (arahan owner:
    # "Produksi & Maklon flownya sama — dua-duanya dilempar ke CMT"). Dulu job internal
    # selalu dipatok `vendor_id=None / 'Produksi Internal'`, sehingga pekerjaan yang
    # sebenarnya dikerjakan mitra CMT hilang identitas pelaksananya: Tracking Produksi
    # menumpuk semuanya di satu baris "Produksi Internal" dan Portal Vendor mitra itu
    # tidak pernah melihat jobnya. Sekarang pelaksana diwarisi dari PO; PO tanpa vendor
    # (dikerjakan sendiri) tetap berperilaku persis seperti sebelumnya.
    job = {
        'id': job_id, 'job_number': f"JOB-{po.get('po_number', job_id[:8])}",
        'parent_job_id': None, 'parent_job_number': None,
        'vendor_id': po.get('vendor_id') or None,
        'vendor_name': po.get('vendor_name') or 'Produksi Internal',
        'po_id': po['id'], 'po_number': po.get('po_number', ''),
        'customer_name': po.get('customer_name', ''),
        'vendor_shipment_id': None, 'shipment_number': None,
        'shipment_type': 'INTERNAL', 'business_type': 'internal',
        'deadline': po.get('deadline'), 'delivery_deadline': po.get('delivery_deadline'),
        'status': 'In Progress', 'notes': body.get('notes', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now(),
    }
    await db.production_jobs.insert_one(job)
    inserted_items = []
    for pi in po_items:
        qty = int(pi.get('qty', 0) or 0)
        ji = {
            'id': new_id(), 'job_id': job_id, 'job_number': job['job_number'],
            'po_item_id': pi['id'], 'vendor_shipment_item_id': None,
            'product_name': pi.get('product_name', ''), 'sku': pi.get('sku', ''),
            'size': pi.get('size', ''), 'color': pi.get('color', ''),
            'serial_number': pi.get('serial_number', ''),
            'model_id': pi.get('model_id'), 'size_id': pi.get('size_id'),
            'rahaza_variant_id': pi.get('rahaza_variant_id'),
            # [DISPLAY FIX] carry buyer's article code + short color code forward.
            'buyer_ref_code': pi.get('buyer_ref_code', ''),
            'color_code': pi.get('color_code', ''),
            'ordered_qty': qty, 'shipment_qty': qty, 'available_qty': qty,
            'produced_qty': 0, 'created_at': now(),
        }
        await db.production_job_items.insert_one(ji)
        inserted_items.append(ji)

    await db.production_pos.update_one({'id': po['id']}, {'$set': {'status': 'In Production', 'updated_at': now()}})

    # GDG-2: draft MI otomatis — gudang tinggal set lokasi → submit → approve
    mi_result = None
    try:
        mi_result = await create_mi_draft_from_job(db, job, user)
    except HTTPException as e:
        mi_result = {'error': str(e.detail)}
    except Exception:
        logger.exception('Auto MI draft-from-job gagal utk job %s', job_id)
        mi_result = {'error': 'auto draft gagal (lihat log)'}

    await log_activity(user['id'], user['name'], 'Create', 'Production Job',
                       f"Created internal job {job['job_number']} dari PO {po.get('po_number')}")
    result = serialize_doc(job)
    result['items'] = serialize_doc(inserted_items)
    result['material_issue_draft'] = serialize_doc(mi_result) if isinstance(mi_result, dict) else mi_result
    return JSONResponse(result, status_code=201)


# ═══════════════════ GDG-2: Material Issue draft-from-job ════════════════════

async def create_mi_draft_from_job(db, job: dict, user: dict, default_loc=None):
    """Draft rahaza_material_issues dari BOM item-item job internal (anchor job_id)."""
    from routes.rahaza_inventory_shared import _uid, _gen_mi_number, _enrich_mi
    existing = await db.rahaza_material_issues.find_one(
        {'job_id': job['id'], 'status': {'$ne': 'rejected'}}, {'_id': 0})
    if existing:
        return existing

    job_items = await db.production_job_items.find({'job_id': job['id']}, {'_id': 0}).to_list(None)
    po_item_ids = [j['po_item_id'] for j in job_items if j.get('po_item_id')]
    po_items = {p['id']: p for p in await db.po_items.find({'id': {'$in': po_item_ids}}, {'_id': 0}).to_list(None)}

    # Agregasi kebutuhan material dari BOM per (model,size) × qty job item
    need = {}   # code → {name, unit, type, qty, composition}
    missing_bom = []
    total_pcs = 0
    for ji in job_items:
        pi = po_items.get(ji.get('po_item_id')) or {}
        model_id = ji.get('model_id') or pi.get('model_id')
        size_id = ji.get('size_id') or pi.get('size_id')
        qty = int(ji.get('shipment_qty') or ji.get('ordered_qty') or 0)
        total_pcs += qty
        if not model_id or not size_id:
            missing_bom.append(f"item {ji.get('sku','?')}: tanpa model_id/size_id")
            continue
        bom = await _active_bom(db, model_id, size_id)
        if not bom:
            missing_bom.append(f"item {ji.get('sku','?')}: BOM aktif tidak ditemukan")
            continue
        # 2026-08-02 · SATUAN: `qty_required` MI dipakai untuk memotong stok
        # (satuan dasar). Baris BOM dikonversi dulu supaya "gram" tidak dianggap "kg".
        bom_mats, uom_warn = await bom_uom.ensure_uom(db, bom)
        for w in uom_warn:
            if w not in missing_bom:
                missing_bom.append(w)
        for m in bom_mats:
            code = (m.get('code') or '').strip().upper()
            if not code:
                continue
            base_unit = bom_uom.base_unit_of(m)
            is_kg = _is_kglike({**m, 'unit': base_unit})
            mtype = 'yarn' if is_kg else 'accessory'
            unit = base_unit or ('kg' if is_kg else 'pcs')
            e = need.setdefault(code, {'name': m.get('name') or code, 'unit': unit,
                                       'type': mtype, 'composition': '', 'qty': 0.0,
                                       'unit_input': m.get('unit'),
                                       'uom_status': m.get('uom_status')})
            e['qty'] += bom_uom.qty_base_of(m) * qty

    if not need:
        raise HTTPException(400, f"Tidak ada BOM yang bisa dipakai untuk job ini. Detail: {missing_bom or 'BOM kosong'}")

    # Resolve / auto-create master material by code (pola sama dgn draft-from-wo)
    codes = list(need.keys())
    mats = {}
    async for m in db.rahaza_materials.find({'code': {'$in': codes}, 'active': True}, {'_id': 0}):
        mats[m['code']] = m
    items = []
    for code, e in need.items():
        mat = mats.get(code)
        if not mat:
            mat = {
                'id': _uid(), 'code': code, 'name': e['name'],
                'type': e['type'], 'unit': e['unit'],
                **material_fields.mirror('composition', e.get('composition') or ''),
                'color': '',
                'notes': 'Auto-created from Job BOM', 'min_stock': 0,
                'active': True, 'created_at': now(), 'updated_at': now(),
            }
            await db.rahaza_materials.insert_one(mat)
            mats[code] = mat
        items.append({
            'id': _uid(), 'material_id': mat['id'],
            'qty_required': round(e['qty'], 4),
            'qty_issued': 0, 'location_id': default_loc, 'notes': '',
        })

    doc = {
        'id': _uid(),
        'mi_number': await _gen_mi_number(db, sistem=True),  # lahir dari alur produksi
        'work_order_id': None,
        'wo_number_snapshot': '',
        'job_id': job['id'],
        'job_number_snapshot': job.get('job_number', ''),
        'production_po_id': job.get('po_id'),
        'po_number_snapshot': job.get('po_number', ''),
        'model_id': (job_items[0].get('model_id') if job_items else None),
        'size_id': (job_items[0].get('size_id') if job_items else None),
        'qty_wo_pcs': total_pcs,
        'items': items, 'status': 'draft',
        'notes': f"Draft otomatis dari Job {job.get('job_number', '')} (GDG-2)",
        'missing_codes': missing_bom,
        'created_by': user['id'], 'created_by_name': user.get('name', ''),
        'created_at': now(), 'updated_at': now(),
    }
    await db.rahaza_material_issues.insert_one(doc)
    await log_activity(user['id'], user.get('name', ''), 'draft_from_job', 'rahaza.mi', doc['mi_number'])
    await _enrich_mi(db, doc)
    return doc


@router.post("/rahaza/material-issues/draft-from-job")
async def draft_mi_from_job_endpoint(request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, MI_DRAFT_ROLES):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = await request.json()
    job_id = body.get('job_id')
    if not job_id:
        raise HTTPException(400, 'job_id wajib diisi')
    job = await db.production_jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(404, 'Job tidak ditemukan')
    if job.get('business_type') != 'internal':
        raise HTTPException(400, 'draft-from-job hanya untuk job internal (maklon: material dari klien via shipment)')
    doc = await create_mi_draft_from_job(db, job, user, default_loc=body.get('default_location_id') or None)
    return serialize_doc(doc)


# ═══════════════ HR-1: mirror progress → rahaza_wip_events ═══════════════════

async def resolve_operator_process(db, operator_id, process_id):
    """Validasi + resolve rate payroll pcs. Return ctx utk insert_wip_mirror."""
    emp = await db.rahaza_employees.find_one({'id': operator_id}, {'_id': 0})
    if not emp:
        raise HTTPException(400, f"operator_id '{operator_id}' tidak valid (rahaza_employees)")
    proc = await db.rahaza_processes.find_one({'id': process_id}, {'_id': 0})
    if not proc:
        raise HTTPException(400, f"process_id '{process_id}' tidak valid (rahaza_processes)")
    rate = 0.0
    profile = await db.rahaza_payroll_profiles.find_one(
        {'employee_id': operator_id, 'active': True}, {'_id': 0})
    if profile and profile.get('pay_scheme') == 'pcs':
        overrides = {r['process_id']: r['rate'] for r in (profile.get('pcs_process_rates') or [])}
        rate = float(overrides.get(process_id, profile.get('base_rate') or 0) or 0)
    return {'employee': emp, 'process': proc, 'rate_per_pcs': rate}


async def insert_wip_mirror(db, job, job_item, qty, ctx, user, progress_id=None):
    """Event bentuk payroll-pcs (event_type='complete', qty_done, rate_per_pcs)
    ter-anchor job_id (work_order_id=None — E10 REPURPOSE rahaza_wip_events)."""
    emp, proc = ctx['employee'], ctx['process']
    ev = {
        'id': new_id(),
        'event_date': now().date().isoformat(),
        'timestamp': now(),
        'line_id': None, 'line_assignment_id': None,
        'process_id': proc['id'], 'process_code': proc.get('code'),
        'location_id': None,
        'model_id': job_item.get('model_id'), 'size_id': job_item.get('size_id'),
        'work_order_id': None,
        'job_id': job['id'], 'job_item_id': job_item['id'],
        'production_po_id': job.get('po_id'),
        'operator_id': emp['id'], 'employee_id': emp['id'],
        'operator_name': emp.get('name', ''),
        'event_type': 'complete',
        'qty': int(qty), 'qty_done': int(qty),
        'rate_per_pcs': ctx['rate_per_pcs'],
        'source': 'production_progress', 'progress_id': progress_id,
        'notes': f"Mirror progress job {job.get('job_number', '')} (HR-1)",
        'created_by': user['id'], 'created_at': now(),
    }
    await db.rahaza_wip_events.insert_one(ev)
    return ev


# ═══════════════ FIN-1/E10: HPP per job + hook job Completed ═════════════════

async def compute_hpp_job(db, job_id: str) -> dict:
    """HPP aktual ter-anchor job_id:
    material = MI (job_id, issued) × unit_cost; labor = Σ qty_done × rate_per_pcs
    (wip mirror job); overhead AD-2 = overhead_rate × Σproduced."""
    job = await db.production_jobs.find_one({'id': job_id}, {'_id': 0})
    if not job:
        raise HTTPException(404, 'Job tidak ditemukan')
    settings = await db.rahaza_costing_settings.find_one({'id': 'GLOBAL'}, {'_id': 0}) or {}
    # FASE 12 / BUG-B: dulu membaca alias legacy `default_yarn_cost_per_kg` LANGSUNG.
    # Sejak FASE 11 alias itu tidak ditulis lagi ⇒ nilainya selalu None ⇒ fallback
    # harga bahan pada HPP job internal jatuh ke 0 **tanpa error** (salah hitung diam-diam).
    # Wajib lewat rantai baca kanonik → legacy di SSOT `material_fields`.
    default_yarn = float(material_fields.read_field(settings, 'default_material_cost_per_kg', 0) or 0)
    default_acc = float(settings.get('default_accessory_cost_per_unit') or 0)
    overhead_rate = float(settings.get('overhead_rate_per_pcs') or 0)
    labor_fallback = float(settings.get('labor_rate_fallback_per_pcs') or 0)

    job_items = await db.production_job_items.find({'job_id': job_id}, {'_id': 0}).to_list(None)
    qty_ordered = sum(int(j.get('ordered_qty') or 0) for j in job_items)
    qty_produced = sum(int(j.get('produced_qty') or 0) for j in job_items)

    # 1) Material dari MI job (status issued)
    mi_rows = await db.rahaza_material_issues.find({'job_id': job_id, 'status': 'issued'}, {'_id': 0}).to_list(500)
    material_cost = 0.0
    material_breakdown = []
    mat_ids = list({i.get('material_id') for mi in mi_rows for i in (mi.get('items') or []) if i.get('material_id')})
    mat_map = {}
    if mat_ids:
        async for d in db.rahaza_materials.find({'id': {'$in': mat_ids}}, {'_id': 0}):
            mat_map[d['id']] = d
    for mi in mi_rows:
        for item in (mi.get('items') or []):
            mat = mat_map.get(item.get('material_id')) or {}
            unit_cost = float(mat.get('unit_cost') or 0)
            if unit_cost <= 0:
                # FASE 12 / BUG-B2: dulu `mat.get('type') in ('yarn','fabric')` ⇒ material
                # `kain`/`benang`/`interlining` tanpa unit_cost memakai default AKSESORIS.
                unit_cost = default_yarn if material_fields.is_kglike_material(mat) else default_acc
            qty = float(item.get('qty_issued') or item.get('qty_required') or 0)
            amount = qty * unit_cost
            material_cost += amount
            material_breakdown.append({
                'material_id': item.get('material_id'), 'material_name': mat.get('name'),
                'type': mat.get('type'), 'qty': qty, 'unit': mat.get('unit'),
                'unit_cost': unit_cost, 'amount': round(amount),
            })

    # 2) Labor dari wip mirror job
    wip = await db.rahaza_wip_events.find({'job_id': job_id, 'event_type': 'complete'}, {'_id': 0}).to_list(1000)
    labor_cost = 0.0
    labor_breakdown = []
    for ev in wip:
        qty = int(ev.get('qty_done') or ev.get('qty') or 0)
        rate = float(ev.get('rate_per_pcs') or 0)
        if rate <= 0:
            rate = labor_fallback
        amount = qty * rate
        labor_cost += amount
        labor_breakdown.append({
            'operator_id': ev.get('operator_id'), 'operator_name': ev.get('operator_name'),
            'process_code': ev.get('process_code'), 'process_id': ev.get('process_id'),
            'qty': qty, 'rate': rate, 'amount': round(amount),
        })

    # 3) Overhead AD-2: rate × Σproduced
    overhead_cost = qty_produced * overhead_rate
    total_cost = material_cost + labor_cost + overhead_cost
    hpp_unit = total_cost / qty_produced if qty_produced > 0 else 0

    return {
        'anchor': 'job',
        'job_id': job_id, 'job_number': job.get('job_number'),
        'production_po_id': job.get('po_id'), 'po_number': job.get('po_number'),
        'business_type': job.get('business_type', 'internal'),
        'qty': qty_ordered, 'qty_completed': qty_produced,
        'material_cost': round(material_cost), 'labor_cost': round(labor_cost),
        'overhead_cost': round(overhead_cost), 'total_cost': round(total_cost),
        'total_hpp': round(total_cost), 'hpp_unit': round(hpp_unit),
        'material_breakdown': material_breakdown, 'labor_breakdown': labor_breakdown,
        'overhead_rate_per_pcs': overhead_rate,
        'computed_at': now().isoformat(),
    }


@router.get("/production-jobs/{job_id}/hpp")
async def hpp_for_job(job_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    db = get_db()
    return serialize_doc(await compute_hpp_job(db, job_id))


@router.post("/production-jobs/{job_id}/hpp-snapshot")
async def snapshot_hpp_job(job_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, HPP_ROLES):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    data = await upsert_hpp_snapshot_job(db, job_id, user)
    return serialize_doc(data)


async def upsert_hpp_snapshot_job(db, job_id: str, user: dict) -> dict:
    data = await compute_hpp_job(db, job_id)
    data['id'] = new_id()
    data['created_at'] = now()
    data['created_by'] = user['id']
    data['created_by_name'] = user.get('name', '')
    await db.rahaza_hpp_snapshots.update_one({'job_id': job_id}, {'$set': data}, upsert=True)
    return data


async def on_job_completed_internal(db, job: dict, user: dict) -> dict:
    """AD-3: job internal Completed → HPP snapshot (job) + posting WIP→FG."""
    snapshot = await upsert_hpp_snapshot_job(db, job['id'], user)
    from routes.rahaza_posting import post_wip_to_fg_on_job_complete
    posting = await post_wip_to_fg_on_job_complete(db, job, user)
    return {'hpp_snapshot_total': snapshot.get('total_cost'), 'wip_to_fg': posting}


# ═══════════════ MKT-1=B: onward CTA rahaza_orders → PO internal ═════════════

@router.post("/production-pos/from-order/{order_id}")
async def create_po_from_order(order_id: str, request: Request):
    user = await require_auth(request)
    deny_klien(user)
    if not check_role(user, FROM_ORDER_ROLES):
        raise HTTPException(403, 'Forbidden')
    db = get_db()
    body = {}
    try:
        body = await request.json()
    except Exception:
        body = {}

    order = await db.rahaza_orders.find_one({'id': order_id}, {'_id': 0})
    if not order:
        raise HTTPException(404, 'Order tidak ditemukan (rahaza_orders)')
    dup = await db.production_pos.find_one({'source_order_id': order_id}, {'_id': 0})
    if dup:
        raise HTTPException(400, f"Order ini sudah punya PO produksi: {dup.get('po_number')}")

    order_items = order.get('items') or []
    if not order_items:
        raise HTTPException(400, 'Order tidak punya item')

    po_number = body.get('po_number') or f"PO-INT-{order.get('order_number') or order_id[:8]}"
    if await db.production_pos.find_one({'po_number': po_number}):
        raise HTTPException(400, f"Nomor PO '{po_number}' sudah digunakan")

    # Validasi D3 semua item dulu (jangan tinggalkan PO yatim)
    validated = []
    for raw in order_items:
        model, size = await validate_internal_item(db, raw)
        validated.append((raw, model, size))

    initial_status = 'Confirmed' if body.get('status') == 'Confirmed' else 'Draft'
    po_id = new_id()
    po = {
        'id': po_id, 'po_number': po_number,
        'customer_name': order.get('customer_name_snapshot', '') or 'Produksi Internal',
        'buyer_id': order.get('customer_id'),
        'vendor_id': None, 'vendor_name': 'Produksi Internal',
        'po_date': now(), 'deadline': None, 'delivery_deadline': None,
        'status': initial_status,
        'notes': f"Dibuat dari Order Produksi {order.get('order_number', order_id)} (MKT-1)",
        'business_type': 'internal',
        'source_order_id': order_id,
        'source_order_number': order.get('order_number', ''),
        'created_by': user['name'], 'created_at': now(), 'updated_at': now(),
    }
    await db.production_pos.insert_one(po)
    inserted = []
    from utils.variant_ssot import resolve_variant, build_variant_sku
    for raw, model, size in validated:
        # SSOT (BUG-2): resolve canonical variant (warna+size) — prefer explicit
        # rahaza_variant_id, else by SKU. SKU kanonik = {MODEL}-{WARNA}-{SIZE}.
        _rv = await resolve_variant(
            db,
            variant_id=raw.get('rahaza_variant_id'),
            sku=raw.get('variant_sku') or raw.get('sku'),
        )
        color_name = (_rv or {}).get('color_name') or raw.get('color', '')
        color_code = (_rv or {}).get('color_code') or raw.get('color_code', '')
        sku = (_rv or {}).get('sku') or build_variant_sku(model.get('code', ''), color_code, size.get('code', ''))
        item = {
            'id': new_id(), 'po_id': po_id, 'po_number': po_number,
            'product_id': None, 'variant_id': None,
            'rahaza_variant_id': (_rv or {}).get('id'),
            'model_id': model['id'], 'size_id': size['id'],
            'product_name': model.get('name', ''),
            'sku': sku,
            'size': size.get('code', ''), 'color': color_name, 'color_code': color_code,
            'qty': int(raw.get('qty', 0) or 0), 'serial_number': raw.get('serial_number', ''),
            'selling_price_snapshot': float(raw.get('selling_price_snapshot', 0) or 0),
            'cmt_price_snapshot': 0.0,
            'created_at': now(),
        }
        await db.po_items.insert_one(item)
        inserted.append(item)

    explode = await explode_po_accessories_from_bom(db, po_id)
    await log_activity(user['id'], user['name'], 'Create', 'Production PO',
                       f"PO internal {po_number} dari order {order.get('order_number', order_id)}")
    result = serialize_doc(po)
    result['items'] = serialize_doc(inserted)
    result['accessories_explode'] = explode
    return JSONResponse(result, status_code=201)
