"""
CV. Dewi Aditya — Portal Maklon API Routes
Phase 3A + Phase 6: Client Management, Order Management,
Auto WO Generation, Stage-Gate Validation, WO Sync.

Collections:
- dewi_maklon_clients:   Master database klien maklon
- dewi_maklon_orders:    Order maklon dengan tracking workflow
                         **DEPRECATED (P1.B 2026-05-22)** — SSOT moved to dewi_maklon_pos
                         New endpoints at /api/dewi/maklon/pos/*. Order endpoints
                         here remain for backward compatibility but emit a
                         Deprecation header (`X-Deprecated-Endpoint: maklon-orders`).
                         All consumers (client portal, billing, samples,
                         management tools) now read from dewi_maklon_pos.
"""
from fastapi import APIRouter, HTTPException, Depends
from routes.production_rbac import deny_external_dep
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
from datetime import datetime, timezone
from database import get_db
from auth import require_auth, serialize_doc
from routes._maklon_adapter import legacy_orders_view as _lmo
from core import stock_service
from core import location_resolver
import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix='/api/dewi/maklon', tags=['Dewi-Maklon'], dependencies=[Depends(deny_external_dep)])
# ─── STAGE CONFIG ────────────────────────────────────────────────────────────
# Urutan stage produksi maklon
STAGES_ORDER = ['draft', 'confirmed', 'material_ready', 'cutting', 'sewing', 'qc', 'packing', 'completed', 'invoiced']

# Stage → auto progress % mapping
STAGE_PROGRESS = {
    'draft': 0,
    'confirmed': 5,
    'material_ready': 10,
    'cutting': 30,
    'sewing': 50,
    'qc': 70,
    'packing': 85,
    'completed': 100,
    'invoiced': 100,
}

# Stage → linked WO status sync
STAGE_TO_WO_STATUS = {
    'confirmed':      'draft',
    'material_ready': 'draft',
    'cutting':        'released',
    'sewing':         'in_production',
    'qc':             'in_production',
    'packing':        'in_production',
    'completed':      'completed',
}


def _uid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


async def _gen_wo_number(db) -> str:
    # SESI #27 — FUNGSI MATI, sengaja tidak dihapus isinya begitu saja:
    # engine `rahaza_work_orders` sudah DIARSIPKAN (FASE 4/E10 — lihat
    # `dewi_maklon_pos.py`: "TIDAK insert WO lagi"), jadi tidak ada satu pun
    # pemanggil fungsi ini. Ia membuat audit penomoran melihat "seri nomor WO"
    # yang tidak pernah lahir — karena itu isinya diganti galat yang jelas
    # daripada memanggil generator dan menghidupkan seri hantu.
    raise RuntimeError(
        "Penomoran WO (rahaza_work_orders) sudah diarsipkan sejak FASE 4/E10 — "
        "tidak ada jalur yang boleh membuat WO baru. Kalau WO dihidupkan kembali, "
        "daftarkan dulu jenis dokumennya di data/doc_number_registry.py.")


# ══════════════════════════════════════════════════════════════════════════════
# PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════════════════

class MaklonClient(BaseModel):
    id: Optional[str] = None
    code: str = Field(..., description="Kode unik klien, e.g. CLT001")
    name: str = Field(..., description="Nama perusahaan/brand klien")
    pic_name: Optional[str] = None
    pic_phone: Optional[str] = None
    pic_email: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = "Sragen"
    contract_type: str = Field(default="per_order")
    standard_rate_per_pcs: float = Field(ge=0, default=0)
    payment_terms: str = Field(default="net_30")
    product_specialization: List[str] = Field(default_factory=list)
    quality_standard: str = Field(default="standard")
    status: str = Field(default="active")
    rating: float = Field(default=4.0, ge=0, le=5)
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    created_by: Optional[str] = None


class _DeprecatedMaklonOrderInputModel(BaseModel):
    """Placeholder — Phase C cleanup removed the legacy POST/PUT /orders endpoints.
    Order create/update now happens at /api/dewi/maklon/pos.
    """


class OrderStatusIn(BaseModel):
    status: Optional[str] = None
    progress_percentage: Optional[int] = Field(default=None, ge=0, le=100)
    # Stage qty input (delta, diisi saat transisi)
    stage_qty_update: Optional[Dict[str, int]] = None
    # Bypass stage gate validation (admin only)
    force: Optional[bool] = False

    @field_validator("stage_qty_update")
    @classmethod
    def _non_negative_stage_qty(cls, v):
        if v:
            for k, qty in v.items():
                if qty is not None and qty < 0:
                    raise ValueError(f"stage_qty_update['{k}'] tidak boleh negatif")
        return v


class StageQtyIn(BaseModel):
    stage: str  # cutting | sewing | qc | packing
    qty_in: Optional[int] = Field(default=None, ge=0)
    qty_out: Optional[int] = Field(default=None, ge=0)
    qty_pass: Optional[int] = Field(default=None, ge=0)
    qty_fail: Optional[int] = Field(default=None, ge=0)
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════════════════════

async def _sync_wo_status(db, order: dict, new_stage: str, user: dict):
    """FASE 4 (E10 DELETE): engine rahaza_work_orders diarsip — sync WO jadi no-op.
    Dipertahankan sebagai stub agar pemanggil transisi stage tidak berubah."""
    return


async def _validate_stage_gate(order: dict, new_stage: str, force: bool = False) -> Optional[str]:
    """
    Validasi apakah transisi ke new_stage diizinkan berdasarkan stage_qty.
    Returns: error message string jika ditolak, None jika OK.
    """
    if force:
        return None

    qty = int(order.get('qty_ordered', 0))
    stage_qty = order.get('stage_qty') or {}

    if new_stage == 'sewing':
        cut_out = int(stage_qty.get('cutting_output', 0))
        if cut_out <= 0:
            return f"Input qty cutting output terlebih dahulu sebelum pindah ke Sewing (saat ini: 0/{qty} pcs)"

    elif new_stage == 'qc':
        sew_out = int(stage_qty.get('sewing_output', 0))
        if sew_out <= 0:
            return f"Input qty sewing output terlebih dahulu sebelum pindah ke QC (saat ini: 0/{qty} pcs)"

    elif new_stage == 'packing':
        qc_pass = int(stage_qty.get('qc_pass', 0))
        if qc_pass <= 0:
            return f"Input qty QC pass terlebih dahulu sebelum pindah ke Packing (saat ini: 0/{qty} pcs)"

    elif new_stage == 'completed':
        pack_out = int(stage_qty.get('packing_output', 0))
        if pack_out <= 0:
            return f"Input qty packing output terlebih dahulu sebelum menyelesaikan order (saat ini: 0/{qty} pcs)"

    return None



# ──────────────────────────────────────────────────────────────────────────────
# Phase C cleanup (2026-05-23): Removed unused legacy helpers:
#   - _auto_generate_wos() — was only called by removed confirm_order endpoint
#   - _build_maklon_wo()   — was only called by _auto_generate_wos
# Auto-WO generation now happens at POST /api/dewi/maklon/pos/{po_id}/confirm
# in dewi_maklon_pos.py (multi-item PO model with native WO generation per item).
# ──────────────────────────────────────────────────────────────────────────────


# ══════════════════════════════════════════════════════════════════════════════
# CLIENT MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/clients')
async def list_clients(status: Optional[str] = None, user: dict = Depends(require_auth)):
    db = get_db()
    query = {}
    if status:
        query['status'] = status
    clients = await db.dewi_maklon_clients.find(query).sort('name', 1).to_list(length=200)
    for c in clients:
        c['_id'] = str(c['_id'])
    return clients


@router.get('/clients/{client_id}')
async def get_client(client_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    client = await db.dewi_maklon_clients.find_one({'id': client_id}, {'_id': 0})
    if not client:
        raise HTTPException(404, 'Client tidak ditemukan')
    return client


@router.post('/clients')
async def create_client(payload: MaklonClient, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_maklon_clients.find_one({'code': payload.code})
    if existing:
        raise HTTPException(400, f'Kode klien {payload.code} sudah digunakan')
    now = _now()
    doc = payload.dict()
    doc['id'] = _uid()
    doc['created_at'] = now
    doc['updated_at'] = now
    doc['created_by'] = user.get('name', 'System')
    await db.dewi_maklon_clients.insert_one(doc)
    return {'message': 'Klien maklon berhasil dibuat', 'id': doc['id']}


@router.put('/clients/{client_id}')
async def update_client(client_id: str, payload: MaklonClient, user: dict = Depends(require_auth)):
    db = get_db()
    existing = await db.dewi_maklon_clients.find_one({'id': client_id})
    if not existing:
        raise HTTPException(404, 'Client tidak ditemukan')
    if payload.code != existing.get('code'):
        conflict = await db.dewi_maklon_clients.find_one({'code': payload.code, 'id': {'$ne': client_id}})
        if conflict:
            raise HTTPException(400, f'Kode {payload.code} sudah digunakan')
    update_data = payload.dict(exclude_unset=True)
    update_data['updated_at'] = _now()
    await db.dewi_maklon_clients.update_one({'id': client_id}, {'$set': update_data})
    return {'message': 'Client berhasil diperbarui'}


@router.delete('/clients/{client_id}')
async def delete_client(client_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    result = await db.dewi_maklon_clients.update_one(
        {'id': client_id},
        {'$set': {'status': 'inactive', 'updated_at': _now()}}
    )
    if result.matched_count == 0:
        raise HTTPException(404, 'Client tidak ditemukan')
    return {'message': 'Client dinonaktifkan'}


@router.put('/clients/{client_id}/toggle')
async def toggle_client_status(client_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    client = await db.dewi_maklon_clients.find_one({'id': client_id})
    if not client:
        raise HTTPException(404, 'Client tidak ditemukan')
    new_status = 'inactive' if client.get('status') == 'active' else 'active'
    await db.dewi_maklon_clients.update_one(
        {'id': client_id},
        {'$set': {'status': new_status, 'updated_at': _now()}}
    )
    return {'message': f'Status client diubah menjadi {new_status}'}


# ══════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# ORDER MANAGEMENT (LEGACY)
# ══════════════════════════════════════════════════════════════════════════════
# Phase C cleanup (2026-05-23): The following endpoints have been DELETED:
#   - GET    /orders                          → use GET /api/dewi/maklon/pos
#   - GET    /orders/{id}                     → use GET /api/dewi/maklon/pos/{po_id}
#   - POST   /orders                          → use POST /api/dewi/maklon/pos
#   - PUT    /orders/{id}                     → use PUT /api/dewi/maklon/pos/{po_id}
#   - PUT    /orders/{id}/confirm             → use POST /api/dewi/maklon/pos/{po_id}/confirm
#   - DELETE /orders/{id}                     → use POST /api/dewi/maklon/pos/{po_id}/cancel
#
# RETAINED for stage_qty workflow + material-issues (no PO equivalent):
#   - PUT  /orders/{id}/status                (stage gate validation + WO sync)
#   - PUT  /orders/{id}/stage-qty             (per-stage qty input)
#   - GET  /orders/{id}/production-detail     (stage + WO aggregation)
#   - POST /orders/{id}/material-issues       (issue material from rahaza_material_stock)
#   - GET  /orders/{id}/material-issues       (list material issues for order)
#   - DELETE /orders/{id}/material-issues/{issue_id}  (cancel issuance)


@router.put('/orders/{order_id}/status', deprecated=True)
async def update_order_status(
    order_id: str,
    payload: OrderStatusIn,
    user: dict = Depends(require_auth)
):
    """Update status + progress order maklon. Includes stage gate validation."""
    db = get_db()
    order = await _lmo(db).find_one({'id': order_id})
    if not order:
        raise HTTPException(404, 'Order tidak ditemukan')

    new_status = payload.status
    progress = payload.progress_percentage
    force = bool(payload.force)

    # ── Stage Gate Validation ─────────────────────────────────────────────
    if new_status:
        gate_error = await _validate_stage_gate(order, new_status, force=force)
        if gate_error:
            raise HTTPException(422, gate_error)

    update_data = {'updated_at': _now()}

    if new_status:
        update_data['status'] = new_status
        # Auto-set progress jika tidak dioverride
        if progress is None:
            progress = STAGE_PROGRESS.get(new_status, order.get('progress_percentage', 0))
        update_data['progress_percentage'] = progress
    elif progress is not None:
        update_data['progress_percentage'] = max(0, min(100, progress))

    # ── Stage qty delta update ────────────────────────────────────────────
    if payload.stage_qty_update:
        existing_sq = order.get('stage_qty') or {}
        existing_sq.update(payload.stage_qty_update)
        update_data['stage_qty'] = existing_sq

    # Auto-set completion date
    if new_status == 'completed' and not order.get('completion_date'):
        update_data['completion_date'] = _now().isoformat()[:10]

    await _lmo(db).update_one({'id': order_id}, {'$set': update_data})

    # ── Sync linked WOs ───────────────────────────────────────────────────
    if new_status:
        updated_order = await _lmo(db).find_one({'id': order_id})
        if updated_order:
            await _sync_wo_status(db, updated_order, new_status, user)

        # ── GAP #5: Notify client on stage change ─────────────────────────
        try:
            from routes.dewi_notifications import queue_for_client as _qfc
            cfg = await db.dewi_provider_config.find_one({'_type': 'main'}) or {}
            if cfg.get('notify_on_stage_change', True):
                client_id = order.get('client_id')
                if client_id:
                    _label_map = {
                        'confirmed': 'Dikonfirmasi', 'material_ready': 'Material Siap',
                        'cutting': 'Proses Cutting', 'sewing': 'Proses Jahit (Sewing)',
                        'qc': 'Proses Quality Control', 'packing': 'Proses Packing',
                        'completed': 'Selesai & Siap Kirim',
                    }
                    label = _label_map.get(new_status, new_status)
                    body = (
                        f"Halo {order.get('client_name', 'Klien')},\n\n"
                        f"Update pesanan Anda:\n"
                        f"Order   : {order.get('order_code')}\n"
                        f"Produk  : {order.get('product_name')}\n"
                        f"Status  : {label}\n"
                        f"Progress: {STAGE_PROGRESS.get(new_status, 0)}%\n\n"
                        f"Terima kasih telah mempercayai layanan kami.\n-- CV. Dewi Aditya"
                    )
                    await _qfc(
                        db, client_id=client_id, body=body,
                        subject=f"[Update Pesanan] {order.get('order_code')} \u2192 {label}",
                        event_type='stage_change', source_ref=order_id,
                        meta={'order_code': order.get('order_code'), 'new_stage': new_status},
                    )
        except Exception as e:
            logger.warning(f"[notify] stage_change failed: {e}")

    return {'message': 'Status order diperbarui', 'status': new_status, 'progress_percentage': progress}


@router.put('/orders/{order_id}/stage-qty', deprecated=True)
async def update_stage_qty(
    order_id: str,
    payload: StageQtyIn,
    user: dict = Depends(require_auth)
):
    """Input / update qty per tahap produksi (cutting/sewing/qc/packing)."""
    db = get_db()
    order = await _lmo(db).find_one({'id': order_id})
    if not order:
        raise HTTPException(404, 'Order tidak ditemukan')

    if order.get('status') in ('draft', 'cancelled', 'invoiced'):
        raise HTTPException(400, f"Status '{order.get('status')}' tidak bisa diinput qty stage")

    stage = payload.stage
    valid_stages = ['cutting', 'sewing', 'qc', 'packing']
    if stage not in valid_stages:
        raise HTTPException(400, f"Stage harus salah satu dari: {valid_stages}")

    stage_qty = order.get('stage_qty') or {}

    if stage == 'cutting':
        if payload.qty_in is not None:
            stage_qty['cutting_input'] = max(0, payload.qty_in)
        if payload.qty_out is not None:
            stage_qty['cutting_output'] = max(0, payload.qty_out)
    elif stage == 'sewing':
        if payload.qty_out is not None:
            stage_qty['sewing_output'] = max(0, payload.qty_out)
    elif stage == 'qc':
        if payload.qty_pass is not None:
            stage_qty['qc_pass'] = max(0, payload.qty_pass)
        if payload.qty_fail is not None:
            stage_qty['qc_fail'] = max(0, payload.qty_fail)
    elif stage == 'packing':
        if payload.qty_out is not None:
            stage_qty['packing_output'] = max(0, payload.qty_out)

    # Auto-calculate progress from stage qty
    progress = _calc_progress_from_stage_qty(order, stage_qty)

    await _lmo(db).update_one(
        {'id': order_id},
        {'$set': {
            'stage_qty': stage_qty,
            'progress_percentage': progress,
            'updated_at': _now(),
        }}
    )
    return {'message': f'Stage qty {stage} diperbarui', 'stage_qty': stage_qty, 'progress_percentage': progress}


def _calc_progress_from_stage_qty(order: dict, stage_qty: dict) -> int:
    """Hitung progress % dari stage qty aktual."""
    qty_ordered = int(order.get('qty_ordered', 0))
    if qty_ordered <= 0:
        return 0
    packing_out = int(stage_qty.get('packing_output', 0))
    if packing_out >= qty_ordered:
        return 100
    qc_pass = int(stage_qty.get('qc_pass', 0))
    sewing_out = int(stage_qty.get('sewing_output', 0))
    cutting_out = int(stage_qty.get('cutting_output', 0))

    if packing_out > 0:
        return min(95, 85 + int((packing_out / qty_ordered) * 15))
    if qc_pass > 0:
        return min(84, 70 + int((qc_pass / qty_ordered) * 14))
    if sewing_out > 0:
        return min(69, 50 + int((sewing_out / qty_ordered) * 19))
    if cutting_out > 0:
        return min(49, 30 + int((cutting_out / qty_ordered) * 19))
    # Fallback ke status-based
    status = order.get('status', 'draft')
    return STAGE_PROGRESS.get(status, 0)


@router.get('/orders/{order_id}/production-detail', deprecated=True)
async def get_order_production_detail(order_id: str, user: dict = Depends(require_auth)):
    """Get detail produksi: order + linked WOs + stage qty summary."""
    db = get_db()
    order = await _lmo(db).find_one({'id': order_id})
    if not order:
        raise HTTPException(404, 'Order tidak ditemukan')
    # Legacy wrapper already projects to legacy shape without _id

    linked_wo_ids = order.get('linked_wo_ids') or []
    wos = []
    if linked_wo_ids:
        raw_wos = await db.rahaza_work_orders.find(
            {'id': {'$in': linked_wo_ids}}, {'_id': 0}
        ).to_list(500)
        # Enrich each WO with progress
        for wo in raw_wos:
            wo_id = wo['id']
            wo_qty = int(wo.get('qty', 0))
            # Count WIP events for final process
            procs = await db.rahaza_processes.find(
                {'active': True, 'is_rework': False}, {'_id': 0}
            ).sort('order_seq', 1).to_list(500)
            if procs:
                last_proc = procs[-1]
                pipe = [
                    {'$match': {'event_type': 'output', 'work_order_id': wo_id, 'process_id': last_proc['id']}},
                    {'$group': {'_id': None, 'total': {'$sum': '$qty'}}},
                ]
                res = await db.rahaza_wip_events.aggregate(pipe).to_list(1)
                completed_qty = res[0]['total'] if res else 0
            else:
                completed_qty = 0
            wo['completed_qty'] = completed_qty
            wo['progress_pct'] = round((completed_qty / wo_qty) * 100, 1) if wo_qty > 0 else 0
            wos.append(wo)

    return {
        'order': serialize_doc(order),
        'linked_wos': serialize_doc(wos),
        'stage_qty': order.get('stage_qty') or {},
        'sync_mode': order.get('sync_mode', 'manual'),
        'wo_count': len(wos),
    }


# ══════════════════════════════════════════════════════════════════════════════
# MATERIAL ISSUE — GAP #4
# ══════════════════════════════════════════════════════════════════════════════

class MaklonMaterialIssueIn(BaseModel):
    material_id: str
    location_id: str
    qty: float = Field(..., gt=0)
    unit: str = 'meter'
    notes: Optional[str] = None


@router.post('/orders/{order_id}/material-issues', deprecated=True)
async def create_material_issue(order_id: str, payload: MaklonMaterialIssueIn, user: dict = Depends(require_auth)):
    """
    Buat permintaan pengeluaran material untuk order maklon.
    Stok TIDAK langsung berkurang — dibuat PENDING OUTBOUND_RM di WMS,
    gudang harus melakukan Scan-Out sebelum stok benar-benar turun.
    """
    db = get_db()
    order = await _lmo(db).find_one({'id': order_id})
    if not order:
        raise HTTPException(404, 'Order tidak ditemukan')
    if order.get('status') in ('draft', 'cancelled', 'invoiced'):
        raise HTTPException(400, f"Status '{order.get('status')}' tidak bisa issue material")

    material = await db.rahaza_materials.find_one({'id': payload.material_id})
    if not material:
        raise HTTPException(404, 'Material tidak ditemukan')

    # Validasi stok saat ini (informasi, belum dikurangi).
    # BUG-INV-12 fix: agregasi stok kanonik lintas semua baris/skema (bukan 1 lokasi saja).
    current_stock = await stock_service.get_onhand(payload.material_id, db=db)
    if current_stock < payload.qty:
        raise HTTPException(400, f"Stok tidak cukup: tersedia {current_stock} {payload.unit}, diminta {payload.qty}")

    # FASE D: resolve nama lokasi lintas skema (wh_zones/wh_positions/wh_racks/
    # wh_buildings/rahaza_locations) via location_resolver — konsisten dgn SSOT
    # dropdown `/api/rahaza/storage-locations` yang dipakai frontend.
    _disp = await location_resolver.build_display_map(db, [payload.location_id])
    _d = _disp.get(payload.location_id) or {}
    loc_name = _d.get("name") or _d.get("code") or payload.location_id
    if not _d or _d.get("source") == "unknown":
        # Fallback lama (wh_racks bila belum ter-cover resolver)
        loc_doc = await db.wh_racks.find_one({'id': payload.location_id}, {'_id': 0})
        if loc_doc:
            loc_name = loc_doc.get('name', loc_doc.get('code', payload.location_id))

    # Buat record issue (UI menampilkan ini)
    issue_id = _uid()
    issue_ref = f"MI-{order.get('order_code','ORD')}-{int(datetime.now(timezone.utc).timestamp())}"

    # Delegate ke WMS: buat pending outbound_rm (stok belum turun)
    try:
        from routes.wms_receiving import helper_create_pending_outbound_rm
        pending = await helper_create_pending_outbound_rm(
            db,
            material_id=payload.material_id,
            material_code=material.get('code', ''),
            material_name=material.get('name', ''),
            qty=float(payload.qty),
            unit=payload.unit,
            source_type='material_issue',
            source_id=issue_id,
            source_ref=issue_ref,
            notes=payload.notes or f"Maklon Order {order.get('order_code')} — scan-out diperlukan",
            created_by=user.get('email', user.get('name', 'system')),
        )
        pending_ref = pending.get('ref_number')
    except Exception as e:
        raise HTTPException(500, f"Gagal buat pending outbound: {e}")

    issue_doc = {
        'id': issue_id, 'order_id': order_id, 'order_code': order.get('order_code', ''),
        'client_name': order.get('client_name', ''),
        'material_id': payload.material_id, 'material_code': material.get('code', ''),
        'material_name': material.get('name', ''), 'material_unit': material.get('unit', payload.unit),
        'location_id': payload.location_id, 'location_name': loc_name,
        'qty': payload.qty, 'unit': payload.unit,
        'stock_before': current_stock, 'stock_after': current_stock,   # belum turun
        'status': 'pending_scan_out',
        'wms_pending_id': pending.get('id'),
        'wms_ref_number': pending_ref,
        'issue_ref': issue_ref,
        'notes': payload.notes or '',
        'issued_by': user.get('name', ''), 'issued_at': _now(),
    }
    await db.dewi_maklon_material_issues.insert_one(issue_doc)
    return {
        'message': f'Pending outbound RM dibuat ({pending_ref}). Gudang harus Scan-Out sebelum stok berkurang.',
        'issue_id': issue_doc['id'],
        'wms_pending_id': pending.get('id'),
        'wms_ref_number': pending_ref,
        'material': material.get('name', ''), 'qty': payload.qty,
        'unit': payload.unit, 'stock_remaining': current_stock,   # masih penuh
        'status': 'pending_scan_out',
    }


@router.get('/orders/{order_id}/material-issues', deprecated=True)
async def list_material_issues(order_id: str, user: dict = Depends(require_auth)):
    db = get_db()
    issues = await db.dewi_maklon_material_issues.find(
        {'order_id': order_id}, {'_id': 0}
    ).sort('issued_at', -1).to_list(500)
    return issues


@router.delete('/orders/{order_id}/material-issues/{issue_id}', deprecated=True)
async def cancel_material_issue(order_id: str, issue_id: str, user: dict = Depends(require_auth)):
    """
    Batalkan permintaan issue material.
    - Jika masih pending_scan_out → batalkan pending WMS, stok tidak berubah (belum turun).
    - Jika sudah scanned (partial/confirmed) → harus dibatalkan lewat WMS (Scan-In balik), tidak bisa di sini.
    """
    db = get_db()
    issue = await db.dewi_maklon_material_issues.find_one({'id': issue_id, 'order_id': order_id})
    if not issue:
        raise HTTPException(404, 'Issue record tidak ditemukan')

    pending_id = issue.get('wms_pending_id')
    if pending_id:
        pending = await db.wh_pending_movements.find_one({'id': pending_id}, {'_id': 0})
        if pending and pending.get('status') in ('confirmed', 'partial'):
            raise HTTPException(400, f"Issue sudah di-scan-out (status {pending.get('status')}). Kembalikan via Scan-In terbalik di WMS.")
        if pending and pending.get('status') == 'pending':
            await db.wh_pending_movements.update_one(
                {'id': pending_id},
                {'$set': {'status': 'cancelled', 'cancelled_at': _now(), 'cancelled_by': user.get('email') or user.get('name', 'system')}}
            )
    await db.dewi_maklon_material_issues.delete_one({'id': issue_id})
    return {'message': f"Issue {issue['qty']} {issue['unit']} {issue['material_name']} dibatalkan. Pending WMS juga dibatalkan (stok tidak pernah turun)."}


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD SUMMARY
# ══════════════════════════════════════════════════════════════════════════════

@router.get('/summary')
async def get_summary(user: dict = Depends(require_auth)):
    db = get_db()
    total_clients = await db.dewi_maklon_clients.count_documents({})
    active_clients = await db.dewi_maklon_clients.count_documents({'status': 'active'})
    total_orders = await _lmo(db).count_documents({})
    active_orders = await _lmo(db).count_documents({
        'status': {'$nin': ['completed', 'cancelled', 'invoiced']}
    })
    completed_orders = await _lmo(db).count_documents({'status': 'completed'})
    draft_orders = await _lmo(db).count_documents({'status': 'draft'})
    confirmed_orders = await _lmo(db).count_documents({'status': 'confirmed'})
    in_production = await _lmo(db).count_documents({
        'status': {'$in': ['material_ready', 'cutting', 'sewing', 'qc', 'packing']}
    })
    pipeline = [
        {'$group': {'_id': None, 'total_revenue': {'$sum': '$total_value'}}}
    ]
    revenue_result = await _lmo(db).aggregate(pipeline).to_list(1)
    total_revenue = revenue_result[0]['total_revenue'] if revenue_result else 0
    return {
        'total_clients': total_clients,
        'active_clients': active_clients,
        'total_orders': total_orders,
        'active_orders': active_orders,
        'completed_orders': completed_orders,
        'draft_orders': draft_orders,
        'confirmed_orders': confirmed_orders,
        'in_production': in_production,
        'total_revenue': total_revenue,
    }
