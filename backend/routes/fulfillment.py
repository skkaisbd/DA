"""
CV. Dewi Aditya — Fulfillment Management (Phase 6)
Bridge between Marketing Orders and Inventory FG

Flow:
1. Marketing order status "packed" → auto masuk fulfillment queue (fulfillment_status = "pending_fulfillment")
2. Admin Inventory: Allocate FG stock (manual select dari rahaza_material_stock)
3. Picking: Mark order sedang diambil dari gudang
4. Packing: Konfirmasi sudah dikemas
5. Dispatch: Scan out FG (kurangi stock) + Post COGS → Finance GL

Collections:
- marketing_orders (extend dengan fulfillment_status, fulfillment_items[], shipment_ref, dispatched_at)
- rahaza_material_stock (source FG stock: ownership=cv_da, inventory_category=fg_internal)

Endpoints:
- GET    /api/fulfillment/queue                    — List orders pending fulfillment
- GET    /api/fulfillment/orders/{id}              — Order detail dengan fulfillment info
- GET    /api/fulfillment/inventory/available      — List FG available untuk allocate
- POST   /api/fulfillment/orders/{id}/allocate     — Allocate FG stock ke order (manual select)
- POST   /api/fulfillment/orders/{id}/pick         — Start picking
- POST   /api/fulfillment/orders/{id}/pack         — Confirm packing done
- POST   /api/fulfillment/orders/{id}/dispatch     — Dispatch + reduce stock + post COGS
- GET    /api/fulfillment/summary                  — Stats dashboard
"""
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
import uuid
import logging

from database import get_db
from core.stock_schema import inc_all_qty, read_available
from core import stock_service
from core import fulfillment_status as fstat
from auth import require_auth, serialize_doc, log_activity
from routes.rahaza_posting import post_cogs_shipment

logger = logging.getLogger(__name__)
router = APIRouter(prefix='/api/fulfillment', tags=['fulfillment'])

def _uid(): return str(uuid.uuid4())
def _now(): return datetime.now(timezone.utc)

# ── Pydantic Models ────────────────────────────────────────────────────────────

class FulfillmentItemIn(BaseModel):
    material_id: str = Field(..., description="Material ID dari rahaza_material_stock")
    sku_code: str = Field(default='', description="SKU code untuk reference")
    material_name: str = Field(default='', description="Nama material")
    qty_allocated: int = Field(..., ge=1, description="Qty yang dialokasikan")
    location_id: str = Field(default='', description="Location ID gudang")

class AllocateInventoryIn(BaseModel):
    items: List[FulfillmentItemIn] = Field(..., min_items=1, description="List FG items to allocate")

class DispatchIn(BaseModel):
    tracking_number: str = Field(default='', description="Nomor resi pengiriman")
    courier: str = Field(default='', description="Kurir pengiriman")
    notes: str = Field(default='', description="Catatan tambahan")

# ── Helpers ────────────────────────────────────────────────────────────────────

FULFILLMENT_STATUSES = list(fstat.FULFILLMENT_STATUSES)

async def _get_order(db, order_id: str):
    """Get marketing order by ID."""
    order = await db.marketing_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(404, f"Order {order_id} tidak ditemukan")
    return order

async def _check_fulfillment_status(order: dict, expected: List[str]):
    """Validasi status fulfillment \u2014 **lewat kosakata kanonik** (Sesi #20).

    Dulu perbandingannya mentah (`status not in expected`), jadi 559 pesanan hasil
    impor yang berstatus warisan ``'unallocated'`` DITOLAK saat dialokasikan
    walaupun artinya sama dengan ``'pending_fulfillment'``. Sekarang keduanya
    dibandingkan setelah dinormalkan oleh :mod:`core.fulfillment_status`.
    """
    raw = order.get("fulfillment_status", "")
    status = fstat.canon(raw)
    if status not in {fstat.canon(e) for e in expected}:
        raise HTTPException(400, f"Status fulfillment saat ini '{fstat.label(raw)}' "
                                 f"({raw}), harus salah satu dari: {expected}")

# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/summary")
async def fulfillment_summary(user: dict = Depends(require_auth)):
    """Ringkasan antrean gudang **+ kesiapan tautannya** (Sesi #20).

    Tambahan `blocked_unmapped` menjawab pertanyaan yang dulu tidak bisa dijawab
    layar mana pun: *\"kenapa daftar barang dari marketing kosong / tidak ada yang
    sama?\"* \u2014 karena barisnya belum menunjuk master gudang. Angkanya sekarang
    tampil, bukan disimpan di dalam skrip forensik.
    """
    db = get_db()

    pending = await db.marketing_orders.count_documents(
        fstat.queue_filter(fstat.PENDING))
    allocated = await db.marketing_orders.count_documents({"fulfillment_status": "allocated"})
    picking = await db.marketing_orders.count_documents({"fulfillment_status": "picking"})
    packed = await db.marketing_orders.count_documents({"fulfillment_status": "packed_ready"})
    dispatched_today = await db.marketing_orders.count_documents({
        "fulfillment_status": "dispatched",
        "dispatched_at": {"$gte": _now().date().isoformat()}
    })

    # Kesiapan tautan pada seluruh antrean (bukan hanya halaman yang tampil —
    # banner kesehatan yang hanya jujur untuk 1 halaman adalah kebohongan sopan).
    queue_total = ready = blocked = 0
    unmapped_skus = set()
    async for o in db.marketing_orders.find(fstat.queue_filter(),
                                            {"_id": 0, "items": 1, "fg_material_id": 1,
                                             "quantity": 1, "sku_id": 1}):
        queue_total += 1
        lk = fstat.order_linkage(o)
        if lk["ready"]:
            ready += 1
        else:
            blocked += 1
            unmapped_skus.update(lk["unmapped_skus"])

    return {
        "pending_fulfillment": pending,
        "allocated": allocated,
        "picking": picking,
        "packed_ready": packed,
        "dispatched_today": dispatched_today,
        # Sesi #20 — kesiapan antrean
        "queue_total": queue_total,
        "queue_ready": ready,
        "queue_blocked": blocked,
        "blocked_unmapped_skus": len(unmapped_skus),
        "blocked_hint": ("Buka 'Jembatan SKU' untuk menautkan SKU platform ke master gudang."
                         if blocked else ""),
    }


@router.get("/queue")
async def get_fulfillment_queue(
    status: Optional[str] = None,
    readiness: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    user: dict = Depends(require_auth)
):
    """Daftar pesanan yang masih jadi pekerjaan gudang.

    **Sesi #20 — dua perbaikan yang membuat daftar ini berhenti kosong:**

    1. Penyaring statusnya memakai :func:`core.fulfillment_status.queue_filter`
       yang MENGAKUI istilah warisan ``'unallocated'``. Impor pesanan menulis
       istilah itu sejak F1, sementara daftar ini hanya mencari
       ``'pending_fulfillment'`` \u21d2 **559 pesanan \"Perlu dikirim\" tidak pernah
       muncul**. Dua kamus untuk satu keadaan; yang membaca kalah.
    2. Tiap baris membawa `linkage` (`ready`/`unlinked`/`unmapped_skus`) supaya
       gudang tahu **mengapa** sebuah pesanan belum bisa dialokasikan, bukan
       sekadar melihat daftar yang tidak bisa diapa-apakan.

    `readiness=ready|blocked` menyaring berdasarkan kesiapan tautan itu.
    """
    db = get_db()

    query = fstat.queue_filter(status) if status else fstat.queue_filter()

    cursor = db.marketing_orders.find(query, {"_id": 0}).sort("created_at", 1)
    rows = []
    counted = 0
    ready_n = blocked_n = 0
    async for o in cursor:
        lk = fstat.order_linkage(o)
        if lk["ready"]:
            ready_n += 1
        else:
            blocked_n += 1
        if readiness == "ready" and not lk["ready"]:
            continue
        if readiness == "blocked" and lk["ready"]:
            continue
        counted += 1
        if counted <= skip or len(rows) >= max(1, int(limit or 50)):
            continue
        doc = serialize_doc(o)
        doc["linkage"] = lk
        doc["fulfillment_status_canonical"] = fstat.canon(o.get("fulfillment_status"))
        doc["fulfillment_status_label"] = fstat.label(o.get("fulfillment_status"))
        rows.append(doc)

    return {
        "orders": rows,
        "total": counted,
        "skip": skip,
        "limit": limit,
        "ready_count": ready_n,
        "blocked_count": blocked_n,
        "blocked_hint": ("Sebagian pesanan belum menunjuk master gudang \u2014 tautkan SKU-nya "
                         "di layar 'Jembatan SKU' agar bisa dialokasikan."
                         if blocked_n else ""),
    }


@router.get("/orders/{order_id}")
async def get_fulfillment_order_detail(order_id: str, user: dict = Depends(require_auth)):
    """Get order detail with fulfillment info."""
    db = get_db()
    order = await _get_order(db, order_id)
    return serialize_doc(order)


@router.get("/inventory/available")
async def get_available_inventory(
    search: Optional[str] = None,
    limit: int = 100,
    user: dict = Depends(require_auth)
):
    """
    List FG inventory available untuk allocate.
    Filter: ownership=cv_da, inventory_category=fg_internal, available_quantity > 0
    """
    db = get_db()
    
    query = {
        "ownership": "cv_da",
        "inventory_category": "fg_internal",
        "available_quantity": {"$gt": 0}
    }
    
    if search:
        query["$or"] = [
            {"material_id": {"$regex": search, "$options": "i"}},
            {"material_name": {"$regex": search, "$options": "i"}},
            {"material_code": {"$regex": search, "$options": "i"}}
        ]
    
    cursor = db.rahaza_material_stock.find(query, {"_id": 0}).sort("material_name", 1).limit(limit)
    items = [serialize_doc(i) async for i in cursor]
    
    return {
        "items": items,
        "total": len(items)
    }


@router.get("/orders/{order_id}/suggest-allocation")
async def suggest_allocation(order_id: str, user: dict = Depends(require_auth)):
    """**M9** — usulkan `material_id` OTOMATIS dari tautan order.

    Dulu `allocate` mewajibkan manusia memilih material dari
    `rahaza_material_stock` untuk SETIAP pesanan ("manual select"), padahal
    order-nya jelas menunjuk satu SKU. Tautan dibuat ulang dengan tangan tiap
    pesanan ⇒ salah pilih = stok salah turun. Sekarang server mengusulkan,
    manusia hanya mengonfirmasi.

    **K-8b (2026-08-10)** — order multi-produk mengusulkan SEMUA barisnya. Dulu
    hanya tautan tingkat-order (baris pertama) yang diusulkan, jadi produk ke-2
    dan seterusnya harus dicari manual — sumber salah-pilih yang sama, hanya
    berpindah tempat.
    """
    db = get_db()
    order = await _get_order(db, order_id)
    from core import catalog_stock as _cstock

    already_total = float(order.get('reserved_qty') or 0) if order.get('stock_reserved') else 0.0

    # ── kumpulkan (material_id, qty) dari baris order bila ada tautan per baris ─
    wants: list = []
    for ln in (order.get('items') or []):
        if isinstance(ln, dict) and ln.get('fg_material_id') and float(ln.get('qty') or 0) > 0:
            wants.append({
                'fg_material_id': ln['fg_material_id'],
                'qty': float(ln.get('qty') or 0),
                'already': float(ln.get('reserved_qty') or 0),
            })

    if not wants:
        # order 1 produk / order LAMA — pakai tautan tingkat-order
        fg_id = order.get('fg_material_id')
        if not fg_id:
            # order LAMA (tanpa tautan) — coba resolusi dari SKU teks, TANPA menebak
            res = await _cstock.resolve_link(db, {
                'variant_sku': order.get('variant_sku') or order.get('sku_id') or '',
                'variant_id': order.get('variant_id'),
            })
            fg_id = res.get('fg_material_id')
        if not fg_id:
            return {
                'ok': True, 'items': [], 'auto_resolved': False,
                'reason': (f"Order ini belum tertaut ke master (sku_id='{order.get('sku_id','')}'), "
                           'dan SKU-nya tidak dikenal. Pilih produk secara manual, atau perbaiki '
                           'tautan order.'),
            }
        wants = [{'fg_material_id': fg_id, 'qty': float(order.get('quantity') or 0),
                  'already': already_total}]

    # gabungkan baris yang menunjuk FG yang SAMA (kalau tidak, usulannya dobel)
    merged: dict = {}
    for w in wants:
        m = merged.setdefault(w['fg_material_id'], {'qty': 0.0, 'already': 0.0})
        m['qty'] += w['qty']
        m['already'] += w['already']

    items_out = []
    for mid, agg in merged.items():
        fg = await db.rahaza_materials.find_one(
            {'id': mid}, {'_id': 0, 'id': 1, 'code': 1, 'name': 1}) or {}
        res = await _cstock.sellable_stock(db, mid)
        items_out.append({
            'material_id': fg.get('id') or mid,
            'sku_code': fg.get('code', ''),
            'material_name': fg.get('name', ''),
            'qty_allocated': agg['qty'],
            'available': res['available'],
            'onhand': res['onhand'],
            'reserved': res['reserved'],
            'enough': res['available'] + agg['already'] >= agg['qty'],
        })

    return {
        'ok': True,
        'auto_resolved': True,
        'order_id': order.get('order_id'),
        'already_reserved_qty': already_total,
        'items': items_out,
        'message': ('Usulan otomatis dari tautan order — periksa lalu konfirmasi.'),
    }


@router.post("/orders/{order_id}/allocate")
async def allocate_inventory(
    order_id: str,
    payload: AllocateInventoryIn,
    user: dict = Depends(require_auth)
):
    """
    Allocate FG inventory ke order.
    Reserve qty di rahaza_material_stock (available_quantity -= qty, reserved_quantity += qty).

    **M10 (2026-08-10)** — order yang sudah memesan stok saat dibuat punya
    reservasi tingkat-order. Reservasi itu DILEPAS lebih dulu di sini supaya
    `allocate` tidak menghitung reservasi DUA KALI (dulu belum ada reservasi saat
    create, jadi masalah ini belum bisa muncul).
    """
    db = get_db()
    order = await _get_order(db, order_id)
    
    # Check status: harus pending_fulfillment
    await _check_fulfillment_status(order, ["pending_fulfillment"])

    # M10 — lepas reservasi tingkat-order dulu (idempoten) agar tidak dobel.
    # K-8b — rincian reservasi per baris order ikut dibersihkan, kalau tidak
    # layar/audit akan menampilkan reservasi yang sudah dipindah ke alokasi.
    if order.get("stock_reserved"):
        from core import catalog_stock as _cstock
        await _cstock.release_rows(db, order.get("reserved_rows") or [])
        _clear: dict = {"stock_reserved": False, "reserved_qty": 0.0, "reserved_rows": [],
                        "reservation_moved_to_allocation_at": _now()}
        _lines = order.get("items") or []
        if any(isinstance(ln, dict) and ln.get("reserved_rows") for ln in _lines):
            for ln in _lines:
                if isinstance(ln, dict):
                    ln["reserved_rows"] = []
                    ln["reserved_qty"] = 0.0
                    ln["reservation_moved_to_allocation"] = True
            _clear["items"] = _lines
        await db.marketing_orders.update_one({"id": order_id}, {"$set": _clear})
    
    # Validate & reserve stock
    from core import catalog_stock as _cstock
    fulfillment_items = []
    for item in payload.items:
        mat = await db.rahaza_materials.find_one(
            {"id": item.material_id}, {"_id": 0, "code": 1, "name": 1}) or {}
        # Reservasi HANYA dari baris stok yang boleh dijual (K-6a: bukan
        # karantina/blokir) — SATU sumber reservasi kanonik `reserved_quantity`
        # lewat stock_service, jadi tetap sinkron dengan reservasi manual FG Matrix.
        try:
            rsv = await _cstock.reserve_sellable(
                db, item.material_id, item.qty_allocated,
                ref={"source": "fulfillment_allocate", "order_id": order_id},
                actor={"id": user.get("id", ""), "email": user.get("email", "")})
        except stock_service.InsufficientStock as e:
            avail = getattr(e, "available", 0)
            raise HTTPException(
                400, f"Stok jual {mat.get('code') or item.material_id} tidak cukup. "
                     f"Tersedia: {avail}, diminta: {item.qty_allocated}") from None

        rows = rsv["rows"]
        fulfillment_items.append({
            "material_id": item.material_id,
            "sku_code": item.sku_code or mat.get("code", ""),
            "material_name": item.material_name or mat.get("name", ""),
            "qty_allocated": item.qty_allocated,
            "location_id": item.location_id or (rows[0].get("location_id") if rows else ""),
            "stock_id": rows[0]["stock_id"] if rows else None,
            "reserved_rows": rows,
        })
    
    # Update order
    await db.marketing_orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "fulfillment_status": "allocated",
                "fulfillment_items": fulfillment_items,
                "allocated_at": _now(),
                "allocated_by": user.get("name", ""),
                "updated_at": _now()
            }
        }
    )
    
    await log_activity(
        user.get("id", ""),
        user.get("name", ""),
        "allocate_inventory",
        "marketing_orders",
        f"Allocate {len(fulfillment_items)} items untuk order {order.get('order_id')}"
    )
    
    return {
        "status": "success",
        "message": f"{len(fulfillment_items)} items dialokasikan",
        "fulfillment_items": fulfillment_items
    }


@router.post("/orders/{order_id}/pick")
async def start_picking(order_id: str, user: dict = Depends(require_auth)):
    """Mark order as picking (sedang diambil dari gudang)."""
    db = get_db()
    order = await _get_order(db, order_id)
    
    await _check_fulfillment_status(order, ["allocated"])
    
    await db.marketing_orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "fulfillment_status": "picking",
                "picking_started_at": _now(),
                "picking_by": user.get("name", ""),
                "updated_at": _now()
            }
        }
    )
    
    await log_activity(
        user.get("id", ""),
        user.get("name", ""),
        "start_picking",
        "marketing_orders",
        f"Start picking order {order.get('order_id')}"
    )
    
    return {"status": "success", "message": "Picking dimulai"}


@router.post("/orders/{order_id}/pack")
async def confirm_packing(order_id: str, user: dict = Depends(require_auth)):
    """Confirm packing done (barang sudah dikemas, siap kirim)."""
    from routes.shared import assert_can_act
    assert_can_act(user, 'toko.manage', 'warehouse.manage', portal='warehouse',
                   legacy_roles=('spv_packing', 'tim_packing', 'admin_gudang', 'pic_toko',
                                 'cs_staff', 'manager_marketing', 'manager',
                                 'owner', 'admin', 'superadmin'),
                   what='mengonfirmasi pengemasan pesanan')
    db = get_db()
    order = await _get_order(db, order_id)
    
    await _check_fulfillment_status(order, ["picking"])
    
    await db.marketing_orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "fulfillment_status": "packed_ready",
                "packed_at": _now(),
                "packed_by": user.get("name", ""),
                "updated_at": _now()
            }
        }
    )
    
    await log_activity(
        user.get("id", ""),
        user.get("name", ""),
        "confirm_packing",
        "marketing_orders",
        f"Packing selesai untuk order {order.get('order_id')}"
    )
    
    return {"status": "success", "message": "Packing selesai"}


@router.post("/orders/{order_id}/dispatch")
async def dispatch_order(
    order_id: str,
    payload: DispatchIn,
    user: dict = Depends(require_auth)
):
    """
    Dispatch order (WS-E — scan-out required):
    1. Buat PENDING OUTBOUND_FG di WMS untuk tiap item (stok BELUM berkurang).
    2. Order → 'awaiting_scanout'. Simpan metadata shipment (resi, kurir).
    3. Stok FG berkurang + COGS diposting SAAT gudang melakukan Scan-Out
       (lihat finalize_fulfillment_dispatch, dipicu dari WMS scan-out).
    """
    db = get_db()
    order = await _get_order(db, order_id)

    await _check_fulfillment_status(order, ["packed_ready"])

    fulfillment_items = order.get("fulfillment_items", [])
    if not fulfillment_items:
        raise HTTPException(400, "Tidak ada items yang dialokasikan")

    from routes.wms_receiving import helper_create_pending_outbound_fg

    shipment_id = _uid()
    shipment_number = f"FUL-{order.get('order_id')}"

    # 1. Buat pending outbound_fg per item (stok belum turun, reserved tetap)
    pendings = []
    for item in fulfillment_items:
        qty = item.get("qty_allocated", 0)
        pending = await helper_create_pending_outbound_fg(
            db,
            material_id=item.get("material_id", ""),
            material_code=item.get("sku_code", ""),
            material_name=item.get("material_name", ""),
            qty=float(qty),
            unit="pcs",
            source_type="fulfillment",
            source_id=order_id,
            source_ref=order.get("order_id", order_id),
            notes=f"Dispatch order {order.get('order_id')} — Scan-Out diperlukan",
            created_by=user.get("email", user.get("name", "system")),
            dedupe=True,
            extra={
                "stock_id": item.get("stock_id"),
                "location_id": item.get("location_id", ""),
                "order_id": order_id,
            },
        )
        pendings.append({"pending_id": pending.get("id"), "ref_number": pending.get("ref_number"),
                         "material_name": item.get("material_name", ""), "qty": qty})

    # 2. Simpan metadata shipment (belum di-posting) + status awaiting_scanout
    pending_shipment = {
        "id": shipment_id,
        "shipment_number": shipment_number,
        "order_id": order_id,
        "marketing_order_id": order_id,
        "items": [
            {
                "material_id": it.get("material_id"),
                "qty": it.get("qty_allocated"),
                "sku_code": it.get("sku_code"),
                "work_order_id": it.get("work_order_id") or it.get("wo_id"),
            } for it in fulfillment_items
        ],
        "tracking_number": payload.tracking_number,
        "courier": payload.courier,
        "notes": payload.notes,
        "created_by": user.get("name", ""),
        "created_at": _now(),
    }

    await db.marketing_orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "fulfillment_status": "awaiting_scanout",
                "awaiting_scanout_at": _now(),
                "pending_shipment": pending_shipment,
                "shipment_ref": shipment_id,
                "tracking_number": payload.tracking_number,
                "courier": payload.courier,
                "cogs_posted": False,
                "updated_at": _now(),
            }
        }
    )

    await log_activity(
        user.get("id", ""),
        user.get("name", ""),
        "dispatch_order",
        "marketing_orders",
        f"Dispatch order {order.get('order_id')} → antrian Scan-Out ({len(pendings)} items)"
    )

    return {
        "status": "success",
        "fulfillment_status": "awaiting_scanout",
        "message": f"{len(pendings)} item masuk antrian Scan-Out gudang. Stok & COGS diproses setelah Scan-Out dikonfirmasi.",
        "shipment_id": shipment_id,
        "shipment_number": shipment_number,
        "pending_movements": pendings,
        "scan_out_required": True,
    }


async def finalize_fulfillment_dispatch(db, order_id: str, user: dict) -> dict:
    """
    Dipicu dari WMS scan-out ketika outbound_fg suatu order sudah confirmed.
    Setelah SEMUA outbound_fg untuk order ini confirmed:
      - Posting COGS (idempotent via post_cogs_shipment)
      - Simpan dokumen shipment
      - Order → 'dispatched'
    Idempotent & aman dipanggil berulang.
    """
    order = await db.marketing_orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        return {"ok": False, "reason": "order_not_found"}
    if order.get("fulfillment_status") == "dispatched":
        return {"ok": True, "already_dispatched": True}

    movements = await db.wh_pending_movements.find(
        {"source_id": order_id, "source_type": "fulfillment", "type": "outbound_fg",
         "status": {"$ne": "cancelled"}},
        {"_id": 0}
    ).to_list(500)
    if not movements:
        return {"ok": False, "reason": "no_pending_movements"}

    not_confirmed = [m for m in movements if m.get("status") != "confirmed"]
    if not_confirmed:
        return {"ok": False, "reason": "scan_out_incomplete", "pending_count": len(not_confirmed)}

    # Semua sudah scan-out → posting COGS + finalisasi
    shipment = order.get("pending_shipment") or {
        "id": order.get("shipment_ref") or _uid(),
        "shipment_number": f"FUL-{order.get('order_id')}",
        "order_id": order_id,
        "marketing_order_id": order_id,
        "items": [
            {"material_id": it.get("material_id"), "qty": it.get("qty_allocated"),
             "sku_code": it.get("sku_code"),
             "work_order_id": it.get("work_order_id") or it.get("wo_id")}
            for it in order.get("fulfillment_items", [])
        ],
        "created_at": _now(),
    }
    shipment["dispatched_at"] = _now()

    # H-07: biaya batch FIFO IKUT KELUAR bersama barang pesanan online (satu kali per shipment).
    # Scan-out WMS mengurangi stok lewat stock_service (bukan qty_ledger.issue_fg), jadi lapisan
    # HPP batch dimakan di sini agar COGS memakai biaya NYATA, bukan snapshot perkiraan.
    if not shipment.get("fg_cogs_consumed_at"):
        from core import fg_cost_layers as fcl
        for it in shipment.get("items") or []:
            if not it.get("material_id") or int(it.get("qty") or 0) <= 0:
                continue
            try:
                c = await fcl.consume_fifo(db, material_id=it["material_id"], qty=int(it["qty"]),
                                           ref={"source": "fulfillment", "order_id": order_id,
                                                "shipment_id": shipment["id"], "sku": it.get("sku_code")},
                                           actor=user)
                it["fg_cogs"] = c.get("cogs", 0.0)
                it["fg_cogs_layers"] = c.get("layers_used") or []
                it["fg_cogs_uncosted_qty"] = c.get("uncosted_qty", 0)
            except Exception as e:  # noqa: BLE001
                logger.warning(f"konsumsi lapisan HPP batch gagal (order {order_id}, {it.get('sku_code')}): {e}")
        shipment["fg_cogs_consumed_at"] = _now()
        await db.rahaza_shipments.update_one({"id": shipment["id"]}, {"$set": shipment}, upsert=True)

    cogs_result = await post_cogs_shipment(db, shipment, user)

    # Simpan shipment (upsert by id) untuk audit
    try:
        await db.rahaza_shipments.update_one(
            {"id": shipment["id"]},
            {"$set": {**shipment, "cogs_posted": cogs_result.get("ok", False),
                      "cogs_je_id": cogs_result.get("je_id"),
                      "cogs_je_number": cogs_result.get("je_number")}},
            upsert=True,
        )
    except Exception as e:
        logger.warning(f"Gagal simpan shipment {shipment.get('id')}: {e}")

    await db.marketing_orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "fulfillment_status": "dispatched",
                "dispatched_at": _now(),
                "dispatched_by": user.get("name", "") or user.get("email", ""),
                "shipment_ref": shipment["id"],
                "cogs_posted": cogs_result.get("ok", False),
                "cogs_je_id": cogs_result.get("je_id"),
                "cogs_je_number": cogs_result.get("je_number"),
                "cogs_error": cogs_result.get("error"),
                "updated_at": _now(),
            }
        }
    )

    await log_activity(
        user.get("id", ""),
        user.get("name", ""),
        "dispatch_finalized",
        "marketing_orders",
        f"Order {order.get('order_id')} dispatched (scan-out selesai). COGS: {cogs_result.get('je_number') or cogs_result.get('error')}"
    )

    return {
        "ok": True,
        "dispatched": True,
        "shipment_id": shipment["id"],
        "shipment_number": shipment.get("shipment_number"),
        "cogs_posted": cogs_result.get("ok", False),
        "cogs_je_number": cogs_result.get("je_number"),
        "cogs_error": cogs_result.get("error"),
    }
